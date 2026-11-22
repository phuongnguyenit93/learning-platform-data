# Phụ thuộc ẩn giữa mã nghiệp vụ với cấu hình pointcut trong Aspect-Oriented Programming (AOP)

## 1. Vấn đề kiến trúc: mã không gọi advice nhưng vẫn phụ thuộc vào advice

**Aspect-Oriented Programming (AOP)** tách các mối quan tâm cắt ngang như logging, metrics, tracing, transaction, retry, audit và kiểm soát truy cập khỏi thân phương thức nghiệp vụ. Một **pointcut** xác định tập *join point* được chọn; **advice** thêm hành vi tại những điểm ấy; cơ chế **weaving**, instrumentation hoặc proxy kết nối advice với mã chạy thật.

Điểm dễ bị bỏ qua là **phụ thuộc vẫn tồn tại dù không có lời gọi trực tiếp trong source code**. Một phương thức có thể hoạt động đúng chỉ khi advice quanh nó thực hiện một việc ngầm định: mở transaction, lưu audit event, truyền context, kiểm tra quyền, biến đổi lỗi, đo thời gian hay retry. Nếu pointcut ngừng khớp sau lần đổi tên/package/chữ ký, phương thức vẫn có thể biên dịch và các unit test trực tiếp vẫn chạy, nhưng hợp đồng vận hành hoặc an toàn đã bị phá vỡ.

Đây là **phụ thuộc ẩn giữa mã nghiệp vụ và cấu hình pointcut**: cấu hình chọn join point dựa trên cấu trúc chương trình, trong khi hành vi thực tế của chương trình phụ thuộc ngược lại vào cấu hình đó. Compiler thường không kiểm tra được toàn bộ mối quan hệ này, nhất là với biểu thức chọn điểm ở runtime, file cấu hình hoặc metadata được đọc khi khởi động.

Ví dụ:

~~~text
Ý định: mọi thao tác thay đổi trạng thái đơn hàng phải có audit.

Pointcut: tên phương thức bắt đầu bằng "submit".
Ban đầu: submitOrder(...) được chọn -> audit chạy.
Refactor: đổi thành placeOrder(...) -> nghiệp vụ vẫn chạy.
Hệ quả: pointcut không còn chọn phương thức -> audit mất âm thầm.
~~~

Sai sót này không nhất thiết hiện ra bằng một exception. Đặc biệt nguy hiểm khi advice là một phần của ranh giới bảo mật, transaction hoặc cơ chế bảo đảm tính nhất quán.

**Mục tiêu:** hiểu chính xác phụ thuộc ẩn hình thành thế nào; phân loại rủi ro khi refactor; dùng một thiết kế khai báo chính sách rõ ràng và các phép kiểm tra tự động để phát hiện mất/nhân đôi advice; phân biệt những gì AOP thật sự bảo đảm với những gì kiến trúc vẫn phải bảo vệ ở boundary nghiệp vụ.

## 2. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Liên quan tới phụ thuộc ẩn |
| --- | --- | --- |
| Join point | Điểm mà cơ chế AOP hỗ trợ can thiệp, chẳng hạn lời gọi hoặc thực thi phương thức | Nếu đường chạy không đi qua join point được chọn, advice không có tác dụng |
| Pointcut | Điều kiện nhận diện join point: tên, kiểu, package, annotation, chữ ký, context... | Có thể phụ thuộc vào cách đặt tên hoặc tổ chức mã thay vì ý nghĩa nghiệp vụ |
| Advice | Hành vi trước/sau/quanh join point, khi trả kết quả hoặc ném lỗi | Thay đổi đặc tính quan sát, an toàn hoặc semantics của lời gọi |
| Weaving / proxy | Cơ chế gắn advice vào execution | Quyết định những lời gọi nào có thể bị chặn trên thực tế |
| Cross-cutting contract | Cam kết áp dụng cho nhiều thao tác, như “mọi lệnh ghi phải được audit” | Hợp đồng có thể không hiện diện trong chữ ký phương thức |
| Pointcut coverage | Phần giao giữa tập join point **cần** áp dụng và tập join point **thực tế** được chọn | Mất coverage hoặc chọn thừa đều là lỗi kiến trúc |

**Pointcut không phải policy nghiệp vụ.** Một biểu thức “mọi phương thức bắt đầu bằng `save`” là cách chọn code theo hình dạng. Nó không bảo đảm mọi thao tác có side effect đều nằm trong tập đó. Ngược lại, tên `savePreview` chưa chắc đại diện cho một hành động ghi trạng thái quan trọng.

Điểm quan trọng hơn: **“method được chọn” khác “advice đã chạy cho đúng đường nghiệp vụ”**. Một pointcut có thể khớp một phương thức trên lý thuyết nhưng đường gọi thực tế đi trực tiếp vào target, đi qua lớp khác, chạy trên thread callback hoặc không đi qua proxy. Cần kiểm tra cả tập khớp và đường thực thi thật.

## 3. Hai chiều của phụ thuộc và chiều thứ ba giữa các aspect

### 3.1 Aspect phụ thuộc vào cấu trúc mã nghiệp vụ

Một pointcut thường biểu diễn các điều kiện kiểu:

~~~text
execution(package.orders.*.submit*(..))
annotation(Audited)
within(package.services.*)
method_signature = (name, parameter_types, declaring_type)
~~~

Đây là **biểu thức khái niệm** để diễn đạt các kiểu lựa chọn, không phải cú pháp chung do mọi engine AOP đều hỗ trợ. Nếu đổi `package.orders` thành `package.checkout` hoặc `submitOrder` thành `placeOrder`, việc chọn có thể thay đổi dù logic bên trong không đổi.

Điều này là coupling từ cấu hình aspect tới *hình dạng* codebase: cấu hình cần biết package, modifier, khai báo method hoặc metadata nào tồn tại.

### 3.2 Mã nghiệp vụ phụ thuộc vào tác dụng của advice

Ví dụ phương thức gọi repository giả định transaction đã được mở bởi advice. Nếu bị gọi trực tiếp mà không qua cơ chế AOP, kết quả có thể khác, side effect không được rollback hoặc kiểm soát truy cập bị bỏ qua. Đây là coupling theo chiều ngược lại: mã nghiệp vụ không import aspect, nhưng hành vi đúng của nó lại trông chờ side effect từ aspect.

Cần phân biệt **hỗ trợ quan sát** và **bất biến bắt buộc**:

- Mất một phép đo latency có thể làm giảm khả năng chẩn đoán nhưng không nhất thiết làm thay đổi kết quả nghiệp vụ.
- Mất audit bắt buộc, kiểm tra quyền, transaction hoặc ràng buộc nhất quán có thể là lỗi nghiêm trọng.
- Retry advice có thể làm tăng số lần chạy mã gốc và side effect; nếu nghiệp vụ ngầm trông đợi retry, đó là một phụ thuộc dễ bị bỏ sót.
- Một exception translator có thể làm caller kỳ vọng loại lỗi khác với loại mà phương thức gốc ném ra.

**Không nên biến một hiệu ứng ngầm thành điều kiện an toàn duy nhất nếu kiến trúc còn các đường truy cập không được bảo vệ.** Đối với ranh giới quan trọng, cần một điểm cưỡng chế thống nhất và/hoặc kiểm soát bổ sung tại tầng sở hữu dữ liệu/tài nguyên.

### 3.3 Các aspect phụ thuộc vào thứ tự nhau

Giả sử cùng join point có:

- Authorization advice.
- Transaction advice.
- Retry advice.
- Audit advice.
- Metrics advice.

Thứ tự có thể quyết định việc kiểm tra quyền diễn ra trước hay sau side effect, mỗi lần retry có transaction riêng hay dùng chung, audit đếm một request logic hay từng attempt, metrics đo thời gian nghiệp vụ hay cả retry, và exception nào được quan sát.

Ví dụ ý tưởng:

~~~text
Metrics(Retry(Transaction(Operation)))
  -> metrics đo cả thời gian retry.

Retry(Metrics(Transaction(Operation)))
  -> metrics có thể ghi từng attempt bên trong retry.
~~~

Không có một thứ tự mặc định đúng cho mọi bài toán. Nhưng **thứ tự là một phần của hợp đồng thực thi**, phải được khai báo, kiểm tra và đưa vào test tích hợp. Nếu chỉ đổi ưu tiên aspect mà dashboard thay đổi đơn vị đếm, hệ thống đã thay đổi semantics của phép đo dù mã nghiệp vụ vẫn như cũ.

## 4. Cách pointcut trở nên giòn khi mã được refactor

### 4.1 Đổi tên phương thức

Pointcut dùng `get*`, `save*`, `delete*`, `submit*` có thể mất match khi đổi động từ, dùng alias hoặc gom API. Tên cũng có thể mang ý nghĩa khác với hành vi thật. **Không dùng prefix tên method làm nguồn quyết định quyền truy cập hoặc transaction bắt buộc.**

### 4.2 Đổi package hoặc chuyển lớp

Pointcut giới hạn `within(com.company.orders..*)` có thể bỏ sót phương thức khi di chuyển nó sang module mới. Ngược lại, thêm một utility class vào package được chọn có thể khiến advice bắt cả code không dự kiến.

### 4.3 Đổi chữ ký, overload hoặc generic

Thay `save(String id)` bằng `save(OrderId id)`, thêm tham số context, overload method, hoặc tạo bridge method do generic có thể thay đổi cách engine nhận diện chữ ký. Java reflection trên interface có thể thấy annotation khác với reflection trên implementation. Không suy ra từ một method name rằng mọi overload có cùng chính sách.

### 4.4 Đổi visibility, phương thức static/final và cơ chế weaving

Khả năng chặn method `private`, `final`, `static`, constructor, field access, self-invocation hoặc lời gọi trực tiếp phụ thuộc engine và cách gắn advice. Một cơ chế dùng proxy interface sẽ có khả năng khác cơ chế weaving bytecode. Không ghi kết luận “AOP luôn chặn mọi lời gọi” hoặc “AOP luôn bỏ qua mọi phương thức nội bộ” mà không xác nhận công nghệ đang dùng.

### 4.5 Chuyển đồng bộ sang bất đồng bộ

Trước refactor, phương thức trả kết quả sau khi hoàn thành công việc. Sau refactor, nó trả `CompletionStage` hoặc publisher gần như ngay lập tức. Advice quanh lời gọi cũ giờ chỉ nhìn thấy lúc **trả đối tượng biểu diễn tác vụ**, chưa phải lúc tác vụ hoàn tất.

Hệ quả có thể là transaction đóng trước khi background task thao tác dữ liệu, metrics báo success quá sớm, hoặc authorization context không còn hiện diện khi callback dùng tài nguyên. Nếu chính sách cần theo dõi vòng đời async, phải chọn rõ join point của completion, subscription, terminal và cancellation, đồng thời quản lý context.

### 4.6 Thay đổi đường gọi và bypass

Một lớp ban đầu chỉ được gọi qua proxy nhưng sau refactor lại được tạo trực tiếp bằng `new`, hoặc code nội bộ gọi `this.operation()`, có thể đi vòng điểm chặn. Test chỉ gọi trực tiếp vào implementation sẽ không xác nhận AOP hoạt động. Phải dùng đúng entrypoint mà production gọi và kiểm tra thêm đường bypass có thể xảy ra.

## 5. Phân biệt thiếu coverage và chọn thừa

Gọi:

- `R` là tập join point **bắt buộc** phải áp dụng một chính sách.
- `M` là tập join point **được pointcut chọn** trong runtime/biên dịch thực tế.

Khi đó:

- **False negative:** phần thuộc `R` nhưng không thuộc `M`. Ví dụ thao tác ghi không được audit.
- **False positive:** phần thuộc `M` nhưng không thuộc `R`. Ví dụ pointcut mở transaction cho một hàm chuyển đổi dữ liệu thuần túy.
- **Đúng mục tiêu:** phần giao `R ∩ M`, nhưng vẫn cần kiểm tra thời điểm và thứ tự chạy advice.

Có thể minh họa:

~~~text
Bắt buộc bảo vệ R:  [submit] [place] [cancel]
Pointcut hiện tại M: [submit] [status] [helper]

Thiếu: [place] [cancel]
Chọn thừa: [status] [helper]
~~~

False positive cũng có hại: đo lặp, tăng CPU, log dữ liệu nhạy cảm, mở transaction không cần thiết, đổi loại exception hoặc khiến chức năng bị từ chối sai. Một điểm cắt rất rộng **không bảo đảm an toàn hơn** nếu nó thay đổi semantics ngoài dự kiến.

Với chính sách bảo mật, không nên dựa vào việc “không có lỗi trong log” để suy ra coverage đủ: **một advice không bao giờ chạy sẽ không tự ghi log rằng mình đã bị bỏ qua**.

## 6. Ví dụ Java 17+ độc lập: lỗi do pointcut theo tên

Ví dụ dùng **JDK dynamic proxy** để minh họa một điểm cắt theo tên và một điểm cắt có khai báo tường minh. Hai method `submit` và `place` đều là thao tác nghiệp vụ có yêu cầu audit. Pointcut theo tên chỉ bắt `submit`, nên `place` chạy mà mất audit; phiên bản dùng `@Audited` chọn cả hai theo metadata đã khai báo.

**Tệp: `PointcutCouplingDemo.java`**

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.function.Predicate;

public class PointcutCouplingDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Audited {}

    public interface Orders {
        @Audited
        String submit(String id);

        @Audited
        String place(String id);

        String status(String id);
    }

    public static final class OrdersImpl implements Orders {
        @Override
        public String submit(String id) {
            return "saved " + id;
        }

        @Override
        public String place(String id) {
            return "saved " + id;
        }

        @Override
        public String status(String id) {
            return "status " + id;
        }
    }

    static Orders decorate(Orders target, Predicate<Method> pointcut) {
        InvocationHandler handler = (proxy, method, args) -> {
            if (method.getDeclaringClass() != Object.class
                    && pointcut.test(method)) {
                System.out.println("audit " + method.getName());
            }

            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException ex) {
                // Giữ nguyên nguyên nhân lỗi nghiệp vụ.
                throw ex.getCause();
            }
        };

        return (Orders) Proxy.newProxyInstance(
            Orders.class.getClassLoader(),
            new Class<?>[] { Orders.class },
            handler
        );
    }

    public static void main(String[] args) {
        Orders target = new OrdersImpl();

        Orders byName = decorate(
            target, method -> method.getName().startsWith("submit")
        );
        System.out.println("-- name-based pointcut --");
        System.out.println(byName.submit("A"));
        System.out.println(byName.place("B"));

        Orders byContract = decorate(
            target, method -> method.isAnnotationPresent(Audited.class)
        );
        System.out.println("-- explicit annotation --");
        System.out.println(byContract.submit("C"));
        System.out.println(byContract.place("D"));
        System.out.println(byContract.status("E"));
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac PointcutCouplingDemo.java
java PointcutCouplingDemo
~~~

**Stdout xác định:**

~~~text
-- name-based pointcut --
audit submit
saved A
saved B
-- explicit annotation --
audit submit
saved C
audit place
saved D
status E
~~~

Đọc kết quả:

1. `byName.submit("A")` in `audit submit` trước `saved A` vì phương thức có tên khớp prefix.
2. `byName.place("B")` vẫn thực thi business code và trả `saved B` nhưng không có audit; đây là **mất hành vi ngầm** mà việc nhìn giá trị trả về không phát hiện được.
3. `byContract.submit("C")` và `byContract.place("D")` đều có `@Audited` trên **method của interface**, do đó proxy nhận metadata và ghi audit.
4. `status("E")` không có annotation và không được audit theo chính sách minh họa.

Cần hiểu đúng giá trị của annotation: **khai báo tường minh giúp phản ánh ý định**, nhưng **không tự bảo đảm đầy đủ**. Nếu thêm phương thức ghi mới rồi quên `@Audited`, phiên bản annotation cũng có thể bỏ sót. Muốn bảo đảm mọi operation bắt buộc phải được bảo vệ, phải có danh sách chính sách chuẩn và bài kiểm tra đối chiếu coverage. Với việc kiểm soát quyền, “không có annotation” ở ranh giới cần bảo vệ phải dẫn tới **từ chối hoặc lỗi cấu hình**, thay vì “cho phép vì không thấy rule”.

**Giới hạn của mẫu:** `decorate` tạo một proxy trên interface. Nó chỉ áp dụng advice cho lời gọi đi qua proxy đó; gọi `target.place("B")` trực tiếp sẽ không qua advice. Annotation được đặt trên interface vì `Method` mà JDK proxy cung cấp cho handler mô tả phương thức interface. Cơ chế AOP khác có thể lấy metadata từ implementation và có quy tắc kế thừa riêng. Ví dụ in audit trên console nhằm dễ kiểm chứng; hệ production cần audit sink có bảo đảm độ bền, điều kiện thất bại và chính sách bảo vệ dữ liệu phù hợp.

## 7. Biến phụ thuộc ẩn thành hợp đồng có thể kiểm tra

### 7.1 Định nghĩa danh mục các operation cần áp chính sách

Thay vì để một regex âm thầm quyết định tác vụ nào quan trọng, lập một **operation catalog** hoặc manifest:

~~~yaml
operations:
  orders.submit:
    audit: required
    authorization: order.write
    transaction: required
  orders.place:
    audit: required
    authorization: order.write
    transaction: required
  orders.status:
    audit: optional
    authorization: order.read
    transaction: none
~~~

Đây là **YAML minh họa kiến trúc**, không phải file cấu hình của một engine cụ thể. Mỗi operation có ID nghiệp vụ ổn định và yêu cầu chính sách rõ. Một lớp ánh xạ từ chữ ký method hoặc annotation sang operation ID phải được xác minh, đặc biệt khi đổi tên/refactor.

Manifest có thể được dùng trong bài kiểm tra khởi động hoặc build để so sánh:

- Operation nào bắt buộc có audit, authorization, transaction?
- Pointcut runtime hiện chọn những join point nào?
- Có operation bị bỏ sót, chọn thừa, trùng policy hoặc thiếu mapping không?
- Có method mới cần phân loại mà chưa có mục trong manifest không?

Khi câu trả lời không đúng, phát cảnh báo **có thể kiểm chứng** hoặc dừng khởi động đối với invariant bắt buộc. Không chỉ in một thông báo rồi để hệ thống bảo mật vận hành trong trạng thái mơ hồ.

### 7.2 Annotation với nội dung giàu ngữ nghĩa

Annotation tường minh như `@RequiresPermission("order.write")` hoặc `@Audited(category = "order")` bền hơn phụ thuộc vào prefix tên, vì nó mang **ý định** sang gần code nghiệp vụ. Tuy vậy:

- Không dùng annotation như bằng chứng người gọi đã có quyền; advice phải kiểm tra principal, action, resource và context với dữ liệu tin cậy.
- Cần quy định annotation đặt trên interface, implementation hay cả hai; kiểm tra inheritance, overload, generic bridge và default method theo công cụ thực tế.
- Annotation ở sai vị trí hoặc không được công cụ đọc có thể vẫn tạo miss. Test coverage phải dùng đường gọi thực.
- Một operation chuyển ý nghĩa từ “chỉ đọc” sang “cập nhật” cần thay policy ngay cả khi annotation vẫn còn.
- Nhiều annotation có thứ tự tương tác: authorization, retry, transaction, audit phải có hợp đồng thực thi rõ.

### 7.3 Biên cưỡng chế chính sách rõ ràng

Với thao tác cần **bảo đảm an toàn**, không nên chỉ dựa vào một matcher động không được kiểm thử. Kiến trúc có thể lựa chọn:

- Một cổng xử lý lệnh (`command boundary`) bắt buộc đưa mọi lệnh ghi qua middleware có policy rõ.
- Một interface truy cập tài nguyên được bao bọc và không tiết lộ đối tượng gốc cho caller không tin cậy.
- Kiểm tra quyền và ràng buộc nhất quán tại nơi thực sự ghi dữ liệu, transaction hoặc kho tài nguyên.
- Build-time weaving kết hợp kiểm tra điểm cắt và kiểm tra end-to-end; cần xác nhận kiểu join point thực tế chứ không suy từ tên công nghệ.

Các lựa chọn này có mục tiêu chung là **người sửa code nhìn thấy hợp đồng cần giữ** và **đường bypass bị giới hạn, phát hiện hoặc chặn**.

## 8. Kiểm soát thay đổi pointcut như một thay đổi hành vi

Một thay đổi cấu hình pointcut có thể có tác động tương đương sửa code nghiệp vụ. Review cần trả lời:

| Loại thay đổi | Nguy cơ | Kiểm tra đề xuất |
| --- | --- | --- |
| Đổi tên method | Mất match hoặc thêm match do prefix | Diff tập join point trước/sau |
| Chuyển package | Mất matcher theo package | Test coverage/operation catalog |
| Thêm overload | Matcher chọn thêm hoặc bỏ một chữ ký | Kiểm tra signature chính xác |
| Di chuyển annotation | Runtime không đọc được metadata | Kiểm tra annotation resolution trên đường gọi thật |
| Thay interface/implementation | Proxy không còn chặn lời gọi dự định | Integration test qua entrypoint production |
| Đổi advice order | Metrics, retry, transaction, authorization đổi semantics | Test hợp đồng kết quả và thứ tự side effect |
| Chuyển sang async | Advice kết thúc trước công việc | Test completion, lỗi, hủy và context propagation |
| Mở rộng wildcard | Instrument utility/hạ tầng, recursion hoặc overhead | So sánh tập chọn và performance test |
| Thay wiring hoặc tạo target trực tiếp | Bypass advice | Test từ đầu vào đến điểm sử dụng resource |

Nếu công cụ AOP hỗ trợ liệt kê match, xuất danh sách đó vào CI và so sánh với tập kỳ vọng. Nếu không, viết phép thử chạy một đường đại diện cho từng operation và dùng một **fake advice/probe** xác nhận số lần kích hoạt, thứ tự và dữ liệu join point. Cần test âm tính để chứng minh operation ngoài scope không bị can thiệp.

**Kiểm thử unit trực tiếp vào target chưa đủ.** Nó xác minh logic gốc, nhưng không xác minh weaving, proxy wiring, pointcut, thứ tự aspect, context hay exception translation. Ít nhất một lớp integration test phải gọi từ boundary thật.

## 9. Thiết kế test đặc biệt cho phụ thuộc ẩn

### 9.1 Bất biến về coverage

Đối với mỗi operation bắt buộc audit:

1. Khi được gọi qua entrypoint hợp lệ, audit advice phải chạy đúng số lần theo hợp đồng.
2. Khi code bị đổi tên hoặc thay chữ ký nhưng vẫn cùng operation ID, yêu cầu audit vẫn còn.
3. Một operation ngoài phạm vi không nhận audit ngoài ý muốn.
4. Khi thiếu binding bắt buộc, test hoặc khởi động phải báo lỗi thay vì bỏ qua im lặng.

Đối với authorization, bổ sung kiểm tra rằng bị từ chối thì **thao tác gốc không được chạy**, thông tin từ chối không làm lộ dữ liệu riêng và mọi đường gọi tài nguyên nhạy cảm đều được bảo vệ.

### 9.2 Bất biến về thứ tự và side effect

Với phối hợp authorization–transaction–retry–audit, dùng probe ghi trình tự các sự kiện. Chẳng hạn:

~~~text
auth-check
transaction-begin
business-start
business-end
transaction-commit
audit-record
~~~

Thứ tự trên chỉ là **một hợp đồng minh họa**, không phải quy tắc phổ quát. Khi đổi thứ tự aspect, test phải đánh giá quy tắc nghiệp vụ thực: authorization cần chạy trước side effect; audit có thể phải gắn với mỗi attempt hoặc kết quả commit tùy yêu cầu; transaction có thể bao quanh từng attempt hay toàn hoạt động. Quan trọng là test **có kỳ vọng tường minh**.

### 9.3 Bất biến về đường bypass

- Tạo đối tượng qua cơ chế wiring thông thường và xác nhận lời gọi được chặn.
- Thử tham chiếu trực tiếp vào target nếu kiến trúc có thể tạo ra nó; test phải phát hiện hoặc ràng buộc quyền truy cập.
- Thử self-invocation, callback, background job, reflection hoặc API đi vào từ đường khác nếu chúng thực sự có trong ứng dụng.
- Với multiple classloaders hoặc dynamic proxy, kiểm tra đúng interface/class và classloader cần áp dụng.
- Thử exception, cancellation và các đường kết thúc sớm: advice có phát side effect thiếu hoặc nhân đôi không?

### 9.4 Khi refactor

Lập test mang tính *refactoring regression*: đổi tên một method giả lập, đổi package, thêm overload hoặc chuyển API sync sang async trong nhánh thử nghiệm, rồi quan sát coverage và hợp đồng điều khiển. Nếu pointcut không còn khớp thì test phải thất bại rõ ràng. Đây là cách hữu ích để phát hiện những phụ thuộc mà compiler thông thường không nhìn thấy.

## 10. Thứ tự thực thi: vì sao phụ thuộc dễ sinh lỗi ngầm?

Giả sử có quanh cùng một thao tác:

~~~text
Authorization -> Retry -> Transaction -> Business
~~~

Nếu retry bên ngoài transaction, mỗi attempt có thể có transaction riêng. Nếu transaction ở ngoài retry, nhiều attempt có thể nằm trong một transaction, dẫn tới semantics rollback và lock khác. Nếu metrics nằm ngoài retry, nó đo latency tổng thể; nếu metrics nằm trong, nó đo mỗi attempt.

Những điều cần được nêu rõ trong tài liệu kiến trúc:

- Advice nào được phép *không gọi* thao tác gốc? Ví dụ authorization từ chối hoặc cache hit.
- Advice nào được phép gọi lại thao tác gốc? Retry có giới hạn và chỉ khi nghiệp vụ idempotent hoặc đã giải quyết side effect.
- Exception nào được chuyển đổi? Caller mong đợi loại lỗi nào?
- Điểm bắt đầu/kết thúc một transaction hoặc một phép đo là gì?
- Mỗi attempt và mỗi logical request có cùng policy không?
- Việc thay đổi thứ tự aspect có cần đánh giá migration và cập nhật dashboard/test không?

Một hệ thống có thể chạy “không lỗi” nhưng báo số liệu sai sau thay đổi: ban đầu metrics đếm một request logic, sau đó đếm từng retry attempt. Đây cũng là lỗi do phụ thuộc ẩn, dù không có exception.

## 11. AOP và tác vụ bất đồng bộ: nơi coupling dễ bị bỏ sót

Khi một method `process()` đổi từ:

~~~java
Result process(Command command);
~~~

thành:

~~~java
CompletionStage<Result> process(Command command);
~~~

các chữ ký trên là **minh họa API**, không phải chương trình độc lập. Nếu advice vẫn ghi nhận success trong `after returning`, nó chỉ biết method đã trả về stage. Stage đó có thể thất bại sau vài giây.

Với một publisher sự kiện, lời gọi tạo publisher khác với `subscribe`, từng `onNext`, terminal signal và `cancel`. Một method có thể tạo publisher nhưng chưa thực thi nghiệp vụ trước khi có subscriber. Vì thế:

- Tracing/metrics cần quyết định đo lời gọi tạo đối tượng, hoàn tất của stage, hay vòng đời subscription.
- Transaction/session/resource context không được giả định tự kéo dài qua callback và thread khác.
- Authorization có thể cần thực thi lại tại thời điểm truy cập tài nguyên nếu quyền có thể thay đổi.
- Advice quan sát stream phải bảo toàn `request(n)`, thứ tự, error và cancellation; không tạo subscription phụ hoặc queue không giới hạn.
- Một context nằm trong `ThreadLocal` ở thread gọi không tự lan qua executor; cần propagation tường minh và đóng scope đúng vòng đời.

Không có một cơ chế advice chung tự bảo đảm tất cả semantics này. **Chuyển từ sync sang async là thay đổi hợp đồng**, phải review pointcut và vòng đời của các aspect liên quan.

## 12. Những mức độ phụ thuộc và cách ứng xử

| Mức | Ví dụ | Yêu cầu khi thiếu advice |
| --- | --- | --- |
| Quan sát tùy chọn | Đo thời gian phục vụ dashboard | Ứng dụng có thể tiếp tục; phát hiện thiếu telemetry qua coverage/health |
| Quan sát cần tuân thủ | Audit lệnh ghi bắt buộc | Phải có policy fail-closed hoặc kiểm soát bổ sung đã được duyệt |
| Kiểm soát truy cập | Kiểm tra subject/action/resource/context | Không cho phép thao tác không được xác minh quyền |
| Tính nhất quán dữ liệu | Transaction/lock/atomicity | Bảo vệ tại biên dữ liệu hoặc đảm bảo mọi đường đều qua enforcement |
| Điều khiển tải | Rate limit/concurrency limit | Mọi entrypoint liên quan phải chịu cùng chính sách, gồm retry và async |
| Thay đổi semantics | Caching, retry, exception translation | Test giá trị, side effect, lỗi và retry contract |

Đừng dùng một tiêu chí chung “có logging là ổn” cho cả những hành vi bắt buộc và tùy chọn. Mỗi phụ thuộc cần **mức độ bảo đảm** tương ứng: review, test coverage, runtime assertion, hoặc bảo vệ bổ sung tại resource boundary.

## 13. Định nghĩa chính xác metadata và trách nhiệm ownership

Một cách hạn chế coupling là phân chia rõ:

- **Nhóm nghiệp vụ sở hữu ý nghĩa operation:** một lệnh là đọc, ghi, publish, thanh toán hay hành động nhạy cảm.
- **Nhóm platform/AOP sở hữu cơ chế thực thi:** pointcut, wiring, propagation, logging, đo và kết hợp advice.
- **Nhóm policy/bảo mật sở hữu quy tắc cho phép hoặc yêu cầu audit:** action, subject/resource, thời điểm kiểm tra, trường hợp ngoại lệ.

Mỗi thay đổi operation phải đi kèm kiểm tra policy mapping. Nếu có thể, tự động hóa bằng một danh mục method đã đăng ký so với manifest. Những key ổn định theo nghiệp vụ (ví dụ `order.place`) giúp giảm phụ thuộc vào cấu trúc source code, nhưng chúng cũng phải được version hóa và không được dùng như bằng chứng cấp quyền.

Khi đổi cấu hình điểm cắt, cần có thông tin **trước/sau**: số join point được match, danh sách mới và mất, số lời gọi advice khi chạy workload đại diện, cùng ảnh hưởng hiệu năng. Review “đổi một dòng regex” vẫn cần nghiêm túc nếu dòng đó chọn hàng nghìn điểm thực thi.

## 14. Chọn pointcut như thế nào cho bền vững?

Không có một biểu thức duy nhất phù hợp mọi hệ thống. Một số phương án:

**Theo tên/signature:** nhanh, ít annotation, hữu ích cho các quy ước mang tính quan sát nhẹ; dễ bị refactor làm drift. Dùng khi có test kiểm tra danh sách khớp và hậu quả bỏ sót không nguy hiểm.

**Theo package/class:** thuận tiện nếu module thực sự trùng với boundary cần áp dụng; có thể chọn thừa khi module chứa hạ tầng hoặc bỏ sót khi di chuyển class.

**Theo annotation/metadata khai báo:** thể hiện ý định gần code, giảm nhầm lẫn do tên; cần kiểm tra coverage, vị trí annotation, inheritance và thay đổi semantics.

**Theo manifest/operation registry:** khai báo chính sách tập trung, có thể kiểm tra đầy đủ; đòi hỏi giữ mapping luôn cập nhật và giải quyết mâu thuẫn giữa registry với code.

**Theo boundary kiến trúc:** middleware hoặc cổng xử lý lệnh không cho caller đi vòng, dễ gắn invariant; có thể cần điều chỉnh thiết kế module và phân quyền truy cập target. Kết hợp với kiểm soát ở data layer khi policy yêu cầu bảo đảm mạnh.

Một chiến lược tốt là dùng **pointcut để áp dụng một hợp đồng được khai báo**, sau đó dùng CI/integration test để chứng minh mọi đường quan trọng đã đi qua hợp đồng ấy. Cần cho phép các operation công khai thực sự bằng chính sách công khai **tường minh** thay vì “không match thì tự được phép”.

## 15. Các lỗi thường gặp

**“Mã không import aspect, nên hai phần độc lập.”** Phụ thuộc runtime vẫn hiện diện nếu thiếu advice làm mất audit, transaction, quyền hoặc semantics cần thiết.

**“Refactor đổi tên method mà compile được là an toàn.”** Compiler thường không biết biểu thức pointcut động và hợp đồng chọn join point. Cần kiểm tra coverage sau refactor.

**“Dùng wildcard rộng sẽ không bao giờ bỏ sót.”** Wildcard rộng có thể bắt thêm join point ngoài ý muốn, tạo recursion, đếm lặp, overhead hoặc side effect sai.

**“Thêm annotation nghĩa là đã an toàn tuyệt đối.”** Annotation có thể bị quên, đặt sai vị trí, thay đổi semantics hoặc không được engine nhìn thấy. Đặc biệt, annotation yêu cầu quyền chưa chứng minh người gọi được phép.

**“Unit test gọi implementation trực tiếp đã xác minh AOP.”** Nó thường bỏ qua chính điểm cần kiểm chứng: proxy/weaving, pointcut và thứ tự advice.

**“Advice around đã chạy nên nghiệp vụ chắc chắn được gọi một lần.”** Một around advice có thể bỏ qua hoặc gọi lại `proceed` tùy thiết kế; phải kiểm tra semantics của từng loại policy.

**“Nếu advice fail thì bỏ qua để ứng dụng tiếp tục là an toàn.”** Với telemetry tùy chọn có thể chấp nhận theo chính sách; với authorization hoặc audit bắt buộc, bỏ qua có thể mở lỗ hổng.

**“Chuyển method sang async không ảnh hưởng aspect.”** Lifecycle, thời gian đo, transaction, resource và context có thể thay đổi lớn khi method chỉ trả một handle của tác vụ chưa kết thúc.

**“Hai aspect đều đúng thì thứ tự nào cũng đúng.”** Retry–transaction–audit–metrics có thể cho kết quả khác nhau khi thay thứ tự.

## 16. Quy trình làm việc để kiểm soát coupling

1. **Lập danh mục hành vi cắt ngang:** phân loại audit, authorization, transaction, retry, metrics, tracing và hành vi nào bắt buộc.
2. **Viết tập operation cần áp dụng:** xác định một nguồn kỳ vọng có thể kiểm chứng như annotation/manifest/boundary rõ ràng.
3. **Đo tập join point thực sự được chọn:** ở build/startup hoặc trong một bài test tích hợp; so sánh với tập kỳ vọng.
4. **Bổ sung negative tests:** chứng minh operation ngoài phạm vi không bị chặn sai và yêu cầu thiếu binding bắt buộc bị từ chối.
5. **Kiểm tra đường gọi production:** không chỉ gọi target trực tiếp; xem self-invocation, factory, callback, reflection và job nền nếu có.
6. **Kiểm tra thứ tự và lifecycle:** test retry, exception, transaction, cancellation, completion và context async khi liên quan.
7. **Review refactor và cấu hình cùng nhau:** đổi package/tên/chữ ký, thêm overload, đổi wiring hoặc advice order đều cần cập nhật contract.
8. **Theo dõi runtime:** đếm advice invocation và so với operation thực tế ở tầng biên; cảnh báo biến mất bất thường, nhưng không thay thế coverage test.
9. **Giữ bảo vệ ở boundary quan trọng:** dữ liệu/quan hệ sở hữu/điều kiện nhất quán không được dựa duy nhất vào một matcher có thể bị bypass.

## 17. Kết luận

AOP tách mã cắt ngang ra khỏi thân nghiệp vụ, nhưng **không xóa phụ thuộc** giữa chúng. Điểm phụ thuộc chuyển sang *pointcut*, cơ chế gắn advice, thứ tự thực thi và vòng đời của các tác vụ. Khi mã được đổi tên, di chuyển, tạo overload, thay kiểu gọi hoặc chuyển sang bất đồng bộ, một aspect có thể mất tác dụng mà code vẫn biên dịch và kết quả đơn giản vẫn trông đúng. Thiết kế bền vững đòi hỏi **policy tường minh, coverage có thể kiểm tra, test đường gọi thực và bảo vệ bổ sung tại boundary có rủi ro cao**.