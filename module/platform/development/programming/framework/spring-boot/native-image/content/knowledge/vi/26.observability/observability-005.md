# Build arguments cần thiết để bật khả năng quan sát được lựa chọn

## 1. Vì sao cần chọn build arguments cho observability?

Native executable được tạo ở build time từ tập class, metadata và tính năng mà GraalVM Native Image được yêu cầu hỗ trợ. Một số khả năng quan sát như debug symbols, báo cáo quá trình build, Java Flight Recorder (JFR), heap dump hoặc JMX có thể cần được bật rõ ràng khi build. Nếu không bật đúng khả năng, người vận hành có thể thiếu dữ liệu khi điều tra sự cố dù ứng dụng vẫn ghi log và expose health endpoint bình thường.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, observability gồm nhiều lớp: log và metric của ứng dụng Spring Boot, trace phân tán, thông tin chẩn đoán của native process, và dữ liệu giúp phân tích chính quá trình Native Image build. Mỗi lớp có cơ chế riêng. Build arguments chỉ bật những tính năng của executable hoặc compiler cần thiết; chúng không tự cấu hình toàn bộ Micrometer, OpenTelemetry hay backend giám sát.

Bài này giúp chọn build arguments theo nhu cầu vận hành, phân biệt build-time diagnostics với runtime monitoring, cấu hình Maven/Gradle và xác minh tính năng thực sự có trong binary được phát hành.

## 2. Phân loại khả năng quan sát

| Nhu cầu | Ví dụ | Thời điểm |
|---|---|---|
| Chẩn đoán build | Build report, analysis diagnostics | Khi Native Image compiler chạy |
| Debug native executable | Debug symbols, source/line information | Build và điều tra process |
| Stack trace rõ hơn | Báo cáo exception stack traces | Runtime |
| Theo dõi ứng dụng | Actuator, Micrometer metrics | Runtime |
| Distributed tracing | OpenTelemetry/Micrometer Tracing | Runtime |
| Profiling/flight recording | JFR nếu runtime và build hỗ trợ | Runtime |
| Memory investigation | Heap dump nếu tính năng được bật và hỗ trợ | Runtime |
| Quản trị/monitoring từ xa | JMX server/client nếu được bật | Runtime |

Không bật mọi tính năng theo mặc định. Chọn theo câu hỏi vận hành cần trả lời, mức nhạy cảm của dữ liệu và chi phí overhead.

## 3. Build arguments và runtime configuration khác nhau

Build argument được truyền cho Native Image compiler và ảnh hưởng executable được tạo. Runtime option/environment được truyền khi chạy executable. Spring application configuration lại là một lớp khác.

Ví dụ:

- `-g` yêu cầu tạo debug information trong executable.
- `--enable-monitoring=...` yêu cầu bật các capability monitoring mà Native Image version hỗ trợ.
- `--emit=...` yêu cầu compiler xuất loại report/diagnostic artifact được hỗ trợ.
- `--logging.level...` là cấu hình logging của ứng dụng, không phải Native Image build argument.
- `management.endpoints.web.exposure.include` điều khiển Actuator endpoint ở runtime, không phải compiler option.

Một executable đã build mà thiếu capability cần thiết có thể phải build lại để bật capability đó. Thay environment variable lúc chạy không thể bổ sung debug symbols hoặc mã monitoring đã bị loại khỏi binary.

## 4. Ghi debug information bằng -g

Native Image hỗ trợ tùy chọn:

```bash
native-image -g -o orders-service ...
```

`-g` yêu cầu tạo debug information cho executable. Debug information giúp debugger và công cụ phân tích native binary ánh xạ địa chỉ máy về symbol/source location khi có đủ thông tin build tương ứng.

Debug symbols hữu ích khi:

- Điều tra crash hoặc native stack trace.
- Dùng debugger/profiler ở mức native.
- Phân tích core dump.
- Ánh xạ frame native về function/source line khi toolchain hỗ trợ.

Debug information có thể làm artifact lớn hơn hoặc tạo thêm file symbol tùy nền tảng/toolchain. Có thể tách symbol khỏi executable và lưu trong artifact store bảo mật theo quy trình của hệ điều hành/build pipeline.

Không đưa file symbol hoặc debug package lên public registry nếu chúng làm lộ thông tin source/path không cần thiết. Giữ symbol gắn với đúng commit và binary digest để phân tích chính xác.

## 5. Exception stack traces

Native Image có tùy chọn:

```bash
native-image -H:+ReportExceptionStackTraces ...
```

Tùy chọn này yêu cầu Native Image báo cáo stack trace chi tiết hơn cho exception trong các trường hợp được hỗ trợ. Tên option và mức độ hỗ trợ có thể phụ thuộc GraalVM version; kiểm tra `native-image --help` hoặc tài liệu đúng release trước khi đưa vào build.

Stack trace hữu ích để xác định exception phát sinh từ application code, framework hoặc dependency. Tuy nhiên, nó không thay thế debug symbols cho debugger native, cũng không bảo đảm mọi frame luôn có source line.

Với production, cân nhắc thông tin stack trace có thể tiết lộ package, class và cấu trúc nội bộ. Log phải được kiểm soát quyền truy cập, retention và masking theo chính sách của hệ thống.

## 6. Build report và diagnostics của Native Image

Build report giúp hiểu compiler đã phân tích và tạo executable như thế nào. Tùy GraalVM release, có thể yêu cầu xuất report bằng option dạng:

```bash
native-image --emit=build-report ...
```

Một số release/plugin có cách bật report hoặc định dạng output khác. Kiểm tra tài liệu của đúng GraalVM version và xác nhận file report được tạo tại vị trí dự kiến. Đừng giả định mọi Native Image version đều hỗ trợ cùng loại report hoặc cùng định dạng.

Build report có thể giúp điều tra:

- Phần nào đóng góp nhiều vào image size.
- Phân tích reachability và các nhóm code được đưa vào.
- Thời gian/chi phí ở các giai đoạn build.
- Các thành phần runtime hoặc metadata có ảnh hưởng đến artifact.

Report build là dữ liệu của compiler, không phải dashboard runtime. Nó không cho biết trực tiếp request latency, error rate hoặc RSS của process đang chạy production.

## 7. Bật các monitoring features được Native Image hỗ trợ

Một số GraalVM Native Image version cung cấp option dạng:

```bash
native-image --enable-monitoring=jfr,heapdump,jmxserver ...
```

Ví dụ minh họa các capability được yêu cầu; tập tên hợp lệ, edition support và giới hạn nền tảng thay đổi theo GraalVM release. Một số phiên bản có thể hỗ trợ các lựa chọn như JFR, heap dump, JMX server/client hoặc nhóm capability khác. Luôn xác minh danh sách bằng tài liệu và `native-image --help` của toolchain thực tế.

Chỉ bật capability cần thiết. JFR phục vụ ghi sự kiện/profiling; heap dump hỗ trợ phân tích object memory; JMX cho phép công cụ quản trị truy cập MBean nếu runtime feature và network policy cho phép.

Không coi việc thêm chuỗi `--enable-monitoring` là đủ. Cần xác minh compiler chấp nhận option, runtime thực sự cung cấp tính năng và container có công cụ/đường truy cập cần thiết.

## 8. JFR: ghi nhận sự kiện và profiling

Java Flight Recorder (JFR) có thể cung cấp dữ liệu về hoạt động JVM/runtime như allocation, GC, thread, lock và sự kiện ứng dụng tùy cấu hình. Native Image có hỗ trợ JFR ở các GraalVM version và cấu hình nhất định, nhưng event set và semantics không nhất thiết giống HotSpot JVM.

Nếu chọn JFR:

1. Xác minh GraalVM distribution/version hỗ trợ JFR cho Native Image.
2. Bật monitoring feature tương ứng ở build time theo tài liệu.
3. Kiểm tra cách bắt đầu recording khi chạy executable.
4. Xác định vị trí lưu recording và giới hạn dung lượng.
5. Bảo vệ file recording vì có thể chứa thông tin nhạy cảm.
6. Thử đọc recording bằng công cụ tương thích với version đã tạo.

Không suy ra JFR đã bật chỉ vì ứng dụng dùng Micrometer hoặc vì có file cấu hình JFR. Cần chạy một recording thử và xác minh file có sự kiện mong muốn.

## 9. Heap dump và điều tra bộ nhớ

Heap dump có thể hữu ích khi cần phân tích object graph, retention và phân bổ bộ nhớ. Native Image có cơ chế heap dump ở những phiên bản/tính năng hỗ trợ; khả năng và lệnh kích hoạt phụ thuộc release.

Trước khi bật:

- Xác minh option `heapdump` được hỗ trợ.
- Xác định đường dẫn output có quyền ghi và đủ dung lượng.
- Đặt giới hạn filesystem/ephemeral storage.
- Kiểm soát ai có thể lấy và đọc dump.
- Thử tạo dump trong staging, không chờ sự cố production đầu tiên.

Heap dump có thể chứa payload, token, thông tin người dùng hoặc dữ liệu nghiệp vụ. Xử lý nó như dữ liệu nhạy cảm: mã hóa khi lưu/truyền, giới hạn truy cập và xóa theo retention policy.

Heap dump của Native Image cũng không nên được giả định có cùng định dạng, công cụ phân tích hoặc mức chi tiết với heap dump của HotSpot. Dùng công cụ được GraalVM version hỗ trợ.

## 10. JMX và bề mặt quản trị

Nếu bật JMX server/client trong native executable, ứng dụng có thể cung cấp hoặc kết nối tới các MBean tùy capability được hỗ trợ. JMX là một giao diện quản trị, do đó cần kiểm soát network exposure.

Không expose JMX port trực tiếp ra internet. Ưu tiên network nội bộ, authentication/authorization phù hợp, TLS khi cần và giới hạn nguồn kết nối. Nếu nền tảng không cần JMX, không bật chỉ vì option tồn tại.

JMX monitoring cũng không thay thế metrics endpoint có schema ổn định cho hệ thống Prometheus/Kubernetes. Chọn cơ chế theo công cụ vận hành đang sử dụng.

## 11. Actuator và Micrometer không được bật bằng Native Image monitoring flags

Spring Boot Actuator cung cấp endpoint như health, info, metrics và prometheus tùy dependency/configuration. Micrometer thu thập metrics ứng dụng và xuất qua registry phù hợp.

Ví dụ cấu hình:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
```

Cần thêm các dependency Actuator và registry tương ứng, ví dụ Prometheus registry nếu muốn expose endpoint Prometheus. Không chỉ thêm YAML rồi kỳ vọng endpoint tự xuất hiện.

Native Image build cần bảo đảm Actuator/Micrometer dependency và metadata được Spring Boot AOT/native support xử lý. Build flags như `--enable-monitoring=jfr` không thay thế `micrometer-registry-prometheus`, và Prometheus registry không tự bật JFR.

## 12. Distributed tracing và OpenTelemetry

Trace phân tán giúp theo dõi request qua nhiều service. Spring Boot có thể tích hợp Micrometer Tracing và exporter/bridge phù hợp; OpenTelemetry agent/SDK cũng có cách tích hợp riêng.

Cần phân biệt:

- Build-time native metadata cho thư viện tracing.
- Runtime endpoint/exporter, service name và sampling configuration.
- Propagation headers giữa service.
- Backend nhận trace như OTLP collector.

Ví dụ cấu hình runtime có thể đặt endpoint exporter và sampling ratio, nhưng property names phụ thuộc stack/version cụ thể. Không hard-code endpoint/credential vào binary.

Native Image compiler flags không tự tạo trace span trong code ứng dụng. Hãy kiểm tra đúng instrumentation, context propagation và exporter bằng integration test trên executable native.

## 13. Cấu hình arguments trong Gradle

Với GraalVM Native Build Tools Gradle plugin, build arguments thường được khai báo trên binary:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add("-g")
            buildArgs.add("-H:+ReportExceptionStackTraces")
            buildArgs.add("--enable-monitoring=jfr")
            buildArgs.add("--emit=build-report")
        }
    }
}
```

Đây là ví dụ minh họa. Không phải mọi GraalVM version đều hỗ trợ toàn bộ option trên; một số option có thể thay đổi, yêu cầu edition hoặc không tương thích với target. Chỉ giữ argument đã xác minh bằng toolchain thực tế.

Có thể tách nhóm argument theo mục đích và build profile, nhưng tránh để cấu hình debug/monitoring thử nghiệm vô tình được áp dụng cho mọi production build. Dùng Gradle task/configuration rõ ràng và lưu log build arguments để tái lập.

## 14. Cấu hình arguments trong Maven

Với Native Maven Plugin, build arguments thường được đặt trong cấu hình plugin:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-g</buildArg>
            <buildArg>-H:+ReportExceptionStackTraces</buildArg>
            <buildArg>--enable-monitoring=jfr</buildArg>
            <buildArg>--emit=build-report</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

Đây là cấu hình minh họa theo cấu trúc plugin; schema, version và cách truyền arguments có thể khác. Xác nhận plugin version trong POM và kiểm tra log compiler để biết argument đã được truyền.

Không copy nguyên cấu hình vào dự án mà chưa kiểm tra option. Một argument không hợp lệ có thể làm native build fail; option được chấp nhận nhưng capability không được dùng cũng không tạo ra observability mong muốn.

## 15. Tách build profile cho diagnostics và production

Có thể tổ chức hai nhóm cấu hình:

| Nhóm | Mục tiêu | Ví dụ |
|---|---|---|
| Diagnostic build | Điều tra lỗi, profiling, build report | Debug symbols, stack trace, report, JFR |
| Production build | Chỉ bật tính năng cần cho vận hành thường xuyên | Exception detail theo policy, monitoring feature thực sự dùng |

Không nhất thiết mọi diagnostic option phải tắt trong production. Ví dụ debug symbols có thể được lưu riêng trong artifact store để hỗ trợ crash analysis mà không phân phối rộng. JFR có thể được bật nếu quy trình vận hành cần và đã đánh giá overhead.

Quyết định phải dựa trên cách vận hành: ai thu thập dữ liệu, ở đâu lưu, thời gian lưu và ai có quyền truy cập.

## 16. Xác minh option trước khi đưa vào pipeline

Mỗi GraalVM version có thể thay đổi option, capability và giới hạn. Trước khi commit build argument:

```bash
native-image --version
native-image --help
native-image --expert-options
```

Dùng `--expert-options` để kiểm tra option nâng cao nếu phiên bản cung cấp; không xem mọi option expert là API ổn định cho production. Đọc tài liệu cùng version, kiểm tra edition và target OS/architecture.

Sau khi build:

- Xác nhận command line/log chứa argument.
- Xác nhận report hoặc debug artifact được tạo.
- Chạy thử tính năng monitoring từ executable.
- Kiểm tra output path và file permissions.
- Đo kích thước binary và RSS.
- Ghi version toolchain cùng digest artifact.

Nếu option bị deprecated hoặc đổi tên, cập nhật theo tài liệu hiện hành thay vì ép dùng cú pháp cũ.

## 17. Bảo mật và chi phí vận hành của observability

Observability tăng khả năng điều tra nhưng cũng có chi phí:

- Debug symbols làm tăng kích thước artifact hoặc tạo file symbol bổ sung.
- JFR/profiling có thể tạo CPU, memory và I/O overhead.
- Heap dump cần dung lượng lớn và có thể chứa dữ liệu nhạy cảm.
- JMX mở thêm bề mặt quản trị/network.
- Stack trace chi tiết có thể tiết lộ cấu trúc nội bộ.
- Build reports có thể chứa tên class, dependency và đường dẫn build.

Cần quy định retention, quyền truy cập, mã hóa và cách xóa dữ liệu. Không bật endpoint quản trị hoặc JMX rộng chỉ để tiện debug. Dùng sampling và thời gian recording có giới hạn khi phù hợp.

## 18. Chẩn đoán khi tính năng không hoạt động

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không có debug symbols | Thiếu `-g` hoặc toolchain không tạo output dự kiến | Kiểm tra build command và binary/symbol files |
| Stack trace thiếu chi tiết | Chưa bật option phù hợp hoặc thông tin bị tối ưu/strip | Kiểm tra version, build flags và runtime trace |
| Không có build report | `--emit` không được hỗ trợ hoặc output path khác | Kiểm tra help/log và report artifact |
| JFR không khởi động | Monitoring feature chưa bật hoặc runtime syntax khác | Kiểm tra version docs và recording command |
| Heap dump thất bại | Capability chưa bật, thiếu quyền hoặc disk space | Kiểm tra build option, path, permission và quota |
| JMX không kết nối | Chưa bật server/client, port/network/auth sai | Kiểm tra listener và network policy |
| Actuator không có metrics | Thiếu dependency/registry hoặc endpoint chưa expose | Kiểm tra Spring configuration |
| Trace không tới backend | Exporter/endpoint/propagation sai | Kiểm tra runtime config và collector connectivity |

Đừng dùng một log “build successful” làm bằng chứng mọi monitoring feature đã hoạt động. Mỗi capability cần một phép xác minh riêng.

## 19. Bài thực hành: chọn observability cho Order API native

**Bối cảnh:** Order API cần crash diagnostics, build report khi điều tra image size, metrics Prometheus thường xuyên và JFR chỉ khi profiling có yêu cầu.

**Bước 1 — Xác định nhu cầu.** Phân loại build report, debug symbols, stack trace, Actuator/Micrometer và JFR theo thời điểm sử dụng.

**Bước 2 — Pin toolchain.** Ghi GraalVM distribution/version, JDK, Native Build Tools và Spring Boot version.

**Bước 3 — Cấu hình diagnostic build.** Thử `-g`, stack trace option và build report option được version hỗ trợ; lưu output riêng.

**Bước 4 — Cấu hình runtime metrics.** Thêm Actuator và Prometheus registry phù hợp; expose endpoint qua network nội bộ.

**Bước 5 — Bật JFR khi cần.** Xác minh monitoring option, chạy recording ngắn trên native executable và mở file bằng công cụ tương thích.

**Bước 6 — Kiểm tra bảo mật.** Xác nhận JMX/Actuator không bị expose ngoài ý muốn; giới hạn quyền đọc recording, dump và build reports.

**Bước 7 — Đo overhead.** So sánh startup, RSS, binary size và CPU với các capability được bật/tắt trong cùng workload.

**Bước 8 — Chuẩn hóa pipeline.** Tách diagnostic build và release build theo nhu cầu, lưu build arguments/toolchain versions cùng artifact.

Tiêu chí hoàn thành: mỗi build argument có mục đích và bằng chứng hoạt động; metrics ứng dụng được cấu hình riêng; diagnostic artifacts được lưu an toàn; chi phí và giới hạn được ghi nhận.

## 20. Kết luận

Build arguments có thể bật những khả năng quan sát quan trọng của GraalVM Native Image như debug information, exception stack traces, build reports và các monitoring features được phiên bản hỗ trợ. Các tính năng này phục vụ những mục tiêu khác nhau và cần được xác minh trên executable thực tế.

Với Spring Boot Native Image, hãy tách compiler diagnostics khỏi Actuator/Micrometer và distributed tracing, pin GraalVM/Native Build Tools version, chỉ bật capability cần thiết, kiểm tra output và đánh giá overhead/bảo mật. Một cấu hình observability tốt phải cho biết dữ liệu nào được tạo, cách thu thập, nơi lưu và ai được phép truy cập.
