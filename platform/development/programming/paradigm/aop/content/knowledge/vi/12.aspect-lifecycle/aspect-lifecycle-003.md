# Vòng đời gắn với luồng điều khiển khi công cụ hỗ trợ trong Aspect/AOP

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), **aspect** đóng gói những hành vi cắt ngang như ghi nhận thời lượng, theo dõi một thao tác nghiệp vụ hoặc thống kê các điểm can thiệp. Một câu hỏi quan trọng là: **trạng thái của aspect tồn tại trong bao lâu, và có được chia sẻ giữa những lần gọi không?**

Một số mô hình AOP có thể tạo **một instance aspect cho mỗi luồng điều khiển động được chọn**. Khi một điểm bắt đầu (*entry join point*) khớp điều kiện, cơ chế tạo hoặc kích hoạt một instance gắn với **lần đi vào luồng đó**; những điểm can thiệp nằm trong phạm vi động thích hợp có thể dùng cùng instance. Khi luồng điều khiển rời phạm vi, instance đó không còn là instance đang hoạt động của luồng ấy. Cách tổ chức này thường được gọi là **per-control-flow aspect lifecycle**, hoặc **`percflow`** trong những ngôn ngữ AOP có cơ chế tương ứng.

Điều này **khác** với chỉ dùng biểu thức **`cflow`** để lọc pointcut. `cflow` có thể kiểm tra một điểm đang thuộc một luồng gọi được chọn, còn một cơ chế **per-control-flow instantiation** quyết định **tạo và quản lý instance aspect theo mỗi lần đi vào luồng**. Một hệ thống có thể hỗ trợ kiểm tra luồng điều khiển nhưng **không** hỗ trợ khởi tạo aspect instance theo luồng. Không được coi mọi cách triển khai proxy/interceptor hoặc mọi bộ weaving đều có khả năng giống nhau.

Bài này chỉ nói về Aspect/AOP cơ bản và nâng cao nói chung. Ví dụ cú pháp thuộc một ngôn ngữ AOP cụ thể sẽ được ghi rõ phạm vi hỗ trợ; ví dụ **Java 17 thuần** mô phỏng lifecycle để hiểu hành vi và có thể biên dịch bằng JDK mà không cần một weaver riêng.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **aspect definition**, **aspect instance** và **activation/lifetime** theo một luồng điều khiển.
2. Hiểu **dynamic control flow** khác phạm vi mã nguồn tĩnh và khác “một HTTP request” hoặc “một thread” theo nghĩa mặc định.
3. Phân biệt pointcut **`cflow`**, **`cflowbelow`**, chính sách tạo instance kiểu **`percflow`** và cơ chế tạo instance khác.
4. Trình bày những gì xảy ra khi có **nhiều lời gọi lồng nhau, đệ quy, ngoại lệ, trả về sớm và cleanup**.
5. Biết khi nào hai join point chia sẻ cùng instance, và khi nào phải tạo/khôi phục instance theo phạm vi mới.
6. Đánh giá nguy cơ chia sẻ trạng thái toàn cục, rò rỉ `ThreadLocal`, truyền sai ngữ cảnh qua async và tác động của thứ tự interceptor.
7. Đọc ví dụ Java 17 mô phỏng per-flow instance qua một ngăn xếp theo luồng, với đầu ra xác định.
8. Thiết kế kiểm thử phân biệt **instance aspect per-flow** và **chỉ lọc pointcut theo control flow**, đồng thời giữ nguyên kết quả và ngoại lệ nghiệp vụ.

## 2. Các thuật ngữ phải tách bạch

| Khái niệm | Nghĩa | Ví dụ |
| --- | --- | --- |
| **Join point** | Điểm mà mô hình AOP cho phép can thiệp | Thực thi phương thức `handle()` |
| **Pointcut** | Điều kiện chọn những join point phù hợp | “Thực thi `dao.load()` khi đang nằm trong `handle()`” |
| **Advice** | Hành vi bổ sung chạy tại điểm được chọn | Tăng bộ đếm, ghi trace |
| **Aspect definition** | Bản mô tả khía cạnh và quy tắc của nó | Khai báo một `TraceAspect` |
| **Aspect instance** | Một đối tượng có trạng thái chứa bộ đếm/tài nguyên | Instance dành cho `handle` lần thứ nhất |
| **Instantiation policy** | Quy tắc xác định có bao nhiêu instance và chúng gắn với cái gì | Singleton, per-target, per-control-flow nếu được hỗ trợ |
| **Dynamic control flow** | Chuỗi gọi đang diễn ra từ một điểm vào trong runtime | `handle → validate → load` |
| **Activation** | Khoảng mà một instance có hiệu lực trong phạm vi | Từ lúc vào root tương ứng tới khi rời root |
| **Scope cleanup** | Dỡ liên kết instance khỏi ngữ cảnh hoạt động | Pop khỏi stack khi root kết thúc |

**Một định nghĩa aspect không đồng nghĩa một instance duy nhất.** Công nghệ có thể dùng một instance toàn chương trình, nhiều instance theo đối tượng, hoặc nhiều instance theo phạm vi luồng điều khiển. Cũng không phải cứ có một phương thức gọi tên `begin` thì aspect tự động được tạo tại đó: điều kiện chọn root và khả năng instantiation phải được công cụ hỗ trợ.

## 3. Dynamic control flow là gì?

Hãy xem lời gọi đồng bộ:

```text
main()
  |
  +-- Checkout.handle("A")
        |
        +-- Validation.check()
        |
        +-- Catalog.find()
              |
              +-- Database.read()
```

Trong khi `Checkout.handle("A")` **đang hoạt động trên ngăn xếp lời gọi**, những điểm bên trong như `Catalog.find()` hoặc `Database.read()` thuộc **luồng điều khiển động** bắt đầu từ `handle("A")`, theo mô hình kiểm tra luồng điều khiển phù hợp.

Điều khác biệt với bộ lọc **theo tên package hoặc vị trí mã nguồn** là dynamic control flow phản ánh **đường gọi thực tế ở runtime**:

- Một phương thức trong package dữ liệu có thể nằm trong flow của `handle()` ở lần gọi thứ nhất.
- Cùng phương thức đó khi được gọi độc lập từ công việc nền có thể **không nằm** trong flow của `handle()`.
- Một phương thức thuộc package khác vẫn có thể tham gia flow, nếu đường thực thi đi tới nó.
- Thời điểm lời gọi bắt đầu và kết thúc thay đổi tập điểm đang nằm trong flow.

### 3.1. Ví dụ hai lần gọi cùng mã nhưng context khác nhau

```text
Lần 1: main -> handle(A) -> dao.load(A)
Lần 2: main -> dao.load(B)
```

Nếu pointcut yêu cầu `dao.load` **đang ở bên trong dynamic control flow của `handle`**, lần 1 có thể khớp; lần 2 không khớp. Đó là lựa chọn dựa trên **call stack đang chạy**, không chỉ dựa vào tên của `dao.load`.

Một điều kiện kiểu `within(package)` hoặc `withincode(method)` (nếu được hỗ trợ) thường nói về **phạm vi tĩnh của mã**, không thể mặc nhiên thay cho dynamic flow. Các bộ lọc tĩnh và động có thể phối hợp nhưng không đồng nhất.

### 3.2. Dynamic flow khác đối tượng và khác thread

Một `Checkout` instance có thể xử lý nhiều yêu cầu. Nếu dùng **per-target aspect**, các lần xử lý cùng target có thể dùng chung aspect instance theo chính sách đó. Nếu dùng **per-control-flow aspect**, các lần đi vào root khác nhau có thể có **các instance riêng**, dù target giống nhau.

Một thread cũng có thể xử lý **nhiều root lần lượt**, hoặc root lồng nhau. Vì vậy “per-control-flow” không có nghĩa “mỗi thread chỉ có một aspect instance vĩnh viễn”.

## 4. `cflow`, `cflowbelow` và chính sách tạo instance

Một số ngôn ngữ AOP có các khái niệm như sau:

- **`cflow(P)`**: chọn điểm đang ở **trong dynamic control flow của một điểm khớp P**, thường gồm cả chính điểm gốc P theo ngữ nghĩa của công cụ.
- **`cflowbelow(P)`**: chọn điểm **bên dưới** P trong dynamic call flow, thường không gồm chính điểm gốc.
- **`percflow(P)`**: chính sách **tạo aspect instance theo mỗi lần luồng điều khiển được xác lập từ P** nếu hệ AOP hỗ trợ.
- **`percflowbelow(P)`**: biến thể per-flow theo phạm vi bên dưới điểm gốc nếu được công nghệ hỗ trợ; chi tiết về thời điểm tạo/khả dụng cần kiểm tra trong ngôn ngữ đó.

Các tên được nêu là **thuật ngữ/cú pháp thuộc những mô hình AOP cụ thể**, không phải từ khóa Java chuẩn và không xuất hiện trong mọi framework.

### 4.1. Pointcut động không nhất thiết tạo instance mới

Giả sử một aspect dùng chung toàn ứng dụng có advice:

```text
khi dao.load() nằm trong cflow(handle()):
    globalCounter += 1
```

Đây là **giả mã**. Điều kiện `cflow` quyết định **khi nào advice chạy**, nhưng `globalCounter` có thể vẫn nằm trên **một instance aspect dùng chung**, không có bộ đếm độc lập cho mỗi `handle()`.

Muốn “mỗi lần vào `handle()` có một bộ đếm riêng”, phải có **chính sách cấp instance hoặc trạng thái theo flow**. Chỉ thêm `cflow` vào pointcut không tự biến bộ đếm dùng chung thành bộ đếm riêng cho mỗi lần root.

### 4.2. Instance theo flow có điểm khởi tạo và điểm ngừng hiệu lực

Mô hình tổng quát:

```text
Root join point P entered
          |
          v
Create/activate Aspect instance F1
          |
          +--> join point A -> advice on F1
          |
          +--> join point B -> advice on F1
          |
          +--> join point C -> advice on F1
          |
Root P returns / exits with error
          |
          v
Deactivate association with F1
```

Tùy cơ chế, việc tạo object thật có thể xảy ra tại một mốc cụ thể của điểm vào và việc dỡ liên kết có thể được tối ưu theo cách khác; người học nên coi **lifetime logic** là điều kiện cốt lõi.

**Dỡ liên kết với flow** không đồng nghĩa JVM lập tức hủy object hoặc gọi một “destructor” tự động. Java dùng garbage collection; nếu có tham chiếu ở nơi khác, đối tượng vẫn có thể còn sống. Tài nguyên như file, khóa hoặc kết nối vẫn cần quy tắc đóng riêng.

## 5. Luồng điều khiển lồng nhau và đệ quy

Xét:

```text
handle(outer)                 -> Flow F1
  |
  +-- dao.load()              -> aspect F1
  |
  +-- handle(inner)           -> Flow F2, nếu P lại khớp
        |
        +-- dao.load()        -> aspect F2 trong phạm vi inner
  |
  +-- dao.save()              -> quay lại F1
```

Trong một chính sách **mỗi lần đi vào root tạo instance riêng**, root inner tạo F2 dù outer F1 vẫn đang hoạt động. Khi inner kết thúc, context hoạt động quay về F1; F2 không còn là instance đang hoạt động cho lời gọi tiếp theo của outer.

### 5.1. Vì sao cần cấu trúc stack?

Với các root lồng nhau, một biến toàn cục đơn `currentAspect` không đủ. Nếu inner gán F2 và kết thúc bằng cách đặt biến về `null`, nó sẽ làm mất liên kết tới F1 đang tiếp tục chạy.

Một **stack** của các activation cho phép:

1. Vào F1 → **push(F1)**.
2. Vào F2 → **push(F2)**.
3. Điểm bên trong sử dụng **top = F2**, nếu chính sách chọn instance đang hoạt động gần nhất.
4. Ra F2 → **pop(F2)**.
5. Tiếp tục F1 → **top = F1**.
6. Ra F1 → **pop(F1)**.

Đây là **mô hình triển khai để hiểu**, không phải bằng chứng mọi công cụ duy trì cấu trúc stack giống vậy trong bộ nhớ.

### 5.2. Đệ quy có làm tạo nhiều instance không?

Nếu một phương thức root gọi lại chính nó và điều kiện root khớp ở **mỗi lần thực thi**, chính sách per-entry có thể tạo nhiều activation lồng nhau. Nhưng nếu điểm vào được mô tả bằng điều kiện **bên dưới/loại trừ những lần gọi nội bộ** hoặc cơ chế có semantics riêng, số instance có thể khác.

Đừng trả lời “một instance cho mọi recursion” hoặc “mỗi depth chắc chắn một instance” khi chưa xác định **P là loại join point nào** và quy tắc instantiation của công nghệ cụ thể.

### 5.3. Phân biệt instance được chọn với tập instance còn sống

Khi F2 nằm trong F1, cả hai activation có thể **đang nằm trong call stack**. Việc advice tại một join point được áp lên F2, F1 hay cả hai phụ thuộc **ngữ nghĩa của aspect instantiation và pointcut**. Một mô hình Java tự xây có thể chọn chỉ **instance trên đỉnh stack**. Một công cụ AOP có quy tắc advice dispatch khác có thể cần cách diễn giải riêng.

Vì vậy ví dụ Java ở phần sau mô phỏng **một kiểu áp dụng xác định**, không tuyên bố nó tương đương tuyệt đối với mọi biến thể per-flow.

## 6. Vòng đời qua các đường return, throw và around advice

Một root có thể:

- Trả về bình thường;
- Trả về `null` bình thường;
- Hoàn tất phương thức `void`;
- Ném một ngoại lệ;
- Được around advice chặn trước khi thực thi đích;
- Được around advice thử lại nhiều lần.

Đối với một flow scope đã **thực sự được mở**, phải xác định thời điểm **dỡ liên kết** trên cả nhánh return và throw. Cấu trúc mô hình:

```text
onRootEnter:
    flowInstance = activateFlow()
    try:
        return continueInsideRoot()
    finally:
        deactivateFlow(flowInstance)
```

Đây là **giả mã**, không phải API chuẩn của AOP. Đặt cleanup trong `finally` giải thích cách giữ cân bằng số lượt vào/ra trên những đường điều khiển thông thường của Java.

### 6.1. Nếu lỗi xảy ra trước khi khởi tạo?

Nếu quá trình tạo instance, bind context hoặc kiểm tra quyền ném lỗi **trước khi flow được xác lập**, chưa có instance hợp lệ để dỡ. Nếu một phần tài nguyên đã được cấp trước lỗi đó, phải có cơ chế rollback/cleanup riêng cho phần đã cấp.

Không nên đưa `pop()` vô điều kiện trong mọi nhánh mà không biết đã `push()` thành công hay chưa; thao tác sai có thể xóa instance của flow cha.

### 6.2. Nếu cleanup tự ném lỗi?

Một `finally` hoặc advice dọn dẹp ném lỗi mới có thể che ngoại lệ gốc từ nghiệp vụ. Với context thuần quan sát, mục tiêu nên là **giữ nguyên kết quả/ngoại lệ**, ghi nhận lỗi thu dọn theo chính sách phù hợp và tránh để hệ theo dõi phá hợp đồng chính.

Không suy rằng instance per-flow tự quản lý đóng kết nối, kết thúc transaction hoặc rollback. **Lifetime của aspect instance** và **vòng đời các tài nguyên mà aspect sở hữu** liên quan nhưng khác nhau.

### 6.3. Around advice làm thay đổi ranh giới quan sát

Một around advice có thể không gọi `proceed`, hoặc gọi nhiều lần nếu API cho phép. Khi đó:

- Nếu root join point **không được đi vào** do lời gọi bị chặn ở một lớp ngoài, flow tương ứng có thể không hình thành.
- Nếu mỗi lần `proceed` thật sự đi vào lại root, có thể hình thành nhiều flow/activation, tùy loại join point và thứ tự aspect.
- Nếu root được mở **bên ngoài** khối retry, những lần thử bên trong có thể cùng một flow.
- Nếu root nằm **bên trong** retry, các attempt có thể được nhìn như những lần vào riêng.

Cần quan sát thứ tự thực sự của chuỗi aspect trước khi quyết định per-flow instance thuộc **logical request** hay **mỗi attempt**.

## 7. So sánh với các kiểu lifetime khác

| Chiến lược | Dữ liệu được gắn với | Mô hình sử dụng thường gặp |
| --- | --- | --- |
| **Shared/singleton aspect** | Một instance dùng chung theo phạm vi mà công cụ định nghĩa | Chính sách thống kê không giữ context từng request |
| **Per-target** | Một instance cho mỗi target phù hợp | Bộ đếm/trạng thái gắn một đối tượng nghiệp vụ |
| **Per-this** | Một instance theo đối tượng `this` trong ngữ nghĩa join point | Theo dõi trạng thái đối tượng phía ngữ cảnh |
| **Per-type** | Một instance theo loại, khi mô hình hỗ trợ | Thống kê theo class hoặc nhóm loại |
| **Per-control-flow** | Một instance cho mỗi activation của dynamic flow đã chọn | Bộ đếm tạm thời của một lần xử lý |
| **Manual scope** | Một token/context do ứng dụng tự quản | Khi công nghệ AOP không có per-flow instantiation |

Một per-flow aspect không đồng nghĩa “tất cả dữ liệu của một yêu cầu web”. Yêu cầu web có thể chạy qua nhiều thread/tác vụ hoặc nhiều root; một root có thể do lời gọi batch, scheduler hay chương trình desktop tạo ra.

**Chọn scope theo nhu cầu dữ liệu**, không theo tên quen thuộc của framework. Nếu chỉ cần biến đếm cục bộ trong một phương thức, không nhất thiết phải thêm AOP state management.

## 8. Cú pháp minh họa thuộc AspectJ: `percflow` và `cflow`

Một ví dụ **chỉ để đọc cú pháp của ngôn ngữ AspectJ**:

```java
package demo;

public aspect FlowCounter percflow(
        execution(* demo.RequestHandler.handle(..))) {

    private int visits = 0;

    before(): execution(* demo.DataStore.load(..)) {
        visits++;
        System.out.println("loads in this flow=" + visits);
    }
}
```

Các tên lớp trong `demo` là ví dụ; đây là **mã aspect riêng, không biên dịch bằng `javac` thường**, và cần bộ compiler/weaver hiểu cú pháp AspectJ cùng những lớp đích phù hợp.

Đọc ý nghĩa ở mức kiến trúc:

1. `execution(* demo.RequestHandler.handle(..))` xác định **root** dùng cho chiến lược instantiation.
2. `percflow(...)` yêu cầu một **aspect instance theo flow** mà công nghệ đó định nghĩa.
3. Field `visits` thuộc **instance aspect**, không phải field static toàn chương trình.
4. Advice ở `DataStore.load(..)` theo dõi các điểm khớp trong phạm vi áp dụng của instance ấy.
5. Khi không có flow phù hợp, không tự có instance đang hoạt động để thực hiện advice có scope này.

Không nên suy từ ví dụ rằng mọi lần gọi `load` đều được đếm: chỉ những điểm được weave và thuộc phạm vi đã định mới có khả năng kích hoạt advice.

### 8.1. Chỉ dùng `cflow` thì khác gì?

Một aspect dùng chung có thể có điều kiện:

```text
pointcut observeLoad:
    execution(DataStore.load(..))
    AND cflow(execution(RequestHandler.handle(..)))
```

Đây là **giả mã**. Nó mô tả việc lọc `load` theo call flow, nhưng **không tự quyết định** instance aspect riêng cho từng `handle`. Nếu mục tiêu là một bộ đếm riêng cho từng lượt root, phải dùng **instantiation policy** tương ứng hoặc thiết kế scope thủ công.

### 8.2. `cflowbelow` khác `cflow` ở biên root

Khi cần tính cả chính điểm root hay chỉ các điểm dưới root, điều kiện chọn phải thể hiện rõ. Ví dụ “đếm mọi `handle` thuộc flow của `handle`” có thể gặp **khớp chính root**, trong khi “chỉ đếm những điểm bên trong handle” cần cách chọn bên dưới thích hợp.

Không tráo `cflow` và `cflowbelow` chỉ vì chúng giống tên. Ngữ nghĩa cụ thể phụ thuộc loại join point, việc lồng nhau và quy tắc của công nghệ.

### 8.3. Đây không phải quy tắc của mọi AOP

Một cơ chế proxy chỉ quanh phương thức giao diện có thể không thể tạo **instance aspect theo mọi điểm call trong stack** hoặc can thiệp field/constructor tùy ý. Khi không có per-flow policy, có thể tự tạo **scope thủ công** hoặc dùng một mô hình tracing rõ ràng — nhưng không gọi đó là native `percflow` của công cụ.

## 9. Ví dụ Java 17 chạy được: mô phỏng vòng đời theo flow

Để thấy rõ **mỗi lượt vào root → instance riêng → join point bên trong → cleanup**, ví dụ tự xây một bộ scope qua `ThreadLocal<Deque<FlowAspect>>`. Nó hoạt động với JDK thuần, không phụ thuộc compiler/weaver AOP.

**Phạm vi minh họa:** `inFlow` là một **ranh giới root chủ động**, `observe` là mô phỏng lời gọi advice tại các điểm chọn, và `FlowAspect` là một instance có trạng thái theo flow. Đây **không phải** hệ AOP tự phát hiện join point; nó mô tả một phương án quản lý activation và khôi phục parent trong mã đồng bộ.

Tạo tệp `ControlFlowAspectDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ControlFlowAspectDemo {
    static final class FlowAspect {
        private final String label;
        private int events;

        FlowAspect(String label) {
            this.label = label;
            System.out.println("CREATE " + label);
        }

        void observe(String point) {
            events++;
            System.out.println("[" + label + "] " + point + " #" + events);
        }
    }

    private static final ThreadLocal<Deque<FlowAspect>> ACTIVE =
            new ThreadLocal<>();

    static FlowAspect current() {
        Deque<FlowAspect> stack = ACTIVE.get();
        return stack == null ? null : stack.peek();
    }

    static void business(String point) {
        FlowAspect aspect = current();
        if (aspect == null) {
            System.out.println("NO_SCOPE " + point);
        } else {
            aspect.observe("business:" + point);
        }
    }

    static <T> T inFlow(String label, Callable<T> operation)
            throws Exception {
        Deque<FlowAspect> stack = ACTIVE.get();
        if (stack == null) {
            stack = new ArrayDeque<>();
            ACTIVE.set(stack);
        }

        FlowAspect aspect = new FlowAspect(label);
        stack.push(aspect);
        try {
            aspect.observe("entry");
            return operation.call();
        } finally {
            aspect.observe("exit");
            FlowAspect removed = stack.pop();
            if (removed != aspect) {
                throw new IllegalStateException("scope stack corrupted");
            }
            if (stack.isEmpty()) {
                ACTIVE.remove();
            }
            System.out.println("END " + label);
        }
    }

    public static void main(String[] args) throws Exception {
        business("outside");

        inFlow("outer", () -> {
            business("A");
            inFlow("inner", () -> {
                business("B");
                return null;
            });
            business("C");
            return null;
        });

        try {
            inFlow("failed", () -> {
                business("D");
                throw new IllegalArgumentException("invalid");
            });
        } catch (IllegalArgumentException error) {
            System.out.println("CAUGHT " + error.getMessage());
        }
        business("after");

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            inFlow("parent", () -> {
                business("before-task");
                Future<?> future = executor.submit(
                        () -> business("worker"));
                future.get();
                business("after-task");
                return null;
            });
        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac -encoding UTF-8 ControlFlowAspectDemo.java
java ControlFlowAspectDemo
```

Đầu ra dự kiến chính xác:

```text
NO_SCOPE outside
CREATE outer
[outer] entry #1
[outer] business:A #2
CREATE inner
[inner] entry #1
[inner] business:B #2
[inner] exit #3
END inner
[outer] business:C #3
[outer] exit #4
END outer
CREATE failed
[failed] entry #1
[failed] business:D #2
[failed] exit #3
END failed
CAUGHT invalid
NO_SCOPE after
CREATE parent
[parent] entry #1
[parent] business:before-task #2
NO_SCOPE worker
[parent] business:after-task #3
[parent] exit #4
END parent
```

### 9.1. Vì sao `outer` và `inner` có bộ đếm riêng?

Mỗi lần gọi `inFlow` tạo một **FlowAspect mới**. Sau `CREATE outer`, `outer` được `push` vào stack. Khi `inFlow("inner")` chạy, instance `inner` được push lên trên `outer`. `current()` lấy phần tử trên đỉnh, nên điểm `business:B` ghi vào bộ đếm inner.

Khi inner kết thúc, `finally` pop instance inner. Lời gọi `business:C` sau đó lại dùng outer, tiếp tục từ `#2` lên `#3`. Đây là cơ chế **khôi phục activation cha** thay vì làm mất context cha.

### 9.2. Vì sao nhánh lỗi vẫn kết thúc flow?

Ở `inFlow("failed")`, `operation.call()` ném `IllegalArgumentException`. Khối `finally` vẫn ghi `exit`, pop instance và in `END failed`, rồi ngoại lệ tiếp tục được truyền ra ngoài tới `catch` trong `main`.

`NO_SCOPE after` chứng minh không còn instance đang hoạt động trên thread chính sau lỗi. Nếu quên pop khi throw, một lần gọi độc lập có thể vô tình nhìn thấy instance cũ.

### 9.3. Vì sao worker thread in `NO_SCOPE`?

`ExecutorService` chạy lambda trên thread khác. `ThreadLocal` của parent thread **không tự truyền** sang thread trong executor. Bởi vậy `business("worker")` không thấy `FlowAspect parent` và in `NO_SCOPE worker`. `future.get()` bảo đảm dòng worker xuất hiện trước `after-task` trong output đã cho.

Đây là **mô phỏng bằng ThreadLocal**, không phải phát biểu mọi hình thức dynamic cflow qua async đều giống hệt. Một công nghệ AOP hoặc tracing có propagation hỗ trợ tác vụ bất đồng bộ có thể đưa ra hợp đồng riêng. Không thể mặc định một định nghĩa per-flow sẽ sống qua ranh giới thread chỉ vì thao tác đã được khởi chạy bên trong root.

### 9.4. Vì sao dùng `ACTIVE.remove()`?

Khi scope cuối của thread kết thúc, ví dụ gọi `ACTIVE.remove()` để bỏ liên kết ThreadLocal tới stack. Đây là một thực hành quan trọng với thread pool sống lâu: giữ những đối tượng per-request trong ThreadLocal sau khi xử lý xong có thể giữ tham chiếu thừa hoặc làm lẫn dữ liệu vào yêu cầu tiếp theo.

Nếu outer còn hoạt động khi inner kết thúc, không được remove toàn bộ ThreadLocal; chỉ pop inner để giữ parent.

### 9.5. Giới hạn của ví dụ

- `inFlow` được gọi **tường minh**, không được weaver tự chèn.
- `business()` đóng vai trò một join point quan sát thủ công.
- `FlowAspect` chỉ giữ một bộ đếm nhỏ; không mô phỏng tất cả precedence hoặc khả năng dispatch advice của mọi ngôn ngữ AOP.
- Chương trình **không an toàn để chia sẻ một `FlowAspect` mutable giữa nhiều thread** nếu không thêm quy tắc đồng thời; ví dụ cố ý không truyền nó sang worker.
- `Callable<T>` được dùng để cho phép nhánh return hoặc throw có thể kiểm chứng.
- `ThreadLocal` không tự cung cấp tracing xuyên tiến trình và không tự đồng nhất với request scope.
- `ExecutorService` được dùng trong một chương trình hữu hạn; `shutdown()` giúp kết thúc executor khi thao tác đã hoàn tất.
- Ví dụ dùng các nhãn không chứa dữ liệu nhạy cảm; thực tế phải kiểm soát log và thời hạn lưu thông tin theo chính sách.

## 10. Lồng flow với proxy và thứ tự interceptor

Nếu hệ AOP dựa vào interceptor quanh phương thức root, vị trí của interceptor tạo flow quyết định phạm vi nó bao quanh.

Giả sử:

```text
FlowScope(Retry(Target))
```

FlowScope được mở **một lần** cho một logical request bên ngoài Retry. Nếu Retry gọi `proceed` hai lần, cả hai attempt có thể dùng **cùng một scope**, miễn đường gọi tiếp tục ở phần bên trong FlowScope và mô hình instantiation hoạt động như vậy.

Ngược lại:

```text
Retry(FlowScope(Target))
```

Mỗi attempt đi vào FlowScope có thể tạo **một instance riêng**, nếu continuation thực sự chạy lại phần đuôi. Điều này ảnh hưởng bộ đếm và tài nguyên.

### 10.1. Không có precedence đúng cho mọi trường hợp

Đặt authorization bên ngoài cache có thể giúp kiểm tra quyền trước cache hit; đặt scope đo thời gian bên ngoài retry có thể đo cả chuỗi; đặt một scope transaction trong retry có thể tạo transaction mới theo mỗi attempt. Nhưng thứ tự đúng phụ thuộc **hợp đồng nghiệp vụ** và khả năng thực tế của cơ chế.

Đừng quyết định lifespan aspect chỉ vì “thứ tự khai báo file A trước file B”. Phải xác minh precedence/registration và test đúng đường.

### 10.2. Bắt đầu flow ở method call hay method execution?

Nếu root được chọn tại **method call** của người gọi, phạm vi có thể gắn với vị trí phát sinh lời gọi. Nếu root ở **method execution**, phạm vi gắn với thân phương thức được chạy. Một proxy phương thức thường chỉ thấy lời gọi đi qua nó, nên khác bộ weaver có thể chọn method-call join point trong bytecode.

Cần nêu rõ root là loại join point nào. Tên phương thức giống nhau chưa chứng minh root activation giống nhau.

## 11. Phạm vi thread, bất đồng bộ và propagation

Phạm vi dynamic call stack đồng bộ thường có ranh giới dễ xác định: bước vào root, gọi các hàm con, rồi rời root. Công việc bất đồng bộ làm mô hình phức tạp hơn:

```text
Thread A:  handle() -> schedule(task) -> return
Thread B:                               task.run()
```

Tại thời điểm `task.run()` chạy, `handle()` trên thread A có thể đã kết thúc. Không có quan hệ **ngăn xếp lời gọi đồng bộ** từ `handle()` trên A sang B.

### 11.1. Truyền context thủ công không phải tự động có per-flow semantics

Một chương trình có thể **capture** trace ID hoặc token context rồi chuyển sang tác vụ async. Tuy nhiên:

- Nếu capture **toàn bộ instance aspect mutable**, hai thread có thể cập nhật cùng bộ đếm gây race condition.
- Nếu flow cha kết thúc rồi tài nguyên bị đóng, worker dùng instance cũ có thể truy cập tài nguyên đã đóng.
- Nếu worker là thread pool, cần khôi phục context trước đó và dọn đúng lúc để tránh lẫn yêu cầu.
- Nếu task bị hủy, thất bại hoặc chạy muộn, chính sách dọn dẹp không thể chỉ dựa vào `finally` của hàm lập lịch.
- Nếu propagation chỉ truyền **mã tương quan bất biến**, có thể cần một scope aspect riêng ở thread worker, với quan hệ cha/con được mô tả tường minh.

Một công cụ hỗ trợ async-aware control-flow có thể có ngữ nghĩa khác. Cần xem hợp đồng thay vì suy từ cách AOP đồng bộ hoạt động.

### 11.2. Không tự đồng nhất cflow với HTTP request

Một HTTP request có thể gồm nhiều callback bất đồng bộ và thread. Một thread có thể phục vụ nhiều request lần lượt. Một cuộc gọi root có thể xảy ra từ command-line, batch job hoặc test.

Nếu yêu cầu thực sự là “mỗi logical request có một state”, nên dùng **request/context propagation** phù hợp; per-control-flow chỉ giải quyết đúng khi ranh giới của nó trùng yêu cầu và công nghệ có khả năng duy trì scope cần thiết.

### 11.3. Virtual thread và cấu trúc tác vụ

Java có thể dùng các mô hình thực thi khác nhau, gồm thread platform và virtual thread ở các phiên bản phù hợp. Việc một context được cất theo thread không biến nó thành context theo logical request, nhất là khi tác vụ phân nhánh hoặc chuyển sang một thread khác.

Dù sử dụng loại thread nào, hãy xác định **ai sở hữu instance, ai truyền context và khi nào dọn**. Không dựa vào số lượng thread hoặc cơ chế pooling để suy ra số instance per-flow.

## 12. Tài nguyên, vòng đời object và giới hạn “kết thúc”

### 12.1. Kết thúc activation không phải thu hồi bộ nhớ tức thì

Khi root thoát, instance không còn là instance active trong luồng điều khiển. Nếu không còn tham chiếu nào khác, object có thể được thu gom rác về sau. Nhưng **garbage collection không có nghĩa chạy đúng lúc để giải phóng file/khóa/kết nối**.

Nếu aspect sở hữu tài nguyên, phải có cơ chế `close`/`finally` hoặc hợp đồng quản lý lifecycle tương ứng.

### 12.2. Scope theo flow chưa chắc là transaction

Bắt đầu/kết thúc instance theo flow không tự mở hoặc commit transaction. Nếu aspect quản lý giao dịch, còn phải xác định rollback, lỗi sau commit, retry, tài nguyên ngoài cơ sở dữ liệu và các hành vi async.

Ném ngoại lệ từ một join point bên trong flow cũng không chứng minh **mọi hiệu ứng trước đó đã rollback**. Không ghi log “đã hoàn tác” chỉ vì flow scope kết thúc.

### 12.3. Những trường hợp không bảo đảm cleanup

Trong Java, `finally` có thể chạy trên return hoặc throw thông thường sau khi vào phạm vi, nhưng không bảo đảm chạy nếu JVM bị kết thúc cưỡng bức, mất điện, hoặc chương trình không bao giờ rời vùng ấy.

Với tác vụ dùng `Future`, lời gọi tạo future có thể return trong khi công việc còn chạy. Dọn instance theo phương thức tạo future **không tương đương** dọn sau completion của future.

## 13. Hiệu năng và chi phí của theo dõi control flow

Kiểm tra `cflow` ở các join point được gọi rất nhiều lần có thể phát sinh chi phí duy trì trạng thái hoặc kiểm tra bối cảnh. Một chính sách per-flow còn phải tạo, gắn và dỡ instance ở những lượt root tương ứng.

Các khoản chi phí có thể là:

- Đánh dấu điểm vào/ra của flow;
- Theo dõi depth hoặc stack activation;
- Truy cập state theo thread/context;
- Khởi tạo object và quản lý lifetime;
- Kiểm tra điều kiện động tại join point;
- Thực thi advice body: logging, network call, serialization, ghi metric.

Không thể kết luận `percflow` luôn chậm hơn một mô hình khác mà không đo công cụ và workload cụ thể. Hành vi của advice, tần suất join point và khả năng tối ưu của weaver có thể chi phối lớn hơn bản thân việc theo dõi flow.

### 13.1. Tránh tạo instance không cần thiết

Nếu chỉ cần đo tổng thời gian của một phương thức, biến thời gian cục bộ trong around advice có thể đã đủ. Per-flow aspect có ích hơn khi **nhiều điểm nằm trong cùng luồng cần chia sẻ một state có vòng đời riêng**.

Nếu chỉ dùng `cflow` như điều kiện lọc và không cần state per-flow, đừng tạo instance mới chỉ để đạt cùng hiệu ứng lọc.

### 13.2. Đừng log mọi điểm chỉ để chứng minh lifetime

Một pointcut quá rộng có thể làm tăng overhead và rò thông tin. Nên chọn **join point thật sự cần** cùng dữ kiện tối thiểu, và dùng test riêng để xác minh scope, thay vì ghi toàn bộ arguments/results của mọi phương thức.

## 14. Ma trận kiểm thử lifecycle theo flow

| Kịch bản | Mong đợi |
| --- | --- |
| Join point ngoài root | Không có per-flow instance hoạt động cho chính sách đó |
| Lần vào root thứ nhất | Tạo hoặc kích hoạt instance F1 |
| Hai join point cùng root | Có thể chia sẻ F1 nếu đúng ngữ nghĩa công cụ |
| Lần vào root thứ hai sau khi F1 kết thúc | Instance mới F2, không giữ bộ đếm F1 |
| Root lồng nhau | Quy tắc instance riêng/khôi phục outer rõ ràng |
| Đệ quy | Số lần activation đúng theo điều kiện root |
| Root trả về bình thường | Dỡ instance khỏi scope |
| Root ném ngoại lệ | Dỡ instance và giữ ngoại lệ gốc |
| Root bị chặn bởi advice ngoài | Xác định flow có thực sự được vào không |
| Retry bao ngoài hoặc bên trong flow scope | Đếm instance/attempt đúng theo thứ tự |
| Hai thread đồng thời | Không lẫn dữ liệu scope |
| Thread pool tái sử dụng | Không để lại context từ yêu cầu trước |
| Task async được lịch từ flow | Không tự suy có cùng instance trên thread khác |
| Kết quả `null` hoặc `void` | Không nhầm normal return với exception |
| Pointcut `cflow` trên singleton | Không tự coi là per-flow instance |
| Lời gọi bypass proxy/weaving | Phát hiện điểm không được can thiệp |
| Lỗi cleanup | Không âm thầm che lỗi nghiệp vụ trái hợp đồng |

### 14.1. Kiểm thử danh tính instance, không chỉ số log

Một log “dao.load executed” có thể xuất hiện đúng khi dùng `cflow` nhưng chưa chứng minh đã có instance riêng cho từng root. Để kiểm tra **per-flow lifecycle**, cần xác minh:

1. Trong cùng flow, những điểm yêu cầu chia sẻ state thấy cùng instance/bộ đếm.
2. Giữa hai flow tách biệt, state được tách riêng.
3. Với flow lồng nhau, quy tắc chọn instance phù hợp được thực thi.
4. Sau return/throw, instance cũ không “rò” vào lời gọi tiếp theo.
5. Khi có concurrency, trạng thái không bị ghi đè bởi flow khác.

### 14.2. Chẩn đoán thiếu hoặc thừa instance

Nếu mỗi lần `dao.load()` lại có instance mới dù nằm trong một `handle`, có thể đang dùng chính sách **per-join-point** tự tạo thay vì per-root. Nếu mọi `handle` cùng ghi vào một bộ đếm, có thể aspect là singleton hoặc dữ liệu nằm trong field static.

Nếu scope chỉ hoạt động ở một số đường, kiểm tra root pointcut, loại join point, điều kiện động, phạm vi weaving/proxy và đường async. **Sửa pointcut và sửa instantiation policy là hai loại sửa khác nhau.**

## 15. Lỗi phổ biến và cách tránh

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi `cflow` là lệnh tạo aspect instance | Vẫn có state chung, bộ đếm lẫn nhau | Phân biệt filtering với instantiation |
| Coi per-flow đồng nghĩa per-thread | Dữ liệu từ nhiều root trong cùng thread bị lẫn | Gắn với lần vào/ra root, hỗ trợ nesting |
| Dùng một biến `currentAspect` global | Flow đồng thời và nested ghi đè | Dùng context/stack theo đúng phạm vi |
| Không pop khi ném lỗi | Thread sau dùng nhầm instance cũ | Cleanup trong finally sau activation thành công |
| Pop sai khi inner kết thúc | Mất context của outer | Kiểm tra thứ tự LIFO/ownership |
| Giữ instance mutable qua async không đồng bộ | Race condition hoặc dùng tài nguyên đã đóng | Truyền dữ liệu phù hợp và quản lý lifecycle riêng |
| Tin ThreadLocal tự truyền sang executor | Không có context ở worker | Propagation tường minh nếu hợp đồng yêu cầu |
| Dùng `cflowbelow` khi cần tính cả root | Bỏ sót điểm gốc | Xác nhận điều kiện biên của pointcut |
| Không tính recursion/nested root | Số instance sai | Test activation theo từng depth |
| Đóng tài nguyên ở cuối hàm tạo future | Công việc async còn sử dụng tài nguyên | Dọn theo completion thật |
| Coi object GC như dọn tài nguyên đúng lúc | Rò file/kết nối/khóa | Close/finally theo ownership |
| Cho rằng proxy chặn mọi join point | Không thấy lời gọi trực tiếp hoặc field access | Kiểm chứng model/proxy/weaving |
| Log mọi đối số vì cần cflow debug | Chi phí cao, lộ dữ liệu | Chỉ thu trường cần thiết, áp quyền truy cập |
| Dùng per-flow cho dữ liệu toàn cục không cần tách | Tăng chi phí và phức tạp | Chọn lifetime đơn giản đủ đáp ứng |
| Không xét thứ tự Retry và FlowScope | State per-request/per-attempt bị nhầm | Test precedence và số lần proceed |

## 16. Bài tập vận dụng có đáp án

### Bài 1 — Lọc theo cflow hay tạo state riêng?

Một aspect dùng chung có pointcut chọn `dao.load` trong `cflow(handle)` và field `int count`. Hai lần gọi `handle` có chắc sử dụng hai bộ đếm riêng không?

**Đáp án:** Không. `cflow` chỉ quyết định nơi áp dụng điều kiện. Nếu field nằm trong một singleton aspect, hai lần handle có thể cùng cập nhật một field. Muốn bộ đếm độc lập, cần per-flow instantiation hoặc state theo flow được quản lý rõ.

### Bài 2 — Nested root

Luồng F1 gọi bên trong một root mới tạo F2. F2 kết thúc; F1 còn chạy. Cách quản lý context đúng là gì?

**Đáp án:** Nếu mô hình dùng ngăn xếp, push F2 khi vào inner, pop F2 khi thoát rồi khôi phục F1 trên đỉnh. Không đặt current về null khi F1 vẫn đang hoạt động.

### Bài 3 — Ngoại lệ

Root mở flow F1 rồi target ném `IllegalArgumentException`. Chỉ dọn flow ở after-returning có đúng không?

**Đáp án:** Không. Nhánh exception không chạy after-returning. Scope phải được dỡ trên các đường thoát tương ứng, thường dùng hành vi finally/after-always hoặc cơ chế tương đương nếu công nghệ hỗ trợ; giữ ngoại lệ gốc.

### Bài 4 — Thread pool

Root chạy trên thread A và submit một task sang executor thread B. Instance per-flow có chắc hiện diện trên B không?

**Đáp án:** Không thể mặc định. Dynamic call stack đồng bộ của A không tự trở thành call stack của B. Cần cơ chế propagation hỗ trợ hoặc một scope mới theo nhiệm vụ và phải quản lý cleanup/concurrency.

### Bài 5 — Retry

Với `FlowScope(Retry(Target))` và `Retry(FlowScope(Target))`, mỗi cấu trúc có thể tạo bao nhiêu instance khi có hai attempts?

**Đáp án:** Trong mô hình continuation cho phép chạy lại phần đuôi, cấu trúc đầu thường mở một flow ngoài Retry; cấu trúc sau có thể mở một flow cho mỗi attempt. Kết quả chính xác phải kiểm tra loại join point và ngữ nghĩa công cụ.

### Bài 6 — Lấy state theo đối tượng hay flow?

Cùng một `OrderService` instance xử lý hai lời gọi `handle(A)` và `handle(B)` tách biệt. Nếu muốn state không dùng chung giữa A và B, nên mặc định per-target hay per-flow?

**Đáp án:** Per-target có thể chia sẻ state vì target giống nhau. Per-flow phù hợp hơn khi A và B là hai root activation độc lập trong mô hình được hỗ trợ. Nếu yêu cầu là logical request xuyên async, cần thiết kế propagation vượt ra ngoài call stack đơn thuần.

### Bài 7 — Gọi bên ngoài root

`dao.load()` được gọi trực tiếp từ `main` mà không qua `handle()`. Advice được ràng buộc theo per-flow của `handle` có chắc chạy không?

**Đáp án:** Không. Nếu không có một activation `handle` phù hợp, không có instance per-flow đang hoạt động theo chính sách đó. Còn một aspect singleton có pointcut khác có thể vẫn quan sát lời gọi; phải phân biệt định nghĩa và scope.

### Bài 8 — Thời điểm object biến mất

Khi flow F1 kết thúc, JVM có phải gọi destructor và hủy object aspect ngay lập tức không?

**Đáp án:** Không. Kết thúc activation là dỡ liên kết logic khỏi flow; garbage collection xảy ra theo chính sách JVM nếu object không còn reachable. Tài nguyên ngoài bộ nhớ phải được đóng theo lifecycle riêng.

### Bài 9 — Cflowbelow

Bạn chỉ muốn áp advice cho các điểm **bên trong** root chứ không áp lên chính root. Điều kiện `cflow` và `cflowbelow` có thể khác ra sao?

**Đáp án:** Trong những mô hình có hai điều kiện ấy, `cflowbelow` thường loại chính điểm root và chọn những điểm ở bên dưới; `cflow` thường bao gồm root. Cần xem ngữ nghĩa và loại join point của công nghệ cụ thể.

### Bài 10 — Chứng minh per-flow

Một test chỉ kiểm tra “mỗi lần load có log” có đủ chứng minh per-flow instance đúng không?

**Đáp án:** Không. Cần kiểm tra nhận dạng/state giữa các điểm trong cùng root, sự tách biệt giữa hai root, nested/recursion, return/throw cleanup và hành vi khi thread được tái sử dụng.

## 17. Ghi nhớ

- **Dynamic control flow** là quan hệ lời gọi đang thực sự diễn ra, không phải chỉ vị trí package hoặc một đối tượng cụ thể.
- **`cflow`/`cflowbelow`** là điều kiện chọn điểm theo luồng; **`percflow`** nếu được hỗ trợ là **chính sách tạo instance aspect gắn với mỗi flow**.
- Per-flow instance có **lifetime logic theo activation**; nó không đồng nghĩa singleton, per-target, per-thread vĩnh viễn hay request scope xuyên async.
- Lời gọi lồng nhau hoặc đệ quy đòi cơ chế **khôi phục activation cha**, thường dễ hình dung qua stack.
- Khi root thoát qua **return hoặc throw**, liên kết scope phải được dỡ đúng đường; việc cleanup và thu hồi tài nguyên ngoài bộ nhớ là trách nhiệm riêng.
- **Thread/async boundary** có thể ngắt call flow đồng bộ; context không tự truyền, và chia sẻ instance mutable giữa thread cần an toàn đồng thời.
- **Thứ tự aspect/proxy và số lần proceed** quyết định một scope có bao toàn bộ logical request hay được mở cho từng attempt.
- Để kiểm chứng per-flow lifecycle, phải đo **instance/state theo từng root**, không chỉ việc log advice có xuất hiện hay không.
