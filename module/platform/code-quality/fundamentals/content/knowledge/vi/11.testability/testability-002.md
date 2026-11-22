# Tách logic miền bài toán khỏi I/O và cơ chế triển khai

Một phép tính nghiệp vụ có thể đúng nhưng rất khó kiểm thử nếu mỗi lần gọi đều phải đọc tệp, mở kết nối cơ sở dữ liệu, gửi HTTP hoặc khởi động cả framework. Khi kết quả kiểm thử phụ thuộc vào mạng, đồng hồ hệ thống, dữ liệu có sẵn và cấu hình môi trường, nhóm dễ nhầm **lỗi quy tắc nghiệp vụ** với **lỗi tích hợp**.

Bài học thuộc chương **Khả năng kiểm thử** của **CODE_QUALITY_FUNDAMENTALS**. Mục tiêu của module là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Trọng tâm ở đây là xác định ranh giới giữa **logic miền bài toán**, **I/O** và **cơ chế triển khai**, sau đó tổ chức chúng để kiểm thử đúng hành vi ở đúng cấp độ.

## 1. Ba loại trách nhiệm thường bị trộn lẫn

Giả sử hệ thống cần tính giá đơn hàng và xuất báo cáo. Trong một phương thức duy nhất, lập trình viên có thể:

1. Đọc các dòng hàng từ tệp hoặc cơ sở dữ liệu.
2. Kiểm tra dữ liệu đầu vào và áp dụng quy tắc giảm giá.
3. Tính phí vận chuyển và tổng tiền.
4. Tạo văn bản báo cáo, ghi tệp hoặc gửi qua HTTP.
5. Xử lý lỗi kết nối, đường dẫn, định dạng hoặc quyền truy cập.

Các thao tác trên có liên quan trong một **use case** nhưng có lý do thay đổi khác nhau.

| Loại trách nhiệm | Câu hỏi chính | Ví dụ | Bằng chứng kiểm thử phù hợp |
| --- | --- | --- | --- |
| **Logic miền bài toán (domain logic)** | Với dữ liệu hợp lệ, quy tắc nghiệp vụ cho kết quả gì? | Ngưỡng miễn phí vận chuyển, điều kiện giảm giá, bất biến số tiền | Unit test với dữ liệu thường, biên, sai và tổ hợp quan trọng |
| **I/O (input/output)** | Dữ liệu vào/ra hệ thống qua đâu và có đúng hợp đồng không? | Đọc tệp, gọi API, truy vấn DB, gửi sự kiện | Test tích hợp, hợp đồng, lỗi kết nối/định dạng |
| **Cơ chế triển khai (implementation mechanism)** | Hệ thống thực thi và kết nối các phần ra sao? | Framework web, ORM, DI container, scheduler, serializer | Kiểm tra cấu hình, wiring, integration và end-to-end theo rủi ro |
| **Điều phối ứng dụng (application orchestration)** | Luồng nào gọi các trách nhiệm trên và xử lý kết quả/thất bại? | Đọc giỏ hàng → tính giá → lưu báo cáo | Unit test dùng fake tại ranh giới và integration test cho luồng thực |

Một thao tác có thể kết hợp nhiều kỹ thuật; mục tiêu là đặt **quy tắc nghiệp vụ ổn định** ở nơi không cần biết quá nhiều về cách dữ liệu được lấy hoặc trả về.

### 1.1. Những gì thuộc logic miền bài toán

Ví dụ, quy định “khách VIP được giảm 10% khi tổng giá hàng từ 500.000 VND trở lên” là chính sách nghiệp vụ. Quy định vẫn đúng dù dữ liệu đến từ HTTP, bảng tính hay cơ sở dữ liệu.

Phần miền bài toán cần xác định:

- Đầu vào nào được xem là hợp lệ?
- Điều kiện áp dụng chính sách là gì?
- Quy tắc làm tròn và đơn vị tiền tệ ra sao?
- Trường hợp biên được xử lý thế nào?
- Bất biến nào phải giữ, chẳng hạn tổng tiền không âm?

Các quy tắc này thường có thể biểu diễn bằng hàm nhận dữ liệu và trả kết quả, không cần truy cập hệ thống bên ngoài.

### 1.2. Những gì thuộc I/O và cơ chế triển khai

“Đọc tệp UTF-8 theo từng dòng”, “gọi API khách hàng để biết hạng VIP” và “lưu hóa đơn bằng JPA” là những cách thực thi cụ thể. Chúng có các lỗi riêng: tệp thiếu, HTTP timeout, kết nối hỏng, schema thay đổi, transaction bị từ chối.

Một quyết định kỹ thuật như dùng PostgreSQL hay MongoDB cũng không nên làm thay đổi định nghĩa của quy tắc giảm giá, nếu yêu cầu nghiệp vụ vẫn giữ nguyên.

## 2. Vấn đề khi trộn tất cả vào một phương thức

Ví dụ minh họa một chương trình Java đọc tệp chứa **mỗi dòng là một giá hàng tính bằng VND** rồi ghi tổng tiền:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

final class MixedPriceReport {
    static void generate(Path input, Path output) throws IOException {
        long subtotal = 0;
        for (String line : Files.readAllLines(input,
                StandardCharsets.UTF_8)) {
            if (!line.isBlank()) {
                subtotal += Long.parseLong(line.trim());
            }
        }

        long shippingFee = subtotal >= 300_000 ? 0 : 30_000;
        long total = subtotal + shippingFee;

        Files.writeString(output, "totalVnd=" + total,
                StandardCharsets.UTF_8);
    }
}
~~~

Trong ví dụ này, muốn kiểm tra trường hợp tổng tiền đúng **300.000 VND**, test phải tạo tệp đầu vào, chọn đường dẫn, gọi phương thức, đọc tệp kết quả và dọn tài nguyên. Khi test thất bại, nguyên nhân có thể là quy tắc ngưỡng sai, quyền ghi tệp, encoding hoặc lỗi parse.

Đoạn mã còn có các rủi ro độc lập:

- Không ngăn giá trị âm; dữ liệu sai có thể đi thẳng vào kết quả.
- Phép `+=` và cộng phí có thể tràn `long` mà không phát hiện.
- Thay định dạng đầu vào sẽ phải sửa phương thức đang chứa quy tắc giá.
- Thêm đầu ra HTTP hoặc database dễ kéo logic giá sang một nơi khác.
- Đoạn mã khó tái sử dụng để tính giá trong API mà không sinh tệp.

Điều này **không có nghĩa mọi script nhỏ đều phải thiết kế nhiều lớp**. Với công cụ dùng một lần và tác động thấp, cách viết ngắn có thể phù hợp. Nhưng khi quy tắc được dùng lặp lại, dễ thay đổi hoặc có hậu quả nếu tính sai, việc tách ranh giới giúp kiểm chứng và bảo trì đáng kể.

## 3. Nguyên tắc: lõi nghiệp vụ thuần, lớp ngoài xử lý tác dụng phụ

Một cách tổ chức thường gọi là **functional core, imperative shell**:

- **Lõi (core):** nhận dữ liệu đầu vào đã được mô hình hóa, áp dụng chính sách và trả về kết quả. Cố gắng giữ tính quyết định (*deterministic*) và không có tác dụng phụ ngoài phạm vi lời gọi.
- **Lớp ngoài (shell):** đọc dữ liệu, gọi hệ thống ngoài, lấy thời gian hiện tại, ghi kết quả, phát sự kiện, thực hiện transaction và xử lý lỗi tích hợp.
- **Ứng dụng:** phối hợp lõi và lớp ngoài để hoàn thành một use case.

~~~mermaid
flowchart LR
    I[Đầu vào: tệp/API/DB] --> A[Adapter đọc]
    A --> U[Use case điều phối]
    U --> D[Logic miền bài toán]
    D --> U
    U --> O[Adapter ghi]
    O --> E[Đầu ra: tệp/API/DB]
~~~

**Chiều phụ thuộc trong mã nguồn** có thể hướng từ use case đến hợp đồng và miền bài toán; adapter bên ngoài triển khai các hợp đồng ấy. **Dòng dữ liệu lúc chạy** vẫn đi từ đầu vào qua use case tới đầu ra. Không nên đồng nhất hai loại mũi tên.

Một phép tính được xem là gần với **hàm thuần (pure function)** khi cùng một đầu vào tạo cùng một kết quả và không thay đổi trạng thái bên ngoài. Hàm có thể cấp phát đối tượng kết quả mới; điều đó không phải tác dụng phụ quan sát được ở bên ngoài theo nghĩa đang xét. Nếu hàm đọc `System.currentTimeMillis()`, cập nhật biến static hoặc gọi mạng, kết quả không còn chỉ phụ thuộc vào tham số.

## 4. Ví dụ xuyên suốt: tách chính sách báo giá bằng Java

Ta chọn hợp đồng minh họa:

- Đầu vào là danh sách các giá hàng, đều là số nguyên VND không âm.
- Nếu khách **VIP** và tổng giá hàng trước giảm từ **500.000 VND** trở lên, giảm **10%** tổng đó; chia số nguyên tương đương làm tròn xuống VND.
- Sau giảm, nếu số tiền từ **300.000 VND** trở lên thì miễn phí vận chuyển; nếu thấp hơn thì phí vận chuyển là **30.000 VND**.
- Tổng phải thanh toán bằng tiền sau giảm cộng phí vận chuyển.
- Số tiền vượt phạm vi biểu diễn của `long` phải được phát hiện.

Đây là **quy tắc giả định cho bài học**, không phải chính sách chung áp dụng cho mọi hệ thống.

### 4.1. Mô hình dữ liệu bất biến

Ví dụ dùng Java 17:

~~~java
import java.util.List;
import java.util.Objects;

record Cart(List<Long> itemPricesVnd) {
    Cart {
        Objects.requireNonNull(itemPricesVnd, "itemPricesVnd");
        itemPricesVnd = List.copyOf(itemPricesVnd);

        for (long price : itemPricesVnd) {
            if (price < 0) {
                throw new IllegalArgumentException(
                        "item price must not be negative");
            }
        }
    }
}

record PriceQuote(long subtotalVnd,
                  long discountVnd,
                  long shippingFeeVnd,
                  long amountDueVnd) {}
~~~

`List.copyOf` bảo vệ cấu trúc danh sách trong `Cart` khỏi việc bên gọi sửa danh sách gốc sau khi tạo. Nó là **bản sao nông**; ví dụ này dùng `Long` là kiểu bất biến. Nếu các phần tử là đối tượng mutable, phải xét sâu hơn về quyền sở hữu dữ liệu.

Trong bài này, danh sách rỗng là hợp lệ và được tính phí vận chuyển 30.000 VND. Dự án thật cần quyết định riêng việc có cho phép giỏ hàng rỗng hay không.

### 4.2. Quy tắc nghiệp vụ không biết I/O

~~~java
import java.util.Objects;

final class PricingPolicy {
    private static final long VIP_THRESHOLD_VND = 500_000L;
    private static final long FREE_SHIPPING_THRESHOLD_VND = 300_000L;
    private static final long STANDARD_SHIPPING_FEE_VND = 30_000L;

    PriceQuote quote(Cart cart, boolean isVip) {
        Objects.requireNonNull(cart, "cart");

        long subtotal = 0L;
        for (long price : cart.itemPricesVnd()) {
            subtotal = Math.addExact(subtotal, price);
        }

        long discount = isVip && subtotal >= VIP_THRESHOLD_VND
                ? subtotal / 10
                : 0L;

        long afterDiscount = Math.subtractExact(
                subtotal, discount);

        long shipping = afterDiscount >= FREE_SHIPPING_THRESHOLD_VND
                ? 0L
                : STANDARD_SHIPPING_FEE_VND;

        long due = Math.addExact(afterDiscount, shipping);

        return new PriceQuote(subtotal, discount, shipping, due);
    }
}
~~~

Ở đây, `PricingPolicy` không biết dữ liệu được đọc từ tệp nào, hạng VIP đến từ API nào hoặc kết quả sẽ hiển thị ở đâu. Các tham số và kiểu dữ liệu thể hiện những thông tin miền bài toán mà nó thật sự cần.

Đây là một ví dụ của **tách trách nhiệm tạo điều kiện kiểm thử**:

- Muốn thử ngưỡng giảm giá, chỉ tạo `Cart` và gọi `quote`.
- Muốn thay định dạng tệp, chỉ sửa adapter đọc.
- Muốn lưu kết quả sang cơ sở dữ liệu, chỉ thay adapter ghi.
- Muốn đổi chính sách giảm giá, sửa logic và kiểm thử của `PricingPolicy`.

**Giới hạn:** `Math.addExact` có thể ném `ArithmeticException` khi tràn. Ứng dụng thật cần quyết định hợp đồng lỗi và cách báo cho người gọi. Trong nghiệp vụ tiền tệ nhiều loại tiền hoặc đơn vị nhỏ hơn VND, cần mô hình `Money`, quy tắc làm tròn và kiểu số phù hợp; ví dụ này chỉ phục vụ một loại tiền nguyên VND.

## 5. Thiết kế hợp đồng ở ranh giới I/O

Use case vẫn phải đọc dữ liệu và ghi kết quả, nhưng có thể phụ thuộc vào **khả năng cần dùng**, thay vì một công nghệ cụ thể:

~~~java
import java.io.IOException;

interface CartSource {
    Cart load() throws IOException;
}

interface QuoteWriter {
    void write(PriceQuote quote) throws IOException;
}
~~~

Hai interface diễn đạt hai tác vụ cần thiết: **lấy giỏ hàng** và **ghi báo giá**. Chúng không ép use case biết `Path`, `HttpClient`, `JdbcTemplate`, JPA hay định dạng JSON.

Không nhất thiết tạo interface cho mọi lớp. Interface ở đây có giá trị vì use case cần ranh giới I/O rõ, có nhiều cách cung cấp dữ liệu trong test và triển khai thật, và việc đọc/ghi có lỗi độc lập.

### 5.1. Use case chỉ điều phối

~~~java
import java.io.IOException;
import java.util.Objects;

final class GenerateQuoteUseCase {
    private final CartSource source;
    private final PricingPolicy policy;
    private final QuoteWriter writer;

    GenerateQuoteUseCase(CartSource source,
                         PricingPolicy policy,
                         QuoteWriter writer) {
        this.source = Objects.requireNonNull(source, "source");
        this.policy = Objects.requireNonNull(policy, "policy");
        this.writer = Objects.requireNonNull(writer, "writer");
    }

    void run(boolean isVip) throws IOException {
        Cart cart = source.load();
        PriceQuote quote = policy.quote(cart, isVip);
        writer.write(quote);
    }
}
~~~

Phần điều phối này không có quy tắc giảm giá riêng. Nó chỉ xác định thứ tự **đọc → tính → ghi**. Nếu đọc thất bại, các bước tiếp theo không xảy ra; nếu tính toán phát hiện dữ liệu sai, kết quả không được ghi. Lỗi ghi không thể làm hàm quay ngược thời gian: với luồng ghi có tác dụng phụ, ứng dụng thật phải xét **transaction, retry và idempotency**.

Giá trị `isVip` trong ví dụ được giả định là **thông tin đáng tin do tầng gọi đã xác thực hoặc xác định**. Trong hệ thống thật, không được lấy cờ VIP do client tự khai mà bỏ qua việc xác minh quyền/hạng khách hàng.

### 5.2. Adapter đọc tệp

Giả sử định dạng đầu vào là tệp UTF-8 nhỏ, **mỗi dòng không rỗng chứa một số nguyên biểu diễn giá hàng**:

~~~text
120000
250000
130000
~~~

Adapter phụ trách việc đọc, parse và ánh xạ sang `Cart`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class TextFileCartSource implements CartSource {
    private final Path path;

    TextFileCartSource(Path path) {
        this.path = Objects.requireNonNull(path, "path");
    }

    @Override
    public Cart load() throws IOException {
        List<Long> prices = new ArrayList<>();
        int lineNumber = 0;

        for (String line : Files.readAllLines(path,
                StandardCharsets.UTF_8)) {
            lineNumber++;
            if (line.isBlank()) {
                continue;
            }
            try {
                prices.add(Long.parseLong(line.trim()));
            } catch (NumberFormatException e) {
                throw new IOException(
                        "Invalid item price at line " + lineNumber, e);
            }
        }
        return new Cart(prices);
    }
}
~~~

Adapter chịu trách nhiệm **cú pháp tệp**: dòng trống, chữ số và lỗi đọc. `Cart` bảo vệ **bất biến miền**: giá không âm. Khi dữ liệu tệp chứa `-1`, `Cart` ném `IllegalArgumentException`; ứng dụng thật có thể ánh xạ ngoại lệ đó thành lỗi đầu vào với mã lỗi rõ ràng ở đúng ranh giới, thay vì để rò stack trace ra người dùng.

`Files.readAllLines` được chọn để giữ ví dụ đơn giản. Với tệp lớn, cân nhắc xử lý theo luồng, giới hạn kích thước và giám sát bộ nhớ; không nên thay đổi chính sách giá chỉ vì cách đọc tệp đổi.

### 5.3. Adapter ghi tệp

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

final class TextFileQuoteWriter implements QuoteWriter {
    private final Path path;

    TextFileQuoteWriter(Path path) {
        this.path = Objects.requireNonNull(path, "path");
    }

    @Override
    public void write(PriceQuote quote) throws IOException {
        Objects.requireNonNull(quote, "quote");
        String report = "subtotalVnd=" + quote.subtotalVnd()
                + System.lineSeparator()
                + "discountVnd=" + quote.discountVnd()
                + System.lineSeparator()
                + "shippingFeeVnd=" + quote.shippingFeeVnd()
                + System.lineSeparator()
                + "amountDueVnd=" + quote.amountDueVnd()
                + System.lineSeparator();

        Files.writeString(path, report, StandardCharsets.UTF_8);
    }
}
~~~

Mã này thể hiện ranh giới rõ ràng nhưng **chưa bảo đảm ghi nguyên tử**. Nếu mất điện hoặc ghi thất bại giữa chừng, tệp có thể không đầy đủ. Với dữ liệu quan trọng, adapter phải thiết kế ghi tạm rồi thay thế, lưu bền vững hoặc transaction theo yêu cầu thực tế. Bản thân `PricingPolicy` không cần biết chi tiết phục hồi đó.

### 5.4. Ghép các thành phần tại điểm khởi tạo

~~~java
import java.nio.file.Path;

final class QuoteBatchMain {
    public static void main(String[] args) throws Exception {
        CartSource source =
                new TextFileCartSource(Path.of("cart.txt"));
        QuoteWriter writer =
                new TextFileQuoteWriter(Path.of("quote.txt"));

        GenerateQuoteUseCase useCase = new GenerateQuoteUseCase(
                source, new PricingPolicy(), writer);

        // Giá trị VIP chỉ minh họa; hệ thống thật phải xác định tin cậy.
        useCase.run(true);
    }
}
~~~

Đây là một **composition root** đơn giản: nơi chọn các triển khai cụ thể và lắp ghép thành luồng xử lý. Nếu chuyển từ ứng dụng dòng lệnh sang HTTP, có thể thay adapter và điểm khởi tạo trong khi vẫn giữ chính sách giá. Framework DI có thể hỗ trợ wiring ở hệ thống lớn, nhưng không phải điều kiện tiên quyết để có ranh giới tốt.

## 6. Kiểm thử miền bài toán mà không cần môi trường ngoài

Ưu điểm trực tiếp của việc tách lõi là các ca quan trọng có thể chạy **nhanh, quyết định và độc lập với I/O**.

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class PricingPolicyTest {
    private final PricingPolicy policy = new PricingPolicy();

    @Test
    void discountsVipAtExactThreshold() {
        PriceQuote quote = policy.quote(
                new Cart(List.of(500_000L)), true);

        assertEquals(500_000L, quote.subtotalVnd());
        assertEquals(50_000L, quote.discountVnd());
        assertEquals(0L, quote.shippingFeeVnd());
        assertEquals(450_000L, quote.amountDueVnd());
    }

    @Test
    void chargesShippingBelowThresholdAfterDiscount() {
        PriceQuote quote = policy.quote(
                new Cart(List.of(299_999L)), false);

        assertEquals(30_000L, quote.shippingFeeVnd());
        assertEquals(329_999L, quote.amountDueVnd());
    }

    @Test
    void waivesShippingAtBoundary() {
        PriceQuote quote = policy.quote(
                new Cart(List.of(300_000L)), false);

        assertEquals(0L, quote.shippingFeeVnd());
        assertEquals(300_000L, quote.amountDueVnd());
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(IllegalArgumentException.class,
                () -> new Cart(List.of(-1L)));
    }

    @Test
    void rejectsOverflowWhenSummingPrices() {
        assertThrows(ArithmeticException.class,
                () -> policy.quote(new Cart(
                        List.of(Long.MAX_VALUE, 1L)), false));
    }
}
~~~

Những test này chủ động dùng **đúng ngưỡng, dưới ngưỡng, dữ liệu không hợp lệ và tràn số**. Chúng không phụ thuộc quyền đọc tệp, cổng mạng hay thứ tự chạy test.

Số lượng test ít không có nghĩa đã kiểm chứng mọi điều kiện. Nếu chính sách thực tế có thêm nhiều trạng thái, loại tiền, khuyến mãi hoặc hoàn tiền, cần bổ sung kiểm thử theo các bất biến và quyết định nghiệp vụ tương ứng.

### 6.1. Kiểm thử use case bằng fake ở ranh giới

Ta muốn xác nhận luồng điều phối đọc giỏ hàng, tính giá và chuyển kết quả đi ghi. Có thể thay nguồn và nơi ghi bằng các đối tượng trong bộ nhớ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class GenerateQuoteUseCaseTest {
    @Test
    void calculatesAndSendsQuoteToOutput() throws Exception {
        CartSource source =
                () -> new Cart(List.of(500_000L));

        AtomicReference<PriceQuote> written =
                new AtomicReference<>();
        QuoteWriter writer = written::set;

        GenerateQuoteUseCase useCase = new GenerateQuoteUseCase(
                source, new PricingPolicy(), writer);

        useCase.run(true);

        assertNotNull(written.get());
        assertEquals(450_000L, written.get().amountDueVnd());
    }
}
~~~

Ở đây, `CartSource` và `QuoteWriter` mỗi loại chỉ có một phương thức trừu tượng nên có thể dùng lambda. `AtomicReference` là vật chứa để test quan sát kết quả trong cùng thread, không có yêu cầu xử lý đồng thời trong test này.

Test không cần tạo tệp. Nó kiểm tra **hợp tác giữa các thành phần**, nhưng chưa chứng minh `TextFileCartSource` parse đúng hoặc `TextFileQuoteWriter` ghi đúng UTF-8. Các adapter vẫn cần kiểm thử tích hợp riêng.

### 6.2. Kiểm tra khi I/O thất bại

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;

class GenerateQuoteFailureTest {
    @Test
    void doesNotWriteWhenSourceFails() {
        CartSource source = () -> {
            throw new IOException("Input unavailable");
        };

        AtomicBoolean writeCalled = new AtomicBoolean(false);
        QuoteWriter writer = quote -> writeCalled.set(true);

        GenerateQuoteUseCase useCase = new GenerateQuoteUseCase(
                source, new PricingPolicy(), writer);

        assertThrows(IOException.class, () -> useCase.run(false));
        assertFalse(writeCalled.get());
    }
}
~~~

Test tập trung vào **điều phối khi phụ thuộc lỗi**. Nó không cần giả lập chi tiết kết nối, nhưng bảo vệ một hành vi rõ ràng: đầu vào thất bại thì không ghi báo giá.

Có thể thêm ca **ghi thất bại** để xác nhận lỗi được báo ra phù hợp. Với use case có tác dụng phụ thực như trừ tiền hoặc thay đổi tồn kho, test cần mô tả rõ trạng thái sau lỗi, transaction và cơ chế đối soát.

## 7. Kiểm thử adapter và hợp đồng bên ngoài

Không nên kết luận “đã tách I/O, nên không cần test I/O”. Việc tách giúp **chọn đúng loại test**:

| Thành phần | Điều cần kiểm chứng | Test thích hợp |
| --- | --- | --- |
| `PricingPolicy` | Điều kiện, giới hạn, bất biến, làm tròn | Unit test thuần |
| `GenerateQuoteUseCase` | Thứ tự và điều kiện thực hiện các bước | Unit test với fake/stub |
| `TextFileCartSource` | Encoding, dòng trống, dữ liệu sai, lỗi đọc | Integration test với tệp tạm |
| `TextFileQuoteWriter` | Định dạng đầu ra, quyền, lỗi ghi, hành vi ghi đè | Integration test với tệp tạm |
| Adapter HTTP hoặc database | Hợp đồng schema, timeout, transaction, ánh xạ lỗi | Contract/integration test với hệ thống hoặc môi trường phù hợp |
| Luồng chạy thực tế | Wiring, cấu hình, bảo mật và tương tác toàn hệ thống | Một số end-to-end test theo rủi ro |

Ví dụ kiểm thử adapter bằng JUnit 5 và `@TempDir`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class TextFileCartSourceTest {
    @TempDir
    Path tempDir;

    @Test
    void readsPricesFromLines() throws Exception {
        Path input = tempDir.resolve("cart.txt");
        Files.writeString(input, "120000" + System.lineSeparator()
                + "250000" + System.lineSeparator(),
                StandardCharsets.UTF_8);

        Cart cart = new TextFileCartSource(input).load();

        assertEquals(List.of(120_000L, 250_000L),
                cart.itemPricesVnd());
    }
}
~~~

Test trên sử dụng **I/O thật nhưng bị giới hạn trong thư mục tạm**. Đây là việc có chủ đích: nó kiểm tra adapter đọc tệp, trong khi test chính sách giá không bị kéo theo tệp.

Nếu bộ tích hợp có database, đừng chỉ mock repository rồi tuyên bố query đã đúng. Cần kiểm tra query, mapping, khóa, transaction và migration tại môi trường phù hợp. Ngược lại, chạy toàn bộ database cho mỗi phép cộng số tiền là chi phí không cần thiết.

## 8. Đồng hồ, số ngẫu nhiên và ID cũng là ranh giới phụ thuộc

Không chỉ file và HTTP mới làm test thiếu tính quyết định. Một hàm miền bài toán gọi trực tiếp `Instant.now()`, `UUID.randomUUID()` hoặc trình sinh ngẫu nhiên mặc định sẽ cho kết quả thay đổi ngay cả khi dữ liệu nghiệp vụ giống nhau.

Ví dụ quy tắc chương trình khuyến mãi chỉ có hiệu lực **trước** thời điểm kết thúc. Có thể giữ phép kiểm tra thuần:

~~~java
import java.time.Instant;
import java.util.Objects;

final class PromotionPolicy {
    boolean activeAt(Instant now, Instant expiresAt) {
        Objects.requireNonNull(now, "now");
        Objects.requireNonNull(expiresAt, "expiresAt");
        return now.isBefore(expiresAt);
    }
}
~~~

Lớp điều phối quyết định **lấy thời gian từ đâu**, chẳng hạn một `Clock` được truyền từ điểm khởi tạo:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

final class CheckPromotionUseCase {
    private final Clock clock;
    private final PromotionPolicy policy;

    CheckPromotionUseCase(Clock clock, PromotionPolicy policy) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    boolean isActive(Instant expiresAt) {
        return policy.activeAt(clock.instant(), expiresAt);
    }
}
~~~

Kiểm thử có thể dùng `Clock.fixed(...)` để không phụ thuộc vào thời gian thực. Tương tự, khi yêu cầu sinh ID hoặc chọn dữ liệu ngẫu nhiên, hãy xác định khả năng cung cấp nguồn ID/ngẫu nhiên từ ranh giới thích hợp, nhất là với xử lý retry và kiểm thử có thể tái hiện.

**Lưu ý:** không dùng nguồn ngẫu nhiên dự đoán được hoặc ID giả trong môi trường sản xuất cho mục đích bảo mật chỉ để thuận tiện kiểm thử. Nguồn thực phải đáp ứng yêu cầu an toàn; nguồn test chỉ dùng ở môi trường kiểm thử.

## 9. Ranh giới miền bài toán khác ranh giới transaction

Việc `PricingPolicy` thuần không có nghĩa toàn bộ nghiệp vụ đặt hàng có thể thực hiện mà không cần giao dịch. Một use case thật có thể:

1. Đọc giỏ hàng và chính sách hiện hành.
2. Tính giá.
3. Kiểm tra và giữ tồn kho.
4. Ghi đơn hàng.
5. Phát sự kiện hoặc điều phối thanh toán.

Các bước 3–5 có tác dụng phụ và có thể thất bại một phần. Nếu việc giữ hàng và ghi đơn phải nhất quán, application service hoặc thành phần hạ tầng cần xác định **ranh giới transaction, thứ tự cập nhật, idempotency và cách phục hồi**.

~~~mermaid
flowchart TD
    A[Nhận yêu cầu] --> B[Đọc dữ liệu và xác minh đầu vào]
    B --> C[Tính chính sách miền bài toán]
    C --> D{Kết quả hợp lệ?}
    D -- Không --> E[Trả lỗi nghiệp vụ]
    D -- Có --> F[Thực thi tác dụng phụ qua hợp đồng I/O]
    F --> G{Tác dụng phụ thành công?}
    G -- Có --> H[Trả kết quả được xác nhận]
    G -- Không --> I[Phân loại lỗi, khôi phục hoặc đối soát]
~~~

Sơ đồ chỉ trình bày **ranh giới trách nhiệm**. Không thể suy ra rằng mọi hệ thống sẽ rollback được giữa database, hàng đợi và API thanh toán chỉ vì có một lớp điều phối chung.

Một kết quả tính giá đúng không thay thế cho các bảo đảm về **trạng thái dùng chung, giao dịch, cạnh tranh và độ mới của dữ liệu**. Tách lõi giúp quy tắc dễ kiểm chứng; phần tích hợp vẫn phải được thiết kế theo độ tin cậy cần thiết.

## 10. Tác động đến chất lượng mã nguồn

| Chiều chất lượng | Lợi ích khi tách đúng ranh giới | Rủi ro khi tách sai |
| --- | --- | --- |
| **Khả năng kiểm thử** | Kiểm chứng quy tắc nhanh, ít phụ thuộc môi trường | Quá nhiều fake làm test xác nhận lời gọi thay vì hành vi |
| **Tính đúng đắn** | Có thể tập trung kiểm thử trường hợp biên, bất biến | Bỏ sót hợp đồng I/O, transaction hoặc độ tươi dữ liệu |
| **Khả năng đọc** | Biết chỗ tìm chính sách và chỗ tìm cách đọc/ghi | Phân tán một quy tắc qua quá nhiều lớp khó điều hướng |
| **Khả năng thay đổi** | Thay nguồn dữ liệu, định dạng hay framework ít động tới chính sách | Interface quá tổng quát tạo phụ thuộc và cấu hình phức tạp |
| **Độ tin cậy** | Cô lập lỗi tích hợp, xác định đường xử lý thất bại | Xử lý lỗi bị nuốt hoặc fallback trái quy tắc nghiệp vụ |
| **Hiệu năng** | Có thể đo và tối ưu I/O độc lập với tính toán | Sao chép dữ liệu lớn hoặc thêm tầng không cần thiết |

Không phải số interface hay số lớp càng lớn thì chất lượng càng cao. Tiêu chí thực tế là: **thay đổi một điều có bắt buộc sửa những phần không liên quan không?** Và khi một test lỗi, ta có xác định rõ lớp trách nhiệm cần điều tra không?

## 11. Khi nào nên tách và tách đến mức nào?

### Nên ưu tiên tách khi

- Quy tắc nghiệp vụ có trường hợp biên quan trọng, được sử dụng lại hoặc thay đổi thường xuyên.
- I/O chậm, khó dựng hoặc không ổn định, làm test thường xuyên thất bại vì môi trường.
- Có nhiều adapter: API, batch, công cụ nội bộ cùng sử dụng một chính sách.
- Cần đổi database, framework hoặc nhà cung cấp mà không viết lại quy tắc.
- Mã hiện chứa nhiều phụ thuộc ngầm như thời gian hệ thống, trạng thái global và kết nối tự tạo.
- Một lỗi dữ liệu có thể gây thiệt hại lớn, cần bộ kiểm thử nghiệp vụ nhanh và đủ sâu.

### Có thể giữ đơn giản khi

- Đoạn script có phạm vi nhỏ, vòng đời ngắn, xử lý dữ liệu giả và không có quy tắc nghiệp vụ phức tạp.
- Tách thêm interface chỉ tạo một tầng gọi chuyển tiếp không có ý nghĩa và không cải thiện khả năng kiểm thử hay thay đổi.
- Một đoạn mã chỉ ánh xạ định dạng đầu vào mà không chứa chính sách miền; dùng hàm rõ nghĩa có thể đủ.

Dù chọn ít lớp, vẫn nên đặt **quy tắc quan trọng thành hàm dễ gọi độc lập** khi điều đó giúp xác nhận hành vi. Không nên xây dựng trước một framework adapter tổng quát cho mọi khả năng I/O chưa có nhu cầu.

## 12. Những sai lầm thường gặp

**“Chỉ cần dùng dependency injection là đã tách miền bài toán.”** DI giúp cung cấp phụ thuộc và thay triển khai, nhưng `PricingPolicy` vẫn bị buộc vào HTTP nếu chính nó gọi HTTP hay biết kiểu DTO của thư viện mạng.

**“Có mock thì mọi kiểm thử đều là unit test tốt.”** Mock giúp cô lập, nhưng test quá phụ thuộc thứ tự gọi hoặc chi tiết nội bộ dễ vỡ khi refactor. Hãy xác nhận kết quả và bất biến trước, xác nhận tương tác khi tương tác là hợp đồng cần bảo vệ.

**“Logic miền không được phép có bất kỳ ngoại lệ.”** Có thể ném lỗi miền hoặc `IllegalArgumentException` khi vi phạm bất biến. Mục tiêu là hành vi có thể dự đoán và không phụ thuộc môi trường, không phải cấm cơ chế báo lỗi.

**“Tách I/O là đưa mọi thao tác vào một lớp `Utils`.”** Tên lớp chung không tạo ranh giới rõ. Hợp đồng đọc/ghi nên nêu **ý nghĩa sử dụng** và giới hạn trách nhiệm.

**“Kiểm thử lõi đầy đủ thì không cần integration test.”** Sai. Parse tệp, truy vấn database, mapping JSON, xác thực, transaction, timeout và cấu hình vẫn có thể sai.

**“Logic miền phải biết các exception HTTP để xử lý tốt.”** HTTP 404, 429 hay 503 là thông tin ở ranh giới tích hợp. Adapter hoặc tầng điều phối nên ánh xạ thành kết quả/lỗi thích hợp mà quy tắc nghiệp vụ có thể hiểu. Không biến lỗi “không kết nối được” thành kết luận “không có sản phẩm” nếu chưa có hợp đồng rõ.

**“Pure function nghĩa là không được dùng object hoặc collection.”** Không đúng. Hàm có thể tạo và trả đối tượng mới. Điều cần tránh là thay đổi trạng thái quan sát được ngoài phạm vi hoặc dựa vào yếu tố đầu vào ẩn.

**“Tách giao diện repository luôn làm ứng dụng nhanh hơn.”** Đây chủ yếu là quyết định về phụ thuộc, khả năng kiểm thử và thay đổi. Tác động hiệu năng thực tế phải được đo thay vì suy từ số lớp.

**“Truyền toàn bộ `ApplicationContext` vào miền bài toán cho tiện.”** Điều này làm ẩn phụ thuộc và khó test. Chỉ truyền dữ liệu hoặc hợp đồng mà hành vi thật sự cần.

## 13. Quy trình refactor một phương thức trộn logic và I/O

**Bước 1 — Xác định hợp đồng nghiệp vụ.** Viết quy tắc bằng đầu vào, đầu ra, trường hợp biên và bất biến. Nếu hành vi hiện tại có bug, cần phân biệt việc sửa bug với việc thay đổi cấu trúc.

**Bước 2 — Bảo vệ hành vi quan trọng.** Viết một số kiểm thử hồi quy hoặc ghi ví dụ đầu vào/đầu ra đã được nghiệp vụ xác nhận. Xác định phần nào cần giữ nguyên và phần nào phải sửa vì sai yêu cầu.

**Bước 3 — Tìm các tác dụng phụ.** Đánh dấu việc đọc/ghi file, HTTP, DB, thời gian thực, biến static, log, gửi sự kiện và thao tác ngoài tiến trình.

**Bước 4 — Trích xuất tính toán thuần.** Đưa điều kiện và phép tính vào hàm nhận đủ dữ liệu cần thiết; không để nó tự đọc dữ liệu hoặc lấy cấu hình toàn cục.

**Bước 5 — Đặt hợp đồng tại ranh giới có ý nghĩa.** Nếu cần, định nghĩa khả năng đọc/ghi theo ngôn ngữ use case; đưa chuyển đổi DTO/SQL/tệp vào adapter.

**Bước 6 — Để use case điều phối.** Use case xác định thứ tự các bước, chính sách lỗi và phạm vi transaction; không nhân bản công thức nghiệp vụ ở đây.

**Bước 7 — Kiểm thử theo tầng.** Unit test miền bài toán, test use case bằng fake, integration test từng adapter, rồi một số luồng end-to-end thiết yếu.

**Bước 8 — Kiểm tra thay đổi và chi phí.** Thử giả định “nếu đổi nguồn dữ liệu”, “nếu đổi mức giảm giá”, “nếu API timeout” để xem có cần sửa đúng nơi mong đợi không; loại bỏ các lớp hoặc hợp đồng thừa.

## 14. Bài tập phân tích

### Tình huống A — Lấy giờ hiện tại ngay trong chính sách

Một hàm `isPromotionValid()` gọi `LocalDateTime.now()` rồi quyết định khuyến mãi còn hạn hay không. Test đôi lúc hỏng gần nửa đêm.

**Câu hỏi:** điều gì đang là đầu vào ẩn? Nên tách ở đâu?

**Gợi ý:** thời gian hiện tại là dữ liệu đầu vào. Có thể truyền `Instant` hoặc `LocalDate` theo múi giờ đã xác định vào quy tắc; lớp điều phối lấy thời gian qua `Clock`. Test dùng mốc cố định để kiểm tra đúng ranh giới ngày hết hạn.

### Tình huống B — Mock repository nhưng query sai

Unit test chính sách hoàn tiền dùng fake repository và tất cả đều qua. Triển khai thật trả thiếu giao dịch do câu query lọc sai trạng thái.

**Câu hỏi:** cần bổ sung loại bằng chứng nào?

**Gợi ý:** unit test của miền bài toán không kiểm chứng SQL và mapping. Cần integration test repository với dữ liệu đại diện và hợp đồng truy vấn phù hợp; giữ unit test cho quy tắc hoàn tiền.

### Tình huống C — Quy tắc thanh toán nằm trong HTTP controller

Một controller nhận JSON, kiểm tra ngưỡng thanh toán, tính phí, cập nhật DB và trả JSON. Sau đó hệ thống cần batch xử lý cùng quy tắc.

**Câu hỏi:** phần nào nên tái sử dụng, phần nào khác nhau giữa hai kênh?

**Gợi ý:** trích xuất chính sách tính phí vào lõi, điều phối cập nhật qua use case; HTTP controller và batch adapter chịu trách nhiệm cách nhập/xuất tương ứng. Transaction và chống trùng ở điểm thực thi tác dụng phụ phải được kiểm chứng riêng.

### Tình huống D — Tạo nhiều interface nhưng không dễ kiểm thử hơn

Một nhóm có `CalculatePriceService`, `CalculatePriceServiceImpl`, `PriceCalculatorManager` và `PriceCalculatorFacade`, nhưng tất cả chỉ chuyển cùng tham số đến một phương thức ngắn.

**Câu hỏi:** có cần giữ mọi tầng không?

**Gợi ý:** xem tầng nào thực sự tạo ranh giới giữa quy tắc và I/O, tầng nào có trách nhiệm rõ ràng hoặc lý do thay đổi độc lập. Những tầng chỉ chuyển tiếp mà không cải thiện hợp đồng có thể được đơn giản hóa.

## 15. Checklist khi review khả năng kiểm thử

- **Quy tắc:** có thể gọi trực tiếp logic nghiệp vụ với dữ liệu mẫu mà không dựng database hoặc web framework không?
- **Đầu vào ẩn:** thời gian, biến môi trường, cấu hình global, số ngẫu nhiên hoặc trạng thái static có ảnh hưởng kết quả không?
- **Bất biến:** ranh giới miền có kiểm tra dữ liệu hợp lệ và điều kiện biên không?
- **I/O:** có xác định nơi đọc/ghi, cách parse, timeout, lỗi và hợp đồng tích hợp không?
- **Hướng phụ thuộc:** miền bài toán có bị buộc vào kiểu dữ liệu/framework cụ thể của adapter không?
- **Test:** mỗi trách nhiệm được xác nhận ở đúng cấp độ với bằng chứng phù hợp chưa?
- **Lỗi và giao dịch:** khi đọc, tính hoặc ghi thất bại, dữ liệu/đầu ra rơi vào trạng thái nào?
- **Chi phí:** ranh giới mới giúp sửa độc lập thực tế hay chỉ làm số lượng lớp tăng?
- **Bàn giao:** người tiếp quản có nhận ra đâu là quy tắc nghiệp vụ và đâu là cơ chế triển khai không?

Tách logic miền bài toán khỏi I/O và cơ chế triển khai giúp **kiểm thử nhanh hơn, khoanh vùng lỗi rõ hơn và thay công nghệ với ít ảnh hưởng đến quy tắc hơn**. Việc tách chỉ có giá trị khi những ranh giới phản ánh trách nhiệm thật: lõi bảo vệ điều kiện nghiệp vụ, adapter xử lý hệ thống bên ngoài và use case điều phối hành vi. Đó là nền tảng để mã trong **CODE_QUALITY_FUNDAMENTALS** tiếp tục **đáng tin cậy, dễ hiểu và dễ thay đổi** qua những lần tích hợp và mở rộng.
