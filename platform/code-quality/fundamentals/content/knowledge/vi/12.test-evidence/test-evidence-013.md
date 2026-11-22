# Không đồng nhất bộ kiểm thử xanh với chứng minh đầy đủ tính đúng đắn

## 1. Mục tiêu bài học

Trong chương **Bằng chứng kiểm thử** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta xem xét ý nghĩa thực sự của câu nói “tất cả test đều xanh”. Một bộ kiểm thử chạy thành công là **bằng chứng có giá trị**, nhưng không phải là **chứng minh rằng chương trình đúng với mọi đầu vào, mọi môi trường và mọi tình huống vận hành**.

Mục tiêu của module là **hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Để đánh giá sự đáng tin cậy, người phát triển cần biết **bằng chứng nào đã có, giả định nào chưa được kiểm tra và rủi ro nào vẫn còn**.

Sau bài học này, bạn có thể:

- Giải thích chính xác kết quả **PASS** của một lần chạy kiểm thử chứng minh được điều gì và không chứng minh được điều gì.
- Phân biệt **test case**, **test oracle** (căn cứ xác định đúng/sai), **độ bao phủ** và **đặc tả hành vi**.
- Chỉ ra cách một lỗi nghiệp vụ có thể tồn tại dù mọi kiểm thử hiện tại đều xanh.
- Thiết kế thêm trường hợp biên, bất biến và kiểm thử ở ranh giới tích hợp nhằm củng cố bằng chứng.
- Đánh giá chất lượng bằng chứng theo **mức độ rủi ro**, thay vì chỉ nhìn một tỷ lệ pass hoặc coverage.

## 2. Kết quả xanh nói lên điều gì?

Một kiểm thử tự động thường chuẩn bị đầu vào hoặc trạng thái, chạy một phần hệ thống rồi so sánh những gì quan sát được với kỳ vọng. Nếu mọi assertion đều đạt và bộ chạy test không báo lỗi, kiểm thử đó được đánh dấu **PASS**.

Diễn giải có trách nhiệm:

> **Với phiên bản mã, dữ liệu, môi trường và các phép kiểm tra đã dùng trong lần chạy này, chưa phát hiện vi phạm nào của những kỳ vọng được kiểm tra.**

Diễn giải **không** được phép suy ra chỉ từ màu xanh:

> “Chương trình chắc chắn đúng cho mọi dữ liệu, mọi phiên bản, mọi tải và mọi tình huống thực tế.”

Ví dụ, nếu một phương thức nhận hàng triệu khả năng đầu vào nhưng bộ test chỉ thử mười trường hợp, kết quả xanh xác nhận **mười trường hợp đó theo kỳ vọng đã viết**, không tự động mở rộng kết luận sang những trường hợp chưa thử.

Có thể tóm tắt bằng một sự khác biệt về phạm vi:

| Câu hỏi | Kết quả test xanh có thể hỗ trợ | Điều còn cần chứng cứ |
| --- | --- | --- |
| Các đầu vào đã kiểm tra có cho kết quả mong đợi không? | Có, trong điều kiện chạy hiện tại và nếu assertion thực sự kiểm tra kết quả. | Kỳ vọng có đúng với yêu cầu nghiệp vụ không? |
| Mọi đầu vào hợp lệ có đúng không? | Chưa đủ. | Phân tích miền dữ liệu, trường hợp biên, các bất biến hoặc lập luận/chứng minh phù hợp. |
| Mọi thành phần tích hợp có tương tác đúng không? | Chỉ khi test có kiểm tra ranh giới đó. | Contract, tích hợp và hành trình thực tế. |
| Hệ thống ổn định dưới tải và lỗi hạ tầng không? | Unit test thông thường không đủ. | Kiểm thử hiệu năng, khả năng phục hồi và bằng chứng vận hành. |
| Sau khi refactor, mã vẫn đúng không? | Test xanh giảm rủi ro trong phạm vi đã được kiểm tra. | Những hành vi chưa có test, điều kiện cạnh tranh và tác dụng phụ. |

**Kiểm thử không chỉ là số ca chạy.** Một nghìn test cùng đi qua một nhánh có thể cung cấp ít thông tin hơn vài test được chọn đúng ở ranh giới và tình huống thất bại.

## 3. Bốn giới hạn thường bị bỏ qua

### 3.1. Thiếu trường hợp: thử được nhiều, nhưng chưa thử đúng chỗ

Mỗi bài test có **miền đầu vào và điều kiện môi trường** cụ thể. Lỗi thường nằm ở giá trị biên, dữ liệu rỗng, số âm, tràn số, mã hóa ký tự, thứ tự xử lý, đồng thời hoặc các tổ hợp ít xuất hiện.

Độ bao phủ dòng cao vẫn có thể không có một ca nào thử ranh giới quyết định một biểu thức dùng `>` hay `>=`. Độ bao phủ nhánh cũng không đồng nghĩa đã kiểm tra đầy đủ mọi giá trị đi qua nhánh đó.

### 3.2. Test oracle có thể sai

**Test oracle** là căn cứ để quyết định kết quả nào được coi là đúng. Với kiểm thử nghiệp vụ, oracle có thể là đặc tả đã được phê duyệt, ví dụ tính tay độc lập, bất biến hoặc kết quả từ hệ thống tham chiếu đáng tin.

Nếu cả mã và test cùng hiểu sai yêu cầu, test vẫn xanh. Chẳng hạn, chính sách nói **“miễn phí giao hàng từ 500.000 VND”**, nhưng lập trình viên và người viết test đều hiểu nhầm rằng chỉ **trên 500.000 VND** mới được miễn phí. Mọi test dùng cùng nhận định sai sẽ không cảnh báo lỗi này.

Vì vậy, không nên lấy **kết quả của chính hiện thực đang kiểm thử** để tạo kỳ vọng rồi coi đó là kiểm chứng độc lập.

### 3.3. Môi trường test không giống môi trường thật

Một phương thức thuần có thể dễ kiểm tra bằng unit test; nhưng sản phẩm còn phụ thuộc database, cấu hình, mạng, đồng hồ, cache, concurrency, đặc điểm JVM và các dịch vụ bên ngoài.

Mock trả HTTP 200 không chứng minh adapter thật đã gửi đúng xác thực, xử lý timeout hoặc giải mã payload của đối tác. Database trong bộ nhớ không nhất thiết có cùng ràng buộc giao dịch, locking và kiểu dữ liệu với database sản xuất.

### 3.4. Test có thể không thực sự quan sát lỗi

Một test không có assertion, assertion kiểm tra sai đối tượng, bắt và bỏ mọi exception hoặc luôn dùng dữ liệu đã được chuẩn hóa có thể kết thúc xanh dù logic quan trọng sai. Test không thực sự chạy vì bị vô hiệu hóa, bị lọc ra khỏi lệnh CI hoặc nằm ngoài tập test được chọn cũng không góp bằng chứng cho lần chạy đó.

Khi báo cáo “bộ kiểm thử xanh”, cần biết **những test nào đã chạy, trên bản mã nào và những assertion nào được thực thi**.

## 4. Ví dụ Java 17: mọi test hiện tại xanh nhưng hàm vẫn sai

Giả sử cửa hàng tính **thành tiền cho một dòng hàng sau giảm giá**, với chính sách:

1. `unitPriceVnd` là giá một đơn vị, không âm, đơn vị VND.
2. `quantity` phải là số nguyên **lớn hơn 0**.
3. `discountVnd` là khoản giảm theo dòng hàng, không âm.
4. Tổng trước giảm là `unitPriceVnd × quantity`. Khoản giảm áp dụng **không được vượt quá tổng trước giảm**; nếu giảm lớn hơn tổng, thành tiền bằng **0**, không được âm.
5. Nếu phép nhân không biểu diễn được trong `long`, thao tác phải **báo lỗi rõ ràng** chứ không dùng kết quả tràn số.

Đây là ví dụ học thuật về một dòng hàng, chưa bao gồm thuế, phí, làm tròn số thập phân hay khuyến mãi áp dụng trên toàn đơn.

### 4.1. Hiện thực có lỗi

```java
public final class NetPriceCalculator {
    private NetPriceCalculator() {}

    public static long calculate(
            long unitPriceVnd, int quantity, long discountVnd) {
        long grossVnd = unitPriceVnd * quantity;
        return grossVnd - discountVnd;
    }
}
```

Mã rất ngắn, cú pháp hợp lệ và có thể cho kết quả đúng trong nhiều tình huống thông thường. Nhưng nó có ít nhất ba vấn đề:

- Không từ chối giá âm, số lượng bằng 0 hoặc khoản giảm âm.
- Giảm giá vượt tổng trước giảm sẽ cho **thành tiền âm**, trái hợp đồng.
- Phép nhân `long` có thể tràn số mà không tự ném lỗi.

### 4.2. Một bộ test xanh chưa đủ

Giả sử nhóm hiện chỉ có các ca sau:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class NetPriceCalculatorSmokeTest {
    @Test
    void calculatesOrdinaryLines() {
        assertEquals(170_000,
                NetPriceCalculator.calculate(100_000, 2, 30_000));
        assertEquals(50_000,
                NetPriceCalculator.calculate(60_000, 1, 10_000));
        assertEquals(100_000,
                NetPriceCalculator.calculate(40_000, 3, 20_000));
    }
}
```

Với hiện thực ở mục 4.1, **cả ba assertion này sẽ đạt**. Tuy nhiên, test không đụng đến giảm giá vượt tổng, đầu vào sai hoặc tràn số. Kết quả xanh **không mâu thuẫn** với việc hàm sai trong các trường hợp còn lại: test đang hỏi những câu mà hiện thực trả lời đúng.

| Đầu vào chưa được test | Hành vi theo hợp đồng | Kết quả của hiện thực lỗi |
| --- | --- | --- |
| `calculate(100_000, 1, 120_000)` | `0` | `-20_000` |
| `calculate(100_000, 0, 0)` | Báo đầu vào không hợp lệ | `0` |
| `calculate(-10, 1, 0)` | Báo đầu vào không hợp lệ | `-10` |
| `calculate(Long.MAX_VALUE, 2, 0)` | Báo tràn số | Phép nhân tràn, cho kết quả sai |

Ví dụ này cho thấy sự khác nhau giữa **“không có lỗi được các test hiện tại phát hiện”** và **“không có lỗi”**.

### 4.3. Hiện thực tuân theo hợp đồng đã nêu

Đây là **phiên bản thay thế** cho lớp `NetPriceCalculator` ở mục 4.1, không phải một lớp cần đặt song song trong cùng package.

```java
// NetPriceCalculator.java - phiên bản sau khi sửa
public final class NetPriceCalculator {
    private NetPriceCalculator() {}

    public static long calculate(
            long unitPriceVnd, int quantity, long discountVnd) {
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException(
                    "unitPriceVnd must not be negative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        if (discountVnd < 0) {
            throw new IllegalArgumentException(
                    "discountVnd must not be negative");
        }

        long grossVnd = Math.multiplyExact(unitPriceVnd, quantity);
        long appliedDiscountVnd = Math.min(grossVnd, discountVnd);
        return grossVnd - appliedDiscountVnd;
    }
}
```

Điều gì đã thay đổi?

- Đầu vào được kiểm tra tại ranh giới API.
- `Math.multiplyExact` ném `ArithmeticException` nếu phép nhân tràn miền biểu diễn của `long`.
- `Math.min` giới hạn giảm giá theo tổng trước giảm. Khi các đầu vào hợp lệ và phép nhân không tràn, kết quả thuộc khoảng từ `0` đến `grossVnd`.

Điều quan trọng không chỉ là mã mới nhìn rõ ràng hơn. **Quy tắc cần được xác nhận độc lập**: nhóm nghiệp vụ phải thực sự mong muốn khoản giảm vượt tổng được giới hạn về tổng, chứ không phải từ chối cả đơn. Hai lựa chọn đó có thể đều hợp lý trong những hệ thống khác nhau, nhưng dẫn tới hợp đồng và test khác nhau.

## 5. Bổ sung bằng chứng bằng ca biên và trường hợp lỗi

Sau khi viết rõ đặc tả, test có thể kiểm tra các **lớp tương đương** và **điểm biên**:

- Giảm bằng `0`: thành tiền bằng tổng trước giảm.
- Giảm **nhỏ hơn**, **bằng** và **lớn hơn** tổng trước giảm.
- Giá bằng `0`, số lượng nhỏ nhất hợp lệ bằng `1`.
- Giá âm, số lượng bằng `0` hoặc âm, khoản giảm âm.
- Phép nhân vừa nằm trong miền `long` và phép nhân vượt giới hạn.

Ví dụ JUnit 5 với test tham số hóa:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class NetPriceCalculatorTest {
    static Stream<Arguments> validCases() {
        return Stream.of(
                Arguments.of(100_000L, 2, 30_000L, 170_000L),
                Arguments.of(100_000L, 2, 0L, 200_000L),
                Arguments.of(100_000L, 2, 200_000L, 0L),
                Arguments.of(100_000L, 2, 250_000L, 0L),
                Arguments.of(0L, 2, 999L, 0L),
                Arguments.of(1L, 1, 0L, 1L)
        );
    }

    @ParameterizedTest
    @MethodSource("validCases")
    void followsDiscountContract(
            long price, int quantity, long discount, long expected) {
        assertEquals(expected,
                NetPriceCalculator.calculate(price, quantity, discount));
    }

    @Test
    void rejectsInvalidInputs() {
        assertThrows(IllegalArgumentException.class,
                () -> NetPriceCalculator.calculate(-1, 1, 0));
        assertThrows(IllegalArgumentException.class,
                () -> NetPriceCalculator.calculate(100, 0, 0));
        assertThrows(IllegalArgumentException.class,
                () -> NetPriceCalculator.calculate(100, -1, 0));
        assertThrows(IllegalArgumentException.class,
                () -> NetPriceCalculator.calculate(100, 1, -1));
    }

    @Test
    void rejectsMultiplicationOverflow() {
        assertThrows(ArithmeticException.class,
                () -> NetPriceCalculator.calculate(
                        Long.MAX_VALUE, 2, 0));
    }

    @Test
    void acceptsRepresentableUpperBound() {
        assertEquals(Long.MAX_VALUE,
                NetPriceCalculator.calculate(
                        Long.MAX_VALUE, 1, 0));
    }
}
```

So với bộ smoke test, phiên bản này cho bằng chứng mạnh hơn về quy tắc giới hạn giảm, miền đầu vào và tràn số. Nhưng nó vẫn **chỉ kiểm tra những trường hợp đã chọn**. Việc có thêm ca biên không biến kiểm thử hữu hạn thành một chứng minh tổng quát.

### Cần cẩn thận với kỳ vọng của test

Nếu kỳ vọng trong test được tính bằng cách **gọi lại chính `NetPriceCalculator.calculate`** rồi so với kết quả của nó, test có thể trở thành vòng lặp tự xác nhận. Nếu test lặp nguyên xi mọi nhánh của hiện thực để tạo expected, cả hai đoạn mã có thể mắc cùng một lỗi.

Hãy ưu tiên các trường hợp có đáp án rõ từ quy tắc nghiệp vụ, phép tính độc lập, hoặc những bất biến mà **nhiều kiểu triển khai khác nhau** đều phải thỏa mãn.

## 6. Kiểm tra bất biến trên nhiều đầu vào

Ngoài vài ví dụ cụ thể, ta có thể hỏi những câu có dạng tổng quát:

**Bất biến cần có với mọi đầu vào hợp lệ không tràn số:**

1. `netVnd >= 0`.
2. `netVnd <= grossVnd`.
3. Không có giảm giá (`discountVnd = 0`) thì `netVnd = grossVnd`.
4. Với cùng giá và số lượng, **tăng khoản giảm không được làm tăng thành tiền**.
5. Khi khoản giảm bằng hoặc lớn hơn tổng trước giảm, `netVnd = 0`.

Những quan hệ này không gắn chặt vào số lớp, tên biến hay cách tính cụ thể nên hữu ích khi **refactor**. Có thể dùng property-based testing để tự tạo nhiều đầu vào, rồi kiểm tra chúng.

Một minh họa chỉ dùng JUnit 5 và `Random` chuẩn của Java:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Random;
import org.junit.jupiter.api.Test;

class NetPricePropertiesTest {
    @Test
    void sampledInputsSatisfyBasicInvariants() {
        Random random = new Random(20261116L);

        for (int i = 0; i < 2_000; i++) {
            long price = random.nextInt(100_001);
            int quantity = 1 + random.nextInt(10);
            long discount = random.nextInt(1_000_001);
            long gross = price * quantity; // Miền sinh bảo đảm không tràn.

            long net = NetPriceCalculator.calculate(
                    price, quantity, discount);
            assertTrue(net >= 0 && net <= gross,
                    "Invariant violated at sample " + i);
            assertEquals(gross,
                    NetPriceCalculator.calculate(price, quantity, 0));

            long biggerDiscount = discount + 1_000;
            long netAfterBiggerDiscount =
                    NetPriceCalculator.calculate(
                            price, quantity, biggerDiscount);
            assertTrue(netAfterBiggerDiscount <= net,
                    "Increasing discount raised net at sample " + i);
        }
    }
}
```

**Ưu điểm:** cùng một tập bất biến được chạy trên nhiều tổ hợp giá, số lượng và giảm giá; seed cố định giúp tái hiện khi có lỗi.

**Giới hạn:** 2.000 mẫu không bao phủ toàn bộ miền `long`, không ngẫu nhiên chạm được mọi ranh giới và không tự kiểm tra phản ứng với đầu vào âm hay tràn số. Những ca ở ranh giới cần được **viết riêng**. Property-based testing chuyên dụng có thể hỗ trợ bộ sinh dữ liệu, thu nhỏ trường hợp lỗi (shrinking) và báo cáo seed, nhưng cũng không tự chứng minh đúng mọi đầu vào.

Không nên dùng test ngẫu nhiên như cách thay thế hiểu biết nghiệp vụ. Nếu bất biến đã được định nghĩa sai, chạy nhiều mẫu chỉ cho thêm bằng chứng về **một quy tắc sai**.

## 7. Độ bao phủ, mutation testing và những con số dễ gây hiểu nhầm

### 7.1. Coverage nói về phần mã được thực thi

**Line coverage** cho biết mức độ dòng mã được chạy qua trong test; **branch coverage** phản ánh một số kết quả nhánh điều khiển đã được đi qua. Các chỉ số này giúp tìm phần chưa được kiểm tra, nhưng không đo trực tiếp liệu **assertion đúng hay đủ**.

Ví dụ:

```java
@Test
void executesMethodButChecksNothing() {
    NetPriceCalculator.calculate(100_000, 2, 30_000);
}
```

Test này có thể làm các dòng trong phương thức được tính là đã thực thi, nhưng nó **không xác nhận kết quả 170.000 VND**. Nếu hiện thực trả kết quả sai nhưng không ném lỗi, test vẫn có thể xanh.

Đừng đặt mục tiêu “100% coverage” thay cho việc xác định những **hành vi và rủi ro** cần được kiểm chứng. 100% coverage cũng không nói test đã chạy trên môi trường giống sản xuất.

### 7.2. Mutation testing đo sức phát hiện một số lỗi được tạo có chủ đích

**Mutation testing** thay đổi nhỏ trong mã (ví dụ đổi `>=` thành `>`, `+` thành `-`) rồi kiểm tra bộ test có phát hiện được khác biệt không. Nếu mutant khiến test thất bại, test đã cho thấy khả năng phân biệt với **loại sai khác ấy**. Nếu mutant sống sót, có thể cần thêm assertion hoặc đầu vào, nhưng cũng có những mutant tương đương về hành vi trong miền hợp đồng nên không thể bị “giết” bằng test đúng.

Mutation score cao là **tín hiệu hỗ trợ**, không phải chứng chỉ rằng chương trình đúng. Nó còn phụ thuộc tập mutant, phạm vi mã được xử lý và cách tính các mutant tương đương.

### 7.3. Số lượng test và tỷ lệ pass cũng có giới hạn

| Chỉ số | Cho biết điều gì | Không cho biết điều gì |
| --- | --- | --- |
| `100% passed` | Không có test đã chạy bị báo thất bại trong lần đó | Mọi tình huống thực tế đều đúng. |
| Số lượng test lớn | Có nhiều trường hợp/đơn vị kiểm tra | Chúng có độc lập, quan trọng hay có assertion tốt không. |
| Line/branch coverage | Mức phần mã/nhánh đã được thực thi | Kỳ vọng và quy tắc nghiệp vụ có chính xác không. |
| Mutation score | Khả năng phát hiện một tập sai khác mô phỏng | Đã phát hiện hết các kiểu bug có thể xảy ra chưa. |
| Thời gian chạy ngắn | Phản hồi nhanh cho người phát triển | Hệ thống đáp ứng SLO ở tải thật không. |
| Không có flaky test đã biết | Tín hiệu ít nhiễu hơn | Test có đủ mạnh hoặc môi trường thật đã được kiểm tra chưa. |

Nên đọc các chỉ số **cùng với phạm vi test, chất lượng oracle và những rủi ro còn chưa được kiểm tra**.

## 8. Những lớp bằng chứng bổ sung cho nhau

Một dịch vụ Java có thể đúng ở mức hàm tính toán nhưng vẫn sai khi giao tiếp với cơ sở dữ liệu, xử lý đồng thời hoặc vận hành dưới tải. Những cách kiểm chứng khác nhau trả lời những câu hỏi khác nhau:

| Hình thức | Bằng chứng chính | Giới hạn quan trọng |
| --- | --- | --- |
| **Unit test** | Quy tắc của một đơn vị trong đầu vào được kiểm soát. | Không chứng minh cấu hình hoặc phụ thuộc thật hoạt động đúng. |
| **Property-based / boundary test** | Nhiều mẫu hoặc bất biến có tính bao quát hơn. | Vẫn phụ thuộc oracle và miền sinh dữ liệu. |
| **Contract test** | Hai phía của giao diện hiểu cùng dữ liệu, lỗi và hành vi cam kết. | Không chứng minh toàn bộ luồng hoặc chất lượng nghiệp vụ. |
| **Integration test** | Những thành phần thật phối hợp được ở môi trường test. | Có thể khác cấu hình, tải và dữ liệu sản xuất. |
| **End-to-end test** | Một hành trình quan trọng hoạt động qua nhiều tầng. | Tốn kém, khó bao phủ mọi tổ hợp và dễ bị ảnh hưởng môi trường. |
| **Static analysis / type checking** | Một số mẫu lỗi và quy tắc có thể xác minh mà không cần chạy. | Không chứng minh tất cả yêu cầu nghiệp vụ đều đúng. |
| **Security / performance / resilience testing** | Hành vi dưới tải, tấn công mô phỏng hoặc lỗi phụ thuộc cụ thể. | Chỉ áp dụng cho mô hình đe dọa và điều kiện thử đã chọn. |
| **Metrics và quan sát vận hành** | Hành vi thật sau triển khai: lỗi, độ trễ, tỷ lệ thất bại. | Không xác định mọi nguyên nhân hay mọi lỗi tiềm ẩn; phát hiện có thể muộn. |

### Trường hợp cần nhiều lớp bằng chứng

Giả sử `NetPriceCalculator` đã có đầy đủ unit test. Trong API thanh toán, còn phải xác minh:

- **Hợp đồng dữ liệu:** JSON gửi lên có đúng đơn vị tiền và cách biểu diễn số lượng không?
- **Tích hợp:** các khoản giảm có được áp dụng đúng một lần trong luồng tạo đơn và thanh toán không?
- **Đồng thời:** hai yêu cầu cập nhật một đơn có làm mất bản ghi hoặc tạo hai giao dịch không?
- **Vận hành:** lỗi bên thứ ba và timeout có được phát hiện, xử lý và quan sát đúng không?

Unit test của phép tính không thể thay thế bằng chứng về những điều ấy. Ngược lại, một end-to-end test “mua hàng thành công” cũng không tự thay thế kiểm thử biên của phép tính.

## 9. Từ “đã kiểm thử” đến lập luận có căn cứ

Khi đánh giá một thay đổi, hãy xem các kết quả test như **một phần của lập luận tin cậy**, thay vì lời khẳng định tuyệt đối.

Một bản ghi đánh giá ngắn có thể gồm:

| Thành phần | Ví dụ |
| --- | --- |
| **Tuyên bố cần hỗ trợ** | Thành tiền một dòng hàng không âm khi đầu vào hợp lệ và tổng trước giảm biểu diễn được. |
| **Giả định** | Giá và giảm giá tính bằng VND nguyên; số lượng dương; yêu cầu nghiệp vụ giới hạn giảm theo tổng. |
| **Bằng chứng trực tiếp** | Unit test cho đầu vào âm, giảm bằng/trên/dưới tổng, tràn số; kiểm tra bất biến trên nhiều mẫu. |
| **Bằng chứng liên quan** | Review quy tắc với người chịu trách nhiệm, contract/integration test của luồng thanh toán. |
| **Phần chưa được chứng minh** | Mọi tổ hợp giá trị `long`, hệ thống phân tán và các lỗi vận hành chưa được mô phỏng. |
| **Hành động tiếp theo** | Bổ sung test ở ranh giới xử lý tiền và theo dõi sai lệch giao dịch ở môi trường thực. |

Trình bày bằng chứng như vậy giúp nhóm nói rõ **mức tin cậy có cơ sở**, biết phần nào đã được bảo vệ khi refactor và ưu tiên rủi ro còn lại.

### Phân biệt kiểm thử với chứng minh hình thức

Ở một số hệ thống, có thể dùng **lập luận toán học**, kiểm tra mô hình hoặc phương pháp hình thức để chứng minh một thuộc tính trong **mô hình và các giả định đã xác định**. Ngay cả khi có chứng minh như vậy, vẫn cần xét tính đúng đắn của đặc tả, mô hình môi trường và phần triển khai ngoài phạm vi chứng minh.

Ngược lại, một suite test thông thường dựa trên **các lần thực thi hữu hạn**. Nó có thể rất thuyết phục về một tập rủi ro nhưng không nên được gọi là “chứng minh đầy đủ” nếu không có cơ sở hình thức tương ứng.

## 10. Ưu tiên kiểm thử theo hậu quả lỗi

Không có ngân sách thời gian vô hạn để thử mọi trường hợp. Cách phân bổ nỗ lực tốt hơn là dựa trên **tác động, khả năng xảy ra và khả năng phát hiện lỗi**.

| Khu vực | Rủi ro chính | Bằng chứng nên ưu tiên |
| --- | --- | --- |
| Tính tiền, giữ hàng, quyền truy cập | Sai tiền, tồn kho âm, thao tác trái phép | Điều kiện biên, bất biến, kiểm thử lỗi, transaction/integration và security test phù hợp. |
| Tìm kiếm, lọc danh sách | Bỏ sót hoặc xếp sai kết quả | Tập dữ liệu đại diện, dữ liệu rỗng, thứ tự/điều kiện lọc đã công bố. |
| Cache hoặc đồng bộ trạng thái | Dữ liệu cũ, race condition | Kiểm thử nhất quán, thời gian, đồng thời, fallback và quan sát hệ thống. |
| Giao tiếp đối tác | Payload sai, timeout, lỗi tương thích | Contract, integration, thử tình huống lỗi và retry an toàn. |
| Định dạng nội dung ít rủi ro | Sai hiển thị hoặc ký tự đặc biệt | Test định dạng, dữ liệu biên và kiểm thử giao diện cần thiết. |

Một thành phần có hậu quả lỗi lớn có thể cần nhiều **loại bằng chứng độc lập** hơn. Không nhất thiết phải tăng số lượng unit test bằng mọi giá; đôi khi một kiểm thử tích hợp về transaction hoặc quyền truy cập mang lại giá trị lớn hơn thêm nhiều phép so sánh thông thường.

## 11. Quy trình thực hành khi một pull request có test xanh

Trước khi chấp nhận kết luận “thay đổi an toàn”, hãy kiểm tra theo thứ tự:

1. **Xác nhận phạm vi lần chạy:** các test cần thiết có thật sự được chạy trên đúng commit, đúng cấu hình và phiên bản phụ thuộc không? Có test bị vô hiệu hóa hoặc lọc mất không?
2. **Đọc yêu cầu thay vì chỉ đọc assertion:** kỳ vọng có được dẫn từ quy tắc nghiệp vụ và hợp đồng đã xác nhận không?
3. **Xem các trường hợp biên:** đầu vào rỗng, null, 0, âm, giá trị lớn, điểm bằng ngưỡng, dữ liệu trùng và đường lỗi.
4. **Kiểm tra các bất biến:** có tính chất nào phải đúng với cả một lớp đầu vào mà các ví dụ riêng lẻ chưa thể hiện không?
5. **Xem tác dụng phụ và tích hợp:** code mới có thay đổi I/O, giao dịch, timeout, bộ nhớ đệm, cấu hình hoặc thứ tự xử lý không? Unit test có bao phủ được không?
6. **Đọc các chỉ số đúng ý nghĩa:** coverage và mutation score giúp chỉ ra chỗ yếu, nhưng không thay thế review oracle hoặc rủi ro.
7. **Ghi nhận giới hạn còn lại:** điều gì chưa kiểm tra, vì sao chấp nhận tạm thời, cần theo dõi hoặc bổ sung loại bằng chứng nào?

Nếu test đỏ, đừng tự động sửa expected để làm pipeline xanh; trước tiên phải tìm xem **hành vi có sai hay đặc tả thật sự thay đổi**. Nếu test xanh, đừng tự động ngừng xem xét những phần nằm ngoài câu hỏi mà test đã hỏi.

## 12. Các ngộ nhận phổ biến

**“Tất cả test xanh nghĩa là không còn bug.”** Không. Kết quả xanh chỉ có ý nghĩa với phạm vi và kỳ vọng đã được thực thi.

**“Có 100% coverage thì chắc chắn đúng.”** Không. Coverage không cho biết oracle có đúng, assertion có mạnh và các tổ hợp dữ liệu đã đủ chưa.

**“Càng nhiều test thì càng đáng tin.”** Chưa chắc. Test trùng lặp, test không assertion hoặc cùng dùng một giả định sai có thể tạo cảm giác an toàn giả.

**“Mutation score cao chứng minh hết lỗi.”** Không. Nó đo khả năng phát hiện một tập thay đổi mô phỏng, không đại diện cho mọi lỗi thực tế.

**“Đã dùng mock nên không cần kiểm thử tích hợp.”** Mock kiểm soát môi trường để kiểm tra logic; nó không tự chứng minh hành vi của dịch vụ hoặc database thật.

**“Kiểm thử ngẫu nhiên đã chạy hàng nghìn lượt nên có thể bỏ ca biên.”** Không. Những giá trị hiếm nhưng quan trọng cần được chọn trực tiếp.

**“Chỉ cần một phép end-to-end đi qua luồng mua hàng thành công.”** Luồng thành công không xác nhận mọi đường lỗi, race condition hoặc trường hợp thanh toán một phần.

**“Không thể chứng minh tuyệt đối thì kiểm thử cũng không có giá trị.”** Sai. Kiểm thử là bằng chứng thực nghiệm cực kỳ hữu ích để phát hiện lỗi, ngăn hồi quy và giảm rủi ro. Chỉ cần diễn giải **đúng phạm vi của bằng chứng**.

## 13. Câu hỏi tự kiểm tra

1. Một hàm tính giảm giá vượt qua 500 unit test, nhưng không test khoản giảm lớn hơn tổng trước giảm. Có thể kết luận nó không trả giá trị âm không? Vì sao?
2. Trong ví dụ `NetPriceCalculator`, tại sao kiểm thử với `Long.MAX_VALUE` và số lượng `2` cung cấp bằng chứng khác với kiểm thử giá thông thường?
3. Nếu test so sánh kết quả với chính kết quả do hiện thực đang kiểm thử tính ra, vấn đề về **test oracle** là gì?
4. Một bộ test đạt 100% line coverage nhưng không có assertion. Bằng chứng thực sự mà nó mang lại là gì?
5. Unit test dùng fake payment gateway đều xanh. Vì sao vẫn phải kiểm tra idempotency, timeout và giao dịch ở ranh giới thật?
6. Nếu nhóm sửa policy từ “giảm giá quá tổng thì giới hạn về 0” sang “giảm quá tổng thì từ chối đơn”, có nên giữ nguyên expected cũ chỉ để bảo toàn màu xanh không?

**Gợi ý:** (1) Không; chưa kiểm tra miền dữ liệu cần thiết và cách tính có thể cho số âm. (2) Nó xác minh đường tràn số có bị báo lỗi rõ thay vì tạo kết quả sai. (3) Test thiếu căn cứ độc lập; cùng một bug có thể xuất hiện ở cả expected và actual. (4) Chỉ biết mã được thực thi mà không tự động phát hiện kết quả sai. (5) Fake không tái hiện đầy đủ tác dụng phụ, lỗi hoặc giao thức của hệ thống thật. (6) Không; đây là **thay đổi hợp đồng nghiệp vụ**, cần cập nhật đặc tả, test và hiện thực theo yêu cầu đã được phê duyệt.

## 14. Ghi nhớ

**Bộ kiểm thử xanh là bằng chứng rằng những phép kiểm tra đã chạy không phát hiện sai lệch, không phải chứng minh đầy đủ tính đúng đắn.** Giá trị của bằng chứng phụ thuộc vào **oracle đúng, đầu vào và trường hợp biên được chọn, mức quan sát của assertion, môi trường thử và rủi ro cần bảo vệ**. Hãy kết hợp unit test, kiểm thử bất biến, contract/integration test, phân tích tĩnh, review nghiệp vụ và tín hiệu vận hành khi thích hợp. Diễn giải rõ những gì **đã kiểm tra** và **chưa kiểm tra** giúp nhóm phát triển mã nguồn đáng tin cậy hơn mà vẫn có thể hiểu và thay đổi an toàn.
