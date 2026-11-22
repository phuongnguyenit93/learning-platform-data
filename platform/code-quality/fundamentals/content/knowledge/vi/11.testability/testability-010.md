# Nhận diện thiết kế khó kiểm thử từ một tình huống cụ thể

Một nhóm phát triển nhận yêu cầu: “Khi người mua xác nhận giỏ hàng, hệ thống phải lấy phí vận chuyển do dịch vụ giao hàng cung cấp, lưu đơn thành công và cho người mua xem mã đơn cùng tổng tiền. Nếu dịch vụ vận chuyển gặp lỗi, không được lưu đơn với phí vận chuyển chưa xác định”. Người viết chức năng thử bằng cách chạy ứng dụng, kết nối cơ sở dữ liệu thật, gọi dịch vụ giao hàng và kiểm tra bản ghi sau mỗi lần chạy. Ngay cả kiểm tra thời điểm tạo đơn cũng cho kết quả thay đổi giữa các lần chạy.

Nhìn từ bên ngoài, chức năng không quá phức tạp. Nhưng **việc xác nhận một quy tắc nhỏ lại phụ thuộc vào quá nhiều thành phần ngoài tầm kiểm soát của bài kiểm thử**. Đây là dấu hiệu thiết kế có khả năng kiểm thử (*testability*) thấp: việc đặt đầu vào, tạo điều kiện lỗi và quan sát kết quả đều tốn công hoặc thiếu tính ổn định.

Trong chương **Khả năng kiểm thử** của module `CODE_QUALITY_FUNDAMENTALS`, khả năng kiểm thử liên hệ trực tiếp với mục tiêu xây dựng mã **đáng tin cậy, dễ hiểu và dễ thay đổi**. Thiết kế dễ kiểm thử giúp một người xác nhận điều gì đang được bảo đảm, phát hiện sai lệch trước khi phát hành và sửa yêu cầu với phạm vi hồi quy có thể dự đoán.

Bài này đi từ **một tình huống Java cụ thể**, phân tích vì sao khó kiểm thử, thử cải thiện các ranh giới phụ thuộc và viết những bài kiểm thử có ý nghĩa. Mục tiêu là học cách chẩn đoán thiết kế qua bằng chứng, không phải thêm interface cho mọi lớp.

Sau bài học, bạn có thể:

- Nhìn vào một tình huống và chỉ ra chính xác **đầu vào khó điều khiển, kết quả khó quan sát và phụ thuộc gây bất ổn**.
- Phân biệt vấn đề thuộc thiết kế sản phẩm với vấn đề thuộc môi trường và cách viết test.
- Đánh giá việc dùng thời gian hệ thống, ID ngẫu nhiên, I/O, biến toàn cục và tác dụng phụ trong logic nghiệp vụ.
- Tách quyết định nghiệp vụ khỏi tương tác với hệ thống ngoài khi điều đó làm mã rõ ràng hơn.
- Viết unit test có kiểm soát bằng fake/stub, rồi xác định những gì vẫn cần integration test.
- Tránh cải thiện “testability” bằng cách phá vỡ hợp đồng hay làm thiết kế phức tạp quá mức.

## 1. Tình huống: tạo đơn hàng phụ thuộc dịch vụ bên ngoài

Giả sử luồng tạo đơn gồm những bước sau:

1. Nhận mã khách và giá trị tạm tính của giỏ.
2. Gọi dịch vụ vận chuyển để lấy phí.
3. Tạo mã đơn ngẫu nhiên và ghi nhận thời điểm tạo.
4. Lưu đơn vào cơ sở dữ liệu.
5. Trả kết quả gồm mã đơn và tổng tiền.

Các yêu cầu nghiệp vụ đã xác định:

- Giá trị đơn không âm và mã khách không rỗng.
- Phí vận chuyển nhận từ dịch vụ ngoài không được âm.
- Khi không lấy được phí vận chuyển, không lưu đơn với phí mặc định.
- Tổng tiền bằng tạm tính cộng phí vận chuyển.
- Nếu lưu đơn thất bại, không được trả kết quả thành công.

### Phiên bản đầu dễ viết nhưng khó kiểm thử

Đoạn mã sau là **mã minh họa**; các lớp `HttpShippingClient` và `JdbcOrderStore` được giả định là các adapter sẵn có trong ứng dụng:

```java
import java.time.Instant;
import java.util.UUID;

final class CheckoutService {
    Purchase checkout(String customerId, long subtotalVnd) {
        long feeVnd = new HttpShippingClient()
                .quoteFee(customerId, subtotalVnd);
        long totalVnd = subtotalVnd + feeVnd;

        String orderId = UUID.randomUUID().toString();
        Instant createdAt = Instant.now();

        Purchase order = new Purchase(
                orderId, customerId, subtotalVnd, feeVnd, totalVnd, createdAt
        );

        new JdbcOrderStore().save(order);
        return order;
    }
}
```

Mã có vẻ ngắn. Nhưng để kiểm tra “phí vận chuyển âm phải bị từ chối” hoặc “dịch vụ ngoài lỗi thì không lưu”, người viết test gặp nhiều khó khăn:

- Không thể truyền một phản hồi giả từ `HttpShippingClient` mà không thay code hoặc dùng công cụ can thiệp vào cách tạo đối tượng.
- Mỗi lần chạy cần cấu hình mạng, dịch vụ ngoài và có thể cả thông tin xác thực.
- `UUID.randomUUID()` và `Instant.now()` khiến kết quả chính xác thay đổi giữa các lần chạy.
- `new JdbcOrderStore()` buộc test chuẩn bị database hoặc can thiệp vào hạ tầng.
- Không có bước kiểm tra phí âm và đầu vào; test có thể phát hiện lỗi nghiệp vụ nhưng cách chèn dữ liệu bất thường khá tốn công.
- Để biết bản ghi đã lưu hay chưa, test phải truy vấn database thật.

Những điều này **không chứng minh bản thân HTTP, JDBC hoặc UUID là xấu**. Chúng cho thấy phần quyết định nghiệp vụ đang tự chọn và tạo các phụ thuộc, khiến một bài test phải chạy gần như cả hệ thống.

## 2. Nhận diện khó kiểm thử qua ba câu hỏi

Khi đọc một hàm hay một quy trình, hãy hỏi:

**A. Tôi có điều khiển được đầu vào và điều kiện của test không?**

Đầu vào không chỉ là tham số truyền trực tiếp. Nó còn có thời điểm hiện tại, số ngẫu nhiên, trạng thái database, phản hồi mạng, biến môi trường, file cấu hình, locale và trạng thái được giữ từ lần chạy trước. Nếu muốn kiểm tra một nhánh lỗi phải chờ dịch vụ thật bị lỗi, bài test đang khó điều khiển.

**B. Tôi có quan sát được kết quả quan trọng không?**

Kết quả có thể là giá trị trả về, exception, bản ghi lưu hoặc thông điệp gửi đi. Nếu test phải đọc log, ngủ vài giây rồi đoán kết quả, hoặc truy vấn hàng loạt bảng không liên quan, rất có thể ranh giới quan sát chưa rõ. Không nhất thiết công khai trạng thái nội bộ chỉ để test; nên quan sát qua hợp đồng mà hành vi thực sự tạo ra.

**C. Test có độc lập, chạy nhanh và lặp lại ổn định không?**

Nếu cùng dữ liệu cho kết quả khác nhau vì thời gian, trạng thái chia sẻ hoặc thứ tự chạy test, khả năng khoanh vùng lỗi giảm. Thử chạy một test riêng, chạy cùng cả bộ và chạy lại nhiều lần: khác biệt sẽ gợi ý phụ thuộc ẩn hoặc cách thiết lập môi trường chưa được kiểm soát.

| Câu hỏi | Ví dụ trong `CheckoutService` ban đầu | Bằng chứng có thể quan sát |
| --- | --- | --- |
| Điều khiển điều kiện | Không chọn được phản hồi HTTP, thời điểm và mã đơn | Khó tạo phản hồi âm, timeout hoặc ID cố định |
| Quan sát kết quả | Lưu dữ liệu thông qua repository được tạo trong hàm | Cần truy vấn DB để biết có gọi lưu hay chưa |
| Lặp lại độc lập | Dùng mạng, DB, đồng hồ và UUID thật | Test cần khởi động nhiều dịch vụ, có thể chập chờn |
| Xác định nguyên nhân lỗi | Quá nhiều bước diễn ra trong một lần kiểm thử | Khi thất bại không rõ do quy tắc, mạng hay database |

Một bài integration test có chủ đích vẫn có thể chạm mạng và database. Vấn đề là **mọi bài test**, kể cả kiểm tra một quy tắc đơn giản, đều phải trả chi phí đó.

## 3. Những dấu hiệu cụ thể trong mã nguồn

### 3.1. Tạo phụ thuộc ngay trong phương thức xử lý

```java
new HttpShippingClient().quoteFee(...);
new JdbcOrderStore().save(...);
```

Cách viết này làm nhiệm vụ của `CheckoutService` trộn với quyết định “dùng nhà cung cấp nào” và “khởi tạo adapter ra sao”. Muốn test riêng nghiệp vụ, phải sửa mã triển khai hoặc dùng cơ chế phức tạp để thay thế lời gọi.

Giải pháp thường dùng là **truyền phụ thuộc từ bên ngoài** qua constructor, để mã sản xuất cung cấp adapter thật và test cung cấp bản thay thế có hành vi được kiểm soát. Không cần tạo một hệ thống dependency injection phức tạp chỉ để làm điều đó.

### 3.2. Thời gian, ngẫu nhiên và cấu hình toàn cục bị giấu

```java
Instant createdAt = Instant.now();
String id = UUID.randomUUID().toString();
String region = System.getenv("SHIPPING_REGION");
```

Những nguồn này tạo ra đầu vào ngầm. Test kiểm tra thời gian biên hoặc một ID cụ thể khó viết chính xác. Thay thế phù hợp:

- `Clock` cho thời điểm.
- Một nguồn sinh ID có hợp đồng rõ nếu giá trị ID ảnh hưởng kết quả cần xác nhận.
- Cấu hình được truyền vào hoặc cung cấp qua thành phần có phạm vi rõ ràng.

Không phải cứ thấy `Instant.now()` là phải refactor; một phương thức logging nhỏ có thể chấp nhận đọc đồng hồ trực tiếp. Hãy quan tâm khi nguồn biến động làm **hành vi cần kiểm thử** trở nên không xác định.

### 3.3. Quy tắc và tác dụng phụ đan xen

Ví dụ:

```java
long fee = shippingClient.quoteFee(...);
orderStore.save(...);
if (fee < 0) {
    throw new IllegalStateException("Invalid fee");
}
```

Nếu kiểm tra phí âm sau khi lưu, việc trả exception không xóa tác dụng phụ đã xảy ra. Cấu trúc khiến test phải kiểm tra cả dữ liệu đã ghi để phát hiện lỗi.

Đưa validation và quyết định có thể thực hiện **trước tác dụng phụ** giúp luồng rõ hơn; điều này không thay transaction cho nhiều thao tác ghi phụ thuộc nhau, nhưng thu hẹp số trường hợp trạng thái dở dang.

### 3.4. Trạng thái dùng chung giữa các test

Một `static Map` có thể sửa, singleton giữ bộ đếm hoặc cache không được reset sẽ khiến kết quả phụ thuộc thứ tự chạy. Test A để lại dữ liệu làm test B thất bại, dù khi chạy riêng B luôn qua.

Nên xác định rõ chủ sở hữu và vòng đời dữ liệu test. Mỗi test có thể tạo đối tượng mới, hoặc làm sạch dữ liệu trong một transaction/test fixture có kiểm soát. Tránh vá bằng cách “chạy test theo đúng thứ tự” nếu các test đáng ra phải độc lập.

### 3.5. Lỗi bị nuốt hoặc bị đổi thành giá trị thành công

```java
try {
    return shippingClient.quoteFee(...);
} catch (Exception ignored) {
    return 0L;
}
```

Nếu `0L` mang nghĩa **miễn phí vận chuyển**, mã đã biến lỗi mạng thành chính sách miễn phí. Điều này đồng thời che lỗi nghiệp vụ và làm test khó quan sát rằng phụ thuộc thất bại.

Testability tốt cần kết quả phân biệt được **thành công hợp lệ**, **bị từ chối theo quy tắc** và **không thực hiện được vì sự cố**. Một exception cụ thể hoặc kiểu kết quả rõ ràng có thể phù hợp; chọn cách nào tùy hợp đồng.

### 3.6. Cần sleep để chờ một kết quả có thể kiểm soát

```java
Thread.sleep(2000);
assertTrue(jobCompleted());
```

Đây có thể là dấu hiệu test đang phụ thuộc lịch chạy, thời gian thực hoặc đồng bộ kém. Với logic tính hạn, dùng đồng hồ giả/fixed clock; với bất đồng bộ, dùng tín hiệu hoàn tất, future, latch hoặc cơ chế chờ có deadline rõ. Không dùng sleep dài như biện pháp chính để “làm test ổn định”.

Trong test tích hợp với hệ thống ngoài, chờ có giới hạn và kiểm tra trạng thái cuối có thể cần thiết. Nhưng độ trễ giả định nên được thay bằng điều kiện có thể quan sát.

## 4. Thiết kế lại đúng phần cần kiểm thử

Đầu tiên, xác định ba trách nhiệm:

1. **Quy tắc nghiệp vụ**: yêu cầu hợp lệ, phí vận chuyển hợp lệ, tổng tiền không tràn và chỉ lưu khi dữ liệu đầy đủ.
2. **Tương tác hạ tầng**: gọi nhà vận chuyển và lưu đơn vào database.
3. **Nguồn dữ liệu biến động**: thời điểm tạo và mã đơn.

Ta có thể tạo các ranh giới nhỏ. Đoạn sau là phiên bản Java 17 tự chứa về mặt cấu trúc; phần triển khai thật cho các interface được cung cấp tại điểm khởi tạo ứng dụng.

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

record CheckoutRequest(String customerId, long subtotalVnd) {
    CheckoutRequest {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("Customer ID is required");
        }
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Subtotal cannot be negative");
        }
    }
}

record Purchase(
        String id,
        String customerId,
        long subtotalVnd,
        long shippingFeeVnd,
        long totalVnd,
        Instant createdAt
) {}

@FunctionalInterface
interface ShippingFeeGateway {
    long quoteFee(CheckoutRequest request);
}

@FunctionalInterface
interface PurchaseStore {
    void save(Purchase purchase);
}

@FunctionalInterface
interface OrderIdSource {
    String nextId();
}

final class CheckoutService {
    private final ShippingFeeGateway shipping;
    private final PurchaseStore store;
    private final Clock clock;
    private final OrderIdSource ids;

    CheckoutService(
            ShippingFeeGateway shipping,
            PurchaseStore store,
            Clock clock,
            OrderIdSource ids
    ) {
        this.shipping = Objects.requireNonNull(shipping);
        this.store = Objects.requireNonNull(store);
        this.clock = Objects.requireNonNull(clock);
        this.ids = Objects.requireNonNull(ids);
    }

    Purchase checkout(CheckoutRequest request) {
        Objects.requireNonNull(request, "request");

        long feeVnd = shipping.quoteFee(request);
        if (feeVnd < 0) {
            throw new IllegalStateException("Shipping fee cannot be negative");
        }

        long totalVnd = Math.addExact(request.subtotalVnd(), feeVnd);
        String id = Objects.requireNonNull(ids.nextId(), "order ID");
        if (id.isBlank()) {
            throw new IllegalStateException("Order ID cannot be blank");
        }

        Purchase purchase = new Purchase(
                id, request.customerId(), request.subtotalVnd(),
                feeVnd, totalVnd, clock.instant()
        );

        store.save(purchase);
        return purchase;
    }
}
```

Trong ví dụ này, `totalVnd` được tính bằng `Math.addExact` để phát hiện tràn số **trước khi lưu** và trở thành một phần của kết quả `Purchase`. Ở sản phẩm thật có thể đưa phép tính này vào mô hình miền hoặc tính tổng từ các thành phần theo quy tắc nghiệp vụ. Mục tiêu ở đây là tránh phát sinh một bản ghi rồi mới phát hiện kết quả số học không hợp lệ.

### Điều gì thực sự được cải thiện?

`CheckoutService` vẫn điều phối các bước chính; không cần biết cách tạo kết nối HTTP hoặc JDBC. Người viết test có thể chọn:

- Gateway trả phí `25_000L`, `0L`, `-1L` hoặc ném exception.
- Store ghi nhận các `Purchase` đã nhận, không cần database.
- `Clock.fixed(...)` để có thời điểm tạo bất biến.
- `OrderIdSource` trả `"order-123"` để xác nhận kết quả chính xác.

Những ranh giới này làm đầu vào dễ điều khiển và kết quả dễ quan sát hơn. Đồng thời chúng làm rõ hợp đồng: phí vận chuyển không âm, phải có mã đơn, lỗi báo giá hoặc lỗi lưu không được coi là thành công.

### Điều gì chưa được giải quyết?

Ví dụ **chưa** xử lý kiểm soát đồng thời, chống tạo đơn trùng khi client thử lại, transaction của nhiều bản ghi, timeout/retry của HTTP hoặc tính đúng của triển khai `PurchaseStore`. Đó là trách nhiệm phải được thiết kế và kiểm thử ở tầng tích hợp. Một unit test tốt không chứng minh tất cả các ranh giới vận hành này đã an toàn.

Chúng ta cũng không đưa ra cơ chế thông báo hay phát sự kiện, vì yêu cầu tình huống chưa có chúng. Thêm outbox, message broker hay factory tổng quát chỉ để phục vụ test sẽ làm tăng độ phức tạp không cần thiết.

## 5. Một bộ test có ý nghĩa cho tình huống

Sử dụng JUnit 5 với fake store đơn giản: fake ghi nhận điều đã được yêu cầu lưu; stub gateway trả dữ liệu do test chọn. Chúng ta **quan sát hợp đồng nghiệp vụ** thay vì kiểm tra từng lời gọi nội bộ.

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

class CheckoutServiceTest {
    static final Instant FIXED_TIME =
            Instant.parse("2026-11-16T08:00:00Z");

    static final class RecordingStore implements PurchaseStore {
        final List<Purchase> saved = new ArrayList<>();

        @Override
        public void save(Purchase purchase) {
            saved.add(purchase);
        }
    }

    @Test
    void savesPurchaseWithKnownFeeIdAndTimestamp() {
        RecordingStore store = new RecordingStore();
        ShippingFeeGateway shipping = request -> 25_000L;
        CheckoutService service = new CheckoutService(
                shipping,
                store,
                Clock.fixed(FIXED_TIME, ZoneOffset.UTC),
                () -> "order-123"
        );

        Purchase result = service.checkout(
                new CheckoutRequest("customer-1", 200_000L));

        assertEquals("order-123", result.id());
        assertEquals(25_000L, result.shippingFeeVnd());
        assertEquals(225_000L, result.totalVnd());
        assertEquals(FIXED_TIME, result.createdAt());
        assertEquals(List.of(result), store.saved);
    }

    @Test
    void invalidShippingFeeDoesNotSaveOrder() {
        RecordingStore store = new RecordingStore();
        CheckoutService service = new CheckoutService(
                request -> -1L,
                store,
                Clock.fixed(FIXED_TIME, ZoneOffset.UTC),
                () -> "order-123"
        );

        assertThrows(IllegalStateException.class, () ->
                service.checkout(new CheckoutRequest("customer-1", 200_000L)));
        assertTrue(store.saved.isEmpty());
    }

    @Test
    void shippingFailureDoesNotSaveOrder() {
        RecordingStore store = new RecordingStore();
        CheckoutService service = new CheckoutService(
                request -> {
                    throw new IllegalStateException("Shipping unavailable");
                },
                store,
                Clock.fixed(FIXED_TIME, ZoneOffset.UTC),
                () -> "order-123"
        );

        assertThrows(IllegalStateException.class, () ->
                service.checkout(new CheckoutRequest("customer-1", 200_000L)));
        assertTrue(store.saved.isEmpty());
    }

    @Test
    void overflowingTotalIsRejectedBeforeSaving() {
        RecordingStore store = new RecordingStore();
        CheckoutService service = new CheckoutService(
                request -> 1L,
                store,
                Clock.fixed(FIXED_TIME, ZoneOffset.UTC),
                () -> "order-123"
        );

        assertThrows(ArithmeticException.class, () ->
                service.checkout(
                        new CheckoutRequest("customer-1", Long.MAX_VALUE)));
        assertTrue(store.saved.isEmpty());
    }

    @Test
    void storageFailureIsNotReportedAsSuccess() {
        PurchaseStore unavailableStore = purchase -> {
            throw new IllegalStateException("Storage unavailable");
        };
        CheckoutService service = new CheckoutService(
                request -> 25_000L,
                unavailableStore,
                Clock.fixed(FIXED_TIME, ZoneOffset.UTC),
                () -> "order-123"
        );

        assertThrows(IllegalStateException.class, () ->
                service.checkout(new CheckoutRequest("customer-1", 200_000L)));
    }

    @Test
    void rejectsInvalidInputBeforeAnyExternalCall() {
        assertThrows(IllegalArgumentException.class,
                () -> new CheckoutRequest("", 200_000L));
        assertThrows(IllegalArgumentException.class,
                () -> new CheckoutRequest("customer-1", -1L));
    }
}
```

Điểm đáng chú ý:

- Test xác định được **phí, thời gian và ID** mà không chạy HTTP hoặc DB.
- Test kiểm tra cả **kết quả** lẫn **tác dụng phụ có ý nghĩa**: khi phí sai hoặc gateway lỗi thì không có đơn nào được lưu.
- Test không phụ thuộc vào thời gian thực, số ngẫu nhiên hoặc thứ tự chạy.
- Không cần mock mọi phương thức nội bộ; fake store là đủ để quan sát hành vi.

Đoạn test trên dùng các interface và record đã định nghĩa ở mục 4; các trường hợp lỗi lưu và tràn số cũng được kiểm tra trực tiếp. Không nên đánh đồng số lượng test nhiều với độ tin cậy cao; một test tốt thường tập trung vào **một hợp đồng hoặc một rủi ro** có thể nêu tên.

### Bảng ca kiểm thử xuất phát từ yêu cầu

| Điều kiện | Kết quả quan sát cần xác nhận | Mức kiểm thử |
| --- | --- | --- |
| Giá trị giỏ hợp lệ, gateway trả 25.000 VND | Lưu đúng đơn và trả cùng nội dung | Unit |
| Gateway trả phí âm | Báo lỗi, không gọi lưu | Unit |
| Gateway ném lỗi | Không lưu đơn, lỗi không bị biến thành phí 0 | Unit |
| Tổng tiền vượt phạm vi `long` | Không lưu giá trị sai do tràn số | Unit |
| Store ném lỗi | Không trả `Purchase` như một kết quả thành công | Unit |
| Gateway HTTP thật trả JSON hợp lệ | Adapter parse và chuyển đổi đúng dữ liệu | Integration |
| Gateway timeout, trả mã lỗi hoặc JSON sai | Adapter phân loại lỗi theo hợp đồng | Integration |
| Database từ chối ghi | Transaction, rollback và phản hồi đúng | Integration |
| Hai request cùng một mã nghiệp vụ | Có cơ chế chống trùng nếu sản phẩm yêu cầu | Integration/concurrency |

Bảng này cũng nhắc chúng ta không thể chỉ nhìn unit test rồi khẳng định mọi tương tác ngoài đều đúng.

## 6. Test khó viết có thể chỉ ra lỗi thiết kế thật

Nhiều khi vấn đề kiểm thử không dừng ở sự bất tiện.

**Ví dụ 1: không thể giả lập phí âm.** Khi buộc phải tạo stub trả `-1L`, ta nhận ra mã cũ không kiểm tra phí trước khi lưu. Thiết kế mới đặt validation tại nơi sở hữu quyết định.

**Ví dụ 2: không thể mô phỏng lỗi lưu.** Khi thử một fake store ném exception, nhóm phải quyết định rõ kết quả API nên thế nào. Không thể trả “đặt hàng thành công” chỉ vì phí đã tính xong nếu dữ liệu chưa lưu.

**Ví dụ 3: không xác định được ID theo yêu cầu.** Nếu tính năng cần chống trùng theo idempotency key, test sẽ chỉ ra ID đơn ngẫu nhiên khác với định danh yêu cầu từ phía client. Sinh ID riêng cho đơn hàng là hợp lý, nhưng chưa giải quyết yêu cầu “cùng một request chỉ xử lý một lần”. Có thể cần định danh yêu cầu bền vững, ràng buộc duy nhất và kiểm tra tích hợp.

**Ví dụ 4: test phải chờ đúng thời điểm.** Khi có chính sách khuyến mãi hết hạn lúc 00:00 UTC, dùng `Clock.fixed` cho phép kiểm tra ngay trước, đúng và sau ranh giới. Nếu mã còn `Instant.now()` nằm sâu ở nơi khác, test có thể phát hiện hai nguồn thời gian không nhất quán.

Như vậy, khả năng kiểm thử là **một công cụ phản hồi về thiết kế**: khi không thể diễn đạt tình huống lỗi trong test, ta thường chưa xác định rõ ai sở hữu đầu vào, bất biến và hành vi thất bại.

## 7. Tách quyết định thuần túy khỏi việc điều phối I/O

Không phải cứ có phụ thuộc vào HTTP là toàn bộ lớp phải trở thành phức tạp. Trong nhiều bài toán, có thể đưa tính toán thuần túy vào một hàm riêng:

```java
final class PurchaseTotals {
    static long totalVnd(long subtotalVnd, long shippingFeeVnd) {
        if (subtotalVnd < 0 || shippingFeeVnd < 0) {
            throw new IllegalArgumentException("Amounts cannot be negative");
        }
        return Math.addExact(subtotalVnd, shippingFeeVnd);
    }
}
```

Test:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PurchaseTotalsTest {
    @Test
    void addsShippingToSubtotal() {
        assertEquals(225_000L,
                PurchaseTotals.totalVnd(200_000L, 25_000L));
    }

    @Test
    void rejectsNegativeFeeAndOverflow() {
        assertThrows(IllegalArgumentException.class,
                () -> PurchaseTotals.totalVnd(100L, -1L));
        assertThrows(ArithmeticException.class,
                () -> PurchaseTotals.totalVnd(Long.MAX_VALUE, 1L));
    }
}
```

Phương thức này xác định kết quả chỉ từ tham số và không gây tác dụng phụ. Unit test rất nhanh và có thể bao phủ các ranh giới toán học. Khi nhóm muốn thay quy tắc tổng tiền (ví dụ áp dụng giảm giá), việc tách trách nhiệm giúp dễ xác định chỗ thay đổi.

Tuy nhiên, **không cần tách mỗi biểu thức thành một class**. Nếu phép cộng chỉ dùng một nơi, đơn giản và đã đủ rõ, một phương thức nhỏ hoặc validation ngay trong lớp nghiệp vụ cũng có thể hợp lý. Động lực tách là sự rõ ràng về trách nhiệm và khả năng xác nhận rủi ro, không phải theo đuổi “100% pure functions”.

## 8. Phân biệt stub, fake, mock và hệ thống thật

Những cách thay phụ thuộc có mục đích khác nhau:

| Công cụ | Dùng để làm gì? | Trong tình huống checkout |
| --- | --- | --- |
| **Stub** | Cung cấp phản hồi có kiểm soát | Gateway luôn trả 25.000 VND hoặc ném lỗi |
| **Fake** | Triển khai đơn giản có hoạt động nhưng không tương đương hệ thống thật | Store ghi vào danh sách trong bộ nhớ |
| **Mock/spy** | Xác nhận tương tác được kỳ vọng, thường qua thư viện | Kiểm tra chỉ gửi lệnh lưu một lần nếu đó là hợp đồng |
| **Adapter thật** | Kiểm tra giao thức và đặc tính hạ tầng thực | HTTP client và JDBC repository thật |

Có thể test bằng lambda mà không cần framework mock. Mặt khác, mock hữu ích khi hợp đồng quan trọng nằm ở **việc tương tác**, chẳng hạn gửi một lệnh không được lặp. Nguy cơ là test bám quá sát chi tiết triển khai:

```text
Test kiểm tra:
  controller gọi facade
  facade gọi service
  service gọi helper
  helper gọi mapper

Nhưng không kiểm tra:
  phí âm bị từ chối
  tổng tiền đúng
  đơn chỉ được lưu khi dữ liệu hợp lệ
```

Khi refactor đổi tên hoặc gộp phương thức nội bộ, các test tương tác cơ học có thể hỏng dù hành vi vẫn đúng. Với logic nghiệp vụ, ưu tiên xác nhận kết quả và tác dụng phụ nhìn thấy từ ranh giới được hỗ trợ.

### Fake không phải database thật

Một `RecordingStore` dùng `ArrayList` không kiểm tra được:

- SQL syntax, mapping cột, migration.
- Unique constraint, foreign key, transaction.
- Khóa và mức cô lập khi nhiều request đồng thời.
- Lỗi kết nối, thời gian timeout hoặc dữ liệu lớn.

Vì thế testability tốt **không đồng nghĩa với thay toàn bộ tích hợp bằng fake**. Fake giúp kiểm tra quyết định nghiệp vụ nhanh; test tích hợp xác minh adapter thật và các ràng buộc mà fake không thể mô phỏng đáng tin.

## 9. Testability không phụ thuộc vào việc có nhiều interface

Một lớp có thể có một interface nhưng vẫn rất khó kiểm thử:

```java
interface OrderWorkflow {
    Object execute(String type, Object payload);
}
```

Kiểu `Object` và chuỗi điều khiển giấu thông tin, người viết test khó biết đầu vào/đầu ra hợp lệ và phải ép kiểu ở nhiều nơi. Tạo ra interface không sửa được vấn đề hợp đồng mơ hồ.

Ngược lại, một phương thức Java thuần túy với dữ liệu rõ ràng có thể rất dễ kiểm thử mà không cần interface:

```java
boolean eligibleForFreeShipping(long subtotalVnd) {
    return subtotalVnd >= 500_000L;
}
```

Hãy đánh giá khả năng kiểm thử qua **khả năng đặt điều kiện và xác nhận hành vi**, không qua số lượng abstraction. Chỉ tạo ranh giới thay thế khi nó tương ứng với nguồn bất định, I/O hoặc biến thể thực sự.

### Khi nào interface chỉ có một triển khai vẫn hữu ích?

Nếu `ShippingFeeGateway` hiện chỉ có `HttpShippingGateway`, một interface vẫn có lý do: ứng dụng cần cô lập hợp đồng phí vận chuyển khỏi thư viện HTTP cụ thể, cần kiểm thử lỗi mạng hoặc có rủi ro tích hợp bên ngoài.

Ngược lại, một `OrderTotalCalculator` chỉ làm phép cộng, không có phụ thuộc và không dự kiến có biến thể, thường không cần thêm interface `IOrderTotalCalculator` riêng chỉ để test.

## 10. Những khó khăn do test gây ra, chưa chắc do thiết kế

Một test bất ổn có thể do chính cách viết test. Đừng vội sửa mã sản xuất khi chưa xác định nguyên nhân.

### Dữ liệu thử thiếu cách ly

Test dùng chung database và không dọn bản ghi sẽ phụ thuộc thứ tự chạy. Cần chiến lược fixture, transaction rollback hoặc dữ liệu riêng theo test. Một phương thức nghiệp vụ thiết kế tốt vẫn bị test đỏ nếu môi trường bị ô nhiễm.

### Khẳng định không đúng ranh giới

Kiểm tra toàn bộ nội dung JSON bao gồm thứ tự các trường trong khi hợp đồng chỉ nói về các trường có tên có thể tạo lỗi giả. Hãy assert những giá trị thực sự thuộc hợp đồng.

### Sử dụng đồng hồ thật trong test thời gian

Một bài test dựa vào `Instant.now()` ở hai điểm khác nhau có thể hỏng quanh thời hạn. Nếu mã cho phép truyền `Clock`, dùng fixed clock; nếu bài test không tận dụng được ranh giới đã có, đó là vấn đề cách viết test.

### Test phụ thuộc hệ thống ngoài không ổn định

Test tích hợp có thể dùng môi trường thử do nhóm quản lý, stub server hoặc cơ chế giả lập giao thức để kiểm soát phản hồi. Sau đó giữ một số kiểm tra end-to-end phù hợp nhằm phát hiện khác biệt với nhà cung cấp thật. Tùy rủi ro, contract test với provider hoặc kiểm tra môi trường staging có thể cần bổ sung.

### Test quá rộng cho một quy tắc quá nhỏ

Nếu test “đổi một ngưỡng” phải khởi chạy UI, HTTP server, database và hàng đợi, thời gian phản hồi dài không chỉ do thiết kế lớp. Nó cũng có thể do **lựa chọn cấp kiểm thử** chưa hợp lý. Nên cân bằng unit, integration và end-to-end theo rủi ro thực tế.

## 11. Quy trình chẩn đoán thiết kế khó kiểm thử từ một yêu cầu thay đổi

Khi gặp một lớp hoặc một tính năng mới, có thể làm theo trình tự sau.

### Bước 1: Viết một hành vi cụ thể cần kiểm chứng

Ví dụ: “Nếu gateway vận chuyển trả phí âm, hệ thống từ chối tạo đơn và không ghi bất kỳ đơn nào.”

Tránh bắt đầu bằng kết luận “class này phải dùng dependency injection”. Hành vi được nêu rõ mới cho biết test cần điều khiển và quan sát điều gì.

### Bước 2: Liệt kê đầu vào nhìn thấy và đầu vào ngầm

| Đầu vào trực tiếp | Đầu vào ngầm ban đầu |
| --- | --- |
| Mã khách | Phản hồi HTTP |
| Giá trị giỏ | Đồng hồ hệ thống |
| | UUID ngẫu nhiên |
| | Cấu hình kết nối DB |
| | Trạng thái DB hiện tại |

Các đầu vào ngầm sẽ chỉ ra nơi nào có thể cần ranh giới được kiểm soát.

### Bước 3: Liệt kê tác dụng phụ và trạng thái có thể quan sát

Ngoài giá trị `Purchase` trả về, tính năng có tác dụng phụ **lưu đơn**. Nếu sau này gửi email, thanh toán hay phát sự kiện, mỗi tác dụng phụ cần một hợp đồng rõ về thứ tự, thất bại và retry. Đừng bỏ qua side effect chỉ vì kết quả trả về đúng.

### Bước 4: Đánh dấu chỗ khó tạo tình huống lỗi

Thử viết test giả định gateway trả phí âm, ném exception hoặc store từ chối lưu. Nếu không thể tạo trạng thái này một cách gọn gàng, xem xét ranh giới phụ thuộc.

### Bước 5: Thực hiện thay đổi nhỏ nhất

Có thể chỉ cần:

- Truyền `Clock` thay vì dùng `Instant.now()` ở nhiều nơi.
- Truyền gateway vào constructor thay vì `new` bên trong.
- Tách phép tính thuần túy khỏi adapter I/O.
- Đưa validation trước thao tác ghi.

Không nhất thiết phải tạo service locator, container DI hay một lớp trừu tượng cho từng dòng mã.

### Bước 6: Kiểm tra lại những rủi ro đã được giải quyết

Test nhanh và ổn định là tín hiệu tích cực, nhưng cần xác nhận:

- Quy tắc nghiệp vụ được test bằng dữ liệu biên.
- Tác dụng phụ quan trọng được quan sát.
- Hợp đồng lỗi không bị thay đổi âm thầm.
- Có test tích hợp cho phần mà fake không mô phỏng đúng.
- Đường đi trong mã sản xuất vẫn dễ đọc.

### Bước 7: Đánh giá chi phí duy trì

Một interface mới có ích nếu giảm công sức tạo các điều kiện kiểm thử và cô lập một phụ thuộc thật. Nếu chỉ thêm một factory, nhiều kiểu chung chung và cấu hình để làm một phép cộng, thiết kế có thể đã phức tạp hơn.

## 12. Ma trận từ triệu chứng đến nguyên nhân và hướng xử lý

| Triệu chứng khi test | Nguyên nhân khả dĩ | Hướng kiểm tra/cải thiện |
| --- | --- | --- |
| Test chỉ chạy được khi có kết nối DB | Lớp nghiệp vụ tự tạo repository | Tiêm store, test nghiệp vụ bằng fake; bổ sung integration test riêng |
| Test fail ngẫu nhiên quanh nửa đêm | Logic gọi thời gian thực | Tiêm `Clock`, kiểm tra trước/đúng/sau ngưỡng |
| Không mô phỏng được phản hồi API lỗi | HTTP client bị tạo cứng trong hàm | Đặt ranh giới gateway có hợp đồng rõ |
| Chạy riêng qua, chạy cả bộ fail | Trạng thái mutable chia sẻ hoặc fixture bẩn | Cách ly state và dữ liệu mỗi test |
| Phải `Thread.sleep` để đoán kết quả | Chưa có tín hiệu hoàn tất hoặc phụ thuộc lịch chạy | Chờ theo điều kiện có deadline, dùng completion signal |
| Test thay đổi theo ID sinh ngẫu nhiên | Nguồn ID bị giấu | Cung cấp nguồn ID có thể điều khiển |
| Dùng nhiều mock mà ít kiểm tra hành vi | Test quá gắn chi tiết lời gọi nội bộ | Xác nhận trạng thái cuối và hợp đồng nghiệp vụ |
| Lỗi mạng bị hiển thị thành dữ liệu rỗng | Ngoại lệ bị nuốt | Phân biệt lỗi với kết quả vắng mặt hợp lệ |
| Interface nhiều nhưng test vẫn khó | Hợp đồng quá chung, kiểu dữ liệu mơ hồ | Đặt tên API theo nghiệp vụ, kiểm soát input/output |
| Fake test qua nhưng sản xuất lỗi concurrency | Thiếu kiểm tra ràng buộc ở tầng lưu trữ | Bổ sung integration/concurrency test và thiết kế transaction |

Bảng là **gợi ý điều tra**, không phải quy tắc kết luận tự động. Mỗi triệu chứng có thể có nhiều nguyên nhân; cần bằng chứng từ luồng gọi, dữ liệu và môi trường chạy.

## 13. Bài tập tình huống

### Tình huống A: khuyến mãi hết hạn đúng thời điểm

Một `DiscountService` gọi `LocalDateTime.now()` rồi so sánh với giờ kết thúc khuyến mãi. Test chạy lúc 23:59 và 00:00 cho kết quả khác nhau.

Hãy xác định đầu vào ngầm và đề xuất cách mô hình hóa thời hạn theo múi giờ. Viết ba ca kiểm thử: trước hạn, đúng hạn và sau hạn. Giải thích vì sao sử dụng `Clock.fixed` hữu ích hơn ngủ cho tới giờ cần test.

### Tình huống B: kho hàng và cạnh tranh

Một unit test dùng fake repository luôn báo còn 1 sản phẩm và xác nhận đặt hàng thành công. Sản xuất có hai request đồng thời đặt sản phẩm cuối cùng và cả hai đều được chấp nhận.

Hãy giải thích vì sao unit test với fake chưa kiểm chứng được bất biến tồn kho dùng chung; nêu một integration test chạy đồng thời và cơ chế cập nhật nguyên tử ở database cần quan sát. Không được kết luận mã an toàn cạnh tranh chỉ vì việc tiêm repository đã làm test dễ viết.

### Tình huống C: email sau khi lưu

Một service lưu đơn rồi gọi `new SmtpClient().send(...)`. SMTP lỗi khiến API trả lỗi dù đơn đã lưu thành công. Người dùng thử lại và có nguy cơ tạo đơn trùng.

Hãy xác định những ranh giới khó kiểm thử và những trạng thái nghiệp vụ phải phân biệt. Bạn sẽ kiểm thử hành vi khi SMTP lỗi thế nào? Khi nào cần chuyển gửi email sang tiến trình riêng, dùng outbox hoặc cơ chế idempotency?

### Tình huống D: test nhiều mock nhưng ít giá trị

Bộ test kiểm tra `CheckoutController` gọi `CheckoutFacade`, facade gọi `CheckoutService`, service gọi `CheckoutHelper` đúng một lần. Tuy nhiên, không có test cho phí âm hoặc lỗi lưu.

Hãy đề xuất một test hành vi bao trùm hợp đồng nghiệp vụ quan trọng, xác định mock/fake nào thật sự cần và loại nào chỉ khiến test phụ thuộc cấu trúc nội bộ.

### Tình huống E: phương thức dài với nhiều trường hợp đặc biệt

Một phương thức `calculatePrice` có 200 dòng gồm thuế, phí và giảm giá, nhưng không dùng I/O. Nhóm đề xuất tạo interface cho từng phép tính chỉ để “dễ mock”.

Hãy xem liệu nên trích các quy tắc nghiệp vụ thành hàm thuần túy với dữ liệu rõ ràng trước không. Nêu cách đặt đầu vào và xác nhận ranh giới mà không cần mock. Nếu thuế và giảm giá có nguồn dữ liệu bên ngoài, đâu là ranh giới phù hợp để tách?

Với mỗi tình huống, trả lời theo chuỗi: **hành vi cần kiểm chứng → điều kiện khó điều khiển → kết quả khó quan sát → thay đổi thiết kế nhỏ nhất → test còn thiếu**.

## 14. Ghi nhớ

Khả năng kiểm thử không được quyết định bởi số lượng test, số interface hoặc việc có dùng một framework mock. Nó thể hiện ở việc **chúng ta có thể đặt hệ thống vào tình huống cần xác nhận và quan sát đúng hành vi với chi phí hợp lý hay không**.

- Bắt đầu bằng một yêu cầu cụ thể, rồi tìm những đầu vào ẩn như thời gian, ngẫu nhiên, I/O và trạng thái dùng chung.
- Làm rõ kết quả và tác dụng phụ nào thuộc hợp đồng để test xác nhận điều quan trọng.
- Tách quyết định có thể kiểm tra riêng khỏi phụ thuộc ngoài khi điều đó làm luồng rõ hơn.
- Dùng stub/fake để kiểm soát tình huống nghiệp vụ; giữ integration test cho giao thức, transaction, concurrency và adapter thật.
- Tránh test dễ vỡ do kiểm tra chi tiết nội bộ, do thời gian thực hoặc dữ liệu test bị chia sẻ.
- Khi test khó viết, hãy điều tra cả **thiết kế sản xuất, hợp đồng nghiệp vụ lẫn cách xây dựng test**, rồi chỉ thay đổi phần có bằng chứng.

Một thiết kế dễ kiểm thử thường cũng dễ hiểu hơn: đầu vào quan trọng hiện rõ, tác dụng phụ có ranh giới, lỗi có nghĩa và mỗi thay đổi có nơi để xác nhận hành vi.
