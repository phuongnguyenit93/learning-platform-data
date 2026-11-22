# Phân biệt vị trí gọi và vị trí thực thi phương thức trong AOP

Trong lập trình hướng khía cạnh (*Aspect-Oriented Programming*, AOP), **điểm can thiệp** (*join point*) là một vị trí hoặc sự kiện trong quá trình thực thi mà cơ chế AOP có thể gắn hành vi bổ sung. Hai loại điểm can thiệp liên quan đến phương thức rất dễ bị nhầm:

- **Method call join point (điểm gọi phương thức):** gắn với **nơi một lời gọi được phát ra**, nhìn từ phía mã đang gọi (*caller*).
- **Method execution join point (điểm thực thi phương thức):** gắn với **việc phương thức đích thực sự bắt đầu chạy**, nhìn từ phía phương thức được gọi (*callee*).

Chúng có liên hệ vì một lời gọi bình thường thường dẫn đến một lần thực thi phương thức, nhưng **không phải cùng một ranh giới**. Ranh giới khác nhau dẫn tới phạm vi pointcut, ngữ cảnh quan sát, thứ tự advice và những lời gọi được bao phủ khác nhau.

> **Phạm vi bài:** Giải thích AOP nói chung, từ trực giác cơ bản đến những trường hợp nâng cao về đa hình, ngoại lệ, đệ quy và kỹ thuật weaving. Các tên `call` và `execution` bên dưới biểu diễn *loại join point*; cú pháp pointcut chính xác và tập join point được hỗ trợ phụ thuộc công cụ AOP.

## 1. Trực giác qua một lời gọi đơn giản

Giả sử có hai phương thức Java:

```java
class InvoiceService {
    void issueInvoice() {
        System.out.println("Issue invoice");
    }
}

class InvoiceController {
    void submit(InvoiceService service) {
        service.issueInvoice(); // [A] Vị trí gọi
    }
}
```

Đoạn này là mã minh họa, **không phải chương trình độc lập có `main`**.

- **[A]** nằm ở `InvoiceController.submit(...)`: đây là *call site*, nơi biểu thức `service.issueInvoice()` phát sinh yêu cầu gọi phương thức.
- Khi việc chuyển điều khiển thành công, JVM bắt đầu chạy thân `InvoiceService.issueInvoice()`: đây là *execution entry*, ranh giới vào phương thức đích.
- Khi phương thức kết thúc, luồng điều khiển quay về phía biểu thức gọi ở [A] (trừ trường hợp luồng thực thi bị kết thúc bất thường ở mức runtime).

Nếu đặt advice ở phía **call**, ta đang quan tâm đến **một lần đi qua vị trí phát sinh lời gọi**. Nếu đặt advice ở phía **execution**, ta quan tâm đến **một lần phương thức đích được thực thi**.

### Hình dung luồng điều khiển

```text
CALLER: InvoiceController.submit()       CALLEE: InvoiceService.issueInvoice()
----------------------------------       ------------------------------------
Trước biểu thức gọi
    |
    +-- [method CALL join point]
    |             |
    |             +------------------> [method EXECUTION join point]
    |                                     |
    |                                     +--> thân issueInvoice()
    |                                     |
    |             <------------------ rời execution (return/throw)
    |
    +-- rời call (return/throw)
    |
Tiếp tục trong submit() hoặc xử lý lỗi
```

Sơ đồ diễn tả trường hợp lời gọi đồng bộ thông thường. Một **around advice tại call** có thể bao quanh cả bước chuyển tới phương thức đích; một **around advice tại execution** bao quanh phần thực thi đích. Các khối advice thực tế được chèn bằng cơ chế weaving/interception của công cụ nên không nhất thiết tương ứng với một frame Java có tên rõ ràng.

## 2. Bảng so sánh hai loại join point

| Góc nhìn | Method call | Method execution |
| --- | --- | --- |
| Vị trí logic | Biểu thức/vị trí phát sinh lệnh gọi trong caller | Ranh giới vào phần thực thi phương thức đích |
| Bên sở hữu ngữ cảnh | Phía gọi; tại sao và ở đâu phát sinh lời gọi | Phía được gọi; phương thức nào thực sự chạy |
| Số vị trí tĩnh | Cùng một phương thức đích có thể được gọi từ nhiều call site | Một thân phương thức có thể phục vụ nhiều caller |
| Đa hình | Call site có thể khai báo qua interface/kiểu cha | Body thực thi phụ thuộc dispatch runtime |
| Điều kiện chọn | Có thể quan tâm tới nguồn gọi hoặc chữ ký được gọi | Có thể quan tâm tới phương thức/loại thực thi |
| Ngữ cảnh caller | Thường dễ liên hệ với vị trí gọi | Không mặc nhiên biết một caller tĩnh duy nhất |
| Ngữ cảnh callee | Có thể quan sát đối tượng được gọi, tùy công cụ | Gắn trực tiếp với target đang thực thi |
| Lời gọi nội bộ | Mỗi biểu thức gọi nội bộ có thể là call join point nếu công cụ weave được | Method execution có thể xảy ra dù lời gọi đến từ trong cùng đối tượng |
| Chiến lược triển khai | Cần hỗ trợ quan sát/chèn ở call site | Cần hỗ trợ quan sát/chèn ở execution entry |
| Dùng khi nào | Chính sách gắn với **nơi phát lời gọi** | Chính sách gắn với **mọi lần chạy của đích** |
| Tính phổ quát | Không phải engine AOP nào cũng hỗ trợ | Cũng không phải engine nào bao phủ mọi execution |

**Lưu ý quan trọng:** “Có call join point” không nhất thiết đồng nghĩa advice chỉ chạy một lần. Một call site nằm trong vòng lặp có thể phát sinh rất nhiều sự kiện gọi ở thời gian chạy. Tương tự, “có một thân phương thức” không có nghĩa nó chỉ có một sự kiện execution: mỗi lần thực thi là một sự kiện riêng.

## 3. Call site là gì, và vì sao nó thuộc phía caller?

**Call site** là một vị trí trong mã mà chương trình thực hiện lời gọi. Ví dụ:

```java
// Hai vị trí gọi tĩnh khác nhau.
class Checkout {
    void confirm(Billing billing) {
        billing.charge("ORDER-1");     // call site #1
    }
}

class BatchJob {
    void bill(Billing billing) {
        billing.charge("ORDER-2");     // call site #2
    }
}

interface Billing {
    void charge(String orderId);
}
```

Mã trên chỉ nhằm nhận diện vị trí gọi và **không biên dịch độc lập vì chưa có implementation/cấu hình chạy**.

Hai biểu thức `billing.charge(...)` thuộc hai caller khác nhau. Nếu một chính sách AOP chọn **vị trí gọi từ `Checkout`**, nó có thể áp dụng ở call site #1 nhưng không áp dụng ở #2, **ngay cả khi hai lời gọi đi tới cùng một implementation**. Ngược lại, nếu chính sách chọn *mọi lần thực thi* `BillingImpl.charge(...)`, nó có thể quan sát cả hai lời gọi vì cùng phương thức đích đã chạy.

### Một call site, nhiều lượt gọi

```java
for (String id : orderIds) {
    billing.charge(id); // Một vị trí tĩnh, nhiều sự kiện gọi động
}
```

Pointcut theo call site có thể khớp vị trí này và advice thực thi mỗi lần chương trình đi qua nó. Đừng đánh đồng **số vị trí trong source** với **số lần advice được kích hoạt**.

### Nhiều call site, một implementation

```text
Checkout.confirm() ---- call #1 -----+
                                     +--> BillingImpl.charge() execution
BatchJob.bill() ------- call #2 -----+
```

Hai call site tĩnh khác nhau có thể dẫn đến hai lần execution khác nhau của cùng phương thức. Nếu muốn chính sách gắn với *mọi đường đi vào một implementation*, execution thường là góc nhìn phù hợp hơn.

## 4. Execution là gì, và vì sao thuộc phía callee?

**Method execution join point** đại diện cho lần thực thi một phương thức đích. Khi một lệnh gọi chọn được implementation cụ thể và đi vào thân phương thức đó, phương thức thực hiện công việc của nó. Advice tại execution được xem là gắn với ranh giới chạy của phương thức.

Ví dụ:

```java
class BillingImpl implements Billing {
    @Override
    public void charge(String orderId) {
        validate(orderId);
        debit(orderId);
    }

    private void validate(String orderId) {
        // Kiểm tra dữ liệu.
    }

    private void debit(String orderId) {
        // Cập nhật trạng thái thanh toán.
    }
}
```

Đây là **mã minh họa**, không phải tệp độc lập; giả định interface `Billing` đã tồn tại.

Nếu công cụ hỗ trợ execution join point của `charge` và lựa chọn đúng phương thức đó, advice có thể chạy khi `charge` được thực thi bất kể caller xuất phát từ `Checkout`, `BatchJob` hay lớp khác.

Điều này đặc biệt hữu ích cho các concern gắn với **hợp đồng hành vi của phương thức**: đo thời gian thực thi một API, theo dõi tổng số lần xử lý, kiểm toán thao tác nghiệp vụ tại ranh giới thực thi, hoặc thực thi một guard trước khi thân phương thức chạy.

Tuy nhiên, nếu yêu cầu là “chỉ audit khi được gọi từ `Checkout`”, chỉ chọn execution của `charge` thường chưa đủ vì execution đó có thể được kích hoạt từ nhiều caller. Việc truy tìm caller qua stack là một kỹ thuật khác, có giới hạn riêng và không biến execution thành call site.

## 5. Thứ tự when call và execution cùng được can thiệp

Giả sử một cơ chế AOP đủ khả năng weave advice cho **cả** call site và execution entry của cùng một lời gọi đồng bộ. Nếu mỗi advice bao quanh và đều gọi tiếp đúng một lần, thứ tự khái niệm có thể là:

```text
call.before
    execution.before
        target.method() body
    execution.after-returning
call.after-returning
```

Khi target ném ngoại lệ:

```text
call.before
    execution.before
        target.method() throws
    execution.after-throwing
call.after-throwing
```

Với xử lý dạng `finally`, các bước dọn dẹp ở phía execution chạy khi rời execution và các bước tương ứng ở phía call chạy khi rời call. **Đây là một kịch bản minh họa theo nesting tự nhiên**, không phải cam kết một thứ tự chuẩn cho mọi hệ thống AOP. Nhiều aspect cùng khớp một join point còn có quy tắc precedence riêng.

### Call advice có thể thấy điều execution advice không thấy?

Trong một số mô hình weaving tại call site, advice bao quanh phần phát lời gọi nên có thể quan sát các lỗi xảy ra trước khi target thực sự được vào, chẳng hạn một lời gọi gặp đối tượng nhận `null`. Nhưng **chi tiết thời điểm đánh giá receiver, đối số và thời điểm bắt đầu join point phụ thuộc ngữ nghĩa ngôn ngữ cùng cơ chế weaving**; không thể khẳng định mọi công cụ sẽ bắt được cùng một lỗi ở cùng vị trí.

Nếu chưa vào được thân phương thức, **không có lần thực thi thân phương thức ấy** để execution advice quan sát. Do đó, không nên cho rằng một lỗi nhìn thấy ở caller luôn chứng minh target đã chạy.

## 6. Ví dụ Java 17+ chạy được: hai vị trí gọi, hai implementation

Ví dụ này cố tình đặt các dòng log ở **phía caller** và **đầu/cuối thân phương thức đích** để làm lộ hai ranh giới. Những dòng log có tiền tố `CALL`/`EXEC` là **mô phỏng thủ công vị trí quan sát**, không phải advice được tự động weave. Ví dụ dùng Java chuẩn, nên chạy độc lập mà không cần thư viện AOP.

Lưu tệp **`CallVsExecutionDemo.java`** bằng UTF-8:

```java
public class CallVsExecutionDemo {
    interface Formatter {
        String format(String text);
    }

    static final class UpperFormatter implements Formatter {
        @Override
        public String format(String text) {
            System.out.println("EXEC enter UpperFormatter.format");
            try {
                if ("fail".equals(text)) {
                    throw new IllegalArgumentException("invalid text");
                }
                String result = text.toUpperCase(java.util.Locale.ROOT);
                System.out.println("EXEC return UpperFormatter.format");
                return result;
            } catch (RuntimeException error) {
                System.out.println("EXEC throw UpperFormatter.format");
                throw error;
            } finally {
                System.out.println("EXEC finally UpperFormatter.format");
            }
        }
    }

    static final class BracketFormatter implements Formatter {
        @Override
        public String format(String text) {
            System.out.println("EXEC enter BracketFormatter.format");
            String result = "[" + text + "]";
            System.out.println("EXEC return BracketFormatter.format");
            return result;
        }
    }

    // Call site #1: phát lời gọi từ useInTitle().
    static String useInTitle(Formatter formatter) {
        System.out.println("CALL before useInTitle");
        try {
            String result = formatter.format("alpha");
            System.out.println("CALL return useInTitle");
            return result;
        } finally {
            System.out.println("CALL finally useInTitle");
        }
    }

    // Call site #2: duy nhất một biểu thức gọi, nhận nhiều
    // implementation runtime khác nhau qua tham số Formatter.
    static String useInReport(Formatter formatter, String value) {
        System.out.println("CALL before useInReport");
        try {
            String result = formatter.format(value);
            System.out.println("CALL return useInReport");
            return result;
        } catch (RuntimeException error) {
            System.out.println("CALL throw useInReport");
            throw error;
        } finally {
            System.out.println("CALL finally useInReport");
        }
    }

    public static void main(String[] args) {
        Formatter upper = new UpperFormatter();
        Formatter bracket = new BracketFormatter();

        System.out.println("RESULT " + useInTitle(upper));
        System.out.println("RESULT " + useInReport(upper, "beta"));
        System.out.println("RESULT " + useInReport(bracket, "gamma"));

        try {
            useInReport(upper, "fail");
        } catch (IllegalArgumentException error) {
            System.out.println("HANDLED " + error.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CallVsExecutionDemo.java
java CallVsExecutionDemo
```

**Đầu ra chính xác** (không tính những thông báo riêng của môi trường terminal):

```text
CALL before useInTitle
EXEC enter UpperFormatter.format
EXEC return UpperFormatter.format
EXEC finally UpperFormatter.format
CALL return useInTitle
CALL finally useInTitle
RESULT ALPHA
CALL before useInReport
EXEC enter UpperFormatter.format
EXEC return UpperFormatter.format
EXEC finally UpperFormatter.format
CALL return useInReport
CALL finally useInReport
RESULT BETA
CALL before useInReport
EXEC enter BracketFormatter.format
EXEC return BracketFormatter.format
CALL return useInReport
CALL finally useInReport
RESULT [gamma]
CALL before useInReport
EXEC enter UpperFormatter.format
EXEC throw UpperFormatter.format
EXEC finally UpperFormatter.format
CALL throw useInReport
CALL finally useInReport
HANDLED invalid text
```

### Phân tích kết quả

**Lần 1 — `useInTitle(upper)`:** lời gọi xảy ra ở call site #1. Việc dispatch đưa chương trình tới implementation `UpperFormatter.format`. Dòng `EXEC enter` chạy sau `CALL before`.

**Lần 2 — `useInReport(upper, "beta")`:** call site #2 khác #1 nhưng lại dẫn tới cùng phương thức `UpperFormatter.format`. Đây là bằng chứng một execution target có thể nhận lời gọi từ nhiều vị trí.

**Lần 3 — `useInReport(bracket, "gamma")`:** vẫn ở call site #2, nhưng runtime target đổi thành `BracketFormatter.format`. Đây là bằng chứng một call site có thể đưa đến nhiều implementation tùy đối tượng tại thời điểm chạy.

**Lần 4 — `useInReport(upper, "fail")`:** target ném `IllegalArgumentException`. Execution chạy phần xử lý lỗi và `finally` trước khi caller nhận ngoại lệ rồi chạy phần `catch/finally` của mình. Kết quả không có dòng `EXEC return` hay `CALL return` cho lần này.

**Giới hạn của ví dụ:** việc chèn thủ công `System.out.println(...)` không tạo ra join point AOP thật. Trong AOP, pointcut/advice nằm ngoài phương thức đích và được công cụ kết hợp vào vị trí phù hợp. Ví dụ làm rõ **ranh giới quan sát và thứ tự dòng điều khiển**, sau đó ta mới chọn đúng cơ chế can thiệp khi triển khai.

## 7. Đa hình: chữ ký lời gọi và phương thức thực chạy không luôn trùng nhau

Đây là một trong những khác biệt quan trọng nhất.

```java
interface Notifier {
    void send(String text);
}

class EmailNotifier implements Notifier {
    @Override
    public void send(String text) {
        System.out.println("email:" + text);
    }
}

class ConsoleNotifier implements Notifier {
    @Override
    public void send(String text) {
        System.out.println("console:" + text);
    }
}

void dispatch(Notifier notifier) {
    notifier.send("Hi");
}
```

Mã là **minh họa ý tưởng** đặt trong một phạm vi phù hợp, không phải tệp Java độc lập.

Ở caller, biểu thức `notifier.send("Hi")` được viết thông qua kiểu khai báo `Notifier`. Runtime quyết định implementation nào thực thi, dựa trên đối tượng thực tế. Vì vậy:

- Một **pointcut theo method call** có thể chọn lệnh gọi nhìn từ kiểu/interface `Notifier` hoặc thông tin call site mà cơ chế hỗ trợ.
- Một **pointcut theo method execution** có thể chọn execution của `EmailNotifier.send` và loại trừ `ConsoleNotifier.send`, nếu cơ chế hỗ trợ nhận diện execution tương ứng.
- Điều kiện khớp dựa trên **chữ ký khai báo tĩnh** và **loại đối tượng runtime** có thể cho kết quả khác nhau.

Đừng đồng nhất “method được nhắc trong source” với “implementation đã chạy”. Với **overriding**, dynamic dispatch có thể chọn override; với **overloading**, trình biên dịch lựa chọn overload dựa trên kiểu/đối số ở compile time, rồi quy tắc dispatch tương ứng được áp dụng. Khi viết pointcut, phải biết đang khớp *mẫu chữ ký nào* và cơ chế có xét runtime target hay không.

### Phương thức được thừa kế và interface

Trong thiết kế đối tượng, caller có thể biết một interface nhưng thân phương thức nằm ở class triển khai hoặc class cha. Nếu chỉ chọn execution theo một kiểu cụ thể, có thể bỏ lọt phương thức được kế thừa/override hoặc phương thức mặc định (*default method*) tùy cách công cụ ánh xạ chữ ký và bytecode. Đừng suy luận pointcut chỉ dựa vào tên hiển thị trong IDE; hãy kiểm thử những implementation và đường gọi thực tế.

## 8. Phân biệt khi có nhiều caller, wrapper và chuỗi lời gọi

Một luồng đồng bộ có thể gồm nhiều cấp:

```text
UI.submit()
  -> Controller.placeOrder()    [call ở UI]
       -> Service.reserve()     [call ở Controller]
            -> Database.save()  [call ở Service]
```

Ở đây có ít nhất ba vị trí gọi khác nhau và ba lần execution có thể quan sát, tùy loại join point và phạm vi weaving. Một aspect chọn **call từ `Controller` vào `Service`** có ý nghĩa “chính sách tại ranh giới tầng caller này”. Một aspect chọn **execution của `Service.reserve`** có nghĩa “mỗi lần service này thực hiện nghiệp vụ”, bất kể ai gọi nó.

Nếu thêm một client khác, chẳng hạn batch job gọi trực tiếp `Service.reserve`, pointcut dựa trên *call từ Controller* có thể bỏ qua lượt batch. Pointcut execution ở service có thể vẫn áp dụng. Chọn loại join point phải xuất phát từ **ý nghĩa chính sách** chứ không chỉ vì cú pháp biểu thức ngắn.

### Call-side concern và execution-side concern

- **Call-side:** giám sát mọi lời gọi từ một thành phần sang một API ngoài, thu thập thống kê phụ thuộc, giới hạn hoạt động do một caller phát ra hoặc áp dụng policy ở boundary caller cụ thể.
- **Execution-side:** đo tổng thời gian của một phương thức đích, audit mọi lần thực thi một hành vi, gắn dữ liệu trace cho một nhóm implementation, hoặc kiểm tra bất biến ở ranh giới method body.

Đây là những ví dụ định hướng thiết kế, không khẳng định tất cả công cụ AOP đều hỗ trợ mọi tiêu chí pointcut tương ứng.

## 9. Lời gọi nội bộ trong cùng đối tượng (*self-invocation*)

Giả sử:

```java
class PriceCalculator {
    void calculate() {
        normalize();
    }

    void normalize() {
        // Công việc nội bộ.
    }
}
```

Có một biểu thức gọi `normalize()` bên trong `calculate()`; việc vào thân `normalize()` là một sự kiện execution. Nếu một công cụ có khả năng **weave trực tiếp cả call site nội bộ và execution entry** trong bytecode, về nguyên tắc hai loại điểm can thiệp có thể được nhận diện.

Nhưng nếu chương trình dùng **proxy đứng ngoài đối tượng**, lời gọi `calculate()` đi qua proxy không khiến `this.normalize()` trong target tự động quay ra proxy. Khi đó lời gọi nội bộ có thể **không bị interception**, dù `normalize()` vẫn thực thi bình thường.

Phải phân biệt:

1. **Bản chất join point:** mã nội bộ vẫn có một lời gọi và một execution.
2. **Khả năng quan sát của công cụ:** proxy, weaving lúc biên dịch và weaving bytecode có phạm vi can thiệp khác nhau.
3. **Đường đi runtime:** việc lời gọi thực sự đi qua lớp trung gian hay không quyết định advice của interceptor có chạy hay không.

Kết luận “self-invocation luôn bỏ qua AOP” là quá rộng. Nó đúng với những chiến lược can thiệp *phụ thuộc hoàn toàn vào đường gọi qua proxy*; không phải định luật cho mọi kỹ thuật AOP.

## 10. Đệ quy và số lượng join point động

Với phương thức đệ quy:

```java
static int factorial(int n) {
    return n <= 1 ? 1 : n * factorial(n - 1);
}
```

Có một **call site tự gọi** bên trong thân phương thức, nhưng khi chạy `factorial(4)`, chương trình vào thân `factorial` với `n = 4, 3, 2, 1`: bốn lần execution. Call site đệ quy bên trong phương thức chỉ được đánh giá ở các lượt `n = 4, 3, 2`, tức ba lần phát sinh lời gọi đệ quy; ngoài ra còn có lời gọi ban đầu từ nơi bắt đầu `factorial(4)`.

Hai hệ quả:

- Advice tại **execution** của `factorial` có thể được kích hoạt cho từng lượt vào thân nếu cơ chế bao phủ cả bốn lần.
- Advice tại **call site đệ quy** có thể kích hoạt cho ba lượt tự gọi; lời gọi đầu tiên đến `factorial(4)` thuộc một call site khác.

Nếu advice dùng around rồi **gọi tiếp nhiều lần**, lượng execution có thể tăng so với logic ban đầu. Nếu advice của một join point tự tạo lời gọi khớp chính pointcut, có nguy cơ reentrancy/đệ quy không chủ ý; cần giới hạn phạm vi và thiết kế guard.

### Lưu ý về số lượng

Không phải quy tắc “một call event bằng đúng một execution event” luôn đúng. Một advice ở call join point có thể chặn không gọi đích, thay kết quả hoặc thử lại theo chính sách; lỗi cũng có thể phát sinh trước khi vào thân phương thức. Tương tự, một execution join point có thể bắt nguồn từ reflection hoặc các cơ chế triệu gọi không có call site Java dạng thông thường mà source code của bạn dễ chỉ ra. **Số lần advice thực tế phải kiểm chứng theo ngữ nghĩa cơ chế đang dùng.**

## 11. Nếu ngoại lệ xảy ra trước khi vào thân phương thức thì sao?

Khi đọc log, rất dễ suy luận nhầm “caller đã thực hiện lời gọi” thành “callee đã bắt đầu chạy”.

Xét:

```java
InvoiceService service = null;
service.issueInvoice();
```

Lệnh ở caller là một **biểu thức gọi** về mặt cú pháp, nhưng quá trình thực hiện sẽ ném `NullPointerException` vì receiver null, **không chạy thân `InvoiceService.issueInvoice()`**. Một cơ chế được weave tại call site có thể có điểm quan sát khác với cơ chế được weave tại execution entry; thứ tự evaluation và cách chèn advice quyết định điều gì quan sát được.

Một tình huống khác:

```java
service.issueInvoice(buildInvoiceData());
```

Nếu `buildInvoiceData()` ném ngoại lệ trong quá trình đánh giá đối số, lời gọi đến `issueInvoice(...)` không hoàn tất bước chuẩn bị và thân của nó không bắt đầu chạy. Nếu cần theo dõi chính xác “đã thử gọi API” so với “API thật sự được vào”, phải định nghĩa rõ ranh giới đo lường và kiểm thử ngoại lệ xảy ra ở từng phía.

Các trường hợp như lỗi truy cập class, linkage error, reflection hoặc native call cũng cần phân tích theo ngữ nghĩa của JVM và cơ chế AOP cụ thể; không coi tất cả lỗi quanh biểu thức gọi là ngoại lệ do thân target ném ra.

## 12. Khi dùng proxy/interceptor, ta đang quan sát ranh giới nào?

Một **runtime proxy** nhận lời gọi từ caller thay cho target, chạy logic bổ sung rồi chuyển tiếp. Nó thường quan sát **lời gọi đi qua proxy** và có thể thiết lập một ranh giới interception hữu ích. Tuy nhiên, không nên đồng nhất điều đó một cách tự động với *mọi method call join point ở mọi nơi* hoặc *mọi execution join point trong bytecode target*.

```text
caller -> proxy (interception) -> target.method()   [đi qua trung gian]
caller -----------------------> target.method()   [đi thẳng]
target.method() -> this.helper()                    [gọi nội bộ]
```

Chỉ đường đầu tiên chắc chắn đi qua chính proxy trong sơ đồ. Hai đường còn lại có thể bỏ qua interception ở proxy. Nếu muốn chọn các **call site tĩnh** từ caller cụ thể, proxy dùng chung trước target thường không tự phân biệt được chính xác từng vị trí source call. Nếu muốn mọi **execution** kể cả self-invocation, đôi khi cần kỹ thuật weaving khác.

Trong Java, `java.lang.reflect.Proxy` dựa trên interface và chuyển các lời gọi trên proxy tới `InvocationHandler`. Đây là cơ chế interceptor chuẩn để học về chain advice, nhưng **không phải bằng chứng rằng Java SE tự hỗ trợ đầy đủ pointcut `call`/`execution`**. Hai loại join point ấy thuộc mô hình AOP và chỉ hiện hữu như điểm có thể weave khi công cụ có cơ chế hỗ trợ tương ứng.

## 13. Weaving ảnh hưởng đến việc quan sát call/execution

| Cơ chế | Góc nhìn thực tế | Khả năng/giới hạn cần lưu ý |
| --- | --- | --- |
| **Compile-time weaving** | Biến đổi chương trình khi biên dịch | Có thể can thiệp call site hoặc execution entry nếu công cụ hỗ trợ và mã cần weave nằm trong phạm vi build. |
| **Post-compile weaving** | Biến đổi bytecode đã biên dịch | Cần bảo đảm artifact đúng đã được biến đổi; call site nằm ở caller có thể cần weave cả caller. |
| **Load-time weaving** | Biến đổi class khi được JVM nạp | Class loader, thứ tự nạp và danh sách class được weave ảnh hưởng phạm vi can thiệp. |
| **Runtime proxy/interception** | Quan sát lời gọi qua đối tượng trung gian | Không tự động phủ mọi call site hay lời gọi nội bộ. |

Điểm đặc biệt quan trọng là **mã sở hữu vị trí can thiệp**:

- Muốn can thiệp **call site**, hệ thống có thể phải instrument/weave phần mã caller nơi chứa lệnh gọi.
- Muốn can thiệp **execution entry**, hệ thống có thể cần instrument/weave class định nghĩa thân phương thức.
- Nếu chỉ kiểm soát một bên (ví dụ thư viện caller hoặc target) thì tính khả thi của điểm can thiệp có thể rất khác nhau.

Ví dụ, một ứng dụng không sở hữu bytecode của một số caller có thể gặp giới hạn khi muốn weave call site trong caller ấy. Mặt khác, instrument execution của một API do mình sở hữu có thể dễ quản lý hơn vì nó tập trung tại implementation. Đây là hệ quả về **vị trí cần chèn mã**, không phải cam kết rằng một kỹ thuật nhất định luôn hỗ trợ mọi loại pointcut.

## 14. Ngữ cảnh `this`, `target` và caller/callee

Một số mô hình AOP cung cấp khả năng bind đối tượng *hiện tại* và *đối tượng đích* của join point. Tên như `this` và `target` có thể xuất hiện trong ngôn ngữ pointcut, nhưng ý nghĩa chính xác phụ thuộc loại join point và công cụ.

Với mô hình call/execution định hướng đối tượng cổ điển:

- Tại **method call**, *caller-side this* có thể là đối tượng đang thực thi mã phát lời gọi (nếu call site nằm trong một phương thức instance); *target* là receiver mà lời gọi hướng đến.
- Tại **method execution**, đối tượng đang thực thi thân method và receiver đích thường là cùng instance của callee trong lời gọi instance thông thường.
- Với **phương thức static**, không có receiver instance theo nghĩa của lời gọi instance. Không mặc định `this`/`target` luôn tồn tại hay luôn mang đối tượng cùng kiểu.
- Với **proxy**, những khái niệm đối tượng proxy, target thực và runtime receiver cần được kiểm tra theo API cụ thể; không áp đặt ánh xạ chung cho mọi công cụ.

Những khác biệt đó giải thích vì sao pointcut theo **caller type** thường cần vị trí call, còn pointcut theo **implementation type** thường tự nhiên hơn ở execution. Tuy vậy, nhiều hệ thống có thêm khả năng suy diễn/giới hạn theo ngữ cảnh runtime, nên đây là định hướng lựa chọn, không phải quy tắc bất biến.

## 15. Reflection, method handles và lời gọi gián tiếp

Một phương thức có thể được thực thi mà source code caller không chứa biểu thức trực tiếp `target.method()`.

Ví dụ reflection:

```java
java.lang.reflect.Method method =
        InvoiceService.class.getDeclaredMethod("issueInvoice");
method.invoke(service);
```

Đây là **đoạn minh họa đặt trong phạm vi có biến `service`, có thể ném checked exceptions**.

Biểu thức Java trực tiếp được viết ở đây là `method.invoke(service)`. Bên trong cơ chế reflection, runtime có thể dẫn đến việc thân `InvoiceService.issueInvoice` thực sự chạy. Một cơ chế **execution weaving** trên thân `issueInvoice` có thể quan sát lần thực thi ấy. Một pointcut **call** tại biểu thức source `service.issueInvoice()` ban đầu thì không thể giả định đã khớp vì biểu thức đó không tồn tại tại vị trí reflection trên.

Các API như method handles, proxy hay callback có đường gọi riêng. Khi cần bảo đảm thu thập mọi lượt chạy của một implementation, hãy xác nhận execution weaving có bao phủ cả các cách triệu gọi gián tiếp đang dùng. Không suy luận rằng mọi lệnh `Method.invoke` đều được coi như một static call join point của phương thức đích theo cùng quy tắc.

## 16. Bất đồng bộ: return của lời gọi chưa chắc là kết thúc công việc

Ví dụ khái niệm:

```java
java.util.concurrent.CompletableFuture<String> result =
        java.util.concurrent.CompletableFuture.supplyAsync(
                () -> expensiveCalculation()
        );
```

Đây là **mã minh họa**, giả định có `expensiveCalculation()` trả về `String`.

Lời gọi `supplyAsync(...)` ở caller có thể trả về một `CompletableFuture` trước khi computation thực tế xong. Việc công việc chạy trên luồng khác là một execution khác, với call/execution boundary khác. Do đó:

- Đo thời gian quanh **call tới hàm khởi tạo tác vụ** thường đo thời gian **gửi/lên lịch**, không đo trọn thời gian xử lý bất đồng bộ.
- Quan sát **execution của task** có thể đo thời gian chạy task, nếu cơ chế có thể can thiệp đúng execution ấy.
- Muốn đo **end-to-end latency**, thường cần ghép ngữ cảnh giữa thời điểm nhận/gửi yêu cầu và thời điểm tác vụ hoàn tất.
- Không mặc định `ThreadLocal` của caller tự truyền nguyên vẹn qua executor hoặc callback bất đồng bộ.

Điều này cho thấy phân biệt call/execution không chỉ là hai vị trí code: nó giúp tránh đặt metric, timeout hoặc tracing ở **sai ranh giới thời gian**.

## 17. Lựa chọn pointcut phù hợp với yêu cầu thực tế

Hãy đặt câu hỏi về **đối tượng chịu trách nhiệm** và **phạm vi chính sách**.

| Yêu cầu | Hướng phù hợp hơn | Vì sao |
| --- | --- | --- |
| “Ghi tất cả lời gọi do `Checkout` gửi tới API thanh toán” | Call join point tại caller tương ứng | Quan tâm đến nguồn phát lời gọi. |
| “Đo mỗi lần `ChargeService.charge` thật sự thực thi” | Execution join point ở callee | Quan tâm đến mọi lượt chạy của target. |
| “Theo dõi mỗi lần một module gọi thư viện bên ngoài” | Call join point nếu có thể weave caller | Nguồn lời gọi là yếu tố chính của policy. |
| “Áp dụng audit cho mọi lần thực thi hàm phát hành dữ liệu” | Execution join point nếu hỗ trợ đầy đủ | Chính sách gắn với hành vi đích. |
| “Chỉ đo thời gian queue một tác vụ async” | Call quanh API submit/schedule | Mục tiêu là độ trễ gửi tác vụ. |
| “Đo thời gian xử lý thật của tác vụ async” | Execution của task hoặc quan sát completion | Mục tiêu là công việc hoàn tất. |
| “Chặn mọi đường đi vào một operation, kể cả gọi nội bộ” | Xác minh execution weaving hoặc cơ chế bảo vệ ở chính target | Proxy ở một đầu vào có thể bỏ qua lời gọi nội bộ. |

Bảng chỉ ra **hướng lựa chọn ngữ nghĩa**, chưa đủ để kết luận có thể triển khai; công cụ cụ thể phải cung cấp điểm can thiệp và khả năng bind context cần thiết.

### Ba câu hỏi trước khi viết pointcut

1. **Chính sách thuộc phía nào?** Nơi caller quyết định gọi, hay hành vi callee phải thực hiện?
2. **Cần bao phủ những đường đi nào?** Caller khác, reflection, lời gọi nội bộ, đa hình, callback, async?
3. **Cơ chế can thiệp nằm ở đâu?** Có weave được caller không, có weave được implementation không, hay chỉ có proxy?

Nếu không trả lời được ba câu này, một pointcut khớp đúng ở bản demo vẫn có thể bỏ lọt các trường hợp thực tế.

## 18. Kiểm thử để tránh nhầm hai loại điểm can thiệp

Một bộ kiểm thử AOP chất lượng phải có **ca khớp** và **ca không khớp**, cũng như phân biệt số sự kiện call/execution.

### Ma trận kiểm thử quan trọng

| Tình huống | Điều phải chứng minh |
| --- | --- |
| Hai caller khác nhau cùng gọi một implementation | Call advice theo caller chỉ khớp nơi định nghĩa; execution advice ở đích có thể khớp cả hai. |
| Một call site nhận hai implementation | Loại execution thực tế có thể khác nhau do dynamic dispatch. |
| Caller gọi trực tiếp target hoặc đi qua proxy | Những đường bypass proxy có được bao phủ không? |
| Phương thức tự gọi phương thức khác trên `this` | Hệ thống có hỗ trợ interception nội bộ hay execution weaving không? |
| Target ném ngoại lệ | Advice return/throw/finally nằm đúng ranh giới, không đổi lỗi trái contract. |
| Receiver null hoặc lỗi đánh giá đối số | Target đã vào thân chưa; call instrumentation đo được giai đoạn nào? |
| Reflection/callback | Có execution được nhìn thấy dù không có direct source call tương ứng không? |
| Nhiều luồng và async | Metric/context có theo đúng lần chạy không? |
| Đệ quy | Advice áp dụng theo *mỗi sự kiện động*, không phải mỗi dòng source. |
| Nhiều aspect cùng khớp | Thứ tự advice và precedence có xác định và được test không? |

Có thể thêm **counter** cho call và execution advice rồi chạy các đường thử trên. Nhưng cần diễn giải counter đúng: một around advice có quyền bỏ qua hoặc gọi lại `proceed`, nên số lần quan sát có thể khác nhau một cách hợp lệ theo contract. Trong hệ thống quan sát thuần túy, nên bảo đảm advice không vô tình lặp thao tác.

### Kiểm tra hai chiều

- **False negative:** Những lượt gọi/thực thi cần được theo dõi nhưng không kích hoạt advice.
- **False positive:** Những lượt gọi/thực thi không thuộc chính sách nhưng vẫn kích hoạt advice.

Test chỉ xác minh rằng “aspect có chạy” thường không phát hiện được hai lỗi này. Hãy kiểm tra cả tập điểm **được chọn** và **bị loại**.

## 19. Các lỗi tư duy thường gặp

1. **“Một call site bằng một execution.”** Một vị trí gọi có thể được thực hiện nhiều lần; một lần lời gọi có thể không vào được thân đích; advice có thể chặn/retry tùy contract.
2. **“Call và execution chỉ khác tên.”** Chúng thuộc hai phía của ranh giới chuyển điều khiển, vì vậy ngữ cảnh và tập can thiệp khác nhau.
3. **“Chọn call của interface chính là chọn execution của implementation.”** Đa hình cho phép một call site dẫn đến nhiều implementation.
4. **“Một implementation chỉ có một caller.”** Nhiều class và nhiều vị trí có thể gọi cùng một method.
5. **“Self-invocation không tạo join point.”** Về mặt mô hình nó vẫn có call và execution; giới hạn nằm ở cơ chế interception đang dùng.
6. **“Proxy tự động hỗ trợ mọi loại pointcut.”** Proxy nhìn thấy lời gọi qua nó; method-call weaving tại mọi call site và method-execution weaving là hai khả năng khác.
7. **“Có stack trace caller nên execution cũng tương đương call.”** Stack có thể chịu ảnh hưởng reflection, tail behavior, inlining, async và hạ tầng runtime; truy dấu stack không thay đổi bản chất join point.
8. **“Lời gọi trả về nghĩa là công việc async đã xong.”** API gửi tác vụ có thể return trước khi task thực sự hoàn tất.
9. **“Mọi exception nhìn thấy ở call đều do target ném.”** Receiver null hoặc lỗi đánh giá đối số có thể khiến thân đích không hề được vào.
10. **“Pointcut đúng khi build là đủ.”** Phải kiểm chứng đường gọi runtime, tập class thực sự được weave và thứ tự advice.

## 20. Bài tập củng cố

1. **Đổi implementation:** Trong `CallVsExecutionDemo`, đổi đối số của `useInTitle` từ `upper` sang `bracket`. Call site nào giữ nguyên, execution target nào thay đổi?
2. **Tạo caller mới:** Viết một hàm thứ ba gọi `Formatter.format`. Nếu chỉ chọn call site của `useInReport`, lời gọi mới có thuộc phạm vi không? Nếu chọn execution `UpperFormatter.format` thì sao?
3. **Kiểm tra lời gọi nội bộ:** Thêm `UpperFormatter.normalize` và gọi nó bên trong `format`. Phân biệt sự tồn tại của join point với khả năng bắt được lời gọi ấy bằng proxy.
4. **Thử ngoại lệ:** Dùng `useInReport(upper, "fail")` để liệt kê chính xác thứ tự các sự kiện ở hai ranh giới; giải thích vì sao không có “return”.
5. **Phân tích đệ quy:** Với `factorial(4)`, đếm số lần vào execution và số lần đi qua call site đệ quy, chưa kể nơi gọi ban đầu.
6. **Thiết kế metric:** Muốn đo thời gian thực thi công việc async thật sự, tại sao chỉ đo quanh lời gọi `supplyAsync(...)` là chưa đủ?
7. **Thiết kế pointcut:** Hãy nêu một chính sách thực tế đòi hỏi ngữ cảnh caller và một chính sách khác chỉ cần biết callee; giải thích vì sao không nên dùng cùng một loại join point cho cả hai.

**Tự kiểm tra:** Nếu hai caller gọi cùng một method, call join point có giống nhau không? Nếu một caller gọi qua interface và runtime chọn hai implementation, execution có giống nhau không? Một method có thể chạy qua reflection mà không có biểu thức gọi trực tiếp trong source không? Lỗi xảy ra trước method entry có được tính là execution của target không?

## Kết luận

**Method call** trả lời câu hỏi **“lời gọi xuất phát ở đâu?”**, còn **method execution** trả lời **“phương thức nào thực sự chạy?”**. Chúng nối tiếp nhau trong lời gọi đồng bộ đơn giản nhưng phân biệt rõ khi có nhiều caller, dynamic dispatch, lời gọi nội bộ, reflection, lỗi trước method entry và bất đồng bộ. Chọn loại join point theo mục tiêu chính sách, sau đó kiểm chứng giới hạn weaving/interception thực tế, sẽ giúp aspect tác động **đúng vị trí, đủ phạm vi và đúng ngữ nghĩa**.