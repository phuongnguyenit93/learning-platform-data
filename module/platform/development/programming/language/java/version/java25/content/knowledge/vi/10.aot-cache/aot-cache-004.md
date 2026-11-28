# Cấu hình JVM sử dụng cache và kiểm tra cache được nạp thành công

## Mục tiêu bài học

**Ahead-of-Time Cache (AOT cache)** của HotSpot JVM lưu lại một số dữ liệu được chuẩn bị trước khi ứng dụng chạy, nhằm giảm công việc phải làm trong giai đoạn khởi động và warm-up. Thay vì để mỗi process luôn bắt đầu từ đầu với việc đọc, phân tích, nạp và liên kết lớp, JVM có thể tái sử dụng các dữ liệu đã được tạo trong một lần chạy huấn luyện phù hợp.

Trong Java 25, AOT cache có hai cải tiến đáng chú ý:

- **JEP 514 — Ahead-of-Time Command-Line Ergonomics:** đơn giản hóa quá trình tạo cache bằng một lệnh `-XX:AOTCacheOutput=...`; JVM tự thực hiện giai đoạn huấn luyện và bước tạo cache tiếp theo.
- **JEP 515 — Ahead-of-Time Method Profiling:** đưa thông tin profiling phương thức từ lần huấn luyện vào cache, giúp JIT có dữ liệu sớm hơn để bắt đầu tối ưu mã nóng khi ứng dụng khởi động.

Bài **Cấu hình JVM sử dụng cache và kiểm tra cache được nạp thành công** thuộc chương **AOT cache** của module **JAVA_VERSION_JAVA25**. Nội dung tập trung vào cách tạo cache, cấu hình JVM ở lần chạy production, kiểm tra cache có được sử dụng và xử lý khi cache không tương thích.

Sau bài học, bạn có thể:

1. Phân biệt AOT cache với Spring AOT processing, Class Data Sharing (CDS) và GraalVM Native Image.
2. Tạo AOT cache bằng workflow một lệnh của Java 25 hoặc workflow tách riêng training và assembly.
3. Cấu hình `-XX:AOTCache`, `-XX:AOTMode` và các tùy chọn chẩn đoán đúng mục đích.
4. Chuẩn bị workload huấn luyện đại diện cho ứng dụng production.
5. Xác minh cache được nạp bằng unified logging và chế độ fail-fast.
6. Nhận diện nguyên nhân cache bị bỏ qua, không tương thích hoặc không mang lại cải thiện hiệu năng.
7. Đánh giá các khác biệt giữa Java 25 và JDK 26 để không áp dụng nhầm giới hạn phiên bản cũ.

> **Phiên bản:** các lệnh chính trong bài dùng HotSpot JDK 25. AOT cache được giới thiệu từ JDK 24; Java 25 bổ sung one-command workflow và method profiling. Tính đến JDK 26, JEP 516 mở rộng khả năng cache object sang mọi garbage collector, bao gồm ZGC. Cache vẫn gắn với ứng dụng, JDK và nền tảng tạo ra nó; không dùng file cache của JDK 25 như một artifact dùng chung cho JDK 26.

## 1. AOT cache giải quyết vấn đề gì?

Khi khởi động một ứng dụng Java, JVM phải thực hiện nhiều công việc trước khi request đầu tiên được xử lý ổn định:

- Đọc class từ JAR hoặc module path.
- Parse bytecode, tạo metadata và nạp lớp.
- Liên kết lớp, phân giải tham chiếu và khởi tạo những lớp cần thiết.
- Tạo các đối tượng ban đầu của runtime và framework.
- Thu thập thông tin thực thi để JIT nhận biết phương thức nóng và tối ưu mã.

Với một ứng dụng Spring Boot có nhiều thư viện, bước khởi động có thể nạp hàng nghìn lớp và tạo nhiều đối tượng framework. AOT cache giúp chuyển một phần công việc này sang giai đoạn trước khi deploy.

~~~mermaid
flowchart LR
    subgraph Training["Training — JDK 25"]
        APP1["Chạy ứng dụng<br/>với workload đại diện"] --> OBS["Ghi nhận class loading,<br/>heap objects và method profiles"]
        OBS --> CACHE["Assembly<br/>tạo app.aot"]
    end
    subgraph Production["Production"]
        CACHE --> JVM["JVM khởi động<br/>-XX:AOTCache=app.aot"]
        JVM --> REUSE["Tái sử dụng dữ liệu<br/>đã chuẩn bị"]
        REUSE --> JIT["JIT tiếp tục tối ưu<br/>theo workload thực"]
    end
~~~

AOT cache không thay thế JVM và không biến ứng dụng thành native executable. Ứng dụng vẫn chạy trên HotSpot, vẫn sử dụng bytecode và JIT. Với Java 25, method profiles trong cache giúp JIT có thông tin về những phương thức thường được gọi ngay từ đầu, thay vì phải chờ toàn bộ profiling được thu thập lại sau khi process mới khởi chạy.

### 1.1. Phân biệt bốn khái niệm

| Cơ chế | Vai trò | Đầu ra chính | Khi nào dùng |
|---|---|---|---|
| **JVM AOT cache** | Tái sử dụng dữ liệu class/object và method profiles đã thu thập trước | File `.aot` | Cải thiện startup và warm-up của HotSpot |
| **CDS / AppCDS** | Chia sẻ dữ liệu lớp đã chuẩn bị giữa các lần chạy/process | Archive `.jsa` | Chia sẻ class metadata và giảm công việc nạp lớp |
| **Spring AOT processing** | Phân tích application context và sinh code/hint ở build time | Source/class sinh ra theo quy trình Spring | Tối ưu cấu hình và khởi tạo Spring trong môi trường phù hợp |
| **GraalVM Native Image** | Biên dịch ứng dụng và dependency thành native executable | File thực thi native | Triển khai native runtime với mô hình và giới hạn riêng |

Các cơ chế có thể phối hợp trong một chiến lược tối ưu, nhưng không đồng nghĩa với nhau. Ví dụ, bật Spring AOT processing không tự tạo file `.aot` của HotSpot; có file `.aot` cũng không có nghĩa ứng dụng đã được biên dịch thành native executable.

## 2. Các mốc AOT cache liên quan đến Java 25

AOT cache phát triển qua nhiều phiên bản. Khi đọc hướng dẫn hoặc vận hành ứng dụng, cần phân biệt khả năng của JDK tạo cache với khả năng của JDK đang sử dụng cache.

| Phiên bản | Thay đổi | Ý nghĩa |
|---|---|---|
| **JDK 24 — JEP 483** | Ahead-of-Time Class Loading & Linking | Đưa AOT cache vào HotSpot; hỗ trợ cache dữ liệu lớp và object để cải thiện startup |
| **JDK 25 — JEP 514** | Ahead-of-Time Command-Line Ergonomics | Đơn giản hóa tạo cache bằng `-XX:AOTCacheOutput` |
| **JDK 25 — JEP 515** | Ahead-of-Time Method Profiling | Ghi method profiles vào AOT cache để JIT có dữ liệu tối ưu sớm |
| **JDK 26 — JEP 516** | Ahead-of-Time Object Caching with Any GC | Mở rộng AOT object caching cho mọi GC, gồm ZGC |

Đối với nội dung Java 25:

- Có thể dùng một lệnh để training và assembly.
- Có thể lưu method profiles trong cache để hỗ trợ warm-up.
- AOT object caching của JDK 25 còn có giới hạn liên quan đến ZGC.
- Nếu triển khai bằng JDK 26, cần tạo lại cache bằng đúng JDK 26 và có thể sử dụng cải tiến JEP 516.

Không lấy giới hạn của Java 25 áp dụng cho JDK 26. Ngược lại, cũng không dùng cache tạo bởi JDK 26 cho process chạy JDK 25.

## 3. Vòng đời của AOT cache

Quy trình logic có ba giai đoạn:

1. **Training:** chạy ứng dụng với workload đại diện để JVM quan sát lớp được nạp, object được khởi tạo và phương thức thường được thực thi.
2. **Assembly:** chuyển dữ liệu training thành file AOT cache.
3. **Production:** khởi chạy ứng dụng với file cache để JVM tái sử dụng dữ liệu đã chuẩn bị.

JEP 514 giúp gom thao tác training và assembly thành một lệnh, nhưng hai công việc vẫn diễn ra bên trong. Với ứng dụng chạy liên tục, có thể dùng `jcmd` để kết thúc một phiên training đúng lúc và yêu cầu JVM ghi kết quả.

### 3.1. Training cần đại diện cho production

AOT cache chỉ hữu ích nếu lần huấn luyện quan sát được những đường chạy sẽ xuất hiện khi triển khai:

- Đường khởi động bình thường của ứng dụng.
- Những controller/service được sử dụng thường xuyên.
- Các loại request đại diện cho workload thực tế.
- Những framework, serializer, driver và client được sử dụng.
- Các phương thức nóng mà JIT cần tối ưu sớm.

Nếu training chỉ khởi động Spring context rồi thoát ngay, cache có thể hỗ trợ startup nhưng không có đủ method profiles cho các luồng nghiệp vụ. Nếu training chạy toàn bộ test suite với rất nhiều mock/framework không có ở production, cache có thể chứa thêm lớp không cần thiết.

**Nguyên tắc:** chọn một workload đủ đại diện, không cần chạy toàn bộ tải cực đại hoặc stress test trong giai đoạn training.

### 3.2. Cache gắn với ứng dụng và nền tảng

AOT cache được tạo cho một tổ hợp cụ thể:

- Ứng dụng, được nhận diện qua classpath, JAR hoặc module path.
- Phiên bản JDK.
- Hệ điều hành và kiến trúc CPU.

Nếu một trong các thành phần này thay đổi, cần tạo cache mới. Khi cập nhật JAR, thêm dependency hoặc đổi JDK, không tái sử dụng cache cũ như thể nó vẫn hợp lệ.

## 4. Tạo cache bằng một lệnh trong Java 25

Đây là workflow thuận tiện nhất theo JEP 514.

Giả sử ứng dụng đã được đóng gói thành `app.jar` và có main class `com.example.App`. Chạy workload training:

~~~bash
java -XX:AOTCacheOutput=app.aot \
     -cp app.jar \
     com.example.App
~~~

JVM sẽ:

1. Khởi chạy ứng dụng trong chế độ training.
2. Thu thập dữ liệu trong lúc workload chạy.
3. Khi training kết thúc, khởi chạy một JVM phụ để assembly.
4. Ghi cache vào file `app.aot`.

Không cần truyền thêm `-XX:AOTMode=record` trong trường hợp sử dụng workflow tự động mặc định này. Khi có `-XX:AOTCacheOutput`, AOT mode mặc định `auto` chuyển sang training/record và thực hiện bước assembly tiếp theo.

### 4.1. Chạy workload có thời hạn

Nếu ứng dụng là một chương trình CLI hoặc integration test runner có thể kết thúc sau khi workload hoàn tất, chỉ cần để process thoát bình thường. JVM sẽ thực hiện assembly và ghi cache.

Với ứng dụng server chạy liên tục, có thể:

- Chạy một bản training riêng trong môi trường staging hoặc môi trường huấn luyện.
- Gửi workload đại diện tới instance.
- Kết thúc training bằng diagnostic command khi đã đủ dữ liệu.

Ví dụ với process đang chạy:

~~~bash
jcmd -l
jcmd 12345 AOT.end_recording
~~~

Thay `12345` bằng PID thực tế. `AOT.end_recording` yêu cầu JVM kết thúc AOT training và ghi kết quả theo các đường dẫn đã cấu hình. Người chạy `jcmd` cần cùng máy và cùng effective user/group với process đích.

### 4.2. Lưu ý tài nguyên của workflow một lệnh

Trong workflow tự động, JVM phụ dùng để assembly có thể cần heap riêng tương đương heap của process training. Vì vậy, môi trường tạo cache cần đủ bộ nhớ cho cả giai đoạn training và assembly; mức sử dụng đỉnh có thể xấp xỉ hai lần heap được chỉ định cho một JVM.

Ví dụ nếu training chạy với:

~~~bash
java -Xms2g -Xmx2g \
     -XX:AOTCacheOutput=app.aot \
     -cp app.jar \
     com.example.App
~~~

thì môi trường tạo cache cần dự trù thêm bộ nhớ cho JVM assembly. Nếu chạy trong container nhỏ, workflow một lệnh có thể thất bại ở bước assembly dù ứng dụng training vẫn chạy bình thường.

Khi bị giới hạn RAM, dùng quy trình tách riêng training và assembly ở mục tiếp theo để có thể chạy hai bước trên các máy có cấu hình tài nguyên khác nhau.

## 5. Tách riêng training và assembly

Workflow tách giai đoạn hữu ích khi:

- Ứng dụng server cần chạy trong một khoảng thời gian trước khi kết thúc training.
- Muốn chạy training ở môi trường gần production nhưng assembly ở máy có nhiều CPU/RAM hơn.
- Muốn lưu riêng file cấu hình training để kiểm tra và tái sử dụng trong pipeline build.
- Muốn điều khiển thời điểm kết thúc training rõ ràng.

### 5.1. Giai đoạn training

~~~bash
java -XX:AOTMode=record \
     -XX:AOTConfiguration=app.aotconf \
     -cp app.jar \
     com.example.App
~~~

JVM ghi dữ liệu training vào `app.aotconf`. Nếu ứng dụng là server, gửi workload đại diện rồi dùng:

~~~bash
jcmd 12345 AOT.end_recording
~~~

Kết quả training được ghi vào file cấu hình AOT đã chỉ định.

### 5.2. Giai đoạn assembly

Chạy một JVM khác để tạo cache:

~~~bash
java -XX:AOTMode=create \
     -XX:AOTConfiguration=app.aotconf \
     -XX:AOTCache=app.aot \
     -cp app.jar
~~~

Ở mode `create`, JVM đọc cấu hình training và tạo file cache; ứng dụng không được chạy lại trong giai đoạn assembly.

### 5.3. Giai đoạn production

Dùng cache trong lệnh khởi chạy:

~~~bash
java -XX:AOTCache=app.aot \
     -cp app.jar \
     com.example.App
~~~

Nếu không chỉ định `AOTMode`, mode mặc định là `auto`. JVM sẽ thử nạp cache nếu tương thích; nếu không thể sử dụng cache, ứng dụng vẫn có thể chạy mà không có lợi ích AOT.

### 5.4. So sánh hai cách tạo cache

| Tiêu chí | Một lệnh `AOTCacheOutput` | Tách training/assembly |
|---|---|---|
| Số thao tác vận hành | Ít | Nhiều bước hơn |
| Quản lý file cấu hình training | JVM tự tạo file tạm | Có thể chỉ định `app.aotconf` |
| Ứng dụng cần kết thúc | Có, hoặc kết thúc recording bằng jcmd | Có thể chủ động kết thúc bằng jcmd |
| Tài nguyên | Training và JVM assembly có thể cần RAM đồng thời | Có thể bố trí training và assembly trên máy khác nhau |
| Phù hợp | CLI, integration workflow và môi trường đủ tài nguyên | Server dài hạn hoặc pipeline có kiểm soát |

Hai workflow tạo cùng loại AOT cache. Chọn theo cách triển khai và khả năng cấp tài nguyên, không dựa vào giả định rằng một cách tạo cache luôn cho kết quả nhanh hơn.

## 6. Cấu hình JVM sử dụng cache ở production

Ở môi trường chạy thật, truyền đường dẫn cache bằng:

~~~bash
java -XX:AOTCache=app.aot \
     -cp app.jar \
     com.example.App
~~~

Nếu ứng dụng đóng gói dưới dạng executable JAR:

~~~bash
java -XX:AOTCache=app.aot \
     -jar app.jar
~~~

Đặt file cache ở vị trí được process đọc, ví dụ cùng thư mục release hoặc một thư mục artifact riêng. Không ghi cache vào thư mục tạm bị xóa sau khi container restart nếu muốn tái sử dụng giữa các lần khởi động.

### 6.1. Hiểu đúng các AOT mode

| Mode | Hành vi |
|---|---|
| `auto` | Mode mặc định; chọn record, on hoặc off tùy tùy chọn và cache có thể nạp được hay không |
| `off` | Không sử dụng AOT cache |
| `record` | Chạy ứng dụng để training, ghi dữ liệu cấu hình |
| `create` | Assembly cache từ file cấu hình training |
| `on` | Chạy production và yêu cầu JVM nạp cache; không nạp được sẽ báo lỗi |

Trong `auto`:

- Nếu có `-XX:AOTCacheOutput`, JVM chuyển sang training/record rồi tạo cache.
- Nếu không có output nhưng cache có thể nạp, JVM chạy ở mode on.
- Nếu không có cache hợp lệ, JVM chạy bình thường mà không dùng AOT cache.

### 6.2. Production nên dùng auto hay on?

<badge color="success">Khuyến nghị production</badge>

Dùng mặc định `auto` hoặc chỉ định rõ:

~~~bash
java -XX:AOTMode=auto \
     -XX:AOTCache=app.aot \
     -Xlog:aot \
     -cp app.jar \
     com.example.App
~~~

Khi cache không thể nạp, JVM tiếp tục chạy không có cache. Cách này phù hợp khi ưu tiên tính sẵn sàng của ứng dụng.

Dùng `on` để **kiểm chứng nghiêm ngặt** trong staging hoặc CI:

~~~bash
java -XX:AOTMode=on \
     -XX:AOTCache=app.aot \
     -Xlog:aot \
     -cp app.jar \
     com.example.App
~~~

Nếu cache không tương thích, JVM dừng với lỗi thay vì âm thầm chạy không cache. Đây là cách tốt để phát hiện cache sai trong pipeline kiểm thử. Không nên bật fail-fast trong production nếu việc không có cache không phải lý do để dừng dịch vụ.

## 7. Kiểm tra cache đã được nạp thành công

Không nên chỉ nhìn thấy file `app.aot` tồn tại rồi kết luận JVM đã sử dụng nó. Cần kiểm tra log và đo hành vi lúc chạy.

### 7.1. Bật unified logging cho AOT

Chạy ứng dụng với:

~~~bash
java -XX:AOTCache=app.aot \
     -XX:AOTMode=on \
     -Xlog:aot \
     -cp app.jar \
     com.example.App
~~~

`-Xlog:aot` giúp xem thông tin về việc nạp và sử dụng AOT cache. Kết hợp `AOTMode=on` để quá trình kiểm tra thất bại rõ ràng nếu cache không thể dùng.

Khi cần xem nguồn class loading, thêm:

~~~bash
java -XX:AOTCache=app.aot \
     -XX:AOTMode=on \
     -Xlog:aot \
     -Xlog:class+load=info:file=aot-classload.log \
     -cp app.jar \
     com.example.App
~~~

Trong log class loading, những lớp được nạp từ cache có thể hiển thị nguồn `shared objects file`. Dùng dấu hiệu này để xác minh lớp cụ thể được tái sử dụng.

### 7.2. Kiểm tra nhanh khi chạy production

Với production mode `auto`, có thể bật log chẩn đoán trong một lần kiểm tra:

~~~bash
java -XX:AOTCache=app.aot \
     -Xlog:aot \
     -Xlog:class+load=info:file=aot-classload.log \
     -cp app.jar \
     com.example.App
~~~

Sau đó:

1. Xác nhận log không báo cache không tương thích hoặc không tìm thấy.
2. Tìm một số lớp ứng dụng/framework kỳ vọng đã được cache.
3. Kiểm tra nguồn class loading là `shared objects file` ở các lớp được cache.
4. Đối chiếu thời gian startup và thời gian đạt throughput ổn định với lần chạy không cache.
5. Ghi nhận trường hợp lớp không được cache để xác định training có thiếu đường chạy hay không.

Không phải tất cả lớp đều nhất thiết được nạp từ cache. Việc một số lớp được nạp bình thường không chứng minh toàn bộ cache thất bại.

### 7.3. Dấu hiệu kiểm tra và kết luận

| Bằng chứng | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| File `app.aot` tồn tại | Cache đã được tạo ra | JVM production đã nạp cache |
| JVM chạy với `-XX:AOTCache=app.aot` | Đã yêu cầu JVM dùng cache | Cache chắc chắn tương thích |
| `-XX:AOTMode=on` khởi chạy thành công | Cache vượt qua kiểm tra nạp trong lần chạy đó | Ứng dụng chắc chắn nhanh hơn |
| `-Xlog:aot` ghi nhận cache được nạp | JVM đã chấp nhận cache | Mọi lớp đều nằm trong cache |
| Class loading log có `shared objects file` | Một số lớp được tái sử dụng từ cache | Mọi luồng nghiệp vụ đã được training |
| Benchmark startup/warm-up tốt hơn | Cache mang lại lợi ích trong workload đo | Mức cải thiện giống hệt production |

## 8. Điều kiện để cache có thể được tái sử dụng

AOT cache phụ thuộc chặt vào môi trường tạo và môi trường dùng.

| Thành phần | Yêu cầu |
|---|---|
| JDK | Dùng đúng phiên bản JDK đã tạo cache |
| Hệ điều hành | Cùng nền tảng tương thích |
| CPU architecture | Cùng kiến trúc |
| Ứng dụng | Cùng build/artifact |
| JAR | Giữ nguyên nội dung và timestamp |
| Classpath | Cùng danh sách và thứ tự; production có thể dùng superset theo điều kiện của JVM |
| Classpath entries | Ưu tiên danh sách JAR cụ thể; tránh thư mục, wildcard và nested JAR |
| JVM options | Không thay đổi các tùy chọn làm mất tính tương thích của cache |
| Workload training | Đại diện cho luồng khởi động và hoạt động thực tế |

### 8.1. Classpath và thứ tự JAR

Khi tạo cache bằng classpath, nên truyền danh sách JAR rõ ràng thay vì dùng wildcard hoặc thư mục:

~~~bash
java -XX:AOTCacheOutput=app.aot \
     -cp "app.jar:lib/core.jar:lib/driver.jar" \
     com.example.App
~~~

Ví dụ trên dùng dấu phân cách classpath của Linux/macOS. Trên Windows, dấu phân cách classpath là dấu chấm phẩy.

Khi sử dụng cache, giữ nguyên danh sách và thứ tự classpath đã dùng lúc training. Classpath production có thể là một superset trong những điều kiện được hỗ trợ, nhưng các JAR bổ sung sẽ không có dữ liệu cache tương ứng. Với Spring Boot executable JAR, nên dùng **executable JAR unpacking support** để đáp ứng yêu cầu classpath của AOT cache và CDS.

### 8.2. Tạo lại cache sau mỗi lần build

Cache không phải artifact độc lập với ứng dụng. Hãy tạo lại cache khi:

- Build lại ứng dụng và thay đổi bytecode.
- Thêm, xóa hoặc cập nhật dependency.
- Nâng JDK hoặc thay bản phân phối JDK.
- Chuyển hệ điều hành hoặc kiến trúc CPU.
- Thay đổi classpath/module path hoặc các tùy chọn JVM có ảnh hưởng đến tính tương thích.

Trong CI/CD, gắn file `.aot` với đúng application artifact, JDK và nền tảng. Không đưa cache cũ vào image mới chỉ vì tên file giống nhau.

## 9. Tối ưu training cho Spring Boot

Spring Framework hỗ trợ tạo AOT cache cho ứng dụng Spring. Với executable JAR, việc unpacking giúp JVM nhận classpath theo danh sách JAR thay vì phụ thuộc cấu trúc nested JAR.

### 9.1. Cache chỉ tối ưu startup

Một cách tạo cache cho Spring là cho application context thoát sau khi refresh:

~~~bash
java -XX:AOTCacheOutput=app.aot \
     -Dspring.context.exit=onRefresh \
     -jar application.jar
~~~

Cách này giúp chuẩn bị những lớp và object cần cho startup. Tuy nhiên, **với Java 25 trở lên**, AOT cache còn lưu method profiles. Nếu chỉ thoát ngay sau `ApplicationContext` refresh, training có thể không trải qua các luồng nghiệp vụ đủ đại diện để thu thập method profiles có ích.

### 9.2. Training với production-like workflow

Để tận dụng JEP 515:

1. Khởi động ứng dụng với cache output.
2. Chạy một phần workload giống production, ví dụ health check, đọc/ghi dữ liệu, các endpoint phổ biến và những luồng tích hợp chính.
3. Kết thúc training có kiểm soát.
4. Kiểm tra file cache và log assembly.
5. Chạy production mode với cùng artifact và classpath.

Nếu ứng dụng cần database/broker trong training, dùng môi trường thử nghiệm có cấu hình tương đương và dữ liệu an toàn. Không dùng secret hoặc dữ liệu khách hàng thật chỉ để tạo cache.

### 9.3. Ví dụ training cho ứng dụng Spring Boot

~~~bash
java -XX:AOTCacheOutput=application.aot \
     -jar application.jar
~~~

Sau khi process đã chạy, gửi một workload đại diện qua HTTP test hoặc integration test. Khi đã hoàn tất:

~~~bash
jcmd 12345 AOT.end_recording
~~~

Ở đây `12345` là PID của process training. Sau khi JVM kết thúc recording và tạo cache, chạy:

~~~bash
java -XX:AOTCache=application.aot \
     -Xlog:aot \
     -jar application.jar
~~~

Trong pipeline thực tế, tách training và production profile để không dùng nhầm database, credentials, message broker hoặc endpoint của môi trường thật.

## 10. Đánh giá hiệu năng có kiểm soát

AOT cache hướng tới cải thiện **startup time** và **warm-up time**, không bảo đảm mọi ứng dụng đều nhanh hơn ở mọi workload.

### 10.1. Đo ba trường hợp

| Trường hợp | Lệnh | Mục đích |
|---|---|---|
| Không cache | `java -cp app.jar com.example.App` | Baseline |
| Có cache | `java -XX:AOTCache=app.aot -cp app.jar com.example.App` | Đo lợi ích |
| Cache bắt buộc | Thêm `-XX:AOTMode=on` | Xác minh cache thực sự nạp được |

Giữ nguyên JDK, artifact, JVM options, cấu hình heap, máy chạy và workload. Chạy lặp nhiều lần; phân biệt cold start với warm start và đo cả thời gian đến request đầu tiên lẫn thời gian đạt throughput ổn định.

### 10.2. Chỉ số nên theo dõi

- Thời gian process khởi động đến khi ứng dụng sẵn sàng.
- Thời gian xử lý request đầu tiên.
- Throughput và latency trong giai đoạn warm-up.
- CPU và memory trong lúc training/assembly.
- Dung lượng file cache.
- Tỷ lệ lớp được nạp từ cache.
- Lỗi khởi chạy hoặc cảnh báo cache mismatch.

Không chỉ so sánh một lần chạy. File system cache, container image layer, JIT warm-up và trạng thái máy có thể làm kết quả thay đổi đáng kể.

### 10.3. Kết quả không cải thiện thì sao?

Nếu cache đã nạp thành công nhưng startup/warm-up không tốt hơn, kiểm tra:

1. Workload training có giống production không?
2. Các lớp và phương thức nóng có được thực thi trong training không?
3. Startup có thực sự bị giới hạn bởi class loading/linking hay bởi network, database, DNS hoặc service discovery?
4. JVM có đang dùng cùng JDK, classpath và cấu hình với training không?
5. Cache có được tái tạo theo đúng build mới nhất không?
6. Lợi ích có bị che bởi container cold start, storage I/O hoặc initialization ngoài JVM không?

Cache có thể giảm công việc JVM nhưng không rút ngắn thời gian chờ database, remote service hoặc migration dữ liệu.

## 11. Khác biệt Java 25 và JDK 26 cần nhớ

Bài này tập trung vào Java 25, nhưng khi triển khai hiện nay cần biết cải tiến đã xuất hiện ở JDK tiếp theo.

| Khía cạnh | Java 25 | JDK 26 |
|---|---|---|
| AOT cache cơ bản | Có, từ JDK 24 | Có |
| One-command cache creation | Có, JEP 514 | Có |
| Method profiles trong cache | Có, JEP 515 | Có |
| AOT object caching với ZGC | Một số tối ưu cần heap-object caching chưa hỗ trợ đầy đủ | Mở rộng hỗ trợ mọi GC theo JEP 516 |
| Cache tương thích giữa hai phiên bản | Không | Không; phải tạo cache mới cho JDK 26 |

**Lưu ý:** JEP 516 là cải tiến của JDK 26, không phải một tính năng của Java 25. Nếu ứng dụng vẫn chạy JDK 25 với ZGC, không giả định rằng các tối ưu AOT cần cached heap objects hoạt động như trên JDK 26. Nếu nâng lên JDK 26, tạo lại cache bằng JDK 26 và kiểm tra hiệu năng theo cấu hình GC mới.

Không mang cache được tạo bởi JDK 25 sang JDK 26. Cache là artifact gắn với phiên bản JDK và nền tảng.

## 12. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| File `.aot` không được tạo | Training chưa kết thúc hoặc assembly lỗi | Kiểm tra exit status, log và dung lượng bộ nhớ |
| JVM production không dùng cache | Đường dẫn sai, cache mismatch hoặc mode off | Dùng `-Xlog:aot`, kiểm tra path và AOT mode |
| Ứng dụng vẫn chạy nhưng không có lợi ích | Mode `auto` fallback sang không cache | Chạy staging với `-XX:AOTMode=on` để phát hiện lỗi |
| `AOTMode=on` dừng ngay | Cache không tương thích hoặc không thể đọc | Đọc log mismatch, tạo lại cache |
| Cache không được dùng sau khi deploy build mới | JAR hoặc dependency đã thay đổi | Tạo cache cho đúng artifact mới |
| Cache không dùng được trên máy khác | Khác JDK, OS hoặc CPU architecture | Tạo cache riêng cho nền tảng triển khai |
| Spring Boot cache không có nhiều lớp | Nested JAR hoặc classpath không đáp ứng điều kiện | Dùng executable JAR unpacking support, kiểm tra classpath |
| Assembly thất bại do thiếu RAM | JVM phụ cần thêm heap | Tách training và assembly hoặc tăng tài nguyên |
| Startup nhanh hơn nhưng request đầu chậm | Training thiếu method profiles | Chạy production-like workload khi training |
| Cache lớn nhưng hiệu quả thấp | Training tải quá nhiều lớp không dùng | Giảm phạm vi workload và tạo lại cache |
| Dùng ZGC trên Java 25 không đạt tối ưu mong đợi | Giới hạn AOT object caching của JDK 25 | Đánh giá JDK 26/JEP 516 hoặc GC phù hợp với JDK 25 |
| Tăng cache không làm giảm startup | Bottleneck nằm ngoài class loading/JVM | Đo network, database, initialization và container startup |

### 12.1. Cache không nạp được nhưng ứng dụng vẫn chạy

Trong production, `AOTMode=auto` cho phép JVM tiếp tục chạy khi cache không tương thích. Đây là hành vi dự phòng an toàn hơn cho tính sẵn sàng, nhưng có thể làm hiệu năng trở lại mức không cache.

Vì vậy:

- Dùng `auto` cho deployment cần khả năng tiếp tục chạy.
- Dùng `on` trong CI/staging để xác nhận cache tương thích.
- Bật `-Xlog:aot` khi cần tìm nguyên nhân.
- Không bỏ qua cảnh báo cache mismatch trong pipeline phát hành.

## 13. Checklist triển khai trong CI/CD

Một pipeline tạo và phát hành AOT cache nên thực hiện:

1. Chọn đúng JDK, OS và CPU architecture của target.
2. Build application artifact và khóa dependency.
3. Chuẩn bị training workload đại diện.
4. Tạo `.aot` bằng `AOTCacheOutput` hoặc workflow record/create.
5. Kiểm tra file cache được tạo và assembly kết thúc thành công.
6. Chạy smoke test với `AOTMode=on` và `-Xlog:aot`.
7. Đo startup/warm-up so với baseline.
8. Gắn cache với đúng build ID, JDK và nền tảng.
9. Đóng gói app và cache vào cùng release artifact hoặc phát hành theo manifest tương ứng.
10. Khi app/JDK/platform thay đổi, tạo cache mới.

### 13.1. Manifest artifact nên ghi nhận gì?

| Trường | Ví dụ |
|---|---|
| Application build | `shop-service-1.8.0` |
| JDK | `25.0.x` |
| OS/architecture | `linux-x86_64` |
| Cache file | `shop-service.aot` |
| Training workload | `checkout-smoke-v3` |
| Classpath fingerprint | Hash của danh sách JAR theo thứ tự |
| Creation time | Thời điểm training/assembly |
| Validation | Kết quả chạy `AOTMode=on` |
| Benchmark | Startup p50/p95 và warm-up throughput |

Các trường trên là quy ước quản lý artifact của dự án, không phải định dạng manifest bắt buộc của JVM.

### 13.2. An toàn khi tạo cache

AOT cache có thể chứa dữ liệu được JVM chuẩn bị trước, bao gồm object state thuộc phạm vi tối ưu của cache. Do đó:

- Tạo cache từ artifact đáng tin cậy và pipeline được kiểm soát.
- Không dùng credentials hoặc dữ liệu khách hàng thật trong training nếu không cần.
- Giới hạn quyền đọc/ghi file cache.
- Không dùng cache như kho lưu secrets hoặc dữ liệu ứng dụng.
- Không tái sử dụng cache giữa các release không tương thích.
- Kiểm tra provenance của cache như với các artifact build khác.

## 14. Ma trận kiểm thử nghiệm thu

| Mã | Kịch bản | Kết quả mong đợi |
|---|---|---|
| A1 | Tạo cache bằng `-XX:AOTCacheOutput` | JVM hoàn tất training và tạo file `.aot` |
| A2 | Tạo cache bằng record/create riêng | Có file cấu hình training và file cache |
| A3 | Chạy với `-XX:AOTCache=app.aot` | JVM thử nạp cache |
| A4 | Chạy với `-XX:AOTMode=on` | Không tương thích thì fail-fast |
| A5 | Chạy với `-XX:AOTMode=auto` khi cache sai | Ứng dụng vẫn có thể chạy không cache |
| A6 | Bật `-Xlog:aot` | Có log chẩn đoán việc nạp cache |
| A7 | Bật `-Xlog:class+load` | Nhận diện được một số lớp từ shared objects file |
| A8 | Thay đổi JAR sau training | Cache cũ không được xem là hợp lệ |
| A9 | Đổi JDK/OS/CPU | Tạo cache mới cho môi trường mới |
| A10 | Training workload thiếu luồng nóng | Benchmark thể hiện lợi ích warm-up hạn chế |
| A11 | Training với production-like workload | Method profiles phù hợp hơn với đường chạy mục tiêu |
| A12 | Chạy assembly trong container giới hạn RAM | Pipeline xử lý được mức tiêu thụ của JVM phụ hoặc tách giai đoạn |
| A13 | Dùng JDK 25 với ZGC | Ghi nhận giới hạn object caching của phiên bản |
| A14 | Dùng JDK 26 với ZGC | Kiểm chứng hỗ trợ mở rộng theo JEP 516 |
| A15 | Nâng build ứng dụng | Pipeline tạo và kiểm tra cache mới |

Một lần chạy thành công với `AOTMode=on` chứng minh cache có thể được nạp trong cấu hình đó; benchmark mới chứng minh được lợi ích hiệu năng.

## 15. Bài tập thực hành

Bạn có ứng dụng `shop-service.jar` chạy bằng JDK 25, sử dụng Spring Boot và có ba luồng chính: khởi động ứng dụng, tra cứu đơn hàng và tạo đơn hàng.

Thực hiện:

1. Kiểm tra JDK và ghi nhận baseline startup/warm-up khi chưa dùng cache.
2. Chạy ứng dụng bằng `-XX:AOTCacheOutput=shop-service.aot` trong môi trường training.
3. Tạo workload gồm health check, tra cứu đơn, tạo đơn và một số thao tác persistence đại diện.
4. Kết thúc training và xác nhận file cache đã được tạo.
5. Chạy production command với `-XX:AOTCache=shop-service.aot`.
6. Lặp lại với `-XX:AOTMode=on -Xlog:aot` để kiểm chứng cache nạp thành công.
7. Bật class loading log, xác minh một số lớp được tái sử dụng từ cache.
8. So sánh startup p50/p95, request đầu tiên và warm-up throughput.
9. Thay đổi một dependency rồi thử lại với cache cũ để quan sát mismatch; tạo cache mới và xác nhận đã khôi phục.
10. Viết hướng dẫn rollback về lần chạy không cache nếu cache không tương thích trong production.

**Sản phẩm cần nộp:** các lệnh training/production, file cache cùng metadata, log xác nhận nạp thành công, bảng benchmark trước/sau và checklist tái tạo cache khi nâng cấp.

## 16. Checklist nhanh khi vận hành

Trước khi phát hành:

- Đúng JDK 25 và đúng OS/CPU target.
- Training có workload đại diện cho production.
- Cache được tạo từ đúng application artifact.
- Classpath/JAR order và timestamp được giữ nhất quán.
- File `.aot` được gắn với release tương ứng.
- Production dùng `-XX:AOTCache`.
- CI/staging đã kiểm tra bằng `-XX:AOTMode=on`.
- Production log có thể chẩn đoán bằng `-Xlog:aot`.
- Benchmark đã đo startup và warm-up, không chỉ thời gian một lần chạy.
- Đã xem xét giới hạn GC theo JDK, đặc biệt khác biệt Java 25 và JDK 26.
- Cache được tạo lại sau khi thay JDK, build, dependency hoặc nền tảng.
- Cache không chứa secrets/dữ liệu nhạy cảm không cần thiết.

## Tài liệu tham khảo chính thức

- [JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): AOT cache được giới thiệu trong JDK 24.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): đơn giản hóa tạo cache với `-XX:AOTCacheOutput`.
- [JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): đưa method profiles vào cache trong JDK 25.
- [JEP 516 — Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516): mở rộng object caching sang mọi GC trong JDK 26.
- [Oracle Java SE 25 — The java Command, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): các tùy chọn `AOTCache`, `AOTCacheOutput`, `AOTConfiguration`, `AOTMode` và logging.
- [Oracle Java SE 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): diagnostic command `AOT.end_recording`.
- [Inside.java — Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/): workflow Java 25, method profiling, requirements và cách kiểm tra cache.
- [Spring Framework — JVM AOT Cache](https://docs.spring.io/spring-framework/reference/integration/aot-cache.html): tạo và sử dụng cache cho ứng dụng Spring, classpath requirements và production-like training.
- [Oracle JDK 26 Release Notes — JEP 516](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): thay đổi hỗ trợ AOT object caching với ZGC và các GC khác.
