# Sai lầm: Bổ sung quá nhiều hành vi ẩn khiến chương trình khó hiểu

Aspect-Oriented Programming (AOP) giúp gom những hành vi xuyên suốt vào aspect, chọn nơi áp dụng qua pointcut rồi đưa advice vào luồng thực thi bằng weaving hoặc interception. Cơ chế này hữu ích khi cùng một trách nhiệm kỹ thuật xuất hiện ở nhiều điểm. Tuy nhiên, nếu một lời gọi tưởng như đơn giản lại bị nhiều advice tác động mà không có hợp đồng rõ ràng, **mã nhìn thấy và hành vi thật có thể khác nhau đáng kể**. Đó là lỗi thiết kế “bổ sung quá nhiều hành vi ẩn”.

Ví dụ, một lời gọi `charge(amount)` trong mã nguồn có thể bị bọc bởi advice kiểm toán, đo thời gian, đổi ngữ cảnh, kiểm tra điều kiện, mở transaction, retry, chuyển ngoại lệ và ghi log. Người đọc một phương thức không nhìn thấy ngay thứ tự thực thi hay số lần nghiệp vụ được gọi. Nếu một advice tự động retry thao tác thu tiền sau lỗi không chắc chắn, side effect có thể xảy ra hai lần. Nếu một advice nuốt ngoại lệ, caller có thể hiểu sai trạng thái giao dịch. Dù từng advice được viết “để tái sử dụng”, tổng thể trở nên khó dự đoán.

Bài này tập trung vào **AOP nói chung**, ở cả mức căn bản và nâng cao: cách nhận diện hành vi ẩn, kiểm soát phạm vi pointcut, thứ tự advice, thay đổi semantics, truy vết luồng thực thi, kiểm thử và lựa chọn thiết kế dễ bảo trì. Cú pháp hay khả năng áp dụng chi tiết phụ thuộc vào công cụ AOP và cách weaving, vì vậy không giả định mọi công cụ hỗ trợ cùng loại join point.

## 1. “Hành vi ẩn” trong AOP thực sự là gì?

Trong AOP, **join point** là điểm của quá trình thực thi có thể áp dụng logic bổ sung; **pointcut** mô tả tập join point; **advice** chạy ở trước, sau hoặc bao quanh điểm được chọn; **aspect** đóng gói concern và các quy tắc áp dụng. **Weaving** kết hợp logic của aspect với chương trình, trong khi một số cách hiện thực dùng proxy/interceptor để điều hướng lời gọi lúc chạy.

“Hành vi ẩn” không nhất thiết là điều xấu: đó là tính chất khi người đọc thân phương thức không thấy đầy đủ phần logic do AOP thêm vào. Mức độ rủi ro phụ thuộc vào **advice tác động đến điều gì**, **phạm vi áp dụng có dễ nhận biết hay không**, và **người phát triển có cách kiểm chứng hành vi thực tế hay không**.

Có thể chia hành vi theo mức độ can thiệp:

| Mức độ | Ví dụ | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Quan sát tương đối thụ động | Đếm lời gọi, ghi thời lượng, ghi trace | Chi phí hiệu năng, lỗi logger, dữ liệu nhạy cảm, đếm trùng |
| Thay đổi ngữ cảnh | Đặt correlation ID, mở/đóng scope, context thread | Rò rỉ context, sai thứ tự cleanup, mất context khi async |
| Kiểm soát đường gọi | Chặn khi thiếu điều kiện, giới hạn tốc độ, cache | Có thể bỏ qua method gốc hoặc trả kết quả khác |
| Thay đổi giao dịch/thử lại | Retry, timeout, transaction boundary, fallback | Có thể gọi lại tác vụ không idempotent hoặc che lỗi |
| Thay đổi dữ liệu/ngữ nghĩa | Sửa tham số, giá trị trả về, ngoại lệ hoặc side effect | Hợp đồng nghiệp vụ bị thay đổi ngoài mã phương thức |

Một advice quan sát vẫn có tác dụng phụ nếu logging đồng bộ gây chậm, ghi log thất bại làm ném ngoại lệ, hoặc tập metric dùng cardinality quá cao. Vì vậy chữ “quan sát” không phải giấy phép để bỏ kiểm thử.

Tính “ẩn” xuất hiện khi lời gọi trong mã và các phần mở rộng được lưu ở những nơi khác nhau. Tính **khó hiểu** xuất hiện khi người đọc không thể trả lời: *advice nào đang chạy, vì sao nó chạy, chạy trước hay sau advice khác, nó có đổi kết quả hoặc số lần gọi gốc không?*

## 2. Tình huống điển hình: một lời gọi, nhiều lớp hành vi

Giả sử caller gọi `processor.execute(request)` nhưng cùng join point được bao bởi các advice: bảo vệ đầu vào, ghi kiểm toán, đo thời gian và retry.

Luồng thực thi thực tế có thể mang dạng:

```text
Caller
  |
  v
Advice A: kiểm tra điều kiện
  |
  v
Advice B: bắt đầu ghi kiểm toán
  |
  v
Advice C: bắt đầu đo thời gian
  |
  v
Advice D: retry/fallback
  |
  +--> Target: execute(request)
  |       |
  |       +--> side effect / exception / return
  |       |
  |       +--> có thể được gọi lần nữa nếu D retry
  |
  v
Advice C: kết thúc đo thời gian
  |
  v
Advice B: kết thúc kiểm toán
  |
  v
Caller nhận kết quả hoặc ngoại lệ
```

Đây là **một cấu hình giả định** để minh họa. Thứ tự thật phải được xác định theo định nghĩa và cơ chế áp dụng của công cụ đang dùng; không được tự cho rằng mọi AOP engine sắp xếp advice giống sơ đồ này.

Bây giờ hãy đặt các câu hỏi mà mã phương thức gốc không trả lời:

- Bản ghi kiểm toán mô tả **một yêu cầu** hay **mỗi lần retry**?
- Timer đo **toàn bộ quá trình retry** hay **một lần thử**?
- Nếu target đã ghi dữ liệu nhưng ném timeout trước khi caller nhận xác nhận, việc retry có lặp side effect không?
- Khi advice kiểm tra điều kiện từ chối, kiểm toán có ghi nhận lần từ chối không?
- Nếu exporter log thất bại, advice quan sát có làm yêu cầu nghiệp vụ thất bại không?
- Nếu hai advice cùng chuyển đổi ngoại lệ, ngoại lệ nào đến caller?
- Nếu target gọi nội bộ một method khác, method đó có thật sự đi qua cơ chế interception hay không?

Mỗi câu đều cần câu trả lời dựa trên **hợp đồng hành vi và kiểm thử**, không dựa vào cảm giác “AOP đã lo hết”.

## 3. Dấu hiệu AOP đã tạo ra quá nhiều hành vi ngầm

### 3.1. Không thể suy ra tác động khi đọc hoặc debug một đường gọi

Bạn thấy một phương thức rất ngắn, nhưng lỗi hoặc dữ liệu trả về chỉ xuất hiện khi chạy trong cấu hình weaving thật. Unit test gọi thẳng đối tượng qua đường khác lại hoạt động bình thường. Điều này có thể do lời gọi trực tiếp bỏ qua proxy, do khác class loader, do pointcut không khớp ở môi trường test, hoặc do thứ tự advice thay đổi.

Dấu hiệu đặc biệt rõ khi người debug phải mở hàng loạt file cấu hình, aspect và danh sách agent để tìm vì sao method được gọi lại, ném ngoại lệ khác hoặc thay dữ liệu.

### 3.2. Mỗi aspect trở thành nơi thêm chức năng mới

Một aspect ban đầu chỉ đo thời gian, sau đó được thêm điều kiện cấp quyền, ghi kiểm toán, cache và fallback để “tiện tận dụng pointcut có sẵn”. Lúc này cùng một aspect có nhiều **lý do thay đổi độc lập**, khó kiểm chứng và khó rollback. Số dòng mã nghiệp vụ có thể giảm, nhưng mức coupling và chi phí suy luận tăng.

Nên tách concern theo hợp đồng riêng: concern đo thời gian, concern kiểm toán, concern điều khiển retry. Tuy nhiên tách thành nhiều aspect vẫn chưa đủ nếu chúng có thứ tự phụ thuộc mơ hồ hoặc pointcut quá rộng. Cần giới hạn điểm áp dụng và tài liệu hóa tương tác.

### 3.3. Pointcut mang tính suy đoán

Một pointcut chọn mọi phương thức bắt đầu bằng `save`, `validate` hoặc mọi phương thức trong một package lớn có thể vô tình nhận thêm join point khi người khác đổi tên class hoặc thêm hàm mới. Tên phương thức và vị trí source là **đặc điểm cấu trúc**, không tự bảo đảm có chung semantics.

Nếu muốn áp dụng một chính sách kỹ thuật cho tập thao tác cụ thể, cần mô tả **tập thao tác mục tiêu** bằng điều kiện có ý nghĩa và có test khẳng định cả trường hợp được chọn lẫn không được chọn.

### 3.4. Advice âm thầm đổi hợp đồng return/exception

Một around advice có thể gọi target không đủ lần, gọi hai lần hoặc không gọi, sửa tham số, bắt ngoại lệ rồi trả giá trị mặc định. Điều đó có thể là hành vi được thiết kế hợp lệ cho một concern cụ thể, nhưng khi bị ẩn và không được công bố thì rất nguy hiểm.

Caller cần biết liệu thao tác có thể bị retry, ngắt trước khi vào target, bị trả kết quả cache, hay được chuyển ngoại lệ. **Thay đổi semantics phải được xem như thay đổi API/hợp đồng**, dù nó được triển khai bằng advice.

### 3.5. Lỗi chỉ xảy ra khi có tương tác giữa nhiều advice

Advice A hoạt động đúng khi đứng một mình, advice B cũng vậy, nhưng A+B tạo ra:

- Trace ghi hai lần hoặc thừa một span khi chạy lồng nhau.
- Timer bị tính ngoài ranh giới mong muốn.
- Transaction đóng trước khi advice đọc dữ liệu trả về.
- Retry lặp một side effect không idempotent.
- Cleanup context sai thứ tự, gây rò dữ liệu sang yêu cầu khác.
- Deadlock khi advice logging dùng cùng lock hoặc phụ thuộc thao tác đang được intercept.

Vấn đề nằm ở **tương tác và thứ tự**, không nhất thiết ở từng advice đơn lẻ.

## 4. Cơ chế AOP làm tăng hoặc giảm độ khó theo dõi

Không thể đánh giá hành vi ẩn chỉ từ tên “AOP”; phải xét cách áp dụng.

| Cách áp dụng | Điều giúp truy vết | Rủi ro thường gặp |
| --- | --- | --- |
| Weaving khi biên dịch | Có thể lưu/kiểm tra class đã weave; build tái hiện được | Mã chạy khác source nhìn thấy, khó suy ra từ source nếu không có bản đồ weave |
| Weaving sau biên dịch | Có artifact đầu vào/đầu ra để so sánh | Có thể dệt thêm ngoài ý muốn, ảnh hưởng metadata/chữ ký hoặc binary compatibility |
| Weaving lúc tải lớp | Có thể bật/tắt hoặc thay cấu hình agent theo môi trường | Hai môi trường có cùng JAR nhưng khác agent/cấu hình cho hành vi khác nhau |
| Proxy/interception runtime | Có điểm bao rõ ràng nếu wiring tường minh | Một số lời gọi không đi qua proxy, có thể có nhiều lớp proxy lồng nhau |

**Ghi nhớ:** một số cơ chế chỉ intercept method execution; một số khác có thể xử lý call, constructor, field access hoặc loại join point khác. Không nên mô tả tất cả advice như thể chúng luôn xuất hiện ở mọi đường gọi.

Đặc biệt, với các proxy chỉ chặn lời gọi qua một đối tượng wrapper, lời gọi trực tiếp vào target hoặc self-invocation có thể không đi qua wrapper. Với weaving bytecode, hành vi lại phụ thuộc các loại join point, thời điểm dệt và class loader. Test phải dùng **đúng đường chạy sản xuất** để chứng minh điểm áp dụng.

Mức dễ hiểu còn phụ thuộc công cụ có xuất danh sách class/join point đã weave, thống kê advice match, cấu hình order và dấu vết thực thi hay không. Khi công cụ hỗ trợ, nên lưu các thông tin đó cùng artifact phát hành hoặc report kiểm thử.

## 5. Chỉ cho phép advice ẩn trong một “ngân sách hành vi”

Để tránh thiết kế ngày càng khó đoán, nhóm phát triển có thể đặt một **hợp đồng cho mỗi concern** với các trường tối thiểu:

| Trường | Cần mô tả |
| --- | --- |
| Mục đích | Aspect thêm điều gì và ai sở hữu trách nhiệm này? |
| Phạm vi | Những join point nào phải áp dụng, những điểm nào phải loại trừ? |
| Cơ chế | Compile-time, load-time, post-compile hay proxy/interception? |
| Thời điểm và thứ tự | Before/after/around, tương tác với advice khác theo thứ tự nào? |
| Target invocation | Có gọi đúng một lần, có thể bỏ qua hoặc retry? Điều kiện cụ thể là gì? |
| Kết quả và ngoại lệ | Có giữ nguyên, chuyển đổi hay che giấu? Caller biết bằng cách nào? |
| Side effect | Ghi log, mạng, I/O, transaction, cache, dữ liệu nào bị thay đổi? |
| Failure policy | Lỗi của chính advice có khiến tác vụ gốc thất bại không? |
| Concurrent/async | Context và trạng thái dùng chung được truyền/dọn như thế nào? |
| Bằng chứng | Test pointcut, order, semantics, log/tracing và chi phí tài nguyên |

Nếu không giải thích được một trường quan trọng, có thể điểm áp dụng đang quá rộng hoặc đang cố giấu một trách nhiệm vốn cần được gọi trực tiếp.

Ví dụ hợp đồng cho advice đo thời gian:

> “Chỉ quan sát các lời gọi thuộc nhóm thao tác X, không sửa tham số, kết quả hoặc ngoại lệ; bắt đầu timer trước lần gọi gốc, ghi kết quả trong finally, không retry; lỗi xuất metric được xử lý theo chính sách đã định; timer đo một lần gọi toàn bộ; ghi dữ liệu có giới hạn và không chứa dữ liệu nhạy cảm.”

Ngay cả hợp đồng này còn cần trả lời: khi một around advice retry khác bọc bên ngoài/ở trong timer, “một lần gọi toàn bộ” là một yêu cầu hay một attempt? **Thứ tự advice phải được kiểm chứng cùng với định nghĩa đơn vị đo.**

## 6. Ví dụ Java 17: thấy rõ thứ tự hai lớp advice

Đoạn Java dưới đây dùng **JDK dynamic proxy** để minh họa interception và thứ tự các lớp wrapper. Đây là một ví dụ runnable độc lập nhằm làm lộ call chain; không phải trình dệt mã tổng quát và không đại diện cho mọi loại join point của mọi hệ AOP.

Chương trình dùng một tác vụ có thể thành công hoặc ném ngoại lệ. Hai lớp có nhãn `audit` và `metrics` chỉ ghi dấu vào danh sách trong bộ nhớ để quan sát thứ tự, không triển khai hệ thống kiểm toán hay thu thập chỉ số thật.

Lưu thành `HiddenAdviceDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class HiddenAdviceDemo {
    @FunctionalInterface
    public interface Task {
        String run(String input);
    }

    static Task surround(Task target, String name, List<String> events) {
        return (Task) Proxy.newProxyInstance(
                Task.class.getClassLoader(),
                new Class<?>[] { Task.class },
                (proxy, method, args) -> {
                    if (!method.getName().equals("run")) {
                        return method.invoke(target, args);
                    }

                    events.add(name + ":before");
                    try {
                        Object result = method.invoke(target, args);
                        events.add(name + ":after");
                        return result;
                    } catch (InvocationTargetException ex) {
                        events.add(name + ":error");
                        throw ex.getCause();
                    }
                });
    }

    static void execute(Task task, String input) {
        try {
            System.out.println("Result: " + task.run(input));
        } catch (IllegalArgumentException ex) {
            System.out.println("Error: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        Task core = input -> {
            events.add("core");
            if (input.isBlank()) {
                throw new IllegalArgumentException("blank input");
            }
            return "accepted:" + input;
        };

        Task observed = surround(
                surround(core, "audit", events),
                "metrics",
                events
        );

        execute(observed, "A");
        execute(observed, "");
        System.out.println("Trace: " + String.join(" | ", events));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 HiddenAdviceDemo.java
java HiddenAdviceDemo
```

Stdout xác định:

```text
Result: accepted:A
Error: blank input
Trace: metrics:before | audit:before | core | audit:after | metrics:after | metrics:before | audit:before | core | audit:error | metrics:error
```

**Giải thích:**

1. Ở `observed`, wrapper metrics nằm **ngoài** wrapper audit, nên chạy `metrics:before` trước `audit:before`; lúc thành công, `audit:after` diễn ra trước `metrics:after`.
2. Khi input rỗng, method gốc ném `IllegalArgumentException`. Reflection bọc ngoại lệ trong `InvocationTargetException`; wrapper unwrap bằng `ex.getCause()`, nên caller nhận lại lỗi gốc, không có bản ghi `:after` trên đường lỗi.
3. Mỗi lần gọi method gốc đúng một lần trong ví dụ. Nếu thêm advice retry, phải kiểm chứng lại số lần gọi và tính idempotent của side effect.
4. Việc gắn wrapper trong `main` là một **điểm lắp ráp tường minh** để nhìn thấy hai lớp behavior. Trong hệ thống dùng pointcut/weaving, sự lắp ráp có thể do cơ chế AOP thực hiện; cần cung cấp tài liệu hoặc công cụ truy vết tương đương.
5. `ArrayList` chỉ phục vụ demo chạy tuần tự. Khi có nhiều thread, phải chọn cấu trúc dữ liệu và chiến lược truyền context an toàn. Không dùng danh sách không đồng bộ này để làm log dùng chung ngoài production.

Nếu đổi thứ tự thành `surround(surround(core, "metrics", events), "audit", events)`, advice audit sẽ thành lớp ngoài. Kết quả nghiệp vụ vẫn có thể giống nhau nhưng **thứ tự sự kiện, khoảng thời gian đo và semantics trong tình huống lỗi có thể đổi**. Đây là lý do không nên coi thứ tự advice là một chi tiết phụ.

## 7. So sánh trước và sau khi kiểm soát hành vi ẩn

Hãy xét cùng một nghiệp vụ `saveDocument`.

**Thiết kế khó hiểu:** một method đơn giản bị pointcut bắt vào nhiều aspect: cache tự động, retry, kiểm toán, đo thời gian, chuyển exception và thông báo. Danh sách aspect nằm ở nhiều nơi; không có mô tả thứ tự và không có test kiểm tra số lần target chạy. Người sửa phương thức không thể biết tác động nếu thêm một thao tác ghi file.

**Thiết kế dễ hiểu hơn:** phương thức nghiệp vụ biểu diễn trực tiếp các bước có ý nghĩa miền; các concern kỹ thuật có hợp đồng riêng; danh sách join point và thứ tự được ghi nhận ở điểm cấu hình/weaving; test xác minh tương tác giữa các advice. Hành vi ảnh hưởng mạnh đến semantics (như retry một thao tác có side effect) được mô tả ở API hoặc tổ chức thành bước gọi tường minh khi cần.

| Thuộc tính | Nhiều hành vi ẩn không kiểm soát | Hành vi AOP có hợp đồng |
| --- | --- | --- |
| Đọc hiểu | Phải phỏng đoán và truy tìm nhiều aspect | Biết tập pointcut, thứ tự và chính sách từ tài liệu/cấu hình |
| Thay đổi | Một aspect sửa có thể tác động ngoài ý muốn | Có owner, phạm vi, test positive/negative |
| Debug | Dễ bỏ sót advice khi xem source và stack | Có trace hoặc bản đồ các advice đã áp dụng |
| Ngoại lệ | Bị đổi hoặc nuốt mà caller không biết | Có hợp đồng truyền/biến đổi lỗi được kiểm thử |
| Hiệu năng | Chi phí tích lũy ở nhiều join point | Có ngân sách overhead và benchmark đại diện |
| Triển khai | Môi trường có thể khác agent/weaving | Ghi rõ version, mode và cấu hình khởi động |

Cần nhấn mạnh: “có hợp đồng” không có nghĩa loại bỏ mọi chức năng AOP. Nó làm cho các tác động xuyên suốt **có thể phát hiện, hiểu, đo và thử nghiệm**.

## 8. Những vấn đề nâng cao khi nhiều aspect tương tác

### 8.1. Thứ tự advice không mang tính giao hoán

Hai advice A và B nhìn có vẻ độc lập nhưng nói chung `A(B(target))` không tương đương `B(A(target))`.

Ví dụ, đặt timer **ngoài** advice retry sẽ đo toàn bộ thời gian của các attempt và thời gian chờ giữa attempt; đặt timer **trong** retry sẽ đo từng attempt riêng. Đặt kiểm toán bên trong retry có thể ghi một bản ghi cho mỗi lần thử; đặt ngoài có thể chỉ ghi một bản ghi ở cấp yêu cầu. Cả hai cách đều có thể hữu ích nếu phù hợp mục tiêu, nhưng phải chọn có chủ đích.

Nếu bộ công cụ AOP có cơ chế chỉ định precedence/order, quản lý nó như một phần hợp đồng. Nếu không hỗ trợ order đủ rõ, cân nhắc đóng gói tương tác liên quan trong một thành phần tường minh hoặc tránh mô hình phụ thuộc vào thứ tự ngầm.

### 8.2. Retry, timeout và side effect không idempotent

Advice có thể khiến một method gốc chạy nhiều lần. Với thao tác đọc thuần, có thể ít rủi ro hơn; với gửi email, trừ tiền, ghi file hoặc gọi API có side effect, việc retry có thể gây trùng. **AOP không tự bảo đảm idempotency hoặc exactly-once semantics.**

Nếu cần retry, xác định trường hợp lỗi nào cho phép retry, giới hạn lần thử, khoảng đợi, idempotency key, cơ chế deduplication và trạng thái giao dịch. Khi các điều kiện gắn chặt vào use case cụ thể, một API retry được gọi tường minh có thể làm logic dễ hiểu hơn aspect rộng.

Timeout cũng cần phân biệt **ngừng chờ** với **dừng thực thi**. Một advice báo timeout không đồng nghĩa tác vụ gốc đã dừng hoặc side effect đã được rollback; điều này phụ thuộc cơ chế và khả năng hủy ở tầng thấp.

### 8.3. Chuyển ngoại lệ và chính sách thất bại

Advice quan sát thường muốn ghi lỗi rồi phát lại lỗi gốc. Nếu ghi log thất bại ngay trong quá trình xử lý ngoại lệ, lỗi phụ có thể che ngoại lệ nghiệp vụ. Hãy xác định ưu tiên: lỗi nào là lỗi chính, lỗi nào chỉ là thông tin bổ sung, và liệu thất bại của kênh metric có làm hỏng tác vụ không.

Đối với advice dạng around, một mẫu khái niệm được sử dụng khi cần cleanup là:

```text
before
try:
    result = proceed to the original invocation
    return result
finally:
    release context or record completion
```

Đây là **pseudocode**, không phải cú pháp chung của mọi công cụ AOP. Nó chỉ minh họa nguyên tắc cleanup cho cả thành công và ngoại lệ; chính sách xử lý lỗi trong finally vẫn phải được thiết kế để không vô ý che ngoại lệ gốc.

### 8.4. Context theo luồng và bất đồng bộ

ThreadLocal có thể hỗ trợ ngữ cảnh ở luồng đồng bộ, nhưng một tác vụ bất đồng bộ hoặc chuyển thread có thể mất context nếu không truyền tường minh. Ngược lại, không dọn ThreadLocal đúng cách có thể rò dữ liệu sang yêu cầu khác khi luồng được tái sử dụng.

Khi dùng aspect để mở/đóng trace hoặc security context, cần phân biệt **kết thúc lời gọi trả về** với **hoàn tất công việc bất đồng bộ**. Nếu method trả về một đối tượng biểu diễn tác vụ chưa hoàn tất, advice chạy sau khi method trả về chưa chắc tương đương “công việc đã xong”. Hợp đồng phải quy định rõ điểm hoàn tất nào được quan sát.

### 8.5. Reentrancy và chặn nhầm hạ tầng

Nếu pointcut chặn vào chính phương thức mà logger/metric exporter gọi, advice có thể tự gọi lại chính nó. Kết quả có thể là vòng lặp, log trùng, stack overflow hoặc khuếch đại tải. Cần loại trừ hạ tầng khỏi tập pointcut, hoặc sử dụng cơ chế guard/reentrancy control đã được kiểm chứng.

Đừng chỉ kiểm tra tên method; xác nhận danh sách join point thực tế và các tình huống nested invocation để chắc chắn guard không che cả lời gọi hợp lệ.

### 8.6. Trạng thái dùng chung và tính đồng thời

Một aspect có state chia sẻ giữa các lời gọi có thể tạo race condition khi viết bộ đếm, cache, map hoặc correlation state. Nếu phải ghi metric, chọn primitive hoặc bộ thu thập được thiết kế cho concurrency, và tránh giữ dữ liệu request trong field dùng chung không được đồng bộ.

Không thể suy ra “advice chạy quanh mỗi method” là mỗi advice có instance riêng. Lifecycle/instance semantics phụ thuộc ngôn ngữ và framework AOP được dùng; khi thiếu cơ chế cô lập rõ ràng, phải kiểm tra concurrency và scope của trạng thái.

## 9. Thiết kế pointcut có thể kiểm chứng

Một pointcut an toàn cần xác định **vì sao** join point thuộc phạm vi, không chỉ nó trông như thế nào. Ví dụ “mọi phương thức có tiền tố get” quá rộng để mặc định gắn logging của dữ liệu nhạy cảm; một nhóm thao tác đã định nghĩa hợp đồng quan sát, với chính sách loại trừ dữ liệu, thường rõ ràng hơn.

Một bộ kiểm thử nên có:

- **Positive cases:** gọi đúng các join point phải nhận advice và đếm chính xác số lần chạy.
- **Negative cases:** utility, method nội bộ, điểm xử lý dữ liệu nhạy cảm hoặc lớp ngoài phạm vi phải không bị bắt.
- **Boundary cases:** method overload, cùng tên khác package, lớp kế thừa, generic bridge, self-invocation, caller khác class loader nếu được hệ thống sử dụng.
- **Failure cases:** method gốc ném checked/unchecked exception, advice ném lỗi, method chưa bắt đầu do guard, hoặc lời gọi bị retry.
- **Evolution cases:** thêm một method mới có tên trùng mẫu wildcard không làm aspect tự mở rộng ngoài hợp đồng.

Không phải mọi công cụ hỗ trợ tất cả join point trong danh sách. Chỉ kiểm tra những trường hợp thực sự tương ứng với cơ chế AOP đang chạy; điều quan trọng là test **tập điểm phải bắt và tập điểm không được bắt**, trên đúng artifact đã weave hoặc đúng đường proxy/runtime.

Cách quản lý hiệu quả là lưu **bản kê concern → pointcut → advice → nơi áp dụng → owner**. Khi xuất bản artifact, ghi nhận phiên bản toolchain và cấu hình weaving để người khác có thể tái hiện chính xác hành vi quan sát.

## 10. Kiểm thử hành vi tích hợp, không chỉ unit test cho từng advice

Unit test advice đơn lẻ không chứng minh A+B+C hoạt động đúng khi chồng lên nhau. Nên có một số bài test ở mức chương trình thực thi:

| Nhóm test | Cần khẳng định |
| --- | --- |
| Semantics | Bật/tắt advice quan sát cho cùng giá trị trả về và ngoại lệ; tác vụ gốc không bị thay đổi không chủ đích |
| Invocation count | Target chạy đúng số lần; nếu retry được phép, số lần phù hợp chính sách |
| Ordering | Before/after/error/cleanup diễn ra theo trật tự quy định |
| Pointcut coverage | Chỉ những join point đã công bố được chặn; negative cases phải không phát sinh advice |
| Error handling | Exception gốc được giữ hoặc đổi đúng hợp đồng; lỗi advice không che lỗi chính ngoài dự kiến |
| Concurrent execution | Không race, mất context hoặc rò state giữa yêu cầu |
| Async completion | Nếu method trả kết quả tương lai, advice đo đúng mốc hoàn tất theo hợp đồng |
| Resource usage | Chi phí CPU, allocation, GC, I/O, latency p95/p99 ở tải đại diện đạt ngưỡng |
| Deployment parity | Build/test và runtime thực sự sử dụng cùng mode, phiên bản weaver/agent và cấu hình cần thiết |

Đối với một aspect vốn được thiết kế chỉ để quan sát, **kiểm tra tương đương hành vi trước–sau** là một tiêu chuẩn rất có giá trị. Với aspect chủ động thay đổi semantics, cần test chính thay đổi đó như một phần API; không thể đòi hỏi tương đương tuyệt đối rồi bỏ qua mục tiêu thiết kế.

Nên có fixture giúp thu thập thứ tự sự kiện theo cách xác định, giống ví dụ Java ở trên. Các assertions về trace có thể chỉ ra chính xác lớp advice đã thay đổi. Ở production, hãy gắn correlation ID và log có cấu trúc, nhưng tránh log tham số/giá trị trả về chứa thông tin nhạy cảm.

## 11. Truy vết khi hành vi runtime khác source

Một quy trình debug thực dụng:

1. **Tái hiện từ đúng entry point.** Đảm bảo caller đi qua proxy hoặc bytecode đã weave, đúng cấu hình và đúng biến thể runtime.
2. **Xác định cơ chế AOP.** Hỏi build-time, post-compile, load-time hay runtime interceptor; ghi phiên bản công cụ, agent, class loader và cấu hình.
3. **Liệt kê aspect áp dụng.** Dựa trên báo cáo weaving, instrumentation logs, pointcut matching hoặc traces của hệ thống thực tế nếu có. Không suy từ source một mình.
4. **Dựng thứ tự before/around/after.** Vẽ call chain từ ngoài vào trong; xác định advice nào có thể bỏ qua, retry, thay tham số, sửa return hoặc exception.
5. **So sánh đường có và không có advice.** Dùng baseline có kiểm soát, giữ cùng input và dữ liệu, kiểm tra semantics và side effect. Không tắt logic bảo vệ bắt buộc ngoài môi trường thử nghiệm được kiểm soát.
6. **Kiểm tra số lần gọi.** Phân biệt một yêu cầu, một attempt và một join point; đếm target invocation và external calls để tìm duplicate.
7. **Kiểm tra lỗi thứ cấp.** Logger, telemetry, context cleanup hay exporter có lỗi trước khi lỗi gốc được truyền lên không?
8. **Kiểm tra hiệu năng và concurrency.** Dùng latency, allocation, GC, queue hoặc profiler khi nghi ngờ advice làm hệ thống chậm hoặc race.
9. **Ghi lại kết quả.** Cập nhật hợp đồng pointcut/advice và test regression, thay vì chỉ vá lỗi ở một luồng chạy.

Stack trace có thể giúp nhưng không luôn hiển thị cấu trúc pointcut đầy đủ. Một số công cụ weaving biến đổi bytecode hoặc sinh wrapper khiến đường đi khó nhìn từ trace đơn thuần; cần kết hợp cấu hình và bằng chứng runtime.

## 12. Cách giảm hành vi ẩn mà vẫn giữ lợi ích AOP

**Giới hạn một aspect vào một concern nhất quán.** Nếu một aspect vừa làm cache, vừa retry, vừa ghi kiểm toán, vừa thay quy tắc nghiệp vụ, nên phân tách trách nhiệm. Sau khi tách, xác định lại thứ tự và tương tác, không chỉ chia file.

**Thu hẹp pointcut.** Chọn tập join point dựa trên nghĩa của ranh giới kỹ thuật hoặc hợp đồng đã được phê duyệt. Định nghĩa exclusions và có test negative để ngăn thêm method mới bị bắt tình cờ.

**Làm lộ ranh giới áp dụng.** Dù AOP thực thi tự động, kiến trúc cần có tài liệu hoặc bản đồ “method nhóm X → những advice Y,Z” để reviewer dễ truy tìm. Nếu công cụ không thể liệt kê tự động, lưu một bảng ngắn gọn được review cùng mã.

**Giữ các quy tắc miền dễ thấy.** Những quyết định như cách tính giá, phê duyệt giao dịch hoặc điều kiện hoàn tiền thường cần biểu diễn rõ bằng domain policy/service hoặc lời gọi tường minh. Chỉ đưa vào aspect khi đó thật sự là một concern xuyên suốt có hợp đồng phù hợp và các giới hạn được hiểu rõ.

**Hạn chế around advice có quyền đổi control flow.** Advice chỉ quan sát nên giữ nguyên kết quả/ngoại lệ và thường tránh gọi lại target. Những advice có quyền retry, short-circuit, cache hoặc fallback phải được review ở mức semantics, vì chúng tác động trực tiếp tới số lần gọi và side effect.

**Cho phép vô hiệu hóa có kiểm soát để chẩn đoán.** Ở môi trường test, cấu hình độc lập từng concern giúp so sánh nguyên nhân. Không mặc định tắt aspect bảo vệ bắt buộc ở production để tìm lỗi; ưu tiên test fixture và chế độ chẩn đoán đã được phê duyệt.

**Cân nhắc decorator hoặc lời gọi tường minh.** Khi số điểm áp dụng nhỏ hoặc thứ tự hành vi là cốt lõi nghiệp vụ, một chuỗi decorator được lắp ráp tại composition root có thể dễ đọc hơn pointcut rộng. AOP vẫn phù hợp khi hành vi xuyên suốt nhiều join point và cơ chế áp dụng được quản lý tốt.

**Tạo bằng chứng vận hành.** Advice count, error rate, CPU, allocation, p95/p99 latency, dropped telemetry, queue depth và số lần retry giúp phát hiện bất thường mà đọc source không thấy. Chọn metric phù hợp concern, tránh tự biến instrumentation thành điểm nghẽn.

## 13. Sai lầm khi “sửa” sự khó hiểu

| Cách xử lý có vẻ nhanh | Tại sao chưa đủ | Cách cải thiện |
| --- | --- | --- |
| Chỉ thêm comment ở method gốc | Comment có thể lỗi thời khi pointcut đổi | Tài liệu hóa hợp đồng ở nguồn cấu hình và test áp dụng |
| Chỉ đổi tên aspect rõ hơn | Không giải quyết được order và side effect | Ghi rõ phạm vi, semantics, failure policy và precedence |
| Dồn nhiều aspect thành một file | Vẫn có nhiều lý do thay đổi trong cùng đơn vị | Tách theo concern và quản lý tương tác |
| Bắt tất cả method rồi dùng if trong advice | Phạm vi chặn quá lớn và khó đánh giá overhead | Thu hẹp pointcut ngay từ đầu |
| Chỉ kiểm thử đường chạy thành công | Bỏ qua retry, ngoại lệ và cleanup | Thử lỗi, negative cases, concurrency và async |
| Tắt một advice rồi kết luận đã tìm nguyên nhân | Có thể chỉ thay thứ tự và che triệu chứng | Dựng call chain, so paired baseline và ghi số lần target gọi |
| In toàn bộ input/output để debug | Có thể lộ dữ liệu và làm tăng chi phí | Log có cấu trúc, tối thiểu hóa thông tin, sampling theo chính sách |
| Giả định mọi advice “trong suốt” | Retry/cache/short-circuit có chủ đích thay đổi semantics | Phân loại rõ advice quan sát và advice điều khiển |

Một số thay đổi thiết kế nên được nhìn như một thay đổi API: nếu thêm aspect làm method có thể được gọi hai lần, trả từ cache hoặc đổi loại exception, review và test theo tác động tới caller chứ không theo số dòng mới của aspect.

## 14. Checklist review một aspect trước khi triển khai

- [ ] Aspect có **một concern rõ ràng** và một chủ thể chịu trách nhiệm.
- [ ] Pointcut dựa trên hợp đồng áp dụng, có danh sách trường hợp thuộc/không thuộc phạm vi.
- [ ] Biết chính xác cơ chế interception/weaving và các giới hạn join point.
- [ ] Có tài liệu hóa thứ tự với các advice khác và test order quan trọng.
- [ ] Xác định số lần target được gọi: một, nhiều, hoặc có thể bị bỏ qua.
- [ ] Giá trị trả về và exception được bảo toàn hoặc biến đổi đúng hợp đồng công khai.
- [ ] Side effect do advice tạo ra được công bố: log, network, cache, transaction, retry, tracing.
- [ ] Chính sách thất bại của advice rõ ràng, đặc biệt lỗi logging/telemetry/cleanup.
- [ ] Không để pointcut tự bắt hạ tầng của nó và gây recursion hay nhân đôi.
- [ ] State/concurrency và async context được kiểm thử ở đường chạy thực.
- [ ] Có cách xem danh sách advice được áp dụng vào một điểm và truy dấu khi debug.
- [ ] Đã đo overhead với tải đại diện nếu advice nằm trên đường gọi nóng.
- [ ] Test tích hợp xác minh semantics khi nhiều advice chồng lên nhau.
- [ ] Môi trường runtime dùng đúng phiên bản, artifact và cấu hình đã được kiểm thử.

**Nguyên tắc thực hành:** AOP có giá trị khi làm cho trách nhiệm xuyên suốt dễ duy trì **mà không khiến hành vi quan trọng trở thành bí ẩn**. Khi thêm một advice, luôn biết nó chạy ở đâu, khi nào, theo thứ tự nào, có thể đổi điều gì và làm sao chứng minh được điều đó. Nếu những câu hỏi này không có đáp án, việc ẩn thêm hành vi sau pointcut sẽ khiến chương trình ngày càng khó hiểu dù thân phương thức có ít dòng hơn.
