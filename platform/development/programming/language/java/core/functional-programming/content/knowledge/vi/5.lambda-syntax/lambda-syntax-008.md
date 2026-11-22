# Viết lambda ngắn, đặt tên tham số rõ nghĩa và tách thân quá dài

Lambda là cú pháp gọn để biểu diễn một hành vi phù hợp với **functional interface** trong Java. Nhưng “ngắn” không chỉ có nghĩa ít ký tự hoặc viết trên một dòng: điều quan trọng là **người đọc nhận ra mục đích của lambda nhanh**, thấy rõ đầu vào và đầu ra, và không phải giải mã nhiều tầng điều kiện hay tác dụng phụ bên trong.

Bài học này tập trung vào ba kỹ năng khi viết Java 17+: **giữ lambda có một trách nhiệm dễ hiểu; đặt tên tham số phản ánh dữ liệu; tách thân quá dài thành phương thức có tên, hàm nhỏ hoặc các bước trung gian hợp lý**. Cùng một nguyên tắc được áp dụng cho Stream API, Comparator, Predicate, Function và Consumer, có đối chiếu trước–sau và chương trình hoàn chỉnh.

## 1. Thế nào là lambda dễ đọc?

Xét hai cách kiểm tra một số:

~~~java
java.util.function.Predicate<Integer> check = x -> x > 0;
java.util.function.Predicate<Integer> isPositive =
    number -> number > 0;
~~~

Hai biểu thức có hành vi giống nhau. Với lambda rất nhỏ, tên x có thể chấp nhận được trong một đoạn đại số đơn giản. Nhưng isPositive và number làm rõ vai trò của điều kiện mà không cần lần theo tất cả ngữ cảnh.

Lambda tốt thường có các đặc điểm:

1. **Một ý định chính:** lọc, biến đổi, so sánh, kiểm tra hoặc thực hiện một hành động rõ ràng.
2. **Tên tham số gợi ngữ nghĩa:** order, customer, product, left, right, entry, index, thay vì những tên mơ hồ khi logic đủ phức tạp.
3. **Thân ngắn trong ngữ cảnh:** người đọc không phải nhảy qua nhiều nhánh if, try/catch hoặc chuỗi biểu thức lồng nhau để hiểu một callback.
4. **Đầu ra và tác dụng phụ rõ:** Predicate trả boolean; Function trả giá trị biến đổi; Consumer thực hiện hành động, thường có tác dụng phụ.
5. **Không lặp logic:** quy tắc nghiệp vụ dùng ở nhiều nơi có tên riêng hoặc được tách ra.
6. **Không tạo trừu tượng giả:** một phép tính hiển nhiên có thể viết inline; không bắt buộc tạo phương thức cho mọi lambda một dòng.

Ví dụ ngắn, đúng ngữ cảnh:

~~~java
items.stream().filter(item -> item.inStock()).toList();
~~~

Nếu kiểu items đã rõ, item là tên đủ ý nghĩa. Việc biến biểu thức đơn giản này thành nhiều lớp phương thức chỉ để giảm độ dài lambda có thể khiến mã khó tra cứu hơn.

**Tiêu chí đánh giá là khả năng hiểu và sửa mã an toàn**, không phải số ký tự cố định cho mọi lambda.

## 2. Cú pháp lambda liên quan đến khả năng đọc

Lambda có dạng tổng quát:

~~~text
(parameters) -> expression
(parameters) -> { statements; }
~~~

Trong Java, các trường hợp thường gặp:

| Dạng | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| Không tham số | () -> "ready" | Supplier hoặc Runnable |
| Một tham số, biểu thức đơn | customer -> customer.active() | Predicate, Function |
| Hai tham số | (left, right) -> left.compareTo(right) | Comparator, BiFunction |
| Thân khối | order -> { ... return result; } | Cần vài câu lệnh để thực hiện một ý định |
| Method reference | String::trim | Gọi trực tiếp phương thức sẵn có tương thích |

Một tham số có kiểu suy luận thường có thể bỏ dấu ngoặc: item -> item.name(). Với hai tham số phải có ngoặc: (left, right) -> .... Kiểu tham số thường được compiler suy ra từ **target type** của functional interface:

~~~java
java.util.function.Function<String, Integer> length =
    text -> text.length();
~~~

Ở đây text có kiểu String vì target là Function<String,Integer>. Viết rõ kiểu khi cần giải quyết nhập nhằng, làm sáng tỏ một API khó hoặc theo chuẩn dự án; không cần lặp kiểu khi ngữ cảnh đã cung cấp đầy đủ.

Khi dùng thân khối, một lambda trả giá trị phải có return ở các đường đi phù hợp:

~~~java
java.util.function.Function<Integer, String> parity = number -> {
    if (number % 2 == 0) {
        return "even";
    }
    return "odd";
};
~~~

Với biểu thức đơn, không dùng return hoặc dấu chấm phẩy bên trong lambda:

~~~java
java.util.function.Function<Integer, String> parity =
    number -> number % 2 == 0 ? "even" : "odd";
~~~

Dạng ternary này vẫn còn dễ đọc vì chỉ có hai nhánh đơn giản. Nếu có nhiều điều kiện hoặc biểu thức lồng nhau, một phương thức đặt tên rõ ràng sẽ tốt hơn.

## 3. Đặt tên tham số theo vai trò, không chỉ theo kiểu

### 3.1. Tên trong xử lý nghiệp vụ

Khó đọc:

~~~java
orders.stream()
    .filter(x -> x.paid() && x.units() > 0)
    .map(x -> x.id())
    .toList();
~~~

Rõ nghĩa hơn:

~~~java
orders.stream()
    .filter(order -> order.paid() && order.units() > 0)
    .map(Order::id)
    .toList();
~~~

Ở đây orders đã là một nguồn dữ liệu về đơn hàng; order cho biết mỗi phần tử đang được kiểm tra. Trong pipeline gồm nhiều kiểu phần tử liên tiếp, tên giúp tránh nhầm đối tượng hiện tại là Order, String hay kết quả trung gian.

Với lambda lồng nhau, tên tham số đặc biệt quan trọng:

~~~java
customers.stream()
    .filter(customer -> customer.orders().stream()
        .anyMatch(order -> order.paid()))
    .toList();
~~~

customer và order phân biệt hai cấp dữ liệu. Không đặt cả hai là x, hoặc đặt tên gây hiểu nhầm như customer cho một đối tượng Order.

**Các đoạn dùng Order/Customer ở trên là mã minh họa** và cần các kiểu tương ứng trong dự án; chương trình tự chạy độc lập xuất hiện ở phần 9.

### 3.2. Tên có tính đối xứng cho phép so sánh

Với Comparator:

~~~java
java.util.Comparator<String> alphabetically =
    (left, right) -> left.compareTo(right);
~~~

left và right biểu thị hai phía của phép so sánh. Trong một comparator nghiệp vụ, dùng firstOrder/secondOrder hoặc leftOrder/rightOrder nếu giúp rõ hơn:

~~~java
java.util.Comparator<Order> byUnits =
    (firstOrder, secondOrder) ->
        Integer.compare(firstOrder.units(), secondOrder.units());
~~~

Không trừ số nguyên trực tiếp để so sánh:

~~~java
// Tránh vì có thể tràn số:
(a, b) -> a.units() - b.units()
~~~

Khi ý định đơn giản hơn, dùng comparator có sẵn sẽ rõ và an toàn:

~~~java
java.util.Comparator<Order> byUnits =
    java.util.Comparator.comparingInt(Order::units);
~~~

### 3.3. Tên phản ánh cặp key/value hoặc current/next

Với Map.forEach:

~~~java
totals.forEach((customerName, totalAmount) ->
    System.out.println(customerName + ": " + totalAmount));
~~~

Tên k, v có thể chấp nhận ở vòng lặp đơn giản, nhưng customerName và totalAmount giúp kiểm tra ý định cập nhật/ghi log. Với Map.merge, hai tham số của BiFunction là **giá trị cũ và giá trị mới**, không phải key/value:

~~~java
totals.merge(customerName, amount,
    (currentTotal, addedAmount) -> currentTotal + addedAmount);
~~~

Chữ ký Map.merge rất quan trọng: đặt tên key, value cho lambda trên sẽ làm người đọc hiểu sai hợp đồng.

### 3.4. Quy tắc đặt tên thực dụng

- Dùng danh từ số ít chỉ một phần tử: order, product, line, user.
- Dùng tên quan hệ khi có hai đối số: availableQuantity, requestedQuantity; currentValue, replacement.
- Chỉ dùng x, y, n, a, b trong biểu thức toán học ngắn, tự giải thích.
- Tránh tên vô nghĩa như data, item1, item2 khi có đủ ngữ cảnh nghiệp vụ tốt hơn.
- Không đánh đổi độ rõ nghĩa để tăng số từ trong tên quá mức.
- Giữ cùng thuật ngữ giữa record/class, biến và lambda nếu chúng biểu thị cùng khái niệm.

Compiler không đánh giá tên có “hay” hay không. Đây là một quyết định về tính dễ hiểu và giảm lỗi trong quá trình bảo trì.

## 4. Giữ thân lambda tập trung vào một hành vi

Một lambda dài thường không khó vì bản thân ký hiệu ->, mà vì nó chứa **nhiều trách nhiệm**.

Ví dụ cần lọc đơn hàng hợp lệ rồi tính giá trị. Cách viết dồn nhiều điều kiện và logic:

~~~java
// Ví dụ khó đọc, giả sử Order có các component tương ứng.
List<String> descriptions = orders.stream()
    .filter(order -> {
        if (!order.paid()) {
            return false;
        }
        if (order.units() <= 0) {
            return false;
        }
        if (order.unitPrice() < 0) {
            return false;
        }
        long amount = (long) order.units() * order.unitPrice();
        return amount >= 50;
    })
    .map(order -> order.id() + "="
        + ((long) order.units() * order.unitPrice()))
    .toList();
~~~

Đoạn này không sai về nguyên tắc, nhưng lambda filter vừa kiểm tra dữ liệu vừa tính giá trị; map lại tính công thức giá trị lần nữa. Người đọc phải rà từng nhánh mới biết vì sao đơn hàng được chọn.

Tách thành các hàm có tên:

~~~java
static boolean isEligible(Order order) {
    return order.paid()
        && order.units() > 0
        && order.unitPrice() >= 0;
}

static long amount(Order order) {
    return Math.multiplyExact(
        (long) order.units(), order.unitPrice());
}
~~~

Pipeline có thể trở nên rõ hơn:

~~~java
List<String> descriptions = orders.stream()
    .filter(LambdaStyleDemo::isEligible)
    .filter(order -> amount(order) >= 50)
    .map(order -> order.id() + "=" + amount(order))
    .toList();
~~~

- isEligible cho biết **vì sao** một order có hợp lệ hay không.
- amount gom công thức vào một nơi và dùng Math.multiplyExact để phát hiện tràn long.
- filter thứ hai giải thích ngưỡng nghiệp vụ 50, thay vì chôn trong nhiều điều kiện.
- map chỉ dựng chuỗi kết quả.

Không nên tách một lambda chỉ để giảm số dòng. Nếu thân khối bốn dòng thực hiện một thuật toán đơn giản, dễ hiểu và không lặp, giữ nguyên cũng hợp lý. Tách khi cần một tên nghiệp vụ, tái sử dụng, kiểm thử riêng, giảm độ lồng hoặc làm rõ tác dụng phụ.

## 5. Khi nào dùng method reference?

Method reference thường hợp lý khi lambda chỉ chuyển tiếp một lời gọi:

~~~java
java.util.function.Function<String, Integer> length =
    text -> text.length();
~~~

Có thể chuyển thành:

~~~java
java.util.function.Function<String, Integer> length = String::length;
~~~

Các dạng thông dụng:

| Dạng | Lambda | Method reference |
| --- | --- | --- |
| Static method | text -> Integer.parseInt(text) | Integer::parseInt |
| Instance method trên đối tượng đầu vào | text -> text.trim() | String::trim |
| Instance method trên đối tượng có sẵn | value -> printer.println(value) | printer::println |
| Constructor | () -> new ArrayList<String>() | ArrayList<String>::new |

Method reference không tự động dễ đọc hơn mọi lambda. Chỉ dùng nếu **tên phương thức biểu đạt đúng hành vi** và người đọc hiểu đối tượng nhận lời gọi. Ví dụ:

~~~java
orders.stream()
    .filter(LambdaStyleDemo::isEligible)
    .map(LambdaStyleDemo::describe)
    .toList();
~~~

Rõ hơn việc inlining một đoạn kiểm tra dài và ghép chuỗi phức tạp. Nhưng nếu lambda kết hợp một điều kiện và tham số ngữ cảnh như minAmount:

~~~java
.filter(order -> amount(order) >= minAmount)
~~~

giữ lambda là hợp lý. Không cần tạo một phương thức chỉ để cố thay bằng method reference; cũng có thể tạo Predicate đặt tên nếu điều kiện này xuất hiện nhiều nơi.

Lưu ý các trường hợp overload hoặc generics: compiler lựa chọn method reference dựa trên target type, nên đôi lúc lambda có tên tham số rõ ràng hơn và giúp xử lý lỗi suy luận kiểu.

## 6. Tách lambda dài thành phương thức, Predicate hay hàm nhỏ?

Có ba cách chính, không có một phương án thắng mọi hoàn cảnh.

### 6.1. Extract method cho quy tắc nghiệp vụ độc lập

Phù hợp khi logic cần tên rõ, có thể kiểm thử và không phụ thuộc vào nhiều biến cục bộ ở điểm gọi:

~~~java
static boolean isEligible(Order order) {
    return order.paid() && order.units() > 0;
}
~~~

Sau đó dùng:

~~~java
.filter(LambdaStyleDemo::isEligible)
~~~

Đặt tên theo ý định nghiệp vụ; isEligible tốt hơn check1 hoặc doFilter. Phương thức có thể là private nếu chỉ phục vụ lớp hiện tại.

### 6.2. Predicate đặt tên cho điều kiện phụ thuộc ngữ cảnh

Khi ngưỡng được truyền từ ngoài, có thể dùng một biến Predicate:

~~~java
java.util.function.Predicate<Order> expensiveEnough =
    order -> amount(order) >= minAmount;

List<Order> selected = orders.stream()
    .filter(expensiveEnough)
    .toList();
~~~

Biến minAmount được lambda capture và phải là final hoặc effectively final nếu là biến cục bộ. Cách này thích hợp khi tên expensiveEnough giúp giải thích ý định hoặc Predicate được kết hợp với điều kiện khác.

### 6.3. Dùng factory method cho điều kiện có tham số

Nếu cùng một quy tắc áp dụng với nhiều ngưỡng:

~~~java
static java.util.function.Predicate<Order> amountAtLeast(long threshold) {
    return order -> amount(order) >= threshold;
}
~~~

Rồi dùng:

~~~java
.filter(amountAtLeast(minAmount))
~~~

Factory method đặt tên cho hành vi được cấu hình bởi threshold. Không cần biến mọi biểu thức nhỏ thành factory; chỉ chọn khi giúp API dễ sử dụng hoặc quy tắc được dùng nhiều lần.

### 6.4. Dùng lớp riêng khi logic là chiến lược có trạng thái

Nếu xử lý cần cấu hình phức tạp, dependency injection, tái sử dụng rộng hoặc có vòng đời, một lớp triển khai interface có tên rõ ràng có thể hợp lý hơn lambda nhiều dòng. Ví dụ một chiến lược phân quyền cần policy repository, cache và audit, hoặc một bộ xử lý nhiều phương thức. Không ép các trách nhiệm đó vào một Function<Object,Object> dài.

## 7. Tách các bước của Stream thành pipeline dễ theo dõi

Một pipeline có thể có nhiều phép toán nhưng mỗi lambda vẫn ngắn. Để pipeline dễ đọc:

1. **Đọc từ trên xuống** theo thứ tự lọc → sắp xếp/biến đổi → tổng hợp khi phù hợp.
2. **Giữ mỗi phép toán có một mục đích.** filter kiểm tra; map biến đổi; sorted sắp xếp; collect/toList tạo kết quả.
3. **Đặt tên quy tắc đủ phức tạp** bằng method reference hoặc Predicate/Function.
4. **Giảm xử lý lồng nhau** khi một đoạn stream nhiều tầng che giấu quy tắc quan trọng.
5. **Không gộp tác dụng phụ vào map/filter** nếu có thể đặt bước I/O tại ranh giới rõ ràng.

Một pipeline ngắn có thể rất rõ:

~~~java
List<String> names = customers.stream()
    .filter(Customer::active)
    .map(Customer::name)
    .sorted()
    .toList();
~~~

Các kiểu Customer, tên phương thức active/name trong đoạn này là minh họa cho một mô hình dữ liệu giả định.

Một pipeline khác có nhiều phép biến đổi vẫn dễ đọc nếu tên đủ tốt:

~~~java
List<String> descriptions = orders.stream()
    .filter(LambdaStyleDemo::isEligible)
    .filter(order -> amount(order) >= minAmount)
    .sorted(Comparator.comparing(Order::customer)
        .thenComparing(Order::id))
    .map(LambdaStyleDemo::describe)
    .toList();
~~~

Cần phân biệt **độ dài của pipeline** và **độ dài của callback**. Một pipeline 6 dòng với bước rõ ràng có thể dễ hiểu hơn một lambda 15 dòng gói nhiều trách nhiệm. Nhưng pipeline quá dài vẫn cần xem xét tách thành các bước có tên hoặc một phương thức nghiệp vụ bao ngoài.

### 7.1. Khi tách biến trung gian hữu ích

Nếu một điều kiện hoặc comparator phức tạp:

~~~java
java.util.Comparator<Order> byCustomerThenId =
    Comparator.comparing(Order::customer)
        .thenComparing(Order::id);

java.util.function.Predicate<Order> meetsThreshold =
    order -> amount(order) >= minAmount;
~~~

Sau đó:

~~~java
return orders.stream()
    .filter(LambdaStyleDemo::isEligible)
    .filter(meetsThreshold)
    .sorted(byCustomerThenId)
    .map(LambdaStyleDemo::describe)
    .toList();
~~~

Đặt biến giúp người đọc nắm tên quy tắc, đồng thời debug/test theo từng phần. Không bắt buộc dùng biến nếu trực tiếp nhìn vẫn hiểu, vì việc nhảy qua nhiều biến chỉ được sử dụng một lần cũng có chi phí đọc.

## 8. Tránh “ngắn giả”: rút ký tự nhưng che giấu logic

### 8.1. Ternary lồng nhiều tầng

Khó đọc:

~~~java
java.util.function.Function<Integer, String> grade =
    score -> score >= 90 ? "A" : score >= 80 ? "B"
        : score >= 70 ? "C" : "D";
~~~

Cú pháp hợp lệ, nhưng nhiều toán tử ?: dễ bị đọc nhầm thứ tự và khó thêm điều kiện. Một phương thức có tên làm rõ các nhánh:

~~~java
static String toGrade(int score) {
    if (score >= 90) return "A";
    if (score >= 80) return "B";
    if (score >= 70) return "C";
    return "D";
}
~~~

Sau đó có thể dùng:

~~~java
java.util.function.IntFunction<String> grade = LambdaStyleDemo::toGrade;
~~~

Các đoạn trên là **mã minh họa cấu trúc**, cần đặt phương thức trong một lớp và kiểu đích phù hợp với ngữ cảnh. Điểm cần nhớ: số dòng nhiều hơn không nhất thiết là xấu nếu logic rõ và bảo trì dễ hơn.

### 8.2. Chèn ghi log, ghi database hoặc thay đổi trạng thái trong filter/map

Khó kiểm soát:

~~~java
List<String> names = orders.stream()
    .filter(order -> {
        System.out.println("Checking " + order.id());
        return order.paid();
    })
    .map(Order::id)
    .toList();
~~~

Code vừa lọc vừa in log. Trong Stream, việc thực thi pipeline có tính lazy; tối ưu và short-circuit có thể ảnh hưởng cách callback được gọi. Với parallel stream, thứ tự không nhất thiết ổn định. Nếu logging là nghiệp vụ bắt buộc, tách phần thu thập dữ liệu và tương tác ra các bước có hợp đồng rõ, tránh dựa vào số lần gọi map/filter.

Không phải logging luôn bị cấm trong lambda. Đôi khi callback Consumer được truyền vào forEach có mục đích chính là thực hiện tương tác. Nhưng **nên thể hiện tác dụng phụ có chủ đích** và xác định ngoại lệ, thứ tự, retry khi cần.

### 8.3. Lambda gọi một phương thức dài nhưng tên mơ hồ

~~~java
orders.stream().map(this::process).toList();
~~~

Đoạn này rất ngắn nhưng process không cho biết nó trả kết quả gì hoặc có ghi dữ liệu không. Tên như calculateNetAmount, normalizeCustomerName hoặc toReceiptLine sẽ hữu ích hơn nếu phản ánh đúng hành vi. Extract method không có giá trị nếu chỉ che logic mà không mang ý nghĩa.

## 9. Chương trình Java 17+ hoàn chỉnh

Bài toán: từ các đơn hàng, chọn đơn đã thanh toán và có dữ liệu hợp lệ, lọc theo ngưỡng tiền, sắp theo khách hàng và mã đơn, tạo mô tả. Đồng thời tính tổng tiền hợp lệ theo khách hàng. Mỗi lambda hoặc method reference trong pipeline chỉ thể hiện một nhiệm vụ.

Tạo tệp **LambdaStyleDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class LambdaStyleDemo {
    record Order(String id, String customer, int units,
                 int unitPrice, boolean paid) {}

    static boolean isEligible(Order order) {
        return order.paid() && order.units() > 0
            && order.unitPrice() >= 0;
    }

    static long amount(Order order) {
        return Math.multiplyExact((long) order.units(), order.unitPrice());
    }

    static String describe(Order order) {
        return order.id() + "/" + order.customer() + "=" + amount(order);
    }

    static List<String> summarize(List<Order> orders, long minAmount) {
        return orders.stream()
            .filter(LambdaStyleDemo::isEligible)
            .filter(order -> amount(order) >= minAmount)
            .sorted(Comparator.comparing(Order::customer)
                .thenComparing(Order::id))
            .map(LambdaStyleDemo::describe)
            .toList();
    }

    static Map<String, Long> totalsByCustomer(List<Order> orders) {
        return orders.stream()
            .filter(LambdaStyleDemo::isEligible)
            .collect(Collectors.groupingBy(
                Order::customer,
                TreeMap::new,
                Collectors.summingLong(LambdaStyleDemo::amount)
            ));
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-2", "Mai", 2, 30, true),
            new Order("O-1", "An", 3, 40, true),
            new Order("O-3", "An", 1, 20, false),
            new Order("O-4", "Lan", 4, 10, true),
            new Order("O-5", "Mai", 1, 50, true)
        );

        System.out.println(summarize(orders, 50));
        System.out.println(totalsByCustomer(orders));
        System.out.println("unchanged=" + orders.size());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp (JDK 17 trở lên):

~~~bash
javac LambdaStyleDemo.java
java LambdaStyleDemo
~~~

Stdout:

~~~text
[O-1/An=120, O-2/Mai=60, O-5/Mai=50]
{An=120, Lan=40, Mai=110}
unchanged=5
~~~

Giải thích:

- isEligible gom ba điều kiện: đã thanh toán, số lượng dương, đơn giá không âm. Đơn O-3 bị loại vì chưa thanh toán.
- amount là hàm riêng, dùng phép nhân long có kiểm tra tràn số. Nó được tái sử dụng trong lọc ngưỡng, mô tả đơn và tổng hợp.
- filter thứ hai giữ đơn có amount >= 50: O-1 = 120, O-2 = 60, O-5 = 50; O-4 = 40 không vượt ngưỡng.
- Comparator.comparing(Order::customer).thenComparing(Order::id) biểu diễn thứ tự rõ ràng: khách hàng trước rồi mã đơn. Vì vậy O-1 đứng trước hai đơn của Mai.
- describe tạo một chuỗi cho mỗi đơn. Trong pipeline, map chỉ cần tham chiếu tới phương thức này.
- totalsByCustomer lọc điều kiện isEligible và nhóm tất cả đơn hợp lệ theo tên, **không dùng ngưỡng 50**. Do đó Lan = 40 vẫn xuất hiện, Mai = 60 + 50 = 110.
- TreeMap giúp khóa của Map được in theo thứ tự từ điển. Không nên giả định HashMap hoặc Map.of cho thứ tự tương tự.
- Danh sách orders gốc được tạo bằng List.of và vẫn có kích thước 5. Chương trình không thay đổi nguồn.

Độ dài của phương thức summarize vẫn cho thấy rõ **chuỗi quy tắc**, không chứa một lambda nhiều nhánh. Đây là ví dụ khi một pipeline 6 phép toán ngắn dễ bảo trì hơn một callback ôm nhiều xử lý.

Trong hệ thống thật, dữ liệu có thể null hoặc không hợp lệ ở nhiều trường hơn (id/customer), và công thức số tiền cần đơn vị, chính sách làm tròn. Bài tập này chỉ minh họa tổ chức lambda. Khi trả kết quả bằng Stream.toList() trên Java 17, List kết quả là **không thể chỉnh sửa**; muốn mutable list phải tạo collection phù hợp.

## 10. Quy trình refactor một lambda dài an toàn

Khi gặp một callback nhiều dòng, có thể làm theo thứ tự:

1. **Xác định hợp đồng SAM:** Predicate phải trả boolean, Function trả R, Consumer trả void; xác định rõ tham số và ngoại lệ.
2. **Đọc điều kiện trước:** tìm quy tắc nghiệp vụ đang bị ẩn trong các nhánh và tính toán.
3. **Đặt tên tham số:** dùng tên mô tả phần tử, cặp đối số hoặc vai trò ở từng tầng.
4. **Chọn phần cần trích xuất:** quy tắc lặp, phép tính có tên hoặc đoạn có nhiều nhánh/ngoại lệ.
5. **Tách phương thức với đầu vào tường minh:** tránh để helper phụ thuộc biến static mutable hoặc capture quá nhiều trạng thái.
6. **Thay bằng method reference hoặc lambda ngắn nếu phù hợp:** giữ những điều kiện phụ thuộc ngữ cảnh nhỏ ở tại điểm gọi.
7. **Kiểm tra lại hành vi:** dữ liệu trả về, ngoại lệ, thứ tự xử lý, tác dụng phụ và khả năng xử lý song song có còn đúng không.

Ví dụ trước khi refactor, một Consumer làm nhiều việc:

~~~java
orders.forEach(order -> {
    if (order.paid() && order.units() > 0) {
        long total = (long) order.units() * order.unitPrice();
        System.out.println(order.id() + ": " + total);
        // Ứng dụng thực có thể còn ghi database và gửi sự kiện.
    }
});
~~~

Một hướng cải thiện là **lọc và tính dữ liệu trước**, sau đó thực hiện hành động có tác dụng phụ:

~~~java
orders.stream()
    .filter(LambdaStyleDemo::isEligible)
    .map(LambdaStyleDemo::describe)
    .forEach(System.out::println);
~~~

Trong ví dụ này, describe trả chuỗi từ Order, còn forEach chịu trách nhiệm in. Với mã nghiệp vụ có database, không nên xem forEach là giao dịch tự động; chính sách lưu, retry và error handling cần xác định riêng.

**Không luôn biến vòng for thành Stream:** khi có nhiều nhánh điều khiển, cần break/continue, xử lý lỗi tinh vi hoặc cập nhật có thứ tự, vòng lặp có thể rõ ràng hơn. Refactor hướng tới diễn đạt ý định tốt, không chỉ chuyển cú pháp.

## 11. Những lưu ý về hiệu năng, kiểu và phạm vi biến

### 11.1. Lambda không phải lời gọi “miễn phí”

Tách một phép tính thành helper thông thường không tự gây chi phí lớn đáng kể; JIT có thể inline những phương thức nhỏ. Nhưng không nên tuyên bố mọi lambda/helper luôn được inline hay luôn nhanh như vòng lặp. Trước khi tối ưu, đo hiệu năng trên dữ liệu đại diện.

Không lặp phép tính tốn kém trong filter rồi map nếu có thể tính một lần và mang kết quả đi theo pipeline. Trong bài ví dụ, amount đơn giản nên mã thiên về dễ đọc. Với dữ liệu lớn hoặc thao tác đắt, có thể tạo một record trung gian chứa Order và amount để tái sử dụng giá trị.

### 11.2. Capture biến effectively final

~~~java
long minAmount = 100;
java.util.function.Predicate<Order> enough =
    order -> amount(order) >= minAmount;
~~~

minAmount là biến cục bộ được capture và phải final hoặc effectively final (không bị gán lại). Điều đó không làm cho đối tượng mutable được capture trở thành bất biến: lambda vẫn có thể thay đổi nội dung List, Map hoặc field của một đối tượng. Khi xử lý song song, đừng dùng biến chia sẻ mutable để “đếm số phần tử” trong callback; dùng count, reduce hoặc Collector.

### 11.3. Exception phải nằm trong hợp đồng

Một helper có thể ném IllegalArgumentException hoặc ArithmeticException nếu dữ liệu không hợp lệ. Tách helper không tự bắt ngoại lệ; điều quan trọng là tên, tài liệu và caller có chính sách lỗi rõ ràng. Với checked exception, SAM như Function.apply không khai báo throws IOException; cần xử lý tại ranh giới hoặc định nghĩa interface thích hợp. Không giấu lỗi bằng catch rộng và trả null/false mặc định.

### 11.4. Chú ý ngữ cảnh khi đặt tên

Lambda parameters không được khai báo trùng tên với một biến cục bộ trong phạm vi bao ngoài nếu điều đó vi phạm quy tắc khai báo biến của Java. Đặt tên rõ ràng và tránh reuse tên gây che khuất/nhầm lẫn. Với các callback lồng nhau, nên dùng những danh từ khác nhau cho từng cấp dữ liệu.

## 12. Lỗi thường gặp

**Lỗi 1 — mọi lambda đều dùng x hoặc a, b:** có thể hợp lý với phép cộng hai số, nhưng dễ nhầm trong pipeline nghiệp vụ hoặc callback nested. Dùng order, customer, leftOrder, rightOrder khi cần.

**Lỗi 2 — đánh đồng ngắn với một dòng:** biểu thức ternary lồng nhau hoặc chuỗi gọi hàm nhiều trách nhiệm trong một dòng thường khó đọc và debug hơn một helper có tên.

**Lỗi 3 — trích xuất quá mức:** tạo hàng chục helper như f1, handleData, computeThing chỉ dời logic sang nơi khác. Tên và ranh giới phải truyền đạt ý nghĩa.

**Lỗi 4 — thân lambda có tác dụng phụ ngầm:** filter/map dùng để sửa biến ngoài hoặc ghi I/O khiến pipeline khó kiểm tra, đặc biệt với lazy evaluation hoặc parallel stream.

**Lỗi 5 — method reference làm mất ngữ cảnh:** một method reference tới phương thức tên quá chung như process có thể kém rõ hơn lambda diễn giải đầu vào. Chọn cách trình bày dễ hiểu nhất.

**Lỗi 6 — nhiều điều kiện lặp giữa filter và map:** dễ sửa lệch quy tắc ở hai nơi. Trích xuất điều kiện hoặc phép tính dùng chung.

**Lỗi 7 — đổi thứ tự khi refactor:** filter, sorted, limit, findFirst có thể phụ thuộc encounter order và short-circuit; đổi thứ tự có thể đổi kết quả. Đặc biệt, không chuyển các hành động có tác dụng phụ sang vị trí khác mà chưa hiểu hợp đồng.

**Lỗi 8 — dùng comparator phép trừ:** (left, right) -> left.score() - right.score() có thể tràn int. Dùng Integer.compare hoặc Comparator.comparingInt phù hợp.

**Lỗi 9 — quên kiểu trả về của SAM:** Predicate phải trả boolean, Function phải trả kết quả tương thích, Consumer trả void. Chuyển từ biểu thức ngắn sang thân khối nhiều nhánh dễ quên return.

**Lỗi 10 — cố dùng Stream cho mọi trường hợp:** vòng for rõ ràng vẫn là lựa chọn tốt khi điều khiển luồng hoặc tác dụng phụ theo thứ tự là trọng tâm. Mục tiêu là khả năng đọc và kiểm soát, không phải số lượng lambda.

## 13. Bảng quyết định khi review mã

| Tình huống | Lựa chọn thường hợp lý |
| --- | --- |
| Một phép tính ngắn, biểu thức rõ | Lambda inline |
| Lambda chỉ gọi phương thức có tên tốt | Method reference |
| Điều kiện nghiệp vụ nhiều nhánh | Extract method đặt tên theo quy tắc |
| Điều kiện phụ thuộc tham số cấu hình | Lambda ngắn hoặc factory trả Predicate |
| Hai điều kiện độc lập cần tái sử dụng | Predicate riêng và kết hợp and/or khi phù hợp |
| Pipeline dài nhưng mỗi phép toán rõ | Giữ pipeline, cân nhắc đặt tên bước trung gian |
| Callback có nhiều thao tác ghi/I/O | Tách phép tính khỏi bước tương tác |
| Logic giữ nhiều state/dependency phức tạp | Lớp hoặc service có hợp đồng rõ |
| Vòng lặp có break/continue phức tạp | Ưu tiên vòng for nếu dễ hiểu hơn |

Đây là các gợi ý thiết kế, không phải quy tắc cú pháp bắt buộc của Java. Một nhóm có thể thống nhất code style về số dòng và cách đặt tên, nhưng nên ưu tiên code review dựa trên hành vi và sự rõ ràng.

## 14. Câu hỏi tự kiểm tra

1. Vì sao order -> order.paid() thường dễ hiểu hơn x -> x.paid() trong pipeline nghiệp vụ?
2. Trường hợp nào nên giữ lambda một dòng, trường hợp nào nên tách thành isEligible(Order)?
3. Tại sao method reference Order::id phù hợp cho map, nhưng một điều kiện phụ thuộc minAmount thường vẫn cần lambda hoặc Predicate factory?
4. Việc đặt tên tham số trong Map.merge khác Map.forEach như thế nào?
5. Điều gì có thể sai nếu tách một pipeline rồi đổi chỗ sorted, limit hoặc filter?
6. Vì sao việc in log hoặc sửa List trong filter khiến pipeline kém tin cậy?
7. Viết lại một lambda gồm ba nhánh if theo cách có tên quy tắc rõ, giữ nguyên kết quả và ngoại lệ.
8. Khi nào vòng lặp for tốt hơn việc cố nén các nhánh điều khiển vào một Stream?

**Ghi nhớ:** viết lambda ngắn là **giữ một mục đích rõ ràng ở mỗi callback**; tên tham số mô tả đúng vai trò; và trích xuất phương thức khi quy tắc đủ phức tạp hoặc được dùng nhiều nơi. Lambda, method reference và helper đều là công cụ để người đọc hiểu hành vi, không phải các mục tiêu về số dòng.