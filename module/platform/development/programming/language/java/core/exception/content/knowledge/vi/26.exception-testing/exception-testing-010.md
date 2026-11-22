# Phân biệt lỗi của mã đang kiểm thử với lỗi trong phần chuẩn bị dữ liệu (Java)

## 1. Vấn đề: một test “xanh” chưa chắc kiểm tra đúng đoạn mã

Một bài kiểm thử thường có ba pha: **Arrange** (chuẩn bị dữ liệu và điều kiện), **Act** (gọi mã cần kiểm thử, hay *System Under Test* — SUT), và **Assert** (xác nhận kết quả). Khi kiểm tra exception, ranh giới giữa Arrange và Act đặc biệt quan trọng.

Xem đoạn JUnit 5 sau:

```java
assertThrows(IllegalArgumentException.class, () -> {
    OrderLine line = makeOrderLine("", -2);
    orderService.calculate(line);
});
```

Đây là **mảnh test cần các hàm/class và JUnit 5 đã được định nghĩa**, không phải chương trình Java SE độc lập. Người viết muốn xác nhận `orderService.calculate(...)` từ chối số lượng âm. Nhưng `makeOrderLine("", -2)` có thể ném `IllegalArgumentException` trước khi dòng `calculate` chạy, chẳng hạn do SKU rỗng. Khi ấy `assertThrows` vẫn báo **PASS**, mặc dù SUT **chưa được gọi lần nào**.

Đây là một **false positive**: test đạt điều kiện hình thức “có exception thuộc loại X”, nhưng không chứng minh đặc tính đang cần kiểm thử.

Giải pháp thường là:

1. Chuẩn bị fixture **ngoài lambda của `assertThrows`**.
2. Đảm bảo fixture hợp lệ theo **những điều kiện ngoài điều kiện cần thử**.
3. Giới hạn lambda chỉ chứa **hành động có trách nhiệm phát sinh exception mong đợi**.
4. Kiểm tra thêm mã lỗi, thuộc tính exception, cause hoặc tương tác của SUT khi có giá trị.
5. Nếu bước Arrange thất bại, test phải báo **lỗi setup**, không được nhận nhầm là thành công của Act.

**Nguyên tắc cốt lõi:** nguồn gốc exception và thời điểm xuất hiện exception quan trọng không kém loại exception.

## 2. Ba pha Arrange — Act — Assert

| Pha | Nhiệm vụ | Lỗi thường xuất hiện | Ý nghĩa với kết quả test |
| --- | --- | --- | --- |
| Arrange | Tạo object, fixture, stub, mock, dữ liệu DB, cấu hình test | Factory thiếu dữ liệu, JSON parse lỗi, container không khởi động, mock chưa cấu hình | **Test chưa vào được hành vi cần kiểm thử** |
| Act | Gọi chính SUT theo một tình huống xác định | Exception nghiệp vụ, validation error, lỗi phụ thuộc mà SUT cần xử lý | Đây là **lỗi thuộc hành vi test đang đánh giá** |
| Assert | Kiểm tra kết quả, exception, state, interaction | Assertion sai, test helper lỗi, truy xuất result sai | Test thất bại ở **bước xác minh**, không đồng nghĩa SUT ném đúng exception |
| Cleanup/teardown | Đóng file, connection, transaction, resource thử nghiệm | Lỗi close, rollback, cleanup | Có thể làm test thất bại dù Act/Assert đã chạy |

Một exception phát sinh trong Arrange không tự động là “bug của SUT”. Nó có thể là lỗi chính fixture builder, seed dữ liệu, test infrastructure hoặc môi trường. Đổi lại, **test data setup cũng là code** và phải được kiểm thử khi nó có logic phức tạp. Tách nguồn lỗi giúp biết cần sửa fixture hay sửa SUT.

Khi đọc test failure, hãy xác định **pha nào** xảy ra lỗi trước khi quyết định thay đổi production code.

## 3. Tại sao kiểu exception thôi là chưa đủ?

`assertThrows(IllegalArgumentException.class, executable)` kiểm tra có exception thuộc loại `IllegalArgumentException` hoặc subtype của nó được ném khi thực thi `executable`. Nó **không biết ý định của bạn**: exception đó có thể đến từ:

- Builder `new OrderLine(...)`;
- Validator trong mock/stub;
- Mapper JSON;
- Phương thức SUT;
- Callback do SUT kích hoạt;
- Assertion helper trong cùng lambda;
- Một phương thức chuẩn bị dữ liệu được gọi “tiện tay” bên trong Act.

Ví dụ sai:

```java
assertThrows(IllegalStateException.class, () -> {
    Repository repository = createRepository();
    MyService service = new MyService(repository);
    service.run();
});
```

Đây là mảnh JUnit, với các API ứng dụng đã định nghĩa. `createRepository()` hoặc constructor `MyService` có thể ném `IllegalStateException` trước `run()`. Test đạt nhưng chưa chứng minh `run()` tuân thủ contract.

**Sửa:**

```java
Repository repository = createRepository();
MyService service = new MyService(repository);

IllegalStateException error =
        assertThrows(IllegalStateException.class, service::run);
```

Nếu Arrange lỗi, test vẫn **FAIL**, nhưng failure chỉ thẳng tới bước chuẩn bị. Nếu Arrange thành công, chỉ phương thức `run` nằm trong phạm vi kỳ vọng exception.

Không cần bao bọc setup bằng `try/catch` để “sửa” một failure. Để lỗi setup được framework báo tự nhiên thường đã đủ, miễn test được cấu trúc rõ.

## 4. Ví dụ Java 17+ độc lập: false positive và cách sửa

Chương trình sau không cần JUnit để có thể chạy ngay bằng JDK 17+. Nó tự định nghĩa một helper `expectThrows` đơn giản chỉ nhằm minh họa hành vi giống một phép kỳ vọng exception, **không phải bản thay thế đầy đủ cho JUnit**.

Các trường hợp:

- **BROAD_SCOPE:** một lambda bao cả Arrange và Act. Arrange ném `IllegalArgumentException`, test tưởng “bắt đúng lỗi”.
- **SETUP_FAILED:** tách Arrange ra và nhìn thấy rõ lỗi fixture.
- **ACT_FAILED:** tạo fixture với SKU hợp lệ nhưng số lượng âm để chủ động kiểm thử lỗi của SUT; chỉ gọi SUT bên trong `expectThrows`.
- **SUCCESS_TOTAL:** có một kiểm thử đường thành công.
- Các kiểm tra tự động dừng chương trình bằng `AssertionError` nếu kết quả không đúng.

Tạo file **`TestBoundaryDemo.java`**:

```java
public class TestBoundaryDemo {
    record OrderLine(String sku, int quantity) {}

    static OrderLine arrange(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("fixture: sku is blank");
        }
        return new OrderLine(sku, quantity);
    }

    static int calculate(OrderLine line) {
        if (line.quantity() < 0) {
            throw new IllegalArgumentException("sut: quantity is negative");
        }
        return line.quantity() * 10;
    }

    static <T extends Throwable> T expectThrows(
            Class<T> type, Runnable action) {
        try {
            action.run();
        } catch (Throwable error) {
            if (type.isInstance(error)) {
                return type.cast(error);
            }
            throw new AssertionError("Wrong exception: " + error, error);
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        IllegalArgumentException misleading =
                expectThrows(IllegalArgumentException.class, () -> {
                    OrderLine line = arrange("", -2);
                    calculate(line);
                });
        System.out.println("BROAD_SCOPE: " + misleading.getMessage());

        try {
            arrange("", -2);
            throw new AssertionError("Setup should fail");
        } catch (IllegalArgumentException error) {
            System.out.println("SETUP_FAILED: " + error.getMessage());
        }

        OrderLine validFixture = arrange("SKU-1", -2);
        IllegalArgumentException expected =
                expectThrows(IllegalArgumentException.class,
                        () -> calculate(validFixture));
        if (!"sut: quantity is negative".equals(expected.getMessage())) {
            throw new AssertionError("Wrong failure origin");
        }
        System.out.println("ACT_FAILED: " + expected.getMessage());

        OrderLine normalFixture = arrange("SKU-1", 3);
        int total = calculate(normalFixture);
        if (total != 30) {
            throw new AssertionError("Unexpected total");
        }
        System.out.println("SUCCESS_TOTAL: " + total);
        System.out.println("CHECKS: PASS");
    }
}
```

Lệnh chạy trong thư mục có file:

```bash
javac -encoding UTF-8 TestBoundaryDemo.java
java TestBoundaryDemo
```

**Standard output đã kiểm chứng:**

```text
BROAD_SCOPE: fixture: sku is blank
SETUP_FAILED: fixture: sku is blank
ACT_FAILED: sut: quantity is negative
SUCCESS_TOTAL: 30
CHECKS: PASS
```

### Diễn giải kết quả

1. `BROAD_SCOPE` hiển thị **fixture: sku is blank**, không phải lỗi quantity từ `calculate`. Lambda bao quá rộng đã che nguồn lỗi.
2. `SETUP_FAILED` minh họa việc tách Arrange giúp nhìn thấy lỗi chuẩn bị là một lỗi khác, không phải hành vi đang kiểm thử.
3. `validFixture` có SKU hợp lệ nhưng quantity âm. **Quantity âm là input chủ động cho SUT validation**, không phải lỗi builder; vì vậy Arrange không ném.
4. `ACT_FAILED` chỉ xuất hiện do `calculate` ném. Kiểm tra message ở đây có mục đích phân biệt rõ fixture/SUT trong demo.
5. `SUCCESS_TOTAL` xác nhận đường xử lý bình thường trả `30`.
6. `expectThrows` bắt `Throwable` trong một **test harness minh họa** để phát hiện loại Throwable ném ra và chuyển sai khác thành `AssertionError`. Điều này không phải lời khuyên thêm `catch(Throwable)` đại trà vào production code.

Trong ứng dụng thật, nên dùng assertion của framework kiểm thử; `assertThrows` của JUnit đã có cơ chế báo lỗi đầy đủ và hỗ trợ message tùy biến.

## 5. Mẫu JUnit 5 nên dùng

Với bài test “quantity âm phải bị từ chối”, tách rõ:

```java
@Test
void rejectsNegativeQuantity() {
    // Arrange: hợp lệ về SKU; quantity âm là input cần kiểm thử.
    OrderLine line = new OrderLine("SKU-1", -2);

    // Act + assert exception: chỉ chứa lời gọi SUT.
    IllegalArgumentException error = assertThrows(
            IllegalArgumentException.class,
            () -> service.calculate(line));

    // Assert bổ sung: chứng minh đúng lý do.
    assertEquals("QUANTITY_NEGATIVE", error.getMessage());
}
```

Đây là **mảnh JUnit 5**, không biên dịch độc lập khi chưa có class `OrderLine`, `service`, import `@Test` và các static assertion. Chuỗi `QUANTITY_NEGATIVE` là giả định một **error code ổn định do ứng dụng quy định**; không được ghép với message của `TestBoundaryDemo` ở trên vì đây là hai ví dụ độc lập với hợp đồng khác nhau.

Nếu test builder có kiểm tra SKU, nên tạo fixture ngay trước `assertThrows`:

```java
OrderLine line = fixtureBuilder()
        .sku("SKU-1")
        .quantity(-2)
        .build();

IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> service.calculate(line));
```

Nếu `build()` ném, JUnit báo lỗi từ Arrange; nó **không** được xem là exception đúng cho `service.calculate`. Phần này cũng là mảnh minh họa yêu cầu builder và SUT được khai báo.

### `assertThrows` so với `assertThrowsExactly`

- `assertThrows(Expected.class, executable)` chấp nhận `Expected` **hoặc subtype**.
- `assertThrowsExactly(Expected.class, executable)` yêu cầu đúng runtime class `Expected`, theo API JUnit Jupiter có hỗ trợ.
- Chọn “exact” nếu khác biệt subtype có ý nghĩa đối với hợp đồng lỗi; không lạm dụng nếu subclass hợp lệ.

Cả hai đều **không tự xác nhận nguồn gốc exception**. Lambda phải được khoanh đúng, và khi cần có thể assert error code/cause hoặc tương tác.

## 6. Khi nào dùng `assertDoesNotThrow` cho Arrange?

Đôi khi bạn muốn làm rõ bước setup **không được phép thất bại**:

```java
OrderLine fixture = assertDoesNotThrow(
        () -> fixtures.createValidOrderLine("SKU-1", -2),
        "Fixture setup must succeed");

IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> service.calculate(fixture));
```

Đây là mảnh JUnit 5 và API ứng dụng minh họa. `assertDoesNotThrow` có thể giúp thông báo “setup lỗi” nổi bật hơn thay vì để exception xuất hiện như một failure thông thường. **Nó không bắt buộc:** nếu code Arrange đơn giản, gọi thẳng fixture helper bên ngoài `assertThrows` thường rõ ràng và ít lớp wrapper hơn.

Đừng bọc tất cả test body trong `assertDoesNotThrow` rồi sau đó kiểm tra exception khác; mục tiêu là phân pha, không phải thêm assertion quanh mọi dòng.

Quan trọng: helper setup có thể chủ động từ chối fixture không hợp lệ. Nếu vậy, phải chọn fixture đúng ý đồ; không ép helper bỏ validation hoặc catch lỗi chỉ để qua được Arrange.

## 7. Valid input cho setup khác với invalid input cho SUT

Một tình huống thường gây nhầm:

- Bạn muốn kiểm tra SUT từ chối **quantity âm**.
- Fixture builder cũng có validation **quantity không được âm**.
- Lúc gọi builder, exception xuất hiện sớm và không tới SUT.

Nếu builder thật sự cam kết chỉ tạo object hợp lệ, cần quyết định chiến lược test:

1. Kiểm thử input qua API SUT **ở trước validation của builder**, ví dụ gọi service nhận DTO/request chưa được validate.
2. Dùng một value object test cho phép biểu diễn trạng thái không hợp lệ tại đúng boundary đang thử, nếu kiến trúc cho phép.
3. Nếu trạng thái không hợp lệ **không thể tồn tại theo contract**, câu hỏi “SUT xử lý quantity âm trong object đã validate” có thể đang thử hành vi không thể xảy ra bằng public API. Cần điều chỉnh mục tiêu kiểm thử, không dùng reflection hoặc phá invariant một cách tùy tiện.
4. Nếu chính builder chịu trách nhiệm validation, chuyển test exception sang builder, thay vì tuyên bố đang test service.

**“Fixture hợp lệ”** ở đây nghĩa là nó được tạo **thành công** và thỏa các tiền điều kiện khác của phép kiểm thử, không nhất thiết mọi trường đều là dữ liệu hợp lệ theo quy tắc mà SUT cần kiểm tra. Cần chỉ rõ lớp nào chịu trách nhiệm validate mỗi điều kiện.

## 8. Kiểm tra SUT thực sự được gọi

Giới hạn `assertThrows` là lớp bảo vệ đầu tiên. Trong vài ca phức tạp còn cần xác nhận **tương tác**:

```java
Order input = validOrderFixture();

IllegalStateException error = assertThrows(
        IllegalStateException.class,
        () -> service.submit(input));

verify(repository).save(input);
```

Đây là **mảnh JUnit + Mockito** giả định `service`, `repository` và phương thức `verify` đã được cấu hình. Chỉ thêm verification nếu **thực sự thuộc contract đang thử**. Ví dụ nếu nghiệp vụ bắt buộc validation **trước** khi ghi repository, thì test validation failure phải kiểm tra ngược lại `verifyNoInteractions(repository)` hoặc `verify(repository, never()).save(any())` tùy mục tiêu.

Không nên cố định mọi chi tiết triển khai bằng mock verification; test sẽ dễ vỡ sau refactor mà hành vi không thay đổi. Sự bảo đảm chính thường là **phạm vi Act hẹp + trạng thái/exception đúng hợp đồng**. Verification là bằng chứng bổ sung khi có ý nghĩa.

Nếu một mock được cấu hình ném đúng loại exception đang kỳ vọng, cần phân biệt bạn đang test **SUT chuyển/propagate lỗi dependency** hay đang vô tình chỉ test **mock throw**. Test thành công phải chứng minh policy của SUT (ví dụ dịch lỗi, fallback hợp lệ, rollback hoặc ghi state), không chỉ rằng stub tự ném được một exception.

## 9. Không để assertion nằm trong lambda kỳ vọng exception của SUT

Sai:

```java
assertThrows(AssertionError.class, () -> {
    Result result = sut.execute();
    assertEquals("OK", result.status());
});
```

Đây là mảnh JUnit **cố tình minh họa lỗi thiết kế**. Test đang chứng minh một assertion nào đó thất bại, nhưng có thể vô tình “đạt” vì test assertion bị lỗi chứ không phải vì SUT xử lý đúng. Ngay cả khi đang test một hàm assertion utility riêng, phải đặt tên và mục tiêu rõ.

Đối với test business thông thường:

```java
Result result = sut.execute();
assertEquals("OK", result.status());
```

Hoặc khi kỳ vọng lỗi từ SUT:

```java
BusinessException ex = assertThrows(
        BusinessException.class,
        () -> sut.execute());
assertEquals(ErrorCode.CONFLICT, ex.code());
```

Đây là các mảnh minh họa có kiểu/enum ứng dụng được định nghĩa. **Không gộp nhiều pha trong một lambda** nếu việc gộp có thể làm sai nguồn exception.

## 10. Lỗi trong `@BeforeEach` và `@BeforeAll`

JUnit Jupiter cung cấp lifecycle callbacks:

- `@BeforeAll`: chuẩn bị tài nguyên/chia sẻ trạng thái theo cấu hình vòng đời test class.
- `@BeforeEach`: chuẩn bị trước mỗi test.
- `@Test`: phần test body chứa Act và Assert.
- `@AfterEach` và `@AfterAll`: cleanup.

Ví dụ:

```java
@BeforeEach
void setup() {
    order = fixtureFactory.createOrder(); // Có thể lỗi.
}

@Test
void rejectsNegativeQuantity() {
    assertThrows(IllegalArgumentException.class,
            () -> service.calculate(order));
}
```

Đây là **mảnh JUnit 5** cần field `order`, `service`, `fixtureFactory` và các import. Nếu `setup()` ném `IllegalArgumentException`, **method test chưa được thực thi**. JUnit ghi nhận sự cố ở lifecycle setup; `assertThrows` trong method test không có cơ hội chứng minh hành vi của SUT.

Đây là một lợi ích của tách lifecycle, nhưng cũng tạo rủi ro nếu error bị che:

```java
@BeforeEach
void setup() {
    try {
        order = fixtureFactory.createOrder();
    } catch (Exception ignored) {
        order = null;
    }
}
```

Đây là **anti-pattern**: lỗi setup bị nuốt, rồi test thất bại với NPE hay lỗi không liên quan sâu hơn. Tốt hơn để setup thất bại **ở đúng vị trí**.

Một số lưu ý:
- Chỉ đặt **setup thực sự dùng chung** trong `@BeforeEach`; fixture đặc thù nên đặt trong test để dễ đọc.
- Không tạo side effect toàn cục không cần thiết ở `@BeforeAll` vì khi hỏng có thể ảnh hưởng nhiều test trong cùng class.
- Dùng cleanup đáng tin cậy cho tài nguyên; thất bại trong `@AfterEach` cần được xem là vấn đề riêng.
- Trạng thái shared giữa các test có thể gây lỗi ngẫu nhiên khi chạy song song; ưu tiên isolation.

## 11. Teardown lỗi khác với Act lỗi

Một test có thể hoàn thành SUT và assertion thành công, nhưng `@AfterEach` hoặc thao tác `close()` lại ném exception. Điều này không có nghĩa production behavior đang được test đã sai theo cùng cách.

Ví dụ:

```java
@Test
void processesOrder() throws Exception {
    try (TestDatabase db = startDatabase()) {
        Result result = sut.process(db);
        assertEquals(Result.SUCCESS, result);
    }
}
```

Đây là **mảnh thiết kế**, cần định nghĩa `TestDatabase` là `AutoCloseable`, `Result` và các API ứng dụng. Khi body thất bại rồi `db.close()` cũng thất bại, try-with-resources có thể giữ **body exception** làm primary, lỗi close trong `getSuppressed()`. Nếu body thành công nhưng close lỗi, lỗi close là primary được báo.

Vì vậy khi phân tích stack trace test:
- Xem exception chính xuất hiện từ dòng Arrange, Act, Assert hay cleanup.
- Xem `getSuppressed()` nếu có nhiều lỗi.
- Không sửa SUT để “qua test” khi lỗi là container teardown hoặc connection cleanup.
- Không nuốt cleanup exception một cách mù quáng; rò tài nguyên giữa các test có thể gây failure về sau.

Ngược lại, lỗi SUT không được phép bị biến mất chỉ vì cleanup cũng lỗi. `try-with-resources` hữu ích để giữ thông tin đó.

## 12. Mock/stub: lỗi cấu hình test và lỗi SUT có thể cùng loại

Một test có thể dùng Mockito:

```java
when(repository.load("A")).thenReturn(null);
assertThrows(NullPointerException.class,
        () -> service.process("A"));
```

Đây là mảnh JUnit/Mockito. Một `NullPointerException` có thể là bug trong SUT hoặc đơn giản do mock trả `null` trái contract. Để test hữu ích, phải xác định **lỗi nào được kỳ vọng**:
- Nếu đang test SUT xử lý dependency trả dữ liệu rỗng, assert một error code/fallback đúng nghiệp vụ, không mặc nhiên kỳ vọng NPE.
- Nếu đang test SUT từ chối input `null`, tạo input đó tách biệt khỏi mock setup.
- Nếu mock trả `null` do thiếu stub, hãy xem lại fixture, không vội sửa logic production.
- Nếu `when(...)` hoặc `thenAnswer(...)` có callback ném lỗi, nó có thể phát sinh trong Arrange, lúc mock được cấu hình, hoặc trong Act tùy thời điểm thực thi.

Một nguyên tắc quan trọng: **mock phải mô phỏng một dependency có hợp đồng rõ**, không tùy tiện khiến dependency “làm mọi thứ” để ép một exception xuất hiện.

## 13. Test fixtures có nhiều bước: phân pha tường minh

Với test tích hợp, Arrange có thể gồm tạo schema, seed dữ liệu, lấy token thử, cấu hình HTTP client, mở transaction và tạo request. Nếu gom tất cả trong một helper “magic”, lỗi setup rất khó chẩn đoán.

Có thể chia Arrange thành những bước có tên:

```java
TestDatabase db = startTestDatabase();
Customer customer = seedCustomer(db, "fixture-001");
Request request = newRequest(customer.id());

Response response = application.handle(request);

assertEquals(409, response.status());
```

Đây là mảnh integration test, cần các API ứng dụng định nghĩa. Nếu `seedCustomer` lỗi do duplicate key hoặc DB không kết nối được, test thất bại **trước Act**; không được đánh đồng nó với việc application trả 409. Mỗi bước chỉ nên tạo dữ liệu phục vụ đúng kịch bản.

Khi một test có nhiều nhánh lỗi, có thể gắn nhãn rõ bằng helper/tên biến, nhưng không nên che mọi lỗi bằng custom exception quá chung như “test failed”. Nếu muốn bọc lỗi setup, hãy giữ cause:

```java
try {
    seedData();
} catch (SQLException ex) {
    throw new TestSetupException("Cannot seed test database", ex);
}
```

Đây là mảnh code cần `TestSetupException` tự định nghĩa và import `java.sql.SQLException`. Bọc như vậy hữu ích tại boundary setup phức tạp; không cần bọc lại mọi lời gọi nhỏ hoặc đưa password/connection string vào message.

## 14. Parameterized tests và lỗi cung cấp dữ liệu

Với JUnit 5, dữ liệu thường đến từ `@MethodSource`, `@CsvSource` hoặc các nguồn tham số khác. Nếu phương thức cung cấp dữ liệu ném exception trong lúc tạo arguments, **test invocation chưa được hình thành hoặc chưa thực hiện Act như dự kiến**.

Ví dụ:

```java
static Stream<Arguments> cases() {
    return Stream.of(
            Arguments.of("SKU-1", -1),
            Arguments.of("SKU-2", -2));
}

@ParameterizedTest
@MethodSource("cases")
void rejectsNegativeQuantity(String sku, int quantity) {
    OrderLine line = new OrderLine(sku, quantity);
    assertThrows(IllegalArgumentException.class,
            () -> service.calculate(line));
}
```

Đây là mảnh JUnit Jupiter Parameterized Tests, yêu cầu JUnit params, imports `Stream` và `Arguments`, các class/field ứng dụng. Nếu `cases()` tính toán dữ liệu bằng helper có thể lỗi, lỗi ở **data source** khác với lỗi từ `service.calculate`.

Nên:
1. Dùng arguments đơn giản, có tên và dễ kiểm tra khi có thể.
2. Nếu data source phụ thuộc IO/DB, cân nhắc tách thành integration fixture thay vì làm phát sinh side effect khó chẩn đoán trong annotation source.
3. Đặt tên invocation rõ ràng để biết tập input nào thất bại.
4. Không cho một nguồn dữ liệu rỗng hoặc không hợp lệ tạo cảm giác toàn bộ yêu cầu đã được kiểm tra.

Đừng dùng `assertThrows` bao quanh chính lời gọi `cases()` trong test hành vi của service nếu mục tiêu không phải kiểm thử data source.

## 15. Nhiều exception xảy ra nối tiếp: lỗi đầu tiên và lỗi thứ cấp

Khi setup, SUT và teardown cùng có lỗi, việc test báo exception nào phụ thuộc **đường thực thi và cơ chế kiểm thử**:

- Nếu Arrange ném, Act không chạy.
- Nếu Act ném, những assertion theo sau trong cùng method thường không chạy.
- Nếu Arrange và Act thành công nhưng Assert ném `AssertionError`, đó là thất bại kiểm tra.
- Nếu cleanup ném sau một lỗi trước đó, `try-with-resources` có thể lưu cleanup trong `getSuppressed()`.
- Nếu `finally` tự ném exception mà không bảo toàn lỗi trước, nó có thể che lỗi gốc.
- JUnit extension/lifecycle có thể báo thêm lỗi; cách runner trình bày nhiều failure không nên được dùng thay cho phân tích stack trace và nguồn lỗi.

**Không chỉ nhìn tên class exception**. Một `IllegalArgumentException` từ fixture builder và một `IllegalArgumentException` từ SUT có thể giống loại nhưng khác nguyên nhân. Thông điệp, call stack, error code, origin và điều kiện tiền đề giúp phân loại.

Nếu cần một quan hệ lỗi ổn định để assert, ứng dụng nên có **exception domain hoặc error code** hơn là so khớp chuỗi message của thư viện/JDK vốn có thể thay đổi.

## 16. Xác minh nơi xảy ra lỗi bằng marker khi cần

Trong một test phức tạp, đôi khi cần chứng minh Act đã bắt đầu hoặc một lời gọi dependency đã xảy ra. Có thể dùng counter/test spy có kiểm soát:

```java
AtomicInteger invocationCount = new AtomicInteger();
Sut sut = new Sut(() -> {
    invocationCount.incrementAndGet();
    throw new DomainException("DEPENDENCY_FAILED");
});

DomainException error = assertThrows(
        DomainException.class,
        sut::execute);

assertEquals(1, invocationCount.get());
```

Đây là **mảnh code thiết kế**, không độc lập; cần `Sut`, `DomainException`, `AtomicInteger`, import và API constructor như đã minh họa. Nếu Arrange thất bại trước `assertThrows`, counter sẽ không được kiểm tra như một Act thành công. Khi Act chạy, counter giúp xác nhận đường gọi mong đợi được đi qua.

Không nên thêm marker khắp production code chỉ để test. Hãy ưu tiên test spy/mock có mục đích rõ và assert trạng thái/interaction quan trọng. Đồng thời, nếu SUT được thiết kế **không gọi dependency khi input invalid**, assert counter bằng `0` mới là phù hợp.

## 17. Bất đồng bộ: lỗi SUT có thể xảy ra sau Act ban đầu

Với `CompletableFuture` hoặc `ExecutorService`, lời gọi Act có thể chỉ **khởi động công việc** rồi trả Future. Exception xảy ra sau đó trong worker không tự được bắt bởi `assertThrows` quanh câu submit/schedule:

```java
CompletableFuture<String> future = sut.loadAsync(request);

CompletionException error = assertThrows(
        CompletionException.class,
        future::join);

assertInstanceOf(DependencyException.class, error.getCause());
```

Đây là mảnh JUnit 5 với SUT và types ứng dụng. **Arrange** tạo `request`, **Act** gọi `sut.loadAsync`, còn **Assert** quan sát stage qua `join`. `CompletionException` là wrapper thường gặp của `join()` khi future exceptional; nếu cancellation, nó có thể ném `CancellationException` trực tiếp. `Future.get()` dùng `ExecutionException` và có thể ném `InterruptedException` ở caller đang chờ.

Khi setup mock async, cần biết nó có ném **ngay khi cấu hình**, ném **đồng bộ khi Act gọi**, hay trả một future hoàn tất exceptionally **sau Act**. Không thể dùng cùng một `assertThrows` bao quanh mọi bước rồi kết luận đã test đúng callback.

Tránh dùng `Thread.sleep` làm cách duy nhất chờ lỗi async: test có thể flaky. Dùng future completion, latch, executor được kiểm soát và timeout phù hợp. Nếu caller bị interrupt trong lúc `get()`, đó là lỗi của **đường chờ trong test** nếu không phải tình huống hủy đang được kiểm thử.

## 18. Kiểm thử exception expected không có nghĩa chấp nhận mọi Throwable

`assertThrows(Exception.class, ...)` hay `assertThrows(RuntimeException.class, ...)` quá rộng có thể tạo false positive tương tự, kể cả khi chỉ bao Act. Ví dụ muốn kiểm tra lỗi validation mà SUT lại có bug `NullPointerException`; nếu chỉ mong `RuntimeException` thì bug cũng khiến test xanh.

Nên chọn:

- Kiểu exception đủ cụ thể theo contract, ví dụ `InvalidOrderException` hoặc `IllegalArgumentException` khi có ý nghĩa.
- `assertThrowsExactly` khi subclass khác sẽ là lỗi contract.
- Mã lỗi hoặc thuộc tính bổ sung ổn định, không lạm dụng exact message của SDK/JDK.
- Điều kiện trạng thái/tương tác sau exception, chẳng hạn database không bị ghi khi validation thất bại.
- Với retry/cancel, assert đúng số lần gọi và trạng thái cuối.

Tránh `assertThrows(Throwable.class, ...)` nếu mục tiêu chỉ là kiểm thử nghiệp vụ thông thường: nó có thể coi `AssertionError` hoặc lỗi nghiêm trọng khác là một “thành công” giả. Một số test framework internals có lý do bắt Throwable để ghi nhận test failure, nhưng đó **không phải pattern assertion phù hợp** cho mọi test ứng dụng.

## 19. Test setup không nên được làm cho “luôn thành công” bằng cách nuốt lỗi

Một anti-pattern:

```java
OrderLine prepare() {
    try {
        return fixtureFactory.create();
    } catch (Exception ignored) {
        return null;
    }
}
```

Đây là mảnh code có factory do ứng dụng định nghĩa. Nó chuyển lỗi fixture thành `null`, làm Act hoặc Assert ném `NullPointerException` ở nơi xa nguyên nhân thật.

Hướng sửa:
- Giữ exception setup gốc hoặc bọc với cause và thông điệp **không chứa dữ liệu nhạy cảm**.
- Tạo fixture nhỏ, rõ tiền điều kiện và kiểm thử riêng nếu helper phức tạp.
- Tách test database/fixtures khỏi network hoặc yếu tố thời gian không cần thiết.
- Đừng dùng giả định `assumeTrue` để tự động bỏ qua mọi lỗi setup; test có thể bị **aborted/skipped** thay vì phát hiện cấu hình hỏng.
- Với dependency bên ngoài thực sự tùy chọn, xác định rõ chính sách integration test và điều kiện môi trường; không ngụy trang hỏng setup thành test pass.

Một test chuẩn bị thành công không bảo đảm SUT hoạt động đúng; ngược lại, setup failure luôn cần được xem xét trước khi kết luận SUT có bug.

## 20. Ma trận tình huống kiểm thử và kết quả mong đợi

| Trường hợp | Điểm thất bại | Kết quả đúng |
| --- | --- | --- |
| Builder sai SKU, SUT chưa được gọi | Arrange | Test báo lỗi setup, không pass exception của SUT |
| Builder hợp lệ, SUT từ chối quantity âm | Act | `assertThrows` nhận đúng domain exception |
| Builder hợp lệ, SUT bất ngờ NPE | Act | Test kỳ vọng validation cụ thể phải FAIL |
| SUT thành công, assertion expected khác actual | Assert | Failure do assertion, không nhận nhầm là exception của SUT |
| `@BeforeEach` không kết nối được DB test | Lifecycle Arrange | Báo thất bại setup/lifecycle; không khẳng định SUT đã chạy |
| `@MethodSource` tạo dữ liệu sai | Parameter source | Báo lỗi nguồn dữ liệu, không phải lỗi Act |
| Mock config bị lỗi trước test body | Arrange | Test failure ở setup, không được nuốt |
| Stub trả exception đúng kiểu nhưng SUT không thực hiện policy | Act | Kiểm tra mapping/fallback/state, không chỉ loại exception |
| Future bị lỗi sau submit | Async completion | Quan sát `join()`/`get()` và cause |
| Cleanup ném sau Assert thành công | Teardown | Test có thể thất bại do cleanup; phân loại đúng |
| Act và `close()` đều lỗi | Act + Cleanup | Xem primary và `getSuppressed()` |
| Setup helper nuốt exception và trả null | Arrange | Sửa helper, không “chữa NPE” ở SUT khi nguồn lỗi là fixture |

Ma trận này hữu ích cho test review và lỗi flaky. Mục tiêu là chứng minh **hành vi của đúng đối tượng đang kiểm thử**, không chỉ làm một assertion có màu xanh.

## 21. Checklist trước khi chấp nhận một test exception

1. Tên test mô tả hành vi của **SUT**, không chỉ tên loại exception.
2. Arrange và Act nằm ở những đoạn mã dễ nhận diện.
3. `assertThrows` chỉ bao đúng thao tác được kỳ vọng ném, tránh constructor/fixture helper không liên quan.
4. Fixture được xây thành công và chỉ có những giá trị bất thường **cố ý cho SUT kiểm tra**.
5. Loại exception kỳ vọng đủ cụ thể; nếu cần, assert error code/cause/attribute ổn định.
6. Test xác minh SUT đã thực hiện hoặc **không thực hiện** những side effects quan trọng.
7. Lỗi `@BeforeEach`/`@BeforeAll`, data provider, mock setup không bị nuốt.
8. Cleanup/teardown errors được phân biệt với Act failure; kiểm tra suppressed khi thích hợp.
9. Test async phân biệt lỗi đồng bộ lúc submit với exceptional completion về sau.
10. Không dùng `catch(Exception)` rộng hoặc `assertThrows(Throwable.class)` để “cho test xanh”.
11. Khi test thất bại, stack trace cho biết **pha** và **nguồn lỗi**; không tự đổi production code chỉ vì gặp cùng một loại exception.
12. Với integration test, test data, transaction và dependency được cô lập, có cleanup và timeout phù hợp.

**Ghi nhớ:** một phép `assertThrows` thành công chỉ chứng minh **một exception phù hợp đã xuất hiện trong lambda**, không chứng minh **đúng đoạn mã cần kiểm thử** đã ném nó. Muốn test đáng tin, hãy tách Arrange khỏi Act, tạo fixture có chủ đích, khoanh hẹp điểm mong đợi exception và xác minh hành vi đúng hợp đồng.
