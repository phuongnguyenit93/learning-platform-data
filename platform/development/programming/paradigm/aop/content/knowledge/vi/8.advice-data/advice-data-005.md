# Làm việc với giá trị trả về và phương thức không trả dữ liệu

## 1. Giá trị trả về là dữ liệu gì trong advice?

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), một **pointcut** chọn các *join point* có thể can thiệp; **advice** thực hiện hành vi bổ sung tại các điểm ấy. Khi join point là lời gọi hoặc lần thực thi phương thức, advice có thể cần biết **giá trị mà phương thức trả cho caller**, ví dụ để ghi thống kê, audit trạng thái, đo kết quả, kiểm tra hợp đồng hoặc áp dụng biến đổi có chủ đích.

Trọng tâm của bài là phân biệt rõ:

1. **Phương thức trả một giá trị:** `String`, `int`, một DTO, `Optional<T>`, `CompletableFuture<T>`, v.v.
2. **Phương thức khai báo `void`:** hoàn tất mà **không có giá trị trả về**.
3. **Phương thức trả tham chiếu `null`:** *có* hợp đồng kiểu trả về tham chiếu, nhưng giá trị cụ thể bằng `null`.
4. **Phương thức ném ngoại lệ:** kết thúc bằng đường exceptional completion; không có một kết quả trả về bình thường ở ranh giới đó.
5. **Phương thức trả một handle bất đồng bộ:** phương thức đã trả về bình thường nhưng dữ liệu cuối có thể **chưa sẵn sàng**.

Những tình huống này có ý nghĩa khác nhau. Nếu gộp `void`, `null`, kết quả rỗng và ném ngoại lệ thành “không có dữ liệu”, advice có thể ghi nhầm metric, ép kiểu lỗi, ném `NullPointerException` hoặc thay đổi giao diện nghiệp vụ.

**Tư duy đúng:** chọn **thời điểm advice** và **hợp đồng dữ liệu của join point** trước; sau đó mới quyết định cách đọc, kiểm tra, ghi hoặc biến đổi kết quả.

## 2. Mối quan hệ giữa return type, return value và completion

Một phương thức Java có thể có **kiểu trả về khai báo** và **giá trị trả về runtime**:

~~~java
String name() {
    return "Alice";
}

String missing() {
    return null;
}

void clear() {
    // hoàn tất bình thường nhưng không return một giá trị
}

int size() {
    return 3;
}
~~~

Các khai báo trên chỉ là minh họa; chưa phải chương trình độc lập có `main`.

| Phương thức | Kiểu khai báo | Kết quả bình thường | Ý nghĩa trong advice |
| --- | --- | --- | --- |
| `name()` | `String` | `"Alice"` | Có một tham chiếu `String` để quan sát |
| `missing()` | `String` | `null` | Vẫn là **normal return** |
| `clear()` | `void` | Không có giá trị | Có thể có sự kiện hoàn tất bình thường nhưng không có result nghiệp vụ |
| `size()` | `int` | `3` | Kết quả primitive; adapter dùng `Object` có thể boxing |
| `load()` ném `IOException` | Tùy chữ ký | Không có normal return cho lần này | Nhánh exceptional completion |

Một phương thức `boolean save()` trả `false` vẫn **kết thúc bình thường**; việc `false` biểu thị thất bại nghiệp vụ không biến nó thành exception. Tương tự, `Result.failure(...)` được trả bình thường vẫn có thể kích hoạt advice hậu trả về.

**Normal completion khác business success.** Khi thống kê, nên dùng tên rõ như `normal_return_count` thay vì mặc định đặt `successful_order_count` cho mọi lần advice sau khi trả về chạy.

## 3. Advice nào có thể quan sát kết quả?

Không phải mọi advice đều có cùng dữ liệu vào cùng thời điểm.

| Loại advice | Có biết kết quả trả về của lời gọi đang diễn ra? | Lưu ý chính |
| --- | --- | --- |
| **Before** | Chưa | Chỉ có thể dựa vào chữ ký, target, đối số/ngữ cảnh được cung cấp trước khi thực thi |
| **After returning** | Có thể, nếu engine hỗ trợ binding | Chỉ khi join point hoàn tất bình thường; cần xử lý `void`, `null` và binding theo engine |
| **After throwing** | Không có normal return của lần ấy | Quan sát ngoại lệ thoát khỏi join point; không phải giá trị trả về |
| **After/finally** | Tùy API; không bảo đảm có kết quả | Chạy khi rời phạm vi ở cả đường bình thường và ngoại lệ theo mô hình tương ứng |
| **Around** | Có thể nhận kết quả từ `proceed` | Có thể chuyển tiếp, giữ nguyên, thay thế, bỏ qua target hoặc xử lý lỗi tùy hợp đồng |

Ví dụ sơ đồ khái niệm:

~~~text
Caller
  |
  v
[Before]
  |
[Target/Join point]
  |
  +---- normal return: result --------> [After returning] ---> caller
  |
  +---- exceptional exit: error ------> [After throwing] ----> caller
                        \
                         [After/finally] trên đường rời phạm vi
~~~

Đây là sơ đồ về **điều kiện kích hoạt**, không phải đặc tả thứ tự chung cho mọi công cụ AOP. Một cơ chế `around` hoặc thứ tự nhiều advice có thể tạo ra nhiều tầng quan sát; result mà mỗi tầng thấy phụ thuộc **ranh giới được bao quanh**.

Cần xác minh bộ máy AOP có hỗ trợ binding giá trị trả về ở loại advice và join point đang dùng hay không. Đừng sao chép cú pháp tham số result từ công cụ này sang công cụ khác, hoặc giả định advice `before` đã biết kết quả tương lai.

## 4. Trường hợp `void`: không trả dữ liệu không có nghĩa là không hoàn tất

`void` trong Java diễn đạt rằng phương thức **không sản sinh giá trị trả về**:

~~~java
void publish(String message) {
    System.out.println(message);
    return;
}
~~~

Đây là đoạn minh họa, không phải chương trình đầy đủ. `return;` trong method `void` chỉ kết thúc phương thức; không trả object hay `null` theo hợp đồng source.

Nhưng `publish(...)` có thể:

- **Hoàn tất bình thường**, nên một advice theo dõi normal completion có thể chạy nếu engine hỗ trợ join point tương ứng.
- **Ném ngoại lệ**, khiến advice quan sát exceptional exit có thể chạy thay vào đó.
- **Bị bỏ qua bởi pointcut/proxy/weaving**, nên không có advice dù phương thức chạy.
- **Thực hiện side effect** (ghi DB, in log, gửi message), dù không có result object.

Vì thế `void` không đồng nghĩa “không có kết quả nghiệp vụ đáng quan sát”. Ta vẫn có thể ghi tên thao tác, thời gian, trạng thái hoàn tất, số lần gọi và ngoại lệ nếu có.

### 4.1. Khi công nghệ yêu cầu binding return value

Một số cơ chế chỉ cho bind giá trị trả về vào tham số advice nếu kiểu hoặc join point phù hợp. Với method `void`, có thể không có gì để bind, dù event normal completion vẫn tồn tại. **Đừng giả định** engine sẽ tự cung cấp đối tượng `Void` hay `null` cho mọi binding return.

Nếu chính sách chỉ cần biết method `void` hoàn tất bình thường, hãy chọn loại advice/cấu hình **không đòi một result object không tồn tại**. Nếu mã adapter dựa trên Reflection cung cấp `null` cho method `void`, đó là quy ước adapter, không phải giá trị return nghiệp vụ.

### 4.2. `void` và `Void` khác nhau

- `void` là từ khóa kiểu trả về **không có giá trị**.
- `Void` là một **kiểu tham chiếu** (`java.lang.Void`). Một phương thức khai báo `Void` có một contract trả về tham chiếu, thực tế trong mã Java thông thường thường là `null`.

Ví dụ:

~~~java
Void task() {
    doWork();
    return null;
}
~~~

Đây là đoạn minh họa thiếu `doWork()`. Không nên dùng `Void` chỉ để ép mọi phương thức `void` vào một giao diện kết quả; mỗi lựa chọn có ngữ nghĩa API riêng. Chẳng hạn `Callable<Void>` có thể biểu diễn một tác vụ kiểu generic với kết quả `null`, khác một phương thức khai báo `void` trực tiếp.

### 4.3. `void` khác `Optional.empty()`

`Optional.empty()` là một **object Optional hợp lệ** biểu thị vắng giá trị bên trong, không phải `null` và không phải `void`. Advice có thể quan sát một kết quả `Optional<T>` tồn tại rồi kiểm tra `isPresent()` theo nhu cầu. Không ép `Optional.empty()` thành exceptional completion.

## 5. Giá trị `null`: có thể là return bình thường

Một lỗi rất phổ biến trong advice sau khi trả về là:

~~~java
void observe(Object result) {
    System.out.println(result.toString());
}
~~~

Đây là đoạn minh họa. Nếu result bằng `null` thì chính advice ném `NullPointerException`, dù target có thể đã hoàn tất bình thường. Điều này gây ra hai sai lệch:

1. Caller có thể thấy lỗi mới không phát sinh từ logic nghiệp vụ.
2. Người vận hành có thể đếm nhầm lời gọi target thành công thành thất bại do advice.

Cách an toàn hơn cho quan sát đơn giản:

~~~java
String label = result == null ? "<null>" : result.getClass().getSimpleName();
~~~

Cần nhớ: **`String.valueOf(result)` gọi `toString()` khi result khác `null`**, nên vẫn có rủi ro tốn thời gian, xuất dữ liệu nhạy cảm hoặc lỗi từ code `toString()`. Nếu không cần toàn bộ nội dung kết quả, chỉ ghi **loại**, **trạng thái**, **kích thước có kiểm soát** hoặc trường đã cho phép.

Nếu hợp đồng API không cho phép `null` nhưng target vẫn trả `null`, đó là một vấn đề hợp đồng đáng kiểm thử. Advice audit không nên âm thầm “sửa” nó thành giá trị khác, trừ khi chính sách chuyển đổi được định nghĩa rõ.

## 6. Primitive, boxing/unboxing và kiểu chính xác

Phương thức trả primitive:

~~~java
int count() { return 7; }
boolean enabled() { return false; }
long bytes() { return 1024L; }
~~~

Khi một adapter Java Reflection trả kết quả qua `Object`, primitive thường được **boxing**:

- `int` → `Integer`
- `boolean` → `Boolean`
- `long` → `Long`

Trong khi đó, **kiểu trả về khai báo vẫn là primitive**, có thể nhận bằng `Method.getReturnType()`: `int.class`, `boolean.class`, `long.class`. Boxing ở tầng adapter **không thay đổi** chữ ký method.

Không được giả định rằng một result `Integer` luôn đến từ method khai báo `Integer`; nó có thể đến từ method khai báo `int`. Ngược lại, nếu một `around` adapter trả `null` cho phương thức primitive, proxy hoặc cơ chế hoàn trả có thể ném lỗi unboxing thay vì trả kết quả hợp lệ.

Ví dụ sai về mặt hợp đồng:

~~~text
target: int balance()
around: return null
caller: cần một int => nguy cơ NullPointerException/unboxing failure
~~~

Bởi vậy, một advice biến đổi result phải xác minh **return type của join point**, khả năng tương thích kiểu và giá trị. Với method `void`, không nên trả một object bất kỳ rồi tin rằng caller có thể sử dụng nó làm return value.

## 7. Phân biệt quan sát và biến đổi giá trị trả về

Đây là ranh giới thiết kế then chốt.

**After-returning** thường dùng để **quan sát** kết quả normal completion. Trong nhiều mô hình AOP, việc hàm advice tự `return` một object không có nghĩa nó được thay vào kết quả của target. Muốn đổi kết quả mà caller nhìn thấy, thường cần **around advice** hoặc một cơ chế return transformation đặc biệt được engine hỗ trợ.

Hai hợp đồng khác nhau:

~~~text
observe(result):
    metrics.record(resultMetadata)
    // Caller nhận result ban đầu

transform(proceed):
    original = proceed()
    changed = normalize(original)
    return changed
    // Caller có thể nhận changed
~~~

Đây là **pseudocode**, không phải ngôn ngữ pointcut dùng chung cho mọi engine AOP.

Ví dụ chính sách rõ ràng:

- **Quan sát**: khi `fetch("none")` trả `null`, ghi `result_is_null=true` rồi caller vẫn nhận `null`.
- **Biến đổi**: `around` chủ động đổi `null` thành `"fallback"` trước khi caller nhận, vì API quy định chính sách mặc định.

Chỉ lựa chọn thứ hai được phép thay result. Và dù biến đổi hợp lệ, advice vẫn cần bảo đảm:

1. Kiểu của result mới tương thích kiểu khai báo/hợp đồng Java.
2. Giá trị mới không làm caller hiểu nhầm trạng thái nghiệp vụ.
3. Không chạy target thêm lần ngoài ý định.
4. Không “nuốt” ngoại lệ và biến thành giá trị thành công trừ khi chính sách phục hồi được công bố.
5. Không làm mất metadata, correlation hoặc cấu trúc domain có ý nghĩa.
6. Các tầng advice bên trong/bên ngoài có thể nhìn **những result khác nhau**.

**Sửa một object mutable là một dạng thay đổi:** advice lấy `List` hoặc DTO rồi sửa field sẽ tác động tới caller dùng cùng tham chiếu, dù chính method advice không trả reference mới. Advice được ghi là “chỉ quan sát” nên tránh các thay đổi như vậy.

## 8. Ví dụ Java 17+ chạy độc lập: giá trị, void, null và transformation

Chương trình này dùng **JDK dynamic proxy** và Java Reflection để mô phỏng dữ liệu mà advice nhận ở ranh giới lời gọi:

- `observe(...)` thực hiện hành vi tương đương **after returning**, chỉ chạy khi target được chuyển tiếp **trả về bình thường**.
- Nó phân biệt `void` dựa vào **kiểu khai báo**, `null` dựa vào **giá trị runtime**, `int` qua boxing của Reflection và `CompletableFuture` còn pending.
- `withFallback(...)` là một **around wrapper khác** có chủ đích biến kết quả `null` của riêng `fetch` thành `"fallback"`. Điểm khác biệt giữa **đọc** và **thay** result sẽ nhìn thấy ở đầu ra.
- `crash()` ném ngoại lệ: observer **không in `AFTER crash`** vì không có normal return ở ranh giới đó.
- Mỗi lời gọi qua proxy được chuyển tiếp một lần; `InvocationTargetException` của reflection được bóc để không thay loại lỗi nghiệp vụ.

Tạo file `AdviceReturnDataDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.CompletableFuture;

public final class AdviceReturnDataDemo {
    interface Operations {
        String fetch(String key);
        int sum(int left, int right);
        void reset();
        CompletableFuture<String> defer();
        String crash();
    }

    static final class Core implements Operations {
        public String fetch(String key) {
            System.out.println("BUSINESS fetch " + key);
            return "none".equals(key) ? null : "item:" + key;
        }

        public int sum(int left, int right) {
            return left + right;
        }

        public void reset() {
            System.out.println("BUSINESS reset");
        }

        public CompletableFuture<String> defer() {
            System.out.println("BUSINESS defer");
            return new CompletableFuture<>();
        }

        public String crash() {
            System.out.println("BUSINESS crash");
            throw new IllegalStateException("unavailable");
        }
    }

    static Object invoke(Operations target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Operations observe(Operations target) {
        return (Operations) Proxy.newProxyInstance(
                Operations.class.getClassLoader(),
                new Class<?>[]{Operations.class},
                (proxy, method, args) -> {
                    Object value = invoke(target, method, args);
                    String display;
                    if (method.getReturnType() == void.class) {
                        display = "<void>";
                    } else if (value == null) {
                        display = "<null>";
                    } else if (value instanceof CompletableFuture<?> future) {
                        display = "Future(done=" + future.isDone() + ")";
                    } else {
                        display = String.valueOf(value);
                    }
                    System.out.println("AFTER " + method.getName()
                            + " declared=" + method.getReturnType().getSimpleName()
                            + " value=" + display);
                    return value;
                });
    }

    static Operations withFallback(Operations target) {
        return (Operations) Proxy.newProxyInstance(
                Operations.class.getClassLoader(),
                new Class<?>[]{Operations.class},
                (proxy, method, args) -> {
                    Object result = invoke(target, method, args);
                    if (method.getName().equals("fetch") && result == null) {
                        System.out.println("AROUND fallback applied");
                        return "fallback";
                    }
                    return result;
                });
    }

    public static void main(String[] args) {
        Operations raw = observe(new Core());
        Operations transformed = withFallback(raw);

        System.out.println("CALLER " + raw.fetch("A"));
        System.out.println("CALLER " + raw.fetch("none"));
        System.out.println("CALLER " + transformed.fetch("none"));
        System.out.println("CALLER " + raw.sum(2, 3));
        raw.reset();
        System.out.println("CALLER reset done");

        CompletableFuture<String> pending = raw.defer();
        System.out.println("CALLER future.done=" + pending.isDone());
        pending.complete("async-done");
        System.out.println("CALLER future.value=" + pending.join());

        try {
            raw.crash();
        } catch (IllegalStateException error) {
            System.out.println("CALLER caught "
                    + error.getClass().getSimpleName() + ":" + error.getMessage());
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 AdviceReturnDataDemo.java
java AdviceReturnDataDemo
~~~

Đầu ra chính xác đã đối chiếu bằng chạy thực:

~~~text
BUSINESS fetch A
AFTER fetch declared=String value=item:A
CALLER item:A
BUSINESS fetch none
AFTER fetch declared=String value=<null>
CALLER null
BUSINESS fetch none
AFTER fetch declared=String value=<null>
AROUND fallback applied
CALLER fallback
AFTER sum declared=int value=5
CALLER 5
BUSINESS reset
AFTER reset declared=void value=<void>
CALLER reset done
BUSINESS defer
AFTER defer declared=CompletableFuture value=Future(done=false)
CALLER future.done=false
CALLER future.value=async-done
BUSINESS crash
CALLER caught IllegalStateException:unavailable
~~~

### 8.1. Vì sao `fetch("none")` có hai kết quả caller khác nhau?

Lần qua `raw`: target trả `null`, observer in `<null>`, rồi caller cũng nhận `null`. **Đó là advice chỉ quan sát**.

Lần qua `transformed`: wrapper `withFallback` gọi vào `raw` trước; `raw` vẫn quan sát `null` và in `AFTER ... <null>`. Sau đó wrapper ngoài thấy result `null`, thay bằng `"fallback"` rồi trả cho caller. Vì thế **observer bên trong và caller bên ngoài nhìn thấy hai result khác nhau**. Đây là hành vi có chủ đích của `around`, không phải một after-returning observer tự sửa kết quả.

Chính thứ tự wrapper quyết định tầng nào thấy giá trị gốc hay biến đổi. Đảo vị trí wrapper có thể làm thay đổi dữ liệu nhìn thấy ở mỗi advice.

### 8.2. Vì sao `reset()` ghi `<void>` thay vì `<null>`?

`Method.invoke()` với method `void` trả `null` trong adapter Reflection. Nếu chỉ xét `value == null`, ví dụ sẽ gộp `reset()` với `fetch("none")`; do đó observer kiểm tra `method.getReturnType() == void.class` **trước**. Đây là phân biệt theo **kiểu khai báo**, không phải một giá trị `Void` đặc biệt được return từ target.

### 8.3. Vì sao `sum(2,3)` in `int` nhưng `value` là `Object`?

Interface khai báo `int sum(int,int)`. Java Reflection cung cấp kết quả qua `Object` (primitive được boxing), nên observer có thể in `5`. Nhưng `Method.getReturnType()` vẫn là `int.class`, vì vậy hiển thị `declared=int`.

### 8.4. Vì sao không có `AFTER crash`?

`crash()` ném `IllegalStateException`. Hàm `invoke(...)` bóc `InvocationTargetException` rồi ném lại nguyên nhân, khiến lời gọi observer không đi tới đoạn in `AFTER`. Caller bắt đúng lỗi gốc. Nếu target bắt lỗi bên trong và **trả một kết quả dự phòng bình thường**, observer có thể chạy như mọi normal return khác.

### 8.5. Phạm vi và giới hạn của mô hình

Đây là **mô hình JDK proxy dùng để học dữ liệu trong advice**, không phải bộ weaving tổng quát. Nó chỉ intercept lời gọi **qua `raw` hoặc `transformed`**; gọi trực tiếp `new Core().fetch(...)` không chạy observer. Chương trình cố ý dùng interface method để lấy kiểu trả về và phản chiếu đúng lời gọi. Một engine AOP có thể khác về loại join point, phương thức đại diện, binding, thứ tự advice và khả năng can thiệp private/final/self-invocation.

Trong code `withFallback`, điều kiện chỉ theo tên `fetch` vì interface minh họa không có overload. Trong code thật, nên chọn rõ chữ ký hoặc marker, tránh một overload khác cũng bị thay result ngoài dự định.

## 9. Làm việc với phương thức không có result object

Nếu method `void` được chọn, advice vẫn có thể thực hiện nhiều nhiệm vụ **không cần giá trị trả về**:

| Mục tiêu | Dữ liệu phù hợp | Có cần return value không? |
| --- | --- | --- |
| Đếm số lần kết thúc bình thường của `void send()` | Tên thao tác, trạng thái normal completion | Không |
| Đo thời gian của `void update()` | Mốc bắt đầu và kết thúc | Không |
| Audit `void delete()` | Hợp đồng thao tác, ID đã được phép log, outcome | Không |
| Theo dõi lỗi của `void publish()` | Ngoại lệ thoát ra, loại lỗi | Không |
| Kiểm tra quyền trước `void reset()` | Principal/role/đối số theo hợp đồng | Không |
| Áp dụng cleanup sau `void flush()` | Tài nguyên/ngữ cảnh của lời gọi | Không |

**Không cần tạo kết quả giả** chỉ để logging. Việc thêm `return null;` vào code `void` là không hợp lệ theo cú pháp Java. Nếu một adapter generic dùng `Object` đại diện result cho mọi phương thức, cách biểu diễn `null` ở tầng adapter phải được quản lý có ý thức, không được xem là result object nghiệp vụ.

Một ví dụ pseudocode:

~~~text
afterNormalCompletion(joinPoint):
    if declaredReturnType == void:
        metrics.count("completed_void_operation")
    else:
        metrics.observeType(returnedValue)
~~~

Đây là **cách tư duy**, không phải API có sẵn của mọi công cụ AOP.

## 10. Dữ liệu null, rỗng và kết quả biểu diễn thất bại nghiệp vụ

Xét những trường hợp:

| Giá trị trả về | Trạng thái Java method | Có đồng nghĩa business success? |
| --- | --- | --- |
| `null` | Normal return nếu không có ngoại lệ | Không đủ thông tin |
| `Optional.empty()` | Normal return với container rỗng | Tùy hợp đồng |
| Danh sách rỗng `List.of()` | Normal return có object | Tùy hợp đồng |
| `false` | Normal return primitive/boxed | Tùy hợp đồng |
| `Result.failure("denied")` | Normal return một Result object | Có thể biểu thị từ chối nghiệp vụ |
| `void` hoàn tất | Normal completion, không có value | Tùy ý nghĩa thao tác |
| Ném `IllegalArgumentException` | Exceptional completion tại ranh giới | Không có normal result |
| Future chưa hoàn tất | Normal return một handle | Chưa biết task cuối thành công |

Không nên gán nhãn `SUCCESS` ở mọi event after-returning. Tên như `NORMAL_RETURN` hoặc `METHOD_COMPLETED` chính xác hơn nếu advice chỉ biết đường hoàn tất.

Nếu chính sách yêu cầu “nghiệp vụ thành công”, hãy diễn đạt cách tính theo từng hợp đồng: cờ `success` trong Result, mã HTTP, trạng thái persistence, completion của Future hoặc event miền. Một advice dùng chung cho nhiều API không tự biết ý nghĩa của từng kiểu giá trị.

## 11. Ngoại lệ: không có giá trị trả về bình thường

Khi một phương thức ném exception ra khỏi join point, không thể đọc một normal result của lần gọi ấy trong after-returning. Ví dụ:

~~~java
String load() {
    throw new IllegalStateException("unavailable");
}
~~~

Đây là đoạn minh họa, không có `main`. Một advice `after throwing` hoặc một `around` bắt và ném lại lỗi có thể quan sát exceptional exit nếu engine hỗ trợ. Nếu cần giữ hợp đồng, không nên biến lỗi thành `null` chỉ để tiếp tục luồng bình thường.

Các tình huống cần phân biệt:

- **Target ném lỗi nhưng tự catch và trả fallback:** join point quan sát ở ranh giới method ngoài có thể **normal return**.
- **Target ném lỗi ra khỏi method:** không có normal result; after-returning ở ranh giới ấy **không chạy**.
- **Advice after-returning tự ném lỗi:** target đã trả bình thường, nhưng caller có thể nhận ngoại lệ do advice. Nguồn lỗi khác nhau.
- **Around cố ý nuốt/biến đổi lỗi:** đây là chính sách điều khiển luồng, không còn là observer thuần túy.
- **`finally` trong target ném lỗi sau khi tính return:** kết quả cuối có thể là exceptional completion, không phải normal return đã dự kiến.

Khi dùng Reflection, `Method.invoke` có thể bọc lỗi do target ném trong `InvocationTargetException`. Nếu không bóc `getCause()` phù hợp, caller qua proxy có thể nhận loại lỗi không mong muốn. Tuy nhiên, không nên catch toàn bộ exception từ Reflection rồi mặc định coi chúng đều là lỗi nghiệp vụ: lỗi truy cập, ký kết API hoặc chính advice cũng có ý nghĩa riêng.

## 12. Thứ tự nhiều advice quyết định kết quả được nhìn thấy

Giả sử chuỗi:

~~~text
Caller
  |
[Outer around normalizer]
  |
[Inner after-returning observer]
  |
[Target] -> null
  |
Inner observer sees null
  |
Outer normalizer turns null -> fallback
  |
Caller sees fallback
~~~

Nếu đổi thứ tự hoặc chọn join point khác, observer có thể thấy `fallback` thay vì `null`. Do đó “giá trị trả về mà advice nhận” phải gắn với **ranh giới và thời điểm**.

Trường hợp phức tạp:

- Một `around` có thể trả cached result mà không gọi target; after-returning của wrapper bên ngoài có thể nhìn một normal return dù target không chạy.
- Một `around` khác có thể gọi `proceed` hai lần vì retry, khiến nhiều inner observations tương ứng với các attempt; outer observer có thể chỉ thấy result cuối.
- Một advice ném exception sau khi target hoàn tất bình thường, khiến outer layer quan sát lỗi dù inner layer đã quan sát normal return.
- Advice biến đổi kết quả có thể làm một phương thức khai báo trả primitive gặp lỗi khi chuyển đổi nếu output không tương thích.

Hãy mô tả precedence/ordering rõ theo engine AOP đang dùng và kiểm thử **giá trị thực sự caller nhận**, không chỉ kiểm tra log trong một advice đơn lẻ.

## 13. Bất đồng bộ: trả Future chưa phải trả dữ liệu cuối

Trong Java, phương thức:

~~~java
CompletableFuture<String> fetchAsync() {
    return new CompletableFuture<>();
}
~~~

đã **trả một đối tượng `CompletableFuture` bình thường**. After-returning ở ranh giới method có thể nhận handle đó ngay cả khi `future.isDone() == false`.

Nhưng “trả về Future” khác “tác vụ hoàn tất với `String`”:

1. **Return stage:** caller nhận `CompletableFuture<String>`; advice theo method normal return chạy tại đây.
2. **Completion stage:** Future có thể hoàn tất với value, hoàn tất ngoại lệ hoặc bị hủy vào một thời điểm sau.
3. **Consumption stage:** caller gọi `join()`, đăng ký callback hoặc sử dụng stage khác để đọc kết quả; exception tại đây không nhất thiết thoát trong lần gọi method tạo Future trước đó.

Nếu yêu cầu là log **giá trị cuối của tác vụ**, cần quan sát completion của Future bằng cơ chế như `whenComplete` hoặc một lớp instrumentation tương ứng:

~~~java
CompletableFuture<String> pending = startAsync();
pending.whenComplete((value, error) -> {
    if (error == null) {
        recordCompletionValue(value);
    } else {
        recordCompletionError(error);
    }
});
~~~

Đoạn trên là **minh họa không độc lập** vì `startAsync` và hai hàm `record...` là dịch vụ ứng dụng. `whenComplete` trả một stage mới; lỗi trong callback có thể ảnh hưởng stage phụ thuộc. Không tự giả định callback chạy trên thread của caller; cần xem ngữ cảnh, cancellation, propagation và chính sách lỗi của observer.

Không gọi `join()` ngay trong một after-returning chỉ để có dữ liệu cuối nếu nó không nằm trong hợp đồng: hành vi này có thể **chặn thread**, thay đổi latency và thứ tự lỗi.

## 14. Return types nâng cao: generics, erasure, covariant return và bridge

### 14.1. Generic return type

Với `List<String> names()`, chữ ký Java ở source có tham số kiểu `String`, nhưng thông tin runtime của generic chịu quy tắc **type erasure**. `Method.getReturnType()` thường trả kiểu thô `List.class`, còn `Method.getGenericReturnType()` có thể cung cấp metadata parameterized type nếu được lưu.

Advice chung không nên ép mọi phần tử thành `String` chỉ vì một khai báo generic trong tài liệu; cần tuân thủ hợp đồng type/metadata và kiểm tra ở ranh giới thích hợp.

### 14.2. Covariant return

Java có thể cho subclass override một phương thức với kiểu trả về hẹp hơn:

~~~java
class Base {
    Number value() { return 1; }
}
class Specialized extends Base {
    @Override
    Integer value() { return 2; }
}
~~~

Hai chữ ký nhìn ở base và subclass có thể có **return type khai báo khác nhau**. Một engine chọn call join point trên interface/base khác với execution join point trong implementation có thể phân giải metadata kiểu trả về khác nhau. Đừng tự áp đặt kết quả `Method.getReturnType()` của một `Method` lên mọi điểm gọi của cùng thao tác.

### 14.3. Bridge/synthetic methods

Trình biên dịch có thể tạo bridge methods để duy trì đa hình với generic/covariant return. Một bộ máy AOP ở mức bytecode có thể nhìn thấy phương thức không được viết trực tiếp trong source. Khi logging result hoặc đo số lần hoàn tất, hãy kiểm tra chính sách lọc bridge/synthetic của công cụ để tránh quan sát trùng hoặc nhầm signature.

### 14.4. Return type và kiểu của advice khác nhau

Return type của **target** không phải return type của **hàm advice**. Một hàm advice được engine yêu cầu trả `Object` hoặc `void` theo API riêng không có nghĩa nó thay đổi hợp đồng `int`, `String` hoặc `void` của phương thức được quan sát. Cần phân biệt ranh giới API của AOP engine với ranh giới public API của ứng dụng.

## 15. Lưu ý hiệu năng, bảo mật và tác dụng phụ

Kết quả trả về có thể là object rất lớn, collection chưa được materialize, stream lazy, object có `toString()` thực hiện I/O hoặc dữ liệu nhạy cảm. Lấy toàn bộ object graph để log có thể tốn hơn cả lời gọi nghiệp vụ.

Các hướng dẫn thực hành:

- Ghi **metadata có giá trị** (tên operation, loại outcome, số phần tử được phép đếm, trạng thái) thay vì toàn bộ payload.
- Không dùng `toString()` trên object tùy ý nếu mục tiêu chỉ là biết có result hay không.
- Không đọc hết `Stream` hay iterator chỉ để log kích thước: thao tác đó có thể tiêu thụ dữ liệu mà caller cần.
- Không sửa `List`, `Map` hoặc DTO mutable khi advice được mô tả là observer.
- Phân biệt lỗi của sink log/metrics với ngoại lệ của target; có chính sách fail-open/fail-closed rõ, không nuốt lỗi tùy tiện.
- Tránh log password, access token, dữ liệu khách hàng hoặc nội dung ngoại lệ có thể chứa dữ liệu riêng tư.
- Với result không đồng bộ, không block trong after-returning để “chờ dữ liệu thật”.
- Đảm bảo observer thread-safe nếu được dùng chung giữa nhiều request; tránh lưu result riêng một lần gọi vào field mutable singleton.
- Giới hạn cardinality nếu đưa loại return/result state vào nhãn metrics; không dùng mọi giá trị business làm label.
- Nếu result là object lazy hoặc resource-bound, chỉ quan sát những đặc điểm có thể đọc an toàn mà không kích hoạt việc tiêu thụ hoặc đóng resource.

## 16. Giới hạn theo cách can thiệp của công cụ AOP

Một biểu thức pointcut chọn được `void reset()` trên lý thuyết không đồng nghĩa advice chắc chắn chạy: điều đó còn phụ thuộc engine, loại join point và ranh giới thực thi.

| Bối cảnh | Điều cần xác minh |
| --- | --- |
| Proxy dựa trên interface | Lời gọi có đi qua proxy không? Interface có khai báo method đó không? |
| Proxy cần override method | Method `private`/`final` hoặc những modifier khác có bị giới hạn không? |
| Bytecode weaving | Lớp và loại join point có thực sự nằm trong vùng weaving được cấu hình không? |
| Method call vs method execution | Return type/metadata được hiểu ở caller hay implementation? |
| Self-invocation | `this.method()` có bỏ qua proxy không? |
| Method `void` | Engine có cho after-returning không cần binding return object không? |
| Generics/bridge | Tool có xem bridge/synthetic methods là join point riêng không? |
| Method trả Future | Tool quan sát method return hay completion của task? |
| Lỗi trong advice | Caller nhìn exception nào, có policy bỏ qua lỗi observer không? |

Không phải mọi công nghệ đều có cùng cú pháp, cùng phạm vi binding result hoặc cùng loại advice. Muốn biết chắc phải xem mô hình join point của engine đang dùng và viết integration test trên **đường gọi thực**, không chỉ gọi unit test của hàm advice.

## 17. Quy trình thiết kế advice xử lý kết quả

1. **Viết mục đích rõ:** chỉ đo số normal return, log trạng thái, hay chủ động biến đổi kết quả?
2. **Chọn join point/pointcut:** call/execution, method cụ thể, overload/annotation và đường can thiệp thực tế.
3. **Chọn loại advice ít quyền lực nhất:** after-returning để quan sát normal result; around nếu thật sự cần thay/điều khiển result.
4. **Phân loại return type:** `void`, primitive, tham chiếu có thể `null`, container, generic, Future.
5. **Xác minh binding:** engine có cung cấp result cho loại join point đó không? Khi `void` thì làm gì?
6. **Quy định null policy:** ghi nhận `null` hợp lệ, cảnh báo vi phạm hợp đồng hay normalize theo một chính sách chuyển đổi rõ.
7. **Bảo vệ hợp đồng caller:** giá trị, kiểu, exception, số lần target chạy và tài nguyên phải được giữ nguyên nếu chỉ quan sát.
8. **Hạn chế dữ liệu truy cập:** chỉ lấy fields/metadata đã cho phép; tránh serialize toàn bộ object.
9. **Tính đến async/lazy:** không coi Future return là task success; không tiêu thụ Stream cho log.
10. **Kiểm thử tích hợp:** cùng method qua proxy/weaving, đường trực tiếp, nhánh lỗi và nhiều wrapper khác thứ tự.

Một matrix kiểm thử cho code `AdviceReturnDataDemo`:

| Case | Loại hoàn tất | Kỳ vọng observer | Kỳ vọng caller |
| --- | --- | --- | --- |
| `fetch("A")` | Normal, `String` | `item:A` | `item:A` |
| `fetch("none")` qua `raw` | Normal, `null` | `<null>` | `null` |
| `fetch("none")` qua `transformed` | Normal bên trong + biến đổi bên ngoài | Observer trong thấy `<null>` | Caller thấy `fallback` |
| `sum(2,3)` | Normal, primitive `int` | `declared=int, value=5` | `5` |
| `reset()` | Normal, `void` | `declared=void, value=<void>` | Không có return value |
| `defer()` | Normal return Future pending | `Future(done=false)` | Nhận Future, hoàn tất sau |
| `crash()` | Exceptional exit | Không có `AFTER crash` | Nhận `IllegalStateException` gốc |
| Target gọi trực tiếp không qua proxy | Tùy target | Không có observer proxy | Theo hợp đồng target |

## 18. Các lỗi thường gặp

1. **Đồng nhất `void` với `null`:** Reflection adapter có thể biểu diễn cả hai qua `null`, nhưng ý nghĩa contract khác nhau.
2. **Giả định before advice đã đọc được return value:** kết quả chưa tồn tại.
3. **Cho rằng after-returning là mọi lần nghiệp vụ thành công:** `false` hoặc `Result.failure` vẫn có thể trả bình thường.
4. **Dùng `result.toString()` vô điều kiện:** lỗi khi `null` và có thể lộ dữ liệu.
5. **Return `null` từ around cho primitive:** phá hợp đồng trả `int`/`boolean`.
6. **Coi `Void` bằng `void`:** kiểu tham chiếu khác hoàn toàn từ khóa không trả giá trị.
7. **Đổi result mà không công bố:** caller nhận kết quả bất ngờ dù tên advice chỉ là logging.
8. **Sửa object mutable rồi nghĩ đó chỉ là quan sát:** caller có thể thấy đối tượng bị thay đổi.
9. **Coi `Optional.empty()` là không có normal return:** nó là một object/container hợp lệ.
10. **Coi Future chưa hoàn tất là task thành công:** mới chỉ có handle được trả bình thường.
11. **Làm `join()` trong after-returning:** có thể block và thay đổi ngữ nghĩa async.
12. **Không bóc `InvocationTargetException` khi dùng reflection:** caller nhìn sai nguồn lỗi.
13. **Không kiểm tra overload, bridge và loại join point:** chọn nhầm phương thức hoặc quan sát trùng.
14. **Giả định proxy nhìn được self-invocation hoặc private method:** phải kiểm thử ranh giới thật.
15. **Ghi mọi result vào log:** chi phí, rò dữ liệu, tiêu thụ lazy Stream và side effect ngoài ý định.
16. **Để lỗi metrics tự che target exception:** làm caller nhận lỗi sai và sai số liệu.
17. **Bỏ qua thứ tự các around wrapper:** observer có thể thấy dữ liệu gốc khác caller.
18. **Chỉ unit test observer mà không integration test AOP:** chưa chứng minh advice chạy đúng điểm.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Phương thức khai báo `String fetch()` trả `null`. Có thể có after-returning advice không?  
**Trả lời:** Có, vì target hoàn tất bình thường; advice phải xử lý `null` an toàn.

**Câu 2.** Phương thức `void reset()` không trả object. Có thể đo thời gian hoặc đếm normal completion không?  
**Trả lời:** Có, nếu engine hỗ trợ join point và advice tương ứng; không cần bind một result object không tồn tại.

**Câu 3.** `Void task()` và `void task()` giống nhau hoàn toàn không?  
**Trả lời:** Không. `Void` là reference type, có thể trả `null`; `void` không trả giá trị.

**Câu 4.** Vì sao một observer dùng `Method.invoke()` nên kiểm tra `getReturnType()` trước khi diễn giải `null`?  
**Trả lời:** Vì `Method.invoke` trả `null` cả khi method `void` và khi method tham chiếu thực sự trả `null`.

**Câu 5.** Nếu `around` đổi `null` thành `fallback`, after-returning ở bên trong và caller bên ngoài có thấy cùng result không?  
**Trả lời:** Không bắt buộc; observer trong có thể thấy `null`, caller ngoài thấy `fallback`.

**Câu 6.** Khi method khai báo `int` và adapter nhận một `Integer`, kiểu trả về method có đổi thành `Integer` không?  
**Trả lời:** Không; đây là boxing trong adapter; kiểu khai báo vẫn `int`.

**Câu 7.** Method trả `CompletableFuture` pending. Sau khi after-returning chạy, task đã hoàn tất chưa?  
**Trả lời:** Chưa chắc. Method đã trả handle, còn task completion là sự kiện khác.

**Câu 8.** Vì sao không dùng kết quả after-returning để tự kết luận mọi thao tác là business success?  
**Trả lời:** Nó chỉ xác nhận normal completion của ranh giới; `null`, `false`, `Optional.empty()` và `Result.failure` có ý nghĩa miền khác nhau.

**Câu 9.** Advice chỉ quan sát có nên ghi toàn bộ result vào log không?  
**Trả lời:** Không mặc định; chỉ ghi metadata/dữ liệu được phép, tránh chi phí, rò thông tin, thay đổi object hoặc tiêu thụ dữ liệu lazy.

## 20. Tổng kết

**Dữ liệu trả về trong advice phải được hiểu theo cả kiểu khai báo, giá trị runtime và cách join point hoàn tất.** Method `void` không có result object nhưng vẫn có thể hoàn tất bình thường; method kiểu tham chiếu có thể trả `null`; method primitive có thể được boxing trong adapter; Future trả bình thường không đồng nghĩa tác vụ hoàn tất.

Hãy dùng **after-returning** khi muốn quan sát normal result theo khả năng binding của engine, **after-throwing** khi cần quan sát ngoại lệ, và **around** chỉ khi có hợp đồng thực sự yêu cầu điều khiển hoặc thay đổi kết quả. Với advice thuần quan sát, bảo toàn return value, exception, dữ liệu đầu vào và số lần thực thi target. Cuối cùng, kiểm thử đủ `void`/`null`/primitive/reference/async/exception và ranh giới proxy/weaving thực để bảo đảm dữ liệu advice nhìn thấy là đúng, an toàn và không gây tác dụng phụ ngoài ý định.