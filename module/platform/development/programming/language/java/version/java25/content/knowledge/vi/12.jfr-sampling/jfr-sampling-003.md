# Cooperative sampling trong JDK 25 và ý nghĩa của thời điểm lấy mẫu an toàn

## 1. Mục tiêu của bài học

Khi một ứng dụng Java chậm, câu hỏi đầu tiên thường là: CPU đang tiêu tốn thời gian ở đâu? Một profiler có thể lấy mẫu các stack trace trong lúc chương trình chạy, rồi tổng hợp các method xuất hiện thường xuyên để chỉ ra vùng mã nóng (*hot code*). Tuy nhiên, việc dừng một thread tại một lệnh máy bất kỳ và đọc stack của nó không phải lúc nào cũng an toàn. JVM chỉ bảo đảm stack có thể được duyệt tại những vị trí đã biết cấu trúc frame và trạng thái thực thi.

Trong **JDK 25**, **JFR Cooperative Sampling** (JEP 518) cải tiến cơ chế lấy mẫu method của HotSpot. Ý tưởng cốt lõi là tách hai thời điểm:

- **Thời điểm lấy mẫu logic:** lúc sampler ghi nhận vị trí thực thi của thread cần quan sát.
- **Thời điểm duyệt stack an toàn:** lúc chính thread được lấy mẫu đi tới một safepoint poll và có thể phối hợp tạo stack trace.

Cơ chế này giúp JFR lấy thông tin đại diện cho vị trí thực thi đã được yêu cầu, trong khi việc duyệt stack diễn ra ở vị trí JVM biết là an toàn. Nhờ vậy, JFR giảm safepoint bias và cải thiện độ ổn định khi lấy mẫu, kể cả với ZGC. JEP 518 là cải tiến đã được đưa vào JDK 25; đây không phải API preview mà ứng dụng cần bật bằng `--enable-preview`.

Bài **Cooperative sampling trong JDK 25 và ý nghĩa của thời điểm lấy mẫu an toàn** thuộc chương **Lấy mẫu JFR** của module **JAVA_VERSION_JAVA25**. Bài tập trung vào JFR trong HotSpot JDK 25, cách hiểu `jdk.ExecutionSample`, `jdk.SafepointLatency`, quy trình ghi và đọc recording, cùng giới hạn của kết quả thống kê.

### Sau bài này, bạn có thể

1. Giải thích sampling là kỹ thuật thống kê và phân biệt sample với method invocation.
2. Mô tả safepoint, safepoint poll và vì sao JVM cần vị trí stack có thể duyệt an toàn.
3. Giải thích cooperative sampling theo JEP 518: sampler ghi nhận vị trí, thread mục tiêu tiếp tục chạy và tự hoàn tất stack walk ở poll phù hợp.
4. Phân biệt safepoint safety với safepoint bias; hiểu tại sao chỉ lấy mẫu tại poll point có thể làm profile thiếu đại diện.
5. Đọc `jdk.ExecutionSample` và `jdk.SafepointLatency` để phân tích profile và độ trễ tới poll.
6. Tạo JFR recording bằng `-XX:StartFlightRecording`, `jcmd` và `jfr`.
7. Nhận biết giới hạn với native code, thread đang chờ, sample bị bỏ lỡ và overhead của recording.
8. Phân biệt JEP 518 với JEP 509 CPU-Time Profiling (Experimental) và chọn đúng công cụ cho câu hỏi hiệu năng.

> **Phạm vi phiên bản:** các lệnh và event chính trong bài nhắm tới JDK 25 HotSpot. JFR Cooperative Sampling (JEP 518) là cải tiến nền tảng của JFR trong JDK 25. JFR CPU-Time Profiling (JEP 509) là tính năng **experimental**, chỉ dành cho Linux trong JDK 25; bài chỉ giới thiệu để phân biệt, không coi đây là nền tảng ổn định bắt buộc cho production. Không dùng cờ preview cũ hoặc API nội bộ HotSpot trong ứng dụng.

## 2. Sampling là gì và nó trả lời câu hỏi nào?

**Sampling** là kỹ thuật quan sát chương trình bằng cách chụp trạng thái thực thi tại các thời điểm được chọn. Với method profiling, một sample thường chứa:

- Thread được lấy mẫu.
- Stack trace tại vị trí sample.
- Trạng thái thread.
- Timestamp của sample.

Nếu một method xuất hiện trong nhiều sample, method đó có thể đang chiếm phần đáng kể thời gian thực thi trong workload đã ghi. Đây là dấu hiệu để điều tra, không phải phép đo chính xác số lần method được gọi hoặc thời gian chạy tuyệt đối của method.

Ví dụ một call tree:

~~~text
HTTP worker
  └── OrderController.handle()
       └── OrderService.submit()
            ├── PricingService.calculate()
            │    └── TaxEngine.compute()
            └── InventoryService.reserve()
~~~

Giả sử trong recording, stack có `TaxEngine.compute()` xuất hiện nhiều hơn `InventoryService.reserve()`. Điều đó gợi ý phần tính thuế là nơi đáng kiểm tra trong workload này. Nó không chứng minh `TaxEngine.compute()` được gọi đúng số lần sample, cũng không chứng minh mỗi lần gọi có thời lượng bằng nhau.

### 2.1. Sample không phải invocation counter

| Dữ liệu | Ý nghĩa | Không thể suy ra trực tiếp |
| --- | --- | --- |
| 1 `jdk.ExecutionSample` | Một snapshot stack tại một thời điểm lấy mẫu | Method ở top frame được gọi đúng một lần |
| 100 samples có một method | Method xuất hiện thường xuyên trong các snapshot | Method chạy chính xác 100 lần |
| Một frame xuất hiện ở nhiều stack | Method có thể nằm trên đường thực thi nóng | Method đó luôn là nguyên nhân gốc |
| Không thấy method trong recording | Không có sample nào ghi nhận method đó | Method chưa từng chạy |
| Thời gian giữa hai sample | Khoảng cách theo cấu hình sampling | CPU time chính xác của method |

Sampling đặc biệt hữu ích để **xếp hạng nơi cần điều tra** trong ứng dụng đang chạy. Để đo latency của một thao tác cụ thể, cần xem thêm event có duration, request trace, benchmark hoặc instrumentation phù hợp.

### 2.2. Sampling khác tracing và timing

- **Sampling:** lấy snapshot theo chu kỳ hoặc theo yêu cầu; thích hợp để tìm vùng nóng mà không instrument mọi invocation.
- **Method timing:** đo thời gian của những invocation được instrument; có thể tạo lượng event lớn nếu bật quá rộng.
- **Tracing:** nối các bước xử lý thành một đường đi nghiệp vụ, thường theo request/trace ID.
- **JFR event duration:** một event có `begin()`/`end()` có thể ghi khoảng thời gian của một hoạt động cụ thể.

JFR có thể thu thập nhiều loại event trong cùng recording, nhưng mỗi loại trả lời một câu hỏi khác nhau. Không diễn giải số lượng `jdk.ExecutionSample` thành latency của một request.

## 3. Safepoint trong HotSpot là gì?

JVM cần những vị trí mà thread có thể tạm dừng và trạng thái thực thi được mô tả đầy đủ. Trong HotSpot, các vị trí đó gắn với **safepoint** và các **safepoint poll**.

Một safepoint là trạng thái mà JVM có thể thực hiện các thao tác cần trạng thái thread nhất quán, ví dụ một số hoạt động runtime hoặc garbage collection. Một safepoint poll là điểm trong luồng mã nơi thread kiểm tra xem JVM có yêu cầu nó đi vào xử lý safepoint hay không.

Các poll point thường xuất hiện ở những vị trí như:

- Đầu vòng lặp trong mã được biên dịch.
- Điểm method return.
- Một số điểm chuyển trạng thái giữa Java và JVM/native.
- Các vị trí khác do compiler/runtime đặt để bảo đảm quy tắc safepoint.

Không phải mọi bytecode hoặc mọi instruction máy đều là safepoint poll. JVM không thể giả định rằng stack luôn có thể được duyệt an toàn tại mọi program counter.

### 3.1. Vì sao stack chỉ an toàn ở một số vị trí?

Một stack trace gồm nhiều stack frame. Để đi từ frame hiện tại tới caller frame, JVM cần biết cấu trúc frame, vị trí stack pointer và metadata mô tả frame.

Trong một method đã biên dịch, compiler có thể tạm thời thay đổi stack trong phần prologue/epilogue. Một số đoạn mã nội bộ, stub hoặc intrinsic cũng có cấu trúc đặc thù. Nếu sampler dừng thread đúng giữa một thay đổi stack mà vẫn cố diễn giải frame như thể nó ở trạng thái ổn định, kết quả có thể sai hoặc thậm chí không an toàn.

Tại safepoint poll phù hợp, JVM bảo đảm các invariant cần thiết để duyệt stack. Đây là lý do việc chờ tới điểm an toàn có giá trị đối với sự ổn định của profiler.

### 3.2. Safepoint poll không đồng nghĩa toàn JVM luôn dừng

Khi nghe “safepoint”, nhiều người liên tưởng ngay tới một lần Stop-the-World của GC. Nhưng trong JEP 518, cơ chế lấy mẫu tận dụng khả năng kiểm soát poll theo từng thread. Thread mục tiêu có thể được yêu cầu xử lý sample request tại poll của chính nó.

Vì vậy, khi đọc về cooperative sampling:

- Không nên hiểu rằng mỗi sample đều buộc toàn bộ JVM dừng.
- Không nên đồng nhất `SafepointLatency` với thời gian pause của một GC.
- Cần phân biệt một thread đi tới poll của nó với một global safepoint phục vụ một thao tác JVM toàn cục.

Đây là khác biệt quan trọng để không gán nhầm một độ trễ lấy mẫu thành pause toàn ứng dụng.

## 4. Safepoint bias: vì sao chỉ lấy mẫu tại điểm an toàn vẫn chưa đủ?

Nếu profiler chỉ chụp stack đúng tại các safepoint poll, profiler có thể bỏ qua phần lớn thời gian thực thi giữa các poll. Những vị trí có nhiều poll sẽ xuất hiện thường xuyên hơn các vùng mã ít poll. Profile khi đó phản ánh **vị trí có poll** thay vì phản ánh đầy đủ **vị trí chương trình thực sự đang chạy**.

Hiện tượng này gọi là **safepoint bias**.

Ví dụ:

~~~text
Method A:
  loop header ---- work ---- work ---- work ---- poll
       ^ nhiều thời gian nằm giữa các poll

Method B:
  poll ---- short work ---- poll ---- short work ---- poll
       ^ poll xuất hiện dày hơn so với lượng công việc
~~~

Nếu lấy sample trực tiếp tại poll, method B có thể được đại diện quá mức trong profile. Method A có thể đang tiêu thụ CPU đáng kể nhưng không được quan sát đúng tỷ lệ.

### 4.1. Hai yêu cầu có vẻ mâu thuẫn

Một profiler muốn đồng thời đạt hai điều:

1. **An toàn:** chỉ duyệt stack tại vị trí JVM bảo đảm frame nhất quán.
2. **Đại diện:** sample phản ánh vị trí thực thi được chọn theo thời điểm lấy mẫu, không chỉ phản ánh nơi có safepoint poll.

Cách lấy mẫu truyền thống chỉ chọn poll point có thể an toàn nhưng thiên lệch. Ngược lại, cố duyệt stack tại bất kỳ instruction nào có thể tăng độ rủi ro và cần nhiều kiểm tra bảo vệ.

JEP 518 thiết kế một quy trình để tách thời điểm ghi nhận vị trí sample khỏi thời điểm stack được duyệt.

## 5. Cooperative sampling hoạt động như thế nào?

Tên **cooperative** nhấn mạnh rằng sampler thread và thread được lấy mẫu cùng tham gia hoàn tất một sample. Sampler không phải tự duyệt toàn bộ stack tại vị trí bất kỳ.

~~~mermaid
sequenceDiagram
    autonumber
    participant S as JFR sampler
    participant T as Thread mục tiêu
    participant J as JFR recording

    S->>T: Yêu cầu sample tại thời điểm t
    S->>S: Ghi snapshot PC/SP và timestamp
    S->>T: Đưa sample request vào hàng đợi riêng của thread
    S->>T: Arm poll page của thread
    S-->>T: Cho thread tiếp tục chạy
    T->>T: Thực thi mã bình thường
    T->>T: Đi tới safepoint poll kế tiếp
    T->>T: Xử lý sample request và tái dựng stack
    T->>J: Ghi jdk.ExecutionSample
    T->>J: Có thể ghi jdk.SafepointLatency
~~~

Diễn giải ở mức khái niệm:

1. Sampler chọn thread và ghi nhận vị trí thực thi tại thời điểm sample.
2. Nó tạo một request mô tả vị trí đó, bao gồm program counter, stack pointer và timestamp; với interpreter frame còn có thông tin bytecode cần thiết.
3. Request được đưa vào cấu trúc gắn với thread mục tiêu.
4. Poll page của thread được arm để thread sẽ xử lý request khi đi tới poll thích hợp.
5. Thread mục tiêu tiếp tục chạy luồng mã bình thường cho đến poll kế tiếp.
6. Tại poll, thread đang ở vị trí stack có thể duyệt an toàn. Nó tái dựng stack trace đại diện cho vị trí đã ghi nhận trước đó.
7. JFR ghi event sample với timestamp gắn với thời điểm yêu cầu, thay vì coi thời điểm poll đến là thời điểm thực thi được lấy mẫu.

Điểm quan trọng là **stack walk xảy ra ở vị trí an toàn**, nhưng top frame được tái dựng theo program counter của sample request. Nhờ đó, kết quả có thể đại diện cho một vị trí thực thi không trùng với poll point.

### 5.1. Sampler ghi nhận gì?

Trong thiết kế JEP 518, sample request mô tả trạng thái đã lấy mẫu. Với compiled frame, thông tin cốt lõi gồm:

- `pc`: program counter tại vị trí sample.
- `sp`: stack pointer của frame.
- `ticks`: timestamp của sample.

Với interpreter frame, request còn cần bytecode program counter (BCP) và thông tin frame tương ứng.

Đây là chi tiết triển khai HotSpot, không phải API để ứng dụng tự tạo hoặc chỉnh sample request. Người dùng JFR không nên phụ thuộc vào cấu trúc nội bộ này trong code production.

### 5.2. Vì sao thread mục tiêu phải phối hợp?

Khi thread mục tiêu đi tới poll, stack của nó đã ở một trạng thái JVM có thể diễn giải. Thread đó có thể tái dựng vị trí sample đã ghi nhận mà không buộc sampler phải đoán cấu trúc frame ở một instruction tùy ý.

Việc chuyển phần nặng của stack walk sang thread mục tiêu giúp giảm công việc của sampler và cho phép JFR thực hiện stack walk tại vị trí đã được JVM định nghĩa an toàn.

### 5.3. Cooperative không có nghĩa ứng dụng phải gọi API

Developer không cần chèn `checkpoint()`, `poll()` hoặc lời gọi JFR vào mọi method. Đây là cơ chế phối hợp giữa các thành phần bên trong HotSpot/JFR. Ứng dụng chỉ cần chạy trên JDK có hỗ trợ và cấu hình recording phù hợp.

Không tự viết một vòng lặp gọi API nội bộ để “hỗ trợ” profiler; đó không phải cách sử dụng JFR.

## 6. Vì sao JEP 518 giảm bias nhưng không biến sampling thành phép đo tuyệt đối?

JEP 518 giảm sự phụ thuộc của kết quả vào vị trí poll vì sample request lưu program counter tại thời điểm được chọn. Khi stack được tái dựng ở poll sau, JFR có thể đưa frame đại diện cho vị trí ban đầu vào stack trace.

Tuy nhiên, sampling vẫn là một kỹ thuật thống kê:

- Sample được lấy theo chu kỳ hoặc lịch lấy mẫu, không phải tại mọi instruction.
- Có thể có sample request không hoàn tất hoặc không tạo được stack trace.
- Các vùng native code có quy tắc và đường xử lý khác.
- Tần suất sample, workload, JIT compilation và trạng thái thread ảnh hưởng đến dữ liệu.
- Một recording ngắn hoặc workload không đại diện có thể dẫn tới kết luận sai.

Do đó, diễn giải đúng là **JFR giảm safepoint bias và cải thiện tính an toàn/khả năng mở rộng của method sampling**, không phải “JFR đã loại bỏ mọi bias và đo chính xác 100% CPU time cho từng method”.

## 7. Event cần biết: jdk.ExecutionSample

`jdk.ExecutionSample` ghi snapshot của thread đang thực thi Java code. Đây là event quan trọng để đọc method profile.

Các trường thường được quan tâm:

| Trường | Ý nghĩa |
| --- | --- |
| `startTime` | Thời điểm sample được ghi nhận |
| `sampledThread` | Thread được lấy mẫu |
| `state` | Trạng thái thread tại sample |
| `stackTrace` | Stack trace đại diện cho vị trí sample |

Event này phản ánh thread đang thực thi Java code. Thread đang chờ hoặc đang thực thi native code không nằm trong tập `ExecutionSample` theo cùng cách. Để quan sát native method sample, JFR có event `jdk.NativeMethodSample`; JDK 25 còn có JEP 509 CPU-Time Profiling (Experimental) với event riêng trên Linux.

Trong các cấu hình JDK 25 được tham chiếu, `jdk.ExecutionSample` được bật theo profile và default settings với chu kỳ khác nhau (thường profile dày hơn default). Hãy kiểm tra `.jfc` thực tế của distribution đang chạy thay vì hardcode giả định về chu kỳ.

### 7.1. Đọc một sample

Ví dụ minh họa:

~~~text
jdk.ExecutionSample {
  startTime = 10:15:30.120
  sampledThread = "http-worker-3"
  state = "STATE_RUNNABLE"
  stackTrace = [
    com.acme.tax.TaxEngine.compute(...)
    com.acme.order.OrderService.submit(...)
    com.acme.web.OrderController.handle(...)
  ]
}
~~~

Đây là dữ liệu minh họa để hiểu cấu trúc, không phải output được bảo đảm giống hệt trên mọi JDK build.

Có thể đọc theo thứ tự:

1. Thread nào được lấy mẫu?
2. Thread đang runnable hay ở trạng thái khác?
3. Top frame là method nào?
4. Caller chain có chỉ ra đường đi nghiệp vụ nào?
5. Method xuất hiện trong bao nhiêu sample trong khoảng recording?
6. Có các event khác như allocation, lock, I/O hoặc GC hỗ trợ giải thích không?

Đừng kết luận method chậm chỉ vì nó xuất hiện ở nhiều stack. Có thể method đó là wrapper/caller của một method con thực sự tiêu thụ CPU. Hãy xem cả stack và những frame sâu hơn.

## 8. Event mới liên quan: jdk.SafepointLatency

JEP 518 bổ sung event `jdk.SafepointLatency` để ghi nhận khoảng thời gian từ lúc có asynchronous sampling interrupt tới khi thread đạt safepoint poll tiếp theo và xử lý sample request.

Event này giúp quan sát một phần quan trọng của sampling pipeline: thread mất bao lâu để tới poll tiếp theo.

### 8.1. Đọc duration như thế nào?

Ví dụ minh họa:

~~~text
jdk.SafepointLatency {
  startTime = 10:15:30.120
  duration = 0.028 ms
  threadState = "_thread_in_Java"
  eventThread = "http-worker-3"
  stackTrace = [
    com.acme.tax.TaxEngine.compute(...)
    com.acme.order.OrderService.submit(...)
  ]
}
~~~

`duration` là độ trễ tới poll theo định nghĩa của event. Nó **không phải** thời gian toàn bộ ứng dụng dừng, không phải GC pause và không phải latency của request HTTP.

### 8.2. Khi nào event này hữu ích?

- Kiểm tra thread có thường xuyên mất nhiều thời gian mới tới poll hay không.
- So sánh độ trễ tới poll giữa các workload.
- Điều tra trường hợp sample request bị trì hoãn.
- Hiểu thêm về hành vi sampling khi method chạy lâu hoặc thread có trạng thái thực thi đặc biệt.
- Đối chiếu timestamp và stack trace của `ExecutionSample` với latency event liên quan.

Không cần bật event này trong mọi recording liên tục. Hãy bật khi cần khảo sát sampling latency hoặc khi đang phân tích một vấn đề cụ thể; theo dõi kích thước recording và overhead.

## 9. Thực hành 1 — ghi profile method bằng JFR trên JDK 25

Giả sử ứng dụng đã có artifact chạy được là `orders.jar`.

### 9.1. Xác nhận đúng JDK và công cụ

~~~bash
java -version
jfr --version
jcmd -l
~~~

Dùng JDK 25 để chạy ứng dụng và công cụ JFR cùng phiên bản tương thích. Trên một máy có nhiều JDK, kiểm tra `java` và `jfr` có cùng toolchain; nếu không, hãy gọi executable theo đường dẫn `JAVA_HOME/bin`.

### 9.2. Ghi profile trong một khoảng thời gian

~~~bash
java \
  -XX:StartFlightRecording:settings=profile,filename=orders-profile.jfr,duration=60s \
  -jar orders.jar
~~~

Trên PowerShell, có thể dùng một dòng:

~~~powershell
java '-XX:StartFlightRecording:settings=profile,filename=orders-profile.jfr,duration=60s' -jar orders.jar
~~~

`settings=profile` thu thập nhiều dữ liệu hơn cấu hình `default`, phù hợp với một lần profiling ngắn. Không nên bật profile dày hơn mức cần thiết trong một recording chạy liên tục mà không đánh giá chi phí và dung lượng.

### 9.3. Đọc recording

~~~bash
jfr summary orders-profile.jfr
jfr print --events jdk.ExecutionSample orders-profile.jfr
~~~

Nếu cần stack sâu hơn:

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 64 orders-profile.jfr
~~~

Để xem danh sách view có sẵn trong file:

~~~bash
jfr view all-views orders-profile.jfr
~~~

Sau đó chọn một view được công cụ hỗ trợ, hoặc dùng JDK Mission Control để xem flame graph, call tree và event timeline. Tên view có thể khác theo JDK build và nội dung recording; kiểm tra `all-views` thay vì đoán tên.

## 10. Thực hành 2 — bật SafepointLatency để phân tích thời điểm poll

Event `jdk.SafepointLatency` không nhất thiết được bật trong recording mặc định. Có thể bật rõ ràng khi khởi động JVM.

~~~bash
java \
  -XX:StartFlightRecording:settings=profile,filename=safepoint-latency.jfr,duration=60s,jdk.SafepointLatency#enabled=true \
  -jar orders.jar
~~~

Trên PowerShell:

~~~powershell
java '-XX:StartFlightRecording:settings=profile,filename=safepoint-latency.jfr,duration=60s,jdk.SafepointLatency#enabled=true' -jar orders.jar
~~~

Sau khi recording kết thúc:

~~~bash
jfr print --events jdk.SafepointLatency safepoint-latency.jfr
~~~

Nếu cần kiểm tra cùng với execution samples:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.SafepointLatency safepoint-latency.jfr
~~~

### 10.1. Đọc kết quả theo câu hỏi

| Quan sát | Câu hỏi tiếp theo |
| --- | --- |
| `ExecutionSample` có stack trace rõ | Method nào xuất hiện thường xuyên trong workload? |
| `SafepointLatency` có duration lớn | Thread đang ở đâu khi chờ poll? |
| Một số sample thiếu stack hoặc không xuất hiện | Có giới hạn event, thread state hay sample request bị bỏ lỡ? |
| Latency event chỉ xuất hiện ở một số thread | Workload hoặc trạng thái thread của chúng khác gì? |
| Nhiều event trong khoảng recording ngắn | Chu kỳ sampling và workload có đang tạo dữ liệu quá dày? |

Đừng coi một event duration cao đơn lẻ là bằng chứng chắc chắn của một lỗi JVM. Cần lặp lại recording, kiểm tra workload và đối chiếu với thread state, safepoint/GC events cùng dữ liệu ứng dụng.

## 11. Thực hành 3 — bắt đầu recording trên JVM đang chạy

Không phải lúc nào cũng có thể khởi động lại service chỉ để bật JFR. Có thể dùng `jcmd` nếu JVM cho phép attach diagnostic command và user có quyền phù hợp.

Liệt kê process Java:

~~~bash
jcmd -l
~~~

Bắt đầu recording:

~~~bash
jcmd <pid> JFR.start name=cooperative-profile settings=profile duration=60s filename=cooperative-profile.jfr
~~~

Trong lệnh trên, thay `<pid>` bằng process ID thực tế. Nếu cần bật `SafepointLatency`, có thể cấu hình event setting qua `JFR.start` theo cú pháp `jdk.SafepointLatency#enabled=true`, hoặc dùng file `.jfc` được chuẩn bị và kiểm tra trước.

Khi recording hoàn tất, đọc file bằng `jfr summary`, `jfr print` hoặc JDK Mission Control.

**Lưu ý:** attach có thể bị giới hạn trong container, quyền người dùng, security policy hoặc cấu hình JVM. Hãy xác nhận quy trình vận hành trước khi dùng trên production. Không bật attach hoặc mở cổng quản trị chỉ để thử nghiệm trên một hệ thống không được phép.

## 12. Cách hiểu “thời điểm sample” so với “thời điểm poll”

Đây là phần quan trọng nhất của JEP 518.

Giả sử sampler ghi nhận một thread tại thời điểm **t0**, trong khi thread đang chạy method `calculate()` ở vị trí **P**. Thread chỉ đi tới poll tiếp theo ở thời điểm **t1**.

~~~text
t0                         t1
|--------------------------|
sample request             next safepoint poll
PC = P                     stack walk is safe
timestamp = t0             thread reconstructs sample
                            event represents P at t0
~~~

Nếu profiler ghi event như thể vị trí thực thi chỉ là code tại poll ở `t1`, kết quả sẽ có safepoint bias. Với cooperative sampling, request lưu vị trí tại `t0`, còn stack được tái dựng ở `t1`. Timestamp của sample phản ánh thời điểm request, còn `SafepointLatency` giúp nhìn thấy khoảng chờ tới poll.

### 12.1. Vì sao không chỉ lấy stack ở t1?

Vì `t1` là vị trí thread đã tiếp tục chạy tới poll. Nó không nhất thiết là vị trí đang chạy tại `t0`. Nếu lấy top frame theo `t1`, sample sẽ bị kéo về những vị trí poll và không còn đại diện cho program counter được chọn.

### 12.2. Vì sao không duyệt stack trực tiếp tại t0?

Vì stack có thể đang ở trạng thái không phù hợp để diễn giải. Một số frame/prologue/epilogue hoặc đoạn mã nội bộ không bảo đảm metadata đủ để đi qua caller frame một cách an toàn.

JEP 518 giữ lại **vị trí logic tại t0** nhưng chờ **điều kiện an toàn tại t1** để tái dựng stack. Đó là sự kết hợp giữa tính đại diện và an toàn.

## 13. Giới hạn: native code và thread không quay lại poll

Cooperative sampling dựa vào việc thread mục tiêu đi tới poll phù hợp để xử lý request. Nếu thread đang chạy trong native code của thư viện bên thứ ba và chưa quay lại JVM, nó có thể chưa tới poll trong một khoảng thời gian dài.

Điều này cần được phân biệt với thread đang chạy Java code:

- `jdk.ExecutionSample` mô tả thread đang thực thi Java code.
- `jdk.NativeMethodSample` ghi snapshot của thread ở native code theo cơ chế JFR tương ứng.
- JDK 25 có thêm JEP 509 CPU-Time Profiling (Experimental) trên Linux, dùng CPU-time sampler để quan sát cả Java và native execution theo cách khác.

Một native call kéo dài có thể khiến cooperative request chờ tới khi thread chuyển về một điểm poll phù hợp. Không nên giả định mọi thread đang chạy native đều được xử lý giống một Java method loop.

### 13.1. Nếu nghi ngờ CPU tiêu tốn trong native code

Hãy kiểm tra:

1. `jdk.NativeMethodSample` trong recording.
2. Native library và call path liên quan.
3. JFR CPU-Time Profiling nếu chạy Linux và chấp nhận trạng thái experimental.
4. Profiling công cụ hệ điều hành/native phù hợp với nền tảng.
5. FFM/JNI boundary và thời gian thread ở native.

Không kết luận “không có sample Java nên CPU không được dùng”. CPU có thể đang chạy trong native library, VM runtime hoặc code không được event đang xem bao phủ.

## 14. JEP 509 CPU-Time Profiling (Experimental) khác JEP 518 ra sao?

JDK 25 có hai cải tiến JFR dễ bị nhầm:

| Tiêu chí | JEP 518 — Cooperative Sampling | JEP 509 — CPU-Time Profiling |
| --- | --- | --- |
| Mục tiêu | Cải thiện method sampling và stack walking an toàn | Bổ sung CPU-time profiling chính xác hơn |
| Trạng thái JDK 25 | Cải tiến JFR trong JDK 25 | **Experimental** |
| Phạm vi nền tảng | Cơ chế method sampling HotSpot | Linux trong JDK 25 |
| Event liên quan | `jdk.ExecutionSample`, `jdk.SafepointLatency` | `jdk.CPUTimeSample`, `jdk.CPUTimeSamplesLost` |
| Cách hiểu | Snapshot Java execution, stack được tái dựng ở poll an toàn | CPU-time sampler bao gồm Java và native execution |
| Có nên dùng mặc định production? | Có thể dùng JFR profiling theo quy trình vận hành | Chỉ thử nghiệm có kiểm soát và đánh giá tương thích |

JEP 509 sử dụng `SIGPROF` trên Linux để thu thập CPU-time samples. Nó xây dựng trên các cải tiến stack safety của JEP 518 nhưng có mục tiêu và trạng thái khác. Không bật một tính năng experimental chỉ vì đang học cooperative sampling.

Ví dụ thử nghiệm trên Linux:

~~~bash
java \
  -XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,filename=cpu-time.jfr \
  -jar orders.jar
~~~

Để xem view nếu JDK build hỗ trợ:

~~~bash
jfr view all-views cpu-time.jfr
~~~

Sau đó tìm view CPU-time tương ứng, hoặc in event:

~~~bash
jfr print --events jdk.CPUTimeSample cpu-time.jfr
~~~

Event `jdk.CPUTimeSample` có thể ghi các trường như `failed`, `samplingPeriod`, `biased`, thread và stack trace. `biased` cho biết sample có safepoint bias hay không; `failed` cho biết không lấy được stack trace. Do đây là tính năng experimental, phải kiểm tra event/setting thực tế của JDK distribution trước khi dùng trong automation hoặc production.

## 15. Vì sao SafepointLatency không phải GC pause?

Có ba khái niệm gần nhau nhưng khác nghĩa:

| Khái niệm | Đo lường | Không đồng nghĩa với |
| --- | --- | --- |
| `jdk.SafepointLatency` | Độ trễ từ sampling interrupt tới safepoint poll tiếp theo của thread | GC pause hoặc global safepoint duration |
| `jdk.GCPhasePause` / GC pause events | Khoảng dừng do một pha GC | Độ trễ một sample request |
| Request latency | Thời gian xử lý request từ góc nhìn ứng dụng | Stack sampling latency |

Một request có thể chậm vì GC pause, lock contention, I/O, queueing hoặc CPU. `SafepointLatency` chỉ giúp phân tích một phần trong đường lấy mẫu; nó không phải công cụ tổng hợp latency cho request.

Nếu cần điều tra pause toàn JVM, hãy xem các event safepoint/GC tương ứng trong JFR và đối chiếu với metrics của ứng dụng.

## 16. Tần suất lấy mẫu và ảnh hưởng tới recording

Tần suất sampling là một lựa chọn cân bằng:

- Chu kỳ ngắn hơn tạo nhiều sample hơn và tăng khả năng quan sát các method ngắn.
- Chu kỳ ngắn hơn cũng có thể tăng overhead, dung lượng recording và chi phí phân tích.
- Chu kỳ dài hơn giảm dữ liệu nhưng có thể bỏ qua hoạt động ngắn hoặc ít xảy ra.
- Một workload không ổn định có thể tạo profile khác nhau giữa các lần chạy.

Trong JDK 25, cấu hình JFR thường có `default.jfc` với mục tiêu overhead thấp cho recording liên tục và `profile.jfc` thu thập chi tiết hơn để profiling ngắn. Không có một chu kỳ duy nhất phù hợp cho mọi service.

### 16.1. Thay đổi period của ExecutionSample

Có thể đặt event setting ngay khi bắt đầu recording:

~~~bash
java \
  -XX:StartFlightRecording:settings=profile,filename=sample-10ms.jfr,duration=60s,jdk.ExecutionSample#period=10ms \
  -jar orders.jar
~~~

Trước khi thay chu kỳ, hãy xem cấu hình đang sử dụng. `period` là tần suất tối thiểu giữa các event định kỳ, không phải cam kết rằng mỗi khoảng 10 ms luôn có một sample thành công cho mọi thread.

### 16.2. Không tối ưu chu kỳ chỉ để tạo flame graph đẹp

Flame graph đẹp không đồng nghĩa profile chính xác. Hãy chọn tần suất theo mục tiêu, recording đủ lâu để bao phủ workload đại diện, và so sánh với một baseline. Nếu một method chỉ xuất hiện trong một sample ở recording ngắn, không nên kết luận nó là hotspot ổn định.

## 17. Phân tích sample trong JDK Mission Control

JFR recording có thể mở bằng **JDK Mission Control (JMC)** để xem:

- Method profiling / hot methods.
- Call tree và stack trace.
- Thread activity.
- Garbage collection.
- Lock contention.
- I/O và các event runtime liên quan.

Một quy trình phân tích gợi ý:

1. Mở recording `.jfr`.
2. Kiểm tra thời lượng, số event và khoảng thời gian recording.
3. Xem method profiling để tìm các method xuất hiện thường xuyên.
4. Chọn một method và mở call tree để hiểu caller.
5. Đối chiếu thread và trạng thái thực thi.
6. Kiểm tra event liên quan như allocation, lock, GC hoặc I/O.
7. Xác định một giả thuyết có thể kiểm chứng bằng benchmark/test.
8. Thay đổi code hoặc cấu hình rồi ghi recording lần nữa trong cùng workload.

Không sửa code chỉ dựa trên một bảng top methods. Một method có nhiều sample có thể chỉ là wrapper/caller của vùng nóng nằm sâu hơn. Xem cả call tree, thread state và các event liên quan.

## 18. Viết chương trình nhỏ để tạo workload có thể lấy mẫu

Ví dụ sau tạo một workload CPU-bound để quan sát stack. Đây là chương trình thực hành, không phải benchmark dùng để so sánh các CPU.

~~~java
public class SamplingWorkload {

    private static volatile long sink;

    static long hotMethod(long seed) {
        long value = seed;

        for (int i = 0; i < 2_000_000; i++) {
            value = Long.rotateLeft(value ^ i, 7) * 0x9E3779B97F4A7C15L;
        }

        return value;
    }

    static void serviceMethod() {
        long result = hotMethod(System.nanoTime());
        sink = result;
    }

    public static void main(String[] args) throws InterruptedException {
        long deadline = System.nanoTime() + 45_000_000_000L;

        while (System.nanoTime() < deadline) {
            serviceMethod();
        }

        System.out.println("Finished: " + sink);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 25 SamplingWorkload.java
java -XX:StartFlightRecording:settings=profile,filename=workload.jfr,duration=45s,jdk.SafepointLatency#enabled=true SamplingWorkload
~~~

Đọc sample:

~~~bash
jfr print --events jdk.ExecutionSample workload.jfr
jfr print --events jdk.SafepointLatency workload.jfr
jfr summary workload.jfr
~~~

### 18.1. Câu hỏi quan sát

- `hotMethod()` có xuất hiện trong stack trace không?
- Caller của nó là method nào?
- Thread `main` đang runnable trong các sample hay không?
- `SafepointLatency` có ghi nhận độ trễ tới poll không?
- Nếu thay workload bằng `Thread.sleep(...)`, profile thay đổi ra sao?

Khi thread chủ yếu ngủ hoặc chờ I/O, `ExecutionSample` có thể không cho thấy một method CPU-bound nổi bật. Đây là kết quả hợp lý: event này nhằm snapshot thread thực thi Java code.

## 19. Viết chương trình đọc event bằng Java API

Nếu cần xử lý recording tự động, package `jdk.jfr.consumer` cung cấp `RecordingFile`, `RecordedEvent` và các kiểu đọc stack trace.

Ví dụ tối giản đếm top frame của `jdk.ExecutionSample`:

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;

import jdk.jfr.consumer.RecordingFile;

public class ExecutionSampleCounter {

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java ExecutionSampleCounter recording.jfr");
        }

        var counts = RecordingFile.readAllEvents(Path.of(args[0])).stream()
            .filter(event ->
                event.getEventType().getName().equals("jdk.ExecutionSample"))
            .map(event -> event.getStackTrace())
            .filter(stack -> stack != null && !stack.getFrames().isEmpty())
            .map(stack -> stack.getFrames().getFirst())
            .filter(frame -> frame.isJavaFrame())
            .map(frame -> frame.getMethod().getType().getName()
                + "." + frame.getMethod().getName())
            .collect(Collectors.groupingBy(
                name -> name,
                Collectors.counting()));

        counts.entrySet().stream()
            .sorted(Map.Entry.<String, Long>comparingByValue().reversed())
            .limit(20)
            .forEach(entry ->
                System.out.printf("%8d %s%n", entry.getValue(), entry.getKey()));
    }
}
~~~

Chạy trên JDK 25:

~~~bash
javac --release 25 ExecutionSampleCounter.java
java ExecutionSampleCounter workload.jfr
~~~

Đây là bộ đếm top frame đơn giản. Nó không tạo flame graph, không phân tích toàn bộ call tree và không tính CPU time tuyệt đối. Để phân tích chuyên sâu, dùng JMC hoặc công cụ đọc JFR đã hiểu stack trace, inline frame, thread state và event metadata.

## 20. Quy trình profiling có thể lặp lại

Một kết luận hiệu năng đáng tin cần recording có thể so sánh.

~~~mermaid
flowchart TD
    A[Xác định giả thuyết hiệu năng] --> B[Chọn workload đại diện]
    B --> C[Chọn JDK 25 và cấu hình JFR]
    C --> D[Ghi baseline]
    D --> E[Đọc ExecutionSample và event liên quan]
    E --> F[Kiểm tra SafepointLatency khi cần]
    F --> G[Đề xuất thay đổi có thể kiểm chứng]
    G --> H[Chạy cùng workload sau thay đổi]
    H --> I[So sánh profile, throughput và latency]
    I --> J{Kết quả cải thiện?}
    J -- Có --> K[Ghi lại bằng chứng và giới hạn]
    J -- Không --> L[Quay lại giả thuyết]
~~~

### Checklist trước khi ghi

- [ ] JDK chạy ứng dụng và công cụ phân tích tương thích.
- [ ] Có workload đại diện và thời lượng đủ dài.
- [ ] Chọn `default` hay `profile` theo mục tiêu.
- [ ] Chỉ bật event bổ sung khi có câu hỏi cụ thể.
- [ ] Ghi nhận cấu hình, build, OS, CPU, GC và tải ứng dụng.
- [ ] Tránh ghi secret, token hoặc dữ liệu cá nhân không cần thiết vào custom JFR events.

### Checklist khi phân tích

- [ ] Xem `jfr summary` trước khi đọc toàn bộ event.
- [ ] Xác nhận số lượng `jdk.ExecutionSample`.
- [ ] Kiểm tra top methods và call tree.
- [ ] Phân biệt Java execution với native execution.
- [ ] Đọc `jdk.SafepointLatency` đúng nghĩa độ trễ tới poll.
- [ ] Không coi sample count là invocation count hoặc thời gian chính xác.
- [ ] So sánh ít nhất một lần chạy lặp lại trước khi kết luận.

## 21. Bài tập thực hành

### Bài tập A — giải thích safepoint bias

Mô tả một vòng lặp dài có nhiều công việc giữa hai poll point. Giải thích vì sao profiler chỉ lấy stack tại poll có thể làm profile thiên lệch.

**Đạt khi:** phân biệt được vị trí sample được yêu cầu và vị trí stack có thể duyệt an toàn.

### Bài tập B — ghi ExecutionSample

Chạy `SamplingWorkload` trong 45 giây với `settings=profile`. In `jdk.ExecutionSample` và tìm top frame xuất hiện thường xuyên.

**Đạt khi:** giải thích được tại sao sample là snapshot và không phải số lần gọi method.

### Bài tập C — bật SafepointLatency

Ghi lại workload với `jdk.SafepointLatency#enabled=true`. Đọc `duration`, `threadState` và stack trace.

**Đạt khi:** giải thích đúng độ trễ từ sampling interrupt tới poll kế tiếp, không gọi đó là GC pause.

### Bài tập D — so sánh workload CPU và workload chờ

Sửa chương trình để thay `hotMethod()` bằng `Thread.sleep(...)`. Ghi hai recording cùng thời lượng và so sánh `ExecutionSample`.

**Đạt khi:** giải thích được vì sao thread chờ không xuất hiện như một method CPU-bound trong event này.

### Bài tập E — native code

Đọc tài liệu về `NativeMethodSample` và JEP 509. Nêu khác biệt giữa `ExecutionSample`, `NativeMethodSample` và `CPUTimeSample`.

**Đạt khi:** biết JEP 509 là experimental trong JDK 25 và chỉ Linux, không dùng nó như mặc định portable.

### Bài tập F — lập kế hoạch profiling

Chọn một service thực tế, viết kế hoạch recording gồm workload, settings, duration, event cần bật, tiêu chí đọc và cách so sánh baseline.

**Đạt khi:** có thể lặp lại phép đo và chỉ ra giới hạn của kết luận.

## 22. Những quan niệm sai cần loại bỏ

1. **“Cooperative sampling chỉ lấy mẫu tại safepoint nên luôn bị bias.”** Không chính xác: stack walk diễn ra tại poll an toàn, nhưng frame được tái dựng theo vị trí đã ghi nhận ở thời điểm sampling request.
2. **“Sampler phải tự đọc toàn bộ stack tại instruction bất kỳ.”** Không đúng với cơ chế JEP 518; thread mục tiêu phối hợp hoàn tất stack trace tại poll.
3. **“Ứng dụng phải gọi poll API.”** Không cần; đây là cơ chế nội bộ của HotSpot/JFR.
4. **“SafepointLatency là GC pause.”** Không đúng; nó đo thời gian thread tới poll sau sampling interrupt.
5. **“ExecutionSample đo chính xác số lần gọi method.”** Không đúng; nó là dữ liệu thống kê.
6. **“Không thấy ExecutionSample nghĩa là thread không chạy.”** Thread có thể chờ, chạy native hoặc nằm ngoài phạm vi event.
7. **“JEP 509 và JEP 518 là một tính năng.”** Không đúng; JEP 518 cải thiện cooperative method sampling, còn JEP 509 là CPU-time profiling experimental trên Linux trong JDK 25.
8. **“JFR luôn không có overhead.”** Không đúng; overhead phụ thuộc cấu hình, event, chu kỳ, stack depth và thời gian recording.
9. **“Một flame graph đủ để kết luận.”** Không đúng; cần workload đại diện, baseline, call tree và các event hỗ trợ.

## 23. Tài liệu tham khảo chính thức

1. [JEP 518 — JFR Cooperative Sampling](https://openjdk.org/jeps/518): thiết kế cooperative sampling, stack walking tại safepoint và giảm safepoint bias.
2. [Oracle JDK 25 Release Notes — JFR Cooperative Sampling](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html): xác nhận JEP 518 thuộc JDK 25 và mục tiêu ổn định stack sampling.
3. [JEP 509 — JFR CPU-Time Profiling (Experimental)](https://openjdk.org/jeps/509): tính năng CPU-time profiling thử nghiệm, phân biệt với JEP 518.
4. [Oracle Java 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:StartFlightRecording`, settings và event-setting options.
5. [Oracle Java 25 — The jfr Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `jfr print`, `view`, `summary`, `metadata` và `configure`.
6. [Oracle Java 25 — JFR Consumer API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html): đọc event và stack trace từ recording.
7. [Inside Java — What's new for JFR in JDK 25](https://inside.java/2025/06/03/new-jfr-jdk25/): tóm tắt JEP 518, `SafepointLatency` và JEP 509.
8. [JDK Flight Recorder Event Reference for JDK 25](https://sap.github.io/jfrevents/25.html): event schema và các trường của `ExecutionSample`, `SafepointLatency`, `CPUTimeSample`.

**Kết quả mong đợi:** người học hiểu rằng JDK 25 JFR có thể ghi nhận vị trí thực thi theo yêu cầu sampling, nhưng chỉ duyệt stack tại điểm JVM bảo đảm an toàn. Cooperative sampling kết hợp hai thời điểm này để giảm safepoint bias và tăng độ ổn định của profiler. Khi đọc recording, cần hiểu đúng `ExecutionSample` và `SafepointLatency`, phân biệt Java với native execution, và luôn coi sample là bằng chứng thống kê cần được kiểm chứng bằng workload đại diện và các phép đo bổ sung.
