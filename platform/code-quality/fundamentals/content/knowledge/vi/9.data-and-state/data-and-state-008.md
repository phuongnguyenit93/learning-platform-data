# Giới hạn phạm vi và vòng đời của trạng thái

Trong chương **Dữ liệu và trạng thái** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta xem xét một quyết định thiết kế có ảnh hưởng lớn đến chất lượng mã nguồn: **một trạng thái nên được nhìn thấy ở đâu, được ai sở hữu và tồn tại trong bao lâu?**

Module này hướng đến việc hiểu những thuộc tính giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Trạng thái đặt sai phạm vi có thể khiến kết quả của một thao tác phụ thuộc vào yêu cầu trước đó, dữ liệu bị rò rỉ giữa người dùng, bài kiểm thử không ổn định hoặc nhiều luồng ghi đè nhau. Ngược lại, cố loại bỏ mọi trạng thái có thể tạo ra tính toán lặp lại, mất thông tin cần thiết và khiến vòng đời nghiệp vụ khó thể hiện.

Nguyên tắc xuất phát hữu ích là:

> **Chỉ giữ trạng thái trong phạm vi nhỏ nhất và trong khoảng thời gian ngắn nhất vẫn đáp ứng đúng yêu cầu; nêu rõ ai sở hữu việc đọc, thay đổi và kết thúc trạng thái đó.**

Đây là nguyên tắc để cân nhắc theo bối cảnh, không phải yêu cầu mọi biến đều phải là biến cục bộ.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **dữ liệu**, **trạng thái thay đổi được**, **phạm vi truy cập**, **vòng đời** và **quyền sở hữu**.
2. Chọn vị trí thích hợp cho dữ liệu tạm, trạng thái của một yêu cầu, một phiên, một đối tượng, ứng dụng hoặc trạng thái cần lưu bền.
3. Giải thích vì sao giữ thông tin của request trong field của service dùng chung gây rủi ro khi xử lý đồng thời.
4. Viết mã Java truyền đầu vào tường minh, giới hạn biến cục bộ và tránh các phụ thuộc vào trạng thái ngầm không cần thiết.
5. Xác định khi nào trạng thái dùng chung thực sự cần thiết và cách bảo vệ bất biến của nó.
6. Quản lý vòng đời tài nguyên, cache, dữ liệu bất đồng bộ và các giá trị gắn với luồng thực thi.
7. Thiết kế kiểm thử nhằm phát hiện trạng thái rò rỉ, tồn tại quá lâu, kết thúc quá sớm hoặc cập nhật không an toàn.

## 2. Trước tiên: trạng thái, phạm vi và vòng đời không phải một khái niệm

**Dữ liệu** là những giá trị chương trình xử lý: đơn hàng, ngày hết hạn, tổng tiền, mã khách hàng. **Trạng thái** thường chỉ những dữ liệu đang thể hiện tình hình hiện tại của một đối tượng hoặc hệ thống, và có thể thay đổi qua thời gian: số lượng còn trong kho, tiến độ đơn hàng, khách đang đăng nhập, tổng số tiền đã giữ chỗ.

Một giá trị không thay đổi cũng có thể mô tả một *ảnh chụp trạng thái* tại một thời điểm. Điều ta cần phân tích là **giá trị đó được tạo, truy cập, chia sẻ, thay đổi và hủy bỏ như thế nào**.

### 2.1. Ba câu hỏi cần tách biệt

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Phạm vi (scope)** | Phần mã nào có thể truy cập tên biến hoặc tham chiếu này? | Biến `subtotal` được khai báo bên trong một phương thức. |
| **Vòng đời (lifetime)** | Giá trị hoặc đối tượng cần tồn tại đến khi nào? | Giỏ hàng có thể cần tồn tại qua nhiều HTTP request trong cùng phiên mua sắm. |
| **Quyền sở hữu (ownership)** | Thành phần nào chịu trách nhiệm tạo, thay đổi, chia sẻ và kết thúc trạng thái? | Repository chịu trách nhiệm lưu đơn hàng; service nghiệp vụ điều phối thay đổi trạng thái đơn. |

Trong Java, **phạm vi từ vựng** của một biến cục bộ kết thúc khi rời khối khai báo, nhưng **đối tượng được biến đó tham chiếu có thể tiếp tục tồn tại** nếu tham chiếu đã được trả về hoặc lưu ở nơi khác.

~~~java
import java.util.ArrayList;
import java.util.List;

static List<String> createSkuList() {
    List<String> result = new ArrayList<>(); // tên biến chỉ dùng trong hàm
    result.add("SKU-100");
    return result; // đối tượng List tiếp tục được bên gọi giữ tham chiếu
}
~~~

Không nên đồng nhất “biến cục bộ” với “đối tượng chắc chắn bị hủy ngay sau khi hàm kết thúc”. Bộ thu gom rác Java quyết định thu hồi bộ nhớ khi đối tượng không còn có thể truy cập, và thời điểm thu hồi không được bảo đảm ngay lập tức.

### 2.2. Trạng thái không luôn là thứ cần xóa bỏ

Một biến đếm vòng lặp, một giao dịch đang thực hiện hay một trạng thái đơn hàng đang chờ thanh toán đều có mục đích chính đáng. Vấn đề nảy sinh khi phạm vi và vòng đời **lớn hơn nhu cầu**, hoặc **không rõ ai có quyền thay đổi**.

Ví dụ: tổng tiền đơn hàng có thể là dữ liệu cục bộ chỉ cần cho một phép tính. Nhưng trạng thái “đã thanh toán” phải được lưu bền để những request và tiến trình sau biết đơn hàng hiện ở bước nào.

## 3. Chọn phạm vi phù hợp với thời gian sống của dữ liệu

Bảng dưới đây là khung tham khảo khi thiết kế Java, không phải sơ đồ bắt buộc cho mọi ứng dụng.

| Loại thông tin | Phạm vi và vòng đời thường phù hợp | Rủi ro nếu giữ quá lâu hoặc chia sẻ sai |
| --- | --- | --- |
| Biến trung gian của phép tính | Một biểu thức, khối hoặc lần gọi phương thức. | Giá trị cũ ảnh hưởng lần tính tiếp theo; khó tái hiện lỗi. |
| Dữ liệu của một HTTP request | Dữ liệu truyền qua tham số, request context có vòng đời kiểm soát. | Dữ liệu request A lẫn sang request B. |
| Giỏ hàng đang sử dụng | Phiên người dùng hoặc dữ liệu lưu bền gắn với định danh giỏ. | Rò rỉ người dùng, mất giỏ khi phiên kết thúc, tích tụ dữ liệu bỏ quên. |
| Cấu hình chỉ đọc | Trường `final` hoặc đối tượng cấu hình dùng chung, có chính sách cập nhật. | Nhiều phiên bản cấu hình mâu thuẫn; không biết khi nào thay đổi có hiệu lực. |
| Bộ đếm/quota dùng chung trong một tiến trình | Đối tượng có chủ sở hữu và cơ chế đồng bộ. | Lost update, race condition, đọc trạng thái thiếu nhất quán. |
| Trạng thái nghiệp vụ cần tồn tại sau restart | Database hoặc hệ lưu trữ bền theo hợp đồng. | Mất trạng thái khi ứng dụng khởi động lại hoặc mở rộng nhiều máy. |
| Kết nối, stream, file handle | Từ lúc mở đến lúc sử dụng xong, đóng đúng lúc. | Rò rỉ tài nguyên, giữ khóa hoặc kết nối lâu hơn cần thiết. |
| Dữ liệu cache | Khoảng thời gian và kích thước giới hạn theo chính sách. | Dữ liệu lỗi thời, tiêu tốn bộ nhớ, khó xác định nguồn sự thật. |

Càng nhiều nơi có quyền đọc và ghi một trạng thái, càng cần giải thích rõ **bất biến**, **điểm đồng bộ**, **thời điểm cập nhật** và **cách khôi phục** nếu thao tác thất bại.

## 4. Giữ trạng thái tạm trong phạm vi nhỏ: ví dụ tính giảm giá

Giả sử quy tắc là: khách hàng được giảm 10% tiền hàng khi dùng mã `SAVE10`; không có mã đúng thì không giảm. Tổng tiền không âm và được tính bằng đơn vị tiền nhỏ nhất.

### 4.1. Dùng field cho dữ liệu chỉ cần trong một lần gọi

~~~java
final class MutableCheckoutService {
    private String lastCouponCode;

    CheckoutResult checkout(CheckoutRequest request) {
        lastCouponCode = request.couponCode();

        long discount = "SAVE10".equals(lastCouponCode)
                ? request.subtotalCents() / 10
                : 0;

        return new CheckoutResult(
                discount, request.subtotalCents() - discount);
    }
}
~~~

Nếu `MutableCheckoutService` là một đối tượng dùng chung giữa các request, field `lastCouponCode` tạo trạng thái dùng chung **không có lý do nghiệp vụ**. Nó làm kết quả một request có khả năng phụ thuộc vào request khác khi hai lời gọi chạy đồng thời.

Ví dụ một lịch thực thi có thể xảy ra:

~~~text
Request A                    Request B
---------                    ---------
ghi lastCouponCode=SAVE10
                             ghi lastCouponCode=null
đọc lastCouponCode=null
→ A không nhận giảm giá
~~~

Trong thực tế còn có các vấn đề về thứ tự nhìn thấy giá trị giữa luồng vì field này không được đồng bộ. Dù ứng dụng hiện chỉ chạy một luồng, trạng thái thừa vẫn gây khó khăn khi thay đổi kiến trúc hoặc kiểm thử.

Không cần thêm `synchronized` chỉ để bảo vệ một field vốn **không cần tồn tại**.

### 4.2. Truyền dữ liệu tường minh và tính bằng biến cục bộ

Ví dụ Java 17+ với `record`:

~~~java
import java.util.Objects;

record CheckoutRequest(long subtotalCents, String couponCode) {
    CheckoutRequest {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Subtotal must be non-negative");
        }
    }
}

record CheckoutResult(long discountCents, long payableCents) {}

final class CheckoutService {
    CheckoutResult checkout(CheckoutRequest request) {
        Objects.requireNonNull(request, "request");

        long subtotal = request.subtotalCents();
        long discount = "SAVE10".equals(request.couponCode())
                ? subtotal / 10
                : 0;

        return new CheckoutResult(discount, subtotal - discount);
    }
}
~~~

Với cùng đầu vào, phép tính cho cùng kết quả; không có field nào nhớ request trước. `couponCode` có thể là `null`: phép gọi `"SAVE10".equals(null)` trả về `false`. Tiền không âm được kiểm tra ngay khi tạo `CheckoutRequest`; ở đây giả định đối tượng request chỉ được khởi tạo qua constructor đã kiểm tra.

Các giá trị `subtotal` và `discount` chỉ có ý nghĩa trong một lần tính, nên biến cục bộ là lựa chọn hợp lý. Không phải mọi phương thức đều phải “thuần túy”, nhưng logic tính toán độc lập với trạng thái ngầm thường **dễ kiểm thử và dễ thay đổi hơn**.

### 4.3. Kiểm thử cách hai request tách biệt

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class CheckoutServiceTest {
    @Test
    void oneRequestDoesNotAffectTheNext() {
        CheckoutService service = new CheckoutService();

        CheckoutResult withCoupon = service.checkout(
                new CheckoutRequest(100_000, "SAVE10"));

        CheckoutResult withoutCoupon = service.checkout(
                new CheckoutRequest(100_000, null));

        assertEquals(10_000, withCoupon.discountCents());
        assertEquals(90_000, withCoupon.payableCents());
        assertEquals(0, withoutCoupon.discountCents());
        assertEquals(100_000, withoutCoupon.payableCents());
    }

    @Test
    void rejectsNegativeSubtotalAtConstruction() {
        assertThrows(IllegalArgumentException.class,
                () -> new CheckoutRequest(-1, "SAVE10"));
    }
}
~~~

Test minh họa rằng service đã sửa **không giữ thông tin từ lần gọi trước**. Tuy nhiên, test tuần tự này không đủ để chứng minh một implementation có field dùng chung sẽ an toàn khi chạy nhiều luồng. Những rủi ro đồng thời cần được xem xét thêm bằng lập luận và kiểm thử phù hợp.

## 5. Phân biệt biến cục bộ, field của đối tượng và trạng thái dùng chung

Trong Java, ba cách giữ dữ liệu dưới đây mang ý nghĩa khác nhau.

### 5.1. Biến cục bộ và tham số

~~~java
static long finalPrice(long subtotal, long shippingFee) {
    long total = Math.addExact(subtotal, shippingFee);
    return total;
}
~~~

`subtotal`, `shippingFee` và `total` thuộc một lần gọi. Nếu phương thức chỉ dùng các biến cục bộ và không đụng tới trạng thái dùng chung, những lần gọi khác nhau không ghi đè trực tiếp lên cùng các biến này.

Nhưng **tham chiếu cục bộ vẫn có thể trỏ tới đối tượng mutable được chia sẻ**. Ví dụ, một phương thức nhận `List` rồi gọi `list.add(...)` vẫn thay đổi dữ liệu bên ngoài dù không có field.

### 5.2. Field của đối tượng

~~~java
final class OrderDraft {
    private long subtotalCents;

    void addItem(long priceCents) {
        if (priceCents < 0) {
            throw new IllegalArgumentException("Negative price");
        }
        subtotalCents = Math.addExact(subtotalCents, priceCents);
    }

    long subtotalCents() {
        return subtotalCents;
    }
}
~~~

Ở đây field `subtotalCents` là **trạng thái có mục đích**: một bản nháp đơn hàng phải nhớ giá trị giữa các lần gọi `addItem`. Nếu đối tượng chỉ được dùng bởi một luồng và không chia sẻ ra ngoài, thiết kế này có thể phù hợp.

Nếu cùng một `OrderDraft` được chia sẻ và thay đổi từ nhiều luồng, mã chưa bảo đảm an toàn đồng thời. Việc có field không tự động sai; cần xác định **ai có thể giữ tham chiếu và gọi phương thức khi nào**.

### 5.3. Field static

~~~java
final class PricingDefaults {
    static final long STANDARD_SHIPPING_CENTS = 30_000;
}
~~~

Một hằng số `static final` kiểu nguyên thủy là thông tin dùng chung **bất biến** trong ví dụ này, có thể hợp lý khi nhiều nơi cần đọc cùng giá trị chính sách.

Ngược lại:

~~~java
final class RequestState {
    static String currentCustomerId; // Không gắn với một request cụ thể
}
~~~

Một field `static` mutable như `currentCustomerId` làm nhiều lời gọi trong cùng một vùng class loader có thể tranh nhau đọc và ghi thông tin của các khách hàng khác nhau. Nó còn khiến test dễ ảnh hưởng nhau nếu không dọn trạng thái.

**Không nên hiểu rằng `static final` luôn tạo đối tượng bất biến.** Với `static final List<String>`, chỉ có tham chiếu không thể gán lại; các phần tử trong danh sách vẫn có thể bị thêm hoặc xóa nếu đối tượng là danh sách mutable.

### 5.4. Bảng quyết định nhanh

| Dữ liệu | Vị trí thường ưu tiên | Lý do |
| --- | --- | --- |
| Kết quả trung gian của một lần tính | Biến cục bộ | Không cần chia sẻ và có vòng đời ngắn. |
| Ngày hiện tại dùng tính quy tắc | Tham số hoặc đối tượng clock được truyền vào | Dễ kiểm thử và tránh phụ thuộc thời gian ngầm. |
| Trạng thái của một bản nháp cụ thể | Field thuộc đối tượng bản nháp | Trạng thái đi cùng đúng đối tượng chịu trách nhiệm. |
| Giá trị cấu hình ổn định, chỉ đọc | Đối tượng cấu hình bất biến được chia sẻ | Tránh tạo lại không cần thiết và thống nhất cách dùng. |
| Trạng thái của mỗi request | Tham số/đối tượng request riêng | Không trộn request này với request khác. |
| Bộ đếm dùng chung cần cập nhật | Thành phần có chủ sở hữu và cơ chế đồng bộ | Bảo vệ bất biến khi nhiều bên thay đổi. |

## 6. Khi trạng thái chia sẻ là cần thiết: bảo vệ bất biến

Có những trường hợp trạng thái phải tồn tại qua nhiều thao tác, ví dụ giới hạn số chỗ được đặt trước trong một tiến trình. Khi đó, mục tiêu không phải xóa field, mà là **giới hạn người có thể sửa và bảo đảm thao tác cập nhật nhất quán**.

Giả sử ta quản lý một hạn mức trong bộ nhớ của **một đối tượng**, với các điều kiện:

- `limit` không âm và được thiết lập khi tạo.
- Mỗi lượt giữ chỗ có số lượng dương.
- Tổng `reserved` luôn nằm trong khoảng từ 0 đến `limit`.
- Một lượt chỉ được chấp nhận nếu sau khi cộng không vượt giới hạn.

### 6.1. Lỗi đọc rồi ghi trong hai bước không nguyên tử

~~~java
final class UnsafeQuota {
    private long reserved;
    private final long limit;

    UnsafeQuota(long limit) {
        this.limit = limit;
    }

    boolean tryReserve(long quantity) {
        if (reserved + quantity > limit) {
            return false;
        }
        reserved += quantity;
        return true;
    }
}
~~~

Ngoài việc thiếu kiểm tra đầu vào và nguy cơ tràn số, phương thức trên có một lỗi đồng thời: hai luồng cùng đọc `reserved` trước khi ghi, rồi đều trả về thành công. Ví dụ `limit = 10`, `reserved = 0`; mỗi luồng muốn đặt 7. Cả hai có thể thấy đủ chỗ.

Nếu một luồng ghi đè kết quả của luồng kia, tổng trên field có thể hiển thị 7 nhưng **hai lời đặt chỗ đều được chấp nhận**; hệ thống đã hứa cấp 14 chỗ trong khi chỉ có 10.

### 6.2. Đóng gói thao tác cập nhật và đồng bộ đúng phạm vi

~~~java
final class ReservationQuota {
    private final long limit;
    private long reserved;

    ReservationQuota(long limit) {
        if (limit < 0) {
            throw new IllegalArgumentException("Negative limit");
        }
        this.limit = limit;
    }

    public synchronized boolean tryReserve(long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        // Bất biến: 0 <= reserved <= limit.
        // Phép trừ chỉ được thực hiện với hai giá trị không âm,
        // và reserved không lớn hơn limit.
        if (quantity > limit - reserved) {
            return false;
        }

        reserved += quantity;
        return true;
    }

    public synchronized long reserved() {
        return reserved;
    }
}
~~~

`synchronized` bảo vệ cả thao tác **kiểm tra và cập nhật** trên cùng một đối tượng; không chỉ bảo vệ từng phép đọc hoặc ghi riêng lẻ. Với các tiền điều kiện và bất biến đã nêu, `limit - reserved` không âm và không tràn `long`; phép cộng sau khi kiểm tra cũng không vượt `limit`.

Sử dụng:

~~~java
var quota = new ReservationQuota(10);
boolean first = quota.tryReserve(7);   // true
boolean second = quota.tryReserve(7);  // false
long used = quota.reserved();          // 7
~~~

**Giới hạn của ví dụ:** đây chỉ là quota trong bộ nhớ của một instance Java. Nó không xử lý việc khởi động lại tiến trình, nhiều instance ứng dụng, cập nhật database hay hoàn tác reservation. Trong hệ thống có nhiều máy hoặc dữ liệu phải tồn tại lâu dài, cần cơ chế nhất quán ở **nơi trạng thái thực sự được lưu**, chẳng hạn giao dịch hoặc cập nhật có điều kiện nguyên tử trong database phù hợp.

### 6.3. Vì sao chỉ dùng AtomicLong không đủ trong mọi trường hợp?

Thay `reserved` bằng `AtomicLong` có thể làm phép cộng đơn lẻ nguyên tử, nhưng đoạn “**đọc trạng thái → kiểm tra ngưỡng → cộng**” vẫn là một thao tác ghép. Nếu tách thành hai lời gọi `get()` rồi `addAndGet()` mà không có cơ chế phối hợp, hai luồng vẫn có thể cùng vượt qua bước kiểm tra.

Có thể dùng vòng lặp compare-and-set với các điều kiện phù hợp, hoặc `synchronized` như trên. Lựa chọn phụ thuộc yêu cầu về hiệu năng, contention, phạm vi chia sẻ và khả năng bảo trì. **Cần bảo vệ bất biến toàn bộ, không chỉ từng phép gán.**

## 7. Bất biến của dữ liệu: giảm nhu cầu đồng bộ khi có thể

Không phải mọi dữ liệu phải được sửa tại chỗ. Khi người dùng cần một kết quả từ một thời điểm cụ thể, **ảnh chụp bất biến** thường dễ hiểu hơn chia sẻ một collection mutable.

### 7.1. Không trả trực tiếp collection nội bộ có thể sửa

~~~java
final class Cart {
    private final java.util.List<String> skuIds =
            new java.util.ArrayList<>();

    java.util.List<String> skuIds() {
        return skuIds; // Bên gọi có thể thêm/xóa mà Cart không kiểm soát
    }
}
~~~

Khi trả về chính danh sách mutable nội bộ, bên gọi có thể thay đổi trạng thái mà không đi qua quy tắc của `Cart`. Lúc đó rất khó biết **ai là chủ sở hữu thay đổi**.

### 7.2. Tạo snapshot có hợp đồng rõ

~~~java
import java.util.List;
import java.util.Objects;

record CartSnapshot(List<String> skuIds) {
    CartSnapshot {
        skuIds = List.copyOf(Objects.requireNonNull(skuIds, "skuIds"));
    }
}
~~~

~~~java
var original = new java.util.ArrayList<String>();
original.add("SKU-100");

var snapshot = new CartSnapshot(original);
original.add("SKU-200");

// snapshot.skuIds() chỉ có "SKU-100".
// snapshot.skuIds().add("SKU-300") ném UnsupportedOperationException.
~~~

`List.copyOf` tạo danh sách không thể sửa qua API của danh sách và không phụ thuộc vào việc sửa danh sách `original` sau đó. Trong ví dụ, các phần tử `String` cũng bất biến.

**Phạm vi bảo đảm:** nếu danh sách chứa các đối tượng **mutable**, `List.copyOf` không tự sao chép sâu từng đối tượng. Bản ghi `record` cũng không tự bảo đảm toàn bộ đồ thị đối tượng bất biến. Khi yêu cầu snapshot hoàn toàn độc lập, cần quyết định cách sao chép/đóng gói cả phần tử.

### 7.3. Phân biệt final và immutable

`final` với biến tham chiếu chỉ ngăn việc gán lại biến đó, không ngăn sửa đối tượng đang trỏ tới:

~~~java
final java.util.List<String> items = new java.util.ArrayList<>();
items.add("SKU-100"); // Hợp lệ: tham chiếu final, List vẫn mutable.
~~~

Bất biến hữu ích khi chia sẻ dữ liệu, nhưng cũng có chi phí tạo bản sao và giữ nhiều phiên bản trong bộ nhớ. Với dữ liệu lớn và thay đổi thường xuyên, cần cân nhắc mô hình ownership, cấu trúc dữ liệu hoặc cơ chế đồng bộ thích hợp.

## 8. Vòng đời của tài nguyên: ngắn và có điểm kết thúc rõ

Một stream, kết nối database, khóa hoặc file handle không giống đối tượng dữ liệu thông thường. Việc không còn sử dụng biến tham chiếu **không đồng nghĩa tài nguyên ngoài JVM được giải phóng ngay**.

### 8.1. Đọc file và đóng tài nguyên đúng lúc

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static String firstLine(Path file) throws IOException {
    try (var reader =
                 Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
        return reader.readLine();
    }
}
~~~

Khối `try-with-resources` bảo đảm gọi `close()` khi ra khỏi khối, bao gồm khi `return` hoặc khi có ngoại lệ phát sinh. Điều đó giúp vòng đời tài nguyên phù hợp với phạm vi sử dụng. Trong thực tế, việc đóng vẫn có thể phát sinh ngoại lệ; Java có cơ chế xử lý ngoại lệ bị che (*suppressed exceptions*) khi cần chẩn đoán.

### 8.2. Đừng lưu tài nguyên ngắn hạn vào field sống quá lâu

Nếu một service dùng chung mở kết nối trong constructor rồi giữ mãi mà không quản lý vòng đời, có thể gặp kết nối hết hạn, hết số lượng kết nối khả dụng hoặc khó khôi phục sau sự cố. Với ứng dụng sử dụng connection pool, đối tượng `Connection` lấy ra thường phải được đóng/trả về pool theo hợp đồng ngay sau khi dùng xong.

**Đừng dựa vào garbage collector để đóng kết nối, stream hay tài nguyên nghiệp vụ**. Tài nguyên cần có điểm hoàn tất rõ ràng, tương ứng với transaction, lần đọc hoặc công việc cụ thể.

### 8.3. Vòng đời quá ngắn cũng gây lỗi

Nếu đóng stream ngay khi trả về một đối tượng còn cần đọc dữ liệu từ stream, người dùng của đối tượng có thể nhận lỗi vì tài nguyên đã đóng. Tương tự, kết thúc transaction trước khi toàn bộ cập nhật cần tính nguyên tử hoàn tất có thể làm sai hành vi.

Do đó, “càng ngắn càng tốt” phải được hiểu là **ngắn nhất nhưng vẫn đủ cho hành vi được cam kết**.

## 9. Cache: trạng thái tồn tại lâu hơn phép tính để đổi lấy hiệu năng

Cache lưu kết quả trước đó nhằm giảm truy vấn hoặc tính toán lặp lại. Khác với biến cục bộ, cache được cố tình giữ qua nhiều lời gọi và có thể chia sẻ.

Một cache đúng đắn cần trả lời ít nhất năm câu hỏi:

1. **Nguồn sự thật là gì?** Khi cache khác dữ liệu gốc, ưu tiên nguồn nào?
2. **Khóa cache là gì?** Có đủ phân biệt người dùng, loại tiền, vùng địa lý, phiên bản chính sách hoặc các yếu tố ảnh hưởng kết quả không?
3. **Khi nào hết hiệu lực?** Dữ liệu thay đổi theo TTL, sự kiện cập nhật hay chủ động xóa?
4. **Giới hạn kích thước ở đâu?** Có tối đa số phần tử, dung lượng hoặc phương thức giải phóng không?
5. **Ai được quyền cập nhật?** Có cách bảo vệ truy cập đồng thời và ngăn ghi đè dữ liệu mới bằng dữ liệu cũ không?

Ví dụ, cache phí giao hàng chỉ theo `productId` sẽ sai nếu phí còn phụ thuộc tỉnh thành và phiên bản chính sách. Cùng một mã hàng nhưng hai người dùng ở hai khu vực có thể cần hai kết quả khác nhau.

### 9.1. TTL không tự giải quyết mọi vấn đề

TTL (*time to live*) quy định sau bao lâu một mục cache bị coi là hết hạn. TTL giảm khoảng thời gian dữ liệu có thể cũ, nhưng trong khoảng thời gian còn hiệu lực vẫn có thể trả kết quả lỗi thời. Các giá trị thực tế phải dựa vào yêu cầu nhất quán của nghiệp vụ.

Đối với tồn kho hoặc hạn mức thanh toán, nhiều quyết định cần kiểm tra lại **tại nguồn có khả năng cập nhật nguyên tử**, thay vì chỉ dựa vào cache có thể lỗi thời.

### 9.2. Cache chia sẻ cần ranh giới người dùng

Nếu dữ liệu chứa thông tin của từng tài khoản, khóa cache và chính sách truy cập phải bảo đảm không lấy nhầm dữ liệu của người khác. Cache biến `static Map<String, Object>` không giới hạn kích thước và không có quy tắc hết hạn có thể vừa làm rò rỉ thông tin vừa giữ bộ nhớ quá lâu.

Bộ nhớ cache không tự mang tính bền vững: khi tiến trình khởi động lại, dữ liệu có thể mất. Chỉ dùng cache để lưu trạng thái bắt buộc không mất sẽ gây lỗi.

## 10. Request, session và trạng thái lưu bền

Ba vòng đời này thường bị nhầm lẫn trong ứng dụng web.

### 10.1. Dữ liệu một request

Dữ liệu như filter tìm kiếm, mã phiếu giảm giá vừa gửi hoặc tham số truy vấn thường chỉ cần tồn tại trong một request. Cách đơn giản là truyền qua DTO, tham số hoặc đối tượng ngữ cảnh có vòng đời được quản lý.

Một service sử dụng chung trong nhiều request **không nên cất `currentUserId` vào field mutable**, vì các request có thể đồng thời hoặc chạy xen kẽ.

### 10.2. Dữ liệu một phiên

Giỏ hàng đang thao tác hoặc lựa chọn tạm thời có thể cần qua nhiều request. Cần xác định **phiên kết thúc khi nào**, cách hết hạn, giới hạn lưu trữ và cách xử lý khi phiên không còn hợp lệ.

Đặc biệt, không nên mặc định “session = một luồng Java”: server thường dùng thread pool và mỗi request của cùng người dùng có thể được phục vụ bởi các luồng khác nhau.

### 10.3. Dữ liệu cần tồn tại lâu dài

Trạng thái đơn hàng, giao dịch tài chính và lịch sử thanh toán thường cần được lưu vào hệ thống bền vững. Với loại dữ liệu này, vòng đời dài hơn vòng đời của một đối tượng Java hoặc một server process.

Một quyết định cập nhật quan trọng thường phải có **ranh giới giao dịch** và quy tắc khi xung đột. Một field `synchronized` trong JVM không thay thế được giao dịch database khi ứng dụng chạy nhiều instance hoặc được khởi động lại.

## 11. Luồng thực thi và công việc bất đồng bộ: đừng để trạng thái ẩn đi lạc

### 11.1. ThreadLocal chỉ gắn với luồng, không tự gắn với request

`ThreadLocal<T>` cho mỗi thread có một giá trị riêng, nhưng nó không tự biết vòng đời request. Trong server dùng thread pool, một luồng có thể được dùng lại cho nhiều request.

Nếu sử dụng để truyền metadata ngắn hạn, phải quản lý dọn dẹp rõ ràng:

~~~java
final class TraceContext {
    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    static void withTrace(String traceId, Runnable action) {
        TRACE_ID.set(traceId);
        try {
            action.run();
        } finally {
            TRACE_ID.remove();
        }
    }

    static String currentTraceId() {
        return TRACE_ID.get();
    }
}
~~~

`remove()` trong `finally` ngăn giá trị của công việc cũ còn nằm lại trên thread được tái sử dụng. Ví dụ này minh họa cách quản lý vòng đời, không phải khuyến nghị dùng `ThreadLocal` cho mọi dữ liệu nghiệp vụ.

**Lưu ý:** `ThreadLocal` thông thường **không tự truyền giá trị** sang các luồng khác được dùng bởi `CompletableFuture` hoặc executor. Nếu công việc cần metadata, ưu tiên truyền dữ liệu rõ qua tham số, hoặc dùng cơ chế truyền ngữ cảnh của framework có quy tắc rõ ràng.

### 11.2. Công việc bất đồng bộ có thể sống lâu hơn request

~~~java
// Ý tưởng: tạo một bản dữ liệu bất biến dành riêng cho công việc nền.
record EmailJob(String recipient, String orderId) {}

static java.util.concurrent.CompletableFuture<Void> sendLater(
        EmailJob job,
        java.util.concurrent.Executor executor) {
    return java.util.concurrent.CompletableFuture.runAsync(
            () -> sendEmail(job), executor);
}
~~~

Trong ví dụ, `sendEmail(job)` là phương thức giả định. Điều cần chú ý là công việc nền nên nhận **những dữ liệu nó thực sự cần**, với quyền sở hữu và thời hạn phù hợp. Không nên giữ trực tiếp một request object chứa tài nguyên hoặc thông tin chỉ còn hợp lệ trong luồng HTTP.

Cần quyết định ai theo dõi việc hoàn tất, timeout, hủy, retry và xử lý khi tiến trình chết trước lúc công việc xong. Một `CompletableFuture` trong bộ nhớ không tự bảo đảm tác vụ sẽ được thực hiện sau khi ứng dụng khởi động lại; công việc quan trọng có thể cần hàng đợi bền hoặc cơ chế lưu trữ khác.

## 12. Thời điểm chuyển trạng thái và bất biến nghiệp vụ

Phạm vi và vòng đời trở nên quan trọng đặc biệt khi hệ thống quản lý **các trạng thái có ý nghĩa nghiệp vụ**.

Giả sử đơn hàng có các trạng thái `CREATED`, `PAID` và `CANCELLED`. Đặc tả có thể chỉ cho phép:

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> PAID: thanh toán thành công
    CREATED --> CANCELLED: hủy hợp lệ
    PAID --> [*]
    CANCELLED --> [*]
~~~

Nếu nghiệp vụ cho phép hoàn tiền sau khi thanh toán, cần thêm trạng thái và chuyển tiếp tương ứng; sơ đồ trên chỉ minh họa một đặc tả đơn giản, không phải mô hình đủ cho mọi hệ thống bán hàng.

Khi thực thi, cần phân biệt:

- **Trạng thái cục bộ:** kết quả kiểm tra “đủ điều kiện thanh toán?” trong một lần gọi.
- **Trạng thái bền:** đơn hàng hiện đang ở `PAID` hay `CANCELLED`.
- **Sự kiện:** “thanh toán thành công” là thông tin về một chuyển tiếp đã xảy ra.
- **Bất biến:** một đơn đã `CANCELLED` không được vô tình chuyển sang `PAID` nếu đặc tả không cho phép.

Nếu nhiều request cùng thay đổi một đơn hàng, kiểm tra trạng thái rồi cập nhật phải có cơ chế đồng bộ ở **nơi lưu trạng thái cuối cùng**. Mỗi request tạo object cục bộ đúng không đủ để bảo vệ bất biến khi cả hai cùng đọc một phiên bản dữ liệu cũ.

## 13. Các lỗi phổ biến khi phạm vi và vòng đời không khớp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra và cải thiện |
| --- | --- | --- |
| Người dùng B nhận kết quả có dữ liệu người dùng A. | Service dùng chung giữ dữ liệu request trong field hoặc cache dùng sai khóa. | Truy dấu nơi giữ trạng thái, chuyển dữ liệu request thành tham số, kiểm tra khóa cache và quyền truy cập. |
| Test đỗ khi chạy riêng nhưng trượt khi chạy cùng bộ. | Biến `static` mutable, singleton test fixture hoặc cache không được reset. | Cô lập dữ liệu, làm rõ vòng đời fixture, hạn chế trạng thái chia sẻ. |
| Hai thao tác cùng báo thành công nhưng vượt hạn mức. | Kiểm tra rồi cập nhật không nguyên tử. | Xác định bất biến, đồng bộ ở đúng phạm vi hoặc dùng giao dịch/cập nhật nguyên tử. |
| Cấu hình đã thay đổi nhưng ứng dụng vẫn dùng giá trị cũ. | Cache thiếu vô hiệu hóa hoặc snapshot sống quá lâu. | Xác định thời điểm hiệu lực, phiên bản và cơ chế refresh. |
| Bộ nhớ tăng liên tục khi ứng dụng chạy lâu. | Collection dùng chung không giới hạn, listener/ThreadLocal không được dọn. | Kiểm tra tham chiếu còn giữ, áp dụng giới hạn và dọn theo vòng đời. |
| Đọc file hoặc truy vấn bị lỗi vì tài nguyên đã đóng. | Đóng resource trước khi người nhận xử lý xong. | Thiết kế lại quyền sở hữu tài nguyên, giữ phạm vi mở đủ cho thao tác. |
| Một tác vụ nền không có dữ liệu cần thiết. | Dữ liệu chỉ nằm trong thread hoặc request vừa kết thúc. | Truyền snapshot đầu vào và định nghĩa thời hạn công việc. |
| Dữ liệu mất sau khi restart. | Trạng thái quan trọng chỉ lưu trong instance hoặc cache. | Đưa trạng thái cần bền vào kho dữ liệu phù hợp. |

**Cùng một biểu hiện có thể có nhiều nguyên nhân.** Trước khi đổi cấu trúc mã, nên tái hiện đường đi dữ liệu và nơi phát sinh thay đổi thật sự.

## 14. Khi nào nên thu hẹp, khi nào nên giữ trạng thái lâu hơn?

Không nên hiểu nguyên tắc “vòng đời ngắn” như một tối ưu tuyệt đối.

| Lựa chọn | Lợi ích | Chi phí hoặc rủi ro |
| --- | --- | --- |
| Biến cục bộ / hàm ít tác dụng phụ | Dễ hiểu đầu vào–đầu ra, giảm ảnh hưởng giữa các lần gọi. | Có thể cần tính toán lại; không giữ được tiến độ qua nhiều thao tác. |
| Snapshot bất biến | Dễ chia sẻ và so sánh phiên bản dữ liệu. | Tốn bộ nhớ và công sức sao chép, có thể lỗi thời. |
| State của đối tượng riêng | Thể hiện rõ vòng đời của một thực thể hoặc tác vụ. | Cần kiểm soát ai giữ tham chiếu và ai được thay đổi. |
| State dùng chung trong tiến trình | Có thể cập nhật nhanh, tránh nhiều bản sao. | Đồng bộ, tranh chấp, phụ thuộc thứ tự, không bền khi restart. |
| Cache | Giảm tính toán hoặc truy cập dịch vụ ngoài. | Cần invalidation, giới hạn, bảo mật và quy tắc nhất quán. |
| Lưu bền | Dữ liệu sống qua restart, nhiều process cùng truy cập được. | Giao dịch, độ trễ, schema, xung đột và vận hành phức tạp hơn. |

Với cấu hình ít thay đổi, giữ object bất biến dùng chung giúp giảm cấp phát mà vẫn dễ suy luận. Với biến tạm của một phép tính đơn giản, tạo một field chỉ để “dùng lại bộ nhớ” thường không đem lại lợi ích có ý nghĩa so với chi phí bảo trì và đồng thời.

Mục tiêu là **đúng vòng đời và đúng quyền sở hữu**, không phải tối thiểu hóa số field bằng mọi giá.

## 15. Quy trình thiết kế và review trạng thái

Khi gặp một field mutable mới, một cache hoặc một biến toàn cục trong pull request, có thể đặt các câu hỏi theo trình tự:

**Bước 1 — Xác định ý nghĩa.** Giá trị biểu diễn điều gì? Nó là dữ liệu tạm, trạng thái nghiệp vụ hay tài nguyên? Bất biến nào phải được giữ?

**Bước 2 — Xác định vòng đời cần thiết.** Dữ liệu chỉ cần đến cuối phép tính, cuối request, cuối session, hết công việc nền hay sau khi ứng dụng khởi động lại?

**Bước 3 — Xác định chủ sở hữu.** Ai tạo? Ai đọc? Ai sửa? Ai có trách nhiệm dọn? Nếu nhiều bên sửa, có một nơi chịu trách nhiệm kiểm tra điều kiện cập nhật không?

**Bước 4 — Xác định phạm vi truy cập.** Có thể chuyển từ `static`/field sang tham số hoặc biến cục bộ không? Có nên trả snapshot hoặc giá trị kết quả thay vì cho bên gọi sửa collection nội bộ không?

**Bước 5 — Phân tích đồng thời và lỗi.** Có hai thao tác cùng chạm trạng thái không? Cần bảo đảm nguyên tử, rollback, idempotency, retry hoặc khả năng khôi phục khi gián đoạn không?

**Bước 6 — Chọn bằng chứng phù hợp.** Test cô lập request, kiểm tra bất biến, kiểm thử đồng thời và tích hợp với kho lưu trữ. Khi cần, theo dõi độ lớn cache và số tài nguyên còn mở.

**Bước 7 — Đánh giá chi phí thay đổi.** Quy tắc giữ trạng thái đã đủ rõ để người khác sửa không? Có thêm tầng trừu tượng hoặc cơ chế đồng bộ phức tạp chỉ để giải quyết một biến tạm không?

### 15.1. Ví dụ lập luận trong code review

> “`couponCode` thuộc từng request và chỉ được dùng khi tính giảm giá. Đưa nó vào field của `CheckoutService` khiến các request có thể ảnh hưởng nhau. Tôi truyền `CheckoutRequest` vào phương thức, tính `discount` cục bộ và trả kết quả. Test lần lượt hai request với mã khác nhau giúp bảo vệ tính độc lập; luồng tính toán không còn trạng thái ngầm cần đồng bộ.”

Lập luận đó thể hiện **đúng phạm vi của dữ liệu, nguyên nhân của lỗi tiềm ẩn và bằng chứng kiểm tra**. Nó hữu ích hơn lý do chung chung “không nên dùng field”.

## 16. Bài tập tình huống

Một hệ thống đặt vé triển khai ba instance ứng dụng. Mỗi instance có một biến `static int remainingSeats = 100`. Khi có yêu cầu mua vé, service đọc `remainingSeats`; nếu còn chỗ thì trừ đi và trả thành công. Ứng dụng đôi khi khởi động lại để triển khai phiên bản mới.

**Câu hỏi:**

1. Vấn đề nào xuất hiện nếu hai request đến cùng một instance đồng thời?
2. Vấn đề nào xuất hiện nếu hai request được xử lý ở hai instance khác nhau?
3. Điều gì xảy ra với `remainingSeats` sau khi một instance khởi động lại?
4. Nên đặt trạng thái tồn kho vé ở đâu và cần tính chất cập nhật nào?
5. Nên lưu dữ liệu nào trong biến cục bộ của một request?

**Gợi ý phân tích:**

- Trên cùng instance, hai luồng có thể cùng đọc một giá trị và cập nhật không nguyên tử. `static` không khiến phép “kiểm tra rồi trừ” trở nên an toàn.
- Các instance giữ các bản sao khác nhau, nên không có một tổng số ghế thống nhất. `synchronized` chỉ trong từng JVM không giải quyết được vấn đề giữa ba instance.
- Sau restart, field được khởi tạo lại, làm mất thông tin đã bán; dựa vào nó có thể dẫn đến bán vượt số ghế.
- Trạng thái tồn kho thực nên nằm ở nơi lưu bền và cung cấp cơ chế **cập nhật có điều kiện nguyên tử** hoặc giao dịch/khóa phù hợp. Cần thiết kế cách tránh xử lý trùng yêu cầu và cách khôi phục khi thanh toán thất bại.
- Mã vé đang đặt, số lượng yêu cầu và kết quả kiểm tra tạm của từng request có thể tồn tại cục bộ, nhưng quyết định ghi nhận bán vé phải được xác nhận tại nguồn dữ liệu có thẩm quyền.

## 17. Checklist áp dụng hằng ngày

- [ ] Tôi biết từng trạng thái tồn tại để phục vụ quy tắc nào và phải giữ bất biến gì.
- [ ] Phạm vi truy cập và vòng đời của trạng thái được xác định riêng, không suy diễn từ loại biến.
- [ ] Giá trị chỉ dùng trong một phép tính được giữ cục bộ hoặc truyền bằng tham số khi phù hợp.
- [ ] Dữ liệu request không nằm trong field mutable của service dùng chung.
- [ ] Những object chia sẻ có hợp đồng rõ về khả năng thay đổi và quyền sở hữu.
- [ ] Collection hoặc đối tượng trả ra ngoài không vô tình cho phép sửa trạng thái nội bộ.
- [ ] Khi cần chia sẻ trạng thái mutable, thao tác kiểm tra và cập nhật bảo vệ **toàn bộ bất biến**.
- [ ] Đã xét phạm vi một process, nhiều process và yêu cầu lưu bền qua restart.
- [ ] Cache có khóa đúng, chính sách hết hạn/vô hiệu hóa và giới hạn kích thước.
- [ ] ThreadLocal hoặc ngữ cảnh tạm được dọn đúng lúc, đặc biệt khi dùng thread pool.
- [ ] Công việc bất đồng bộ nhận dữ liệu đủ dùng và có chính sách hoàn tất, retry hoặc khôi phục.
- [ ] Stream, connection và tài nguyên ngoài JVM có điểm đóng rõ ràng.
- [ ] Test kiểm tra việc không rò rỉ trạng thái giữa lần gọi và các trường hợp đồng thời/ràng buộc dữ liệu có rủi ro.

## 18. Kết luận

**Giới hạn phạm vi** giúp giảm số nơi có thể tác động lên trạng thái. **Giới hạn vòng đời** giúp ngăn dữ liệu cũ, tài nguyên và thông tin người dùng bị giữ lại ngoài nhu cầu. **Quyền sở hữu rõ ràng** cho biết ai được thay đổi, ai bảo vệ bất biến và ai chịu trách nhiệm kết thúc trạng thái.

Trong **CODE_QUALITY_FUNDAMENTALS**, đây là các quyết định thiết kế quan trọng để mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ưu tiên biến cục bộ và dữ liệu truyền tường minh cho tính toán ngắn hạn; dùng trạng thái của đối tượng, cache hoặc lưu bền khi nghiệp vụ thực sự cần; và khi chia sẻ trạng thái mutable, hãy bảo vệ bất biến đúng ở ranh giới mà dữ liệu được sở hữu. Thiết kế tốt không loại bỏ trạng thái, mà khiến **vòng đời và trách nhiệm của nó có thể nhìn thấy, kiểm tra và bảo trì được**.

