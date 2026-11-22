# Kiểm thử theo hành vi thay vì cấu trúc triển khai

Một nhóm thay phương thức `calculateFee()` dài bằng vài hàm nhỏ dễ đọc hơn. Mã trả kết quả y hệt trước đó, nhưng hàng chục kiểm thử thất bại vì chúng kiểm tra tên các hàm nội bộ và số lần từng helper được gọi. Nhóm phải sửa kiểm thử dù không có thay đổi nào về nghiệp vụ. Đây là dấu hiệu **bộ kiểm thử đang phụ thuộc quá nhiều vào cấu trúc triển khai**.

Trong chương **Khả năng kiểm thử** của module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là học cách viết kiểm thử xác nhận **điều hệ thống hứa với bên sử dụng**, giúp mã nguồn đáng tin cậy, dễ hiểu và dễ thay đổi. Kiểm thử nên phát hiện khi hành vi quan trọng bị phá vỡ, đồng thời tiếp tục có giá trị khi mã được tái cấu trúc mà vẫn giữ nguyên hợp đồng.

## 1. “Hành vi” trong một kiểm thử nghĩa là gì?

**Hành vi quan sát được** (*observable behavior*) là kết quả hoặc tác dụng phụ mà bên sử dụng một thành phần được phép dựa vào theo hợp đồng. Nó có thể gồm:

- Giá trị trả về, định dạng dữ liệu và quy tắc tính toán.
- Ngoại lệ hoặc kết quả lỗi được đặc tả khi đầu vào không hợp lệ.
- Trạng thái được lưu hoặc được công bố sau thao tác.
- Tác dụng phụ có ý nghĩa: tạo một đơn hàng, giữ hàng, phát một thông báo được yêu cầu.
- Bất biến và thứ tự có ý nghĩa nghiệp vụ: không thanh toán trước khi xác nhận giữ hàng, không tạo hai đăng ký trùng.

**Chi tiết triển khai** là cách mã đạt kết quả: tên helper `private`, số lượng vòng lặp, việc dùng `for` hay Stream, cách chia lớp nội bộ, gọi cache một hay nhiều lần, hoặc thứ tự gọi hai phép tính độc lập mà hợp đồng không quy định.

| Câu hỏi | Kiểm thử theo hành vi | Kiểm thử bám cấu trúc triển khai |
| --- | --- | --- |
| Đang bảo vệ điều gì? | Kết quả và tác dụng phụ mà người gọi cần | Một cách tổ chức mã hiện tại |
| Khi refactor nhưng giữ nguyên hợp đồng | Thường tiếp tục đạt | Dễ thất bại chỉ vì helper hoặc lời gọi thay đổi |
| Khi mã cho kết quả nghiệp vụ sai | Có cơ sở để phát hiện | Có thể vẫn xanh nếu đúng các lời gọi đã mock |
| Ví dụ | “Đơn đúng ngưỡng 500.000 VND được miễn phí giao thường” | “Hàm `checkThreshold()` được gọi đúng một lần” |
| Độ ổn định mong muốn | Ổn định theo **hợp đồng** | Ổn định theo **cấu trúc mã** |

**Kiểm thử theo hành vi không đồng nghĩa phải đi qua giao diện người dùng hoặc mạng HTTP.** Một unit test gọi phương thức công khai của một lớp tính toán cũng có thể là kiểm thử hành vi, miễn nó kiểm tra kết quả theo quy tắc đã xác nhận. Ngược lại, một end-to-end test vẫn có thể bám quá sát chi tiết HTML hoặc thứ tự request không thuộc hợp đồng.

## 2. Xác định hợp đồng trước khi viết assertion

Trước khi kiểm thử, hãy viết rõ:

1. **Đầu vào hợp lệ:** kiểu, miền giá trị, trạng thái được phép.
2. **Hậu điều kiện thành công:** kết quả nào, thay đổi trạng thái nào phải xảy ra.
3. **Hành vi khi thất bại:** lỗi gì, trạng thái có phải được giữ nguyên không.
4. **Các trường hợp biên:** giá trị ngay dưới, đúng và ngay trên ngưỡng.
5. **Ranh giới quan sát:** người gọi thấy được điều gì và không cần biết điều gì.

**Nguồn của kết quả kỳ vọng** thường là đặc tả nghiệp vụ, hợp đồng API, tiêu chí chấp nhận hoặc ví dụ đã được người phụ trách xác nhận. Nguồn đó được gọi là **test oracle**: căn cứ để kết luận một kết quả là đúng hoặc sai.

Nếu chỉ chạy mã hiện tại để lấy kết quả rồi viết `assertEquals(actual, actual)` hoặc chép kết quả ấy vào `expected`, kiểm thử có thể chỉ ghi lại **một lỗi đang tồn tại**. Kết quả kỳ vọng cần có căn cứ độc lập với phần triển khai được kiểm tra.

Ví dụ, yêu cầu “đơn từ 500.000 đồng được miễn phí vận chuyển” cần được làm rõ: tính trước hay sau giảm giá, áp dụng cho loại giao hàng nào, mốc 500.000 có được tính không. Khi chưa chốt các điểm đó, kiểm thử không thể tự chọn một chính sách rồi gọi mọi cách tính khác là sai.

## 3. Tình huống xuyên suốt: báo giá vận chuyển

Giả sử **chính sách minh họa** đã được xác nhận như sau:

| Mã quy tắc | Điều kiện | Kết quả hoặc bảo đảm |
| --- | --- | --- |
| R1 | Tiền hàng và voucher đều không âm; voucher không vượt tiền hàng | Nếu vi phạm, từ chối yêu cầu |
| R2 | Tiền hàng sau voucher = tiền hàng trước voucher trừ số tiền giảm | Kết quả `payableVnd` phải đúng |
| R3 | Giao **nhanh** | Phí vận chuyển 30.000 VND, không áp dụng miễn phí |
| R4 | Giao **tiêu chuẩn**, khách **thành viên**, `payableVnd >= 500_000` | Phí vận chuyển bằng 0 |
| R5 | Những trường hợp giao tiêu chuẩn còn lại | Phí vận chuyển 15.000 VND |
| R6 | Báo giá thành công | Tổng phải trả bằng tiền hàng sau voucher cộng phí giao hàng |
| R7 | Phép cộng tổng vượt giới hạn `long` | Báo lỗi số học, không xuất ra báo giá sai |

Đây là ví dụ dạy học, chưa xét thuế, hoàn tiền, vùng xa hoặc nhiều loại tiền tệ. Hợp đồng cũng quy định phép tính **không thay đổi dữ liệu đơn hàng hoặc phát sự kiện**.

### 3.1. Cài đặt Java 17 để kiểm thử

Tệp `ShippingQuotes.java`:

```java
package com.example.shipping;

import java.util.Objects;

public final class ShippingQuotes {
    private static final long FREE_THRESHOLD_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 15_000L;
    private static final long EXPRESS_FEE_VND = 30_000L;

    public enum DeliverySpeed { STANDARD, EXPRESS }

    public record Request(
            long merchandiseSubtotalVnd,
            long voucherDiscountVnd,
            boolean member,
            DeliverySpeed speed) {}

    public record Quote(
            long payableVnd,
            long shippingFeeVnd,
            long totalChargeVnd) {}

    private ShippingQuotes() {}

    public static Quote quote(Request request) {
        Objects.requireNonNull(request, "request");
        Objects.requireNonNull(request.speed(), "speed");

        if (request.merchandiseSubtotalVnd() < 0
                || request.voucherDiscountVnd() < 0
                || request.voucherDiscountVnd() > request.merchandiseSubtotalVnd()) {
            throw new IllegalArgumentException("invalid amounts");
        }

        long payableVnd =
                request.merchandiseSubtotalVnd() - request.voucherDiscountVnd();

        long shippingFeeVnd;
        if (request.speed() == DeliverySpeed.EXPRESS) {
            shippingFeeVnd = EXPRESS_FEE_VND;
        } else if (request.member() && payableVnd >= FREE_THRESHOLD_VND) {
            shippingFeeVnd = 0L;
        } else {
            shippingFeeVnd = STANDARD_FEE_VND;
        }

        long totalChargeVnd = Math.addExact(payableVnd, shippingFeeVnd);
        return new Quote(payableVnd, shippingFeeVnd, totalChargeVnd);
    }
}
```

Cấu trúc chương trình có ba nhánh quyết định phí. Nhưng bên gọi `quote(request)` chỉ cần biết **đầu vào**, **giá trị trong `Quote`** và **hành vi lỗi**. Bên gọi không được hứa rằng mã sẽ có đúng ba câu `if` hoặc một phương thức cụ thể mang tên `calculateStandardFee`.

### 3.2. Kiểm thử theo hành vi bằng JUnit 5

Tệp `ShippingQuotesTest.java` ở cùng package. JUnit Jupiter cung cấp `@Test`, `@ParameterizedTest` và `@CsvSource`:

```java
package com.example.shipping;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingQuotesTest {
    @ParameterizedTest
    @CsvSource({
        "STANDARD, true,  499999, 0,      15000",
        "STANDARD, true,  500000, 0,          0",
        "STANDARD, true,  500001, 0,          0",
        "STANDARD, false, 500000, 0,      15000",
        "EXPRESS,  true,  500000, 0,      30000",
        "STANDARD, true,  600000, 100000,     0",
        "STANDARD, true,  600000, 100001, 15000",
        "EXPRESS,  false, 100000, 0,      30000"
    })
    void shippingFeeMatchesConfirmedRules(
            ShippingQuotes.DeliverySpeed speed,
            boolean member,
            long subtotalVnd,
            long discountVnd,
            long expectedShippingFeeVnd) {

        var request = new ShippingQuotes.Request(
                subtotalVnd, discountVnd, member, speed);

        var quote = ShippingQuotes.quote(request);

        long expectedPayableVnd = subtotalVnd - discountVnd;
        assertEquals(expectedPayableVnd, quote.payableVnd());
        assertEquals(expectedShippingFeeVnd, quote.shippingFeeVnd());
        assertEquals(
                expectedPayableVnd + expectedShippingFeeVnd,
                quote.totalChargeVnd());
    }

    @Test
    void rejectsDiscountLargerThanSubtotal() {
        var request = new ShippingQuotes.Request(
                100_000L, 100_001L, true,
                ShippingQuotes.DeliverySpeed.STANDARD);

        assertThrows(IllegalArgumentException.class,
                () -> ShippingQuotes.quote(request));
    }

    @Test
    void rejectsNegativeSubtotalAndNullSpeed() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingQuotes.quote(new ShippingQuotes.Request(
                        -1L, 0L, false,
                        ShippingQuotes.DeliverySpeed.STANDARD)));
        assertThrows(NullPointerException.class,
                () -> ShippingQuotes.quote(new ShippingQuotes.Request(
                        100_000L, 0L, false, null)));
    }

    @Test
    void rejectsOverflowInsteadOfReturningWrongTotal() {
        var request = new ShippingQuotes.Request(
                Long.MAX_VALUE, 0L, false,
                ShippingQuotes.DeliverySpeed.STANDARD);

        assertThrows(ArithmeticException.class,
                () -> ShippingQuotes.quote(request));
    }
}
```

Tập kiểm thử này bảo vệ các quy tắc từ R1 đến R7 trong những trường hợp đã chọn: miễn phí đúng ngưỡng, kết quả hai bên ngưỡng, sự khác biệt thành viên, loại vận chuyển, tác động của voucher, đầu vào sai và tràn số. Những ca này **không chứng minh mọi đầu vào đúng**, nhưng cho thấy cách chuyển yêu cầu thành các ví dụ kiểm chứng có ý nghĩa.

Ở các dòng `assertEquals` về `payableVnd` và `totalChargeVnd`, phép tính giá trị mong đợi được tính đơn giản từ **đặc tả**. Trong những trường hợp CSV được chọn, tổng không tràn `long`. Với logic phức tạp, nên lấy kỳ vọng từ ví dụ độc lập hoặc một mô hình tham chiếu có thể kiểm tra, tránh sao chép toàn bộ thuật toán của mã đang được kiểm thử vào test.

### 3.3. Refactor mà kiểm thử hành vi vẫn có giá trị

Giả sử muốn làm rõ cách tính phí bằng một phương thức riêng và biểu thức `switch`. Có thể thay phần chọn `shippingFeeVnd` trong `quote(...)` bằng:

```java
long shippingFeeVnd = shippingFeeFor(
        request.speed(), request.member(), payableVnd);
```

Và thêm phương thức `private` vào `ShippingQuotes`:

```java
private static long shippingFeeFor(
        DeliverySpeed speed, boolean member, long payableVnd) {

    return switch (speed) {
        case EXPRESS -> EXPRESS_FEE_VND;
        case STANDARD -> (member && payableVnd >= FREE_THRESHOLD_VND)
                ? 0L : STANDARD_FEE_VND;
    };
}
```

Đoạn refactor này dùng `switch expression` của Java 17, giữ nguyên giá trị đầu ra theo các quy tắc đã nêu. **Bộ kiểm thử ở phần 3.2 không cần biết helper mới tồn tại**, nên tiếp tục dùng được. Nếu refactor lỡ đổi dấu `>=` thành `>`, kiểm thử đúng ngưỡng 500.000 VND có cơ sở để phát hiện hồi quy.

Điều quan trọng không phải đảm bảo mọi refactor sẽ làm test xanh. Khi refactor vô ý thay đổi hành vi, test **nên thất bại**. Khả năng kiểm thử tốt thể hiện ở việc test thất bại vì **hợp đồng bị phá**, không chỉ vì số lượng helper thay đổi.

## 4. Những kiểm thử bám cấu trúc dễ gây báo động giả

Các ví dụ sau là **mẫu tư duy cần tránh**, không phải đề xuất viết kiểm thử như vậy:

### 4.1. Kiểm tra sự tồn tại của helper nội bộ

```java
// Anti-pattern: chỉ kiểm tra tên một helper private.
assertNotNull(ShippingQuotes.class.getDeclaredMethod(
        "shippingFeeFor",
        ShippingQuotes.DeliverySpeed.class,
        boolean.class,
        long.class));
```

Lệnh phản chiếu (*reflection*) có thể báo lỗi khi `shippingFeeFor` được đổi tên hoặc tính trực tiếp trong `quote(...)`, dù kết quả báo giá không đổi. Nếu `shippingFeeFor` không phải API công khai được hứa với người gọi, tên của nó không nên là điều kiện nghiệm thu nghiệp vụ.

### 4.2. Chỉ xác nhận lời gọi đến mock

```java
// Ví dụ ý tưởng với Mockito, không phải một test hoàn chỉnh:
verify(calculator).calculateBaseFee(any());
verify(discountPolicy).checkMembership(any());
```

Hai lời gọi trên có thể diễn ra đúng như kỳ vọng mà tổng tiền vẫn sai. Ngược lại, refactor gộp các phép tính có thể làm cả hai verification thất bại dù kết quả đúng. Nếu **hợp đồng không yêu cầu** gọi đúng các phương thức nội bộ ấy, nên kiểm tra giá trị báo giá thay vì tương tác chi tiết.

### 4.3. Đóng băng toàn bộ cấu trúc biểu diễn

Kiểm thử so sánh snapshot của toàn bộ JSON, HTML, đối tượng nội bộ hoặc log có thể thất bại khi một thuộc tính trình bày không liên quan thay đổi. Snapshot **không tự xấu**: nếu cấu trúc JSON công khai chính là hợp đồng của API, kiểm tra tên field và kiểu dữ liệu là hợp lý. Vấn đề là snapshot quá rộng khiến mỗi thay đổi vô hại đều trở thành điều kiện phải duyệt lại mà không có giải thích nghiệp vụ.

### 4.4. Mock từng bước đến mức test lặp lại chính mã sản xuất

Một test tạo mock cho từng helper, chỉ định thứ tự gọi và trả lại chính kết quả đã được lập trình sẵn thường ít kiểm tra được phép tính thật. Nó có thể chứng minh “các mock hoạt động theo kịch bản”, thay vì “hệ thống thỏa yêu cầu”. Khi có thể, hãy cho **đoạn logic thuộc phạm vi kiểm thử chạy thật** và chỉ thay các phụ thuộc bên ngoài khó kiểm soát như mạng, thời gian hoặc cơ sở dữ liệu.

## 5. Phân biệt hành vi cục bộ và hành vi có tác dụng phụ

Với **phép tính thuần**, đầu vào và đầu ra là ranh giới thuận tiện để kiểm thử. Với **thao tác cập nhật trạng thái**, hành vi có thể bao gồm trạng thái sau lời gọi, yêu cầu từ chối và khả năng gọi lại.

Xét dịch vụ đăng ký học viên cho một khóa học. Hợp đồng minh họa:

- `studentId` và `courseId` phải dương.
- Nếu chưa có đăng ký của cặp học viên/khóa học, tạo một đăng ký và trả `CREATED`.
- Nếu đã có, giữ nguyên tập đăng ký và trả `ALREADY_ENROLLED`.
- Không được tạo hai bản ghi cho cùng một cặp.

### 5.1. Use case diễn đạt hợp đồng ở ranh giới

Tệp `EnrollmentService.java`, Java 17:

```java
package com.example.enrollment;

import java.util.Objects;

public final class EnrollmentService {
    public record Key(long studentId, long courseId) {}

    public enum Result { CREATED, ALREADY_ENROLLED }

    public interface EnrollmentStore {
        // Trả true khi cặp này lần đầu được ghi nhận.
        boolean addIfAbsent(Key key);
    }

    private final EnrollmentStore store;

    public EnrollmentService(EnrollmentStore store) {
        this.store = Objects.requireNonNull(store, "store");
    }

    public Result enroll(long studentId, long courseId) {
        if (studentId <= 0 || courseId <= 0) {
            throw new IllegalArgumentException("ids must be positive");
        }

        return store.addIfAbsent(new Key(studentId, courseId))
                ? Result.CREATED
                : Result.ALREADY_ENROLLED;
    }
}
```

Ở đây hành vi nghiệp vụ gồm **kết quả trả về** và **trạng thái đăng ký được ghi nhận**. Giao diện `addIfAbsent` diễn đạt tính duy nhất ở hợp đồng lưu trữ, thay vì để use case tự kiểm tra tồn tại rồi thêm trong hai bước không nguyên tử.

### 5.2. Kiểm thử trạng thái bằng một fake in-memory

Tệp `EnrollmentServiceTest.java`:

```java
package com.example.enrollment;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class EnrollmentServiceTest {
    static final class InMemoryStore
            implements EnrollmentService.EnrollmentStore {
        final Set<EnrollmentService.Key> entries = new HashSet<>();

        @Override
        public boolean addIfAbsent(EnrollmentService.Key key) {
            return entries.add(key);
        }
    }

    @Test
    void createsOneEnrollmentForRepeatedRequest() {
        InMemoryStore store = new InMemoryStore();
        EnrollmentService service = new EnrollmentService(store);

        assertEquals(EnrollmentService.Result.CREATED,
                service.enroll(7, 42));
        assertEquals(EnrollmentService.Result.ALREADY_ENROLLED,
                service.enroll(7, 42));

        assertEquals(Set.of(new EnrollmentService.Key(7, 42)),
                store.entries);
    }

    @Test
    void rejectsInvalidIdWithoutCreatingEnrollment() {
        InMemoryStore store = new InMemoryStore();
        EnrollmentService service = new EnrollmentService(store);

        assertThrows(IllegalArgumentException.class,
                () -> service.enroll(0, 42));

        assertEquals(Set.of(), store.entries);
    }
}
```

Kiểm thử xác nhận **đăng ký được tạo đúng một lần và không tạo dữ liệu khi đầu vào sai**. Nó không nhất thiết quan tâm `EnrollmentService` có gọi một helper `validate()`, dùng một hay hai câu `if`.

**Giới hạn rất quan trọng:** `HashSet` ở fake không phải bộ lưu trữ an toàn khi nhiều luồng cùng cập nhật. Hai kiểm thử trên xác nhận hành vi **đơn luồng** của use case với fake. Muốn bảo đảm không có bản ghi trùng ở môi trường nhiều request, triển khai `EnrollmentStore` thật cần ràng buộc duy nhất, thao tác ghi nguyên tử/giao dịch phù hợp và kiểm thử tích hợp có tranh chấp. Một fake đúng trong unit test không tự chứng minh adapter thật giữ hợp đồng.

## 6. Khi nào kiểm tra tương tác với phụ thuộc là hợp lý?

Không có quy tắc “mọi `verify(...)` đều sai”. Với một use case điều phối, việc yêu cầu **gửi đúng một thông báo xác nhận**, **không yêu cầu thanh toán khi giữ hàng thất bại** hoặc **không gọi API thanh toán lần hai cho cùng một giao dịch** có thể là hành vi công khai của hệ thống. Trong unit test, cách duy nhất quan sát hành vi đó có thể là ghi lại thao tác gửi ra một **port** rồi kiểm tra.

Phân biệt:

| Tương tác được kiểm tra | Có phải hợp đồng? | Cách đánh giá |
| --- | --- | --- |
| Gọi `private calculateFee()` đúng một lần | Thường không | Kiểm tra kết quả tính phí |
| Gọi phương thức cache nội bộ đúng một lần | Chỉ khi có yêu cầu định lượng về cache/hiệu năng | Dùng phép đo hoặc thử nghiệm phù hợp với yêu cầu |
| Không gửi lệnh thu tiền nếu đơn không hợp lệ | Có thể là hành vi quan trọng | Kiểm tra port thanh toán không nhận lệnh |
| Phát một thông báo cho đơn đã xác nhận | Có thể là cam kết nghiệp vụ | Dùng recording fake và kiểm tra nội dung thông báo |
| Sử dụng đúng một lần retry đến dịch vụ ngoài | Chỉ khi chính sách retry là hợp đồng cần bảo đảm | Kiểm tra retry, idempotency và tình huống lỗi trong test thích hợp |

Khi dùng mock, ưu tiên mock **ranh giới giữa phần đang kiểm thử và hệ thống ngoài** (gateway, clock, publisher, repository) hơn là từng phương thức nội bộ. Dữ liệu do mock trả cần thể hiện một tình huống có ý nghĩa: thanh toán bị từ chối, hết hàng, timeout, v.v. Sau đó kiểm tra quyết định cuối cùng mà use case đưa ra.

Ví dụ một yêu cầu hợp lý: “khi xác nhận đơn thất bại trước khi thu tiền, không có yêu cầu thanh toán nào được gửi đi”. Một recording fake có thể lưu `paymentRequests` để kiểm tra danh sách này rỗng. Điều cần bảo vệ là **không phát sinh tác dụng phụ thanh toán**, chứ không phải tên phương thức nội bộ dùng để chuyển trạng thái đơn.

## 7. Chọn cấp kiểm thử phù hợp với ranh giới hành vi

Không có một loại kiểm thử nào đủ để bảo vệ toàn bộ hệ thống:

| Cấp kiểm thử | Ranh giới có thể quan sát | Dùng để xác nhận | Giới hạn |
| --- | --- | --- | --- |
| **Unit test tính toán** | Phương thức hoặc đối tượng công khai | Quy tắc, giá trị biên, đầu vào sai | Không xác nhận adapter, DB hoặc mạng |
| **Unit test use case** | Lời gọi nghiệp vụ và port giả | Quyết định, trạng thái logic, lời gọi ra biên theo hợp đồng | Fake có thể không giống đặc tính thực của adapter |
| **Contract test** | Giao diện giữa các thành phần | Schema, mã lỗi, ý nghĩa phản hồi, tương thích | Không chứng minh toàn luồng hoạt động trên hạ tầng |
| **Integration test** | Tương tác thật với DB, hàng đợi, gateway thử nghiệm | Giao dịch, truy vấn, mapping, cấu hình và lỗi tích hợp | Chậm hơn và cần môi trường kiểm soát |
| **End-to-end test** | Kết quả của luồng nghiệp vụ | Các bước kết nối đúng, hành vi người dùng quan sát được | Khó khoanh vùng lỗi, dễ bất ổn nếu phụ thuộc môi trường ngoài |

Một tổ chức thường dùng nhiều unit test cho quy tắc, ít integration test hơn cho biên hạ tầng, và một số end-to-end test cho luồng quan trọng. Đó là **nguyên tắc cân bằng chi phí và độ tin cậy**, không phải một tỷ lệ số lượng bắt buộc.

**Ranh giới hành vi phụ thuộc người sử dụng:** tên field JSON là chi tiết quan trọng đối với client API, dù nó chỉ là cách biểu diễn trong bộ nhớ của server. Thay đổi tên một private helper là refactor nội bộ; thay tên field công khai có thể là thay đổi hợp đồng và test đúng là phải báo lỗi.

## 8. Thiết kế dữ liệu kiểm thử từ quy tắc

Thay vì viết một test cho từng dòng mã, hãy bắt đầu từ **phân hoạch đầu vào và bảng quyết định**:

| Kỹ thuật | Cách dùng | Ví dụ |
| --- | --- | --- |
| Phân lớp tương đương | Chọn đại diện cho các nhóm kết quả tương đương | Thành viên và không thành viên; giao nhanh/tiêu chuẩn |
| Giá trị biên | Thử ngay dưới, đúng và ngay trên mốc | 499.999, 500.000, 500.001 VND |
| Bảng quyết định | Liệt kê điều kiện kết hợp ảnh hưởng kết quả | Thành viên × loại giao × mức thanh toán |
| Chuyển trạng thái | Thử thứ tự hành động và trạng thái hợp lệ | `CREATED → PAID → REFUNDED` |
| Kiểm thử thuộc tính (*property-based*) | Kiểm tra một bất biến trên nhiều đầu vào sinh tự động | Phí giao hàng không âm; tổng bằng tiền hàng sau giảm cộng phí |
| Kiểm thử biến đổi (*metamorphic*) | So kết quả giữa hai đầu vào có quan hệ đã biết | Với đơn đủ điều kiện miễn giao tiêu chuẩn, tăng tiền hàng hợp lệ không làm mất điều kiện miễn |

Ví dụ về một **bất biến hành vi** cho báo giá hợp lệ:

```text
quote.payableVnd >= 0
quote.shippingFeeVnd ∈ {0, 15000, 30000}
quote.totalChargeVnd = quote.payableVnd + quote.shippingFeeVnd
```

Bất biến chỉ áp dụng khi đầu vào hợp lệ và phép cộng biểu diễn được bằng `long`. Với kiểm thử sinh dữ liệu, phải ràng buộc miền này hoặc kiểm tra đúng hành vi `ArithmeticException` khi vượt miền.

Một quan hệ biến đổi cần có phạm vi: tăng số tiền hàng của **khách thành viên, giao tiêu chuẩn**, không thay voucher, sau khi đã vượt ngưỡng 500.000 VND sẽ giữ phí vận chuyển bằng 0, miễn tổng còn biểu diễn được. Không nên phát biểu “tăng tiền hàng không bao giờ đổi phí” cho mọi chính sách hoặc mọi hình thức giao hàng khi chưa có đặc tả tương ứng.

### 8.1. Đặt tên kiểm thử theo tình huống và kết quả

Tên như `calculatesCorrectly()` hoặc `testMethod1()` không giải thích được quy tắc. Nên dùng tên thể hiện **điều kiện → kết quả**:

```text
memberWithExactlyThresholdGetsFreeStandardShipping
expressShippingNeverUsesMemberFreeShippingBenefit
invalidVoucherIsRejected
repeatedEnrollmentDoesNotCreateDuplicate
paymentRejectionDoesNotChangeOrderToPaid
```

Một test có tên rõ giúp người review hiểu ngay *vì sao* test cần tồn tại, và khi thất bại có thể liên hệ về quy tắc nào.

### 8.2. Arrange–Act–Assert giúp tách mục tiêu kiểm thử

```text
Arrange: chuẩn bị dữ liệu và trạng thái đủ để tạo tình huống.
Act:     gọi một thao tác chính qua ranh giới được kiểm thử.
Assert:  kiểm tra kết quả, lỗi và tác dụng phụ thuộc hợp đồng.
```

Không nhất thiết ép đúng ba khối mã hoặc chỉ một assertion. Một thao tác trả `Quote` có ba thuộc tính liên quan nhau; kiểm tra cả ba là hợp lý nếu chúng cùng mô tả **một hành vi báo giá**. Vấn đề là tập trung vào một kịch bản dễ hiểu, không ghép nhiều luồng không liên quan khiến nguyên nhân thất bại khó nhận biết.

## 9. Khả năng kiểm thử phụ thuộc vào thiết kế, nhưng không cần thiết kế chỉ vì mock

Một thiết kế dễ kiểm thử thường có:

- **Đầu vào và kết quả rõ:** không phải tìm cấu hình ngầm hoặc biến toàn cục để hiểu kết quả.
- **Tác dụng phụ được khoanh vùng:** quy tắc tính tiền tách khỏi nơi ghi DB hoặc gọi mạng khi trách nhiệm cho phép.
- **Phụ thuộc kiểm soát được:** `Clock`, dịch vụ gửi thông báo hoặc kho lưu trữ có thể được cung cấp vào thành phần cần chúng.
- **Trạng thái và thời gian quan sát được:** có thể xác nhận hệ thống đã đạt trạng thái đúng, không phải đoán bằng `Thread.sleep(...)`.
- **Hợp đồng đường lỗi:** biết khi ngoại lệ xuất hiện, thay đổi nào đã xảy ra.

Ví dụ với thời gian: thay vì gọi `LocalDate.now()` trong nhiều nhánh nghiệp vụ, có thể truyền `Clock` vào thành phần cần xác định “hôm nay”. Kiểm thử cung cấp `Clock.fixed(...)` để kiểm tra ngày cuối hạn ổn định. **Thời gian vẫn là đầu vào nghiệp vụ**, nhưng không cần phụ thuộc đồng hồ thực tại thời điểm chạy test.

Tương tự, tách chức năng tính giá thành một phép tính thuần có thể làm việc kiểm thử các trường hợp biên dễ dàng. Tuy nhiên, tạo interface và mock cho mọi lớp, kể cả các phép tính thuần không có phụ thuộc, lại khiến mã và kiểm thử khó đọc hơn. Hãy đưa vào điểm thay thế khi nó **bảo vệ ranh giới có ý nghĩa**.

## 10. Những ngộ nhận thường gặp

| Ngộ nhận | Hệ quả | Cách nhìn phù hợp |
| --- | --- | --- |
| “Kiểm thử hành vi phải chạy từ UI.” | Test chậm và khó xác định lỗi cho mọi quy tắc nhỏ | Gọi ranh giới phù hợp: public method, use case, API hoặc UI |
| “Không được kiểm tra tương tác với mock.” | Bỏ sót side effect thuộc hợp đồng như không thu tiền khi lỗi | Kiểm tra tác dụng phụ qua port khi nó là nghĩa vụ rõ ràng |
| “Mọi helper private đều cần test riêng.” | Khóa cứng cấu trúc và tăng chi phí refactor | Kiểm tra thông qua hành vi của đơn vị sở hữu helper |
| “Chỉ cần test xanh là mã đúng.” | Test oracle có thể sai hoặc thiếu ca biên | Truy vết kỳ vọng về đặc tả độc lập |
| “Coverage cao chứng minh chất lượng.” | Phủ dòng nhưng bỏ sót quyết định nghiệp vụ | Xem chất lượng assertion, phân hoạch dữ liệu và đường lỗi |
| “Snapshot càng lớn càng tốt.” | Báo động giả khi chi tiết không thuộc hợp đồng đổi | Snapshot có chọn lọc và xác nhận trường công khai quan trọng |
| “Mock DB chứng minh transaction thật.” | Fake không phản ánh isolation, constraint, commit | Thêm integration test tại ranh giới lưu trữ |
| “Refactor thì tất cả test luôn phải xanh.” | Bỏ qua thay đổi hành vi vô ý | Test phải thất bại khi hợp đồng bị vi phạm |
| “Test có `Thread.sleep` là kiểm thử thực tế.” | Phụ thuộc timing gây flaky test | Dùng đồng hồ điều khiển được, đồng bộ sự kiện và điều kiện quan sát được |

## 11. Quy trình chuyển một bộ test bám triển khai sang kiểm thử hành vi

Giả sử một pull request đổi các helper nội bộ khiến hàng chục unit test thất bại, nhưng chưa có bằng chứng hành vi thay đổi. Không nên xóa test hàng loạt. Có thể làm theo quy trình:

1. **Liệt kê các test thất bại và quy tắc mỗi test muốn bảo vệ.** Nếu không giải thích được quy tắc, xem lại mục đích tồn tại của test.
2. **Phân loại assertion.** Nó đang xác nhận output/trạng thái/side effect theo hợp đồng hay tên lớp, thứ tự helper, số lần gọi nội bộ?
3. **Tìm oracle độc lập.** Đối chiếu yêu cầu, ví dụ biên và hợp đồng đã được xác nhận; sửa test nếu kỳ vọng cũ dựa vào một nhầm lẫn.
4. **Chọn ranh giới quan sát thích hợp.** Với tính toán dùng public method; với nghiệp vụ có I/O dùng trạng thái hoặc recording fake ở port; với schema dùng contract test.
5. **Bảo toàn những kiểm thử quan trọng.** Giữ ca biên, từ chối đầu vào, trạng thái sau lỗi và tác dụng phụ quan trọng trước khi sửa cách viết assertion.
6. **Thực hiện refactor nhỏ và chạy kiểm thử liên quan.** Nếu test thất bại, xác định hợp đồng bị phá hay test đang lệ thuộc cấu trúc; bổ sung integration test khi phụ thuộc thật là nơi có rủi ro.
7. **Review tính dễ hiểu của test.** Người khác có thể đọc tên, đầu vào, kết quả mong đợi và biết nó bảo vệ quy tắc nào mà không đọc mã sản xuất không?

### Mẫu ghi nhận một kiểm thử hữu ích

```text
Hành vi: Thành viên giao tiêu chuẩn được miễn phí khi
         tiền hàng sau voucher đạt đúng 500.000 VND.

Nguồn kỳ vọng: Quy tắc R4 đã được chốt.
Arrange: subtotal=600.000, voucher=100.000,
         member=true, speed=STANDARD.
Act:     ShippingQuotes.quote(request).
Assert:  payable=500.000, shippingFee=0, total=500.000.

Không phụ thuộc: số helper, số if, tên biến nội bộ.
```

Bản ghi này giúp người viết và người review thấy vì sao test cần tồn tại. Nếu sau này đổi cấu trúc tính phí, test vẫn là tài liệu sống cho **hành vi đã cam kết**.

## 12. Bài tập vận dụng

**Tình huống:** một hệ thống hoàn tiền có quy tắc được xác nhận:

- Khách chỉ có thể hoàn tiền cho đơn đã thanh toán.
- Giá trị hoàn là số dương và không vượt số tiền còn được phép hoàn của đơn.
- Khi thành công, số tiền đã hoàn cộng dồn tăng đúng mức yêu cầu; trạng thái đơn được cập nhật theo chính sách.
- Yêu cầu trùng `refundRequestId` không tạo khoản hoàn thứ hai.
- Nếu cổng thanh toán trả kết quả chưa rõ, hệ thống ghi trạng thái chờ đối soát, không tự khẳng định thất bại.

Bộ test cũ kiểm tra rằng `RefundService` gọi `validateAmount()`, `calculateRefundable()`, `saveRefund()` theo đúng thứ tự. Khi refactor, ba helper được thay bằng một đối tượng chính sách mới và test đồng loạt thất bại.

**Yêu cầu:**

1. Viết ít nhất **sáu ca kiểm thử hành vi**, gồm hoàn thành công, số tiền bằng 0, vượt hạn mức, đơn chưa thanh toán, request ID trùng và phản hồi cổng thanh toán chưa rõ.
2. Với từng ca, xác định **đầu vào, trạng thái ban đầu, kết quả mong đợi và trạng thái sau thao tác**.
3. Chỉ ra những kiểm thử có thể chạy bằng fake và những kiểm thử cần tích hợp với DB/cổng thanh toán giả lập để xác nhận tính nguyên tử hoặc idempotency.
4. Phân biệt hai loại tương tác: “gọi helper `calculateRefundable()` đúng một lần” và “không gửi thêm lệnh hoàn tiền lần hai”. Loại nào là hành vi cần bảo vệ, vì sao?
5. Nếu sửa cách lưu hoàn tiền từ một bảng sang hai bảng nhưng API và trạng thái nghiệp vụ giữ nguyên, hãy nêu test nào nên giữ nguyên, test nào phải cập nhật và test mới nào cần bổ sung.

**Gợi ý tự đối chiếu:** các test hành vi phải chứng minh số tiền hoàn và trạng thái không bị thay đổi trái quy tắc. Yêu cầu cùng `refundRequestId` không được phát sinh lần hoàn thứ hai là hợp đồng, cần kiểm tra bằng trạng thái hoặc dấu vết ở cổng thanh toán. Số lần gọi helper nội bộ không phải điều kiện nghiệm thu. Test tích hợp vẫn cần để bảo đảm transaction, unique constraint và cạnh tranh đồng thời; một fake trả kết quả như mong muốn không tự chứng minh cơ sở dữ liệu làm được điều đó.

## 13. Ghi nhớ

- **Kiểm thử điều hệ thống hứa**, gồm đầu ra, lỗi, trạng thái và tác dụng phụ quan trọng; không khóa cứng cách chia helper nội bộ.
- **Lấy kỳ vọng từ hợp đồng**, tránh sao chép kết quả của mã hiện tại để tự xác nhận chính nó.
- **Dùng ca biên và bảng quyết định** để kiểm tra quy tắc nghiệp vụ, thêm kiểm thử bất biến khi phù hợp.
- **Mock hoặc fake tại ranh giới có ý nghĩa**, và kiểm chứng adapter thật ở cấp tích hợp khi cần.
- **Phân biệt refactor với thay đổi hành vi**: giữ nguyên hợp đồng thì kiểm thử nên ổn định; vi phạm hợp đồng thì kiểm thử phải phát hiện.

Một bộ kiểm thử tốt cho phép người phát triển thay cấu trúc mã với sự tự tin có căn cứ. Giá trị của nó nằm ở khả năng trả lời rõ ràng: **khi nào phần mềm làm đúng điều đã hứa, và thay đổi nào sẽ phá vỡ lời hứa ấy?**
