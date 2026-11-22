# ParameterizedTest cho ma trận dữ liệu

Trong JUnit Jupiter, `@ParameterizedTest` cho phép chạy cùng một phương thức kiểm thử nhiều lần với các bộ dữ liệu đầu vào khác nhau. Thay vì viết nhiều phương thức `@Test` gần như giống nhau, ta mô tả dữ liệu kiểm thử thành các hàng (rows). Mỗi hàng tạo ra một lần thực thi độc lập của phương thức.

Đây là cách phù hợp để kiểm tra một quy tắc qua nhiều trường hợp: giá trị hợp lệ và không hợp lệ, biên dưới và biên trên, các trạng thái enum, tổ hợp phương thức giao hàng với số lượng sản phẩm, hoặc nhiều đầu vào tương ứng với kết quả mong đợi.

## 1. Cấu trúc của một Parameterized Test

Một parameterized test có ba phần:

1. **Phương thức kiểm thử** được đánh dấu `@ParameterizedTest` và khai báo các tham số cần nhận.
2. **Nguồn dữ liệu** cung cấp một hoặc nhiều bộ đối số bằng các annotation như `@ValueSource`, `@CsvSource`, `@MethodSource`.
3. **Phần kiểm tra** thực hiện assertion trên từng bộ đối số.

```java
@ParameterizedTest
@ValueSource(ints = {1, 2, 3, 5})
void acceptsPositiveQuantity(int quantity) {
    assertThat(quantity).isPositive();
}
```

JUnit tạo bốn lần thực thi cho phương thức trên. Mỗi lần nhận một giá trị `quantity` riêng. Nếu trường hợp `quantity = 3` thất bại, kết quả sẽ gắn với invocation tương ứng, giúp xác định dữ liệu gây lỗi.

Khác với `@Test`, `@ParameterizedTest` là một test template. JUnit cần có ít nhất một nguồn đối số để tạo các invocation. Mỗi invocation vẫn đi qua vòng đời kiểm thử của JUnit: các callback và `@BeforeEach`/`@AfterEach` được thực thi theo từng lần chạy, còn `@BeforeAll`/`@AfterAll` áp dụng theo vòng đời test container.

## 2. Dependency cần có

Các annotation và cơ chế parameterized test thuộc module `junit-jupiter-params`. Nếu dự án dùng JUnit Jupiter tổng hợp hoặc Spring Boot `spring-boot-starter-test`, dependency này thường đã được đưa vào. Với dự án tự khai báo JUnit, cần thêm nó vào test classpath.

Ví dụ Gradle:

```groovy
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
}

tasks.test {
    useJUnitPlatform()
}
```

Nếu dự án quản lý riêng từng module JUnit thì có thể khai báo `junit-jupiter-api`, `junit-jupiter-params` và engine tương ứng. Hãy dùng cùng một dòng phiên bản cho các module JUnit; trong dự án Spring Boot, nên để dependency management của Boot quản lý phiên bản.

## 3. Các nguồn dữ liệu có sẵn

JUnit Jupiter cung cấp nhiều annotation source. Chọn nguồn theo hình dạng dữ liệu giúp test dễ đọc và giảm code chuẩn bị dữ liệu.

### 3.1. `@ValueSource`: một tham số đơn giản

`@ValueSource` phù hợp khi mỗi invocation chỉ cần một giá trị thuộc kiểu được hỗ trợ, chẳng hạn `int`, `long`, `double`, `boolean`, `char`, `String` hoặc `Class`.

```java
@ParameterizedTest(name = "[{index}] accepts quantity {0}")
@ValueSource(ints = {1, 2, 10, 100})
void acceptsPositiveQuantity(int quantity) {
    assertThat(quantity).isGreaterThan(0);
}
```

Ở đây mỗi phần tử trong `ints` là một bộ đối số chỉ có một phần tử. `@ValueSource` không phải lựa chọn phù hợp khi một trường hợp cần đồng thời nhiều cột dữ liệu như đầu vào, kết quả mong đợi và thông điệp lỗi; khi đó nên dùng `@CsvSource` hoặc `@MethodSource`.

### 3.2. `@NullSource`, `@EmptySource` và `@NullAndEmptySource`

Ba annotation này hữu ích khi kiểm tra đầu vào vắng mặt hoặc rỗng:

- `@NullSource` truyền `null` cho tham số kiểu tham chiếu.
- `@EmptySource` truyền giá trị rỗng cho những kiểu được hỗ trợ như `String`, collection, map và array.
- `@NullAndEmptySource` kết hợp trường hợp `null` và rỗng.

Có thể kết hợp chúng với `@ValueSource` để kiểm tra cả chuỗi trắng:

```java
@ParameterizedTest
@NullAndEmptySource
@ValueSource(strings = {" ", "\t", "\n"})
void rejectsMissingOrBlankCustomerCode(String customerCode) {
    assertThat(customerCode == null || customerCode.isBlank()).isTrue();
}
```

Không truyền `null` vào tham số kiểu nguyên thủy như `int` hoặc `boolean`; các kiểu đó không biểu diễn được `null`. Nếu test cần xác nhận `null`, hãy dùng kiểu tham chiếu tương ứng.

### 3.3. `@EnumSource`: kiểm tra các giá trị enum

`@EnumSource` tạo invocation từ các hằng enum. Mặc định, tất cả hằng của enum được sử dụng. Có thể chọn tên cụ thể hoặc loại trừ một số giá trị.

```java
enum DeliveryMode {
    STANDARD,
    EXPRESS,
    PICKUP
}

@ParameterizedTest
@EnumSource(value = DeliveryMode.class, names = {"STANDARD", "EXPRESS"})
void deliveryModesRequireShippingAddress(DeliveryMode mode) {
    assertThat(mode).isIn(DeliveryMode.STANDARD, DeliveryMode.EXPRESS);
}
```

Một số chế độ thường dùng:

| Mode | Ý nghĩa |
|---|---|
| `INCLUDE` | Chỉ chạy các hằng được liệt kê trong `names`. |
| `EXCLUDE` | Chạy tất cả hằng, trừ những hằng được liệt kê. |
| `MATCH_ALL` | Chọn các tên khớp tất cả biểu thức regular expression được cung cấp. |
| `MATCH_ANY` | Chọn các tên khớp ít nhất một biểu thức regular expression. |

Ví dụ loại trừ `PICKUP`:

```java
@ParameterizedTest
@EnumSource(value = DeliveryMode.class,
        mode = EnumSource.Mode.EXCLUDE,
        names = "PICKUP")
void shippedModesHaveShippingCost(DeliveryMode mode) {
    assertThat(mode).isIn(DeliveryMode.STANDARD, DeliveryMode.EXPRESS);
}
```

### 3.4. `@CsvSource`: nhiều cột dữ liệu ngay trong test

`@CsvSource` phù hợp với ma trận nhỏ, dễ đọc. Mỗi dòng CSV là một invocation; các cột được ánh xạ lần lượt vào tham số của phương thức.

```java
@ParameterizedTest(name = "quantity={0}, expectedValid={1}")
@CsvSource({
        "1, true",
        "2, true",
        "100, true",
        "0, false",
        "-1, false"
})
void validatesQuantity(int quantity, boolean expectedValid) {
    assertThat(QuantityRules.isValid(quantity)).isEqualTo(expectedValid);
}
```

Trong ví dụ, hai cột lần lượt được chuyển thành `int` và `boolean`. Assertion dùng cột thứ hai làm kết quả mong đợi nên mỗi hàng vừa mô tả input vừa mô tả expected outcome.

Một số tùy chọn của `@CsvSource` có thể giúp dữ liệu rõ ràng hơn:

- `delimiter` thay đổi ký tự phân tách cột; `delimiterString` dùng một chuỗi phân tách.
- `nullValues` khai báo token nào trong dữ liệu tương ứng với `null`.
- `emptyValue` quy định cách biểu diễn giá trị chuỗi rỗng được trích dẫn.
- `ignoreLeadingAndTrailingWhitespace` kiểm soát việc bỏ khoảng trắng quanh giá trị.
- `useHeadersInDisplayName` có thể dùng tên cột trong tên hiển thị ở các phiên bản JUnit hỗ trợ tùy chọn này.

Ví dụ dùng token để biểu diễn `null`:

```java
@ParameterizedTest
@CsvSource(value = {
        "customer-1, ACTIVE",
        "NIL, UNKNOWN"
}, nullValues = "NIL")
void handlesOptionalCustomerCode(String customerCode, String expectedStatus) {
    // Kiểm tra quy tắc dựa trên customerCode và expectedStatus.
}
```

Nếu một trường có dấu phẩy hoặc ký tự phân cách, hãy dùng cú pháp quote của CSV để giữ trường đó thành một giá trị. Với dữ liệu phức tạp, nhiều cột hoặc cần tái sử dụng, `@MethodSource` thường dễ bảo trì hơn một chuỗi CSV dài.

### 3.5. `@CsvFileSource`: dữ liệu từ file CSV

Khi ma trận có nhiều hàng, có thể tách dữ liệu khỏi mã test. `@CsvFileSource` đọc file trên classpath hoặc từ đường dẫn file theo cấu hình của annotation.

Ví dụ file `src/test/resources/quantity-cases.csv`:

```csv
quantity,expectedValid
1,true
2,true
100,true
0,false
-1,false
```

Test tương ứng:

```java
@ParameterizedTest(name = "quantity={0}, valid={1}")
@CsvFileSource(resources = "/quantity-cases.csv", numLinesToSkip = 1)
void validatesQuantityFromCsv(int quantity, boolean expectedValid) {
    assertThat(QuantityRules.isValid(quantity)).isEqualTo(expectedValid);
}
```

`numLinesToSkip = 1` bỏ dòng header. File dữ liệu cần được quản lý cùng test, có tên cột dễ hiểu và không chứa các giá trị khó diễn giải. Khi test phụ thuộc vào file, hãy đặt file đúng trong `src/test/resources` để build có thể đưa nó vào test classpath.

### 3.6. `@MethodSource`: nguồn dữ liệu bằng Java

`@MethodSource` phù hợp khi dữ liệu cần tạo bằng code, cần nhiều kiểu tham số, cần tính toán giá trị mong đợi hoặc cần đặt tên cho từng trường hợp. Factory method thường trả về `Stream<Arguments>`.

```java
class QuantityRulesTest {

    @ParameterizedTest(name = "[{index}] {0}")
    @MethodSource("quantityCases")
    void validatesQuantity(String caseName, int quantity, boolean expectedValid) {
        assertThat(QuantityRules.isValid(quantity)).isEqualTo(expectedValid);
    }

    static Stream<Arguments> quantityCases() {
        return Stream.of(
                Arguments.of("minimum accepted", 1, true),
                Arguments.of("ordinary quantity", 5, true),
                Arguments.of("zero", 0, false),
                Arguments.of("negative", -1, false)
        );
    }
}
```

Tên method được truyền vào `@MethodSource` phải khớp với factory. Với test instance lifecycle mặc định, factory method trong cùng class cần là `static`. Nếu dùng `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, có thể dùng factory instance method. Có thể đặt factory trong class khác bằng cú pháp tham chiếu class và tên method theo quy ước của JUnit.

Factory có thể trả về các kiểu nguồn như `Stream`, `Collection`, `Iterable`, `Iterator` hoặc mảng, tùy hợp đồng của JUnit. Với mỗi trường hợp nhiều tham số, dùng `Arguments.of(...)` để tạo một bộ đối số có thứ tự tương ứng với chữ ký phương thức kiểm thử.

### 3.7. `@ArgumentsSource`: provider tùy chỉnh

Khi cách tạo dữ liệu có logic dùng lại ở nhiều test, có thể viết `ArgumentsProvider` và tham chiếu nó bằng `@ArgumentsSource`.

```java
class QuantityArgumentsProvider implements ArgumentsProvider {

    @Override
    public Stream<? extends Arguments> provideArguments(ExtensionContext context) {
        return Stream.of(
                Arguments.of(1, true),
                Arguments.of(5, true),
                Arguments.of(0, false),
                Arguments.of(-1, false)
        );
    }
}

class QuantityProviderTest {

    @ParameterizedTest
    @ArgumentsSource(QuantityArgumentsProvider.class)
    void validatesQuantity(int quantity, boolean expectedValid) {
        assertThat(QuantityRules.isValid(quantity)).isEqualTo(expectedValid);
    }
}
```

Provider tùy chỉnh hữu ích khi có quy tắc sinh dữ liệu chung, nhưng làm test khó đọc hơn nếu được tạo chỉ để thay thế một `@CsvSource` ngắn. Hãy giữ provider có tên phản ánh mục đích và tránh giấu các giá trị quan trọng khỏi người đọc test.

## 4. Tạo ma trận dữ liệu và tổ hợp đầu vào

Một hàng trong nguồn dữ liệu thường biểu diễn **một trường hợp kiểm thử hoàn chỉnh**. Ví dụ:

| Case | Delivery mode | Quantity | Expected |
|---|---|---:|---|
| A | STANDARD | 1 | Hợp lệ |
| B | STANDARD | 3 | Hợp lệ |
| C | EXPRESS | 1 | Hợp lệ |
| D | EXPRESS | 3 | Hợp lệ |

Nếu muốn kiểm tra tất cả tổ hợp giữa hai phương thức giao hàng và hai số lượng, có thể tạo tích Descartes (Cartesian product) bằng `@MethodSource`:

```java
static Stream<Arguments> deliveryAndQuantityCases() {
    return Stream.of(DeliveryMode.STANDARD, DeliveryMode.EXPRESS)
            .flatMap(mode -> Stream.of(1, 3)
                    .map(quantity -> Arguments.of(mode, quantity)));
}

@ParameterizedTest(name = "{0} with quantity {1}")
@MethodSource("deliveryAndQuantityCases")
void acceptsSupportedDeliveryAndQuantity(DeliveryMode mode, int quantity) {
    assertThat(ShippingRules.isSupported(mode, quantity)).isTrue();
}
```

Với 2 phương thức giao hàng và 2 số lượng, nguồn trên tạo 4 invocation. Nếu có nhiều chiều dữ liệu, số tổ hợp tăng theo tích số lượng giá trị của từng chiều. Chẳng hạn 4 kích cỡ, 5 màu và 3 phương thức vận chuyển tạo ra 60 tổ hợp. Không phải lúc nào cũng cần chạy toàn bộ tích Descartes; hãy xác định các tương tác có rủi ro, các biên quan trọng và các tổ hợp cần chứng minh. Có thể chọn các hàng đại diện hoặc thiết kế bộ dữ liệu theo pairwise khi số chiều quá lớn.

Đừng nhầm một danh sách các giá trị với ma trận nhiều chiều. `@ValueSource` tạo các invocation một tham số. Nếu phương thức nhận hai tham số, nguồn phải cung cấp đủ hai đối số cho từng invocation, chẳng hạn `@CsvSource`, `@MethodSource` hoặc một provider tùy chỉnh.

## 5. Chuyển đổi và gom nhóm tham số

### 5.1. Chuyển đổi kiểu tự động

JUnit Jupiter có thể chuyển một số kiểu nguồn phổ biến sang kiểu tham số tương ứng. Ví dụ, các giá trị trong `@CsvSource` được đọc dưới dạng chuỗi và chuyển sang `int`, `long`, `boolean`, enum hoặc một số kiểu chuẩn được hỗ trợ khi chữ ký test yêu cầu. Điều này giúp dữ liệu CSV ngắn gọn mà không cần tự parse trong thân test.

Khi kiểu đích là kiểu phức tạp của ứng dụng, hãy dùng `@ConvertWith` và một `ArgumentConverter`, hoặc tạo sẵn đối tượng bằng `@MethodSource`. Ví dụ converter cho `BigDecimal`:

```java
class MoneyConverter extends SimpleArgumentConverter {

    @Override
    protected Object convert(Object source, Class<?> targetType)
            throws ArgumentConversionException {
        if (targetType != BigDecimal.class || !(source instanceof String value)) {
            throw new ArgumentConversionException("Expected a decimal string");
        }

        try {
            return new BigDecimal(value);
        } catch (NumberFormatException exception) {
            throw new ArgumentConversionException("Invalid decimal: " + value, exception);
        }
    }
}

@ParameterizedTest
@CsvSource({"10.50", "0.99", "125.00"})
void acceptsMoneyAmount(@ConvertWith(MoneyConverter.class) BigDecimal amount) {
    assertThat(amount).isPositive();
}
```

Nếu nguồn dữ liệu đã là đối tượng `BigDecimal`, `LocalDate`, hoặc một value object được tạo rõ ràng, `@MethodSource` thường dễ đọc hơn converter vì không phải duy trì thêm quy tắc chuyển đổi.

### 5.2. `ArgumentsAccessor`: truy cập các cột theo vị trí

Khi dùng CSV có nhiều cột, đôi khi không muốn khai báo một tham số Java cho từng cột. `ArgumentsAccessor` cho phép đọc các đối số theo index:

```java
@ParameterizedTest
@CsvSource({
        "SKU-1, 2, true",
        "SKU-2, 0, false"
})
void validatesOrderRow(ArgumentsAccessor row) {
    String sku = row.getString(0);
    int quantity = row.getInteger(1);
    boolean expectedValid = row.getBoolean(2);

    assertThat(OrderRules.isValid(sku, quantity)).isEqualTo(expectedValid);
}
```

`ArgumentsAccessor` tiện khi cần đọc dữ liệu linh hoạt, nhưng các index như `0`, `1`, `2` ít diễn đạt ý nghĩa hơn tên tham số. Với cấu trúc ổn định, nên khai báo tham số rõ ràng hoặc dùng `@AggregateWith` để gom một hàng dữ liệu thành object có tên trường.

### 5.3. Gom một hàng dữ liệu thành object

`@AggregateWith` cho phép dùng một `ArgumentsAggregator` để chuyển nhiều cột thành một đối tượng miền. Cách này hữu ích khi test làm việc với một cấu trúc dữ liệu có ý nghĩa, chẳng hạn `OrderInput`.

```java
record OrderInput(String sku, int quantity) {}

class OrderInputAggregator implements ArgumentsAggregator {

    @Override
    public Object aggregateArguments(ArgumentsAccessor row, ParameterContext context)
            throws ArgumentsAggregationException {
        return new OrderInput(row.getString(0), row.getInteger(1));
    }
}

@ParameterizedTest
@CsvSource({"SKU-1, 2", "SKU-2, 5"})
void acceptsOrderInput(@AggregateWith(OrderInputAggregator.class) OrderInput input) {
    assertThat(input.quantity()).isPositive();
}
```

Aggregator giúp test tập trung vào object có ý nghĩa thay vì thao tác với các cột rời. Tuy nhiên, với chỉ hai tham số đơn giản, khai báo trực tiếp `String sku, int quantity` thường dễ hiểu hơn.

## 6. Đặt tên cho từng invocation

Khi một phương thức chạy nhiều lần, tên hiển thị rõ ràng giúp xác định trường hợp nào thất bại trong IDE và báo cáo test. `@ParameterizedTest` hỗ trợ template trong thuộc tính `name`:

| Placeholder | Nội dung |
|---|---|
| `{index}` | Số thứ tự invocation. |
| `{arguments}` | Danh sách các đối số. |
| `{argumentsWithNames}` | Đối số kèm tên khi nguồn dữ liệu cung cấp thông tin tên phù hợp và phiên bản hỗ trợ. |
| `{0}`, `{1}`, ... | Đối số theo vị trí bắt đầu từ 0. |

Ví dụ:

```java
@ParameterizedTest(name = "[{index}] {0}: quantity={1}, valid={2}")
@MethodSource("quantityCases")
void validatesQuantity(String caseName, int quantity, boolean expectedValid) {
    assertThat(QuantityRules.isValid(quantity)).isEqualTo(expectedValid);
}
```

Với `MethodSource`, có thể dùng `Named` để gắn nhãn cho một đối số:

```java
static Stream<Arguments> deliveryCases() {
    return Stream.of(
            Arguments.of(Named.of("economy", DeliveryMode.STANDARD)),
            Arguments.of(Named.of("fast", DeliveryMode.EXPRESS))
    );
}
```

Tên test nên mô tả dữ liệu hoặc kỳ vọng có ý nghĩa. Một tên như `case 4` ít hữu ích hơn `zero quantity is rejected`, nhất là khi thứ tự dữ liệu thay đổi.

## 7. Kết hợp với Spring Test

Parameterized test thuộc JUnit Jupiter. Khi test cần Spring `ApplicationContext`, có thể kết hợp `@ParameterizedTest` với `@SpringJUnitConfig` hoặc cấu hình Spring Test phù hợp. Spring Extension vẫn quản lý context và tiêm dependency; nguồn tham số của JUnit cung cấp dữ liệu cho từng invocation.

Ví dụ một service Spring được kiểm tra với nhiều đầu vào:

```java
@SpringJUnitConfig(classes = PricePolicyTestConfiguration.class)
class PricePolicyParameterizedTest {

    @Autowired
    private PricePolicy pricePolicy;

    @ParameterizedTest(name = "quantity={0} -> discount={1}")
    @CsvSource({
            "1, 0",
            "4, 0",
            "5, 5",
            "10, 10"
    })
    void calculatesDiscount(int quantity, int expectedDiscount) {
        assertThat(pricePolicy.discountPercent(quantity)).isEqualTo(expectedDiscount);
    }
}
```

Ở đây `@SpringJUnitConfig` tích hợp JUnit Jupiter với Spring TestContext và tạo context từ `PricePolicyTestConfiguration`. Spring tiêm `PricePolicy` vào test instance. `@CsvSource` tạo các invocation và truyền `quantity`, `expectedDiscount` cho từng lần chạy. Test không cần khởi tạo context thủ công trong mỗi hàng dữ liệu; Spring Test quản lý vòng đời và cache context theo cấu hình.

Nếu test chỉ kiểm tra hàm thuần Java hoặc một quy tắc không phụ thuộc Spring, không cần nạp `ApplicationContext`. Dùng JUnit parameterized test độc lập sẽ đơn giản và nhanh hơn. Chỉ thêm Spring context khi hành vi cần xác nhận phụ thuộc bean, cấu hình hoặc hạ tầng Spring.

## 8. Tổ chức ma trận kiểm thử có ý nghĩa

Một ma trận tốt không chỉ có nhiều hàng. Mỗi hàng cần chứng minh một hành vi hoặc một ranh giới cụ thể. Khi thiết kế dữ liệu, nên xác định:

- **Giá trị bình thường:** các đầu vào thường gặp trong luồng sử dụng.
- **Giá trị biên:** ngay dưới, đúng tại và ngay trên ngưỡng được chấp nhận.
- **Đầu vào bất thường:** `null`, chuỗi rỗng, chuỗi trắng, số âm, enum không được hỗ trợ hoặc định dạng sai.
- **Kết quả mong đợi:** boolean, exception, trạng thái, giá trị tính toán hoặc một phần của object trả về.
- **Tên trường hợp:** nhãn ngắn gọn để người đọc hiểu vì sao hàng đó tồn tại.

Ví dụ ma trận cho quy tắc số lượng từ 1 đến 100:

| Nhóm | Input | Expected |
|---|---:|---|
| Biên dưới hợp lệ | 1 | Hợp lệ |
| Bên trong khoảng | 50 | Hợp lệ |
| Biên trên hợp lệ | 100 | Hợp lệ |
| Dưới biên | 0 | Không hợp lệ |
| Trên biên | 101 | Không hợp lệ |
| Số âm | -1 | Không hợp lệ |

Không nên thêm các hàng trùng lặp mà không tạo thêm giá trị kiểm chứng. Nếu nhiều hàng kiểm tra cùng một kết quả và cùng một nhánh logic, hãy cân nhắc giữ các đại diện thực sự cần thiết. Với quy tắc có nhiều điều kiện, mỗi hàng nên làm rõ điều kiện nào đang được kích hoạt và các điều kiện còn lại được giữ cố định ra sao.

## 9. Khi nào nên dùng nguồn nào?

| Tình huống | Nguồn phù hợp |
|---|---|
| Một tham số, danh sách giá trị ngắn | `@ValueSource` |
| Kiểm tra `null`, chuỗi rỗng hoặc collection rỗng | `@NullSource`, `@EmptySource`, `@NullAndEmptySource` |
| Duyệt một số hoặc toàn bộ enum | `@EnumSource` |
| Nhiều cột đơn giản, ma trận nhỏ | `@CsvSource` |
| Ma trận nhiều hàng được quản lý như dữ liệu | `@CsvFileSource` |
| Dữ liệu cần tính toán, object phức tạp hoặc tổ hợp nhiều chiều | `@MethodSource` |
| Quy tắc cung cấp dữ liệu cần tái sử dụng rộng | `@ArgumentsSource` |
| Nhiều cột cần gom thành object | `@AggregateWith` hoặc `@MethodSource` trả về object phù hợp |

Ưu tiên nguồn dữ liệu thể hiện rõ cấu trúc của test. `@CsvSource` dễ nhìn với vài hàng ngắn; `@MethodSource` dễ bảo trì hơn khi dữ liệu có logic hoặc object; `@ArgumentsSource` nên dành cho provider thực sự có thể tái sử dụng.

## 10. Những lỗi thường gặp

### Thiếu dependency `junit-jupiter-params`

Nếu IDE không nhận ra `@ParameterizedTest`, `@ValueSource` hoặc `@MethodSource`, hãy kiểm tra test classpath. Dự án dùng JUnit Jupiter tổng hợp hoặc `spring-boot-starter-test` thường đã có module này; dự án khai báo thủ công cần thêm đúng dependency.

### Số đối số không khớp chữ ký test

Mỗi invocation phải cung cấp đủ đối số cho các tham số do nguồn dữ liệu quản lý, theo đúng thứ tự và kiểu có thể chuyển đổi. Ví dụ `@CsvSource` có ba cột thì phương thức cần nhận ba tham số tương ứng, trừ khi dùng `ArgumentsAccessor` hoặc aggregator.

### Factory method của `@MethodSource` không được tìm thấy

Kiểm tra tên trong `@MethodSource`, phạm vi truy cập và quy tắc `static` của factory method. Với lifecycle mặc định, method source trong cùng class phải là `static`. Nếu dùng factory instance, cần cấu hình `@TestInstance(PER_CLASS)` theo đúng mục đích.

### Dùng `@ValueSource` cho nhiều tham số

`@ValueSource` chỉ cung cấp một đối số mỗi invocation. Với input và expected value, dùng `@CsvSource` hoặc `@MethodSource` để mô tả cả hàng.

### Truyền `null` vào kiểu nguyên thủy

`@NullSource` không thể gán `null` cho `int`, `long` hoặc `boolean`. Hãy dùng kiểu tham chiếu nếu test cần kiểm tra `null` hoặc tách trường hợp null khỏi trường hợp giá trị số.

### Ma trận quá lớn và chậm

Tích Descartes có thể làm số invocation tăng rất nhanh. Chỉ tạo mọi tổ hợp khi mục tiêu kiểm thử yêu cầu điều đó. Với nhiều chiều dữ liệu, xác định tương tác quan trọng, kiểm thử biên và dùng kỹ thuật chọn tổ hợp phù hợp để giữ thời gian chạy trong giới hạn hợp lý.

### Tên invocation không giúp tìm lỗi

Tên mặc định hoặc chỉ có index khiến báo cáo khó đọc. Hãy đặt `name` theo dữ liệu quan trọng, dùng đối số mô tả hoặc `Named` khi cần.

### Đặt quá nhiều logic trong nguồn dữ liệu

Factory method nên mô tả các trường hợp và cách tạo dữ liệu. Nếu factory chứa nhiều nhánh nghiệp vụ, test có thể đang lặp lại logic cần kiểm tra hoặc che khuất ý nghĩa của ma trận. Giữ expected value rõ ràng và không tính expected bằng chính hàm đang được test.

## 11. Checklist khi viết một ParameterizedTest

Trước khi hoàn thành test, có thể tự kiểm tra các điểm sau:

- Phương thức dùng `@ParameterizedTest` và có nguồn dữ liệu phù hợp.
- Mỗi hàng dữ liệu là một trường hợp có ý nghĩa, với input và expected value rõ ràng.
- Số lượng, thứ tự và kiểu tham số khớp với dữ liệu nguồn.
- Đã bao phủ các giá trị bình thường, biên và đầu vào bất thường có liên quan.
- Tên invocation đủ rõ để xác định hàng dữ liệu thất bại.
- Nguồn dữ liệu dễ đọc và có vị trí lưu trữ phù hợp với quy mô của ma trận.
- Nếu dùng Spring, chỉ nạp `ApplicationContext` khi hành vi cần kiểm tra thực sự phụ thuộc vào Spring.

`@ParameterizedTest` giúp biến một quy tắc kiểm thử thành nhiều lần thực thi có dữ liệu minh bạch. Khi mỗi hàng thể hiện rõ một tình huống và kết quả mong đợi, ma trận dữ liệu trở thành tài liệu sống của hành vi hệ thống, đồng thời giúp mở rộng phạm vi kiểm thử mà không nhân bản các phương thức `@Test` gần giống nhau.
