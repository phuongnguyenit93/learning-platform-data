# Tránh sao chép thuật toán triển khai vào phép kiểm tra

Một bài kiểm thử chỉ có giá trị khi có thể phát hiện một lỗi mà chính mã đang được kiểm tra mắc phải. Vì vậy, phần xác định kết quả mong đợi cần độc lập với cách chương trình tạo ra kết quả đó. Nếu test chép lại cùng thuật toán, cùng điều kiện rẽ nhánh hoặc cùng công thức của mã sản phẩm để tính expected, hai bên có thể cùng sai theo một cách và test vẫn xanh.

Trong thiết kế kiểm thử cho ứng dụng Spring, nguyên tắc này đặc biệt quan trọng với service nghiệp vụ, phép tính tiền, quy tắc giảm giá, phân loại, sắp xếp, chuyển trạng thái và các truy vấn có logic phức tạp. Hãy xác định kết quả mong đợi từ hợp đồng nghiệp vụ, ví dụ đã được tính độc lập hoặc thuộc tính có ý nghĩa của miền nghiệp vụ. Sau đó gọi mã sản phẩm và so sánh kết quả thực tế với kết quả đó.

## 1. Vì sao test không nên lặp lại thuật toán?

Một test thường có ba phần:

1. **Arrange**: chuẩn bị đầu vào và các phụ thuộc cần thiết.
2. **Act**: gọi hành vi đang được kiểm tra.
3. **Assert**: đối chiếu kết quả thực tế với điều được kỳ vọng.

Rủi ro xuất hiện khi phần Assert tự chạy lại thuật toán của phần Act để tạo ra expected. Khi đó, test không còn là một nguồn kiểm chứng độc lập.

Giả sử chính sách vận chuyển quy định đơn hàng có giá trị từ 500.000 đồng trở lên được miễn phí vận chuyển; đơn hàng thấp hơn ngưỡng này chịu phí 30.000 đồng. Service có thể triển khai quy tắc như sau:

~~~java
public class ShippingFeeService {

    private static final BigDecimal FREE_SHIPPING_LIMIT =
            new BigDecimal("500000");

    private static final BigDecimal STANDARD_FEE =
            new BigDecimal("30000");

    public BigDecimal calculate(BigDecimal subtotal) {
        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException("Subtotal must not be negative");
        }

        if (subtotal.compareTo(FREE_SHIPPING_LIMIT) >= 0) {
            return BigDecimal.ZERO;
        }

        return STANDARD_FEE;
    }
}
~~~

Đây là một cách triển khai trực tiếp. Nhưng nếu test cũng dùng cùng ngưỡng, cùng toán tử so sánh và cùng nhánh điều kiện để tính expected, lỗi ở điều kiện biên có thể bị lặp lại trong cả hai nơi.

### Cách viết dễ mắc lỗi

~~~java
@Test
void calculatesShippingFee() {
    BigDecimal subtotal = new BigDecimal("500000");

    BigDecimal expected =
            subtotal.compareTo(new BigDecimal("500000")) >= 0
                    ? BigDecimal.ZERO
                    : new BigDecimal("30000");

    BigDecimal actual = service.calculate(subtotal);

    assertEquals(expected, actual);
}
~~~

Test trên trông có vẻ đang kiểm tra kết quả, nhưng nó đã sao chép chính sách và cách triển khai điều kiện vào phép tính expected. Nếu cả service và test cùng đổi từ toán tử **>=** thành **>** thì test vẫn có thể xanh dù đơn hàng đúng bằng ngưỡng bị tính phí sai.

Việc chuyển công thức trùng lặp vào một hàm trợ giúp trong test cũng không giải quyết được vấn đề. Nếu hàm trợ giúp vẫn lặp lại thuật toán của service, hai phần vẫn có cùng nguy cơ sai.

### Cách viết có kết quả độc lập

Hãy lấy các trường hợp và kết quả từ chính sách đã được xác định, rồi ghi rõ kết quả mong đợi:

~~~java
class ShippingFeeServiceTest {

    private final ShippingFeeService service = new ShippingFeeService();

    @ParameterizedTest
    @CsvSource({
        "499999, 30000",
        "500000, 0",
        "750000, 0"
    })
    void calculatesShippingFeeFromPolicy(
            String subtotalText,
            String expectedFeeText) {

        BigDecimal subtotal = new BigDecimal(subtotalText);
        BigDecimal expected = new BigDecimal(expectedFeeText);

        BigDecimal actual = service.calculate(subtotal);

        assertEquals(0, actual.compareTo(expected));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.calculate(new BigDecimal("-1"))
        );
    }
}
~~~

Các cặp đầu vào và kết quả mong đợi được khai báo độc lập. Test kiểm tra cả trường hợp ngay dưới ngưỡng, đúng bằng ngưỡng và cao hơn ngưỡng. Nếu service vô tình đổi toán tử **>=** thành **>**, trường hợp 500.000 đồng sẽ làm test thất bại.

Trong ví dụ này, so sánh BigDecimal bằng **compareTo** giúp kiểm tra giá trị số mà không phụ thuộc vào scale. Nếu scale là một phần của hợp đồng đầu ra, chẳng hạn API bắt buộc trả về hai chữ số thập phân, hãy kiểm tra scale hoặc biểu diễn JSON riêng như một yêu cầu rõ ràng.

## 2. Xác định expected từ hợp đồng, không từ mã đang kiểm tra

Nguồn tốt nhất cho kết quả mong đợi thường là đặc tả nghiệp vụ, quy tắc sản phẩm, ví dụ được chủ nghiệp vụ xác nhận hoặc dữ liệu chuẩn đã được kiểm chứng độc lập.

Ví dụ, với một service tính số tiền phải thanh toán, đặc tả có thể nêu:

- Số lượng nhân với đơn giá tạo thành thành tiền của dòng hàng.
- Tổng trước giảm giá là tổng thành tiền của các dòng.
- Giảm giá 10% được áp dụng trên tổng trước giảm giá.
- Số tiền giảm được làm tròn đến đơn vị tiền tệ nhỏ nhất theo quy tắc đã thống nhất.

Từ một ví dụ nhỏ, có thể tính độc lập: hai sản phẩm có thành tiền lần lượt là 25.000 và 10.000 đồng; giảm giá 10% tương đương 3.500 đồng; số tiền phải trả là 31.500 đồng. Test nên ghi rõ đầu vào và kết quả 31.500 đồng theo ví dụ đã xác nhận, thay vì gọi một hàm tính giảm giá trong production để dựng expected.

~~~java
@Test
void appliesTenPercentDiscountToKnownSubtotal() {
    var lines = List.of(
            new OrderLine("A", 2, new BigDecimal("12500")),
            new OrderLine("B", 1, new BigDecimal("10000"))
    );

    BigDecimal actual = pricingService.calculatePayable(lines);

    assertEquals(
            0,
            actual.compareTo(new BigDecimal("31500"))
    );
}
~~~

Điểm quan trọng là con số 31.500 phải được xác định từ quy tắc và ví dụ độc lập. Không nên tạo expected bằng cách gọi lại **calculatePayable**, **calculateDiscount** hoặc một helper production có cùng logic.

### Giữ rõ nguồn gốc của từng expected

Khi test có nhiều trường hợp, hãy ghi lại lý do của các giá trị quan trọng bằng tên test hoặc dữ liệu có ý nghĩa. Ví dụ:

- **returnsFreeShippingAtThreshold** mô tả chính sách tại ngưỡng.
- **roundsDiscountAccordingToCurrencyRule** mô tả quy tắc làm tròn.
- **rejectsQuantityBelowZero** mô tả giới hạn hợp lệ của đầu vào.

Với trường hợp phức tạp, comment ngắn có thể chỉ ra điều khoản hoặc ví dụ nghiệp vụ mà expected dựa vào. Tránh comment giải thích lại từng dòng của thuật toán; mục tiêu là làm rõ nguồn kỳ vọng.

Không nên lấy các hằng số private của service làm nguồn expected nếu test đang xác minh chính sách do những hằng số đó biểu diễn. Nếu cả service và test cùng tham chiếu một hằng số sai, thay đổi giá trị hằng số sẽ không làm test phát hiện lỗi. Có thể dùng chung hằng số cho dữ liệu không thuộc đối tượng đang kiểm tra, nhưng expected của chính quy tắc cần được xác định độc lập.

## 3. Các dạng sao chép thuật toán thường gặp

### Lặp lại cùng công thức tính toán

Nếu service tính chiết khấu bằng phép nhân tỷ lệ, test cũng tính expected bằng phép nhân cùng tỷ lệ, một lỗi về cách áp dụng tỷ lệ hoặc làm tròn có thể xuất hiện ở cả hai phía.

Thay vì viết:

~~~java
BigDecimal expected = subtotal.multiply(discountRate);
assertEquals(expected, service.calculateDiscount(subtotal, discountRate));
~~~

hãy dùng các ví dụ số đã tính độc lập theo đặc tả, đặc biệt ở các giá trị có phần thập phân, ngưỡng và quy tắc làm tròn. Ví dụ có thể kiểm tra số tiền giảm của một subtotal đã biết và một tỷ lệ cụ thể.

### Lặp lại điều kiện rẽ nhánh

Nếu production dùng **if**, **switch** hoặc biểu thức điều kiện để phân loại trạng thái, test không nên sao chép cùng điều kiện để chọn expected. Hãy liệt kê từng đầu vào và trạng thái kết quả được quy định.

Ví dụ, nếu trạng thái đơn hàng được phép chuyển từ **PENDING** sang **PAID**, nhưng không được chuyển từ **CANCELLED** sang **PAID**, test nên xác nhận trực tiếp từng cặp trạng thái hợp lệ hoặc không hợp lệ theo bảng chuyển trạng thái nghiệp vụ.

### Lặp lại vòng lặp và phép biến đổi collection

Một service sắp xếp danh sách theo thời điểm tạo không nên được kiểm tra bằng cách chép lại comparator vào test để tạo danh sách expected. Với một bộ dữ liệu nhỏ, hãy ghi rõ thứ tự kết quả cần có.

~~~java
@Test
void sortsOrdersByCreationTime() {
    var input = List.of(
            order("C", "2026-03-03T10:00:00Z"),
            order("A", "2026-03-01T10:00:00Z"),
            order("B", "2026-03-02T10:00:00Z")
    );

    var result = orderService.sortByCreationTime(input);

    assertEquals(
            List.of("A", "B", "C"),
            result.stream().map(Order::id).toList()
    );
}
~~~

Danh sách **A, B, C** là kết quả được ghi rõ từ dữ liệu mẫu. Test không tự sắp xếp đầu vào bằng cùng comparator rồi so sánh với kết quả service.

### Dùng chính mã sản phẩm để tạo expected

Một test không có ý nghĩa nếu expected được lấy từ chính phương thức đang kiểm tra:

~~~java
var expected = service.calculate(input);
var actual = service.calculate(input);

assertEquals(expected, actual);
~~~

Hai lời gọi có thể cùng trả về một kết quả sai. Tương tự, không nên gọi một helper production khác nếu helper đó dùng chung thuật toán hoặc phụ thuộc mà test đang muốn xác minh.

### Dùng cùng bộ chuyển đổi để dựng dữ liệu kỳ vọng

Khi kiểm tra JSON, XML, ngày giờ hoặc dữ liệu đã serialize, hãy cẩn thận nếu dùng chính ObjectMapper, formatter hoặc converter của production để tạo expected. Nếu serializer có lỗi, cả expected và actual có thể cùng phản ánh lỗi đó.

Ví dụ, nếu mục tiêu là xác minh định dạng JSON công khai, có thể so sánh với JSON literal đã được xác định theo hợp đồng hoặc kiểm tra các trường và giá trị cụ thể. Nếu mục tiêu là xác minh một converter, cần một expected được xác định độc lập với converter đó.

## 4. Dùng ví dụ cụ thể để kiểm tra trường hợp biên

Các ví dụ có expected cố định đặc biệt hữu ích ở nơi thuật toán có ranh giới hoặc quy tắc dễ sai. Không chỉ chọn một trường hợp bình thường; hãy chọn dữ liệu có thể phân biệt cách triển khai đúng với một số lỗi phổ biến.

Một số nhóm trường hợp đáng cân nhắc:

| Loại quy tắc | Dữ liệu cần chú ý | Điều cần xác nhận |
|---|---|---|
| Ngưỡng | Ngay dưới, đúng bằng và ngay trên ngưỡng | Toán tử so sánh và chính sách tại biên |
| Tiền tệ | Giá trị có phần thập phân, kết quả nửa đơn vị nhỏ nhất | Quy tắc làm tròn và scale |
| Số lượng | 0, 1, số lớn, số âm | Giới hạn hợp lệ và hành vi biên |
| Ngày giờ | Trước/sau thời điểm chuyển ngày, múi giờ, năm nhuận | Mốc thời gian và quy tắc lịch |
| Danh sách | Rỗng, một phần tử, phần tử trùng, thứ tự đảo | Hành vi với kích thước và thứ tự khác nhau |
| Trạng thái | Mọi cặp chuyển trạng thái quan trọng | Chuyển đổi hợp lệ và bị từ chối |
| Phân trang | Trang đầu, trang cuối, ngoài phạm vi, kích thước 0 hoặc không hợp lệ | Offset, giới hạn và tổng số phần tử |

Test biên có expected cụ thể thường bắt được lỗi tốt hơn việc tăng số lượng test với các đầu vào tương tự nhau. Ví dụ, nếu quy tắc miễn phí vận chuyển bắt đầu từ 500.000 đồng, ba trường hợp 499.999, 500.000 và 500.001 cung cấp tín hiệu rõ ràng hơn ba giá trị đều thấp hơn ngưỡng.

## 5. Khi thuật toán phức tạp, xây dựng oracle độc lập

Với thuật toán đơn giản, có thể dùng ví dụ tính tay. Với thuật toán phức tạp như phân bổ tồn kho, tính lịch, xếp hạng, định tuyến hoặc tính phí theo nhiều bậc, một vài ví dụ cố định có thể chưa đủ bao phủ.

Trong trường hợp đó, cần một **test oracle**: nguồn xác định kết quả đúng để so sánh với kết quả thực tế. Có một số cách xây dựng oracle mà không sao chép mù quáng triển khai.

### Bộ dữ liệu chuẩn được xác nhận độc lập

Dùng một tập đầu vào và đầu ra đã được tính toán hoặc xác nhận từ nguồn có thẩm quyền. Lưu bộ dữ liệu này như fixture và dùng lại trong nhiều test.

Ví dụ: một bảng phí vận chuyển được bộ phận nghiệp vụ xác nhận cho từng vùng, trọng lượng và phương thức giao hàng. Test đọc các hàng trong fixture rồi kiểm tra service trả về đúng mức phí.

Cần quản lý nguồn và phiên bản của bộ dữ liệu. Khi chính sách thay đổi, cập nhật fixture cùng với thay đổi nghiệp vụ và ghi rõ lý do. Không nên âm thầm tái tạo expected bằng service mới.

### Mô hình tham chiếu độc lập

Đối với thuật toán lớn, có thể viết một mô hình tham chiếu đơn giản hơn để tạo kết quả so sánh. Mô hình này cần được xây dựng từ đặc tả độc lập và tránh dùng lại cùng các hàm, cấu trúc quyết định hoặc giả định dễ gây lỗi giống production.

Ví dụ, production có thể dùng cấu trúc dữ liệu tối ưu để phân bổ nhiều đơn hàng vào các kho. Mô hình tham chiếu cho bộ dữ liệu nhỏ có thể duyệt toàn bộ phương án theo quy tắc được mô tả trong đặc tả. Vì cách triển khai khác nhau, khả năng hai bên mắc cùng một lỗi cụ thể giảm đi.

Dù vậy, mô hình tham chiếu cũng là mã và có thể sai. Hãy xác nhận nó bằng ví dụ đã được kiểm chứng, đồng thời giữ một số expected cố định để test không phụ thuộc hoàn toàn vào mô hình đó.

### Kiểm tra thuộc tính và bất biến nghiệp vụ

Không phải lúc nào cũng cần biết chính xác kết quả cho mọi đầu vào. Một số thuật toán phải luôn thỏa mãn thuộc tính được xác định từ nghiệp vụ.

Ví dụ:

- Phí vận chuyển không được âm.
- Số tiền phải trả không được lớn hơn tổng tiền trước giảm giá nếu chính sách chỉ áp dụng giảm giá.
- Kết quả phân trang không được chứa nhiều phần tử hơn kích thước trang đã yêu cầu.
- Một thao tác chuẩn hóa đã hoàn tất thì áp dụng lần nữa không làm thay đổi kết quả.
- Sắp xếp một danh sách đã sắp xếp lần nữa vẫn giữ nguyên thứ tự.

Các thuộc tính này bổ sung cho ví dụ expected cụ thể. Tuy nhiên, một bất biến quá rộng có thể để lọt lỗi. Chẳng hạn, một hàm sắp xếp trả về danh sách đầu vào chưa sắp xếp vẫn có thể giữ nguyên số lượng phần tử và không có phần tử âm. Vì vậy, cần kết hợp bất biến với một số ví dụ có thứ tự kết quả rõ ràng.

### Kiểm thử quan hệ giữa nhiều lần chạy

Với một số bài toán, có thể kiểm tra quan hệ giữa đầu vào và đầu ra thay vì tính toàn bộ expected. Đây là cách tiếp cận thường gọi là kiểm thử quan hệ hoặc metamorphic testing.

Ví dụ, nếu một thuật toán chuẩn hóa chuỗi được đặc tả là idempotent, chuẩn hóa kết quả lần thứ hai phải cho cùng kết quả:

~~~java
@Test
void normalizationIsIdempotent() {
    String once = normalizer.normalize("  Spring   Test  ");
    String twice = normalizer.normalize(once);

    assertEquals(once, twice);
}
~~~

Test này kiểm tra một thuộc tính độc lập với chi tiết triển khai. Nhưng nó chưa chứng minh chuỗi sau chuẩn hóa đúng định dạng mong muốn. Nếu normalizer luôn trả về chuỗi rỗng, thuộc tính idempotent vẫn đúng. Vì vậy, hãy kết hợp với một ví dụ đầu ra đã được xác định:

~~~java
@Test
void normalizesKnownInputToExpectedValue() {
    assertEquals(
            "Spring Test",
            normalizer.normalize("  Spring   Test  ")
    );
}
~~~

Một quan hệ tốt cần xuất phát từ đặc tả nghiệp vụ và có khả năng phát hiện lỗi cụ thể. Không nên chọn thuộc tính chỉ vì nó dễ viết.

## 6. Tách phần chuẩn bị dữ liệu khỏi phép tính expected

Test helper rất hữu ích để làm cho Arrange ngắn gọn. Tuy nhiên, helper nên hỗ trợ tạo dữ liệu, mock phụ thuộc hoặc diễn đạt assertion chung; nó không nên che giấu một bản sao của thuật toán đang kiểm tra.

Ví dụ, helper sau chỉ tạo một Order với các trường đã khai báo:

~~~java
private Order order(String id, BigDecimal subtotal) {
    return new Order(id, subtotal);
}
~~~

Helper này không thực hiện quy tắc tính phí. Nó giúp test tập trung vào hành vi.

Ngược lại, helper sau có thể làm test mất tính độc lập nếu nó sao chép quy tắc tính tổng của production:

~~~java
private BigDecimal expectedTotal(List<OrderLine> lines) {
    return lines.stream()
            .map(line -> line.unitPrice()
                    .multiply(BigDecimal.valueOf(line.quantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);
}
~~~

Nếu chính thuật toán tính tổng đang được kiểm tra, helper này có thể mắc cùng lỗi với production. Hãy dùng các kết quả đã xác định trước hoặc một oracle độc lập.

Một số nguyên tắc khi viết helper:

- Đặt tên theo dữ liệu hoặc ý nghĩa nghiệp vụ, chẳng hạn **anOrderWithTwoLines**.
- Truyền rõ các giá trị quan trọng thay vì tự tính chúng bằng logic production.
- Tránh helper có tên **expected...** nhưng bên trong gọi phương thức đang được kiểm tra.
- Để expected quan trọng xuất hiện rõ trong test hoặc fixture, giúp người đọc dễ xác nhận.
- Nếu helper dùng chung cho nhiều test, giữ nó đơn giản và không đưa điều kiện nghiệp vụ đang kiểm tra vào đó.

## 7. Áp dụng nguyên tắc này trong các cấp kiểm thử Spring

Việc kiểm tra expected độc lập áp dụng ở mọi cấp kiểm thử. Spring cung cấp môi trường để kiểm tra bean, MVC, persistence và các tích hợp; Spring không làm thay đổi nguyên tắc về nguồn của kết quả mong đợi.

### Unit test cho service nghiệp vụ

Với logic thuần Java không cần container, hãy khởi tạo service trực tiếp và kiểm tra bằng dữ liệu có expected cụ thể. Không cần dùng **@SpringBootTest** chỉ để gọi một phương thức tính toán đơn giản.

Nếu service có phụ thuộc, dùng mock để kiểm soát phản hồi từ các phụ thuộc đó. Giá trị trả về kỳ vọng của mock cũng nên là dữ liệu cố định được xác định từ hợp đồng của phụ thuộc.

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository repository;

    @InjectMocks
    private OrderService service;

    @Test
    void marksOrderAsPaidAfterSuccessfulPayment() {
        var order = new Order("order-42", OrderStatus.PENDING);

        when(repository.findById("order-42"))
                .thenReturn(Optional.of(order));

        service.markPaid("order-42");

        assertEquals(OrderStatus.PAID, order.status());
        verify(repository).save(order);
    }
}
~~~

Trong ví dụ này, test xác định trước trạng thái ban đầu và trạng thái mong đợi theo quy tắc nghiệp vụ. Nếu cần kiểm tra việc lưu dữ liệu, có thể xác nhận tương tác với repository. Không nên gọi một hàm production để tính trạng thái mong đợi rồi so sánh với trạng thái service vừa tạo.

### Kiểm thử web với MockMvc

Với **@WebMvcTest**, mục tiêu thường là xác minh hợp đồng HTTP: status, header, cấu trúc JSON, validation và xử lý lỗi.

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsExpectedOrderRepresentation() throws Exception {
        when(orderService.findById("order-42"))
                .thenReturn(new OrderView("order-42", "PAID"));

        mockMvc.perform(get("/orders/order-42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("order-42"))
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

Các giá trị **order-42** và **PAID** là dữ liệu cố định của hợp đồng kiểm thử. Nếu mục tiêu là kiểm tra JSON được serialize đúng, hãy xác định rõ cấu trúc và định dạng mong đợi. Tránh dùng cùng một converter để tạo cả response thực tế và expected, vì lỗi converter có thể bị che khuất.

### Kiểm thử persistence với @DataJpaTest

Với **@DataJpaTest**, expected nên dựa trên dữ liệu đã chuẩn bị và quy tắc truy vấn. Ví dụ, khi kiểm tra repository tìm đơn hàng theo khách hàng, hãy tạo một số bản ghi với mã khách hàng đã biết và xác nhận chính xác tập mã đơn hàng được trả về.

Không nên gọi cùng repository query để tạo expected rồi gọi lại query để lấy actual. Cũng không nên tính expected bằng một biểu thức sao chép điều kiện WHERE nếu chính điều kiện đó là nội dung cần kiểm tra.

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void findsOrdersForTheRequestedCustomer() {
        repository.saveAll(List.of(
                new OrderEntity("order-1", "customer-A"),
                new OrderEntity("order-2", "customer-B"),
                new OrderEntity("order-3", "customer-A")
        ));

        var result = repository.findByCustomerId("customer-A");

        assertEquals(
                Set.of("order-1", "order-3"),
                result.stream().map(OrderEntity::getId).collect(Collectors.toSet())
        );
    }
}
~~~

Expected ở đây là tập mã đơn hàng cụ thể từ dữ liệu test. Test xác minh kết quả truy vấn thực tế của database thay vì lặp lại điều kiện truy vấn trong Java để tạo tập expected.

### Integration test với nhiều bean và hạ tầng

Với **@SpringBootTest**, có thể kiểm tra luồng qua nhiều bean, transaction và database. Dù phạm vi rộng hơn, expected vẫn cần đến từ hợp đồng hoặc dữ liệu chuẩn. Ví dụ, nếu kiểm tra một giao dịch tạo đơn, hãy xác định rõ trạng thái, mã tham chiếu và số tiền cần lưu theo kịch bản đã chuẩn bị.

Không nên đọc lại dữ liệu bằng một hàm tính toán giống service để tạo expected. Có thể dùng repository để quan sát dữ liệu đã lưu, nhưng các giá trị so sánh phải được xác định độc lập từ kịch bản.

## 8. Kết hợp ví dụ cố định, thuộc tính và kiểm thử đột biến

Không có một kiểu assertion nào đủ cho mọi thuật toán. Một bộ test có tín hiệu tốt thường kết hợp:

- **Ví dụ cố định**: xác nhận một đầu vào cụ thể cho kết quả đã biết.
- **Trường hợp biên**: xác nhận hành vi tại ranh giới và với dữ liệu bất thường.
- **Thuộc tính**: xác nhận những bất biến phải luôn đúng.
- **Kiểm thử tích hợp**: xác nhận thuật toán được gọi đúng trong luồng Spring và làm việc với phụ thuộc thật cần thiết.

Một kỹ thuật bổ sung là mutation testing. Công cụ mutation testing thay đổi nhỏ mã sản phẩm, chẳng hạn đổi **>=** thành **>** hoặc thay một giá trị điều kiện, rồi chạy lại test. Nếu thay đổi làm sai hành vi nhưng toàn bộ test vẫn xanh, bộ test có thể chưa đủ nhạy với lỗi đó.

Ví dụ với chính sách miễn phí vận chuyển, nếu thay toán tử **>=** bằng **>**, test có trường hợp đúng bằng ngưỡng phải thất bại. Nếu mutation này vẫn sống sót, hãy xem lại dữ liệu test và expected ở điều kiện biên.

Mutation testing không chứng minh test hoàn hảo. Một mutation có thể không ảnh hưởng đến hành vi quan sát được trong phạm vi test; cũng có thể có nhiều cách viết tương đương. Tuy nhiên, nó là một tín hiệu hữu ích về khả năng phát hiện một số loại lỗi.

Code coverage cũng cần được diễn giải đúng. Dòng mã được chạy không đồng nghĩa kết quả mong đợi độc lập hoặc assertion đủ mạnh. Một test có coverage cao vẫn có thể sao chép thuật toán và để lọt lỗi. Hãy đánh giá test theo hành vi mà nó có thể phát hiện, không chỉ theo số dòng đã chạy.

## 9. Dấu hiệu cho thấy test đang sao chép production

Khi đọc một test, hãy chú ý các dấu hiệu sau:

- Expected được tính bằng cùng công thức hoặc cùng nhánh điều kiện của phương thức đang kiểm tra.
- Test gọi lại chính phương thức production hoặc helper dùng chung để lấy expected.
- Test lấy hằng số private của service làm expected cho chính quy tắc do hằng số đó quyết định.
- Test dùng cùng mapper, formatter hoặc converter để dựng expected và actual.
- Một helper trong test chứa vòng lặp, comparator hoặc quy tắc nghiệp vụ giống production.
- Khi sửa thuật toán, người viết phải sửa cả expected theo cùng một cách mà không có thay đổi nào trong đặc tả.

Khi gặp dấu hiệu này, hãy quay lại câu hỏi: **Nếu implementation mắc lỗi, nguồn expected hiện tại có khả năng mắc cùng lỗi không?** Nếu câu trả lời là có, cần tìm một nguồn kỳ vọng độc lập hơn.

## 10. Cách thiết kế một test có phép kiểm tra độc lập

Một quy trình thực hành có thể gồm các bước sau:

1. **Xác định hành vi công khai**: mô tả đầu vào, đầu ra và các điều kiện được đặc tả.
2. **Chọn ví dụ có khả năng phân biệt**: gồm trường hợp bình thường, biên và lỗi quan trọng.
3. **Xác định expected trước khi xem kết quả chạy**: lấy từ quy tắc nghiệp vụ, ví dụ đã xác nhận hoặc dữ liệu chuẩn.
4. **Viết Arrange đơn giản**: tạo dữ liệu bằng builder hoặc fixture không chứa thuật toán cần kiểm tra.
5. **Gọi đúng hành vi cần kiểm tra**: tránh gọi thêm production helper để dựng expected.
6. **Assert kết quả có ý nghĩa**: kiểm tra giá trị, trạng thái, thứ tự hoặc hợp đồng quan sát được.
7. **Bổ sung thuộc tính hoặc mutation test khi cần**: tăng khả năng phát hiện lỗi mà không biến test thành bản sao của implementation.

Ví dụ, khi kiểm tra quy tắc tính phí, trước tiên ghi rõ bảng chính sách và expected cho các ngưỡng. Sau đó viết test bằng các giá trị cụ thể. Khi kiểm tra query, xác định bản ghi nào phải xuất hiện theo hợp đồng truy vấn. Khi kiểm tra chuyển trạng thái, liệt kê các chuyển đổi được phép và bị từ chối.

## 11. Những gì nên và không nên dùng chung giữa test và production

Không phải mọi chia sẻ mã đều làm mất tính độc lập. Cần phân biệt việc dùng chung hạ tầng với việc dùng chung logic đang được xác minh.

| Có thể dùng chung khi phù hợp | Cần tránh nếu đang kiểm tra chính logic đó |
|---|---|
| Kiểu dữ liệu và model của ứng dụng | Hàm production tính expected |
| Builder tạo entity với giá trị tường minh | Helper builder tự tính trường nghiệp vụ theo cùng thuật toán |
| JUnit, Mockito và Spring TestContext | Cùng mapper hoặc converter để dựng expected cho phép kiểm tra serializer |
| Hằng số kỹ thuật không thuộc quy tắc đang kiểm tra | Hằng số chính sách dùng chung cho cả actual và expected |
| Fixture dữ liệu tĩnh đã được xác nhận | Fixture tự sinh expected bằng service đang kiểm tra |

Một test có thể dùng chung kiểu Order hoặc DTO vì đó là cấu trúc dữ liệu của hợp đồng. Nhưng nếu test đang xác minh cách service tính tổng đơn hàng, không nên gọi phương thức tính tổng của model để tạo expected.

Khi một quy tắc nghiệp vụ được dùng ở nhiều nơi, việc trích xuất nó thành một thành phần production dùng chung có thể là quyết định thiết kế tốt. Tuy nhiên, test của thành phần đó vẫn cần expected độc lập. Việc hai service cùng gọi một hàm dùng chung không tự chứng minh hàm đó đúng.

## 12. Ví dụ về tác động của việc sao chép thuật toán

Giả sử một chính sách quy định phí giao hàng bằng 30.000 đồng nếu giá trị đơn hàng dưới 500.000 đồng, và bằng 0 nếu đạt ngưỡng.

Nếu implementation và test đều dùng điều kiện lớn hơn nghiêm ngặt, trường hợp đúng 500.000 đồng bị tính phí sai nhưng test có thể vẫn xanh. Một test với expected cố định tại đúng ngưỡng sẽ phát hiện lỗi.

Tương tự, nếu cả production và test đều làm tròn xuống thay vì làm tròn theo quy tắc HALF_UP, các ví dụ có kết quả làm tròn không nguyên sẽ giúp phát hiện lỗi chỉ khi expected được tính từ quy tắc độc lập.

Đây là lý do nên chọn dữ liệu có ý nghĩa phân biệt. Một tập test chỉ gồm các giá trị đơn giản có thể không phân biệt được thuật toán đúng với một biến thể sai. Hãy chọn đầu vào mà các cách triển khai khác nhau tạo ra kết quả khác nhau.

## 13. Kết luận về thiết kế phép kiểm tra

Một test tốt phải có một cơ sở độc lập để khẳng định kết quả nào là đúng. Với logic đơn giản, hãy dùng các cặp đầu vào và đầu ra cụ thể được xác định từ đặc tả. Với thuật toán phức tạp, kết hợp dữ liệu chuẩn, mô hình tham chiếu độc lập, thuộc tính nghiệp vụ và kiểm thử quan hệ. Trong các bài test Spring, hãy giữ nguyên nguyên tắc đó dù test đang chạy trực tiếp service, qua MVC slice, repository slice hay toàn bộ ApplicationContext.

Khi đọc một assertion, hãy tự hỏi: nếu mã sản phẩm sai, phép kiểm tra này có thể nhận ra không? Nếu expected được tạo bằng cùng công thức, điều kiện, converter hoặc helper với production, câu trả lời có thể là không. Hãy làm cho nguồn kỳ vọng rõ ràng, độc lập và đủ cụ thể để một lỗi thực sự khiến test thất bại.

