# Ảnh hưởng của phương thức riêng, phương thức tĩnh và thành phần không thể ghi đè trong AOP qua proxy

> **Mục tiêu học tập:** Hiểu vì sao khả năng can thiệp bằng proxy trong Aspect-Oriented Programming (AOP) phụ thuộc cơ chế dispatch và ranh giới lời gọi; phân biệt **proxy dựa trên giao diện**, **proxy dựa trên lớp con** và **weaving trực tiếp mã**; xác định ảnh hưởng của phương thức `private`, `static`, `final`, lớp `final`, constructor, lời gọi nội bộ và những thành phần không thể override. Từ đó thiết kế pointcut, advice và phép kiểm thử phù hợp, tránh các khẳng định sai kiểu “AOP luôn chặn được” hoặc “AOP không bao giờ chặn được”.

## 1. Tình huống mở đầu: cùng một phương thức nhưng cách gọi khác nhau

Giả sử có một đối tượng thực thi thao tác ghi dữ liệu. Ta muốn thêm advice đo thời gian bằng **proxy**.

~~~text
Client ──> Proxy ──> Target.save(...)
            |
            +── before / after / around
~~~

Nếu client gọi `proxy.save(...)`, lời gọi đi qua ranh giới can thiệp. Nhưng nếu ở một nơi khác client giữ `target` và gọi thẳng `target.save(...)`, cùng phương thức nghiệp vụ có thể chạy **không qua advice của proxy**.

Tình huống phức tạp hơn khi phương thức đích là `final`, có một helper `private`, hoặc gọi một phương thức `static`. Ba đặc điểm này liên quan đến **quy tắc ghi đè/dispatch của Java**, nhưng ảnh hưởng của chúng lên AOP **khác nhau theo loại proxy**.

Ta sẽ phân biệt:

- **Interface proxy:** trung gian triển khai một giao diện; handler nhận lời gọi interface từ client.
- **Subclass proxy:** trung gian là lớp con, can thiệp chủ yếu bằng cách override các phương thức đủ điều kiện.
- **Bytecode weaving:** thay đổi các vị trí mã đã được mô hình join point cho phép; không nhất thiết phụ thuộc vào khả năng override của phương thức.

Điểm quan trọng: một phương thức `final` **không thể bị lớp con override**, nhưng **có thể được gọi qua interface proxy**. Một lời gọi `private` **không phải phương thức có thể override**, nhưng một bộ dệt method execution phù hợp **có thể có khả năng** quan sát nó. Vì thế phải nói rõ **cơ chế**, **điểm can thiệp** và **đường thực thi**.

## 2. Ba câu hỏi trước khi xét modifier

Trong AOP, **join point** là vị trí có thể can thiệp, **pointcut** chọn vị trí và **advice** là hành vi bổ sung. Một **proxy/interceptor** chặn lời gọi tại ranh giới đối tượng; một **weaver** có thể chèn hành vi tại các điểm của mã nếu loại join point được hỗ trợ. Khả năng đọc metadata bằng Reflection không đồng nghĩa khả năng chặn thực thi.

Trước khi nói method `private`, `static` hoặc `final` “không được AOP hỗ trợ”, cần kiểm tra:

1. **Chọn điểm gì?** Lời gọi interface, method execution, constructor hay field access?
2. **Can thiệp bằng cách nào?** Interface delegation, subclass override hay bytecode weaving?
3. **Đường thực thi có tới đó không?** Caller dùng proxy hay target thô, receiver nào thực thi, class có thuộc phạm vi instrumentation không?

Câu trả lời theo ba tầng sẽ phân biệt được **không thể override**, **không được proxy expose** và **không được weaving chọn** — ba nguyên nhân khác nhau.

## 3. Interface proxy hoạt động theo hợp đồng giao diện

Một interface proxy được tạo để triển khai một hoặc nhiều **giao diện** và cung cấp một đối tượng trung gian. Đối với Java Dynamic Proxy, các lời gọi instance method của những giao diện được proxy triển khai có thể đi qua `InvocationHandler`.

Mô hình:

~~~text
interface Worker {
    void execute();
}

class WorkerImpl implements Worker {
    public void execute() { ... }
}

caller ───> (Worker) proxy ──> InvocationHandler ──> WorkerImpl.execute()
~~~

*Đây là cấu trúc mô tả, không phải một tệp Java hoàn chỉnh.*

Điều kiện quan trọng:

- Caller phải **gọi qua tham chiếu proxy** được cung cấp.
- Phương thức cần chặn nằm trong **hợp đồng instance method của giao diện** mà proxy triển khai, hoặc thuộc những method được cơ chế proxy xử lý đặc biệt.
- Handler có thể tiếp tục tới target, short-circuit hoặc xử lý lỗi theo hợp đồng.
- Việc target dùng một lớp `final` **không ngăn proxy giao diện đứng phía trước nó**, vì proxy không cần kế thừa lớp target.

### 3.1. Proxy giao diện không đồng nghĩa proxy của mọi method trên target

Target có thể có method không khai báo trong giao diện:

~~~java
final class WorkerImpl implements Worker {
    public void execute() { /* ... */ }
    public void maintenanceOnly() { /* ... */ }
}
~~~

Đây là mã minh họa. Caller với biến kiểu `Worker` không tự có quyền gọi `maintenanceOnly()`; một `java.lang.reflect.Proxy` triển khai `Worker` cũng **không tự mang method đó**.

Một lớp đích có thể chứa rất nhiều method, nhưng proxy giao diện chỉ đứng trên **bề mặt được giao diện và cơ chế proxy cung cấp**.

## 4. Subclass proxy dựa trên khả năng ghi đè

Một dạng proxy khác tạo hoặc sử dụng **lớp con** của lớp đích. Lớp con override một phương thức có thể ghi đè để thêm hành vi rồi chuyển tiếp về phần cài đặt của lớp cha.

~~~text
TargetClass
   ^
   |
TargetProxySubclass
   |
   +── override execute() {
           before();
           result = super.execute();
           after();
           return result;
       }
~~~

Điều này dựa trên **quy tắc override của Java**. Vì thế:

- **`private` method** không thể được override bởi lớp con.
- **`static` method** không được override đa hình; khai báo trùng tên có thể là *method hiding*, không phải interception theo virtual dispatch.
- **`final` method** không cho phép override.
- **`final` class** không cho phép kế thừa, nên không tạo subclass của chính lớp ấy bằng cách thông thường.
- Constructor không phải là method được kế thừa/override.

**Cần phân biệt** một phương thức của lớp cha có modifier `final` với một phương thức của interface được triển khai bằng method `final` ở target. Interface proxy chặn ở lớp trung gian **trước khi gọi target**; subclass proxy phải override chính phương thức target nếu muốn chặn trực tiếp đường dispatch tương ứng.

### 4.1. Vì sao không thể suy từ “final” sang “không thể AOP”?

`final` hạn chế **override**; nó không tự cấm một đoạn code khác gọi một phương thức, không cấm tạo một đối tượng proxy **triển khai giao diện**, và không tự loại mọi khả năng bytecode weaving.

Một công cụ dệt bytecode vào thân phương thức hoặc call site phù hợp có thể hoạt động theo cơ chế **không phải subclass override**, nếu join point model và giới hạn runtime cho phép.

Nhận định đúng phải có phạm vi:

> “Subclass proxy không thể override một instance method `final`; interface proxy vẫn có thể chặn lời gọi interface tới target có method implementation `final`.”

## 5. Phương thức `private`: không được override và không là API của proxy giao diện

Trong Java, thành viên `private` thuộc phạm vi truy cập riêng của lớp khai báo. Lớp con không override `private` method của lớp cha. Nếu một lớp con tự khai báo method cùng tên/chữ ký, đó là một thành viên độc lập theo ngôn ngữ, không phải override method private của lớp cha.

Ví dụ:

~~~java
class Base {
    private void check() {
        System.out.println("Base private");
    }

    public void run() {
        check();
    }
}

class Child extends Base {
    public void check() {
        System.out.println("Child public");
    }
}
~~~

*Đoạn mã minh họa quy tắc Java, có thể đặt vào tệp đầy đủ khi chạy.*

Lời gọi `check()` trong thân `Base.run()` vẫn tham chiếu phần private của `Base`, không tự dispatch đến `Child.check()`. Vì vậy không thể “override check” để chặn phần helper này bằng một subclass proxy.

### 5.1. Điều gì vẫn có thể quan sát?

Nếu caller gọi `proxy.run()`, advice ở ranh giới `run()` có thể chạy **trước và sau toàn bộ hoạt động**, bao gồm phần private helper đã được thực thi bên trong. Nhưng điều đó khác với một **join point độc lập** tại `check()`.

Để có advice riêng quanh `check()`, cần một mô hình và cơ chế có khả năng quan sát vị trí **method execution/call** thích hợp, không chỉ một proxy giao diện.

### 5.2. Private method và reflection

Java Reflection có thể tìm metadata của `private` method qua `getDeclaredMethod`. Tuy nhiên:

- Tìm thấy `Method` **không đồng nghĩa** proxy có một đường can thiệp tới mọi lời gọi.
- Việc thực sự invoke một private member còn chịu kiểm soát access và module.
- Tự dùng reflection để gọi helper là **một lời gọi mới**, không phải cách thay thế `proceed` ở join point hiện tại.

Không được coi reflection là giải pháp tự động phá mọi giới hạn proxy.

## 6. Phương thức `static`: method hiding khác với override

Một `static` method gắn với kiểu khai báo và được gọi theo cơ chế không giống virtual dispatch của instance method. Method `static` không được **override đa hình**.

Ví dụ minh họa:

~~~java
class Parent {
    static String label() {
        return "Parent";
    }
}

class Child extends Parent {
    static String label() {
        return "Child";
    }
}
~~~

Đây là *method hiding*. Những lời gọi sử dụng tên class tương ứng có thể chọn method khác nhau theo quy tắc giải quyết của Java; không có lời gọi override đa hình đến subclass handler chỉ vì object runtime thuộc `Child`.

### 6.1. Static method không đi qua Java Dynamic Proxy giao diện

Một static method khai báo trên interface **không phải instance method được implement/override** bởi proxy. Ví dụ `Tool.version()` được gọi trên tên interface, không qua tham chiếu `proxy`.

Một static method trên class target cũng không đi qua handler chỉ vì class ấy có một proxy cho các instance method khác.

### 6.2. Nhưng weaving bytecode có thể khác

Nếu AOP có join point model hỗ trợ **method call hoặc method execution cho static method** và weaver xử lý mã tương ứng, có thể có cơ chế quan sát. Sự bất khả của **subclass override** không phải sự bất khả của **mọi cách weaving**.

Cần nêu rành mạch: “không thể can thiệp static theo *cơ chế override subclass*” khác “mô hình AOP này không hỗ trợ static method join point”.

## 7. `final` method: giới hạn riêng của kế thừa

Một `final` instance method không cho lớp con override. Vì thế, một **subclass proxy dựa trên override** không thể chèn advice bằng cách tạo bản override cho chính method đó.

~~~java
class BaseService {
    public final String calculate() {
        return "done";
    }
}
~~~

Nếu một subclass khai báo lại `calculate()` với cùng chữ ký nhằm override, Java từ chối khi biên dịch. Một bộ sinh subclass hợp lệ cũng phải tôn trọng quy tắc này.

Tuy nhiên:

- Một interface proxy chặn **lời gọi đi vào qua giao diện** trước khi gọi `BaseService.calculate()`, nếu method là hiện thực của hợp đồng interface.
- Một weaver mã có thể có loại join point khác không dựa trên override.
- Một method `final` vẫn có thể **được gọi bình thường**; hạn chế nằm ở cách đặt interception.

**Không được đồng nhất `final method` với `method không bao giờ được quan sát`.**

### 7.1. `final` không nói gì về việc policy đã chạy

Ngay cả với method không-final, proxy chỉ chạy khi caller đi đúng đường. Tính override được là **điều kiện khả năng** của subclass proxy, không phải bằng chứng rằng mọi invocation đều qua proxy.

## 8. `final` class và những thành phần không thể tạo subclass

Khai báo `final class` chặn kế thừa class đó. Một dạng proxy tạo subclass của chính target không thể dùng cách ấy để bao một class `final` bằng subclass.

Những cấu trúc Java khác cũng cần chú ý:

- **Record class** là final theo ngữ nghĩa của Java; không thể tạo lớp con của record như một target subclass tùy ý.
- **Enum class** có mô hình kế thừa đặc biệt và không phải lớp target thông thường để subclass proxy.
- **Sealed class** hạn chế những lớp con được phép; một lớp con sinh động không nằm trong danh sách được phép có thể không được chấp nhận.
- **Sealed interface** cũng không phải một giao diện tự do cho mọi lớp proxy sinh động triển khai; Java Dynamic Proxy tiêu chuẩn không chấp nhận tạo proxy trực tiếp cho sealed interface.
- **Constructor** không được kế thừa và override.
- **Field** không là method có thể override; field hiding không phải method dispatch.

### 8.1. Lớp final vẫn có thể đứng sau interface proxy

Nếu `final class PaymentImpl implements Payment`, một proxy triển khai interface `Payment` vẫn có thể chuyển lời gọi đến `PaymentImpl`.

Quan hệ:

~~~text
Payment interface
      ^
      | implemented by
   Proxy             final PaymentImpl
      |                      ^
      +---- delegates ------+
~~~

Proxy **không kế thừa `PaymentImpl`**. Vì thế cấm kế thừa target không tác động trực tiếp lên khả năng tạo đối tượng proxy giao diện.

Điều kiện là API cần chặn thực sự có thể đi qua **giao diện không bị hạn chế tương ứng** và caller sử dụng proxy thay cho target.

## 9. Bảng phân biệt theo cơ chế

| Thành phần / tình huống | Interface proxy | Subclass proxy dựa trên override | Bytecode weaving với mô hình phù hợp |
|---|---|---|---|
| Public instance method khai báo trong interface | Có thể chặn khi caller đi qua proxy | Có thể nếu override hợp lệ | Có thể nếu điểm/mã thuộc phạm vi dệt |
| Target method `final` triển khai interface | **Có thể chặn ở proxy giao diện** | Không thể override method `final` | Có thể nếu model/weaver hỗ trợ |
| Helper `private` bên trong target | Không có interception riêng qua interface proxy | Không thể override | Có thể nếu pointcut/weaving hỗ trợ private method join point |
| `static` method | Không đi qua instance interface proxy | Không override; có thể method hiding | Có thể nếu model/weaver hỗ trợ static join point |
| Target `final class` có interface phù hợp | **Có thể** tạo proxy giao diện | Không thể subclass target | Có thể tùy phạm vi và hạn chế mã |
| Target class không có interface phù hợp | Java Dynamic Proxy giao diện không áp dụng trực tiếp | Có thể nếu target cho kế thừa/override | Có thể theo loại điểm được hỗ trợ |
| Constructor call/execution | Không tự chặn bằng method proxy | Constructor không override | Có thể ở một số join point models |
| Field get/set trực tiếp | Không tự chặn | Field không override | Có thể nếu có field access join points |
| Lời gọi nội bộ `this.other()` | Không tự quay qua proxy | Tùy virtual dispatch của method đủ điều kiện override | Có thể nếu execution/call site đã dệt |
| Gọi trực tiếp target từ bên ngoài | Không đi qua handler | Có thể bypass nếu dùng object target gốc | Tùy vị trí mã thực sự đã dệt |

**Cột weaving là khả năng có điều kiện, không phải cam kết mọi hệ AOP đều hỗ trợ tất cả hàng.** Một công cụ có thể chỉ hỗ trợ một phần điểm, dù dùng bytecode instrumentation.

## 10. Chương trình Java 17 số 1: interface proxy chặn được target `final`

Ví dụ này cố ý dùng một **lớp target final** chứa **method implementation final**, bên cạnh helper `private` và `static`. Chương trình chứng minh interface proxy **vẫn chặn được lời gọi giao diện đến method final**, trong khi helper private/static không tự trở thành lời gọi qua handler.

**Đây là Java Dynamic Proxy chuẩn, minh họa interception qua giao diện; không phải một engine weaving AOP tổng quát.**

Tạo tệp `InterfaceProxyLimitsDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class InterfaceProxyLimitsDemo {
    interface Work {
        String execute(String id);
        String state();
    }

    static final class FinalWorker implements Work {
        private int count = 0;

        @Override
        public final String execute(String id) {
            System.out.println("[target] execute " + id);
            privateStep(id);
            count++;
            return "done-" + id;
        }

        @Override
        public String state() {
            return "count=" + count;
        }

        private void privateStep(String id) {
            System.out.println("[target] private step " + id);
        }

        static String staticStep() {
            System.out.println("[target] static step");
            return "STATIC";
        }
    }

    public static void main(String[] args) {
        FinalWorker target = new FinalWorker();

        Work proxy = (Work) Proxy.newProxyInstance(
                Work.class.getClassLoader(),
                new Class<?>[] {Work.class},
                (proxyObject, method, arguments) -> {
                    System.out.println("[proxy] " + method.getName());
                    try {
                        return method.invoke(target, arguments);
                    } catch (InvocationTargetException wrapped) {
                        throw wrapped.getCause();
                    }
                }
        );

        System.out.println("-- via interface proxy --");
        System.out.println("[caller] " + proxy.execute("A"));
        System.out.println("[caller] " + proxy.state());

        System.out.println("-- direct target --");
        System.out.println("[caller] " + target.execute("B"));

        System.out.println("-- static method --");
        System.out.println("[caller] " + FinalWorker.staticStep());
    }
}
~~~

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac InterfaceProxyLimitsDemo.java
java InterfaceProxyLimitsDemo
~~~

**Stdout:**

~~~text
-- via interface proxy --
[proxy] execute
[target] execute A
[target] private step A
[caller] done-A
[proxy] state
[caller] count=1
-- direct target --
[target] execute B
[target] private step B
[caller] done-B
-- static method --
[target] static step
[caller] STATIC
~~~

### 10.1. Điều gì đã được chứng minh?

- `FinalWorker` là **final class** nên không thể được subclass.
- `execute` là **final instance method** nên cũng không thể override.
- Nhưng `Work` là một interface bình thường; `proxy.execute("A")` vẫn đi qua `InvocationHandler` trước khi handler gọi method trên target.
- `privateStep` chạy bên trong target nhưng **không có một dòng `[proxy] privateStep`**; nó không là method của giao diện.
- `FinalWorker.staticStep()` được gọi bằng class, **không đi qua đối tượng proxy**.
- Lời gọi `target.execute("B")` từ caller đi thẳng target, không in `[proxy] execute`.

Như vậy `final` có ảnh hưởng rất khác nhau đối với **subclass proxy** và **interface proxy**. Nếu một lời gọi bị bỏ sót, phải kiểm tra **tham chiếu mà caller dùng**, không chỉ modifier của method.

### 10.2. Giới hạn của ví dụ

Handler dùng `Method.invoke` để chuyển tiếp. Nếu method đích ném lỗi, reflection có thể bọc nó trong `InvocationTargetException`; đoạn handler giải bọc để giữ nguyên nhân gốc. Các chính sách khác như đổi đối số, retry hoặc đo thời gian không được triển khai ở đây.

Java Dynamic Proxy tiêu chuẩn chỉ cung cấp một cách chặn cụ thể. Nó không sửa thân `FinalWorker.execute`, không chặn constructor hay biến một private method thành public join point.

## 11. Chương trình Java 17 số 2: lớp con không thể override `private`/`static`/`final`

Ví dụ dưới đây mô phỏng ý tưởng **subclass proxy** bằng một lớp con viết thủ công. Nó override **chỉ** method `open` được phép override.

Lưu file `SubclassOverrideLimitsDemo.java`:

~~~java
public class SubclassOverrideLimitsDemo {
    static class Base {
        public String open(String name) {
            System.out.println("[base] open " + name);
            privateStep(name);
            return "open-" + name;
        }

        public final String fixed(String name) {
            System.out.println("[base] final " + name);
            return "fixed-" + name;
        }

        private void privateStep(String name) {
            System.out.println("[base] private " + name);
        }

        public static String utility() {
            System.out.println("[base] static");
            return "static-result";
        }
    }

    static final class InterceptingSubclass extends Base {
        @Override
        public String open(String name) {
            System.out.println("[subclass advice] before open");
            String result = super.open(name);
            System.out.println("[subclass advice] after open");
            return result;
        }
    }

    public static void main(String[] args) {
        Base proxyLike = new InterceptingSubclass();

        System.out.println("[caller] " + proxyLike.open("X"));
        System.out.println("[caller] " + proxyLike.fixed("Y"));
        System.out.println("[caller] " + Base.utility());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SubclassOverrideLimitsDemo.java
java SubclassOverrideLimitsDemo
~~~

**Stdout:**

~~~text
[subclass advice] before open
[base] open X
[base] private X
[subclass advice] after open
[caller] open-X
[base] final Y
[caller] fixed-Y
[base] static
[caller] static-result
~~~

### 11.1. Vì sao chỉ `open` có dòng advice?

`InterceptingSubclass` override được `Base.open` và đặt các lệnh “before/after” quanh `super.open`. Đây là điểm có thể dùng cơ chế **virtual override**.

`Base.fixed` là `final`; lớp con kế thừa nhưng **không thể override** để thêm hành vi vào chính method ấy. Vì vậy lời gọi `proxyLike.fixed("Y")` chạy vào implementation đã thừa kế, không có dòng `[subclass advice]`.

`privateStep` của `Base` không bị override; khi `Base.open` gọi helper đó, nó chạy body của `Base`. `Base.utility` là `static`, không có virtual dispatch vào `InterceptingSubclass`.

### 11.2. Đừng nhầm lớp con viết tay với weaver tự động

Chương trình này chỉ **minh họa quy tắc override** bằng Java thuần, không định nghĩa pointcut, không tự tạo proxy và không có weaving engine. Trong một hệ AOP thực, cơ chế tạo subclass có thể phát sinh mã bao quanh hoặc dùng các chiến lược khác tùy khả năng runtime.

Nếu muốn chặn `fixed`, cần một **ranh giới khác**: ví dụ interface proxy đứng ngoài lời gọi nếu target triển khai giao diện phù hợp, hoặc một mô hình weaving có hỗ trợ join point thích hợp. Không thể khắc phục giới hạn Java override bằng cách đổi tên method và vẫn gọi đó là override.

## 12. Những trường hợp Java cố ý không cho biên dịch

Các ví dụ sau chỉ nhằm hiểu quy tắc ngôn ngữ; **không ghép chúng vào hai tệp Java chạy được ở trên**.

### 12.1. Kế thừa một final class

~~~java
final class LockedType {}

class BadSubclass extends LockedType {}
~~~

Compiler từ chối vì `LockedType` không được kế thừa.

### 12.2. Override một final method

~~~java
class LockedMethod {
    public final void execute() {}
}

class BadOverride extends LockedMethod {
    @Override
    public void execute() {}
}
~~~

Compiler từ chối phương thức override `final`.

### 12.3. Dùng `@Override` cho static method

~~~java
class StaticBase {
    public static void run() {}
}

class BadStatic extends StaticBase {
    @Override
    public static void run() {}
}
~~~

Phương thức `static` không được override; `@Override` ở đây không hợp lệ. Nếu bỏ annotation và đáp ứng các điều kiện ngôn ngữ, khai báo trùng tên có thể là *method hiding* chứ không là đa hình instance.

### 12.4. Cố override private method

~~~java
class PrivateBase {
    private void act() {}
}

class MisleadingChild extends PrivateBase {
    @Override
    public void act() {}
}
~~~

Trong ví dụ, private method không được kế thừa như method có thể override, nên `@Override` không hợp lệ. Nếu bỏ annotation, method `act` trong lớp con không tự trở thành interceptor cho body private của lớp cha.

**Các lỗi trên là lỗi compile Java**, không phải bằng chứng có một pointcut AOP sai.

## 13. Self-invocation: cùng đối tượng gọi method của nó

Xét:

~~~java
interface Billing {
    void checkout();
    void charge();
}

class BillingImpl implements Billing {
    public void checkout() {
        charge();
    }

    public void charge() {
        // business logic
    }
}
~~~

Đây là mảnh Java minh họa.

Với **interface proxy** đứng trước `BillingImpl`, caller gọi `proxy.checkout()`. Handler có thể can thiệp `checkout` rồi chuyển tới `target.checkout()`. Bên trong `target.checkout()`, lời gọi `charge()` đi trực tiếp trên target, không tự đi qua proxy.

Kết quả có thể là advice cho `checkout` chạy, còn advice riêng dự kiến cho `charge` **không chạy ở self-invocation này**.

### 13.1. Subclass proxy có thể khác ở lời gọi virtual

Với subclass proxy, nếu method đang chạy thực sự nằm trên một **instance của lớp proxy** và gọi một virtual method có thể override, virtual dispatch có thể quay tới override của lớp proxy. Vì thế không thể khẳng định “self-invocation luôn bỏ qua mọi proxy”.

Nhưng nếu lời gọi là `private`, `static`, `final`, một lời gọi `super.method()` cụ thể, hoặc một đường gọi vào target khác nằm ngoài instance proxy, kết quả khác.

**Phân tích theo bytecode/dispatch và đối tượng runtime**, không theo tên gọi self-invocation đơn thuần.

### 13.2. Khả năng chặn ở method execution weaving

Nếu một công cụ weaving sửa chính phần thân của `charge` để có hook ở method execution, lời gọi bên trong lớp đích có thể được quan sát **nếu method body được dệt và thực sự chạy**. Không có điều kiện bắt buộc lời gọi phải quay qua proxy giao diện.

Điều này thể hiện sự khác nhau giữa can thiệp **ở ranh giới đối tượng** và can thiệp **ở vị trí mã thực thi**.

## 14. Method call và method execution: vị trí dệt quyết định độ bao phủ

Trong một số mô hình AOP có hai loại điểm:

- **Method call join point:** hoạt động lời gọi tại **vị trí caller**.
- **Method execution join point:** hoạt động khi **thân method đích** được thực thi.

Một proxy giao diện thường hoạt động như **interception ở ranh giới lời gọi qua proxy**, không thể tự suy rằng nó cung cấp đúng toàn bộ semantics của hai loại join point trên.

Ví dụ:

~~~text
Caller A  ─┐
           ├──> Worker.run() body
Caller B  ─┘
~~~

Nếu chỉ một caller đi qua proxy, handler có thể không thấy lời gọi kia. Nếu method body được weaving với method-execution advice phù hợp, cả hai đường có thể được quan sát khi thực sự đi vào thân đã dệt.

Ngược lại, một call-site weaving trong **Caller A** không tự chặn call site ở **Caller B** nếu Caller B chưa được dệt.

Điểm can thiệp “method `run`” cần được mô tả thêm bằng **vị trí**: ở caller, ở proxy hoặc ở thân method.

## 15. Constructor không phải phương thức để override

Constructor của Java không được kế thừa như method và không được override. Khi `new Target()` chạy, một instance của target được khởi tạo. Một proxy được dựng **sau đó** để đứng trước target không thể quay ngược thời gian mà chặn mọi câu lệnh bên trong constructor đã hoàn tất.

Với subclass proxy, việc tạo đối tượng lớp con cũng liên quan quy tắc gọi constructor của lớp cha; một phương thức override được gọi quá sớm từ constructor có thể quan sát trạng thái lớp con **chưa khởi tạo đầy đủ**.

Những lưu ý:

- Interface proxy không tự cung cấp constructor join point.
- Subclass proxy không thể “override constructor”.
- Một số mô hình weaving có thể có constructor call/execution hoặc initialization join points, nhưng các điểm đó có semantics riêng.
- Advice trong giai đoạn khởi tạo phải thận trọng với `this` escaping, virtual dispatch và bất biến đối tượng.

Không đặt kỳ vọng “mọi new đều được AOP quan sát” nếu cơ chế thực tế chỉ có method interceptor.

## 16. Field và accessor: truy cập trực tiếp không phải gọi phương thức

Ví dụ:

~~~java
class Account {
    private int balance;

    public int getBalance() {
        return balance;
    }
}
~~~

Đây là đoạn khai báo minh họa.

Một interface/subclass proxy có thể chặn lời gọi `getBalance()` nếu nằm trong phạm vi và method đủ điều kiện. Nhưng thao tác truy cập trường `balance` **bên trong body** không tự trở thành một lời gọi interface method.

Nếu code khác đọc/ghi field trực tiếp theo quyền truy cập Java, thao tác ấy cũng không đi qua một proxy method thông thường.

Một số mô hình weaving cung cấp join point **field get/set**, nhưng không phải mọi cơ chế proxy có được khả năng đó. Ngoài ra, “field read/write” ở mức bytecode không mặc nhiên bao phủ mọi sự thay đổi trạng thái do reflection, native code hoặc hệ thống ngoài gây ra.

## 17. Default method của interface và private method trong interface

Từ Java 8, interface có thể khai báo **default method**; từ Java 9, interface có thể có **private method** phục vụ tái sử dụng logic bên trong interface.

Với Java Dynamic Proxy:

- Một **default method** là instance method của interface, nên lời gọi tương ứng **có thể tới `InvocationHandler`**.
- Handler phải quyết định cách thực thi tiếp theo: gọi implementation trên target, hoặc dùng cơ chế invoke default phù hợp do Java cung cấp.
- Một **private interface method** không phải API mà caller bên ngoài có thể gọi qua proxy như một public method giao diện.
- Một **static interface method** cũng không là lời gọi instance method qua proxy.

Đừng suy rằng “default method thì luôn chặn được mọi lời gọi nội bộ do nó thực hiện”. Các lời gọi tới helper private hoặc tới method khác bên trong mặc định có ranh giới dispatch riêng.

### 17.1. Khi target có implementation của default method

Nếu target override default method hoặc kế thừa implementation mặc định, việc handler dùng reflection gọi `method.invoke(target, args)` có thể dẫn tới implementation phù hợp trên **target**, không giống việc tự động gọi bản default của **proxy**.

Một số API Java hỗ trợ gọi cụ thể default method qua `InvocationHandler.invokeDefault` trong những điều kiện phù hợp. Đây là một API của JDK, không phải quy tắc chung của mọi engine AOP; cần kiểm tra hành vi cần đạt khi thiết kế handler.

## 18. Object methods và các phương thức đặc biệt

Với Java Dynamic Proxy, các method như `equals(Object)`, `hashCode()` và `toString()` có cơ chế dispatch tới handler theo hợp đồng proxy. Điều đó cần được xử lý có chủ đích.

Ví dụ một handler dùng `proxy.toString()` ngay trong `invoke` để ghi log có thể kích hoạt `invoke` lần nữa, gây **recursion** nếu không cẩn thận.

Ngược lại, những method `final` của `Object` như `getClass()` không được proxy override theo cách instance interface method thông thường.

### 18.1. Không đánh đồng identity proxy với identity target

`proxy == target` thường sai vì đó là hai đối tượng khác nhau. Việc `equals`, `hashCode` và `toString` có thể bị handler xử lý có nghĩa định danh, map key và log output có thể khác target.

Nếu code bên ngoài ép kiểu sang class implementation `FinalWorker`, một Java Dynamic Proxy chỉ triển khai `Work` **không tự là instance của FinalWorker**. Đây là ràng buộc type của API: không thể lấy interface proxy làm một đối tượng subtype của target final class.

**Thiết kế nên dựa trên interface phù hợp** nếu muốn ranh giới interface proxy thay thế được target trong những đường gọi chủ đích.

## 19. Modifier `final` và Java record/sealed types: đánh giá từng trường hợp

Nhu cầu dùng record, sealed type hoặc đối tượng bất biến không có nghĩa phải bỏ AOP, nhưng ảnh hưởng lên loại proxy.

### 19.1. Record

Record là class final. Không thể tạo subclass của record, nhưng record vẫn có thể **triển khai một interface bình thường**. Nếu có lời gọi instance method qua một interface proxy phù hợp, cơ chế ấy có thể đứng trước record.

### 19.2. Sealed class

Một sealed class liệt kê/giới hạn các subclass được phép. Một subclass sinh động không được phép theo quy tắc sealed không thể tự nhiên trở thành subclass proxy của sealed class đó. Đây là một ràng buộc **của cơ chế kế thừa**, không phải cấm weaving thân method trong mọi hoàn cảnh.

### 19.3. Sealed interface

Java Dynamic Proxy tiêu chuẩn có ràng buộc: không tạo proxy trực tiếp implement **sealed interface**. Nếu thiết kế API yêu cầu sealed interface cho một miền kiểu đóng, cần cân nhắc một ranh giới can thiệp khác thay vì mặc định interface proxy như với giao diện không sealed.

### 19.4. Kiểu bất biến

Một lớp immutable có thể là final; nếu vẫn cần quan sát giao diện ngoài của nó, interface proxy có thể phù hợp. Nhưng một policy chỉ quan sát thường không nên sửa đối tượng bất biến hoặc tìm cách chặn mọi truy cập field để thay đổi semantics của class.

## 20. Access modifier và tính hiển thị của API

Không chỉ có `private` và `public`. Java còn có **protected** và **package-private**; khả năng override/hợp lệ phụ thuộc phạm vi truy cập, package, class loader và cấu trúc kế thừa.

Một subclass proxy sinh động thường phải tuân thủ:

- Có được tạo subclass hợp lệ của target?
- Có constructor hợp lệ để khởi tạo subclass?
- Method muốn override có hiển thị cho subclass trong ngữ cảnh đó?
- Có dùng đúng package/module access không?
- Method có modifier cấm override không?
- Phần code có chạy trong đúng class loader/module?

Một method `protected` **có thể override** trong một số điều kiện hợp lệ; method `private` thì không. Package-private cũng có điều kiện package và runtime package riêng.

**Đừng suy rằng mọi method không-public đều như nhau.** Những quy tắc Java về kế thừa và truy cập khác nhau theo modifier và môi trường tạo subclass.

## 21. Module, class loader và class identity

Trên JVM hiện đại, **Java Platform Module System (JPMS)** giới hạn các kiểu truy cập và khả năng tạo/đọc metadata trong những module khác nhau.

Một proxy/interceptor có thể gặp những vấn đề như:

- Interface không có khả năng truy cập hợp lệ trong loader/module mong muốn.
- Một module không mở package cho một phép reflection cần thiết.
- Class target và class proxy ở những module/loader khác nhau.
- Một kiểu cùng tên được nạp qua nhiều class loader nhưng **không cùng runtime identity**.
- Mã sinh subclass không thể thỏa quy tắc package/private/protected access như dự kiến.

Không nên nhầm:

- **Compiler chấp nhận source**.
- **Proxy generator tạo được class trung gian**.
- **Handler có thể gọi target hợp lệ bằng reflection**.
- **Caller có thể cast và gọi object trung gian**.

Đó là các tầng riêng, có thể lỗi ở những thời điểm khác nhau.

## 22. Bytecode weaving không dựa hoàn toàn vào override

Một số hình thức weaving trực tiếp **method body**, **call site** hoặc **điểm truy cập field** theo cơ chế bytecode. Khi đó việc method là `final`, `private` hoặc `static` **không tự loại khả năng can thiệp**: ràng buộc chính nằm ở **join point model, scope, bytecode hợp lệ và giới hạn công cụ**.

Nhưng cũng không được kết luận ngược rằng bytecode weaving luôn can thiệp được:

- Mọi constructor, nhất là giai đoạn object chưa khởi tạo đủ.
- Mọi native method body.
- Mọi JVM-generated method/lambda theo cùng cách.
- Mọi field access do reflection hoặc native code.
- Mọi class đã được load từ trước.
- Mọi method khi VM giới hạn retransformation/redefinition.
- Mọi điểm trên nền tảng AOT/native không có JVM instrumentation tương ứng.

Một lựa chọn kỹ thuật cần căn cứ **bộ join point được công cụ công bố**, cách weaving, phiên bản JVM và kiểm thử thực tế.

### 22.1. Tại sao không chỉ đổi proxy sang weaver để “giải quyết hết”?

Weaving có thể tăng độ bao phủ nhưng mang thêm rủi ro: tương thích bytecode, class loader, JPMS, quyền instrumentation, startup/class loading, hiệu năng và khả năng phối hợp nhiều aspect. Độ sâu can thiệp cao hơn không mặc nhiên tốt hơn cho mọi yêu cầu.

Khi một chính sách chỉ cần quan sát API công khai, một interface proxy đơn giản có thể dễ bảo trì hơn. Khi cần field/constructor/internal execution, có thể phải dùng mô hình khác hoặc thiết kế một ranh giới quan sát rõ trong nghiệp vụ.

## 23. Điểm dễ nhầm: final method trên interface proxy

Câu sau **sai nếu phát biểu không kèm phạm vi**:

> “Method được khai báo final nên AOP không thể chặn nó.”

Một instance method `final` có thể hiện thực phương thức của một giao diện. Caller dùng **interface proxy**, handler nhận lời gọi trước khi chuyển xuống method `final` của target; vậy vẫn có interception ở phía ngoài.

Điều đúng:

> “Nếu cơ chế proxy cần **override chính phương thức final** trong một subclass, nó không làm được điều đó.”

Từ đó có một nguyên tắc thiết kế: khi đánh giá modifier, **hỏi modifier ảnh hưởng tới thao tác nào** — override, dispatch, đọc metadata, weaving body hay chỉ đường vào của caller.

## 24. Khi pointcut hợp lệ nhưng advice không chạy

Những trường hợp thường xuất hiện trong AOP qua proxy:

1. Caller gọi trực tiếp target, không dùng proxy.
2. Pointcut áp dụng cho method **không có trên giao diện proxy**.
3. Subclass proxy không override được method `final`.
4. Target `final class` không thể được subclass.
5. Method `private` được gọi bên trong target, không qua proxy.
6. Method `static` được gọi trực tiếp bằng class.
7. Constructor/field operation không là loại điểm proxy hỗ trợ.
8. Một lời gọi nội bộ không đi qua ranh giới proxy đã thiết kế.
9. Một advice bao ngoài short-circuit và không gọi tiếp khiến advice phía trong không chạy.
10. Điều kiện pointcut động không khớp trong lần gọi đó.
11. Method có overload khác chữ ký, hoặc interface được ánh xạ khác dự kiến.
12. Handler đã chạy nhưng chính logger/sink bỏ qua sự kiện.

Không phải tất cả là **lỗi runtime** hoặc **lỗi của AOP engine**. Một số là kết quả đúng của mô hình và đường gọi. Điều quan trọng là đối chiếu **hợp đồng độ bao phủ mà ứng dụng đã hứa**.

## 25. Advice bao quanh và `proceed` khi gặp giới hạn proxy

Trong một around advice, `proceed` hoặc continuation tương đương thường chuyển quyền điều khiển vào phần còn lại của chuỗi. Nhưng:

- Không gọi proceed có thể **bỏ qua phần gốc** theo semantics của cơ chế.
- Gọi nhiều lần có thể **thực thi lại phần trong** nếu được phép.
- Gọi một lần ở lớp ngoài không đảm bảo phần gốc chạy đúng một lần nếu advice phía trong short-circuit hoặc retry.
- Advice `finally` có thể chạy ở đường return và throw nếu có unwinding phù hợp.
- Một exception ném từ chính advice có thể che lỗi gốc.

Những điều này **độc lập một phần** với vấn đề method `private/static/final`. Nếu lời gọi vốn **không đi qua proxy**, ngay cả một advice viết đúng `proceed` cũng không được kích hoạt.

### 25.1. Không tự gọi lại method để thay proceed

Một advice gọi lại method bị can thiệp thông qua cùng proxy có thể tạo vòng lặp:

~~~text
handler -> proxy.execute() -> handler -> proxy.execute() -> ...
~~~

Hoặc nếu gọi thẳng target, nó có thể **bỏ qua các advice khác** trong chain. Cần dùng continuation đúng hợp đồng của cơ chế thay vì suy rằng một lệnh reflection tương đương `proceed`.

## 26. Bảng kiểm thử cho các thành phần không override được

| Ca | Câu hỏi mong đợi |
|---|---|
| Interface proxy → method target final | Handler có chạy không? Trả về đúng không? |
| Interface proxy → target final class | Proxy có triển khai interface và chạy được không? |
| Gọi trực tiếp target final method | Handler có bị bỏ qua đúng như mô hình không? |
| Method private gọi trong target | Có một interception riêng hay chỉ trong phạm vi outer method? |
| Static method trên target | Có bị gọi trực tiếp ngoài instance proxy không? |
| Subclass proxy → public overridable method | Override có thể chèn before/after không? |
| Subclass proxy → final method | Có bị cấm override hay không có advice ở chính method? |
| Subclass proxy → final class | Tạo subclass có bị ngăn bởi quy tắc Java không? |
| Protected/package-private method | Có điều kiện package/module để override hợp lệ không? |
| Method call nội bộ trên target | Dispatch có quay qua proxy/subclass override hay bỏ qua? |
| Default method trên interface | Handler/target xử lý default method theo hợp đồng nào? |
| Object `equals/hashCode/toString` | Handler có semantics identity và recursion an toàn không? |
| Constructor và field access | Công cụ có hỗ trợ loại join point tương ứng không? |
| Method execution dệt bytecode | Có quan sát đúng cả lời gọi nội bộ/direct call không? |

Cần kết hợp test dương/âm. Chỉ có một log `[proxy] execute` không chứng minh **mọi lời gọi** `execute` đi qua proxy.

### 26.1. Đếm phần gốc thay vì chỉ đếm advice

Một ca thử có thể có handler chạy hai lần nhưng nghiệp vụ chỉ một lần, hoặc ngược lại. Hãy dùng một **bộ đếm trong phần gốc** và một **bộ đếm tại interceptor** để xác nhận số lần thực thi phù hợp thiết kế.

Trong ví dụ `InterfaceProxyLimitsDemo`, hai lần `execute` chạy nghiệp vụ nhưng chỉ một lần đi qua proxy.

## 27. Hiệu năng, bảo mật và độ đúng của lời gọi

Thêm interception có chi phí: dispatch qua proxy, reflection hoặc mã wrapper, kiểm tra pointcut, tạo context, logging, serialization và có thể đồng bộ trạng thái.

Với `private/static/final`, điều nguy hiểm không chỉ là thiếu log mà còn là **giả định độ bao phủ sai**. Ví dụ một chính sách kiểm soát bắt buộc chỉ nằm trong interface proxy, nhưng hệ thống có đường gọi trực tiếp target, có thể tồn tại một đường **bỏ qua kiểm tra**.

Vì thế:

- Không dùng proxy đơn thuần làm hàng rào an toàn nếu còn những đường gọi tin cậy khác bỏ qua nó.
- Đặt các bất biến nghiệp vụ bắt buộc ở ranh giới thực sự kiểm soát được hoặc trong thành phần nghiệp vụ sở hữu chúng.
- Chứng minh độ bao phủ qua integration test, không chỉ unit test của handler.
- Không tự log mọi đối số vì có thể lộ token, thông tin tài khoản hoặc dữ liệu nhạy cảm.
- Thiết kế lỗi logger/interceptor để không vô ý đổi kết quả/ngoại lệ nghiệp vụ nếu chính sách chỉ nhằm quan sát.
- Đo overhead trên những method tần suất cao; không mở rộng pointcut chỉ vì công cụ có khả năng.

### 27.1. Quan sát không đồng nghĩa thực thi quyền truy cập

Một advice ghi `ACCESS CHECK PASSED` trên một đường proxy không đảm bảo mọi lời gọi ở hệ thống đều đã qua kiểm tra. Khi cần chính sách bắt buộc, phải định nghĩa **toàn bộ ranh giới truy cập**, không chỉ một đường gọi được trang bị proxy.

## 28. Quy trình lựa chọn chiến lược khi gặp modifier đặc biệt

Một cách quyết định có cấu trúc:

1. **Đề bài là gì?** Ghi log API công khai, đo method nội bộ, theo dõi field hay kiểm soát constructor?
2. **Công cụ can thiệp nào đang dùng?** Interface proxy, subclass proxy, bytecode weaving, instrumentation?
3. **Loại join point có được hỗ trợ không?** Không suy từ tên “AOP”.
4. **Method/class có modifier nào?** Private, static, final, sealed, record, protected, package-private?
5. **Có interface phù hợp không?** Caller có thể dùng interface proxy thay vì class implementation không?
6. **Lời gọi có đi qua proxy không?** Bao gồm các đường self-invocation và direct reference.
7. **Nếu dùng subclass, có thể kế thừa và override hợp lệ không?** Xem constructor, module, package và method visibility.
8. **Nếu cần sâu hơn, weaving có hỗ trợ không?** Kiểm tra phạm vi, bytecode/version và join point semantics.
9. **Advice có bảo toàn hành vi gốc không?** Return, exception và số lần gọi?
10. **Có kiểm thử cả đường không can thiệp không?** Tránh hứa bao phủ ngoài thực tế.
11. **Có vấn đề bảo mật/độ tin cậy nếu bỏ sót không?** Nếu có, đặt policy ở ranh giới được bảo đảm.
12. **Có phương án đơn giản hơn?** Một API wrapper/decorator rõ ràng đôi khi dễ kiểm soát hơn việc dệt sâu.

Mục tiêu là **thiết kế đúng yêu cầu và giới hạn**, không phải dùng công cụ phức tạp nhất.

## 29. Câu hỏi tự kiểm tra

### Câu 1. `final` có làm mọi AOP bất lực?

Một `final class` triển khai `Service`; method `execute` ở implementation là `final`. Caller gọi `Service` qua Java Dynamic Proxy. Handler có thể chạy không?

**Đáp án:** có, nếu proxy được tạo đúng và caller dùng proxy. Handler chặn lời gọi interface; nó không override lớp final/method final của target.

### Câu 2. Vì sao subclass proxy không override `final`?

**Đáp án:** Java cấm lớp con override một final instance method. Muốn quan sát bằng lớp con phải chọn method đủ điều kiện override hoặc một ranh giới can thiệp khác.

### Câu 3. Private helper

Một public method được proxy chặn rồi gọi private helper. Có chắc handler nhận thêm một lần invocation cho private helper không?

**Đáp án:** không. Proxy interface không tự chặn private helper nội bộ. Dòng code private chạy trong phần gốc nhưng không là lời gọi giao diện qua proxy.

### Câu 4. Static method

Lớp con khai báo static method cùng tên với lớp cha. Đây có phải override đa hình và làm handler chạy không?

**Đáp án:** không. Đây có thể là *method hiding*, không phải override. Một instance interface proxy không tự chặn static method.

### Câu 5. Self-invocation

Client gọi qua interface proxy `checkout()`; bên trong target `checkout` gọi `charge()` bằng `this`. Nếu handler không ghi thêm `charge`, phải kết luận `charge` không chạy?

**Đáp án:** không. `charge` vẫn có thể chạy trực tiếp trên target. Thiếu handler log không chứng minh thiếu nghiệp vụ.

### Câu 6. Lớp final và record

Một record triển khai interface `Readable`. Có thể tạo subclass proxy của record không? Có thể cân nhắc interface proxy không?

**Đáp án:** record là final nên không thể subclass. Một interface proxy có thể áp dụng nếu interface phù hợp với ràng buộc của cơ chế và caller dùng proxy.

### Câu 7. Sealed interface

Một công cụ tạo Java Dynamic Proxy tiêu chuẩn muốn implement trực tiếp một sealed interface. Có được giả định thành công như giao diện bình thường không?

**Đáp án:** không. Sealed interface hạn chế class triển khai; Java Dynamic Proxy tiêu chuẩn không tạo proxy implement sealed interface trực tiếp.

### Câu 8. Bytecode weaving

Một method `private` có bị cấm tuyệt đối đối với mọi dạng AOP không?

**Đáp án:** không. Nó không override được và không được chặn riêng bằng interface proxy thông thường; một mô hình weaving khác có thể quan sát method execution phù hợp, nếu công cụ/VM hỗ trợ.

### Câu 9. Static method và field

Một proxy chặn lời gọi `getBalance()`. Có chứng minh mọi lần đọc field `balance` được chặn không?

**Đáp án:** không. Lời gọi getter là method invocation, còn field get có thể là một loại join point khác hoặc nằm ngoài mô hình proxy.

### Câu 10. Subclass self-invocation

Subclass proxy override được `open()`. Một method khác trên **cùng instance proxy** gọi virtual `open()`. Có khả năng đi qua override không?

**Đáp án:** có, theo virtual dispatch nếu lời gọi không bị buộc vào implementation khác và method override hợp lệ. Vì thế không khẳng định mọi self-invocation đều bỏ qua tất cả loại proxy.

### Câu 11. Object methods

Handler log bằng `proxy.toString()` trong chính handler có thể có rủi ro gì?

**Đáp án:** `toString()` của Java Dynamic Proxy có thể đi qua handler; handler tự gọi lại proxy có thể tạo recursion không mong muốn. Cần định nghĩa xử lý Object methods rõ ràng.

### Câu 12. Chính sách bắt buộc

Một policy phân quyền chỉ chạy khi caller dùng interface proxy. Có thể tuyên bố mọi lời gọi target đều đã được kiểm tra?

**Đáp án:** không, nếu tồn tại đường gọi trực tiếp target hoặc các điểm khác ngoài ranh giới proxy. Policy bắt buộc cần được thực thi ở nơi có độ bao phủ được bảo đảm.

## 30. Ghi nhớ

- **`private`** không thể override; private helper trên target không tự có interception riêng khi dùng interface proxy.
- **`static`** không được override đa hình; method hiding khác với interception qua virtual method.
- **`final method`** chặn subclass override, **không chặn mặc định interface proxy** đứng trước lời gọi đến một implementation final.
- **`final class`** không thể subclass nhưng vẫn có thể triển khai giao diện và đứng sau một interface proxy.
- **Record/sealed type** đưa thêm ràng buộc vào chiến lược subclass/proxy; phải kiểm tra đúng loại.
- **Constructor và field** không thể được xử lý như một virtual instance method bình thường chỉ bằng proxy.
- **Self-invocation** phụ thuộc đường gọi: interface proxy trên target thường bị bỏ qua, subclass override có thể được dispatch tới trong những trường hợp hợp lệ.
- **Bytecode weaving** có thể khác proxy về khả năng quan sát private/static/final, nhưng còn tùy join point model, phạm vi và giới hạn JVM.
- **Pointcut đúng chưa đủ**: phải có loại điểm hỗ trợ, cơ chế can thiệp thực sự hoạt động và đường runtime đi qua đúng vị trí.
- Chính sách quan sát/kiểm soát cần **kiểm thử dương/âm**, bảo toàn giá trị/ngoại lệ và tránh tuyên bố độ bao phủ vượt khả năng.

**Kết luận quan trọng:** Khi đánh giá một phương thức có `private`, `static` hoặc `final`, hãy hỏi **“công cụ cần override phương thức đó, chặn lời gọi qua một giao diện, hay dệt trực tiếp vào mã?”**. Chỉ sau khi biết câu trả lời mới xác định được modifier ấy thật sự giới hạn loại AOP đang áp dụng như thế nào.
