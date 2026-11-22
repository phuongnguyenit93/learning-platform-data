# Kết hợp Predicate và Function để biểu diễn quy tắc xử lý

Trong Java Stream API, một yêu cầu nghiệp vụ thường có hai phần: **quyết định dữ liệu nào được chấp nhận** và **biến dữ liệu được chấp nhận thành kết quả mong muốn**. `Predicate<T>` diễn đạt điều kiện có/không; `Function<T, R>` diễn đạt phép biến đổi từ kiểu `T` sang kiểu `R`. Khi kết hợp, chúng tạo thành các quy tắc nhỏ, có tên, dễ tái sử dụng và dễ kiểm tra.

Bài này thuộc phần **Hàm hành vi và kiểu dữ liệu** của mô-đun **JAVA_STREAM_API**. Kiến thức ở đây là nền tảng để xây dựng pipeline `filter`, `map`, `reduce` và `collect`; về sau có thể áp dụng vào `groupingBy`, collector tùy chỉnh và những phương thức xử lý Stream nâng cao. Trọng tâm của bài là **viết và kết hợp quy tắc xử lý có kiểu rõ ràng**, đồng thời hiểu thứ tự đánh giá, tính lazy và giới hạn của trạng thái.

## 1. Phân biệt vai trò của Predicate và Function

Cả hai đều là *functional interface* trong `java.util.function`: giao diện có một phương thức trừu tượng và có thể biểu diễn bằng lambda hoặc method reference.

| Đặc điểm | `Predicate<T>` | `Function<T, R>` |
| --- | --- | --- |
| Câu hỏi được trả lời | “Phần tử này có đáp ứng điều kiện không?” | “Phần tử này biến thành giá trị nào?” |
| Phương thức trừu tượng | `boolean test(T value)` | `R apply(T value)` |
| Kết quả | `boolean` | Một giá trị kiểu `R` |
| Cách dùng phổ biến | `Stream.filter(predicate)` | `Stream.map(function)` |
| Phép kết hợp sẵn có | `and`, `or`, `negate` | `andThen`, `compose`, `identity` |
| Mục đích | Lựa chọn/xác nhận dữ liệu | Chuyển đổi/chuẩn hóa dữ liệu |

Ví dụ với chuỗi:

```java
import java.util.function.Function;
import java.util.function.Predicate;

Predicate<String> notBlank = text -> text != null && !text.isBlank();
Function<String, Integer> countCharacters = String::length;

System.out.println(notBlank.test("Java"));          // true
System.out.println(notBlank.test("   "));            // false
System.out.println(countCharacters.apply("Java"));  // 4
```

`Predicate<String>` không trả lại chuỗi đã sửa, và `Function<String, Integer>` không phải phép kiểm tra điều kiện. Hai vai trò này khác nhau ngay cả khi một `Function` được khai báo với kiểu trả về `Boolean`; cách biểu diễn quy tắc điều kiện tự nhiên vẫn là `Predicate`.

Trong Stream:

```java
List<String> lengthsAsText = List.of(" Java ", "", "Stream")
    .stream()
    .filter(text -> !text.isBlank())  // Predicate<String>
    .map(String::strip)                // Function<String, String>
    .map(String::length)               // Function<String, Integer>
    .map(String::valueOf)              // Function<Integer, String>
    .toList();

System.out.println(lengthsAsText); // [4, 6]
```

Lưu ý: đoạn ví dụ này cần `import java.util.List;` và các snippet ở những mục sau có thể dùng chung import nếu đặt trong một lớp Java.

## 2. Kết hợp nhiều Predicate thành một quy tắc nghiệp vụ

Một quy tắc thực tế thường gồm nhiều điều kiện. Thay vì nhét tất cả vào một lambda dài, hãy đặt tên từng điều kiện rồi kết hợp chúng.

Ba phương thức quan trọng:

- `p.and(q)`: đúng khi **cả** `p` và `q` đúng.
- `p.or(q)`: đúng khi **ít nhất một** trong `p` và `q` đúng.
- `p.negate()`: đảo giá trị đúng/sai của `p`.

Cú pháp tương đương về ý nghĩa:

```java
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> even = n -> n % 2 == 0;

Predicate<Integer> positiveAndEven = positive.and(even);
Predicate<Integer> positiveOrEven = positive.or(even);
Predicate<Integer> notPositive = positive.negate();

System.out.println(positiveAndEven.test(8)); // true
System.out.println(positiveAndEven.test(3)); // false
System.out.println(notPositive.test(-2));    // true
```

### 2.1. Nhóm điều kiện đúng theo ý nghĩa nghiệp vụ

Giả sử yêu cầu: **Chỉ nhận đơn đã thanh toán**, và đơn đó **có số tiền từ 1.000.000 VND trở lên hoặc thuộc khách hàng VIP**. Quy tắc logic phải là:

```text
đủ điều kiện = đã thanh toán AND (đạt số tiền tối thiểu OR là khách VIP)
```

Java biểu diễn trực tiếp:

```java
Predicate<Order> paid = Order::paid;
Predicate<Order> minimumAmount = order -> order.amountVnd() >= 1_000_000L;
Predicate<Order> vipCustomer = order -> order.customerId().startsWith("VIP-");

Predicate<Order> eligible = paid.and(minimumAmount.or(vipCustomer));
```

Dấu ngoặc trong yêu cầu rất quan trọng. `paid.and(minimumAmount).or(vipCustomer)` mang ý nghĩa khác: khách VIP **chưa thanh toán** vẫn có thể được chọn. Việc đặt tên và nhóm biểu thức giúp rà soát chính sách dễ hơn.

### 2.2. Hiểu short-circuit và thứ tự kiểm tra

`Predicate.and` và `Predicate.or` đánh giá ngắn mạch (*short-circuit*), theo thứ tự từ trái sang phải:

| Biểu thức | Khi nào bỏ qua `q.test(value)`? | Lý do |
| --- | --- | --- |
| `p.and(q)` | Khi `p` trả về `false` | Kết quả cuối chắc chắn là `false` |
| `p.or(q)` | Khi `p` trả về `true` | Kết quả cuối chắc chắn là `true` |

Do đó, có thể đặt kiểm tra an toàn trước kiểm tra cần dữ liệu hợp lệ:

```java
Predicate<String> nonNull = java.util.Objects::nonNull;
Predicate<String> hasContent = text -> !text.isBlank();

Predicate<String> usableText = nonNull.and(hasContent);

System.out.println(usableText.test(null));   // false; không gọi isBlank()
System.out.println(usableText.test("  "));    // false
System.out.println(usableText.test("Java"));  // true
```

Mặc dù có thể giảm số lần kiểm tra đắt tiền bằng short-circuit, **không nên dựa vào tác dụng phụ** bên trong `Predicate`. Đừng đặt việc tăng bộ đếm, ghi log bắt buộc hoặc cập nhật cơ sở dữ liệu trong biểu thức điều kiện rồi giả định mọi điều kiện đều chạy.

## 3. Kết hợp Function để tạo một phép biến đổi có nghĩa

`Function<T, R>` hỗ trợ ghép phép biến đổi theo hai cách:

- `f.andThen(g)`: áp dụng `f` **trước**, rồi áp dụng `g`.
- `g.compose(f)`: áp dụng `f` **trước**, rồi áp dụng `g`.

Hai cách sau cho cùng kết quả:

```java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> removeEdgeSpaces = String::strip;
Function<String, String> toLower = text -> text.toLowerCase(Locale.ROOT);

Function<String, String> normalizedA = removeEdgeSpaces.andThen(toLower);
Function<String, String> normalizedB = toLower.compose(removeEdgeSpaces);

System.out.println(normalizedA.apply("  JAVA@EXAMPLE.ORG  "));
// java@example.org

System.out.println(normalizedB.apply("  JAVA@EXAMPLE.ORG  "));
// java@example.org
```

Có thể đọc `removeEdgeSpaces.andThen(toLower)` từ trái sang phải: **xóa khoảng trắng đầu/cuối → chuyển chữ thường**. Trong khi đó, `toLower.compose(removeEdgeSpaces)` đọc theo nghĩa “thực hiện bước xóa khoảng trắng trước khi gọi bước chuyển chữ thường”.

Để ghép hai `Function`, kiểu đầu ra của bước trước phải tương thích với kiểu đầu vào của bước sau:

```java
Function<String, Integer> length = String::length;

// String -> String -> Integer
Function<String, Integer> normalizedLength =
    removeEdgeSpaces.andThen(length);

System.out.println(normalizedLength.apply("  ABC  ")); // 3
```

Nếu `Function<T, R>` làm thay đổi kiểu từ `T` sang `R`, cần xây dựng các bước tiếp theo nhận đầu vào `R`. Không thể nối hai hàm chỉ vì chúng cùng tên ý nghĩa; Java phải kiểm tra được kiểu ở thời điểm biên dịch.

### 3.1. Khi nào dùng `Function.identity()`?

`Function.identity()` trả về hàm giữ nguyên đầu vào:

```java
Function<String, String> unchanged = Function.identity();
System.out.println(unchanged.apply("A-01")); // A-01
```

Hàm này hữu ích trong collector hoặc khi một API yêu cầu truyền `Function` nhưng giá trị không cần biến đổi. Ví dụ khi gom các chuỗi vào map theo chính nội dung của chúng, `Function.identity()` có thể làm key mapper hoặc value mapper, tùy yêu cầu và quy tắc xử lý khóa trùng.

## 4. Kết hợp Predicate và Function đúng cách

Hai kiểu giao diện có thể phối hợp theo nhiều tầng:

```text
                    Predicate<Order>          Function<Order, OrderView>
Nguồn Order ── filter(eligible) ── Order ── map(toView) ── OrderView
                         │                            │
                   giữ hoặc loại                 biến đổi cấu trúc
```

Với `Stream<T>`, `filter` nhận `Predicate<? super T>` và giữ nguyên kiểu phần tử là `T`. `map` nhận hàm chuyển từ `T` sang `R` và đổi kiểu của luồng thành `Stream<R>`.

### 4.1. Ví dụ chạy hoàn chỉnh: áp dụng quy tắc chọn đơn và tạo dữ liệu đầu ra

Ví dụ sau biên dịch với **Java 17 trở lên** (sử dụng `record` và `Stream.toList()`):

```java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

public class OrderRuleDemo {
    record Order(
        String id,
        String customerId,
        long amountVnd,
        boolean paid
    ) {}

    record OrderView(String id, long amountVnd, String tier) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", "C-01",   1_500_000L, true),
            new Order("O-02", "VIP-02",   300_000L, true),
            new Order("O-03", "VIP-03", 2_000_000L, false),
            new Order("O-04", "C-04",     600_000L, true)
        );

        Predicate<Order> paid = Order::paid;
        Predicate<Order> minimumAmount =
            order -> order.amountVnd() >= 1_000_000L;
        Predicate<Order> vipCustomer =
            order -> order.customerId().startsWith("VIP-");

        // Đã thanh toán VÀ (đạt mức tối thiểu HOẶC là khách VIP).
        Predicate<Order> eligible =
            paid.and(minimumAmount.or(vipCustomer));

        Function<Order, OrderView> toView = order -> new OrderView(
            order.id(),
            order.amountVnd(),
            order.customerId().startsWith("VIP-") ? "VIP" : "STANDARD"
        );

        List<OrderView> result = orders.stream()
            .filter(eligible)
            .map(toView)
            .toList();

        result.forEach(System.out::println);
    }
}
```

Kết quả:

```text
OrderView[id=O-01, amountVnd=1500000, tier=STANDARD]
OrderView[id=O-02, amountVnd=300000, tier=VIP]
```

Phân tích từng đơn:

| Đơn | Đã thanh toán | Số tiền ≥ 1 triệu | Khách VIP | Kết quả |
| --- | --- | --- | --- | --- |
| O-01 | Có | Có | Không | Giữ lại |
| O-02 | Có | Không | Có | Giữ lại |
| O-03 | Không | Có | Có | Loại vì chưa thanh toán |
| O-04 | Có | Không | Không | Loại vì không đạt điều kiện |

Vì quy tắc được đặt trong biến `eligible` và phép biến đổi được đặt trong `toView`, chúng có thể dùng lại tại nhiều nơi mà không cần sao chép toàn bộ biểu thức lambda.

### 4.2. Biến đổi trước rồi mới kiểm tra

Không phải lúc nào `filter` cũng đứng trước `map`. Nếu muốn kiểm tra **giá trị sau khi chuẩn hóa**, hãy biến đổi trước rồi lọc sau:

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Predicate;

List<String> rawEmails = java.util.Arrays.asList(
    "  MAI@EXAMPLE.ORG ",
    "support@other.org",
    null,
    "  AN@EXAMPLE.ORG "
);

Function<String, String> normalizeEmail =
    ((Function<String, String>) String::strip)
        .andThen(text -> text.toLowerCase(Locale.ROOT));

Predicate<String> belongsToExample =
    email -> email.endsWith("@example.org");

List<String> acceptedEmails = rawEmails.stream()
    .filter(Objects::nonNull)
    .map(normalizeEmail)
    .filter(belongsToExample)
    .toList();

System.out.println(acceptedEmails);
// [mai@example.org, an@example.org]
```

Việc kiểm tra `null` được đặt **trước** `String::strip` để tránh `NullPointerException`. Ví dụ chỉ minh họa kiểm tra hậu tố miền; nó **không** phải bộ xác thực đầy đủ định dạng địa chỉ email. Với dữ liệu thực tế cần kiểm tra định dạng, chuẩn hóa và quy tắc an ninh phù hợp với nghiệp vụ.

Điểm mấu chốt là: nếu đầu vào chưa chuẩn hóa, áp dụng `belongsToExample` ngay trước `map(normalizeEmail)` sẽ loại sai chuỗi chứa chữ hoa và khoảng trắng như `"  MAI@EXAMPLE.ORG "`.

### 4.3. Tạo Predicate trên kiểu nguồn từ Function và Predicate trên kiểu đích

Đôi khi một phép kiểm tra chỉ biết làm việc với kiểu `R`, nhưng dữ liệu đầu vào thuộc kiểu `T`. Khi đó, lấy `R` bằng `Function<T, R>` rồi truyền vào `Predicate<R>`:

```java
// Giả sử Order là record đã định nghĩa trong ví dụ 4.1.
Function<Order, String> getCustomerId = Order::customerId;
Predicate<String> isVipId = id -> id.startsWith("VIP-");

// Adapter: Predicate<Order> được xây từ Function<Order, String>
// và Predicate<String>.
Predicate<Order> orderFromVipCustomer =
    order -> isVipId.test(getCustomerId.apply(order));
```

Có thể diễn đạt mối liên hệ này bằng công thức:

```text
Predicate<T> onSource =
    value -> predicateOnResult.test(function.apply(value))
```

`Predicate` **không có** phương thức `compose` hay `andThen` như `Function`. Adapter lambda ở trên là cách phổ biến để nối hai kiểu giao diện.

Nếu mục đích là **xuất ra giá trị đã biến đổi**, cách rõ ràng thường là `stream.map(function).filter(predicateOnResult)`. Nếu phải chạy `function.apply` trong `Predicate` rồi lại chạy cùng hàm ở `map`, phép biến đổi có thể bị thực hiện hai lần. Với hàm tốn kém, nên thiết kế pipeline để tính kết quả một lần, miễn là thứ tự xử lý và kiểu dữ liệu vẫn đúng yêu cầu.

## 5. Thiết kế quy tắc có thể tái sử dụng và kiểm thử

Một bộ quy tắc dễ bảo trì nên có các đặc điểm:

1. **Có tên mô tả nghiệp vụ.** Ví dụ `paid`, `minimumAmount`, `eligible`, `toView` dễ hiểu hơn `p1`, `p2`, `f`.
2. **Chỉ làm một việc.** `Predicate` kiểm tra; `Function` chuyển đổi. Tránh đưa thao tác ghi cơ sở dữ liệu hay cập nhật biến ngoài vào biểu thức lọc và ánh xạ.
3. **Biểu diễn yêu cầu null rõ ràng.** Dùng `Objects::nonNull` hoặc thiết kế domain không chấp nhận null từ đầu. Không tự suy rằng mọi lambda đều xử lý null.
4. **Giữ quy tắc độc lập với cách thu thập kết quả.** `Predicate` và `Function` có thể dùng ngoài Stream, ví dụ trong `if`, trong kiểm tra dữ liệu đầu vào hoặc khi chuyển đổi một đối tượng đơn lẻ.
5. **Kiểm thử tổ hợp và ranh giới.** Ít nhất cần kiểm tra ngưỡng tiền, điều kiện ngoại lệ VIP, đơn chưa thanh toán và danh sách rỗng.

Ví dụ tái sử dụng quy tắc trên một đối tượng đơn lẻ:

```java
Order oneOrder = new Order("O-05", "VIP-10", 200_000L, true);

if (eligible.test(oneOrder)) {
    OrderView view = toView.apply(oneOrder);
    System.out.println(view);
}
```

Trong mã này, `eligible` và `toView` là hai biến ở phạm vi có thể truy cập được từ ví dụ 4.1. Điều đó minh họa rằng **quy tắc không phụ thuộc vào Stream**; Stream chỉ cung cấp một cách thực thi quy tắc trên nhiều phần tử.

### Bảng kiểm thử theo kịch bản

| Kịch bản | Điều kiện đầu vào | Kỳ vọng |
| --- | --- | --- |
| Vừa đạt ngưỡng | Đã thanh toán, 1.000.000 VND, không VIP | `eligible.test` trả về `true` |
| Dưới ngưỡng nhưng VIP | Đã thanh toán, 200.000 VND, VIP | `true` |
| Không thanh toán nhưng VIP | Chưa thanh toán, 2.000.000 VND, VIP | `false` |
| Dưới ngưỡng và không VIP | Đã thanh toán, 999.999 VND, không VIP | `false` |
| Danh sách nguồn rỗng | Không có đơn | `stream().filter(...).map(...).toList()` cho danh sách rỗng |

Nếu điều kiện nghiệp vụ thay đổi, ví dụ “khách VIP phải thanh toán tối thiểu 100.000 VND”, hãy sửa biểu thức tạo `Predicate` và bổ sung các ca kiểm thử liên quan, giữ nguyên phép `Function` tạo `OrderView` nếu định dạng đầu ra không đổi.

## 6. Lazy pipeline, short-circuit và trạng thái

Trong Java Stream API, `filter` và `map` là các **thao tác trung gian**. Việc khai báo pipeline chưa khiến `Predicate.test` hoặc `Function.apply` chạy ngay:

```java
var selected = orders.stream()
    .filter(eligible)
    .map(toView); // Chưa duyệt dữ liệu tại thời điểm khai báo.

List<OrderView> views = selected.toList(); // Terminal operation tiêu thụ Stream.
```

Stream chỉ có thể được tiêu thụ một lần; nếu cần kết quả khác, tạo pipeline mới từ nguồn. Các terminal operation có thể **dừng sớm** hoặc được tối ưu theo đặc điểm nguồn. Không được giả định mỗi `Predicate` hay `Function` luôn được gọi đúng một lần cho mọi phần tử: ví dụ `anyMatch` có thể dừng ngay khi đã có phần tử thỏa mãn, còn một số pipeline với `count` có thể được tối ưu để không cần thực hiện những bước trung gian không ảnh hưởng kết quả.

### Vì sao cần tránh trạng thái chia sẻ?

Đoạn mã sau là một ví dụ **không nên dùng**:

```java
int[] counter = {0};

List<OrderView> views = orders.stream()
    .filter(order -> {
        counter[0]++; // Tác dụng phụ trong Predicate.
        return eligible.test(order);
    })
    .map(toView)
    .toList();
```

Cách này trộn việc đếm với kiểm tra điều kiện. Kết quả đếm phụ thuộc cách pipeline được thực thi; nếu chuyển sang parallel Stream, cập nhật phần tử của mảng này còn có thể xảy ra *data race*. Nếu cần số lượng kết quả, có thể dùng một terminal operation phù hợp:

```java
long eligibleCount = orders.stream()
    .filter(eligible)
    .count();
```

Với pipeline song song, ưu tiên các hàm **stateless** và **non-interfering**: không sửa nguồn Stream và không cập nhật trạng thái chung khi xử lý từng phần tử. `Predicate`/`Function` thuần thường thuận tiện hơn cho song song hóa, nhưng điều đó không khiến `parallelStream()` tự động nhanh hơn. Hiệu năng phụ thuộc chi phí xử lý, chia dữ liệu, bộ nhớ, thứ tự và overhead; cần đo trên dữ liệu thực tế.

Khi phải xử lý phép quét phụ thuộc phần tử trước, hoặc bộ quy tắc phức tạp có trạng thái, vòng lặp có thể rõ hơn. Các kỹ thuật nâng cao như collector tùy chỉnh, `Spliterator` hay Stream Gatherers phục vụ những bài toán riêng; không cần dùng chúng chỉ để kết hợp các điều kiện `Predicate` và phép biến đổi `Function` đơn giản.

## 7. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Viết `paid.and(minimumAmount).or(vipCustomer)` khi nghiệp vụ yêu cầu thanh toán bắt buộc | Khách VIP chưa thanh toán vẫn lọt | Dùng `paid.and(minimumAmount.or(vipCustomer))` |
| Gọi `function.andThen(predicate)` | Lỗi kiểu: `Predicate` không phải `Function` | Dùng `stream.map(function).filter(predicate)` hoặc lambda adapter |
| Lọc theo dữ liệu thô rồi mới chuẩn hóa dù yêu cầu kiểm tra dữ liệu chuẩn hóa | Loại nhầm giá trị | Đặt `map(normalize)` trước `filter(predicate)` |
| Truy cập thuộc tính của giá trị có thể `null` | `NullPointerException` | Kiểm tra null trước hoặc thiết kế đầu vào không nhận null |
| Đếm hoặc cập nhật danh sách bên ngoài trong `filter`/`map` | Tác dụng phụ khó dự đoán, dễ lỗi song song | Dùng terminal operation như `count`, `toList` hoặc collector phù hợp |
| Dùng chung một Stream cho hai terminal operation | `IllegalStateException` khi tiêu thụ lại | Tạo Stream mới từ nguồn |
| Cho rằng `map` luôn chạy với mọi phần tử | Hiểu sai lazy, short-circuit và tối ưu hóa | Không phụ thuộc vào tác dụng phụ của hàm |
| Biến đổi trong `Predicate` rồi biến đổi lặp lại ở `map` | Dễ tính trùng công việc | Cân nhắc `map` trước `filter` khi chỉ cần giá trị đã biến đổi |

## 8. Bài tập thực hành

### Bài 1: Bộ lọc ứng viên

Cho danh sách ứng viên có `yearsOfExperience`, `javaSkill` và `available`. Quy tắc: ứng viên phải sẵn sàng làm việc và có ít nhất 3 năm kinh nghiệm **hoặc** đạt mức kỹ năng Java yêu cầu. Hãy viết ba `Predicate` riêng, ghép bằng `and`/`or` đúng dấu ngoặc, rồi `map` thành một bản tóm tắt chứa tên và số năm kinh nghiệm. Kiểm thử trường hợp ứng viên chưa sẵn sàng nhưng kỹ năng rất cao.

### Bài 2: Chuẩn hóa mã sản phẩm

Nhận `List<String>` có thể chứa `null`, khoảng trắng và chữ hoa/chữ thường lẫn lộn. Chuẩn hóa mã bằng cách `strip` và `toUpperCase(Locale.ROOT)`; chỉ giữ mã bắt đầu bằng `"PRD-"`. Viết hai `Function`, ghép bằng `andThen`, sau đó kết hợp với `Predicate` trong Stream. Giải thích vì sao phải lọc null trước khi gọi `strip`.

### Bài 3: Phân biệt thứ tự ghép

Với `Function<String, String> trim`, `Function<String, Integer> length` và `Predicate<Integer> atLeastFive`, hãy tạo pipeline chỉ giữ các chuỗi có **độ dài sau trim ít nhất 5**. So sánh `trim.andThen(length)` với `length.compose(trim)`. Viết adapter `Predicate<String>` từ hai thành phần tương ứng và giải thích nguy cơ tính lặp nếu vẫn `map` lại các bước đó.

### Bài 4: Phân tích quy tắc thanh toán

Thay quy tắc ở ví dụ 4.1 bằng: “Đã thanh toán, và **không thuộc** nhóm khách bị chặn, và (đủ ngưỡng hoặc VIP)”. Xây thêm `Predicate<Order> blockedCustomer` và dùng `negate`. Tạo dữ liệu thử cho mọi nhánh điều kiện, nhất là khách VIP nhưng bị chặn.

### Bài 5: Đánh giá khả năng song song

Giả sử `Predicate` lấy dữ liệu cấu hình từ một biến có thể thay đổi khi pipeline chạy. Hãy nêu rủi ro về kết quả và đồng bộ khi sử dụng `parallelStream()`. Đề xuất cách đóng băng cấu hình thành dữ liệu bất biến trước khi chạy pipeline, và giải thích vì sao vẫn cần đo hiệu năng trước khi bật xử lý song song.

## 9. Tự kiểm tra kiến thức

- `Predicate<T>` trả về gì, và khác `Function<T,R>` ở điểm nào?
- Tại sao `and`/`or` có thể bỏ qua một số lần gọi điều kiện?
- `f.andThen(g)` và `g.compose(f)` khác nhau về cách viết nhưng cùng thứ tự thực hiện như thế nào?
- Nếu cần kiểm tra kết quả **sau** chuẩn hóa, nên đặt `filter` ở đâu so với `map`?
- Vì sao không nên dùng tác dụng phụ trong `Predicate`/`Function` để đếm phần tử của Stream?

**Ghi nhớ:** Chia một quy tắc lớn thành **Predicate kiểm tra điều kiện** và **Function chuyển đổi dữ liệu** giúp mô tả nghiệp vụ rõ, tái sử dụng và kiểm thử dễ hơn. Để kết quả đúng, luôn kiểm tra **phạm vi của điều kiện logic, thứ tự biến đổi, xử lý null** và đặc tính **lazy/short-circuit** của Stream.
