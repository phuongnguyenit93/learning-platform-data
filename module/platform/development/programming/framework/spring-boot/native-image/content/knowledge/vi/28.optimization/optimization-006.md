# Garbage collector và các tùy chọn khả dụng theo distribution, phiên bản

## 1. Vì sao cần chọn garbage collector cho Native Image?

Garbage collector (GC) thu hồi vùng nhớ của các object Java không còn được sử dụng. Khi chuyển Spring Boot từ JVM sang GraalVM Native Image, ứng dụng vẫn cần quản lý heap, allocation, object lifetime và áp lực bộ nhớ. Tuy nhiên, GC của Native Image có tập lựa chọn, đặc điểm và giới hạn phụ thuộc GraalVM distribution, phiên bản, hệ điều hành và kiến trúc mục tiêu.

Không nên mặc định native executable luôn dùng cùng GC như HotSpot JVM, hoặc cho rằng mọi GC có trong JDK đều có sẵn trong Native Image. Tùy chọn được hỗ trợ có thể khác giữa GraalVM Community, Oracle GraalVM, các bản thương mại và các release. Một build argument hợp lệ ở máy này có thể bị từ chối ở toolchain khác.

Trong module SPRING_BOOT_NATIVE_IMAGE, bài học này tập trung vào cách xác định GC khả dụng, hiểu các lựa chọn phổ biến như Serial và G1, nhận diện Epsilon nếu distribution hỗ trợ, cấu hình heap, và đo workload trước khi chọn. Mục tiêu là chọn GC theo latency, throughput, footprint và giới hạn container thay vì dựa trên tên GC hoặc mặc định của một môi trường khác.

## 2. GC của Native Image khác gì với GC trên HotSpot?

Native Image tạo executable trước khi chạy. Runtime của executable vẫn có bộ quản lý bộ nhớ và GC, nhưng không phải toàn bộ HotSpot JVM runtime. Một số collector, diagnostic option và tuning flag của HotSpot có thể không được hỗ trợ hoặc có semantics khác.

Cần phân biệt:

- **Build-time options:** lựa chọn GC và cấu hình runtime được ghi vào executable khi Native Image được tạo.
- **Runtime options:** giới hạn heap hoặc tham số có thể truyền khi khởi chạy, nếu runtime hỗ trợ.
- **HotSpot flags:** tùy chọn dành cho JVM như một số XX collector-specific flags; không mặc định áp dụng cho native executable.
- **Container limits:** giới hạn CPU/RAM do Docker/Kubernetes/cgroup áp đặt, độc lập với GC nhưng ảnh hưởng trực tiếp đến hành vi cấp phát và thu hồi bộ nhớ.

Ví dụ, tùy chọn UseG1GC là cách chọn G1 quen thuộc trong HotSpot. Với Native Image, cách chọn GC thường được thực hiện bằng option Native Image như --gc=... nếu collector đó được distribution hỗ trợ. Hãy dùng help/documentation của native-image compiler thực tế.

## 3. Xác định distribution và phiên bản trước khi cấu hình

Trước khi chọn GC, ghi lại toolchain:

    native-image --version
    java -version
    native-image --help

Nếu dùng GraalVM distribution có lệnh hoặc package manager riêng, xác minh executable native-image mà build plugin thực sự gọi. Trên CI có thể tồn tại nhiều JDK/GraalVM installations; java và native-image không nhất thiết đến từ cùng một distribution nếu PATH được cấu hình sai.

Ghi lại:

- Distribution/vendor và edition.
- GraalVM version/build number.
- JDK version.
- Native Image component đã cài.
- OS và target architecture.
- Native Build Tools version.
- Spring Boot version.
- Các option GC được compiler liệt kê hoặc tài liệu release xác nhận.

Không ghi đơn giản “GraalVM latest”. Khi so sánh GC hoặc tái lập build, version chính xác là một phần của kết quả.

## 4. Những collector thường gặp và phạm vi hỗ trợ

Native Image có các lựa chọn GC phổ biến, nhưng danh sách khả dụng thay đổi theo distribution và release:

| Collector | Đặc điểm tổng quát | Cần xác minh |
|---|---|---|
| Serial GC | Collector đơn giản, thường có footprint thấp; phù hợp workload nhỏ hoặc ít contention | Thường là lựa chọn mặc định trong nhiều Native Image distributions |
| G1 GC | Collector phân vùng heap, hướng tới cân bằng throughput và pause time ở heap lớn | Có thể phụ thuộc edition/distribution và version |
| Epsilon GC | No-op GC, không thu hồi object; chỉ phù hợp tiến trình có vòng đời/heap được kiểm soát rất chặt | Có thể experimental hoặc không có trong distribution; không dùng như GC production thông thường |

Bảng này là định hướng, không phải cam kết support cho mọi GraalVM release. Một số distribution chỉ cung cấp Serial; G1 có thể chỉ xuất hiện trong một số edition/version; Epsilon có thể không được cung cấp hoặc không được khuyến nghị. Luôn kiểm tra tài liệu của vendor và native-image --help tại toolchain đang build.

## 5. Serial GC

Serial GC là collector đơn giản, thường phù hợp ứng dụng có heap nhỏ đến vừa, số thread/CPU hạn chế hoặc yêu cầu footprint thấp. Nó có thể giảm overhead quản lý so với collector phức tạp hơn, nhưng hoạt động thu gom có thể gây pause đáng kể khi heap lớn hoặc allocation pressure cao.

Với dịch vụ Spring Boot native, Serial GC có thể là điểm bắt đầu hợp lý khi:

- Workload không tạo quá nhiều object mỗi giây.
- Số core được cấp thấp.
- Heap và live set vừa phải.
- Ưu tiên footprint và tính đơn giản.
- Latency target không bị ảnh hưởng bởi pause đo được.

Không suy ra Serial luôn nhanh hoặc ít RAM hơn trong mọi trường hợp. Allocation rate, object graph, thread count và live set mới quyết định kết quả.

Trong nhiều Native Image distributions, Serial là mặc định. Tuy vậy, nên ghi rõ GC được dùng trong build report/log thay vì dựa vào giả định.

## 6. G1 GC

G1 chia heap thành các region và thu gom theo vùng, hướng tới cân bằng throughput và thời gian pause cho heap lớn. Trên Native Image, G1 chỉ khả dụng trong một số distribution/edition/version. Không phải mọi GraalVM Community hoặc bản JDK có G1 đều đồng nghĩa Native Image G1 có sẵn.

Nếu compiler hỗ trợ, có thể chọn bằng option dạng:

    native-image --gc=G1 -o orders-service ...

Cú pháp và giá trị chính xác phải được xác nhận bằng help/documentation của release. Nếu compiler báo GC không được hỗ trợ, không nên cố truyền HotSpot flag thay thế.

G1 có thể đáng thử khi:

- Heap lớn hoặc live set lớn.
- Nhiều thread tạo object đồng thời.
- Throughput và pause time cần cân bằng.
- Serial GC gây pause/latency vượt mục tiêu trong benchmark.

G1 có thể tăng overhead hoặc memory footprint. Hãy so sánh với Serial trên cùng workload và resource limits.

## 7. Epsilon GC và trường hợp đặc biệt

Epsilon là no-op garbage collector: nó cấp phát nhưng không thu hồi object. Khi heap cạn, process có thể thất bại thay vì thu gom để lấy lại vùng nhớ. Vì vậy, nó chỉ phù hợp tình huống đặc biệt như tiến trình chạy ngắn, allocation được giới hạn trước và heap đủ lớn với vòng đời process rõ ràng.

Không dùng Epsilon cho web service Spring Boot chạy liên tục hoặc workload có allocation không giới hạn. Một request burst, cache tăng trưởng hoặc object retention ngoài dự kiến có thể làm process hết heap.

Nếu Native Image distribution có Epsilon, hãy xem nó như một lựa chọn chuyên biệt để đo/kiểm thử use case có kiểm soát. Xác minh option và support status trong release docs; không giả định --gc=epsilon được chấp nhận ở mọi phiên bản.

## 8. Chọn GC bằng Native Image build argument

Native Image thường sử dụng option --gc để chọn collector khi collector đó được hỗ trợ:

    native-image --gc=serial -o orders-service ...

Hoặc nếu toolchain hỗ trợ G1:

    native-image --gc=G1 -o orders-service ...

Tên giá trị có thể phân biệt chữ hoa/thường theo CLI/version. Hãy sao chép đúng giá trị từ help và tài liệu chính thức của toolchain. Nếu bỏ option, compiler dùng default của distribution/version đó.

Đừng trộn cú pháp chọn GC của HotSpot (-XX:+UseG1GC) với option Native Image. Một số runtime flags có thể được hỗ trợ ở native, nhưng chỉ dùng khi Native Image documentation xác nhận rõ.

## 9. Truyền GC option qua Gradle

Với GraalVM Native Build Tools Gradle plugin, build arguments thường được đặt trên binary:

    graalvmNative {
        binaries {
            main {
                buildArgs.add('--gc=serial')
            }
        }
    }

Nếu muốn thử G1 và distribution hỗ trợ:

    graalvmNative {
        binaries {
            main {
                buildArgs.add('--gc=G1')
            }
        }
    }

Đây là ví dụ cấu hình; DSL và plugin version cần được kiểm tra theo dự án. Đảm bảo task native đang dùng đúng binary configuration và log hiển thị argument. Nếu có nhiều binary (main/test), cấu hình đúng target cần đo.

Không thêm đồng thời nhiều lựa chọn GC vào cùng một build. Mỗi lần build benchmark nên chọn một collector rõ ràng để kết quả có thể so sánh.

## 10. Truyền GC option qua Maven

Với Native Maven Plugin, build argument có thể khai báo trong cấu hình plugin:

    <plugin>
        <groupId>org.graalvm.buildtools</groupId>
        <artifactId>native-maven-plugin</artifactId>
        <configuration>
            <buildArgs>
                <buildArg>--gc=serial</buildArg>
            </buildArgs>
        </configuration>
    </plugin>

Đây là ví dụ minh họa. Xác nhận plugin version, execution và profile native thực tế của dự án. Nếu dùng nhiều Maven profile cho các biến thể GC, bảo đảm mỗi profile tạo artifact riêng và log ghi rõ lựa chọn.

Không chỉnh POM chỉ dựa trên ví dụ nếu plugin hiện tại nhận arguments qua cấu hình khác. Mục tiêu là chứng minh compiler đã nhận option, không chỉ có chuỗi trong file build.

## 11. Thiết lập giới hạn heap

GC hoạt động trong phạm vi heap của process. Native executable có thể nhận các runtime memory options được hỗ trợ như -Xms và -Xmx, nhưng mức hỗ trợ và semantics cần kiểm tra theo Native Image version.

Ví dụ chạy:

    ./orders-service -Xms128m -Xmx512m

-Xms đặt heap ban đầu; -Xmx giới hạn heap tối đa theo semantics runtime hỗ trợ. Không đồng nhất -Xmx với memory limit container: RSS còn bao gồm native memory, thread stacks, code, mapped files và các vùng ngoài Java heap.

Nếu container giới hạn 512 MiB mà heap max cũng đặt 512 MiB, process vẫn có thể OOM do phần memory ngoài heap. Cần để lại headroom và đo cgroup memory thực tế.

## 12. Phân biệt heap, RSS và container memory

Các chỉ số sau không thể thay thế cho nhau:

| Chỉ số | Nội dung |
|---|---|
| Java heap | Vùng quản lý object bởi GC |
| Live set | Object còn được tham chiếu sau thu gom |
| Allocation rate | Lượng object/byte được tạo theo thời gian |
| RSS | Trang bộ nhớ resident của process |
| Container/cgroup memory | Bộ nhớ được tính cho container/cgroup |
| Memory limit | Giới hạn do runtime/orchestrator áp đặt |

GC chủ yếu quản lý heap. Giảm heap không chắc giảm RSS theo cùng tỷ lệ; tăng heap có thể giảm tần suất collection nhưng làm tăng memory ceiling. Native Image còn dùng memory ngoài heap cho code, metadata, thread và native libraries.

Khi benchmark, ghi cả heap-related metrics nếu có và RSS/cgroup memory. Đừng tuyên bố GC tối ưu chỉ từ một số đo docker stats tại một thời điểm.

## 13. Hiểu live set và allocation rate trước khi đổi GC

Hai workload có cùng request rate vẫn có thể tạo áp lực GC khác nhau:

- Workload A tạo nhiều object ngắn hạn nhưng live set nhỏ.
- Workload B tạo ít object hơn nhưng giữ cache/object graph lớn.
- Workload C có burst allocation khi parse JSON hoặc render PDF.
- Workload D giữ buffer/native resource lâu hơn dự kiến.

GC cần xử lý allocation và live objects, không chỉ tổng số request. Trước khi đổi collector, đo:

- Allocation rate theo thời gian.
- Live heap sau collection.
- Collection frequency và pause nếu runtime cung cấp.
- Số thread và mức đồng thời.
- Object retention/caches.
- Peak memory khi traffic burst.

Nếu live set tăng liên tục, vấn đề có thể là memory leak hoặc cache không giới hạn, không phải lựa chọn GC. Đổi collector không sửa được object bị giữ tham chiếu mãi.

## 14. Chọn GC theo workload và mục tiêu

| Workload | Hướng bắt đầu | Điều cần đo |
|---|---|---|
| API nhỏ, ít core, heap thấp | Serial nếu có sẵn | RSS, pause, p95/p99 |
| API nhiều request đồng thời, heap lớn | So sánh Serial và G1 nếu được hỗ trợ | Throughput, pause, CPU, memory |
| Job chạy ngắn, dữ liệu/heap có giới hạn rõ | Đánh giá GC phù hợp với vòng đời; Epsilon chỉ trong trường hợp đặc biệt và có giới hạn | Peak heap, OOM, thời gian job |
| Service chạy dài, cache lớn | Collector được hỗ trợ và phù hợp heap; theo dõi retention | Live set, pause, RSS theo thời gian |
| Container memory rất nhỏ | Serial thường là baseline đáng thử | Headroom, OOM, tail latency |

Đây là hướng bắt đầu chứ không phải quy tắc cố định. Một collector phù hợp cần đáp ứng SLO và memory limit dưới tải đại diện.

## 15. Kiểm tra GC option có thật sự được sử dụng

Sau khi cấu hình, xác minh theo nhiều bước:

1. Kiểm tra native-image --version và help của đúng compiler.
2. Chạy build với GC argument đã chọn.
3. Xác nhận log compiler không bỏ qua hoặc từ chối option.
4. Lưu command line/build report nếu có.
5. Khởi chạy executable và xác minh runtime behavior bằng workload.
6. Thu metrics/diagnostics mà distribution hỗ trợ.
7. Ghi GC selection trong benchmark report.

Không dựa vào POM/Gradle file đơn thuần. Build plugin có thể không áp dụng cấu hình cho task/binary bạn đang chạy. Nếu compiler không in GC selection rõ ràng, đối chiếu tài liệu và chạy kiểm thử có thể quan sát.

## 16. Tuning heap và GC cần có headroom container

Giả sử container có memory limit 1 GiB. Không nên tự động đặt -Xmx1g, vì process còn cần memory ngoài heap. Có thể bắt đầu với giới hạn heap thấp hơn, sau đó đo peak cgroup memory dưới tải.

Ví dụ cấu hình runtime trong Kubernetes:

    resources:
      requests:
        memory: "768Mi"
        cpu: "500m"
      limits:
        memory: "1Gi"
        cpu: "1"

Đây là ví dụ resource budget, không phải heap sizing recommendation. -Xmx cần được chọn dựa trên live set, allocation burst và overhead native. CPU limit cũng ảnh hưởng GC concurrency/throughput, đặc biệt khi collector cần worker threads.

Nếu process bị OOMKilled, kiểm tra container event và cgroup metrics. Tăng -Xmx trong khi container limit không đổi có thể làm tình hình xấu đi.

## 17. Benchmark GC công bằng

Để so Serial với G1 hoặc collector khác:

- Cùng source revision và dependency.
- Cùng GraalVM distribution/version.
- Cùng CPU/RAM limits và container base image.
- Cùng heap bounds nếu mục tiêu là so collector; nếu heap khác nhau, ghi rõ.
- Cùng request mix, data set, concurrency và warm-up policy.
- Cùng số lần chạy và thời gian đo.
- Cùng observability overhead.
- Chạy riêng từng binary/collector, tránh process cũ còn chạy.

Đo ít nhất:

| Metric | Mục đích |
|---|---|
| Throughput | Khả năng xử lý tổng |
| p50/p95/p99 latency | Trải nghiệm và tail latency |
| GC pause/frequency | Tác động thu gom |
| CPU usage | Overhead collector |
| Peak heap/live set | Áp lực heap |
| RSS/cgroup peak | Mức dùng memory thực |
| OOM/restarts | Độ ổn định |
| Startup/readiness | Chi phí khởi động |

Chạy nhiều lượt và báo median/phân phối. Một lần benchmark ngắn có thể bỏ lỡ memory growth hoặc GC behavior sau thời gian dài.

## 18. Các lỗi thường gặp khi đổi GC

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Compiler từ chối --gc=G1 | Distribution/edition/version không hỗ trợ | Kiểm tra support matrix và help |
| -XX:+UseG1GC không có tác dụng | Dùng HotSpot flag không phù hợp Native Image | Dùng Native Image option được tài liệu xác nhận |
| RSS vượt container limit dù heap dưới Xmx | Native memory, stacks, code hoặc buffers ngoài heap | Đo cgroup và để headroom |
| Serial pause cao | Heap/live set lớn hoặc allocation pressure | Profile workload, thử collector khác nếu có |
| G1 dùng nhiều memory hơn | Collector overhead/region structures | So sánh tổng RSS và SLO |
| Epsilon hết heap | Không thu hồi object | Không dùng cho service dài hạn; chọn GC thu gom |
| OOM khi traffic burst | Heap limit hoặc container limit không đủ | Đo burst, sizing heap và memory budget |
| Heap tăng liên tục | Object retention/cache leak | Phân tích object lifecycle, không chỉ đổi GC |

## 19. Bài thực hành: so sánh Serial và collector khác nếu khả dụng

**Bối cảnh:** Order API native chạy trong container 1 GiB, cần giữ p99 latency dưới SLO và xử lý burst request.

**Bước 1 — Xác định toolchain.** Ghi distribution, edition, version, JDK và danh sách GC được hỗ trợ.

**Bước 2 — Build baseline.** Tạo native executable với GC mặc định; lưu build log, build time và binary digest.

**Bước 3 — Đo baseline.** Chạy cùng request mix/concurrency, thu throughput, p95/p99, RSS, cgroup peak, heap metrics và OOM/restart.

**Bước 4 — Build biến thể Serial.** Nếu Serial là default, ghi rõ điều đó; không cần tạo biến thể giả khác nhau.

**Bước 5 — Build biến thể G1.** Chỉ thực hiện nếu distribution/version xác nhận hỗ trợ; dùng option đúng và lưu build arguments.

**Bước 6 — Giữ điều kiện tương đương.** Cùng CPU/memory limit, heap bounds, data, duration và observability configuration.

**Bước 7 — So sánh kết quả.** Đánh giá SLO, tail latency, CPU, RSS, peak heap và độ ổn định dưới burst.

**Bước 8 — Chọn cấu hình.** Chọn collector đáp ứng SLO với tổng resource hợp lý; ghi rõ version và giới hạn support để lần build sau tái lập.

Tiêu chí hoàn thành: GC option được xác minh trên đúng distribution; benchmark có điều kiện tương đương; kết quả bao gồm latency/throughput/memory và failure; quyết định không dựa riêng vào startup hoặc một lần chạy.

## 20. Kết luận

Garbage collector của GraalVM Native Image phải được lựa chọn theo distribution và version cụ thể. Serial thường là baseline đơn giản; G1 có thể phù hợp heap/workload lớn nếu edition hỗ trợ; Epsilon chỉ dành cho tình huống đặc biệt vì không thu gom object. Không thể suy ra collector khả dụng từ HotSpot flags hoặc từ một GraalVM release khác.

Hãy xác minh native-image --help, pin toolchain, phân biệt build-time GC selection với runtime heap sizing, và đo cả heap, RSS, cgroup memory, pause, throughput cùng tail latency. Một cấu hình GC tốt là cấu hình đáp ứng SLO trong memory budget thực tế của container, với bằng chứng benchmark có thể tái lập.
