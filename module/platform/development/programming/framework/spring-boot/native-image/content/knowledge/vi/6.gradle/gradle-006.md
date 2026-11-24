# `nativeRun`, tham số ứng dụng và môi trường thực thi trong Gradle

Khi phát triển một ứng dụng **Spring Boot Native Image**, có hai thời điểm cần phân biệt: **biên dịch** ứng dụng thành executable nhờ **Spring AOT và GraalVM Native Image**, rồi **chạy** executable đó với cấu hình môi trường thực tế. Trong dự án dùng **GraalVM Native Build Tools Gradle plugin**, task `nativeRun` giúp thực hiện bước chạy trực tiếp từ Gradle.

Bài học tập trung vào cách sử dụng `nativeRun`, truyền tham số cho ứng dụng Spring Boot, đặt biến môi trường, đọc kết quả cấu hình và xử lý những khác biệt giữa chế độ native với `bootRun` trên JVM. Đây là bước quan trọng để kiểm thử ứng dụng native trước khi đóng gói container hoặc đưa vào môi trường vận hành.

## 1. `nativeRun` làm gì?

Plugin Gradle `org.graalvm.buildtools.native` cung cấp các task chính:

| Task | Công việc | Kết quả |
|---|---|---|
| `nativeCompile` | Biên dịch ứng dụng thành executable native | Tạo file thực thi trong thư mục output của build |
| **`nativeRun`** | Chạy executable của ứng dụng native | Khởi động và chạy ứng dụng như một tiến trình native |
| `nativeTestCompile` | Biên dịch tập test native theo cấu hình plugin | Tạo executable phục vụ test |
| `nativeTest` | Chạy bài test tương ứng bằng chế độ native | Kết quả test từ native image |

Với cấu hình thông dụng, `nativeRun` phụ thuộc vào đầu ra của `nativeCompile`: nếu chưa có executable hoặc output đã lỗi thời theo mô hình task của Gradle, quá trình build cần thiết sẽ được thực hiện trước khi chạy. Sau khi executable sẵn sàng, task khởi chạy **bản native**, không gọi `java -jar` và không chạy ứng dụng trên HotSpot JVM.

~~~mermaid
flowchart TD
    A["Lệnh: ./gradlew nativeRun"] --> B["Gradle xác định task và dependency"]
    B --> C["Spring AOT + Native Image build khi cần"]
    C --> D["Executable native"]
    D --> E["nativeRun khởi chạy executable"]
    F["runtimeArgs"] --> E
    G["Environment của tiến trình"] --> E
    E --> H["Spring Boot đọc cấu hình runtime"]
    H --> I["ApplicationContext và nghiệp vụ"]
~~~

Sơ đồ mô tả **luồng xử lý**, không có nghĩa Native Image bắt buộc phải build lại từ đầu ở mọi lần gọi `nativeRun`. Tính up-to-date, cache và thay đổi source/build configuration quyết định phần công việc Gradle cần làm lại.

## 2. Điều kiện tiên quyết

Ví dụ trong bài giả định dự án đã có:

- Spring Boot cùng Gradle wrapper (`gradlew` trên Unix hoặc `gradlew.bat` trên Windows).
- GraalVM Native Build Tools Gradle plugin, với cấu hình tương thích phiên bản Spring Boot/Gradle.
- JDK/GraalVM có `native-image` phù hợp với phiên bản và platform đích, được plugin tìm thấy qua toolchain hoặc môi trường.
- Điểm vào chính của ứng dụng (`mainClass`) được xác định chính xác.
- Các thành phần động cần thiết được hỗ trợ bởi Spring AOT và runtime hints phù hợp.

Từ thư mục gốc của dự án:

~~~bash
# Xem các task native mà project đang có
./gradlew tasks --all

# Biên dịch executable native
./gradlew nativeCompile

# Biên dịch khi cần và chạy executable native
./gradlew nativeRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat nativeCompile
.\gradlew.bat nativeRun
~~~

Nếu không thấy task `nativeRun`, trước hết kiểm tra plugin đã được áp dụng cho đúng module Gradle chưa. Với dự án đa module, có thể phải chỉ rõ task bằng đường dẫn, ví dụ `:server:nativeRun` khi module `server` thực sự được cấu hình native plugin.

**Điểm cần nhớ:** `nativeRun` phục vụ chạy cục bộ hoặc trong môi trường kiểm thử. Để phát hành, thường sử dụng executable đã build, package/distribution hoặc container image phù hợp, thay vì yêu cầu máy production chạy Gradle.

## 3. `nativeRun` khác `bootRun` và `run` ra sao?

Spring Boot Gradle plugin thường cung cấp `bootRun` để chạy ứng dụng trên JVM. Application plugin của Gradle có thể cung cấp task `run`. GraalVM Native Build Tools cung cấp `nativeRun` để chạy native executable.

| Đặc điểm | `bootRun` | `run` (Application plugin) | `nativeRun` |
|---|---|---|---|
| Cách chạy | JVM với Spring Boot | JVM, theo cấu hình Application plugin | Executable native đã biên dịch |
| Cần native compilation | Không | Không | Có |
| Mục đích thường gặp | Phát triển Spring Boot nhanh, debug JVM | Chạy Java app thông thường | Kiểm thử hành vi, cấu hình và startup native |
| Tham số ứng dụng | Cấu hình của `BootRun`/`JavaExec`, thường có `--args` | Cấu hình `JavaExec`, thường có `--args` | **`runtimeArgs` của GraalVM Native Build Tools** |
| Tham số JVM | Có ý nghĩa đối với JVM thực thi app | Có ý nghĩa đối với JVM thực thi app | Không có JVM HotSpot chạy app theo cách đó |

Đừng mặc định cú pháp:

~~~bash
# Cú pháp --args quen thuộc của bootRun/run
./gradlew bootRun --args="--server.port=9091"
~~~

có thể được sao chép nguyên sang `nativeRun`. `NativeRunTask` không phải `JavaExec`; tài liệu plugin công bố **`runtimeArgs`** làm cơ chế cấu hình tham số của binary. Với tham số chỉ dùng một lần, có thể cấp giá trị thông qua Gradle property được ánh xạ vào `runtimeArgs`, hoặc chạy executable trực tiếp (các cách trình bày phía dưới).

## 4. Phân biệt ba lớp tham số

Khi gọi Gradle, cần xác định **tham số thuộc tiến trình nào**.

| Loại | Ví dụ | Nơi tiếp nhận | Mục đích |
|---|---|---|---|
| **Gradle CLI/task** | `--info`, `--stacktrace`, `-PdemoPort=9091` | Gradle | Log, project property, điều khiển build |
| **Native Image build arguments** | `--no-fallback` hoặc tùy chọn compiler tương ứng | Trình `native-image` khi biên dịch | Ảnh hưởng executable được tạo |
| **Application runtime arguments** | `--server.port=9091`, `--demo.message=hello` | Spring Boot bên trong executable native | Điều chỉnh hành vi ứng dụng khi chạy |
| **Biến môi trường runtime** | `SERVER_PORT=9091`, `DEMO_MESSAGE=hello` | Tiến trình native và Spring Environment | Cấu hình phụ thuộc nơi chạy |
| **Native runtime flags** | Tùy chọn runtime hỗ trợ bởi phiên bản GraalVM | Native executable | Điều chỉnh một số đặc tính runtime của native image |

Một vài nhầm lẫn phổ biến:

- `./gradlew nativeRun --info` bật **log của Gradle**; không đồng nghĩa Spring Boot bật chế độ `--debug`.
- `-PdemoPort=9091` tạo **Gradle project property**; nó chỉ tác động đến ứng dụng nếu build script dùng giá trị đó để cấu hình runtime.
- `-Dspring.profiles.active=dev` đặt trên lệnh Gradle có thể nhắm vào JVM chạy Gradle; không nên coi đó là cách truyền system property tới native executable.
- `org.gradle.jvmargs` và `GRADLE_OPTS` áp dụng cho Gradle/JVM liên quan, không phải một lối cấu hình heap HotSpot cho ứng dụng native.
- `buildArgs` và `runtimeArgs` là hai nhóm cấu hình khác nhau. Tham số `--server.port` thuộc **runtimeArgs**.

## 5. Cấu hình `runtimeArgs` trong `build.gradle` (Groovy DSL)

Giả sử ứng dụng có các thuộc tính Spring Boot `server.port` và `demo.message`. Với dự án đã áp dụng plugin Native Build Tools, thêm vào `build.gradle`:

~~~groovy
graalvmNative {
    binaries {
        main {
            // Mỗi phần tử là một đối số của executable.
            runtimeArgs.add("--server.port=9091")
            runtimeArgs.add("--demo.message=hello-from-native")
        }
    }
}
~~~

Sau đó chạy:

~~~bash
./gradlew nativeRun
~~~

Gradle sẽ chạy executable native với các đối số ứng dụng tương đương:

~~~text
<native-executable> --server.port=9091 --demo.message=hello-from-native
~~~

Hai giá trị trên được Spring Boot phân tích như **command-line properties** nếu ứng dụng dùng cơ chế xử lý arguments mặc định của Spring Boot. Ví dụ `--server.port=9091` thay cổng HTTP khi ứng dụng là web server và không có mã tùy biến ngăn xử lý đối số.

Có thể dùng `runtimeArgs.addAll` để cấu hình nhiều đối số:

~~~groovy
graalvmNative {
    binaries {
        main {
            runtimeArgs.addAll(
                "--server.port=9091",
                "--demo.message=hello-from-native"
            )
        }
    }
}
~~~

Mỗi phần tử của danh sách là **một đối số riêng**. Ví dụ, không nên ghi hai đối số cách nhau bởi khoảng trắng trong cùng một chuỗi rồi kỳ vọng plugin tự phân tách chúng như shell.

## 6. Cấu hình trong `build.gradle.kts` (Kotlin DSL)

Nếu dự án dùng Kotlin DSL, cấu hình tương đương:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            runtimeArgs.add("--server.port=9091")
            runtimeArgs.add("--demo.message=hello-from-native")
        }
    }
}
~~~

Khi cần nhiều đối số:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            runtimeArgs.addAll(
                "--server.port=9091",
                "--demo.message=hello-from-native"
            )
        }
    }
}
~~~

Trong cả hai DSL, `main` đại diện cấu hình binary ứng dụng chính của plugin. Cấu hình `runtimeArgs` tác động đến cách plugin chạy image; **không tự nhúng `server.port=9091` thành giá trị cố định bên trong executable**. Khi chạy executable ở môi trường khác, cần truyền đối số hoặc biến môi trường tương ứng tại nơi đó.

## 7. Truyền giá trị linh hoạt bằng Gradle project property

Không nên sửa `build.gradle` cho mỗi lần muốn đổi cổng thử nghiệm. Có thể **ánh xạ** project property sang runtime argument.

Trong `build.gradle` (Groovy DSL):

~~~groovy
graalvmNative {
    binaries {
        main {
            // Giá trị chỉ được chuyển đến executable vì ta đã ánh xạ rõ ràng.
            runtimeArgs.add(
                providers.gradleProperty("demoPort")
                    .map { port -> "--server.port=" + port }
                    .orElse("--server.port=8080")
            )
        }
    }
}
~~~

Chạy lần lượt:

~~~bash
# Dùng giá trị mặc định 8080 từ cấu hình mẫu
./gradlew nativeRun

# Dùng giá trị 9092
./gradlew nativeRun -PdemoPort=9092
~~~

Trong `build.gradle.kts` (Kotlin DSL), ý tưởng tương tự:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            runtimeArgs.add(
                providers.gradleProperty("demoPort")
                    .map { port -> "--server.port=" + port }
                    .orElse("--server.port=8080")
            )
        }
    }
}
~~~

`-PdemoPort` chỉ có tác dụng vì **build script đã đọc thuộc tính đó và thêm đối số vào `runtimeArgs`**. Nếu không có ánh xạ này, Gradle property không tự động xuất hiện trong đối số ứng dụng.

**Lưu ý bảo mật:** Chỉ dùng ví dụ `-P` cho giá trị không nhạy cảm như cổng hoặc tên chế độ test. Không đưa password, access token hoặc credential vào command line/project property được log và lưu trong lịch sử shell; ưu tiên cơ chế secret của runtime/CI và các kho bí mật phù hợp.

## 8. Chạy executable trực tiếp để truyền đối số một lần

Khi đã build xong, cách dễ nhất để thử các tham số khác nhau là **chạy file native trực tiếp**. Với cấu hình Gradle plugin thông dụng, executable chính nằm dưới `build/native/nativeCompile/`.

~~~bash
./gradlew nativeCompile

# Thay my-app bằng tên image thực tế trong thư mục build/native/nativeCompile/
./build/native/nativeCompile/my-app --server.port=9093 --demo.message=direct
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat nativeCompile

# Thay my-app.exe bằng tên executable đã tạo.
.\build\native\nativeCompile\my-app.exe --server.port=9093 --demo.message=direct
~~~

Tên file phụ thuộc `imageName`, cấu hình plugin và hệ điều hành. Windows thường sinh file `.exe`. Với cấu hình custom output, hãy xem kết quả task `nativeCompile` thay vì cố định đường dẫn trên.

**Ưu điểm:** thay đổi tham số nhiều lần mà không cần cấu hình lại Gradle, dễ quan sát hành vi runtime giống khi triển khai executable.

**Giới hạn:** quá trình chạy trực tiếp không qua logic chuẩn bị môi trường riêng đã khai báo cho task `nativeRun` trong Gradle; bạn phải tự cung cấp biến môi trường, thư mục làm việc và những file cần thiết.

## 9. Biến môi trường khi chạy `nativeRun`

Spring Boot có thể đọc cấu hình từ **environment variables** thông qua `Spring Environment`. Ví dụ phổ biến:

| Biến môi trường | Thuộc tính Spring Boot tương ứng | Tác dụng |
|---|---|---|
| `SERVER_PORT` | `server.port` | Đổi cổng web server |
| `SPRING_PROFILES_ACTIVE` | `spring.profiles.active` | Chọn active profile theo cơ chế cấu hình |
| `LOGGING_LEVEL_ROOT` | `logging.level.root` | Đặt mức logging gốc |
| `DEMO_MESSAGE` | `demo.message` | Cấu hình tùy biến nếu ứng dụng có đọc thuộc tính đó |

Quy tắc Spring Boot thường dùng khi chuyển tên property sang environment variable là đổi dấu chấm thành dấu gạch dưới, bỏ dấu gạch nối rồi viết hoa. Với những property có cấu trúc phức tạp, hãy kiểm tra cách binding và định dạng phù hợp.

### Linux và macOS

~~~bash
# Hai biến chỉ được đặt cho lệnh này.
SERVER_PORT=9094 DEMO_MESSAGE=from-env ./gradlew nativeRun
~~~

Nếu cần chọn profile:

~~~bash
SPRING_PROFILES_ACTIVE=local ./gradlew nativeRun
~~~

Cách đặt trên truyền biến vào tiến trình Gradle. Tiến trình con do Gradle khởi chạy thường kế thừa môi trường đó, trừ khi task hoặc runner có cấu hình ghi đè.

### Windows PowerShell

~~~powershell
$env:SERVER_PORT = "9094"
$env:DEMO_MESSAGE = "from-env"

.\gradlew.bat nativeRun

# Xóa hai giá trị chỉ phục vụ thử nghiệm khỏi phiên PowerShell hiện tại.
Remove-Item Env:SERVER_PORT
Remove-Item Env:DEMO_MESSAGE
~~~

Trước khi xóa, cần lưu lại giá trị cũ nếu những biến đó đã tồn tại và còn được ứng dụng khác trong shell sử dụng. Các lệnh `Remove-Item` ở đây dành cho phiên thử nghiệm không có giá trị trước đó.

### Khi chạy executable trực tiếp

~~~bash
SERVER_PORT=9094 DEMO_MESSAGE=from-env \
  ./build/native/nativeCompile/my-app
~~~

Không cần chạy Gradle nếu executable đã được build và mọi dependency runtime bên ngoài đã sẵn sàng.

## 10. Cấu hình environment riêng cho task `nativeRun`

GraalVM Native Build Tools cung cấp thuộc tính `environment` trên `NativeRunTask`. Có thể đặt biến môi trường cho **tiến trình được task chạy**, thay vì phụ thuộc hoàn toàn vào shell.

Với Groovy DSL:

~~~groovy
import org.graalvm.buildtools.gradle.tasks.NativeRunTask

tasks.named("nativeRun", NativeRunTask) {
    environment.put("DEMO_MESSAGE", "from-native-run-task")
    environment.put("SERVER_PORT", "9095")
}
~~~

Với Kotlin DSL:

~~~kotlin
import org.graalvm.buildtools.gradle.tasks.NativeRunTask

tasks.named<NativeRunTask>("nativeRun") {
    environment.put("DEMO_MESSAGE", "from-native-run-task")
    environment.put("SERVER_PORT", "9095")
}
~~~

Các ví dụ này đặt biến **cho lần chạy do Gradle quản lý**, không tạo thành cấu hình mặc định cố định trong binary. Chúng giả định phiên bản Native Build Tools đang dùng có API `NativeRunTask.environment`, như các bản plugin hiện đại. Nếu một phiên bản plugin cũ dùng API khác, hãy kiểm tra tài liệu API đúng phiên bản.

Không hardcode secret trong `build.gradle` hoặc `build.gradle.kts`. Với dữ liệu nhạy cảm, nên sử dụng biến được cấp từ hệ thống triển khai hoặc CI secret store và chỉ tham chiếu giá trị khi thực sự cần.

## 11. Thứ tự ưu tiên cấu hình Spring Boot

Khi cùng một Spring property xuất hiện ở nhiều nguồn, **nguồn có độ ưu tiên cao hơn sẽ thắng**. Trong cấu hình Spring Boot mặc định, command-line property dạng `--server.port=... ` có độ ưu tiên cao hơn system environment và nhiều nguồn cấu hình file thông thường.

Ví dụ:

~~~text
application.properties:
    server.port=8080

Environment:
    SERVER_PORT=9094

Runtime arguments:
    --server.port=9096

Cổng ứng dụng kỳ vọng:
    9096
~~~

Nếu bỏ runtime argument `--server.port=9096`, môi trường với `SERVER_PORT=9094` sẽ điều khiển cổng trong trường hợp không có một nguồn cấu hình khác có độ ưu tiên cao hơn can thiệp.

Một ví dụ kiểm tra với CLI:

~~~bash
# Nếu nativeRun được cấu hình runtimeArgs chứa --server.port=9096,
# giá trị SERVER_PORT=9094 có thể bị đối số CLI ghi đè.
SERVER_PORT=9094 ./gradlew nativeRun
~~~

Lưu ý rằng thứ tự ưu tiên còn có các nguồn khác như system properties, `SPRING_APPLICATION_JSON` và test configuration. Với nhu cầu chẩn đoán, hãy xem property sources thực tế thay vì mặc định mọi nguồn có cùng mức ưu tiên.

Để tránh rối, nên chọn **một cách chính** cấu hình cùng một thuộc tính trong mỗi môi trường kiểm thử, và ghi lại khi chủ động thử nghiệm precedence.

## 12. Thực hành quan sát runtime bằng một endpoint

Có thể tạo endpoint chỉ dùng cho bài học để xem bản native đọc đúng thuộc tính chưa:

~~~java
package example.nativeapp;

import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class RuntimeProbeController {
    private final Environment environment;

    RuntimeProbeController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/runtime-info")
    Map<String, String> runtimeInfo() {
        return Map.of(
            "message", environment.getProperty("demo.message", "unset"),
            "serverPort", environment.getProperty("server.port", "8080")
        );
    }
}
~~~

Đoạn mã giả định dự án có Spring Web. Sau khi build native, thử:

~~~bash
# Trường hợp 1: cấu hình runtimeArgs cho cổng 9091 và message trong build.gradle.
./gradlew nativeRun
~~~

Trong một terminal thứ hai:

~~~bash
curl http://localhost:9091/runtime-info
~~~

Kết quả minh họa, khi các giá trị trong ví dụ được áp dụng:

~~~json
{
  "message": "hello-from-native",
  "serverPort": "9091"
}
~~~

Tiếp đó, thay cách truyền giá trị bằng environment variables hoặc thực thi binary trực tiếp. Endpoint giúp phân biệt **giá trị ứng dụng đã đọc** với **giá trị người chạy nghĩ mình đã truyền**.

Endpoint này là công cụ học tập; không nên công khai mọi biến môi trường, đường dẫn cấu hình hay secret trong một endpoint vận hành.

## 13. Ranh giới giữa build-time và runtime trong Spring AOT

Ứng dụng Spring Boot Native Image cần biết cấu trúc bean và những khả năng reflection/resource quan trọng ngay khi biên dịch. Trong quá trình Spring AOT, các điều kiện quyết định cấu trúc bean có thể được đánh giá và sinh mã theo **môi trường build**.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class GatewayConfiguration {

    @Bean
    @Profile("dev")
    PaymentGateway devGateway() {
        return new LocalPaymentGateway();
    }

    @Bean
    @Profile("prod")
    PaymentGateway prodGateway() {
        return new RemotePaymentGateway();
    }
}
~~~

Ở đây các kiểu `PaymentGateway`, `LocalPaymentGateway` và `RemotePaymentGateway` giả định đã được khai báo. Nếu cấu trúc bean phụ thuộc profile được xác định trong pha AOT, việc chạy cùng executable với `SPRING_PROFILES_ACTIVE=prod` không mặc nhiên tạo được bean chỉ xuất hiện trong cấu hình AOT của profile khác.

Ngược lại, các giá trị như `server.port`, endpoint URL, timeout và thông báo hiển thị **có thể là cấu hình runtime** khi bean hiện có đọc chúng mà không làm thay đổi các quyết định cấu trúc đã được cố định trong lúc AOT.

~~~mermaid
flowchart TD
    A["Môi trường AOT khi build"] --> B["Quyết định cấu trúc bean và mã sinh"]
    B --> C["nativeCompile: executable"]
    C --> D["nativeRun + CLI args + env"]
    D --> E["Cấu hình runtime của bean đang tồn tại"]
    D -. "Không tự tạo lại cấu trúc AOT đã loại" .-> F["Bean chỉ có trong điều kiện build khác"]
~~~

**Nguyên tắc thực hành:** sử dụng tham số runtime để thay đổi **dữ liệu vận hành**; với property/profile làm thay đổi **tập bean được đăng ký**, phải xác minh khả năng thay đổi đó có được hỗ trợ trong bản image hiện tại hay cần build riêng cho từng cấu hình.

## 14. System property, cấu hình JVM và native runtime

Một native executable có thể hỗ trợ một số đối số dạng `-D` và `-XX` theo quy định của GraalVM Native Image, nhưng không phải mọi HotSpot JVM option đều có ý nghĩa khi chạy native.

So sánh:

~~~bash
# Ví dụ đối số runtime của native executable; hỗ trợ cụ thể tùy GraalVM.
./build/native/nativeCompile/my-app \
  -Ddemo.message=from-system-property \
  --server.port=9091
~~~

~~~bash
# Đối số Gradle/JVM; không nên dùng để truyền config tới app native.
./gradlew nativeRun -Ddemo.message=from-gradle-jvm
~~~

Trường hợp đầu truyền argument cho **native executable**; trường hợp sau đặt property cho **quy trình Gradle**. Để truyền một system property tới native executable thông qua Gradle task, cấu hình nó trong `runtimeArgs` khi phiên bản GraalVM hỗ trợ:

~~~groovy
graalvmNative {
    binaries {
        main {
            runtimeArgs.add("-Ddemo.message=from-native-runtime")
        }
    }
}
~~~

Các cờ quản lý bộ nhớ native, monitoring hoặc chẩn đoán thay đổi theo phiên bản GraalVM. Hãy kiểm tra tài liệu runtime của đúng phiên bản trước khi áp dụng flag. Không sao chép các tùy chọn `-Xmx`, `-XX` hoặc agent của HotSpot sang native mà chưa xác nhận hỗ trợ.

Đặc biệt, `JAVA_TOOL_OPTIONS` vốn dành cho Java launcher/JVM không nên là cơ chế chính để cấu hình một executable native. Với Spring Boot, **application CLI properties và environment variables** thường rõ ràng và dễ vận hành hơn.

## 15. Thư mục làm việc và tài nguyên bên ngoài

Một chương trình native không chỉ nhận đối số và environment: nó còn có **working directory**, quyền trên file và đường dẫn tới resource.

Giả sử ứng dụng mở file với đường dẫn tương đối:

~~~java
Path path = Path.of("config", "rules.json");
String json = Files.readString(path);
~~~

Đường dẫn tương đối được giải quyết theo working directory của **tiến trình chạy**. Khi gọi `nativeRun` qua Gradle, working directory có thể chịu ảnh hưởng của task và Gradle project; khi trực tiếp chạy executable từ một thư mục khác, kết quả có thể thay đổi.

Cách tránh phụ thuộc ngầm là dùng đường dẫn tuyệt đối hoặc truyền đường dẫn như runtime property, ví dụ:

~~~bash
./build/native/nativeCompile/my-app \
  --demo.rules-file=/etc/myapp/rules.json
~~~

Trong mã ứng dụng, đọc cấu hình này từ Spring `Environment` hoặc `@ConfigurationProperties` rồi mở file tương ứng. Đảm bảo file thực sự tồn tại và tài khoản chạy có quyền truy cập.

**Phân biệt file hệ thống với classpath resource:**

- File bên ngoài như `/etc/myapp/rules.json` được đọc tại runtime từ filesystem và phải được cung cấp trong môi trường triển khai.
- Resource đóng gói theo classpath có thể cần được nhận diện qua Spring AOT/runtime hints để được đưa vào native image.
- Tài nguyên nằm trong JAR hoặc `src/main/resources` của nguồn build **không đồng nghĩa** có thể truy cập bằng mọi đường dẫn filesystem tương đối sau khi chuyển thành native executable.

Với Spring Boot, một ví dụ cấp file cấu hình từ bên ngoài bằng CLI là:

~~~bash
./build/native/nativeCompile/my-app \
  --spring.config.additional-location=optional:file:/etc/myapp/
~~~

Tùy môi trường, thay `/etc/myapp/` bằng thư mục thực tế. Prefix `optional:` cho phép ứng dụng không báo lỗi chỉ vì vị trí cấu hình bổ sung đó không tồn tại; nên bỏ `optional:` khi thiếu file phải được xem là lỗi triển khai.

## 16. Điều gì xảy ra khi chạy trong container?

`nativeRun` thường chạy trên build host và được dùng để phát triển hoặc thử nghiệm. Khi đóng gói executable vào container, **container runtime** sẽ cung cấp environment, working directory, file mount và arguments cho tiến trình.

Ví dụ giả định đã có Docker image mang tên `demo-native:local` và entrypoint chạy executable native:

~~~bash
docker run --rm \
  -p 9091:9091 \
  -e SERVER_PORT=9091 \
  -e DEMO_MESSAGE=container \
  demo-native:local
~~~

Ở đây `SERVER_PORT` và `DEMO_MESSAGE` được truyền tới **tiến trình trong container**; không cần đặt chúng trên máy từng chạy `nativeCompile`. Nếu entrypoint/CMD của image định nghĩa các arguments khác, cần kiểm tra chúng có bị ghi đè hay được nối thêm.

Lưu ý rằng những giá trị dùng để xử lý Spring AOT tại build time có thể khác với biến môi trường của container sau khi image đã tạo. Kiểm thử cả hai giai đoạn giúp tránh trường hợp container chạy với profile thay đổi cấu trúc bean mà image không hỗ trợ.

## 17. Xử lý lỗi `nativeRun` thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| `Task 'nativeRun' not found` | Chưa áp dụng đúng native plugin hoặc gọi sai Gradle module | `./gradlew tasks --all`, kiểm tra module và plugin |
| Không tìm được GraalVM/`native-image` | Toolchain/JDK/plugin chưa cấu hình đúng | Xem thông báo build, công cụ đã chọn và `native-image --version` |
| Build lâu trước khi thấy server khởi động | `nativeRun` đang cần biên dịch native executable | Xem log `nativeCompile`, không nhầm với startup time |
| `Unknown command-line option '--args'` | Áp dụng cú pháp của `bootRun`/`run` vào `nativeRun` | Chuyển sang `runtimeArgs` hoặc chạy executable trực tiếp |
| Cổng không đổi dù đã đặt `SERVER_PORT` | `runtimeArgs` hoặc nguồn property ưu tiên cao hơn đang ghi đè | Kiểm tra runtimeArgs và Spring property sources |
| Đổi profile nhưng bean không xuất hiện | Cấu trúc bean đã được AOT quyết định khi build | Kiểm tra môi trường AOT, generated code và điều kiện bean |
| Lỗi binding/serialization chỉ khi chạy native | Thiếu runtime hints/metadata hoặc khác biệt tính năng | Kiểm thử code path và stack trace, bổ sung hint phù hợp |
| Không tìm thấy file JSON/template | Sai working directory, file chưa được mount hoặc thiếu resource hint | Phân biệt filesystem path và classpath resource |
| Cổng đã được sử dụng | Tiến trình khác đang nghe cùng cổng | Chọn cổng khác hoặc dừng tiến trình đang chiếm cổng |
| Dừng `nativeRun` rồi cổng vẫn bị giữ | Tiến trình con chưa kết thúc như mong đợi | Kiểm tra PID/port bằng công cụ hệ điều hành, dừng đúng tiến trình |

Khi điều tra lỗi, nên phân biệt **build failure** (xảy ra trước khi executable chạy), **startup failure** (Spring context không khởi động được) và **runtime failure** (chỉ lỗi khi gọi một tính năng). Mỗi nhóm cần xem log và đầu vào khác nhau.

### Tránh nhầm log Gradle với log ứng dụng

~~~bash
# Chi tiết về task/build của Gradle
./gradlew nativeRun --info
~~~

~~~groovy
// Cấu hình riêng để Spring Boot in thêm thông tin debug ở runtime.
graalvmNative {
    binaries {
        main {
            runtimeArgs.add("--debug")
        }
    }
}
~~~

Hai cách này có mục tiêu khác nhau. Lệnh Gradle `--debug` còn có thể tạo log build rất nhiều; không nên bật theo thói quen trong CI, đặc biệt khi log có thể tiết lộ cấu hình nhạy cảm.

## 18. Quy trình kiểm thử tương thích với `nativeRun`

Một quy trình nhỏ nhưng đủ ý nghĩa nên chạy cùng một tính năng ở JVM và native, với cùng dữ liệu đầu vào:

1. **Baseline JVM:** chạy `bootRun` với cấu hình tương đương, gọi endpoint `/runtime-info` và một nghiệp vụ thực tế.
2. **Build native:** thực thi `nativeCompile`, lưu log và xác nhận executable được tạo.
3. **Chạy native:** dùng `nativeRun`, truyền cùng `demo.message` và `server.port` qua `runtimeArgs` hoặc env.
4. **Đối chiếu:** kiểm tra status HTTP, JSON body, tác động dữ liệu, log và xử lý ngoại lệ.
5. **Thử precedence:** đặt `SERVER_PORT` khác runtime argument để xác nhận nguồn có ưu tiên cao hơn.
6. **Thử file/config:** chạy từ một working directory khác hoặc dùng external config path, quan sát chênh lệch.
7. **Thử kết thúc tiến trình:** dừng ứng dụng và xác nhận port được giải phóng, các tài nguyên được đóng.

Với ứng dụng HTTP, cần tách thời gian **native compilation** khỏi thời gian **khởi động executable**. `./gradlew nativeRun` có thể mất rất lâu ở lần đầu vì phải build; dùng thời gian của toàn bộ task để kết luận thời gian startup sẽ làm sai lệch phép đo. Để đo startup, hãy chạy executable đã biên dịch trong cùng điều kiện và đo từ lúc tiến trình bắt đầu đến khi app sẵn sàng.

## 19. Bài thực hành tổng hợp

Mục tiêu: chứng minh bạn kiểm soát được tham số và môi trường của **cùng một binary native**.

### Phần A — Tham số cố định

Trong `build.gradle` hoặc `build.gradle.kts`, thiết lập:

~~~text
--server.port=9091
--demo.message=from-gradle
~~~

cho `graalvmNative.binaries.main.runtimeArgs`. Chạy `nativeRun` và gọi `/runtime-info`; kỳ vọng thấy cổng và thông báo từ `runtimeArgs`.

### Phần B — Environment

Bỏ `--server.port` khỏi `runtimeArgs`, đặt `SERVER_PORT=9094` trong shell và chạy lại `nativeRun`. Kiểm tra endpoint hoạt động trên cổng 9094. Tiếp đó thêm lại argument `--server.port=9091` và xác nhận cách precedence vận hành.

### Phần C — Gradle property

Ánh xạ `-PdemoPort` tới `runtimeArgs` như phần 7. Lần lượt chạy:

~~~bash
./gradlew nativeRun -PdemoPort=9081
./gradlew nativeRun -PdemoPort=9082
~~~

Dừng tiến trình của lần chạy trước khi khởi động lần chạy sau. Chứng minh rằng hai giá trị cổng là dữ liệu runtime được truyền vào executable qua Gradle.

### Phần D — Chạy trực tiếp

Chạy một executable đã build:

~~~bash
./build/native/nativeCompile/my-app \
  --server.port=9083 \
  --demo.message=direct
~~~

Đối chiếu `/runtime-info` trên cổng 9083 và quan sát điều gì thay đổi khi working directory hoặc environment thay đổi.

### Phần E — Giới hạn của AOT

Nếu ứng dụng có `@Profile` hoặc `@ConditionalOnProperty` quyết định **bean definition** tại build time, hãy so sánh cấu trúc bean khi build theo hai môi trường AOT khác nhau. Không kỳ vọng chỉ đổi runtime profile là đủ để có mọi bean đã bị loại khỏi image.

Ghi kết quả theo bảng:

| Ca thử | Cách truyền | Cổng quan sát | Thông báo quan sát | Kết luận |
|---|---|---|---|---|
| A | `runtimeArgs` cố định | Điền thực tế | Điền thực tế | Đối số ứng dụng hoạt động? |
| B | `SERVER_PORT` | Điền thực tế | Điền thực tế | Environment có tác dụng? |
| C | `-PdemoPort` được ánh xạ | Điền thực tế | Điền thực tế | Gradle property có được chuyển? |
| D | Executable trực tiếp | Điền thực tế | Điền thực tế | Không cần Gradle để chạy? |
| E | Profile/conditional | Điền thực tế | Điền thực tế | Phân biệt AOT build và runtime? |

## 20. Nguyên tắc vận hành cần ghi nhớ

- **`nativeRun` chạy bản native** và thuận tiện cho kiểm thử cục bộ, nhưng lần chạy có thể kéo theo native compilation nếu output chưa sẵn sàng.
- **`runtimeArgs` truyền tham số cho ứng dụng**, trong khi `buildArgs` và những cờ của Gradle có vai trò khác.
- **Environment variables thuộc môi trường chạy** và cần được kiểm tra về precedence, quyền truy cập và cách triển khai.
- **Executable không mang theo toàn bộ môi trường Gradle.** Khi chạy trực tiếp hoặc đóng gói container, phải cung cấp arguments, environment, file và working directory phù hợp.
- **Spring AOT có thể cố định các quyết định về cấu trúc bean tại build time**; runtime properties chỉ thay đổi hành vi mà image hiện có hỗ trợ.
- **Kiểm thử trên executable thật** là bước cần thiết để xác nhận reflection/resource hints và tương thích của nghiệp vụ Spring Boot sau khi biên dịch.

### Tài liệu tham khảo để đối chiếu với phiên bản công cụ đang dùng

- GraalVM Native Build Tools — Gradle plugin: https://graalvm.github.io/native-build-tools/latest/gradle-plugin
- GraalVM Native Build Tools — Gradle end-to-end guide: https://graalvm.github.io/native-build-tools/latest/end-to-end-gradle-guide.html
- GraalVM — Build a Native Executable from a Spring Boot Application: https://www.graalvm.org/dev/reference-manual/native-image/guides/build-spring-boot-app-into-native-executable/

Khi sử dụng bài học với một dự án thực tế, hãy đối chiếu các ví dụ DSL và runtime flags với **đúng phiên bản Spring Boot, GraalVM và Gradle plugin** đã được cấu hình.
