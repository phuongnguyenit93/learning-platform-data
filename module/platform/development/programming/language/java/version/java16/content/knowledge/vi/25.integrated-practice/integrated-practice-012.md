# Lập báo cáo tương thích nguồn, runtime, nền tảng và hiệu năng sau nâng JDK

## 1. Mục tiêu của báo cáo nâng JDK

Nâng JDK là thay đổi nền tảng chạy của ứng dụng, không chỉ là thay một đường dẫn cài Java. Một bản nâng cấp có thể ảnh hưởng tới cú pháp biên dịch, API có sẵn, module encapsulation, thư viện bên thứ ba, native library, hành vi bảo mật, dữ liệu locale/timezone, GC và hiệu năng.

Một báo cáo tương thích tốt phải trả lời được bốn nhóm câu hỏi:

1. **Source compatibility:** mã nguồn và dependency có biên dịch được với JDK/compiler đích không? Ứng dụng cần hỗ trợ runtime tối thiểu nào?
2. **Runtime compatibility:** bytecode và thư viện có chạy đúng trên JVM đích không? Có thay đổi API, module access, security default hoặc JVM flag không?
3. **Platform compatibility:** ứng dụng có chạy đúng trên các OS, CPU, ABI, container và native dependency được hỗ trợ không?
4. **Performance compatibility:** latency, throughput, CPU, heap, GC pause, native memory, startup và footprint có nằm trong ngưỡng chấp nhận không?

Báo cáo phải dựa trên bằng chứng có thể lặp lại: build log, test result, dependency inventory, runtime log, benchmark và môi trường đã ghi nhận. Một lần chạy thành công trên máy phát triển chưa đủ để kết luận tương thích.

Phạm vi module Java 16 tập trung vào các cải tiến vẫn hữu ích trong Java hiện đại như record, pattern matching cho `instanceof`, Stream API, đóng gói runtime/application và thay đổi JVM. Java 16 không phải bản LTS; vì vậy, khi lập kế hoạch, hãy chọn JDK đích còn được tổ chức hoặc nhà cung cấp hỗ trợ. Có thể giữ Java 16 làm mốc kiểm tra tính năng/nguồn khi sản phẩm thực sự cần, nhưng không mặc định chọn nó làm runtime triển khai dài hạn.

## 2. Xác định baseline và JDK đích

Trước khi chạy kiểm thử, phải ghi rõ:

- JDK hiện tại của production, ví dụ JDK 16.
- JDK đích và bản phân phối/vendor dự kiến.
- Phiên bản runtime tối thiểu mà sản phẩm cam kết hỗ trợ.
- Hệ điều hành, kiến trúc CPU, container base image và ABI được hỗ trợ.
- Thời hạn hỗ trợ, chính sách cập nhật bảo mật và cách rollback.
- Các thành phần nằm ngoài ứng dụng: application server, agent APM, profiler, native library, script triển khai và công cụ vận hành.

Không nhầm ba khái niệm:

| Khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| JDK build/compiler | Dùng compiler nào để biên dịch source và annotation processor? |
| Java release target | Bytecode và API thấp nhất mà ứng dụng cần tương thích là release nào? |
| Runtime production | JVM nào thực sự chạy ứng dụng sau khi triển khai? |

Ví dụ: nhóm phát triển có thể dùng JDK mới để build, đặt `--release 17` nếu sản phẩm vẫn hỗ trợ Java 17, rồi chạy kiểm thử trên cả runtime tối thiểu và runtime production. Việc build bằng JDK mới không tự động có nghĩa ứng dụng yêu cầu đúng phiên bản JDK đó để chạy.

Nên ghi ma trận mục tiêu trước khi sửa code:

| Hạng mục | Baseline | Target |
| --- | --- | --- |
| JDK/compiler | Phiên bản production hiện tại | JDK được phê duyệt |
| Java release tối thiểu | Release đang cam kết | Giữ nguyên hoặc nâng có chủ đích |
| OS/CPU | Các target hiện tại | Các target sẽ tiếp tục hỗ trợ |
| Container | Base image hiện tại | Image mới, libc và CA certificates đã xác minh |
| Collector/JVM flags | Cấu hình production hiện tại | Defaults/flags đã kiểm thử trên JDK đích |

## 3. Kiểm kê ứng dụng trước khi nâng

Tạo inventory có phiên bản cụ thể cho:

- Module/source code, module descriptor và multi-release JAR.
- Build tool, compiler plugin, wrapper, annotation processor và code generator.
- Dependency trực tiếp, dependency bắc cầu, framework, agent và thư viện logging.
- API nội bộ của JDK, reflection sâu, JNI/FFM và native library.
- JVM flags, system properties, environment variables, startup script và service definition.
- Resource bên ngoài: truststore, keystore, font, timezone/locale data, file cấu hình và template.
- Công cụ build/deploy: CI image, Dockerfile, installer, `jlink`, `jpackage` và script vận hành.

Giữ lại baseline để so sánh:

1. Commit/tag source đang chạy production.
2. Build artifact và checksum.
3. JVM command line và environment.
4. Dependency tree và SBOM nếu dự án có tạo.
5. Test report, GC log, JFR hoặc APM metrics.
6. Workload, dữ liệu thử nghiệm và cách tạo tải.

Nếu không có baseline, rất khó xác định thay đổi nào do JDK, thay đổi nào do code, dependency, cấu hình hoặc hạ tầng.

## 4. Kiểm tra source compatibility bằng javac --release

`javac --release N` là cách phù hợp để biên dịch trên JDK mới nhưng giới hạn ngôn ngữ, bytecode và Java SE API theo release đích. Ví dụ nếu sản phẩm cam kết chạy từ Java 17:

~~~powershell
javac --release 17 -d out src\com\example\Main.java
~~~

Không nên chỉ dùng cặp `-source` và `-target` khi cần bảo đảm API tương thích. Hai tùy chọn này điều khiển cú pháp và bytecode, nhưng không tự giới hạn toàn bộ API JDK mà compiler mới nhìn thấy. `--release` kết hợp các ràng buộc cần thiết cho release được chọn.

Nếu sản phẩm đã nâng baseline và chỉ chạy trên JDK mới, đặt release tương ứng với chính sách hỗ trợ. Không giữ `--release 16` chỉ vì một số feature được giới thiệu ở Java 16; hãy chọn mức thấp nhất mà sản phẩm thực sự cần hỗ trợ.

Kiểm tra build tool:

**Maven Compiler Plugin**

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

**Gradle Java toolchain**

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Ví dụ dùng release 17 chỉ minh họa sản phẩm có runtime tối thiểu là Java 17. Hãy thay bằng release được phê duyệt của dự án và khóa phiên bản build tool/plugin để build có thể tái lập.

## 5. Rà soát các tính năng Java 16 trong source

Khi nâng từ Java 16, hãy xác nhận các feature được dùng đúng theo semantics hiện hành:

| Feature | Kiểm tra source và test |
| --- | --- |
| Record | Constructor compact/canonical, validation, equals/hashCode/toString, immutability nông và serialization |
| Pattern matching cho `instanceof` | Nhánh true/false, flow scoping của pattern variable, null và logic điều kiện phức hợp |
| `Stream.toList()` | Kết quả là list không sửa đổi được; kiểm tra nơi gọi có đang cố add/remove/sort hay không |
| `Stream.mapMulti()` | Xác minh hành vi flatten, thứ tự phần tử, số phần tử phát ra và xử lý stream lớn |
| `jpackage`/`jlink` | Kiểm tra runtime image, module cần thiết, launcher, resource và installer trên target OS |

Ví dụ record:

~~~java
public record CustomerId(String value) {
    public CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
    }
}
~~~

Record là carrier cho dữ liệu với state component cố định, nhưng tính bất biến chỉ là nông. Nếu component chứa một collection có thể sửa đổi, caller vẫn có thể thay đổi nội dung collection trừ khi constructor tạo defensive copy.

Ví dụ pattern matching:

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
~~~

Kiểm thử cả trường hợp `null`, kiểu không khớp và nhánh logic ngắn mạch. Pattern variable chỉ có scope ở nơi compiler xác định nó chắc chắn đã được match.

Ví dụ Stream:

~~~java
List<String> names = customers.stream()
        .map(Customer::name)
        .filter(Objects::nonNull)
        .toList();
~~~

`Stream.toList()` trả về list không sửa đổi được. Nếu logic cần collection mutable, hãy dùng collector phù hợp, ví dụ `Collectors.toCollection(ArrayList::new)`. Đừng thay thế máy móc giữa `toList()` và `Collectors.toList()` mà không kiểm tra contract mutability và downstream caller.

## 6. Kiểm tra API nội bộ, deprecated API và dependency

Một ứng dụng có thể biên dịch thành công nhưng vẫn phụ thuộc API nội bộ hoặc API đã deprecated. Dùng các công cụ JDK để tìm rủi ro tĩnh:

Tìm dependency tới JDK internal API:

~~~powershell
jdeps --jdk-internals --recursive --class-path "lib\*" app.jar
~~~

Kiểm tra API đã deprecated tại release mục tiêu:

~~~powershell
jdeprscan --release 17 --class-path "lib\*" app.jar
~~~

Kiểm tra dependency tree bằng build tool, ví dụ:

~~~powershell
mvn dependency:tree
~~~

Hoặc:

~~~powershell
gradlew dependencies
~~~

Kết quả cần đưa vào báo cáo:

- Thư viện nào tham chiếu JDK internal API?
- API nào đã deprecated hoặc bị loại bỏ ở release đích?
- Dependency nào chưa có bản hỗ trợ JDK đích?
- Có dependency bắc cầu trùng phiên bản hoặc kéo theo native binary cũ không?
- Có agent, framework hoặc annotation processor chỉ hỗ trợ một số JDK nhất định không?

`jdeps` và `jdeprscan` phân tích bytecode tĩnh. Chúng không phát hiện đầy đủ tên class được ghép động, reflection theo cấu hình, class sinh lúc runtime, JNI call, service provider được nạp động hoặc code chỉ chạy ở production. Vì vậy, kết quả sạch không thay thế integration test và kiểm tra source/config.

## 7. Kiểm tra module encapsulation và reflection

Từ JDK 16, strong encapsulation đối với phần lớn JDK internals được áp dụng mặc định; JDK 17 tiếp tục đóng gói mạnh các thành phần nội bộ. Thư viện cũ dùng reflection sâu vào private member của JDK có thể gặp `InaccessibleObjectException` khi chạy trên runtime mới.

Quy trình:

1. Tìm stack trace đầu tiên chỉ ra thư viện thực hiện reflection.
2. Xác định module/package nguồn và module gọi.
3. Nâng cấp framework hoặc thay cách truy cập bằng API công khai.
4. Nếu cần ngoại lệ tạm thời, mở đúng package cho đúng named module bằng `--add-opens` hoặc qualified `opens` trong `module-info.java`.
5. Chỉ dùng `ALL-UNNAMED` khi consumer thực sự nằm trên classpath và đã đánh giá phạm vi mọi unnamed module.

Không dùng `--illegal-access` như giải pháp. Tùy chọn chuyển tiếp này không khôi phục quyền truy cập từ JDK 17. Không thêm hàng loạt `--add-opens=...=ALL-UNNAMED` vào production để che lỗi dependency.

Ghi từng ngoại lệ vào báo cáo với package, module được mở, thư viện phụ thuộc, lý do và kế hoạch loại bỏ. Đây là một tiêu chí chấp nhận có thời hạn, không phải cấu hình mặc định lâu dài.

## 8. Kiểm tra runtime flags và hành vi JVM

Flag JVM có thể đổi mặc định, bị deprecated/obsolete hoặc bị loại bỏ qua các release. Trước khi triển khai:

~~~powershell
java -version
java -X
java -XX:+PrintFlagsFinal -version
java -Xlog:help
~~~

Với tiến trình đang chạy:

~~~powershell
jcmd 12345 VM.command_line
jcmd 12345 VM.flags -all
jcmd 12345 VM.version
~~~

Thay PID bằng PID thật. So sánh flag đang có với tài liệu của JDK đích, không chỉ so sánh startup script.

Các điểm cần rà soát:

- GC collector và các flag gắn với collector cũ.
- GC logging: chuyển sang Unified Logging `-Xlog` thay cho nhóm flag legacy như `PrintGCDetails`.
- Heap sizing, metaspace, compressed class space và container memory.
- Thread stack, direct memory, code cache và native memory.
- Agent APM/profiler, JMX, JDWP và service wrapper.
- Flag thử nghiệm hoặc internal flag không có cam kết tương thích.

Không sao chép toàn bộ JVM options của runtime cũ sang JDK mới. Bắt đầu với defaults của JDK đích, chỉ thêm flag có lý do đo được, rồi benchmark lại.

## 9. Kiểm tra thay đổi API, charset, security và dữ liệu môi trường

Kiểm thử runtime phải bao gồm cả hành vi mặc định, không chỉ khả năng khởi động:

**Charset và file**

Từ JDK 18, UTF-8 trở thành default charset trên các nền tảng được hỗ trợ theo JEP 400. Nếu ứng dụng dựa vào charset mặc định cũ, dữ liệu đọc/ghi có thể thay đổi. Khai báo charset rõ ràng trong giao thức và file format, ví dụ `StandardCharsets.UTF_8`, thay vì dựa vào default.

**TLS và security**

- Kiểm tra TLS protocol, cipher suite và thuật toán bị disabled theo security policy mới.
- Kiểm tra truststore/keystore, CA certificates, client certificate và hostname verification.
- Kiểm tra provider JCA/JSSE, chữ ký số, key size và thuật toán ứng dụng đang dùng.
- Không hạ security level chỉ để làm một server cũ kết nối được; ghi nhận tương thích và phương án nâng server.

**Locale và timezone**

- Kiểm tra định dạng ngày/giờ, số, tiền tệ và ngôn ngữ.
- Kiểm tra timezone database và các thay đổi quy tắc DST.
- Dùng dữ liệu timezone/locale của runtime đích và test các mốc biên quan trọng.

**Reflection, serialization và API**

- Kiểm tra serializer/ORM/proxy, record và constructor semantics.
- Kiểm tra định dạng serialized data nếu ứng dụng lưu object qua phiên bản.
- Kiểm tra API bị deprecated/removed, security manager assumptions và JDK internal dependencies.

Ghi rõ dữ liệu kiểm thử và expected result. Ví dụ file UTF-8 có dấu tiếng Việt, chứng thư TLS của môi trường staging, timestamp quanh thời điểm đổi DST và dữ liệu locale đại diện.

## 10. Kiểm tra tương thích OS, CPU, ABI và native library

Ứng dụng Java thuần thường dễ di chuyển hơn ứng dụng có JNI/FFM, native database driver, compression, cryptography hoặc codec. Với mỗi target, lập ma trận:

| OS | CPU/JVM | Native dependency | Kiểm tra |
| --- | --- | --- | --- |
| Windows | x86_64/ARM64 | DLL và C/C++ runtime | PE architecture, dependency DLL, quyền file và installer |
| Linux | x86_64/AArch64 | ELF shared object | glibc/musl, SONAME, RPATH/RUNPATH và base image |
| macOS | Intel/Apple Silicon | Mach-O dylib | architecture slice, deployment target, code signing/notarization |

`System.loadLibrary()` tìm thư viện theo tên logic và cơ chế native library path; `System.load()` nhận đường dẫn tuyệt đối. Tìm được file native chính chưa chắc đã tìm được dependency bậc hai của hệ điều hành.

Nếu dùng FFM API, nhớ rằng API này không biến native binary thành portable. Vẫn phải phân phối đúng OS/CPU/ABI và kiểm tra native access policy của JDK đích. Với dự án mới cần gọi C function, FFM API đã ổn định từ JDK 22; JNI vẫn phù hợp khi hệ sinh thái hoặc binding hiện có phụ thuộc JNI.

Kiểm thử native dependency trên máy sạch hoặc container đúng base image. Không chỉ test trên máy build vì máy đó có thể đã cài sẵn DLL/SO/DYLIB mà gói phát hành quên mang theo.

## 11. Kiểm tra jlink và jpackage sau nâng JDK

`jlink` tạo runtime image tùy biến từ các module JDK. `jpackage` đóng gói ứng dụng thành application image hoặc installer theo nền tảng. Khi nâng JDK, cần tạo lại runtime image và installer bằng toolchain tương ứng; không mặc định runtime image cũ dùng được với JDK mới.

Xác định module phụ thuộc tĩnh:

~~~powershell
jdeps --print-module-deps --recursive app.jar
~~~

Kết quả là điểm bắt đầu. Reflection, JNI, service loading, resource bundle và module được nạp động có thể cần bổ sung module bằng kiểm tra thực tế. Nếu ứng dụng dùng service provider, đánh giá `jlink --bind-services` theo yêu cầu của provider và module graph.

Ví dụ tạo runtime image:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" `
      --add-modules com.example.app `
      --output runtime-image
~~~

Đóng gói application image:

~~~powershell
jpackage --type app-image `
         --name SampleApp `
         --module-path mods `
         --module com.example.app/com.example.app.Main `
         --runtime-image runtime-image `
         --dest dist
~~~

Ví dụ cần điều chỉnh module path, main class, resource và native library của dự án. `jpackage` tạo installer cho nền tảng đang build; cần pipeline riêng hoặc build host phù hợp cho Windows, Linux và macOS.

Kiểm tra launcher, JVM options, resource path, user config directory, native library, file permissions, shortcut/service và uninstall/upgrade behavior. Không lưu config/data người dùng trong application image hoặc thư mục cài đặt.

## 12. Thiết kế benchmark so sánh hiệu năng công bằng

Không kết luận JDK mới nhanh hơn/chậm hơn từ một lần chạy. So sánh phải giữ các điều kiện càng giống nhau càng tốt:

- Cùng source commit và dependency version, trừ thay đổi bắt buộc đã ghi nhận.
- Cùng phần cứng/VM, CPU quota, memory limit, OS và container base image nếu mục tiêu là đo tác động JDK.
- Cùng dữ liệu, request mix, concurrency, warm-up và thời lượng đo.
- Cùng cấu hình ứng dụng; riêng JVM flags phải được ghi rõ và kiểm tra có còn hợp lệ.
- Chạy lặp nhiều lần, có thứ tự hoặc cách phân bổ baseline/candidate giảm ảnh hưởng tải nền.

Đo ít nhất:

| Nhóm | Chỉ số |
| --- | --- |
| Latency | p50, p95, p99, maximum và timeout/error rate |
| Throughput | Request/transaction mỗi giây, công việc hoàn thành mỗi phút |
| CPU | CPU utilization, throttling, CPU time/request |
| Heap/allocation | Heap occupancy, allocation rate, live set sau GC |
| GC | Pause count, p95/p99/max pause, tổng pause, Full GC/concurrent cycle |
| Native memory | RSS, committed heap, Metaspace, direct memory và NMT category |
| Startup | Thời gian khởi động, thời gian ready, thời gian warm-up |
| Footprint | Kích thước runtime image, installer và mức dùng disk |

Đặt ngưỡng chấp nhận trước khi chạy. Ví dụ p99 không được tăng quá 5%, throughput không giảm quá 3%, error rate không tăng và memory peak phải nằm trong giới hạn container. Các con số phải do chủ sản phẩm/SLO quyết định, không dùng như ngưỡng chung cho mọi ứng dụng.

## 13. Dùng JFR và GC log để giải thích chênh lệch

Khi benchmark cho thấy khác biệt, cần thu thập dữ liệu giải thích:

**Unified GC logging**

~~~powershell
java "-Xlog:gc*:file=logs/gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=20M" -jar app.jar
~~~

So sánh pause frequency, pause duration, heap before/after, Full GC, concurrent cycle và phase breakdown. Khi cần, bật `gc*=debug`, `gc+phases=debug`, `gc+cpu=info` hoặc `safepoint=info` có chọn lọc.

**Java Flight Recorder**

~~~powershell
java -XX:StartFlightRecording=filename=recording.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

Hoặc bắt đầu recording trên tiến trình đang chạy:

~~~powershell
jcmd 12345 JFR.start name=upgrade settings=profile duration=5m filename=upgrade.jfr
~~~

Đọc tổng quan recording:

~~~powershell
jfr summary upgrade.jfr
~~~

JFR giúp kiểm tra CPU hot methods, allocation, lock contention, thread activity, GC và các sự kiện runtime. Recording profile có overhead; dùng cùng settings và thời gian đo cho baseline/candidate, hoặc chọn settings phù hợp với production policy.

Không chỉ nhìn GC log để giải thích mọi chênh lệch. Nếu p99 tăng nhưng GC pause không tăng, hãy xem CPU hot methods, lock, I/O, network, thread scheduling và downstream dependency.

## 14. Lập test matrix và tiêu chí chấp nhận

Một ma trận thực tế có thể gồm:

| Lớp kiểm thử | Nội dung | Bằng chứng cần lưu |
| --- | --- | --- |
| Compile | Build bằng JDK đích, `--release`, annotation processor | Build log, compiler version, warnings |
| Unit | Logic record, pattern matching, Stream semantics | Test report, coverage liên quan |
| Integration | Database, messaging, HTTP/TLS, serialization, reflection | Test report, server/client log |
| Runtime | Startup, shutdown, flags, JMX/JFR, GC | JVM command line, GC/JFR recording |
| Platform | OS/CPU, container, native library, installer | Matrix result, binary metadata, install log |
| Security | Truststore, TLS, provider, permissions, dependency scan | Security test report |
| Performance | Load/stress/soak test cùng workload | Raw result, percentile, resource metrics |
| Operations | Deploy, rollback, upgrade, backup/restore | Runbook và rehearsal report |

Định nghĩa rõ trạng thái:

- **PASS:** đã chạy trên môi trường xác định và đạt tiêu chí.
- **FAIL:** có lỗi tái hiện hoặc vượt ngưỡng chấp nhận.
- **BLOCKED:** chưa kiểm thử được do thiếu môi trường, license, native binary hoặc dependency.
- **NOT TESTED:** chưa có bằng chứng; không được ghi thành PASS.

Một release chỉ được chấp nhận khi mọi hạng mục bắt buộc đạt PASS hoặc có ngoại lệ được chủ sở hữu phê duyệt, có phạm vi và thời hạn xử lý. BLOCKED/NOT TESTED phải hiển thị trong báo cáo.

## 15. Mẫu báo cáo tương thích sau nâng JDK

Có thể dùng cấu trúc sau làm báo cáo cho từng dự án:

~~~text
PROJECT:
OWNER:
REPORT DATE:
SOURCE COMMIT:

BASELINE
- Production JDK/vendor:
- Runtime flags:
- Build tool and version:
- OS/CPU/container:
- Current performance baseline:

TARGET
- Target JDK/vendor:
- Minimum supported Java release:
- Build compiler/toolchain:
- Target OS/CPU/container:
- Planned rollout and rollback:

SOURCE COMPATIBILITY
- Compile result:
- --release value:
- jdeps --jdk-internals:
- jdeprscan:
- Dependency/annotation processor status:
- Source/API changes:
- Exceptions:

RUNTIME COMPATIBILITY
- Startup/shutdown:
- JVM flags removed/changed:
- Module/reflection:
- TLS/security/provider:
- Charset/locale/timezone:
- Serialization/configuration:
- Exceptions:

PLATFORM COMPATIBILITY
- Windows:
- Linux:
- macOS:
- CPU/ABI/native libraries:
- jlink/jpackage image and installer:
- File permissions/user data paths:
- Exceptions:

PERFORMANCE
- Workload and environment:
- Throughput:
- p50/p95/p99/max latency:
- Error/timeout rate:
- CPU:
- Heap/allocation/GC:
- Native memory/RSS:
- Startup and footprint:
- Comparison with baseline:

DECISION
- Source compatibility: PASS/FAIL/BLOCKED/NOT TESTED
- Runtime compatibility: PASS/FAIL/BLOCKED/NOT TESTED
- Platform compatibility: PASS/FAIL/BLOCKED/NOT TESTED
- Performance compatibility: PASS/FAIL/BLOCKED/NOT TESTED
- Known issues and owners:
- Approved exceptions and expiry:
- Rollback trigger:
- Final decision: GO / NO-GO
~~~

Không để trường báo cáo trống mà không có trạng thái. Ghi rõ phiên bản JDK/vendor, commit, OS/CPU và ngày đo để người khác có thể tái lập kết quả.

## 16. Ví dụ cách ghi nhận một kết quả

Ví dụ giả định cho ứng dụng web nâng từ JDK 16 lên JDK 25:

| Hạng mục | Kết quả kiểm thử giả định | Trạng thái |
| --- | --- | --- |
| Source | Build bằng JDK 25 với `--release 17`; dependency tree không còn JDK internal API đã xác định | PASS |
| Runtime | Framework ORM cũ cần reflection; nâng framework đã loại bỏ cấu hình `--add-opens` | PASS |
| TLS/charset | HTTPS staging đạt; file CSV tiếng Việt đọc/ghi UTF-8 ổn định | PASS |
| Platform | Linux x86_64 container đạt; Windows ARM64 chưa có native driver để kiểm thử | BLOCKED |
| Performance | Throughput tăng 4%; p99 tăng 2%; GC pause p99 giảm 8% trong cùng workload | PASS theo ngưỡng giả định |
| Operations | App image chạy bằng tài khoản thường; config nằm ở user data directory; rollback đã diễn tập | PASS |

Quyết định trong ví dụ này chưa thể là GO nếu Windows ARM64 là nền tảng bắt buộc. Nếu nền tảng đó không thuộc phạm vi sản phẩm, cần ghi rõ quyết định loại khỏi support matrix và được chủ sở hữu chấp thuận trước khi phát hành.

Số liệu trên chỉ minh họa cách trình bày; không phải benchmark Java 16 so với Java 25 đã được thực thi.

## 17. Checklist cuối cùng trước khi phát hành

- Đã chọn JDK đích còn được hỗ trợ và ghi rõ runtime tối thiểu.
- Đã khóa build toolchain và dùng `--release` theo baseline sản phẩm.
- Đã rà soát record, pattern matching, Stream API và các semantics liên quan.
- Đã chạy `jdeps`, `jdeprscan`, dependency scan và kiểm tra dynamic/reflection path.
- Đã xử lý module encapsulation, JVM flags và security defaults.
- Đã kiểm tra UTF-8, TLS, truststore, locale, timezone và serialization.
- Đã kiểm thử từng OS/CPU/ABI và native dependency được hỗ trợ.
- Đã tạo lại runtime image/installer bằng JDK đích và thử trên máy sạch.
- Đã so sánh throughput, p95/p99, GC, CPU, native memory và startup với baseline.
- Đã có rollback plan, monitoring và người chịu trách nhiệm cho ngoại lệ.
- Không đánh dấu PASS cho hạng mục chưa chạy.

**Ghi nhớ:** Báo cáo nâng JDK phải chứng minh bốn lớp tương thích: source, runtime, platform và performance. Dùng `--release` để khóa API/language target, công cụ phân tích dependency để tìm rủi ro tĩnh, integration test để phát hiện hành vi runtime, ma trận OS/CPU để xác nhận native/package, và benchmark/JFR/GC log để so sánh hiệu năng. Chỉ quyết định GO khi mọi target bắt buộc có bằng chứng đạt tiêu chí và có phương án rollback.

## Nguồn tham khảo chính thức

- [The javac Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [The jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [The jdeprscan Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeprscan.html)
- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [The jpackage Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Java Flight Recorder Runtime Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/jfapi/index.html)
- [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400)
- [JEP 396: Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [JEP 395: Records](https://openjdk.org/jeps/395)
- [JEP 394: Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 387: Elastic Metaspace](https://openjdk.org/jeps/387)
- [JEP 392: Packaging Tool](https://openjdk.org/jeps/392)
