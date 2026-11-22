# Kiểm thử Value Object về tính hợp lệ, so sánh và tính bất biến

Trong Domain-Driven Design (DDD), Value Object biểu diễn một khái niệm miền bằng giá trị của các thuộc tính, thay vì bằng identity riêng. Ví dụ: Money, Quantity, EmailAddress, ProductCode, DateRange và Address. Hai Value Object được xem là bằng nhau khi chúng biểu diễn cùng một giá trị theo quy tắc của domain.

Vì Value Object thường nằm ở đầu vào và đầu ra của nhiều Entity, Aggregate và use case, lỗi trong chúng có thể lan rộng khắp hệ thống. Một Quantity chấp nhận số âm, một Money so sánh sai do scale của BigDecimal, hoặc một Address bị thay đổi qua collection bên ngoài đều có thể làm quy tắc nghiệp vụ mất hiệu lực.

Kiểm thử Value Object cần tập trung vào ba nhóm cam kết:

1. **Tính hợp lệ:** chỉ những giá trị đáp ứng quy tắc miền mới được tạo.
2. **So sánh theo giá trị:** equals, hashCode và các phép so sánh phản ánh đúng ngữ nghĩa nghiệp vụ.
3. **Tính bất biến:** sau khi tạo, giá trị không thay đổi ngoài ý muốn, kể cả khi dữ liệu đầu vào hoặc đối tượng được trả ra bị thay đổi.

Bài học này trình bày cách thiết kế test cho các cam kết đó bằng Java và JUnit, đồng thời chỉ ra cách kiểm tra normalization, boundary cases, collection, property-based testing và ranh giới giữa Value Object với Aggregate.

## 1. Value Object và lý do cần kiểm thử riêng

Một Value Object thường có các đặc điểm:

- Không có identity độc lập như Entity.
- Được so sánh dựa trên toàn bộ thuộc tính có ý nghĩa.
- Thường bất biến sau khi tạo.
- Có thể tự bảo vệ quy tắc hợp lệ của giá trị.
- Có thể kết hợp với Value Object khác để biểu diễn một khái niệm lớn hơn.

Ví dụ, Quantity không phải chỉ là một số nguyên. Nó là số lượng trong một ngữ cảnh nghiệp vụ và có thể yêu cầu lớn hơn 0. Money không chỉ là BigDecimal; nó gồm số tiền và đơn vị tiền tệ. DateRange không chỉ là hai ngày; nó còn có quy tắc về thứ tự và cách tính hai đầu khoảng.

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be greater than zero"
            );
        }
    }
}
~~~

Nếu Quantity được tạo thành công, các phần khác của domain có thể dựa vào cam kết rằng giá trị của nó luôn dương. Điều đó giảm việc lặp lại kiểm tra trong OrderLine, Inventory hoặc Reservation.

Kiểm thử Value Object giúp xác nhận cam kết được thực thi tại nơi tạo giá trị, thay vì chỉ được ghi trong tài liệu hoặc dựa vào caller.

### Value Object khác Entity như thế nào khi kiểm thử?

| Khía cạnh | Value Object | Entity |
|---|---|---|
| Identity | Không có identity riêng | Có identity ổn định |
| Equality | Dựa trên giá trị | Thường dựa trên identity |
| Thay đổi | Thường bất biến | State có thể thay đổi qua behavior |
| Test chính | Validation, equality, hashCode, immutability | Lifecycle, state transition, invariant |
| Ví dụ | Money, Quantity, Address | Order, Customer, Payment |

Không nên viết test Value Object như test lifecycle của Aggregate. Một Value Object thường được kiểm tra độc lập, nhanh và không cần database hoặc framework.

## 2. Ba nhóm hợp đồng cần kiểm tra

Mỗi Value Object nên có một bộ test tương ứng với semantics của nó.

| Nhóm | Câu hỏi kiểm thử | Ví dụ |
|---|---|---|
| Validation | Giá trị nào được chấp nhận hoặc từ chối? | Quantity không nhận 0 hoặc số âm |
| Equality và comparison | Hai giá trị được coi là bằng nhau khi nào? | Money cùng amount và currency bằng nhau |
| Immutability | Giá trị có thể đổi sau khi tạo không? | Sửa list nguồn không làm Address thay đổi |

Ngoài ba nhóm chính, một Value Object có thể cần test:

- Normalization và canonical representation.
- Boundary values.
- Ordering hoặc comparison.
- Serialization/deserialization nếu đó là contract của boundary.
- Tương thích với Set, Map hoặc sorting.
- Quy tắc kết hợp với Value Object khác.

Không phải Value Object nào cũng cần mọi loại test. Hãy bắt đầu từ quy tắc miền thực sự có ý nghĩa.

## 3. Kiểm thử validation ở constructor hoặc factory

Một Value Object nên ngăn giá trị không hợp lệ xuất hiện. Validation thường được thực hiện ở constructor, static factory hoặc một hàm tạo có tên rõ nghĩa.

Ví dụ Quantity:

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new InvalidQuantity(value);
        }
    }
}
~~~

Test cần xác nhận cả hai phía:

- Giá trị hợp lệ được tạo và giữ nguyên.
- Giá trị không hợp lệ bị từ chối với lỗi phù hợp.

~~~java
class QuantityTest {
    @Test
    void acceptsPositiveQuantity() {
        Quantity quantity = new Quantity(3);

        assertEquals(3, quantity.value());
    }

    @Test
    void rejectsZero() {
        assertThrows(
                InvalidQuantity.class,
                () -> new Quantity(0)
        );
    }

    @Test
    void rejectsNegativeValue() {
        assertThrows(
                InvalidQuantity.class,
                () -> new Quantity(-1)
        );
    }
}
~~~

Nếu code dùng IllegalArgumentException thay vì InvalidQuantity, test phải phản ánh đúng contract đã chọn. Với domain lớn, exception riêng có thể giúp application phân biệt lỗi nghiệp vụ và ánh xạ chúng rõ ràng.

### Kiểm tra exception đủ cụ thể

Test chỉ xác nhận “có exception” đôi khi chưa đủ. Một bug có thể ném NullPointerException thay cho lỗi validation mà test vẫn pass nếu chỉ dùng assertThrows(RuntimeException.class, ...).

Nên kiểm tra loại lỗi chính xác:

~~~java
assertThrows(
        InvalidQuantity.class,
        () -> new Quantity(0)
);
~~~

Nếu exception mang dữ liệu hữu ích như giá trị bị từ chối hoặc reason code, có thể kiểm tra thêm:

~~~java
InvalidQuantity error = assertThrows(
        InvalidQuantity.class,
        () -> new Quantity(-2)
);

assertEquals(-2, error.rejectedValue());
~~~

Không nên kiểm tra toàn bộ message nếu message chỉ phục vụ hiển thị và có thể được bản địa hóa. Ưu tiên type hoặc error code ổn định.

## 4. Kiểm thử boundary values

Nhiều lỗi validation xuất hiện ở biên: 0, 1, giá trị tối đa, giá trị ngay trên hoặc dưới ngưỡng.

Với Quantity có quy tắc lớn hơn 0:

| Giá trị | Kết quả |
|---:|---|
| -1 | Từ chối |
| 0 | Từ chối |
| 1 | Chấp nhận |
| 2 | Chấp nhận |

Với một Value Object có giới hạn tối đa, hãy kiểm tra cả max và max + 1. Với khoảng ngày, kiểm tra ngày bắt đầu bằng ngày kết thúc, ngày kết thúc trước ngày bắt đầu và các biên inclusive/exclusive theo policy.

JUnit hỗ trợ parameterized test:

~~~java
@ParameterizedTest
@ValueSource(ints = {-10, -1, 0})
void rejectsNonPositiveQuantity(int value) {
    assertThrows(
            InvalidQuantity.class,
            () -> new Quantity(value)
    );
}

@ParameterizedTest
@ValueSource(ints = {1, 2, 100})
void acceptsPositiveQuantity(int value) {
    assertEquals(value, new Quantity(value).value());
}
~~~

Test theo bảng dữ liệu giúp thể hiện quy tắc ngắn gọn và bổ sung trường hợp mới dễ dàng.

### Kiểm tra giới hạn theo domain, không theo phỏng đoán

Không tự đặt max quantity hoặc max length chỉ để test có thêm boundary. Giới hạn phải đến từ chính sách nghiệp vụ, giới hạn kỹ thuật được chấp nhận hoặc contract đã thống nhất.

Ví dụ, giới hạn độ dài ProductCode có thể đến từ chuẩn mã sản phẩm. Giới hạn số chữ số thập phân của Money có thể đến từ currency hoặc chính sách tính toán.

## 5. Phân biệt structural validation và semantic validation

Một chuỗi có thể đúng cấu trúc nhưng vẫn không hợp lệ trong domain.

Ví dụ:

- ProductCode có đúng pattern nhưng mã không được phép dùng trong catalog hiện tại.
- DateRange có hai ngày hợp lệ nhưng khoảng kết thúc trước ngày bắt đầu.
- Money có amount hợp lệ nhưng currency không tương thích với giao dịch.
- EmailAddress có hình thức hợp lệ nhưng không được phép làm địa chỉ liên hệ theo policy của doanh nghiệp.

Có thể chia validation thành:

| Loại | Ví dụ | Nơi phù hợp |
|---|---|---|
| Structural | Không null, không blank, format đúng | Value Object hoặc boundary |
| Semantic | End date không trước start date | Value Object |
| Contextual | Sản phẩm đang được bán trong catalog | Application/domain service |
| Stateful | Đơn đang ở trạng thái cho phép đổi địa chỉ | Aggregate |
| Persistence | Mã duy nhất trong phạm vi tenant | Database và use case |

Không nên tải repository hoặc gọi API bên ngoài từ constructor Value Object chỉ để kiểm tra contextual rule. Value Object nên bảo vệ các quy tắc nội tại của giá trị. Quy tắc phụ thuộc state hoặc dữ liệu bên ngoài thuộc use case hoặc domain service có đủ ngữ cảnh.

## 6. Kiểm thử normalization và canonicalization

Một số giá trị có nhiều representation nhưng domain xem chúng là cùng một giá trị. Khi đó Value Object có thể chuẩn hóa đầu vào thành canonical representation.

Ví dụ ProductCode không phân biệt chữ hoa/chữ thường và bỏ khoảng trắng ở hai đầu:

~~~java
public record ProductCode(String value) {
    public ProductCode {
        Objects.requireNonNull(value, "value");

        value = value.trim().toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z0-9-]{3,20}")) {
            throw new InvalidProductCode(value);
        }
    }
}
~~~

Test normalization:

~~~java
@Test
void trimsAndNormalizesProductCode() {
    ProductCode code = new ProductCode("  ab-120 ");

    assertEquals("AB-120", code.value());
}

@Test
void equivalentRepresentationsAreEqual() {
    ProductCode first = new ProductCode("ab-120");
    ProductCode second = new ProductCode(" AB-120 ");

    assertEquals(first, second);
}
~~~

Normalization cần được quyết định bởi domain. Không phải chuỗi nào cũng nên trim, lowercase hoặc bỏ dấu. Với email, mã định danh hoặc tên người, quy tắc chuẩn hóa cần được xác định cẩn thận; không nên áp dụng một thao tác chung chỉ vì thuận tiện.

### Kiểm thử idempotence của normalization

Một phép chuẩn hóa tốt thường có tính idempotent:

\[
normalize(normalize(x)) = normalize(x)
\]

Nghĩa là chuẩn hóa một giá trị đã chuẩn hóa không làm thay đổi nó lần nữa.

Test có thể tạo một ProductCode từ giá trị đã được canonicalize và xác nhận representation không đổi.

## 7. Equality của Value Object

Equality là phần cốt lõi của Value Object. Hai instance riêng biệt có thể bằng nhau nếu tất cả thuộc tính có ý nghĩa theo domain bằng nhau.

Ví dụ:

~~~java
ProductCode first = new ProductCode("AB-120");
ProductCode second = new ProductCode("AB-120");

assertEquals(first, second);
assertNotSame(first, second);
~~~

assertEquals kiểm tra equality theo equals; assertNotSame xác nhận hai object không phải cùng reference trong bộ nhớ.

Một Value Object thường cần tuân thủ các tính chất của equals:

1. **Reflexive:** x.equals(x) là true.
2. **Symmetric:** nếu x.equals(y) là true thì y.equals(x) cũng true.
3. **Transitive:** nếu x bằng y và y bằng z thì x bằng z.
4. **Consistent:** kết quả không đổi khi các thuộc tính liên quan không đổi.
5. **Non-null:** x.equals(null) là false.

Với Java record, compiler sinh equals và hashCode dựa trên components. Tuy nhiên, developer vẫn phải quyết định components nào thực sự thuộc giá trị miền và có cần canonicalize trước khi so sánh hay không.

### Kiểm tra các thuộc tính ảnh hưởng equality

Ví dụ Money có amount và currency. Hai Money chỉ bằng nhau nếu cả số tiền và đơn vị tiền tệ tương ứng theo quy tắc domain.

~~~java
@Test
void moneyEqualityIncludesCurrency() {
    Money usd = new Money(new BigDecimal("10.00"), Currency.getInstance("USD"));
    Money eur = new Money(new BigDecimal("10.00"), Currency.getInstance("EUR"));

    assertNotEquals(usd, eur);
}
~~~

Không được chỉ so sánh amount rồi bỏ qua currency. 10 USD và 10 EUR không phải cùng một giá trị.

### Equality không phải cùng object

Một test Value Object chỉ dùng assertSame là sai mục tiêu. Value Object thường được tạo mới nhiều lần và vẫn phải được so sánh theo giá trị.

## 8. Kiểm thử equals và hashCode

Java yêu cầu hai object bằng nhau theo equals phải có cùng hashCode:

\[
x.equals(y) \Rightarrow x.hashCode() = y.hashCode()
\]

Chiều ngược lại không bắt buộc: hai object khác nhau vẫn có thể có hashCode trùng nhau.

Test cơ bản:

~~~java
@Test
void equalProductCodesHaveSameHashCode() {
    ProductCode first = new ProductCode("ab-120");
    ProductCode second = new ProductCode(" AB-120 ");

    assertEquals(first, second);
    assertEquals(first.hashCode(), second.hashCode());
}
~~~

Hash-based collections phụ thuộc contract này. Nếu equals đúng nhưng hashCode không nhất quán, HashSet hoặc HashMap có thể không tìm được key dù key bằng nhau.

~~~java
@Test
void equivalentValuesBehaveAsOneSetElement() {
    Set<ProductCode> codes = new HashSet<>();

    codes.add(new ProductCode("ab-120"));
    codes.add(new ProductCode(" AB-120 "));

    assertEquals(1, codes.size());
}
~~~

Test collection giúp kiểm tra equality và hashCode trong tình huống sử dụng thực tế.

### Kiểm tra nhiều thuộc tính

Với Value Object nhiều components, nên tạo test xác nhận thay đổi từng component có ý nghĩa sẽ làm equality thay đổi.

Ví dụ:

- Money khác amount thì không bằng nhau.
- Money khác currency thì không bằng nhau.
- DateRange khác start hoặc end thì không bằng nhau.
- Address khác postal code nếu postal code là phần của giá trị miền.

Không đưa field kỹ thuật như database row ID hoặc timestamp tạo object vào equality nếu chúng không thuộc semantics của Value Object.

## 9. Kiểm thử so sánh và thứ tự

Equality và ordering là hai contract khác nhau.

- equals trả lời hai giá trị có được xem là cùng một giá trị không.
- compareTo hoặc comparator xác định thứ tự sắp xếp.
- isGreaterThan/isLessThan có thể diễn đạt phép so sánh nghiệp vụ.

Ví dụ Quantity có thể implement Comparable:

~~~java
public record Quantity(int value)
        implements Comparable<Quantity> {

    public Quantity {
        if (value <= 0) {
            throw new InvalidQuantity(value);
        }
    }

    @Override
    public int compareTo(Quantity other) {
        return Integer.compare(value, other.value);
    }
}
~~~

Test:

~~~java
@Test
void comparesQuantitiesByNumericValue() {
    Quantity small = new Quantity(2);
    Quantity large = new Quantity(5);

    assertTrue(small.compareTo(large) < 0);
    assertTrue(large.compareTo(small) > 0);
    assertEquals(0, small.compareTo(new Quantity(2)));
}
~~~

Nếu Value Object implement Comparable, cần xem xét consistency giữa compareTo và equals. Trong ví dụ Quantity, compareTo trả 0 đúng khi equals là true.

### Không so sánh các giá trị không cùng đơn vị

Money là ví dụ quan trọng. Không thể so sánh trực tiếp 10 USD với 9 EUR nếu chưa có tỷ giá và thời điểm quy đổi. Không nên implement Comparable<Money> với phép so sánh amount đơn thuần.

Một API rõ nghĩa có thể yêu cầu cùng currency:

~~~java
public boolean isGreaterThan(Money other) {
    requireSameCurrency(other);
    return amount.compareTo(other.amount) > 0;
}
~~~

Test cần xác nhận:

- Cùng currency thì so sánh theo amount.
- Khác currency thì từ chối hoặc yêu cầu một phép quy đổi có ngữ cảnh.
- Không tự động coi amount có cùng số là tương đương.

## 10. BigDecimal và equality theo ngữ nghĩa tiền tệ

BigDecimal.equals() phân biệt scale:

~~~java
new BigDecimal("10.0").equals(new BigDecimal("10.00")) // false
new BigDecimal("10.0").compareTo(new BigDecimal("10.00")) == 0 // true
~~~

Vì vậy Money phải định nghĩa rõ domain có coi 10.0 và 10.00 là cùng một số tiền hay không.

Nếu domain xem chúng tương đương, có thể chuẩn hóa representation khi tạo:

~~~java
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        if (amount.signum() < 0) {
            throw new InvalidMoneyAmount(amount);
        }

        amount = amount.signum() == 0
                ? BigDecimal.ZERO
                : amount.stripTrailingZeros();
    }

    public boolean isGreaterThan(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IncompatibleCurrency(
                    currency,
                    other.currency
            );
        }

        return amount.compareTo(other.amount) > 0;
    }
}
~~~

Test:

~~~java
@Test
void moneyUsesNumericEqualityForSameCurrency() {
    Money first = new Money(
            new BigDecimal("10.0"),
            Currency.getInstance("USD")
    );
    Money second = new Money(
            new BigDecimal("10.00"),
            Currency.getInstance("USD")
    );

    assertEquals(first, second);
    assertEquals(first.hashCode(), second.hashCode());
}

@Test
void zeroHasOneCanonicalRepresentation() {
    Money first = new Money(
            new BigDecimal("0.00"),
            Currency.getInstance("USD")
    );
    Money second = new Money(
            BigDecimal.ZERO,
            Currency.getInstance("USD")
    );

    assertEquals(first, second);
}
~~~

Đây chỉ là một policy minh họa. Một domain có thể yêu cầu scale cố định theo currency, hoặc cần giữ precision cao cho phép tính trung gian. Khi đó hãy chuẩn hóa theo quy tắc làm tròn và độ chính xác đã thống nhất. Không tự ý làm tròn trong constructor nếu hành vi đó có thể làm mất dữ liệu nghiệp vụ.

## 11. Kiểm thử tính bất biến

Một Value Object bất biến không thay đổi state sau khi được tạo. Tính bất biến giúp object có thể được chia sẻ an toàn giữa nhiều phần của ứng dụng và giúp equality/hashCode ổn định.

Với Java record chứa primitive, String và các Value Object bất biến, tính bất biến thường đơn giản. Nhưng record chỉ tạo field final; nó không tự làm cho object lồng bên trong trở nên bất biến.

Ví dụ không an toàn:

~~~java
public record OrderLines(List<OrderLine> values) {
}
~~~

Caller có thể thay đổi list sau khi tạo:

~~~java
List<OrderLine> source = new ArrayList<>();
OrderLines lines = new OrderLines(source);

source.add(new OrderLine(...));
~~~

Nếu record giữ nguyên reference list, giá trị OrderLines đã thay đổi dù không gọi method nào trên nó.

### Defensive copy

Cách phổ biến là copy dữ liệu đầu vào:

~~~java
public record OrderLines(List<OrderLine> values) {
    public OrderLines {
        values = List.copyOf(values);
    }
}
~~~

Test:

~~~java
@Test
void sourceListMutationDoesNotChangeValueObject() {
    List<OrderLine> source = new ArrayList<>();
    source.add(new OrderLine(new ProductId("P-1"), new Quantity(2)));

    OrderLines lines = new OrderLines(source);

    source.add(new OrderLine(new ProductId("P-2"), new Quantity(1)));

    assertEquals(1, lines.values().size());
}
~~~

Test này xác nhận constructor không giữ alias tới mutable list của caller.

### Không cho phép thay đổi qua accessor

~~~java
@Test
void exposedCollectionCannotBeModified() {
    OrderLines lines = new OrderLines(
            List.of(new OrderLine(new ProductId("P-1"), new Quantity(2)))
    );

    assertThrows(
            UnsupportedOperationException.class,
            () -> lines.values().add(
                    new OrderLine(new ProductId("P-2"), new Quantity(1))
            )
    );
}
~~~

List.copyOf trả về collection không sửa đổi được. Tuy nhiên, nó chỉ bảo vệ cấu trúc collection; các phần tử bên trong cũng cần bất biến hoặc được copy phù hợp.

## 12. Shallow immutability và deep immutability

Một object có field final chưa chắc bất biến sâu.

Ví dụ:

~~~java
public final class DeliveryAddress {
    private final List<String> lines;

    public DeliveryAddress(List<String> lines) {
        this.lines = lines;
    }

    public List<String> lines() {
        return lines;
    }
}
~~~

Field lines là final nhưng list vẫn có thể bị thay đổi qua reference đầu vào hoặc accessor.

Để bảo vệ deep immutability:

- Copy collection khi nhận dữ liệu.
- Trả về collection immutable hoặc defensive copy.
- Dùng các phần tử bất biến.
- Không giữ reference tới mutable object bên ngoài.
- Với array hoặc Date mutable, clone hoặc chuyển sang kiểu bất biến.

Ví dụ với array:

~~~java
public final class Digest {
    private final byte[] bytes;

    public Digest(byte[] bytes) {
        this.bytes = bytes.clone();
    }

    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Test cả hai chiều:

~~~java
@Test
void digestDefensivelyCopiesInputAndOutput() {
    byte[] source = {1, 2, 3};
    Digest digest = new Digest(source);

    source[0] = 9;
    assertArrayEquals(new byte[]{1, 2, 3}, digest.bytes());

    byte[] returned = digest.bytes();
    returned[1] = 9;

    assertArrayEquals(new byte[]{1, 2, 3}, digest.bytes());
}
~~~

Với Date hoặc Calendar, thường nên chuyển sang LocalDate, Instant hoặc các kiểu java.time bất biến thay vì giữ object mutable.

## 13. Kiểm thử Value Object lồng nhau

Một Value Object có thể gồm nhiều Value Object nhỏ hơn.

Ví dụ Address:

~~~java
public record Address(
        AddressLine line1,
        WardCode wardCode,
        CityCode cityCode,
        PostalCode postalCode
) {
    public Address {
        Objects.requireNonNull(line1);
        Objects.requireNonNull(wardCode);
        Objects.requireNonNull(cityCode);
        Objects.requireNonNull(postalCode);
    }
}
~~~

Test Address không cần lặp lại mọi test của AddressLine hoặc PostalCode. Thay vào đó, nên kiểm tra:

- Không chấp nhận thành phần bắt buộc null.
- Equality bao gồm đúng các thành phần có ý nghĩa.
- Hai Address có cùng components thì bằng nhau.
- Thay đổi một component có ý nghĩa làm Address khác.
- Các thành phần con đã bất biến.

Test từng Value Object nhỏ ở bộ test riêng, rồi test cách chúng kết hợp trong Address. Cách này giúp tìm lỗi ở đúng lớp và tránh test quá nhiều behavior cùng lúc.

## 14. Kiểm thử null, empty và absent theo semantics

Không phải mọi trường hợp thiếu dữ liệu đều giống nhau.

- null: không có object hoặc giá trị.
- empty: có object nhưng không có nội dung, ví dụ chuỗi rỗng hoặc list rỗng.
- absent: field không xuất hiện trong request hoặc cấu trúc dữ liệu.
- unknown: hệ thống chưa biết giá trị.
- not applicable: khái niệm không áp dụng trong trường hợp này.

Với một Value Object bắt buộc như ProductCode, null, empty và whitespace có thể đều bị từ chối. Với một Note tùy chọn, empty có thể được chuẩn hóa thành absence hoặc giữ lại như một giá trị rỗng tùy semantics.

Không nên tự động coi null và empty là bằng nhau. Test cần thể hiện đúng quy tắc của domain.

Ví dụ:

~~~java
@ParameterizedTest
@EmptySource
@ValueSource(strings = {" ", "   "})
void rejectsBlankProductCode(String value) {
    assertThrows(
            InvalidProductCode.class,
            () -> new ProductCode(value)
    );
}

@Test
void rejectsNullProductCode() {
    assertThrows(
            NullPointerException.class,
            () -> new ProductCode(null)
    );
}
~~~

Trong ví dụ ProductCode ở trên, null bị từ chối bởi Objects.requireNonNull nên test mong đợi NullPointerException; empty và whitespace bị từ chối bởi validation format nên test mong đợi InvalidProductCode. Nếu domain muốn một loại lỗi thống nhất, factory có thể chuyển cả hai trường hợp về cùng domain error và test cần phản ánh contract đó.

## 15. Kiểm thử equality của collection và Map

Value Object thường được dùng làm key hoặc phần tử của collection.

Các test nên xác nhận:

- Hai giá trị bằng nhau không tạo hai phần tử trong HashSet.
- Map lookup bằng một instance tương đương tìm được value.
- Thứ tự sorting theo comparator đúng với semantics.
- Equality/hashCode ổn định trong suốt vòng đời object.

Ví dụ:

~~~java
@Test
void equivalentValueObjectCanFindMapEntry() {
    Map<ProductCode, String> names = new HashMap<>();
    names.put(new ProductCode("AB-120"), "Keyboard");

    String name = names.get(new ProductCode(" ab-120 "));

    assertEquals("Keyboard", name);
}
~~~

Nếu Value Object mutable và bị thay đổi sau khi đưa vào HashMap, hashCode có thể thay đổi và key trở nên khó tìm. Đây là một lý do thực tế khiến immutability rất quan trọng.

## 16. Property-based testing cho Value Object

Unit test với một số input cụ thể rất cần thiết, nhưng có thể bỏ sót nhiều tổ hợp giá trị. Property-based testing tạo nhiều input và kiểm tra một tính chất tổng quát.

Một số property hữu ích:

### Quantity

Với mọi integer dương:

- Constructor thành công.
- Giá trị lưu giữ bằng giá trị đầu vào.
- Hai Quantity cùng value bằng nhau.
- Quantity bằng nhau có hashCode bằng nhau.

Với mọi integer không dương:

- Constructor bị từ chối.

### ProductCode

Với mọi representation hợp lệ theo policy:

- Normalization tạo code canonical.
- Chuẩn hóa lần thứ hai không đổi kết quả.
- Hai representation canonical tương đương có equality và hashCode giống nhau.

### DateRange

Với mọi cặp ngày thỏa start không sau end theo policy:

- Range được tạo thành công.
- contains() đúng ở các điểm bên trong.
- contains() xử lý biên đúng theo inclusive/exclusive contract.
- Hai range bằng nhau nếu endpoints bằng nhau.

### Money

Với mọi amount không âm và currency hợp lệ:

- Money được tạo thành công.
- Normalization bảo toàn giá trị số theo policy.
- Cùng amount/currency thì equality đúng.
- Khác currency thì equality sai.

Có thể dùng jqwik hoặc QuickTheories cho Java. Hãy viết property từ quy tắc nghiệp vụ, không chỉ từ cách code đang hoạt động.

## 17. Kiểm thử tính bất biến bằng chuỗi thao tác

Một Value Object bất biến không nên thay đổi khi caller thực hiện thao tác trên dữ liệu nguồn hoặc giá trị trả về.

Một số tình huống cần kiểm tra:

- Sửa list nguồn sau constructor.
- Sửa map nguồn sau constructor.
- Sửa array đầu vào.
- Sửa array hoặc collection trả ra.
- Gọi nhiều lần accessor.
- Dùng Value Object làm key trong HashMap rồi tiếp tục thao tác với dữ liệu nguồn.
- Kết hợp Value Object với object con có mutable state.

Ví dụ test tổng hợp cho OrderLines:

~~~java
@Test
void orderLinesRemainStableAfterExternalMutations() {
    OrderLine line = new OrderLine(
            new ProductId("P-1"),
            new Quantity(2)
    );
    List<OrderLine> source = new ArrayList<>(List.of(line));

    OrderLines value = new OrderLines(source);
    int originalHash = value.hashCode();

    source.clear();

    assertEquals(1, value.values().size());
    assertEquals(originalHash, value.hashCode());
}
~~~

Test này xác nhận việc thay đổi list nguồn không làm thay đổi nội dung hoặc hash của Value Object.

## 18. Kiểm thử serialization và persistence mapping

Value Object có thể được serialize qua JSON, message hoặc lưu xuống database. Đây là contract ở boundary và persistence adapter, không phải lý do để làm domain model phụ thuộc framework.

Nếu hệ thống dùng Jackson, JPA converter hoặc serializer khác, có thể có test riêng để xác nhận:

- Deserialize tạo được Value Object hợp lệ.
- Giá trị không hợp lệ bị từ chối.
- Serialize/deserialize round-trip bảo toàn equality.
- Normalization được áp dụng nhất quán.
- Database mapping không làm mất precision hoặc currency.
- Null/empty được ánh xạ theo contract.

Ví dụ property mong muốn:

\[
decode(encode(value)) = value
\]

Round-trip test không thay thế unit test constructor. Nó kiểm tra adapter có giữ đúng semantics khi chuyển qua representation khác.

### Không đưa framework annotation vào mọi Value Object chỉ để dễ deserialize

Có thể dùng factory, converter hoặc adapter để tạo Value Object từ dữ liệu bên ngoài. Domain model nên giữ quy tắc và không phụ thuộc vào một serializer cụ thể nếu không cần.

## 19. Test Value Object không nên cần database hoặc network

Một Value Object thuần nên được tạo và kiểm thử độc lập. Nếu test constructor phải kết nối database, gọi HTTP hoặc khởi động Spring context, có thể Value Object đang ôm trách nhiệm không thuộc nó.

Ví dụ, kiểm tra ProductCode có format hợp lệ không là trách nhiệm nội tại. Kiểm tra ProductCode đã tồn tại trong catalog hay chưa là quy tắc cần repository hoặc catalog context.

Hãy tách:

- Value Object test: quy tắc nội tại và semantics.
- Domain service test: quy tắc cần phối hợp nhiều khái niệm.
- Application test: orchestration và dữ liệu bên ngoài.
- Integration test: persistence, serialization hoặc giao tiếp hệ thống.

Việc tách này giúp test nhanh, ổn định và chỉ ra lỗi ở đúng layer.

## 20. Những lỗi thường gặp khi kiểm thử Value Object

### Chỉ kiểm tra constructor không ném exception

Điều đó chưa xác nhận giá trị được lưu đúng, normalized đúng hoặc equality đúng.

### Chỉ kiểm tra equals mà quên hashCode

HashSet và HashMap có thể hoạt động sai dù assertEquals pass.

### Dùng assertSame thay cho assertEquals

Hai instance khác nhau nhưng cùng giá trị phải được xem là bằng nhau.

### Test implementation thay vì domain semantics

Ví dụ kiểm tra một field private bằng reflection khiến test phụ thuộc cấu trúc code. Ưu tiên public behavior và contract.

### Coi record là bất biến sâu

Record chỉ làm component reference final. List, Map, array hoặc object mutable vẫn có thể thay đổi.

### Không test input và output aliasing

Defensive copy cần kiểm tra cả việc sửa object nguồn và sửa object được trả ra.

### Chuẩn hóa quá mức

Lowercase, trim hoặc làm tròn có thể làm mất ý nghĩa. Normalization phải theo domain policy.

### So sánh Money chỉ bằng amount

Bỏ qua currency có thể coi hai giá trị khác đơn vị là bằng nhau.

### Dùng regex đơn giản làm chuẩn xác thực phức tạp

Regex có thể kiểm tra format cơ bản nhưng không chứng minh một mã hoặc địa chỉ hợp lệ về nghiệp vụ.

### Đưa quy tắc contextual vào Value Object

Gọi repository trong constructor khiến giá trị khó tạo, khó test và phụ thuộc hạ tầng.

### Test quá nhiều thứ trong một test

Một test vừa tạo Value Object, gọi database, cập nhật Aggregate và gửi event khó chỉ ra contract nào bị lỗi. Chia test theo trách nhiệm.

## 21. Quy trình thiết kế bộ test cho Value Object

Khi thêm một Value Object mới, có thể đi theo trình tự:

1. **Viết định nghĩa miền:** giá trị đại diện cho khái niệm gì và thuộc ngôn ngữ nào?
2. **Xác định equality:** thuộc tính nào quyết định hai giá trị bằng nhau?
3. **Xác định normalization:** representation nào được coi là tương đương?
4. **Liệt kê validation:** null, empty, range, format và semantic constraints.
5. **Xác định immutability:** có collection, array hoặc object mutable nào không?
6. **Chọn behavior so sánh:** equals, hashCode, compareTo hoặc phép so sánh có ngữ cảnh.
7. **Viết test hợp lệ:** giá trị biên hợp lệ được tạo và giữ đúng.
8. **Viết test không hợp lệ:** từng loại input bị từ chối với lỗi ổn định.
9. **Viết test equality/hashCode:** instance tương đương hoạt động đúng trong collection.
10. **Viết test immutability:** sửa dữ liệu nguồn hoặc output không đổi Value Object.
11. **Viết property-based test:** nếu có quy tắc tổng quát hoặc nhiều tổ hợp input.
12. **Test adapter riêng:** serialization và persistence mapping nếu Value Object đi qua boundary.
13. **Rà lại phạm vi:** quy tắc phụ thuộc Aggregate hoặc context khác phải được test ở layer tương ứng.

## 22. Checklist kiểm thử Value Object

Trước khi hoàn thiện Value Object, hãy kiểm tra:

- Ý nghĩa nghiệp vụ của Value Object đã rõ chưa?
- Các thuộc tính thực sự tham gia equality đã được xác định chưa?
- Constructor hoặc factory có bảo vệ validation không?
- Null, empty, whitespace và absent có semantics rõ chưa?
- Boundary values đã được kiểm thử chưa?
- Lỗi validation có type hoặc reason code phù hợp không?
- Normalization có đúng policy và idempotent không?
- Hai instance tương đương có equals đúng không?
- equals có tuân thủ reflexive, symmetric, transitive và consistent không?
- Hai object bằng nhau có hashCode giống nhau không?
- HashSet/HashMap có xử lý instance tương đương đúng không?
- compareTo/comparator có phản ánh đúng thứ tự nghiệp vụ không?
- Money có xét currency và precision/scale đúng không?
- Collection đầu vào đã được defensive copy chưa?
- Collection hoặc array trả ra có thể bị caller sửa không?
- Các object lồng bên trong có bất biến sâu không?
- Value Object có phụ thuộc database hoặc network không cần thiết không?
- Serialization/persistence adapter có giữ equality và giá trị không?
- Property-based test có ích cho các quy tắc tổng quát không?
- Test có tập trung vào behavior và contract thay vì private implementation không?

## 23. Kết luận

Kiểm thử Value Object cần xác nhận giá trị được tạo ra luôn hợp lệ, được so sánh theo đúng ngữ nghĩa miền và không thay đổi ngoài ý muốn. Validation bảo vệ cấu trúc và quy tắc nội tại; equality/hashCode bảo đảm giá trị hoạt động đúng trong các phép so sánh và collection; immutability giúp giá trị ổn định khi được chia sẻ giữa các thành phần.

Trong DDD, Value Object là một phần quan trọng của ngôn ngữ chung. Vì vậy, test nên xuất phát từ ý nghĩa nghiệp vụ: hai giá trị nào được xem là tương đương, giới hạn nào được chấp nhận, representation nào cần chuẩn hóa và dữ liệu nào phải bất biến. Với collection hoặc object lồng nhau, cần kiểm tra defensive copy và deep immutability. Với Money hoặc các giá trị có đơn vị, cần xác định rõ precision, currency và quy tắc so sánh.

Một bộ test Value Object tốt chạy nhanh, độc lập và tập trung vào contract. Nó giúp các Aggregate và use case dựa vào những giá trị đáng tin cậy, đồng thời cho phép đội ngũ thay đổi implementation mà không làm thay đổi semantics đã thống nhất của domain.
