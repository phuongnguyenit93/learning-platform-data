# Biểu thức `execution`, `call` và `within` trong pointcut AspectJ

## 1. Ba câu hỏi khác nhau về một lời gọi phương thức

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, **AOP**), một **aspect** đóng gói mối quan tâm cắt ngang các thành phần; **advice** là logic được gắn tại những **join point** do **pointcut** lựa chọn. AspectJ là một cách hiện thực AOP trên Java, cung cấp ngôn ngữ pointcut với nhiều loại join point và các biểu thức chọn chúng.

Ba pointcut designator quan trọng:

- **`execution(MethodPattern)`**: chọn **điểm thực thi** của phương thức phù hợp; hỏi “phương thức nào đang bắt đầu chạy?”.
- **`call(MethodPattern)`**: chọn **điểm gọi** phương thức phù hợp; hỏi “ở đâu đang phát sinh lời gọi tới phương thức đó?”.
- **`within(TypePattern)`**: lọc theo **vị trí từ vựng trong mã nguồn/kiểu khai báo** của join point; hỏi “join point nằm bên trong kiểu nào?”.

Điểm khác biệt lớn nhất là **execution tập trung vào callee**, **call tập trung vào call site**, và **within tập trung vào vị trí chứa join point**, không tự định nghĩa đây là lời gọi hay thực thi.

Ví dụ giả định:

~~~java
class Task {
    void run() {
        System.out.println("running");
    }
}

class Client {
    void start(Task task) {
        task.run();
    }
}
~~~

Với một lời gọi `task.run()` từ `Client.start()`:

~~~text
Client.start()  -- call(Task.run()) -->  Task.run() body
        ^                                    ^
        |                                    |
    call join point                     execution join point
    thuộc Client                        thuộc Task

within(Client): true ở call site nằm trong Client
within(Task): true ở execution join point của Task.run
~~~

Một lời gọi thông thường có thể dẫn tới cả `call` và `execution` join point, **nếu cả hai vị trí đều nằm trong phạm vi được weaving**. Điều này không có nghĩa mỗi lời gọi nhất thiết được quan sát đủ cả hai: kiểu join point được hỗ trợ, điểm cắt, phạm vi dệt mã, lời gọi native/reflective và lộ trình dispatch ảnh hưởng tới tập điểm xuất hiện trong chương trình đang chạy.

## 2. Nền tảng cú pháp: signature pattern và type pattern

AspectJ có ngôn ngữ biểu thức riêng. Các ví dụ cú pháp dưới đây sử dụng **code-style AspectJ**, trong đó có thể khai báo `aspect` và pointcut bằng cú pháp `execution(...)`, `call(...)`, `within(...)`.

Mẫu chữ ký phương thức phổ biến:

~~~aspectj
execution(public * demo.services.OrderService.submit(..))
call(* demo.services.OrderService.submit(..))
~~~

Đọc mẫu trên:

| Thành phần | Ý nghĩa |
| --- | --- |
| `public` | Ràng buộc modifier; có thể bỏ để không giới hạn theo modifier đó |
| `*` đầu tiên | Mọi kiểu trả về |
| `demo.services.OrderService` | Kiểu khai báo phương thức được chọn |
| `submit` | Tên phương thức |
| `(..)` | Bất kỳ số lượng và kiểu tham số |
| `(String)` | Đúng một tham số `String` |
| `(String, ..)` | Tham số đầu là `String`, theo sau có thể có thêm tham số |
| `demo.services..*` trong type pattern | Kiểu trong package đó và các package con theo quy tắc mẫu kiểu |
| `+` sau một type pattern | Kiểu đó và các subtype phù hợp |

Một số biểu thức minh họa:

~~~aspectj
// Mọi phương thức công khai của một lớp, mọi tham số.
execution(public * demo.services.OrderService.*(..))

// Mọi phương thức tên save trả void và nhận đúng một String.
execution(void demo.services.OrderService.save(String))

// Các lời gọi tới phương thức có tên log của một lớp.
call(* demo.telemetry.AuditLogger.log(..))

// Các điểm thực thi method có kiểu khai báo thuộc vùng dịch vụ.
execution(* demo.services..*.*(..))

// Các join point nằm từ vựng trong các kiểu thuộc vùng ứng dụng.
within(demo.application..*)
~~~

**Chú ý:** `execution` và `call` yêu cầu **method pattern**; `within` yêu cầu **type pattern**. Không viết `within(* demo.Service.run(..))`, vì đây là mẫu phương thức, không phải mẫu kiểu. Ngược lại, `execution(demo.services..*)` không phải mẫu thực thi phương thức hoàn chỉnh.

Cú pháp `*`, `..` và `+` có ý nghĩa theo vị trí. Ví dụ `..` bên trong danh sách tham số đại diện cho nhiều tham số, còn `..` trong type/package pattern liên quan phân cấp package/type. Không nên tự suy diễn chúng đều có cùng nghĩa trong mọi ngữ cảnh.

## 3. `execution(...)`: điểm thực thi nằm trong phương thức đích

Biểu thức:

~~~aspectj
pointcut selectedExecution():
    execution(void demo.WorkUnit.run(String));
~~~

chọn method-execution join point tương ứng khi `WorkUnit.run(String)` thực thi, với điều kiện thân phương thức thích hợp đã được dệt mã theo cơ chế triển khai.

Dòng thời gian thông thường:

~~~text
caller chuẩn bị tham số
caller gọi WorkUnit.run(...)
    [execution advice before / around entry]
    body WorkUnit.run(...)
    [execution advice after / around exit]
caller tiếp tục
~~~

`execution` phù hợp khi mục tiêu là **bao quanh hành vi của callee**. Nếu phương thức được gọi từ nhiều nơi, một execution advice ở thân phương thức có thể quan sát các lượt thực thi tương ứng mà không cần liệt kê từng caller.

Ứng dụng thường gặp:

- Đo thời lượng thực thi thực tế của một phương thức nghiệp vụ.
- Kiểm tra điều kiện tại ranh giới bước vào thực thi.
- Gắn context cho một lần operation.
- Ghi nhận ngoại lệ mà thân phương thức đẩy ra đồng bộ.
- Đặt chính sách kỹ thuật được mô tả dựa trên vòng đời method execution.

Tuy nhiên, điểm “thực thi phương thức” vẫn là ranh giới **theo lời gọi đồng bộ**: nếu method chỉ trả về một future chưa hoàn tất, `execution` không tự chờ tác vụ bất đồng bộ xong.

### 3.1. Nhiều caller, một execution pointcut

~~~text
CallerA -> WorkUnit.run()
CallerB -> WorkUnit.run()
Worker  -> WorkUnit.run()
                  |
                  v
         execution(WorkUnit.run)
~~~

Một execution pointcut có thể áp dụng cho tất cả lần thực thi trong phạm vi đã weave, trong khi một call pointcut chỉ đặt ở một tập call site sẽ chỉ nhìn thấy những lời gọi thuộc tập đó.

### 3.2. Trả về hay ném ngoại lệ

Advice `before()` tại `execution` chạy ở đầu lượt thực thi. Advice `after() returning` và `after() throwing` có thể phân biệt return bình thường với throw đồng bộ theo ngữ nghĩa advice. `around()` có thể bao quanh proceed và thay đổi hành vi nếu được thiết kế như vậy.

Không được đồng nhất việc `run()` trả về một `CompletionStage` với trạng thái hoàn tất thành công của công việc được đại diện bởi stage đó.

### 3.3. Mẫu lớp và kế thừa

Nếu kiểu thực tế dùng kế thừa hoặc interface, cần xem xét chữ ký phương thức được thực thi, kiểu khai báo và phương thức được override. Chẳng hạn một điểm cắt cho `execution(* demo.Base.work(..))` không nên bị coi là lời hứa bao phủ mọi implementation của `work` ở mọi kiểu chỉ vì các đối tượng có quan hệ subtype.

Khi muốn match subtype, dùng type pattern phù hợp (ví dụ `Base+`) rồi **kiểm chứng trên các lớp thực tế**, đặc biệt với override, bridge method do generic và các phương thức có chữ ký gần giống.

## 4. `call(...)`: điểm gọi nằm ở phía caller

Biểu thức:

~~~aspectj
pointcut selectedCall():
    call(void demo.WorkUnit.run(String));
~~~

chọn join point xuất hiện ở **vị trí mã đang gọi** phương thức có chữ ký phù hợp. Advice của `call` có thể chạy trước khi lời gọi chuyển điều khiển sang callee.

Dòng thời gian:

~~~text
Caller:
    tạo/đánh giá receiver, arguments
    [call advice before]
    gọi target method
        [execution advice before nếu có]
        chạy method body
        [execution advice after nếu có]
    [call advice after]
    caller tiếp tục
~~~

Thời điểm đánh giá receiver và argument cũng là một phần semantics của ngôn ngữ Java. Không được giả định `before() : call(...)` chạy trước mọi biểu thức tạo argument; nó chạy tại call join point sau khi những giá trị cần thiết cho lời gọi đã được chuẩn bị theo trình tự đánh giá Java.

`call` đặc biệt hữu ích khi mục tiêu là **quan sát những người gọi cụ thể** hoặc chính thao tác đi qua một ranh giới phụ thuộc, chẳng hạn “mọi call site trong tầng nhập liệu gọi một API nguy hiểm”.

Ví dụ:

~~~aspectj
before():
    call(* demo.remote.RemoteClient.request(..))
    && within(demo.application..*) {
    System.out.println("outgoing request from application code");
}
~~~

Điểm cắt trên chọn các call join point đến `RemoteClient.request` mà **call site nằm trong kiểu thuộc `demo.application` hoặc các package con tương ứng**. Nó không tự chọn mọi phương thức của RemoteClient và cũng không chọn các call site nằm ở package khác.

### 4.1. Cùng callee, nhiều call site

~~~text
ClientA.run() --- call site A ---+
                                 +--> Worker.perform()
ClientB.run() --- call site B ---+
Internal.tick() - call site C ---+
~~~

`call(Worker.perform)` có thể chọn các vị trí A, B, C đã được weave. Điều kiện `&& within(ClientA)` thu hẹp về vị trí A. Một execution pointcut cho Worker.perform là một **điểm loại khác** ở phần thực thi của Worker.

### 4.2. Phạm vi weave ở caller là then chốt

Nếu chỉ class callee được weave, một `call` advice nằm ở code caller chưa được weave có thể không chạy. Ngược lại, `execution` advice ở callee đã được weave vẫn có thể chạy khi một caller ngoài phạm vi gọi nó.

Điều này quan trọng với thư viện bên thứ ba, classloader riêng, mã nạp động, môi trường có nhiều artifact hoặc khi chỉ weaving một tập lớp đã định. **Không có call join point được instrument tại call site thì call advice không thể xuất hiện ở đó.**

### 4.3. Lời gọi reflection hoặc lối gọi gián tiếp

Nếu mã gọi `java.lang.reflect.Method.invoke(...)`, call join point tại source site có thể là `Method.invoke`, không phải lời gọi viết trực tiếp như `service.work()`. Còn execution join point của `work()` đã được weave có thể vẫn quan sát lượt thực thi của method khi reflection kích hoạt nó.

Đây là khác biệt loại join point, **không phải tuyên bố rằng reflection luôn né AOP**. Cần kiểm tra runtime, kiểu phương thức và cơ chế weaving được dùng.

## 5. `within(...)`: lọc theo vị trí từ vựng, không theo runtime receiver

Biểu thức:

~~~aspectj
within(demo.WorkUnit)
~~~

chọn các join point **nằm trong phần mã được khai báo từ vựng bên trong kiểu `demo.WorkUnit`**, theo type pattern. Nó không có nghĩa “mọi lời gọi bất kỳ đến đối tượng WorkUnit”.

Ví dụ:

~~~java
class WorkUnit {
    void run() {
        // phần thân run nằm trong WorkUnit
    }

    void localCall() {
        run(); // vị trí gọi này cũng nằm trong WorkUnit
    }
}

class Client {
    void invoke(WorkUnit unit) {
        unit.run(); // vị trí gọi này nằm trong Client
    }
}
~~~

Bảng đối chiếu:

| Join point | `within(WorkUnit)` | `within(Client)` | Lý do |
| --- | --- | --- | --- |
| `execution(WorkUnit.run)` | Có | Không | Execution được khai báo trong WorkUnit |
| `call(WorkUnit.run)` từ WorkUnit.localCall | Có | Không | Call site nằm trong WorkUnit |
| `call(WorkUnit.run)` từ Client.invoke | Không | Có | Call site nằm trong Client |
| `execution(Client.invoke)` | Không | Có | Execution được khai báo trong Client |

**Ghi nhớ:** `within` mô tả **kiểu chứa join point**, không phải kiểu runtime của receiver hay đối tượng đang được gọi.

Dấu hiệu rất dễ nhầm:

~~~aspectj
call(void demo.WorkUnit.run(..))
&& within(demo.Client)
~~~

đọc đúng là “các lời gọi tới WorkUnit.run **viết trong mã của Client**”. Nó **không** có nghĩa “method WorkUnit.run được khai báo trong Client”, và cũng không chọn tất cả execution của WorkUnit.run.

Ngược lại:

~~~aspectj
execution(void demo.WorkUnit.run(..))
&& within(demo.WorkUnit)
~~~

thường là điều kiện phù hợp với vị trí khai báo method WorkUnit.run, nhưng `within` ở đây không làm thay đổi nó thành call pointcut. Khi chỉ cần method execution của kiểu cụ thể, chỉ dùng `execution` thường đã rõ hơn.

### 5.1. `within` độc lập không chỉ chọn phương thức

Một biểu thức `within(SomeType)` tự nó giới hạn **vị trí chứa** những loại join point mà AspectJ hỗ trợ. Nó có thể match nhiều loại join point xuất hiện trong kiểu đó, chứ không chỉ `call` hoặc `execution` method. Do vậy, để tránh lời khuyên “áp dụng cho mọi thứ nằm trong lớp”, thường phối hợp:

~~~aspectj
execution(* demo.WorkUnit.*(..))
&& within(demo.WorkUnit)
~~~

hoặc:

~~~aspectj
call(* demo.RemoteApi.*(..))
&& within(demo.application..*)
~~~

Điều kiện đầu xác định **loại và chữ ký điểm cắt**, điều kiện sau giới hạn vị trí mã chứa điểm ấy.

### 5.2. Không nhầm `within` với `withincode`, `this`, `target`

Các từ khóa khác trả lời câu hỏi khác:

| Pointcut designator | Chọn theo |
| --- | --- |
| `within(TypePattern)` | Kiểu từ vựng chứa join point |
| `withincode(MethodPattern)` | Phần mã thuộc thân method/constructor phù hợp |
| `this(TypeOrId)` | Đối tượng `this` ở join point theo ngữ nghĩa từng loại join point |
| `target(TypeOrId)` | Đối tượng đích của join point theo ngữ nghĩa từng loại join point |
| `args(TypeOrId, ..)` | Đối số tại join point |
| `execution(MethodPattern)` | Method execution |
| `call(MethodPattern)` | Method call site |

Ví dụ `within(Client)` không đòi receiver của cuộc gọi phải là Client; caller code có thể gọi một đối tượng WorkUnit hoặc RemoteApi. Nếu muốn ràng buộc receiver theo kiểu runtime, cần xem xét `target(...)` và loại join point, không thay bằng `within`.

## 6. Ví dụ đầy đủ: ba designator tạo kết quả khác nhau

Ví dụ dưới đây có thể biên dịch với **AspectJ compiler (`ajc`)** và chạy trên Java 17 nếu môi trường đã cài một bản AspectJ hỗ trợ JDK đang dùng. Nó dùng **code-style AspectJ**; cú pháp `aspect` nằm trong file `.aj` và không thể biên dịch bằng riêng `javac`.

Tạo cấu trúc:

~~~text
demo/
  Demo.java
  WorkUnit.java
  TraceAspect.aj
~~~

### 6.1. Tệp `demo/WorkUnit.java`

~~~java
package demo;

public class WorkUnit {
    public void run(String message) {
        System.out.println("BODY " + message);
    }

    public void self() {
        run("internal");
    }
}
~~~

### 6.2. Tệp `demo/Demo.java`

~~~java
package demo;

public class Demo {
    public static void main(String[] args) {
        WorkUnit unit = new WorkUnit();
        unit.run("external");
        unit.self();
    }
}
~~~

### 6.3. Tệp `demo/TraceAspect.aj`

~~~aspectj
package demo;

public aspect TraceAspect {
    // Nằm tại call site trong Demo.
    before():
        call(void demo.WorkUnit.run(String))
        && within(demo.Demo) {
        System.out.println("CALL from Demo");
    }

    // Nằm tại call site trong WorkUnit.self().
    before():
        call(void demo.WorkUnit.run(String))
        && within(demo.WorkUnit) {
        System.out.println("CALL from WorkUnit");
    }

    // Nằm tại method execution, dù caller là ai.
    before():
        execution(void demo.WorkUnit.run(String)) {
        System.out.println("EXEC WorkUnit.run");
    }
}
~~~

Ở ví dụ này, mỗi điểm gọi `run` match **đúng một** advice `call` nhờ hai điều kiện `within` loại trừ nhau. Advice `execution` là một loại join point khác. Vì vậy thứ tự in ra không dựa vào việc phỏng đoán precedence giữa nhiều advice tại cùng một join point.

### 6.4. Biên dịch và chạy

Điều kiện môi trường:

- Có JDK 17+ và `java` sẵn trong PATH.
- Có công cụ `ajc` (AspectJ compiler) từ bản AspectJ tương thích với JDK.
- Có `aspectjrt.jar` trên runtime classpath nếu cách cài AspectJ yêu cầu (thường nằm trong thư mục `lib` của bản phân phối AspectJ).

Từ thư mục **cha của `demo`**, dùng lệnh sau trên môi trường Unix-like. Biến `ASPECTJ_HOME` là đường dẫn tới bản cài AspectJ thực tế trên máy, phải cấu hình trước:

~~~bash
# ASPECTJ_HOME đã trỏ tới thư mục cài AspectJ.
mkdir -p out
ajc -17 -d out demo/WorkUnit.java demo/Demo.java demo/TraceAspect.aj
java -cp "out:$ASPECTJ_HOME/lib/aspectjrt.jar" demo.Demo
~~~

Trên Windows, dấu phân cách classpath là `;` thay cho `:`; tùy cách cài, vị trí `aspectjrt.jar` có thể khác. Khi công cụ compiler không hỗ trợ cờ `-17`, cần dùng một bản AspectJ có hỗ trợ language level phù hợp; ví dụ Java trên cũng không dùng tính năng vượt quá Java 17.

Stdout:

~~~text
CALL from Demo
EXEC WorkUnit.run
BODY external
CALL from WorkUnit
EXEC WorkUnit.run
BODY internal
~~~

**Vì sao có đúng các dòng đó?**

1. `Demo.main` gọi `unit.run("external")`. Call site nằm trong kiểu Demo: `call(...) && within(Demo)` match và in `CALL from Demo`.
2. Control vào phương thức `WorkUnit.run`: `execution(...)` match, in `EXEC WorkUnit.run`.
3. Thân method chạy và in `BODY external`.
4. Sau đó `Demo.main` gọi `unit.self()`; biểu thức `call(run)` không match lời gọi `self()` vì tên method khác.
5. Bên trong `WorkUnit.self`, biểu thức `run("internal")` tạo call site nằm từ vựng trong WorkUnit: advice thứ hai in `CALL from WorkUnit`.
6. Thân `WorkUnit.run` thực thi lần nữa và in `EXEC WorkUnit.run`, rồi `BODY internal`.

Nếu bỏ weaving khỏi **`Demo`**, advice `call && within(Demo)` không còn cơ hội chặn call site của Demo. Nếu bỏ weaving khỏi **`WorkUnit`**, cả call site trong `self()` và execution của `run()` có thể không được instrument. Đó là lý do ví dụ biên dịch/dệt **cả ba file cùng nhau**.

### 6.5. Tại sao không dùng `javac` cho `.aj`?

`javac` hiểu Java thông thường nhưng không xử lý khai báo `aspect` và logic weaving của code-style AspectJ. `ajc` biên dịch AspectJ và Java cần thiết, thực hiện weaving theo cấu hình. Trong một dự án dùng load-time weaving, quy trình chuẩn bị và runtime khác; khi đó phải xác định đúng các lớp được load/weave và không tự sử dụng lệnh biên dịch trên như công thức cho mọi môi trường.

## 7. Ma trận chọn điểm cắt: quan sát người gọi hay người được gọi?

| Nhu cầu | Biểu thức minh họa | Lý do |
| --- | --- | --- |
| Theo dõi mỗi lượt thực thi của `WorkUnit.run` | `execution(void demo.WorkUnit.run(String))` | Bám vào thân method đích |
| Theo dõi những call site gọi `WorkUnit.run` | `call(void demo.WorkUnit.run(String))` | Bám vào điểm phát sinh lời gọi |
| Chỉ theo dõi caller nằm trong `demo.ui` | `call(* demo.WorkUnit.run(..)) && within(demo.ui..*)` | Giới hạn nơi viết lời gọi |
| Chỉ instrument code trong `demo.services` | `within(demo.services..*)` cộng điều kiện join point cụ thể | Giới hạn vị trí chứa |
| Chọn execution của toàn bộ service được phê duyệt | `execution(* demo.services..*Service.*(..))` | Giới hạn method execution theo type/name |
| Chọn các call site trong một method cụ thể | `call(* demo.RemoteApi.*(..)) && withincode(* demo.Client.submit(..))` | Hẹp hơn giới hạn theo cả kiểu |
| Chọn các execution khai báo ở một kiểu nhất định | `execution(* demo.WorkUnit.*(..)) && within(demo.WorkUnit)` | Kết hợp chữ ký và vị trí chứa |
| Truy vết lời gọi qua lớp thư viện nhưng chỉ có quyền weave caller | `call(* demo.RemoteApi.*(..))` tại call site được weave | Call-site advice không đòi instrument thân thư viện, nếu call site thuộc phạm vi |
| Bảo vệ thao tác nhạy cảm từ nhiều entry point | Xem xét execution tại ranh giới tin cậy, kèm kiểm tra độ bao phủ | Chặn theo callee thường phù hợp hơn dựa duy nhất vào một tập caller |

Đây là mẫu phân tích, không phải cam kết rằng mọi expression sẽ match trong bất kỳ bản biên dịch nào. Phải kiểm tra các type/method pattern thực tế, phạm vi weaving và control flow.

## 8. Chọn giữa `call` và `execution` khi làm quan sát

### 8.1. Kết quả đo có thể khác nhau

Giả sử method đích `calculate` nhanh nhưng caller dành thời gian xử lý tham số phức tạp trước khi gọi. Advice tại call join point và advice tại execution join point không tự động bao gồm toàn bộ thời gian chuẩn bị tham số ấy.

- **`execution`** quan sát lượt thực thi thân phương thức đích.
- **`call`** quan sát phần hoạt động của lời gọi tại một call site đã được weave, gồm việc tiến vào/ra lời gọi theo semantics AOP.
- Để đo **end-to-end operation** gồm xếp hàng, retry hoặc hoàn tất bất đồng bộ, cần một ranh giới khác rộng hơn, được định nghĩa theo hợp đồng.

Một phép đo “call duration” và “execution duration” có thể khác nhau vì các lớp advice khác, dispatch/bridge, wrapper, lỗi, thread scheduling hoặc phạm vi quan sát. Không nên gán chúng cùng một tên metric.

### 8.2. Người gọi có nhiều call site

Nếu một method được gọi từ 20 chỗ khác nhau:

- `execution` tại callee thường giúp instrument tập trung.
- `call` có thể giúp phân biệt những chỗ gọi, đặc biệt khi kết hợp `within` hoặc `withincode`.
- Truy vết mọi call site làm tăng số điểm instrument và overhead; phải giới hạn theo mục tiêu.

### 8.3. Thư viện chỉ có bytecode

Có lúc người phát triển không muốn hoặc không thể weave code thư viện. Nếu một caller thuộc quyền kiểm soát được weave, `call` ở caller có thể quan sát các lần gọi từ caller đó vào API thư viện mà không cần thay đổi thân method thư viện. Nhưng các caller khác không được weave vẫn nằm ngoài.

Ngược lại, nếu thư viện là nơi chứa method execution và không được weave, `execution` advice không thể tự xuất hiện trong body của thư viện. Quyết định cần dựa trên khả năng can thiệp tại build/load-time trong môi trường thật.

## 9. `within` chỉ nói “mã nằm ở đâu”, không nói “ai đang chạy”

Giả sử:

~~~java
class Processor {
    void delegate(ExternalService service) {
        service.send();
    }
}
~~~

Join point `call(ExternalService.send)` nằm từ vựng trong `Processor.delegate`. Do đó:

~~~aspectj
call(* demo.ExternalService.send(..)) && within(demo.Processor)
~~~

có thể match call site đó. Dù receiver là `ExternalService`, `within(ExternalService)` **không** match riêng call site nằm trong Processor.

Ở method execution `ExternalService.send`, tình thế ngược lại: execution nằm trong kiểu khai báo method tương ứng. Dùng `within(Processor)` không biến execution của ExternalService thành join point trong Processor chỉ vì Processor là caller.

Các câu cần tự hỏi:

1. Mình đang chọn **call** hay **execution**?
2. Join point ấy nằm trong **mã của lớp nào**?
3. Kiểu receiver/target có liên quan đến `within` không? (Thông thường không; đó là vai trò của `target` khi phù hợp.)
4. Có call site nào khác được tạo ở kiểu/package khác không?
5. Nếu mã bị refactor sang helper class, biểu thức `within` có thay đổi tập match không?

Điểm cuối cùng rất thực tế: chuyển một dòng gọi từ `Client` sang `Helper` có thể làm một `call && within(Client)` advice không còn chạy, ngay cả khi hành vi nghiệp vụ bên ngoài giữ nguyên.

## 10. Pointcut composition bằng toán tử logic

Ba designator có thể kết hợp bằng:

- `&&`: cả hai điều kiện cùng đúng ở **cùng một join point**.
- `||`: một trong hai điều kiện đúng.
- `!`: loại trừ điều kiện.
- Dấu `(...)` để nhóm và kiểm soát thứ tự biểu thức.

Ví dụ:

~~~aspectj
pointcut observedCalls():
    call(* demo.RemoteClient.request(..))
    && within(demo.application..*)
    && !within(demo.telemetry..*);
~~~

Một biểu thức khác:

~~~aspectj
pointcut observedMethods():
    execution(public * demo.services..*.*(..))
    && !within(demo.services.internal..*);
~~~

Ở dạng tổng quát, `execution(...) && call(...)` thường **không chọn được một join point method bình thường**, vì method execution và method call là hai **loại join point khác nhau**. Không dùng `&&` để mang nghĩa “đầu tiên call rồi execution” trên cùng một điểm.

Nếu muốn theo dõi cả hai loại, dùng `||` khi thích hợp:

~~~aspectj
pointcut bothKinds():
    call(void demo.WorkUnit.run(String))
    || execution(void demo.WorkUnit.run(String));
~~~

Nhưng advice cho `bothKinds()` có thể kích hoạt **hai lần cho một lượt gọi được weave đầy đủ**: một tại call site, một tại execution. Nếu chỉ muốn một event “operation started”, đây có thể gây đếm trùng. Cần xác định loại điểm và đơn vị metric.

### 10.1. Độ ưu tiên logic và tính dễ đọc

Với biểu thức phức tạp, nên dùng dấu ngoặc:

~~~aspectj
(
    call(* demo.Api.read(..))
    || call(* demo.Api.write(..))
)
&& within(demo.clients..*)
~~~

Dấu ngoặc giúp cho điều kiện `within` rõ ràng áp dụng cho **cả hai nhóm call**. Nếu bỏ ngoặc và hiểu sai precedence của toán tử, pointcut có thể chọn nhiều call site hơn dự kiến.

### 10.2. Named pointcut

Một biểu thức được sử dụng nhiều nơi nên có tên thể hiện ý nghĩa:

~~~aspectj
pointcut businessExecution():
    execution(public * demo.business..*Service.*(..));

pointcut inboundApiCalls():
    call(* demo.api..*.*(..))
    && within(demo.application..*);
~~~

Tên pointcut giúp review, nhưng **không thay thế thử nghiệm** xem join point nào thực sự match. Mỗi tên nên đi kèm phạm vi loại trừ và ý định đo/kiểm soát.

## 11. Mức độ rộng của pattern và rủi ro instrument quá nhiều

Các expression rất rộng như:

~~~aspectj
execution(* *(..))
call(* *(..))
within(demo..*)
~~~

có thể match số lượng lớn join point. Nếu advice gọi logger, formatter hoặc metric exporter mà chính các thành phần ấy cũng match, hệ thống có thể tạo vòng đệ quy, log storm hoặc tăng mạnh overhead.

Một điểm cắt tốt thường có:

1. **Mẫu dương** xác định nhóm hành vi cần instrument.
2. **Điều kiện vị trí** dùng `within` khi cần ràng buộc caller code hoặc vùng module.
3. **Loại trừ hạ tầng** như logger, exporter, policy evaluator và code của chính aspect.
4. **Chính sách kết quả** cho lỗi, timeout, callback và việc thay đổi control flow.
5. **Test xác nhận tập join point được chọn**, cả dương tính lẫn âm tính.

Ví dụ giả mã dạng chính sách (không phải cú pháp đầy đủ):

~~~text
allowed =
    expected method execution
    AND within approved modules
    AND NOT instrumentation internals
    AND NOT sensitive utilities excluded by policy
~~~

Một khi `call` hoặc `execution` được dùng cho authorization, transaction hoặc retry, việc chọn sai tập điểm có thể gây thay đổi chức năng nghiêm trọng hơn một phép đo sai; cần review kiến trúc và lỗi/tác dụng phụ.

## 12. Các tình huống nâng cao cần phân biệt

### 12.1. Lời gọi nội bộ trên `this`

Với code:

~~~java
class A {
    void one() { two(); }
    void two() {}
}
~~~

Lời gọi `two()` nằm trong A.one. Trong **code-style AspectJ được weave phù hợp**, `call(* A.two(..)) && within(A)` có thể match call site đó; `execution(* A.two(..))` có thể match thân A.two. Không lấy quy tắc bỏ qua self-invocation của một số cơ chế proxy để suy ra rằng AspectJ weaving luôn bỏ qua call site nội bộ.

### 12.2. Dynamic dispatch và method pattern

Với `Base b = new Child(); b.work();`, caller biết một chữ ký theo kiểu biên dịch và JVM dispatch tới implementation thực tế. `call` và `execution` có thể khác nhau về chữ ký join point được match trong tình huống kế thừa, override và bridge methods.

Không nên suy ra từ runtime class của receiver rằng mọi `call(Sub.work)` đều match call site viết qua biến kiểu Base. Nếu muốn theo dõi đa hình, cần dùng type pattern đúng, xem xét `+`/binding của `target` khi phù hợp, và kiểm thử cả kiểu khai báo lẫn kiểu runtime.

### 12.3. Constructor không phải method call thông thường

`execution(...)` và `call(...)` trong bài áp dụng cho **method**. AspectJ còn có join point/pointcut riêng liên quan constructor, chẳng hạn `initialization` hoặc `preinitialization`, và mẫu constructor call `call(Type.new(..))` trong những trường hợp được hỗ trợ.

Không dùng mẫu method `execution(void Type.new(..))` để thay cho constructor execution. Nếu cần instrument vòng đời khởi tạo, hãy học và dùng cú pháp constructor cùng các giai đoạn initialization thích hợp; thứ tự và điểm thực thi khác method thường.

### 12.4. Accessor, bridge và phương thức sinh bởi compiler

Compiler có thể tạo bridge method cho generic hoặc những đoạn mã hỗ trợ khác. Một pointcut quá rộng có thể thấy các điểm không phải là operation nghiệp vụ như mong đợi, tùy phiên bản compiler và cách weaving. Nếu metrics cần một đơn vị “một business invocation”, hãy kiểm tra số event thực tế thay vì tự coi một method name tương đương một event.

### 12.5. Kiểm soát quyền nên đặt ở ranh giới thực hiện effect

Giả sử `call(SensitiveApi.delete)` chỉ được instrument ở UI caller, nhưng job, event consumer hoặc reflection cũng có thể kích hoạt hành vi. Tập call site UI không đủ chứng minh mọi đường đều được bảo vệ. `execution` ở phương thức dịch vụ đã weave có thể phù hợp hơn, song vẫn phải xác nhận toàn bộ đường đến effect và tránh phụ thuộc vào advice có thể bị bỏ qua.

Nếu tài nguyên nhạy cảm, giữ kiểm tra quyền ở ranh giới đáng tin cậy là lựa chọn kiến trúc quan trọng, ngay cả khi AOP hỗ trợ áp cùng chính sách ở nhiều điểm.

### 12.6. Các mô hình weaving và phạm vi runtime

AspectJ có thể được tích hợp vào quá trình build để dệt class, hoặc áp dụng load-time weaving theo cấu hình. Dù chọn cách nào, phải xác định **cả call site lẫn callee nào thực sự đã được weave**, tránh kết luận sai từ việc aspect source được biên dịch thành công.

Dấu hiệu phổ biến của lỗi phạm vi: `execution` có event nhưng `call` không có, hoặc chỉ một nhóm caller hiện ra. Hãy kiểm tra phạm vi dệt, classloader, loại code và call site được chọn; không sửa bằng cách tùy tiện nới pointcut trên toàn chương trình khi chưa hiểu nguyên nhân.

## 13. Debug pointcut và xác nhận join point thực tế

Khi không thấy advice chạy, kiểm tra có hệ thống:

**Bước 1 — Xác nhận kiểu join point mong muốn.** Lỗi phổ biến là muốn biết caller ở đâu nhưng viết `execution`, hoặc muốn bảo vệ method đích nhưng chỉ chọn `call` trong một package hẹp.

**Bước 2 — Xác nhận pattern.** Kiểm tra return type, modifier, tên phương thức, danh sách tham số, package và subtype pattern. Một overload khác có thể không match.

**Bước 3 — Xác nhận `within`.** Join point nằm trong kiểu chứa mã nào? Với call, đó là vùng source của caller; với execution, là vùng khai báo/thực thi method được instrument.

**Bước 4 — Xác nhận weaving.** Với call, caller class đã được weave chưa? Với execution, callee đã được weave chưa? Có classloader, build artifact hoặc runtime config khác biệt không?

**Bước 5 — Xác nhận order.** Một advice khác có thể trả về trước khi proceed(), làm advice phía trong không chạy.

**Bước 6 — Xác nhận self-call, reflection và dispatch.** Đừng dùng suy đoán “mọi internal call đều bỏ qua aspect” hoặc “reflection luôn bypass”; hãy xem kiểu can thiệp và receiver thực tế.

**Bước 7 — Thu hẹp phép thử.** Dùng ví dụ hai class và một method tương tự demo; kiểm tra một join point trước, sau đó tăng dần pattern.

**Bước 8 — Kiểm chứng trường hợp bị loại trừ.** Đảm bảo advice **không** match telemetry internals và các method không thuộc chính sách; tránh chỉ test happy path.

Một cách quan sát an toàn trong môi trường thử nghiệm là dùng `thisJoinPointStaticPart` để biết thông tin tĩnh về join point được chọn, nhưng không nên log không giới hạn mọi đối số hoặc toàn bộ dữ liệu nhạy cảm.

## 14. Những sai lầm thường gặp

**Sai lầm 1 — Coi `call` và `execution` là đồng nghĩa.** Call gắn với vị trí gọi; execution gắn với thân phương thức. Một bên có thể được weave, bên kia không.

**Sai lầm 2 — Coi `within(Type)` là “target có kiểu Type”.** Within là vị trí từ vựng chứa join point. Với receiver type dùng công cụ pointcut khác phù hợp như `target`.

**Sai lầm 3 — Viết `call(...) && execution(...)` để “bao cả hai”.** Một join point thường không đồng thời là hai loại này. Khi cần lựa chọn union, dùng `||` và đánh giá rủi ro đếm trùng.

**Sai lầm 4 — Chọn method signature sai.** Phương thức trả kiểu khác, có overload khác hoặc nằm ở subtype không được type pattern bao phủ. Kiểm tra chữ ký được compiler nhìn thấy.

**Sai lầm 5 — Đặt `within(Callee)` trên `call` và kỳ vọng bắt mọi caller.** Khi đó chỉ lấy call site **nằm trong Callee**, không phải mọi lời gọi hướng tới Callee. Nếu muốn mọi call site có thể weave, bỏ hoặc thay điều kiện `within`.

**Sai lầm 6 — Chỉ weave một phía nhưng kỳ vọng đủ hai event.** Nếu caller chưa được weave, call advice thiếu; nếu callee chưa được weave, execution advice thiếu. Cần quản lý phạm vi dệt mã.

**Sai lầm 7 — Dùng pointcut quá rộng cho logger/metric.** Advice có thể tự chặn hạ tầng do nó gọi, gây đệ quy hoặc chi phí cực lớn. Loại trừ và kiểm thử.

**Sai lầm 8 — Đồng nhất method return với hoàn tất tác vụ async.** Return future không phải success của future; thiết kế observer completion riêng nếu cần.

**Sai lầm 9 — Dựa trên một call pointcut để cưỡng chế mọi đường truy cập.** Caller khác, callback, job hoặc reflection có thể nằm ngoài phạm vi. Bảo vệ effect tại ranh giới tin cậy.

**Sai lầm 10 — Sao chép cú pháp từ một biến thể AOP sang mô hình khác mà không kiểm tra.** Phạm vi join point và khả năng weave phụ thuộc công cụ. Ví dụ `.aj` code-style AspectJ cần `ajc`, không thể giả định mọi compiler Java hay mọi hình thức proxy đều hiểu cú pháp đó.

## 15. Bài tập có đáp án

### Câu 1. Cho hai lớp:

~~~java
class A {
    void x(B b) { b.y(); }
}
class B {
    void y() {}
}
~~~

Ở lời gọi `b.y()`, `within(A)` kết hợp với `call(B.y)` có thể match không?

**Đáp án:** Có, nếu call site nằm trong A đã được weave và chữ ký method pattern đúng. Còn `execution(B.y) && within(A)` không match execution của B.y chỉ vì A là caller.

### Câu 2. Một phương thức `B.y()` được gọi từ A và C. Muốn chọn mọi lượt thực thi tại thân `B.y()`, điểm cắt nào tự nhiên nhất?

**Đáp án:** `execution(* B.y(..))` với type pattern và phạm vi weave phù hợp. Một `call` pointcut ở riêng A chỉ thấy call site của A.

### Câu 3. Muốn đo các lời gọi tới `RemoteClient.fetch` chỉ phát sinh từ kiểu thuộc package `app.ui`, chọn biểu thức nào?

**Đáp án:** Ví dụ `call(* RemoteClient.fetch(..)) && within(app.ui..*)` với tên kiểu đầy đủ theo dự án. `within` lọc mã caller, không lọc nơi định nghĩa `fetch`.

### Câu 4. Một class được weave ở method execution, nhưng caller đến từ thư viện không được weave. `execution` và `call` có thể cho kết quả gì?

**Đáp án:** Execution advice của callee có thể chạy; call advice tại call site thư viện chưa weave không chạy. Cần biết phạm vi weaving và các join point thực tế.

### Câu 5. Một `call` advice chọn vị trí trong `WorkUnit.self()` nơi tự gọi `run()`. Có thể kết luận đây là bypass vì “self-call” không?

**Đáp án:** Không. Trong code-style AspectJ được weave ở call site ấy, `call` có thể match. Giới hạn self-invocation của một số cơ chế proxy không được áp đặt cho mọi dạng weaving.

### Câu 6. Biểu thức `call(..) || execution(..)` cùng chọn `run`. Người phát triển ghi một metric ở cả hai. Rủi ro gì?

**Đáp án:** Một lượt gọi bình thường có thể phát hai sự kiện: một cho call site và một cho execution. Metric operations_total có thể đếm trùng nếu không phân biệt loại join point.

### Câu 7. Có nên viết `within(demo..*)` và coi đó chỉ là “mọi phương thức trong demo”?

**Đáp án:** Không. `within` chọn join point theo vùng mã nằm trong kiểu phù hợp, có thể gồm nhiều loại join point. Nếu chỉ muốn method execution, thêm `execution(...)`.

### Câu 8. Di chuyển câu lệnh gọi API từ `Client` sang `Helper`, còn logic nghiệp vụ tương đương. Pointcut `call(Api.send(..)) && within(Client)` có còn match không?

**Đáp án:** Không nhất thiết; vị trí từ vựng của call site đã đổi sang Helper. Cần cập nhật điểm cắt hoặc thiết kế theo một ranh giới ít phụ thuộc vị trí source hơn.

## 16. Checklist review trước khi dùng trong chương trình thật

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Muốn quan sát method được gọi hay nơi gọi? | Chọn `execution` hoặc `call` có lý do |
| Cần lọc caller trong một module? | Dùng `call && within(CallerPattern)` nếu tương thích phạm vi weave |
| Cần lọc code trong một kiểu? | `within(TypePattern)` dùng đúng nghĩa từ vựng |
| Signature có đúng? | Kiểm tra return, modifier, overload, parameters, subtype |
| Caller/callee có được weave? | Biên dịch, load-time weave và test runtime xác nhận |
| Có call nội bộ/reflective không? | Kiểm tra đúng receiver và loại join point |
| Có advice chồng nhau không? | Đánh giá precedence, skip/proceed và đếm trùng |
| Có nguy cơ recursion từ telemetry? | Loại trừ hạ tầng aspect và thử failure path |
| Có dùng để kiểm soát truy cập không? | Không có đường bypass tới sensitive effect |
| Có future, callback hoặc Publisher không? | Phân biệt invocation return với logical completion |
| Có retry hoặc giao dịch không? | Effect, transaction scope, idempotency được kiểm tra |
| Có test âm tính không? | Method/call site ngoài vùng phải thực sự không match |

## 17. Tổng kết

`execution`, `call` và `within` trả lời ba câu hỏi khác nhau:

~~~text
execution(...)  -> callee nào đang thực thi?
call(...)       -> lời gọi tới callee ấy nằm ở đâu?
within(...)     -> join point nằm từ vựng trong kiểu nào?
~~~

Dùng `execution` khi mục tiêu là ranh giới thực thi của method; dùng `call` khi mục tiêu là call site hoặc vùng phụ thuộc giữa các thành phần; dùng `within` để thu hẹp theo vị trí mã chứa một join point đã được xác định rõ loại.

Khi kết hợp, viết pointcut thể hiện đúng mục tiêu, kiểm tra chữ ký và phạm vi weaving, đo đúng đơn vị call/execution, đồng thời loại trừ hạ tầng dễ gây recursion. Với chính sách có thể đổi luồng điều khiển hoặc kiểm soát quyền, phải xác nhận mọi đường thực thi và tác dụng phụ nhạy cảm được bảo vệ; tên của biểu thức điểm cắt không thay thế chứng cứ runtime.