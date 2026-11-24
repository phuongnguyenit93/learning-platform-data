# Theo dõi chuỗi khởi tạo để tìm nguyên nhân lỗi

## 1. Vì sao cần theo dõi chuỗi khởi tạo class?

Trong ứng dụng Spring Boot, một lỗi xuất hiện lúc startup có thể bắt nguồn từ static initializer của một class được gọi gián tiếp qua nhiều dependency. Với GraalVM Native Image, tình huống còn phức tạp hơn vì một số class có thể được khởi tạo ngay trong quá trình build, một số khác được giữ lại để khởi tạo lúc process chạy.

Một class có thể khởi tạo class khác khi đọc static field, gọi static method, tạo instance hoặc thực hiện một thao tác phụ thuộc. Vì vậy, class xuất hiện cuối cùng trong stack trace chưa chắc là nguyên nhân gốc. Cần tìm được **chuỗi khởi tạo**, thời điểm mỗi class được khởi tạo và thao tác đầu tiên gây lỗi.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, bài học này hướng dẫn theo dõi initialization chain trên JVM và Native Image, phân biệt lỗi build-time với runtime, khoanh vùng class có side effect và chọn cách sửa phù hợp.

## 2. Quy tắc khởi tạo class của Java

Theo quy tắc Java, class được khởi tạo trước khi thực hiện một số thao tác chủ động như tạo instance, gọi static method hoặc đọc/ghi static field không phải constant variable. Việc khởi tạo gồm thực thi static field initializer và static initializer theo thứ tự văn bản trong class.

Ví dụ:

```java
final class DatabaseDefaults {
    static final int PORT = 5432;

    static {
        System.out.println("DatabaseDefaults initialized");
    }
}

final class DataSourceFactory {
    static final String URL = createUrl();

    static {
        System.out.println("DataSourceFactory initialized");
    }

    private static String createUrl() {
        return "jdbc:postgresql://localhost:" +
                DatabaseDefaults.PORT;
    }
}
```

Khi `DataSourceFactory` được khởi tạo, phương thức `createUrl()` được gọi. Nếu thao tác này kích hoạt việc khởi tạo class khác, các initializer liên quan có thể xuất hiện trong chuỗi.

Lưu ý: `static final` primitive/String được gán bằng constant expression có thể là compile-time constant và không nhất thiết kích hoạt class initialization khi được đọc. Ví dụ `PORT = 5432` là constant variable; không nên dùng riêng việc đọc field này để suy luận rằng `DatabaseDefaults` đã được khởi tạo.

## 3. Chuỗi khởi tạo gián tiếp

Xét ví dụ:

```java
final class AppConfig {
    static final String REGION =
            System.getenv("APP_REGION");
}

final class CloudClient {
    static final String ENDPOINT =
            "https://" + AppConfig.REGION + ".api.internal";
}

final class ClientRegistry {
    static final CloudClient CLIENT = new CloudClient();
}
```

Khi ứng dụng truy cập `ClientRegistry.CLIENT`, chuỗi có thể là:

```text
ClientRegistry initialization
  -> construct CloudClient
      -> initialize CloudClient
          -> read AppConfig.REGION
              -> initialize AppConfig
                  -> System.getenv("APP_REGION")
```

Nếu Native Image khởi tạo một class trong chuỗi này ở build time, giá trị environment của builder có thể bị lưu trong image heap. Nếu class khác được giữ ở runtime, cùng một dependency chain có thể chạy ở thời điểm process startup.

Không chỉ nhìn class ngoài cùng. Hãy lần theo các static field, static method và constructor mà initializer gọi, kể cả trong thư viện bên thứ ba.

## 4. Hai môi trường cần theo dõi

| Môi trường | Thời điểm khởi tạo | Công cụ/chỉ dấu |
|---|---|---|
| JVM thông thường | Khi class được sử dụng lần đầu theo quy tắc Java | JVM unified logging, stack trace, log trong initializer |
| Native Image build | Khi compiler chạy initializer được chọn build time | Native Image build log/diagnostic class initialization |
| Native executable runtime | Khi class được chọn runtime được khởi tạo | Log ứng dụng, stack trace, runtime diagnostics |
| Spring AOT | Khi ApplicationContext được phân tích để sinh mã | Log `processAot`/AOT processing và condition/configuration output |

Spring AOT và Native Image class initialization là hai hoạt động khác nhau. AOT phân tích cấu trúc bean và sinh mã. Class initialization quyết định static initializer chạy trong build hay process runtime. Một lỗi AOT không nhất thiết là lỗi class initialization, và ngược lại.

## 5. Bật log khởi tạo class trên JVM

Trên JDK hiện đại, unified logging có thể hiển thị class initialization:

```bash
java -Xlog:class+init=info -jar target/orders-service.jar
```

Để tăng chi tiết:

```bash
java -Xlog:class+init=debug -jar target/orders-service.jar
```

Cú pháp và mức log phụ thuộc JDK version. Log có thể rất dài, đặc biệt với Spring Boot có nhiều dependency. Hãy lọc theo package/class đang điều tra và giữ lại phần log đầu tiên liên quan tới lỗi.

Có thể kết hợp với log startup của Spring:

```bash
java -Xlog:class+init=info -jar target/orders-service.jar --debug
```

`--debug` của Spring Boot có thể tạo condition evaluation report; nó không thay thế JVM class initialization log. Hai nguồn trả lời hai câu hỏi khác nhau: class nào được khởi tạo và cấu hình/condition nào match.

## 6. Theo dõi class initialization trong Native Image build

Native Image có các tùy chọn chẩn đoán class initialization, nhưng tên option và mức hỗ trợ thay đổi theo GraalVM version. Các bản GraalVM từng cung cấp tùy chọn như:

```bash
native-image -H:+PrintClassInitialization ...
```

Một số phiên bản có thể hỗ trợ trace theo class hoặc package:

```bash
native-image --trace-class-initialization=com.example.AppConfig ...
```

**Không coi các lệnh trên là cú pháp bất biến cho mọi phiên bản.** Trước khi dùng, kiểm tra:

```bash
native-image --help
native-image --expert-options
native-image --version
```

Một số tùy chọn chẩn đoán thuộc nhóm expert/internal và có thể bị đổi hoặc loại bỏ. Khi build qua Maven/Gradle, truyền đúng build argument qua Native Build Tools plugin và xác nhận trong log rằng argument được chuyển tới Native Image compiler.

Không thêm option trace vào cấu hình production vĩnh viễn nếu nó chỉ phục vụ chẩn đoán; log chi tiết có thể tăng thời gian build và dung lượng output.

## 7. Đọc initialization report theo thứ tự

Khi có report, tập trung vào các thông tin:

- Class nào được khởi tạo ở build time.
- Class nào được khởi tạo ở runtime.
- Lý do hoặc dependency khiến class được khởi tạo.
- Class nào được khởi tạo trước class đang gây lỗi.
- Có class nào vừa đọc environment/file/network vừa bị khởi tạo ở build time không.
- Có class nào phụ thuộc object hoặc native resource không thể lưu vào image heap không.

Không chỉ tìm class xuất hiện ở cuối report. Cần dựng lại chuỗi gọi từ điểm kích hoạt đến initializer gây side effect. Nếu report không cho biết đầy đủ call path, bổ sung log có kiểm soát vào initializer trong môi trường thử nghiệm hoặc dùng stack trace để xác định caller.

## 8. Dùng log tạm thời để tìm điểm kích hoạt

Trong code do ứng dụng sở hữu, có thể thêm log tạm thời:

```java
final class RegionConfig {

    static final String REGION;

    static {
        System.err.println(
                "Initializing RegionConfig, user.dir=" +
                System.getProperty("user.dir"));
        REGION = System.getenv("APP_REGION");
    }
}
```

Log này giúp xác định initializer được chạy trong build process hay runtime process, nhưng chỉ dùng trong nhánh chẩn đoán. Không log secret hoặc toàn bộ environment.

Một cách khác là ném exception có stack trace trong test để xác định call path, nhưng không nên để side effect đó tồn tại trong code phát hành. Trước khi thêm log, kiểm tra initializer có thể đã bị compiler thực thi trong build time; log build và log runtime là hai output khác nhau.

## 9. Phân biệt lỗi build-time initialization và runtime initialization

### Lỗi trong build

Dấu hiệu thường gặp:

- Native Image build thất bại khi khởi tạo class.
- Thông báo liên quan object không thể lưu trong image heap.
- Build process cố mở file, kết nối network hoặc tạo thread.
- Giá trị environment của máy build xuất hiện trong static state.

Hướng xử lý: tìm initializer gây side effect, tách logic bất biến khỏi logic phụ thuộc môi trường, hoặc chuyển class phù hợp sang runtime initialization.

### Lỗi khi native executable chạy

Dấu hiệu thường gặp:

- Static initializer ném exception khi process startup hoặc request đầu tiên.
- Runtime environment thiếu file/library mà initializer mong đợi.
- Static field chứa giá trị không đúng môi trường triển khai.
- Lỗi `ExceptionInInitializerError` hoặc `NoClassDefFoundError: Could not initialize class`.

Hướng xử lý: xem exception gốc bên trong `ExceptionInInitializerError`, xác định class đã thất bại và kiểm tra class initialization policy cùng dependency chain.

## 10. Hiểu ExceptionInInitializerError và NoClassDefFoundError

Nếu static initializer ném exception, JVM thường bọc lỗi đầu tiên trong `ExceptionInInitializerError`. Những lần sử dụng sau có thể nhận `NoClassDefFoundError: Could not initialize class`, vì class đã thất bại trong quá trình khởi tạo ở process đó.

Ví dụ:

```java
final class SecretConfig {
    static final String TOKEN;

    static {
        TOKEN = Files.readString(
                Path.of("/run/secrets/api-token"));
    }
}
```

Nếu file không tồn tại, lần khởi tạo đầu tiên có thể gây exception. Stack trace sau đó có thể chỉ hiện `Could not initialize class SecretConfig`, che khuất nguyên nhân gốc.

Khi debug:

1. Tìm lần lỗi đầu tiên trong log process.
2. Mở `Caused by` sâu nhất.
3. Xác định class initializer và thao tác file/environment/network.
4. Kiểm tra process user, path, mount và quyền truy cập.
5. Chạy lại trong process mới sau khi sửa; class đã thất bại không tự phục hồi trong cùng process.

## 11. Xác định class gây lỗi trong dependency chain

Class gây lỗi có thể thuộc thư viện, không phải source ứng dụng. Ví dụ một SDK có static initializer đọc file cấu hình hoặc nạp native library. Hãy:

- Xác định JAR chứa class từ dependency tree/build report.
- Kiểm tra static fields và static initializer của class nếu có source/decompiler phù hợp.
- Tìm class khác được gọi từ initializer.
- Kiểm tra version thư viện và ghi chú hỗ trợ GraalVM Native Image.
- Xem thư viện đã cung cấp reachability metadata hoặc Spring RuntimeHints chưa.

Không sửa trực tiếp JAR dependency hoặc generated source. Nếu lỗi nằm trong thư viện, cân nhắc nâng version có hỗ trợ Native Image, cấu hình initialization phù hợp, hoặc báo upstream với stack trace tối thiểu.

## 12. Khoanh vùng bằng run-time initialization

Nếu class phụ thuộc môi trường và không nên khởi tạo ở build time, có thể yêu cầu Native Image giữ việc khởi tạo đến runtime:

```bash
native-image \
  --initialize-at-run-time=com.example.environment.RegionConfig \
  ...
```

Trong Maven/Gradle, truyền option này qua Native Build Tools configuration. Ví dụ Gradle dạng minh họa:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add(
                '--initialize-at-run-time=com.example.environment.RegionConfig'
            )
        }
    }
}
```

Kiểm tra DSL theo version plugin. Sau khi build lại, xác nhận class thực sự được runtime initialize bằng report/log hoặc test environment khác builder.

Chuyển class sang runtime không phải lúc nào cũng là giải pháp cuối cùng. Nếu initializer tạo thread, kết nối database hoặc thực hiện network call, nên chuyển side effect vào bean lifecycle/service thay vì để static initializer tự làm việc đó.

## 13. Khi nào nên refactor thay vì thay initialization policy?

Một initializer có thể làm quá nhiều việc:

```java
final class ApplicationBootstrap {
    static final Rules RULES = loadRulesFromDisk();
    static final Client CLIENT = connectToRemoteService();
    static final String REGION = System.getenv("APP_REGION");
}
```

Đổi cả class sang runtime initialization sẽ khiến tất cả công việc chạy lúc startup, bao gồm đọc file và kết nối network. Thiết kế rõ hơn:

- Dữ liệu bất biến: giữ trong constant hoặc class thuần.
- Cấu hình deployment: bind qua `@ConfigurationProperties`.
- Đọc external file: dùng service/bean với path runtime.
- HTTP/database client: tạo bean theo lifecycle và connection policy.
- Thread/scheduler: khởi động/dừng qua lifecycle quản lý của Spring.
- Secret: lấy từ secret source lúc chạy, không nhúng vào static state.

Refactor tách side effect khỏi initializer giúp kiểm thử dễ hơn, giảm phụ thuộc thứ tự khởi tạo và làm rõ lỗi khi startup.

## 14. Quy trình chẩn đoán từng bước

Dùng quy trình sau khi native build hoặc process startup thất bại:

1. **Ghi nhận lỗi đầu tiên:** lấy toàn bộ exception đầu tiên và phần `Caused by`, không chỉ dòng lỗi cuối.
2. **Xác định pha:** lỗi xảy ra trong Maven/Gradle AOT, Native Image compilation hay khi chạy executable?
3. **Tìm class initializer:** xác định class có static field/khối `static` liên quan.
4. **Dựng dependency chain:** lần theo class/method/constructor được gọi từ initializer.
5. **Phân loại side effect:** environment, file, clock, random, network, thread, native library hay dữ liệu bất biến.
6. **Đọc initialization report:** xác nhận class được xử lý build time hay runtime.
7. **Chọn cách sửa:** refactor side effect, chuyển class phù hợp sang runtime, hoặc giữ build-time nếu initializer deterministic.
8. **Build lại từ cấu hình đã ghi nhận:** không đổi đồng thời nhiều biến để tránh mất dấu nguyên nhân.
9. **Chạy trong runtime image đích:** xác nhận path, library, user và environment.
10. **Chạy regression tests:** bảo đảm sửa initializer không làm thay đổi hành vi bean/configuration khác.

## 15. Bảng dấu hiệu và nguyên nhân thường gặp

| Dấu hiệu | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| Build báo object không thể lưu trong image heap | Static state chứa thread, socket, native handle hoặc object không hỗ trợ | Class initialization report và initializer chain |
| Build cố đọc file máy developer | File access trong static initializer chạy build time | Stack trace, CWD và đường dẫn file |
| Native dùng environment builder | Static field bị đóng băng trong image heap | Build/runtime environment và class policy |
| Runtime ném ExceptionInInitializerError | Initializer lỗi ở process startup | `Caused by` sâu nhất |
| Lần sau báo Could not initialize class | Lần khởi tạo đầu tiên đã thất bại | Log đầu tiên của process |
| Chỉ lỗi trong container | File/library/permission khác host hoặc class runtime init phụ thuộc môi trường | Mount, user, loader và runtime config |
| Startup chậm sau khi chuyển nhiều class sang runtime | Quá nhiều công việc bị dời sang process startup | So sánh initialization report và readiness time |
| Lỗi sau nâng dependency | Initializer hoặc policy của thư viện thay đổi | Dependency version và report mới |

## 16. Bài thực hành: lần theo chuỗi khởi tạo ba class

**Bối cảnh:** ứng dụng có `ClientRegistry`, `RemoteClient` và `DeploymentSettings`. Một static field đọc `APP_REGION` và tạo endpoint.

**Bước 1 — Tạo chuỗi phụ thuộc.** Để `ClientRegistry` khởi tạo `RemoteClient`, còn `RemoteClient` đọc `DeploymentSettings.REGION`.

**Bước 2 — Chạy JVM với log.** Dùng `-Xlog:class+init=info` và log tạm trong initializer để quan sát thứ tự.

**Bước 3 — Build Native Image.** Bật diagnostic class initialization phù hợp GraalVM version; lưu log và phân biệt build-time/runtime classes.

**Bước 4 — Đổi environment.** Build với `APP_REGION=build-region`, chạy với `APP_REGION=runtime-region`; quan sát giá trị static.

**Bước 5 — Khoanh vùng.** Chuyển riêng `DeploymentSettings` sang runtime initialization và build lại; xác minh giá trị runtime.

**Bước 6 — Refactor.** Thay static environment access bằng `@ConfigurationProperties` hoặc Spring Environment trong bean phù hợp.

**Bước 7 — Regression test.** Chạy JVM và native với hai environment, xác nhận endpoint dùng đúng cấu hình, startup và lỗi được ghi nhận.

Tiêu chí hoàn thành: mô tả được thứ tự khởi tạo, xác định class đầu tiên gây side effect, giải thích class được build-time hay runtime initialized và chứng minh giải pháp bằng native executable.

## 17. Kết luận

Lỗi class initialization thường là kết quả của một chuỗi phụ thuộc, không chỉ của class xuất hiện trong thông báo cuối. Muốn tìm đúng nguyên nhân, cần kết hợp JVM class-init logging, Native Image initialization diagnostics, stack trace và kiểm tra static initializer của các class liên quan.

Với Spring Boot Native Image, hãy phân biệt Spring AOT với Native Image class initialization, xác định thời điểm build/runtime của từng class, tránh side effect trong initializer và chỉ chuyển class cần thiết sang runtime initialization. Sau khi sửa, build lại và kiểm thử executable trong runtime container đích để bảo đảm giá trị cấu hình, tài nguyên và startup behavior đều đúng.
