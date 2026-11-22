# Phân biệt điểm trong mã nguồn với điểm trong luồng thực thi

## Mục tiêu bài học

Khi học Aspect-Oriented Programming (**AOP**), rất dễ nhìn vào một dòng mã như `service.process()` rồi nghĩ rằng đó chính là “một join point”. Cách nói này thiếu một lớp phân biệt quan trọng: **vị trí viết trong chương trình** là một mô tả tĩnh, còn **lần thực sự xảy ra của thao tác khi chương trình chạy** là sự kiện động. Một vị trí trong mã có thể được thực thi không lần nào, một lần hoặc hàng triệu lần; một lần chạy có thể đi qua nhiều điểm can thiệp khác nhau.

Sau bài này, bạn sẽ:

- Phân biệt **source location / call site / vị trí mã tĩnh** với **runtime event / lần xảy ra của join point**.
- Hiểu khái niệm **join-point shadow** trong những mô hình AOP có định nghĩa thuật ngữ đó, và không mặc định mọi công cụ dùng cùng thuật ngữ.
- Phân biệt **method call** với **method execution**, kể cả khi cú pháp nguồn khiến chúng trông giống nhau.
- Dự đoán số lần advice chạy khi có vòng lặp, nhánh điều kiện, đa hình, đệ quy, bất đồng bộ và lời gọi đi vòng qua proxy.
- Thiết kế pointcut và kiểm thử theo **đường chạy thực tế**, tránh đếm dòng mã hoặc số method declaration để suy ra số lần can thiệp.
- Giải thích được ranh giới giữa những gì AOP chọn ở **mức cấu trúc chương trình** và những gì cần kiểm tra tiếp ở **runtime**.

Bài học nói về AOP **nói chung**. Các điểm can thiệp mà một ngôn ngữ hay công cụ cụ thể hỗ trợ có thể khác nhau; không suy rộng khả năng của một kiểu proxy sang mọi kỹ thuật AOP.

## 1. Hai câu hỏi khác nhau: “ở đâu?” và “đã xảy ra lúc nào?”

Xét mã:

```java
for (int i = 0; i < 3; i++) {
    service.execute(i);   // một vị trí lời gọi trong mã nguồn
}
```

Có **một biểu thức lời gọi** `service.execute(i)` trong phần thân vòng lặp, nhưng nếu vòng lặp chạy đủ ba lần và không bị ngắt trước lời gọi, sẽ có **ba lần gọi xảy ra khi thực thi**.

Nếu đổi điều kiện thành `i < 0`, vẫn còn nguyên dòng mã ấy nhưng không có lần gọi nào xảy ra. Nếu gọi `execute` từ nhiều vị trí khác nữa, số vị trí mã tăng; số lần thực thi vẫn phụ thuộc đường đi, dữ liệu và lịch chạy.

| Góc nhìn | Điểm trong mã nguồn | Điểm trong luồng thực thi |
| --- | --- | --- |
| Câu hỏi | “Thao tác được viết/biểu diễn ở chỗ nào?” | “Một thao tác cụ thể đã xảy ra khi nào?” |
| Tính chất | Tương đối tĩnh theo phiên bản chương trình hoặc artifact. | Động, phụ thuộc input, nhánh, vòng lặp, lịch chạy, exception. |
| Ví dụ | Biểu thức `service.execute(i)` trong một thân vòng lặp. | Lượt `execute(0)`, `execute(1)`, `execute(2)` thực sự xảy ra. |
| Số lượng | Một call site ở đoạn mã đã cho. | Có thể bằng 0, 1, 3 hoặc rất nhiều lượt. |
| Dữ liệu sẵn có | Chữ ký, kiểu tĩnh, modifier, metadata, cấu trúc mã. | Đối tượng thực, giá trị đối số, thread/context, thời điểm, kết quả/lỗi. |
| Công việc kiểm chứng | Phân tích cấu trúc hoặc bytecode, xem pointcut dự kiến chọn vị trí nào. | Chạy chương trình và quan sát đúng các sự kiện có/không được advice xử lý. |

**Ý chính:** Vị trí mã là **ứng viên có thể phát sinh sự kiện**, không phải bằng chứng rằng sự kiện đã xảy ra. Đây là nền tảng để hiểu join point trong AOP.

## 2. Join point là gì trong sự phân biệt này?

Trong nhiều mô hình AOP, **join point** là một điểm hoặc sự kiện có ý nghĩa xác định trong **luồng thực thi** mà công cụ có thể chèn hành vi hoặc quan sát, chẳng hạn “một lần thực thi phương thức `save`” hay “một lần gọi phương thức `save`”. **Pointcut** là quy tắc chọn các join point quan tâm; **advice** là hành vi được áp dụng ở những điểm được chọn; **weaving** là cách kết hợp advice với chương trình.

Điều quan trọng là từ “điểm” không bắt buộc có nghĩa “một dòng source”. Một lần thực thi method có thể bắt đầu tại bytecode đã biên dịch, chạy qua hàng loạt statement, và kết thúc bằng return hoặc throw. Một join point được công cụ mô hình hóa như sự kiện có thể có **ngữ cảnh**, **thời gian tồn tại** hoặc khả năng bao quanh một vùng thực thi. Cách biểu diễn cụ thể là hợp đồng của công cụ.

### 2.1. Join-point shadow là khái niệm hữu ích nhưng không phổ quát

Trong một số hệ thống AOP có phân biệt tĩnh/động, **join-point shadow** là vị trí trong mã (thường được xem ở source hoặc bytecode) **có thể tạo ra join point khi được thực thi**.

Ví dụ với vòng lặp `service.execute(i)`:

- **Shadow tiềm năng:** vị trí thao tác gọi `execute` được công cụ nhận diện trong mã.
- **Join-point occurrences:** những lần thao tác ấy thực sự diễn ra ở runtime.
- **Pointcut match:** quy tắc có thể chọn shadow theo thông tin tĩnh, có thể cần kiểm tra bổ sung theo ngữ cảnh runtime.
- **Advice executions:** những lần advice thực sự chạy sau khi cơ chế can thiệp được kích hoạt và các điều kiện chọn được thỏa.

Không phải mọi công cụ AOP công bố khái niệm *shadow*, và không phải loại join point nào cũng có một địa chỉ dòng source tương ứng duy nhất. Với proxy thuần runtime, ta có thể quan sát lời gọi qua proxy mà không cần một bộ chọn vị trí nguồn. Thuật ngữ shadow nên dùng **khi mô hình đang học hỗ trợ nó**, không dùng như tiêu chuẩn bắt buộc của mọi AOP.

### 2.2. Không đồng nhất số shadow, join point và lần chạy advice

Số liệu này có thể khác nhau:

```text
01 vị trí lời gọi trong mã
       |
       | vòng lặp chạy 10 lần
       v
10 lần gọi ở runtime
       |
       | chỉ 6 lần thỏa điều kiện động của pointcut
       v
06 lần advice được kích hoạt
```

Sơ đồ có tính minh họa: một công cụ có thể chọn ở mức method execution thay vì call site, hoặc không có điều kiện động. Nó nhấn mạnh **ba phép đếm khác nhau**. Không dùng phép đếm dòng mã để dự báo lượng log, overhead hay số lần advice.

## 3. Method call và method execution là hai loại join point khác nhau

Xét một đoạn chương trình:

```java
class ReportService {
    void generate() {
        save("Q4");       // vị trí gọi
    }

    void save(String name) {
        System.out.println(name); // phần thân được thực thi
    }
}
```

Nếu một mô hình AOP hỗ trợ phân biệt hai loại sau:

- **Method-call join point:** sự kiện ở phía thao tác **gọi** `save("Q4")` từ `generate()`. Vị trí liên quan nằm ở phía caller.
- **Method-execution join point:** sự kiện khi **phần thực thi của `save`** bắt đầu/chạy theo định nghĩa của mô hình. Vị trí liên quan nằm ở phía callee.

Lược đồ:

```text
generate()
    |
    |  call-site: save("Q4")  <-- method-call join point (nếu được hỗ trợ)
    v
save(name)
    |                     <-- method-execution join point (nếu được hỗ trợ)
    v
in "Q4"
```

Một lần gọi thông thường có thể liên quan cả sự kiện call và execution trong những mô hình hỗ trợ cả hai. Tuy nhiên, chúng **không phải cùng join point**. Nếu `save` được gọi từ ba call site khác nhau, ba vị trí call tĩnh có thể dẫn đến các lượt thực thi của cùng thân method. Một call site trong vòng lặp có thể làm phát sinh nhiều lượt call và execution.

Đặc biệt, các kỹ thuật chỉ chặn lời gọi qua **proxy** không nhất thiết hiện thực được một join-point model phân biệt call/execution theo cấu trúc source. Ở đó, cách mô tả chính xác hơn là **handler chạy khi có lời gọi đi qua proxy**, chứ không suy luận rằng công cụ hỗ trợ mọi call site hoặc mọi method execution trong chương trình.

### 3.1. Đa hình khiến “dòng gọi” và “thân code chạy” càng khác nhau

Xét:

```java
interface Operation {
    void run();
}

class FastOperation implements Operation {
    public void run() {
        System.out.println("fast");
    }
}

class SafeOperation implements Operation {
    public void run() {
        System.out.println("safe");
    }
}
```

Biểu thức `operation.run()` tại một call site có kiểu tĩnh `Operation`, nhưng đối tượng runtime có thể là `FastOperation` hoặc `SafeOperation`. Vì vậy:

- Một vị trí gọi tĩnh **không xác định duy nhất** thân triển khai nào sẽ được chạy.
- Một pointcut dựa vào **chữ ký tĩnh** có thể chọn khác với pointcut phụ thuộc **loại target runtime**.
- Advice ở phía method-execution có thể gắn với một triển khai cụ thể, trong khi call site có thể dispatch đến nhiều triển khai khác nhau.
- Kết quả quan sát chịu ảnh hưởng các quy tắc overload, override, dynamic dispatch, bridge method và giới hạn của cơ chế AOP cụ thể.

Cần tránh lập luận “dòng này gọi interface X, vậy advice trên implementation Y chắc chắn sẽ chạy”; phải chứng minh receiver thực và đường can thiệp tại runtime.

### 3.2. Static dispatch và dynamic dispatch là hai trục khác

Một lệnh gọi `static` không có cơ chế virtual dispatch tương tự một instance method, nhưng nó vẫn có thể có **vị trí lời gọi** và **lần xảy ra lúc runtime**. Công cụ có chặn được hay không phụ thuộc vào join-point model và cách triển khai. Tương tự, `private`, `final` hay constructor không thể bị chặn bằng mọi kiểu subclass proxy, nhưng có thể thuộc tập điểm mà một số cơ chế weaving hỗ trợ.

Do đó, luôn tách hai câu hỏi: “Điểm nào xuất hiện theo ngữ nghĩa thực thi?” và “Cơ chế AOP hiện tại **quan sát được** điểm nào?”.

## 4. Bốn tình huống làm số điểm runtime thay đổi

### 4.1. Điều kiện: một vị trí có thể không được thực thi

```java
if (enabled) {
    service.save();
}
```

Nếu `enabled == false`, biểu thức vẫn có trong source nhưng **không phát sinh lời gọi**. Advice không thể “ghi nhận sự kiện đã xảy ra” cho lời gọi vốn không diễn ra. Có thể một advice khác chạy ở điểm bao quanh `if` hoặc ở caller nếu công cụ hỗ trợ loại điểm ấy, nhưng đó là join point khác.

### 4.2. Vòng lặp: một vị trí phát sinh nhiều lượt

```java
for (int i = 0; i < 100; i++) {
    service.save();
}
```

Có một call site ở đoạn mã nhưng có thể có 100 lần gọi. Nếu advice đo thời gian chạy mỗi lần, lượng dữ liệu/chi phí sẽ tính theo **100 sự kiện runtime**, không theo một dòng source.

### 4.3. Đệ quy: một thân phương thức có nhiều lần được kích hoạt

```java
static int factorial(int n) {
    if (n <= 1) {
        return 1;
    }
    return n * factorial(n - 1);
}
```

Với `factorial(4)`, phần thân được vào cho `n = 4, 3, 2, 1`: **bốn lần thực thi** của cùng method. Có một biểu thức gọi đệ quy tại phần thân, được thực hiện **ba lần** ở lượt `n = 4, 3, 2`; lời gọi ban đầu tới `factorial(4)` xuất phát từ một vị trí khác. Vì thế count của *call* tại riêng vị trí đệ quy khác count *execution* của method.

Cũng không thể mặc định một proxy thuần runtime chặn lời gọi đệ quy nội bộ. Với wrapper/proxy thường gặp, lời gọi trên `this` hoặc gọi trực tiếp method trong target có thể đi **ngoài** wrapper. Weaving và các cơ chế khác có khả năng can thiệp khác. Phải kiểm tra call path thật.

### 4.4. Thread và bất đồng bộ: sự kiện còn phụ thuộc lịch chạy

Một call site gửi task có thể chạy một lần, nhưng task được thực hiện sau đó, ở thread khác, thậm chí không hoàn tất do cancellation. Một method trả `Future` hoặc một handle không đồng nghĩa kết quả công việc đã hoàn thành.

```text
Thread A                         Worker thread B
    |                                  |
    | submit(task)                      |
    |---- call xảy ra ----> queue ------+--> task.run() bắt đầu
    |                                  |
    +-- submit trả handle               +--> task.run() kết thúc
```

Nếu advice chọn điểm `submit`, nó quan sát **giai đoạn gửi**. Nếu chọn điểm `task.run` hoặc completion, nó quan sát **giai đoạn thực thi/hoàn tất** (với điều kiện công cụ nhìn thấy các điểm ấy). Không đồng nhất ba thời điểm. Thứ tự các sự kiện giữa thread có thể khác nhau, nên log cần thông tin tương quan và đồng hồ phù hợp; không suy ra thứ tự thời gian chỉ từ thứ tự dòng source ở các thread khác nhau.

## 5. Pointcut có thể xét tĩnh, xét động hoặc kết hợp cả hai

Một pointcut chọn **loại sự kiện nào** theo một số thông tin:

| Thông tin | Thường xác định được từ cấu trúc chương trình | Có thể cần dữ liệu runtime |
| --- | --- | --- |
| Method name, chữ ký, modifier | Có. | Thường không, trừ cơ chế đặc thù. |
| Package, class, inheritance khai báo | Có thể phân tích tĩnh nếu toàn bộ kiểu có sẵn. | Một số quan hệ kiểu/receiver cần xét thêm. |
| Annotation có trong artifact | Có thể xác định lúc build/weaving hoặc đọc metadata. | Nếu công cụ chọn tại runtime, phải thực hiện tra cứu tương ứng. |
| Kiểu thực của receiver | Không nhất thiết biết từ kiểu khai báo tại call site. | Có thể cần kiểm tra object thực. |
| Đối số có giá trị cụ thể | Không biết đầy đủ ở thời điểm phân tích source. | Phải quan sát từng lần gọi. |
| Thread ID, request context, luồng điều khiển | Không gắn cố định với vị trí source. | Cần ngữ cảnh của sự kiện runtime. |
| Kết quả/exception | Chưa xuất hiện trước khi thực thi. | Chỉ biết sau khi điểm liên quan trả về hoặc ném lỗi. |

Không phải mọi công cụ hỗ trợ tất cả loại matcher. Một engine có thể **lọc tĩnh** một số vị trí ứng viên rồi chèn kiểm tra điều kiện động cho từng lượt thực thi. Một proxy runtime đơn giản có thể chọn theo `Method` và args ngay trong handler. Hệ thống khác có thể kết hợp điều kiện ngay lúc biên dịch/weaving.

Giả mã mô tả một pointcut, **không phải cú pháp của thư viện cụ thể**:

```text
select:
    methodExecution belongsTo("operations")
    AND methodHasMarker("Observed")
    AND runtimeArgument("enabled") == true
```

Giả sử trong mã có **một vị trí** method execution phù hợp tên/marker, nhưng nó chạy 10 lần và chỉ 4 lần có `enabled = true`. Nếu engine thực sự hỗ trợ kiểm tra đối số như trên và advice được cài đúng, advice có thể chạy **4 lần**. Không thể lấy số điểm tĩnh nhân một hằng số tùy ý để suy ra số lần can thiệp.

### 5.1. Khi đọc biểu thức pointcut cần trả lời bốn câu hỏi

1. **Nó chọn loại join point gì?** Call, execution, field access, constructor hay event do wrapper cung cấp?
2. **Phần nào cố định trong chương trình?** Chữ ký, package, metadata hay vị trí bytecode?
3. **Phần nào được đánh giá theo từng lần xảy ra?** Đối tượng, đối số, context, return/throw?
4. **Lời gọi có thực sự đi qua cơ chế AOP không?** Proxy, weaving, instrumenter, compile transform đã được áp vào artifact đang chạy chưa?

Bỏ câu số 4 là nguyên nhân phổ biến của nhận định sai rằng “pointcut trông có vẻ khớp thì advice chắc chắn phải chạy”.

## 6. Thực hành Java 17: một call site, nhiều lần runtime, nhiều implementation

Ví dụ dưới dùng **Java thuần**, chưa cài engine AOP, để bạn thấy rõ khác biệt giữa một biểu thức gọi trong source và từng lần thực thi. Các dòng `CALL` và `EXECUTE` là log do ta chủ động đặt, **không phải advice tự động**.

Tạo tệp `SourceVsRuntimeDemo.java`:

```java
public class SourceVsRuntimeDemo {
    interface Handler {
        String handle(int value);
    }

    static final class DoubleHandler implements Handler {
        @Override
        public String handle(int value) {
            System.out.println("EXECUTE DoubleHandler.handle " + value);
            return "double=" + (value * 2);
        }
    }

    static final class SquareHandler implements Handler {
        @Override
        public String handle(int value) {
            System.out.println("EXECUTE SquareHandler.handle " + value);
            return "square=" + (value * value);
        }
    }

    static void dispatch(Handler handler, int count) {
        for (int i = 1; i <= count; i++) {
            System.out.println("CALL dispatch site value=" + i);
            String result = handler.handle(i);
            System.out.println("RESULT " + result);
        }
    }

    public static void main(String[] args) {
        dispatch(new DoubleHandler(), 2);
        dispatch(new SquareHandler(), 1);
        dispatch(new DoubleHandler(), 0);
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac SourceVsRuntimeDemo.java
java SourceVsRuntimeDemo
```

Kết quả chuẩn:

```text
CALL dispatch site value=1
EXECUTE DoubleHandler.handle 1
RESULT double=2
CALL dispatch site value=2
EXECUTE DoubleHandler.handle 2
RESULT double=4
CALL dispatch site value=1
EXECUTE SquareHandler.handle 1
RESULT square=1
```

Phân tích theo đúng từng phép đếm:

- Trong `dispatch` có **một biểu thức** `handler.handle(i)` đóng vai trò call site nguồn.
- `dispatch(DoubleHandler, 2)` cho hai lượt, `dispatch(SquareHandler, 1)` cho một lượt, `dispatch(DoubleHandler, 0)` không cho lượt nào. Tổng cộng có **ba lần gọi runtime** từ chính call site ấy.
- Runtime dispatch chọn body `DoubleHandler.handle` **hai lần**, `SquareHandler.handle` **một lần**; cùng một call site, nhưng khác target implementation.
- Không thể suy luận “một dòng `handle` = một lần advice” hoặc “interface `Handler` = một body duy nhất”.
- Nếu mô hình AOP có join point dạng **method-call**, điểm phía caller có thể là ba occurrence từ một vị trí `handler.handle(i)`. Nếu có **method-execution**, ta có hai occurrence thực thi body `DoubleHandler.handle` và một occurrence `SquareHandler.handle`. Đây là diễn giải khái niệm theo mô hình **nếu có hỗ trợ hai loại join point**; ví dụ Java trên không tự tạo AOP.

**Tự thử:** Đổi `dispatch(new SquareHandler(), 1)` thành `dispatch(new SquareHandler(), 3)`. Vị trí call-site không đổi nhưng sẽ có thêm hai lần gọi; hãy dự đoán toàn bộ stdout trước khi chạy.

## 7. Ví dụ cơ chế AOP một phần: proxy quan sát lần gọi chứ không “sở hữu dòng source”

JDK cung cấp **dynamic proxy theo interface**. Handler có thể chạy mỗi khi caller gọi phương thức thông qua đối tượng proxy. Kỹ thuật này minh họa một điểm quan trọng: **một cơ chế can thiệp có thể nhận runtime event mà không có biểu thức chọn địa chỉ source call site**.

Để đơn giản, demo dùng một interface `Gateway`, một target thật và một proxy. Handler chỉ ghi sự kiện cho phương thức `send`. Đây là **minh họa một cơ chế theo tư duy AOP**, không phải một engine AOP đầy đủ; nó không định nghĩa tập pointcut hoặc join-point shadow của mọi công nghệ.

Tạo tệp `RuntimeInterceptionDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class RuntimeInterceptionDemo {
    interface Gateway {
        String send(String message);
    }

    static final class RealGateway implements Gateway {
        @Override
        public String send(String message) {
            if (message.isBlank()) {
                throw new IllegalArgumentException("empty message");
            }
            System.out.println("TARGET send " + message);
            return "ACK " + message;
        }
    }

    static Gateway observing(Gateway target) {
        return (Gateway) Proxy.newProxyInstance(
                Gateway.class.getClassLoader(),
                new Class<?>[] { Gateway.class },
                (proxy, method, methodArgs) -> {
                    if (!method.getName().equals("send")) {
                        return method.invoke(target, methodArgs);
                    }
                    System.out.println("ADVICE before send");
                    try {
                        Object result = method.invoke(target, methodArgs);
                        System.out.println("ADVICE returning send");
                        return result;
                    } catch (InvocationTargetException ex) {
                        System.out.println("ADVICE throwing send");
                        throw ex.getCause();
                    }
                }
        );
    }

    public static void main(String[] args) {
        Gateway target = new RealGateway();
        Gateway proxy = observing(target);

        for (int i = 1; i <= 2; i++) {
            System.out.println("CALL through proxy " + i);
            System.out.println("RESULT " + proxy.send("M" + i));
        }

        System.out.println("CALL direct");
        System.out.println("RESULT " + target.send("M3"));

        try {
            proxy.send("");
        } catch (IllegalArgumentException ex) {
            System.out.println("CALLER caught " + ex.getMessage());
        }
    }
}
```

Chạy:

```bash
javac RuntimeInterceptionDemo.java
java RuntimeInterceptionDemo
```

Stdout kỳ vọng:

```text
CALL through proxy 1
ADVICE before send
TARGET send M1
ADVICE returning send
RESULT ACK M1
CALL through proxy 2
ADVICE before send
TARGET send M2
ADVICE returning send
RESULT ACK M2
CALL direct
TARGET send M3
RESULT ACK M3
ADVICE before send
ADVICE throwing send
CALLER caught empty message
```

### 7.1. Đếm đúng các sự kiện

- Biểu thức `proxy.send("M" + i)` có **một vị trí nguồn**, được thực thi hai lần; handler quan sát **hai** lượt.
- Biểu thức `target.send("M3")` là vị trí khác, nhưng **không qua proxy**, nên không có dòng advice.
- Biểu thức `proxy.send("")` là một vị trí nữa và tạo thêm **một** lần handler được kích hoạt ở đường exception.
- Tổng số lần `RealGateway.send` chạy: **bốn**; tổng số lần handler ghi `ADVICE before send`: **ba**. Sự khác nhau đến từ **đường gọi**, không phải do source code của `send` thay đổi.
- `Method.invoke` bọc exception do target ném trong `InvocationTargetException`; handler truyền tiếp `ex.getCause()` để caller nhận `IllegalArgumentException` gốc.

### 7.2. Điều gì xảy ra nếu có self-invocation?

Nếu `RealGateway.send` tự gọi một phương thức khác trên `this`, lời gọi đó **không tự đi qua proxy** ở ví dụ này. Một số cơ chế weaving có thể can thiệp điểm nằm bên trong target; không được suy từ hạn chế của ví dụ proxy ra mọi công nghệ AOP.

### 7.3. Tại sao handler không đủ để tìm “dòng source đã gọi”?

Handler nhận `Method`, args và đối tượng target mà mã thiết kế cho nó nắm giữ. Nó **không tự được cung cấp một ánh xạ chính xác** từ sự kiện tới dòng source của caller. Có thể dùng stack trace hoặc công cụ instrumentation để hỗ trợ truy xuất, nhưng line numbers có thể không tồn tại hoặc không còn 1:1 sau compile, tạo mã, inlining hoặc tối ưu. Một bộ AOP có hỗ trợ method-call join point tại source/bytecode có thể nắm vị trí khác, tùy thiết kế.

## 8. Từ source đến bytecode: đừng mặc định ánh xạ một-một

Trong thực tế, mã được biên dịch hoặc biến đổi:

```text
Mã nguồn
  -> biểu diễn compiler / bytecode / mã được sinh
  -> linking, class loading, instrumentation, JIT (nếu có)
  -> sự kiện thực thi được quan sát
```

Tùy ngôn ngữ và công cụ:

- Một biểu thức nguồn có thể tạo **nhiều instruction hoặc helper method**. Lambda, generic bridge, coroutine state machine, synthetic accessors và code generation có thể làm cấu trúc runtime khác source.
- Một method source có thể không còn cấu trúc dễ nhận diện sau inlining/tối ưu. Công cụ weaving hoặc profiler có cách bảo toàn/nghiệm lại ngữ nghĩa riêng; không suy ra số sự kiện từ bytecode một cách tùy tiện.
- Một vị trí bytecode có thể được thực thi nhiều lần. Một lần dynamic event có thể không có thông tin dòng source nếu artifact không chứa debug symbols.
- Cơ chế source weaving và bytecode weaving có thể mô tả “vị trí tĩnh” ở tầng khác nhau; proxy thuần runtime lại quan sát qua **đối tượng đại diện**.

Vì thế, từ “điểm trong mã nguồn” trong lời giải thích thường là lối nói dễ học cho **vị trí tĩnh có thể xác định**, nhưng khi làm kỹ thuật thực tế cần chỉ rõ tầng đang xét: source syntax, AST, bytecode, instruction, method descriptor hay runtime proxy entry.

### Phân biệt nơi đặt hook với nơi xảy ra kết quả

Một advice around có thể bao quanh cả method execution; pointcut chọn từ chữ ký tĩnh nhưng advice đo một **khoảng thời gian runtime**. Nếu method ném exception ở dòng sâu trong thân, cùng join point execution đó kết thúc theo đường throwing. Đừng nghĩ mỗi nhánh return/throw đòi hỏi một “dòng source mới” để advice có thể quan sát, trừ khi công cụ mô hình hóa chúng thành những join point khác.

## 9. Từ một vị trí tĩnh đến nhiều sự kiện khi áp dụng pointcut

Giả sử có pointcut mô tả:

```text
execution method whose name is "send"
AND runtime argument message is nonempty
```

Đây là **giả mã**, không phải cú pháp hợp lệ chung. Trong một công cụ hỗ trợ bộ điều kiện này:

1. Quy tắc theo tên/chữ ký có thể thu hẹp tập điểm **theo cấu trúc chương trình**.
2. Kiểm tra đối số không rỗng cần dùng giá trị ở **mỗi lần gọi runtime**.
3. Advice được áp dụng cho các lần thỏa **toàn bộ điều kiện**, qua cơ chế weaving/proxy đã được kích hoạt.
4. Hai lần thực thi cùng method có thể cho kết quả matching khác nhau vì args khác.

Bảng đối chiếu:

| Tình huống | Cùng một vị trí tĩnh? | Có sự kiện runtime? | Advice có nhất thiết chạy? |
| --- | --- | --- | --- |
| Method không bao giờ được gọi | Có vị trí khả dĩ. | Không. | Không có sự kiện tương ứng để áp dụng advice. |
| Call site trong loop chạy 5 lần | Một call site. | Có thể 5 lần call. | Tùy loại pointcut, điều kiện và đường can thiệp. |
| Method được gọi hai lần với args khác nhau | Có thể cùng call site/method. | Hai sự kiện. | Có thể chọn một, cả hai hoặc không sự kiện nào. |
| Target được gọi trực tiếp, không qua proxy | Source method vẫn tồn tại. | Có execution thật. | Handler trên proxy không chạy cho đường gọi đó. |
| Method được weave vào bytecode | Vị trí trong artifact đã được biến đổi. | Mỗi lần thực thi có thể kích hoạt hook. | Còn phụ thuộc pointcut, điều kiện và triển khai thực tế. |
| Gửi task async rồi task chưa chạy | Call site submit có thể đã xảy ra. | Sự kiện submit có; task execution có thể chưa. | Phụ thuộc chọn điểm submit hay task execution/completion. |

Nếu mục tiêu là **đếm số lần xử lý**, phải định nghĩa rõ bạn đếm **invocation attempted**, **execution entered**, **completed successfully**, **thrown**, hay **logical operation**. Chúng khác nhau khi retry, cancellation, timeout, lỗi trước target, hoặc kết quả trả về là handle bất đồng bộ.

## 10. Hậu quả thiết kế: chọn pointcut ở sai tầng tạo ra lỗi khó nhận ra

### 10.1. Muốn áp dụng vào một nhóm method nhưng chọn theo call site

Một chính sách đo thời gian của `save` có thể cần bao phủ mọi lần thực thi của method. Nếu pointcut chỉ chọn vài vị trí **gọi** trong module A mà lời gọi từ module B bị bỏ qua, kết quả đếm có thể thiếu. Ngược lại, một chính sách gắn với caller cụ thể có thể cần method-call join point để biết ngữ cảnh phía caller.

**Đặt câu hỏi nghiệp vụ kỹ thuật:** Muốn chặn “hành vi method được thực thi” hay “caller ở một nơi cụ thể thực hiện lời gọi”? Sau đó mới chọn loại join point.

### 10.2. Log và overhead phụ thuộc số sự kiện, không phải số dòng

Pointcut khớp một call site trong hot loop có thể tạo triệu advice executions mỗi giây. Một dòng log ở mỗi lượt có thể gây áp lực I/O lớn. Phải benchmark theo **tần suất runtime**, sampling và workload thật. Đếm có bao nhiêu dòng source được weave chỉ giúp hiểu **phạm vi vị trí**, không đủ để ước lượng tổng overhead.

### 10.3. Điểm tĩnh trông khớp nhưng advice không chạy

Những nguyên nhân cần xét:

- Nhánh code chưa được đi qua; event chưa xảy ra.
- Dữ liệu runtime không thỏa điều kiện pointcut.
- Lời gọi đi trực tiếp vào target thay vì qua proxy.
- Pointcut đặt ở loại join point khác (call thay vì execution, hoặc ngược lại).
- Đối tượng runtime/overload/implementation thực không như giả định.
- Aspect chưa được đăng ký, class chưa được weave hoặc artifact chạy khác artifact được kiểm tra.
- Giới hạn ngôn ngữ/công cụ: `final`, `private`, constructor, module, classloader hoặc loại join point chưa hỗ trợ.

Kiểm tra từng nguyên nhân bằng quan sát có kiểm soát; không kết luận chỉ từ việc biểu thức pointcut “nhìn đúng”.

### 10.4. Advice chạy nhiều lần hơn dự tính

Những nguyên nhân:

- Một call site được lặp hoặc tái gọi bởi recursion.
- Thao tác bị retry do hệ thống khác hoặc do chính around advice gọi tiếp nhiều lần.
- Có nhiều caller dẫn đến cùng method execution.
- Nhiều advice/instance của aspect khớp cùng sự kiện.
- Nested wrapper hoặc instrumentation đôi có thể làm một logical operation đi qua nhiều lớp.
- Tác vụ được chạy lại sau lỗi, timeout hoặc cơ chế delivery ít nhất một lần.

Khi điều tra, cần gắn correlation ID cho **logical operation** và phân biệt nó với invocation ID cho **mỗi lần chạy**. Không nên gộp chúng thành một con số nếu nghiệp vụ cần phân biệt.

## 11. Cách kiểm thử ranh giới source/runtime

Một bộ test tốt cần vừa chứng minh **positive matching** vừa chứng minh **negative matching**, đồng thời kiểm tra số occurrence thực tế.

| Ca kiểm thử | Thiết lập | Kỳ vọng cần xác nhận |
| --- | --- | --- |
| Zero occurrence | Nhánh bỏ qua call site hoặc loop 0 lượt. | Không có advice do sự kiện đó gây ra. |
| One occurrence | Gọi một lần qua đường được can thiệp. | Advice chạy đúng số lượt và đúng thứ tự đã thiết kế. |
| Many occurrences | Gọi cùng call site N lượt. | Số lần advice tỷ lệ với những occurrence thực sự thỏa rule, không theo số dòng. |
| Polymorphic target | Cùng call site nhưng hai implementation. | Kết quả chọn theo chữ ký tĩnh/kiểu runtime đúng hợp đồng. |
| Direct target vs proxy | Gọi qua proxy và trực tiếp. | Xác nhận giới hạn đường can thiệp của proxy. |
| Method-call vs execution | Dùng công cụ hỗ trợ cả hai loại. | Quan sát đúng nơi caller/callee, không lẫn các loại. |
| Recursion/nested call | Gọi method đệ quy hoặc method khác trong target. | Đếm và thứ tự rõ; đặc biệt kiểm tra self-invocation. |
| Dynamic filter | Đổi giá trị args/context trên cùng call site. | Chỉ những occurrence thỏa predicate được chọn. |
| Exception path | Target ném lỗi. | Advice after-throwing/finally hoạt động theo hợp đồng; caller nhận lỗi đúng. |
| Async | Gửi task rồi hoàn tất ở thời điểm sau. | Tách submit event, execute event, completion event. |
| Weaving/config mismatch | Chạy đúng artifact sản xuất. | Xác nhận hook thật sự được cài, không chỉ khớp ở bản demo. |

Nên lấy bằng chứng từ output, metric, trace hoặc bộ đếm trong **môi trường có cơ chế AOP thật**, không chỉ từ unit test gọi thẳng vào đối tượng target. Với những công cụ hỗ trợ công bố join-point matching hoặc inspect bytecode, kết hợp thông tin đó với test runtime để xác nhận cả “nơi có khả năng tác động” và “nơi đã xảy ra sự kiện”.

### Một phép kiểm chứng bằng số

Giả sử có hai method:

- `A.save()` được gọi 10 lượt và thỏa pointcut ở cả 10.
- `B.save()` được gọi 7 lượt nhưng 3 lượt có args không thỏa điều kiện động.
- Hai method được gọi bằng đường AOP đang can thiệp đầy đủ, mỗi occurrence được chọn chỉ chạy một advice duy nhất, không có retry.

Khi đó số lần advice kỳ vọng là **10 + (7 − 3) = 14**, dù số method declaration chỉ bằng 2. Kết quả 14 dựa trên giả thiết đường chạy và điều kiện rõ ràng; thay dữ liệu, scheduling, retry hoặc cấu hình thì phép đếm phải tính lại.

## 12. Các lỗi tư duy phổ biến

**“Có một lời gọi trong source thì sẽ có một join point.”** Chưa đủ. Cần nêu loại join point và hiểu một vị trí có thể tạo 0, 1 hoặc nhiều occurrence.

**“Join point chính là số dòng code.”** Không. Line number chỉ là thông tin vị trí phục vụ người đọc/debug; nhiều statement có thể cùng dòng, một statement có thể trải nhiều dòng, compiler có thể sinh code và loại bỏ thông tin debug.

**“Method-call và method-execution tương đương.”** Không. Một bên gắn với phía gọi, một bên với lúc thực thi body; tập điểm được chọn và ngữ cảnh khác nhau.

**“Pointcut khớp chữ ký là advice nhất định chạy.”** Sai nếu runtime không đi qua điểm đó, điều kiện động sai hoặc cơ chế can thiệp không được kích hoạt/bao phủ đường gọi.

**“Mọi lượt thực thi một method đều đi qua interface proxy.”** Sai: còn đường gọi trực tiếp vào target và lời gọi nội bộ. Phạm vi phụ thuộc mô hình AOP cụ thể.

**“Đếm aspect advice bằng số method có annotation.”** Sai: đó có thể chỉ là số ứng viên, trong khi số advice executions phụ thuộc từng lượt thực thi và điều kiện.

**“Sau khi async method trả về là tác vụ đã xong.”** Sai với các API trả handle trước thời điểm completion. Cần đặt hook tại đúng loại sự kiện muốn đo.

**“Một kết quả nghiệp vụ đồng nghĩa một lần invocation.”** Không nhất thiết: retry, idempotency, phân tán, batching và cancellation có thể tạo quan hệ nhiều-một hoặc không có kết quả.

## 13. Bài tập tự đánh giá

### Câu 1 — Loop và condition

```java
for (int i = 0; i < 6; i++) {
    if (i % 2 == 0) {
        task.run(i);
    }
}
```

Có bao nhiêu biểu thức gọi `task.run(i)` trong đoạn mã, và bao nhiêu lần gọi thực sự diễn ra nếu vòng lặp chạy bình thường? **Đáp án:** một vị trí mã; ba lần gọi với `i = 0, 2, 4`.

### Câu 2 — Đa hình

Một biến kiểu `Processor` nhận lần lượt đối tượng `SafeProcessor` và `FastProcessor` ở hai vòng lặp. Cùng một biểu thức `processor.process()` được gọi 5 lần trên mỗi đối tượng. Có bao nhiêu vị trí call site và bao nhiêu occurrence? **Đáp án:** một call site trong giả thiết đoạn code chỉ viết biểu thức đó một lần; 10 occurrence; body thực thi được quyết định bởi target runtime.

### Câu 3 — Đệ quy

`factorial(4)` có bao nhiêu lần vào phần thân `factorial` và bao nhiêu lần thực thi biểu thức gọi đệ quy `factorial(n - 1)`? **Đáp án:** bốn lượt execution của thân method, ba lượt call tại biểu thức đệ quy. Lời gọi ban đầu xuất phát từ caller.

### Câu 4 — Proxy

Một lời gọi `proxy.save()` được handler ghi nhận, nhưng `target.save()` không được ghi nhận. Điều này có mâu thuẫn với thực tế cả hai chạy cùng method nghiệp vụ không? **Đáp án:** không. Handler được gắn vào **đường gọi qua proxy**, không tự chặn mọi execution của target.

### Câu 5 — Điểm đặt đo thời gian

Bạn cần đo toàn bộ thời gian hoàn tất job bất đồng bộ, nhưng advice after-returning chỉ quan sát lúc phương thức gửi job trả `Future`. Nên làm gì? **Đáp án:** xác định và instrument thêm sự kiện hoàn tất của future/task; phân biệt submit latency với end-to-end latency và xử lý exception/cancellation.

### Câu 6 — Kiểm chứng pointcut

Một marker xuất hiện trên method nhưng không thấy advice. Nêu ít nhất ba khả năng khác nhau. **Đáp án gợi ý:** marker đặt trên vị trí metadata mà matcher không đọc; đường gọi bỏ qua proxy; method chưa từng được chạy; điều kiện runtime không thỏa; engine chưa kích hoạt hoặc artifact chưa được weave.

## Kết luận

Trong AOP, **vị trí mã tĩnh** trả lời “chương trình có thể tạo ra điểm can thiệp ở đâu?”, còn **sự kiện runtime** trả lời “điều gì đã thật sự xảy ra tại lần chạy này?”. Với các mô hình hỗ trợ khái niệm *join-point shadow*, shadow nối giữa hai góc nhìn; với proxy hay kỹ thuật khác, ranh giới quan sát được xác định theo đường gọi và hợp đồng triển khai. Một source call site có thể tạo vô số lần runtime, có thể chọn nhiều implementation và có thể bị bỏ qua hoàn toàn. Vì vậy, trước khi đếm advice hoặc đặt pointcut, hãy xác định **loại join point, tầng mã đang xét, điều kiện động và con đường thật mà chương trình chạy qua**.
