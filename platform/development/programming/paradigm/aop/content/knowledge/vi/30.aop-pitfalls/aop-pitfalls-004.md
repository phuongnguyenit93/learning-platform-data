# Gọi proceed sai số lần hoặc sai thời điểm trong AOP

## 1. Bài toán và mục tiêu học tập

Trong **Aspect-Oriented Programming (AOP)**, **around advice** có thể quyết định có tiếp tục xử lý một join point hay không. Với cú pháp **AspectJ code style**, `proceed(...)` chuyển quyền điều khiển tới advice có độ ưu tiên thấp hơn hoặc computation gốc nếu không còn advice ở phía trong. Một lỗi nhỏ ở lệnh này có thể làm toàn bộ nghiệp vụ đổi nghĩa:

- **Thiếu `proceed()`:** một thao tác đáng lẽ được thực hiện bị bỏ qua, caller nhận kết quả thay thế hoặc phần xử lý bên trong không chạy.
- **Thừa `proceed()`:** cùng một computation có thể chạy nhiều lần, tạo side effect lặp, gửi request trùng, tính tiền nhiều lần, ghi log/metric nhiều lần.
- **`proceed()` đặt sai thời điểm:** validation xảy ra sau hành động nguy hiểm; khóa bị lấy quá muộn; metric “thành công” được ghi trước khi biết kết quả; cleanup không chạy khi có exception.

Không có quy tắc “mọi advice luôn phải proceed đúng một lần”: cache hit hoặc từ chối yêu cầu có thể **cố ý không proceed**; retry có thể **cố ý proceed nhiều lần**. Điều quan trọng là mỗi nhánh phải tuân thủ **hợp đồng về số lần thực hiện, thứ tự sự kiện, giá trị trả về, ngoại lệ và side effect** của join point.

Bài này dùng **AspectJ** làm ngôn ngữ minh họa cho các khái niệm AOP cơ bản và nâng cao. Các triển khai AOP khác có thể hỗ trợ tập join point và cú pháp tiếp tục khác nhau. Sau bài, bạn sẽ phân tích được luồng around/proceed, thiết kế đúng timing, kiểm tra retry/idempotency, nhận diện precedence và tạo kiểm thử có bằng chứng.

## 2. `proceed()` thực sự làm gì?

Cho một method:

```java
public String calculate() {
    return "done";
}
```

Một around advice AspectJ có thể bao quanh execution join point:

```aspectj
String around(): execution(String demo.Task.calculate()) {
    System.out.println("before");
    String result = proceed();
    System.out.println("after");
    return result;
}
```

Đây là snippet cần class `demo.Task` và aspect bao ngoài để biên dịch. Nếu chuỗi advice không chặn execution, trình tự là:

```text
caller
  → around: "before"
      → proceed()
          → advice phía trong (nếu có)
              → thân calculate()
          ← kết quả hoặc exception
  → around: "after" (chỉ khi proceed trả về bình thường)
  → caller
```

Trong AspectJ, `proceed()` **không mặc nhiên là một lời gọi Java trực tiếp tới method gốc**. Nó chuyển sang advice có precedence thấp hơn và sau đó mới tới computation thực, trừ khi advice phía trong quyết định ngừng. Một around advice phía ngoài có thể gọi `proceed` đúng một lần, nhưng advice phía trong gọi hai lần; phần thân method vẫn có thể chạy hai lần.

Nếu `proceed()` ném exception, các câu lệnh phía sau nó trong cùng `try` sẽ bị bỏ qua. Phần `catch`/`finally` tương ứng vẫn tuân theo quy tắc Java. Không nên dùng việc xuất hiện một log trong advice như bằng chứng đầy đủ về số lần chạy computation.

### So sánh với các advice khác

| Loại advice | Ý nghĩa | Quan hệ với `proceed` |
| --- | --- | --- |
| `before` | Chạy trước computation ở join point | Không tự kiểm soát continuation bằng `proceed`. |
| `after returning` | Chạy khi phần xử lý bên trong trả về bình thường | Không tương đương mọi lệnh “sau `proceed`”, vì `proceed` có thể ném lỗi. |
| `after throwing` | Chạy khi phần bên trong ném exception thích hợp | Có thể quan sát lỗi dù outer around về sau trả fallback, tùy precedence. |
| `after` | Chạy khi xử lý tiếp theo hoàn tất hoặc throw | Thích hợp khi chỉ cần kết thúc/cleanup. |
| `around` | Quyết định có tiếp tục, số lần tiếp tục và có thay đổi giá trị/exception không | Có quyền điều khiển mạnh nhất, nên đòi hỏi test chặt. |

Chỉ cần log “trước” hoặc “sau” thường có thể dùng before/after advice, giúp tránh các lỗi quản lý continuation không cần thiết.

## 3. Không gọi, gọi một lần và gọi nhiều lần

### 3.1. 0 lần: short-circuit hay lỗi?

```aspectj
String around(): execution(String demo.Cacheable.load()) {
    return "cached-value";
}
```

Advice này trả về mà không gọi `proceed`. Nếu đó là kết quả cache hợp lệ theo hợp đồng, hành vi có thể đúng. Nhưng nếu `load()` cần cập nhật trạng thái hoặc chứa kiểm tra bắt buộc, short-circuit khiến phần việc ấy bị bỏ qua. Advice phía trong có precedence thấp hơn cũng có thể bị bỏ qua. Phải định nghĩa rõ những thao tác nào **được phép** không xảy ra ở cache hit.

### 3.2. 1 lần: đường xử lý thông thường

```aspectj
String around(): execution(String demo.Cacheable.load()) {
    String result = proceed();
    return result;
}
```

Nếu không có tầng advice phía trong nào nhân bản execution, thân method chạy một lần. Gọi `proceed` một lần thường phù hợp với validation, tracing và đo thời gian trên thao tác vốn cần thực hiện đúng một lần.

### 3.3. 2 lần: không phải “đọc lại kết quả”

```aspectj
String around(): execution(String demo.Cacheable.load()) {
    String first = proceed();
    String second = proceed();
    return first + "|" + second;
}
```

Hai lệnh có thể khiến computation phía trong chạy hai lần. Kết quả có thể khác nhau nếu method tăng counter, đọc trạng thái biến đổi hoặc gọi dịch vụ ngoài. Nếu chỉ muốn dùng cùng kết quả hai lần, phải lưu biến sau **một** `proceed`:

```aspectj
String around(): execution(String demo.Cacheable.load()) {
    String once = proceed();
    return once + "|" + once;
}
```

Đặc biệt nguy hiểm khi method thực hiện `createOrder()`, `withdraw()`, ghi file, phát sự kiện hoặc gửi email. Thất bại của lần thứ hai không tự đảo ngược side effect đã thành công của lần thứ nhất.

## 4. Ví dụ AspectJ hoàn chỉnh, chạy được trên JDK 17+

Ví dụ sau có một class lưu counter và một aspect điều khiển lần lượt **0, 1, 2 lần proceed** cùng đường exception. Dùng AspectJ code style (tệp `.aj`), không cần framework ứng dụng.

Cấu trúc:

```text
demo/
  Counter.java
  Driver.java
  ProceedControl.aj
```

**Tệp `demo/Counter.java`**

```java
package demo;

public class Counter {
    private int calls;

    public String skip() {
        calls++;
        System.out.println("body skip count=" + calls);
        return "skip-" + calls;
    }

    public String once() {
        calls++;
        System.out.println("body once count=" + calls);
        return "once-" + calls;
    }

    public String twice() {
        calls++;
        System.out.println("body twice count=" + calls);
        return "twice-" + calls;
    }

    public String fail() {
        calls++;
        System.out.println("body fail count=" + calls);
        throw new IllegalStateException("boom");
    }

    public int count() {
        return calls;
    }
}
```

**Tệp `demo/Driver.java`**

```java
package demo;

public class Driver {
    public static void main(String[] args) {
        Counter counter = new Counter();
        System.out.println("skip=" + counter.skip());
        System.out.println("once=" + counter.once());
        System.out.println("twice=" + counter.twice());

        try {
            counter.fail();
        } catch (IllegalStateException ex) {
            System.out.println("main caught " + ex.getMessage());
        }

        System.out.println("count=" + counter.count());
    }
}
```

**Tệp `demo/ProceedControl.aj`**

```aspectj
package demo;

public aspect ProceedControl {
    String around(): execution(String demo.Counter.skip()) {
        System.out.println("around skip: no proceed");
        return "cached";
    }

    String around(): execution(String demo.Counter.once()) {
        System.out.println("around once: before");
        String result = proceed();
        System.out.println("around once: after");
        return result;
    }

    String around(): execution(String demo.Counter.twice()) {
        System.out.println("around twice: first");
        String first = proceed();
        System.out.println("around twice: second");
        String second = proceed();
        System.out.println("around twice: finish");
        return first + "|" + second;
    }

    String around(): execution(String demo.Counter.fail()) {
        System.out.println("around fail: before");
        try {
            return proceed();
        } catch (IllegalStateException ex) {
            System.out.println("around fail: caught " + ex.getMessage());
            throw ex;
        } finally {
            System.out.println("around fail: finally");
        }
    }
}
```

Dùng `ajc` hỗ trợ Java 17 và thư viện `aspectjrt.jar` tương ứng. Ví dụ lệnh cho Unix-like shell, với `ASPECTJ_HOME` là thư mục AspectJ và `ajc` có trong `PATH`:

```bash
ajc -17 -classpath "$ASPECTJ_HOME/lib/aspectjrt.jar" -d out \
  demo/Counter.java demo/Driver.java demo/ProceedControl.aj
java -cp "out:$ASPECTJ_HOME/lib/aspectjrt.jar" demo.Driver
```

Trên Windows, classpath dùng dấu `;` và cú pháp biến môi trường thay đổi theo shell. Lệnh `javac` thuần túy không biên dịch trực tiếp tệp AspectJ `.aj`.

**Stdout xác định của chương trình:**

```text
around skip: no proceed
skip=cached
around once: before
body once count=1
around once: after
once=once-1
around twice: first
body twice count=2
around twice: second
body twice count=3
around twice: finish
twice=twice-2|twice-3
around fail: before
body fail count=4
around fail: caught boom
around fail: finally
main caught boom
count=4
```

Giải thích:

- `skip()`: body không chạy vì không proceed; count vẫn 0.
- `once()`: proceed một lần, count tăng thành 1; log “after” xuất hiện sau log body.
- `twice()`: mỗi proceed tăng count, lần lượt thành 2 và 3; hai return value khác nhau.
- `fail()`: body tăng count thành 4 rồi throw; advice log trong catch, ném lại exception và thực hiện finally; caller bắt được “boom”.
- `count()` không bị pointcut nào chọn, trả 4; đây là kiểm chứng nội bộ về số lần method body thực sự được chạy.

Nếu chạy lại cùng nguồn nghiệp vụ nhưng không dệt aspect, kết quả khác: `skip` cũng chạy body, `twice` chỉ chạy một lần. Vì thế việc kiểm thử phải thực hiện với bytecode **đã dệt**.

## 5. Sai thời điểm: xác thực đặt sau side effect

Điều kiện đầu vào phải được kiểm tra **trước khi** kích hoạt computation cần bảo vệ. Snippet dưới đây cố ý sai:

```aspectj
String around(String id):
        execution(String demo.Repository.fetch(String)) && args(id) {
    String result = proceed(id);
    if (id == null || id.isBlank()) {
        throw new IllegalArgumentException("invalid id");
    }
    return result;
}
```

Đây là ví dụ minh họa cần class `Repository`; nếu `fetch` đã truy cập mạng hoặc ghi audit, side effect đã xảy ra trước khi validation fail. Throw ở cuối không xóa được những thao tác đó.

Thứ tự hợp lý:

```aspectj
String around(String id):
        execution(String demo.Repository.fetch(String)) && args(id) {
    if (id == null || id.isBlank()) {
        throw new IllegalArgumentException("invalid id");
    }
    return proceed(id);
}
```

Trong trường hợp này, **không gọi proceed khi input sai là chủ đích**. Nếu validation là quy tắc bảo vệ quan trọng, cần kiểm thử rằng pointcut thật sự được weave đúng mọi entry point; không xem advice là bảo đảm duy nhất khi có đường gọi không được instrument.

## 6. Sai thời điểm: lock, context và resource

Nếu muốn thân method chạy **trong một khóa**, thứ tự sau không có tác dụng bảo vệ:

```text
proceed()
lock.lock()
lock.unlock()
```

Thân method đã chạy xong trước khi khóa được lấy. Cần bao quanh phép tính:

```java
lock.lock();
try {
    return proceed();
} finally {
    lock.unlock();
}
```

Đây là **snippet bên trong around advice**, cần khai báo `lock` và return type tương thích mới biên dịch; không phải class Java độc lập. `finally` bảo đảm release kể cả khi `proceed()` throw. Vẫn phải kiểm tra nguy cơ deadlock, thứ tự lấy nhiều lock và reentrancy nếu method gọi lại chính nó.

Tương tự với tracing/security/correlation context: thiết lập context trước proceed, restore context cũ trong finally sau khi proceed kết thúc. Không đặt context vào thread local sau proceed rồi kết luận computation đã chạy với context đó.

Khi cleanup cũng có thể throw, cần chính sách giữ lỗi gốc (chẳng hạn suppressed exceptions hoặc exception handling thích hợp). Không cho lỗi cleanup vô tình che mất nguyên nhân thất bại ban đầu nếu hợp đồng cần giữ nó.

## 7. Sai thời điểm: đo thời gian và log thành công

**Đo đồng bộ đúng phần computation bên trong:**

```aspectj
String around(): execution(String demo.Service.read()) {
    long started = System.nanoTime();
    try {
        return proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        System.out.println("elapsedNanos=" + elapsed);
    }
}
```

Snippet cần `demo.Service.read()` và aspect hoàn chỉnh. `System.nanoTime()` đo **khoảng thời gian trôi qua**, không phải thời điểm lịch. `finally` được chạy cả khi proceed throw. Tuy nhiên việc in stdout trên đường nóng có thể lấn át chi phí method thực tế; dùng cách tổng hợp metric hiệu quả hơn khi cần benchmark.

**Đánh dấu thành công quá sớm:**

```aspectj
String around(): execution(String demo.Service.save()) {
    System.out.println("save succeeded");
    return proceed();
}
```

Đây là log **trước thao tác**; nếu method throw, log sai. Success log phải nằm **sau một `proceed()` đã trả về bình thường**. Failure log có thể ở catch phù hợp; không nuốt exception ngoài chính sách.

Không nên đưa log “after” chỉ vào sau lệnh proceed nếu mục tiêu là audit mọi kết thúc: khi exception xảy ra, code đó không chạy. Dùng finally hoặc advice after thích hợp.

## 8. Exception, return và finally

Một bẫy Java ảnh hưởng trực tiếp tới around advice:

```java
try {
    return proceed();
} finally {
    return fallback;
}
```

Snippet yêu cầu biến `fallback`, hợp đồng return type và một around advice bao ngoài; **không phải code Java độc lập**. Trong Java, `return` từ finally **lấn át** cả return ở try lẫn exception phát sinh trong try. Vì thế caller có thể thấy fallback dù method gốc thất bại. Tương tự, exception trong finally có thể che exception của `proceed`.

Mẫu cần dùng khi chỉ cleanup:

```java
Resource resource = acquire();
try {
    return proceed();
} finally {
    release(resource);
}
```

Đây là pseudocode Java minh họa, không có class `Resource`/hàm `acquire` cụ thể. Không thêm return vào finally; quản lý lỗi cleanup theo policy.

### Catch thay đổi hợp đồng

```aspectj
String around(): execution(String demo.Remote.fetch()) {
    try {
        return proceed();
    } catch (RuntimeException ex) {
        return "";
    }
}
```

Nếu caller cần biết truy vấn thất bại để retry, trả chuỗi rỗng có thể **nuốt lỗi** và gây xử lý sai ở nơi khác. Fallback chỉ nên dùng khi hợp đồng thực sự cho phép và phân biệt được kết quả hợp lệ với trạng thái lỗi.

Khi có `after throwing` ở chuỗi precedence thấp hơn, nó có thể đã chạy trước lúc outer around catch exception. Ngược lại, nếu outer around hoàn toàn không proceed, advice sâu hơn có thể không chạy. Đừng suy “catch đã nuốt mọi after throwing” nếu chưa biết chuỗi advice và thứ tự ưu tiên.

## 9. Truyền tham số vào `proceed(...)`

AspectJ code style cho phép thay giá trị được bind qua pointcut:

```aspectj
String around(String text):
        execution(String demo.Echo.echo(String)) && args(text) {
    String normalized = text.trim();
    return proceed(normalized);
}
```

Đây là snippet cần `demo.Echo.echo(String)`. Nếu thân method trả `"[" + text + "]"` và đầu vào là `"  hi  "`, kết quả của nhánh này có thể là `"[hi]"` vì around cung cấp giá trị mới khi tiếp tục.

Cần đặc biệt phân biệt:

- Với **AspectJ code style**, arguments của `proceed(...)` tương ứng những tham số hình thức/binding của around advice, **không mặc nhiên là danh sách toàn bộ tham số của method gốc**.
- Với **AspectJ annotation style**, phương thức `ProceedingJoinPoint.proceed(Object[])` có quy tắc sắp xếp tham số **khác**: khi bind `this`/`target` chúng có vị trí đặc thù, sau đó là các đối số join point theo thứ tự gốc. Không sao chép mảng theo thứ tự formals của code style một cách máy móc.
- Đổi binding sai kiểu có thể gây `ClassCastException` hoặc giá trị truyền xuống computation không đúng dự kiến.
- Khi chỉ gán lại biến local mà không truyền giá trị mới bằng `proceed(...)` phù hợp, không thể kết luận args phía trong đã đổi.
- Việc thay tham số còn có thể ảnh hưởng advice phía trong về validation, logging, identity và authorization; phải đảm bảo điều đó nằm trong hợp đồng.

Đừng coi `proceed(Object[])` là một lời gọi method tùy ý với bao nhiêu tham số cũng được.

## 10. Retry bằng nhiều `proceed()`: điều kiện cần

Một chính sách retry hợp lệ phải xác định rõ:

1. **Loại lỗi retry được:** timeout nhất thời, failure tạm thời theo nghiệp vụ, không phải mọi exception.
2. **Số lần tối đa:** ví dụ `maxAttempts=2` nghĩa là tổng số lần gọi phần trong tối đa hai, bao gồm attempt đầu.
3. **Idempotency/deduplication:** lần thử đầu có thể đã gây side effect dù trả lỗi; retry không được tạo tác động kép ngoài hợp đồng.
4. **Cleanup giữa các attempt:** mỗi lần thử có thể cần resource/connection/context mới; đừng dùng lại trạng thái đã hỏng.
5. **Cancel/interrupt/backoff:** thời gian chờ và interrupt phải được xử lý theo chính sách, nhất là trên thread pool.
6. **Báo lỗi cuối:** khi hết lượt retry, truyền exception cuối hoặc kết quả thay thế hợp đồng; không giả vờ thành công.
7. **Metrics:** phân biệt số *attempts* với số *logical operations*.

Snippet sau chỉ để minh họa hình thức retry tối đa hai lần, **không chạy độc lập nếu chưa có** `demo.RemoteReader.read()` và một aspect:

```aspectj
String around(): execution(String demo.RemoteReader.read()) {
    RuntimeException last = null;
    for (int attempt = 1; attempt <= 2; attempt++) {
        try {
            return proceed();
        } catch (IllegalStateException ex) {
            last = ex;
        }
    }
    throw last;
}
```

Nhánh retry trên chỉ dành cho `IllegalStateException`, không có nghĩa mọi lỗi loại này thật sự nên retry. Lỗi loại khác sẽ đi ra ngay. Nếu attempt đầu có side effect rồi throw, attempt sau có thể gây side effect lần thứ hai. Với lệnh ghi tiền hoặc tạo đơn hàng, phải có **idempotency key được hệ thống đích thực thi**, hoặc thiết kế nghiệp vụ phù hợp, trước khi dùng kiểu retry này.

Ví dụ nguy hiểm là gửi yêu cầu đến dịch vụ ngoài, dịch vụ đã xử lý thành công nhưng kết nối mất trước khi nhận response. Around advice bắt timeout rồi proceed lại; nếu phía đích không deduplicate, kết quả có thể là hai đơn hàng mặc dù caller chỉ gọi một lần.

## 11. Advice precedence: một lệnh ở ngoài, nhiều lần ở trong

Giả sử around A có precedence cao hơn around B, cả hai match cùng execution join point:

```text
caller
  → A around
       → A.proceed() (một lần)
            → B around
                 → B.proceed() (lần 1)
                      → method body
                 → B.proceed() (lần 2)
                      → method body
       ← A tiếp tục
```

A chỉ gọi proceed một lần nhưng method body có thể chạy hai lần. Số lượng `proceed()` trong **một** aspect không đủ để suy số body invocations khi có advice khác.

Với AspectJ, thứ tự giữa các aspect có thể được xác định bằng `declare precedence` hoặc các quy tắc khác liên quan tới kế thừa; nếu không xác định được precedence, không nên suy thứ tự từ tên file hay classpath. Một outer around không proceed có thể chặn các advice precedence thấp hơn. Một advice ở lớp trong còn có thể dùng around return fallback, thay đổi exception hoặc tự gọi proceed lặp.

**Cách kiểm chứng:** đặt counter ở ba tầng (outer around entry, inner around entry, method body), chạy một lời gọi cố định và đo riêng. Cần ghi cả join point kind/signature để tránh đếm hai join point khác nhau như một.

## 12. Nhầm `call` với `execution`

```aspectj
call(* demo.Job.process(..))
execution(* demo.Job.process(..))
```

Hai pointcut này chọn **khác loại join point**:

- `call` quan sát vị trí gọi method (call site); cần call site đó nằm trong phạm vi được weave.
- `execution` quan sát lúc method body bắt đầu; cần class chứa thân method được weave.
- Một lời gọi có thể đi qua cả call advice và execution advice nếu cả hai join point đều được dệt; các around advice thuộc **hai lớp join point** có thể lồng nhau.
- Với reflection, loader hoặc đường dispatch khác nhau, tập join point quan sát được phụ thuộc weaver và phạm vi bytecode đã dệt.

Vì thế hai dòng log “around entered” chưa chứng minh có hai lần `proceed`. Có thể là hai advice, hoặc một call join point cùng một execution join point. Ghi `thisJoinPointStaticPart.getKind()` và chữ ký từ `getSignature()` khi điều tra.

### Không gọi method gốc trực tiếp thay `proceed`

Đoạn nguy hiểm:

```aspectj
String around(demo.Job job):
        execution(String demo.Job.process()) && this(job) {
    return job.process();
}
```

Đây là snippet cần class `Job`; với execution advice đúng trên method ấy, `job.process()` có thể kích hoạt lại chính advice và tạo đệ quy vô hạn. Nó **không tương đương** `proceed()`. Muốn tiếp tục computation hiện tại, dùng cú pháp `proceed(...)` theo binding tương ứng.

Ngược lại, một method gốc **tự đệ quy** có thể tạo nhiều execution join point hợp lệ dù mỗi frame quanh chỉ proceed một lần. Phải phân biệt recurrence của nghiệp vụ và continuation bị gọi thừa trong một frame.

## 13. Sai thời điểm với bất đồng bộ

Một method có thể trả `CompletionStage<T>` hoặc future ngay, rồi công việc hoàn tất sau đó:

```text
t0: around bắt đầu
t1: proceed() trả một CompletionStage chưa complete
t2: around trả stage cho caller
t3: tác vụ bất đồng bộ hoàn tất
```

Nếu ghi “operation completed” ở `t2` thì đó chỉ là **completion của việc trả stage**, không phải completion của tác vụ ở `t3`. Đo thời gian quanh proceed cho **submission/return latency**; muốn đo **end-to-end completion** phải gắn observer vào completion theo API phù hợp, xử lý đúng exception/cancellation/context và quyết định có thay đổi stage trả cho caller hay không.

Không tùy tiện lưu một continuation và gọi `proceed` trễ trong callback/thread khác. Với API đồng bộ, caller cần return value hoặc exception theo thời gian gốc; chuyển việc tiếp tục sang thread khác có thể thay đổi hoàn toàn contract, khóa, context thread và thứ tự advice. Chuyển từ synchronous sang async là quyết định thiết kế API, không chỉ là di chuyển một dòng `proceed`.

## 14. Lỗi về return type, exception và side effect

Around advice có quyền trả kết quả thay thế nên phải giữ tính tương thích:

- Trả `null` khi caller cần primitive có thể gây `NullPointerException` qua unboxing.
- Trả kiểu sai có thể gây lỗi runtime/cast hoặc lỗi ngay khi compile.
- Trả default từ catch rộng có thể giấu lỗi gốc và làm mất thông tin retry.
- Một phép transformation trên return value phải xét trường hợp giá trị null.
- Exception checked phải phù hợp contract và giới hạn ngôn ngữ/pointcut, không tự tiện thay exception tùy ý.
- Với multiple proceed, việc “chỉ dùng kết quả lần cuối” **không xóa side effect** của các lần trước.
- Thực thi cleanup trong finally là đúng hướng, nhưng `return`/`throw` từ finally có thể che kết quả hoặc nguyên nhân ban đầu.

Phải kiểm tra cả **giá trị caller thấy** lẫn **trạng thái hệ thống sau lời gọi**, đặc biệt cho retry, cache và các thao tác ghi.

## 15. Kiểm thử đúng số lần và đúng thứ tự

Một test cho quanh advice không nên chỉ assert kết quả trả về. Cần quan sát:

| Kịch bản | Body invocations mong đợi | Assertion quan trọng |
| --- | ---: | --- |
| Cache miss | 1 | Giá trị thật, side effect một lần. |
| Cache hit hợp lệ | 0 | Giá trị cache đúng, không bỏ qua bước bắt buộc. |
| Validation fail | 0 | Exception đúng, state không đổi. |
| Success bình thường | 1 | Before/lock/start xảy ra trước body; cleanup/end sau. |
| Computation throw | 1 | Finally chạy; ngoại lệ tới caller đúng hợp đồng. |
| Retry lỗi tạm rồi thành công | Theo maxAttempts, có thể 2 | Attempts và side effect/idempotency đúng. |
| Hai around cùng match | Tùy precedence và proceed của tầng trong | Counter riêng cho advice và body. |
| Đệ quy | Theo số frame nghiệp vụ | Không nhầm recursion với double proceed. |
| Async return | Theo số lần submission hợp đồng | Phân biệt stage được tạo và đã complete. |

Ví dụ `Counter` ở mục 4 có thể dùng các assertion:

1. Sau `skip()`, `count() == 0`.
2. Sau `once()`, `count() == 1` và kết quả `"once-1"`.
3. Sau `twice()`, `count() == 3` và kết quả `"twice-2|twice-3"`.
4. Sau `fail()`, caller nhận `IllegalStateException("boom")` và `count() == 4`.
5. Thứ tự stdout như mục 4: “before” trước body, “after” chỉ khi return bình thường, “finally” ngay cả khi throw.

Trong ứng dụng thực, nên dùng bộ đếm ở **thân method** hoặc hệ thống thực hiện side effect; một counter chỉ nằm trong advice ngoài không chứng minh method body đã chạy bao nhiêu lần. Test cần chạy trên bytecode đã được weaving, với pointcut và precedence thực tế.

## 16. Quy trình chẩn đoán nhanh

1. **Xác định hợp đồng:** khi nào body phải chạy 0, 1 hoặc nhiều lần? Những nhánh cache/reject/retry nào được phép?
2. **Ghi join point thật:** loại `call`/`execution`, signature, class được dệt và đường gọi. Loại trừ chuyện một method bị quan sát tại hai join point.
3. **Vẽ chuỗi precedence:** outer/inner advice, vị trí `proceed()` của từng tầng, và nhánh return/throw.
4. **Đánh dấu các nhánh điều kiện:** `if/return/catch/finally/loop`, có nhánh nào thiếu proceed, chạy thừa hoặc nuốt lỗi?
5. **Đếm thân computation:** tăng counter ngay trong method body để tách lỗi advice entry khỏi double execution.
6. **Kiểm tra thứ tự bảo vệ:** validation và acquire lock trước proceed; result processing sau proceed thành công; cleanup trong finally.
7. **Phân tích idempotency:** nếu có retry, lần trước đã commit side effect chưa? Có deduplication thực sự không?
8. **Xét asynchronous boundary:** caller đang nhận kết quả cuối hay mới nhận future? Measurement và success log đang ở thời điểm nào?
9. **Sửa đúng nguyên nhân:** gọi proceed đúng số lần, đổi điểm đặt logic, giới hạn retry hoặc dùng before/after advice nếu không cần điều khiển continuation.
10. **Chạy hồi quy:** assert count, order, return, exception và side effect cho nhánh hợp lệ lẫn không hợp lệ.

Mẫu ghi lại bằng chứng:

```text
Join point: execution(String demo.Counter.twice())
Hợp đồng: thân phương thức chạy một lần
Around entries: 1
Proceed invocations: 2
Body entries: 2
State trước: 1
State sau: 3
Return: twice-2|twice-3
Nguyên nhân: proceed thứ hai tái thực thi computation
Sửa: lưu String result = proceed() rồi dùng lại result
Test: state chỉ tăng một đơn vị, không side effect lặp
```

## 17. Checklist phòng ngừa

- [ ] Around advice thật sự cần kiểm soát continuation; nếu chỉ log trước/sau, đã cân nhắc before/after.
- [ ] Số lần `proceed` trên từng nhánh được mô tả rõ (0, 1 hoặc N).
- [ ] Short-circuit trả kết quả thay thế hợp lệ và không bỏ các bước bắt buộc.
- [ ] Không gọi `proceed` lần hai chỉ để đọc lại kết quả cũ.
- [ ] Validation/context/lock/resource được thiết lập trước proceed khi cần bảo vệ computation.
- [ ] Cleanup/restore/end timing chạy trong finally ở đúng phạm vi.
- [ ] Không return từ finally để che lỗi của proceed.
- [ ] Catch không đổi loại lỗi hoặc fallback ngoài hợp đồng.
- [ ] Retry có bound, lỗi retry được định nghĩa, idempotency được kiểm chứng.
- [ ] Cách binding tham số `proceed(...)` phù hợp cú pháp AspectJ đang dùng.
- [ ] Đã xem precedence và phân biệt `call` với `execution`.
- [ ] Đã phân biệt completion của future với việc trả future.
- [ ] Test đo trực tiếp body count, thứ tự và side effect trên class đã weave.

**Kết luận:** `proceed()` là lệnh **tiếp tục phép tính bên trong join point**, không phải hàm đọc lại kết quả. Đặt đúng một lệnh trong một nhánh success bình thường giúp giữ hợp đồng một lần thực thi; bỏ qua hoặc lặp chỉ hợp lệ khi nghiệp vụ cho phép. Thứ tự của validation, lock, metric, exception và cleanup so với proceed quyết định tính đúng đắn của toàn bộ advice.

## Tài liệu tham khảo

- [AspectJ Programming Guide — Advice Semantics](https://eclipse.dev/aspectj/doc/released/progguide/semantics-advice.html): around advice, `proceed`, lời gọi tới advice có precedence thấp hơn.
- [AspectJ Programming Guide — Language Semantics](https://eclipse.dev/aspectj/doc/latest/progguide/semantics.html): tham số `proceed(...)` trong code style, thay giá trị và kiểu trả về.
- [AspectJ — Pointcuts and Advice](https://eclipse.dev/aspectj/doc/released/adk15notebook/ataspectj-pcadvice.html): khác biệt `ProceedingJoinPoint.proceed(Object[])` với code style.
- [Java SE 17 JLS — Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html): `try/catch/finally`, return và abrupt completion.
