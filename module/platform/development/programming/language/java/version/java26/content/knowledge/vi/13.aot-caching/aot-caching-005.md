# Ba giai đoạn: huấn luyện, tạo bộ đệm và chạy sử dụng

AOT Cache của HotSpot giúp JVM giảm thời gian khởi động và warm-up bằng cách tái sử dụng những thông tin đã thu thập từ một lần chạy đại diện trước đó. Quy trình có ba giai đoạn: **huấn luyện (Training/Record)** để ghi nhận ứng dụng hoạt động như thế nào, **tạo bộ đệm (Assembly/Create)** để chuyển dữ liệu huấn luyện thành file cache, và **chạy sử dụng (Production)** để JVM nạp cache khi khởi chạy ứng dụng.

Trong JDK 26, AOT Cache là tính năng runtime của HotSpot, không phải preview API và không cần --enable-preview. Nó cũng không tạo ra một executable native thay thế ứng dụng Java. JVM vẫn chạy bytecode và vẫn dùng JIT; cache cung cấp trước một số dữ liệu và trạng thái để JVM khởi động nhanh hơn, đồng thời có thể bắt đầu tối ưu phương thức sớm hơn.

Bài tập trung vào JDK 26 và kiểm tra khác biệt cần biết khi chuyển sang JDK 27. Chỉ sử dụng các lệnh AOT Cache còn được tài liệu JDK 26/27 hỗ trợ; không dựa vào quy trình AppCDS cũ hoặc tùy chọn đã bị loại bỏ.

## 1. AOT Cache lưu gì và giúp gì?

AOT Cache là một container chứa các artifact do JVM tạo trước để tái sử dụng ở lần chạy sau. Nền tảng ban đầu của tính năng là JEP 483 – Ahead-of-Time Class Loading & Linking, được đưa vào JDK 24.

Qua các release tiếp theo, cache được mở rộng:

| Release | JEP | Cải tiến |
|---|---|---|
| JDK 24 | JEP 483 | AOT Cache lưu trạng thái class đã được nạp và liên kết cùng các object đã khởi tạo, giúp giảm công việc lặp lại khi khởi động |
| JDK 25 | JEP 514 | Đơn giản hóa thao tác tạo cache bằng AOTCacheOutput |
| JDK 25 | JEP 515 | Ghi method execution profiles từ lần huấn luyện vào cache để JIT có thể bắt đầu tối ưu sớm hơn |
| JDK 26 | JEP 516 | Mở rộng AOT object caching để hoạt động với mọi garbage collector, bao gồm ZGC |

AOT Cache có thể hỗ trợ:

- Tái sử dụng class đã được đọc, phân tích, nạp và liên kết trong lần huấn luyện.
- Tái sử dụng một số object đã được khởi tạo và được phép đưa vào cache.
- Cung cấp method profiles đã ghi nhận để JIT có dữ liệu tối ưu ngay từ sớm.
- Giảm thời gian khởi động và rút ngắn giai đoạn warm-up trong workload phù hợp.

Method profile không phải mã native đã biên dịch sẵn. JEP 515 lưu dữ liệu thực thi của phương thức để JIT sử dụng khi ứng dụng chạy. JVM vẫn quyết định biên dịch và tối ưu mã native theo runtime.

JEP 516 cho phép AOT object caching làm việc với các GC khác nhau, gồm G1, Parallel GC, Serial GC, Shenandoah và ZGC tùy theo cấu hình/runtime hỗ trợ. Trước JDK 26, một số tối ưu AOT liên quan đến heap object không dùng được với ZGC vì định dạng object trong cache gắn với cách bố trí bộ nhớ của GC. JDK 26 bổ sung cách lưu/nạp object trung lập với GC để gỡ giới hạn đó.

## 2. Phân biệt ba giai đoạn

~~~text
Ứng dụng + workload đại diện
            |
            v
   1. TRAINING / RECORD
   Chạy ứng dụng, ghi nhận class,
   object và thông tin thực thi
            |
            v
      app.aotconfig
            |
            v
   2. ASSEMBLY / CREATE
   Đọc cấu hình, tạo AOT Cache
            |
            v
         app.aot
            |
            v
   3. PRODUCTION
   JVM nạp cache và chạy ứng dụng
            |
            v
   Startup / warm-up được cải thiện
~~~

Mỗi giai đoạn có một nhiệm vụ riêng:

| Giai đoạn | JVM làm gì? | Đầu ra / kết quả |
|---|---|---|
| Training / Record | Thực thi ứng dụng với workload đại diện, thu thập dữ liệu và lịch sử khởi tạo | File cấu hình AOT, thường có đuôi .aotconfig |
| Assembly / Create | Đọc file cấu hình và tạo artifact tối ưu hóa | File AOT Cache, thường có đuôi .aot |
| Production | Nạp cache tương thích rồi thực thi ứng dụng bình thường | Startup và warm-up có thể nhanh hơn |

File .aotconfig là dữ liệu đầu vào của bước Assembly. File .aot là cache được dùng trong Production. Không nhầm hai file này hoặc đổi tên một file thành phần mở rộng của file kia.

Ba giai đoạn là mô hình triển khai. JDK 25 đã thêm một lệnh tiện dụng để kết hợp Training và Assembly, nhưng hai công việc này vẫn diễn ra riêng về mặt logic. Phần dưới trước hết trình bày quy trình ba bước tường minh để dễ kiểm soát và chẩn đoán.

## 3. Chuẩn bị môi trường và workload huấn luyện

AOT Cache gắn với một tổ hợp cụ thể:

- Ứng dụng, được xác định qua classpath, JAR hoặc module path.
- Release JDK tạo cache.
- Hệ điều hành và kiến trúc CPU.

Nếu thay đổi một trong các yếu tố này, hãy tạo lại cache. Không dùng file AOT được tạo bằng JDK 26 để triển khai sang JDK 27. Không sao chép cache từ Linux x64 sang Windows hoặc ARM64 rồi giả định nó sẽ dùng được.

Trước khi huấn luyện:

1. Chọn đúng bản JDK sẽ chạy ứng dụng trong Production.
2. Hoàn tất build ứng dụng và dependency; không thay JAR sau khi tạo cache.
3. Xác định cách khởi chạy thật: classpath, module path, main class, system properties và các VM options ảnh hưởng đến việc nạp class.
4. Chuẩn bị workload đại diện cho các chức năng thường dùng.
5. Chạy qua các nhánh khởi tạo quan trọng, chẳng hạn cấu hình, dependency injection, kết nối pool, mapper, serializer và các endpoint chính.
6. Ghi lại phiên bản ứng dụng, JDK, OS/CPU, classpath và VM options cùng file cache.

Training không phải một lần chạy Hello World rồi mặc định mọi luồng của ứng dụng đều được tối ưu. JVM chỉ quan sát những gì workload thực sự kích hoạt. Nếu workload không nạp một class hoặc không chạy một nhánh nghiệp vụ, dữ liệu huấn luyện có thể không chứa thông tin hữu ích cho nhánh đó. Ứng dụng vẫn có thể nạp class động trong Production; chỉ là nhánh đó có thể không nhận được lợi ích AOT dự kiến.

Nên huấn luyện bằng dữ liệu và thao tác gần với Production nhưng đã loại bỏ thông tin nhạy cảm. Không đưa credential thật, dữ liệu khách hàng thật hoặc secret vào script huấn luyện chỉ để tạo cache.

## 4. Giai đoạn 1 – Training bằng AOTMode=record

Trong giai đoạn này, JVM chạy ứng dụng bình thường nhưng ghi nhận thông tin AOT vào file cấu hình.

Ví dụ ứng dụng được đóng gói trong app.jar và main class là com.example.Main:

~~~powershell
java -XX:AOTMode=record -XX:AOTConfiguration=app.aotconfig -cp app.jar com.example.Main --training
~~~

Ý nghĩa:

- -XX:AOTMode=record chọn chế độ huấn luyện.
- -XX:AOTConfiguration=app.aotconfig chỉ định nơi ghi dữ liệu huấn luyện.
- -cp app.jar xác định classpath của ứng dụng.
- com.example.Main là main class.
- --training là ví dụ tham số nghiệp vụ để ứng dụng chạy workload huấn luyện; thay bằng tham số và quy trình phù hợp của hệ thống.

Trong quá trình chạy, hãy thực hiện các luồng nghiệp vụ đại diện. Khi workload hoàn tất, dừng ứng dụng theo quy trình bình thường để JVM kết thúc phiên record và hoàn tất file cấu hình.

Sau bước này, kiểm tra file:

~~~powershell
Get-Item .\app.aotconfig
~~~

File cấu hình phải tồn tại và có kích thước hợp lý. Nếu file không xuất hiện, kiểm tra log JVM, quyền ghi thư mục và việc tiến trình huấn luyện đã kết thúc bình thường hay chưa.

Có thể bật log AOT để quan sát hoạt động:

~~~powershell
java -XX:AOTMode=record -XX:AOTConfiguration=app.aotconfig -Xlog:aot -cp app.jar com.example.Main --training
~~~

Không thêm các agent hoặc công cụ instrumentation làm biến đổi class một cách tùy ý trong Training rồi bỏ chúng ở Production. Một số tùy chọn JVM, JVMTI agent hoặc class loading hook có thể làm cache không tương thích với lần chạy sử dụng.

### Chọn workload đại diện

Một kế hoạch huấn luyện cho web service có thể gồm:

| Nhóm thao tác | Mục tiêu |
|---|---|
| Khởi động ứng dụng | Nạp cấu hình, DI container, logging và framework |
| Truy cập dữ liệu | Nạp driver, ORM, mapping và connection pool |
| API đọc | Nạp DTO, serializer, validation và lớp service |
| API ghi | Nạp transaction, validation, persistence và xử lý lỗi |
| Tác vụ nền | Nạp scheduler, consumer và thành phần xử lý message |
| Xử lý lỗi | Chạy các nhánh exception, retry và fallback phổ biến |

Không cần tạo workload khổng lồ chỉ để làm file cấu hình lớn. Tập trung vào những đường chạy thực sự quan trọng. Nếu ứng dụng có nhiều chế độ khởi chạy khác nhau với classpath hoặc module graph khác nhau, hãy đánh giá và tạo cache tương ứng cho từng biến thể cần triển khai.

## 5. Giai đoạn 2 – Assembly bằng AOTMode=create

Sau khi có app.aotconfig, dùng JVM ở chế độ create để tạo file cache. Trong giai đoạn này, JVM đọc dữ liệu cấu hình; nó không chạy main method của ứng dụng.

~~~powershell
java -XX:AOTMode=create -XX:AOTConfiguration=app.aotconfig -XX:AOTCache=app.aot -cp app.jar
~~~

Ý nghĩa:

- -XX:AOTMode=create chọn giai đoạn Assembly.
- -XX:AOTConfiguration=app.aotconfig chỉ định dữ liệu huấn luyện cần đọc.
- -XX:AOTCache=app.aot chỉ định file cache đầu ra trong chế độ create.
- -cp app.jar cung cấp cùng định danh classpath của ứng dụng.

Ở chế độ create, AOTCache được ghi ra file. Đây là một trường hợp đặc biệt của tùy chọn AOTCache: trong Production nó được đọc, còn khi AOTMode=create thì nó là đích ghi cache. Không truyền đồng thời AOTCache và AOTCacheOutput trong cùng một lệnh; hai tùy chọn này loại trừ nhau.

Sau khi lệnh kết thúc, xác nhận file cache:

~~~powershell
Get-Item .\app.aot
~~~

Có thể dùng log AOT trong giai đoạn Assembly:

~~~powershell
java -XX:AOTMode=create -XX:AOTConfiguration=app.aotconfig -XX:AOTCache=app.aot -Xlog:aot -cp app.jar
~~~

Nếu Assembly thất bại, kiểm tra:

- File .aotconfig có tồn tại, đọc được và được tạo từ đúng ứng dụng hay không.
- Classpath hoặc module path trong lệnh create có khớp với ứng dụng huấn luyện hay không.
- JDK dùng để huấn luyện và tạo cache có cùng release hay không.
- Các VM options có xung đột hoặc agent có can thiệp class loading hay không.
- Dung lượng đĩa và quyền ghi file cache.

Không tự sửa nội dung .aotconfig hoặc .aot. Đây là định dạng artifact do JVM quản lý; hãy tạo lại từ quy trình record/create nếu dữ liệu hỏng hoặc không tương thích.

## 6. Giai đoạn 3 – Production bằng AOTCache

Trong Production, khởi chạy ứng dụng với file cache đã tạo:

~~~powershell
java -XX:AOTCache=app.aot -cp app.jar com.example.Main
~~~

Hoặc viết rõ chế độ tự động:

~~~powershell
java -XX:AOTMode=auto -XX:AOTCache=app.aot -cp app.jar com.example.Main
~~~

Ở JDK 26, auto là chế độ mặc định. Nếu cache có thể nạp, JVM sử dụng cache. Nếu cache không thể nạp do không tồn tại, không truy cập được hoặc không tương thích, JVM tiếp tục chạy ứng dụng mà không dùng cache.

Đây là hành vi phù hợp cho Production khi muốn ứng dụng tiếp tục hoạt động dù cache không sử dụng được. Không để sự cố cache làm gián đoạn ứng dụng nếu cache chỉ là tối ưu hiệu năng.

Nếu muốn kiểm tra fail-fast trong môi trường thử nghiệm, có thể dùng:

~~~powershell
java -XX:AOTMode=on -XX:AOTCache=app.aot -Xlog:aot -cp app.jar com.example.Main
~~~

Trong JDK 26, on yêu cầu JVM nạp cache; nếu cache không tương thích, JVM báo lỗi và dừng thay vì chạy tiếp không có cache. Dùng chế độ này để xác nhận cache có được nạp hay không trong môi trường kiểm thử. Không chọn nó cho Production nếu hệ thống cần khả năng fallback.

### Xác nhận cache thực sự được dùng

Chạy với log:

~~~powershell
java -XX:AOTMode=auto -XX:AOTCache=app.aot -Xlog:aot -cp app.jar com.example.Main
~~~

Đọc thông báo AOT trong log để xác nhận cache được nạp hay bị bỏ qua. Nếu cần xác minh nghiêm ngặt, chạy thêm lần thử với AOTMode=on trên cùng cấu hình thử nghiệm để JVM dừng khi không thể nạp cache.

Không dùng riêng việc ứng dụng khởi động thành công làm bằng chứng rằng cache đã được sử dụng. Với auto, ứng dụng vẫn có thể khởi động bình thường sau khi JVM bỏ qua cache.

## 7. Cách rút gọn: AOTCacheOutput từ JDK 25

JEP 514 – Ahead-of-Time Command-Line Ergonomics được đưa vào JDK 25. Nó bổ sung tùy chọn AOTCacheOutput để kết hợp Training và Assembly vào một lệnh:

~~~powershell
java -XX:AOTCacheOutput=app.aot -cp app.jar com.example.Main --training
~~~

Khi dùng tùy chọn này trong chế độ auto mặc định, JVM chuyển sang quá trình record, chạy ứng dụng để huấn luyện, rồi khởi chạy JVM thứ hai để tạo cache. File cấu hình tạm được JVM quản lý nếu không chỉ định AOTConfiguration riêng.

Production vẫn dùng cache theo cách thông thường:

~~~powershell
java -XX:AOTCache=app.aot -cp app.jar com.example.Main
~~~

Cần hiểu rõ:

- AOTCacheOutput chỉ rút gọn lệnh; Training và Assembly vẫn là hai công việc khác nhau.
- Lệnh tạo cache một lần vẫn phải chạy ứng dụng qua workload đại diện.
- JVM thứ hai thực hiện Assembly sau Training.
- Có thể truyền thêm VM options cho JVM Assembly qua biến môi trường JDK_AOT_VM_OPTIONS.
- Nếu cần tách máy hoặc tách tài nguyên giữa huấn luyện và tạo cache, dùng quy trình ba bước tường minh ở các phần trước.

Trong JDK 26, cả quy trình ba bước lẫn AOTCacheOutput đều có thể dùng. Hãy chọn ba bước khi cần lưu, kiểm tra và chuyển file cấu hình huấn luyện riêng; chọn AOTCacheOutput khi muốn tự động hóa quy trình tạo cache trên cùng môi trường.

## 8. Chọn auto hay chế độ fail-fast

Các giá trị AOTMode có ý nghĩa khác nhau:

| Giá trị | JDK 26 | Mục đích |
|---|---|---|
| auto | Mặc định; tự chọn record, on hoặc off theo tùy chọn và khả năng nạp cache | Chế độ Production linh hoạt |
| off | Không sử dụng AOT Cache; các tùy chọn AOT khác bị bỏ qua | Chạy đối chứng hoặc tắt cache |
| record | Chạy ứng dụng để thu thập dữ liệu huấn luyện | Training |
| create | Tạo cache từ file cấu hình; không chạy ứng dụng | Assembly |
| on | Bắt buộc nạp cache; lỗi nếu không thể nạp | Fail-fast trong kiểm thử |

Trong JDK 26, auto hoạt động như sau:

- Nếu chỉ định AOTCacheOutput, JVM chọn record và sau đó thực hiện Assembly.
- Nếu không chỉ định AOTCacheOutput nhưng cache có thể được nạp, JVM chọn on.
- Nếu không có cache có thể nạp, JVM chọn off.

Khi cache không thể nạp:

- Với auto, ứng dụng tiếp tục chạy mà không có AOT Cache.
- Với on, JVM báo lỗi và thoát.

Đối với Production, ưu tiên auto nếu yêu cầu độ sẵn sàng của ứng dụng quan trọng hơn việc bắt buộc cache phải được nạp. Dùng on để kiểm tra tương thích hoặc triển khai fail-fast có chủ đích, sau khi đã kiểm soát chặt cấu hình JVM.

## 9. Điều kiện tương thích giữa Training và Production

AOT Cache là artifact gắn với ứng dụng và môi trường tạo ra nó. Các yếu tố cần giữ nhất quán:

| Yếu tố | Yêu cầu |
|---|---|
| JDK | Tạo và dùng cache bằng cùng JDK release |
| OS và CPU | Dùng đúng hệ điều hành và kiến trúc tương thích |
| Ứng dụng | Cùng phiên bản ứng dụng và dependency |
| Classpath / JAR | Không thay đổi classpath hoặc nội dung JAR sau khi tạo cache |
| Module path | Giữ module graph và cấu hình module tương thích |
| JVM options | Giữ các tùy chọn ảnh hưởng đến class loading, linking và AOT |
| Agent / instrumentation | Xác minh các agent và hook không làm cache mất tương thích |
| Workload | Training phải đại diện cho workload Production |

Nếu thay JAR, cập nhật thư viện, đổi module path hoặc nâng JDK, hãy tạo lại cache. Không tái sử dụng file cache cũ chỉ vì tên file hoặc đường dẫn vẫn giống nhau.

Một số VM options phục vụ chẩn đoán hoặc JVMTI agent có thể làm cache không nạp được. AOT Cache là tối ưu hóa; không có cam kết rằng mọi tổ hợp JVM options đều tương thích. Khi gặp mismatch, dùng -Xlog:aot để biết lý do JVM bỏ cache.

Tùy chọn AOTClassLinking cho phép JVM thực hiện thêm tối ưu hóa liên kết class, ví dụ giải quyết trước một số invokedynamic instruction. Khi dùng AOTMode, AOTClassLinking được bật tự động trong JDK 26. Cấu hình này có thể tăng hiệu quả startup/warm-up nhưng cũng làm tăng các điều kiện tương thích. Chỉ tắt bằng -XX:-AOTClassLinking khi có lý do tương thích rõ ràng và đã đo kiểm; không thay đổi tùy chọn giữa Training và Production một cách tùy tiện.

## 10. Dữ liệu huấn luyện có ảnh hưởng thế nào đến hiệu quả?

Chất lượng cache phụ thuộc workload huấn luyện. Một cache tạo thành công chưa chắc đem lại cải thiện đáng kể nếu Training không phản ánh hành vi Production.

Ví dụ, một API service có nhiều nhóm chức năng nhưng Training chỉ gọi health endpoint. JVM có thể ghi nhận một phần rất nhỏ class và trạng thái khởi tạo. Khi Production nhận request thật, nhiều class khác vẫn phải nạp và nhiều method vẫn cần thu thập profile lúc chạy.

Để tăng chất lượng:

1. Chạy đầy đủ bước khởi tạo ứng dụng.
2. Gọi các endpoint quan trọng với payload đại diện.
3. Chạy các tác vụ nền thường xuyên.
4. Bao phủ các đường xử lý lỗi phổ biến.
5. Dùng cùng phiên bản dependency và cấu hình môi trường với Production.
6. Huấn luyện lại khi có thay đổi đáng kể về ứng dụng hoặc workload.

Không cố gắng ghi mọi nhánh hiếm bằng cách tạo workload không thực tế. Hãy ưu tiên các đường chạy có tần suất và ảnh hưởng lớn đến thời gian khởi động, thời gian xử lý request đầu tiên và warm-up.

## 11. Đo lường lợi ích và xác nhận cache

Đo lường phải tách rõ hiệu quả startup và warm-up. Một cache có thể cải thiện một chỉ số nhưng không thay đổi nhiều chỉ số khác.

Các chỉ số nên so sánh:

| Chỉ số | Ý nghĩa |
|---|---|
| Process startup time | Thời gian từ lúc khởi chạy JVM đến khi ứng dụng sẵn sàng |
| Time to first request | Thời gian đến khi request đầu tiên được xử lý ổn định |
| Time to steady state | Thời gian đến khi throughput/latency ổn định |
| CPU trong giai đoạn khởi động | Lượng CPU dùng để nạp class, khởi tạo object và warm-up |
| Throughput sau warm-up | Xác nhận cache không làm giảm hiệu năng steady-state |
| P95/P99 latency | Xác nhận độ trễ trong giai đoạn khởi động và sau khi ổn định |
| RSS / heap / disk | Đánh giá chi phí bộ nhớ và dung lượng cache |

Thiết kế phép đo:

- Dùng cùng phần cứng, JDK, OS, cấu hình heap, GC, classpath và workload.
- So sánh một lượt không dùng cache với một lượt dùng cache.
- Tách cold start và warm start nếu filesystem cache ảnh hưởng đến kết quả.
- Lặp lại nhiều lần và so sánh median/percentile, không chỉ lấy một lần chạy.
- Không đo cùng lúc với build, tải dependency hoặc tác vụ nền gây nhiễu.
- Ghi rõ cache có được nạp thành công trong từng lần đo.

Ví dụ chạy đối chứng không dùng AOT Cache:

~~~powershell
java -XX:AOTMode=off -cp app.jar com.example.Main
~~~

Chạy có cache:

~~~powershell
java -XX:AOTMode=auto -XX:AOTCache=app.aot -Xlog:aot -cp app.jar com.example.Main
~~~

Nếu cache không được nạp, loại lần đo đó khỏi nhóm “có cache” và điều tra log. Không báo cáo kết quả như thể AOT đã hoạt động.

## 12. AOT Cache, CDS, JIT và native image khác nhau thế nào?

| Cơ chế | Hoạt động | Kết quả |
|---|---|---|
| AOT Cache của HotSpot | Ghi nhận class, object và profile từ Training; nạp lại trong Production | Giảm công việc startup/warm-up; ứng dụng vẫn chạy trên JVM |
| CDS | Chia sẻ dữ liệu class đã được xử lý giữa các JVM | Giảm chi phí nạp và bộ nhớ cho class |
| JIT | Biên dịch method sang native code khi ứng dụng chạy và có đủ profile | Tối ưu mã theo hành vi runtime |
| Native image | Biên dịch ứng dụng thành executable native trong giai đoạn build bằng công nghệ như GraalVM Native Image | Chạy executable native, có mô hình runtime khác JVM HotSpot |

AOT Cache không thay thế JIT. JIT vẫn hoạt động và có thể sử dụng method profile đã lưu để tối ưu sớm hơn. AOT Cache cũng không phải quy trình tạo native image; không cần thay đổi cách đóng gói ứng dụng thành executable native để sử dụng cache này.

CDS là một phần nền tảng của các tối ưu class sharing. AOT Cache mở rộng khả năng đó với dữ liệu object và profile. Với ứng dụng Java chạy trên HotSpot, hãy ưu tiên quy trình AOT Cache hiện hành khi mục tiêu là cải thiện startup và warm-up, thay vì sao chép các hướng dẫn AppCDS cũ mà không kiểm tra JDK.

## 13. JDK 27 – điểm cần kiểm tra khi nâng cấp

JDK 27 tiếp tục hỗ trợ AOT Cache và giữ mô hình Training, Assembly, Production. Tuy nhiên, tên chế độ bắt buộc nạp cache đã được cập nhật:

| Nội dung | JDK 26 | JDK 27 |
|---|---|---|
| Chế độ fail-fast | AOTMode=on | AOTMode=required |
| on | Giá trị chính thức trong danh sách mode | Alias của required; tài liệu khuyến cáo không dùng vì có thể bị deprecated/removed |
| auto | Nếu cache nạp được thì chọn on | Nếu cache nạp được thì chọn required |
| Fallback của auto | Chạy không có cache khi cache không tương thích | Vẫn tiếp tục chạy không có cache |
| record/create | Có | Có |

Khi nâng cấp lên JDK 27:

1. Tạo lại AOT Cache bằng chính JDK 27.
2. Dùng lại workload Training phù hợp với bản ứng dụng sẽ triển khai.
3. Cập nhật lệnh fail-fast từ AOTMode=on sang AOTMode=required.
4. Kiểm tra lại log AOT và khả năng nạp cache.
5. Không dùng cache được tạo từ JDK 26 cho runtime JDK 27.

Ví dụ Production fail-fast bằng JDK 27:

~~~powershell
java -XX:AOTMode=required -XX:AOTCache=app.aot -Xlog:aot -cp app.jar com.example.Main
~~~

Ví dụ Production có fallback:

~~~powershell
java -XX:AOTMode=auto -XX:AOTCache=app.aot -Xlog:aot -cp app.jar com.example.Main
~~~

Đối với triển khai cần khả năng fallback, giữ auto. Chỉ dùng required khi cache là điều kiện bắt buộc và pipeline đã kiểm tra tương thích.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không có file .aotconfig | Training chưa kết thúc, đường dẫn sai hoặc không có quyền ghi | Kiểm tra record mode, log và quyền thư mục |
| Create báo không đọc được config | File cấu hình thiếu, sai đường dẫn hoặc không tương ứng với ứng dụng | Tạo lại Training bằng đúng JDK và classpath |
| Không tạo được .aot | Assembly lỗi, không đủ dung lượng hoặc cấu hình không hợp lệ | Đọc log create, kiểm tra file đầu vào và quyền ghi |
| Production chạy nhưng không có lợi ích | auto bỏ qua cache hoặc workload huấn luyện không đại diện | Dùng -Xlog:aot và chạy kiểm thử fail-fast |
| JVM báo cache không tương thích | Khác JDK, OS/CPU, ứng dụng, classpath hoặc VM options | Tạo lại cache trên môi trường đích |
| Cache cũ không còn dùng được sau khi cập nhật JAR | Cache gắn với phiên bản ứng dụng và classpath | Tạo lại sau mỗi lần thay đổi dependency |
| Training và Production cho kết quả khởi tạo khác nhau | Khác system properties, cấu hình hoặc workload | Chuẩn hóa cấu hình và kiểm thử cùng đường khởi tạo |
| AOTMode=on không hợp lệ trên JDK 27 trong tương lai | JDK 27 đã khuyến cáo dùng required | Dùng AOTMode=required cho fail-fast |
| Cache không tạo được lợi ích với workload ZGC cũ | Cache được tạo trước hỗ trợ GC độc lập | Tạo lại cache bằng JDK 26 trở lên và đo lại |
| Hiệu năng warm-up không cải thiện | Workload Training không ghi nhận method profile hữu ích hoặc ứng dụng ít warm-up | Mở rộng workload đại diện, đo lại và kiểm tra log |

## 15. Bài thực hành tổng hợp

Thực hiện với JDK 26:

1. Build một ứng dụng Java đơn giản đóng gói trong app.jar.
2. Chạy Training bằng AOTMode=record và ghi app.aotconfig.
3. Chạy workload gồm các chức năng chính, không chỉ gọi main method rồi thoát ngay.
4. Chạy Assembly bằng AOTMode=create và tạo app.aot.
5. Chạy Production bằng AOTCache và bật -Xlog:aot.
6. Chạy lại Production với AOTMode=on để kiểm tra fail-fast trong môi trường thử nghiệm.
7. Chạy đối chứng với AOTMode=off và ghi thời gian startup.
8. So sánh các lần chạy có cache và không cache bằng cùng workload.
9. Thử thay đổi một dependency JAR, tạo lại cache và kiểm tra cache cũ không còn là artifact phù hợp.
10. Thử AOTCacheOutput để kết hợp Training và Assembly thành một lệnh.
11. Nếu có môi trường ZGC, tạo cache bằng JDK 26 và kiểm tra AOT object caching hoạt động với collector này.
12. Tạo lại cache bằng JDK 27, đổi chế độ fail-fast sang required và kiểm tra log.

**Tiêu chí hoàn thành:** giải thích được nhiệm vụ của Training, Assembly và Production; tạo được .aotconfig và .aot bằng đúng lệnh; dùng cache trong Production; phân biệt auto fallback với on/required fail-fast; biết AOT Cache phụ thuộc vào JDK, ứng dụng, OS và CPU; thiết kế workload huấn luyện đại diện; xác nhận lợi ích bằng đo lường; phân biệt AOT Cache của HotSpot với CDS, JIT và native image; cập nhật quy trình đúng khi chuyển từ JDK 26 sang JDK 27.

## 16. Tài liệu tham khảo chính thức

- [JEP 483: Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483) — nền tảng AOT Cache, các giai đoạn huấn luyện, tạo cache và chạy sử dụng.
- [JEP 514: Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514) — AOTCacheOutput và cách rút gọn thao tác tạo cache trong JDK 25.
- [JEP 515: Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515) — lưu method execution profiles vào AOT Cache để hỗ trợ warm-up.
- [JEP 516: Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516) — hỗ trợ AOT object caching với mọi GC, gồm ZGC, trong JDK 26.
- [Java 26 java Command – Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — cú pháp và hành vi AOTMode, AOTConfiguration, AOTCache, AOTCacheOutput, AOTClassLinking.
- [Java 27 java Command – Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — khác biệt AOTMode=required và hành vi auto trong JDK 27.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) — thay đổi AOT object caching với mọi garbage collector.
- [Inside.java: Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/) — ví dụ triển khai AOT Cache, JEP 514/515 và các lưu ý tương thích.

Các tùy chọn AOT Cache dạng -XX là tùy chọn của HotSpot, không phải hợp đồng portable cho mọi JVM. Luôn kiểm tra java command và tài liệu của đúng JDK đang chạy. AOT Cache chỉ là tối ưu hóa: ứng dụng phải tiếp tục đúng về chức năng khi cache không được nạp, trừ khi hệ thống chủ động chọn chế độ fail-fast.

