# Lựa chọn kiểm thử dựa trên thuộc tính cho các bất biến phù hợp

Trong Domain-Driven Design (DDD), Aggregate và Value Object bảo vệ các quy tắc nghiệp vụ bằng những invariant: số lượng không âm, tổng tiền được tính nhất quán, khoảng hiệu lực có thứ tự hợp lệ, reservation không vượt quá lượng hàng khả dụng hoặc một trạng thái chỉ được chuyển theo những bước được cho phép. Kiểm thử theo ví dụ (example-based testing) xác minh một số tình huống cụ thể. Nhưng với nhiều quy tắc, số lượng tổ hợp đầu vào có thể rất lớn và một vài ví dụ không đủ để phát hiện các trường hợp biên.

**Property-based testing (PBT)** bổ sung một cách tiếp cận khác: thay vì chỉ viết từng input và expected output, người viết mô tả một thuộc tính tổng quát mà hệ thống phải luôn thỏa mãn, sau đó framework sinh nhiều input để kiểm tra thuộc tính đó. Khi tìm thấy phản ví dụ, framework có thể thu nhỏ input để tạo ra trường hợp đơn giản hơn, giúp xác định nguyên nhân.

PBT đặc biệt phù hợp với các quy tắc có tính tổng quát hoặc đại số, như bất biến của Value Object, giới hạn số lượng, phép toán trên tiền, khoảng thời gian, tính idempotent và các chuyển trạng thái. Nó không thay thế kiểm thử theo ví dụ hay kiểm thử tích hợp. Bài học này trình bày cách nhận diện invariant phù hợp, thiết kế generator, dùng jqwik trong Java, kiểm thử Aggregate và các giới hạn cần lưu ý.

## 1. Property-based testing là gì?

Trong kiểm thử theo ví dụ, test mô tả một input cụ thể và kết quả mong đợi:

```java
@Test
void addingTwoAmountsProducesTheExpectedAmount() {
    Money left = Money.of("10.00", Currency.getInstance("USD"));
    Money right = Money.of("5.00", Currency.getInstance("USD"));

    assertEquals(Money.of("15.00", Currency.getInstance("USD")),
            left.plus(right));
}
```

Test này hữu ích nhưng chỉ kiểm tra một cặp giá trị. Property-based test mô tả quy tắc tổng quát hơn, ví dụ: “cộng hai khoản tiền cùng currency có tính giao hoán”. Framework sẽ sinh nhiều cặp tiền hợp lệ để kiểm tra:

```java
@Property
void additionIsCommutative(@ForAll("sameCurrencyMoneyPairs") MoneyPair pair) {
    assertEquals(pair.left().plus(pair.right()),
            pair.right().plus(pair.left()));
}
```

Framework chạy property nhiều lần với dữ liệu được sinh. Nếu có input làm thuộc tính sai, test thất bại và báo dữ liệu gây lỗi; một số framework còn shrink input để tìm phản ví dụ nhỏ hơn.

### 1.1. Property không phải là một input ngẫu nhiên bất kỳ

Một property phải là phát biểu có ý nghĩa về hành vi hoặc invariant của domain. “Chạy hàm với nhiều số ngẫu nhiên” chưa phải một kiểm thử tốt nếu không xác định kết quả nào phải luôn đúng.

Ví dụ property có ý nghĩa:

- Sau mọi thao tác giữ hàng hợp lệ, số lượng khả dụng không âm.
- Một khoảng `[start, end)` luôn chứa `start` và không chứa `end`.
- Cộng một Money zero cùng currency không làm thay đổi giá trị.
- Gọi lặp một command idempotent không tạo thêm tác động.
- Serialize rồi deserialize một Value Object giữ nguyên giá trị miền.

## 2. Khi nào nên chọn PBT?

PBT hữu ích khi có thể phát biểu một quy tắc đúng cho một tập input rộng, và framework có thể sinh các input đại diện cho tập đó.

Các tình huống phù hợp:

- **Invariant số học:** tiền, tỷ lệ, số lượng, phân bổ và giới hạn.
- **Value Object:** equality, normalization, validation, comparison và các phép toán.
- **Khoảng thời gian:** containment, overlap, adjacency, duration và boundary semantics.
- **Aggregate:** invariant phải giữ sau mọi command hợp lệ.
- **Idempotency:** thực hiện lặp cùng một ý định không làm tăng số tác động.
- **Round-trip:** chuyển đổi sang DTO/database/event rồi đọc lại phải giữ ngữ nghĩa cần thiết.
- **Metamorphic properties:** thay đổi đầu vào theo một phép biến đổi đã biết thì kết quả phải thay đổi theo quy luật tương ứng.

PBT đặc biệt có giá trị khi có nhiều trường hợp biên, miền đầu vào rộng hoặc các phép toán có luật tổng quát.

## 3. Khi nào không nên dùng PBT làm cách kiểm thử chính?

Không phải mọi yêu cầu đều có property tổng quát dễ xác định.

Ví dụ ít phù hợp:

- Một thông báo phải có câu chữ chính xác theo hợp đồng pháp lý.
- Một use case có một luồng nghiệp vụ đặc thù với vài nhánh cụ thể.
- Quyết định phụ thuộc vào dịch vụ ngoài không thể mô phỏng hoặc kiểm soát.
- Một quy tắc chưa được chuyên gia nghiệp vụ định nghĩa đủ rõ.
- Một tập dữ liệu nhỏ có thể liệt kê và kiểm tra hết bằng example-based tests.
- Một bài toán concurrency mà test tuần tự không thể chứng minh an toàn khi nhiều transaction chạy đồng thời.

Trong các trường hợp này, dùng example-based, contract, integration, concurrency hoặc acceptance tests phù hợp. PBT có thể bổ sung để kiểm tra phần logic thuần hoặc mô hình trạng thái bên trong.

## 4. Phân biệt Example-based, Property-based và Fuzz Testing

| Cách kiểm thử | Cách tiếp cận | Điểm mạnh | Giới hạn chính |
|---|---|---|---|
| Example-based | Người viết chọn input và expected result | Diễn đạt rõ tình huống nghiệp vụ cụ thể | Dễ bỏ sót tổ hợp và biên |
| Property-based | Người viết mô tả property, framework sinh nhiều input | Bao phủ rộng trong miền generator và tìm phản ví dụ | Cần generator tốt và property đúng |
| Fuzz testing | Đưa dữ liệu bất thường/ngẫu nhiên để tìm crash, lỗi parser hoặc lỗ hổng | Tìm lỗi robustness và input không dự kiến | Không tự biết kết quả nghiệp vụ đúng là gì |

Ba cách có thể bổ sung cho nhau. Một parser có thể được fuzz để tìm crash; một Value Object có thể được property-test để bảo đảm invariant; một use case quan trọng vẫn cần các example-based tests thể hiện các quyết định nghiệp vụ dễ đọc.

## 5. Bắt đầu từ invariant của DDD

Trước khi viết generator, hãy đọc mô hình miền và xác định điều kiện phải luôn đúng.

Ví dụ với Inventory Aggregate:

- `availableQuantity >= 0`.
- `reservedQuantity >= 0`.
- `availableQuantity + reservedQuantity` không vượt quá lượng được phép quản lý theo mô hình.
- Reservation chỉ được tạo khi yêu cầu hợp lệ.
- Không thể giải phóng reservation đã được tiêu thụ theo cùng hành vi release thông thường.

Ví dụ với Money Value Object:

- Currency không được null.
- Hai khoản tiền chỉ được cộng nếu currency tương thích.
- Cộng zero giữ nguyên giá trị.
- Kết quả cộng không phụ thuộc thứ tự toán hạng nếu quy tắc scale/rounding đã được xác định phù hợp.

Ví dụ với TimeRange `[start, end)`:

- `end` không trước `start`.
- `start` thuộc khoảng nếu khoảng không rỗng.
- `end` không thuộc khoảng.
- Hai khoảng chỉ chạm nhau ở biên không overlap.
- Quan hệ overlap có tính đối xứng.

### 5.1. Invariant phải được viết bằng ngôn ngữ miền

Không nên bắt đầu bằng câu “field `reservedQty` không âm” nếu điều quan trọng trong nghiệp vụ là “không thể cam kết nhiều hàng hơn lượng tồn có thể phân bổ”. Hãy diễn đạt điều kiện nghiệp vụ trước, sau đó xác định các field và phép tính thực hiện điều kiện đó.

Một property tốt phải giúp đội phát triển và chuyên gia nghiệp vụ hiểu điều gì đang được bảo vệ.

## 6. Phân loại các property thường gặp

Một số nhóm property hữu ích:

### 6.1. Invariant property

Khẳng định một điều kiện luôn đúng sau khi tạo hoặc thực hiện hành vi:

\[
availableQuantity \geq 0
\]

### 6.2. Algebraic property

Mô tả luật của phép toán:

\[
a + b = b + a
\]

hoặc identity:

\[
a + 0 = a
\]

Chỉ áp dụng luật khi các điều kiện domain tương ứng được thỏa, ví dụ hai Money có cùng currency.

### 6.3. Metamorphic property

Mô tả cách kết quả phải thay đổi khi input được biến đổi theo một quy tắc đã biết. Ví dụ, nếu tăng available stock nhưng giữ nguyên request quantity, một yêu cầu trước đó được chấp nhận không nên chuyển thành bị từ chối chỉ vì lượng hàng khả dụng tăng, với giả định các điều kiện khác không đổi.

### 6.4. Round-trip property

Chuyển đổi một giá trị qua serialization/persistence rồi đọc lại phải giữ ngữ nghĩa:

\[
decode(encode(x)) = x
\]

Đẳng thức có thể là equality miền hoặc tương đương theo contract, không nhất thiết byte-for-byte giống nhau.

### 6.5. Idempotency property

Thực hiện cùng một thao tác có định danh lặp lại phải không tạo thêm tác động:

\[
effect(command, key) = effect(retry(command, key))
\]

Property cần xác định rõ tác động nào được so sánh: trạng thái Aggregate, số bản ghi, event, payment attempt hay kết quả trả về.

## 7. Công cụ Java: jqwik

`jqwik` là một framework property-based testing cho Java và tích hợp với JUnit Platform. Test được viết bằng annotation như `@Property`, `@ForAll` và `@Provide`.

Các đoạn code bên dưới là ví dụ theo jqwik; import của JUnit assertion và một số domain type được lược bỏ để tập trung vào property. Những kiểu như `Money`, `TimeRange`, `Stock` và `Reservation` là API miền minh họa, cần thay bằng kiểu thực tế của dự án.

Ví dụ tối thiểu:

```java
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;

class IntegerPropertiesTest {
    @Property
    void addingZeroKeepsTheValue(@ForAll int value) {
        assertEquals(value, value + 0);
    }
}
```

Framework sinh nhiều giá trị `int` thay vì chỉ chạy một giá trị cố định. Số lần thử, seed và chi tiết thực thi có thể cấu hình theo phiên bản jqwik và cấu hình test của dự án.

### 7.1. Dependency và chạy test

Thêm jqwik vào test scope của Maven hoặc Gradle và bảo đảm JUnit Platform được cấu hình theo hướng dẫn của phiên bản đang sử dụng. Ví dụ Maven dependency có dạng:

```xml
<dependency>
    <groupId>net.jqwik</groupId>
    <artifactId>jqwik</artifactId>
    <scope>test</scope>
</dependency>
```

Phiên bản nên được quản lý thống nhất qua dependency management hoặc version catalog của dự án. Không nên sao chép một version cũ mà không kiểm tra tương thích với JDK, JUnit Platform và build plugin hiện tại.
Nếu dự án không quản lý version qua BOM hoặc dependency management, cần khai báo version jqwik cụ thể trong dependency.

## 8. Generator: sinh dữ liệu hợp lệ có chủ đích

Generator quyết định PBT khám phá được những phần nào của miền đầu vào. Generator quá rộng có thể tạo dữ liệu không hợp lệ và khiến test chủ yếu kiểm tra validation. Generator quá hẹp có thể bỏ qua chính những trường hợp dễ gây lỗi.

Với jqwik, `@Provide` khai báo một `Arbitrary`:

```java
import java.math.BigDecimal;
import java.util.Currency;
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.Provide;

@Provide
Arbitrary<Integer> positiveQuantities() {
    return Arbitraries.integers().between(1, 1_000);
}
```

Sau đó dùng tên provider trong `@ForAll`:

```java
@Property
void quantityIsAlwaysPositive(@ForAll("positiveQuantities") int quantity) {
    assertTrue(quantity > 0);
}
```

Property này chủ yếu xác minh generator sinh đúng miền đã định. Giá trị của nó nằm ở việc xây dựng generator dùng chung cho các property nghiệp vụ tiếp theo; tự nó chưa kiểm tra sâu hành vi domain.

### 8.1. Sinh dữ liệu hợp lệ và không hợp lệ

Nên có generator riêng cho hai mục tiêu:

- Generator hợp lệ để kiểm tra hành vi và invariant sau command.
- Generator gần biên hoặc không hợp lệ để kiểm tra constructor/factory từ chối input sai.

Ví dụ:

```java
@Provide
Arbitrary<Integer> validQuantities() {
    return Arbitraries.integers().between(1, 1_000);
}

@Provide
Arbitrary<Integer> invalidQuantities() {
    return Arbitraries.integers().between(-1_000, 0);
}
```

Không nên dùng `filter()` quá nhiều để loại dữ liệu. Filter dày có thể làm generator khó tìm đủ mẫu, giảm hiệu quả hoặc che giấu miền hợp lệ. Hãy sinh trực tiếp từ miền mong muốn khi có thể.

### 8.2. Bao phủ giá trị biên

Generator nên thường xuyên tạo:

- Giá trị nhỏ nhất và lớn nhất.
- Zero và một đơn vị nhỏ nhất.
- Giá trị ngay trước/sau ngưỡng.
- Chuỗi rỗng, độ dài tối đa và ký tự đặc biệt.
- Khoảng rỗng, khoảng có độ dài tối thiểu và hai khoảng liền kề.
- Trạng thái chuyển tiếp ít phổ biến.

Một generator ngẫu nhiên đều có thể hiếm khi sinh ra đúng biên. Có thể dùng `Arbitraries.oneOf`, `frequencyOf`, `edgeCases` hoặc cấu trúc tương đương của framework để tăng tần suất trường hợp quan trọng. Cú pháp cụ thể cần theo jqwik version của dự án.

## 9. Shrinking: tìm phản ví dụ nhỏ hơn

Khi một property thất bại, framework có thể cố gắng rút gọn input để tìm trường hợp nhỏ nhất vẫn làm test sai. Quá trình này gọi là shrinking.

Ví dụ một property thất bại khi số lượng lớn hơn một ngưỡng bất thường. Thay vì phải đọc một input rất lớn, framework có thể tìm một số nhỏ hơn nhưng vẫn tái hiện lỗi.

Shrinking giúp:

- Loại bỏ phần dữ liệu không liên quan.
- Tạo phản ví dụ dễ đọc và dễ chuyển thành regression test.
- Rút ngắn thời gian hiểu lỗi.

Tuy nhiên, shrinker chỉ hoạt động tốt nếu generator và cấu trúc dữ liệu cho phép thu nhỏ có ý nghĩa. Với một object phức tạp, nên tạo arbitrary từ các thành phần nhỏ để framework hiểu cách giảm từng phần.

### 9.1. Không bỏ qua seed và phản ví dụ

Khi property thất bại, lưu lại seed, input đã thu nhỏ và thông tin môi trường theo output của framework. Dùng chúng để tái hiện lỗi. Sau khi sửa, cân nhắc thêm example-based regression test cho phản ví dụ cụ thể nếu đó là một trường hợp nghiệp vụ quan trọng.

## 10. Ví dụ: property cho Money Value Object

Giả sử `Money` là Value Object có currency và amount. Domain quy định chỉ cộng được hai khoản cùng currency, amount được chuẩn hóa theo chính sách tiền tệ.

Một số property có thể là:

- Cộng zero cùng currency giữ nguyên giá trị.
- Cộng hai khoản cùng currency có tính giao hoán nếu phép cộng không áp dụng rounding phụ thuộc thứ tự.
- Currency mismatch bị từ chối.
- Serialization round-trip giữ nguyên currency và amount theo precision contract.

Ví dụ dưới đây giả định `Money.of`, `plus`, `currency` và `amount` là API của Value Object trong domain:

```java
import java.math.BigDecimal;
import java.util.Currency;
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.ForAll;
import net.jqwik.api.Provide;
import net.jqwik.api.Property;

class MoneyPropertiesTest {

    @Provide
    Arbitrary<BigDecimal> amounts() {
        return Arbitraries.longs()
                .between(0, 10_000_000)
                .map(value -> BigDecimal.valueOf(value, 2));
    }

    @Property
    void addingZeroKeepsAmount(@ForAll("amounts") BigDecimal amount) {
        Currency currency = Currency.getInstance("USD");
        Money money = Money.of(amount, currency);
        Money zero = Money.zero(currency);

        assertEquals(money, money.plus(zero));
    }
}
```

Generator giới hạn amount không âm và có hai chữ số thập phân để khớp với contract minh họa. Domain có thể hỗ trợ precision khác hoặc currency không có hai chữ số lẻ; khi đó generator cần phản ánh chính sách thực tế.

### 10.1. Property giao hoán

```java
import java.math.BigDecimal;
import java.util.Currency;
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.Combinators;
import net.jqwik.api.ForAll;
import net.jqwik.api.Provide;
import net.jqwik.api.Property;

class MoneyCommutativityPropertiesTest {

record MoneyPair(Money left, Money right) {}

@Provide
Arbitrary<MoneyPair> sameCurrencyMoneyPairs() {
    Arbitrary<BigDecimal> amounts = Arbitraries.longs()
            .between(0, 10_000_000)
            .map(value -> BigDecimal.valueOf(value, 2));

    return Combinators.combine(amounts, amounts)
            .as((left, right) -> new MoneyPair(
                    Money.of(left, Currency.getInstance("USD")),
                    Money.of(right, Currency.getInstance("USD"))));
}

@Property
void additionIsCommutative(@ForAll("sameCurrencyMoneyPairs") MoneyPair pair) {
    assertEquals(pair.left().plus(pair.right()),
            pair.right().plus(pair.left()));
}
}
```

Property này chỉ đúng nếu quy tắc làm tròn và chuẩn hóa của `Money.plus` bảo toàn tính giao hoán. Nếu nghiệp vụ có rounding ở từng bước, cần xác định luật chính xác trước khi khẳng định property.

## 11. Ví dụ: property cho khoảng thời gian nửa mở

Giả sử `TimeRange` biểu diễn `[startInclusive, endExclusive)` và không cho phép khoảng rỗng. Có thể sinh các cặp Instant theo epoch milli trong một miền hữu hạn:

```java
import java.time.Instant;
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.Combinators;
import net.jqwik.api.ForAll;
import net.jqwik.api.Provide;
import net.jqwik.api.Property;

class TimeRangePropertiesTest {

    @Provide
    Arbitrary<Instant> instants() {
        return Arbitraries.longs()
                .between(1_700_000_000_000L, 1_800_000_000_000L)
                .map(Instant::ofEpochMilli);
    }

    @Provide
    Arbitrary<TimeRange> validRanges() {
        return Combinators.combine(instants(), Arbitraries.longs().between(1, 86_400_000))
                .as((start, lengthMillis) -> new TimeRange(
                        start,
                        start.plusMillis(lengthMillis)));
    }

    @Property
    void rangeContainsItsStart(@ForAll("validRanges") TimeRange range) {
        assertTrue(range.contains(range.startInclusive()));
    }

    @Property
    void rangeDoesNotContainItsEnd(@ForAll("validRanges") TimeRange range) {
        assertFalse(range.contains(range.endExclusive()));
    }

    @Property
    void overlapIsSymmetric(
            @ForAll("validRanges") TimeRange left,
            @ForAll("validRanges") TimeRange right) {
        assertEquals(left.overlaps(right), right.overlaps(left));
    }
}
```

Những property này kiểm tra quy ước biên và tính đối xứng của overlap trên nhiều khoảng khác nhau. Cần thêm example-based test cho hai khoảng chạm nhau đúng tại biên, vì đây là trường hợp có ý nghĩa nghiệp vụ quan trọng.

## 12. Ví dụ: bảo vệ invariant của Aggregate

Property của Aggregate thường có dạng: sinh trạng thái ban đầu và command hợp lệ, thực hiện hành vi, sau đó xác minh invariant vẫn đúng.

Giả sử Stock Aggregate có số lượng khả dụng và thao tác reserve:

```java
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.ForAll;
import net.jqwik.api.Provide;
import net.jqwik.api.Property;

class StockPropertiesTest {

@Property
void stockQuantityNeverBecomesNegative(
        @ForAll("availableQuantities") int available,
        @ForAll("requestedQuantities") int requested) {
    Stock stock = Stock.withAvailableQuantity(available);
    int availableBefore = stock.availableQuantity();
    int reservedBefore = stock.reservedQuantity();

    ReserveResult result = stock.reserve(requested);

    assertTrue(stock.availableQuantity() >= 0);
    assertTrue(stock.reservedQuantity() >= 0);
    assertEquals(requested <= availableBefore, result.accepted());
    if (result.accepted()) {
        assertEquals(availableBefore - requested, stock.availableQuantity());
        assertEquals(reservedBefore + requested, stock.reservedQuantity());
    } else {
        assertEquals(availableBefore, stock.availableQuantity());
        assertEquals(reservedBefore, stock.reservedQuantity());
    }
}

@Provide
Arbitrary<Integer> availableQuantities() {
    return Arbitraries.integers().between(0, 10_000);
}

@Provide
Arbitrary<Integer> requestedQuantities() {
    return Arbitraries.integers().between(1, 10_000);
}
}
```

Ví dụ giả định `reserve` trả về `ReserveResult` có method `accepted()` và từ chối mà không thay đổi trạng thái khi không đủ hàng. Nếu domain dùng exception cho business rejection, hãy viết property theo contract đó và xác minh trạng thái không đổi sau exception. Test kiểm tra cả kết quả và trạng thái trước/sau để bảo đảm Aggregate không chỉ giữ số lượng không âm bằng cách âm thầm bỏ qua mọi request.

### 12.1. Kiểm tra quan hệ giữa kết quả và trạng thái

Property có thể khẳng định:

- Nếu reservation được chấp nhận, available giảm đúng quantity và reserved tăng tương ứng.
- Nếu reservation bị từ chối vì thiếu hàng, trạng thái tồn không thay đổi.
- Tổng lượng đã phân bổ không vượt lượng được phép.
- Một reservation được release hợp lệ không làm lượng khả dụng vượt giới hạn.

Các property cần tính đến những yếu tố khác như hàng đang hỏng, hàng đã xuất hoặc điều chỉnh tồn kho. Không nên áp dụng một công thức đơn giản nếu mô hình miền có nhiều loại số lượng.

## 13. Property cho chuỗi command và state machine

Invariant của Aggregate không chỉ cần đúng sau một command. Một chuỗi thao tác có thể tạo ra trạng thái lỗi dù từng thao tác riêng lẻ có vẻ hợp lệ.

Ví dụ reservation:

```text
Create -> Reserve -> Extend -> Release -> Release again
```

Hoặc Order:

```text
Draft -> Submit -> Confirm -> Cancel
```

Có thể sinh chuỗi command và kiểm tra sau mỗi bước:

- Aggregate không rơi vào trạng thái bất hợp lệ.
- Command không được phép ở trạng thái hiện tại bị từ chối.
- Chuyển trạng thái thành công luôn tuân theo transition được định nghĩa.
- Event phát ra tương ứng với hành động thực sự được chấp nhận.

Với jqwik, có thể xây arbitrary cho danh sách command hợp lệ hoặc mô hình command/state-machine tùy phiên bản và cấu trúc test. Cách đơn giản là sinh một danh sách input rồi áp dụng tuần tự trong test. Cần tránh tạo danh sách chỉ gồm các command hợp lệ nếu mục tiêu là kiểm tra khả năng từ chối command sai trạng thái.

### 13.1. Model-based testing

Với quy trình phức tạp, có thể tạo một model trạng thái đơn giản độc lập để dự đoán kết quả, rồi so sánh với Aggregate thực. Model phải đơn giản và diễn đạt quy tắc theo cách khác với implementation; nếu copy cùng thuật toán, hai bên có thể cùng mắc một lỗi.

## 14. Metamorphic testing cho quy tắc nghiệp vụ

Metamorphic property hữu ích khi khó viết expected result cho mọi input nhưng biết một phép biến đổi phải có ảnh hưởng nhất định.

Ví dụ Inventory:

- Nếu một yêu cầu được chấp nhận với available = 10 và requested = 4, tăng available lên 12 trong khi giữ nguyên các điều kiện khác không nên khiến yêu cầu đó bị từ chối.
- Nếu giảm requested quantity trong một policy chỉ giới hạn theo lượng hàng, một request được chấp nhận không nên trở thành không đủ hàng.

Ví dụ khoảng thời gian:

- Dịch cả hai đầu mút của hai khoảng cùng một Duration không làm thay đổi quan hệ overlap.
- Nếu tăng end của một khoảng mà giữ start cố định, các thời điểm đã thuộc khoảng trước đó vẫn thuộc khoảng mới.

Ví dụ tìm kiếm:

- Thêm một bộ lọc AND không nên làm tập kết quả rộng hơn.
- Bỏ một bộ lọc AND không nên làm tập kết quả hẹp hơn.

Metamorphic property cần nêu giả định. Nếu policy thay đổi theo thời gian, tier khách hàng hoặc ngưỡng khác, phép biến đổi có thể không còn giữ quy luật.

## 15. Round-trip property cho serialization và persistence

DDD thường có nhiều adapter chuyển đổi giữa domain model, API DTO, event schema và persistence record. Round-trip test kiểm tra ngữ nghĩa không bị mất qua quá trình chuyển đổi.

Ví dụ:

```java
@Property
void moneyJsonRoundTripPreservesValue(@ForAll("validMoney") Money money) {
    String json = mapper.writeValueAsString(moneyMapper.toDto(money));
    MoneyDto dto = mapper.readValue(json, MoneyDto.class);
    Money restored = moneyMapper.toDomain(dto);

    assertEquals(money, restored);
}
```

Đây là ví dụ khái niệm; mapper và exception handling cần được điều chỉnh theo codebase. Property có thể áp dụng cho:

- Domain Value Object ↔ API DTO.
- Aggregate state ↔ persistence representation.
- Domain Event ↔ event schema.
- Money/Quantity/DateRange ↔ JSON hoặc database type.

Không nhất thiết yêu cầu serialized JSON giống từng ký tự. Thứ tự field, whitespace hoặc format tương đương có thể khác; điều quan trọng là domain meaning được giữ đúng theo contract.

## 16. Property cho idempotency và message handling

Với một use case idempotent, cùng command và cùng key được gửi lặp không nên tạo thêm tác động. Có thể kiểm tra ở application/integration level:

Ví dụ giả định test fixture đã cung cấp `handler`, `orderRepository` và provider `createOrderRequests()` sinh request hợp lệ; phần generator request phụ thuộc vào schema command cụ thể của dự án.

```java
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.ForAll;
import net.jqwik.api.Provide;
import net.jqwik.api.Property;

class IdempotencyPropertiesTest {

@Property
void replayingSameCreateCommandDoesNotCreateAnotherOrder(
        @ForAll("createOrderRequests") CreateOrderRequest request,
        @ForAll("idempotencyKeys") String key) {

    StoredResponse first = handler.handle(key, request);
    StoredResponse second = handler.handle(key, request);

    assertEquals(first.resourceId(), second.resourceId());
    assertEquals(1, orderRepository.countByBusinessRequestKey(key));
}

@Provide
Arbitrary<String> idempotencyKeys() {
    return Arbitraries.strings().alpha().ofMinLength(16).ofMaxLength(32);
}
}
```

Test này minh họa property ở mức use case và cần test fixture/database được cô lập cho mỗi lần chạy. Nếu handler có random ID hoặc external provider, test phải kiểm soát các dependency đó.

Với consumer message, property tương tự có thể xác minh xử lý cùng message ID nhiều lần chỉ cập nhật Aggregate một lần. Nhưng PBT tuần tự không thay thế test hai transaction đồng thời tranh chấp cùng key; concurrency cần integration test riêng trên storage thực tế.

## 17. Generator cho Aggregate phức tạp

Khi Aggregate có nhiều field và invariant liên kết, không nên tạo object bằng cách sinh từng field tùy ý rồi gọi constructor nếu phần lớn object không hợp lệ.

Một số chiến lược:

- Sinh dữ liệu nền hợp lệ rồi gọi factory miền.
- Tạo arbitrary từ các Value Object đã có generator riêng.
- Dùng builder/test fixture có kiểm tra để tạo Aggregate hợp lệ.
- Tạo generator riêng cho trạng thái cụ thể như `DraftOrder`, `SubmittedOrder` hoặc `ActiveReservation`.
- Tạo generator cho command hợp lệ và generator cho command vi phạm từng quy tắc.

Ví dụ cấu trúc:

```java
@Provide
Arbitrary<Order> draftOrders() {
    return Combinators.combine(orderIds(), customerIds(), orderLines())
            .as((id, customerId, lines) -> Order.draft(id, customerId, lines));
}
```

`Order.draft` cần là factory miền bảo đảm Aggregate hợp lệ. Generator không nên truy cập private field hoặc bỏ qua constructor để tạo trạng thái mà production code không thể tạo.

### 17.1. Sinh trạng thái và sinh hành động là hai việc khác nhau

Với stateful property, generator có thể tạo một Aggregate ban đầu hợp lệ rồi sinh một chuỗi command. Nên kiểm tra sau mỗi command và lưu lại sequence gây lỗi. Khi shrink, framework cần giảm được cả số command lẫn dữ liệu trong command để phản ví dụ dễ hiểu.

## 18. Coverage và chất lượng generator

PBT không bảo đảm mọi giá trị trong miền đều được kiểm tra. Nó kiểm tra các mẫu do generator sinh ra trong số lần thử đã cấu hình.

Hãy đánh giá generator theo các câu hỏi:

- Có bao phủ các giá trị biên không?
- Có sinh trạng thái hiếm nhưng hợp lệ không?
- Có sinh input không hợp lệ khi cần kiểm tra validation không?
- Có tránh phần lớn input vô nghĩa không?
- Có bao phủ các nhánh domain quan trọng không?
- Có làm cho shrinker rút gọn được dữ liệu không?

Có thể dùng statistics/label của framework để quan sát phân bố input, chẳng hạn tỷ lệ amount bằng zero, range liền kề hoặc trạng thái cancelled. Nếu 1.000 lần chạy không sinh được một trường hợp quan trọng, cần cải thiện generator thay vì chỉ tăng số lần thử.

### 18.1. Đừng để generator chỉ sinh trường hợp dễ

Nếu generator chỉ tạo quantity từ 1 đến 10 và stock từ 100 đến 1.000, property “không vượt tồn” sẽ luôn đi qua mà không kiểm tra tình huống hết hàng. Cần sinh cả quan hệ requested > available, requested = available và requested < available.

Một generator tốt được thiết kế từ cấu trúc miền và các nhánh quyết định, không chỉ từ kiểu dữ liệu của field.

## 19. Determinism và tái hiện lỗi

Property test thường dùng random seed để sinh dữ liệu, nhưng một lần chạy phải có thể được tái hiện khi thất bại.

Thực hành tốt:

- Giữ output test có seed và sample gây lỗi.
- Không phụ thuộc thời gian hệ thống; dùng Clock cố định.
- Không gọi API ngoài thật trong property test.
- Không chia sẻ mutable fixture giữa các lần thử.
- Không dùng global counter hoặc random source ngoài framework nếu không kiểm soát.
- Mỗi lần thử nên có trạng thái database riêng hoặc transaction/cleanup rõ.
- Nếu test có concurrency, kiểm soát thread, barrier và timeout để tránh flakiness.

Một test có seed cố định giúp tái hiện lỗi nhưng không nên khiến framework chỉ kiểm tra cùng một tập mẫu vĩnh viễn. CI có thể dùng seed được ghi nhận khi debug và vẫn cho phép khám phá thêm mẫu theo cấu hình phù hợp.

## 20. PBT không chứng minh tính đúng tuyệt đối

Nếu property chạy 1.000 lần mà không thất bại, điều đó không chứng minh quy tắc đúng với mọi input. Kết quả chỉ cung cấp bằng chứng trên các mẫu do generator chọn và trong giới hạn test.

Các giới hạn cần nhớ:

- Generator có thể bỏ sót miền quan trọng.
- Property có thể được viết sai hoặc quá yếu.
- Oracle và implementation có thể cùng dùng một giả định sai.
- Framework chỉ thử hữu hạn lần.
- Test trong bộ nhớ không chứng minh database concurrency.
- Test adapter với fake không chứng minh provider ngoài thực hiện đúng contract.

Đối với invariant quan trọng, kết hợp PBT với example-based tests, database constraints, transaction/concurrency tests và review nghiệp vụ.

## 21. Kết hợp PBT với các tầng kiểm thử DDD

| Tầng | Mục tiêu | Ví dụ property phù hợp |
|---|---|---|
| Value Object | Luật giá trị và phép toán | Money cộng zero, TimeRange overlap đối xứng |
| Entity/Aggregate | Invariant sau hành vi | Stock không âm sau reserve/release |
| Domain Service/Policy | Quy tắc tổng hợp | Tăng stock không làm request hợp lệ trở thành thiếu hàng |
| Application Service | Điều phối và idempotency | Retry cùng key không tạo Order mới |
| Repository/Mapper | Bảo toàn dữ liệu | Round-trip Aggregate giữ state cần thiết |
| API/ACL/Event adapter | Contract và mapping | Encode/decode không mất ngữ nghĩa |
| Consumer/Outbox | Xử lý message lặp | Cùng message ID không áp dụng event hai lần |

PBT thường hiệu quả nhất ở domain logic thuần vì generator có thể chạy nhanh và lặp nhiều lần. Với tầng infrastructure, cần kiểm soát chi phí và trạng thái test; đôi khi một bộ integration tests có mục tiêu rõ sẽ phù hợp hơn.

## 22. Ví dụ: kiểm tra quy tắc Reservation

Giả sử Reservation có các thuộc tính:

- `quantity` phải dương.
- `createdAt` không null.
- `expiresAt` phải sau `createdAt`.
- Reservation hết hạn tại `now >= expiresAt`.
- Chỉ reservation `ACTIVE` mới có thể được release.

Các property có thể được chia nhỏ:

1. Factory không tạo reservation với quantity không hợp lệ.
2. Factory luôn tạo `expiresAt > createdAt` khi TTL dương.
3. Trước `expiresAt`, reservation chưa hết hạn.
4. Tại `expiresAt`, reservation đã hết hạn.
5. Release một reservation active chuyển trạng thái đúng một lần.
6. Release lặp không làm thay đổi thêm lượng hàng hoặc phát thêm tác động.

Ví dụ property về thời hạn:

```java
@Property
void positiveTtlAlwaysProducesFutureExpiry(
        @ForAll("instants") Instant createdAt,
        @ForAll("positiveTtls") Duration ttl) {
    Reservation reservation = Reservation.create(
            reservationId(),
            List.of(aReservationLine()),
            createdAt,
            ttl
    );

    assertTrue(reservation.expiresAt().isAfter(createdAt));
}

@Provide
Arbitrary<Duration> positiveTtls() {
    return Arbitraries.longs().between(1, 86_400)
            .map(Duration::ofSeconds);
}
```

Property về biên hết hạn:

```java
@Property
void reservationExpiresAtItsExclusiveDeadline(
        @ForAll("instants") Instant createdAt,
        @ForAll("positiveTtls") Duration ttl) {
    Reservation reservation = Reservation.create(
            reservationId(), List.of(aReservationLine()), createdAt, ttl);

    assertFalse(reservation.isExpiredAt(reservation.expiresAt().minusNanos(1)));
    assertTrue(reservation.isExpiredAt(reservation.expiresAt()));
}
```

Các đoạn code giả định domain API tương ứng. Test class cần khai báo provider `instants()` như mục 11 và tạo ID/line bằng fixture hoặc generator riêng để mỗi lần thử có dữ liệu hợp lệ và độc lập.

## 23. Quy trình đưa PBT vào codebase

1. **Chọn một invariant rõ:** bắt đầu từ Value Object hoặc Aggregate có quy tắc tổng quát.
2. **Viết property bằng ngôn ngữ miền:** nêu điều gì phải luôn đúng và các giả định.
3. **Xác định miền input:** giá trị hợp lệ, không hợp lệ và trường hợp biên.
4. **Tạo generator nhỏ:** tái sử dụng generator cho Value Object và trạng thái hợp lệ.
5. **Viết property test:** dùng jqwik hoặc framework phù hợp với stack.
6. **Kiểm tra phân bố:** xác minh generator thực sự sinh các trường hợp quan trọng.
7. **Chạy và xem shrink:** bảo đảm phản ví dụ có thể hiểu và tái hiện.
8. **Bổ sung regression example:** chuyển lỗi quan trọng thành test cụ thể dễ đọc.
9. **Mở rộng sang command sequence:** khi invariant phụ thuộc lịch sử trạng thái.
10. **Bổ sung integration/concurrency tests:** cho database, message và phụ thuộc ngoài.
11. **Đưa vào CI:** cấu hình số lần thử và thời gian chạy phù hợp.
12. **Bảo trì generator:** cập nhật khi domain rule hoặc kiểu dữ liệu thay đổi.

## 24. Các lỗi thường gặp khi viết Property-based Tests

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Property chỉ lặp lại một ví dụ | Không tăng khả năng khám phá input | Viết phát biểu tổng quát về invariant hoặc quan hệ |
| Generator quá hẹp | Bỏ qua giá trị biên và nhánh lỗi | Thiết kế từ domain partition và boundary |
| Generator tạo object không hợp lệ | Test chủ yếu thất bại ở bước setup | Dùng factory miền và arbitrary hợp lệ riêng |
| Dùng filter quá nhiều | Generator khó tạo đủ mẫu | Sinh trực tiếp từ miền hợp lệ |
| Property sai hoặc quá yếu | Test xanh dù implementation sai | Review property với chuyên gia và thêm counterexample |
| Bỏ qua shrinking | Khó hiểu input thất bại phức tạp | Dùng cấu trúc dữ liệu có thể shrink và lưu seed |
| Dùng thời gian thật | Test chập chờn ở biên | Tiêm Clock cố định |
| Gọi provider thật trong mỗi lần thử | Test chậm, không ổn định và có side effect | Dùng fake/contract test riêng |
| Dùng PBT để thay mọi example test | Khó đọc các quyết định nghiệp vụ quan trọng | Kết hợp hai cách kiểm thử |
| Nghĩ test tuần tự chứng minh concurrency | Bỏ sót race condition | Test đồng thời trên database/storage thực |
| Không lưu seed hoặc phản ví dụ | Khó tái hiện lỗi CI | Lưu thông tin chạy và thêm regression test |
| Tăng số lần thử mà không xem coverage | Tốn thời gian nhưng vẫn bỏ sót nhánh | Đo phân bố generator và bổ sung edge cases |

## 25. Checklist chọn và triển khai PBT

- [ ] Có invariant hoặc property tổng quát được diễn đạt rõ.
- [ ] Property có ý nghĩa nghiệp vụ và không chỉ lặp lại implementation.
- [ ] Các giả định và điều kiện áp dụng được nêu rõ.
- [ ] Generator đại diện cho miền input cần kiểm tra.
- [ ] Có generator riêng cho dữ liệu hợp lệ và không hợp lệ khi cần.
- [ ] Giá trị biên và nhánh ít phổ biến được bao phủ có chủ đích.
- [ ] Generator không phụ thuộc external service hoặc đồng hồ thật.
- [ ] Shrinking tạo được phản ví dụ dễ đọc.
- [ ] Seed và input lỗi có thể được tái hiện.
- [ ] Property kiểm tra cả kết quả lẫn invariant sau hành vi khi phù hợp.
- [ ] Có example-based tests cho các quyết định nghiệp vụ trọng yếu.
- [ ] Có integration/concurrency tests cho persistence và message boundary.
- [ ] Số lần thử và thời gian CI được cân bằng với độ phức tạp test.
- [ ] Generator được cập nhật khi domain contract thay đổi.

## 26. Kết nối với các khái niệm DDD khác

Property-based testing hỗ trợ xác minh các invariant mà Aggregate Root và Value Object bảo vệ. Value Object thường có các luật đại số và round-trip dễ kiểm tra. Aggregate có thể được kiểm tra sau nhiều chuỗi command để xác minh trạng thái luôn hợp lệ. Domain Service và Policy có thể được kiểm tra bằng metamorphic properties. Repository, serializer và ACL có thể dùng round-trip properties để phát hiện mất ngữ nghĩa khi chuyển đổi.

PBT không thay thế việc mô hình hóa đúng. Nếu invariant chưa được xác định, generator và framework không thể tự suy ra nghiệp vụ mong muốn. Bắt đầu từ ngôn ngữ chung với chuyên gia, diễn đạt quy tắc thành property có thể kiểm tra, rồi dùng generator để khám phá nhiều trường hợp. Khi kết hợp PBT với example-based, integration và concurrency tests, đội phát triển có thêm bằng chứng rằng mô hình miền giữ được invariant trên nhiều đầu vào và chuỗi hành vi khác nhau.
