# Lambda và closure

Lambda và closure là hai khái niệm quan trọng trong lập trình hàm và thiết kế DSL nội bộ. Chúng cho phép chương trình truyền một đoạn hành vi như một giá trị, lưu lại để dùng sau, hoặc cung cấp một khối biểu thức cho thư viện xử lý. Nhờ đó, API có thể được viết gần với cách mô tả công việc trong một miền, chẳng hạn lọc đơn hàng, khai báo quy trình, xác định điều kiện hoặc xây dựng cấu hình.

**Lambda** thường là một biểu thức tạo ra một hàm không cần khai báo tên riêng. **Closure** là một hàm đi kèm môi trường từ vựng mà nó cần để hoạt động, bao gồm những biến bên ngoài được hàm tham chiếu. Trong nhiều ngôn ngữ, một lambda có thể trở thành closure khi nó sử dụng biến thuộc phạm vi bao quanh. Hai thuật ngữ có liên quan chặt chẽ nhưng không hoàn toàn đồng nghĩa.

## 1. Lambda là gì?

Lambda expression (biểu thức lambda) là cách viết một hàm ngay tại nơi cần dùng, thường không cần đặt tên hàm. Lambda có thể nhận tham số, thực hiện biểu thức hoặc khối lệnh và trả về kết quả theo quy tắc của ngôn ngữ.

Ví dụ bằng JavaScript:

```javascript
const double = x => x * 2;
const isPositive = number => number > 0;

console.log(double(5));       // 10
console.log(isPositive(-3));  // false
```

`x => x * 2` là một lambda nhận một tham số và trả về kết quả nhân đôi. Lambda có thể được gán cho biến, truyền vào hàm khác hoặc trả về từ một hàm.

### 1.1. Hàm có tên và lambda

Cùng một hành vi có thể được viết bằng hàm có tên hoặc lambda:

```javascript
function isExpensive(product) {
  return product.price > 1_000_000;
}

const isExpensiveLambda = product => product.price > 1_000_000;
```

Hàm có tên phù hợp khi hành vi được tái sử dụng rộng rãi hoặc cần một tên mô tả rõ mục đích. Lambda hữu ích khi hành vi ngắn, gắn với một thao tác cụ thể hoặc được truyền làm đối số cho một API.

Không nên mặc định lambda luôn ngắn hoặc luôn chỉ có một dòng. Nhiều ngôn ngữ cho phép lambda có khối lệnh nhiều câu lệnh. Điều quan trọng là biểu thức được tạo ra như một giá trị hàm theo cú pháp của ngôn ngữ.

### 1.2. Hàm là giá trị hạng nhất

Trong ngôn ngữ hỗ trợ hàm hạng nhất (first-class functions), hàm có thể được xử lý giống các giá trị khác: gán cho biến, truyền làm tham số, trả về từ hàm hoặc lưu trong cấu trúc dữ liệu.

Ví dụ:

```javascript
function apply(value, operation) {
  return operation(value);
}

const result = apply(7, number => number * number);
console.log(result); // 49
```

`apply` không cần biết chi tiết phép toán. Nó nhận một hàm `operation` và gọi hàm đó với giá trị đầu vào. Cách tách này giúp một hàm tổng quát có thể dùng với nhiều hành vi khác nhau.

## 2. Kiểu hàm và cách truyền lambda

Một lambda có kiểu được xác định bởi các tham số và kiểu kết quả. Ví dụ, một hàm nhận số nguyên và trả về Boolean có thể được mô tả khái quát là:

```text
(Integer) -> Boolean
```

Kiểu hàm giúp API diễn đạt rõ hành vi mà nó cần nhận. Một số dạng thường gặp:

| Kiểu hàm | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| `() -> Unit` | Không nhận tham số, không trả kết quả có ý nghĩa | Callback sau khi hoàn tất |
| `(Order) -> Boolean` | Nhận đơn hàng và trả về điều kiện đúng/sai | Lọc đơn hàng |
| `(Product, Integer) -> Money` | Nhận sản phẩm và số lượng, trả về tiền | Tính thành tiền |
| `(Request) -> Response` | Chuyển yêu cầu thành phản hồi | Xử lý request |
| `() -> T` | Tạo ra một giá trị kiểu `T` khi được gọi | Khởi tạo trì hoãn |

Ví dụ với Kotlin:

```kotlin
val isPaid: (Order) -> Boolean = { order ->
    order.status == OrderStatus.PAID
}

val paidOrders = orders.filter(isPaid)
```

Biến `isPaid` giữ một hàm nhận `Order` và trả về `Boolean`. Hàm `filter` nhận predicate này để quyết định phần tử nào được giữ lại.

Lambda cũng có thể nhận nhiều tham số hoặc không có tham số:

```kotlin
val add: (Int, Int) -> Int = { a, b -> a + b }
val onComplete: () -> Unit = { println("Completed") }
```

## 3. Closure là gì?

Một hàm có thể sử dụng biến được khai báo bên ngoài thân hàm. Khi hàm tiếp tục sử dụng được những biến đó sau khi phạm vi khai báo ban đầu đã kết thúc, hàm cần mang theo môi trường thích hợp. Tổ hợp giữa hàm và môi trường từ vựng mà nó tham chiếu được gọi là **closure**.

Ví dụ JavaScript:

```javascript
function makeMinimumRule(minimum) {
  return order => order.total >= minimum;
}

const atLeastOneMillion = makeMinimumRule(1_000_000);

console.log(atLeastOneMillion({ total: 1_200_000 })); // true
console.log(atLeastOneMillion({ total: 800_000 }));   // false
```

Lambda `order => order.total >= minimum` sử dụng biến `minimum` được khai báo trong hàm `makeMinimumRule`. Khi `makeMinimumRule` kết thúc, hàm được trả về vẫn có thể đọc giá trị `minimum` tương ứng với lần tạo closure đó. Môi trường này được giữ lại để hàm hoạt động về sau.

Có thể gọi `atLeastOneMillion` nhiều lần với các đơn hàng khác nhau. Mỗi lần gọi vẫn sử dụng ngưỡng đã được ghi nhận khi closure được tạo.

### 3.1. Môi trường từ vựng (lexical environment)

Phạm vi từ vựng được xác định bởi vị trí một đoạn mã được viết trong chương trình. Closure tra cứu các biến bên ngoài theo môi trường từ vựng đó, không phải đơn giản theo nơi hàm được gọi.

```javascript
const message = "Xin chào";

function createGreeter() {
  const name = "Lan";
  return () => `${message}, ${name}!`;
}

const greetLan = createGreeter();
console.log(greetLan()); // Xin chào, Lan!
```

Closure sử dụng `message` từ phạm vi bên ngoài và `name` từ lần gọi `createGreeter`. Dù hàm được gọi sau khi `createGreeter` đã trả về, nó vẫn có thể truy cập các binding cần thiết.

### 3.2. Closure có thể được trả về hoặc lưu trữ

Closure không chỉ được truyền ngay vào một hàm. Nó có thể được lưu trong biến, thuộc tính đối tượng, danh sách callback hoặc trả về từ một hàm khác. Điều này cho phép tạo hành vi được cấu hình bằng dữ liệu tại thời điểm khởi tạo.

Ví dụ, tạo bộ đếm độc lập:

```javascript
function makeCounter() {
  let count = 0;

  return () => {
    count += 1;
    return count;
  };
}

const firstCounter = makeCounter();
const secondCounter = makeCounter();

console.log(firstCounter());  // 1
console.log(firstCounter());  // 2
console.log(secondCounter()); // 1
```

Mỗi lần gọi `makeCounter` tạo một môi trường riêng. `firstCounter` và `secondCounter` giữ trạng thái đếm độc lập. Đây là ví dụ về closure vừa giữ hành vi vừa giữ trạng thái.

## 4. Lambda và closure khác nhau thế nào?

Lambda nói về **cách tạo hoặc biểu đạt một hàm**; closure nói về **mối liên hệ giữa hàm và môi trường mà nó cần**. Trong một số ngôn ngữ, lambda không tham chiếu biến bên ngoài nên không cần capture môi trường. Trong nhiều ngôn ngữ khác, lambda có tham chiếu biến bên ngoài và được thực hiện như closure.

| Khía cạnh | Lambda | Closure |
|---|---|---|
| Trọng tâm | Biểu thức tạo hàm, thường không có tên | Hàm cùng môi trường từ vựng được capture |
| Biến bên ngoài | Có thể không sử dụng biến bên ngoài | Giữ quyền truy cập đến binding bên ngoài cần thiết |
| Trạng thái | Có thể thuần túy, không giữ trạng thái riêng | Có thể giữ và sử dụng trạng thái từ môi trường |
| Vòng đời | Phụ thuộc cách tạo và lưu hàm | Môi trường cần thiết có thể sống lâu hơn phạm vi ban đầu |
| Quan hệ | Lambda có thể tạo ra closure | Closure có thể được tạo bằng lambda hoặc hàm lồng có tên |

Thuật ngữ không được dùng hoàn toàn giống nhau trong mọi ngôn ngữ và tài liệu. Có hệ sinh thái gọi các hàm lambda có capture là closure; có ngôn ngữ xem mọi hàm lồng có thể truy cập môi trường ngoài là closure. Vì vậy, khi đọc tài liệu một ngôn ngữ, cần xem định nghĩa và quy tắc capture cụ thể của ngôn ngữ đó.

## 5. Capture biến bên ngoài hoạt động ra sao?

**Capture** là việc một hàm giữ quyền truy cập đến biến nằm ngoài phạm vi cục bộ của nó. Cách capture có thể khác nhau giữa các ngôn ngữ: có nơi capture binding, có nơi yêu cầu chỉ rõ capture theo giá trị hoặc tham chiếu, có nơi giới hạn biến được capture.

### 5.1. JavaScript: truy cập binding theo phạm vi từ vựng

JavaScript sử dụng lexical scope. Hàm lồng có thể đọc binding bên ngoài và có thể thay đổi binding đó nếu quy tắc phạm vi cho phép.

```javascript
function makeSequence(start) {
  let current = start;

  return () => {
    current += 1;
    return current;
  };
}

const nextNumber = makeSequence(10);
console.log(nextNumber()); // 11
console.log(nextNumber()); // 12
```

Closure giữ binding `current`, vì vậy các lần gọi tiếp theo nhìn thấy giá trị đã được cập nhật. Nếu tạo một sequence khác, nó có binding riêng.

### 5.2. Java: biến cục bộ được capture phải final hoặc effectively final

Java lambda có thể tham chiếu biến cục bộ bên ngoài nếu biến đó là `final` hoặc effectively final (được gán một lần và không bị gán lại sau đó).

```java
int minimum = 1_000_000;

Predicate<Order> isLargeOrder = order ->
    order.total() >= minimum;
```

Biến `minimum` được capture trong lambda. Java không cho phép gán lại biến cục bộ `minimum` sau khi nó đã được sử dụng theo cách capture này. Điều đó không có nghĩa đối tượng được tham chiếu luôn bất biến: nếu biến là tham chiếu đến một đối tượng mutable, trạng thái bên trong đối tượng vẫn có thể thay đổi theo quy tắc của đối tượng.

### 5.3. Kotlin: lambda có thể truy cập biến bên ngoài

Kotlin cho phép lambda tham chiếu các biến ở phạm vi bao quanh:

```kotlin
fun makeThresholdPredicate(threshold: Int): (Int) -> Boolean {
    return { value -> value >= threshold }
}

val atLeastTen = makeThresholdPredicate(10)
println(atLeastTen(12)) // true
```

Lambda được trả về vẫn sử dụng `threshold` sau khi hàm tạo đã kết thúc. Kotlin cũng cho phép lambda truy cập biến cục bộ mutable theo quy tắc capture của ngôn ngữ.

### 5.4. C++: capture list chỉ rõ cách capture

C++ dùng capture list để cho biết lambda cần sử dụng biến bên ngoài nào và cách capture chúng:

```cpp
int minimum = 100;

auto isLarge = [minimum](int value) {
    return value >= minimum;
};

auto isLargeByReference = [&minimum](int value) {
    return value >= minimum;
};
```

`[minimum]` capture biến theo giá trị; `[&minimum]` capture theo tham chiếu. Capture theo tham chiếu đòi hỏi quản lý vòng đời cẩn thận: không được sử dụng tham chiếu sau khi đối tượng gốc đã hết vòng đời. Capture list tường minh giúp người đọc nhìn thấy sự phụ thuộc của lambda.

### 5.5. Ruby: block, Proc và lambda có thể giữ binding

Ruby có block, `Proc` và `lambda` để biểu đạt hành vi. Chúng có thể truy cập biến cục bộ được khai báo trong phạm vi bao quanh:

```ruby
minimum = 1_000_000
is_large_order = ->(order) { order.total >= minimum }

puts is_large_order.call(order)
```

Lambda giữ khả năng truy cập biến `minimum` theo môi trường từ vựng. Ruby còn có một số khác biệt về cách `lambda` và `Proc` xử lý số lượng tham số và `return`/`break`; không nên coi chúng là hoàn toàn đồng nhất.

## 6. Capture theo giá trị, tham chiếu và trạng thái có thể thay đổi

Khi một closure sử dụng dữ liệu bên ngoài, cần hiểu nó giữ gì và các lần gọi sau nhìn thấy thay đổi như thế nào. Đây là vấn đề quan trọng với callback, xử lý bất đồng bộ và DSL được thực thi ở thời điểm khác với lúc khai báo.

### 6.1. Capture giá trị

Với capture theo giá trị, lambda giữ một bản sao của giá trị tại thời điểm capture theo quy tắc của ngôn ngữ. Những thay đổi sau đó ở biến gốc không nhất thiết ảnh hưởng đến bản sao mà lambda sử dụng.

```cpp
int threshold = 50;
auto predicate = [threshold](int value) {
    return value > threshold;
};
threshold = 100;
// predicate vẫn sử dụng giá trị threshold đã capture là 50
```

Đây là hành vi capture theo giá trị trong C++. Với kiểu dữ liệu phức tạp, cần xem xét chi phí sao chép và liệu bản sao có chứa tham chiếu đến dữ liệu mutable khác hay không.

### 6.2. Capture tham chiếu hoặc binding dùng chung

Với capture theo tham chiếu, closure truy cập đối tượng hoặc binding gốc. Thay đổi có thể được nhìn thấy qua closure và ngược lại. Điều này hữu ích khi cần cập nhật trạng thái chung, nhưng dễ gây lỗi nếu nhiều nơi thay đổi cùng dữ liệu.

```cpp
int count = 0;
auto increment = [&count]() {
    ++count;
};

increment();
// count hiện là 1
```

Trong JavaScript, ví dụ `makeCounter` ở trên cho thấy nhiều lần gọi closure cùng truy cập binding `count`. Đây là một cách quản lý trạng thái cục bộ mà không cần công khai biến ra bên ngoài.

### 6.3. Capture tham chiếu và vòng đời

Closure có thể tồn tại lâu hơn hàm hoặc khối đã tạo ra nó. Một số ngôn ngữ tự quản lý môi trường cần thiết; ngôn ngữ khác cho phép tham chiếu không sở hữu và yêu cầu lập trình viên bảo đảm đối tượng còn sống.

Rủi ro thường gặp gồm:

- Trả về lambda tham chiếu đến biến cục bộ đã hết vòng đời trong C++.
- Giữ callback quá lâu khiến closure giữ các đối tượng lớn và làm tăng mức sử dụng bộ nhớ.
- Closure giữ tham chiếu đến đối tượng giao diện hoặc dịch vụ lâu hơn dự kiến, tạo vòng tham chiếu hoặc rò rỉ tài nguyên tùy môi trường.
- Callback bất đồng bộ chạy sau khi trạng thái mà nó cần đã bị thay đổi hoặc giải phóng.

### 6.4. Trạng thái mutable và tính đồng thời

Nếu nhiều luồng hoặc tác vụ bất đồng bộ cùng gọi closure có trạng thái mutable, các cập nhật có thể xung đột. Cần đồng bộ hóa, dùng cấu trúc dữ liệu an toàn luồng hoặc thiết kế closure thuần túy không thay đổi trạng thái dùng chung.

Closure giúp đóng gói trạng thái, nhưng không tự động làm trạng thái đó an toàn khi truy cập đồng thời.

## 7. Lambda và closure trong DSL nội bộ

Lambda đặc biệt hữu ích cho DSL nội bộ vì thư viện có thể nhận một khối biểu thức do người dùng cung cấp. Closure cho phép khối biểu thức đó sử dụng dữ liệu và tham số đã có trong ngữ cảnh bao quanh.

Thay vì cung cấp nhiều hàm riêng cho mọi trường hợp, DSL có thể đưa ra một cấu trúc tổng quát như:

```text
filter { <điều kiện> }
where { <điều kiện> }
when { <điều kiện> }
then { <hành động> }
```

Người viết đặt biểu thức vào lambda; thư viện quyết định khi nào và trong ngữ cảnh nào lambda được gọi.

### 7.1. Dùng lambda để truyền điều kiện

Ví dụ Kotlin:

```kotlin
data class Order(val total: Long, val paid: Boolean)

fun selectOrders(
    orders: List<Order>,
    condition: Order.() -> Boolean
): List<Order> = orders.filter { order -> order.condition() }

val selected = selectOrders(orders) {
    total >= 1_000_000 && paid
}
```

`condition` là lambda có receiver kiểu `Order`. Bên trong khối, `total` và `paid` được truy cập như các thuộc tính của `Order`. Hàm `selectOrders` gọi lambda cho từng đơn hàng để quyết định có giữ lại đơn đó hay không.

Đây là cách tạo cú pháp gần với miền: người viết tập trung vào điều kiện của đơn hàng, còn thư viện đảm nhận vòng lặp và việc tạo danh sách kết quả.

### 7.2. Dùng closure để cấu hình quy tắc

Một DSL có thể tạo quy tắc dựa trên một tham số bên ngoài:

```javascript
function minimumOrderValueRule(minimum) {
  return order => order.total >= minimum;
}

const premiumOrderRule = minimumOrderValueRule(2_000_000);
const eligibleOrders = orders.filter(premiumOrderRule);
```

`premiumOrderRule` là hàm đã được cấu hình với ngưỡng 2.000.000. Closure giữ ngưỡng đó để dùng khi lọc từng đơn. Thư viện có thể cho phép người dùng tạo nhiều quy tắc khác nhau từ cùng một hàm tạo.

### 7.3. Dùng lambda có receiver để tạo DSL khai báo trong Kotlin

Kotlin hỗ trợ function type có receiver, thường được dùng để tạo DSL lồng nhau. Ví dụ:

```kotlin
class OrderRuleBuilder {
    var minimumTotal: Long = 0
    var mustBePaid: Boolean = false
}

fun orderRule(block: OrderRuleBuilder.() -> Unit): OrderRuleBuilder {
    val builder = OrderRuleBuilder()
    builder.block()
    return builder
}

val rule = orderRule {
    minimumTotal = 1_000_000
    mustBePaid = true
}
```

Lambda `OrderRuleBuilder.() -> Unit` chạy với `OrderRuleBuilder` làm receiver. Vì vậy, bên trong block có thể gán `minimumTotal` và `mustBePaid` mà không phải viết `builder.` trước mỗi thuộc tính. Hàm `orderRule` tạo builder, gọi block trên builder đó rồi trả về cấu hình.

Ví dụ này minh họa một builder DSL. Trong hệ thống thực tế, nên xác thực giá trị sau khi cấu hình và có thể trả về một đối tượng quy tắc bất biến thay vì để builder mutable tiếp tục được dùng.

### 7.4. Closure giúp tạo callback có ngữ cảnh

Một DSL có thể nhận callback được gọi khi một sự kiện xảy ra:

```javascript
function onStatusChange(expectedStatus, callback) {
  return order => {
    if (order.status === expectedStatus) {
      callback(order);
    }
  };
}

const notifyPaidOrder = onStatusChange("PAID", order => {
  console.log(`Order ${order.id} has been paid`);
});
```

Callback có thể sử dụng biến `expectedStatus` và tham số `order`. Closure giúp giữ điều kiện đã cấu hình để hàm xử lý sự kiện có thể được gọi về sau.

## 8. Thực thi ngay hay trì hoãn lambda?

Khi truyền lambda cho DSL, cần hiểu thư viện sẽ gọi nó ngay hay lưu lại để chạy sau. Sự khác biệt này ảnh hưởng đến thời điểm đọc dữ liệu, tác dụng phụ và giá trị mà closure nhìn thấy.

### 8.1. Thực thi ngay (eager)

Ví dụ `filter` thông thường gọi predicate trong lúc duyệt danh sách và trả về kết quả đã tính. Nếu lambda capture biến mutable, giá trị được đọc tại thời điểm lambda được gọi.

### 8.2. Thực thi trì hoãn (lazy hoặc deferred)

Một query builder có thể lưu predicate để chỉ chạy khi người dùng yêu cầu kết quả. Một callback có thể được gọi sau khi cấu hình đã hoàn tất. Khi đó, biến được closure capture có thể đã thay đổi kể từ thời điểm khai báo.

```javascript
let minimum = 100;
const predicate = item => item.value >= minimum;

minimum = 500;
// Nếu predicate được gọi ở đây, nó đọc binding minimum hiện tại.
console.log(predicate({ value: 300 })); // false
```

Lambda được tạo khi `minimum` bằng 100, nhưng nó tham chiếu binding `minimum`. Khi gọi sau khi biến đã đổi thành 500, biểu thức sử dụng giá trị hiện tại theo ngữ nghĩa JavaScript.

Với DSL trì hoãn, cần xác định có chủ đích liệu quy tắc sẽ dùng snapshot của cấu hình tại thời điểm khai báo hay đọc trạng thái mới ở thời điểm thực thi. Nếu cần snapshot, hãy capture một giá trị bất biến hoặc sao chép cấu hình theo cách phù hợp.

## 9. Tác dụng phụ và tính thuần khiết

Lambda có thể chỉ tính toán và trả kết quả, hoặc có thể thay đổi trạng thái, ghi log, gọi mạng và thực hiện các tác động khác. Với DSL khai báo, lambda thuần túy thường dễ kiểm tra và tối ưu hơn.

**Hàm thuần túy (pure function)** có hai đặc điểm chính: cùng đầu vào cho cùng kết quả, và không tạo tác dụng phụ quan sát được. Ví dụ:

```kotlin
val isLargeOrder: (Order) -> Boolean = { order ->
    order.total >= 1_000_000
}
```

Lambda này chỉ đọc dữ liệu đơn hàng và trả về Boolean. Ngược lại:

```kotlin
val processOrder: (Order) -> Unit = { order ->
    database.save(order)
    emailService.sendReceipt(order)
}
```

Lambda thứ hai tạo tác dụng phụ. Nếu DSL lưu nó để thực thi sau, cần xác định rõ thời điểm, số lần gọi, cách xử lý lỗi và khả năng thử lại. Một callback có thể bị gọi nhiều lần trong một quy trình retry; nếu gửi email không có cơ chế idempotency, người dùng có thể nhận nhiều email trùng lặp.

Với DSL mô tả quy tắc hoặc truy vấn, nên tách phần điều kiện thuần túy khỏi hành động có tác động khi điều đó giúp kiểm soát và kiểm thử tốt hơn.

## 10. Phạm vi lambda lồng nhau và shadowing

Khi DSL sử dụng nhiều lambda lồng nhau, có thể xuất hiện nhiều tham số hoặc receiver cùng tên. Điều này làm biểu thức khó đọc hoặc khiến người viết vô tình tham chiếu sai đối tượng.

Ví dụ JavaScript:

```javascript
orders.forEach(order => {
  order.lines.forEach(line => {
    console.log(order.id, line.quantity);
  });
});
```

Đặt tên `order` và `line` rõ ràng giúp phân biệt hai phạm vi. Trong DSL có receiver lồng nhau, vấn đề có thể khó nhận ra hơn vì tên thuộc tính được truy cập ngầm.

Kotlin cho phép dùng label để chỉ rõ receiver bên ngoài:

```kotlin
orders.forEach { order ->
    order.lines.forEach { line ->
        println("${order.id}: ${line.quantity}")
    }
}
```

Khi dùng lambda có receiver lồng nhau, có thể đặt tên label và tham chiếu rõ như `this@orderBlock` hoặc dùng tham số tường minh. Nên tránh lồng quá nhiều tầng nếu người đọc phải liên tục suy luận receiver hiện tại.

## 11. Những lỗi thường gặp khi dùng lambda và closure

| Lỗi | Nguyên nhân | Cách hạn chế |
|---|---|---|
| Capture biến mutable thay đổi ngoài dự kiến | Closure đọc binding dùng chung tại thời điểm thực thi | Dùng snapshot bất biến hoặc truyền dữ liệu rõ ràng |
| Closure giữ đối tượng quá lâu | Callback được lưu lâu hơn vòng đời dự kiến | Hủy đăng ký callback và giới hạn tham chiếu |
| Capture tham chiếu đã hết vòng đời | Thường gặp khi capture theo tham chiếu trong C++ | Bảo đảm đối tượng sống đủ lâu hoặc capture theo giá trị phù hợp |
| Chia sẻ trạng thái giữa nhiều luồng | Nhiều lời gọi cùng cập nhật binding hoặc đối tượng mutable | Đồng bộ hóa hoặc loại bỏ trạng thái dùng chung |
| Lambda quá dài | Trộn nhiều bước nghiệp vụ trong một biểu thức | Tách thành hàm có tên và giữ lambda ngắn gọn |
| Lambda lồng nhau khó hiểu | Nhiều receiver hoặc biến cùng tên | Dùng tên tham số rõ ràng, label và giảm độ sâu lồng |
| Tác dụng phụ không được dự đoán | DSL lưu lambda rồi gọi nhiều lần hoặc gọi muộn | Định nghĩa rõ thời điểm, số lần gọi và chính sách retry |
| Nhầm lambda với closure | Không phân biệt biểu thức hàm với môi trường capture | Xác định biến bên ngoài mà hàm cần sử dụng |

## 12. Nguyên tắc thiết kế lambda API cho DSL

Khi xây dựng DSL nội bộ, lambda API nên có hợp đồng rõ ràng để người dùng dự đoán được hành vi.

1. **Đặt kiểu hàm rõ ràng.** Cho biết lambda nhận đối tượng nào, trả kết quả gì và có được phép không trả kết quả hay không.
2. **Định nghĩa thời điểm thực thi.** Nêu rõ lambda được gọi ngay, khi duyệt dữ liệu hay khi một tác vụ được kích hoạt sau đó.
3. **Quy định số lần gọi.** Một predicate có thể được gọi một lần cho mỗi phần tử; callback có thể được gọi một hoặc nhiều lần tùy luồng sự kiện.
4. **Làm rõ ngữ nghĩa capture.** Giải thích cấu hình được đọc theo snapshot hay theo trạng thái hiện tại khi lambda chạy.
5. **Giới hạn tác dụng phụ khi cần.** Với DSL khai báo, ưu tiên predicate thuần túy và tách hành động có tác động.
6. **Tránh receiver mơ hồ.** Đặt tên tham số hoặc label rõ ràng khi có nhiều lambda lồng nhau.
7. **Cung cấp lỗi dễ hiểu.** Khi biểu thức không hợp lệ, chỉ rõ kiểu đầu vào, điều kiện hoặc ngữ cảnh gây lỗi.
8. **Kiểm thử trường hợp biên.** Kiểm tra lambda capture biến, callback chạy muộn, gọi lặp, lỗi trong callback và truy cập đồng thời.

## 13. Khi nào nên dùng lambda, closure hoặc hàm có tên?

| Tình huống | Cách biểu đạt thường phù hợp |
|---|---|
| Một thao tác ngắn chỉ dùng tại một điểm | Lambda tại chỗ |
| Một điều kiện cần truyền cho `filter`, `map` hoặc API tương tự | Lambda nhận tham số rõ ràng |
| Hành vi cần nhớ cấu hình được tạo trước đó | Closure capture cấu hình |
| Hành vi dài, có nhiều bước hoặc cần tái sử dụng rộng | Hàm có tên |
| Cần giữ trạng thái riêng giữa các lần gọi | Closure có trạng thái hoặc đối tượng chuyên biệt |
| Cần kiểm soát kiểu và trạng thái phức tạp | Kiểu đối tượng hoặc interface tường minh |

Không nên dùng closure chỉ để che giấu một lượng lớn trạng thái. Nếu hành vi có nhiều phụ thuộc, vòng đời hoặc tác động phụ, một lớp hoặc đối tượng có tên với API rõ ràng có thể dễ bảo trì hơn.

## 14. Kết luận

Lambda là biểu thức tạo hàm, giúp truyền hành vi như một giá trị. Closure là hàm đi cùng môi trường từ vựng mà nó cần, cho phép hàm tiếp tục sử dụng các biến bên ngoài sau khi phạm vi tạo ra nó kết thúc. Lambda có thể tạo thành closure khi capture biến, nhưng closure cũng có thể được tạo bởi hàm lồng có tên.

Trong DSL nội bộ, lambda giúp thư viện nhận điều kiện, hành động và cấu trúc do người dùng khai báo; closure giúp những biểu thức đó giữ cấu hình hoặc ngữ cảnh cần thiết. Để thiết kế an toàn và dễ hiểu, cần quy định rõ kiểu hàm, biến được capture, vòng đời, thời điểm thực thi, tác dụng phụ và cách xử lý trạng thái dùng chung.
