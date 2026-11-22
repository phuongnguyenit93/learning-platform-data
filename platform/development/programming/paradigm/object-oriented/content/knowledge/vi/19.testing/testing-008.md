# Tránh kiểm thử phụ thuộc quá chặt vào chi tiết bên trong

> **Bối cảnh:** OOP → Kiểm thử. Mục tiêu là viết test phát hiện lỗi nghiệp vụ nhưng vẫn cho phép refactor implementation khi hành vi công khai không đổi.

## 1. Vấn đề: bài test có thể đúng hôm nay nhưng cản trở thay đổi ngày mai

Khi lớp được kiểm thử (SUT — System Under Test) dùng đối tượng cộng tác, những thứ ta *có thể* quan sát rất nhiều: giá trị trả về, exception, trạng thái, email được gửi, số lần gọi dependency, thứ tự gọi helper, tên private field, kiểu collection. Nhưng không phải điều nào cũng là **hợp đồng** với client.

Một test **gắn chặt chi tiết triển khai** (implementation-coupled test) thất bại khi lập trình viên đổi thuật toán, tách/gộp helper, thêm cache hoặc thay cấu trúc dữ liệu, dù kết quả được hứa với client vẫn đúng. Tình trạng đó gọi là *brittle test*.

Một test đáng tin nên hỏi: **Đầu vào này dẫn đến kết quả/tác dụng phụ nào theo yêu cầu?** Chỉ khi yêu cầu thật sự giới hạn một tương tác thì mới xác minh tương tác đó.

| Test quá chặt | Test bám hợp đồng |
|---|---|
| Dùng reflection gọi helper private calculateSubtotal | Gọi API báo giá rồi assert tổng tiền |
| Verify catalog.priceOf được gọi đúng 2 lần | Assert cùng SKU trên nhiều dòng vẫn được tính đúng |
| Assert implementation sử dụng HashMap | Assert kết quả nghiệp vụ với các bộ dữ liệu |
| Verify 5 helper được gọi theo thứ tự | Assert trạng thái cuối và tác dụng phụ có ý nghĩa |
| Assert thông điệp lỗi gắn số dòng/stack trace | Assert loại lỗi và thông tin đã được cam kết |

**Ngoại lệ quan trọng:** gửi mail, ghi database, trừ tiền, xuất event có thể là **tác dụng phụ quan sát được**. Verify rằng *không gửi mail sau khi thanh toán thất bại* hoàn toàn hợp lý, vì đó là quy tắc nghiệp vụ. Tương tác nội bộ chỉ là implementation detail khi nó không được cam kết.

## 2. Ví dụ tự chạy: hai thuật toán, một hợp đồng

Yêu cầu ứng dụng báo giá:
- Mỗi dòng có SKU và số lượng nguyên dương; giỏ hàng không rỗng.
- Thành tiền = tổng đơn giá nhân số lượng.
- Phí vận chuyển 30.000 VND khi thành tiền dưới 500.000 VND; từ 500.000 VND trở lên miễn phí.
- Trả ra thành tiền, phí giao hàng và tổng; số lần tra giá SKU **không phải** hợp đồng công khai.

Bản A tra giá mỗi dòng; bản B gộp số lượng cùng SKU trước, rồi tra giá. Refactor này có thể giảm số lần gọi collaborator **PriceCatalog** nhưng không làm thay đổi kết quả. Ta viết một bộ test chạy trên cả hai.

Lưu mã sau vào file **QuoteContractDemo.java**, dùng Java 11 trở lên, không cần JUnit:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class QuoteContractDemo {
    static final long FREE_SHIPPING_FROM = 500_000L;
    static final long SHIPPING_FEE = 30_000L;

    static final class Line {
        final String sku;
        final int quantity;
        Line(String sku, int quantity) {
            this.sku = sku;
            this.quantity = quantity;
        }
    }

    static final class Quote {
        final long subtotal;
        final long shipping;
        final long total;
        Quote(long subtotal, long shipping) {
            this.subtotal = subtotal;
            this.shipping = shipping;
            this.total = Math.addExact(subtotal, shipping);
        }
    }

    interface PriceCatalog {
        long priceOf(String sku);
    }

    interface QuoteService {
        Quote quote(List<Line> lines);
    }

    // Test fake: giá cố định trong RAM, không dùng API hay database.
    static final class FakeCatalog implements PriceCatalog {
        private final Map<String, Long> prices =
                Map.of("BOOK", 200_000L, "PEN", 50_000L);
        int lookups;

        @Override
        public long priceOf(String sku) {
            lookups++;
            Long price = prices.get(sku);
            if (price == null) {
                throw new IllegalArgumentException("Unknown SKU: " + sku);
            }
            return price;
        }
    }

    private static void validate(List<Line> lines) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("Empty cart");
        }
        for (Line line : lines) {
            if (line == null || line.sku == null
                    || line.sku.isBlank() || line.quantity <= 0) {
                throw new IllegalArgumentException("Invalid line");
            }
        }
    }

    private static Quote buildQuote(long subtotal) {
        return new Quote(subtotal,
                subtotal >= FREE_SHIPPING_FROM ? 0L : SHIPPING_FEE);
    }

    // Implementation A: tra giá một lần cho từng dòng.
    static final class PerLineService implements QuoteService {
        private final PriceCatalog catalog;
        PerLineService(PriceCatalog catalog) {
            this.catalog = catalog;
        }

        @Override
        public Quote quote(List<Line> lines) {
            validate(lines);
            long subtotal = 0L;
            for (Line line : lines) {
                long amount = Math.multiplyExact(
                        catalog.priceOf(line.sku), (long) line.quantity);
                subtotal = Math.addExact(subtotal, amount);
            }
            return buildQuote(subtotal);
        }
    }

    // Implementation B: gộp SKU, mỗi SKU chỉ tra giá một lần.
    // Tổng quantity dùng long vì nhiều dòng int dương có thể vượt int.
    static final class GroupedService implements QuoteService {
        private final PriceCatalog catalog;
        GroupedService(PriceCatalog catalog) {
            this.catalog = catalog;
        }

        @Override
        public Quote quote(List<Line> lines) {
            validate(lines);
            Map<String, Long> grouped = new LinkedHashMap<>();
            for (Line line : lines) {
                grouped.merge(line.sku, (long) line.quantity, Math::addExact);
            }

            long subtotal = 0L;
            for (Map.Entry<String, Long> entry : grouped.entrySet()) {
                long amount = Math.multiplyExact(
                        catalog.priceOf(entry.getKey()),
                        entry.getValue());
                subtotal = Math.addExact(subtotal, amount);
            }
            return buildQuote(subtotal);
        }
    }

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    private static void assertQuote(QuoteService service,
                                    List<Line> lines,
                                    long subtotal, long shipping, long total) {
        Quote actual = service.quote(lines);
        check(actual.subtotal == subtotal, "Wrong subtotal");
        check(actual.shipping == shipping, "Wrong shipping");
        check(actual.total == total, "Wrong total");
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected invalid input rejection");
    }

    // Kiểm tra hợp đồng, không biết SUT dùng vòng lặp nào.
    private static void runContract(QuoteService service) {
        // 2 dòng trùng BOOK: 400.000 + 2 PEN: 100.000.
        assertQuote(service, List.of(
                new Line("BOOK", 1),
                new Line("BOOK", 1),
                new Line("PEN", 2)),
                500_000L, 0L, 500_000L);

        // Thấp hơn ngưỡng: vẫn tính phí.
        assertQuote(service,
                List.of(new Line("BOOK", 1)),
                200_000L, 30_000L, 230_000L);

        // Hai quantity int đều hợp lệ, nhưng cộng lại vượt Integer.MAX_VALUE.
        // Tổng tiền vẫn nằm trong miền long: hai implementation phải như nhau.
        assertQuote(service, List.of(
                new Line("BOOK", Integer.MAX_VALUE),
                new Line("BOOK", Integer.MAX_VALUE)),
                858_993_458_800_000L, 0L, 858_993_458_800_000L);

        expectInvalid(() -> service.quote(List.of()));
        expectInvalid(() ->
                service.quote(List.of(new Line("BOOK", 0))));
    }

    public static void main(String[] args) {
        FakeCatalog first = new FakeCatalog();
        FakeCatalog second = new FakeCatalog();

        runContract(new PerLineService(first));
        runContract(new GroupedService(second));

        System.out.println("Both implementations PASS");
        System.out.println("Per-line lookups: " + first.lookups);
        System.out.println("Grouped lookups: " + second.lookups);
    }
}
~~~

Chạy:

~~~bash
javac QuoteContractDemo.java
java QuoteContractDemo
~~~

Kết quả dự kiến:

~~~text
Both implementations PASS
Per-line lookups: 6
Grouped lookups: 4
~~~

Bộ test **PASS ở cả hai implementation**. Bộ đếm tra giá minh họa khác biệt implementation (6 so với 4 lần sau ba giỏ hợp lệ), không phải điều kiện PASS. Nếu buộc một test assert đúng bốn lần tra giá, test đó đỏ sau refactor dù giá tiền vẫn chính xác.

Các case được cố tình chọn để bắt lỗi nghiệp vụ thực sự: giỏ có SKU lặp, ngưỡng miễn phí **đúng bằng 500.000**, giỏ dưới ngưỡng, input rỗng, số lượng bằng 0 và tổng quantity vượt `int` nhưng tiền vẫn nằm trong `long`. Đổi điều kiện từ >= thành > sẽ khiến case ngưỡng đỏ: đây là regression có ý nghĩa.

## 3. Bài test Mockito dễ vỡ và bản thay thế

Ví dụ anti-pattern dưới đây giả định các lớp ở mục 2 nằm trong phạm vi import phù hợp và dự án có Mockito:

~~~java
PriceCatalog catalog = mock(PriceCatalog.class);
when(catalog.priceOf("BOOK")).thenReturn(200_000L);
when(catalog.priceOf("PEN")).thenReturn(50_000L);

QuoteService service = new PerLineService(catalog);
service.quote(List.of(
        new Line("BOOK", 1),
        new Line("BOOK", 1),
        new Line("PEN", 2)));

verify(catalog, times(2)).priceOf("BOOK");
verify(catalog, times(1)).priceOf("PEN");
~~~

Nếu thay PerLineService bằng GroupedService, lần gọi BOOK giảm từ 2 còn 1. Test hỏng dù hợp đồng không đổi.

Kiểu kiểm thử bền hơn (JUnit 5, trong cùng package với lớp mẫu):

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class QuoteBehaviorTest {
    @Test
    void duplicateSkuKeepsCorrectTotals() {
        QuoteContractDemo.PriceCatalog catalog = sku -> {
            if (sku.equals("BOOK")) return 200_000L;
            if (sku.equals("PEN")) return 50_000L;
            throw new IllegalArgumentException("Unknown SKU");
        };
        QuoteContractDemo.QuoteService service =
                new QuoteContractDemo.GroupedService(catalog);

        QuoteContractDemo.Quote quote = service.quote(List.of(
                new QuoteContractDemo.Line("BOOK", 1),
                new QuoteContractDemo.Line("BOOK", 1),
                new QuoteContractDemo.Line("PEN", 2)));

        assertEquals(500_000L, quote.subtotal);
        assertEquals(0L, quote.shipping);
        assertEquals(500_000L, quote.total);
    }
}
~~~

Với PerLineService thay GroupedService, test này vẫn xanh. Cần cấu hình dependency JUnit Jupiter và chạy bằng test runner (Maven/Gradle/IDE); ví dụ standalone ở mục 2 là lựa chọn không cần dependency.

**Vì sao không verify lời gọi PriceCatalog?** Ở ví dụ này, lookup chỉ phục vụ tính giá. Nếu yêu cầu mới được bổ sung: "mỗi SKU được tra giá tối đa một lần trong mỗi lần báo giá", giới hạn lookup lập tức trở thành **hợp đồng có thể kiểm thử**. Chuyển assertion cũ thành test riêng có tên diễn đạt ràng buộc mới; khi đó implementation A không thỏa, B thỏa.

## 4. Khi interaction verification thực sự đúng

Các đối tượng cộng tác ở ranh giới ngoại vi như gửi mail, thanh toán, ghi event, database có thể mang **side effect**. Nếu quy tắc là "không gửi hóa đơn khi thanh toán bị từ chối", nên verify không có yêu cầu gửi hóa đơn sau thất bại. Ví dụ phác thảo Mockito (các kiểu này do ứng dụng định nghĩa):

~~~java
when(gateway.charge(orderId, totalVnd)).thenReturn(false);

CheckoutResult result = checkout.checkout(orderId);

assertEquals(CheckoutResult.PAYMENT_DECLINED, result);
verifyNoInteractions(receiptSender);
~~~

Trong trường hợp này, **không gọi ReceiptSender** là yêu cầu có ý nghĩa, khác với kiểm tra số lần helper private chạy. Tương tự, thứ tự xác thực trước thao tác nhạy cảm hoặc chỉ publish event sau commit có thể là hợp đồng. Không có quy tắc "tuyệt đối tránh mọi verify(mock)".

~~~mermaid
flowchart TD
    A["Muốn thêm một assertion"] --> B{"Nó bảo vệ yêu cầu quan sát được?"}
    B -- "Có" --> C["Assert kết quả, state, error hoặc side effect"]
    B -- "Không rõ" --> D{"Chỉ đổi thuật toán thì assertion đổi?"}
    D -- "Có" --> E["Xem lại và diễn đạt bằng hành vi nghiệp vụ"]
    D -- "Không" --> F["Xác định yêu cầu và cấp test thích hợp"]
    C --> G["Test ca biên, ca lỗi và ca bình thường"]
    E --> G
    F --> G
~~~

## 5. Những dạng phụ thuộc quá chặt thường gặp

**Reflection để gọi private method.** Khi đổi tên, gộp hoặc tách helper, test hỏng dù API vẫn đúng. Hãy test qua public API. Nếu logic quá lớn và độc lập, tách thành một thành phần có hợp đồng riêng và kiểm thử qua interface của nó.

**Assert private field hoặc cấu trúc collection.** Ví dụ mở trường cache qua reflection rồi kiểm tra HashMap có 3 phần tử. Chuyển cache thành LRU sẽ làm test đỏ. Nếu yêu cầu là TTL hoặc tránh gọi API quá ngưỡng, hãy kiểm tra yêu cầu bằng Clock giả và adapter có thể đếm cuộc gọi, không đóng băng loại Map.

**Mock mọi value object.** Đối với Money, Address, OrderLine, thường nên dùng đối tượng thật. Mock quá nhiều khiến phần lớn test chỉ xác minh những stub do chính test tạo ra.

**Verify toàn bộ thứ tự gọi.** Mockito InOrder nên dành cho thứ tự được cam kết (xác thực trước khi thanh toán; publish sau commit). Không nên verify mọi bước validate, parse, calculate, format nếu chúng chỉ là helper.

**Snapshot dữ liệu quá rộng.** ID ngẫu nhiên, timestamp, debug metadata và thứ tự thuộc tính JSON không được công bố có thể thay đổi. Assert các trường công khai quan trọng; chỉ snapshot nguyên cấu trúc nếu đó chính là hợp đồng của API.

**Dùng đồng hồ và số ngẫu nhiên thật.** Nếu quy tắc phụ thuộc thời gian, inject java.time.Clock; nếu phụ thuộc ID ngẫu nhiên, inject Supplier<UUID> hoặc generator interface. Chốt dữ liệu đầu vào phi xác định trong test, rồi assert kết quả nghiệp vụ. Đừng assert số lần gọi Instant.now() trong private helper.

**Chỉ dùng double mà không test tích hợp.** Fake catalog không mô phỏng timeout, cache consistency hoặc thay đổi schema. Unit test chứng minh logic ứng dụng khi collaborator đáp ứng giả định; integration test chứng minh adapter thực tế có thực hiện đúng hợp đồng đó.

## 6. Chọn cấp test đúng trách nhiệm

| Cấp | Điều cần chứng minh | Test double | Hạn chế |
|---|---|---|---|
| Unit | Hành vi một SUT | Có thể thay collaborator để kiểm soát đầu vào | Dễ bị over-mocking |
| Component | Quy tắc của nhiều lớp phối hợp | Dùng chọn lọc | Fake có thể thiếu transaction |
| Integration | API, SQL, mapping, giao dịch thật | Ít dùng ở ranh giới chính đang test | Chậm và cần môi trường |
| End-to-end | Luồng cuối cùng từ góc nhìn người dùng | Môi trường có kiểm soát | Đắt, dễ không ổn định nếu ôm quá nhiều ca |

Cũng cần phân biệt **hợp đồng công khai** với lựa chọn cài đặt: API có thể quy định thứ tự, tính idempotent, giới hạn số lần gọi, kiểu ngoại lệ, độ chính xác tiền tệ. Nếu những điều đó thực sự được cam kết, vẫn phải test. Private/public modifier tự nó không quyết định mọi thứ có phải chi tiết nội bộ hay không.

## 7. Checklist khi review test

1. Tên test diễn đạt yêu cầu (ví dụ: freeShippingAppliesAtThreshold) thay vì tên helper (testCallsPriceOfTwice).
2. Arrange chỉ tạo dữ liệu, stub và dependency thật sự liên quan.
3. Act gọi API công khai hoặc giao diện hợp đồng thích hợp.
4. Assert đúng outcome, trạng thái, lỗi và hiệu ứng ngoài đã được quy định.
5. Không ép implementation giữ số lời gọi, tên helper, kiểu collection hay thứ tự xử lý tùy ý.
6. Thêm ca bình thường, ca lỗi, boundary và integration test cho đường nối quan trọng.
7. Sau refactor, nếu test đỏ, xác định **hợp đồng thay đổi** hay test chỉ đang bắt chi tiết nội bộ.

## 8. Bài tập và cách tự đánh giá

**Bài 1:** Thay vòng lặp tính tổng trong PerLineService bằng Stream, giữ nguyên các assertion trong runContract. Kỳ vọng toàn bộ PASS.

**Bài 2:** Đổi điều kiện miễn phí giao hàng thành subtotal > 500_000. Ca bằng đúng 500.000 phải FAIL — một regression thật.

**Bài 3:** Viết verify(catalog, times(2)).priceOf("BOOK"), rồi đổi sang GroupedService. Giải thích vì sao đó là false alarm khi chưa có yêu cầu giới hạn số lần lookup.

**Bài 4:** Thêm yêu cầu "mỗi SKU chỉ được tra giá tối đa một lần cho mỗi báo giá". Viết test riêng cho ràng buộc mới; A không đạt, B đạt. Số lượt gọi lúc này đã trở thành điều kiện hợp đồng.

**Bài 5:** Bổ sung trường hợp SKU không tồn tại, Line null, số lượng âm và tổng tiền vượt long. Xác định loại exception nào cần cam kết, và tránh assert thông điệp/stack trace nội bộ nếu không được quy định.

**Ghi nhớ:** Một bộ test chất lượng nên cho phép refactor hợp lệ, đồng thời báo đỏ khi hành vi đã hứa bị phá vỡ. Hãy kiểm tra **kết quả và hiệu ứng có ý nghĩa**, dùng test double để cô lập phụ thuộc, và dành các assertion về tương tác cho những lời gọi thực sự thuộc yêu cầu.