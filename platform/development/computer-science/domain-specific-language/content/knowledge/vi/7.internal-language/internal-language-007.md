# Giới hạn của ngữ pháp

## Ngữ pháp của DSL nội bộ phụ thuộc vào ngôn ngữ chủ

Ngôn ngữ chuyên miền (domain-specific language, DSL) nội bộ (internal DSL hoặc embedded DSL) được xây dựng bên trong một ngôn ngữ lập trình có sẵn. Người thiết kế cung cấp API, kiểu dữ liệu, hàm, lớp và các cấu trúc hỗ trợ để người dùng diễn đạt khái niệm của miền. Chương trình DSL vẫn được lexer, parser và compiler của ngôn ngữ chủ xử lý.

Điểm này tạo ra giới hạn quan trọng: **DSL nội bộ không thể tùy ý định nghĩa một ngữ pháp mới nằm ngoài những gì ngôn ngữ chủ cho phép**. Nó có thể tạo cảm giác như một ngôn ngữ riêng nhờ cách đặt tên và tổ chức API, nhưng cú pháp thực tế vẫn phải tuân theo quy tắc của host language.

Ví dụ, trong Java, một thư viện có thể cung cấp API fluent để viết:

```java
Rule freeShipping = rule("Free shipping")
    .when(allOf(
        orderTotal().atLeast(money(1_000_000, VND)),
        customerSegment().is(VIP)
    ))
    .then(set(shipmentFee(), money(0, VND)));
```

Thư viện có thể đặt tên hàm gần với ngôn ngữ nghiệp vụ, nhưng người dùng vẫn phải viết dấu chấm, dấu ngoặc, dấu phẩy, dấu chấm phẩy khi cần và tuân theo quy tắc biểu thức Java. Thư viện không thể thêm từ khóa `WHEN` hoặc tạo một câu lệnh mới với cấu trúc tùy ý như thể đó là một phần của Java.

Ngược lại, một DSL bên ngoài có frontend riêng có thể định nghĩa cú pháp:

```text
RULE "Free shipping"
WHEN order.total >= 1000000 VND
  AND customer.segment IS VIP
THEN shipment.fee = 0 VND
```

Hai biểu thức có thể mô tả cùng một quy tắc, nhưng chỉ biểu thức thứ hai được phân tích theo ngữ pháp riêng do DSL định nghĩa. Khi dùng DSL nội bộ, giới hạn của ngôn ngữ chủ cần được xem là một phần của quyết định thiết kế API.

## Ngữ pháp là gì trong bối cảnh này?

Ngữ pháp (grammar) là tập quy tắc xác định cách các thành phần nhỏ được kết hợp thành cấu trúc hợp lệ. Ở mức từ vựng, ngôn ngữ quy định token nào tồn tại: định danh, từ khóa, số, chuỗi, toán tử và dấu phân cách. Ở mức cú pháp, ngôn ngữ quy định các token được kết hợp thành biểu thức, câu lệnh, khai báo và khối lệnh như thế nào.

Một DSL nội bộ có thể thay đổi *cách dùng* các thành phần của host language thông qua thư viện, nhưng không thể thay đổi tùy ý:

- Những ký tự và token mà lexer của ngôn ngữ chủ nhận diện.
- Từ nào là từ khóa dành riêng và từ nào có thể dùng làm tên.
- Cấu trúc biểu thức và câu lệnh mà parser chấp nhận.
- Độ ưu tiên và tính kết hợp của toán tử.
- Vị trí có thể đặt lời gọi hàm, lambda, khai báo hoặc khối lệnh.
- Quy tắc dấu ngoặc, dấu phân cách, kết thúc câu lệnh và phạm vi.
- Quy tắc phân giải tên, overload, kiểu và đánh giá biểu thức của ngôn ngữ chủ.

Một API DSL tốt tận dụng những cấu trúc sẵn có một cách có chủ đích. Một API kém có thể khiến người dùng phải vật lộn với cú pháp chủ, viết nhiều dấu ngoặc hoặc đọc một chuỗi lời gọi khó hiểu.

## Những giới hạn cú pháp thường gặp

### Không thể tự tạo từ khóa mới

Từ khóa của ngôn ngữ chủ được xác định bởi đặc tả ngôn ngữ. Thư viện thông thường không thể biến một tên hàm thành từ khóa mới hoặc yêu cầu parser hiểu một cấu trúc chưa được định nghĩa.

Trong Java, `when`, `then` hay `rule` có thể được dùng làm tên phương thức nếu không xung đột với quy tắc định danh và từ khóa của phiên bản Java đang dùng. Tuy nhiên, chúng vẫn là identifier trong một biểu thức Java, không trở thành token cú pháp đặc biệt.

Ví dụ:

```java
rule("VIP discount")
    .when(customerIsVip())
    .then(applyDiscount(10));
```

Ở đây `rule`, `when` và `then` là các lời gọi phương thức. Compiler không hiểu chúng như cấu trúc ngữ pháp riêng của DSL; nó chỉ kiểm tra chúng theo quy tắc gọi phương thức Java.

Nếu người thiết kế muốn cú pháp `WHEN ... THEN ...` không có dấu ngoặc hay dấu chấm, cần một parser riêng hoặc một cơ chế mở rộng ngôn ngữ ở mức compiler. Khi văn bản DSL được đặt trong chuỗi rồi đưa cho parser riêng, phần nội dung chuỗi đã là một ngôn ngữ con có frontend riêng, dù nó được chứa trong mã Java.

### Không thể tự chọn dấu phân cách và ký hiệu

Một ngôn ngữ riêng có thể chọn dấu `:` để mở khối, từ khóa để kết thúc khối hoặc một ký hiệu đặc biệt để nối điều kiện. DSL nội bộ phải dùng những dấu mà host language cho phép trong vị trí cú pháp tương ứng.

Ví dụ, Java yêu cầu lời gọi hàm có dấu ngoặc:

```java
condition.and(otherCondition);
```

Không thể thay bằng cú pháp tùy ý như:

```text
condition AND otherCondition
```

trừ khi `AND` là một phương thức hoặc biểu thức được viết theo một cấu trúc Java hợp lệ. Ngay cả khi ngôn ngữ chủ hỗ trợ operator overloading, ký hiệu có thể dùng và cách parser hiểu nó vẫn do ngôn ngữ chủ quy định.

### Cú pháp lời gọi hàm có thể làm biểu thức dài

DSL nội bộ thường dựa vào lời gọi phương thức, builder hoặc hàm tạo. Mỗi lời gọi cần dấu ngoặc và có thể cần truyền tham số theo vị trí hoặc tên theo quy tắc của host language.

Một yêu cầu đơn giản có thể thành chuỗi lời gọi:

```java
query()
    .select(customerName())
    .from(orders())
    .where(orderStatus().is(PAID))
    .groupBy(customerId())
    .having(sum(orderTotal()).greaterThan(money(10_000_000, VND)))
    .execute();
```

Kiểu API này có thể dễ đọc với lập trình viên quen fluent API, nhưng nó vẫn mang hình dạng cú pháp của Java. Dấu ngoặc, dấu chấm và cách lồng lời gọi có thể làm biểu thức xa cách với cách chuyên gia miền mô tả yêu cầu.

### Không thể tự định nghĩa cấu trúc khối tùy ý

Một DSL bên ngoài có thể định nghĩa khối bằng từ khóa và quy tắc riêng. DSL nội bộ phải sử dụng cấu trúc khối mà ngôn ngữ chủ hỗ trợ, chẳng hạn lambda, closure, block hoặc hàm nhận callback.

Trong Java, một builder có thể dùng lambda:

```java
workflow("Order fulfillment", flow -> {
    flow.step("Validate order", this::validateOrder);
    flow.step("Capture payment", this::capturePayment);
    flow.step("Arrange shipment", this::arrangeShipment);
});
```

Lambda giúp biểu diễn nhóm thao tác và có thể làm DSL tự nhiên hơn. Tuy nhiên, dấu `{}`, dấu `;`, kiểu tham số và quy tắc return vẫn thuộc Java. Nếu DSL cần cú pháp khối không giống lambda Java, thư viện không thể tự thay đổi parser để tạo ra cú pháp đó.

### Quy tắc xuống dòng và kết thúc câu lệnh bị ràng buộc

Một số ngôn ngữ dùng xuống dòng để phân tách câu lệnh; một số ngôn ngữ yêu cầu dấu kết thúc; một số cho phép dấu chấm phẩy tùy chọn trong một số vị trí. DSL nội bộ phải chấp nhận chính sách của host language.

Trong Java, dấu chấm phẩy kết thúc nhiều câu lệnh. Xuống dòng thường chỉ có ý nghĩa định dạng và không tự động kết thúc một biểu thức theo cách người thiết kế DSL có thể tùy chỉnh. Điều này ảnh hưởng đến việc trình bày các quy tắc dài hoặc danh sách khai báo.

### Không thể tùy ý thay đổi độ ưu tiên toán tử

Độ ưu tiên (precedence) và tính kết hợp (associativity) xác định cách một biểu thức được nhóm khi không có dấu ngoặc. Ví dụ, trong nhiều ngôn ngữ, phép nhân được thực hiện trước phép cộng; phép so sánh có độ ưu tiên khác phép logic.

Nếu DSL nội bộ muốn ký hiệu `+`, `*`, `&&` hoặc `||` mang ý nghĩa khác, nó vẫn phải tuân theo độ ưu tiên và cách phân tích mà host language đã quy định. Một thư viện không thể yêu cầu parser nhóm biểu thức theo một bảng precedence riêng.

Ví dụ trong Java:

```java
boolean result = a || b && c;
```

Biểu thức được hiểu theo quy tắc Java là `a || (b && c)`. Một API DSL không thể đổi cách nhóm này. Nếu ý định nghiệp vụ cần một nhóm khác, người viết phải dùng dấu ngoặc hoặc cấu trúc hàm tường minh:

```java
boolean result = anyOf(a, allOf(b, c));
```

Trong ngôn ngữ có operator overloading, người thiết kế có thể thay đổi phép toán mà một toán tử thực hiện trên kiểu do mình định nghĩa, nhưng không nhất thiết thay đổi được precedence hoặc tính kết hợp của toán tử đó. Khả năng này phụ thuộc từng ngôn ngữ chủ.

## Giới hạn do đặc điểm của từng ngôn ngữ chủ

Mức độ tự do của DSL nội bộ khác nhau theo ngôn ngữ. Một số ngôn ngữ có cú pháp biểu thức linh hoạt, lambda ngắn, extension method hoặc operator overloading; một số ngôn ngữ có cú pháp lời gọi hàm chặt chẽ hơn.

| Ngôn ngữ chủ | Khả năng hỗ trợ DSL nội bộ | Giới hạn đáng chú ý |
|---|---|---|
| Java | Fluent API, builder, lambda, method reference, generic, annotation | Không có operator overloading do người dùng định nghĩa; cú pháp lời gọi hàm và dấu ngoặc khá rõ ràng; không thể thêm từ khóa hoặc câu lệnh mới bằng thư viện thông thường |
| Kotlin | Extension function, lambda with receiver, infix function, operator overloading, named argument | Vẫn tuân theo grammar Kotlin; từ khóa, precedence và cấu trúc câu lệnh do ngôn ngữ quy định; một số cú pháp DSL có thể gây khó hiểu nếu lồng receiver |
| Scala | Function, implicit/given, extension method, operator notation, flexible method syntax | Quy tắc parser, precedence theo ký tự toán tử và hệ kiểu có thể tạo độ phức tạp; người dùng cần hiểu các quy ước Scala |
| Ruby | Block, method chaining, symbol, dynamic dispatch, cú pháp gần ngôn ngữ tự nhiên | Tính linh hoạt có thể làm lỗi chỉ xuất hiện lúc chạy; DSL phụ thuộc quy ước và hành vi runtime; tên phương thức vẫn chịu cú pháp Ruby |
| Python | Function, decorator, context manager, operator overloading, fluent API | Không thể thêm cú pháp câu lệnh tùy ý bằng thư viện; indentation và grammar Python chi phối; nhiều lỗi cấu trúc hoặc kiểu có thể chỉ được phát hiện lúc chạy nếu không có công cụ bổ sung |

Bảng mô tả khả năng tổng quát của các ngôn ngữ; chi tiết cụ thể phụ thuộc phiên bản và thư viện. Không nên suy luận rằng có operator overloading hoặc extension function đồng nghĩa với việc có thể định nghĩa một ngữ pháp hoàn toàn mới.

## Giới hạn từ khóa và tên định danh

Host language có bộ quy tắc định danh riêng. Một từ có thể bị dành riêng, có ý nghĩa đặc biệt trong một ngữ cảnh hoặc gây xung đột với tên trong thư viện.

Khi thiết kế API DSL, cần xem xét:

- Tên hàm có trùng với từ khóa của ngôn ngữ chủ không?
- Tên miền có dễ nhầm với lớp, biến hoặc phương thức phổ biến không?
- Có cần tiền tố hoặc namespace để tránh xung đột không?
- Có thể dùng static import, extension method hoặc alias để làm tên ngắn hơn không?
- Tên có thể bị overload theo nhiều kiểu khiến lời gọi trở nên mơ hồ không?
- IDE có gợi ý đúng thành phần DSL hay hiển thị quá nhiều API không liên quan?

Ví dụ, trong Java, `record` trở thành từ khóa hạn chế từ Java 16; một API cần dùng tên tương thích với các phiên bản Java mục tiêu. Tên `when` có thể dùng như identifier trong Java nhưng có thể có ý nghĩa đặc biệt ở một ngôn ngữ chủ khác. Vì vậy, API DSL cần tuân theo phiên bản và quy tắc của môi trường biên dịch thực tế.

## Giới hạn do biểu thức và mô hình kiểu của ngôn ngữ chủ

Khả năng biểu đạt không chỉ bị giới hạn bởi ký tự và dấu phân cách. Cấu trúc biểu thức và hệ kiểu của host language cũng ảnh hưởng đến việc mô tả miền.

### Biểu thức và câu lệnh không giống nhau ở mọi ngôn ngữ

Một số ngôn ngữ cho phép hầu hết cấu trúc trả về giá trị; một số ngôn ngữ phân biệt rõ expression và statement. Nếu DSL muốn một khối quy tắc được dùng ở vị trí biểu thức nhưng ngôn ngữ chủ chỉ cho phép câu lệnh ở vị trí đó, người thiết kế phải dùng lambda, hàm hoặc wrapper phù hợp.

Ví dụ, trong Java, một lambda có thể là expression lambda hoặc block lambda:

```java
Function<Order, Boolean> eligible = order -> order.total().isPositive();

Consumer<Order> action = order -> {
    order.setPriority(Priority.HIGH);
    audit(order);
};
```

Kiểu lambda quyết định nó trả về giá trị hay thực hiện hành động. DSL cần thiết kế interface chức năng và chữ ký phương thức phù hợp với các vị trí sử dụng.

### Overload resolution có thể tạo ra lời gọi mơ hồ

DSL nội bộ thường dùng overload để tạo API ngắn gọn. Nhưng khi nhiều phương thức có cùng tên với các kiểu tham số gần nhau, compiler có thể không xác định được overload mong muốn hoặc người đọc khó đoán phương thức nào được gọi.

Ví dụ giả định:

```java
where(isEligible(null));
```

Nếu thư viện có nhiều overload nhận `Customer`, `Order` hoặc một kiểu khác, giá trị `null` có thể làm lời gọi mơ hồ. Tương tự, lambda không có kiểu tham số tường minh đôi khi khó phân giải khi có nhiều overload nhận các functional interface khác nhau.

Có thể giảm vấn đề bằng cách dùng tên phương thức khác nhau, kiểu wrapper rõ ràng, generic có giới hạn hoặc khai báo kiểu tường minh tại nơi gọi.

### Hệ kiểu chủ không nhất thiết khớp với kiểu miền

Một miền có các khái niệm như Money, Percentage, Temperature, Distance, AccountId hoặc OrderStatus. Nếu biểu diễn tất cả bằng `String`, `int` hoặc `double`, nhiều quy tắc miền không được thể hiện rõ trong kiểu.

DSL nội bộ có thể định nghĩa value object hoặc kiểu riêng để làm rõ:

```java
Money total = Money.of(1_000_000, Currency.VND);
Percentage discount = Percentage.of(10);
```

Điều này tăng khả năng kiểm tra kiểu nhưng vẫn phải tuân theo cú pháp khởi tạo đối tượng và phương thức của ngôn ngữ chủ. Một DSL bên ngoài có thể cho phép literal chuyên miền như `1000000 VND`, nhưng DSL nội bộ Java thông thường cần hàm tạo hoặc factory method để biểu diễn cùng ý tưởng.

### Generic và suy luận kiểu có giới hạn

Generic và type inference giúp API DSL ngắn gọn, nhưng các quy tắc suy luận kiểu của host language đôi khi không đủ để xác định kiểu mong muốn trong biểu thức lồng nhau. Người dùng có thể phải khai báo kiểu tường minh hoặc chia biểu thức thành biến trung gian.

Trong một API có nhiều lambda lồng nhau, kiểu của tham số có thể khó suy ra nếu chữ ký generic phức tạp. Việc thêm overload hoặc abstraction mới cũng có thể làm thay đổi cách compiler phân giải những lời gọi cũ.

## Giới hạn về ngữ nghĩa và thời điểm đánh giá

Ngay cả khi cú pháp API đọc tự nhiên, DSL nội bộ vẫn kế thừa cách ngôn ngữ chủ đánh giá biểu thức, gọi hàm và xử lý tác dụng phụ. Đây là giới hạn quan trọng vì ý nghĩa của DSL có thể bị ảnh hưởng bởi hành vi vốn không thuộc miền.

### Thứ tự đánh giá và short-circuit

Nếu DSL dùng toán tử logic của ngôn ngữ chủ, thứ tự đánh giá và short-circuit tuân theo ngôn ngữ đó. Nếu dùng hàm như `allOf(a(), b())`, cần xem xét các đối số được đánh giá trước khi gọi hàm hay được truyền dưới dạng lambda để trì hoãn.

Trong Java, lời gọi:

```java
allOf(checkInventory(), chargePayment());
```

sẽ đánh giá các đối số trước khi gọi `allOf`. Nếu `checkInventory()` trả về false, `chargePayment()` vẫn đã được gọi. Nếu ý định là chỉ thực hiện kiểm tra sau khi điều kiện trước đúng, API cần nhận `Supplier<Boolean>` hoặc một cấu trúc biểu thức không thực thi ngay.

Ví dụ dùng lambda:

```java
allOf(
    () -> checkInventory(),
    () -> chargePayment()
);
```

Ngay cả cách này cũng cần định nghĩa rõ thứ tự, short-circuit và tác dụng phụ. Không nên giả định tên hàm `allOf` tự động mang ý nghĩa giống toán tử `&&` của host language.

### Tác dụng phụ và tính khai báo

Một DSL quy tắc thường muốn biểu thức mô tả điều kiện và hành động, không thực hiện ngay khi tạo cấu hình. Nhưng nếu API sử dụng các hàm Java thông thường, lời gọi hàm có thể được thực thi ngay và tạo tác dụng phụ.

Ví dụ:

```java
rule("Payment")
    .when(paymentCaptured())
    .then(chargeCustomer());
```

Nếu `paymentCaptured()` và `chargeCustomer()` là các hàm thực thi ngay, quy tắc có thể chạy trong lúc xây dựng DSL thay vì lúc runtime của rule engine. API cần phân biệt rõ việc *tạo biểu thức* với việc *đánh giá biểu thức*, thường bằng các đối tượng mô tả, lambda trì hoãn hoặc AST.

### Khả năng phân tích chương trình bị ảnh hưởng

Nếu DSL nội bộ cho phép gọi bất kỳ hàm nào của host language, công cụ khó phân tích đầy đủ ý nghĩa chỉ từ cấu trúc API. Hàm có thể đọc tệp, gọi mạng, sửa trạng thái hoặc phụ thuộc vào dữ liệu bên ngoài.

Muốn phân tích tĩnh, tối ưu hóa hoặc kiểm tra chính sách, nhóm thường phải giới hạn API và lưu logic dưới dạng dữ liệu có cấu trúc. Điều này làm DSL dễ phân tích hơn nhưng cũng giới hạn khả năng gọi logic tùy ý.

## Các kỹ thuật giảm bớt giới hạn ngữ pháp

Không thể xóa bỏ giới hạn của host language bằng một thư viện thông thường, nhưng có thể thiết kế API để giảm tác động của chúng.

### Fluent API và method chaining

Fluent API tổ chức các lời gọi phương thức theo chuỗi, trong đó mỗi phương thức trả về đối tượng cho phép gọi bước tiếp theo.

```java
query()
    .from(orders())
    .where(status().is(PAID))
    .orderBy(createdAt().descending())
    .limit(20);
```

Cách viết này tạo nhịp đọc gần với một câu mô tả, giảm biến trung gian và giúp IDE gợi ý bước tiếp theo. Cần tránh chuỗi quá dài, tên phương thức không nhất quán hoặc trạng thái builder cho phép gọi sai thứ tự.

### Builder pattern và kiểu theo trạng thái

Builder pattern giúp chia việc tạo cấu trúc phức tạp thành từng bước. Có thể dùng kiểu trả về khác nhau để giới hạn bước tiếp theo:

```java
interface RuleStart {
    RuleCondition when(Condition condition);
}

interface RuleCondition {
    RuleAction then(Action action);
}

interface RuleAction {
    Rule build();
}
```

Người dùng phải gọi `when` trước `then`, rồi mới `build`. Cách thiết kế này dùng hệ kiểu Java để loại bỏ một số trạng thái không hợp lệ ngay lúc biên dịch. Nó không thay đổi grammar Java, nhưng tận dụng grammar và type system để tạo API có trình tự rõ.

### Lambda và closure

Lambda có thể biểu diễn phạm vi hoặc nhóm hành động:

```java
workflow("Order")
    .step("Validate", order -> validate(order))
    .step("Ship", order -> arrangeShipment(order));
```

Trong ngôn ngữ có lambda with receiver hoặc closure linh hoạt hơn, cú pháp có thể gần DSL riêng hơn. Tuy nhiên, cách viết vẫn bị giới hạn bởi quy tắc của host language và kiểu callback mà API định nghĩa.

### Static import, extension method và alias

Một số ngôn ngữ cho phép đưa hàm hoặc extension method vào phạm vi để giảm tiền tố và làm biểu thức gọn hơn. Java có static import; Kotlin có extension function; các ngôn ngữ khác có module import hoặc namespace alias.

Những kỹ thuật này giúp giảm nhiễu cú pháp nhưng không tạo ra cấu trúc ngữ pháp mới. Cần cân nhắc nguy cơ xung đột tên và khả năng người đọc xác định hàm đến từ đâu.

### Operator overloading khi host language hỗ trợ

Ngôn ngữ như Kotlin, Scala, Python hoặc C++ cho phép một số dạng operator overloading. Điều này có thể giúp biểu thức DSL gần với ký hiệu toán học hoặc logic hơn.

Ví dụ giả định trong ngôn ngữ hỗ trợ overload:

```text
order.total >= minimumTotal && customer.isVip()
```

Các toán tử có thể được ánh xạ sang phương thức trên kiểu miền. Tuy nhiên, operator overloading không cho phép tự chọn mọi ký hiệu, không nhất thiết thay đổi precedence và có thể làm ý nghĩa toán tử trở nên bất ngờ. Nên dùng khi phép toán phù hợp với trực giác của người đọc.

### Annotation, decorator và metadata

Annotation hoặc decorator cho phép gắn metadata lên lớp, hàm hoặc thành phần chương trình:

```java
@RuleDefinition(name = "VIP discount")
@When("customer.segment == VIP")
@Then("discount.rate = 10")
public class VipDiscountRule {
}
```

Đây chỉ là ví dụ minh họa. Annotation giúp khai báo cấu hình theo dạng metadata, nhưng chuỗi bên trong annotation vẫn có cú pháp do parser riêng hoặc logic thư viện xử lý. Annotation processor có thể kiểm tra một số điều kiện ở compile time, nhưng không tự thay đổi ngữ pháp Java.

## Khi nào nên chuyển từ DSL nội bộ sang DSL bên ngoài?

Nếu nhóm liên tục phải tìm cách lách cú pháp host language, đó có thể là dấu hiệu DSL nội bộ không còn phù hợp với nhu cầu.

Những dấu hiệu thường gặp:

- Người dùng phải viết nhiều dấu ngoặc, lời gọi builder hoặc kiểu wrapper cho một quy tắc đơn giản.
- Cú pháp Java hoặc ngôn ngữ chủ khiến chuyên gia miền không thể đọc hoặc tự chỉnh sửa.
- Cần từ khóa, cấu trúc khối, literal hoặc toán tử chuyên miền mà host language không hỗ trợ tự nhiên.
- Cần kiểm tra và phân tích chương trình độc lập với compiler hoặc runtime của ngôn ngữ chủ.
- Cùng một ngôn ngữ cần chạy trên nhiều nền tảng hoặc backend.
- Logic DSL cần được lưu thành tệp dữ liệu, review và quản lý phiên bản độc lập với mã ứng dụng.
- API nội bộ ngày càng phức tạp vì phải mô phỏng một grammar khác bằng lời gọi phương thức.

Chuyển sang DSL bên ngoài đồng nghĩa phải đầu tư lexer/parser, AST, semantic analyzer, diagnostics, formatter và công cụ hỗ trợ. Vì vậy, không nên chuyển chỉ vì cú pháp nội bộ chưa đẹp. Cần đánh giá lợi ích về khả năng đọc, kiểm tra, quản lý và độc lập triển khai so với chi phí xây dựng frontend.

## Phân biệt DSL nội bộ với DSL bên ngoài được nhúng trong chuỗi

Một trường hợp dễ nhầm là mã Java chứa một chuỗi có cú pháp riêng:

```java
String ruleText = """
    RULE "VIP discount"
    WHEN customer.segment IS VIP
    THEN discount.rate = 10%
    """;

Rule rule = dslParser.parse(ruleText);
```

Phần Java bên ngoài là ngôn ngữ chủ; nội dung `ruleText` được parser riêng phân tích theo grammar của DSL. Đây là **DSL bên ngoài được nhúng hoặc truyền qua chuỗi**, không phải internal DSL thuần túy chỉ dựa trên cú pháp Java.

Sự phân biệt này quan trọng vì parser riêng có thể định nghĩa từ khóa và cấu trúc tùy ý bên trong chuỗi, nhưng phải tự chịu trách nhiệm về lỗi cú pháp, vị trí nguồn, kiểm tra kiểu và tích hợp IDE. Mã Java chỉ đóng vai trò nạp, cấu hình hoặc gọi frontend của DSL.

Một cách khác là dùng annotation processor, compiler plugin hoặc macro system nếu host language và công cụ cho phép. Các cơ chế này có thể mở rộng hoặc biến đổi mã ở một số giai đoạn, nhưng chúng có giới hạn riêng, phụ thuộc compiler và không nên được xem như khả năng tự do thay đổi grammar của mọi chương trình.

## Quy trình thiết kế DSL nội bộ có xét đến giới hạn grammar

Để tránh xây dựng một API đẹp trên giấy nhưng khó dùng trong ngôn ngữ chủ, hãy thiết kế từ các ví dụ sử dụng thực tế.

1. **Xác định người viết và người đọc:** lập trình viên, chuyên gia miền hay cả hai; họ có quen ngôn ngữ chủ không?
2. **Thu thập tác vụ đại diện:** chọn quy tắc phổ biến, trường hợp phức tạp và tình huống ngoại lệ.
3. **Viết thử biểu thức bằng cú pháp host language:** dùng các cấu trúc có thật như method call, lambda, builder hoặc operator overloading được hỗ trợ.
4. **Đánh dấu phần cú pháp gây nhiễu:** xác định dấu ngoặc, dấu chấm, kiểu tham số hoặc cấu trúc lồng nhau nào làm ý định khó đọc.
5. **Chọn abstraction phù hợp:** fluent API, builder, lambda, extension method, kiểu miền hoặc cấu trúc khai báo.
6. **Kiểm tra giới hạn parser và type system:** không giả định thư viện có thể thay đổi từ khóa, precedence, scope hoặc cách compiler suy luận kiểu.
7. **Kiểm tra ngữ nghĩa và thời điểm đánh giá:** phân biệt tạo biểu thức với thực thi, xác định thứ tự đánh giá và tác dụng phụ.
8. **Thử với người dùng mục tiêu:** yêu cầu họ đọc, viết, sửa và giải thích biểu thức mà không có tác giả bên cạnh.
9. **Đánh giá ngưỡng chuyển đổi:** nếu cú pháp chủ cản trở rõ rệt, so sánh chi phí của DSL bên ngoài hoặc mô hình kết hợp.

Ví dụ, nếu các biểu thức Java trở nên dài vì phải lồng nhiều `allOf`, `anyOf` và `not`, nhóm có thể cải tiến tên API hoặc dùng builder có cấu trúc. Nếu người dùng cần cú pháp gần như câu tiếng Anh hoặc tiếng Việt, thay đổi tên hàm có thể chưa đủ; lúc đó nên thử một grammar riêng.

## Kết luận

Giới hạn của ngữ pháp là một ràng buộc cốt lõi khi xây dựng DSL nội bộ. DSL nội bộ có thể tạo từ vựng và API chuyên miền, tận dụng kiểu dữ liệu, hàm, lambda và công cụ của ngôn ngữ chủ, nhưng vẫn phải tuân theo token, từ khóa, dấu phân cách, cấu trúc biểu thức, độ ưu tiên toán tử và quy tắc đánh giá của host language.

Những kỹ thuật như fluent API, builder, lambda, extension method, static import và operator overloading có thể làm cách diễn đạt tự nhiên hơn trong phạm vi ngôn ngữ cho phép. Khi yêu cầu về cú pháp, người dùng hoặc khả năng phân tích vượt quá giới hạn đó, DSL bên ngoài có frontend riêng có thể là lựa chọn phù hợp. Quyết định nên dựa trên các biểu thức thực tế, mức độ dễ hiểu, khả năng kiểm tra và chi phí sở hữu lâu dài.
