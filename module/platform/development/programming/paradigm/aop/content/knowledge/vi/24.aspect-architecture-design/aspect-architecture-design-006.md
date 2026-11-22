# Biên giới mô-đun và khả năng hiểu hành vi từ mã nguồn khi dùng AOP

## 1. Vấn đề kiến trúc: mã nguồn của phương thức chưa phản ánh toàn bộ hành vi lúc chạy

Trong lập trình hướng khía cạnh (*Aspect-Oriented Programming — AOP*), một phương thức có thể trông rất đơn giản khi đọc mã nguồn nhưng hành vi thực tế còn chịu ảnh hưởng của các advice được gắn vào những join point tương ứng. Ví dụ phương thức xử lý thanh toán chỉ chứa thuật toán nghiệp vụ, trong khi khi gọi qua điểm chặn AOP, hệ thống có thể kiểm tra quyền, tạo trace, đo thời gian, kiểm soát retry hoặc ghi audit.

Cách tổ chức này có lợi: nhiều chức năng dùng chung cơ chế đo đạc và kiểm soát mà không cần sao chép mã. Nhưng nó đồng thời đặt ra hai câu hỏi kiến trúc:

1. **Biên giới mô-đun nằm ở đâu?** Mô-đun nào sở hữu hợp đồng nghiệp vụ, mô-đun nào sở hữu cơ chế AOP, và phần nào được phép biết chi tiết của mô-đun khác?
2. **Có thể hiểu hành vi từ mã nguồn đến mức nào?** Khi đọc một phương thức, người bảo trì phải tìm thêm pointcut, advice, cấu hình weaving/interception, thứ tự áp dụng và đường gọi thực tế nào để biết điều gì sẽ xảy ra?

Một ứng dụng có AOP tốt cần giữ được cả hai: tách trách nhiệm xuyên suốt và giúp người đọc truy tìm được **luồng thực thi có hiệu lực** (*effective execution path*).

## 2. Các khái niệm nền tảng và cách chúng liên quan tới mô-đun

- **Mô-đun kiến trúc:** đơn vị đóng gói một trách nhiệm, có giao diện công khai, các phần triển khai nội bộ và quy tắc phụ thuộc. Nó có thể là package, thư viện, thành phần triển khai độc lập hoặc module của Java Platform Module System (JPMS), tùy kiến trúc.
- **Join point:** vị trí AOP có thể can thiệp, ví dụ lúc phương thức được gọi hoặc thực thi. Các cơ chế AOP khác nhau hỗ trợ những loại join point khác nhau.
- **Pointcut:** biểu thức/quy tắc chọn tập join point chịu chính sách.
- **Advice:** hành vi được thực hiện trước, sau hoặc bao quanh join point; với around advice, phần logic có thể quyết định có chuyển tiếp vào thao tác gốc không.
- **Aspect:** tập hợp pointcut và advice mô tả một mối quan tâm xuyên suốt.
- **Weaving/interception:** cơ chế kết nối advice vào những join point phù hợp, có thể qua proxy, công cụ sửa bytecode lúc build/load hoặc cơ chế khác.

**Mô-đun và aspect không phải cùng một trục phân chia.** Một mô-đun nghiệp vụ có thể sở hữu chức năng đặt hàng. Một mô-đun observability sở hữu logic trace dùng chung nhiều mô-đun; một mô-đun chính sách truy cập có thể áp dụng các kiểm tra xuyên suốt. Tuy nhiên, việc aspect áp dụng ở nhiều nơi không làm nó trở thành chủ sở hữu của toàn bộ quy tắc nghiệp vụ các nơi đó.

### Biên giới cần bảo vệ

| Biên giới | Nên chứa | Không nên tự động kéo sang |
| --- | --- | --- |
| API/hợp đồng mô-đun nghiệp vụ | Kiểu tham số, giá trị trả về, lỗi có chủ đích, ý nghĩa thao tác | Chi tiết đo lường/collector nội bộ |
| Triển khai nội bộ | Thuật toán, bất biến nghiệp vụ, truy cập dữ liệu | Điểm mở công khai chỉ để pointcut nhận diện |
| Mô-đun chính sách AOP | Advice, pointcut, cơ chế ghi metric/trace hoặc kiểm tra chung | Quy tắc domain chưa được xác nhận và dữ liệu riêng tư của mọi mô-đun |
| Thành phần lắp ghép (*composition root*) | Đăng ký aspect, cấu hình scope/thứ tự, lắp các cổng gọi | Logic nghiệp vụ phân tán không kiểm soát |
| Kiểm thử/quan sát | Bằng chứng cho đường gọi trực tiếp và đường qua advice | Giả định rằng chỉ đọc code thân phương thức đã là đủ |

Biên giới mô-đun chính là hợp đồng về điều gì được công khai, điều gì được che giấu và bên nào phải chịu trách nhiệm nếu một hành vi thay đổi.

## 3. Khác biệt giữa luồng gọi nhìn thấy và luồng gọi thực tế

Giả sử đọc được:

~~~java
public String charge(int amount) {
    return ledger.recordCharge(amount);
}
~~~

Đoạn này chỉ cho biết hành vi **trong thân phương thức**, không đủ kết luận về lời gọi khi có AOP. Nếu composition root lắp một advice kiểm tra quyền bên trong một advice tracing, đường chạy có thể là:

~~~text
caller
  |
  v
Tracing advice: enter
  |
  v
Authorization advice: check permission
  |                           |
  | allow                     | deny
  v                           v
Charge method                 throw SecurityException
  |                           |
  v                           |
Authorization advice: return  |
  |                           |
  +------------+--------------+
               v
Tracing advice: success/error
               |
               v
caller receives result/exception
~~~

Nếu thứ tự lắp ngược lại, từ chối quyền có thể diễn ra **trước khi tracing bắt đầu**. Cả hai cách đều có thể hợp lý trong những hợp đồng khác nhau, nhưng người đọc không thể suy ra chỉ từ thân charge().

Một cách diễn đạt thực tế:

> Hành vi quan sát được phụ thuộc vào thân phương thức, các advice thực sự được áp dụng, thứ tự của chúng, cơ chế interception, cấu hình triển khai và đường gọi.

Không có nghĩa mọi hệ thống cần mô tả từng bước runtime bằng tài liệu dài. Cần đủ thông tin để người đọc **lần ra đúng nơi phát sinh hành vi** và kiểm chứng giả thuyết bằng kiểm thử.

## 4. Những nguyên tắc để AOP không phá vỡ biên giới mô-đun

### 4.1. Phụ thuộc vào hợp đồng ổn định, không bám vào chi tiết nội bộ

Pointcut dựa vào tên lớp nội bộ, thứ tự package hoặc phương thức private cụ thể có thể bị ảnh hưởng khi mô-đun refactor. Nếu chính sách thật sự áp dụng cho mọi lời gọi qua một cổng nghiệp vụ, ưu tiên biểu diễn ranh giới công khai và quy tắc chọn có thể kiểm thử.

Chẳng hạn “đo mọi lần gọi qua cổng PaymentOperations” mô tả ranh giới rõ hơn “đo tất cả phương thức có tên chứa process thuộc một package bất kỳ”. Nhưng lựa chọn cụ thể còn tùy cơ chế weaving: với dynamic proxy dựa trên interface, chỉ các lời gọi đi qua proxy mới được chặn.

### 4.2. Mô-đun nghiệp vụ giữ bất biến nghiệp vụ

Kiểm tra số dư, hạn mức, trạng thái đơn hàng, quyền trên đúng tài nguyên, phát sinh sự kiện domain và tính nhất quán transaction thuộc hợp đồng nghiệp vụ. Một aspect kiểm tra quyền tổng quát có thể được tái sử dụng, nhưng aspect không nên tự suy diễn rằng “thao tác thành công tức đã thanh toán” nếu hợp đồng nghiệp vụ chưa xác nhận.

Tương tự, một advice ghi audit truy cập khác với cơ chế tạo sự kiện nghiệp vụ đáng tin: hai loại bản ghi có vòng đời và điều kiện phát sinh khác nhau.

### 4.3. Mô-đun AOP cung cấp cơ chế có giới hạn

Một aspect tốt có nhiệm vụ xác định: nó nhận dữ liệu gì, chạy khi nào, có thể chặn hay thay đổi kết quả không, và lỗi trong aspect được xử lý thế nào. Các trách nhiệm thường thích hợp để dùng chung là:

- Trace và correlation ID tại ranh giới đã chọn.
- Đo duration/số lần gọi và trạng thái kỹ thuật.
- Kiểm tra permission tổng quát theo policy rõ ràng.
- Cơ chế timeout/retry cho thao tác thật sự an toàn khi lặp, đã có hợp đồng.
- Cache cho các thao tác có kết quả tái sử dụng theo khóa và ngữ cảnh đúng.

Nếu cùng một aspect vừa đo thời gian, quyết định giao dịch, cấp quyền cho từng đối tượng và sửa payload nghiệp vụ thì biên giới trách nhiệm đã quá mờ. Khi một chính sách có tác động nghiệp vụ, phải xác định người sở hữu và cách kiểm thử riêng.

### 4.4. Composition root cho thấy cách các mô-đun kết hợp

Thành phần lắp ghép là nơi dễ đọc nhất để biết mô-đun nào được gắn advice nào, cấu hình thứ tự và điều kiện kích hoạt. Có thể dùng khai báo cấu hình, explicit decorators hoặc đăng ký weaving tùy nền tảng.

Nguyên tắc hữu ích là các quyết định ở composition root phải **có thể tìm kiếm, đối chiếu và kiểm thử**. Không làm người bảo trì phải suy từ những quy tắc ngầm không được kiểm soát qua hàng chục module.

## 5. Ví dụ Java 17: tách phần nghiệp vụ khỏi hai lớp advice

Ví dụ dùng Java dynamic proxy để minh họa interception ở một ranh giới interface. Nó chạy bằng JDK chuẩn, không cần thư viện AOP bên ngoài. Thành phần nghiệp vụ chỉ ghi nhận khoản phí giả định; một proxy kiểm tra quyền, một proxy khác ghi trace kỹ thuật. Composition root thể hiện rõ thứ tự áp dụng.

Mặc dù đặt trong một tệp để dễ chạy, các kiểu trong ví dụ đại diện cho những phần có thể tách sang các mô-đun khác nhau.

Tạo tệp **ModularAopDemo.java**:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

public class ModularAopDemo {
    record RequestContext(String subject, Set<String> permissions) {
        RequestContext {
            Objects.requireNonNull(subject);
            permissions = Set.copyOf(permissions);
        }
    }

    interface PaymentOperations {
        String charge(RequestContext context, int amount);
    }

    // Trách nhiệm nghiệp vụ: xử lý một lần charge hợp lệ.
    static final class PaymentCore implements PaymentOperations {
        final AtomicInteger charges = new AtomicInteger();

        @Override
        public String charge(RequestContext context, int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            charges.incrementAndGet();
            System.out.println("core:charge");
            return "receipt-" + amount;
        }
    }

    static Object invokeTarget(
            Object target, Method method, Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static PaymentOperations proxy(InvocationHandler handler) {
        return (PaymentOperations) Proxy.newProxyInstance(
                PaymentOperations.class.getClassLoader(),
                new Class<?>[] { PaymentOperations.class },
                handler
        );
    }

    // Advice kiểm soát permission tổng quát.
    static PaymentOperations authorize(PaymentOperations target) {
        return proxy((instance, method, args) -> {
            RequestContext context = (RequestContext) args[0];
            if (context == null
                    || !context.permissions().contains("CHARGE")) {
                throw new SecurityException("forbidden");
            }
            return invokeTarget(target, method, args);
        });
    }

    // Advice quan sát kỹ thuật, không ra quyết định nghiệp vụ.
    static PaymentOperations trace(PaymentOperations target) {
        return proxy((instance, method, args) -> {
            System.out.println("trace:start");
            try {
                Object result = invokeTarget(target, method, args);
                System.out.println("trace:success");
                return result;
            } catch (Throwable failure) {
                System.out.println(
                        "trace:error=" + failure.getClass().getSimpleName());
                throw failure;
            }
        });
    }

    public static void main(String[] args) {
        PaymentCore core = new PaymentCore();

        // Composition root: tracing bao ngoài kiểm tra quyền.
        PaymentOperations secured = authorize(core);
        PaymentOperations exposed = trace(secured);

        RequestContext allowed = new RequestContext(
                "alice", Set.of("CHARGE"));
        RequestContext denied = new RequestContext(
                "bob", Set.of());

        System.out.println(
                "allowed=" + exposed.charge(allowed, 100));

        try {
            exposed.charge(denied, 200);
        } catch (SecurityException ex) {
            System.out.println("denied=" + ex.getMessage());
        }

        System.out.println("coreCalls=" + core.charges.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ModularAopDemo.java
java ModularAopDemo
~~~

**Stdout theo đúng thứ tự:**

~~~text
trace:start
core:charge
trace:success
allowed=receipt-100
trace:start
trace:error=SecurityException
denied=forbidden
coreCalls=1
~~~

Giải thích:

1. Lời gọi hợp lệ đi qua trace, sau đó authorize, rồi mới tới PaymentCore. Phương thức gốc được gọi đúng một lần và tạo ra receipt-100.
2. Lời gọi không có quyền vẫn đi qua trace bên ngoài, nhưng bị authorize từ chối. PaymentCore không thực thi cho yêu cầu này.
3. Do tracing bọc bên ngoài authorization, hệ thống ghi được cả lần bị từ chối. Nếu đổi thành authorize(trace(core)), lần bị từ chối không đi qua trace. Đây là **khác biệt hành vi do thứ tự lắp advice**, dù mã của PaymentCore không đổi.
4. Nếu một thành phần khác giữ tham chiếu trực tiếp đến core và gọi core.charge(...), cả hai proxy đều bị bỏ qua. Composition root phải chỉ phát hành đúng cổng đã được bảo vệ ra ngoài ranh giới tin cậy.

**Giới hạn minh họa:** RequestContext được truyền như tham số để tái hiện được các tình huống. Trong hệ thống thật, subject và permissions phải đến từ danh tính đã xác thực và nguồn phân quyền tin cậy, không do người gọi tự khai. PaymentCore không xử lý thanh toán thật, transaction, idempotency hay bảo vệ tài nguyên cụ thể. Cơ chế dùng ở đây là dynamic proxy cho interface; phạm vi join point của cơ chế weaving khác có thể rộng hoặc khác hoàn toàn.

### Những điều mã nguồn cho thấy và không cho thấy

Đọc riêng PaymentCore cho biết nghiệp vụ thuần, điều kiện amount > 0 và sự tăng bộ đếm charge. Muốn biết yêu cầu không có quyền bị từ chối hay có trace hay không, phải đọc **authorize()**, **trace()** và **main()**. Muốn biết một đường gọi có đi qua advice thật không, cần xem đối tượng nào được truyền cho caller và kiểm thử đường gọi ấy.

Cách làm này minh họa yêu cầu về khả năng hiểu hành vi: nhà phát triển có thể lần từ cổng công khai tới composition root, qua chuỗi advice rồi đến triển khai lõi; không cần suy đoán ở các điểm ẩn.

## 6. AOP có thể tạo phụ thuộc kiến trúc ẩn như thế nào?

### 6.1. Pointcut quá rộng

Giả sử một quy tắc chọn mọi phương thức có tiền tố save trong toàn bộ ứng dụng. Khi một mô-đun khác thêm saveDraft() với ý nghĩa mới, advice có thể tự động tác động vào phương thức ấy mà người viết không biết. Nếu advice chỉ ghi metric nhẹ, tác động có thể là overhead và nhiễu số liệu. Nếu advice thực hiện retry, ghi audit bắt buộc hoặc chặn quyền, hậu quả còn lớn hơn.

Thay đổi cấu trúc package, tên phương thức hoặc phạm vi public cũng có thể vô tình làm pointcut ngừng khớp. Cần xác định **phạm vi dự định** và có kiểm thử xác nhận tập join point được chọn.

### 6.2. Aspect đọc cấu trúc nội bộ của nhiều mô-đun

Một advice dùng reflection để truy cập trường private, suy đoán ID người dùng từ vị trí tham số hoặc gọi trực tiếp repository nội bộ sẽ phụ thuộc vào chi tiết triển khai. Refactor hợp lệ của mô-đun có thể phá aspect.

Nên cung cấp contract công khai như operation name, metadata của ngữ cảnh, interface chính sách hoặc adapter được chủ sở hữu mô-đun chấp nhận. Nếu cần khai báo pointcut bằng annotation, định nghĩa ngữ nghĩa annotation rõ ràng và tránh tạo vòng phụ thuộc giữa mô-đun domain với thư viện cơ chế không cần thiết.

### 6.3. Mô-đun nghiệp vụ phụ thuộc ngược vào aspect

Một nghiệp vụ luôn cần ghi “transaction đã commit” mà chỉ trông đợi một advice có thể bật/tắt hoặc bỏ qua sẽ trở nên mong manh. Những bất biến và hiệu ứng bắt buộc phải được biểu diễn trong hợp đồng nghiệp vụ/transaction; aspect chỉ nên thực hiện chính sách xuyên suốt theo thiết kế có kiểm chứng.

Tương tự, không cho cơ chế tracing quyết định tính thành công của nghiệp vụ nếu mất log; một collector quan sát gặp lỗi không nên mặc định làm hỏng kết quả trả về.

### 6.4. Có quá nhiều cơ chế can thiệp cùng một điểm

Khi authorization, cache, retry, transaction, tracing và exception mapping đều quanh một join point, số thứ tự khả dĩ tăng nhanh. Không có thứ tự “luôn đúng” cho mọi hệ thống. Phải xác định phụ thuộc ngữ nghĩa, chẳng hạn:

- Quyền truy cập phải được kiểm soát trước khi dữ liệu từ cache có thể được tiết lộ.
- Retry chỉ an toàn với lời gọi idempotent hoặc đã có thiết kế chống lặp.
- Tracing bên ngoài hay bên trong retry quyết định đếm một thao tác tổng hay từng attempt.
- Thời điểm transaction bắt đầu/commit quyết định advice nào quan sát được thành công thật sự.
- Exception translation có thể làm thay đổi loại lỗi mà advice khác nhìn thấy.

Cần ghi nhận thứ tự và lý do cho những tương tác có hậu quả nghiệp vụ hoặc bảo mật.

## 7. Khi nào mã nguồn dễ hiểu, khi nào trở nên khó đọc?

### Khả năng hiểu được cải thiện khi

- Cổng public mô tả rõ dữ liệu đầu vào, kết quả và lỗi có thể xảy ra.
- Mô-đun lõi tập trung vào domain, không trộn logging và metric ở mọi lớp.
- Mỗi aspect có một nhiệm vụ dễ gọi tên, phạm vi pointcut được giới hạn và kiểm thử được.
- Quy tắc kích hoạt và thứ tự được công khai ở composition root hoặc nơi đăng ký tương đương.
- Trace/log cung cấp danh tính operation nhất quán giữa module, nhưng không làm rò rỉ dữ liệu nhạy cảm.
- Sơ đồ luồng và tài liệu nêu cả các đường không được weaving hoặc không đi qua proxy.
- Kiểm thử tích hợp chạy trên cấu hình lắp ghép thật thay vì chỉ gọi trực tiếp mã lõi.

### Khả năng hiểu bị giảm khi

- Người đọc phải mở rất nhiều aspect để biết một phương thức có được gọi hay không.
- Pointcut chọn theo mẫu tên/package mơ hồ nên thêm mã mới vô tình thay đổi hành vi.
- Advice âm thầm thay kết quả, nuốt lỗi hoặc retry thao tác có tác dụng phụ.
- Thứ tự khía cạnh được xác định bởi cấu hình khó tìm hoặc không được kiểm thử.
- Kiểu phương thức/return value bị proxy đổi khác hợp đồng.
- Cơ chế context dùng trạng thái toàn cục ngầm và không truyền đúng qua async.
- Hai mô-đun lạm dụng dữ liệu nội bộ của nhau để tạo quyết định trong advice.

Một nguyên tắc hữu ích là **mã lõi rõ nghĩa và đường can thiệp cũng phải tra cứu được**. Tránh đánh đổi sự lặp lại nhỏ của vài dòng code bằng một hệ thống chính sách không ai xác định được luồng chạy.

## 8. Khả năng truy vết hành vi: từ source đến runtime

Khi điều tra câu hỏi “vì sao phương thức A trả lỗi trước khi chạy?”, người bảo trì cần một lộ trình nhất quán:

1. **Tìm cổng công khai:** interface hoặc API mô tả thao tác, đầu vào và lỗi.
2. **Tìm điểm lắp ghép:** cổng thực tế được tạo từ implementation và những proxy/advice nào?
3. **Tìm pointcut:** join point cần xem có thật sự được chọn không? Có điều kiện cấu hình hoặc annotation nào?
4. **Xác định thứ tự advice:** lớp nào bọc ngoài, lớp nào bọc trong, và lúc ném lỗi luồng đi qua lớp nào?
5. **Kiểm tra quyền/nguồn dữ liệu:** advice dựa vào metadata, ThreadLocal, parameter hay trạng thái nào; dữ liệu đó đáng tin không?
6. **Theo dõi proceed/invoke:** trường hợp nào bỏ qua gọi lõi, trường hợp nào gọi nhiều lần, trường hợp nào biến đổi kết quả?
7. **Đối chiếu bằng kiểm thử/trace:** sử dụng đường gọi thật, xác nhận luồng kết quả, lỗi và hành vi khi bật/tắt aspect.

Một bảng **bản đồ can thiệp** theo module có thể giúp:

| Cổng hoặc nhóm thao tác | Aspect áp dụng | Thứ tự có ý nghĩa | Điều kiện cần xác minh |
| --- | --- | --- | --- |
| Charge operations | Trace, authorization | Trace bao ngoài authorization | DENY không chạy lõi; có trace cho DENY |
| Query read-only | Authorization, cache, metrics | Quyền được thực thi trước khi tiết lộ dữ liệu | Không rò dữ liệu qua cache hit |
| External call có retry | Trace, retry, timeout | Scope một request so với từng attempt | Idempotency và giới hạn thời gian |
| Publish event | Metrics, exception handling | Quan sát lần gửi và trạng thái gửi | Không nhầm attempt với domain event |

Bảng này là tài liệu kiến trúc minh họa, **không phải định nghĩa mặc định** cho mọi dự án. Lưu nó gần cấu hình lắp ghép và cập nhật khi pointcut/thứ tự đổi; tốt hơn nữa, kiểm thử tự động có thể xác minh một phần bất biến từ bản đồ.

## 9. Mô-đun trong Java: package, interface và JPMS

Trong Java, chữ “module” có thể chỉ một thành phần kiến trúc hoặc một JPMS module khai báo bằng module-info.java. Hai khái niệm liên quan nhưng không đồng nhất:

- Package giúp tổ chức mã và kiểm soát truy cập theo visibility.
- Interface và kiểu dữ liệu công khai xác định hợp đồng phụ thuộc.
- JPMS có thể khai báo requires, exports và opens, qua đó điều khiển khả năng đọc module, khả năng truy cập API và quyền reflection theo chính sách runtime.
- Một mô-đun kiến trúc vẫn có thể gồm nhiều package/JPMS modules; ngược lại, một JPMS module có thể chứa nhiều trách nhiệm nếu thiết kế chưa tốt.

Nếu cơ chế AOP dùng reflection hay proxy, phạm vi exports/opens và accessibility của các kiểu có thể ảnh hưởng khả năng interception. **Không nên mở toàn bộ package nội bộ chỉ để một pointcut tiện truy cập.** Ưu tiên thiết kế API cho điểm tích hợp rõ và cấp quyền truy cập tối thiểu theo cơ chế thực tế sử dụng.

Không phải mọi phương thức private, constructor hay lời gọi nội bộ đều có thể bị can thiệp chỉ vì dự án đã bật AOP. Đây là giới hạn phụ thuộc công nghệ weaving; cần xác minh bằng tài liệu cơ chế đang dùng và kiểm thử đường thực tế.

## 10. Self-invocation và đường gọi bypass cơ chế AOP

Với cơ chế interception dựa trên proxy, lời gọi từ bên ngoài đi qua proxy có thể bị advice chặn. Nhưng một phương thức trong implementation gọi một phương thức khác trực tiếp trên cùng đối tượng (self-invocation) có thể không đi qua proxy.

Ví dụ mô hình:

~~~text
caller -> proxy -> Service.publicMethod()
                       |
                       v
                  this.internalMethod()
                       |
                    (không đi qua proxy)
~~~

Nếu một chính sách bảo mật hoặc giao dịch chỉ nằm ở interceptor của internalMethod(), đường gọi nội bộ trên một đối tượng như vậy có thể bỏ qua chính sách. Cơ chế bytecode weaving tại điểm thực thi có thể có phạm vi khác; không được áp dụng kết luận self-invocation của proxy cho mọi cơ chế AOP.

Giải pháp phụ thuộc trách nhiệm: đặt enforcement ở cổng đáng tin mà mọi đường cần bảo vệ phải đi qua, trích một cộng tác viên có interface được bọc đúng, hoặc dùng phương án weaving được xác nhận. Đối với bất biến nghiệp vụ bắt buộc, không đặt toàn bộ an toàn vào một advice có thể bị bỏ qua bởi đường gọi hợp lệ khác.

## 11. Phân biệt cross-cutting concern với nghiệp vụ cốt lõi

Không phải logic xuất hiện ở nhiều nơi đều nên chuyển thành aspect.

**Các cơ chế phù hợp** thường có tính thống nhất: đo thời gian một nhóm lời gọi, tạo span, gắn correlation ID, kiểm tra quyền tổng quát theo policy rõ, ghi nhận thống kê cache.

**Các quy tắc cần thuộc domain** thường liên quan ý nghĩa: thanh toán có hợp lệ, đơn hàng đã chuyển trạng thái, tồn kho có cho phép đặt, người dùng có thể sửa một tài nguyên trong trạng thái nào, event nghiệp vụ nào phải phát sinh.

Một phép thử thiết kế: nếu vô hiệu hóa aspect, thuật toán domain có vẫn xác định đúng kết quả theo hợp đồng không? Với advice chỉ ghi telemetry, câu trả lời thường là có. Với aspect bảo mật hoặc transaction bắt buộc, vô hiệu hóa có thể gây vi phạm; khi đó phải coi nó là **thành phần bắt buộc của ranh giới thực thi**, có kiểm thử và cấu hình fail-closed thay vì một tùy chọn ẩn.

Không dùng việc “đặt trong aspect” để tránh phải xác định owner cho quy tắc. Cơ chế triển khai chỉ là một phần của quyết định kiến trúc; tính đúng và quyền sở hữu policy vẫn phải có người chịu trách nhiệm.

## 12. Thứ tự advice, ngoại lệ và hành vi trả về

Một advice có thể thay đổi nhiều thứ ngoài việc ghi log:

- **Before advice** có thể từ chối trước khi lõi chạy.
- **Around advice** có thể bỏ qua, lặp lại hoặc thay đổi kết quả từ thao tác gốc.
- **After-returning** chỉ thấy đường trả về bình thường theo join point được chọn; không có nghĩa transaction đã commit ở một nơi khác.
- **After-throwing** thấy ngoại lệ đi qua ranh giới tương ứng; không phải mọi lỗi bất đồng bộ xảy ra sau khi phương thức trả về đều được quan sát ở đây.
- **After/finally** có thể chạy cả đường thành công và thất bại, nhưng lỗi mới từ code quan sát có thể che mất lỗi gốc nếu xử lý kém.

Nếu một phương thức trả CompletionStage/Future, return của phương thức tạo tác vụ thường chỉ chứng tỏ đã trả handle; không đồng nghĩa công việc bất đồng bộ hoàn tất. Một aspect chỉ đo khoảng trước/sau proceed có thể báo duration nhỏ hơn nhiều so với độ trễ kết quả cuối. Khi yêu cầu quan sát completion phải gắn callback hoặc instrument nơi hoàn tất, và nêu rõ trạng thái lỗi/huỷ.

Đây là ví dụ điển hình cho khả năng hiểu mã nguồn: một phương thức có vẻ “trả kết quả” có thể thực tế mới hoàn tất **bước gửi việc**. Tài liệu hợp đồng và tên metric phải xác định rõ ranh giới được đo.

## 13. Kiểm thử ranh giới mô-đun và khả năng hiểu hành vi

Nên có các lớp kiểm thử phục vụ mục đích khác nhau:

### Kiểm thử logic lõi

Gọi trực tiếp implementation để xác nhận bất biến nghiệp vụ, loại trừ việc advice gây nhiễu. Ví dụ kiểm tra amount không hợp lệ bị từ chối và không tạo charge. Kiểm thử này **không** chứng minh cổng đã được bảo vệ bởi AOP.

### Kiểm thử chuỗi advice thực tế

Khởi tạo đúng composition root hoặc đúng cấu hình weaving rồi xác nhận:

1. Lời gọi được phép đi qua advice theo thứ tự mong muốn và vào lõi đúng số lần.
2. Lời gọi bị từ chối không vào lõi, trả lỗi đúng hợp đồng.
3. Advice ghi telemetry không thay đổi giá trị trả về hoặc ngoại lệ gốc.
4. Bật/tắt các phần quan sát tùy chọn không làm đổi nghiệp vụ.
5. Các điểm không được chọn bởi pointcut không bị can thiệp ngoài ý muốn.
6. Các đường self-invocation, direct-call và async được xử lý đúng giới hạn cơ chế.

### Kiểm thử kiến trúc

Kiểm tra dependency direction và ownership: ví dụ module domain không import collector quan sát, mô-đun AOP không gọi trực tiếp lớp repository nội bộ, các kiểu API được công khai tối thiểu, và danh sách pointcut áp dụng cho đúng cổng dự định.

Đối với chính sách bảo mật và transaction, nên có kiểm thử tích hợp trên đường đi thật. Mock lời gọi trực tiếp đến class lõi có thể bỏ qua proxy và cho kết quả đánh lừa.

## 14. Sai lầm phổ biến và cách khắc phục

| Sai lầm | Tại sao làm khó hiểu hoặc sai kiến trúc? | Cách sửa |
| --- | --- | --- |
| Đọc thân phương thức rồi cho rằng đó là toàn bộ runtime | Không nhìn thấy advice và composition | Lần theo cổng, pointcut, thứ tự, đường gọi thật |
| Pointcut trùm toàn bộ namespace quá rộng | Mô-đun mới vô tình chịu chính sách cũ | Chọn ranh giới có ý nghĩa; kiểm thử match set |
| Aspect dùng reflection truy cập nhiều private field | Coupling với chi tiết nội bộ | Cấp metadata/hợp đồng tối thiểu |
| Nhiều aspect tự sửa cùng return value | Kết quả phụ thuộc thứ tự khó theo dõi | Phân rõ owner và thứ tự, hạn chế biến đổi |
| Retry mọi phương thức ở advice | Có thể lặp thao tác không idempotent | Chỉ retry theo hợp đồng và chính sách rõ |
| Tracing hoặc cache che kiểm tra quyền | Có thể lộ dữ liệu hoặc mất audit | Xác minh thứ tự và ranh giới bảo mật |
| Coi return bình thường là commit/domain event | Sự kiện sai khi rollback hoặc async còn chạy | Quan sát đúng mốc nghiệp vụ |
| Bảo vệ chỉ bằng proxy nhưng caller giữ reference tới core | Đường trực tiếp bypass advice | Composition root chỉ xuất cổng được bảo vệ |
| Đọc code lõi nhưng không kiểm thử aspect | Test xanh dù runtime thiếu policy | Kiểm thử lắp ghép và đường thực thi thực |
| Bật aspect theo cấu hình khó tìm | Khó tái hiện hành vi giữa môi trường | Tập trung cấu hình và công khai trạng thái áp dụng |

## 15. Checklist để giữ AOP vừa hữu ích vừa dễ bảo trì

1. Xác định hợp đồng công khai và owner của mỗi mô-đun.
2. Viết rõ lý do cross-cutting concern cần áp dụng xuyên nhiều cổng.
3. Giữ logic domain, bất biến và sự kiện nghiệp vụ trong phạm vi sở hữu đúng.
4. Định nghĩa pointcut bằng tiêu chí ổn định, kiểm chứng được tập join point.
5. Giới hạn dữ liệu nội bộ mà aspect được phép đọc/ghi.
6. Tập trung nơi đăng ký và thứ tự advice; mô tả lý do của các thứ tự quan trọng.
7. Bảo vệ tất cả đường gọi cần enforcement, gồm direct-call, self-invocation và async.
8. Ghi rõ khi nào advice được phép chặn, retry, cache hoặc đổi return/exception.
9. Cho người đọc đường truy tìm từ API công khai đến code lõi và các aspect thực sự áp dụng.
10. Kiểm thử song song domain thuần, composition có AOP và ranh giới kiến trúc.
11. Đo overhead của advice và tránh logging/metric quá nặng trong đường nóng.
12. Xem lại pointcut và chính sách AOP khi refactor API, di chuyển package, thay đổi giao dịch hoặc bổ sung mô-đun.

**Kết luận:** AOP có thể làm mã nghiệp vụ gọn và tăng tái sử dụng cơ chế xuyên suốt, nhưng nó thêm một lớp hành vi mà người đọc thân phương thức không nhìn thấy ngay. Kiến trúc tốt đặt aspect ở ranh giới rõ ràng, giữ quyền sở hữu domain, công khai composition và thứ tự can thiệp, đồng thời có kiểm thử xác nhận hành vi runtime. Khi đó, tách mô-đun và khả năng hiểu mã nguồn hỗ trợ nhau thay vì xung đột.
