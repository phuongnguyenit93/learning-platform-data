# Lợi ích, đánh đổi và những bài toán không nên dùng AOP

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Nhận ra một *cross-cutting concern* (mối quan tâm xuyên suốt) và giải thích vì sao AOP có thể giúp xử lý nó.
- Cân nhắc lợi ích về tổ chức mã nguồn, tính nhất quán và khả năng thay đổi chính sách so với chi phí về luồng chạy, kiểm thử, hiệu năng và độ tin cậy.
- Phân biệt một chính sách kỹ thuật phù hợp với AOP và một quy tắc nghiệp vụ cần xuất hiện tường minh trong mã.
- Lựa chọn có cơ sở giữa AOP, lời gọi trực tiếp, decorator, interceptor và các cơ chế có biên rõ ràng khác.

## 1. Đặt AOP đúng vị trí

**Aspect-Oriented Programming (AOP)** giúp tập trung chính sách dùng chung xuất hiện ở nhiều điểm của chương trình, nhằm giảm mã phân tán (*scattering*) và trách nhiệm đan xen với nghiệp vụ (*tangling*). Chẳng hạn, bộ đo thời gian có thể chọn một nhóm thao tác rồi ghi độ trễ khi chúng kết thúc, thay vì mỗi phương thức tự đặt đồng hồ.

Ở mức tối thiểu, **join point** là sự kiện được cơ chế hỗ trợ, **pointcut** là điều kiện chọn sự kiện, **advice** là hành vi áp dụng, **aspect** là đơn vị chứa chính sách, và **weaving/interception** là cách kết hợp hành vi vào đường thực thi. AOP là mô hình chứ không phải một công nghệ duy nhất: proxy và dệt bytecode có các giới hạn khác nhau.

**Điều kiện để lợi ích có thật:** chính sách phải có cùng ý nghĩa tại những điểm đã chọn, pointcut phải đủ chính xác, và toàn bộ đường gọi, kết quả, lỗi, side effect phải được kiểm chứng. Chỉ giảm số dòng mã không bảo đảm thiết kế tốt hơn.

## 2. AOP có thể mang lại lợi ích gì?

### 2.1. Giảm mã lặp cho chính sách xuyên suốt

Giả sử nhiều nghiệp vụ cần cùng bộ quy tắc ghi nhận thông tin: thời điểm, loại thao tác, mã tương quan và kết quả thành công/thất bại. Sao chép đoạn ghi nhận vào từng phương thức dễ khiến phiên bản không đồng nhất, khó sửa và khó phát hiện chỗ bị quên. Đặt chính sách trong một aspect thích hợp giúp sửa một nơi và áp dụng có hệ thống.

Nhưng **ít dòng mã hơn không tự động đồng nghĩa với thiết kế tốt hơn**. Nếu hai thao tác có yêu cầu kiểm toán khác nhau về dữ liệu nhạy cảm, điều kiện thành công hoặc mức độ bắt buộc, gộp chúng vào cùng một aspect có thể che mất sự khác biệt.

### 2.2. Tách chính sách kỹ thuật khỏi câu chuyện nghiệp vụ

Một phương thức xử lý đơn hàng nên dễ đọc như các bước xử lý đơn hàng. Việc đo độ trễ hay gắn mã theo dõi thường là chính sách quan sát, không phải bước quyết định đơn có hợp lệ hay không. Tách hành vi này giúp mã nghiệp vụ dễ đọc hơn và giảm điểm cần sửa khi thay đổi công cụ quan sát.

Cần giữ ranh giới: **quyết định giảm giá, tính phí, xác định quyền sở hữu dữ liệu hay chuyển trạng thái đơn hàng là hành vi nghiệp vụ**, kể cả khi quy tắc xuất hiện ở nhiều nơi. Việc “dùng lại được” không đủ để biến nó thành aspect.

### 2.3. Tăng tính nhất quán tại biên có hợp đồng rõ

Các điểm vào/ra được xác định ổn định là nơi chính sách kỹ thuật có khả năng áp dụng đồng đều: chuẩn hóa thông tin log, đếm số lần gọi, gắn dấu vết, hoặc kiểm tra quy định đầu vào thống nhất. AOP hữu ích nhất khi:

1. Các điểm áp dụng được định nghĩa bằng tiêu chí ổn định, có thể kiểm tra.
2. Hành vi bổ sung có cùng ý nghĩa tại mọi điểm được chọn.
3. Có thể mô tả hợp đồng trước/sau mà không cần biết toàn bộ bên trong nghiệp vụ.
4. Nhóm phát triển có khả năng quan sát và kiểm thử mã được kết hợp sau weaving.

### 2.4. Thay đổi hoặc tắt chính sách tập trung

Khi cần đổi định dạng log hay cách ghi đo lường, thay đổi ở một aspect có thể giảm số vị trí sửa thủ công. Việc bật/tắt có kiểm soát cũng hữu ích cho đo đạc. Tuy nhiên, tính tập trung kéo theo **phạm vi tác động rộng**: một lỗi trong aspect có thể ảnh hưởng hàng trăm lời gọi cùng lúc. Cần có chủ sở hữu, kiểm thử tích hợp và kế hoạch khôi phục tương xứng.

## 3. Các đánh đổi thường bị đánh giá thấp

### 3.1. Luồng điều khiển không còn hiển thị đầy đủ tại nơi gọi

Nhìn vào `service.execute()` không cho biết trước và sau nó còn chạy advice nào, thứ tự gì, có bị thay tham số/kết quả hoặc chặn ngoại lệ hay không. Người bảo trì phải hiểu cả phương thức, pointcut, thứ tự aspect và cơ chế weaving.

Hệ quả thực tế:

- Stack trace có thêm lớp proxy hoặc frame do công cụ sinh ra; gỡ lỗi có thể khó hơn.
- Một thay đổi tên lớp, package, annotation hoặc chữ ký phương thức có thể làm pointcut đổi phạm vi mà mã nghiệp vụ vẫn biên dịch.
- Khi nhiều aspect cùng bao quanh một điểm, thứ tự có thể thay đổi kết quả. Hai aspect độc lập trên giấy chưa chắc giao hoán trong thực thi.

Ví dụ, nếu aspect A “ghi nhận thành công” chạy **trước** khi aspect B hoàn tất lưu trạng thái, log thành công có thể xuất hiện ngay cả khi B thất bại. Phải xác định rõ “thành công” nghĩa là advice hoàn thành, phương thức trả về hay giao dịch đã được xác nhận.

### 3.2. Hành vi lỗi và hợp đồng phương thức có thể thay đổi

Advice dạng *around* có quyền gọi tiếp, gọi nhiều lần hoặc không gọi phần nghiệp vụ tùy cơ chế. Nếu viết sai, nó có thể:

- Bỏ qua một thao tác bắt buộc hoặc thực hiện lại tác vụ có tác dụng phụ.
- Nuốt ngoại lệ, biến thất bại thành giá trị mặc định hoặc đổi kiểu ngoại lệ ngoài ý muốn.
- Làm thay đổi cách xử lý `finally`, thời điểm giải phóng tài nguyên, thứ tự commit hoặc phản hồi tới bên gọi.
- Làm rò rỉ dữ liệu nếu ghi nguyên tham số, kết quả, token hoặc thông tin định danh vào log.

Cần coi advice bao quanh như mã điều khiển quan trọng, có hợp đồng và kiểm thử riêng. Đừng mặc định mọi hành vi có thể thêm “trong suốt”.

### 3.3. Chi phí hiệu năng và độ phức tạp vận hành

Can thiệp vào lời gọi có thể thêm chi phí chọn điểm, tạo proxy, đi qua nhiều advice, truy xuất ngữ cảnh, phân bổ bộ nhớ và ghi log/I/O. Mức chi phí thực tế tùy cơ chế, cấu hình, mức tối ưu của JVM và đường chạy. Không nên khẳng định AOP luôn chậm đáng kể hoặc luôn miễn phí.

Ở đường nóng (*hot path*) chạy hàng triệu lần, thêm một thao tác tưởng nhỏ vào mọi lần gọi vẫn có thể trở thành nút thắt. Ngược lại, với một tác vụ cần truy vấn mạng, chi phí lời gọi trung gian có thể không đáng kể. **Đo độ trễ, throughput và cấp phát trên workload thật** trước khi kết luận.

### 3.4. Khả năng áp dụng phụ thuộc cơ chế

Trong mô hình proxy, lời gọi đi thẳng vào đối tượng đích có thể bỏ qua advice; lời gọi nội bộ `this.otherMethod()` có thể không đi qua proxy. Proxy dựa trên interface có giới hạn khác với proxy dựa trên lớp. Trong mô hình weaving vào bytecode, tập join point và giới hạn lại khác. Phương thức `final`, `private`, constructor, lambda, lời gọi bất đồng bộ hay lớp do công cụ sinh ra đều cần được đánh giá theo công nghệ cụ thể.

Điểm nguy hiểm là **tưởng chính sách đã bao phủ toàn hệ thống nhưng thực tế có đường gọi không được chặn**. Đây là rủi ro lớn nếu dùng aspect như lớp bảo vệ duy nhất cho dữ liệu hoặc hành động nhạy cảm.

### 3.5. Khó kiểm thử, khó suy luận về concurrency và thứ tự

Unit test gọi trực tiếp một đối tượng có thể không kích hoạt aspect; chỉ integration test qua cơ chế wiring/weaving thực mới cho thấy hành vi đầy đủ. Các tác vụ bất đồng bộ còn có vấn đề truyền context giữa thread, callback hoặc điểm tiếp tục xử lý. Dựa vào `ThreadLocal` mà không có chiến lược truyền/đóng context có thể làm mất mã tương quan hoặc để sót trạng thái trên thread tái sử dụng.

Ngoài kiểm thử “aspect có chạy”, cần kiểm thử cả **nơi aspect không được chạy**, đường lỗi, thứ tự nhiều aspect và trường hợp thực thi đồng thời.

### 3.6. Thay đổi diện rộng tạo rủi ro bảo trì

Một pointcut quá rộng như “mọi phương thức public” có thể bao gồm cả mã mới thêm về sau. Thay đổi một advice ảnh hưởng nhiều đội hoặc module. Khi tiêu chí chọn dựa vào tên phương thức, việc refactor không kèm kiểm thử phạm vi có thể mở rộng/thu hẹp chính sách âm thầm.

Hướng kiểm soát tốt hơn là phạm vi nhỏ, tiêu chí rõ, contract được công bố, test xác nhận tập điểm được chọn và review tác động trước khi đổi advice.

## 4. Những bài toán **không nên dùng AOP**

| Bài toán | Vì sao AOP thường không phù hợp | Hướng phù hợp hơn |
| --- | --- | --- |
| Tính giá, chiết khấu, hạn mức, điều kiện chuyển trạng thái | Đây là quyết định nghiệp vụ cần thấy và giải thích trực tiếp trong luồng chính; mỗi tình huống có thể khác nhau. | Domain service, policy/strategy, state machine hoặc lời gọi tường minh. |
| Điều phối quy trình gồm nhiều bước có thứ tự, rollback/bù trừ riêng | Hành vi quanh một join point không thể thay cho mô hình trạng thái và điều phối toàn quy trình. | Workflow/orchestrator, saga hoặc logic điều phối tường minh. |
| Chỉ có một hoặc hai nơi cùng cần thêm xử lý | Độ phức tạp pointcut/weaving có thể lớn hơn lượng trùng lặp loại bỏ được. | Lời gọi hàm rõ ràng, helper hoặc decorator nhỏ. |
| Mỗi lời gọi cần một ngoại lệ khác nhau | Một aspect dùng chung dễ chứa nhiều nhánh đặc biệt, làm chính sách khó hiểu và khó kiểm soát. | Interface rõ trách nhiệm, strategy hoặc cấu hình tường minh ngay tại nơi sử dụng. |
| Kiểm tra quyền phụ thuộc dữ liệu và chủ thể của từng thao tác | Gắn một pointcut theo tên phương thức không đảm bảo mọi đường truy cập đều được bảo vệ; quy tắc sở hữu là bất biến nghiệp vụ. | Kiểm tra tại biên tin cậy và trong logic quyết định quyền; AOP chỉ có thể là lớp bổ sung đã được chứng minh phạm vi. |
| Ghi kiểm toán bắt buộc phải thành công trước khi trả kết quả | Một advice kiểu “cố gắng ghi rồi bỏ qua lỗi” có thể làm mất bằng chứng; cần quy định rõ tính bền vững, thứ tự và xử lý lỗi. | Thiết kế giao dịch, outbox hoặc cơ chế ghi kiểm toán có hợp đồng đảm bảo cụ thể. |
| Retry mọi ngoại lệ một cách tự động | Retry có thể thực hiện nhiều lần một tác dụng phụ như gửi tiền hay phát sự kiện, gây trùng lặp và bão tải. | Retry tường minh tại biên I/O, có phân loại lỗi, idempotency key, backoff, giới hạn lần thử. |
| Cache mọi lời gọi chỉ vì muốn tăng tốc | Phương thức có side effect, phụ thuộc ngữ cảnh hoặc dữ liệu thay đổi không có semantics cache an toàn. | Thiết kế cache tường minh với khóa, TTL, bất biến và chiến lược vô hiệu hóa. |
| Xử lý vòng lặp rất nóng hoặc đường cực kỳ nhạy độ trễ | Can thiệp mọi lần gọi có thể làm tăng chi phí hoặc tạo I/O không kiểm soát. | Đo lường bằng profiling/sampling, xử lý theo lô hoặc instrumentation được đánh giá riêng. |
| Che giấu hành vi có ảnh hưởng hợp đồng API | Người gọi không biết được dữ liệu bị sửa, lỗi bị nuốt hoặc thao tác có thể bị thực hiện lại. | API tường minh, middleware có hợp đồng rõ hoặc hàm bao có tên cụ thể. |

**Dấu hiệu cảnh báo mạnh:** Nếu muốn hiểu tại sao kết quả nghiệp vụ là X mà bắt buộc phải mở một aspect “ẩn” mới thấy quy tắc quyết định X, có khả năng quy tắc đó đang nằm sai chỗ.

## 5. Ví dụ Java 17: tiện lợi của can thiệp tập trung và giới hạn của proxy

Ví dụ dưới dùng **JDK dynamic proxy** để minh họa một phần ý tưởng AOP: chặn lời gọi qua interface và áp dụng hành vi audit trước/sau tại một điểm chung. Đây là ví dụ chạy độc lập bằng Java chuẩn, **không phải bộ AOP hoàn chỉnh**: không có ngôn ngữ pointcut hay weaving bytecode. Nó hữu ích để thấy ranh giới giữa chính sách xuyên suốt và logic nghiệp vụ.

Tạo tệp `AopTradeoffDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class AopTradeoffDemo {
    interface OrderService {
        String place(String orderId);
    }

    static class DefaultOrderService implements OrderService {
        @Override
        public String place(String orderId) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId required");
            }
            System.out.println("BUSINESS place " + orderId);
            return "OK " + orderId;
        }
    }

    public static void main(String[] args) {
        OrderService target = new DefaultOrderService();
        OrderService audited = (OrderService) Proxy.newProxyInstance(
                OrderService.class.getClassLoader(),
                new Class<?>[] { OrderService.class },
                (proxy, method, methodArgs) -> {
                    System.out.println("AUDIT before " + method.getName());
                    try {
                        Object result = method.invoke(target, methodArgs);
                        System.out.println("AUDIT success " + method.getName());
                        return result;
                    } catch (InvocationTargetException ex) {
                        System.out.println("AUDIT failure " + method.getName());
                        throw ex.getCause();
                    }
                }
        );

        System.out.println(audited.place("ORD-7"));
        try {
            audited.place("");
        } catch (IllegalArgumentException ex) {
            System.out.println("CALLER caught " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac AopTradeoffDemo.java
java AopTradeoffDemo
```

Kết quả chuẩn:

```text
AUDIT before place
BUSINESS place ORD-7
AUDIT success place
OK ORD-7
AUDIT before place
AUDIT failure place
CALLER caught orderId required
```

Phân tích:

- `DefaultOrderService` giữ quy tắc nghiệp vụ: mã đơn không được trống. Quy tắc này **không chuyển vào advice** chỉ vì mọi đơn đều cần nó.
- Logic ghi nhận đặt tại một nơi. Cùng cơ chế bọc có thể dùng cho nhiều lời gọi qua interface đã chọn mà không lặp đoạn audit trong phương thức nghiệp vụ.
- `Method.invoke` bọc ngoại lệ do phương thức đích ném trong `InvocationTargetException`. `throw ex.getCause()` giữ lại nguyên nhân để bên gọi nhận `IllegalArgumentException`, thay vì vô tình đổi hợp đồng lỗi.
- `AUDIT success` chỉ chứng minh lời gọi trả về bình thường. Nó **không chứng minh** dữ liệu đã được lưu bền vững hay giao dịch đã commit; yêu cầu audit thực tế phải xác định điều kiện thành công.
- Chỉ lời gọi qua `audited` được chặn. Gọi trực tiếp `target.place(...)` bỏ qua handler; lời gọi tự gọi trong lớp đích cũng không tự chuyển qua đối tượng proxy này. Đây là giới hạn của **cách proxy trong ví dụ**, không phải mọi dạng AOP.
- Handler trong ví dụ chưa xử lý phân loại phương thức, lọc dữ liệu nhạy cảm, truy vết bất đồng bộ hoặc ghi audit bền vững. Không dùng nguyên xi làm chính sách bảo mật/kiểm toán production.

Một bài toán **không phù hợp** để chuyển sang handler trên: khi tính tổng tiền đơn hàng, quy tắc “khách hạng A được giảm 10% nếu đơn thỏa điều kiện” nên nằm ở mô hình chính sách giá và được gọi tường minh trong tiến trình chốt giá. Nếu che trong advice của `place()`, hành vi tính tiền trở nên khó truy vết, khó thử các trường hợp biên và dễ bị bỏ qua khi đường xử lý đổi.

## 6. Chọn AOP hay phương án khác?

| Cách tổ chức | Nên cân nhắc khi | Đánh đổi chính |
| --- | --- | --- |
| **Lời gọi trực tiếp / helper** | Số điểm áp dụng ít; tác động tới kết quả nghiệp vụ cần hiển thị. | Có thể lặp lời gọi ở nhiều nơi. |
| **Decorator hoặc wrapper tường minh** | Muốn thêm hành vi cho một interface/đối tượng với chuỗi bọc rõ ràng. | Phải truyền và cấu hình wrapper; phạm vi gắn với đối tượng cụ thể. |
| **Interceptor ở một biên có sẵn** | Hành vi thuộc ranh giới vào/ra cụ thể, như một pipeline xử lý yêu cầu hoặc thông điệp. | Phụ thuộc contract và phạm vi của pipeline. |
| **AOP theo pointcut/advice** | Cùng một chính sách kỹ thuật xuất hiện ở nhiều điểm, tiêu chí chọn ổn định và cơ chế weaving đã được kiểm chứng. | Luồng thực thi ít tường minh hơn; phạm vi tác động, thứ tự và kiểm thử phức tạp hơn. |
| **Domain service / policy / workflow** | Có quyết định nghiệp vụ, trạng thái, quyền theo đối tượng hoặc nhiều bước bù trừ. | Phải mô hình hóa và gọi hành vi một cách rõ ràng. |

Không phải mọi concern xuyên suốt đều dùng AOP tốt nhất. Ví dụ, gắn ID truy vết ở biên tiếp nhận rồi chuyển theo context có hợp đồng rõ thường dễ quản lý hơn so với một pointcut bắt mọi phương thức. Hãy chọn cơ chế ở **biên tự nhiên của trách nhiệm**.

### Bộ câu hỏi ra quyết định

Trước khi viết một aspect, tự trả lời:

1. **Chính sách hay nghiệp vụ?** Có thể thay đổi hoặc bỏ hành vi này mà kết quả nghiệp vụ vẫn đúng không? Nếu không, ưu tiên mô hình hóa nghiệp vụ tường minh.
2. **Có đủ điểm giống nhau?** Có thực sự nhiều điểm cùng nhu cầu và cùng điều kiện áp dụng, hay chỉ vài điểm nhìn có vẻ giống?
3. **Ranh giới xác định được không?** Có thể mô tả chính xác join point cần chọn và join point phải loại trừ? Refactor có làm quy tắc mất tác dụng âm thầm?
4. **Hợp đồng có được bảo toàn?** Advice có giữ nguyên tham số, kết quả, ngoại lệ, thứ tự tác dụng phụ, context và các bất biến quan trọng?
5. **Độ tin cậy phù hợp không?** Nếu logging/metrics thất bại, nghiệp vụ có được tiếp tục không? Nếu audit hoặc kiểm tra quyền thất bại, phải xử lý thế nào? Câu trả lời phải là thiết kế rõ ràng.
6. **Có chứng minh bằng thử nghiệm không?** Có thể đo overhead và viết kiểm thử xác nhận cả trường hợp được chọn, không được chọn, lỗi, bất đồng bộ và nhiều advice?
7. **Người bảo trì có tìm ra hành vi không?** Điểm áp dụng, thứ tự và chủ sở hữu aspect có dễ tra cứu từ mã và tài liệu?

Nếu nhiều câu trả lời vẫn mơ hồ, bắt đầu với giải pháp tường minh quy mô nhỏ thường giúp làm rõ hợp đồng; chỉ khái quát thành aspect khi đã thấy điểm chung ổn định.

## 7. Nếu vẫn chọn AOP, triển khai thế nào để giảm rủi ro?

- **Pointcut hẹp, có ý nghĩa:** chọn biên/nhóm chức năng thật sự cần chính sách; tránh bắt toàn hệ thống theo quy ước tên dễ vỡ. Với annotation hoặc marker, cần quy định ai có quyền gắn và gắn ở đâu.
- **Advice có một trách nhiệm:** ví dụ đo thời gian, ghi log hoặc áp chính sách riêng; tránh trộn log, retry, thay dữ liệu và phân quyền vào một advice khó kiểm tra.
- **Hợp đồng ngoại lệ và side effect rõ:** phân biệt thành công của phương thức với commit bền vững. Với retry, chỉ lặp khi thao tác có tính idempotent hoặc có cơ chế chống trùng lặp đã được kiểm chứng.
- **Thứ tự nhiều advice được xác định:** mô tả thứ tự trước/sau/around, đặc biệt với transaction, audit, đo thời gian và xử lý lỗi; thử nghiệm thứ tự quan sát được.
- **Kiểm thử trên cơ chế thực:** chạy integration test qua wiring hoặc weaving thực tế; có ca positive, negative, thất bại, nested call, concurrency và đường asynchronous phù hợp.
- **Đo tác động:** so sánh latency, throughput, lượng log và cấp phát trước/sau bật aspect trên tải gần thực tế; tránh log dữ liệu nhạy cảm.
- **Bảo đảm khả năng quan sát:** tài liệu hóa điểm áp dụng, tên aspect và cách xác định advice nào đang chạy; giữ thông tin correlation/trace qua các đường bất đồng bộ cần thiết.
- **Giới hạn phạm vi lỗi:** phát hành có kiểm soát, kiểm tra các điểm chịu tác động và chuẩn bị cách vô hiệu hóa an toàn nếu loại chính sách cho phép. Với chính sách fail-closed như kiểm soát quyền, không được tắt tùy tiện để “khôi phục” hệ thống.

## 8. Tự đánh giá qua bốn tình huống

**Tình huống A:** 40 thao tác I/O cần cùng một bộ đo thời gian và phát số liệu, không làm thay đổi giá trị trả về. Các điểm cần đo được định nghĩa ổn định. **AOP đáng cân nhắc**, sau khi so sánh với instrumentation tại biên I/O, kiểm thử phạm vi và đo overhead.

**Tình huống B:** Hệ thống đặt vé yêu cầu giữ chỗ, thanh toán và hoàn tác giữ chỗ khi thanh toán thất bại. **Không dùng AOP để ẩn orchestration**: trạng thái và bù trừ là phần lõi của quy trình, nên cần workflow/điều phối tường minh.

**Tình huống C:** Mọi lệnh “xóa tài liệu” phải kiểm tra người gọi có sở hữu tài liệu đó hay không. **Không coi một pointcut là bảo đảm duy nhất**: quyền phụ thuộc đối tượng dữ liệu và mọi đường truy cập. Đặt bất biến kiểm quyền tại biên tin cậy và logic nghiệp vụ; chỉ thêm AOP như một lớp kỹ thuật nếu chứng minh được bao phủ.

**Tình huống D:** Một tiện ích toán học nhỏ được gọi trong vòng lặp chặt hàng triệu lần; muốn log từng lần để điều tra hiệu năng. **Tránh chặn/log tất cả lượt gọi**: I/O làm méo kết quả đo và có thể áp đảo thời gian tính toán. Dùng profiling hoặc sampling có giới hạn.

## Kết luận

AOP mạnh khi **một chính sách kỹ thuật có nghĩa giống nhau** cần áp dụng nhất quán trên nhiều điểm thực thi, và tập điểm đó có thể xác định, kiểm thử, quan sát được. Giá đổi lại là luồng thực thi ít hiển thị tại nơi gọi, nhiều ràng buộc về thứ tự, ngoại lệ, hiệu năng, concurrency và khả năng bảo trì. Quy tắc nghiệp vụ, bảo đảm dữ liệu quan trọng và tiến trình nhiều bước nên được mô hình hóa rõ ràng. Câu hỏi quan trọng nhất trước khi chọn AOP là: **“Hành vi này có thực sự là chính sách độc lập với nghiệp vụ, và ta có chứng minh được phạm vi tác động của nó không?”**
