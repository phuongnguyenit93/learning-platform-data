# Nhận diện scattering và tangling trong chương trình mẫu

Một trong những lý do quan trọng để tìm hiểu **lập trình hướng khía cạnh (aspect-oriented programming, AOP)** là nhận ra khi nào các chức năng xuyên suốt bị phân tán ở nhiều vị trí và bị trộn với nghiệp vụ. Hai hiện tượng thường được nhắc đến là **scattering** và **tangling**. Chúng khác nhau nhưng thường cùng tồn tại: một yêu cầu như ghi audit có thể xuất hiện ở hàng chục phương thức (scattering), trong khi ở từng phương thức, audit lại xen giữa kiểm tra đầu vào, tính toán và trả kết quả (tangling).

Bài học này là một **bài tập tổng hợp**. Bạn sẽ đọc chương trình Java 17+ chạy được, xác định các concern, đánh dấu bằng chứng scattering/tangling, phân tích rủi ro bảo trì, đề xuất điểm chặn (*join point*) và điều kiện chọn (*pointcut*), rồi so sánh hành vi trước/sau khi tách xử lý xuyên suốt bằng một proxy minh họa. Mục tiêu không phải biến mọi đoạn code trùng lặp thành aspect: chỉ chọn tách khi đó thật sự là một *cross-cutting concern* và cấu trúc mới bảo toàn các yêu cầu chức năng.

## 1. Phân biệt chính xác hai hiện tượng

**Concern** là một trách nhiệm hoặc yêu cầu mà chương trình phải đáp ứng, ví dụ tính giá hóa đơn, kiểm tra tồn kho, ghi sự kiện kiểm toán, theo dõi thời gian xử lý hay xác thực quyền truy cập.

**Scattering (phân tán)** xuất hiện khi **cùng một concern** phải được triển khai hoặc sửa ở **nhiều vị trí khác nhau** của codebase. Ví dụ mọi thao tác thay đổi dữ liệu đều tự ghi hai dòng audit; khi đổi cấu trúc sự kiện audit phải sửa trên hàng chục lớp.

**Tangling (đan xen)** xuất hiện khi **nhiều concern riêng biệt bị trộn vào cùng một đơn vị mã**, thường cùng phương thức hoặc lớp, khiến luồng nghiệp vụ bị ngắt bởi logging, audit, xử lý quyền hoặc cơ chế hạ tầng.

Để ghi nhớ:

| Thuộc tính | Scattering | Tangling |
|---|---|---|
| Góc quan sát | Một concern trải rộng ra nhiều chỗ | Nhiều concern đan trong một chỗ |
| Câu hỏi nhận diện | “Muốn đổi concern này phải sửa bao nhiêu vị trí?” | “Phương thức này đang xử lý bao nhiêu trách nhiệm?” |
| Ví dụ | `TRACE begin/end` lặp trong 20 service | `TRACE`, kiểm tra input, tính tiền, `AUDIT` nằm trong cùng phương thức |
| Rủi ro thường thấy | Sửa thiếu, không đồng nhất hành vi, khó thay chính sách | Khó hiểu luồng chính, khó kiểm thử riêng, dễ sai thứ tự xử lý |
| Hướng cải thiện | Gom chính sách xuyên suốt về nơi thống nhất | Tách xử lý xuyên suốt khỏi logic nghiệp vụ |
| Điều cần bảo vệ | Không bỏ sót điểm nghiệp vụ phải chặn | Không đổi thứ tự tác dụng phụ, outcome hoặc ngoại lệ |

**Không phải cứ xuất hiện hai dòng giống nhau là scattering đáng tách bằng AOP.** Công thức nghiệp vụ hoặc điều kiện đầu vào trùng nhau có thể thuộc một hàm domain chung, value object hoặc policy domain, không phải aspect. **Không phải phương thức dài nào cũng tangling:** độ dài là tín hiệu đọc mã, còn tangling liên quan ranh giới trách nhiệm.

## 2. Chương trình mẫu: hai nghiệp vụ cùng lặp tracing và audit

Tình huống: một hệ thống có dịch vụ lập hóa đơn và dịch vụ giữ hàng. Mỗi phương thức cần làm ba nhóm việc:

1. **Nghiệp vụ:** kiểm tra số lượng và tính tổng tiền hoặc số hàng còn lại.
2. **Tracing:** in dấu thời điểm đi vào/đi ra để quan sát đường gọi.
3. **Audit thành công:** ghi sự kiện khi thao tác nghiệp vụ hoàn tất bình thường.

Trong phiên bản đầu, mỗi dịch vụ tự viết các thao tác tracing và audit. Mã cố ý không sử dụng bất kỳ công cụ AOP nào để người học nhận diện từ cấu trúc Java thông thường.

Tạo tệp `ScatteringTanglingBefore.java`:

```java
public class ScatteringTanglingBefore {
    static final class InvoiceService {
        int issue(int count) {
            System.out.println("TRACE invoice.enter");  // I1
            try {
                if (count <= 0) {                        // I2
                    throw new IllegalArgumentException(
                        "count must be positive"
                    );
                }

                int total = count * 10;                 // I3
                System.out.println("AUDIT invoice.issued"); // I4
                return total;                           // I5
            } finally {
                System.out.println("TRACE invoice.exit"); // I6
            }
        }
    }

    static final class StockService {
        int reserve(int units) {
            System.out.println("TRACE stock.enter");    // S1
            try {
                if (units <= 0 || units > 20) {          // S2
                    throw new IllegalArgumentException(
                        "units out of range"
                    );
                }

                int remaining = 20 - units;             // S3
                System.out.println("AUDIT stock.reserved"); // S4
                return remaining;                       // S5
            } finally {
                System.out.println("TRACE stock.exit"); // S6
            }
        }
    }

    public static void main(String[] args) {
        var invoice = new InvoiceService();
        var stock = new StockService();

        System.out.println("Invoice result: " + invoice.issue(3));
        System.out.println("Stock result: " + stock.reserve(4));

        try {
            stock.reserve(25);
        } catch (IllegalArgumentException exception) {
            System.out.println("Error: " + exception.getMessage());
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac ScatteringTanglingBefore.java
java ScatteringTanglingBefore
```

Stdout chính xác:

```text
TRACE invoice.enter
AUDIT invoice.issued
TRACE invoice.exit
Invoice result: 30
TRACE stock.enter
AUDIT stock.reserved
TRACE stock.exit
Stock result: 16
TRACE stock.enter
TRACE stock.exit
Error: units out of range
```

**Đọc luồng thực thi trước khi trả lời.** Khi `issue(3)` thành công, audit được in sau phép tính, còn `finally` in dấu thoát trước khi caller nhận kết quả. Khi `reserve(25)` ném ngoại lệ, audit thành công **không được in**, nhưng dấu thoát vẫn được in vì `finally` chạy cả trên đường lỗi. Các chi tiết này là hợp đồng cần bảo toàn nếu tái cấu trúc.

## 3. Bài tập A: đánh dấu concern trên mã gốc

Không đọc đáp án ở phần tiếp theo trước khi tự trả lời:

1. Trong mỗi phương thức, xác định concern nghiệp vụ và các concern hỗ trợ. Chúng có độc lập về ý định thay đổi không?
2. Hai nhóm dòng nào minh họa **scattering** giữa `InvoiceService` và `StockService`?
3. Dòng nào trong `issue()` cho thấy **tangling**? Nếu xóa riêng tracing thì còn những concern nào cùng nằm trong phương thức?
4. Tại sao `I2` và `S2` chưa đủ để kết luận “validation là scattering nên phải chuyển hết sang advice”?
5. Nếu đổi định dạng audit thành JSON, phải xem xét những vị trí nào của phiên bản hiện tại? Nếu thêm dịch vụ thứ ba, rủi ro sao chép là gì?
6. Đường lỗi `reserve(25)` có audit thành công hay không? Có tracing thoát không? Vì sao câu trả lời quan trọng?
7. Hãy chỉ ra một thay đổi tưởng là tái cấu trúc nhưng **làm đổi kết quả quan sát được** của chương trình.
8. Liệu AOP có thể gom tracing và audit mà không xóa kiểm tra input của domain không? Đề xuất phạm vi pointcut thích hợp.

Hãy trình bày đáp án dưới dạng bảng gồm **concern — bằng chứng — nhiều nơi hay trộn cùng nơi — yêu cầu hành vi**. Cách làm này buộc nhận diện bằng chứng trên mã nguồn thay vì chỉ gọi tên khái niệm.

## 4. Đáp án phân tích chương trình mẫu

### 4.1. Phân loại các dòng

| Dòng | Concern | Vai trò | Bằng chứng |
|---|---|---|---|
| `I1`, `I6` | Tracing | Xử lý xuyên suốt | Ghi dấu vào/ra quanh nghiệp vụ hóa đơn |
| `S1`, `S6` | Tracing | Xử lý xuyên suốt | Cùng chính sách dấu vào/ra cho tồn kho |
| `I4` | Audit thành công | Xử lý xuyên suốt nhưng cần nội dung nghiệp vụ | Ghi sự kiện `invoice.issued` sau khi tính thành công |
| `S4` | Audit thành công | Xử lý xuyên suốt nhưng cần nội dung nghiệp vụ | Ghi sự kiện `stock.reserved` sau khi tính thành công |
| `I2` | Kiểm tra điều kiện nghiệp vụ | Bảo vệ quy tắc của hóa đơn | Số lượng phải dương |
| `S2` | Kiểm tra điều kiện nghiệp vụ | Bảo vệ quy tắc giữ hàng | Số lượng phải trong phạm vi được hỗ trợ |
| `I3`, `I5` | Tính tổng và trả kết quả | Nghiệp vụ | `count * 10` |
| `S3`, `S5` | Tính tồn kho và trả kết quả | Nghiệp vụ | `20 - units` |

**Scattering của tracing:** cặp `I1/I6` và `S1/S6` thể hiện cùng yêu cầu “ghi entry/exit” được phân bố ở hai dịch vụ. Muốn đổi chiến lược tracing hoặc gắn correlation ID, nhiều vị trí phải được sửa hoặc dễ bị quên.

**Scattering của audit:** `I4` và `S4` đều thực hiện chính sách ghi nhận sau thành công. Tuy mỗi sự kiện có nhãn và payload nghiệp vụ khác nhau, **cơ chế xuất audit** có thể là mối quan tâm xuyên suốt, còn **ý nghĩa sự kiện** là dữ liệu nghiệp vụ phải được chỉ rõ.

**Tangling tại `issue()`:** phương thức vừa ghi trace, kiểm tra input, tính tiền, xuất audit, xử lý dọn cuối đường gọi. Trách nhiệm observability/audit được trộn trong đường tính hóa đơn. `reserve()` có tình trạng tương tự.

**Validation không mặc nhiên là scattering AOP:** `count > 0` và `0 < units <= 20` thuộc hai bất biến domain khác nhau. Ngay cả khi lặp một điều kiện giống nhau, cách sửa tốt có thể là giá trị kiểu mạnh, helper thuần hoặc domain policy dùng chung. Nếu một kiểm tra quyền truy cập có quy tắc xuyên suốt tất cả thao tác nhạy cảm, nó có thể là ứng viên aspect; nhưng không được chuyển kiểm tra bảo vệ ra khỏi nơi đáng tin mà chưa chứng minh mọi đường gọi bắt buộc đều được chặn.

### 4.2. “Scattering + tangling” không phải hai nhãn thay thế nhau

Hai nhãn mô tả **hai chiều độc lập**. Nhìn từ tracing, các lệnh xuất hiện ở nhiều lớp → scattering. Nhìn từ `InvoiceService.issue()`, tracing được ghép vào tính toán nghiệp vụ → tangling. Một concern có thể vừa rải rác trên nhiều mô-đun, vừa đan vào mỗi phương thức đó.

Một chương trình nhỏ có thể chỉ có tangling mà chưa cho thấy scattering (ví dụ một hàm rất dài pha nhiều concern). Một concern có thể scattering nhưng không tangling quá nặng nếu mỗi lớp gọi một helper rõ ràng. Do vậy không suy luận hai hiện tượng luôn xuất hiện cùng mức độ.

### 4.3. Phân biệt tín hiệu và nguyên nhân

Các dấu hiệu như “nhiều `println`”, “nhiều `try/finally`” hoặc “hai lớp giống nhau” mới là **tín hiệu điều tra**. Cần đặt câu hỏi trách nhiệm: có cùng lý do thay đổi không, có trải qua nhiều ranh giới nghiệp vụ không, có cần chính sách tập trung không, có điểm chặn ổn định không?

Ví dụ hai phương thức cùng gọi `validatePositive()` có thể chỉ đang tái sử dụng kiểm tra dữ liệu bình thường, không cần aspect. Ngược lại, logging và audit có thể không chứa dòng mã y hệt nhưng vẫn có cùng lý do thay đổi và là mối quan tâm xuyên suốt.

## 5. Bài tập B: dự đoán hệ quả khi sửa phiên bản ban đầu

Hãy xét các yêu cầu mới và xác định nhóm mã chịu tác động:

| Thay đổi yêu cầu | Nơi phải xem xét ở bản gốc | Rủi ro scattering/tangling |
|---|---|---|
| Thêm correlation ID vào mọi dấu tracing | `I1/I6`, `S1/S6` và các dịch vụ tương tự | Sửa thiếu hoặc quên dọn context trên đường lỗi |
| Chuyển audit từ console sang kênh lưu trữ | `I4`, `S4` và các vị trí audit khác | Trộn lỗi I/O của hạ tầng vào nghiệp vụ |
| Audit cả thao tác thất bại | Các nhánh `catch/finally` tương ứng, định nghĩa event lỗi | Sai ngữ nghĩa nếu gắn “success” cho lời gọi lỗi |
| Đổi đơn giá hóa đơn | `I3` | Thay đổi nghiệp vụ, không cần thay tracing |
| Đổi giới hạn tồn kho từ 20 thành cấu hình | `S2/S3` | Thay đổi luật tồn kho, không nên ép vào aspect logging |
| Đo thời gian mọi thao tác quan trọng | Phần bao quanh từng điểm được chọn | Nếu copy thủ công dễ rải logic đo ở nhiều nơi |

Khi refactor, không chỉ đếm số dòng giảm được. Cần chứng minh sự thay đổi đã **giảm số vị trí phải sửa cho cùng một chính sách** mà vẫn giữ hành vi đích: kết quả thành công, thứ tự side effect, loại ngoại lệ, điều kiện ghi audit và cleanup.

## 6. Thiết kế AOP cho ví dụ: chọn join point, pointcut và advice

Một thiết kế hướng AOP có thể tách phần cơ chế tracing/audit khỏi thân nghiệp vụ:

- **Join point:** thời điểm thực thi các thao tác quan trọng như lập hóa đơn hoặc giữ hàng.
- **Pointcut:** chọn đúng các thao tác đã được định nghĩa là cần observability/audit; không mặc định chặn mọi getter hay helper.
- **Around advice:** ghi trace khi vào; gọi `proceed()` để chạy đích; chỉ ghi audit thành công nếu đích hoàn tất bình thường; ghi trace thoát trong `finally`.
- **Context:** định danh thao tác (ví dụ `invoice`/`stock`), sự kiện audit và các trường thật sự cần; không tự động sao chép toàn bộ object graph.
- **Bộ máy can thiệp:** proxy hoặc weaving tùy công cụ, ranh giới target, khả năng chặn self-invocation và loại join point cần hỗ trợ.

Logic cơ chế có thể mô tả bằng pseudocode:

```text
around(operation, auditEvent):
    trace(operation, "enter")
    try:
        result = proceed()               // chạy nghiệp vụ
        audit(auditEvent, "success")       // chỉ sau thành công
        return result
    finally:
        trace(operation, "exit")          // luôn chạy cả khi có lỗi
```

Đây là **pseudocode mô tả advice**, không phải cú pháp của một framework hay một chương trình Java độc lập. Ý định chính là chỉ có một nơi định nghĩa quy tắc tracing; audit dùng cấu hình sự kiện riêng; phương thức nghiệp vụ không cần biết cách xuất trace.

Tuy nhiên, muốn có ngữ nghĩa “audit phản ánh tác vụ đã commit thật” thì ghi audit sau return của phương thức **chưa chắc đủ** nếu hệ thống còn có giao dịch hoặc thao tác bất đồng bộ. Chính sách phải định nghĩa “thành công” ở biên nào: hoàn tất lời gọi, cam kết dữ liệu hay sự kiện nghiệp vụ đã bền vững. Refactor không được âm thầm thay đổi mốc này.

## 7. Phiên bản sau: dùng proxy để minh họa tách concern

Chương trình sau dùng **JDK dynamic proxy** và một hàm `observed()` chứa phần tracing/audit dùng chung. Đây là **một cách triển khai AOP**, không khẳng định mọi mô hình aspect đều yêu cầu proxy. Hai lớp domain chỉ giữ logic kiểm tra input và tính toán.

Tạo tệp `ScatteringTanglingAfter.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class ScatteringTanglingAfter {
    interface Operation {
        int execute(int value);
    }

    static final class InvoiceCore implements Operation {
        @Override
        public int execute(int count) {
            if (count <= 0) {
                throw new IllegalArgumentException(
                    "count must be positive"
                );
            }
            return count * 10;
        }
    }

    static final class StockCore implements Operation {
        @Override
        public int execute(int units) {
            if (units <= 0 || units > 20) {
                throw new IllegalArgumentException(
                    "units out of range"
                );
            }
            return 20 - units;
        }
    }

    static Operation observed(
            Operation target, String name, String auditEvent) {
        return (Operation) Proxy.newProxyInstance(
            Operation.class.getClassLoader(),
            new Class<?>[] { Operation.class },
            (proxy, method, args) -> {
                // Demo chỉ gọi Operation.execute().
                System.out.println("TRACE " + name + ".enter");
                try {
                    Object result = method.invoke(target, args);
                    System.out.println("AUDIT " + auditEvent);
                    return result;
                } catch (InvocationTargetException exception) {
                    throw exception.getCause();
                } finally {
                    System.out.println("TRACE " + name + ".exit");
                }
            }
        );
    }

    public static void main(String[] args) {
        Operation invoice = observed(
            new InvoiceCore(), "invoice", "invoice.issued"
        );
        Operation stock = observed(
            new StockCore(), "stock", "stock.reserved"
        );

        System.out.println("Invoice result: " + invoice.execute(3));
        System.out.println("Stock result: " + stock.execute(4));

        try {
            stock.execute(25);
        } catch (IllegalArgumentException exception) {
            System.out.println("Error: " + exception.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ScatteringTanglingAfter.java
java ScatteringTanglingAfter
```

Stdout chính xác:

```text
TRACE invoice.enter
AUDIT invoice.issued
TRACE invoice.exit
Invoice result: 30
TRACE stock.enter
AUDIT stock.reserved
TRACE stock.exit
Stock result: 16
TRACE stock.enter
TRACE stock.exit
Error: units out of range
```

Đầu ra trên **giống bản trước từng dòng** đối với ba ca thử đã chọn. Điều đó là bằng chứng cần thiết cho các đường này, nhưng chưa chứng minh toàn bộ ngữ nghĩa production. Ví dụ thực tế còn phải kiểm tra overload, cách xử lý `equals/hashCode/toString` của proxy, ngoại lệ checked, gọi nội bộ, concurrency và những phương thức không thuộc pointcut.

### Tại sao phiên bản sau giảm scattering và tangling?

- Tracing `enter/exit` chỉ được mô tả một lần trong `observed()`, thay vì lặp trong `issue()` và `reserve()`.
- Quy tắc audit khi thành công chỉ được triển khai một lần; từng hành động vẫn truyền tên sự kiện `invoice.issued` hoặc `stock.reserved`.
- `InvoiceCore.execute()` tập trung vào “số lượng hợp lệ → tính tổng”; `StockCore.execute()` tập trung vào “số lượng hợp lệ → tính tồn kho”. Đây là giảm tangling trong mã nghiệp vụ.
- Chính sách có thể được sửa tập trung trong interceptor minh họa, trong khi các quy tắc domain vẫn ở lớp domain.

**Giới hạn quan trọng:** Bản demo không loại bỏ mọi khả năng tangling. Hàm `observed()` đang thực hiện cả tracing và audit; nếu hai chính sách phát triển độc lập, có thể tách thành hai interceptor/advice riêng trong một chuỗi với thứ tự có chủ đích. Việc gộp hai concern vào một wrapper là **bước chuyển để minh họa cơ chế**, chưa phải thiết kế sản phẩm cuối cùng tối ưu cho mọi hoàn cảnh.

## 8. Phân tích thay đổi ngữ nghĩa khi refactor

| Thuộc tính | Bản đầu | Bản sau | Điều cần giữ |
|---|---|---|---|
| Kiểm tra số lượng hóa đơn | Trong `issue()` | Trong `InvoiceCore.execute()` | `count <= 0` vẫn báo lỗi |
| Kiểm tra giới hạn tồn kho | Trong `reserve()` | Trong `StockCore.execute()` | `units <= 0 || units > 20` vẫn báo lỗi |
| Tracing entry | Đầu mỗi phương thức | Đầu handler `observed()` | Một lần trước nghiệp vụ |
| Tracing exit | `finally` riêng của từng phương thức | `finally` chung | Chạy trên thành công và lỗi |
| Audit success | Sau phép tính thành công | Sau `Method.invoke` hoàn tất | Không ghi success khi target lỗi |
| Ngoại lệ của target | Ném trực tiếp | Reflection bọc rồi handler mở cause | Caller nhận đúng `IllegalArgumentException` |
| Kết quả | `30` và `16` | `30` và `16` | Cùng đầu ra |
| Đường gọi ngoài | Gọi trực tiếp đối tượng domain | Đi qua proxy | Phải có cùng chính sách can thiệp |

Điểm cần cảnh giác: với một proxy bọc quanh đối tượng, nếu caller giữ tham chiếu tới `new InvoiceCore()` và gọi trực tiếp thì lời gọi **không đi qua interceptor**. Vì thế một chính sách bắt buộc như kiểm soát truy cập không nên chỉ phụ thuộc vào một proxy có thể bị bỏ qua; cần thiết kế ranh giới tin cậy và kiểm thử mọi đường gọi hợp lệ. Với cơ chế weaving, phạm vi join point và khả năng chặn lời gọi nội bộ có thể khác.

Bản `observed()` minh họa chỉ một phương thức interface `execute()`. Nếu caller gọi các phương thức `Object` trên proxy, handler có thể cũng nhận các lời gọi đó; sản phẩm thực tế cần thiết kế riêng cho identity, equality, logging proxy object và những method không thuộc pointcut.

## 9. Bài tập C: thiết kế hai advice độc lập

Hãy giả sử tracing và audit có vòng đời phát triển khác nhau:

- Nhóm vận hành muốn tracing thêm duration hoặc correlation ID, với chính sách lấy mẫu.
- Nhóm nghiệp vụ muốn audit thành công hoặc thất bại theo định dạng kiểm toán bắt buộc.
- Tracing có thể tắt trong một số phép đo hiệu năng; audit bắt buộc không được bỏ qua.

Hãy tách thiết kế thành:

```text
Caller
  → TracingAdvice (before / finally)
     → AuditAdvice (after returning / after throwing nếu chính sách yêu cầu)
        → TargetOperation
```

Trả lời:

1. Thứ tự hai advice thay đổi điều gì? Nếu tracing ở ngoài audit, khoảng đo có bao gồm chi phí audit không?
2. Audit có được phép chạy khi nghiệp vụ ném lỗi hay phải có sự kiện lỗi riêng?
3. Nếu audit ném lỗi ngay sau khi target đã thành công, caller nên nhận thành công hay thất bại? Chính sách nghiệp vụ phải quyết định trước khi code.
4. Nếu tracing chỉ lấy mẫu 1%, audit bắt buộc vẫn chạy 100% hay không?
5. Nếu một advice around quên gọi `proceed()`, điều gì xảy ra?
6. Nếu retry gọi `proceed()` nhiều lần, mỗi lần target và audit sẽ được ghi như thế nào?

**Đáp án hướng dẫn:** mỗi concern nên có vòng đời, chính sách lỗi và phạm vi riêng. Độ đo tracing của wrapper ngoài có thể gồm cả thời gian audit nếu audit nằm bên trong. `finally` giúp cleanup dù có lỗi, còn “after returning” chỉ chạy khi hoàn tất bình thường. Sampling tracing không được tự tác động tới audit bắt buộc. Không được gộp các quyết định này thành một interceptor chỉ để giảm số dòng nếu nghĩa vụ của chúng khác nhau.

## 10. Bài tập D: tự nhận diện từ một chương trình khác

Hãy đọc pseudocode sau:

```text
function createPayment(request):
    ensureAuthenticated(request.user)
    log("start createPayment")
    validatePayment(request)
    payment = calculateAndPersistPayment(request)
    audit("payment-created", request.user, payment.id)
    log("end createPayment")
    return payment

function cancelPayment(request):
    ensureAuthenticated(request.user)
    log("start cancelPayment")
    validateCancelRequest(request)
    payment = cancelStoredPayment(request.id)
    audit("payment-cancelled", request.user, payment.id)
    log("end cancelPayment")
    return payment
```

Hãy xác định:

- Concern nào có cùng lý do thay đổi ở hai phương thức?
- Những đoạn nào thuộc nghiệp vụ thanh toán và hủy thanh toán?
- Điểm nào cho thấy tangling trong từng phương thức?
- Điều gì xảy ra nếu `validatePayment` hoặc `cancelStoredPayment` ném lỗi? Dấu “end” có được ghi không?
- Nếu dời `ensureAuthenticated` vào advice, phải kiểm chứng ranh giới nào để không tạo đường gọi thiếu kiểm soát?
- Muốn có audit chỉ khi dữ liệu **đã cam kết bền vững**, nên đặt policy ở đâu so với biên commit?
- Hai thao tác có cần cùng audit payload không, hay chỉ nên chia sẻ cơ chế phát sự kiện?

**Gợi ý đáp án:** xác thực, ghi dấu và cơ chế audit là ứng viên cross-cutting; hai thao tác có logic domain và quy tắc kiểm tra đầu vào khác nhau. Trong pseudocode, “end” ở cuối chỉ chạy trên đường thành công; muốn bảo toàn cleanup trên đường lỗi thì phải định nghĩa lại yêu cầu và có cấu trúc tương đương `finally`. Xác thực là bảo vệ bắt buộc, do đó refactor an toàn phải chứng minh **mọi đường truy cập dữ liệu cần bảo vệ** đều đi qua biên kiểm soát. Audit về commit không thể được bảo đảm chỉ bằng “đã return thành công” nếu cơ chế lưu trữ còn có giao dịch chưa hoàn tất.

## 11. Kiểm thử bằng chứng về scattering và tangling

Một kế hoạch kiểm thử nên chứa:

**A. Contract trước/sau**

- `issue(3)` hoặc thao tác tương đương cho tổng 30.
- `reserve(4)` hoặc thao tác tương đương trả 16.
- `reserve(25)` ném `IllegalArgumentException` với thông điệp mong đợi.
- Trên hai lần thành công có hai sự kiện audit success; trên lần lỗi không có audit success.
- Mỗi lần đi qua điểm được chọn phải có dấu enter và exit, kể cả khi lỗi.
- Nếu thay thứ tự advice, so lại thứ tự dấu/log và side effects.

**B. Kiểm chứng đúng phạm vi**

- Phương thức thuộc pointcut có advice.
- Phương thức không thuộc pointcut không bị audit sai.
- Gọi trực tiếp target, lời gọi qua proxy, self-invocation và đường async được kiểm tra theo cơ chế AOP chọn.
- Không đánh đồng số lần advice gọi với số lần nghiệp vụ hoàn thành khi có retry hoặc short-circuit.

**C. Độ bao phủ và hồi quy**

- Unit test của core để bảo vệ quy tắc domain.
- Test integration trên đường được instrument để khẳng định advice.
- Negative test cho input lỗi và pointcut không khớp.
- So sánh kết quả, ngoại lệ, số sự kiện và thứ tự khi điều kiện thay đổi.
- Dùng công cụ coverage dòng/nhánh cho code, kết hợp ma trận join point/advice vì 100% line coverage không tự bảo đảm pointcut đúng.

**D. Hiệu năng sau khi đúng chức năng**

- Đo số lần chạy advice trước/sau: hai dòng code được gom thành một vị trí định nghĩa không đồng nghĩa runtime chạy ít hơn.
- Đo overhead của proxy/weaving và context trên những hot path thực tế.
- Tránh đặt I/O đồng bộ hoặc dựng stack trace ở mọi invocation để “xác nhận AOP hoạt động”.
- Nếu cần, dùng JMH cho microbenchmark và đo tải thực tế cho throughput, allocation, p95/p99.

Trong ví dụ đã cho, bản trước và bản sau đều tạo **ba dấu enter, ba dấu exit và hai dòng audit thành công** khi chạy ba lượt. Mục tiêu của refactor ở đây là **tập trung hóa trách nhiệm và giảm tangling**, không phải cắt bớt các sự kiện bắt buộc. Mức overhead của bản sau có thể khác vì proxy/reflection; phải đo trước khi tuyên bố phiên bản sau nhanh hơn.

## 12. Những trường hợp không nên đưa ngay vào aspect

**Quy tắc tính toán nghiệp vụ:** việc tính `count * 10` và `20 - units` khác nhau theo miền domain. Ép chúng vào một advice chỉ vì đều có phép toán là làm mờ trách nhiệm, không giải quyết scattering thực chất.

**Validation gắn với bất biến object:** nhiều kiểm tra dữ liệu thuộc domain model hoặc API contract. Nếu tách khỏi nơi dữ liệu có thể được tạo/sửa mà không có cơ chế bao phủ đáng tin, invariant dễ bị bỏ qua.

**Quy trình nhiều bước có trạng thái:** không phải mọi thao tác khởi tạo, kiểm tra, lưu và xác nhận đều là cross-cutting concern; đôi khi đó là orchestration nghiệp vụ. Tách một khâu cốt lõi vào advice có thể khiến người đọc không thấy quy trình quan trọng.

**Concern không thực sự đồng nhất:** audit giữa các nghiệp vụ có thể chia sẻ cơ chế phát sự kiện nhưng có payload, mức độ bắt buộc, thời điểm commit và cách xử lý lỗi khác nhau. Nếu cố gộp tất cả thành một advice với nhiều điều kiện phân nhánh, chính advice sẽ trở thành một khối tangling mới.

**Điểm chặn không bảo đảm:** nếu cơ chế proxy không thấy self-invocation hoặc đường gọi trực tiếp, không chuyển một kiểm tra bảo mật quan trọng vào interception mà không giải quyết ranh giới này. Có trường hợp explicit wrapper/decorator hoặc policy domain rõ ràng dễ kiểm chứng hơn.

AOP là một cách tổ chức *cross-cutting concerns*, không phải câu trả lời tự động cho mọi duplicate code.

## 13. Quy trình nhận diện trong codebase lớn

Có thể áp dụng bảy bước:

1. **Lập danh sách concern.** Gọi tên chính xác: audit thành công, log lỗi, trace duration, xác thực quyền, transaction boundary, cache invalidation, chứ không gom mọi thứ vào nhãn “infrastructure”.
2. **Đánh dấu vị trí.** Tìm các mẫu lời gọi/annotation/hook có cùng mục đích trên nhiều lớp. Dùng tìm kiếm mã để lập một bảng vị trí, nhưng đọc ngữ cảnh trước khi kết luận.
3. **Vẽ ma trận concern × module.** Trục ngang là các lớp/phương thức; trục dọc là concern. Một hàng xuất hiện ở nhiều cột cho thấy nguy cơ scattering; nhiều concern trong một cột cho thấy nguy cơ tangling.
4. **Phân biệt policy chung và dữ liệu đặc thù.** Quy tắc “log enter/exit trong `finally`” có thể dùng chung; tên sự kiện audit hoặc cấu trúc payload có thể vẫn cần khai báo ở nghiệp vụ.
5. **Xác định join point và tập pointcut mong đợi.** Viết cả positive và negative case, đặc biệt với overload, gọi nội bộ, ngoại lệ và concurrency.
6. **Thiết kế lifecycle và kiểm thử.** Xác định advice chạy trước/sau, có được short-circuit/retry không, tương tác với transaction và cleanup ra sao. Lưu baseline trước khi đổi.
7. **Đánh giá tác động.** So sánh số vị trí phải sửa khi thay policy, mức độ dễ đọc của core, test bảo vệ semantics và chi phí runtime. Nếu cấu trúc mới khó debug hoặc overhead lớn mà lợi ích nhỏ, cân nhắc giải pháp đơn giản hơn.

### Ví dụ ma trận concern × vị trí

| Concern \ Vị trí | `Invoice.issue` | `Stock.reserve` | `Invoice.calculateTax` | Interceptor chung |
|---|---|---|---|---|
| Tính tiền/tồn kho | Tính tổng | Giảm tồn kho | Tính thuế | Không |
| Tracing | Có (bản trước) | Có (bản trước) | Không cần nếu policy không yêu cầu | Có (bản sau) |
| Audit thành công | Có (bản trước) | Có (bản trước) | Không cần | Có (bản sau) |
| Kiểm tra invariant domain | Số lượng dương | Trong giới hạn | Quy tắc thuế | Không |

Ma trận giúp nhìn ra **hàng tracing/audit rải nhiều cột** là scattering và **hai cột đầu kết hợp nhiều hàng concern** là tangling. Bản sau vẫn cần cấu hình chính xác các sự kiện, không được dùng một pointcut quá rộng đến mức can thiệp mọi hàm tính toán.

## 14. Những lỗi nhận diện và refactor thường gặp

1. **“Scattering nghĩa là code được copy-paste y hệt.”** Không đủ. Cùng một concern có thể dùng nhiều câu lệnh khác nhau ở nhiều lớp.
2. **“Tangling nghĩa là method có quá nhiều dòng.”** Sai trọng tâm. Một method ngắn trộn bảo mật, nghiệp vụ và logging vẫn có thể tangling.
3. **“Mọi validation đều là aspect.”** Không. Domain validation gắn với bất biến riêng nên thường phải ở ranh giới domain phù hợp.
4. **“Tách mã trùng là đã giải quyết scattering.”** Chỉ tạo helper chung có thể vẫn phải chèn lệnh gọi helper ở hàng trăm phương thức; chính sách có thể còn bị phân tán theo điểm kích hoạt.
5. **“Tách vào AOP thì mọi lời gọi đều tự được chặn.”** Sai. Khả năng chặn phụ thuộc proxy, weaving, class loader, self-invocation và phạm vi join point.
6. **“Audit có thể chạy trong `finally` mà không đổi nghĩa.”** Audit success ở `finally` sẽ chạy cả khi nghiệp vụ lỗi; cần tách success/failure theo hợp đồng.
7. **“Trước và sau đều in đúng output một lần thì luôn tương đương.”** Chưa đủ. Cần thêm exception, concurrency, retry, side effect và đường gọi khác.
8. **“Một advice thật lớn giải quyết mọi concern.”** Có thể chỉ chuyển tangling từ domain sang advice; nên xác định chính sách và thứ tự độc lập.
9. **“AOP luôn tăng hiệu năng.”** AOP giúp tổ chức code; proxy, reflection, matching, allocation và I/O có thể thêm overhead. Tối ưu runtime cần đo.
10. **“Giảm số lời gọi advice là ưu tiên hơn yêu cầu chức năng.”** Nếu audit hoặc kiểm tra quyền bắt buộc, không được bỏ chỉ vì tần suất cao.
11. **“Scattering chỉ gây phiền khi thêm tính năng.”** Nó cũng gây rủi ro sửa thiếu, lỗi chính sách khác nhau giữa các module và khó chứng minh độ bao phủ.
12. **“Không cần negative test khi pointcut rõ ràng.”** Pointcut rộng có thể chặn nhầm getter/helper và tạo audit thừa, latency hoặc side effect ngoài mong muốn.

## 15. Bài tập mở rộng và tiêu chí đánh giá

**Bài tập mở rộng 1 — thay đổi yêu cầu audit:** sửa chính sách từ “chỉ ghi thành công” thành “ghi thành công hoặc lỗi, với loại sự kiện khác nhau”. Đề xuất vị trí xử lý, payload, exception semantics và test tương ứng. Không viết nhãn success cho trường hợp thất bại.

**Bài tập mở rộng 2 — tách hai interceptor:** thiết kế `TracingInterceptor` và `AuditInterceptor` hoạt động theo chuỗi, xác định rõ thứ tự. Thử một interceptor ném lỗi trong pha after, giải thích caller nhìn thấy gì và cleanup còn chạy không.

**Bài tập mở rộng 3 — pointcut hẹp:** thêm phương thức thuần `preview` không cần audit; kiểm chứng tracing/audit không chạy khi gọi `preview` nếu policy chỉ quan tâm hành động thay đổi trạng thái. Nếu vẫn qua proxy handler, phân biệt chi phí dispatch với việc advice thực sự chạy.

**Bài tập mở rộng 4 — đường gọi nội bộ:** cho `InvoiceCore.execute()` gọi một helper cùng đối tượng. So sánh khả năng chặn helper qua proxy với trường hợp có weaving tương thích. Không khẳng định mọi cơ chế có kết quả giống nhau.

**Bài tập mở rộng 5 — đo tác động bảo trì:** giả sử có 30 dịch vụ đều cần đổi định dạng trace. Đếm số điểm định nghĩa chính sách cần sửa ở bản cũ so với bản có tracing được tập trung hóa. Ngoài số dòng, đánh giá độ bao phủ, tính rõ ràng khi gỡ lỗi và chi phí của lớp trừu tượng mới.

### Rubric tự chấm

| Mức đạt | Dấu hiệu |
|---|---|
| Chưa đạt | Gọi mọi đoạn lặp là aspect; nhầm scattering với tangling hoặc không chỉ ra dòng cụ thể |
| Đạt cơ bản | Xác định đúng tracing/audit rải ở hai dịch vụ; chỉ ra nhiều concern trong một method |
| Khá | Tách đúng nghiệp vụ và xử lý xuyên suốt, giải thích đường thành công/lỗi và pointcut |
| Tốt | Đề xuất refactor kiểm chứng được; giữ kết quả, exception, audit count, tracing `finally`; có test phủ định |
| Rất tốt | Phân biệt ý nghĩa nghiệp vụ của audit với cơ chế chung, xét self-invocation, proxy/weaving, concurrency, retry và trade-off hiệu năng/bảo trì |

## 16. Câu hỏi tự kiểm tra

**1. Cùng một concern xuất hiện trong 15 lớp là gì?** Đó là dấu hiệu scattering nếu các vị trí thực sự có cùng lý do thay đổi. Cần chứng minh concern và phạm vi, không dựa vào trùng chuỗi đơn thuần.

**2. Một phương thức gồm nghiệp vụ, tracing và audit là gì?** Có nguy cơ tangling vì nhiều trách nhiệm đan xen; mức độ đáng tách phụ thuộc tính độc lập và yêu cầu hệ thống.

**3. Trong mã mẫu, đâu là bằng chứng scattering rõ nhất?** Hai cặp trace `I1/I6` và `S1/S6` cùng chính sách, và hai lệnh audit `I4/S4` nằm ở các dịch vụ khác nhau.

**4. Có nên chuyển `count <= 0` và `units > 20` vào cùng một advice?** Không chỉ vì cả hai là `if`. Chúng bảo vệ những bất biến domain khác nhau; cấu trúc tốt phải giữ chúng được kiểm tra ở biên đáng tin.

**5. Vì sao audit success không nằm trong `finally`?** Vì `finally` chạy cả khi ném ngoại lệ. Audit success đặt sai chỗ sẽ ghi một giao dịch lỗi là thành công.

**6. Refactor đã loại bỏ hoàn toàn scattering chưa?** Nó tập trung hóa cơ chế tracing/audit của ví dụ, nhưng dữ liệu sự kiện và các cấu hình áp dụng vẫn hiện diện ở biên thích hợp. Tính đúng đắn còn phụ thuộc mọi đường gọi cần can thiệp đều đi qua cơ chế.

**7. Sau refactor, logic nghiệp vụ có thay đổi không?** Với các ca được chạy, kết quả/exception/stdout là như nhau. Để khẳng định hoàn toàn tương đương còn cần thêm kiểm thử cho đường gọi và trạng thái khác.

**8. Vì sao “ít code hơn” chưa đủ là bằng chứng thiết kế tốt?** Có thể làm mất chính sách bắt buộc, che giấu hành vi, làm khó debug hoặc thêm overhead. Chất lượng đánh giá theo sự phân tách trách nhiệm và các bất biến được giữ.

**9. Một helper tĩnh dùng chung có giải quyết được mọi vấn đề không?** Không. Nó gom implementation nhưng điểm gọi helper vẫn phân tán; AOP có thể gom cả quy tắc kích hoạt nếu join point và pointcut phù hợp. Trong vài bài toán, helper lại dễ hiểu và đủ tốt.

**10. Kết luận chính từ chương trình mẫu?** Phân tích scattering theo trục **một concern — nhiều vị trí**, tangling theo trục **một vị trí — nhiều concern**. Tách tracing/audit chỉ có giá trị nếu giữ đúng điều kiện, thứ tự, outcome và phạm vi chặn.

**Ghi nhớ:** Bước đầu của thiết kế AOP không phải viết advice, mà là *phân loại các lý do thay đổi trong mã hiện tại*. Xác định bằng chứng scattering/tangling, giữ nghiệp vụ ở nơi thuộc về nó, chọn join point rõ ràng và dùng kiểm thử đầu ra, ngoại lệ cùng side effect để xác nhận sự tách biệt thực sự an toàn.