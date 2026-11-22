# Gọi tiếp hành vi gốc qua cơ chế proceed hoặc cơ chế tương đương trong around advice

> **Mục tiêu:** Nắm được vai trò của `proceed` — hoặc một cơ chế continuation tương đương — trong **around advice** của lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP). Hiểu rõ vì sao gọi `proceed` thường là cách cho phép luồng xử lý được tiếp tục; điểm tiếp tục có thể đi qua các advice khác trước khi tới hành vi nghiệp vụ; và hậu quả khi không gọi, gọi một lần, gọi nhiều lần, truyền đối số khác, thay giá trị trả về hoặc xử lý ngoại lệ.

## 1. Vấn đề: advice bao quanh phải quyết định có tiếp tục hay không

Trong những loại advice đơn giản, thời điểm chạy thường đã được định nghĩa: chạy trước khi phần gốc bắt đầu, sau khi phần gốc hoàn tất bình thường hoặc khi nó kết thúc bằng ngoại lệ.

**Around advice** khác ở chỗ nó bao lấy một hoạt động được chọn và có thể **quyết định thời điểm, điều kiện và cách tiếp tục luồng thực thi**. Điều đó cho phép nó thực hiện các chính sách như:

- Đo thời gian và quan sát cả trước lẫn sau một lời thực thi.
- Kiểm tra điều kiện rồi cho phép hoặc từ chối thực hiện hoạt động kế tiếp.
- Ghi log trước khi gọi, sau khi trả về và khi có lỗi.
- Gói một ranh giới thực thi trong `try/finally` để dọn ngữ cảnh.
- Với **những cơ chế cho phép**, điều chỉnh đối số, trả về kết quả thay thế hoặc thực hiện lại phần tiếp tục.

Cơ chế then chốt thường được biểu diễn bằng lời gọi `proceed()`, `next()`, `continuation.invoke()`, `invocation.proceed()` hoặc một giao diện tương đương. Đây là tên **khái niệm**, không phải một cú pháp bắt buộc của mọi AOP.

Mô hình ngắn:

~~~text
Caller
  |
  v
[ Around advice: trước ]
  |
  | proceed()
  v
[ Phần thực thi tiếp theo: advice khác và/hoặc phần gốc ]
  |
  v
[ Around advice: sau ]
  |
  v
Caller
~~~

**Chìa khóa:** Trong một chuỗi có nhiều advice, `proceed` thường có nghĩa là **tiếp tục tới mắt xích kế tiếp**, không nhất thiết **gọi thẳng vào phương thức gốc ngay lập tức**.

## 2. Xác định đúng continuation trước khi gọi tiếp

**Join point** là vị trí thực thi có thể can thiệp; **pointcut** chọn tập join point; **weaving/interception** quyết định liệu advice có thực sự được nối vào đường gọi hay không. Khi **around advice** đã nhận quyền điều khiển, thao tác **`proceed` (continuation)** chuyển sang phần còn lại của chuỗi advice và cuối cùng có thể tới target. Nó không mặc nhiên gọi trực tiếp target.

Trước khi đọc một lời gọi `proceed`, hãy kiểm tra ba điều độc lập:

1. **Điểm thực thi nào được chọn?** Pointcut và cơ chế AOP có thực sự bao phủ lời gọi này không?
2. **Advice nào nằm bên trong?** Continuation có thể qua một advice khác rồi mới đến nghiệp vụ.
3. **Lớp hiện tại có gọi tiếp không, và bao nhiêu lần?** Advice bên trong có thể short-circuit, ném lỗi hoặc lặp tiếp nếu cơ chế cho phép.

Một aspect tổ chức pointcut/advice cho concern xuyên suốt; nó không thay đổi các câu hỏi trên. Trong bài này, trọng tâm là **ngữ nghĩa của lời gọi tiếp tục**. Các bài về không gọi, thay đối số, retry và xử lý ngoại lệ sẽ áp dụng cùng ranh giới này vào những hợp đồng riêng.

## 3. Cú pháp khái niệm cơ bản

Một mẫu around advice có thể được diễn đạt như sau:

~~~text
around selectedJoinPoint:
    before()
    result = proceed()
    after()
    return result
~~~

Đây là **pseudocode**, không phải chương trình Java độc lập hay một ngôn ngữ aspect cụ thể.

Ý nghĩa:

1. `before()` chạy khi advice nhận quyền điều khiển.
2. `proceed()` cho phép hoạt động tiếp theo trong chuỗi can thiệp thực thi.
3. Nếu phần tiếp theo **trả về bình thường**, biến `result` nhận kết quả.
4. `after()` chạy sau khi `proceed` trả về bình thường.
5. `return result` chuyển kết quả trở lại lớp gọi phía ngoài.

Mẫu này **chưa** ghi nhận đầy đủ nhánh lỗi: nếu `proceed()` ném ngoại lệ, lệnh `after()` nằm tiếp sau nó sẽ bị bỏ qua theo luồng điều khiển thông thường. Muốn xử lý cả hai kiểu thoát cần dùng `try/catch/finally` tương ứng.

### 3.1. Mẫu bảo toàn kết quả và ngoại lệ

~~~text
around selectedJoinPoint:
    before()
    try:
        result = proceed()
        afterSuccess(result)
        return result
    catch error:
        afterFailure(error)
        throw error
    finally:
        afterExit()
~~~

Mục đích minh họa:

- Không ngầm nuốt ngoại lệ của phần tiếp theo.
- Chỉ ghi **success** sau khi phần tiếp theo trả về bình thường.
- Chỉ ghi **failure** với ngoại lệ thực sự đi ra khỏi ranh giới đó.
- `afterExit` hướng tới cả hai đường thoát nếu có unwinding phù hợp.

Mẫu trên là **ý tưởng logic**, không khẳng định mọi công cụ hỗ trợ đúng cú pháp hoặc mọi kiểu ngoại lệ có cùng semantics. Advice `afterSuccess`, `afterFailure` hoặc `afterExit` tự phát sinh lỗi cũng có thể thay đổi kết quả cuối. Cần quy định chính sách lỗi rõ.

## 4. Proceed là một sự tiếp tục, không chỉ là lời gọi lại cùng tên phương thức

Khi có nhiều around advice, chuỗi có thể trông như sau:

~~~text
Caller
  |
  v
Around A
  |  A.proceed()
  v
Around B
  |  B.proceed()
  v
Original operation
  |
  v
Around B nhận kết quả
  |
  v
Around A nhận kết quả
  |
  v
Caller nhận kết quả
~~~

Nếu A ghi “A trước”, B ghi “B trước”, phần gốc in “business”, sau đó B in “B sau”, A in “A sau”, thứ tự dự kiến là:

~~~text
A before
B before
business
B after
A after
~~~

Trong cách lồng này:

- `A.proceed()` chuyển quyền cho **B**, chưa chắc vào nghiệp vụ ngay.
- `B.proceed()` mới đi tiếp đến **phần gốc** nếu không còn advice bao phía trong.
- Kết quả và ngoại lệ quay ngược lên các lớp bao, giống luồng call stack.
- Chính sách ordering quyết định ai là lớp ngoài/lớp trong; **không được đoán thứ tự** từ tên aspect hoặc vị trí khai báo nếu cơ chế không quy định như vậy.

Hãy tưởng tượng `proceed` như một “continuation” được trao cho advice: nó đại diện cho phần còn lại của quá trình xử lý mà advice có thể cho phép tiếp tục theo hợp đồng.

## 5. Ba tình huống cơ bản: không gọi, gọi một lần, gọi nhiều lần

### 5.1. Không gọi proceed

~~~text
around selectedJoinPoint:
    if forbidden():
        return rejection
    return proceed()
~~~

Nếu điều kiện `forbidden()` đúng và advice trả về ngay, phần tiếp tục không được thực thi **trong mô hình cho phép short-circuit như vậy**.

Hệ quả có thể là:

- Phần nghiệp vụ gốc **không được chạy** ở lượt này.
- Những advice **nằm bên trong continuation** cũng không chạy.
- Những advice **nằm bên ngoài** advice hiện tại vẫn có thể thực hiện phần xử lý sau khi nhận kết quả.
- Caller nhận giá trị thay thế nếu loại join point và hợp đồng cho phép.

Cần cực kỳ thận trọng: nếu pointcut quá rộng hoặc logic từ chối sai, advice có thể vô tình bỏ qua những thao tác nghiệp vụ quan trọng. Không phải mọi dạng join point đều cho phép trả về một giá trị tùy ý khi không proceed.

### 5.2. Gọi proceed một lần

~~~text
around selectedJoinPoint:
    before()
    result = proceed()
    after()
    return result
~~~

Đây là dạng thường gặp nhất để giữ hành vi gốc trong một chính sách quan sát: **một lần tiếp tục**, giữ nguyên giá trị trả về, không chủ ý thay đổi số lần thực thi phần gốc.

Tuy nhiên, một lần gọi `proceed` ở lớp ngoài **không bảo đảm** phần gốc chạy đúng một lần: một advice lớp trong có thể bỏ qua, tự ném lỗi hoặc, nếu cơ chế cho phép, tiếp tục nhiều lần. Chỉ khi xác minh toàn chuỗi mới có thể kết luận số lần chạy nghiệp vụ.

### 5.3. Gọi proceed nhiều lần

~~~text
around selectedJoinPoint:
    first = proceed()
    second = proceed()
    return second
~~~

Đây là **pseudocode nêu ý tưởng**, không phải cú pháp hoặc hành vi được bảo đảm cho mọi AOP. Một số cơ chế quanh join point hỗ trợ tiếp tục nhiều lần; một số chỉ cho phép một lần, hoặc có giới hạn nghiêm ngặt tùy loại điểm.

Nếu mỗi `proceed` khởi động lại phần còn lại của chuỗi thì phần gốc **có thể chạy nhiều lần**: hai lần ghi dữ liệu, hai lần gửi yêu cầu, hai lần trừ tiền hoặc hai lần phát sự kiện. Retry chỉ hợp lý khi thao tác **idempotent** hoặc có bảo đảm chống trùng phù hợp. Không được xem multiple proceed là cách retry an toàn mặc định.

## 6. Java 17: tự xây chuỗi around/continuation bằng Java thuần

Đoạn sau là một **mô hình giáo dục chạy được**. Ta định nghĩa:

- `Invocation`: một đơn vị tiếp tục thực thi.
- `Around`: một mắt xích nhận continuation tới phần còn lại.
- `run(...)`: xây dựng chuỗi bằng cách cho advice hiện tại gọi mắt xích kế tiếp; khi hết advice, gọi hàm nghiệp vụ.
- `trace`: một around advice quan sát trước, sau thành công, ngoại lệ và finally.
- `audit`: một around advice bên trong.
- `block`: một around advice trả về thay thế và không gọi tiếp.

**Chương trình không tự weaving vào Java bytecode và không phải cú pháp của bất kỳ thư viện AOP cụ thể nào.** Nó minh họa chính xác mô hình `proceed/next` bằng các hàm Java 17.

Lưu file **`ProceedChainDemo.java`**:

~~~java
import java.util.List;

public class ProceedChainDemo {
    @FunctionalInterface
    interface Invocation {
        String proceed() throws Exception;
    }

    @FunctionalInterface
    interface Around {
        String invoke(Invocation next) throws Exception;
    }

    static String run(List<Around> chain, int index, Invocation original)
            throws Exception {
        if (index == chain.size()) {
            return original.proceed();
        }
        Around current = chain.get(index);
        return current.invoke(() -> run(chain, index + 1, original));
    }

    public static void main(String[] args) throws Exception {
        Around trace = next -> {
            System.out.println("trace before");
            try {
                String result = next.proceed();
                System.out.println("trace success " + result);
                return result;
            } catch (Exception error) {
                System.out.println("trace error " + error.getMessage());
                throw error;
            } finally {
                System.out.println("trace finally");
            }
        };

        Around audit = next -> {
            System.out.println("audit before");
            String result = next.proceed();
            System.out.println("audit after");
            return result;
        };

        Invocation success = () -> {
            System.out.println("business success");
            return "OK";
        };

        String value = run(List.of(trace, audit), 0, success);
        System.out.println("caller result " + value);

        Invocation failure = () -> {
            System.out.println("business failure");
            throw new IllegalStateException("boom");
        };

        try {
            run(List.of(trace, audit), 0, failure);
        } catch (IllegalStateException error) {
            System.out.println("caller caught " + error.getMessage());
        }

        Around block = next -> {
            System.out.println("blocked");
            return "DENIED";
        };

        String denied = run(List.of(trace, block, audit), 0, success);
        System.out.println("caller result " + denied);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ProceedChainDemo.java
java ProceedChainDemo
~~~

**Stdout chính xác:**

~~~text
trace before
audit before
business success
audit after
trace success OK
trace finally
caller result OK
trace before
audit before
business failure
trace error boom
trace finally
caller caught boom
trace before
blocked
trace success DENIED
trace finally
caller result DENIED
~~~

### 6.1. Đọc lần thành công

Chuỗi `[trace, audit]` được truyền vào `run`.

1. `trace` in `trace before`.
2. `trace` gọi `next.proceed()`, nên quyền điều khiển chuyển đến `audit`.
3. `audit` in `audit before`, rồi gọi tiếp.
4. Vì không còn advice khác, `run` gọi `original.proceed()`.
5. Nghiệp vụ in `business success` rồi trả `"OK"`.
6. `audit` nhận kết quả, in `audit after`, trả nguyên giá trị.
7. `trace` nhận `"OK"`, in `trace success OK`, sau đó `finally` in `trace finally`.
8. Caller nhận và in `caller result OK`.

Dòng `audit after` đứng trước `trace success OK` vì **audit ở trong trace**.

### 6.2. Đọc lần thất bại

`failure` ném `IllegalStateException("boom")`. Advice `audit` không có catch/finally, vì thế dòng `audit after` **không xuất hiện**. Ngoại lệ tiếp tục lên `trace`, `trace` ghi lỗi, ném lại, rồi chạy `finally`. Caller bắt đúng loại ngoại lệ và in `caller caught boom`.

Từ đó rút ra:

- `proceed()` có thể **trả về** hoặc **ném ngoại lệ**.
- Đoạn lệnh nằm **sau** `proceed` chỉ chạy khi có đường đi tới nó.
- `finally` hữu ích để xử lý việc rời phạm vi cả bình thường và ngoại lệ.
- Nếu advice tự ném ngoại lệ mới, lỗi gốc có thể bị thay thế; ví dụ trên không làm như vậy.

### 6.3. Đọc trường hợp block

Chuỗi cuối `[trace, block, audit]`.

- `trace` bắt đầu và gọi `next.proceed()`.
- `block` in `blocked` và trả `"DENIED"` **mà không gọi next**.
- Vì thế `audit` và `success` **không chạy**.
- `trace` phía ngoài vẫn nhận một giá trị trả về bình thường `"DENIED"`, in `trace success DENIED` rồi `trace finally`.

Điểm tinh tế: **“trace success” trong chương trình chỉ có nghĩa continuation trả về bình thường**, không có nghĩa hành vi nghiệp vụ gốc đã chạy hoặc giao dịch nghiệp vụ thành công. Đây là lý do hệ thống quan sát phải phân biệt normal return, short-circuit, trạng thái nghiệp vụ và kết quả thực hiện phần gốc.

## 7. Không gọi proceed không đồng nghĩa dừng toàn bộ thế giới

Một around advice bỏ qua `proceed` chỉ ảnh hưởng tới **continuation nằm bên trong nó** theo mô hình kết hợp của hệ AOP.

Những hành vi sau **có thể vẫn xảy ra**:

- Advice bao ngoài nhận kết quả, xử lý hoặc ghi log.
- Các hoạt động đã được thực hiện trước khi vào advice hiện tại.
- Các tác vụ bất đồng bộ đã được gửi đi từ nơi khác.
- Mã phía caller sau khi nhận giá trị thay thế.
- Những join point khác không thuộc chuỗi này.

Do đó, một điểm bị short-circuit không phải là lệnh “hủy toàn bộ request” trừ khi kết quả và hợp đồng của phần ứng dụng thực sự có nghĩa như vậy.

Nếu dùng short-circuit cho kiểm soát quyền, phải cân nhắc bảo đảm an toàn ở **mọi đường vào** và mọi cơ chế dispatch. Một pointcut có thể bỏ sót join point hoặc một lời gọi đi ngoài weaving, nên không được xem chỉ một advice là bằng chứng đủ cho một chính sách an ninh bắt buộc.

## 8. Khi gọi proceed nhiều lần: demonstration và rủi ro

Để hình dung sự khác biệt giữa một lần và hai lần tiếp tục, dùng chương trình Java 17 thứ hai. Chương trình **tự định nghĩa** continuation có thể gọi nhiều lần; nó không khẳng định rằng tất cả công cụ AOP thực tế đều cho phép làm vậy.

Lưu file **`RepeatProceedDemo.java`**:

~~~java
public class RepeatProceedDemo {
    @FunctionalInterface
    interface Invocation {
        String proceed();
    }

    @FunctionalInterface
    interface Around {
        String invoke(Invocation continuation);
    }

    static String apply(Around advice, Invocation original) {
        return advice.invoke(original);
    }

    public static void main(String[] args) {
        int[] calls = {0};

        Invocation operation = () -> {
            int count = ++calls[0];
            System.out.println("business invocation " + count);
            return "value-" + count;
        };

        Around twice = next -> {
            String first = next.proceed();
            System.out.println("first=" + first);
            String second = next.proceed();
            System.out.println("second=" + second);
            return second;
        };

        String result = apply(twice, operation);
        System.out.println("caller=" + result);
        System.out.println("count=" + calls[0]);
    }
}
~~~

Chạy:

~~~bash
javac RepeatProceedDemo.java
java RepeatProceedDemo
~~~

**Stdout chính xác:**

~~~text
business invocation 1
first=value-1
business invocation 2
second=value-2
caller=value-2
count=2
~~~

Ở mô hình do chương trình này định nghĩa, mỗi lần `next.proceed()` thực thi lại lambda `operation`. Do đó số lần chạy nghiệp vụ bằng **2** dù caller chỉ gọi `apply(...)` một lần.

**Không áp dụng suy luận này một cách máy móc cho mọi advice runtime.** Một số hệ AOP giới hạn số lần gọi tiếp, có semantics riêng cho constructor và field access, hoặc dùng trạng thái invocation không thể phát lại an toàn. Muốn retry thật, phải nghiên cứu hợp đồng của continuation và tính idempotent của phần nghiệp vụ.

### 8.1. Repeat có thể lặp cả những advice phía trong

Nếu continuation bao gồm chuỗi `[audit, business]`, việc gọi nó nhiều lần có thể chạy **cả audit lẫn business nhiều lần**. Tại một ranh giới có nhiều aspect, điều này khiến số bản ghi, số lần đo và số lần nghiệp vụ khác dự đoán ban đầu.

Không chỉ đếm `proceed` của advice ngoài; hãy xét **cây lời gọi continuation hoàn chỉnh**.

## 9. Proceed và nguyên tắc bảo toàn hợp đồng phương thức

Một around advice dùng cho hoạt động trả kết quả nên cân nhắc những thuộc tính sau:

### 9.1. Giá trị trả về

Nếu phần gốc trả một `Order`, advice chỉ làm logging thường nên **trả đúng `Order` đó**. Trả `null`, giá trị kiểu khác hoặc một đối tượng thay thế có thể vi phạm API hoặc tạo lỗi ở caller.

Trong mô hình có cho phép biến đổi kết quả, việc biến đổi phải có **chủ đích và hợp đồng rõ**, không phải tác dụng phụ vô tình.

### 9.2. Ngoại lệ

Nếu `proceed` ném một ngoại lệ, advice quan sát thông thường nên ghi nhận rồi **ném lại ngoại lệ phù hợp**. Nuốt lỗi có thể biến một tác vụ thất bại thành bình thường giả; bọc ngoại lệ tùy tiện có thể phá hợp đồng mà caller phụ thuộc.

Nếu mục đích là chuyển lỗi sang dạng kết quả có kiểm soát, hãy thiết kế đây như một **chính sách lỗi** rõ ràng, có kiểm thử với các loại ngoại lệ được cho phép.

### 9.3. Số lần gọi

Một advice đo thời gian bình thường nên tránh gọi `proceed` hai lần. Nếu có retry, phải xét quyền tái thực thi, tác dụng phụ, transaction, timeout và khả năng trùng dữ liệu.

### 9.4. Đối số

Nếu cơ chế cho phép gọi continuation với đối số mới, advice cần bảo toàn kiểu, thứ tự, số lượng và bất biến. Không tự cho rằng mọi loại join point đều cho sửa đối số, hay cú pháp `proceed(newArgs)` hoạt động giống nhau trong mọi công cụ.

### 9.5. Ngữ cảnh của đối tượng và luồng

Đối tượng đích, receiver, caller và ngữ cảnh thread có thể là những thông tin khác nhau. Khi thay điều kiện hoặc đẩy `proceed` sang thread khác, ngữ nghĩa của advice và quan hệ ngữ cảnh có thể đổi. Nếu công cụ không tài liệu hóa việc tiếp tục bất đồng bộ, không được dùng nó như một mặc định.

## 10. Proceed với tham số thay đổi

Một số mô hình AOP cho phép around advice **cung cấp lại đối số** khi tiếp tục. Một số chỉ hỗ trợ tiếp tục với đối số gốc hoặc có quy tắc ràng buộc riêng.

Mô tả ý tưởng:

~~~text
around selectedCall(originalArguments):
    checked = normalizeAndValidate(originalArguments)
    return proceed(checked)
~~~

Đây là **pseudocode**, không phải cú pháp thống nhất. Những câu hỏi cần làm rõ:

- Có được đổi **giá trị** đối số không?
- Có được đổi **số lượng**, **kiểu**, hoặc **đối tượng đích** không?
- Đối số mới được dùng tại **điểm nào**: call site, execution hay một continuation bao nhiều advice?
- Nếu có advice khác phía trong, nó quan sát **đối số gốc** hay **đối số đã được thay**?
- Việc thay đổi có ảnh hưởng tới kiểm tra pointcut động và điều kiện chọn của những advice tiếp theo không?

Không nên chuẩn hóa/biến đổi dữ liệu bí mật ở một advice “đăng ký vào mọi phương thức” mà không có hợp đồng nghiệp vụ. Sai kiểu hoặc sai ngữ nghĩa có thể tạo lỗi tinh vi.

### 10.1. Phân biệt dữ liệu đọc được với quyền thay đổi dữ liệu

Một mô hình có khả năng **đọc** đối số tại join point không đồng nghĩa có quyền **thay** đối số khi proceed. Hai khả năng phải được kiểm tra riêng trong tài liệu công cụ.

## 11. Advice bao quanh và exception flow

Xét mô hình:

~~~text
around:
    before()
    result = proceed()
    after()
    return result
~~~

Nếu `proceed` ném ngoại lệ, lệnh `after()` bị bỏ qua. Để quan sát lỗi:

~~~text
around:
    before()
    try:
        result = proceed()
        afterSuccess(result)
        return result
    catch error:
        recordFailure(error)
        throw error
    finally:
        restoreContext()
~~~

**Không tự hứa rằng `finally` được gọi trong mọi tai biến tuyệt đối:** nếu tiến trình bị kết thúc cưỡng bức, có lỗi khiến VM không thể unwinding hoặc một hoạt động không bao giờ trả về/throw, không có bảo đảm đó.

### 11.1. Ngoại lệ phát sinh trong advice

Nếu `afterSuccess()` tự ném lỗi, caller có thể nhận lỗi từ advice thay vì kết quả nghiệp vụ bình thường. Nếu `restoreContext()` trong `finally` tự ném lỗi, nó có thể che ngoại lệ gốc đang lan truyền.

Đối với logging/metrics best-effort, cần chính sách xử lý lỗi để việc quan sát không tùy tiện phá nghiệp vụ. Với những tác vụ cleanup bắt buộc cho tính đúng đắn, không nên đơn giản nuốt mọi lỗi; cần một hợp đồng rõ về ngoại lệ chính và thông tin lỗi phụ.

### 11.2. Trả về trong finally là một anti-pattern

Trong Java, `return` hoặc `throw` xuất phát từ `finally` có thể thay đổi kết quả đang chờ. Mô hình around advice có xử lý cleanup nên tránh trả về giá trị mới bên trong phần dọn dẹp trừ khi có chính sách chuyển đổi kết quả rất rõ.

## 12. Advice chaining: ai gọi ai, và thứ tự ra/vào?

Giả sử có ba around advice:

- **A** đặt ngữ cảnh trace.
- **B** kiểm tra chính sách truy cập.
- **C** đo thời gian.
- **Original** chạy nghiệp vụ.

Một thứ tự lồng có thể là:

~~~text
A.before
  B.before
    C.before
      Original
    C.after
  B.after
A.after
~~~

Nhưng với một chính sách “từ chối nếu không có quyền”, nếu **B không gọi proceed**:

~~~text
A.before
  B.before
  B.denied
A.after
~~~

Khi đó **C không được chạy**, Original không được chạy, nhưng A vẫn có cơ hội xử lý phần kết thúc nếu A đã chuyển quyền vào B và B trả về bình thường.

### 12.1. Tầm quan trọng của thứ tự

Nếu yêu cầu là “mọi lời từ chối cũng phải được đo thời gian”, phải chọn ranh giới metrics phù hợp — đặt nó ngoài advice có khả năng chặn, hoặc chọn một điểm quan sát khác. Nếu metrics nằm bên trong nhánh bị bỏ qua thì nó không có dữ liệu cho lời từ chối.

Nếu yêu cầu là “mọi yêu cầu bị từ chối đều phải có audit”, không thể đặt audit tùy tiện phía trong advice chặn mà vẫn kỳ vọng mọi trường hợp đều xuất hiện audit.

**Pointcut xác định tập điểm ứng viên**, còn **ordering** quyết định cấu trúc lồng và tính bao phủ thực tế của từng advice trong một chuỗi.

## 13. Không proceed và return thay thế: quyền lực đi cùng ràng buộc

Một around advice có thể short-circuit trong một số mô hình. Nhưng việc thay thế hành vi chỉ an toàn khi ý nghĩa được xác định:

- Với **method trả boolean**, `false` có phải từ chối hợp lệ không?
- Với **method trả object**, `null` có thuộc hợp đồng không?
- Với **method trả void**, short-circuit có nghĩa không làm nghiệp vụ; caller có được thông báo không?
- Với **constructor execution**, có thể bỏ phần khởi tạo hay thay đối tượng không? Điều này phụ thuộc cơ chế và các ràng buộc của runtime; không được giả định như một method thông thường.
- Với **field get/set**, giá trị và tác dụng phụ có thể chịu quy tắc đặc biệt của mô hình.

Nếu một điểm không cho thay kết quả hoặc không cho bỏ qua hoạt động gốc, một đoạn mô phỏng Java dùng lambda không làm cho thao tác đó hợp lệ trong hệ AOP thật.

### 13.1. Kết quả giả có thể gây hiểu sai

Giả sử advice không gọi tiếp và trả một `PaymentResult.success()` giả trong khi không thực hiện thanh toán. Caller có thể tin rằng tiền đã được chuyển. Vì vậy, short-circuit thường phải trả một kết quả phản ánh **đúng việc không thực hiện nghiệp vụ**, hoặc ném một lỗi từ chối có hợp đồng, tùy thiết kế.

Trong hệ thống có tác vụ gây tác dụng phụ, lựa chọn short-circuit phải được thử ở cả nhánh đồng ý và nhánh từ chối.

## 14. Gọi proceed nhiều lần với retry: điều kiện để có thể làm an toàn

Retry quanh một join point là một ứng dụng nâng cao thường được nhắc tới. Tuy nhiên:

1. **Công cụ có cho multiple proceed không?** Một số continuation chỉ one-shot.
2. **Join point nào được retry?** Method execution, method call hay toàn bộ chuỗi bên trong?
3. **Có tác dụng phụ trước khi lỗi không?** Gửi email, ghi DB, phát message có thể đã xảy ra một phần.
4. **Hành vi gốc có idempotent không?** Thực thi lại nhiều lần cho cùng đầu vào có an toàn không?
5. **Có giới hạn số lần và timeout không?** Tránh retry vô hạn.
6. **Có backoff và phân loại lỗi không?** Không nên retry lỗi dữ liệu không hợp lệ như lỗi mạng tạm thời.
7. **Có tác động lên transaction, lock và context không?** Một lần retry có thể cần phạm vi giao dịch mới.
8. **Các advice bên trong có chạy lại không?** Có thể tạo log/audit nhiều lần.

Một đoạn pseudocode có kiểm soát:

~~~text
around retryableOperation:
    attempts = 0
    while attempts < maxAttempts:
        attempts = attempts + 1
        try:
            return proceed()
        catch retryableError:
            if attempts == maxAttempts:
                throw retryableError
            waitBeforeNextAttempt()
~~~

Pseudocode này chỉ có nghĩa nếu cơ chế cho phép continuation lặp lại và hợp đồng nghiệp vụ đáp ứng các điều kiện trên. Không nên xem nó như công thức copy-paste cho mọi hoạt động.

## 15. Proceed trong vòng bao đo thời gian và dọn ngữ cảnh

Một cách sử dụng phổ biến:

~~~text
around selectedOperation:
    saved = captureContext()
    start = monotonicClock()
    try:
        installContext()
        return proceed()
    finally:
        elapsed = monotonicClock() - start
        recordElapsed(elapsed)
        restore(saved)
~~~

Mục đích:

- Tạo thời điểm bắt đầu ở đúng ranh giới bao.
- Cho phép phần trong thực thi với ngữ cảnh cần thiết.
- Dù phần trong trả về hoặc ném lỗi, kết thúc phép đo và phục hồi ngữ cảnh.
- Trả nguyên kết quả hoặc để ngoại lệ lan truyền nếu phần cleanup không tự phá luồng.

Với Java, `System.nanoTime()` thích hợp để tính **khoảng thời gian**, không dùng trực tiếp để biểu diễn thời điểm lịch.

### 15.1. Đừng dùng biến toàn cục cho mỗi lời gọi

Nếu hai thread thực thi cùng method, dùng một biến tĩnh `startTime` có thể làm thời lượng lẫn nhau. Với lời gọi lồng nhau, một `ThreadLocal` duy nhất mà không có cơ chế stack cũng có thể bị ghi đè.

Tùy công cụ, context của một lần invocation có thể được cung cấp riêng. Nếu tự triển khai wrapper, có thể dùng biến cục bộ của lambda/closure hoặc cấu trúc lưu-phục hồi đúng scope.

### 15.2. Cleanup không đồng nghĩa close mọi tài nguyên nghiệp vụ

Aspect chỉ nên thu dọn những gì **nó sở hữu**. Ví dụ, một method `openStream()` trả một stream để caller dùng tiếp; một around advice không nên đóng stream đó ngay khi method trả, trừ khi hợp đồng API đã quy định như vậy.

Điểm kết thúc của **lời gọi method** và điểm kết thúc **vòng đời tài nguyên** có thể khác nhau.

## 16. Proceed và giá trị trả về: đồng bộ so với bất đồng bộ

Với một method đồng bộ:

~~~java
String result = service.calculate();
~~~

`proceed` thường tiếp tục cho tới khi phần tiếp theo trả về `String` hoặc ném lỗi, theo semantics công cụ.

Với một method bất đồng bộ:

~~~java
CompletionStage<String> pending = service.calculateAsync();
~~~

Hai dòng trên là **mảnh Java minh họa**, không phải chương trình hoàn chỉnh. Nếu phần gốc trả một `CompletionStage`, việc `proceed` trả về **đối tượng đại diện** không đồng nghĩa tác vụ đã hoàn thành. Around advice sau `proceed` có thể chạy trước khi trạng thái cuối của tác vụ được xác định.

Cần phân biệt:

~~~text
T0: vào around
T1: proceed() trả một handle / future
T2: around trả handle cho caller
T3: công việc async mới hoàn thành hoặc thất bại
~~~

Một chính sách cần đo tới **T3** phải có ranh giới quan sát hoàn tất thích hợp, ví dụ một callback an toàn hoặc điểm hoàn tất khác theo kiến trúc. Không tự suy rằng `proceed` chờ mọi tác vụ async.

## 17. Proceed không phải công cụ thay thế kiểm soát giao dịch

Một method có thể thực hiện nhiều thao tác trước khi lỗi:

~~~text
1. Ghi bản ghi A
2. Gửi thông điệp B
3. Ném ngoại lệ
~~~

Nếu around advice bắt lỗi và gọi `proceed` lần nữa, bước 1 hoặc 2 có thể bị lặp. Retry không tự rollback những tác dụng phụ đã xảy ra.

Khi cần tính nguyên tử hoặc nhất quán, phải thiết kế transaction, idempotency key, outbox hoặc cơ chế bù trừ phù hợp **bên trong hợp đồng nghiệp vụ và hạ tầng**. AOP có thể tổ chức điểm can thiệp nhưng không tạo ra giao dịch nguyên tử chỉ bằng tên `proceed`.

Tương tự, nếu around advice chặn không cho thực thi mà caller không biết, dữ liệu nghiệp vụ có thể bị “thành công giả”. Đây là quyết định kiến trúc, không phải chỉ là vấn đề cú pháp.

## 18. Phân biệt proceed với gọi trực tiếp phương thức gốc bằng reflection

Một mô hình can thiệp có thể cung cấp đối tượng đại diện cho lời gọi gốc. Nhưng hai thao tác sau **không mặc nhiên tương đương**:

~~~text
proceed()
~~~

và:

~~~text
reflectivelyInvoke(targetMethod, target, originalArgs)
~~~

Vì:

- `proceed` có thể đi qua **các advice kế tiếp** trong chuỗi.
- Reflection trực tiếp có thể **bỏ qua** một số advice hoặc đi qua một đường gọi khác.
- Reflection có quy tắc access, boxing, varargs và exception wrapping riêng.
- Nếu gọi vào một proxy không đúng cách, một lệnh reflection có thể gây can thiệp lặp hoặc recursion.
- Các cơ chế weaving ở method call/execution có thể khác cách tiếp tục bằng lời gọi reflection.

Trong ví dụ Java 17 ở phần 6, `next.proceed()` là continuation do mô hình dựng lên. Không nên sửa nó thành việc tự gọi lại method bằng tên mà cho rằng vẫn giữ nguyên thứ tự advice.

### 18.1. Nguy cơ đệ quy vô hạn

Nếu advice trên `placeOrder` gọi lại **chính `placeOrder` qua cùng đường can thiệp** thay vì gọi continuation hợp lệ, lời gọi có thể kích hoạt cùng advice lần nữa:

~~~text
advice → call intercepted method → advice → call intercepted method → ...
~~~

Điều đó dễ dẫn tới stack overflow hoặc các tác dụng phụ lặp không mong muốn. Cách đúng là sử dụng cơ chế continuation của framework AOP đang dùng, đúng hợp đồng, thay vì tự mô phỏng bằng cách gọi lại tên method.

## 19. Pointcut động và tiến trình proceed

Một pointcut có thể bao gồm điều kiện ngữ cảnh: chỉ nhận lời gọi khi tier = `"VIP"`. Trong một số mô hình, điểm được chọn trước khi around advice nhận quyền điều khiển; sau đó advice tiếp tục theo semantics của công cụ.

Nếu advice được phép thay đổi đối số ở `proceed`, cần kiểm tra:

- Điều kiện pointcut phía ngoài được đánh giá **trước** hay **sau** phép thay?
- Các pointcut của advice phía trong có nhìn thấy giá trị đã thay không?
- Có cơ chế dùng binding của đối số gốc hay không?
- Có thể tái đánh giá điều kiện động cho mỗi lần multiple proceed không?

Không có đáp án chung cho mọi mô hình AOP. **Điều kiện lựa chọn điểm** và **điều kiện của lần tiếp tục** cần được phân biệt về thời điểm và dữ liệu.

## 20. Các lỗi phổ biến với proceed

### 20.1. Quên gọi proceed

Một advice chỉ ghi “before” rồi trả về có thể bỏ qua hành vi nghiệp vụ. Nếu mục tiêu chỉ là đo thời gian, đây thường là lỗi nghiêm trọng.

**Khắc phục:** trong trường hợp quan sát thuần, tổ chức `try/finally` và gọi continuation đúng một lần, trừ khi có lý do được tài liệu hóa.

### 20.2. Không trả về kết quả từ proceed

Một method có kết quả nhưng advice dùng `proceed()` rồi trả `null` có thể phá hợp đồng hoặc làm caller lỗi.

**Khắc phục:** bảo toàn đúng giá trị trả về hoặc định nghĩa chính sách biến đổi có chủ đích.

### 20.3. Nuốt ngoại lệ

Advice `catch` mọi lỗi và trả một giá trị “thành công” giả khiến caller không biết hoạt động đã thất bại.

**Khắc phục:** xác định rõ lỗi nào được chuyển đổi, lỗi nào phải ném lại; kiểm thử cả nhánh throw.

### 20.4. Gọi proceed hai lần ngoài ý muốn

Ví dụ một advice gọi `proceed` để “lấy dữ liệu”, sau đó gọi lại để “thực thi thật”. Nếu continuation tái chạy phần trong, nghiệp vụ đã bị nhân đôi.

**Khắc phục:** nhớ rằng `proceed` **thực thi**, không phải lời gọi truy vấn metadata.

### 20.5. Cho rằng một proceed đảm bảo một business execution

Advice phía trong có thể short-circuit hoặc tự retry. Vì vậy một `proceed` ở lớp ngoài không bảo đảm phần gốc được gọi đúng một lần.

**Khắc phục:** kiểm thử sự kết hợp toàn chuỗi và số lần thực thi phần gốc.

### 20.6. Đặt advice quan sát ở phía trong advice chặn

Nếu advice authorization bên ngoài short-circuit, metrics/audit phía trong không chạy. Đó có thể là lỗi phạm vi đo.

**Khắc phục:** xác định sự kiện cần quan sát (đã yêu cầu, đã được cho phép, đã thực thi hay hoàn tất) rồi đặt ranh giới phù hợp.

### 20.7. Tin rằng mọi join point đều có cùng quyền thay thế

Một số hệ AOP cho phép around method execution nhưng không around constructor hoặc loại điểm đặc biệt. Một số cho phép sửa đối số, số khác thì không.

**Khắc phục:** xác minh loại join point và semantics proceed cụ thể; không suy từ demo lambda.

### 20.8. Bỏ qua chi phí

Advice chạy ở điểm tần suất cao có thể làm chi phí tăng do logging, kiểm tra điều kiện, phân bổ đối tượng hay retry.

**Khắc phục:** thiết kế pointcut chặt, đo chi phí trong điều kiện thật và không thêm tác vụ chậm vào đường nóng nếu không cần.

## 21. Viết kiểm thử cho around advice có proceed

Một bộ kiểm thử đáng tin cần tách **hành vi lựa chọn** và **hành vi tiếp tục**:

| Tình huống | Kết quả cần kiểm tra |
|---|---|
| Pointcut không chọn | Advice không chạy; nghiệp vụ vẫn theo đường bình thường |
| Around quan sát, phần gốc trả bình thường | Proceed chạy đúng theo thiết kế; kết quả trả về nguyên vẹn |
| Phần gốc ném ngoại lệ | Advice xử lý theo hợp đồng; caller nhận đúng lỗi hoặc chuyển đổi có chủ đích |
| Short-circuit | Phần gốc không chạy; kết quả từ chối đúng hợp đồng |
| Nhiều around lồng nhau | Thứ tự before và after đúng với thứ tự chain |
| Advice phía trong short-circuit | Advice phía ngoài vẫn có thể thấy normal return; phần trong sau điểm chặn không chạy |
| Multiple proceed (nếu hỗ trợ) | Số lần phần gốc chạy và tác dụng phụ đúng như yêu cầu |
| Điều kiện động / ngoại lệ loại trừ | Advice chỉ kích hoạt cho đúng tập điểm |
| Đường gọi ngoài weaving | Không suy ra độ bao phủ sai khi lời gọi bỏ qua cơ chế can thiệp |
| Lời gọi đồng thời/lồng nhau | Trạng thái thời gian/ngữ cảnh tách riêng theo invocation |

### 21.1. Đo số lần thực thi phần gốc

Một test nên tăng một bộ đếm **ngay trong nghiệp vụ**, không chỉ đếm số dòng log advice. Nhờ vậy có thể phát hiện tình huống around chạy nhưng phần gốc bị bỏ qua hoặc bị gọi nhiều lần.

### 21.2. Kiểm thử ngoại lệ từ chính advice

Không chỉ kiểm tra khi nghiệp vụ ném lỗi. Cần xét trường hợp logger, serializer, cleanup hoặc advice phía trong ném lỗi để xem exception nào cuối cùng tới caller và có bị che mất lỗi gốc không.

### 21.3. Kiểm tra giới hạn runtime

Nếu công cụ chỉ chặn qua proxy, phải thử cả lời gọi qua proxy và lời gọi trực tiếp đến target. Nếu công cụ weaving mã, phải xác minh phạm vi class/call site được xử lý. Pointcut đúng về logic không đủ chứng minh mọi đường đi đều nhận advice.

## 22. Quy trình thiết kế around advice chuẩn xác

1. **Định nghĩa mục tiêu:** chỉ quan sát hay có chủ đích chặn/thay đổi/retry?
2. **Chọn join point:** method call, method execution, constructor hay loại khác? Công cụ có hỗ trợ quanh điểm đó không?
3. **Định nghĩa pointcut:** những điểm nào được chọn, có ngoại lệ hoặc điều kiện động không?
4. **Mô tả continuation:** `proceed` chuyển đến đâu; chuỗi có những advice nào và thứ tự nào?
5. **Xác định số lần tiếp tục:** một, không hoặc nhiều; nếu nhiều, cơ chế có cho phép và nghiệp vụ có an toàn?
6. **Định nghĩa return/throw contract:** kết quả và ngoại lệ có được bảo toàn không?
7. **Xác định ngữ cảnh:** đối số/receiver/caller có thể được đọc/thay đổi thế nào?
8. **Thiết kế cleanup:** dùng `finally` đúng phạm vi và tránh che lỗi gốc.
9. **Xem xét async:** proceed trả handle hay đợi công việc hoàn tất?
10. **Đo hiệu năng:** tránh những phép ghi log/đọc trạng thái đắt ở mọi join point.
11. **Lập ca kiểm thử:** success, throw, short-circuit, nested advice, duplicate invocation, đường ngoài weaving.
12. **Tài liệu hóa semantics triển khai:** không giả định các tên API giống nhau luôn có cùng hợp đồng.

## 23. Bài tập vận dụng

### Bài 1: Đọc thứ tự

Cho chuỗi `A → B → business`. Cả A và B đều in “before”, gọi `proceed`, sau đó in “after”. Thứ tự in là gì?

**Đáp án:**

~~~text
A before
B before
business
B after
A after
~~~

### Bài 2: Advice B không gọi tiếp

Vẫn chuỗi đó, nhưng B trả `"DENIED"` mà không proceed. A vẫn gọi `proceed` để chuyển vào B. Business có chạy không?

**Đáp án:** không. A có thể nhận `"DENIED"` rồi chạy đoạn sau `proceed` của A. Đây là short-circuit ở B, không phải toàn bộ chương trình dừng.

### Bài 3: Một proceed có chắc nghiệp vụ chạy?

Một advice A gọi `proceed` một lần. B ở phía trong có khả năng retry hoặc chặn. Có chắc nghiệp vụ chạy đúng một lần không?

**Đáp án:** không. A chỉ cam kết chuyển quyền vào continuation một lần. B có thể làm thay đổi số lần thực thi phần sâu hơn nếu mô hình cho phép.

### Bài 4: Ngoại lệ

Advice có cấu trúc:

~~~text
before()
result = proceed()
after()
return result
~~~

Nếu `proceed` ném ngoại lệ, `after()` có được gọi không?

**Đáp án:** không trên đường đi thông thường. Muốn ghi nhận rời phạm vi bất kể lỗi hay thành công, cần `finally` hoặc cơ chế after/finally tương ứng.

### Bài 5: Retry

Một around advice gọi `proceed()` hai lần khi lần đầu thất bại. Phần gốc trừ tiền trước khi ném ngoại lệ. Đây có an toàn không?

**Đáp án:** không thể kết luận là an toàn. Việc trừ tiền có thể đã xảy ra; lần hai có thể trừ tiếp. Cần idempotency, ranh giới transaction, chính sách retry và xác minh cơ chế cho phép multiple proceed.

### Bài 6: Ghi thời gian bất đồng bộ

`proceed()` trả một `CompletionStage` chưa hoàn tất, và advice ghi thời lượng ngay sau đó. Thời lượng ấy đo điều gì?

**Đáp án:** thời gian tới khi phương thức trả đối tượng đại diện, không tự đo tới khi tác vụ hoàn tất. Muốn thời lượng tác vụ phải quan sát trạng thái hoàn tất ở ranh giới khác.

### Bài 7: Gọi lại method bị chặn

Tại sao tự gọi lại `target.interceptedMethod()` trong advice có thể khác `proceed()`?

**Đáp án:** đó là một đường gọi mới, có thể kích hoạt advice lần nữa hoặc bỏ qua chuỗi hiện tại; `proceed` đại diện cho continuation của join point đang được xử lý theo hợp đồng công cụ. Việc tự gọi có thể tạo đệ quy không mong muốn.

### Bài 8: Đổi giá trị trả về

Một around advice quan sát dùng:

~~~text
proceed()
return null
~~~

với phương thức được khai báo trả `String`. Rủi ro là gì?

**Đáp án:** caller có thể nhận null ngoài hợp đồng; giá trị thật bị đánh mất. Với các mô hình/kiểu khác còn có thể xuất hiện lỗi chuyển kiểu hoặc unboxing. Advice quan sát thường phải trả nguyên kết quả.

## 24. Checklist ghi nhớ

- Around advice **nắm quyền điều phối** phần tiếp theo của join point được chọn.
- `proceed` hoặc continuation tương đương **chuyển quyền điều khiển vào phần còn lại của chuỗi**, không nhất thiết gọi thẳng nghiệp vụ ngay lập tức.
- **Không proceed** có thể short-circuit; **một proceed** không chứng minh original chạy một lần; **nhiều proceed** có thể lặp phần trong khi công cụ hỗ trợ.
- Cần bảo toàn **return value, exception, số lần thực thi và hợp đồng nghiệp vụ** nếu advice chỉ nhằm quan sát.
- Kết hợp `try/catch/finally` giúp phân biệt success, error và cleanup; **lỗi do advice sinh ra** cũng có thể thay đổi kết quả.
- Thứ tự các around advice quyết định lớp nào là **ngoài/trong**, dữ liệu/log nào được nhìn thấy khi advice phía trong short-circuit.
- Khả năng đổi đối số, bỏ qua phần gốc, chạy lại, can thiệp constructor/field access **phụ thuộc mô hình AOP và semantics của cơ chế**.
- Một phương thức bất đồng bộ trả future không đồng nghĩa toàn bộ công việc hoàn tất khi `proceed` trả về.
- Pointcut và weaving vẫn quyết định join point nào thật sự có advice; proceed chỉ có ý nghĩa sau khi around advice đã nhận quyền điều khiển.

**Câu hỏi quan trọng nhất khi đọc một around advice:** “Lời gọi `proceed` này tiếp tục vào những lớp nào, có thể chạy phần gốc bao nhiêu lần, và điều gì xảy ra với kết quả hoặc ngoại lệ khi quyền điều khiển quay trở lại?”
