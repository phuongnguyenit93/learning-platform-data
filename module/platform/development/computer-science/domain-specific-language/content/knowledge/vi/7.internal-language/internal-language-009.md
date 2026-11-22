# Kiểm thử DSL nội bộ

## 1. Vì sao cần kiểm thử DSL nội bộ?

DSL nội bộ (internal Domain-Specific Language) là cách biểu diễn một miền nghiệp vụ bằng cú pháp của một ngôn ngữ lập trình có sẵn. Trong Java, DSL nội bộ thường được xây dựng từ fluent API, method chaining, builder, lambda, kiểu dữ liệu miền và các hàm có tên gần với thuật ngữ nghiệp vụ.

Ví dụ:

~~~java
Policy policy = policy("Gold member discount")
    .when(customerTier().atLeast(GOLD))
    .and(orderTotal().atLeast(Money.of(2_000_000, VND)))
    .then(discountPercent(10));
~~~

Đoạn mã trông giống một câu mô tả chính sách, nhưng nó vẫn là chương trình Java. Compiler kiểm tra cú pháp và kiểu của Java; thư viện DSL định nghĩa các hàm, kiểu và quy tắc tạo nên ý nghĩa nghiệp vụ. Vì vậy, kiểm thử DSL nội bộ cần xác nhận cả hai lớp:

- **Cách viết DSL:** API có dễ hiểu, ghép nối đúng, từ chối cấu trúc không hợp lệ và tận dụng được hệ thống kiểu của ngôn ngữ chủ hay không.
- **Ý nghĩa của DSL:** biểu thức được tạo ra có mô tả đúng quy tắc miền và cho kết quả đúng khi được đánh giá hay thực thi hay không.

Một fluent API có thể biên dịch thành công nhưng vẫn tạo sai mô hình. Một builder có thể cho phép gọi thiếu bước bắt buộc. Một biểu thức có thể đánh giá sai ở đúng ngưỡng hoặc xử lý null không nhất quán. Nếu chỉ kiểm tra rằng đoạn DSL biên dịch được, nhiều lỗi quan trọng vẫn có thể lọt qua.

Kiểm thử DSL nội bộ giúp bảo đảm người dùng có thể diễn đạt đúng ý định, compiler phát hiện được những lỗi thuộc phạm vi kiểu của ngôn ngữ chủ, thư viện DSL giữ đúng ngữ nghĩa miền và các thành phần tích hợp thực hiện đúng kết quả.

## 2. Kiểm thử những lớp nào?

Không nên gom mọi kiểm tra vào một bài test lớn. Hãy chia theo trách nhiệm của DSL và kiến trúc thực thi.

| Lớp kiểm thử | Điều cần xác nhận | Ví dụ |
|---|---|---|
| Kiểu dữ liệu miền | Giá trị và phép toán có ý nghĩa đúng | Money không cộng được với Duration |
| Thành phần biểu thức | Hàm DSL tạo đúng node hoặc đối tượng | customerTier().atLeast(GOLD) tạo điều kiện hạng thành viên |
| Fluent API và builder | Các lời gọi được ghép đúng thứ tự và đúng trạng thái | when(...).and(...).then(...) tạo một policy hoàn chỉnh |
| Kiểm tra ngữ nghĩa | Tên, kiểu, phạm vi và quy tắc hợp lệ | Thuộc tính không tồn tại bị từ chối |
| Đánh giá hoặc thực thi | Biểu thức trả kết quả đúng | Đơn hàng đúng ngưỡng được chấp nhận |
| Kiểm tra tại thời điểm biên dịch | Những cách dùng sai bị compiler từ chối | Không truyền chuỗi vào API yêu cầu Money |
| Tích hợp | DSL kết nối đúng với ứng dụng và dịch vụ | Policy được nạp và áp dụng trong luồng tạo đơn |
| Tương thích và tài liệu | Ví dụ công khai vẫn biên dịch và hoạt động | Code sample trong tài liệu chạy được |

Mỗi lớp trả lời một câu hỏi khác nhau. Kiểm thử thành phần biểu thức không thay thế kiểm thử hành vi; kiểm thử hành vi không chứng minh API có trải nghiệm sử dụng tốt; kiểm thử tích hợp không giúp xác định nhanh lỗi trong một toán tử đơn lẻ.

## 3. Thiết kế DSL để có thể kiểm thử

Khả năng kiểm thử bắt đầu từ cách tổ chức thư viện. Một DSL dễ kiểm thử thường phân biệt rõ phần **xây dựng mô tả**, phần **kiểm tra mô tả** và phần **thực thi mô tả**.

### 3.1 Tách xây dựng và thực thi

Nếu mỗi lời gọi DSL lập tức gọi database, gửi HTTP hoặc thay đổi trạng thái bên ngoài, bài test sẽ khó cô lập và dễ phụ thuộc môi trường.

Một thiết kế thường thuận tiện hơn là để DSL tạo ra một mô hình hoặc biểu thức có thể kiểm tra trước:

~~~java
Policy policy = policy("Gold member discount")
    .when(customerTier().atLeast(GOLD))
    .and(orderTotal().atLeast(Money.of(2_000_000, VND)))
    .then(discountPercent(10));

EvaluationResult result = evaluator.evaluate(policy, context);
~~~

Trong thiết kế này:

- Các hàm DSL xây dựng cấu trúc mô tả.
- Validator kiểm tra cấu trúc và ràng buộc.
- Evaluator nhận mô tả cùng dữ liệu đầu vào và trả kết quả.
- Adapter hoặc ứng dụng quyết định cách dùng kết quả.

Nhờ vậy, có thể kiểm tra cấu trúc mà chưa cần kết nối hệ thống thật; kiểm tra evaluator với dữ liệu nhỏ; và chỉ dùng integration test cho phần kết nối.

Không phải DSL nào cũng cần tạo AST riêng. Một DSL có thể dùng object model, specification, predicate hoặc cấu trúc cấu hình. Điều quan trọng là có một ranh giới rõ để kiểm tra ý nghĩa trước khi gây tác dụng phụ.

### 3.2 Ưu tiên kiểu dữ liệu miền

Kiểu dữ liệu giúp loại bỏ một số cách dùng sai ngay khi biên dịch. Ví dụ, nếu giá trị tiền tệ được biểu diễn bằng Money, API có thể tránh việc truyền một số double không có đơn vị:

~~~java
Money threshold = Money.of(2_000_000, VND);
Condition condition = orderTotal().atLeast(threshold);
~~~

Thiết kế này rõ ràng hơn một API nhận mọi thứ dưới dạng Object hoặc String:

~~~java
Condition condition = compare("order.total", ">=", "2000000");
~~~

Kiểu mạnh không loại bỏ mọi lỗi nghiệp vụ. Một Money hợp lệ về kiểu vẫn có thể dùng sai loại tiền hoặc sai thời điểm quy đổi. Các quy tắc đó cần được kiểm tra riêng.

### 3.3 Giữ các đối tượng DSL bất biến khi phù hợp

Nếu policy hoặc expression có thể bị thay đổi sau khi tạo, một nơi khác trong chương trình có thể vô tình làm thay đổi kết quả kiểm thử hoặc hành vi thực thi.

Với mô hình khai báo, nên cân nhắc:

- Dùng đối tượng bất biến sau khi hoàn tất builder.
- Sao chép collection đầu vào thay vì giữ tham chiếu có thể thay đổi.
- Không để getter trả collection nội bộ có thể sửa.
- Tách cấu hình mutable trong giai đoạn xây dựng khỏi mô hình đã hoàn tất.

Kiểm thử cần xác nhận các thuộc tính này nếu chúng là một phần của hợp đồng API.

### 3.4 Tiêm các phụ thuộc có thể thay đổi

DSL có thể phụ thuộc vào đồng hồ hệ thống, dịch vụ khách hàng, dữ liệu hoặc cấu hình. Đưa các phụ thuộc đó qua interface hoặc context giúp kiểm thử có thể kiểm soát đầu vào.

Ví dụ, nếu policy kiểm tra thời hạn:

~~~java
EvaluationContext context = EvaluationContext.builder()
    .clock(Clock.fixed(
        Instant.parse("2026-12-10T10:00:00Z"),
        ZoneOffset.UTC
    ))
    .build();
~~~

Đồng hồ cố định giúp test không thay đổi theo ngày chạy. Cách tương tự có thể áp dụng cho tỷ giá, dữ liệu thành viên hoặc dịch vụ bên ngoài bằng fake hoặc stub.

## 4. Kiểm thử kiểu dữ liệu và toán tử miền

Kiểu dữ liệu miền là nền tảng của DSL nội bộ. Hãy kiểm thử quy tắc tạo giá trị, tính bất biến và phép toán mà DSL sử dụng.

### 4.1 Kiểm thử giá trị hợp lệ và không hợp lệ

Ví dụ với Money:

~~~java
class MoneyTest {
    @Test
    void createsMoneyWithCurrency() {
        Money money = Money.of(1000, VND);

        assertEquals(VND, money.currency());
        assertEquals(new BigDecimal("1000"), money.amount());
    }

    @Test
    void rejectsNegativeAmountWhenDomainDisallowsIt() {
        assertThrows(
            IllegalArgumentException.class,
            () -> Money.nonNegative(-1, VND)
        );
    }
}
~~~

Ví dụ trên giả định miền có kiểu Money.nonNegative để biểu diễn khoản không âm. Nếu miền cho phép số âm trong một số trường hợp như bút toán điều chỉnh, không nên áp đặt một quy tắc chung cho mọi giá trị tiền. Hãy đặt bất biến đúng ở loại giá trị hoặc nghiệp vụ tương ứng.

### 4.2 Kiểm thử đơn vị và quy tắc làm tròn

Với tiền tệ, cần kiểm tra:

- Cộng và trừ giá trị cùng đơn vị.
- Hành vi khi hai đơn vị tiền khác nhau.
- Độ chính xác thập phân.
- Quy tắc làm tròn và scale.
- So sánh ở đúng ngưỡng.
- Giá trị cực lớn hoặc cực nhỏ theo giới hạn miền.

Không dùng double cho tiền chỉ vì ví dụ nhỏ có vẻ chính xác. Kiểu số và quy tắc làm tròn cần được xác định rõ trong miền.

### 4.3 Kiểm thử các toán tử logic

Nếu DSL cung cấp and, or, not, before, after hoặc các toán tử so sánh, hãy kiểm tra bảng chân trị và các trường hợp biên.

Ví dụ với AND:

| Điều kiện A | Điều kiện B | Kết quả AND |
|---|---|---|
| true | true | true |
| true | false | false |
| false | true | false |
| false | false | false |

Nếu DSL có trạng thái không xác định, chẳng hạn thuộc tính bị thiếu, cần xác định bảng chân trị mở rộng và kiểm thử riêng. Không nên ngầm coi null là false nếu ngữ nghĩa miền chưa quy định như vậy.

## 5. Kiểm thử các thành phần biểu thức

Nhiều DSL nội bộ tạo biểu thức từ các hàm factory hoặc method. Kiểm thử cần xác nhận mỗi hàm tạo đúng loại biểu thức, lưu đúng toán hạng và giữ được kiểu dữ liệu.

Giả sử API có:

~~~java
Expression<Boolean> eligible =
    customerTier().atLeast(GOLD);
~~~

Các kiểm tra có thể gồm:

- Biểu thức có đúng kiểu Boolean không?
- Thuộc tính được tham chiếu có đúng định danh không?
- Giá trị GOLD có được lưu đúng không?
- Toán tử là AT_LEAST hay GREATER_THAN?
- Biểu thức có bất biến sau khi tạo không?
- Có thể kết hợp biểu thức với toán tử logic hợp lệ không?

Nếu cấu trúc biểu thức là implementation detail, tránh buộc mọi test vào class nội bộ. Có thể kiểm tra thông qua visitor, renderer debug hoặc hành vi công khai. Chỉ kiểm tra trực tiếp AST/model khi cấu trúc đó là hợp đồng có chủ đích hoặc khi cần chẩn đoán lỗi.

### 5.1 Kiểm thử method chaining

Method chaining có thể tạo cảm giác API tự nhiên, nhưng thứ tự gọi và kiểu trả về rất quan trọng.

Ví dụ:

~~~java
Policy policy = policy("Shipping")
    .when(orderTotal().atLeast(Money.of(500_000, VND)))
    .and(destination().isWithin("HCMC"))
    .then(freeShipping());
~~~

Test nên xác nhận:

- Hai điều kiện được kết hợp bằng AND.
- Hành động được gắn vào đúng policy.
- Tên policy được giữ nguyên hoặc chuẩn hóa theo hợp đồng.
- Không mất điều kiện khi gọi and nhiều lần.
- Thứ tự điều kiện không làm thay đổi kết quả nếu ngữ nghĩa quy định AND thuần túy.

Nếu thứ tự có ý nghĩa vì short-circuit hoặc ưu tiên, phải kiểm thử hành vi đó một cách tường minh.

### 5.2 Kiểm thử builder

Builder thường có trạng thái: chưa có điều kiện, đã có điều kiện, đã thêm hành động hoặc đã build. Kiểm thử các chuyển trạng thái:

- Build khi thiếu trường bắt buộc.
- Gọi then trước when.
- Gọi when nhiều lần.
- Thêm điều kiện sau khi build.
- Build nhiều lần.
- Dùng lại builder cho hai policy.
- Truyền collection rỗng hoặc null.

Quy tắc API cần được quyết định rõ. Một số builder có thể cho phép bổ sung nhiều điều kiện; một số chỉ cho phép một khối. Test phải phản ánh hợp đồng đã công bố.

Ví dụ:

~~~java
@Test
void builderRejectsPolicyWithoutAction() {
    PolicyBuilder builder = policy("Missing action")
        .when(customerTier().atLeast(GOLD));

    assertThrows(
        IllegalStateException.class,
        builder::build
    );
}
~~~

Nếu API dùng type-state để không cho phép trạng thái thiếu action ngay từ compile time, test runtime này có thể không cần; thay vào đó cần compile-fail test ở lớp kiểm thử kiểu.

## 6. Kiểm thử ngữ nghĩa của DSL

Kiểm thử ngữ nghĩa là xác nhận biểu thức DSL có nghĩa đúng với miền và trả kết quả đúng với các đầu vào cụ thể.

Giả sử chính sách:

~~~java
Policy goldDiscount = policy("Gold discount")
    .when(customerTier().atLeast(GOLD))
    .and(orderTotal().atLeast(Money.of(2_000_000, VND)))
    .then(discountPercent(10));
~~~

Một bộ kiểm thử hành vi cần có trường hợp đạt, không đạt và đúng ngưỡng:

~~~java
class GoldDiscountPolicyTest {
    private final Evaluator evaluator = new Evaluator();

    @Test
    void appliesDiscountWhenBothConditionsAreSatisfied() {
        EvaluationContext context = context(
            GOLD,
            Money.of(2_500_000, VND)
        );

        EvaluationResult result =
            evaluator.evaluate(goldDiscount, context);

        assertTrue(result.isEligible());
        assertEquals(
            Money.of(250_000, VND),
            result.discount()
        );
    }

    @Test
    void rejectsOrderBelowMinimum() {
        EvaluationContext context = context(
            GOLD,
            Money.of(1_999_999, VND)
        );

        EvaluationResult result =
            evaluator.evaluate(goldDiscount, context);

        assertFalse(result.isEligible());
    }

    @Test
    void acceptsOrderAtExactMinimum() {
        EvaluationContext context = context(
            GOLD,
            Money.of(2_000_000, VND)
        );

        EvaluationResult result =
            evaluator.evaluate(goldDiscount, context);

        assertTrue(result.isEligible());
    }
}
~~~

Các lớp Evaluator, EvaluationContext và EvaluationResult trong ví dụ là API minh họa. Test thật cần dùng interface và cách khởi tạo thực tế của DSL.

### 6.1 Kiểm thử theo bảng dữ liệu

Với nhiều tổ hợp đầu vào, parameterized test giúp giảm lặp:

~~~java
@ParameterizedTest
@CsvSource({
    "GOLD, 2500000, true",
    "GOLD, 2000000, true",
    "GOLD, 1999999, false",
    "SILVER, 2500000, false",
    "SILVER, 1500000, false"
})
void evaluatesEligibility(
    String tier,
    long total,
    boolean expected
) {
    EvaluationContext context =
        context(tier, Money.of(total, VND));

    EvaluationResult result =
        evaluator.evaluate(goldDiscount, context);

    assertEquals(expected, result.isEligible());
}
~~~

Nếu định dạng số hoặc dữ liệu phức tạp, có thể dùng MethodSource thay vì CsvSource để tạo object rõ ràng.

### 6.2 Kiểm thử trường hợp biên

Các điều kiện thường có lỗi ở điểm biên:

- Bằng đúng ngưỡng.
- Ngay dưới hoặc trên ngưỡng.
- Ngày bắt đầu và ngày kết thúc.
- Giá trị rỗng hoặc thiếu.
- Collection không có phần tử.
- Giá trị lớn nhất theo kiểu dữ liệu.
- Số thập phân có nhiều chữ số.
- Chuỗi có khoảng trắng hoặc khác biệt chữ hoa/chữ thường.

Với khoảng thời gian, xác định rõ đầu mút bao gồm hay không. Nếu policy có hiệu lực từ 00:00 ngày 1 đến trước 00:00 ngày 1 tháng sau, test cần cố định timezone và clock.

### 6.3 Kiểm thử quy tắc kết hợp

Nếu DSL hỗ trợ nhiều điều kiện, hãy kiểm tra từng toán tử và cách lồng biểu thức:

~~~java
Condition condition =
    customerTier().atLeast(GOLD)
        .and(orderTotal().atLeast(minimum))
        .or(employeePurchase());
~~~

Test phải xác nhận precedence và grouping. Nếu API không quy định rõ thứ tự ưu tiên, nên yêu cầu người dùng dùng ngoặc hoặc method group rõ ràng thay vì dựa vào thứ tự gọi khó đoán.

### 6.4 Kiểm thử short-circuit và số lần đánh giá

Nếu điều kiện có thể truy cập dữ liệu hoặc gọi hàm, cần quy định một nhánh false có ngăn đánh giá nhánh tiếp theo không. Test có thể dùng fake expression đếm số lần evaluate để kiểm tra:

- AND có dừng sau điều kiện false không?
- OR có dừng sau điều kiện true không?
- Một biểu thức có bị đánh giá nhiều lần ngoài ý muốn không?
- Có tác dụng phụ nào xảy ra khi nhánh không cần thiết không?

Nếu DSL được thiết kế là khai báo thuần, nên tránh cho biểu thức điều kiện gây tác dụng phụ. Khi đó, thứ tự đánh giá ít gây rủi ro hơn nhưng vẫn cần được định nghĩa.

## 7. Kiểm thử lỗi và xác thực DSL

Một DSL tốt phải từ chối cách dùng không hợp lệ bằng lỗi có ích. Kiểm thử cần xác nhận cả việc phát hiện lỗi lẫn nội dung chẩn đoán.

Các nhóm lỗi phổ biến:

- Thiếu điều kiện hoặc hành động bắt buộc.
- Dùng sai kiểu dữ liệu.
- Tham chiếu thuộc tính không tồn tại.
- Dùng toán tử không hỗ trợ cho kiểu.
- Kết hợp biểu thức Boolean với giá trị không phải Boolean.
- Dùng đơn vị tiền tệ không tương thích.
- Cấu hình trùng hoặc xung đột.
- Truy cập dữ liệu ngoài phạm vi.
- Dùng builder ở trạng thái không hợp lệ.

Ví dụ:

~~~java
@Test
void reportsMissingRequiredCondition() {
    DslValidationException error = assertThrows(
        DslValidationException.class,
        () -> policy("Incomplete").then(discountPercent(10)).build()
    );

    assertTrue(error.getMessage().contains("condition"));
}
~~~

Trong test thật, tránh phụ thuộc quá chặt vào toàn bộ câu thông báo nếu nội dung có thể được biên tập lại. Nên kiểm tra mã lỗi ổn định, loại lỗi, vị trí nguồn và tham số có ý nghĩa. Ví dụ:

~~~java
assertEquals("DSL_REQUIRED_CONDITION", error.code());
assertEquals("policy.discount", error.path());
~~~

### 7.1 Phân biệt lỗi xây dựng, lỗi xác thực và lỗi thực thi

| Giai đoạn | Ví dụ | Cách kiểm thử |
|---|---|---|
| Xây dựng API | Gọi build khi thiếu action | Assert exception hoặc compile-time rejection |
| Xác thực ngữ nghĩa | Thuộc tính không tồn tại | Assert diagnostic và path |
| Đánh giá | Dữ liệu đầu vào thiếu | Assert kết quả hoặc lỗi theo hợp đồng |
| Tích hợp | Service dữ liệu không khả dụng | Assert cách xử lý lỗi hạ tầng |

Không nên để mọi lỗi trở thành IllegalArgumentException chung chung. Một mô hình lỗi có mã và ngữ cảnh giúp người dùng sửa mô tả, còn ứng dụng có thể xử lý lỗi vận hành riêng.

## 8. Kiểm thử các bảo đảm tại thời điểm biên dịch

Một lợi ích lớn của DSL nội bộ là tận dụng hệ thống kiểu của ngôn ngữ chủ. Một số cách dùng sai có thể bị từ chối trước khi chương trình chạy.

Ví dụ API định kiểu:

~~~java
Condition<Money> orderTotal();
Condition<CustomerTier> customerTier();

Money threshold = Money.of(2_000_000, VND);
Condition<Boolean> eligible =
    orderTotal().isAtLeast(threshold);
~~~

Nếu API chỉ chấp nhận Money, việc truyền String hoặc Duration sẽ không biên dịch. Đây là một bảo đảm cần được giữ qua các thay đổi API.

### 8.1 Positive compile tests

Positive compile test xác nhận các ví dụ hợp lệ vẫn biên dịch. Các ví dụ quan trọng nên được đưa vào test source set hoặc sample project được build trong CI.

Ví dụ:

~~~java
@Test
void documentedPolicyExampleCompiles() {
    Policy policy = policy("Shipping")
        .when(orderTotal().atLeast(Money.of(500_000, VND)))
        .then(freeShipping());

    assertNotNull(policy);
}
~~~

Kiểm tra biên dịch giúp phát hiện việc đổi tên method, đổi generic type hoặc thay đổi overload làm hỏng người dùng DSL.

### 8.2 Negative compile tests

Negative compile test xác nhận một đoạn mã sai phải bị compiler từ chối. Ví dụ:

~~~java
// Đoạn mã này được kỳ vọng không biên dịch:
Condition<Boolean> condition =
    orderTotal().isAtLeast("2000000");
~~~

Có thể thực hiện bằng Java Compiler API, một compile-testing library hoặc một project mẫu được build với kết quả lỗi mong đợi. Bài test cần xác nhận compile thất bại vì lý do phù hợp; nếu thất bại do thiếu dependency hoặc lỗi cú pháp không liên quan, test vẫn chưa chứng minh được hợp đồng kiểu.

Không nên kiểm tra nguyên văn toàn bộ thông báo compiler vì thông báo có thể thay đổi theo phiên bản JDK. Hãy xác nhận việc biên dịch thất bại và, nếu công cụ cho phép, xác nhận vị trí hoặc loại lỗi mong đợi.

### 8.3 Type-state API

Một số DSL dùng generic type để biểu diễn trạng thái builder. Ví dụ, một policy chỉ có thể build sau khi có condition và action. Kiểu trả về của mỗi method giới hạn thao tác tiếp theo.

Ý tưởng:

~~~java
PolicyStart start = policy("Discount");
PolicyWithCondition configured = start.when(eligible());
PolicyComplete complete = configured.then(discountPercent(10));
Policy policy = complete.build();
~~~

Các kiểu trên chỉ là minh họa. Nếu type-state được dùng, hãy viết compile tests cho các chuỗi hợp lệ và không hợp lệ. Đổi lại, API có thể phức tạp hơn và tạo nhiều generic type; cần cân nhắc liệu lợi ích phát hiện lỗi sớm có đáng với độ khó đọc.

## 9. Kiểm thử lambda, generic và overload của ngôn ngữ chủ

DSL nội bộ thường dựa vào các tính năng nâng cao của ngôn ngữ chủ. Chúng có thể tạo lỗi khó nhận ra khi API phát triển.

Với Java, cần chú ý:

- Overload có thể khiến lambda được suy luận sang interface khác với dự định.
- Generic type có thể bị mất thông tin do type erasure.
- Method reference có thể không còn khớp sau khi đổi chữ ký.
- Null có thể làm overload trở nên mơ hồ hoặc chọn sai nhánh.
- Checked exception trong lambda có thể khiến API khó sử dụng.
- Varargs và generic overload có thể gây bất ngờ khi truyền collection.

Ví dụ, nếu có hai method nhận Predicate và Function, một lambda ngắn có thể gây ambiguity tùy kiểu trả về:

~~~java
builder.when(customer -> customer.isActive());
~~~

Khi API có overload, hãy viết compile test với các dạng lambda, method reference và kiểu dữ liệu mà người dùng dự kiến. Tránh thêm overload chỉ vì muốn rút ngắn cú pháp nếu nó làm lời gọi khó phân giải.

## 10. Kiểm thử tích hợp với ứng dụng

Unit test có thể chứng minh evaluator đúng với context giả lập, nhưng chưa chứng minh DSL hoạt động trong ứng dụng thật.

Integration test nên kiểm tra các ranh giới:

- Cấu hình DSL được nạp từ nguồn lưu trữ.
- Builder hoặc parser tạo mô hình mà ứng dụng mong đợi.
- Dependency injection cung cấp đúng evaluator và service.
- Dữ liệu thật được ánh xạ đúng vào EvaluationContext.
- Kết quả DSL được ứng dụng chuyển thành quyết định hoặc hành động.
- Lỗi DSL được hiển thị hoặc ghi nhận đúng.

Ví dụ một bài integration test cho policy:

~~~java
@SpringBootTest
class DiscountPolicyIntegrationTest {
    @Autowired
    DiscountService discountService;

    @Test
    void appliesConfiguredPolicyToEligibleOrder() {
        Order order = eligibleOrder();

        DiscountResult result =
            discountService.calculate(order);

        assertEquals(
            Money.of(250_000, VND),
            result.discount()
        );
    }
}
~~~

Đây là ví dụ Spring Boot mang tính minh họa. Trong test thật, cần kiểm soát dữ liệu, transaction, clock và các dependency ngoài. Chỉ dùng database hoặc service thật khi mục tiêu kiểm thử cần xác nhận chính tích hợp đó.

### 10.1 Phân biệt fake, stub và mock

- **Fake:** triển khai đơn giản nhưng có hành vi thực tế đủ cho test, ví dụ in-memory repository.
- **Stub:** trả dữ liệu định trước để test một nhánh.
- **Mock:** ghi nhận lời gọi để xác nhận một tương tác cụ thể.

Với DSL thiên về biểu thức thuần, nên ưu tiên kiểm tra kết quả thay vì xác nhận quá nhiều lời gọi nội bộ. Mock hữu ích khi hợp đồng yêu cầu một dịch vụ phải được gọi đúng số lần hoặc không được gọi trong một nhánh.

### 10.2 Kiểm thử lỗi dịch vụ ngoài

Nếu DSL có biểu thức tra cứu thông tin khách hàng hoặc tỷ giá, cần kiểm tra:

- Timeout.
- Dữ liệu không tồn tại.
- Lỗi xác thực.
- Lỗi dịch vụ tạm thời.
- Retry và giới hạn số lần thử.
- Hành vi khi kết quả không xác định.

Không để test phụ thuộc mạng công cộng hoặc dữ liệu bên ngoài không ổn định. Dùng stub/fake trong unit test và chỉ dành integration test có kiểm soát cho hợp đồng kết nối.

## 11. Kiểm thử property-based và các thuộc tính tổng quát

Ví dụ cụ thể kiểm tra các trường hợp đã biết. Property-based testing sinh nhiều đầu vào để kiểm tra những thuộc tính phải đúng với cả một tập giá trị.

Ví dụ, với phép cộng tiền cùng loại tiền:

- Kết quả có cùng currency.
- amount(a + b) bằng amount(a) + amount(b) theo scale đã định.
- a + zero bằng a.

Với điều kiện so sánh:

- Nếu a lớn hơn b thì a >= b phải đúng.
- Nếu a bằng b thì a >= b và a <= b phải đúng.
- Với các giá trị hợp lệ, phủ định của a < b phải tương ứng với a >= b nếu ngữ nghĩa không có trạng thái unknown.

Ví dụ giả mã với property-based framework:

~~~java
@Property
void addingZeroPreservesMoney(
    @ForAll("validMoney") Money amount
) {
    assertEquals(
        amount,
        amount.plus(Money.zero(amount.currency()))
    );
}
~~~

Property-based test cần định nghĩa generator hợp lệ. Không nên sinh tùy tiện giá trị mà miền không cho phép rồi kết luận implementation sai.

### 11.1 Invariant của builder và expression

Một số thuộc tính tổng quát:

- Build thành công luôn tạo policy có đủ thành phần bắt buộc.
- Sửa collection đầu vào sau khi build không làm thay đổi policy bất biến.
- Cùng một policy và context bất biến tạo cùng kết quả.
- Serialize rồi deserialize giữ nguyên ý nghĩa nếu DSL hỗ trợ lưu trữ.
- Chuỗi điều kiện tương đương về mặt logic cho kết quả tương đương trong miền giá trị đã xác định.

Các thuộc tính này thường phát hiện lỗi mà một vài ví dụ đơn lẻ không bao phủ.

## 12. Kiểm thử hồi quy và tương thích API

DSL nội bộ là API mà các module hoặc ứng dụng khác có thể sử dụng. Đổi tên method, thay generic type hoặc thay đổi hành vi có thể phá vỡ mã nguồn của người dùng.

Nên duy trì:

- Bộ ví dụ DSL hợp lệ được biên dịch trong CI.
- Bộ compile-fail cho những cách dùng bị cấm quan trọng.
- Bộ ca kiểm thử hành vi đã xác nhận với nghiệp vụ.
- Kiểm thử tương thích binary nếu thư viện được phân phối dưới dạng artifact.
- Kiểm thử migration nếu có thay đổi API hoặc ngữ nghĩa.

Nếu DSL được phát hành như thư viện, có thể dùng công cụ kiểm tra API compatibility phù hợp với hệ sinh thái build. Việc đổi một method public hoặc generic signature cần được đánh giá theo chính sách versioning của thư viện.

### 12.1 Golden test và snapshot

Nếu DSL tạo AST, expression tree hoặc mô tả có thể render, snapshot test có thể giúp phát hiện thay đổi cấu trúc:

~~~text
AND
  CUSTOMER_TIER_AT_LEAST(GOLD)
  ORDER_TOTAL_AT_LEAST(Money(2000000, VND))
THEN
  DISCOUNT_PERCENT(10)
~~~

Golden test hữu ích khi đầu ra có định dạng ổn định và dễ review. Tuy nhiên, không nên biến snapshot nội bộ thành hợp đồng public nếu nhóm chưa có ý định cam kết cấu trúc đó. Khi snapshot thay đổi, phải hiểu lý do thay đổi thay vì tự động chấp nhận cập nhật.

## 13. Kiểm thử mutation và độ nhạy của test

Mutation testing thay đổi nhỏ implementation, chẳng hạn thay >= thành >, bỏ một điều kiện AND hoặc đảo true thành false, rồi xem bộ test có phát hiện không.

Ví dụ:

- Thay toán tử lớn hơn hoặc bằng bằng lớn hơn.
- Bỏ điều kiện hạng thành viên.
- Đổi phép AND thành OR.
- Tính giảm giá trước khi áp dụng giới hạn.
- Đổi timezone hoặc bỏ kiểm tra thời hạn.

Nếu test vẫn qua sau một thay đổi làm sai quy tắc, bộ test chưa đủ nhạy. Mutation testing đặc biệt hữu ích cho evaluator và toán tử miền, nơi một ký tự thay đổi có thể làm thay đổi chính sách.

Không cần chạy mutation testing cho mọi thay đổi nhỏ. Hãy ưu tiên các thành phần chứa logic nghiệp vụ quan trọng hoặc có nhiều trường hợp biên.

## 14. Kiểm thử hiệu năng và tài nguyên

Nếu DSL được đánh giá với số lượng lớn biểu thức hoặc trong luồng có độ trễ nghiêm ngặt, cần đo hiệu năng trên workload đại diện.

Các yếu tố nên đo:

- Thời gian tạo expression hoặc policy.
- Thời gian validate/build.
- Thời gian đánh giá một context.
- Thông lượng khi đánh giá hàng loạt.
- Allocation và bộ nhớ giữ lại.
- Chi phí cache hoặc compile nếu có.
- Hành vi khi policy có nhiều điều kiện lồng nhau.

Benchmark nên tách chi phí xây dựng khỏi chi phí thực thi. Không so sánh hai DSL bằng một benchmark mà một bên đã cache expression còn bên kia phải parse hoặc build lại ở mỗi lần chạy.

Nếu có thể, dùng benchmark harness phù hợp thay vì đo thời gian bằng một lần gọi System.currentTimeMillis trong unit test. Unit test không nên thất bại ngẫu nhiên chỉ vì máy CI chậm.

## 15. Kiểm thử bảo mật và giới hạn thực thi

DSL nội bộ có thể chạy trong cùng tiến trình với ứng dụng. Nếu API cho phép callback tùy ý hoặc truy cập object rộng, người viết DSL có thể thực hiện nhiều thao tác hơn dự định.

Hãy kiểm tra:

- API chỉ công khai những thao tác cần thiết.
- Không vô tình để lộ repository, credential hoặc service nhạy cảm.
- Expression không thể sửa dữ liệu nếu chỉ được phép đánh giá.
- Callback không được thực thi nhiều lần ngoài hợp đồng.
- Collection lớn hoặc biểu thức lồng sâu không gây tiêu thụ tài nguyên quá mức.
- Lỗi không làm lộ dữ liệu nhạy cảm.
- Quyền của người tạo policy được kiểm tra ở đúng ranh giới.

Nếu DSL nội bộ chỉ được dùng bởi lập trình viên đáng tin cậy trong mã nguồn đã review, mô hình rủi ro khác với DSL do người dùng cuối cấu hình. Cần xác định rõ ai có thể tạo và thực thi DSL trước khi chọn mức kiểm soát.

## 16. Kiểm thử đồng thời và khả năng tái sử dụng

Một policy bất biến có thể được dùng đồng thời bởi nhiều request. Nhưng nếu evaluator hoặc builder giữ state mutable, kết quả có thể bị ảnh hưởng giữa các lần chạy.

Nên kiểm tra:

- Cùng một policy được đánh giá song song với context khác nhau có kết quả độc lập.
- Evaluator có an toàn khi dùng chung thread hay không.
- Builder có bị dùng đồng thời ngoài ý muốn không.
- Cache không trả kết quả từ context trước.
- Context không bị sửa bởi evaluator nếu hợp đồng không cho phép.

Ví dụ kiểm thử đồng thời nên dùng dữ liệu xác định và executor có thể đóng đúng cách. Không nên dùng Thread.sleep để chờ race condition; hãy dùng latch, barrier hoặc công cụ đồng bộ phù hợp.

Nếu API không cam kết thread-safe, hãy ghi rõ điều đó và kiểm thử hành vi theo hợp đồng. Không nên tự tuyên bố thread-safe chỉ vì một test đồng thời đơn giản chạy thành công.

## 17. Kiểm thử tài liệu và ví dụ sử dụng

Tài liệu DSL nội bộ thường chứa code sample để người dùng sao chép. Những ví dụ này là một phần của trải nghiệm API và nên được biên dịch, chạy trong CI khi có thể.

Kiểm tra:

- Import và tên hàm trong tài liệu còn hợp lệ.
- Các ví dụ tối thiểu biên dịch được.
- Kết quả minh họa đúng với implementation.
- Ví dụ lỗi cho thấy thông báo dễ hiểu.
- Các ví dụ không dựa vào dữ liệu hoặc thời gian ngẫu nhiên.
- Phiên bản thư viện trong hướng dẫn phù hợp với sample project.

Có thể lưu ví dụ trong thư mục sample và dùng build task để biên dịch. Với tài liệu có nhiều đoạn mã, nên tránh sao chép cùng một đoạn ở nhiều nơi vì chúng dễ lệch nhau.

## 18. Một bộ kiểm thử cân đối

Không phải mọi DSL đều cần tất cả loại test với cùng mức độ. Một cấu trúc tham khảo:

| Loại kiểm thử | Phạm vi | Mục tiêu |
|---|---|---|
| Unit test | Value object, operator, builder | Kiểm tra quy tắc nhỏ và nhanh |
| Semantic test | Expression và evaluator | Xác nhận ý nghĩa nghiệp vụ |
| Compile test | API và type-state | Giữ bảo đảm của compiler |
| Integration test | Ứng dụng, repository, service | Xác nhận ranh giới tích hợp |
| Property-based test | Invariant và toán tử | Mở rộng độ bao phủ đầu vào |
| Regression test | Ví dụ đã xác nhận | Giữ hành vi qua thay đổi |
| Performance test | Workload đại diện | Đo độ trễ và tài nguyên |
| Security test | API, callback và dữ liệu | Kiểm tra giới hạn quyền và tác dụng |
| Documentation test | Code sample | Giữ ví dụ hướng dẫn luôn dùng được |

Một chiến lược thực tế thường có nhiều unit và semantic test nhanh, một số compile test, một số integration test có kiểm soát và benchmark riêng. Không nên biến toàn bộ test thành end-to-end vì lỗi sẽ khó định vị và thời gian chạy dài.

## 19. Quy trình xây dựng test cho một DSL mới

Có thể triển khai theo trình tự:

1. **Xác định hợp đồng API:** ghi rõ các cấu trúc hợp lệ, trạng thái builder và kiểu dữ liệu.
2. **Viết ví dụ sử dụng:** tạo các ví dụ nhỏ thể hiện cách người dùng dự kiến viết DSL.
3. **Kiểm tra kiểu:** xác nhận lời gọi hợp lệ biên dịch và lời gọi sai bị từ chối khi có thể.
4. **Kiểm tra cấu trúc:** xác nhận builder và factory tạo mô hình đúng.
5. **Kiểm tra ngữ nghĩa:** dùng ví dụ nghiệp vụ đã xác nhận để kiểm tra evaluator.
6. **Kiểm tra lỗi:** xác nhận lỗi có mã, vị trí và nguyên nhân đủ rõ.
7. **Kiểm tra tích hợp:** kết nối DSL với context, service và luồng ứng dụng.
8. **Mở rộng đầu vào:** dùng parameterized hoặc property-based tests cho điều kiện biên.
9. **Kiểm tra hồi quy:** giữ lại các ví dụ quan trọng khi thay đổi API hoặc ngữ nghĩa.
10. **Đưa vào CI:** biên dịch sample, chạy test và xuất kết quả để review.

Khi phát hiện lỗi từ một tình huống thực tế, hãy bổ sung một test tái hiện lỗi trước hoặc cùng lúc với việc sửa. Test đó trở thành ví dụ hồi quy để bảo đảm lỗi không quay lại.

## 20. Những sai lầm thường gặp

### Chỉ kiểm tra rằng DSL biên dịch được

Compiler chỉ kiểm tra cú pháp và kiểu theo ngôn ngữ chủ. Nó không tự xác nhận quy tắc miền có đúng hay không.

**Cách khắc phục:** bổ sung semantic test và test hành vi với dữ liệu đại diện.

### Chỉ kiểm tra implementation nội bộ

Test phụ thuộc quá nhiều vào class và field nội bộ có thể hỏng khi refactor dù API công khai vẫn hoạt động.

**Cách khắc phục:** ưu tiên kiểm tra hành vi và hợp đồng công khai; chỉ kiểm tra cấu trúc nội bộ khi đó là mục tiêu cần xác nhận.

### Bỏ qua trường hợp biên

Điều kiện >= có thể bị đổi thành > mà test chỉ dùng giá trị lớn hơn ngưỡng vẫn qua.

**Cách khắc phục:** luôn có trường hợp ngay dưới, bằng và ngay trên ngưỡng.

### Dùng mock cho mọi thứ

Mock quá sâu có thể khiến test chỉ xác nhận các lời gọi đã được viết sẵn, không xác nhận kết quả thực tế.

**Cách khắc phục:** dùng object thật cho biểu thức thuần, fake cho dependency đơn giản và mock khi tương tác là một phần của hợp đồng.

### Test phụ thuộc thời gian hoặc dữ liệu bên ngoài

Test có thể lúc qua lúc thất bại do timezone, ngày hiện tại hoặc dịch vụ ngoài.

**Cách khắc phục:** tiêm Clock, dùng dữ liệu cố định và kiểm soát service bằng stub/fake.

### Chấp nhận snapshot mới mà không xem xét

Golden file thay đổi có thể che giấu thay đổi ngữ nghĩa.

**Cách khắc phục:** review nguyên nhân và xác nhận kết quả trước khi cập nhật snapshot.

### Không kiểm tra ví dụ tài liệu

API thay đổi có thể khiến hướng dẫn cũ không còn biên dịch.

**Cách khắc phục:** đưa sample quan trọng vào build và CI.

## 21. Đầu ra cần có sau khi kiểm thử DSL nội bộ

Một bộ kiểm thử có thể bảo trì nên có:

| Đầu ra | Nội dung |
|---|---|
| Hợp đồng API | Cách gọi hợp lệ, trạng thái builder và kiểu dữ liệu |
| Bộ unit test | Kiểm tra value object, factory, builder và operator |
| Bộ semantic test | Các ví dụ đầu vào và kết quả nghiệp vụ mong đợi |
| Compile test | Ví dụ hợp lệ và không hợp lệ ở thời điểm biên dịch |
| Bộ test lỗi | Mã lỗi, vị trí và cách xử lý |
| Integration test | Kết nối với ứng dụng và dependency |
| Bộ regression case | Các lỗi hoặc chính sách đã được xác nhận |
| Test tài liệu | Ví dụ code có thể biên dịch và chạy |
| Báo cáo hiệu năng/bảo mật | Kết quả đo hoặc kiểm tra khi yêu cầu của hệ thống cần |

Các test nên chỉ rõ quy tắc nghiệp vụ nào đang được bảo vệ. Khi quy tắc thay đổi, người review có thể xác định test nào cần cập nhật và vì sao.

## 22. Câu hỏi tự kiểm tra

1. Vì sao kiểm thử DSL nội bộ cần kiểm tra cả cách viết API và ý nghĩa biểu thức?
2. Phân biệt kiểm thử builder, semantic test và integration test.
3. Vì sao nên tách xây dựng policy khỏi thực thi policy?
4. Những trường hợp nào cần được kiểm tra với toán tử AND, OR và NOT?
5. Vì sao phải có test đúng bằng ngưỡng?
6. Positive compile test và negative compile test xác nhận điều gì?
7. Khi nào nên dùng fake, stub hoặc mock?
8. Property-based testing có thể kiểm tra những invariant nào của DSL?
9. Vì sao snapshot test không đủ để chứng minh ngữ nghĩa đúng?
10. Cần kiểm tra những rủi ro nào nếu DSL có lambda hoặc callback?
11. Làm thế nào để giữ các ví dụ trong tài liệu luôn tương thích với API?
12. Một bộ test nên thay đổi thế nào khi DSL được dùng đồng thời bởi nhiều request?

Khi xây dựng DSL nội bộ, hãy xem các ví dụ sử dụng như hợp đồng của thư viện. Kiểm tra chúng từ lúc biên dịch, lúc tạo mô hình, lúc đánh giá quy tắc cho đến khi tích hợp vào ứng dụng. Nhờ vậy, DSL vừa dễ sử dụng vừa giữ được ý nghĩa nghiệp vụ qua các lần thay đổi.
