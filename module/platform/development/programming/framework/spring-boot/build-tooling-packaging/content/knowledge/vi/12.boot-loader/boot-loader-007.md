# Khi nào cần requiresUnpack hoặc cấu hình unpack của plugin trong Spring Boot Loader

## 1. Mục tiêu bài học

Executable JAR của Spring Boot thường đặt các dependency JAR bên trong chính JAR ứng dụng: `BOOT-INF/lib/library.jar`. Spring Boot Loader có thể nạp classes và resources trực tiếp từ cấu trúc **nested JAR** mà không phải giải nén tất cả dependency ra ổ đĩa. Đây là khả năng mặc định, áp dụng tốt với phần lớn thư viện Java.

Tuy nhiên một số thư viện bên thứ ba không chỉ dùng Java class loading. Chúng tự mở chính file JAR bằng đường dẫn `java.io.File`, dùng thư viện đọc ZIP riêng, yêu cầu một JAR có đường dẫn vật lý, hoặc thực hiện một thao tác nội bộ không hiểu nested JAR URL. Trong những trường hợp **đã được xác nhận** đó, Spring Boot packaging plugin cung cấp cơ chế `requiresUnpack` để đánh dấu dependency cần được **giải nén ra một thư mục tạm khi ứng dụng được khởi chạy qua Spring Boot Loader**.

Sau bài này, bạn có thể:

- Giải thích được Spring Boot Loader nạp nested JAR ra sao và vì sao mặc định **không cần** unpack.
- Nhận diện dấu hiệu thực tế cho biết một thư viện **phải có file JAR thật trên filesystem**.
- Phân biệt `requiresUnpack` với `exclude`, `unpack` toàn bộ executable archive, ZIP compression và Maven/Gradle dependency resolution.
- Cấu hình `requiresUnpack` chính xác với **Gradle Groovy DSL**, **Gradle Kotlin DSL** và **Spring Boot Maven Plugin**.
- Biết pattern Gradle khớp **đường dẫn tuyệt đối của source dependency JAR** chứ không phải một Java package hay tùy ý một tên ở runtime.
- Kiểm tra hiệu lực qua artifact cuối, chạy `java -jar` và các phép thử phù hợp; hạn chế false positive khi chỉ chạy `bootRun` hoặc IDE.
- Xử lý các lỗi quyền thư mục tạm, môi trường container và dependency path mà không áp dụng unpack rộng rãi vô cớ.

**Phạm vi:** Spring Boot executable JAR/WAR, Spring Boot Loader và cấu hình packaging. Ví dụ sử dụng Spring Boot 3.3.13, Java 17 làm mốc nhất quán; đây là phiên bản minh họa, không phải tuyên bố bản Spring Boot mới nhất.

## 2. Cơ chế nền: Boot Loader đọc nested JAR

### 2.1. Vì sao executable Spring Boot JAR có cấu trúc khác plain JAR?

Với Spring Boot Gradle `bootJar` hoặc Maven `spring-boot:repackage`, cấu trúc executable JAR tiêu biểu:

~~~text
app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   └── com/example/demo/DemoApplication.class
    └── lib/
        ├── spring-boot-3.3.13.jar
        ├── spring-context-....jar
        └── some-library-1.2.3.jar
~~~

Đây là cấu trúc khái quát; tên và số lượng thư viện phụ thuộc dependency graph, plugin configuration và phiên bản. Một JAR tạo bởi Java plugin `jar` thông thường có thể chỉ chứa classes/resources của module, không có layout `BOOT-INF` và Boot Loader.

Manifest của executable Spring Boot 3.3 JAR thông thường:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.DemoApplication
~~~

`Main-Class` là launcher của Spring Boot; `Start-Class` là ứng dụng. Khi chạy:

~~~bash
java -jar app.jar
~~~

JVM gọi Boot launcher; loader chuẩn bị class loader có thể đọc nested dependency JAR từ `BOOT-INF/lib` và sau đó gọi ứng dụng. Java class loader chuẩn không tự hiểu mọi loại nested JAR URL, nên Spring Boot cung cấp cơ chế loader riêng.

### 2.2. Thông thường không có bước giải nén hàng loạt

Spring Boot Loader hỗ trợ đọc nội dung của nested JAR thông qua cơ chế seek vào outer archive. Dependency JAR nằm trong outer JAR theo bố cục mà loader hỗ trợ; thông thường không cần tạo file riêng bên ngoài cho từng dependency.

Sơ đồ hai luồng:

~~~text
Trường hợp thông thường:
app.jar
  └─ BOOT-INF/lib/library.jar
      └─ Spring Boot Loader đọc nested JAR trực tiếp
          └─ class/resource được nạp vào ứng dụng

Thư viện được đánh dấu requiresUnpack:
app.jar
  └─ BOOT-INF/lib/problem-library.jar
      └─ Spring Boot Loader giải nén JAR đó ra vị trí tạm
          └─ runtime có thể sử dụng bản JAR nằm trên filesystem
~~~

Cần phân biệt hai mốc thời gian:

- **Build time:** Gradle/Maven plugin đóng gói executable archive và ghi thông tin rằng một số nested dependency cần unpack.
- **Runtime:** khi executable archive được khởi chạy qua Spring Boot Loader, loader xử lý những dependency đã được đánh dấu.

Do đó `requiresUnpack` **không có nghĩa Gradle/Maven sẽ giải nén source JAR ra `build/libs` hoặc `target` lúc build**. Cũng không có nghĩa nó sẽ tự tạo một `lib` directory cố định bên cạnh `app.jar`.

### 2.3. Nested JAR cần định dạng ZIP phù hợp

Theo Spring Boot executable JAR specification, ZIP entry chứa **nested JAR** phải được lưu bằng phương thức `STORED` trong outer archive để loader có thể seek trực tiếp. Bên trong nested JAR, các entry riêng vẫn có thể được nén bình thường.

Đây là điều kiện về **định dạng archive**, khác với `requiresUnpack`:

- `STORED`: cách lưu entry nested JAR trong outer ZIP, giúp loader đọc trực tiếp.
- `requiresUnpack`: quyết định một dependency cụ thể có cần **file thực trên đĩa ở runtime** hay không.

Nếu archive bị đóng gói lại sai khiến nested JAR entry không còn phù hợp định dạng Boot, đặt `requiresUnpack` không phải phương án sửa đúng. Cần dùng plugin đóng gói Spring Boot phù hợp và tránh tự sửa ZIP bằng tool làm mất metadata/layout.

## 3. Khi nào thật sự cần `requiresUnpack`?

Một thư viện Java bình thường chỉ dùng classes/resources qua context class loader, `getResourceAsStream` hay các API JAR URL tương thích thì thường **không cần** unpack.

Xem xét `requiresUnpack` khi có **bằng chứng** thư viện cần thao tác trực tiếp với một file JAR trên filesystem, chẳng hạn:

1. Thư viện tự đọc JAR của chính nó bằng `File` hoặc `Path` và kỳ vọng `File.exists()` là true đối với một JAR độc lập.
2. Thư viện có class loader, ZIP/JAR parser hoặc native bridge riêng **không hiểu Boot nested URL**.
3. Một thành phần nội bộ của thư viện yêu cầu mở một JAR file bằng API chỉ chấp nhận filesystem path.
4. Tài liệu chính thức của thư viện hoặc Spring Boot khuyến nghị chọn chính dependency đó để unpack khi chạy bên trong executable Boot archive.
5. Có thể tái hiện lỗi chỉ trong `java -jar` của executable archive, còn khi chạy bằng IDE/Gradle `bootRun` thì thành công vì các dependency là file JAR vật lý trên disk.

**Ví dụ có trong tài liệu Spring Boot:** `JRuby`/`jruby-complete` có khả năng xử lý nested archive riêng và có giả định về việc file `jruby-complete.jar` tồn tại trực tiếp trên filesystem. Spring Boot dùng trường hợp này làm ví dụ của `requiresUnpack`. Không suy rộng rằng *mọi* phiên bản JRuby hoặc *mọi* ứng dụng dùng JRuby chắc chắn sẽ lỗi; phải kiểm tra dependency và version thực tế.

### 3.1. Những dấu hiệu chỉ mang tính gợi ý

Bảng dưới đây hỗ trợ khoanh vùng, không phải bộ quy tắc tự động:

| Dấu hiệu | Có thể liên quan tới unpack? | Kiểm tra trước khi kết luận |
| --- | --- | --- |
| `ClassNotFoundException` khi `java -jar` | Có thể, nhưng rất nhiều nguyên nhân khác | Xác nhận dependency nằm trong `BOOT-INF/lib`/`WEB-INF/lib` và runtime scope |
| `FileNotFoundException` với đường dẫn chứa `jar:nested:...` | Có thể | Xem library có đang chuyển JAR URL thành `File` không |
| Thư viện báo “JAR must be on filesystem” | Khá phù hợp | Xác định chính xác artifact và liệu thư viện hỗ trợ nested URL hay không |
| `UnsatisfiedLinkError` | Chưa đủ | Kiểm tra native library packaging, OS/ABI, `java.library.path`, quyền filesystem |
| Chạy `bootRun` thành công, `java -jar` lỗi | Cần điều tra nested-JAR behavior | So sánh classpath, JVM, profiles, external config và executable artifact |
| Dependency không được tải từ repository | Không | Đây là lỗi dependency resolution/repository, không phải unpack |
| Thiếu `Main-Class`/`Start-Class` | Không | Đây là lỗi executable packaging/entrypoint |
| Muốn giảm dung lượng JAR | Không | Unpack ở runtime không tự loại dependency khỏi archive |
| Chỉ muốn tạo Docker image nhỏ hơn | Không | Cần xem layers, image build và dependency trimming |
| Ứng dụng cần external config file | Thường không | Dùng Spring externalized configuration, không unpack dependency JAR |
| Thư viện cần ghi file bên trong JAR | Không nhất thiết giải quyết được | JAR artifact vẫn là read-only archive; cần writable directory riêng |

Nguyên tắc: **chỉ đánh dấu đúng thư viện gặp hạn chế**, dựa trên tái hiện hoặc tài liệu nhà cung cấp. Không bật unpack cho toàn bộ `BOOT-INF/lib` để “chắc ăn”.

### 3.2. Vì sao chạy trong IDE có thể che lỗi?

Khi chạy từ IDE, Gradle `bootRun` hoặc Maven `spring-boot:run`, các dependencies thường đã là những file vật lý trong Gradle/Maven cache, ví dụ đường dẫn kiểu `.../caches/modules-2/files-2.1/.../library.jar` hoặc `.../.m2/repository/.../library.jar`.

Khi đóng gói thành executable Boot JAR, cùng dependency được lồng trong `BOOT-INF/lib`. Nếu thư viện tự trích xuất location thành `File`, nó có thể hoạt động trong IDE nhưng lỗi với nested URL.

Bởi vậy **phép thử quyết định** là chạy chính executable archive qua Boot Loader:

~~~bash
java -jar path/to/app.jar
~~~

Không thể xác minh đầy đủ `requiresUnpack` chỉ bằng `bootRun`; task đó không phản ánh đầy đủ cơ chế nested archive của sản phẩm phát hành.

## 4. `requiresUnpack` không phải những thao tác nào?

| Cơ chế | Tác dụng | Có thay cho `requiresUnpack` không? |
| --- | --- | --- |
| Gradle/Maven dependency declaration | Đưa thư viện vào dependency graph và runtime classpath | Không: thư viện có mặt chưa nói loader có phải unpack hay không |
| `requiresUnpack` | Đánh dấu nested dependency phải được giải nén lúc Boot Loader chạy | Đúng cơ chế cho lỗi “cần file JAR vật lý” |
| `exclude`/`excludes` của plugin | Bỏ dependency khỏi executable archive theo quy tắc | Không: bỏ thư viện có thể làm ứng dụng thiếu class |
| Gradle `zipTree`/Maven Shade | Có thể giải nén/trộn nội dung JAR tại build time | Không tương đương và có rủi ro trùng class/resources |
| `jar -xf app.jar` | Giải nén archive thủ công ở vị trí bạn chọn | Không tự đặt marker để Boot Loader unpack thư viện |
| `java -Djarmode=tools -jar app.jar extract` | Trích xuất executable JAR theo một layout được Spring Boot hỗ trợ, phục vụ triển khai | Khác: là thao tác trích xuất ứng dụng, không chọn từng library |
| Layered JAR / `layers.idx` | Mô tả các lớp để hỗ trợ caching trong image build | Không |
| `launchScript()` / fully executable JAR | Thêm shell launch script để chạy archive trực tiếp trên môi trường phù hợp | Không |
| `loader.path` của PropertiesLauncher | Tùy chỉnh vị trí thư viện/classpath khi dùng launcher tương ứng | Không tự giải quyết mọi thư viện cần JAR file vật lý |

**Từ khóa unpack có nhiều nghĩa.** Trong bài này, `requiresUnpack` nghĩa là **cấu hình ngoại lệ để Spring Boot Loader unpack dependency cụ thể khi khởi chạy**, không phải trích xuất toàn bộ artifact sau build.

## 5. Gradle Groovy DSL: cấu hình `bootJar.requiresUnpack`

### 5.1. Bản build đầy đủ không có dependency đặc biệt

Tạo project Java/Spring Boot đơn module; tệp `settings.gradle`:

~~~groovy
rootProject.name = 'unpack-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Đây là một **build script độc lập** cho ví dụ cơ bản. Nó có Spring Boot plugin, Java plugin, Java toolchain và dependency management phù hợp với mốc Spring Boot 3.3.13. Không có thư viện nào trong bản ví dụ cần unpack, vì vậy **không khai báo `requiresUnpack` là lựa chọn đúng**.

Gradle wrapper (`gradlew`, `gradle/wrapper`) cần được tạo/sẵn có từ quy trình project; tệp `build.gradle` không tự sinh wrapper.

### 5.2. Fragment `requiresUnpack` chính thức

Khi dependency cụ thể được xác nhận cần file JAR vật lý, Spring Boot 3.3 dùng cú pháp này cho Gradle Groovy DSL:

~~~groovy
tasks.named("bootJar") {
    requiresUnpack '**/jruby-complete-*.jar'
}
~~~

Đây là **fragment bổ sung vào `build.gradle`**, không phải build script độc lập. Nó chỉ có tác dụng với những dependency JAR thực sự xuất hiện trong classpath được đóng gói và khớp pattern.

Để minh họa cách kết hợp với một dependency JRuby thực tế nếu dự án **có sử dụng JRuby**, có thể khai báo:

~~~groovy
dependencies {
    implementation 'org.jruby:jruby-complete:9.4.6.0'
}

tasks.named("bootJar") {
    requiresUnpack '**/jruby-complete-*.jar'
}
~~~

Hai khối này là **fragment theo tình huống**, không phải yêu cầu thêm JRuby vào ví dụ cơ bản. Version JRuby ở đây chỉ để biểu diễn dependency coordinate, không phải khuyến nghị upgrade/downgrade; dự án thật phải xác minh version tương thích, repository, CVEs và nhu cầu sử dụng.

`requiresUnpack '**/jruby-complete-*.jar'` sử dụng **Ant-style path pattern**. Theo tài liệu Spring Boot 3.3, matcher được áp dụng cho **đường dẫn tuyệt đối của file source dependency JAR** lúc đóng gói. Pattern `**/` khớp các cấp thư mục, `*` khớp phần biến thiên như version trong filename. Một tên như `jruby-complete-9.4.6.0.jar` có thể khớp, nếu file thực tế có tên và path phù hợp.

### 5.3. Không dùng pattern là Java package

Các pattern sau là ví dụ sai hoặc rủi ro:

~~~groovy
tasks.named("bootJar") {
    requiresUnpack 'org/jruby/**'  // Sai ý định: đây là tên package/classes
    requiresUnpack '*.jar'         // Quá rộng, có thể bắt nhiều thư viện
}
~~~

Mục tiêu không phải tìm `org/jruby` **bên trong** nested archive; matcher nhắm tới **file JAR nguồn** đã resolve từ Gradle dependency graph. Dùng một pattern tên JAR đủ hẹp, ví dụ `**/jruby-complete-*.jar`, và xác minh đúng file được chọn. Pattern rộng có thể khiến runtime giải nén hàng loạt dependency, làm tăng I/O và phụ thuộc temporary filesystem không cần thiết.

**Chú ý:** câu lệnh ví dụ “sai” trên chỉ nhằm nhận diện lỗi thiết kế; **đừng chép nó vào project đang học**.

### 5.4. Dùng closure khi cần điều kiện nâng cao

Spring Boot Gradle Plugin hỗ trợ overload nhận một closure làm predicate. Closure nhận một `FileTreeElement` và trả `boolean`, cho phép chọn dependency theo file path/filename.

Ví dụ Groovy fragment minh họa:

~~~groovy
tasks.named("bootJar") {
    requiresUnpack { element ->
        element.file.name.startsWith('jruby-complete-') &&
            element.file.name.endsWith('.jar')
    }
}
~~~

Cách này có ích khi matcher cần logic chính xác hơn một Ant pattern. Đổi lại, nó làm build logic phức tạp hơn. Trong phần lớn trường hợp, pattern tường minh dễ đọc và dễ bảo trì hơn. Đừng viết closure dựa trên tên folder cache cụ thể của một developer vì Gradle cache path khác nhau giữa các máy.

**Phân biệt:** closure/predicate được đánh giá khi plugin quyết định file nào sẽ được đánh dấu trong artifact; nó không có nghĩa closure Java/Groovy được đóng gói để chạy tại runtime.

## 6. Gradle Kotlin DSL: cấu hình tương đương

### 6.1. Bản build Kotlin chạy được

Tệp `settings.gradle.kts`:

~~~kotlin
rootProject.name = "unpack-demo"
~~~

Tệp `build.gradle.kts`:

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

Bản này tương đương Groovy ở mục 5.1: tạo Boot executable JAR, không yêu cầu unpack bất kỳ library nào trong ví dụ cơ bản. Kotlin DSL là **ngôn ngữ script build**, không buộc bạn phải viết ứng dụng bằng Kotlin; Java class ở mục 8 dùng chung.

### 6.2. Fragment `requiresUnpack` chính xác

Ở **đầu `build.gradle.kts`**, thêm import (đặt ngoài mọi block):

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar
~~~

Sau đó cấu hình task:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    requiresUnpack("**/jruby-complete-*.jar")
}
~~~

Đây là cú pháp được Spring Boot 3.3 tài liệu hóa: `BootJar` là kiểu task, `requiresUnpack(...)` là phương thức dùng pattern string.

Nếu project thực sự dùng JRuby, dependency tương ứng sẽ nằm trong `dependencies`:

~~~kotlin
dependencies {
    implementation("org.jruby:jruby-complete:9.4.6.0")
}
~~~

Không đặt dependency version mẫu vào một hệ thống thực mà chưa kiểm tra version/resolution/compatibility. Chỉ thêm `requiresUnpack` cho dependency đã xác định, không thay đổi toàn bộ classpath.

Trong Kotlin DSL, `tasks.named("bootJar")` không luôn cho bạn typed API của `BootJar` khi khai báo một biến task chung. `tasks.named<BootJar>("bootJar")` giúp compiler biết kiểu task và nhận đúng method.

### 6.3. Cấu hình nhiều dependency

Nếu có **hai thư viện thực sự cần file vật lý**, có thể thêm hai pattern cụ thể:

**Groovy:**

~~~groovy
tasks.named("bootJar") {
    requiresUnpack '**/legacy-engine-*.jar'
    requiresUnpack '**/jruby-complete-*.jar'
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    requiresUnpack("**/legacy-engine-*.jar")
    requiresUnpack("**/jruby-complete-*.jar")
}
~~~

`legacy-engine` ở đây là **tên giả để minh họa** và không đại diện cho thư viện thật; chỉ giữ khi dự án có artifact và bằng chứng đúng. Không thêm cả hai theo mẫu nếu thực tế chỉ có một dependency vấn đề.

## 7. Maven: `spring-boot-maven-plugin` cấu hình unpack ra sao?

Maven không có task Gradle tên `bootJar`. Với Maven, Spring Boot Maven Plugin dùng goal `repackage`, có tham số `requiresUnpack` nhận **danh sách dependency** cần được giải nén khi runtime.

Khác với Gradle:

- Gradle chọn file dependency bằng **Ant-style pattern** khớp absolute source JAR path.
- Maven chọn dependency theo tọa độ **`groupId` và `artifactId`** trong cấu hình `requiresUnpack`.

### 7.1. Fragment Maven cho JRuby

Trong `pom.xml` của một ứng dụng Maven đã có Spring Boot parent/plugin, cấu hình:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <requiresUnpack>
                    <dependency>
                        <groupId>org.jruby</groupId>
                        <artifactId>jruby-complete</artifactId>
                    </dependency>
                </requiresUnpack>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đoạn này là **fragment XML**, cần hợp nhất vào `<build><plugins>` hiện tại; không tạo hai khối `<build>` lặp. `requiresUnpack` nhắm tới **dependency có group/artifact đã khai báo**, không phải đường dẫn `BOOT-INF/lib` hay tên package Java.

Một dependency Maven JRuby minh họa (chỉ thêm khi project thực sự cần):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.jruby</groupId>
        <artifactId>jruby-complete</artifactId>
        <version>9.4.6.0</version>
    </dependency>
</dependencies>
~~~

Bản Maven `requiresUnpack` không yêu cầu ghi version trong mỗi item `<dependency>` của `requiresUnpack`; dependency và version thực tế được resolve từ POM/`dependencyManagement`/transitive graph. Bạn phải xác định artifact có thực sự được đưa vào executable archive không.

### 7.2. Maven `repackage` phải có execution

Nếu dùng `spring-boot-starter-parent` cho ứng dụng, parent có execution `repackage` chuẩn; khai báo plugin trong `build/plugins` thường đủ để `mvn package` tạo executable archive.

Nếu **không dùng** starter parent, chỉ import Spring Boot BOM, có thể phải khai báo plugin version và execution đúng phase để `repackage` chạy. Ví dụ fragment trong Maven module dùng parent khác:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.13</version>
    <configuration>
        <requiresUnpack>
            <dependency>
                <groupId>org.jruby</groupId>
                <artifactId>jruby-complete</artifactId>
            </dependency>
        </requiresUnpack>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây là **plugin fragment**, không phải toàn bộ POM. Nếu parent đã định nghĩa execution, không tự copy thêm execution thứ hai và dẫn tới goal chạy nhiều lần. Dùng `mvn help:effective-pom` và log `package` để kiểm chứng.

### 7.3. Lệnh Maven để kiểm tra

~~~bash
mvn dependency:tree
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn clean package
java -jar target/ten-ung-dung-thuc-te.jar
~~~

Dòng cuối là **đường dẫn mô tả**, cần thay bằng đúng executable artifact đang có dưới `target`; không phải file có tên cố định do ví dụ tạo sẵn. Nếu dự án có Maven wrapper, dùng `./mvnw` trên Linux/macOS hoặc `.\mvnw.cmd` trên Windows.

Kiểm tra trong effective POM: version của `spring-boot-maven-plugin`, execution `repackage` và cấu hình `requiresUnpack` có đúng không. Kiểm tra `mvn dependency:tree` xem `org.jruby:jruby-complete` thực sự có trong resolved dependencies không. Chỉ khi file executable được tạo và chạy qua Boot Loader mới có ý nghĩa thử runtime unpack.

## 8. Java 17: chương trình nhỏ chạy được trước khi cần unpack

Tạo tệp `src/main/java/com/example/demo/DemoApplication.java` trong một trong hai project Gradle hoàn chỉnh ở mục 5.1 hoặc 6.1:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner reportStart() {
        return args -> System.out.println("APP_STARTED nested-ok");
    }
}
~~~

Ứng dụng sử dụng `spring-boot-starter` (không cần embedded web server), tạo Spring context, chạy `CommandLineRunner` và có thể kết thúc sau khi startup nếu không có background non-daemon process. Với cấu hình không có dependencies đặc biệt, **không cần requiresUnpack**.

Từ project có wrapper Gradle hợp lệ:

~~~bash
./gradlew clean bootJar
java -jar build/libs/unpack-demo-0.1.0.jar
~~~

Trong log startup còn có dòng của Spring Boot. Dòng **stdout do chương trình tự in** là:

~~~text
APP_STARTED nested-ok
~~~

**Điều dòng này chứng minh:** executable JAR cơ bản chạy được qua Boot Loader. Nó **không chứng minh** rằng JRuby (nếu chỉ mới ghi fragment nhưng ứng dụng không sử dụng API JRuby) gặp lỗi hay đã dùng đường dẫn JAR giải nén. Không nên coi kết quả thành công của chương trình tối giản là kiểm thử đầy đủ với legacy library.

### 8.1. Dùng cùng source để so sánh `bootRun` và `java -jar`

~~~bash
./gradlew bootRun
./gradlew clean bootJar
java -jar build/libs/unpack-demo-0.1.0.jar
~~~

Trong ví dụ cơ bản, cả hai kiểu chạy đều có dòng `APP_STARTED nested-ok`. Nhưng:

- `bootRun` chạy ứng dụng với main runtime classpath bên ngoài Boot archive.
- `java -jar` chạy sản phẩm có nested JAR và Boot Loader.
- Nếu thư viện cần file vật lý, sự khác biệt có thể chỉ bộc lộ khi `java -jar`.

**Không cố ý thêm một thư viện cũ vào production chỉ để làm ví dụ lỗi.** Cách học an toàn là hiểu cấu hình và sử dụng một dự án đã có vấn đề thật hoặc một integration test được tổ chức phê duyệt để tái hiện.

## 9. Kiểm tra pattern có khớp đúng dependency không

Đặt `requiresUnpack` đúng cú pháp **chưa đủ**. Phải bảo đảm:

1. Dependency đó nằm trong resolved runtime graph của **module ứng dụng**.
2. Spring Boot plugin thực sự đóng dependency vào executable JAR/WAR.
3. Pattern Gradle khớp **absolute path của source JAR** như Gradle đang thấy tại build time.
4. Runtime thực sự dùng executable Boot artifact mới được tạo và khởi chạy qua Boot Loader.

### 9.1. Xác định dependency trước

Trong project Gradle một module:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jruby-complete --configuration runtimeClasspath
~~~

Nếu đang dùng multi-project, chỉ định đúng project, ví dụ `:app:dependencies` và `:app:dependencyInsight` với các tham số tương ứng (tên `app` chỉ minh họa).

`dependencyInsight` cho thấy nguồn/phiên bản của dependency khi có trong configuration. Nếu module không dùng JRuby, lệnh có thể không tìm thấy match; đó không phải lỗi Boot Loader. Với Maven:

~~~bash
mvn dependency:tree
~~~

Nếu thư viện chỉ có trong test scope hoặc đã bị exclude, nó có thể không được đưa vào executable production archive; `requiresUnpack` không làm một dependency vắng mặt tự xuất hiện.

### 9.2. Xác nhận JAR có mặt trong output

Dùng đúng file executable sau build:

~~~bash
./gradlew clean bootJar
jar tf build/libs/unpack-demo-0.1.0.jar
~~~

Nếu dependency mẫu JRuby đã được khai báo và resolve, tìm entry tương tự:

~~~text
BOOT-INF/lib/jruby-complete-9.4.6.0.jar
~~~

**Lưu ý:** `jar tf` chỉ cho biết entry có trong archive. Nó không tự chứng minh entry đó đã được đánh dấu `requiresUnpack`, cũng không chứng minh Boot Loader sẽ tạo file tạm thành công ở runtime. Đừng coi “file nằm trong `BOOT-INF/lib`” là phép thử đầy đủ cho unpack.

Đối với Maven executable JAR, dùng `jar tf target/<artifact-thuc-te>.jar` sau khi xác định tên file. Nếu build output thực tế là executable WAR, thư viện có thể nằm ở `WEB-INF/lib` hoặc `WEB-INF/lib-provided` theo packaging, không phải `BOOT-INF/lib`.

### 9.3. Pattern Gradle khớp file nguồn, không khớp nội dung JAR

Ví dụ file đã resolve trong Gradle cache có đường dẫn tương tự:

~~~text
.../caches/modules-2/files-2.1/org.jruby/jruby-complete/9.4.6.0/.../jruby-complete-9.4.6.0.jar
~~~

Pattern:

~~~text
**/jruby-complete-*.jar
~~~

nhắm tới absolute path đó. `**/` đại diện cho phần directory phía trước và `*` đại diện cho version ở filename. Không dùng pattern `BOOT-INF/lib/jruby-complete-*.jar` chỉ vì archive output chứa entry ở vị trí đó; path được đối chiếu theo tài liệu là **source JAR file**, không phải path sau khi đóng gói.

Nếu artifact được đặt filename khác (classifier, repackaging, custom file dependencies), pattern cần điều chỉnh theo file thực tế. Ưu tiên kiểm chứng ở build log/diagnostic Gradle và phép thử runtime thay vì đoán tên từ tọa độ Maven.

## 10. Kiểm chứng ở runtime: bước quyết định

### 10.1. Thử đúng executable archive, đúng JVM

Với Gradle:

~~~bash
./gradlew clean bootJar
java -version
java -jar build/libs/unpack-demo-0.1.0.jar
~~~

Với Maven:

~~~bash
mvn clean package
java -version
java -jar target/<artifact-thuc-te>.jar
~~~

Trong các lệnh Maven, `<artifact-thuc-te>` là ký hiệu giải thích, phải thay bằng filename đã liệt kê; không gõ dấu ngoặc nhọn như một tên file thực.

Cần đối chiếu **cùng phiên bản JDK, hệ điều hành, cấu hình runtime và dependency versions** giữa các lần chạy. Nếu chỉ thay build configuration mà đồng thời đổi profile, port, JVM arguments, network hoặc thư viện, rất khó quy lỗi cho `requiresUnpack`.

### 10.2. Phân biệt ba mức bằng chứng

| Mức | Bằng chứng | Chưa chứng minh điều gì? |
| --- | --- | --- |
| A — Build | `bootJar`/`repackage` thành công | Chưa chắc app chạy; chưa chắc dependency cần unpack đã chọn đúng |
| B — Archive | Thư viện có mặt ở `BOOT-INF/lib`/`WEB-INF/lib` | Chưa đủ chứng minh thư viện được đánh dấu/runtime unpack |
| C — Runtime | App được khởi chạy **qua Boot Loader** và ca sử dụng thư viện vấn đề chạy thành công | Chưa tự chứng minh mọi trường hợp/OS/JVM đều hoạt động |

Với thư viện gặp vấn đề vì tự mở file JAR, phép thử có giá trị nhất là **thực hiện đúng thao tác thư viện từng bị lỗi** trong app đã đóng gói. Ví dụ chương trình chỉ in một dòng startup sẽ không bao phủ lỗi xảy ra khi library scan plugin ở request đầu tiên.

### 10.3. Thư mục tạm và môi trường container

Khi dependency được đánh dấu unpack, runtime cần có vị trí tạm để tạo file. Trong Java, cơ chế temp directory thường liên quan tới property `java.io.tmpdir`; Spring Boot Loader có chi tiết quản lý tên/path riêng theo phiên bản. **Không suy đoán** rằng file sẽ luôn xuất hiện ở một đường dẫn cố định như `/tmp/library.jar` hay tồn tại sau khi process kết thúc.

Ở container hoặc môi trường hạn chế:

- Kiểm tra vị trí temp directory được phép ghi, có dung lượng và inode đủ.
- Với read-only root filesystem, cần có writable temp mount theo chính sách deployment.
- Xác nhận UID/GID của process có quyền sử dụng temp location.
- Với các process khởi động song song, không dùng một tên temp cố định tự đặt gây xung đột.
- Tránh cấu hình global `chmod 777` hoặc tắt mọi giới hạn bảo mật chỉ để khắc phục lỗi ghi temp.
- Nếu dùng `-Djava.io.tmpdir=/path`, kiểm tra thư mục đó **đã tồn tại và có quyền ghi** theo runtime/JDK, đồng thời không biến nó thành storage lâu dài chứa secret.

Nếu lỗi runtime cho thấy `AccessDeniedException`/`No space left on device` khi loader phải unpack, hướng điều tra là temp storage/permissions, không phải đổi dependency version vô cớ.

### 10.4. Đường chạy khác có thể che lỗi

- `bootRun`: dependencies thường là file JAR độc lập trong Gradle cache; không kiểm tra đầy đủ nested loading.
- `spring-boot:run`: tương tự theo Maven runtime classpath.
- IDE Application run configuration: phụ thuộc IDE module/dependency classpath, không nhất thiết dùng Boot Loader.
- Exploded artifact: các libraries có thể đã được trích xuất ra ngoài, nên hành vi khác one-file Boot JAR.
- `java -cp ... DemoApplication`: gọi trực tiếp main class mà bỏ qua manifest/Boot launcher, không tương đương `java -jar executable.jar`.

**Kết luận QA:** muốn chứng minh bản phân phối hoạt động, chạy **bản phân phối cuối cùng** theo cùng kiểu startup sẽ dùng trên server.

## 11. Unpack trong executable WAR và phạm vi áp dụng

Spring Boot Gradle Plugin tạo `bootWar` khi có War plugin. Một executable WAR dùng loader phù hợp với layout WAR:

~~~text
app.war
├── WEB-INF/classes/
├── WEB-INF/lib/
│   └── dependency.jar
├── WEB-INF/lib-provided/
│   └── embedded-server-related.jar
└── org/springframework/boot/loader/
~~~

`requiresUnpack` được cấu hình trên **task tạo executable archive liên quan**. Với Gradle WAR, ví dụ:

**Groovy fragment:**

~~~groovy
tasks.named("bootWar") {
    requiresUnpack '**/jruby-complete-*.jar'
}
~~~

**Kotlin fragment (phải import `BootWar`):**

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootWar

tasks.named<BootWar>("bootWar") {
    requiresUnpack("**/jruby-complete-*.jar")
}
~~~

Đây là fragment cho module **đã có War plugin và Spring Boot plugin**, không phải câu lệnh có thể chạy trong một Java-only JAR project không có `bootWar`. Khi ứng dụng chỉ tạo executable JAR, cấu hình trên `bootJar` là đủ; **không cần** cấu hình thêm `bootWar` nếu task không tồn tại.

Nếu WAR được triển khai vào **servlet container bên ngoài**, container có thể có cơ chế unpack WAR và class loading riêng. Hành vi của container deploy không nhất thiết giống khởi chạy executable WAR qua `java -jar`. Chỉ kỳ vọng `requiresUnpack` phát huy đúng cơ chế Boot Loader khi sử dụng phương thức startup có Boot Loader; kiểm tra cả hai đường triển khai nếu dự án hỗ trợ cả hai.

Maven Spring Boot Plugin dùng `repackage` cho JAR/WAR và khai báo `requiresUnpack` theo dependency coordinates; không tạo một cấu hình riêng tên `bootWar` như Gradle.

## 12. Ví dụ trước–sau khi có lỗi thật

Giả sử dự án `payment-app` sử dụng thư viện `com.example:legacy-loader`. Khi chạy từ IDE, ứng dụng hoạt động. Sau khi đóng gói thành executable JAR, một chức năng cụ thể của thư viện báo không thể mở đường dẫn JAR do nó yêu cầu `java.io.File`.

**Trạng thái trước (mang tính minh họa):**

~~~text
IDE / Gradle bootRun: thư viện nhận path trên filesystem → chạy
java -jar app.jar: thư viện nhận nested JAR URL → xử lý nội bộ lỗi
~~~

Quy trình xử lý đúng:

1. Tái hiện lỗi bằng đúng executable JAR, lưu stack trace.
2. Kiểm tra phần code/thư viện tạo `File` từ JAR URL; xác nhận lỗi không phải do thiếu dependency.
3. Xác định chính xác resolved artifact tương ứng `com.example:legacy-loader`.
4. Tra tài liệu thư viện về nested JAR compatibility/unpacking, cân nhắc nâng version hoặc thay API nếu được.
5. Nếu cần, thêm **một** rule `requiresUnpack` nhắm chính thư viện đó.
6. Build sạch, chạy lại ca sử dụng đã lỗi với `java -jar`.
7. Kiểm tra môi trường chạy production có temp storage phù hợp.

**Ví dụ Gradle Groovy fragment có điều kiện:**

~~~groovy
tasks.named("bootJar") {
    requiresUnpack '**/legacy-loader-*.jar'
}
~~~

**Ví dụ Kotlin fragment có điều kiện:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    requiresUnpack("**/legacy-loader-*.jar")
}
~~~

**Ví dụ Maven plugin fragment có điều kiện:**

~~~xml
<configuration>
    <requiresUnpack>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>legacy-loader</artifactId>
        </dependency>
    </requiresUnpack>
</configuration>
~~~

Các tên `payment-app` và `legacy-loader` là **minh họa**, không khẳng định có dependency đó trên Maven Central. Những snippet này không thể build/runnable độc lập khi chưa có project và dependency tương ứng. Mục tiêu là biểu diễn quyết định cấu hình dựa trên bằng chứng.

**Sau khi sửa thành công**, kỳ vọng ca sử dụng thư viện vốn lỗi khi chạy từ Boot JAR sẽ hoạt động. Không khẳng định một message stdout cụ thể vì phụ thuộc thư viện và ứng dụng; phải định nghĩa test/assertion của dự án.

## 13. Trường hợp `requiresUnpack` không giải quyết được

Mặc dù hữu ích, unpack không phải “chế độ tương thích cho mọi thư viện”.

### 13.1. Library dùng system class loader

Spring Boot executable JAR sử dụng loader/classloader dành cho nested JAR. Một thư viện cố dùng `ClassLoader.getSystemClassLoader()` để tìm classes từ nested dependency có thể gặp hạn chế. Unpack một JAR không nhất thiết làm mọi class tự xuất hiện trong system class loader.

Hướng khắc phục thường là dùng `Thread.currentThread().getContextClassLoader()`/API tài nguyên phù hợp hoặc thay thế thư viện; nếu thư viện không hỗ trợ loader architecture của Boot, cần xem phương thức đóng gói/launch phù hợp. Đừng tự kết luận “ClassNotFound thì thêm requiresUnpack”.

### 13.2. Native library không phù hợp OS/architecture

Một dependency JAR có thể chứa `.so`, `.dll` hoặc `.dylib`. Java native loading cần file vật lý ở môi trường phù hợp, nhưng **unpack nguyên dependency JAR không bảo đảm native resource bên trong tự được extract/load đúng**. Native library có thể yêu cầu extraction logic riêng, architecture/ABI phù hợp và `java.library.path`/JNI setup đúng.

Bởi vậy phải đọc tài liệu native library tương ứng. Nếu lỗi là `UnsatisfiedLinkError` do CPU architecture khác hoặc binary thiếu, thay đổi `requiresUnpack` không khắc phục nguyên nhân.

### 13.3. Thư viện yêu cầu ghi vào JAR

File JAR đóng gói thường là artifact bất biến. Unpack ra temp không có nghĩa có thể ghi thay đổi vào JAR gốc hoặc những thay đổi sẽ được lưu bền vững. Nếu thư viện cần writable state, cung cấp thư mục dữ liệu riêng, có permission/storage phù hợp.

### 13.4. Duplicate classes hoặc version conflict

Nếu ứng dụng có hai version thư viện trên runtime classpath, thứ tự classpath/version conflict có thể gây linkage error hoặc behavior sai. `requiresUnpack` không thay đổi dependency resolution, không giải quyết `NoSuchMethodError` do API version mismatched. Cần xem `dependencyInsight`/`dependency:tree`, BOM và exclusions.

### 13.5. Sai layout executable JAR

Nếu tự nén lại Boot archive khiến `BOOT-INF` bị sai vị trí, manifest có launcher sai, ZIP entry compression không phù hợp hoặc signature/metadata hỏng, vấn đề là **packaging**. Dùng Spring Boot Gradle/Maven Plugin đúng version để build, không áp dụng unpack như thuốc chữa chung.

## 14. Troubleshooting thực hành

| Biểu hiện | Kiểm tra đầu tiên | Hành động phù hợp |
| --- | --- | --- |
| `bootRun` ổn, `java -jar` lỗi ở một JAR parser riêng | Xem stack trace, thư viện có tự mở JAR bằng File/Path không | Nếu đúng, `requiresUnpack` đúng một dependency và retest |
| `requiresUnpack` không có tác dụng | Pattern không khớp source path hoặc cấu hình sai task/module | Kiểm tra runtimeClasspath, `bootJar`/`bootWar` và task configuration |
| JAR cuối không có dependency cần unpack | Dependency bị exclude, sai scope hoặc không resolve | Sửa dependency graph; unpack không đưa library trở lại |
| `Task 'bootJar' not found` | Java + Spring Boot plugin chưa áp dụng tại module | Xem `plugins`, `./gradlew tasks --all`, project path |
| `Task 'bootWar' not found` | Chưa áp dụng War plugin | Chỉ dùng cấu hình bootWar nếu dự án thực sự tạo WAR |
| Maven `package` không chạy `repackage` | Thiếu plugin execution khi không dùng starter parent | Xem effective POM và plugin executions |
| Một pattern chọn quá nhiều JAR | `**/*.jar` hoặc matcher quá rộng | Thu hẹp theo filename/version; kiểm thử lại |
| Runtime gặp `AccessDeniedException` ở temp | Temp volume read-only, permission, UID/GID không phù hợp | Cấp writable temp mount/path chính xác và giữ nguyên chính sách bảo mật |
| Runtime gặp `No space left on device` | Temp filesystem/inodes thiếu | Điều chỉnh temp storage/quota sau khi đo nhu cầu |
| `ClassNotFoundException` hoặc `NoSuchMethodError` | Có thể dependency vắng mặt hoặc version conflict | Kiểm tra `BOOT-INF/lib`, dependency tree, classpath và version |
| `UnsatisfiedLinkError` với native binary | Native resource, OS/ABI, library path | Tra hướng dẫn native loading; unpack JAR không bảo đảm sửa |
| IDE chạy, container không chạy | Khác classpath, JVM, temp filesystem, profile, OS | Tái hiện bằng exact Boot artifact trong container gần production |
| `jar tf` nhìn thấy JAR nhưng chức năng vẫn lỗi | Inclusion khác runtime unpack/cách library sử dụng | Chạy path gây lỗi; xác nhận plugin rule và temp access |
| Trích xuất cả JAR bằng jarmode mà app chạy | Exploded startup khác one-file nested startup | Dùng đúng cách đóng gói/runtime mục tiêu để xác minh |
| Có `requiresUnpack` nhưng không dùng thư viện đó | Rule dư thừa hoặc “cargo cult” | Xóa rule nếu test chứng minh không cần, tránh I/O/temp file vô nghĩa |

### 14.1. Quy trình điều tra gọn nhưng đủ bằng chứng

**Bước A — Xác định đúng artifact:** file nào là executable từ `bootJar`/`repackage`, ở module nào, với version nào? Không chọn file `-plain.jar` rồi trông đợi Boot Loader.

**Bước B — Xác định lỗi:** có stack trace thuộc API của thư viện hay không; thông điệp nhắc đường dẫn `jar:nested:`, `File`, `ZipFile` hay `JarFile` như thế nào? Không cần phỏng đoán từ triệu chứng chung.

**Bước C — Xác định dependency:** trong Gradle xem `runtimeClasspath`; trong Maven xem `dependency:tree`. Nếu dependency không có, xử lý resolution/scope trước.

**Bước D — Chọn cấu hình nhỏ nhất:** Gradle pattern chỉ chọn artifact JAR thật; Maven group/artifact chính xác. Nếu dependency là source khác hoặc file dependency local, xem path matcher theo file thực.

**Bước E — Build sạch và chạy bản phát hành:** chạy lại **ca lỗi cụ thể** bằng `java -jar` trong môi trường có temp writable.

**Bước F — Ghi lại lý do:** trong build script hoặc tài liệu kỹ thuật, ghi ngắn vì sao dependency phải unpack và liên kết issue/version. Điều này giúp khi nâng thư viện, team biết rule còn cần hay không.

## 15. Đối chiếu một số tùy chọn gần chủ đề

### 15.1. `bootJar` và `bootWar` là task packaging, không phải startup

Gradle `bootJar` và `bootWar` ghi marker/config vào executable archive. Việc thực thi unpack xảy ra khi ứng dụng launch bằng Boot Loader; vì vậy `./gradlew bootJar` thành công không đồng nghĩa runtime có permission để unpack.

### 15.2. Maven `repackage` và `spring-boot:run` là hai cơ chế khác

`spring-boot:repackage` tạo executable artifact; `spring-boot:run` chạy ứng dụng development với Maven runtime classpath. Nếu lỗi chỉ xuất hiện sau repackage, cần chạy `java -jar` để kiểm tra. Thêm `requiresUnpack` trên Maven packaging plugin không có nghĩa `spring-boot:run` phải tạo file tạm giống hệt Boot Loader.

### 15.3. `java -Djarmode=tools -jar app.jar extract` là unpack khác

Spring Boot 3.3 hỗ trợ trích xuất executable JAR để phục vụ một số mô hình triển khai/caching và startup. Ví dụ tài liệu:

~~~bash
java -Djarmode=tools -jar my-app.jar extract
~~~

Lệnh trên hướng tới **trích xuất ứng dụng** (theo layout mà Boot tools hỗ trợ). Nó khác yêu cầu “chỉ unpack `jruby-complete` ở runtime trong one-file executable JAR”. Nếu chọn mô hình exploded deployment, phải kiểm tra quy trình publish và startup phù hợp; không mặc định đồng nhất với `requiresUnpack`.

### 15.4. Mối liên hệ với container image

Với OCI container, Spring Boot JAR có thể được chạy trực tiếp hoặc trích xuất thành layers/files tùy cách build image. Nếu startup qua Boot Loader và dependency được đánh dấu unpack, container phải có temp filesystem writable. Nếu runtime sử dụng exploded classpath, hành vi filesystem có thể khác. Vì thế test cần sát cách production thực tế chạy.

Đừng thay đổi Docker image layer caching, disable `layers.idx` hoặc tắt bảo mật container chỉ để xử lý một thư viện không hỗ trợ nested JAR; trước hết xác định nguyên nhân và chọn ngoại lệ nhỏ nhất.

## 16. Thực hành: từ dependency tới cấu hình unpack

### Bài 1 — Đọc cấu trúc executable JAR

Dùng bản Gradle ở mục 5 hoặc 6 với mã Java ở mục 8:

~~~bash
./gradlew clean bootJar
jar tf build/libs/unpack-demo-0.1.0.jar
java -jar build/libs/unpack-demo-0.1.0.jar
~~~

**Yêu cầu:** xác định `BOOT-INF/classes` và `BOOT-INF/lib`. Ứng dụng in `APP_STARTED nested-ok` trong stdout (cùng các dòng log Spring Boot).

**Đáp án:** vì không có thư viện đặc biệt, đây là ví dụ không cần `requiresUnpack`; Boot Loader tải các nested JAR theo cơ chế mặc định.

### Bài 2 — Nhận diện pattern đúng

Giả sử Gradle resolve dependency có đường dẫn:

~~~text
.../org.jruby/jruby-complete/9.4.6.0/.../jruby-complete-9.4.6.0.jar
~~~

Chọn trong hai pattern:

~~~text
A. BOOT-INF/lib/jruby-complete-*.jar
B. **/jruby-complete-*.jar
~~~

**Đáp án:** B. Theo Spring Boot Gradle Plugin 3.3, `requiresUnpack` dùng Ant pattern khớp absolute source JAR path. A là path bên trong output archive, không phải chuẩn matcher được tài liệu mô tả.

### Bài 3 — Viết cấu hình Kotlin DSL

**Yêu cầu:** chọn `jruby-complete` cho task `bootJar`.

**Đáp án:**

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    requiresUnpack("**/jruby-complete-*.jar")
}
~~~

Đây là fragment; cần plugin Gradle đã được áp dụng và dependency thật có trong runtimeClasspath.

### Bài 4 — Viết cấu hình Maven

**Yêu cầu:** chọn `org.jruby:jruby-complete` khi Maven `repackage`.

**Đáp án:**

~~~xml
<configuration>
    <requiresUnpack>
        <dependency>
            <groupId>org.jruby</groupId>
            <artifactId>jruby-complete</artifactId>
        </dependency>
    </requiresUnpack>
</configuration>
~~~

Đoạn này thuộc phần `spring-boot-maven-plugin` của POM, không phải phần `dependencies` chính. Vẫn cần dependency được khai báo/resolve và goal repackage được cấu hình thực thi.

### Bài 5 — Vì sao `jar tf` chưa đủ?

**Câu hỏi:** `jar tf app.jar` thấy `BOOT-INF/lib/jruby-complete-9.4.6.0.jar`. Điều đó có chứng minh `requiresUnpack` đúng và chạy thành công không?

**Đáp án:** chưa. Nó chỉ cho thấy dependency được chứa trong archive. Cần kiểm tra rule packaging và khởi chạy bằng Boot Loader trong môi trường phù hợp, đồng thời thực hiện ca sử dụng JRuby vốn cần file vật lý.

### Bài 6 — Chẩn đoán permission

**Tình huống:** ứng dụng chạy từ IDE, JAR đã đánh dấu unpack nhưng container production báo không thể tạo file tạm.

**Đáp án:** kiểm tra writable temp path, UID/GID, disk/inode quota và các volume mounts. Nếu `java.io.tmpdir` được điều chỉnh, xác nhận thư mục tồn tại và writable. Không xóa rule hoặc cấp permission quá rộng khi chưa xác nhận nguyên nhân.

### Bài 7 — Phân biệt fix đúng vấn đề

**Câu hỏi:** `NoSuchMethodError` do `library-a` được resolve phiên bản quá cũ; có nên bật `requiresUnpack` cho `library-a`?

**Đáp án:** không. `NoSuchMethodError` do binary incompatibility/version conflict cần xử lý dependency versions và resolution. Unpack không thay API của class.

## 17. Checklist ra quyết định

Trước khi merge cấu hình `requiresUnpack`, kiểm tra:

- [ ] Có stack trace/tài liệu chứng minh **đúng dependency cần file JAR vật lý**.
- [ ] Đã phân biệt nested-JAR limitation với thiếu dependency, sai main class, profile, Java version và native ABI.
- [ ] Đã xem lựa chọn sửa thư viện/nâng version hoặc sử dụng API classpath-friendly; không vội thêm workaround nếu upstream đã sửa.
- [ ] Dependency nằm trong runtime graph của **đúng module ứng dụng**.
- [ ] Với Gradle, pattern đủ hẹp và khớp **absolute source JAR path**.
- [ ] Với Maven, `requiresUnpack` chứa đúng `groupId`/`artifactId` trong `spring-boot-maven-plugin`.
- [ ] `bootJar`/`bootWar` hoặc `repackage` thật sự chạy và tạo executable artifact.
- [ ] `jar tf`/manifest xác nhận sản phẩm phù hợp, nhưng không dừng ở kiểm tra inclusion.
- [ ] Đã thử `java -jar` trên chính archive mới tạo, thực hiện ca sử dụng thư viện và xác nhận lỗi biến mất.
- [ ] Môi trường container/server có temp filesystem writable và dung lượng/quota hợp lý.
- [ ] Không vô tình unpack toàn bộ runtime dependencies, làm lộ secrets vào temp hoặc dựa vào temp file name cố định.
- [ ] Có test hồi quy và ghi chú ngắn vì sao rule tồn tại để lần nâng thư viện sau có thể đánh giá lại.

**Kết luận:** Với Spring Boot Loader, **mặc định là giữ và đọc nested JAR trực tiếp**. Chỉ dùng `requiresUnpack` khi có một **ngoại lệ thực sự cần file JAR trên filesystem ở runtime**, cấu hình chính xác dependency đó, rồi kiểm tra bằng executable artifact cuối trong môi trường gần production.

## 18. Tài liệu tham khảo chính thức

- Spring Boot 3.3.13 Gradle Plugin — Packaging Executable Archives, **Configuring Libraries that Require Unpacking**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3.13 Maven Plugin — Packaging Executable Archives, goal `repackage` và tham số `requiresUnpack`: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Executable Jar Format / Nested JARs: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/nested-jars.html
- Spring Boot 3.3 — Spring Boot Loader and NestedJarFile: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/jarfile-class.html
- Spring Boot 3.3 — Executable Jar Restrictions: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/restrictions.html
- Spring Boot 3.3 — Packaging Efficient Deployments / unpacking executable JAR: https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html
- Gradle Java Plugin và Java source sets: https://docs.gradle.org/current/userguide/java_plugin.html

Hãy đối chiếu tài liệu đúng phiên bản plugin/loader đang dùng: đường dẫn package launcher, API cấu hình và tính năng unpack có thể thay đổi giữa các dòng Spring Boot. **Không coi requiresUnpack là mặc định tốt hơn; đó là ngoại lệ có chủ đích cho một thư viện cụ thể.**
