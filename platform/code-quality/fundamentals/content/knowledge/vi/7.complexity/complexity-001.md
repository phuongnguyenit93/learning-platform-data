# Độ phức tạp do bản thân bài toán và do cách triển khai

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **độ phức tạp vốn có của bài toán** (essential/inherent complexity) và **độ phức tạp phát sinh từ cách triển khai** (accidental/implementation complexity).
2. Nhận biết độ phức tạp nào cần được **mô hình hóa và kiểm soát**, độ phức tạp nào nên được **loại bỏ hoặc giảm bớt**.
3. Phân tích một đoạn Java có nhiều điều kiện, trạng thái và phụ thuộc để xác định nguyên nhân khiến mã khó hiểu hoặc khó thay đổi.
4. Dùng bảng quyết định, mô hình trạng thái, ranh giới trách nhiệm, test và code review để làm rõ quy tắc nghiệp vụ.
5. Tránh đánh đồng độ phức tạp thuật toán, độ phức tạp điều khiển và gánh nặng nhận thức của người bảo trì.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu các thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không. Chủ đề **Độ phức tạp** rất quan trọng vì không phải mọi thứ khó hiểu trong mã nguồn đều có cùng nguyên nhân. Một phần khó khăn đến từ việc hệ thống phải giải quyết một bài toán thực sự phức tạp; phần khác do các quyết định biểu diễn, phân tách và tổ chức chương trình.

**Định hướng chính:** Không thể làm cho một nghiệp vụ phức tạp trở nên đơn giản chỉ bằng cách rút ngắn số dòng mã. Mục tiêu là **biểu diễn đầy đủ độ phức tạp cần thiết** và **không thêm độ phức tạp không mang lại giá trị**.

## 1. Hai nguồn gốc của độ phức tạp

### 1.1. Độ phức tạp do bản thân bài toán

Độ phức tạp này đến từ **quy tắc, trạng thái, ràng buộc, ngoại lệ và quan hệ thực** mà phần mềm phải xử lý. Ta cũng gọi là **độ phức tạp bản chất** (essential/inherent complexity). Nó còn tồn tại ngay cả khi chọn ngôn ngữ lập trình, framework hay kiến trúc khác.

Ví dụ, hệ thống đặt vé cần xét:

- Chỗ ngồi có còn trống ở thời điểm xác nhận không?
- Nếu hai khách cùng chọn một chỗ thì chỉ ai được giữ chỗ?
- Khi thanh toán bị từ chối, giữ chỗ có được giải phóng không?
- Đơn đặt vé hết hạn sau bao lâu?
- Khách đổi chuyến, hủy vé hoặc được hoàn tiền theo điều kiện nào?

Những câu hỏi này tồn tại vì **nghiệp vụ có trạng thái, quy tắc và cạnh tranh tài nguyên**. Đổi từ Java sang Kotlin, tách microservice hay dùng một thư viện mới không làm chúng biến mất. Ta chỉ có thể mô tả rõ, đơn giản hóa yêu cầu nếu được phép, hoặc thiết kế để xử lý an toàn.

Một dạng độ phức tạp bản chất khác là giới hạn tính toán: có bài toán phải xử lý tập dữ liệu lớn, duy trì thứ tự sự kiện hoặc đáp ứng tính nhất quán giao dịch. Không phải bài toán nào cũng có thuật toán vừa nhanh vừa dùng ít bộ nhớ với mọi kích thước đầu vào.

### 1.2. Độ phức tạp do cách triển khai

Đây là khó khăn do **công cụ, cấu trúc, kỹ thuật triển khai hoặc quyết định của nhóm phát triển** tạo thêm, vượt quá những gì bài toán thật sự đòi hỏi. Thường gọi là **độ phức tạp ngẫu sinh** (accidental complexity), vì nó không bắt buộc phát sinh từ bản thân yêu cầu.

Ví dụ với cùng chức năng giữ chỗ:

- Trạng thái vé được biểu diễn bằng bốn cờ boolean độc lập, tạo ra nhiều tổ hợp vô nghĩa.
- Quy tắc hết hạn được sao chép ở controller, service và tác vụ nền.
- Để hiểu một lần giữ chỗ, người đọc phải đi qua tám lớp chỉ gọi tiếp sang lớp khác.
- Một phương thức vừa xác thực, cập nhật cơ sở dữ liệu, gọi hệ thống thanh toán và gửi email.
- Số tiền được dùng dưới dạng **double** ở một module và chuỗi ký tự ở module khác; mỗi nơi có quy tắc làm tròn riêng.
- Những giá trị cấu hình có cùng ý nghĩa nhưng đơn vị khác nhau: nơi dùng giây, nơi dùng mili giây.

Các đặc điểm này làm mã khó hiểu hoặc dễ lỗi dù không phải là yêu cầu của nghiệp vụ. Có thể thay cách biểu diễn, xác định một nơi sở hữu quy tắc, cô lập tác dụng phụ hoặc chuẩn hóa hợp đồng để giảm chúng.

### 1.3. Không phải ranh giới nào cũng tuyệt đối

Một thiết kế có thể hợp lý trong hoàn cảnh này nhưng trở thành gánh nặng khi bối cảnh đổi.

Ví dụ, một abstraction cho ba nhà cung cấp thanh toán thực sự có thể làm rõ ranh giới tích hợp. Cùng abstraction đó, nếu được tạo cho một hàm tính cộng duy nhất và không có nhu cầu thay thế, có thể chỉ tạo thêm công đọc hiểu. Độ phức tạp của việc tích hợp nhà cung cấp ngoài là có thật; số lớp trung gian để tổ chức nó là một **lựa chọn thiết kế**.

Vì vậy, khi phân loại cần hỏi: **“Nếu viết lại bằng thiết kế hợp lý khác nhưng giữ nguyên yêu cầu, sự phức tạp này có còn không?”** Câu trả lời giúp xác định phần nào là bản chất và phần nào có thể giảm bằng triển khai.

## 2. Nhìn qua ví dụ một hệ thống bán hàng

Giả sử ứng dụng có chức năng đặt hàng, thanh toán và hủy đơn. Yêu cầu nghiệp vụ ban đầu:

1. Đơn mới ở trạng thái **DRAFT**.
2. Đơn **DRAFT** có thể được xác nhận thành **CONFIRMED**.
3. Đơn **CONFIRMED** có thể được thanh toán thành **PAID**.
4. Đơn **DRAFT** hoặc **CONFIRMED** có thể bị hủy thành **CANCELLED**.
5. Luồng đơn giản này không cho phép thanh toán đơn đã hủy hoặc hủy trực tiếp đơn đã thanh toán.

Đây là các **quy tắc bản chất** của luồng minh họa. Khi dùng một mô hình đúng, vẫn phải có cách biểu diễn những chuyển trạng thái hợp lệ và cách từ chối thao tác không hợp lệ.

### 2.1. Cách biểu diễn làm bài toán khó hơn

Ví dụ Java sau cố gắng biểu diễn trạng thái bằng nhiều cờ độc lập:

~~~java
class OrderFlags {
    boolean draft;
    boolean confirmed;
    boolean paid;
    boolean cancelled;
}
~~~

Bốn cờ boolean tạo ra tối đa **2⁴ = 16 tổ hợp** giá trị. Nhưng yêu cầu trên chỉ có bốn trạng thái riêng hợp lệ. Những tổ hợp như **paid = true** và **cancelled = true**, hoặc tất cả đều **false**, không có ý nghĩa trong mô hình này.

Khi chương trình cho phép tạo trạng thái không hợp lệ, mọi đoạn mã dùng **OrderFlags** phải tự suy luận xem cờ nào ưu tiên, cần kiểm tra bao nhiêu cờ và liệu dữ liệu có bị mâu thuẫn. **Đây là độ phức tạp do biểu diễn**, bởi nghiệp vụ không yêu cầu 16 trạng thái.

Nếu sau này có thêm cờ **shipped**, số tổ hợp lý thuyết tăng thành 32; số trường hợp hợp lệ có thể vẫn rất ít. Sự phình to này làm test và debug khó hơn.

### 2.2. Mô hình hóa trực tiếp các trạng thái hợp lệ

Dùng **enum** để biểu diễn một trạng thái đơn tại một thời điểm:

~~~java
enum OrderStatus {
    DRAFT,
    CONFIRMED,
    PAID,
    CANCELLED
}

enum OrderAction {
    CONFIRM,
    PAY,
    CANCEL
}
~~~

Bây giờ, biến **status** chỉ nhận một trong bốn giá trị. Ta vẫn phải xử lý quy tắc chuyển trạng thái, nhưng đã loại bỏ những tổ hợp trạng thái vốn không tồn tại trong bài toán.

Bảng chuyển trạng thái cho ví dụ:

| Trạng thái hiện tại | CONFIRM | PAY | CANCEL |
| --- | --- | --- | --- |
| DRAFT | CONFIRMED | Không hợp lệ | CANCELLED |
| CONFIRMED | Không hợp lệ | PAID | CANCELLED |
| PAID | Không hợp lệ | Không hợp lệ | Không hợp lệ |
| CANCELLED | Không hợp lệ | Không hợp lệ | Không hợp lệ |

Bảng này thể hiện **độ phức tạp bản chất của các quy tắc**. Người phân tích nghiệp vụ có thể kiểm tra trực tiếp bảng trước khi xem code.

Một triển khai Java 17 đơn giản:

~~~java
import java.util.Objects;

public final class OrderStateMachine {
    private OrderStateMachine() {
    }

    public static OrderStatus next(
            OrderStatus current, OrderAction action) {

        Objects.requireNonNull(current, "current");
        Objects.requireNonNull(action, "action");

        return switch (action) {
            case CONFIRM -> {
                requireState(current, OrderStatus.DRAFT, action);
                yield OrderStatus.CONFIRMED;
            }
            case PAY -> {
                requireState(current, OrderStatus.CONFIRMED, action);
                yield OrderStatus.PAID;
            }
            case CANCEL -> {
                if (current != OrderStatus.DRAFT
                        && current != OrderStatus.CONFIRMED) {
                    throw new IllegalStateException(
                            "Cannot " + action + " from " + current);
                }
                yield OrderStatus.CANCELLED;
            }
        };
    }

    private static void requireState(
            OrderStatus actual,
            OrderStatus expected,
            OrderAction action) {

        if (actual != expected) {
            throw new IllegalStateException(
                    "Cannot " + action + " from " + actual);
        }
    }
}
~~~

Lợi ích không nằm ở việc loại bỏ mọi **if**. Mã vẫn có các điều kiện vì **nghiệp vụ có điều kiện**. Cải thiện nằm ở chỗ trạng thái có kiểu rõ ràng, quy tắc chuyển được tập trung và các đầu vào bất hợp lệ bị từ chối thay vì tạo trạng thái mâu thuẫn.

### 2.3. Kiểm thử để xác nhận điều không thể giản lược

Ví dụ dùng JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderStateMachineTest {

    @Test
    void confirmsDraftOrder() {
        assertEquals(
                OrderStatus.CONFIRMED,
                OrderStateMachine.next(
                        OrderStatus.DRAFT, OrderAction.CONFIRM));
    }

    @Test
    void cancelsConfirmedOrder() {
        assertEquals(
                OrderStatus.CANCELLED,
                OrderStateMachine.next(
                        OrderStatus.CONFIRMED, OrderAction.CANCEL));
    }

    @Test
    void cannotPayCancelledOrder() {
        assertThrows(
                IllegalStateException.class,
                () -> OrderStateMachine.next(
                        OrderStatus.CANCELLED, OrderAction.PAY));
    }
}
~~~

Đây là một số test đại diện. Khi cần kiểm chứng đầy đủ bảng ở trên, có thể dùng **parameterized test** hoặc một tập ca kiểm thử bao phủ từng tổ hợp hành động/trạng thái. Điều quan trọng là test mô tả **hợp đồng nghiệp vụ**, không chỉ gọi qua phương thức để tăng độ bao phủ.

**Giới hạn của ví dụ:** Quy tắc thực tế có thể cần thêm **REFUNDED**, xử lý hoàn tiền, đồng thời nhiều yêu cầu và khả năng xảy ra xung đột khi ghi cơ sở dữ liệu. **OrderStateMachine** chỉ xác định chuyển trạng thái hợp lệ trong bộ nhớ; nó **không tự giải quyết** giao dịch, optimistic locking hay việc cập nhật xảy ra đúng một lần. Những vấn đề phát sinh từ tính chất hệ thống thực phải được xử lý ở các ranh giới thích hợp.

## 3. Độ phức tạp có nhiều hình thức

Không nên chỉ dùng từ “phức tạp” theo một nghĩa. Trong đánh giá code quality, ít nhất cần phân biệt:

| Góc nhìn | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Nghiệp vụ/bản chất** | Có bao nhiêu quy tắc, trạng thái, ngoại lệ thực sự cần xử lý? | Nhiều điều kiện hoàn tiền với các mốc thời gian |
| **Điều khiển (control-flow)** | Có bao nhiêu nhánh, vòng lặp và đường đi có thể chạy? | Nhiều nhánh **if/else** và ngoại lệ lồng nhau |
| **Cấu trúc/phụ thuộc** | Để sửa một điều phải hiểu hoặc thay đổi bao nhiêu thành phần? | Service phụ thuộc trực tiếp vào nhiều API và loại dữ liệu |
| **Trạng thái và dữ liệu** | Có bao nhiêu trạng thái hợp lệ, dữ liệu được cập nhật ở đâu và theo thứ tự nào? | Cờ chia sẻ có thể thay đổi không đồng bộ |
| **Nhận thức (cognitive)** | Người đọc phải ghi nhớ bao nhiêu điều kiện hoặc ngữ cảnh cùng lúc? | Điều kiện phủ định nhiều tầng, hàm gọi qua chuỗi dài |
| **Thuật toán/tài nguyên** | Thời gian và bộ nhớ tăng thế nào khi dữ liệu lớn lên? | Tìm kiếm tuyến tính O(n) hay dùng chỉ mục gần O(1) trung bình |
| **Vận hành/phân tán** | Điều gì xảy ra khi mạng chậm, timeout, retry hoặc hai tác vụ cập nhật cùng lúc? | Ghi dữ liệu ở hai dịch vụ và một bước thất bại |

Các góc nhìn có quan hệ nhưng **không đồng nhất**.

Ví dụ, một thuật toán sắp xếp có độ phức tạp thời gian **O(n log n)**. Điều đó không cho biết mã Java gọi thuật toán có dễ bảo trì không. Một phương thức chỉ mười dòng cũng có thể khó hiểu nếu có nhiều trạng thái ngầm. Ngược lại, một thuật toán được viết rõ từng bước có thể dài hơn nhưng vẫn dễ kiểm chứng.

## 4. Độ phức tạp thuật toán không phải toàn bộ độ phức tạp mã

Ký hiệu **Big O** mô tả xu hướng tăng chi phí tính toán theo kích thước đầu vào trong một mô hình phân tích. Nó giúp lựa chọn thuật toán, nhưng không phải thước đo đầy đủ cho khả năng đọc hiểu hoặc thay đổi.

Ví dụ, kiểm tra một mã sản phẩm đã tồn tại trong danh sách:

~~~java
boolean containsSku(java.util.List<String> skus, String target) {
    return skus.contains(target);
}
~~~

Thao tác tìm kiếm tuyến tính trên **ArrayList** thường có độ phức tạp O(n). Nếu danh sách chỉ có vài chục phần tử và ít truy vấn, giải pháp này có thể đủ đơn giản và hiệu quả.

Trong trường hợp phải tra cứu hàng triệu lần trên tập dữ liệu lớn, cấu trúc **HashSet** có thể giảm thời gian tra cứu trung bình về gần O(1), đổi lại chi phí bộ nhớ và xây dựng tập. Không có lý do mặc định để thay mọi **List** bằng **Set**, vì **List** còn bảo toàn thứ tự, cho phép phần tử trùng và có ngữ nghĩa khác. Trước khi đổi cấu trúc dữ liệu, cần xác định hợp đồng và kích thước tải thực.

Bảng phân biệt:

| Nhận xét | Có thể kết luận gì? | Chưa thể kết luận gì? |
| --- | --- | --- |
| Thuật toán O(n²) | Chi phí có thể tăng nhanh khi n lớn | Chắc chắn không phù hợp với dữ liệu nhỏ |
| Một hàm có nhiều nhánh | Cần xem lại số đường đi và lý do tồn tại | Tất cả các nhánh đều thừa |
| Hàm chỉ có năm dòng | Mã ngắn về hình thức | Mã dễ hiểu và đúng |
| Một luồng đi qua nhiều service | Hệ thống có nhiều bước phối hợp | Mọi service đều không cần thiết |
| Số lớp giảm sau refactor | Cấu trúc có ít lớp hơn | Độ phức tạp nghiệp vụ hoặc phụ thuộc cũng giảm |

Tối ưu thuật toán giải quyết **chi phí tính toán**; refactor kiến trúc giải quyết **cách tổ chức tri thức và phụ thuộc**. Đôi khi một thay đổi cải thiện cả hai, nhưng cần đánh giá từng mục tiêu bằng bằng chứng riêng.

## 5. Những nguồn phổ biến làm độ phức tạp triển khai tăng

### 5.1. Trách nhiệm bị trộn lẫn

Một phương thức vừa kiểm tra quyền truy cập, tính giá, ghi database, gọi thanh toán và gửi email khiến nhiều lý do thay đổi tập trung ở một nơi. Khi test phép tính giá, người phát triển phải dựng cả cơ sở dữ liệu và email service.

Cách cải thiện thường là **tách phép tính thuần khỏi thao tác I/O**, để ứng dụng điều phối các bước thông qua ranh giới rõ ràng. Nhưng không cần tạo thêm một lớp cho mỗi dòng mã: mỗi ranh giới nên có trách nhiệm và lợi ích cụ thể.

### 5.2. Trạng thái ẩn và tác dụng phụ không rõ

Một phương thức tên **calculateTotal()** nhưng đồng thời lưu vào database khiến người gọi không thể dự đoán tác dụng. Một singleton có biến toàn cục thay đổi giữa các request có thể tạo lỗi phụ thuộc thứ tự gọi.

Giảm độ phức tạp bằng cách làm **đầu vào, đầu ra và nơi thay đổi trạng thái** rõ ràng. Những trạng thái nghiệp vụ thực sự cần thiết vẫn phải được mô hình hóa, thay vì giả vờ hệ thống không có trạng thái.

### 5.3. Điều kiện nghiệp vụ bị sao chép

Nếu quy tắc miễn phí vận chuyển “từ 500.000 đồng” nằm trong controller web, API di động và job lập hóa đơn, ba nơi có thể dùng các dấu so sánh khác nhau. Đây là một nguồn phức tạp triển khai: một tri thức nghiệp vụ có nhiều bản sao và nhiều nơi sửa.

Nên xác định **nơi sở hữu quy tắc** và gọi qua một hợp đồng rõ ràng. Tuy nhiên, đừng gộp hai quy tắc khác nhau chỉ vì chúng cùng có một phép so sánh hoặc cùng dùng phần trăm.

### 5.4. Abstraction không phục vụ một thay đổi có thật

Một hệ thống có interface, base class, factory, strategy registry và adapter cho thao tác cộng hai số sẽ có nhiều điểm điều hướng nhưng rất ít lợi ích.

Abstraction hữu ích khi nó **cô lập phụ thuộc**, **thể hiện một hợp đồng bền vững** hoặc **đón nhận sự biến đổi đã có bằng chứng**. Nếu chỉ được tạo vì “có thể sau này cần”, nó có thể tăng chi phí hiện tại.

### 5.5. Nhiều giá trị cấu hình không có mối quan hệ rõ

Các biến **timeout**, **retry**, **queueSize** và **maxConcurrency** có thể tác động lẫn nhau. Nếu cấu hình nằm rải rác và không có ngân sách tổng, thay một thông số có thể làm hệ thống quá tải hoặc vi phạm thời gian phản hồi.

Giảm sự khó hiểu bằng cách mô tả **bất biến và ngân sách**: tổng thời gian cho một yêu cầu, loại lỗi được retry, số công việc có thể chờ. Phần phức tạp do hạ tầng chậm là thực tế phải đối diện; phần phức tạp do cấu hình không được giải thích là có thể giảm.

### 5.6. Dữ liệu mơ hồ

Ví dụ, một phương thức nhận:

~~~java
processAmount(1000, 3, true);
~~~

Người đọc khó biết 1000 là đơn vị tiền gì, 3 là số lượng hay tỷ lệ và **true** có ý nghĩa gì. Một kiểu dữ liệu hoặc tham số tên rõ ràng sẽ giảm số giả định phải nhớ:

~~~java
record PriceLine(
        java.math.BigDecimal unitPrice,
        int quantity,
        boolean taxIncluded) {
}

void processAmount(PriceLine line) {
    // Xử lý theo hợp đồng đã được định nghĩa.
}
~~~

Không phải mọi tham số đều cần tạo một record riêng. Nhưng khi nhiều giá trị đi cùng nhau, có bất biến và thường bị truyền sai vị trí, một kiểu dữ liệu có tên sẽ giảm gánh nặng nhận thức.

## 6. Tách độ phức tạp bản chất khỏi độ phức tạp triển khai như thế nào?

Có thể dùng quy trình năm câu hỏi.

**Câu hỏi 1 — Nghiệp vụ thật sự yêu cầu điều gì?**

Viết hợp đồng độc lập với Java, framework và tên lớp: đầu vào, đầu ra, quy tắc, trạng thái, trường hợp biên và tác dụng phụ được phép. Dùng bảng quyết định hoặc sơ đồ trạng thái khi cần.

**Câu hỏi 2 — Quy tắc nào không thể bỏ nếu vẫn giữ nguyên yêu cầu?**

Ví dụ, hệ thống đặt hàng phải phân biệt đã thanh toán và chưa thanh toán. Ta không thể xóa khái niệm này chỉ bằng cách bỏ một nhánh **if**. Có thể biểu diễn nó bằng enum hoặc mô hình trạng thái tốt hơn.

**Câu hỏi 3 — Khó khăn nào do quyết định triển khai gây ra?**

Tìm những biểu hiện như:
- Cùng quy tắc tồn tại ở nhiều nơi.
- Trạng thái được mã hóa bằng cờ không ràng buộc.
- Trách nhiệm nghiệp vụ và I/O trộn lẫn.
- Người đọc phải nhớ thứ tự gọi ngầm.
- Một thay đổi nhỏ kéo theo sửa nhiều lớp không liên quan.
- Những thành phần trung gian chỉ chuyển tiếp và làm mất ngữ cảnh.

**Câu hỏi 4 — Có thể thay cách biểu diễn mà giữ nguyên hợp đồng không?**

Đề xuất phương án cụ thể: bảng quyết định, enum, kiểu dữ liệu có bất biến, hàm thuần, lớp sở hữu quy tắc, adapter tại ranh giới hệ thống hoặc loại bỏ abstraction không cần thiết. Hỏi liệu phương án mới có giảm số trạng thái không hợp lệ, số nơi sửa và số điều cần ghi nhớ không.

**Câu hỏi 5 — Có bằng chứng phương án mới tốt hơn không?**

Viết test chứng minh hành vi trước/sau. Khi liên quan hiệu năng, chạy benchmark hoặc profiling có tải đại diện. Khi liên quan khả năng thay đổi, xem phạm vi sửa cho một tình huống thật. Khi liên quan sự dễ hiểu, dùng code review và khả năng giải thích hợp đồng.

Không nên kết luận một refactor thành công chỉ vì **ít dòng hơn** hoặc **ít lớp hơn**.

## 7. Sơ đồ quyết định khi gặp mã khó hiểu

~~~mermaid
flowchart TD
    A[Phát hiện đoạn mã khó hiểu] --> B[Viết rõ yêu cầu và bất biến]
    B --> C{Quy tắc có thật trong nghiệp vụ?}
    C -- Có --> D[Mô hình hóa rõ quy tắc và trạng thái]
    C -- Không --> E[Xem cấu trúc và phụ thuộc triển khai]
    D --> F{Biểu diễn hiện tại có tạo trạng thái hoặc ràng buộc thừa?}
    E --> F
    F -- Có --> G[Đề xuất cách biểu diễn đơn giản hơn]
    F -- Không --> H[Giữ cấu trúc cần thiết và bổ sung giải thích/test]
    G --> I[Kiểm chứng hành vi và chi phí thay đổi]
    H --> I
    I --> J[Review kết quả theo bối cảnh]
~~~

Sơ đồ không thể thay thế phán đoán chuyên môn. Nó giúp tránh hai cực đoan: **xóa đi quy tắc có thật** để mã trông ngắn hơn và **giữ nguyên cấu trúc khó hiểu** vì cho rằng nghiệp vụ vốn phức tạp.

## 8. Bảng quyết định: làm rõ quy tắc trước khi viết điều kiện

Một công cụ hữu ích là **decision table**. Giả sử đơn hàng được giảm phí vận chuyển khi:
- Khách có hạng **PREMIUM**; hoặc
- Khách thông thường có tạm tính từ **500.000 đồng**;
- Nhưng đơn hàng đã bị hủy **không được áp dụng** chương trình.

Đây là quy tắc minh họa, không phải chính sách của một hệ thống cụ thể.

| Đơn bị hủy? | Hạng khách | Tạm tính | Có ưu đãi? |
| --- | --- | --- | --- |
| Có | Bất kỳ | Bất kỳ | Không |
| Không | PREMIUM | Bất kỳ giá trị hợp lệ | Có |
| Không | REGULAR | Từ 500.000 đồng | Có |
| Không | REGULAR | Dưới 500.000 đồng | Không |

Mã Java đơn giản từ bảng:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

enum CustomerTier {
    REGULAR,
    PREMIUM
}

final class ShippingBenefit {
    private static final BigDecimal THRESHOLD =
            new BigDecimal("500000");

    static boolean eligible(
            boolean cancelled,
            CustomerTier tier,
            BigDecimal subtotal) {

        Objects.requireNonNull(tier, "tier");
        Objects.requireNonNull(subtotal, "subtotal");
        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }

        if (cancelled) {
            return false;
        }
        if (tier == CustomerTier.PREMIUM) {
            return true;
        }
        return subtotal.compareTo(THRESHOLD) >= 0;
    }
}
~~~

Mã vẫn có điều kiện vì bảng nghiệp vụ có điều kiện. Ta đã **sắp xếp quy tắc theo thứ tự rõ ràng**: kiểm tra dữ liệu, loại đơn hủy, áp dụng quyền lợi của PREMIUM, rồi xét ngưỡng REGULAR.

Một lỗi có thể xảy ra nếu viết điều kiện phức tạp trong một dòng:

~~~java
// Rất dễ đọc sai thứ tự ưu tiên toán tử khi logic thay đổi.
return tier == CustomerTier.PREMIUM
        || subtotal.compareTo(THRESHOLD) >= 0 && !cancelled;
~~~

Vì **&&** có độ ưu tiên cao hơn **||**, biểu thức này có nghĩa: **PREMIUM luôn được ưu đãi**, kể cả khi đơn đã hủy. Nó không tương đương với bảng quyết định. Nếu cần dùng biểu thức gộp, phải viết dấu ngoặc thể hiện đúng ý nghĩa:

~~~java
return !cancelled && (
        tier == CustomerTier.PREMIUM
        || subtotal.compareTo(THRESHOLD) >= 0);
~~~

Ở đây, **đặt ngoặc** và **tách nhánh theo nghiệp vụ** làm giảm độ phức tạp nhận thức mà không làm mất bất kỳ quy tắc bản chất nào. Test nên bao phủ đơn PREMIUM đã hủy, REGULAR dưới ngưỡng, bằng ngưỡng và trên ngưỡng.

## 9. Khi “giảm độ phức tạp” chỉ làm nó chuyển chỗ

Một refactor có thể làm một phương thức ngắn hơn nhưng chuyển khó khăn sang nơi khác:

| Cách “làm gọn” | Độ phức tạp đã đi đâu? | Cần đánh giá gì? |
| --- | --- | --- |
| Đưa 15 điều kiện vào một helper tên chung **isValid()** | Quy tắc bị giấu trong helper | Người đọc có biết điều kiện gì được bảo vệ không? |
| Tách một luồng tuyến tính thành 12 lớp | Luồng phải được lần qua nhiều file | Có trách nhiệm độc lập nào thực sự được tách không? |
| Dùng reflection và cấu hình động để bỏ các nhánh | Ràng buộc chuyển sang runtime, khó dò lỗi | Có cần mở rộng động; lỗi cấu hình có được phát hiện sớm không? |
| Đẩy mọi logic vào database stored procedure | Tri thức nghiệp vụ đổi vị trí | Ranh giới truy cập, kiểm thử và triển khai có rõ không? |
| Tạo một framework xử lý mọi biến thể | Tăng cách kết hợp cấu hình và đường chạy | Có biến thể thực tế nào cần hỗ trợ không? |
| Chỉ bắt mọi exception rồi trả kết quả rỗng | Lỗi bị giấu | Hợp đồng và khả năng chẩn đoán còn đúng không? |
| Chỉ cắt bỏ test “khó viết” | Mất khả năng kiểm chứng | Sự khó test có phản ánh thiết kế bị gắn I/O không? |

Giảm độ phức tạp **không phải** làm mất thông tin cần thiết. Một hàm tên rõ ràng, test có ý nghĩa, bảng quyết định hoặc tài liệu hợp đồng ngắn có thể làm người đọc hiểu vấn đề nhanh hơn dù số dòng tổng thể tăng.

## 10. Đánh đổi khi quyết định cấu trúc

### 10.1. Đơn giản cho người đọc hay linh hoạt cho tương lai?

Tách interface và chiến lược khác nhau có thể hữu ích khi hệ thống có nhiều nhà cung cấp thực. Nhưng nếu chỉ có một triển khai ổn định, thêm interface, registry, factory và hệ thống chọn cấu hình có thể làm phức tạp luồng hiện tại.

Đặt câu hỏi: **“Chúng ta đang bảo vệ một điểm thay đổi đã biết hay chỉ dự đoán một khả năng chưa có chứng cứ?”** Thời gian và công sức bảo trì hiện tại là chi phí thật; lợi ích của mở rộng giả định có thể không bao giờ xuất hiện.

### 10.2. Giảm lặp hay giảm liên kết?

Hai chính sách có cùng phép nhân phần trăm không nhất thiết có chung hợp đồng. Nếu một là **discount** và một là **refund**, điều kiện làm tròn, đối tượng được phép, thời hạn và lý do thay đổi có thể khác nhau.

Có thể chia sẻ tiện ích toán học rất nhỏ với hợp đồng rõ ràng, nhưng nên giữ quy tắc nghiệp vụ ở những thành phần có trách nhiệm tương ứng. **DRY** có giá trị nhất khi tránh sao chép **cùng một tri thức cần thay đổi cùng nhau**, không phải mọi chuỗi ký tự giống nhau.

### 10.3. Xử lý mọi trường hợp hay xây đúng phạm vi?

Mô hình hóa cả hoàn tiền, giao hàng quốc tế và thanh toán trả góp ngay từ ngày đầu có thể biến một tính năng đặt hàng đơn giản thành hệ thống quy tắc khó hiểu. Ngược lại, cố tình bỏ qua trường hợp nghiệp vụ đã cam kết chỉ để code ngắn là lỗi đúng đắn.

Cách phù hợp là phân biệt **yêu cầu hiện tại đã xác nhận**, **yêu cầu sắp đến có cơ sở rõ** và **khả năng giả định**. Chỉ thêm mức phức tạp có giá trị kiểm chứng được.

### 10.4. Tối ưu hiệu năng hay bảo vệ khả năng hiểu?

Một thuật toán hoặc cấu trúc dữ liệu phức tạp hơn có thể phù hợp khi có số đo chứng minh lợi ích trên dữ liệu lớn. Nhưng thay mã dễ hiểu bằng một micro-optimization thiếu benchmark thường tăng rủi ro.

Thực hành tốt là giữ test hành vi, đo trước/sau và ghi lý do của tối ưu. Nếu hiệu năng không phải vấn đề, mã rõ ràng với cấu trúc dữ liệu phù hợp thường đáng ưu tiên.

## 11. Những chỉ số và dấu hiệu có thể sử dụng

Không có **một con số** nào tóm tắt toàn bộ độ phức tạp mã nguồn. Kết hợp các tín hiệu:

| Tín hiệu | Có thể gợi ý gì? | Giới hạn |
| --- | --- | --- |
| **Cyclomatic complexity** | Số đường đi điều khiển độc lập tăng theo nhánh/điểm rẽ | Không cho biết mỗi nhánh là cần thiết hay thừa |
| **Cognitive complexity** | Người đọc phải xử lý mức lồng nhau và ngắt mạch suy luận | Phụ thuộc cách chấm điểm của công cụ; không thay code review |
| **Độ sâu lồng nhau** | Nhiều ngữ cảnh cần giữ khi đọc | Một số cấu trúc lồng nhau là tự nhiên với bài toán |
| **Số tham số/cờ điều khiển** | Phương thức có thể gánh nhiều chế độ hành vi | Một vài tham số rõ ràng không phải tự thân là lỗi |
| **Mức liên kết giữa module** | Thay đổi một nơi có thể tác động nhiều nơi khác | Phụ thuộc qua hợp đồng bền vững có thể hợp lý |
| **Change amplification** | Một quy tắc đổi khiến phải sửa nhiều chỗ | Cần phân biệt sửa nhiều chỗ cần thiết và sao chép không cần thiết |
| **Thời gian hiểu và kiểm thử** | Người bảo trì khó xác định luồng hoặc tạo test cô lập | Cần đặt trong bối cảnh kinh nghiệm và công cụ hiện có |
| **Lỗi hồi quy ở cùng vùng mã** | Ranh giới hoặc mô hình có thể gây hiểu nhầm | Số lỗi còn phụ thuộc vào tần suất thay đổi và mức kiểm thử |

**Cyclomatic complexity** thường được giới thiệu qua số nhánh quyết định cộng một cho đoạn điều khiển đơn giản. Công thức tổng quát dựa trên đồ thị điều khiển cần xét cách xây dựng đồ thị và số thành phần liên thông; đừng dùng công thức rút gọn để tranh luận chính xác từng điểm với mọi cấu trúc Java.

Một phương thức có điểm cyclomatic cao vì nhiều quy tắc hợp lệ không nhất thiết phải bị tách thành nhiều phương thức vô nghĩa. Có thể cần một **bảng quy tắc** hoặc **state machine** rõ hơn. Ngược lại, phương thức có điểm thấp vẫn có thể khó hiểu nếu có trạng thái toàn cục và phụ thuộc ngầm.

Đánh giá nên trả lời: **người khác có thể dự đoán hành vi, xác định nơi sửa và chứng minh một thay đổi không phá hợp đồng hay không?**

## 12. Cách cải thiện từng bước trong một mã nguồn có sẵn

Một quá trình giảm độ phức tạp có thể tiến hành như sau:

1. **Khoanh vùng nhiệm vụ:** Chọn một hành vi hoặc thay đổi cụ thể, chẳng hạn “thêm quy tắc hủy đơn khi đã xác nhận”. Không bắt đầu bằng việc “làm sạch toàn bộ codebase”.
2. **Thu thập yêu cầu và bất biến:** Xác minh bằng nghiệp vụ, test hiện có hoặc hành vi đã cam kết. Ghi rõ những trạng thái, điều kiện và tác dụng phụ cần giữ.
3. **Vẽ mô hình tối thiểu:** Bảng chuyển trạng thái, sơ đồ luồng hoặc ví dụ đầu vào/đầu ra. Dùng ngôn ngữ nghiệp vụ trước khi thiết kế lớp.
4. **Chỉ ra độ phức tạp triển khai:** Nơi quy tắc bị sao chép, trạng thái không hợp lệ có thể tạo, phụ thuộc I/O làm test khó, chuỗi lớp trung gian không mang thêm ý nghĩa.
5. **Đề xuất một thay đổi nhỏ có mục tiêu:** Ví dụ, thay nhiều cờ bằng enum; tách phép tính thuần; tập trung quy tắc chuyển trạng thái; đặt tên rõ đơn vị dữ liệu.
6. **Bảo vệ hợp đồng bằng test:** Thêm test cho hành vi quan trọng và trường hợp biên, đặc biệt khi refactor đụng đến các nhánh đang chạy thật.
7. **Kiểm chứng và review:** So sánh luồng đọc, số trạng thái không hợp lệ, số nơi phải sửa và rủi ro mới. Nếu có thay đổi hiệu năng, đo tải đại diện.
8. **Dừng khi đã đủ rõ:** Không tiếp tục trừu tượng hóa chỉ vì có thể. Mục tiêu là giảm chi phí hiểu và sửa, không phải đạt một hình thức kiến trúc lý tưởng.

Ví dụ, để thay **OrderFlags** bằng **OrderStatus** trong hệ thống đang có dữ liệu cũ, có thể cần bước ánh xạ, kiểm tra dữ liệu bất thường, migration và xử lý tương thích. Đó là chi phí triển khai thực tế; không nên giả định refactor mô hình trong ví dụ luôn có thể áp dụng ngay trên production.

## 13. Tình huống tổng hợp: giá vận chuyển phụ thuộc khu vực

Nhóm nhận yêu cầu mới: phí vận chuyển phụ thuộc **khu vực**, **khối lượng**, **loại khách hàng** và **thời điểm giao**. Trong mã đang chạy, công thức nằm ở controller, một job lập hóa đơn và ứng dụng di động. Mỗi nơi có các hằng số và kiểm tra điều kiện khác nhau.

### Phân tích nguồn gốc độ phức tạp

**Phần thuộc bản chất bài toán:**
- Chính sách thực sự phân biệt khu vực, khối lượng, loại khách và khung thời gian.
- Có trường hợp ngoại lệ về ngày nghỉ hoặc khu vực không hỗ trợ nếu nghiệp vụ xác nhận.
- Cần quy tắc ưu tiên khi nhiều chương trình cùng áp dụng.
- Số tiền cần có đơn vị, độ chính xác và làm tròn nhất quán.

**Phần do triển khai:**
- Một chính sách được sao chép ở ba nơi.
- Hằng số không có người sở hữu rõ.
- Quy tắc ưu tiên bị ngầm định bởi thứ tự các câu **if**.
- Mỗi nơi xử lý tiền hoặc ngưỡng khác nhau.
- Không có bộ test dùng chung cho điều kiện biên.

### Hướng cải thiện

Trước tiên, làm rõ chính sách bằng **decision table**, với các trường hợp biên được nghiệp vụ xác nhận. Sau đó đặt quyết định tính phí tại một thành phần hoặc dịch vụ có hợp đồng ổn định; xác định cách các kênh sử dụng kết quả và xử lý lỗi. Viết test cho các tổ hợp có ý nghĩa, đặc biệt khi điều kiện giao nhau.

Không nhất thiết tạo ngay một **rules engine** động, vì chính rules engine có thể mang thêm cấu hình, thứ tự ưu tiên, phiên bản chính sách và cơ chế debug. Chỉ cân nhắc khi tần suất thay đổi quy tắc, số biến thể và quyền quản trị thực sự biện minh cho chi phí ấy.

## 14. Bài tập thực hành

### Bài tập 1: Phân loại nguồn phức tạp

Với mỗi tình huống, hãy chỉ ra phần **bản chất**, phần **do triển khai** và hướng xử lý:

1. Hệ thống ngân hàng phải tính lãi theo nhiều kỳ và sản phẩm được pháp luật quy định khác nhau.
2. Một ứng dụng dùng năm cờ boolean độc lập để mô tả ba trạng thái giao hàng hợp lệ.
3. Dịch vụ thanh toán cần giải quyết việc client timeout dù server có thể đã xử lý giao dịch.
4. Để đổi một ngưỡng khuyến mại phải sửa ở controller web, service, mobile client và tác vụ báo cáo.
5. Một helper tính chuỗi ngắn phải đi qua bốn interface và ba factory dù chỉ có một cách triển khai.

**Gợi ý:** (1) và (3) có phần bản chất đáng kể; (2), (4), (5) chỉ ra cơ hội giảm độ phức tạp do biểu diễn, nhân bản tri thức và abstraction. Tuy nhiên, mỗi tình huống cần xác nhận hợp đồng và ràng buộc thật trước khi refactor.

### Bài tập 2: Đọc biểu thức điều kiện

Cho mã:

~~~java
boolean eligible(
        boolean cancelled,
        boolean premium,
        boolean reachedThreshold) {

    return premium || reachedThreshold && !cancelled;
}
~~~

Yêu cầu nghiệp vụ: “Đơn đã hủy không được ưu đãi; đơn còn hiệu lực được ưu đãi nếu là PREMIUM hoặc đạt ngưỡng”.

Hãy:
- Tìm một trường hợp mà mã hiện tại trả sai.
- Viết biểu thức hoặc cấu trúc điều kiện đúng.
- Đề xuất ba test thể hiện ý định nghiệp vụ.

**Đáp án gợi ý:** Với **premium = true**, **cancelled = true**, mã hiện tại trả **true** do ưu tiên toán tử. Biểu thức đúng là **!cancelled && (premium || reachedThreshold)**. Nên kiểm tra đơn PREMIUM bị hủy, đơn REGULAR đạt ngưỡng còn hiệu lực và đơn REGULAR dưới ngưỡng còn hiệu lực.

### Bài tập 3: Lựa chọn biểu diễn trạng thái

Một hệ thống quản lý phê duyệt có các trạng thái **SUBMITTED**, **APPROVED**, **REJECTED**, **CANCELLED**. Người phát triển đề xuất lưu hai cờ **approved** và **rejected**, kết hợp thêm **active**.

Hãy phân tích:
- Có bao nhiêu tổ hợp cờ lý thuyết?
- Những trạng thái nào mơ hồ hoặc không hợp lệ?
- Dùng **enum**, bảng chuyển trạng thái và điều kiện bảo vệ nào sẽ rõ hơn?
- Nếu hệ thống còn lưu lịch sử nhiều lần phê duyệt/từ chối, liệu một enum duy nhất có đủ? Vì sao?

**Gợi ý:** Ba cờ tạo tối đa **8 tổ hợp** và có thể không mô tả đúng bốn trạng thái nghiệp vụ. Một enum là phù hợp cho **trạng thái hiện tại**, nhưng lịch sử nhiều sự kiện có thể cần cấu trúc dữ liệu khác. Không được nhầm việc giảm trạng thái mâu thuẫn với xóa yêu cầu lưu lịch sử.

### Bài tập 4: Đánh giá một refactor

Một pull request giảm một phương thức từ 80 dòng xuống 12 dòng bằng cách chuyển logic sang chín phương thức con. Mỗi phương thức có tên **step1**, **step2**, **handleData**; các phương thức con thay đổi một biến trạng thái dùng chung.

Hãy nhận xét:
- Số dòng giảm đã chứng minh độ phức tạp nhận thức giảm chưa?
- Việc chia nhỏ có tạo trách nhiệm và hợp đồng rõ ràng không?
- Có thể cải thiện bằng cách đặt tên theo nghiệp vụ, trả kết quả rõ ràng hoặc giảm trạng thái dùng chung thế nào?
- Những test nào cần giữ để bảo vệ hành vi?

**Gợi ý:** Refactor chỉ có giá trị khi làm ý định dễ theo dõi, giảm phụ thuộc ngầm và duy trì hợp đồng. Nếu sự khó hiểu chỉ bị chuyển sang các hàm tên mơ hồ, lợi ích có thể rất thấp.

## 15. Những hiểu nhầm thường gặp

- **“Mã càng ngắn càng đơn giản.”** Mã ngắn có thể nén nhiều giả định vào một biểu thức; đôi khi thêm tên biến hoặc bảng quyết định sẽ dễ đọc hơn.
- **“Phương thức có nhiều nhánh chắc chắn viết kém.”** Có thể nghiệp vụ có nhiều trường hợp. Cần xác định nhánh nào cần thiết và có cách mô hình hóa rõ hơn không.
- **“Thêm abstraction luôn giảm phức tạp.”** Abstraction chỉ hữu ích khi giảm số chi tiết phải biết và làm rõ hợp đồng; nếu chỉ tăng số điểm điều hướng, nó có thể gây tác dụng ngược.
- **“Chuyển sang microservice là đơn giản hóa.”** Microservice có thể cô lập trách nhiệm nhưng đem thêm giao tiếp mạng, lỗi phân tán, versioning và vận hành. Độ phức tạp có thể chuyển từ trong tiến trình sang giữa các tiến trình.
- **“Refactor đẹp có thể bỏ test.”** Khi đổi cách biểu diễn và ranh giới, test giúp chứng minh các quy tắc bản chất vẫn được bảo vệ.
- **“Một chỉ số complexity có thể kết luận mã tốt/xấu.”** Công cụ tạo tín hiệu để điều tra; cần đọc yêu cầu, hợp đồng, rủi ro và khả năng thay đổi thực tế.
- **“Chỉ cần giảm nhánh if là giải quyết xong.”** Nhánh bị ẩn trong cấu hình, annotation, callback hoặc rule engine vẫn cần được hiểu, kiểm thử và vận hành.

## Ghi nhớ

**Độ phức tạp do bản thân bài toán** đến từ những quy tắc, trạng thái và ràng buộc hệ thống bắt buộc phải xử lý; **độ phức tạp do cách triển khai** đến từ quyết định biểu diễn và tổ chức làm công việc khó hơn mức cần thiết. Muốn mã đáng tin cậy, dễ hiểu và dễ thay đổi, trước tiên phải làm rõ phần phức tạp thực sự cần có, rồi giảm trạng thái không hợp lệ, phụ thuộc ngầm, quy tắc sao chép và tầng trừu tượng không có mục đích. Đánh giá kết quả bằng **tính đúng đắn, khả năng đọc hiểu, phạm vi thay đổi và bằng chứng kiểm thử**, thay vì chỉ đếm dòng mã hoặc số lớp.
