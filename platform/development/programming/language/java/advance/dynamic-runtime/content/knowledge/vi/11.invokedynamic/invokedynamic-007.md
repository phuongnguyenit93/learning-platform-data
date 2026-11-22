# 11.7 Bootstrap có thể được thực thi cạnh tranh: thiết kế tác dụng phụ an toàn

`invokedynamic` đưa việc chọn đích gọi một phương thức từ giai đoạn biên dịch sang **giai đoạn liên kết tại runtime**. Khi một lệnh `invokedynamic` chưa được liên kết, JVM gọi *bootstrap method* (BSM) để tạo một `CallSite` có đích gọi phù hợp. Điểm khó và rất dễ bị bỏ qua: nếu nhiều thread cùng đến một điểm gọi chưa liên kết, JVM **được phép gọi cùng bootstrap cạnh tranh**. JVM sẽ chọn **một kết quả liên kết** làm `CallSite` của lệnh đó và bỏ qua các kết quả còn lại, nhưng **không hoàn tác tác dụng phụ** do những lần bootstrap không được chọn đã thực hiện.

Vì vậy, **“một lệnh chỉ được liên kết thành công một lần” không có nghĩa “bootstrap chỉ chạy một lần”**. Nếu BSM ghi registry, đăng ký listener, tạo resource bên ngoài, tăng bộ đếm nghiệp vụ, khởi chạy thread hoặc phát sự kiện, việc dựa vào giả định “chỉ chạy một lần” có thể gây duplicate, data race, rò rỉ tài nguyên hoặc trạng thái không nhất quán.

Bài này tập trung trực tiếp vào **tính cạnh tranh của bootstrap**, sự khác nhau giữa **kết quả được JVM chọn** và **tác dụng phụ đã xảy ra**, cùng các thiết kế an toàn: bootstrap thuần tính toán, cấu hình bất biến, cache thread-safe, *idempotency key*, giao dịch bền vững, kiểm soát vòng đời và kiểm thử. Ví dụ dùng **Java 17+**, có một chương trình gọi BSM trực tiếp từ nhiều thread để kiểm tra hành vi cạnh tranh **có kiểm soát**, và một chương trình chứa `invokedynamic` thật do `javac` sinh ra để quan sát class file.

## 1. Lệnh invokedynamic được liên kết theo mô hình nào?

Ở bytecode, `invokedynamic` không tham chiếu một phương thức đích cố định như `invokestatic`. Class file có mục `CONSTANT_InvokeDynamic` và `BootstrapMethods` mô tả:

- **Bootstrap method handle**: code được JVM gọi để quyết định đích.
- **Tên gọi** (name) và **kiểu lời gọi** (`MethodType`) mà điểm gọi yêu cầu.
- **Các static bootstrap arguments** tùy chọn: metadata được nhúng trong class file để cấu hình bootstrap.
- **Vị trí instruction**: mỗi lệnh `invokedynamic` là một điểm liên kết cụ thể; không đồng nhất với mọi điểm gọi dùng cùng tên hoặc cùng bootstrap.

Một BSM thường có chữ ký:

```java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String name,
        MethodType type,
        /* các static arguments nếu có */)
        throws Throwable
```

Đây là **chữ ký minh họa**, không phải chương trình độc lập. Ba tham số đầu thường mang ý nghĩa:

| Đối số | Mục đích |
| --- | --- |
| `caller` | Quyền và lớp chứa lệnh được liên kết; `caller.lookupClass()` thường giúp nhận diện caller |
| `name` | Tên tượng trưng tại điểm gọi, ví dụ `apply` hoặc `dispatch` |
| `type` | Chữ ký runtime yêu cầu, ví dụ `(String)String` |
| Static args | ID logic, handle đích, cờ cấu hình, chính sách hoặc dữ liệu bất biến do class file cung cấp |

BSM **phải trả một `CallSite` không null**, và `callSite.type()` phải khớp kiểu mà lệnh `invokedynamic` yêu cầu. Một `ConstantCallSite` giữ target cố định; `MutableCallSite` hoặc `VolatileCallSite` có thể thay target sau khi liên kết, với các quy tắc visibility khác nhau. Sự lựa chọn loại CallSite là một vấn đề **khác** với việc BSM có thể chạy cạnh tranh lúc liên kết.

Đường đi khái quát:

```text
invokedynamic chưa được liên kết
          |
          v
JVM resolve BSM, name, MethodType, static args
          |
          v
gọi BSM trong thread đang cố thực thi instruction
          |
          v
BSM tạo CallSite có type phù hợp
          |
          v
JVM chọn / lắp đặt kết quả liên kết của instruction
          |
          v
các lần thực thi sau gọi target qua CallSite đã liên kết
```

Một instruction được liên kết thành công thì không tự liên kết lại chỉ vì caller tiếp tục chạy. Nếu dùng `MutableCallSite` để đổi target sau đó, **đổi target không phải chạy lại BSM**. Cũng không nên gọi `bootstrap(...)` thủ công và nghĩ đó là thao tác yêu cầu JVM liên kết lại instruction.

## 2. Điều gì xảy ra khi nhiều thread cùng chạm điểm gọi lần đầu?

Java Virtual Machine Specification 17, `5.4.3.6, cho phép các thread đang cùng resolve một symbolic reference thực thi bootstrap **đồng thời**. Nếu nhiều lần BSM xảy ra, JVM chọn kết quả của **một invocation** và cài đặt nó để các thread nhìn thấy; các BSM khác có thể tiếp tục chạy đến hết nhưng kết quả của chúng bị bỏ qua.

Hãy hình dung:

```text
                  instruction X: invokedynamic chưa liên kết
Thread T1:   BSM(X) ---------> CallSite A ----                                               Thread T2:     BSM(X) -------> CallSite B -------+--> JVM chọn một kết quả
                                               /       cài đặt cho X
Thread T3:   BSM(X) ---------> CallSite C ----/         các kết quả khác bỏ
                                                             |
                       side effects của A, B, C vẫn có thể xảy ra
```

Đây là **một interleaving có thể xảy ra**, không phải số lần gọi BSM do mọi JVM bắt buộc phải thực hiện. JVM cũng có thể tuần tự hóa việc liên kết và chỉ gọi bootstrap một lần. **Không kiểm tra correctness bằng việc “trên máy mình chỉ thấy một lần”**.

### 2.1. JVM bảo đảm điều gì — và không bảo đảm điều gì?

| Điều có thể dựa vào | Điều không được suy ra |
| --- | --- |
| Một instruction `invokedynamic` đang được liên kết thành công sẽ có một `CallSite` được JVM lựa chọn | BSM chỉ được thực thi đúng một lần trên toàn bộ quá trình |
| Các thread sử dụng kết quả liên kết được JVM công bố | Các đoạn side effect của mọi BSM đã được serialize hoặc rollback |
| Kết quả BSM hợp lệ phải có type khớp instruction | Nếu một BSM thất bại thì JVM sẽ “thử lại tới khi có kết quả tốt” cho các lần gọi tương lai |
| Các lần thực thi sau của instruction đã liên kết dùng cùng linkage | Những instruction khác dùng cùng tên/type/bootstrap sẽ tự động dùng chung một CallSite |
| BSM cạnh tranh có thể tạo các `CallSite` khác nhau | JVM luôn chọn CallSite được tạo đầu tiên, nhanh nhất, hay theo ID thread |

**“Một CallSite được chọn” không đồng nghĩa “một object CallSite được tạo”.** Nếu cả T1, T2 và T3 đều thực hiện `new ConstantCallSite(...)`, chúng có thể tạo ba object; một object được chọn để liên kết X, còn object khác có thể trở thành rác để GC nếu không có tham chiếu nào giữ lại. Nhưng nếu mỗi BSM còn mở socket, đăng ký callback vào registry toàn cục hoặc ghi cơ sở dữ liệu, những tác dụng phụ này **không tự biến mất** khi object CallSite bị bỏ.

### 2.2. Tại sao JVM không đơn giản bảo đảm BSM chạy đúng một lần?

Mô hình liên kết động cho phép nhiều thread cố thực thi cùng một instruction chưa resolve. Đặc tả ưu tiên quy tắc **chọn một kết quả liên kết quan sát được**, chứ không trao cho BSM một khóa “execute-once” tự động để bao trọn mọi thay đổi ứng dụng. BSM là code Java có thể truy cập trạng thái chung và có exception, do đó người viết BSM phải áp dụng đồng bộ, bất biến và chính sách side effect như với code đa luồng thông thường.

**Liên hệ với `CONSTANT_Dynamic`:** dynamic constant cũng sử dụng bootstrap khi resolve; đặc tả `5.4.3.6` mô tả khả năng cạnh tranh tương tự. Nhưng trọng tâm bài này là **CallSite của `invokedynamic`**, không nhầm một dynamic constant với một instruction gọi phương thức.

## 3. Phân biệt ba “số đếm” dễ bị nhập làm một

Đối với một instruction X, nên tách:

1. **Bootstrap attempts**: bao nhiêu lần BSM được thực sự gọi trong quá trình các thread cạnh tranh.
2. **Logical initialization/registration**: bao nhiêu lần hệ thống thực hiện một hành động nghiệp vụ vốn chỉ nên xảy ra một lần theo một khóa logic.
3. **JVM-installed linkage**: kết quả CallSite được JVM chọn cho instruction X.

Ví dụ T1 và T2 cùng chạy BSM, mỗi lần tăng `attempts`. Một thiết kế an toàn có thể để `attempts==2` (đúng cho metric *attempts*) nhưng chỉ có **một** lần thiết lập `registry` cho cùng khóa. JVM vẫn chỉ chọn một kết quả cho X. Không nên tính toán số CallSite đã được lắp đặt bằng cách đếm số lần BSM thực thi — BSM **không có callback chuẩn báo “tôi là người thắng”**.

Nếu muốn metric “call site đã liên kết”, cần đặt tên và quy ước đo lường thành thật; không gán nhãn đó cho một counter tăng trong BSM. Ngay cả nếu thấy `attempts==1` trên một JVM cụ thể, điều đó không tạo hợp đồng áp dụng được cho các nền tảng khác.

## 4. Tác dụng phụ nào nguy hiểm nhất?

| Tác dụng phụ trong BSM | Nguy cơ khi BSM chạy cạnh tranh | Thiết kế khuyến nghị |
| --- | --- | --- |
| `counter++` trên field thường | Lost update, race và đo sai loại metric | `AtomicInteger`/`LongAdder` nếu cần đếm attempts |
| `new Thread(...).start()` | Khởi chạy nhiều worker mà chỉ một CallSite được dùng | Chuyển lifecycle ra bên ngoài BSM hoặc đăng ký bằng một gate idempotent |
| Gửi email, ghi hóa đơn, debit tài khoản | Hành động ngoại vi bị lặp, hậu quả không hoàn tác được | Không thực hiện trong BSM; nếu bắt buộc cần idempotency key + transaction của hệ ngoài |
| Đăng ký listener/route vào global map | Duplicate callback, rò rỉ listener hoặc ghi đè trạng thái | `ConcurrentHashMap.computeIfAbsent` với giá trị bất biến, hoặc registry quản lý vòng đời |
| Mở connection/file/socket | Loser vẫn có thể giữ resource, tăng chi phí và rò rỉ | Tránh mở trong BSM; dùng resource pool có ownership và close policy rõ |
| Tạo cache key theo `name + type` | Nhiều site khác nhau dùng chung nhầm trạng thái | Key bao gồm caller identity và static site ID nếu contract yêu cầu |
| Phát event `BOOTSTRAP_DONE` | Event có thể phát nhiều lần dù chỉ một linkage được chọn | Phân biệt event attempt và event nghiệp vụ once-only |
| Cập nhật `MutableCallSite` chung | Những site không liên quan vô tình cùng đổi hành vi | Tạo CallSite riêng nếu muốn target độc lập; xử lý visibility riêng |

Mẫu **không an toàn** sau có race:

```java
// Minh họa anti-pattern: không phải chương trình độc lập.
static boolean registered;
static void onBootstrap() {
    if (!registered) {
        registerListener();    // Có thể thực hiện hai lần.
        registered = true;
    }
}
```

Hai thread có thể cùng thấy `registered == false` và cùng gọi `registerListener()`. Biến `volatile boolean registered` giúp visibility nhưng **không biến check-then-act thành atomic**: vẫn có thể cùng vượt qua điều kiện trước khi thread nào ghi `true`.

Một `AtomicBoolean.compareAndSet(false,true)` có thể lập gate at-most-once cho một hành động nội bộ đơn giản, nhưng cần cân nhắc failure: nếu thread đặt gate thành true rồi hành động thất bại, các thread khác tưởng đã khởi tạo xong. Với tài nguyên phức tạp, dùng state machine `NEW → INITIALIZING → READY/FAILED`, future chung hoặc bộ quản lý vòng đời. Với tác dụng phụ ngoại vi, CAS trong process **không bảo đảm exactly-once** nếu process crash/restart.

## 5. Nguyên tắc thiết kế: BSM càng thuần tính toán càng tốt

Thiết kế dễ review nhất:

```text
BSM nhận Lookup + name + MethodType + static args
  -> kiểm tra type/metadata
  -> chọn MethodHandle đã có quyền
  -> kết hợp/adapter handle (asType, insertArguments, filter...)
  -> tạo ConstantCallSite
  -> trả CallSite
```

Các bước này chủ yếu chỉ tạo metadata/handle local và kết quả độc lập với thứ tự các thread chạy. Nếu BSM có thể chạy hai lần và mỗi lần trả một CallSite **tương đương về ngữ nghĩa**, việc JVM chọn một trong các kết quả không gây khác biệt nghiệp vụ.

Một BSM phù hợp nên:

- **Deterministic theo dữ kiện hợp đồng**: cùng metadata và cấu hình hợp lệ cho target tương đương; nếu hệ thống cố ý dynamic thì trạng thái được đọc phải có quy tắc nhất quán.
- **Không có side effect không idempotent**: không charge tiền, phát email hay đăng ký listener nhiều lần.
- **Không publish object chưa khởi tạo xong**: cấu trúc được chia sẻ phải immutable hoặc được công bố an toàn.
- **Phản ứng lỗi có kiểm soát**: xác minh handle có thể gọi với `MethodType` yêu cầu trước khi trả CallSite, tránh thay đổi hệ ngoài rồi mới ném exception do type mismatch.
- **Không giữ khóa rộng khi resolve phức tạp**: BSM có thể trigger class loading, tìm handle, initialization hoặc bootstrap lồng nhau. Global lock làm tăng nguy cơ contention/reentrancy/deadlock.

Điều này **không** có nghĩa BSM phải tuyệt đối pure; nhiều runtime linker có nhu cầu cache/registry thực tế. Nhưng tác dụng phụ phải có hợp đồng idempotency, thread safety, lỗi và lifetime được xác định riêng.

### 5.1. Local allocation khác global side effect

Tạo riêng một `ConstantCallSite`, một `MethodHandle` hoặc một object cấu hình bất biến cho mỗi BSM attempt thường an toàn: chỉ những object thật sự còn được tham chiếu mới tồn tại lâu. Ngược lại, đăng ký mọi object vào static list/map làm loser thành object tồn tại dài hạn và có thể rò memory.

Không đặt logic `registry.add(site)` trong BSM rồi dự đoán rằng “JVM sẽ tự unregister loser”. JVM không cung cấp cơ chế rollback như thế.

## 6. Chương trình Java 17+: ép hai lời gọi bootstrap cạnh tranh

Ví dụ sau chứng minh cách viết BSM **chịu được việc bị gọi nhiều lần**. Nó thực hiện một thử nghiệm *manual bootstrap invocation*: hai Java thread **gọi trực tiếp** cùng method `bootstrap` với cùng metadata. Điều này kiểm tra thread safety/idempotency của code BSM nhưng **không phải** mã bytecode `invokedynamic` để JVM chọn winner. Ta không giả lập thuật toán lắp CallSite của JVM.

Tạo tệp **`IndyBootstrapSafetyDemo.java`**:

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class IndyBootstrapSafetyDemo {
    record SiteKey(Class<?> caller, String logicalId) {}

    private static final ConcurrentHashMap<SiteKey, String> CONFIG = new ConcurrentHashMap<>();
    private static final AtomicInteger attempts = new AtomicInteger();
    private static final AtomicInteger registrations = new AtomicInteger();

    public static String dispatch(String configuration, String input) {
        return configuration + ":" + input;
    }

    public static CallSite bootstrap(MethodHandles.Lookup caller, String name,
                                     MethodType type, String logicalId)
            throws ReflectiveOperationException {
        attempts.incrementAndGet(); // Count attempts, not installed JVM call sites.
        SiteKey key = new SiteKey(caller.lookupClass(), logicalId);
        String configuration = CONFIG.computeIfAbsent(key, ignored -> {
            registrations.incrementAndGet();
            return "policy-" + logicalId;
        });

        MethodHandle raw = MethodHandles.lookup().findStatic(
                IndyBootstrapSafetyDemo.class, "dispatch",
                MethodType.methodType(String.class, String.class, String.class));
        MethodHandle bound = MethodHandles.insertArguments(raw, 0, configuration);
        return new ConstantCallSite(bound.asType(type));
    }

    public static void main(String[] args) throws Throwable {
        MethodType type = MethodType.methodType(String.class, String.class);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        try {
            Callable<CallSite> job = () -> {
                ready.countDown();
                start.await();
                return bootstrap(MethodHandles.lookup(), "run", type, "demo-site");
            };
            Future<CallSite> firstTask = workers.submit(job);
            Future<CallSite> secondTask = workers.submit(job);
            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("workers did not start");
            }
            start.countDown();
            CallSite first = firstTask.get();
            CallSite second = secondTask.get();

            System.out.println("attempts=" + attempts.get());
            System.out.println("registrations=" + registrations.get());
            System.out.println("cachedKeys=" + CONFIG.size());
            System.out.println("siteTypesEqual=" + first.type().equals(second.type()));
            System.out.println("first=" + (String) first.dynamicInvoker().invokeExact("A"));
            System.out.println("second=" + (String) second.dynamicInvoker().invokeExact("B"));
        } finally {
            start.countDown();
            workers.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 IndyBootstrapSafetyDemo.java
java IndyBootstrapSafetyDemo
```

`stdout` của chương trình khi hai task hoàn tất đúng:

```text
attempts=2
registrations=1
cachedKeys=1
siteTypesEqual=true
first=policy-demo-site:A
second=policy-demo-site:B
```

**Diễn giải:**

1. `CountDownLatch` giúp hai task đã sẵn sàng trước khi mở cổng `start`. Thí nghiệm luôn **gọi bootstrap hai lần**; không phụ thuộc JVM có tự tạo tranh chấp liên kết `invokedynamic` hay không.
2. `attempts` đếm hai lời gọi thực tế bằng `AtomicInteger`. Nó **không** phải số CallSite được JVM lắp đặt.
3. `CONFIG.computeIfAbsent(key, ...)` bảo đảm việc thiết lập giá trị cache cho **cùng key** được phối hợp nguyên tử. Trong thử nghiệm không có lỗi/loại bỏ entry này, lambda khởi tạo chạy một lần nên `registrations=1` và `cachedKeys=1`.
4. Mỗi lời gọi `bootstrap` tạo **một `ConstantCallSite` riêng**; cả hai có `type` hợp lệ và target tương đương. Trong liên kết `invokedynamic` thật, JVM có thể chọn một trong các kết quả tương đương, nhưng chương trình minh họa này **không tự tuyên bố ai thắng**.
5. `MethodHandles.insertArguments(raw,0,configuration)` gắn sẵn cấu hình vào target `dispatch(String,String)` để target cuối có type `(String)String`; `bound.asType(type)` tạo kiểu target phù hợp với BSM request. Không phải mọi type đều thích nghi hợp lệ, nên production BSM vẫn phải validate `type`.

**Giới hạn quan trọng của `computeIfAbsent`:** ở `ConcurrentHashMap`, mapping function được phối hợp trên cùng key khi tính giá trị chưa có; nó cần ngắn gọn, tránh thay đổi đệ quy cùng map. Nếu mapping function ném exception, entry có thể không được lưu và lời gọi sau có thể thử lại. Do đó, **không đặt giao dịch ngoại vi không thể lặp lại vào mapping function rồi gọi đó là exactly-once**. `registrations` trong code chỉ đo một khởi tạo in-memory thành công của ví dụ, không đại diện cho giao dịch bền vững qua crash.

## 7. Quan sát invokedynamic thật do javac tạo ra

Java source thông thường không có từ khóa để viết trực tiếp bytecode `invokedynamic` tùy ý. Trong chương trình Java 17, một biểu thức lambda hoặc method reference thường được `javac` biên dịch thành `invokedynamic` do `LambdaMetafactory` liên kết. Đây là cách xem **instruction thực** mà không cần ASM, thư viện ngoài hay bytecode generator.

Tạo tệp **`IndyLambdaInspection.java`**:

```java
import java.util.function.IntUnaryOperator;

public class IndyLambdaInspection {
    static IntUnaryOperator add(int delta) {
        return value -> value + delta;
    }

    public static void main(String[] args) {
        IntUnaryOperator op = add(3);
        System.out.println("lambda=" + op.applyAsInt(4));
    }
}
```

```bash
javac --release 17 IndyLambdaInspection.java
java IndyLambdaInspection
javap -c -p IndyLambdaInspection
javap -v -p IndyLambdaInspection
```

Phần **`stdout` của lệnh `java`**:

```text
lambda=7
```

Khi xem kết quả `javap`, tìm hai dấu hiệu (định dạng chỉ số constant pool có thể thay đổi giữa các compiler/build):

- Trong bytecode của `add(int)` có một instruction `invokedynamic` tương ứng với việc tạo `IntUnaryOperator` cho lambda.
- Trong `BootstrapMethods` có một method handle tới `java.lang.invoke.LambdaMetafactory.metafactory`. Class có thể còn có một `invokedynamic` khác để nối chuỗi trong `println`; đó là cơ chế bootstrap khác, không phải một lần chạy BSM bổ sung cho cùng instruction lambda.

**Quan trọng:** `javap` chứng minh class file chứa `invokedynamic` và tham chiếu bootstrap, **không** đếm số lần BSM được JVM thực thi lúc runtime. Cũng không thể dùng một run không có tranh chấp để kết luận JVM sẽ luôn gọi BSM một lần. Mục đích hai chương trình tách biệt rõ: ví dụ `IndyBootstrapSafetyDemo` kiểm thử concurrency/idempotency của **BSM do bạn viết**; ví dụ `IndyLambdaInspection` minh họa **instruction invokedynamic thật**.

## 8. Chọn khóa idempotency cho đúng phạm vi

Đây là một trong những quyết định khó nhất ở BSM có side effect. Không được giả định khóa `(name,type)` là duy nhất cho một instruction:

- Hai instruction khác nhau trong **cùng class** có thể cùng `name` và `MethodType`, thậm chí cùng bootstrap method handle.
- Hai lớp khác nhau có thể cùng tên và descriptor tại các call site. Trong ứng dụng plugin, các class có cùng binary name nhưng được tải bằng **class loader khác nhau** là các `Class<?>` khác nhau.
- Các static arguments có thể mang cấu hình khác nhau. Nếu key không bao gồm thuộc tính cấu hình cần phân biệt, cache sẽ trộn trạng thái.
- Có tình huống **cố ý chia sẻ** cấu hình logic giữa nhiều site; khi đó key theo *logical feature* là hợp lý, nhưng đó phải là quyết định có chủ đích, không phải tối ưu mặc định.

Một bảng chọn key:

| Loại dữ liệu muốn cache | Key phù hợp về nguyên tắc | Lưu ý |
| --- | --- | --- |
| Cấu hình bất biến dùng chung cho một feature | `(tenant, featureId, version)` nếu contract định nghĩa vậy | Không phụ thuộc việc BSM thắng; bảo đảm loader/tenant isolation |
| Metadata riêng cho caller class | `(caller.lookupClass(), configId)` | `Class<?>` phản ánh identity cùng loader; cache mạnh có thể giữ class loader sống |
| Dữ liệu riêng cho từng instruction | ID **được cấp riêng** cho instruction từ static args hoặc metadata ngoài | `(caller,name,type)` một mình không bảo đảm phân biệt hai instruction |
| Metric attempts | Khóa theo nhu cầu quan sát (caller/site/feature) | Đặt tên attempts, không đặt tên installed |
| Một giao dịch ngoại vi cần once-only | Business idempotency key có unique constraint bền vững | Không dựa vào identity của object CallSite ngẫu nhiên |

Trong ví dụ, `SiteKey(Class<?> caller,String logicalId)` được dùng để minh họa caching một **logical registration** theo lớp caller và ID tường minh. Nó **không** được khẳng định là khóa duy nhất cho mọi instruction nếu hai instruction cố ý dùng cùng `logicalId`. Muốn phân biệt chúng, người tạo bytecode cần truyền static argument nhận diện site riêng hoặc dùng kiến trúc registry quản lý instruction cụ thể.

### 8.1. Tránh rò rỉ class loader

Cache static sống lâu mà giữ `Class<?>`, `Lookup`, `MethodHandle`, `CallSite` hoặc instance thuộc plugin có thể giữ cả class loader sống, khiến hot reload/unload thất bại. Nếu cần cache theo caller class, cân nhắc `ClassValue`, cache có vòng đời rõ, key yếu và chính sách dọn dẹp phù hợp. **Không** dùng một `ConcurrentHashMap` static vô hạn chỉ vì nó thread-safe: thread safety khác memory-lifecycle safety.

## 9. Nếu buộc phải có side effect: xác định cấp độ bảo đảm

### 9.1. At-most-once trong một JVM process

Một cổng `AtomicBoolean` hoặc map/future có thể đảm bảo nhiều BSM attempts phối hợp để **một luồng thực hiện khởi tạo** cho key. Tuy nhiên:

```java
// Minh họa ý tưởng; thiếu recovery nếu registerService() thất bại.
if (installed.compareAndSet(false, true)) {
    registerService();
}
```

Đoạn này giả định `installed` là `AtomicBoolean`, không phải chương trình độc lập. Nếu `registerService()` thất bại sau CAS, cờ vẫn true và các thread khác có thể bỏ qua việc khởi tạo bị lỗi. Nếu chính thao tác registration mất nhiều thời gian, các thread khác cần **chờ trạng thái READY** chứ không chỉ thấy “người khác đã bắt đầu”.

Một thiết kế in-memory đầy đủ hơn dùng cache `CompletableFuture<Registration>` theo key, tạo future bằng primitive thread-safe, một worker thực hiện initializer và hoàn tất future; các waiter cùng đợi success/failure. Cần quy định retry, cancellation, timeout, reentrancy và xoá future khi lỗi để tránh một dead state.

### 9.2. Exactly-once trong hệ ngoài không tự xuất hiện

Một BSM không nên trực tiếp charge payment, xuất hóa đơn hoặc gửi notification như một hành động cần chính xác một lần. CAS và `computeIfAbsent` chỉ bảo vệ **bộ nhớ của process hiện tại**. Khi process crash sau khi remote system nhận request nhưng trước khi ghi nhận success, retry có thể tạo duplicate.

Nếu side effect không thể bỏ, cần:

- Business idempotency key bền vững, độc lập với thread và instance CallSite.
- Unique constraint/transaction hoặc API remote hỗ trợ idempotent requests.
- Ghi nhận trạng thái `PENDING / COMPLETED / FAILED`, kiểm tra kết quả trước khi retry.
- Outbox/inbox hoặc cơ chế xử lý sự kiện có khả năng khử trùng lặp.
- Một lifecycle manager riêng cho bootstrap/linker nếu cần rollback resource hoặc đóng những tài nguyên tạm chưa được dùng.

Cách an toàn nhất thường là **đưa side effect nghiệp vụ ra khỏi BSM** sang điểm thực thi đích hoặc một bước application service đã có transaction/idempotency rõ ràng. Tuy vậy, side effect được chuyển sang target cũng có thể chạy nhiều lần khi target được gọi nhiều lần; muốn once-only phải có gate riêng ở tầng thích hợp.

### 9.3. Không chia sẻ mutable CallSite ngoài ý muốn

Nếu BSM trả một `MutableCallSite` từ cache chung cho nhiều instruction, những instruction đó có thể dùng cùng object. Việc `setTarget` sẽ tác động tới **mọi instruction chia sẻ object**, không chỉ một site.

Nếu ứng dụng cần **mỗi site retarget độc lập**, BSM nên tạo một `MutableCallSite` riêng cho mỗi kết quả yêu cầu, thay vì đưa cùng object singleton từ cache. Ngược lại, chia sẻ object có thể là thiết kế hợp lệ khi muốn cùng policy routing được cập nhật đồng loạt; lúc đó phải ghi rõ semantics và chính sách visibility.

Cũng cần phân biệt:

- `ConstantCallSite`: target cố định sau khi tạo.
- `MutableCallSite`: target có thể thay đổi, visibility giữa thread không tự như volatile; `MutableCallSite.syncAll(...)` là cơ chế đồng bộ đặc thù khi cập nhật target.
- `VolatileCallSite`: target có semantics volatile cho việc đọc/ghi target; phù hợp nếu cập nhật thường xuyên và cần visibility theo hợp đồng đó.

Các lựa chọn này xử lý **thay đổi target sau khi đã liên kết**, không thay thế quy tắc BSM có thể bị gọi cạnh tranh lúc liên kết đầu tiên.

## 10. BSM thất bại: đừng dựa vào việc JVM tự retry

Nếu BSM ném exception, JVM áp dụng quy tắc lỗi liên kết:

- Nếu lỗi là `Error` hoặc subclass, theo đặc tả có thể truyền lỗi đó theo cơ chế resolve.
- Nếu BSM ném một exception không phải `Error`, lỗi liên kết được biểu diễn bằng `BootstrapMethodError` có cause tương ứng.
- Nếu BSM trả `null`, một object không phải `CallSite`, hoặc `CallSite` có type sai, resolution không hợp lệ và phát sinh `BootstrapMethodError`.
- Với một instruction đã thất bại trong resolution, **không có hợp đồng “mỗi lần gọi lại bootstrap để thử lần nữa”**. Kết quả lỗi liên kết được ghi nhận cho những lần resolution sau theo quy tắc JVM.

Đừng làm BSM kiểu:

```java
// Anti-pattern: side effect có thể thành công rồi type check thất bại.
chargeCustomer();
return new ConstantCallSite(wrongTypeHandle);
```

Đoạn trên chỉ là anti-pattern minh họa. Nếu `wrongTypeHandle` không khớp `MethodType` yêu cầu, linkage thất bại **sau khi** khách đã bị charge. Một thread cạnh tranh khác cũng có thể charge. Sự kiện “call site không dùng được” không hoàn tác giao dịch đã xảy ra.

**Trình tự tốt hơn:**

1. Validate tên, `MethodType`, metadata và quyền lookup.
2. Tìm/chuyển handle, kiểm tra `target.type().equals(type)` hoặc thực hiện adapter có kiểm soát.
3. Chuẩn bị `CallSite` local hợp lệ, không side effect nguy hiểm.
4. Chỉ đăng ký cấu hình/cache thread-safe nếu đây thật sự là một phần bắt buộc của hợp đồng; ưu tiên cache immutable và idempotent.
5. Return `CallSite`. Nếu thất bại, log nguyên nhân rõ ràng, không nuốt lỗi và không dựa vào retry tự động.

**Giới hạn race khi có cả success và failure:** đặc tả cho phép concurrent bootstrap attempts; đừng suy diễn rằng runtime nhất định sẽ chọn kết quả của attempt thành công hoặc sẽ retry trên request tiếp theo. Hãy thiết kế để mọi attempt hợp lệ dưới cùng metadata có kết quả tương đương và không cần side effect có tính “thắng/thua”.

## 11. Reentrancy, khởi tạo lớp và deadlock

BSM không chỉ chạy logic ứng dụng mà có thể kéo theo resolution của class khác, method handle, static arguments hoặc các dynamic constants. Một BSM cũng có thể gián tiếp kích hoạt một call site khác hoặc chính logic liên kết liên quan.

Những tình huống cần cảnh giác:

- Giữ `synchronized(globalRegistry)`, sau đó gọi `Class.forName` hoặc thực hiện reflection/class loading phức tạp; thread khác giữ class-initialization lock và đang chờ registry lock.
- Trong `computeIfAbsent`, mapping function gọi code quay lại cập nhật cùng map/key — không phải thao tác được bảo đảm an toàn; có thể thất bại hoặc gây chờ/hành vi không mong đợi.
- BSM truy cập một static field mà initializer của class chứa field lại gọi vào chính dynamic site đang được resolve.
- Khởi tạo các dependency trong BSM rồi chờ thread khác mà thread đó đang bị chặn bởi class initialization hoặc một lock do BSM nắm giữ.
- BSM tạo target có phụ thuộc vào một cấu hình global mutable chưa được publish đúng cách.

Theo JVM spec, một số chu trình resolve bootstrap có thể dẫn tới `StackOverflowError` do gọi lồng nhau. Không nên dùng recursion trong BSM làm cơ chế “thử lại đến khi thành công”. Giữ BSM **nhanh, ít khóa, ít I/O, ít khởi tạo phụ** và tránh gọi lại cùng site trong quá trình nó chưa liên kết.

## 12. Kiểm thử đúng: đừng dựa vào một lần chạy invokedynamic

**Kiểm thử chức năng** xác nhận target nhận đúng tham số và trả đúng kiểu. **Kiểm thử concurrency** xác nhận BSM chịu được nhiều attempts và shared state có idempotency. **Kiểm thử liên kết JVM** xác nhận class file thật có `invokedynamic` và bootstrap metadata mong muốn. Ba loại này bổ sung nhau, không thay nhau.

| Bài kiểm thử | Mục tiêu | Điều không được suy ra |
| --- | --- | --- |
| Gọi BSM thủ công từ 2–100 thread có latch/barrier | Khả năng chịu concurrent invocation và cache/key logic | JVM thật chắc chắn chạy BSM bấy nhiêu lần |
| Dùng `javap -v` | Xem `CONSTANT_InvokeDynamic` và `BootstrapMethods` của class file | Số lần bootstrap method thực thi tại runtime |
| Chạy stress nhiều JDK/CPU | Tìm data race, deadlock, duplicate, timing issue | Stress pass chứng minh mọi interleaving đều đúng |
| Tiêm failure vào initializer/cache | Kiểm tra retry, cleanup và không giữ trạng thái `INITIALIZING` vĩnh viễn | JVM sẽ tự retry một linkage đã thất bại |
| Hai call sites cùng `name/type` nhưng static args khác | Đảm bảo key không đè lẫn logical site | Bộ ba caller/name/type luôn xác định instruction |
| Plugin load/unload lặp lại | Phát hiện classloader leak do static cache | `ConcurrentHashMap` tự dọn cache khi plugin unload |

### 12.1. Thiết kế stress test có giá trị

Với BSM tùy biến có thể được gọi trực tiếp, test nên:

1. Tạo **cùng request key** cho tất cả task để kiểm tra sự tranh chấp thật trên một logical registration.
2. Đồng bộ điểm bắt đầu bằng `CountDownLatch` hoặc `CyclicBarrier`, không chỉ `Thread.sleep`.
3. Lấy kết quả từng `Future` và kiểm tra **mọi CallSite trả về đều có type đúng** và hành vi tương đương.
4. Kiểm tra số lượng *attempts* bằng counter thread-safe; biết trước số lần gọi chủ động trong harness.
5. Kiểm tra side effect once-only trong phạm vi có thể: cache size, số registration, trạng thái cuối và chính sách lỗi.
6. Thử mapping function ném exception hoặc timeout; bảo đảm không để cấu hình nửa khởi tạo.
7. Tách metric “BSM attempted” khỏi “logical registration”, “linkage success” và “target invocation”.
8. Kiểm tra độc lập trường hợp hai logical IDs khác nhau, hai caller classes khác nhau, hoặc hai class loader khác nhau.
9. Đừng thêm logging có `synchronized` trong đường nóng rồi mặc định kết quả test vẫn đại diện cho interleaving bình thường; instrumentation có thể vô tình che race.
10. Nếu hệ thống có durable side effect, thử crash/restart và retry với cùng idempotency key, không chỉ chạy trong cùng JVM.

### 12.2. Tiêu chí cho một BSM an toàn

Một code review tốt có thể trả lời được:

```text
BSM input:
  Lookup lookup, String name, MethodType type, staticArgs ...
Semantic site identity:
  định nghĩa rõ caller + logicalId (hoặc khác), không đoán unique
Local target construction:
  pure / equivalent across competing attempts
Shared registry:
  thread-safe, immutable values, defined cleanup
External side effect:
  absent (preferred) or durable idempotency + error recovery
CallSite:
  non-null; type exactly expected; mutable-sharing intentional?
Failure:
  BootstrapMethodError? invalid metadata? who owns cleanup?
Observability:
  attempts != installed CallSites != invocation count
Testing:
  manual concurrency + real classfile inspection + failure injection
```

Nếu một BSM không có đáp án cho **“losing attempt đã làm gì?”**, **“retry sau lỗi có an toàn không?”** và **“khóa cache phân biệt hai site thế nào?”**, chưa nên coi thiết kế đó là an toàn để đưa vào production.

## 13. Những lỗi hiểu nhầm phổ biến

| Nhận định hoặc hiện tượng | Đúng/sai và giải thích |
| --- | --- |
| “Cùng một instruction nên bootstrap chỉ gọi đúng một lần” | **Sai.** JVM có thể chạy nhiều bootstrap attempts cạnh tranh cho instruction chưa liên kết |
| “Chỉ một CallSite được chọn nên side effect cũng một lần” | **Sai.** Các BSM loser có thể hoàn thành tác dụng phụ; kết quả CallSite của họ mới bị bỏ |
| “Dùng `AtomicInteger` là side effect once-only” | **Sai.** Atomic counter đếm attempts đúng, nhưng không ngăn business operation chạy nhiều lần |
| “`volatile boolean done` + check-then-act đã đủ” | **Sai.** Check và action không nguyên tử như một giao dịch |
| “Có `ConcurrentHashMap.computeIfAbsent` nên external charge exactly-once” | **Sai.** Có thể lỗi, retry, crash, nhiều process; cần durable idempotency |
| “`name + MethodType` phân biệt được từng invokedynamic instruction” | **Không bảo đảm.** Nhiều instruction có thể trùng; cần contract ID nếu muốn phân biệt |
| “BSM thất bại thì call site tự retry khi thread khác gọi” | **Không có hợp đồng đó.** Linkage errors được ghi nhận theo quy tắc JVM |
| “`MutableCallSite.setTarget` gọi lại bootstrap” | **Sai.** Retarget là chuyện sau linkage, không tái chạy bootstrap |
| “Số lần in log BSM trên JVM này luôn là 1, nên code ổn” | **Không đủ.** Spec cho phép cạnh tranh; test trên một lịch chạy không chứng minh an toàn |
| “Chỉ nên chia sẻ CallSite vì tiết kiệm bộ nhớ” | **Phụ thuộc.** Shared mutable target có thể nối các site vốn phải độc lập |
| “Tạo mỗi lần một ConstantCallSite là duplicate side effect” | **Không nhất thiết.** Local allocation/GC khác với registration hoặc I/O không idempotent |
| “JVM chọn BSM chạy xong nhanh nhất” | **Không được hứa hẹn.** Không dựa vào một chính sách chọn winner cụ thể |

## 14. Bài tập tự kiểm tra

**Bài 1.** Hai thread cùng chạy BSM cho một instruction chưa liên kết, mỗi BSM gọi `mailService.sendWelcomeEmail()` rồi trả `ConstantCallSite`. JVM chỉ chọn một CallSite. Có thể gửi hai email không?

**Đáp án:** Có. JVM chọn một *kết quả liên kết*, không hoàn tác side effects của loser. Không gửi welcome email trực tiếp từ BSM; đưa tác vụ qua workflow có idempotency.

**Bài 2.** BSM dùng `static int registrations; registrations++;` để đo số site đã liên kết. Có hai lỗi nào?

**Đáp án:** `registrations++` không atomic nên có data race; đồng thời nó đếm bootstrap attempts (chưa chắc đúng do race), **không** đếm số site mà JVM đã cài đặt.

**Bài 3.** Hai BSM attempts cùng gọi `ConcurrentHashMap.computeIfAbsent` với cùng key và mapping function trả giá trị bình thường, không xóa key. Có thể dùng làm cache cấu hình in-memory?

**Đáp án:** Có, nếu key và dữ liệu đúng phạm vi và giá trị được publish an toàn. Không đồng nghĩa exactly-once ngoại vi qua exception hoặc process restart; mapping function phải ngắn gọn, tránh reentrancy.

**Bài 4.** Hai instruction trong cùng class dùng `name="route"`, `type=(String)String`, nhưng static argument `siteId` lần lượt là `"A"` và `"B"`. Có nên cache theo `(callerClass,name,type)` để tạo state riêng?

**Đáp án:** Không, vì key như thế trùng cho cả hai. Nếu state phải riêng, thêm `siteId` hoặc ID được bảo đảm phân biệt vào key.

**Bài 5.** BSM trả `new ConstantCallSite(handle)`, nhưng `handle.type()` khác kiểu mà instruction yêu cầu. Hệ quả?

**Đáp án:** Linkage bị từ chối bằng `BootstrapMethodError` theo quy tắc validation của JVM. Nên validate/adapter type trước khi thực hiện side effects.

**Bài 6.** Trong thử nghiệm manual, `attempts=2` và `registrations=1`. Có thể kết luận JVM đã cài một trong hai CallSite đó vào bytecode không?

**Đáp án:** Không. Thử nghiệm **gọi BSM trực tiếp từ Java code**, không thực thi lệnh `invokedynamic` tự viết. Nó kiểm tra concurrency của BSM, không mô phỏng bước chọn/cài đặt kết quả của JVM.

**Bài 7.** BSM cache chung một `MutableCallSite` cho hai instruction khác nhau. Sau đó gọi `setTarget`. Điều gì cần xem lại?

**Đáp án:** Cả hai instruction có thể chia sẻ thay đổi target của cùng object. Nếu yêu cầu độc lập, mỗi site phải có CallSite riêng; nếu cố ý chia sẻ, phải quy định chính sách visibility (`syncAll` hoặc cân nhắc `VolatileCallSite`).

**Bài 8.** Thread T1 đánh dấu `initialized=true` bằng CAS trước khi ghi config; T2 thấy true và dùng config. Có an toàn không?

**Đáp án:** Chưa. CAS chỉ thắng quyền thực hiện, không chứng minh config đã sẵn sàng. Cần công bố trạng thái `READY` **sau** khi khởi tạo thành công và cơ chế chờ/nhận lỗi thích hợp.

## Nguồn đặc tả và API chính thức

- [JVMS Java SE 17 `5.4.3.6 — Dynamically-Computed Constant and Call Site Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6): BSM arguments, khả năng bootstrap cạnh tranh, kết quả được chọn, xử lý lỗi và validation của CallSite.
- [Java SE 17 `java.lang.invoke` — Dynamic resolution / Timing of resolution](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/package-summary.html): diễn giải rõ mỗi instruction được liên kết, BSM có thể chạy trên nhiều thread và loser có thể đã có side effect.
- [JDK 17 `ConstantCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html): target không đổi sau construction.
- [JDK 17 `MutableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html) và [`VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): thay đổi target sau linkage và memory visibility.
- [JDK 17 `ConcurrentHashMap.computeIfAbsent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function)): nguyên tắc tính atomically theo key và giới hạn mapping function.
- [JDK 17 `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): kiểm tra `invokedynamic` và bảng `BootstrapMethods` trong class file.

**Ghi nhớ:** đừng viết bootstrap dựa trên giả định “JVM chỉ gọi tôi một lần”. Hãy xây BSM sao cho **mọi attempt đều an toàn**, kể cả attempt không thắng: ưu tiên *pure/local work*, dùng cache thread-safe theo key có chủ đích, giữ trạng thái được publish đầy đủ, tách metric attempts khỏi linkage, và đẩy side effect ngoại vi sang một giao thức idempotent có kiểm soát. **Một liên kết được lắp đặt không đồng nghĩa một lần thực hiện tác dụng phụ.**
