# Đọc thay đổi cấu hình plugin, task, goal và giá trị mặc định

## 1. Vì sao nâng version công cụ có thể làm build đổi hành vi?

Khi nâng Maven plugin, Gradle plugin hoặc Spring Boot build plugin, thay đổi không chỉ nằm ở số version. Plugin mới có thể:

- Thêm, bỏ hoặc đổi tên goal/task.
- Đổi phase mà goal được gắn vào hoặc thay đổi task dependency.
- Thêm, bỏ, đổi kiểu hoặc đổi tên tham số cấu hình.
- Đổi giá trị mặc định của một tham số.
- Đổi cách suy luận giá trị từ project, source set, toolchain hoặc environment.
- Đổi vị trí/tên artifact, manifest, classifier, archive layout hoặc output directory.
- Đổi điều kiện skip, incremental build, caching, validation hoặc cách báo lỗi.
- Ngừng hỗ trợ một version Maven/Gradle/JDK hoặc một cấu hình cũ.

Một build vẫn có thể **BUILD SUCCESS** sau khi nâng plugin nhưng tạo artifact khác trước. Ví dụ, task vẫn chạy nhưng archive classifier thay đổi; goal vẫn được gọi nhưng tham số mặc định đổi; main class trước đây được tự tìm thấy nhưng sau nâng plugin không còn được suy luận như cũ.

Khi review thay đổi công cụ, cần trả lời bốn câu hỏi:

1. **Plugin version nào đang được resolve?**
2. **Goal/task nào được đăng ký và thực sự chạy?**
3. **Cấu hình nào đến từ POM/build script, parent, settings, version catalog hoặc command line?**
4. **Giá trị nào được plugin/task tự cung cấp khi project không cấu hình rõ?**

Bài này tập trung vào Maven, Gradle và Spring Boot 3.5.x, với ví dụ Java 17. Version trong ví dụ chỉ để minh họa; hãy đọc tài liệu đúng version đang dùng thay vì lấy default từ tài liệu phiên bản mới nhất.

## 2. Phân biệt plugin, goal, task, phase và default

| Khái niệm | Maven | Gradle | Ý nghĩa |
|---|---|---|---|
| **Build tool** | Maven | Gradle | Chương trình điều phối build và dependency |
| **Plugin** | Maven plugin | Gradle plugin | Mở rộng build tool, thêm goal/task và cấu hình |
| **Goal** | Goal/Mojo của Maven plugin | Không có khái niệm tương đương trực tiếp | Đơn vị chức năng của Maven plugin, ví dụ repackage |
| **Task** | Maven lifecycle thực thi goal theo phase | Task của Gradle | Đơn vị công việc trong task graph, ví dụ bootJar |
| **Phase** | compile, test, package, verify | Không có chuỗi phase Maven tương đương | Mốc trong Maven lifecycle để gắn goal |
| **Task dependency** | Quan hệ phase/execution và reactor | Quan hệ dependsOn và task graph | Xác định việc nào cần chạy trước |
| **Configuration** | XML configuration trong POM | DSL, extension và task properties | Giá trị người dùng cung cấp cho plugin/task |
| **Default/convention** | Giá trị mặc định của tham số Mojo | Giá trị convention/provider của task hoặc extension | Giá trị dùng khi project không ghi đè |

### 2.1. Maven plugin goal không phải Maven phase

Một Maven plugin có thể cung cấp nhiều goal. Ví dụ Spring Boot Maven Plugin cung cấp goal **repackage**. Goal đó có thể được bind vào phase **package** bằng execution:

```xml
<execution>
    <id>repackage-executable-archive</id>
    <phase>package</phase>
    <goals>
        <goal>repackage</goal>
    </goals>
</execution>
```

Khi chạy **mvn package**, Maven đi qua lifecycle và gọi các goal đã được bind vào phase tương ứng. Khi gọi một goal trực tiếp, chẳng hạn **mvn spring-boot:repackage**, bạn đang yêu cầu goal chạy trực tiếp; đừng giả định mọi phase trước đó tự động chạy giống **mvn package**.

### 2.2. Gradle task là một node trong task graph

Gradle plugin có thể đăng ký task như **bootJar**, **bootWar**, **bootRun**. Task có:

- **Type:** lớp triển khai task, ví dụ BootJar.
- **Inputs:** source, classpath, cấu hình và file đầu vào.
- **Outputs:** archive, report hoặc file được tạo.
- **Dependencies:** task phải hoàn tất trước nó.
- **Properties:** các giá trị cấu hình như main class, archive name hoặc classpath.

Khi chạy **./gradlew bootJar**, Gradle cấu hình project, tạo task graph và thực thi task cần thiết. Task graph có thể thay đổi theo plugin, project và configuration.

### 2.3. Default và convention không phải lúc nào cũng hiện trong file build

Nếu POM không khai báo mainClass, Spring Boot Maven Plugin có thể tự phát hiện main class theo quy tắc của plugin. Nếu Gradle build không set main class cho bootRun, Spring Boot Gradle Plugin có thể tự tìm class có phương thức public static void main(String[]) trong main source set.

Đây là **giá trị được suy luận/default từ plugin**. Việc POM hoặc build.gradle không có dòng cấu hình không có nghĩa giá trị đang là null, rỗng hoặc không được thiết lập.

> **Cấu hình hiệu lực** cho biết build đã nhận cấu hình nào; **descriptor/tài liệu plugin** cho biết plugin có tham số nào và default được định nghĩa ra sao; **log hoặc giá trị task đã resolve** cho biết lần build cụ thể thực sự dùng gì.

## 3. Có nhiều lớp cấu hình cùng tác động đến một plugin

Trước khi so sánh hai version, hãy tìm nơi version và cấu hình được khai báo. Nếu chỉ nhìn file pom.xml hoặc build.gradle của module hiện tại, bạn có thể bỏ sót cấu hình kế thừa.

### 3.1. Maven: nơi plugin version và configuration được khai báo

Các nguồn phổ biến:

1. POM của module: build/plugins.
2. POM cha: cấu hình plugin được kế thừa.
3. pluginManagement: quản lý version/configuration mặc định cho plugin khi plugin được khai báo sử dụng.
4. Super POM và lifecycle mapping: các plugin/goal mặc định gắn với packaging type như jar hoặc war.
5. Active profiles: profile có thể thêm plugin hoặc ghi đè cấu hình.
6. Command line: tham số -Dproperty=value có thể ghi đè nếu plugin công bố user property tương ứng.

Ví dụ:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.5.16</version>
                <configuration>
                    <mainClass>com.example.demo.DemoApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>

    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Trong ví dụ, pluginManagement cung cấp version và configuration được quản lý; phần plugins khai báo plugin được sử dụng trong build. **Chỉ đặt plugin trong pluginManagement không có nghĩa plugin tự động được thực thi.**

Nếu dùng spring-boot-starter-parent, parent đã cung cấp nhiều cấu hình/plugin management và execution tiện ích. Nếu chỉ import spring-boot-dependencies BOM trong dependencyManagement, bạn đang quản lý dependency versions; BOM không tự làm nhiệm vụ của Spring Boot parent đối với toàn bộ plugin executions.

### 3.2. Maven: cấu hình ở plugin level và execution level

Cấu hình ở plugin level có thể áp dụng cho các goal của plugin; cấu hình ở execution level có thể tinh chỉnh riêng cho một execution.

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.demo.DemoApplication</mainClass>
    </configuration>
    <executions>
        <execution>
            <id>repackage-executable-jar</id>
            <phase>package</phase>
            <goals>
                <goal>repackage</goal>
            </goals>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Trong ví dụ, mainClass được khai báo ở plugin level; classifier thuộc execution repackage. Khi nâng plugin, hãy xem tham số có còn tồn tại, kiểu dữ liệu có thay đổi và quy tắc merge/inheritance có đổi không.

Một số cấu hình Maven hỗ trợ thuộc tính merge nâng cao như combine.children và combine.self. Chỉ dùng chúng khi thực sự cần kiểm soát việc merge giữa parent/child; trước tiên hãy xem effective POM để hiểu kết quả.

### 3.3. Gradle: plugin version có thể nằm ở nhiều file

Các nguồn phổ biến:

- plugins block trong build.gradle hoặc build.gradle.kts.
- pluginManagement block trong settings.gradle(.kts).
- Plugin alias và version trong gradle/libs.versions.toml.
- buildscript classpath trong các build cũ.
- Convention plugin trong buildSrc hoặc included build.

Ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}
```

Ví dụ Kotlin DSL:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}
```

Ví dụ version catalog:

```toml
[versions]
springBoot = "3.5.16"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "springBoot" }
```

Sau đó module có thể dùng alias thay vì ghi version trực tiếp. Khi review nâng version, cần đọc cả settings.gradle(.kts) và version catalog, không chỉ build script của module.

### 3.4. Gradle: extension và task property có vai trò khác nhau

Plugin thường cung cấp **extension** để cấu hình chung cho project và **task properties** để cấu hình một task cụ thể.

Ví dụ Spring Boot DSL:

```groovy
springBoot {
    mainClass = 'com.example.demo.DemoApplication'
}
```

Cấu hình trực tiếp task:

```groovy
tasks.named('bootJar') {
    mainClass = 'com.example.demo.DemoApplication'
}
```

Cấu hình extension có thể là nguồn convention cho task; cấu hình trực tiếp task có thể ghi đè giá trị đó. Khi nâng plugin, hãy xem tài liệu version mới về cách extension truyền giá trị sang task và property nào đã bị deprecated.

## 4. Giá trị mặc định trong Maven: dùng help:describe

Maven Help Plugin là công cụ quan trọng để đọc goal và tham số của một plugin cụ thể.

### 4.1. Xem danh sách goal và thông tin plugin

Ví dụ với Spring Boot Maven Plugin 3.5.16:

```bash
mvn help:describe \
  -Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.16 \
  -Ddetail
```

Lệnh này hiển thị các goal của plugin, thông tin triển khai và các tham số mà goal hỗ trợ. Để xem riêng goal repackage:

```bash
mvn help:describe \
  -Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.16 \
  -Dgoal=repackage \
  -Ddetail
```

Đọc các trường:

- **Parameter:** tên tham số.
- **Type:** kiểu dữ liệu.
- **Required:** có bắt buộc hay không.
- **User Property:** property có thể truyền qua -D.
- **Default:** giá trị mặc định được plugin mô tả.
- **Description:** ý nghĩa và giới hạn của tham số.

Ví dụ minh họa một phần output của một Mojo bất kỳ:

```text
Parameter: skip
Type: boolean
Required: No
User Property: example.skip
Default: false

Parameter: outputDirectory
Type: File
Required: No
Default: expression referring to the Maven project build directory
```

Đây là output minh họa để giải thích cách đọc, không khẳng định các giá trị trên là default của mọi goal hoặc mọi version Spring Boot. Hãy lấy output từ đúng plugin/version mà project resolve.

### 4.2. Default có thể là literal hoặc expression

Plugin descriptor có thể định nghĩa:

- Literal: false, true, một số, chuỗi hoặc enum.
- Expression: tham chiếu project/session, ví dụ project build directory.
- Giá trị do code plugin tính ở runtime.
- Giá trị do một component khác truyền vào.

Do đó, khi output hiển thị expression, cần hiểu nó sẽ được resolve trong context nào. Đừng copy expression thành một đường dẫn literal hoặc kết luận giá trị cuối chỉ từ chuỗi descriptor.

### 4.3. Không nhầm default của Help Plugin với default của plugin đang khảo sát

Lệnh help:describe có hai plugin liên quan:

- maven-help-plugin: plugin đang thực hiện goal help:describe.
- Plugin được truyền trong -Dplugin=...: plugin mà bạn muốn khảo sát.

Version của plugin Help và version của plugin Spring Boot là hai thứ khác nhau. Để kết quả so sánh đáng tin, chỉ rõ version plugin đích trong -Dplugin=groupId:artifactId:version.

## 5. Maven: xem cấu hình hiệu lực bằng effective POM

### 5.1. Effective POM gồm những gì?

POM hiệu lực là kết quả Maven tính sau khi áp dụng:

- POM hiện tại.
- Parent POM và inheritance.
- Properties/interpolation.
- Active profiles.
- Dependency management và plugin management.
- Cấu hình build đã merge.

Tạo file:

```bash
mvn help:effective-pom \
  -Dverbose \
  -Doutput=target/effective-pom.xml
```

-Dverbose yêu cầu Help Plugin thêm comment nguồn gốc của từng phần tử XML khi có thông tin. Điều này giúp nhận biết cấu hình đến từ POM module, parent hoặc profile nào.

Xem profile đang active:

```bash
mvn help:active-profiles
```

Xem các profile có sẵn:

```bash
mvn help:all-profiles
```

### 5.2. Effective POM không chứa mọi default được plugin tự tiêm

Đây là điểm rất dễ nhầm.

**Effective POM cho biết cấu hình Maven đã merge**, ví dụ plugin version, execution, phase và các node trong configuration. Nó không nhất thiết liệt kê toàn bộ giá trị default mà plugin sẽ đưa vào Mojo khi thực thi.

Ví dụ:

- Effective POM có thể không chứa mainClass.
- Plugin descriptor có thể mô tả tham số mainClass không bắt buộc.
- Khi chạy, Spring Boot plugin có thể tự phát hiện main class từ compiled output.

Ba thông tin đó không mâu thuẫn. Chúng thuộc ba lớp khác nhau: cấu hình khai báo, metadata/default của plugin và giá trị thực tế được resolve lúc chạy.

Để hiểu đầy đủ, kết hợp:

1. Effective POM.
2. help:describe của đúng plugin/version.
3. Tài liệu plugin và migration notes của version đó.
4. Build log và artifact sau khi thực thi.

### 5.3. Xem plugin/goal gắn với lifecycle phase nào

Dùng Help Plugin để xem lifecycle mapping:

```bash
mvn help:describe -Dcmd=package
mvn help:describe -Dcmd=verify
```

Kết quả giúp nhận biết các goal được gắn vào phase theo packaging type. Nếu project có execution tùy chỉnh, đối chiếu thêm effective POM và build log vì một phase có thể chạy nhiều goal.

### 5.4. Đọc cấu hình thực tế trong debug log

Khi cần xác nhận Maven truyền gì cho Mojo, dùng debug log:

```bash
mvn -X -Dstyle.color=never package
```

Tìm tên plugin/goal, execution id và phần configuration/mojo execution. Debug log có thể chứa URL nội bộ, property, đường dẫn và credential; hãy bảo vệ log và che thông tin nhạy cảm trước khi chia sẻ.

**Không dựa duy nhất vào debug log:** một số giá trị được tính bên trong code plugin hoặc chỉ hiện trong output archive. Hãy kiểm tra artifact cuối để xác nhận hành vi.

## 6. Maven: hiểu user property, POM configuration và execution

Một plugin parameter có thể nhận giá trị từ nhiều nguồn. Quy tắc chính xác phụ thuộc cách plugin khai báo parameter, user property và Maven model.

### 6.1. Tìm đúng User Property

Nếu help:describe hiển thị:

```text
User Property: example.skip
Default: false
```

Bạn có thể thử override bằng:

```bash
mvn package -Dexample.skip=true
```

Đây là ví dụ generic. Chỉ dùng property được plugin thực sự công bố. Không tự đoán tên property; hãy đọc descriptor/tài liệu đúng version.

### 6.2. Tách cấu hình theo execution id

Một plugin có thể được gọi nhiều lần với execution id khác nhau. Ví dụ:

```xml
<executions>
    <execution>
        <id>repackage-service-jar</id>
        <phase>package</phase>
        <goals>
            <goal>repackage</goal>
        </goals>
        <configuration>
            <classifier>exec</classifier>
        </configuration>
    </execution>
</executions>
```

Khi log cho thấy goal chạy nhiều lần, hãy đọc execution id để biết cấu hình nào được áp dụng. Không chỉ tìm tên goal repackage, vì cùng một goal có thể xuất hiện trong execution khác hoặc được gọi trực tiếp.

### 6.3. Phân biệt cấu hình plugin với dependency version

Maven có hai khu vực dễ nhầm:

- dependencyManagement quản lý dependency versions.
- pluginManagement quản lý plugin versions và plugin configuration.

Nâng Spring Boot dependency BOM không nhất thiết nâng Maven plugin. Nâng spring-boot-maven-plugin cũng không tự động thay toàn bộ dependency versions trong ứng dụng.

Khi nâng Spring Boot, hãy xem cả parent/BOM, plugin version và Java baseline. Nếu dùng parent, các version thường được căn chỉnh theo release; nếu tách parent và BOM, phải quản lý plugin riêng.

## 7. Spring Boot Maven Plugin: kiểm tra thay đổi repackage

### 7.1. Goal repackage làm gì?

Goal repackage lấy archive do Maven package tạo và chuyển nó thành executable archive phù hợp với Spring Boot Loader. Với executable JAR, cấu trúc thường chứa:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/...
BOOT-INF/lib/...
```

Manifest có thông tin launcher và application entry point. Với executable WAR, layout dùng WEB-INF theo quy tắc của Spring Boot.

### 7.2. Các cấu hình nên so sánh khi nâng plugin

| Tham số/khía cạnh | Câu hỏi khi nâng version |
|---|---|
| mainClass | Cách tự phát hiện main class có thay đổi không? Có cần khai báo tường minh? |
| classifier | Artifact executable có còn ghi đè artifact chính hay tạo artifact riêng? |
| attach | Archive repackaged có được attach vào project/deployment không? |
| layout | Kiểu archive có còn được suy luận phù hợp với packaging không? |
| includes / excludes | Bộ dependency được đưa vào archive có thay đổi không? |
| layers | Layer index và cách nhóm dependency có thay đổi không? |
| outputDirectory / outputFilename | Vị trí và tên archive có thay đổi không? |
| skip | Có điều kiện nào làm repackage bị bỏ qua? |
| requiresUnpack | Dependency nào cần được giải nén khi chạy? |

Tên tham số, kiểu, default và hỗ trợ theo version phải được xác nhận bằng help:describe cùng tài liệu version cụ thể. Bảng này là checklist review, không khẳng định mọi tham số đều thay đổi ở mỗi lần nâng.

### 7.3. Kiểm tra main class và artifact sau repackage

Nếu plugin không được cấu hình main class, nó có thể cố gắng phát hiện main class từ compiled classes. Khi có nhiều class phù hợp hoặc không tìm thấy class, repackage có thể thất bại hoặc tạo kết quả không như mong đợi.

Có thể cấu hình rõ:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.demo.DemoApplication</mainClass>
    </configuration>
</plugin>
```

Sau build, kiểm tra:

```bash
jar tf target/demo-1.0.0.jar
unzip -p target/demo-1.0.0.jar META-INF/MANIFEST.MF
```

Nếu môi trường không có unzip, dùng lệnh jar để trích manifest:

```bash
mkdir -p target/manifest-check
cd target/manifest-check
jar xf ../demo-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
```

Đọc Main-Class và Start-Class nếu có. Đối chiếu tên file, classifier và BOOT-INF/lib để chắc chắn bạn đang xem đúng artifact executable.

## 8. Gradle: xem plugin version, task và task graph

### 8.1. Kiểm tra Gradle Wrapper trước

Gradle Wrapper cố định version Gradle của project, độc lập với version Spring Boot Gradle Plugin.

Kiểm tra:

```bash
./gradlew --version
```

Đọc file:

```text
gradle/wrapper/gradle-wrapper.properties
```

Ví dụ cấu hình wrapper:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
```

Version ở đây chỉ là ví dụ. Plugin version và Gradle Wrapper version phải nằm trong dải tương thích của Spring Boot Gradle Plugin đang dùng.

### 8.2. Tìm nơi khai báo plugin version

Kiểm tra theo thứ tự:

1. settings.gradle hoặc settings.gradle.kts và block pluginManagement.
2. gradle/libs.versions.toml nếu dùng plugin alias.
3. build.gradle hoặc build.gradle.kts của root/module.
4. buildSrc hoặc included build nếu dùng convention plugin.
5. buildscript nếu dự án dùng cơ chế plugin cũ.

Lệnh:

```bash
./gradlew tasks --all
./gradlew help --task bootJar
./gradlew help --task bootRun
```

- tasks --all liệt kê task có thể gọi, kể cả task không nằm trong group mặc định.
- help --task mô tả task, path, group và cách dùng.
- Những lệnh này giúp nhận diện task do plugin đăng ký; chúng không nhất thiết in toàn bộ property/default đã resolve.

### 8.3. Xem task graph mà không chạy task actions

```bash
./gradlew bootJar --dry-run
./gradlew build --dry-run
```

--dry-run cấu hình build và in những task sẽ được chạy nhưng không thực thi task actions. Dùng để so sánh task graph trước và sau khi nâng plugin.

Ví dụ một plugin version mới có thể thêm task hoặc thay đổi dependency giữa task. Nếu chỉ nhìn BUILD SUCCESS, bạn có thể bỏ qua thay đổi này. So sánh danh sách task với baseline trước khi kết luận upgrade không ảnh hưởng build flow.

### 8.4. Không nhầm buildEnvironment với toàn bộ plugin DSL

```bash
./gradlew buildEnvironment
```

Lệnh này hữu ích để xem buildscript classpath trong các build dùng cơ chế buildscript. Với plugin khai báo qua plugins block và pluginManagement, version có thể được resolve theo cơ chế plugin marker; buildEnvironment không phải lúc nào cũng là bản kê đầy đủ mọi plugin DSL. Hãy đọc đúng nơi khai báo version.

## 9. Gradle: hiểu default, convention và explicit value

Gradle sử dụng Property, Provider và convention để cấu hình task theo hướng lazy.

### 9.1. Convention là giá trị dùng khi chưa có explicit value

Ví dụ generic:

```kotlin
val outputLabel = objects.property(String::class)

outputLabel.convention("default-name")
println(outputLabel.get())

outputLabel.set("custom-name")
println(outputLabel.get())
```

Khi chưa gọi set, property lấy giá trị từ convention. Khi có explicit value, convention không còn là giá trị cuối.

Điều này giải thích tại sao:

- Build script không ghi một property nhưng task vẫn có giá trị.
- Plugin mới đổi convention và output thay đổi dù build script không sửa.
- Một extension cung cấp convention cho task.
- Một provider lấy giá trị từ project hoặc file khác và chỉ được resolve khi task cần.

### 9.2. Thứ tự đọc giá trị task

Khi cần xác định một property thực tế, hãy lần theo:

1. Giá trị được set trực tiếp trong task configuration.
2. Giá trị truyền từ project extension hoặc convention plugin.
3. Provider/Convention do plugin cung cấp.
4. Default trong task type/plugin.
5. Giá trị được tính từ project model hoặc môi trường khi resolve.

Đây là cách suy luận để điều tra, không phải một thứ tự precedence chung áp dụng cho mọi plugin. Tài liệu task/property cụ thể mới là nguồn quyết định.

### 9.3. Ví dụ đọc giá trị của BootJar

Spring Boot Gradle Plugin cung cấp task bootJar có type BootJar. Nếu cần xác minh giá trị đã resolve, có thể tạm thêm logging vào build script Groovy:

```groovy
tasks.named('bootJar') {
    doFirst {
        logger.lifecycle("bootJar.archiveFileName={}", archiveFileName.get())
        logger.lifecycle("bootJar.archiveClassifier={}", archiveClassifier.orNull)
        logger.lifecycle("bootJar.mainClass={}", mainClass.orNull)
    }
}
```

Sau đó chạy:

```bash
./gradlew bootJar
```

Ví dụ log có dạng:

```text
bootJar.archiveFileName=demo-1.0.0.jar
bootJar.archiveClassifier=
bootJar.mainClass=com.example.demo.DemoApplication
```

Đây là **ví dụ minh họa**, không phải output cố định của mọi project. Tên archive, classifier và main class phụ thuộc project/plugin configuration. Đoạn doFirst chỉ phục vụ chẩn đoán; bỏ nó sau khi đã ghi nhận giá trị, không commit debug logging nếu không cần.

Nếu dùng Kotlin DSL, có thể cấu hình task theo type:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    doFirst {
        logger.lifecycle("archiveFileName={}", archiveFileName.get())
        logger.lifecycle("archiveClassifier={}", archiveClassifier.orNull)
        logger.lifecycle("mainClass={}", mainClass.orNull)
    }
}
```

Nếu property không tồn tại trong plugin version đang dùng, compiler của Kotlin DSL sẽ chỉ ra API không phù hợp; hãy kiểm tra API docs của đúng version.

### 9.4. help --task không phải công cụ đọc mọi default

Lệnh:

```bash
./gradlew help --task bootJar
```

giúp biết task là gì và cách gọi. Nó không đảm bảo in giá trị cuối của mọi Property. Muốn biết default:

- Đọc API/docs của đúng plugin version.
- Kiểm tra task type và property description.
- Tìm convention(...) hoặc provider trong source plugin khi cần.
- In giá trị đã resolve ở task execution như ví dụ trên.
- Kiểm tra artifact thực tế sau khi task chạy.

Không dùng ./gradlew properties để kết luận toàn bộ task defaults; lệnh đó chủ yếu in project properties.

## 10. Đọc thay đổi version và default theo từng lớp

Khi upgrade, nên lập bảng so sánh trước/sau thay vì sửa nhiều thứ rồi mới tìm nguyên nhân.

| Lớp cần so sánh | Baseline trước upgrade | Sau upgrade | Bằng chứng |
|---|---|---|---|
| Build tool version | Maven/Gradle Wrapper | Version mới | mvn -version, gradlew --version |
| Plugin version | Version cũ | Version mới | POM, settings, version catalog, plugin DSL |
| Goal/task | Danh sách và binding cũ | Danh sách/binding mới | help:describe, tasks --all, build log |
| Configuration | Explicit values và inheritance | Explicit values sau merge | Effective POM, settings/build scripts |
| Plugin defaults | Descriptor/docs cũ | Descriptor/docs mới | help:describe, versioned docs |
| Task conventions | Task type/property cũ | Convention mới | API docs, source plugin, resolved property log |
| Task graph | Dependencies cũ | Dependencies mới | Gradle --dry-run |
| Artifact | Filename, classifier, manifest, layout | Artifact mới | jar tf, manifest, checksum |
| Runtime | Cách app khởi động | Hành vi mới | java -jar, smoke test |

### 10.1. So sánh Maven effective POM

Tạo baseline trước upgrade:

```bash
mvn help:effective-pom -Dverbose -Doutput=target/effective-pom-before.xml
mvn help:active-profiles
```

Sau khi nâng parent/plugin version:

```bash
mvn help:effective-pom -Dverbose -Doutput=target/effective-pom-after.xml
mvn help:active-profiles
```

So sánh:

```bash
git diff --no-index target/effective-pom-before.xml target/effective-pom-after.xml
```

Nếu hai file nằm ngoài Git hoặc command diff không phù hợp môi trường, dùng diff tool của IDE. Tập trung vào plugin, version, executions, phase, goals, configuration và profile đang active.

Sau đó mô tả goal của từng version:

```bash
mvn help:describe \
  -Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.16 \
  -Dgoal=repackage -Ddetail

mvn help:describe \
  -Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.17 \
  -Dgoal=repackage -Ddetail
```

Version 3.5.17 ở đây chỉ là ví dụ cho cách so sánh hai release; thay bằng version thật của dự án. So sánh tên parameter, type, user property, default và mô tả.

### 10.2. So sánh Gradle task graph

Trước upgrade:

```bash
./gradlew clean build --dry-run --console=plain > tasks-before.txt
```

Sau upgrade:

```bash
./gradlew clean build --dry-run --console=plain > tasks-after.txt
```

So sánh:

```bash
git diff --no-index tasks-before.txt tasks-after.txt
```

Task graph có thể thay đổi do plugin hoặc do project config thay đổi. Khi diff khác, tìm task mới/bị bỏ, dependency edge, task được skip và task output. Sau đó chạy build thật để xác nhận hành vi, vì dry-run không kiểm tra task actions hoặc artifact.

### 10.3. Không so sánh output nếu môi trường khác nhau

Để kết quả có ý nghĩa, cố định:

- Commit/source tree.
- JDK/toolchain.
- Maven/Gradle Wrapper.
- Active profiles và project properties.
- OS/architecture khi build phụ thuộc nền tảng.
- Dependency repositories/cache.
- Environment variables có ảnh hưởng build.
- Cùng lệnh build và cùng module.

Nếu baseline dùng JDK 17 nhưng sau upgrade dùng JDK 21, bạn chưa thể kết luận output thay đổi chỉ do plugin version.

## 11. Ví dụ Maven: pin plugin version và đọc default repackage

Đây là POM nhỏ minh họa cách quản lý plugin version riêng và kích hoạt repackage. Spring Boot version được pin để tránh phụ thuộc version ngầm từ môi trường.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>plugin-default-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
            <version>3.5.16</version>
        </dependency>
    </dependencies>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <version>3.5.16</version>
                </plugin>
            </plugins>
        </pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Ví dụ pin dependency và plugin versions để minh họa. POM tối thiểu này chưa khai báo source code; ứng dụng thực tế cần main class và source tree tương ứng. Trong project lớn, ưu tiên dùng Boot parent/BOM theo policy của dự án để đồng bộ dependency versions.

Các lệnh kiểm tra:

```bash
mvn help:effective-pom -Dverbose -Doutput=target/effective-pom.xml

mvn help:describe \
  -Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.16 \
  -Dgoal=repackage -Ddetail

mvn help:active-profiles
mvn package
```

Sau build, kiểm tra archive và manifest. Đừng chỉ dựa vào effective POM để kết luận mainClass hoặc output filename cuối cùng nếu plugin có logic tự suy luận.

## 12. Ví dụ Gradle: quản lý plugin version và task configuration

### 12.1. Version trong settings và plugin DSL

settings.gradle:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
    plugins {
        id 'org.springframework.boot' version '3.5.16'
    }
}
```

build.gradle:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('bootJar') {
    mainClass = 'com.example.demo.DemoApplication'
}
```

Version được khai báo ở settings, plugin được áp dụng trong build script. Khi nâng plugin, đổi version ở nguồn quản lý tương ứng rồi kiểm tra task graph và output.

### 12.2. Không nhầm wrapper và plugin

Một thay đổi có thể nâng:

- gradle-wrapper.properties: Gradle distribution.
- Plugin Spring Boot trong pluginManagement/version catalog.
- Java toolchain.
- Dependency BOM/platform.

Đây là bốn trục khác nhau. Nâng cùng lúc có thể cần thiết, nhưng khi build hỏng hãy so sánh release notes và compatibility matrix của từng trục để biết thay đổi nào gây ra hành vi mới.

## 13. Các kiểu thay đổi default thường gặp

### 13.1. Default chuyển từ suy luận sang yêu cầu khai báo tường minh

Một version plugin cũ có thể tự tìm main class; version mới có thể yêu cầu cấu hình rõ trong một tình huống nhất định hoặc thay đổi thuật toán phát hiện. Dấu hiệu:

- Plugin báo không tìm thấy main class.
- Có nhiều class main và plugin không chọn được.
- bootRun chạy được nhưng bootJar không có Start-Class như mong đợi.

Cách xử lý:

1. Xem docs/migration notes đúng version.
2. Xác nhận compiled output có main class.
3. Xác định task/goal đang suy luận main class.
4. Khai báo main class rõ ràng nếu project có nhiều entry point.
5. Kiểm tra manifest và chạy artifact.

### 13.2. Default output/classifier thay đổi

Plugin có thể đổi cách tạo artifact chính, artifact phụ hoặc tên file. Dấu hiệu:

- CI không tìm thấy target/*.jar theo glob cũ.
- Dockerfile copy nhầm file.
- Publication đẩy plain JAR thay vì executable JAR.
- Checksum khác dù source code không đổi.

Cách xử lý:

- Kiểm tra classifier, finalName, archive name và output directory.
- Xem task/goal nào tạo file.
- Dùng tên file cụ thể trong pipeline hoặc cấu hình archive name ổn định.
- Kiểm tra nội dung JAR, không chỉ kiểm tra file tồn tại.

### 13.3. Default skip hoặc execution binding thay đổi

Dấu hiệu:

- Build thành công nhưng không có report/archive mong đợi.
- Goal/task xuất hiện trong cấu hình nhưng không chạy.
- CI dùng -D...skip hoặc project property làm plugin bỏ qua.
- Gradle task bị onlyIf condition hoặc không có input.

Kiểm tra:

- Maven execution id, phase, goal và user property.
- Gradle task graph, task dependencies, onlyIf, enabled, NO-SOURCE, UP-TO-DATE.
- Log có ghi task/goal skipped hay không.

Không kết luận plugin không hoạt động chỉ vì output cũ vẫn còn trong thư mục build. Chạy clean và xác minh artifact được tạo trong lần build hiện tại.

### 13.4. Default dependency/classpath thay đổi

Plugin có thể thay đổi dependency được đưa vào archive, test runtime hoặc compiler classpath. Dấu hiệu:

- ClassNotFoundException/NoClassDefFoundError.
- Test chạy khác trước.
- Artifact nhỏ hơn/lớn hơn bất thường.
- Dependency trùng hoặc thiếu trong BOOT-INF/lib.

Dùng Maven dependency:tree, Gradle dependencies/dependencyInsight, rồi so archive thật. Đừng quy lỗi cho default plugin nếu dependency graph cũng thay đổi do BOM.

### 13.5. Default caching/incremental behavior thay đổi

Gradle plugin/task có thể khai báo inputs/outputs hoặc cacheability khác. Maven plugin có thể đổi incremental logic. Dấu hiệu:

- Task không chạy vì UP-TO-DATE hoặc FROM-CACHE.
- Report/artifact không được refresh như mong đợi.
- Build sạch thành công nhưng incremental build thất bại hoặc ngược lại.

Chẩn đoán bằng một lượt clean để loại output cũ, sau đó so với build incremental. Không tắt cache toàn cục để che một task khai báo input/output sai.

## 14. Checklist review khi nâng plugin/task/goal

### 14.1. Trước khi nâng

- [ ] Ghi nhận Maven/Gradle Wrapper và JDK/toolchain.
- [ ] Xác định plugin version đang resolve.
- [ ] Ghi lại plugin version khai báo ở parent, pluginManagement, settings hoặc version catalog.
- [ ] Xuất effective POM và active profiles.
- [ ] Lưu danh sách Gradle tasks và task graph của lệnh build chính.
- [ ] Ghi lại giá trị quan trọng: main class, archive name, classifier, output path, skip flags.
- [ ] Lưu artifact baseline và manifest.
- [ ] Ghi lại test reports và build command.

### 14.2. Sau khi nâng

- [ ] Đọc release notes/migration guide của từng plugin và build tool.
- [ ] Kiểm tra plugin compatibility với Maven/Gradle/JDK.
- [ ] So sánh goal/task có còn tồn tại và có đổi tên không.
- [ ] So sánh phase binding/task dependency.
- [ ] So sánh parameter/property, kiểu và default.
- [ ] So sánh effective POM và active profiles.
- [ ] So sánh Gradle task graph.
- [ ] Xác nhận default được resolve bằng log hoặc task property.
- [ ] Build từ clean state.
- [ ] So sánh artifact filename, classifier, manifest, layout và checksum.
- [ ] Chạy unit/integration tests và smoke test executable archive.
- [ ] Kiểm tra CI scripts, Dockerfile và publication đang lấy đúng artifact.
- [ ] Ghi rõ các cấu hình được thêm tường minh để không phụ thuộc default dễ thay đổi.

## 15. Lỗi thường gặp khi đọc default và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Plugin version trong POM khác version log thực thi | Parent, pluginManagement hoặc profile ghi đè | Effective POM, active profiles và debug log |
| Effective POM không hiển thị default plugin | Default được khai báo trong plugin descriptor hoặc tính lúc runtime | help:describe -Ddetail, docs và execution log |
| help:describe không tìm thấy goal | Sai plugin coordinates/version hoặc goal không tồn tại | Kiểm tra groupId, artifactId, version và goal |
| mvn package không chạy repackage | Plugin chưa active hoặc execution/phase không được bind | build/plugins, parent và effective POM |
| pluginManagement có plugin nhưng không chạy | Plugin chỉ được quản lý, chưa được kích hoạt trong build | Thêm plugin vào build/plugins hoặc dùng parent có execution phù hợp |
| -Dskip... không có tác dụng | Dùng sai User Property hoặc property không được plugin hỗ trợ | help:describe, docs đúng version |
| Gradle help --task không hiện default | Task help không in mọi property đã resolve | API docs, task type và log property |
| buildEnvironment không liệt kê plugin DSL | Plugin được resolve qua plugins DSL/pluginManagement | Kiểm tra settings, version catalog và plugins block |
| Gradle task biến mất sau upgrade | Plugin không áp dụng, đổi task name hoặc compatibility fail | tasks --all, plugin version và migration guide |
| Task graph thay đổi | Plugin đổi task dependency hoặc project config | --dry-run trước/sau |
| JAR tên khác sau upgrade | Archive name/classifier/default output thay đổi | bootJar, jar, Maven repackage config và manifest |
| Main class không còn được tìm thấy | Source set/compiled output hoặc default discovery thay đổi | Main class, plugin docs, task/goal configuration |
| Build success nhưng archive thiếu loader | Đang xem plain JAR hoặc repackage/bootJar không chạy | Manifest, BOOT-INF và đúng output file |
| Build chỉ lỗi trên CI | Khác JDK, profile, environment, property hoặc wrapper | So môi trường và command line |
| Build incremental khác clean build | Cache/input/output hoặc output cũ | Clean build, task input/output và cache diagnostics |

## 16. Chiến lược nâng công cụ an toàn và có thể truy vết

Một lần nâng công cụ tốt cần có baseline, diff và bằng chứng hành vi. Thực hiện theo trình tự:

1. **Pin version:** không để plugin quan trọng phụ thuộc version động hoặc prefix không rõ nguồn.
2. **Nâng có kiểm soát:** ưu tiên thay đổi từng trục; nếu phải nâng wrapper, plugin và JDK cùng lúc, ghi lại từng thay đổi.
3. **Đọc tài liệu version cụ thể:** release notes, migration guide, plugin descriptor/API docs.
4. **Xuất cấu hình hiệu lực:** Maven effective POM/profiles; Gradle plugin declarations/task graph.
5. **So default:** Maven help:describe; Gradle convention/property docs và giá trị đã resolve.
6. **Build clean:** tránh nhầm output cũ với output của plugin mới.
7. **Kiểm tra artifact:** tên, classifier, manifest, archive layout và dependencies.
8. **Chạy tests/smoke tests:** xác nhận hành vi chứ không chỉ task success.
9. **Cập nhật CI/Docker/publication:** trỏ tới đúng artifact sau upgrade.
10. **Ghi quyết định:** plugin version, wrapper, JDK, property được pin tường minh và lý do.

Đối với những default ảnh hưởng đến release, nên cấu hình tường minh khi điều đó làm hành vi rõ ràng và ổn định hơn. Không cần copy mọi default vào POM/build script: chỉ pin những giá trị có ý nghĩa với hợp đồng build, ví dụ main class, archive classifier hoặc output name khi pipeline phụ thuộc chúng.

## 17. Tài liệu chính thức

- [Apache Maven Help Plugin — Plugin details và các goal](https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html)
- [Maven Help Plugin — help:describe configuration](https://maven.apache.org/plugins/maven-help-plugin/examples/describe-configuration.html)
- [Maven Help Plugin — help:describe goal reference](https://maven.apache.org/components/plugins/maven-help-plugin/describe-mojo.html)
- [Maven Help Plugin — help:effective-pom goal reference](https://maven.apache.org/components/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Plugin Configuration](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Spring Boot Maven Plugin 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Spring Boot Gradle Plugin — Running Applications](https://docs.spring.io/spring-boot/gradle-plugin/running.html)
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle — Configuring Tasks Lazily and Property Conventions](https://docs.gradle.org/current/userguide/lazy_configuration.html)
- [Gradle — Plugins](https://docs.gradle.org/current/userguide/plugins.html)
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html)
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)

**Kết luận:** Để đọc thay đổi cấu hình khi nâng công cụ, hãy tách ba thứ: cấu hình project đã merge, default/convention do plugin cung cấp và giá trị thực tế sau khi build. Maven dùng help:describe, effective POM và lifecycle mapping để soi goal/parameter; Gradle dùng plugin declarations, task type, task graph và resolved properties để soi task/convention. Cuối cùng, kiểm tra artifact thật để xác nhận thay đổi default có làm đổi tên file, manifest, classifier hoặc nội dung executable JAR/WAR hay không.
