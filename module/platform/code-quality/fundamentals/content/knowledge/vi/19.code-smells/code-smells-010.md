# Trừu tượng hóa suy đoán và thành phần chưa có nhu cầu thực

Một lập trình viên có thể thêm `PaymentProviderFactory`, `AbstractPricingEngine`, nhiều interface chiến lược và một cơ chế đăng ký plugin dù sản phẩm hiện chỉ có **một** cách tính giá. Ý định thường tốt: “chuẩn bị để sau này mở rộng”. Nhưng nếu tương lai chưa được xác nhận, những lớp mới có thể khiến một thay đổi nhỏ phải đi qua nhiều tệp, nhiều hợp đồng và nhiều bước cấu hình mà không mang lại giá trị thực tế.

Mùi mã này thường được gọi là **Speculative Generality** — trừu tượng hóa hoặc tổng quát hóa dựa trên những tình huống **được dự đoán** thay vì nhu cầu có thật. Nó gần với các thành phần “để dành”: interface chỉ có một triển khai không mang ý nghĩa ranh giới, tham số không sử dụng, lớp con rỗng, hook chưa có người gọi hoặc cơ chế mở rộng chưa được dùng.

Bài học thuộc chương **Mùi mã** của **CODE_QUALITY_FUNDAMENTALS**. Theo mục tiêu module, mã chất lượng cần **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở đây, mục tiêu không phải loại bỏ mọi trừu tượng, mà là học cách nhận ra **chi phí của sự linh hoạt chưa cần thiết**, tìm bằng chứng cho một ranh giới có ích, và đơn giản hóa thiết kế mà không làm mất khả năng thay đổi khi nhu cầu thực sự xuất hiện.

## 1. Mùi mã không đồng nghĩa lỗi chắc chắn

**Code smell** là một dấu hiệu trong cấu trúc mã khiến nhóm nên kiểm tra kỹ hơn. Nó **không tự chứng minh** chương trình tính sai, chạy chậm hoặc có lỗ hổng bảo mật.

Với trừu tượng hóa suy đoán, câu hỏi không phải “có interface hay không?” mà là:

> Thành phần trừu tượng này đang giúp giải quyết một nhu cầu **có thật và được kiểm chứng**, hay chỉ bắt nhóm bảo trì một khả năng chưa ai sử dụng?

Một interface có một triển khai vẫn có thể hợp lý nếu nó là ranh giới với I/O, là hợp đồng public ổn định, hỗ trợ dependency inversion, hoặc giúp cô lập hệ thống bên ngoài trong kiểm thử. Ngược lại, một hệ thống có ba cách triển khai khác nhau vẫn có thể bị trừu tượng hóa sai nếu chúng không cùng ngữ nghĩa hoặc buộc phải chia sẻ một interface quá rộng.

Những phán đoán sau là khác nhau:

- **Chương trình đang chạy đúng**: tính đúng đắn hiện tại có thể tốt.
- **Thiết kế có mùi mã**: đang có chi phí đọc hiểu, thay đổi hoặc kiểm thử không tương xứng.
- **Thiết kế phải refactor ngay**: chỉ kết luận khi lợi ích của thay đổi lớn hơn rủi ro và chi phí trong bối cảnh thực.

Đừng biến một dấu hiệu kiến trúc thành luật “cấm interface”, “cấm kế thừa” hoặc “mọi lớp chỉ được tồn tại khi có hai triển khai”.

## 2. Vì sao lập trình viên thường tổng quát hóa quá sớm?

Một số nguyên nhân phổ biến:

1. **Dự đoán yêu cầu:** “sớm muộn cũng có nhiều nhà cung cấp”, “chắc chắn sẽ có thêm định dạng”.
2. **Áp dụng mẫu thiết kế máy móc:** dùng Strategy, Abstract Factory, Template Method hoặc plugin registry vì đã học mẫu đó.
3. **Hiểu quá rộng nguyên tắc Open/Closed:** cho rằng mọi đoạn mã phải mở rộng được bằng cách thêm class, không bao giờ được sửa class cũ.
4. **Sợ trùng lặp từ đầu:** gộp hai tình huống chỉ giống nhau ở cú pháp thành một framework tổng quát.
5. **Muốn dễ test bằng mọi giá:** tạo interface và mock cho cả hàm thuần vốn dễ kiểm thử trực tiếp.
6. **Mang nguyên kiến trúc hệ thống lớn sang tác vụ nhỏ:** thêm nhiều tầng, đăng ký dependency injection và cấu hình cho một chức năng chưa cần chúng.
7. **Quên dọn cấu trúc cũ:** tính năng thử nghiệm đã bị hủy nhưng interface, flag và nhánh tương thích vẫn còn.

Những động cơ này có thể xuất phát từ mong muốn cải thiện chất lượng. Nhưng **ý định tạo khả năng mở rộng** không đủ để biện minh cho **chi phí duy trì khả năng mở rộng**.

### 2.1. Phân biệt ba khái niệm dễ nhầm

| Khái niệm | Mô tả | Ví dụ |
| --- | --- | --- |
| **Abstraction có giá trị** | Che giấu một chi tiết biến động hoặc biểu diễn hợp đồng ổn định có người dùng thật | `ProductReader` tách nghiệp vụ khỏi database |
| **Speculative Generality** | Chuẩn bị cho nhiều biến thể chưa có yêu cầu hoặc bằng chứng dùng đến | Factory chọn chính sách theo `channel` dù chỉ có một chính sách |
| **Dead code** | Mã không còn được sử dụng trong phạm vi hệ thống đã xác minh | Một lớp thử nghiệm không được đăng ký hay gọi nữa |
| **Premature optimization** | Đổi thiết kế nhằm tăng hiệu năng trước khi biết nút thắt và workload | Cache mọi giá trị dù không có đọc lặp |
| **Overengineering** | Giải pháp có nhiều thành phần và cơ chế hơn nhu cầu biện minh | Dựng framework plugin cho một báo cáo đơn giản |

Các hiện tượng có thể cùng xuất hiện, nhưng khác nguyên nhân và hướng xử lý. Một factory chưa cần có thể là speculative generality dù nó vẫn được gọi ở runtime. Một helper không dùng nữa có thể là dead code mà trước đây từng rất cần.

## 3. Dấu hiệu nhận diện trong mã Java

| Dấu hiệu | Ví dụ thường gặp | Câu hỏi cần đặt |
| --- | --- | --- |
| Interface chỉ có một implementation và một bên dùng | `IPriceCalculator` + `DefaultPriceCalculator` | Interface đang bảo vệ ranh giới nào hay chỉ chuyển tiếp? |
| Abstract class có một lớp con | `AbstractOrderProcessor` → `StandardOrderProcessor` | Có hành vi chung thật cần kế thừa không? |
| Tham số chưa sử dụng | `quote(order, channel, futureMode)` nhưng bỏ qua hai tham số | Ai cung cấp giá trị đó và khi nào nó có tác dụng? |
| Hook chỉ có mặc định rỗng | `protected void beforeSave() {}` | Có yêu cầu biến thể hoặc người dùng hook chưa? |
| Factory luôn trả cùng một loại | `PolicyFactory.create(...)` luôn tạo `DefaultPolicy` | Factory đang giải quyết nhu cầu tạo đối tượng thực nào? |
| Cờ cho tính năng chưa tồn tại | `enableAdvancedRouting` không thay hành vi | Flag có lịch triển khai, chủ sở hữu và test không? |
| Lớp cấu hình chứa trường “for future use” | `supportsMultiTenantMode` nhưng chưa có multi-tenant | Có hợp đồng hiện tại nào cần trường này? |
| Framework tổng quát chỉ dùng một trường hợp | `RuleRegistry`, `HandlerProvider` cho một rule | Registry có giảm công sức thay đổi thực không? |
| Wrapper chỉ gọi tiếp | `Facade` → `Manager` → `Service` → `Processor` | Mỗi tầng có trách nhiệm độc lập không? |
| Type parameter không mang ý nghĩa | `BaseController<T, U, V>` chỉ dùng `T` | Generic có giúp đúng kiểu hoặc tái sử dụng thực không? |
| Mã thử nghiệm vẫn đi kèm production | `LegacyExperimentalStrategy` không được chọn | Có đường gọi động hoặc tương thích nào phải giữ? |

**Không có dấu hiệu nào đủ để kết luận độc lập.** Trước khi xóa, cần xác minh vị trí sử dụng, hợp đồng công khai, đăng ký động, cấu hình và yêu cầu dự kiến đã được phê duyệt.

### 3.1. Sự phức tạp không chỉ nằm ở số dòng

Một phương thức chỉ có một dòng:

~~~java
return policyRegistry.resolve(context).apply(order, options);
~~~

có thể trông đơn giản nhưng buộc người đọc tìm:

- `context` được tạo ở đâu.
- Registry đăng ký những chính sách nào.
- Điều kiện chọn policy có phụ thuộc cấu hình không.
- `options` có bao nhiêu cờ, cờ nào thực sự hoạt động.
- Ngoại lệ, tác dụng phụ và state nằm ở implementation nào.

Điểm Cognitive Complexity của phương thức có thể thấp, nhưng **chi phí điều hướng** và **phạm vi kiến thức cần hiểu** vẫn lớn. Hạ điểm đo tại một file bằng cách đẩy logic qua nhiều tầng không mặc nhiên là cải thiện.

## 4. Chi phí thật của sự linh hoạt chưa cần thiết

Một abstraction tạo ra **hợp đồng**. Khi đã xuất hiện, người bảo trì phải tự hỏi nó có bao nhiêu implementation, có được gọi động không, có phải giữ tương thích không và thay đổi ở đâu là đúng.

| Loại chi phí | Biểu hiện |
| --- | --- |
| **Đọc hiểu** | Phải lần theo nhiều tầng mới biết nghiệp vụ chạy thế nào |
| **Thay đổi** | Sửa một quy tắc nhỏ có thể phải đổi interface, factory, registry và cấu hình |
| **Kiểm thử** | Test phải dựng nhiều mock, cấu hình DI hoặc fake không cần thiết |
| **Bảo trì hợp đồng** | Signature cũ phải giữ vì nhiều lớp đang implements, kể cả khi sai hướng |
| **Phụ thuộc** | Tăng số type, package và chiều import cần hiểu |
| **Nguy cơ cấu hình** | Registry sai tên, provider không được đăng ký hoặc thứ tự chọn mơ hồ |
| **Review và onboarding** | Người mới không biết tầng nào là nơi sửa thật |
| **Cơ hội bị bỏ lỡ** | Thời gian xây cơ chế giả định có thể dùng cho test, xử lý lỗi hoặc yêu cầu hiện tại |

Nhưng bỏ abstraction cũng có chi phí nếu nhiều bên đang phụ thuộc vào hợp đồng. Cần đánh giá **chi phí tiếp tục duy trì** và **chi phí đơn giản hóa an toàn**, không xóa chỉ để giảm số class.

## 5. Ví dụ xuyên suốt: hệ thống chỉ có một quy tắc giảm giá

Giả sử một hệ thống hiện có yêu cầu đã được xác nhận:

- Đơn hàng có mã `orderId` và tổng tiền `subtotalVnd` nguyên VND không âm.
- Khách VIP được giảm **10%** nếu tổng tiền từ **500.000 VND** trở lên.
- Khách không VIP không được giảm theo quy tắc này.
- Phần giảm làm tròn xuống đến VND nguyên bằng chia số nguyên.
- Số tiền phải trả bằng tổng tiền trừ số tiền giảm.
- Chưa có yêu cầu chính sách theo kênh bán; sản phẩm hiện dùng **một** cách tính giá.

Đây là **đặc tả minh họa cho bài học**, không phải chính sách dùng chung của mọi dự án.

### 5.1. Mô hình dữ liệu đầu vào và đầu ra

Ví dụ dùng Java 17:

~~~java
record PurchaseOrder(String orderId,
                     long subtotalVnd,
                     boolean vip) {
    PurchaseOrder {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException(
                    "subtotalVnd must not be negative");
        }
    }
}

record PriceQuote(String orderId,
                  long subtotalVnd,
                  long discountVnd,
                  long amountDueVnd) {}
~~~

Tên trường nêu rõ đơn vị VND. `PurchaseOrder` là record có trường bất biến; ví dụ không bàn đến nguồn dữ liệu vì bài học tập trung vào cấu trúc tính toán. Nếu có đa tiền tệ hoặc quy tắc làm tròn phức tạp, cần mô hình phù hợp hơn là một `long`.

### 5.2. Thiết kế suy đoán trước khi có biến thể

Một lập trình viên dự kiến “sẽ có nhiều chính sách theo kênh bán”, nên thêm:

~~~java
interface DiscountStrategy {
    long discountVnd(PurchaseOrder order);
}

final class DefaultDiscountStrategy
        implements DiscountStrategy {

    @Override
    public long discountVnd(PurchaseOrder order) {
        if (order.vip() && order.subtotalVnd() >= 500_000L) {
            return order.subtotalVnd() / 10L;
        }
        return 0L;
    }
}

interface DiscountStrategyFactory {
    DiscountStrategy forChannel(String channel);
}

final class DefaultDiscountStrategyFactory
        implements DiscountStrategyFactory {

    private final DiscountStrategy defaultStrategy =
            new DefaultDiscountStrategy();

    @Override
    public DiscountStrategy forChannel(String channel) {
        // Hiện chưa có chính sách theo channel.
        return defaultStrategy;
    }
}

final class PricingFacade {
    private final DiscountStrategyFactory factory;

    PricingFacade(DiscountStrategyFactory factory) {
        this.factory = factory;
    }

    PriceQuote quote(PurchaseOrder order, String channel) {
        long discount = factory.forChannel(channel)
                .discountVnd(order);

        long due = Math.subtractExact(
                order.subtotalVnd(), discount);

        return new PriceQuote(
                order.orderId(),
                order.subtotalVnd(),
                discount,
                due);
    }
}
~~~

Đây là **mã có thể vận hành theo một đường xử lý**, nhưng cấu trúc đang trả giá cho một tương lai chưa xuất hiện:

- `channel` là tham số của API nhưng **không tác động đến kết quả**.
- `DefaultDiscountStrategyFactory` luôn trả một implementation.
- `DiscountStrategyFactory` chưa che giấu việc chọn biến thể thực tế nào.
- Test cần dựng factory hoặc mock interface trước khi kiểm chứng phép tính đơn giản.
- Người đọc có thể nhầm rằng **hai kênh được tính giá khác nhau** dù chưa hề có chính sách đó.

Thậm chí **sự tồn tại của tham số chưa dùng là rủi ro về hợp đồng**: caller có thể cho rằng truyền `"partner"` sẽ kích hoạt chính sách riêng. Hành vi thật lại giống `"web"`, và điều này có thể bị hiểu sai khi sản phẩm mở rộng.

Vì chưa có nhu cầu chọn policy theo kênh, một interface và một factory không tạo ra lợi ích tương xứng với chi phí tại thời điểm này.

### 5.3. Thiết kế đơn giản đáp ứng yêu cầu đang có

~~~java
import java.util.Objects;

final class PricingService {
    PriceQuote quote(PurchaseOrder order) {
        Objects.requireNonNull(order, "order");

        long discountVnd = 0L;
        if (order.vip() && order.subtotalVnd() >= 500_000L) {
            discountVnd = order.subtotalVnd() / 10L;
        }

        long amountDueVnd = Math.subtractExact(
                order.subtotalVnd(), discountVnd);

        return new PriceQuote(
                order.orderId(),
                order.subtotalVnd(),
                discountVnd,
                amountDueVnd);
    }
}
~~~

So với thiết kế trước, cách này:

- Diễn đạt chính sách tại nơi người đọc dễ tìm.
- Không nhận `channel` mà chưa có ý nghĩa.
- Không cần registry hoặc factory cho một luật duy nhất.
- Không làm logic tính giá phụ thuộc framework hay I/O.
- Giữ khả năng viết unit test bằng dữ liệu thuần.
- Cho phép thay đổi chính sách sau này bằng một quyết định mới dựa trên yêu cầu thật.

**Đơn giản không đồng nghĩa mọi thứ phải viết trong một hàm dài.** Nếu chính sách đã có nhiều điều kiện phức tạp, có thể tách thành hàm hoặc type có ý nghĩa nghiệp vụ hiện tại, chẳng hạn `VipDiscountPolicy`, nhưng chưa nhất thiết xây cả hệ thống plugin.

### 5.4. Kiểm thử sau khi đơn giản hóa

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PricingServiceTest {
    private final PricingService pricing = new PricingService();

    @Test
    void discountsVipAtExactThreshold() {
        PriceQuote quote = pricing.quote(
                new PurchaseOrder("O-01", 500_000L, true));

        assertEquals(50_000L, quote.discountVnd());
        assertEquals(450_000L, quote.amountDueVnd());
    }

    @Test
    void doesNotDiscountVipBelowThreshold() {
        PriceQuote quote = pricing.quote(
                new PurchaseOrder("O-02", 499_999L, true));

        assertEquals(0L, quote.discountVnd());
        assertEquals(499_999L, quote.amountDueVnd());
    }

    @Test
    void doesNotDiscountNonVip() {
        PriceQuote quote = pricing.quote(
                new PurchaseOrder("O-03", 800_000L, false));

        assertEquals(0L, quote.discountVnd());
        assertEquals(800_000L, quote.amountDueVnd());
    }

    @Test
    void roundsDiscountDownToWholeVnd() {
        PriceQuote quote = pricing.quote(
                new PurchaseOrder("O-04", 500_009L, true));

        assertEquals(50_000L, quote.discountVnd());
        assertEquals(450_009L, quote.amountDueVnd());
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> new PurchaseOrder("O-05", -1L, true));
    }
}
~~~

Những test này bảo vệ **hành vi được yêu cầu**, chứ không khóa test vào việc phải có factory nào hoặc một strategy được gọi bao nhiêu lần. Nếu refactor cấu trúc lần nữa, test vẫn hữu ích miễn hợp đồng nghiệp vụ không thay đổi.

Khi bỏ các tầng cũ trong ứng dụng thật, cần kiểm tra **public API, dependency injection, cấu hình serialization, reflection và nơi gọi qua module khác**. Ví dụ này chỉ minh họa lõi nghiệp vụ; không thể tự khẳng định mọi hệ thống thực đều có thể xóa interface mà không cần kế hoạch tương thích.

## 6. Khi biến thể thật xuất hiện thì sao?

Giả sử sau đó sản phẩm đã **phê duyệt** hai chính sách khác nhau:

- **DIRECT:** dùng quy tắc VIP 10% từ 500.000 VND như trước.
- **PARTNER:** giảm 5% cho đơn hàng được xử lý qua đối tác, không phụ thuộc cờ VIP.

Đây là yêu cầu cụ thể để cân nhắc điểm biến thiên của thiết kế.

### 6.1. Có thể dùng một nhánh rõ ràng trước

Nếu chỉ có hai trường hợp đơn giản, một `enum` và một `switch` tường minh có thể đủ:

~~~java
enum SalesChannel {
    DIRECT,
    PARTNER
}

final class DiscountRules {
    static long discountVnd(PurchaseOrder order,
                            SalesChannel channel) {
        if (order == null || channel == null) {
            throw new IllegalArgumentException("missing input");
        }

        return switch (channel) {
            case DIRECT ->
                    order.vip() && order.subtotalVnd() >= 500_000L
                            ? order.subtotalVnd() / 10L
                            : 0L;
            case PARTNER -> order.subtotalVnd() / 20L;
        };
    }
}
~~~

Với Java 17, `switch expression` có cú pháp như trên. Điểm quan trọng là **nhánh PARTNER hiện có hành vi thật và có thể kiểm thử**. Nó không còn là một tham số “cho tương lai”.

Không nhất thiết dùng Strategy ngay khi có hai giá trị enum. Nếu mọi chính sách đơn giản, thay đổi cùng nhau và chỉ dùng ở một chỗ, cách trực tiếp có thể dễ hiểu hơn.

### 6.2. Khi nào Strategy hoặc một hợp đồng riêng có giá trị?

Một abstraction như `DiscountPolicy` có thể phù hợp khi:

- Các chính sách thực tế có **thuật toán hoặc phụ thuộc khác nhau**.
- Nhiều use case cần chọn chính sách từ một danh sách được quản lý.
- Từng chính sách được sở hữu, phát hành hoặc kiểm thử theo trách nhiệm độc lập.
- Chính sách cần được thay ở runtime theo cấu hình đã xác thực.
- Hợp đồng ổn định, còn các implementation thực sự đổi độc lập.
- Việc bổ sung một chính sách mới đang khiến nhiều nơi sửa cùng một nhánh.

Ví dụ ý tưởng:

~~~java
interface DiscountPolicy {
    long discountVnd(PurchaseOrder order);
}

final class DirectDiscountPolicy implements DiscountPolicy {
    @Override
    public long discountVnd(PurchaseOrder order) {
        return order.vip() && order.subtotalVnd() >= 500_000L
                ? order.subtotalVnd() / 10L
                : 0L;
    }
}

final class PartnerDiscountPolicy implements DiscountPolicy {
    @Override
    public long discountVnd(PurchaseOrder order) {
        return order.subtotalVnd() / 20L;
    }
}
~~~

Ở đây đã có **hai hành vi được xác định và sử dụng**. Nhưng việc chọn implementation vẫn cần một nguồn đáng tin, không được lấy enum hoặc quyền từ dữ liệu người dùng rồi bỏ qua kiểm tra hợp đồng. Không nên tự tạo một hệ thống đăng ký plugin phức tạp nếu việc chọn hai chính sách bằng `switch` là đủ.

**Chốt ý:** trì hoãn abstraction không có nghĩa chống mở rộng. Nó có nghĩa **đợi đến khi xuất hiện điểm biến thiên thật để đặt ranh giới đúng chỗ**.

## 7. YAGNI và các nguyên tắc thiết kế không mâu thuẫn đơn giản

**YAGNI — You Aren't Gonna Need It** khuyên không triển khai chức năng hoặc cơ chế chỉ vì dự đoán có thể dùng trong tương lai. Nguyên tắc này không khuyên bỏ yêu cầu đã được xác nhận, không viết test hay không chuẩn bị ranh giới cơ bản cho hệ thống đáng tin cậy.

### 7.1. YAGNI không đồng nghĩa “cứ viết code bừa rồi sửa sau”

Ngay cả khi chỉ có một chính sách, nhóm vẫn cần:

- Đầu vào và đầu ra có hợp đồng rõ.
- Kiểm soát dữ liệu sai và trường hợp biên.
- Cách chia trách nhiệm hợp lý.
- Bằng chứng kiểm thử theo mức rủi ro.
- Quản lý I/O, bảo mật, transaction và tác dụng phụ khi có.
- Tên biểu đạt khái niệm nghiệp vụ.

YAGNI chủ yếu nói về **khả năng biến thể chưa cần thiết**, không phải chất lượng tối thiểu của hành vi hiện tại.

### 7.2. Open/Closed không có nghĩa “cấm sửa mã đang có”

Nguyên tắc Open/Closed thường được diễn đạt là thành phần nên có khả năng mở rộng mà hạn chế phải sửa những hợp đồng ổn định. Điều này có giá trị khi **điểm biến thiên đã rõ**.

Nếu cố áp dụng thành “tuyệt đối không sửa lớp cũ”, nhóm có thể tạo nhiều abstraction và delegation chỉ để thêm hành vi chưa xuất hiện. Thực tế, một lớp được sửa có kiểm thử bảo vệ không tự là thiết kế tệ.

Hãy hỏi: **điều gì thay đổi thường xuyên và điều gì ổn định?** Sau khi có bằng chứng, đặt abstraction quanh ranh giới đó. Trước khi có, mã đơn giản và dễ sửa thường ít rủi ro hơn một framework dự đoán sai.

### 7.3. Dependency inversion có thể cần dù chỉ một implementation

Ví dụ use case cần đọc dữ liệu từ database:

~~~java
interface ProductReader {
    Product loadBySku(String sku);
}

final class PriceQuoteUseCase {
    private final ProductReader products;

    PriceQuoteUseCase(ProductReader products) {
        this.products = products;
    }

    // Tính toán không cần biết lớp JDBC hay HTTP cụ thể.
}
~~~

Dù hiện chỉ có `JdbcProductReader`, interface vẫn có thể tạo một **ranh giới I/O có ý nghĩa**: miền ứng dụng không phụ thuộc trực tiếp vào thư viện database, và test có thể dùng fake phù hợp.

Không nên xóa interface chỉ vì “một implementation”, nếu xóa khiến lõi nghiệp vụ bị kéo vào cơ chế lưu trữ, tăng chi phí kiểm thử hoặc phá hợp đồng module. Điều quan trọng là **lý do tồn tại của ranh giới**, không phải đếm implementation.

## 8. Trừu tượng hóa sai có thể tệ hơn một ít trùng lặp

Khi hai đoạn mã mới xuất hiện, chúng có thể trông giống nhau nhưng mang ý nghĩa khác nhau.

Ví dụ:

- Phí vận chuyển và phí xử lý thanh toán đều được tính bằng phần trăm trong một số trường hợp.
- Hai endpoint cùng nhận một chuỗi ID nhưng một ID là SKU, ID kia là mã người dùng.
- Hai rule cùng có ngưỡng 500.000 VND nhưng được thay theo hai quyết định nghiệp vụ riêng.

Nếu gộp chúng vào `GenericThresholdRule<T>` chỉ vì cú pháp tương tự, nhóm có thể tạo một abstraction chung mà sau này phải thêm cờ `ignoreMinimum`, `useRoundingB`, `forPartner` và nhiều ngoại lệ. Mỗi biến thể kéo thêm sự phụ thuộc lẫn nhau.

Một ít **trùng lặp biểu thức** đôi khi ít tốn kém hơn việc trộn hai **lý do thay đổi khác nhau**.

### 8.1. Dấu hiệu nên tách abstraction

- Nhiều đoạn mã **thể hiện cùng một quy tắc nghiệp vụ**, nếu đổi quy tắc phải đổi tất cả.
- Các triển khai có **hợp đồng chung rõ và ổn định**.
- Tách abstraction giúp bảo đảm bất biến ở một nơi.
- Người sử dụng có thể hiểu tên abstraction mà không phải biết các ngoại lệ nội bộ.
- Có bằng chứng về thay đổi lặp lại hoặc lỗi do cập nhật thiếu nơi.

### 8.2. Dấu hiệu nên giữ riêng

- Chỉ giống cú pháp, khác chủ sở hữu hoặc lý do đổi.
- Để gộp phải thêm nhiều flag điều khiển.
- Hợp đồng chung ngày càng dùng kiểu tổng quát như `Object` hoặc `Map<String, Object>` vì các trường hợp quá khác.
- Thêm biến thể mới thường yêu cầu sửa abstraction cũ và nhiều implementation.
- Các trường hợp được kiểm thử theo nghiệp vụ khác nhau và hiếm thay đổi cùng.

**Không có “luật ba lần” cứng** bắt buộc phải trích abstraction khi thấy trùng ba chỗ. Số lần lặp là một tín hiệu; **bản chất khái niệm và xu hướng thay đổi** quan trọng hơn.

## 9. Các thành phần “chưa có nhu cầu” thường xuất hiện ở đâu?

### 9.1. Tham số và cờ không dùng đến

~~~java
long calculateFee(long subtotalVnd,
                  boolean enableFuturePricing) {
    // Cờ không tham gia tính toán.
    return subtotalVnd >= 500_000L ? 0L : 30_000L;
}
~~~

Caller có thể hiểu sai rằng cờ thay đổi cách tính. Trong phạm vi API nội bộ chưa phát hành, nên xóa tham số và cập nhật các nơi gọi. Nếu là public API, cần đánh giá tương thích và kế hoạch ngừng sử dụng, không tự ý đổi chữ ký.

Nếu cờ đại diện một tính năng đã được lên lịch rõ và có kiểm thử theo trạng thái, đây có thể là việc triển khai theo giai đoạn thay vì speculative generality. Cần ghi thời điểm bật và điều kiện dọn dẹp.

### 9.2. Empty hook và lớp con rỗng

~~~java
abstract class BaseBatchProcessor {
    void run() {
        beforeProcess();
        process();
        afterProcess();
    }

    protected void beforeProcess() {}
    protected void afterProcess() {}
    protected abstract void process();
}
~~~

Mẫu Template Method có thể hợp lý khi có các bước thực sự được tùy biến. Nhưng nếu toàn bộ hệ thống chỉ có một lớp con, hai hook luôn rỗng và không có bên ngoài nào mở rộng, nó có thể làm người đọc phải lần theo một vòng đời tưởng tượng.

Khi đơn giản hóa, nên giữ lại **các bước xử lý thật** trong một class tường minh. Đừng chỉ xóa hook mà không xem framework, subclass từ thư viện hoặc khả năng mở rộng công khai.

### 9.3. Repository và manager nhiều tầng

Một mô hình có thể là:

~~~text
ReportController
    → ReportFacade
    → ReportManager
    → ReportProcessor
    → ReportService
    → ReportRepository
~~~

Tầng có thể có giá trị nếu mỗi nơi xử lý một trách nhiệm: xác thực, điều phối transaction, quy tắc nghiệp vụ, lưu dữ liệu. Nhưng nếu `Facade`, `Manager` và `Processor` chỉ chuyển cùng tham số cho nhau, nhóm cần hỏi có thể giảm tầng mà vẫn giữ ranh giới không.

**Tên “Manager” hoặc “Service” không phải vấn đề tự thân.** Chi phí đến từ các lớp không có hợp đồng và lý do thay đổi độc lập.

### 9.4. Registry, plugin và “future provider”

Một hệ thống plugin thực có thể cần:

- Nhiều nhà cung cấp độc lập.
- Khả năng cài/gỡ plugin mà không sửa lõi.
- Versioning và tương thích hợp đồng.
- Phân quyền, cấu hình và chính sách lỗi rõ.
- Kiểm thử từng plugin và xử lý plugin lỗi.

Nếu hiện chỉ có một luồng báo cáo và không có yêu cầu nạp provider động, registry có thể chỉ thêm lỗi cấu hình, bước khởi tạo và nơi tìm code.

### 9.5. Generic framework cho một use case

Một task nhập CSV đơn giản không nhất thiết cần `AbstractImporter<TInput, TState, TConfig, TOutput>` với nhiều lifecycle extension point. Trước tiên có thể triển khai một pipeline rõ trách nhiệm, tách parser, validation và writer nếu mỗi phần thực sự có hợp đồng cần bảo vệ.

Khi có thêm JSON, XML hoặc nguồn đọc mới, lúc đó người viết có **hai tình huống thật** để nhận diện phần chung và phần khác, thay vì phỏng đoán chúng sẽ giống nhau.

## 10. Phân biệt “chưa cần” với khả năng mở rộng bắt buộc

Có những bối cảnh cần chuẩn bị hợp đồng trước khi xuất hiện nhiều implementation trong cùng repository:

| Bối cảnh | Vì sao abstraction có thể cần ngay | Bằng chứng nên có |
| --- | --- | --- |
| **Public SDK hoặc API mở rộng** | Người dùng ngoài có thể viết implementation không thấy trong mã nội bộ | Hợp đồng công khai, chính sách tương thích, tài liệu extension |
| **Plugin do bên thứ ba cung cấp** | Thành phần được nạp hoặc triển khai độc lập | Quy trình đăng ký, phiên bản, kiểm thử tương thích |
| **Ranh giới hạ tầng** | Nghiệp vụ cần độc lập khỏi DB, mạng, thời gian hoặc nguồn ID | Kiến trúc, test sử dụng fake, yêu cầu đổi hạ tầng |
| **Feature rollout đã phê duyệt** | Hai hành vi phải tồn tại song song trong giai đoạn chuyển đổi | Kế hoạch rollout, flag, thời điểm xóa nhánh cũ |
| **Nhiều tenant/chính sách thực** | Có khác biệt đã được xác nhận và phải giữ đúng quyền | Đặc tả, test từng biến thể, hợp đồng chọn chính sách |
| **Tương thích dữ liệu lâu dài** | Cần giữ nhiều phiên bản schema hoặc event | Người tiêu thụ, lịch chuyển đổi, kế hoạch deprecate |

Nếu chỉ có câu “biết đâu sau này cần” mà không có **người dùng, hợp đồng, lịch triển khai hoặc ràng buộc thực**, đó là lý do yếu.

Đồng thời, **chưa thấy nơi gọi trong repository** không chứng minh không có người dùng. Public SDK, reflection, cấu hình DI, `ServiceLoader`, serialization, script bên ngoài và hệ thống đối tác có thể dùng thành phần qua đường không hiện trong tìm kiếm tĩnh.

## 11. Làm sao xác minh một thành phần thật sự không cần thiết?

Trước khi xóa class, interface, tham số hoặc hook, kiểm tra theo cấp:

1. **Tìm reference tĩnh:** nơi import, gọi method, implements, extends hoặc tạo đối tượng.
2. **Xem điểm cấu hình và wiring:** DI container, bean name, `ServiceLoader`, registry và các file cấu hình theo hợp đồng hệ thống.
3. **Kiểm tra hợp đồng public:** API dùng ngoài module, thư viện đã phát hành, serialization schema, interface extension.
4. **Xem sử dụng runtime:** dữ liệu quan sát có đáng tin không, có đường chạy theo mùa, flag hoặc job ít hoạt động không?
5. **Tra yêu cầu thật:** issue đã phê duyệt, chức năng được lên lịch, nghĩa vụ tương thích hoặc cam kết đối tác.
6. **Xem test:** test có bảo vệ biến thể đang được sử dụng, hay chỉ test khả năng chưa có yêu cầu?
7. **Ghi bằng chứng và giả thiết:** vì sao tin việc xóa hoặc gộp an toàn; phần nào chưa xác minh.

Một báo cáo “0 usages” từ IDE là **đầu mối**, không phải bằng chứng tuyệt đối. Với reflection và liên kết ngoài, cần phối hợp người sở hữu API và kiểm thử tích hợp.

### 11.1. Trường hợp có thể đơn giản hóa ngay

- Class nội bộ, không có liên kết động.
- Không có người dùng hoặc hợp đồng công khai.
- Không có yêu cầu biến thể đã cam kết.
- Test hiện tại bảo vệ hành vi đơn giản có thể giữ nguyên.
- Đổi cấu trúc nhỏ, dễ rollback và ít rủi ro.

### 11.2. Trường hợp cần lộ trình

- Public API hoặc plugin interface đã được phát hành.
- Nhiều ứng dụng dùng chung một thư viện.
- Dữ liệu đã được serialize theo type hoặc field cũ.
- Feature flag đang chuyển đổi người dùng qua hai đường xử lý.
- Có tiến trình nền/cấu hình runtime dùng một class ít được gọi.

Với trường hợp này, có thể **đánh dấu deprecate**, đo sử dụng trong phạm vi được phép, hỗ trợ tương thích tạm và xóa ở phiên bản phù hợp. Một abstraction thừa trong thiết kế mới không có nghĩa có thể phá hợp đồng triển khai cũ ngay hôm nay.

## 12. Refactor an toàn từ cấu trúc suy đoán sang thiết kế tối giản

### Bước 1 — Viết lại yêu cầu hiện tại

Nêu rõ hệ thống đang hỗ trợ trường hợp nào, dữ liệu đầu vào, đầu ra, tác dụng phụ, lỗi và các biến thể đã được xác nhận. Ví dụ: “Hiện chỉ có một chính sách giá; `channel` không ảnh hưởng phép tính.”

Nếu có tranh luận về việc tương lai có thêm kênh, đưa điều đó vào **giả thiết cần xem lại**, không tự coi là chức năng hiện tại.

### Bước 2 — Vẽ luồng gọi và chiều phụ thuộc

~~~mermaid
flowchart TD
    A[Caller] --> B[PricingFacade]
    B --> C[DiscountStrategyFactory]
    C --> D[DefaultDiscountStrategy]
    D --> E[Quy tắc giảm giá hiện tại]
    A -. Đơn giản hóa .-> F[PricingService]
    F --> E
~~~

Sơ đồ nêu **đường điều hướng để hiểu hành vi**. Hãy xác nhận mỗi tầng có trách nhiệm thật hay chỉ chuyển tiếp.

### Bước 3 — Bảo vệ hành vi trước khi xóa

Viết hoặc củng cố test cho:

- Giá trị bình thường.
- Điều kiện biên nghiệp vụ.
- Dữ liệu không hợp lệ.
- Ngoại lệ hoặc trạng thái lỗi.
- Các tác dụng phụ quan trọng và thứ tự cần giữ.
- Hợp đồng với caller nếu đang được dùng ngoài module.

Với thay đổi cấu trúc, dùng test trên hành vi quan sát được. Không để test bắt buộc lớp factory vẫn tồn tại nếu lớp ấy không phải hợp đồng công khai.

### Bước 4 — Gộp từng tầng không có trách nhiệm độc lập

Đưa quy tắc vào thành phần có tên rõ; bỏ interface, factory, hook và tham số chưa dùng nếu đã kiểm tra an toàn. Giữ các ranh giới I/O, bảo mật, transaction và phân quyền đang thật sự có ý nghĩa.

Không cần chuyển cả hệ thống sang một kiến trúc khác trong cùng lần refactor. Mỗi bước nên nhỏ để dễ review.

### Bước 5 — Chạy lại đúng loại kiểm thử

- **Unit test:** hành vi miền bài toán không đổi.
- **Integration/contract test:** wiring, API và adapter vẫn hoạt động.
- **Test tương thích:** public API, định dạng dữ liệu và consumer quan trọng không bị phá.
- **Performance test khi có căn cứ:** việc bỏ delegation thường không mang lợi ích tốc độ đáng kể; không cần tuyên bố tăng hiệu năng nếu chưa đo.

### Bước 6 — Kiểm tra thành phần không còn được dùng

Sau khi xóa một factory, xem còn cấu hình hoặc registration nào nhắc đến nó không. Với ứng dụng khởi tạo bằng DI, một thay đổi compile được vẫn có thể lỗi wiring lúc chạy.

### Bước 7 — Ghi điều kiện khiến abstraction nên được xem lại

Ví dụ:

> “Dùng `PricingService` trực tiếp vì hiện chỉ có một chính sách giảm giá. Nếu có ít nhất hai chính sách được phê duyệt với vòng đời thay đổi độc lập, đánh giá tách `DiscountPolicy` tại ranh giới hiện tại; không triển khai registry cho tới khi có nhu cầu lựa chọn động.”

Mẫu này không biến “hai chính sách” thành ngưỡng khoa học bắt buộc. Nó ghi rõ **sự kiện cần xem lại thiết kế**, tránh phải tranh luận lại từ đầu sau vài tháng.

## 13. Kiểm thử: tránh test khóa chặt một trừu tượng không còn cần

Một test yếu có thể kiểm tra:

~~~java
// Ví dụ ý tưởng: kiểm tra chi tiết cấu trúc thay vì kết quả.
verify(factory).forChannel("web");
verify(strategy).discountVnd(order);
~~~

Các lời gọi trên có thể đúng trong thiết kế cũ, nhưng không chứng minh **số tiền phải trả** đúng. Khi gộp hai tầng, test sẽ thất bại dù hành vi người dùng không đổi.

Thay vào đó, với lõi tính toán, ưu tiên:

~~~java
PriceQuote quote = new PricingService().quote(
        new PurchaseOrder("O-01", 500_000L, true));

assertEquals(50_000L, quote.discountVnd());
assertEquals(450_000L, quote.amountDueVnd());
~~~

Với một use case thực sự cần gọi hệ thống ngoài, có thể kiểm tra tương tác **khi đó là hợp đồng**: ví dụ ghi đúng một giao dịch hoặc không gửi thông báo khi tính giá thất bại.

**Không phải mọi interaction test đều sai.** Vấn đề là bảo vệ **chi tiết triển khai không mang giá trị nghiệp vụ**, khiến nhóm ngại đơn giản hóa cấu trúc.

### 13.1. Test số lượng class không phải chỉ số chất lượng

Một hệ thống có một lớp `PricingService` và test tốt không tự kém hơn hệ thống có sáu lớp cùng nhiều mock. Ngược lại, một hệ thống chỉ một class nhưng trộn tính tiền, SQL, email và retry có thể khó bảo trì hơn thiết kế nhiều lớp có trách nhiệm rõ.

Hãy đo và review theo **hành vi đúng, phạm vi thay đổi, độ rõ trách nhiệm và khả năng cô lập test**, không đếm lớp theo một hướng tuyệt đối.

## 14. Chọn mức trừu tượng dựa trên chi phí thay đổi thật

Có thể hình dung hai phương án:

- **Đơn giản hiện tại:** xây và hiểu nhanh, ít type và cấu hình; khi nhu cầu mới xuất hiện có thể phải refactor.
- **Tổng quát trước:** tốn chi phí thiết kế và test ngay, có thể dễ mở rộng **nếu dự đoán chính xác**; nếu dự đoán sai phải trả chi phí thừa lâu dài.

Một mô hình khái niệm:

~~~text
Tổng chi phí kỳ vọng =
    chi phí triển khai hiện tại
  + chi phí đọc hiểu và bảo trì
  + chi phí thay đổi khi yêu cầu thật xuất hiện
  + chi phí sai sót và kiểm chứng
~~~

Mô hình này **không phải công thức tiền tệ chính xác**. Nó giúp nhận diện thứ đang bị bỏ qua khi chỉ hỏi “sau này thêm class có dễ không?”.

| Câu hỏi | Thiết kế tối giản | Thiết kế tổng quát trước |
| --- | --- | --- |
| Hỗ trợ yêu cầu hiện tại | Thường trực tiếp | Có thể cần nhiều lớp để đi đến cùng kết quả |
| Chi phí hiểu luồng chính | Thường thấp | Tăng nếu nhiều tầng chọn/đăng ký |
| Khi biến thể chưa xuất hiện | Ít mã phải bảo trì | Phải duy trì cả hook/contract chưa dùng |
| Khi biến thể xuất hiện đúng như dự đoán | Cần refactor để tách | Có thể tận dụng abstraction đã có |
| Khi biến thể khác hẳn dự đoán | Thiết kế lại dựa trên nhu cầu thật | Có thể phải tháo bỏ abstraction sai |
| Khả năng kiểm thử | Tốt nếu ranh giới và dữ liệu rõ | Tốt nếu abstraction phản ánh hợp đồng thật; có thể ngược lại nếu mock quá nhiều |

Vì tương lai không chắc chắn, **trì hoãn quyết định đắt đỏ cho đến khi có thông tin tốt hơn** thường là một cách giảm rủi ro. Nhưng có những quyết định khó đảo ngược — như public API, dữ liệu đã triển khai hoặc cơ chế plugin cho đối tác — cần đầu tư thiết kế sớm dựa trên hợp đồng đã được cam kết.

## 15. Bốn tình huống so sánh để tránh áp dụng YAGNI máy móc

### 15.1. Service chỉ có một phép tính thuần

**Bối cảnh:** một báo cáo nội bộ tính điểm từ vài giá trị đầu vào, không có I/O trong phép tính, không có biến thể.

**Đánh giá:** xây interface, factory và registry chỉ để kiểm thử một hàm thuần thường không cần. Một class hoặc hàm có tên rõ và unit test là đủ.

### 15.2. Một database implementation cho use case quan trọng

**Bối cảnh:** use case thanh toán cần đọc dữ liệu đơn hàng từ database, chạy trên hệ thống lâu dài. Hiện có một adapter JDBC.

**Đánh giá:** một `OrderRepository` hẹp tại ranh giới ứng dụng có thể rất có giá trị dù chỉ một implementation, vì nó cô lập I/O, giúp test quy tắc và giảm phụ thuộc vào chi tiết JDBC. Đây không nhất thiết là speculative generality.

### 15.3. Public API cung cấp điểm mở rộng cho bên thứ ba

**Bối cảnh:** sản phẩm bán SDK, khách hàng có thể phát triển plugin độc lập; những plugin đó không nằm trong repository.

**Đánh giá:** số implementation được tìm thấy nội bộ không phản ánh số người dùng thật. Cần giữ hợp đồng đã công bố, kiểm tra tương thích, versioning và quy trình deprecate. Không xóa chỉ vì IDE báo “one implementation”.

### 15.4. Tính năng đã được phê duyệt nhưng đang rollout theo giai đoạn

**Bối cảnh:** ứng dụng phải giữ hai cách tính phí trong một thời gian chuyển đổi, có feature flag, test và lịch tắt nhánh cũ.

**Đánh giá:** cấu trúc hỗ trợ hai hành vi là nhu cầu thật ở thời điểm chuyển đổi, không phải suy đoán. Nhưng cần theo dõi **ngày xóa nhánh cũ**, tránh để hai đường vĩnh viễn tồn tại sau khi rollout kết thúc.

## 16. Khi nào không nên refactor ngay?

Một mùi mã có thể được xác nhận nhưng chưa phải ưu tiên cao nếu:

- Thành phần ít thay đổi, không nằm trên đường nghiệp vụ rủi ro và không gây khó test.
- Refactor sẽ phá public API đang có người dùng.
- Nhóm đang xử lý sự cố quan trọng; thay đổi cấu trúc lớn lúc đó tăng rủi ro.
- Thiếu test hồi quy cần thiết để bảo vệ hành vi.
- Không đủ dữ liệu về đường sử dụng động hoặc khả năng tương thích.
- Chi phí đơn giản hóa lớn hơn lợi ích kỳ vọng trong giai đoạn đang xét.

Trong trường hợp này, nên **ghi lại nợ thiết kế có điều kiện**:

- Mùi mã nằm ở đâu và gây chi phí nào.
- Vì sao chưa sửa ngay.
- Loại thay đổi nào có thể làm vấn đề trở nên cấp bách.
- Test hoặc dữ liệu sử dụng nào cần có trước khi refactor.
- Ai chịu trách nhiệm quyết định khi điều kiện thay đổi.

Đây là quản lý ưu tiên có trách nhiệm, không phải phủ nhận sự tồn tại của vấn đề.

## 17. Mẫu ghi quyết định giữ hoặc bỏ abstraction

Có thể dùng một ghi chép ngắn:

~~~markdown
### DESIGN-010 — <tên abstraction hoặc cơ chế mở rộng>

Phạm vi:
- Module / chức năng / hợp đồng liên quan:

Nhu cầu hiện tại:
- Các trường hợp đang được sử dụng:
- Người dùng hoặc hệ thống tiêu thụ hợp đồng:
- Biến thể đã được xác nhận, không chỉ dự đoán:

Giả thiết và bằng chứng:
- Vì sao abstraction được tạo:
- Nơi gọi tĩnh, cấu hình runtime và public API:
- Test và tài liệu đang dựa vào nó:

Chi phí:
- Số tầng, phụ thuộc và cấu hình thêm:
- Khó khăn review, kiểm thử hoặc thay đổi:
- Rủi ro nếu đơn giản hóa:

Quyết định:
- Giữ / đơn giản hóa / deprecate / cần điều tra thêm:
- Hành vi và tương thích phải bảo vệ:
- Người phê duyệt / người sở hữu:

Điều kiện xem lại:
- Khi có biến thể nghiệp vụ cụ thể:
- Khi API cũ không còn người dùng:
- Khi cấu trúc gây lỗi hoặc chi phí thay đổi đo được:
~~~

Mẫu này dành cho quyết định có ảnh hưởng lâu dài hoặc dễ gây tranh luận. Không phải mọi helper nhỏ đều cần tài liệu chính thức. Mục tiêu là **giữ lại lý do**, tránh việc người tiếp quản phục hồi một cấu trúc thừa vì tưởng nó đã được thiết kế cho yêu cầu có thật.

## 18. Những nhầm lẫn thường gặp

**“Interface có một implementation luôn là mùi mã.”** Không. Ranh giới I/O, hợp đồng public, plugin và dependency inversion có thể biện minh cho interface ngay cả khi repository chỉ thấy một implementation.

**“YAGNI nghĩa là không thiết kế trước bất kỳ điều gì.”** Không. Yêu cầu bảo mật, dữ liệu, khả năng kiểm thử, tương thích và ranh giới trách nhiệm hiện tại vẫn phải được thiết kế đúng.

**“Muốn tuân thủ SOLID phải dùng Strategy và Factory cho mọi nghiệp vụ.”** Không. Mẫu thiết kế là công cụ cho những vấn đề cụ thể; dùng thiếu nhu cầu có thể tăng phụ thuộc và chi phí đọc hiểu.

**“Cứ có hai chỗ giống nhau là cần một base class.”** Chưa chắc. Hai đoạn có thể giống cú pháp nhưng khác lý do thay đổi. Trừu tượng sai có thể tạo coupling nhiều hơn việc giữ riêng.

**“Sau này sẽ có nhiều loại nên thiết kế generic ngay sẽ tiết kiệm.”** Chưa có bằng chứng. Tương lai có thể khác dự đoán, và generic framework được tạo trước có thể làm việc mở rộng thật còn khó hơn.

**“Cắt bỏ factory chắc sẽ tăng hiệu năng.”** Không có cơ sở nếu chưa đo. Lợi ích chính ở ví dụ này là đơn giản hóa trách nhiệm và kiểm thử; tốc độ runtime có thể không thay đổi đáng kể.

**“Mọi lớp không có usages đều xóa an toàn.”** Không. Reflection, cấu hình DI, SPI, SDK public, serialization và bên dùng ngoài có thể không hiện trong tìm kiếm thông thường.

**“Đã có abstraction rồi thì cứ giữ, không gây hại.”** Không hẳn. Nó tạo hợp đồng, cấu hình, test và gánh nặng bảo trì; khi không còn mục đích cần cân nhắc chi phí tiếp tục giữ.

**“Test xanh là có thể bỏ mọi tầng mà không cần xem hợp đồng.”** Unit test không chứng minh wiring runtime, tích hợp bên ngoài và khả năng tương thích public đều đúng.

**“Đơn giản hóa là gom hết vào một class.”** Sai. Bỏ cơ chế biến thể suy đoán không có nghĩa bỏ ranh giới database, transaction, phân quyền và quy tắc nghiệp vụ đang cần thiết.

**“Không sửa vì mùi mã chưa gây incident thì mã chắc đã tốt.”** Không. Chi phí đọc và thay đổi cũng ảnh hưởng chất lượng; nên theo dõi khi vùng mã bắt đầu thay đổi thường xuyên hoặc test trở nên khó dựng.

## 19. Bài tập vận dụng

### Tình huống A — Factory không bao giờ chọn loại khác

`InvoiceFormatterFactory.create("pdf")` hiện luôn trả `TextFormatter`; chỉ có một use case xuất văn bản, còn PDF chưa được phê duyệt. Test chủ yếu mock factory.

**Câu hỏi:** dấu hiệu suy đoán ở đâu? Nên bắt đầu cải thiện thế nào?

**Gợi ý:** tham số định dạng và factory tạo cảm giác đã có biến thể trong khi không có. Xác nhận nơi gọi/public API; viết test trên kết quả xuất văn bản; đơn giản hóa chữ ký và cấu trúc nội bộ nếu không cần giữ tương thích. Khi có yêu cầu PDF thật, thiết kế ranh giới trên hai hành vi đã biết.

### Tình huống B — Repository interface một implementation

`OrderUseCase` phụ thuộc vào `OrderRepository`, triển khai thật là JDBC. Unit test dùng fake để kiểm tra chính sách đặt hàng; integration test xác minh mapping DB.

**Câu hỏi:** có nên xóa interface chỉ vì có một triển khai thật?

**Gợi ý:** không nhất thiết. Interface đang che chi tiết I/O và bảo vệ khả năng kiểm thử, một ranh giới có lợi ích hiện tại. Nên xem chất lượng hợp đồng và số trách nhiệm hơn là số implementation.

### Tình huống C — Hai hàm tương tự nhưng khác nghiệp vụ

Một hàm tính phí giao hàng và một hàm tính phí hủy đơn đều dùng phần trăm. Nhóm định gộp vào `GenericFeeCalculator` với nhiều boolean flag.

**Câu hỏi:** cần kiểm tra điều gì trước khi trích abstraction?

**Gợi ý:** hai phí có cùng lý do thay đổi, cùng cách làm tròn, cùng điều kiện và chủ sở hữu nghiệp vụ không? Nếu khác, giữ riêng có thể tốt hơn. Chỉ gộp phần **thực sự chung về ý nghĩa**, không gộp vì công thức trông giống.

### Tình huống D — Hook rỗng trong thư viện public

Một thư viện cho phép đối tác kế thừa `BaseImporter` và override `beforeImport`. Trong repository chỉ có một subclass và hook mặc định rỗng.

**Câu hỏi:** có đủ căn cứ xóa hook không?

**Gợi ý:** chưa. Cần kiểm tra hợp đồng public, đối tác sử dụng, versioning và quy trình deprecate. Hook mặc định rỗng có thể là một phần API mở rộng đang dùng ngoài repository.

### Tình huống E — Feature flag đã rollout xong

Sáu tháng trước, nhóm thêm `newCheckoutEnabled` để chuyển dần người dùng. Hiện 100% traffic đã dùng đường mới, nhưng đường cũ vẫn được giữ vì “lỡ phải quay lại”.

**Câu hỏi:** đây có phải nhu cầu thực hay mùi mã đang hình thành?

**Gợi ý:** trong giai đoạn rollout, hai nhánh là nhu cầu thật. Sau khi hoàn tất, cần xác minh khả năng rollback, trạng thái dữ liệu và chính sách phát hành. Nếu không còn cần đường cũ, lên kế hoạch xóa có test và kiểm chứng; giữ vĩnh viễn một nhánh có thể làm chi phí thay đổi tăng.

### Tình huống F — Lớp đơn giản nhưng chứa nhiều phụ thuộc ngoại vi

Một lớp có phương thức tính phí nhưng trực tiếp gọi JDBC và HTTP. Nhóm định xóa hai interface adapter để “giảm số lớp” theo YAGNI.

**Câu hỏi:** đó có phải cách giảm speculative generality phù hợp?

**Gợi ý:** có thể không. Ranh giới I/O giúp logic miền độc lập, kiểm thử dễ hơn và cô lập lỗi hệ thống ngoài. YAGNI không yêu cầu phá những abstraction đang giải quyết khó khăn hiện tại.

### Tình huống G — Dự đoán được thị trường mới nhưng chưa có hợp đồng

Nhóm sản phẩm nói “có thể” mở thị trường mới với chính sách thuế khác. Kỹ sư muốn viết ngay một tax engine plugin tổng quát trước khi có luật thuế, phạm vi và ngày phát hành.

**Câu hỏi:** lựa chọn ít rủi ro hơn là gì?

**Gợi ý:** giữ chính sách thuế hiện tại rõ và có test; ghi các giả thiết, giới hạn và điều kiện cần xem lại. Khi có yêu cầu thị trường mới, dùng hợp đồng cụ thể để xác định biến thể và ranh giới. Không dựng plugin theo một mô hình thuế chưa biết.

## 20. Checklist khi review trừu tượng hóa suy đoán

- **Nhu cầu thật:** abstraction đang phục vụ trường hợp đã tồn tại hoặc đã cam kết nào?
- **Người dùng:** ai gọi interface/hook/registry, kể cả người dùng ngoài repository?
- **Biến thể:** hiện có những implementation và hành vi thực nào?
- **Ý nghĩa:** hợp đồng chung phản ánh cùng khái niệm nghiệp vụ hay chỉ giống cú pháp?
- **Chi phí:** người đọc phải đi qua bao nhiêu tầng để hiểu một hành vi?
- **Ranh giới:** abstraction có bảo vệ I/O, public API, bảo mật hoặc phụ thuộc quan trọng không?
- **Tham số và flag:** có tham số, nhánh hoặc hook không tác động đến yêu cầu hiện tại?
- **Tính đúng:** có test đầu vào, kết quả và trường hợp biên trước khi refactor?
- **Tương thích:** reflection, DI, serialization, SDK hoặc consumer ngoài có bị ảnh hưởng?
- **Phương án nhỏ nhất:** bỏ một tầng chuyển tiếp có đủ cải thiện không, thay vì viết lại toàn bộ?
- **Thay đổi tương lai:** có sự kiện hoặc dữ liệu rõ ràng để xem lại quyết định không?
- **Kết quả:** sau đơn giản hóa, mã có dễ hiểu, dễ kiểm thử và dễ sửa hơn mà vẫn đúng hợp đồng không?

**Trừu tượng hóa suy đoán** nhắc rằng khả năng mở rộng luôn có chi phí. Thiết kế tốt không phải thiết kế đoán được mọi biến thể, mà là thiết kế **đáp ứng rõ ràng nhu cầu hiện tại, bảo vệ những ranh giới đã có lý do tồn tại và đủ linh hoạt để thay đổi khi có bằng chứng mới**. Trong **CODE_QUALITY_FUNDAMENTALS**, loại bỏ cơ chế “để dành” không cần thiết giúp mã **đáng tin cậy hơn nhờ ít đường cấu hình sai, dễ hiểu hơn nhờ trách nhiệm trực tiếp và dễ thay đổi hơn vì không bị khóa vào giả định tương lai chưa được xác nhận**.
