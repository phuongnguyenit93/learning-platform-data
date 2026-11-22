# Điểm xử lý ngoại lệ và các giới hạn theo công cụ

## 1. Vì sao điểm xử lý ngoại lệ là một điểm can thiệp đáng tìm hiểu?

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), một **join point (điểm nối/điểm can thiệp)** là vị trí trong luồng thực thi mà cơ chế AOP có thể cho phép gắn thêm hành vi. Các điểm liên quan đến ngoại lệ đặc biệt quan trọng vì chúng quyết định *lỗi được quan sát lúc nào*, *ai thực sự nhận lỗi*, và *lỗi đã được xử lý hay vẫn tiếp tục lan truyền*.

Java phân biệt rõ hai hiện tượng:

- **Một thao tác kết thúc bằng ngoại lệ:** ngoại lệ thoát khỏi lời gọi/phương thức đang được quan sát; advice kiểu **after throwing** có thể được kích hoạt ở ranh giới này nếu công nghệ AOP hỗ trợ.
- **Một exception handler được đi vào:** luồng thực thi đến phần `catch` phù hợp với ngoại lệ; ở những cơ chế có hỗ trợ **exception-handler join point**, chính điểm bước vào handler này có thể là nơi advice chạy.

Đây là **hai điểm khác nhau**. Một ngoại lệ có thể đã được bắt và xử lý bên trong phương thức, khiến phương thức trả về bình thường: handler đã chạy nhưng **không có after throwing tại ranh giới phương thức ấy**. Ngược lại, một ngoại lệ thoát khỏi phương thức không nhất thiết có handler nằm trong phương thức đó.

Đề bài này tập trung vào việc hiểu đúng **điểm xử lý ngoại lệ**, những gì advice có thể biết ở đó, và những **giới hạn tùy công cụ** (proxy, weaving, join point model, kiểu ngoại lệ, bất đồng bộ).

## 2. Ôn lại vòng đời ngoại lệ ở Java

Xét chương trình ý niệm:

~~~java
String readValue() {
    try {
        return load(); // có thể ném IllegalStateException
    } catch (IllegalStateException problem) {
        return "fallback";
    } finally {
        release();
    }
}
~~~

Luồng chạy gồm các bước:

1. `load()` được gọi trong `try`.
2. Nếu `load()` thành công, khối `catch` bị bỏ qua, `finally` vẫn thực thi trước khi phương thức trả về.
3. Nếu `load()` ném `IllegalStateException`, Java tìm khối `catch` tương thích theo thứ tự khai báo; handler tương ứng được đi vào.
4. Handler ở ví dụ trả về `"fallback"`, sau đó `finally` chạy; với điều kiện `release()` không ném lỗi, phương thức **trả về bình thường**.
5. Nếu không có handler phù hợp trong phương thức, hoặc handler ném lại lỗi, ngoại lệ tiếp tục lan lên các lời gọi phía ngoài.
6. Nếu `release()` trong `finally` ném ngoại lệ, chính ngoại lệ mới có thể thay đổi kết quả quan sát được, thậm chí che lỗi trước đó. Vì thế cần xem toàn bộ cấu trúc xử lý.

Trong Java, lựa chọn handler dựa trên kiểu ngoại lệ và tính tương thích với khai báo `catch`. Ví dụ, `catch (RuntimeException e)` có thể nhận `IllegalArgumentException` hoặc `IllegalStateException`, vì chúng là kiểu con của `RuntimeException`. Với nhiều `catch`, thứ tự và ràng buộc của ngôn ngữ quyết định handler nào hợp lệ và được chọn.

**Điểm handler không phải nơi ngoại lệ được tạo ra bằng `throw`.** Nếu một câu lệnh `throw` xuất hiện trong hàm A, còn `catch` xử lý ở hàm B phía ngoài, vị trí tạo ngoại lệ và vị trí vào handler nằm ở hai phần khác nhau của chương trình.

## 3. Phân biệt bốn loại sự kiện cần quan sát

| Sự kiện | Khi xảy ra | Điểm quan sát phù hợp | Điều không thể suy ra |
| --- | --- | --- | --- |
| **Throw** | Mã thực hiện `throw` hoặc thao tác gây ra ngoại lệ | Điểm ném (nếu cơ chế hỗ trợ) | Chưa biết cuối cùng có được xử lý hay không |
| **Handler entry** | Luồng chuyển vào `catch` phù hợp | Exception-handler join point (nếu có) | Chưa biết handler sẽ nuốt, ném lại hay đổi lỗi |
| **Exceptional method exit** | Ngoại lệ thoát khỏi phương thức đang quan sát | Advice `after throwing` tại method execution/call | Không thấy các lỗi đã xử lý hoàn toàn bên trong |
| **Normal method exit** | Phương thức trả kết quả, kể cả kết quả dự phòng sau `catch` | Advice `after returning` | Không chứng minh bên trong chưa từng có ngoại lệ |

Ví dụ:

~~~text
Caller
  |
  +-> operation()
         |
         +-> riskyCall() ---- ném IllegalStateException ----+
         |                                                   |
         +<------------------- catch IllegalStateException <-+
         |                     [handler entry]
         |                     return "fallback"
         |
  <------ "fallback" (normal return)
~~~

Tại `operation()`, có **handler entry**, rồi **normal return**. Một aspect chỉ quan sát `after throwing` tại ranh giới `operation()` sẽ không nhận được sự kiện lỗi này. Điều đó không có nghĩa aspect vận hành sai; pointcut đơn giản là nhắm tới **một loại điểm can thiệp khác**.

Nếu handler thực hiện `throw e;`, lỗi có thể tiếp tục thoát ra và tạo thêm sự kiện exceptional exit ở ranh giới bên ngoài. Nếu handler đổi thành ngoại lệ khác, lời gọi bên ngoài nhìn thấy ngoại lệ mới, còn tại handler entry ban đầu có thể quan sát ngoại lệ cũ. Cần quyết định **muốn đo “đã xảy ra lỗi”, “đã xử lý lỗi”, hay “tác vụ cuối cùng thất bại”** trước khi chọn join point.

## 4. Exception-handler join point thực chất là gì?

Với một cơ chế AOP hỗ trợ điểm xử lý ngoại lệ, **exception-handler join point** thường đại diện cho thời điểm điều khiển chuyển đến một handler `catch` được chọn trong chương trình. Đây là điểm theo *cấu trúc xử lý ngoại lệ*, chứ không chỉ là việc một phương thức trả về hoặc ném lỗi.

Mô hình khái niệm:

~~~text
try {
    perform();
} catch (SpecificProblem problem) {
    // [handler join point: khi catch này được đi vào]
    recover(problem);
}
~~~

Một advice gắn vào điểm này có thể được thiết kế để ghi nhận loại lỗi, tên vùng xử lý (nếu cơ chế cung cấp), thông tin truy vết hoặc thống kê số lần handler được sử dụng. Nhưng phải kiểm tra tài liệu của công cụ để biết các chi tiết quan trọng:

- **Có hỗ trợ loại join point “handler” hay không?** Một công cụ chỉ bao phương thức bằng proxy thường không có điểm can thiệp ở bên trong khối `catch`.
- **Có thể chọn handler theo kiểu ngoại lệ không?** Nếu có, quy tắc chọn dựa trên kiểu khai báo `catch`, kiểu lỗi thực tế, hay một tiêu chí khác?
- **Advice chạy ở vị trí chính xác nào?** Trước thân handler, sau handler, hay bao quanh xử lý? Không tự giả định mọi kiểu advice đều khả dụng ở handler join point.
- **Advice được cung cấp những giá trị nào?** Có thấy biến ngoại lệ, chữ ký phương thức chứa handler, target và các biến cục bộ khác không? Các biến này không mặc nhiên được công cụ cung cấp.
- **Nếu advice ném lỗi thì sao?** Nó có thể làm gián đoạn việc phục hồi mà handler dự định thực hiện; đây là thay đổi ngữ nghĩa chương trình.
- **Handler do trình biên dịch tạo và handler ngầm định có được tính không?** Công nghệ bytecode và cách biên dịch có thể ảnh hưởng các vị trí thực sự có thể quan sát.

Chính vì thế, cách nói chính xác là: **handler là một loại join point có thể được hỗ trợ trong một số mô hình AOP**. Không phải mọi AOP engine đều có khả năng chặn `catch`, và không thể coi một phương thức `after throwing` là tương đương với handler join point.

## 5. Giới hạn theo cách kết hợp aspect vào chương trình

### 5.1. Cơ chế dựa trên proxy

Một proxy nằm giữa caller và target có thể quan sát sự kiện **lời gọi qua proxy**: tham số, trả về, ngoại lệ thoát ra từ lời gọi. Nhưng nó thường không nhìn được từng câu lệnh bên trong target, bao gồm `try`, `catch` và các handler nội bộ.

Ví dụ, phương thức `fetch()` ném lỗi rồi tự `catch` và trả `"cached"`. Với proxy bao quanh `fetch()`, kết quả chỉ là **một lời gọi thành công trả `"cached"`**. Proxy không biết chắc handler có chạy, trừ khi target chủ động phát sự kiện hoặc có cơ chế can thiệp bên trong khác.

Các giới hạn quen thuộc của proxy còn gồm:

- Lời gọi đi thẳng vào target, bỏ qua proxy, không được can thiệp.
- Lời gọi nội bộ giữa các phương thức qua `this` có thể không đi qua proxy (**self-invocation**).
- Loại phương thức can thiệp được phụ thuộc kỹ thuật proxy: interface, class, khả năng override và các ràng buộc truy cập. Không áp dụng một giả định cho mọi kiểu proxy.
- Một proxy method-call không tự động thêm join point cho constructor, truy cập field, lệnh `throw` hoặc khối `catch`.

### 5.2. Cơ chế weaving ở mức bytecode/mã biên dịch

Một cơ chế weaving có thể chèn hành vi ở phạm vi sâu hơn, bao gồm các điểm bên trong thân phương thức **nếu mô hình join point của nó hỗ trợ**. Khả năng này cần kiểm tra rõ chứ không thể suy ra chỉ từ tên “weaver”.

Các yếu tố phụ thuộc công cụ gồm thời điểm kết hợp (biên dịch, hậu biên dịch hoặc nạp lớp), lớp nào nằm trong phạm vi weaving, thư viện bên thứ ba có được biến đổi hay không, các lớp do JDK quản lý và các giới hạn về module/classloader.

Một join point tồn tại trên lý thuyết nhưng nằm trong lớp **không được weaving** vẫn không tạo advice. Điều này thường gây hiểu nhầm “pointcut đã đúng nhưng không có log”.

### 5.3. Giới hạn cú pháp pointcut và kiểu advice

Không phải mọi ngôn ngữ pointcut đều có toán tử chọn handler; không phải kiểu advice nào cũng áp dụng được lên mọi loại join point. Nếu cần tham chiếu ngoại lệ trong `catch`, phải xác minh cú pháp binding tương ứng. Không dùng cú pháp của một công nghệ để suy đoán rằng công nghệ khác hỗ trợ tương tự.

## 6. Ví dụ Java 17+: chứng minh handler entry khác exceptional exit

Ví dụ chạy độc lập dưới đây dùng **Java thuần**. Dòng `HANDLER` được gọi *tường minh trong `catch`* để mô phỏng sự kiện “đi vào handler”. Các dòng `RETURN` và `THROWING` được ghi bởi **JDK dynamic proxy**, đại diện cho điều proxy có thể quan sát ở ranh giới phương thức. Đây là mô phỏng cơ chế, không phải triển khai một bộ weaving handler join point.

Tạo file `ExceptionJoinPointDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class ExceptionJoinPointDemo {
    interface Work {
        String recover();
        String rethrow();
        String fail();
        String succeed();
    }

    static final class Core implements Work {
        private void onHandlerEntry(String where, Exception error) {
            System.out.println("HANDLER " + where + ": " + error.getMessage());
        }

        @Override
        public String recover() {
            try {
                throw new IllegalStateException("offline");
            } catch (IllegalStateException error) {
                onHandlerEntry("recover", error);
                return "cached";
            }
        }

        @Override
        public String rethrow() {
            try {
                throw new IllegalStateException("unavailable");
            } catch (IllegalStateException error) {
                onHandlerEntry("rethrow", error);
                throw error;
            }
        }

        @Override
        public String fail() {
            throw new IllegalArgumentException("invalid");
        }

        @Override
        public String succeed() {
            return "done";
        }
    }

    static Work observeCalls(Work target) {
        return (Work) Proxy.newProxyInstance(
                Work.class.getClassLoader(), new Class<?>[] { Work.class },
                (proxy, method, args) -> invokeObserved(target, method, args));
    }

    static Object invokeObserved(Work target, Method method, Object[] args)
            throws Throwable {
        try {
            Object result = method.invoke(target, args);
            System.out.println("RETURN " + method.getName() + ": " + result);
            return result;
        } catch (InvocationTargetException wrapper) {
            Throwable error = wrapper.getCause();
            System.out.println("THROWING " + method.getName() + ": "
                    + error.getClass().getSimpleName());
            throw error;
        }
    }

    public static void main(String[] args) {
        Work work = observeCalls(new Core());
        System.out.println("CALL recover: " + work.recover());
        try {
            work.rethrow();
        } catch (IllegalStateException error) {
            System.out.println("CALLER rethrow: " + error.getMessage());
        }
        try {
            work.fail();
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER fail: " + error.getMessage());
        }
        System.out.println("CALL succeed: " + work.succeed());
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 ExceptionJoinPointDemo.java
java ExceptionJoinPointDemo
~~~

Kết quả tiêu chuẩn đã được đối chiếu sau khi biên dịch:

~~~text
HANDLER recover: offline
RETURN recover: cached
CALL recover: cached
HANDLER rethrow: unavailable
THROWING rethrow: IllegalStateException
CALLER rethrow: unavailable
THROWING fail: IllegalArgumentException
CALLER fail: invalid
RETURN succeed: done
CALL succeed: done
~~~

Phân tích chính xác bốn trường hợp:

1. **`recover()`:** Có ngoại lệ `IllegalStateException`, handler `catch` được đi vào và trả giá trị dự phòng. Proxy quan sát **RETURN**, không có **THROWING** tại ranh giới `recover()`.
2. **`rethrow()`:** Handler được đi vào rồi ném lại ngoại lệ ban đầu. Proxy quan sát **THROWING** khi ngoại lệ thoát khỏi phương thức. Một handler join point và một sự kiện exceptional exit có thể cùng xuất hiện trong một lời gọi.
3. **`fail()`:** Ngoại lệ thoát khỏi phương thức mà không có handler nội bộ. Proxy quan sát **THROWING**, còn caller bắt ngoại lệ ở mức cao hơn.
4. **`succeed()`:** Không có ngoại lệ. Proxy chỉ quan sát **RETURN**.

Phương thức `invokeObserved()` bóc lớp `InvocationTargetException` được tạo bởi reflection, rồi ném lại nguyên nhân gốc. Nếu không bóc, log có thể nhầm ngoại lệ nghiệp vụ thành lỗi của API phản chiếu. Ví dụ dùng các ngoại lệ unchecked để không cần khai báo `throws` trong interface; checked exception cần hợp đồng `throws` hoặc cách chuyển đổi rõ ràng phù hợp với proxy.

Điểm quan trọng nhất: **proxy không hề phát hiện trực tiếp câu lệnh `catch`**. Ta chủ động gọi `onHandlerEntry()` trong mã target để minh họa vị trí handler. Muốn can thiệp vào handler không sửa trực tiếp mã nghiệp vụ, phải chọn công cụ có khả năng tương ứng và bảo đảm vùng mã ấy thực sự được kết hợp.

## 7. Catch handler, after throwing, finally và “handled” khác nhau ra sao?

Một advice kiểu **after throwing** dùng để quan sát khi join point đang theo dõi kết thúc bằng ngoại lệ, ví dụ lần thực thi phương thức vừa ném lỗi ra ngoài. **Handler join point** là thời điểm một khối `catch` cụ thể bắt đầu xử lý. **Finally** là cơ chế Java đảm bảo chạy khối dọn dẹp trong phạm vi `try` phù hợp; nó không đồng nghĩa với “một handler đã xử lý ngoại lệ”.

Một kịch bản phức tạp:

~~~java
String load() {
    try {
        return readPrimary();
    } catch (IllegalStateException original) {
        logFailure(original);
        return readFallback(); // có thể ném ngoại lệ khác
    } finally {
        closeResource(); // cũng có thể ném ngoại lệ
    }
}
~~~

Đoạn này là **mã minh họa không độc lập**: `readPrimary()`, `logFailure()`, `readFallback()` và `closeResource()` đại diện cho các thao tác ứng dụng.

Từ đoạn mã này không thể kết luận mọi lần vào `catch` đều dẫn đến trả về thành công. `readFallback()` có thể lỗi, hoặc `closeResource()` có thể thay đổi kết quả khi kết thúc. Một advice quan sát **entry vào handler** chỉ biết handler vừa bắt đầu; một advice quan sát **exceptional exit** ở cuối `load()` biết ngoại lệ cuối cùng thoát ra; một advice quan sát **normal return** chỉ biết có kết quả cuối cùng. Các sự kiện có ý nghĩa khác nhau.

Nếu ứng dụng dùng `try-with-resources`, Java cũng có cơ chế quản lý ngoại lệ khi đóng tài nguyên và có thể gắn ngoại lệ đóng thành **suppressed exception** của lỗi chính. Khi muốn audit nguyên nhân thực tế, cần kiểm tra cả `Throwable.getSuppressed()` trong những trường hợp phù hợp, thay vì chỉ nhìn thông điệp của ngoại lệ cuối.

## 8. Những giới hạn khác thường bị bỏ sót

### 8.1. Checked exception, unchecked exception và `Error`

`catch (Exception e)` không bao quát mọi `Throwable` vì `Error` không là lớp con của `Exception`. Chọn handler cần hiểu hệ phân cấp kiểu ngoại lệ. Một advice `after throwing` có thể được cấu hình lọc các loại lỗi khác nhau tùy công cụ. Không đưa ra giả định “mọi thất bại đều là Exception” khi thiết kế logging hoặc metrics.

Khi proxy xử lý checked exception không nằm trong chữ ký `throws` của interface, cơ chế có thể phải bọc nó theo quy tắc proxy của Java. Phần mềm gọi qua proxy có thể thấy **kiểu lỗi khác với lỗi gốc**. Cần giữ rõ hợp đồng `throws`, kiểm tra loại ngoại lệ thực tế caller quan sát, và phân biệt lỗi của target với lỗi phát sinh từ advice.

### 8.2. Re-throw, đổi lỗi và ngoại lệ do advice phát sinh

Nếu handler `throw original;` thì lời gọi bên ngoài có thể nhận lại nguyên nhân cũ. Nếu handler `throw new DomainFailure(original);` thì sự kiện bên ngoài phản ánh ngoại lệ mới với `cause` là lỗi cũ. Nếu advice tự ném lỗi khi ghi audit, lỗi này cũng có thể khiến phương thức kết thúc khác đi.

Điểm handler có thể dùng để quan sát ngoại lệ được bắt, **không bảo đảm biết trước handler sẽ nuốt hay ném lại**. Muốn biết kết quả cuối, cần quan sát thêm ranh giới hoàn tất của thao tác hoặc có event sau khi handler xử lý, nếu công nghệ hỗ trợ.

### 8.3. Bất đồng bộ: lỗi không nhất thiết thoát tại điểm gọi ban đầu

Phương thức có thể trả `CompletableFuture` ngay lập tức rồi tác vụ chạy sau đó mới thất bại. Khi ấy, method `after returning` ở thời điểm tạo Future có thể đã chạy, trong khi kết quả thực của tác vụ chưa có. Ngoại lệ có thể được lưu trong Future và chỉ hiện ra khi chờ/đọc kết quả hoặc trong callback xử lý hoàn tất.

Nếu muốn đo lỗi cuối cùng của tác vụ, cần quan sát điểm hoàn tất Future hoặc nơi ngoại lệ được xử lý bất đồng bộ. Không thể chỉ đặt `after throwing` lên phương thức trả Future rồi mặc định thu được mọi lỗi của tác vụ bên trong.

### 8.4. Handler do công cụ nhìn thấy và handler do người viết mong đợi

Trình biên dịch có thể biến đổi mã điều khiển ngoại lệ, tạo cấu trúc phục vụ `finally` hoặc quản lý tài nguyên. Một số công cụ chỉ phát hiện handler trong class đã weaving; một số chỉ can thiệp ranh giới phương thức; một số có giới hạn với lớp thư viện, classloader, module hoặc bytecode được tối ưu hóa.

Do đó, khi kiểm thử handler join point, cần đối chiếu **các khối `catch` thực sự được công cụ quan sát** chứ không suy luận từ cú pháp Java. Nếu cơ chế hỗ trợ pointcut theo kiểu handler, vẫn phải kiểm tra kiểu thực tế và phạm vi biên dịch/weaving trước khi tin rằng mọi handler được khớp.

### 8.5. Chính sách dữ liệu và lỗi phụ

Một handler có thể chứa thông tin nhạy cảm trong `message`, `cause` hoặc tham số của lời gọi. Hành vi audit tại handler nên ghi thông tin tối thiểu, tránh in toàn bộ payload hoặc stack trace không kiểm soát. Đồng thời, nếu chính cơ chế ghi sự kiện thất bại, hệ thống phải có chính sách không để lỗi phụ vô tình che lỗi nghiệp vụ hay phá luồng phục hồi.

## 9. Chọn loại điểm can thiệp theo mục tiêu

| Mục tiêu quan sát | Nên xem xét điểm nào? | Vì sao? |
| --- | --- | --- |
| Biết một khối `catch` cụ thể có được sử dụng | Handler entry nếu engine hỗ trợ, hoặc instrumentation tường minh | Sự kiện xảy ra ngay khi bắt đầu xử lý |
| Biết lời gọi API trả lỗi cho caller | Exceptional exit / `after throwing` ở ranh giới API | Đo thất bại theo hợp đồng caller |
| Biết số lần xảy ra lỗi dù được phục hồi nội bộ | Điểm ném hoặc điểm handler đủ rộng, có kiểm soát | Lỗi có thể bị xử lý và không thoát ra ngoài |
| Biết tác vụ cuối cùng thành công hay không | Ranh giới hoàn tất tác vụ hoặc completion của Future | Một `catch` không quyết định kết quả cuối cùng |
| Đảm bảo cleanup trên cả nhánh lỗi và thành công | `finally` hoặc advice tương đương trong phạm vi phù hợp | Hành vi cần chạy trên mọi đường rời phạm vi |
| Theo dõi chính sách phục hồi cụ thể | Handler kết hợp kết quả xử lý nếu có khả năng quan sát | Entry handler chưa chứng minh phục hồi thành công |

Một quy trình áp dụng thực tế:

1. **Viết rõ sự kiện muốn đếm:** số lần phát sinh lỗi, số lần vào handler, số lần phương thức thất bại, hay số tác vụ cuối cùng thất bại?
2. **Chọn điểm theo ngữ nghĩa sự kiện**, không theo tên advice nghe có vẻ giống nhau.
3. **Kiểm tra khả năng của công cụ:** join point nào được hỗ trợ, tên pointcut và advice hợp lệ, ngữ cảnh ngoại lệ bind được, phạm vi weaving/proxy.
4. **Thiết kế ranh giới quan sát:** tránh đếm nhiều lần một lỗi khi nó bị ném qua nhiều lớp; quyết định có phân biệt lỗi được phục hồi và lỗi chưa xử lý hay không.
5. **Kiểm thử tại đường chạy thật:** kiểm tra handler có nuốt lỗi, handler ném lại, không có handler nội bộ, lỗi trong `finally`, và đường bất đồng bộ nếu ứng dụng dùng.
6. **Giữ hành vi quan sát an toàn:** không tự đổi exception, kết quả và số lần xử lý nếu yêu cầu chỉ là audit hoặc metrics.

## 10. Các trường hợp kiểm thử cần có

| Trường hợp | Handler nội bộ? | Phương thức cuối cùng ra sao? | Điều cần quan sát |
| --- | --- | --- | --- |
| Không lỗi | Không | Return bình thường | Không có handler event |
| Lỗi được phục hồi | Có | Return dự phòng | Handler event, không có exceptional exit tại ranh giới đó |
| Lỗi bị ném lại | Có | Thoát bằng ngoại lệ | Handler event rồi exceptional exit |
| Không có handler phù hợp bên trong | Không | Thoát bằng ngoại lệ | Exceptional exit, caller có thể bắt ngoài |
| Handler tự gây lỗi mới | Có | Có thể thoát bằng lỗi mới | Phân biệt lỗi ban đầu và lỗi cuối |
| `finally` gây lỗi | Có hoặc không | Có thể đổi lỗi cuối | Nguyên nhân gốc và lỗi cleanup |
| Trả Future, lỗi xuất hiện sau | Có thể không ở call ban đầu | Phương thức trả Future bình thường; task thất bại sau | Quan sát completion, không chỉ method exit |
| Gọi target trực tiếp bỏ qua proxy | Tùy target | Theo nghiệp vụ | Không kỳ vọng advice chỉ gắn trên proxy xuất hiện |

Đừng chỉ chạy unit test trên hàm advice. Với AOP, phải kiểm tra **điểm can thiệp thực sự được chọn và chạy**. Cách dễ nhất là kiểm tra cùng một target ở hai đường: gọi qua ranh giới có advice và gọi trực tiếp; đồng thời kiểm tra số lần handler thật sự được thực thi.

## 11. Lỗi hiểu sai thường gặp

- **“Có throw thì chắc chắn có handler join point tại đó.”** Không đúng; `throw` và `catch` là hai vị trí khác nhau.
- **“After throwing sẽ bắt được mọi lỗi đã từng xảy ra trong phương thức.”** Không đúng nếu lỗi được xử lý nội bộ và phương thức trả bình thường.
- **“Có handler join point nghĩa là advice biết recovery thành công.”** Không đúng; vào `catch` mới là bắt đầu xử lý.
- **“Proxy chặn được cả catch bên trong target.”** Thông thường proxy chỉ nhìn ranh giới lời gọi; cần hỗ trợ weaving hoặc phát sự kiện tường minh để nhìn trong handler.
- **“Bất kỳ công cụ AOP nào cũng có handler pointcut.”** Mô hình join point và ngôn ngữ pointcut phụ thuộc công cụ.
- **“Bắt Exception tức là bắt mọi Throwable.”** `Error` không thuộc nhánh `Exception`.
- **“Một after throwing trên hàm trả Future quan sát luôn lỗi bất đồng bộ.”** Future có thể chỉ báo lỗi về sau.
- **“Ghi log trong advice không thể ảnh hưởng chương trình.”** Lỗi logging, sửa tham số, biến đổi exception hoặc gọi tiếp sai có thể đổi hành vi thật.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `read()` bắt `IllegalStateException` bên trong rồi trả giá trị dự phòng. `After throwing` ở ranh giới `read()` có chạy vì lỗi đó không?  
**Trả lời:** Không, nếu `read()` cuối cùng trả về bình thường. Handler bên trong đã chạy nhưng ngoại lệ không thoát khỏi ranh giới quan sát.

**Câu 2.** Handler đã nhận ngoại lệ và thực hiện `throw e;`. Lúc này có thể quan sát những điểm nào?  
**Trả lời:** Handler entry ở vị trí `catch` nếu cơ chế hỗ trợ; sau đó exceptional exit tại các ranh giới mà lỗi đi qua và có advice phù hợp.

**Câu 3.** Vì sao lời gọi qua dynamic proxy không đủ quan sát mọi `catch`?  
**Trả lời:** Proxy can thiệp ở giao diện lời gọi. Một handler xử lý hoàn toàn bên trong target không tạo sự kiện bắt lỗi ở ranh giới phương thức.

**Câu 4.** Nếu muốn đo tỷ lệ *tác vụ bất đồng bộ cuối cùng thất bại*, nên theo dõi gì?  
**Trả lời:** Trạng thái completion cuối cùng của tác vụ/Future, phân biệt với thời điểm phương thức tạo tác vụ trả về.

**Câu 5.** Khi chọn công cụ AOP để can thiệp vào handler, cần xác minh tối thiểu những gì?  
**Trả lời:** Công cụ có hỗ trợ handler join point; pointcut chọn đúng handler; advice/binding ngoại lệ được hỗ trợ; mã chứa handler thuộc phạm vi weaving; và kết quả thực tế được kiểm chứng qua chạy chương trình.

## 13. Ghi nhớ

**Điểm xử lý ngoại lệ** là nơi chương trình *bắt đầu xử lý* một ngoại lệ, khác với **điểm ném lỗi** và **lần thoát phương thức bằng ngoại lệ**. Khả năng can thiệp trực tiếp tại handler phụ thuộc mô hình join point và kỹ thuật mà công cụ AOP hỗ trợ. Khi cần theo dõi lỗi chính xác, hãy bắt đầu từ sự kiện muốn quan sát, chọn đúng ranh giới, xác minh khả năng proxy/weaving, và kiểm thử đủ cả phục hồi, ném lại, lỗi cleanup cùng trường hợp bất đồng bộ.