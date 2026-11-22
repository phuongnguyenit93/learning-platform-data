# Biên dịch phân tầng trong HotSpot và vai trò của C1, C2

**Tiered compilation (biên dịch phân tầng)** là chiến lược của **HotSpot JVM** kết hợp **interpreter** và các cấp độ **JIT compilation** để cân bằng hai mục tiêu có phần mâu thuẫn:

- **Khởi động và warm-up nhanh:** không tốn quá nhiều CPU để tối ưu sâu mọi method ngay từ đầu.
- **Hiệu năng ổn định dài hạn:** khi JVM đã quan sát đủ cách chương trình chạy, có thể tạo mã máy tối ưu hơn dựa trên thông tin thực tế.

Trong mô hình HotSpot phổ biến của **JDK 17**, hai bộ biên dịch đóng vai trò chủ đạo:

- **C1** (*client compiler*): biên dịch tương đối nhanh, có các chế độ tạo mã với **không profiling**, **profiling giới hạn** hoặc **profiling đầy đủ**. C1 giúp method nóng chuyển từ interpreter sang native code mà chưa phải trả hết chi phí tối ưu của C2.
- **C2** (*server compiler*): bộ tối ưu hóa mạnh hơn, dùng những thông tin runtime đã thu thập để tối ưu method, inlining, loops, speculative type optimizations và nhiều phép chuyển đổi khác; thường tạo **level 4** code.

**Quan trọng:** mô tả C1/C2 và năm mức biên dịch là kiến trúc **HotSpot**, không phải một phần bắt buộc của Java Language Specification hoặc JVM Specification. Một JVM khác, một bản HotSpot đặc thù hay một backend JIT khác có thể khác. Học cấp độ để hiểu runtime, nhưng **không viết ứng dụng dựa vào việc một method chắc chắn được JIT ở level nào**.

## 1. Từ Java source tới interpreter và mã máy JIT

```text
           javac (trước lúc chạy)
   MyApp.java ─────────────────────► MyApp.class
                                     JVM bytecode
                                          │
                                  class loading/linking
                                          │
                                          ▼
                          HotSpot interpreter (level 0)
                          đọc/thực thi bytecode
                          và thu thập thông tin
                                          │
                                method đủ "hot"?
                                          │
                          ┌───────────────┴───────────────┐
                          ▼                               ▼
                   C1 compiler                       C2 compiler
                  levels 1,2,3                         level 4
                  biên dịch nhanh                   tối ưu chuyên sâu
                          │                               │
                          └──────────┬────────────────────┘
                                     ▼
                            native machine code
                           trong HotSpot code cache
                                     │
                                     ▼
                               CPU thực thi
```

Sơ đồ chỉ thể hiện **các thành phần**, không áp đặt một con đường duy nhất “interpreter → C1 → C2” cho mọi method. Một method có thể:

- Chạy ở interpreter suốt đời tiến trình nếu ít sử dụng.
- Được C1 compile rồi không bao giờ chuyển lên C2.
- Có nhiều phiên bản code ở các mức và/hoặc cho OSR.
- Được C2 compile trực tiếp trong một số tình huống.
- Bị deoptimize, quay về interpreter hoặc code ở cấp thấp hơn rồi được biên dịch lại.

### Ba loại mã khác nhau

| Thành phần | Lưu ở đâu / vai trò | Dễ nhầm |
| --- | --- | --- |
| **Source Java** | Tệp `.java`, đầu vào `javac` | Không phải thứ CPU thực thi trực tiếp |
| **JVM bytecode** | `.class` / runtime metadata của class | `javap -c` xem bytecode, **không** xem JIT machine code |
| **Machine code JIT** | Native executable code do VM tạo, trong code cache | Có thể bị thay thế, vô hiệu hóa, tối ưu lại |

Lệnh `javac` chạy **trước** JVM execution khi build ứng dụng. **C1 và C2 không phải hai lựa chọn backend thay `javac` trong quá trình biên dịch source**; chúng hoạt động khi code đã chạy dưới JVM.

## 2. Vì sao không dùng C2 cho mọi method ngay lập tức?

Tối ưu sâu là công việc tốn CPU và thường cần **profile của chương trình thực tế**:

- Method được gọi bao nhiêu lần?
- Vòng lặp chạy bao nhiêu backedges/iterations?
- Những runtime types nào thường xuất hiện tại call site?
- Các nhánh `if` nào thường được chọn?
- Giá trị hoặc trạng thái nào cho phép giảm checks?
- Một lời gọi có nên được inline không?
- Có thể biến đổi loop, loại bỏ bounds checks hay hoist code không?

**Nếu tối ưu quá sớm:** JVM mất nhiều thời gian/CPU compiler cho code chưa chắc được dùng; startup và throughput giai đoạn đầu có thể xấu. **Nếu không bao giờ tối ưu:** method nóng chạy chậm dài hạn dù JVM đã có nhiều cơ hội làm tốt hơn.

Tiered compilation dùng **C1 như cầu nối nhanh**, đồng thời thu thập profile đủ để **C2 có đầu vào hữu ích**. Thực tế policy còn cân nhắc **compile queues**, compiler thread availability, call/backedge rates, method size, code cache, class loading và nhiều giới hạn khác.

### Hot code không chỉ là lời gọi method nhiều lần

Method có thể chỉ được gọi **một lần** nhưng chứa vòng lặp khổng lồ. Backedge counters giúp runtime phát hiện nóng ngay trong một lần thực thi và có thể dùng **on-stack replacement (OSR)** để chuyển sang compiled loop. Ngược lại, method được gọi lặp lại nhưng rất ngắn/trivial có thể được inline vào caller, khiến code cuối cùng không còn lời gọi method độc lập như source.

## 3. Năm execution levels trong HotSpot tiered policy

Trong HotSpot JDK 17 theo sơ đồ tiered thường dùng, có **năm cấp độ** được đánh số 0–4:

| Level | Engine/compiler | Profiling | Mục tiêu chính |
| ---: | --- | --- | --- |
| **0** | **Interpreter** | Có thể ghi nhận invocation/backedge counters và method data | Thực thi sớm, quan sát runtime |
| **1** | **C1 simple** | **Không tạo full profiling instrumentation** | Compiled code C1 tương đối nhẹ; hợp đường code không cần profile thêm |
| **2** | **C1 limited profile** | Chủ yếu invocation/backedge counting; ít hơn level 3 | Chạy code nhanh hơn level 3 khi C2 queue chịu tải, vẫn nhận biết độ nóng |
| **3** | **C1 full profile** | Thu thập profile phong phú, có method data liên quan | Chuẩn bị thông tin để quyết định và tối ưu level 4 |
| **4** | **C2 full optimization** | Tận dụng profile đã có, thường không mang instrumentation như C1 level 3 | Mã tối ưu cho hot path |

**Không hiểu sai tên “full optimization”:** level 1 có thể dùng các tối ưu của **C1** nhưng **không tương đương khả năng tối ưu của C2 level 4**. Level 3 không nhất thiết chạy nhanh hơn level 2, vì profiling instrumentation cũng có chi phí. Level 4 không có nghĩa VM từ nay chắc chắn dùng mã này mãi mãi.

### 3.1. Level 0 — interpreter

- Giúp chương trình **chạy ngay** mà chưa cần compile từng method.
- Có thể ghi nhận invocation counters, backedge events, method profile theo chính sách runtime.
- Chưa đặt một JIT-compiled nmethod tương ứng cho mọi method.
- Có overhead diễn giải bytecode, nhưng cold code có thể không đáng để compile.

### 3.2. Level 1 — C1 không profiling

- Tạo code C1 có tối ưu phù hợp nhưng **không gắn bộ thu thập profile đầy đủ**.
- Có thể chọn cho những methods mà policy thấy không cần tiếp tục lên C2, hoặc khi C2 không phù hợp.
- **Không phải một checkpoint bắt buộc** trước level 2 hay 3; đường chuyển có thể là 0 → 3 trực tiếp.

### 3.3. Level 2 — C1 limited profiling

- Chủ yếu duy trì thông tin invocation/backedge để policy ra quyết định.
- Có thể được chọn khi queue C2 dài khiến phương án level 3 full profiling không hấp dẫn trong giai đoạn chờ.
- Không tự tạo đủ loại profile call site như level 3 trong cùng mô hình.
- Level 2 cũng không phải tầng bắt buộc mọi method phải vượt qua.

### 3.4. Level 3 — C1 full profiling

- Thực thi compiled code của C1 đồng thời thu thập nhiều runtime profile hơn.
- **MethodData / MethodDataOop lịch sử, MethodData trong HotSpot hiện đại** có thể lưu những thống kê dùng cho adaptive optimization.
- Có thể cung cấp branch/type profiles hữu ích cho C2.
- Tốn thêm chi phí instrumentation/metadata, nên không nên khẳng định level 3 luôn là compiled code nhanh nhất trong giai đoạn chờ.

### 3.5. Level 4 — C2 tối ưu chuyên sâu

- Tận dụng profile như các call site types thường gặp, branch probabilities và hot loops.
- Có thể tạo speculative optimizations kèm guard/deoptimization fallback.
- Chi phí compilation cao hơn nhưng hướng tới **steady-state performance** tốt khi code thực sự nóng.
- Không bảo đảm luôn thắng C1 trong mọi microbenchmark; hiệu quả phụ thuộc method shape, target CPU, workload, profiling và compile budget.

## 4. Các đường chuyển level không phải tuyến tính

Mô hình chuyển phổ biến:

```text
                          ┌───────────────────┐
                          │ Level 0           │
                          │ Interpreter       │
                          └──────┬────────────┘
                                 │ method nóng
                  ┌──────────────┼─────────────────────┐
                  ▼              ▼                     ▼
        ┌────────────────┐ ┌────────────────┐  ┌────────────────┐
        │ C1 level 3     │ │ C1 level 2     │  │ C1 level 1     │
        │ full profiling │ │ limited profile│  │ no profiling   │
        └────────┬───────┘ └────────┬───────┘  └────────────────┘
                 │                  │
                 ▼                  ▼
          ┌────────────────────────────┐
          │ C2 level 4                 │
          │ full optimization          │
          └────────────────────────────┘

Deoptimization có thể chuyển đường thực thi về interpreter/
mã compiled khác, để sau đó recompile nếu chính sách phù hợp.
```

Những ví dụ đường đi trong tiered policy:

- **0 → 3 → 4:** đường thường được dùng khi profiler cần tích lũy dữ liệu ở level 3 rồi C2 compile.
- **0 → 2 → 3 → 4:** có thể dùng khi C2 queue cao và VM muốn giảm phí full profiling trong lúc chờ.
- **0 → 3 → 1**, hoặc **0 → 2 → 1:** một số methods có thể nhận code C1 ít instrumentation do compiler/policy đánh giá không cần C2.
- **0 → 4:** có thể xảy ra trong trường hợp thích hợp, ví dụ C1 compilation không thành công hoặc code/profile sẵn.
- **3 → 4 → deopt → 0/3/...:** optimized assumptions có thể mất hiệu lực, JVM khôi phục trạng thái execution đúng và biên dịch lại.

Đường đi chịu ảnh hưởng version và policy. **Các chuyển mũi tên trên là ví dụ của HotSpot**, không phải máy trạng thái bất biến cho mọi application run. Không đặt assertion rằng một method đi qua đủ 5 cấp theo thứ tự.

## 5. Profiling: dữ liệu nào dẫn tới quyết định JIT?

### 5.1. Invocation counters và backedge counters

- **Invocation counter:** tín hiệu một method được gọi nhiều lần.
- **Backedge counter:** tín hiệu nhánh quay về trong loop chạy nhiều lần.
- **Rate / event frequency:** policy có thể quan tâm số lần sự kiện trên một đơn vị thời gian, không chỉ tổng counters.
- **Method Data Object (MDO):** metadata chứa profiling information cho các bytecode sites phù hợp.

```java
static long sum(int n) {
    long result = 0;
    for (int i = 0; i < n; i++) {
        result += i;
    }
    return result;
}
```

Đây là một **method minh họa**, không có `main`. Gọi method một lần với `n` rất lớn vẫn có thể tăng backedge counter đủ để runtime xem xét OSR. Gọi method liên tục với `n=0` lại tạo invocation count lớn dù loop body không chạy.

### 5.2. Type profiles và inlining

Một lời gọi ảo:

```java
interface Worker { int work(int x); }

static int apply(Worker w, int x) {
    return w.work(x);
}
```

Đây là **đoạn minh họa**, cần đặt trong các types đầy đủ để chạy. Nếu trong runtime phần lớn `w` có đúng một concrete class, VM có thể ghi nhận **monomorphic call site**, inline method phù hợp và thêm guards để giữ correctness.

Nếu sau này xuất hiện nhiều types hoặc nạp subclass mới làm giả định không còn hợp lệ, optimized code có thể **deoptimize**. Điều này không có nghĩa JIT biên dịch sai; speculative optimization là hợp lệ nếu VM có cơ chế rút lui đúng.

### 5.3. Branch profiles và loop optimizations

Giả sử:

```java
if (x >= 0) {
    fastPath();
} else {
    rarePath();
}
```

Đây là **pseudocode Java**; `fastPath` và `rarePath` phải được định nghĩa mới biên dịch. Khi một nhánh hiếm, JIT có thể đặt hot path thuận tiện hơn trong machine code. Nhưng **không thể** từ đó suy rằng nhánh hiếm bị xóa bỏ và không bao giờ cần thực thi. VM vẫn phải bảo toàn tính đúng đắn khi điều kiện thay đổi.

### 5.4. Profile không bất biến

Profile được ghi từ các inputs thực tế và có thể khác giữa warm-up với production workload. Những hành vi làm thay đổi profile:

- Dữ liệu đầu vào không còn cùng phân bố.
- Cache warms up, request traffic thay đổi.
- Dynamic proxies hoặc subclasses mới được nạp.
- Class loaders khác làm tăng polymorphism.
- Code hot thay đổi theo workload phase.
- Recompilation, code cache pressure hoặc compilation limits.

Vì vậy không dự đoán machine code cuối cùng chỉ từ Java source; nó phụ thuộc **runtime evidence**.

## 6. C1 và C2 khác nhau ở chi phí và tối ưu

| Khía cạnh | C1 | C2 |
| --- | --- | --- |
| Định hướng | Biên dịch tương đối nhanh, hỗ trợ tiered warm-up | Tối ưu chuyên sâu cho code nóng |
| Compilation cost | Thường thấp hơn | Thường cao hơn |
| Runtime profiling | Level 2/3 có instrumentation theo mức | Tận dụng profiles; optimized output ít profiling hơn |
| Compilation levels | 1, 2, 3 trong sơ đồ HotSpot | 4 |
| Tối ưu | Các tối ưu C1 phù hợp, hướng thời gian compile nhanh | Inlining sâu, loop optimization, speculative optimizations, vectorization khi áp dụng |
| Startup | Có thể đưa method hot sang native code sớm | Có thể tạo compile latency/CPU nếu dùng quá sớm |
| Steady-state | Đủ tốt cho nhiều methods | Có thể đạt thông lượng cao hơn trên hot paths |
| Code cache | Tạo C1 compiled nmethods, có bản profiled | Tạo C2 compiled nmethods, thường non-profiled |
| Rủi ro hiểu nhầm | C1 level 3 luôn nhanh hơn level 2 | C2 luôn nhanh nhất cho mọi method |

Từ “C1” lịch sử gắn với **client compiler**, “C2” gắn với **server compiler**, nhưng trong HotSpot hiện đại tiered compilation có thể dùng cả hai **trong cùng một Server VM**. Đừng nghĩ cần chạy `-client` để có C1 trên JDK 17 64-bit.

### C2 không biến Java thành unsafe code

Tối ưu hóa có thể loại bỏ allocation vật lý, inline virtual calls, biến đổi loops hay bỏ checks đã chứng minh dư thừa **miễn vẫn bảo toàn ngữ nghĩa quan sát được**: exceptions, synchronization, Java Memory Model, class initialization, safepoints và các điều kiện bắt buộc.

Nếu một giả định speculative sai, VM có thể deopt và khôi phục trạng thái method/frames ở một điểm hợp lệ. **Speculation không cho phép JIT trả kết quả sai tùy ý**.

## 7. Compilation policy, thresholds và compile queues

HotSpot không JIT method ngay khi invocation count chạm một con số “ma thuật” cố định trên mọi JVM.

Policy có thể cân nhắc:

- Invocation count và backedge count.
- Rate của các events, tốc độ method trở nên hot.
- Profile data đã đủ hữu ích chưa.
- Compiler queue length và compiler threads.
- Method size/bytecode complexity.
- Code cache space.
- Compilation exclusions và compiler failure cases.
- JVM flags, tiered policy và version.

### Compile queue không phải một danh sách FIFO đơn giản

Các compile requests có thể vào hàng chờ của C1/C2, có mức ưu tiên theo Hotness/estimated benefit, và một request có thể trở nên **stale** khi workload thay đổi. VM có thể điều chỉnh thresholds khi compiler bận để tránh biên dịch hàng loạt methods không còn hot.

```text
Method A đang được gọi rất nhiều ─► C1 queue ─► C1 worker
                                        │
                                        ▼
                                   C1 nmethod
                                        │ profiling
                                        ▼
                                     C2 queue ─► C2 worker
                                                    │
                                                    ▼
                                              C2 nmethod
```

Sơ đồ là mô hình, không phải đảm bảo mỗi method luôn có đúng một request trong mỗi queue.

### Compiler threads là tài nguyên runtime

C1/C2 compilation dùng CPU và memory; chúng có thể chạy **bất đồng bộ so với application threads**. Ứng dụng tiếp tục chạy interpreted/C1 code trong khi C2 đang compile. Compile activity ảnh hưởng:

- CPU vào giai đoạn warm-up.
- Tốc độ startup/ready.
- Code cache occupancy.
- Throughput dài hạn sau khi hot methods được tối ưu.

Vì vậy “JVM còn chậm ở 10 giây đầu” có thể do chưa warm up, nhưng cũng có thể do I/O, class loading, cache misses, GC, allocations hay external services. Cần đo đa chiều.

## 8. On-Stack Replacement (OSR) cho vòng lặp đang chạy

Khi một method được gọi **một lần** nhưng loop chạy lâu, sẽ không hiệu quả nếu VM phải chờ method return mới dùng compiled code trong lần gọi sau. **OSR** cho phép biên dịch một entry tương ứng với một **loop/backedge bytecode index** rồi chuyển execution từ interpreter/C1 sang optimized code phù hợp khi method vẫn đang chạy.

```text
Method gọi lần đầu ở interpreter
              │
              ▼
        loop rất dài
              │
       backedge đủ nóng
              │
              ▼
         OSR compile
              │
              ▼
         OSR nmethod
       (entry ở loop BCI)
              │
              ▼
     tiếp tục loop ở code compiled
```

- OSR compiled code có thể **khác** normal-entry compiled code của cùng method.
- `PrintCompilation` có thể đánh dấu OSR bằng ký hiệu `%`; những code/notations khác tùy HotSpot version.
- OSR không đơn giản là “chuyển toàn bộ Java stack sang code cache” — đó là chuyển **execution state** tại điểm hợp lệ.
- Một JVM có thể chọn không OSR trong một lần chạy cụ thể; việc loop nóng không bảo đảm thấy đúng một OSR compile event.

### OSR và tiered levels

Một OSR nmethod có thể được tạo ở cấp độ thích hợp theo VM policy, không nhất thiết chờ tất cả các compilation levels. Khi xem log, phải phân biệt **OSR compile của method** với **normal-entry compile** thay vì cộng chúng như hai method source khác nhau.

## 9. Deoptimization: khi optimized assumptions không còn phù hợp

C2 có thể tối ưu dựa trên type/branch profiles và **guards**. Nếu cần quay về execution path tổng quát, HotSpot có thể thực hiện **deoptimization**.

```text
C2 optimized method
      │
      ├─ assumptions còn hợp lệ ──► tiếp tục mã tối ưu
      │
      └─ guard thất bại/class thay đổi
                    │
                    ▼
            deoptimization
                    │
                    ▼
         interpreter frame state
         hoặc đường thực thi khác
                    │
                    ▼
            profile/recompile nếu cần
```

Những ví dụ:

- Call site từng chỉ nhận class `Dog` nhưng sau đó nhận `Cat`.
- Class hierarchy thay đổi khi một subclass mới được load.
- Rare branch/exceptions xuất hiện nhiều hơn.
- Optimized code phụ thuộc giả định về synchronization hoặc reference state được VM kiểm tra.

**Deoptimization không đồng nghĩa exception hoặc JVM crash.** Nó là cơ chế **duy trì tính đúng đắn khi đã sử dụng speculative optimization**.

### Uncommon traps và recompile

HotSpot có thể đưa đường “hiếm” qua **uncommon trap** để trở về execution tổng quát. Nếu đường đó về sau phổ biến, profile có thể thay đổi và JVM biên dịch lại code ít giả định hơn hoặc tối ưu lại theo dữ liệu mới.

Đọc code JIT đã in ra phải chú ý **từng compile ID/level/BCI và trạng thái phiên bản**, không khẳng định một method mãi chỉ có một compiled body.

## 10. Code cache giữ kết quả biên dịch C1/C2

Mã máy do C1 hoặc C2 tạo được quản lý trong **HotSpot code cache**, thường dưới dạng **nmethods**. Code cache ở vùng native executable memory, **khác Java heap**, metaspace và stack frames.

Một HotSpot cấu hình **segmented code cache** có thể có:

| CodeHeap | Mục đích |
| --- | --- |
| **non-nmethods** | VM-generated runtime stubs, adapters và code không phải compiled Java method |
| **profiled nmethods** | Code C1 có profiling, thường phục vụ giai đoạn warm-up và chuyển level |
| **non-profiled nmethods** | Code ít/không profiling, gồm nhiều compiled methods tối ưu dài hạn |

Không đánh đồng một CodeHeap với một compilation level tuyệt đối; phân bổ thật phụ thuộc version/mode. C1 level 1 có thể nằm ở vùng non-profiled, trong khi C1 level 3 mang instrumentation phù hợp với vùng profiled.

### Khi code cache đầy

Nếu code cache không còn đủ không gian cho nmethod mới, HotSpot có thể **giảm/ngừng compilation** và in cảnh báo dạng:

```text
CodeCache is full. Compiler has been disabled.
```

Đây là **mẫu thông báo thường gặp**, không phải string cam kết của mọi release. Ứng dụng có thể tiếp tục chạy ở interpreter/mã đã có nhưng mất cơ hội tối ưu thêm. Không kết luận chắc chắn code cache đầy là nguyên nhân chỉ vì throughput thấp; cần thống kê code heap, queues và logs.

Các thao tác **code sweeping**, **not entrant/zombie nmethods**, **class unloading** và **deoptimization** giúp quản lý vòng đời compiled code. Không phải cứ JIT compile một method thì native code tồn tại vĩnh viễn tới khi process thoát.

## 11. Bật/tắt tiered compilation trên HotSpot JDK 17

Các lệnh sau là ví dụ dùng đúng **HotSpot**, không phải Java SE flags chuẩn mọi JVM:

| Option | Ý nghĩa | Cẩn trọng |
| --- | --- | --- |
| `-XX:+TieredCompilation` | Bật tiered compilation nếu JVM/build hỗ trợ | Trong nhiều Server VM hiện đại đã bật mặc định |
| `-XX:-TieredCompilation` | Tắt tiered compilation policy | **Không đồng nghĩa chỉ dùng interpreter**; JVM có thể vẫn JIT |
| `-XX:TieredStopAtLevel=1` | Giới hạn mức compilation, thường giữ C1 no-profiling | Không chứng minh mọi method đều được compile |
| `-XX:TieredStopAtLevel=3` | Cho phép các level tới 3, không dùng level 4 của sơ đồ thường | Compiler/mode/runtime flags có thể ảnh hưởng |
| `-Xint` | Chế độ **interpreted-only** cho Java methods | Phù hợp thí nghiệm correctness/perf, thường chậm |
| `-Xcomp` | Ưu tiên aggressively compile methods sớm | Có chi phí startup; không phản ánh chạy bình thường |
| `-XX:+PrintCompilation` | In những compilation events | Output biến động theo runtime |
| `-XX:+PrintCodeCache` | In thống kê code cache | VM/build dependent |
| `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` | Chẩn đoán quyết định inlining (nếu hỗ trợ) | Rất nhiều output, không bật bừa trên production |

**Một bẫy phổ biến:** `-XX:-TieredCompilation` **không phải** một cách viết dài của `-Xint`. `-Xint` rõ ràng hơn khi mục tiêu là so sánh interpreter-only.

### Chú ý về `CompileThreshold`

Không thể khẳng định “trên mọi HotSpot, cứ gọi method đúng 10.000 lần thì được C2 biên dịch”. Trong tiered mode, thresholds chịu tác động counters, rate, compile queues, tier transitions và các JVM flags khác; `CompileThreshold` đơn lẻ không mô tả toàn bộ policy.

Nếu muốn học ý nghĩa từng threshold flag, đọc chính xác **JDK version/source** và dùng compiler logs. Thay threshold có thể làm profile chưa đủ, compile queue quá tải hoặc warm-up khác đi; không nên dùng để tối ưu production khi chưa benchmark.

## 12. Lab Java 17+: method nóng và vòng lặp có thể OSR

Tạo file duy nhất **`TieredCompilationDemo.java`**:

```java
public class TieredCompilationDemo {
    private static volatile long lastValue;

    static long score(int n) {
        long sum = 0;
        for (int i = 0; i < n; i++) {
            sum += (i & 7);
        }
        return sum;
    }

    static long longLoop(int n) {
        long sum = 0;
        for (int i = 0; i < n; i++) {
            sum += i % 13;
        }
        return sum;
    }

    public static void main(String[] args) {
        long checksum = 0;
        int repeats = 80;

        for (int j = 0; j < repeats; j++) {
            long result = score(1_000_000);
            checksum += result;
            lastValue = result;
        }

        long osrCandidate = longLoop(1_300_000);

        System.out.println("score: " + lastValue);
        System.out.println("iterations: " + repeats);
        System.out.println("checksum: " + checksum);
        System.out.println("long loop: " + osrCandidate);
        System.out.println("done");
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -encoding UTF-8 TieredCompilationDemo.java
java TieredCompilationDemo
```

**Standard output chính xác khi chạy không bật compiler/GC logging:**

```text
score: 3500000
iterations: 80
checksum: 280000000
long loop: 7800000
done
```

### Giải thích vì sao kết quả cố định

- `i & 7` cho dãy tuần hoàn `0,1,2,3,4,5,6,7`, tổng **28** mỗi 8 giá trị.
- `1_000_000 / 8 = 125_000` chu kỳ nên mỗi `score(1_000_000) = 125_000 × 28 = 3_500_000`.
- Lặp `80` lần và cộng dồn nên `checksum = 80 × 3_500_000 = 280_000_000`.
- `i % 13` cho một chu kỳ từ 0 đến 12, tổng **78**. `1_300_000 / 13 = 100_000` chu kỳ nên `longLoop = 7_800_000`.
- Dùng `long` cho tổng để tránh hiểu nhầm overflow khi bài tập thay số lần lặp.
- `lastValue` là `volatile`: việc ghi/đọc giá trị được thiết kế có hiệu ứng observable, ngăn suy diễn source loop chắc chắn bị loại bỏ hoàn toàn; dù vậy VM vẫn được tối ưu các đường thực thi bảo toàn semantics.

**Không có guarantee JIT:** loop nhiều iterations tạo **cơ hội** cho profiling/OSR, không bảo đảm level hay số compilation events cố định trên mọi CPU/JVM/config.

## 13. Quan sát level của method bằng `PrintCompilation`

Trên HotSpot:

```bash
java -XX:+PrintCompilation TieredCompilationDemo
```

Ngoài năm dòng output của chương trình, JVM có thể in nhiều compiler events cho cả **methods của JDK libraries**. Một log có thể có dạng:

```text
...  3   TieredCompilationDemo::score (N bytes)
...  4   TieredCompilationDemo::score (N bytes)
...  %   4   TieredCompilationDemo::longLoop @ BCI (N bytes)
```

Đây là **mẫu cấu trúc**, không phải log được đo và không phải những dòng bắt buộc xuất hiện. `N bytes` là kích thước bytecode/method được VM báo, còn **BCI** là bytecode index ở OSR entry. Output thực tế có compile ID, timestamp, flags và thông tin version-specific khác.

### Cách đọc đúng

- **Compile ID:** định danh sự kiện compilation trong VM process.
- **Level** như 1,2,3,4: cấp compilation theo tiered policy (khi hiện cột đó).
- **Method name:** `Class::method` được biên dịch hoặc liên quan sự kiện.
- **`%`:** thường báo một sự kiện **OSR compilation**.
- **`made not entrant`:** version compiled code không còn nhận lời gọi mới trong tình huống được đánh dấu.
- **`made zombie`:** trạng thái nội bộ của compiled code không còn được dùng theo vòng đời VM.

**Không suy luận mọi method đều phải in 3 rồi 4.** Nếu interpreter hoặc C1 policy khác, quá trình kết thúc trước khi C2 biên dịch, compile queue chưa tiêu hoặc JVM đã tối ưu theo cách khác, log có thể thiếu level 4.

### Thử các chế độ khác nhau

```bash
java -Xint TieredCompilationDemo
java -XX:TieredStopAtLevel=1 -XX:+PrintCompilation TieredCompilationDemo
java -XX:TieredStopAtLevel=3 -XX:+PrintCompilation TieredCompilationDemo
java -XX:+PrintCompilation TieredCompilationDemo
java -XX:-TieredCompilation -XX:+PrintCompilation TieredCompilationDemo
```

Những lệnh này chạy **năm JVM processes riêng**. **Kết quả tính toán của chương trình phải giữ nguyên** ở tất cả các lệnh được runtime hỗ trợ; nhưng compilation logs và thời gian chạy khác nhau.

**Mục tiêu của bài tập** là nhìn thấy **đường execution thay đổi**, chứ không khẳng định level 1 phải có đúng X events hay level 4 nhất định xuất hiện khi chạy một lần ngắn.

## 14. `javap` chỉ hiển thị bytecode, không hiển thị C1/C2 output

Lệnh:

```bash
javap -c -p TieredCompilationDemo
```

cho các opcode bytecode như `iload`, `iand`, `i2l`, `ladd`, `iinc`, conditional branches, `lreturn`, và lời gọi `invokestatic` phù hợp. `javap` đọc class file, **không chụp code cache** của JVM đang chạy.

### Nếu muốn xem native assembly do JIT sinh

HotSpot có diagnostic mechanisms như:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintAssembly TieredCompilationDemo
```

Nhưng `PrintAssembly` thường yêu cầu thư viện **hsdis** đúng OS/architecture/JDK build, và output có thể rất lớn hoặc không có assembly nếu bộ disassembler chưa sẵn. **Không coi việc không thấy assembly là bằng chứng C2 không hoạt động.** Dùng `PrintCompilation` hoặc công cụ profiler trước khi đi vào assembly.

Một số build/tooling có thể dùng `CompileCommand=print` để giới hạn methods, nhưng cú pháp và requirements phải kiểm tra trên đúng HotSpot version; đừng copy một cấu hình dài vào production khi chưa thử.

## 15. Quan sát compile queues, code cache bằng `jcmd`

Trên JDK/HotSpot hỗ trợ tool `jcmd`, một JVM process đang chạy có thể cung cấp chẩn đoán JIT:

```bash
jcmd -l
jcmd PID help
jcmd PID Compiler.queue
jcmd PID Compiler.codelist
jcmd PID Compiler.codecache
```

`PID` là **placeholder**, phải thay bằng mã số tiến trình thực. Đừng gõ nguyên dấu `<PID>` trong shell vì nó có thể bị hiểu là cú pháp redirect.

| Lệnh | Cách dùng |
| --- | --- |
| `Compiler.queue` | Quan sát những methods đang chờ compile |
| `Compiler.codelist` | Liệt kê nhiều compiled methods/code đang sống trong VM |
| `Compiler.codecache` | Thống kê bố trí/dung lượng code cache |
| `VM.flags` | Kiểm tra effective flags của JVM |
| `help` | Xác minh một diagnostic command có được build hỗ trợ |

**Lưu ý:** chương trình `TieredCompilationDemo` có thể chạy quá nhanh để bạn gõ `jcmd` đúng lúc. Dùng một process test lâu sống hoặc service đang vận hành với quyền truy cập cho phép.

### Code cache và compile queue quá tải khác nhau

- **C2 queue dài:** C2 chưa xử lý hết compilation requests; JVM có thể tiếp tục chạy interpreter/C1 code.
- **Code cache đầy:** không còn chỗ phù hợp cho code blobs mới, compilation có thể bị hạn chế.
- **Profile chưa đủ:** policy chưa gửi method tới compile hoặc chưa chọn level 4.
- **Method bị loại khỏi compilation:** có compiler exclusion/limit/failure, hoặc mode `-Xint`.
- **CPU bị throttle:** compiler threads khó nhận CPU, khiến warm-up lâu.

Không chỉ thấy throughput thấp là lập tức tăng code cache. Phải đo **queue lengths, effective flags, code cache use, CPU throttling và load**.

## 16. Compilation MXBean và công cụ monitoring

Java Management API có `java.lang.management.CompilationMXBean`, **nếu JVM expose**. Nó có thể báo tên JIT compiler và `totalCompilationTime`, nhưng không cung cấp một standardized log của mọi compilation level:

```java
import java.lang.management.CompilationMXBean;
import java.lang.management.ManagementFactory;

public class CompilerInfoDemo {
    public static void main(String[] args) {
        CompilationMXBean bean =
                ManagementFactory.getCompilationMXBean();

        if (bean == null) {
            System.out.println("compiler bean: unavailable");
            return;
        }

        System.out.println("compiler: " + bean.getName());
        if (bean.isCompilationTimeMonitoringSupported()) {
            System.out.println("time(ms): "
                    + bean.getTotalCompilationTime());
        } else {
            System.out.println("time(ms): unsupported");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CompilerInfoDemo.java
java CompilerInfoDemo
```

**Output có cấu trúc rõ nhưng giá trị biến động:** compiler name và compilation time phụ thuộc JVM/mode, có thể `compiler bean: unavailable` hoặc `time(ms): unsupported`. Không đưa một con số ms cố định, vì thời điểm khởi tạo VM, workload và JIT threads khác nhau.

### Vì sao JMX không thay compiler log?

`CompilationMXBean` giúp biết tình trạng JIT tổng quát, nhưng **không** trực tiếp chứng minh method `score` đã lên level 4. Muốn phân tích từng method, dùng `PrintCompilation`, JIT logs, JFR compiler events hoặc công cụ profiler được hỗ trợ; muốn phân tích machine instructions phải dùng công cụ decode đúng VM.

## 17. Các đánh đổi về hiệu năng

### Startup vs steady state

Một ứng dụng CLI 2 giây có thể **kết thúc trước khi hưởng lợi nhiều từ C2**. Dành CPU cho profile/compile method mà không được tái dùng đủ lần có thể làm startup hoặc tổng thời gian kém hơn. Một server chạy nhiều ngày với hot methods ổn định có thể có lợi đáng kể từ C2.

**Tiered compilation tồn tại để tìm điểm cân bằng**, không phải vì C2 luôn “mạnh nhất” mà lúc nào cũng nên bật chế độ compile tất cả methods ngay lập tức.

### Warm-up và benchmark sai

Nếu đo:

```java
long start = System.nanoTime();
for (int i = 0; i < 100; i++) {
    targetMethod();
}
long elapsed = System.nanoTime() - start;
```

Đây là **pseudocode Java** có method `targetMethod()` chưa được định nghĩa. Kết quả dễ bị nhiễu bởi class loading, interpreter, C1/C2 transitions, code cache, GC, CPU scheduling và dead-code elimination. Không dùng phép đo một lần để chọn flags.

Với microbenchmark, nên dùng **JMH**, warm-up đủ, nhiều forks, tránh constant folding/dead-code elimination và quan sát JVM flags. Nhưng **cũng không nên warm-up vô hạn** nếu chính startup latency là thứ bạn cần đo. Hãy định nghĩa mục tiêu trước.

### Khi nào cân nhắc `TieredStopAtLevel=1`?

Trên một số serverless/short-lived workloads, giới hạn C1 có thể làm giảm compilation overhead, cải thiện readiness hoặc tiết kiệm code cache. Nhưng steady-state throughput có thể giảm. Không chọn theo cảm giác; đo request latency/warm-up/CPU với application thực.

### Khi nào có thể cân nhắc tắt tiered?

Chỉ khi có lý do benchmark/tuning cụ thể và đã chứng minh trade-off. `-XX:-TieredCompilation` có thể làm compiler policy dùng đường khác (không phải `-Xint`). Đừng cố dùng nó để “tắt JIT” khi điều cần kiểm tra là interpreter-only.

## 18. Troubleshooting các trường hợp thường gặp

| Triệu chứng | Khả năng | Kiểm tra |
| --- | --- | --- |
| Method nóng không lên level 4 | Profile chưa đủ, C2 queue, exclusions, stop level, C2 không hoạt động, code cache | `PrintCompilation`, `Compiler.queue`, effective flags |
| Log chỉ có level 1 | `TieredStopAtLevel=1` hoặc policy chọn C1 no-profiling | `VM.flags` / startup command |
| Không có JIT events | `-Xint`, JVM/tooling không hỗ trợ log, workload quá ngắn | VM mode, logger, lệnh chạy |
| Throughput tăng dần sau startup | JVM warm-up/profile/JIT; cũng có thể cache/app effects | JIT logs, metrics, warm-up phase |
| CPU tăng lúc khởi động | JIT compilation, class loading, GC hoặc app initialization | CPU profiles, compiler events |
| Thời gian compile quá lớn | C2 queue/compilation cost, quá nhiều hot methods | CompilationMXBean, JFR, method-level logs |
| Code cache warning | Native code region cạn capacity/fragmentation | `Compiler.codecache`, flags, code cache logs |
| Method `made not entrant` | Version compiled code bị thay/không còn thích hợp | Deopt/recompilation, class loading |
| `PrintAssembly` không hiển thị assembly | Không có hsdis hoặc thiếu diagnostic setup | JDK architecture/build và hsdis |
| Cùng source có compile level khác | Profile, inputs, CPU quota, JDK build, timing | So môi trường/lần chạy |
| Long loop không thấy OSR | Loop chưa đủ hot theo policy hoặc mode không hỗ trợ | Backedge/workload, `PrintCompilation` |
| `-XX:-TieredCompilation` vẫn JIT | Đó là thay policy, không phải interpreter-only | Dùng `-Xint` khi muốn tắt JIT |

### JVM versions và distributions

Các mức và flags mô tả ở đây nhằm minh họa **HotSpot JDK 17**. Những bản HotSpot mới có thể thay đổi policy, code cache, compiler internals, hoặc bổ sung AOT mechanisms. Một số JVM có compiler khác như **Graal compiler** tại level tối ưu trong cấu hình phù hợp. **OpenJ9** cũng có JIT nhưng không áp trực tiếp năm mức C1/C2 HotSpot này.

Nếu một flag báo không nhận diện, đừng tự kết luận bản Java hỏng: cần xem implementation, JDK version và release docs của binary đó.

## 19. Bảng phân biệt các khái niệm dễ nhầm

| Nhầm lẫn | Thực tế |
| --- | --- |
| “`javac` chính là C1 hoặc C2.” | `javac` biên dịch source thành bytecode trước khi chạy; C1/C2 tạo native code khi runtime |
| “JVM luôn thông dịch, không bao giờ chạy native code.” | HotSpot có interpreter và JIT compiled native code |
| “C1 chỉ chạy trên Client VM, C2 chỉ trên Server VM.” | HotSpot tiered mode có thể dùng cả hai trong Server VM |
| “Mọi method phải đi level 0→1→2→3→4.” | Policy chọn đường khác tùy profile và queue |
| “Level 1 nghĩa là C1 không tối ưu.” | Có C1 optimizations nhưng không full profiling instrumentation |
| “Level 3 luôn nhanh hơn level 2.” | Profiling có runtime cost, phụ thuộc method |
| “Level 4 code sẽ không bao giờ thay đổi.” | Deopt, recompilation, unloading/code sweeping có thể xảy ra |
| “Gọi method nhiều lần là điều kiện duy nhất của hotness.” | Backedge counters cho loop dài cũng quan trọng |
| “Một method chỉ có một compiled version.” | C1/C2/OSR/recompile có thể sinh nhiều code versions |
| “C2 tối ưu sâu hơn nên mọi chương trình khởi động nhanh hơn.” | C2 compile cost/profile có thể làm startup chậm |
| “`javap -c` là native assembly sau C2.” | Đó là JVM bytecode trong class file |
| “`-XX:-TieredCompilation` tắt JIT.” | Không nhất thiết; `-Xint` mới là interpreter-only |
| “`TieredStopAtLevel=1` đảm bảo mọi method có C1 code.” | Cold methods có thể mãi interpreted |
| “C2 queue rỗng nghĩa là mọi hot method đã tối ưu.” | Có thể compilation bị vô hiệu, profile chưa đủ hoặc stop level |
| “`PrintCompilation` event count luôn xác định.” | Phụ thuộc JDK, CPU, workload, timing và compiler state |
| “HotSpot tiered levels là tính năng chuẩn của mọi JVM.” | Đó là implementation detail |
| “Code cache là Java heap.” | Mã native nằm trong vùng HotSpot code cache, ngoài heap objects |
| “Deoptimization chứng minh compiler sai.” | Đó là cơ chế rút lui hợp lệ khỏi speculative assumption |

## 20. Bài tập có đáp án

**Bài 1.** HotSpot level 0 là gì?  
**Đáp án:** Interpreter; JVM có thể thực thi bytecode trước khi method được JIT compile.

**Bài 2.** C1 thường tạo compiled code ở levels nào?  
**Đáp án:** 1, 2, 3; khác nhau về mức profiling.

**Bài 3.** C2 thường tương ứng level nào trong mô hình tiered HotSpot?  
**Đáp án:** Level 4, hướng tới full optimization.

**Bài 4.** Level 3 có phải “tối ưu sâu nhất” vì số 3 lớn hơn 2?  
**Đáp án:** Không. Nó là C1 với profiling đầy đủ; level 4 mới là C2 tối ưu sâu hơn.

**Bài 5.** Vì sao level 2 có thể hữu ích khi C2 queue dài?  
**Đáp án:** Nó tránh một phần profiling overhead của level 3 trong thời gian chờ, vẫn theo dõi invocation/backedge counters.

**Bài 6.** Một method được gọi đúng một lần nhưng loop rất dài có thể được JIT khi còn đang chạy?  
**Đáp án:** Có thể, qua OSR nếu backedges và policy phù hợp.

**Bài 7.** `PrintCompilation` có dấu `%` thường báo gì?  
**Đáp án:** Một OSR compilation event trong format HotSpot thường gặp.

**Bài 8.** Một optimized call site từng chỉ thấy một type, sau đó thấy type khác, có thể xảy ra gì?  
**Đáp án:** Deoptimization, profile update và recompilation; chương trình vẫn phải giữ đúng semantics.

**Bài 9.** `-XX:TieredStopAtLevel=1` có bắt JVM compile mọi method không?  
**Đáp án:** Không; nó giới hạn mức nếu compile, còn cold methods có thể interpreted.

**Bài 10.** Tắt tiered bằng `-XX:-TieredCompilation` có đồng nghĩa tắt JIT?  
**Đáp án:** Không; dùng `-Xint` khi muốn interpreter-only.

**Bài 11.** `javap -c` có cho biết C2 đã inline method chưa?  
**Đáp án:** Không. Nó hiển thị bytecode; cần JIT logs/profiler/native code diagnostics.

**Bài 12.** Vì sao level 4 không phải code vĩnh viễn?  
**Đáp án:** Assumptions có thể thay đổi, deoptimization hoặc compiled-code lifecycle khiến VM thay version.

**Bài 13.** C2 queue dài có thể gây gì?  
**Đáp án:** Warm-up lâu hơn, method tiếp tục chạy interpreter/C1 trong khi chờ C2.

**Bài 14.** `TieredCompilationDemo.score(1_000_000)` trả bao nhiêu?  
**Đáp án:** 3.500.000 vì `i & 7` có chu kỳ 8 với tổng 28.

**Bài 15.** `TieredCompilationDemo` in tổng checksum bao nhiêu với 80 lần lặp?  
**Đáp án:** 280.000.000.

**Bài 16.** `longLoop(1_300_000)` có tổng bao nhiêu khi cộng `i % 13`?  
**Đáp án:** 7.800.000.

**Bài 17.** Nếu một app CLI kết thúc trong hai giây, ép JIT sớm nhất có luôn lợi?  
**Đáp án:** Không. Compilation cost có thể lớn hơn lợi ích nếu code chưa tái dùng đủ.

**Bài 18.** Nếu code cache đầy, có phải Java heap thiếu chỗ?  
**Đáp án:** Không nhất thiết. Code cache là vùng native riêng, dù cả hai cộng vào resource footprint.

**Bài 19.** Dùng gì để kiểm tra compile events của một method trong HotSpot JDK 17?  
**Đáp án:** `-XX:+PrintCompilation`, log compilation/JFR và các công cụ diagnostic phù hợp; đối chiếu flags và workload.

**Bài 20.** Có thể áp sơ đồ HotSpot 0–4 trực tiếp sang OpenJ9 không?  
**Đáp án:** Không. Đây là cách tổ chức tiered JIT của HotSpot, không phải JVM-spec requirement.

## 21. Checklist khi điều tra JIT warm-up

- [ ] Đã xác nhận vendor, JVM implementation, version và architecture?
- [ ] Đã xác minh `TieredCompilation`, `TieredStopAtLevel` và effective flags?
- [ ] Đã phân biệt interpreter-only (`-Xint`) với tiered disabled?
- [ ] Có quan sát compile events theo **method + level + OSR status**?
- [ ] Có đo C1/C2 compile queues, code cache và compiler threads khi cần?
- [ ] Có warm-up và đo nhiều lần để giảm nhiễu?
- [ ] Có phân biệt startup latency với steady-state throughput?
- [ ] Có xem khả năng inlining, profile và deoptimization khi performance đổi bất thường?
- [ ] Có tránh kết luận mỗi method phải tới level 4?
- [ ] Có phân biệt Java bytecode và machine code trong HotSpot code cache?
- [ ] Có tránh cấu hình tier threshold/compilers tùy tiện trước khi có baseline?
- [ ] Có chú ý CPU quota, GC, I/O, class loading và memory footprint?
- [ ] Có lưu lại runtime flags trong báo cáo benchmark?
- [ ] Có kiểm tra code sau thay đổi vẫn cho output đúng như Java semantics?
- [ ] Có xem JDK release notes khi một flag/log format thay đổi?

## 22. Tổng kết và tài liệu đối chiếu

Mô hình mental model hữu ích:

```text
INTERPRETER (level 0)
  │ chạy bytecode + nhận biết độ nóng
  ▼
C1 (levels 1–3)
  │ compiled code nhanh, profiling theo mức
  ▼
C2 (level 4)
  │ dùng runtime profile để tối ưu sâu
  ▼
CODE CACHE giữ compiled machine code
  │
  └─ deopt/OSR/recompile khi runtime cần

Không phải mọi method đều phải đi đủ các ô trong sơ đồ.
```

**C1** tạo compiled code tương đối sớm, cung cấp nhiều modes thu thập profiling; **C2** dùng profile để tối ưu sâu những đoạn đáng đầu tư. **Tiered policy** quyết định **khi nào, ở cấp nào và có đáng compile hay không** dựa trên invocation/backedge counters, call/type profiles, compiler queues và chi phí biên dịch. **OSR** giải quyết loops nóng trong method đang thực thi; **deoptimization** duy trì correctness khi speculative assumptions thay đổi; **code cache** quản lý nhiều compiled nmethods qua vòng đời JVM.

### Tài liệu tham khảo đáng tin

1. **Microsoft for Java Developers — How Tiered Compilation Works in OpenJDK**, trình bày levels 0–4 và C1/C2: https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/
2. **OpenJDK HotSpot source — compilationPolicy.hpp** (tiered policy, queues, threshold decisions): https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.hpp
3. **OpenJDK HotSpot JDK 17 source** (để đối chiếu cùng release): https://github.com/openjdk/jdk/tree/jdk-17%2B35/src/hotspot/share/compiler
4. **Oracle JDK 17 — The java Command** (flags `TieredCompilation`, `PrintCompilation`, `PrintInlining`, code cache): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
5. **Oracle JDK 17 — jcmd** (Compiler.queue, Compiler.codelist, Compiler.codecache): https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
6. **OpenJDK JEP 197 — Segmented Code Cache** (profiled vs non-profiled nmethods): https://openjdk.org/jeps/197/
7. **Java SE 17 — CompilationMXBean**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/CompilationMXBean.html

**Thông điệp chính:** Biên dịch phân tầng không đơn thuần “C1 nhanh, C2 chậm” mà là cơ chế **đầu tư compiler resources theo mức độ nóng và profile runtime**. Khi tối ưu Java, hãy đo mục tiêu cụ thể — startup, warm-up, throughput, latency và compile overhead — thay vì coi một compilation level hay một set flags là tối ưu trong mọi môi trường.