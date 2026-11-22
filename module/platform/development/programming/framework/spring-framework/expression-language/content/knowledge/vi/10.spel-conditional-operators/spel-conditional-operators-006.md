# Phân biệt giá trị mặc định với xử lý lỗi

Trong Spring Expression Language (SpEL), biểu thức có thể nhận dữ liệu null, thiếu thông tin hoặc gặp lỗi khi đánh giá. Một cách xử lý phổ biến là cung cấp giá trị mặc định để biểu thức vẫn tạo được kết quả. Tuy nhiên, **giá trị mặc định và xử lý lỗi là hai việc khác nhau**.

Giá trị mặc định dùng khi dữ liệu hợp lệ về mặt cấu trúc nhưng chưa có giá trị hoặc đang ở trạng thái được quy ước là có thể thay thế. Xử lý lỗi dùng khi một thao tác không thể thực hiện đúng, chẳng hạn biểu thức sai cú pháp, property không tồn tại, chuyển đổi kiểu thất bại hoặc method ném exception.

SpEL cung cấp toán tử Elvis, toán tử điều kiện và safe navigation để xử lý một số trường hợp thiếu dữ liệu. Những toán tử này không thay thế cơ chế bắt và xử lý exception của ứng dụng.

## 1. Phân biệt hai mục tiêu

Giả sử ứng dụng cần lấy tên khách hàng để hiển thị. Nếu tên chưa được cung cấp, có thể dùng giá trị mặc định như Guest. Đây là trường hợp fallback:

~~~java
customerName ?: 'Guest'
~~~

Nhưng nếu biểu thức tham chiếu một property không tồn tại hoặc gọi method bị lỗi, việc cung cấp Guest không tự động bắt được lỗi đó.

Có thể phân biệt như sau:

| Tình huống | Mục tiêu | Cách xử lý phù hợp |
|---|---|---|
| Giá trị là null | Cung cấp giá trị thay thế | Elvis hoặc toán tử điều kiện |
| Chuỗi rỗng | Dùng nội dung thay thế theo quy tắc | Elvis hoặc kiểm tra chuỗi tường minh |
| Chuỗi chỉ có khoảng trắng | Chuẩn hóa hoặc dùng mặc định | Kiểm tra isBlank/trim |
| Boolean là false | Giữ nguyên false nếu đó là giá trị hợp lệ | Không coi false là null |
| Property không tồn tại | Sửa tên property hoặc model/accessor | Kiểm tra lỗi evaluate |
| Biểu thức sai cú pháp | Sửa biểu thức | Bắt ParseException |
| Method ném exception | Xử lý lỗi nghiệp vụ hoặc kỹ thuật | Bắt exception ở tầng Java |
| Chuyển đổi kiểu thất bại | Bổ sung converter hoặc sửa kiểu dữ liệu | Xử lý lỗi chuyển đổi |

Không nên dùng một giá trị mặc định để che giấu mọi lỗi. Nếu property bị viết sai tên, trả về Guest có thể khiến ứng dụng tiếp tục chạy với dữ liệu sai mà không ai nhận ra nguyên nhân.

## 2. Toán tử Elvis (?:)

### 2.1. Cú pháp

Elvis operator là cách viết ngắn để cung cấp giá trị thay thế khi vế trái không có giá trị phù hợp:

~~~java
customerName ?: 'Guest'
~~~

Nếu customerName có giá trị được chấp nhận, SpEL trả về giá trị đó. Nếu giá trị thuộc trường hợp fallback, SpEL trả về Guest.

Ví dụ với biến trong EvaluationContext:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customerName", null);

String name = parser
        .parseExpression("#customerName ?: 'Guest'")
        .getValue(context, String.class);
~~~

Kết quả là Guest.

Biến SpEL được tham chiếu bằng dấu #. Giá trị của biến được cung cấp từ Java trước khi đánh giá biểu thức.

### 2.2. Elvis với null và chuỗi rỗng

Elvis được dùng phổ biến để cung cấp mặc định khi giá trị là null. Từ Spring Framework 4.3, Elvis operator cũng dùng nhánh mặc định khi vế trái là chuỗi rỗng.

Ví dụ:

~~~java
#name ?: 'Unknown'
~~~

Các trường hợp:

| Giá trị của name | Kết quả |
|---|---|
| null | Unknown |
| Chuỗi rỗng | Unknown |
| An | An |
| An Nguyen | An Nguyen |
| Chuỗi chỉ có dấu cách | Chuỗi dấu cách vẫn được giữ |

Chuỗi chỉ có khoảng trắng không giống chuỗi rỗng. Nếu nghiệp vụ muốn coi cả chuỗi trắng là không có nội dung, cần kiểm tra tường minh:

~~~java
#name == null || #name.trim().isEmpty()
    ? 'Unknown'
    : #name
~~~

Trong ví dụ trên, toán tử OR đánh giá ngắn mạch. Khi name là null, vế trim không được đánh giá.

Nếu ứng dụng dùng Java 11 trở lên, có thể gọi isBlank() để kiểm tra chuỗi rỗng hoặc chỉ chứa whitespace:

~~~java
#name == null || #name.isBlank()
    ? 'Unknown'
    : #name
~~~

Hãy chọn quy tắc phù hợp với phiên bản Java và Spring của ứng dụng.

### 2.3. Elvis không thay thế mọi giá trị falsy

Elvis không có nghĩa là “nếu vế trái không đúng thì dùng mặc định”. Một giá trị Boolean false vẫn là một giá trị có thật và không phải null.

Ví dụ:

~~~java
#enabled ?: true
~~~

Nếu enabled là false, kết quả vẫn là false. Đây là hành vi cần thiết khi false có ý nghĩa nghiệp vụ riêng.

Nếu muốn xử lý null thành true nhưng vẫn giữ false, Elvis là lựa chọn phù hợp. Nếu muốn mọi trường hợp false hoặc null đều thành true, cần viết điều kiện theo đúng quy tắc đó:

~~~java
#enabled == null || !#enabled ? true : #enabled
~~~

Tuy nhiên, hãy tránh biểu thức dài nếu có thể đặt tên cho trạng thái ở tầng Java.

Elvis cũng không mặc nhiên coi list rỗng, map rỗng, số 0 hoặc collection không có phần tử là null. Nếu cần fallback cho những trường hợp đó, hãy kiểm tra điều kiện riêng như isEmpty() hoặc so sánh với 0.

### 2.4. Dùng Elvis cho property

Khi property có thể null, có thể cung cấp giá trị mặc định:

~~~java
order.note ?: 'No note'
~~~

Hoặc kết hợp với root object:

~~~java
customer.displayName ?: customer.username
~~~

Biểu thức thứ hai dùng username khi displayName thuộc trường hợp fallback. Tuy nhiên, nếu customer có thể null thì cần xử lý customer trước:

~~~java
customer?.displayName ?: 'Guest'
~~~

Safe navigation và Elvis giải quyết hai vấn đề liên tiếp: safe navigation tránh truy cập property trên receiver null; Elvis chọn giá trị thay thế khi kết quả là null hoặc chuỗi rỗng theo semantics của phiên bản Spring.

## 3. Toán tử điều kiện ba ngôi (ternary)

### 3.1. Cú pháp

Toán tử điều kiện có dạng:

~~~java
condition ? valueIfTrue : valueIfFalse
~~~

SpEL đánh giá condition trước. Nếu condition đúng, biểu thức trả về valueIfTrue; nếu sai, trả về valueIfFalse.

Ví dụ:

~~~java
order.total >= 100 ? 'VIP' : 'STANDARD'
~~~

Có thể đánh giá:

~~~java
String category = parser
        .parseExpression(
                "order.total >= 100 ? 'VIP' : 'STANDARD'"
        )
        .getValue(context, String.class);
~~~

Ternary phù hợp khi cần lựa chọn giữa hai kết quả theo một điều kiện nghiệp vụ.

### 3.2. Dùng ternary để cung cấp mặc định

Có thể viết fallback bằng ternary:

~~~java
#name != null ? #name : 'Guest'
~~~

Cách này chỉ thay thế null, còn chuỗi rỗng vẫn được giữ nguyên. Đây là điểm khác với Elvis trong các phiên bản Spring hỗ trợ fallback cho chuỗi rỗng.

So sánh:

~~~java
#name ?: 'Guest'
~~~

và:

~~~java
#name != null ? #name : 'Guest'
~~~

Hai biểu thức có thể cho kết quả khác nhau khi name là chuỗi rỗng. Hãy chọn cú pháp dựa trên định nghĩa “không có giá trị” của nghiệp vụ.

### 3.3. Kiểm tra nhiều trường hợp

Ternary có thể dùng để phân loại:

~~~java
order.total > 1000
    ? 'LARGE'
    : (order.total > 0 ? 'NORMAL' : 'EMPTY')
~~~

Biểu thức trên có ba kết quả:

- LARGE nếu tổng tiền lớn hơn 1000.
- NORMAL nếu tổng tiền lớn hơn 0 nhưng không vượt quá 1000.
- EMPTY trong các trường hợp còn lại.

Ternary lồng nhau có thể trở nên khó đọc. Nếu có nhiều nhánh, hãy cân nhắc method Java hoặc một cấu trúc quyết định ở tầng nghiệp vụ.

### 3.4. Ternary chỉ đánh giá nhánh được chọn

Sau khi condition được đánh giá, SpEL chỉ đánh giá nhánh kết quả tương ứng. Nhánh còn lại không được thực thi.

Điều này hữu ích khi nhánh được chọn phụ thuộc vào dữ liệu có thể null:

~~~java
order.customer != null
    ? order.customer.name
    : 'Guest'
~~~

Khi customer null, nhánh truy cập name không được đánh giá.

Không nên đưa hành động có tác dụng phụ vào nhánh ternary. Hãy giữ các nhánh là biểu thức trả về giá trị để kết quả dễ kiểm thử và dự đoán.

## 4. Safe navigation (?.) kết hợp với giá trị mặc định

### 4.1. Safe navigation xử lý receiver null

Toán tử safe navigation giúp truy cập property hoặc gọi method mà không phát sinh lỗi chỉ vì receiver đang null:

~~~java
order.customer?.name
~~~

Nếu customer null, biểu thức trả về null thay vì tiếp tục truy cập name trên giá trị null.

Có thể kết hợp với Elvis:

~~~java
order.customer?.name ?: 'Guest'
~~~

Luồng xử lý:

1. Truy cập customer của order.
2. Nếu customer null, safe navigation trả về null.
3. Nếu customer tồn tại, đọc name.
4. Nếu kết quả thuộc trường hợp fallback, Elvis trả về Guest.

Với nhiều cấp nullable, cần đặt safe navigation ở các điểm có thể null:

~~~java
order.customer?.profile?.displayName ?: 'Guest'
~~~

### 4.2. Safe navigation không bắt mọi exception

Safe navigation chỉ bảo vệ việc truy cập qua receiver null tại vị trí dùng toán tử. Nó không xử lý tất cả loại lỗi.

Ví dụ, các lỗi sau vẫn có thể xuất hiện:

- Property không tồn tại.
- Method không tồn tại hoặc không truy cập được.
- Method được gọi ném exception.
- Chuyển đổi kiểu thất bại.
- Toán tử hoặc phép tính không hợp lệ.
- Biểu thức có cú pháp sai.

Vì vậy, biểu thức:

~~~java
order.customer?.unknownProperty ?: 'Guest'
~~~

không nên được xem là cách bắt lỗi property sai tên. Safe navigation không biến một property không tồn tại thành null. Elvis chỉ có thể xử lý kết quả mà phần bên trái đánh giá thành công.

### 4.3. Phân biệt null receiver với lỗi nghiệp vụ

Giả sử ứng dụng có một customer nhưng customer bị khóa. Safe navigation không có nghĩa là khách hàng bị khóa sẽ được thay bằng Guest. Đó là hai trạng thái khác nhau:

- Không có customer: dữ liệu thiếu, có thể dùng fallback nếu nghiệp vụ cho phép.
- Có customer nhưng bị khóa: trạng thái nghiệp vụ cần được xử lý riêng.

Ví dụ:

~~~java
order.customer?.name ?: 'Guest'
~~~

chỉ tạo tên hiển thị dự phòng. Nó không quyết định customer có được phép đặt hàng hay không.

## 5. Giá trị mặc định không phải xử lý lỗi

### 5.1. Lỗi parse

Lỗi parse xảy ra khi chuỗi không đúng cú pháp SpEL:

~~~java
order.total >= ? 'VIP' : 'STANDARD'
~~~

Parser không thể tạo Expression hợp lệ. Elvis hoặc ternary không thể bắt lỗi này vì biểu thức chưa được parse thành công.

Cần bắt ParseException tại bước parse:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
} catch (ParseException ex) {
    // Báo biểu thức không đúng cú pháp.
    throw new IllegalArgumentException(
            "Invalid SpEL syntax at position " + ex.getPosition(),
            ex
    );
}
~~~

### 5.2. Lỗi evaluate

Biểu thức có thể đúng cú pháp nhưng thất bại khi đánh giá:

~~~java
order.unknownProperty ?: 'Guest'
~~~

Nếu unknownProperty không tồn tại, SpEL có thể ném lỗi truy cập property. Elvis không tự động bắt lỗi đó để trả về Guest.

Cần kiểm tra model, property accessor và cấu hình context. Nếu lỗi là do dữ liệu hoặc quy tắc nghiệp vụ, xử lý theo chính sách tương ứng.

### 5.3. Method ném exception

Ví dụ:

~~~java
order.calculateTax() ?: 0
~~~

Elvis có thể dùng 0 nếu method đánh giá thành công và trả về null hoặc chuỗi rỗng trong trường hợp áp dụng. Nhưng nếu calculateTax() ném exception, vế phải không phải cơ chế catch exception. Lỗi vẫn truyền ra ngoài.

Nếu cần xử lý exception, hãy bắt tại tầng Java:

~~~java
try {
    BigDecimal tax = parser
            .parseExpression("order.calculateTax()")
            .getValue(context, BigDecimal.class);
} catch (EvaluationException ex) {
    // Ghi nhận và xử lý lỗi đánh giá theo chính sách ứng dụng.
}
~~~

Không nên thay mọi lỗi tính thuế bằng 0 nếu điều đó có thể khiến hóa đơn hoặc báo cáo tài chính sai. Giá trị mặc định phải được nghiệp vụ cho phép.

## 6. Chọn cách xử lý theo từng tình huống

| Tình huống | Cách viết hoặc cơ chế | Ý nghĩa |
|---|---|---|
| Null cần fallback | **value ?: default** | Trả về mặc định khi không có giá trị |
| Null hoặc chuỗi rỗng cần fallback | **value ?: default** trong Spring 4.3+ | Chuỗi rỗng cũng dùng nhánh mặc định |
| Chỉ null cần fallback, chuỗi rỗng giữ nguyên | **value != null ? value : default** | Phân biệt null và empty |
| Chuỗi trắng cần fallback | Kiểm tra **isBlank()** hoặc **trim().isEmpty()** | Áp dụng quy tắc blank riêng |
| Chọn một trong hai kết quả | **condition ? a : b** | Điều kiện đúng/sai |
| Receiver có thể null | **object?.property** | Tránh truy cập property trên null |
| Property không tồn tại | Kiểm tra model/accessor | Sửa lỗi truy cập |
| Method ném exception | try/catch ở Java | Xử lý lỗi đánh giá |
| Biểu thức sai cú pháp | Bắt ParseException | Xử lý lỗi parse |

## 7. Không che giấu lỗi bằng fallback quá rộng

Một biểu thức như:

~~~java
order.customer?.name ?: 'Guest'
~~~

có thể phù hợp cho màn hình hiển thị tên. Nhưng không nên dùng nó làm căn cứ xác thực danh tính khách hàng hoặc quyết định quyền truy cập.

Nếu customer null vì dữ liệu bị thiếu ngoài dự kiến, mặc định Guest có thể làm hệ thống tiếp tục với một đối tượng không đúng. Hãy phân biệt rõ:

- **Fallback hiển thị:** dùng chuỗi thay thế để giao diện không bị trống.
- **Fallback nghiệp vụ:** thay thế giá trị khi quy tắc đã định nghĩa rõ trường hợp đó.
- **Validation:** xác nhận dữ liệu bắt buộc tồn tại và hợp lệ.
- **Error handling:** ghi nhận, chuyển đổi hoặc xử lý exception theo chính sách ứng dụng.

Ví dụ, tên hiển thị có thể có fallback:

~~~java
order.customer?.displayName ?: 'Khách hàng'
~~~

Nhưng customerId bắt buộc phải có thì nên được kiểm tra riêng:

~~~java
order.customer != null && order.customer.id != null
~~~

Không nên dùng một giá trị giả để thay thế identifier bắt buộc rồi tiếp tục xử lý nghiệp vụ như thể dữ liệu hợp lệ.

## 8. Thiết kế giá trị mặc định ở tầng Java

Nếu cùng một quy tắc fallback được dùng ở nhiều nơi, hãy cân nhắc đặt tên cho nó trong Java thay vì lặp lại biểu thức:

~~~java
public String displayNameOrGuest(Customer customer) {
    if (customer == null) {
        return "Guest";
    }

    String displayName = customer.getDisplayName();

    if (displayName == null || displayName.isBlank()) {
        return "Guest";
    }

    return displayName;
}
~~~

Sau đó, SpEL có thể gọi method phù hợp nếu EvaluationContext cho phép:

~~~java
#displayPolicy.displayNameOrGuest(order.customer)
~~~

Cách này giúp:

- Tập trung quy tắc xử lý null và blank.
- Dễ kiểm thử độc lập.
- Dễ thay đổi giá trị mặc định.
- Tránh lặp lại cùng một biểu thức trong nhiều nơi.
- Tách quyết định nghiệp vụ khỏi chuỗi SpEL.

Với các quy tắc quan trọng, hãy ưu tiên method hoặc service có tên rõ nghĩa và kiểm soát quyền truy cập method trong context.

## 9. Kiểm thử fallback và error handling

Nên kiểm thử riêng từng loại tình huống. Ví dụ với Elvis:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("name", null);

assertEquals(
        "Guest",
        parser.parseExpression("#name ?: 'Guest'")
                .getValue(context, String.class)
);
~~~

Kiểm tra chuỗi rỗng:

~~~java
context.setVariable("name", "");

assertEquals(
        "Guest",
        parser.parseExpression("#name ?: 'Guest'")
                .getValue(context, String.class)
);
~~~

Kiểm tra false không bị thay thế:

~~~java
context.setVariable("enabled", false);

assertEquals(
        Boolean.FALSE,
        parser.parseExpression("#enabled ?: true")
                .getValue(context, Boolean.class)
);
~~~

Kiểm tra ternary:

~~~java
context.setVariable("score", 80);

assertEquals(
        "PASS",
        parser.parseExpression("#score >= 50 ? 'PASS' : 'FAIL'")
                .getValue(context, String.class)
);
~~~

Và kiểm tra lỗi parse độc lập:

~~~java
assertThrows(
        ParseException.class,
        () -> parser.parseExpression("10 > ?")
);
~~~

Với lỗi evaluate, tạo root object hoặc context có property/method tương ứng để kiểm tra exception thực tế. Không gộp kiểm thử parse, fallback và evaluate thành một trường hợp duy nhất vì chúng xác nhận những hành vi khác nhau.

## 10. Tổng kết

Giá trị mặc định giúp biểu thức có kết quả khi dữ liệu thuộc trường hợp thiếu giá trị đã được dự liệu. Xử lý lỗi giải quyết những thao tác không thể thực hiện đúng.

- Dùng **Elvis (?:)** cho fallback, hiểu rõ cách xử lý null và chuỗi rỗng.
- Dùng **ternary (? :)** khi cần chọn giữa hai kết quả theo điều kiện.
- Dùng **safe navigation (?.)** để bảo vệ truy cập qua receiver null.
- Dùng **ParseException** và **EvaluationException** để xử lý lỗi ở đúng giai đoạn.
- Không dùng fallback để che giấu property sai, method lỗi, lỗi chuyển đổi hoặc dữ liệu bắt buộc bị thiếu.
- Đặt quy tắc fallback dùng chung trong Java khi nó có ý nghĩa nghiệp vụ và cần được kiểm thử độc lập.

Một biểu thức tốt phải cho thấy rõ trường hợp nào được thay thế bằng giá trị mặc định và trường hợp nào cần báo lỗi. Khi ranh giới đó được xác định, SpEL sẽ dễ đọc hơn và ứng dụng tránh được việc âm thầm tiếp tục với dữ liệu sai.