# Làm rõ điều kiện boolean và các nhánh xử lý

Mã có thể chạy đúng hôm nay nhưng vẫn khó bảo trì nếu người đọc phải tự giải mã một biểu thức boolean dài hoặc lần theo nhiều lớp **if/else** để hiểu vì sao một nhánh được chọn. Khi yêu cầu nghiệp vụ thay đổi, cách viết thiếu rõ ràng làm tăng nguy cơ sửa sai điều kiện, bỏ sót trường hợp biên và tạo lỗi hồi quy.

Trong module **CODE_QUALITY_FUNDAMENTALS**, khả năng đọc là một yếu tố quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không. Bài này tập trung vào việc diễn đạt **ý nghĩa của điều kiện**, tổ chức **các nhánh xử lý** và kiểm chứng rằng việc cải thiện cách viết vẫn giữ nguyên hành vi đúng theo yêu cầu.

## 1. Đọc điều kiện boolean là đọc một quyết định

Một biểu thức boolean trả về **true** hoặc **false**, nhưng ý nghĩa của nó trong chương trình thường rộng hơn giá trị logic:

- Đầu vào có hợp lệ không?
- Người dùng có đủ quyền thực hiện thao tác không?
- Giao dịch có được phép chuyển trạng thái không?
- Dịch vụ có nên thực hiện hành động tiếp theo không?

Ví dụ:

~~~java
if (a && b && !c) {
    process();
}
~~~

Để hiểu đoạn này, người đọc phải lần tìm **a**, **b**, **c**. Nếu chúng là những tên khó hiểu hoặc được tính ở xa, việc kiểm tra mã rất tốn công.

Cách thể hiện sát nghiệp vụ hơn:

~~~java
if (isAccountActive && hasValidSubscription && !isSuspended) {
    process();
}
~~~

Biểu thức thứ hai cho thấy các điều kiện cần đáp ứng. Dù vậy, tên rõ ràng không thay thế việc kiểm chứng chúng có thực sự được tính đúng và cập nhật đúng thời điểm hay không.

**Một điều kiện dễ đọc phải trả lời được:** “Khi nào nhánh này được thực hiện và vì sao?”

## 2. Những dấu hiệu khiến điều kiện khó hiểu

| Dấu hiệu | Ví dụ hoặc hiện tượng | Rủi ro |
| --- | --- | --- |
| **Tên biến mơ hồ** | ok, flag, check, a, b | Người đọc phải truy ngược nhiều bước để biết ý nghĩa. |
| **Phủ định chồng nhau** | !isNotEligible | Dễ hiểu ngược kết quả. |
| **Biểu thức dài** | Nhiều điều kiện && và &#124;&#124; chen nhau | Khó nhận ra quy tắc và thứ tự ưu tiên. |
| **Nhánh lồng sâu** | if bên trong if, mỗi nhánh lại có if/else | Khó theo dõi mọi đường đi và điểm kết thúc. |
| **Điều kiện lặp** | Cùng kiểm tra quyền ở nhiều nhánh | Khi chính sách đổi, các bản sao có thể lệch nhau. |
| **Tác dụng phụ trong điều kiện** | Kiểm tra đồng thời ghi dữ liệu hoặc gọi mạng | Khó dự đoán thứ tự thực thi và kết quả. |
| **Boolean không đủ trạng thái** | true/false nhưng còn “chưa xác định” | Có thể ép một trạng thái chưa biết thành quyết định sai. |

Cách cải thiện tùy vào bản chất của vấn đề: đặt lại tên, nhóm biểu thức, trích xuất một ý định nghiệp vụ, dùng **guard clause**, chia phương thức hoặc dùng một kiểu dữ liệu phù hợp hơn.

Không nên biến mọi phép so sánh đơn giản thành phương thức riêng. Mục tiêu là làm rõ quyết định, không phải tăng số dòng hoặc số lớp.

## 3. Đặt tên boolean theo ý nghĩa có thể khẳng định

Tên boolean hiệu quả thường đọc được như một mệnh đề:

~~~java
boolean isExpired;
boolean hasPermission;
boolean canRetry;
boolean requiresApproval;
boolean wasDelivered;
~~~

Khi dùng chúng trong điều kiện, người đọc có thể hình dung hành vi:

~~~java
if (hasPermission && !isExpired) {
    grantAccess();
}
~~~

Một số quy ước hữu ích:

- Dùng tên phản ánh **ý nghĩa nghiệp vụ**, ví dụ **hasPermission** thay vì **flag1**.
- Chọn cách diễn đạt **khẳng định** khi có thể: **isActive** dễ đọc hơn **isNotInactive**.
- Thống nhất ý nghĩa: **canCancel** chỉ nên true khi thực sự đáp ứng điều kiện hủy, không chỉ khi người dùng đang mở màn hình hủy.
- Phân biệt **trạng thái** và **hành động**: **isPaid** (đã thanh toán) khác **shouldCharge** (cần thu tiền).
- Tránh tên gây kỳ vọng sai: **isValid** quá chung nếu thực chất chỉ kiểm tra định dạng mã.

**Không có quy tắc buộc mọi biến boolean phải bắt đầu bằng is/has/can.** Điều quan trọng là tên đủ rõ và nhất quán trong ngữ cảnh.

### Khi phủ định làm thay đổi cách hiểu

So sánh:

~~~java
if (!isNotEligible) {
    approve();
}
~~~

và:

~~~java
if (isEligible) {
    approve();
}
~~~

Về mặt logic, hai biểu thức tương đương **nếu** isEligible được định nghĩa chính xác là phủ định của isNotEligible. Tuy nhiên, không nên tự ý đổi tên nếu trong mô hình thật có trạng thái “chưa đánh giá” hoặc “không xác định”. Khi đó, hai giá trị true/false có thể chưa biểu đạt hết nghiệp vụ.

## 4. Ví dụ xuyên suốt: điều kiện hủy đơn hàng

Giả sử chính sách hủy đơn có các quy tắc:

1. Người yêu cầu và đơn hàng phải tồn tại; người yêu cầu có mã định danh hợp lệ.
2. Người yêu cầu phải **đang hoạt động** và **là chủ đơn**.
3. Đơn phải ở trạng thái **DRAFT** hoặc **CONFIRMED**.
4. Đơn chưa được bàn giao vận chuyển.
5. Nếu đơn đã thanh toán, phải có phương án hoàn tiền khả dụng. Nếu chưa thanh toán, không cần hoàn tiền.

Bản viết dồn nhiều điều kiện có thể vẫn trả về đúng kết quả:

~~~java
boolean canCancel(User u, Order o) {
    return u != null && o != null
            && u.id() != null && !u.id().isBlank()
            && u.active() && u.id().equals(o.ownerId())
            && (o.status() == Status.DRAFT
                || o.status() == Status.CONFIRMED)
            && !o.dispatched()
            && (!o.paid() || o.refundAvailable());
}
~~~

Người đọc phải giữ nhiều khái niệm trong đầu: đầu vào, quyền, trạng thái, vận chuyển và hoàn tiền. Cũng dễ sửa nhầm điều kiện cuối hoặc bỏ quên dấu ngoặc khi thêm quy tắc.

### Bản làm rõ luồng bằng guard clause

~~~java
public final class OrderCancellationPolicy {
    public enum Status { DRAFT, CONFIRMED, SHIPPED, CANCELLED }

    public record User(String id, boolean active) {}

    public record Order(
            String ownerId,
            Status status,
            boolean dispatched,
            boolean paid,
            boolean refundAvailable) {}

    private OrderCancellationPolicy() {}

    public static boolean canCancel(User user, Order order) {
        if (user == null || order == null) {
            return false;
        }

        if (user.id() == null || user.id().isBlank()) {
            return false;
        }

        if (!user.active() || !user.id().equals(order.ownerId())) {
            return false;
        }

        if (!isCancelableStatus(order.status()) || order.dispatched()) {
            return false;
        }

        return !order.paid() || order.refundAvailable();
    }

    private static boolean isCancelableStatus(Status status) {
        return status == Status.DRAFT || status == Status.CONFIRMED;
    }
}
~~~

Từng bước tương ứng một nhóm lý do từ chối:

1. **Thiếu dữ liệu** → không thể đánh giá.
2. **Danh tính không hợp lệ** → không thể xác định người yêu cầu.
3. **Không đủ điều kiện sở hữu và hoạt động** → không thể hủy.
4. **Trạng thái đơn hoặc vận chuyển không cho phép** → không thể hủy.
5. **Điều kiện hoàn tiền** → quyết định cuối cùng.

Ở ví dụ này, việc trả false khi thiếu dữ liệu là một phần **hợp đồng của hàm kiểm tra khả năng hủy**. Trong API thực tế, đầu vào thiếu có thể cần phản hồi validation riêng; kiểm tra quyền phải dựa trên danh tính xác thực ở phía máy chủ. Việc phương thức trả true cũng chỉ xác nhận **đủ điều kiện tại thời điểm kiểm tra**. Hệ thống vẫn phải kiểm tra và cập nhật trạng thái đơn an toàn khi thực hiện hủy, nhất là trước thay đổi đồng thời.

### Bảng quyết định giúp đọc và kiểm tra chính sách

| Người dùng | Trạng thái | Đã giao vận chuyển | Đã thanh toán | Có đường hoàn tiền | Có thể hủy? |
| --- | --- | :---: | :---: | :---: | :---: |
| Chủ đơn đang hoạt động | DRAFT | Không | Không | Không | **Có** |
| Chủ đơn đang hoạt động | CONFIRMED | Không | Có | Có | **Có** |
| Chủ đơn đang hoạt động | CONFIRMED | Không | Có | Không | **Không** |
| Chủ đơn đang hoạt động | CONFIRMED | Có | Không | Không | **Không** |
| Chủ đơn đang hoạt động | SHIPPED | Không | Không | Không | **Không** |
| Người khác hoặc tài khoản không hoạt động | DRAFT | Không | Không | Không | **Không** |
| Không có người dùng hoặc không có đơn | Bất kỳ | Bất kỳ | Bất kỳ | Bất kỳ | **Không** |

Bảng quyết định làm rõ các trường hợp tưởng chừng giống nhau. Ví dụ **chưa thanh toán** và **đã thanh toán nhưng có đường hoàn tiền** đều có thể được hủy, nhưng vì những lý do khác nhau.

## 5. Hiểu đúng AND, OR, NOT và dấu ngoặc

Trong Java, các toán tử boolean thường gặp:

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **!** | Phủ định | !isExpired |
| **&&** | AND ngắn mạch: đúng khi cả hai vế đúng | isActive && hasPermission |
| **&#124;&#124;** | OR ngắn mạch: đúng khi ít nhất một vế đúng | isAdmin &#124;&#124; isOwner |
| **==**, **!=** | So sánh bằng/khác; với object tham chiếu so sánh định danh đối tượng | status == Status.DRAFT |

Khi kết hợp **&&** và **&#124;&#124;**, **&& có mức ưu tiên cao hơn &#124;&#124;**. Hai biểu thức dưới đây có ý nghĩa khác nhau:

~~~java
// Cho phép quản trị viên hoặc chủ đơn đang hoạt động.
boolean allowedA = isAdmin || (isOwner && isActive);

// Chỉ cho phép người đang hoạt động và (quản trị viên hoặc chủ đơn).
boolean allowedB = (isAdmin || isOwner) && isActive;
~~~

Nếu **isAdmin = true**, **isActive = false**, **isOwner = false**, thì **allowedA = true** còn **allowedB = false**. Do đó, thêm hoặc xóa ngoặc có thể thay đổi quyền truy cập.

**Nguyên tắc:** Đặt dấu ngoặc thể hiện chính sách nghiệp vụ, kể cả khi đã biết thứ tự ưu tiên của Java. Đừng dựa vào việc người review phải nhớ mọi quy tắc ưu tiên để hiểu một quyết định quan trọng.

### Hai định luật De Morgan

Khi cần đơn giản hóa phủ định, có hai quy tắc:

~~~java
!(isAdmin || isOwner) == (!isAdmin && !isOwner)
!(isActive && hasPermission) == (!isActive || !hasPermission)
~~~

Đây là các đẳng thức boolean dùng để lý giải. Trong mã thực thi, phải phân biệt **toán tử so sánh ==** với ý nghĩa diễn đạt “tương đương logic”. Không viết cả biểu thức trong ví dụ trên như một lời gọi nghiệp vụ. Ngoài ra, khi đổi cấu trúc biểu thức, cần giữ nguyên hành vi đánh giá ngắn mạch và tác dụng phụ của các phép gọi, nếu có.

Chỉ nên biến đổi điều kiện sau khi đã kiểm chứng rằng bản mới biểu đạt đúng yêu cầu.

## 6. Đánh giá ngắn mạch và kiểm tra null

Trong Java, **&&** và **&#124;&#124;** đánh giá từ trái sang phải và có thể bỏ qua vế sau:

- Với **&&**, nếu vế trái false thì vế phải không được đánh giá.
- Với **&#124;&#124;**, nếu vế trái true thì vế phải không được đánh giá.

Ví dụ đúng:

~~~java
boolean isActiveUser = user != null && user.active();
~~~

Nếu user là null, Java không gọi phương thức active().

Đổi thứ tự sẽ gây lỗi:

~~~java
// SAI: active() bị gọi trước khi kiểm tra null.
boolean isActiveUser = user.active() && user != null;
~~~

Một trường hợp nguy hiểm khác là trích xuất biến quá sớm:

~~~java
// SAI: phương thức bị gọi trước khi guard kiểm tra null.
boolean active = user.active();
if (user != null && active) {
    proceed();
}
~~~

Trích xuất điều kiện thành biến hoặc phương thức chỉ giúp dễ đọc nếu vẫn giữ **đúng thứ tự đánh giá**. Nếu một biểu thức có thể ném ngoại lệ, gọi mạng hoặc thay đổi trạng thái, việc tách ra có thể làm thay đổi hành vi ngay cả khi kết quả boolean trông tương đương.

**Ưu tiên để điều kiện đọc trạng thái, không gây tác dụng phụ.** Ví dụ, không nên kết hợp kiểm tra quyền với thao tác tự động ghi audit hoặc trừ tồn ngay trong toán hạng của &&. Tách bước quyết định và bước thực hiện giúp người đọc dễ dự đoán điều gì sẽ xảy ra.

## 7. Guard clause giúp giảm lồng nhau như thế nào?

Một đoạn mã lồng nhánh sâu:

~~~java
void submit(Request request) {
    if (request != null) {
        if (request.isValid()) {
            if (request.isAuthorized()) {
                save(request);
            } else {
                reject("Not authorized");
            }
        } else {
            reject("Invalid");
        }
    } else {
        reject("Missing request");
    }
}
~~~

Có thể làm luồng chính dễ nhìn hơn bằng cách xử lý các trường hợp không đáp ứng tiền điều kiện trước:

~~~java
void submit(Request request) {
    if (request == null) {
        reject("Missing request");
        return;
    }
    if (!request.isValid()) {
        reject("Invalid");
        return;
    }
    if (!request.isAuthorized()) {
        reject("Not authorized");
        return;
    }

    save(request);
}
~~~

Trong phiên bản thứ hai, **save** xuất hiện ở cuối sau khi các điều kiện chặn đã được kiểm tra. Người đọc không cần theo dõi nhiều tầng ngoặc nhọn.

Đổi sang guard clause chỉ phù hợp khi hành vi không thay đổi. Ví dụ, nếu reject ném ngoại lệ, các lệnh return ngay sau đó không cần thiết; nếu reject chỉ ghi phản hồi, return giúp không tiếp tục chạy sang nhánh thành công. Cần hiểu rõ hợp đồng của reject.

### Khi nào nên giữ if/else?

Không phải mọi if/else đều cần chuyển thành return sớm. Một cấu trúc **hai lựa chọn đối xứng** thường rất rõ:

~~~java
if (isNewCustomer) {
    discount = WELCOME_DISCOUNT;
} else {
    discount = STANDARD_DISCOUNT;
}
~~~

Trường hợp trên không có nhiều tầng lồng và cho thấy rõ hai hành vi đối lập. Sự rõ ràng quan trọng hơn việc bắt buộc dùng một phong cách cho toàn dự án.

## 8. Trích xuất điều kiện theo ý định nghiệp vụ

Một biểu thức dài chứa nhiều chi tiết có thể trở nên dễ hiểu khi chia theo các câu hỏi độc lập:

~~~java
boolean hasAccess(User user, Document document) {
    if (user == null || document == null) {
        return false;
    }

    boolean isOwner = user.id() != null
            && user.id().equals(document.ownerId());

    boolean canReadSharedDocument = document.isShared()
            && user.hasSharedReadPermission();

    return isOwner || canReadSharedDocument;
}
~~~

Hai tên **isOwner** và **canReadSharedDocument** giúp phần return thể hiện chính sách. Tuy vậy, cần xác định chính xác yêu cầu bảo mật: nếu người dùng bị khóa vẫn không được đọc tài liệu của mình, hàm trên còn thiếu điều kiện. Đặt tên tốt giúp **phát hiện** thiếu sót, nhưng không chứng minh chính sách đã hoàn chỉnh.

Đừng trích xuất quá mức:

~~~java
private static boolean isGreaterThanZero(int value) {
    return value > 0;
}
~~~

Một hàm như vậy hiếm khi mang thêm ý nghĩa. Trong ngữ cảnh lượng hàng, tên **hasAvailableStock** hoặc **isPositiveQuantity** có thể hữu ích hơn nếu gắn với một quy tắc thực sự và không làm giấu logic đơn giản vô ích.

## 9. Đừng dùng boolean cho quyết định có hơn hai trạng thái

Nếu nghiệp vụ có ba trạng thái **ALLOWED**, **DENIED** và **UNKNOWN**, ép chúng vào một giá trị boolean sẽ khiến người gọi không biết **false** là bị từ chối hay chưa xác định được vì phụ thuộc lỗi.

Ví dụ:

~~~java
enum Eligibility {
    ALLOWED,
    DENIED,
    UNKNOWN
}
~~~

Ở đây, enum giúp người đọc thấy ngay trạng thái cần xử lý:

~~~java
Eligibility decision = checkEligibility();

switch (decision) {
    case ALLOWED -> proceed();
    case DENIED -> reject("Not eligible");
    case UNKNOWN -> retryLater();
}
~~~

Đây là minh họa cú pháp **switch statement** với enum trong Java hiện đại. Hàm retryLater chỉ nên thực hiện khi việc thử lại thực sự an toàn theo ngữ cảnh; UNKNOWN không mặc nhiên cho phép thử lại thao tác có tác dụng phụ.

Ngoài ra, lời gọi có nhiều tham số boolean thường kém rõ ràng:

~~~java
sendNotification(true, false, true);
~~~

Người đọc không biết ba giá trị đại diện điều gì nếu không xem định nghĩa hàm. Có thể dùng tham số có tên ở đối tượng cấu hình, enum cho lựa chọn nhiều giá trị, hoặc chia các thao tác có ý nghĩa nghiệp vụ rõ ràng.

## 10. Làm rõ nhánh xử lý trong switch và luồng trạng thái

Với nhiều giá trị của cùng một trạng thái, **switch** có thể dễ đọc hơn một chuỗi so sánh lặp lại:

~~~java
String label(OrderCancellationPolicy.Status status) {
    if (status == null) {
        return "Không xác định";
    }

    return switch (status) {
        case DRAFT -> "Nháp";
        case CONFIRMED -> "Đã xác nhận";
        case SHIPPED -> "Đang giao";
        case CANCELLED -> "Đã hủy";
    };
}
~~~

Ưu điểm là mỗi trạng thái có một nhánh riêng, dễ quét và dễ kiểm tra tình huống thiếu. Với **switch expression trên enum** được compiler kiểm tra tính bao phủ, khi thêm giá trị enum mới, mã có thể cần được cập nhật; cách kiểm tra cụ thể còn phụ thuộc phiên bản Java và cách viết switch.

Đừng dùng switch chỉ để che một quy tắc quá phức tạp vào hàng chục nhánh không liên quan. Có thể tách quy tắc theo trạng thái hoặc sử dụng các đối tượng chính sách riêng khi số lượng trạng thái và chuyển tiếp thực sự lớn.

## 11. Kiểm chứng việc làm rõ mã không làm đổi hành vi

Đọc dễ hơn chưa đủ nếu bản sửa làm đổi kết quả. Với chính sách hủy đơn ở phần 4, có thể lập các ca JUnit 5 để xác nhận ranh giới:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OrderCancellationPolicyTest {
    private static final OrderCancellationPolicy.User OWNER =
            new OrderCancellationPolicy.User("u-1", true);

    private static OrderCancellationPolicy.Order order(
            OrderCancellationPolicy.Status status,
            boolean dispatched,
            boolean paid,
            boolean refundAvailable) {
        return new OrderCancellationPolicy.Order(
                "u-1", status, dispatched, paid, refundAvailable);
    }

    @Test
    void draftUnpaidCanBeCancelled() {
        assertTrue(OrderCancellationPolicy.canCancel(
                OWNER,
                order(OrderCancellationPolicy.Status.DRAFT,
                        false, false, false)));
    }

    @Test
    void paidOrderRequiresRefundPath() {
        assertFalse(OrderCancellationPolicy.canCancel(
                OWNER,
                order(OrderCancellationPolicy.Status.CONFIRMED,
                        false, true, false)));
        assertTrue(OrderCancellationPolicy.canCancel(
                OWNER,
                order(OrderCancellationPolicy.Status.CONFIRMED,
                        false, true, true)));
    }

    @Test
    void dispatchedOrderCannotBeCancelled() {
        assertFalse(OrderCancellationPolicy.canCancel(
                OWNER,
                order(OrderCancellationPolicy.Status.CONFIRMED,
                        true, false, false)));
    }

    @Test
    void otherUserCannotCancel() {
        var otherUser = new OrderCancellationPolicy.User("u-2", true);
        assertFalse(OrderCancellationPolicy.canCancel(
                otherUser,
                order(OrderCancellationPolicy.Status.DRAFT,
                        false, false, false)));
    }

    @Test
    void invalidIdentityAndNullAreRejected() {
        assertFalse(OrderCancellationPolicy.canCancel(null, 
                order(OrderCancellationPolicy.Status.DRAFT,
                        false, false, false)));
        assertFalse(OrderCancellationPolicy.canCancel(
                new OrderCancellationPolicy.User(null, true),
                order(OrderCancellationPolicy.Status.DRAFT,
                        false, false, false)));
    }
}
~~~

Các ca trên xác minh những tình huống quan trọng chứ **chưa thay thế toàn bộ bảng quyết định**. Có thể bổ sung: trạng thái SHIPPED/CANCELLED, người dùng bị khóa, đơn null, mã định danh trống, chủ đơn khác và các tổ hợp chính sách còn lại.

Khi refactor code đang chạy thật, có thể kiểm tra thêm:

- **Behavior trước và sau:** Với cùng đầu vào và trạng thái, kết quả trả về hoặc ngoại lệ có tương đương không?
- **Tác dụng phụ:** Có thay đổi số lần gọi kho dữ liệu, thứ tự thao tác hoặc cập nhật trạng thái không?
- **Short-circuit:** Có lời gọi mới xảy ra trước khi guard ngăn null hoặc lỗi không?
- **Trường hợp biên:** Các ngưỡng, trạng thái chuyển tiếp và dữ liệu trống có giữ nguyên ý nghĩa không?
- **Điều kiện được bổ sung:** Đây là thay đổi yêu cầu chủ ý hay vô tình thay đổi hành vi trong lúc dọn mã?

Nếu mã gốc chứa **lỗi nghiệp vụ**, không nên cố giữ lỗi chỉ để nói refactor tương đương. Hãy tách rõ việc **làm rõ cấu trúc** với việc **sửa hành vi**, kèm kiểm thử xác nhận yêu cầu mong muốn.

## 12. Một số phép biến đổi dễ làm sai

| Trước | Cách sửa tưởng hợp lý | Vì sao cần kiểm tra lại? |
| --- | --- | --- |
| A && B | B && A | Logic boolean thuần có thể tương đương, nhưng thứ tự đánh giá và tác dụng phụ có thể khác. |
| A &#124;&#124; B | A && B | Thay đổi ý nghĩa từ “ít nhất một” sang “cả hai”; không tương đương. |
| !paid &#124;&#124; refundable | !paid && refundable | Khi chưa thanh toán, bản mới yêu cầu cả điều kiện hoàn tiền; sai nghiệp vụ. |
| admin &#124;&#124; owner && active | (admin &#124;&#124; owner) && active | Thay đổi quyền của quản trị viên không hoạt động. |
| if (valid) { save(); } | if (!valid) { return; } save(); | Chỉ tương đương nếu không có nhánh else hoặc bước dọn dẹp/ghi trạng thái phải chạy trong mọi trường hợp. |

Trước khi đổi cấu trúc điều kiện, nên viết một **bảng chân trị nhỏ** cho các biến quyết định nếu không chắc chắn. Với ba biến boolean có thể liệt kê tối đa tám tổ hợp; khi thêm ràng buộc, cần loại các tổ hợp bất khả thi.

### Ví dụ bảng chân trị cho điều kiện hoàn tiền

| Đã thanh toán? | Có thể hoàn tiền? | !paid &#124;&#124; refundAvailable |
| :---: | :---: | :---: |
| false | false | true |
| false | true | true |
| true | false | false |
| true | true | true |

Bảng này chứng minh chính sách: **chưa thu tiền thì không cần đường hoàn tiền; đã thu tiền mới bắt buộc có đường hoàn tiền**. Đây là minh chứng rõ hơn việc chỉ nói “biểu thức đúng”.

## 13. Quy trình review điều kiện và nhánh xử lý

1. **Nêu quyết định bằng lời.** Ví dụ: “Chỉ chủ đơn đang hoạt động được hủy đơn DRAFT hoặc CONFIRMED chưa vận chuyển; đơn đã thanh toán phải có đường hoàn tiền”.
2. **Xác định từng nhóm ràng buộc.** Đầu vào, phân quyền, trạng thái, ngoại lệ và tác động phụ là những nhóm khác nhau.
3. **Đặt tên theo ý nghĩa.** Tránh cờ mơ hồ và phủ định kép; dùng tên có thể đọc như mệnh đề.
4. **Tổ chức đường đi rõ ràng.** Guard clause cho trường hợp phải từ chối sớm; if/else cho hai nhánh đối xứng; switch cho nhiều giá trị trạng thái.
5. **Kiểm tra biểu thức ghép.** Chú ý dấu ngoặc, thứ tự &&/&#124;&#124;, short-circuit và nguy cơ null.
6. **Xem tác dụng phụ.** Không để việc trích xuất biến làm gọi phụ thuộc sớm hoặc nhiều lần hơn dự kiến.
7. **Viết ca kiểm thử cho quyết định.** Xét bảng chân trị, giá trị biên, trường hợp thiếu dữ liệu, trạng thái không hợp lệ và đầu ra mong muốn.
8. **Giữ refactor ở phạm vi hiểu được.** Nếu cần thay đổi chính sách, diễn đạt riêng thay đổi hành vi và chứng minh bằng kiểm thử.

Mức độ trừu tượng nên **vừa đủ để thể hiện ý định**. Một hàm nhỏ với điều kiện rõ có thể dễ hiểu hơn hệ thống nhiều lớp quy tắc, trong khi một chính sách lớn lại cần được tách thành những khái niệm có tên.

## 14. Tự luyện

### Bài 1 — Nhận ra khác biệt ngữ nghĩa

Cho hai biểu thức:

~~~java
boolean a = isAdmin || (isOwner && isActive);
boolean b = (isAdmin || isOwner) && isActive;
~~~

**Câu hỏi:** Khi **isAdmin = true**, **isOwner = false**, **isActive = false**, a và b là gì? Hai biểu thức có thể hoán đổi cho nhau không?

**Gợi ý:** a là true, b là false. Chỉ dùng biểu thức phù hợp với chính sách quyền đã được xác định.

### Bài 2 — Làm rõ phương thức nhiều tầng if

~~~java
String classify(int score, boolean submitted) {
    if (submitted) {
        if (score >= 0) {
            if (score <= 100) {
                return score >= 50 ? "PASS" : "FAIL";
            }
        }
    }
    return "INVALID";
}
~~~

**Yêu cầu:** Viết lại để trường hợp không hợp lệ được xử lý sớm, nhưng giữ nguyên kết quả.

Một lời giải:

~~~java
String classify(int score, boolean submitted) {
    if (!submitted || score < 0 || score > 100) {
        return "INVALID";
    }
    return score >= 50 ? "PASS" : "FAIL";
}
~~~

Hãy kiểm tra các trường hợp: chưa nộp, điểm -1, 0, 49, 50, 100 và 101. Bản mới ngắn hơn vì ba điều kiện từ chối được gộp thành một nhóm có ý nghĩa rõ ràng.

### Bài 3 — Tác dụng phụ trong điều kiện

~~~java
if (isValid(order) && paymentService.charge(order)) {
    confirm(order);
}
~~~

**Câu hỏi:** Điều gì có thể xảy ra nếu **charge** đã thu tiền nhưng **confirm** thất bại? Liệu chỉ đổi tên điều kiện có xử lý được rủi ro không?

**Gợi ý:** Vấn đề nằm ở tác dụng phụ và ranh giới giao dịch, cần xác định cơ chế ghi nhận, chống lặp, khôi phục hoặc đối soát phù hợp. Một phép kiểm tra boolean dễ đọc không tự đảm bảo tính nguyên tử của toàn quy trình.

---

**Ghi nhớ:** Một điều kiện dễ đọc phải diễn đạt được **ý định nghiệp vụ**, còn các nhánh xử lý phải cho thấy rõ **điều kiện cho phép, điều kiện từ chối và đường đi tiếp theo**. Hãy dùng tên có nghĩa, dấu ngoặc minh bạch, guard clause khi phù hợp và kiểm thử để bảo vệ hành vi. Mã dễ hiểu giúp người bảo trì phát hiện thiếu sót và thay đổi an toàn hơn.
