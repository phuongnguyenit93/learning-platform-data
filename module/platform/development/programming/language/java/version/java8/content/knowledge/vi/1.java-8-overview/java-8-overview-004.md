# Giữ hợp đồng API khi thay đổi cách triển khai (Java 8)

## Mục tiêu và nguyên tắc

Đổi thuật toán, cấu trúc dữ liệu, thư viện hay cách truy xuất dữ liệu có thể giúp code dễ bảo trì và hiệu quả hơn. Nhưng chương trình **gọi** API phải tiếp tục sử dụng được API và nhận đúng những hành vi đã cam kết. Đây là yêu cầu cốt lõi khi refactor và nâng cấp hệ thống.

Trong bài này, bạn sẽ biết cách: xác định API contract, phân biệt phần công khai và chi tiết nội bộ, giữ tương thích qua `interface`/functional interface của Java 8, dùng contract test để so sánh các implementation, và kiểm soát breaking change.

> **Nguyên tắc:** Client phụ thuộc vào *hợp đồng* (contract), không phụ thuộc vào *cách thực thi* (implementation). Đổi implementation thành công chỉ khi những đảm bảo công khai quan trọng vẫn được giữ.

## 1. Hợp đồng API thực sự bao gồm gì?

Đối với Java API, một contract không chỉ là chữ ký phương thức. Nó còn gồm hành vi mà caller có quyền kỳ vọng.

| Khía cạnh | Điều cần bảo toàn | Ví dụ |
| --- | --- | --- |
| Chữ ký | Tên, visibility, kiểu tham số/trả về, cấu trúc công khai | `total(List<Line>)` tiếp tục trả `BigDecimal`. |
| Ngữ nghĩa | Kết quả, điều kiện lọc, thứ tự, quy tắc làm tròn | Cùng giỏ hàng có cùng tổng tiền. |
| Biên dữ liệu | `null`, rỗng, dữ liệu sai, số âm | Giỏ rỗng trả 0. |
| Lỗi | Điều kiện lỗi và kiểu exception được công bố | Giá âm ném `IllegalArgumentException`. |
| Tác dụng phụ | Input có bị thay đổi, trạng thái có được cập nhật hay không | Phép tính không sửa danh sách đầu vào. |
| Vận hành | Tính đồng thời, consistency, bảo mật hoặc SLO đã cam kết | Không rò dữ liệu qua cache giữa các principal. |
| Giao thức (nếu có) | HTTP status, JSON schema, event payload, mã lỗi | Client HTTP vẫn đọc được cùng schema. |

**Cùng chữ ký không đủ.** Nếu `total(...)` trước đây chấp nhận `null`, sau refactor lại ném exception, đây là thay đổi hành vi dù compiler không báo lỗi. Tương tự, đổi thứ tự trả về hoặc đổi quy tắc làm tròn có thể làm hỏng client.

- **Public API:** interface, public method, DTO, endpoint hoặc sự kiện mà client sử dụng và quan sát.
- **Implementation:** vòng lặp, Stream, repository, class nội bộ, thuật toán, cache, adapter hoặc thư viện phía sau API.
- **Published contract:** những điều đã hứa qua tài liệu, JavaDoc, schema và test. Đừng coi mọi chi tiết tình cờ của implementation cũ là cam kết bắt buộc.

## 2. Phân biệt thay đổi tương thích và breaking change

| Thay đổi | Nhận định |
| --- | --- |
| Thay vòng lặp bằng Stream nhưng giữ input/output, lỗi, thứ tự và side effect đã hứa | Có thể tương thích. |
| Chuyển từ repository cũ sang repository mới, giữ dữ liệu và chính sách consistency | Có thể tương thích. |
| Xóa, đổi tên public method hoặc thay tham số/return type | Thường phá vỡ source và có thể phá binary compatibility. |
| Giữ chữ ký nhưng đổi xử lý `null` hoặc exception | Breaking change về hành vi nếu đã có cam kết. |
| Đổi từ danh sách có thứ tự sang thứ tự không xác định | Breaking change nếu thứ tự được cam kết. |
| Thêm abstract method vào interface có implementer bên ngoài | Rủi ro lớn; implementer hiện có không có method khi được gọi. |
| Thêm `default method` của Java 8 | Có thể giúp mở rộng nhưng vẫn phải kiểm tra xung đột tên/default. |
| Dùng `double` thay `BigDecimal` cho tiền | Rủi ro thay đổi tính chính xác và semantics. |

Nên coi việc "có thể tương thích" là giả thuyết cần chứng minh bằng test, không phải sự bảo đảm chỉ từ việc code mới chạy.

## 3. Java 8: ổn định interface, thay implementation

Java 8 vẫn đóng vai trò quan trọng trong cách viết Java hiện đại với `interface`, lambda, method reference, `@FunctionalInterface` và Stream. Ví dụ này dùng **hai implementation** cho cùng một contract tính tiền: cách cũ dùng `for`, cách mới dùng Stream.

**Hợp đồng `TotalCalculator.total(lines)`:**

1. Tổng bằng `price × quantity` của từng dòng, dùng `BigDecimal`.
2. Danh sách rỗng trả tổng 0; không làm thay đổi input.
3. `lines == null` hoặc một phần tử `null` gây `NullPointerException`.
4. Giá hoặc số lượng âm gây `IllegalArgumentException`.
5. Cùng dữ liệu hợp lệ cho cùng giá trị số; caller không phải biết thuật toán.

### Ví dụ Java hoàn chỉnh

Lưu file **`ApiContractDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class ApiContractDemo {
    static final class Line {
        final BigDecimal price;
        final int quantity;

        Line(String price, int quantity) {
            this.price = new BigDecimal(price);
            this.quantity = quantity;
        }
    }

    @FunctionalInterface
    interface TotalCalculator {
        BigDecimal total(List<Line> lines);
    }

    private static BigDecimal lineTotal(Line line) {
        Objects.requireNonNull(line, "line");
        if (line.price.signum() < 0 || line.quantity < 0) {
            throw new IllegalArgumentException("negative price or quantity");
        }
        return line.price.multiply(BigDecimal.valueOf(line.quantity));
    }

    // Implementation cũ: vòng lặp.
    static final class LoopCalculator implements TotalCalculator {
        @Override
        public BigDecimal total(List<Line> lines) {
            Objects.requireNonNull(lines, "lines");
            BigDecimal result = BigDecimal.ZERO;
            for (Line line : lines) {
                result = result.add(lineTotal(line));
            }
            return result;
        }
    }

    // Implementation mới: Stream (Java 8).
    static final class StreamCalculator implements TotalCalculator {
        @Override
        public BigDecimal total(List<Line> lines) {
            Objects.requireNonNull(lines, "lines");
            return lines.stream()
                    .map(ApiContractDemo::lineTotal)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
        }
    }

    // Caller chỉ phụ thuộc TotalCalculator.
    static final class CheckoutService {
        private final TotalCalculator calculator;

        CheckoutService(TotalCalculator calculator) {
            this.calculator = Objects.requireNonNull(calculator, "calculator");
        }

        BigDecimal checkout(List<Line> lines) {
            return calculator.total(lines);
        }
    }

    // Test qua interface, dùng lại cho cả hai implementation.
    static void verifyContract(TotalCalculator calculator) {
        List<Line> cart = Arrays.asList(
                new Line("12.50", 2),
                new Line("2.00", 3)
        );

        if (calculator.total(cart)
                .compareTo(new BigDecimal("31.00")) != 0) {
            throw new AssertionError("wrong total");
        }

        if (calculator.total(Collections.emptyList())
                .compareTo(BigDecimal.ZERO) != 0) {
            throw new AssertionError("empty input must return zero");
        }

        try {
            calculator.total(Arrays.asList(new Line("-1.00", 1)));
            throw new AssertionError("negative price accepted");
        } catch (IllegalArgumentException expected) {
            // Đúng kiểu lỗi theo contract.
        }

        try {
            calculator.total(null);
            throw new AssertionError("null input accepted");
        } catch (NullPointerException expected) {
            // Đúng kiểu lỗi theo contract.
        }
    }

    public static void main(String[] args) {
        TotalCalculator before = new LoopCalculator();
        TotalCalculator after = new StreamCalculator();

        verifyContract(before);
        verifyContract(after);

        List<Line> cart = Arrays.asList(
                new Line("12.50", 2),
                new Line("2.00", 3)
        );
        System.out.println("Loop: "
                + new CheckoutService(before).checkout(cart));
        System.out.println("Stream: "
                + new CheckoutService(after).checkout(cart));
        System.out.println("Contract: PASS");
    }
}
```

Biên dịch và chạy bằng JDK 17+ (ví dụ chỉ dùng API đã tồn tại từ Java 8):

```bash
javac ApiContractDemo.java
java ApiContractDemo
```

Stdout:

```text
Loop: 31.00
Stream: 31.00
Contract: PASS
```

**Vì sao contract được giữ?** `CheckoutService` vẫn gọi `calculator.total(lines)`, không biết hoặc phụ thuộc loại implementation. Cả hai cách cộng đều giữ kết quả, validation, kiểu exception, hành vi với danh sách rỗng và không sửa `cart`. Hàm `lineTotal` thống nhất kiểm tra phần tử; `BigDecimal` phù hợp để biểu diễn giá trị thập phân chính xác trong phép cộng/nhân ở ví dụ.

`verifyContract` mô phỏng **contract test dùng chung**. Trong dự án thật, hãy đưa nó vào JUnit 5, bổ sung dữ liệu lớn, phần tử null, số lượng âm, trạng thái đồng thời, tác dụng phụ, quy tắc làm tròn và các trường hợp theo yêu cầu nghiệp vụ. Ví dụ trên chưa quy định thuế, tiền tệ, chiết khấu hay scale của kết quả; API thanh toán thực tế cần đặc tả những chính sách đó.

### Lambda và method reference

Do `TotalCalculator` chỉ có một abstract method, có thể tạo implementation bằng Java 8 lambda/method reference (các dòng sau đặt trong phạm vi `ApiContractDemo`):

```java
TotalCalculator viaReference = new StreamCalculator()::total;
TotalCalculator viaLambda = lines -> new LoopCalculator().total(lines);
```

`@FunctionalInterface` giúp compiler phát hiện việc vô tình thêm abstract method làm lambda của client không còn phù hợp. Trong ứng dụng, có thể chọn implementation bằng factory hoặc dependency injection mà không thay đổi code gọi interface.

## 4. Bốn lớp tương thích phải phân biệt

**Source compatibility:** client có thể biên dịch lại không sửa code. Đổi tên/signature, thêm overload gây nhập nhằng hoặc đổi checked exception công bố có thể phá vỡ nguồn.

**Binary compatibility:** client đã biên dịch vẫn liên kết với phiên bản thư viện mới. Xóa method, đổi descriptor hoặc thu hẹp visibility có thể gây `NoSuchMethodError`, `IllegalAccessError` hoặc lỗi liên kết khác. Source mới biên dịch thành công không tự chứng minh JAR cũ chạy được.

**Behavioral compatibility:** kết quả, lỗi, thứ tự, nullability, side effect và bảo đảm trạng thái/đồng thời đã hứa được giữ. Hai phiên bản có thể source/binary compatible nhưng behavior incompatible.

**Wire/schema compatibility:** API qua HTTP, JSON, gRPC, event hoặc cơ sở dữ liệu có hợp đồng field, kiểu dữ liệu, error code, HTTP status, quyền truy cập và khả năng tương thích message. Giữ nguyên Java interface bên server không đủ để chứng minh HTTP client an toàn.

Chọn loại tương thích dựa trên **client được hỗ trợ**; không phải API nào cũng cần kiểm tra cả bốn lớp.

## 5. Tiến hóa Java 8 interface đúng cách

Java 8 hỗ trợ `default method` và `static method` trong interface. Default method đôi khi giúp mở rộng API mà không yêu cầu mọi class triển khai viết code mới ngay:

```java
interface GreetingService {
    String greet(String name);

    default String greetUppercase(String name) {
        return greet(name).toUpperCase(java.util.Locale.ROOT);
    }
}
```

Interface trên vẫn có duy nhất một abstract method. Tuy nhiên, default method **không bảo đảm tương thích trong mọi tình huống**: class có thể gặp xung đột nếu triển khai hai interface cùng cung cấp default method trùng chữ ký; phương thức mới cũng có thể va chạm với member sẵn có. Khi thêm API, phải biên dịch các client/implementer thực tế và chạy test tương thích.

Những cách mở rộng thường hợp lý: giữ method cũ và thêm method mới có contract riêng; dùng interface mở rộng hoặc API version mới khi thay đổi semantics không thể tránh; có migration guide và thời hạn hỗ trợ. `@Deprecated` chỉ thông báo API đang được thay thế, không tự đảm bảo backward compatibility.

## 6. Quy trình refactor có bằng chứng

1. **Xác định client**: module cùng repository, bên dùng thư viện đã biên dịch, ứng dụng HTTP hoặc event consumer.
2. **Chụp hợp đồng hiện hành**: chữ ký, input hợp lệ, output, trường hợp biên, exception, thứ tự, mutation, auth, consistency, hiệu năng đã hứa.
3. **Viết contract test trước refactor**: phải pass trên triển khai cũ, gồm cả lỗi và biên, để làm baseline đáng tin.
4. **Đổi implementation sau abstraction**: interface, adapter, factory hoặc dependency injection; tránh sửa public signature chỉ để tiện thuật toán mới.
5. **Chạy cùng test cho cũ/mới**: với `BigDecimal`, `compareTo` so giá trị số, `equals` phân biệt scale. Chọn phép so phù hợp với contract; đừng bỏ qua scale nếu caller đã được hứa scale.
6. **Kiểm tra tính tương thích thực tế**: build client, thử JAR đã biên dịch nếu binary compatibility quan trọng; schema/consumer-driven contract test cho HTTP và event.
7. **Triển khai có quan sát**: có thể rollout theo giai đoạn, theo dõi sai lệch kết quả, lỗi, độ trễ, hiệu năng và khả năng rollback.
8. **Nếu phải phá hợp đồng**: công bố version mới, migration guide, lịch hỗ trợ và kế hoạch loại bỏ API cũ theo chính sách dự án.

Một refactor đạt yêu cầu khi client trong phạm vi hỗ trợ vẫn dùng được API, contract test pass, giao thức không sai khác ngoài thỏa thuận, và không phát hiện vi phạm ràng buộc khi quan sát.

## 7. Lỗi phổ biến

- **Chỉ nhìn chữ ký.** Đổi cách xử lý null, validation, exception hoặc thứ tự là thay đổi đáng kể dù method signature giữ nguyên.
- **Dùng `parallelStream()` vô điều kiện.** Lambda có side effect, chia sẻ trạng thái hoặc phụ thuộc encounter order có thể gây race hoặc kết quả bất định.
- **Phụ thuộc thứ tự không cam kết.** Ví dụ, `HashMap` không bảo đảm iteration order.
- **Giả định collection trả về luôn mutable.** Cần mô tả rõ khả năng sửa, ownership, nullability và ordering nếu client phụ thuộc.
- **So sánh `BigDecimal` sai mục đích.** `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` là `false`, còn `compareTo` trả 0. Đừng vô tình đổi luật so sánh.
- **Cho rằng cache trong suốt.** Cache có thể làm sai consistency, staleness và ranh giới bảo mật.
- **Test chi tiết private method thay cho contract.** Test implementation có thể pass trong khi public behavior bị phá vỡ.
- **Bỏ qua client JAR cũ.** Unit test trong thư viện mới không chứng minh binary compatibility.

## 8. Tình huống tự kiểm tra

**A.** Method `listNames()` giữ nguyên chữ ký; bản cũ luôn sắp xếp alphabet theo tài liệu, bản mới trả thứ tự bất kỳ. Đây là **behavioral breaking change**.

**B.** `TotalCalculator` chuyển từ vòng lặp sang Stream, giữ giá trị, quy tắc lỗi, không sửa input, client không đổi và contract test pass. Đây là **thay implementation, giữ contract**.

**C.** Một functional interface được nhiều client triển khai bằng lambda. Thêm abstract method thứ hai sẽ phá các lambda này; xem xét default method hoặc interface riêng, rồi kiểm tra xung đột.

## 9. Ghi nhớ

Chỉ số quan trọng của việc thay implementation là **những lời hứa API được giữ bằng bằng chứng**, không phải code mới trông sạch hơn. Interface, lambda, method reference và Stream từ Java 8 vẫn là kỹ thuật hữu ích trong Java hiện đại. Xác định contract, kiểm thử qua public surface, cô lập chi tiết thực thi và quản lý breaking change có chủ đích.
