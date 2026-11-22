# 19.1. Khi nào cần debugger để kiểm tra trạng thái mà log hoặc profiler chưa giải thích được

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Quyết định **khi nào nên dùng debugger** thay vì tiếp tục thêm log, chạy profiler hoặc lấy thread dump.
- Phân biệt **bằng chứng về trạng thái và luồng điều khiển** (debugger), **diễn biến sự kiện** (log/trace), **thống kê chi phí** (profiler/JFR) và **ảnh chụp thread** (thread dump).
- Sử dụng breakpoint, conditional breakpoint, exception breakpoint, call stack, variables, watches và **Step Into / Over / Out** để tìm nguyên nhân một invariant bị phá vỡ.
- Tái hiện và phân tích một lỗi Java 17+ mà đầu ra cuối cùng cho thấy sai nhưng không chỉ ra **biến trung gian nào** đã được dùng không đúng.
- Biết giới hạn khi debug hệ nhiều thread, virtual threads và ứng dụng production: **pause có thể thay đổi timing**, gây timeout/deadlock giả, làm gián đoạn dịch vụ hoặc tạo rủi ro bảo mật nếu mở JDWP.

Trọng tâm không phải “cách bấm mọi nút của một IDE”, mà là **chọn debugger đúng lúc và dùng nó để đặt câu hỏi về trạng thái chương trình**. Các tên menu trong IntelliJ IDEA, Eclipse và VS Code Java Debugger có thể khác nhau, nhưng nguyên tắc tương đương.

## 1. Một vấn đề, bốn cách quan sát khác nhau

Khi ứng dụng chạy sai, các công cụ chẩn đoán không cùng trả lời một câu hỏi.

| Công cụ | Thường trả lời tốt | Thường không thể chứng minh trực tiếp |
|---|---|---|
| **Log có cấu trúc** | Hệ thống đã ghi sự kiện gì, vào lúc nào, với request/correlation ID nào; đã đi qua nhánh ghi log nào | Giá trị chính xác của một local variable **tại dòng chưa được log**, biến vừa bị ghi đè ở đâu |
| **Metrics, tracing** | Mức lỗi, latency, throughput; request đi qua những service/span nào | Toàn bộ object graph/branch trong một stack frame Java |
| **Profiler, JFR, CPU/allocation profiles** | CPU tập trung ở stack nào, allocation/GC/lock/I/O có tăng không; xu hướng theo khoảng thời gian | Vì sao **một field mang giá trị sai** nếu thao tác đó rất nhanh, hiếm và không có event phù hợp |
| **Thread dump** | Những thread nào đang chạy/chờ, stack và dấu hiệu lock/deadlock tại thời điểm lấy mẫu | Hầu hết local values và diễn biến thay đổi state từng bước |
| **Debugger** | Tại một điểm dừng, biến local, field, giá trị tham số, object identity, thứ tự gọi, nhánh điều kiện và call stack **cụ thể** | Toàn cảnh hiệu năng khi breakpoint làm thay đổi timing; dữ liệu đã biến mất trước khi dừng |

**Quy tắc chọn:** Khi câu hỏi còn là **“phần nào tốn CPU / chờ I/O / cấp phát nhiều?”**, ưu tiên profiler, JFR và số liệu. Khi câu hỏi chuyển thành **“tại sao request này lại đi vào nhánh này, và object này mang giá trị này ở thời điểm này?”**, debugger thường có giá trị hơn.

Debugger làm việc bằng việc **tạm dừng hoặc quan sát có điều kiện** một JVM. Giá trị trong IDE là **trạng thái tại điểm quan sát**; nó không tự cung cấp lịch sử đầy đủ trước đó nếu bạn không đặt breakpoint/watchpoint hay ghi dữ liệu từ trước.

### Ví dụ một tín hiệu chưa đủ để kết luận

Giả sử log cho thấy:

```text
checkout request=EDGE finished payable=-500
```

Log đã xác nhận **đầu ra sai**. Một CPU profiler có thể báo không có hotspot vì phép tính chỉ mất vài micro-giây. Nhưng câu hỏi còn lại là: **Giá trị `payable` âm được tính từ tham số nào? Một field đã được chuẩn hóa hay chưa? Ai đã gọi phương thức?**

Đó là một tình huống debugger phù hợp: dừng **trước phép gán**, kiểm tra các giá trị **cùng thời điểm**, rồi step để xem lệnh nào phá invariant.

## 2. Dấu hiệu nên chuyển sang debugger

### 2.1. Invariant bị vi phạm nhưng log không thấy trạng thái trung gian

Một **invariant** là điều kiện phải luôn đúng trong phạm vi nghiệp vụ/mô hình, ví dụ:

- `payableCents >= 0`.
- `payableCents + appliedDiscountCents == subtotalCents`.
- Đơn hàng ở `PAID` phải có transaction đã xác nhận.
- Đối tượng được xử lý theo một tenant/session nhất quán.

Khi chỉ log kết quả cuối, bạn biết **invariant hỏng**, nhưng không biết nó hỏng **ở dòng gán nào**. Đặt breakpoint trước và sau các thay đổi state là cách trực tiếp thấy chuyển trạng thái.

### 2.2. Một nhánh điều kiện chạy khác với kỳ vọng

Ví dụ `if (user.hasPermission())` đi vào nhánh cho phép trong khi người dùng bị từ chối ở nơi khác. Có thể xảy ra vì:

- Đối tượng `user` khác với đối tượng bạn nghĩ.
- Role/feature flag/config đã được nạp từ nguồn hoặc thời điểm khác.
- Biểu thức boolean có short-circuit `&&`/`||` hoặc giá trị `null` được xử lý theo quy ước khác.
- Điều kiện được kiểm tra **trước** khi state được cập nhật.

Debugger cho phép thấy **tham số đầu vào, giá trị các toán hạng, instance thực, caller và line đang chạy**. Log chỉ chứa `allowed=true` không thể chứng minh hết các giả thuyết đó.

### 2.3. Giá trị bị thay đổi ở đâu đó trong chuỗi gọi

Một field trong object đang đúng ở đầu request, nhưng sai ở cuối. Có nhiều setter, callback, mapper hoặc consumer liên quan, và grep log không tìm được lần thay đổi.

Đây là lúc dùng **field modification watchpoint** (nếu debugger/JVM hỗ trợ) hoặc breakpoint tại các điểm ghi. Watchpoint giúp dừng khi field được gán, xác định **stack/caller thực sự gây thay đổi**; không nhầm nó với local-variable watch trong UI chỉ hiển thị giá trị. Watchpoint có thể rất đắt trên field được cập nhật thường xuyên.

### 2.4. Exception hoặc lỗi chỉ xuất hiện qua một đường hiếm

Khi exception bị bắt rồi bọc lại, chỉ log ở tầng cao, call stack cuối cùng có thể thiếu trạng thái nơi lỗi **được ném lần đầu**. **Exception breakpoint** (caught/uncaught tùy trường hợp) dừng gần điểm throw để kiểm tra biến, điều kiện và stack liên quan.

Cần đặt bộ lọc theo exception class hoặc ngữ cảnh; dừng ở **mọi exception** có thể gây nhiễu rất nhiều vì một số framework sử dụng exception trong đường xử lý thông thường.

### 2.5. Lỗi tái hiện được với đúng dữ liệu nhưng profiler không chỉ ra gì

Các bug logic rất nhanh (làm tròn sai, dùng biến cũ, so nhầm ID, tính nhầm tiền, sai thứ tự update) thường **không tốn CPU**. Không có “hot method” không có nghĩa ứng dụng đúng. Một test có đầu vào ổn định và breakpoint gần invariant có thể tiết kiệm thời gian hơn việc đo thêm nhiều profile.

**Điều kiện ưu tiên:** có thể tái hiện trong môi trường development/test với input đã biết, state đủ gần production và không cần đụng vào dữ liệu nhạy cảm. Nếu bug chỉ xảy ra rất hiếm khi có tải, hãy thu thập bằng chứng trước rồi quyết định debugger có làm lỗi biến mất hay không.

## 3. Khi nào chưa nên dùng debugger?

Debugger không phải bước đầu tiên cho mọi sự cố.

| Tình huống | Công cụ nên ưu tiên trước | Lý do |
|---|---|---|
| CPU 100%, ứng dụng chậm, chưa biết method nào | JFR/CPU profiler, CPU theo process/thread | Breakpoint phá thời gian chạy và khó tìm điểm đặt nếu chưa có giả thuyết |
| Memory footprint tăng qua nhiều giờ | Heap histogram/dump, JFR allocation, NMT/OS metrics | Xem một object tại một breakpoint chưa phản ánh retained memory hay native usage |
| Service treo, hàng nghìn thread đang chờ | Thread dump/JFR Locks/I/O | Dừng thêm JVM có thể làm triệu chứng nặng hơn |
| Lỗi xuất hiện trên hàng triệu request, mỗi lần khác nhau | Structured logs, correlation IDs, metrics, sampling traces | Debug từng request không mở rộng được và có thể làm thay đổi tải |
| Race condition chỉ xảy ra dưới contention | Stress/reproduction tests, JFR/thread dumps, đồng bộ hóa có kiểm chứng | Breakpoint có thể làm lệch thứ tự thread, khiến bug biến mất hoặc phát sinh tình huống mới |
| Production đang phục vụ khách hàng, chưa được phép pause | Bằng chứng không xâm nhập trước | “Suspend all threads” có thể gây timeout, làm kẹt lock và vi phạm SLO |
| Vấn đề ở native code/JNI | Native debugger, native profiler, JVM crash logs | Debugger Java không nhất thiết thấy trạng thái C/C++ bên dưới |
| Đã có log với stack+đủ state chứng minh nguyên nhân | Test hồi quy và sửa bug | Debugger có thể không thêm bằng chứng cần thiết |

**Mẫu quyết định hiệu quả:** Quan sát bên ngoài → đặt một giả thuyết cụ thể → thử xác nhận bằng log/test/JFR ít xâm nhập → dùng debugger nếu vẫn thiếu **state ở một điểm thực thi** → sửa và xác nhận lại bằng test, không chỉ bằng phiên debug.

## 4. Debugger quan sát những gì khi JVM bị dừng?

Một breakpoint tại một dòng có thể cho bạn:

1. **Line và source location:** chính xác vị trí JVM có thể dừng, cùng class/method đã nạp; cần source phù hợp với bytecode đang chạy.
2. **Local variables:** tham số, biến tạm và giá trị trong frame được chọn, nếu thông tin debug có sẵn và debugger/JVM cung cấp.
3. **Object fields:** `this`, fields trong object, các object được tham chiếu, giá trị `null`, collection/maps (với nguy cơ phép hiển thị có thể gọi code).
4. **Call stack:** method nào gọi method hiện tại, giá trị và context của từng frame còn sống.
5. **Threads:** thread nào đang bị dừng, thread nào còn chạy; thread state và lock có thể giúp kiểm tra tình trạng đồng thời.
6. **Control flow:** bước tiếp theo sẽ đi theo nhánh nào khi bạn Step Over hoặc Step Into.

### Phân biệt Step Over, Into và Out

- **Step Over:** thực thi dòng hiện tại (bao gồm việc gọi method nếu có) rồi dừng ở dòng phù hợp tiếp theo trong frame đang xét. Dùng khi đã biết method con không phải nghi vấn.
- **Step Into:** đi vào method được gọi, nếu debugger có source và cài đặt stepping cho phép. Dùng để theo dõi nơi điều kiện hoặc dữ liệu bị tính sai.
- **Step Out:** tiếp tục đến khi thoát method hiện tại và quay lại caller. Dùng để so kết quả method con với trạng thái caller.
- **Resume/Continue:** chạy tới breakpoint/exception tiếp theo; không có nghĩa là chạy thêm đúng một dòng.

**Không dùng Step Into vào mọi method**; code framework, lambda, JDK internals và hàng chục lời gọi phụ khiến bạn mất điểm tựa. Bắt đầu từ invariant và các biến có liên quan, đi sâu khi có bằng chứng.

### Biểu thức Evaluate và side effects

Nhiều IDE có **Evaluate Expression** để tính biểu thức trên object/locals. Cẩn thận: đánh giá `object.toString()`, gọi getter lazy, truy vấn DB, đọc iterator hoặc method có side effect có thể **thực thi code thật trong JVM**, thay đổi state hoặc làm deadlock khi các thread đang bị suspend.

Ưu tiên **xem primitive fields/locals trực tiếp**, chỉ evaluate biểu thức thuần khi hiểu tác dụng phụ. Không sửa biến trong phiên debug để “chứng minh đã fix” rồi bỏ qua test hồi quy; đó là một phép thí nghiệm tạm thời, không phải bản vá.

## 5. Các loại breakpoint nên dùng đúng trường hợp

| Loại | Phù hợp | Điều cần cẩn trọng |
|---|---|---|
| **Line breakpoint** | Dừng trước một dòng gán, điều kiện hoặc gọi method cụ thể | Dòng có thể chạy rất thường xuyên; JVM tạm dừng |
| **Conditional breakpoint** | Chỉ dừng cho một request ID, một giá trị bất thường, một instance | Biểu thức điều kiện được đánh giá nhiều lần; có overhead và không nên có side effect |
| **Exception breakpoint** | Dừng lúc lỗi được ném, kể cả khi framework bắt rồi log chung chung | Dừng ở exception “bình thường” gây nhiễu; lọc loại/đường xử lý |
| **Field access/modification watchpoint** | Tìm call site đọc/ghi một field thay đổi ngoài dự kiến | Có thể có overhead lớn; local variable không phải field watchpoint |
| **Method breakpoint** | Chưa biết dòng nào nhưng muốn thấy lần vào/ra method | Method gọi nhiều có thể cực đắt; đôi khi line breakpoint tốt hơn |
| **Logpoint/tracepoint không suspend** | Muốn thu một giá trị có điều kiện mà không tạm dừng | Vẫn có overhead; công thức logpoint có thể chạy code và làm lộ dữ liệu |

Một **conditional breakpoint** hữu ích khi một method được gọi 100.000 lần nhưng chỉ một case sai: dừng khi `invoice.id.equals("EDGE")` hoặc `requestedDiscountCents > subtotalCents` thay vì dừng mọi lần. Điều kiện phải **không thay đổi state** và rẻ để đánh giá.

Debugger có thể chọn **Suspend: All threads** hoặc **Suspend: Thread** tùy IDE/JVM. “All” cho một snapshot đồng bộ hơn nhưng dừng toàn process; “Thread” giảm tác động tới thread khác nhưng những thread kia **vẫn tiếp tục sửa shared state** trong lúc bạn kiểm tra. Lựa chọn này có thể quyết định liệu kết quả quan sát còn có ý nghĩa hay không.

## 6. Thực hành Java 17+: log cho thấy sai, debugger tìm dòng làm sai

Tình huống: hóa đơn có `subtotalCents`, coupon yêu cầu giảm một số tiền, hệ thống phải **giới hạn discount không vượt subtotal**. Invariant là:

```text
0 <= appliedDiscountCents <= subtotalCents
payableCents >= 0
payableCents + appliedDiscountCents == subtotalCents
```

Chương trình có một lỗi rất nhỏ: field `appliedDiscountCents` được giới hạn đúng, nhưng phép tính `payableCents` lại dùng **giá trị requested trước khi giới hạn**. Profiler có thể hoàn toàn không thấy điều gì lạ vì phép tính gần như không tốn CPU.

### 6.1. Mã nguồn hoàn chỉnh

Tạo file **`DebuggerStateDemo.java`**:

```java
public class DebuggerStateDemo {
    private static final class Invoice {
        private final String id;
        private final int subtotalCents;
        private int appliedDiscountCents;
        private int payableCents;

        Invoice(String id, int subtotalCents) {
            this.id = id;
            this.subtotalCents = subtotalCents;
            this.payableCents = subtotalCents;
        }

        void applyCoupon(int requestedDiscountCents) {
            int capped = Math.min(Math.max(0, requestedDiscountCents), subtotalCents);
            appliedDiscountCents = capped;
            payableCents = subtotalCents - requestedDiscountCents;
        }

        boolean valid() {
            return payableCents >= 0
                    && payableCents + appliedDiscountCents == subtotalCents;
        }

        void printSummary() {
            System.out.printf("%s subtotal=%d discount=%d payable=%d valid=%s%n",
                    id, subtotalCents, appliedDiscountCents, payableCents, valid());
        }
    }

    private static void checkout(Invoice invoice, int couponCents) {
        invoice.applyCoupon(couponCents);
        invoice.printSummary();
    }

    public static void main(String[] args) {
        checkout(new Invoice("NORMAL", 1000), 250);
        checkout(new Invoice("EDGE", 1000), 1500);
    }
}
```

### 6.2. Biên dịch và chạy bình thường

Dùng JDK 17 trở lên; tùy chọn `-g` đưa thông tin biến local/source vào `.class` để debugger có khả năng hiển thị tốt hơn:

```bash
javac --release 17 -g DebuggerStateDemo.java
java DebuggerStateDemo
```

**Stdout chính xác** của bản còn lỗi:

```text
NORMAL subtotal=1000 discount=250 payable=750 valid=true
EDGE subtotal=1000 discount=1000 payable=-500 valid=false
```

Bản ghi kết quả đã cho biết `EDGE` sai, nhưng chưa chỉ ra **tại sao discount được lưu là 1.000 mà payable lại trừ 1.500**. Đây chính là khoảng trống mà debugger sẽ lấp bằng giá trị local và field tại phép gán.

### 6.3. Đặt breakpoint đúng điểm

Mở `DebuggerStateDemo.java` trong IDE có Java Debugger và chạy bằng **Debug**, không phải Run. Trong method `Invoice.applyCoupon`:

1. Đặt **line breakpoint** tại dòng `payableCents = subtotalCents - requestedDiscountCents;`.
2. Thêm **điều kiện** `requestedDiscountCents > subtotalCents` để chỉ dừng case bất thường; IDE cũng có thể lọc theo `id.equals("EDGE")`.
3. Khi dừng, chọn stack frame của `applyCoupon`, mở **Variables** hoặc **Evaluate** chỉ với các biểu thức đọc giá trị.
4. Quan sát trước khi thực thi dòng lỗi:
   - `id = "EDGE"`.
   - `subtotalCents = 1000`.
   - `requestedDiscountCents = 1500`.
   - `capped = 1000`.
   - `appliedDiscountCents = 1000`.
   - `payableCents = 1000` **trước phép gán** (giá trị từ constructor).
5. Chọn **Step Over** một dòng: `payableCents` trở thành **-500**.
6. Xem **Call Stack**: `main() → checkout(...) → Invoice.applyCoupon(...)`. Caller đã chuyển `1500`; lỗi không ở việc mất dữ liệu trong logger mà ở việc method dùng **sai biến**.

**Ghi nhớ:** line breakpoint thường dừng **trước** khi dòng hiện tại được thực thi. Nếu bạn thấy một field chưa thay đổi, hãy nhìn line highlight và step đúng một lần; đừng quy kết câu lệnh đã chạy khi nó còn đang chờ.

### 6.4. Sửa lỗi và kiểm chứng invariant

Thay **duy nhất** dòng đang dùng biến sai:

```java
payableCents = subtotalCents - capped;
```

Đây là **một dòng sửa trong `Invoice.applyCoupon`**, không phải chương trình standalone. Sau sửa, cùng hai input sẽ cho:

```text
NORMAL subtotal=1000 discount=250 payable=750 valid=true
EDGE subtotal=1000 discount=1000 payable=0 valid=true
```

Bài học quan trọng hơn việc sửa một phép trừ: debugger chứng minh **chính xác trạng thái trước/sau phép gán**, tại đúng input, đúng instance và đúng call path. Tiếp theo hãy thêm **unit test** cho coupon nhỏ hơn, bằng, lớn hơn subtotal và coupon âm (nếu nghiệp vụ cho phép). Khi yêu cầu xử lý tiền trong ứng dụng thực, nên quy định đơn vị nguyên cents/decimal hợp lệ, overflow, tiền tệ và các quy tắc hoàn tiền riêng thay vì suy rộng ví dụ đơn giản.

## 7. Debug bằng IDE và jdb/JDWP: hai cách quan sát cùng JVM

### 7.1. Dùng IDE khi có mã nguồn và input tái hiện

Workflow thực tế:

1. Mở đúng project/commit và bảo đảm bytecode đang chạy tương ứng source trong IDE.
2. Chạy test hoặc ứng dụng ở **Debug mode** với input tái hiện; chọn breakpoint tại điểm invariant có thể hỏng.
3. Chọn **conditional breakpoint** để bỏ qua các request bình thường.
4. Khi dừng, quan sát **Parameters → Locals → Fields → Call Stack** trước, rồi mới Step Over/Into.
5. Ghi lại trạng thái cụ thể: “trước gán, capped=1000 nhưng phép tính dùng requested=1500”.
6. Sửa code, chạy regression test không cần debugger và xác nhận log/metrics trở lại bình thường.

Nếu source lệch bản build, breakpoint có thể không hit, nhảy sang dòng khác hoặc locals không hiện đủ. Kiểm tra jar/classpath, source map/symbols, compiler options và các optimization; `javac -g` hữu ích cho ví dụ Java trong bài.

### 7.2. JDWP và công cụ dòng lệnh jdb

Java Platform Debugger Architecture (**JPDA**) gồm những thành phần cho phép debugger điều khiển/quan sát JVM; giao thức **JDWP** nối debugger với debuggee. JDK có `jdb`, một debugger CLI. Với ví dụ đã biên dịch, trong terminal **đầu tiên** chạy local JVM ở chế độ chờ debugger:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 DebuggerStateDemo
```

Ở terminal **thứ hai** trên **cùng máy**:

```bash
jdb -attach 127.0.0.1:5005
```

`suspend=y` nghĩa là JVM tạm dừng lúc khởi động cho tới khi debugger kết nối; hữu ích cho bug startup nhưng không phù hợp nếu bạn muốn process phục vụ request ngay. `suspend=n` cho phép ứng dụng chạy không đợi debugger, tuy nhiên bạn có thể bỏ lỡ một bug xuất hiện quá sớm.

Ví dụ các thao tác JDB trong **phiên tương tác** sau khi đã kết nối và dừng tại breakpoint:

```text
help
where
locals
print this.subtotalCents
print this.payableCents
next
cont
```

Đây là **các lệnh tương tác minh họa**, không phải stdout chương trình; `where`/`locals` cần có **thread đang dừng và frame được chọn**. Để tạo breakpoint theo method, JDB có lệnh `stop in FullyQualifiedClass.method`; với class lồng nhau, tên bytecode chứa dấu `$` (ví dụ `DebuggerStateDemo$Invoice.applyCoupon`). Có thể dùng `stop at Class:line` nếu biết line number của file hiện tại. Với điều kiện complex/correlation ID, debugger IDE thường tiện hơn JDB.

**Tuyệt đối không mở JDWP ra Internet hoặc mạng công cộng.** Debugger có khả năng kiểm soát thực thi/chỉnh trạng thái của JVM; JDWP không nên được xem là API ứng dụng có xác thực và mã hóa an toàn. Ví dụ chỉ bind vào **127.0.0.1** cho thực hành local. Khi phải debug từ xa, dùng môi trường riêng được phân quyền, tunneling an toàn/kiểm soát truy cập và chỉ cho phép người đã được phê duyệt; đóng cổng ngay khi xong. Không sao chép tùy chọn `address=*:5005` vào production.

## 8. Những giới hạn lớn của debugger trong hệ đa luồng

### 8.1. “Pause” thay đổi tiến trình đang quan sát

Khi dừng một thread:

- Những thread khác có thể tiếp tục cập nhật shared field, khiến trạng thái thay đổi trong lúc bạn xem.
- Nếu thread bị dừng đang giữ `synchronized` monitor/lock, thread khác có thể chờ nó, tạo ra **hang/timeout nhân tạo**.
- Khi chọn **Suspend All**, cả JVM đứng lại; client/network bên ngoài không dừng theo, nên timeout/retry có thể bùng lên.
- Thời gian thread bị dừng không được tính như một lần chạy bình thường; benchmark latency/throughput trong phiên breakpoint thường **không đáng tin**.

Một lỗi race có thể **biến mất** vì breakpoint làm thay đổi interleaving, hoặc xuất hiện một bug mới vì môi trường bị giữ tại điểm không tự nhiên (hiện tượng *Heisenbug*).

### 8.2. Dùng công cụ ít xâm nhập cho concurrency trước

Với lỗi tranh chấp hoặc thứ tự thread, nên bắt đầu bằng:

- Thread dumps, JFR thread/lock events và timeline.
- Counters/structured logs có correlation và timestamp phù hợp.
- Stress test tái hiện với đúng kích thước pool, dữ liệu, thời gian và contention.
- Test cho invariant/linearizability hoặc synchronization/visibility khi cần.

Sau khi thu hẹp phạm vi, có thể debug một thread/case xác định. Đừng suy đoán **“đã thấy giá trị đúng khi tạm dừng”** thì không còn data race; debugger có thể vô tình cung cấp thêm điểm đồng bộ hoặc thay đổi lịch chạy.

### 8.3. Virtual threads và async callback

Trong ứng dụng Java dùng virtual threads hoặc chuỗi `CompletableFuture`, một request không nhất thiết tương ứng một OS thread cố định. Debugger/JDI hiện đại có hỗ trợ virtual threads nhưng cách liệt kê/đặt breakpoint tùy bản JDK và debugger; theo tài liệu JDB Java 21, debugger có thể **không liệt kê toàn bộ virtual threads mặc định** để tránh quá tải. Đừng dùng danh sách thread thiếu một virtual thread để kết luận task không tồn tại.

Với async flow, call stack hiện tại có thể **không chứa toàn bộ lịch sử** trước lúc callback được lên lịch. Dùng correlation ID, async stack support của IDE (nếu có), structured trace và event log để bổ sung bối cảnh.

## 9. Quy trình chẩn đoán “log/profiler chưa giải thích được”

Để không sa vào việc step ngẫu nhiên hàng giờ, dùng quy trình có thể lặp:

### Bước 1 — Mô tả sự kiện sai dưới dạng kiểm chứng được

Thay vì “checkout thỉnh thoảng bị lỗi”, viết: “với subtotal=1000, coupon=1500, `payable` phải bằng 0 nhưng thực tế bằng -500”. Ghi input, expected, actual, phiên bản code và môi trường.

### Bước 2 — Dùng dữ liệu sẵn có để thu hẹp nơi đặt breakpoint

Đọc log, trace và exception stack; dùng profiler/JFR nếu triệu chứng là **cost**. Đừng thêm 20 breakpoint ở nơi chưa có giả thuyết. Tìm **invariant đầu tiên** bị sai: state được tạo, chuyển đổi hay ghi ra ở đâu?

### Bước 3 — Dựng test tái hiện không phá dữ liệu thật

Tạo unit/integration test hoặc local fixture an toàn. Thay các service ngoài bằng stub hợp lý nếu bug không phụ thuộc network; giữ nguyên dữ liệu biên, feature flags và thứ tự tác vụ cần thiết. Tránh dùng token/PII thật trong màn hình debug hoặc screenshot.

### Bước 4 — Chọn breakpoint có lọc

Ví dụ dừng tại method áp coupon chỉ khi `requestedDiscountCents > subtotalCents`; với request nhiều người, dùng request ID (nếu được truyền trong phạm vi đó). Tránh dừng cả triệu lần qua một hot loop.

### Bước 5 — Chụp trạng thái có cấu trúc

Tại điểm dừng, ghi:

- Đang ở **method/line nào**, commit/build nào, frame nào?
- Input/parameters thực tế là gì? `this` có đúng instance/tenant không?
- Những field/local nào là **nguồn sự thật**, biến nào là giá trị đã transform?
- Nhánh tiếp theo dựa trên điều kiện gì; kết quả boolean có đúng không?
- Ai gọi phương thức này? Có thể cùng method được gọi thêm một lần từ caller khác không?

### Bước 6 — Step đúng một thay đổi rồi so invariant

So **trước** và **sau** một phép gán, một method call hoặc một branch. Nếu invariant đúng trước dòng và sai sau dòng, bạn đã có một bằng chứng rất mạnh. Nếu nó đã sai **trước khi vào method**, Step Out/call stack chưa đủ: cần đặt breakpoint **sớm hơn ở caller hoặc điểm ghi**.

### Bước 7 — Xác nhận sửa chữa ngoài debugger

Sửa code và chạy test không tạm dừng; tái chạy input biên, nhiều lần dưới tải phù hợp. Nếu có ảnh hưởng hiệu năng, đo bằng profiler/JFR **không bật breakpoint**. Ghi kết luận dựa trên invariant và tests, không dựa trên việc dùng Evaluate gán giá trị đúng tạm thời.

## 10. Các tình huống chọn debugger trong Java thực tế

| Tình huống | Log/profiler đang cho thấy gì? | Dùng debugger để biết điều gì? | Phép xác minh bổ sung |
|---|---|---|---|
| **Sai giá trị sau một phép tính rất nhanh** | Log ghi kết quả, profiler không có hotspot | Biến được chuẩn hóa ở đâu, phép tính dùng biến nào | Unit test cases biên |
| **Vào nhánh “không thể xảy ra”** | Log chỉ ghi tên nhánh | Các toán hạng boolean và config/identity thực tế | Test các tổ hợp điều kiện |
| **Một field bị ghi đè** | Log trước đúng, log sau sai | Watchpoint tìm đúng call site và thread sửa field | Test side effects, ownership và bất biến |
| **Một exception bị wrapper nuốt/bọc** | Stack cuối chỉ trỏ controller/framework | Exception breakpoint tại throw đầu tiên, locals và frame | Test failure path |
| **Cache stale trong một request** | Metrics cache hit bình thường nhưng data sai | Key, entry version, tenant context, state trong cache và caller | Test invalidation/freshness |
| **Lỗi chỉ xảy ra khi nhiều thread** | JFR lock/time, logs khó dựng thứ tự | State từng thread quanh điểm nghi vấn, *nếu pause không che bug* | Stress test/JFR/thread dump là bằng chứng chính |
| **Hot method dùng CPU lớn** | CPU profiler đã tìm đúng call stack | Debugger giúp xem input cụ thể gây nhánh thuật toán đắt | JMH/load test xác minh hiệu năng, không dùng timing khi breakpoint |
| **Lỗi trên production nhưng chưa thể tái hiện** | Traces/logs có correlation, không có full state | Chưa nên attach; cần thêm bằng chứng an toàn/fixture | Instrumentation có điều kiện, sanitized reproducible test |

### Ba ví dụ “thêm log không phải lúc nào cũng tốt hơn”

**Case A — Trạng thái đến từ một object khác.** Log `userId=42`, nhưng method gọi với một đối tượng session cũ cũng có `userId=42`. Debugger kiểm tra `this`, field version, instance identity và frame cho thấy input đang giữ **state stale**. Kết luận dựa trên identity/state, không dựa riêng vào cùng ID string.

**Case B — Feature flag đổi trước lúc kiểm tra.** Log chỉ ghi “flag enabled”. Conditional breakpoint dừng tại nhánh và phát hiện cấu hình effective tại thời điểm request khác với cấu hình đã log ở startup. Cần so timestamp, tenant/environment/config revision; debugger cho trạng thái hiện tại, logs giúp giải thích lịch sử.

**Case C — Field được cập nhật hai lần.** Mã tính amount đúng, nhưng một callback sau đó ghi đè. Watchpoint/breakpoint ở setter chỉ ra lần ghi thứ hai cùng call stack; log cuối cùng không tự nói được lần ghi nào gây lỗi. Sửa bằng quy tắc ownership/state transition hoặc loại bỏ side effect, rồi thêm regression test.

## 11. Sai lầm phổ biến và giới hạn an toàn

1. **“Profiler không thấy hotspot nghĩa là không có bug.”** Sai: bug logic có thể thực thi rất nhanh.
2. **“Log đủ mọi dòng sẽ giải quyết.”** Không nhất thiết: logging dày làm tăng I/O/CPU, lộ dữ liệu nhạy cảm và có thể thay đổi timing. Log có mục tiêu và correlation thường tốt hơn.
3. **“Breakpoint cho biết lịch sử đầy đủ.”** Sai: một breakpoint chỉ cho snapshot; muốn biết ai đã sửa field cần dừng sớm/watchpoint hoặc ghi bằng chứng theo thời gian.
4. **“Dừng thread không làm thay đổi lỗi concurrency.”** Sai: pause thay đổi lịch chạy, timeout và lock ownership.
5. **“`RUNNABLE` trong thread dump nghĩa là chắc chắn ăn CPU.”** Sai: cần đối chiếu OS/JFR CPU sampling; trạng thái Java không phản ánh trực tiếp CPU tiêu thụ.
6. **“Evaluate Expression luôn read-only.”** Sai: getter, `toString()` hoặc method có thể làm mutation, I/O hoặc deadlock.
7. **“Đổi biến trong debugger là đã fix bug.”** Sai: sửa tạm thời trong runtime không thay code, không thay test và có thể làm dữ liệu giả.
8. **“Conditional breakpoint miễn phí vì ít hit.”** Sai: điều kiện vẫn có thể phải được đánh giá ở nhiều lần đi qua, ảnh hưởng hot path.
9. **“Debug production qua JDWP mở port cho tiện.”** Rất nguy hiểm: debugger có quyền thao tác JVM; không phơi cổng ra mạng không tin cậy.
10. **“Source đang mở chắc chắn là source đang chạy.”** Sai: container/jar, class loader, module, shaded artifact hoặc deployment version khác có thể khiến breakpoint/locals lệch.
11. **“Một request chậm = thread tiêu CPU.”** Sai: wall time có thể chờ I/O/lock/scheduler; dùng profiler/JFR để phân biệt.
12. **“Không thấy thread trong debugger nghĩa là chưa có task.”** Sai trong môi trường async/virtual thread; công cụ và policy liệt kê thread khác nhau.

## 12. Checklist trước và sau khi debug

**Trước khi attach:**

- [ ] Có **expected vs actual** và case tái hiện/sanitized input.
- [ ] Biết câu hỏi cần trả lời là **trạng thái/luồng điều khiển**, không chỉ tổng chi phí CPU/memory.
- [ ] Có đúng source/class/JDK và debug symbols cần thiết.
- [ ] Biết breakpoint sẽ dừng ở method nào, condition gì, ảnh hưởng thread nào.
- [ ] Môi trường được phép tạm dừng; không mở JDWP công khai; có kế hoạch đóng debug listener.
- [ ] Nếu nghi race/latency production, đã cân nhắc log/JFR/thread dump ít xâm nhập hơn.

**Sau khi debug:**

- [ ] Ghi đúng **state trước/sau** phép gán, selected stack frame và caller.
- [ ] Chứng minh một invariant hoặc giả thuyết cụ thể bị vi phạm; tránh suy diễn từ snapshot.
- [ ] Tạo regression test cho case biên, exception path hay concurrency scenario tương ứng.
- [ ] Chạy lại **không có breakpoint**; khi vấn đề hiệu năng, đo bằng profiler/JFR/load test.
- [ ] Ngắt debugger/đóng cổng, không lưu secret vào screenshot, log hoặc artifact.

### Câu hỏi tự kiểm tra

1. Khi nào thêm log đủ, khi nào debugger đáng dùng hơn profiler/JFR?
2. Trong ví dụ coupon, trước khi thực thi dòng gán `payableCents`, các giá trị `requestedDiscountCents`, `capped` và `subtotalCents` là bao nhiêu? Tại sao điều này chứng minh bug?
3. Vì sao cần conditional breakpoint trên một method được gọi rất nhiều lần?
4. Sự khác biệt giữa field modification watchpoint và mục Watches hiển thị expression trong IDE?
5. Vì sao Step Over trong request nhiều thread có thể làm timeout nhân tạo hoặc làm biến mất race?
6. Vì sao một `jdb where` không hoạt động nếu JVM chưa dừng ở frame/thread thích hợp?
7. Sau khi sửa code, tại sao chạy pass một phiên debugger chưa đủ kết luận sự cố đã được khắc phục?

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — jdb Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdb.html): breakpoints, stepping, `where`/`locals`, attach và hướng dẫn virtual threads.
- [Oracle Java SE 21 — JPDA Connection and Invocation](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html): `-agentlib:jdwp`, `suspend`, `address`, transport, giới hạn kết nối.
- [Oracle Java SE 21 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/introduction-client-issues.html): JDWP và công cụ chẩn đoán phù hợp theo loại vấn đề.
- [Oracle Java SE 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): thread dump và JFR commands khi nên thu bằng chứng thay vì pause.
- [Oracle Java SE 21 — jfr](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): xem và lọc JFR events phục vụ profiling trước khi bước vào debugger.
- [Oracle JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html): công cụ xem JFR về CPU, allocation, lock và I/O.
