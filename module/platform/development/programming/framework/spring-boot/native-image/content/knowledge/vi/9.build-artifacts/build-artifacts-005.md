# Chuyển JAR đã xử lý AOT bằng Buildpacks hoặc GraalVM Native Image

## 1. Từ JAR chạy JVM đến sản phẩm native

Trong module **SPRING_BOOT_NATIVE_IMAGE**, Spring Boot được xử lý bằng **Spring AOT** rồi biên dịch thành GraalVM Native Image để đánh giá thời gian khởi động, mức dùng bộ nhớ và khả năng vận hành. Một cách tổ chức pipeline hữu ích là tạo **Spring Boot executable JAR đã chứa đầu ra AOT**, lưu JAR làm artifact trung gian trong CI/CD, rồi chuyển artifact đó thành native image ở một bước riêng.

Cách làm này tách hai công việc:

1. **Đóng gói artifact Java trung gian:** biên dịch mã nguồn, chạy AOT và đóng gói JAR chứa generated classes, resource và metadata AOT. JAR vẫn là artifact Java có thể phân phối giữa các máy build.
2. **Chuyển artifact thành native:** dùng Cloud Native Buildpacks để tạo container image có native executable, hoặc dùng GraalVM `native-image` để tạo executable trực tiếp.

Điều kiện bắt buộc là JAR phải có **các tài nguyên AOT đã sinh**, ví dụ generated classes và JSON hint files. Một JAR Spring Boot thông thường chưa chạy AOT không tự trở thành đầu vào native hợp lệ chỉ vì đổi tên file hoặc chạy compiler.

~~~mermaid
flowchart TB
    S["Mã nguồn Spring Boot + dependencies"] --> A["Spring AOT ở build time"]
    A --> J["Executable JAR có generated classes và hints"]
    J --> V["Kiểm tra / chạy thử AOT trên JVM"]
    J --> B["Cloud Native Buildpacks + BP_NATIVE_IMAGE=true"]
    J --> N["Giải nén JAR + GraalVM native-image"]
    B --> C["OCI container image chứa native executable"]
    N --> E["Executable native cho OS/CPU của máy build"]
~~~

Hai nhánh cuối tạo ra **hai loại sản phẩm khác nhau**: Buildpacks tạo container image, còn Native Image trực tiếp tạo executable. Không nên nhầm JAR trung gian với một trong hai sản phẩm này.

## 2. JAR đã xử lý AOT có gì khác JAR thông thường?

Một Spring Boot executable JAR thường chứa:

- `BOOT-INF/classes`: bytecode và resource của ứng dụng;
- `BOOT-INF/lib`: các dependency JAR;
- `META-INF`: manifest và metadata;
- các asset bổ sung do AOT tạo ra, gồm mã khởi tạo, bytecode hỗ trợ proxy và reachability hints khi cần.

Spring AOT phân tích cấu hình Spring trong build time, tạo mã và metadata cho bean registration/khởi tạo cũng như những hành vi truy cập động mà GraalVM cần. Các asset này phải được đưa vào JAR để bước chuyển đổi phía sau sử dụng được.

| Artifact | Nội dung | Mục đích |
| --- | --- | --- |
| JAR JVM thông thường | Bytecode ứng dụng, dependency, resource | Chạy bằng JVM theo cách thông thường |
| JAR đã xử lý AOT | Nội dung JAR cùng mã/metadata AOT | Kiểm tra AOT trên JVM hoặc dùng làm đầu vào tạo native |
| Native executable | Mã máy được biên dịch cho OS/CPU đích | Chạy trực tiếp, không cần JVM |
| Native container image | Runtime filesystem và native executable bên trong image | Triển khai bằng Docker/container runtime |

**AOT JAR vẫn là JAR chạy trên JVM.** Để kiểm tra mã AOT sinh ra trước khi tốn thời gian native compilation, có thể chạy:

~~~bash
java -Dspring.aot.enabled=true -jar target/myproject-0.0.1-SNAPSHOT.jar
~~~

JAR phải được đóng gói có đầu ra AOT. Nếu ứng dụng khởi động thành công trong chế độ này, ta có thêm bằng chứng rằng generated initialization code hoạt động. Bước này **chưa chứng minh** mọi reflection, resource, serialization hay proxy đều tương thích với GraalVM Native Image.

## 3. Tạo executable JAR có AOT

### 3.1. Maven với Spring Boot Parent

Nếu dự án dùng `spring-boot-starter-parent`, profile `native` của Spring Boot có thể cấu hình việc chạy `process-aot` và các thiết lập cần thiết cho native build. Module ứng dụng cần khai báo Spring Boot Maven Plugin và Native Build Tools plugin phù hợp.

Ví dụ phần plugin trong `pom.xml`:

~~~xml
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

Tạo JAR đã xử lý AOT:

~~~bash
./mvnw -Pnative package
~~~

Trong trường hợp này, mục đích của bước `package` là tạo JAR có asset AOT để chuyển tiếp. Đừng nhầm lệnh này với `native:compile`: lệnh sau gọi Native Image để biên dịch executable trực tiếp. Nếu POM không dùng Spring Boot Parent, phải tự cấu hình execution `process-aot` và các plugin/lifecycle tương ứng.

### 3.2. Kiểm tra asset bên trong JAR

Sau khi build, xác định đúng file JAR ở `target/`. Có thể liệt kê nội dung:

~~~bash
jar tf target/myproject-0.0.1-SNAPSHOT.jar
~~~

Tìm các đường dẫn liên quan:

~~~bash
jar tf target/myproject-0.0.1-SNAPSHOT.jar | grep -E 'BOOT-INF/classes|BOOT-INF/lib|META-INF/native-image'
~~~

Tên và số lượng file cụ thể tùy ứng dụng và plugin. Cần xác minh JAR có generated classes/resources AOT và hint metadata cần thiết. Không nên chỉ kiểm tra rằng file JAR tồn tại hoặc dung lượng lớn hơn JAR cũ.

### 3.3. Lưu ý cấu hình build time

Trong quá trình AOT, Spring chuẩn bị bean graph và đánh giá các điều kiện cấu hình. Vì thế, profile Spring, property hoặc environment variable làm thay đổi việc tạo bean cần được đặt đúng **ngay khi tạo JAR AOT**.

Ví dụ, nếu `@ConditionalOnProperty` khiến một bean không được đăng ký khi chạy AOT, đổi property ở container runtime không tự sinh lại bean đã vắng mặt. Nếu cần nhiều biến thể bean graph, có thể phải tạo artifact AOT riêng cho từng cấu hình build phù hợp.

Các thuộc tính runtime thông thường như URL, timeout hay credential không mặc nhiên bị cố định chỉ vì dùng AOT. Hãy phân biệt giá trị được đọc khi ứng dụng chạy với giá trị quyết định cấu trúc ApplicationContext trong build time.

## 4. Nhánh một: chuyển JAR thành native container image bằng Buildpacks

### 4.1. Buildpacks làm gì?

**Cloud Native Buildpacks** nhận source hoặc artifact ứng dụng, phát hiện loại ứng dụng, chọn buildpack cần thiết rồi tạo OCI image. Với Spring Boot AOT JAR, Java buildpack có thể được yêu cầu tạo native executable bằng biến môi trường:

`BP_NATIVE_IMAGE=true`

Ưu điểm của cách này:

- Không cần cài GraalVM `native-image` trực tiếp trên máy host; compiler và toolchain phù hợp được cung cấp trong builder.
- Có thể dùng cùng một JAR trung gian để tạo image trong pipeline CI/CD.
- Đầu ra đã là container image có thể chạy bằng Docker hoặc nền tảng container tương thích.

Bạn vẫn cần **Docker daemon** truy cập được và cài CLI `pack` nếu chọn cách gọi Buildpacks trực tiếp.

### 4.2. Build container image từ JAR có sẵn bằng pack

Giả sử JAR đã xử lý AOT là:

~~~text
target/myproject-0.0.1-SNAPSHOT.jar
~~~

Với Spring Boot 4.2, tài liệu hiện hành dùng builder/run image Ubuntu Resolute và yêu cầu build artifact bằng ít nhất **JDK 25** cho đường chuyển đổi Buildpacks này. Cần kiểm tra builder tương thích với phiên bản Spring Boot, Java và nền tảng triển khai của dự án.

~~~bash
pack build --builder paketobuildpacks/ubuntu-resolute-builder --run-image paketobuildpacks/ubuntu-resolute-run-tiny --path target/myproject-0.0.1-SNAPSHOT.jar --env 'BP_NATIVE_IMAGE=true' my-application:0.0.1-SNAPSHOT
~~~

Giải thích:

| Thành phần | Vai trò |
| --- | --- |
| `pack build` | Bắt đầu quy trình Cloud Native Buildpacks |
| `--builder` | Chọn builder image có buildpack/toolchain để build |
| `--run-image` | Chọn image nền cho giai đoạn chạy, tương thích với builder |
| `--path` | Đường dẫn JAR đã xử lý AOT |
| `BP_NATIVE_IMAGE=true` | Yêu cầu Java buildpack tạo native executable |
| `my-application:0.0.1-SNAPSHOT` | Tên và tag OCI image đầu ra |

Buildpacks tạo image bằng môi trường builder, vì vậy **không cần cài GraalVM Native Image trên host**. Tuy nhiên, Docker phải có đủ CPU/RAM/disk để chạy native compilation; build có thể mất nhiều thời gian hơn đóng gói JAR thông thường.

Sau khi build xong, chạy container:

~~~bash
docker run --rm -p 8080:8080 my-application:0.0.1-SNAPSHOT
~~~

Kiểm tra log khởi động, health endpoint và API nghiệp vụ. Tên image, port và endpoint cần thay theo cấu hình thực tế.

### 4.3. Dùng Spring Boot Maven Plugin thay cho pack

Nếu muốn Spring Boot Maven Plugin điều phối việc build container từ project, có thể dùng:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Với profile native được cấu hình theo Spring Boot Parent, plugin thiết lập môi trường để Buildpacks tạo native image. Đây là cách thuận tiện cho pipeline Maven thông thường.

Phân biệt hai tình huống:

- `pack build --path target/app.jar` là cách **chuyển trực tiếp JAR đã có** thành image.
- `spring-boot:build-image` là goal tích hợp với Maven lifecycle/project để tạo image từ artifact mà plugin build ra.

Nếu yêu cầu là lưu JAR làm artifact bất biến rồi chuyển nó ở một job CI/CD riêng, `pack` với `--path` thể hiện ranh giới artifact rõ hơn. Nếu muốn một lệnh Maven điều phối build và đóng gói từ project, dùng `spring-boot:build-image`.

## 5. Nhánh hai: chuyển JAR thành executable bằng GraalVM native-image

### 5.1. Vì sao phải giải nén JAR?

Spring Boot executable JAR sử dụng cấu trúc nested JAR riêng: lớp ứng dụng thường ở `BOOT-INF/classes`, dependency ở `BOOT-INF/lib`. GraalVM `native-image` cần classpath gồm thư mục/class và từng dependency JAR để phân tích reachability.

Vì vậy, không nên giả định rằng lệnh:

~~~bash
native-image -jar target/myproject-0.0.1-SNAPSHOT.jar
~~~

sẽ xử lý đúng định dạng executable JAR đã được Spring Boot repackaged. Hãy giải nén JAR, dựng classpath từ `BOOT-INF/classes` và **liệt kê từng JAR trong `BOOT-INF/lib`**. Native Image không hỗ trợ wildcard classpath theo cách có thể thay thế việc liệt kê các dependency trong trường hợp này.

### 5.2. Yêu cầu môi trường

Nhánh này cần:

- Một GraalVM distribution có `native-image` phù hợp với Java version dùng để build ứng dụng.
- Compiler, linker, SDK và toolchain hệ điều hành theo yêu cầu của GraalVM.
- JDK/JAR tool để giải nén và kiểm tra artifact.
- Máy build có đủ RAM/CPU cho Native Image compilation.

Kiểm tra trước:

~~~bash
java -version
native-image --version
~~~

Khác với Buildpacks, nhánh này **dùng Native Image cài trên máy build**. Executable tạo ra gắn với OS/CPU của môi trường native compilation; GraalVM Native Image không phải công cụ cross-compile tổng quát để đổi tùy ý từ macOS sang Linux hay từ x86_64 sang ARM64.

### 5.3. Giải nén JAR và dựng classpath

Ví dụ dưới đây dành cho Bash trên Linux/macOS. Giả sử artifact là `target/myproject-0.0.1-SNAPSHOT.jar` và ta muốn tạo binary tên `myproject`:

~~~bash
set -euo pipefail

# Tạo thư mục làm việc mới bên trong target, tránh trộn với lần giải nén cũ.
WORK_DIR="$(mktemp -d target/native-work.XXXXXX)"
(
    cd "$WORK_DIR"
    jar -xf ../myproject-0.0.1-SNAPSHOT.jar

    # Native Image cần liệt kê từng dependency JAR; không dùng BOOT-INF/lib/*
    LIB_CP="$(find BOOT-INF/lib -name '*.jar' -print | paste -sd ':' -)"
    APP_CP=".:BOOT-INF/classes"

    # argfile có thể không được đóng gói nếu không cần override metadata.
    if [ -f META-INF/native-image/argfile ]; then
        native-image -H:Name=myproject @META-INF/native-image/argfile -cp "$APP_CP:$LIB_CP"
    else
        native-image -H:Name=myproject -cp "$APP_CP:$LIB_CP"
    fi

    mv myproject ../myproject-native
)
~~~

Giải thích:

1. `jar -xf` giải nén executable JAR vào thư mục làm việc.
2. `BOOT-INF/classes` cung cấp bytecode và resource ứng dụng.
3. `find` liệt kê từng dependency JAR; `paste` ghép chúng thành classpath phân cách bằng dấu hai chấm trên Linux/macOS.
4. Nếu JAR có `META-INF/native-image/argfile`, nội dung file được truyền cho Native Image như argument file. File này **không phải lúc nào cũng tồn tại**; chỉ thêm khi nó thực sự được đóng gói.
5. `-H:Name` đặt tên executable đầu ra. Kết quả được chuyển lên `target/myproject-native`.

Không dùng wildcard như `BOOT-INF/lib/*` để thay thế danh sách dependency: tùy chọn `-cp` của Native Image cần các entry được liệt kê rõ. Với Windows, phải điều chỉnh separator classpath, lệnh tìm file và cú pháp Bash; có thể dùng PowerShell hoặc script riêng phù hợp.

### 5.4. Kiểm tra và chạy executable

Sau khi lệnh kết thúc thành công:

~~~bash
file target/myproject-native
./target/myproject-native
~~~

`file` giúp xác nhận loại binary và kiến trúc được tạo. Chạy executable trên hệ điều hành/kiến trúc tương thích, sau đó kiểm tra endpoint, resource, serialization, reflection và proxy ở các luồng nghiệp vụ thật.

Nếu build bằng macOS, binary tạo ra là executable macOS; không thể chép nguyên file Mach-O đó vào Linux container rồi chạy. Muốn có Linux native binary, hãy build trong môi trường Linux hoặc builder Linux phù hợp với kiến trúc triển khai.

## 6. So sánh hai cách chuyển đổi

| Tiêu chí | Buildpacks từ JAR | GraalVM native-image trực tiếp |
| --- | --- | --- |
| Đầu vào | AOT executable JAR | AOT executable JAR đã giải nén |
| Công cụ chính | `pack`, Docker daemon, builder/run image | GraalVM distribution và `native-image` local |
| Cài GraalVM trên host | Không bắt buộc | Bắt buộc có Native Image |
| Đầu ra | OCI container image | Native executable |
| Toolchain native | Nằm trong builder image | Nằm trong môi trường máy build |
| Kiểm soát môi trường | Thông qua builder, run image, buildpack env | Trực tiếp qua GraalVM, compiler và tham số |
| Tính phù hợp | Pipeline triển khai container | Cần binary độc lập hoặc muốn kiểm soát native compilation |
| Nền tảng đầu ra | Nền tảng của builder/target được cấu hình | OS/CPU của môi trường native compilation |

**Cả hai đều cần AOT assets.** Buildpacks không tự biến một JAR JVM thông thường thành Spring AOT JAR; Native Image cũng không tự suy ra toàn bộ bean graph và metadata Spring còn thiếu.

## 7. Xử lý reflection, resource và metadata sau khi chuyển JAR

Một JAR đã xử lý AOT có thể chứa hints Spring sinh ra, nhưng không phải mọi hành vi động của ứng dụng đều được phát hiện. Những tình huống thường cần rà soát:

- Reflection tạo lớp/constructor/method từ tên lấy trong cấu hình.
- Resource được tìm bằng tên hoặc pattern tạo động.
- Serialization/deserialization của kiểu dữ liệu mà framework không tự suy ra.
- JDK dynamic proxy hoặc proxy dựa trên class.
- JNI hoặc dependency có thao tác native riêng.

Có thể dùng `RuntimeHintsRegistrar` và `@ImportRuntimeHints` để khai báo chính xác:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ReportHints.class)
class ReportConfiguration {
}

class ReportHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("reports/*.txt");
        hints.reflection().registerType(
            CsvReportFormatter.class,
            org.springframework.aot.hint.MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
    }
}
~~~

Ví dụ đăng ký resource và constructor reflection cho một implementation cụ thể. Cần thay tên class/pattern bằng nhu cầu thật; không nên đăng ký toàn bộ classpath hoặc mọi thành viên của mọi kiểu nếu không cần.

Nếu thiếu metadata, lỗi có thể chỉ xuất hiện khi chạy native executable, dù JAR AOT chạy trên JVM vẫn thành công. Có thể dùng GraalVM tracing agent trên JVM để quan sát các nhánh truy cập động, sau đó rà soát và đưa hint cần thiết vào source/resource của ứng dụng trước lần build tiếp theo.

## 8. Kiểm thử theo từng tầng artifact

Nên kiểm tra theo thứ tự để biết lỗi phát sinh ở đâu:

| Tầng | Cách kiểm tra | Điều được xác nhận |
| --- | --- | --- |
| JAR tồn tại | `ls target/*.jar` hoặc liệt kê thư mục | Build tạo artifact |
| AOT assets | `jar tf app.jar`, tìm generated classes và native metadata | JAR có đầu ra AOT cần thiết |
| JVM AOT mode | `java -Dspring.aot.enabled=true -jar app.jar` | Generated initialization code có thể chạy trên JVM |
| Buildpacks | `pack build ... BP_NATIVE_IMAGE=true` | Builder tạo được container image native |
| Native Image | Chạy `native-image` và kiểm tra exit code | Compiler tạo được executable |
| Runtime native | Chạy binary hoặc container, gọi endpoint và nghiệp vụ | Binary hoạt động đúng trong môi trường đích |

Một bộ kiểm thử tối thiểu nên bao gồm:

1. Health endpoint và một endpoint nghiệp vụ chính.
2. JSON binding/serialization với DTO thực tế.
3. Đọc template/resource trên classpath.
4. Luồng có reflection, proxy hoặc thư viện tích hợp quan trọng.
5. Kết nối database/broker hoặc dịch vụ ngoài nếu ứng dụng sử dụng.
6. Profile/cấu hình đã được chọn ở build time và giá trị cấu hình runtime.

JVM AOT mode giúp kiểm tra nhanh đầu ra Spring AOT nhưng không thay thế native test. Native compilation có thể tốn nhiều thời gian và RAM, vì vậy hãy chạy bộ test JVM rộng trước rồi tập trung native test vào những vùng có khác biệt.

## 9. Lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Buildpacks báo không nhận diện ứng dụng | JAR không đúng định dạng executable hoặc buildpack không nhận artifact | Xác nhận JAR Boot executable, builder và đường dẫn `--path` |
| Buildpacks tạo JVM image thay vì native | Thiếu `BP_NATIVE_IMAGE=true` hoặc builder không hỗ trợ cấu hình | Kiểm tra env của buildpack và log detect/build |
| Builder build native thất bại do version Java | JDK trong JAR không đáp ứng yêu cầu builder/native-image hiện tại | Kiểm tra yêu cầu JDK của Spring Boot/builder; với Boot 4.2, xem yêu cầu JDK 25 |
| Native Image báo thiếu class | Classpath giải nén thiếu dependency hoặc lớp không được giữ lại | Kiểm tra `BOOT-INF/classes`, danh sách `BOOT-INF/lib` và reachability |
| Native Image báo không tìm thấy argfile | JAR không chứa `META-INF/native-image/argfile` | Chỉ truyền argfile khi file thực sự tồn tại |
| JAR chạy JVM AOT nhưng native lỗi reflection | Thiếu reflection hints cho đường truy cập động | Bổ sung runtime hints hoặc metadata đúng thành viên |
| Native không đọc được template | Resource chưa được đóng gói vào image | Kiểm tra resource đầu vào và resource hints |
| Binary chạy trên máy build nhưng không chạy ở container | Binary sai OS/CPU hoặc thiếu thư viện hệ thống | Dùng artifact được build cho Linux và đúng kiến trúc |
| Build native hết RAM hoặc quá lâu | Native compilation tốn tài nguyên | Tăng CPU/RAM cho host/builder, loại dependency không cần và theo dõi log compiler |

## 10. Pipeline CI/CD: giữ JAR làm artifact trung gian

Một pipeline thực tế có thể tách thành hai job:

~~~mermaid
flowchart LR
    C["CI: compile + test"] --> A["AOT + package"]
    A --> J["Lưu AOT JAR"]
    J --> R["CD: nhận đúng JAR đã lưu"]
    R --> B["Buildpacks hoặc native-image"]
    B --> T["Native smoke / integration tests"]
    T --> P["Publish container image hoặc executable"]
~~~

**Job tạo JAR:**

~~~bash
./mvnw test
./mvnw -Pnative package
jar tf target/myproject-0.0.1-SNAPSHOT.jar
~~~

Lưu đúng file JAR đã xác minh vào artifact repository/CI artifact storage cùng checksum, version ứng dụng và thông tin commit.

**Job chuyển bằng Buildpacks:**

~~~bash
pack build --builder paketobuildpacks/ubuntu-resolute-builder --run-image paketobuildpacks/ubuntu-resolute-run-tiny --path target/myproject-0.0.1-SNAPSHOT.jar --env 'BP_NATIVE_IMAGE=true' registry.example.com/myproject:0.0.1
~~~

**Hoặc job chuyển bằng GraalVM Native Image:** tải đúng JAR, giải nén, dựng classpath và chạy `native-image` như ví dụ ở phần 5. Chọn môi trường build phù hợp với OS/CPU muốn phát hành.

Ưu điểm của cách tách này:

- Có thể kiểm tra và lưu JAR AOT trước khi bước native bắt đầu.
- Nếu native compilation thất bại vì thiếu tài nguyên, không cần chạy lại compile/test/AOT khi đầu vào không đổi.
- Có thể dùng cùng một JAR AOT để tạo các sản phẩm theo kiến trúc khác nhau bằng builder/runner tương ứng, nhưng mỗi lần vẫn phải biên dịch native trên nền tảng đích phù hợp vì Native Image không cross-compile tùy ý.
- Dễ truy vết checksum JAR đầu vào, phiên bản builder, GraalVM và image đầu ra.

## 11. Đánh giá sản phẩm sau build

Không chỉ kiểm tra build thành công. Cần đo và ghi nhận:

| Chỉ số | Cách đo/ghi nhận |
| --- | --- |
| Thời gian tạo JAR AOT | Thời gian từ compile đến package |
| Thời gian native compilation | Thời gian riêng của Buildpacks hoặc Native Image |
| Kích thước JAR | Dung lượng artifact trung gian |
| Kích thước native executable | Dung lượng file binary nếu dùng native-image trực tiếp |
| Kích thước container image | Dung lượng OCI image do Buildpacks tạo |
| Thời gian sẵn sàng phục vụ | Đo từ lúc start đến khi health endpoint sẵn sàng |
| RSS/bộ nhớ | Đo trên cùng giới hạn container và tải |
| Độ trễ/thông lượng | Dùng cùng dữ liệu, request và kịch bản |
| Kết quả tương thích | Ghi pass/fail cho reflection, resource, proxy, serialization và tích hợp |

So sánh công bằng cần giữ nguyên workload, cấu hình, CPU/RAM và môi trường chạy. Không suy ra mức dùng bộ nhớ chỉ từ dung lượng binary hoặc container image. Native thường khởi động nhanh và có thể dùng ít bộ nhớ hơn trong nhiều workload, nhưng hiệu năng tải dài hạn, thông lượng và độ trễ vẫn cần đo.

## 12. Checklist trước khi phát hành

- [ ] JAR là Spring Boot executable JAR và đã chạy Spring AOT.
- [ ] Generated classes, resource và JSON hint cần thiết đã nằm trong JAR.
- [ ] Profile/điều kiện Spring được chọn đúng ở build time.
- [ ] JAR chạy được với `-Dspring.aot.enabled=true` trên JVM.
- [ ] Đã chọn Buildpacks hay GraalVM Native Image theo định dạng sản phẩm cần phát hành.
- [ ] Phiên bản JDK, GraalVM, builder, OS và CPU architecture tương thích.
- [ ] Đã kiểm thử endpoint, resource, reflection, serialization, proxy và luồng nghiệp vụ quan trọng trên native.
- [ ] Đã lưu checksum/version của JAR đầu vào và native artifact/container image đầu ra.
- [ ] Đã đo startup, RSS, độ trễ/thông lượng và thời gian build trên môi trường tương đương.

**Điểm cốt lõi:** JAR đã xử lý AOT là artifact trung gian mang theo mã và metadata mà Spring chuẩn bị. Buildpacks dùng JAR đó để tạo container image native; GraalVM `native-image` dùng classpath được dựng từ JAR để tạo executable trực tiếp. Chọn đúng nhánh, xác minh asset AOT và kiểm thử trên nền tảng đích là ba điều kiện để chuyển đổi có thể lặp lại trong CI/CD.

## Tài liệu tham khảo

- [Spring Boot 4.2 — Converting a Spring Boot Executable Jar](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): yêu cầu JAR có AOT assets, cách chuyển bằng Buildpacks và GraalVM `native-image`.
- [Spring Boot Maven Plugin — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html): goal `process-aot`, thư mục generated classes/resources và profile `native`.
- [Spring Boot — GraalVM Native Image Support](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): tổng quan Native Image, AOT, runtime hints và giới hạn tương thích.
