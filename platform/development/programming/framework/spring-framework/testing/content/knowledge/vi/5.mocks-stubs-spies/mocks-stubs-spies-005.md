# Argument matcher và dữ liệu đầu vào chính xác

Khi kiểm thử một service có sử dụng dependency được thay bằng mock, kết quả của lời gọi phụ thuộc vào cách mock nhận diện các đối số. Mockito cho phép khai báo dữ liệu đầu vào chính xác bằng giá trị cụ thể, hoặc dùng *argument matcher* để mô tả điều kiện mà đối số phải thỏa mãn.

Chọn đúng cách so khớp giúp test thể hiện rõ hợp đồng giữa các thành phần: service đã gọi dependency với mã khách hàng nào, số tiền nào, trạng thái nào hoặc một đối tượng có những thuộc tính gì. Nếu matcher quá rộng, test có thể PASS dù service truyền sai dữ liệu. Nếu matcher quá chặt, test có thể thất bại vì một chi tiết không thuộc hành vi cần bảo vệ.

## 1. Mockito so khớp đối số như thế nào?

Khi stub một mock, Mockito cần biết lời gọi nào sẽ nhận kết quả đã cấu hình. Khi verify, Mockito cần biết lời gọi nào được xem là đã xảy ra.

Nếu truyền giá trị thông thường, Mockito so khớp đối số bằng cơ chế so sánh equality, về cơ bản dựa trên `equals()` của đối tượng:

```java
when(customerRepository.findByEmail("lan@example.test"))
        .thenReturn(Optional.of(customer));

verify(customerRepository).findByEmail("lan@example.test");
```

Trong ví dụ này, stub chỉ áp dụng khi service gọi `findByEmail` với chuỗi có giá trị bằng `"lan@example.test"`. Lệnh verify cũng xác nhận một lời gọi với giá trị tương đương đã diễn ra.

Điều này phù hợp khi giá trị đầu vào là một phần quan trọng của hành vi cần kiểm tra. Người đọc nhìn thấy ngay mã email được kỳ vọng.

Với đối tượng tự định nghĩa, `equals()` và `hashCode()` quyết định equality. Nếu lớp không triển khai `equals()`, so sánh mặc định của `Object` thường là so sánh identity. Vì vậy, hai đối tượng có cùng thuộc tính chưa chắc được xem là bằng nhau. Cần hiểu cách lớp miền định nghĩa equality trước khi dựa vào nó trong stub hoặc verify.

## 2. Khi nào cần argument matcher?

Argument matcher mô tả điều kiện để một đối số được chấp nhận. Thay vì yêu cầu giá trị phải bằng một đối tượng cụ thể, test có thể diễn đạt:

- Đối số là bất kỳ chuỗi nào.
- Đối số khác `null`.
- Đối số bằng một giá trị xác định.
- Đối số là chính instance đã chuẩn bị.
- Đối tượng có một thuộc tính hoặc tổ hợp thuộc tính thỏa mãn điều kiện.
- Đối số thỏa mãn một quy tắc do test định nghĩa.

Ví dụ, service có thể tạo một đối tượng tìm kiếm mới mỗi lần gọi repository. Test chỉ quan tâm bộ lọc có chứa trạng thái `ACTIVE` và trang đầu tiên:

```java
when(customerRepository.search(argThat(criteria ->
        criteria != null
                && criteria.status() == CustomerStatus.ACTIVE
                && criteria.page() == 0
))).thenReturn(List.of(customer));
```

Matcher này cho phép đối tượng `criteria` là instance mới, miễn là các thuộc tính quan trọng đúng. Đây là cách kiểm tra dữ liệu đầu vào theo ý nghĩa thay vì phụ thuộc vào việc service có dùng lại cùng một object hay không.

Không nên dùng matcher chỉ để làm test ngắn hơn. Hãy chọn matcher khi nó diễn đạt được một điều kiện có ý nghĩa mà giá trị cụ thể không thể hiện rõ hoặc khó tạo trước.

## 3. Các matcher thường dùng

Mockito cung cấp các matcher trong `ArgumentMatchers`. Thông thường, test dùng static import để code gọn hơn.

| Matcher | Điều kiện |
|---|---|
| `any()` | Chấp nhận mọi giá trị, kể cả `null` |
| `any(Class)` | Chấp nhận đối tượng thuộc kiểu chỉ định; không khớp `null` |
| `anyString()`, `anyInt()`, `anyLong()` | Chấp nhận giá trị thuộc kiểu tương ứng; matcher kiểu cụ thể không chấp nhận `null` |
| `eq(value)` | Đối số bằng giá trị chỉ định theo equality |
| `same(value)` | Đối số phải chính là cùng một object instance |
| `isNull()` | Đối số phải là `null` |
| `notNull()` | Đối số không được là `null` |
| `nullable(Class)` | Chấp nhận `null` hoặc đối tượng thuộc kiểu chỉ định |
| `argThat(matcher)` | Điều kiện tùy chỉnh |
| `aryEq(array)` | So sánh nội dung mảng theo matcher dành cho mảng |

### any() và any(Class)

`any()` hữu ích khi giá trị của đối số không thuộc phạm vi cần kiểm tra:

```java
when(notificationClient.send(any()))
        .thenReturn(SendResult.accepted());
```

Stub này áp dụng cho mọi giá trị đối số, kể cả `null`. Vì matcher rộng như vậy, nó không thể chứng minh service đã gửi đúng nội dung thông báo.

Khi cần giới hạn theo kiểu:

```java
when(notificationClient.send(any(Notification.class)))
        .thenReturn(SendResult.accepted());
```

`any(Notification.class)` chỉ khớp một đối tượng thuộc kiểu `Notification` và không khớp `null`. Nếu `null` cũng được chấp nhận, có thể dùng `nullable(Notification.class)` hoặc `isNull()` tùy ý nghĩa test.

Các matcher kiểu như `anyString()`, `anyInt()`, `anyLong()` cũng có quy tắc kiểu cụ thể. Chúng không có nghĩa là chấp nhận cả `null` trong trường hợp kiểu tham chiếu.

### eq(value): vẫn kiểm tra một giá trị chính xác

`eq(value)` thường được dùng khi một lời gọi có nhiều đối số và cần kết hợp một giá trị chính xác với matcher khác:

```java
verify(paymentGateway).charge(
        eq("ORDER-42"),
        any(BigDecimal.class)
);
```

Ở đây mã đơn hàng phải bằng `"ORDER-42"`, còn số tiền chỉ cần là một đối tượng `BigDecimal`. Nếu số tiền cũng là điều cần bảo vệ, hãy dùng `eq(expectedAmount)` thay cho matcher rộng.

### same(value): kiểm tra cùng object instance

`same(value)` kiểm tra identity: đối số truyền vào phải là đúng instance đã cung cấp.

```java
Notification notification = new Notification("ORDER-42");

notificationClient.send(notification);

verify(notificationClient).send(same(notification));
```

Matcher này phù hợp khi identity có ý nghĩa, ví dụ một object mutable phải được chuyển tiếp nguyên vẹn qua một ranh giới. Nếu chỉ cần nội dung bằng nhau, dùng `eq(notification)` hoặc một matcher kiểm tra thuộc tính sẽ thể hiện đúng mục tiêu hơn.

### isNull(), notNull() và nullable()

Các matcher này diễn đạt rõ quy tắc null:

```java
verify(customerRepository).findByEmail(isNull());
verify(auditClient).publish(notNull());
verify(profileClient).update(nullable(Profile.class));
```

Dùng matcher null cụ thể giúp người đọc thấy null là điều kiện được kiểm tra có chủ đích. Không nên dùng `any()` nếu test thực sự cần chứng minh đối số không null.

## 4. Quy tắc quan trọng: đã dùng matcher thì mọi đối số phải dùng matcher

Khi một lời gọi có nhiều tham số, nếu đã sử dụng matcher cho một tham số thì các tham số còn lại cũng phải được biểu diễn bằng matcher. Không trộn matcher với giá trị literal trực tiếp trong cùng lời gọi stub hoặc verify.

Ví dụ sai:

```java
verify(orderRepository).find("ORDER-42", anyBoolean());
```

Lời gọi trên trộn chuỗi literal với matcher `anyBoolean()`. Mockito sẽ báo lỗi sử dụng matcher không hợp lệ.

Cách đúng:

```java
verify(orderRepository).find(eq("ORDER-42"), anyBoolean());
```

Tương tự khi stub:

```java
when(reportClient.export(
        eq("CSV"),
        any(ExportOptions.class)
)).thenReturn(report);
```

Nếu mọi tham số đều là giá trị chính xác, có thể truyền trực tiếp mà không dùng matcher:

```java
when(orderRepository.find("ORDER-42", true))
        .thenReturn(Optional.of(order));
```

Không cần bọc mọi literal trong `eq()`. Chỉ cần dùng matcher khi có lý do phải kết hợp điều kiện chính xác với điều kiện khác hoặc muốn diễn đạt quy tắc riêng.

## 5. Dùng matcher với kiểu nguyên thủy

Các kiểu nguyên thủy như `int`, `long`, `boolean` có matcher tương ứng:

- `anyInt()`
- `anyLong()`
- `anyBoolean()`
- `anyDouble()`
- `anyFloat()`
- `anyShort()`
- `anyByte()`
- `charThat(...)`, `intThat(...)`, `longThat(...)` cho điều kiện tùy chỉnh theo kiểu

Ví dụ:

```java
verify(rateLimiter).consume(eq("CUSTOMER-42"), anyInt());
```

Với phương thức nhận primitive, hãy dùng matcher đúng kiểu. Không nên dùng `argThat(...)` trả về một giá trị tham chiếu rồi để Java tự unbox sang primitive; matcher có thể trả về giá trị giả `null`, dẫn đến `NullPointerException` trước khi Mockito hoàn tất việc ghi nhận matcher.

Nếu cần điều kiện tùy chỉnh cho `int`, dùng `intThat`:

```java
verify(rateLimiter).consume(
        eq("CUSTOMER-42"),
        intThat(value -> value > 0 && value <= 10)
);
```

Điều kiện trên xác nhận số lượng tiêu thụ nằm trong khoảng từ 1 đến 10. Nó thể hiện rõ hợp đồng đầu vào thay vì chỉ chấp nhận bất kỳ số nguyên nào.

## 6. Viết điều kiện tùy chỉnh bằng argThat

`argThat` nhận một `ArgumentMatcher` hoặc biểu thức lambda để kiểm tra đối số. Đây là cách phù hợp khi cần xác nhận một phần cấu trúc hoặc quy tắc nghiệp vụ của object.

Ví dụ, service gửi lệnh tạo đơn hàng đến repository. Test muốn kiểm tra khách hàng và số dòng hàng, nhưng không quan tâm thời điểm tạo:

```java
verify(orderRepository).save(argThat(command ->
        command != null
                && command.customerId().equals("CUSTOMER-42")
                && command.lines().size() == 2
));
```

Matcher tập trung vào các thuộc tính quyết định. Nếu thời điểm tạo được sinh từ clock hoặc timestamp hiện tại, test không phải phụ thuộc vào giá trị đó.

### Đặt tên điều kiện phức tạp

Nếu lambda dài, hãy trích xuất thành biến hoặc phương thức có tên mô tả:

```java
ArgumentMatcher<CreateOrderCommand> validCommandForCustomer =
        command -> command != null
                && command.customerId().equals("CUSTOMER-42")
                && command.lines().size() == 2;

verify(orderRepository).save(argThat(validCommandForCustomer));
```

Hoặc:

```java
private boolean isExpectedCommand(CreateOrderCommand command) {
    return command != null
            && command.customerId().equals("CUSTOMER-42")
            && command.lines().size() == 2;
}
```

Khi matcher có nhiều điều kiện, tên nên mô tả ý nghĩa của toàn bộ điều kiện. Tránh viết một lambda dài nhiều dòng với các giá trị rải rác không có tên.

### Tránh NullPointerException trong matcher

Đối số được kiểm tra có thể là `null`, nên matcher tùy chỉnh cần xử lý null nếu null không phải điều kiện mong muốn:

```java
argThat(command ->
        command != null
                && "CUSTOMER-42".equals(command.customerId())
);
```

Dùng hằng số hoặc literal ở phía trái của `equals` giúp tránh gọi phương thức trên một giá trị null. Nếu null là điều kiện cần kiểm tra, hãy dùng `isNull()` để diễn đạt rõ ràng.

## 7. Exact value, equality và identity

Ba cách kiểm tra sau có ý nghĩa khác nhau:

| Cách kiểm tra | Điều được xác nhận | Khi nên dùng |
|---|---|---|
| Giá trị literal hoặc `eq(value)` | Đối số bằng expected theo equality | Giá trị hoặc nội dung là hợp đồng |
| `same(value)` | Đối số là đúng instance expected | Identity của object quan trọng |
| `argThat(...)` | Đối số thỏa điều kiện tùy chỉnh | Chỉ một phần thuộc tính hoặc quy tắc quan trọng |

Ví dụ với một đối tượng địa chỉ:

```java
Address expected = new Address("12 Nguyen Hue", "HCMC");

verify(customerRepository).updateAddress(eq(expected));
```

Cách này chỉ hoạt động như so sánh theo nội dung nếu `Address.equals()` được triển khai phù hợp. Nếu lớp không override `equals()`, hai object riêng biệt có cùng dữ liệu có thể không được xem là bằng nhau.

Nếu mục tiêu là xác nhận service truyền đúng instance:

```java
verify(customerRepository).updateAddress(same(expected));
```

Nếu mục tiêu chỉ là xác nhận thành phố:

```java
verify(customerRepository).updateAddress(argThat(address ->
        address != null && "HCMC".equals(address.getCity())
));
```

Hãy chọn theo hợp đồng của thành phần. Không nên kiểm tra identity khi ứng dụng chỉ yêu cầu nội dung tương đương; cũng không nên chỉ kiểm tra một thuộc tính khi toàn bộ giá trị là dữ liệu quan trọng cần bảo vệ.

## 8. Dùng ArgumentCaptor khi cần xem lại đối số

Matcher trả lời câu hỏi “đối số có thỏa điều kiện không?”. Khi cần giữ lại đối số thực tế để kiểm tra nhiều thuộc tính sau lời gọi, dùng `ArgumentCaptor`.

Ví dụ:

```java
@Captor
ArgumentCaptor<CreateOrderCommand> commandCaptor;

@Test
void sendsExpectedCommandToRepository() {
    orderService.createOrder("CUSTOMER-42");

    verify(orderRepository).save(commandCaptor.capture());

    CreateOrderCommand actual = commandCaptor.getValue();

    assertEquals("CUSTOMER-42", actual.customerId());
    assertEquals(1, actual.lines().size());
}
```

Captor lấy đối tượng được truyền vào lời gọi đã verify. Sau đó test có thể dùng assertion thông thường để kiểm tra các trường.

Phân biệt hai công cụ:

- **Argument matcher** xác định lời gọi nào được khớp trong stub hoặc verify.
- **ArgumentCaptor** ghi lại đối số thực tế để test kiểm tra sau khi lời gọi xảy ra.

Với một điều kiện đơn giản, `argThat` thường ngắn gọn. Khi cần kiểm tra nhiều thuộc tính hoặc dùng lại đối tượng thực tế trong nhiều assertion, captor có thể rõ ràng hơn.

Không nên dùng captor chỉ để xác nhận một giá trị đơn giản nếu `eq(expected)` đã diễn đạt đầy đủ. Captor thêm bước capture và biến trung gian, nên chỉ dùng khi việc giữ lại đối số mang lại lợi ích.

## 9. Kiểm tra dữ liệu đầu vào chính xác trong stub và verify

Giả sử service tạo yêu cầu thanh toán từ mã đơn hàng và tổng tiền:

```java
class CheckoutService {

    private final PaymentGateway paymentGateway;

    CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    PaymentResult checkout(Order order) {
        PaymentRequest request = new PaymentRequest(
                order.getId(),
                order.getTotal()
        );

        return paymentGateway.charge(request);
    }
}
```

Test có thể xác nhận gateway nhận đúng request:

```java
@Test
void sendsExpectedPaymentRequest() {
    Order order = new Order(
            "ORDER-42",
            new BigDecimal("120000")
    );

    when(paymentGateway.charge(any(PaymentRequest.class)))
            .thenReturn(PaymentResult.approved());

    checkoutService.checkout(order);

    verify(paymentGateway).charge(argThat(request ->
            request != null
                    && "ORDER-42".equals(request.orderId())
                    && new BigDecimal("120000").equals(request.amount())
    ));
}
```

Stub dùng `any(PaymentRequest.class)` vì test cần gateway trả về kết quả được kiểm soát để service hoàn thành. Verify dùng matcher cụ thể hơn để xác nhận request được gửi đi có mã đơn hàng và số tiền đúng.

Điểm đáng chú ý: matcher rộng trong stub không thay thế assertion về dữ liệu đầu vào. Nếu chỉ stub và không verify hoặc capture đối số, test có thể không phát hiện service tạo sai request.

Nếu `PaymentRequest` là record hoặc lớp có `equals()` đúng theo các trường cần kiểm tra, có thể tạo expected object và dùng `eq(expectedRequest)`. Khi đó code ngắn hơn:

```java
PaymentRequest expected = new PaymentRequest(
        "ORDER-42",
        new BigDecimal("120000")
);

verify(paymentGateway).charge(eq(expected));
```

Cách dùng equality chỉ đáng tin khi semantics của `equals()` khớp với điều test muốn xác nhận.

## 10. Matcher trong stub có thể quá rộng

Một stub dùng `any()` thường tiện:

```java
when(customerRepository.findByEmail(anyString()))
        .thenReturn(Optional.of(customer));
```

Nhưng nếu service phải tìm đúng email của khách hàng hiện tại, matcher rộng không chứng minh điều đó. Service có thể gọi nhầm `"other@example.test"` mà stub vẫn trả về cùng customer.

Để kiểm tra hợp đồng đầu vào, có thể stub theo giá trị cụ thể:

```java
when(customerRepository.findByEmail("lan@example.test"))
        .thenReturn(Optional.of(customer));
```

Hoặc verify rõ lời gọi:

```java
verify(customerRepository).findByEmail(eq("lan@example.test"));
```

Cách chọn phụ thuộc mục tiêu:

- Dùng matcher rộng khi đối số không liên quan đến hành vi cần kiểm tra.
- Dùng giá trị cụ thể khi đầu vào chính xác là một phần của hợp đồng.
- Dùng matcher tùy chỉnh khi chỉ một tập thuộc tính hoặc điều kiện cần được xác nhận.

Không cần verify mọi lời gọi của mọi mock. Chỉ xác nhận tương tác khi nó có ý nghĩa đối với hành vi. Nếu test chỉ quan tâm kết quả công khai của service, assertion trên kết quả có thể đủ; verify chi tiết nội bộ quá mức làm test dễ vỡ khi triển khai thay đổi mà hành vi không đổi.

## 11. Các matcher chỉ được dùng trong ngữ cảnh Mockito

Các phương thức như `any()`, `eq()`, `argThat()` không tạo ra đối tượng expected thông thường. Chúng đăng ký matcher trong cơ chế nội bộ của Mockito và trả về một giá trị giả để phù hợp với chữ ký Java.

Do đó, không nên lưu kết quả matcher vào biến rồi dùng như dữ liệu thực:

```java
// Không dùng theo cách này
String email = anyString();
```

Cũng không dùng matcher ngoài lời gọi stubbing hoặc verification:

```java
// Không phải cách chuẩn bị dữ liệu test
Customer customer = new Customer(anyString());
```

Hãy tạo dữ liệu fixture bằng giá trị thực:

```java
String email = "lan@example.test";
Customer customer = new Customer(email);
```

Sau đó dùng matcher tại vị trí Mockito cần so khớp:

```java
verify(customerRepository).findByEmail(eq(email));
```

Tách biệt dữ liệu thực và matcher giúp code dễ hiểu: fixture tạo đối tượng có giá trị cụ thể; matcher mô tả cách Mockito nhận diện lời gọi.

## 12. Các trường hợp đặc biệt: collection, array và varargs

Các collection Java thường triển khai `equals()` theo nội dung và thứ tự phần tử. Vì vậy, có thể dùng một collection expected để so sánh:

```java
List<String> expectedRoles = List.of("ADMIN", "EDITOR");

verify(roleRepository).saveAll(eq(expectedRoles));
```

Nếu thứ tự không thuộc hợp đồng, equality của `List` có thể quá chặt. Khi đó, dùng matcher tùy chỉnh để kiểm tra membership hoặc chuyển dữ liệu sang cấu trúc phù hợp với quy tắc nghiệp vụ.

Mảng Java có hành vi equality khác collection: `equals()` mặc định của mảng không so sánh nội dung phần tử theo cách mong đợi. Mockito cung cấp matcher `aryEq(expectedArray)` để so sánh nội dung:

```java
verify(binaryClient).send(aryEq(new byte[] { 1, 2, 3 }));
```

Với phương thức nhận varargs, cần chú ý kiểu tham số thực tế và phiên bản Mockito đang sử dụng. Nếu muốn xác nhận toàn bộ mảng varargs, hãy dùng matcher phù hợp với kiểu mảng; nếu muốn kiểm tra từng phần tử, có thể capture hoặc viết matcher cho dữ liệu đã gom. Không nên giả định `any()` luôn thể hiện cùng một ý nghĩa cho một phần tử vararg và toàn bộ mảng varargs.

## 13. Những lỗi thường gặp khi sử dụng matcher

| Lỗi | Vì sao có vấn đề | Cách xử lý |
|---|---|---|
| Trộn literal với matcher trong cùng lời gọi | Mockito không thể diễn giải nhất quán các đối số | Bọc literal bằng `eq()` |
| Dùng `any()` khi cần giá trị chính xác | Stub hoặc verify quá rộng | Dùng literal, `eq()` hoặc `argThat()` |
| Nhầm `any(Class)` chấp nhận null | Stub không khớp khi đối số null | Dùng `isNull()` hoặc `nullable(Class)` |
| Dùng matcher tham chiếu cho primitive | Có thể gặp unboxing `null` | Dùng `anyInt()`, `intThat()` và matcher primitive tương ứng |
| Dùng `same()` trong khi chỉ cần equality | Test phụ thuộc identity không cần thiết | Dùng `eq()` hoặc matcher theo thuộc tính |
| Dùng `argThat` dài và khó hiểu | Điều kiện bị ẩn trong lambda phức tạp | Trích xuất matcher có tên mô tả |
| Gọi phương thức trên đối số null trong matcher | Matcher ném `NullPointerException` | Kiểm tra null trước hoặc dùng matcher null rõ ràng |
| Dùng matcher như dữ liệu fixture | Giá trị trả về của matcher chỉ là giá trị giả | Tạo dữ liệu thực bằng constructor hoặc factory |
| Stub quá rộng rồi bỏ qua verify | Không phát hiện service truyền sai đối số | Xác nhận input quan trọng bằng verify/captor |

Một lỗi khác là verify quá chi tiết những tương tác không phải hợp đồng của thành phần. Ví dụ, nếu test chỉ cần chứng minh khách hàng nhận được kết quả đúng, việc kiểm tra từng lời gọi nội bộ có thể làm test gắn chặt với cấu trúc hiện tại của service. Hãy ưu tiên kiểm tra đầu vào chính xác tại ranh giới mà dữ liệu đó có ý nghĩa.

## 14. Cách chọn matcher theo mục tiêu

Có thể bắt đầu bằng cách xác định mức độ chính xác cần thiết:

1. **Giá trị đầu vào là hợp đồng cần bảo vệ:** truyền literal hoặc dùng `eq(expected)`.
2. **Chỉ cần xác nhận kiểu và không quan tâm nội dung:** dùng `any(Type.class)`.
3. **Chỉ cần xác nhận không null:** dùng `notNull()`.
4. **Null là một giá trị được mong đợi:** dùng `isNull()` hoặc `nullable(Type.class)` tùy trường hợp.
5. **Cần cùng object instance:** dùng `same(expected)`.
6. **Cần kiểm tra quy tắc trên một phần dữ liệu:** dùng `argThat()` hoặc matcher primitive tương ứng.
7. **Cần xem và kiểm tra nhiều thuộc tính của đối số thực tế:** dùng `ArgumentCaptor`.

Một test rõ nghĩa thường dùng ít matcher nhất có thể mà vẫn diễn đạt đúng điều kiện. Giá trị cụ thể làm rõ expected; matcher tổng quát chỉ nên xuất hiện ở những vị trí mà chi tiết đầu vào không quan trọng.

## 15. Liên hệ với Mock, Stub và Spy

Argument matcher được sử dụng trong các thao tác stubbing và verification với mock. Khi dùng stub, matcher xác định lời gọi nào sẽ nhận giá trị trả về hoặc hành vi đã cấu hình. Khi verify, matcher xác định lời gọi nào được chấp nhận là đã xảy ra.

Với spy, Mockito bọc một object thật và có thể quan sát hoặc thay thế hành vi của một số phương thức. Matcher vẫn có thể dùng trong `verify(spy)` để kiểm tra đối số của lời gọi. Tuy nhiên, stubbing trên spy cần chú ý vì cách viết `when(spy.method(...))` có thể gọi phương thức thật ngay trong lúc cấu hình. Với phương thức có tác dụng phụ, `doReturn(...).when(spy).method(...)` thường an toàn hơn.

Ví dụ kiểm tra spy nhận đúng dữ liệu:

```java
List<String> values = spy(new ArrayList<>());

values.add("spring");

verify(values).add(eq("spring"));
```

Matcher xác nhận đối số của lời gọi `add` bằng chuỗi `"spring"`. Đây là kiểm tra tương tác của spy; dữ liệu danh sách vẫn được xử lý bởi object thật.

Khi làm việc với mock, stub và spy, hãy giữ rõ mục tiêu: stub kiểm soát kết quả phụ thuộc, verify xác nhận tương tác có ý nghĩa, còn matcher mô tả điều kiện so khớp đối số. Chọn đúng mức độ chính xác giúp test phát hiện dữ liệu sai mà không bị phụ thuộc vào những chi tiết triển khai không cần thiết.

