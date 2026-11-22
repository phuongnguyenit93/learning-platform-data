# So sánh AOP với hàm dùng chung, đối tượng cộng tác và thiết kế theo thành phần

## 1. Vấn đề thiết kế: một mối quan tâm xuất hiện ở nhiều nơi

Trong một hệ thống, mã nghiệp vụ trả lời câu hỏi **chương trình làm gì**: tạo đơn hàng, tính giá, ghi nhận thanh toán, cập nhật trạng thái. Bên cạnh đó còn các mối quan tâm như ghi nhật ký, đo thời gian, kiểm toán, kiểm soát truy cập hoặc chuẩn hóa cách xử lý lỗi. Khi cùng một quy tắc xuất hiện ở nhiều đường thực thi, ta gọi đó là **mối quan tâm xuyên cắt** (*cross-cutting concern*).

Giả sử có ba thao tác tạo đơn hàng, hủy đơn hàng và tra cứu đơn hàng. Cả ba cần ghi lại thời điểm bắt đầu/kết thúc, nhưng mỗi thao tác vẫn có quy tắc nghiệp vụ riêng. Có ít nhất bốn cách tổ chức:

1. Gọi **hàm dùng chung** tại các vị trí cần ghi nhận.
2. Cho đối tượng nghiệp vụ làm việc với **đối tượng cộng tác** có trách nhiệm ghi nhận.
3. Ghép các **thành phần** thực hiện nghiệp vụ và các lớp bao ngoài theo thứ tự rõ ràng.
4. Khai báo quy tắc **AOP** chọn những điểm thực thi thích hợp rồi gắn hành vi ghi nhận tại đó.

Bốn cách này đều có thể loại bỏ việc sao chép *thân hàm* ghi nhật ký. Khác biệt chính là **ai quyết định lúc nào hành vi được thực thi, sự phụ thuộc được biểu diễn ở đâu, và có thể kiểm tra luồng điều khiển bằng cách nào**.

Hai biểu hiện cần phân biệt:

- **Scattering (phân tán):** cùng một quy tắc xuất hiện rải rác ở nhiều lớp hoặc phương thức; sửa quy tắc phải chạm nhiều nơi.
- **Tangling (đan xen):** một phương thức trộn nhiều trách nhiệm, khiến phần nghiệp vụ khó đọc và khó kiểm thử.

Tách thành hàm dùng chung có thể giải quyết sự lặp của thuật toán ghi nhật ký nhưng vẫn để lại các lời gọi rải rác. AOP có thể tập trung cả quy tắc lẫn điểm áp dụng, nhưng đổi lại tạo thêm một tầng điều khiển cần được quản lý rõ ràng.

## 2. Hàm dùng chung: tái sử dụng thuật toán, lời gọi vẫn tường minh

**Cách hoạt động.** Đặt thao tác lặp lại vào một hàm tiện ích hoặc một hàm bậc cao nhận hành động cần chạy. Mã gọi tự quyết định khi nào gọi hàm.

~~~java
static <T> T trace(java.util.function.Supplier<T> action) {
    System.out.println("start");
    try {
        return action.get();
    } finally {
        System.out.println("end");
    }
}

// Ví dụ bên trong một phương thức khác:
String result = trace(() -> orderService.place("A"));
~~~

Đây là **đoạn minh họa**, chưa phải chương trình độc lập. Từ khóa **finally** khiến dòng kết thúc được in ngay cả khi hành động ném ngoại lệ; nó không tự chuyển ngoại lệ thành thành công.

**Ưu điểm:**

- Quan hệ nguyên nhân–kết quả hiện ngay tại vị trí gọi; IDE có thể lần theo hàm một cách trực tiếp.
- Dễ hiểu với Java thuần, không cần cơ chế dệt mã hay bộ chọn điểm thực thi.
- Rất phù hợp cho thao tác nhỏ, chỉ vài nơi dùng, hoặc trường hợp mỗi lời gọi cần lựa chọn tham số riêng.
- Hàm bậc cao có thể bảo toàn giá trị trả về và ngoại lệ, nếu phần bao ngoài được viết cẩn thận.

**Giới hạn:**

- Người lập trình có thể quên gọi hàm tại một đường đi mới.
- Nếu quy tắc phải bao quanh toàn bộ thao tác thì chỉ gọi một hàm ghi log ở đầu không đủ; cần tự tổ chức khối try/finally.
- Thay đổi phạm vi áp dụng thường buộc sửa nhiều điểm gọi.
- Mã nghiệp vụ vẫn nhìn thấy kiến thức về concern, dù thân hàm thực sự đã được tái sử dụng.

**Nên chọn khi:** phạm vi nhỏ, lời gọi có ý nghĩa nghiệp vụ tại đúng vị trí đó, hoặc việc thể hiện hành động rõ ràng trong mã quan trọng hơn khả năng áp dụng hàng loạt.

## 3. Đối tượng cộng tác: tách trách nhiệm và khai báo phụ thuộc

**Cách hoạt động.** Thay vì đưa hành vi dùng chung vào chính lớp nghiệp vụ, truyền vào một đối tượng có giao diện rõ ràng: **Audit**, **Metrics**, **Clock**, **AccessPolicy**... Đối tượng nghiệp vụ gọi cộng tác viên khi có sự kiện cần xử lý.

~~~java
interface Audit {
    void record(String event);
}

final class Checkout {
    private final Audit audit;

    Checkout(Audit audit) {
        this.audit = audit;
    }

    void complete(String orderId) {
        // Kiểm tra điều kiện và hoàn tất đơn hàng...
        audit.record("order-completed:" + orderId);
    }
}
~~~

Đây là **đoạn minh họa**. Một triển khai Audit có thể ghi ra màn hình, lưu vào kho kiểm toán hoặc làm đối tượng giả trong bài kiểm thử.

Đặc điểm quan trọng là lớp **Checkout** biểu đạt một **sự kiện nghiệp vụ có ý nghĩa**: đơn đã hoàn tất. Sự kiện này khác với yêu cầu kỹ thuật “ghi dấu mỗi khi bất kỳ phương thức nào được gọi”. Không nên tự động chuyển tất cả sự kiện nghiệp vụ sang AOP, vì lúc phát sinh sự kiện thường là một quyết định thuộc mô hình nghiệp vụ.

**Ưu điểm:**

- Có hợp đồng rõ ràng; có thể thay triển khai bằng đối tượng giả, đối tượng ghi nhớ sự kiện hoặc bộ gửi thông điệp.
- Dễ kiểm thử điều kiện phát sinh sự kiện, thứ tự lời gọi và dữ liệu được truyền.
- Quan hệ phụ thuộc hiện ra trong constructor; áp dụng nguyên tắc đảo ngược phụ thuộc.
- Xử lý được tình huống cần dữ liệu miền cụ thể, chẳng hạn lý do hủy đơn hoặc loại phê duyệt.

**Giới hạn:**

- Nơi cần concern vẫn phải khai báo cộng tác viên và gọi nó đúng lúc.
- Nếu mọi phương thức trong hàng trăm lớp đều có cùng lời gọi kỹ thuật, việc thêm cộng tác viên vào từng lớp có thể thành mã lặp.
- Giao diện quá rộng hoặc “một đối tượng làm mọi tiện ích” sẽ biến thành điểm phụ thuộc khó bảo trì.
- Đối tượng cộng tác chỉ tạo khả năng tái sử dụng trách nhiệm; nó không tự động chặn mọi phương thức phù hợp.

**Nên chọn khi:** concern cần được nghiệp vụ chủ động kích hoạt, cần truyền dữ liệu ngữ nghĩa của miền, hoặc hợp đồng cộng tác là một phần quan trọng trong thiết kế.

## 4. Thiết kế theo thành phần: lắp ghép hành vi bằng cấu trúc tường minh

**Cách hoạt động.** Mỗi thành phần thực hiện một trách nhiệm; hệ thống tạo luồng làm việc bằng cách lắp chúng lại. Ví dụ dùng mẫu **Decorator**: nhiều đối tượng cùng thực hiện giao diện **OrderService**, mỗi lớp bao ngoài ủy quyền cho thành phần bên trong.

~~~text
Caller
  → MetricOrderService
      → AuditedOrderService
          → CoreOrderService
~~~

Thành phần đo đạc có thể chạy trước/sau khi ủy quyền. Thành phần kiểm toán ghi sự kiện; thành phần lõi tạo đơn. Đây là **composition**: quan hệ lắp ghép có thể quan sát được từ mã khởi tạo hoặc cấu hình.

Không nên đồng nhất *thiết kế theo thành phần* với riêng Decorator. Thiết kế này còn bao gồm việc phân tách các module, sử dụng interface, thành phần dịch vụ, pipeline hoặc middleware, và lắp ghép hàm. Decorator chỉ là một ví dụ dễ thấy về cách bổ sung hành vi quanh một lời gọi.

**Ưu điểm:**

- Danh sách và thứ tự thành phần thường xác định rõ tại điểm lắp ghép.
- Có thể tạo nhiều biến thể pipeline mà không sửa lõi: có đo đạc, không đo đạc, có kiểm toán...
- Mỗi lớp bao ngoài là đơn vị kiểm thử độc lập; cấu hình thành phần có thể được kiểm tra.
- Không cần điểm cắt ẩn hoặc cơ chế weaving; phù hợp với các ranh giới dịch vụ, giao diện hoặc pipeline.

**Giới hạn:**

- Mọi đường gọi phải đi qua chuỗi thành phần đã lắp; truy cập trực tiếp đối tượng lõi sẽ bỏ qua các lớp bao ngoài.
- Cần thiết kế ranh giới, giao diện và nơi lắp ghép đủ ổn định.
- Tổ hợp nhiều wrapper có thể phức tạp; thứ tự wrapper làm thay đổi hành vi.
- Không tự động chạm đến mọi thao tác bên trong thành phần (ví dụ truy cập trường dữ liệu, thao tác nội bộ) chỉ vì nó tồn tại.

**Nên chọn khi:** luồng xử lý có các bước rõ ràng, hành vi thêm vào có tính thành phần, hoặc cần cấu hình linh hoạt mà vẫn giữ đường đi của lời gọi tương đối dễ nhìn.

## 5. AOP: tập trung quy tắc *và* điều kiện áp dụng

**Aspect-Oriented Programming (AOP)** là cách mô-đun hóa mối quan tâm xuyên cắt bằng việc mô tả **hành vi bổ sung** cùng với **tập điểm thực thi** nơi hành vi đó có hiệu lực. AOP thường được sử dụng bên cạnh thiết kế hướng đối tượng và composition, chứ không thay thế yêu cầu chia nhỏ đối tượng, xác định trách nhiệm hay xây dựng giao diện.

Các thuật ngữ nền tảng:

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Join point** | Một điểm trong quá trình thực thi mà cơ chế AOP có thể nhận diện và tác động; tập điểm được hỗ trợ tùy công cụ, chẳng hạn thực thi phương thức, lời gọi phương thức hoặc truy cập trường. |
| **Pointcut** | Biểu thức/quy tắc chọn một tập join point theo tên, chữ ký, annotation, ngữ cảnh hoặc điều kiện được cơ chế hỗ trợ. |
| **Advice** | Mã chạy trước, sau, khi trả về thành công, khi có ngoại lệ, hoặc bao quanh join point. |
| **Aspect** | Đơn vị gói concern gồm pointcut và advice, có thể kèm trạng thái/cấu hình. |
| **Target** | Đối tượng hoặc phần mã mang hành vi gốc được chọn. |
| **Weaving (dệt)** | Quá trình gắn hoặc kết hợp hành vi aspect vào đường thực thi của chương trình. |

**Luồng khái niệm:**

~~~text
Lời gọi đến hành vi gốc
     ↓
Có khớp pointcut không?
     ├─ Không → Chạy hành vi gốc
     └─ Có  → Chạy advice thích hợp
                  ↓
              Chạy/bao quanh hành vi gốc
                  ↓
              Xử lý kết quả hoặc ngoại lệ
~~~

*Không phải mọi advice đều chạy theo một trình tự cố định.* Advice **before** chạy trước join point; **after-returning** liên quan tới hoàn tất bình thường; **after-throwing** liên quan tới hoàn tất bằng ngoại lệ; **after/finally** là hành vi kết thúc trong những mô hình hỗ trợ; **around** có quyền điều phối việc thực hiện hành vi gốc. Một advice **around** có thể quyết định không tiếp tục, tiếp tục một lần hoặc (nếu mô hình hỗ trợ) nhiều lần; thay đổi số lần gọi có thể thay đổi ngữ nghĩa nghiêm trọng.

Ví dụ **giả mã độc lập công cụ**, không phải cú pháp Java có thể biên dịch:

~~~text
aspect ExecutionTrace
    pointcut selectedOperations =
        execution(method in applicationService with @Observed)

    before selectedOperations:
        recordStart()

    afterFinally selectedOperations:
        recordEnd()
end
~~~

Ví dụ thể hiện sự khác biệt: lớp nghiệp vụ không cần trực tiếp gọi **recordStart** và **recordEnd**. Tập phương thức áp dụng được khai báo bằng pointcut. Cú pháp pointcut và khả năng chọn annotation/field/constructor phụ thuộc vào công cụ AOP cụ thể.

### 5.1. Weaving xảy ra ở đâu?

- **Compile-time weaving:** công cụ tích hợp hành vi aspect khi biên dịch nguồn thành bytecode hoặc mã thực thi.
- **Post-compile/binary weaving:** biến đổi mã đã biên dịch ở một bước sau biên dịch.
- **Load-time weaving:** chèn/biến đổi hành vi khi lớp được tải vào môi trường thực thi.
- **Runtime interception:** đối tượng đại diện, bộ chặn lời gọi hoặc cơ chế tương đương điều phối lời gọi khi chạy.

Đây là các họ kỹ thuật, không phải những khả năng chắc chắn luôn cùng có trong một công cụ. Đặc biệt, **proxy chỉ bắt được những lời gọi thực sự đi qua proxy**. Một hệ thống dệt mã ở cấp bytecode có thể quan sát những loại join point khác, tùy khả năng của bộ dệt. Bởi vậy không thể suy luận rằng “đã viết pointcut thì mọi lời gọi liên quan đều bị bắt” nếu chưa biết cơ chế áp dụng cụ thể.

### 5.2. Tính xuyên cắt khác sự tái sử dụng hàm ở điểm nào?

Giả sử chính sách thay đổi từ “ghi nhận hai phương thức” sang “ghi nhận mọi thao tác có đánh dấu @Observed”:

- **Hàm dùng chung:** phải bảo đảm mỗi lời gọi thích hợp đều bao quanh thao tác bằng hàm.
- **Đối tượng cộng tác:** phải thêm/kiểm tra việc phát sự kiện từ từng nơi.
- **Composition:** phải cấu hình mọi đường đi cần thiết qua component/wrapper tương ứng.
- **AOP:** có thể cập nhật pointcut hoặc gắn annotation tại biên thích hợp; việc áp dụng sẽ do cơ chế AOP thực hiện tại các join point thực sự được hỗ trợ.

AOP vì vậy đặc biệt có giá trị khi **một chính sách kỹ thuật thống nhất cắt ngang nhiều thành phần** và ranh giới áp dụng có thể diễn đạt ổn định. Nếu ranh giới mơ hồ hoặc pointcut phụ thuộc tên hàm rất dễ đổi, lợi ích có thể giảm mạnh.

## 6. Cùng một nghiệp vụ, bốn cách triển khai bằng Java 17

Ví dụ sau chạy được bằng Java 17 trở lên. Nó minh họa hàm dùng chung, đối tượng cộng tác, composition qua Decorator và cơ chế chặn lời gọi bằng **JDK dynamic proxy**. Proxy ở phần cuối là ví dụ cụ thể về *một cơ chế interception*, **không đồng nghĩa với toàn bộ khả năng AOP** (không có ngôn ngữ pointcut tổng quát và không tự dệt mọi join point).

Tạo file **CompareApproaches.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.function.Supplier;

public class CompareApproaches {
    interface OrderService {
        String place(String id);
    }

    static class CoreOrderService implements OrderService {
        public String place(String id) {
            return "created:" + id;
        }
    }

    static class TraceFunctions {
        static <T> T around(Supplier<T> action) {
            System.out.println("[trace] start");
            try {
                return action.get();
            } finally {
                System.out.println("[trace] end");
            }
        }
    }

    interface Audit {
        void record(String event);
    }

    static class ConsoleAudit implements Audit {
        public void record(String event) {
            System.out.println("[audit] " + event);
        }
    }

    static class AuditedOrderService implements OrderService {
        private final OrderService next;
        private final Audit audit;

        AuditedOrderService(OrderService next, Audit audit) {
            this.next = next;
            this.audit = audit;
        }

        public String place(String id) {
            audit.record("place:" + id);
            return next.place(id);
        }
    }

    static class MetricOrderService implements OrderService {
        private final OrderService next;

        MetricOrderService(OrderService next) {
            this.next = next;
        }

        public String place(String id) {
            System.out.println("[metric] begin");
            try {
                return next.place(id);
            } finally {
                System.out.println("[metric] end");
            }
        }
    }

    public static void main(String[] args) {
        OrderService core = new CoreOrderService();

        String a = TraceFunctions.around(() -> core.place("A"));
        System.out.println(a);

        OrderService collaborator =
                new AuditedOrderService(core, new ConsoleAudit());
        System.out.println(collaborator.place("B"));

        OrderService components = new MetricOrderService(
                new AuditedOrderService(core, new ConsoleAudit()));
        System.out.println(components.place("C"));

        OrderService observed = (OrderService) Proxy.newProxyInstance(
                OrderService.class.getClassLoader(),
                new Class<?>[]{OrderService.class},
                (proxy, method, actualArgs) -> {
                    System.out.println("[crosscut] before " + method.getName());
                    try {
                        return method.invoke(core, actualArgs);
                    } catch (InvocationTargetException error) {
                        throw error.getCause();
                    } finally {
                        System.out.println("[crosscut] after " + method.getName());
                    }
                });
        System.out.println(observed.place("D"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 CompareApproaches.java
java CompareApproaches
~~~

Kết quả chuẩn:

~~~text
[trace] start
[trace] end
created:A
[audit] place:B
created:B
[metric] begin
[audit] place:C
[metric] end
created:C
[crosscut] before place
[crosscut] after place
created:D
~~~

**Đọc kết quả theo từng đoạn:**

1. **A:** nơi gọi chọn hàm **TraceFunctions.around** và truyền hành động vào. Lõi không ghi log, nhưng điểm dùng hàm vẫn do caller quyết định.
2. **B:** **AuditedOrderService** có cộng tác viên **Audit** được truyền vào constructor; bản thân wrapper gọi cộng tác viên khi thao tác bắt đầu. Trong ứng dụng thực, cộng tác viên có thể được đặt trực tiếp ở lớp nghiệp vụ nếu đó là một sự kiện miền.
3. **C:** hai thành phần được ghép: **MetricOrderService → AuditedOrderService → CoreOrderService**. Thứ tự bao ngoài quyết định thứ tự log.
4. **D:** cuộc gọi đến **observed.place** đi qua JDK proxy, nên bộ chặn chạy trước/sau lời gọi đến **core.place**. Nếu gọi thẳng **core.place**, bộ chặn của proxy này không chạy. JDK dynamic proxy ở đây làm việc qua interface **OrderService**.

Ví dụ là thí nghiệm phân biệt **nơi đặt chính sách**, không phải bài đo hiệu năng. Những dòng ghi nhận đơn giản ở đây không đại diện cho cách triển khai kiểm toán, đo thời gian hoặc bảo mật thực tế.

## 7. Bảng đối chiếu các đặc tính thiết kế

| Tiêu chí | Hàm dùng chung | Đối tượng cộng tác | Composition / component | AOP |
|---|---|---|---|---|
| **Nơi khai báo hành vi** | Hàm, helper, wrapper function | Interface và đối tượng triển khai | Thành phần độc lập/wrapper | Aspect/advice |
| **Nơi xác định phạm vi áp dụng** | Từng lời gọi | Nơi đối tượng chủ động gọi cộng tác viên | Đường lắp ghép/cấu hình pipeline | Pointcut + các join point được hỗ trợ |
| **Sự hiện diện tại mã nghiệp vụ** | Lời gọi rõ ràng | Phụ thuộc và lời gọi rõ ràng | Có thể ẩn khỏi lõi, hiện tại lắp ghép | Thường không có lời gọi trực tiếp trong lõi |
| **Mức tự động áp dụng** | Thấp; cần gọi | Thấp đến trung bình; tùy cấu trúc | Theo tuyến đường đi qua component | Cao trong phạm vi pointcut/weaving |
| **Đổi chính sách chung** | Đổi thân hàm dễ, đổi tập nơi gọi khó hơn | Đổi implementation dễ, đổi nơi phát sự kiện có thể tốn công | Đổi/reorder wrapper ở nơi lắp ghép | Đổi advice/pointcut tập trung, nhưng phải kiểm tra ảnh hưởng |
| **Khả năng lần theo luồng** | Trực tiếp | Trực tiếp qua interface | Qua chuỗi component | Cần cả mã gốc, cấu hình và pointcut |
| **Kiểm thử đơn vị** | Hàm và caller | Cộng tác viên giả, tương tác | Từng component + chuỗi tích hợp | Aspect riêng + kiểm thử weaving/interception thực |
| **Nguy cơ quên áp dụng** | Quên gọi tại điểm mới | Quên phát sự kiện | Đường đi tắt bỏ wrapper | Pointcut không khớp, lớp không được weave, lời gọi bỏ qua proxy |
| **Điểm mạnh điển hình** | Tái sử dụng đơn giản | Hợp đồng miền và testability | Cấu trúc linh hoạt, rõ thứ tự | Chính sách xuyên nhiều điểm thực thi |
| **Rủi ro đặc trưng** | Lặp lời gọi; tangling | Phụ thuộc lan rộng | Chuỗi wrapper phức tạp | Phụ thuộc ngầm; pointcut quá rộng; thứ tự advice |

Các ô trong bảng là khuynh hướng thường gặp, không phải định luật. Chẳng hạn composition vẫn có thể khó lần theo khi cấu hình quá động; AOP vẫn có thể rất rõ nếu pointcut, phạm vi và hiệu ứng được đặt tên và kiểm thử tốt.

## 8. Tình huống nào nên chọn cách nào?

### Tình huống A — Chuẩn hóa một phép tính dùng ở nhiều nơi

Nhiều màn hình cùng cần chuẩn hóa mã đơn hàng hoặc tính quy tắc làm tròn. Chọn **hàm dùng chung** (hoặc đối tượng chuyên trách phép tính nếu có trạng thái/phụ thuộc). Đây là **thuật toán tái sử dụng**, chưa chắc là concern xuyên cắt ở cấp thực thi; đặt nó vào advice sẽ làm mờ nơi phép tính được gọi và có thể đổi ngữ nghĩa.

### Tình huống B — Hoàn tất giao dịch phải phát sự kiện nghiệp vụ

Khi đơn hàng chuyển từ **đang xử lý** sang **hoàn tất**, nghiệp vụ phải phát sự kiện chứa mã đơn, người duyệt, thời điểm và lý do. Chọn **đối tượng cộng tác**, hoặc thành phần phát sự kiện có giao diện rõ ràng. Sự kiện gắn với **chuyển trạng thái có ý nghĩa** chứ không chỉ với tên phương thức. Một advice “sau khi phương thức kết thúc” không đủ chứng minh trạng thái đã cam kết thành công; nếu phương thức trả về nhưng công việc khác vẫn có thể thất bại thì điểm gắn advice chưa đúng.

### Tình huống C — Dịch vụ cần pipeline kiểm tra, chuyển đổi, đo đạc

Có một cửa vào ổn định, các bước có thể sắp theo thứ tự và bật/tắt tùy cấu hình. Chọn **composition** với Decorator/middleware/pipeline. Kiểm thử sự khác nhau giữa các thứ tự là trực quan: đặt bước kiểm soát truy cập trước hoặc sau bước cache có thể tạo ra ý nghĩa khác nhau.

### Tình huống D — Theo dõi hàng trăm thao tác ở các module

Muốn đo khoảng thời gian thực thi của mọi thao tác được đánh dấu; chính sách ghi nhận không làm thay đổi quyết định nghiệp vụ. Nếu môi trường hỗ trợ join point phù hợp, **AOP** có thể giảm scattering. Điểm cắt nên dựa trên một hợp đồng ổn định, ví dụ annotation khai báo mục đích, hoặc một nhóm API được định nghĩa rõ. Cần kiểm thử rằng thao tác mới thực sự khớp và có advice chạy.

### Tình huống E — Kiểm soát quyền truy cập hoặc giao dịch có ảnh hưởng đúng/sai

Có thể dùng một cơ chế chặn tại biên làm lớp thực thi chính sách nhất quán. Tuy nhiên vẫn phải xác định chính xác **ranh giới tin cậy**, đường đi không được chặn, ngoại lệ, gọi bất đồng bộ và hành vi khi thất bại. Quy tắc cho phép thao tác cụ thể, tính hợp lệ dữ liệu và các bất biến miền thường cần hiện diện tại nơi sở hữu chúng. Một pointcut đặt tên theo lớp không tự tạo ra bảo đảm bảo mật.

## 9. Những khác biệt sâu hơn khi dự án phát triển

### 9.1. Mức liên kết: phụ thuộc tường minh và phụ thuộc ngầm

Với cộng tác viên, constructor cho thấy lớp phụ thuộc vào **Audit**. Với composition, điểm lắp ghép cho thấy lớp đo đạc bao lớp nghiệp vụ. Với AOP, phụ thuộc ngược lại có thể tồn tại ở **cấu hình thực thi**, dù mã lõi không gọi aspect.

Điều đó làm giảm coupling trong *mã nguồn của lõi*, nhưng không xóa sự phụ thuộc vào thứ tự, tên phương thức, annotation, loader hoặc cơ chế weaving. Hãy mô tả đó là **dịch chuyển nơi khai báo coupling**: từ lời gọi trực tiếp sang hợp đồng áp dụng aspect.

### 9.2. Mức bao phủ: chặn ở biên so với điểm thực thi nội bộ

Ví dụ một phương thức gọi phương thức khác trên chính đối tượng:

~~~java
void outer() {
    inner();
}

void inner() {
    // Công việc cần theo dõi
}
~~~

Nếu hệ thống chỉ chặn cuộc gọi **qua một proxy bên ngoài**, lời gọi nội bộ **inner()** có thể không đi qua proxy nên không kích hoạt bộ chặn của inner. Một cơ chế weaving khác có thể quan sát thực thi của inner, nhưng điều đó phải được xác minh theo loại join point mà nó hỗ trợ. Tương tự, phương thức private, static, final, constructor hay truy cập trường có thể được hỗ trợ khác nhau ở từng cơ chế.

**Bài học:** đừng thiết kế chính sách theo giả định rằng có AOP thì tất cả đường đi đều bị chặn. Xác định cụ thể **join point được hỗ trợ, đối tượng thực nhận cuộc gọi, phạm vi lớp được biến đổi và cơ chế áp dụng**.

### 9.3. Thứ tự chồng nhiều hành vi

Giả sử có hai concern: đo thời gian và retry. Nếu đo thời gian bao ngoài retry, kết quả có thể bao gồm toàn bộ các lần thử. Nếu retry bao ngoài đo thời gian, mỗi lần thử có thể được ghi riêng. Cùng một cặp hành vi nhưng thứ tự bao có thể cho ra dữ liệu khác nhau.

~~~text
Timer(Retry(Core))  → một khoảng thời gian của cả chuỗi thử lại
Retry(Timer(Core))  → một khoảng thời gian cho từng lần thử
~~~

Điều này đúng khi các wrapper/advice có hành vi tương đương với sơ đồ trên; kết quả thực tế phụ thuộc cách chúng được triển khai và điều phối. Đối với AOP, khi nhiều aspect chọn cùng join point, phải định nghĩa và kiểm tra precedence theo cơ chế đang dùng. Không nên dựa vào thứ tự ngẫu nhiên.

### 9.4. Kết quả, ngoại lệ và tính nguyên tử

Một đoạn **after** chạy không có nghĩa thao tác đã thành công. Phân biệt ít nhất ba hoàn cảnh:

- Hoàn tất bình thường và trả kết quả.
- Ném ngoại lệ.
- Đã trả về tại biên quan sát nhưng công việc bất đồng bộ vẫn tiếp tục.

Một thao tác đo đạc thường nên dùng **finally** để đóng span. Kiểm toán thành công có thể chỉ được ghi khi kết quả nghiệp vụ đã xác nhận. Advice bao quanh cũng cần truyền đúng ngoại lệ gốc và kết quả về caller, tránh nuốt lỗi hoặc vô tình đổi kiểu lỗi.

Nếu advice tự mở giao dịch, rollback, retry hoặc gửi thông điệp, điều đó đã tác động đến tính đúng đắn chứ không chỉ tính quan sát. Hãy định nghĩa rõ thời điểm cam kết, khả năng lặp lại, idempotency và điều kiện thất bại. Những yêu cầu này không tự được bảo đảm bởi cú pháp AOP.

### 9.5. Chi phí hiệu năng và khả năng chẩn đoán

Mỗi cách có chi phí khác nhau: gọi hàm trực tiếp, gọi qua interface, chuỗi wrapper, bộ chặn phản xạ hoặc mã đã được weave. Chi phí phụ thuộc cơ chế, tối ưu JVM, số lớp advice, lượng I/O của logging, tần suất gọi và cấu hình thực tế. Không có cơ sở kết luận mặc định rằng “AOP luôn chậm” hoặc “AOP không có chi phí”.

Mốc thực tế: một lời ghi log ra mạng/ổ đĩa thường mang ý nghĩa hiệu năng khác nhiều so với một lần gọi hàm; chỉ phép đo với workload phù hợp mới trả lời được. Khi chẩn đoán, phải nhớ rằng stack trace và trình gỡ lỗi có thể hiển thị proxy, bộ chặn hoặc mã được weave, khiến đường đi khác với những gì nhìn thấy trong lớp nghiệp vụ.

### 9.6. Tính minh bạch dữ liệu và ranh giới an toàn

Aspect quan sát tham số và giá trị trả về có thể vô tình ghi mật khẩu, token, thông tin nhận dạng hoặc dữ liệu nhạy cảm. Chọn loại dữ liệu được phép thu thập và cách che/mã hóa theo chính sách thực tế. Nếu advice có trạng thái chia sẻ, phải xét concurrency, reentrancy, lưu context theo luồng và việc chuyển context qua tác vụ bất đồng bộ.

Không nên giả định dữ liệu gắn với một luồng sẽ theo sang một luồng khác. Với xử lý bất đồng bộ, bước quan sát quanh thao tác tạo tác vụ có thể kết thúc trước khi công việc thực sự hoàn thành; điểm theo dõi phải phù hợp với vòng đời của tác vụ.

## 10. Cách kết hợp các phương pháp mà không chồng trách nhiệm

Các phương pháp không loại trừ lẫn nhau. Một kiến trúc có thể phân vai:

~~~text
Application boundary
   → Aspect quan sát thời gian/tracing tại những join point được hỗ trợ
   → Component điều phối yêu cầu
       → Domain service
           → Collaborator Audit: ghi sự kiện miền có ý nghĩa
           → Shared functions: chuẩn hóa dữ liệu và tính toán thuần
       → Decorator/pipeline: cache hoặc biến đổi có cấu hình
~~~

Ví dụ trách nhiệm:

- **Hàm thuần:** kiểm tra định dạng, tính thuế, chuyển đổi dữ liệu nhất quán.
- **Cộng tác viên:** gửi thông báo “đơn được duyệt”, tra cứu chính sách được mô hình miền chủ động yêu cầu.
- **Thành phần:** ghép đường xử lý thành các bước có thứ tự, cache, adapter hoặc middleware.
- **Aspect:** đo thời gian ở những biên ổn định, thống kê lời gọi, log kỹ thuật có chính sách chung.

Nếu vừa có wrapper đo thời gian vừa có aspect đo cùng một sự kiện, rất dễ **đếm kép**. Mỗi concern nên có nơi sở hữu, danh sách biên áp dụng và tên metric/log thống nhất. Khi phối hợp, kiểm thử end-to-end cần xác nhận chính xác **một lần** ghi nhận trên mỗi biến cố mong muốn.

## 11. Thiết kế pointcut có khả năng bảo trì

Một pointcut rộng kiểu “tất cả phương thức trong toàn bộ ứng dụng” có thể vô tình áp dụng cho đường đi nhạy cảm về hiệu năng hoặc cho API không nên bị quan sát. Ngược lại, pointcut dựa trên mẫu tên dễ bỏ sót các lớp được đổi tên.

Nên làm rõ:

1. **Ý định:** đang chọn theo ranh giới kiến trúc, metadata đánh dấu hay chữ ký kỹ thuật?
2. **Phạm vi:** chọn những loại join point nào; có ngoại lệ cần loại trừ không?
3. **Tính ổn định:** khi đổi tên/refactor, tập join point phải thay đổi theo yêu cầu nào?
4. **Quan hệ giữa aspects:** precedence, các advice chồng nhau và hành vi khi có lỗi.
5. **Kiểm chứng:** có bài kiểm thử chứng minh join point mong muốn được áp dụng, join point ngoài phạm vi không bị áp dụng không?

Một annotation đánh dấu chủ ý có thể rõ hơn quy tắc tên trong nhiều trường hợp, nhưng bản thân annotation không mang tính “ma thuật”: phải có cơ chế AOP đọc nó và áp dụng advice, đồng thời không để cùng một annotation gánh nhiều chính sách không liên quan.

## 12. Kiểm thử: phải xác minh cả chức năng gốc lẫn cơ chế áp dụng

| Loại kiểm thử | Điều cần chứng minh |
|---|---|
| **Hàm dùng chung** | Giá trị trả về, ngoại lệ, tác dụng phụ và số lần gọi hành động. |
| **Cộng tác viên** | Khi nào được gọi/không gọi, tham số đúng, phản ứng với lỗi cộng tác. |
| **Composition** | Các lớp nhận đúng ủy quyền; thứ tự của pipeline; đường đi ngoài pipeline có được chặn như yêu cầu không. |
| **AOP unit-level** | Logic advice và bộ chọn theo biểu thức được mô hình hỗ trợ; hành vi trên kết quả/ngoại lệ. |
| **AOP integration-level** | Weaving/interception thực xảy ra với lớp và lời gọi đã định; không áp dụng nhầm; cùng nhiều aspect có thứ tự đúng. |

Với AOP, gọi thẳng phương thức xử lý trong aspect rồi thấy nó đúng **chưa đủ**. Bài kiểm thử tích hợp phải đi qua đường thực thi thực tế mà chương trình sử dụng, để phát hiện lỗi không được weave, không đi qua proxy, pointcut không khớp, hoặc advice chạy hai lần. Ngược lại, test nghiệp vụ lõi nên xác nhận nghiệp vụ đúng ngay cả khi hệ thống quan sát được thay bằng giả lập phù hợp.

Cần thêm các ca đối chứng: lời gọi thành công, ném ngoại lệ, lời gọi lồng nhau, hai aspect cùng khớp, đổi tên phương thức, xử lý bất đồng bộ và đường đi trực tiếp bỏ qua interceptor (nếu cơ chế có giới hạn đó).

## 13. Những ngộ nhận và lỗi thiết kế thường gặp

**“AOP chỉ là một cách viết hàm tiện ích.”** Sai ở cấp mô hình: hàm tiện ích cần nơi gọi tường minh; AOP có pointcut và weaving/interception để áp dụng hành vi ở những join point phù hợp.

**“Tách concern sang cộng tác viên là đã giải quyết hoàn toàn xuyên cắt.”** Mới tách phần thực hiện hành vi; lời gọi và quy tắc chọn nơi gọi có thể vẫn rải rác.

**“Dùng AOP thì không cần kiến trúc thành phần.”** AOP không quyết định ranh giới miền, trách nhiệm đối tượng, hợp đồng API hoặc cấu trúc module. Hệ thống có aspect vẫn cần thiết kế cơ sở tốt.

**“Aspect đảm bảo không thể bị bỏ qua.”** Sai nếu điểm cắt không khớp, vùng weaving thiếu, lời gọi đi tắt qua đối tượng gốc hoặc loại join point không được hỗ trợ.

**“Logging sau khi hàm chạy nghĩa là giao dịch đã hoàn tất.”** Không luôn đúng; kết thúc phương thức, hoàn tất bất đồng bộ và cam kết nghiệp vụ có thể ở các thời điểm khác nhau.

**“Advice là chỗ phù hợp để đặt mọi quy tắc nghiệp vụ.”** Nếu chính sách cần hiểu bất biến miền, điều kiện chuyển trạng thái hoặc dữ liệu sự kiện nghiệp vụ, việc giấu nó trong pointcut có thể làm hệ thống khó giải thích và khó kiểm chứng.

**“Cứ càng nhiều aspect càng ít mã.”** Các aspect chồng nhau tạo thêm chi phí đọc, debug, xác định thứ tự, hiệu năng và bảo trì. Mục tiêu là phân định trách nhiệm rõ ràng, không tối đa hóa số lượng aspect.

## 14. Câu hỏi quyết định trước khi chọn giải pháp

Hãy trả lời lần lượt:

1. **Đây là thuật toán dùng lại, sự kiện nghiệp vụ, một bước trong pipeline hay một chính sách xuyên cắt?** Câu trả lời xác định nơi khai báo tự nhiên của hành vi.
2. **Hành vi cần xuất hiện ở từng nơi gọi cụ thể hay ở mọi join point thuộc một tập đã biết?** Từng nơi gọi phù hợp với hàm/cộng tác viên; tập rộng, ổn định là ứng viên cho AOP.
3. **Ai sở hữu thời điểm áp dụng?** Nghiệp vụ sở hữu chuyển trạng thái; composition sở hữu pipeline; pointcut sở hữu phạm vi quan sát kỹ thuật.
4. **Có thể chứng minh bao phủ và thứ tự không?** Nếu không thể xác minh đường gọi, weaving và precedence, việc ẩn hành vi sau aspect có thể gây rủi ro.
5. **Thất bại của concern có làm thất bại nghiệp vụ không?** Nếu có, phải xác định hợp đồng ngoại lệ, retry, tính nguyên tử và trạng thái.
6. **Người bảo trì sẽ tìm nguyên nhân ở đâu?** Đảm bảo tài liệu, công cụ debug và test thể hiện được điểm áp dụng thực tế.

**Quy tắc thực hành:** bắt đầu từ ranh giới trách nhiệm rõ ràng. Dùng hàm cho phép tính tái sử dụng, cộng tác viên cho hành vi được nghiệp vụ chủ động gọi, composition cho các bước lắp ghép, và AOP cho chính sách xuyên cắt có tập điểm áp dụng rõ ràng, cơ chế hỗ trợ xác định và phép kiểm thử bao phủ. Khi phối hợp nhiều cách, ghi rõ nơi sở hữu mỗi concern.

## 15. Tự kiểm tra khả năng vận dụng

**Bài 1.** Năm thao tác đều gọi chung một thuật toán chuẩn hóa mã. Có nên tạo pointcut chỉ để chạy thuật toán này không? Giải thích nơi thuật toán được gọi và việc ai lựa chọn thời điểm áp dụng.

**Bài 2.** Dịch vụ vừa được bọc trong Decorator đo thời gian vừa nằm trong pointcut đo thời gian. Sự cố nào có thể xảy ra với metric, và sửa bằng cách xác định quyền sở hữu concern ra sao?

**Bài 3.** Một advice ghi thành công khi phương thức trả về, nhưng phương thức đó chỉ tạo tác vụ chạy nền. “Trả về thành công” đã đủ chứng minh tác vụ thành công chưa? Cần đổi điểm quan sát sang đâu?

**Bài 4.** Trong ví dụ Java 17, thay **observed.place("D")** bằng **core.place("D")** thì hai dòng crosscut có xuất hiện không? Giải thích dựa trên đường đi qua proxy.

**Gợi ý đáp án:** (1) thường dùng hàm/cộng tác viên vì đó là phép tính có lời gọi mang ý nghĩa rõ ràng; (2) metric có thể đếm hai lần, cần một biên đo thống nhất; (3) chưa, cần quan sát thời điểm hoàn tất thật của tác vụ; (4) không, vì cuộc gọi đã bỏ qua đối tượng đại diện.

---

**Kết luận về nguyên lý:** AOP khác biệt bởi khả năng mô tả một chính sách và **tập join point** cần áp dụng nó; hàm dùng chung tập trung thuật toán, đối tượng cộng tác tập trung trách nhiệm, còn composition tập trung cấu trúc lắp ghép. Giá trị của AOP nằm ở việc giảm những lời gọi kỹ thuật rải rác tại các biên được định nghĩa rõ. Sự đánh đổi là phải chủ động quản lý sự phụ thuộc ngầm, phạm vi pointcut, thứ tự advice và việc kiểm chứng interception/weaving.