# Bật UseCompactObjectHeaders và xác minh cấu hình JVM thực tế

## 1. Mục tiêu và bối cảnh phiên bản

Bài thuộc chương **Header đối tượng gọn** của module **JAVA_VERSION_JAVA25**. Java 25 mang đến Compact Object Headers qua **JEP 519**: HotSpot có thể giảm header của mỗi object từ 96 hoặc 128 bit xuống còn 64 bit trên kiến trúc 64-bit. Việc này giảm lượng heap cần dùng cho workload có nhiều object nhỏ, có thể cải thiện locality và giảm áp lực bộ nhớ.

Điểm cần nắm chính xác là trạng thái mặc định:

- **JDK 24:** Compact Object Headers còn là tính năng experimental theo JEP 450.
- **JDK 25:** JEP 519 đưa tính năng thành product option. Có thể bật bằng `-XX:+UseCompactObjectHeaders`, nhưng **mặc định vẫn tắt**. Không cần `-XX:+UnlockExperimentalVMOptions`.
- **JDK 27:** JEP 534 bật Compact Object Headers mặc định. Nếu cần điều tra tương thích, JDK 27 vẫn có thể tắt bằng `-XX:-UseCompactObjectHeaders`, nhưng hướng này được dự kiến deprecate và loại bỏ trong tương lai.

Bài tập trung vào cách cấu hình và xác minh trên **JDK 25**, đồng thời ghi rõ khác biệt của JDK 27 để tránh mang giả định về mặc định giữa các phiên bản. Đây là tùy chọn của **HotSpot JVM**, không phải một API Java mà chương trình có thể gọi.

Sau bài này, bạn có thể:

1. Giải thích object header gọn làm thay đổi điều gì trong heap.
2. Bật hoặc tắt `UseCompactObjectHeaders` bằng JVM option phù hợp với JDK 25.
3. Phân biệt giá trị mặc định với giá trị được đặt từ command line.
4. Xác minh giá trị thực tế của JVM đang chạy bằng `PrintFlagsFinal` và `jcmd`.
5. Phát hiện trường hợp kiểm tra nhầm Java executable, container hoặc service process.
6. Nhận diện giới hạn kiến trúc 64-bit và giới hạn số class.
7. Đánh giá ảnh hưởng tới memory footprint, GC, latency và throughput bằng workload có kiểm soát.
8. Tránh dùng các cờ experimental/deprecated từ hướng dẫn cũ.

## 2. Object header và lợi ích của layout gọn

### 2.1. Object header chứa gì?

Mỗi object do HotSpot quản lý đều có metadata nội bộ nằm ở đầu vùng nhớ object. Header chứa thông tin mà JVM cần để quản lý object, ví dụ:

- Thông tin nhận diện class.
- Trạng thái lock/monitor.
- Identity hash code khi được tạo.
- Metadata phục vụ garbage collector, chẳng hạn tuổi object hoặc trạng thái forwarding.

Mã Java thông thường làm việc với reference và object API. Chương trình không được dựa vào một bố cục byte cụ thể của header; bố cục này là chi tiết triển khai của JVM.

### 2.2. Compact Object Headers thay đổi điều gì?

Theo tài liệu Garbage Collection Tuning của Oracle JDK 25, header truyền thống có kích thước 96 hoặc 128 bit; khi bật compact header, kích thước được giảm xuống 64 bit trên kiến trúc 64-bit.

| Layout | Kích thước header | Ý nghĩa |
| --- | ---: | --- |
| Header truyền thống với compressed class pointer | 96 bit (12 byte) | Header gồm metadata object và class pointer nén |
| Header truyền thống không dùng compressed class pointer | 128 bit (16 byte) | Header chiếm nhiều byte hơn |
| Compact Object Header | 64 bit (8 byte) | Metadata được mã hóa trong header gọn |

Oracle ghi nhận mức giảm footprint heap trung bình khoảng **4 byte cho mỗi object**. Mức tiết kiệm thực tế phụ thuộc vào số object, loại object, alignment, layout field và đặc điểm workload. Không lấy phép nhân số object với 4 byte làm cam kết về dung lượng RSS hoặc heap sẽ giảm đúng bằng con số đó.

### 2.3. Workload nào có thể hưởng lợi?

Lợi ích thường đáng quan tâm ở ứng dụng giữ nhiều object nhỏ:

- Map, Set và cấu trúc collection có số lượng entry lớn.
- Object graph trong domain model.
- Cache trong heap chứa nhiều value object.
- Cây cú pháp, metadata hoặc cấu trúc biểu diễn đồ thị.
- Message/event payload được deserialize thành nhiều object.
- Ứng dụng tạo và giữ nhiều object nhỏ trong thời gian dài.

Nếu ứng dụng chủ yếu giữ vài mảng primitive lớn, byte buffer, direct memory hoặc dữ liệu off-heap, header object có thể chỉ chiếm phần nhỏ trong tổng footprint. Khi đó mức cải thiện có thể không đáng kể.

**Compact Object Headers không phải garbage collector mới.** Đây là thay đổi layout object trong HotSpot. Chọn G1, ZGC hoặc collector khác vẫn là quyết định riêng, dựa trên yêu cầu pause time, throughput và memory của ứng dụng.

## 3. Trạng thái flag theo phiên bản JDK

### 3.1. Bảng phiên bản

| JDK | Trạng thái Compact Object Headers | Cách cấu hình |
| --- | --- | --- |
| 24 | Experimental (JEP 450) | Cách bật experimental thuộc phiên bản cũ; không dùng làm hướng dẫn cho JDK 25 |
| 25 | Product option (JEP 519), mặc định tắt | Bật bằng `-XX:+UseCompactObjectHeaders` |
| 27 | Bật mặc định (JEP 534) | Không cần cờ bật; `-XX:-UseCompactObjectHeaders` có thể tắt trong giai đoạn chuyển tiếp |

### 3.2. JDK 25: product option nhưng mặc định tắt

JEP 519 thay đổi trạng thái flag từ experimental thành product option. Điều đó có nghĩa người dùng JDK 25 có thể bật trực tiếp:

~~~bash
java -XX:+UseCompactObjectHeaders -jar app.jar
~~~

Không cần thêm:

~~~text
-XX:+UnlockExperimentalVMOptions
~~~

Tùy chọn `-XX:+UseCompactObjectHeaders` **không tự bật chỉ vì JVM là Java 25**. Oracle JDK 25 ghi rõ mặc định của nó là `disabled`. Vì vậy, nếu muốn dùng layout gọn trên JDK 25, hãy đặt cờ trong cấu hình khởi chạy của đúng JVM process.

Có thể chủ động tắt trong một lần thử nghiệm bằng:

~~~bash
java -XX:-UseCompactObjectHeaders -jar app.jar
~~~

Trên JDK 25, lệnh này giúp tạo baseline truyền thống để so sánh. Trong production, chỉ duy trì cấu hình tắt nếu phép đo và yêu cầu tương thích chứng minh điều đó cần thiết.

### 3.3. Cập nhật hiện hành: JDK 27 đã đổi mặc định

JEP 534 trong JDK 27 bật Compact Object Headers mặc định. Điều này quan trọng khi ứng dụng nâng từ JDK 25 lên JDK 27:

- JDK 25 không có flag tường minh thì mặc định `false`.
- JDK 27 không có flag tường minh thì mặc định `true`.
- Một JVM argument cũ `-XX:-UseCompactObjectHeaders` có thể làm JDK 27 tiếp tục dùng layout cũ, dù mặc định phiên bản mới đã bật.

Khi nâng cấp JDK, hãy kiểm tra các JVM options trong Dockerfile, Helm chart, systemd service, script startup và biến môi trường. Đừng giả định một process dùng cùng layout chỉ vì source code và ứng dụng không đổi.

## 4. Bật Compact Object Headers trên JDK 25

### 4.1. Chạy ứng dụng JAR

Lệnh cơ bản:

~~~bash
java -XX:+UseCompactObjectHeaders -jar app.jar
~~~

Có thể đặt cùng các JVM option khác:

~~~bash
java -Xms1g -Xmx2g -XX:+UseCompactObjectHeaders -jar app.jar
~~~

JVM options phải đứng trước `-jar` và tên JAR. Các tham số sau tên JAR được truyền cho ứng dụng, không còn là JVM options.

### 4.2. Chạy main class với classpath

~~~bash
java -XX:+UseCompactObjectHeaders -cp "app.jar:lib/*" com.acme.Application
~~~

Ví dụ trên dùng dấu `:` của Linux/macOS. Trên Windows, classpath dùng dấu `;`:

~~~powershell
java -XX:+UseCompactObjectHeaders -cp "app.jar;lib/*" com.acme.Application
~~~

Hãy giữ classpath và các JVM options đúng như cấu hình thực tế của ứng dụng. Một lệnh kiểm tra đơn giản không có cùng agent, container hoặc service wrapper chưa chắc phản ánh cấu hình của process production.

### 4.3. Docker và container

Có thể truyền cờ trong `ENTRYPOINT`:

~~~dockerfile
ENTRYPOINT ["java", "-XX:+UseCompactObjectHeaders", "-jar", "/app/app.jar"]
~~~

Hoặc truyền qua biến môi trường JVM options mà image/entrypoint đang hỗ trợ. Ví dụ một số image dùng `JAVA_TOOL_OPTIONS`:

~~~dockerfile
ENV JAVA_TOOL_OPTIONS="-XX:+UseCompactObjectHeaders"
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Không mặc định mọi image đều sử dụng cùng cơ chế biến môi trường. Hãy xem entrypoint của image, log startup và xác minh trên process đang chạy. `JAVA_TOOL_OPTIONS` có thể được áp dụng ngầm bởi runtime/container, nên cần kiểm tra giá trị thực tế thay vì chỉ đọc Dockerfile.

### 4.4. Không trộn flag của JDK 24 vào cấu hình JDK 25

Một số hướng dẫn cũ cho JDK 24 có cặp flag:

~~~text
-XX:+UnlockExperimentalVMOptions
-XX:+UseCompactObjectHeaders
~~~

Từ JDK 25, `UseCompactObjectHeaders` là product option. Cấu hình mới chỉ cần:

~~~text
-XX:+UseCompactObjectHeaders
~~~

Giữ `UnlockExperimentalVMOptions` trong script chỉ để bật compact header không còn cần thiết. Tránh sao chép nguyên lệnh từ tài liệu preview/experimental cũ.

## 5. Xác minh flag trước khi khởi chạy ứng dụng

### 5.1. Kiểm tra JDK và kiến trúc đang dùng

Trước tiên xác minh binary `java` trong terminal:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Trong phần properties, kiểm tra:

- `java.version`: phiên bản Java runtime.
- `java.vendor`: nhà cung cấp runtime.
- `os.arch`: kiến trúc hệ điều hành.
- `sun.arch.data.model`: độ rộng dữ liệu của JVM nếu runtime hiển thị thuộc tính này.

Compact Object Headers của HotSpot yêu cầu JVM 64-bit. Đừng chỉ kiểm tra phiên bản compiler `javac`; process chạy ứng dụng có thể dùng một JDK/JRE khác.

### 5.2. Dùng PrintFlagsFinal để xem giá trị flag

Khởi chạy một JVM thử nghiệm với cờ bật và in toàn bộ flag cuối cùng:

~~~bash
java -XX:+UseCompactObjectHeaders -XX:+PrintFlagsFinal -version
~~~

Tìm dòng:

~~~text
bool UseCompactObjectHeaders = true {product} {command line}
~~~

Kết quả cho thấy JVM nhận flag và giá trị cuối cùng là `true`; phần `{command line}` chỉ ra giá trị đến từ tham số khởi chạy.

Để xem mặc định của JDK 25 trong một JVM mới không truyền flag:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Dòng tương ứng thường có dạng:

~~~text
bool UseCompactObjectHeaders = false {product} {default}
~~~

Hai lệnh này tạo JVM mới để kiểm tra. Chúng không đọc trạng thái của một service process đang chạy.

Trên Linux/macOS có thể lọc dòng cần xem:

~~~bash
java -XX:+UseCompactObjectHeaders -XX:+PrintFlagsFinal -version 2>&1 | grep UseCompactObjectHeaders
~~~

Trên PowerShell:

~~~powershell
java -XX:+UseCompactObjectHeaders -XX:+PrintFlagsFinal -version 2>&1 |
  Select-String UseCompactObjectHeaders
~~~

### 5.3. Phân biệt giá trị và nguồn cấu hình

Ví dụ:

~~~text
bool UseCompactObjectHeaders = true {product} {command line}
~~~

Có thể đọc như sau:

- `bool`: flag kiểu boolean.
- `UseCompactObjectHeaders`: tên flag.
- `true`: giá trị hiệu lực của JVM được kiểm tra.
- `{product}`: flag thuộc nhóm product option.
- `{command line}`: giá trị được đặt từ tham số khởi chạy.

Nếu thấy:

~~~text
bool UseCompactObjectHeaders = false {product} {default}
~~~

thì JVM đang kiểm tra không nhận cờ bật và dùng mặc định tắt của JDK 25.

Nếu kết quả cho thấy giá trị không như mong đợi, hãy kiểm tra lại Java binary, JVM options và launcher trước khi sửa ứng dụng.

## 6. Xác minh cấu hình của JVM process đang chạy

Đây là bước quan trọng nhất khi ứng dụng được khởi chạy qua service manager, container, Kubernetes, IDE hoặc script wrapper.

### 6.1. Tìm đúng process

~~~bash
jcmd -l
~~~

Lệnh liệt kê các JVM process mà user hiện tại có thể attach. Xác định PID của đúng ứng dụng, không lấy nhầm PID của build tool, sidecar hoặc một JVM khác.

### 6.2. Xem flag hiện tại bằng jcmd

~~~bash
jcmd <pid> VM.flags -all
~~~

Tìm dòng `UseCompactObjectHeaders`. Ví dụ:

~~~text
bool UseCompactObjectHeaders = true {product} {command line}
~~~

Trên Windows PowerShell:

~~~powershell
jcmd <pid> VM.flags -all |
  Select-String UseCompactObjectHeaders
~~~

Trên Linux/macOS:

~~~bash
jcmd <pid> VM.flags -all | grep UseCompactObjectHeaders
~~~

`VM.flags` in các flag và giá trị hiện tại của JVM process được chỉ định. Tùy chọn `-all` yêu cầu in cả các flag hỗ trợ bởi VM.

### 6.3. Xem command line thực tế

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.version
~~~

Dùng kết hợp:

- `VM.command_line`: kiểm tra command line đã dùng để khởi chạy process.
- `VM.version`: xác nhận phiên bản HotSpot/JDK của process.
- `VM.flags -all`: kiểm tra giá trị flag hiện tại.

`VM.command_line` cho biết các tham số khởi chạy nhưng không thay thế việc đọc giá trị hiệu lực. `VM.flags -all` là bước xác nhận trực tiếp flag đang có giá trị nào.

### 6.4. jcmd không attach được

Nếu không tìm thấy process hoặc không thể attach:

1. Xác minh PID thuộc đúng JVM.
2. Chạy `jcmd` trên cùng máy/container host theo điều kiện attach của runtime.
3. Dùng user có quyền phù hợp với user chạy JVM.
4. Dùng bộ công cụ JDK tương ứng với JVM đang chạy.
5. Kiểm tra process có tắt attach mechanism hay chạy trong môi trường bị giới hạn hay không.

Trong container, PID namespace có thể khiến PID nhìn thấy từ host khác PID nhìn thấy bên trong container. Chạy `jcmd -l` ở đúng namespace hoặc dùng công cụ quan sát phù hợp với môi trường triển khai.

### 6.5. Không đổi object layout giữa lúc process đang chạy

`UseCompactObjectHeaders` quyết định layout object khi JVM khởi động. Không thể đổi layout an toàn bằng cách sửa biến môi trường hoặc chạy một lệnh `jcmd` sau khi ứng dụng đã khởi động. Hãy đặt flag trong startup options rồi restart process có kiểm soát.

## 7. Những giới hạn cần kiểm tra trước khi bật

### 7.1. JVM 64-bit

Compact Object Headers được thiết kế cho HotSpot 64-bit. Kiểm tra kiến trúc runtime thực tế, không suy ra từ kiến trúc CPU của máy host nếu ứng dụng chạy trong container hoặc image khác.

### 7.2. Giới hạn số class

Oracle JDK 25 GC Tuning Guide nêu rằng khi bật Compact Object Headers, JVM có giới hạn khoảng **4 triệu class khác nhau được load**. Đây là giới hạn rất cao với phần lớn ứng dụng, nhưng cần lưu ý với ứng dụng có plugin/classloader động quy mô lớn.

Nếu hệ thống có số lượng class tăng bất thường:

- Kiểm tra số class và classloader theo thời gian.
- Điều tra classloader leak.
- Xem xét plugin hoặc module được load lặp lại.
- Không bật compact header nếu workload thực tế có thể vượt giới hạn này.

Một hệ thống load rất nhiều class thường cần điều tra vòng đời classloader trước khi xem object header là nút thắt.

### 7.3. Compressed class pointers và flag đã deprecated

JDK 25 đã deprecate `UseCompressedClassPointers`. Chế độ compressed class pointer là mặc định; tùy chọn này được giữ lại trong giai đoạn chuyển tiếp và sẽ bị loại bỏ ở phiên bản sau.

Vì vậy:

- Không thêm `-XX:+UseCompressedClassPointers` chỉ để bật compact header.
- Không dùng `-XX:-UseCompressedClassPointers` để thử một layout cũ.
- Không xây hướng dẫn mới dựa trên việc tắt compressed class pointers.

JDK 27 đã loại bỏ tùy chọn `UseCompressedClassPointers`. Hãy xóa các JVM arguments cũ này khỏi script/container khi nâng cấp.

### 7.4. Native agent và công cụ phụ thuộc layout nội bộ

Ứng dụng Java thông thường không cần thay đổi source code để dùng Compact Object Headers. Tuy nhiên, cần kiểm tra các thành phần phụ thuộc vào chi tiết nội bộ của HotSpot, ví dụ:

- Native/JVMTI agent đọc trực tiếp vùng nhớ object.
- Công cụ debug/diagnostic giả định kích thước header cố định.
- Thư viện dùng internal API hoặc hard-coded offset thay vì hỏi JVM.
- Mã native tự diễn giải object reference hoặc object metadata.

Đây không phải hợp đồng của Java platform. Hãy dùng phiên bản agent/thư viện có hỗ trợ JDK đích và kiểm thử với flag bật trong staging.

### 7.5. CDS và startup

JDK 25 cung cấp các CDS archive tương ứng cho cấu hình compact object headers, gồm `classes_coh.jsa` và `classes_nocoops_coh.jsa`, nhằm hỗ trợ startup tương đương khi dùng layout này.

Nếu ứng dụng dùng custom runtime image hoặc CDS archive tự tạo, hãy kiểm tra cách archive được tạo và cấu hình JVM. Đừng mặc định một archive do pipeline cũ tạo ra sẽ đại diện đúng cho mọi tổ hợp flag.

## 8. Đánh giá tác động bằng benchmark có kiểm soát

### 8.1. Đừng kết luận chỉ từ việc flag đã bật

Giá trị `true` chứng minh JVM đang dùng cấu hình được yêu cầu. Nó không chứng minh ứng dụng đã giảm heap hoặc tăng throughput theo một tỷ lệ cố định.

Mức cải thiện phụ thuộc:

- Số object sống trong heap.
- Kích thước và phân bố object.
- Alignment và layout field.
- Tỷ lệ object ngắn hạn so với object sống lâu.
- GC, heap size, allocation rate và workload.
- CPU cache locality và hành vi truy cập dữ liệu.

### 8.2. Thiết lập hai lần chạy A/B

Chạy cùng một artifact trên cùng JDK 25 build và cùng môi trường.

**Baseline — header truyền thống:**

~~~bash
java -Xms2g -Xmx2g -XX:-UseCompactObjectHeaders -Xlog:gc*:file=gc-baseline.log:time,uptime,level,tags -jar app.jar
~~~

**Candidate — compact header:**

~~~bash
java -Xms2g -Xmx2g -XX:+UseCompactObjectHeaders -Xlog:gc*:file=gc-compact.log:time,uptime,level,tags -jar app.jar
~~~

Dùng `-XX:-UseCompactObjectHeaders` làm baseline chỉ trong JDK 25, nơi mặc định vốn tắt. Trên JDK 27, compact header bật mặc định; nếu tạo baseline tắt để điều tra, ghi rõ đây là cấu hình đối chứng và không để cờ tắt sót lại trong production.

Giữ giống nhau:

- JDK vendor, version/build.
- Artifact và dependency.
- Heap size và GC.
- JVM options còn lại.
- Container memory/CPU limit.
- Dataset, traffic profile và thời lượng chạy.
- Warm-up và số lần lặp.

### 8.3. Chỉ số cần so sánh

| Chỉ số | Mục đích | Cách diễn giải |
| --- | --- | --- |
| Live set / heap used sau các chu kỳ GC tương đương | Xem lượng dữ liệu Java còn sống | So cùng workload và cùng thời điểm |
| Heap occupancy | Xem áp lực sử dụng heap | Đừng so hai lần chạy có heap size khác nhau |
| GC frequency và pause | Xem tác động gián tiếp lên GC | Không mặc định ít heap hơn luôn đồng nghĩa pause thấp hơn |
| Allocation rate | Xem tốc độ tạo object | Có thể giữ gần như giống nhau dù header nhỏ hơn |
| Startup time | Xem tác động khởi động | Tách JVM startup khỏi kết nối dịch vụ ngoài |
| Throughput và p95/p99 latency | Đánh giá KPI ứng dụng | Lặp lại nhiều lần, tránh kết luận từ một run |
| RSS/process memory | Xem footprint toàn process | Không đồng nhất RSS với Java heap |

Compact headers giảm kích thước object trong Java heap. Nó không trực tiếp giảm direct buffer, native allocation, thread stack, metaspace hoặc code cache.

### 8.4. Công cụ quan sát

Bật GC log:

~~~bash
-Xlog:gc*:file=gc.log:time,uptime,level,tags
~~~

Dùng `jcmd` xem histogram trong môi trường kiểm thử:

~~~bash
jcmd <pid> GC.class_histogram
~~~

Class histogram giúp xem class nào đang giữ nhiều instance và dung lượng heap, nhưng bản thân nó không đo trực tiếp byte header tiết kiệm trên từng object. Lệnh có thể có chi phí phụ thuộc heap và nội dung, nên chọn thời điểm phù hợp.

Nếu cần kiểm tra layout object cụ thể, có thể dùng Java Object Layout (JOL) trong một chương trình chẩn đoán riêng, chạy với cùng JDK và cùng JVM flags. JOL là công cụ quan sát layout triển khai, không phải API chuẩn để ứng dụng phụ thuộc vào.

### 8.5. Ví dụ cách diễn giải kết quả

Giả sử candidate giảm live heap sau GC nhưng throughput không đổi:

- Có thể ứng dụng được lợi về dung lượng heap và deployment density.
- Không có bằng chứng rằng CPU path đã nhanh hơn.
- Nếu GC pause hoặc tail latency không thay đổi, đừng tuyên bố hiệu năng đã cải thiện chỉ từ heap.

Nếu throughput giảm nhẹ nhưng live heap thấp hơn, cần chạy thêm nhiều lần và xem allocation, cache locality, GC, JIT và nhiễu môi trường trước khi quyết định. Một phép đo đơn lẻ không đủ để loại bỏ hoặc chấp nhận tính năng.

## 9. Chẩn đoán khi flag không hoạt động như mong đợi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Unrecognized VM option 'UseCompactObjectHeaders'` | Runtime không phải HotSpot JDK phù hợp hoặc phiên bản quá cũ | Kiểm tra `java -version`, vendor và binary thực tế |
| JVM báo flag chỉ có trên LP64/64-bit | Đang dùng JVM 32-bit | Chuyển sang runtime 64-bit được hỗ trợ |
| PrintFlagsFinal cho `false` | Không truyền flag, bị wrapper bỏ qua hoặc dùng JVM process khác | Kiểm tra command line và `jcmd <pid> VM.flags -all` |
| Terminal cho `true`, service cho `false` | Terminal và service dùng JDK/options khác nhau | Kiểm tra PID, service config, container entrypoint và JAVA_TOOL_OPTIONS |
| Process production không nhận thay đổi sau khi sửa env | Flag được đọc lúc JVM startup | Restart process theo quy trình triển khai |
| Ứng dụng có lỗi với agent/native library khi bật | Thành phần phụ thuộc layout nội bộ hoặc chưa tương thích | Nâng phiên bản agent/library và kiểm thử riêng |
| Lợi ích heap không đáng kể | Workload không object-dense hoặc phần heap object header không chiếm tỷ lệ lớn | Đo live set và số object trước khi tiếp tục |
| Không thể bật do class count cao | Ứng dụng tiến gần giới hạn class của compact header | Điều tra classloader, plugin và class unloading |

### 9.1. Quy trình xử lý từng bước

1. Chạy `java -version` và xác nhận đây là HotSpot JDK 25 64-bit.
2. Chạy một JVM thử với `-XX:+UseCompactObjectHeaders -XX:+PrintFlagsFinal -version`.
3. Khởi động ứng dụng bằng đúng flag.
4. Dùng `jcmd -l` xác định PID.
5. Chạy `jcmd <pid> VM.version`, `VM.command_line` và `VM.flags -all`.
6. Xác nhận `UseCompactObjectHeaders = true`.
7. Chạy workload staging và thu GC log.
8. So sánh với baseline tắt flag trong cùng điều kiện.
9. Kiểm tra native/JVMTI agents và classloader nếu có lỗi hoặc giới hạn.
10. Chỉ đưa cấu hình vào production sau khi xác minh KPI và khả năng tương thích.

## 10. Quy trình triển khai an toàn

### Trước khi thay đổi

- [ ] Xác nhận JDK vendor/version/build của process.
- [ ] Xác nhận JVM 64-bit.
- [ ] Kiểm tra classloader và số class được load nếu ứng dụng đặc thù.
- [ ] Kiểm kê Java agent, native/JVMTI agent và công cụ instrumentation.
- [ ] Xác định baseline heap, GC, latency và throughput.

### Khi bật trên JDK 25

- [ ] Thêm `-XX:+UseCompactObjectHeaders` trước `-jar` hoặc main class.
- [ ] Không thêm `-XX:+UnlockExperimentalVMOptions`.
- [ ] Không thêm `UseCompressedClassPointers` đã deprecated.
- [ ] Restart JVM để áp dụng layout mới.
- [ ] Xác minh bằng `jcmd <pid> VM.flags -all`.

### Sau khi bật

- [ ] Chạy smoke test và regression test.
- [ ] Kiểm tra các luồng dùng native/JVMTI agent.
- [ ] Đo live heap, GC, throughput và latency.
- [ ] So sánh với baseline cùng điều kiện.
- [ ] Ghi JDK build và JVM arguments vào metadata triển khai.
- [ ] Kiểm tra lại mặc định khi nâng JDK 27 trở lên.

## 11. Bài thực hành tổng hợp

**Tình huống:** một dịch vụ Java 25 giữ nhiều object nhỏ trong cache và domain model. Nhóm vận hành muốn giảm heap nhưng cần xác minh JVM thực tế đã dùng compact headers.

### Phần A — Xác minh baseline

1. Chạy `java -version`.
2. Kiểm tra `os.arch` và `sun.arch.data.model`.
3. Chạy `java -XX:+PrintFlagsFinal -version`.
4. Ghi lại giá trị `UseCompactObjectHeaders`.
5. Khởi chạy service chưa bật flag và xác minh process bằng `jcmd`.

**Đạt** khi phân biệt được mặc định của JDK 25 với cấu hình của service process.

### Phần B — Bật flag

1. Thêm `-XX:+UseCompactObjectHeaders` vào startup command.
2. Restart service.
3. Dùng `jcmd -l` tìm PID.
4. Chạy `jcmd <pid> VM.flags -all`.
5. Chạy `jcmd <pid> VM.command_line`.
6. Xác nhận flag có giá trị `true`.

**Đạt** khi có bằng chứng từ đúng JVM process, không chỉ từ một lệnh `java -version` riêng.

### Phần C — Đo tác động

1. Chạy baseline với `-XX:-UseCompactObjectHeaders`.
2. Chạy candidate với `-XX:+UseCompactObjectHeaders`.
3. Giữ cùng heap, GC, artifact, dataset và traffic.
4. Thu GC log, live heap và latency.
5. So sánh nhiều lần chạy.
6. Ghi nhận lợi ích, giới hạn và rủi ro.

**Đạt** khi kết luận dựa trên số liệu và không mặc định heap sẽ giảm đúng 4 byte nhân với mọi object.

### Phần D — Đánh giá nâng cấp JDK

1. Chạy cùng ứng dụng trên JDK 25.
2. Kiểm tra default flag và startup options.
3. Khi nâng lên JDK 27, kiểm tra JEP 534 và giá trị mặc định mới.
4. Tìm các cờ `-XX:-UseCompactObjectHeaders` còn sót trong script.
5. Ghi rõ cấu hình mong muốn sau nâng cấp.

**Đạt** khi giải thích được vì sao JDK 25 cần bật tường minh còn JDK 27 đã bật mặc định.

## 12. Câu hỏi tự đánh giá

1. JEP nào đưa Compact Object Headers thành product option trong JDK 25?
2. JDK 25 mặc định bật hay tắt `UseCompactObjectHeaders`?
3. Vì sao JDK 25 không cần `-XX:+UnlockExperimentalVMOptions`?
4. Object header truyền thống có kích thước bao nhiêu bit và compact header còn bao nhiêu bit?
5. Vì sao mức giảm trung bình 4 byte/object không đồng nghĩa RSS giảm chính xác theo phép nhân?
6. Workload nào có khả năng hưởng lợi nhiều từ compact headers?
7. Compact Object Headers có thay thế garbage collector không?
8. JVM architecture nào cần để dùng compact headers?
9. Giới hạn số class được load theo Oracle JDK 25 GC Tuning Guide là bao nhiêu?
10. Vì sao không nên dùng `UseCompressedClassPointers` làm workaround trong JDK 25?
11. `PrintFlagsFinal` giúp phân biệt giá trị mặc định và giá trị từ command line như thế nào?
12. Vì sao `java -XX:+PrintFlagsFinal -version` không đủ để xác minh service process?
13. `jcmd <pid> VM.flags -all` cung cấp bằng chứng gì?
14. Khi nào cần xem `VM.command_line` và `VM.version`?
15. Vì sao phải restart process sau khi thay đổi `UseCompactObjectHeaders`?
16. Native/JVMTI agent có thể cần kiểm tra gì khi thay đổi layout object?
17. Tại sao không nên xem class histogram là phép đo trực tiếp byte header tiết kiệm?
18. Cần giữ những điều kiện nào giống nhau trong benchmark A/B?
19. JDK 27 thay đổi mặc định Compact Object Headers ra sao?
20. Khi nâng từ JDK 25 lên JDK 27, cần rà soát những JVM options nào?

## 13. Tài liệu tham khảo

- [OpenJDK JEP 519 — Compact Object Headers](https://openjdk.org/jeps/519): trạng thái product option và mục tiêu của Compact Object Headers trong JDK 25.
- [OpenJDK JEP 450 — Compact Object Headers (Experimental)](https://openjdk.org/jeps/450): bối cảnh thử nghiệm ban đầu trong JDK 24.
- [Oracle JDK 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): mô tả `-XX:+UseCompactObjectHeaders`, mặc định tắt và mức giảm footprint trung bình.
- [Oracle JDK 25 — Garbage Collection Tuning Guide, Other Considerations](https://docs.oracle.com/en/java/javase/25/gctuning/other-considerations.html): kích thước header 96/128 bit xuống 64 bit và giới hạn 4 triệu class.
- [Oracle JDK 25 — Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/25all-relnotes.html): JEP 519 là product option; `UseCompressedClassPointers` đã deprecated trong JDK 25.
- [Oracle JDK 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `VM.flags`, `VM.command_line`, `VM.version` và các công cụ xác minh JVM đang chạy.
- [Oracle JDK 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): cách dùng `jcmd` để kiểm tra process và flag.
- [OpenJDK JEP 534 — Compact Object Headers by Default](https://openjdk.org/jeps/534): thay đổi mặc định ở JDK 27.
- [Inside Java — JDK 27 Runtime Updates](https://inside.java/2026/09/12/jdk-27-runtime-updates/): Compact Object Headers được bật mặc định trong JDK 27.

