# Pointcut `cflow` và `cflowbelow` trong AspectJ: hiểu luồng điều khiển động của AOP

## 1. Vấn đề: cùng một phương thức, nhưng ngữ cảnh gọi khác nhau

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP), một pointcut thông thường có thể chọn join point bằng tên method, kiểu chứa method, annotation hoặc loại hoạt động. Tuy nhiên, nhiều chính sách xuyên suốt không chỉ phụ thuộc **method nào đang thực thi**, mà còn phụ thuộc **đường điều khiển nào đã đưa chương trình đến method đó**.

Ví dụ, một phương thức `store.write(...)` được gọi trong hai trường hợp:

- Nhánh A: `processOrder() → reserve() → store.write()`.
- Nhánh B: `adminRepair() → store.write()`.

Nếu muốn ghi telemetry chuyên biệt **chỉ khi thao tác ghi diễn ra bên trong việc xử lý đơn hàng**, pointcut chỉ chọn `execution(* Store.write(..))` là quá rộng. Cần bổ sung điều kiện: tại thời điểm `write` chạy, stack điều khiển vẫn đang nằm trong phạm vi động được mở bởi `processOrder`.

AspectJ cung cấp hai pointcut designator liên quan:

- **`cflow(P)`**: chọn các join point thuộc *dynamic control flow* của một join point khớp `P`, **bao gồm cả join point khởi đầu**.
- **`cflowbelow(P)`**: chọn các join point ở **bên dưới** join point khớp `P` trong dynamic control flow, **loại trừ chính join point mở đầu đó**.

Dấu `P` đại diện cho một pointcut biểu thức. Đây là **pointcut xác định theo ngữ cảnh thực thi động**, không chỉ là tìm lời gọi nằm về mặt văn bản trong source code.

Ví dụ trực quan:

~~~text
main()
  |
  +-- processOrder()         <-- P = execution(processOrder)
  |     |
  |     +-- reserve()
  |     |     |
  |     |     +-- store.write()
  |     |
  |     +-- validate()
  |
  +-- adminRepair()
        |
        +-- store.write()
~~~

Trong lần chạy có `processOrder()` đang hoạt động:

- `cflow(P)` đúng tại `processOrder()` **và** các join point nằm trong luồng thực thi phát sinh bên dưới nó.
- `cflowbelow(P)` đúng tại `reserve()`, `store.write()`, `validate()` và các join point khác thuộc phần bên dưới, nhưng **không đúng tại chính `processOrder()` mở đầu**.
- `adminRepair()` và `store.write()` do `adminRepair()` gọi sau khi `processOrder()` kết thúc không thuộc luồng đó.

**Chú ý:** sơ đồ trên chỉ thể hiện các phương thức tiêu biểu. Tập join point thật còn phụ thuộc các kiểu join point mà bộ weaving hỗ trợ và điểm nào được pointcut còn lại chọn.

## 2. Những khái niệm cần nắm trước

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Join point** | Vị trí sự kiện thực thi được AspectJ cho phép lựa chọn: method call, method execution, constructor execution, field access... tùy dạng pointcut |
| **Pointcut** | Biểu thức chọn tập join point để áp advice |
| **Advice** | Mã được gắn vào join point đã chọn, ví dụ before, after, around |
| **`execution(...)`** | Khớp thời điểm thực thi thân method với chữ ký phù hợp |
| **`call(...)`** | Khớp điểm gọi method ở phía bên gọi |
| **`within(...)`** | Điều kiện dựa trên lexical type mà mã join point nằm trong |
| **`withincode(...)`** | Điều kiện dựa trên mã nguồn enclosing method/constructor |
| **`cflow(P)`** | Điều kiện về call stack/dynamic control flow được mở từ `P`, tính cả entry join point |
| **`cflowbelow(P)`** | Điều kiện về dynamic control flow bên dưới `P`, loại trừ entry join point |
| **`thisJoinPoint`** | Thông tin runtime của join point trong advice |
| **`thisJoinPointStaticPart`** | Phần thông tin tĩnh của join point, hữu ích khi cần tránh dựng object chi tiết không cần thiết |

**Điểm phân biệt:** `within` và `withincode` phản ánh **vị trí tĩnh/lexical**. `cflow` và `cflowbelow` phản ánh **đường đi đã thực sự được thực thi**.

Ví dụ, `store.write()` có thể được gọi từ nhiều phương thức khác nhau; cùng một execution join point ở `Store.write` đôi khi thuộc `cflow(processOrder)`, đôi khi không. Điều kiện thay đổi theo lời gọi đang diễn ra, không do tên method thay đổi.

## 3. Cú pháp cơ bản và cách kết hợp

Một số biểu thức mẫu:

~~~aspectj
// Chọn mọi join point trong dynamic control flow của
// execution một method processOrder không tham số:
cflow(execution(void OrderService.processOrder()))

// Chỉ chọn những join point bên dưới execution đó:
cflowbelow(execution(void OrderService.processOrder()))

// Chỉ chọn execution các method của Repository diễn ra
// bên trong control flow processOrder:
execution(* Repository.*(..))
    && cflow(execution(void OrderService.processOrder()))

// Chỉ chọn các execution bên dưới processOrder:
execution(* Repository.*(..))
    && cflowbelow(execution(void OrderService.processOrder()))
~~~

Đây là **các mảnh cú pháp AspectJ minh họa**, chưa phải một file `.aj` hoàn chỉnh. Tên class/method mang tính giả định; chữ ký trong pointcut phải đúng với chương trình thật.

Hai câu cuối là ví dụ sử dụng toán tử **`&&`** để lấy giao của hai điều kiện:

1. Về mặt method: join point hiện tại phải là execution thuộc tập `Repository.*(..)`.
2. Về mặt đường điều khiển: join point hiện tại phải nằm trong `cflow` hoặc `cflowbelow` của `OrderService.processOrder()`.

**Không nên nhầm** `cflow(P)` với “tìm tất cả method mà `P` có thể gọi đến” bằng phân tích tĩnh. AspectJ đánh giá membership trong control flow ở runtime. Đường call chưa chạy, nhánh if không được chọn hoặc method đã return đều không tạo membership tại thời điểm đó.

## 4. Phân biệt chính xác `cflow` và `cflowbelow`

Giả sử entry pointcut `P` khớp execution của `outer()`. Khi gọi:

~~~text
main
 └─ outer                   P matches here
     └─ inner
         └─ leaf
~~~

Ta chỉ quan sát execution của ba method `outer`, `inner`, `leaf`:

| Execution join point | `cflow(P)` | `cflowbelow(P)` | Vì sao |
| --- | --- | --- | --- |
| `outer()` mở đầu | Có | **Không** | `cflow` tính cả entry; `cflowbelow` loại trừ entry |
| `inner()` trong `outer` | Có | Có | Nằm bên dưới entry đang hoạt động |
| `leaf()` trong `inner` | Có | Có | Thuộc nhánh con của cùng entry |
| `other()` sau khi `outer` return | Không | Không | Entry không còn trên dynamic control flow |

Có thể diễn đạt:

~~~text
cflow(P)      = { entry(P) } ∪ { các join point ở bên dưới entry(P) }
cflowbelow(P) =                { các join point ở bên dưới entry(P) }
~~~

Công thức là **mô hình tư duy cho một lần kích hoạt entry đơn lẻ**. Khi có đệ quy hoặc các kích hoạt `P` lồng nhau, cần xét nhiều entry đang hoạt động cùng lúc; một join point có thể là entry cho lần kích hoạt bên trong nhưng vẫn nằm **bên dưới** một entry `P` khác phía ngoài.

### Khác gì với `cflow(P) && !P`?

Dễ nghĩ rằng:

~~~aspectj
cflowbelow(P)
~~~

luôn tương đương:

~~~aspectj
cflow(P) && !P
~~~

Nhưng **không nên thay thế máy móc**, nhất là khi `P` có thể khớp nhiều join point lồng nhau/đệ quy. `!P` loại bỏ **mọi join point hiện tại khớp P**. Ngược lại, một join point khớp `P` bên trong vẫn có thể nằm dưới một entry `P` khác đã bắt đầu trước đó, nên `cflowbelow(P)` có thể đúng tại join point lồng trong ấy. Hãy hiểu “below” theo **quan hệ control flow của một entry đang hoạt động**, không đơn giản là phủ định nhãn method.

## 5. Ví dụ đầy đủ: Java 17 + AspectJ đếm join point

Ví dụ sau dùng **compile-time weaving của AspectJ** để quan sát ba method trong một chương trình Java nhỏ. Cấu trúc gồm một file Java và một file aspect. Chương trình không dùng thư viện ứng dụng; chỉ cần một bản phân phối AspectJ tương thích với JDK đang chạy, trong đó có compiler `ajc` và runtime `aspectjrt.jar`.

Điểm thiết kế: hai advice tăng hai bộ đếm độc lập thay vì cùng in log tại mọi join point. Nhờ vậy, ví dụ **không phụ thuộc vào thứ tự chạy của hai before advice** cùng khớp một join point; kết quả cuối rõ ràng và kiểm chứng được.

### 5.1. Tệp `FlowDemo.java`

~~~java
public class FlowDemo {
    // Package-private để aspect trong cùng package cập nhật.
    static int cflowHits = 0;
    static int belowHits = 0;

    void outer() {
        inner();
    }

    void inner() {
        leaf();
    }

    void leaf() {
        // Không có side effect; chỉ làm một execution join point.
    }

    void outside() {
        // Execution bên ngoài control flow của outer().
    }

    public static void main(String[] args) {
        FlowDemo demo = new FlowDemo();

        demo.outer();
        demo.outside();

        System.out.println("cflow=" + cflowHits);
        System.out.println("cflowbelow=" + belowHits);
    }
}
~~~

Từ `main()`, chương trình đi qua `outer → inner → leaf`. Sau khi `outer` return mới gọi `outside`. `outside` không được tính vào control flow của `outer`.

### 5.2. Tệp `FlowCounterAspect.aj`

~~~aspectj
public aspect FlowCounterAspect {
    // Entry point của phạm vi control flow cần quan sát.
    pointcut root():
        execution(void FlowDemo.outer());

    // Chỉ đếm ba execution join point cụ thể.
    pointcut tracked():
        execution(void FlowDemo.outer())
        || execution(void FlowDemo.inner())
        || execution(void FlowDemo.leaf());

    // Bao gồm chính execution outer() và descendants.
    before(): tracked() && cflow(root()) {
        FlowDemo.cflowHits++;
    }

    // Chỉ bao gồm descendants bên dưới execution outer().
    before(): tracked() && cflowbelow(root()) {
        FlowDemo.belowHits++;
    }
}
~~~

Đây là **mã AspectJ thật**: phần `pointcut` và `before()` thuộc cú pháp ngôn ngữ khía cạnh, không phải cú pháp Java thuần. Cần compiler `ajc` để weave aspect; lệnh `javac FlowCounterAspect.aj` không hợp lệ.

### 5.3. Biên dịch và chạy

Đặt hai file cùng thư mục. Cần cài phiên bản AspectJ có khả năng chạy với JDK đang sử dụng, thêm executable `ajc` vào `PATH`, đồng thời biết vị trí `aspectjrt.jar` của cùng bản phân phối.

~~~bash
ajc -d out FlowDemo.java FlowCounterAspect.aj

# macOS / Linux: đường dẫn runtime ví dụ theo ASPECTJ_HOME
java -cp "out:$ASPECTJ_HOME/lib/aspectjrt.jar" FlowDemo
~~~

Trên Windows PowerShell, thay dấu phân tách classpath bằng dấu chấm phẩy:

~~~powershell
ajc -d out FlowDemo.java FlowCounterAspect.aj
$runtimeJar = Join-Path $env:ASPECTJ_HOME "lib/aspectjrt.jar"
java -cp "out;$runtimeJar" FlowDemo
~~~

**Tiền điều kiện:** biến `ASPECTJ_HOME` phải trỏ tới bản phân phối có file `lib/aspectjrt.jar`; nếu cài AspectJ bằng Maven/Gradle hoặc đặt JAR ở nơi khác, dùng đúng đường dẫn runtime thực tế. Compiler và runtime cần tương thích. Nếu compiler yêu cầu xác định source/target level, cấu hình cấp Java phù hợp cho phiên bản `ajc` đang dùng; ví dụ chỉ dùng cú pháp Java đơn giản để giảm phụ thuộc vào phiên bản ngôn ngữ.

### 5.4. Kết quả mong đợi

~~~text
cflow=3
cflowbelow=2
~~~

Giải thích chính xác:

| Thời điểm | Join point được `tracked()` chọn? | Trong `cflow(root())`? | Trong `cflowbelow(root())`? |
| --- | --- | --- | --- |
| Thực thi `outer()` | Có | Có | Không |
| Thực thi `inner()` | Có | Có | Có |
| Thực thi `leaf()` | Có | Có | Có |
| Thực thi `outside()` | **Không** | Không | Không |
| Thực thi `main()` | **Không** | Không | Không |

Do đó `cflowHits` tăng ba lần, `belowHits` tăng hai lần. Không có statement nào trong thân ba method tự tăng bộ đếm; mọi thay đổi phát sinh từ hai **before advice** được weave vào execution join point tương ứng.

**Điều kiện của kết quả:** cả hai file phải được biên dịch/weave trong cùng cấu hình. Nếu chỉ biên dịch Java bằng `javac` hoặc chạy class không được weave thì hai counters vẫn là 0; đó là dấu hiệu aspect **không tham gia** chứ không phải `cflow` đã khớp sai.

## 6. Tại sao thêm `tracked()` ngoài `cflow(root())`?

Một pointcut đơn lẻ:

~~~aspectj
before(): cflow(root()) {
    // ...
}
~~~

có thể áp trên **rất nhiều join point** nằm trong phạm vi điều khiển, tùy mức weaving và tập join point AspectJ có thể quan sát. Trong ví dụ có mục tiêu đếm đúng ba method execution, ta dùng:

~~~aspectj
tracked() && cflow(root())
~~~

Điều đó giúp:

- **Rõ phép đo**: chỉ đếm execution của `outer`, `inner`, `leaf`, không đếm constructor, method call, field access hoặc hook khác.
- **Giảm phạm vi advice**: không chạy trên mọi join point chỉ vì nằm trong control flow.
- **Giải thích đúng semantics**: `cflow` là điều kiện ngữ cảnh, còn `tracked` là điều kiện loại/vị trí sự kiện.
- **Dễ kiểm thử**: dự đoán được chính xác số lần increment trong một lịch chạy xác định.

Trong chương trình thật, thường kết hợp điều kiện ngữ cảnh với điều kiện tài nguyên:

~~~aspectj
execution(* AuditStore.save(..))
    && cflow(execution(void BatchRunner.runBatch(..)))
~~~

Nó nói: “chỉ áp policy tại execution của `AuditStore.save` **khi đang nằm trong luồng thực thi động do `runBatch` mở ra**”. Nó **không** nói rằng mọi method do `runBatch` gọi đều được phép hoặc chắc chắn `save` sẽ được gọi.

## 7. Vì sao `execution` và `call` cho kết quả khác?

AspectJ phân biệt:

- `call(ReturnType Type.method(..))` khớp **điểm gọi** một method, nằm phía *caller*.
- `execution(ReturnType Type.method(..))` khớp **việc thực thi thân method**, nằm phía *callee*.

Sơ đồ:

~~~text
Caller.someMethod()
   |
   +-- [call join point] ---> Target.method()
                                 |
                                 +-- [execution join point]
                                 |    body...
                                 +-- return
~~~

Nếu dùng `cflow(call(...))`, entry là **call join point**. Nếu dùng `cflow(execution(...))`, entry là **execution join point**. Cả hai có thể bao quanh những phần khác nhau của quá trình gọi do advice, dispatch và vùng được weave; chỉ dựa vào tên method không đảm bảo chúng là cùng một entry.

Trong ví dụ phần 5, cố ý chọn `execution` để làm việc trên một execution entry rõ ràng, thay vì phụ thuộc caller cụ thể. Khi muốn diễn tả *lời gọi được phát ra từ đâu*, cần xem xét `call` hoặc các điều kiện lexical. Khi muốn diễn tả *operation thực sự đang chạy ở callee*, `execution` thường dễ hiểu hơn.

**Điểm giới hạn:** một class gọi tới thư viện chưa được weave có thể tạo những join point khác với khi toàn bộ bytecode được weave. Việc match một `call` phụ thuộc call site đã được instrument; match `execution` phụ thuộc body/implementation có thể được weave. Phải xác minh build/runtime thực tế.

## 8. `cflow` khác `within` và `withincode` ở điểm nào?

Giả sử method `audit.log` được gọi cả từ `OrderService.place` lẫn `MaintenanceTool.repair`.

| Pointcut | Cơ sở quyết định | Điều nó không biểu đạt |
| --- | --- | --- |
| `within(OrderService)` | Join point nằm về mặt lexical trong type đó | Không tự chọn method của class khác chỉ vì được gọi từ OrderService |
| `withincode(* OrderService.place(..))` | Join point nằm trong code lexical của method `place` | Không tự theo toàn bộ chuỗi gọi sâu qua các class khác |
| `cflow(execution(* OrderService.place(..)))` | Join point hiện tại thuộc dynamic control flow mở bởi execution `place` | Không tự yêu cầu join point là loại execution cụ thể |
| `cflowbelow(execution(* OrderService.place(..)))` | Như trên nhưng nằm dưới entry | Không khớp chính entry mở đầu |
| `execution(* AuditStore.log(..)) && cflow(...)` | Execution của `log` diễn ra trong control flow phù hợp | Không match `log` ở một đường gọi ngoài flow |

Ví dụ `OrderService.place` gọi `Inventory.reserve`, sau đó `Inventory.reserve` gọi `AuditStore.log`. `withincode(* OrderService.place(..))` không chọn execution của `AuditStore.log` vì nó **không nằm trong code lexical của `place`**. Nhưng `cflow(execution(* OrderService.place(..)))` có thể đúng tại `AuditStore.log` khi execution của `place` vẫn đang hoạt động.

Có thể dùng cả điều kiện lexical lẫn dynamic, nhưng không dùng thay nhau nếu yêu cầu nghiệp vụ phụ thuộc call stack.

## 9. Đệ quy và nhiều kích hoạt lồng nhau

Xét:

~~~text
outer(level=2)           <- entry A
  |
  +-- outer(level=1)     <- entry B; đồng thời nằm dưới A
        |
        +-- leaf()
~~~

Giả sử `P` khớp cả hai execution `outer`. Khi `outer(level=1)` bắt đầu:

- Nó là **entry join point** của kích hoạt B.
- Nó đồng thời nằm **bên dưới entry A** vẫn đang hoạt động.
- Vì vậy `cflowbelow(P)` có thể đúng tại execution `outer(level=1)`, mặc dù biểu thức `P` cũng đúng ở join point này.

Đây là lý do không nên luôn thay `cflowbelow(P)` bằng `cflow(P) && !P`. Trong đệ quy, hai biểu thức có thể cho những tập match khác nhau.

Tương tự, nếu pointcut `P` chọn nhiều method entry khác nhau có thể lồng nhau, `cflow` phản ánh **các lần kích hoạt thực tế**, không giả định chỉ có một entry duy nhất cho toàn chương trình. Khi đặt state trong advice, phải cân nhắc mỗi lần kích hoạt, recursion depth và ownership, tránh trộn context của các entry lồng nhau.

Nếu một concern chỉ nên chạy ở entry ngoài cùng, có thể cần pointcut/guard riêng để loại recursion hoặc đánh dấu scope; không suy rằng `cflowbelow` tự mang ý nghĩa “một lần duy nhất cho cả workflow”.

## 10. Gắn dữ liệu từ entry pointcut tới join point bên trong

Một khả năng quan trọng của `cflow` là **truyền/bind context** được match tại entry đến advice ở bên trong dynamic flow, với các pointcut parameter được định nghĩa phù hợp.

Mẫu AspectJ minh họa:

~~~aspectj
pointcut batchEntry(String jobId):
    execution(void BatchRunner.run(String))
    && args(jobId);

before(String jobId):
    execution(* AuditStore.record(..))
    && cflow(batchEntry(jobId)) {
    System.out.println("In batch: " + jobId);
}
~~~

Đây là đoạn **minh họa cú pháp**, không phải file hoàn chỉnh vì `BatchRunner` và `AuditStore` chưa được khai báo. Ý tưởng: khi `run(String)` được gọi với `jobId="J-42"`, advice cho `AuditStore.record` bên trong dynamic flow có thể nhận `jobId` thuộc entry phù hợp.

Cần phân biệt:

- `args(jobId)` ở `batchEntry` lấy tham số từ **entry join point**.
- `execution(* AuditStore.record(..))` chọn **join point hiện tại** mà advice sẽ chạy.
- `cflow(batchEntry(jobId))` là điều kiện runtime và **liên kết** dữ liệu của entry động với advice.

Điều này có thể hỗ trợ correlation/audit theo workflow mà không cần thêm tham số `jobId` vào tất cả method trung gian. Tuy nhiên, không dùng context lấy từ một đối số thiếu tin cậy làm căn cứ cấp quyền nếu chưa xác thực/ủy quyền; cflow không biến dữ liệu do caller cung cấp thành identity đáng tin cậy.

## 11. Kết hợp với `before`, `after` và `around`

`cflow`/`cflowbelow` là **pointcut designator**, không phải một loại advice riêng. Có thể kết hợp với những advice mà bộ máy AOP hỗ trợ:

~~~aspectj
before(): execution(* Store.save(..))
          && cflow(execution(void OrderService.place(..))) {
    // Ghi thời điểm bắt đầu thao tác save ở trong flow đặt hàng.
}
~~~

Đây là đoạn mô tả cú pháp; chưa phải chương trình độc lập.

Một **around advice** có thể chặn `proceed()` khi join point nằm trong control flow được chọn, ví dụ áp policy kiểm soát ở tầng storage khi đang xử lý lệnh import. Tuy nhiên:

- Mỗi `proceed()` phải tuân hợp đồng return/exception của join point.
- Bỏ `proceed()` có thể bỏ qua side effect của method đích.
- Gọi `proceed()` nhiều lần có thể lặp tác động, cần hợp đồng retry/idempotency.
- Advice nằm bên trong một around advice short-circuit có thể không chạy.
- Thứ tự các advice cùng match một join point ảnh hưởng context, metrics và bảo mật.

Không dùng `cflow` như một cơ chế bảo vệ đủ mạnh để nói “bất kỳ ai cũng không thể gọi Store.save ngoài luồng đơn hàng”. Nếu các đường ngoài flow vẫn truy cập tài nguyên nhạy cảm, policy kiểm soát truy cập cần có enforcement phù hợp với mọi entry path.

## 12. Luồng đồng bộ, bất đồng bộ và thread boundary

`cflow` diễn tả **dynamic control flow đang hoạt động**. Nó không tự tạo cơ chế truyền scope hoặc principal xuyên mọi asynchronous boundary.

Ví dụ:

~~~text
Thread A:
  runBatch()
    |
    +-- executor.submit(task)
    |
    +-- return

Thread B (sau đó):
  task.run()
    |
    +-- AuditStore.record()
~~~

Khi `runBatch` tạo task và return, execution của task trên Thread B **không tự thuộc dynamic control flow của execution `runBatch` trên Thread A**. Việc chuyển `Runnable` hay `CompletionStage` sang executor không có nghĩa AspectJ `cflow(runBatch)` tiếp tục áp cho method bên worker. Cơ chế cflow truyền thống theo ngữ cảnh luồng thực thi động, không tương đương distributed trace hoặc một context token được lan truyền tự động.

Các hệ quả:

1. Một advice `before(): save() && cflow(batchEntry())` có thể chạy với thao tác save **đồng bộ** trong `batchEntry`, nhưng không chạy với save của worker ở luồng khác.
2. Advice `after returning` ở entry method có thể kích hoạt khi entry trả **handle**, không phải khi tác vụ hoàn tất.
3. `CompletableFuture.thenApply(...)` có thể chạy ở luồng khác hoặc lúc khác; không nên suy membership cflow từ sơ đồ logic nghiệp vụ.
4. Nếu dùng executor, cần một mô hình truyền context được thiết kế tường minh, hoặc đặt join point entry phù hợp **ở chính worker**.
5. Không xem `ThreadLocal` như một giải pháp chuyển context tự động. Context mang security/transaction còn phải có lifetime, quyền và cleanup đúng.

Ví dụ thiết kế lại:

~~~text
submit(jobId, work)
    |
    +-- wrap task with explicit context
           |
           +-- worker.run()
                   |
                   +-- join point entry ở worker
                   +-- method cần quan sát/kiểm soát
~~~

Ở đây có thể đặt pointcut root vào `worker.run` được weave, hoặc dùng scoped explicit context do tầng được tin cậy quản lý. Không cần cố khiến một `cflow` của method đã return “tồn tại mãi” qua thread khác.

## 13. `cflow` và context của transaction, authorization, tracing

### 13.1. Transaction

Transaction là phạm vi **tài nguyên và transaction manager**, không phải chỉ là phạm vi call stack. Một pointcut `cflow(execution(* OrderService.place(..)))` có thể xác định method nào chạy trong luồng lời gọi của use-case, nhưng **không tự tạo transaction**, không chứng minh connection đã tham gia transaction, và không bảo đảm rollback/commit nếu lời gọi bất đồng bộ hoặc qua resource khác.

Nếu transaction advice được gắn ở một entry join point, phải kiểm tra ownership, propagation, rollback policy, commit timing và resource thật. `cflow` chỉ giúp chọn ngữ cảnh để áp advice, không thay thế transaction coordinator.

### 13.2. Authorization

Một storage method có thể cần phân quyền ở mọi entry path. Nếu chỉ bảo vệ nó khi `cflow(execution(* Controller.action(..)))`, các lời gọi từ CLI, batch hoặc direct service path có thể đi vòng ngoài flow và không được kiểm tra. Bảo mật nên **fail closed** và có điểm enforcement không bị bỏ qua. `cflow` phù hợp điều kiện *thêm* theo ngữ cảnh hơn là làm hàng rào duy nhất cho tài nguyên nhạy cảm.

### 13.3. Tracing và correlation

`cflow` hữu ích để gắn telemetry cho các join point chạy đồng bộ trong một phạm vi. Nhưng trace xuyên service, process và thread cần cơ chế propagating trace context; `cflow` không tự truyền trace ID qua mạng hoặc worker. Không đánh đồng “ở trong cflow” với “thuộc cùng business request về mặt phân tán”.

### 13.4. Retry và caching

Nếu một around advice retry một method bên trong entry, join point có thể xuất hiện nhiều lần trong cùng control flow; advice dùng `cflow` được kích hoạt theo **mỗi lần execution thực tế**. Nếu cache trả sớm ở lớp ngoài, method bên trong không chạy và không phát sinh join point cần match. `cflow` không tự bảo đảm method sẽ thực thi.

## 14. Chi phí runtime và cách kiểm soát phạm vi

Các pointcut dựa trên chữ ký/lexical position thường có nhiều phần điều kiện có thể giải quyết khi weave. `cflow`/`cflowbelow` cần xét **trạng thái dynamic control flow** khi runtime đi tới join point; công cụ có thể sinh mã theo dõi entry/exit hoặc dùng chiến lược tối ưu hóa riêng.

Vì vậy:

- Không đặt điều kiện `cflow` cực rộng trên mọi join point nếu chỉ cần một tập operation nhỏ.
- Hãy kết hợp điều kiện tĩnh cụ thể như `execution(* Store.save(..))` để giảm phạm vi quan sát.
- Ưu tiên root `P` có ý nghĩa nghiệp vụ rõ; tránh các pointcut root match quá nhiều event khó kiểm soát.
- Đo overhead thực tế nếu join point chạy cực thường xuyên, như thao tác nhỏ trong vòng lặp nóng.
- Dùng các công cụ compiler/weaver phù hợp để kiểm tra join point nào thực sự được weave.
- Quan sát nested entry và recursion nếu policy cần state; tránh state global không an toàn đồng thời.
- Chú ý vòng đời class loader và build config: aspect không được weave sẽ không có hiệu lực dù cú pháp đúng.

Không có một mức overhead cố định cho mọi bản AspectJ, mọi JDK và mọi pointcut. Chi phí phụ thuộc cách biên dịch, phạm vi điểm match, số advice, cấu hình weave, tối ưu hóa của công cụ và đặc điểm workload.

## 15. Debug: vì sao pointcut không match?

Khi một advice sử dụng `cflow` hoặc `cflowbelow` không chạy như mong đợi, kiểm tra theo thứ tự:

1. **Entry `P` thực sự match chưa?** `execution` và `call` khác nhau; chữ ký method phải chính xác.
2. **Class nào đã được weave?** Compile-time, post-compile hoặc load-time weaving chỉ có tác dụng trên đúng class/module được cấu hình.
3. **Join point đích được chọn chưa?** Có thể điều kiện `execution(* Repository.*(..))` quá hẹp dù `cflow` đúng.
4. **Join point nằm trong cùng dynamic flow không?** Entry đã return, work chạy trên executor hoặc lời gọi từ đường khác đều làm điều kiện sai.
5. **Có biến thể method/overload/bridge không?** Chữ ký pointcut phải xét method thực được chọn.
6. **Advice khác có short-circuit không?** Nếu method không chạy thì execution join point không xuất hiện.
7. **Có recursion/nested root không?** Tập `cflowbelow` có thể khác suy nghĩ trực giác.
8. **Có nhiều thread đồng thời không?** Log từ hai thread có thể xen kẽ; không dùng log order toàn cục làm bằng chứng duy nhất.
9. **Có instrumentation/agent xung đột không?** Thứ tự weave và bytecode transform có thể thay đổi khả năng match.
10. **Runtime `aspectjrt.jar` có đúng với code woven không?** Sai hoặc thiếu runtime có thể gây lỗi khi chạy.

**Cách thử nhanh:** tạo một before advice chọn riêng `root()`, sau đó một before advice chọn `tracked()` không có cflow, cuối cùng thêm `cflow(root())`. Lần lượt so sánh điểm match giúp phân biệt lỗi ở entry, join point đích hay điều kiện dynamic. Đây là hướng debug, không phải lời khuyên ghi log dữ liệu nhạy cảm vô hạn trong môi trường production.

## 16. Các lỗi nhận thức phổ biến

| Nhầm lẫn | Sửa lại |
| --- | --- |
| “`cflow` là danh sách những method `P` có thể gọi” | Nó xét control flow **đang diễn ra**, không suy toàn bộ call graph có thể xảy ra |
| “`cflowbelow` là alias của `cflow(P) && !P`” | Có thể khác khi `P` lồng nhau/đệ quy |
| “`cflowbelow` chọn chính entry method” | Nó loại entry mở đầu, trừ trường hợp join point là entry bên trong nhưng nằm dưới một entry khác |
| “`cflow` truyền scope qua `CompletableFuture`” | Không tự theo worker/thread hoặc distributed flow |
| “Có advice `cflow` tức method gốc luôn chạy” | Cache/around advice khác có thể short-circuit; event chưa xảy ra thì không có gì để match |
| “`call` và `execution` có cùng boundary” | Call nằm bên caller, execution nằm ở callee |
| “`withincode` giống `cflow`” | Một cái lexical; một cái dynamic |
| “Một `cflow` tự bảo đảm transaction” | Cần transaction manager và tài nguyên thực |
| “Một `cflow` làm bảo mật kín mọi đường gọi” | Đường ngoài flow không được chọn; cần enforcement có coverage đầy đủ |
| “AspectJ là cú pháp Java thường” | `aspect`, `pointcut` và advice cần compiler/weaver thích hợp |
| “Nếu compiler thành công thì aspect chắc chắn áp đúng” | Cần kiểm chứng join point/weaving và hành vi runtime |
| “Mỗi lần gọi có một global cflow dùng chung” | Phải xét control-flow context theo execution/thread và lồng nhau |

## 17. Kiểm thử có ý nghĩa học tập

### 17.1. Với ví dụ phần 5

- **Test A — root vào đúng một lần:** `outer → inner → leaf`; kết quả `cflow=3`, `cflowbelow=2`.
- **Test B — outside sau root:** `outside` không làm tăng counters vì không thuộc `tracked()` và không nằm trong active cflow.
- **Test C — gọi `inner()` trực tiếp từ `main`:** nếu thay body main chỉ gọi `inner()`, không có execution `outer` mở đầu nên hai counters vẫn bằng 0.
- **Test D — gọi `outer()` hai lần tuần tự:** mỗi lần thêm 3 và 2, sau hai lần mong đợi 6 và 4.
- **Test E — bỏ file aspect khỏi weave:** counters giữ 0, chứng minh khác biệt giữa logic Java gốc và advice được weave.

### 17.2. Đường cần thử trong ứng dụng thực

| Kiểm thử | Mục tiêu |
| --- | --- |
| Entry `P` bắt đầu rồi method con gọi cùng thread | Pointcut động đúng |
| Method con được gọi từ entry khác | Không false-positive |
| Entry đã return mới gọi method đích | Không còn active flow |
| Recursion hoặc nested entry `P` | Phân biệt `cflowbelow` với phủ định đơn giản |
| Gọi method đồng bộ có exception | Scope được kết thúc đúng khi stack unwinds |
| Async task trên executor | Không giả định cflow tự lan theo task |
| Method overload hoặc thư viện chưa weave | Hiểu rõ coverage |
| Có cache/retry/transaction advice khác | Đúng số lần join point xuất hiện và thứ tự advice |
| Tải nhiều thread | Counters/log correlation không bị trộn ngữ cảnh |
| Thay đổi config weaving | Test báo lỗi nếu aspect không còn active |

Nếu đo bằng counter shared giữa nhiều thread, cần cấu trúc đồng bộ/atomic thích hợp; các trường `static int` trong demo chỉ dành cho trường hợp đơn luồng xác định. Trên production, các chỉ số còn cần tên operation và key correlation để không ghép sai những control flow cùng chạy.

## 18. Khi nào nên dùng `cflow` và khi nào không?

**Nên cân nhắc** khi concern phụ thuộc một ngữ cảnh lời gọi đồng bộ, chẳng hạn:

- Đánh dấu log/metrics của những method con chỉ khi được gọi từ một nghiệp vụ cụ thể.
- Thêm profiling chuyên sâu cho các operation phát sinh trong một workflow.
- Gắn thông tin từ entry method đến advice chạy ở method con (nếu chính sách cho phép).
- Phân biệt cùng một method được gọi từ nhiều use-case bằng dynamic call stack.
- Dùng `cflowbelow` khi muốn áp policy **chỉ cho phần bên trong**, tránh advice áp lên chính entry.

**Không nên dùng làm lời giải duy nhất** nếu mục tiêu là:

- Bảo vệ một resource bắt buộc được kiểm tra với **mọi** entry path.
- Theo dõi xuyên thread, process, HTTP, message broker hoặc các continuation dài sau method return.
- Xây transaction phân tán hoặc bảo đảm rollback/commit xuyên nhiều tài nguyên.
- Thay thế truyền ngữ cảnh được quản lý rõ ràng cho danh tính người dùng, tenant hoặc correlation ID trong tác vụ nền.
- Chọn một tập method cố định chỉ dựa trên tên/type/annotation: pointcut tĩnh có thể đơn giản hơn.

**Nguyên tắc lựa chọn:** nếu câu hỏi là “join point thuộc type/method nào?” thì dùng pointcut chữ ký/lexical. Nếu câu hỏi là “join point này **đang xảy ra trong quá trình chạy do method X khởi phát** hay không?” thì `cflow` hoặc `cflowbelow` mới phù hợp.

## 19. Checklist tự đánh giá

Trước khi dùng `cflow`/`cflowbelow`, hãy trả lời:

1. Entry `P` chọn đúng **call** hay **execution** join point?
2. Advice có cần khớp **chính entry** không? Nếu cần chọn `cflow`; nếu không, cân nhắc `cflowbelow`.
3. Tập join point đích đã giới hạn bằng `execution/call/within` phù hợp chưa?
4. Có recursion hoặc nhiều entry `P` lồng nhau không?
5. Method đích có được gọi ngoài flow đó hay sau khi entry đã return không?
6. Có tác vụ async, thread switch hoặc callback làm thay đổi dynamic scope không?
7. Cơ chế weaving đã instrument đúng các class và join point chưa?
8. Có advice nào trước đó có thể bỏ `proceed()`, retry hoặc đổi outcome không?
9. Nếu dùng để kiểm soát quyền/giao dịch, có enforcement/resource transaction thực ngoài điều kiện cflow không?
10. Đã thử trường hợp âm tính **không nằm trong flow** và trường hợp **nằm dưới entry** chưa?
11. Runtime overhead và log/metric cardinality có được đo đúng trên workload không?
12. Đã phân biệt rõ lexical scope và dynamic control-flow scope trong tài liệu/bài kiểm thử chưa?

## 20. Tổng kết

`cflow(P)` và `cflowbelow(P)` thể hiện năng lực lựa chọn join point theo **luồng điều khiển động** của AspectJ. `cflow` tính cả join point khởi đầu do `P` chọn; `cflowbelow` chọn các join point xảy ra ở **bên dưới** entry đó. Khi kết hợp với `execution(...)` hoặc `call(...)`, chúng giúp áp advice có điều kiện theo cách một operation được đi tới, thay vì chỉ dựa vào tên method.

Ba giới hạn cần nhớ: **(1)** dynamic flow không phải lexical call graph; **(2)** đệ quy/lồng nhau làm `cflowbelow` khác phép phủ định đơn giản của `P`; **(3)** không tự truyền context qua luồng bất đồng bộ hoặc thay thế cơ chế bảo mật/giao dịch thực. Dùng hai pointcut này đúng lúc sẽ minh họa rất rõ điểm mạnh của AOP: tách chính sách xuyên suốt theo **bối cảnh đang thực thi**, với ngữ nghĩa và phạm vi được xác định cụ thể.