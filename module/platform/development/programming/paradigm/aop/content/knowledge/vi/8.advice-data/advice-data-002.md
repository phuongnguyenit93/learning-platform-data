# Nhận tham số, đối tượng đích và đối tượng thực thi trong advice AOP

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), advice thường cần biết **lần thực thi nào đang diễn ra** và **những dữ liệu nào liên quan tới lần thực thi đó**. Ghi log, kiểm tra quyền, đo thời gian, theo dõi truy vết hay kiểm toán đều có thể cần đọc tham số của lời gọi, đối tượng nhận lời gọi và đối tượng đang thực thi mã ở vị trí được can thiệp.

Ba nguồn ngữ cảnh dễ nhầm nhất là:

1. **Arguments / args – tham số thực tế:** những giá trị được truyền vào một lời gọi, theo vị trí và kiểu tương ứng.
2. **Target – đối tượng đích:** đối tượng mà thao tác hướng tới hoặc được gọi, nếu loại join point ấy có target.
3. **This / executing object – đối tượng đang thực thi:** đối tượng của ngữ cảnh `this` tại vị trí chương trình đang chạy; ở một **method call join point** có thể là đối tượng phía bên gọi, không phải target.

**Đây không phải ba tên cho cùng một đối tượng.** Đặc biệt, ở điểm gọi `a.call(b)`, đối tượng `a` có thể là *receiver/target* của phương thức `call`, trong khi `b` chỉ là **tham số**; còn `this` trong mã phát sinh lời gọi có thể là một đối tượng thứ ba. Ở điểm **method execution** trong phương thức instance của đích, `this` thông thường gắn với chính đối tượng nhận việc thực thi.

Bài này trình bày cách nhận và ràng buộc ba loại dữ liệu trong advice, giải thích sự khác biệt theo **loại join point**, cách sử dụng khi chọn pointcut và những giới hạn của cơ chế AOP. Tên biểu thức cụ thể như `this`, `target`, `args` được dùng theo nghĩa khái niệm thường thấy trong các mô hình AOP có khả năng expose ngữ cảnh; **không phải mọi công cụ đều hỗ trợ cùng cú pháp hoặc cùng tập join point**.

## 1. Ngữ cảnh của join point: tại sao advice cần dữ liệu?

**Join point (điểm nối)** là một điểm xác định trong luồng thực thi mà mô hình AOP có thể can thiệp. **Pointcut** xác định điểm nào được chọn. **Advice** là hành vi thực thi tại điểm được chọn. **Context binding/exposure** cung cấp dữ liệu của một lần xuất hiện join point cho advice.

Ví dụ nghiệp vụ:

~~~java
receiptService.create("ORDER-7", 3);
~~~

Đây là **một mảnh lời gọi**, giả định đã có đối tượng `receiptService` và phương thức `create`. Nếu advice ghi lại lần tạo biên nhận, nó có thể cần:

- **Chữ ký/mô tả:** tên phương thức `create`, kiểu tham số được khai báo.
- **Giá trị args:** `"ORDER-7"` và `3` ở chính lần gọi này.
- **Target:** đối tượng thực sự nhận thao tác tạo biên nhận.
- **Executing object / this:** đối tượng mà mã đang được thực thi tại điểm nối thuộc về nó, **nếu điểm đó có ngữ cảnh this**.
- **Dữ liệu sau thực thi:** giá trị trả về hoặc ngoại lệ, chỉ khả dụng ở những thời điểm/loại advice phù hợp.
- **Dữ liệu bổ sung:** correlation ID, identity đã xác thực hoặc transaction context nếu chương trình cung cấp qua một nguồn hợp lệ.

Advice không nên tự coi một đối số tên `userId` là danh tính đã xác thực. **Binding truyền dữ liệu, không tự xác minh độ tin cậy của dữ liệu.**

## 2. Bảng phân biệt: args, target và this

| Thành phần | Câu hỏi cần trả lời | Ví dụ ở một lời gọi method call | Lưu ý |
| --- | --- | --- | --- |
| **Arguments** | Lần này truyền những giá trị gì? | `"ORDER-7"`, `3` | Có thể rỗng, null, primitive được biểu diễn boxing |
| **Target** | Đối tượng nào là đích nhận lời gọi? | `receiptService` | Có thể không tồn tại ở điểm tĩnh, constructor hoặc loại join point khác |
| **This / executing object** | Đối tượng nào đang thực thi mã tại điểm nối? | `this` của phương thức bên gọi phát sinh `receiptService.create(...)` | Có thể khác target; ở static context không có instance this |

Nếu code là:

~~~java
class OrderController {
    private ReceiptService receiptService;

    void confirm() {
        receiptService.create("ORDER-7", 3);
    }
}
~~~

Đây là **đoạn minh họa trong ngữ cảnh lớp**. Tại **method call join point** của `receiptService.create` phát sinh trong `confirm()`:

- **This** của mã bên gọi có thể là instance `OrderController`.
- **Target** là instance nhận lời gọi `ReceiptService.create`.
- **Args** là mã đơn `"ORDER-7"` và số lượng `3`.

Nhưng tại **method execution join point** ở phần thân `ReceiptService.create`, nếu đó là phương thức instance thông thường, **this** đang chạy thân phương thức thường là đối tượng service đó; tức có thể trùng với đối tượng đích của execution. Sự phân biệt phải gắn với **loại join point**, không chỉ tên phương thức.

### 2.1 Đây là dữ liệu runtime chứ không chỉ chữ ký tĩnh

Kiểu khai báo trong phương thức có thể là:

~~~java
void create(CharSequence orderId, int copies);
~~~

Hai lần gọi `create("A", 1)` và `create("B", 5)` có **cùng chữ ký tĩnh** nhưng giá trị args khác nhau. Nếu `ReceiptService` là interface, một biến khai báo kiểu interface có thể trỏ tới nhiều triển khai runtime khác nhau.

Vì vậy cần phân biệt:

- **Declared parameter types:** `CharSequence`, `int`.
- **Actual argument values:** `"A"`, `1` hoặc `"B"`, `5`.
- **Actual argument runtime classes:** ví dụ đối số chuỗi có thể là `String`; đối số null không có runtime class.
- **Declared target type:** kiểu được dùng ở chữ ký hoặc tại call site.
- **Target runtime type:** lớp đối tượng thật tại lần thực thi, nếu có target.

Pointcut chọn theo chữ ký không đồng nghĩa pointcut chọn theo giá trị hay kiểu runtime của đối tượng.

## 3. Nhận tham số trong advice

### 3.1 Các cách tiếp cận khái niệm

Một hệ thống AOP có thể cho advice nhận:

1. **Toàn bộ danh sách đối số** dưới dạng mảng/sequence.
2. **Một số đối số được bind theo vị trí, tên hoặc kiểu**, tùy cơ chế.
3. **Thông tin chữ ký** như tên phương thức và kiểu được khai báo.
4. **Ngữ cảnh kết quả/ngoại lệ** ở loại advice sau thực thi phù hợp.

Giả mã không gắn với một ngôn ngữ AOP cụ thể:

~~~text
pointcut: execution of ReceiptService.create(...)
bind:     orderId = args[0]
          copies  = args[1]

before advice:
    record("create", orderId, copies)
~~~

Bộ chọn ở đây mô tả nơi chạy advice. Việc ràng buộc `args[0]` và `args[1]` giúp advice biết **giá trị của lần gọi đang xử lý**, không phải những giá trị cố định lúc khai báo pointcut.

Nếu một mô hình AOP hỗ trợ mẫu kiểu động trên tham số, pointcut còn có thể dùng **kiểu runtime của args** để quyết định có khớp. Điều đó khác với binding dữ liệu cho advice: **đọc một đối số không tự động có nghĩa đã lọc theo đối số đó**.

### 3.2 Không giả định args luôn có độ dài và thứ tự mong muốn

Nếu pointcut rộng chọn các overload khác nhau:

~~~java
void process(String id);
void process(String id, int priority);
~~~

Đây là mảnh khai báo. Với overload đầu, `args[1]` không tồn tại. Advice đọc chỉ số 1 mà không kiểm tra chữ ký/độ dài có thể ném lỗi. Phải chọn đúng signature hoặc kiểm tra đối số an toàn.

Ngoài ra:

- Phương thức không tham số có danh sách args rỗng.
- Tham số kiểu tham chiếu có thể là `null`.
- Tham số primitive có thể hiện dưới dạng wrapper (`int` thành `Integer`) ở một API reflection/proxy.
- Với varargs Java, phần `String...` thường là **một tham số mảng** ở chữ ký bytecode; đừng mặc định một phần tử vararg tương đương một mục độc lập trong mảng args của advice.
- Generic bị **type erasure** có thể làm kiểu trong descriptor khác kiểu tổng quát nhìn từ nguồn.
- Một số cơ chế cung cấp bản sao mảng đối số; thay đổi mảng ấy có được truyền sang lời gọi thật hay không **phụ thuộc hợp đồng của continuation/binding**.

### 3.3 Đọc khác với sửa tham số

Một advice chỉ quan sát thường nên đọc args mà không chỉnh sửa. Để thay tham số trước khi tiếp tục, cần khả năng **around advice + proceed với đối số thay thế** nếu mô hình hỗ trợ, và phải bảo toàn hợp đồng về kiểu, thứ tự, tính hợp lệ và tác dụng phụ.

Giả mã:

~~~text
around(context, proceed):
    original = context.args
    if allowedToNormalize(original):
        transformed = normalize(original)
        return proceed(transformed)
    return proceed(original)
~~~

**Không mặc định** việc sửa một `Object[]` trong handler hoặc context khiến lời gọi thật nhận đối số đã sửa. Cũng không mặc định mọi AOP runtime cho phép thay đối số hoặc gọi `proceed` nhiều lần. Đây là các tính năng cần xác minh.

### 3.4 Tránh làm rò rỉ dữ liệu

Truyền args cho advice logging là một ranh giới dữ liệu mới. Không tự in tất cả tham số hoặc `toString()` của đối tượng:

- Password, token, secret, thông tin thanh toán và dữ liệu cá nhân có thể bị lộ.
- `toString()` có thể có tác dụng phụ, ném lỗi hoặc vô tình truy cập cấu trúc lớn/vòng lặp.
- Các đối tượng mutable có thể thay đổi giữa thời điểm advice ghi nhận và thời điểm xử lý bất đồng bộ.
- Nếu lưu tham chiếu tới args lâu hơn vòng đời lời gọi, cần cân nhắc quyền sở hữu, snapshot và dọn dẹp để tránh rò dữ liệu.

Một cách an toàn hơn là **chọn đúng các trường cần quan sát, che dữ liệu nhạy cảm, ghi mã tương quan và trạng thái**, thay vì ghi toàn bộ payload.

## 4. Target: đối tượng đích là ai?

**Target** của một method-call join point instance thường là đối tượng mà lời gọi hướng tới. Nhưng một chương trình có thể chứa nhiều đối tượng:

~~~java
controller.submit(service, order);
~~~

Ở lời gọi `submit`:

- Target của **`submit`** là `controller`.
- `service` và `order` là **arguments** của lời gọi `submit`, không phải target của `submit`.
- Nếu bên trong `submit` có `service.save(order)`, thì ở lời gọi **`save`** target lại là `service`, args gồm `order`.

Việc một object xuất hiện trong danh sách tham số **không** biến nó thành target của cùng join point.

### 4.1 Target type tĩnh và type thực tế

~~~java
Service service = new SpecialService();
service.execute("A");
~~~

Nếu `Service` là interface và `SpecialService` là một triển khai, **kiểu khai báo** của biến service là `Service`, nhưng **runtime class** của target là `SpecialService`.

Một pointcut dựa trên kiểu khai báo của chữ ký có thể so khớp khác một pointcut kiểm tra target runtime. Nếu muốn chọn tất cả triển khai của interface, mẫu quan hệ subtype/instance (khi được hỗ trợ) có ý nghĩa khác điều kiện **đúng bằng một lớp**.

### 4.2 Proxy và decorator: “đối tượng nào là target?”

Trong hệ thống có **proxy**, bên gọi có thể nắm một proxy, proxy chuyển tiếp tới object nghiệp vụ gốc. Lúc này cần phân biệt:

- **Proxy/receiver tại biên:** object bên gọi thực sự gọi.
- **Underlying target:** object nghiệp vụ mà lớp bọc chuyển tiếp tới.
- **Method signature được handler nhận:** có thể được khai báo bởi interface.
- **Đối tượng đang chạy thân phương thức nghiệp vụ:** instance cụ thể của lớp triển khai.

Ở một **proxy invocation handler**, tham số `proxy` không nhất thiết là `target` gốc. Nếu advice muốn kiểm tra annotation hoặc kiểu của lớp nghiệp vụ, đọc `proxy.getClass()` có thể cho kết quả khác `target.getClass()`.

Quan trọng hơn, **không có một quy tắc phổ quát** bắt mọi công cụ AOP gán từ “target” cho cùng đối tượng khi có nhiều lớp bọc. Phải đọc định nghĩa ngữ cảnh của loại join point và kỹ thuật weaving đang sử dụng.

### 4.3 Target không phải lúc nào cũng tồn tại

Có thể có join point không gắn với một đối tượng instance cụ thể:

- Phương thức `static`: không có receiver instance theo nghĩa lời gọi instance.
- Một số điểm khởi tạo đối tượng: đối tượng có thể chưa tồn tại ở giai đoạn trước khi được tạo.
- Một số sự kiện xử lý ngoại lệ hoặc truy cập tĩnh: ngữ cảnh target phụ thuộc mô hình.
- Một số kỹ thuật weaving chỉ expose chữ ký và tham số, không có object target khả dụng.

Không được gọi `target.getClass()` khi target có thể là `null`. Việc `null` được diễn giải ra sao trong biểu thức pointcut còn phụ thuộc ngôn ngữ AOP cụ thể.

## 5. This: đối tượng đang thực thi và sự khác nhau giữa call/execution

Trong Java, từ khóa `this` trong thân **phương thức instance** tham chiếu đối tượng đang thực thi phương thức ấy. Nhưng khi dùng ký hiệu `this` trong pointcut AOP, cần hỏi **điểm nối là call hay execution**.

### 5.1 Tại method-call join point

Ví dụ:

~~~java
class Controller {
    private final Service service;

    Controller(Service service) {
        this.service = service;
    }

    void submit() {
        service.execute("A");
    }
}
~~~

Đây là mã minh họa, giả sử `Service` được khai báo ở nơi khác.

Tại vị trí gọi `service.execute("A")` **nằm trong** `Controller.submit()`:

- **This của mã đang thực thi tại chỗ gọi** là instance `Controller`.
- **Target của lời gọi `execute`** là instance mà `service` tham chiếu.
- **Args** chứa `"A"`.

Nếu một mô hình AOP expose cả this và target tại method-call join point, hai giá trị này thường là **hai đối tượng khác nhau**. Đây là lý do tên “đối tượng thực thi” không được tự động đồng nhất với đối tượng “bị gọi”.

### 5.2 Tại method-execution join point

Khi phần thân `ServiceImpl.execute` chạy:

~~~java
class ServiceImpl implements Service {
    @Override
    public void execute(String id) {
        System.out.println(this.getClass().getSimpleName());
    }
}
~~~

Đây là mã minh họa, giả sử giao diện `Service` tồn tại.

Ở **execution của phương thức instance**, `this` của thân phương thức là đối tượng `ServiceImpl` đang thực thi. Target của execution, nếu mô hình hỗ trợ khái niệm ấy, thông thường cũng là đối tượng đang chạy thân phương thức. Trong trường hợp gọi qua proxy hoặc công cụ tạo mã, cách mô hình hóa `this` và `target` phải xem hợp đồng cụ thể; không suy từ một biến `proxy` trong handler ra mọi execution join point.

### 5.3 Tại static method và static context

~~~java
static void refreshAll() {
    // Không có this của một instance ở thân phương thức static.
}
~~~

Vì không có `this` instance, điều kiện pointcut đòi một object executing-this có thể không khớp hoặc không hợp lệ cho điểm này, tùy mô hình. Đừng thay một `Class` object vào vị trí instance target mà không có định nghĩa rõ.

### 5.4 Bảng đối chiếu

| Loại điểm | This / executing object | Target | Args |
| --- | --- | --- | --- |
| Gọi instance method từ thân instance method khác | Instance bên gọi tại vị trí phát sinh call | Instance nhận lời gọi | Đối số truyền cho lời gọi |
| Thực thi thân instance method | Instance đang chạy thân phương thức | Thông thường chính instance đó, nếu được expose | Tham số của phần thực thi |
| Gọi instance method từ static context | Không có caller-instance `this` | Instance nhận lời gọi | Đối số |
| Gọi static method | Không có receiver instance theo nghĩa instance target | Tùy mô hình, thường không có instance target | Đối số của static method |
| Proxy invocation handler | Không suy máy móc từ `proxy` | Object nghiệp vụ do handler giữ có thể khác proxy | Các đối số handler nhận |

Bảng mô tả **ngữ nghĩa khái niệm**. Không phải mọi nền tảng đều định nghĩa mỗi hàng thành một loại join point có thể weave advice.

## 6. Context binding vào advice và quan hệ với pointcut

Có hai trách nhiệm độc lập:

1. **Pointcut selection:** quyết định **điểm/lần gọi nào** khớp.
2. **Context binding:** quyết định **những giá trị nào** được truyền vào advice sau khi khớp.

Một số mô hình pointcut có thể vừa lọc theo kiểu runtime vừa bind dữ liệu. Giả mã:

~~~text
structuralCondition = method execution of process(...)
runtimeCondition    = target is instance of SpecialService
argumentCondition   = amount > 0

pointcut = structuralCondition
           AND runtimeCondition
           AND argumentCondition

advice receives (target, amount, invocationInfo)
~~~

Đây không phải cú pháp một thư viện; phần chọn xác định tập điểm chịu tác động, phần binding cung cấp thông tin cụ thể của mỗi lần thực thi.

Ví dụ một advice đo thời gian **không cần lọc theo giá trị** nhưng vẫn có thể bind tên phương thức để đặt tên metric. Ngược lại, một pointcut chỉ khớp tham số có kiểu runtime đặc biệt cần đánh giá điều kiện động nhưng không bắt buộc advice phải ghi nội dung của tham số đó.

### 6.1 Khi nào nên chọn theo target, this hay args?

- Muốn theo dõi **mọi thao tác trên một nhóm lớp đích**: nghĩ đến target và phạm vi cấu trúc tương ứng.
- Muốn theo dõi **các điểm phát sinh từ một nhóm caller**: cân nhắc this ở loại **call** phù hợp; phải xác minh những call join point thực sự được hỗ trợ.
- Muốn đo hoặc kiểm toán **theo dữ liệu yêu cầu**: dùng args hoặc context được bind, nhưng lọc/chuyển đổi an toàn.
- Muốn áp dụng hành vi tại **phương thức được khai báo** ở interface hoặc lớp cụ thể: ưu tiên khái niệm chữ ký/declaring type; đừng thay bằng runtime type khi yêu cầu là tĩnh.
- Muốn **kiểm soát quyền**: chọn tất cả điểm cần bảo vệ rồi kiểm tra danh tính đã được xác thực và tài nguyên trong policy; không chỉ chọn các lần đã có quyền khiến những lần không đủ quyền bỏ qua kiểm tra.

## 7. Ví dụ Java 17 chạy độc lập: proxy, target, caller và args

Để thấy rõ ranh giới, ví dụ dưới sử dụng **Java dynamic proxy**. Nó thể hiện cách một lớp chặn lời gọi **qua interface** nhận `Method`, target và args. Đây **không phải hệ thống AOP chung**: lớp proxy không tự expose `this` của caller, và các dòng quan sát caller được in trực tiếp trong phương thức bên gọi để làm rõ đối tượng đang thực thi ở call site.

Lưu file `AdviceContextDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AdviceContextDemo {
    interface Task {
        String run(String id, int attempts);
    }

    static final class TaskImpl implements Task {
        @Override
        public String run(String id, int attempts) {
            System.out.println("BODY this="
                    + getClass().getSimpleName()
                    + " id=" + id + " attempts=" + attempts);
            return id + ":" + attempts;
        }
    }

    static final class Caller {
        private final Task task;

        Caller(Task task) {
            this.task = task;
        }

        String invoke(String id, int attempts) {
            System.out.println("CALLER this="
                    + getClass().getSimpleName());
            return task.run(id, attempts);
        }
    }

    static Object invokeTarget(Task target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static Task weave(Task target) {
        return (Task) Proxy.newProxyInstance(
                Task.class.getClassLoader(),
                new Class<?>[] { Task.class },
                (proxy, method, args) -> {
                    Object[] actualArgs =
                            args == null ? new Object[0] : args.clone();

                    System.out.println("ADVICE methodDeclared="
                            + method.getDeclaringClass().getSimpleName());
                    System.out.println("ADVICE target="
                            + target.getClass().getSimpleName()
                            + " proxyIsTarget=" + (proxy == target));
                    System.out.println("ADVICE args="
                            + actualArgs[0] + "," + actualArgs[1]);

                    return invokeTarget(target, method, actualArgs);
                });
    }

    public static void main(String[] args) {
        TaskImpl original = new TaskImpl();
        Task task = weave(original);
        Caller caller = new Caller(task);

        System.out.println("RESULT " + caller.invoke("alpha", 2));
        System.out.println("DIRECT");
        System.out.println("RESULT " + original.run("beta", 1));
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac AdviceContextDemo.java
java AdviceContextDemo
~~~

Stdout xác định của chương trình:

~~~text
CALLER this=Caller
ADVICE methodDeclared=Task
ADVICE target=TaskImpl proxyIsTarget=false
ADVICE args=alpha,2
BODY this=TaskImpl id=alpha attempts=2
RESULT alpha:2
DIRECT
BODY this=TaskImpl id=beta attempts=1
RESULT beta:1
~~~

### 7.1 Đọc từng dòng

**`CALLER this=Caller`**: trong thân `Caller.invoke`, `this` là instance của `Caller`. Đây là cách chương trình Java **tự in this tại call site**; dynamic proxy không tự nhận được object Caller qua một tham số `this` của handler.

**`ADVICE methodDeclared=Task`**: handler nhận `Method` được khai báo tại interface `Task`. `Method.getDeclaringClass()` chỉ nói về khai báo của `Method`, không phải lớp runtime của target.

**`ADVICE target=TaskImpl proxyIsTarget=false`**: handler đang giữ object nghiệp vụ `TaskImpl`; biến `proxy` là object đại diện khác. Trong ví dụ này, `target` được xác định **tường minh bởi closure của handler**, không phải suy ra từ tên lớp proxy.

**`ADVICE args=alpha,2`**: tham số đúng của lần gọi qua proxy gồm chuỗi `alpha` và số nguyên `2`. Vì Reflection/Proxy biểu diễn primitive qua wrapper trong `Object[]`, giá trị 2 tương ứng `Integer` tại đây.

**`BODY this=TaskImpl...`**: khi `TaskImpl.run` thực thi, `this` của thân phương thức chính là object `TaskImpl`.

**Nhánh `DIRECT`**: lời gọi trực tiếp `original.run` không đi qua proxy, nên không có dòng `ADVICE`; điều đó minh họa **độ bao phủ của cơ chế can thiệp**, không nói rằng lời gọi trực tiếp không có arguments hoặc target.

Ví dụ này không xác định syntax cho các pointcut `this`/`target`/`args` của mọi mô hình AOP. Nó chỉ minh họa ba dạng thông tin bằng chương trình Java chạy được.

### 7.2 Điều gì thay đổi khi có nhiều proxy?

Nếu một proxy bao ngoài proxy khác, “object nhận lời gọi” ở mỗi biên có thể là một proxy khác nhau. Một advice bên ngoài có thể biết loại runtime của proxy kế tiếp; một advice ở gần nghiệp vụ hơn có thể biết target gốc. **Không có một object target phổ quát độc lập với vị trí can thiệp**.

Vì thế khi test, cần ghi rõ:

- Điểm gọi nào đã được instrument?
- `this` thuộc đoạn mã nào?
- `target` trong hợp đồng công cụ chỉ đối tượng nhận ở biên nào?
- `args` là tham số trước hay sau khi một advice bên ngoài đã biến đổi chúng?
- Khi chuyển tiếp, giá trị trả về và ngoại lệ có được giữ đúng hợp đồng hay không?

## 8. Nhận ngữ cảnh ở before, after và around advice

Không phải mọi dữ liệu có thể đọc tại mọi thời điểm.

| Dạng advice | Dữ liệu có thể cần | Dữ liệu/chức năng cần lưu ý |
| --- | --- | --- |
| Before | Method signature, target/this, args trước thực thi | Chưa có kết quả của lần thực thi |
| After returning | Dữ liệu join point và kết quả thành công nếu cơ chế expose | Không chạy trên nhánh lỗi theo nghĩa after-success |
| After throwing | Dữ liệu join point và ngoại lệ nếu được expose | Không có kết quả thành công; phải truyền tiếp lỗi khi cần |
| After / finally | Dữ liệu chung và trạng thái hoàn thành phù hợp | Có thể chạy khi thành công hoặc lỗi; cleanup phải an toàn |
| Around | Context, args, tiếp tục `proceed`, kết quả hoặc ngoại lệ | Có thể chặn, biến đổi, gọi tiếp nhiều lần nếu được hỗ trợ |

**Around advice** thường có quyền tác động mạnh hơn: nó có thể chọn **không gọi tiếp** rồi trả giá trị cache hoặc ném lỗi. Khi đó một advice nằm bên trong có thể không được thực thi, và kết quả trả về có thể không xuất phát từ thân nghiệp vụ. Ngược lại, lời gọi `proceed()` có thể kích hoạt thêm các advice bên trong trước khi tới phương thức đích thật.

Khi phân tích ngữ cảnh, hãy nhớ **object target được cung cấp bởi một API không chứng minh thân phương thức gốc đã chạy**; quanh advice khác có thể đã short-circuit.

## 9. Các trường hợp nâng cao dễ nhầm

### 9.1 `this` trong advice không tự đồng nhất với `this` ở join point

Bên trong **mã của aspect/advice**, `this` của ngôn ngữ Java (nếu advice là một instance method trong một object aspect) có thể trỏ tới **instance của aspect**. Nó không tự nhiên trở thành `this` của lớp nghiệp vụ.

Nếu ngôn ngữ pointcut có biểu thức expose **this của join point**, đó là **giá trị ngữ cảnh được bind** theo hợp đồng của AOP, khác với từ khóa `this` theo cú pháp bên trong thân Java của advice.

### 9.2 Static method và không có receiver

Với `Math.abs(-3)` hoặc một phương thức static tự viết, không có receiver instance làm target giống lời gọi instance. Ngay cả khi có một `Class` object mô tả lớp chứa phương thức, nó **không tự là một target object của lời gọi static** theo cùng ý nghĩa.

### 9.3 Constructor và object initialization

Với constructor, câu hỏi “đối tượng đích tồn tại lúc nào” phụ thuộc giai đoạn: **trước khi tạo, đang khởi tạo, sau khởi tạo**. Một số mô hình AOP có join point constructor call/execution/initialization riêng. Không lấy quy tắc của method-execution instance thông thường áp dụng máy móc cho mọi giai đoạn khởi tạo.

### 9.4 Generic, overload, bridge và phương thức sinh

Một pointcut dựa trên chữ ký `process(String)` có thể khác pointcut chọn `process(Object)`. Với Java generics, compiler có thể tạo **bridge method** sau type erasure. Reflection có thể thấy cả bridge và phương thức chuyên biệt, nhưng **không thể suy** một bộ AOP sẽ expose hai execution join point hoặc luôn chạy advice hai lần.

Args runtime của `String` vẫn là giá trị chuỗi thực tế; thông tin kiểu generic như `List<String>` thường không tạo một runtime class riêng để match. Cần phân biệt **kiểu trong chữ ký**, **runtime class của đối số** và **danh mục join point của nền tảng**.

### 9.5 Self-invocation và đường gọi bỏ qua proxy

Nếu một phương thức nghiệp vụ gọi một phương thức khác trên `this` bên trong object gốc, lời gọi đó **có thể không đi qua proxy ngoài**. Advice được cài ở proxy vì thế có thể bỏ lỡ lần gọi nội bộ. Nhưng với kỹ thuật weaving ở bytecode, điểm execution tương ứng có thể vẫn được quan sát.

Điều này nhấn mạnh rằng **ngữ cảnh đúng không thay thế phạm vi can thiệp đúng**. Có thể biết một target phù hợp mà vẫn không có advice nào chạy vì đường gọi không đi qua vị trí đã được instrument.

### 9.6 Control flow, thread và tác vụ bất đồng bộ

Một advice ở điểm đồng bộ có thể đọc target và args khi lời gọi còn sống. Nếu công việc tiếp tục trên thread hoặc task khác, không mặc định rằng các giá trị context gắn với luồng sẽ tự truyền sang đó. Cần quy định cách truyền correlation ID, danh tính và những dữ liệu được phép dùng qua ranh giới bất đồng bộ.

Giữ lại một tham chiếu tới target hoặc args trong hàng đợi log có thể kéo dài vòng đời của object và làm lộ dữ liệu. Đối với hệ thống truy vết, nên chuyển dữ liệu sang một cấu trúc sự kiện tối thiểu, bất biến và được bảo vệ đúng phạm vi.

## 10. Bảo mật và tính đúng đắn khi dùng ngữ cảnh

### 10.1 Target đúng không tự chứng minh quyền

Kiểm tra `target instanceof SensitiveService` chỉ xác định loại đối tượng. Nó **không xác thực người dùng**, không xác định người ấy có quyền truy cập tài nguyên cụ thể và không ngăn đường gọi không nằm trong phạm vi advice.

Đối với chính sách bắt buộc, cần chọn đủ điểm cần bảo vệ, kiểm tra chủ thể đã được xác thực và tài nguyên thực sự, chặn trước tác dụng phụ, đồng thời kiểm chứng mọi đường vào. Không nên đưa điều kiện “người dùng đã có quyền” vào pointcut rồi vô tình để lời gọi không có quyền **bỏ qua advice kiểm tra**.

### 10.2 Arguments có thể bị sửa trong khi đang xử lý

Nếu đối tượng tham số mutable được truyền chung qua các lớp, một advice có thể đọc trạng thái trước khi nghiệp vụ thay đổi hoặc sau khi advice khác đã thay đổi. Muốn log trạng thái như lúc yêu cầu đến, phải xác định thời điểm chụp snapshot và chiến lược sao chép phù hợp.

`args.clone()` chỉ tạo **bản sao nông của mảng**. Nó không clone các object bên trong, không tự bảo vệ khỏi dữ liệu thay đổi và không giải quyết quyền truy cập.

### 10.3 Lựa chọn trường dữ liệu an toàn

Bản ghi log nên ưu tiên:

- Tên thao tác hoặc chữ ký cần thiết.
- Correlation ID/trace ID không nhạy cảm và được quản lý đúng.
- Mã phân loại trạng thái thành công/lỗi.
- Những tham số đã được whitelist, chuẩn hóa hoặc che giá trị nhạy cảm.
- Chỉ danh tính đã xác thực từ nguồn tin cậy, với phạm vi retention phù hợp.

Đừng để advice tự gọi `toString()` trên mọi target/args mà không kiểm soát. Đôi khi hành vi này đắt, đệ quy hoặc có tác dụng phụ.

## 11. Kiểm thử binding và phạm vi pointcut

Một ma trận kiểm thử tốt phải xác minh đồng thời **điểm được chọn** và **giá trị được bind**.

| Trường hợp | Args | Target | This/executing object | Điều cần kiểm chứng |
| --- | --- | --- | --- | --- |
| Gọi instance method từ một instance khác | Đúng thứ tự và giá trị | Object nhận lời gọi | Object phía caller ở điểm call | Không đánh đồng caller với receiver |
| Execution của instance method | Tham số của lần chạy | Object đang thực thi theo định nghĩa mô hình | Thường cùng object ở thân instance method | Phân biệt call/execution |
| Gọi từ static context | Vẫn có args | Đích instance nếu là instance method | Không có caller `this` | Không giả định this khác null |
| Static method | Args theo chữ ký | Không có instance target thông thường | Không có executing instance | Không gọi `getClass()` trên null |
| Lời gọi qua proxy | Args do handler nhận | Proxy hay target gốc tùy ranh giới | Caller không tự xuất hiện trong handler | Phân biệt `proxy` và `target` |
| Lời gọi trực tiếp object gốc | Có args và target | Object thật | Phụ thuộc điểm gọi | Proxy advice có thể không chạy |
| Args chứa null | Một phần tử null | Target không đổi | Không liên quan | Không cố lấy runtime class của null |
| Overload/generic | Chữ ký có thể khác | Phụ thuộc lời gọi | Phụ thuộc điểm | Bind đúng mảng args và kiểu |
| Nhiều advice | Có thể đã bị biến đổi trước khi vào lớp trong | Mỗi lớp nhìn theo ranh giới | Phụ thuộc call/execution | Không mặc định tất cả thấy cùng context |
| Chuyển sang task khác | Có thể phải truyền tường minh | Có thể chỉ truyền ID thay object | Thread context có thể đổi | Không rò dữ liệu hoặc giữ tham chiếu quá lâu |

Khi dùng framework/công cụ AOP thực tế, nên kiểm tra riêng:

1. Nó hỗ trợ **call join point**, **execution join point** hay chỉ một loại?
2. Nó định nghĩa `this`, `target`, `args` như thế nào ở mỗi loại?
3. Chữ ký được bind là từ interface, lớp khai báo hay method thực thi?
4. Có bind được **giá trị đối số** hay chỉ đọc metadata chữ ký?
5. Có khả năng **thay đổi args** khi `proceed` không, và nếu có thì cách ánh xạ thế nào?
6. Có điểm nào không có target hoặc this không?
7. Proxy, self-invocation, bridge methods và async có làm thay phạm vi không?
8. Advice có giữ nguyên kết quả, ngoại lệ và các bất biến nghiệp vụ không?

## 12. Những lỗi hiểu sai phổ biến

**Lỗi 1: Coi args là kiểu tham số được khai báo.** Args là giá trị thực tế của lần thực thi; chữ ký phương thức mô tả loại tham số tĩnh. Hai lời gọi cùng phương thức có args khác nhau.

**Lỗi 2: Coi target là một tham số bất kỳ.** Một object có thể được truyền vào như tham số `service` nhưng target của lời gọi hiện tại lại là `controller`. Target chỉ xác định theo **join point đang xét**.

**Lỗi 3: Coi this và target luôn giống nhau.** Ở method call từ một instance khác, this có thể là caller và target là receiver. Ở method execution thông thường, chúng có thể trùng. Cần biết loại điểm.

**Lỗi 4: Coi `this` trong thân advice là `this` của nghiệp vụ.** Từ khóa Java trong mã advice có thể trỏ tới aspect instance. Ngữ cảnh `this` của join point phải được expose/bind riêng.

**Lỗi 5: Coi proxy chính là object nghiệp vụ.** Runtime class của proxy có thể khác target. Lớp `Method` do proxy cung cấp cũng có thể là interface.

**Lỗi 6: Cho rằng đủ args sẽ tự khớp pointcut.** Binding không đồng nghĩa selection. Pointcut cần điều kiện chọn rõ ràng, và cơ chế weaving phải thực sự quan sát được điểm.

**Lỗi 7: Cho rằng static method có target object như instance method.** Lời gọi static không có receiver instance theo nghĩa thông thường.

**Lỗi 8: Cứ sửa mảng args là sửa được lời gọi thật.** Khả năng này phải được nền tảng định nghĩa; thay đổi bản sao mảng không tự thay đổi dữ liệu ở target.

**Lỗi 9: In hết target và args để debug.** Có thể gây rò thông tin, log quá lớn, tác dụng phụ `toString()` và rò vòng đời object.

**Lỗi 10: Thấy advice chạy qua proxy thì mọi đường gọi khác cũng chịu advice.** Direct call và self-invocation có thể đi ngoài proxy.

## 13. Tình huống tự luyện

Giả sử có:

~~~java
class Controller {
    private final Service service;

    Controller(Service service) {
        this.service = service;
    }

    void submit(String id) {
        service.save(id);
    }
}
~~~

Đây là **mảnh minh họa**, giả định `Service` có phương thức instance `save(String)`.

**Câu 1.** Tại điểm **call** của `service.save(id)`, this là gì?

**Đáp:** nếu đây là instance method call join point mà mô hình có expose this, nó là object `Controller` đang chạy `submit`.

**Câu 2.** Tại điểm **call**, target là gì?

**Đáp:** object nhận lời gọi `save`, tức đối tượng mà `service` đang tham chiếu (có thể là proxy ở ranh giới bên gọi).

**Câu 3.** Args gồm gì?

**Đáp:** giá trị hiện tại của biến `id` được truyền cho `save`, theo chữ ký của lời gọi.

**Câu 4.** Tại **execution** của thân `ServiceImpl.save`, this là gì?

**Đáp:** object `ServiceImpl` đang thực thi thân instance method, nếu cơ chế expose điểm đó.

**Câu 5.** Nếu `id == null`, có lấy `id.getClass()` để match runtime type không?

**Đáp:** không; null không có lớp runtime. Có thể vẫn có thông tin declared type `String` trong chữ ký.

**Câu 6.** Nếu `service` trỏ tới proxy và handler giữ `ServiceImpl`, `proxy.getClass()` có chắc là `ServiceImpl.class` không?

**Đáp:** không. Đó là hai object khác nhau trong ví dụ proxy thông thường.

**Câu 7.** Nếu `ServiceImpl.save` gọi `this.audit(id)` ở thân phương thức, advice chỉ có ở proxy có chắc thấy lời gọi `audit` này không?

**Đáp:** không. Lời gọi nội bộ có thể không đi qua proxy. Cần kiểm tra cơ chế can thiệp thực tế.

## 14. Tổng kết

Để nhận đúng dữ liệu trong advice, hãy luôn trả lời **bốn câu hỏi**:

1. **Đang ở loại join point nào?** `call`, `execution` hay một loại khác mà mô hình hỗ trợ?
2. **Args thuộc lời gọi nào?** Giá trị thực tế, thứ tự, nullability và loại dữ liệu của chính lần thực thi?
3. **Target là object nào?** Receiver tại ranh giới nào, proxy hay target nghiệp vụ gốc?
4. **This là object nào?** Đối tượng đang thực thi mã tại điểm nối, có thể là caller ở call join point hoặc object nghiệp vụ ở execution join point?

**Kết luận:** `args` trả lời **“truyền những gì?”**; `target` trả lời **“thao tác hướng tới object nào?”**; `this` trả lời **“mã của object nào đang được thực thi ở điểm này?”**. Khi advice phân biệt được ba nguồn ngữ cảnh, việc ghi log, truy vết, chọn pointcut và kiểm soát hành vi sẽ chính xác hơn, không bị nhầm lẫn giữa giao diện, proxy, đối tượng đích và bên gọi.
