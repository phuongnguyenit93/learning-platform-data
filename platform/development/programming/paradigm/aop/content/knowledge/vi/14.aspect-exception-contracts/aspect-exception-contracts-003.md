# Giữ nguyên hoặc chuyển đổi ngoại lệ có chủ đích trong AOP

## 1. Ngoại lệ là một phần của hợp đồng

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, *advice* có thể quan sát hoặc bao quanh một **join point** được **pointcut** lựa chọn. Khi phương thức thành công, caller nhận **giá trị trả về**; khi thất bại, caller nhận **ngoại lệ** hoặc một cách biểu diễn thất bại khác. Cả hai cùng thuộc **hợp đồng hành vi**.

Một aspect có thể ghi nhận lỗi, truyền tiếp nguyên trạng, đổi lỗi hạ tầng thành lỗi domain, thử lại hoặc trả kết quả dự phòng. Nhưng việc “bắt được exception” **không tạo quyền thay đổi ngữ nghĩa của API tùy ý**. Nếu method vốn báo `IOException` mà advice biến thành `null` hoặc một exception khác không được hợp đồng chấp nhận, caller có thể xử lý sai dữ liệu, sai quyền hoặc sai trạng thái giao dịch.

**Nguyên tắc:** **Giữ nguyên ngoại lệ gốc** là lựa chọn mặc định khi không có lý do cụ thể để thay. **Chuyển đổi** chỉ nên xảy ra tại ranh giới trừu tượng có chính sách rõ, giữ được chẩn đoán, kiểu dữ liệu và những điều caller có quyền kỳ vọng.

> Bài này trình bày **AOP cơ bản và nâng cao nói chung**, không phụ thuộc bất kỳ công cụ cụ thể nào. “Around”, “after-throwing”, “proceed”, “method call/execution” là khái niệm AOP; API và quyền thay đổi outcome của từng công cụ có thể khác. Java 17+ được dùng để minh họa những giới hạn kiểu ngoại lệ có thể kiểm chứng.

## 2. Năm quyết định khác nhau đối với một Throwable

| Quyết định | Outcome tới caller | Khi phù hợp |
| --- | --- | --- |
| **Preserve** | Chính ngoại lệ gốc được throw | Lỗi vẫn đúng contract, advice chỉ quan sát |
| **Observe and rethrow** | Lỗi gốc sau khi log/metric/audit | Giữ failure semantics, thêm observability |
| **Translate / map** | Ngoại lệ mới có ngữ nghĩa khác, chứa `cause` gốc | Đi qua ranh giới storage → domain hoặc domain → API |
| **Recover** | Giá trị fallback hợp lệ thay cho exception | Contract cho phép phục hồi từ loại lỗi cụ thể |
| **Retry** | Nhiều lần `proceed` rồi return/throw cuối | Lỗi tạm thời, thao tác an toàn lặp, có giới hạn |

Một advice cũng có thể **chủ động ném lỗi mới** để chặn thao tác theo policy, nhưng đó là loại quyết định khác với việc target đã ném lỗi và advice chỉ đang xử lý nó.

### Mô hình outcome

```text
                   proceed()
                       |
                +------+------+
                |             |
         Return(value)    Throw(original)
                |             |
          preserve/map    preserve/map
              value       recover/retry
                |             |
                +------+------+
                       |
             Final outcome to caller
```

Việc thay `Throw(error)` bằng `Return(value)` là một thay đổi lớn của **hợp đồng nghiệp vụ**, ngay cả khi `value` đúng Java type.

## 3. Đọc hợp đồng của phương thức trước khi xử lý exception

Xét:

```java
// Khai báo minh họa, không phải chương trình độc lập.
String readDocument(String id) throws java.io.IOException;
```

Caller có thể dựa vào các điều kiện: dữ liệu trả về phải hợp lệ; lỗi I/O được truyền bằng `IOException` hoặc subtype; một tài liệu không tồn tại có thể có nghĩa riêng; side effect không được giả vờ hoàn tất.

**`throws` chỉ mô tả một phần contract.** Java checked exception kiểm tra compile-time cho một số loại lỗi; nó không mô tả đầy đủ nullability, semantic fallback, tính idempotent hay lỗi runtime.

| Nhóm Throwable | Ví dụ | Lưu ý |
| --- | --- | --- |
| Checked exception | `IOException`, `SQLException` | Cần tính tương thích với declared throws và caller |
| Unchecked exception | `IllegalArgumentException`, `IllegalStateException` | Không cần kê `throws`, nhưng vẫn thuộc behavior contract |
| Error | `OutOfMemoryError`, `LinkageError` | Không nên recover thành success trong một catch tổng quát |

Đừng dùng `catch (Throwable)` để biến mọi `Error` thành giá trị dự phòng. Một around advice có thể bắt `Throwable` nhằm **cleanup và rethrow đúng object**, nhưng quyền quan sát rộng không có nghĩa mọi lỗi đều phục hồi an toàn.

## 4. Giữ nguyên bằng `throw original`

Một advice chỉ quan sát thất bại có thể viết:

```java
// Pseudocode của around advice; proceed là API giả định của AOP engine.
try {
    return proceed();
} catch (Throwable original) {
    recordFailure(original);
    throw original;
}
```

Nếu `recordFailure` không ném lỗi khác, `throw original` bảo toàn:

- Loại Throwable và object identity.
- Message và `cause`.
- Stack trace đã gắn với original.
- Danh sách suppressed exceptions.
- Metadata riêng trên Throwable object.

Không tạo exception mới chỉ để thêm một đoạn message nếu caller đang cần đúng subtype hoặc identity gốc.

### Những phép biến đổi khác nhau

```java
// Minh họa đặt trong scope thích hợp.
throw original; // Giữ chính object gốc.

// Các biểu thức sau CHỈ nên dùng khi có quyết định mapping rõ:
// throw new IOException("mapped", original);
// throw new IllegalStateException("domain failure", original);
```

`new IOException("mapped", original)` giữ cause nhưng tạo **object exception mới** với stack trace của điểm mapping. `new IllegalStateException(...)` còn đổi nhóm checked/unchecked mà caller nhìn thấy.

**Không nhầm “có cause” với “không đổi ngoại lệ”.**

## 5. Ghi log rồi truyền tiếp: phân biệt observability và outcome

```text
Target throws IOException
          |
          v
Advice records event
          |
          v
Caller receives IOException
```

Một logging advice đúng kiểu quan sát **không bắt buộc làm thay đổi** return/throw. Nhưng bản thân logger hoặc audit sink có thể ném lỗi. Nếu nó thất bại ở `catch` hoặc `finally`, caller có thể thấy lỗi sink **thay vì ngoại lệ target**.

Hãy có chính sách:

- Với metric/log phụ trợ, có thể cần cô lập lỗi sink theo contract.
- Với audit bắt buộc, lỗi audit có thể phải làm thao tác thất bại.
- Không im lặng nuốt mọi Throwable, nhất là lỗi nghiêm trọng.
- Không log argument/return chứa mật khẩu, token hoặc dữ liệu nhạy cảm một cách vô điều kiện.
- Ghi riêng **lỗi gốc** và **lỗi ghi nhận** khi chẩn đoán.

### `finally` không bảo đảm preserve nếu chính nó throw

```text
Target throws OriginalError
    |
finally cleanup throws CleanupError
    |
Caller may receive CleanupError
```

**Dù có `finally`, outcome vẫn có thể bị thay đổi.** Cần thiết kế cleanup đúng, tránh che thất bại chính bằng một lỗi phụ không mong đợi.

## 6. Translation tại đúng abstraction boundary

Một chuyển đổi hợp lý:

```text
Storage method
  -> IOException("connection reset")
Domain boundary
  -> DocumentUnavailableException(cause=IOException)
Application caller
  -> xử lý "tài liệu chưa thể truy cập"
```

Một domain caller có thể không nên phụ thuộc vào chi tiết filesystem hoặc driver. Nhưng conversion phải có policy rõ:

1. Lỗi gốc nào thuộc category này?
2. Exception mới thể hiện ý nghĩa nghiệp vụ gì?
3. Caller biết bắt loại mới không?
4. Có cần giữ subtype phân biệt not-found, timeout, access-denied?
5. Cause chain có còn nguyên không?
6. Error code/retryability có được bảo toàn?
7. Message public có lộ thông tin hạ tầng không?
8. Có aspect nào đã map trước đó không?

### Mapping tốt giữ `cause`

```java
// Ví dụ Java trong method được phép throws IOException.
try {
    return storageRead();
} catch (java.io.IOException original) {
    throw new java.io.IOException(
            "Cannot load requested document",
            original);
}
```

Hàm `storageRead()` là hàm nghiệp vụ giả định; đoạn trên minh họa phép translation, chưa phải một chương trình độc lập. `getCause()` trên exception mới dẫn về original.

**Đừng chỉ copy chuỗi `original.getMessage()` rồi bỏ object Throwable.** Message có thể đổi theo locale hoặc version và không thay được cause.

## 7. Duy trì subtype và phân loại lỗi

`FileNotFoundException` là subtype của `IOException`. Nếu map tất cả `IOException` thành superclass `IOException` mới:

- Caller vẫn có thể bắt `IOException`.
- Nhưng caller bắt riêng `FileNotFoundException` có thể không còn bắt được loại đã phát sinh từ target.
- Các policy retry và metric dựa vào subtype có thể thay đổi.

Giữ cùng superclass **không nhất thiết giữ nguyên hợp đồng chi tiết**. Nếu domain cần phân biệt not-found, forbidden, transient outage và corrupt data, mapping nên giữ phân biệt ấy bằng một taxonomy rõ.

Không phân loại theo `getMessage().contains("timeout")` nếu có type/error code đáng tin cậy; chuỗi message không phải giao thức ổn định.

## 8. `cause` và suppressed exceptions

**Cause chain** mô tả quan hệ “ngoại lệ mới được tạo vì lỗi nào”. **Suppressed exceptions** mô tả những lỗi bổ sung, thường thấy khi dọn resource bằng `try-with-resources`.

```java
// Ví dụ ý tưởng; Resource là AutoCloseable do ứng dụng định nghĩa.
try (Resource resource = open()) {
    work(resource);
} // Nếu work và close đều lỗi, close có thể được suppressed.
```

Nếu mapping tạo `DomainError(message, original)`, suppressed exception gắn với `original` vẫn có thể được truy vết **qua cause chain**. Không mặc định `mapped.getSuppressed()` tự chứa cùng danh sách với `original.getSuppressed()`.

Một phép chuyển đổi giữ cause nhưng **không tự đảm bảo** cùng object identity hay suppressed trực tiếp. Khi cần thông tin chẩn đoán, đọc đúng từng tầng Throwable; đừng tự copy/cắt chuỗi stack trace.

## 9. Khả năng thay lỗi của từng loại advice

| Advice | Thích hợp | Điều không nên mặc định |
| --- | --- | --- |
| Before | Precondition, policy chặn trước | Đã có lỗi target để quan sát |
| After-returning | Quan sát thành công | Có thể thay lỗi target bằng return bất kỳ |
| After-throwing | Log/metric/phân loại lỗi ném ra | Có thể suppress lỗi chỉ bằng `return` của advice |
| After/finally | Dọn context, đo duration | Cleanup không bao giờ làm thay outcome |
| Around | Bao quanh `proceed`, preserve/map/recover/retry nếu được hỗ trợ | Mọi engine cho thay return/checked exception vô hạn |

**After-throwing thường chỉ được quyền quan sát lỗi**, còn **around** hay hook điều khiển outcome mới phù hợp khi cần biến throw thành return. Có engine cho advice ném exception mới; khả năng cụ thể phải kiểm theo công cụ.

**Thứ tự advice** cũng ảnh hưởng: nếu một outer around không `proceed`, những advice bên trong có thể không chạy và target có thể chưa hề phát sinh lỗi.

## 10. Ví dụ Java 17+ chạy được: preserve, map, recover và sai checked contract

Ví dụ dùng **Java Dynamic Proxy** để mô phỏng interceptor AOP, không dùng thư viện ngoài. Nó làm rõ:

- **PRESERVE:** caller nhận đúng object `IOException` gốc.
- **MAP_IO:** tạo `IOException` mới, giữ nguyên `cause`.
- **RECOVER_MISSING:** chỉ phục hồi loại lỗi tài liệu không tồn tại bằng một `String` dự phòng.
- **BAD_CHECKED:** handler ném `SQLException` không thuộc declared throws; Java Dynamic Proxy bọc thành `UndeclaredThrowableException`.

`BAD_CHECKED` là tình huống **cố tình vi phạm** để học về contract, không phải phương pháp triển khai nên dùng.

### 10.1. Tệp `AdviceExceptionContractDemo.java`

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;
import java.sql.SQLException;

public class AdviceExceptionContractDemo {
    private static final IOException SENTINEL = new IOException("known");

    interface DocumentPort {
        String load(String key) throws IOException;
        String parse(String input);
    }

    static final class Documents implements DocumentPort {
        @Override
        public String load(String key) throws IOException {
            System.out.println("target.load " + key);
            return switch (key) {
                case "missing" ->
                        throw new FileNotFoundException("missing: " + key);
                case "offline" -> throw new IOException("offline");
                case "same" -> throw SENTINEL;
                default -> "DOC:" + key;
            };
        }

        @Override
        public String parse(String input) {
            System.out.println("target.parse " + input);
            if ("bad".equals(input)) {
                throw new IllegalArgumentException("invalid input");
            }
            return input.trim();
        }
    }

    enum Policy { PRESERVE, MAP_IO, RECOVER_MISSING, BAD_CHECKED }

    static final class Advice implements InvocationHandler {
        private final DocumentPort target;
        private final Policy policy;

        Advice(DocumentPort target, Policy policy) {
            this.target = target;
            this.policy = policy;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            String name = method.getName();
            System.out.println("advice.before " + name);
            try {
                try {
                    Object value = method.invoke(target, args);
                    System.out.println("advice.return " + name);
                    return value;
                } catch (InvocationTargetException wrapped) {
                    Throwable original = wrapped.getCause();
                    System.out.println("advice.throw "
                            + original.getClass().getSimpleName());

                    if (policy == Policy.MAP_IO
                            && original instanceof IOException) {
                        throw new IOException(
                                "mapped storage failure", original);
                    }

                    if (policy == Policy.RECOVER_MISSING
                            && original instanceof FileNotFoundException
                            && "load".equals(name)) {
                        System.out.println("advice.recover missing");
                        return "DEFAULT";
                    }

                    if (policy == Policy.BAD_CHECKED
                            && original instanceof IOException) {
                        throw new SQLException(
                                "different checked", original);
                    }

                    throw original;
                }
            } finally {
                System.out.println("advice.finally " + name);
            }
        }
    }

    static DocumentPort wrap(DocumentPort target, Policy policy) {
        return (DocumentPort) Proxy.newProxyInstance(
                DocumentPort.class.getClassLoader(),
                new Class<?>[]{DocumentPort.class},
                new Advice(target, policy));
    }

    public static void main(String[] args) throws IOException {
        DocumentPort target = new Documents();

        System.out.println("== preserve ==");
        DocumentPort keep = wrap(target, Policy.PRESERVE);
        System.out.println("caller " + keep.load("ok"));

        try {
            keep.load("same");
        } catch (IOException error) {
            System.out.println(
                    "caller sameIdentity " + (error == SENTINEL));
        }

        try {
            keep.parse("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("caller runtime " + error.getMessage());
        }

        System.out.println("== map ==");
        try {
            wrap(target, Policy.MAP_IO).load("offline");
        } catch (IOException error) {
            System.out.println(
                    "caller mapped " + error.getMessage());
            System.out.println(
                    "caller cause " + error.getCause().getMessage());
        }

        System.out.println("== recover ==");
        System.out.println("caller "
                + wrap(target, Policy.RECOVER_MISSING).load("missing"));

        System.out.println("== bad checked ==");
        try {
            wrap(target, Policy.BAD_CHECKED).load("offline");
        } catch (UndeclaredThrowableException error) {
            System.out.println("caller wrapper "
                    + error.getClass().getSimpleName());
            System.out.println("caller underlying "
                    + error.getUndeclaredThrowable()
                            .getClass().getSimpleName());
        }
    }
}
```

### 10.2. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 AdviceExceptionContractDemo.java
java AdviceExceptionContractDemo
```

**Standard output đã được đối chiếu bằng JDK:**

```text
== preserve ==
advice.before load
target.load ok
advice.return load
advice.finally load
caller DOC:ok
advice.before load
target.load same
advice.throw IOException
advice.finally load
caller sameIdentity true
advice.before parse
target.parse bad
advice.throw IllegalArgumentException
advice.finally parse
caller runtime invalid input
== map ==
advice.before load
target.load offline
advice.throw IOException
advice.finally load
caller mapped mapped storage failure
caller cause offline
== recover ==
advice.before load
target.load missing
advice.throw FileNotFoundException
advice.recover missing
advice.finally load
caller DEFAULT
== bad checked ==
advice.before load
target.load offline
advice.throw IOException
advice.finally load
caller wrapper UndeclaredThrowableException
caller underlying SQLException
```

### 10.3. Đọc nhánh preserve

`Documents.load("same")` ném **`SENTINEL`**. Reflection bọc lỗi target bằng `InvocationTargetException`; handler lấy `wrapped.getCause()` rồi `throw original`. Vì caller method khai báo `throws IOException`, proxy truyền Throwable `IOException` phù hợp. Phép so sánh `error == SENTINEL` trả `true`.

**SENTINEL chỉ dùng cho bài kiểm thử identity.** Trong sản xuất, không nên tái sử dụng một object Throwable chung cho những lỗi độc lập vì stack trace/state/diagnostics có thể gây nhầm.

### 10.4. Đọc nhánh mapping

Policy `MAP_IO` nhận `IOException("offline")` và tạo `IOException("mapped storage failure", original)`. `IOException` mới vẫn phù hợp declared throws, nhưng **khác object gốc**. `getCause()` dẫn về lỗi ban đầu, giúp caller/diagnostics biết nguyên nhân.

### 10.5. Đọc nhánh recover

`FileNotFoundException` là subtype của `IOException`. Advice chỉ recover khi error đúng subtype và method có tên `load`, rồi trả `"DEFAULT"`. Đây là một **quyết định nghiệp vụ giả định**. Nếu contract coi “thiếu tài liệu” là lỗi bắt buộc hoặc fallback có thể gây hiểu nhầm, policy này **không được dùng**, dù Java type vẫn hợp lệ.

### 10.6. Đọc nhánh sai checked exception

Policy `BAD_CHECKED` cố ném `SQLException` từ handler cho `DocumentPort.load`. Method interface chỉ khai báo `throws IOException`, không khai báo `SQLException`. **Java Dynamic Proxy** sẽ bọc checked exception không được khai báo tương thích trong `UndeclaredThrowableException`.

Đây là **quy tắc của Java Dynamic Proxy**, không phải lời khẳng định mọi kỹ thuật bytecode weaving có cùng cách bọc. Cần kiểm thử engine/interceptor thực tế.

### 10.7. Vì sao `finally` xuất hiện trên mọi đường?

`finally` của handler chạy khi target return, khi propagate/map và khi recover. Nó chỉ in log để minh họa. Nếu `finally` ném một exception khác, Throwable caller thấy có thể bị thay — do đó code sản xuất phải thiết kế cleanup và logging failure policy có chủ đích.

### 10.8. Giới hạn demo

Đây là proxy trên interface. **Lời gọi trực tiếp vào target bỏ qua handler**. Ví dụ không triển khai pointcut DSL, không weave bytecode target, không retry, không xử lý async completion. Nó chứng minh contract trong một cơ chế Java SE cụ thể, không đại diện mọi engine AOP.

## 11. Checked exception và giới hạn của API

`String load(String) throws IOException` cho phép caller bắt `IOException` và subtype. Một handler khai báo `throws Throwable` **không tự mở rộng danh sách checked exceptions** của method interface.

Trong Java:

- `IOException` có thể được ném từ `load`.
- `FileNotFoundException` có thể được ném vì thuộc `IOException`.
- `SQLException` không thuộc hệ `IOException`.
- `RuntimeException`/`Error` không phải declared checked exceptions.
- Override method chịu quy tắc Java riêng về danh sách checked exceptions được khai báo.
- Caller có thể viết `catch` cho subtype có ý nghĩa cụ thể.

Nếu map `FileNotFoundException` thành superclass `IOException` khác, caller bắt subtype có thể ngừng hoạt động như trước. **Phải phân biệt hợp lệ tại proxy boundary với bảo toàn toàn bộ contract đã được tài liệu hóa.**

## 12. Wrapper exception: unwrap có chọn lọc

| Wrapper | Nơi thường gặp | Cần lưu ý |
| --- | --- | --- |
| `InvocationTargetException` | `Method.invoke` hoặc constructor reflection | `getCause()` là Throwable target thực sự ném |
| `UndeclaredThrowableException` | Java Dynamic Proxy với checked exception ngoài declared throws | `getUndeclaredThrowable()` lấy lỗi bên trong |
| `ExecutionException` | `Future.get()` | Lỗi tác vụ nằm trong `getCause()` |
| `CompletionException` | Completion stage hoặc `join()` | Có thể là lớp bọc cho thất bại async |
| Domain exception wrapper | Một boundary do ứng dụng quy định | Có thể là chính hợp đồng public, không nên tự unwrap để bỏ domain semantics |

Một helper Reflection hợp lý:

```java
// Ví dụ minh họa Java, đặt ở class phù hợp.
static Object invokeTarget(
        java.lang.reflect.Method method,
        Object target, Object[] args) throws Throwable {
    try {
        return method.invoke(target, args);
    } catch (java.lang.reflect.InvocationTargetException wrapped) {
        throw wrapped.getCause();
    }
}
```

Không viết quy tắc chung “lặp `getCause()` tới tận cuối rồi ném root cause” cho mọi boundary. Wrapper có thể mang **ngữ nghĩa contract**, và unwrap hết có thể đổi taxonomy caller nhận. Lỗi do chính Reflection sai quyền truy cập/đối số cũng phải được phân biệt với lỗi target.

## 13. Không nuốt lỗi bằng fallback tùy tiện

```java
// Pseudocode KHÔNG khuyến nghị.
try {
    return proceed();
} catch (Exception ignored) {
    return null;
}
```

Những vấn đề có thể xảy ra:

- `null` vi phạm contract non-null.
- Method trả primitive có thể gây lỗi unboxing.
- Lỗi mất quyền hoặc hạ tầng offline bị hiểu thành “không có dữ liệu”.
- Side effects có thể đã chạy nhưng caller tưởng thành công.
- Monitoring không thấy lỗi, stack trace bị mất.
- Một ngoại lệ từ logger/cleanup vẫn có thể che hoặc tạo lỗi khác.

Một fallback hợp lý chỉ được áp dụng **cho loại lỗi và method cụ thể**, với dữ liệu dự phòng được xác thực. Trả `Optional.empty()` chỉ đúng nếu “không tìm thấy” là trạng thái hợp lệ, không phải cách che mọi lỗi kết nối.

## 14. Phân loại lỗi theo ngữ nghĩa nghiệp vụ

Những loại lỗi cần được phân biệt:

1. **Validation:** input hoặc invariant sai; thường không retry.
2. **Not-found:** resource không tồn tại; có thể map hoặc recover theo contract.
3. **Authorization/security:** bị từ chối; không recover thành “cho phép”.
4. **Transient infrastructure:** có thể retry sau backoff nếu thao tác idempotent.
5. **Permanent infrastructure:** cấu hình/permission/format sai, retry vô ích.
6. **Programming bug:** cast sai, trạng thái null bất hợp lệ; không giấu thành lỗi “tạm thời”.
7. **Cancellation/interruption:** tín hiệu điều phối task, cần xử lý riêng.
8. **VM/system failure:** `Error` hoặc lỗi nghiêm trọng, thường cần propagate.

Một advice chung bắt mọi `Exception` rồi biến thành một `DomainException` vô danh làm mất thông tin phân loại. Nếu public boundary cần ẩn chi tiết hạ tầng, nên cung cấp **error code/taxonomy ổn định** thay cho việc chỉ copy message.

## 15. Retry có điều kiện: khác với mapping

Một around advice có thể gọi `proceed` nhiều lần khi error được xác định là tạm thời:

```java
// Pseudocode minh họa; API proceed và exception tự định nghĩa.
int attempt = 0;
while (true) {
    attempt++;
    try {
        return proceed();
    } catch (TransientFailure error) {
        if (attempt >= maxAttempts) {
            throw error;
        }
        waitBeforeRetry(attempt);
    }
}
```

Các yêu cầu:

- **Attempt count** thuộc invocation hiện tại, không là field shared trên singleton aspect.
- Có giới hạn số lần thử và deadline.
- Có backoff hợp lý.
- Không retry lỗi validation/authorization.
- Phải hiểu liệu target **đã tạo side effect** trước khi throw.
- Có idempotency key hoặc cơ chế chống lặp cho thao tác quan trọng.
- Cần chính sách xử lý cancellation/interrupt.
- Cuối cùng preserve hay map exception cũng phải đúng contract caller.

Retry thành công **không có nghĩa các attempt trước không có side effect**. Một thao tác thanh toán có thể đã ghi nhận debit nhưng timeout trước khi phản hồi; retry bừa có nguy cơ ghi hai lần.

### Advice ordering ảnh hưởng retry

```text
OuterMapping
    |
    Retry
      |
      Target throws IOException
```

Retry ở trong mapper có thể thấy raw `IOException`. Đảo thứ tự có thể khiến retry chỉ thấy domain exception đã map. Điều kiện chọn retry vì vậy phụ thuộc **precedence** của các around advice.

## 16. Async: lỗi sau khi method đã return

`CompletableFuture<String> fetchAsync()` có thể trả một **future object bình thường**; task phía sau mới complete exceptionally. Một after-throwing advice **đồng bộ** quanh `fetchAsync()` chưa chắc thấy lỗi completion.

```text
Method call -> Return(CompletableFuture<String>)
                    |
                    v
          Later completion:
           value | error | cancel
```

### `exceptionally` là recovery

```java
// Minh họa khi original là CompletableFuture<String>.
java.util.concurrent.CompletableFuture<String> recovered =
        original.exceptionally(error -> "DEFAULT");
```

Stage mới có thể trở thành success với `"DEFAULT"`, do đó **làm thay đổi outcome**. Chỉ dùng khi contract async cho phép fallback.

### `whenComplete` dùng để quan sát nhưng vẫn cần thận trọng

```java
// Minh họa khi original là CompletableFuture<String>.
java.util.concurrent.CompletableFuture<String> observed =
        original.whenComplete((value, error) -> {
            if (error != null) {
                recordFailure(error);
            }
        });
```

`whenComplete` trả stage phụ. Nếu callback `recordFailure` ném lỗi, semantics completion của stage mới có thể bị ảnh hưởng. Nếu chỉ cần quan sát, phải kiểm soát lỗi sink và cancellation.

`join()` thường có thể báo thất bại qua `CompletionException`; `get()` thông thường qua `ExecutionException`. Đừng nhầm wrapper async với exception target ném đồng bộ trước lúc method trả future.

## 17. Interrupt và cancellation không phải lỗi retry thông thường

Nếu gặp `InterruptedException` trong blocking operation:

- Có thể **propagate** theo checked contract.
- Nếu bắt và không propagate vì API boundary yêu cầu conversion, thường cần **khôi phục interrupt flag** khi phù hợp: `Thread.currentThread().interrupt()`.
- Không tiếp tục retry vô hạn hoặc chuyển thành success giả.
- Hành vi cancellation của future/task có semantics riêng, không tự có nghĩa “dữ liệu không tồn tại”.

```java
// Đoạn Java minh họa trong method thích hợp.
try {
    performBlockingWork();
} catch (InterruptedException original) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", original);
}
```

`performBlockingWork()` là tên hàm giả định phục vụ giải thích, không phải API Java SE. Đây là **một quyết định conversion**; không áp dụng máy móc nếu method đã có thể khai báo `throws InterruptedException` và caller cần tín hiệu checked gốc.

## 18. `Error` và cleanup

Advice có thể bắt `Throwable` để đảm bảo dọn resource hoặc truyền tiếp nguyên trạng, nhưng không nên mặc nhiên recover `OutOfMemoryError`, `LinkageError`, `StackOverflowError` thành giá trị bình thường. Hệ thống có thể đang ở trạng thái không an toàn để chạy tiếp.

Trong tình huống nghiêm trọng:

- Tránh logging/serialization tạo quá nhiều resource mới.
- Giữ cleanup tối thiểu theo khả năng thực tế.
- Không làm mất Throwable nghiêm trọng bởi một exception mới không cần thiết.
- Propagate theo chính sách runtime phù hợp.
- Không dùng blanket catch để che lỗi trong production.

## 19. Nhiều aspect nhìn thấy những lỗi khác nhau

Một chuỗi:

```text
AuditAround
  |
  RetryAround
    |
    MappingAround
      |
      Target
```

Một lần target thất bại không có nghĩa tất cả advice nhìn thấy cùng exception:

- Target ném `IOException`.
- Mapper biến thành `DocumentUnavailable`.
- Retry ở ngoài thấy `DocumentUnavailable` chứ không phải lỗi gốc.
- Audit ở ngoài ghi lỗi cuối cùng hoặc success nếu outer recover.
- Nếu một around ngoài **không proceed**, những advice bên trong không chạy.

Cần xác định **ai sở hữu mapping, ai sở hữu retry, ai ghi raw failure và ai ghi final caller outcome**. Nếu mọi aspect đều log full stack trace hoặc map lại, dễ có log trùng và cause chain nhiễu.

### Double wrapping

```text
DomainUnavailable("outer")
  caused by DomainUnavailable("inner")
    caused by IOException("offline")
```

Nếu hai layer cùng map một lỗi vào cùng domain taxonomy mà không thêm semantics mới, chuỗi wrapper có thể vô ích. Hãy map tại **boundary có chủ đích**, không “mỗi method đều thêm một wrapper”.

## 20. Lỗi target, lỗi advice và lỗi infrastructure

Một exception có thể phát sinh ở:

- **Target:** business/dependency thực sự lỗi.
- **Before advice:** validation hoặc authorization từ chối.
- **Around advice:** policy retry, mapping hoặc bug.
- **After/finally advice:** logging, cleanup hoặc serialization hỏng.
- **Proxy/Reflection infrastructure:** invoke sai method, access, cast/checked compatibility.
- **Bytecode weaving/module loading:** verify/link/runtime helper không phù hợp.
- **Async continuation:** executor/callback/stage thất bại về sau.

Không map lỗi `IllegalAccessException` do interceptor cấu hình sai thành “tài liệu không tồn tại”. Khi debug, cần xác định **điểm exception được tạo**, số lần `proceed`, thứ tự advice, cause chain và giá trị cuối caller quan sát.

## 21. Return contract khi recover

Một advice có thể trả fallback nếu API cho phép, nhưng phải bảo toàn **return type** lẫn nghiệp vụ:

| Return type | Fallback có thể phù hợp | Rủi ro |
| --- | --- | --- |
| `String` | Chuỗi hợp lệ theo contract | `null` hoặc text mặc định làm sai nghĩa |
| `int` | Primitive đúng miền giá trị | `null` qua proxy gây unboxing error; `0` có thể nghĩa “hết hàng” |
| `Optional<T>` | `Optional.empty()` khi thật sự not-found | Không thay database outage bằng empty |
| `List<T>` | Danh sách đã xác thực | List rỗng có thể che timeout |
| `CompletableFuture<T>` | Stage/future đúng kiểu | Không trả trực tiếp object `T` cho caller |
| `void` | Không có giá trị caller nhận | Không thể báo thành công bằng một object return |
| Generic `T` | Giá trị phù hợp kiểu caller dùng | Type erasure có thể hoãn lỗi cast |

Một fallback **hợp lệ về Java type** vẫn có thể sai về authorization, tính toàn vẹn hoặc side effect. Với yêu cầu bảo mật, không bao giờ recover lỗi từ chối quyền thành success.

## 22. Bảo vệ dữ liệu khi chuyển đổi và log exception

Message/cause có thể chứa:

- Đường dẫn file hoặc host/port nội bộ.
- Query/cấu hình hạ tầng.
- Token, password, credential.
- Identifier khách hàng hoặc dữ liệu cá nhân.
- Internal implementation details.

Ở public API boundary có thể cần message và error code an toàn; diagnostics nội bộ có thể giữ cause với **quyền truy cập phù hợp**. Nhưng giữ cause **không cho phép tự serialize toàn bộ chain ra public response**.

Một error taxonomy đáng tin nên có **mã lỗi ổn định**, retryability và correlation ID phù hợp; caller không nên parse ngẫu nhiên exception message để ra quyết định nghiệp vụ.

## 23. Kiểm thử exception contract, không chỉ handler logic

| Ca kiểm thử | Điều phải chứng minh |
| --- | --- |
| Target return bình thường | Advice không tạo lỗi mới |
| Preserve | Caller nhận Throwable đúng loại/object nếu yêu cầu |
| Map cùng family checked | Cause gốc còn, type mới hợp contract |
| Map mất subtype | Test phát hiện caller bắt subtype bị ảnh hưởng |
| Checked không khai báo ở Java Dynamic Proxy | `UndeclaredThrowableException` theo semantics proxy |
| Unchecked exception | Propagate/map phù hợp |
| Error nghiêm trọng | Không bị swallow thành success |
| Throwable có suppressed exceptions | Có thể truy vết đầy đủ qua cause |
| Not-found | Recover đúng khi contract cho phép |
| Storage offline | Không giả làm dữ liệu “không tìm thấy” |
| Before advice throw | Target có chạy không, after nào được gọi? |
| Logging/cleanup throw | Có che lỗi gốc không? |
| Around skip proceed | Outcome cuối và side effects đúng |
| Retry nhiều lần | Đúng attempt count/idempotency/deadline |
| Mapping và retry đổi thứ tự | Lỗi ngoài cùng có thể khác |
| Future complete lỗi | Phân biệt lỗi sync và lỗi async |
| Interrupt/cancellation | Không mất tín hiệu dừng |
| Raw target bypass proxy | Policy AOP chỉ áp dụng đúng đường được intercept |
| Fallback cho primitive/generic/future | Không vi phạm type/caller contract |
| Sensitive error | Không lộ bí mật ở log/public response |

Cần **unit test taxonomy**, **integration test qua AOP engine thật**, và **contract test phía caller**. Unit test một hàm `Throwable map(Throwable)` có thể pass nhưng khi đi qua Java proxy lại gặp lỗi checked exception hoặc type không tương thích.

## 24. Checklist quyết định preserve/map/recover

1. Join point thực sự là call hay execution, và lời gọi có đi qua AOP không?
2. Method khai báo return type và checked throws như thế nào?
3. Throwable đến từ target, advice khác, hay infrastructure?
4. Error type và cause cụ thể là gì?
5. Lỗi này expected domain, transient hay bug/security/system?
6. Nếu chỉ quan sát, có thể giữ nguyên object không?
7. Nếu map, mapping nằm tại abstraction boundary nào?
8. New Throwable có cause và taxonomy/error code đúng không?
9. Caller nào phụ thuộc vào subtype checked exception cũ?
10. Nếu recover, fallback có đúng kiểu và semantics?
11. Target có side effect nào đã chạy trước failure?
12. Nếu retry, có idempotency, backoff, limit và cancellation không?
13. Trong chuỗi advice, mapping nằm trong hay ngoài retry/audit?
14. Logger/cleanup có thể che lỗi chính không?
15. Với async, đang xử lý synchronous throw hay future completion?
16. Có test xác minh **caller thấy gì**, không chỉ advice in gì không?

Chỉ khi trả lời rõ những câu hỏi phù hợp với hệ thống mới nên biến đổi outcome của target.

## 25. Những sai lầm thường gặp

1. **Bắt mọi `Exception` rồi trả null.** Che lỗi và có thể phá return contract.
2. **Tưởng log xong là giữ nguyên lỗi.** Nếu không rethrow/đường finally throw khác, caller có thể không thấy original.
3. **Đổi mọi lỗi thành `RuntimeException`.** Phá subtype và checked semantics.
4. **Chỉ sao chép message.** Làm mất cause chain.
5. **Giữ cause nghĩa là preserve exception identity.** Không: wrapper là object mới.
6. **After-throwing chắc chắn recover được.** Quyền thay outcome tùy engine.
7. **Handler `throws Throwable` nên proxy truyền được mọi checked type.** Interface method contract vẫn áp dụng.
8. **`UndeclaredThrowableException` là loại lỗi nghiệp vụ.** Nó có thể là wrapper kỹ thuật của Java Dynamic Proxy.
9. **Bất kỳ `IOException` nào cũng có thể retry.** Có lỗi permanent và side effects.
10. **Lỗi tài liệu thiếu giống storage offline.** Khác semantics.
11. **`finally` không thể thay outcome.** Exception cleanup có thể che original.
12. **Suppressed exceptions luôn nằm trực tiếp trên mapped Throwable.** Phải xem object và cause chain.
13. **Nên unwrap tất cả Throwable tới root.** Có thể xóa domain boundary có ý nghĩa.
14. **Completion future thành công nếu method return được future.** Task có thể thất bại sau đó.
15. **`exceptionally` chỉ ghi log.** Nó có thể biến failure thành fallback success.
16. **Interrupt/cancel nên retry ngay.** Cần giữ tín hiệu điều phối.
17. **Có fallback đúng kiểu thì đúng nghiệp vụ.** Phải xét tính toàn vẹn, quyền và consistency.
18. **Mapped exception có thể public nguyên cause vô điều kiện.** Cause/message có thể lộ thông tin.
19. **Mọi aspect nhìn thấy cùng lỗi gốc.** Precedence/mapping/recovery làm thay đổi outcome.
20. **Unit test mapper đủ đảm bảo caller contract.** Proxy boundary, weaving, async và type checks cần integration test.

## 26. Bài tập

1. Chạy `AdviceExceptionContractDemo.java`, đối chiếu toàn bộ stdout.
2. Vì sao `caller sameIdentity true`? Nếu map thành exception mới, phép `==` có còn true không?
3. Với `MAP_IO`, kiểm tra message, cause và stack trace ngoài cùng của mapped exception.
4. Thay `FileNotFoundException` thành `IOException` mới; caller bắt subtype bị ảnh hưởng thế nào?
5. Đổi `BAD_CHECKED` từ `SQLException` sang `IllegalStateException`; wrapper proxy có giống trước không?
6. Thêm method interface không khai báo checked throws; thử handler ném `IOException`.
7. Thêm policy chỉ ghi audit rồi `throw original`, so sánh với policy nuốt lỗi.
8. Cho audit sink ném lỗi trong `finally` và giải thích Throwable caller thấy.
9. Tạo một `try-with-resources` mà work và `close` cùng lỗi; quan sát suppressed, sau đó map có cause.
10. Tạo hai around advice: retry và mapping; đảo thứ tự, đối chiếu lỗi mỗi layer nhận.
11. Viết policy chỉ retry một subtype lỗi transient, với giới hạn attempt/deadline.
12. Mô phỏng charge bị timeout sau khi có side effect; vì sao retry cần idempotency key?
13. Dùng `Optional.empty()` cho not-found nhưng propagate lỗi network; giải thích.
14. Trả null cho một proxy method trả `int` và kiểm tra lỗi unboxing.
15. Tạo future hoàn tất lỗi, so sánh `get()` và `join()`.
16. Gắn `exceptionally(error -> "DEFAULT")` rồi xác định khi nào caller không thấy lỗi nữa.
17. Gắn `whenComplete` có callback ném exception; kiểm tra semantics stage mới.
18. Xây taxonomy error code cho ba loại: not-found, forbidden, unavailable, tránh parse message.
19. Viết test rằng raw target không qua proxy mapping còn wrapped target có policy.
20. Thiết kế metric tách số attempt thất bại, số caller invocation thất bại và số recovery thành công.

**Tự kiểm tra:** Preserve khác map ở object identity như thế nào? Khi nào nên giữ subtype? Vì sao Java Dynamic Proxy có thể sinh `UndeclaredThrowableException`? Recovery có thể vi phạm non-null/primitive contract ra sao? Cause và suppressed khác nhau thế nào? Khi future return bình thường nhưng completion thất bại, advice nào quan sát được? Retry có thể làm side effect trùng không?

## Kết luận

**Ngoại lệ là đầu ra có ý nghĩa của một phương thức, không phải thứ advice được phép xóa tùy tiện.** Trong AOP, hãy mặc định **giữ nguyên Throwable gốc** nếu chỉ quan sát. Khi có abstraction boundary rõ, có thể **chuyển đổi có chủ đích**, giữ cause và taxonomy hợp lệ; khi business contract cho phép, có thể **recover** bằng fallback đúng nghĩa; retry chỉ khi có tính idempotent và kiểm soát deadline/cancellation.

Cần phân biệt lỗi target, lỗi advice, wrapper kỹ thuật, lỗi cleanup và thất bại bất đồng bộ. Quyết định cuối phải được xác nhận bằng **giá trị hoặc ngoại lệ mà caller thật sự quan sát**, kể cả qua proxy/weaving, chứ không chỉ bằng dòng log trong advice.