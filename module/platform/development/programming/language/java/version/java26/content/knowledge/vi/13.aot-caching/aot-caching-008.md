# Sử dụng bộ đệm bằng -XX:AOTCache

> **Mốc cập nhật: 27-11-2026.** AOT Cache được giới thiệu trong JDK 24 (JEP 483), đơn giản hóa quy trình tạo ở JDK 25 (JEP 514), bổ sung method profiling ở JDK 25 (JEP 515) và hỗ trợ lưu trữ object với mọi garbage collector từ JDK 26 (JEP 516). Trong JDK 27, các cờ `-XX:AOTCache`, `-XX:AOTCacheOutput` và `-XX:AOTMode` tiếp tục là cách chính thức để tạo và sử dụng cache. Đây là tính năng runtime của HotSpot, không phải Preview hay Incubator feature.

## 1. AOT Cache giải quyết vấn đề gì?

Khi khởi động một ứng dụng Java, JVM thường phải thực hiện nhiều công việc trước khi ứng dụng xử lý được request đầu tiên:

- Tìm và đọc class từ JAR hoặc module.
- Parse bytecode và tạo biểu diễn nội bộ của class.
- Load, link và initialize các class cần thiết.
- Tạo một số object nền tảng và cấu trúc runtime.
- Thu thập profile trong quá trình chạy để JIT nhận diện method nóng và tối ưu mã.

Những công việc này có thể lặp lại trong mỗi lần khởi động. Với ứng dụng CLI, serverless, job chạy ngắn hoặc service thường xuyên scale từ zero, thời gian khởi động và warm-up ảnh hưởng trực tiếp tới thời gian có request đầu tiên và thời gian đạt throughput ổn định.

**Ahead-of-Time Cache (AOT Cache)** lưu các kết quả tối ưu có thể tái sử dụng từ một lần chạy huấn luyện. Khi ứng dụng khởi động lần sau với cache phù hợp, JVM có thể nạp class và object đã lưu, đồng thời sử dụng dữ liệu profile đã thu thập để JIT bắt đầu tối ưu sớm hơn.

AOT Cache hướng tới hai mục tiêu:

| Mục tiêu | Ý nghĩa |
|---|---|
| Startup | Rút ngắn thời gian từ lúc chạy JVM đến khi ứng dụng sẵn sàng xử lý công việc. |
| Warm-up | Giúp JIT có profile từ lần chạy trước để nhận diện method nóng sớm hơn, giảm thời gian đạt hiệu năng ổn định. |

AOT Cache không biến ứng dụng Java thành native executable. JVM vẫn chạy bytecode, vẫn có class loading động, vẫn thực thi JIT và vẫn có thể tối ưu tiếp trong runtime. Cache chỉ chuyển một phần công việc có thể chuẩn bị trước sang giai đoạn tạo cache.

## 2. AOT Cache chứa những gì?

AOT Cache là container của HotSpot cho các artifact được tạo trước. Qua các JDK:

- JDK 24 (JEP 483) đưa vào AOT cache cho class loading và linking, cùng khả năng lưu archived heap objects.
- JDK 25 (JEP 515) bổ sung method execution profiles để JIT có dữ liệu về method nóng ngay từ lúc khởi động.
- JDK 26 (JEP 516) cải tiến cách lưu và nạp heap objects để AOT object caching hoạt động với mọi garbage collector, bao gồm ZGC.
- JDK 27 tiếp tục dùng các cờ AOT Cache hiện hành và bổ sung alias rõ nghĩa hơn là `-XX:AOTMode=required` cho chế độ bắt buộc nạp cache.

Không nên hiểu AOT Cache là một file chứa toàn bộ native machine code của ứng dụng. Method profiling cung cấp dữ liệu cho JIT; JIT vẫn quyết định và biên dịch native code trong runtime.

## 3. Ba giai đoạn của AOT Cache

Quy trình đầy đủ gồm ba giai đoạn:

~~~mermaid
flowchart LR
    A["Training<br/>Chạy workload đại diện"] --> B["AOT Configuration<br/>app.aotconfig"]
    B --> C["Assembly<br/>Tạo AOT Cache"]
    C --> D["AOT Cache<br/>app.aot"]
    D --> E["Production<br/>Chạy ứng dụng với cache"]
~~~

| Giai đoạn | Việc JVM thực hiện | Artifact |
|---|---|---|
| Training | Chạy ứng dụng với workload đại diện, ghi nhận class, object và dữ liệu profile phù hợp. | AOT Configuration (`.aotconfig`). |
| Assembly | Đọc cấu hình, tạo artifact có thể tái sử dụng và ghi thành cache. | AOT Cache (`.aot`). |
| Production | Khởi chạy ứng dụng và nạp cache tương thích. | Cache được đọc, không phải training lại. |

Training cần chạy các đường xử lý có ý nghĩa với production. Nếu chỉ chạy main method rồi thoát mà không đi qua luồng nghiệp vụ quan trọng, cache có thể bỏ sót class hoặc profile cần thiết.

## 4. Tạo cache nhanh bằng -XX:AOTCacheOutput

Từ JDK 25, JEP 514 đơn giản hóa thao tác phổ biến: có thể thực hiện training và assembly trong một lệnh bằng `-XX:AOTCacheOutput`.

Giả sử ứng dụng được đóng gói trong `app.jar`:

~~~text
java -XX:AOTCacheOutput=app.aot -jar app.jar
~~~

Trong lần chạy này:

1. JVM chạy ứng dụng ở chế độ training.
2. JVM thu thập thông tin trong lúc ứng dụng hoạt động.
3. Khi ứng dụng kết thúc, JVM tự thực hiện assembly bằng một JVM process thứ hai.
4. File `app.aot` được tạo để dùng cho những lần chạy tiếp theo.

Sau đó khởi chạy ứng dụng với cache:

~~~text
java -XX:AOTCache=app.aot -jar app.jar
~~~

Đây là cách phù hợp để bắt đầu thử nghiệm vì chỉ cần hai lệnh.

### 4.1. Training phải chạy đủ workload

Nếu ứng dụng là web service, training nên bao gồm các bước tương tự khởi động production:

- Khởi tạo framework và dependency injection.
- Đăng ký route/controller.
- Tạo kết nối hoặc khởi tạo client theo cách phù hợp với môi trường training.
- Chạy một số request đại diện cho các luồng thường dùng.
- Thực hiện các nhánh khởi tạo quan trọng mà production cần.

Tránh chạy toàn bộ stress test hoặc test suite quá rộng nếu chúng chỉ load nhiều class không cần thiết. Cache càng chứa nhiều thành phần không dùng, quá trình tạo và nạp cache càng có thể tốn thời gian và bộ nhớ.

Không nên tạo cache từ một lần chạy quá ngắn chỉ để JVM thoát nhanh. Chất lượng cache phụ thuộc vào mức độ đại diện của training workload.

### 4.2. Lưu ý tài nguyên khi dùng AOTCacheOutput

Cách một lệnh có thể khởi chạy thêm JVM process để assembly. Process assembly sử dụng heap riêng với cấu hình heap tương tự training process. Vì vậy, trong môi trường giới hạn RAM, tổng nhu cầu bộ nhớ lúc tạo cache có thể gần gấp đôi heap được cấu hình cho một process.

Ví dụ, nếu training chạy với `-Xmx2g`, quá trình tạo cache có thể cần thêm khoảng 2 GB heap cho JVM assembly, ngoài các vùng nhớ khác của hai process.

Nếu máy build nhỏ hoặc container có memory limit chặt, hãy cân nhắc tách training và assembly thành ba giai đoạn để có thể chạy assembly trên máy có nhiều RAM/CPU hơn.

## 5. Tạo cache theo ba giai đoạn riêng biệt

Khi cần kiểm soát training và assembly độc lập, dùng `-XX:AOTConfiguration` và `-XX:AOTMode`.

### 5.1. Giai đoạn training

~~~text
java -XX:AOTMode=record -XX:AOTConfiguration=app.aotconfig -jar app.jar
~~~

JVM chạy ứng dụng và ghi thông tin training vào `app.aotconfig`. Đây là file cấu hình, chưa phải cache dùng cho production.

Nếu training bằng classpath và main class:

~~~text
java -XX:AOTMode=record -XX:AOTConfiguration=app.aotconfig -cp app.jar com.example.Main
~~~

### 5.2. Giai đoạn assembly

~~~text
java -XX:AOTMode=create -XX:AOTConfiguration=app.aotconfig -XX:AOTCache=app.aot -cp app.jar
~~~

JVM đọc dữ liệu training trong `app.aotconfig` và tạo `app.aot`. Ở giai đoạn này ứng dụng không được thực thi như một lần chạy production; JVM chỉ thực hiện công việc assembly.

Trong chế độ `create`, `-XX:AOTCache=app.aot` chỉ định file cache đầu ra.

### 5.3. Giai đoạn production

~~~text
java -XX:AOTCache=app.aot -jar app.jar
~~~

JVM nạp cache nếu cache tương thích với ứng dụng, JDK, nền tảng và các tùy chọn runtime đang dùng.

Ba giai đoạn riêng biệt phù hợp khi:

- Training cần chạy trên môi trường gần production.
- Assembly cần nhiều CPU hoặc RAM hơn môi trường training.
- Muốn lưu AOT Configuration để kiểm tra, quản lý hoặc tái tạo cache.
- Muốn tách quy trình build artifact khỏi quá trình chạy ứng dụng.

## 6. Ý nghĩa của các cờ AOT

Các cờ chính trong JDK 27:

| Cờ | Chức năng |
|---|---|
| `-XX:AOTCache=cachefile` | Đọc cache trong production; ở mode `create`, đây cũng là đường dẫn cache đầu ra. |
| `-XX:AOTCacheOutput=cachefile` | Chỉ định cache cần tạo; trong mode mặc định `auto`, kích hoạt training và assembly tự động. |
| `-XX:AOTConfiguration=configfile` | Chỉ định file cấu hình training để ghi hoặc đọc. |
| `-XX:AOTMode=mode` | Chọn chế độ hoạt động: `auto`, `off`, `record`, `create`, `required` hoặc alias `on`. |
| `-XX:+AOTClassLinking` | Cho phép tối ưu class linking nâng cao khi tạo cache; có thể bổ sung ràng buộc tương thích runtime. |
| `-XX:+AOTStreamableObjects` | Yêu cầu định dạng object có thể stream theo cách GC-agnostic trong các tình huống cần lựa chọn này. |
| `-Xlog:aot` | Hiển thị thông tin chẩn đoán quá trình dùng hoặc từ chối AOT Cache. |

Đuôi file thông dụng:

- AOT Cache: `.aot`
- AOT Configuration: `.aotconfig`

Không dùng đồng thời `-XX:AOTCache` và `-XX:AOTCacheOutput` trong cùng một command line. Chúng là hai lựa chọn loại trừ nhau.

## 7. Hiểu các chế độ AOTMode

JDK 27 có các mode sau:

| Mode | Hành vi |
|---|---|
| `auto` | Mặc định. Tự chọn training, production hoặc tắt AOT tùy theo cờ cache. |
| `off` | Không dùng AOT Cache; các tùy chọn AOT khác bị bỏ qua. |
| `record` | Chạy training và ghi AOT Configuration. Có thể kèm AOTCacheOutput để tự thực hiện assembly tiếp theo. |
| `create` | Đọc AOT Configuration và tạo AOT Cache; không chạy ứng dụng. |
| `required` | Bắt buộc nạp AOT Cache; không nạp được thì JVM báo lỗi và thoát. |
| `on` | Alias của `required` trong JDK 27; không nên dùng trong cấu hình mới. |

### 7.1. Cách mode auto lựa chọn

Nếu không chỉ định `-XX:AOTMode`, JVM dùng `auto`:

| Điều kiện | Mode mà JVM chọn | Kết quả |
|---|---|---|
| Có `-XX:AOTCacheOutput=...` | `record` | Training; sau đó assembly. |
| Không có AOTCacheOutput nhưng có cache có thể nạp | `required` | Chạy production với cache. |
| Không có cache có thể nạp | `off` | Chạy ứng dụng bình thường, không dùng cache. |

Trong production, `auto` thường là lựa chọn an toàn. Nếu cache không tương thích hoặc không thể nạp, JVM có thể tiếp tục chạy ứng dụng mà không dùng cache.

### 7.2. Mode required dùng khi nào?

`required` buộc JVM phải nạp cache. Nếu cache thiếu, sai phiên bản hoặc không tương thích với tùy chọn runtime, JVM báo lỗi và dừng khởi chạy.

Dùng mode này trong CI hoặc staging để xác nhận cache được sử dụng thật sự:

~~~text
java -XX:AOTCache=app.aot -XX:AOTMode=required -jar app.jar
~~~

Trong JDK 27, `on` là alias cũ của `required`; nên dùng `required` trong cấu hình mới vì `on` có thể bị deprecated và loại bỏ trong release tương lai.

Không nên ép `required` trong production nếu môi trường triển khai có thể tự thêm các JVM option hoặc agent mà đội ứng dụng không kiểm soát. Khi đó cache có thể không nạp được và ứng dụng sẽ không khởi động.

## 8. Điều kiện để tái sử dụng AOT Cache

AOT Cache không phải cache dùng chung cho mọi ứng dụng Java. Theo JDK 27, cache gắn với tổ hợp:

1. Ứng dụng cụ thể, được xác định qua classpath, JAR hoặc module path.
2. JDK release cụ thể.
3. Hệ điều hành và CPU architecture cụ thể.

Khi một trong các yếu tố này thay đổi, cần tạo lại cache.

### 8.1. Giữ môi trường training và production nhất quán

Các nguyên tắc quan trọng:

- Training và production dùng cùng JDK release.
- Training và production dùng cùng OS và CPU architecture.
- Giữ nguyên timestamp của các JAR qua quá trình build/deploy nếu quy trình phụ thuộc vào chúng.
- Dùng classpath là danh sách JAR rõ ràng; tránh directory, wildcard và nested JAR trong classpath của training.
- Classpath production phải tương thích với classpath training; classpath production có thể là superset của classpath training theo quy tắc của AOT Cache.
- Giữ thứ tự JAR và module options nhất quán.
- Không dùng JVMTI agent thay đổi class loader search path qua `AddToBootstrapClassLoaderSearch` hoặc `AddToSystemClassLoaderSearch`.
- Training workload phải gần với hành vi ứng dụng trong production.

Một thay đổi code, thay đổi dependency hoặc nâng cấp JDK có thể khiến cache cũ không còn phù hợp. Quy trình build nên tạo lại cache cùng artifact của ứng dụng thay vì giữ cache qua nhiều phiên bản không liên quan.

### 8.2. Ví dụ ma trận tương thích

| Training | Production | Có nên dùng lại cache? |
|---|---|---|
| JDK 27, Linux x64, app build A | JDK 27, Linux x64, cùng app build A | Có, nếu các điều kiện classpath và JVM options phù hợp. |
| JDK 27, Linux x64 | JDK 27, Windows x64 | Không; khác OS. |
| JDK 27, Linux x64 | JDK 27, Linux ARM64 | Không; khác CPU architecture. |
| JDK 26, Linux x64 | JDK 27, Linux x64 | Không; khác JDK release. |
| app build A | app build B đã đổi class/dependency | Tạo lại cache. |
| Training classpath A | Production classpath là superset A | Có thể tương thích nếu các điều kiện còn lại thỏa mãn. |
| Training có `--add-modules X` | Production dùng `--add-modules Y` | Có thể cache không dùng được do module option khác nhau. |

## 9. JEP 516: AOT object caching với mọi GC

Trước JDK 26, một số tối ưu AOT cần archived heap objects không hoạt động với ZGC. Cách lưu object trước đây phụ thuộc vào việc memory-map dữ liệu object vào heap theo layout cụ thể của garbage collector. Các GC có cách biểu diễn object reference và layout khác nhau nên không thể dùng chung một định dạng mapping.

JEP 516 bổ sung định dạng object GC-agnostic và cơ chế nạp object tuần tự trong background. Nhờ vậy AOT object caching có thể dùng với mọi garbage collector, bao gồm:

- G1
- Serial
- Parallel
- ZGC
- Shenandoah (nếu có trong bản phân phối JDK)

Hai kiểu lưu object có trade-off:

| Kiểu object cache | Đặc điểm |
|---|---|
| GC-specific / mappable | Có thể khởi động rất nhanh khi dữ liệu cache đã nằm trong filesystem cache; phụ thuộc layout và cấu hình GC tương thích. |
| GC-agnostic / streamable | Nạp và materialize object theo cách độc lập với layout của GC; hữu ích khi cần hỗ trợ GC khác nhau hoặc giảm ảnh hưởng disk latency khi cold start, nhưng có thể dùng thêm CPU để stream/materialize. |

JVM có thể chọn cách phù hợp theo môi trường và dữ liệu training. `-XX:+AOTStreamableObjects` là tùy chọn nâng cao để yêu cầu định dạng streamable trong những trường hợp cần kiểm soát rõ lựa chọn này. Không cần thêm cờ đó cho mọi ứng dụng.

Từ JDK 26, không còn phải tránh ZGC chỉ vì muốn sử dụng AOT object caching. Hãy benchmark trên GC production thực tế vì kiểu nạp object và chi phí CPU/I/O có thể khác nhau.

## 10. JDK 24, 25, 26 và 27 đã thay đổi gì?

| JDK | Cải tiến AOT | Ý nghĩa khi sử dụng |
|---|---|---|
| JDK 24 — JEP 483 | AOT Class Loading & Linking | Giới thiệu AOT Cache, quy trình training, assembly, production và khả năng lưu class/heap objects. |
| JDK 25 — JEP 514 | AOT Command-Line Ergonomics | Cho phép tạo cache phổ biến bằng một lệnh `-XX:AOTCacheOutput`. |
| JDK 25 — JEP 515 | AOT Method Profiling | Đưa method execution profiles vào cache để JIT tối ưu sớm hơn khi ứng dụng khởi động. |
| JDK 26 — JEP 516 | AOT Object Caching with Any GC | Mở rộng AOT object caching cho mọi GC, bao gồm ZGC, bằng định dạng GC-agnostic. |
| JDK 27 | Tiếp tục các cờ AOT Cache; thêm alias `required` cho `on` | Dùng `-XX:AOTMode=required` thay cho `on` trong cấu hình mới. |

Các thay đổi này bổ sung cho nhau. Khi tạo cache bằng JDK 27, bạn được hưởng các cải tiến đã tích hợp từ các release trước, miễn là cache được tạo và sử dụng với môi trường tương thích.

## 11. Chẩn đoán khi cache không được sử dụng

### 11.1. Bật AOT logging

Thêm:

~~~text
-Xlog:aot
~~~

Ví dụ:

~~~text
java -XX:AOTCache=app.aot -Xlog:aot -jar app.jar
~~~

Log có thể cho biết cache có được mở hay bị từ chối, cùng nguyên nhân như:

- Không tìm thấy file cache.
- Ứng dụng không khớp với cache.
- JDK release hoặc nền tảng khác.
- JVM options không tương thích.
- Module options khác giữa training và production.
- Cache không được tạo hoàn chỉnh hoặc không thể đọc.

### 11.2. Dùng required để kiểm tra fail-fast

~~~text
java -XX:AOTCache=app.aot -XX:AOTMode=required -Xlog:aot -jar app.jar
~~~

Nếu cache không thể nạp, JVM báo lỗi thay vì chạy âm thầm không dùng cache. Đây là cách hữu ích trong CI hoặc staging.

Sau khi xác nhận cache hợp lệ, production có thể dùng `auto` mặc định để ứng dụng vẫn khởi chạy nếu cache gặp vấn đề ngoài dự kiến.

### 11.3. Kiểm tra class loading

Có thể kết hợp:

~~~text
-Xlog:aot,class+load=info
~~~

Log class loading giúp quan sát class nào được nạp từ nguồn shared archive và class nào vẫn được load bình thường. Đây là thông tin bổ sung khi cần kiểm tra cache có bao phủ đường khởi động mong muốn hay không.

### 11.4. Một số nguyên nhân phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| JVM chạy nhưng không thấy lợi ích | Mode `auto` đã fallback sang off. | Bật `-Xlog:aot` hoặc thử `required` trong staging. |
| Cache không nạp trên máy khác | Khác JDK, OS hoặc CPU architecture. | Tạo cache trên đúng nền tảng đích. |
| Cache không dùng sau khi cập nhật JAR | App build/dependency đã thay đổi. | Tạo lại cache sau mỗi build phù hợp. |
| Cache không tương thích module | `--add-modules` hoặc module options khác training. | Đồng bộ module options. |
| Cache fail khi bật agent | Agent dùng JVMTI class-loader search hooks hoặc sửa class. | Kiểm tra agent và tương thích với AOT Cache. |
| Training cache ít tác dụng | Workload không load class hoặc không đi qua method nóng cần thiết. | Bổ sung đường chạy đại diện, tránh test quá rộng. |
| Tạo cache bị thiếu RAM | `AOTCacheOutput` khởi chạy JVM assembly thứ hai. | Tách training/assembly hoặc tăng tài nguyên lúc build. |

## 12. Thiết kế quy trình AOT Cache cho CI/CD

Một quy trình phù hợp cho ứng dụng service:

~~~mermaid
flowchart TD
    A["Build application JARs"] --> B["Run representative training"]
    B --> C["Create AOT cache"]
    C --> D["Validate with AOTMode=required"]
    D --> E{"Cache loads successfully?"}
    E -->|Yes| F["Package app + app.aot"]
    E -->|No| G["Inspect -Xlog:aot and fix compatibility"]
    G --> C
    F --> H["Deploy with -XX:AOTCache=app.aot"]
    H --> I["Measure startup, warm-up and memory"]
~~~

Các bước nên có trong pipeline:

1. Build ứng dụng và dependency.
2. Chạy training workload gần production.
3. Tạo AOT Cache với `AOTCacheOutput` hoặc ba giai đoạn.
4. Xác nhận cache tồn tại và có kích thước hợp lý.
5. Khởi chạy smoke test bằng `AOTMode=required`.
6. Đóng gói AOT Cache cùng đúng phiên bản ứng dụng và JDK target.
7. Triển khai bằng `-XX:AOTCache=...`.
8. Đo startup, warm-up và tài nguyên sau triển khai.

AOT Cache là artifact gắn với build và runtime cụ thể. Hãy version hóa hoặc lưu cache theo build ID, JDK release và nền tảng. Không dùng chung một file cache cho nhiều phiên bản ứng dụng hoặc nhiều kiến trúc máy khác nhau.

## 13. Đo hiệu quả AOT Cache

AOT Cache có thể giảm startup và warm-up, nhưng không bảo đảm mọi ứng dụng đều cải thiện như nhau.

Nên đo tối thiểu bốn nhóm:

| Chỉ số | Ý nghĩa |
|---|---|
| Time to first useful work | Thời gian từ lúc khởi chạy đến khi ứng dụng hoàn thành công việc đầu tiên. |
| Time to readiness | Thời gian đến khi service sẵn sàng nhận request. |
| Time to steady-state throughput | Thời gian đạt throughput ổn định sau JIT warm-up. |
| CPU, RSS và memory footprint | Chi phí CPU, resident memory và tài nguyên lúc khởi động. |

So sánh ba cấu hình:

1. Chạy bình thường, không AOT Cache.
2. Chạy với AOT Cache.
3. Chạy với AOT Cache và GC production thực tế, đặc biệt nếu ứng dụng dùng ZGC.

Điều kiện benchmark:

- Cùng JDK release, OS, CPU và heap settings.
- Cùng application build và dependency.
- Cùng startup workload.
- Tách cold start khỏi warm start; filesystem cache có thể ảnh hưởng thời gian đọc cache.
- Chạy nhiều lượt và báo cáo median/p95 nếu phù hợp.
- Đo cả thời gian tạo cache và chi phí tài nguyên ở build pipeline.
- Không chỉ đo `main()` kết thúc nhanh; đo thời điểm service thực sự sẵn sàng.

AOT Cache chuyển một phần công việc từ runtime sang giai đoạn training/assembly. Khi ứng dụng được triển khai lặp lại nhiều lần, chi phí tạo cache có thể được phân bổ qua nhiều lần khởi chạy. Với ứng dụng chạy dài và ít restart, lợi ích startup có thể ít quan trọng hơn.

## 14. Bài tập thực hành

Dùng JDK 27 và một ứng dụng JAR thử nghiệm:

1. Chạy ứng dụng bình thường và ghi thời gian startup đến khi sẵn sàng.
2. Tạo cache bằng `-XX:AOTCacheOutput=app.aot`.
3. Kiểm tra file `.aot` được tạo sau khi ứng dụng training kết thúc.
4. Chạy lại bằng `-XX:AOTCache=app.aot`.
5. Bật `-Xlog:aot` và xác nhận cache được nạp.
6. Chạy bằng `-XX:AOTMode=required` để kiểm tra fail-fast.
7. Tạo cache theo ba giai đoạn bằng `app.aotconfig`.
8. So sánh chi phí RAM khi dùng cách một lệnh và ba giai đoạn.
9. Training với một workload không đi qua tính năng phụ; sau đó bổ sung workload đại diện và so sánh startup/warm-up.
10. Thử dùng cache với G1 và ZGC trên JDK 26/27; ghi nhận khác biệt.
11. Thử thay đổi JDK release hoặc dependency để quan sát cache compatibility.
12. Tích hợp tạo cache vào CI và gắn cache với application build ID.

Bảng ghi nhận:

| Thử nghiệm | JDK | Cache | GC | Startup | Readiness | Warm-up | Ghi chú |
|---|---|---|---|---:|---:|---:|---|
| Baseline | 27 | Không | G1 | | | | |
| Production cache | 27 | Có | G1 | | | | |
| ZGC cache | 27 | Có | ZGC | | | | |
| Required validation | 27 | Có | G1 | | | | |

## 15. Checklist trước khi triển khai

- [ ] Cache được tạo từ đúng application build và dependency.
- [ ] Training workload đại diện cho startup path và nghiệp vụ production.
- [ ] Training và production dùng cùng JDK release, OS và CPU architecture.
- [ ] Classpath/module path và module options tương thích.
- [ ] Timestamp của JAR được bảo toàn theo quy trình đóng gói.
- [ ] Cache được tạo lại khi ứng dụng, dependency hoặc JDK thay đổi.
- [ ] Đã kiểm tra cache bằng `-XX:AOTMode=required` trong CI/staging.
- [ ] Production có chiến lược fallback phù hợp; `auto` thường an toàn hơn `required`.
- [ ] Đã bật `-Xlog:aot` khi cần chẩn đoán.
- [ ] Đã tính đến RAM cần cho JVM assembly khi dùng `AOTCacheOutput`.
- [ ] Đã benchmark trên GC và nền tảng thực tế.
- [ ] Cache được version hóa và triển khai cùng application artifact tương ứng.

## Tài liệu tham khảo chính thức

- [JEP 483: Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483)
- [JEP 514: Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514)
- [JEP 515: Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515)
- [JEP 516: Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516)
- [The java Command — Java SE 27, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [JDK 26 Release Notes — AOT Object Caching with Any GC](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK 27 Release Notes — AOTMode required alias](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations — Inside Java](https://inside.java/2026/01/09/run-aot-cache/)
- [Performance Improvements in JDK 26 — Inside Java](https://inside.java/2026/06/09/jdk-26-performance-improvements/)

