# Biên dịch native với profile và goal phù hợp cấu hình plugin Maven

## 1. Mục tiêu và ba khái niệm cần phân biệt

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng **Spring AOT** trước khi GraalVM Native Image tạo executable. Với Maven, cách build phụ thuộc vào profile, plugin và execution trong `pom.xml`. Vì thế, một lệnh như `mvn -Pnative native:compile` chỉ đúng khi POM đã cấu hình các thành phần tương ứng.

- **Maven profile** là nhóm cấu hình được kích hoạt theo tên. `-Pnative` kích hoạt profile tên `native`; đây không phải cờ native mà Maven tự hiểu trong mọi dự án.
- **Plugin goal** là hành động do plugin cung cấp, ví dụ `spring-boot:process-aot` hoặc `native:compile`.
- **Lifecycle phase** là mốc trong vòng đời build như `package`. Một goal tự chạy ở phase chỉ khi có execution bind goal đó vào phase.

Bài này hướng dẫn chọn đúng lệnh để tạo executable trực tiếp, gắn native compilation vào Maven lifecycle hoặc tạo container image bằng Cloud Native Buildpacks.

## 2. Chuỗi xử lý native trong Maven

Ở mức khái niệm, quy trình tạo native executable gồm:

1. Maven đọc profile, plugin, dependency và execution.
2. Java source và dependency được biên dịch/chuẩn bị.
3. **Spring Boot Maven Plugin** chạy `process-aot` để phân tích ApplicationContext và sinh mã/metadata AOT.
4. **GraalVM Native Build Tools Maven Plugin** cung cấp goal tích hợp Native Image và cấu hình classpath/reachability metadata.
5. GraalVM Native Image phân tích rồi biên dịch thành executable cho OS/CPU đích.

~~~mermaid
flowchart TB
    P["pom.xml: profiles, plugins, executions"] --> V["Maven kích hoạt profile và chọn goal/phase"]
    V --> J["Compile Java + dependency"]
    J --> A["Spring Boot: process-aot"]
    A --> G["Mã AOT và metadata"]
    G --> N["GraalVM Native Build Tools"]
    N --> I["GraalVM Native Image"]
    I --> E["Executable native"]
    P -. "plugin configuration" .-> A
    P -. "plugin configuration" .-> N
~~~

Sơ đồ mô tả quan hệ logic; thứ tự thực tế phụ thuộc plugin version, Maven lifecycle và execution của dự án. Khi dùng `spring-boot-starter-parent`, profile `native` của Spring Boot Parent chuẩn bị một số tích hợp quan trọng, bao gồm thực thi AOT và cấu hình mặc định cho Native Build Tools.

## 3. Kiểm tra môi trường và POM

Native compilation cần GraalVM JDK có Native Image phù hợp, ngoài Maven và cấu hình Spring Boot. Trên máy build, kiểm tra:

~~~bash
java -version
native-image --version
./mvnw --version
~~~

Trên Windows có thể dùng `mvnw.cmd --version`. Nếu `native-image` không được tìm thấy, cần cài/chọn bản GraalVM có Native Image và cấu hình `JAVA_HOME`/`PATH` đúng. Native compiler còn cần toolchain hệ điều hành tương ứng, chẳng hạn compiler/linker/SDK trên macOS hoặc Linux.

Ví dụ cấu hình thường gặp khi dùng Spring Boot Parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>${spring-boot.version}</version>
    <relativePath/>
</parent>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

`${spring-boot.version}` là placeholder cho version Spring Boot do dự án quản lý. Khi dùng Spring Boot Parent, nhiều version plugin và thiết lập mặc định được quản lý sẵn; không tự thêm version tùy tiện nếu chưa kiểm tra compatibility. POM thực tế cũng có thể quản lý version qua property hoặc parent nội bộ.

**Điều kiện quan trọng:** plugin phải được khai báo ở module chứa ứng dụng Spring Boot. Trong multi-module Maven, module thư viện không nhất thiết phải tạo native executable riêng.

## 4. Trường hợp phổ biến: dùng spring-boot-starter-parent

Nếu dự án kế thừa `spring-boot-starter-parent`, Spring Boot cung cấp profile tên `native`. Khi profile được kích hoạt, profile này:

- cấu hình thực thi `process-aot` khi Spring Boot Maven Plugin được áp dụng;
- chuẩn bị một số thiết lập cho native image/build image;
- cung cấp mặc định cho Native Build Tools, như dùng raw classpath phù hợp thay vì nhầm lẫn với JAR đã được Spring Boot repackaged;
- kiểm tra GraalVM phù hợp và hỗ trợ lấy third-party reachability metadata.

Vì vậy, không nên tự khai báo lại mọi execution nếu dự án đã dùng Spring Boot Parent. Module ứng dụng cần khai báo cả `spring-boot-maven-plugin` và `native-maven-plugin` để tận dụng profile.

### 4.1. Tạo executable trực tiếp với native:compile

Khi muốn tạo executable native trên máy build:

~~~bash
./mvnw -Pnative native:compile
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| `./mvnw` | Maven Wrapper của dự án, chọn Maven version đã khai báo |
| `-Pnative` | Kích hoạt profile Maven có tên `native` |
| `native:compile` | Gọi goal `compile` của plugin prefix `native`, thường là `org.graalvm.buildtools:native-maven-plugin` |

Kết quả thường nằm trong `target/`; tên executable mặc định dựa trên artifact/project name hoặc giá trị `imageName` đã cấu hình. Kiểm tra:

~~~bash
ls -la target
~~~

Trên Windows dùng `dir target`. Chạy executable thực tế, ví dụ:

~~~bash
./target/<ten-executable>
~~~

Thay `<ten-executable>` bằng tên file thật. Đây là binary native cho nền tảng build/target, không phải JAR chạy bằng `java -jar`.

### 4.2. Build theo Maven lifecycle với package

Một cách khác là bind goal `compile-no-fork` của Native Build Tools vào phase `package`. Khi execution đã được cấu hình, có thể chạy:

~~~bash
./mvnw -Pnative package
~~~

Ví dụ cấu hình minh họa:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <version>${native.maven.plugin.version}</version>
    <extensions>true</extensions>
    <executions>
        <execution>
            <id>build-native</id>
            <phase>package</phase>
            <goals>
                <goal>compile-no-fork</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <mainClass>com.example.Application</mainClass>
        <imageName>billing-service</imageName>
    </configuration>
</plugin>
~~~

Version là property do dự án quản lý; thay `com.example.Application` bằng main class thật. `extensions` cho phép plugin tham gia mở rộng Maven lifecycle/artifact handling theo yêu cầu của Native Build Tools.

**Không mặc định rằng `package` luôn tạo native executable.** Điều đó chỉ xảy ra khi có execution native bind vào phase này và profile chứa execution đang được kích hoạt. Nếu POM chỉ khai báo plugin mà không có execution, `./mvnw -Pnative package` có thể chỉ tạo JAR thông thường. Nếu Spring Boot Parent đã quản lý profile, kiểm tra cấu hình hiệu lực trước khi tự thêm execution để tránh build native hai lần.

## 5. Nếu không dùng spring-boot-starter-parent

Một số dự án kế thừa corporate parent POM, dùng BOM hoặc quản lý lifecycle riêng. Không thể giả định profile `native` của Spring Boot Parent đã tồn tại.

Khi đó cần tự cấu hình các phần cần thiết:

1. Gắn execution `process-aot` cho `spring-boot-maven-plugin`.
2. Cấu hình Native Build Tools và goal tạo executable (gọi trực tiếp `native:compile` hoặc bind `compile-no-fork` vào phase phù hợp).
3. Tích hợp reachability metadata, ví dụ goal `add-reachability-metadata` của Native Build Tools.
4. Quản lý version Spring Boot, Native Build Tools và GraalVM tương thích.

Ví dụ khai báo AOT:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>process-aot</id>
            <goals>
                <goal>process-aot</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Ví dụ cấu hình Native Build Tools ở mức khái niệm:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <version>${native.maven.plugin.version}</version>
    <extensions>true</extensions>
    <executions>
        <execution>
            <id>reachability-metadata</id>
            <goals>
                <goal>add-reachability-metadata</goal>
            </goals>
        </execution>
        <execution>
            <id>build-native</id>
            <phase>package</phase>
            <goals>
                <goal>compile-no-fork</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <mainClass>com.example.Application</mainClass>
    </configuration>
</plugin>
~~~

Đây là mẫu thể hiện các goal cần tích hợp, không phải POM hoàn chỉnh cho mọi dự án. Cần kiểm tra version plugin, dependency, thứ tự execution và classpath thực tế. Nếu chỉ gọi `native:compile` trực tiếp, hãy chắc chắn AOT và metadata đã chạy trước đó hoặc đã được tích hợp vào lifecycle.

### Tự khai báo profile native

Khi không kế thừa Spring Boot Parent, có thể nhóm cấu hình trong profile riêng:

~~~xml
<profiles>
    <profile>
        <id>native</id>
        <build>
            <plugins>
                <!-- Đặt Spring Boot AOT và Native Build Tools
                     executions tương ứng trong profile này. -->
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Lúc đó `-Pnative` kích hoạt profile do dự án định nghĩa. Tách cấu hình native khỏi build JVM giúp máy phát triển không phải chạy native compilation trong mọi lần `mvn package` thông thường.

## 6. Chọn đúng goal và cách đóng gói

Các lệnh dưới đây không thay thế nhau:

| Goal/lệnh | Thành phần cung cấp | Tác dụng | Dùng khi nào |
| --- | --- | --- | --- |
| `spring-boot:process-aot` | Spring Boot Maven Plugin | Chạy riêng Spring AOT trên ứng dụng | Kiểm tra hoặc chẩn đoán bước AOT |
| `native:compile` | GraalVM Native Build Tools | Gọi Native Image để biên dịch executable | Build native trực tiếp theo cấu hình plugin |
| `native:compile-no-fork` | GraalVM Native Build Tools | Goal phù hợp để bind vào lifecycle mà không fork lifecycle khác | Tự cấu hình execution, ví dụ gắn `package` |
| `spring-boot:build-image` | Spring Boot Maven Plugin/Buildpacks | Tạo container image; builder có thể build native executable trong môi trường container | Cần image để triển khai container |
| `mvn -Pnative package` | Maven lifecycle | Chạy các goal đã bind vào lifecycle trong profile `native` | POM đã cấu hình execution phù hợp |

### 6.1. Chạy riêng Spring AOT để chẩn đoán

~~~bash
./mvnw -Pnative spring-boot:process-aot
~~~

Goal này giúp tách lỗi Spring AOT khỏi lỗi GraalVM compiler. Nếu AOT thất bại vì cấu hình bean/condition hoặc code khởi tạo, chạy `native:compile` tiếp theo không giải quyết được nguyên nhân. Thư mục sinh mã mặc định của Spring Boot Maven Plugin có thể nằm dưới `target/spring-aot/main/`, với các thư mục sources, classes và resources; đường dẫn có thể được cấu hình trong plugin.

### 6.2. Tạo container image bằng Buildpacks

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Đây là con đường **đóng gói container**. Spring Boot Maven Plugin phối hợp Cloud Native Buildpacks; builder image thực hiện các bước cần thiết để tạo image. Lệnh này khác với việc tạo executable trực tiếp bằng `native:compile` trên máy local. Hãy kiểm tra Docker daemon, builder/run image, nền tảng CPU và tài nguyên dành cho container engine.

Nếu mục tiêu là có executable local để benchmark, `native:compile` thường trực tiếp hơn. Nếu mục tiêu là artifact triển khai container, `build-image` phù hợp hơn.

## 7. Profile Maven và Spring Profile ảnh hưởng đến AOT

Spring AOT chuẩn bị ApplicationContext trong lúc build, vì vậy các điều kiện liên quan bean graph được đánh giá trong môi trường build. Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {
    @Bean
    @ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
    )
    AuditService auditService() {
        return new AuditService();
    }
}
~~~

Nếu quá trình AOT chạy với `feature.audit.enabled=false`, bean có thể không được đưa vào mã AOT. Đổi giá trị thành `true` khi chạy native executable không tự động tái dựng bean graph.

Profile Maven `native` chỉ là profile build. Nó **không đồng nghĩa** với Spring Profile ứng dụng như `dev`, `staging` hay `prod`:

- `-Pnative` chọn cấu hình build Maven.
- `spring.profiles.active` hoặc tham số Spring tương ứng chọn profile của ứng dụng.

Phải xác định rõ profile Spring nào được dùng trong AOT, đặc biệt nếu chúng làm thay đổi bean graph. Các giá trị runtime thông thường như URL, timeout hay credential không mặc nhiên bị đóng băng chỉ vì dùng AOT; cần phân biệt giá trị được đọc lúc chạy với giá trị quyết định cấu trúc bean lúc build.

## 8. Tùy chỉnh Native Image qua plugin Maven

Native Build Tools cho phép cấu hình tham số Native Image trong `pom.xml`. Ví dụ:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <imageName>billing-service</imageName>
        <verbose>true</verbose>
        <buildArgs>
            <buildArg>--no-fallback</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Đây là ví dụ minh họa; cấu hình thực tế có thể nằm trong profile `native` hoặc được quản lý bởi parent. `--no-fallback` yêu cầu build thất bại nếu không tạo được native image đúng nghĩa thay vì sinh fallback image; cần hiểu ý nghĩa tùy chọn trước khi bật.

Reachability metadata có thể đến từ:

- Spring AOT và các thư viện tích hợp sẵn;
- metadata repository do Native Build Tools hỗ trợ;
- file cấu hình native trong resource của dự án;
- hints do ứng dụng tự đăng ký, ví dụ `RuntimeHintsRegistrar`.

Nếu native executable lỗi reflection hoặc resource, cần xác định metadata thiếu ở đâu. Không nên mặc định thêm hàng loạt metadata hoặc build arguments không cần thiết.

## 9. Kiểm tra cấu hình hiệu lực và thứ tự thực thi

Trước khi build tốn thời gian, kiểm tra profile và plugin thực sự được Maven kích hoạt:

~~~bash
# Liệt kê các profile đang active.
./mvnw help:active-profiles -Pnative

# Hiển thị cấu hình POM đã được kế thừa/ghép.
./mvnw help:effective-pom -Pnative -Doutput=target/effective-pom.xml

# Kiểm tra môi trường Maven/JDK.
./mvnw --version
~~~

`help:effective-pom` giúp xác định plugin version, execution và cấu hình kế thừa từ parent. Có thể mở `target/effective-pom.xml` để tìm `process-aot`, `native-maven-plugin`, `compile-no-fork` và profile liên quan. Đây là đầu ra chẩn đoán trong `target`, không phải POM nguồn để sửa.

Khi cần chẩn đoán sâu:

~~~bash
./mvnw -Pnative -X native:compile
~~~

Log `-X` rất dài và có thể chứa đường dẫn hoặc giá trị cấu hình nhạy cảm; loại bỏ secret/token trước khi chia sẻ log.

## 10. Kiểm thử và phân loại lỗi

Build native thành công không có nghĩa mọi chức năng đều tương thích:

| Giai đoạn | Dấu hiệu lỗi | Kiểm tra trước |
| --- | --- | --- |
| Maven profile | `No plugin found for prefix 'native'` hoặc profile không active | Plugin đã khai báo chưa, prefix mapping và `-Pnative` có đúng không |
| Spring AOT | `process-aot` thất bại khi tạo ApplicationContext | Spring config, profile/condition, bean khởi tạo tại build time |
| Metadata | Thiếu cấu hình reflection/resource/proxy | Reachability metadata, runtime hints và dependency hỗ trợ native |
| Native Image | Không tìm thấy `native-image`, compiler/linker hoặc build lỗi | GraalVM JDK, Native Image, toolchain OS, version tương thích |
| Runtime native | Binary chạy nhưng một nhánh nghiệp vụ lỗi | Reflection, resource, serialization, proxy, JNI và test native |
| Container | Image build/chạy lỗi hoặc sai kiến trúc | Docker/Buildpacks, builder/run image, OS/CPU target và thư viện hệ thống |

Chạy test JVM để có baseline:

~~~bash
./mvnw test
~~~

Native Build Tools có thể hỗ trợ biên dịch và thực thi test trên Native Image nếu đã cấu hình native test execution và JUnit Platform phù hợp:

~~~bash
./mvnw -Pnative test
~~~

Lệnh trên chỉ chạy native test nếu execution tương ứng được cấu hình trong plugin/profile. Khi cần bỏ qua native test nhưng vẫn chạy test JVM, Native Build Tools hỗ trợ `-DskipNativeTests`; `-DskipTests` có phạm vi rộng hơn và có thể bỏ qua cả test JVM.

Các nhánh nên kiểm thử gồm JSON binding, reflection, proxy/transaction, resource trên classpath, serialization, kết nối database và các tính năng có điều kiện cấu hình.

## 11. Quy trình thực hành hoàn chỉnh

Giả sử dự án Spring Boot tên `billing-service` sử dụng `spring-boot-starter-parent` và khai báo `spring-boot-maven-plugin` cùng `native-maven-plugin` trong module ứng dụng.

**Bước 1 — xác nhận profile và toolchain**

~~~bash
./mvnw --version
java -version
native-image --version
./mvnw help:active-profiles -Pnative
~~~

**Bước 2 — xác nhận Spring AOT**

~~~bash
./mvnw -Pnative spring-boot:process-aot
~~~

Nếu lệnh lỗi, kiểm tra cấu hình Spring ở build time và log AOT. Chưa cần kết luận GraalVM compiler có lỗi.

**Bước 3 — biên dịch executable native**

~~~bash
./mvnw -Pnative native:compile
~~~

Kiểm tra `target/`, tên executable và log Native Image. Nếu dự án cấu hình execution `compile-no-fork` ở phase `package` thay vì gọi trực tiếp `native:compile`, dùng:

~~~bash
./mvnw -Pnative package
~~~

Chỉ chọn lệnh thứ hai khi execution đã được bind vào `package`. Không chạy cả hai chỉ vì nghĩ chúng là hai bước bắt buộc.

**Bước 4 — chạy và kiểm tra chức năng**

~~~bash
./target/billing-service
~~~

Tên binary là ví dụ, thay bằng tên file thực tế. Gọi endpoint HTTP và chạy testcase cho resource/reflection/proxy. Nếu binary có tên khác, xem `imageName` và output thực tế.

**Bước 5 — đóng gói container nếu cần**

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Sau đó chạy container theo image name đã cấu hình, kiểm tra port, health endpoint và log. Đây là build image qua Buildpacks; không dùng executable macOS local như thể nó là Linux binary.

## 12. Lỗi cấu hình Maven thường gặp

### `-Pnative` không có tác dụng

Maven có thể vẫn build JAR JVM vì:

- POM không kế thừa `spring-boot-starter-parent` và cũng không tự định nghĩa profile `native`;
- profile tồn tại ở POM khác hoặc chỉ trong settings.xml chưa được kích hoạt;
- plugin/execution native không nằm trong module đang build;
- plugin nằm trong `pluginManagement` nhưng không được khai báo/áp dụng trong `plugins` của module cần build.

Kiểm tra bằng `help:active-profiles` và `help:effective-pom`.

### `native:compile` không tìm thấy goal hoặc plugin

Kiểm tra `org.graalvm.buildtools:native-maven-plugin` có trong cấu hình hiệu lực không, prefix `native` có được Maven nhận diện không và version plugin có tương thích với JDK/GraalVM hiện tại không. Nếu cần, gọi plugin bằng tọa độ đầy đủ hoặc cấu hình plugin theo hướng dẫn của phiên bản Native Build Tools.

### `process-aot` không chạy

Nếu dùng Spring Boot Parent, xác nhận `spring-boot-maven-plugin` được khai báo trong module. Nếu dùng parent riêng, cần tự cấu hình execution `process-aot`. Một profile `native` rỗng không tự sinh mã AOT.

### Native Image chạy nhưng thiếu class hoặc resource

Kiểm tra reachability metadata và runtime hints. Với resource truy cập bằng tên động, xác nhận resource thực sự có trong input và được đăng ký để Native Image đóng gói. Với reflection, khai báo chính xác class/member cần thiết; không dùng cấu hình quá rộng như giải pháp mặc định.

## 13. Ghi nhớ cách chọn lệnh

| Mục tiêu | Lệnh thường dùng | Điều kiện |
| --- | --- | --- |
| Chạy riêng AOT | `./mvnw -Pnative spring-boot:process-aot` | Có Spring Boot Maven Plugin và profile/cấu hình tương ứng |
| Tạo executable trực tiếp | `./mvnw -Pnative native:compile` | Có Native Build Tools plugin và cấu hình Spring AOT phù hợp |
| Build native trong Maven lifecycle | `./mvnw -Pnative package` | Goal `compile-no-fork` đã bind vào phase `package` |
| Tạo container image bằng Buildpacks | `./mvnw -Pnative spring-boot:build-image` | Spring Boot plugin, Buildpacks builder và container engine sẵn sàng |
| Kiểm tra cấu hình profile | `./mvnw help:active-profiles -Pnative` | Maven Help Plugin có sẵn hoặc có thể tải |
| Xem cấu hình sau kế thừa | `./mvnw help:effective-pom -Pnative` | Maven Help Plugin có sẵn hoặc có thể tải |

**Nguyên tắc cuối:** profile chọn cấu hình, goal thực hiện hành động, lifecycle phase quyết định khi nào execution được chạy. Đọc POM hiệu lực trước khi chọn lệnh sẽ giúp xác định Spring AOT đã được nối vào native build hay chưa, tránh nhầm giữa build JAR, executable native và container image.

## Tài liệu tham khảo

- [Spring Boot Maven Plugin — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html): cấu hình `process-aot`, profile `native` của `spring-boot-starter-parent` và tích hợp Native Build Tools.
- [Spring Boot — Developing Your First GraalVM Native Application](https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html): cách build executable, yêu cầu Maven Parent/plugin, goal `native:compile` và Buildpacks.
- [GraalVM Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin.html): cấu hình plugin, goal, metadata và native test.
- [GraalVM Native Build Tools — End-to-End Maven Guide](https://graalvm.github.io/native-build-tools/latest/end-to-end-maven-guide.html): ví dụ plugin, bind `compile-no-fork` vào `package`, build và chạy executable.
