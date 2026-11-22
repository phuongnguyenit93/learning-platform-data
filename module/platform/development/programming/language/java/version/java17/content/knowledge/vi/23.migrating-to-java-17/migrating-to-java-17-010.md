# Kế hoạch triển khai từng bước, quan sát và quay lui khi nâng cấp lên Java 17

Nâng cấp ứng dụng lên Java 17 là một thay đổi ở cả build, runtime, dependency và vận hành. Một lần build thành công chưa chứng minh hệ thống sẵn sàng phát hành: thư viện có thể chưa hỗ trợ JDK 17, JVM flags cũ có thể không còn phù hợp, hành vi TLS hoặc module access có thể thay đổi, và tải thực tế có thể làm lộ vấn đề về latency, memory hoặc GC.

Một đợt nâng cấp an toàn cần có ba khả năng:

1. **Triển khai có kiểm soát:** thay đổi theo từng môi trường hoặc từng phần lưu lượng, có điểm dừng để đánh giá.
2. **Quan sát đủ sâu:** so sánh lỗi, latency, throughput, tài nguyên JVM và các chỉ số nghiệp vụ với baseline.
3. **Quay lui được:** giữ artifact và cấu hình phiên bản cũ, đồng thời bảo đảm schema, message, cache và dữ liệu vẫn tương thích khi hai phiên bản cùng tồn tại.

Kế hoạch dưới đây áp dụng cho ứng dụng Java chạy trên JVM, từ service đơn lẻ đến hệ thống nhiều service. Có thể điều chỉnh cách rollout theo nền tảng triển khai, nhưng các nguyên tắc về tương thích, quan sát và rollback vẫn cần được giữ.

## 1. Xác định phạm vi và mục tiêu nâng cấp

Trước khi sửa build, ghi rõ điều gì đang được nâng cấp và điều gì được kỳ vọng sau thay đổi.

Các câu hỏi cần trả lời:

- Ứng dụng đang chạy Java phiên bản nào và sẽ chuyển sang Java 17 ở môi trường nào?
- Dùng JDK/JVM của nhà cung cấp nào? Phiên bản cập nhật cụ thể nào được phê duyệt?
- Build tool, plugin, test runner và annotation processor hiện tại là gì?
- Ứng dụng có JNI, JNA, agent, profiler, native executable hoặc thư viện phụ thuộc nền tảng không?
- Có service, batch job, worker, scheduled task hoặc CLI nào dùng chung thư viện?
- Mục tiêu chính là hỗ trợ Java 17, tận dụng tính năng Java 17, cải thiện vận hành hay chuẩn hóa nền tảng?
- Những SLO/SLA nào phải giữ nguyên trong đợt chuyển đổi?

Phạm vi cần bao gồm toàn bộ thành phần thực sự chạy trên JVM: API server, worker, migration job, công cụ quản trị, test harness và tác vụ nền. Nếu chỉ nâng service chính nhưng quên một batch job chạy theo lịch, lỗi có thể xuất hiện muộn sau khi phát hành.

### Xác định phiên bản nguồn và đích

Ghi lại tối thiểu:

| Thông tin | Giá trị cần ghi |
| --- | --- |
| Runtime hiện tại | Vendor, phiên bản Java, bản cập nhật và JVM |
| Runtime đích | JDK 17 vendor/build và bản cập nhật được phê duyệt |
| Build runtime | JDK chạy Maven/Gradle và compiler thực tế |
| Bytecode target | Phiên bản class file dự kiến, Java 17 là major version 61 |
| Deployment | OS, container/base image, CPU architecture, memory/CPU limit |
| Dependencies | Phiên bản thư viện, framework, agent và native library |
| Rollback target | Artifact, cấu hình và runtime cũ có thể khôi phục |

Java 17 là một release LTS, nhưng bản cập nhật JDK 17 vẫn tiếp tục được phát hành. Nên chọn bản cập nhật bảo mật còn được nhà cung cấp hỗ trợ và pin rõ phiên bản trong CI/production. Không cố định sản phẩm ở một bản cập nhật cũ chỉ vì lần nâng cấp đầu tiên đã thành công.

## 2. Lập inventory trước khi thay đổi

Tạo danh sách tất cả thứ có thể bị ảnh hưởng bởi runtime mới. Dữ liệu inventory sẽ giúp chọn thứ tự xử lý và xác định chủ sở hữu cho từng rủi ro.

### Inventory mã nguồn và build

Ghi nhận:

- Module Maven/Gradle và source set.
- Phiên bản compiler plugin, test plugin, packaging plugin.
- Annotation processor và code generator.
- Các compiler flags và JVM flags.
- Các script shell/PowerShell gọi Java trực tiếp.
- Dockerfile, image base, buildpack và pipeline CI.
- Cấu hình IDE nếu có ảnh hưởng tới build dùng chung.
- Các file cấu hình chứa đường dẫn JAVA_HOME hoặc đường dẫn JDK cố định.

Tìm các điểm gọi runtime trực tiếp như script khởi chạy, systemd unit, launch configuration, Kubernetes command/args, cron job, service wrapper và cấu hình application server.

### Inventory dependency

Phân nhóm dependency:

| Nhóm | Ví dụ | Việc cần xác minh |
| --- | --- | --- |
| Framework | Spring, Jakarta/Java EE integration, application framework | Phiên bản có hỗ trợ Java 17 và cách cấu hình tương thích |
| Runtime library | Logging, JSON, HTTP, database driver | API, bytecode và hành vi runtime |
| Bytecode tool | ASM, Byte Buddy, Javassist, instrumentation library | Có hiểu class file version 61 và JDK 17 internals cần thiết không |
| Test | JUnit, Mockito, test engine, coverage | Test runner, mocking và coverage agent hỗ trợ JDK 17 |
| Build | Maven/Gradle plugin, compiler, packaging | Chạy được với JDK/toolchain đã chọn |
| Observability | APM agent, tracing, metrics, profiler | Agent hỗ trợ JDK 17 và không dựa vào internal access đã bị đóng |
| Native | JNI, JNA, database client native, compression | Có binary đúng OS/architecture và dependency graph |
| Security | TLS provider, crypto provider, certificate library | Thuật toán, protocol, provider và trust configuration |

Không chỉ đọc dependency trực tiếp. Cần kiểm tra dependency bắc cầu và phiên bản được resolve thực tế. Một framework có thể tương thích Java 17 nhưng một plugin cũ hoặc một agent được nạp lúc startup lại không tương thích.

### Inventory JVM flags và startup options

Thu thập toàn bộ JVM arguments đang dùng:

- Heap sizing và metaspace.
- GC selection và GC logging.
- JIT/compiler options.
- Module access options như add-exports/add-opens.
- System properties.
- TLS/security properties.
- Agent options.
- Native library paths.
- JFR hoặc diagnostic options.

Phân loại từng flag thành: còn cần, có thể bỏ, cần kiểm chứng hoặc không còn được hỗ trợ. Không sao chép nguyên bộ flags từ runtime cũ sang Java 17 mà không xác minh. Đặc biệt, không dựa vào tùy chọn illegal-access để mở lại JDK internals trên Java 17; hướng xử lý nên là nâng thư viện và loại bỏ truy cập nội bộ.

## 3. Đánh giá thay đổi giữa phiên bản nguồn và Java 17

Nếu nâng qua nhiều release, đọc migration guide và release notes của các phiên bản đã bỏ qua. Không cần triển khai từng release trung gian chỉ để có thể nâng lên 17, nhưng cần xem các thay đổi tích lũy vì chúng có thể ảnh hưởng source, dependency và runtime.

Những vùng cần kiểm tra:

### Module system và strong encapsulation

Java 17 áp dụng strong encapsulation cho JDK internals theo JEP 403. Framework cũ có thể dùng reflection để đọc private field hoặc gọi method nội bộ của JDK và gặp InaccessibleObjectException.

Việc cần làm:

- Tìm setAccessible, trySetAccessible, privateLookupIn và reflection theo tên class/field.
- Chạy test với Java 17 để xác định lỗi thực tế.
- Nâng framework/agent lên phiên bản hỗ trợ Java 17.
- Chỉ mở package của ứng dụng do mình sở hữu khi framework thật sự cần deep reflection.
- Ghi lại mọi add-opens còn tồn tại, chủ sở hữu và lý do.

Không mở rộng hàng loạt package của java.base như một giải pháp mặc định. Mở package JDK tạo thêm phụ thuộc vào implementation và không biến internal API thành hợp đồng ổn định.

### API từng đi kèm JDK nhưng đã được tách ra

Nếu ứng dụng nâng từ Java 8 hoặc một runtime cũ, kiểm tra code và dependency từng dựa vào module không còn được đóng gói sẵn trong JDK hiện đại. Một số Java EE/CORBA modules đã bị tách khỏi JDK từ các release trước Java 17.

Nếu ứng dụng cần XML binding, web services hoặc API tương tự, xác định implementation/dependency cần thiết và quản lý chúng như dependency riêng. Không giả định đổi JDK sẽ tự cung cấp các module đó. Cũng không tự động đổi namespace javax thành jakarta: việc chuyển namespace phụ thuộc phiên bản specification và framework, không phải một bước cơ học của nâng JDK.

### Security và TLS

Kiểm tra kết nối outbound/inbound tới database, message broker, LDAP, API ngoài và dịch vụ nội bộ. Chú ý:

- TLS protocol và cipher suite được hai đầu hỗ trợ.
- Certificate chain, truststore và hostname verification.
- Provider mật mã và thuật toán bị giới hạn theo security policy.
- Certificate hết hạn hoặc CA nội bộ không được tin cậy.
- Client library cũ có giả định về TLS hoặc provider.

Không hạ TLS hoặc tắt certificate validation để làm cho kết nối cũ chạy lại. Xác định chính xác khác biệt về certificate, protocol, cipher hoặc provider rồi cập nhật cấu hình/đầu cuối phù hợp.

### Locale, timezone và dữ liệu

JDK update có thể mang theo thay đổi dữ liệu timezone, locale hoặc Unicode. Nếu ứng dụng xử lý lịch, hóa đơn, báo cáo, sorting hoặc format số/ngày, hãy kiểm tra:

- Timestamp lưu và hiển thị.
- Chuyển đổi timezone và daylight saving time.
- Locale mặc định của container.
- Format tiền tệ, số thập phân và ngày.
- Quy tắc collation/sorting nếu phụ thuộc locale.

Nên lưu thời điểm nghiệp vụ theo Instant/UTC khi phù hợp và chỉ chuyển sang timezone hiển thị ở biên hệ thống. Kiểm tra các trường hợp có quy tắc timezone thay đổi theo dữ liệu mới.

### GC, JIT và container

Java 17 có thể khác runtime cũ về JIT, GC, ergonomics và khả năng nhận diện giới hạn container. Đừng mặc định heap, CPU hoặc GC sẽ giữ nguyên hiệu năng sau khi đổi JDK.

Kiểm tra:

- Heap max thực tế so với container memory limit.
- GC algorithm và pause distribution.
- Allocation rate, live set và metaspace.
- CPU quota, throttling và số processor JVM nhận diện.
- Startup time và JIT warmup.
- Thread count, pool sizing và virtual/native resource usage.

Nếu đang dùng G1 mặc định của HotSpot server, trước tiên giữ cấu hình gần mặc định và đo baseline. Chỉ thay GC hoặc compiler flags khi profile cho thấy có vấn đề cụ thể; thay nhiều biến cùng lúc sẽ làm khó xác định nguyên nhân.

## 4. Chốt chiến lược build và target Java 17

Build phải diễn đạt rõ phiên bản tối thiểu mà sản phẩm hỗ trợ. Khi compiler chạy trên JDK mới hơn, dùng release target để tránh vô tình gọi API chỉ có ở JDK mới.

Với javac:

~~~bash
javac --release 17 -encoding UTF-8 -d out @sources.txt
~~~

Với Maven, cấu hình maven.compiler.release bằng 17 và dùng maven-compiler-plugin có hỗ trợ thuộc tính này:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Với Gradle, cấu hình Java toolchain và release target:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
~~~

Toolchain xác định JDK/compiler dùng cho task; release xác định ngôn ngữ, bytecode và API nền tảng đích. Nếu build trên JDK mới hơn nhưng phát hành cho Java 17, có thể dùng compiler mới hỗ trợ release 17, nhưng vẫn cần chạy test bằng runtime Java 17.

Class file Java 17 có major version 61. Có thể kiểm tra bằng:

~~~bash
javap -verbose -classpath build/classes/java/main com.example.Main
~~~

Không chỉnh header class file để hạ major version. Việc đổi con số không backport bytecode hoặc API mới.

### Pin build environment

Build nên tái lập được:

- Pin JDK vendor và bản cập nhật.
- Pin Maven/Gradle wrapper và plugin.
- Pin dependency qua lockfile hoặc dependency management phù hợp.
- Cố định encoding.
- Ghi lại JVM args của test/build.
- Dùng container image có version hoặc digest được quản lý.

Không dùng một JDK ngẫu nhiên trên máy developer làm nguồn duy nhất cho artifact production.

## 5. Tạo baseline trước khi nâng runtime

Baseline là dữ liệu của phiên bản đang chạy trước khi thay đổi. Không có baseline, sau triển khai khó biết lỗi hoặc biến động tài nguyên là mới hay đã tồn tại.

Thu thập baseline trong điều kiện tải đại diện, tốt nhất bao gồm giờ cao điểm và các luồng nghiệp vụ quan trọng.

### Chỉ số dịch vụ

Theo dõi:

- Request rate hoặc job throughput.
- Error rate theo loại lỗi và endpoint.
- Latency p50, p95, p99.
- Timeout và retry.
- Queue depth, consumer lag và thời gian xử lý message.
- Tỷ lệ request thành công theo luồng nghiệp vụ.
- Database connection pool, query latency và lỗi kết nối.
- Tỷ lệ phụ thuộc ngoài bị lỗi.

### Chỉ số JVM và host

Theo dõi:

- Process CPU và container CPU throttling.
- Heap used, committed, max và live set sau GC.
- Allocation rate.
- GC count, pause time và pause distribution.
- Metaspace và direct/native memory nếu có.
- Thread count, blocked threads và deadlock.
- Class loading/unloading.
- File descriptor, socket và connection count.
- Process restart, OOM kill và exit code.

### Chỉ số nghiệp vụ

Một API có thể giữ latency ổn định nhưng tạo ra kết quả nghiệp vụ sai. Theo dõi các chỉ số phù hợp:

- Số đơn hàng/transaction hoàn tất.
- Tỷ lệ thanh toán thành công.
- Số message được xử lý và số message lỗi.
- Số job hoàn tất đúng hạn.
- Tỷ lệ bản ghi bị từ chối hoặc retry.
- Số lần xử lý trùng, mất hoặc sai trạng thái.

Đối chiếu cả số lượng và chất lượng kết quả. Chỉ nhìn CPU hoặc HTTP status không đủ để xác nhận nâng cấp an toàn.

### Ghi nhận baseline theo phiên bản

Mỗi biểu đồ và log nên có nhãn:

- Service và environment.
- Application version/commit.
- JDK vendor/version.
- Container image hoặc host group.
- Region/zone.
- Deployment revision.

Nhờ vậy có thể so sánh nhóm chạy Java cũ với nhóm Java 17 trên cùng khoảng thời gian và tải tương đương.

## 6. Chuẩn bị test trước khi rollout

Không bắt đầu canary nếu chỉ có unit test. Cần xác minh những đường tích hợp có nguy cơ bị ảnh hưởng bởi runtime.

### Unit và component test

Chạy toàn bộ test bằng JDK 17. Chú ý:

- Test reflection và serialization.
- Test annotation processor và generated code.
- Test date/time, locale và timezone.
- Test TLS/certificate.
- Test thread, executor và concurrency.
- Test exception handling và resource cleanup.

### Integration và contract test

Kiểm tra các kết nối thực tế hoặc môi trường test tương đương:

- Database driver, ORM và transaction.
- Message broker, consumer/producer và schema registry.
- HTTP client/server, proxy và TLS.
- File storage, object storage và filesystem.
- Authentication, authorization và crypto provider.
- Native library/JNI/JNA nếu có.

Contract test đặc biệt quan trọng khi các service có thể chạy nhiều phiên bản cùng lúc. Java 17 rollout không nên làm thay đổi wire protocol hoặc message schema ngoài kế hoạch.

### Performance và capacity test

So sánh runtime cũ và Java 17 trên cùng loại workload:

- Throughput ở tải thông thường và tải đỉnh.
- Latency p50/p95/p99.
- CPU trên mỗi request/job.
- Allocation rate và GC pause.
- Startup time và thời gian warmup.
- Memory footprint dưới tải ổn định.
- Hành vi khi downstream chậm hoặc mất kết nối.

Dùng cùng dữ liệu, cấu hình tài nguyên và môi trường càng giống nhau càng tốt. Nếu đổi cả JDK, heap, GC, framework và instance size trong cùng một đợt, sẽ khó xác định biến nào gây thay đổi.

### Soak và failure test

Chạy đủ lâu để quan sát:

- Memory leak hoặc tăng dần live set.
- Thread/connection không được giải phóng.
- Queue tích lũy.
- GC behavior sau nhiều chu kỳ.
- Token/certificate refresh.
- Scheduled job và batch chạy theo lịch.
- Khả năng phục hồi sau database/broker/network interruption.

Một smoke test vài phút không thay thế soak test cho service chạy nhiều ngày.

## 7. Chuẩn bị rollback trước khi deploy

Rollback phải là một thao tác đã được diễn tập và có chủ sở hữu, không phải quyết định ứng biến khi production gặp sự cố.

Tạo rollback package gồm:

- Artifact ứng dụng phiên bản trước.
- Runtime image/JDK trước.
- Cấu hình khởi chạy trước.
- JVM flags trước đã được xác nhận.
- Manifest dependency và image digest.
- Script hoặc quy trình khôi phục deployment.
- Kế hoạch khôi phục feature flags.
- Quy trình xử lý schema/data/message nếu đã có ghi dữ liệu từ phiên bản mới.

Giữ artifact cũ ở registry hoặc kho phát hành với định danh bất biến. Không rebuild lại phiên bản cũ vào thời điểm rollback vì dependency hoặc build environment có thể đã thay đổi.

### Tương thích dữ liệu là điều kiện quan trọng

Rollback binary không tự động rollback dữ liệu đã ghi. Nếu phiên bản mới thay đổi schema hoặc format dữ liệu, phiên bản cũ có thể không đọc được dữ liệu mới.

Dùng chiến lược expand-contract cho thay đổi database:

1. **Expand:** thêm cột/bảng/index hoặc cấu trúc mới theo cách phiên bản cũ vẫn hoạt động.
2. **Dual compatibility:** trong giai đoạn chuyển tiếp, code cũ và mới có thể đọc/ghi theo quy tắc tương thích đã định.
3. **Backfill:** chuyển dữ liệu theo batch có kiểm soát, có checkpoint và có thể tiếp tục.
4. **Switch:** chuyển ứng dụng sang đọc/ghi cấu trúc mới khi đã xác minh.
5. **Contract:** chỉ xóa cấu trúc cũ sau khi không còn instance hoặc consumer nào cần nó và cửa sổ rollback đã kết thúc.

Không thực hiện migration phá hủy ngay trước hoặc cùng lúc với lần rollout đầu nếu chưa có đường phục hồi dữ liệu đã thử nghiệm.

### Message và event compatibility

Nếu service dùng queue/event stream:

- Producer mới phải phát message mà consumer cũ có thể xử lý trong thời gian rolling deployment nếu cần rollback.
- Consumer mới nên xử lý message đã được phát bởi producer cũ.
- Thay đổi schema theo quy tắc tương thích của hệ thống.
- Không đổi ý nghĩa field hiện có mà không có versioning.
- Kiểm tra retry, dead-letter queue, ordering và duplicate handling.
- Xác định message nào có thể bị xử lý lại sau rollback.

Nếu ứng dụng serialize object Java trực tiếp vào cache hoặc queue, nâng cấp runtime hoặc class có thể làm lộ vấn đề tương thích serialization. Ưu tiên format có schema/wire contract rõ ràng và kiểm tra dữ liệu giữa hai phiên bản.

### Session, cache và token

Kiểm tra:

- Session được lưu ở memory hay shared store.
- Cache value có phụ thuộc class serialization không.
- Cache key/namespace có cần versioning không.
- Token và cookie có giữ tương thích không.
- Rolling deployment có khiến user bị logout hoặc session không đọc được không.

Nếu cần, tách cache namespace theo version hoặc dùng format trung lập với ngôn ngữ. Tránh xóa cache toàn bộ như một bước mặc định vì có thể tạo tải đột biến lên database/downstream.

## 8. Chọn chiến lược rollout

Chọn cách triển khai phù hợp kiến trúc và khả năng điều khiển traffic.

### Rolling deployment

Thay từng instance theo batch:

~~~text
Version cũ: [old] [old] [old] [old]
Batch 1:    [new] [old] [old] [old]
Batch 2:    [new] [new] [old] [old]
Batch 3:    [new] [new] [new] [old]
Hoàn tất:   [new] [new] [new] [new]
~~~

Ưu điểm là không cần toàn bộ capacity mới cùng lúc. Rủi ro là hai phiên bản cùng phục vụ traffic trong thời gian chuyển đổi; API, database, cache và message cần tương thích chéo.

### Canary deployment

Đưa một phần nhỏ traffic hoặc một nhóm instance sang Java 17 trước:

~~~text
Traffic
  |
  +---- 95% ----> Version cũ
  |
  +----  5% ----> Java 17 canary
~~~

Canary cho phép so sánh nhóm mới với nhóm cũ dưới tải production thực tế. Tỷ lệ 5% chỉ là ví dụ, không phải quy tắc. Chọn tỷ lệ đủ nhỏ để giới hạn tác động nhưng đủ lớn để tạo mẫu traffic đại diện.

Không chỉ định canary theo một tenant hoặc endpoint quá đặc biệt nếu workload của nhóm đó không đại diện. Theo dõi các loại request và tác vụ quan trọng.

### Blue-green deployment

Duy trì hai môi trường:

- Blue tiếp tục phục vụ phiên bản cũ.
- Green được dựng với Java 17 và được kiểm tra trước.
- Chuyển traffic sang green sau khi readiness và smoke test đạt.
- Giữ blue sẵn sàng trong cửa sổ rollback.

Blue-green có thể giảm thời gian chuyển đổi nhưng cần capacity cho hai môi trường và cơ chế chuyển traffic/session phù hợp.

### Chọn phương án

| Điều kiện | Cách rollout phù hợp |
| --- | --- |
| Có nhiều instance và traffic routing theo phần trăm | Canary rồi rolling |
| Có hai môi trường và đủ capacity | Blue-green |
| Service stateless, API tương thích hai phiên bản | Rolling deployment |
| Batch job không có traffic routing | Chạy shadow/parallel có kiểm soát hoặc chuyển lịch theo nhóm |
| Worker tiêu thụ queue | Nâng consumer theo batch, quan sát lag và message errors |
| Native dependency theo architecture | Tách artifact/deployment target theo architecture trước rollout |

Với database migration hoặc thay đổi message format, rollout application phải tuân theo thứ tự tương thích dữ liệu, không chỉ theo khả năng thay binary.

## 9. Triển khai theo từng môi trường

Một thứ tự triển khai điển hình:

1. Local developer environment.
2. CI build/test.
3. Integration environment.
4. Staging/pre-production.
5. Production canary.
6. Production rollout theo batch.
7. Theo dõi sau triển khai và đóng cửa sổ rollback.

### Local và CI

Mỗi developer có thể dùng nhiều JDK, nhưng build chính thức phải dùng toolchain đã thống nhất. CI nên:

- Build với release 17.
- Chạy test bằng Java 17.
- Kiểm tra dependency và class file version.
- Tạo artifact bất biến.
- Gắn commit, JDK vendor/version và build metadata.
- Lưu test report, dependency manifest và image digest.

### Integration

Chạy các kết nối thực tế và contract test. Không chỉ mock tất cả dependency, vì lỗi TLS, driver, module access, serialization hoặc native loading thường chỉ xuất hiện khi tích hợp thật.

### Staging

Dùng cấu hình gần production:

- Cùng loại JDK distribution và container image.
- Cùng giới hạn CPU/memory.
- Cùng JVM flags.
- Cùng agent/metrics/tracing.
- Dữ liệu được ẩn danh hoặc tạo theo phân phối tương đương.
- Traffic replay hoặc load test đại diện.

Staging không nhất thiết có quy mô production, nhưng phải giữ các yếu tố runtime quan trọng giống production.

### Production canary

Trước khi chuyển traffic:

- Xác nhận instance Java 17 healthy và ready.
- Xác nhận đúng JDK/version/image.
- Xác nhận agent và metrics đang gửi dữ liệu.
- Chạy smoke test read-only hoặc luồng thử nghiệm an toàn.
- Xác nhận database/broker compatibility.
- Xác nhận rollback revision cũ còn sẵn sàng.

Sau đó chuyển một phần traffic, theo dõi trong khoảng thời gian đủ để quan sát workload đại diện. Nếu hệ thống có batch theo giờ hoặc scheduled job, cửa sổ canary phải bao gồm hoặc chủ động kiểm thử các luồng đó.

## 10. Quan sát sau khi triển khai

Quan sát cần kết hợp ba lớp: service, JVM và nghiệp vụ. So sánh canary Java 17 với phiên bản cũ trong cùng khoảng thời gian và điều kiện tải tương đương.

### Golden signals của service

| Signal | Câu hỏi cần trả lời |
| --- | --- |
| Traffic | Java 17 có nhận đúng lưu lượng dự kiến không? |
| Errors | Error rate, timeout hoặc retry có tăng không? |
| Latency | p50/p95/p99 có xấu đi không? |
| Saturation | CPU, memory, thread pool, connection pool hoặc queue có gần giới hạn không? |

Theo dõi theo endpoint, tenant/segment, region và loại tác vụ nếu hệ thống có phân nhóm. Một trung bình toàn service có thể che một endpoint hoặc một nhóm người dùng đang lỗi.

### JVM metrics

Các metric nên có:

- Heap used/committed/max và tỷ lệ sau GC.
- Allocation rate và object promotion.
- GC pause count/time, pause duration và frequency.
- Metaspace và direct buffer/native memory nếu ứng dụng sử dụng.
- Thread count, peak thread count, blocked/waiting threads.
- Class loading/unloading.
- Process CPU, uptime và restart count.
- JIT compilation nếu công cụ giám sát hỗ trợ.

Không chỉ xem heap trước GC. Heap có thể tăng trong lúc tải cao nhưng được thu hồi bình thường; live set sau GC và xu hướng tăng theo thời gian thường hữu ích hơn để nhận biết memory leak.

### Log, trace và lỗi runtime

Tìm kiếm có chủ đích:

- UnsatisfiedLinkError, NoClassDefFoundError, NoSuchMethodError.
- InaccessibleObjectException và IllegalAccessException.
- SSLHandshakeException, certificate path và protocol errors.
- OutOfMemoryError, GC overhead hoặc container OOM kill.
- RejectedExecutionException, queue saturation và timeout.
- ClassCastException hoặc serialization/deserialization errors.
- Connection reset, pool exhaustion và retry storm.

Log cần có application version và runtime version để xác định lỗi thuộc nhóm Java cũ hay Java 17.

### GC logging trên Java 17

Java 17 dùng unified logging. Có thể bật log GC có kiểm soát:

~~~bash
-Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags
~~~

Đường dẫn file và rotation cần được cấu hình theo môi trường triển khai. Không ghi log vô hạn vào filesystem nhỏ của container. Nếu đã có metrics/JFR, chọn mức log đủ để điều tra mà không làm tăng I/O quá mức.

### Java Flight Recorder

JFR giúp quan sát compilation, GC, thread, allocation và nhiều runtime event. Có thể bật recording khi khởi động hoặc dùng jcmd trên môi trường cho phép attach:

~~~bash
jcmd <pid> JFR.start name=java17-rollout settings=profile duration=5m filename=java17-rollout.jfr
~~~

Đây là ví dụ lệnh chẩn đoán; quyền attach, container namespace và cấu hình runtime có thể ảnh hưởng khả năng chạy. Recording có overhead nên chọn thời lượng và event phù hợp. Không cần ghi profile chi tiết liên tục nếu mục tiêu chỉ là theo dõi metric vận hành.

## 11. Đặt tiêu chí go/no-go trước khi canary

Không chờ tới lúc production có sự cố mới thống nhất thế nào là thất bại. Trước rollout, chủ service, SRE và product owner nên xác định ngưỡng dựa trên SLO và baseline.

Ví dụ nhóm tiêu chí:

| Nhóm | Tiêu chí cần định nghĩa |
| --- | --- |
| Availability | Error rate và health check trong giới hạn SLO |
| Latency | p95/p99 không vượt ngưỡng đã thống nhất |
| Throughput | Không giảm bất thường ở cùng mức traffic |
| JVM memory | Heap/live set ổn định, không tăng liên tục |
| GC | Pause và frequency không gây vi phạm latency |
| CPU | Không tăng tới mức saturation hoặc throttling |
| Stability | Không restart loop, crash hoặc OOM kill |
| Dependencies | DB, broker, HTTP và TLS không tăng lỗi |
| Business | Tỷ lệ transaction/job thành công giữ trong ngưỡng |

Ngưỡng phải có baseline và thời gian đánh giá. Ví dụ, tăng error rate trong một phút có thể là nhiễu; tăng kéo dài qua nhiều cửa sổ hoặc ảnh hưởng SLO là tín hiệu nghiêm trọng hơn. Không dùng một con số chung cho mọi ứng dụng.

### Ví dụ rule canary

Các con số sau chỉ minh họa cách viết rule; đội vận hành phải thay bằng SLO thực tế:

- Dừng mở rộng canary nếu error rate vượt ngưỡng đã định trong hai cửa sổ liên tiếp.
- Rollback nếu p99 vượt SLO trong thời gian đủ dài và có tương quan với nhóm Java 17.
- Rollback ngay nếu có data corruption, mất dữ liệu, security regression hoặc lỗi nghiệp vụ nghiêm trọng.
- Dừng rollout nếu JVM restart/OOM tăng rõ rệt so với baseline.
- Tiếp tục khi chỉ số ổn định qua peak workload và các scheduled jobs quan trọng.

Tách **stop rollout** và **rollback**. Một cảnh báo chưa rõ nguyên nhân có thể đủ để dừng mở rộng, nhưng chưa chắc cần rollback toàn bộ. Ngược lại, data corruption hoặc vi phạm bảo mật có thể cần rollback ngay mà không chờ đủ cửa sổ thống kê.

## 12. Quy trình mở rộng canary

Một quy trình mẫu:

1. Deploy một instance hoặc nhóm nhỏ Java 17.
2. Xác nhận readiness, startup và smoke test.
3. Chuyển traffic nhỏ, ví dụ 1–5% nếu phù hợp quy mô.
4. So sánh golden signals và business metrics với nhóm cũ.
5. Kiểm tra log, trace, GC và memory trend.
6. Chạy các luồng nghiệp vụ chính và scheduled jobs có thể kiểm thử an toàn.
7. Nếu đạt, tăng tỷ lệ theo các bước đã định.
8. Dừng ở mỗi bước để đánh giá trước khi tăng tiếp.
9. Sau khi toàn bộ traffic đã chuyển, giữ phiên bản cũ trong cửa sổ rollback.

Tỷ lệ traffic nên phản ánh khả năng giới hạn blast radius. Với service có traffic thấp, phần trăm nhỏ có thể tạo quá ít mẫu; dùng số instance hoặc nhóm request đại diện để đánh giá.

### Giữ hai phiên bản tương thích trong thời gian chuyển tiếp

Trong rolling/canary, request có thể đi qua service cũ rồi tới service mới. Cần bảo đảm:

- API request/response tương thích.
- Schema database được cả hai phiên bản hỗ trợ.
- Message format không làm consumer cũ lỗi.
- Cache/session có thể đọc trong giai đoạn chuyển đổi.
- Feature flags có giá trị nhất quán.
- Không có migration phá hủy trước khi hoàn tất cửa sổ rollback.

Nếu không thể duy trì tương thích hai chiều, cần dùng chiến lược chuyển đổi có kiểm soát như tạm dừng producer, drain queue, chuyển traffic theo boundary hoặc thực hiện migration riêng có kế hoạch phục hồi.

## 13. Quyết định rollback

Rollback khi rủi ro hoặc tác động vượt tiêu chí đã thống nhất, đặc biệt khi:

- Availability hoặc latency vi phạm SLO do phiên bản mới.
- Lỗi runtime nghiêm trọng xuất hiện trên đường nghiệp vụ chính.
- Memory/CPU/GC khiến service mất khả năng phục vụ.
- Dependency quan trọng không kết nối được.
- Data corruption, duplicate hoặc missing transaction.
- Security/TLS/authentication regression.
- Không thể duy trì tương thích với các service hoặc consumer hiện tại.

Không rollback chỉ vì một metric đơn lẻ dao động nhẹ nếu chưa xác định ý nghĩa. Nhưng cũng không trì hoãn khi có dấu hiệu mất dữ liệu hoặc vi phạm bảo mật.

### Quy trình rollback ứng dụng

1. Dừng mở rộng rollout và khóa pipeline deploy tiếp theo.
2. Xác định blast radius: service, instance, region, tenant và dữ liệu liên quan.
3. Chuyển traffic về phiên bản cũ hoặc scale up nhóm cũ.
4. Khôi phục image/JDK/config revision đã lưu.
5. Tắt hoặc đảo feature flag nếu thay đổi đó có thể gây lỗi.
6. Giữ log/trace/JFR và thông tin deployment của nhóm Java 17 để điều tra.
7. Xác nhận health, error rate, latency và throughput của phiên bản cũ.
8. Kiểm tra queue, retry, transaction và dữ liệu phát sinh trong thời gian phiên bản mới hoạt động.
9. Thông báo trạng thái theo quy trình incident của tổ chức.
10. Ghi lại quyết định, thời điểm, người thực hiện và kết quả.

Rollback binary thường nhanh hơn rollback database. Không chạy migration ngược tự động nếu migration đó có thể mất dữ liệu hoặc không có script reverse đã được kiểm thử.

### Khi rollback không đơn giản

Nếu phiên bản mới đã:

- Ghi schema hoặc payload chỉ phiên bản mới đọc được.
- Phát message không tương thích với consumer cũ.
- Thay đổi trạng thái nghiệp vụ không thể đảo ngược.
- Xóa hoặc biến đổi dữ liệu cũ.
- Thay đổi cache/session format đang được dùng chung.

thì chỉ chuyển traffic về binary cũ có thể làm lỗi nặng hơn. Khi đó cần runbook tương thích dữ liệu: giữ phiên bản mới cho một nhóm xử lý, chuyển đổi payload, chạy compensating action hoặc khôi phục backup theo RPO/RTO đã định. Đây là lý do schema expand-contract và backward-compatible message cần được chuẩn bị trước rollout.

## 14. Diễn tập rollback trước production

Rollback chỉ đáng tin khi đã thử trong môi trường tương đương. Thực hiện ít nhất một lần:

1. Deploy bản cũ.
2. Deploy Java 17 theo đúng quy trình.
3. Tạo một thay đổi dữ liệu đại diện.
4. Giả lập điều kiện rollback đã định.
5. Chuyển traffic về bản cũ.
6. Kiểm tra bản cũ đọc được dữ liệu và tiếp tục xử lý.
7. Kiểm tra queue, cache, session và scheduled job.
8. Đo thời gian hoàn thành rollback.
9. Ghi lại bước nào cần quyền thủ công hoặc phụ thuộc bên ngoài.

Nếu rollback yêu cầu thao tác thủ công, hãy viết rõ người chịu trách nhiệm và cách xác nhận. Đừng để một runbook chỉ có các lệnh không có điều kiện kiểm tra kết quả.

## 15. Hoàn tất rollout và đóng cửa sổ rollback

Sau khi toàn bộ traffic chạy Java 17:

- Theo dõi qua ít nhất một chu kỳ peak traffic.
- Chờ scheduled job, batch và tác vụ định kỳ quan trọng chạy thành công.
- Kiểm tra error rate, latency, JVM memory, GC và CPU.
- Kiểm tra nghiệp vụ và reconciliation.
- Xác nhận queue lag, retry và dead-letter queue ở mức bình thường.
- Kiểm tra alert không tăng bất thường.
- Xác nhận không còn instance hoặc worker dùng runtime cũ ngoài dự kiến.

Chỉ đóng cửa sổ rollback khi:

- Tất cả luồng quan trọng đã được xác nhận.
- Schema/data đã ở trạng thái tương thích với quyết định phát hành.
- Không còn message hoặc consumer cần phiên bản cũ.
- Artifact cũ và backup được giữ theo chính sách lưu trữ.
- Chủ hệ thống chấp nhận rủi ro còn lại.

Sau đó mới thực hiện contract migration như xóa cột cũ, bỏ adapter tương thích hoặc dọn cache namespace cũ. Đây là bước riêng, có review và kế hoạch phục hồi.

## 16. Phân vai và trách nhiệm

Một rollout thường cần nhiều vai trò:

| Vai trò | Trách nhiệm |
| --- | --- |
| Application owner | Xác nhận hành vi ứng dụng, test và tiêu chí nghiệp vụ |
| Platform/DevOps | JDK image, build pipeline, deployment và rollback mechanics |
| SRE/Operations | Dashboard, alert, SLO, canary observation và incident handling |
| Database owner | Schema migration, backfill, backup và data compatibility |
| Security | TLS, certificate, provider, agent và security regression |
| QA | Regression, integration, contract và exploratory testing |
| Product/business owner | Xác nhận tác động nghiệp vụ và chấp nhận rollout |

Mỗi hành động quan trọng cần có người chịu trách nhiệm và người quyết định go/no-go. Một checklist không có owner thường bị bỏ sót khi rollout gấp.

## 17. Mẫu timeline triển khai

Timeline dưới đây chỉ là ví dụ; thời gian thực tế phụ thuộc độ phức tạp, mức độ rủi ro và khả năng kiểm thử.

| Giai đoạn | Công việc | Điều kiện chuyển bước |
| --- | --- | --- |
| Chuẩn bị | Inventory, migration review, dependency upgrades, baseline | Có danh sách rủi ro và owner |
| Build/test | Release 17, unit/integration/contract tests | CI xanh trên Java 17 |
| Staging | Load/soak/failure tests, rollback rehearsal | SLO và rollback đạt |
| Canary | Nhóm nhỏ Java 17, quan sát thực tế | Metrics và business checks ổn định |
| Progressive rollout | Tăng traffic theo batch | Mỗi batch đạt tiêu chí |
| Stabilization | Theo dõi peak, batch, queue và memory trend | Không còn vấn đề mở |
| Close rollback window | Giữ artifact cũ theo chính sách, kết thúc chuyển đổi | Owner xác nhận |
| Contract cleanup | Dọn schema/config/compatibility code cũ | Đã hết consumer phiên bản cũ |

Không gộp contract cleanup vào cùng một bước với rollout runtime nếu việc xóa cấu trúc cũ làm mất khả năng quay lui.

## 18. Mẫu runbook go/no-go

Trước khi bắt đầu:

- [ ] JDK 17 vendor/version và image đã được xác nhận.
- [ ] Build dùng release 17.
- [ ] Unit, integration, contract và performance tests đạt.
- [ ] Dependency, agent và native libraries hỗ trợ Java 17.
- [ ] Baseline dashboard và alert sẵn sàng.
- [ ] Canary routing và rollback revision đã kiểm tra.
- [ ] Schema/message/cache tương thích trong thời gian hai phiên bản cùng chạy.
- [ ] Người quyết định go/no-go và người thực hiện rollback đã được xác định.

Trong canary:

- [ ] Readiness và smoke test đạt.
- [ ] Error rate và latency nằm trong ngưỡng.
- [ ] Throughput và business metrics bình thường.
- [ ] CPU, heap, GC và thread ổn định.
- [ ] DB, broker, TLS và native integration hoạt động.
- [ ] Không có lỗi runtime mới nghiêm trọng.
- [ ] Đã quan sát đủ loại workload và scheduled jobs quan trọng.

Khi mở rộng:

- [ ] Từng batch được đánh giá trước khi tăng traffic.
- [ ] Phiên bản cũ vẫn có thể phục vụ rollback.
- [ ] Không có migration phá hủy trong cửa sổ rollback.
- [ ] Queue/cache/session không tạo dependency một chiều.

Khi kết thúc:

- [ ] Toàn bộ instance chạy đúng JDK 17.
- [ ] Không còn lỗi hoặc alert tăng bất thường.
- [ ] Reconciliation nghiệp vụ đạt.
- [ ] Rollback window được đóng có chủ đích.
- [ ] Contract cleanup có lịch và owner riêng.

## 19. Sau rollout: ghi nhận và cải thiện

Sau khi nâng cấp ổn định:

- Ghi lại JDK vendor/version, build image, JVM flags và dependency set cuối cùng.
- Lưu baseline trước/sau cùng báo cáo performance.
- Ghi nhận vấn đề gặp phải và cách giải quyết.
- Loại bỏ flag/workaround không còn cần.
- Cập nhật runbook, dashboard và alert.
- Cập nhật tài liệu phát triển để local/CI dùng cùng release target.
- Lập lịch cập nhật bảo mật tiếp theo cho dòng JDK 17 theo chính sách hỗ trợ.

Nếu rollout phải rollback, giữ nguyên artifact, log, trace, JFR, JVM args và deployment metadata để điều tra. Khi thử lại, thay đổi một nhóm nguyên nhân có kiểm soát và chạy lại test liên quan; không lặp lại cùng một rollout mà chưa hiểu lý do thất bại.

## 20. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chỉ compile trên JDK mới | Có thể gọi API không tồn tại trong runtime đích | Dùng release 17 và test bằng JDK 17 |
| Chỉ nâng JDK, không nâng agent | APM/coverage/profiler có thể lỗi khi startup hoặc instrumentation | Xác minh agent support matrix |
| Copy toàn bộ JVM flags cũ | Flag lỗi thời hoặc cấu hình không phù hợp | Audit từng flag, giữ baseline và đo |
| Dùng canary quá nhỏ | Không đủ mẫu để phát hiện lỗi | Chọn tỷ lệ và thời gian theo traffic |
| Chuyển toàn bộ traffic một lần | Blast radius lớn | Progressive rollout hoặc blue-green |
| Không giữ artifact cũ | Rollback chậm hoặc không tái lập | Lưu artifact/image digest bất biến |
| Migration database phá hủy sớm | Binary cũ không đọc được dữ liệu sau rollback | Expand-contract và trì hoãn contract |
| Producer mới đổi message không tương thích | Consumer cũ lỗi trong rolling deployment | Version schema và contract test |
| Chỉ xem CPU/heap | Bỏ sót lỗi nghiệp vụ hoặc latency | Kết hợp golden signals và business metrics |
| Đổi JDK, GC, heap và framework cùng lúc | Khó xác định nguyên nhân regression | Thay đổi theo nhóm và đo có kiểm soát |
| Dùng staging khác xa production | Không phát hiện vấn đề tài nguyên/runtime | Đồng bộ image, flags, agent và limits |
| Không diễn tập rollback | Runbook có thể thất bại lúc incident | Thử rollback trước production |
| Xóa phiên bản cũ ngay sau rollout | Mất đường lui khi lỗi xuất hiện muộn | Giữ rollback window theo rủi ro |
| Rollback binary nhưng bỏ qua dữ liệu | Phiên bản cũ có thể hỏng khi đọc dữ liệu mới | Data compatibility và reconciliation |

## 21. Nguyên tắc thực hành

Khi triển khai nâng cấp lên Java 17:

1. Kiểm kê toàn bộ service, job, dependency, agent, native library và startup configuration.
2. Đọc migration notes của các release đã bỏ qua và kiểm tra strong encapsulation, API tách khỏi JDK, TLS và runtime behavior.
3. Chốt JDK 17 vendor/build được hỗ trợ; pin toolchain và dùng release 17.
4. Chạy test trên runtime Java 17 thật, bao gồm integration, contract, performance và soak.
5. Thu thập baseline service, JVM, host và business metrics trước khi thay đổi.
6. Chuẩn bị artifact/config rollback và bảo đảm database, message, cache, session tương thích giữa hai phiên bản.
7. Chọn canary, rolling hoặc blue-green theo khả năng giới hạn blast radius.
8. Định nghĩa go/no-go và rollback criteria dựa trên SLO trước rollout.
9. Theo dõi traffic, errors, latency, saturation, GC, memory, logs, traces và nghiệp vụ trong từng bước.
10. Diễn tập rollback; chỉ đóng cửa sổ rollback sau khi peak workload, scheduled jobs và reconciliation đều đạt.
11. Thực hiện contract cleanup sau rollout như một thay đổi riêng.
12. Lưu bằng chứng, cấu hình và kết quả để lần cập nhật JDK tiếp theo có thể tái lập.

Một đợt nâng cấp Java 17 hoàn tất khi ứng dụng chạy ổn định trên runtime đích, các dependency và luồng nghiệp vụ đã được xác nhận, số liệu vận hành nằm trong giới hạn chấp nhận, và đội ngũ có thể giải thích rõ cách dừng hoặc quay lui nếu xuất hiện regression. Việc chuẩn bị rollback cùng lúc với chuẩn bị triển khai giúp giảm rủi ro dữ liệu và rút ngắn thời gian phục hồi khi sự cố xảy ra.
