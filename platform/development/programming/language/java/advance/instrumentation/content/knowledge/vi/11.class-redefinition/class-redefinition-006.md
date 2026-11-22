# Lớp, đối tượng và trạng thái đang tồn tại được giữ như thế nào khi Redefinition?

**Java Instrumentation** cho phép thay **định nghĩa bytecode của một class đã được JVM nạp** bằng `Instrumentation.redefineClasses(...)`. Điều dễ nhầm là từ “thay định nghĩa” không có nghĩa JVM hủy class cũ, tạo class mới, khởi tạo lại static fields rồi tạo lại mọi object trong heap.

Theo hợp đồng của Java Instrumentation và JVM Tool Interface (JVMTI), **redefinition thành công bảo toàn các instance hiện có và trạng thái field của chúng; không tự chạy lại class initializer; các static field giữ giá trị trước thao tác**. Đồng thời, **những lời gọi method mới dùng phiên bản bytecode mới**, còn stack frame của một method **đang thực thi** tiếp tục dùng bytecode phiên bản cũ. Đó là lý do cùng một object có thể đang hoàn tất một lời gọi theo logic cũ nhưng ngay sau đó thực hiện lời gọi khác theo logic mới.

Bài học thuộc chủ đề **Redefinition**, tập trung vào câu hỏi trực tiếp: *Class identity, object identity, instance fields, static state và lời gọi method đang hoạt động thay đổi hoặc được giữ như thế nào?* Bài có một Java agent JDK 17+ chạy được, sử dụng **redefinition thật**, kèm minh chứng về state, identity, `<clinit>` và active stack frames.

## 1. Nhìn đúng bản chất: thay method definition, không thay object

Trước redefinition:

~~~text
Class object:   LiveCounter.class (Class<?> C)
       |
       +-- static shared = 345, initRuns = 1
       |
       +-- method compute(): return value + 1
       |
       +-- instance A: { value = 7  }
       +-- instance B: { value = 12 }

Một lời gọi inFlight() đang có stack frame chạy code cũ.
~~~

JVM nhận **class bytes mới** cho chính class C:

~~~text
Instrumentation.redefineClasses(
    new ClassDefinition(C, replacementBytes)
)
                      |
              JVM xác minh class
                      |
              Định nghĩa method mới
~~~

Sau khi redefinition thành công:

~~~text
Class object:   vẫn là C
       |
       +-- static shared = 345, initRuns = 1    (KHÔNG tự reset)
       |
       +-- method compute(): return value + 1000 (lời gọi mới)
       |
       +-- instance A: vẫn chính object A, { value = 7  }
       +-- instance B: vẫn chính object B, { value = 12 }

Frame inFlight() đã bắt đầu trước đó -> tiếp tục code cũ.
Lời gọi compute() mới trên object A/B -> dùng code mới.
~~~

Trong ví dụ này, giá trị `shared = 345` được ứng dụng chủ động đặt **trước** redefinition. Dù file class thay thế có mã khởi tạo `shared = 999`, JVM **không tự chạy lại phần khởi tạo** đó. Tương tự, constructor không được chạy lại cho các object đã có.

**Bốn ý phải tách riêng:**

1. **Class identity**: đối tượng `Class<?>` của target vẫn được dùng; không sinh class mới chỉ vì redefine.
2. **Object identity**: tham chiếu tới instance hiện có vẫn trỏ tới chính instance đó; không clone/recreate.
3. **Heap state**: các giá trị instance/static fields hiện có không bị reset bởi thao tác redefine.
4. **Executable method versions**: method body **có thể được thay**, nhưng active stack frames không tự chuyển giữa chừng sang code mới.

Không nên rút gọn thành “redefinition không làm gì tới chương trình đang chạy”. Ngược lại, sau khi redefine thành công, **các lời gọi mới có thể thay đổi hành vi rõ rệt**, và do đó có thể **thay trạng thái về sau** theo logic mới.

## 2. Class identity vẫn được giữ

Trong JVM, cùng binary name như `com.example.LiveCounter` **không đủ** để xác định duy nhất một class: class loader định nghĩa nó cũng quan trọng. Trong cùng class loader, một class đã được định nghĩa có `Class<?>` đại diện cho danh tính runtime của nó.

Với:

~~~java
Class<?> before = liveCounter.getClass();

// Redefine chính Class object này bằng ClassDefinition(before, newBytes).

Class<?> after = liveCounter.getClass();
boolean sameClass = before == after;
~~~

Khi thao tác thành công theo contract, `sameClass` vẫn `true`. Đoạn code ở trên là **mảnh minh họa**; nó cần một instance `liveCounter` cùng lời gọi redefine đã được chuẩn bị. Code runnable hoàn chỉnh ở mục 7.

### Redefinition không giống load một class trùng tên bằng class loader khác

Hai trường hợp khác nhau:

| Hành động | Kết quả về danh tính |
| --- | --- |
| `redefineClasses(new ClassDefinition(existingClass, bytes))` | Định nghĩa **chính class đã tồn tại** được cập nhật; không tạo danh tính class mới |
| Tạo `new URLClassLoader(...)` rồi nạp class file trùng binary name | Tạo một **class khác** nếu loader đó thực sự định nghĩa class; có thể không cast được qua ranh giới loader |
| Khởi động JVM khác với JAR mới | Tất cả class/instance/state được tạo cho tiến trình khác; không phải redefinition của tiến trình cũ |
| Dùng reflection gọi method trên instance cũ sau redefine | Vẫn tương tác với **object cũ**, và hành vi của lời gọi method mới theo định nghĩa hiện hành |

Vì vậy, để kiểm tra class identity, dùng `before == after` (tham chiếu), không chỉ so sánh `getName()`; hai class khác loader vẫn có thể cùng tên. Đừng dùng `System.identityHashCode(...)` làm bằng chứng duy nhất cho việc là cùng object; hai object khác nhau về lý thuyết có thể trùng identity hash. Dùng `==` trong một test kiểm chứng trực tiếp.

### Hệ quả với existing references và kiểu dữ liệu

Một biến đã giữ tham chiếu tới `LiveCounter` **không cần được cập nhật lại** để gọi method đã redefine. Những tham chiếu đó vẫn hợp lệ và đối tượng vẫn có runtime type như trước. Các collection, cache, dependency-injection container hoặc object graph chứa đối tượng cũ không tự bị thay vì redefinition.

Điều này là một lợi ích lớn của sửa logic runtime, nhưng cũng giới hạn ta: **không có cơ chế tự động chạy migration** để cập nhật tất cả existing instances theo một schema field hoàn toàn mới.

## 3. Instance hiện có không bị tạo lại; field của chúng giữ giá trị

Giả sử:

~~~java
LiveCounter a = new LiveCounter(7);
LiveCounter b = new LiveCounter(12);
Object sameReference = a;
~~~

Sau khi redefine class:

~~~java
boolean identityPreserved = (a == sameReference);
int stillSeven = a.getValue();
int stillTwelve = b.getValue();
~~~

Đây là **mảnh code đặt trong chương trình đã định nghĩa `LiveCounter` và đã redefine thành công**. Với phương thức `getValue()` có nội dung không đổi như demo bên dưới, giá trị tương ứng vẫn là `7` và `12`.

**Vì sao?** Heap đã chứa các object với các field slots; việc thay method definition không phải thao tác `new`, `clone`, Java serialization/deserialization hay khởi tạo lại object. Theo JVMTI, instances của class được redefine không bị ảnh hưởng và các field giữ giá trị trước đó.

Tuy nhiên, cần tránh hai suy luận quá mức:

- **Không bảo đảm object state sẽ luôn giống mãi về sau**. Một method mới có thể ghi `this.value = ...` khi nó được gọi; khi đó state thay đổi do **thực thi code mới**, không phải vì redefinition tự reset state.
- **Không bảo đảm mọi dữ liệu nghiệp vụ vẫn tương thích**. Nếu code mới diễn giải field `int status` với ý nghĩa khác code cũ, JVM vẫn giữ bit-pattern cũ, nhưng logic ứng dụng có thể không còn đúng. JVM không tự migration dữ liệu nghiệp vụ.

### Constructor có được chạy lại không?

**Không.** Các object đã có không được đưa qua constructor thêm một lần chỉ vì class được redefine.

Nếu body của constructor trong bytes mới được thay đổi một cách hợp lệ, các **lần tạo object mới** sẽ thực thi constructor phiên bản mới, trong khi instance hiện có không bị tạo lại. Trong bài demo, constructor được giữ cùng body để cô lập yếu tố redefinition của `compute()`.

### Vì sao không được thêm field mới tùy ý?

Redefinition chuẩn trong JVM TI có ràng buộc về **schema/class structure**. Không thể mặc nhiên thêm một field `int generation;` rồi trông chờ JVM mở rộng layout của tất cả existing objects. Những thay đổi như thêm/xóa/đổi tên field, đổi method signature, thay quan hệ kế thừa thường **không được phép**; phần 9 trình bày các giới hạn cụ thể.

Nếu cần state mới cho logic instrumented, cân nhắc **side table** được quản lý bởi agent (có chiến lược lifetime và identity phù hợp), hoặc phát hành phiên bản ứng dụng có migration rõ ràng, thay vì dựa vào HotSwap như cơ chế thay schema.

## 4. Static fields không tự reset và class initializer không chạy lại

Đây là một điểm dễ gây hiểu nhầm khi nhìn vào source của class thay thế.

Ví dụ class gốc:

~~~java
public static int initRuns;
public static int shared = 100;

static {
    initRuns++;
    System.out.println("clinit=original");
}
~~~

Class thay thế được biên dịch từ source có:

~~~java
public static int initRuns;
public static int shared = 999;

static {
    initRuns++;
    System.out.println("clinit=patched");
}
~~~

Cả hai đoạn là **phần trích của hai phiên bản cùng class**, không phải hai khai báo cùng tồn tại trong một file. Trên bytecode, khai báo có initializer thuộc mã khởi tạo static `<clinit>`.

Nếu class đã được khởi tạo từ trước, và code nghiệp vụ đặt:

~~~java
LiveCounter.shared = 345;
~~~

thì sau khi redefine thành công:

- `LiveCounter.shared` **vẫn là 345**, không thành 999.
- `LiveCounter.initRuns` **vẫn là 1**, không tự thành 2.
- Không xuất hiện log `clinit=patched` **chỉ vì lời gọi redefine**.

Lý do: hợp đồng redefinition nêu rõ **không gây khởi tạo lại class**, ngoại trừ cơ chế khởi tạo thông thường của JVM nếu có lý do độc lập để class được khởi tạo. Redefinition không phải công cụ reset state.

### Nếu file class mới đổi cách tính giá trị static thì sao?

Có hai loại thay đổi phải phân biệt:

| Thay đổi trong bytes mới | Điều xảy ra |
| --- | --- |
| Đổi giá trị được gán trong `<clinit>` từ `100` thành `999` | Với class đã khởi tạo, **không tự chạy lại `<clinit>`**; static value đang có vẫn giữ |
| Đổi thân một static method `total()` từ `return shared + 1` thành `return shared + 1000` | **Lời gọi mới** sử dụng method body mới và đọc **giá trị shared đang có** |
| Application tự gọi `LiveCounter.shared = 0` sau redefine | Giá trị đổi về 0 vì có **một lệnh gán mới**, không phải tự động do redefine |
| Agent chủ động dùng reflection/VarHandle để gán static field | State có thể đổi vì **hành động khác của agent**; không phải semantic mặc định của `redefineClasses` |

Ví dụ nếu `shared = 345`, lời gọi mới tới `total()` đã thay body sẽ trả `1345`. Code mới và state cũ có thể **cùng tồn tại**; đó chính là điều cần kiểm thử về tương thích nghiệp vụ.

### Static final và compile-time constants

Cần cẩn trọng khi class có `static final` primitive hoặc `String` là **constant variable** theo JLS. Caller đã được `javac` biên dịch có thể sử dụng **giá trị hằng đã được inline**, thay vì đọc field lúc runtime. Vì vậy đổi source của constant trong class thay thế **không đủ** để buộc mọi caller đã load nhìn thấy giá trị mới. Hơn nữa, phép redefine không tự reset static field.

Đừng đánh đồng “body method mới được gọi” với “mọi chỗ dùng static constant lập tức cập nhật”. Muốn cấu hình thay đổi khi runtime, thiết kế đường đọc state rõ ràng (ví dụ accessor method đọc field biến đổi được), và kiểm thử đúng phiên bản compiled callers.

## 5. Method body mới áp dụng cho lời gọi mới, frame đang chạy tiếp tục body cũ

Đây là phân biệt quan trọng nhất khi ứng dụng có nhiều thread hoặc có method chạy lâu.

Theo Java Instrumentation:

- Khi một method được redefine trong lúc có **active stack frame**, các frame đó tiếp tục thực thi **bytecode của phiên bản method ban đầu**.
- **New invocations** của method được thực hiện sau redefinition sẽ dùng **phiên bản method mới**.

Sơ đồ:

~~~text
Thread A: vào LiveCounter.inFlight() [bytecode v1]
          |
          | chờ CountDownLatch
          |
Thread B: redefine LiveCounter [v2]
          |
          +----> v2 được cài đặt thành công
          |
Thread A: tiếp tục frame inFlight() cũ [v1] -> trả v1-result

Thread A/B: gọi inFlight() MỚI           [v2] -> trả v2-result
~~~

Không có thao tác “hoán đổi instruction pointer giữa hai body” trong một frame đang chạy. Nếu method cũ vừa qua một phần tính toán, JVM không thể đơn giản nhảy nó sang offset bytecode mới mà vẫn bảo đảm stack/locals và control flow hợp lệ.

### Một frame cũ vẫn có thể gọi một method mới

Nếu frame cũ sau khi tiếp tục thực thi **gọi một method khác**, lời gọi đó là một invocation mới và theo quy tắc sử dụng định nghĩa method hiện hành. Vì thế **một stack có thể chứa frame của phiên bản cũ và frame được gọi theo phiên bản mới**. Đừng suy luận rằng toàn bộ thread bị “khóa cứng” ở phiên bản cũ cho đến khi thread kết thúc.

Tương tự, object được frame cũ thao tác vẫn là object hiện có. Code cũ và code mới có thể đọc/ghi cùng state. Đây là lý do patch logic đồng thời (concurrency-sensitive) cần kiểm thử mạnh hơn việc chỉ nhìn một giá trị `compute()` sau redefinition.

### Có cần dừng toàn bộ thread?

Java Instrumentation API không yêu cầu người gọi tự dừng mọi thread mới được `redefineClasses`. JVM thực hiện công việc đồng bộ/đảm bảo nhất quán theo implementation. Tuy nhiên, một hệ thống nghiệp vụ vẫn có thể cần **quiescence ở mức ứng dụng** nếu patch thay đổi protocol tương tác giữa các method, giao dịch hoặc shared state.

Không coi redefinition là cơ chế giao dịch tự động cho logic nghiệp vụ đang chạy. Tính nguyên tử của **cập nhật class bytes** khác với việc mọi request đang xử lý đồng thời đều nhìn cùng version business logic từ đầu đến cuối.

## 6. API và yêu cầu trước khi redefine

API Java 17+:

~~~java
void Instrumentation.redefineClasses(ClassDefinition... definitions)
        throws ClassNotFoundException, UnmodifiableClassException
~~~

Và tạo một định nghĩa thay thế:

~~~java
ClassDefinition replacement =
        new ClassDefinition(targetClass, newClassFileBytes);

instrumentation.redefineClasses(replacement);
~~~

Đây là **mảnh minh họa**, cần `Instrumentation instrumentation` do JVM cấp cho Java agent, một `Class<?> targetClass` và `byte[] newClassFileBytes` đúng binary name.

### Các điều kiện cần

1. **Agent JAR** phải khai báo `Can-Redefine-Classes: true` trong manifest.
2. JVM phải thực sự có redefinition capability; kiểm tra `inst.isRedefineClassesSupported()`.
3. Class đích phải được JVM xem là modifiable; kiểm tra `inst.isModifiableClass(targetClass)`.
4. Bytes mới phải đại diện **chính binary name** của class cần thay và là class file hợp lệ, dùng class-file version JVM chấp nhận.
5. Thay đổi phải nằm trong **giới hạn redefine** của JVM, nhất là không thay schema bị cấm.
6. Khi có transformer đã đăng ký, bytes của lần redefine còn có thể đi qua các `ClassFileTransformer` theo hợp đồng. Kết quả cuối cùng sau các transform cũng phải hợp lệ.

`isRedefineClassesSupported()` và `isModifiableClass(...)` là **hai phép kiểm tra khác nhau**. Nếu capability của JVM đúng nhưng class là primitive/array hoặc thuộc nhóm VM đánh dấu không thể sửa, vẫn không thể redefine nó. Ngược lại, class modifiable không thể cứu được việc JVM/agent thiếu redefinition capability.

### Redefine khác Retransform

| Câu hỏi | Redefinition | Retransformation |
| --- | --- | --- |
| API | `redefineClasses(ClassDefinition...)` | `retransformClasses(Class<?>...)` |
| Nguồn class bytes | **Caller cung cấp bytes mới** tương ứng target | JVM bắt đầu từ bytes gốc phù hợp rồi áp lại/chạy lại các transformers |
| Capability | `Can-Redefine-Classes` | `Can-Retransform-Classes` |
| Use case thường gặp | Hot fix / replace method implementation từ class file đã biên dịch | Áp dụng lại bytecode instrumentation trên class đã load |
| Giữ instance, static state và frame cũ? | Có, theo hợp đồng class redefinition | Có các ngữ nghĩa tương ứng về state và active frames |
| Có tự chạy lại constructor hoặc `<clinit>`? | Không | Không |

**Không dùng class loader mới như một lối tắt** để tái hiện trạng thái của class cũ: nạp một class trùng tên vào loader mới là vấn đề khác, không cập nhật method của object đã nạp bởi loader cũ.

## 7. Ví dụ đầy đủ: redefine class đang có object và frame hoạt động

Ví dụ gồm hai phiên bản **cùng binary name `LiveCounter`** biên dịch vào **hai thư mục khác nhau**, một agent `RedefineAgent` và chương trình `RedefineStateDemo`. Nó minh họa đồng thời:

- Instance cũ vẫn **cùng tham chiếu**, cùng `Class<?>` và giữ field `value`.
- Static field `shared` và bộ đếm `initRuns` không reset.
- File class thay thế có static initializer khác, nhưng initializer đó **không chạy lại**.
- Method `inFlight()` bắt đầu **trước** redefinition vẫn trả kết quả theo body cũ.
- Lời gọi mới tới method trên **chính instance cũ** sử dụng body mới.
- Instance được tạo **sau** redefinition cũng sử dụng body mới.

Dùng JDK **17 trở lên**. Ví dụ đã biên dịch và chạy thực tế trên **Zulu OpenJDK 24.0.2**. Cần chạy tại JVM hỗ trợ redefinition; nếu không, agent sẽ nêu rõ lỗi capability thay vì giả vờ đã áp dụng patch.

### 7.1. Bố trí thư mục

Tạo các thư mục và file:

~~~text
redefine-state-example/
├── old/
│   └── LiveCounter.java
├── new/
│   └── LiveCounter.java
├── app/
│   ├── RedefineAgent.java
│   └── RedefineStateDemo.java
└── agent.mf
~~~

Hai file `LiveCounter.java` chứa **hai phiên bản khác nhau của cùng class**, **không đặt chung vào một thư mục output của javac**. Hai phiên bản phải có cùng fields, method names/descriptors và flags tương ứng; chỉ đổi nội dung method body và code `<clinit>` cho mục đích demo.

### 7.2. File old/LiveCounter.java

~~~java
import java.util.concurrent.CountDownLatch;

public final class LiveCounter {
    public static int initRuns;
    public static int shared = 100;

    static {
        initRuns++;
        System.out.println("clinit=original");
    }

    private int value;

    public LiveCounter(int value) {
        this.value = value;
    }

    public int getValue() {
        return value;
    }

    public int compute() {
        return value + 1;
    }

    public int inFlight(CountDownLatch entered, CountDownLatch proceed) {
        entered.countDown();
        try {
            proceed.await();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(interrupted);
        }
        return value + 10;
    }

    public static int total() {
        return shared + 1;
    }
}
~~~

Cần chú ý `inFlight()` có hai latches:

- `entered.countDown()` báo cho thread chính rằng thread worker **đã vào method v1**.
- `proceed.await()` giữ frame v1 đang hoạt động.
- `return value + 10` nằm **sau** điểm chờ. Khi thread tiếp tục sau redefinition, theo contract frame này vẫn chạy logic v1.

### 7.3. File new/LiveCounter.java

Giữ nguyên class name, fields, signatures và modifiers; đổi **nội dung thực thi**:

~~~java
import java.util.concurrent.CountDownLatch;

public final class LiveCounter {
    public static int initRuns;
    public static int shared = 999;

    static {
        initRuns++;
        System.out.println("clinit=patched");
    }

    private int value;

    public LiveCounter(int value) {
        this.value = value;
    }

    public int getValue() {
        return value;
    }

    public int compute() {
        return value + 1000;
    }

    public int inFlight(CountDownLatch entered, CountDownLatch proceed) {
        entered.countDown();
        try {
            proceed.await();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(interrupted);
        }
        return value + 1000;
    }

    public static int total() {
        return shared + 1000;
    }
}
~~~

Các khác biệt là `shared = 999`, log `clinit=patched`, và body của `compute`, `inFlight`, `total`. **Đừng nhầm** rằng thay `shared = 999` sẽ làm JVM tự gán lại static field thành 999. Nó sẽ không thực hiện `<clinit>` lần hai khi redefine class đã khởi tạo.

### 7.4. File app/RedefineAgent.java

Đây là agent nạp lúc khởi động qua `premain`. Chỉ code có `Instrumentation` do JVM cung cấp mới gọi được `redefineClasses`:

~~~java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("agentReady=true");
    }

    public static void replace(Class<?> target, Path replacementClass)
            throws Exception {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Run with -javaagent:redefine-agent.jar");
        }
        System.out.println("redefineSupported="
                + inst.isRedefineClassesSupported());
        System.out.println("modifiable=" + inst.isModifiableClass(target));
        if (!inst.isRedefineClassesSupported()
                || !inst.isModifiableClass(target)) {
            throw new IllegalStateException("Class redefinition is unavailable");
        }
        inst.redefineClasses(new ClassDefinition(
                target, Files.readAllBytes(replacementClass)));
        System.out.println("redefineApplied=true");
    }
}
~~~

Nội dung file thay thế được đọc qua `Files.readAllBytes`. Agent **chỉ** gọi `redefineClasses` sau khi kiểm tra capability và modifiability. Log `redefineApplied=true` chỉ xuất hiện sau khi lời gọi không ném ngoại lệ.

Trong production, cần xử lý cụ thể `UnmodifiableClassException`, `UnsupportedOperationException`, `ClassFormatError`, `VerifyError` và lỗi class loading/linkage. Ví dụ để lộ ngoại lệ ra ngoài nhằm dễ phân biệt lỗi thao tác với một chương trình có vẻ chạy bình thường nhưng không thực sự redefine.

### 7.5. File app/RedefineStateDemo.java

~~~java
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class RedefineStateDemo {
    public static void main(String[] args) throws Exception {
        LiveCounter existing = new LiveCounter(7);
        LiveCounter another = new LiveCounter(12);
        Object originalReference = existing;
        Class<?> originalClass = existing.getClass();
        LiveCounter.shared = 345;

        System.out.println("beforeOldMethod=" + existing.compute());
        System.out.println("stateBefore=" + existing.getValue());
        System.out.println("sharedBefore=" + LiveCounter.shared);
        System.out.println("initBefore=" + LiveCounter.initRuns);

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch proceed = new CountDownLatch(1);
        AtomicInteger inFlightResult = new AtomicInteger();
        Thread worker = new Thread(() ->
                inFlightResult.set(existing.inFlight(entered, proceed)));
        worker.start();
        entered.await();
        System.out.println("inFlightEntered=true");

        RedefineAgent.replace(LiveCounter.class, Path.of("new", "LiveCounter.class"));

        System.out.println("sameClass=" + (existing.getClass() == originalClass));
        System.out.println("sameObject=" + (existing == originalReference));
        System.out.println("stateAfter=" + existing.getValue());
        System.out.println("sharedAfter=" + LiveCounter.shared);
        System.out.println("initAfter=" + LiveCounter.initRuns);

        proceed.countDown();
        worker.join();
        System.out.println("inFlightOldFrame=" + inFlightResult.get());
        System.out.println("existingNewMethod=" + existing.compute());
        System.out.println("anotherNewMethod=" + another.compute());
        System.out.println("newObjectNewMethod=" + new LiveCounter(4).compute());
        System.out.println("staticNewMethod=" + LiveCounter.total());
        System.out.println("newInvokeInFlight="
                + existing.inFlight(new CountDownLatch(0), new CountDownLatch(0)));
    }
}
~~~

Trình tự có tính quyết định:

1. Tạo **hai existing objects** từ phiên bản cũ; giữ lại `originalReference` và `originalClass`.
2. Gán `shared = 345`, làm thay đổi trạng thái static sau khi class đã khởi tạo.
3. Khởi động worker vào `inFlight(...)` của **v1**. Latch `entered` xác nhận worker đã vào method trước khi main gọi redefine.
4. Thực hiện redefine bằng bytes của file trong thư mục `new/`.
5. Kiểm tra **identity/state** ngay sau khi redefinition hoàn tất.
6. Mở latch để frame cũ hoàn tất; quan sát `inFlightOldFrame=17` (= `7+10`).
7. Gọi lại trên existing object và tạo object mới; quan sát body mới (= `value+1000`).

Sử dụng `CountDownLatch` làm cho việc khởi động frame cũ và thời điểm redefine có thứ tự được xác định; tránh kiểu demo “sleep 100 ms rồi hy vọng worker đã chạy” vốn phụ thuộc tốc độ máy.

### 7.6. File agent.mf

Tạo manifest:

~~~text
Manifest-Version: 1.0
Premain-Class: RedefineAgent
Can-Redefine-Classes: true
~~~

File cần có **dòng trống ở cuối** đúng cú pháp manifest. Đây là redefinition, vì vậy dùng `Can-Redefine-Classes: true`; không cần `Can-Retransform-Classes: true` cho ví dụ này.

### 7.7. Biên dịch và chạy

Từ thư mục gốc `redefine-state-example/`, với **JDK 17+**:

~~~bash
javac -d old old/LiveCounter.java
javac -d new new/LiveCounter.java
javac -cp old -d app app/RedefineAgent.java app/RedefineStateDemo.java
jar --create --file redefine-agent.jar --manifest agent.mf -C app RedefineAgent.class
~~~

Chạy trên **Windows PowerShell**:

~~~powershell
java -javaagent:redefine-agent.jar -cp "old;app" RedefineStateDemo
~~~

Chạy trên **Linux/macOS Bash** (classpath separator là dấu `:`):

~~~bash
java -javaagent:redefine-agent.jar -cp 'old:app' RedefineStateDemo
~~~

**Lưu ý về thư mục output:** `-d old` và `-d new` đưa hai phiên bản `LiveCounter.class` vào hai thư mục khác nhau. Khi chạy, classpath chứa **old** và **app**, **không chứa new**. JVM nạp class gốc từ old; agent chỉ dùng bytes trong new để redefine class đó. Nếu thêm thư mục new vào classpath đầu tiên, bạn sẽ làm sai kịch bản thử nghiệm.

### 7.8. Stdout đã xác minh trên Zulu OpenJDK 24.0.2

~~~text
agentReady=true
clinit=original
beforeOldMethod=8
stateBefore=7
sharedBefore=345
initBefore=1
inFlightEntered=true
redefineSupported=true
modifiable=true
redefineApplied=true
sameClass=true
sameObject=true
stateAfter=7
sharedAfter=345
initAfter=1
inFlightOldFrame=17
existingNewMethod=1007
anotherNewMethod=1012
newObjectNewMethod=1004
staticNewMethod=1345
newInvokeInFlight=1007
~~~

Giải thích **các bằng chứng quan trọng**, không chỉ nhìn ba chữ “true”:

| Kết quả | Chứng minh điều gì? |
| --- | --- |
| `clinit=original` chỉ in một lần | Class gốc được khởi tạo một lần; không có callback `clinit=patched` ở redefinition |
| `sameClass=true` | Existing object giữ cùng đối tượng `Class<?>` |
| `sameObject=true` | Existing object vẫn chính tham chiếu ban đầu |
| `stateAfter=7` | Field `value` của instance cũ không bị reset |
| `sharedAfter=345` | Static state từ trước không bị thay bằng initializer mới là 999 |
| `initAfter=1` | Class initializer không chạy lại |
| `inFlightOldFrame=17` | Frame `inFlight` đã bắt đầu trước redefine tiếp tục body v1, trả `7+10` |
| `existingNewMethod=1007` | Lời gọi mới trên **cùng existing object** chạy body v2, trả `7+1000` |
| `anotherNewMethod=1012` | Một object khác đã tồn tại cũng gọi body v2 |
| `newObjectNewMethod=1004` | Object mới tạo sau redefine dùng body v2 |
| `staticNewMethod=1345` | Static method v2 chạy trên static field **cũ** có giá trị 345 |
| `newInvokeInFlight=1007` | Lời gọi `inFlight` mới thực hiện body v2; khác frame cũ trước đó |

Các dòng `redefineSupported=true` và `modifiable=true` **phụ thuộc môi trường**. Nếu JVM hoặc agent không hỗ trợ, demo chủ động báo lỗi; không được xem hai giá trị đó là quy tắc cho mọi JVM.

### 7.9. Chứng minh bằng code chứ không phải chỉ bằng tên phương thức

Nếu chỉ đọc hai source `old/LiveCounter.java` và `new/LiveCounter.java`, ta chưa chứng minh redefinition thực sự diễn ra. Nhưng stdout kết hợp cả **cờ capability**, log **redefineApplied**, kiểm tra **Class identity** và chênh lệch **active frame vs new invocation** tạo ra chuỗi kiểm chứng độc lập: JVM đã nạp v1, có frame v1 đang chờ, áp dụng bytes v2, rồi gọi v2 trên existing object.

Việc `inFlightOldFrame=17` trong khi `newInvokeInFlight=1007` đặc biệt quan trọng: nó xác nhận không thể mô tả redefinition như thao tác “mọi code trên tất cả threads lập tức chuyển sang v2”.

## 8. Tại sao những sửa đổi class file sau không được phép?

Redefinition theo JVM TI **không phải** cơ chế thay toàn bộ schema của class như lúc load lần đầu. Các hạn chế thông dụng trong đặc tả:

- **Không thêm/xóa/đổi tên fields**.
- **Không thêm/xóa/đổi tên methods**.
- **Không đổi method signatures**.
- **Không đổi class/method modifiers** theo những ràng buộc nêu trong JVMTI.
- **Không đổi superclass / interfaces** hoặc quan hệ kế thừa.
- **Không đổi các thuộc tính cấu trúc** như `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses`.
- Class file cuối phải hợp lệ và có version/kiểu thông tin mà JVM chấp nhận.

Bạn có thể thay **method bodies**, constant pool và các attributes **trong giới hạn cho phép**. Bản thân việc javac tạo ra một `.class` hợp lệ **không đồng nghĩa** file đó có thể dùng để redefine class đang tồn tại. Nếu thêm một field mới vào source thay thế, compiler vẫn biên dịch; lỗi chỉ xuất hiện khi JVM kiểm tra bản redefine.

### Ví dụ thay đổi hợp lệ và không hợp lệ về ý tưởng

| Ý định | Đánh giá trong redefinition chuẩn |
| --- | --- |
| Đổi body `compute()` từ `value+1` sang `value+1000` | **Thường hợp lệ** nếu giữ schema và class bytes đúng |
| Đổi body static method `total()` | **Thường hợp lệ**; state static hiện có giữ nguyên |
| Đổi code `<clinit>` từ gán 100 sang 999 | Có thể có bytes thay đổi, nhưng **không chạy lại initializer** |
| Đổi body constructor nhưng giữ signature | Có thể hợp lệ nếu đáp ứng ràng buộc; **existing objects không chạy lại constructor** |
| Thêm `int newField;` | **Không hợp lệ** theo giới hạn cấu trúc chuẩn |
| Xóa `getValue()` hoặc đổi kiểu trả về của nó | **Không hợp lệ** |
| Đổi `private int value` thành `long value` | Đổi field descriptor/structure, **không hợp lệ** |
| Đổi class `final` thành non-final hoặc thêm interface | Đổi modifiers/hierarchy, **không hợp lệ** |
| Đổi `Record`/`PermittedSubclasses` của class đã load | Bị giới hạn theo JVMTI |

**Cảnh báo**: một số JVM/tool chuyên biệt có khả năng HotSwap mở rộng, nhưng không coi chúng là hành vi **portable** của `java.lang.instrument.Instrumentation.redefineClasses` trên JVM tiêu chuẩn. Khi cần hot reload toàn schema, phải đánh giá giải pháp riêng thay vì ngầm dựa vào redefinition chuẩn.

## 9. Một lượt redefine nhiều class: nguyên tử của thao tác, không phải transaction nghiệp vụ

`Instrumentation.redefineClasses(ClassDefinition...)` nhận **nhiều `ClassDefinition`** trong một lần gọi để có thể thay các class phụ thuộc nhau cùng lúc:

~~~java
inst.redefineClasses(
        new ClassDefinition(ServiceA.class, bytesForA),
        new ClassDefinition(ServiceB.class, bytesForB));
~~~

Đây là **mã minh họa**, yêu cầu `Instrumentation inst`, hai `Class<?>` và mảng bytes đã được chuẩn bị. Nếu một class file cuối không hợp lệ hoặc thao tác thất bại, contract quy định **không class nào trong lượt gọi đó được redefine thành công**. Điều đó hữu ích khi cần cập nhật logic liên quan tới nhiều class.

Nhưng không hiểu sai thành một distributed/business transaction:

- Các request đã chạy một phần trước thao tác vẫn có thể giữ **active frames cũ**.
- Dữ liệu trong database, cache hoặc heap **không rollback** chỉ vì redefinition thành công hoặc thất bại.
- Code trong transformer, logger hoặc agent có thể đã có side effects riêng trong quá trình xử lý.
- Những method mới được gọi **sau** khi cài class bytes có thể thay state theo logic mới, trong khi request cũ vẫn hoàn tất logic cũ.

Đối với sửa logic có giao thức nhiều bước, có thể cần cơ chế **quiescence**, versioning hoặc compatibility windows ở mức ứng dụng. JVM chỉ bảo đảm các ngữ nghĩa đã được quy định cho việc cập nhật định nghĩa class.

## 10. Phân biệt “state được giữ” với “state tương thích code mới”

Giả sử v1 lưu số tiền theo đơn vị **đồng**, v2 lại giải thích cùng field `amount` là **nghìn đồng**. JVM giữ field bit-for-bit nhưng ý nghĩa nghiệp vụ đã khác. Đây là nguy cơ thực tế khi sửa logic trên existing objects.

| Loại trạng thái | JVM bảo toàn điều gì? | Điều application phải tự bảo đảm |
| --- | --- | --- |
| Primitive instance fields | Giá trị lưu trong instance hiện có | Code mới diễn giải giá trị cũ đúng nghĩa |
| Reference instance fields | Tham chiếu hiện có và object graph vẫn tồn tại | Không giả định graph đã migration |
| Static mutable fields | Giá trị đang giữ tại thời điểm redefine | Đồng bộ hóa, visibility và invariant của state mới |
| Object locks / đang đồng bộ | Object identity vẫn là object hiện có | Code mới không tự làm mất deadlock/lock-ordering cũ |
| Active method frames | Tiếp tục phiên bản bytecode đã vào | Code mới tương thích tương tác giữa frame cũ và mới |
| Constructor side effects | Không chạy lại cho existing objects | Không giả định mọi object đã được khởi tạo theo constructor v2 |
| Class initializer side effects | Không chạy lại chỉ do redefine | Không dựa vào `<clinit>` v2 để migrate config hoặc đăng ký service |

Sự bất biến của **state tại thời điểm redefine** không loại bỏ tác động của garbage collector, threads khác hoặc các lệnh gán bình thường. Ví dụ, nếu một thread khác ghi field cùng lúc, kết quả state theo Java Memory Model phụ thuộc chương trình; redefinition không tự tạo atomic snapshot của mọi field đối với code ứng dụng.

### State nằm ngoài fields thì sao?

Object có thể giữ tài nguyên ngoài JVM heap như file descriptor, network connection, native handle hoặc session trong hệ thống khác. Redefinition **không tự đóng/mở lại** các tài nguyên đó và không bảo đảm chúng thích nghi với thuật toán v2. Cũng không tự đổi state của database, message queue, transaction hay scheduler. Một hot fix an toàn phải xét cả state ngoại vi nếu method body mới tương tác với chúng theo cách khác.

## 11. Khi nào còn thấy bytecode cũ?

Có ba nguyên nhân khác nhau thường bị gộp:

1. **Active stack frame**: method đã vào trước redefine tiếp tục bytecode cũ, đúng contract.
2. **Không redefine đúng class**: target `Class<?>` thuộc loader khác class bạn quan sát; class name có thể giống nhưng identity khác.
3. **Redefine thất bại**: thiếu capability, class không modifiable, class bytes không hợp lệ hoặc thay đổi cấu trúc bị cấm; method body mới chưa được cài.

Vì vậy cần kiểm tra chính xác:

~~~text
1. JVM/agent hỗ trợ redefine?
2. Đúng Class<?> của class loader đang dùng?
3. Class đó modifiable?
4. File .class thay thế có đúng binary name và cấu trúc?
5. redefineClasses(...) đã trả về thành công?
6. Lời gọi đang quan sát là ACTIVE FRAME cũ hay NEW INVOCATION?
7. New code có làm thay state sau lúc redefine không?
~~~

Một log “redefine requested” hoặc “agent attached” không đủ chứng minh bytes đã được cài. Tránh dựa hoàn toàn vào đọc source files trên đĩa: JVM có thể đã load version khác hoặc class có thể được biến đổi thêm bởi transformers khác.

## 12. Ảnh hưởng tới reflection, proxy, cache và class loader

Redefinition **không phải class unload/reload**, vì vậy identity của target class và các existing objects vẫn giữ. Nhưng cần phân biệt **điều được hợp đồng bảo đảm** với các chi tiết reflection/caching mà một framework triển khai riêng:

- `obj.getClass() == savedClass` vẫn đúng trong tình huống redefinition chuẩn của chính class đó.
- Các reference trong `List<LiveCounter>`, field khác, dependency injection container vẫn trỏ tới object cũ.
- Method handles, reflection objects, compiled call sites hoặc JIT optimization có thể được JVM/runtime quản lý và thích nghi theo cơ chế riêng; không lập luận rằng một cache metadata của thư viện bên thứ ba **chắc chắn** được làm mới chỉ vì redefine.
- Một framework tự cache kết quả phân tích bytecode, annotation hoặc method body có thể cần invalidation riêng, tùy thiết kế. Class-file attributes có thể được cập nhật trong redefinition, nhưng cache ngoài JVM không tự có hợp đồng như vậy.
- Nếu một plugin cố nạp lại cùng binary name dưới một class loader khác, đó là **new class identity**, không phải sửa identity cũ; chuyện cast/visibility phải xem theo class loader boundary.

Khi kiểm thử instrumentation có nhiều class loader, xác định target bằng **object `Class<?>` thực sự** và loader của nó, không chỉ bằng chuỗi class name. Cũng cần tránh vô tình redefine bản copy của class từ test loader thay vì bản production loader đang phục vụ request.

## 13. Lỗi và quy trình chẩn đoán

| Lỗi/hiện tượng | Giải thích đúng hướng | Cách xử lý |
| --- | --- | --- |
| `isRedefineClassesSupported() == false` | JVM/agent thiếu capability | Kiểm tra manifest và JVM implementation |
| `isModifiableClass(target) == false` | Class đích không cho redefine/retransform | Chọn target khác, không thử ép primitive/array |
| `UnmodifiableClassException` | Một target không thể sửa | Kiểm tra từng `Class<?>` trước khi gọi |
| `UnsupportedOperationException` | Có thể thiếu capability hoặc thay schema bị cấm | So sánh cấu trúc class old/new và capability |
| `NoClassDefFoundError` trong redefine | Tên class file không khớp tên target | Đảm bảo binary name/class loader mục tiêu đúng |
| `ClassFormatError` | Bytes class không hợp lệ | Kiểm tra build/transformer output và công cụ verify |
| `UnsupportedClassVersionError` | Class-file version không được JVM hỗ trợ | Biên dịch đúng target release |
| `VerifyError` / `LinkageError` | Bytecode/linkage có vấn đề | Kiểm tra instructions, stack maps, references |
| Method mới đã dùng nhưng static value vẫn cũ | **Đúng contract**: static fields không reset | Di trú state bằng logic ứng dụng riêng nếu thực sự cần |
| Không thấy `clinit=patched` | **Đúng contract**: không chạy lại initializer | Không dùng log này để suy luận redefine thất bại |
| Một thread vẫn trả kết quả method cũ | Có thể đang có **active frame** phiên bản cũ | Phân biệt frame đang chạy với lời gọi mới |
| Object cũ vẫn là cùng object | **Đúng contract** | Dùng `==` để khẳng định identity |
| Class mới từ loader khác không cast được | Khác runtime class identity | Phân biệt redefinition với class loading mới |
| App logic đổi state sau redefinition | Method v2 thực thi có thể gán state | Kiểm tra code mới, không coi đó là reset tự động |

Khi gặp lỗi, **không retry lặp vô hạn** với cùng bytes và cùng cấu hình. Hãy log rõ capability, binary class name, class loader, kích thước/hash class bytes, danh sách thay đổi cấu trúc và nguyên nhân ngoại lệ. Không log raw bytecode của ứng dụng vào hệ thống telemetry production nếu không có yêu cầu và cơ chế bảo vệ phù hợp.

## 14. Những kiểm thử phải có trước khi dùng redefinition trong production

Một checklist hữu ích cho agent sửa method body runtime:

1. **Same class identity**: lưu `Class<?>` trước/sau và assert `==`.
2. **Same existing object identity**: giữ reference instance và assert `==`.
3. **Instance fields**: assert giá trị các primitive và reference fields không đổi **ngay sau redefine**.
4. **Static fields**: gán giá trị có chủ đích trước redefine rồi assert vẫn giữ nguyên.
5. **No rerun of initialization**: đo log/bộ đếm `<clinit>`; không xuất hiện side effects lần hai.
6. **No constructor replay**: existing object không được chạy lại constructor hoặc tăng constructor-count.
7. **Existing object, new invocation**: gọi method đã sửa trên instance cũ và assert hành vi v2.
8. **New object**: tạo instance sau redefine; kiểm tra constructor/hành vi mới đúng kỳ vọng.
9. **Active frame**: dùng latch để giữ một frame v1, redefine, rồi giải phóng và xác nhận nó hoàn tất v1.
10. **Multiple threads**: chạy song song những method khác nhau để tìm invariant bị vi phạm do coexistence frame cũ/mới.
11. **Schema rejection**: cố tình thêm field hoặc đổi signature trong môi trường kiểm thử và xác nhận JVM từ chối, không nhầm với thành công.
12. **Failed redefinition**: cung cấp bytes lỗi cho một class trong batch; xác nhận không class nào trong batch được cập nhật và hệ thống xử lý lỗi rõ ràng.
13. **ClassLoader identity**: nếu có custom loaders, xác minh redefinition áp dụng đúng class object.
14. **Transformer pipeline**: khi có nhiều agents, xác minh class bytes cuối được chấp nhận sau mọi transform.
15. **Business state compatibility**: thử code mới trên instance có state v1 đặc thù, không chỉ object tạo mới.

**Mẹo quan trọng:** so sánh thông tin **ngay sau khi lời gọi redefine trả về**, trước khi cho phép code v2 thay đổi dữ liệu, để phân biệt “JVM giữ nguyên state” với “ứng dụng đã tự cập nhật state bằng method mới”.

## 15. Bài tập và đáp án

**Câu 1.** Có `UserSession s` đã được lưu trong cache trước redefine. Redefine `UserSession` có tự tạo object `s` mới và thay reference trong cache không?

**Câu 2.** `Config.shared` đang là 42. File class mới chứa initializer `shared = 999`. Redefine thành công sau khi class đã khởi tạo. Giá trị của field ngay sau thao tác là gì, nếu không có thread khác ghi?

**Câu 3.** Một thread đã vào method `calculate()` phiên bản v1 và đang chờ latch. JVM redefine thành công `calculate()` thành v2. Khi thread được đánh thức, nó tiếp tục body nào? Một lời gọi `calculate()` mới thì sao?

**Câu 4.** Dùng `URLClassLoader` mới nạp file `com.demo.Account.class` v2 và tạo instance v2. Điều này có làm những instance `Account` do class loader cũ tạo ra chuyển sang class mới không?

**Câu 5.** Trong demo, `existing.getValue()` sau redefine vẫn trả 7, nhưng `existing.compute()` sau redefine trả 1007. Đây có phải mâu thuẫn không?

**Câu 6.** Agent tạo class bytes mới bằng `javac` và thêm field `int retryCount;`. File class hợp lệ. Có đồng nghĩa `redefineClasses` phải chấp nhận không?

**Câu 7.** Vì sao `isModifiableClass(MyClass.class) == true` **chưa đủ** để gọi redefine thành công?

**Câu 8.** Hai class A và B được truyền trong **một** lời gọi `redefineClasses(A, B)`. Nếu B có thay đổi schema bị cấm, JVM có được phép chỉ áp dụng A và bỏ B không?

**Câu 9.** Code v2 thay `void update()` bằng body mới có lệnh `value += 100`. Sau redefine, field `value` ban đầu là 7; sau lần gọi `update()` mới, nó thành 107. Có mâu thuẫn với “instance state được bảo toàn” không?

**Câu 10.** Một method `static int getFlag()` trả một `static final int` đã được compile-time inline ở caller khác. Chỉ redefine class chứa constant có bảo đảm caller cũ đọc giá trị mới không?

**Câu 11.** Tại sao trong bộ kiểm thử cần dùng `==` khi xác minh object identity thay vì chỉ dùng `equals()` hoặc `identityHashCode`?

**Câu 12.** Một active frame v1 gọi một method khác `helper()` sau khi redefinition đã hoàn tất. Lời gọi `helper()` đó có nhất thiết dùng code v1 không?

### Đáp án

1. **Không.** Instance hiện có không bị tạo lại và cache vẫn trỏ tới object cũ.
2. **42**. Redefinition không tự chạy lại `<clinit>` và không reset static state đã có.
3. Active frame tiếp tục **v1**; new invocation sử dụng **v2**.
4. **Không.** Class loader mới tạo runtime class identity khác; đó không phải redefinition của class cũ.
5. **Không.** Field vẫn là 7, nhưng method body mới tính `7+1000`; chính là state cũ đi cùng logic mới.
6. **Không.** Thêm field đổi cấu trúc class, thường bị cấm bởi JVM TI RedefineClasses.
7. Còn cần `isRedefineClassesSupported()`, manifest, class bytes hợp lệ, đúng class identity và thay đổi cấu trúc được hỗ trợ.
8. **Không.** Theo contract, nếu lời gọi redefine thất bại thì không class nào trong cùng lượt được redefine thành công.
9. **Không.** JVM giữ field **tại thời điểm redefine**, nhưng một lời gọi method v2 **sau đó** có quyền thay đổi field theo logic của nó.
10. **Không.** Compile-time constant có thể đã được inline trong bytecode caller; static initializer cũng không chạy lại.
11. `equals()` có thể trả true cho hai objects khác nhau; identity hash có thể trùng. `==` kiểm tra đúng reference identity.
12. **Không.** Frame v1 đang chạy code cũ, nhưng invocation mới tới `helper()` tuân theo định nghĩa method hiện hành; có thể dùng v2.

## 16. Kết luận

Redefinition **thay executable definition**, không thay **danh tính class hoặc existing objects**. Các field hiện có vẫn giữ giá trị ở thời điểm thao tác, static initializer không chạy lại, constructor không chạy lại cho object cũ. Một active frame tiếp tục code của phiên bản trước, trong khi new invocations dùng method code đã redefine. Đó là cơ sở kỹ thuật để hot fix và instrumentation runtime, đồng thời cũng là lý do phải kiểm tra **tính tương thích state giữa v1 và v2**, các giới hạn schema và hành vi nhiều thread.

Để ghi nhớ, hãy tách rõ: **class identity không đổi; object identity không đổi; immediate state không reset; method body cho lời gọi mới có thể đổi; active frames vẫn theo body cũ**.

## 17. Tài liệu kỹ thuật chính thức

- [Java SE 21 — Instrumentation.redefineClasses](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineClasses(java.lang.instrument.ClassDefinition...)): quy định về instance, static state, initializer, active frames, lỗi và atomicity.
- [Java SE 21 — ClassDefinition](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): cách kết hợp class identity với bytes thay thế.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): khai báo manifest `Can-Redefine-Classes` và `premain` của Java agent.
- [Java SE 21 — JVM Tool Interface, Redefine Classes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RedefineClasses): chi tiết active methods, existing instances, static fields và giới hạn class structure.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): cách transformers có thể biến đổi bytes trước khi được cài vào JVM.
- [Java Language Specification 21 — §12.4, Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4): thời điểm class initialization và ý nghĩa static initialization.
