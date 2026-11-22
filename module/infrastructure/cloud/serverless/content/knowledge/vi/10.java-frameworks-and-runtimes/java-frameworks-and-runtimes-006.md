# So sánh JVM và native executable cho workload thực tế

Java serverless có thể chạy ứng dụng theo hai cách phổ biến. Cách thứ nhất đóng gói ứng dụng thành JAR và chạy trên JVM. Cách thứ hai biên dịch trước ứng dụng thành native executable, thường bằng GraalVM Native Image, rồi chạy trực tiếp binary trên hệ điều hành đích.

Hai cách đều có thể chạy cùng logic Java, nhưng có đặc tính khác nhau về thời gian khởi động, mức dùng bộ nhớ, thông lượng sau khi chạy ổn định, cách đóng gói và khả năng tương thích thư viện. Không có lựa chọn luôn nhanh hơn hoặc rẻ hơn. Quyết định đúng phải dựa trên workload: function chạy ngắn hay dài, có cold start thường xuyên hay không, lưu lượng ổn định hay tăng giảm đột ngột, và ứng dụng dùng những tính năng Java nào.

## 1. Hai mô hình thực thi

### 1.1. Chạy JAR trên JVM

Ở mô hình JVM, ứng dụng được biên dịch thành Java bytecode. Khi triển khai, một Java runtime khởi chạy process, nạp class, khởi tạo framework và thực thi bytecode.

JVM có thể dùng interpreter để bắt đầu chạy nhanh, sau đó JIT compiler biên dịch những đoạn code được gọi thường xuyên thành mã máy. JVM thu thập thông tin từ workload thực tế để tối ưu các đường chạy nóng (hot paths), inline method và tối ưu theo hành vi quan sát được. Khi ứng dụng chạy đủ lâu, những tối ưu này có thể cải thiện throughput đáng kể.

Ưu điểm quan trọng của mô hình này là khả năng tương thích rộng với hệ sinh thái Java: reflection, class loading động, proxy, JNI, instrumentation, thư viện và công cụ giám sát thường hoạt động theo cách mà ứng dụng Java truyền thống mong đợi.

Đổi lại, một process mới cần khởi tạo JVM, nạp class và framework. JIT cũng cần thời gian để thu thập profile và tối ưu code. Với function chỉ chạy vài trăm mili giây rồi kết thúc, nhiều tối ưu JIT có thể chưa kịp phát huy tác dụng.

### 1.2. Native executable với AOT compilation

Native Image biên dịch ứng dụng Java trước khi triển khai (ahead-of-time, AOT) thành một executable dành cho hệ điều hành và kiến trúc đích. Khi chạy, binary không cần một JVM độc lập để nạp bytecode và JIT compile theo cách thông thường.

Native executable vẫn chứa runtime cần thiết cho các tính năng Java mà nó hỗ trợ, ví dụ quản lý object, garbage collection, exception và thread. Vì vậy, không nên hiểu native executable là mã máy thuần không còn runtime. Điểm khác biệt là phần lớn phân tích khả năng truy cập và biên dịch được thực hiện ở build time.

Native Image thường phân tích reachability từ các entry point đã biết để xác định class, method và resource cần đưa vào binary. Mô hình này thường được gọi là closed-world assumption: những thành phần chỉ được phát hiện động khi chạy có thể không tự động xuất hiện trong executable. Reflection, JNI, resource loading, proxy và service loading có thể cần metadata hoặc cấu hình bổ sung.

Kết quả thường có thời gian khởi động nhanh và không cần giai đoạn JIT warm-up truyền thống. Tuy nhiên, build native có thể lâu hơn, tốn tài nguyên CI và cần xử lý rõ các tính năng động của ứng dụng.

## 2. So sánh tổng quan

| Tiêu chí | JAR chạy trên JVM | Native executable |
|---|---|---|
| Khởi động process | Thường cần khởi tạo JVM, nạp class và framework | Thường nhanh hơn do đã biên dịch trước và runtime gọn theo ứng dụng |
| JIT warm-up | Có; code nóng được tối ưu trong lúc chạy | Không có JIT profiling thông thường trong Native Image truyền thống |
| Throughput sau warm-up | Thường mạnh với workload dài và ổn định nhờ JIT | Có thể thấp hơn hoặc tương đương; phụ thuộc code, workload và cấu hình |
| Bộ nhớ | Có heap, metaspace, thread stack, JIT và native memory | Có heap và native runtime; thường giảm một số overhead nhưng không bảo đảm luôn ít RAM hơn |
| Kích thước triển khai | JAR cộng Java runtime hoặc runtime layer | Binary có thể lớn; không cần cài JVM riêng khi runtime đã được đóng gói phù hợp |
| Build | Thường nhanh và đơn giản | Có thể lâu, nặng CPU/RAM và cần toolchain native |
| Reflection và class loading động | Hỗ trợ rộng | Cần metadata và cấu hình cho những đường truy cập động |
| Debug và profiling | Hệ sinh thái JVM phong phú, quen thuộc | Công cụ và khả năng quan sát phụ thuộc native runtime, build và nền tảng |
| Tính di động | Bytecode có thể chạy trên các JVM tương thích | Binary gắn với OS, CPU architecture và ABI của môi trường build |
| Phù hợp nổi bật | Workload dài, throughput cao, thư viện Java phong phú | Function ngắn, cold start quan trọng, workload burst hoặc scale-to-zero |

Các nhận xét trong bảng là xu hướng thường gặp, không phải cam kết hiệu năng. Native executable có thể chậm hơn JVM trong một workload, và JVM có thể khởi động đủ nhanh cho yêu cầu thực tế nếu framework, runtime và cách triển khai đã được tối ưu.

## 3. Khởi động và cold start

Cold start xảy ra khi nền tảng phải tạo execution environment mới trước khi xử lý invocation. Với Java, tổng thời gian này có thể gồm:

- Khởi tạo container hoặc sandbox.
- Khởi chạy process và runtime.
- Nạp class và thư viện.
- Khởi tạo framework, dependency injection và cấu hình.
- Tạo client, connection pool hoặc cache.
- Thực hiện logic invocation đầu tiên.

Native executable thường rút ngắn phần khởi tạo runtime và nạp class. Điều này có thể hữu ích khi function scale từ 0 lên nhiều instance, hoặc mỗi instance chỉ xử lý một số ít request trước khi bị thu hồi.

Tuy nhiên, native compilation không loại bỏ mọi thành phần của cold start. Container startup, mount file, đọc secret, DNS, TLS handshake, kết nối database và logic khởi tạo của ứng dụng vẫn có thể tốn thời gian. Một ứng dụng native khởi động rất nhanh nhưng mất vài trăm mili giây để kết nối dịch vụ ngoài vẫn có cold start đáng kể.

Cần đo thời gian đến lúc function thực sự sẵn sàng nhận request (ready-to-serve), không chỉ đo thời gian từ lúc bắt đầu process đến khi in dòng log đầu tiên.

### 3.1. JVM cũng có cách giảm cold start

Trước khi chuyển sang native, hãy xem các biện pháp tối ưu JVM phù hợp với nền tảng:

- Giảm số thư viện và class được nạp lúc khởi động.
- Tránh khởi tạo client hoặc cache không cần thiết trong static initializer.
- Dùng lazy initialization cho thành phần chỉ cần ở một số route.
- Tối ưu framework startup và cấu hình dependency injection.
- Dùng Class Data Sharing (CDS) hoặc cơ chế archive class phù hợp nếu runtime hỗ trợ.
- Dùng snapshot/restore của nền tảng hoặc cơ chế CRaC khi có hỗ trợ và khi trạng thái có thể checkpoint an toàn.
- Giữ execution environment ấm nếu mô hình chi phí và tải cho phép.

Các cơ chế snapshot hoặc restore có giới hạn riêng: kết nối socket, credential, thời gian hệ thống và trạng thái bên ngoài có thể cần được làm mới sau restore. Không nên giả định mọi ứng dụng đều an toàn khi snapshot process.

### 3.2. Độ trễ cần đo theo percentile

Một số function có cold start hiếm nhưng rất chậm. Nếu chỉ nhìn average, vấn đề có thể bị che khuất. Hãy đo:

- p50: trải nghiệm phổ biến.
- p95: độ trễ của nhóm request chậm.
- p99: phần đuôi phân phối, quan trọng với SLA nghiêm ngặt.
- Cold-start duration riêng.
- Ready-to-serve duration.
- Duration của invocation đầu tiên và các invocation ấm.

Nếu p95 hoặc p99 chủ yếu do database connection, DNS hoặc dependency ngoài, đổi sang native có thể không giải quyết đúng nút thắt.

## 4. Throughput và hiệu năng sau khi warm-up

JVM JIT có lợi thế khi một process chạy lâu và lặp lại cùng các đường code. Sau khi thu thập profile, JVM có thể tối ưu những method thường xuyên được gọi, phân bổ object và nhánh điều kiện theo hành vi thực tế.

Native Image thực hiện tối ưu chủ yếu tại build time. Nó có thể dùng profile-guided optimization (PGO) để tận dụng profile thu thập từ một workload đại diện trong quá trình build, nhưng không giống việc JVM tiếp tục học profile và JIT tối ưu theo từng execution environment khi chạy.

Với workload CPU-bound kéo dài, JVM sau warm-up thường là lựa chọn mạnh. Với function chạy ngắn, việc chờ JIT warm-up có thể không đáng vì invocation kết thúc trước khi tối ưu có tác dụng. Native có thể có lợi hơn ở trường hợp này.

Một số workload không bị giới hạn bởi runtime Java:

- Gọi API bên ngoài và chờ mạng.
- Đọc/ghi object storage.
- Chờ database hoặc message broker.
- Chờ người dùng hoặc callback.

Với workload I/O-bound, khác biệt giữa JVM và native có thể nhỏ hơn so với thời gian chờ dependency. Hãy đo tổng thời gian xử lý và độ trễ dependency trước khi quyết định.

## 5. Bộ nhớ và khả năng scale

Mức RAM ảnh hưởng đến số instance có thể chạy đồng thời, cấu hình CPU trên một số nền tảng và chi phí function. Native executable thường giảm một số overhead liên quan đến JVM và class metadata, nhưng tổng RSS còn phụ thuộc heap, native allocation, thread, TLS, buffer và thư viện.

Cần phân biệt:

- **Java heap:** object do ứng dụng tạo.
- **Metaspace/class metadata:** dữ liệu class trong JVM.
- **JIT code cache:** mã máy được JIT tạo trong JVM.
- **Thread stack:** vùng stack của từng thread.
- **Native memory:** direct buffer, TLS, thư viện native và runtime.
- **RSS:** lượng bộ nhớ vật lý của process được hệ điều hành ghi nhận.

Native Image không có metaspace và JIT code cache theo mô hình JVM truyền thống, nhưng vẫn dùng heap, stack và native memory. Một native executable có thể có RSS cao nếu ứng dụng giữ nhiều object hoặc dùng thư viện native lớn.

Đừng chỉ so sánh thông số heap tối đa. Hãy đo peak RSS và mức dùng bộ nhớ khi xử lý payload lớn, concurrency cao và workload thực tế. Cũng cần đo thời gian GC pause, allocation rate và số lần invocation bị kết thúc do vượt giới hạn bộ nhớ.

### 5.1. Scale-out và concurrency

Khi nền tảng tăng số instance, mỗi instance có thể tiêu thụ một phần RAM và mở một số connection đến database. Native executable dùng ít RAM hơn trong một số workload có thể cho phép mật độ instance cao hơn, nhưng điều này không tự động có nghĩa database chịu được nhiều connection hơn.

Hãy giới hạn connection pool và concurrency toàn hệ thống. Nếu mỗi function instance mở 10 connection và nền tảng scale lên 100 instance, database có thể nhận đến 1.000 connection. Chuyển sang native không giải quyết được giới hạn đó.

## 6. Tính tương thích Java và framework

Đây là một trong những khác biệt quan trọng nhất khi chọn native executable.

JVM thường hỗ trợ rộng các tính năng dựa trên classpath và runtime discovery. Native Image cần biết trước những thành phần nào có thể được sử dụng. Những tình huống cần chú ý:

- Reflection để tạo object hoặc gọi method theo tên.
- JSON/XML serialization dựa trên reflection.
- Classpath scanning và plugin discovery.
- Dynamic proxy và framework-generated proxy.
- Resource đọc từ classpath.
- JNI và thư viện native.
- ServiceLoader và provider được phát hiện động.
- Instrumentation, agent và công cụ bytecode enhancement.
- Class loading từ module hoặc JAR được tải sau khi process khởi động.

Một số framework đã cung cấp build-time augmentation, AOT processing và metadata để hỗ trợ Native Image. Quarkus và Micronaut được thiết kế với nhiều tối ưu build-time; Spring Boot cũng có hỗ trợ AOT và native image thông qua các phiên bản và plugin tương thích. Mức hỗ trợ cụ thể phụ thuộc phiên bản framework, extension và thư viện đang dùng.

Không nên kết luận “framework hỗ trợ native” nghĩa là mọi thư viện trong ứng dụng đều tương thích. Một extension có thể chạy trên JVM nhưng chưa có metadata hoặc chưa hỗ trợ một tính năng ở native mode.

### 6.1. Reflection và reachability metadata

Ví dụ, ứng dụng tạo object theo tên class:

~~~java
Class<?> type = Class.forName(configuredClassName);
Object handler = type.getDeclaredConstructor().newInstance();
~~~

Trên JVM, class có thể được tìm thấy trong classpath nếu JAR chứa nó. Với Native Image, class và constructor được gọi qua reflection cần được nhận diện trong phân tích build hoặc khai báo metadata phù hợp. Nếu không, runtime có thể báo class hoặc member không khả dụng dù code đã biên dịch thành công.

Cách xử lý:

1. Ưu tiên API và framework integration đã hỗ trợ native.
2. Dùng build-time registration hoặc annotation mà framework cung cấp.
3. Khai báo reflection/resource/JNI metadata theo định dạng Native Image hỗ trợ.
4. Dùng tracing agent trong workload kiểm thử để thu thập một phần cấu hình truy cập động.
5. Kiểm thử native executable bằng các luồng nghiệp vụ thực tế, gồm cả nhánh hiếm.

Tracing agent chỉ ghi nhận những đường code đã được chạy trong lúc thu thập. Nó không thể tự suy ra mọi nhánh có thể xảy ra trong production. Metadata tạo ra từ test cần được rà soát và kiểm thử bổ sung.

### 6.2. Build-time initialization và runtime initialization

Native Image có thể khởi tạo một số class ở build time để giảm công việc lúc chạy. Điều này hữu ích với dữ liệu bất biến, nhưng nguy hiểm nếu static initializer đọc thời gian hiện tại, biến môi trường, secret, random seed, file cấu hình theo môi trường hoặc mở kết nối.

Giá trị được tính tại build time có thể bị đóng gói vào binary và dùng lại ở mọi môi trường. Ví dụ, không nên đưa credential production vào image hoặc tính một giá trị phụ thuộc deployment environment khi build.

Hãy xác định rõ class nào có thể khởi tạo an toàn ở build time và class nào phải chờ runtime. Không ép mọi class sang build-time initialization chỉ để cải thiện startup.

## 7. Đóng gói, triển khai và vận hành

JAR thường có tính di động cao hơn: cùng bytecode có thể chạy trên nhiều hệ điều hành và kiến trúc có JVM tương thích. Native executable được tạo cho một target cụ thể, thường gắn với:

- Hệ điều hành và phiên bản thư viện hệ thống.
- CPU architecture như x86_64 hoặc ARM64.
- ABI và loại libc (ví dụ glibc hoặc musl).
- Các thư viện native được liên kết.
- Phiên bản toolchain và Native Image builder.

Một binary build trên máy phát triển có thể không chạy trong runtime Linux của nền tảng nếu kiến trúc hoặc ABI không khớp. Hãy build trong môi trường tương thích với target deployment, dùng container/build image phù hợp và kiểm tra binary trong môi trường gần production.

Build native có thể tốn nhiều CPU, RAM và thời gian hơn. CI nên cache dependency và toolchain nếu an toàn, nhưng phải tái tạo binary khi thay đổi source, metadata, framework, JDK hoặc cấu hình native. Cần lưu build provenance và phiên bản compiler để có thể tái lập.

### 7.1. Ví dụ cách chạy

Ở mô hình JVM, ứng dụng có thể được chạy như sau:

~~~bash
java -jar target/application.jar
~~~

Ở mô hình native, build tool hoặc framework plugin tạo executable, sau đó chạy binary tương ứng:

~~~bash
./target/application
~~~

Tên file, thư mục và lệnh build phụ thuộc Maven/Gradle plugin, framework và hệ điều hành. Không nên coi một lệnh native chung là đúng cho mọi dự án. Hãy dùng cấu hình build chính thức của framework và target runtime.

Với FaaS, có thể cần custom runtime hoặc adapter để nền tảng gọi executable native. Hãy kiểm tra runtime contract: cách nhận event, đọc input, trả response, xử lý signal, log và khai báo architecture. Một native binary chạy tốt trong container không đồng nghĩa có thể đặt trực tiếp vào mọi Java managed runtime.

## 8. Chi phí serverless: đo tổng chi phí thay vì chỉ nhìn startup

Chi phí phụ thuộc mô hình tính phí của nhà cung cấp. Nền tảng có thể tính theo số request, thời lượng invocation, bộ nhớ cấu hình, CPU, concurrency provisioned, network hoặc dịch vụ phụ trợ.

Native executable có thể giảm duration hoặc cho phép dùng cấu hình memory thấp hơn trong một số trường hợp. Nhưng cũng có thể cần memory cao hơn, build pipeline tốn hơn hoặc tăng thời gian phát triển do phải xử lý compatibility.

Hãy tính cả:

- Chi phí compute cho invocation.
- Chi phí request và các lần retry.
- Chi phí provisioned concurrency hoặc môi trường luôn ấm.
- Chi phí database, queue, object storage và network.
- Chi phí build native và thời gian CI.
- Công sức duy trì metadata, native-specific configuration và kiểm thử.
- Chi phí sự cố nếu một thư viện chỉ lỗi trong native mode.

Một native function chạy nhanh hơn 20% chưa chắc giảm 20% tổng chi phí nếu phần lớn thời gian là chờ database hoặc API ngoài. Ngược lại, với workload gọi rất thường xuyên và cold start chiếm tỷ lệ lớn, giảm startup có thể mang lại lợi ích đáng kể.

## 9. Chọn theo đặc tính workload

| Workload | JVM thường phù hợp khi | Native thường phù hợp khi |
|---|---|---|
| HTTP API có lưu lượng ổn định | Instance sống lâu, JIT warm-up có thời gian phát huy | Startup vẫn là bottleneck và framework/thư viện hỗ trợ tốt |
| HTTP API scale-to-zero | Cold start chấp nhận được hoặc có cơ chế giảm startup | p95/p99 cold start là yêu cầu quan trọng |
| Queue consumer xử lý message ngắn | Consumer chạy liên tục, throughput dài hạn quan trọng | Worker scale theo burst, mỗi instance xử lý ít message |
| Xử lý CPU-bound kéo dài | Cần throughput cao sau warm-up | Workload ngắn, không đủ thời gian hưởng lợi JIT và native đã được benchmark |
| Tác vụ I/O-bound | Tính tương thích và tốc độ phát triển là ưu tiên | Startup hoặc footprint là vấn đề đo được |
| Ứng dụng dùng reflection/plugin rộng | Cần hệ sinh thái runtime động | Có thể thay bằng build-time registration hoặc metadata đã kiểm thử |
| Function rất nhỏ, ít dependency | Cả hai có thể phù hợp; chọn theo benchmark | Có thể đạt startup và footprint tốt nếu build đơn giản |

### 9.1. Ví dụ 1: webhook xử lý ngắn

Một webhook nhận event, xác thực chữ ký, ghi một bản ghi và phát message. Function chạy vài trăm mili giây, có thể scale từ 0 và lưu lượng không đều.

Trong trường hợp này, cold start và footprint có thể ảnh hưởng p95/p99 và chi phí. Native executable đáng được thử nghiệm, đặc biệt nếu framework và thư viện JSON, HTTP, crypto đều hỗ trợ native tốt. Nếu JVM đã đạt SLA sau khi tối ưu startup hoặc nền tảng có snapshot/restore hiệu quả, native có thể không đem lại đủ lợi ích để bù chi phí build và bảo trì.

### 9.2. Ví dụ 2: consumer chạy liên tục

Một consumer đọc message liên tục, mỗi process chạy nhiều giờ và xử lý hàng nghìn message. JVM có thời gian warm-up, JIT có thể tối ưu các đường code lặp lại. Trong trường hợp này, throughput ổn định, GC và khả năng quan sát có thể quan trọng hơn startup. JVM thường là lựa chọn đầu tiên để benchmark.

Native vẫn có thể phù hợp nếu process cần footprint thấp hoặc scale-out nhanh, nhưng cần đo throughput dài hạn và mức dùng CPU/RAM dưới tải thực tế.

### 9.3. Ví dụ 3: function dùng framework và reflection nhiều

Một ứng dụng dùng plugin được nạp theo cấu hình, serializer phát hiện type động và thư viện sử dụng reflection sâu. JVM thường giảm rủi ro tương thích và giúp đội phát triển triển khai nhanh hơn.

Muốn dùng native, cần lập danh sách các tính năng động, xác định metadata, kiểm thử mọi plugin và kiểm tra các đường hiếm. Nếu chi phí chuyển đổi cao hơn lợi ích cold start, tiếp tục dùng JVM là quyết định hợp lý.

## 10. Quy trình benchmark công bằng

Không chọn native chỉ từ một con số startup trong máy phát triển. Hãy benchmark cả cold path, warm path và scale-out.

### 10.1. Giữ điều kiện thử nghiệm tương đương

- Cùng source code và cùng phiên bản dependency.
- Cùng logic nghiệp vụ, payload và dữ liệu đầu vào.
- Cùng region, CPU architecture và giới hạn network.
- Cùng cấu hình memory/CPU nếu nền tảng cho phép so sánh trực tiếp.
- Cùng giới hạn concurrency và chính sách retry.
- Cùng dependency phía sau, hoặc đo riêng phần dependency.
- Build release/production mode cho cả hai phương án.

Nếu native dùng một phiên bản framework hoặc thư viện khác với JVM, kết quả không còn chỉ phản ánh khác biệt runtime. Ghi lại mọi khác biệt trong báo cáo.

### 10.2. Đo nhiều loại workload

Chạy ít nhất các nhóm sau:

1. Cold start đơn lẻ, không có request trước đó.
2. Warm invocation liên tục trên cùng execution environment.
3. Burst tăng nhanh từ ít lên nhiều invocation.
4. Concurrency cao để đo scale-out và connection pressure.
5. Payload nhỏ và payload lớn.
6. Workload CPU-bound và I/O-bound nếu ứng dụng có cả hai.
7. Dependency chậm hoặc lỗi tạm thời để quan sát timeout/retry.

Không chỉ đo một lần. Chạy đủ mẫu để percentile có ý nghĩa và tách riêng thời gian khởi tạo khỏi thời gian nghiệp vụ.

### 10.3. Metric cần so sánh

| Nhóm | Metric |
|---|---|
| Startup | Time to ready, cold-start duration, init duration |
| Latency | p50, p95, p99 của invocation |
| Throughput | Request/message mỗi giây và thời gian xử lý ổn định |
| Memory | Peak RSS, heap, native memory, allocation rate |
| CPU | CPU time, utilization và thời gian GC |
| Reliability | Error rate, timeout, crash, retry và throttling |
| Scale | Thời gian tăng instance, concurrency đạt được, số connection |
| Cost | Chi phí compute, request, dependency và build pipeline |

Dùng cùng cách đo cho cả hai. Ví dụ, nếu JVM metric chỉ báo heap còn native metric báo RSS, so sánh đó không công bằng. Cần thu thập cùng chỉ số ở tầng process và bổ sung metric runtime để giải thích khác biệt.

## 11. Những lỗi thường gặp khi chuyển sang native

- **Ứng dụng chạy được khi build nhưng lỗi reflection lúc runtime:** bổ sung metadata hoặc dùng framework integration đúng phiên bản.
- **Resource không được đóng gói:** khai báo resource cần thiết và kiểm tra file trong binary.
- **ServiceLoader không tìm thấy provider:** kiểm tra service metadata và cấu hình reachability.
- **JNI hoặc thư viện native không tương thích:** xác minh architecture, ABI và thư viện được liên kết.
- **Giá trị static phụ thuộc môi trường bị cố định khi build:** chuyển khởi tạo sang runtime.
- **Build quá nặng trong CI:** chọn build image phù hợp, phân bổ tài nguyên và tối ưu cache.
- **Binary không chạy trên môi trường đích:** build cho đúng OS/architecture/libc và test trong image triển khai.
- **Hiệu năng warm thấp hơn JVM:** benchmark PGO, cấu hình GC và cấu trúc workload; cân nhắc quay lại JVM nếu throughput quan trọng hơn startup.
- **Metric bộ nhớ gây hiểu nhầm:** so sánh RSS với RSS và kiểm tra cả heap lẫn native allocation.

Đừng chỉ chạy smoke test một endpoint. Một ứng dụng có thể khởi động native thành công nhưng lỗi ở route chỉ được gọi khi có một loại event đặc biệt hoặc khi serializer gặp một subtype hiếm. Kiểm thử phải bao phủ những đường nghiệp vụ thực tế.

## 12. Checklist ra quyết định

Trước khi chọn runtime cho một Java function, hãy trả lời:

1. Function có thường xuyên cold start hoặc scale từ 0 không?
2. SLA có yêu cầu nghiêm ngặt về p95/p99 startup không?
3. Mỗi execution environment sống bao lâu và xử lý bao nhiêu request/message?
4. Workload CPU-bound hay chủ yếu chờ I/O?
5. Throughput sau warm-up có quan trọng hơn startup không?
6. Ứng dụng dùng reflection, dynamic proxy, JNI hoặc plugin không?
7. Framework và tất cả extension có hỗ trợ native ở phiên bản đang dùng không?
8. Native binary có tương thích OS, architecture và ABI của nền tảng không?
9. CI có đủ tài nguyên và thời gian để build, kiểm thử native không?
10. Mức giảm latency/RAM có tạo ra tiết kiệm chi phí đo được không?
11. Đội ngũ có thể duy trì metadata và test riêng cho native không?
12. JVM có thể đáp ứng mục tiêu bằng startup tuning, snapshot hoặc cấu hình nền tảng không?

Một quyết định thực tế thường bắt đầu bằng JVM vì đường triển khai đơn giản và tương thích rộng. Sau đó, benchmark native trên đúng function có cold start hoặc memory là bottleneck. Nếu native cải thiện metric quan trọng mà không làm tăng rủi ro tương thích và vận hành quá mức, có thể chọn native cho function đó. Không cần buộc toàn bộ hệ thống dùng chung một runtime; từng function có thể có lựa chọn phù hợp với workload của nó.

## 13. Câu hỏi tự kiểm tra

- JVM JIT tối ưu code dựa trên thông tin nào khi ứng dụng chạy?
- Native Image khác JAR chạy trên JVM ở bước nào của vòng đời?
- Vì sao native executable vẫn cần runtime và garbage collector?
- Closed-world assumption ảnh hưởng reflection và resource loading như thế nào?
- Khi nào JVM warm-up là lợi thế thay vì chi phí?
- Vì sao native không chắc chắn có throughput cao hơn JVM?
- Vì sao phải đo peak RSS thay vì chỉ so sánh Java heap?
- Những khác biệt nào về OS, architecture và ABI ảnh hưởng native binary?
- Vì sao cần kiểm thử các nhánh reflection và plugin trong native mode?
- Những metric nào giúp quyết định native có giảm chi phí serverless thật sự không?

JVM và native executable là hai cách triển khai Java với các đánh đổi khác nhau. Hãy chọn dựa trên thời gian sống của function, tỷ lệ cold start, throughput, bộ nhớ, tính tương thích và chi phí vận hành. Benchmark trên workload thực tế mới cho biết phương án nào đáp ứng SLA và ngân sách tốt hơn.

