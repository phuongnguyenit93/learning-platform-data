# Vì sao `sealed interface` không thể làm kiểu đích cho lambda trong Java?

## 1. Kết luận chính xác theo ngôn ngữ Java

Trong Java 17 trở lên, một interface muốn trở thành **functional interface** phải thỏa **đồng thời** hai điều kiện:

1. Interface **không được khai báo `sealed`**.
2. Sau khi xét các phương thức kế thừa, ghi đè và loại các khai báo tương ứng với phương thức `public` của `Object`, nó có **một hợp đồng phương thức trừu tượng duy nhất** (*single abstract method*, SAM).

Vì vậy, **`sealed interface` có đúng một phương thức trừu tượng vẫn không phải functional interface**, và không thể là kiểu đích (*target type*) trực tiếp của biểu thức lambda hoặc method reference.

Đây là quy tắc của **Java Language Specification (JLS) `9.8**, không phải một giới hạn do một IDE hay thư viện cụ thể đặt ra. JLS `15.27.3 cũng yêu cầu kiểu đích của lambda là một functional interface type. Annotation `@FunctionalInterface` không thể thay đổi các quy tắc đó.

> **Điểm cần phân biệt:** Không dùng được `() -> ...` để tạo trực tiếp giá trị có kiểu đích `sealed interface` **không có nghĩa** không thể tạo đối tượng triển khai interface đó, không thể gọi phương thức của nó, hoặc không thể lưu một đối tượng tạo từ lambda vào biến có kiểu sealed thông qua một subtype hợp lệ.

## 2. Hai tính chất khác nhau: SAM và `sealed`

### 2.1. SAM nói về hợp đồng hành vi

Ví dụ một interface thông thường:

~~~java
@FunctionalInterface
interface Action {
    void execute();
}
~~~

`Action` có một phương thức trừu tượng `execute()`. Nó không `sealed`, vì vậy biểu thức `Action a = () -> System.out.println("run");` hợp lệ.

Một interface có thể thêm các phương thức `default`, `static`, `private` có phần thân mà vẫn có một SAM. Các phương thức `equals(Object)`, `hashCode()` và `toString()` có chữ ký tương đương các phương thức `public` của `Object` cũng không làm tăng số SAM.

### 2.2. `sealed` giới hạn các kiểu con **trực tiếp**

Khai báo `sealed` được Java hỗ trợ chính thức từ **Java 17**. Nó dùng để giới hạn những class/interface nào được phép **trực tiếp** `implements` hoặc `extends` kiểu sealed.

~~~java
sealed interface Task permits BuiltInTask {
    void execute();
}

final class BuiltInTask implements Task {
    @Override
    public void execute() {
        System.out.println("built-in");
    }
}
~~~

Đây là đoạn mã khai báo hợp lệ. `Task` chỉ có một phương thức abstract, nhưng vì nó là `sealed interface` nên không phải functional interface.

`permits BuiltInTask` là tập các subtype trực tiếp được cho phép. `BuiltInTask` là `final`, phù hợp với quy tắc rằng một class trực tiếp kế thừa kiểu sealed phải quyết định rõ cách tiếp tục hoặc dừng khả năng kế thừa (thường `final`, `sealed` hoặc `non-sealed` theo ngữ cảnh). Một interface được phép trực tiếp mở rộng sealed interface phải được khai báo `sealed` hoặc `non-sealed`.

Cú pháp `permits` **không phải danh sách các object có thể tạo**. Nó là danh sách các **kiểu trực tiếp** được phép kế thừa. Một khi có nhánh `non-sealed`, các subtype sâu hơn có thể được phép mở rộng qua nhánh đó.

### 2.3. Vì sao hai tính chất xung đột khi dùng lambda trực tiếp?

Lambda là một biểu thức cần **functional interface type** làm kiểu đích. Khi lambda được đánh giá ở runtime, kết quả là tham chiếu đến một đối tượng có triển khai interface kiểu đích; chi tiết cách runtime tạo hoặc tái sử dụng đối tượng được JLS cho phép thay đổi.

Ngược lại, một sealed interface quy định rõ tập các kiểu con trực tiếp được phép. Java vì vậy **loại interface được khai báo `sealed` khỏi định nghĩa functional interface** thay vì cho phép một lambda tự trở thành phương thức khai báo một kiểu con trực tiếp mới.

Quy tắc này còn chặt hơn trực giác “interface có đúng một abstract method thì dùng lambda được”: **một SAM là điều kiện cần nhưng chưa đủ**. Số lượng tham số lambda khớp hay thân lambda đúng kiểu trả về cũng không thể vượt qua điều kiện `sealed`.

Không cần dựa vào tên class synthetic do compiler/runtime có thể dùng để chứng minh quy tắc; nền tảng chính xác là điều kiện của JLS về **kiểu đích**.

## 3. Ví dụ không biên dịch: `sealed interface` có một SAM

Đoạn sau là **ví dụ cố ý sai**, đặt trong file `InvalidSealedTarget.java` để quan sát lỗi (không chạy chương trình):

~~~java
sealed interface ClosedAction permits DefaultAction {
    String apply(String input);
}

final class DefaultAction implements ClosedAction {
    @Override
    public String apply(String input) {
        return "default:" + input;
    }
}

public class InvalidSealedTarget {
    public static void main(String[] args) {
        ClosedAction action = input -> "lambda:" + input; // Lỗi biên dịch.
        System.out.println(action.apply("Java"));
    }
}
~~~

Thử biên dịch bằng JDK 17+:

~~~bash
javac InvalidSealedTarget.java
~~~

Kết quả: **biên dịch thất bại** tại biểu thức lambda gán cho `ClosedAction`. Thông báo chính xác của `javac` có thể thay đổi theo phiên bản, nhưng nguyên nhân là `ClosedAction` không phải functional interface vì được khai báo `sealed`. Không có stdout từ lệnh `java InvalidSealedTarget` vì không có chương trình được biên dịch thành công.

Việc giữ nguyên một abstract method và có class `DefaultAction` nằm trong `permits` **không khiến** `ClosedAction` trở thành kiểu đích của lambda. Trình biên dịch phải xét tính hợp lệ của **kiểu đích** trước khi xem một thân lambda có khớp hợp đồng hay không.

### Đánh dấu `@FunctionalInterface` có sửa được không?

Không. Nếu thêm `@FunctionalInterface` vào `ClosedAction`, bản khai báo interface cũng bị báo lỗi vì annotation đòi hỏi interface đáp ứng định nghĩa functional interface, trong khi `sealed` bị loại khỏi định nghĩa đó. Annotation là công cụ kiểm tra tại compile time, không làm thay đổi luật kiểu.

### Chuyển sang method reference có sửa được không?

Không. `ClosedAction action = String::trim;` cũng không hợp lệ vì method reference cần functional interface type. Chữ ký `String::trim` có thể tương thích với phương thức `String apply(String)` về tham số và kết quả, nhưng `ClosedAction` vẫn không phải functional interface.

## 4. Cách đúng thứ nhất: dùng subtype `non-sealed` làm kiểu đích

Có thể giữ một interface gốc `sealed` để quản lý các **nhánh trực tiếp**, và công khai một nhánh `non-sealed` có đúng một SAM cho các lambda.

Lưu thành `SealedWithLambdaDemo.java`:

~~~java
import java.util.Locale;

sealed interface Job permits BuiltInJob, OpenJob {
    String execute(String input);
}

final class BuiltInJob implements Job {
    @Override
    public String execute(String input) {
        return "builtin:" + input;
    }
}

@FunctionalInterface
non-sealed interface OpenJob extends Job {
    // Kế thừa SAM execute(String) từ Job.
}

public class SealedWithLambdaDemo {
    public static void main(String[] args) {
        Job builtIn = new BuiltInJob();

        OpenJob lambdaJob =
                input -> "lambda:" + input.toUpperCase(Locale.ROOT);

        // Upcast: đối tượng lambda triển khai OpenJob, và OpenJob extends Job.
        Job asJob = lambdaJob;

        System.out.println(builtIn.execute("one"));
        System.out.println(lambdaJob.execute("java"));
        System.out.println(asJob.execute("ok"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SealedWithLambdaDemo.java
java SealedWithLambdaDemo
~~~

Stdout chính xác:

~~~text
builtin:one
lambda:JAVA
lambda:OK
~~~

**Giải thích cơ chế:**

1. `Job` là sealed interface, khai báo một phương thức trừu tượng `execute(String)`. `Job` không phải functional interface.
2. `BuiltInJob` là một subtype trực tiếp hợp lệ, được liệt kê trong `permits` và khai báo `final`.
3. `OpenJob` cũng là subtype **trực tiếp** được cho phép; nó được khai báo `non-sealed`, tức nhánh này cho phép những subtype tiếp theo theo các quy tắc Java thông thường.
4. `OpenJob` không tự khai báo thêm abstract method, nên kế thừa đúng một SAM `execute(String)`. Nó **không bị sealed**; `@FunctionalInterface` hợp lệ và lambda có thể nhắm tới `OpenJob`.
5. `Job asJob = lambdaJob;` là phép gán upcast bình thường từ subtype sang supertype. Ta **không** tạo lambda có kiểu đích `Job`; kiểu đích khi tạo lambda là `OpenJob`.

Đây là điểm mấu chốt: **một object bắt nguồn từ lambda có thể được tham chiếu qua biến kiểu sealed** nếu nó đã được tạo bằng một kiểu con **functional interface không sealed** được phép. Giới hạn áp dụng tại bước dùng kiểu đích của lambda, không phải cấm mọi giá trị kiểu sealed từng có liên quan đến lambda.

### Vì sao không thể thay `OpenJob` bằng một interface bất kỳ?

Nếu viết thêm `interface OtherJob extends Job` nhưng `OtherJob` không nằm trong tập `permits` của `Job`, khai báo kế thừa trực tiếp sẽ không hợp lệ. Nếu cho phép nó, `OtherJob` cũng phải được khai báo `sealed` hoặc `non-sealed` vì nó trực tiếp mở rộng sealed interface. Một interface bình thường không liên hệ kế thừa với `Job` không tự động có thể gán cho biến `Job` chỉ vì nó có phương thức giống tên và chữ ký: hệ kiểu Java là **nominal typing**, cần quan hệ kiểu rõ ràng.

## 5. Cách đúng thứ hai: dùng lambda ở bên trong một class được `permits`

Không phải thiết kế nào cũng muốn mở một nhánh `non-sealed`. Nếu cần giữ tập kiểu triển khai trực tiếp **đóng**, có thể tạo một class `final` được cho phép triển khai sealed interface, rồi truyền lambda theo một functional interface độc lập vào class đó.

Lưu thành `SealedAdapterDemo.java`:

~~~java
import java.util.Objects;
import java.util.function.IntUnaryOperator;

sealed interface Calculation permits ConfigurableCalculation {
    int compute(int input);
}

final class ConfigurableCalculation implements Calculation {
    private final IntUnaryOperator rule;

    ConfigurableCalculation(IntUnaryOperator rule) {
        this.rule = Objects.requireNonNull(rule);
    }

    @Override
    public int compute(int input) {
        return rule.applyAsInt(input);
    }
}

public class SealedAdapterDemo {
    public static void main(String[] args) {
        Calculation doubledPlusOne =
                new ConfigurableCalculation(x -> x * 2 + 1);
        Calculation squared =
                new ConfigurableCalculation(x -> x * x);

        System.out.println(doubledPlusOne.compute(5));
        System.out.println(squared.compute(5));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SealedAdapterDemo.java
java SealedAdapterDemo
~~~

Stdout:

~~~text
11
25
~~~

**Phân tích từng kiểu:**

- `Calculation` là sealed interface, không phải functional interface; nó vẫn là kiểu hợp lệ của hai biến `doubledPlusOne` và `squared`.
- `ConfigurableCalculation` là class `final` nằm trong danh sách `permits`, vì vậy các instance của nó hợp lệ trong phân cấp sealed.
- `IntUnaryOperator` là functional interface chuẩn, có SAM `int applyAsInt(int operand)`, do đó hai lambda `x -> x * 2 + 1` và `x -> x * x` là hợp lệ tại vị trí truyền vào constructor.
- Việc constructor giữ `rule` trong trường `final` không thay đổi kiểu đích của lambda; kiểu đích vẫn là `IntUnaryOperator`.
- Phương thức `compute` chỉ ủy quyền cho `rule`. Mỗi phép tính được cung cấp bằng lambda, trong khi tập class trực tiếp triển khai `Calculation` vẫn được quản lý bởi `permits`.

Mẫu này thường gọi là **adapter/delegation**: sealed hierarchy quản lý danh mục loại đối tượng; functional interface diễn đạt hành vi có thể cấu hình. Lưu ý nếu một lambda capture mutable state thì riêng việc lưu nó trong trường `final` không bảo đảm logic thuần khiết hoặc an toàn luồng.

## 6. So sánh ba trường hợp dễ nhầm

| Khai báo/kiểu đích | Dùng lambda trực tiếp? | Giải thích |
|---|---|---|
| `interface A { void run(); }` | Có | Không sealed, có một SAM |
| `sealed interface A permits Impl { void run(); }` | Không | Sealed nên không đủ điều kiện của JLS `9.8, dù có một SAM |
| `non-sealed interface B extends A { }` với `A` là sealed và `B` được permits | Có nếu có đúng một SAM | `B` không sealed, được kế thừa SAM |
| `interface A { void run(); void stop(); }` | Không | Có hai phương thức abstract độc lập |
| `interface A { void run(); default void reset() {} }` | Có | `reset` không được đếm |
| `Runnable r = () -> ...` | Có | Kiểu đích là `Runnable`, không sealed |
| `A a = r;` với `A` sealed, `r` là `Runnable` không có quan hệ subtype | Không | Java không ép kiểu dựa trên việc hai interface trùng chữ ký |
| `A a = permittedSubtypeLambda;`, với subtype là non-sealed functional interface extends A | Có ở phép upcast | Lambda được tạo dưới kiểu đích subtype, sau đó gán lên supertype |

Trường hợp `non-sealed interface B extends A` chỉ hợp lệ khi `A` là sealed direct superinterface và `B` được phép mở rộng nó. Không thể thêm từ khóa `non-sealed` vào một interface bất kỳ không có sealed direct superinterface.

## 7. Tại sao Java không tự biến lambda thành một subtype được cho phép?

Một hiểu nhầm phổ biến là: “Nếu compiler đã biết `permits`, tại sao nó không tạo một instance thuộc subtype đã cho phép?”

Biểu thức lambda **không phải câu lệnh gọi constructor của một permitted class**. Nó dùng functional interface type làm kiểu đích và runtime cung cấp đối tượng thực thi hợp đồng đó; chi tiết triển khai có thể khác nhau theo JDK và không nên trở thành API contract.

Đối với `sealed interface`, ngôn ngữ muốn các nhánh kế thừa **trực tiếp** được khai báo có tên và được kiểm soát bởi `permits`. Nếu muốn dùng hành vi lambda trong phân cấp sealed, tác giả phải **chỉ rõ đường đi hợp lệ**:

- Công khai một permitted `non-sealed` subinterface có SAM để caller có thể dùng lambda làm giá trị kiểu subtype; hoặc
- Công khai constructor/factory của một permitted class và cho class đó nhận một functional interface làm chiến lược hành vi.

Như vậy, ta không đánh đồng “tạo thêm cách tính” với “tạo thêm subtype trực tiếp”. Với các mô hình domain cần quản lý chặt loại đối tượng (ví dụ loại lệnh hoặc kết quả), cách thứ hai thường dễ giữ bất biến của phân cấp hơn.

**Không kết luận quá rộng:** Một sealed interface hoàn toàn có thể khai báo abstract methods, default methods, generic parameters, và được class cụ thể triển khai. Nó chỉ không đủ điều kiện để trở thành functional interface **khi chính sealed interface đó được dùng làm kiểu đích cho lambda/method reference**.

## 8. Các lỗi thường gặp và cách kiểm tra

### Lỗi 1: Đếm một SAM rồi suy ra dùng lambda được

~~~java
// Minh họa cố ý không hợp lệ khi thêm annotation.
@FunctionalInterface
sealed interface SealedOp permits ConcreteOp {
    void run();
}

final class ConcreteOp implements SealedOp {
    public void run() {}
}
~~~

Dù `run()` là SAM duy nhất, annotation bị từ chối: sealed interface không phải functional interface. Cách sửa phụ thuộc mục tiêu thiết kế: nếu cần lambda trực tiếp thì dùng interface không sealed; nếu cần sealed thì cung cấp permitted class hoặc permitted non-sealed subinterface.

### Lỗi 2: Cast lambda sang sealed interface

~~~java
// Minh họa không hợp lệ; không phải một chương trình chạy độc lập.
// ClosedAction a = (ClosedAction) (text -> text);
~~~

Cast không bỏ qua điều kiện kiểu đích. Nếu kiểu cast là `ClosedAction` sealed, nó vẫn không phải functional interface. Ngược lại, cast lambda sang một **non-sealed functional subinterface** có thể hợp lệ, rồi gán kết quả cho biến kiểu sealed superinterface.

### Lỗi 3: Nghĩ rằng không dùng được lambda thì không tạo được instance

~~~java
// Minh họa hợp lệ trong phạm vi ví dụ InvalidSealedTarget,
// sau khi bỏ dòng gán lambda gây lỗi:
ClosedAction action = new DefaultAction();
System.out.println(action.apply("Java"));
~~~

Đoạn này gọi class được permits và in `default:Java`. Vấn đề chỉ nằm ở cách tạo giá trị bằng lambda với kiểu đích không hợp lệ, không nằm ở khả năng có instance của sealed interface.

### Lỗi 4: Nghĩ `permits` chặn mọi subtype gián tiếp

Nếu một sealed interface cho phép `non-sealed interface Extension` trực tiếp kế thừa, các class triển khai `Extension` có thể trở thành subtype **gián tiếp** của sealed interface. Đây chính là cơ chế ở `OpenJob`. Ngược lại, nếu tất cả các nhánh được phép đều đóng bằng `final` hoặc tiếp tục `sealed`, không có cùng mức mở rộng tự do đó.

### Lỗi 5: Nghĩ method reference khác quy tắc lambda

`String::trim` hay `System.out::println` cũng cần một functional interface type trong ngữ cảnh sử dụng. Đổi ký pháp lambda sang method reference sẽ không biến sealed interface thành kiểu đích hợp lệ.

### Lỗi 6: Gán chức năng của annotation cho từ khóa `sealed`

`@FunctionalInterface` là annotation kiểm tra hợp đồng SAM; `sealed` là một bộ sửa đổi giới hạn subtype trực tiếp. Đây là hai cơ chế ngôn ngữ khác nhau; một cái không “ưu tiên” để vô hiệu cái kia. Với sealed interface, điều kiện `@FunctionalInterface` đơn giản là không được đáp ứng.

### Lỗi 7: Cho rằng Java 8 hỗ trợ các ví dụ `sealed`

`sealed`, `non-sealed` và `permits` trở thành tính năng chuẩn trong Java 17. Các chương trình chạy trong bài được thiết kế cho JDK 17+; nếu dùng JDK 8 hoặc 11 thì lỗi cú pháp xuất phát từ phiên bản ngôn ngữ, không phải riêng quy tắc lambda.

## 9. Khi nào nên chọn từng cách thiết kế?

**Chọn interface functional bình thường** khi nhiệm vụ chính là truyền hành vi/callback và bạn muốn caller dễ dàng cung cấp lambda. Có thể gắn `@FunctionalInterface` để buộc compiler bảo vệ hợp đồng.

**Chọn sealed hierarchy** khi nghiệp vụ cần kiểm soát các *loại đối tượng trực tiếp* trong phân cấp và tổ chức logic theo các nhánh đã biết. Cần triển khai class theo phân cấp; lambda nhắm thẳng vào root sealed không phù hợp.

**Chọn sealed root + permitted `non-sealed` functional subinterface** khi domain cho phép một nhánh mở rộng tùy ý nhưng các nhánh trực tiếp của root vẫn phải được công bố. Đây là cách dùng lambda trực tiếp cho nhánh mở.

**Chọn sealed root + permitted concrete adapter** khi bạn muốn giữ danh sách kiểu trực tiếp đóng nhưng muốn tùy chỉnh logic xử lý bằng `Function`, `Predicate`, `IntUnaryOperator` hoặc một functional interface riêng. Đây là cách ghép mục đích quản lý kiểu với mục đích cấu hình hành vi mà không lẫn hai hợp đồng.

Trước khi chọn, nên trả lời hai câu hỏi riêng biệt: “Tôi muốn giới hạn **kiểu con** nào?” và “Tôi muốn người gọi truyền **hành vi** nào?”. Nếu chỉ cần hành vi, sealed có thể là một ràng buộc không cần thiết. Nếu domain yêu cầu tập loại đối tượng hữu hạn, các class/factory tường minh thường làm invariant dễ kiểm tra hơn.

## 10. Bài tập tự kiểm tra

1. Một `sealed interface` chỉ có `void run();`, không có phương thức khác. Có thể gán `() -> {}` trực tiếp cho kiểu đó không? Điều kiện nào bị thiếu?
2. Vì sao `@FunctionalInterface` không thể làm khai báo `sealed interface` hợp lệ thành kiểu đích?
3. Với `sealed interface Root permits Extension` và `non-sealed interface Extension extends Root` kế thừa một SAM, biểu thức `Extension e = () -> {}; Root r = e;` có hợp lệ không? Chỉ ra kiểu đích khi lambda được tạo.
4. Nếu `Root` chỉ permits một class `final`, cách nào cho phép người gọi cấu hình hành vi bằng lambda mà vẫn giữ root sealed?
5. Vì sao thay `() -> ...` bằng `SomeType::method` không giải quyết việc kiểu đích sealed?
6. Nếu xóa `sealed` khỏi root nhưng giữ hai abstract methods khác nhau, lambda có hợp lệ không?

**Đáp án gợi ý:** (1) Không: `sealed` loại kiểu đó khỏi định nghĩa functional interface. (2) Annotation chỉ kiểm tra, không thay đổi định nghĩa. (3) Có, nếu `Extension` đúng một SAM; lambda có kiểu đích `Extension` rồi upcast sang `Root`. (4) Dùng permitted class có constructor/factory nhận functional interface làm strategy. (5) Method reference cũng cần functional interface type. (6) Không: vẫn thiếu điều kiện một SAM.

## 11. Nguồn đặc tả để đối chiếu

- [JLS Java SE 17, `9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8): định nghĩa functional interface bao gồm điều kiện không khai báo `sealed`.
- [JLS Java SE 17, `15.27.3 — Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.3): điều kiện tương thích giữa lambda và target functional interface type.
- [JLS Java SE 17, `9.1.1.4 — sealed and non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): các quy tắc về nhánh kế thừa trực tiếp của sealed interface.

**Ghi nhớ:** “Đúng một SAM” chưa đủ. **Sealed interface không bao giờ là functional interface**, nên không thể làm kiểu đích trực tiếp của lambda hay method reference. Java vẫn cho phép dùng lambda bên trong một thiết kế sealed qua **permitted non-sealed functional subinterface** hoặc **functional interface được truyền vào permitted class**.