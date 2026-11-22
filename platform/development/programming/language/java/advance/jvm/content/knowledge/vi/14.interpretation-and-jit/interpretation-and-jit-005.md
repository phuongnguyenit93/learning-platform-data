# Biên dịch phương thức và thay thế khi đang chạy vòng lặp (OSR) trong HotSpot JVM

## Mục tiêu

Một chương trình Java 17+ không nhất thiết thực thi mã bytecode bằng cùng một cơ chế trong suốt vòng đời. **HotSpot** có thể bắt đầu bằng **interpreter**, thu thập thông tin hành vi khi chạy rồi **JIT-compile** những phần mã đủ “nóng” thành machine code. Với phương thức thường được gọi đi gọi lại, JIT có thể tạo mã **bắt đầu từ method entry** để những lần gọi sau đi vào native code ngay. Nhưng một phương thức **chỉ được gọi một lần mà thực thi một vòng lặp rất dài** vẫn có thể tốn hàng triệu lần lặp trong interpreter. **On-Stack Replacement (OSR)** giải quyết chính tình huống đó: chuyển **lần gọi đang hoạt động** từ phiên bản interpreter hoặc compiled tier thấp hơn sang một phiên bản compiled có **điểm vào ở bên trong phương thức**, thường tại đầu vòng lặp (*loop header/backedge target*).

Sau bài này, bạn sẽ có thể:

- Phân biệt **normal method compilation** với **OSR compilation**, và biết vì sao một method có thể có **nhiều nmethods** hoặc mã ở nhiều compilation levels.
- Giải thích **method invocation counter**, **backedge counter**, **profiling**, **compile queue**, **C1**, **C2**, **tiered compilation** và **nmethod** theo ngữ cảnh HotSpot.
- Đọc ký hiệu **`%`**, **`@ bci`**, compilation level và **made not entrant** trong `-XX:+PrintCompilation` mà không coi log là kết quả chạy bất biến.
- Hiểu chuyển trạng thái giữa **interpreter frame / compiled frame**, các **local variables**, operand stack, stack maps và safepoints, cùng giới hạn của việc mô phỏng ở Java source.
- Phân biệt OSR với **deoptimization**, **inlining**, **uncommon trap**, **OSR bci** và **GC safepoint**.
- Viết Java 17+ chạy được để nghiên cứu sự khác nhau giữa một vòng lặp dài và một phương thức được gọi nhiều lần.
- Biết sử dụng `javap`, `PrintCompilation`, `LogCompilation`, `jcmd`, JFR và các tham số như `-Xint`, `-XX:TieredStopAtLevel`, không “ép” OSR bằng một ngưỡng cố định thiếu cơ sở.
- Đánh giá warmup, code-cache pressure, deoptimization và benchmark pitfalls bằng dữ liệu thực tế.

## 1. Interpreter, JIT và nmethod

Java source được `javac` chuyển thành **class file bytecode**. Khi JVM thực thi:
1. Class loading/linking/initialization xử lý class theo quy tắc.
2. Method bắt đầu thực thi trong **interpreter** hoặc vào mã compiled đã sẵn có, tùy trạng thái HotSpot.
3. Runtime quan sát những phương thức hoặc loops thực thi nhiều, tích lũy counters và profile data.
4. **Compilation policy** quyết định có gửi một yêu cầu biên dịch tới **compile queue**.
5. Compiler thread sử dụng thông tin kiểu, call sites, branches, loop behavior và runtime assumptions thích hợp để tạo machine code.
6. Nếu mã compiled được cài đặt thành công, JVM có thể điều hướng những lần thực thi thích hợp vào nó.

**`nmethod`** là khái niệm nội bộ HotSpot cho một khối mã native đã biên dịch gắn với method và metadata như entry points, scope/deoptimization information và runtime dependencies. Nó không phải một method Java source mới.

Sơ đồ:

~~~text
.java -> javac -> .class / bytecode
                         |
                         v
                    HotSpot JVM
                         |
            +------------+-------------+
            |                          |
       INTERPRETER                COMPILED CODE
       bytecode dispatch        C1/C2 nmethod(s)
            |                          ^
            +-- profiling/counters ----+
                         |
                  compile queue
                         |
                  compiler threads
~~~

**Phân biệt:** Bytecode trong .class file không bị “ghi đè” bởi assembly khi JIT hoạt động. JVM quản lý native compiled code riêng, vẫn cần metadata bytecode cho verification, stack traces, deoptimization và những mục đích khác.

## 2. Normal method compilation là gì?

Giả sử:

~~~java
static int plusOne(int value) {
    return value + 1;
}
~~~

Đây là **đoạn method minh họa**, phải đặt trong một class để biên dịch. Với một vòng ngoài gọi `plusOne` liên tục, HotSpot có thể thấy invocation count cao và biên dịch mã có **entry ở đầu method**.

~~~text
Caller gọi plusOne() nhiều lần:
  call #1    -> interpreter
  call #2    -> interpreter
  ...
  HotSpot nhận diện hot method
            |
            v
      compile plusOne
      entry BCI chuẩn / method entry
            |
  call #K+1 -> compiled nmethod
  call #K+2 -> compiled nmethod
~~~

**Đây là trình tự minh họa**. Số K không có giá trị cố định và JIT có thể inline lời gọi, sử dụng tier khác hoặc bị giới hạn bởi flags/code cache. Không có guarantee một method “được gọi đúng 10.000 lần là biên dịch”.

### Điểm vào method entry

Normal compilation tạo mã có thể dùng khi **bắt đầu một lần gọi mới**. Caller chuyển tới compiled entry theo runtime dispatch/inlining decisions. Nếu một lần gọi đã vào interpreter và còn chạy bên trong vòng lặp trong thời gian dài, chỉ có compiled method-entry code **không đủ** để tự chuyển lần gọi đó sang native code mà không có cơ chế thích hợp.

### JIT không bắt buộc biên dịch mọi method

Method hiếm khi gọi, quá lớn, không đủ profile, có restrictions hoặc chỉ thực hiện rất ít công việc có thể luôn chạy interpreted. Một số method được inline vào caller, khiến chúng không xuất hiện như một compiled method riêng theo kỳ vọng. Compilation có thể bị trì hoãn khi compiler threads bận hoặc code cache căng.

## 3. Vấn đề đặc biệt của một vòng lặp chạy rất lâu

Xét:

~~~java
static long oneLongCall(int limit) {
    long sum = 0L;
    for (int i = 0; i < limit; i++) {
        sum += (i & 7);
    }
    return sum;
}
~~~

Đây là snippet minh họa. Phương thức có thể chỉ được gọi **một lần**, nhưng `limit` có thể đạt hàng chục triệu hoặc hàng trăm triệu iterations. Invocation count không cao, song **loop backedges** (các nhánh quay về đầu vòng lặp) xảy ra liên tục.

Nếu chỉ dựa trên phương thức được gọi lặp lại, HotSpot có thể không biên dịch kịp một method chỉ được gọi một lần. Nếu biên dịch “thông thường”, mã mới ở method entry sẽ chỉ được dùng khi gọi lại từ đầu, **không giúp phần lớn vòng lặp đang thực thi**.

**OSR cho phép chuyển chính lần gọi hiện tại sang compiled code ở một BCI bên trong method.** Đây là điểm khác biệt cốt lõi với normal compilation.

### Ví dụ thời gian

~~~text
T0   Method bắt đầu trong interpreter
T1   Loop chạy 100.000 lần; backedge counter tăng
T2   JVM quyết định gửi OSR compilation request
T3   Compile thread tạo OSR nmethod (có thể chạy song song)
T4   Method vẫn đang thực thi trong interpreter
T5   Khi có điểm chuyển thích hợp và OSR code đã sẵn:
       interpreter frame/state
                |
                v
       OSR entry trong compiled nmethod
       tiếp tục từ loop BCI hiện tại
T6   Loop và method hoàn tất; caller nhận return value
~~~

Các mốc T chỉ là **mô tả logic**. JVM không bảo đảm request được gửi sau đúng 100.000 iterations, compilation luôn kết thúc trước khi loop xong, hay OSR luôn được chọn.

## 4. BCI và tại sao output có dấu `@`

**BCI (bytecode index)** là vị trí offset tính theo byte trong vùng bytecode của một method. Lệnh ở offset đó là một phần của **một method**, không phải line number trong Java source.

Khi HotSpot OSR-compile một method, compilation task có **OSR entry BCI** xác định nơi compiled code có thể nhận một **activation đang chạy**. Trong các loop thông dụng, nó thường tương ứng một điểm tại loop header hoặc vị trí backedge target.

Ví dụ output minh họa của `-XX:+PrintCompilation`:

~~~text
    75   33 %     3       OsrDemo::longLoop @ 4 (37 bytes)
   111   55       4       OsrDemo::longLoop (37 bytes)
   145   33 %     3       OsrDemo::longLoop @ 4 (37 bytes)   made not entrant
~~~

**Các số millis, compile ID, level, BCI và số byte ở đây hoàn toàn minh họa**, không phải log đúng cho một chương trình cụ thể. Trong định dạng HotSpot thông thường:
- Con số đầu thường là **thời gian từ JVM startup** (ms), tùy format.
- Một số tiếp theo là **compilation ID**.
- **`%`** đánh dấu **OSR compilation**.
- Số như **3** hoặc **4** có thể là compilation level trong tiered policy.
- `OsrDemo::longLoop` là tên class/method.
- **`@ 4`** là **OSR BCI**, không phải số iteration.
- `(37 bytes)` nói đến độ dài **bytecode method**, không phải bytes của machine code.
- **`made not entrant`** là trạng thái một nmethod không còn được lựa chọn cho những entry mới, thường do một bản compiled khác hoặc invalidation.

Không suy ra từ một dòng `%` rằng OSR **thực sự đã được sử dụng** cho mọi invocation đang chạy: dòng này chủ yếu xác nhận **có compilation request/compilation tương ứng**. Mã có thể sẵn nhưng loop đã kết thúc trước thời điểm chuyển hoặc tier khác được chọn.

### OSR BCI khác Java line

Một lệnh Java `for` có thể sinh nhiều bytecodes: khởi tạo index, so sánh limit, nhảy có điều kiện, tải locals, toán tử arithmetic, tăng index, `goto` về đầu. Vì vậy BCI=4 không có nghĩa “dòng 4”. Dùng `javap -c -p` để xem offsets bytecode và lệnh branch.

## 5. Backedge counter và compilation policy

Một vòng lặp bytecode thường có nhánh ngược về offset nhỏ hơn. JVM có thể sử dụng **backedge counts** và profile information để xác định vòng lặp “nóng” dù method invocation count thấp.

Hai tín hiệu khác nhau:

| Tín hiệu | Thường tăng khi nào | Trường hợp có giá trị |
| --- | --- | --- |
| **Invocation count** | Gọi một method nhiều lần | Method ngắn, thường được gọi |
| **Backedge count** | Nhánh quay lại vùng code trước đó nhiều lần | Một hoặc vài lần gọi có loop rất dài |
| **Branch/profile data** | Runtime quan sát tỷ lệ nhánh, call receivers, types... | C1 profiling và tối ưu theo dữ liệu thực |
| **Hotness/rate heuristics** | JVM kết hợp counts, tốc độ, compile-queue load... | Lựa tier và thời điểm compile |

**Cẩn thận:** đây không phải hai đồng hồ đơn giản độc lập với thresholds cố định. HotSpot tiered policy thay đổi theo version, compiler queue, profile maturity và số active methods. Các flags như `CompileThreshold` hoặc `OnStackReplacePercentage` có ý nghĩa phụ thuộc chế độ tiered/non-tiered; dùng một công thức threshold cũ của Java 8 để dự đoán Java 17+ là sai.

### Compilation có thể chạy bất đồng bộ

Khi interpreter phát hiện hot backedge, nó có thể gửi compile task rồi **tiếp tục chạy loop trong interpreter** trong lúc compiler thread làm việc. Nếu loop kết thúc trước khi OSR code sẵn, chương trình không được chuyển sang OSR ở lần đó. Cũng có các chế độ **blocking compilation** hoặc các tình huống policy khác; đừng mặc định mọi JIT compilation luôn background và không bao giờ chặn application thread.

### OSR có nhất thiết xảy ra tại mỗi backedge?

Không. Runtime phải có một checkpoint/safepoint hoặc cơ chế kiểm tra thích hợp để nhận biết code đã sẵn, bảo đảm frame transition hợp lệ. Nó không phải phép “đổi địa chỉ lệnh CPU ngay giữa một expression Java” tùy tiện. JIT cần chuyển trạng thái tại nơi có đủ metadata để khôi phục semantics.

## 6. Tiered compilation: interpreter, C1 và C2

HotSpot server JVM thông dụng triển khai **tiered compilation** để cân bằng thời gian warmup và hiệu quả machine code. Một mô hình các levels thường gặp:

| Level | Hình thức | Vai trò |
| --- | --- | --- |
| **0** | Interpreter | Bắt đầu thực thi và/hoặc thu profile theo policy |
| **1** | C1 compiled, tối ưu không bổ sung profiling nhiều như tiers sau | Method có đường đi được lựa chọn phù hợp |
| **2** | C1 compiled với profiling giới hạn | Thu thập một phần dữ liệu hỗ trợ tier tiếp |
| **3** | C1 compiled với profiling đầy đủ hơn | Phổ biến trên đường tiến lên optimized tier |
| **4** | C2 compiled, tối ưu mạnh theo profile | Tối ưu steady-state throughput/latency khi thích hợp |

**Đây là diễn giải HotSpot C1/C2 truyền thống**, không phải cấu trúc bắt buộc của JVMS hoặc mọi build/platform. Một số JVM có JVMCI compiler, tuning options và tier policy khác.

Trong thực tế:
- Một method có thể chạy ở level 0 rồi sang C1 level 3, sau đó C2 level 4.
- Một method rất đơn giản có thể vào level 1.
- JVM có thể skip level, dừng ở C1, không compile hoặc recompile khi assumptions thay đổi.
- Một method có thể có **normal nmethod** và **OSR nmethod**; cả hai có thể khác levels.
- Những dấu level trong PrintCompilation chỉ phản ánh compilation task/nmethod, không phải “mọi bytecode lập tức ở level đó” trên mọi invocation.

### C1 và C2 không phải hai phiên bản Java source

C1/C2 là **compilers nội bộ VM**. Mục tiêu của JVM vẫn là thực thi đúng Java semantics. C2 có thể inline methods, eliminate allocations, hoist invariant computations hoặc vectorize loops nếu điều kiện phù hợp. Những tối ưu có thể phải được vô hiệu hóa khi runtime observations không còn đúng.

### C1 OSR và C2 OSR có thể tồn tại đồng thời

Một vòng lặp rất dài có thể:
1. Bắt đầu interpreted.
2. Được OSR-compile ở C1 để sớm nhận native execution.
3. Tiếp tục được quan sát và gửi C2 OSR compilation khi đủ profile.
4. Chuyển tới mã tier cao hơn theo đường VM cho phép.

Không suy ra việc chuyển luôn trực tiếp từ C1 OSR frame sang C2 OSR frame. Có thể cần deoptimization/re-entry/intermediate state; chi tiết tùy HotSpot version và compiler/runtime policy.

## 7. So sánh method-entry compilation và OSR

| Khía cạnh | Normal compilation | OSR compilation |
| --- | --- | --- |
| **Mục tiêu** | Tăng tốc **những lần gọi mới** bắt đầu tại method entry | Tăng tốc **lần thực thi hiện tại** đã ở trong vòng lặp |
| **Tín hiệu điển hình** | Method invocations/hotness | Loop backedges/hotness |
| **Entry point** | Standard method entry | Một BCI bên trong method (thường loop header) |
| **Compile task** | Standard nmethod | OSR nmethod với osr_bci |
| **PrintCompilation** | Thường không có `%` và không có `@ bci` | Có `%`, thường có `@ bci` |
| **Activation được tối ưu** | Chủ yếu future invocations | Có thể current activation |
| **State chuyển đổi** | Caller truyền arguments tới normal entry | Runtime chuyển interpreter/compiled state của activation hiện hành |
| **Độ tối ưu** | Có thể dùng thông tin ở method entry | Có những ràng buộc vì phải chấp nhận state ở OSR entry |
| **Có thể có thêm bản compiled khác?** | Có, khi tiering/recompilation | Có, nhiều osr_bci hoặc levels |
| **Bảo đảm sẽ xảy ra?** | Không | Không |

**OSR không phải một Java syntax feature.** Source code `for`/`while` giống hệt; OSR là quyết định và cơ chế nội bộ JVM nhằm tối ưu execution mà không thay đổi kết quả chương trình.

## 8. Trạng thái đang chạy cần được chuyển như thế nào?

Một interpreted frame đang ở trong loop có trạng thái không thể “bỏ đi”:
- **Local variables**: tham số, loop index, counters, object references, temporaries.
- **Operand stack** tại bytecode state liên quan.
- **Java monitors/locks** nếu method hoặc block được synchronized và OSR entry phải bảo toàn trạng thái khóa.
- **Exception handlers** và thông tin control flow.
- **GC map/reference metadata** cần cho collector biết vị trí object references.
- Thông tin liên quan stack traces, inlining/deoptimization nếu chuyển tiếp từ compiled frames.

Ví dụ một loop:

~~~java
static long countEven(int n) {
    long sum = 0L;
    int accepted = 0;
    for (int i = 0; i < n; i++) {
        if ((i & 1) == 0) {
            sum += (i % 10);
            accepted++;
        }
    }
    return sum + accepted;
}
~~~

Đây là snippet minh họa. Nếu chuyển sang OSR ở giữa loop, compiled code cần tiếp tục với **giá trị hiện tại** của `i`, `sum`, `accepted` và `n`. Không được reset chúng về 0. Cũng không được lặp lại những side effects đã xảy ra trước điểm chuyển.

### Sơ đồ frame state

~~~text
Interpreter activation (đang tại loop backedge):
  locals: [n=8,000,000, i=3,450,123,
           sum=..., accepted=...]
  operand stack: trạng thái tại OSR checkpoint
  monitor state, metadata, method/BCI

                |
                | OSR runtime state transfer
                v

Compiled OSR entry @ loop BCI:
  reconstruct/register-map relevant locals,
  operand values, references and monitor state
  -> continue from current loop iteration
  -> preserve Java semantics
~~~

Các số giả lập. Trạng thái vật lý có thể nằm trong interpreter frame, compiled frame, register/spill slots hoặc buffers; HotSpot cần metadata để tái lập trạng thái đúng. **Không khẳng định OSR luôn “copy toàn bộ stack”** hay giữ mọi local variable trong RAM theo layout bất biến.

### OSR có thể bị từ chối

Các conditions có thể khiến một OSR request không được thực hiện: method/bci không phù hợp để compile tại level hiện tại, compiler busy, code cache constraints, insufficient profile, JVM flags và policy. Một method có loop lớn vẫn có thể chạy hoàn toàn trong interpreter.

## 9. Ví dụ đầy đủ Java 17+: một loop dài và nhiều lần gọi nhỏ

Tạo file **`OsrVsMethodDemo.java`**:

~~~java
public class OsrVsMethodDemo {
    static volatile long observable;

    static long longLoop(int limit) {
        long sum = 0L;
        for (int i = 0; i < limit; i++) {
            sum += (i & 7);
        }
        return sum;
    }

    static int plusOne(int value) {
        return value + 1;
    }

    public static void main(String[] args) {
        long loopResult = longLoop(16_000_000);
        observable = loopResult;

        long callSum = 0L;
        for (int i = 0; i < 100_000; i++) {
            callSum += plusOne(i);
        }
        observable = callSum;

        System.out.println("loopSum=" + loopResult);
        System.out.println("callSum=" + callSum);
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac --release 17 OsrVsMethodDemo.java
java OsrVsMethodDemo
~~~

**Stdout nghiệp vụ chính xác:**

~~~text
loopSum=56000000
callSum=5000050000
~~~

Giải thích toán học:
- Dãy `i & 7` lặp lại 0,1,…,7, tổng mỗi nhóm 8 là **28**. 16.000.000 / 8 = 2.000.000 nhóm, tổng = **56.000.000**.
- `plusOne(i)` trả 1,2,…,100.000; tổng = `100000×100001/2 = 5.000.050.000`, chứa trong `long`.
- `observable` là volatile field giữ kết quả có ý nghĩa quan sát, nhưng không cam kết mọi intermediate allocation/instruction phải tồn tại trong machine code.

**Ý tưởng so sánh:** `longLoop` là **một method invocation** với rất nhiều backedges, trong khi `plusOne` có rất nhiều calls. Tuy nhiên compiler có thể inline `plusOne` vào `main`, làm số compilation tasks khác mô hình đơn giản. Chương trình không hứa “chắc chắn có đúng một OSR compilation”.

### Quan sát PrintCompilation

Trên HotSpot hỗ trợ flags:

~~~bash
java -XX:+PrintCompilation OsrVsMethodDemo
~~~

**Cảnh báo:** đầu ra console sẽ có **các dòng compilation events không cố định** trước, giữa hoặc sau hai dòng nghiệp vụ trên; JVM còn biên dịch JDK library methods. Vì vậy **không đưa ra stdout nguyên chương trình cố định** cho lệnh này.

Tìm những dòng chứa:
- `OsrVsMethodDemo::longLoop` và dấu `%`.
- `OsrVsMethodDemo::main` và có thể dấu `%` vì vòng gọi bên trong main cũng dài.
- `OsrVsMethodDemo::plusOne` nếu compiler biên dịch riêng; nếu được inline, không nhất thiết xuất hiện thành một normal compilation.
- `@ <number>` sau method để nhận biết OSR entry BCI.
- Level 3/4 để xem đường tiered compilation trong run ấy.

### Chạy ở chế độ interpreted

~~~bash
java -Xint OsrVsMethodDemo
~~~

Lệnh này dùng interpreter-only mode trên HotSpot; chương trình vẫn in hai dòng **cùng giá trị nghiệp vụ**. Thời gian thực thi có thể khác rất lớn nhưng **không hứa một hệ số tăng tốc cố định**. Một số thành phần VM/library có xử lý đặc biệt, song với code Java của ví dụ này `-Xint` là đối chứng để tránh JIT optimization.

### Chạy chỉ C1 để quan sát thay đổi tier

~~~bash
java -XX:TieredStopAtLevel=1 -XX:+PrintCompilation OsrVsMethodDemo
~~~

`TieredStopAtLevel=1` giới hạn compiled tiers theo HotSpot version có hỗ trợ. Quan sát compilation entries và so với tiering mặc định, nhưng không đọc đây là “buộc OSR level 1 chắc chắn xảy ra”. Việc thay tier có thể đổi warmup, compiler overhead và cả loại compilation request.

## 10. Ví dụ thứ hai: OSR phải bảo toàn locals, branch và loop exit

Tạo file **`OsrStateDemo.java`**:

~~~java
public class OsrStateDemo {
    static long countEven(int n) {
        long sum = 0L;
        int accepted = 0;

        for (int i = 0; i < n; i++) {
            if ((i & 1) == 0) {
                sum += i % 10;
                accepted++;
            }
        }
        return sum + accepted;
    }

    public static void main(String[] args) {
        System.out.println("result=" + countEven(8_000_000));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 OsrStateDemo.java
java OsrStateDemo
~~~

**Stdout chính xác:**

~~~text
result=20000000
~~~

Giải thích:
- Trong 8 triệu số `0..7,999,999` có đúng 4 triệu số chẵn, nên `accepted=4.000.000`.
- Đối với `i` chẵn, `i % 10` lặp 0,2,4,6,8; tổng 20 cho 5 phần tử và average 4. Qua 4 triệu phần tử, `sum=16.000.000`.
- Kết quả = `sum+accepted=20.000.000`.

Nếu JVM quyết định OSR vào giữa loop, values của `sum`, `accepted` và `i` phải tiếp tục đúng để chương trình luôn in kết quả này. Nếu compiled code mất trạng thái hoặc lặp lại một nhánh đã chạy, kết quả sẽ sai — nhưng một JVM đúng không được làm vậy.

### Dùng javap kiểm tra BCI

~~~bash
javap -c -p OsrStateDemo
~~~

Ở đoạn `countEven`, bạn sẽ thấy những lệnh như `iload`, `iand`, `irem`, `iinc` và các nhánh `if...`/`goto` với bytecode offsets. Vị trí `@ bci` trong PrintCompilation cần đối chiếu với **offset bytecode thực tế** của file .class, không với số dòng Java.

## 11. Mô tả OSR chính xác hơn: compile request không đồng nghĩa chuyển thành công

Quá trình có thể được chia thành các mốc độc lập:

~~~text
(A) Hot backedge observed
           |
(B) Compilation policy quyết định request?
       /                  \
     NO                    YES
     |                      |
  interpret         Enqueue OSR compile task
                           |
                    Compiler thread xử lý
                           |
                    Code generated/installed?
                     /               \
                   NO                 YES
                   |                   |
          vẫn interpret        OSR nmethod sẵn
                                       |
                                Activation còn đang
                                ở checkpoint phù hợp?
                                  /           \
                                NO             YES
                                |               |
                             Không chuyển    Runtime có thể
                             lần này         OSR transition
~~~

Phân biệt rõ:
- **OSR task requested**: policy đã yêu cầu compile.
- **OSR compiled**: native code đã tạo/cài đặt thành công.
- **OSR activated**: current execution đã chuyển sang OSR entry.
- **Compiled at higher tier**: code được nâng chất lượng/tier, chưa chắc current activation dùng phiên bản đó.

`-XX:+PrintCompilation` chủ yếu hữu ích để **quan sát compilation events**, không thay thế bộ profiling runtime chứng minh activation path ở mức cực chi tiết. Với nghiên cứu sâu có thể dùng JITWatch + HotSpot compilation logs hoặc các công cụ profiling/diagnostic được hỗ trợ.

## 12. Deoptimization: hướng chuyển ngược lại OSR

JIT có thể tối ưu dựa trên **assumptions** từ type/branch profiles. Ví dụ, compiler thấy một call site thường chỉ có receiver thuộc một class, rồi inline method tương ứng. Nếu sau đó loại receiver khác xuất hiện, một guard có thể fail.

**Deoptimization** chuyển execution từ compiled code về một trạng thái tương thích với interpreter (hoặc đường thực thi phù hợp khác), phục hồi các JVM frames/locals/operand values để tiếp tục đúng Java semantics.

So sánh:

| Hiện tượng | Chiều chuyển | Vì sao xảy ra |
| --- | --- | --- |
| **OSR** | Interpreter / lower tier → compiled OSR entry | Loop nóng, muốn tăng tốc **activation hiện tại** |
| **Deoptimization** | Optimized compiled frame → deoptimized/interpreted state | Assumption không còn đúng, uncommon trap, dependency invalidation hoặc lý do runtime khác |
| **Normal compilation** | Tạo compiled code cho method entry mới | Hot method/hot calls |
| **Recompilation** | Có code compiled tier/optimization mới | Profile trưởng thành, invalidation hoặc tiering |
| **Inlining** | Đặt thân callee vào mã compiled caller | Giảm dispatch/cho phép optimize xuyên method boundary |

**Không đồng nhất OSR với deoptimization.** Hai cơ chế đều yêu cầu metadata để diễn dịch/chuyển trạng thái frames, nhưng mục đích và hướng chuyển khác nhau.

### Uncommon trap và loop exit

Một JIT compiler có thể quan sát một vòng lặp cực dài mà exit condition hầu như chưa xảy ra trong profile. Nó có thể tối ưu luồng “thường gặp” và dùng **uncommon trap** cho nhánh hiếm. Khi loop cuối cùng kết thúc, nhánh exit có thể kích hoạt deoptimization. Đây là một khả năng HotSpot, **không phải chuyện mọi OSR loop đều deopt ở vòng cuối**.

### Ví dụ thay đổi profile theo loại receiver

Tạo tệp **`ProfileShiftDemo.java`**:

~~~java
public class ProfileShiftDemo {
    static int read(Number value) {
        return value.intValue();
    }

    public static void main(String[] args) {
        long total = 0L;

        for (int i = 0; i < 50_000; i++) {
            total += read(Integer.valueOf(1));
        }

        total += read(Double.valueOf(2.5));

        System.out.println("total=" + total);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ProfileShiftDemo.java
java ProfileShiftDemo
~~~

**Stdout chính xác:**

~~~text
total=50002
~~~

Phần lớn calls đi qua Integer, rồi một lần qua Double. JVM **có thể** tối ưu dựa trên profile loại receiver và deopt khi call site gặp Double, nhưng **không bảo đảm** vì compiler có thể không compile, có thể đã thấy polymorphic profile hoặc chọn generic dispatch. Kết quả nghiệp vụ phải đúng dù không có deoptimization nào xảy ra.

## 13. Compilation logs: đọc dấu `%` và mức độ tin cậy

### Flag `PrintCompilation`

~~~bash
java -XX:+PrintCompilation OsrStateDemo
~~~

Nó in các compile events của **cả ứng dụng lẫn nhiều library methods**, có thể làm lẫn stdout. Khi tìm dòng `OsrStateDemo::countEven`, một OSR compilation thường trông dạng:

~~~text
   120   67 %     3       OsrStateDemo::countEven @ 4 (49 bytes)
   160   88 %     4       OsrStateDemo::countEven @ 4 (49 bytes)
   166   67 %     3       OsrStateDemo::countEven @ 4 (49 bytes)   made not entrant
~~~

**Đây là log minh họa, không phải output được dự đoán chính xác**. Số bytecodes, BCI, IDs và order phải lấy từ run thật. HotSpot output còn có attributes như `s` (synchronized), `!` (exception handlers), `b` (blocking), `n` (native), hoặc trạng thái khác tùy release; không diễn giải các ký hiệu chỉ dựa vào một ví dụ mà không xem bản JDK.

### Ý nghĩa của `made not entrant` và `made zombie`

- **Made not entrant:** compiled nmethod không còn được JVM chọn cho **những lần entry mới**, nhưng các active frames có thể tiếp tục sử dụng code đó hoặc cần chuyển/cleanup thích hợp.
- **Made zombie:** nmethod không còn active ở trạng thái thích hợp và có thể chờ reclaimed code-cache storage theo cơ chế CodeCache/sweeper.

**Không đồng nhất “made not entrant” với Java object bị GC thu gom.** Đây là lifecycle của **compiled machine code** trong code cache, không phải lifecycle của một heap object ứng dụng.

### JIT compilation output không cố định theo code

Thời điểm code compiled chịu ảnh hưởng từ:
- JDK build và HotSpot implementation;
- compile thresholds và profiling heuristics;
- CPU speed/core counts, compile queue contention;
- JVM startup mode, tiering flags và code cache;
- loop trip count, type profiles và inlining;
- interpreter performance, JIT warmup và background compilation.

Vì vậy giáo trình phải tách:
1. **Stdout nghiệp vụ** của các ví dụ — có thể dự đoán chính xác.
2. **JVM diagnostic output** — không thể hứa cùng compile IDs, mức tier hoặc số OSR tasks qua mọi máy.

## 14. Compilation log chi tiết với `LogCompilation`

Một số nghiên cứu JIT cần log dạng XML để phân tích compilation tasks, inlining, traps và mã OSR. Trên JDK 17 HotSpot có hỗ trợ:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -XX:LogFile=jit-log.xml OsrStateDemo
~~~

Các options `LogCompilation`/`LogFile` là **diagnostic**, không nhất thiết khả dụng/hoạt động giống nhau trên các vendor JVM. Trong XML logs có thể thấy thuộc tính tương tự:

~~~xml
<task compile_id='67' method='OsrStateDemo countEven (I)J'
      compile_kind='osr' osr_bci='4' level='3'>
</task>
~~~

Đây là **XML minh họa về kiểu metadata**, không phải fragment schema đầy đủ hay output bắt buộc. Cần dùng file log thực và JDK tools/JITWatch phù hợp để phân tích.

Các từ khóa có ích:
- `compile_kind='osr'` / `osr_bci`: xác định task OSR.
- `compile_id` và `level`: biết identity/tier của compilation.
- `task_done`: biết task đã hoàn tất với trạng thái nào.
- Inlining decisions/failed optimizations: tìm vì sao một đoạn không tối ưu như dự kiến.
- Traps và invalidations: kiểm tra deoptimization/recompilation.

**Cẩn thận:** nội dung XML, tag details và log availability là HotSpot-specific và có thể thay đổi; không coi nó là Java SE public contract.

## 15. Thử nghiệm các chế độ JIT một cách có kiểm soát

| Lệnh/flag | Mục đích học tập | Giới hạn |
| --- | --- | --- |
| `java -Xint Demo` | Chủ yếu chạy Java code interpreted | Không đại diện performance của HotSpot ở production tiered mode |
| `java -XX:+PrintCompilation Demo` | Liệt kê JIT compilation events | Nhiều library methods và timing không cố định |
| `java -XX:TieredStopAtLevel=1 ...` | Giới hạn JIT tối đa tới C1 level 1 trên bản hỗ trợ | Không buộc OSR một method cụ thể |
| `java -XX:-TieredCompilation ...` | So behavior khi tắt tiered compilation | Thay đổi compilation policy và thresholds mạnh, không phải chỉ “tắt C1” |
| `java -Xcomp ...` | Yêu cầu compile mạnh mẽ hơn khi thực thi | Thay đổi startup, blocking, profile quality, có thể giảm performance |
| `java -XX:CompileThresholdScaling=...` | Chỉnh thresholds heuristic | Không phải công tắc OSR đơn giản, không nên dùng để tạo số liệu benchmark |
| `java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation ...` | Ghi log compilation chi tiết | Diagnostic overhead và XML format không bất biến |
| `javap -c -p Demo` | Xem bytecode và offsets | Không hiển thị machine code JIT hay chứng minh OSR activated |

### Vì sao `-Xcomp` không phải “chạy JIT giống production nhưng nhanh hơn”?

`-Xcomp` khuyến khích biên dịch mạnh thay vì interpreter-warmup profile thông thường; JVM có thể biên dịch **trước khi có profile tốt**, tăng startup/compile overhead và đôi khi làm ứng dụng chậm hơn. Không dùng nó làm bằng chứng “JIT luôn tốt hơn interpreter” hoặc để đo lựa chọn tier production.

### Chỉ C1 không giống chỉ C2

Tiered compilation có chi phí và chiến lược thu profile. Khi đặt `TieredStopAtLevel=1`, JVM có thể tiết kiệm compile CPU, cải thiện startup cho một số workload nhưng bỏ lỡ tối ưu C2. **Không suy ra** mọi chương trình chậm hơn; phải so startup time, steady-state throughput và tail latency.

### Có nên cố ép OSR bằng threshold?

Thường **không**. Các thresholds khác nhau theo tiered policy và JVM version. Với mục đích học, chọn loop đủ dài, bật compilation logging rồi **quan sát**. Nếu cần nghiên cứu chuyên sâu, ghi tất cả flags và exact JDK build, dùng compiler directives/JITWatch/JFR; không xây tutorial dựa vào một “magic number” mà không kiểm chứng.

## 16. Method invocation counter và backedge counter không phải hai public API

Không có Java SE API tiêu chuẩn cho:

~~~java
// Ví dụ giả định KHÔNG PHẢI Java API:
int count = JVM.getBackedgeCounter(MyClass.class, "method");
~~~

Đoạn trên là **pseudo-code bị comment**, không biên dịch thành công nếu bỏ dấu comment vì API không tồn tại. HotSpot có counters/profiling metadata nội bộ; giá trị, dạng lưu trữ và lifetime tùy VM build/tier.

**Đừng dùng Reflection** để đoán vị trí backedge counters trong method/class. Tương tự, `Thread.getStackTrace()` không tiết lộ trạng thái compiled vs interpreted của từng frame theo contract phổ thông.

Nếu cần quan sát HotSpot internals:
- JVM logging/profiling phù hợp.
- JFR compilation events nếu recording/event set có hỗ trợ.
- `jcmd` diagnostics.
- JITWatch hoặc tooling nghiên cứu trên đúng JDK.
- OpenJDK HotSpot source cho bản JDK tương ứng.

Một số diagnostic VM flags chỉ có trong debug build; không dùng chúng như hướng dẫn chạy phổ quát trên production binary.

## 17. OSR và safepoint: liên quan nhưng không đồng nghĩa

JVM cần những điểm thích hợp để:
- kiểm tra requests từ runtime;
- đồng bộ GC/safepoints;
- chuyển interpreter/compiled execution khi code mới sẵn;
- deopt hoặc giải quyết một số runtime conditions.

Backedges thường là vị trí tự nhiên cho một số checks. Tuy nhiên:

- **OSR entry** là điểm chuyển trạng thái vào compiled nmethod, được xác định bởi BCI.
- **GC safepoint** là trạng thái/phối hợp VM giúp runtime thực hiện các hoạt động cần biết object references và thread states.
- **Deoptimization point** là nơi VM có đủ thông tin để tái tạo state tương thích khi rời optimized code.
- Những khái niệm này liên quan ở mức metadata/checkpoint nhưng **không đồng nghĩa một OSR transition = một GC pause**.

Một loop có thể không có object allocations vẫn đủ “nóng” để được JIT chú ý. OSR không chỉ được kích hoạt do garbage collector, và GC không phải điều kiện bắt buộc để compile một method.

## 18. OSR trong synchronized method và exception handling

Một method đang chạy có thể có:
- `synchronized` method monitor;
- `synchronized(lock)` block;
- `try/catch/finally`;
- local references cần GC chính xác;
- object state bị mutate qua mỗi loop iteration.

OSR phải giữ đúng Java semantics liên quan locks, exception flow và locals.

Ví dụ (snippet minh họa):

~~~java
static synchronized long count(int n) {
    long total = 0;
    for (int i = 0; i < n; i++) {
        total += i;
    }
    return total;
}
~~~

Nếu HotSpot OSR-compile loop, quyền sở hữu monitor **không thể tự biến mất** trong quá trình chuyển. Khi method kết thúc hoặc ném exception, Java synchronization semantics vẫn phải đúng.

OSR không phải “bỏ qua phần code trước vòng lặp”. Nó tiếp tục từ điểm tương thích với **state được tạo bởi phần code đã thực hiện**, và phải bảo toàn những side effects đó.

## 19. OSR và inlining của call sites

Khi compiler biên dịch `caller()` và có thể inline `callee()`, HotSpot có thể tạo **compiled code chứa callee logic ngay bên trong caller**. Vì thế:
- Log của `callee()` không nhất thiết có normal nmethod riêng.
- A method có thể nằm trong một compiled caller frame, và stack traces vẫn cần hiển thị Java-level frames đúng.
- Counters/hotness có thể gắn với method đang inline, không chỉ owner top-level.
- OSR policy có thể xét loop/inlinee phù hợp để chọn compile requests; chi tiết thuộc compiler policy.

**Ví dụ quan trọng:** `plusOne` trong chương trình ở mục 9 quá nhỏ nên rất dễ inline. Nếu không thấy `plusOne` trong PrintCompilation, **không kết luận nó “không được tối ưu”**. Nó có thể đã được inline và tối ưu mạnh vào loop bên ngoài.

### Muốn ép một method không inline?

Có thể dùng compiler directives hoặc `-XX:CompileCommand=dontinline,...` trên HotSpot được hỗ trợ cho một nghiên cứu riêng, nhưng điều đó **thay đổi profile và code shape**. Không đưa flags ép inline/no-inline làm kết luận hiệu năng production; hãy đo cả baseline và experimental run.

## 20. Warmup: tại sao một benchmark rất ngắn dễ đánh giá sai JIT

HotSpot có thời gian warmup do:
- class loading/verification/initialization;
- interpreter profiling;
- C1 compilation và OSR;
- C2 compilation/recompilation;
- dynamic linking, caches và data structure initialization;
- JIT recompilation/deoptimization và code-cache management.

Một single-shot microbenchmark:

~~~java
long before = System.nanoTime();
// Run a loop and print elapsed...
~~~

là **snippet minh họa**, chưa phải benchmark đủ tốt. Vòng đầu có thể chịu compilation overhead hoặc OSR transition giữa chừng, vòng sau đi thẳng vào optimized nmethod. Đo một lần rồi kết luận “loop được OSR nên nhanh gấp 10 lần” là không chắc chắn.

### JMH và đo đúng

**OpenJDK JMH** là dự án dành cho microbenchmark có warmup iterations, measurement iterations, forks, controlled state và blackholes. Khi đánh giá:
1. Viết workload tái hiện logic ứng dụng.
2. Bảo đảm kết quả được tiêu thụ, tránh dead-code elimination.
3. Tách class loading/setup khỏi timed region khi mục tiêu là steady-state.
4. Dùng nhiều forks/runs và so distributions.
5. Ghi JDK build, flags, CPU quota và compiler modes.
6. Đo performance lẫn compilation events nếu câu hỏi là warmup/OSR.
7. Với live services, đối chiếu request latency và throughput thật, không chỉ microbenchmark.

**Một loop rất dài trong một method** có thể tận dụng OSR, nhưng benchmark còn chịu branch prediction, vectorization, CPU caches, scheduling và profile type. Không đoán rằng OSR là nguồn duy nhất của speedup.

## 21. Code cache và vòng đời compiled code

Native JIT output phải được lưu ở **code cache**. HotSpot có thể dùng **segmented code cache**, chia các vùng lưu non-method/profiled/non-profiled code theo configuration.

Khi nhiều methods và OSR variants được compile:
- code cache memory tăng;
- compiler phải duy trì metadata và nmethods;
- code sweeper có thể làm sạch code đã không còn active;
- có thể xuất hiện states như `made not entrant`, `made zombie`;
- khi code cache đầy hoặc bị giới hạn, JIT compilation có thể bị hạn chế/tạm ngưng, làm performance khác.

**Không nhầm code cache với Java heap.** Code cache lưu machine code và runtime metadata, không phải nơi `new Person()` tạo Java object.

Lệnh quan sát trên HotSpot có hỗ trợ (thay PID thật):

~~~bash
jcmd PID Compiler.codecache
jcmd PID Compiler.codelist
jcmd PID Compiler.queue
~~~

Những diagnostic commands có availability/output thay đổi theo JDK; kiểm tra bằng `jcmd PID help` trên exact runtime. Một số lệnh có thể cần quyền attach và có tác động đến hệ thống; không chạy tùy tiện với production khi chưa có quyền.

### Khi code cache hết

Một cảnh báo về code cache có thể giải thích tại sao compilation dừng, chứ không có nghĩa OSR algorithm sai. Kiểm tra code cache usage, `ReservedCodeCacheSize` và compiled-method churn trước khi đổi heap `-Xmx` — vì **-Xmx điều khiển Java heap, không trực tiếp là giới hạn code cache**.

## 22. Dùng JFR để quan sát compilation

**Java Flight Recorder (JFR)** có các event types liên quan compilation/code cache/tiered execution tùy JDK/event configuration. Có thể dùng JFR để phân tích:
- compilation activity và compiler threads;
- durations của compilation;
- code cache statistics;
- CPU profile trong warmup;
- deoptimization/code-cache events khi được bật/hỗ trợ;
- latency hoặc throughput bên ngoài đối chiếu với giai đoạn warmup.

Ví dụ chạy chương trình trong một recording:

~~~bash
java -XX:StartFlightRecording=filename=jit-study.jfr,dumponexit=true,settings=profile OsrVsMethodDemo
~~~

Đầu ra binary `jit-study.jfr` không có nội dung cố định. Đọc bằng JDK Mission Control hoặc `jfr print` trên JDK phù hợp. Trên workload quá ngắn, recording có thể không có đủ events để diễn giải. JFR sampling không chứng minh mọi OSR activation đã xảy ra, đặc biệt khi event set không ghi transition cụ thể.

Muốn lấy dữ liệu trong process đang chạy:

~~~bash
jcmd PID JFR.start name=JitStudy settings=profile duration=60s filename=jit-study.jfr
jcmd PID JFR.check
~~~

`PID` là placeholder cho process ID, thay bằng số thực. Diagnostic data có thể chứa thông tin ứng dụng; bảo vệ files.

## 23. Quy trình chẩn đoán “vòng lặp nóng mà không nhanh”

Nếu loop chạy chậm dù tưởng rằng OSR/JIT sẽ tối ưu:

1. **Kiểm tra đúng JVM**: `java -version`, vendor/HotSpot build, architecture, flags.
2. **Xác định chế độ**: đang có `-Xint`, `-XX:-TieredCompilation`, `TieredStopAtLevel`, hoặc flags giới hạn compilation không?
3. **Xem PrintCompilation**: có method/OSR compile task không, level nào, có `made not entrant`?
4. **Đối chiếu javap**: `@ bci` ứng với loop nào?
5. **Kiểm tra compile queue**: compiler threads có bận, code cache gần đầy hay method bị loại khỏi compile không?
6. **Profiling actual hot path**: method có được inline vào caller? Có virtual calls/megapolymorphic receivers, bounds checks hoặc memory stalls không?
7. **Xem deoptimization/traps**: assumptions thay đổi khiến optimized code phải invalidated nhiều lần?
8. **Kiểm tra CPU/GC**: loop có bị tranh CPU, blocked, memory bandwidth hay GC pauses không?
9. **Đo sau warmup**: sử dụng JMH/service metrics, không kết luận từ một lần chạy.
10. **Tối ưu thuật toán/dữ liệu**: nếu algorithm O(n²) hoặc cache locality tệ, JIT/OSR không thay thế được thiết kế thuật toán.

### Dấu hiệu thường gặp và cách suy luận

| Hiện tượng | Điều cần kiểm tra | Không nên vội kết luận |
| --- | --- | --- |
| Không thấy ký hiệu `%` | OSR task không được in/không xảy ra, JIT flags, threshold/policy, loop ngắn, inlining | “JVM không hỗ trợ OSR” |
| Có `%` nhưng method vẫn chậm | OSR code có được activated, workload, memory/GC/CPU, optimizer | “OSR tự động làm nhanh” |
| Có nhiều levels 3 và 4 | Tiered C1→C2 progression, recompile | “Vòng lặp chạy nhiều bản đồng thời trên cùng thread” |
| Có `made not entrant` | New tier/invalidation/nmethod lifecycle | “Ứng dụng bị lỗi/GC thu object” |
| Có deoptimization | Guard/profile change, uncommon traps | “Kết quả Java bị sai” |
| `-Xint` chậm hơn | Interpreter overhead và JIT optimizations thiếu | “OSR alone tạo mọi speedup” |
| Method nhỏ không xuất hiện riêng | Inlining, compile policy | “Method không được tối ưu” |
| Compilations giảm khi service chạy lâu | Warmup hoàn tất hoặc code cache pressure | “JIT bị tắt” |
| Một số runs không có OSR | Timing/queue/loop finishes before compilation | “PrintCompilation bị lỗi” |

## 24. Những ngộ nhận cần tránh

| Ngộ nhận | Sự thật |
| --- | --- |
| “Normal method compilation làm lần gọi đang chạy tự chuyển sang code mới.” | Standard entry code chủ yếu cho invocations mới; OSR giải quyết current activation ở loop. |
| “OSR là compiler khác C1/C2.” | OSR là **kiểu compilation/entry**; C1/C2 có thể sinh OSR nmethod. |
| “OSR chỉ cần thay pointer trong biến Java.” | VM phải chuyển frame state/locals/operand/monitors đúng semantics. |
| “OSR bci là iteration number.” | BCI là bytecode offset trong method. |
| “Dấu % trong PrintCompilation là tỷ lệ CPU.” | Dấu `%` là OSR compilation marker. |
| “Cứ loop 10.000 lần là OSR.” | Policy/threshold/timing khác theo JVM và workload. |
| “Method có normal nmethod thì không thể có OSR nmethod.” | Có thể có cả hai variants. |
| “C1 OSR và C2 OSR luôn được dùng theo thứ tự tất định.” | Tier policy, queue, compilation latency, deopt và profiling quyết định. |
| “OSR là GC pause.” | OSR liên quan JIT execution transition, không phải tên một GC event. |
| “OSR là deoptimization.” | Hướng/mục đích khác; OSR đi vào optimized code, deopt rời optimized code khi cần. |
| “`-Xcomp` phản ánh production throughput.” | Nó thay compile timing/profile, có thể giảm performance. |
| “`-Xint` cũng có OSR native code.” | Interpreter-only mode không dùng JIT cho Java methods theo cách thông thường. |
| “Log `made zombie` báo object Java chết.” | Đây là nmethod/code-cache lifecycle. |
| “`javap` hiển thị C2 assembly.” | `javap -c` xem bytecode; JIT machine code cần công cụ/flags khác. |
| “Không thấy compiled callee tức JIT bỏ qua.” | Callee có thể được inline vào caller. |
| “Có OSR task nghĩa OSR chắc chắn activated.” | Compilation và transition là hai thời điểm/điều kiện riêng. |
| “OSR luôn tăng tốc mọi loop.” | Biên dịch/transition có overhead và loop có thể kết thúc sớm. |

## 25. Câu hỏi tự kiểm tra

**1. Method được gọi một lần nhưng chạy 50 triệu iterations có thể được JIT chú ý không?**

Có. Backedge counts/profiling có thể kích hoạt một **OSR compilation**, dù invocation count thấp.

**2. Vì sao normal compiled method entry chưa đủ để tăng tốc lần gọi đang chạy?**

Vì compiled entry phục vụ bắt đầu method; current invocation đã ở sâu trong loop. OSR cung cấp điểm vào ở BCI phù hợp cùng state transfer.

**3. Dấu `%` trong PrintCompilation là gì?**

OSR compilation marker, không phải phần trăm tải CPU.

**4. `@ 8` trong dòng OSR log thường chỉ gì?**

Một **OSR BCI** trong bytecode method, không phải Java line 8 hay vòng lặp thứ 8.

**5. C1/C2 liên quan OSR thế nào?**

C1/C2 là compilers; cả hai có thể tạo OSR variants ở compilation levels thích hợp.

**6. Tại sao phải chuyển giá trị biến `sum` vào OSR code?**

Để không mất phần kết quả đã cộng trong interpreter và để method tiếp tục từ trạng thái hiện tại.

**7. OSR có phải Java syntax feature không?**

Không. Source `for` hoặc `while` không đổi; OSR do VM quản lý.

**8. Dùng `-Xint` sẽ thấy JIT method compilation bình thường không?**

Không trong execution Java interpreted-only thường gặp; lệnh này chủ yếu dùng làm đối chứng interpreter.

**9. Vì sao một method nhỏ được gọi nhiều không xuất hiện thành compilation entry riêng?**

Có thể được inline vào caller hoặc không đủ điều kiện biên dịch riêng.

**10. OSR task đã compile là bảo đảm current loop chuyển sang compiled code?**

Không. Loop có thể đã kết thúc hoặc policy/transition không chọn mã OSR ấy.

**11. Tại sao nmethod có thể `made not entrant`?**

Khi mã không còn được dùng cho new entries, ví dụ do new tier hoặc dependency invalidation. Đây không phải Java heap object GC.

**12. OSR và deoptimization khác gì?**

OSR nhằm đi **vào compiled code** giữa activation; deoptimization phục hồi execution state khi phải **rời optimized code**.

**13. Nếu loop có synchronized monitor, OSR được phép bỏ qua lock không?**

Không. Monitor ownership và Java synchronization semantics phải được bảo toàn.

**14. Vì sao dùng JMH thay vì tính time của một vòng for lần đầu?**

Vì warmup, OSR/JIT compilation latency, JIT dead-code elimination, cache và scheduling làm số đo đơn lẻ thiếu tin cậy.

**15. Phải nhìn metric nào khi compiler queue quá tải?**

Compile events/queue, compiler CPU/time, tiering progression, code cache và workload actual CPU/latency, cùng trạng thái JVM flags.

**16. Tại sao PrintCompilation số thời gian/method ID không thể là expected stdout?**

Vì compilation được quyết định runtime, chịu JDK build, thread scheduling, CPU, profile và flags khác nhau.

## 26. Bản đồ ghi nhớ

~~~text
                 JAVA BYTECODE METHOD
                          |
                      INTERPRETER
                          |
             +------------+-----------+
             |                        |
        Many method calls      One long-running loop
             |                        |
       invocation counters        backedge counters
             |                        |
             v                        v
     NORMAL COMPILATION         OSR COMPILATION
     method entry code          osr_bci inside method
             |                        |
       future invocations      current active invocation
             |                        |
             +-------------+----------+
                           |
                       TIERED JIT
               0 interpreter -> C1 -> C2
                           |
               nmethod(s) in CODE CACHE
                           |
             +-------------+--------------+
             |                            |
       OPTIMIZED EXECUTION           DEOPTIMIZATION
                                    (if assumptions fail)
             |                            |
             +----------------------------+
                           |
                 JAVA SEMANTICS UNCHANGED
                           |
                  DIAGNOSTICS / MEASUREMENT
           javap -c; PrintCompilation (% / @bci)
           LogCompilation; JFR; jcmd; JITWatch
                           |
                  JMH / service metrics
~~~

**Kết luận:** **Normal method compilation** tăng tốc các lần gọi mới từ method entry; **OSR** cho phép một lần gọi đã ở giữa **vòng lặp nóng** đi vào compiled native code tại một **BCI** thích hợp mà vẫn giữ đúng locals/operand/monitor state. OSR là một cơ chế **JIT execution transition**, không phải một compiler riêng hay một hoạt động GC. Hãy nhận diện nó qua `%` và `@ bci` trong HotSpot logs, rồi đo hiệu năng thực tế với warmup và diagnostics thay vì hứa thresholds hoặc speedups cố định.

## Tài liệu tham khảo chuẩn

- [Oracle JDK 17 — The java Command: PrintCompilation, TieredCompilation, LogCompilation, CompileThresholdScaling, CompileCommand](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [JVMS Java SE 17 — §2 Runtime Data Areas, JVM Frames and Operand Stacks](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html).
- [JVMS Java SE 17 — §6 Java Virtual Machine Instruction Set, BCI/branches](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html).
- [OpenJDK HotSpot — compilationPolicy.hpp, tiered compilation levels, backedge events](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.hpp).
- [OpenJDK HotSpot — compileBroker.cpp, OSR compilation tasks and statistics](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compileBroker.cpp).
- [OpenJDK HotSpot — compiler_globals.hpp, OnStackReplacePercentage and diagnostics](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compiler_globals.hpp).
- [OpenJDK HotSpot — C2 parse1.cpp, OSR BCI and type flow](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/parse1.cpp).
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://openjdk.org/projects/code-tools/jmh/).
- [Oracle JDK 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
- [OpenJDK JITWatch project](https://github.com/AdoptOpenJDK/jitwatch).
