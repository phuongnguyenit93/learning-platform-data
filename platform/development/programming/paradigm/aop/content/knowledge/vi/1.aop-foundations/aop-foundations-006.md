# Quan hệ giữa AOP, lập trình thủ tục và lập trình hướng đối tượng

## 1. Bức tranh tổng thể

**Lập trình thủ tục (procedural programming)**, **lập trình hướng đối tượng (object-oriented programming — OOP)** và **lập trình hướng khía cạnh (aspect-oriented programming — AOP)** trả lời ba nhóm câu hỏi khác nhau khi tổ chức phần mềm:

- **Thủ tục:** Những bước xử lý nào cần thực hiện, theo trình tự và luồng điều khiển nào?
- **Hướng đối tượng:** Dữ liệu và hành vi thuộc trách nhiệm của đối tượng nào? Các đối tượng phối hợp với nhau ra sao?
- **Hướng khía cạnh:** Một chính sách hoặc hành vi chung xuất hiện ở nhiều vị trí nên được mô tả và gắn vào các điểm thực thi nào?

Ba cách tiếp cận **không tạo thành một chuỗi thay thế nhau**. Một ứng dụng hướng đối tượng vẫn dùng thuật toán và thủ tục trong các phương thức; AOP có thể bổ sung cơ chế tách các mối quan tâm trải rộng qua nhiều chức năng. Tùy ngôn ngữ và công cụ, AOP có thể kết hợp với chương trình hướng đối tượng hoặc chương trình tổ chức theo hàm/thủ tục.

Ví dụ, khi xử lý đơn hàng, quy tắc tính tổng tiền là **nghiệp vụ cốt lõi**. Ghi nhận thời gian thực thi, tạo dấu vết kiểm toán và áp dụng một chính sách quan sát chung có thể là các **mối quan tâm xuyên suốt** (*cross-cutting concerns*) vì chúng xuất hiện ở nhiều thao tác như tạo đơn, hoàn tiền và hủy đơn. AOP tập trung vào cách biểu đạt và kết hợp những mối quan tâm xuyên suốt đó.

## 2. Từng mô hình tổ chức chương trình như thế nào?

### 2.1. Lập trình thủ tục: tổ chức theo bước và hàm

Chương trình được chia thành các thủ tục/hàm. Luồng điều khiển chủ yếu được thể hiện qua lời gọi hàm, điều kiện, vòng lặp và cấu trúc dữ liệu. Ví dụ dưới đây là **mã giả**, nhằm trình bày luồng xử lý:

```text
procedure checkout(order):
    requirePermission(order)
    recordAudit("checkout started")
    result = chargePayment(order)
    recordAudit("checkout finished")
    return result

procedure refund(order):
    requirePermission(order)
    recordAudit("refund started")
    result = reversePayment(order)
    recordAudit("refund finished")
    return result
```

Điểm mạnh là dễ theo dõi thứ tự xử lý trực tiếp ở mỗi thủ tục, phù hợp với các thuật toán và tác vụ có luồng tuần tự rõ ràng. Tuy nhiên, nếu hàng chục thủ tục đều phải thực hiện cùng một chính sách kiểm toán, kiểm tra quyền hoặc đo thời gian, mã chung dễ **lặp lại hoặc phân tán**.

Có thể tách phần chung thành các hàm như `recordAudit()` hay `requirePermission()`; điều này giảm trùng lặp bên trong logic chung, nhưng mỗi thủ tục vẫn cần **gọi chúng đúng chỗ**, trừ khi sử dụng thêm một cơ chế bao bọc hoặc tự động kết hợp khác. Đây là vấn đề về *vị trí áp dụng chính sách*, không phải nhược điểm tuyệt đối của lập trình thủ tục.

### 2.2. OOP: tổ chức theo dữ liệu, trạng thái và trách nhiệm

OOP gom dữ liệu và hành vi liên quan vào đối tượng, sử dụng đóng gói, trừu tượng, đa hình và quan hệ giữa các kiểu để quản lý độ phức tạp. Ví dụ, `CheckoutService` chịu trách nhiệm thanh toán, còn `RefundService` chịu trách nhiệm hoàn tiền. Mỗi phương thức bên trong đối tượng vẫn có các bước thực thi tuần tự.

Mẫu Java 17 dưới đây đặt cạnh nhau một hàm xử lý kiểu thủ tục và hai phương thức hướng đối tượng; phần kiểm toán được viết tại từng điểm gọi để làm rõ vấn đề phân tán:

```java
public class CheckoutDemo {
    static void checkoutProcedural(String orderId) {
        System.out.println("[procedural:audit] start");
        System.out.println("[procedural] checkout " + orderId);
        System.out.println("[procedural:audit] end");
    }

    static final class CheckoutService {
        void checkout(String orderId) {
            System.out.println("[audit] start checkout");
            System.out.println("checkout " + orderId);
            System.out.println("[audit] end checkout");
        }
    }

    static final class RefundService {
        void refund(String orderId) {
            System.out.println("[audit] start refund");
            System.out.println("refund " + orderId);
            System.out.println("[audit] end refund");
        }
    }

    public static void main(String[] args) {
        checkoutProcedural("P-01");
        new CheckoutService().checkout("O-02");
        new RefundService().refund("O-03");
    }
}
```

Lưu tệp dưới tên `CheckoutDemo.java` rồi chạy:

```bash
javac CheckoutDemo.java
java CheckoutDemo
```

Kết quả chính xác:

```text
[procedural:audit] start
[procedural] checkout P-01
[procedural:audit] end
[audit] start checkout
checkout O-02
[audit] end checkout
[audit] start refund
refund O-03
[audit] end refund
```

Mẫu này chủ ý tối giản: chưa có thanh toán thật, lỗi mạng hay giao dịch dữ liệu. Nó cho thấy OOP có thể tách trách nhiệm thanh toán và hoàn tiền vào các đối tượng, nhưng các dòng kiểm toán vẫn nằm rải rác trong nhiều phương thức.

OOP đã có các công cụ giảm lặp như kế thừa, composition, decorator, interceptor hoặc helper. Chúng đủ tốt trong nhiều tình huống. Tuy nhiên, nếu một quy tắc phải gắn ở nhiều lớp không có cùng quan hệ kế thừa, dùng chung superclass dễ gây gắn kết không cần thiết; dùng decorator hoặc interceptor thủ công lại đòi hỏi quản lý nơi bọc và nơi gọi. AOP đưa ra một cách diễn đạt khác cho quy tắc trải rộng này.

### 2.3. AOP: tổ chức theo mối quan tâm xuyên suốt và điểm áp dụng

AOP mô tả một hành vi chung thành **aspect** và định nghĩa **những điểm thực thi** nơi hành vi đó được áp dụng. Trong ví dụ, mã xử lý thanh toán và hoàn tiền tập trung vào nghiệp vụ, còn quy tắc kiểm toán được mô tả một lần trong aspect.

Minh họa dưới đây là **mã giả AOP trung lập công cụ**, không phải cú pháp Java hay chương trình có thể biên dịch trực tiếp:

```text
aspect OperationAudit:
    pointcut trackedOperations =
        execution(CheckoutService.checkout)
        OR execution(RefundService.refund)

    around trackedOperations(invocation):
        audit("start " + invocation.name)
        try:
            return proceed(invocation)
        finally:
            audit("end " + invocation.name)
```

Trong mã giả, `pointcut` chọn hai điểm thực thi, `around` bao phần xử lý, và `proceed` tiếp tục gọi thao tác gốc. Khi cơ chế **weaving** phù hợp đã kết hợp aspect với mã chương trình, bên gọi vẫn gọi `checkout()` hoặc `refund()`, còn logic kiểm toán được thực thi tại các điểm được chọn. `finally` minh họa ý định ghi nhận kết thúc kể cả khi thao tác gốc ném lỗi; hành vi cụ thể vẫn tùy loại advice và công cụ AOP.

Chỉ viết ra một mô tả aspect **chưa đủ để chương trình Java tự động chạy nó**. Cần có cơ chế nhận diện điểm nối và kết hợp advice vào quá trình thực thi. Các công cụ AOP khác nhau có cú pháp, loại điểm nối và giới hạn khác nhau.

## 3. AOP bổ sung chiều trách nhiệm nào cho thủ tục và OOP?

Để so sánh ba mô hình, chỉ cần một bộ thuật ngữ đủ dùng: **join point** là sự kiện mà công cụ AOP có thể can thiệp, **pointcut** chọn tập sự kiện, **advice** là hành vi được thực hiện, **aspect** gom chính sách cùng cách áp dụng, và **weaving/interception** đưa hành vi vào đường chạy. Nghiệp vụ gốc là **target**; loại sự kiện được hỗ trợ phụ thuộc kỹ thuật triển khai.

Trong thủ tục hoặc OOP, người gọi hay đối tượng thường thể hiện trực tiếp cách phối hợp hành vi:

```text
Caller → auditStart() → checkout() → auditEnd()
```

Với AOP, quy tắc áp dụng được đặt tách khỏi thân phương thức:

```text
Caller → [advice trước] → [checkout gốc] → [advice kết thúc]
               ↑               ↑
      pointcut chọn join point phù hợp
```

Với cách thứ hai, phần nghiệp vụ vẫn được tổ chức bằng hàm hoặc đối tượng như trước; AOP **không** tạo ra thuật toán thanh toán hay quyết định quy tắc hoàn tiền. Nó chỉ cung cấp một trục mô-đun hóa khác cho chính sách chung.

Advice có thể chạy **before**, **after returning**, **after throwing**, **after/finally** hoặc **around** theo công cụ. Đặc biệt, `around` có thể quyết định có tiếp tục phần xử lý bên trong hay không; quên tiếp tục hoặc tiếp tục nhiều lần có thể bỏ sót hay lặp side effect. Vì vậy việc áp dụng advice phải bảo toàn hợp đồng kết quả/ngoại lệ trừ khi chính sách thay đổi hợp đồng có chủ đích.

Cũng cần phân biệt thời điểm kết hợp: **compile-time weaving**, **load-time weaving**, biến đổi bytecode sau biên dịch và **runtime proxy/interception** là các cách thực hiện khác nhau. Proxy chỉ quan sát những đường gọi đi qua trung gian phù hợp; weaving mã có giới hạn khác. Không được suy luận “đã khai báo aspect” là mọi lời gọi, constructor hoặc truy cập trường đều bị can thiệp.

## 4. Quan hệ bổ sung giữa ba cách tiếp cận

| Tiêu chí | Thủ tục | Hướng đối tượng | Hướng khía cạnh |
| --- | --- | --- | --- |
| Đơn vị tổ chức nổi bật | Hàm/thủ tục và chuỗi bước | Đối tượng, lớp, giao diện, trách nhiệm | Aspect, pointcut, advice |
| Câu hỏi thiết kế chủ đạo | Xử lý theo các bước nào? | Trách nhiệm thuộc thành phần nào? | Hành vi chung cần áp dụng tại đâu? |
| Đường đi của xử lý | Chủ yếu thể hiện bằng lời gọi trực tiếp | Thể hiện bằng phương thức và cộng tác đối tượng | Có thể được bổ sung tại các điểm nối bởi weaving |
| Chia sẻ hành vi chung | Gọi hàm dùng chung | Composition, đa hình, decorator, helper | Khai báo chính sách và các điểm áp dụng |
| Thế mạnh | Thuật toán tuyến tính, luồng xử lý tường minh | Mô hình hóa miền, đóng gói, khả năng mở rộng theo trách nhiệm | Tách chính sách lặp qua nhiều thành phần |
| Rủi ro nếu lạm dụng | Thủ tục lớn; nhiều nơi phải gọi cùng helper | Quá nhiều lớp, kế thừa hoặc wrapper chỉ để tái sử dụng một mảnh hành vi | Luồng thực thi khó nhận ra, pointcut quá rộng, thứ tự advice phức tạp |

Bảng chỉ mô tả **trọng tâm**, không phải ranh giới tuyệt đối. Chẳng hạn, một ứng dụng thủ tục vẫn có thể chia module hợp lý; OOP có thể áp dụng interceptor; AOP vẫn cần các hàm, đối tượng và thuật toán hiện hữu để thực hiện nghiệp vụ.

Có thể nhìn cùng một xử lý theo ba lớp:

```text
Luồng bước nghiệp vụ:         kiểm tra đơn -> tính tiền -> thanh toán
Trách nhiệm hướng đối tượng: OrderService / PricingPolicy / PaymentGateway
Chính sách xuyên suốt:        phân quyền, audit, đo thời gian
```

Lớp thứ ba **không định nghĩa lại** cách tính tiền hay trách nhiệm của từng đối tượng. Nó quy định hành vi chung sẽ được thực hiện tại những điểm cụ thể trong luồng đã có.

### 4.1. Vì sao đóng gói OOP chưa giải quyết hết cross-cutting concerns?

Đóng gói gom **dữ liệu và hành vi thuộc cùng trách nhiệm** vào một đối tượng. Nhưng một chính sách như đo thời gian có thể áp dụng cho rất nhiều lớp độc lập. Nếu đặt đo thời gian trong từng lớp, ta làm mờ trách nhiệm chính của chúng; nếu gom tất cả vào một lớp cha, ta dễ ép các lớp độc lập vào quan hệ kế thừa không tự nhiên.

Đây là khác biệt giữa hai chiều phân rã:

- **Phân rã theo chức năng/trách nhiệm:** thanh toán, hoàn tiền, quản lý tồn kho.
- **Phân rã theo chính sách xuyên suốt:** kiểm toán, quan sát, quy tắc kiểm soát truy cập dùng chung.

AOP cung cấp một cơ chế mô-đun hóa theo chiều thứ hai, song không loại bỏ nhu cầu thiết kế theo chiều thứ nhất.

### 4.2. AOP có thể kết hợp với chương trình thủ tục không?

Về ý tưởng, **có**: nếu nền tảng cho phép can thiệp các điểm thực thi như lời gọi hàm, aspect có thể áp dụng lên các hàm/thủ tục. Tuy vậy, khả năng này không mặc nhiên tồn tại trong mọi ngôn ngữ hay trình biên dịch. Trong hệ sinh thái Java, AOP thường được diễn giải qua các điểm nối gắn với kiểu, đối tượng và phương thức, nên OOP và AOP hay xuất hiện cùng nhau.

Điểm cần nhớ là: **AOP độc lập về mục đích mô-đun hóa mối quan tâm xuyên suốt, nhưng phụ thuộc vào cơ chế hỗ trợ cụ thể để hiện thực trên chương trình thực tế.**

## 5. Một tình huống đầy đủ: thêm kiểm toán và đo thời gian

Giả sử hệ thống có `checkout()`, `refund()` và `cancelOrder()`. Yêu cầu mới:

- Ghi nhận tên thao tác, thời điểm bắt đầu và kết quả thành công/thất bại.
- Đo thời gian thực thi của cả ba thao tác.
- Không thay đổi quy tắc tính phí, hoàn tiền hay hủy đơn.
- Các thao tác mới cùng nhóm phải được áp dụng chính sách nhất quán.

**Cách thủ tục:** thêm lời gọi các hàm `auditStart`, `auditEnd`, `timerStart`, `timerStop` tại từng thủ tục. Cần dùng cấu trúc kiểm soát lỗi phù hợp để ghi nhận trường hợp thất bại; nếu quên một đường trả về hoặc ngoại lệ, số liệu có thể sai.

**Cách OOP thuần:** đặt nghiệp vụ trong các dịch vụ và sử dụng decorator, composition hoặc interceptor do chương trình lắp ghép tường minh. Cách này thường dễ theo dõi và kiểm thử khi số điểm áp dụng nhỏ, nhưng tăng công cấu hình/bọc khi chính sách trải qua nhiều đối tượng.

**Cách AOP:** khai báo tập các điểm thực thi hợp lệ và một advice bao quanh. Thay vì thêm lệnh đo ở từng phương thức, cơ chế weaving gắn hành vi đo vào các điểm đã chọn. Ví dụ ý tưởng:

```text
around selectedBusinessOperation(context):
    start = monotonicClock()
    status = "SUCCESS"
    try:
        return proceed(context)
    catch error:
        status = "FAILURE"
        throw error
    finally:
        duration = monotonicClock() - start
        recordMetric(context.operationName, status, duration)
```

Đây tiếp tục là **mã giả**. Đồng hồ tăng đơn điệu phù hợp hơn đồng hồ lịch để đo khoảng thời gian. Việc ném lại ngoại lệ giữ nguyên tín hiệu lỗi cho bên gọi; advice nên tránh tự ý nuốt lỗi hoặc thay đổi kết quả trừ khi đó chính là chính sách được thiết kế.

Xét ở cấp độ logic, kết quả mong muốn có dạng:

```text
Bên gọi
  -> advice bắt đầu đo
      -> checkout/refund/cancelOrder thực thi quy tắc nghiệp vụ gốc
  <- advice đo kết thúc, lưu trạng thái và thời gian
Bên gọi nhận kết quả/ngoại lệ theo hợp đồng nghiệp vụ
```

Lưu ý: nếu thao tác trả về một đối tượng biểu diễn công việc bất đồng bộ, thời điểm phương thức **trả về** có thể xảy ra trước thời điểm công việc **hoàn tất**. Muốn đo toàn bộ tác vụ cần hiểu vòng đời tác vụ và điểm nối mà cơ chế AOP thực sự hỗ trợ; đo lời gọi phương thức đơn thuần không bảo đảm đo toàn bộ quá trình bất đồng bộ.

## 6. Khi nào chọn thủ tục, OOP, AOP hoặc kết hợp?

- **Dùng thủ tục/hàm** khi trọng tâm là một thuật toán, pipeline dữ liệu hay tác vụ ngắn với luồng điều khiển trực tiếp. Tách helper nếu phần xử lý được tái sử dụng.
- **Dùng OOP** khi cần quản lý trách nhiệm, bất biến dữ liệu, trạng thái và tương tác giữa thành phần. Đây là lựa chọn tổ chức nghiệp vụ phổ biến trong Java.
- **Dùng composition/decorator/interceptor tường minh** khi một hành vi chung chỉ bao vài đối tượng, thứ tự gọi phải dễ nhận ra trong mã, hoặc cần chủ động kiểm soát từng đường đi.
- **Cân nhắc AOP** khi cùng một chính sách ổn định cần áp dụng nhất quán qua nhiều điểm thực thi, việc khai báo điểm áp dụng làm mã nghiệp vụ rõ hơn và công cụ có thể can thiệp chính xác các điểm cần thiết.

Ví dụ phù hợp với AOP gồm telemetry chung, audit tại ranh giới thao tác, đo hiệu năng, hoặc các quy tắc kỹ thuật dùng chung. Tuy nhiên, **không phải mọi logic lặp đều nên thành aspect**. Phép tính thuế, quyết định hạn mức tín dụng hay quy tắc chọn phương thức thanh toán là nghiệp vụ cốt lõi; chúng nên có nơi sở hữu rõ ràng trong thiết kế chức năng, ngay cả khi nhiều nơi sử dụng.

Một câu hỏi lựa chọn thực tế: *Nếu bỏ cơ chế can thiệp tự động, chính sách này có còn là bước nghiệp vụ mà người đọc bắt buộc phải nhìn thấy để hiểu tính đúng đắn của phương thức không?* Nếu có, việc đưa toàn bộ chính sách đó ra khỏi luồng nghiệp vụ có thể làm thiết kế khó hiểu hoặc nguy hiểm. Ví dụ, kiểm tra điều kiện hoàn tiền đặc thù cho đơn hàng thường thuộc miền nghiệp vụ; một chính sách ghi audit nhất quán cho mọi lần hoàn tiền có thể là ứng viên cross-cutting tốt hơn.

## 7. Những hệ quả thiết kế nâng cao

### 7.1. Thứ tự và tính kết hợp của nhiều aspect

Một điểm thực thi có thể khớp nhiều pointcut. Ví dụ, cùng một thao tác chịu kiểm tra quyền, đo thời gian và kiểm toán. Thứ tự bao quanh quyết định điều gì được đo và ghi:

```text
Audit(Authorization(Timing(businessOperation)))
```

Ở thứ tự này, audit có thể ghi cả lần bị từ chối quyền, trong khi timer chỉ đo thao tác vượt qua kiểm tra quyền. Nếu đổi thành `Authorization(Audit(Timing(...)))`, yêu cầu bị từ chối có thể không đi qua audit. **Đừng suy ra thứ tự mặc định** khi chưa xác minh cơ chế sắp xếp advice của công cụ; hãy đặt thứ tự rõ ràng và kiểm thử các đường thành công, lỗi và từ chối.

### 7.2. Pointcut quá rộng hoặc quá hẹp

Một pointcut chọn mọi phương thức theo mẫu tên quá chung có thể bắt cả thao tác không liên quan; một pointcut quá cụ thể có thể bỏ sót các thao tác mới. Điều này gây ra hai loại lỗi đối xứng: **áp dụng sai nơi** và **không áp dụng nơi cần thiết**.

Tốt nhất nên xác định rõ ranh giới ngữ nghĩa (nhóm thao tác, kiểu hoặc dấu đánh dấu có nghĩa), kiểm tra tập điểm thực thi khớp với pointcut, và có bài kiểm thử chứng minh một điểm **phải được can thiệp** cũng như một điểm **không được can thiệp**. Tên phương thức một mình có thể không đủ để diễn đạt chính sách bảo mật hoặc nghiệp vụ.

### 7.3. Tác động đến hợp đồng của phương thức

Advice có thể tạo thêm ngoại lệ, đổi kết quả, bỏ qua lời gọi gốc hoặc tăng chi phí thực thi. Với các thao tác có tác dụng phụ, gọi `proceed` nhiều lần có thể gây trừ tiền hai lần hoặc ghi dữ liệu hai lần. Khi xây dựng aspect, cần xác định rõ:

1. Advice có được phép ngăn thao tác gốc không?
2. Nó có được phép sửa tham số, giá trị trả về hoặc ngoại lệ không?
3. Nó phải chạy một lần hay có chủ ý thử lại?
4. Nếu bản thân logging/metrics/audit gặp lỗi, hành vi nghiệp vụ phải ra sao?

Những quyết định này thuộc **hợp đồng ứng dụng**. AOP chỉ cung cấp điểm và cơ chế để kết hợp hành vi; nó không tự bảo đảm an toàn nghiệp vụ.

### 7.4. Ranh giới kỹ thuật và khả năng quan sát

Một số cách hiện thực dùng đối tượng trung gian nên chỉ can thiệp được các cuộc gọi đi qua trung gian ấy; lời gọi nội bộ có thể đi đường khác. Các cơ chế biến đổi mã có thể có tập join point rộng hơn, nhưng đòi hỏi quy trình biên dịch/nạp phù hợp. Vì thế, cần kiểm chứng trên công cụ thực tế thay vì suy đoán rằng một pointcut đã bao phủ mọi trường hợp.

AOP cũng có thể khiến người đọc một phương thức không nhìn thấy ngay toàn bộ hành vi khi chạy. Nên có quy ước đặt tên, tài liệu hóa điểm áp dụng, log/trace rõ ràng, và kiểm thử tích hợp cho thứ tự advice, ngoại lệ, hiệu năng và sự tương tác giữa aspect.

### 7.5. Tránh nhầm giữa tách mã và tách trách nhiệm

Chuyển các dòng `checkPermission()` hay `audit()` ra ngoài phương thức khiến thân phương thức ngắn hơn, nhưng **không tự động cải thiện thiết kế**. Một aspect có thể trở thành nơi chứa quá nhiều chính sách không liên quan; pointcut có thể tạo phụ thuộc ngầm vào cấu trúc lớp hoặc tên phương thức; lạm dụng AOP có thể làm thay đổi hành vi khó truy tìm hơn so với lời gọi tường minh.

Quy tắc thực hành là: mỗi aspect nên diễn đạt một chính sách xuyên suốt có trách nhiệm rõ, điểm áp dụng có thể giải thích được và tác động lên kết quả/ngoại lệ được kiểm soát.

## 8. Những nhầm lẫn thường gặp

**“AOP là phiên bản mới thay thế OOP.”** Sai. OOP tổ chức trách nhiệm và trạng thái; AOP giải quyết thêm chiều mô-đun hóa các hành vi xuyên suốt. Nhiều hệ thống dùng đồng thời cả hai.

**“OOP không thể tái sử dụng logging hoặc bảo mật.”** Sai. OOP có composition, helper, decorator, interceptor và nhiều cách tổ chức khác. AOP thuận lợi khi muốn mô tả **chính sách và phạm vi áp dụng** tập trung.

**“Aspect giống hệt một hàm tiện ích.”** Không hẳn. Hàm tiện ích cần được gọi hoặc bọc tại những nơi sử dụng; aspect kết hợp **hành vi + quy tắc chọn điểm áp dụng + cơ chế weaving**.

**“Có pointcut thì mọi phương thức khớp tên đều được can thiệp.”** Không bảo đảm. Phải xét loại join point, thời điểm weaving, phạm vi mã và các giới hạn cụ thể của công cụ.

**“AOP chỉ thêm logging nên không thể thay đổi logic.”** Sai. Around advice có thể bỏ qua, lặp lại, sửa tham số hoặc tác động đến kết quả nếu công cụ cho phép. Vì vậy cần kỷ luật thiết kế.

**“Cứ có mã xuất hiện ở nhiều nơi thì đưa vào aspect.”** Sai. Nghiệp vụ cốt lõi nên ở nơi chịu trách nhiệm nghiệp vụ. Chỉ dùng aspect khi sự tách biệt giúp bảo toàn ngữ nghĩa và làm rõ thiết kế.

## 9. Tự kiểm tra hiểu bài

**Tình huống 1:** Năm dịch vụ độc lập đều cần ghi thời gian thực thi và tỷ lệ thất bại. Đây có phải ứng viên AOP không?

Có, nếu cùng một quy tắc đo có thể được áp dụng nhất quán ở các ranh giới mà công cụ hỗ trợ. Một decorator/interceptor tường minh cũng có thể đủ tốt; lựa chọn dựa trên độ bao phủ, tính minh bạch và chi phí vận hành.

**Tình huống 2:** Hai kiểu đơn hàng tính phí vận chuyển khác nhau. Có nên tạo aspect để quyết định mức phí?

Thông thường không. Đây là quy tắc nghiệp vụ cần được biểu đạt bằng chính sách tính phí, mô hình đối tượng hoặc hàm miền phù hợp. Chỉ phần quan sát/kiểm toán chung cho những phép tính ấy mới là ứng viên AOP rõ ràng.

**Tình huống 3:** Advice đo thời gian chỉ chạy sau khi phương thức trả về một tác vụ bất đồng bộ. Nó đã đo hết thời gian xử lý chưa?

Chưa chắc. Nó có thể chỉ đo thời gian tạo và trả về tác vụ. Muốn đo đến lúc hoàn tất cần theo dõi vòng đời bất đồng bộ và dùng điểm can thiệp phù hợp.

**Tình huống 4:** Một pointcut chọn đúng `checkout()`, nhưng kiểm tra quyền không xảy ra ở một đường gọi. Điều gì cần xác minh?

Kiểm tra đường gọi có đi qua cơ chế can thiệp hay không, loại join point được hỗ trợ, phạm vi weaving, điều kiện khớp pointcut và thứ tự các advice. Không nên kết luận chỉ từ tên phương thức.

## 10. Kết luận

- **Thủ tục** diễn đạt các bước xử lý và luồng điều khiển.
- **OOP** phân chia dữ liệu, hành vi và trách nhiệm giữa các đối tượng.
- **AOP** tập trung mô-đun hóa và áp dụng các mối quan tâm xuyên suốt tại những điểm thực thi được lựa chọn.

Một thiết kế tốt có thể kết hợp cả ba: thuật toán rõ ràng trong phương thức, trách nhiệm nghiệp vụ rõ ràng giữa đối tượng, và chính sách kỹ thuật xuyên suốt được áp dụng nhất quán. Giá trị của AOP nằm ở việc giảm phân tán chính sách **khi cơ chế áp dụng chính xác, kiểm chứng được và không che khuất quy tắc nghiệp vụ quan trọng**.
