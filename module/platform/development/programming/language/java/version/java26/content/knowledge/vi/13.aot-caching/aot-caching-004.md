# Quan hệ giữa CDS, lớp đã liên kết và đối tượng được lưu

**Class Data Sharing (CDS)** là nền tảng lưu trữ và tái sử dụng dữ liệu lớp giữa các lần chạy JVM. Project Leyden mở rộng nền tảng đó thành **Ahead-of-Time (AOT) cache**: thay vì chỉ lưu dữ liệu lớp đã được phân tích, cache còn có thể lưu lớp đã được nạp và liên kết trước, cùng một số đối tượng Java trên heap được JVM xác định là có thể lưu trữ và tái sử dụng.

Trong Java 26, JEP 516 hoàn thiện phần lưu đối tượng để AOT cache dùng được với mọi garbage collector, bao gồm ZGC. Với định dạng GC-agnostic, JVM nạp và materialize các đối tượng từ cache vào heap theo cách tương thích với collector đang chạy, thay vì phụ thuộc vào bố cục object/reference của một GC cụ thể. Mục tiêu là giảm công việc khởi động và warm-up, không phải chụp toàn bộ heap của ứng dụng hay tạo một executable native.

**Trạng thái:** AOT cache, CDS và các tối ưu của JEP 483/JEP 516 là tính năng runtime của HotSpot đã được đưa vào JDK 24 và JDK 26; không phải preview feature hoặc incubator API. Java 26 dùng quy trình ba giai đoạn Training, Assembly và Production. [JEP 483](https://openjdk.org/jeps/483) · [JEP 516](https://openjdk.org/jeps/516) · [JDK 26 Significant Changes](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html).

## 1. Ba lớp khái niệm cần phân biệt

CDS, AOT class loading/linking và AOT object caching có quan hệ với nhau, nhưng mỗi phần lưu một loại dữ liệu và giảm một nhóm công việc khác nhau.

| Thành phần | Dữ liệu được lưu | Công việc được giảm khi JVM khởi động |
|---|---|---|
| **CDS** | Dữ liệu lớp đã được xử lý trước, metadata của lớp; có thể kèm một số heap object được phép archive. | Đọc và phân tích lại class file, tạo lại một phần metadata; các archive dùng chung có thể được memory-map giữa nhiều JVM. |
| **AOT class loading & linking** (JEP 483) | Các lớp mà JVM đã quan sát trong lần Training, ở trạng thái đã nạp và đã liên kết; có thể bao gồm thông tin module graph và các tham chiếu đã được giải quyết trước. | Nạp và liên kết lại các lớp đó trong mỗi lần chạy; giảm công việc phân tích, xác minh, chuẩn bị và giải quyết tham chiếu. |
| **AOT heap object caching** (JEP 483, được mở rộng bởi JEP 516) | Một số đối tượng Java trên heap và các tham chiếu giữa chúng, chẳng hạn `Class` object cùng các `String` hoặc byte array mà chúng tham chiếu. | Tạo lại các đối tượng runtime có thể tái sử dụng và dựng lại một phần object graph trong giai đoạn khởi động. |

Có thể hình dung mối quan hệ như sau:

```text
CDS archive
  └─ Dữ liệu lớp và metadata đã xử lý
       |
       v
AOT cache (JDK 24+, dựa trên CDS)
  ├─ Các lớp đã nạp và liên kết (JEP 483)
  └─ Các heap object đủ điều kiện archive
       ├─ Class objects / class mirrors
       ├─ String, byte array và object được tham chiếu
       └─ Một số object graph nội bộ của JDK
              |
              v
      Nạp vào JVM mới và liên kết với runtime heap
              |
              v
       JEP 516: định dạng object GC-agnostic
       để dùng được với G1, Parallel, Serial, ZGC...
```

CDS là cơ chế lưu trữ và chia sẻ dữ liệu lớp. AOT cache dùng nền tảng đó để lưu thêm trạng thái đã nạp/liên kết và heap objects. JEP 516 xử lý vấn đề bố cục object khi tái tạo các đối tượng đã archive dưới những garbage collector khác nhau.

## 2. CDS lưu gì và vì sao có ích?

Khi JVM khởi động, nó cần tìm class file, đọc bytecode, phân tích cấu trúc lớp và tạo các cấu trúc nội bộ trong Metaspace. Những lớp nền tảng như `java.lang.String`, `java.lang.Object`, collection classes và nhiều lớp khác thường xuất hiện trong hầu hết ứng dụng.

CDS cho phép chuẩn bị dữ liệu của các lớp dùng chung trước. Khi một JVM mới khởi động, archive có thể được memory-map để tái sử dụng phần dữ liệu đã chuẩn bị. Điều này giảm công việc đọc/phân tích class và có thể giảm footprint khi nhiều tiến trình JVM cùng dùng archive.

Trong phần lớn bản phân phối JDK, một default CDS archive được đóng gói sẵn và được bật mặc định, trừ khi ứng dụng tắt bằng `-Xshare:off`. Ứng dụng cũng có thể tạo dynamic CDS archive chứa các lớp ứng dụng đã được nạp trong một lần chạy. CDS hiện đại còn hỗ trợ archive một số heap object tĩnh, ví dụ dữ liệu module graph; vì vậy, không nên hiểu CDS chỉ chứa bytecode thô.

Ví dụ tạo dynamic CDS archive cho một ứng dụng:

```bash
# Chạy ứng dụng và tạo archive từ các lớp được nạp trong lần chạy
java -XX:ArchiveClassesAtExit=app-cds.jsa -cp app.jar com.example.Main

# Dùng archive trong lần chạy sau
java -XX:SharedArchiveFile=app-cds.jsa -cp app.jar com.example.Main
```

Đây là luồng CDS truyền thống, vẫn được hỗ trợ trong JDK 26. Nó hữu ích khi mục tiêu là chia sẻ class data và giảm chi phí nạp lớp. Khi cần cả lớp đã liên kết và AOT heap objects theo quy trình Leyden, dùng AOT cache.

## 3. AOT class loading và linking bổ sung điều gì?

JEP 483 đưa thêm bước xử lý lớp về trước thời điểm production. Trong lần Training, JVM chạy ứng dụng và ghi nhận các lớp được nạp. Ở giai đoạn Assembly, JDK tạo AOT cache chứa các lớp phù hợp ở trạng thái đã nạp và liên kết. Khi production JVM khởi động, nó có thể khôi phục trạng thái đó thay vì lặp lại toàn bộ công việc.

Trong JVM, linking bao gồm các bước xác minh, chuẩn bị và giải quyết tham chiếu. Chẳng hạn, một class file có symbolic reference tới class, field hoặc method khác. Khi tham chiếu được resolve, JVM xác định thực thể đích và lưu thông tin cần thiết để lần sử dụng sau không phải thực hiện lại cùng một công việc. Với AOT class linking, JDK có thể làm trước một số công việc như resolution của `invokedynamic` instructions.

`-XX:+AOTClassLinking` là tùy chọn liên quan đến phần tối ưu này. Trong JDK 26, khi dùng `-XX:AOTMode`, AOT class linking được bật tự động. Nếu không dùng `AOTMode`, AOT class linking mặc định tắt để giữ tương thích với luồng CDS truyền thống như `-Xshare:dump`.

### Linking không đồng nghĩa với class initialization

Nạp và liên kết lớp không có nghĩa là JVM chạy toàn bộ static initializer của ứng dụng trong giai đoạn Assembly. Class initialization (`<clinit>`) là giai đoạn riêng theo vòng đời lớp. AOT cache lưu các trạng thái mà JVM cho phép archive; khi production khởi động, những lớp hoặc trạng thái chưa có trong cache vẫn được xử lý theo cơ chế runtime thông thường.

Nếu một lớp chưa được nạp trong Training, JVM có thể phải nạp và liên kết lớp đó khi ứng dụng thực sự cần. Vì vậy, workload Training cần đại diện cho những luồng nghiệp vụ mà ứng dụng thường sử dụng.

## 4. Đối tượng được lưu là gì?

Java 26 AOT cache hiện lưu Java classes và heap objects. Các object được archive là những đối tượng runtime mà JVM có thể tái tạo an toàn từ trạng thái đã ghi nhận. Ví dụ thường gặp là `java.lang.Class` object (class mirror) và những `String`, byte array hoặc object được chúng tham chiếu.

Khi một class đã được nạp, JVM tạo một `Class` object đại diện cho class đó. Object này có liên hệ với metadata của lớp trong JVM. Nó cũng có thể tham chiếu tới các đối tượng khác như tên lớp, chuỗi hằng, dữ liệu byte hoặc cấu trúc nội bộ. AOT cache có thể lưu cả object graph phù hợp, nhờ đó JVM mới không phải tạo lại mọi object từ đầu.

```text
Class metadata đã archive
          |
          v
   java.lang.Class object
          |
          +------> String: tên lớp
          |
          +------> byte[]: dữ liệu liên quan
          |
          +------> các object runtime được tham chiếu
```

Điểm quan trọng: đây không phải snapshot toàn bộ Java heap. AOT cache không tự lưu session người dùng, request đang chạy, transaction, dữ liệu mutable trong cache nghiệp vụ hoặc mọi instance của các class ứng dụng. Chỉ các đối tượng và object graph đủ điều kiện do cơ chế archiving của JVM lựa chọn mới được lưu. Ứng dụng vẫn khởi tạo trạng thái nghiệp vụ theo cách thông thường.

Việc object có thể được lưu hay không phụ thuộc quy tắc archiving và cách JVM tái tạo object graph; không dùng AOT cache như một cơ chế persistence cho dữ liệu nghiệp vụ hoặc để khôi phục trạng thái ứng dụng giữa các lần chạy.

## 5. JEP 516: lưu object độc lập với garbage collector

Trước JEP 516, heap object trong AOT cache được lưu theo định dạng phụ thuộc garbage collector. JVM có thể memory-map nội dung archive trực tiếp vào vùng heap khi bố cục object và reference tương thích. Cách này rất nhanh khi dữ liệu cache đã nằm trong filesystem page cache, nhưng tạo ràng buộc về cách từng GC biểu diễn object và reference.

ZGC có bố cục object/reference khác với các collector dùng định dạng archive cũ. Do đó, các tối ưu AOT cần archived heap objects trước JDK 26 không dùng được đầy đủ với ZGC. JEP 516 bổ sung định dạng object **GC-agnostic** để tách nội dung archive khỏi bố cục heap riêng của collector.

| Định dạng | Cách nạp | Ưu điểm | Đánh đổi |
|---|---|---|---|
| **GC-specific / mappable** | Memory-map object data trực tiếp vào heap khi định dạng tương thích với GC. | Rất nhanh khi archive đã nằm trong filesystem cache; ít công việc materialize object. | Phụ thuộc bố cục object/reference của GC và cấu hình heap. |
| **GC-agnostic / streamable** | Đọc dữ liệu archive theo luồng và materialize object vào heap theo bố cục mà GC hiện tại yêu cầu. Công việc có thể chạy nền song song với startup. | Dùng được với các GC khác nhau, bao gồm ZGC; có thể che bớt độ trễ đọc archive trên cold start. | Cần CPU và công việc tạo object/reference trong lúc khởi động. |

Trong định dạng streamable, archive không thể đơn giản đưa nguyên byte của object vào heap như memory mapping. JVM đọc dữ liệu, tạo object theo quy tắc của collector đang chạy và khôi phục các liên kết tham chiếu giữa object. Cách làm này cho phép G1, Parallel, Serial và ZGC quản lý các object sau khi chúng được materialize theo định dạng heap phù hợp.

JDK 26 có thể lựa chọn định dạng phù hợp theo cấu hình và quá trình Training. `-XX:+AOTStreamableObjects` là tùy chọn chẩn đoán nâng cao để yêu cầu định dạng streamable khi tạo cache; cần mở nhóm diagnostic options trước khi dùng:

```bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+AOTStreamableObjects \
     -XX:AOTMode=create \
     -XX:AOTConfiguration=app.aotconfig \
     -XX:AOTCacheOutput=app-streamable.aot \
     -cp app.jar com.example.Main
```

Tùy chọn này tác động tới định dạng khi ghi archive trong giai đoạn Assembly, không phải cờ bật GC-agnostic cho mọi lần production. Chỉ cân nhắc điều chỉnh khi đã đo trên JDK/GC và môi trường triển khai thực tế. Với cấu hình thông thường, nên để JVM chọn định dạng thay vì mặc định rằng streamable luôn nhanh hơn memory mapping.

### Tại sao streamable có thể nhanh hơn dù phải tạo object?

Memory mapping có lợi khi cache đã nóng trong filesystem cache. Nhưng nếu cache phải đọc từ storage chậm, startup có thể chờ dữ liệu được fault-in vào bộ nhớ. Với streamable format, JVM có thể đọc và materialize object bằng thread nền trong lúc ứng dụng bắt đầu chạy. Phần công việc này dùng thêm CPU, nhưng có thể che một phần thời gian I/O và cải thiện cold start.

Đánh giá hai định dạng cần tách ít nhất hai tình huống: warm start (archive đã có trong page cache) và cold start (archive phải đọc từ storage). Cùng một định dạng không nhất thiết tối ưu cho cả hai.

## 6. Quy trình tạo và dùng AOT cache trong Java 26

Quy trình AOT cache gồm ba giai đoạn:

1. **Training:** chạy ứng dụng với workload đại diện. JVM ghi thông tin vào AOT Configuration file (`.aotconfig`).
2. **Assembly:** dùng file cấu hình để tạo AOT cache (`.aot`). Ở giai đoạn này ứng dụng không được thực thi; JVM đọc lịch sử/thống kê và tạo artifact tối ưu.
3. **Production:** khởi chạy ứng dụng với AOT cache để giảm startup và warm-up.

Giả sử ứng dụng được đóng gói trong `app.jar`, main class là `com.example.Main`.

### Bước 1: Training

```bash
java -XX:AOTMode=record \
     -XX:AOTConfiguration=app.aotconfig \
     -cp app.jar com.example.Main
```

Chạy các luồng nghiệp vụ đại diện trong lần này: khởi tạo dependency, mở kết nối cần thiết, thực hiện các tác vụ thường dùng và tải các module/lớp liên quan. Sau khi workload hoàn tất, kết thúc tiến trình để file `app.aotconfig` được ghi hoàn chỉnh.

Training quá ngắn hoặc chỉ chạy startup có thể bỏ sót lớp được nạp muộn. Training bằng dữ liệu thử nghiệm không đại diện có thể khiến cache chứa lớp không cần thiết hoặc thiếu lớp quan trọng. Không đưa dữ liệu bí mật hay dữ liệu production nhạy cảm vào quy trình Training nếu không cần thiết.

### Bước 2: Assembly

```bash
java -XX:AOTMode=create \
     -XX:AOTConfiguration=app.aotconfig \
     -XX:AOTCacheOutput=app.aot \
     -cp app.jar com.example.Main
```

JVM đọc `app.aotconfig` và ghi `app.aot`. Ứng dụng không chạy `main()` trong giai đoạn Assembly. File `.aot` là AOT cache được production JVM sử dụng.

### Bước 3: Production

```bash
java -XX:AOTMode=auto \
     -XX:AOTCache=app.aot \
     -cp app.jar com.example.Main
```

`auto` là chế độ mặc định của Java 26. Nếu cache tương thích, JVM dùng cache. Nếu cache không thể được nạp, JVM tiếp tục chạy mà không dùng cache; ứng dụng vẫn hoạt động nhưng không nhận được lợi ích AOT. Đây là chế độ phù hợp cho production khi không thể kiểm soát hoàn toàn mọi JVM argument được thêm vào môi trường triển khai.

Khi cần kiểm tra fail-fast, có thể dùng `-XX:AOTMode=on`. Nếu cache không thể được nạp, JVM báo lỗi và thoát. Không nên chọn `on` làm mặc định cho môi trường mà command line có thể bị agent hoặc nền tảng triển khai thay đổi ngoài dự kiến.

### Các tùy chọn cần nhớ

| Tùy chọn | Ý nghĩa |
|---|---|
| `-XX:AOTMode=auto` | Chế độ mặc định; tự chọn record/on/off theo việc có cache đầu ra hoặc cache có thể nạp được hay không. |
| `-XX:AOTMode=record` | Chạy ứng dụng để Training và ghi `.aotconfig`. |
| `-XX:AOTMode=create` | Assembly cache từ `.aotconfig`; không chạy ứng dụng. |
| `-XX:AOTMode=on` | Production và yêu cầu nạp cache; không nạp được thì JVM thoát. |
| `-XX:AOTMode=off` | Không dùng AOT cache. |
| `-XX:AOTConfiguration=file.aotconfig` | File cấu hình Training/Assembly. |
| `-XX:AOTCacheOutput=file.aot` | Đường dẫn AOT cache được tạo trong Assembly. |
| `-XX:AOTCache=file.aot` | Đường dẫn cache được nạp trong Production. |
| `-Xlog:aot` | Ghi log chẩn đoán việc sử dụng AOT cache và lý do cache không được dùng. |

`-XX:AOTCache` và `-XX:AOTCacheOutput` không được dùng đồng thời trong cùng một invocation. Nếu đặt `-XX:AOTCacheOutput` trong chế độ `auto`, JVM chuyển sang Training và thực hiện Assembly bằng một JVM thứ hai để tạo cache.

## 7. Quan hệ giữa AOT class linking và archived object graph

Lớp đã nạp/liên kết và heap objects có quan hệ tham chiếu với nhau. Một `Class` object đại diện cho lớp đã nạp; các object runtime có thể giữ tham chiếu tới class mirror hoặc metadata liên quan. Nếu chỉ archive metadata lớp mà không xử lý các object graph phụ thuộc, JVM vẫn cần tạo lại một phần đối tượng và nối lại tham chiếu trong startup.

AOT cache có thể lưu cả hai phần: class metadata ở trạng thái đã xử lý và các heap objects phù hợp. Khi production JVM nạp cache, các lớp được khôi phục cùng các object liên quan. Với GC-specific format, object data có thể được memory-map khi layout tương thích. Với GC-agnostic format của JEP 516, JVM materialize object và phục hồi các tham chiếu để collector hiện tại quản lý chúng.

Trong JDK 26, nội dung được tài liệu hóa của AOT cache là Java classes và heap objects. File `.aotconfig` chứa dữ liệu Training để quyết định nội dung nào nên đưa vào cache; điều đó không có nghĩa cache production đã chứa mã máy của mọi method. JIT vẫn biên dịch và tối ưu các method nóng trong runtime.

Vì vậy, ba phần bổ sung cho nhau:

- CDS giảm công việc phân tích và chia sẻ class data.
- AOT class loading/linking giảm công việc nạp, xác minh, chuẩn bị và resolve lớp.
- AOT object caching giảm việc tạo lại các heap object đủ điều kiện và tái lập các object reference liên quan.

Không phần nào thay thế hoàn toàn các bước runtime. Lớp chưa được Training quan sát, object không đủ điều kiện archive, hoặc trạng thái nghiệp vụ phát sinh sau startup vẫn được tạo và xử lý trong tiến trình production bình thường.

## 8. Điều kiện tương thích của cache

AOT cache gắn với ứng dụng và môi trường tạo cache. Theo tài liệu Java 26, cần tạo lại cache khi thay đổi một trong các thành phần quan trọng sau:

- Ứng dụng được xác định bằng `-classpath`, `-jar` hoặc `--module-path`.
- JDK release dùng để tạo cache.
- Hệ điều hành hoặc CPU architecture.
- Nội dung JAR/class path hoặc các tùy chọn module/JVM làm thay đổi môi trường nạp và liên kết.

Một số quy tắc CDS cũng áp dụng cho AOT cache:

- Class path lúc tạo archive cần tương thích với class path lúc chạy; các JAR trong class path hoặc module path không được sửa sau khi archive được tạo.
- Những module options như `--module-path`, `--module`, `--add-modules` và `--enable-native-access`, nếu dùng khi tạo cache, cần có giá trị tương ứng khi production sử dụng cache.
- Nếu AOT class linking được bật khi tạo archive, archive yêu cầu archived full module graph tương thích. Nếu full module graph không được sử dụng, JVM có thể từ chối archive với thông báo `CDS archive has aot-linked classes. It cannot be used when archived full module graph is not used`.
- Các tùy chọn `--upgrade-module-path`, `--patch-module` và `--limit-modules` làm CDS bị vô hiệu hóa trong JDK 26.
- Một số JVM options hoặc JVMTI agents có thể khiến cache không tương thích. Không thể giả định mọi tổ hợp agent, instrumentation và class transformation đều dùng được AOT cache.

Khi dùng `-XX:AOTMode`, AOT class linking được bật tự động. Nếu chủ động tắt bằng `-XX:-AOTClassLinking`, cần hiểu rằng cache sẽ không có các tối ưu class linking tương ứng. Không thêm hoặc bỏ các cờ này tùy tiện giữa Training, Assembly và Production.

## 9. Chẩn đoán khi AOT cache không được dùng

Nếu JVM khởi động bình thường nhưng không có lợi ích AOT, hãy kiểm tra log:

```bash
java -Xlog:aot \
     -XX:AOTMode=auto \
     -XX:AOTCache=app.aot \
     -cp app.jar com.example.Main
```

`-Xlog:aot` giúp quan sát việc nạp cache, mismatch giữa tùy chọn module lúc dump và runtime, hoặc lý do archive không thể sử dụng. Nếu cần xác nhận cache có bắt buộc phải nạp được hay không, chạy staging với `-XX:AOTMode=on` để JVM fail-fast thay vì âm thầm fallback.

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| JVM chạy bình thường nhưng startup không cải thiện | `AOTMode=auto` fallback vì cache không tương thích hoặc không tồn tại. | Bật `-Xlog:aot`, kiểm tra đường dẫn và lý do cache bị bỏ qua. |
| Cache không nạp sau khi nâng JDK | Cache được tạo bởi JDK release khác. | Training và Assembly lại bằng JDK release production. |
| Cache không nạp sau khi đổi container/base image | OS hoặc CPU architecture khác; JDK build khác; file JAR thay đổi. | Tạo cache trong môi trường tương ứng với production. |
| Lỗi archived full module graph | AOT-linked classes được tạo với module graph khác runtime. | Giữ module options nhất quán và tạo lại cache. |
| CDS bị tắt | Có `--patch-module`, `--upgrade-module-path` hoặc `--limit-modules`. | Đánh giá lại cấu hình module; loại bỏ option không cần hoặc chấp nhận không dùng cache. |
| Lớp nghiệp vụ vẫn được nạp lúc runtime | Lớp không được load trong Training. | Chạy lại Training với workload đại diện có sử dụng luồng nghiệp vụ đó. |
| Startup cold không nhanh như kỳ vọng | Đọc cache từ storage chậm, materialization object hoặc workload chưa phù hợp. | Đo cold/warm start riêng, kiểm tra loại cache và tài nguyên CPU/I/O. |

## 10. Đo hiệu quả đúng cách

AOT cache chủ yếu giảm startup và warm-up. Nó không bảo đảm tăng throughput lâu dài cho mọi ứng dụng. Sau khi startup, JIT vẫn tiếp tục tối ưu các method nóng theo hành vi runtime. Nếu workload chạy liên tục nhiều giờ, chi phí startup có thể ít quan trọng hơn so với throughput, GC pause hoặc latency của request.

Khi benchmark, nên đo riêng:

1. **Cold start:** lần chạy khi cache file chưa nằm trong filesystem page cache.
2. **Warm start:** lần chạy khi cache đã nằm trong page cache.
3. **Time to readiness:** thời gian từ lúc khởi động JVM đến khi ứng dụng thực sự sẵn sàng nhận traffic.
4. **Warm-up:** thời gian để latency/throughput ổn định sau khi nhận workload.
5. **Tài nguyên:** CPU, RSS, heap, I/O và thời gian GC trong lúc materialize archived objects.

So sánh cùng JDK build, cùng container/CPU, cùng classpath/module path và cùng workload. Chạy nhiều lần và tách cold/warm start; không kết luận từ một lần đo. Nếu ứng dụng có agent, profiling hoặc instrumentation trong production, kiểm tra tương thích cache trong đúng cấu hình đó.

### Khi nào nên dùng?

- Dịch vụ khởi động thường xuyên, autoscaling hoặc scale-to-zero và cần giảm thời gian sẵn sàng.
- CLI hoặc worker được khởi tạo nhiều lần trong thời gian ngắn.
- Ứng dụng có nhiều lớp nền tảng/thư viện được nạp lặp lại giữa các lần chạy.
- Dịch vụ muốn sử dụng ZGC nhưng vẫn hưởng lợi từ AOT object caching trong JDK 26.

### Khi nào lợi ích có thể nhỏ?

- Ứng dụng chạy liên tục lâu dài và startup không nằm trên đường latency quan trọng.
- Workload Training không đại diện hoặc lớp được dùng chủ yếu chỉ xuất hiện ở một luồng hiếm.
- Môi trường triển khai thay đổi liên tục khiến cache phải tạo lại thường xuyên.
- Phần lớn startup time đến từ kết nối mạng, đọc cấu hình ngoài, migration database hoặc công việc nghiệp vụ không thể archive.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| CDS và AOT cache là hai tên của cùng một file cache. | CDS là nền tảng chia sẻ class data; AOT cache mở rộng nền tảng đó để chứa trạng thái lớp đã liên kết và heap objects. |
| AOT cache lưu toàn bộ heap của lần Training. | Chỉ các đối tượng đủ điều kiện archive do JVM lựa chọn; không phải snapshot session/request hoặc toàn bộ trạng thái nghiệp vụ. |
| AOT class linking nghĩa là JVM đã chạy static initializer của mọi class. | Linking và class initialization là các giai đoạn khác nhau. Không mặc định `<clinit>` đã được chạy chỉ vì class được archive ở trạng thái linked. |
| JEP 516 biến mọi object thành GC-independent ngay trong heap. | JEP 516 bổ sung định dạng archive GC-agnostic; object vẫn được materialize vào heap theo quy tắc của collector đang chạy. |
| AOT cache là native image hoặc đã biên dịch mọi method thành mã máy. | JDK 26 AOT cache chứa class data và heap objects; JIT vẫn tối ưu method nóng trong runtime. |
| Dùng ZGC thì không thể dùng AOT cache. | JEP 516 mở khả năng dùng AOT object caching với mọi GC, bao gồm ZGC, nhờ định dạng GC-agnostic. |
| `AOTMode=on` là chế độ an toàn nhất cho mọi production. | `on` fail-fast khi cache không nạp được; `auto` fallback và được khuyến nghị cho production khi command line có thể thay đổi. |
| Chỉ cần tạo cache một lần cho mọi máy và mọi JDK. | Cache phụ thuộc ứng dụng, JDK release, OS/CPU và các tùy chọn nạp lớp liên quan; thay đổi môi trường cần tạo lại. |

## 12. Checklist triển khai

- [ ] Đã phân biệt CDS, AOT class loading/linking và AOT heap object caching.
- [ ] Đã xác định mục tiêu là giảm startup/warm-up, không kỳ vọng AOT cache thay thế JIT hoặc native image.
- [ ] Đã chọn workload Training đại diện cho các lớp và luồng nghiệp vụ cần thiết.
- [ ] Đã hoàn tất đủ Training (`.aotconfig`), Assembly (`.aot`) và Production.
- [ ] Đã giữ JDK release, OS, CPU architecture và application classpath/module path tương thích.
- [ ] Đã giữ module options nhất quán và kiểm tra yêu cầu archived full module graph khi AOT class linking được bật.
- [ ] Đã kiểm tra agent, JVMTI, class transformation và JVM options có thể làm cache không tương thích.
- [ ] Đã dùng `-XX:AOTMode=auto` cho production nếu cần fallback an toàn.
- [ ] Đã dùng `-Xlog:aot` để xác minh cache thực sự được nạp.
- [ ] Đã đo cold start, warm start, time-to-readiness, warm-up và tài nguyên CPU/I/O.
- [ ] Nếu dùng ZGC, đã xác minh AOT object cache được nạp bằng định dạng GC-agnostic trên JDK 26 build triển khai.
- [ ] Đã có bước tạo lại cache khi JDK, JAR, OS, CPU hoặc module configuration thay đổi.

## Tài liệu tham khảo chính thức

- [JEP 483: Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483)
- [JEP 516: Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516)
- [Java SE 26 — The `java` Command, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Java SE 26 — Application Class Data Sharing](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html#application-class-data-sharing)
- [Significant Changes in JDK 26 Release](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html)
- [Consolidated JDK 26 Release Notes — JEP 516](https://www.oracle.com/java/technologies/javase/26all-relnotes.html)
- [Performance Improvements in JDK 26 — Inside.java](https://inside.java/2026/06/09/jdk-26-performance-improvements/)

*Cập nhật nội dung: 27-11-2026. JEP 516 là cải tiến đã tích hợp trong JDK 26, cho phép AOT object caching với mọi GC, gồm ZGC. Luôn tạo lại cache theo JDK release và môi trường triển khai thực tế.*
