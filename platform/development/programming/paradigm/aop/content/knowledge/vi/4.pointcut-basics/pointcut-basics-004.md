# Phân biệt kiểu khai báo và kiểu thực tế khi lựa chọn điểm can thiệp

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), một pointcut chọn những điểm thực thi (join point) nơi hành vi bổ sung (advice) có thể chạy. Khi pointcut xét **kiểu**, cần xác định đang xét kiểu được biết ở lúc khai báo/biên dịch hay lớp của đối tượng thật ở thời điểm chạy. Hai loại thông tin này có thể khác nhau do **giao diện, kế thừa, đa hình, override, proxy và generic**.

Đây là kiến thức nền tảng của **pointcut cơ bản**, nhưng nếu nhầm loại kiểu được dùng để so khớp, một advice có thể áp dụng quá rộng, quá hẹp hoặc bỏ sót đường gọi quan trọng.

## 1. Phân biệt ba nguồn thông tin về kiểu

Ví dụ minh họa:

~~~java
Notifier notifier = new EmailNotifier();
notifier.send("Hello");
~~~

Đoạn trên giả định `Notifier` là interface, `EmailNotifier` là lớp triển khai; đây chưa phải chương trình độc lập. Ta có:

- **Declared/static type của biến** `notifier`: `Notifier`. Kiểu này được ghi trong mã nguồn và dùng để kiểm tra lời gọi hợp lệ tại lúc biên dịch.
- **Runtime/dynamic type của đối tượng** mà biến tham chiếu: `EmailNotifier`. Với một đối tượng khác null, `getClass()` trả về lớp runtime đó.
- **Declaring type của một phương thức cụ thể**: kiểu khai báo chính phương thức đang được mô tả. Nó có thể là interface, lớp cha hoặc lớp con override, tùy đang xét phương thức nào.

Điểm thứ ba rất quan trọng. `Method.getDeclaringClass()` của Java Reflection trả về lớp hoặc giao diện khai báo đối tượng `Method`, **không đồng nghĩa** lớp runtime của đối tượng đích. Khi phương thức có bản khai báo ở interface và bản triển khai tại lớp con, các đối tượng `Method` tương ứng có thể có `getDeclaringClass()` khác nhau.

| Câu hỏi | Ví dụ | Nguồn dữ liệu |
| --- | --- | --- |
| Biến/biểu thức có kiểu tĩnh gì? | `Notifier` | Khai báo và phân giải kiểu lúc biên dịch |
| Phương thức trong một chữ ký do ai khai báo? | `Notifier.send` hoặc `EmailNotifier.send` | Thông tin chữ ký/`Method` cụ thể |
| Đối tượng đích hiện thực thuộc lớp nào? | `EmailNotifier` | Đối tượng tại runtime |
| Thân phương thức nào thực sự chạy? | `EmailNotifier.send` | Quy tắc dispatch của Java và kiểu lời gọi |

**Không nên gom bốn câu trả lời thành một khái niệm “kiểu của phương thức”.** Khi đọc quy tắc pointcut, phải xác định chính xác trường thông tin nào được nó so khớp.

## 2. Tại sao pointcut cần phân biệt kiểu tĩnh và kiểu động?

Giả sử:

~~~java
Notifier first = new EmailNotifier();
Notifier second = new SmsNotifier();
~~~

Đây là mảnh minh họa, giả sử cả hai lớp đều triển khai `Notifier`.

Hai biến có **cùng kiểu tĩnh** nhưng các đối tượng trỏ tới có **kiểu runtime khác nhau**. Một quy tắc chọn các lời gọi theo hợp đồng `Notifier` có thể quan tâm tới cả hai. Một quy tắc chỉ theo dõi các đối tượng đích là `EmailNotifier` cần loại trường hợp thứ hai.

Ta có thể phát biểu hai điều kiện bằng **giả mã AOP trung lập với công cụ**:

~~~text
staticSelector:
    chọn join point có chữ ký tĩnh phù hợp hợp đồng Notifier

runtimeSelector:
    chọn join point nếu đối tượng đích tại thời điểm chạy
    là instance của EmailNotifier

advice:
    thực hiện ghi log, đo thời gian hoặc hành vi khác
    tại điểm được chọn
~~~

`staticSelector` và `runtimeSelector` chỉ minh họa hai ý nghĩa lựa chọn; chúng **không phải** cú pháp pointcut của một thư viện cụ thể. Cơ chế AOP khác nhau có tập join point, cú pháp mẫu kiểu và khả năng kiểm tra runtime khác nhau.

Quy tắc dựa trên chữ ký có thể được phân tích hoặc loại trừ từ sớm. Quy tắc phụ thuộc đối tượng runtime có thể phải kiểm tra mỗi lần gọi. Điều này ảnh hưởng hiệu năng, nhưng ưu tiên đầu tiên vẫn phải là **ngữ nghĩa chọn đúng**.

## 3. Điểm gọi và điểm thực thi có thể dùng thông tin chữ ký khác nhau

Một phương thức có thể được **gọi** qua tham chiếu kiểu interface rồi **thực thi** bằng phần thân override trong lớp cụ thể:

~~~java
interface Notifier {
    void send(String message);
}

class EmailNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("EMAIL " + message);
    }
}

Notifier viaInterface = new EmailNotifier();
EmailNotifier viaConcrete = new EmailNotifier();

viaInterface.send("A");
viaConcrete.send("B");
~~~

Đây là một đoạn minh họa đủ khai báo liên quan, nhưng không có phương thức `main` độc lập.

Cả hai lời gọi cuối đều thực thi thân `EmailNotifier.send`. Tuy nhiên:

| Thuộc tính | `viaInterface.send("A")` | `viaConcrete.send("B")` |
| --- | --- | --- |
| Kiểu của biến bên gọi sử dụng | `Notifier` | `EmailNotifier` |
| Kiểu runtime của đối tượng đích | `EmailNotifier` | `EmailNotifier` |
| Thân phương thức thực thi | `EmailNotifier.send` | `EmailNotifier.send` |
| Chữ ký tĩnh tại điểm call | Có thể mang kiểu đủ điều kiện `Notifier` | Có thể mang kiểu đủ điều kiện `EmailNotifier` |
| Điều kiện runtime “target là EmailNotifier” | Đúng | Đúng |

**Method-call join point** nằm tại vị trí bên gọi phát sinh lời gọi. **Method-execution join point** nằm tại việc thực thi phần thân phương thức. Đó là hai loại điểm khác nhau, và không phải mọi cơ chế AOP đều hỗ trợ cả hai.

~~~text
Bên gọi có biến kiểu Notifier
              |
              v
         CALL join point
              |
              v
       Dispatch đa hình
              |
              v
   EXECUTION của EmailNotifier.send
              |
              v
          Thân send
~~~

Trong một mô hình AOP hỗ trợ cả call và execution với chữ ký tĩnh, kiểu đủ điều kiện ở chữ ký **call** có thể xuất phát từ kiểu dùng để truy cập phương thức ở mã bên gọi, còn chữ ký **execution** có thể gắn với kiểu khai báo phần thân đang thực thi. Đây là một ví dụ cho thấy “hai lời gọi cùng chạy một thân phương thức” **không bảo đảm** cùng được chọn bởi mọi pointcut dựa trên chữ ký call.

Ngược lại, nếu pointcut kiểm tra *đối tượng đích runtime* là `EmailNotifier`, cả hai lời gọi có thể thỏa, **miễn là join point tương ứng nằm trong khả năng và phạm vi can thiệp của cơ chế**.

## 4. Chọn theo chữ ký, nơi khai báo hay đối tượng thực tế

Khi mô tả “chọn phương thức của lớp `EmailNotifier`”, người viết cần làm rõ một trong các yêu cầu sau:

1. **Theo kiểu xuất hiện trong chữ ký tại điểm gọi:** bên gọi truy cập phương thức thông qua một kiểu tĩnh được chỉ định.
2. **Theo phương thức đang thực thi:** chỉ chọn phần thân được khai báo/thực thi ở một lớp nhất định.
3. **Theo đối tượng đích runtime:** chọn lời gọi nếu đối tượng thật là `EmailNotifier` hoặc một lớp con.
4. **Theo kiểu thực tế của tham số:** chọn nếu một đối số thực tế là `EmailNotifier`, dù nó chỉ là tham số chứ không phải đối tượng nhận lời gọi.
5. **Theo đối tượng bên gọi:** xét đối tượng đang thực thi mã ở nơi phát sinh lời gọi, có thể khác đối tượng đích.

Những điều kiện này không tương đương. Trong cách diễn đạt AOP, các thuật ngữ `this`, `target` và `args` thường chỉ những vai trò ngữ cảnh khác nhau. Ở điểm **call**, đối tượng đang thực thi mã tại bên gọi và đối tượng **nhận lời gọi** có thể là hai đối tượng. Ở một điểm thực thi thuộc ngữ cảnh `static`, có thể không có `this` là instance. Một số mô hình pointcut cho phép ràng buộc những giá trị này để advice sử dụng, nhưng việc truy xuất dữ liệu không tự làm thay đổi điểm được chọn.

**Quy tắc đọc pointcut:** trước khi kết luận, xác định **loại join point**, **loại kiểu đang xét**, **đối tượng tham gia** và **khả năng triển khai thực tế**.

## 5. Ví dụ Java 17 chạy độc lập: declared Method và runtime target

Chương trình sau sử dụng **Java dynamic proxy** để mô hình hóa hai điều kiện so khớp. Đây là ví dụ về **tư duy AOP** ở điểm lời gọi đi qua giao diện, không phải một bộ công cụ AOP hỗ trợ mọi loại join point.

Tạo file `DeclaredRuntimePointcutDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class DeclaredRuntimePointcutDemo {
    interface Handler {
        String handle(String value);
    }

    static class BasicHandler implements Handler {
        @Override
        public String handle(String value) {
            System.out.println("BUSINESS BasicHandler");
            return "basic:" + value;
        }
    }

    static class FastHandler extends BasicHandler {
        @Override
        public String handle(String value) {
            System.out.println("BUSINESS FastHandler");
            return "fast:" + value;
        }
    }

    // Ví dụ điều kiện trên Method do proxy cung cấp.
    static boolean declaredMatch(Method method) {
        return method.getDeclaringClass() == Handler.class
                && method.getName().equals("handle");
    }

    // Ví dụ điều kiện dựa trên đối tượng runtime.
    static boolean runtimeMatch(Handler target) {
        return target instanceof FastHandler;
    }

    static Handler wrap(Handler target) {
        return (Handler) Proxy.newProxyInstance(
                Handler.class.getClassLoader(),
                new Class<?>[] { Handler.class },
                (proxy, method, args) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return method.invoke(target, args);
                    }
                    boolean declared = declaredMatch(method);
                    boolean runtime = runtimeMatch(target);
                    System.out.println("MATCH declared=" + declared
                            + " runtime=" + runtime);

                    if (declared && runtime) {
                        System.out.println("ADVICE "
                                + target.getClass().getSimpleName());
                    }

                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                });
    }

    public static void main(String[] args) throws Exception {
        Handler fast = new FastHandler();

        Method contract = Handler.class.getMethod("handle", String.class);
        Method actualMethod =
                FastHandler.class.getMethod("handle", String.class);

        System.out.println("METHOD declared="
                + contract.getDeclaringClass().getSimpleName());
        System.out.println("TARGET runtime="
                + fast.getClass().getSimpleName());
        System.out.println("METHOD implementation="
                + actualMethod.getDeclaringClass().getSimpleName());

        Handler fastProxy = wrap(fast);
        Handler basicProxy = wrap(new BasicHandler());

        System.out.println("RESULT " + fastProxy.handle("hi"));
        System.out.println("RESULT " + basicProxy.handle("hi"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DeclaredRuntimePointcutDemo.java
java DeclaredRuntimePointcutDemo
~~~

Stdout:

~~~text
METHOD declared=Handler
TARGET runtime=FastHandler
METHOD implementation=FastHandler
MATCH declared=true runtime=true
ADVICE FastHandler
BUSINESS FastHandler
RESULT fast:hi
MATCH declared=true runtime=false
BUSINESS BasicHandler
RESULT basic:hi
~~~

Phân tích:

- `Handler.class.getMethod(...)` trả về `Method` của giao diện `Handler`; declaring class là `Handler`.
- `fast.getClass()` trả về `FastHandler`, lớp runtime của đối tượng.
- `FastHandler.class.getMethod(...)` tìm bản override khai báo tại `FastHandler`; declaring class là `FastHandler`.
- Hai lần gọi qua proxy đều chuyển `Method` của giao diện vào bộ xử lý, nên `declaredMatch` đúng cả hai.
- `runtimeMatch` đúng với `FastHandler` và sai với `BasicHandler`. Vì vậy chỉ một lần có dòng `ADVICE`.
- Gọi `method.invoke(target, args)` chuyển tiếp đến phương thức phù hợp trên đối tượng thật; ngoại lệ do reflection bọc trong `InvocationTargetException` được tháo để không thay đổi lỗi nghiệp vụ.

Hai hàm `declaredMatch` và `runtimeMatch` **chỉ là điều kiện minh họa do chương trình tự viết**. `Method` trong `InvocationHandler` của proxy là thông tin của cơ chế proxy này; đừng suy rằng mọi mô hình **call join point** đều dùng chính `Method` ấy để quyết định chữ ký tĩnh.

Nếu gọi trực tiếp `new FastHandler().handle("hi")`, phương thức nghiệp vụ vẫn chạy, nhưng **proxy và advice trong ví dụ này không chạy**. Việc đối tượng có kiểu runtime phù hợp không tự bảo đảm đường gọi nằm trong phạm vi đã được weave.

## 6. Kế thừa, override và phần thân thực thi

Xét:

~~~java
class Parent {
    void execute() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    @Override
    void execute() {
        System.out.println("Child");
    }
}

Parent ref = new Child();
ref.execute();
~~~

Đây là mã minh họa, chưa phải chương trình có `main`. Trong dispatch ảo thông thường, `Child` được in ra. Kiểu khai báo của `ref` vẫn là `Parent`, còn đối tượng runtime là `Child`.

Nếu `Child` không override `execute()`, phần thân được chạy có thể vẫn **được khai báo tại Parent**, trong khi đối tượng runtime là `Child`. Một pointcut xét declaring class của phần thân và một pointcut xét lớp runtime của đối tượng vì thế có thể khác kết quả.

Cần phân biệt thêm:

- **Override:** phương thức lớp con thay cách thực hiện, dispatch động chọn phương thức khi phù hợp.
- **Overload:** nhiều phương thức cùng tên nhưng khác danh sách tham số. Trình biên dịch chọn overload dựa trên các kiểu tĩnh và quy tắc phân giải lời gọi; không đơn giản chọn theo lớp runtime của đối số.
- **Static method:** không có dispatch ảo theo đối tượng như phương thức instance có thể override.
- **Private method và lời gọi `super`:** có quy tắc phân giải riêng, không nên suy rộng ví dụ override.
- **Constructor:** có join point và ngữ nghĩa riêng trong các mô hình hỗ trợ, không coi là một method-call thông thường.

Ví dụ overload:

~~~java
void send(CharSequence value) { /* trường hợp A */ }
void send(String value)       { /* trường hợp B */ }
~~~

Một pointcut chỉ lọc tên `send` có thể chọn quá rộng; điểm gọi sử dụng chữ ký `CharSequence` và chữ ký `String` có thể thuộc các tập điểm khác nhau.

## 7. Bằng đúng lớp hay bao gồm lớp con?

Một chính sách chọn “đích là `EmailNotifier`” có thể mang hai ý nghĩa:

| Mong muốn | Biểu thức kiểm tra lớp Java | Có chọn lớp con không? |
| --- | --- | --- |
| Chính xác lớp `EmailNotifier` | `target.getClass() == EmailNotifier.class` | Không |
| `EmailNotifier` hoặc bất kỳ lớp con | `target instanceof EmailNotifier` | Có |
| Mọi đối tượng triển khai `Notifier` | `target instanceof Notifier` | Có nếu thuộc hợp đồng đó |

Các biểu thức là ví dụ kiểm tra trên biến `target` khác null, giả sử các kiểu đã tồn tại. Mẫu kiểu trong ngôn ngữ pointcut có thể có cú pháp và quy tắc bao gồm lớp con riêng; **không mặc định** ký hiệu giống nhau giữa các công cụ.

Nếu chính sách là “mọi triển khai của một hợp đồng đều phải được kiểm tra quyền”, chọn theo quan hệ interface/lớp cha thường thể hiện ý định rõ hơn việc liệt kê tên từng lớp triển khai. Tuy vậy vẫn phải bảo đảm mọi đường gọi cần bảo vệ đi qua điểm can thiệp.

## 8. Các tình huống nâng cao

### 8.1 Proxy, wrapper và đối tượng đích

Một chương trình có thể tạo đối tượng proxy có runtime class khác đối tượng nghiệp vụ bên trong. Nếu truy vấn `getClass()` trên **proxy** thì kết quả khác truy vấn trên **đối tượng được proxy chuyển tiếp tới**. Trước khi so khớp kiểu runtime, cần hỏi rõ “đang xét đối tượng nào: proxy, caller, receiver hay target thật?”.

Đó cũng là lý do không nên suy `Method.getDeclaringClass()` của phương thức qua giao diện sẽ là lớp của đối tượng triển khai. Một bộ chặn lời gọi có thể thấy phương thức khai báo ở interface, trong khi thân phương thức chạy trên lớp cụ thể.

### 8.2 Generic và xóa kiểu

Trong Java, `List<String>` và `List<Integer>` có cùng kiểu thô runtime sau **type erasure** đối với các đối tượng `ArrayList` tương ứng. Thông tin generic trong khai báo không tạo hai runtime class `ArrayList<String>` và `ArrayList<Integer>` khác nhau.

Một cơ chế chọn điểm dựa trên chữ ký nguồn hoặc metadata generic có thể có thông tin khác cơ chế chỉ so khớp bytecode đã xóa kiểu. Khi các lớp override phương thức generic, trình biên dịch đôi khi tạo **bridge method** để giữ dispatch sau erasure. Những phương thức synthetic/bridge có thể làm việc liệt kê hoặc instrument phương thức khác mong đợi; cần kiểm tra cụ thể và tránh đếm trùng.

### 8.3 Annotation trên interface, lớp cha và override

Metadata annotation không tự động có cùng ý nghĩa ở mọi mức của cây kế thừa. Annotation đặt ở phương thức của interface không bảo đảm một phương thức override có cùng annotation trực tiếp. Trong Java, `@Inherited` chỉ hỗ trợ quy tắc kế thừa annotation ở **kiểu lớp** trong phạm vi được định nghĩa; nó không tự khiến annotation của phương thức được kế thừa trên mọi override.

Vì thế, pointcut so khớp annotation tại khai báo gốc có thể khác so khớp tại phương thức thực tế hoặc loại runtime của đối tượng. Phải xác định rõ nguồn metadata.

### 8.4 Tham số null và kiểm tra kiểu động

Đối số `null` không có runtime class; gọi `getClass()` trên `null` gây `NullPointerException`. Tuy nhiên, phương thức vẫn có **kiểu tham số được khai báo**. Cách match một tham số null khi sử dụng biểu thức kiểu động là quy tắc của ngôn ngữ pointcut cụ thể, không thể thay bằng một kết luận chung “null luôn khớp” hay “null không bao giờ khớp”.

### 8.5 Tối ưu pointcut và chi phí runtime

Điều kiện chữ ký có thể được tính hoặc loại trừ ở thời điểm biết cấu trúc chương trình; điều kiện kiểu runtime cần đọc đối tượng thực tế và có thể đánh giá trên từng lần gọi. Không nên đưa phép kiểm tra có tác dụng phụ hoặc quá tốn thời gian vào điểm nóng. Sự đúng đắn của tập join point được chọn vẫn là ưu tiên; chỉ tối ưu sau khi đo được chi phí.

## 9. Các lỗi thiết kế dễ gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi kiểu biến là kiểu runtime | Bỏ sót các lớp triển khai khác nhau | Phân biệt static reference type và dynamic target type |
| Coi `getDeclaringClass()` luôn trả lớp runtime | Chọn sai khi quan sát `Method` của interface hoặc lớp cha | Xác định đối tượng `Method` đang được dùng |
| Đồng nhất call với execution | Hiểu nhầm chữ ký và nơi can thiệp | Xác minh loại join point |
| Chọn đúng kiểu nhưng bỏ qua phạm vi proxy/weaving | Một số lời gọi không chạy advice | Kiểm thử toàn bộ đường gọi |
| Dùng so sánh lớp chính xác trong khi muốn gồm lớp con | Bỏ sót subclass | Dùng quan hệ subtype/instance phù hợp |
| Coi kiểu generic lúc biên dịch luôn tồn tại ở runtime | Pointcut không khớp như mong đợi | Kiểm tra erasure và bridge methods |
| Lẫn runtime target với runtime argument | Quy tắc chọn đối tượng khác mục tiêu | Chỉ rõ target, this và args |
| Giả định annotation trên hợp đồng tự xuất hiện ở override | Bỏ sót advice hoặc chọn lệch | Kiểm tra nơi khai báo annotation và quy tắc tìm kiếm |
| Chỉ thử trường hợp thành công của một lớp | Không biết phạm vi thật của pointcut | Kiểm thử cả nhánh khớp và không khớp |

## 10. Kiểm thử bằng ma trận kiểu

Giả sử có interface `Notifier`, hai triển khai `EmailNotifier`, `SmsNotifier`, và lớp con `FastEmailNotifier`:

1. Gọi qua **biến `Notifier`** tới `EmailNotifier`: đối chiếu chữ ký call tĩnh và kiểu đích runtime.
2. Gọi qua **biến `EmailNotifier`** tới cùng một đối tượng: kiểu tham chiếu khác, đích runtime không đổi.
3. Gọi qua **biến `Notifier`** tới `SmsNotifier`: chữ ký phía interface có thể giữ nguyên, đích runtime đổi.
4. Gọi tới `FastEmailNotifier`: thử điều kiện “đúng bằng EmailNotifier” và “là instance của EmailNotifier”.
5. Gọi phương thức **được kế thừa nhưng không override**: declaring class của phần thân có thể vẫn là lớp cha.
6. Gọi phương thức **qua proxy** và **trực tiếp**: phân biệt đúng điều kiện kiểu với khả năng advice thực sự được kích hoạt.
7. Thử **overload**, generic/bridge, annotation và các tham số null trong những điểm mà hệ thống thực tế có hỗ trợ.

Ở mỗi trường hợp, ghi lại **kiểu tĩnh**, **loại join point**, **declaring type của chữ ký liên quan**, **kiểu đối tượng runtime**, **kết quả match** và **advice có thực sự chạy hay không**. Một dòng log thành công tại một lời gọi không chứng minh pointcut đã bao phủ mọi đường gọi quan trọng.

## 11. Câu hỏi tự luyện

Xét:

~~~java
Payment p = new CardPayment();
p.pay();
~~~

Giả sử `Payment` là giao diện, `CardPayment` triển khai và override `pay()`.

**Kiểu khai báo của `p`?** — `Payment`.

**Kiểu runtime của đối tượng?** — `CardPayment`.

**Có thể mặc định điểm gọi mang chữ ký của `CardPayment` chỉ vì đối tượng là `CardPayment`?** — Không. Phải xem loại join point và quy tắc hình thành chữ ký.

**Một điều kiện chọn runtime target `instanceof CardPayment` có thể khớp khi gọi qua biến `Payment`?** — Có, nếu mô hình hỗ trợ kiểu chọn đó và đường gọi nằm trong phạm vi can thiệp.

**Nếu một proxy chỉ bọc vài đường gọi, điều kiện kiểu đúng có bảo đảm advice chạy với lời gọi trực tiếp không?** — Không.

**Nếu `PremiumCardPayment extends CardPayment`, phép `getClass()==CardPayment.class` có chọn đối tượng PremiumCardPayment không?** — Không; phép `instanceof CardPayment` có.

**Nếu muốn áp dụng kiểm tra chung cho mọi hiện thực của `Payment`, cần nghĩ theo loại thông tin nào?** — Theo hợp đồng chung và tập điểm cần bảo vệ, kết hợp kiểm chứng mọi đường gọi, thay vì phụ thuộc vào một tên lớp triển khai.

## Tài liệu tham khảo

- [AspectJ Programming Guide – Signatures and Matching](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): mô hình ví dụ về sự khác biệt giữa chữ ký method call và method execution.
- [AspectJ Language Semantics – Pointcuts](https://eclipse.dev/aspectj/doc/latest/progguide/semantics.html): ví dụ cơ chế AOP phân biệt điều kiện chữ ký và điều kiện kiểu runtime.
- [Java SE 17 – Method.getDeclaringClass()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDeclaringClass()): quy tắc Reflection về kiểu khai báo phương thức.

**Ghi nhớ:** Khi đọc hoặc viết pointcut, hãy hỏi **“kiểu tĩnh của khai báo/chữ ký nào?”** và **“kiểu runtime của đối tượng nào?”**. Phân biệt chúng cùng với loại join point, quan hệ subtype và phạm vi weaving giúp chọn đúng điểm can thiệp trong chương trình đa hình.
