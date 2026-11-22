# Chọn theo kiểu của đối tượng đang thực thi và đối tượng đích trong AOP

## 1. Bài toán: hai đối tượng trong cùng một điểm can thiệp

Khi thiết kế pointcut cho **Aspect-Oriented Programming (AOP)**, không phải lúc nào chỉ tên phương thức hoặc lớp khai báo cũng đủ xác định vị trí áp dụng advice. Trong một lần gọi phương thức instance, có thể tồn tại ít nhất hai vai trò đối tượng:

- **Đối tượng đang thực thi (currently executing object, thường gọi là `this` theo mô hình join point):** đối tượng chứa ngữ cảnh instance của mã đang chạy ở điểm can thiệp.
- **Đối tượng đích (target object):** đối tượng nhận lời gọi hoặc là đối tượng chịu tác động trực tiếp của thao tác tại join point.

Hai đối tượng có thể **khác nhau tại method-call join point** nhưng thường **trùng nhau tại method-execution join point** của một phương thức instance. Vì vậy, việc chọn pointcut dựa trên loại đối tượng phải đi kèm câu trả lời: **join point nằm ở phía caller hay bên trong phần mã đang thực thi của callee?**

Ví dụ:

~~~text
Client (đang thực thi send())
    │
    └──► Service.execute()
              │
              └──► logic nghiệp vụ
~~~

Ở **method call join point** tại câu lệnh gọi bên trong `Client.send()`, đối tượng đang thực thi là instance `Client`, còn đối tượng đích là instance `Service`. Ở **method execution join point** của `Service.execute()`, phương thức thuộc chính đối tượng `Service` đang chạy; khi đó `this` và `target` cùng biểu thị receiver `Service` theo ngữ nghĩa AOP tương ứng.

Đây là kiến thức **pointcut theo ngữ cảnh động**, khác với chọn điểm chỉ dựa vào tên phương thức, vị trí mã hay chữ ký tĩnh. Những ví dụ `this(Type)` và `target(Type)` trong bài dùng **AspectJ** làm một ngôn ngữ AOP minh họa có mô hình join point rõ ràng. Không phải mọi công cụ AOP đều có hai toán tử này hoặc hỗ trợ cả call và execution. Phải kiểm tra cơ chế weaving/interception của công cụ cụ thể.

## 2. Khái niệm nền: join point, pointcut và advice

| Khái niệm | Nội dung cần nhớ |
|---|---|
| **Join point** | Một sự kiện hoặc vị trí trong quá trình chạy mà mô hình AOP hỗ trợ nhận diện, chẳng hạn method call, method execution hoặc field access. |
| **Pointcut** | Một điều kiện chọn một tập join point. Có thể xét chữ ký, kiểu, phạm vi mã và thông tin runtime. |
| **Advice** | Hành vi được thực thi tại join point phù hợp, ví dụ before, after hoặc around. |
| **Caller** | Mã thực hiện lời gọi phương thức. Khi mã caller nằm trong instance method, có thể có đối tượng đang thực thi ở phía caller. |
| **Receiver / callee** | Đối tượng nhận lời gọi instance; đó là target ở method-call join point trong mô hình xét ở đây. |
| **Context binding** | Khả năng cho advice nhận được chính đối tượng/đối số của join point phù hợp, thay vì chỉ biết điểm đã khớp. |

Cần phân biệt **một loại đối tượng (type)** với **một instance cụ thể**. Điều kiện `target(Service)` thường là kiểm tra quan hệ kiểu lúc chạy, tương tự ý tưởng `receiver instanceof Service`; nó không mặc định có nghĩa “đúng instance `service` này”. Nếu muốn một đối tượng cụ thể, phải có bước so sánh danh tính hoặc một điều kiện ngữ cảnh được công cụ hỗ trợ.

Cũng cần phân biệt ba ý nghĩa của chữ “this”:

1. **`this` trong Java:** reference đến instance trong mã Java đang thực thi; không tồn tại trong static context.
2. **`this(Type)` trong ngôn ngữ pointcut:** điều kiện chọn join point dựa trên đối tượng đang thực thi tại join point; ngữ nghĩa tùy mô hình AOP.
3. **`this` viết trong thân một aspect/advice:** có thể là bản thân instance của aspect trong những ngôn ngữ có cú pháp Java-like, **không được tự suy ra là đối tượng đang được advice quan sát**.

Không nên dùng một từ “this” mà bỏ mất ranh giới giữa ba ngữ cảnh trên.

## 3. Phân biệt loại join point trước khi kiểm tra `this` và `target`

### 3.1. Method call: góc nhìn của nơi gọi

Giả sử mã Java:

~~~java
final class Client {
    void send(Service service) {
        service.execute();
    }
}
~~~

Đây là đoạn minh họa; cần định nghĩa `Service` và tạo caller để thành chương trình độc lập.

Tại **call join point** của biểu thức `service.execute()` bên trong `Client.send()`:

- Đối tượng `this` là **instance Client** đang chạy `send()`.
- Đối tượng `target` là **instance Service** mà biến `service` trỏ đến.
- Kiểu tĩnh của biểu thức `service` là **Service**; kiểu runtime của instance đó có thể là Service hoặc một subclass.
- Nếu advice được kích hoạt bởi `call(...)`, bộ dệt phải có khả năng chặn **vị trí lời gọi** đó; không phải một proxy bất kỳ đều cung cấp call join point tại source này.

Ví dụ bảng dự đoán:

| Biểu thức pointcut tại call join point | Nếu caller là Client, receiver là FastService extends Service |
|---|---|
| `this(Client)` | Khớp |
| `this(Service)` | Không khớp nếu Client không phải subtype Service |
| `target(Service)` | Khớp |
| `target(FastService)` | Khớp |
| `this(Client) && target(FastService)` | Khớp |
| `this(OtherClient) && target(FastService)` | Không khớp nếu caller không phải OtherClient |

Kết quả nói về **kiểu runtime của hai instance tại call join point**, không phải về package khai báo method hoặc kiểu static của biến. Nếu caller thực chất là subtype Client, `this(Client)` vẫn có thể khớp do quan hệ kế thừa.

### 3.2. Method execution: góc nhìn của phương thức đang chạy

Bây giờ xét chính thân phương thức:

~~~java
class Service {
    void execute() {
        // Tại đây instance Service đang thực thi.
    }
}
~~~

Ở **execution join point** của một phương thức instance trong mô hình AspectJ:

- `this` trỏ đến instance đang thực thi phương thức.
- `target` cũng chính là instance đó.
- `this(Service)` và `target(Service)` vì vậy thường cùng đúng hoặc cùng sai đối với kiểu Service ở join point này.

Nếu receiver là `FastService extends Service`, cả `this(Service)` và `target(Service)` đều có thể khớp vì `FastService` là subtype của Service. Điều kiện `this(Client)` không “nhớ” caller Client ở execution của Service; execution nằm bên trong đối tượng Service, trừ khi bản thân Service đồng thời thuộc type Client theo một cấu trúc khác.

**Kết luận chính:** muốn phân biệt *ai gọi* và *ai được gọi*, hãy xem xét **call join point**; chỉ ghép `this(Client) && target(Service)` tại **execution** không có nghĩa là “Client gọi Service”. Với execution của Service, cả hai điều kiện áp vào receiver đang thực thi nên thường không thể diễn tả caller bằng cách đó.

### 3.3. Field access: bên truy cập và object chứa trường

Trong mô hình AOP hỗ trợ **field get/set join point**, có thể có một đối tượng thực hiện thao tác đọc/ghi, và một đối tượng khác **sở hữu trường instance đang được truy cập**.

~~~java
class Sensor {
    int value;
}

class Dashboard {
    int read(Sensor sensor) {
        return sensor.value;
    }
}
~~~

Đây là đoạn minh họa. Ở điểm đọc `sensor.value` bên trong `Dashboard.read()`:

- `this` thuộc instance **Dashboard** đang chạy mã đọc trường.
- `target` thuộc instance **Sensor** có trường `value` được đọc, theo mô hình AOP hỗ trợ field access.

Một pointcut `get(int Sensor.value) && this(Dashboard) && target(Sensor)` là ý tưởng lựa chọn theo cả hai đối tượng trong một mô hình như AspectJ. Với các field **static**, không có receiver instance cho trường static; không thể sử dụng `target(Sensor)` như thể đang có một đối tượng Sensor cụ thể.

## 4. Mô hình trực quan: `this` và `target` ở ba điểm

~~~text
[Client instance]
   │  đang chạy Client.send()
   │
   ├─ JOIN POINT A: method CALL của service.execute()
   │      this   ───► Client instance
   │      target ───► Service instance
   │
   ▼
[Service instance]
   │  bắt đầu chạy Service.execute()
   │
   ├─ JOIN POINT B: method EXECUTION của Service.execute()
   │      this   ───► Service instance
   │      target ───► Service instance
   │
   │ đọc sensor.value
   │
   └─ JOIN POINT C: instance FIELD GET
          this   ───► Service instance
          target ───► Sensor instance
~~~

Sơ đồ mô tả **ngữ nghĩa** của các join point giả định. Chương trình chỉ có các join point đó nếu công cụ AOP hỗ trợ chúng và mã tương ứng nằm trong phạm vi weaving. Proxy chỉ chặn lời gọi qua đối tượng đại diện sẽ có khả năng quan sát khác với bytecode weaver có method-call, method-execution và field-access pointcut.

## 5. Pointcut theo kiểu runtime khác pointcut theo chữ ký tĩnh

Đây là nguồn nhầm lẫn lớn nhất khi sử dụng kế thừa/đa hình.

~~~java
Service service = new FastService();
service.execute();
~~~

Trong ví dụ này, **kiểu tĩnh** của biến là `Service`, nhưng **kiểu runtime** của receiver là `FastService`. Trong mô hình AspectJ:

- Một điều kiện loại `call(* Service.execute(..))` xem xét chữ ký của **call join point** và quy tắc giải quyết lời gọi tĩnh.
- Một điều kiện loại `target(FastService)` xem xét đối tượng **thực tại runtime**.
- Hai điều kiện có thể **cùng khớp** khi caller gọi qua kiểu Service mà receiver thực là FastService.
- Một `execution(* FastService.execute(..))` phụ thuộc thân phương thức thực được chọn và chữ ký execution, không đơn thuần kiểu runtime của biến nhận.

Ví dụ giả mã ý tưởng:

~~~text
Chọn mọi lời gọi execute qua hợp đồng Service
    nếu receiver runtime thuộc FastService:

    call to Service.execute
    AND target instance-of FastService
~~~

Điều kiện runtime có thể thay đổi giữa các lần thực thi **cùng một call site** nếu caller nhận các implementation khác nhau. Đây là điểm mạnh của pointcut theo ngữ cảnh đối tượng.

**Không đồng nhất subtype pattern với runtime test.** Một mẫu chữ ký `Service+` trong một ngôn ngữ có biểu diễn subtype pattern có nghĩa chọn chữ ký theo tập kiểu và quy tắc của ngôn ngữ đó. Nó không tự thay thế mọi trường hợp cần `target(Service)`. Khi một subclass **kế thừa nhưng không override** phương thức, thân thực thi có thể vẫn khai báo ở superclass trong khi receiver runtime là subclass.

## 6. Cú pháp `this(Type)` và `target(Type)` trong một mô hình AOP cụ thể

AspectJ cung cấp ví dụ được định nghĩa rõ cho hai pointcut designator:

~~~text
this(Type)
target(Type)
~~~

Chúng chọn join point theo đối tượng đang thực thi và đối tượng đích có kiểu tương thích với `Type`. Biểu thức có thể kết hợp bằng các phép toán logic:

~~~text
call(* example.Service+.execute(..))
    && this(example.Client)
    && target(example.FastService)
~~~

Đây là **mẫu cú pháp pointcut minh họa**, chưa phải chương trình Java 17 chạy bằng `javac`. Ý định: chỉ chọn lời gọi `execute` trong vùng chữ ký đã mô tả, khi mã gọi chạy trong instance Client và receiver thực thuộc FastService. Cú pháp tên package, wildcard và subtype phải theo chuẩn ngôn ngữ AOP được dùng.

Một ví dụ khác:

~~~text
execution(* example.Service+.execute(..))
    && target(example.FastService)
~~~

Ý định khác: chọn **thực thi** phương thức phù hợp khi đối tượng đang chạy là FastService. Nó không yêu cầu caller phải là Client, và vì thế có thể bắt các lần gọi từ nhiều nơi khác nếu các execution join point được weave.

Cần lưu ý một số bộ dệt có thể đơn giản hóa điều kiện dựa trên thông tin tĩnh khi kiểu chắc chắn đúng/sai; nhưng kết quả cuối vẫn phải tuân theo ngữ nghĩa chọn join point của công cụ. Không nên dựa vào việc một tool có tạo ra phép `instanceof` ở bytecode hay không để quyết định logic pointcut.

### 6.1. AND, OR và phủ định

Các ví dụ logic:

~~~text
this(Client) && target(FastService)
    → Caller runtime thuộc Client VÀ receiver runtime thuộc FastService.

this(Client) || target(FastService)
    → Ít nhất một điều kiện phù hợp.

target(Service) && !target(FastService)
    → Receiver thuộc Service nhưng không thuộc FastService.
~~~

Các biểu thức này chỉ minh họa ý nghĩa logic của **type matching**. Thứ tự đánh giá các điều kiện con và kỹ thuật tối ưu có thể do bộ dệt quyết định. Tránh đặt tác dụng phụ trong điều kiện động với giả định chúng luôn được đánh giá theo một thứ tự cụ thể.

### 6.2. Interface và subtype

Nếu **FastService implements Operation**, kiểm tra `target(Operation)` có thể đúng khi receiver là FastService, ngay cả khi caller giữ biến kiểu interface.

Nếu một đối tượng implement đồng thời hai interface, pointcut kiểm tra một trong hai interface đều có thể khớp. Điều này không phải “hai target khác nhau”; đó là **một instance có nhiều quan hệ kiểu**.

Nếu pointcut cần chọn **đúng lớp runtime cụ thể, không gồm subclass**, thì điều kiện dạng `target(Base)` thường chưa đủ vì type matching theo quan hệ subtype. Tùy công cụ, cần thêm kiểm tra chính xác runtime class hoặc cấu trúc loại trừ phù hợp. Phải cân nhắc các proxy/subclass được sinh động trước khi so sánh class tuyệt đối.

## 7. Ví dụ Java 17 có thể chạy: mô phỏng hai ngữ cảnh một cách tường minh

Để nhìn thấy loại đối tượng ở phía caller và phía target mà không cần trình dệt riêng, ví dụ này tự truyền hai đối tượng vào một bộ mô phỏng ghi nhận ngữ cảnh. **Nó không phải một công cụ weaving**: sự lựa chọn điểm quan sát được viết tường minh. Nó minh họa các quy tắc mà một engine AOP có thể dùng khi đánh giá `this(Type)` và `target(Type)`.

Tạo file **ObjectContextDemo.java**:

~~~java
public class ObjectContextDemo {
    interface Task {
        void run();
    }

    static class BaseTask implements Task {
        @Override
        public void run() {
            Context.execution(this, () -> System.out.println("BaseTask.run"));
        }
    }

    static class FastTask extends BaseTask {
        @Override
        public void run() {
            Context.execution(this, () -> System.out.println("FastTask.run"));
        }
    }

    static class Client {
        void send(Task target) {
            Context.call(this, target, target::run);
        }
    }

    static class Scheduler {
        void send(Task target) {
            Context.call(this, target, target::run);
        }
    }

    static class Context {
        static void call(Object caller, Object target, Runnable action) {
            System.out.println("CALL this=" + caller.getClass().getSimpleName()
                    + " target=" + target.getClass().getSimpleName());
            System.out.println("match=" + (caller instanceof Client
                    && target instanceof FastTask));
            action.run();
        }

        static void execution(Object receiver, Runnable body) {
            System.out.println("EXEC this=" + receiver.getClass().getSimpleName()
                    + " target=" + receiver.getClass().getSimpleName());
            body.run();
        }
    }

    public static void main(String[] args) {
        new Client().send(new BaseTask());
        new Client().send(new FastTask());
        new Scheduler().send(new FastTask());
    }
}
~~~

Biên dịch và chạy trên Java 17+:

~~~bash
javac --release 17 ObjectContextDemo.java
java ObjectContextDemo
~~~

Stdout chính xác:

~~~text
CALL this=Client target=BaseTask
match=false
EXEC this=BaseTask target=BaseTask
BaseTask.run
CALL this=Client target=FastTask
match=true
EXEC this=FastTask target=FastTask
FastTask.run
CALL this=Scheduler target=FastTask
match=false
EXEC this=FastTask target=FastTask
FastTask.run
~~~

**Phân tích:**

1. Ở lời gọi thứ nhất, caller là Client nhưng target là BaseTask. Điều kiện **caller thuộc Client AND target thuộc FastTask** sai.
2. Ở lời gọi thứ hai, caller vẫn là Client; target đã là FastTask nên hai điều kiện đều đúng. Lớp FastTask override `run()`, vì thế body FastTask.run thực thi.
3. Ở lời gọi thứ ba, target vẫn là FastTask, nhưng caller trở thành Scheduler. Điều kiện kết hợp sai vì `this(Client)` không đúng.
4. Tại phần mô phỏng **execution**, chương trình cố ý dùng **receiver** làm cả `this` lẫn `target`: đối tượng đang thực thi là BaseTask/FastTask tương ứng; nguồn gọi không còn là giá trị `this` của execution.

Khi viết một aspect thật, không cần tự gọi `Context.call`/`Context.execution` tại mỗi vị trí: bộ dệt có thể đảm nhận việc đó nếu loại join point và phạm vi được hỗ trợ. Nhưng mô phỏng này giúp phân biệt **logic chọn đối tượng** với **cơ chế tự động can thiệp**. Kết quả của một engine thật còn tùy kỹ thuật weaving, pointcut và chính sách khớp metadata.

## 8. Khi `this` và `target` trùng nhau

Chúng thường trùng ở **method-execution join point** của phương thức instance: chính receiver đang thực thi thân đó. Ngoài ra, tại một lời gọi nội bộ trên cùng object, ví dụ `this.otherMethod()`, hai vai trò ở **call join point** cũng có thể cùng chỉ về một instance.

~~~java
class Worker {
    void first() {
        second();
    }

    void second() {
        // Logic xử lý
    }
}
~~~

Đây là đoạn minh họa. Trong `first()`, lời gọi `second()` trên cùng object có **caller instance** và **receiver instance** là một.

Điều này **không làm mất ý nghĩa** hai designator: chúng vẫn trả lời hai câu hỏi khác nhau. Việc cả hai cùng đúng ở một số tình huống không cho phép coi `this(Type)` và `target(Type)` tương đương trong mọi loại join point.

Đặc biệt khi dùng proxy chặn method-call, lời gọi **self-invocation** bên trong target có thể không đi qua proxy nên advice của proxy **không chạy**, dù đối tượng Java vẫn có cả ngữ cảnh caller và target. Hai vấn đề độc lập:

- Ngữ nghĩa runtime của các đối tượng hiện diện.
- Cơ chế AOP có thực sự intercept được join point đó hay không.

## 9. Khi `this` không tồn tại hoặc không có target instance

### 9.1. Phương thức static

Trong Java, mã static không có `this` của instance. Với một **static method execution join point**, cũng không có receiver object theo nghĩa gọi phương thức instance; một pointcut bắt buộc `this(SomeClass)` hoặc `target(SomeClass)` không nên được kỳ vọng khớp như thể có một object tương ứng.

Xét mã minh họa:

~~~java
class Utility {
    static void check() {
        // Không có "this" của instance tại đây.
    }
}
~~~

Nếu mục tiêu là quan sát `Utility.check()`, thường phải dùng **chữ ký static/execution** hoặc điều kiện lexical thích hợp; không thể dùng `target(Utility)` để thay cho “method thuộc lớp Utility”.

### 9.2. Lời gọi instance phát ra từ static context

~~~java
class JobLauncher {
    static void launch(Task target) {
        target.run();
    }
}
~~~

Đây là đoạn minh họa, `Task` là một interface đã biết trong phạm vi ví dụ. Ở **call join point** của `target.run()` bên trong static method:

- Không có `this` instance của `JobLauncher`.
- Vẫn có đối tượng target nhận lời gọi, ví dụ một FastTask.

Vì thế `target(FastTask)` có thể khớp nhưng `this(JobLauncher)` không tự khớp vì source nằm trong lớp đó. Để chọn theo **nơi mã được khai báo**, cần điều kiện lexical như `within(JobLauncher)` hoặc `withincode(...)` ở mô hình hỗ trợ.

### 9.3. Một số join point khác

Constructor call/execution, static initialization, handler execution và các dạng advice execution có quy tắc availability của `this`/`target` riêng. Không nên mở rộng bảng method call/execution một cách máy móc sang mọi join point.

Nếu không có target object tại loại join point đã chọn, biểu thức `target(T)` không có instance để kiểm tra. Một bộ dệt có thể bỏ qua điểm đó vì không thể khớp, hoặc áp dụng ngữ nghĩa đặc thù đã được định nghĩa. Khi thiết kế pointcut, luôn tra **join point model** của engine.

## 10. Phân biệt `this`, `target`, `args` và vùng lexical

Các pointcut designator thường gặp có nhiệm vụ khác nhau:

| Điều kiện | Câu hỏi nó trả lời |
|---|---|
| **this(T)** | Đối tượng đang thực thi tại join point có thuộc T không? |
| **target(T)** | Đối tượng đích của join point có thuộc T không? |
| **args(T)** | Đối số của join point có tương thích kiểu T ở vị trí tương ứng không? |
| **within(T)** | Mã chứa join point có nằm trong khai báo kiểu T không? |
| **withincode(...)** | Join point có nằm trong thân method/constructor có chữ ký phù hợp không? |
| **call(...)** | Tại đây có một lời gọi với chữ ký thỏa điều kiện không? |
| **execution(...)** | Tại đây thân method có chữ ký phù hợp đang được thực thi không? |

Ví dụ ba thao tác tương tự về bề ngoài nhưng khác nghĩa:

~~~text
this(Client)        : object caller/current execution context là Client.
target(Client)      : receiver/target object là Client.
within(Client)      : mã chứa join point nằm về mặt lexical trong Client.
~~~

Một method **kế thừa** từ Base đang thực thi trên instance Child có thể khiến:

- `this(Child)` và `target(Child)` cùng đúng tại execution nếu receiver là Child.
- `within(Child)` không nhất thiết đúng cho thân method **khai báo trong Base**.
- Chỉ thấy tên Child ở runtime không đủ suy ra phạm vi lexical của body.

### 10.1. Một phản ví dụ thường gặp

Ý định: “Chỉ áp dụng advice khi Client gọi vào Service”.

Sai về mặt mô hình nếu viết:

~~~text
execution(* Service.execute(..))
    && this(Client)
    && target(Service)
~~~

Tại execution của method Service instance, `this` gắn với chính Service. Điều kiện `this(Client)` không diễn tả caller Client và thường khiến pointcut không khớp trong kiến trúc Client/Service tách biệt.

Nếu mô hình hỗ trợ method-call join point tại caller, một ý tưởng phù hợp hơn là:

~~~text
call(* Service.execute(..))
    && this(Client)
    && target(Service)
~~~

Hoặc nếu ý định thật là “mọi execution Service mà lời gọi bên ngoài xuất phát từ Client”, cần một **điều kiện theo luồng điều khiển** hoặc truyền **request context** theo cơ chế phù hợp, chứ không đồng nhất đối tượng `this` của execution với caller từ một khung stack khác. Các cơ chế theo control flow cũng phải cân nhắc nested calls, chi phí và asynchronous execution.

## 11. Kết hợp với điều kiện theo luồng thực thi

Đôi khi mong muốn không phải “caller ngay tại call site thuộc T” mà là “đang ở **bên trong chuỗi xử lý được bắt đầu bởi** một thao tác trên T”.

Một số ngôn ngữ AOP cung cấp khái niệm **cflow** (control flow) để diễn đạt join point hiện tại nằm trong luồng động của một điểm khác. Ví dụ ý tưởng:

~~~text
execution of Service.execute
AND within dynamic control flow of Client.handle
~~~

Khác biệt quan trọng:

- `this(Client)` ở execution của Service **không tự mang lại** caller Client.
- Một điều kiện control flow có thể chọn execution Service khi nó xảy ra trong ngữ cảnh động có liên quan đến Client.
- Control flow có thể chứa nhiều lớp trung gian, nhiều lời gọi lồng nhau hoặc recursion; cần xác định có bao gồm chính điểm bắt đầu hay không.

**Async boundary:** một callback chạy ở thread khác hoặc vào thời điểm sau khi call stack ban đầu kết thúc có thể không còn cùng control flow thông thường. Nếu cần theo yêu cầu xuyên thread, hãy dùng cơ chế truyền context/trace identity thích hợp; không giả định `this` hay `cflow` tự lan truyền sang mọi tác vụ bất đồng bộ.

## 12. Binding: lấy chính đối tượng được match để dùng trong advice

Một pointcut không chỉ có thể trả về đúng/sai; trong những mô hình hỗ trợ, nó còn **ràng buộc reference** của đối tượng liên quan cho advice.

Ví dụ cú pháp minh họa kiểu AspectJ:

~~~java
// Minh họa cú pháp advice của một ngôn ngữ AOP,
// không phải lớp Java độc lập biên dịch bằng javac.

before(Object current, Object receiver):
        call(* example.Service+.execute(..))
        && this(current)
        && target(receiver) {
    System.out.println(current.getClass().getSimpleName()
            + " -> " + receiver.getClass().getSimpleName());
}
~~~

Ví dụ diễn tả việc lấy đối tượng đang thực thi và receiver. Trong một mô hình AOP có **formal parameters** cho advice, tên tham số và khai báo pointcut phải đúng quy tắc binding của ngôn ngữ. Với kiểu formal cụ thể hơn, phép binding đồng thời có thể là điều kiện lọc kiểu.

Trong thực tế, ưu tiên **binding typed** có phạm vi rõ ràng khi cần truy cập API của một loại object. Nếu chỉ cần tên lớp, signature hoặc thống kê, có thể dùng metadata của join point thay vì giữ reference mạnh đến object, để giảm coupling và rủi ro lưu giữ object lâu ngoài ý định.

### 12.1. Chọn theo kiểu không phải chọn theo identity

~~~text
target(Service)
~~~

Có thể khớp nhiều instance khác nhau của Service và subclass của nó. Không nên dùng nó để diễn đạt “duy nhất instance có id 42”, trừ khi có thêm điều kiện ngữ cảnh thích hợp.

Nếu advice cần phân biệt hai instance có cùng runtime class, có thể dùng một khóa định danh thuộc miền hoặc so sánh reference một cách có kiểm soát. Không nên suy từ `getClass()` rằng hai object là một.

### 12.2. Kiểu runtime bị thay đổi bởi decorator hoặc proxy

Ở một đường interception sử dụng đối tượng đại diện, kiểu runtime **của reference đi qua interceptor** có thể không trùng với lớp implementation gốc:

~~~text
Caller ─► Proxy/Decorator ─► Service implementation
~~~

Một số công cụ quan sát target implementation; một số khác quan sát proxy hoặc một đối tượng khác do cơ chế weaving định nghĩa. Khi đánh giá `this(Type)` và `target(Type)` theo ngôn ngữ AOP cụ thể, phải xác nhận **đối tượng nào thực sự được bind**. Không chuyển quy tắc giữa hai công cụ chỉ vì cả hai đều có khái niệm proxy/target.

Đây cũng là lý do `object.getClass() == Service.class` có thể quá hẹp. Khi muốn match họ kiểu, `instanceof Service` hoặc điều kiện kiểu tương thích trong pointcut phản ánh polymorphism tốt hơn, nếu policy cần bao gồm subclass/proxy hợp lệ.

## 13. Phạm vi của advice và ảnh hưởng của polymorphism

Nếu `FastService extends Service`, `target(Service)` thường khớp receiver thuộc FastService vì nó là subtype. Điều này có thể đúng cả khi:

- Caller khai báo reference Service.
- Caller khai báo reference qua interface.
- Thân thực thi là một override ở FastService.
- Thân thực thi là một phương thức được kế thừa không override, do Service khai báo.

Tuy nhiên **pointcut type condition khớp** chưa có nghĩa **advice chắc chắn chạy**. Cần cả các điều kiện:

1. Loại join point (call/execution/field access...) được engine hỗ trợ.
2. Join point nằm trong phạm vi weaving hoặc đi qua interceptor đã đăng ký.
3. Các điều kiện chữ ký, visibility, lexical và control flow cùng khớp.
4. Tại runtime, object được bind làm `this` hoặc `target` thực sự tương thích T.
5. Không có điều kiện loại trừ hoặc advice precedence nào làm thay đổi kết quả quan sát theo cách ngoài dự tính.

Việc thay một instance Service bằng FastService có thể thay kết quả `target(FastService)` **tại cùng một call site**; đó là một hành vi mong đợi của dynamic pointcut. Nhưng nếu refactor đổi nơi khai báo thân hoặc bỏ phạm vi instrument, việc khớp pointcut dựa chữ ký cũng có thể thay đổi.

## 14. Khi `this` và `target` là hai vai trò khác nhau nhưng cùng kiểu

Giả sử `Service` có thể gọi một Service khác:

~~~java
class Service {
    void forward(Service next) {
        next.execute();
    }

    void execute() {
        // Xử lý
    }
}
~~~

Ở call join point bên trong `forward`:

- `this(Service)` đúng nếu caller object là Service hoặc subtype.
- `target(Service)` cũng đúng vì receiver `next` là Service hoặc subtype.
- Nhưng **hai instance có thể khác nhau**: caller `first`, target `second`.

Điều kiện `this(Service) && target(Service)` chỉ chứng minh cả hai thuộc loại Service, **không chứng minh `this == target`**. Nếu cần quan sát giao tiếp giữa các instance khác nhau, advice hoặc điều kiện động phải phân biệt danh tính và đảm bảo không thay đổi trạng thái ngoài ý định.

Ngược lại, một self-call dùng chính reference `this` có thể khiến danh tính trùng nhau; nhưng chỉ đọc kiểu cũng không phân biệt được hai trường hợp đó.

## 15. Tác dụng phụ và quyền truy cập khi bind đối tượng

Binding giúp advice đọc được object và thậm chí gọi phương thức của nó. Điều đó rất mạnh nhưng không đồng nghĩa luôn an toàn.

- **Side effect:** gọi một phương thức khác của receiver bên trong advice có thể tạo thêm join point, thậm chí kích hoạt lại cùng aspect.
- **Reentrancy:** nếu pointcut rộng, advice gọi logging/helper mà logging/helper lại nằm trong tập chọn, có thể tạo vòng lặp quan sát không mong muốn.
- **Thread safety:** object target có thể được nhiều luồng sử dụng; advice không nên giả định object chỉ có một caller.
- **Partial initialization:** tại join point constructor hoặc giai đoạn init, object có thể chưa hoàn tất bất biến.
- **Sensitive data:** việc có reference target không cho phép thu thập mọi trường/giá trị của target; dữ liệu truy vết phải tuân thủ chính sách hệ thống.
- **Object retention:** nếu advice đưa object vào một collection tĩnh tồn tại lâu, object có thể không được giải phóng như dự kiến.

Khi chỉ cần tag metric theo loại thao tác, hãy ưu tiên tên logic ổn định và metadata được phép dùng, thay vì giữ toàn bộ object để “tiện debug”.

## 16. Hiệu năng: điều kiện động có chi phí thực

Một pointcut chỉ dựa trên chữ ký có thể được tối ưu phần lớn ở lúc weaving. Ngược lại, `this(T)`/`target(T)` có thể cần đánh giá quan hệ kiểu trong lúc chạy nếu không thể xác định hoàn toàn từ thông tin tĩnh.

Điều này không có nghĩa dynamic pointcut luôn chậm: JVM có các tối ưu cho type check, và một số trường hợp bộ dệt suy luận được kết quả. Tổng chi phí còn bao gồm:

- Bao nhiêu join point phải qua điều kiện.
- Có bao nhiêu advice cùng được áp dụng.
- Advice làm I/O hay chỉ đọc metadata.
- Có tạo đối tượng/chuỗi log mới mỗi lượt không.
- Có kiểm tra thêm control flow hay binding phức tạp không.

Nếu một rule áp dụng vào phương thức được gọi rất thường xuyên, hãy đo trên workload thực tế. Không nên quyết định bỏ `target(Type)` chỉ dựa trên giả định rằng mọi phép `instanceof` đều tốn kém.

## 17. Lỗi thường gặp khi chọn pointcut theo đối tượng

### Lỗi 1 — Nhầm `this` với target ở method call

Một advice định giám sát “mọi lần Client gọi tới FastService” nhưng viết `this(FastService)`, khiến điều kiện chỉ xét caller có phải FastService không. Ở call site thuộc Client, điều kiện sai; cần dùng `target(FastService)` nếu muốn xét receiver, đồng thời chọn đúng điểm call.

### Lỗi 2 — Dùng `this(Client)` tại execution để suy ra caller

Ở execution của `FastService.run()`, current executing object chính là instance FastService. Nếu cần biết caller Client, pointcut execution + this(Client) không tự diễn đạt được nguồn gọi. Cần method-call join point tại caller hoặc cơ chế ngữ cảnh khác.

### Lỗi 3 — Đồng nhất `within(Client)` với `this(Client)`

`within` diễn tả nơi mã khai báo; `this` là object runtime. Một phương thức kế thừa khai báo ở Base nhưng chạy trên Child cho thấy hai điều kiện có thể khác nhau.

### Lỗi 4 — Chỉ dựa vào kiểu tĩnh của biến

`Service value = new FastService()` có type tĩnh Service nhưng receiver runtime FastService. Một dynamic target pointcut có thể khớp FastService ngay cả khi chữ ký call thuộc Service.

### Lỗi 5 — Nhầm subtype với đúng class

`target(Service)` thường bao gồm mọi subtype phù hợp; nếu policy chỉ dành cho đúng implementation cụ thể, phải bổ sung điều kiện thích hợp và đánh giá tác động proxy/subclass.

### Lỗi 6 — Tưởng static method có target object

Không có receiver instance cho static execution. Dùng `target(Utility)` để chọn static method trong Utility là mô hình sai; chọn theo signature/lexical context.

### Lỗi 7 — Tưởng có target thì sẽ có this

Một lời gọi instance nằm trong static method vẫn có target receiver nhưng không có this của caller instance. Hai ngữ cảnh cần được xét độc lập.

### Lỗi 8 — Tưởng hai object cùng kiểu là cùng một instance

`this(Service) && target(Service)` có thể đúng khi Service A gọi Service B. Nếu policy chỉ dành cho self-call, điều kiện kiểu đơn thuần chưa đủ.

### Lỗi 9 — Áp đặt semantics của một engine cho mọi công cụ AOP

Một proxy chỉ intercept public interface method có thể không hỗ trợ call-site hoặc field-get join point như một bytecode weaver. Tên “this”/“target” trong API của framework cũng có thể khác object trong mô hình AspectJ. Luôn xác định ranh giới interception thực tế.

### Lỗi 10 — Kiểm thử bằng cách gọi trực tiếp advice

Advice tự chạy đúng khi được gọi như method Java chỉ chứng minh logic bên trong. Phải có test đi qua cơ chế AOP thật để chứng minh join point được chọn, object được bind đúng và lời gọi ngoài phạm vi không bị ảnh hưởng.

## 18. Quy trình thiết kế một dynamic object-type pointcut

**Bước 1 — Viết một câu về chủ thể.** Ví dụ: “Ghi nhận khi một Client instance gọi một FastService instance”, hoặc “Ghi nhận mọi lần FastService instance thực thi phương thức execute”. Đừng gom hai yêu cầu vào một câu mơ hồ.

**Bước 2 — Chọn loại join point.** Chọn call nếu chính caller tại vị trí phát lệnh là quan trọng; chọn execution nếu cần quan sát thân đang chạy từ bất kỳ caller nào. Chỉ dùng loại được engine hỗ trợ.

**Bước 3 — Gán vai trò object.** Với call: ai là executing object (`this`), ai là target? Với execution: cả hai có cùng receiver không? Nếu mã static, vai trò nào không tồn tại?

**Bước 4 — Chọn type condition.** Chọn `this(Type)` hoặc `target(Type)` theo vai trò, thêm interface/subtype nếu cần. Đừng dùng `within(Type)` để thay dynamic type.

**Bước 5 — Giới hạn chữ ký và phạm vi.** Một `target(Service)` đơn độc có thể chọn nhiều join point ngoài dự tính. Kết hợp `call`/`execution`, method pattern, package/lexical restriction hoặc metadata phù hợp.

**Bước 6 — Kiểm thử cặp đối tượng.** Thử caller Client/OtherClient và target BaseService/FastService theo ma trận. Bảo đảm pointcut đúng cả trường hợp *không được chạy*.

**Bước 7 — Kiểm thử cơ chế dệt thật.** Chạy qua đúng đường proxy/weaving, với self-call, static context, override và lỗi khi phù hợp.

**Bước 8 — Kiểm tra advice và chi phí.** Đảm bảo advice không thay đổi return/exception ngoài ý định, không tái nhập vô hạn, không giữ target lâu và không ghi dữ liệu nhạy cảm.

## 19. Ma trận kiểm thử đề xuất

Giả sử policy mong muốn là “một **Client** gọi vào một **FastService**”. Với điểm quan sát **method call**, xét ma trận:

| Đối tượng đang thực thi | Đối tượng đích | Có chọn không? |
|---|---|---|
| Client | BaseService | Không |
| Client | FastService | Có |
| Scheduler | FastService | Không |
| Scheduler | BaseService | Không |
| Subclass của Client | FastService | Có, nếu điều kiện chấp nhận subtype Client |
| Client | Subclass của FastService | Có, nếu điều kiện chấp nhận subtype FastService |
| Không có caller instance (static context) | FastService | Không với điều kiện `this(Client)` |
| Client | Không có target instance (static call) | Không với điều kiện `target(FastService)` |

Để xây dựng bài kiểm thử AOP thực:

1. Dùng fixture có hai lớp caller instance khác nhau, một static caller và hai lớp target có quan hệ kế thừa.
2. Gắn advice đếm lượt và bind object nếu engine hỗ trợ.
3. Kích hoạt từng cặp caller-target qua cùng phương thức có chữ ký thích hợp.
4. Kiểm tra cặp được chọn chạy **đúng một** lượt advice tại join point mong muốn.
5. Kiểm tra cặp không được chọn chạy **không lượt** advice.
6. Với execution, đổi expectation: caller không còn là `this` của execution; kiểm tra `this`/`target` cùng là receiver.
7. Thử gọi trực tiếp target bên ngoài bộ chặn nếu đang dùng proxy; đánh giá rõ ràng hành vi có thể bỏ qua advice.
8. Khi có nhiều aspect khớp cùng điểm, kiểm tra precedence và số lần ghi nhận, tránh đếm lặp.

Có thể log `thisJoinPoint` hoặc dữ liệu join point tương đương để nhìn rõ loại điểm, chữ ký và thông tin object; đừng chỉ dựa vào tên method vì nhiều caller/overload/override có thể cùng tên.

## 20. Tự kiểm tra và lời giải

**Câu 1.** Trong `Client.send()`, Client gọi `FastService.execute()`. Tại **call join point**, `this(Client)` và `target(FastService)` cùng khớp không?

**Đáp:** Có nếu chính một instance Client đang thực thi send, receiver là instance FastService, bộ dệt có call join point và các điều kiện khác đều phù hợp.

**Câu 2.** Với cùng lời gọi, tại **execution join point** của FastService.execute, `this(Client)` có thể được dùng để tìm caller Client không?

**Đáp:** Không theo cách đó. `this` tại execution biểu thị FastService instance đang thực thi; caller phải được quan sát tại call site hoặc theo ngữ cảnh khác.

**Câu 3.** Một object FastService được giữ qua biến `Service service`. `target(FastService)` có thể khớp không?

**Đáp:** Có. Type check động dựa vào receiver thực, không chỉ kiểu tĩnh của biến.

**Câu 4.** Một Service A gọi instance Service B. `this(Service) && target(Service)` có chứng minh đó là self-call không?

**Đáp:** Không. Hai object cùng thuộc Service nhưng có thể khác identity.

**Câu 5.** `static void launch(Task task) { task.run(); }` có target Task không? Có `this` của caller không?

**Đáp:** Lời gọi `task.run()` có receiver instance Task; static method không có `this` instance của caller.

**Câu 6.** Lớp con FastService không override `execute()` của Service. `target(FastService)` có thể đúng tại execution thân Service.execute không?

**Đáp:** Có nếu object thực là FastService và join point thân Service.execute đã được weave. Kiểu khai báo method và kiểu runtime target khác nhau.

**Câu 7.** Một pointcut chỉ dựa vào `within(Client)` có tương đương “caller object runtime là Client” không?

**Đáp:** Không. `within` dựa vào vùng mã khai báo, còn `this` xét object runtime.

**Câu 8.** Vì sao test logic advice đơn thuần chưa đủ chứng minh AOP hoạt động?

**Đáp:** Test đó chưa xác nhận type condition có khớp, join point được engine hỗ trợ, weaving/interception có áp dụng và object có được bind đúng ở đường thực thi thật.

## 21. Sơ đồ ghi nhớ

~~~text
                     DỮ LIỆU MỘT JOIN POINT
                     ┌─────────────────────┐
                     │ Kind: call/execution│
                     │ Signature           │
                     │ Lexical location    │
                     │ Runtime context     │
                     └──────────┬──────────┘
                                │
                 ┌──────────────┴──────────────┐
                 ▼                             ▼
          THIS OBJECT                    TARGET OBJECT
    đối tượng đang thực thi           đối tượng nhận tác động
                 │                             │
          this(Type)                       target(Type)
                 │                             │
                 └──────────────┬──────────────┘
                                │
                        &&, ||, !, ...
                                │
                        POINTCUT KHỚP?
                                │
                 ┌──────────────┴──────────────┐
                Không                         Có
                 │                             │
           Không chạy advice              Chạy advice
                 │                         tại join point
                 └─────────────────────────────┘
~~~

**Nhớ ba nguyên tắc:**

1. Tại **method call**, `this` là đối tượng đang thực thi mã caller còn `target` là receiver của lời gọi.
2. Tại **method execution** của instance method, `this` và `target` cùng gắn với đối tượng đang chạy phương thức; chúng **không mang danh tính caller trước đó**.
3. Pointcut theo kiểu runtime cần được hiểu cùng với **loại join point, chữ ký, phạm vi weaving và đường đi của lời gọi**. Chỉ khi những điều kiện ấy đồng thời đúng, advice mới có thể được áp dụng như mong đợi.

## Tài liệu đối chiếu

- [AspectJ Programming Guide — The Dynamic Join Point Model](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): giải thích method-call và method-execution join points, phân biệt `this`, `target`, `args` và chữ ký điểm can thiệp.
- [AspectJ Programming Guide — Pointcuts](https://eclipse.dev/aspectj/doc/released/progguide/semantics-pointcuts.html): quy tắc lựa chọn theo object type, binding ngữ cảnh và kết hợp logic.
- [Java Language Specification, Java SE 17, §15.12](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): giải quyết method invocation, kiểu tĩnh, dynamic dispatch và Java method semantics.
