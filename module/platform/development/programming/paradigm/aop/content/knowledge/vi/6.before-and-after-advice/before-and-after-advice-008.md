# Giới hạn thay đổi dữ liệu theo loại advice và công cụ trong AOP

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, *advice* là hành vi bổ sung được áp dụng tại những **join point** mà một *pointcut* lựa chọn. Người học thường biết các loại advice như “trước”, “sau khi thành công”, “sau khi lỗi”, “sau khi kết thúc” và “bao quanh”. Nhưng một câu hỏi quan trọng hơn là:

**Advice có thể đọc, chỉnh sửa hoặc thay thế những dữ liệu nào của lời gọi phương thức, và việc đó có thật sự thay đổi hành vi mà người gọi quan sát không?**

Câu trả lời phụ thuộc vào **loại advice**, **thời điểm nó chạy**, **khả năng truy cập ngữ cảnh**, **hợp đồng của công cụ AOP** và **cách weaving/interception được triển khai**. Không thể mặc định mọi before/after advice đều được thay tham số, trả kết quả mới hoặc nuốt ngoại lệ; cũng không thể khẳng định mọi hệ thống AOP đều cung cấp một around advice có toàn quyền can thiệp như nhau.

> **Phạm vi:** Bài này trình bày AOP cơ bản và nâng cao nói chung. Các tên before, after-returning, after-throwing, after/finally và around là khái niệm; cú pháp khai báo, quy tắc binding và quyền thay đổi dữ liệu cụ thể khác nhau giữa các công cụ.

## 1. Định vị advice trong mô hình AOP

Một **join point** là điểm trong quá trình chạy nơi cơ chế AOP có thể chèn hành vi, chẳng hạn một lần gọi hay thực thi phương thức. **Pointcut** lựa chọn các điểm đó theo loại, tên, chữ ký, ngữ cảnh hoặc các điều kiện được hỗ trợ. **Advice** là phần xử lý thực thi tại những điểm được chọn. **Aspect** thường đóng gói pointcut và advice phục vụ một mối quan tâm cắt ngang, chẳng hạn logging, tracing, audit, quan sát hiệu năng hoặc chính sách truy cập.

Với lời gọi đồng bộ thông thường, luồng khái niệm:

```text
Caller
  |
  |  before advice
  v
Target.method(arguments)
  |
  +---- trả về kết quả ------> after-returning advice
  |
  +---- ném ngoại lệ --------> after-throwing advice
  |
  +---- kết thúc theo cả hai nhánh ---> after/finally advice
  |
Caller nhận kết quả hoặc ngoại lệ
```

**Around advice** có thể bao phủ cả vùng này, tùy cơ chế:

```text
around: trước proceed
   |
   +---- gọi tiếp target/chuỗi advice (proceed)
   |           |
   |           +---- return hoặc throw
   |
around: có thể quan sát, thay đổi kết quả/ngoại lệ, hoặc quyết định không proceed
   |
Caller
```

Sơ đồ nhằm mô tả quyền kiểm soát khái niệm, **không phải lời hứa** rằng mọi AOP engine có cùng các kiểu advice, thứ tự hoặc ngôn ngữ pointcut.

### Mấu chốt: quan sát khác với thay thế

Giả sử hàm đích nhận `String name` và trả về `String greeting`. Một advice có thể:

1. **Quan sát** đối số `name`, không làm thay đổi nó.
2. **Sửa một object mutable** được tham chiếu qua đối số, làm thay đổi trạng thái mà target có thể thấy.
3. **Thay đối số thực sự truyền tới target** (ví dụ chuyển `" a "` thành `"a"`) nếu advice và API chuyển tiếp hỗ trợ.
4. **Quan sát** giá trị trả về.
5. **Thay giá trị mà caller nhận** nếu vị trí advice có quyền trả kết quả thay thế.
6. **Quan sát, truyền tiếp, chuyển đổi hoặc nuốt ngoại lệ**, nếu hợp đồng advice cho phép.

Các hành vi trên **không tương đương**. Đặc biệt, thay một biến local trong advice không tự động sửa biến local của caller hay vùng tham số đã được truyền theo giá trị của Java.

## 2. Bảng so sánh quyền can thiệp theo loại advice

| Loại advice | Khi nào chạy? | Thường làm tốt | Điều **không nên mặc định** |
| --- | --- | --- | --- |
| **Before** | Trước khi vào điểm xử lý đích | Validate, log đầu vào, khởi tạo ngữ cảnh | Trả một giá trị thay thế kết quả method; thay hẳn các argument của lời gọi theo mặc định |
| **After-returning** | Khi thao tác kết thúc **bình thường** | Log kết quả, metric thành công, đọc return value | Thay return value cho caller chỉ bằng cách gán lại tham số advice |
| **After-throwing** | Khi thao tác kết thúc bằng **ngoại lệ** | Audit lỗi, tracing, cleanup tùy contract | Tự biến ngoại lệ thành kết quả thành công hoặc nuốt lỗi trong mọi DSL |
| **After/finally** | Sau thao tác trên cả nhánh bình thường và bất thường, theo semantics engine | Cleanup, đóng scope, metric kết thúc | Luôn nhận đầy đủ return/throw context hoặc chủ động thay outcome |
| **Around** | Bao quanh bước chuyển tiếp được hỗ trợ | Điều khiển `proceed`, biến đổi arguments/return, recovery, retry | Có thể can thiệp mọi kiểu join point, mọi method, hoặc sửa tùy ý bất chấp type contract |

Từ **“thường”** quan trọng: bảng mô tả mô hình phổ biến, không xác nhận một năng lực phổ quát. Có hệ thống chỉ hỗ trợ interceptor kiểu before/after; có hệ thống cho phép around chèn vào bytecode; có hệ thống cho phép binding dữ liệu nhưng không cho đổi outcome; có hệ thống đưa ra API `proceed` với những ràng buộc riêng.

### Quy tắc thiết kế nhanh

**Nếu cần quan sát:** ưu tiên advice ít quyền nhất, ví dụ before hoặc after thích hợp. **Nếu cần thay đổi cách target được gọi hay kết quả caller thấy:** xem xét around hoặc cơ chế tương đương đã được công cụ cam kết hỗ trợ. **Nếu thao tác là bất biến nghiệp vụ hoặc bảo mật bắt buộc:** bảo vệ thêm tại ranh giới đáng tin cậy; không phụ thuộc độc nhất vào một đường can thiệp có thể bị bypass.

## 3. Before advice: được làm gì trước khi phương thức chạy?

Một **before advice** chạy trước phần công việc được chọn. Đây là vị trí thích hợp để:

- Ghi log tên thao tác, mã tương quan, tham số đã được ẩn dữ liệu nhạy cảm.
- Tạo mốc đo thời gian hoặc thiết lập scope quan sát.
- Kiểm tra các điều kiện tiền đề được phép kiểm tra tại boundary.
- Từ chối thao tác bằng ngoại lệ nếu đó là hợp đồng được cho phép.
- Khởi tạo tài nguyên hoặc ngữ cảnh cần được cleanup tương ứng.

Ví dụ, **mã giả**:

```text
before save(document):
    log("begin", document.id)
    ensureValid(document)
```

Đây không phải cú pháp Java hay pointcut chuẩn. Nếu `ensureValid` ném lỗi trước khi target bắt đầu, target có thể không chạy. Tuy nhiên, quyền **chặn** này không biến before advice thành một cơ chế tùy ý **trả về kết quả mới**.

### 3.1. Vì sao before thường không thay được return value?

Tại thời điểm before chạy, target chưa trả kết quả nào. Một hàm before có tham số `String input` hoặc `Method method` không tự có hợp đồng “giá trị tôi `return` là kết quả thay thế của target”. Nhiều API before có kiểu trả về `void` hoặc bỏ qua return value của advice.

Nếu muốn bỏ qua target và trả một giá trị thay thế cho caller, cần **điểm kiểm soát luồng** như around hoặc interception hook có return contract cụ thể. Một before advice ném ngoại lệ có thể ngăn target chạy, nhưng đó là **kết thúc bất thường**, không phải “trả kết quả thành công tùy ý”.

### 3.2. Sửa object đối số: có thể, nhưng đó là hành vi khác

Giả sử target nhận một `MutableRequest`. Before advice nhận tham chiếu tới cùng object rồi gọi `request.setStatus(...)`. Nếu target sau đó đọc object ấy, nó **có thể thấy trạng thái mới**. Đây là **mutation trên object chia sẻ**, không chứng minh before advice có quyền **thay instance đối số** từ A sang B.

Trong Java, tham số luôn được **truyền theo giá trị**: đối với object, giá trị được sao chép là **reference**. Việc advice gán `request = new MutableRequest(...)` cho biến local của chính advice không khiến caller hay target tự động nhận reference mới.

Thậm chí khi mutation có hiệu lực, hành vi ấy có thể nguy hiểm: thay object trước validation, gây race giữa thread, phá invariant hoặc khiến log khác với dữ liệu gốc. Tốt hơn nên giữ before advice mang tính quan sát, trừ khi mutation là contract rõ ràng và được kiểm thử.

## 4. After-returning: quan sát kết quả không đồng nghĩa thay kết quả

Một **after-returning advice** chạy sau khi phương thức đích **kết thúc thành công**, trước khi quyền điều khiển tiếp tục theo cơ chế AOP.

Ví dụ:

```text
result = target.fetch(id)
afterReturning(result):
    metric("fetch.success")
    logMetadata(result)
```

Điểm này thích hợp để ghi metric thành công, log thông tin kết quả không nhạy cảm hoặc cập nhật quan sát độc lập. Tuy nhiên, nếu advice chỉ nhận bản sao của tham chiếu kết quả rồi gán:

```java
// Mã minh họa tại bên trong advice, không phải chương trình độc lập.
String value = "original";
value = "replacement";
```

thì thao tác gán vào `value` **không thay** một kết quả mà caller sẽ nhận ở bên ngoài. Việc thay return value đòi hỏi API advice có **hợp đồng thay thế giá trị trả về**; không suy luận từ việc có biến `returnValue` trong tham số advice.

### 4.1. Mutable return value là một ngoại lệ dễ gây nhầm lẫn

Nếu target trả về một `List` mutable và after-returning advice được cấp **cùng tham chiếu** rồi gọi `list.clear()`, caller nhận cùng object nhưng thấy dữ liệu đã bị thay. Đó là **mutation trạng thái**, không phải thay reference của kết quả trả về.

Tách biệt ba khả năng:

- **Read-only:** chỉ quan sát list.
- **In-place mutation:** sửa các phần tử của chính list; caller có thể quan sát thay đổi.
- **Replacement:** trả một list object hoàn toàn khác cho caller; cần contract hỗ trợ đổi outcome.

Một công cụ AOP có thể cho phép bước thứ nhất, có thể không cấm bước thứ hai về mặt Java nếu đối tượng mutable, nhưng không nhất thiết hỗ trợ bước thứ ba từ after-returning.

### 4.2. Hành vi khi target ném lỗi

Nếu target kết thúc bằng ngoại lệ, **after-returning** theo đúng nghĩa “returning bình thường” **không phải nơi quan sát lần thất bại đó**. Hãy dùng after-throwing hoặc cleanup dạng finally nếu phù hợp. Không gộp hai loại sự kiện vì chúng thể hiện hai outcome khác nhau.

## 5. After-throwing: biết lỗi, nhưng được đổi lỗi đến đâu?

**After-throwing advice** gắn với trường hợp thao tác kết thúc bất thường. Nó phù hợp để:

- Ghi loại lỗi, mã lỗi và ngữ cảnh an toàn.
- Đếm metric thất bại hoặc gắn trạng thái vào trace.
- Audit trường hợp từ chối/không thành công.
- Thực hiện dọn dẹp theo contract nếu không có ranh giới finally khác.

Ví dụ khái niệm:

```text
try:
    target.process()
catch error:
    afterThrowing(error)
    throw error
```

Mục tiêu thông thường là **truyền tiếp lỗi gốc**. Một số hệ thống cho phép advice ném một ngoại lệ mới, làm thay outcome; nhưng nhiều API after-throwing **không** cho phép “trả một giá trị bình thường” thay cho ngoại lệ. Phải xem hợp đồng của công cụ.

### 5.1. Không thể đồng nhất thay exception với recovery

Có ba hành vi riêng:

1. **Observe + rethrow:** log rồi giữ nguyên loại/lỗi.
2. **Map exception:** chuyển `IllegalArgumentException` thành loại lỗi khác nếu cơ chế cho phép; thay đổi contract ngoại lệ caller thấy.
3. **Recover:** ngăn lỗi lan ra và trả kết quả thành công/fallback; thường cần cơ chế bao quanh có thể điều khiển luồng.

Một after-throwing advice có thể tự ném lỗi mới, nhưng điều đó chưa chứng minh nó có thể **khôi phục và trả giá trị bình thường** như around. Cần phân biệt “thay throwable” với “chuyển outcome từ throw thành return”.

### 5.2. Exception từ chính advice

Advice cũng là code và có thể thất bại. Nếu logger hoặc audit sink ném lỗi, ngoại lệ mới có thể che mất ngoại lệ nghiệp vụ tùy cách engine xử lý. Thiết kế phải xác định rõ *logging thất bại có được làm lời gọi thất bại hay không?*, *nên giữ lỗi nào làm nguyên nhân chính?*, và *có dùng suppressed exceptions hay báo lỗi phụ không?*.

Không viết advice bắt `Throwable` rồi nuốt mọi thứ chỉ để “hệ thống không lỗi”. Điều đó che giấu cả lỗi nghiêm trọng. Khi cần giữ nguyên exception, phải truyền tiếp đúng đối tượng lỗi theo contract.

## 6. After/finally: cleanup cho cả hai nhánh

Một **after/finally advice** theo mô hình thông thường chạy khi rời join point ở cả nhánh **return** và **throw**. Nó rất có giá trị để:

- Đóng scope tracing/timing.
- Khôi phục ngữ cảnh trước đó.
- Giải phóng tài nguyên được advice sở hữu.
- Ghi metric thời gian hoàn tất, bất kể outcome.

Dạng logic:

```java
// Mã minh họa cách Java try/finally hoạt động.
long start = System.nanoTime();
try {
    work();
} finally {
    long elapsed = System.nanoTime() - start;
    recordDuration(elapsed);
}
```

Đoạn này không phải tệp Java chạy độc lập. Nó minh họa **finally chạy cả khi work trả về và khi work ném lỗi**. Tuy nhiên, không phải every “after” của mọi DSL đều có semantic finally; tên API có thể phân biệt after-returning, after-throwing, after-finally theo cách riêng.

### 6.1. Vì sao không nên đổi outcome trong finally?

Một khối `finally` thông thường dùng để cleanup, không để trả kết quả khác hoặc che lỗi. Trong Java, một `return` hoặc một exception mới từ `finally` có thể ghi đè luồng kết thúc trước đó. Trong AOP, nếu cleanup advice ném lỗi, outcome của caller có thể thay đổi tương tự theo cơ chế đang dùng.

Do vậy:

- Không chủ ý `return` kết quả nghiệp vụ từ cleanup.
- Đảm bảo cleanup an toàn và có chính sách xử lý lỗi phụ.
- Với context scope, ghi nhớ giá trị cũ và **restore trong finally** ngay cả khi target ném lỗi.
- Kiểm thử không chỉ nhánh thành công mà cả thất bại và trường hợp cleanup ném lỗi.

**Một after/finally advice không mặc nhiên có quyền truy cập hoặc thay đổi return value**, dù nó biết một lượt gọi đã kết thúc.

## 7. Around advice: điểm kiểm soát luồng mạnh nhất khi được hỗ trợ

**Around advice** có thể chạy **trước và sau** thao tác được chọn. Với một API `proceed` hay cơ chế tương đương, around quyết định khi nào/bao nhiêu lần gọi tiếp, cách đưa đối số vào bước tiếp theo, và có xử lý kết quả/ngoại lệ sau đó hay không.

```text
around(arguments):
    prepared = normalize(arguments)
    try:
        result = proceed(prepared)
        return transform(result)
    catch knownError:
        return fallback
```

Đây là **pseudocode**, không phải cú pháp universal. Một số engine hỗ trợ `proceed(newArguments)`; số khác chỉ cung cấp `proceed()`, hoặc hạn chế số/lọai đối số có thể thay. Có engine giới hạn around cho method execution/proxy invocation; có engine hỗ trợ nhiều loại join point hơn.

### 7.1. Những khả năng thường gặp

Nếu engine hỗ trợ đầy đủ, around có thể:

- **Quan sát** hoặc **sửa đối số** trước khi gọi tiếp.
- **Không gọi tiếp**, qua đó bỏ qua target và trả giá trị mặc định.
- **Gọi tiếp đúng một lần** rồi biến đổi kết quả trước khi trả cho caller.
- **Gọi tiếp nhiều lần**, ví dụ retry có điều kiện.
- **Bắt ngoại lệ** và giữ nguyên, chuyển đổi hoặc phục hồi.
- **Đo thời gian** của toàn bộ chuỗi advice/target mà nó bao ngoài.

Mỗi khả năng đều phải tuân theo **type contract** và **semantic contract**. Nếu method trả `int`, một around advice trả `String` có thể gây lỗi kiểu khi runtime unbox/cast. Nếu method trả `void`, return value tùy ý thường không có ý nghĩa cho caller.

### 7.2. “Có thể” không có nghĩa “nên”

Around quá mạnh có thể che mất hành vi nghiệp vụ: bỏ qua một thao tác cần chạy, thực thi thanh toán hai lần, nuốt lỗi giao dịch hoặc sửa kết quả không còn đúng contract. Chỉ dùng mức can thiệp này khi concern thực sự cần thay luồng và có test bảo vệ.

**Một before + một after** thường dễ đọc hơn một around phức tạp nếu nhu cầu chỉ là log trước và sau. Không chọn around chỉ vì muốn viết một advice bao trùm mọi logic.

## 8. Ví dụ Java 17+ chạy được: before/after chỉ quan sát, around đổi argument và outcome

Ví dụ sau sử dụng hai **dynamic proxy** nối nhau để mô phỏng hai nhóm trách nhiệm:

1. **Proxy quan sát** in “before”, “after-returning”, “after-throwing”, “after-finally” rồi **không đổi** argument, return value hay exception.
2. **Proxy ngoài** mô phỏng **around advice**, trim đối số trước khi gọi tiếp, bọc kết quả bình thường và phục hồi một loại ngoại lệ được nhận diện.

Ví dụ chạy được với **Java 17+**, không cần thư viện AOP. Nó minh họa contract interception của proxy và **không phải DSL pointcut đầy đủ**. Đừng suy luận mọi AOP framework có đúng tập quyền như hai proxy này.

Lưu toàn bộ mã vào `AdviceDataLimitsDemo.java` bằng UTF-8:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Locale;

public class AdviceDataLimitsDemo {
    public interface Operation {
        String process(String value);
    }

    public static final class OperationImpl implements Operation {
        @Override
        public String process(String value) {
            System.out.println("target " + value);
            if ("fail".equals(value)) {
                throw new IllegalArgumentException("blocked");
            }
            return value.toUpperCase(Locale.ROOT);
        }
    }

    // Gọi target qua reflection nhưng chuyển tiếp lỗi gốc.
    static Object invoke(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    // Mô phỏng before, after-returning, after-throwing, after/finally.
    static Operation withObservation(Operation target) {
        return (Operation) Proxy.newProxyInstance(
                Operation.class.getClassLoader(),
                new Class<?>[] { Operation.class },
                (proxy, method, args) -> {
                    System.out.println("before " + args[0]);
                    try {
                        Object result = invoke(method, target, args);
                        System.out.println("after-return " + result);
                        return result; // Giữ nguyên kết quả.
                    } catch (Throwable error) {
                        System.out.println(
                                "after-throw "
                                + error.getClass().getSimpleName()
                                + ":" + error.getMessage());
                        throw error; // Giữ nguyên ngoại lệ.
                    } finally {
                        System.out.println("after-finally");
                    }
                });
    }

    // Mô phỏng around: đổi argument, đổi kết quả, có thể recover.
    static Operation withAround(Operation next) {
        return (Operation) Proxy.newProxyInstance(
                Operation.class.getClassLoader(),
                new Class<?>[] { Operation.class },
                (proxy, method, args) -> {
                    String prepared = ((String) args[0]).trim();
                    System.out.println("around-enter " + prepared);
                    try {
                        String result = (String) invoke(
                                method, next, new Object[] { prepared });
                        System.out.println("around-map " + result);
                        return "<<" + result + ">>";
                    } catch (IllegalArgumentException error) {
                        System.out.println(
                                "around-recover " + error.getMessage());
                        return "RECOVERED";
                    } finally {
                        System.out.println("around-exit");
                    }
                });
    }

    public static void main(String[] args) {
        Operation target = new OperationImpl();
        Operation observed = withObservation(target);
        Operation service = withAround(observed);

        System.out.println("caller " + service.process(" ok "));
        System.out.println("caller " + service.process(" fail "));

        // Bỏ qua cả hai proxy:
        System.out.println("caller-direct " + target.process("plain"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 AdviceDataLimitsDemo.java
java AdviceDataLimitsDemo
```

**Đầu ra chuẩn:**

```text
around-enter ok
before ok
target ok
after-return OK
after-finally
around-map OK
around-exit
caller <<OK>>
around-enter fail
before fail
target fail
after-throw IllegalArgumentException:blocked
after-finally
around-recover blocked
around-exit
caller RECOVERED
target plain
caller-direct PLAIN
```

### 8.1. Đường thành công

`service.process(" ok ")` đi qua **proxy ngoài**, nơi chuỗi được trim thành `"ok"`. Đây là **thay đối số truyền tới bước tiếp theo** bằng cách tạo `new Object[]{prepared}`, không phải “chỉnh biến local trong before”.

Proxy quan sát nhận `"ok"` và in `before ok`. Target nhận đúng `"ok"`, in `target ok` rồi trả `"OK"`. Proxy quan sát in `after-return OK`, trả **nguyên** `"OK"`, và in `after-finally`.

Proxy ngoài nhận `"OK"` và tạo kết quả mới `"<<OK>>"`. Caller vì vậy nhận `"<<OK>>"`, không nhận trực tiếp `"OK"`. **Đây là replacement của return outcome** tại ranh giới around.

### 8.2. Đường thất bại

`service.process(" fail ")` được trim thành `"fail"`. Target in `target fail` rồi ném `IllegalArgumentException("blocked")`. Hàm `invoke` mở lớp bọc `InvocationTargetException` để giữ lỗi gốc.

Proxy quan sát in `after-throw IllegalArgumentException:blocked`, chuyển tiếp cùng lỗi, rồi luôn in `after-finally`. Nó **không trả một giá trị thành công**.

Proxy ngoài bắt `IllegalArgumentException` và quyết định **không truyền lỗi tới caller**, thay bằng chuỗi `"RECOVERED"`. Đây là recovery từ lỗi sang return outcome. Dù vậy, target vẫn đã chạy và thất bại; “caller thấy thành công” **không biến thao tác đã thất bại thành thành công về mặt nghiệp vụ**.

### 8.3. Đường gọi trực tiếp

`target.process("plain")` không đi qua proxy nào nên chỉ có dòng `target plain`. Dù các điều kiện method có thể tương ứng với logic interceptor, **đường gọi thực tế không được weave/intercept** nên advice không chạy. Khả năng thay dữ liệu chỉ tồn tại khi execution path đi qua cơ chế AOP.

### 8.4. Những hạn chế cố ý của demo

- Không có pointcut DSL hay hệ thống weaving tổng quát; handler áp dụng với interface proxy.
- Không minh họa advice cho private/static method, field access, constructor hay self-invocation.
- Việc cast `(String) args[0]` trong around giả định đầu vào không null; code production cần contract hoặc validation rõ ràng.
- Recovery trả `"RECOVERED"` chỉ để minh họa, **không phải một chính sách an toàn mặc định**.
- Không hỗ trợ transaction, retry hay propagation ngữ cảnh tự động.
- Không khẳng định một engine thực tế cho phép khai báo before/after độc lập với chính các quyền của proxy demonstration.

## 9. Thay đổi đối số: thay reference khác với sửa trạng thái

Đây là nguồn nhầm lẫn lớn nhất khi người học thấy advice nhận được mảng argument.

### 9.1. Java truyền theo giá trị

Đối với primitive, Java sao chép giá trị số/boolean. Đối với object, Java sao chép **giá trị của reference**. Vì vậy:

```java
// Hàm minh họa, có thể đặt trong một class.
static void changeLocalReference(String name) {
    name = "new";
}

static void mutateList(java.util.List<String> items) {
    items.add("extra");
}
```

Sau `changeLocalReference(x)`, biến `x` bên caller vẫn giữ reference cũ. Nhưng sau `mutateList(list)`, list caller giữ có thể chứa phần tử mới vì **cùng một object bị thay đổi**.

Nếu advice giữ tham chiếu tới object được truyền vào target, nó có thể làm mutation qua API của object, dù bản thân advice không có quyền **thay argument slot** tại điểm chuyển tiếp. Nếu một API around cho phép cung cấp `newArguments` vào `proceed`, đó lại là quyền khác: **thay giá trị truyền tới bước tiếp theo**.

### 9.2. Đừng suy từ việc sửa Object[] thành sửa lời gọi

Một interceptor có thể nhận `Object[] args`. Việc làm `args[0] = replacement` có thể ảnh hưởng bước chuyển tiếp trong **một implementation cụ thể** nếu nó dùng chính mảng đó để invoke target. Nhưng không thể mặc định mọi API advice chia sẻ cùng mảng, không sao chép hay cho phép thay input. Một số công cụ truyền bản sao hoặc chỉ hỗ trợ đọc. Hãy dùng API chính thức của công cụ để thay argument nếu có.

### 9.3. Ràng buộc kiểu, số lượng và overload

Một method khai báo `calculate(int)` không thể nhận một `String` tùy ý chỉ vì around muốn vậy. Nếu method nhận hai tham số, mảng argument chuyển tiếp phải phù hợp về **số lượng, thứ tự và kiểu**. Với overload, method đã được chọn trước khi around can thiệp có thể không tự đổi sang overload khác sau khi argument bị biến đổi.

Ví dụ Java về overload:

```java
// Hai phương thức thuộc một class minh họa:
void save(String name) { }
void save(Object value) { }
```

Lời gọi `save((Object) "hi")` chọn overload `save(Object)` theo kiểu biểu thức compile-time. Nếu around thay value runtime bằng một `String`, điều đó **không tự bắt JVM chọn lại** overload `save(String)`. Nó vẫn cần chuyển tiếp qua method descriptor được chọn, trừ khi cơ chế AOP cố ý thực hiện một lời gọi khác.

## 10. Thay đổi kết quả: cần giữ hợp đồng phương thức

Khi around có quyền trả kết quả thay thế, giá trị thay thế phải tương thích với kiểu trả về và semantics của API.

| Return contract của target | Điều phải cân nhắc khi thay |
| --- | --- |
| `String` | Có thể trả chuỗi khác nếu contract cho phép; null có hợp lệ không? |
| `int` | Runtime có thể yêu cầu wrapper số phù hợp rồi unbox; trả null hoặc sai loại sẽ lỗi |
| `boolean` | Kết quả thay đổi có thể đảo quyết định nghiệp vụ |
| `void` | Không có kết quả hữu ích để caller tiêu thụ; behavior phụ thuộc API interception |
| `Optional<T>` | Phải giữ invariant của Optional và kiểu giá trị bên trong |
| `CompletableFuture<T>` | Thay chính object future khác với thay kết quả bên trong future sau khi hoàn tất |
| Một object mutable | Có thể đổi reference hoặc mutate trạng thái; hai hành vi có hệ quả khác |

**Tính hợp lệ về kiểu chỉ là mức tối thiểu**. Trả một `String` đúng kiểu vẫn có thể sai nghiệp vụ, ví dụ trả “paid” trong khi giao dịch chưa được thực hiện.

### 10.1. Covariant return và generic type

Một method override có thể khai báo kiểu trả về hẹp hơn kiểu ở lớp cha theo quy tắc Java. Reflection hoặc interceptor làm việc với một method metadata cụ thể phải nắm đúng return contract, không chỉ dựa vào tên method.

Với generics, type erasure có thể khiến runtime chỉ thấy một raw type. Việc cast một `List<String>` có thể thành công ở mức raw `List` nhưng không chứng minh từng phần tử là `String`. Around advice thay kết quả bằng một list sai loại phần tử có thể gây lỗi **muộn hơn ở caller**. Những contract generic cần được kiểm thử ở mức hành vi, không chỉ kiểm tra `instanceof List`.

### 10.2. Null và giá trị mặc định

Nếu một method non-null theo contract, around trả `null` có thể gây lỗi tại caller dù chữ ký Java cho phép reference null. Với primitive return, proxy có thể gặp lỗi khi unbox null. Nếu muốn fallback, phải chọn giá trị phù hợp semantics thay vì trả tùy ý chỉ để không ném exception.

## 11. Thay đổi ngoại lệ và tính minh bạch của advice

Ở mức quyền kiểm soát luồng, outcome của một lời gọi có thể mô hình hóa là:

```text
Outcome<T> =
    Return(T value)
    OR
    Throw(Throwable error)
```

Đây là **mô hình khái niệm**, không phải khai báo kiểu Java chuẩn. Một advice quan sát lý tưởng giữ nguyên outcome. Một around advice có thể thay outcome nếu được công cụ cho phép:

```text
Return(x)  -> Return(transform(x))
Throw(e)   -> Throw(map(e))
Throw(e)   -> Return(fallback)
Return(x)  -> Throw(policyError)
```

Bốn chuyển đổi này là bốn quyết định khác nhau. Mỗi chuyển đổi cần contract, test và lý do rõ ràng.

### 11.1. Đừng nuốt lỗi vô điều kiện

Một advice `catch (Exception) { return defaultValue; }` có thể khiến caller tin thao tác đã thành công, dù mục tiêu đã ném lỗi do dữ liệu không hợp lệ, lưu trữ thất bại hoặc một trạng thái bất biến bị phá. Đối với tác vụ có side effect, fallback có thể làm trạng thái hệ thống không nhất quán.

Nếu thực sự cần phục hồi, hãy phân loại lỗi **có thể phục hồi**, giữ lỗi gốc trong telemetry, và phân biệt rõ trạng thái như “đã dùng cache cũ” với “thực thi mới thành công”.

### 11.2. Checked exceptions và API proxy

Trong Java, interceptor dùng reflection thường gặp `InvocationTargetException` bọc lỗi target; cần mở lớp bọc nếu muốn giữ Throwable gốc. Với proxy dựa trên interface, một checked exception không được khai báo thích hợp trong contract interface có thể bị runtime bọc dưới dạng một ngoại lệ proxy cụ thể. Vì vậy không thể tự coi “ném bất kỳ Throwable” là luôn giữ nguyên loại ngoại lệ mà caller thấy ở mọi công cụ.

### 11.3. Phục hồi có ảnh hưởng tới after advice nào?

Một target ném lỗi có thể khiến after-throwing bên trong chạy. Nếu một around bên ngoài **recover** rồi trả giá trị, một advice được gắn **bên ngoài around** có thể quan sát outcome **thành công**. Không có mâu thuẫn: chúng quan sát **các ranh giới khác nhau** trong chuỗi advice. Thứ tự và mức lồng quyết định outcome mà từng advice thấy.

## 12. Thứ tự advice có thể đổi dữ liệu được quan sát

Giả sử ba aspect cùng khớp một method:

- **ValidationAspect:** kiểm tra đầu vào.
- **TransformAspect:** chuẩn hóa đầu vào.
- **AuditAspect:** ghi lại thao tác.

Nếu Validation nằm **ngoài** Transform, nó kiểm tra đầu vào trước khi chuẩn hóa. Nếu Transform nằm ngoài Validation, nó có thể biến đổi argument rồi mới đi vào Validation. Hai thứ tự tạo chính sách khác nhau.

```text
Thứ tự A:
  Validate(raw)
    -> Transform(raw -> normalized)
      -> Target(normalized)

Thứ tự B:
  Transform(raw -> normalized)
    -> Validate(normalized)
      -> Target(normalized)
```

Cả hai sơ đồ chỉ diễn tả nesting khái niệm; khả năng thực tế phụ thuộc API around và precedence của công cụ.

**Pointcut** quyết định *ở đâu* advice áp dụng. **Precedence/ordering** quyết định *lớp nào bên ngoài/lớp nào bên trong* khi nhiều advice cùng khớp. Không nên nhầm việc thay thứ tự với “đổi pointcut”. Thứ tự không được định nghĩa rõ có thể làm log nhận dữ liệu khác kết quả nghiệp vụ, hoặc khiến lỗi bị quan sát như thành công.

### 12.1. Exception và finally khi nhiều lớp lồng nhau

Xét quanh một target:

```text
OuterAround.before
  InnerObservation.before
    Target
  InnerObservation.after-return-or-throw
  InnerObservation.finally
OuterAround.after-or-recover
OuterAround.finally
```

Nếu target ném lỗi, inner có thể ghi “failed”, outer recover rồi trả fallback. Nếu audit cần ghi *kết quả caller thấy*, audit phải được đặt tại ranh giới phản ánh outcome cuối cùng, không nhất thiết sát target. Nếu audit cần ghi *target thực sự đã thất bại*, nó phải quan sát ranh giới bên trong thích hợp.

## 13. Retry: gọi tiếp nhiều lần là thay đổi rất lớn

Một around advice có thể muốn retry bằng cách gọi `proceed` nhiều lần, **nếu công cụ cho phép**. Nhưng điều đó làm phương thức đích có khả năng thực thi **nhiều lần cho một lời gọi của caller**.

```text
Caller gọi transfer() một lần
  AroundRetry:
    proceed #1 -> target ghi dữ liệu rồi ném timeout
    proceed #2 -> target ghi lại cùng dữ liệu
```

Nếu thao tác không idempotent, giá trị đã được ghi ở lần #1 có thể chưa được caller xác nhận, và lần #2 tạo side effect trùng lặp. Retry phải có:

- Danh sách lỗi thực sự có thể retry.
- Giới hạn số lần và tổng thời gian.
- Idempotency key hoặc contract chống lặp phù hợp.
- Timeout/deadline/cancellation nhất quán.
- Chính sách backoff và xử lý kết quả cuối.
- Test đối với “thành công một phần trước khi ném lỗi”.

**Một around advice không tự làm retry an toàn.** Khi concern chỉ là quan sát, tuyệt đối không gọi target nhiều lần chỉ để “thử lại” sau lỗi.

## 14. Quyền thay dữ liệu còn phụ thuộc loại join point

Ví dụ có hai loại join point:

- **Method call:** điểm phát lời gọi ở caller.
- **Method execution:** lúc target bắt đầu thực thi.

Một cơ chế weaving vào **call site** có thể có quyền can thiệp tại phía caller. Một cơ chế weaving vào **execution entry** có thể chỉ nhìn thấy metadata/dữ liệu sau bước lựa chọn method và đánh giá arguments. Thay dữ liệu ở hai vị trí có thể mang ý nghĩa khác nhau.

Ví dụ, đối số là biểu thức có side effect:

```java
// Minh họa:
service.process(buildInput());
```

Nếu `buildInput()` đã chạy và tạo dữ liệu trước khi advice execution bắt đầu, việc advice thay reference đối số **không “hoàn tác” tác dụng phụ của buildInput()**. Tương tự, một advice quanh method execution không nhất thiết can thiệp được vào lỗi xảy ra khi caller đang đánh giá argument trước khi vào target.

**Không mặc định AOP có quyền đảo ngược thời gian thực thi**: advice có thể chọn dữ liệu mới cho bước tiếp theo, nhưng không tự hoàn tác hiệu ứng đã diễn ra ở caller.

## 15. Giới hạn của công cụ: proxy, interception và weaving

Một lời khuyên mạnh về mặt thiết kế vẫn vô dụng nếu đường gọi thực tế không đi qua nơi công cụ áp dụng advice.

| Cơ chế | Vị trí can thiệp thường thấy | Giới hạn cần xem |
| --- | --- | --- |
| **Proxy dựa trên interface** | Lời gọi đi qua object proxy | Không tự bắt trực tiếp target, private/static method hoặc self-invocation trong target |
| **Proxy dựa trên subclass** | Override/intercept những method có thể can thiệp trong subclass | Final/private/static và việc gọi không qua proxy có thể tạo giới hạn |
| **Compile-time weaving** | Bytecode/mã được ghép advice khi biên dịch | Phải build đúng phần mã; khả năng join point tùy engine |
| **Post-compile weaving** | Biến đổi bytecode đã biên dịch | Phải dùng artifact đã weave và tương thích bytecode |
| **Load-time weaving** | Kết hợp khi class được nạp | Class loader, cấu hình, thứ tự nạp và phạm vi instrument ảnh hưởng coverage |
| **Interceptor tại pipeline** | Điểm hook do một nền tảng cung cấp | Có thể chỉ cho phép một số kiểu dữ liệu/hành vi và không phải join point tổng quát |

Một API “before callback” không trở thành around advice chỉ vì được đặt trong class tên Aspect. Ngược lại, một interceptor có khả năng nhận handler bao quanh lời gọi có thể mô phỏng một số hành vi around mà không dùng cú pháp AOP chuyên biệt.

### 15.1. Self-invocation

```java
class OrderService {
    void submit() {
        validate();  // gọi nội bộ qua this
    }

    void validate() { }
}
```

Ở kiểu proxy đứng ngoài target, lời gọi `this.validate()` trong target có thể bỏ qua proxy. Dù pointcut chọn `validate()`, advice không nhất thiết chạy nếu không có đường interception phù hợp.

Với weaving trực tiếp ở mức bytecode, các phương thức nội bộ có thể được nhận diện ở những join point khác, tùy công cụ. Do đó “self-invocation luôn bị bỏ qua” là kết luận quá rộng; đúng hơn phải nói **proxy-based interception có giới hạn đường đi**, còn bytecode weaving có các khả năng khác.

### 15.2. Static, private, final, constructor và native

Không phải mọi cơ chế đều có quyền can thiệp vào những vị trí này. Một số có thể chọn method execution và chèn advice vào bytecode, nhưng cũng có giới hạn theo language/runtime. Constructor, initialization, field access hoặc exception handler có thể là các loại join point khác nếu công cụ hỗ trợ. **Không dùng cùng một bảng quyền thay argument/return cho mọi loại điểm can thiệp** mà không kiểm tra API thực tế.

## 16. Binding đối số và return value: phân biệt dữ liệu đọc với dữ liệu ghi

Một công cụ AOP có thể cấp các biến cho advice, ví dụ đối số, target object, method metadata, return value hoặc Throwable. Câu hỏi cần hỏi là:

1. Dữ liệu này là **bản sao, tham chiếu đến object hay một view bất biến**?
2. Advice có được **đọc** thôi hay được sửa?
3. Nếu sửa, thay đổi đó tác động vào **object** hay **slot argument/return**?
4. Nếu muốn thay slot, phải gọi API đặc biệt như `proceed(arguments)` hay chỉ gán biến?
5. Advice có được quyền **bỏ qua lời gọi tiếp** không?
6. Nếu thất bại, Throwable nào đến caller?
7. Khi nhiều advice cùng áp dụng, advice nào thấy dữ liệu trước và sau biến đổi?

Một biến tên `result` không tự trở thành “handle cho return value của caller”. Việc API cho bind kết quả có thể chỉ nhằm **quan sát**. Tương tự, thấy mảng `arguments` không chứng minh có quyền ghi lại đúng các slot sẽ được target sử dụng.

### 16.1. Một ví dụ sai về cách hiểu reference

```java
// Minh họa cục bộ; không phải một advice hoàn chỉnh.
static void observer(String input) {
    input = input.trim();  // Chỉ đổi biến local input.
}
```

Nếu caller đã có `String raw = " x "` rồi gọi `observer(raw)`, biến `raw` vẫn tham chiếu `" x "`. Muốn target nhận `"x"`, cơ chế điều khiển bước gọi tiếp phải thực sự dùng reference mới tại ranh giới invoke/proceed.

## 17. Async return: after-returning của method không nhất thiết thấy kết quả cuối

Một method có thể trả `CompletableFuture<String>` ngay sau khi lên lịch tác vụ. **After-returning của method** có thể thấy **object future**, không thấy chuỗi `String` sẽ được tính ra sau.

```java
// Minh họa kiểu return, chưa phải chương trình hoàn chỉnh.
java.util.concurrent.CompletableFuture<String> result =
        java.util.concurrent.CompletableFuture.supplyAsync(
                () -> "finished");
```

Những điều khác nhau:

- **Return của method:** một `CompletableFuture<String>`.
- **Completion của future:** thành công với `"finished"`, thất bại với exception hoặc cancellation.
- **After-returning advice:** quan sát future khi method trả về, theo semantics join point.
- **Completion callback:** có thể quan sát outcome cuối cùng khi future hoàn tất, nhưng là cơ chế/điểm xử lý khác.

Nếu around advice thay **object future** bằng future khác, nó có thể thay giao diện kết quả mà caller nhận. Nếu nó muốn biến đổi giá trị bên trong future, có thể cần compose stage mới với `thenApply`/`handle`/`exceptionally` theo hợp đồng API. Việc đó khác với việc gán lại một biến `result` trong after-returning.

Không được mặc định callback chạy trong cùng thread với advice; phải cân nhắc context propagation, lỗi, cancellation và deadline.

## 18. Trạng thái, concurrency và dữ liệu mutable

Ngay cả một advice chỉ dự định “quan sát” cũng có thể gây side effect nếu nó dùng dữ liệu mutable.

### 18.1. Mutate tham số được chia sẻ

Nếu advice gọi setter trên một request object được dùng đồng thời, target có thể thấy giá trị trung gian hoặc race. Nếu cần chuẩn hóa, nên cân nhắc tạo **bản sao bất biến** rồi chuyển nó cho bước tiếp theo qua API cho phép đổi arguments; điều này giảm việc thay trực tiếp object chung, nhưng vẫn phải tuân thủ contract và lifetime của dữ liệu.

### 18.2. Mutate giá trị trả về

Thay đổi collection do target trả về có thể gây lỗi khi caller đang duyệt trên thread khác hoặc khi target giữ cùng collection. Muốn thêm metadata quan sát, không nên chèn field nhạy cảm vào object trả về chỉ để logging dễ hơn.

### 18.3. State của aspect

Nếu một instance aspect/interceptor được chia sẻ qua nhiều thread, trường mutable như `currentArgument` hoặc `lastResult` có thể bị ghi đè chéo. Biến local theo invocation thường an toàn hơn. Với context gắn theo thread, phải truyền và restore đúng khi qua executor/async, không mặc định `ThreadLocal` đi theo tác vụ.

### 18.4. Time-of-check/time-of-use

Một before advice kiểm tra `request.amount`, nhưng giá trị bị thread khác sửa trước khi target sử dụng, có thể dẫn đến **TOCTOU**. AOP không tự tạo tính nguyên tử. Quy tắc nghiệp vụ quan trọng cần thực thi dưới cơ chế dữ liệu/giao dịch/snapshot đáng tin cậy.

## 19. Bảo mật và bất biến nghiệp vụ: advice không phải phép màu

Một **validation aspect** có thể hữu ích để áp dụng quy tắc nhập liệu chung. Nhưng nếu đường gọi trực tiếp target không đi qua advice hoặc nếu có task nội bộ bỏ qua proxy, một **security invariant** chỉ đặt ở aspect có thể bị bỏ lọt.

Cần phân biệt:

- **Chính sách phụ trợ:** log, tracing, metric, audit quan sát.
- **Chính sách bảo vệ bắt buộc:** quyền truy cập, invariant trạng thái, phân quyền dữ liệu, xác thực giao dịch.
- **Chính sách điều khiển luồng:** retry, fallback, caching, circuit breaking.

Các chính sách điều khiển luồng có thể có trong AOP, nhưng phải đáp ứng semantic contract. Quy tắc bảo vệ bắt buộc cần được bảo vệ ở ranh giới mà mọi đường thực thi liên quan đều đi qua, không chỉ ở một proxy dễ bypass.

### Không ghi dữ liệu nhạy cảm khi “quan sát”

Một before advice có quyền đọc arguments không có nghĩa nên ghi toàn bộ object vào log. Dữ liệu có thể chứa mật khẩu, token, địa chỉ, thông tin sức khỏe hoặc nội dung bí mật. Nên chọn các trường an toàn, ẩn danh/ẩn dữ liệu nhạy cảm và giới hạn nhãn metric có cardinality cao.

## 20. Quy trình quyết định loại advice

Khi có yêu cầu mới, hỏi lần lượt:

1. **Chỉ cần chạy logic trước target?** Nếu có, xem before advice. Có cần chặn bằng lỗi không?
2. **Chỉ cần quan sát kết quả thành công?** Xem after-returning. Có cần biết thất bại nữa không?
3. **Chỉ cần quan sát thất bại?** Xem after-throwing. Có muốn truyền nguyên lỗi không?
4. **Cần dọn dẹp bất kể outcome?** Xem after/finally hoặc scope có `try/finally`.
5. **Cần thay đối số thực sự truyền tới target, bỏ qua target, đổi return hoặc recover lỗi?** Xem around hay interception API **được xác nhận có quyền điều khiển đó**.
6. **Có nhiều aspect cùng áp dụng?** Xác định precedence trước khi chọn vị trí quan sát/biến đổi.
7. **Có async hoặc mutable object?** Phân biệt return của method và completion của công việc; phân tích ownership/concurrency.
8. **Có đường bypass cơ chế AOP?** Kiểm tra direct call, self-invocation, reflection, thread/task và proxy coverage.
9. **Việc đổi outcome có an toàn nghiệp vụ không?** Xác minh contract, idempotency, type, error và logging.
10. **Công cụ AOP thực tế hỗ trợ gì?** Đọc đặc tả tool về loại join point, binding, `proceed`, precedence, checked exception và loại return.

### Ma trận lựa chọn nhanh

| Mục tiêu | Lựa chọn thường hợp lý |
| --- | --- |
| Ghi nhận bắt đầu | Before |
| Đếm thành công | After-returning |
| Ghi nhận lỗi gốc | After-throwing |
| Đóng trace scope ở mọi nhánh | After/finally |
| Chuẩn hóa argument **được chuyển tiếp** | Around hoặc hook có argument replacement |
| Bọc result trả về | Around hoặc hook có return replacement |
| Chuyển exception thành fallback | Around hoặc mechanism hỗ trợ recovery |
| Retry | Around có hợp đồng `proceed` và idempotency phù hợp |
| Kiểm tra logic quyền bắt buộc | Boundary đáng tin cậy; AOP chỉ là một lớp bổ sung nếu không đảm bảo coverage |
| Đo completion của future | Completion callback/stage observation, không chỉ after-returning của method |

## 21. Kiểm thử hành vi: không chỉ kiểm tra advice đã chạy

Muốn biết một loại advice thực sự có quyền thay dữ liệu không, phải kiểm thử từ **góc nhìn caller** và **góc nhìn target**.

| Ca kiểm thử | Câu hỏi cần trả lời |
| --- | --- |
| Before đọc argument | Target có nhận nguyên argument không? |
| Before gán lại biến local | Caller/target có bị thay reference không? |
| Before mutate object mutable | Target và caller có thấy mutation không, và có được phép không? |
| After-returning quan sát | Giá trị caller nhận có giữ nguyên không? |
| After-returning cố trả giá trị khác | Công cụ bỏ qua, hỗ trợ hay báo lỗi? |
| After-throwing ghi lỗi | Caller nhận Throwable gốc hay bị thay? |
| After/finally cleanup | Chạy đủ trên success và throw không? |
| Around đổi arguments | Target nhận giá trị mới hay vẫn giá trị cũ? |
| Around đổi result | Caller có nhận đúng kiểu/giá trị mới không? |
| Around recover | Target đã thất bại nhưng caller có nhận fallback đúng contract không? |
| Around không proceed | Target có thực sự không chạy không, side effect nào còn? |
| Around proceed hai lần | Target chạy mấy lần, có side effect trùng không? |
| Nhiều aspect | Thứ tự vào/ra và dữ liệu quan sát có đúng precedence không? |
| Gọi target trực tiếp | Có bypass interceptor/proxy không? |
| Async target | Advice thấy future hay kết quả completion? |
| Exception từ advice | Lỗi chính/ phụ nào tới caller? |
| Chạy đồng thời | Advice có lẫn argument/result giữa requests không? |

Một regression test nên so sánh **input mà target thực sự nhận**, **output/exception caller thực sự thấy** và **số lần target chạy**. Chỉ xác nhận log “advice activated” không chứng minh dữ liệu được thay.

### Phương pháp kiểm thử từng lớp

- **Unit test:** logic advice riêng, phân biệt observer và transformer.
- **Integration test:** đường proxy/weaving thật, thứ tự advice và đường bypass.
- **Contract test:** giá trị trả về, checked/unchecked exception, idempotency, null, generic type và async completion.
- **Concurrency test:** mutable arguments, ThreadLocal/context và cleanup khi exception/cancellation.

Các công cụ AOP khác nhau có thể cho kết quả khác nhau đối với cùng một pseudocode, nên test **trên cơ chế đang triển khai**.

## 22. Những hiểu lầm phổ biến

1. **“Before advice có thể return để bỏ qua target.”** Không mặc định; thường cần around hoặc hook được định nghĩa để thay kết quả.
2. **“Gán biến trong advice sẽ sửa argument của caller.”** Java truyền theo giá trị; gán reference local không thay biến bên ngoài.
3. **“After-returning đổi giá trị bằng cách gán lại result.”** Chỉ đúng nếu tool cấp API thay return, không phải vì có biến result.
4. **“After-throwing luôn phục hồi được lỗi.”** Quan sát/mapping/recovery là các quyền khác nhau.
5. **“After advice luôn giống finally.”** Cần phân biệt after-returning, after-throwing và after/finally theo contract.
6. **“Around luôn chạy target một lần.”** Nó có thể gọi không lần, một lần hoặc nhiều lần nếu API hỗ trợ.
7. **“Đổi argument ở runtime sẽ chọn lại overload Java.”** Overload thường được lựa chọn theo kiểu tĩnh trước đó.
8. **“Return type đúng là đủ an toàn.”** Còn invariant nghiệp vụ, nullability, idempotency và generic contract.
9. **“Aspect quan sát không thể đổi hành vi.”** Logging có thể ném lỗi, latency tăng, hoặc mutate object nếu code viết sai.
10. **“Có pointcut là mọi lời gọi đều được can thiệp.”** Phạm vi proxy/weaving thực tế có thể bỏ sót direct call hoặc self-invocation.
11. **“Around retry không có hại nếu target báo timeout.”** Target có thể đã gây side effect trước khi timeout.
12. **“Advice nào nhìn thấy exception cũng nhìn thấy cùng outcome.”** Around bên ngoài có thể recover lỗi mà advice bên trong vừa quan sát.
13. **“Future trả về là công việc đã xong.”** Method return và asynchronous completion là hai thời điểm khác nhau.
14. **“Mọi công cụ AOP có cùng binding/proceed.”** Cần đối chiếu khả năng cụ thể với mỗi loại advice và join point.

## 23. Bài tập tự luyện

1. Chạy `AdviceDataLimitsDemo.java` và giải thích tại sao `before` thấy `"ok"` chứ không phải `" ok "`.
2. Bỏ `trim()` ở around. Xác định đầu ra và kết quả `process(" fail ")` thay đổi như thế nào; vì sao chuỗi có khoảng trắng không còn bằng `"fail"`?
3. Đổi result wrapper từ `"<<...>>"` thành `"[...]"`. Chỉ ra dòng nào chứng minh **caller** nhận kết quả đã thay chứ không phải target tự trả kết quả đó.
4. Chuyển `before` sang một hàm Java chỉ gán biến local `String value = "changed"`, nhưng không đổi mảng argument dùng để invoke. Target có nhận `"changed"` không? Giải thích.
5. Cho target trả `List<String>` mutable. So sánh việc advice thêm phần tử vào cùng list với việc around trả một list khác.
6. Cho around cố trả `null` từ method có kiểu trả `int` trong một cơ chế proxy. Cần kiểm tra loại lỗi nào và ở ranh giới nào?
7. Viết test xác minh lỗi `IllegalArgumentException("blocked")` được before/after observer truyền tiếp nguyên vẹn khi không có around recovery.
8. Viết test đổi thứ tự observer và transformer, rồi phân tích advice nào thấy dữ liệu gốc, advice nào thấy dữ liệu đã chuẩn hóa.
9. Thiết kế retry cho thao tác lưu trạng thái: nêu giới hạn lần thử, idempotency key, deadline và khả năng side effect trước lỗi.
10. Thêm một method trả `CompletableFuture<String>` và giải thích tại sao after-returning không tự thấy giá trị `String` cuối cùng.
11. Tạo một target chứa `this.internalMethod()`, so sánh gọi qua proxy với lời gọi nội bộ. Điều gì chứng minh giới hạn can thiệp?
12. Viết một bảng quyết định cho từng yêu cầu “quan sát”, “mutation object”, “replace argument”, “replace return”, “recover exception”; chọn loại advice tối thiểu và điều kiện công cụ cần có.

**Tự kiểm tra:** Vì sao mutation trên object khác với thay argument slot? After-returning có mặc nhiên thay được return không? Around có thể đổi outcome theo những cách nào? Nếu around ở ngoài recover lỗi, after-throwing ở trong có còn ghi nhận target thất bại không? Làm sao chứng minh thao tác biến đổi có tác động tới caller, không chỉ tới biến local của advice?

## Kết luận

**Quyền thay dữ liệu không chỉ phụ thuộc việc code được gọi là “advice”, mà phụ thuộc thời điểm chạy, loại advice, dữ liệu được bind và API điều khiển bước tiếp theo.** Before và các after advice thường phù hợp với **quan sát, validate hoặc cleanup**; chúng không mặc định thay argument slot, return value hay biến throw thành return. Around thường có khả năng **điều khiển lời gọi và outcome** rộng hơn, nhưng chỉ trong giới hạn cụ thể của engine, join point, type contract và đường weaving. Thiết kế tốt phải phân biệt **đọc**, **mutation object**, **thay input truyền tiếp**, **thay kết quả** và **thay luồng ngoại lệ**, sau đó kiểm chứng bằng kết quả caller/target thật, không chỉ nhìn log.