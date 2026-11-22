# Suy luận kiểu

## 1. Suy luận kiểu trong DSL là gì?

Suy luận kiểu (type inference) là khả năng để compiler hoặc bộ kiểm tra tự xác định kiểu của biểu thức, biến hoặc tham số từ ngữ cảnh và các quy tắc của hệ kiểu, thay vì yêu cầu người viết khai báo kiểu ở mọi vị trí.

Ví dụ, một DSL có thể cho phép viết:

~~~text
let quantity = 3;
let unitPrice = money(120000, VND);
let total = quantity * unitPrice;
~~~

Người viết không khai báo kiểu cho từng biến. Bộ kiểm tra có thể suy ra:

- quantity có kiểu Integer từ literal 3.
- unitPrice có kiểu Money<VND> từ lời gọi money.
- total có kiểu Money<VND> vì phép nhân Integer với Money<VND> được định nghĩa trả về Money<VND>.

Nếu DSL yêu cầu khai báo tường minh, chương trình có thể được viết:

~~~text
let quantity: Integer = 3;
let unitPrice: Money<VND> = money(120000, VND);
let total: Money<VND> = quantity * unitPrice;
~~~

Hai cách viết có thể có cùng ý nghĩa. Suy luận kiểu giúp giảm phần khai báo lặp lại, làm chương trình ngắn hơn và giữ sự chú ý của người viết ở logic nghiệp vụ.

Suy luận kiểu không phải là đoán kiểu dựa trên tên biến hoặc ý định của người viết. Nó là quá trình có quy tắc: compiler thu thập thông tin từ literal, khai báo, toán tử, lời gọi hàm và ngữ cảnh; sau đó giải các ràng buộc để tìm kiểu phù hợp. Nếu không thể xác định một kiểu duy nhất hoặc không có kiểu nào phù hợp, compiler cần yêu cầu thêm thông tin hoặc báo lỗi.

## 2. Vì sao DSL cần suy luận kiểu?

DSL thường hướng đến việc diễn đạt nghiệp vụ ngắn gọn. Nếu bắt người dùng khai báo kiểu ở mọi biểu thức trung gian, mã có thể trở nên dài và khó đọc:

~~~text
let activeOrders: List<Order> =
    filterOrders(orders, (order: Order) -> Boolean {
        return order.status == OrderStatus.ACTIVE;
    });
~~~

Nếu filterOrders đã quy định tham số thứ hai là hàm nhận Order và trả về Boolean, compiler có thể suy ra kiểu của order và kiểu trả về của lambda:

~~~text
let activeOrders = filterOrders(orders, order ->
    order.status == OrderStatus.ACTIVE
);
~~~

Suy luận kiểu mang lại một số lợi ích:

- Giảm khai báo lặp lại và giữ biểu thức DSL gọn.
- Giúp người viết tập trung vào khái niệm nghiệp vụ thay vì chi tiết kiểu.
- Tăng khả năng đọc khi kiểu đã rõ từ ngữ cảnh.
- Cho phép DSL hỗ trợ lambda, generic và biểu thức phức hợp tự nhiên hơn.
- Vẫn giữ được nhiều lợi ích của kiểm tra kiểu tĩnh nếu compiler suy luận và xác minh trước khi chạy.

Tuy nhiên, suy luận kiểu cũng làm compiler phức tạp hơn. Nếu quy tắc không nhất quán, người dùng khó hiểu vì sao một biểu thức được suy ra thành kiểu này thay vì kiểu khác. Một DSL tốt cần cân bằng giữa sự ngắn gọn và khả năng dự đoán.

## 3. Khai báo tường minh và suy luận kiểu

Khai báo kiểu tường minh cho biết trực tiếp kiểu mà người viết mong muốn:

~~~text
let retryCount: Integer = 3;
let customerName: String = "An";
~~~

Suy luận kiểu cho phép bỏ phần kiểu khi compiler có đủ thông tin:

~~~text
let retryCount = 3;
let customerName = "An";
~~~

Hai cách có thể được dùng kết hợp. Người viết có thể khai báo kiểu tại những ranh giới quan trọng và để compiler suy luận các biến trung gian:

~~~text
let orders: List<Order> = loadOrders();
let unpaid = orders.filter(order -> order.status == UNPAID);
let totalDue = unpaid.map(order -> order.total).sum();
~~~

Ở đây, kiểu của orders được ghi rõ vì đó là dữ liệu đầu vào quan trọng. Kiểu order trong lambda, kết quả filter và các biểu thức trung gian có thể được suy ra từ chữ ký của List và các phương thức tương ứng.

| Tiêu chí | Kiểu tường minh | Suy luận kiểu |
|---|---|---|
| Khả năng đọc | Cho biết trực tiếp hợp đồng kiểu | Ngắn gọn khi ngữ cảnh đủ rõ |
| Độ dài mã | Có thể lặp lại kiểu nhiều lần | Giảm khai báo dư thừa |
| Kiểm soát của người viết | Có thể chỉ định kiểu mong muốn | Phụ thuộc quy tắc compiler |
| Chẩn đoán lỗi | Dễ chỉ ra kiểu kỳ vọng | Có thể cần giải thích chuỗi suy luận |
| Phù hợp | API công khai, ranh giới dữ liệu, kiểu miền quan trọng | Biểu thức cục bộ, lambda, giá trị trung gian |

Không có quy tắc rằng mọi biến đều phải suy luận hoặc mọi biến đều phải khai báo. Chính sách tốt thường cho phép cả hai và quy định nơi nào nên ưu tiên kiểu tường minh.

## 4. Môi trường kiểu và thông tin đầu vào

Để suy luận kiểu, compiler cần một môi trường chứa các khai báo có thể nhìn thấy tại vị trí đang phân tích. Môi trường này thường được ký hiệu là Γ (Gamma), gọi là môi trường kiểu (typing environment).

Γ có thể chứa:

- Kiểu của biến và hằng.
- Chữ ký hàm và phương thức.
- Kiểu dữ liệu và generic parameter.
- Kiểu thuộc tính của object.
- Kiểu trả về của hàm hoặc lambda.
- Các ràng buộc về subtype, trait hoặc interface.
- Thông tin về namespace và module đang được import.

Ví dụ:

~~~text
let quantity: Integer = 4;
let unitPrice: Money<VND> = money(25000, VND);
let total = quantity * unitPrice;
~~~

Tại biểu thức quantity * unitPrice, môi trường kiểu cung cấp:

~~~text
Γ(quantity) = Integer
Γ(unitPrice) = Money<VND>
~~~

Quy tắc kiểu của phép nhân có thể suy ra:

~~~text
Integer × Money<VND> -> Money<VND>
~~~

Vì vậy, total có kiểu Money<VND>.

Môi trường kiểu thay đổi theo scope. Khi đi vào một hàm hoặc block, compiler bổ sung kiểu của tham số và biến cục bộ. Khi ra khỏi scope, những khai báo đó không còn được dùng để phân giải biểu thức bên ngoài.

## 5. Các quy tắc suy luận cơ bản

Một bộ suy luận kiểu hoạt động bằng cách áp dụng quy tắc cho từng loại biểu thức. Các quy tắc dưới đây là ví dụ giản lược cho một DSL có kiểu tĩnh.

### 5.1. Literal

Literal thường có kiểu được xác định trực tiếp từ cú pháp:

| Literal | Kiểu có thể suy ra |
|---|---|
| 42 | Integer |
| 3.14 | Decimal |
| "hello" | String |
| true | Boolean |
| 2026-11-15 | Date |
| null | Kiểu null riêng hoặc kiểu chưa xác định cần ngữ cảnh |

Kiểu chính xác phụ thuộc thiết kế DSL. Ví dụ, một DSL có thể xem số nguyên mặc định là Int64, hoặc dùng kiểu số nguyên tổng quát rồi chọn độ rộng theo ngữ cảnh.

Literal số có thể cần ngữ cảnh để xác định kiểu:

~~~text
let price: Decimal = 120;
~~~

Nếu DSL cho phép literal nguyên được chuyển thành Decimal trong ngữ cảnh gán, compiler có thể suy ra hoặc chuyển kiểu theo quy tắc đã công bố. Nếu không, người viết phải dùng literal Decimal hoặc phép chuyển đổi tường minh.

### 5.2. Khai báo biến

Với khai báo:

~~~text
let name = expression;
~~~

compiler suy luận kiểu của expression rồi gán kiểu đó cho name, trừ khi ngôn ngữ quy định kiểu biến rộng hơn hoặc có chú thích kiểu ở bên trái.

Nếu biểu thức không có kiểu xác định, compiler không thể tạo khai báo hợp lệ:

~~~text
let value = empty();
~~~

Nếu empty() có thể tạo danh sách của bất kỳ kiểu phần tử nào, compiler cần thêm thông tin:

~~~text
let value: List<Order> = empty();
~~~

### 5.3. Toán tử

Kiểu kết quả của toán tử được suy ra từ kiểu toán hạng và quy tắc của toán tử.

| Biểu thức | Quy tắc minh họa | Kiểu kết quả |
|---|---|---|
| Integer + Integer | Cộng hai số nguyên | Integer |
| Decimal + Decimal | Cộng hai số thập phân | Decimal |
| String + String | Nối chuỗi nếu DSL hỗ trợ | String |
| Money<VND> + Money<VND> | Cộng cùng loại tiền | Money<VND> |
| Money<VND> + Money<USD> | Không hợp lệ nếu chưa chuyển đổi | Lỗi kiểu |
| Integer > Integer | So sánh số nguyên | Boolean |

Compiler không nên suy luận kiểu chỉ dựa vào tên toán tử. Mỗi toán tử phải có quy tắc được định nghĩa rõ, đặc biệt với kiểu miền như tiền tệ, ngày giờ, đơn vị đo và trạng thái.

### 5.4. Lời gọi hàm

Với lời gọi hàm, kiểu kết quả thường được lấy từ kiểu trả về của chữ ký đã chọn:

~~~text
function calculateTax(order: Order): Money<VND>;

let tax = calculateTax(currentOrder);
~~~

Nếu lời gọi được phân giải tới chữ ký trả về Money<VND>, compiler suy ra tax có kiểu đó. Nếu có overload, compiler cần xác định overload phù hợp trước khi suy ra kết quả.

## 6. Suy luận kiểu cho hàm và generic

Generic cho phép một hàm hoặc kiểu dữ liệu làm việc với nhiều kiểu khác nhau mà vẫn giữ kiểm tra kiểu.

Ví dụ:

~~~text
function first<T>(items: List<T>): T {
    return items[0];
}

let firstOrder = first(orders);
let firstName = first(customerNames);
~~~

Nếu orders có kiểu List<Order>, compiler suy ra T là Order và firstOrder có kiểu Order. Nếu customerNames có kiểu List<String>, T là String và firstName có kiểu String.

Trong ví dụ này, người dùng không cần ghi:

~~~text
let firstOrder: Order = first<Order>(orders);
~~~

vì kiểu tham số đầu vào cung cấp đủ thông tin để suy ra T.

### 6.1. Suy luận nhiều tham số kiểu

Một hàm có thể có nhiều tham số kiểu:

~~~text
function pair<A, B>(left: A, right: B): Pair<A, B>;

let result = pair("order-42", 42);
~~~

Compiler suy ra A là String, B là Integer và kết quả có kiểu Pair<String, Integer>.

Nếu cùng một tham số kiểu xuất hiện ở nhiều vị trí, các kiểu đối số phải đáp ứng quy tắc ràng buộc:

~~~text
function sameType<T>(left: T, right: T): T;

let result = sameType(10, 20);
~~~

Hai đối số cùng là Integer nên T có thể được suy ra là Integer. Nhưng lời gọi sameType(10, "ten") không có một T duy nhất nếu DSL yêu cầu hai đối số cùng kiểu và không có quy tắc hợp nhất phù hợp.

### 6.2. Ràng buộc generic

Generic có thể bị giới hạn bởi interface, trait hoặc lớp cơ sở:

~~~text
function sort<T: Comparable<T>>(items: List<T>): List<T>;
~~~

Ràng buộc T: Comparable<T> có nghĩa kiểu T phải đáp ứng hợp đồng Comparable<T>. Khi gọi sort, compiler vừa suy luận T từ danh sách đầu vào vừa kiểm tra T thỏa ràng buộc.

Nếu một kiểu không có khả năng so sánh theo hợp đồng đó, lời gọi bị từ chối trước khi chạy. Điều này giúp generic an toàn hơn so với dùng Object rồi ép kiểu trong runtime.

### 6.3. Suy luận kiểu trả về

Compiler có thể suy luận kiểu trả về từ các nhánh return:

~~~text
function displayName(customer) {
    if customer.nickname != null {
        return customer.nickname;
    }
    return customer.fullName;
}
~~~

Nếu cả nickname và fullName đều là String, kiểu trả về có thể được suy ra là String. Nếu một nhánh trả về String và nhánh khác trả về Integer, compiler cần một kiểu chung hợp lệ hoặc báo lỗi tùy quy tắc của DSL.

Một số ngôn ngữ yêu cầu khai báo kiểu trả về tường minh cho hàm công khai hoặc hàm đệ quy. Điều này tránh vòng suy luận khó giải và giúp hợp đồng API ổn định hơn.

## 7. Suy luận kiểu cho lambda và biểu thức hàm

Lambda thường không ghi kiểu tham số vì kiểu có thể được suy ra từ nơi lambda được truyền vào.

~~~text
let paidOrders = orders.filter(order -> order.status == PAID);
~~~

Nếu filter nhận predicate có kiểu Order -> Boolean, compiler suy ra:

- order có kiểu Order.
- order.status có kiểu trạng thái của đơn hàng.
- So sánh với PAID trả về Boolean.
- Kết quả filter có kiểu List<Order>.

Nếu lambda không có ngữ cảnh kỳ vọng, compiler có thể không suy ra được kiểu tham số:

~~~text
let transform = value -> value;
~~~

Biểu thức này có thể là hàm T -> T với kiểu tổng quát, hoặc cần chú thích kiểu tùy khả năng của DSL. Một DSL đơn giản có thể yêu cầu:

~~~text
let transform = (value: String) -> value;
~~~

### 7.1. Kiểu tham số từ ngữ cảnh

Với một lời gọi:

~~~text
orders.map(order -> order.customer.name)
~~~

Nếu kiểu của orders là List<Order>, compiler biết order là Order. Nó có thể tra thuộc tính customer, rồi tra name và suy ra kiểu kết quả là List<String>.

Nếu orders chưa có kiểu hoặc có kiểu quá tổng quát như List<Any>, compiler có thể không biết customer có tồn tại hay không. Người viết cần khai báo kiểu đầu vào hoặc cung cấp schema.

### 7.2. Lambda có nhiều nhánh

Kiểu trả về của lambda phải nhất quán giữa các nhánh:

~~~text
let label = order ->
    if order.isPaid then "Paid"
    else "Pending";
~~~

Cả hai nhánh trả về String nên lambda có kiểu Order -> String.

Nếu một nhánh trả về String và nhánh còn lại trả về null, kiểu kết quả có thể là Nullable<String> hoặc Option<String>, tùy mô hình nullability của DSL. Quy tắc này phải được định nghĩa thống nhất để tránh giá trị null xuất hiện bất ngờ.

## 8. Suy luận kiểu hai chiều

Một số compiler dùng kỹ thuật suy luận kiểu hai chiều (bidirectional type checking). Thay vì chỉ suy luận kiểu từ biểu thức con lên trên, compiler còn truyền kiểu kỳ vọng từ ngữ cảnh xuống biểu thức con.

Hai hướng thường được mô tả là:

- **Synthesis (suy ra):** từ biểu thức, xác định kiểu của nó.
- **Checking (kiểm tra theo kỳ vọng):** biết kiểu cần có và xác nhận biểu thức phù hợp với kiểu đó.

Ví dụ:

~~~text
let amount: Money<VND> = money(500000, VND);
~~~

Lời gọi money có thể tự suy ra Money<VND>. Nhưng với lambda:

~~~text
let isLarge: Order -> Boolean =
    order -> order.total > money(1000000, VND);
~~~

Kiểu kỳ vọng Order -> Boolean được truyền vào lambda. Compiler dùng nó để gán kiểu Order cho order và kiểm tra thân lambda trả về Boolean.

Suy luận hai chiều thường giúp xử lý lambda, literal rỗng, biểu thức generic và các cấu trúc cần ngữ cảnh mà không phải giải toàn bộ bài toán kiểu một cách toàn cục.

## 9. Ràng buộc kiểu và quá trình giải ràng buộc

Khi phân tích một biểu thức, compiler có thể chưa biết kiểu cuối cùng ngay lập tức. Nó tạo các biến kiểu và ràng buộc, sau đó giải chúng.

Ví dụ:

~~~text
let result = choose(condition, 10, 20);
~~~

Giả sử choose có chữ ký:

~~~text
function choose<T>(condition: Boolean, left: T, right: T): T;
~~~

Từ đối số thứ nhất, compiler xác nhận condition có kiểu Boolean. Từ hai đối số còn lại, compiler tạo các ràng buộc:

- T tương thích với kiểu của literal 10.
- T tương thích với kiểu của literal 20.

Nếu cả hai literal có kiểu Integer, nghiệm là T = Integer và result có kiểu Integer.

Quy trình tổng quát:

1. Tạo biến kiểu chưa biết cho những phần chưa xác định.
2. Duyệt biểu thức và sinh các ràng buộc từ toán tử, lời gọi hàm, gán và ngữ cảnh.
3. Hợp nhất các kiểu khi có ràng buộc tương đương.
4. Kiểm tra các giới hạn subtype hoặc interface.
5. Tìm nghiệm cho các biến kiểu.
6. Thay biến kiểu bằng kiểu đã xác định và báo lỗi nếu ràng buộc mâu thuẫn.

Ví dụ ràng buộc mâu thuẫn:

~~~text
function sameType<T>(left: T, right: T): T;
let result = sameType(10, "ten");
~~~

Nếu không có kiểu chung được phép, compiler không thể tìm nghiệm cho T. Diagnostic nên chỉ rõ hai đối số tạo ra xung đột.

## 10. Hợp nhất kiểu và kiểu chung

Hợp nhất (unification) là quá trình tìm cách làm cho hai biểu thức kiểu tương thích bằng cách thay biến kiểu chưa biết bằng kiểu phù hợp.

Ví dụ, nếu compiler có:

~~~text
List<T> = List<Order>
~~~

nó có thể hợp nhất T với Order.

Với hai nhánh điều kiện:

~~~text
let result =
    if condition then 10
    else 20;
~~~

compiler cần tìm kiểu chung cho hai nhánh. Nếu cả hai là Integer, kiểu kết quả là Integer.

Nếu một nhánh là Integer và nhánh còn lại là Decimal, DSL có thể:

- Chọn Decimal nếu có quy tắc nâng kiểu số nguyên lên số thập phân.
- Yêu cầu chuyển đổi tường minh.
- Báo lỗi nếu hai kiểu không có kiểu chung hợp lệ.

Không nên chọn kiểu chung tùy tiện chỉ để chương trình biên dịch. Ví dụ, hợp nhất Money<VND> và Money<USD> thành Money chung có thể làm mất thông tin đơn vị tiền tệ và dẫn tới phép tính sai.

### 10.1. Subtyping và variance

Nếu DSL có quan hệ subtype, một giá trị kiểu con có thể được dùng ở vị trí cần kiểu cha theo quy tắc của ngôn ngữ. Ví dụ, CardPayment có thể là subtype của PaymentMethod.

Generic còn cần quy định variance:

- Covariant: List<Dog> có thể được dùng ở vị trí cần List<Animal> nếu chỉ đọc theo hợp đồng phù hợp.
- Contravariant: một bộ xử lý nhận Animal có thể dùng ở nơi cần bộ xử lý nhận Dog.
- Invariant: hai kiểu generic chỉ tương thích khi tham số kiểu giống nhau.

Variance ảnh hưởng đến cách suy luận kiểu chung và an toàn khi truyền collection hoặc function. DSL không nhất thiết phải hỗ trợ mọi dạng variance; nếu có, cần ghi rõ quy tắc và cách checker áp dụng.

## 11. Các thuật toán suy luận kiểu

Không có một thuật toán duy nhất phù hợp với mọi hệ kiểu. Một số hướng phổ biến:

### 11.1. Hindley-Milner

Hindley-Milner là nền tảng của nhiều hệ thống suy luận kiểu trong các ngôn ngữ hàm. Nó hỗ trợ suy luận kiểu đa hình cho các hàm mà không yêu cầu khai báo kiểu ở mọi nơi.

Một đặc điểm quan trọng là generalization: sau khi suy ra kiểu của một khai báo, các biến kiểu không bị ràng buộc bởi môi trường có thể được tổng quát hóa để dùng ở nhiều kiểu khác nhau.

Ví dụ, một hàm identity:

~~~text
function identity(value) {
    return value;
}
~~~

có thể được suy ra kiểu tổng quát T -> T. Nó có thể dùng với Integer, String hoặc Order mà không cần viết nhiều bản sao.

Hindley-Milner phù hợp với một số hệ kiểu hàm, nhưng cần điều chỉnh khi DSL có subtype phức tạp, overload, effect hoặc các tính năng kiểu phụ thuộc.

### 11.2. Local type inference

Local type inference giới hạn việc suy luận trong phạm vi biểu thức hoặc khai báo gần nhau. Compiler không cần suy ra toàn bộ kiểu của chương trình trong một bước.

Cách này thường dễ dự đoán hơn khi hệ kiểu có subtype, overload hoặc API hướng đối tượng. Người viết có thể cần khai báo kiểu tại một số ranh giới như tham số hàm, kiểu trả về hoặc generic argument.

### 11.3. Constraint-based inference

Constraint-based inference tạo một tập ràng buộc kiểu từ chương trình rồi giải chúng bằng thuật toán hợp nhất hoặc solver. Cách tiếp cận này linh hoạt và thường được dùng trong compiler có nhiều loại ràng buộc.

Đổi lại, khi lỗi xảy ra, chuỗi ràng buộc có thể dài. Compiler cần lưu nguồn gốc của mỗi ràng buộc để giải thích vì sao hai kiểu không tương thích.

### 11.4. Bidirectional type checking

Bidirectional checking kết hợp suy kiểu từ biểu thức và kiểm tra theo kiểu kỳ vọng. Nó đặc biệt hữu ích với lambda, generic, literal rỗng và biểu thức có nhiều lựa chọn.

Một DSL có thể kết hợp nhiều kỹ thuật: suy luận local cho biến, constraint solving cho generic, và bidirectional checking cho lambda hoặc cấu trúc lồng nhau.

## 12. Giới hạn và trường hợp mơ hồ

Suy luận kiểu không phải lúc nào cũng tìm được một đáp án. Một số tình huống thường gặp:

### 12.1. Không đủ thông tin

~~~text
let values = empty();
~~~

Compiler không biết phần tử của danh sách có kiểu gì. Có thể giải quyết bằng chú thích kiểu hoặc truyền ngữ cảnh:

~~~text
let values: List<Customer> = empty();
~~~

### 12.2. Có nhiều kiểu phù hợp

~~~text
format(null);
~~~

Nếu có format(String) và format(Date), giá trị null có thể phù hợp với cả hai. Compiler cần quy tắc ưu tiên rõ ràng hoặc yêu cầu người viết ép kiểu.

### 12.3. Xung đột ràng buộc

~~~text
function same<T>(left: T, right: T): T;
let result = same(1, "one");
~~~

Nếu kiểu Integer và String không có kiểu chung được phép cho T, lời gọi không hợp lệ.

### 12.4. Đệ quy

~~~text
function countDown(value) {
    if value == 0 then 0
    else countDown(value - 1)
}
~~~

Để suy luận kiểu của hàm đệ quy, compiler có thể cần một kiểu tạm cho hàm trong lúc phân tích thân hàm. Một số ngôn ngữ yêu cầu khai báo kiểu trả về tường minh cho hàm đệ quy để tránh vòng suy luận không thể giải.

### 12.5. Overload và lambda

Nếu nhiều overload nhận các kiểu function khác nhau, lambda không có chú thích kiểu có thể không cung cấp đủ thông tin để chọn overload. Compiler có thể yêu cầu ghi kiểu tham số lambda hoặc chỉ định kiểu generic.

## 13. Nullability và kiểu đặc biệt

Suy luận kiểu cần xử lý nhất quán các kiểu có thể thiếu giá trị:

~~~text
let nickname = customer.nickname;
~~~

Nếu nickname có thể null, kiểu được suy ra có thể là Nullable<String>, Option<String> hoặc một dạng union tương đương.

Khi dùng:

~~~text
let length = customer.nickname.length;
~~~

compiler cần báo lỗi nếu truy cập thuộc tính trên giá trị có thể null mà không kiểm tra. Người viết có thể dùng kiểm tra null:

~~~text
if customer.nickname != null {
    let length = customer.nickname.length;
}
~~~

Một số hệ kiểu có flow-sensitive typing: sau khi kiểm tra nickname khác null, compiler thu hẹp kiểu của nó trong nhánh điều kiện thành String không nullable.

Các kiểu đặc biệt khác cũng cần quy tắc rõ:

- Never hoặc Nothing: biểu thức không bao giờ trả về bình thường.
- Unit hoặc Void: biểu thức không mang giá trị hữu ích.
- Option hoặc Maybe: biểu diễn giá trị có thể vắng mặt.
- Union type: giá trị có thể thuộc một trong nhiều kiểu.
- Tuple: kiểu của từng thành phần được suy ra theo vị trí.

## 14. Suy luận kiểu cho DSL miền nghiệp vụ

Trong DSL nghiệp vụ, kiểu dữ liệu thường mang nhiều ý nghĩa hơn kiểu nguyên thủy. Một số khái niệm cần được phân biệt:

| Kiểu miền | Ý nghĩa | Quy tắc suy luận cần chú ý |
|---|---|---|
| Money<VND> | Tiền Việt Nam đồng | Không tự trộn với Money<USD> |
| Percentage | Tỷ lệ phần trăm | Không cộng trực tiếp với Money |
| Duration | Khoảng thời gian | Cộng/trừ theo đơn vị thời gian |
| LocalDate | Ngày lịch không kèm múi giờ | Không tự chuyển thành instant |
| CustomerId | Định danh khách hàng | Không nhầm với OrderId dù cùng biểu diễn chuỗi |
| Quantity<Product> | Số lượng theo loại sản phẩm | Phép cộng cần cùng loại đơn vị |

Ví dụ:

~~~text
let subtotal = item.quantity * item.unitPrice;
let discount = subtotal * item.discountRate;
let payable = subtotal - discount;
~~~

Nếu quantity có kiểu Quantity<Item>, unitPrice có kiểu Money<VND>/Item và discountRate có kiểu Percentage, hệ kiểu có thể suy ra:

- subtotal có kiểu Money<VND>.
- discount có kiểu Money<VND>.
- payable có kiểu Money<VND>.

Điều này yêu cầu DSL định nghĩa rõ phép nhân, phép trừ và cách biểu diễn tỷ lệ. Nếu kiểu chỉ là Decimal cho mọi giá trị, compiler khó phát hiện việc nhân sai đơn vị.

Suy luận kiểu miền giúp DSL ngắn gọn nhưng vẫn giữ được ý nghĩa nghiệp vụ. Nó đặc biệt hữu ích trong tài chính, định giá, đo lường, workflow và cấu hình có nhiều loại định danh.

## 15. Diagnostic khi suy luận kiểu thất bại

Thông báo lỗi nên giúp người viết hiểu:

- Biểu thức nào không thể suy luận.
- Kiểu nào đang được kỳ vọng.
- Các kiểu hoặc ràng buộc nào xung đột.
- Ngữ cảnh nào tạo ra ràng buộc đó.
- Cách thêm chú thích hoặc chuyển đổi để giải quyết.

Ví dụ thông báo kém:

~~~text
Type inference failed.
~~~

Thông báo hữu ích hơn:

~~~text
ERROR TYPE-021: Cannot infer the element type of empty().
  at rules/discount.dsl:8:14
  Expected context: List<T>
  No element or annotation constrains T.
  Hint: Declare the variable as List<Order> or provide a typed empty list.
~~~

Với xung đột:

~~~text
ERROR TYPE-034: Conflicting type constraints for T.
  at rules/identity.dsl:4:20
  First argument: Integer
  Second argument: String
  Hint: Use two separate type parameters or convert both values to a common type.
~~~

Compiler nên lưu nguồn gốc của các ràng buộc để chỉ ra vị trí tạo ra xung đột. Nếu chỉ báo lỗi ở cuối biểu thức lớn, người viết khó xác định phần nào cần sửa.

## 16. Thiết kế suy luận kiểu cho một DSL mới

Khi xây dựng hệ kiểu cho DSL, có thể triển khai theo trình tự:

1. **Xác định các kiểu miền cốt lõi.** Liệt kê kiểu nguyên thủy, kiểu giá trị, kiểu định danh và kiểu dữ liệu nghiệp vụ.
2. **Quy định literal.** Xác định kiểu mặc định của số, chuỗi, ngày, Boolean và null.
3. **Định nghĩa quy tắc toán tử.** Ghi rõ kiểu đầu vào, kiểu đầu ra và chuyển đổi được phép.
4. **Thiết kế kiểu hàm.** Quy định tham số, kiểu trả về, generic và overload.
5. **Chọn phạm vi suy luận.** Quyết định suy luận toàn cục, local, theo ngữ cảnh hay kết hợp.
6. **Quy định chú thích kiểu.** Cho phép người dùng bổ sung kiểu khi không đủ thông tin hoặc khi cần làm rõ hợp đồng.
7. **Thiết kế ràng buộc.** Xác định cách sinh, hợp nhất và giải các ràng buộc kiểu.
8. **Quy định nullability và subtype.** Nêu rõ kiểu có thể thiếu giá trị và quan hệ kế thừa.
9. **Thiết kế diagnostics.** Lưu nguồn gốc ràng buộc và đưa ra gợi ý sửa có ý nghĩa.
10. **Kiểm thử các trường hợp biên.** Bao gồm literal, lambda, generic, overload, đệ quy và kiểu miền.

Không nên bắt đầu bằng một thuật toán phức tạp nếu DSL chỉ cần một tập quy tắc nhỏ. Có thể triển khai suy luận local cho literal, biến và lời gọi hàm trước, sau đó mở rộng generic hoặc bidirectional checking khi nhu cầu xuất hiện.

## 17. Kiểm thử bộ suy luận kiểu

Một bộ suy luận kiểu cần được kiểm thử bằng các ví dụ thành công và thất bại.

### 17.1. Kiểm thử suy luận thành công

~~~text
let count = 3;
let label = "ready";
let active = true;
~~~

Kiểu kỳ vọng lần lượt là Integer, String và Boolean.

### 17.2. Kiểm thử kiểu từ ngữ cảnh

~~~text
let orders: List<Order> = empty();
let names = orders.map(order -> order.customer.name);
~~~

Kiểu kỳ vọng của names là List<String>, nếu customer.name có kiểu String.

### 17.3. Kiểm thử generic

~~~text
let number = first([1, 2, 3]);
let text = first(["a", "b"]);
~~~

Kiểu kỳ vọng lần lượt là Integer và String.

### 17.4. Kiểm thử lỗi

~~~text
let total = money(100, VND) + money(20, USD);
~~~

Nếu DSL không có phép cộng khác tiền tệ, compiler phải báo lỗi kiểu.

Các nhóm kiểm thử cần có:

- Unit test cho quy tắc kiểu của từng biểu thức.
- Test hợp nhất và giải ràng buộc.
- Test generic, lambda, overload và suy luận trả về.
- Test scope và môi trường kiểu.
- Golden test cho diagnostic và vị trí nguồn.
- Test hồi quy cho chương trình từng bị suy luận sai.
- Test hiệu năng với biểu thức lớn hoặc nhiều generic constraint.

## 18. Những lỗi thiết kế thường gặp

### Suy luận quá nhiều, làm kiểu khó đoán

Nếu compiler cố suy ra mọi thứ qua nhiều module và nhiều overload, thông báo lỗi có thể rất khó hiểu. Giới hạn phạm vi suy luận và cho phép chú thích kiểu tại ranh giới quan trọng.

### Không có cách viết kiểu tường minh

Khi suy luận thất bại, người dùng cần cách cung cấp thêm thông tin. Hãy hỗ trợ type annotation hoặc generic argument rõ ràng ở những vị trí phù hợp.

### Chọn kiểu chung làm mất ý nghĩa miền

Hợp nhất Money<VND> và Money<USD> thành một kiểu tiền chung có thể làm mất đơn vị. Không nên hy sinh an toàn miền chỉ để tìm được một kiểu kết quả.

### Chuyển kiểu ngầm định không rõ ràng

Tự động chuyển Decimal sang Integer hoặc chuyển giữa đơn vị đo có thể gây mất dữ liệu. Mọi phép chuyển đổi cần có quy tắc và mức độ an toàn được công bố.

### Overload làm suy luận mơ hồ

Nhiều overload nhận kiểu gần nhau hoặc lambda không có kiểu tham số rõ có thể khiến compiler không chọn được hàm. Hãy thiết kế overload có phân biệt rõ và cung cấp cách chỉ định kiểu.

### Diagnostic không giải thích được nguồn ràng buộc

Chỉ báo rằng hai kiểu không tương thích là chưa đủ nếu biểu thức lớn. Checker cần giữ vị trí và ngữ cảnh của các ràng buộc để chỉ ra nơi phát sinh xung đột.

### Dùng suy luận thay cho kiểm tra runtime

Suy luận kiểu xác định kiểu của biểu thức, không chứng minh dữ liệu bên ngoài luôn hợp lệ. Vẫn cần validation runtime cho dữ liệu và môi trường chỉ biết khi chạy.

## 19. Kết luận

Suy luận kiểu cho phép compiler xác định kiểu của biến và biểu thức từ literal, khai báo, toán tử, chữ ký hàm và ngữ cảnh sử dụng. Nó giúp DSL ngắn gọn hơn mà vẫn có thể giữ được lợi ích của kiểm tra kiểu tĩnh. Để suy luận đáng tin cậy, ngôn ngữ cần môi trường kiểu rõ ràng, quy tắc cho từng loại biểu thức, cơ chế giải ràng buộc và cách xử lý những trường hợp thiếu hoặc mơ hồ thông tin.

Các kỹ thuật như suy luận local, constraint solving, Hindley-Milner và kiểm tra hai chiều có những phạm vi phù hợp khác nhau. DSL không cần áp dụng tất cả; nên chọn mức phức tạp tương xứng với kiểu dữ liệu, generic, lambda và nhu cầu của người dùng. Với kiểu miền như tiền tệ, đơn vị đo và định danh, suy luận cần bảo toàn ý nghĩa thay vì chọn một kiểu chung thiếu an toàn.

Khi thiết kế DSL, hãy để compiler suy ra kiểu khi ngữ cảnh đủ rõ, cho phép khai báo tường minh ở ranh giới quan trọng và cung cấp diagnostics giải thích được vì sao suy luận thành công hoặc thất bại. Cách tiếp cận này giúp chương trình vừa gọn, dễ đọc vừa có hợp đồng kiểu có thể kiểm tra và dự đoán.
