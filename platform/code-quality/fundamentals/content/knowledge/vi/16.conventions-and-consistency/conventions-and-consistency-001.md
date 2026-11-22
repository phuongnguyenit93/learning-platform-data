# Quy ước định dạng, đặt tên và cách diễn đạt

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **quy ước định dạng, đặt tên và cách diễn đạt** làm mã Java dễ đọc, dễ kiểm tra và dễ thay đổi hơn.
2. Phân biệt ba nhóm vấn đề: **hình thức trình bày**, **từ vựng và ý nghĩa**, **cách biểu diễn luồng suy luận**.
3. Áp dụng các quy ước đặt tên thông dụng của Java cho package, lớp, interface, phương thức, biến, hằng số và test mà vẫn tôn trọng ngôn ngữ nghiệp vụ.
4. Cải thiện những biểu thức khó hiểu bằng tên gọi rõ, điều kiện có chủ đích, phương thức có trách nhiệm nhất quán và comment giải thích lý do.
5. Chọn cách duy trì quy ước bằng formatter, linter, IDE, CI và code review, đồng thời phân biệt ngoại lệ hợp lý với sự thiếu nhất quán vô cớ.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn **có đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Quy ước là một phần của chất lượng vì mã được **đọc nhiều lần hơn là viết một lần**: người bảo trì phải hiểu ý định, dự đoán tác động và xác minh thay đổi.

Quy ước có ích không phải vì mọi người cùng thích một phong cách, mà vì chúng giảm số điều phải đoán. Khi mã dùng cùng cách đặt tên và cùng mô hình diễn đạt cho những việc tương tự, người đọc dành nhiều sự chú ý hơn cho **quy tắc nghiệp vụ**, thay vì giải mã phong cách của từng tác giả.

**Nguyên tắc xuyên suốt:** Quy ước tốt khiến ý định rõ ràng và có thể thực thi nhất quán; quy ước chỉ làm mã “trông giống nhau” nhưng che khuất ngữ nghĩa thì cần xem lại.

## 1. Ba lớp của sự nhất quán trong mã nguồn

Ba nhóm quy ước có liên quan nhưng không thể thay thế cho nhau.

| Nhóm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Định dạng (formatting)** | Mã được trình bày nhất quán như thế nào? | Thụt lề, dấu ngoặc, xuống dòng, khoảng trắng, import |
| **Đặt tên (naming)** | Một tên giúp người đọc hiểu vai trò và ý nghĩa đến đâu? | **orderId**, **unitPriceVnd**, **calculateSubtotal()** |
| **Cách diễn đạt (expression)** | Ý tưởng được thể hiện theo trình tự dễ suy luận không? | Điều kiện rõ ràng, ít phủ định kép, tách phép tính khỏi I/O |

Một đoạn mã được formatter xử lý có thể có khoảng trắng hoàn hảo nhưng vẫn rất khó hiểu vì các biến tên **a**, **x1** và phương thức tên **process()** làm quá nhiều việc. Ngược lại, mã có tên nghiệp vụ rõ nhưng định dạng tùy tiện ở mỗi tệp cũng khiến việc review và đọc diff khó hơn.

Ví dụ giả định:

~~~java
// Khó hiểu dù cú pháp Java hợp lệ.
double f(double x, int y, boolean z) {
    double a=x*y;
    return z&&a<500000?a+30000:a;
}
~~~

Để hiểu hàm, người đọc phải đoán:
- **x** là giá nào, có đơn vị gì?
- **y** là số lượng hay tỷ lệ?
- **z** biểu diễn quyết định nào?
- Ngưỡng **500000** mang ý nghĩa gì?
- **30000** là phí hay giảm giá?
- Điều kiện **a < 500000** có đúng tại ranh giới không?

Thêm khoảng trắng chỉ giải quyết một phần:

~~~java
double f(double x, int y, boolean z) {
    double a = x * y;
    return z && a < 500000 ? a + 30000 : a;
}
~~~

Định dạng đã dễ nhìn hơn, nhưng **ý nghĩa vẫn bị giấu**. Cần tiếp tục xác định hợp đồng và dùng tên, kiểu dữ liệu, cấu trúc biểu thức phù hợp. Đây là lý do các quy ước phải phối hợp.

## 2. Quy ước định dạng: giảm tiếng ồn khi đọc và review

### 2.1. Những quyết định định dạng thường gặp

Một codebase Java nên có lựa chọn rõ và ổn định về:
- Thụt lề và cách xuống dòng của khối lệnh.
- Dấu ngoặc nhọn cho câu điều kiện, vòng lặp và lớp.
- Khoảng trắng quanh toán tử và sau dấu phẩy.
- Cách tổ chức import và tránh import không dùng.
- Giới hạn chiều rộng dòng và cách xuống dòng biểu thức dài.
- Dấu xuống dòng cuối tệp, mã hóa UTF-8 và kiểu line ending.
- Định dạng lời gọi phương thức nhiều tham số, builder và chuỗi phương thức.
- Cách đặt comment, Javadoc và annotation.

Không có một kiểu dấu ngoặc hay một ngưỡng độ rộng dòng luôn là tốt nhất trong mọi dự án. Tuy nhiên, **một quy ước được áp dụng ổn định** giúp giảm tranh luận và tránh diff không có giá trị.

### 2.2. Cùng một luồng nhưng khó theo dõi vì trình bày

Ví dụ:

~~~java
// Minh họa cách viết khó đọc.
if(quantity>0){if(customer!=null){total=price.multiply(
BigDecimal.valueOf(quantity));}}
~~~

Ngay cả khi logic nghiệp vụ được giữ nguyên, cách viết theo khối giúp nhìn rõ điều kiện lồng nhau:

~~~java
if (quantity > 0) {
    if (customer != null) {
        total = price.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

Nhưng chưa nên dừng ở việc format. Nếu đầu vào không hợp lệ phải được từ chối, có thể diễn đạt hợp đồng rõ hơn:

~~~java
if (quantity <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
Objects.requireNonNull(customer, "customer");

BigDecimal total = price.multiply(BigDecimal.valueOf(quantity));
~~~

Đoạn cuối **khác ngữ nghĩa** với hai ví dụ đầu: nó ném lỗi thay vì lặng lẽ bỏ qua phép tính. Đây chỉ là cải tiến hợp lý **nếu hợp đồng đã yêu cầu từ chối đầu vào không hợp lệ**. Formatter không được và không thể tự quyết định thay đổi hành vi như vậy.

### 2.3. Quy ước tự động hóa được nên giao cho công cụ

Các công cụ thường gặp trong dự án Java:

| Công cụ/cơ chế | Phù hợp để làm gì? | Không thay thế được điều gì? |
| --- | --- | --- |
| **EditorConfig** | Một số quy tắc editor như charset, indent, line ending, final newline | Hợp đồng đặt tên và ý nghĩa nghiệp vụ |
| **google-java-format** | Định dạng Java theo phong cách thống nhất của công cụ | Quy tắc nghiệp vụ, chất lượng abstraction |
| **Spotless** | Tích hợp các bước format/check vào quy trình build | Test tính đúng đắn |
| **Checkstyle** | Kiểm tra các quy ước tĩnh tùy cấu hình: tên, import, dấu ngoặc, một số quy tắc cấu trúc | Khả năng hiểu toàn bộ nghiệp vụ |
| **PMD / static analysis** | Cảnh báo một số mẫu mã có rủi ro hoặc khó bảo trì | Phán đoán liệu mọi cảnh báo đều là lỗi |
| **IDE formatter / inspection** | Giúp lập trình viên nhận phản hồi trước khi commit | CI và thống nhất giữa nhiều môi trường |
| **CI** | Kiểm tra mọi thay đổi theo cùng tập công cụ và cấu hình | Review hành vi, ngữ nghĩa và đánh đổi |

Một ví dụ **.editorconfig** ở mức minh họa:

~~~ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.java]
indent_style = space
indent_size = 4
~~~

**Đây không phải cấu hình bắt buộc** của mọi dự án Java. Nếu nhóm chọn formatter với quy ước khác, cần để EditorConfig, IDE và CI **không mâu thuẫn** với formatter đó.

Lưu ý: formatter có thể thay cách chia dòng theo quy tắc riêng, kể cả khi một người muốn xuống dòng theo cách khác. Không nên chỉnh tay đi chỉnh tay lại một đoạn đã được formatter quản lý: điều đó gây diff lặp lại và tốn thời gian review.

### 2.4. Vì sao một pull request chỉ đổi định dạng có thể gây khó khăn?

Một thay đổi chức năng gồm 20 dòng nhưng formatter bất ngờ sửa thêm 2.000 dòng không liên quan sẽ:
- Làm reviewer khó thấy thay đổi hành vi thật.
- Tăng nguy cơ xung đột merge với các nhánh khác.
- Khi truy vết lịch sử, commit định dạng có thể che ngữ cảnh của thay đổi trước.

Trong codebase cũ, việc chuẩn hóa toàn bộ định dạng có thể cần thiết, nhưng nên **tách commit hoặc pull request định dạng** khỏi commit thay đổi nghiệp vụ khi có thể; nêu rõ phạm vi và kiểm tra rằng không có thay đổi ngữ nghĩa. Với mã mới, tự động format ngay từ đầu giúp tránh tích tụ nợ định dạng.

## 3. Quy ước đặt tên cơ bản của Java

Java có những quy ước phổ biến giúp người đọc nhận ra vai trò của một định danh. Dự án có thể áp dụng chuẩn cụ thể hơn, nhưng các trường hợp điển hình gồm:

| Thành phần | Dạng thường dùng | Ví dụ |
| --- | --- | --- |
| Package | Chữ thường, thường dùng nhiều phân đoạn có nghĩa | **com.example.orders.pricing** |
| Class | **UpperCamelCase** | **OrderCalculator**, **CustomerRepository** |
| Interface | **UpperCamelCase**, tên mô tả hợp đồng/khả năng | **PaymentGateway**, **ClockSource** |
| Record | **UpperCamelCase**, tên một loại dữ liệu có ý nghĩa | **OrderLine**, **MoneyAmount** |
| Enum | **UpperCamelCase** | **OrderStatus**, **PaymentResult** |
| Hằng enum | **UPPER_SNAKE_CASE** | **PAID**, **PAYMENT_FAILED** |
| Phương thức | **lowerCamelCase** | **calculateSubtotal()**, **findById()** |
| Biến/field/tham số | **lowerCamelCase** | **orderId**, **lineTotal**, **customerTier** |
| Hằng **static final** thật sự | **UPPER_SNAKE_CASE** theo quy ước được chọn | **MAX_ITEMS_PER_ORDER**, **DEFAULT_TIMEOUT** |
| Tham số kiểu tổng quát | Tên ngắn có nghĩa hoặc tên theo quy ước dự án | **T**, **E**, **K**, **V**, hoặc tên mô tả hơn |
| Test | Tên mô tả hành vi/hợp đồng | **rejectsZeroQuantity()** |

Một số phân biệt cần nhớ:

- **Không phải mọi biến final đều là hằng theo nghĩa đặt tên.** Một biến cục bộ **final BigDecimal subtotal** vẫn thường dùng lowerCamelCase. Một field **static final** cũng có thể giữ đối tượng không bất biến; nên xem **ngữ nghĩa của giá trị và quy ước dự án**, không chỉ hai từ khóa.
- **Không nhất thiết đặt tiền tố I cho interface** như **IPaymentGateway**, nếu codebase dùng **PaymentGateway** và **StripePaymentGateway**. Tính nhất quán trong hệ thống quan trọng hơn áp một quy tắc phụ không có mục đích.
- Những từ viết tắt như **URL**, **HTTP**, **ID** có thể được viết theo nhiều quy ước trong tên Java (ví dụ **parseUrl** hay **parseURL**). Chọn quy tắc của nhóm và tránh đổi cách viết của một khái niệm trong cùng API.
- Tên package là một phần của API/kiến trúc. Đổi package có thể tác động import, cấu hình serialization, reflection hoặc người dùng thư viện. Không nên đổi hàng loạt chỉ để làm tên “đẹp hơn” mà bỏ qua tương thích.

**Điểm quan trọng hơn kiểu chữ** là cùng một loại thông tin được gọi bằng một thuật ngữ có ý nghĩa ổn định. **customerId** và **customerCode** có thể đều đặt theo camelCase, nhưng chúng không nhất thiết chỉ cùng một thứ.

## 4. Đặt tên phải diễn đạt được ý nghĩa nghiệp vụ

### 4.1. Chọn từ theo miền nghiệp vụ

Giả sử hệ thống bán hàng có các khái niệm:
- **subtotal**: tổng tiền hàng trước những điều chỉnh được định nghĩa.
- **discountAmount**: số tiền giảm theo một chính sách.
- **shippingFee**: phí vận chuyển.
- **payableAmount**: số tiền khách phải trả theo công thức đã công bố.

Đặt tất cả thành **amount1**, **amount2**, **total1** và **finalTotal** buộc người đọc đoán quan hệ giữa các giá trị. Tên chính xác giúp code review và test dễ hơn.

Ví dụ:

~~~java
BigDecimal subtotalVnd = new BigDecimal("500000");
BigDecimal discountVnd = new BigDecimal("50000");
BigDecimal shippingFeeVnd = new BigDecimal("30000");

BigDecimal payableVnd = subtotalVnd
        .subtract(discountVnd)
        .add(shippingFeeVnd);
~~~

Ví dụ chỉ để diễn đạt tên gọi; công thức thực tế phải dựa trên chính sách thuế, giảm giá, làm tròn và khoản phí của sản phẩm. **Vnd** trong tên làm rõ đơn vị ở một hệ thống đang quy định số tiền theo VND. Nếu hỗ trợ nhiều loại tiền, nên có **kiểu tiền mang mã tiền tệ** thay vì dựa hoàn toàn vào hậu tố tên.

### 4.2. Tên phải phân biệt các khái niệm khác nhau

Một số cặp dễ nhầm:

| Tên | Có thể mang ý nghĩa gì? | Vì sao cần phân biệt? |
| --- | --- | --- |
| **customerId** / **customerCode** | Định danh nội bộ / mã nghiệp vụ bên ngoài | Không tự thay thế cho nhau ở tra cứu hoặc API |
| **createdAt** / **paidAt** | Thời điểm tạo / thời điểm thanh toán | Dùng sai thời điểm khiến báo cáo sai |
| **subtotal** / **payableAmount** | Trước / sau các điều chỉnh | Phải biết giảm giá, thuế và phí đã tính chưa |
| **timeoutMillis** / **deadline** | Khoảng thời gian / thời điểm kết thúc | Không nên dùng chung tên **timeout** cho cả hai |
| **sku** / **productId** | Mã hàng bán / ID thực thể sản phẩm | Một sản phẩm có thể có nhiều SKU |
| **status** / **transition** | Trạng thái hiện tại / hành động đổi trạng thái | Giúp kiểm tra bảng chuyển trạng thái |
| **isEligible** / **isAuthorized** | Đáp ứng điều kiện khuyến mại / có quyền truy cập | Hợp lệ nghiệp vụ không đồng nghĩa được phép truy cập |

Nên xây dựng **bảng thuật ngữ nghiệp vụ nhỏ** cho những khái niệm xuyên nhiều tính năng. Không cần tài liệu hóa mọi biến cục bộ, nhưng cần thống nhất những tên đóng vai trò hợp đồng giữa các module.

### 4.3. Tránh từ mơ hồ và “tên nhiều nghĩa”

Những tên như **data**, **info**, **object**, **process**, **manager**, **util**, **handle**, **tmp** không phải luôn sai, nhưng trở nên yếu khi chúng che khuất trách nhiệm.

Ví dụ:

~~~java
// Người đọc không biết thao tác nào thực sự xảy ra.
void process(Order order);

// Tên thể hiện kết quả hoặc tác dụng phụ cụ thể hơn.
BigDecimal calculateSubtotal(Order order);
void reserveInventory(Order order);
void publishOrderConfirmed(Order order);
~~~

Ba phương thức sau không nhất thiết phải cùng tồn tại. Chúng cho thấy **một tên nên giúp người gọi dự đoán việc được thực hiện**. Nếu cùng một phương thức vừa tính tiền vừa phát sự kiện, việc đổi tên vẫn không giải quyết hoàn toàn vấn đề tách trách nhiệm.

### 4.4. Độ dài tên phụ thuộc vào phạm vi

Một biến đếm trong vòng lặp rất nhỏ có thể dùng **i** nếu không gây nhầm. Nhưng một biến **x** được truyền qua nhiều phương thức và giữ vai trò tổng tiền sẽ khiến người đọc trả giá cao về nhận thức.

Ví dụ:

~~~java
for (int index = 0; index < lines.size(); index++) {
    OrderLine line = lines.get(index);
    // ...
}
~~~

**index** rõ vai trò hơn **i** khi có nhiều chỉ số hoặc vòng lặp lồng nhau. Nếu chỉ là một vòng lặp tuyến tính đơn giản, **i** có thể vẫn phù hợp với quy ước nhóm. Không cần tạo tên dài một cách máy móc.

Hãy hỏi: **Người đọc có thể hiểu vai trò của tên mà không phải tìm ngược nhiều trang code không?**

## 5. Tên boolean và điều kiện: tránh phủ định kép

Một boolean nên thể hiện một mệnh đề có thể đọc thành câu:

~~~java
boolean paymentConfirmed;
boolean hasPermission;
boolean isEligibleForFreeShipping;
boolean shouldRetry;
~~~

Cách đặt tên không nhất thiết buộc mọi biến boolean phải có tiền tố **is**. Với field trong JavaBeans hoặc framework serialization, tên property và getter có quy ước riêng cần giữ ổn định. Điều đáng quan tâm là biểu thức dễ đọc và không gây đảo ngược ý nghĩa.

So sánh:

~~~java
// Có thể khiến người đọc phải suy luận hai lần phủ định.
if (!userNotBlocked && !orderNotReady) {
    submit(order);
}
~~~

Với các biến thể hiện cùng hợp đồng, cách đọc dễ hơn:

~~~java
if (userActive && orderReady) {
    submit(order);
}
~~~

**Lưu ý:** Hai biểu thức chỉ tương đương khi **userNotBlocked** thật sự mang nghĩa phủ định chính xác của **userActive** và **orderNotReady** phủ định chính xác của **orderReady**. Trong nghiệp vụ có nhiều trạng thái, “không bị chặn” chưa chắc là “đang hoạt động”. Khi đổi tên, phải xác nhận hợp đồng thay vì chỉ rút gọn phép phủ định.

### Guard clause để giảm độ lồng nhau

Một phương thức từ chối dữ liệu sớm có thể tránh kéo cả luồng chính vào nhiều tầng if:

~~~java
void approve(Order order, User actor) {
    Objects.requireNonNull(order, "order");
    Objects.requireNonNull(actor, "actor");

    if (!actor.canApprove(order)) {
        throw new SecurityException("not allowed to approve");
    }
    if (!order.isAwaitingApproval()) {
        throw new IllegalStateException("invalid order state");
    }

    order.approve();
}
~~~

Đoạn mã minh họa ngữ nghĩa: **kiểm tra tiền điều kiện → thực hiện hành động chính**. Việc gọi **canApprove** hoặc **approve** ở đây giả định các hợp đồng liên quan được xác định và thực thi đúng. Trong ứng dụng thật, quyền và thay đổi trạng thái còn phải được bảo vệ ở tầng giao dịch nếu có cập nhật đồng thời.

Guard clause không phải quy tắc bắt buộc ở mọi phương thức. Với thuật toán có nhiều nhánh cân đối hoặc pattern matching rõ ràng, một **switch** hoặc bảng trạng thái có thể diễn đạt tốt hơn.

## 6. Tên phương thức phải khớp tác dụng phụ và hợp đồng

Một tên như **calculateTotal()** thường gợi ý phép tính. Nếu phương thức này còn ghi database, gọi cổng thanh toán và gửi email, người gọi có thể không lường trước tác dụng phụ.

Nên xem mức độ khớp giữa tên và hợp đồng:

| Tên | Kỳ vọng thường gặp | Điều nên tránh |
| --- | --- | --- |
| **calculateSubtotal()** | Tính ra giá trị từ đầu vào | Âm thầm lưu dữ liệu hoặc phát sự kiện |
| **findById()** | Truy vấn theo ID, có thể không tìm thấy | Tự tạo đối tượng mới khi không thấy mà không nói rõ |
| **save()** | Yêu cầu lưu dữ liệu theo hợp đồng repository | Vừa lưu vừa gửi email không được công bố |
| **reserveInventory()** | Thực hiện hành vi giữ tồn kho | Chỉ kiểm tra tồn kho nhưng gọi tên “giữ” |
| **validateOrder()** | Kiểm tra điều kiện hợp lệ | Tự sửa dữ liệu hoặc đặt hàng mà không nêu rõ |
| **publishOrderCreated()** | Phát thông báo/sự kiện | Sửa trạng thái đơn theo cách không được hợp đồng quy định |

Không nên suy từ tên rằng mọi phương thức **get...** đều phải thuần hoặc không tốn tài nguyên, vì trong API thực tế một getter có thể lazy load. Nhưng nếu chi phí, I/O hoặc tác dụng phụ đáng kể, API nên làm rõ thông qua **tên, tài liệu hoặc ranh giới sử dụng**.

### Phân biệt thao tác truy vấn và lệnh thay đổi

Một phân biệt hữu ích là:
- **Query:** lấy dữ liệu/kết quả, người gọi thường kỳ vọng không làm thay đổi trạng thái nghiệp vụ.
- **Command:** yêu cầu tạo tác dụng phụ hoặc thay đổi trạng thái.

Không phải mọi hệ thống đều cần áp dụng CQRS hoặc hai bộ lớp riêng. Nguyên tắc đủ dùng ở đây là **người gọi biết khi nào hành động có tác dụng phụ**, tránh việc một tên đọc dữ liệu lại lặng lẽ sửa dữ liệu.

## 7. Cách diễn đạt biểu thức: làm nổi bật quy tắc thay vì cú pháp

### 7.1. Một biểu thức quá ngắn có thể làm mất ý nghĩa

Ví dụ:

~~~java
return a >= 500000 && !b ? 0 : 30000;
~~~

Biểu thức này có thể chính xác với một hợp đồng rất cụ thể, nhưng tên và con số không cho biết tại sao. Nếu nghiệp vụ quy định miễn phí vận chuyển cho đơn từ 500.000 đồng và không bị hủy, có thể viết:

~~~java
private static final BigDecimal FREE_SHIPPING_THRESHOLD_VND =
        new BigDecimal("500000");
private static final BigDecimal STANDARD_SHIPPING_FEE_VND =
        new BigDecimal("30000");

BigDecimal shippingFee(BigDecimal subtotalVnd, boolean cancelled) {
    Objects.requireNonNull(subtotalVnd, "subtotalVnd");
    if (subtotalVnd.signum() < 0) {
        throw new IllegalArgumentException("negative subtotal");
    }
    if (cancelled) {
        return BigDecimal.ZERO; // Giả định nghiệp vụ minh họa.
    }

    boolean qualifiesForFreeShipping =
            subtotalVnd.compareTo(FREE_SHIPPING_THRESHOLD_VND) >= 0;
    return qualifiesForFreeShipping
            ? BigDecimal.ZERO
            : STANDARD_SHIPPING_FEE_VND;
}
~~~

**Chú ý hợp đồng:** Việc đơn hủy có phí bằng 0 là **quy tắc giả định của ví dụ**, không nên tự áp cho mọi hệ thống. Điểm cần học là tên **qualifiesForFreeShipping** và hai hằng số giúp diễn đạt ngưỡng và kết quả.

Đồng thời, dùng **BigDecimal** cho tiền tránh nhiều vấn đề từ biểu diễn số thập phân bằng **double**, nhưng nó không tự quy định đơn vị, tiền tệ hoặc chính sách làm tròn. Những yêu cầu này cần được mô hình hóa rõ ở nơi thích hợp.

### 7.2. Đặt tên cho điều kiện phức hợp

Với các điều kiện có nhiều lý do nghiệp vụ:

~~~java
if (status == Status.PAID
        && !fraudHold
        && addressVerified
        && total.compareTo(limit) <= 0) {
    releaseForShipping();
}
~~~

Khi đọc, người bảo trì cần giữ nhiều điều kiện trong đầu. Có thể đặt tên cho kết luận:

~~~java
boolean paymentReady = status == Status.PAID && !fraudHold;
boolean deliveryReady = addressVerified;
boolean withinShippingLimit = total.compareTo(limit) <= 0;

if (paymentReady && deliveryReady && withinShippingLimit) {
    releaseForShipping();
}
~~~

Phân tích này chỉ hữu ích nếu **paymentReady** thật sự biểu diễn toàn bộ điều kiện thanh toán được phép theo nghiệp vụ. Nếu chỉ là một phần trong nhiều quy tắc khác, tên quá mạnh sẽ gây hiểu nhầm. **Tên tốt phải đúng về nghĩa, không chỉ dễ đọc về hình thức.**

### 7.3. Kiểm soát thứ tự ưu tiên toán tử

Trong Java, **&&** có độ ưu tiên cao hơn **||**. Một biểu thức như:

~~~java
boolean eligible = premium || reachedThreshold && !cancelled;
~~~

có nghĩa:

~~~java
boolean eligible =
        premium || (reachedThreshold && !cancelled);
~~~

Nếu hợp đồng quy định **đơn bị hủy không bao giờ được hưởng ưu đãi**, phải viết:

~~~java
boolean eligible =
        !cancelled && (premium || reachedThreshold);
~~~

Không nên chỉ đổi dấu ngoặc vì “đọc đẹp hơn”: ở đây đó là **thay đổi hành vi**. Trước khi sửa, phải xác nhận quy tắc nghiệp vụ bằng bảng điều kiện và test. Dấu ngoặc rõ ràng giúp người đọc ít phải ghi nhớ thứ tự ưu tiên, nhưng không tự chứng minh biểu thức đúng.

### 7.4. Chọn if, switch, biểu thức điều kiện hay bảng quy tắc

| Tình huống | Cách diễn đạt thường dễ hiểu |
| --- | --- |
| Một lựa chọn ngắn giữa hai giá trị | Toán tử **?:** nếu biểu thức vẫn rõ |
| Nhiều điều kiện độc lập hoặc có thứ tự ưu tiên | **if/else** hoặc guard clauses có tên |
| Nhiều nhánh theo một enum khép kín | **switch** với từng trường hợp rõ |
| Nhiều chiều điều kiện và nhiều kết quả | **Bảng quyết định** để làm rõ nghiệp vụ trước khi triển khai |
| Trạng thái và chuyển trạng thái hợp lệ | **State machine** hoặc mô hình miền tương ứng |
| Nhiều chính sách có lý do thay đổi độc lập | Các **policy/strategy** có hợp đồng rõ nếu có nhu cầu thật |

Không có một cấu trúc điều khiển luôn phù hợp cho mọi nơi. Không nên đổi **if** sang **switch** chỉ để giảm một chỉ số độ phức tạp; hãy xem cách nào giúp hợp đồng và trường hợp biên dễ kiểm chứng hơn.

### 7.5. Stream hay vòng lặp?

Dùng Stream cho biến đổi dữ liệu tuyến tính có thể rõ ràng:

~~~java
BigDecimal subtotal = lines.stream()
        .map(OrderLine::total)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Một vòng lặp cũng có thể rất dễ hiểu:

~~~java
BigDecimal subtotal = BigDecimal.ZERO;
for (OrderLine line : lines) {
    subtotal = subtotal.add(line.total());
}
~~~

Không nên xem một trong hai là dấu hiệu chất lượng tuyệt đối. Với tập dữ liệu lớn, yêu cầu hiệu năng, lỗi cần xử lý từng phần tử hoặc phép biến đổi có tác dụng phụ, cách chọn có thể khác. Điều quan trọng là **trình tự có thể đọc và kết quả đúng hợp đồng**; nếu tối ưu hiệu năng, hãy đo trên dữ liệu đại diện.

## 8. Ví dụ Java 17 hoàn chỉnh: tên và cấu trúc làm rõ hợp đồng

Xét một tính năng tính tổng đơn hàng đơn giản. Giả định được xác nhận:

1. Mỗi dòng hàng có SKU không rỗng, đơn giá VND không âm và số lượng dương.
2. Đơn hàng có ít nhất một dòng.
3. **subtotalVnd** bằng tổng **unitPriceVnd × quantity** của từng dòng.
4. Nếu subtotal từ 500.000 đồng, phí vận chuyển bằng 0; thấp hơn, phí là 30.000 đồng.
5. **payableVnd = subtotalVnd + shippingFeeVnd**.
6. Ví dụ không xét thuế, giảm giá, giao dịch thanh toán và biểu diễn đa tiền tệ.

Những giả định này giúp hiểu vì sao lớp và phương thức mang tên như vậy; chúng không phải chính sách áp dụng chung cho mọi hệ thống.

### 8.1. Mô hình dữ liệu có tên giàu ý nghĩa

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

record OrderLine(
        String sku,
        BigDecimal unitPriceVnd,
        int quantity) {

    OrderLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPriceVnd, "unitPriceVnd");
        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (unitPriceVnd.signum() < 0) {
            throw new IllegalArgumentException(
                    "unitPriceVnd must be non-negative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
    }

    BigDecimal lineTotalVnd() {
        return unitPriceVnd.multiply(
                BigDecimal.valueOf(quantity));
    }
}

record OrderSummary(
        BigDecimal subtotalVnd,
        BigDecimal shippingFeeVnd,
        BigDecimal payableVnd) {

    OrderSummary {
        Objects.requireNonNull(subtotalVnd, "subtotalVnd");
        Objects.requireNonNull(shippingFeeVnd, "shippingFeeVnd");
        Objects.requireNonNull(payableVnd, "payableVnd");
        if (subtotalVnd.signum() < 0
                || shippingFeeVnd.signum() < 0
                || payableVnd.signum() < 0) {
            throw new IllegalArgumentException(
                    "order summary cannot contain negative amounts");
        }
    }
}
~~~

**OrderLine** diễn đạt một dòng hàng thay vì truyền nhiều tham số cùng kiểu qua các phương thức. Các tên **unitPriceVnd**, **quantity** và **lineTotalVnd** giúp người đọc nhận diện đơn vị và phép tính ngay tại nơi dùng.

**OrderSummary** đặt tên từng thành phần của kết quả. Không nên trả **List<BigDecimal>** với các vị trí 0, 1, 2 rồi bắt người gọi đoán thứ tự. Record cũng tạo dữ liệu thuận tiện cho việc kiểm tra kết quả bằng test.

**Giới hạn của ví dụ:** Constructor OrderLine chưa áp dụng chính sách số chữ số thập phân hoặc mức tiền tối đa. Với VND hoặc tiền tệ khác, cần thêm hợp đồng về đơn vị nhỏ nhất và làm tròn nếu thực tế yêu cầu. Đoạn mã tập trung minh họa quy ước tên và diễn đạt, không phải thư viện tiền tệ hoàn chỉnh.

### 8.2. Thành phần tính toán có tên phương thức theo trách nhiệm

~~~java
final class OrderTotalCalculator {
    private static final BigDecimal FREE_SHIPPING_THRESHOLD_VND =
            new BigDecimal("500000");
    private static final BigDecimal STANDARD_SHIPPING_FEE_VND =
            new BigDecimal("30000");

    private OrderTotalCalculator() {
    }

    static OrderSummary summarize(List<OrderLine> lines) {
        Objects.requireNonNull(lines, "lines");
        if (lines.isEmpty()) {
            throw new IllegalArgumentException(
                    "order must have at least one line");
        }

        BigDecimal subtotalVnd = calculateSubtotalVnd(lines);
        BigDecimal shippingFeeVnd =
                calculateShippingFeeVnd(subtotalVnd);
        BigDecimal payableVnd =
                subtotalVnd.add(shippingFeeVnd);

        return new OrderSummary(
                subtotalVnd, shippingFeeVnd, payableVnd);
    }

    private static BigDecimal calculateSubtotalVnd(
            List<OrderLine> lines) {
        BigDecimal subtotalVnd = BigDecimal.ZERO;
        for (OrderLine line : lines) {
            Objects.requireNonNull(line, "line");
            subtotalVnd = subtotalVnd.add(line.lineTotalVnd());
        }
        return subtotalVnd;
    }

    private static BigDecimal calculateShippingFeeVnd(
            BigDecimal subtotalVnd) {
        boolean qualifiesForFreeShipping =
                subtotalVnd.compareTo(FREE_SHIPPING_THRESHOLD_VND) >= 0;

        return qualifiesForFreeShipping
                ? BigDecimal.ZERO
                : STANDARD_SHIPPING_FEE_VND;
    }
}
~~~

Các quyết định tên giúp thể hiện cấu trúc:
- **summarize(...)** trả một bản tóm tắt gồm nhiều giá trị, không có I/O.
- **calculateSubtotalVnd(...)** chỉ giải quyết phép cộng thành tiền dòng hàng.
- **calculateShippingFeeVnd(...)** diễn đạt một quy tắc phí cụ thể.
- **FREE_SHIPPING_THRESHOLD_VND** thay con số ẩn trong điều kiện.
- **qualifiesForFreeShipping** diễn đạt kết luận nghiệp vụ thay vì chỉ giữ một biểu thức so sánh.
- **payableVnd** phân biệt kết quả phải trả với **subtotalVnd**.

Việc tách các phương thức private không phải để thỏa một ngưỡng số dòng. Chúng có **một nhiệm vụ có tên riêng** và cho phép đọc phương thức chính như một trình tự nghiệp vụ.

Nếu sau này chính sách phí phát triển thành nhiều biến thể thực, có thể cân nhắc truyền **ShippingFeePolicy** qua composition. **Chưa cần** tạo interface/factory chỉ vì có một quy tắc cố định trong ví dụ.

### 8.3. Unit test mô tả hợp đồng, không mô tả thứ tự dòng code

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderTotalCalculatorTest {

    @Test
    void chargesShippingBelowFreeThreshold() {
        var lines = List.of(new OrderLine(
                "SKU-01", new BigDecimal("100000"), 2));

        OrderSummary result = OrderTotalCalculator.summarize(lines);

        assertEquals(
                new BigDecimal("200000"), result.subtotalVnd());
        assertEquals(
                new BigDecimal("30000"), result.shippingFeeVnd());
        assertEquals(
                new BigDecimal("230000"), result.payableVnd());
    }

    @Test
    void shippingIsFreeAtExactThreshold() {
        var lines = List.of(new OrderLine(
                "SKU-01", new BigDecimal("250000"), 2));

        OrderSummary result = OrderTotalCalculator.summarize(lines);

        assertEquals(
                new BigDecimal("500000"), result.subtotalVnd());
        assertEquals(BigDecimal.ZERO, result.shippingFeeVnd());
        assertEquals(
                new BigDecimal("500000"), result.payableVnd());
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine(
                        "SKU-01", new BigDecimal("100000"), 0));
    }

    @Test
    void rejectsEmptyOrder() {
        assertThrows(
                IllegalArgumentException.class,
                () -> OrderTotalCalculator.summarize(List.of()));
    }
}
~~~

Tên test diễn đạt **điều gì phải đúng**. Các test vẫn có giá trị nếu bên trong **calculateSubtotalVnd(...)** đổi từ vòng lặp sang Stream, miễn là kết quả và hợp đồng giữ nguyên.

Cần phân biệt tên test có nghĩa với một quy tắc đặt tên duy nhất. Các dự án có thể dùng **should...When...**, **givenWhenThen** hoặc tên mô tả hành vi bằng lowerCamelCase. Chọn một phong cách nhóm đọc được, thay vì bắt buộc mọi test chứa đúng một từ khóa.

## 9. Cách tổ chức tên và biểu thức ảnh hưởng khả năng thay đổi

Quy ước không chỉ là vấn đề đọc một đoạn mã hôm nay; nó còn tác động đến thay đổi trong tương lai.

Giả sử chính sách miễn phí vận chuyển tăng ngưỡng từ 500.000 lên 700.000 đồng. Trong ví dụ trên, người bảo trì biết giá trị nằm ở **FREE_SHIPPING_THRESHOLD_VND** và kiểm tra các test liên quan. Nếu số tiền xuất hiện rải rác bằng con số **500000** ở controller, job báo cáo và UI, cần đi tìm các bản sao.

**Nhưng không phải mọi số lặp lại đều là cùng một khái niệm.** Ngưỡng phí vận chuyển và ngưỡng giảm giá có thể tình cờ cùng là 500.000 đồng hôm nay nhưng thay đổi độc lập. Không nên gom chúng vào **GLOBAL_THRESHOLD** chỉ để tránh lặp ký tự.

### Đặt tên theo “lý do thay đổi”

Một tên tốt giúp biết **ai sở hữu quy tắc** và **điều gì thay đổi khi nghiệp vụ đổi**:
- **FREE_SHIPPING_THRESHOLD_VND** thuộc chính sách vận chuyển.
- **MAX_ITEMS_PER_ORDER** thuộc giới hạn đơn hàng.
- **PAYMENT_REQUEST_TIMEOUT_MILLIS** thuộc ngân sách gọi cổng thanh toán.
- **ORDER_ID** là định danh đơn, không phải mã khách hàng.
- **refundAmount** khác **discountAmount** dù đều có kiểu BigDecimal.

Việc mô hình hóa đúng ranh giới quan trọng hơn tạo hằng số cho mọi số literal. **0** và **1** trong phép đếm đơn giản có thể rõ tự thân, trong khi **30.000 đồng phí** cần tên vì nó là chính sách có thể đổi.

## 10. Comment và Javadoc: diễn giải “tại sao”, không chép lại “làm gì”

Comment giúp lưu lại **ngữ cảnh, lý do, bất biến hoặc hạn chế** mà người đọc không dễ suy ra từ code. Nó không nên chỉ diễn giải lại cú pháp.

Ví dụ comment ít giá trị:

~~~java
// Cộng phí vận chuyển vào tổng.
payableVnd = subtotalVnd.add(shippingFeeVnd);
~~~

Người đọc đã thấy phép cộng. Comment nên giải thích lý do đặc biệt:

~~~java
// Đơn hàng đã xác nhận dùng phí vận chuyển được chốt lúc xác nhận;
// không tính lại theo biểu phí hiện tại khi chỉ hiển thị hóa đơn cũ.
BigDecimal shippingFeeVnd = order.confirmedShippingFeeVnd();
~~~

Comment thứ hai diễn đạt **bất biến nghiệp vụ và quyết định lưu dữ liệu lịch sử**. Nó giúp người sửa tránh vô tình “tối ưu” bằng cách tính lại với bảng phí hiện tại.

### Những loại thông tin đáng ghi lại

- Quy tắc không hiển nhiên được xác nhận bởi nghiệp vụ.
- Lý do phải giữ một thứ tự xử lý hoặc một bước kiểm tra.
- Tình huống tương thích với API hoặc dữ liệu cũ.
- Nguồn của một giá trị có thời hạn thay đổi, kèm tham chiếu tài liệu ổn định nếu có.
- Lý do chọn cấu trúc phức tạp hơn bình thường, nhất là sau đo hiệu năng.
- Ý nghĩa của phép tính có thuật toán/phân phối khó đọc.
- Hạn chế hoặc điều kiện mà một phương thức công khai yêu cầu.

### Khi nào cần Javadoc?

Javadoc đặc biệt hữu ích cho **public API**, thư viện dùng bởi nhiều module, hợp đồng không rõ chỉ từ chữ ký và các điều kiện lỗi/tác dụng phụ.

~~~java
/**
 * Tính thành tiền của dòng hàng theo đơn giá và số lượng.
 *
 * <p>Đơn giá cùng đơn vị VND, số lượng phải dương;
 * phép tính không đọc hoặc ghi dữ liệu bên ngoài.
 *
 * @return thành tiền của dòng hàng, không âm
 */
BigDecimal lineTotalVnd() {
    return unitPriceVnd.multiply(BigDecimal.valueOf(quantity));
}
~~~

Trong ví dụ, Javadoc có thể hơi chi tiết đối với một phương thức package-private nhỏ, nhưng minh họa **hợp đồng nên được mô tả**: đơn vị, tiền điều kiện, kết quả và tác dụng phụ. Không nhất thiết phải Javadoc mọi getter hoặc dòng code hiển nhiên.

**Cảnh báo:** Comment sai hoặc lỗi thời còn nguy hiểm hơn không có comment. Khi thay đổi quy tắc, phải cập nhật test, code và comment/Javadoc liên quan cùng nhau.

### TODO không phải kế hoạch thay đổi

Một TODO như **// TODO fix later** không nói gì về vấn đề và ưu tiên. Nếu cần ghi lại nợ kỹ thuật, nêu rõ:
- Hạn chế hiện tại.
- Rủi ro nếu chưa xử lý.
- Điều kiện hoặc công việc để sửa.
- Mã theo dõi hoặc chủ sở hữu khi quy trình nhóm yêu cầu.

Không nên dùng comment để hợp thức hóa mã khó hiểu mà không cố cải thiện tên hoặc cấu trúc trước.

## 11. Thống nhất từ ngữ trong lỗi, log và API

Quy ước cách diễn đạt còn xuất hiện ngoài tên Java:

- **Mã lỗi:** cùng một trạng thái nên có tên mã ổn định, ví dụ **ORDER_NOT_FOUND**.
- **Thông điệp lỗi:** dễ hiểu với người nhận, không lẫn ngôn ngữ hoặc khái niệm một cách bất ngờ.
- **Trường API:** cùng ý nghĩa phải dùng cùng tên và đơn vị, đặc biệt ở ranh giới công khai.
- **Log:** có trường định danh tương quan và tên hành động nhất quán, tránh ghi bí mật hoặc payload không cần thiết.
- **Sự kiện nghiệp vụ:** tên thể hiện điều đã xảy ra, không nhập nhằng với lệnh yêu cầu thực hiện.

Ví dụ giả định:

~~~json
{
  "code": "INVALID_QUANTITY",
  "field": "quantity",
  "message": "Số lượng phải lớn hơn 0",
  "requestId": "req-93a"
}
~~~

Định dạng trên là **một lựa chọn thiết kế**, không phải chuẩn bắt buộc mọi API. Điều quan trọng là **định nghĩa và giữ hợp đồng**: nơi này không nên trả JSON lỗi có mã, nơi khác lại trả HTTP 200 và chuỗi "FAILED" cho cùng kiểu thất bại nếu không có lý do tương thích.

### Nhất quán tên dữ liệu và đơn vị

**duration** là một tên yếu nếu không nói rõ đó là milliseconds, seconds hay một **Duration** theo kiểu dữ liệu. Trong Java có thể ưu tiên **java.time.Duration**, hoặc đặt tên **timeoutMillis** nếu buộc dùng số nguyên.

Tương tự, **createdAt** cần được hiểu là thời điểm trên trục thời gian hay giờ địa phương. Khi dữ liệu có ý nghĩa thời gian, có thể dùng **Instant**, **LocalDate** và **ZoneId** thay vì chỉ đổi hậu tố tên một cách không có hợp đồng.

Tên rõ giúp giảm nhầm lẫn, nhưng **kiểu dữ liệu và validation** vẫn cần bảo vệ bất biến. Một biến tên **amountVnd** nhưng chứa USD vẫn là lỗi.

## 12. Quy ước và tính tương thích: đừng đổi tên mù quáng

Đổi tên có thể rất dễ trong một phương thức private, nhưng là thay đổi đáng cân nhắc đối với:
- Public Java method hoặc class được module khác sử dụng.
- Thuộc tính JSON được client đọc.
- Tên cột cơ sở dữ liệu, khóa message broker hoặc schema sự kiện.
- Key cấu hình môi trường.
- Tên phương thức được gọi qua reflection hoặc framework convention.
- Nội dung log hoặc metric mà dashboard/cảnh báo đang phụ thuộc.

Một trường **customerCode** trong API v1 có thể không nên đổi thành **customerId** chỉ vì tên thứ hai đẹp hơn, nếu client đã phụ thuộc vào trường cũ hoặc hai khái niệm chưa được chứng minh tương đương.

Khi cần chuẩn hóa, có thể dùng **adapter**, ánh xạ trường, alias có thời hạn, versioning hoặc một kế hoạch migration. Điều kiện quyết định là tính đúng đắn và tương thích, không phải phong cách.

### Phân biệt quy ước mới và di sản cũ

Trong một codebase lâu đời, có thể tồn tại:
- Các package dùng tên cũ vì tương thích.
- Những lớp auto-generated có quy tắc đặt tên từ schema bên ngoài.
- Các API đối tác dùng chữ viết tắt không cùng phong cách Java.
- Những đoạn mã có ngoại lệ hiệu năng hoặc tương thích được chứng minh.

Cách ứng xử phù hợp là **làm rõ ranh giới của ngoại lệ**. Không nhất thiết sửa ngay mọi tên, nhưng cũng không nên sao chép ngoại lệ cũ như quy ước mặc định cho mã mới.

## 13. Khi nào không nên áp dụng quy tắc đặt tên một cách tuyệt đối?

### 13.1. Công thức toán học

Trong một thuật toán ngắn được giải thích rõ, ký hiệu **i**, **j**, **x**, **y** hoặc **n** có thể là cách truyền đạt tốt nếu chúng khớp định nghĩa toán học. Đổi mọi ký hiệu thành tên dài có thể khiến công thức khó đối chiếu với tài liệu.

Nhưng khi những biến ấy rời khỏi phạm vi ngắn và trở thành khái niệm nghiệp vụ, nên dùng tên mô tả ý nghĩa hơn.

### 13.2. Mã theo hợp đồng bên ngoài

Nếu thư viện hoặc API bên ngoài dùng trường **snake_case**, có thể phải giữ tên đó ở lớp DTO/serialization để tuân thủ hợp đồng. Ở mô hình miền nội bộ, Java vẫn có thể dùng lowerCamelCase và ánh xạ ở ranh giới.

Đừng cố đổi tên trường trên wire chỉ để làm code Java “đúng chuẩn”, vì khả năng tương thích quan trọng hơn thẩm mỹ tên.

### 13.3. Mã sinh tự động

Mã generated thường cần được **tạo lại từ schema hoặc template**. Sửa tay tên và định dạng trong tệp generated có thể bị ghi đè lần sinh sau. Nếu có vấn đề với quy ước, cần sửa nguồn sinh hoặc cấu hình generator khi được phép.

### 13.4. Mã hiệu năng cao

Một đoạn mã đã được đo là điểm nghẽn có thể dùng cấu trúc khác với phần còn lại, ví dụ vòng lặp tối ưu thay vì pipeline Stream. Điều đó không có nghĩa bỏ qua tên, comment, test hoặc quy ước cơ bản. **Ngoại lệ nên được giải thích bằng dữ liệu đo, ranh giới rõ và test giữ hợp đồng.**

### 13.5. Không nên “đặt tên cho mọi thứ”

Quá nhiều lớp, wrapper và interface tên dài có thể khiến việc tìm đúng hành vi khó hơn. Nếu một biểu thức ngắn đã rõ, trích thành phương thức có tên **doThing()** không cải thiện chất lượng.

Câu hỏi là **một tên mới có làm lộ thêm ý nghĩa và giảm số giả định không**, chứ không phải số lượng tên được tạo ra.

## 14. Công cụ và quy trình giữ quy ước thống nhất

Một quy ước chỉ có trong tài liệu nhưng không được áp dụng thường xuyên sẽ nhanh chóng bị quên. Quy trình hiệu quả kết hợp **thống nhất**, **tự động hóa** và **review có lý do**.

~~~mermaid
flowchart LR
    A[Thống nhất quy ước và ví dụ] --> B[IDE / EditorConfig]
    B --> C[Formatter và lint cục bộ]
    C --> D[Pull request]
    D --> E[CI kiểm tra format và static analysis]
    E --> F[Code review về ngữ nghĩa]
    F --> G[Merge]
    F --> H[Điều chỉnh quy ước khi có bằng chứng]
    H --> A
~~~

### Bước 1 — Xác định phạm vi và mục đích

Tài liệu ngắn nên trả lời:
- Quy ước áp dụng cho Java production, test, generated code hay tất cả?
- Formatter nào là nguồn sự thật cho định dạng?
- Những quy tắc đặt tên nào được kiểm tra tự động?
- Từ vựng nghiệp vụ nào cần thống nhất?
- Ngoại lệ được đề xuất và chấp nhận theo cách nào?

Không cần biến tài liệu thành bộ luật hàng trăm trang. Một vài ví dụ đúng/sai có giải thích thường hữu ích hơn các chỉ thị trừu tượng.

### Bước 2 — Chọn một formatter chính

Một dự án có thể dùng **google-java-format qua Spotless**, hoặc một cấu hình formatter thống nhất từ IDE/build tool. Tránh để nhiều công cụ định dạng cùng phần code theo các quy tắc xung đột.

**Quy tắc quan trọng:** Kết quả check trên máy phát triển và CI phải tương thích. Nếu CI luôn phát hiện lỗi định dạng mà IDE tự tạo ra, vấn đề nằm ở cấu hình quy trình, không phải do từng người không cẩn thận.

### Bước 3 — Kiểm tra các quy tắc tĩnh

Checkstyle hoặc công cụ phân tích tĩnh có thể phát hiện một số lỗi đặt tên, import, hoặc dấu ngoặc. Chỉ bật những quy tắc nhóm có thể giải thích mục đích và duy trì nhất quán.

Không biến mọi cảnh báo thành lỗi bắt buộc nếu quá nhiều false positive và chưa có cơ chế xử lý ngoại lệ. Cần ưu tiên cảnh báo có rủi ro thật về lỗi, bảo mật hoặc chi phí đọc hiểu.

### Bước 4 — Để code review tập trung vào ngữ nghĩa

Nếu formatter đã kiểm tra khoảng trắng, reviewer không cần lặp lại tranh luận về indent. Review nên hỏi:
- Tên phương thức có khớp tác dụng phụ không?
- Từ vựng có phù hợp miền nghiệp vụ không?
- Hai tên khác nhau có đang chỉ cùng một khái niệm, hoặc ngược lại?
- Có đơn vị, trạng thái hoặc điều kiện biên nào đang bị ngầm định?
- Biểu thức có diễn đạt đúng thứ tự ưu tiên nghiệp vụ không?
- Một comment có ghi lại lý do cần thiết và có còn đúng không?
- Thay đổi có làm hỏng hợp đồng API bên ngoài không?

### Bước 5 — Cập nhật quy ước theo bằng chứng

Nếu một quy tắc khiến code khó đọc trong một nhóm thuật toán cụ thể hoặc gây xung đột với framework, nên đánh giá và điều chỉnh ở phạm vi phù hợp. Tránh tình trạng mỗi người tự có ngoại lệ riêng mà không được giải thích; cũng tránh giữ quy tắc bất hợp lý chỉ vì đã tồn tại lâu.

## 15. Góp ý code review theo cách có thể hành động

Nhận xét chưa hữu ích:

> “Tên này xấu, viết clean code hơn đi.”

Nhận xét tốt hơn:

> “Biến **total** hiện chứa số tiền trước phí vận chuyển, trong khi response cũng có trường **total** sau phí. Có thể đổi biến nội bộ thành **subtotalVnd**, và đặt tên rõ giá trị trả về, để tránh dùng sai trong bước tính hóa đơn không?”

Nhận xét tốt hơn vì xác định **ý nghĩa**, **rủi ro sử dụng nhầm** và **đề xuất cụ thể**.

Một số ví dụ khác:

| Góp ý mơ hồ | Góp ý có căn cứ |
| --- | --- |
| “Hàm này dài quá.” | “Hàm vừa kiểm tra quyền vừa tính giá và ghi DB; khó test phép tính độc lập. Có thể tách tính giá thuần khỏi phần I/O không?” |
| “Đừng dùng magic number.” | “Giá trị 500000 là ngưỡng phí, có thể đổi theo chính sách. Đặt tên **FREE_SHIPPING_THRESHOLD_VND** sẽ làm rõ nơi cập nhật.” |
| “Phải dùng Stream.” | “Vòng lặp hiện thể hiện từng bước rất rõ. Nếu đề xuất Stream giúp đọc tốt hơn, hãy so sánh cách diễn đạt; nếu mục tiêu là hiệu năng, cần số đo.” |
| “Comment quá nhiều.” | “Comment này chỉ lặp lại phép cộng. Có thể bỏ và giữ comment về lý do chốt phí ở thời điểm xác nhận, vì đó mới là quy tắc khó suy ra.” |
| “Đổi hết URL thành Url.” | “Các tên công khai đang dùng **URL** và client có thể phụ thuộc; nên xác định quy ước cho mã mới, đánh giá tương thích trước khi đổi API cũ.” |
| “Tên bool không chuẩn.” | “**notEligible** kết hợp với phủ định gây khó đọc. Có thể dùng **eligible** nếu hai khái niệm thật sự là phủ định của nhau và đã có test biên không?” |

Ngôn ngữ review nên tránh biến sở thích cá nhân thành yêu cầu bắt buộc mà không có quy ước chung hoặc lý do kỹ thuật. Mục tiêu là cải thiện sản phẩm và giúp người viết hiểu **vì sao** nên đổi.

## 16. Những lỗi phổ biến cần nhận biết

| Dấu hiệu | Vấn đề tiềm ẩn | Cách xử lý nên cân nhắc |
| --- | --- | --- |
| **x**, **a1**, **tmp2** xuất hiện xuyên nhiều phương thức | Khó biết dữ liệu nào đang được xử lý | Đặt tên theo vai trò, đơn vị hoặc trạng thái |
| **total** có nơi trước thuế, nơi sau thuế | Cùng tên nhưng khác ý nghĩa | Phân biệt **subtotal**, **tax**, **payableAmount** |
| Tên phương thức **get...** nhưng ghi database | Tác dụng phụ khó dự đoán | Tách trách nhiệm hoặc mô tả hợp đồng rõ |
| Nhiều literal **500000** rải ở các nơi | Có thể trùng lặp quy tắc, khó thay đổi | Xác định hằng số/chính sách có chủ sở hữu |
| Mọi **500000** đều gom thành một hằng | Những chính sách độc lập bị liên kết | Tách theo lý do thay đổi, không theo giá trị trùng |
| Điều kiện có nhiều phủ định kép | Dễ nhầm logic | Xác định mệnh đề dương đúng nghĩa, thêm test |
| Một biểu thức rất dài nhiều toán tử | Khó đọc ưu tiên và điều kiện biên | Đặt tên cho kết luận, dùng ngoặc/bảng quyết định |
| Formatter sửa lại chính định dạng IDE tạo ra | Công cụ xung đột | Chọn nguồn sự thật, đồng bộ cấu hình |
| Comment giải thích cú pháp hiển nhiên | Tăng nhiễu và dễ lỗi thời | Bỏ hoặc chuyển sang ghi lý do/bất biến |
| Public field/API bị đổi tên chỉ để đồng bộ phong cách | Có thể phá tương thích | Đánh giá phụ thuộc và lộ trình migration |
| Test tên **test1**, **test2** | Không biết hành vi nào được bảo vệ | Đặt tên theo tình huống và kỳ vọng |
| Chỉ đếm độ dài tên hoặc số dòng | Đánh giá hình thức thay vì ý nghĩa | Kết hợp hợp đồng, độ rõ và phạm vi thay đổi |

Không phải mọi dấu hiệu đều chắc chắn là lỗi. Một biến **tmp** trong vài dòng xử lý thuật toán có thể chấp nhận được; một hàm dài nhưng tuyến tính có thể rõ hơn nhiều hàm con không có ý nghĩa. Cần điều tra bằng **bối cảnh**, không áp một công thức tuyệt đối.

## 17. Tình huống thực hành: sửa tên và biểu thức trong dịch vụ khuyến mại

Một pull request bổ sung kiểm tra miễn phí vận chuyển. Hiện có đoạn mã giả định:

~~~java
boolean a(boolean x, boolean y, BigDecimal z) {
    return x || y && z.compareTo(new BigDecimal("500000")) >= 0;
}
~~~

Tác giả giải thích:
- **x**: khách là PREMIUM.
- **y**: đơn còn hiệu lực.
- **z**: subtotal VND.
- Nguyên tắc nghiệp vụ: **đơn đã hủy không được miễn phí**; nếu đơn còn hiệu lực thì PREMIUM được miễn phí, khách thường được miễn khi subtotal từ 500.000 đồng.

### Câu hỏi

1. Biểu thức hiện tại có đáp ứng quy tắc “đơn đã hủy không được miễn phí” không?
2. Bạn sẽ đặt tên phương thức, tham số và hằng số thế nào?
3. Nên dùng một biểu thức boolean có ngoặc hay guard clause?
4. Những ca test nào cần có ở ngưỡng và theo trạng thái đơn?
5. Nếu quy tắc đã tồn tại ở một nơi khác, nên xử lý trùng lặp như thế nào?
6. Có cần lập tức tạo một framework policy với nhiều interface và factory không?

### Gợi ý phân tích

Biểu thức trên tương đương:

~~~java
return premium || (orderActive && reachedThreshold);
~~~

Khách PREMIUM vẫn được miễn phí ngay cả khi đơn không còn hiệu lực; đây là lỗi nếu hợp đồng cấm như vậy. Cách biểu đạt đúng theo quy tắc là:

~~~java
boolean qualifiesForFreeShipping =
        orderActive && (premium || reachedThreshold);
~~~

Ví dụ đặt tên rõ:

~~~java
private static final BigDecimal FREE_SHIPPING_THRESHOLD_VND =
        new BigDecimal("500000");

boolean qualifiesForFreeShipping(
        boolean orderActive,
        boolean premiumCustomer,
        BigDecimal subtotalVnd) {

    Objects.requireNonNull(subtotalVnd, "subtotalVnd");
    if (subtotalVnd.signum() < 0) {
        throw new IllegalArgumentException("negative subtotal");
    }

    boolean reachedThreshold =
            subtotalVnd.compareTo(FREE_SHIPPING_THRESHOLD_VND) >= 0;

    return orderActive && (premiumCustomer || reachedThreshold);
}
~~~

Tên **orderActive** ở đây chỉ chính xác nếu nghiệp vụ đã xác nhận nó tương đương với “đơn còn hiệu lực và chưa hủy” theo chính sách khuyến mại. Nếu còn trạng thái **PAID**, **REFUNDED**, **EXPIRED** với các quy tắc khác, nên dùng điều kiện nghiệp vụ cụ thể hơn thay vì một boolean dễ che giấu nhiều trạng thái.

Test nên có: **PREMIUM bị hủy**, **PREMIUM còn hiệu lực dưới ngưỡng**, **khách thường dưới ngưỡng**, **bằng ngưỡng**, **trên ngưỡng** và **subtotal âm**. Một biểu thức đẹp vẫn có thể sai nếu thiếu test trường hợp biên.

Nếu một chính sách tương tự được dùng ở nhiều kênh, cần xác định **nơi sở hữu quy tắc** và tránh sao chép tri thức. Nhưng không nên xây một framework trừu tượng lớn trước khi có nhiều policy với nhu cầu thay đổi thật.

## 18. Bài tập tự luyện

### Bài tập 1 — Cải thiện tên nhưng giữ hợp đồng

Cho mã:

~~~java
BigDecimal x = getA(order);
BigDecimal y = getB(order);
BigDecimal z = x.add(y);
send(z);
~~~

Giả sử **getA** trả thành tiền trước thuế, **getB** trả thuế, còn **send** gửi số tiền phải thu sang cổng thanh toán.

Hãy đặt lại tên cho các biến và phương thức để một người mới đọc có thể hiểu ý nghĩa. Phân biệt phần **tính toán** với phần **gửi lệnh thanh toán**, và nêu vì sao đổi tên **không tự bảo đảm công thức đúng**.

*Gợi ý:* Dùng **subtotal**, **taxAmount**, **payableAmount**, **calculate...**, **submitPayment...** khi đúng hợp đồng. Kiểm tra đơn vị tiền và những khoản phí còn thiếu trước khi kết luận.

### Bài tập 2 — Chọn quy ước định dạng

Hai thành viên dùng formatter khác nhau. Một người dùng 4 spaces, người khác dùng 2 spaces; mỗi lần mở pull request lại thấy hàng trăm dòng chỉ đổi indent.

Hãy đề xuất một quy trình để thống nhất cấu hình trong editor, build và CI, đồng thời xử lý các file cũ mà không che mất thay đổi chức năng.

*Gợi ý:* Chọn một nguồn sự thật, thử trên một số tệp đại diện, cập nhật hướng dẫn/CI, rồi tách đợt format lớn khỏi thay đổi nghiệp vụ.

### Bài tập 3 — Phân biệt tên khác nhau có cùng nghĩa

Trong ứng dụng, **clientId**, **userId** và **customerId** đang được dùng cho cùng dữ liệu ở ba lớp. Tuy nhiên, nhóm vận hành nói “client” đôi khi còn là tên một ứng dụng tích hợp.

Bạn nên hỏi những gì trước khi đổi tên? Đề xuất bảng thuật ngữ và vị trí chuyển đổi ở ranh giới để giảm nhầm lẫn.

*Gợi ý:* Không giả định ba tên luôn tương đương. Xác nhận ID thuộc thực thể nào, ai tạo và nguồn nào là thẩm quyền; cân nhắc tương thích khi đổi trường công khai.

### Bài tập 4 — Điều kiện boolean và trạng thái

Cho mã:

~~~java
boolean canShip =
        !orderNotPaid && (!addressMissing || express);
~~~

Hãy mô tả điều kiện bằng lời, sau đó hỏi xem **express** có thật sự được phép bỏ qua yêu cầu địa chỉ không. Viết phiên bản tên và biểu thức tốt hơn **sau khi xác nhận nghiệp vụ**, kèm hai test phát hiện nhầm thứ tự ưu tiên.

*Gợi ý:* Không thể tự suy ra quy tắc chỉ từ ý muốn “làm đẹp” tên. Một trường hợp express chưa có địa chỉ là ca biên quan trọng.

### Bài tập 5 — Comment về lý do

Một đoạn mã sử dụng **Instant** để tính thời điểm giao dịch, nhưng người viết thêm comment “lấy giờ hiện tại”, không ghi lý do chọn múi giờ. Nhóm báo cáo cần tổng hợp theo ngày địa phương của khách.

Hãy viết lại tên/kiểu dữ liệu và comment sao cho phân biệt **mốc thời gian tuyệt đối** với **ngày nghiệp vụ**, và đề xuất test cho trường hợp gần nửa đêm ở múi giờ mục tiêu.

*Gợi ý:* **Instant** không tự quyết định ngày theo khu vực; cần **ZoneId** và quy tắc định nghĩa ngày của báo cáo.

### Bài tập 6 — Review một PR có nhiều loại thay đổi

PR thay **total** thành **payableVnd**, thêm kiểm tra số lượng âm, tự động format lại toàn bộ package và đổi tên trường JSON công khai **total** thành **payableVnd**.

Hãy phân loại:
- Điều gì chỉ liên quan định dạng?
- Điều gì thay đổi hành vi?
- Điều gì có nguy cơ phá hợp đồng bên ngoài?
- Nên tách commit hoặc kiểm thử như thế nào?

*Gợi ý:* Đổi tên biến nội bộ khác đổi tên trường JSON; thêm validation là thay đổi hành vi; format diện rộng nên tách để review dễ.

## 19. Tự kiểm tra kiến thức

**Câu 1.** Nếu toàn bộ mã đi qua formatter, có thể kết luận hệ thống nhất quán về ý nghĩa và dễ bảo trì không?

*Trả lời:* Không. Formatter chủ yếu thống nhất hình thức. Từ vựng nghiệp vụ, hợp đồng, trách nhiệm, điều kiện biên và tác dụng phụ vẫn cần thiết kế/test/review.

**Câu 2.** Vì sao **subtotalVnd** có thể hữu ích hơn **total**?

*Trả lời:* Nó thể hiện loại tổng tiền và đơn vị, giảm nguy cơ nhầm với tổng sau phí hoặc sau thuế. Tuy nhiên tên phải khớp dữ liệu thật và chính sách tính toán.

**Câu 3.** Một field **final** có bắt buộc dùng **UPPER_SNAKE_CASE** không?

*Trả lời:* Không. Tên hằng thường theo quy ước UPPER_SNAKE_CASE, nhưng biến cục bộ final hoặc field tham chiếu không thay đổi không đương nhiên mang ý nghĩa hằng số. Phải xem loại giá trị và chuẩn dự án.

**Câu 4.** Có nên luôn đổi **if** sang một biểu thức ternary để giảm dòng?

*Trả lời:* Không. Một biểu thức ngắn chỉ tốt hơn khi làm ý định rõ hơn. Với nhiều điều kiện, nhánh hoặc tác dụng phụ, if/switch và bảng quyết định có thể dễ hiểu hơn.

**Câu 5.** Tại sao comment “cộng phí vào tổng” thường ít hữu ích hơn comment về lý do chốt phí tại thời điểm xác nhận?

*Trả lời:* Phép cộng đã thể hiện trong code; lý do chọn giá trị lịch sử là một quy tắc nghiệp vụ khó suy ra và cần được bảo vệ khi sửa đổi.

**Câu 6.** Có nên đổi mọi trường public API sang camelCase mới chỉ vì nhóm vừa thống nhất chuẩn?

*Trả lời:* Không nên đổi mù quáng. Cần xem client, serialization, phiên bản và kế hoạch tương thích; mã nội bộ và ranh giới công khai có các ràng buộc khác nhau.

**Câu 7.** Một boolean tên **notInactive** có thể đổi thành **active** ngay không?

*Trả lời:* Chỉ khi hai tên tương đương đúng theo mô hình trạng thái. “Không inactive” có thể còn bao gồm những trạng thái khác, nên cần kiểm tra hợp đồng.

**Câu 8.** Đoạn mã nhanh hơn 10% trong microbenchmark nhưng p99 của API không đổi. Có nên giữ phiên bản khó đọc hơn?

*Trả lời:* Chưa có cơ sở rõ. Cần xem điểm nghẽn của toàn luồng và đánh đổi bảo trì; cải thiện ở một phép tính không nhất thiết có tác động ở mức người dùng.

## Ghi nhớ

**Quy ước định dạng, đặt tên và cách diễn đạt** giúp người phát triển đọc mã theo các mẫu có thể dự đoán. Định dạng làm giảm tiếng ồn; tên gọi truyền đạt vai trò, đơn vị và thuật ngữ nghiệp vụ; cách diễn đạt làm lộ điều kiện, trình tự và tác dụng phụ. Trong Java, hãy sử dụng quy ước tên quen thuộc, công cụ format/lint thống nhất và test bảo vệ hành vi; đồng thời chọn tên và cấu trúc dựa trên **hợp đồng thực tế**, không dựa trên khẩu hiệu. Quy ước tốt được tự động hóa ở phần cơ học, được giải thích trong code review ở phần ngữ nghĩa và được điều chỉnh có chủ đích khi bối cảnh thay đổi.
