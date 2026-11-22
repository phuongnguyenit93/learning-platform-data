# Lộ trình từ khái niệm đến cơ chế và ứng dụng AOP

## Bạn sẽ học được gì?

Aspect-Oriented Programming (**AOP**, lập trình hướng khía cạnh) là cách tổ chức những hành vi có xu hướng xuất hiện tại nhiều điểm thực thi của chương trình thành các mô-đun riêng, thường gọi là **aspect**. Để sử dụng đúng, cần học theo trình tự: **vì sao cần AOP → AOP mô tả điểm can thiệp như thế nào → cơ chế can thiệp hoạt động ra sao → viết và kiểm thử → quyết định khi nào áp dụng**. Biết cú pháp của một công cụ mà chưa hiểu chuỗi này dễ dẫn tới pointcut quá rộng, hành vi ẩn hoặc suy luận sai về những lời gọi thực sự được xử lý.

Sau bài học, bạn có thể:

1. Nhận ra *cross-cutting concern* (mối quan tâm xuyên suốt), hiện tượng *scattering* (mã một chính sách bị rải rác) và *tangling* (mã chính sách đan xen nghiệp vụ).
2. Giải thích chính xác **join point**, **pointcut**, **advice**, **aspect**, **target**, **weaving**, cũng như giới hạn tùy từng cơ chế AOP.
3. Đọc một luồng thực thi có advice chạy trước/sau/bao quanh; xác định điều gì xảy ra khi phương thức trả về hoặc ném lỗi.
4. Phân biệt proxy dựa trên interface, proxy dựa trên lớp và weaving vào mã; thực hành một minh họa Java 17 chạy được.
5. Tự thiết kế và kiểm thử một chính sách xuyên suốt, từ phạm vi lựa chọn đến thứ tự, ngoại lệ, chi phí và rủi ro vận hành.
6. Chọn AOP cho bài toán phù hợp và từ chối AOP khi quy tắc cần thể hiện tường minh trong mô hình nghiệp vụ.

Bài học dùng **AOP như một kỹ thuật lập trình chung**, độc lập với sản phẩm hoặc thư viện cụ thể. Ký pháp được ghi là *giả mã* chỉ nhằm giải thích khái niệm; cú pháp pointcut và tập join point thực tế phụ thuộc vào cơ chế triển khai.

## 1. Bản đồ học tập: đi từ vấn đề đến giải pháp

| Chặng | Câu hỏi cần trả lời | Kết quả cần tự chứng minh |
| --- | --- | --- |
| **0. Nền tảng** | Interface, lời gọi phương thức, decorator, reflection và ngoại lệ hoạt động thế nào? | Giải thích được call stack, hợp đồng phương thức và một wrapper thông thường. |
| **1. Nhận diện vấn đề** | Vì sao cùng một chính sách xuất hiện ở nhiều chức năng? | Phân biệt scattering/tangling với logic nghiệp vụ cần giữ tường minh. |
| **2. Nắm mô hình AOP** | Pointcut chọn gì, advice làm gì, aspect chứa gì? | Giải thích được join point, pointcut, advice, target và weaving. |
| **3. Thiết kế điểm áp dụng** | Phạm vi nào phải khớp, phải loại trừ và hợp đồng advice là gì? | Viết được ca dương/âm và sơ đồ success/error path. |
| **4. Hiểu cách kết hợp** | Lời gọi nào thực sự đi qua advice? | So sánh proxy với weaving, chỉ ra đường đi được hoặc bị bỏ qua. |
| **5. Thực hành Java** | Làm sao thêm chính sách mà không đổi logic chính? | Chạy demo Java, xác nhận marker, exception và phạm vi áp dụng. |
| **6. Nâng cao** | Nhiều advice, recursion, lỗi, bất đồng bộ và hiệu năng thì sao? | Dự đoán thứ tự, bảo toàn ngữ nghĩa và kiểm thử edge cases. |
| **7. Ứng dụng** | Khi nào dùng AOP, khi nào chọn thiết kế khác? | Đề xuất chính sách, cơ chế, ma trận kiểm thử và phương án thay thế. |

**Cách học:** Không chuyển chặng chỉ vì đã thuộc định nghĩa. Mỗi chặng có một câu hỏi hoặc phép thử đầu ra; nếu chưa giải thích được trường hợp biên, quay lại chặng liên quan.

## 2. Chặng 0 — Nền tảng cần có trước khi nhìn vào AOP

AOP không thay thế kiến thức hướng đối tượng hoặc luồng thực thi Java. Đặc biệt cần hiểu:

- **Đối tượng và interface:** Bên gọi có thể nắm một interface còn phía sau là đối tượng thật hoặc đối tượng bọc (*wrapper*). Kết quả phụ thuộc đối tượng nào nhận lời gọi.
- **Decorator:** Một đối tượng cài cùng interface, xử lý trước/sau rồi ủy quyền cho đối tượng gốc. Đây là ví dụ dễ hiểu về thêm hành vi tại biên, dù chưa có hệ thống pointcut.
- **Call stack:** Phương thức có thể trả về bình thường, ném exception hoặc gọi các phương thức khác; thứ tự chạy và cleanup quyết định ngữ nghĩa.
- **Reflection và dynamic dispatch:** Java có thể tìm và gọi phương thức tại runtime, nhưng cần hiểu kiểu phương thức, đối tượng đích và việc đóng gói ngoại lệ.
- **Hợp đồng phương thức:** Input, output, exception, side effect và điều kiện thành công quan trọng hơn việc viết ít dòng mã.

**Bài tự kiểm tra:** Nếu `x.transfer()` gọi `this.validate()`, hãy chỉ ra đối tượng nhận từng lời gọi. Nếu thay `x` bằng wrapper, bạn có chắc lần gọi nội bộ cũng đi qua wrapper không? Câu trả lời phải dựa vào sơ đồ đối tượng thực tế, không dựa vào tên phương thức.

## 3. Chặng 1 — Thấy vấn đề trước khi đề xuất aspect

Hãy tưởng tượng ứng dụng có nhiều thao tác như `send()`, `importData()`, `calculate()`. Mỗi thao tác đều cần ghi lại thời gian, mã tương quan và trạng thái lỗi. Nếu chép cùng đoạn xử lý vào từng hàm, sẽ có hai dạng khó khăn:

- **Scattering:** Cùng một chính sách ghi đo lường nằm ở nhiều vị trí; thay đổi định dạng phải sửa nhiều nơi và dễ bỏ sót.
- **Tangling:** Một hàm xử lý nhập dữ liệu phải xen kẽ logic chính với log, đo thời gian, xử lý thống kê; người đọc khó nhận ra đâu là nghiệp vụ.

Một thiết kế có thể tách nhóm hành vi này thành module độc lập, rồi định nghĩa **tập điểm thực thi cần áp dụng**. Đó là động cơ cốt lõi để nghĩ tới AOP.

Nhưng không phải mọi phần mã bị lặp đều là mối quan tâm xuyên suốt phù hợp với aspect. Chẳng hạn, “đơn hàng vượt hạn mức phải được phê duyệt” có thể xuất hiện tại nhiều tuyến xử lý, nhưng đó là **quyết định nghiệp vụ**; nó cần hiện rõ trong domain policy hoặc workflow, vì ảnh hưởng trực tiếp tính đúng đắn và có thể phụ thuộc ngữ cảnh dữ liệu.

### Cách nhận diện một ứng viên AOP

Hãy viết thành câu: “Tại **những điểm X**, mỗi lần **sự kiện Y** xảy ra, thực hiện **chính sách Z** với **hợp đồng H**.”

Ví dụ hợp lý:

> Tại các điểm gọi thao tác lưu trữ được đánh dấu, khi mỗi thao tác bắt đầu/kết thúc, ghi số lần gọi và trạng thái thành công/thất bại; việc đo không thay đổi dữ liệu lưu và không được làm lộ tham số nhạy cảm.

Nếu không xác định được X, Y, Z, H một cách rõ ràng, có thể chưa đủ điều kiện để thiết kế aspect an toàn.

**Đầu ra chặng 1:** Liệt kê ít nhất ba nơi có cùng chính sách kỹ thuật và một ngoại lệ rõ ràng **không** nên bị áp dụng. Đây sẽ là dữ liệu kiểm thử pointcut ở chặng sau.

## 4. Chặng 2 — Mô hình khái niệm: thành phần nào chịu trách nhiệm gì?

| Khái niệm | Trả lời câu hỏi | Chú ý |
| --- | --- | --- |
| **Concern** | Cần giải quyết vấn đề gì? | Một concern xuyên suốt có thể là quan sát độ trễ, audit hoặc chính sách kỹ thuật chung. |
| **Aspect** | Chính sách xuyên suốt được đóng gói ở đâu? | Có thể kết hợp logic advice với biểu thức chọn điểm và cấu hình liên quan. |
| **Target** | Mã/đối tượng nghiệp vụ gốc là gì? | Logic đích vẫn mang trách nhiệm chính của chức năng. |
| **Join point** | Điểm can thiệp có thể quan sát hoặc xử lý trong luồng thực thi là gì? | Ví dụ một lần *execution* của phương thức; một số cơ chế hỗ trợ thêm *call*, truy cập field, constructor... |
| **Pointcut** | Chọn tập join point nào? | Có thể mô tả theo chữ ký, loại, package, marker, ngữ cảnh... tùy công cụ. |
| **Advice** | Khi điểm được chọn xảy ra, chạy hành vi gì và lúc nào? | Có thể là before, after, around và các biến thể khi return/throw. |
| **Weaving** | Advice được kết hợp với mã chạy bằng cách nào? | Có thể ở compile time, load time hoặc runtime tùy kỹ thuật. |
| **Introduction / inter-type declaration** | Có mở rộng cấu trúc/khả năng của kiểu hay không? | Chỉ có ở một số công nghệ AOP; là chủ đề nâng cao, không phải tính năng bắt buộc. |

### Một dòng thời gian mẫu

Giả sử có một join point là lúc thực thi `AccountService.transfer(...)`. Một advice quan sát có thể tạo luồng:

```text
Bên gọi
   |
   v
[Before advice] -> [Thực thi transfer] -> [After returning advice]
                                    |
                                    +-> nếu ném lỗi: [After throwing advice]
   |
   v
Bên gọi nhận giá trị hoặc exception
```

Đây là **sơ đồ khái niệm**, chưa mô tả thứ tự của nhiều aspect hoặc cleanup. Advice kiểu “after/finally” thường được diễn giải là chạy khi join point kết thúc bằng cả hai đường; advice chỉ dành cho *returning* và advice chỉ dành cho *throwing* có điều kiện kích hoạt khác nhau. Tên loại advice, thứ tự cụ thể và khả năng can thiệp ngoại lệ phụ thuộc công cụ.

### Phân biệt “điểm có thể can thiệp” và “điểm đã chọn”

Giả sử chương trình có 100 lần thực thi phương thức. Cơ chế AOP hỗ trợ điểm thực thi phương thức sẽ xem mỗi lần đó như một join point tiềm năng. Một pointcut chỉ chọn 15 điểm thỏa điều kiện. Advice chỉ chạy tại những điểm thực sự được chọn **và đi qua con đường can thiệp hợp lệ**.

Không nên đồng nhất:

- “Công cụ có thể can thiệp vào phương thức” với “mọi phương thức đều bị can thiệp”.
- “Một biểu thức pointcut khớp chữ ký” với “mọi đường gọi runtime đều chắc chắn chạy advice”.
- “Join point thực thi” với “join point gọi phương thức”. Với công nghệ phân biệt `call` và `execution`, chúng là hai vị trí và hai ngữ nghĩa khác nhau.

**Đầu ra chặng 2:** Khi nhìn thấy một aspect, bạn phải mô tả được **nó chọn điểm nào**, **hành vi gì**, **diễn ra lúc nào**, và **được kết hợp qua cơ chế gì**.

## 5. Chặng 3 — Thiết kế pointcut và advice trước khi viết mã

### 5.1. Pointcut là hợp đồng phạm vi

Một điểm cắt tốt cần có cả **tập được chọn** lẫn **tập phải loại trừ**. Giả mã tiêu chí:

```text
chọn join point nếu:
    là execution của thao tác công khai tại biên lưu trữ
    VÀ đã được đánh dấu cần đo
    VÀ không thuộc mã đo lường
```

Các công nghệ khác nhau biểu diễn quy tắc bằng biểu thức chữ ký, annotation/marker, quan hệ kiểu, đối tượng runtime hoặc mã cấu hình. Ký pháp ví dụ ở trên **không phải biểu thức pointcut dùng nguyên xi trong một thư viện**.

Đánh giá pointcut theo bốn câu hỏi: có chọn đủ điểm mong muốn, có chọn nhầm chỗ không, refactor có làm thay đổi tập điểm âm thầm không, và có cách nào kiểm thử được phạm vi này? Một pointcut rất rộng có thể làm logic kỹ thuật xuất hiện ở những vùng chưa từng được xét tới.

### 5.2. Advice trả lời chuyện gì xảy ra tại điểm đã chọn

| Kiểu hành vi | Cách hiểu | Ví dụ thích hợp |
| --- | --- | --- |
| **Before** | Trước khi join point thực thi. | Bắt đầu thu thập dấu vết; kiểm tra điều kiện kỹ thuật không thay đổi nghiệp vụ. |
| **After returning** | Sau khi thực thi kết thúc bình thường. | Ghi số lần thành công sau khi có kết quả trả về. |
| **After throwing** | Khi join point kết thúc bằng exception. | Ghi loại lỗi, duy trì exception ban đầu. |
| **After / finally** | Dọn dẹp hoặc ghi nhận bất kể bình thường hay lỗi. | Kết thúc context đo đạc. |
| **Around** | Bao quanh quá trình thực thi; có thể quyết định cách hoặc có gọi tiếp hay không tùy cơ chế. | Đo khoảng thời gian tổng thể, bọc một hoạt động idempotent bằng retry có kiểm soát. |

Với advice kiểu around, khái niệm **proceed** thường là thao tác tiếp tục vào phần bên trong của chuỗi xử lý, có thể gồm advice tiếp theo và target. Một implementation có thể không gọi, gọi một lần hoặc gọi nhiều lần; mỗi lựa chọn đều ảnh hưởng hợp đồng của chương trình.

Ví dụ giả mã:

```text
around operation:
    start = monotonicClock()
    try:
        return proceed()         // chuyển quyền thực thi vào bên trong
    finally:
        recordDuration(monotonicClock() - start)
```

Mục đích của `finally` là đo cả đường lỗi. Khi đo độ trễ, nên dùng nguồn thời gian **đơn điệu** (*monotonic*) phù hợp, thay vì lấy thời gian đồng hồ lịch có thể bị chỉnh trong khi chạy. Nếu hàm ghi đo trong `finally` cũng ném lỗi, nó có thể che mất lỗi gốc; phải quyết định chính sách xử lý lỗi ghi đo.

### 5.3. Hợp đồng quan trọng hơn việc advice chạy thành công

Trước khi bật một advice hãy ghi ra:

- **Đầu vào:** Có đọc hoặc sửa tham số không? Có dữ liệu nhạy cảm cần loại khỏi log không?
- **Đầu ra:** Có đổi giá trị trả về không? Điều kiện ghi “thành công” là phương thức trả về hay cam kết bền vững?
- **Ngoại lệ:** Có giữ nguyên loại/nguyên nhân exception? Nếu logging lỗi thì phương thức chính ra sao?
- **Tác dụng phụ:** Có thể bị chạy lặp do retry? Một lần gọi phải được thực thi đúng một lần hay có cơ chế idempotency?
- **Context:** Metadata, correlation ID, transaction hoặc thread context được tạo và xóa ở đâu?

**Đầu ra chặng 3:** Mô tả pointcut theo tiêu chí kiểm chứng được, vẽ được success/error path, và giải thích được vì sao advice không thay đổi hợp đồng ngoài phần chính sách đã công bố.

## 6. Chặng 4 — Cơ chế thực thi: từ cấu hình đến bytecode và lời gọi

Một lỗi phổ biến khi học AOP là nghĩ rằng chỉ cần viết aspect thì mọi lệnh gọi khớp tên sẽ tự động chạy advice. Thực tế phải hiểu **đường đi của lời gọi** và **cách mã can thiệp được chèn vào**.

### 6.1. Proxy dựa trên interface

Bên gọi giữ tham chiếu một đối tượng proxy cài cùng interface với target. Khi bên gọi gọi phương thức **qua proxy**, proxy chạy handler/advice rồi mới ủy quyền đến target.

```text
client -> proxy [advice] -> target.method(...)
                  ^                 |
                  +---- result/error+
```

Ưu điểm là có thể thêm hành vi ở runtime, dễ hiểu từ góc nhìn một wrapper. Giới hạn: một lời gọi đi trực tiếp tới target không thông qua proxy; lời gọi nội bộ trên `this` ở target thường cũng bỏ qua proxy. Với proxy dựa trên interface, chỉ các phương thức giao diện được lộ qua proxy. Đây là giới hạn **của mô hình proxy tương ứng**.

### 6.2. Proxy dựa trên lớp

Một số cơ chế tạo lớp con hoặc đối tượng tương đương để chặn phương thức. Phạm vi khác proxy interface; hành vi `final`, `private`, constructor, khả năng tạo lớp con và dispatch tùy cách triển khai. Không nên suy ra rằng cơ chế dựa trên lớp sẽ can thiệp được **mọi** phương thức của **mọi** đối tượng.

### 6.3. Weaving vào mã

Một hướng khác kết hợp hành vi của aspect với mã lớp, có thể diễn ra:

- **Compile-time:** khi biên dịch mã nguồn/bytecode.
- **Post-compile/binary weaving:** trên bytecode đã biên dịch trước khi nạp hoặc phân phối.
- **Load-time:** khi lớp được nạp vào runtime.
- **Runtime transformation:** khi môi trường hỗ trợ sửa/biến đổi mã tại thời điểm thực thi phù hợp.

Các thời điểm này là **các khả năng kỹ thuật**, không có nghĩa mọi công cụ đều hỗ trợ tất cả. Weaving có thể cung cấp tập join point rộng hơn mô hình proxy đơn giản, nhưng thêm yêu cầu build, class loading, công cụ quan sát và tương thích.

### 6.4. Bảng so sánh cơ chế

| Tiêu chí | Proxy theo interface | Proxy dựa trên lớp | Weaving bytecode |
| --- | --- | --- | --- |
| Nơi lời gọi được chặn | Qua tham chiếu proxy thực sự. | Qua điểm dispatch có thể được lớp đại diện can thiệp. | Ở điểm được đưa logic vào bytecode. |
| Điểm mạnh | Rõ ràng về contract interface, có thể minh họa bằng JDK. | Có thể dùng trong một số tình huống không có interface. | Có thể hỗ trợ nhiều dạng join point hơn. |
| Điểm cần kiểm tra | Gọi trực tiếp target, self-invocation, phương thức không thuộc interface. | Quy tắc override, `final`, `private`, constructor, khả năng tạo proxy. | Thứ tự weaving, classloader, build, tương thích bytecode và công cụ debug. |
| Điều cần chứng minh | Call path có đi qua proxy không? | Method có bị chặn theo đúng cơ chế không? | Bytecode đang chạy đã được weave và pointcut có khớp không? |

**Đầu ra chặng 4:** Với một lời gọi cụ thể, vẽ được `caller → [proxy/weaving?] → target`, thay vì kết luận chỉ bằng tên phương thức hay annotation.

## 7. Chặng 5 — Thực hành Java 17: mô phỏng AOP bằng dynamic proxy

Ví dụ sau dùng **JDK dynamic proxy** để làm rõ quan hệ giữa điểm được chọn và advice. Một marker `@Observed` được đặt trên phương thức **interface**; handler chỉ in quan sát khi đúng marker. Chúng ta chủ động giữ quy tắc nghiệp vụ trong target. Đây là **minh họa AOP ở mức cơ chế**, không phải engine AOP hoàn chỉnh và không cung cấp ngôn ngữ pointcut phổ quát.

Tạo tệp `AopLearningPath.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AopLearningPath {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Observed { }

    interface PaymentService {
        @Observed
        String pay(String reference);
        String health();
    }

    static final class DefaultPaymentService implements PaymentService {
        @Override
        public String pay(String reference) {
            if (reference == null || reference.isBlank()) {
                throw new IllegalArgumentException("reference required");
            }
            System.out.println("BUSINESS pay " + reference);
            return "PAID " + reference;
        }

        @Override
        public String health() {
            System.out.println("BUSINESS health");
            return "UP";
        }
    }

    static PaymentService observed(PaymentService target) {
        return (PaymentService) Proxy.newProxyInstance(
                PaymentService.class.getClassLoader(),
                new Class<?>[] { PaymentService.class },
                (proxy, method, args) -> invoke(target, method, args)
        );
    }

    static Object invoke(PaymentService target, Method method, Object[] args)
            throws Throwable {
        boolean selected = method.isAnnotationPresent(Observed.class);
        if (selected) {
            System.out.println("ADVICE before " + method.getName());
        }
        try {
            Object result = method.invoke(target, args);
            if (selected) {
                System.out.println("ADVICE success " + method.getName());
            }
            return result;
        } catch (InvocationTargetException ex) {
            if (selected) {
                System.out.println("ADVICE failure " + method.getName());
            }
            throw ex.getCause();
        }
    }

    public static void main(String[] args) {
        PaymentService target = new DefaultPaymentService();
        PaymentService proxied = observed(target);

        System.out.println("RESULT " + proxied.pay("P-17"));
        System.out.println("RESULT " + proxied.health());

        try {
            proxied.pay("");
        } catch (IllegalArgumentException ex) {
            System.out.println("CALLER caught " + ex.getMessage());
        }
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac AopLearningPath.java
java AopLearningPath
```

Đầu ra kỳ vọng, theo đúng thứ tự:

```text
ADVICE before pay
BUSINESS pay P-17
ADVICE success pay
RESULT PAID P-17
BUSINESS health
RESULT UP
ADVICE before pay
ADVICE failure pay
CALLER caught reference required
```

### Đọc chương trình theo từng thành phần

1. **Target:** `DefaultPaymentService` thực hiện `pay` và `health`. Luật `reference` không được rỗng là nghiệp vụ, nên nằm trong target.
2. **Join point minh họa:** lần gọi phương thức interface qua đối tượng `proxied`; khả năng chặn cụ thể là do dynamic proxy.
3. **Pointcut minh họa:** điều kiện `method.isAnnotationPresent(Observed.class)`. Trong ví dụ chỉ `pay` được gắn marker tại **phương thức interface** nên `health` không phát sự kiện advice.
4. **Advice minh họa:** các dòng `ADVICE before/success/failure`. Handler cũng gọi target kể cả với `health`, nhưng không ghi advice ở điểm không được chọn.
5. **Cơ chế kết hợp:** đối tượng trả từ `Proxy.newProxyInstance` đảm nhận việc chuyển lời gọi qua handler. Không có weaving vào bytecode target trong ví dụ.
6. **Ngoại lệ:** `Method.invoke` bọc exception của phương thức đích trong `InvocationTargetException`; `throw ex.getCause()` truyền tiếp lỗi gốc tới caller. Trong phiên bản thực tế còn cần chính sách rõ về lỗi do chính advice gây ra.

**Thử nghiệm đối chứng:**

- Đổi dòng `proxied.pay("P-17")` thành `target.pay("P-17")`: nghiệp vụ vẫn thực thi nhưng sẽ không có dòng `ADVICE ...` cho lời gọi đó, vì bỏ qua proxy.
- Bỏ annotation `@Observed` tại `PaymentService.pay`: handler vẫn chuyển lời gọi, nhưng quy tắc lựa chọn không khớp, nên không in dòng `ADVICE ...`.
- Gọi `proxied.health()`: không có advice, chứng minh **điểm phải loại trừ** cũng được kiểm thử.
- Đưa marker **chỉ** vào phương thức triển khai mà không sửa cách tìm annotation: `method` mà dynamic proxy nhận là phương thức interface, vì vậy `isAnnotationPresent` trên `method` không tự dò marker ở implementation. Đây là ví dụ về sự khác nhau giữa **metadata ở đâu** và **pointcut thực sự kiểm tra ở đâu**.

### Tại sao đây vẫn chưa phải bộ AOP đầy đủ?

Handler ở đây chỉ chặn lời gọi qua interface, dùng một predicate Java để chọn phương thức và ghi log đồng bộ. Một hệ thống AOP tổng quát còn có thể hỗ trợ biểu thức pointcut, nhiều advice có thứ tự, join point khác phương thức, weaving, binding ngữ cảnh và quản lý lifecycle. Do đó, không dùng kết quả demo để kết luận giới hạn hoặc khả năng của **mọi** cơ chế AOP.

**Đầu ra chặng 5:** Chạy được chính xác ví dụ, giải thích từng dòng kết quả và dự đoán đúng kết quả khi thay một trong ba yếu tố: cách gọi, marker hoặc tình huống ném lỗi.

## 8. Chặng 6 — Học nâng cao: khi một aspect không còn đơn giản

### 8.1. Nhiều advice và thứ tự lồng nhau

Giả sử advice A và B đều là around tại cùng một join point. Một thứ tự có thể là:

```text
A.before
  B.before
    target
  B.after
A.after
```

Nếu B chạy trước A ở phía ngoài, thứ tự quan sát đổi khác. Các cơ chế AOP khác nhau có quy tắc về *precedence/order* và cách xác định tie-breaker. Không nên dựa vào thứ tự ngẫu nhiên hoặc thứ tự tình cờ xuất hiện trong mã.

Đặc biệt, **đo thời gian** ở ngoài lớp retry sẽ đo toàn bộ các lần thử, còn ở bên trong lớp retry có thể đo từng lần; cả hai đều đúng cho mục đích khác nhau. Tương tự, audit “thành công” trước commit không mang cùng nghĩa với audit sau khi dữ liệu đã được lưu bền vững.

### 8.2. Reentrancy, recursion và tự gọi

Một aspect có thể vô tình gọi vào phương thức cũng khớp chính pointcut của nó, tạo vòng lặp:

```text
advice -> logger -> method được pointcut chọn -> advice -> ...
```

Giải pháp có thể là pointcut loại trừ module/loại phương thức phục vụ đo lường, hoặc thiết kế tầng quan sát không tái kích hoạt chính nó. Kỹ thuật “cờ đang thực thi” cũng có rủi ro nếu context không được xóa đúng cách. Với recursion hay self-invocation, trước hết phải xác minh **cơ chế can thiệp**: proxy đơn giản và weaving vào bytecode có hành vi khác nhau.

### 8.3. Around advice có thể thay đổi ngữ nghĩa

Một around advice gọi `proceed()` hai lần có thể tạo ra hai tác dụng phụ. Vì vậy, **retry không thể thêm tùy tiện** cho thanh toán, chuyển khoản, gửi thông báo hoặc cập nhật trạng thái. Cần phân loại lỗi có thể thử lại, giới hạn số lần, backoff, timeout tổng, idempotency và bảo đảm ngừng đúng hạn.

Nếu advice đổi tham số, giá trị trả về hoặc exception, nó đang mở rộng hợp đồng. Điều này có thể hợp lý ở một biên kỹ thuật đã công bố, nhưng nguy hiểm nếu người đọc nghiệp vụ không biết. Đối với phần lớn advice quan sát, thiết kế an toàn hơn là không sửa kết quả hay che lỗi gốc.

### 8.4. Tài nguyên, exception và lỗi của chính advice

Phân biệt ít nhất ba lỗi:

1. **Target lỗi:** Advice cần ghi nhận rồi cho lỗi đi qua hay chuyển sang một kiểu lỗi có hợp đồng rõ?
2. **Chính advice lỗi:** Log/metrics hỏng thì nghiệp vụ có tiếp tục không? Với audit bắt buộc, fail-open có thể sai yêu cầu.
3. **Weaving/configuration lỗi:** Aspect không được áp dụng ở những nơi cần thiết, hoặc áp dụng quá rộng; đây là lỗi phạm vi, có thể không tạo exception nào.

Nếu advice mở tài nguyên, cần cleanup trên mọi đường thoát. Nếu advice ghi log nguyên input/output, cần kiểm soát dữ liệu cá nhân và bí mật. “Aspect dùng chung” có thể khuếch đại một lỗi nhỏ trên nhiều chức năng.

### 8.5. Concurrency và asynchronous execution

Đừng giả định *sau khi phương thức trả về* đồng nghĩa *sau khi công việc thực tế hoàn tất*. Một phương thức trả về đối tượng biểu diễn kết quả trong tương lai có thể trả về ngay, còn thao tác chạy sau. Advice quanh lời gọi đó chỉ quan sát **giai đoạn gọi/đăng ký công việc**, trừ khi cơ chế được thiết kế riêng để quan sát thời điểm hoàn tất asynchronous.

Thông tin theo thread (ví dụ `ThreadLocal`) không tự động trở thành ngữ cảnh nghiệp vụ xuyên suốt mọi luồng thực thi. Chuyển tác vụ sang executor, callback hoặc runtime bất đồng bộ có thể cần chiến lược truyền context, làm sạch và kiểm thử riêng. Đây là giới hạn cần xem xét ở thiết kế observability và tracing.

### 8.6. Hiệu năng và phạm vi ảnh hưởng

Mỗi điểm được can thiệp có thể phát sinh proxy dispatch, matching/binding, đo thời gian, cấp phát, serialization hoặc I/O. Tác động lớn nhất có thể đến từ log và truy xuất hệ thống bên ngoài, không nhất thiết từ bản thân lời gọi advice. Hãy benchmark khi cần, đo ở tải gần thực tế và tránh áp một advice nặng lên hot path.

Pointcut rộng cũng là **phạm vi triển khai rộng**: một thay đổi nhỏ có thể làm nhiều luồng chức năng cùng đổi hành vi. Kiểm thử phạm vi và khả năng truy xuất “tại sao advice chạy ở đây?” là yêu cầu bảo trì, không phải phần trang trí.

### 8.7. Khả năng mở rộng mô hình

Một số công nghệ hỗ trợ *introduction/inter-type declarations*, *join point context binding*, *annotation matching*, hoặc *per-object/per-control-flow aspect lifecycle*. Đây là công cụ nâng cao, nhưng chỉ nên học sau khi nắm vững tính đúng đắn của pointcut, advice và weaving. Chúng làm tăng sức biểu đạt đồng thời làm tăng tải nhận thức và yêu cầu kiểm thử.

**Đầu ra chặng 6:** Với hai aspect, bạn vẽ được thứ tự trước/sau; với một lỗi của target hoặc advice, bạn chỉ ra được caller nhận gì; với tác vụ async, bạn xác định đúng “kết thúc lời gọi” và “kết thúc công việc” khác nhau thế nào.

## 9. Chặng 7 — Chuyển thành ứng dụng có kiểm chứng

### 9.1. Bài tập tổng hợp: đo thời gian và lỗi cho thao tác I/O

**Đề bài:** Một nhóm phương thức I/O đã được đánh dấu cần thu số lần gọi, thời lượng và số lần thất bại. Logic nghiệp vụ không được đổi; phương thức không có marker không được đo. Không ghi dữ liệu nhạy cảm.

Làm theo các bước:

1. **Xác định concern:** Một chính sách quan sát thống nhất; không phải chính sách quyết định dữ liệu hợp lệ.
2. **Xác định target:** Các phương thức I/O phục vụ nghiệp vụ.
3. **Định nghĩa pointcut:** Đánh dấu rõ nhóm điểm cần đo và nhóm loại trừ, đặc biệt code nội bộ của bộ đo.
4. **Thiết kế advice:** Trước lúc gọi lưu thời điểm bắt đầu; khi hoàn tất đo độ trễ, tăng bộ đếm success hoặc failure; exception gốc phải tới caller.
5. **Chọn cơ chế:** Proxy nếu các lời gọi đều đi qua biên interface phù hợp; cân nhắc weaving nếu cần chặn các điểm runtime không qua proxy, và có khả năng quản lý build/class loading.
6. **Thiết lập ngữ nghĩa:** Nếu phương thức trả future/handle, metric là độ trễ tạo tác vụ hay thời gian tác vụ hoàn tất? Chọn và đặt tên rõ.
7. **Kiểm thử:** Có ca được chọn, không được chọn, target ném lỗi, target được gọi trực tiếp, lời gọi nội bộ, nhiều aspect và async nếu ứng dụng có.
8. **Đo và rà soát:** Benchmark trước/sau, kiểm soát sampling/cardinality, kiểm tra rò rỉ dữ liệu và tài liệu hóa phạm vi.
9. **Triển khai có giám sát:** Quan sát tỷ lệ lỗi, độ trễ và khối lượng log/metric sau thay đổi.

### 9.2. Ma trận chọn kỹ thuật

| Nhu cầu | Điểm bắt đầu hợp lý | Khi nào AOP đáng cân nhắc? |
| --- | --- | --- |
| Đo thời gian nhiều phương thức độc lập | Instrumentation ở biên, decorator hoặc helper dùng chung. | Có nhiều join point ổn định, cùng chính sách và cần áp dụng nhất quán. |
| Gắn mã truy vết cho xử lý đầu vào | Interceptor hoặc wrapper tại biên tiếp nhận, truyền context có chủ đích. | Cần mở rộng đến những điểm thực thi xác định, chứng minh được context và phạm vi. |
| Ghi kiểm toán có yêu cầu bền vững | Thiết kế luồng audit, transaction/outbox phù hợp hợp đồng. | AOP chỉ có thể hỗ trợ gắn hook nếu ngữ nghĩa bền vững và bao phủ đã được kiểm chứng. |
| Kiểm tra quyền theo đối tượng dữ liệu | Tầng quyết định quyền và bất biến nghiệp vụ tường minh. | Có thể dùng để bổ trợ một kiểm tra kỹ thuật ở biên; không là bảo vệ duy nhất khi có đường truy cập bỏ qua. |
| Cache kết quả hàm thuần | Memoization/decorator có khóa và quy tắc invalidation rõ. | Nhiều điểm có cùng cache semantics và phương thức không có side effect nguy hiểm. |
| Điều phối nhiều bước nghiệp vụ | Domain service, state machine, workflow/orchestrator. | Thường không dùng AOP để che quyết định trạng thái hoặc bù trừ. |
| Retry thao tác mạng | Retry tại client/boundary với idempotency, timeout và backoff. | Chỉ khi pointcut khớp chính xác tập thao tác có thể retry và hợp đồng được thử nghiệm. |

Chọn công cụ từ **yêu cầu bảo toàn hành vi**, không từ mong muốn áp dụng một mô hình lập trình.

### 9.3. Bài kiểm tra phạm vi và hành vi

Với bất kỳ aspect nào chuẩn bị dùng, phải có tối thiểu:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Điểm thuộc pointcut | Advice chạy đúng số lần, đúng loại và đúng thứ tự đã công bố. |
| Điểm không thuộc pointcut | Không có side effect của advice. |
| Target trả về bình thường | Bên gọi nhận giá trị đúng; advice success xử lý như thiết kế. |
| Target ném exception | Exception đến caller đúng hợp đồng; cleanup chạy. |
| Advice tự gặp lỗi | Hành vi tiếp tục/dừng đã được xác định và có kiểm thử. |
| Gọi trực tiếp target hoặc self-call | Kết quả có/không được can thiệp khớp với cơ chế thực tế; không suy đoán. |
| Có nhiều advice | Thứ tự và ý nghĩa kết quả được kiểm chứng. |
| Có cạnh tranh hoặc async | Context và sự kiện “hoàn tất” được đo đúng mốc. |
| Refactor chữ ký/package/marker | Tập điểm được chọn không tự thay đổi ngoài dự kiến. |

**Đầu ra chặng 7:** Một bài thực hành hoàn chỉnh cần có mô tả chính sách, phương án cơ chế, bảng ca kiểm thử và giải thích vì sao không vi phạm hợp đồng nghiệp vụ.

## 10. Các ngộ nhận thường gặp và cách tự sửa

**“AOP là công cụ tự động thêm log.”** Ghi log chỉ là một ứng dụng. Cốt lõi của AOP là mô hình hóa và kết hợp một hành vi ở nhiều join point theo quy tắc chọn điểm.

**“Gắn marker là chắc chắn advice chạy.”** Marker chỉ là dữ liệu để có thể chọn. Cần có cơ chế AOP thực sự được kích hoạt, điểm được chọn và đường thực thi đi qua can thiệp.

**“Proxy luôn bắt mọi lời gọi của target.”** Sai với các mô hình proxy thông dụng nếu đường gọi bỏ qua proxy hoặc diễn ra nội bộ trong target. Phải vẽ lại đường gọi thực.

**“Before/after không thể ảnh hưởng nghiệp vụ.”** Advice có thể ném lỗi, tiêu tốn tài nguyên, thay đổi ngữ cảnh hoặc làm trễ xử lý. Around còn có thể không gọi hoặc gọi lại target.

**“AOP luôn chậm.”** Overhead tùy cơ chế, nội dung advice và tần suất kích hoạt; quyết định bằng phép đo. Một lời ghi log đồng bộ ở hot path có thể đắt hơn nhiều so với dispatch trung gian.

**“Code ít lặp đi nên thiết kế sẽ tốt.”** Chỉ tốt nếu chính sách thật sự đồng nhất, phạm vi được kiểm soát và người bảo trì có thể truy vết. Ẩn quy tắc nghiệp vụ trong advice làm giảm tính rõ ràng.

**“Test target trực tiếp là đủ.”** Unit test target không chứng minh weaving, matching, precedence và propagation. Cần integration test qua cơ chế chạy thật, cộng negative test xác nhận các điểm không được chọn.

## 11. Tự đánh giá cuối lộ trình

Tự trả lời trước khi xem gợi ý:

1. Một chương trình có 20 phương thức cùng ghi latency. Đó là cơ hội AOP trong điều kiện nào?
2. Một pointcut chọn theo marker. Bạn chứng minh thế nào rằng một phương thức không có marker **không** bị advice tác động?
3. Vì sao `target.foo()` và `proxy.foo()` có thể cho hành vi advice khác nhau?
4. Nếu `around` vô tình gọi phần nghiệp vụ hai lần, các thao tác nào đặc biệt nguy hiểm?
5. Phương thức trả future ngay, nhưng tác vụ chạy thêm năm giây. “After returning” đã đo được toàn bộ thời gian tác vụ chưa?
6. Khi thêm AOP vào kiểm tra quyền, làm cách nào tránh sai lầm cho rằng mọi đường truy cập đã được bảo vệ?
7. Hai advice có thứ tự A ngoài B hoặc B ngoài A. Vì sao kết quả audit/latency có thể khác?

**Gợi ý đối chiếu:**

1. Khi cùng một chính sách quan sát có ý nghĩa nhất quán, tập điểm chọn rõ, có kiểm thử và overhead chấp nhận được.
2. Đặt negative test gọi đúng điểm đó qua cơ chế AOP thật, xác nhận không có side effect; kiểm tra cả marker được tìm ở interface hay implementation.
3. Proxy chỉ can thiệp lời gọi đi qua nó; target trực tiếp không nhất thiết được chặn.
4. Thanh toán, chuyển tiền, ghi dữ liệu không idempotent, gửi sự kiện/thông báo có tác dụng phụ.
5. Chưa, nếu advice chỉ bao quanh lời gọi tạo future; cần instrumentation tại thời điểm future hoàn tất khi mục tiêu là đo toàn bộ tác vụ.
6. Mô hình hóa kiểm tra quyền tại biên tin cậy và bất biến nghiệp vụ; test các tuyến truy cập, không coi pointcut là tuyến bảo vệ duy nhất.
7. Advice bên ngoài quan sát một phạm vi thời gian và trạng thái khác advice bên trong; định nghĩa “thành công” cũng có thể khác trước/sau commit hoặc retry.

## 12. Cách đi tiếp sau bài học

Nếu **chưa phân biệt được join point/pointcut/advice**, quay lại chặng 2 và viết ba ví dụ của riêng mình. Nếu **không dự đoán đúng kết quả Java**, quay lại chặng 4–5 để kiểm tra proxy và lời gọi thực tế. Nếu **chạy demo đúng nhưng chưa biết thiết kế hệ thống**, học tiếp chặng 6–7: exception, thứ tự advice, context bất đồng bộ, phạm vi và benchmark.

Một người đã nắm vững AOP có thể giải thích được cả **nơi advice sẽ chạy, nơi nó không chạy và vì sao**. Đó là bước chuyển quan trọng từ ghi nhớ thuật ngữ sang hiểu cơ chế và ứng dụng có kiểm soát.
