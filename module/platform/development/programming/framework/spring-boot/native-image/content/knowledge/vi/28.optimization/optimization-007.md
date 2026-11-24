# PGO: thu thập profile đại diện và biên dịch lại trên nền tảng được hỗ trợ

## 1. Vì sao Native Image cần profile?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng **Spring AOT** rồi biên dịch thành **GraalVM Native Image** để đánh giá thời gian khởi động, bộ nhớ, throughput và khả năng vận hành. Native Image biên dịch Ahead-of-Time (AOT): compiler phân tích code reachable và tạo machine code trước khi ứng dụng chạy. Khác với JIT compiler, AOT compiler không tự quan sát workload production để biết method nào được gọi thường xuyên, nhánh điều kiện nào phổ biến hoặc kiểu dữ liệu nào xuất hiện nhiều.

**Profile-Guided Optimization (PGO)** đưa thông tin runtime vào quá trình AOT compilation. Nhóm phát triển build một executable có instrumentation, chạy executable đó với workload đại diện để thu profile, rồi truyền profile vào lần build native tiếp theo. Compiler có thêm dữ liệu để quyết định tối ưu hot methods, branch, call sites và các đường xử lý thường gặp.

Với dịch vụ Spring Boot, profile có thể giúp compiler ưu tiên các đường request phổ biến như xác thực, truy vấn, serialize JSON, tính toán nghiệp vụ và gọi service nội bộ. Nếu workload thu thập khác xa production, profile có thể hướng compiler tối ưu nhầm các đường ít dùng và làm hiệu năng giảm.

Sau bài học, người học có thể:

1. Giải thích PGO bổ sung dữ liệu runtime cho AOT compiler như thế nào.
2. Phân biệt PGO profile với reachability metadata do tracing agent tạo ra.
3. Xác định GraalVM distribution, version, OS và architecture có hỗ trợ PGO.
4. Build instrumented native executable bằng `--pgo-instrument`.
5. Chạy workload đại diện và thu file `.iprof` bằng `-XX:ProfilesDumpFile`.
6. Thu thập nhiều profile, hợp nhất hoặc truyền nhiều file cho compiler.
7. Build executable tối ưu bằng `--pgo=<profile>`.
8. Cấu hình Maven/Gradle Native Build Tools cho từng giai đoạn.
9. Đánh giá profile quality, hiệu năng và ảnh hưởng của profile cũ.
10. Xây dựng quy trình CI có thể tái lập trên đúng nền tảng triển khai.

> **Điều kiện quan trọng:** PGO không có trong GraalVM Community Edition. Cần dùng GraalVM distribution và phiên bản có hỗ trợ PGO, đồng thời xác nhận Native Image target cùng native toolchain phù hợp với nền tảng triển khai.

## 2. PGO ghi nhận điều gì?

Một profile là bản tóm tắt hành vi chương trình khi chạy. Tùy dữ liệu Native Image thu thập, compiler có thể biết:

- Method nào được gọi thường xuyên và tần suất tương đối.
- Nhánh điều kiện nào thường đúng hoặc sai.
- Call site nào thường nhận một kiểu dữ liệu cụ thể.
- Đường allocation nào xuất hiện thường xuyên.
- Các context thực thi nào thường gặp.

Ví dụ, một endpoint xử lý đơn hàng có thể nhận 95% request hợp lệ và 5% request bị từ chối. Nếu profile đại diện ghi nhận phân bố đó, compiler có thêm căn cứ để ưu tiên đường xử lý đơn hàng hợp lệ. Nếu profile chỉ chứa request lỗi, compiler có thể dành nhiều công sức cho error path vốn ít xuất hiện trong production.

### 2.1. PGO khác tracing agent

Hai loại profile/metadata này phục vụ mục tiêu khác nhau:

| Công cụ | Thu thập | Mục đích |
| --- | --- | --- |
| Native Image Tracing Agent | Reflection, resource, proxy, serialization, JNI access được quan sát trong JVM. | Tạo reachability metadata để Native Image biết các truy cập động cần giữ lại. |
| PGO instrumentation | Tần suất method, branch, type và hành vi runtime được compiler dùng cho optimization. | Hướng AOT compiler tối ưu code theo workload. |

PGO không tự đăng ký reflection, resource hoặc proxy. Nếu native build lỗi vì thiếu reachability metadata, cần xử lý hints/metadata tương ứng; PGO không thay thế bước đó.

### 2.2. PGO có bảo đảm nhanh hơn không?

Không. PGO cung cấp dữ liệu cho compiler đưa ra quyết định tốt hơn đối với workload tương tự profile. Kết quả còn phụ thuộc code, workload, GraalVM version, CPU, GC, cấu hình build và cách đo.

PGO thường được dùng để cải thiện throughput hoặc hiệu năng của hot paths. Kích thước executable cũng có thể thay đổi vì compiler phân biệt hot code và cold code. Startup, memory và latency không mặc nhiên cải thiện trong mọi ứng dụng; phải đo từng mục tiêu riêng.

## 3. Kiểm tra GraalVM và nền tảng được hỗ trợ

Trước khi tạo profile, xác nhận môi trường build:

~~~bash
java -version
native-image --version
native-image --help
native-image --print-options
~~~

Kiểm tra:

- Distribution có cung cấp tính năng PGO hay không.
- GraalVM version có nhận `--pgo-instrument`, `--pgo` và các runtime options cần dùng không.
- JDK version có tương thích với Spring Boot, Spring Framework và dependency graph không.
- Native Image hỗ trợ OS/architecture đích của executable.
- C compiler, linker, libc, headers và native libraries phù hợp target.
- CI runner hoặc build container sử dụng đúng toolchain đã xác minh.

Tài liệu GraalVM hiện hành ghi rõ PGO không khả dụng trong GraalVM Community Edition. Nếu option không được nhận diện, không nên đổi tên option theo một bài viết cũ; hãy xác minh distribution và version trước.

### 3.1. Nền tảng thu thập profile và nền tảng build

Profile PGO thường có thể được thu thập trên một nền tảng rồi sử dụng để build executable trên nền tảng khác. Tuy nhiên, một số class/method phụ thuộc OS hoặc architecture, chẳng hạn implementation dành riêng cho POSIX và Windows. Profile thu trên một nền tảng có thể không chứa entry tương ứng với code chỉ tồn tại trên nền tảng khác.

Thực hành tốt nhất:

- Thu profile trên cùng OS/architecture với target optimized executable nếu có thể.
- Nếu dùng profile cross-platform, kiểm tra build report và benchmark trên target thật.
- Với nhiều target như Linux x64 và Linux ARM64, cân nhắc duy trì profile riêng cho từng target.
- Không giả định profile của một GraalVM release hoặc dependency graph bất kỳ luôn là lựa chọn tốt cho release hiện tại.

PGO profile là dữ liệu cho compiler, không phải executable có thể chạy trên mọi nền tảng. Bản native cuối cùng vẫn phải được build theo target được GraalVM và native toolchain hỗ trợ.

### 3.2. Khi cần cross-compilation

Native Image có option `--target=<OS>-<architecture>` ở các version hỗ trợ. Cross-compilation còn phụ thuộc target toolchain, C libraries và native dependencies; chỉ thêm `--target` không bảo đảm môi trường build đã sẵn sàng.

Với pipeline nhiều nền tảng, ưu tiên build trên runner/container tương ứng từng target. Nếu dùng cross-compilation, kiểm tra tài liệu GraalVM đúng release, C compiler target, linker, libc và mọi native library trước khi phát hành.

### 3.3. CPU architecture và `-march`

`-march` quyết định tập CPU instruction mà compiler có thể sử dụng. `-march=native` có thể cải thiện hiệu năng khi binary chỉ chạy trên máy có cùng tập CPU features, nhưng có thể làm executable không chạy trên node khác trong cluster.

Với deployment trên nhiều máy khác nhau, chọn CPU baseline tương thích hoặc build riêng theo nhóm CPU. Giữ cùng `-march` khi so sánh baseline và PGO để kết quả không bị ảnh hưởng bởi hai tập instruction khác nhau.

## 4. Quy trình PGO tổng thể

PGO cho Native Image gồm ba lần chạy chính:

~~~mermaid
flowchart TD
    A[Spring Boot source và dependency graph] --> B[Build instrumented native executable]
    B --> C[Run workload đại diện]
    C --> D[Profile .iprof được ghi khi process kết thúc]
    D --> E[Review, lưu trữ hoặc merge profiles]
    E --> F[Build optimized executable với --pgo]
    F --> G[Kiểm tra build output và target]
    G --> H[Benchmark cùng workload với baseline]
    H --> I{Đạt mục tiêu hiệu năng và regression?}
    I -->|Không| J[Điều chỉnh workload/profile/build options]
    J --> B
    I -->|Có| K[Đóng gói và phát hành optimized executable]
~~~

Ba giai đoạn cần phân biệt:

1. **Instrumented build:** thêm counter vào AOT code để ghi profile.
2. **Profile collection:** chạy instrumented executable với workload đại diện.
3. **Optimized build:** biên dịch lại source bằng profile đã thu.

Executable có instrumentation chỉ phục vụ thu thập profile. Nó có overhead và không phải binary production.

## 5. Tạo baseline không dùng PGO

Trước khi tối ưu, tạo native executable chuẩn từ cùng source và cấu hình ứng dụng. Ví dụ với Spring Boot executable JAR:

~~~bash
native-image \
  -jar target/orders-service.jar \
  -o orders-default
~~~

Nếu project dùng Native Build Tools, chạy native compile theo Maven/Gradle configuration hiện tại. Lưu lại:

- Source commit và dependency graph.
- Spring Boot, JDK, GraalVM và plugin versions.
- OS/architecture, libc, CPU features và native toolchain.
- Build arguments, GC, heap options và `-march`.
- Build duration, executable size và build report.
- Startup-to-ready, throughput, latency, CPU và memory dưới workload chuẩn.

Baseline là mốc để xác định PGO có tạo khác biệt hay không. Nếu mục tiêu là throughput, cần có workload đủ dài để đo steady-state. Nếu ứng dụng thiên về serverless/cold start, đo startup và thời gian hoàn thành request riêng.

### 5.1. Tạo thêm baseline cùng optimization level khi cần

Trên Oracle GraalVM, PGO build thường tự dùng mức optimization `-O3`. Build thường mặc định có thể dùng `-O2`. Nếu muốn tách ảnh hưởng của profile khỏi ảnh hưởng của optimization level, hãy đo thêm một executable không PGO nhưng dùng cùng mức `-O3` nếu version hỗ trợ.

Có thể duy trì ba biến thể:

| Biến thể | Mục đích |
| --- | --- |
| Native mặc định | Đo cấu hình production hiện tại. |
| Native không PGO với cùng `-O3` | Tách ảnh hưởng của optimization level. |
| Native có PGO | Đo lợi ích thực tế từ profile. |

Không thay đổi đồng thời GC, `-march`, heap size, build flags và workload khi đang cố xác định lợi ích riêng của PGO.

## 6. Build instrumented executable

Dùng option `--pgo-instrument` để compiler tạo binary có counter thu thập profile:

~~~bash
native-image \
  --pgo-instrument \
  -jar target/orders-service.jar \
  -o orders-instrumented
~~~

Với Spring Boot, lệnh minh họa cần được thay bằng classpath/launcher và build arguments thực tế của project nếu native plugin quản lý quá trình compile. Mục tiêu là tạo cùng ứng dụng và cùng native configuration, chỉ thêm PGO instrumentation.

### 6.1. Instrumented build có chi phí

Instrumentation làm tăng thời gian thực thi và có thể tăng memory/CPU usage. Build instrumented cũng có thể tốn thêm tài nguyên compiler. Vì vậy:

- Không dùng instrumented executable để benchmark hiệu năng production.
- Không lấy latency của instrumented binary để so với baseline.
- Dành đủ CPU/RAM cho native-image builder.
- Giữ build arguments khác giống baseline.
- Không phát hành instrumented executable như binary production.

Nếu native-image builder gặp OutOfMemoryError, kiểm tra build log, memory limit, parallelism và builder heap. Có thể cần tăng tài nguyên build hoặc giảm số thread; đây là bộ nhớ của quá trình build, khác với memory runtime của service.

## 7. Chạy workload để thu profile

### 7.1. Profile được ghi ở đâu và khi nào?

Mặc định, instrumented executable ghi profile vào file `default.iprof` trong working directory khi process kết thúc. Có thể chỉ định đường dẫn khác bằng runtime option:

`-XX:ProfilesDumpFile=<path>`

Ví dụ:

~~~bash
mkdir -p profiles

./orders-instrumented \
  -XX:ProfilesDumpFile=profiles/steady-state.iprof \
  --spring.profiles.active=performance
~~~

Option này phải được truyền cho native executable khi chạy. Hãy bảo đảm thư mục tồn tại và process có quyền ghi file. Với container, mount một volume writable cho thư mục profiles hoặc ghi vào filesystem phù hợp rồi copy artifact ra ngoài.

Profile thường được dump khi application shutdown. Với service chạy lâu, cần dừng process graceful để runtime có cơ hội ghi profile. Nếu process bị SIGKILL, container bị OOM kill hoặc máy tắt đột ngột, profile có thể không được ghi đầy đủ.

### 7.2. Workload cho Spring Boot service

GraalVM không tự tạo workload HTTP cho ứng dụng web. Dùng load-testing tool hoặc end-to-end test có request mix gần production.

Ví dụ khởi chạy instrumented service:

~~~bash
./orders-instrumented \
  -XX:ProfilesDumpFile=profiles/orders-steady.iprof \
  --spring.profiles.active=performance
~~~

Từ process khác, chạy load test:

~~~bash
k6 run --duration 5m --vus 40 pgo-workload.js
~~~

File `pgo-workload.js` cần gửi request đến các endpoint thật mà service sử dụng, với payload, xác thực và tỷ lệ request gần môi trường production. Khi load test kết thúc, dừng service bằng cơ chế graceful shutdown của môi trường, rồi kiểm tra file profile.

Với endpoint GET đơn giản, có thể dùng `wrk`:

~~~bash
wrk -t4 -c32 -d5m http://localhost:8080/api/catalog
~~~

Một endpoint health đơn lẻ thường không đại diện cho workload business. Chọn endpoint có logic, serialization, database/cache và downstream calls mà service thực sự xử lý.

### 7.3. Xây dựng workload đại diện

Một workload tốt nên phản ánh:

- Tỷ lệ request theo endpoint hoặc use case.
- Tỷ lệ request thành công, validation failure và business rejection.
- Kích thước payload, kiểu dữ liệu và phân bố giá trị.
- Số lượng concurrent users/requests và request rate.
- Tỷ lệ cache hit/miss và database query.
- Authentication, authorization và serialization thực tế.
- Các feature flag/profile được bật trong deployment.
- Thời lượng đủ để service đi qua startup, warm-up và steady-state.

Không cần cố đưa mọi error case hiếm vào profile với tần suất bằng nhau. Profile nên phản ánh tần suất tương đối trong production. Những case hiếm vẫn phải được test về tính đúng đắn; chúng không nhất thiết phải trở thành hot path.

### 7.4. Warm-up trước khi lấy profile

Đối với service có connection pool, cache, lazy initialization hoặc client TLS, có thể tách warm-up khỏi giai đoạn profile chính:

1. Khởi động instrumented executable.
2. Chờ readiness và khởi tạo dependency.
3. Gửi warm-up requests theo quy trình ổn định.
4. Chạy workload profile với request mix đã định.
5. Dừng process graceful để ghi profile.

Không loại bỏ những đường khởi tạo quan trọng nếu mục tiêu của ứng dụng bao gồm startup/cold path. Hãy quyết định rõ profile cần đại diện cho steady-state hay cả quá trình startup, rồi thiết kế workload tương ứng.

### 7.5. Vì sao unit tests thường không phải profile tốt?

Unit tests có mục tiêu kiểm tra nhiều corner cases, không phải tái tạo tần suất production. Một test suite có thể gọi một helper lỗi hàng trăm lần và chỉ gọi business path chính vài lần; profile khi đó có thể khiến compiler ưu tiên sai.

Ưu tiên:

- End-to-end tests đại diện cho luồng production.
- Benchmark có request/data distribution gần production.
- Workload replay từ dữ liệu đã được xử lý an toàn.
- Load test có tỷ lệ request được đo từ production.

Có thể dùng unit tests nếu chúng thật sự đại diện cho workload cần tối ưu, nhưng không nên lấy toàn bộ test suite làm profile mặc định.

## 8. Thu thập nhiều profile cho nhiều scenario

Một profile duy nhất có thể chưa đại diện đủ nếu ứng dụng có nhiều workload khác nhau. Có thể chạy instrumented executable nhiều lần và dùng tên file riêng.

Ví dụ profile cho luồng đọc:

~~~bash
./orders-instrumented \
  -XX:ProfilesDumpFile=profiles/read-heavy.iprof \
  --spring.profiles.active=performance
~~~

Sau khi process kết thúc, chạy lại instrumented executable với workload ghi:

~~~bash
./orders-instrumented \
  -XX:ProfilesDumpFile=profiles/write-heavy.iprof \
  --spring.profiles.active=performance
~~~

Tạo profile batch riêng nếu batch là workload production quan trọng:

~~~bash
./orders-instrumented \
  -XX:ProfilesDumpFile=profiles/batch.iprof \
  --spring.profiles.active=batch-performance
~~~

Các profile cần được thu từ cùng phiên bản instrumented application và các scenario đã mô tả. Không cho nhiều process ghi đồng thời vào cùng một profile filename; dùng file riêng cho từng process.

### 8.1. Truyền nhiều profile trực tiếp cho compiler

Option `--pgo` nhận danh sách file phân tách bằng dấu phẩy:

~~~bash
native-image \
  --pgo=profiles/read-heavy.iprof,profiles/write-heavy.iprof,profiles/batch.iprof \
  -jar target/orders-service.jar \
  -o orders-pgo
~~~

GraalVM sẽ đọc các profile được chỉ định. Không cần đưa file `.iprof` vào application classpath hoặc đóng gói chúng vào runtime image; đây là đầu vào build.

### 8.2. Hợp nhất profile bằng Native Image Utils

Nếu muốn tạo một profile tổng hợp để quản lý như một artifact riêng, Native Image Utils cung cấp lệnh `merge-pgo-profiles`.

~~~bash
native-image-utils merge-pgo-profiles \
  --input-file=profiles/read-heavy.iprof \
  --input-file=profiles/write-heavy.iprof \
  --input-file=profiles/batch.iprof \
  --output-file=profiles/orders-combined.iprof
~~~

Có thể dùng một thư mục làm nguồn:

~~~bash
native-image-utils merge-pgo-profiles \
  --input-dir=profiles/ \
  --output-file=profiles/orders-combined.iprof
~~~

Lệnh merge tạo profile chứa hợp của các type, method và profile entries từ các file đầu vào. Vì profile tổng hợp có thể chứa nhiều scenario, hãy giữ lại danh sách nguồn và tỷ lệ workload đã dùng để tạo từng file.

### 8.3. Cân nhắc phân bố traffic khi kết hợp profile

Một tập profile không tự chứng minh rằng traffic mix cuối cùng đúng với production. Nếu một profile đại diện workload đọc chiếm 90% traffic và một profile batch chỉ chạy một lần mỗi ngày, cách tổ chức workload cần phản ánh mức độ quan trọng đó.

Hãy thiết kế thời lượng/tần suất thu thập theo tỷ lệ thực tế hoặc dùng một workload tổng hợp đã định nghĩa rõ distribution. Không chạy mọi scenario cùng thời lượng rồi mặc định kết quả tương đương tỷ lệ production.

## 9. Biên dịch optimized executable với PGO

Sau khi có profile, build lại cùng ứng dụng và truyền profile cho compiler:

~~~bash
native-image \
  --pgo=profiles/orders-combined.iprof \
  -jar target/orders-service.jar \
  -o orders-pgo
~~~

Nếu dùng profile mặc định `default.iprof` trong working directory, một số version có thể tự tìm file đó khi chạy build không chỉ định đường dẫn. Trong pipeline production, nên truyền đường dẫn rõ ràng để tránh vô tình dùng profile cũ hoặc file nằm sai thư mục.

### 9.1. Dùng profile nào?

Chọn profile được tạo từ:

- Đúng ứng dụng và dependency graph gần với release cần build.
- Workload đã được kiểm tra tính đại diện.
- GraalVM version phù hợp.
- Nền tảng/architecture tương ứng nếu có thể.
- Scenario được ghi nhận và còn phù hợp với code hiện tại.

Nếu profile có từ một release trước, kiểm tra mức thay đổi ở hot paths và các dependency chính. Một profile cũ vẫn có thể được compiler đọc, nhưng điều đó không có nghĩa nó còn hữu ích.

### 9.2. Không trộn instrument và optimize trong cùng build

Hai giai đoạn có option khác nhau:

| Giai đoạn | Build argument | Kết quả |
| --- | --- | --- |
| Instrumented | `--pgo-instrument` | Executable ghi profile khi chạy. |
| Optimized | `--pgo=profiles/orders-combined.iprof` | Executable được tối ưu dựa trên profile. |
| Baseline | Không có PGO option | Executable native chuẩn để so sánh. |

Mỗi lần build chỉ chọn cấu hình tương ứng. Không giữ `--pgo-instrument` trong production build cuối cùng.

## 10. Cấu hình Maven Native Build Tools

Với Maven, thêm build argument vào cấu hình `native-maven-plugin`. Ví dụ cho instrumented profile:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--pgo-instrument</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Khi build executable thu thập profile, kích hoạt profile Maven chứa argument đó:

~~~bash
./mvnw -Pinstrumented -Pnative package
~~~

Với optimized build, dùng profile Maven riêng có argument:

~~~xml
<buildArg>--pgo=profiles/orders-combined.iprof</buildArg>
~~~

Chạy build optimized theo profile đã cấu hình:

~~~bash
./mvnw -Ppgo-optimized -Pnative package
~~~

Đây là các fragment minh họa. Hợp nhất chúng vào POM hiện có, giữ nguyên plugin version, execution, main class, Spring AOT configuration và build arguments khác. Không để hai profile instrumented và optimized cùng active nếu cấu hình sẽ truyền cả hai option vào một native-image invocation.

Nếu dùng `spring-boot-maven-plugin` hoặc Buildpacks để tạo executable, kiểm tra cách plugin/builder nhận native build arguments ở đúng version. Không giả định mọi profile `native` mặc định của Spring Boot đã bật PGO.

## 11. Cấu hình Gradle Native Build Tools

Với Kotlin DSL, thêm `--pgo-instrument` vào native binary khi cần tạo instrumented executable:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--pgo-instrument")
        }
    }
}
~~~

Khi chuyển sang optimized build, thay bằng profile đã thu:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--pgo=profiles/orders-combined.iprof")
        }
    }
}
~~~

Với Groovy DSL:

~~~groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add('--pgo=profiles/orders-combined.iprof')
        }
    }
}
~~~

Chạy task native compile theo plugin:

~~~bash
./gradlew nativeCompile
~~~

Để tạo instrumented binary, dùng build configuration có `--pgo-instrument`; để tạo optimized binary, dùng build configuration có `--pgo=...`. Có thể tách hai cấu hình thành Gradle properties hoặc convention plugin để CI chọn rõ ràng.

Cú pháp DSL và tên task phụ thuộc version Native Build Tools và Spring Boot Gradle Plugin. Kiểm tra `./gradlew tasks`, plugin DSL reference và build log của project. Tránh copy một cấu hình Gradle từ release khác mà không xác nhận property tồn tại.

## 12. Xác nhận compiler thực sự dùng profile

Đừng chỉ dựa vào exit code 0. Đọc phần **Builder configuration** trong Native Image build output.

Trên Oracle GraalVM, dòng compiler configuration có thể hiển thị trạng thái PGO, ví dụ:

- `off`: không dùng PGO.
- `instrument`: binary được instrument để thu profile.
- `user-provided`: compiler dùng profile do người dùng cung cấp.
- `ML-inferred`: profile được suy luận từ mô hình machine learning ở một số cấu hình/release.

Với instrumented build, kiểm tra trạng thái là `instrument`. Với optimized build dùng `.iprof`, kiểm tra trạng thái là `user-provided` hoặc cách biểu diễn tương ứng của GraalVM version đang dùng.

Nếu build output báo `off`, kiểm tra:
- Build argument có đến được native-image process không.
- Profile path có đúng working directory không.
- Maven/Gradle profile có được kích hoạt không.
- Có dùng đúng GraalVM distribution hỗ trợ PGO không.
- Có warning hoặc thông báo profile bị bỏ qua không.

GraalVM cung cấp `native-image --native-image-info` và các build reports để ghi lại toolchain/configuration. Giữ log của cả instrumented build và optimized build làm bằng chứng.

## 13. Đánh giá chất lượng profile

### 13.1. Profile applicability và profile relevance

Một số GraalVM version có thể in hai chỉ số:

- **Profile applicability:** mức độ các điểm trong code cần profile có dữ liệu tương ứng.
- **Profile relevance:** mức độ profile entries liên quan tới code của ứng dụng được build.

Có thể yêu cầu compiler in các chỉ số này bằng option:

~~~bash
native-image \
  --pgo=profiles/orders-combined.iprof \
  -H:+PGOPrintProfileQuality \
  -jar target/orders-service.jar \
  -o orders-pgo
~~~

`-H:+PGOPrintProfileQuality` là option experimental trong tài liệu hiện hành. Chỉ dùng khi GraalVM version hỗ trợ và không coi các con số tuyệt đối là điểm đánh giá chất lượng duy nhất. Ý nghĩa tốt nhất của chúng là theo dõi xu hướng khi dùng lại profile qua nhiều build hoặc so sánh các profile khác nhau.

### 13.2. Kiểm tra profile cũ

Profile có thể được tái sử dụng sau một số thay đổi code, nhưng profile sai lệch có thể làm hiệu năng kém hơn build không PGO. Đánh giá lại khi:

- Thay đổi thuật toán hoặc hot path.
- Thay đổi request mix hoặc tỷ lệ workload.
- Nâng dependency ảnh hưởng đến code được gọi thường xuyên.
- Thêm/bỏ feature, serializer, database access hoặc downstream client.
- Thay đổi profile/runtime configuration.
- Nâng GraalVM/JDK hoặc chuyển target platform.
- Profile không còn phản ánh hành vi production.

Không cần thu lại profile sau mọi thay đổi tài liệu hoặc refactor chỉ tác động cold code. Tuy nhiên, phải có chính sách re-profile định kỳ hoặc khi thay đổi hot path.

### 13.3. Metadata của profile phải có provenance

Lưu kèm file `.iprof`:

| Trường | Nội dung |
| --- | --- |
| Application commit | Commit đã tạo instrumented executable. |
| GraalVM | Distribution, version và JDK. |
| Target | OS, architecture, libc và CPU baseline. |
| Dependencies | Dependency graph/BOM version. |
| Workload | Script, request mix, dataset và thời lượng. |
| Environment | Profile, feature flags và cấu hình runtime. |
| Collected at | Thời điểm thu thập. |
| Source profiles | Các file đầu vào nếu profile đã merge. |
| Owner | Pipeline/team chịu trách nhiệm profile. |

Profile là build input, không phải runtime asset của service. Lưu trong artifact repository hoặc CI artifact store có version và metadata; không đặt nhầm trong thư mục resources của ứng dụng.

## 14. Benchmark baseline và PGO optimized

### 14.1. Không đo instrumented binary

Instrumented executable có overhead do counter và instrumentation. Nó có thể chậm hơn đáng kể so với binary bình thường. Dùng nó để thu profile, không dùng để báo cáo hiệu năng production.

Benchmark hai binary:
- Native baseline không PGO.
- Native optimized có PGO.

Nếu muốn tách ảnh hưởng của `-O3`, thêm baseline không PGO cùng optimization level. Giữ các cấu hình còn lại giống nhau.

### 14.2. Cố định điều kiện đo

Dùng cùng:

- Máy/CPU hoặc cùng loại runner.
- OS, architecture, libc và container base image.
- CPU quota, memory limit và swap policy.
- Dataset, request payload và traffic distribution.
- Concurrency, duration, warm-up và số lần lặp.
- Spring profile, environment variables và downstream services.
- Logging, metrics, tracing và GC configuration.
- JDK/GraalVM version và build arguments ngoài PGO.

Không so sánh binary PGO chạy trên CPU mới với baseline chạy trên CPU cũ. Nếu build target khác nhau, kết quả có thể phản ánh khác biệt platform thay vì PGO.

### 14.3. Chỉ số nên ghi

| Chỉ số | Mục tiêu |
| --- | --- |
| Throughput/RPS | Số request xử lý mỗi giây ở cùng concurrency. |
| p50/p95/p99 latency | Phân bố thời gian phản hồi. |
| CPU utilization | Chi phí CPU để xử lý cùng workload. |
| Allocation/GC | Áp lực allocation và thời gian GC nếu runtime expose. |
| RSS/peak memory | Footprint của executable dưới tải. |
| Startup-to-ready | Thời gian từ process start đến readiness. |
| Executable size | Kích thước binary cuối cùng. |
| Build duration | Chi phí tạo baseline, instrumented và optimized binaries. |

PGO thường nhắm tới hot code và throughput. Nếu latency p99 hoặc startup là mục tiêu chính, kiểm tra chúng riêng; không suy luận từ throughput rằng mọi latency percentile đều giảm.

### 14.4. Lặp lại và phân tích

Chạy nhiều lần và ghi median, min/max hoặc khoảng dao động. Xen kẽ thứ tự baseline/PGO để giảm ảnh hưởng tải nền hoặc thay đổi CPU frequency. Dùng cùng một workload script và giữ kết quả thô.

Nếu PGO không cải thiện:
- Xác nhận profile được dùng.
- Kiểm tra workload có đại diện không.
- Kiểm tra profile có stale hoặc quá ngắn không.
- So sánh `-O` và `-march`.
- Xem profile quality/build report nếu option có sẵn.
- Đo lại sau khi thay đổi một yếu tố tại một thời điểm.

Nếu PGO làm kết quả xấu hơn, thử build không PGO và thu profile mới. Không giữ PGO chỉ vì pipeline đã tốn thời gian tạo profile.

## 15. Tổ chức PGO trong CI/CD

Có thể tách pipeline thành các job:

~~~mermaid
flowchart TD
    A[Checkout source và resolve dependencies] --> B[Build instrumented native executable]
    B --> C[Start instrumented service]
    C --> D[Replay representative workload]
    D --> E[Graceful shutdown và collect iprof]
    E --> F[Upload profile artifact kèm provenance]
    F --> G[Build optimized native executable]
    G --> H[Verify PGO status và build report]
    H --> I[Run correctness tests]
    I --> J[Benchmark baseline và PGO]
    J --> K{Đạt performance gate?}
    K -->|Không| L[Giữ baseline và điều tra profile]
    K -->|Có| M[Package và publish optimized artifact]
~~~

### 15.1. Tách artifact theo mục đích

Giữ riêng:
- Instrumented executable.
- Profile files `.iprof`.
- Merged profile nếu có.
- Native executable optimized.
- Baseline executable.
- Build logs/reports và benchmark results.

Không dùng nhầm instrumented executable cho release. Không copy profile vào container runtime nếu service không cần nó khi chạy.

### 15.2. Chính sách refresh profile

Có thể thu profile:
- Mỗi release lớn.
- Khi hot path hoặc request distribution thay đổi.
- Theo lịch, ví dụ nightly/weekly tùy tốc độ thay đổi ứng dụng.
- Từ benchmark workload được version hóa.
- Từ một instance/canary riêng nếu có quy trình chấp nhận instrumentation overhead.

Không tái sử dụng profile vô thời hạn. Profile stale vẫn có thể được compiler đọc nhưng có thể hướng optimization sai. Gắn profile với commit, dependency graph, workload và target để quyết định khi nào cần tạo lại.

### 15.3. Kiểm tra trước khi phát hành

- Native executable là optimized build mới.
- Build output xác nhận PGO user-provided.
- Đúng GraalVM distribution/version và target.
- Correctness tests pass.
- Benchmark so sánh cùng workload.
- Không có regression đáng kể về latency, memory hoặc executable size.
- Profile provenance và build logs được lưu.
- Instrumented executable không bị đưa vào release image.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `--pgo-instrument` không được nhận diện | GraalVM Community Edition hoặc version không hỗ trợ option. | Xác minh distribution/version và `native-image --help`. |
| Không có `default.iprof` | Process chưa shutdown, bị kill, không có quyền ghi hoặc working directory khác. | Dùng `-XX:ProfilesDumpFile` với path writable và shutdown graceful. |
| File `.iprof` rỗng/không hợp lệ | Workload chưa chạy, process bị dừng đột ngột hoặc profile chưa được dump. | Kiểm tra log, thời gian chạy và file sau shutdown. |
| Optimized build báo PGO off | Build argument không được truyền hoặc plugin config không được kích hoạt. | Kiểm tra Maven/Gradle profile và Builder configuration. |
| Build báo không đọc được profile | Sai path, profile không phải output hợp lệ hoặc file hỏng. | Dùng đúng artifact `.iprof`, không chỉnh sửa thủ công, thu lại profile. |
| PGO không cải thiện | Workload không đại diện, profile ngắn, app bị giới hạn I/O hoặc hot path không đổi. | Đo CPU-bound path, tăng coverage workload và so sánh nhiều lần. |
| PGO làm chậm hơn | Profile sai lệch hoặc stale, traffic mix khác production. | Thu profile mới hoặc dùng baseline không PGO. |
| Một số method không có profile entry | Code chưa chạy hoặc platform-specific code không tồn tại ở nền tảng thu thập. | Bổ sung scenario hoặc thu profile trên target platform. |
| Build instrumented OOM | Instrumentation làm tăng tài nguyên cần cho build. | Tăng builder RAM, điều chỉnh `-J-Xmx` và `--parallelism`. |
| Profile dùng được trên một OS nhưng thiếu entry ở OS khác | Implementation/JDK code khác theo platform. | Thu profile riêng cho target hoặc kiểm tra profile trên target. |
| CI dùng nhầm profile cũ | Artifact store không gắn commit/workload hoặc file mặc định bị tái sử dụng. | Dùng path version hóa, provenance và chính sách refresh. |

### 16.1. Trình tự khoanh vùng

~~~mermaid
flowchart TD
    A[PGO build hoặc runtime có vấn đề] --> B{Instrumented build thành công?}
    B -->|Không| C[Kiểm tra GraalVM edition, version, target và toolchain]
    B -->|Có| D{Profile file được tạo?}
    D -->|Không| E[Kiểm tra workload, quyền ghi và graceful shutdown]
    D -->|Có| F{Optimized build xác nhận PGO?}
    F -->|Không| G[Kiểm tra --pgo path và plugin arguments]
    F -->|Có| H{Benchmark cải thiện?}
    H -->|Không| I[Đánh giá profile quality và workload distribution]
    H -->|Có| J[Chạy correctness tests và release checks]
    C --> A
    E --> A
    G --> A
    I --> A
~~~

## 17. Bài thực hành: thu PGO profile cho dịch vụ Spring Boot

**Bối cảnh:** dịch vụ quản lý đơn hàng có ba nhóm workload chính: tra cứu catalog, tạo đơn và batch reconciliation. Nhóm muốn tăng throughput của native executable trên Linux x64 và kiểm tra profile có giúp cải thiện latency khi tải cao hay không.

### Nhiệm vụ

1. Xác minh GraalVM distribution có hỗ trợ PGO; ghi JDK, GraalVM, Native Build Tools và native toolchain version.
2. Chốt target OS/architecture, libc, CPU baseline và container runtime.
3. Build native baseline không PGO; lưu executable, build report và benchmark.
4. Build instrumented executable bằng `--pgo-instrument`.
5. Tạo workload script có tỷ lệ catalog/create/reconciliation gần production.
6. Khởi chạy instrumented service với `-XX:ProfilesDumpFile` trỏ đến thư mục writable.
7. Chờ readiness, chạy warm-up rồi chạy workload profile đủ lâu.
8. Dừng service graceful và xác minh file `.iprof` được ghi.
9. Thu thêm profile cho scenario batch hoặc workload khác bằng file riêng.
10. Hợp nhất profiles bằng `native-image-utils merge-pgo-profiles` hoặc truyền danh sách vào `--pgo`.
11. Build optimized native executable trên target được hỗ trợ.
12. Kiểm tra build output để xác nhận PGO profile được sử dụng.
13. Chạy correctness tests, native integration tests và container smoke tests.
14. Benchmark baseline/optimized bằng cùng request mix, CPU/memory limit và số lần lặp.
15. Ghi throughput, p95/p99 latency, CPU, RSS, startup, executable size và build duration.
16. Quyết định giữ PGO, tạo profile mới hoặc quay về baseline dựa trên kết quả.

### Biên bản kết quả

| Bằng chứng | Nội dung cần lưu |
| --- | --- |
| Toolchain | GraalVM distribution/version, JDK, Native Build Tools và C compiler. |
| Target | OS, architecture, libc, CPU baseline và container image. |
| Baseline | Build arguments, output path, size và benchmark. |
| Instrumented build | Command, log và executable path. |
| Workload | Script, request mix, payload, concurrency, duration và dataset. |
| Profile | `.iprof` path, size, timestamp và process shutdown result. |
| Profile sources | Danh sách scenario/profile đầu vào và cách merge. |
| Optimized build | `--pgo` arguments, build log và PGO status. |
| Benchmark | Throughput, p50/p95/p99, CPU, memory và số lần lặp. |
| Decision | Kết quả, regression, profile freshness và next action. |

### Tiêu chí hoàn thành

- [ ] Xác minh PGO khả dụng trên GraalVM distribution/version.
- [ ] Chọn target OS/architecture và native toolchain được hỗ trợ.
- [ ] Tạo được baseline và instrumented native executable.
- [ ] Thu profile từ workload đại diện thay vì toàn bộ unit-test suite một cách máy móc.
- [ ] File `.iprof` được ghi sau graceful shutdown.
- [ ] Biết thu và merge nhiều profile.
- [ ] Optimized build dùng `--pgo` và build output xác nhận PGO.
- [ ] Không phát hành instrumented executable.
- [ ] Benchmark baseline/PGO cùng điều kiện và workload.
- [ ] Lưu provenance để tái lập profile và optimized build.

## 18. Câu hỏi tự đánh giá

1. PGO giúp AOT compiler có thêm loại thông tin nào?
2. PGO profile khác reachability metadata do tracing agent tạo ra như thế nào?
3. Vì sao PGO không có trong GraalVM Community Edition theo tài liệu hiện hành?
4. `--pgo-instrument` tạo ra executable có đặc điểm gì?
5. `-XX:ProfilesDumpFile` dùng để làm gì và profile thường được ghi khi nào?
6. Vì sao instrumented executable không phù hợp để benchmark production performance?
7. Vì sao workload từ toàn bộ unit-test suite có thể hướng compiler tối ưu sai?
8. Khi nào nên thu nhiều profile và khi nào nên merge chúng?
9. Vì sao profile cross-platform thường dùng được nhưng thu trên target platform vẫn là thực hành tốt?
10. Profile cũ có thể gây tác động gì khi hot path thay đổi?
11. Build output cần thể hiện trạng thái nào để xác nhận PGO đã được sử dụng?
12. Những chỉ số nào cần đo ngoài throughput khi so sánh baseline và PGO?

## 19. Tài liệu chính thức

Các option và phạm vi hỗ trợ PGO phụ thuộc GraalVM distribution, release và target platform. Đối chiếu đúng version trước khi cấu hình:

- [GraalVM Native Image — Profile-Guided Optimization](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/PGO/): nguyên lý PGO, profile events và cách thu profile.
- [GraalVM Native Image — Basic Usage of PGO](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/PGO/basic-usage/): instrumented build, `ProfilesDumpFile`, `.iprof` và optimized rebuild.
- [GraalVM Native Image — PGO Frequently Asked Questions](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/PGO/faq/): workload đại diện, unit tests, instrumentation overhead và cross-platform profiles.
- [GraalVM Native Image — Tracking Profile Quality](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/PGO/profile-quality/): profile cũ, refresh schedule, applicability và relevance.
- [GraalVM Native Image — Merging Profiles from Multiple Sources](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/PGO/merging-profiles/): `native-image-utils merge-pgo-profiles`.
- [GraalVM Native Image — Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/): PGO status, optimization level, build report và build artifacts.
- [GraalVM Native Image — Command-line Options](https://www.graalvm.org/latest/reference-manual/native-image/overview/Options/): `--pgo`, `--pgo-instrument`, `--pgo-sampling`, `--target` và option availability theo version.
- [GraalVM Support](https://www.graalvm.org/latest/support/): distribution, certified platforms và phạm vi hỗ trợ hiện hành.

**Điểm cần nhớ:** PGO chỉ hữu ích khi profile mô tả đúng workload cần tối ưu. Hãy dùng GraalVM có hỗ trợ PGO, build instrumented executable, chạy workload đại diện trên nền tảng phù hợp, lưu profile có provenance, build lại với `--pgo` và đo optimized binary trong cùng điều kiện với baseline.

