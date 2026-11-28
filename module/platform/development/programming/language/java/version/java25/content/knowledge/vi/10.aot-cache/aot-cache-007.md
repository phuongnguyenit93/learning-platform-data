# Phân biệt dữ liệu được lưu trong cache với trạng thái ứng dụng lúc chạy

Một ứng dụng Java có thể mất thời gian ở giai đoạn khởi động vì JVM phải nạp và liên kết class, khởi tạo cấu trúc cần thiết, dựng framework và thu thập profile để JIT tối ưu các method nóng. **Ahead-of-Time (AOT) cache** của HotSpot giúp tái sử dụng một số kết quả tối ưu hóa từ lần chạy huấn luyện trước để giảm chi phí startup và warmup ở những lần chạy sau.

Điều quan trọng là hiểu chính xác cache lưu gì. **AOT cache không phải bản sao đầy đủ của tiến trình đã chạy và không khôi phục trạng thái nghiệp vụ đang sống.** Nó chứa các artifact JVM được chọn, chẳng hạn dữ liệu class, một số heap objects đủ điều kiện archive và, với các cải tiến Java 25, dữ liệu profile thực thi method. Mỗi lần khởi động production vẫn tạo một JVM mới, dựng trạng thái ứng dụng mới, mở kết nối mới và nạp dữ liệu nghiệp vụ từ các nguồn có thẩm quyền.

Bài thuộc chương **AOT cache** của module **JAVA_VERSION_JAVA25**. Nội dung tập trung vào việc phân biệt **artifact tối ưu hóa được lưu trong cache** với **trạng thái ứng dụng lúc chạy**, cách training/assembly/production hoạt động, cách áp dụng cho Java thuần và Spring Boot, cũng như cách xác minh hiệu quả mà không hiểu nhầm cache là database, session store hay snapshot của heap.

> **Phạm vi hiện hành:** AOT cache được giới thiệu trong JDK 24 qua JEP 483. Java 25 bổ sung cải tiến về command-line ergonomics (JEP 514) và method profiling (JEP 515). Với Java 25 trở lên, tài liệu Spring khuyến nghị AOT cache khi có thể sử dụng; bài không lấy quy trình CDS cũ làm hướng dẫn chính.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích AOT cache là gì và mục tiêu chính là giảm startup/warmup của JVM.
2. Phân biệt class metadata, archived heap objects và method execution profiles với dữ liệu nghiệp vụ của một phiên chạy.
3. Giải thích vì sao AOT cache không khôi phục session, transaction, request đang xử lý, connection pool hoặc trạng thái mutable của process.
4. Phân biệt AOT cache của JVM với Spring AOT processing, CDS và native image.
5. Mô tả ba pha training, assembly và production; hiểu thay đổi Java 25 trong JEP 514.
6. Tạo cache bằng tùy chọn JVM AOTCacheOutput và sử dụng bằng AOTCache.
7. Chọn workload huấn luyện phù hợp để method profiles phản ánh cách ứng dụng được sử dụng.
8. Hiểu vì sao spring.context.exit=onRefresh phù hợp với mục tiêu startup cache nhưng không đại diện cho business workflow.
9. Xác minh cache được nạp, kiểm tính tương thích và đo hiệu quả bằng benchmark.
10. Thiết kế pipeline tạo lại cache khi artifact, JDK, hệ điều hành hoặc kiến trúc CPU thay đổi.

## 2. AOT cache là gì?

AOT cache là một **container artifact do JVM tạo trước để tái sử dụng ở lần chạy sau**. Nó giúp JVM giảm một phần công việc phải lặp lại khi khởi động cùng ứng dụng. Tùy phiên bản JDK và các tối ưu được bật, cache có thể chứa:

- **Class-related artifacts:** dữ liệu class đã được JVM xử lý để hỗ trợ nạp/liên kết nhanh hơn.
- **Một số heap objects được archive:** các object được JVM lựa chọn và lưu theo quy tắc của AOT cache.
- **Method execution profiles trong Java 25+:** dữ liệu thống kê thu được từ lần chạy huấn luyện, để JIT có thông tin về hành vi method sớm hơn khi JVM khởi động lần sau.

Đây là những **artifact tối ưu hóa**, không phải toàn bộ trạng thái của chương trình.

~~~mermaid
flowchart TD
    A["Training run<br/>Chạy ứng dụng với workload"] --> B["AOT artifacts"]
    B --> C["Class data / metadata"]
    B --> D["Archived heap objects<br/>được JVM lựa chọn"]
    B --> E["Method profiles<br/>Java 25+"]
    C --> F["AOT cache (.aot)"]
    D --> F
    E --> F
    F --> G["JVM mới khởi động"]
    G --> H["Nạp artifact phù hợp"]
    H --> I["Ứng dụng dựng runtime state mới"]
    I --> J["Nhận request và xử lý nghiệp vụ"]
~~~

### 2.1. AOT cache không phải snapshot của process

Một snapshot tiến trình theo nghĩa thông thường có thể khiến người đọc nghĩ rằng toàn bộ heap, thread, file descriptor, socket, transaction và dữ liệu đang xử lý sẽ được khôi phục. **Không nên hiểu AOT cache theo cách đó.**

AOT cache không hứa hẹn khôi phục:

- HTTP request đang được xử lý tại thời điểm training kết thúc.
- Session đăng nhập của người dùng.
- Transaction đang mở hoặc trạng thái transaction manager.
- Kết nối JDBC, socket, HTTP client, message broker hay connection pool đang hoạt động.
- Thread đang chạy, stack frame hoặc lịch thực thi của process.
- Cache nghiệp vụ mutable trong heap, chẳng hạn giỏ hàng hoặc dữ liệu người dùng vừa đọc.
- Dữ liệu mới nhất trong database, Redis, Kafka hoặc hệ thống bên ngoài.
- Token, secret hoặc credential của một phiên chạy production.

Các thành phần này phải được khởi tạo hoặc nạp lại theo quy trình ứng dụng trong **mỗi lần khởi động mới**.

### 2.2. Heap objects được archive không có nghĩa là toàn bộ heap được lưu

JVM có thể đưa một số object đủ điều kiện vào archive để tái sử dụng. Điều này không đồng nghĩa mọi object tồn tại trong heap ở training run đều được ghi vào cache.

Cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Archived heap objects | Một tập object được JVM lựa chọn để phục vụ tối ưu khởi động |
| Live application heap | Các object thực sự tồn tại trong heap của một JVM đang chạy |
| Business state | Dữ liệu nghiệp vụ như đơn hàng, giỏ hàng, phiên đăng nhập, trạng thái workflow |
| Persistent state | Dữ liệu được lưu ở database, object storage, message log hoặc hệ thống lưu trữ khác |

Ví dụ, việc một framework tạo object trong lúc training không có nghĩa toàn bộ Spring ApplicationContext, mọi singleton bean và mọi trạng thái runtime được đóng gói thành một context sẵn sàng phục vụ request trong cache. Cache có thể hỗ trợ JVM xử lý một số artifact nhanh hơn; ứng dụng vẫn phải thực hiện startup/lifecycle theo thiết kế của nó.

## 3. Ba nhóm dữ liệu: cache, profile và trạng thái runtime

Để tránh nhầm lẫn, hãy phân loại thông tin theo mục đích và thời điểm tồn tại.

| Nhóm | Ví dụ | Có thể nằm trong AOT cache? | Được tạo/nạp khi nào? |
|---|---|---|---|
| Class data/metadata | Class đã được load/link, thông tin phục vụ JVM | Có, theo phạm vi JVM hỗ trợ | Training/assembly, dùng lại lúc JVM mới khởi động |
| Archived heap objects | Một số object đủ điều kiện archive | Có, theo quy tắc của JVM | Tạo trong training, dùng lại từ cache |
| Method profiles | Thống kê hành vi thực thi method từ workload trước | Java 25 bổ sung hỗ trợ qua AOT method profiling | Thu trong training, cung cấp sớm cho JIT ở lần chạy sau |
| Cấu hình triển khai | Environment variables, JVM flags, config map | Không nên xem là business state được cache | Đọc từ môi trường ở mỗi lần chạy |
| Trạng thái Spring runtime | Bean lifecycle, connection pool, scheduled tasks | Không phải snapshot đầy đủ được phục hồi | Dựng trong startup của JVM mới |
| Trạng thái request | Request ID, authentication context, transaction | Không | Tạo cho từng request |
| Dữ liệu nghiệp vụ | Đơn hàng, tài khoản, tồn kho | Không | Đọc/ghi qua nguồn dữ liệu nghiệp vụ |
| Cache nghiệp vụ | Kết quả truy vấn Redis, local cache có TTL | Không phải AOT cache | Nạp lại hoặc tái tạo theo chính sách ứng dụng |
| Trạng thái thread/process | Thread stack, socket, file handle | Không phải mục tiêu của AOT cache | Tạo trong mỗi process |

**Điểm cần nhớ:** method profile là dữ liệu thống kê về hành vi chương trình, không phải dữ liệu người dùng. Profile có thể cho JVM biết method nào thường được gọi hoặc đường thực thi nào phổ biến; nó không chứa kết quả nghiệp vụ mà method đã trả về cho một người dùng cụ thể.

## 4. AOT cache khác Spring AOT, CDS và native image

Từ “AOT” được dùng trong nhiều công nghệ Java, nhưng chúng giải quyết các vấn đề khác nhau.

| Công nghệ | Thời điểm chính | Kết quả | Vai trò |
|---|---|---|---|
| **JVM AOT cache** | Training run trước deployment hoặc trong pipeline | File cache .aot | Tái sử dụng artifact JVM để cải thiện startup/warmup |
| **Spring AOT processing** | Build time | Code/configuration được sinh cho ứng dụng Spring | Chuẩn bị một số cấu trúc framework trước khi chạy |
| **Class Data Sharing (CDS)** | Tạo archive và runtime | Archive class data | Tiền thân của AOT cache; với Java 25+ nên ưu tiên AOT cache khi được hỗ trợ |
| **GraalVM Native Image** | Build time | Executable native binary | Tạo ứng dụng native, với mô hình build/runtime và giới hạn khác JVM truyền thống |

**Spring AOT không phải JVM AOT cache.** Spring AOT processing có thể sinh code phục vụ khởi tạo Spring. JVM AOT cache lại được tạo từ một training run của JVM và được bật bằng JVM option. Hai kỹ thuật có thể phối hợp nếu phiên bản/framework và cách đóng gói hỗ trợ.

**Native Image cũng không phải file .aot.** Một ứng dụng native image không chạy theo cùng quy trình khởi động JVM và không sử dụng AOT cache HotSpot như một JVM process thông thường.

Với Java 25, tài liệu Spring Boot khuyến nghị dùng AOT cache thay CDS khi có thể. Vì vậy, phần thực hành dưới đây dùng AOTCacheOutput và AOTCache, không lấy các lệnh tạo archive CDS cũ làm quy trình chính.

## 5. Training, assembly và production

AOT cache có ba pha khái niệm:

1. **Training:** chạy ứng dụng để JVM quan sát class loading/linking và thu thập thông tin phù hợp từ workload.
2. **Assembly:** JVM tạo file cache từ các artifact và dữ liệu đã thu thập.
3. **Production:** một JVM mới nạp cache để giảm một phần chi phí startup/warmup.

~~~mermaid
sequenceDiagram
    participant CI as Build / CI
    participant T as Training JVM
    participant A as AOT Assembly
    participant P as Production JVM
    participant DB as Database

    CI->>T: Chạy artifact + workload đại diện
    T->>T: Load classes, khởi tạo và thu profile
    T-->>A: Kết thúc training
    A->>A: Tạo app.aot
    CI->>P: Triển khai artifact + app.aot
    P->>P: Nạp AOT cache
    P->>DB: Mở kết nối mới
    P->>P: Dựng runtime state mới
    P-->>CI: Readiness / phục vụ request
~~~

### 5.1. Java 25 và JEP 514

**JEP 514 — Ahead-of-Time Command-Line Ergonomics** đơn giản hóa việc tạo AOT cache cho trường hợp phổ biến. Trong JDK 25, có thể dùng:

~~~bash
java -XX:AOTCacheOutput=app.aot -cp app.jar com.example.Main
~~~

Khi ứng dụng kết thúc training run, JVM thực hiện bước assembly để tạo cache. Người vận hành không cần luôn tự chia nhỏ các bước record/create cho trường hợp thông thường.

Một số chế độ AOT vẫn tồn tại cho nhu cầu điều khiển cụ thể:

| Option | Ý nghĩa |
|---|---|
| AOTCacheOutput=app.aot | Ghi training và tạo cache output |
| AOTCache=app.aot | Nạp cache khi chạy ứng dụng |
| AOTMode=auto | Chế độ mặc định; JVM tự chọn theo cache output hoặc cache có thể nạp |
| AOTMode=off | Không sử dụng AOT cache |
| AOTMode=record | Chạy pha training rõ ràng |
| AOTMode=create | Tạo cache từ AOT configuration đã ghi |
| AOTMode=on | Yêu cầu nạp cache và fail-fast nếu không thể nạp; phù hợp kiểm tra tương thích hơn là mặc định production |

Với production, chế độ auto thường có tính chịu lỗi tốt hơn: nếu cache không tương thích, JVM có thể tiếp tục chạy mà không dùng cache. Điều này bảo vệ khả năng khởi động của ứng dụng, dù lợi ích tối ưu hóa không còn.

### 5.2. Java 25 và JEP 515: method profiles

**JEP 515 — Ahead-of-Time Method Profiling** làm cho method execution profiles từ lần chạy trước có sẵn sớm hơn khi HotSpot JVM khởi động. JIT có thể sử dụng dữ liệu profile đó để bắt đầu tối ưu method sớm, thay vì phải chờ thu thập toàn bộ profile trong lần chạy hiện tại.

Điều này tạo ra một khác biệt quan trọng:

- Class data giúp JVM xử lý một số công việc liên quan class nhanh hơn.
- Archived heap objects giúp tái sử dụng các object được chọn.
- Method profiles giúp JIT hiểu hành vi thực thi đã quan sát trong training.

Profile là **bằng chứng thống kê của workload huấn luyện**, không phải một bản sao kết quả chạy. Nếu workload training không đại diện cho production, profile có thể không giúp ích hoặc không phản ánh đúng đường chạy phổ biến sau triển khai.

## 6. Chọn workload training: startup-only hay production-like?

Đây là quyết định ảnh hưởng trực tiếp tới loại artifact và lợi ích mong đợi.

### 6.1. Training chỉ tới lúc application context refresh

Với Spring Boot, có thể dùng:

~~~bash
java -Djarmode=tools -jar my-app.jar extract --destination application
cd application
java -XX:AOTCacheOutput=app.aot -Dspring.context.exit=onRefresh -jar my-app.jar
~~~

Sau khi Spring ApplicationContext được refresh, process sẽ thoát. Ở thời điểm này, các singleton không lazy đã được khởi tạo và callback InitializingBean đã chạy; lifecycle chưa bắt đầu và ContextRefreshedEvent chưa được phát.

Cách này phù hợp khi mục tiêu chính là **tối ưu giai đoạn khởi động và khởi tạo framework**. Tuy nhiên, nó không tạo ra một business workflow đại diện. Những method chỉ được gọi khi có request thực tế có thể chưa được thực thi trong training.

### 6.2. Training có workload gần production

Nếu muốn tận dụng method profiles của Java 25, hãy chạy ứng dụng qua một phần workload đại diện:

1. Khởi động ứng dụng trong chế độ training với AOTCacheOutput=app.aot.
2. Chạy synthetic requests hoặc integration workload có kiểm soát.
3. Bao phủ các luồng phổ biến: đọc dữ liệu, validation, mapping, serialization, truy cập repository và các method thực sự quan trọng.
4. Dừng training process một cách có kiểm soát để hoàn tất việc tạo cache.
5. Dùng cache trên đúng artifact/JDK/platform đã tạo nó.

Không cần chạy toàn bộ production traffic. Cần workload đại diện cho những luồng thường xuyên và quan trọng.

**Không dùng dữ liệu production nhạy cảm chỉ để tạo profile.** Hãy dùng test data đã ẩn danh, môi trường cô lập, mock hoặc sandbox cho các side effects.

### 6.3. So sánh hai cách training

| Tiêu chí | spring.context.exit=onRefresh | Workload production-like |
|---|---|---|
| Mục tiêu chính | Tối ưu startup/context initialization | Startup và method profiling |
| Application context | Dừng sau refresh | Có thể tiếp tục xử lý request |
| Business methods | Có thể chưa được gọi | Được gọi theo workload |
| Method profiles | Có thể ít dữ liệu hữu ích | Có thể phản ánh luồng thực tế hơn |
| Thời gian training | Ngắn hơn | Dài hơn |
| Rủi ro side effects | Thấp hơn nếu startup được kiểm soát | Cần kiểm soát dữ liệu và tác vụ ghi |
| Khi phù hợp | Ứng dụng chủ yếu cần giảm startup cost | Ứng dụng có warmup/method hot paths đáng kể |

Không có một cách training tốt nhất cho mọi ứng dụng. Chọn theo SLO và workload thật, rồi đo hiệu quả.

## 7. Ví dụ Java thuần: tạo và sử dụng AOT cache

Giả sử ứng dụng đã được đóng gói thành app.jar và entry point là com.example.Main.

### 7.1. Training và tạo cache

~~~bash
java -XX:AOTCacheOutput=app.aot -cp app.jar com.example.Main
~~~

Ứng dụng phải thực thi workload mà bạn muốn JVM quan sát rồi kết thúc. Nếu chương trình chỉ in một dòng rồi thoát, cache có thể vẫn được tạo, nhưng method profile sẽ không đại diện cho một ứng dụng có nhiều luồng nghiệp vụ.

### 7.2. Production sử dụng cache

~~~bash
java -XX:AOTCache=app.aot -cp app.jar com.example.Main
~~~

Ứng dụng được khởi chạy trong JVM mới. JVM nạp cache nếu tương thích, sau đó tiếp tục khởi tạo runtime state bình thường.

### 7.3. Điều gì xảy ra với trạng thái runtime?

Giả sử Main tạo một object lưu số request đã xử lý:

~~~java
public class RequestCounter {
    private long count;

    public void increment() {
        count++;
    }

    public long value() {
        return count;
    }
}
~~~

Training run xử lý 100 request giả lập và kết thúc. Production run không tự động bắt đầu với count bằng 100. Một JVM mới khởi tạo object và trạng thái của nó theo logic ứng dụng. Nếu số liệu request cần được giữ qua restart, phải lưu ở database hoặc hệ thống lưu trữ phù hợp.

Đây là ví dụ trực quan để phân biệt **profile của cách chương trình thực thi** với **giá trị nghiệp vụ đã được chương trình tạo ra**.

## 8. Ví dụ Spring Boot: cache startup và runtime state mới

Spring Boot có thể tạo AOT cache trên ứng dụng đã extract. Cách này giúp classpath và layout JAR phù hợp hơn với yêu cầu của AOT cache.

### 8.1. Extract executable JAR

~~~bash
java -Djarmode=tools -jar my-app.jar extract --destination application
cd application
~~~

Dùng phiên bản Spring Boot có hỗ trợ JAR tools mode và AOT cache. Với ứng dụng đã extract, production cũng phải chạy từ layout được tạo tương ứng.

### 8.2. Tạo cache cho startup

~~~bash
java -XX:AOTCacheOutput=app.aot -Dspring.context.exit=onRefresh -jar my-app.jar
~~~

Đây là cách đơn giản để ghi nhận startup path và thoát sau khi context refresh. File app.aot có thể được đóng gói cùng deployment artifact tương ứng.

### 8.3. Chạy ứng dụng với cache

~~~bash
java -XX:AOTCache=app.aot -jar my-app.jar
~~~

Ứng dụng vẫn cần:

- Đọc cấu hình runtime từ environment/configuration provider.
- Kết nối database và message broker.
- Tạo connection pools và các client runtime.
- Dựng bean lifecycle, scheduled tasks và listener.
- Nạp dữ liệu nghiệp vụ theo repository/service.
- Khởi tạo cache ứng dụng theo chính sách riêng.

AOT cache có thể giảm chi phí JVM startup; nó không thay thế các bước này.

### 8.4. Nếu cần method profiles cho Spring Boot

Với Java 25+, Spring Framework lưu ý AOT cache có thể chứa method profiling information. Nếu muốn tận dụng JEP 515, training cần thực thi một phần workload gần production. Khi đó, không dùng spring.context.exit=onRefresh để dừng ngay sau refresh.

Một quy trình tổng quát:

~~~bash
# Chạy từ thư mục application đã extract.
java -XX:AOTCacheOutput=app.aot -jar my-app.jar
~~~

Trong lúc process training còn chạy, gửi synthetic traffic qua các luồng nghiệp vụ đại diện. Sau đó dừng process bằng cơ chế graceful shutdown đã cấu hình để JVM hoàn tất training/assembly. Không dùng dữ liệu thật hoặc để training run gửi email, thanh toán, tạo đơn hàng hay phát message ra hệ thống production.

**Chú ý:** cấu hình trên chỉ là khung quy trình. Cách kích hoạt workload và graceful shutdown phải phù hợp ứng dụng, Spring Boot version, container orchestration và các side effects của service.

## 9. Dữ liệu nào vẫn phải tạo mới khi khởi động?

Một hệ thống Spring Boot điển hình có thể có các loại trạng thái sau:

| Thành phần | Lần khởi động mới phải làm gì? | AOT cache có thay thế không? |
|---|---|---|
| Class metadata | Nạp từ cache khi tương thích hoặc xử lý phần còn thiếu | Có thể hỗ trợ một phần |
| Bean definitions/khởi tạo Spring | Dựng application context theo cấu hình hiện tại | Không thay thế đầy đủ |
| Database pool | Mở kết nối mới | Không |
| HTTP client/socket | Tạo client và kết nối theo runtime | Không |
| Redis local cache | Nạp lại hoặc để cache miss rồi lấy dữ liệu | Không |
| Session store | Đọc từ session store nếu kiến trúc có persistence | Không |
| Transaction | Tạo transaction cho operation mới | Không |
| Request context | Tạo từ request hiện tại | Không |
| Authentication principal | Xác thực lại theo security flow | Không |
| Feature flags/config | Đọc từ nguồn cấu hình hiện tại | Không |
| Method profiles | Có thể nạp từ training profile | Có, trong phạm vi JVM hỗ trợ |
| Dữ liệu đơn hàng | Đọc từ database hoặc hệ thống nghiệp vụ | Không |

Một ví dụ: cache chứa profile cho method OrderService.calculateTotal() được gọi nhiều trong training. Khi production khởi động, JVM có thể tận dụng profile để tối ưu method này sớm hơn. Nhưng danh sách đơn hàng của khách hàng vẫn phải được truy vấn từ nguồn dữ liệu nghiệp vụ.

## 10. Cache và tính nhất quán của trạng thái ứng dụng

AOT cache phải được xem là **artifact gắn với một build/deployment**, không phải nơi chứa state có thể cập nhật theo request.

### 10.1. Thay đổi cấu hình runtime

Giả sử ứng dụng có hai môi trường:

- Staging dùng endpoint database thử nghiệm.
- Production dùng endpoint database thật.

AOT cache không được dùng như nơi lưu endpoint hay credential. Mỗi process đọc cấu hình tương ứng từ environment hoặc secret manager. Nếu một object được archive có thể chứa thông tin phụ thuộc môi trường, cần kiểm tra khả năng tương thích và thiết kế training để không đưa dữ liệu nhạy cảm vào artifact.

### 10.2. Thay đổi dữ liệu database sau training

Training run có thể đọc dữ liệu mẫu. Khi production chạy, database có thể đã có dữ liệu mới. AOT cache không giữ bản snapshot database và không được dùng để trả dữ liệu cũ thay cho repository.

### 10.3. Trạng thái singleton trong Spring

Spring singleton bean được tạo trong ApplicationContext của một process. AOT cache không hứa hẹn khôi phục toàn bộ object graph singleton với các trạng thái mutable của training. Các bean và dependency phải được dựng theo lifecycle của JVM mới. Nếu singleton chứa state nghiệp vụ, hãy xem lại thiết kế stateless hoặc chuyển state sang nơi lưu trữ phù hợp.

### 10.4. Method profile cũ không phải kết quả cũ

Method profiles là thông tin thống kê, không phải kết quả trả về từ method. Nếu một method trước đây xử lý dữ liệu A và hiện tại xử lý dữ liệu B, profile cũ không làm JVM trả lại kết quả A. Tuy nhiên, workload thay đổi đáng kể có thể khiến profile kém đại diện, ảnh hưởng chất lượng tối ưu JIT; hãy huấn luyện lại theo workload mới khi cần.

## 11. Tính tương thích và vòng đời AOT cache

AOT cache phụ thuộc vào môi trường tạo cache. Theo tài liệu JDK và Spring Framework, cần chú ý:

- **Application artifact/classpath:** cache gắn với ứng dụng và cách classpath/module path được thiết lập.
- **JDK release/build:** thay đổi JDK có thể làm cache không tương thích.
- **OS và CPU architecture:** cache được tạo cho nền tảng cụ thể.
- **JVM/JDK build và classpath:** dùng cùng JVM implementation/build; classpath nên được biểu diễn bằng JAR hoặc danh sách JAR, tránh directory và wildcard trong phần classpath được cache.
- **JAR files và thứ tự classpath:** khi dùng Spring Boot extracted layout, giữ nguyên các JAR, timestamp và thứ tự classpath giữa training và production. Nếu bổ sung thư viện hoặc directory ở cuối classpath, phần thêm đó không được cache.
- **JAR timestamps:** không làm thay đổi timestamp theo cách phá tính tương thích.
- **JVM options và agents:** một số option/agent can thiệp class loading có thể làm cache không sử dụng được.

### 11.1. Khi nào phải tạo lại cache?

| Thay đổi | Hành động |
|---|---|
| Build JAR mới hoặc thay dependency | Tạo cache mới |
| Thay version/build JDK | Tạo cache mới |
| Đổi OS image hoặc CPU architecture | Tạo cache mới |
| Thay layout/extracted classpath | Tạo cache mới và kiểm lại |
| Thay JVM options ảnh hưởng compatibility | Xác minh; tạo lại nếu cần |
| Thay dữ liệu nghiệp vụ trong database | Không cần tạo cache mới chỉ vì dữ liệu thay đổi |
| Thay user session/request | Không cần tạo cache mới |
| Thay cấu hình runtime thông thường | Đọc cấu hình ở runtime; đánh giá riêng nếu nó làm thay đổi artifact/classpath hoặc object được archive |

Không tái sử dụng cache của bản build trước chỉ vì tên file vẫn là app.aot. Tên file không chứng minh cache còn tương thích với artifact hiện tại.

### 11.2. Cache không tương thích thì sao?

Với AOTMode=auto, JVM có thể bỏ qua cache không tương thích và tiếp tục chạy mà không hưởng tối ưu. Với chế độ yêu cầu nạp cache nghiêm ngặt, JVM có thể báo lỗi và dừng.

Trong production, cần bảo đảm ứng dụng vẫn khởi động đúng nếu cache không được dùng. Cache là tối ưu hiệu năng; correctness nghiệp vụ không được phụ thuộc vào việc cache nạp thành công.

## 12. Kiểm tra cache có được sử dụng hay không

Không nên suy luận chỉ từ việc file .aot tồn tại. Cần kiểm tra log và phép đo.

### 12.1. Bật log AOT

~~~bash
java -XX:AOTCache=app.aot -XX:AOTMode=auto -Xlog:aot -jar my-app.jar
~~~

Đọc log để biết JVM có nạp cache, bỏ qua cache hoặc phát hiện mismatch. Nếu cache không được dùng, kiểm tra nguyên nhân trong log thay vì mặc định cho rằng ứng dụng đang được tối ưu.

### 12.2. Kiểm tra class loading

Có thể ghi log class loading:

~~~bash
java -XX:AOTCache=app.aot -Xlog:class+load:file=class-load.log -jar my-app.jar
~~~

Các class được nạp từ cache có thể xuất hiện với nguồn như shared objects file. Đây là một dấu hiệu xác minh, không phải bằng chứng rằng toàn bộ ứng dụng đã được cache.

### 12.3. Đối chiếu ba nguồn

| Nguồn | Câu hỏi |
|---|---|
| File .aot và metadata build | Cache được tạo cho artifact/JDK/platform nào? |
| JVM logs (-Xlog:aot, class loading) | JVM có nạp cache và dùng artifact không? |
| Metrics/startup benchmark | Cache có tạo lợi ích đo được không? |

Nếu file cache tồn tại nhưng JVM bỏ qua do mismatch, kích thước file không nói lên hiệu quả. Nếu JVM nạp cache nhưng startup không cải thiện, có thể chi phí chính nằm ở network, database, remote config hoặc initialization logic của ứng dụng.

## 13. Benchmark: đo hiệu quả mà không nhầm với trạng thái ứng dụng

Một benchmark có ích cần so sánh **cùng artifact, cùng workload và cùng điều kiện runtime**.

### 13.1. Các chỉ số nên đo

| Chỉ số | Ý nghĩa |
|---|---|
| Process startup time | Từ lúc khởi chạy process đến mốc đo được chọn |
| Application readiness | Thời điểm service thực sự sẵn sàng nhận traffic |
| Time to first request | Thời gian xử lý request đầu tiên |
| Warmup throughput | Throughput trong giai đoạn đầu |
| Steady-state throughput | Throughput sau khi hệ thống ổn định |
| P95/P99 latency | Tail latency trước/sau warmup |
| RSS/heap | Footprint bộ nhớ |
| Training duration | Chi phí tạo cache |
| Cache artifact size | Dung lượng phải đóng gói và phân phối |

### 13.2. Thiết kế phép so sánh

Chạy nhiều lần theo cùng quy trình:

1. Build một artifact cố định.
2. Tạo AOT cache từ workload đại diện.
3. Chạy baseline không cache với cùng JDK, heap limits, GC và container limits.
4. Chạy lại với AOT cache.
5. Đo startup, readiness, first request, warmup throughput và P95/P99.
6. Lặp lại đủ số lần để giảm nhiễu do OS page cache, CPU scheduling và background load.
7. Ghi rõ cache có được JVM nạp thành công hay không.

Không so baseline trên một JDK với cache trên JDK khác rồi kết luận chênh lệch là do AOT cache. Cũng không so lần đầu sau khi máy cold boot với lần sau khi OS filesystem cache đã nóng mà bỏ qua yếu tố đó.

### 13.3. Khi nào AOT cache không giúp nhiều?

- Ứng dụng có startup cost chủ yếu là đợi database hoặc remote service.
- Workload training không bao phủ các method quan trọng.
- Ứng dụng thay đổi artifact quá thường xuyên, cache liên tục bị invalidated.
- Thời gian startup vốn đã rất thấp.
- Service chạy lâu và phần lớn chi phí nằm trong steady-state workload.
- Cache không được nạp do khác JDK, classpath, OS/CPU hoặc JVM options.

AOT cache không đảm bảo một tỷ lệ tăng tốc cố định. Giá trị phải được đo trên hệ thống thật.

## 14. An toàn khi chạy training

Training run thực sự **chạy ứng dụng**. Vì vậy, nó có thể kích hoạt initializer, listener, scheduler hoặc logic startup có side effects. Không được coi training như một thao tác chỉ đọc file.

Trước khi chạy training:

- Dùng môi trường cô lập và test data phù hợp.
- Chặn gửi email/SMS, thanh toán, publish message hoặc gọi hệ thống production.
- Dùng database/schema thử nghiệm hoặc adapter giả lập.
- Kiểm tra bean initialization có gọi remote services trước khi application lifecycle bắt đầu hay không.
- Không ghi secret/token/credential vào file cache, log hoặc training artifacts.
- Hạn chế quyền của user tạo cache và kiểm soát việc phân phối .aot.
- Không chạy training trong production nếu chưa kiểm soát được side effects.

Với Spring Boot, các kết nối remote có thể được thực hiện từ sớm trong startup, trước khi Spring lifecycle bắt đầu. Cần có cấu hình riêng cho training để ngăn tương tác không mong muốn với hệ thống bên ngoài.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| File .aot có nhưng startup không nhanh hơn | Cache không được nạp hoặc bottleneck ở remote I/O | Kiểm -Xlog:aot, startup trace và readiness |
| JVM bỏ qua cache | Khác JDK, artifact, OS/CPU hoặc JVM options | Tạo cache lại từ đúng deployment target |
| Cache class loading có nhưng method warmup không cải thiện | Training không chạy workload đại diện | Tạo training run có method profiles |
| Dùng spring.context.exit=onRefresh nhưng method profile ít giá trị | Training dừng trước business workflow | Chạy synthetic traffic trước khi dừng training |
| Spring Boot cache không có tác dụng | Dùng executable JAR chưa extract hoặc layout không tương thích | Dùng extracted application layout theo hướng dẫn Boot |
| Runtime vẫn truy vấn database | AOT cache không lưu database state | Giữ repository và database là nguồn dữ liệu nghiệp vụ |
| Session không tồn tại sau restart | Session không phải trạng thái AOT cache | Dùng session store/persistence nếu yêu cầu |
| Cache hoạt động ở máy build nhưng không hoạt động ở máy chạy | Khác OS/CPU/JDK hoặc classpath | Tạo cache cho đúng target platform |
| Training run tạo đơn hàng thật | Startup/workload có side effects | Cô lập adapter, dữ liệu và endpoint bên ngoài |
| Production chạy sai cấu hình sau khi dùng cache | Nhầm object/archive với runtime config | Đọc config theo môi trường ở mỗi lần chạy |
| Cache quá cũ sau release mới | Không gắn cache với artifact version | Tạo cache như một phần của pipeline mỗi release |
| Bật cache nhưng P99 tăng | Profile không đại diện hoặc bottleneck khác | Benchmark lại và xem JIT/GC/I/O metrics |

## 16. Pipeline triển khai AOT cache cho Java 25

Một pipeline có thể được tổ chức như sau:

~~~mermaid
flowchart TD
    A["Build application artifact"] --> B["Chốt JDK, OS/CPU target"]
    B --> C["Extract package nếu framework yêu cầu"]
    C --> D["Training trong môi trường cô lập"]
    D --> E["Chạy startup + workload đại diện"]
    E --> F["Assembly tạo app.aot"]
    F --> G["Verify cache compatibility"]
    G --> H["Đóng gói artifact + cache"]
    H --> I["Deploy canary"]
    I --> J["Kiểm startup, readiness, latency"]
    J --> K{"SLO và correctness đạt?"}
    K -- "Có" --> L["Rollout"]
    K -- "Không" --> M["Rollback artifact/runtime"]
~~~

### 16.1. Gắn cache với build identity

Nên ghi lại metadata cùng release:

| Metadata | Mục đích |
|---|---|
| Application version/digest | Xác định artifact tạo cache |
| JDK vendor, version, build | Xác định runtime |
| OS image digest | Xác định nền tảng |
| CPU architecture | Xác định target architecture |
| Classpath/dependency list | Xác định thứ tự và tập JAR |
| Training workload version | Biết profile được thu từ kịch bản nào |
| Cache creation timestamp | Theo dõi tuổi cache |
| Benchmark result | Quyết định có tiếp tục sử dụng hay không |

Không sửa cache file sau khi tạo. Khi release artifact mới, tạo cache tương ứng và triển khai chúng như một cặp.

### 16.2. Cache lỗi không được làm hỏng nghiệp vụ

Trong production, ưu tiên cấu hình để ứng dụng có thể chạy không cache khi cache không dùng được, nếu chính sách triển khai cho phép. Sau đó phát cảnh báo và điều tra. Chỉ dùng chế độ fail-fast khi muốn xác minh compatibility trong test/canary hoặc khi quy trình vận hành yêu cầu rõ ràng.

## 17. Tình huống thực tế: một service xử lý đơn hàng

Giả sử một Spring Boot service có luồng:

1. Nhận POST /orders.
2. Xác thực request.
3. Đọc giá sản phẩm và tồn kho.
4. Tính tổng tiền.
5. Ghi đơn hàng vào database.
6. Publish event sang message broker.

Trong training, có thể chạy các request giả lập để JVM quan sát class loading và method execution profiles của các bước 2–6.

Khi production khởi động bằng cache:

- JVM có thể nạp class artifacts và method profiles từ cache.
- Spring vẫn dựng ApplicationContext và các bean theo runtime configuration.
- Database pool và message broker connections được mở mới.
- Request thật được xác thực lại.
- Giá sản phẩm và tồn kho được đọc từ nguồn dữ liệu hiện tại.
- Đơn hàng mới được ghi bằng transaction mới.
- Event được publish theo hoạt động thực tế.

**Không có đơn hàng nào từ training được khôi phục thành đơn hàng production chỉ vì AOT cache được nạp.** Nếu training vô tình ghi đơn thật, đó là side effect của việc chạy ứng dụng trong môi trường training; AOT cache không phải nguyên nhân lưu hoặc khôi phục dữ liệu đó. Vì vậy, phải cách ly side effects trước khi training.

## 18. Bài tập thực hành

**Bài 1 — Phân loại dữ liệu:** Liệt kê 15 thành phần của một ứng dụng Spring Boot và đánh dấu chúng thuộc class artifact, archived heap object, method profile hay runtime business state. Giải thích các trường hợp dễ nhầm.

**Bài 2 — AOT cache không phải snapshot:** Viết một chương trình tăng counter trong memory ở training run. Chạy lại với cùng AOT cache và giải thích vì sao counter không tự mang giá trị của process trước.

**Bài 3 — Training và production:** Tạo cache cho một ứng dụng Java đơn giản bằng AOTCacheOutput. Sau đó chạy với AOTCache. Kiểm log để xác nhận cache được sử dụng.

**Bài 4 — Spring Boot startup cache:** Extract executable JAR, tạo cache với spring.context.exit=onRefresh, chạy lại bằng cache và đo readiness time.

**Bài 5 — Method profile:** Tạo workload có một method được gọi thường xuyên, chạy training với traffic giả lập rồi tạo cache. So sánh warmup với cache startup-only. Không khẳng định kết quả nếu chưa đo.

**Bài 6 — Phân biệt Spring AOT:** Tìm trong build output phần code Spring AOT được sinh và file .aot do JVM tạo. Giải thích hai loại artifact có lifecycle khác nhau.

**Bài 7 — Cache mismatch:** Thử dùng cache với một artifact/JDK/platform khác trong môi trường kiểm thử. Đọc log và giải thích vì sao JVM có thể bỏ qua cache.

**Bài 8 — Side effects:** Liệt kê các bean initializer, scheduler, listener và outbound client có thể chạy trong training. Thiết kế profile/configuration để chúng không tác động hệ thống production.

**Bài 9 — Benchmark:** So sánh cold startup, readiness, first request, warmup throughput, P95/P99 và RSS giữa baseline và cache. Lặp nhiều lần và ghi lại build/JDK/platform.

**Bài 10 — Release pipeline:** Thiết kế bước tạo cache theo application digest và target platform; nêu điều kiện phải tạo lại cache sau mỗi release.

## 19. Checklist hoàn thành

- [ ] Giải thích AOT cache là artifact tối ưu JVM, không phải snapshot process.
- [ ] Phân biệt class metadata, archived heap objects và method profiles.
- [ ] Hiểu method profiles của Java 25 là dữ liệu thống kê, không phải dữ liệu nghiệp vụ.
- [ ] Không kỳ vọng cache khôi phục session, transaction, socket, connection pool hoặc request đang chạy.
- [ ] Phân biệt JVM AOT cache với Spring AOT processing và native image.
- [ ] Hiểu AOT cache được giới thiệu qua JEP 483; JEP 514/515 cải tiến trong Java 25.
- [ ] Biết AOTCacheOutput và AOTCache.
- [ ] Phân biệt startup-only training với production-like workload training.
- [ ] Hiểu giới hạn của spring.context.exit=onRefresh.
- [ ] Dùng extracted application layout khi quy trình Spring Boot yêu cầu.
- [ ] Tạo cache tương thích với artifact, JDK, OS và CPU architecture.
- [ ] Kiểm classpath, JAR timestamps, JVM options và agents.
- [ ] Xác minh cache qua -Xlog:aot và class loading logs.
- [ ] Benchmark startup, readiness, warmup, latency và memory.
- [ ] Cô lập database writes, messaging, email và các side effects trong training.
- [ ] Gắn cache với build identity và tạo lại khi release/platform thay đổi.
- [ ] Bảo đảm ứng dụng vẫn đúng khi AOT cache không được nạp.

## Tài liệu tham khảo chính thức

- [JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): AOT cache và các artifact JVM được chuẩn bị trước.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): đơn giản hóa lệnh training và tạo cache trong JDK 25.
- [JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): sử dụng method execution profiles từ lần chạy trước ở thời điểm JVM khởi động.
- [Oracle JDK 25 — Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): mô tả JEP 514 và JEP 515 trong Java 25.
- [Oracle JDK 25 — java command, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): các option AOTCacheOutput, AOTCache, AOTMode và quy tắc tương thích.
- [Spring Framework — JVM AOT Cache](https://docs.spring.io/spring-framework/reference/integration/aot-cache.html): training, method profiling trong Java 25+, classpath và cách kiểm cache.
- [Spring Boot — AOT Cache](https://docs.spring.io/spring-boot/reference/packaging/aot-cache.html): extract executable JAR, training run và production run.
- [Spring Boot — AOT Cache How-to](https://docs.spring.io/spring-boot/how-to/aot-cache.html): đóng gói cache bằng Buildpacks và Dockerfiles.

## Kết luận

**AOT cache lưu kết quả tối ưu hóa mà JVM có thể tái sử dụng; nó không lưu toàn bộ trạng thái ứng dụng đang chạy.** Trong Java 25, cache có thể giúp JVM tận dụng class artifacts, archived heap objects và method profiles từ training run. Nhưng mỗi JVM production vẫn phải dựng runtime state mới: đọc cấu hình, khởi tạo framework, mở kết nối, xác thực request và nạp dữ liệu nghiệp vụ từ nguồn lưu trữ.

Để dùng AOT cache đúng cách, hãy chọn workload training theo mục tiêu. spring.context.exit=onRefresh phù hợp khi tập trung vào startup; workload production-like cần thiết khi muốn method profiles phản ánh các luồng thực tế. Sau đó gắn cache với đúng artifact/JDK/platform, xác minh qua log và benchmark, kiểm soát side effects trong training. **Khi tách bạch artifact tối ưu JVM với trạng thái nghiệp vụ, bạn có thể tận dụng AOT cache mà vẫn giữ đúng vòng đời và tính nhất quán của ứng dụng Java hiện đại.**
