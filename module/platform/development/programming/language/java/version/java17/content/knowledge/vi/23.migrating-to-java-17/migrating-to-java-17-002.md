# Chạy thử ứng dụng trước khi đồng thời sửa nhiều thành phần khi nâng cấp lên Java 17

## 1. Vì sao cần chạy thử trước khi thay đổi nhiều thứ?

Nâng cấp một ứng dụng lên Java 17 thường liên quan đến nhiều lớp khác nhau: JDK chạy ứng dụng, công cụ build, compiler, thư viện bên thứ ba, framework, plugin, cấu hình JVM, container image và đôi khi cả mã nguồn. Nếu thay tất cả cùng một lúc rồi mới chạy thử, khi ứng dụng lỗi sẽ rất khó biết nguyên nhân nằm ở đâu.

Ví dụ, sau một lần nâng cấp đồng thời:

- JDK được đổi từ 11 lên 17.
- Framework được nâng phiên bản.
- Một thư viện logging được thay thế.
- Compiler chuyển sang `--release 17`.
- Các cờ JVM cũ được thay đổi.

Nếu ứng dụng không khởi động, có thể do framework chưa tương thích, một API nội bộ bị đóng gói mạnh, plugin build không chạy được, hoặc một cờ JVM đã bị loại bỏ. Nếu không có kết quả chạy trung gian, các nguyên nhân này bị trộn lẫn.

Một cách chuyển đổi dễ kiểm soát hơn là **chạy thử artifact hiện tại trên JDK 17 trước**, giữ nguyên các thành phần khác trong phạm vi có thể. Kết quả này cho biết ứng dụng và các dependency hiện tại có tương thích ở mức runtime hay không. Sau đó mới nâng cấp build, dependency, cấu hình và mã nguồn theo từng nhóm thay đổi.

Mục tiêu không phải là tránh mọi thay đổi cùng lúc bằng quy tắc cứng. Mục tiêu là tạo các mốc có thể so sánh, để mỗi lần thay đổi có một giả thuyết, một kết quả kiểm chứng và một phương án quay lui.

Sau bài học, người học cần:

1. Lập baseline cho ứng dụng trên JDK đang dùng.
2. Chạy cùng artifact trên JDK 17 để kiểm tra tương thích runtime.
3. Phân biệt lỗi do runtime, dependency, build tool, compiler và cấu hình.
4. Thay đổi từng nhóm thành phần theo trình tự có thể kiểm chứng.
5. Dùng công cụ JDK để tìm dependency tới API nội bộ hoặc API deprecated.
6. Kiểm tra startup, health check, luồng nghiệp vụ và hành vi vận hành.
7. Ghi nhận kết quả, quyết định tiếp tục hoặc rollback dựa trên bằng chứng.

## 2. Xác định chính xác phạm vi nâng cấp

Trước khi thay đổi, hãy viết rõ điều gì đang được nâng cấp. Cụm từ “nâng cấp lên Java 17” có thể chỉ nhiều việc khác nhau:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Runtime JDK | Ứng dụng sẽ chạy bằng JDK 17 nào và từ nhà cung cấp nào? |
| Build JDK | Máy build/CI có dùng JDK 17 không? |
| Compiler target | Mã được biên dịch để chạy trên Java 17 hay vẫn cần hỗ trợ runtime cũ? |
| Dependency | Các thư viện runtime và compile-time có hỗ trợ JDK 17 không? |
| Build tool/plugin | Maven/Gradle và plugin hiện tại có chạy ổn với JDK 17 không? |
| Framework | Framework có phiên bản hỗ trợ Java 17 và các dependency tương ứng không? |
| JVM options | Có cờ JVM đã bị loại bỏ, đổi hành vi hoặc không còn cần thiết không? |
| Deployment | Container image, startup script, health check và giám sát có dùng đúng JDK không? |
| Source code | Có cần dùng API/language feature mới của Java 17 không? |

Không đồng nhất các câu hỏi này. Một ứng dụng có thể chạy trên runtime Java 17 dù bytecode được biên dịch từ Java 11. Ngược lại, compiler có thể biên dịch thành công nhưng một thư viện chỉ được nạp trong production lại không tương thích với JDK 17.

### 2.1. Phân biệt chạy trên Java 17 với biên dịch cho Java 17

Đây là hai bước độc lập:

- **Runtime migration:** dùng JVM 17 để chạy artifact hiện tại.
- **Build/compile migration:** dùng toolchain/compiler phù hợp và chọn API/class-file target cho phiên bản Java mong muốn.

Một class file được biên dịch cho Java 11 có thể chạy trên Java 17 nếu các dependency và hành vi runtime tương thích. Class file Java 17 có major version 61. Runtime cũ hơn Java 17 không thể nạp class file version 61.

Tùy chọn `javac --release 17` vừa đặt ngôn ngữ, vừa giới hạn API Java SE được dùng, vừa tạo bytecode cho release 17. Nó không phải tùy chọn để chọn JVM chạy chương trình.

## 3. Lập baseline trước khi đổi JDK

Baseline là kết quả quan sát được từ phiên bản hiện tại. Không có baseline thì rất khó kết luận Java 17 làm thay đổi hành vi nào.

### 3.1. Ghi nhận môi trường hiện tại

Lưu các thông tin:

- Phiên bản JDK và nhà cung cấp JDK.
- Hệ điều hành, kiến trúc CPU và môi trường container/VM.
- Lệnh khởi chạy đầy đủ và JVM flags.
- Phiên bản ứng dụng, commit/build number.
- Dependency graph và phiên bản framework.
- Biến môi trường và cấu hình ứng dụng có ảnh hưởng tới runtime.
- CPU quota, memory limit, heap và số replica.
- Dịch vụ phụ thuộc như database, cache, message broker và HTTP service.

Ví dụ:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Với tiến trình đang chạy, có thể dùng `jcmd` nếu JDK hiện tại hỗ trợ:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
~~~

Không đưa password, token hoặc secret trong command line vào báo cáo baseline. Hãy lưu thông tin cấu hình theo chính sách bảo mật của dự án.

### 3.2. Chọn các luồng nghiệp vụ đại diện

Không chỉ kiểm tra một endpoint trả về HTTP 200. Chọn các luồng thể hiện những thành phần quan trọng:

- Khởi động ứng dụng và hoàn tất dependency injection.
- Kết nối database và thực hiện truy vấn.
- Đọc/ghi file hoặc object storage.
- Gửi/nhận message nếu ứng dụng dùng queue.
- Gọi dịch vụ HTTP bên ngoài.
- Xác thực và phân quyền.
- Xử lý dữ liệu Unicode, ngày giờ và locale.
- Các tác vụ batch hoặc scheduled job.
- Shutdown bình thường và xử lý signal/termination.

Với từng luồng, ghi input, output kỳ vọng, status, side effect và tiêu chí thành công. Nếu có dữ liệu nhạy cảm, dùng fixture đã ẩn danh hoặc dữ liệu kiểm thử được phê duyệt.

### 3.3. Đo hành vi trước khi nâng cấp

| Nhóm | Baseline cần lưu |
|---|---|
| Startup | Thời gian khởi động, thời điểm health check sẵn sàng |
| Functional | Kết quả test, response/status, dữ liệu được tạo/cập nhật |
| Performance | Throughput, p50/p95/p99 latency, error rate |
| JVM | Heap, GC, thread count, class loading |
| Resource | CPU, RSS, memory limit, file descriptor nếu liên quan |
| Logs | Warning/error thường gặp và các exception đã biết |
| Operations | Health check, readiness/liveness, shutdown, restart |

Không cần đo mọi chỉ số có thể có. Hãy chọn những chỉ số liên quan đến yêu cầu vận hành và lưu cùng workload để có thể so sánh sau đó.

## 4. Chạy nguyên artifact hiện tại trên JDK 17

Đây là mốc quan trọng để tách tương thích runtime khỏi thay đổi build và source.

### 4.1. Giữ artifact cố định

Lấy đúng JAR/WAR/distribution đang chạy trên JDK cũ. Ghi hash hoặc build ID để xác nhận artifact không bị rebuild trong bước thử này.

Nếu ứng dụng được đóng gói thành fat JAR, container image hoặc distribution nhiều module, giữ nguyên nội dung artifact và thay runtime JDK trong môi trường thử nghiệm. Chỉ thay JDK cần thiết để chạy.

### 4.2. Chạy với JDK 17

Ví dụ:

~~~bash
java -version
java -jar application.jar
~~~

Đảm bảo `java` trong `PATH` thực sự là JDK 17. Trên môi trường có nhiều JDK, dùng đường dẫn đầy đủ tới executable để tránh nhầm:

~~~bash
/opt/jdk-17/bin/java -version
/opt/jdk-17/bin/java -jar application.jar
~~~

Nếu ứng dụng cần startup script, agent, native library hoặc JVM option riêng, chạy đúng entry point của môi trường thử nghiệm và ghi lại mọi khác biệt.

### 4.3. Giữ nguyên các yếu tố còn lại

Trong lần chạy đầu, cố gắng giữ nguyên:

- Artifact và dependency đã đóng gói.
- Application configuration.
- Dataset và request mix.
- Database/schema và các dịch vụ phụ thuộc tương đương.
- CPU/memory limit và số replica.
- JVM options, nếu các option đó còn được Java 17 chấp nhận.

Nếu một JVM option cũ khiến Java 17 không khởi động, ghi nhận lỗi và chỉ thay đổi tối thiểu để JVM có thể chạy. Đừng nhân tiện thay collector, heap size, framework và thư viện trong cùng lần thử. Cần phân biệt “bỏ một cờ không còn được hỗ trợ để JVM khởi động” với “tối ưu lại toàn bộ cấu hình JVM”.

### 4.4. Vì sao chạy artifact cũ có giá trị?

Nếu cùng một artifact chạy tốt trên runtime cũ nhưng thất bại trên Java 17, vấn đề có thể thuộc về:

- Thay đổi hoặc loại bỏ API trong JDK.
- Strong encapsulation của module system.
- Thư viện dùng API nội bộ hoặc reflection sâu.
- Native/JNI component không tương thích.
- JVM option hoặc collector option đã bị loại bỏ.
- Hành vi runtime, bảo mật hoặc môi trường thay đổi.

Nếu artifact chạy tốt trên Java 17, đó là bằng chứng tích cực về runtime compatibility cho các luồng đã thử. Nó chưa chứng minh build pipeline, compiler, plugin hoặc mọi đường code hiếm gặp đều tương thích.

## 5. Kiểm tra startup và hành vi thực tế

### 5.1. Startup và readiness

Sau khi khởi động:

1. Xác nhận process dùng đúng JDK 17.
2. Chờ ứng dụng hoàn tất khởi tạo, không chỉ kiểm tra process còn tồn tại.
3. Kiểm tra readiness/health endpoint.
4. Xác nhận connection pool, message consumer và scheduler đã sẵn sàng.
5. Kiểm tra log startup và warning.

Một JVM process sống không có nghĩa ứng dụng đã sẵn sàng nhận traffic. Readiness nên phản ánh trạng thái các dependency quan trọng theo thiết kế của hệ thống.

### 5.2. Smoke test và end-to-end test

Chạy smoke test trước để xác nhận các luồng cơ bản. Sau đó chạy integration/E2E test cho các hành vi có side effect.

| Luồng | Kiểm tra | Kết quả cần lưu |
|---|---|---|
| Login | Xác thực và tạo session/token | Status, claims hoặc trạng thái session kỳ vọng |
| Database | Đọc/ghi một bản ghi test | Dữ liệu và transaction result |
| HTTP client | Gọi dependency test | Status, body, timeout behavior |
| Message | Publish và consume một message | Ack, retry và dữ liệu cuối |
| File | Đọc/ghi file UTF-8 | Nội dung và byte format kỳ vọng |
| Scheduler | Chạy job test | Job status và side effect |
| Shutdown | Gửi tín hiệu dừng | Tài nguyên được đóng và process thoát |

Không chạy test tạo giao dịch thật hoặc gửi thông báo ra ngoài nếu môi trường chưa được cô lập.

### 5.3. So sánh kết quả với baseline

Không chỉ đánh dấu “pass”. So sánh:

- Log mới có warning/exception khác không?
- Output và side effect có giống kỳ vọng không?
- Thời gian startup có thay đổi đáng kể không?
- Throughput và latency có nằm trong SLO không?
- Heap, GC, CPU và RSS có thay đổi bất thường không?
- Có lỗi chỉ xuất hiện sau một khoảng chạy dài không?

Một lần smoke test thành công là bước đầu, không thay thế regression, soak và load test.

## 6. Phân loại lỗi xuất hiện trên Java 17

Khi chạy thử, hãy ghi lại lỗi nguyên bản, stack trace, bước tái hiện và điều kiện môi trường trước khi thay code.

### 6.1. UnsupportedClassVersionError

Lỗi này thường cho biết JVM đang chạy không hỗ trợ class file version của một class được nạp. Khi mục tiêu là Java 17, cần kiểm tra:

- Artifact hoặc dependency có class file mới hơn version 61 hay không.
- Có nhầm JDK runtime trong `PATH` hay container không.
- Một dependency có multi-release JAR hoặc bytecode được build cho runtime khác không.

Có thể xem version class bằng:

~~~bash
javap -verbose -classpath application.jar com.example.Main
~~~

Với JAR phức tạp, xác định class gây lỗi từ stack trace rồi kiểm tra đúng class file. Đừng vội đổi toàn bộ source target nếu lỗi thực chất đến từ một dependency được đóng gói sai.

### 6.2. NoClassDefFoundError, ClassNotFoundException hoặc NoSuchMethodError

Các lỗi này có thể liên quan tới:

- Dependency bị thiếu hoặc phiên bản không tương thích.
- Hai thư viện kéo các phiên bản khác nhau của cùng API.
- Class chỉ được nạp trong một nhánh code chưa được test.
- Method/class đã thay đổi hoặc không có trong phiên bản dependency runtime.

Kiểm tra dependency tree, nội dung artifact và class loader. Chỉ nâng đúng dependency liên quan sau khi đã xác định nguyên nhân.

### 6.3. InaccessibleObjectException hoặc lỗi module access

Java 17 áp dụng strong encapsulation cho các thành phần nội bộ của JDK theo JEP 403. Framework cũ có thể dùng reflection để truy cập private field hoặc package nội bộ.

Hướng xử lý:

1. Xác định class/package đang bị truy cập.
2. Kiểm tra phiên bản framework/thư viện có bản hỗ trợ Java 17 không.
3. Nâng cấp thư viện hoặc chuyển sang API công khai.
4. Nếu cần `--add-opens` như một cầu nối tạm thời, mở đúng package cho đúng module và ghi lại kế hoạch loại bỏ.

Không thêm một loạt `--add-opens` rộng để che mọi lỗi. Điều đó làm giảm encapsulation và che khuất dependency cần sửa.

### 6.4. JVM không khởi động vì option không còn hợp lệ

Một số cờ JVM cũ đã bị deprecated hoặc removed. Ví dụ, CMS collector đã bị loại bỏ trước Java 17; cờ `-XX:+UseConcMarkSweepGC` không phải cấu hình hợp lệ cho Java 17.

Khi gặp lỗi option:

- Lưu nguyên thông báo JVM.
- Xác định cờ thuộc GC, memory, logging, module hay diagnostic.
- Tra tài liệu Java 17 để tìm trạng thái hiện tại.
- Bỏ cờ không còn hỗ trợ hoặc thay bằng cấu hình hiện hành có cùng mục tiêu.
- Chỉ thay một nhóm option tại một thời điểm và ghi lại tác động.

Không sao chép một bộ JVM flags từ blog cũ mà không xác minh với đúng JDK.

### 6.5. Lỗi JNI/native library

Ứng dụng có thể khởi động Java nhưng lỗi khi nạp thư viện native do:

- Kiến trúc CPU không khớp.
- Native binary không tương thích hệ điều hành hoặc ABI.
- Thư viện native phụ thuộc runtime khác.
- Phiên bản JNI/JNA hoặc wrapper không hỗ trợ môi trường mới.

Kiểm tra kiến trúc, thư viện được nạp và phiên bản hỗ trợ Java 17. Nếu cần cập nhật native dependency, thực hiện như một thay đổi riêng để có thể kiểm chứng.

## 7. Kiểm kê API nội bộ và API deprecated

Sau khi artifact đã chạy được, kiểm tra source và dependency để tìm rủi ro còn tiềm ẩn.

### 7.1. Tìm JDK internals bằng jdeps

Chạy trên JAR:

~~~bash
jdeps --jdk-internals --recursive application.jar
~~~

`jdeps` có thể phát hiện nhiều tham chiếu tĩnh tới API nội bộ của JDK và đưa ra gợi ý thay thế nếu có. Kết quả giúp xác định class hoặc dependency cần xử lý.

Giới hạn: phân tích tĩnh không bảo đảm phát hiện mọi tên class được tạo động, reflection theo chuỗi, code được sinh lúc runtime hoặc plugin chỉ nạp trong một cấu hình hiếm.

### 7.2. Tìm API deprecated bằng jdeprscan

~~~bash
jdeprscan --release 17 application.jar
~~~

Deprecated API và internal API là hai nhóm khác nhau. Một API công khai có thể deprecated; một API nội bộ có thể chưa deprecated nhưng vẫn không được cam kết hỗ trợ. Dùng cả hai công cụ khi cần bức tranh rộng hơn.

### 7.3. Kiểm tra dependency bên thứ ba

Đối với từng thư viện:

- Xác nhận phiên bản hỗ trợ Java 17 theo tài liệu của nhà cung cấp.
- Kiểm tra framework/plugin/agent có phụ thuộc JDK internals không.
- Kiểm tra native component và annotation processor.
- Kiểm tra thư viện chỉ được nạp trong test, startup hoặc production path.
- Xác định phiên bản tối thiểu và các dependency bắc cầu.

Không nhất thiết phải nâng tất cả thư viện lên phiên bản mới nhất. Chọn phiên bản tương thích, được hỗ trợ và đã được kiểm thử với ứng dụng.

## 8. Sau runtime test mới nâng build tool và compiler

Khi artifact hiện tại đã có kết quả runtime trên Java 17, chuyển sang build pipeline.

### 8.1. Xác nhận build tool chạy được trên JDK 17

Kiểm tra phiên bản Maven/Gradle và plugin. Build tool có thể chạy trên JDK 17 nhưng plugin cũ lại dùng API nội bộ hoặc chưa hỗ trợ runtime đó.

Ghi lại:

- Phiên bản build tool.
- Phiên bản compiler plugin/toolchain.
- Annotation processor.
- Test runner và code coverage agent.
- Plugin đóng gói, shading, bytecode enhancement và instrumentation.

Nếu build thất bại trước khi biên dịch source, phân biệt lỗi của build tool/plugin với lỗi source code. Đừng sửa source để chữa một plugin không chạy được trên JDK 17.

### 8.2. Dùng toolchain rõ ràng

Với Gradle, Java toolchain có thể xác định JDK dùng để compile/test mà không phụ thuộc JDK mặc định của máy:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Với Maven, cấu hình compiler plugin theo phiên bản được dự án hỗ trợ và đặt release:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Các đoạn trên minh họa cách khai báo; cú pháp đầy đủ và phiên bản plugin cần được kiểm tra theo build tool của dự án.

### 8.3. Vì sao ưu tiên --release?

`--release 17` giới hạn API Java SE mà source có thể tham chiếu theo release 17 và tạo class file tương ứng. Chỉ đặt `-source 17` và `-target 17` không tự bảo đảm compiler chỉ dùng API Java 17; nếu build bằng JDK mới hơn, source có thể vô tình gọi API mới hơn target.

Nếu ứng dụng chỉ cần chạy trên Java 17, `--release 17` thường là cách rõ ràng cho compiler. Nếu phải hỗ trợ thêm runtime cũ hơn, chọn release thấp nhất được yêu cầu và kiểm thử trên từng runtime mục tiêu.

## 9. Nâng dependency và framework theo từng nhóm

Sau khi build tool đã ổn định, mới xử lý thư viện.

### 9.1. Không nâng tất cả dependency cùng lúc

Chia theo nhóm có quan hệ:

1. Framework nền tảng và dependency cốt lõi.
2. Logging và monitoring.
3. Persistence/ORM/database driver.
4. HTTP client/server và serialization.
5. Security/authentication.
6. Test framework, mock library và agent.
7. Plugin hoặc native integration.

Thứ tự thực tế phụ thuộc dependency graph. Trước khi nâng, kiểm tra release note và yêu cầu phiên bản của framework.

### 9.2. Khóa phiên bản để phép thử có thể lặp lại

Không để version range hoặc dependency động thay đổi giữa hai lần chạy. Lưu dependency lockfile hoặc dependency tree theo cơ chế của build tool.

Nếu cần nâng nhiều thư viện do một framework mới yêu cầu, coi đó là một nhóm thay đổi có quan hệ và ghi rõ lý do. Sau đó chạy test trước khi tiếp tục nhóm khác.

### 9.3. Chú ý agent và instrumentation

APM agent, profiler, coverage agent, mocking framework và bytecode enhancer có thể can thiệp class loading hoặc instrumentation. Chúng thường bị bỏ sót nếu chỉ kiểm tra dependency runtime.

Chạy test với cùng agent/cấu hình dự kiến triển khai. Nếu nghi ngờ agent gây lỗi, chạy một lần có kiểm soát không có agent để cô lập nguyên nhân, sau đó xác minh phiên bản agent hỗ trợ JDK 17.

## 10. Thay đổi source code sau khi runtime ổn định

Không cần viết lại toàn bộ code chỉ vì ứng dụng đã chuyển sang Java 17. Trước hết, xác định thay đổi source nào thực sự cần thiết để tương thích hoặc cải thiện thiết kế.

### 10.1. Sửa dependency vào API nội bộ

Thay API nội bộ bằng API công khai tương ứng, hoặc thay đổi thiết kế nếu không có replacement trực tiếp. Không giữ một dependency không được hỗ trợ chỉ vì nó vẫn chạy trên một bản JDK cụ thể.

### 10.2. Xử lý API deprecated

Đọc Javadoc và release note để hiểu API deprecated có replacement nào. Không phải mọi deprecated API đều bị xóa ngay trong Java 17, nhưng code mới nên tránh tạo thêm dependency vào API đã có cảnh báo loại bỏ.

Dùng `jdeprscan --release 17` để hỗ trợ kiểm kê, sau đó xem xét từng trường hợp trong source.

### 10.3. Chưa cần áp dụng ngay mọi language feature mới

Java 17 có nhiều language/API feature hữu ích, nhưng migration runtime không bắt buộc phải chuyển code sang records, sealed classes, text blocks hoặc pattern matching. Việc áp dụng feature mới nên là thay đổi riêng sau khi runtime và build đã ổn định.

Tách hai mục tiêu:

- **Compatibility:** làm cho ứng dụng hiện tại chạy đúng trên Java 17.
- **Modernization:** cải thiện source code bằng khả năng mới của Java 17.

Khi hai mục tiêu được triển khai riêng, regression dễ truy nguyên hơn.

## 11. Kiểm thử sau mỗi mốc thay đổi

Mỗi mốc nên có một tập kiểm thử cố định:

| Mốc | Thay đổi | Kiểm thử bắt buộc |
|---|---|---|
| A | Chỉ đổi runtime sang JDK 17 | Startup, smoke, E2E quan trọng, logs |
| B | Sửa JVM options tối thiểu | Startup, GC/resource metrics, shutdown |
| C | Nâng build tool/compiler | Clean build, unit test, packaging |
| D | Nâng một nhóm dependency | Unit/integration/E2E liên quan nhóm đó |
| E | Sửa source compatibility | Regression test và test biên |
| F | Tối ưu hiệu năng | Load/soak test so với baseline |

Không chuyển sang mốc tiếp theo khi mốc hiện tại còn lỗi chưa giải thích. Nếu có ngoại lệ được chấp nhận, ghi rõ ảnh hưởng và người chịu trách nhiệm.

### 11.1. Kiểm thử chức năng

So sánh kết quả với baseline:

- Dữ liệu trả về.
- Side effect.
- Exception và error handling.
- Serialization/deserialization nếu có.
- Ngày giờ, timezone, locale và encoding.
- Hành vi bảo mật, TLS và certificate.

### 11.2. Kiểm thử tải

Sau khi chức năng đúng, chạy workload tương đương baseline. So sánh throughput, p95/p99, error rate, CPU, heap, GC và RSS.

Không điều chỉnh heap/GC chỉ vì con số khác baseline một chút. Hãy xác định có vi phạm SLO, vượt ngân sách hoặc có xu hướng bất thường hay không.

### 11.3. Kiểm thử thời gian dài

Soak test giúp phát hiện:

- Heap hoặc RSS tăng dần.
- Thread hoặc connection không được giải phóng.
- Queue tăng liên tục.
- Lỗi chỉ xuất hiện sau nhiều lần reconnect/retry.
- Scheduled task không chạy đúng hoặc chạy trùng.
- Resource leak khi reload/shutdown.

## 12. Lập ma trận thử nghiệm để cô lập nguyên nhân

Một ma trận đơn giản:

| Thử nghiệm | JDK runtime | Artifact/build | Dependency | Mục tiêu |
|---|---|---|---|---|
| Baseline | JDK hiện tại | Artifact hiện tại | Hiện tại | Ghi hành vi chuẩn |
| Runtime-only | JDK 17 | Cùng artifact | Cùng dependency | Tìm lỗi runtime compatibility |
| Build-only | JDK 17 | Build tool/compiler đã cập nhật | Dependency giữ nguyên | Kiểm tra build pipeline |
| Dependency group 1 | JDK 17 | Build ổn định | Chỉ nâng nhóm 1 | Cô lập framework/dependency |
| Dependency group 2 | JDK 17 | Build ổn định | Chỉ nâng nhóm 2 | Cô lập nhóm kế tiếp |
| Source migration | JDK 17 | Release 17 | Dependency đã chọn | Kiểm tra source/API target |
| Final candidate | JDK 17 | Cấu hình đích | Tập dependency đích | Regression, load và soak |

Nếu có quá nhiều thành phần phải thay cùng lúc vì phụ thuộc bắt buộc, ghi nhận nhóm thay đổi và kiểm tra từng ranh giới nhỏ nhất có thể. Không nhất thiết mỗi dòng bảng phải là một release riêng; quan trọng là có khả năng quy lỗi.

## 13. Quản lý rollback và triển khai thử

### 13.1. Giữ artifact và cấu hình cũ

Trước khi triển khai:

- Lưu artifact đang chạy.
- Lưu image/container digest.
- Lưu JVM options và biến môi trường.
- Lưu dependency lock/manifest.
- Xác định cách quay về runtime cũ.

Không overwrite artifact cũ trong quá trình thử nghiệm. Giữ bản build có thể tái tạo và biết chính xác commit nào tạo ra nó.

### 13.2. Thử trên staging/canary

Triển khai Java 17 vào môi trường staging hoặc một phần nhỏ traffic theo quy trình của hệ thống. Theo dõi:

- Startup/readiness.
- Error rate.
- Latency.
- CPU/RAM/GC.
- Dependency failures.
- Log và alert.

Canary phải có tiêu chí dừng rõ ràng. Nếu metric vượt ngưỡng, dừng rollout và quay về artifact/runtime đã biết hoạt động.

### 13.3. Rollback phải được kiểm chứng

Rollback không chỉ là đổi image tag. Kiểm tra:

- Database migration có tương thích ngược không?
- Queue/message format có bị thay đổi không?
- Cache key hoặc serialized payload có đổi không?
- Artifact cũ có đọc được dữ liệu được tạo bởi candidate mới không?
- Cấu hình có thể quay lại mà không mất secret hoặc setting không?

Nếu migration dữ liệu không tương thích ngược, phải xử lý thứ tự triển khai và kế hoạch khôi phục trước khi rollout.

## 14. Ví dụ quy trình nâng cấp một ứng dụng

Giả sử một service đang chạy bằng Java 11, build artifact `orders-service.jar` và có database, HTTP client cùng message broker.

### Giai đoạn 1: Baseline trên Java 11

~~~bash
java -version
java -jar orders-service.jar
~~~

Chạy smoke/E2E test, lưu startup time, request latency, error rate, heap/GC và log.

### Giai đoạn 2: Chạy đúng artifact trên Java 17

~~~bash
/opt/jdk-17/bin/java -version
/opt/jdk-17/bin/java -jar orders-service.jar
~~~

Giữ nguyên artifact, config, dataset và dependency. Chạy lại đúng tập test. Nếu JVM không khởi động do option cũ, chỉ loại bỏ/thay option gây lỗi và ghi lại.

### Giai đoạn 3: Kiểm kê dependency

~~~bash
jdeps --jdk-internals --recursive orders-service.jar
jdeprscan --release 17 orders-service.jar
~~~

Đọc kết quả, kiểm tra framework, agent, database driver và native dependency. Tạo danh sách công việc có owner và test tương ứng.

### Giai đoạn 4: Cập nhật build pipeline

Cập nhật build tool/plugin cần thiết để chạy trên JDK 17. Cấu hình compiler release theo mục tiêu. Chạy clean build và unit test mà chưa thay toàn bộ dependency.

### Giai đoạn 5: Nâng dependency theo nhóm

Nâng framework/dependency theo thứ tự dependency graph yêu cầu. Sau mỗi nhóm, chạy integration/E2E test liên quan và ghi lại khác biệt.

### Giai đoạn 6: Hoàn thiện source và cấu hình

Thay API nội bộ, sửa reflection access, cập nhật JVM options hiện hành và chỉ áp dụng Java 17 language/API feature khi có nhu cầu.

### Giai đoạn 7: Kiểm thử final candidate

Chạy regression, load, soak và shutdown test trên môi trường gần production. So sánh với baseline và triển khai canary theo tiêu chí đã định.

## 15. Những lỗi thường gặp

### 15.1. Đổi JDK, framework và dependency cùng một lần

Khi app lỗi, không biết lỗi do runtime hay thay đổi thư viện.

**Cách xử lý:** chạy nguyên artifact trên JDK 17 trước, sau đó thay đổi theo nhóm.

### 15.2. Chỉ kiểm tra compile thành công

Compile không chạy hết code path, không xác nhận plugin runtime, reflection, native library hoặc dependency được nạp muộn.

**Cách xử lý:** chạy startup, smoke, integration, E2E và các luồng vận hành quan trọng.

### 15.3. Dùng `--release 17` như một cách chọn runtime

`--release` là tùy chọn compiler, không chọn JVM khi chạy.

**Cách xử lý:** xác nhận riêng `java -version` và compiler release.

### 15.4. Thêm nhiều --add-opens để bỏ qua lỗi

Việc này có thể làm ứng dụng chạy tạm nhưng che giấu dependency vào private JDK internals.

**Cách xử lý:** nâng framework hoặc thay API nội bộ; nếu cần cờ tạm thời, thu hẹp package/module và đặt kế hoạch bỏ.

### 15.5. Nâng mọi thư viện lên latest

Latest không đồng nghĩa tương thích nhất với ứng dụng hiện tại. Thay đổi lớn có thể kéo theo breaking changes và làm khó truy nguyên.

**Cách xử lý:** chọn phiên bản được hỗ trợ, phù hợp dependency graph và nâng theo nhóm.

### 15.6. Tối ưu GC/heap trước khi có baseline

Thay collector và heap size cùng lúc với runtime migration làm mất khả năng so sánh.

**Cách xử lý:** giữ cấu hình gần baseline trong runtime-only test; tuning sau khi chức năng ổn định và có số liệu.

### 15.7. Chỉ chạy smoke test một lần

Một lần khởi động thành công không chứng minh job nền, reconnect, shutdown hoặc tải cao hoạt động đúng.

**Cách xử lý:** kiểm thử theo ma trận luồng nghiệp vụ và workload, gồm soak test khi phù hợp.

### 15.8. Không lưu artifact/cấu hình cũ

Không có bản cũ đã biết hoạt động thì rollback trở nên khó đoán.

**Cách xử lý:** giữ artifact, image digest, config và dependency lock của baseline.

## 16. Checklist cho một lần chạy thử Java 17

**Trước khi chạy:**

- [ ] Ghi phiên bản JDK, build ID và cấu hình hiện tại.
- [ ] Lưu artifact nguyên trạng và xác nhận hash/build identity.
- [ ] Chuẩn bị môi trường thử nghiệm có dependency tương đương.
- [ ] Chọn smoke/E2E test và workload đại diện.
- [ ] Xác định metric và tiêu chí pass/fail.
- [ ] Chuẩn bị cách quay lại artifact/runtime cũ.

**Trong khi chạy:**

- [ ] Xác nhận đúng JDK 17 đang chạy process.
- [ ] Ghi lại mọi JVM option phải thay để khởi động.
- [ ] Kiểm tra startup và readiness.
- [ ] Chạy các luồng nghiệp vụ đại diện.
- [ ] Thu log, error, latency, throughput và resource metrics.
- [ ] Ghi nhận lỗi cùng stack trace và bước tái hiện.

**Sau khi chạy:**

- [ ] So sánh với baseline.
- [ ] Phân loại lỗi runtime, dependency, build, source hoặc deployment.
- [ ] Chạy jdeps/jdeprscan để kiểm kê dependency.
- [ ] Chỉ chuyển sang nhóm thay đổi tiếp theo khi kết quả đã được giải thích.
- [ ] Lưu artifact, config, kết quả và quyết định tiếp tục/rollback.

## 17. Bài tập thực hành

### Bài 1 — Tạo baseline

Chọn một ứng dụng đang chạy trên JDK thấp hơn 17. Ghi phiên bản runtime, artifact, JVM flags, dependency, startup time, health check, một số luồng nghiệp vụ và metric hiệu năng.

### Bài 2 — Runtime-only test

Chạy nguyên artifact trên JDK 17 trong môi trường thử nghiệm. Không thay source hoặc dependency. Ghi kết quả startup, smoke test và log. Nếu cần thay một JVM option để chạy, giải thích vì sao và ghi lại option cũ/mới.

### Bài 3 — Phân loại lỗi

Với mỗi lỗi sau, xác định nhóm điều tra đầu tiên: `UnsupportedClassVersionError`, `NoSuchMethodError`, `InaccessibleObjectException`, lỗi nạp native library và JVM option không hợp lệ. Nêu dữ liệu cần thu trước khi sửa.

### Bài 4 — Kiểm kê dependency

Chạy `jdeps --jdk-internals` và `jdeprscan --release 17` trên artifact. Phân biệt kết quả internal API và deprecated API. Nêu giới hạn khi dependency dùng reflection động.

### Bài 5 — Tách build migration

Sau runtime-only test, cập nhật build tool/compiler để dùng JDK 17 và `--release 17`. Chạy clean build/unit test mà chưa nâng dependency. Ghi lỗi thuộc build tool/plugin hay source.

### Bài 6 — Nâng một nhóm dependency

Chọn một nhóm, ví dụ database driver hoặc HTTP client. Nâng phiên bản được hỗ trợ, chạy test liên quan và so sánh với baseline. Không thay các nhóm khác trong cùng phép thử.

### Bài 7 — Thiết kế rollback

Viết quy trình quay về artifact/runtime cũ. Xác định database, queue, cache và serialized data có tương thích ngược không. Nêu điều kiện dừng rollout.

## 18. Tiêu chí hoàn thành

Người học nắm vững bài khi có thể:

1. Giải thích vì sao phải chạy thử artifact hiện tại trên JDK 17 trước khi thay nhiều thành phần.
2. Phân biệt runtime migration, build migration và source modernization.
3. Lập baseline gồm môi trường, workload, chức năng và metric.
4. Chạy đúng artifact bằng executable JDK 17 và xác nhận runtime thực tế.
5. Thực hiện startup, readiness, smoke, E2E, load và soak test phù hợp.
6. Phân loại lỗi class version, dependency, module access, JVM option và native library.
7. Dùng jdeps/jdeprscan đúng mục đích và hiểu giới hạn phân tích tĩnh.
8. Cập nhật build tool, compiler và dependency theo các mốc có thể kiểm chứng.
9. Dùng `--release 17` đúng vai trò và không nhầm với chọn runtime.
10. So sánh kết quả với baseline và giữ phương án rollback có thể thực hiện.

## 19. Tài liệu chính thức

- [Java SE 17 Migration Guide](https://docs.oracle.com/en/java/javase/17/migrate/): các thay đổi cần lưu ý khi chuyển ứng dụng lên JDK 17.
- [Java SE 17 Release Notes](https://www.oracle.com/java/technologies/javase/17-relnote-issues.html): thay đổi, loại bỏ và vấn đề tương thích trong Java 17.
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): tác động của strong encapsulation.
- [Java SE 17 man page — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, compiler options và cách biên dịch.
- [Java SE 17 man page — jdeps](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): phân tích dependency và JDK internals.
- [Java SE 17 man page — jdeprscan](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeprscan.html): phát hiện API deprecated.
- [Java SE 17 man page — java](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): khởi chạy ứng dụng và JVM options.

**Ghi nhớ:** Trước khi đổi framework, dependency, compiler và JVM flags cùng lúc, hãy chạy artifact hiện tại trên JDK 17 để có một mốc runtime compatibility. Ghi baseline, kiểm tra các luồng thật, phân loại lỗi rồi nâng từng nhóm thành phần. Chỉ kết luận migration ổn định khi build, chức năng, vận hành và hiệu năng đều đã được kiểm chứng trên môi trường mục tiêu.
