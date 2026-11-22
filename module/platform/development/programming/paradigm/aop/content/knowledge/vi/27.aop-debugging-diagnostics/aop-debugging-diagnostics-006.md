# Đọc ngăn xếp lời gọi có advice và mã được sinh

## 1. Vì sao stack trace của chương trình AOP trông khác mã nguồn?

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), một lời gọi nghiệp vụ có thể được bao quanh bởi nhiều **advice**: ghi log, đo thời gian, xác thực, thử lại, kiểm soát giao dịch hoặc đổi cách xử lý ngoại lệ. Tùy cơ chế áp dụng AOP, runtime còn có thể tạo **proxy**, trình chuyển tiếp lời gọi, hàm phụ trợ hoặc mã đã được **weave** (đan vào bytecode). Vì vậy, ngăn xếp lời gọi có thể chứa những frame không có dòng mã trực tiếp tương ứng trong phần nghiệp vụ mà lập trình viên đang đọc.

Mục tiêu của bài này là biết **đọc đúng đường đi thực thi**, nhận ra ranh giới giữa target, advice và mã do công cụ tạo ra, rồi truy tìm nguyên nhân lỗi mà không đổ lỗi cho frame lạ xuất hiện trong trace.

Sau bài học, bạn có thể:

- Đọc stack trace theo chiều từ vị trí ném ngoại lệ về người gọi, đồng thời phân biệt ngoại lệ gốc với wrapper và cause.
- Nhận diện khả năng xuất hiện của frame advice, target, proxy, reflection, bridge, lambda và mã được weave.
- Hiểu vì sao cùng một ngoại lệ có thể tạo các dạng stack trace khác nhau tùy điểm quan sát và thứ tự advice.
- Dùng một chương trình Java 17+ độc lập để tái hiện và phân loại các frame thực tế.
- Sử dụng trace đầy đủ, thông tin proxy/weaving, vị trí bytecode và các tín hiệu chẩn đoán để xác minh giả thuyết.

**Giới hạn phạm vi:** đây là kiến thức AOP tổng quát. Java dynamic proxy trong ví dụ là một phương tiện học cơ chế chặn lời gọi và mã sinh lúc chạy. Những hệ AOP dùng weaving khi biên dịch hoặc khi tải lớp có thể hiện ra các frame khác nhau; phải kiểm tra cơ chế và phiên bản cụ thể trước khi kết luận.

## 2. Phân biệt “call stack đang chạy” với “stack trace của ngoại lệ”

Một **stack frame** biểu diễn một lần kích hoạt phương thức: có phương thức đang thực hiện, điểm quay về và dữ liệu thực thi liên quan. Khi phương thức A gọi B, thông thường frame B nằm phía trên frame A trong ngăn xếp đang hoạt động. Khi B trả về, frame B được gỡ khỏi ngăn xếp.

Có hai loại thông tin thường bị gọi chung là “stack”:

| Loại | Chụp tại thời điểm nào? | Trả lời câu hỏi gì? |
| --- | --- | --- |
| **Stack trace của Throwable** | Thường được ghi tại lúc đối tượng Throwable được tạo/điền trace, có thể thay đổi nếu gọi fillInStackTrace hoặc thay thế Throwable. | Ngoại lệ đã phát sinh qua đường gọi nào? |
| **Call stack hiện tại** | Tại thời điểm đọc Thread.getStackTrace, StackWalker hoặc thread dump. | Luồng này đang thực hiện điều gì ngay bây giờ? |

Điều này dẫn tới một bẫy rất phổ biến: trong catch của advice, **target có thể đã unwind khỏi ngăn xếp hiện tại**, nhưng target vẫn xuất hiện trong stack trace **được lưu trong ngoại lệ gốc**. Nếu advice chụp ngăn xếp mới bằng Thread.currentThread().getStackTrace(), trace đó mô tả thời điểm catch, không nhất thiết mô tả nơi lỗi xuất hiện.

Với Java, đối tượng StackTraceElement thường có:

- Tên class và phương thức (getClassName, getMethodName).
- Tên tệp và số dòng nếu thông tin có sẵn (getFileName, getLineNumber).
- Dấu hiệu phương thức native (isNativeMethod).
- Trong các JDK hiện đại, thông tin module/class loader có thể hiện trong cách biểu diễn frame.

**Không được giả định mọi frame đều có file và số dòng:** mã sinh lúc chạy, class thiếu debug information, native method hoặc lớp được biến đổi có thể xuất hiện dưới dạng Unknown Source hay không có số dòng. Tên class của proxy sinh động cũng có thể khác giữa JDK và các lần chạy.

## 3. Cách đọc một stack trace có advice

Xét sơ đồ minh họa, không phải log cố định cho mọi JVM:

~~~text
java.lang.IllegalArgumentException: invalid
    at example.OperationImpl.run(OperationImpl.java:...)
    at ...reflective invocation...
    at example.TraceHandler.invoke(TraceHandler.java:...)
    at ...$Proxy0.run(Unknown Source)
    at example.Application.main(Application.java:...)
~~~

Ở stack trace thường được in bởi Throwable.printStackTrace(), **frame trên cùng** thường chỉ tới vị trí Throwable ghi nhận trace; đi dần xuống là các bước gọi dẫn tới vị trí đó. Với ngoại lệ phát sinh từ target trong sơ đồ:

1. **OperationImpl.run**: mã nghiệp vụ tạo/ném IllegalArgumentException; bắt đầu phân tích nguyên nhân ở đây.
2. **Reflection**: tầng trung gian chuyển tiếp lời gọi bằng Method.invoke; sự hiện diện của nó không tự chứng minh đây là nơi tạo ra lỗi nghiệp vụ.
3. **TraceHandler.invoke**: lời gọi đã đi qua advice hoặc bộ chặn đang bao quanh target.
4. **$Proxy0.run**: phương thức chuyển tiếp do runtime tạo cho proxy; nó kết nối người gọi với handler.
5. **Application.main**: caller phía ngoài đã gọi qua proxy.

**Đọc theo chiều ngược khi cần dựng luồng:** người gọi ở dưới → proxy → advice → reflection → target ở trên. Ngược lại, để truy vết ngoại lệ từ nơi ném, đọc từ trên xuống dưới. Cùng một trace nhưng hai hướng giúp trả lời hai câu hỏi khác nhau.

### 3.1. Phân loại frame bằng vai trò, không chỉ tên

| Vai trò | Dấu hiệu nhận diện | Điều cần xác minh |
| --- | --- | --- |
| Target nghiệp vụ | Class/phương thức đã viết, nơi phát lỗi hoặc tính toán. | Lỗi xuất phát thật từ target, hay target chỉ bị gọi lại? |
| Advice | Hàm advice, handler, interceptor hoặc đoạn mã do công cụ weave vào luồng thực thi. | Advice chạy trước, quanh hay sau target; advice có đổi return/exception không? |
| Proxy/dispatcher | Tên lớp được tạo động hoặc lớp forwarding. | Caller có đi qua proxy không; proxy áp dụng cho những phương thức nào? |
| Reflection/method handle | java.lang.reflect, cơ chế invoke hay adapter. | Có wrapper ngoại lệ? Có cần đi tiếp vào cause để thấy lỗi gốc không? |
| Generated helper | Hàm phụ trợ, accessor, bridge, lambda, method sinh bởi bytecode tool. | Đây là mã tạo/cải biến nào, và có source map/line mapping không? |
| Caller | Mã gọi API/proxy/target. | Ai kích hoạt lời gọi, qua đường nào, có bỏ qua interception không? |

Các dấu hiệu này chỉ là **manh mối**, không phải quy tắc đặt tên chuẩn cho mọi công cụ. Một advice được weave trực tiếp vào target có thể **không có frame advice riêng** như một phương thức độc lập. Một proxy có thể không được đặt tên theo mẫu “$Proxy”. Một frame tên giống mã sinh chưa đủ để xác nhận nguồn gốc; dùng cơ chế áp dụng và bytecode nếu cần.

### 3.2. Join point và pointcut ảnh hưởng cách hiểu trace

**Join point** là vị trí/sự kiện thực thi mà AOP có thể can thiệp; **pointcut** xác định tập join point được chọn. Một hệ AOP có thể hỗ trợ join point khi **gọi** phương thức, khi **thực thi** phương thức, truy cập trường, xử lý ngoại lệ hoặc kiểu sự kiện khác; không có bảo đảm mọi hệ đều hỗ trợ các loại giống nhau.

Đặc biệt, phân biệt **vị trí call** với **vị trí execution**. Nếu target thực thi dưới một lớp proxy, trace có thể chứa proxy như một điểm chuyển tiếp. Nếu bytecode được weave vào target, advice có thể nằm ngay trong thân code đã biến đổi. Sự khác biệt về frame là hệ quả của mô hình thực thi, không nhất thiết là sai lệch chức năng.

## 4. Thứ tự advice quyết định các frame được quan sát

Giả sử có hai advice around: **TRACE** ghi dấu vết và **RETRY** gọi lại khi gặp lỗi tạm thời. Chúng có thể lồng nhau theo hai cách:

~~~text
TRACE ngoài RETRY:
caller
  TRACE.enter
    RETRY.enter
      target attempt 1 -> lỗi
      target attempt 2 -> thành công
  TRACE.exit

RETRY ngoài TRACE:
caller
  RETRY.enter
    TRACE.enter
      target attempt 1 -> lỗi
    TRACE.error
    TRACE.enter
      target attempt 2 -> thành công
    TRACE.exit
~~~

Một Throwable phát sinh ở lần đầu có thể ghi lại những tầng đang nằm trên đường gọi tới target. Nếu advice ở vòng ngoài xử lý và nuốt ngoại lệ, người gọi có thể chỉ nhận kết quả thành công và **không có stack trace lỗi được ném tiếp**. Nếu advice catch rồi **ném lại cùng đối tượng Throwable**, trace gốc thường vẫn mô tả vị trí trước đó; nếu advice tạo **Throwable mới**, frame trên cùng của ngoại lệ mới lại phản ánh nơi tạo/ghi stack mới. Việc đọc cả **cause chain** trở nên rất quan trọng.

Với advice before hoặc after, không nên suy luận từ tên loại advice rằng một frame chắc chắn xuất hiện trước hay sau một frame target trong stack trace. Chỉ những phương thức **đang có mặt trên ngăn xếp khi trace được ghi** mới có thể hiện diện trong trace đó. Ví dụ: một đoạn after chạy trong finally khi đang unwind có thể thực thi nhưng không xuất hiện trong stack trace được lưu trước đó của ngoại lệ.

Vì vậy, để xác định thứ tự thực:
- Ghi sự kiện ngay tại ranh giới **advice enter/exit**, **trước/sau proceed**, target enter và exception catch.
- Ghi một định danh lời gọi logic và số thứ tự attempt nếu có retry.
- Đối chiếu trace và log sự kiện. Đừng kết luận precedence từ thứ tự class trên đĩa hoặc tên phương thức.

## 5. Ví dụ Java 17+: nhận diện frame target, advice, proxy sinh động và caller

Ví dụ này sử dụng JDK dynamic proxy để mô phỏng một advice kiểu around. Target ném IllegalArgumentException. Handler gọi target bằng reflection, bắt InvocationTargetException, lấy **ngoại lệ gốc**, đọc stack trace của ngoại lệ, rồi ném lại chính ngoại lệ đó.

Lưu toàn bộ mã sau thành **AdviceStackTraceDemo.java**:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AdviceStackTraceDemo {
    interface Operation {
        String run();
    }

    static final class OperationImpl implements Operation {
        @Override
        public String run() {
            throw new IllegalArgumentException("invalid");
        }
    }

    static final class TraceHandler implements InvocationHandler {
        private final Operation target;

        TraceHandler(Operation target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            System.out.println("advice: enter");
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException wrapper) {
                Throwable original = wrapper.getCause();
                System.out.println("advice: caught "
                        + original.getClass().getSimpleName());
                printRelevantFrames(original);
                throw original;
            } finally {
                System.out.println("advice: exit");
            }
        }
    }

    private static void printRelevantFrames(Throwable failure) {
        for (StackTraceElement frame : failure.getStackTrace()) {
            String owner = frame.getClassName();
            String method = frame.getMethodName();
            if (owner.equals(OperationImpl.class.getName())) {
                System.out.println("frame: TARGET." + method);
            } else if (owner.equals(TraceHandler.class.getName())) {
                System.out.println("frame: ADVICE." + method);
            } else if (owner.contains("$Proxy") && method.equals("run")) {
                System.out.println("frame: GENERATED_PROXY." + method);
            } else if (owner.equals(AdviceStackTraceDemo.class.getName())
                    && method.equals("main")) {
                System.out.println("frame: CALLER." + method);
            }
        }
    }

    public static void main(String[] args) {
        Operation operation = (Operation) Proxy.newProxyInstance(
                Operation.class.getClassLoader(),
                new Class<?>[] { Operation.class },
                new TraceHandler(new OperationImpl()));
        try {
            operation.run();
        } catch (IllegalArgumentException failure) {
            System.out.println("caller: " + failure.getMessage());
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac AdviceStackTraceDemo.java
java AdviceStackTraceDemo
~~~

**Stdout xác nhận khi chạy bằng JDK 21** (mã dùng cú pháp tương thích Java 17):

~~~text
advice: enter
advice: caught IllegalArgumentException
frame: TARGET.run
frame: ADVICE.invoke
frame: GENERATED_PROXY.run
frame: CALLER.main
advice: exit
caller: invalid
~~~

Chương trình in **các frame quan trọng đã lọc và gắn nhãn**, nên kết quả trên không phải nguyên văn Throwable.printStackTrace(). Phần phản chiếu Java có thể thêm các frame khác tùy phiên bản JDK. Bộ lọc cố ý không in số dòng hay package proxy để đầu ra minh họa ổn định.

### 5.1. Giải thích vì sao thứ tự đó xuất hiện

- Khi main gọi **operation.run()**, đối tượng đang được gọi là proxy triển khai interface Operation. Phương thức proxy sinh động chuyển tiếp vào InvocationHandler.
- **TraceHandler.invoke** tương đương một điểm bao quanh lời gọi: ghi “enter”, gọi method.invoke trên target rồi quan sát kết quả/lỗi.
- **Method.invoke** ném InvocationTargetException bọc Throwable do target ném. Handler dùng getCause để lấy IllegalArgumentException gốc.
- **failure.getStackTrace()** chứa đường đi lúc ngoại lệ gốc hình thành, từ OperationImpl.run ngược qua handler, proxy rồi main. Bởi vậy các frame được lọc theo thứ tự TARGET → ADVICE → GENERATED_PROXY → CALLER.
- Handler ném lại **cùng đối tượng** original. Khối finally in “advice: exit” khi handler kết thúc; main sau đó bắt được IllegalArgumentException với thông điệp “invalid”.

**Điểm tinh tế:** trong lúc printRelevantFrames(original) đang chạy, OperationImpl.run đã không còn thực thi trên call stack hiện hành, nhưng frame TARGET vẫn có trong **trace được lưu của ngoại lệ**. Nếu thay original.getStackTrace() bằng Thread.currentThread().getStackTrace(), những frame được nhìn thấy sẽ mô tả việc đang ở trong hàm chẩn đoán.

### 5.2. Ví dụ chứng minh điều gì và không chứng minh điều gì?

Ví dụ chứng minh rằng một lời gọi qua proxy có thể tạo đường đi gồm mã nghiệp vụ, tầng phản chiếu, một handler như advice và class được sinh động; bản trace lưu trong Throwable vẫn giúp truy ngược nguồn phát lỗi.

Ví dụ **không** tự động khẳng định rằng mọi hệ AOP đều dùng JDK proxy, Method.invoke, hay một class có tên chứa “$Proxy”. Nếu cơ chế đan bytecode vào lúc biên dịch hoặc tải lớp, sự xuất hiện và vị trí frame sẽ khác. Chỉ dùng chương trình này làm mô hình giải thích; muốn kết luận lỗi thực tế phải tái hiện bằng cơ chế AOP thực tế của ứng dụng.

## 6. Nhìn xuyên qua exception wrapper và chuỗi nguyên nhân

Khi đọc trace, hãy đi từ **lớp ngoại lệ quan sát được** về **root cause có ý nghĩa**, nhưng không bỏ qua wrapper: wrapper có thể cho biết tầng nào đã chuyển lỗi.

### 6.1. Reflection: InvocationTargetException

Khi một phương thức được gọi qua Method.invoke và phương thức đích ném exception, tầng reflection có thể báo InvocationTargetException. Trong ví dụ, catch ở handler nhận wrapper, sau đó lấy **wrapper.getCause()**. Stack trace của wrapper nói về việc reflection báo lỗi; stack trace của cause nói về nơi lỗi nghiệp vụ hình thành.

Có hai hành vi rất khác nhau:
- **throw original**: truyền tiếp cùng Throwable; vị trí trace gốc vẫn hữu ích.
- **throw new IllegalStateException("context", original)**: thêm ngữ cảnh và giữ nguyên nhân bên trong cause chain; trace ngoài bắt đầu ở tầng advice.

Lỗi thường gặp là tạo Throwable mới nhưng **không đặt cause**, dẫn đến mất đường truy vết nguyên nhân. Ngược lại, cứ ném lại cùng loại exception không phải lúc nào cũng đúng về hợp đồng API; phải giữ chính sách xử lý lỗi được yêu cầu.

### 6.2. Proxy và ngoại lệ checked không được khai báo

Với một số cơ chế proxy trên Java, nếu InvocationHandler phát ra một **checked exception** không được khai báo trong chữ ký phương thức interface, caller có thể nhận UndeclaredThrowableException. Khi đó cần đọc **cause** bên trong để tìm checked exception gốc. Đây là quy tắc liên quan đến hợp đồng ngoại lệ của JDK dynamic proxy; không áp đặt nó lên mọi hệ weaving.

### 6.3. Chuỗi cause, suppressed và phần rút gọn của trace

Khi in lỗi bằng Throwable.printStackTrace, có thể gặp:

~~~text
java.lang.IllegalStateException: higher-level failure
    at ...
Caused by: java.lang.IllegalArgumentException: invalid
    at ...
    ... 3 more
Suppressed: java.io.IOException: close failed
    at ...
~~~

- **Caused by** là nhánh nguyên nhân được liên kết bằng Throwable.getCause().
- **Suppressed** là các ngoại lệ phụ được đính vào Throwable, thường thấy khi dọn dẹp tài nguyên hoặc có lỗi phụ đồng thời với lỗi chính.
- **... N more** là cách rút gọn các frame cuối trùng với trace bao ngoài; nó không có nghĩa là n phương thức chạy thêm hay n lỗi nữa.

Để điều tra nghiêm túc, lưu **đầy đủ class, message, cause chain, suppressed chain và frame**, đồng thời giữ mối quan hệ giữa chúng. Một dòng “message” riêng lẻ hiếm khi đủ để kết luận lỗi thuộc target hay advice.

## 7. Mã sinh ra từ đâu và vì sao không có source tương ứng?

### 7.1. Proxy được sinh ở thời gian chạy

Runtime có thể tạo một class đứng giữa caller và target. Call stack có thể có tên như **jdk.proxy1.$Proxy0.run**; con số 0, tên module/package và vị trí nguồn chỉ mang tính minh họa, có thể thay đổi. Hãy dựa vào đối tượng thật và công cụ kiểm tra, không cố đoán từ đuôi số.

Trong ví dụ Java, có thể kiểm tra trực tiếp:

~~~java
boolean generatedProxy =
        java.lang.reflect.Proxy.isProxyClass(operation.getClass());
~~~

Đây là **đoạn minh họa để chèn trong main sau khi tạo operation**, không phải chương trình chạy độc lập. Hàm isProxyClass trả lời chính xác câu hỏi một Class có phải **JDK dynamic proxy class** hay không; nó không phát hiện mọi dạng proxy hoặc weaving của các công cụ khác.

### 7.2. Bytecode được weave vào target

Với weaving, công cụ có thể sửa bytecode đã biên dịch hoặc biến đổi nó trong quá trình tải lớp. Có ít nhất ba kiểu hình dáng trace khả dĩ:

1. Advice chạy qua một phương thức phụ trợ và tạo **frame riêng**.
2. Mã advice được chèn trực tiếp vào thân phương thức đích, nên stack trace chỉ hiện **frame của target** tại thời điểm lỗi.
3. Một lớp dispatch/trampoline hoặc method synthetic trung gian xuất hiện do cách compiler/weaver tổ chức code.

Không thể xác định chắc “advice không chạy” chỉ vì không thấy tên aspect ở stack trace. Phải kiểm tra bytecode, sự kiện tại ranh giới advice và cách engine chọn join point.

### 7.3. Lambda, bridge, accessor và runtime helper

Một trace Java cũng có thể chứa phương thức lambda, bridge do generics/covariant return, accessor do compiler, reflection, method-handle hoặc runtime helper. Chúng có thể xuất hiện khi **không có AOP**. Tên chứa ký hiệu đặc biệt hoặc không có file nguồn **không đủ** để quy tất cả thành aspect.

Khi không rõ frame thuộc về ai, đặt câu hỏi: “Class này được tải từ đâu, ai tạo/biến đổi nó, nó gọi tới phương thức nào, và có log/bytecode nào xác nhận?” Phân tích nhiệm vụ của frame thay vì chỉ nhìn tên.

## 8. Kỹ thuật xác minh từ stack trace đến bytecode

### Bước 1 — Giữ bản trace gốc

Chụp Throwable.printStackTrace đầy đủ, bao gồm cause và suppressed. Đừng xóa các frame “internal” trước khi tìm được điểm phát lỗi. Nếu ghi từ nhiều luồng, thêm tên luồng, định danh lời gọi logic và thời điểm. Hạn chế ghi dữ liệu nhạy cảm trong thông điệp ngoại lệ hoặc tham số.

### Bước 2 — Đánh dấu các ranh giới

Khoanh: **target throw site**, **advice bắt/chuyển đổi lỗi**, **proxy/dispatcher**, **caller**. Ghi rõ frame nào có line chính xác, frame nào không. Vẽ tuyến luồng từ caller tới target, sau đó vẽ tuyến ngoại lệ quay ngược ra các catch/finally.

### Bước 3 — Kiểm tra class và cơ chế áp dụng thực tế

Xác nhận object được caller sử dụng có phải proxy không; nếu không phải, xác định có weaving ở class đích không. Kiểm tra công cụ tạo proxy, classloader, module và phương thức được chọn. Mã gọi trực tiếp đối tượng gốc có thể khác với mã gọi qua proxy; trong cơ chế proxy cụ thể, lời gọi nội bộ trên cùng target có thể không đi qua interceptor.

### Bước 4 — So sánh có và không có advice

Chạy lại đầu vào xác định với advice bật/tắt theo từng aspect; ghi cùng định dạng trace và chuỗi sự kiện. Nếu tắt logging advice mà lỗi vẫn xảy ra, logging có thể chỉ đang quan sát lỗi từ target. Nếu lỗi biến mất khi đảo thứ tự aspect, kiểm tra phạm vi catch/proceed, chuyển đổi ngoại lệ và tác dụng phụ.

### Bước 5 — Đọc bytecode khi mã nguồn không giải thích frame

Nếu có tệp .class đã biên dịch, lệnh **javap** giúp xem bytecode và bảng số dòng:

~~~bash
javac -g AdviceStackTraceDemo.java
javap -c -l -p 'AdviceStackTraceDemo$TraceHandler'
~~~

Trong dòng javap, tên class lồng nhau được đặt trong dấu nháy đơn để ký tự **$** không bị shell mở rộng. Lệnh này đọc bytecode của class TraceHandler đã biên dịch trên đĩa, không tự động giải mã **class proxy được tạo trong bộ nhớ**.

Với JDK dynamic proxy, một số phiên bản JDK cho phép lưu các class được tạo qua tùy chọn **-Djdk.proxy.ProxyGenerator.saveGeneratedFiles=true**. Đây là công cụ chẩn đoán phụ thuộc vào implementation và có thể tạo tệp .class trong thư mục chạy; thử trong thư mục tạm rồi kiểm tra tệp sinh thực tế. Nếu bytecode đã weave trong môi trường triển khai, lấy **class sau biến đổi** hoặc bản dump do engine hỗ trợ; javap trên tệp nguồn **trước weaving** có thể không khớp mã đang chạy.

Một frame ghi Unknown Source không nhất thiết là lỗi bản đồ nguồn. Nó có thể chỉ thiếu thông tin file/line. Nếu có file lineNumberTable, so sánh số dòng trace với **đúng bản class đã triển khai**, không dựa vào tệp nguồn đã thay đổi sau build.

### Bước 6 — Xác nhận thay đổi bằng cùng một ca tái hiện

Sau khi điều chỉnh pointcut, thứ tự hoặc cơ chế exception handling, chạy lại **đúng đầu vào và điều kiện**. So sánh stack và các bất biến nghiệp vụ: có còn đúng số lần target chạy, advice chạy, retry, log, tác dụng phụ hay không? Một trace “ngắn hơn” không tự nó chứng minh bug đã được sửa.

## 9. Phân biệt những trường hợp dễ gây ngộ nhận

### 9.1. Exception được ném lại sau khi advice đã chạy

Nếu advice thực hiện finally rồi ném lại cùng Throwable, stack trace gốc vẫn có thể dừng ở target và chứa frame advice tại **thời điểm Throwable được tạo**. Điều này không phủ nhận việc finally đã chạy sau đó; trạng thái thực thi và stack snapshot là hai sự kiện khác thời điểm.

Nếu advice tạo exception mới khi rethrow, trace ngoài có thể bắt đầu từ advice. Cần đọc cause thay vì chỉ nhìn frame đầu của wrapper và kết luận target không tham gia.

### 9.2. Lỗi xảy ra trong chính advice

Nếu advice ném lỗi **trước khi proceed**, target có thể hoàn toàn chưa chạy. Nếu advice ném lỗi **sau khi proceed trả về**, target có thể đã thành công, nhưng caller nhận lỗi từ advice. Đánh dấu số lần proceed, return của target và vị trí throw. Trường hợp handler “chỉ dùng để log” vẫn có thể làm lời gọi thất bại nếu chính việc ghi log ném exception.

### 9.3. Chuyển luồng hoặc bất đồng bộ

Khi target được chạy trong một thread khác, stack trace của exception trên worker mô tả **đường gọi trong worker**, không nhất thiết chứa caller ở thread khởi tạo tác vụ. Nếu caller quan sát lỗi qua Future hoặc cấu trúc kết quả bất đồng bộ, có thể có exception wrapper và trace riêng phía caller.

Đừng nối hai stack trace thành một chuỗi đồng bộ giả. Dùng **correlation id**, thông tin quan hệ tác vụ và thời điểm lên lịch/hoàn thành để ghép lại một **luồng nguyên nhân logic**. Nếu dùng ThreadLocal để theo dõi advice, phải kiểm tra cơ chế truyền và dọn state giữa các task; không giả định tự động được truyền qua mọi thread.

### 9.4. Nhiều advice và recursion

Advice gọi một hàm helper mà chính helper lại khớp pointcut có thể tái nhập hoặc sinh recursion không mong muốn. Trace có thể lặp các nhóm frame. Kiểm tra pointcut, độ sâu lần gọi, guard tái nhập và số lần proceed. Đừng xóa bớt frame lặp trước khi biết đó là recursion thực, retry có chủ ý hay chỉ thông tin hiển thị trùng.

### 9.5. Không xuất hiện frame advice

Những lời giải thích khả dĩ gồm: join point không được chọn; caller đi vòng qua proxy; advice đã bị loại bởi điều kiện runtime; bytecode được weave theo cách không tạo frame độc lập; frame đã bị cắt bởi hệ thống ghi log; hoặc stack được chụp **sau khi advice đã kết thúc**. Kiểm tra theo bằng chứng, không tuyên bố “aspect chưa chạy” từ một trace duy nhất.

### 9.6. Stack bị cắt ngắn, lineNumber âm hoặc tên class lạ

Nguồn ghi log có thể giới hạn số frame; runtime có thể thiếu số dòng cho mã sinh; một số tối ưu hóa hoặc cơ chế JVM có thể ảnh hưởng cách stack được cung cấp. So sánh trên cùng JDK và cấu hình khi tái hiện. Đừng dựng assertion hồi quy dựa trên tên như “$Proxy0” hoặc số dòng của code generated: chúng không phải giao diện ổn định để ứng dụng phụ thuộc.

## 10. Quy trình chẩn đoán một ca thực tế từ trace

Giả sử API nghiệp vụ thất bại nhưng log chỉ lộ ra một exception ở tầng proxy. Thực hiện quy trình ngắn sau:

1. **Xác nhận lỗi thực tế:** lấy type/message của exception caller nhận; giữ cause và suppressed. Phân biệt lỗi cuối cùng với một attempt lỗi đã được phục hồi.
2. **Tìm điểm phát sinh:** từ stack trace của cause sâu nhất có ý nghĩa, tìm frame mã nghiệp vụ hoặc advice gần vị trí throw. Đọc mã tại **đúng phiên bản class**.
3. **Gắn nhãn đường gọi:** đánh dấu caller, generated dispatcher/proxy, advice, reflection, target. Dùng trace theo chiều dưới → trên để biết ai gọi ai.
4. **Tái tạo thứ tự advice:** dùng sự kiện trước/sau proceed và catch/finally; xác định advice nào bao ngoài, advice nào bao trong. Không chỉ dựa vào vị trí frame khi đã có rethrow.
5. **Thử một thay đổi:** tắt từng aspect, siết pointcut, đổi precedence nếu công cụ cho phép, hoặc thay quy tắc exception handling. Ghi cả thay đổi của return, error, số lần gọi và side effect.
6. **Xác nhận cơ chế:** nếu chỉ lỗi trong môi trường đã weave, phải tái hiện với bản đã weave. Nếu chỉ lỗi khi qua proxy, so sánh class thực sự mà caller giữ với đối tượng target.
7. **Tạo kiểm thử hồi quy:** assert hợp đồng kết quả, type/cause exception và các bất biến có ý nghĩa; tránh assert nguyên văn mọi frame có thể thay đổi giữa JDK.

**Bảng chẩn đoán ví dụ:**

| Quan sát | Giả thuyết nên thử | Phép kiểm tra |
| --- | --- | --- |
| Trace có proxy nhưng không có target | Advice ném trước proceed, hoặc target không được gọi. | Đếm proceed và target-enter. |
| Throwable bên ngoài phát sinh ở advice | Advice wrap/rethrow lỗi hoặc tự ném lỗi. | Kiểm tra cause và nơi tạo Throwable. |
| Target xuất hiện hai lần theo log sự kiện | Retry hoặc vòng lặp do advice. | Gắn attempt id và đếm continuation. |
| Frame generated không có số dòng | Mã sinh thiếu thông tin nguồn. | Xác định class runtime; kiểm tra bytecode/source mapping. |
| Trên thread worker không thấy main của caller | Có ranh giới bất đồng bộ. | Nối theo correlation id và quan hệ tác vụ. |
| Bật một aspect là tên frame thay đổi | Chuỗi dispatch hoặc bytecode thay đổi. | So sánh stack đầy đủ, precedence, cấu hình áp dụng. |

## 11. Lỗi phổ biến khi đọc stack AOP và cách tránh

- **Đổ lỗi cho frame đầu tiên có tên lạ:** wrapper/dispatcher có thể nằm trên đường đi nhưng không phải nơi lỗi hình thành. Luôn đọc root cause và điểm throw.
- **Coi thứ tự in từ trên xuống là thứ tự lời gọi:** stack trace từ throw site về caller; muốn mô tả tuyến gọi, thường cần đọc phần frame theo chiều ngược.
- **Cho rằng catch luôn xuất hiện như một frame mới:** catch có thể chạy sau khi ngăn xếp target đã unwind; ngoại lệ giữ một bản trace cũ.
- **Không đọc cause/suppressed:** che mất target gốc hoặc lỗi dọn dẹp xảy ra khi advice kết thúc.
- **Gán mọi synthetic/helper cho AOP:** compiler, reflection, lambda và runtime cũng tạo code trung gian.
- **Coi tên class proxy và số dòng là chuẩn ổn định:** tên proxy, thứ tự frame nội bộ, file/line thay đổi theo implementation và build.
- **Dùng proxy sample để khẳng định lỗi trong weaving:** mô hình chặn khác nhau có thể có tập join point và cấu trúc bytecode khác nhau.
- **Chỉ kiểm tra stack mà không đo hành vi:** thiếu số lần proceed, retry, exception transform và side effect thì khó chứng minh lỗi tương tác.
- **Gộp call stack nhiều thread thành một stack duy nhất:** quan hệ async cần correlation/causality riêng.
- **Chỉnh sửa stack trace để giấu frame trước khi phân tích:** nếu lọc cho người đọc, luôn lưu bản gốc để đối chiếu.

## 12. Bài tập tự kiểm tra

**Bài tập 1 — Đổi điểm quan sát.** Trong ví dụ, thêm lệnh in kết quả Thread.currentThread().getStackTrace() ngay trong catch. Đánh dấu khác biệt so với original.getStackTrace(). Giải thích vì sao frame của target có thể biến mất khỏi ảnh chụp hiện tại nhưng vẫn ở trace của ngoại lệ.

**Bài tập 2 — Wrap exception.** Thay dòng ném lại trong handler bằng:

~~~java
throw new IllegalStateException("advice failed", original);
~~~

Đây là **một dòng thay thế**, không phải chương trình độc lập. Chạy lại cần sửa nhánh catch ở main để bắt IllegalStateException; in cả cause. Dự đoán: ngoại lệ ngoài bắt đầu ở handler, trong khi cause vẫn chỉ về OperationImpl.run. Kiểm chứng bằng trace thật.

**Bài tập 3 — Phân biệt lỗi nghiệp vụ và lỗi advice.** Di chuyển lệnh ném lỗi từ OperationImpl.run sang TraceHandler.invoke **trước method.invoke**. Dự đoán frame target và các dòng sự kiện sẽ thay đổi như thế nào? Thêm bộ đếm target-entry và chứng minh target không chạy.

**Bài tập 4 — So sánh mechanism.** Với engine AOP bạn đang dùng, dựng cùng một target/advice nhưng thay proxy interception bằng weaving nếu engine hỗ trợ. Thu trace thực tế, đánh dấu mỗi frame theo vai trò rồi giải thích những frame thêm/mất. Không ép hai cơ chế phải có trace giống nhau.

## 13. Checklist kết thúc phân tích stack trace

- [ ] Đã xác định đây là Throwable stack trace hay call stack hiện tại, và thời điểm chụp.
- [ ] Có bản trace đầy đủ cùng exception type, message, causes và suppressed.
- [ ] Đã tìm điểm throw thật; phân biệt target, advice, dispatch/generated và caller.
- [ ] Biết join point/pointcut và cơ chế AOP dùng trong chương trình; không suy diễn từ tên class.
- [ ] Đã đối chiếu precedence, số lần proceed, catch/rethrow/wrap và side effect với trace.
- [ ] Nếu có generated frame, biết mã được tạo/biến đổi lúc nào và phiên bản class nào đang chạy.
- [ ] Với xử lý async, có correlation id hoặc dấu vết nhân quả giữa các thread/task.
- [ ] Kết luận dựa trên MRE hoặc phép thử có điều kiện xác định; kiểm thử hồi quy bảo vệ hợp đồng nghiệp vụ.

**Điểm cốt lõi:** stack trace AOP là **dấu vết của đường thực thi thực tế tại thời điểm Throwable ghi nhận trace**, có thể chứa code do runtime hoặc compiler tạo. Tên frame lạ là manh mối để lần theo ranh giới interception; bằng chứng quyết định nằm ở nơi phát sinh exception, chuỗi cause, thứ tự advice/proceed và cơ chế áp dụng AOP thực tế.
