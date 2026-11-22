# Chế độ và tùy chọn Shenandoah còn được JDK đang dùng hỗ trợ (Java 15+)

## 1. Vấn đề thực tế cần giải quyết

**Shenandoah GC** là bộ thu gom rác đồng thời của HotSpot/OpenJDK, hướng tới thời gian tạm dừng ứng dụng (*GC pause*) thấp ngay cả khi heap lớn. Tính năng đã trở thành **production trong OpenJDK 15** theo [JEP 379](https://openjdk.org/jeps/379). Nhưng một bài viết hoặc câu lệnh cho “Shenandoah” có thể không chạy được trong **JDK binary đang triển khai**.

Ví dụ: một máy phát triển có Shenandoah, nhưng Docker image production lại dùng bản JDK không đóng gói collector này; hoặc tài liệu phiên bản mới giới thiệu **generational Shenandoah** trong khi service vẫn dùng JDK 21/24. Một số tùy chọn chỉ hợp lệ ở **single-generation mode**, không hợp lệ khi chuyển sang **generational mode**.

Vì thế phải trả lời ba câu hỏi riêng:

1. **Feature có trong tài liệu của JDK/HotSpot nào?** Phân biệt phiên bản phát hành và trạng thái production.
2. **Feature có trong chính runtime đang chạy?** Xem vendor, VM implementation, OS/CPU architecture, build và dùng thử flag để kiểm tra.
3. **Feature có đáp ứng SLO trên workload thực tế không?** Startup thành công chưa phải bằng chứng đạt latency, throughput và memory budget.

Bài này tập trung vào những **mode, heuristic và tùy chọn Shenandoah còn được JDK hiện đại hỗ trợ**. Các tùy chọn không còn phù hợp hoặc phụ thuộc bản build chỉ được nhắc đến để tránh dùng sai; không hướng dẫn dựa vào chế độ legacy/experimental làm cấu hình production.

## 2. Phân biệt collector, mode và heuristic

Ba khái niệm này **không thay thế nhau**:

| Lớp cấu hình | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Chọn **collector** | `-XX:+UseShenandoahGC` | Yêu cầu HotSpot dùng Shenandoah thay vì GC mặc định |
| Chọn **mode** | `-XX:ShenandoahGCMode=satb` hoặc `generational` | Xác định thuật toán/chiến lược tổ chức vùng và barriers |
| Chọn **heuristic** | `-XX:ShenandoahGCHeuristics=adaptive` | Điều chỉnh thời điểm và độ tích cực khởi chạy các chu kỳ GC trong mode đã chọn |

Sự khác biệt quan trọng: **`ShenandoahGCHeuristics=generational` là sai**, vì `generational` là **mode**, không phải heuristic. Tương tự, `adaptive` không phải một collector và không chuyển Shenandoah sang generational.

Cú pháp có chủ đích trên **HotSpot JDK 25+ có hỗ trợ**:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -XX:ShenandoahGCHeuristics=adaptive -jar app.jar
```

Nếu chưa xác minh khả dụng ở build đích, đó **chỉ là cấu hình ứng viên**, không phải lệnh mặc định nên copy sang mọi máy.

## 3. Các mode Shenandoah hiện hành theo tài liệu JDK 27

Tại thời điểm của bài, trang **Oracle JDK 27 — The java Command** liệt kê hai mode chính:

| Mode | Cờ | Cơ chế | Trạng thái / cách dùng |
| --- | --- | --- | --- |
| **SATB (single-generation)** | `-XX:ShenandoahGCMode=satb` | Snapshot-at-the-beginning; concurrent mark–evacuate–update, **một thế hệ** | Đang được hỗ trợ; **mode mặc định của Shenandoah trong tài liệu JDK 27** |
| **Generational Shenandoah** | `-XX:ShenandoahGCMode=generational` | Concurrent GC có **young/old generations**, nhằm tối ưu workload cấp phát nhiều | Chế độ **production từ JDK 25** (JEP 521), nếu bản phân phối/CPU/OS có feature |

**SATB không phải “legacy bị loại bỏ”**. Dù tên gắn với mô hình một thế hệ truyền thống, tài liệu JDK 27 vẫn công bố `satb` là mode được hỗ trợ và là mặc định tại phiên bản đó.

**Generational không tự động bật khi nâng lên JDK 25/26/27**: theo tài liệu JDK 27, default `ShenandoahGCMode` vẫn là `satb`. Muốn dùng generational cần chọn mode tường minh, đồng thời kiểm tra binary và nhà cung cấp.

### 3.1. Mốc phát hành cần nhớ

- **Java 15 / JEP 379:** Shenandoah đạt trạng thái production trong OpenJDK, nhưng không phải mọi JDK distribution/build đều đóng gói.
- **JDK 24:** có các công việc phát triển generational Shenandoah ở một số bản build, nhưng **không coi mode này là baseline production chung** ở JDK 24.
- **JDK 25 / JEP 521:** Generational Shenandoah được hoàn thiện và đưa vào **production**.
- **JDK 27:** trang man công bố `satb` và `generational`, với `satb` mặc định. Không suy diễn mode mặc định cho các JDK tương lai mà chưa kiểm tra tài liệu của phiên bản đó.

**Kết luận cho production:** Nếu đang chạy JDK 17 hoặc 21 và cần mode `generational`, đừng chỉ sao chép flag từ bài dành cho JDK 25+. Xác định dòng JDK nào được tổ chức hỗ trợ, nâng cấp và chạy thử trên artifact được phép trước.

## 4. Heuristic nào đang được hỗ trợ?

Ở JDK 27, `-XX:ShenandoahGCHeuristics=` có ba giá trị được công bố:

| Heuristic | Ý nghĩa | Dùng với mode nào? |
| --- | --- | --- |
| **`adaptive`** | Điều chỉnh khi nào chạy GC, cố gắng giữ đủ vùng heap rảnh để ứng dụng cấp phát | **SATB và generational**; là mặc định |
| **`static`** | Khởi chạy collection dựa trên ngưỡng heap rảnh được cấu hình | **SATB**, không dùng với generational theo hợp đồng JDK 27 |
| **`compact`** | Có xu hướng chạy GC thường xuyên hơn với mục tiêu giải phóng vùng heap sâu hơn | **SATB**, không dùng với generational theo hợp đồng JDK 27 |

**Ràng buộc quan trọng:** Khi `ShenandoahGCMode=generational`, tài liệu JDK 27 quy định **chỉ heuristic `adaptive` được hỗ trợ**. Vì thế ví dụ sau **không phải cấu hình production hợp lệ** theo hợp đồng đó:

```text
-XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -XX:ShenandoahGCHeuristics=static
```

Không cố dùng một tham số tùy ý để vượt qua kiểm tra; đổi về `adaptive` hoặc chọn SATB nếu kết quả benchmark và chính sách cho phép.

### 4.1. Chọn `adaptive` trước khi tinh chỉnh

Nếu chỉ cần bật collector:

```bash
java -XX:+UseShenandoahGC -Xlog:gc=info -jar app.jar
```

Khi binary đang triển khai công bố mặc định `satb` và heuristic `adaptive` như JDK 27, lệnh trên sẽ chọn Shenandoah với các mặc định đó. Nếu ứng dụng muốn cấu hình rõ:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=satb -XX:ShenandoahGCHeuristics=adaptive -Xlog:gc=info -jar app.jar
```

Đây là lựa chọn khởi đầu dễ giải thích. Không cần thay heuristic trước khi có bằng chứng rằng mặc định chưa đáp ứng p99 latency hoặc footprint.

### 4.2. `static` và `compact` có phải “mode” mới không?

**Không.** Hai tùy chọn này là heuristic lựa chọn *khi* chạy các chu kỳ collection cho SATB. Chúng không chuyển SATB thành generational, không thay đổi API ứng dụng và không đảm bảo đạt SLA.

- `static`: phù hợp để khảo sát chính sách kích hoạt dựa ngưỡng khi có workload rất đặc thù và phép đo so sánh.
- `compact`: có thể ưu tiên thu hồi bộ nhớ mạnh hơn nhưng tăng số chu kỳ GC hoặc chi phí CPU; cần benchmark.
- `adaptive`: mặc định đáng dùng làm baseline; nếu thay đổi phải ghi lại trong deployment manifest và so sánh số liệu.

**Không mặc định rằng “compact” luôn làm heap nhỏ hơn hoặc ứng dụng nhanh hơn**. Chất lượng của từng heuristic tùy allocation pattern, memory pressure, CPU quota và mức độ song song.

## 5. Các nhóm tùy chọn Shenandoah nên xem xét

| Tùy chọn / lệnh | Vai trò | Lưu ý |
| --- | --- | --- |
| `-XX:+UseShenandoahGC` | Bật collector | Phải có collector trong binary và platform |
| `-XX:ShenandoahGCMode=satb` | Chọn SATB single-generation | Được tài liệu JDK 27 hỗ trợ |
| `-XX:ShenandoahGCMode=generational` | Chọn generational | Tính năng production từ JDK 25; kiểm tra runtime |
| `-XX:ShenandoahGCHeuristics=adaptive` | Heuristic mặc định | Là lựa chọn hỗ trợ cho generational |
| `-XX:ShenandoahGCHeuristics=static` / `compact` | Tinh chỉnh hành vi SATB | **Không** phối hợp với generational theo JDK 27 |
| `-Xms` / `-Xmx` | Heap size ban đầu / tối đa | Chọn theo memory budget, allocation rate, headroom |
| `-Xlog:gc=info` | Log GC cơ bản để xác nhận collector | Đọc `Using Shenandoah`, sau đó phân tích log |
| `-Xlog:gc+init=info` | Log thông tin khởi tạo GC (khi runtime cung cấp) | Hữu ích để xem mode/heap/CPU trong GC init |
| `-XX:+PrintFlagsFinal` | In giá trị VM flags mà HotSpot xử lý | Kiểm tra mode/heuristic thực tế; không thay thế startup test |
| `-XX:ConcGCThreads` / `-XX:ParallelGCThreads` | Giới hạn worker GC concurrent / stop-the-world | Tuning nâng cao; không chỉnh nếu chưa đo CPU/latency |
| `jcmd <PID> VM.flags` | Xem flags của JVM đang chạy | Cần quyền attach; không phải phần bắt buộc trong mọi container |

`-XX` là **HotSpot-specific**, không phải bảo đảm về Java SE API. Tên options có thể thay đổi theo version/vendor, vì vậy dùng bảng làm **danh sách cần kiểm tra** chứ không làm cam kết rằng mọi VM đều nhận tất cả.

### 5.1. Heap và uncommit

Shenandoah cần **memory headroom** để tiếp tục concurrent collection khi ứng dụng cấp phát. `-Xmx` quá nhỏ so với allocation rate/working set có thể dẫn tới GC pressure, allocation stalls hoặc chu kỳ thu gom không theo kịp ứng dụng.

`-Xms` là heap ban đầu; `-Xmx` là giới hạn heap. Một số cơ chế hoàn trả bộ nhớ đã commit (*uncommit*) chỉ có tác dụng khi JVM có khả năng giảm phần committed heap: nếu đặt `-Xms` bằng `-Xmx`, không nên kỳ vọng heap được thu nhỏ xuống dưới mức tối thiểu.

Không sao chép hằng số `-Xms`, `-Xmx` từ internet làm cấu hình chuẩn. **Heap không phải toàn bộ RSS**; còn native memory, direct buffers, metaspace, thread stacks và overhead GC.

### 5.2. Thread counts và CPU quota

Các tùy chọn `-XX:ConcGCThreads` và `-XX:ParallelGCThreads` có thể ảnh hưởng tài nguyên CPU dùng cho GC. Những điều chỉnh này rất nhạy với CPU quota và mức tải của service. Thông thường hãy bắt đầu từ mặc định đã được JVM tính toán (*ergonomics*), sau đó đo:

- p99/p99.9 request latency và GC pause;
- application/GC CPU usage;
- allocation rate và allocation stalls;
- throughput, RSS và tổng số GC cycles.

Không tăng concurrent threads vô hạn với kỳ vọng pause tự giảm; GC chạy đồng thời cũng cạnh tranh CPU với ứng dụng.

## 6. Quy trình xác nhận trên đúng JDK đang dùng

### Bước 1 — xác định vendor, JVM, build, OS và image

Chạy trên đúng runtime của service:

```bash
java -version
java -XshowSettings:properties -version
```

Thu thập `java.version`, `java.runtime.version`, `java.vendor`, `java.vm.name`, `java.vm.version`, `os.name`, `os.arch`, đường dẫn `java` thật và image digest nếu chạy container.

**Máy dev không chứng minh được production:** cùng phiên bản Java vẫn có thể dùng JDK distribution khác. Trên một VM không phải HotSpot (ví dụ OpenJ9), không áp dụng mặc định các cờ Shenandoah của HotSpot.

### Bước 2 — chạy startup smoke test

Trên **HotSpot** dự kiến hỗ trợ Shenandoah:

```bash
java -XX:+UseShenandoahGC -Xms128m -Xmx256m -Xlog:gc=info -version
```

Kiểm tra:

1. **Exit code = 0**.
2. GC startup log có dòng `Using Shenandoah`.
3. Không có lỗi `Unrecognized VM option`, `Option -XX:+UseShenandoahGC not supported` hoặc lỗi tạo JVM.

Nếu không khởi động được, đánh dấu **UNAVAILABLE** trên binary đó. **Đừng bỏ flag rồi vẫn báo collector Shenandoah đã hoạt động**.

`-Xms128m -Xmx256m` chỉ là heap cho smoke test. Với một workload production, kích thước cần đo và lựa chọn riêng.

### Bước 3 — xác nhận mode và heuristic SATB

Khi đã biết Shenandoah có sẵn và muốn chạy SATB:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=satb -XX:ShenandoahGCHeuristics=adaptive -Xms128m -Xmx256m -Xlog:gc=info -version
```

Để xem chi tiết flag HotSpot đã xử lý:

```bash
java -XX:+UseShenandoahGC -XX:+PrintFlagsFinal -version
```

Trong output dài, tìm `UseShenandoahGC`, `ShenandoahGCMode`, `ShenandoahGCHeuristics`. Ví dụ nếu thấy `UseShenandoahGC = true`, `ShenandoahGCMode = satb`, `ShenandoahGCHeuristics = adaptive`, đó là bằng chứng hữu ích rằng **JVM xác định cấu hình như mong đợi**.

Cần kết hợp **exit code và GC log**, vì bản thân việc một tên flag xuất hiện trong danh sách VM flags không chứng minh collector được chọn hay không gặp lỗi startup.

### Bước 4 — xác nhận generational chỉ ở build phù hợp

Trên một **JDK 25+ có generational Shenandoah production**, thử:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -XX:ShenandoahGCHeuristics=adaptive -Xms128m -Xmx256m -Xlog:gc=info -version
```

Kết quả chỉ có giá trị cho **JDK binary đã kiểm chứng**. Với runtime cũ hoặc vendor không đóng gói mode, có thể nhận thông báo không hỗ trợ. **Không tự động thêm `-XX:+UnlockExperimentalVMOptions` để ép một cấu hình chưa đạt trạng thái production**, nhất là khi bài tập yêu cầu chỉ dùng kiến thức còn phù hợp hiện tại.

**Bản thử nghiệm bên dưới dùng Zulu JDK 24 và chỉ xác minh SATB**, không nhận là đã kiểm chứng generational Shenandoah trên JDK 25+.

### Bước 5 — kiểm tra service sau khi start

Có thể xem GC logs của service hoặc sử dụng `jcmd` khi có quyền:

```text
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
```

Đây là cú pháp minh họa; thay `<PID>` bằng process ID thực tế. Trong container, namespace và security policy có thể không cho attach; khi đó cần dùng startup log, metrics và JFR theo cách hạ tầng cho phép.

**Không dùng GC MXBean name như điều kiện duy nhất để xác định mode.** Nhiều mode có thể có tên bean tương tự nhau; cần kết hợp VM flags, init logs và documentation.

## 7. Ví dụ Java 17+ chạy được: quan sát collector và runtime flags

Chương trình không yêu cầu thư viện ngoài, không giả định trước tên vendor hay tên GC bean. Nó in **phiên bản Java, JDK vendor, VM implementation, các GC MXBeans và JVM arguments** đang hoạt động.

Tạo file **`ShenandoahSupportProbe.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.util.stream.Collectors;

public class ShenandoahSupportProbe {
    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        System.out.println("javaFeature=" + Runtime.version().feature());
        System.out.println("javaVendor=" + System.getProperty("java.vendor"));
        System.out.println("vmName=" + System.getProperty("java.vm.name"));
        System.out.println("gcBeans=" + ManagementFactory.getGarbageCollectorMXBeans()
                .stream()
                .map(GarbageCollectorMXBean::getName)
                .sorted()
                .collect(Collectors.joining(", ")));
        System.out.println("jvmArgs=" + runtime.getInputArguments());
    }
}
```

Biên dịch trên JDK 17 trở lên:

```bash
javac --release 17 ShenandoahSupportProbe.java
```

Chạy từng cấu hình trong **một process mới**:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=satb -XX:ShenandoahGCHeuristics=adaptive -Xms128m -Xmx256m -Xlog:gc=info -cp . ShenandoahSupportProbe
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=satb -XX:ShenandoahGCHeuristics=static -Xms128m -Xmx256m -Xlog:gc=info -cp . ShenandoahSupportProbe
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=satb -XX:ShenandoahGCHeuristics=compact -Xms128m -Xmx256m -Xlog:gc=info -cp . ShenandoahSupportProbe
```

**Các lệnh trên dành cho SATB** và chỉ chạy nếu build có Shenandoah. Muốn thử generational, dùng lệnh riêng ở bước 4 sau khi xác nhận JDK 25+ và support của vendor. Java bytecode của chương trình không cần được viết lại khi đổi collector; **GC được chọn qua JVM startup flags**.

### 7.1. Stdout thực tế đã kiểm chứng trên Azul Zulu JDK 24

Chương trình đã biên dịch thành công bằng `javac --release 17` và chạy trên **Azul Zulu OpenJDK 24.0.2+12**. Đây là **kết quả quan sát của một build cụ thể**, không phải output bắt buộc của mọi JVM.

**SATB + adaptive**, phần stdout của chương trình (không tính dòng GC log có timestamp):

```text
javaFeature=24
javaVendor=Azul Systems, Inc.
vmName=OpenJDK 64-Bit Server VM
gcBeans=Shenandoah Cycles, Shenandoah Pauses
jvmArgs=[-XX:+UseShenandoahGC, -XX:ShenandoahGCMode=satb, -XX:ShenandoahGCHeuristics=adaptive, -Xms128m, -Xmx256m, -Xlog:gc=info]
```

**SATB + static**:

```text
javaFeature=24
javaVendor=Azul Systems, Inc.
vmName=OpenJDK 64-Bit Server VM
gcBeans=Shenandoah Cycles, Shenandoah Pauses
jvmArgs=[-XX:+UseShenandoahGC, -XX:ShenandoahGCMode=satb, -XX:ShenandoahGCHeuristics=static, -Xms128m, -Xmx256m, -Xlog:gc=info]
```

**SATB + compact**:

```text
javaFeature=24
javaVendor=Azul Systems, Inc.
vmName=OpenJDK 64-Bit Server VM
gcBeans=Shenandoah Cycles, Shenandoah Pauses
jvmArgs=[-XX:+UseShenandoahGC, -XX:ShenandoahGCMode=satb, -XX:ShenandoahGCHeuristics=compact, -Xms128m, -Xmx256m, -Xlog:gc=info]
```

Trong cả ba trường hợp, startup GC log xuất hiện **`Using Shenandoah`** và process hoàn tất với **exit code 0** trên binary đã thử.

**Khi không truyền `-XX:+UseShenandoahGC`**, cùng bản JDK thử nghiệm chọn G1 và GC beans là `G1 Concurrent GC, G1 Old Generation, G1 Young Generation`. Điều này nhắc rằng **JDK có Shenandoah không có nghĩa Shenandoah đang được bật mặc định**.

Các output này không chứng minh **JDK 24 có generational Shenandoah production**; chương trình chỉ kiểm tra SATB. Chạy được `static`/`compact` trên SATB cũng không có nghĩa chúng dùng được với generational mode.

## 8. Đối chiếu cấu hình nào là hợp lệ

| Điều kiện runtime | Cấu hình ứng viên | Cách kết luận |
| --- | --- | --- |
| HotSpot có Shenandoah, muốn mặc định | `-XX:+UseShenandoahGC` | PASS nếu JVM start và GC log xác nhận |
| HotSpot có Shenandoah SATB | `ShenandoahGCMode=satb` + heuristic `adaptive` | Được tài liệu JDK 27 hỗ trợ; vẫn thử trên binary |
| SATB cần thử heuristic khác | `ShenandoahGCHeuristics=static` hoặc `compact` | Chỉ dùng sau khi thử trên runtime và benchmark |
| JDK 25+ build có generational | `ShenandoahGCMode=generational` + `adaptive` | PASS khi startup thành công, mode/log phù hợp và vendor hỗ trợ |
| Generational + `static`/`compact` | Không phải kết hợp được JDK 27 công bố hỗ trợ | Không triển khai; dùng `adaptive` |
| Runtime không đóng gói Shenandoah | Bất kỳ `UseShenandoahGC` nào | UNAVAILABLE; chọn JDK build hoặc collector khác theo policy |
| VM implementation không phải HotSpot | HotSpot `-XX` Shenandoah flags | Không giả định portable; tra docs của VM tương ứng |
| Flag được nhận nhưng p99/SLO kém | Bất kỳ mode/heuristic nào | Không chấp nhận chỉ vì startup PASS; benchmark lại |

**Mỗi trường hợp phải gắn với JDK version + vendor + build + OS/architecture + container image digest.** Nếu đổi image hoặc chuyển CPU architecture, phải chạy lại phép thử khả dụng chứ không giữ nguyên kết luận cũ.

### 8.1. Khi flag không được nhận

Nếu lệnh trả lỗi `Unrecognized VM option`, `Option ... not supported` hoặc `Could not create the Java Virtual Machine`:

1. Kiểm tra `java -version`, `java.vm.name` và runtime path.
2. Đối chiếu flag với **JDK man page của đúng phiên bản**.
3. Xác minh mode/heuristic được kết hợp đúng.
4. Xác minh binary có Shenandoah và platform hỗ trợ.
5. Ghi lại exit code, stderr/GC init logs và trạng thái **UNAVAILABLE**.
6. Không cho deployment âm thầm bỏ flag rồi vẫn báo đang dùng Shenandoah.

Đừng thử hàng loạt flag chưa có tài liệu chỉ để vượt kiểm tra. Nếu ứng dụng phải chạy trên bản JDK không có Shenandoah, chọn collector khác được hỗ trợ và benchmark rõ ràng, không tuyên bố đó là cùng cấu hình.

## 9. Benchmark và vận hành: mode được nhận chưa chắc phù hợp workload

Shenandoah có mục tiêu giảm **stop-the-world GC pauses**, nhưng collector đồng thời vẫn tiêu tốn CPU và bộ nhớ. Một phép thử `java -version` có thể chứng minh feature khả dụng, **không thể chứng minh** tải production sẽ có tail latency tốt.

Khi so SATB, generational Shenandoah và baseline G1, kiểm tra:

| Nhóm metric | Mục tiêu quan sát |
| --- | --- |
| **p99/p99.9 request latency** | End-to-end SLO của dịch vụ có đạt không |
| **GC pause distribution** | Max/p99 GC pauses, thời gian safepoint |
| **CPU** | Background GC workers cạnh tranh với application threads ra sao |
| **Allocation rate / allocation stalls** | GC có theo kịp nhịp cấp phát không |
| **Throughput / error rate** | Có giảm số request/giây hoặc gây lỗi không |
| **Heap used/committed, RSS** | Bộ nhớ thực tế có vừa container memory limit không |
| **Concurrent, degenerated, full cycles** | Có GC pressure hoặc phải chuyển sang chu kỳ kém thuận lợi không |
| **Startup/warmup và peak load** | Collector có ổn định khi rollout hoặc tăng tải đột ngột không |

Dùng **GC unified logging** và khi phù hợp **Java Flight Recorder (JFR)**:

```bash
java -XX:+UseShenandoahGC -Xlog:gc*,safepoint=info -jar app.jar
```

```bash
java -XX:+UseShenandoahGC -XX:StartFlightRecording=duration=120s,filename=shenandoah-review.jfr,settings=profile -jar app.jar
```

Log `gc*` có thể khá dài; trong production cần cấu hình level, retention, rotation và quyền truy cập. JFR có overhead và có thể chứa dữ liệu nhạy cảm tùy events; chỉ ghi theo chính sách. Không gọi `System.gc()` liên tục để suy ra chất lượng GC trong tải tự nhiên của ứng dụng.

### 9.1. Những yếu tố phải giữ cố định khi so sánh

- Cùng ứng dụng và dependencies.
- Cùng loại request, payload, concurrency và allocation profile.
- Cùng CPU quota, memory limit, workload duration và warmup.
- Cùng JDK build/vendor nếu mục tiêu là **so heuristic hoặc mode**.
- Đo nhiều lần để tránh đánh giá dựa trên một kết quả may rủi.
- Có **baseline G1**, rồi mới kết luận Shenandoah mang lại lợi ích.

Nếu đang so các JDK distributions khác nhau, lưu toàn bộ khác biệt VM/patch/JIT, không quy hết chênh lệch hiệu năng về GC.

## 10. Ví dụ áp dụng trong container và CI/CD

Một quy trình CI hợp lý trước khi chuyển service sang Shenandoah:

```text
1. Xác nhận java -version trong đúng image.
2. Xác nhận HotSpot và Shenandoah có trong binary.
3. Khởi động JVM với chính xác GC mode và heuristic dự định deploy.
4. Lưu exit code, flags, GC init log, runtime/vendor/build.
5. Chạy smoke tests của ứng dụng; nếu thất bại thì không deploy.
6. Chạy load/stress test theo SLO (p99/p99.9, CPU, RSS, throughput).
7. Canary rollout và theo dõi metrics, có rollback.
```

Với build **JDK 25+ có generational Shenandoah**, manifest có thể cấu hình:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xms512m -Xmx1024m -Xlog:gc=info -jar app.jar
```

`512m` và `1024m` **chỉ là con số minh họa**, không phải cấu hình đề nghị cho mọi ứng dụng. Heap phải để lại native-memory headroom, nhất là trong container có memory limit.

Nếu runtime không hỗ trợ `generational`, deployment phải báo **không tương thích** để cập nhật binary hoặc chọn lại mode theo review. Không thêm cờ experimental để biến thiếu tính năng production thành điều kiện thành công giả.

## 11. Các lỗi hiểu sai thường gặp

1. **“Java 15 có Shenandoah production nghĩa là mọi JDK 15+ đều có.”** Sai: còn phụ thuộc vendor/build/platform.
2. **“Cùng Java version là cùng HotSpot flags.”** Sai nếu dùng JVM implementation khác.
3. **“`satb` là mode legacy đã bị loại bỏ.”** Sai: JDK 27 vẫn hỗ trợ và dùng mặc định.
4. **“Generational Shenandoah luôn tự bật từ JDK 25.”** Sai: JDK 27 vẫn mặc định `satb`.
5. **“`ShenandoahGCHeuristics=generational` là cú pháp đúng.”** Sai: `generational` thuộc `ShenandoahGCMode`.
6. **“Generational + `static` hoặc `compact` được hỗ trợ như SATB.”** Sai theo tài liệu JDK 27: chỉ `adaptive`.
7. **“`static`/`compact` chắc chắn giảm latency.”** Sai: cần benchmark.
8. **“JDK có tên flag thì chắc chắn build chứa GC đó.”** Sai: chỉ startup test mới xác nhận binary thực tế.
9. **“GC startup PASS nghĩa đã đạt latency SLO.”** Sai: phải đo workload thật.
10. **“Tên `gcBeans` luôn giống nhau trên mọi JDK.”** Sai: tùy VM/build, thường có nhiều bean.
11. **“`-Xmx` bằng RAM container thì an toàn.”** Sai: còn native memory và GC overhead.
12. **“`ShenandoahGCMode` có thể đổi động trong một JVM đang chạy.”** Sai: chọn collector/mode khi JVM khởi động.
13. **“Cứ thêm `UnlockExperimentalVMOptions` để bật tính năng bị thiếu.”** Sai: không phải cách kiểm tra support production.
14. **“Một lần đo GC pause nhỏ là đủ.”** Sai: phải xem p99, CPU, RSS, throughput và workload peak.
15. **“Nếu option lỗi, cứ bỏ flag rồi ghi nhận vẫn dùng Shenandoah.”** Sai: đó là cấu hình sai lệch, cần báo lỗi triển khai.

## 12. Checklist đối chiếu Shenandoah hiện hành

- [ ] Xác định **vendor, build/update, JVM implementation, OS/architecture, image digest** của runtime đang triển khai.
- [ ] Đối chiếu release notes và Java launcher/GC docs **đúng JDK major version**.
- [ ] Chạy thử `-XX:+UseShenandoahGC`, kiểm tra exit code và `Using Shenandoah` trong log.
- [ ] Xác nhận mode `satb` hoặc `generational` theo chính binary, không đoán theo version.
- [ ] Nếu chọn generational, có JDK 25+ và bản phân phối hỗ trợ production mode đó?
- [ ] Với generational, heuristic vẫn là `adaptive`?
- [ ] Nếu dùng `static`/`compact`, mode có phải SATB và đã benchmark chưa?
- [ ] Ghi lại `UseShenandoahGC`, `ShenandoahGCMode`, `ShenandoahGCHeuristics` từ flags/log.
- [ ] Dùng `-Xms`/`-Xmx` theo workload và container memory headroom?
- [ ] Đã đo p99/p99.9, pauses, CPU, RSS, allocation stalls và throughput?
- [ ] Có xác nhận GC runtime bằng startup log, MXBeans/`jcmd` khi được phép?
- [ ] Có CI smoke test, canary, rollback và regression test sau mỗi lần đổi JDK image?

**Tóm tắt:** `-XX:+UseShenandoahGC` chọn collector; `-XX:ShenandoahGCMode=satb|generational` chọn mode; `-XX:ShenandoahGCHeuristics=adaptive|static|compact` điều chỉnh heuristic theo mode. Với JDK 27, **SATB là mặc định**, **generational là chế độ production trên JDK 25+ có support và chỉ dùng heuristic adaptive**. Khi triển khai, phải xác nhận trên **binary thật** rồi đo SLO; không sao chép máy móc flags của một JDK khác.

## 13. Tài liệu chính thức, còn hiệu lực

- [Oracle Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `-XX:+UseShenandoahGC`, `ShenandoahGCMode` (SATB/generational), `ShenandoahGCHeuristics` (adaptive/static/compact), ràng buộc generational chỉ dùng adaptive.
- [Oracle Java SE 27 — HotSpot Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/27/gctuning/): cách lựa chọn GC và đo hiệu năng.
- [OpenJDK JEP 379 — Shenandoah Production](https://openjdk.org/jeps/379): đưa Shenandoah lên production ở Java 15.
- [OpenJDK JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): mode generational production trong JDK 25.
- [Java SE 27 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): quan sát tên collector và các MXBeans.
- [Java SE 27 — ManagementFactory](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/ManagementFactory.html): `getRuntimeMXBean()`, `getGarbageCollectorMXBeans()`.
- [Java SE 27 — RuntimeMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/RuntimeMXBean.html): quan sát VM input arguments.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): mốc phiên bản, thay đổi và cảnh báo hiện hành; kiểm tra thêm release notes vendor cho binary đang chạy.

Bài học sử dụng các tính năng và kiểm tra thực tế còn được hỗ trợ trong Java hiện đại, tránh cấu hình Shenandoah thử nghiệm của JDK cũ và các tùy chọn không được công bố cho mode hiện hành.