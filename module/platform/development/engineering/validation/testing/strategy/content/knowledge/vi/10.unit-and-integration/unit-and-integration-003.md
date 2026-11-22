# Lựa chọn kiểm chứng trạng thái hoặc tương tác theo rủi ro

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), một ca kiểm thử đơn vị hoặc tích hợp cần chứng minh hành vi có ý nghĩa của hệ thống. Có hai cách tiếp cận thường gặp: **kiểm chứng trạng thái (state verification)** và **kiểm chứng tương tác (interaction verification)**. Cách thứ nhất quan sát kết quả hoặc trạng thái sau khi thực thi; cách thứ hai xác minh thành phần đã giao tiếp với phụ thuộc theo cách được yêu cầu.

Không có cách nào luôn đúng cho mọi trường hợp. Nếu mục tiêu là tính đúng đắn của kết quả, kiểm chứng trạng thái thường tạo bằng chứng trực tiếp và ít phụ thuộc vào cấu trúc nội bộ. Nếu mục tiêu là một tương tác có ý nghĩa độc lập, chẳng hạn gửi thông điệp đúng một lần, gọi cổng thanh toán với khóa idempotency hoặc không gọi dịch vụ khi dữ liệu đầu vào không hợp lệ, kiểm chứng tương tác có thể phù hợp hơn.

Bài học này giải thích hai cách tiếp cận, cách chọn theo rủi ro, cách sử dụng mock và test double, cùng ví dụ thực tế để thiết kế bộ kiểm thử rõ ràng và ổn định.

## 1. Kiểm chứng trạng thái và kiểm chứng tương tác là gì?

### 1.1. Kiểm chứng trạng thái

Kiểm chứng trạng thái tập trung vào điều có thể quan sát sau khi hành động được thực hiện. Ca kiểm thử thiết lập trạng thái ban đầu, gọi hành vi cần kiểm tra và xác nhận trạng thái kết quả.

Trạng thái được quan sát có thể là:

- Giá trị trả về từ một hàm hoặc API.
- Thuộc tính của đối tượng sau khi xử lý.
- Bản ghi được lưu trong cơ sở dữ liệu.
- Trạng thái nghiệp vụ như đơn hàng chuyển từ PENDING sang PAID.
- Sự kiện hoặc thông điệp xuất hiện trong một hàng đợi kiểm thử.
- Nội dung hiển thị hoặc kết quả mà người dùng có thể quan sát.

Ví dụ, khi kiểm tra chức năng áp dụng mã giảm giá, mục tiêu là xác nhận tổng tiền mới bằng giá trị mong đợi và trạng thái mã giảm giá được cập nhật đúng. Ca kiểm thử không nhất thiết phải biết dịch vụ nội bộ gọi các lớp nào để tính kết quả.

### 1.2. Kiểm chứng tương tác

Kiểm chứng tương tác tập trung vào cách một thành phần phối hợp với các phụ thuộc của nó. Ca kiểm thử xác minh một lời gọi đã xảy ra, không xảy ra, xảy ra đúng số lần, với tham số phù hợp hoặc theo thứ tự được yêu cầu.

Các đặc điểm có thể kiểm tra gồm:

- Một phương thức phụ thuộc đã được gọi với đối số đúng.
- Một thao tác chỉ được thực hiện một lần dù yêu cầu bị gửi lặp.
- Một thông điệp được phát sau khi giao dịch thành công.
- Một dịch vụ thanh toán không được gọi khi dữ liệu đầu vào không hợp lệ.
- Một hành động hoàn tác được gọi khi bước xử lý tiếp theo thất bại.
- Các bước giao tiếp diễn ra theo thứ tự bắt buộc.

Ví dụ, khi người dùng thanh toán đơn hàng, nhóm có thể cần xác minh payment gateway nhận đúng số tiền, đơn vị tiền tệ và khóa idempotency. Những tham số này là một phần của hợp đồng giao tiếp; chỉ kiểm tra trạng thái đơn hàng cuối cùng có thể chưa chứng minh chúng được gửi đúng.

### 1.3. So sánh hai cách tiếp cận

| Khía cạnh | Kiểm chứng trạng thái | Kiểm chứng tương tác |
|---|---|---|
| Câu hỏi chính | Sau hành động, kết quả hoặc trạng thái có đúng không? | Thành phần đã phối hợp với phụ thuộc theo yêu cầu chưa? |
| Bằng chứng | Giá trị trả về, đối tượng, bản ghi, trạng thái nghiệp vụ hoặc đầu ra quan sát được. | Lời gọi, đối số, số lần gọi, thứ tự hoặc việc không gọi. |
| Phù hợp khi | Kết quả là điều quan trọng nhất và có thể quan sát trực tiếp. | Hành vi giao tiếp hoặc tác dụng phụ là một phần của yêu cầu. |
| Điểm mạnh | Thường ít phụ thuộc cấu trúc nội bộ và dễ phản ánh hành vi bên ngoài. | Kiểm tra rõ hợp đồng giữa thành phần và phụ thuộc. |
| Rủi ro | Có thể bỏ sót việc phối hợp sai nếu trạng thái cuối tình cờ vẫn đúng. | Có thể gắn chặt test với cách triển khai và thất bại khi refactor dù hành vi vẫn đúng. |
| Ví dụ | Đơn hàng được lưu ở trạng thái PAID. | Payment gateway được gọi đúng một lần với số tiền và idempotency key chính xác. |

Hai cách tiếp cận có thể được kết hợp trong cùng một ca kiểm thử nếu mỗi assertion trả lời một câu hỏi có ý nghĩa riêng. Không nên thêm assertion tương tác chỉ để kiểm tra mọi lời gọi nội bộ.

## 2. Chọn cách kiểm chứng theo mục tiêu và rủi ro

Quyết định nên bắt đầu từ điều cần bảo đảm và hậu quả nếu hành vi sai. Đừng bắt đầu bằng câu hỏi “nên dùng mock hay không?”; trước hết hãy xác định điều gì cần được chứng minh.

### 2.1. Khi nên ưu tiên kiểm chứng trạng thái

Kiểm chứng trạng thái thường là lựa chọn tốt khi:

- Kết quả nghiệp vụ có thể quan sát trực tiếp.
- Có thể xác nhận kết quả qua giá trị trả về hoặc dữ liệu đã lưu.
- Cấu trúc nội bộ có thể thay đổi mà không làm thay đổi hợp đồng bên ngoài.
- Mục tiêu là xác minh phép tính, quy tắc, chuyển trạng thái hoặc tính nhất quán dữ liệu.
- Không có yêu cầu quan trọng nào về số lần gọi hoặc thứ tự giao tiếp.

Ví dụ, với hàm tính phí vận chuyển, nhóm cần xác nhận phí trả về theo trọng lượng, khu vực và phương thức giao hàng. Kiểm tra rằng một service cụ thể được gọi ba lần sẽ không chứng minh công thức đúng và có thể khiến test phụ thuộc vào cách tổ chức mã.

### 2.2. Khi nên ưu tiên kiểm chứng tương tác

Kiểm chứng tương tác có giá trị khi bản thân việc giao tiếp là một phần của hành vi được yêu cầu:

- Gửi thông báo hoặc sự kiện sau khi một giao dịch được xác nhận.
- Không gửi yêu cầu thanh toán nếu kiểm tra dữ liệu thất bại.
- Gọi một dịch vụ đúng một lần để tránh giao dịch trùng.
- Truyền đúng định danh, quyền, số tiền hoặc khóa idempotency cho phụ thuộc.
- Thực hiện thao tác bù trừ khi một bước trong quy trình phân tán thất bại.
- Tuân thủ thứ tự bắt buộc giữa các thao tác có tác dụng phụ.
- Không truy cập phụ thuộc nhạy cảm trong trường hợp bị từ chối quyền.

Ví dụ, một dịch vụ gửi email có thể trả về trạng thái thành công ngay cả khi nó gửi nhầm người nhận. Kiểm chứng tương tác giúp xác nhận địa chỉ người nhận và nội dung được truyền chính xác đến cổng gửi email.

### 2.3. Dùng mức rủi ro để quyết định độ sâu

Có thể đánh giá một mục tiêu theo các câu hỏi:

1. Nếu sai, hậu quả với người dùng, dữ liệu hoặc hoạt động kinh doanh nghiêm trọng đến đâu?
2. Có thể quan sát trực tiếp kết quả cuối cùng không?
3. Tương tác với phụ thuộc có phải một phần của hợp đồng hay ràng buộc nghiệp vụ không?
4. Có nguy cơ lỗi do gọi thiếu, gọi thừa, sai tham số hoặc sai thứ tự không?
5. Có thể kiểm tra tương tác bằng môi trường tích hợp thật hay cần test double?
6. Assertion có ổn định qua các thay đổi triển khai hợp lý không?

Một quy tắc ít rủi ro, có đầu ra rõ ràng thường chỉ cần kiểm chứng trạng thái. Một thao tác thanh toán, ghi dữ liệu hoặc phát sự kiện có hậu quả cao có thể cần kiểm chứng trạng thái cùng một số tương tác quan trọng.

Không cần nhân đôi mọi kiểm tra khi mức rủi ro tăng. Hãy bổ sung đúng bằng chứng còn thiếu: chẳng hạn kiểm tra trạng thái dữ liệu và xác minh một lần gọi đến nhà cung cấp với tham số có ý nghĩa.

## 3. Kiểm chứng trạng thái trong unit test và integration test

### 3.1. Unit test: xác minh kết quả của quy tắc cục bộ

Unit test thường phù hợp để kiểm tra:

- Giá trị trả về của phép tính.
- Trạng thái đối tượng sau khi gọi phương thức.
- Quy tắc xác thực dữ liệu.
- Chuyển trạng thái theo điều kiện.
- Kết quả xử lý trường hợp biên hoặc lỗi.

Ví dụ sau kiểm tra trạng thái của đơn hàng sau khi áp dụng giảm giá:

~~~java
@Test
void appliesValidDiscountToOrderTotal() {
    Order order = new Order("ORD-101", 100_000);
    Discount discount = new Discount("SAVE10", 10);

    order.apply(discount);

    assertEquals(90_000, order.getTotal());
    assertEquals("SAVE10", order.getAppliedDiscountCode());
}
~~~

Mục tiêu của ca kiểm thử là xác minh tổng tiền và mã giảm giá được áp dụng đúng. Test không cần biết đối tượng Order gọi helper nội bộ nào.

### 3.2. Integration test: xác minh trạng thái được duy trì qua ranh giới

Khi một thao tác tương tác với cơ sở dữ liệu hoặc thành phần thật, integration test có thể kiểm tra trạng thái sau khi giao dịch hoàn tất.

Ví dụ, khi tạo đơn hàng, nhóm có thể xác minh:

- Bản ghi đơn hàng được lưu với đúng tổng tiền.
- Các dòng đơn hàng liên kết đúng với đơn.
- Trạng thái giao dịch được lưu nhất quán.
- Transaction rollback khi một thao tác bắt buộc thất bại.
- Dữ liệu có thể được đọc lại qua repository hoặc API.

Một test chỉ kiểm tra phương thức repository trả về một đối tượng đã mock không chứng minh câu lệnh SQL, mapping hoặc ràng buộc cơ sở dữ liệu hoạt động đúng. Nếu rủi ro nằm ở persistence, hãy dùng cơ sở dữ liệu thử nghiệm hoặc môi trường tích hợp phù hợp.

### 3.3. Xác minh trạng thái cuối không có nghĩa là bỏ qua trạng thái trung gian

Một quy trình có thể đạt trạng thái cuối đúng nhưng đã trải qua một chuyển trạng thái không hợp lệ. Với hệ thống có yêu cầu về kiểm toán, quyền hoặc tính toàn vẹn, cần kiểm tra các trạng thái trung gian có ý nghĩa.

Ví dụ, một giao dịch thanh toán có thể chuyển qua AUTHORIZED, CAPTURED và SETTLED. Nếu quy tắc yêu cầu không được chuyển trực tiếp từ FAILED sang SETTLED, ca kiểm thử cần xác minh ràng buộc chuyển trạng thái đó. Có thể kiểm tra bằng unit test cho state machine và integration test cho dữ liệu lưu trữ.

Chọn các trạng thái trung gian dựa trên rủi ro. Không cần kiểm tra mọi bước nội bộ nếu chúng không tạo ra khác biệt về hành vi hoặc hậu quả.

## 4. Kiểm chứng tương tác trong unit test và integration test

### 4.1. Unit test: thay thế phụ thuộc để kiểm tra hợp đồng cộng tác

Trong unit test, mock hoặc fake có thể giúp cô lập thành phần đang kiểm tra. Khi mục tiêu là xác minh lời gọi đến phụ thuộc, mock cho phép quan sát tham số và số lần gọi.

Ví dụ, dịch vụ thông báo cần gửi email xác nhận sau khi đơn hàng được tạo:

~~~java
@Test
void sendsConfirmationToTheOrderCustomer() {
    EmailGateway emailGateway = mock(EmailGateway.class);
    OrderService service = new OrderService(emailGateway);
    Order order = new Order("ORD-102", "buyer@example.test");

    service.confirm(order);

    verify(emailGateway).send(
        eq("buyer@example.test"),
        contains("ORD-102")
    );
}
~~~

Ca kiểm thử này có mục tiêu cụ thể: xác minh dịch vụ gửi thông báo đến đúng người nhận với nội dung có mã đơn hàng. Nếu chỉ kiểm tra rằng phương thức confirm trả về thành công, nhóm chưa chứng minh người nhận đúng.

Tuy nhiên, test này chưa chứng minh email thực sự được nhà cung cấp gửi đi. Nó chỉ chứng minh OrderService đã gọi cổng email theo hợp đồng mà test đang quan sát.

### 4.2. Kiểm tra việc không gọi cũng có thể quan trọng

Một số yêu cầu xác định rõ phụ thuộc không được gọi trong điều kiện nhất định.

Ví dụ, khi mã giảm giá không hợp lệ, hệ thống không được gọi payment gateway:

~~~java
@Test
void doesNotChargeWhenOrderValidationFails() {
    PaymentGateway gateway = mock(PaymentGateway.class);
    CheckoutService service = new CheckoutService(gateway);

    CheckoutResult result = service.checkout(invalidOrder());

    assertEquals("INVALID_ORDER", result.getCode());
    verifyNoInteractions(gateway);
}
~~~

Ở đây có hai bằng chứng khác nhau:

- Trạng thái kết quả cho biết yêu cầu bị từ chối.
- Assertion tương tác xác nhận không có yêu cầu thanh toán nào được gửi đi.

Nếu chỉ kiểm tra kết quả từ chối, lỗi gọi gateway trước khi kiểm tra dữ liệu có thể không bị phát hiện.

### 4.3. Kiểm tra số lần gọi và thứ tự khi có ràng buộc thực sự

Số lần gọi hoặc thứ tự chỉ nên được xác minh khi nó ảnh hưởng đến tính đúng đắn, an toàn hoặc chi phí.

Ví dụ, với thanh toán, việc gửi lại cùng yêu cầu có thể dẫn đến giao dịch trùng. Nhóm có thể kiểm tra payment gateway chỉ nhận một yêu cầu với cùng idempotency key. Với một workflow có thao tác bù trừ, nhóm có thể kiểm tra hành động hoàn tác được kích hoạt khi bước tiếp theo thất bại.

Không nên kiểm tra thứ tự mọi lời gọi nội bộ. Nếu hai lời gọi độc lập có thể đổi thứ tự mà không ảnh hưởng hành vi, assertion về thứ tự sẽ làm test dễ vỡ khi refactor.

### 4.4. Integration test: xác minh tương tác với phụ thuộc thật

Khi rủi ro nằm ở giao tiếp thực tế, integration test nên dùng thành phần thật hoặc môi trường tương thích thay vì chỉ xác minh mock được gọi.

Ví dụ:

- Gửi truy vấn đến cơ sở dữ liệu thử nghiệm và xác minh dữ liệu được ghi.
- Phát thông điệp vào message broker thử nghiệm và xác minh consumer xử lý.
- Gọi API của dịch vụ nội bộ trong môi trường tích hợp.
- Kiểm tra serialization/deserialization giữa producer và consumer.
- Xác minh transaction rollback khi một bước ghi dữ liệu thất bại.

Mock có thể chứng minh thành phần gọi đúng interface, nhưng không chứng minh cấu hình mạng, schema thực, quyền truy cập, transaction hoặc khả năng tương thích của dịch vụ thật.

## 5. Tránh lạm dụng mock và assertion tương tác

Kiểm chứng tương tác có thể rất hữu ích, nhưng việc mock quá nhiều sẽ làm test kiểm tra cách viết mã thay vì hành vi cần bảo đảm.

### 5.1. Dấu hiệu test đang phụ thuộc quá mức vào triển khai

Một ca kiểm thử có thể quá mong manh khi:

- Xác minh mọi lời gọi nội bộ dù không có yêu cầu về chúng.
- Kiểm tra thứ tự các lời gọi không có phụ thuộc nghiệp vụ.
- Mock nhiều lớp đến mức không còn hành vi thực nào được thực thi.
- Thất bại khi đổi tên hoặc tách một lớp dù hành vi bên ngoài không đổi.
- Dùng verify số lần gọi để thay cho xác minh kết quả thực tế.
- Lặp lại chi tiết implementation trong test setup và assertion.

Ví dụ, nếu một phương thức tính phí được tái cấu trúc từ hai lời gọi helper thành một lời gọi, test chỉ nên thất bại nếu quy tắc tính phí hoặc hợp đồng giao tiếp bị thay đổi. Nếu test thất bại chỉ vì số lần gọi helper thay đổi, assertion đó có thể đang kiểm tra chi tiết nội bộ.

### 5.2. Dùng đúng loại test double

| Test double | Công dụng | Khi phù hợp |
|---|---|---|
| Dummy | Được truyền vào nhưng không tham gia hành vi đang kiểm tra. | Cần đáp ứng chữ ký phương thức nhưng giá trị không được sử dụng. |
| Stub | Trả về dữ liệu định trước. | Cần kiểm soát phản hồi của phụ thuộc để kiểm tra kết quả thành phần. |
| Fake | Triển khai đơn giản nhưng có hành vi thực tế giới hạn. | Cần một phụ thuộc nhẹ, chẳng hạn repository in-memory. |
| Mock | Cho phép xác minh lời gọi, tham số và số lần gọi. | Tương tác là một phần của yêu cầu hoặc ràng buộc quan trọng. |
| Spy | Bao bọc đối tượng thật và ghi nhận một phần tương tác. | Cần quan sát lời gọi nhưng vẫn muốn chạy hành vi thật có chọn lọc. |

Không chọn mock chỉ vì framework hỗ trợ. Hãy chọn test double dựa trên câu hỏi cần trả lời. Nếu mục tiêu là kiểm tra kết quả tính toán, một input trực tiếp thường đủ. Nếu mục tiêu là phản ứng trước timeout của dịch vụ thanh toán, stub có thể mô phỏng lỗi; nếu mục tiêu là xác minh cổng thanh toán được gọi đúng một lần, mock có thể phù hợp.

### 5.3. Tránh mock chính đối tượng đang kiểm tra

Mock đối tượng đang kiểm tra có thể khiến test chỉ xác minh cấu hình mock, không thực thi logic cần xác minh. Hãy tạo đối tượng thật của đơn vị đang kiểm tra và thay thế các phụ thuộc bên ngoài bằng test double khi cần.

Ví dụ, khi kiểm tra CheckoutService, hãy tạo CheckoutService thật với PaymentGateway được mock. Khi đó, logic điều phối của CheckoutService vẫn chạy và test có thể quan sát hợp đồng tương tác.

### 5.4. Không dùng assertion tương tác thay cho bằng chứng tích hợp

Nếu mục tiêu là bảo đảm dữ liệu được lưu bền vững, xác minh repository.save được gọi chưa đủ. Cần kiểm tra dữ liệu thực sự tồn tại sau thao tác. Nếu mục tiêu là bảo đảm message consumer xử lý sự kiện, xác minh publisher được gọi chưa chứng minh consumer nhận và xử lý thông điệp.

Hãy đặt assertion ở ranh giới có thể chứng minh rủi ro: state assertion cho dữ liệu được lưu; integration test cho giao tiếp; contract test cho schema; end-to-end test cho hành trình người dùng.

## 6. Quy trình chọn cách kiểm chứng

Có thể áp dụng quy trình sau cho mỗi mục tiêu kiểm thử.

### Bước 1: Viết mục tiêu dưới dạng hành vi cần bảo đảm

Ví dụ: “Khi thanh toán được xác nhận, đơn hàng chuyển sang PAID và hệ thống phát một sự kiện PaymentCompleted.”

Mục tiêu này chứa cả kết quả trạng thái và một tác dụng phụ giao tiếp.

### Bước 2: Xác định bằng chứng quan sát được

Liệt kê điều cần kiểm tra:

- Trạng thái đơn hàng sau thao tác.
- Thông tin giao dịch được lưu.
- Sự kiện được phát với đúng order ID và transaction ID.
- Sự kiện không được phát nếu giao dịch thất bại.

### Bước 3: Đánh giá rủi ro nếu hành vi sai

Nếu trạng thái đơn hàng sai, người dùng có thể không nhận hàng hoặc bị tính tiền sai. Nếu sự kiện bị phát hai lần, downstream có thể gửi thông báo hoặc xử lý đơn trùng. Đây là các rủi ro có hậu quả khác nhau và có thể cần assertion khác nhau.

### Bước 4: Chọn tầng và cách kiểm chứng chính

- Unit test xác minh state transition và logic quyết định phát sự kiện.
- Unit test với mock xác minh sự kiện được phát đúng một lần khi đó là hợp đồng của thành phần.
- Integration test xác minh trạng thái được lưu và sự kiện đi qua cơ chế messaging thật.
- End-to-end test đại diện xác minh người dùng thấy đơn hàng đã thanh toán.

### Bước 5: Kiểm tra tính ổn định và khả năng chẩn đoán

Assertion có phụ thuộc chi tiết nội bộ không? Khi thất bại, nhóm có xác định được nguyên nhân không? Có thể kiểm tra trực tiếp trạng thái thay vì theo dõi nhiều lời gọi không? Có cần một integration test để xác minh hành vi của phụ thuộc thật không?

### Bước 6: Ghi lý do cho assertion quan trọng

Với các kiểm tra tương tác về số lần gọi, thứ tự hoặc việc không gọi, hãy ghi ngắn gọn ràng buộc hoặc rủi ro mà assertion bảo vệ. Điều này giúp người bảo trì hiểu vì sao kiểm tra cần tồn tại.

## 7. Ví dụ tổng hợp: xử lý đơn hàng và thanh toán

Giả sử CheckoutService thực hiện các bước:

1. Xác thực giỏ hàng và quyền mua.
2. Tính tổng tiền.
3. Gửi yêu cầu thanh toán đến PaymentGateway.
4. Lưu kết quả giao dịch.
5. Chuyển đơn hàng sang trạng thái phù hợp.
6. Phát sự kiện cho các dịch vụ downstream.

Không nên dùng một kiểu assertion duy nhất cho mọi hành vi. Ma trận sau minh họa cách lựa chọn:

| Mục tiêu | Cách kiểm chứng phù hợp | Lý do |
|---|---|---|
| Tổng tiền đúng theo quy tắc giảm giá | State verification trong unit test | Kết quả tính toán có thể quan sát trực tiếp. |
| Đơn không hợp lệ không bị tính tiền | State assertion và interaction verification | Cần xác nhận kết quả từ chối và bảo đảm gateway không được gọi. |
| Gateway nhận đúng số tiền và idempotency key | Interaction verification trong unit test | Tham số giao tiếp là một phần của hợp đồng. |
| Giao dịch và đơn hàng được lưu nhất quán | State verification trong integration test | Cần bằng chứng từ cơ sở dữ liệu và transaction thực. |
| Callback lặp không tạo thanh toán lặp | State verification cùng kiểm tra tương tác có chọn lọc | Cần xác nhận trạng thái cuối và ràng buộc xử lý trùng. |
| Sự kiện PaymentCompleted được phát sau thành công | Interaction verification ở unit test; integration test cho messaging | Việc phát sự kiện là tác dụng phụ quan trọng và cần kiểm tra đường truyền thật. |
| Người dùng nhìn thấy trạng thái thanh toán chính xác | End-to-end state verification | Đây là kết quả cuối mà người dùng trải nghiệm. |

Một test unit có thể trông như sau:

~~~java
@Test
void chargesOnceAndPublishesPaymentEventAfterSuccessfulValidation() {
    PaymentGateway gateway = mock(PaymentGateway.class);
    EventPublisher publisher = mock(EventPublisher.class);
    CheckoutService service = new CheckoutService(gateway, publisher);

    when(gateway.charge(any()))
        .thenReturn(PaymentResult.approved("TX-901"));

    CheckoutResult result = service.checkout(validOrder());

    assertEquals("PAID", result.getOrderStatus());
    verify(gateway, times(1)).charge(argThat(request ->
        request.amount().equals(new Money(120_000, "VND"))
            && request.idempotencyKey().equals("ORD-901")
    ));
    verify(publisher, times(1)).publish(argThat(event ->
        event.type().equals("PaymentCompleted")
            && event.orderId().equals("ORD-901")
    ));
}
~~~

Đây là ví dụ minh họa cách kết hợp assertion trạng thái và tương tác trong một ca có mục tiêu rõ. Trong hệ thống thực, việc xác minh trạng thái được lưu bền vững và thông điệp được chuyển đến consumer vẫn cần integration test phù hợp.

## 8. Ma trận quyết định nhanh

| Tình huống | Ưu tiên | Có thể bổ sung |
|---|---|---|
| Hàm tính toán thuần | Trạng thái/giá trị trả về | Kiểm tra tương tác chỉ khi có hợp đồng gọi phụ thuộc. |
| Quy tắc chuyển trạng thái | Trạng thái đối tượng | Kiểm tra lời gọi phát sự kiện nếu sự kiện là yêu cầu. |
| Ghi dữ liệu | Trạng thái được đọc lại từ kho dữ liệu | Xác minh lời gọi transaction hoặc repository khi cần chẩn đoán. |
| Gọi dịch vụ thanh toán | Tương tác và tham số gửi đi | Trạng thái giao dịch được lưu qua integration test. |
| Gửi thông báo | Tương tác về người nhận và nội dung | Trạng thái yêu cầu gửi hoặc kết quả từ adapter nếu có. |
| Từ chối đầu vào không hợp lệ | Kết quả lỗi | Xác minh không có tác dụng phụ nguy hiểm. |
| Giao tiếp message broker | Tương tác ở unit test; trạng thái xử lý ở integration test | Contract test cho schema và tương thích. |
| Hành trình người dùng | Trạng thái hoặc kết quả hiển thị | Một số kiểm tra tương tác ở ranh giới có rủi ro cao. |

Ma trận là hướng dẫn, không phải quy tắc bắt buộc. Một tình huống có thể cần cả hai cách kiểm chứng nếu chúng bảo vệ hai khía cạnh khác nhau.

## 9. Những sai lầm thường gặp

- **Chỉ kiểm tra trạng thái cuối:** có thể bỏ sót việc một dịch vụ nhạy cảm đã bị gọi sai hoặc tác dụng phụ không mong muốn đã xảy ra.
- **Chỉ kiểm tra lời gọi mock:** chứng minh lời gọi được thực hiện nhưng không chứng minh kết quả nghiệp vụ hoặc dữ liệu được lưu đúng.
- **Mock mọi phụ thuộc:** test trở nên cô lập quá mức và không còn kiểm tra ranh giới tích hợp quan trọng.
- **Xác minh mọi lời gọi nội bộ:** test phụ thuộc cấu trúc triển khai và dễ hỏng khi refactor.
- **Kiểm tra thứ tự không cần thiết:** làm giảm tính linh hoạt dù thứ tự không ảnh hưởng kết quả.
- **Không kiểm tra việc không gọi:** có thể bỏ sót tác dụng phụ nguy hiểm khi đầu vào không hợp lệ hoặc quyền bị từ chối.
- **Nhầm lẫn mock với tích hợp thật:** mock không xác minh mạng, cấu hình, schema thực hoặc hành vi của nhà cung cấp.
- **Dùng cùng một kiểu assertion cho mọi rủi ro:** mỗi mục tiêu cần bằng chứng phù hợp với hậu quả nếu sai.

## 10. Danh sách rà soát trước khi hoàn tất bộ kiểm thử

- [ ] Mục tiêu kiểm thử được mô tả thành hành vi hoặc ràng buộc cụ thể.
- [ ] Nhóm xác định được trạng thái hoặc kết quả có thể quan sát.
- [ ] Các tương tác quan trọng được nhận diện theo hợp đồng và rủi ro.
- [ ] Assertion trạng thái được ưu tiên khi kết quả là bằng chứng trực tiếp.
- [ ] Assertion tương tác chỉ kiểm tra lời gọi, tham số, số lần hoặc thứ tự có ý nghĩa.
- [ ] Trường hợp cần thiết đã xác minh phụ thuộc không được gọi.
- [ ] Mock, stub, fake và spy được chọn đúng mục đích.
- [ ] Integration test xác minh các ranh giới mà unit test không thể chứng minh.
- [ ] Không mock quá mức hoặc kiểm tra chi tiết triển khai không thuộc hợp đồng.
- [ ] Mỗi assertion quan trọng có lý do gắn với yêu cầu hoặc rủi ro.
- [ ] Test ổn định, có khả năng chẩn đoán và không lặp bằng chứng không cần thiết.

## Kết luận

Kiểm chứng trạng thái trả lời kết quả sau hành động có đúng không; kiểm chứng tương tác trả lời thành phần có phối hợp với phụ thuộc theo đúng hợp đồng không. Hãy ưu tiên trạng thái khi kết quả có thể quan sát trực tiếp, và dùng kiểm chứng tương tác khi lời gọi, tham số, số lần, thứ tự hoặc việc không gọi có ý nghĩa đối với rủi ro. Khi kết hợp hai cách có chủ đích giữa unit test và integration test, nhóm có thể tạo bằng chứng đủ mạnh mà vẫn giữ bộ kiểm thử ổn định, dễ bảo trì và tập trung vào hành vi thực sự quan trọng.
