# Vị trí mã nguồn, lớp và tài nguyên được sinh bởi Maven hoặc Gradle

Khi build một ứng dụng **Spring Boot** thành **GraalVM Native Image**, Maven và Gradle tạo ra nhiều loại đầu ra: mã nguồn AOT, mã Java đã biên dịch, tài nguyên được sao chép, metadata phục vụ Native Image, JAR và native executable. Nếu không phân biệt các loại này, rất dễ tìm nhầm file, chỉnh sửa output do build sinh ra, hoặc kết luận sai rằng một resource đã được đóng gói chỉ vì nó xuất hiện trong thư mục build.

Trong chương **Sản phẩm build** của module **`SPRING_BOOT_NATIVE_IMAGE`**, bài học này giúp bạn đọc cấu trúc thư mục đầu ra của Maven/Gradle, nhận biết vị trí mã nguồn và lớp được sinh bởi Spring AOT, truy vết tài nguyên và metadata, rồi xác minh artifact cuối cùng. Đây là kỹ năng cần thiết khi kiểm tra reflection/resource, xử lý lỗi native build, đóng gói container và vận hành bản native.

> **Lưu ý về đường dẫn:** các thư mục bên dưới là quy ước phổ biến của Maven, Gradle và Spring Boot. Phiên bản plugin, source set, cấu hình output directory, module và tác vụ cụ thể có thể thay đổi đường dẫn. Hãy xác minh trên dự án thực tế bằng task/log và cấu hình build; không coi một đường dẫn minh họa là cam kết bất biến của mọi phiên bản.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **mã nguồn đầu vào**, **mã nguồn sinh tự động**, **class files**, **resources**, **metadata Native Image** và **artifact cuối cùng**.
- Đọc cây thư mục `target/` của Maven và `build/` của Gradle.
- Tìm vị trí mã nguồn/lớp/tài nguyên được tạo trong quá trình Spring AOT.
- Biết khi nào output được đưa vào JAR hoặc native executable, khi nào chỉ là file trung gian.
- Dùng lệnh Maven, Gradle và hệ điều hành để truy vết đầu ra.
- Xử lý tình trạng output cũ, build cache, sai source set hoặc thiếu resource khi biên dịch native.

## 2. Bốn nhóm dữ liệu cần phân biệt

Một build Spring Boot Native Image có thể tạo nhiều file, nhưng chúng thuộc bốn nhóm chính:

| Nhóm | Ví dụ | Vai trò |
|---|---|---|
| **Nguồn do lập trình viên quản lý** | `src/main/java`, `src/main/resources`, `src/test/java` | Mã và tài nguyên đầu vào của dự án |
| **Nguồn sinh trong build** | Generated sources từ annotation processor, Spring AOT sources | Mã Java được công cụ tạo tự động, thường được compile ở bước sau |
| **Đầu ra biên dịch/trung gian** | `.class`, copied resources, metadata, temporary files | Đầu vào cho package hoặc Native Image |
| **Artifact phân phối** | Executable JAR, native executable, OCI/container image | Sản phẩm dùng để chạy, triển khai hoặc phân phối |

Điểm quan trọng: **file nằm trong `target/` hoặc `build/` chưa chắc là artifact cuối cùng**. Một `.java` trong generated sources có thể được biên dịch thành `.class`; một file resource có thể được copy vào class output; chỉ một phần trong số đó được đóng gói vào JAR/native executable theo cấu hình và phân tích reachability.

### Dòng chảy tổng quát

~~~mermaid
flowchart TD
    S["src/main/java + src/main/resources"] --> C["Java compile / process resources"]
    T["src/test/java + src/test/resources"] --> TC["Test compile / process test resources"]
    A["Annotation processors / Spring AOT"] --> G["Generated Java sources + generated resources"]
    G --> GC["Compile generated Java"]
    C --> O["Main classes + resources"]
    GC --> O
    TC --> TO["Test classes + test resources"]
    O --> P["JAR packaging hoặc Native Image analysis"]
    TO --> NT["Test execution / native test image"]
    P --> N["Native executable"]
    P --> J["Executable JAR"]
    N --> R["Chạy native / container"]
    J --> JVM["Chạy trên JVM"]
~~~

Sơ đồ là mô hình logic. Một plugin có thể gộp hoặc tách task, và một số output được chuyển vào thư mục riêng trước khi đưa vào classpath.

## 3. Cấu trúc đầu vào của dự án Spring Boot

Thông thường, mã nguồn do nhóm phát triển quản lý nằm dưới `src/`:

~~~text
my-spring-app/
├── pom.xml                    # hoặc build.gradle / build.gradle.kts
├── src/
│   ├── main/
│   │   ├── java/              # Mã nguồn ứng dụng
│   │   └── resources/         # application.yml, templates, static, ...
│   └── test/
│       ├── java/              # JUnit tests
│       └── resources/         # fixtures, cấu hình test, dữ liệu mẫu
└── ...
~~~

Ý nghĩa:

- `src/main/java`: mã Java chính của ứng dụng, ví dụ controller, service, repository và cấu hình Spring.
- `src/main/resources`: resource chạy cùng ứng dụng, chẳng hạn `application.yml`, SQL migration, template, file tĩnh và dữ liệu cấu hình.
- `src/test/java`: mã kiểm thử, thường dùng JUnit, Spring Test, Mockito và các thư viện test.
- `src/test/resources`: dữ liệu và cấu hình dành riêng cho test; thông thường không được đóng gói vào artifact production.

**Không đưa file sinh tự động vào `src/main/java` chỉ để IDE nhìn thấy chúng.** Maven/Gradle có cơ chế đăng ký generated source roots. Nếu một plugin đã tạo mã trong output directory, hãy dùng cấu hình plugin/source set thay vì chép thủ công file sang nguồn chính.

## 4. Maven: đọc thư mục `target/`

Maven thường đặt output của một module trong thư mục `target/`. Với dự án Spring Boot, một cây thư mục khái niệm có thể trông như sau:

~~~text
my-spring-app/
├── src/
│   ├── main/java/
│   ├── main/resources/
│   ├── test/java/
│   └── test/resources/
└── target/
    ├── classes/                         # Main .class + resources đã copy
    ├── test-classes/                    # Test .class + test resources
    ├── generated-sources/
    │   └── annotations/                 # Annotation processor output
    ├── generated-test-sources/
    │   └── test-annotations/
    ├── spring-aot/
    │   └── main/
    │       ├── sources/                 # Spring AOT generated Java
    │       ├── resources/               # Resource do AOT tạo
    │       └── classes/                 # Output compile AOT, tùy cấu hình
    ├── surefire-reports/                # Báo cáo test JVM
    ├── my-spring-app.jar                # Executable JAR, nếu package
    └── ...                              # Output native/build trung gian
~~~

Đây là **cây minh họa**, không phải danh sách thư mục bắt buộc. Chẳng hạn, `spring-aot/` chỉ xuất hiện khi chạy goal AOT; vị trí và cách tích hợp class output phụ thuộc phiên bản Spring Boot Maven Plugin. Nếu dự án dùng plugin khác hoặc custom output, thư mục sẽ khác.

### 4.1. `target/classes/`

Đây là thư mục quan trọng chứa **main class files và resources đã được copy** từ source set chính sau các phase compile/process-resources.

Ví dụ:

~~~text
target/classes/
├── com/example/demo/DemoApplication.class
├── com/example/demo/service/OrderService.class
├── application.yml
├── db/migration/V1__init.sql
└── templates/order.html
~~~

Đây là một phần classpath đầu vào khi chạy ứng dụng trên JVM và khi plugin thực hiện các bước tiếp theo. Nhưng việc một resource hiện diện ở `target/classes/` chưa đủ chứng minh Native Image sẽ giữ resource đó trong executable: còn phụ thuộc resource được truy cập thế nào và metadata/hints có phù hợp không.

### 4.2. `target/test-classes/`

Thư mục này chứa test class files và test resources sau `test-compile`/`process-test-resources`. Nó giúp Maven Surefire hoặc Native Build Tools lấy test classes làm đầu vào.

Test resources thường **không thuộc artifact production**. Nếu ứng dụng production vô tình phụ thuộc file trong `src/test/resources`, JVM test có thể chạy được nhưng JAR/native application không có file đó.

### 4.3. `target/generated-sources/` và `target/generated-test-sources/`

Đây thường là nơi các plugin hoặc annotation processors sinh Java sources. Ví dụ:

- Annotation processor tạo implementation hoặc metamodel.
- Bộ sinh mã từ schema/API.
- Các plugin tạo mã cho serialization hoặc mapping.

Các thư mục này được compiler đưa vào source roots thông qua cấu hình plugin. Không phải mọi generated source đều do Spring AOT tạo; cần xác định **task/goal nào sở hữu file**.

### 4.4. `target/spring-aot/`

Khi chạy Spring Boot Maven Plugin AOT, bạn có thể thấy các output riêng cho ứng dụng, thường nằm dưới `target/spring-aot/main/` trong cấu hình mặc định của nhiều phiên bản:

- `sources/`: mã Java được Spring AOT sinh ra từ việc phân tích cấu hình/bean của ứng dụng.
- `resources/`: tài nguyên được tạo trong quá trình AOT nếu có.
- `classes/`: class files được compile từ generated sources ở các pipeline/cấu hình có bước này.

Các thư mục chính xác phụ thuộc phiên bản plugin và cách dự án chạy AOT. Hãy dùng log goal `spring-boot:process-aot` để xác định output directory thực tế.

**Generated AOT source không phải mã nguồn bạn nên sửa trực tiếp.** Khi thay đổi bean, configuration hoặc Runtime Hints trong nguồn thật, hãy chạy lại AOT để sinh output mới.

### 4.5. `target/surefire-reports/`

Maven Surefire thường ghi báo cáo test JVM ở đây, ví dụ XML và text report. Nếu native tests dùng một execution/plugin khác, báo cáo có thể nằm ở vị trí hoặc định dạng khác. Đừng dựa vào sự hiện diện của `surefire-reports` để kết luận native tests đã chạy.

## 5. Gradle: đọc thư mục `build/`

Gradle thường đặt output của mỗi project trong `build/`. Cây thư mục khái niệm:

~~~text
my-spring-app/
├── src/
│   ├── main/java/
│   ├── main/resources/
│   ├── test/java/
│   └── test/resources/
└── build/
    ├── classes/
    │   └── java/
    │       ├── main/                  # Main class files
    │       └── test/                  # Test class files
    ├── resources/
    │   ├── main/                      # Main resources đã copy
    │   └── test/                      # Test resources đã copy
    ├── generated/
    │   ├── sources/                   # Generated source theo plugin/task
    │   ├── aotSources/                # Spring AOT sources, nếu được tạo
    │   └── aotResources/              # Spring AOT resources, nếu được tạo
    ├── reports/
    │   └── tests/                     # Báo cáo Gradle test
    ├── libs/
    │   └── my-spring-app.jar          # JAR nếu bootJar/jar đã chạy
    └── native/                        # Native output theo plugin/cấu hình
~~~

Các thư mục `generated/aotSources`, `generated/aotResources` và `native/` là vị trí minh họa phổ biến; plugin hoặc phiên bản Gradle có thể dùng cấu trúc khác.

### 5.1. `build/classes/java/main/` và `build/classes/java/test/`

Gradle Java plugin thường đặt class files của source set `main` và `test` trong hai thư mục này. Đây là output từ `compileJava` và `compileTestJava`, không phải mã nguồn đầu vào.

### 5.2. `build/resources/main/` và `build/resources/test/`

`processResources` và `processTestResources` copy resource tương ứng sang đây. Nếu `application.yml` xuất hiện trong `build/resources/main/`, điều đó cho thấy resource đã được xử lý trong main source set; vẫn cần kiểm tra packaging hoặc native reachability nếu muốn xác nhận nó có mặt khi chạy.

### 5.3. `build/generated/`

Gradle và các plugin có thể tạo nhiều loại source riêng trong cây `generated/`, chẳng hạn annotation processor output, mã từ schema generator hoặc Spring AOT.

Spring Boot Gradle plugin cung cấp các task AOT như `processAot` và các task liên quan đến compile/process output. Trong nhiều cấu hình, có thể quan sát các thư mục mang tên `aotSources`/`aotResources`. **Không nên đoán tên hoặc vị trí output chỉ từ tên task**; chạy task với `--info` và đọc log/configuration để biết đường dẫn thực tế.

### 5.4. `build/reports/tests/`

Gradle Test thường ghi báo cáo dưới `build/reports/tests/` và kết quả XML dưới `build/test-results/`. Đây là kết quả thực thi test, không phải test classes hay native executable.

### 5.5. `build/libs/`

Đây thường là nơi chứa JAR do task `jar` hoặc `bootJar` tạo ra. Với Spring Boot, executable JAR thường có cấu trúc riêng, ví dụ `BOOT-INF/classes` cho ứng dụng và `BOOT-INF/lib` cho dependencies.

## 6. So sánh Maven và Gradle

| Mục đích | Maven (thông dụng) | Gradle (thông dụng) |
|---|---|---|
| Main classes | `target/classes/` | `build/classes/java/main/` |
| Main resources | `target/classes/` | `build/resources/main/` |
| Test classes | `target/test-classes/` | `build/classes/java/test/` |
| Test resources | `target/test-classes/` | `build/resources/test/` |
| Annotation processor sources | `target/generated-sources/annotations/` | `build/generated/sources/annotationProcessor/java/main/` |
| Spring AOT sources | Thường dưới `target/spring-aot/main/sources/` | Thường trong cây generated AOT như `build/generated/aotSources/` |
| Test reports | `target/surefire-reports/` (Surefire) | `build/reports/tests/`, `build/test-results/` |
| JAR | Thường trong `target/` | Thường trong `build/libs/` |
| Native executable | Theo cấu hình/plugin, thường dưới `target/` hoặc thư mục con | Theo cấu hình/plugin, thường dưới `build/` hoặc thư mục con |

Hai công cụ có quy ước output khác nhau nhưng cùng một logic: **source set → generated source/resource → compile/process → package/native build → artifact**. Đừng chuyển đường dẫn output của Maven sang Gradle theo kiểu thay `target` bằng `build` mà không kiểm tra plugin.

## 7. Spring AOT tạo gì và được dùng ở đâu?

Spring AOT phân tích cấu hình Spring trong giai đoạn build và sinh ra các thành phần hỗ trợ khởi tạo ứng dụng hiệu quả hơn khi chạy native. Có thể phân loại output thành:

1. **Generated Java source:** mã hỗ trợ khởi tạo bean, cấu hình và các phần Spring đã phân tích.
2. **Generated resources:** resource được tạo trong quá trình AOT hoặc các công cụ tiếp theo.
3. **Compiled generated classes:** class files được tạo khi compile generated sources.
4. **Runtime hints/reachability metadata:** thông tin để Native Image giữ lại những phần cần thiết cho reflection, resource, serialization, proxy hoặc JNI.

Không phải mọi loại metadata đều được biểu diễn thành một file riêng trong cùng thư mục AOT. Một số hint được mã hóa trong generated code; metadata từ dependency có thể nằm trong JAR của dependency; cấu hình Native Image thủ công có thể nằm trong `META-INF/native-image/`. Vì vậy, khi điều tra thiếu reflection/resource, cần xem cả output của dự án lẫn dependencies và cấu hình hints.

### Runtime Hints trong mã nguồn

Ví dụ khai báo resource hint bằng Spring:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.ImportRuntimeHints;

class AppRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("templates/*.html");
    }
}
~~~

Sau đó đăng ký registrar qua cấu hình phù hợp của ứng dụng, chẳng hạn annotation `@ImportRuntimeHints(AppRuntimeHints.class)` trên một configuration class.

Đoạn code chỉ là ví dụ cho ý tưởng: hint cần được đăng ký từ **mã nguồn được build**, để Spring AOT/Native Image nhận biết. Không nên mở rộng pattern quá rộng khi không cần thiết. Với reflection, proxy hoặc serialization, dùng API hint tương ứng và test native để xác minh.

### Metadata có thể đến từ dependency

Một thư viện có thể mang theo reachability metadata dưới đường dẫn dạng `META-INF/native-image/`. Khi dependency được đưa vào classpath, Native Image có thể đọc metadata đó theo quy ước GraalVM. Vì vậy, nếu tìm một cấu hình reflection không thấy trong `src/main/resources`, nó có thể nằm trong JAR của dependency hoặc được tạo bởi plugin.

## 8. JAR và native executable khác nhau thế nào?

**Executable JAR** là gói chứa bytecode, resource và dependencies theo cấu trúc mà Spring Boot Loader hiểu. Nó cần một JVM tương thích để chạy, ví dụ:

~~~bash
java -jar target/my-spring-app.jar
~~~

Với Gradle, đường dẫn thường tương tự:

~~~bash
java -jar build/libs/my-spring-app.jar
~~~

**Native executable** là chương trình máy được tạo bởi GraalVM Native Image, không phải JAR để chạy bằng `java -jar`. Ví dụ:

~~~bash
./target/my-spring-app
# hoặc
./build/native/nativeCompile/my-spring-app
~~~

Hai đường dẫn native ở trên chỉ minh họa; tên và thư mục thực tế phải lấy từ log hoặc cấu hình plugin. Trên Windows, binary thường có phần mở rộng `.exe`; binary Linux không chạy trực tiếp như một executable Windows.

| Đặc điểm | Executable JAR | Native executable |
|---|---|---|
| Nội dung chính | Bytecode, resource, dependencies | Mã máy và dữ liệu runtime cần thiết |
| Lệnh chạy | `java -jar ...` | Gọi trực tiếp executable |
| Cần JVM trên máy đích | Có | Không cần JVM đầy đủ theo cách chạy JAR |
| Build step | Java compile và package | AOT + Native Image analysis/compile/link |
| Đặc tính nền tảng | Tương đối dễ chạy trên JVM phù hợp | Gắn với OS/CPU/ABI mục tiêu |

Không nên nhầm thư mục chứa `*.class` với artifact native cuối cùng. Một dự án có thể giữ tất cả intermediate classes và generated source trong output directory, nhưng chỉ tạo một binary native sau bước Native Image.

## 9. Tìm output bằng Maven

### 9.1. Chạy các phase cơ bản

~~~bash
# Xóa output cũ của module
./mvnw clean

# Biên dịch main code và xử lý resource
./mvnw compile

# Biên dịch test classes
./mvnw test-compile

# Đóng gói JAR nếu cấu hình dự án hỗ trợ
./mvnw package
~~~

Sau mỗi lệnh, kiểm tra `target/` để nhận diện output mới. `compile` không nhất thiết tạo JAR; `package` mới đi đến phase đóng gói.

### 9.2. Chạy Spring AOT

Trong dự án có Spring Boot Maven Plugin và cấu hình AOT phù hợp:

~~~bash
./mvnw spring-boot:process-aot
~~~

Hoặc chạy trong profile native của dự án, ví dụ:

~~~bash
./mvnw -Pnative package
~~~

Tên profile và execution phụ thuộc POM. Khi goal AOT chạy, xem log để tìm output source/resources được tạo. Không giả định rằng goal AOT đã chạy chỉ vì build JAR thành công.

### 9.3. Build Native Image

Với dự án đã cấu hình Native Build Tools:

~~~bash
./mvnw -Pnative native:compile
~~~

Kiểm tra log để biết:

- Spring AOT goal có chạy không.
- Native Image compiler được gọi với đường dẫn/version nào.
- Output executable được đặt ở đâu.
- Có lỗi metadata/resource hay lỗi native linker không.

Nếu dùng `spring-boot:build-image`, output cuối là container image trong daemon/registry theo cấu hình buildpack; không nhất thiết có một executable native dễ thấy ở cùng vị trí trên host. Hãy đọc log builder và cấu hình image.

## 10. Tìm output bằng Gradle

### 10.1. Chạy các task Java

~~~bash
# Xóa output cũ
./gradlew clean

# Biên dịch main source và copy resource
./gradlew classes

# Biên dịch test source và copy test resource
./gradlew testClasses

# Đóng gói executable JAR theo cấu hình Spring Boot
./gradlew bootJar
~~~

Sau các task, kiểm tra `build/classes`, `build/resources` và `build/libs`.

### 10.2. Chạy Spring AOT

~~~bash
./gradlew processAot
~~~

Task AOT cần plugin Spring Boot và cấu hình phù hợp. Dùng:

~~~bash
./gradlew processAot --info
~~~

để xem task thực sự chạy và các đường dẫn generated output. Nếu task không tồn tại, kiểm tra Spring Boot Gradle plugin đã áp dụng vào đúng project/subproject chưa.

### 10.3. Build Native Image

~~~bash
./gradlew nativeCompile --info
~~~

Với GraalVM Native Build Tools, task native thường gọi công cụ Native Image và tạo executable theo cấu hình. Thư mục output có thể được tùy chỉnh; đừng mặc định `build/native/nativeCompile/` là luôn đúng.

Đối với container build qua Spring Boot/Buildpacks:

~~~bash
./gradlew bootBuildImage
~~~

Builder image có thể chạy toolchain native bên trong container. `build/` trên host có thể chỉ chứa các intermediate Gradle, trong khi artifact container được lưu trong Docker daemon hoặc registry. Hãy phân biệt **file output local** và **container image**.

## 11. Truy vết file trên Linux, macOS và Windows

### Linux/macOS

Liệt kê thư mục output:

~~~bash
find target -maxdepth 4 -type d
find target -type f | sort

find build -maxdepth 5 -type d
find build -type f | sort
~~~

Tìm các file thường quan tâm:

~~~bash
find target build -type f \( -name '*.class' -o -name '*.jar' -o -name '*.json' -o -name '*.properties' \)
~~~

Lệnh có thể báo lỗi nếu một trong hai thư mục chưa tồn tại; điều đó chỉ cho biết task tương ứng chưa tạo output hoặc build tool khác đang được dùng.

### Windows PowerShell

~~~powershell
# Liệt kê cây output của Maven/Gradle nếu thư mục đã tồn tại
Get-ChildItem -Path .\target -Recurse -File -ErrorAction SilentlyContinue
Get-ChildItem -Path .\build -Recurse -File -ErrorAction SilentlyContinue

# Tìm class, JAR và metadata JSON
Get-ChildItem -Path .\target, .\build -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in '.class', '.jar', '.json', '.properties' } |
    Select-Object FullName, Length
~~~

Khi output quá nhiều, lọc theo tên thư mục/file hoặc chỉ xem khu vực cần điều tra. Không cần in toàn bộ thư mục `build/` trong mỗi lần debug.

### Tìm trong JAR

Vì JAR là ZIP archive, có thể xem danh sách nội dung:

~~~bash
jar tf target/my-spring-app.jar
~~~

Hoặc JAR Gradle:

~~~bash
jar tf build/libs/my-spring-app.jar
~~~

Tìm `BOOT-INF/classes/` để xem main resources/classes và `BOOT-INF/lib/` để xem dependencies. Metadata `META-INF/native-image/` có thể nằm trong dependency JAR hoặc phần output được đóng gói, tùy thư viện và plugin.

## 12. Đọc lỗi bằng cách xác định đúng output bị thiếu

| Triệu chứng | Kiểm tra đầu tiên | Nguyên nhân có thể |
|---|---|---|
| Class ứng dụng không xuất hiện trong `target/classes`/`build/classes` | Source set, package, compile task, compiler log | Source chưa được compile hoặc task không chạy |
| Resource không xuất hiện trong main output | `src/main/resources`, resource filtering, process-resources/processResources | Sai vị trí, include/exclude hoặc cấu hình resource |
| Generated source không xuất hiện | Annotation processor hoặc AOT task log | Plugin chưa áp dụng, task chưa chạy, điều kiện AOT chưa bật |
| AOT source có nhưng không có class tương ứng | Compile AOT task và compile log | Generated source không được thêm vào source set hoặc compile thất bại |
| File có trong output nhưng mất khỏi JAR | JAR packaging, includes/excludes, source set | Packaging bỏ qua output hoặc resource thuộc test source set |
| File có trong JAR nhưng không đọc được ở native | Reachability metadata/Runtime Hints và Native Image log | Resource chưa được đăng ký/giữ lại phù hợp |
| Native executable không nằm ở thư mục dự đoán | Native task log, outputDirectory, binary name | Plugin dùng output directory khác hoặc build chưa đến bước native |
| Thay đổi source nhưng binary vẫn có hành vi cũ | Incremental build/cache và file output | Output cũ hoặc task chưa được chạy lại như mong muốn |

### Quy trình điều tra có thứ tự

1. Xác nhận file đầu vào có tồn tại đúng nơi: `src/main/java`, `src/main/resources`, `src/test/...`.
2. Xác nhận task/goal chịu trách nhiệm đã chạy: `compile`, `processResources`, `processAot`, `nativeCompile` hoặc goal Maven tương ứng.
3. Kiểm tra output trung gian: class, generated source/resource.
4. Kiểm tra package JAR hoặc native image log.
5. Kiểm thử runtime để phân biệt lỗi đóng gói với lỗi reachability hoặc cấu hình môi trường.

**Không nhảy thẳng đến kết luận thiếu reflection metadata** khi resource còn chưa được copy vào main output. Cần xác định lỗi xảy ra ở giai đoạn nào.

## 13. Output cũ, incremental build và `clean`

Maven và Gradle đều tối ưu build bằng cách chỉ chạy lại tác vụ cần thiết. Điều này giúp tăng tốc, nhưng khi đổi phiên bản plugin, source set, AOT configuration hoặc native build arguments, output cũ có thể làm việc điều tra khó khăn.

### Maven

~~~bash
./mvnw clean
./mvnw -Pnative package
~~~

`clean` thường xóa `target/` của module; build lại tạo output từ đầu. Trong multi-module, phạm vi clean phụ thuộc reactor và nơi chạy lệnh.

### Gradle

~~~bash
./gradlew clean
./gradlew nativeCompile
~~~

`clean` xóa thư mục build của project theo cấu hình Gradle. Gradle Build Cache có thể tái sử dụng output hợp lệ sau đó; điều này không có nghĩa output cũ bị lỗi. Khi nghi ngờ cache, kiểm tra task outcome/log trước khi vô hiệu hóa cache trên diện rộng.

**Không dùng clean như phản xạ cho mọi lỗi.** Hãy dùng khi cần xác minh build sạch, khi output trung gian đã cũ hoặc khi thay đổi cấu hình làm khó phân biệt trạng thái. Với CI, build sạch là một lựa chọn kiểm chứng, còn cache được quản lý có thể giúp tiết kiệm thời gian.

## 14. Có nên sửa hoặc commit generated output không?

Thông thường:

- **Sửa source đầu vào** trong `src/main/java`, `src/main/resources`, test sources hoặc cấu hình build.
- **Không sửa thủ công** `.java`/`.class` do AOT hoặc annotation processor sinh ra trong `target/`/`build/`; chúng có thể bị ghi đè lần build tiếp theo.
- **Không commit** thư mục output thông thường như `target/` và `build/`, trừ trường hợp repository có quy ước đặc biệt được xác định rõ.
- **Commit mã nguồn Runtime Hints hoặc cấu hình Native Image do nhóm viết** nếu chúng thuộc source/configuration được quản lý.
- **Không xóa metadata của dependency** chỉ vì không thấy nó trong `src/`; kiểm tra nội dung JAR và quy trình đóng gói trước.

Đối với mã sinh ra từ công cụ ngoài Spring AOT, quy tắc có thể khác nếu dự án chủ động quản lý generated source trong repository. Hãy theo convention của chính dự án; không áp dụng một chính sách duy nhất cho mọi bộ sinh mã.

## 15. Bài tập thực hành

**Bài 1 — Phân biệt main/test resource:** `fixtures/customer.json` chỉ có trong `src/test/resources`. Vì sao test JVM đọc được nhưng native executable production không có file?

**Gợi ý:** resource thuộc test source set, thường được copy vào `target/test-classes` hoặc `build/resources/test`, không phải main output dùng để đóng gói production.

**Bài 2 — Tìm Spring AOT output:** Sau khi chạy `./mvnw -Pnative package`, bạn không thấy `target/spring-aot/`. Có thể kết luận Spring AOT không tạo mã không?

**Gợi ý:** chưa thể. Kiểm tra profile, goal `process-aot`, log và output directory cấu hình của phiên bản plugin. Có thể AOT chưa được kích hoạt hoặc output được đặt nơi khác.

**Bài 3 — Generated source chưa được compile:** Một file Java xuất hiện dưới generated source directory nhưng không có class tương ứng. Cần kiểm tra điều gì?

**Gợi ý:** source root đã được đăng ký chưa, compile AOT/generated source task có chạy không, compiler có lỗi không và task dependency có đúng thứ tự không.

**Bài 4 — Resource có trong JAR nhưng không có trong native:** Hãy nêu các bước điều tra.

**Gợi ý:** kiểm tra tên/đường dẫn resource trong JAR; xác định code truy cập resource; kiểm tra Spring Runtime Hints/reachability metadata; đọc Native Image diagnostic; chạy lại executable và test.

**Bài 5 — Phân biệt artifact:** `build/libs/app.jar` và `build/native/nativeCompile/app` là hai file gì?

**Gợi ý:** JAR chứa bytecode/resources để JVM chạy; file thứ hai là ví dụ native executable do Native Image tạo, đường dẫn thực tế phụ thuộc plugin/cấu hình.

## 16. Checklist khi bàn giao sản phẩm build

- [ ] Xác định đúng source set main/test và resource đầu vào.
- [ ] Biết main/test classes được tạo ở đâu trong `target/` hoặc `build/`.
- [ ] Xác nhận annotation processor/Spring AOT task đã chạy khi cần.
- [ ] Xác định đường dẫn generated sources/resources bằng log thực tế.
- [ ] Kiểm tra generated Java được compile thành class files.
- [ ] Phân biệt resource copy ở class output với resource được giữ trong Native Image.
- [ ] Xác nhận reachability metadata/Runtime Hints phù hợp với reflection và resource.
- [ ] Kiểm tra nội dung JAR hoặc đường dẫn native executable.
- [ ] Chạy smoke/integration tests trên đúng loại artifact sẽ triển khai.
- [ ] Ghi lại phiên bản JDK/GraalVM, Maven/Gradle plugin và nền tảng build.
- [ ] Không chỉnh trực tiếp hoặc commit output generated thông thường.

**Ghi nhớ:** Maven thường đặt output trong `target/`, Gradle thường đặt output trong `build/`. Trong đó có thể có mã nguồn sinh tự động, class files, resource đã copy, AOT output, báo cáo test và artifact. Hãy truy vết theo đúng task/goal và kiểm tra từng giai đoạn để biết file nào là đầu vào, file nào là trung gian và file nào thực sự được đóng gói vào JAR hoặc native executable.
