# Giữ điều kiện pattern tuyến tính

## 1. “Tuyến tính” nghĩa là gì trong điều kiện pattern?

Trong xử lý Java, một nhánh thường cần lần lượt trả lời ba câu hỏi: **giá trị có đúng cấu trúc không, dữ liệu bên trong có thỏa điều kiện không, và nếu thỏa thì cần làm gì?** Với pattern matching, ta có thể diễn đạt các bước ấy theo một chiều dễ theo dõi:

1. **Khớp mẫu** để xác nhận kiểu/cấu trúc và ràng buộc biến.
2. **Kiểm tra điều kiện bổ sung** bằng các biến chỉ vừa được ràng buộc.
3. **Xử lý kết quả** hoặc chuyển sang nhánh tiếp theo.

“Tuyến tính” ở đây là cách tổ chức **luồng đọc và luồng điều khiển rõ ràng**, không phải lời hứa rằng thuật toán có độ phức tạp thời gian `O(n)`. Một điều kiện có thể rất ngắn nhưng vẫn khó hiểu nếu trộn nhiều phép phủ định, nhánh `||` và truy cập dữ liệu chưa được kiểm tra.

Ví dụ với các record:

```java
record Address(String city) {}
record Customer(String name, Address address) {}
record Order(String id, Customer customer, int amount) {}
```

Ta muốn nhận diện đơn hàng có đầy đủ khách hàng, địa chỉ, số tiền từ 100 trở lên và thành phố là Hà Nội.

Cách viết nhiều tầng `if`, giả định biến `input` đã được khai báo:

```java
if (input instanceof Order order) {
    if (order.customer() != null) {
        Customer customer = order.customer();
        if (customer.address() != null) {
            Address address = customer.address();
            if (order.amount() >= 100) {
                if ("Hà Nội".equals(address.city())) {
                    System.out.println("Đơn ưu tiên: " + order.id());
                }
            }
        }
    }
}
```

Đoạn này đúng với dữ liệu mẫu nhưng người đọc phải theo nhiều tầng ngoặc và các biến trung gian. Nếu bài toán chỉ cần hành động khi **tất cả** điều kiện đúng, có thể đặt chuỗi kiểm tra theo thứ tự tự nhiên hơn.

## 2. Kết hợp record pattern và toán tử &&

Trong Java 21, record pattern có thể lồng vào nhau và kết hợp với `&&`:

```java
if (input instanceof Order(
        String id,
        Customer(String name, Address(String city)),
        int amount)
        && amount >= 100
        && "Hà Nội".equals(city)) {
    System.out.println("Đơn ưu tiên: " + id);
}
```

Đọc theo đúng thứ tự:

- `input instanceof Order(...)` kiểm tra giá trị là `Order`, phân rã `customer` thành `Customer`, rồi phân rã tiếp `address` thành `Address`. Nếu các mẫu lồng không khớp, điều kiện `instanceof` là `false`.
- Chỉ sau khi pattern khớp, biến `id`, `name`, `city`, `amount` mới có thể được sử dụng ở phần `&&` phía sau.
- `amount >= 100` là kiểm tra nghiệp vụ trên biến `int` vừa được lấy từ record.
- `"Hà Nội".equals(city)` kiểm tra địa điểm. Cách đặt hằng chuỗi ở bên trái cũng an toàn nếu `city` có thể là `null`; với mẫu `String city` ở đây, giá trị `null` đã khiến mẫu tương ứng không khớp.
- Khi cả ba phần đều đúng, thân `if` chạy.

**Toán tử `&&` đánh giá ngắn mạch (short-circuit):** nếu vế trái sai, Java không đánh giá vế phải. Vì vậy, chương trình không truy cập các biến pattern chưa được ràng buộc khi cấu trúc không khớp. Quan hệ “khớp mẫu trước, kiểm tra dữ liệu sau” vừa dễ đọc vừa phù hợp quy tắc phạm vi biến (*flow scoping*) của Java.

Để dễ đọc, nên xuống dòng sau mỗi điều kiện lớn. Không cần nén toàn bộ record pattern lồng nhau, guard nghiệp vụ và hành động vào một dòng.

## 3. Khi điều kiện nhiều bước: dùng guard clause để giảm lồng nhau

Một điều kiện dài với nhiều `&&` vẫn có thể khó bảo trì. Khi có nhiều lý do bị từ chối khác nhau, nên để chương trình **trả về sớm** (*guard clause*) rồi tiếp tục xử lý ở cùng mức thụt đầu dòng:

```java
static String classify(Object input) {
    if (!(input instanceof Order(
            String id,
            Customer(String name, Address(String city)),
            int amount))) {
        return "Không đủ cấu trúc đơn hàng";
    }

    if (amount < 100) {
        return "Đơn nhỏ: " + id;
    }

    if (!"Hà Nội".equals(city)) {
        return "Ngoài Hà Nội: " + id;
    }

    return "Đơn ưu tiên: " + id + " - " + name;
}
```

Các bước vẫn đi theo một hướng:

1. Đầu tiên loại giá trị không khớp cấu trúc cần thiết.
2. Sau đó loại đơn chưa đạt ngưỡng số tiền.
3. Tiếp theo loại đơn ngoài địa điểm phục vụ.
4. Cuối cùng xử lý trường hợp đạt tất cả yêu cầu.

Đây là ví dụ minh họa trong lớp có các record đã khai báo. Điểm quan trọng về **flow scoping**: điều kiện `!(input instanceof Order(...))` có nghĩa là “không khớp mẫu”. Nếu rơi vào nhánh `if` thì phương thức lập tức `return`. Do đó, trên đường thực thi đi tiếp sau `if`, trình biên dịch biết mẫu đã khớp và cho phép dùng `id`, `name`, `city` và `amount`.

Không phải cứ phủ định `instanceof` là biến pattern dùng được phía sau. Điều kiện quyết định là **mọi đường đi tới vị trí sử dụng biến đều đã chứng minh mẫu khớp**. Nếu nhánh phủ định không kết thúc luồng xử lý, biến chưa chắc được ràng buộc và Java sẽ từ chối cách dùng sai phạm vi.

## 4. Phân biệt && với || trong flow scoping

So sánh hai dạng:

```java
// Hợp lệ: phần sau && chỉ được xét khi mẫu đã khớp.
if (input instanceof Order(var id, var customer, var amount)
        && amount >= 100) {
    System.out.println(id);
}
```

```java
// KHÔNG BIÊN DỊCH: nếu mẫu bên trái không khớp,
// nhánh bên phải của || vẫn được xét nhưng amount chưa được ràng buộc.
// if (input instanceof Order(var id, var customer, var amount)
//         || amount >= 100) {
//     System.out.println(id);
// }
```

Đoạn thứ hai được chú thích hoàn toàn vì là **ví dụ lỗi có chủ đích**, không phải mã runnable. Với `||`, nhánh bên phải được đánh giá khi vế trái **sai**; vì vậy không thể dùng ở đó một biến chỉ được khai báo khi mẫu vế trái **đúng**.

Dạng có `||` đôi khi hợp lệ khi hai điều kiện độc lập, ví dụ:

```java
if (input == null || input instanceof String) {
    System.out.println("Trống hoặc là chuỗi");
}
```

Nhưng khi các điều kiện cần dữ liệu được ràng buộc bởi một pattern, hãy ưu tiên chuỗi `&&` hoặc tách thành các guard clause để trình bày sự phụ thuộc thật rõ ràng. Đừng đổi `&&` sang `&`: toán tử boolean `&` đánh giá cả hai vế, không có đặc tính ngắn mạch và không cho ta cùng cách dùng biến pattern phụ thuộc điều kiện đầu.

## 5. Kết hợp pattern với switch và when

Khi cần **nhiều kết quả** cho cùng một cấu trúc, `switch` có thể làm luồng phân loại rõ hơn. Từ Java 21, đặt record pattern vào `case` và thêm `when` cho điều kiện nghiệp vụ:

```java
static String classifySwitch(Object input) {
    return switch (input) {
        case Order(String id, Customer(String name, Address(String city)),
                   int amount)
                when amount >= 100 && "Hà Nội".equals(city) ->
                "Ưu tiên theo switch: " + id;

        case Order order ->
                "Đơn khác: " + order.id();

        case null ->
                "Không có dữ liệu";

        default ->
                "Không phải đơn hàng";
    };
}
```

Cách đọc mỗi `case` là **pattern → guard (nếu có) → hành động**. `when` chỉ được đánh giá khi record pattern phía trước đã khớp, nên các biến ràng buộc bởi pattern được phép xuất hiện trong guard. Ở ví dụ trên, `amount` và `city` là dữ liệu của đúng `Order` đang xét.

**Thứ tự các nhánh rất quan trọng:** đặt `case Order order` sau nhánh chi tiết. Nếu đặt nhánh bắt mọi `Order` phía trước, nhánh cụ thể phía sau sẽ không thể được chọn và trình biên dịch có thể báo lỗi *dominated case*. Tương tự, nếu có nhiều nhánh `Order(...) when ...`, nên đặt quy tắc cụ thể trước quy tắc bao quát và tránh điều kiện chồng chéo không chủ ý.

Nhánh `case null` xử lý selector bằng `null`. `default` xử lý dữ liệu không phải `Order`; không nên mặc định `default` là cách thay thế cho xử lý `null`.

## 6. Ví dụ Java 21 hoàn chỉnh và kết quả chính xác

Tạo tệp **`LinearPatternConditionsDemo.java`**:

```java
public class LinearPatternConditionsDemo {
    record Address(String city) {}
    record Customer(String name, Address address) {}
    record Order(String id, Customer customer, int amount) {}

    static boolean isPriority(Object input) {
        return input instanceof Order(
                String id,
                Customer(String name, Address(String city)),
                int amount)
                && amount >= 100
                && "Hà Nội".equals(city);
    }

    static String classify(Object input) {
        if (!(input instanceof Order(
                String id,
                Customer(String name, Address(String city)),
                int amount))) {
            return "Không đủ cấu trúc đơn hàng";
        }

        if (amount < 100) {
            return "Đơn nhỏ: " + id;
        }

        if (!"Hà Nội".equals(city)) {
            return "Ngoài Hà Nội: " + id;
        }

        return "Đơn ưu tiên: " + id + " - " + name;
    }

    static String classifySwitch(Object input) {
        return switch (input) {
            case Order(String id,
                    Customer(String name, Address(String city)),
                    int amount)
                    when amount >= 100 && "Hà Nội".equals(city) ->
                    "Ưu tiên theo switch: " + id;
            case Order order ->
                    "Đơn khác: " + order.id();
            case null ->
                    "Không có dữ liệu";
            default ->
                    "Không phải đơn hàng";
        };
    }

    public static void main(String[] args) {
        Object priority = new Order(
                "O-1", new Customer("Lan", new Address("Hà Nội")), 150);
        Object small = new Order(
                "O-2", new Customer("Minh", new Address("Hà Nội")), 50);
        Object elsewhere = new Order(
                "O-3", new Customer("An", new Address("Đà Nẵng")), 200);
        Object missingAddress = new Order(
                "O-4", new Customer("Bình", null), 500);

        System.out.println(classify(priority));
        System.out.println(isPriority(priority));
        System.out.println(classify(small));
        System.out.println(classify(elsewhere));
        System.out.println(classify(missingAddress));
        System.out.println(classifySwitch(priority));
        System.out.println(classifySwitch(missingAddress));
        System.out.println(classifySwitch(null));
        System.out.println(classifySwitch("khác"));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**, không cần bật tính năng preview:

```bash
javac LinearPatternConditionsDemo.java
java LinearPatternConditionsDemo
```

Kết quả:

```text
Đơn ưu tiên: O-1 - Lan
true
Đơn nhỏ: O-2
Ngoài Hà Nội: O-3
Không đủ cấu trúc đơn hàng
Ưu tiên theo switch: O-1
Đơn khác: O-4
Không có dữ liệu
Không phải đơn hàng
```

Vì sao đầu ra như vậy?

- `priority` có đủ cả ba record, `amount = 150` và `city = "Hà Nội"`: pattern khớp, các guard đúng, nên `classify` trả về đơn ưu tiên và `isPriority` là `true`.
- `small` khớp cấu trúc, nhưng `amount = 50` nên đi qua guard clause trả về “Đơn nhỏ”.
- `elsewhere` khớp cấu trúc và số tiền, nhưng `city` là “Đà Nẵng”, nên trả về “Ngoài Hà Nội”.
- `missingAddress` có `customer` nhưng `address == null`. Nested pattern `Address(String city)` không khớp, nên `classify` trả về “Không đủ cấu trúc đơn hàng”.
- Trong `switch`, `missingAddress` không khớp nhánh record pattern lồng nhau có `when`, nhưng vẫn là một `Order`, vì vậy nhánh `case Order order` trả về “Đơn khác: O-4”.
- `null` chọn `case null`; chuỗi `"khác"` chọn `default`.

Đoạn chương trình chứa cả ba cách trình bày cùng một ý tưởng: **biểu thức boolean với `&&`**, **chuỗi guard clause**, và **switch có pattern kèm `when`**. Chúng phục vụ mục đích khác nhau: một điều kiện đúng/sai, một quy trình có nhiều lý do dừng sớm, và nhiều nhánh phân loại.

## 7. Xử lý null mà không phá vỡ tuyến tính

Với nested record pattern, từng record con phải khớp. Nếu `customer == null` hoặc `address == null`, mẫu `Order(String id, Customer(...), int amount)` không khớp và Java không đánh giá những phép kiểm tra `&&` phía sau.

Tuy vậy, **record pattern không tự chứng minh mọi tham chiếu đều khác null trong mọi cách viết**. Chẳng hạn, nếu dùng `var city` để ràng buộc một component kiểu `String` thì cần xét khả năng `city` là `null` trước khi gọi phương thức trên nó. Viết `"Hà Nội".equals(city)` an toàn hơn `city.equals("Hà Nội")` khi dữ liệu có thể thiếu.

Đừng tự động suy luận từ việc `Order` khớp mẫu bên ngoài rằng `customer` và `address` đều tồn tại. Một mẫu nông hơn, ví dụ `Order(var id, var customer, var amount)`, vẫn có thể ràng buộc biến `customer` khi giá trị ấy bằng `null`. Hãy chọn độ sâu phân rã phù hợp với những điều kiện thực sự cần kiểm tra.

## 8. Các quy tắc để giữ điều kiện dễ đọc

| Quy tắc | Lý do | Ví dụ |
| --- | --- | --- |
| Khớp kiểu và cấu trúc trước | Tránh dùng giá trị khi chưa xác định đúng loại dữ liệu. | `input instanceof Order(...)` |
| Đặt điều kiện phụ thuộc sau `&&` | Bảo đảm chỉ xét khi biến pattern đã được ràng buộc. | `&& amount >= 100` |
| Dùng tên biến rõ nghĩa | Giảm nhầm lẫn khi record nhiều tầng. | `city`, `amount`, `id` |
| Tách nhánh khi có nhiều lý do từ chối | Tránh lồng `if` sâu và thông báo lỗi mơ hồ. | `if (amount < 100) return ...;` |
| Trong `switch`, xét mẫu cụ thể trước | Tránh bị nhánh tổng quát bao phủ. | `case Order(...) when ...` rồi `case Order order` |
| Xử lý dữ liệu có thể null | Phân biệt selector null với component null. | `case null`; kiểm tra pattern lồng |
| Không đặt tác dụng phụ trong guard khi không cần | Biểu thức điều kiện được đánh giá ngắn mạch, nên tác dụng phụ có thể bị bỏ qua. | Tách ghi log/cập nhật trạng thái khỏi `&&` |

Không có một mẫu duy nhất phù hợp cho mọi trường hợp. Một phép phân loại đơn giản nên dùng `&&`; khi mỗi trường hợp bị loại cần một lời giải thích riêng, các guard clause sẽ rõ ràng hơn; khi có nhiều loại record hoặc nhiều nhánh xử lý, `switch` cùng `case` và `when` giúp nhóm logic theo cấu trúc dữ liệu.

## 9. Lỗi thường gặp

1. **Dùng biến pattern trước khi mẫu khớp.** Ví dụ, dùng `amount` ở bên phải `||` trong khi chỉ khai báo `amount` ở mẫu bên trái sẽ không được Java chấp nhận theo flow scoping.
2. **Thay `&&` bằng `&`.** `&` với boolean không ngắn mạch, khiến phần sau vẫn được tính ngay cả khi phần trước sai; điều này vừa dễ tạo lỗi vừa không thể hiện quan hệ phụ thuộc giữa pattern và guard.
3. **Nhồi một điều kiện dài nhiều phủ định.** `if (!... || (... && !...))` khó kiểm tra hơn chuỗi “khớp mẫu → điều kiện nghiệp vụ → hành động”. Có thể dùng guard clause và đặt tên cho khái niệm nghiệp vụ.
4. **Dùng `case` tổng quát trước `case` cụ thể.** Nhánh rộng có thể khiến nhánh cụ thể bị *dominated*, gây lỗi biên dịch. Cần sắp nhánh chuyên biệt trước.
5. **Cho rằng `default` xử lý được selector null.** Với pattern matching for switch, xử lý `null` là trường hợp riêng; dùng `case null` khi cần kết quả rõ ràng.
6. **Nhầm “tuyến tính” với độ phức tạp thuật toán.** Việc tổ chức điều kiện thành từng bước không bảo đảm xử lý nhanh hơn. Mục tiêu là thể hiện chính xác sự phụ thuộc và giảm độ phức tạp khi đọc code.
7. **Dùng sai phiên bản Java.** Record pattern và pattern matching for `switch` trở thành tính năng chính thức ở Java 21. Các ví dụ với `when` và record deconstruction trong bài này cần JDK 21 trở lên.

## 10. Tự kiểm tra

Giả sử dữ liệu là:

```java
record Score(String subject, int value) {}
Object candidate = new Score("Java", 85);
```

Viết điều kiện cho phép in môn học khi giá trị là `Score` có `value >= 80` và môn là `"Java"`:

```java
if (candidate instanceof Score(String subject, int value)
        && value >= 80
        && "Java".equals(subject)) {
    System.out.println(subject + ": đạt");
}
```

Kết quả là:

```text
Java: đạt
```

Sau đó thử thay `candidate` bằng `"Java"` hoặc `null`: vế `instanceof Score(...)` không khớp nên Java không đánh giá các điều kiện còn lại; thân `if` không chạy. Thử đổi `value` thành `70`: record pattern vẫn khớp, nhưng guard đầu tiên sai nên nhánh không chạy.

**Ghi nhớ:** Hãy tổ chức điều kiện pattern theo trật tự **khớp cấu trúc → kiểm tra dữ liệu đã ràng buộc → thực hiện hành động**. Dùng `&&` cho chuỗi phụ thuộc ngắn mạch, guard clause cho nhiều điều kiện loại trừ, và `switch case ... when ...` cho nhiều nhánh phân loại. Như vậy điều kiện vừa đúng quy tắc phạm vi biến Java 21, vừa dễ đọc và dễ bảo trì.
