# Advice sau khi hoàn tất thành công và xử lý giá trị trả về

## 1. Mục tiêu và vị trí của after-returning advice

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), **advice** là hành vi bổ sung được áp dụng ở một *join point* (điểm có thể can thiệp) được pointcut lựa chọn. **After-returning advice** là loại advice chạy **khi thao tác được quan sát hoàn tất bình thường**, tức không thoát khỏi phạm vi quan sát bằng ngoại lệ. Đây là thời điểm thích hợp để quan sát giá trị trả về, ghi nhận kết quả thành công, thống kê, cập nhật metrics và bổ sung hành vi kỹ thuật mà không làm lẫn vào logic nghiệp vụ.

Ví dụ: phương thức `Catalog.lookup("A7")` trả `"item:A7"`. Khi join point của nó được chọn, một advice sau khi trả về có thể ghi loại kết quả và thời gian phản hồi. Người viết `lookup()` vẫn chỉ cần lo việc tìm mặt hàng, không phải sao chép mã ghi log vào mọi phương thức tương tự.

**Định nghĩa quan trọng:**

> After-returning advice được kích hoạt sau khi join point hoàn tất **bình thường**; nếu có binding kết quả, advice có thể quan sát giá trị trả về theo khả năng của cơ chế AOP.

Từ “thành công” trong tên gọi chỉ nói **thành công về luồng điều khiển tại join point** (normal completion), không tự khẳng định nghiệp vụ đã đạt mục tiêu. Một phương thức trả `false`, `null`, mã trạng thái `NOT_FOUND` hoặc `Result.failure(...)` vẫn là **normal return** nếu nó không ném ngoại lệ. Vì vậy, nếu muốn đo “thành công nghiệp vụ”, advice phải diễn giải thêm hợp đồng kết quả hoặc sử dụng tín hiệu miền thích hợp.

Ngược lại, khi target ném ngoại lệ ra khỏi join point và không có lớp bên trong xử lý rồi trả về bình thường, **after-returning advice gắn ở chính ranh giới đó không chạy**. Tình huống ấy liên quan đến `after-throwing`, `after/finally` hoặc một `around` có nhánh lỗi, tùy cơ chế.

## 2. Phân biệt after returning với những advice dễ nhầm

| Loại advice | Thời điểm/điều kiện kích hoạt | Có kết quả bình thường? | Mục đích phổ biến |
| --- | --- | --- | --- |
| **Before** | Trước khi chuyển điều khiển vào điểm được chọn | Chưa | Ghi bắt đầu, xác thực ngữ cảnh |
| **After returning** | Chỉ sau khi điểm được chọn hoàn tất bình thường | Có thể quan sát nếu cơ chế cung cấp | Audit thành công, kiểm tra/đếm giá trị trả về |
| **After throwing** | Khi điểm được chọn kết thúc bằng ngoại lệ | Không có kết quả trả bình thường của lần đó | Audit thất bại, phân loại ngoại lệ |
| **After / finally** | Khi phạm vi được bao rời đi dù bình thường hoặc lỗi | Không phải lúc nào cũng có kết quả | Cleanup, đo thời gian tổng quát |
| **Around** | Bao quanh lời thực thi, có quyền chuyển tiếp | Có thể nhận và xử lý kết quả/ngoại lệ | Cache, đo thời gian, retry có chủ đích |

Giả sử một join point được chọn chạy theo đường:

~~~text
Caller
  |
  v
[Before] ---> [Target method]
                   |
           +-------+--------+
           |                |
      normal return      throws error
           |                |
           v                v
    [After returning]  [After throwing]
           |                |
           +-------+--------+
                   v
              [After/finally]
                   |
                   v
       Caller nhận kết quả hoặc lỗi
~~~

Sơ đồ **chỉ minh họa những nhánh khái niệm**, không phải đặc tả thứ tự chung cho tất cả công cụ. Khi nhiều aspect cùng áp dụng, thứ tự và cách lồng advice phải tuân theo hợp đồng precedence/weaving của công nghệ đó. Quan trọng nhất là hai nhánh **after returning** và **after throwing** phân biệt theo cách join point kết thúc.

Nếu một phương thức có `try/catch` bên trong, nó có thể ném lỗi rồi **tự bắt** và trả về giá trị dự phòng. Từ bên ngoài ranh giới thực thi phương thức, kết quả cuối vẫn là normal completion. Do đó, after-returning có thể chạy dù đã có ngoại lệ nội bộ. Người thiết kế phải xác định muốn quan sát **kết quả cuối** hay **mọi ngoại lệ từng phát sinh**; đó không phải cùng một yêu cầu.

## 3. Giá trị trả về: khai báo, runtime và binding

### 3.1. Kiểu trả về khai báo khác đối tượng thực tế

Phương thức `Object find()` có thể trả về một `String`, một đối tượng khác hoặc `null`. Chữ ký khai báo `Object`, còn loại đối tượng runtime phụ thuộc từng lần chạy. Nếu một pointcut chọn theo kiểu trả về khai báo, kết quả matching có thể khác với việc advice kiểm tra loại đối tượng trả về thực tế.

Ví dụ:

~~~java
Object result = target.find(); // khai báo Object
if (result instanceof String s) {
    System.out.println("Chuỗi có độ dài " + s.length());
}
~~~

Đây là đoạn **minh họa**, không phải một chương trình chạy riêng vì `target` chưa được định nghĩa. Thông điệp: trong advice, chỉ ép kiểu kết quả sau khi đã xác minh hợp đồng hoặc kiểu thực tế. Không giả định phương thức nào có tên `find` cũng trả `String`.

### 3.2. Giá trị `null` vẫn có thể là normal return

`String lookup("missing")` trả `null` không hề ném ngoại lệ nếu `null` nằm trong hợp đồng trả về. After-returning vẫn có thể chạy. Nếu code advice thực hiện `result.toString()` không có kiểm tra, **chính advice** có thể ném `NullPointerException` và làm caller thất bại dù target hoàn tất bình thường.

Nên dùng cách quan sát an toàn như `String.valueOf(result)` khi chỉ cần nhãn hiển thị, nhưng vẫn phải xem xét dữ liệu nhạy cảm và chi phí `toString()`. Một đối tượng có `toString()` phức tạp hoặc phát sinh lỗi không phù hợp để log tùy tiện.

### 3.3. Phương thức `void` có hoàn tất bình thường hay không?

Có. `void ping()` chạy đến cuối hoặc `return;` mà không ném lỗi là một **normal completion**. After-returning có thể được kích hoạt ở join point ấy nếu cơ chế AOP hỗ trợ loại join point/return type tương ứng. Nhưng **không có giá trị trả về nghiệp vụ** để binding như một đối tượng `String`.

Trong Java Reflection, `Method.invoke()` trả `null` khi target khai báo `void`. Vì vậy, `result == null` trong bộ bao reflection **không đủ** phân biệt giữa “trả tham chiếu `null`” và “target `void`”. Phải xem `method.getReturnType() == void.class` hoặc hợp đồng do AOP engine cung cấp.

### 3.4. Primitive, boxing và generic

Các phương thức trả `int`, `boolean` hoặc `long` cũng hoàn tất bình thường. Nếu một API advice cung cấp mọi kết quả thông qua kiểu `Object`, giá trị primitive có thể được **boxing** thành `Integer`, `Boolean` hoặc `Long`. Đây là chi tiết của adapter/engine, không có nghĩa chữ ký target đã đổi thành wrapper.

Kiểu generic như `List<String>` có thể bị **type erasure** tại runtime. Không suy diễn rằng chỉ nhìn `Object result` đủ chứng minh mọi phần tử đều là `String`. Hãy kiểm tra cách công nghệ bind kết quả và cấu trúc dữ liệu thực tế.

## 4. Quan sát giá trị trả về hay thay thế giá trị trả về?

Đây là khác biệt quan trọng nhất của chủ đề.

**After-returning advice có mục tiêu điển hình là quan sát việc hoàn tất bình thường.** Nhiều mô hình AOP tách loại advice này khỏi quyền **thay thế giá trị trả về**: nó được gọi sau khi target đã tính kết quả, và không dùng giá trị `return` của chính phương thức advice như giá trị mới cho caller. Tuy nhiên, API của từng engine có thể có các khả năng đặc biệt; cần đọc hợp đồng cụ thể thay vì khẳng định một giới hạn cú pháp cho mọi công cụ.

Cần tách ba trường hợp:

1. **Quan sát không can thiệp:** advice đọc giá trị để tính metrics, kiểm tra loại dữ liệu hoặc ghi audit, rồi caller vẫn nhận kết quả gốc.
2. **Sửa đối tượng mutable được chia sẻ:** nếu advice lấy được tham chiếu tới `List`, `Map` hoặc DTO mutable và thay đổi bên trong nó, caller có thể nhìn thấy thay đổi **ngay cả khi advice không thay thế tham chiếu trả về**. Đây là một tác dụng phụ có thể phá hợp đồng và gây race condition; không nên làm nếu chính sách chỉ là logging.
3. **Thay kết quả thật sự:** đổi `null` thành object mặc định, cache result, làm giàu dữ liệu trước khi caller nhận, hoặc áp dụng fallback là **thay đổi ngữ nghĩa**. Tình huống này thường cần `around` advice hoặc một cơ chế transformation được engine hỗ trợ, với kiểm thử chính xác kiểu, ngoại lệ và số lần target chạy.

Pseudocode minh họa (không phải API chạy độc lập):

~~~text
afterReturning(joinPoint, returnedValue):
    metrics.observe(returnedValue)   # chỉ quan sát

around(joinPoint, proceed):
    original = proceed()
    return transform(original)       # có thể thay kết quả cho caller
~~~

Không nên chọn `around` chỉ vì muốn in giá trị trả về. Quyền kiểm soát `proceed` mang thêm khả năng gọi target **0, 1 hoặc nhiều lần** và dễ phát sinh lỗi khi quên chuyển tiếp, nhân đôi tác dụng phụ hoặc nuốt ngoại lệ.

### 4.1. Return value của advice khác return value của target

Nếu một engine yêu cầu hàm advice có kiểu `void`, `Object` hoặc một kiểu khác, kiểu trả về của **hàm advice** không nên bị nhầm với kiểu trả về của **join point target**. Chức năng của after-returning được xác định bằng hợp đồng áp dụng advice; tự viết `return newValue;` trong hàm advice không bảo đảm caller nhận `newValue`.

### 4.2. Một kết quả “lỗi” vẫn có thể là normal return

Ví dụ:

~~~java
record SaveResult(boolean success, String message) {}

SaveResult save(boolean accepted) {
    if (!accepted) return new SaveResult(false, "rejected");
    return new SaveResult(true, "saved");
}
~~~

Đây là ví dụ chỉ về ý nghĩa kết quả, không phải một chương trình độc lập có `main`. Cả hai nhánh **đều là normal return**. After-returning chạy ở cả hai nếu pointcut khớp; không thể đếm mọi lần advice chạy như “số giao dịch thành công”. Muốn thống kê nghiệp vụ phải đọc `success()` hoặc dùng sự kiện miền thích hợp.

## 5. Ví dụ Java 17+ chạy được: after-returning trên nhiều loại kết quả

Để minh họa mà không cần một engine AOP chuyên biệt, ta xây dựng **JDK dynamic proxy** đóng vai trò adapter ở ranh giới lời gọi. Chương trình có phương thức trả `String`, trả `null`, trả `int`, `void`, trả `CompletableFuture` và ném ngoại lệ.

- `ResultObserver.afterReturning(...)` đại diện cho **hành vi sau normal completion**.
- Trong `observe()`, chỉ khi `method.invoke()` **trả bình thường**, observer mới được gọi.
- Nếu target ném ngoại lệ, `InvocationTargetException` của reflection được bóc để giữ nguyên nguyên nhân gốc; không chạy `afterReturning` cho lần gọi đó.
- Bộ hiển thị kiểm tra `void`, `null` và `Future` để tạo stdout ổn định, không lệ thuộc định danh/hash của object.
- Ví dụ **không phải AOP engine đầy đủ**: nó chỉ chặn lời gọi qua interface proxy, không tự thêm join point trong thân target.

Tạo file `AfterReturningDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.CompletableFuture;

public final class AfterReturningDemo {
    interface Catalog {
        String lookup(String key);
        int twice(int number);
        void ping();
        CompletableFuture<String> async(String key);
        String fail();
    }

    static final class CatalogCore implements Catalog {
        @Override
        public String lookup(String key) {
            System.out.println("BUSINESS lookup " + key);
            return "none".equals(key) ? null : "item:" + key;
        }

        @Override
        public int twice(int number) {
            return number * 2;
        }

        @Override
        public void ping() {
            System.out.println("BUSINESS ping");
        }

        @Override
        public CompletableFuture<String> async(String key) {
            System.out.println("BUSINESS async");
            return new CompletableFuture<>();
        }

        @Override
        public String fail() {
            System.out.println("BUSINESS fail");
            throw new IllegalStateException("storage unavailable");
        }
    }

    static final class ResultObserver {
        void afterReturning(Method method, Object result) {
            String display;
            if (method.getReturnType() == void.class) {
                display = "<void>";
            } else if (result instanceof CompletableFuture<?> future) {
                display = "Future(done=" + future.isDone() + ")";
            } else {
                display = String.valueOf(result);
            }
            System.out.println("AFTER_RETURNING "
                    + method.getName() + " -> " + display);
        }
    }

    static Catalog observe(Catalog target, ResultObserver observer) {
        return (Catalog) Proxy.newProxyInstance(
                Catalog.class.getClassLoader(),
                new Class<?>[]{Catalog.class},
                (proxy, method, args) -> {
                    Object result;
                    try {
                        result = method.invoke(target, args);
                    } catch (InvocationTargetException wrapped) {
                        Throwable original = wrapped.getCause();
                        System.out.println("EXCEPTION "
                                + method.getName() + " -> "
                                + original.getClass().getSimpleName());
                        throw original;
                    }
                    observer.afterReturning(method, result);
                    return result;
                });
    }

    public static void main(String[] args) {
        Catalog catalog = observe(new CatalogCore(), new ResultObserver());
        System.out.println("CALLER " + catalog.lookup("A7"));
        System.out.println("CALLER " + catalog.lookup("none"));
        System.out.println("CALLER " + catalog.twice(3));
        catalog.ping();
        System.out.println("CALLER ping done");

        CompletableFuture<String> pending = catalog.async("A7");
        System.out.println("CALLER future.done=" + pending.isDone());
        pending.complete("async:A7");
        System.out.println("CALLER async.result=" + pending.join());

        try {
            catalog.fail();
        } catch (IllegalStateException original) {
            System.out.println("CALLER caught " + original.getMessage());
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 AfterReturningDemo.java
java AfterReturningDemo
~~~

Đầu ra chính xác (đã kiểm chứng bằng trình biên dịch Java với `--release 17`):

~~~text
BUSINESS lookup A7
AFTER_RETURNING lookup -> item:A7
CALLER item:A7
BUSINESS lookup none
AFTER_RETURNING lookup -> null
CALLER null
AFTER_RETURNING twice -> 6
CALLER 6
BUSINESS ping
AFTER_RETURNING ping -> <void>
CALLER ping done
BUSINESS async
AFTER_RETURNING async -> Future(done=false)
CALLER future.done=false
CALLER async.result=async:A7
BUSINESS fail
EXCEPTION fail -> IllegalStateException
CALLER caught storage unavailable
~~~

### 5.1. Phân tích từng nhánh

**`lookup("A7")`:** target tính `"item:A7"` rồi trả bình thường. Observer nhận và in chính giá trị đó, sau đó caller cũng nhận `"item:A7"`. Điều này thể hiện mô hình advice **quan sát mà không thay thế** kết quả.

**`lookup("none")`:** target trả `null` bình thường. Observer in `null` và caller vẫn nhận `null`. Không có lỗi chỉ vì kết quả là `null`.

**`twice(3)`:** target trả `int 6`; reflection biểu diễn qua `Object` với boxing. Observer in `6`, nhưng chữ ký interface vẫn là `int twice(int)`, không bị thay đổi.

**`ping()`:** target có return type `void`. `Method.invoke()` cung cấp `null` cho adapter, nhưng observer kiểm tra `void.class` nên in `<void>` thay vì nhầm với một kết quả tham chiếu `null`.

**`async("A7")`:** target tạo và trả ngay một `CompletableFuture` **chưa hoàn tất**. Vì phương thức đã return bình thường, after-returning chạy và quan sát `Future(done=false)`; mã caller mới hoàn tất Future sau đó. Đây là bằng chứng rằng **method return** khác **asynchronous completion**.

**`fail()`:** target ném `IllegalStateException`. Adapter in một sự kiện `EXCEPTION` riêng (chỉ để minh họa đường lỗi), rồi caller bắt nguyên nhân gốc; **không có dòng `AFTER_RETURNING fail`**. Đường `EXCEPTION` của adapter không phải một instance của after-returning advice.

### 5.2. Phạm vi chính xác của ví dụ

Proxy chỉ quan sát lời gọi **đi qua đối tượng `catalog`** theo interface `Catalog`. Nếu gọi `new CatalogCore().lookup("A7")` trực tiếp, `ResultObserver` không được gọi. Không suy diễn từ ví dụ rằng mọi private method, constructor, field access, self-invocation hay lời gọi trực tiếp đều tạo được join point. Một cơ chế weaving khác có thể có độ phủ khác, nhưng cần xác minh tài liệu và kiểm thử thực tế.

Ở ví dụ, mọi phương thức khai báo trong `Catalog` đều đi qua observer nếu trả bình thường; ta chưa đặt điều kiện pointcut lọc phương thức cụ thể. Trong ứng dụng, có thể ghép bộ chọn chữ ký hoặc annotation để giảm phạm vi, tránh log thông tin không cần thiết.

## 6. Khi nào kết quả được coi là hoàn tất?

### 6.1. Phương thức trả về bình thường từ `try/catch`

~~~java
String load() {
    try {
        return readPrimary();
    } catch (IllegalStateException error) {
        return "fallback";
    }
}
~~~

Đây là **pseudocode Java minh họa**, chưa độc lập vì `readPrimary()` chưa định nghĩa. Nếu lỗi được handler bắt và `load()` trả `"fallback"`, after-returning ở ranh giới `load()` có thể chạy và thấy `"fallback"`. Dù hệ thống đã có một lỗi nội bộ, lần thực thi `load()` cuối cùng **không ném ngoại lệ ra ngoài**.

Nếu handler cũng ném lỗi, hoặc một `finally` phía sau ném lỗi, thì kết quả cuối có thể là exceptional completion và after-returning sẽ không chạy ở ranh giới được xét.

### 6.2. Return sớm

Một phương thức có nhiều nhánh `return` đều là kết thúc bình thường khi không ném lỗi. After-returning hoạt động theo **sự kiện kết thúc của join point**, không phụ thuộc target đã đi qua một hay nhiều lệnh `return` trong source. Nếu advice cần biết nhánh logic nào đã được đi qua, chỉ nhìn giá trị trả về có thể không đủ; cần tín hiệu nghiệp vụ rõ hơn.

### 6.3. `void` và constructor

Phương thức `void` có thể hoàn tất bình thường, nhưng **constructor** là một loại join point khác trong những mô hình hỗ trợ nó. Không tự áp dụng quy tắc “method after returning” lên constructor, field access hoặc exception handler nếu công cụ không định nghĩa cách áp dụng. Việc một constructor hoàn tất bình thường không có nghĩa một pointcut chọn method execution tự động chọn được constructor.

## 7. Lỗi phát sinh trong chính after-returning advice

Một trong những nguy cơ lớn là: **target đã thành công, nhưng after-returning advice tự gây ngoại lệ**.

Ví dụ advisor ghi `result.toString()` khi `result == null`, hoặc gọi dịch vụ audit đang mất kết nối. Target đã hoàn tất bình thường nhưng nếu lỗi từ advice được truyền tới caller, caller có thể thấy **toàn bộ lời gọi thất bại**. Trong trường hợp này:

- “Target thành công” và “caller nhận kết quả thành công” là hai phát biểu khác nhau.
- Chính sách error-handling của advice phải được mô tả, không tự ý nuốt mọi lỗi hoặc để lỗi thứ cấp thay thế lỗi quan trọng.
- Lỗi quan sát (metrics, logging) có thể được báo qua một kênh riêng nếu yêu cầu cho phép, nhưng cách xử lý cần nhất quán và an toàn.
- Nếu advice cố tình kiểm tra và từ chối kết quả, đó đã là hành vi có tác động lên hợp đồng caller; cần coi là quyết định thiết kế, không chỉ là một log statement.

Trong ví dụ Java, `observer.afterReturning(...)` nằm **sau** khối `try/catch` dành riêng cho `method.invoke(...)`. Nhờ đó, lỗi do observer ném không bị gắn nhầm nhãn là `EXCEPTION` của target. Việc phân biệt nguồn lỗi rất quan trọng khi thiết kế advice có độ tin cậy cao.

### 7.1. Tránh ghi dữ liệu nhạy cảm

Kết quả trả về có thể chứa mã truy cập, mật khẩu đã băm, định danh người dùng, thông tin thanh toán hoặc payload cá nhân. Advice không nên serialize toàn bộ object graph và đẩy vào log chỉ vì đó là giá trị dễ lấy từ join point. Hãy chọn trường cần thiết, masking dữ liệu, giới hạn độ dài, sampling và chính sách retention phù hợp.

### 7.2. Không tạo vòng gọi ngoài ý muốn

Nếu advice ghi log bằng một API cũng bị chính pointcut audit lựa chọn, việc ghi log có thể kích hoạt advice lần nữa và dẫn tới **đệ quy không kiểm soát**. Pointcut nên loại trừ cơ chế logging/metrics nội bộ hoặc sử dụng cách ngăn reentrancy có hợp đồng rõ ràng.

## 8. Bất đồng bộ: after returning khác after completion

Trong hệ thống bất đồng bộ, một phương thức có thể trả về một `CompletableFuture<T>`, promise, stream hoặc handle tới công việc sẽ diễn ra sau. Có ít nhất hai thời điểm tách biệt:

1. **Method return:** phương thức trả về đối tượng handle bình thường. After-returning của method execution/call có thể chạy ngay.
2. **Task completion:** nội dung bất đồng bộ hoàn tất thành công hoặc thất bại. Điều này có thể xảy ra sau đó, ở thread khác, hoặc không bao giờ xảy ra nếu tác vụ bị treo.

Ví dụ `async()` vừa trả một `CompletableFuture` pending: after-returning thấy *handle* đó, không có sẵn `T` bên trong. Nếu Future hoàn tất bằng ngoại lệ sau đó, phương thức tạo Future vẫn có thể đã **normal return**. Không dùng duy nhất số lần after-returning trên phương thức trả Future làm thống kê số tác vụ thành công.

Nếu muốn quan sát kết quả cuối, có thể gắn một callback completion vào handle, với chính sách rõ về completion bình thường, completion ngoại lệ và cancellation. Đây là **quan sát bất đồng bộ thêm**, không đồng nghĩa với advice `after returning` trên method ban đầu. Nếu callback làm biến đổi Future được trả, nó có thể thay đổi semantics và cần kiểm thử.

Ví dụ minh họa callback (chưa độc lập):

~~~java
CompletableFuture<String> future = startAsyncJob();
future.whenComplete((value, error) -> {
    if (error == null) {
        recordTaskSuccess(value);
    } else {
        recordTaskFailure(error);
    }
});
~~~

`startAsyncJob`, `recordTaskSuccess` và `recordTaskFailure` là các thành phần giả định. `whenComplete` đăng ký hành vi quan sát kết quả cuối; exception do callback sinh ra có quy tắc ảnh hưởng tới stage trả về tùy API và cần xem xét. Không tự giả định `whenComplete` chạy trên thread hay ngữ cảnh giống caller ban đầu.

## 9. Thứ tự nhiều advice ảnh hưởng kết quả quan sát

Giả sử `A` và `B` cùng quan sát việc trả về của một phương thức, nhưng `B` nằm trong một `around` của `A`. Trình tự thực tế tùy cơ chế kết hợp, chẳng hạn:

~~~text
Around A enter
  Around B enter
    Target -> original result
  Around B exit
Around A exit
Caller receives final result
~~~

Nếu tầng B là một **transformer around** làm `original` thành `modified` trước khi trả cho A, thì một after-returning observer ở **trong** B có thể thấy `original`, còn observer nằm **ngoài** B có thể thấy `modified`. Đây là lý do “giá trị trả về được advice nhìn thấy” luôn gắn với **join point và tầng wrapper cụ thể**, không phải lúc nào cũng là kết quả cuối cùng caller nhận.

Cần làm rõ các vấn đề sau trước khi kết hợp:

- Advice nào chạy trước/sau; thứ tự do precedence, cấu hình hoặc weaving quy định, **không mặc định dựa trên thứ tự source file**.
- After-returning của một tầng có quan sát kết quả trước hay sau các phép biến đổi ở tầng khác?
- Một tầng `around` có thể bỏ gọi `proceed` không? Nếu nó trả kết quả cache bình thường, advice nằm phía ngoài có thể quan sát normal return dù target không chạy.
- Nếu một tầng ném ngoại lệ sau khi target return, các advice bao ngoài có thể thấy **exceptional completion**, trong khi observer bên trong đã thấy normal completion.

Đối với hệ thống đòi hỏi audit chính xác, nên quy định **“kết quả sau tầng nào”** được đo và kiểm thử nhiều advice cùng khớp.

## 10. Thiết kế hợp đồng quan sát giá trị trả về

Một after-returning advice tốt nên mô tả cụ thể:

| Quyết định | Câu hỏi cần trả lời |
| --- | --- |
| Phạm vi pointcut | Phương thức nào được chọn? Có loại trừ logging/metrics nội bộ không? |
| Loại kết quả | Nhìn kiểu khai báo, kiểu runtime hay cả hai? Có `void`, `null`, primitive, generic? |
| Ngữ nghĩa thành công | Đếm normal return hay thành công nghiệp vụ trong `Result`? |
| Dữ liệu quan sát | Chỉ đếm, ghi mã trạng thái, kích thước hoặc hash an toàn? |
| Lỗi advice | Logging/metrics thất bại được báo riêng hay làm thất bại lời gọi? |
| Tác động mutable | Có vô tình thay đổi object graph được caller dùng không? |
| Thứ tự | Advice chạy trước/sau transformer nào? |
| Async | Kết quả đo tại method return hay task completion cuối? |
| Khả năng can thiệp | Call/execution join point, proxy, weaving và self-invocation được hỗ trợ ra sao? |
| Tài nguyên | Có sampling, giới hạn chi phí và bộ đếm an toàn đồng thời không? |

Một ví dụ về đo lường đúng ngữ nghĩa: thay vì ghi `businessSuccess++` ở mọi after-returning của `save()`, có thể ghi `normalReturns++` trước; nếu `save()` trả `SaveResult` có flag `success`, một phép đo riêng mới dựa vào flag đó để thống kê miền. Hai metric sẽ khác nhau khi nghiệp vụ từ chối một yêu cầu mà không ném lỗi.

## 11. Kiểm thử after-returning

Có thể dùng bảng sau làm contract test:

| Trường hợp | Kết thúc target | Có after-returning tại ranh giới ấy? | Kiểm tra bổ sung |
| --- | --- | --- | --- |
| Trả `"item:A7"` | Bình thường | Có nếu pointcut khớp | Advice/caller thấy đúng giá trị |
| Trả `null` | Bình thường | Có | Không `NullPointerException` do observer |
| Trả `int 6` | Bình thường | Có | Boxing trong adapter không đổi chữ ký API |
| Method `void` | Bình thường | Có nếu join point/engine hỗ trợ | Phân biệt `void` với trả tham chiếu `null` |
| Target ném `IllegalStateException` | Ngoại lệ | Không | Caller nhận đúng ngoại lệ gốc |
| Target ném lỗi rồi tự bắt, trả fallback | Bình thường ở ranh giới ngoài | Có | Phân biệt normal return với nghiệp vụ đã phục hồi |
| Trả `Result.failure(...)` | Bình thường | Có | Không tự cộng vào business success |
| Trả Future còn pending | Bình thường tại method | Có | Không coi Future pending là tác vụ thành công |
| Future thất bại sau khi method đã return | Bình thường tại method; thất bại trong task | Có tại method; event task tùy cơ chế riêng | Quan sát completion đúng |
| Advice tự ném lỗi | Target có thể thành công | Target normal completion đã xảy ra | Chính sách lỗi và caller contract rõ |
| Gọi target trực tiếp bỏ qua proxy | Theo target | Advice proxy không chạy | Phân biệt matching và interception |
| Hai advice khác thứ tự | Tùy tầng | Theo từng điểm/tầng | Kiểm tra giá trị mỗi tầng và caller |

Đừng chỉ unit test một method `afterReturning(...)` bằng mock result. Nó kiểm tra phần logic observer nhưng **không chứng minh** engine đã chọn đúng pointcut, chạy đúng loại advice và giữ nguyên kết quả trả cho caller. Phải có integration test đi qua ranh giới thực được instrument.

### Những assertion hữu ích

- Gọi `lookup("A7")` qua proxy: observer chạy **một lần**, nhận `"item:A7"` và caller vẫn nhận `"item:A7"`.
- Gọi `lookup("none")`: observer vẫn chạy, xử lý `null` an toàn.
- Gọi `fail()`: observer **không** chạy; caller nhận `IllegalStateException` gốc.
- Gọi `async("A7")`: observer thấy Future lúc return; hoàn tất Future không tự kích hoạt **thêm lần after-returning của cùng method**.
- Gọi trực tiếp `CatalogCore`: không có sự kiện từ observer của proxy.
- Thay thứ tự các wrapper/transformer: ghi lại kết quả observer thấy ở từng tầng, so sánh với kết quả cuối caller.

## 12. Lỗi hiểu sai phổ biến

1. **“After returning luôn là nghiệp vụ thành công.”** Sai: trả `false`, `null` hoặc `Result.failure` vẫn là normal completion.
2. **“After returning chạy cả khi ném ngoại lệ.”** Sai tại ranh giới đã chọn; đó là nhánh exceptional completion.
3. **“Trả `null` nghĩa là không có return.”** Sai; `null` là giá trị của kiểu tham chiếu và khác `void`.
4. **“Phương thức `void` không thể hoàn tất bình thường.”** Sai; nó có normal completion dù không có result object.
5. **“Advice có thể `return` gì thì caller nhận nấy.”** Không có quy tắc chung như vậy; phải xét hợp đồng after-returning của engine. Biến đổi kết quả thường là trách nhiệm của `around` hoặc API chuyên dụng.
6. **“Sửa một DTO mutable trong advice không ảnh hưởng caller.”** Sai; cùng tham chiếu có thể được sử dụng tiếp.
7. **“Future đã được trả tức tác vụ đã xong.”** Sai; hãy phân biệt return handle và completion.
8. **“Target thành công thì caller chắc chắn thành công.”** Advice phía sau có thể tự gây lỗi hoặc biến đổi kết quả.
9. **“Hai advice sẽ luôn quan sát một giá trị giống nhau.”** Thứ tự wrapper/transformer có thể khiến các tầng thấy các kết quả khác nhau.
10. **“Đặt after-returning là chặn được mọi phương thức.”** Khả năng intercept phụ thuộc pointcut, call/execution, proxy/weaving và đường gọi thực tế.
11. **“Log toàn bộ giá trị trả về là an toàn và rẻ.”** Dữ liệu có thể nhạy cảm, object lớn, `toString()` tốn chi phí hoặc có side effect.
12. **“Sau khi target trả bình thường, advice không thể ném lỗi.”** Sai; lỗi do chính advice vẫn có thể ảnh hưởng caller.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Phương thức trả `Result(success=false)` mà không ném exception. After-returning có chạy không?  
**Đáp án:** Có thể chạy nếu pointcut khớp và engine hỗ trợ; đó là normal return dù nghiệp vụ báo thất bại.

**Câu 2.** Sự khác nhau giữa `void` và kết quả `null` khi quan sát qua Java Reflection là gì?  
**Đáp án:** Cả hai có thể cho `Method.invoke()` trả `null`, nhưng `void` không có giá trị trả về nghiệp vụ, còn `null` là giá trị của một phương thức có kiểu trả về tham chiếu; dùng return type để phân biệt.

**Câu 3.** Muốn thay kết quả `"A"` thành `"B"` trước khi caller nhận, có nên mặc định dùng after-returning để làm không?  
**Đáp án:** Không. Nhiều mô hình after-returning được thiết kế để quan sát; việc thay kết quả thường cần `around` hoặc cơ chế transformation được công cụ hỗ trợ và kiểm thử.

**Câu 4.** Một phương thức trả `CompletableFuture` pending rồi tác vụ lỗi sau đó. Sau khi phương thức return có thể có after-returning không?  
**Đáp án:** Có, vì bản thân method đã trả Future bình thường; muốn biết lỗi của tác vụ phải quan sát completion riêng.

**Câu 5.** Nếu `lookup()` thành công nhưng advice ghi log ném exception, caller có chắc nhận kết quả của `lookup()` không?  
**Đáp án:** Không. Điều đó phụ thuộc việc lỗi advice được xử lý hay lan ra; phải quy định và kiểm thử chính sách lỗi.

**Câu 6.** Vì sao không nên chỉ nhìn một biến `result` để quyết định tính số “nghiệp vụ thành công”?  
**Đáp án:** Kết quả có thể là `null`, status thất bại trong một response object hoặc handle bất đồng bộ còn pending; định nghĩa thành công nghiệp vụ cần hợp đồng rõ hơn normal completion.

## 14. Tổng kết

**After-returning advice** kích hoạt sau khi join point được chọn **hoàn tất bình thường** và thường dùng để **quan sát giá trị trả về** mà không lẫn vào logic nghiệp vụ. Hiểu đúng loại advice này cần phân biệt **normal return với thành công nghiệp vụ**, **`void` với `null`**, **kiểu khai báo với giá trị runtime**, **quan sát với thay thế kết quả**, **method return với task completion bất đồng bộ**, và **lỗi target với lỗi của advice**. Khi nhiều aspect cùng tham gia, hãy xác định ranh giới và thứ tự để biết chính xác giá trị nào được quan sát. Kiểm thử kết quả caller, nhánh ngoại lệ và phạm vi weaving/proxy để bảo đảm chính sách cắt ngang đúng ý định.