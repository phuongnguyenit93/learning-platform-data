# Đặt tên biến theo ý nghĩa dữ liệu và vai trò khi sử dụng `var`

*Chủ đề cha: Sử dụng var rõ ràng. Các quy tắc và ví dụ dưới đây còn phù hợp với Java hiện đại; chương trình hoàn chỉnh chạy với JDK 17 trở lên.*

## 1. Mục tiêu

Bạn cần biết cách:

1. Đặt tên biến để thể hiện **dữ liệu là gì**, **đang ở trạng thái nào**, **có vai trò gì trong phép xử lý** và **đơn vị đo** nếu cần.
2. Phân biệt **kiểu tĩnh suy luận từ initializer** với **nghĩa nghiệp vụ do tên biến truyền đạt**.
3. Đặt tên đúng cho các biến giữ đối tượng đơn, collection, Stream, Optional, cờ boolean và kết quả chuyển đổi.
4. Giữ code dùng `var` ngắn mà vẫn đọc được khi không thấy toàn bộ biểu thức bên phải.
5. Nhận ra tên gây hiểu nhầm và xác định khi nên dùng **kiểu tường minh** thay vì `var`.

Khi gặp:

```java
var x = orders.stream().filter(Order::paid).toList();
```

Trình biên dịch có thể suy luận kiểu của `x`, nhưng người đọc phải xem hết biểu thức mới biết nó mang vai trò gì. Nếu viết:

```java
var paidOrders = orders.stream().filter(Order::paid).toList();
```

thì `paidOrders` diễn đạt chính xác: đây là các đơn hàng đã thanh toán. Đây là lợi ích chính của tên có nghĩa khi dùng `var`.

**`var` là suy luận kiểu cục bộ (Java 10+), không phải kiểu động.** Compiler cố định kiểu của biến khi biên dịch; tên biến không thay đổi kiểu và không thay thế kiểm tra dữ liệu, nullability hay hợp đồng API.

## 2. Kiểu tĩnh và ý nghĩa nghiệp vụ là hai lớp thông tin

Xem ba giá trị:

```java
var customerId = "C-42";
var orderId = "O-42";
var couponCode = "SAVE10";
```

Cả ba được suy ra là `String` nhưng không thể thay thế cho nhau về ý nghĩa: ID khách hàng, ID đơn hàng và mã giảm giá. Nếu đặt hết là `value` hoặc `id` trong cùng một phương thức, người đọc dễ nhầm khi truyền đối số.

Ngược lại, một khái niệm có thể được biểu diễn qua các kiểu khác nhau:

```java
// Đoạn minh họa bên trong một phương thức
var orderId = "O-42";                         // String
var orderIds = java.util.List.of("O-42");      // List<String>
var orderCount = orderIds.size();             // int
```

Tên biến truyền tải **vai trò và số lượng**; kiểu biên dịch truyền tải **các thao tác hợp lệ**. Cả hai phải đúng.

Hãy chọn mức thông tin vừa đủ:

| Khía cạnh | Ví dụ tên | Ý nghĩa |
| --- | --- | --- |
| Thực thể | `customer`, `order`, `invoice` | Đối tượng nghiệp vụ nào |
| Thuộc tính | `customerId`, `billingAddress` | Thuộc tính của đối tượng nào |
| Tập hợp | `customers`, `orderIds` | Nhiều phần tử, khác một giá trị đơn |
| Điều kiện | `paidOrders`, `activeUsers` | Tập đã đáp ứng điều kiện nào |
| Giai đoạn | `rawInput`, `normalizedName` | Dữ liệu trước/sau biến đổi nào |
| Có thể vắng mặt | `maybeCustomer` | Chưa chắc tìm thấy đối tượng |
| Đơn vị | `retryDelaySeconds`, `sizeBytes` | Số đo được hiểu theo đơn vị nào |
| Câu hỏi đúng/sai | `hasPaidOrders`, `isExpired` | Ý nghĩa giá trị boolean |
| Cách tra cứu | `customersById` | Map có khóa nào và giá trị nào |

Không ghép mọi khía cạnh vào một tên dài. Chỉ nêu những thông tin nếu thiếu sẽ làm người đọc hiểu sai.

## 3. Quy ước Java hiện đại: rõ, ngắn, nhất quán

Biến cục bộ Java thường dùng **`lowerCamelCase`**: `customerName`, `paidOrderCount`, `timeoutMillis`. Đặt cùng một từ cho cùng một khái niệm trong phạm vi module; chẳng hạn đã dùng `customer` thì không tự đổi thành `client` ở một hàm khác nếu hai từ không có ý nghĩa khác nhau trong nghiệp vụ.

Tránh biến như `a`, `t2`, `obj`, `tmp`, `value1` và `result2` khi nhiều loại dữ liệu tồn tại. Đổi thành `currentOrder`, `requestedCustomerId`, `normalizedName` hoặc `eligibleOrders` tùy hành vi thực tế.

Không cần cố định số từ hay số ký tự. Tên `i` trong vòng lặp nhỏ có thể dễ đọc; tên `id` đủ trong lambda chỉ có một loại ID. Khi phương thức làm việc với ID khách hàng và ID đơn hàng, `customerId` và `orderId` an toàn hơn.

Tránh viết **thông tin kiểu dư thừa theo kiểu tiền tố Hungary**:

| Tên khó đọc | Tên đề xuất | Lý do |
| --- | --- | --- |
| `strName` | `customerName` | Ý nghĩa cụ thể hơn kiểu `String` |
| `intNum` | `retryCount` | Biết đang đếm gì |
| `lst1` | `pendingOrders` | Biết danh sách đại diện tập nào |
| `map2` | `ordersById` | Biết cách tra cứu |
| `boolFlag` | `isEligible` | Biết câu hỏi đúng/sai |
| `res` | `paidOrderIds` | Biết kết quả chứa dữ liệu gì |

Tuy vậy, những hậu tố như `ById`, `Millis`, `Ids` hay đôi khi `Stream` **có thể cần thiết**: chúng mô tả vai trò, đơn vị, tính chất tập hợp hoặc vòng đời pipeline, không đơn thuần là ghi lại kiểu.

## 4. Đặt tên theo đúng điều kiện nghiệp vụ

Một tên nên mô tả điều gì đã thật sự xảy ra với dữ liệu. Ví dụ:

```java
// Đoạn minh họa: orders là danh sách Order có sẵn
var paidOrders = orders.stream()
        .filter(Order::paid)
        .toList();

var paidOrderIds = paidOrders.stream()
        .map(Order::id)
        .toList();

var paidRevenueCents = paidOrders.stream()
        .mapToLong(Order::totalCents)
        .sum();
```

Những tên này cho biết một luồng xử lý rõ ràng: chọn đơn thanh toán → lấy mã đơn hoặc tính tổng tiền. Nếu đặt `approvedOrders` sau bộ lọc `paid()` thì sai, trừ khi nghiệp vụ xác định `paid` tương đương `approved`. **Đừng đặt tên khẳng định trạng thái chưa được code bảo đảm.**

Tên `paidRevenueCents` còn cho biết đơn vị là cent; vì cùng là `long`, compiler không tự kiểm tra tính tương thích đơn vị giữa cent và đồng/giây/mili giây. Tên phải phản ánh đúng quy ước dữ liệu.

## 5. Chương trình chạy được: tên biểu đạt dữ liệu và vai trò

Tạo **`OrderNamingDemo.java`**:

```java
import java.util.List;

public class OrderNamingDemo {
    record Order(String id, String customerId, long totalCents, boolean paid) {}

    public static void main(String[] args) {
        var orders = List.of(
                new Order("O-101", "C-1", 4500L, true),
                new Order("O-102", "C-2", 3000L, false),
                new Order("O-103", "C-1", 7500L, true)
        );

        var paidOrders = orders.stream()
                .filter(Order::paid)
                .toList();

        var paidOrderIds = paidOrders.stream()
                .map(Order::id)
                .toList();

        var paidRevenueCents = paidOrders.stream()
                .mapToLong(Order::totalCents)
                .sum();

        var hasPaidOrders = !paidOrders.isEmpty();

        System.out.println("paidOrderIds=" + paidOrderIds);
        System.out.println("paidRevenueCents=" + paidRevenueCents);
        System.out.println("hasPaidOrders=" + hasPaidOrders);
        System.out.println("allOrderCount=" + orders.size());
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 OrderNamingDemo.java
java OrderNamingDemo
```

Stdout chính xác:

```text
paidOrderIds=[O-101, O-103]
paidRevenueCents=12000
hasPaidOrders=true
allOrderCount=3
```

Các biến được suy luận và mang vai trò:

| Biến | Kiểu tĩnh | Vai trò |
| --- | --- | --- |
| `orders` | `List<Order>` | Toàn bộ đơn hàng đầu vào |
| `paidOrders` | `List<Order>` | Chỉ đơn đã thanh toán |
| `paidOrderIds` | `List<String>` | Mã của các đơn đã thanh toán |
| `paidRevenueCents` | `long` | Tổng số cent của tập đã lọc |
| `hasPaidOrders` | `boolean` | Có ít nhất một đơn đã thanh toán? |

Chính tên biến giúp hiểu phép biến đổi dù người đọc chưa nhớ mọi chữ ký `Stream`. Trình biên dịch vẫn kiểm tra các kiểu chính xác. Mô hình dùng `long` và cent để có số minh họa nguyên; bài toán tiền tệ thực tế cần quy ước về loại tiền và độ chính xác riêng, không chỉ dựa vào tên `Cents`.

Lưu ý `Stream.toList()` có từ Java 16 và trả danh sách **không hỗ trợ sửa bằng `add`/`remove`/`set`**. Tên `paidOrders` không tự bảo đảm mutable hay immutable; điều đó thuộc hợp đồng API.

## 6. Collection, Stream, một phần tử và kết quả terminal

### 6.1. Dùng số ít/số nhiều đúng vai trò

`order` thường là một `Order`; `orders` hoặc `paidOrders` là tập nhiều phần tử. Kể cả danh sách có 0 hoặc 1 phần tử, tên số nhiều vẫn hợp lý vì kiểu dữ liệu mang ý nghĩa tập.

```java
for (var order : orders) {
    System.out.println(order.id());
}
```

Ở đây `orders` có kiểu `List<Order>` và `order` là từng `Order`. Tên nhất quán giúp người đọc phân biệt collection và element mà không phải tự giải mã `var`.

### 6.2. Phân biệt pipeline với dữ liệu đã có

```java
// Minh họa bên trong method:
var paidOrderStream = orders.stream().filter(Order::paid);
var paidOrders = paidOrderStream.toList();
```

`paidOrderStream` có kiểu `Stream<Order>`, còn `paidOrders` là `List<Order>`. Hậu tố `Stream` ở đây có ích vì một Stream gắn với **một pipeline** và không được sử dụng lại sau khi tiêu thụ. Không gọi tiếp `paidOrderStream.count()` sau `toList()`.

Để đếm hoặc xử lý theo cách khác, tạo Stream mới từ collection nguồn hoặc từ `paidOrders`:

```java
var paidOrderCount = paidOrders.size(); // int
var allOrderCount = orders.stream().count(); // long
```

Nếu pipeline chỉ có một mục đích, dạng chain thường rõ hơn:

```java
var paidOrders = orders.stream()
        .filter(Order::paid)
        .toList();
```

Không tạo thêm biến `stream1`, `stream2` chỉ vì muốn viết mọi bước trên một dòng riêng. Chỉ tách khi tên mỗi bước giúp giải thích nghĩa hoặc làm rõ kiểu.

### 6.3. Tên trước/sau biến đổi

```java
// Giả sử rawNames là List<String>
var trimmedNames = rawNames.stream()
        .map(String::strip)
        .toList();

var nonBlankNames = trimmedNames.stream()
        .filter(name -> !name.isBlank())
        .toList();

var uniqueNames = nonBlankNames.stream()
        .distinct()
        .toList();
```

`trimmedNames` đã bỏ khoảng trắng ở hai đầu chuỗi; `nonBlankNames` đã loại các tên chỉ chứa khoảng trắng; `uniqueNames` đã loại trùng. Không gọi các bước này là `validatedNames` nếu chưa có điều kiện kiểm tra tính hợp lệ thực sự.

`map` có thể thay kiểu phần tử, còn `filter` và `distinct` không thay đổi `T`. Tên phản ánh ngữ nghĩa biến đổi; IDE/`javac` vẫn là nơi xác nhận `Stream<T>` hoặc `List<T>` thật.

## 7. Tên cho `Optional` và kết quả có thể vắng mặt

Khi có `var`, dễ bỏ sót một API trả **`Optional<T>` thay vì `T`**. Ví dụ:

```java
var maybeDisplayName = findDisplayName(namesById, "u9");
var displayName = maybeDisplayName.orElse("Guest");
```

`maybeDisplayName` là kết quả tìm có thể rỗng; `displayName` là chuỗi đã có fallback. Nếu cùng đặt `displayName` cho Optional, người đọc dễ gọi nhầm các phương thức của `String`.

Tạo **`OptionalNamingDemo.java`** để thấy rõ:

```java
import java.util.Map;
import java.util.Optional;

public class OptionalNamingDemo {
    static Optional<String> findDisplayName(
            Map<String, String> namesById, String userId) {
        return Optional.ofNullable(namesById.get(userId));
    }

    public static void main(String[] args) {
        var namesById = Map.of("u1", "Linh");

        var maybeDisplayName = findDisplayName(namesById, "u9");
        var displayName = maybeDisplayName.orElse("Guest");

        System.out.println("hasDisplayName=" + maybeDisplayName.isPresent());
        System.out.println("displayName=" + displayName);
    }
}
```

Chạy:

```bash
javac --release 17 OptionalNamingDemo.java
java OptionalNamingDemo
```

Stdout:

```text
hasDisplayName=false
displayName=Guest
```

Tên `maybe...` là một lựa chọn diễn đạt trạng thái, không phải quy tắc Java bắt buộc hoặc tên kiểu. Dự án có thể chọn `displayNameCandidate` hay quy ước khác miễn nhất quán và không gây hiểu nhầm. `Optional.ofNullable` nhận đầu vào có thể là `null`, nhưng bản thân `Optional` vẫn là đối tượng có hợp đồng riêng; tên không thay thế xử lý rỗng.

## 8. Đặt tên cho boolean như một câu hỏi

Biến kiểu `boolean` nên đọc được như một điều kiện đúng/sai rõ ràng:

| Khó hiểu | Dễ hiểu hơn | Điều kiện được hỏi |
| --- | --- | --- |
| `var flag = orders.isEmpty();` | `var hasNoOrders = orders.isEmpty();` | Không có đơn hàng? |
| `var test = attempts < retryLimit;` | `var canRetry = attempts < retryLimit;` | Có thể thử lại? |
| `var ok = age >= 18;` | `var isAdult = age >= 18;` | Có đủ điều kiện tuổi theo quy tắc này? |
| `var b = !paidOrders.isEmpty();` | `var hasPaidOrders = !paidOrders.isEmpty();` | Có đơn đã thanh toán? |

Các tiền tố `is...`, `has...`, `can...`, `should...` hoặc động từ `matches...` đều ổn tùy nghĩa. Không đặt `isValid` chỉ vì mới kiểm tra một điều kiện nhỏ; tên `isSyntaxValid` hoặc `matchesPattern` chính xác hơn nếu chỉ kiểm tra cú pháp/mẫu.

Tránh phủ định chồng phủ định làm khó hiểu:

```java
// Minh họa trong method:
var hasNoOrders = orders.isEmpty();
if (!hasNoOrders) {
    System.out.println("Có đơn hàng");
}
```

Trong trường hợp này `var hasOrders = !orders.isEmpty();` có thể dễ đọc hơn ở nhiều nơi. Chọn tên khớp đúng điều kiện và hướng suy nghĩ của đoạn code, không ép một tiền tố duy nhất.

## 9. Đơn vị đo và mốc thời gian

Vì `var duration = 5000;` không cho biết giá trị là đơn vị nào, tên nên thể hiện đơn vị khi số đo còn biểu diễn dưới dạng primitive:

```java
var timeoutMillis = 5000L;
var retryDelaySeconds = 2L;
var payloadSizeBytes = 4096L;
var subtotalCents = 1299L;
```

Tên có đơn vị giảm rủi ro hiểu sai, nhưng Java **không kiểm tra đơn vị bằng tên biến**. Một phương thức nhận `long` có thể vẫn chấp nhận nhầm mili giây thay vì giây.

Khi API cho phép, dùng kiểu mang ý nghĩa rõ ràng:

```java
var timeout = java.time.Duration.ofSeconds(5); // Duration
var startedAt = java.time.Instant.now();       // Instant
```

`Duration` là khoảng thời gian; `Instant` là một mốc thời gian. Tên `startedAt` nói đây là thời điểm bắt đầu, khác với `timeout`. Đây là API Java vẫn áp dụng hiện nay, tốt hơn việc dựa vào số nguyên không đơn vị cho mọi phép xử lý thời gian.

Một tên như `totalCents` chỉ đúng khi mô hình quy định tiền dùng cent và các giá trị có cùng loại tiền. Nếu ứng dụng xử lý nhiều loại tiền, cần mô hình dữ liệu có currency, không trộn chỉ vì cả hai là `long`.

## 10. Tên biểu diễn vòng đời và trạng thái chuyển đổi

Trong code xử lý đầu vào, nên dùng tên thể hiện đúng bước đã thực hiện:

```java
var rawGreeting = "  Hello  ";
var trimmedGreeting = rawGreeting.strip();
var upperGreeting = trimmedGreeting.toUpperCase(java.util.Locale.ROOT);
```

`rawGreeting` là đầu vào, `trimmedGreeting` đã được bỏ khoảng trắng hai đầu theo `strip`, `upperGreeting` được chuyển chữ hoa. Không đặt tên `validatedGreeting` nếu code chưa kiểm tra hợp đồng dữ liệu.

Với nghiệp vụ có trạng thái như draft, approved, persisted, cached, chỉ dùng `approvedOrder` hoặc `savedOrder` sau khi thao tác tương ứng đã được thực hiện và xác nhận đúng. Không suy đoán rằng đối tượng đã lưu chỉ vì một hàm tên `save` được gọi mà không xem hợp đồng của API.

Trong hàm dài, các tên trạng thái giúp thấy chuyển đổi rõ; nhưng nhiều tên gần giống như `result`, `result2`, `newResult`, `finalResult` là dấu hiệu cần cải thiện scope hoặc tách hàm theo nhiệm vụ.

## 11. Tên Map, Set và các định danh

Với `Map`, tên tốt thường nêu rõ quan hệ khóa → giá trị:

```java
var displayNamesById = java.util.Map.of(
        "u1", "Linh",
        "u2", "An"
);
var activeUserIds = java.util.Set.of("u1", "u2");
```

`displayNamesById` có nghĩa là tra tên hiển thị theo ID, không chỉ là một “map”. `activeUserIds` thể hiện các ID đang hoạt động, không phải `Set<User>`.

Khi duyệt:

```java
for (var userEntry : displayNamesById.entrySet()) {
    var userId = userEntry.getKey();
    var displayName = userEntry.getValue();
    System.out.println(userId + ": " + displayName);
}
```

`userEntry` được suy luận là `Map.Entry<String, String>`. `userId` và `displayName` đều là `String` nhưng khác nghĩa. Vì `Map.of` không bảo đảm thứ tự duyệt, không dùng đoạn này để dạy một stdout có thứ tự dòng cố định.

Tên `map` hoặc `set` có thể chấp nhận trong một helper tổng quát thực sự xử lý cấu trúc dữ liệu; trong mã nghiệp vụ, nên đặt theo nội dung và cách truy xuất.

## 12. Tên đẹp không sửa được suy luận kiểu sai của `var`

`var` suy ra kiểu từ biểu thức khởi tạo. Ví dụ:

```java
// Đoạn minh họa trong method:
var customerNames = new java.util.ArrayList<>();
customerNames.add("Lan");
// String first = customerNames.get(0); // Lỗi biên dịch: Object không gán được cho String
```

Tên `customerNames` gợi ý danh sách `String`, nhưng compiler suy luận `ArrayList<Object>` khi `new ArrayList<>()` không có ngữ cảnh phần tử cụ thể.

Sửa bằng cách cung cấp kiểu thực:

```java
// Hai lựa chọn tương đương về ý định nhưng khác kiểu biến
var customerNames = new java.util.ArrayList<String>();
// customerNames: ArrayList<String>

java.util.List<String> namesAsList = new java.util.ArrayList<>();
// namesAsList: List<String>
```

Đây là đoạn minh họa hai lựa chọn; nếu dùng trong cùng phương thức, tránh trùng tên biến. Kiểu tường minh `List<String>` có thể tốt khi muốn nhấn mạnh hợp đồng interface thay vì lớp triển khai.

Một trường hợp khác:

```java
// var customer = null; // Lỗi: null không cung cấp kiểu suy luận cho var
String customer = null; // Hợp lệ, vì kiểu đích đã rõ
```

Tên `customer` hay `maybeCustomer` không làm `var ... = null` trở thành hợp lệ. Suy luận kiểu và diễn đạt ý nghĩa phải được thiết kế đồng thời.

Với generic factory `Stream.empty()` hoặc `new ArrayList<>()`, đôi khi kiểu phần tử được suy luận là `Object` khi không có ngữ cảnh hẹp hơn. Nếu API cần `String`, hãy ghi `Stream.<String>empty()`, `new ArrayList<String>()` hoặc khai báo kiểu đích tường minh.

## 13. Khi nào dùng `var`, khi nào ghi kiểu?

Dùng `var` khi initializer và tên giúp nhận diện kiểu/vai trò dễ dàng:

```java
var customerId = "C-42";
var createdAt = java.time.Instant.now();
var paidOrderIds = paidOrders.stream().map(Order::id).toList();
```

Cân nhắc ghi kiểu khi:

- Muốn dùng abstraction `List<Order>` thay vì ràng buộc vào `ArrayList<Order>`.
- Kiểu generic khó nhìn ra từ initializer hoặc diamond `<>` có thể suy luận quá rộng.
- Cần khai báo với `null` ban đầu (vì `var x = null` không hợp lệ).
- Kiểu trả về API ít quen thuộc và người đọc phải hover nhiều lần mới hiểu.
- Codebase có quy tắc rõ ràng để ưu tiên kiểu tường minh tại ranh giới quan trọng.

```java
java.util.List<String> labels = new java.util.ArrayList<>();
```

Trong ví dụ này, `labels` là tên ngắn và đủ rõ; kiểu tường minh cung cấp hợp đồng element `String` và interface `List`. Không cần ép tất cả biến sang `var`.

`var` chỉ áp dụng ở những vị trí Java hỗ trợ như khai báo biến cục bộ có initializer và biến trong vòng lặp thích hợp; không dùng thay kiểu field, kiểu trả về phương thức hay tham số phương thức thông thường. `var` cũng không làm một đối tượng trở nên mutable hay immutable.

## 14. Tên trong lambda, vòng lặp và phương thức dài

Xét:

```java
var eligibleOrderIds = orders.stream()
        .filter(order -> order.paid() && order.totalCents() >= 5000L)
        .map(Order::id)
        .toList();
```

Tên `order` trong lambda giúp đọc điều kiện; `eligibleOrderIds` nói đây là các ID đã qua một quy tắc chọn. Tuy nhiên, nếu “eligible” trong nghiệp vụ còn yêu cầu điều kiện khác, tên này không đủ chính xác; khi đó đặt `paidLargeOrderIds` hoặc tên diễn đạt đúng quy tắc được áp dụng.

Với lambda một dòng rất ngắn, `n -> n * 2` có thể đủ rõ. Nhưng khi có hai đối tượng cùng tham gia, `sourceOrder` và `targetOrder` rõ hơn `a` và `b`. Không lặp lại toàn bộ tên kiểu trong từng tham số nếu ngữ cảnh đã đủ.

Một phương thức xử lý cả nhiều loại định danh nên giữ `customerId`, `orderId` riêng. Đừng dùng cùng một tên `id` ở nhiều scope chồng nhau khiến người review phải dò lại đối tượng.

Tên tốt giúp code đọc dễ hơn, nhưng không thay thế chia nhỏ phương thức quá dài. Nếu code chứa hàng chục biến kiểu `raw...`, `new...`, `final...` không có ý nghĩa rõ, cân nhắc chia các bước xử lý thành hàm riêng với hợp đồng đầu vào/đầu ra chính xác.

## 15. Các lỗi đặt tên phổ biến

| Mẫu gây khó hiểu | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `var data = loadOrders();` | Không nói dữ liệu nào | `var orders = loadOrders();` nếu API thật sự trả đơn hàng |
| `var count = orders.stream();` | Biến không phải số đếm | `orderStream` hoặc dùng `.count()` để nhận `orderCount` |
| `var validatedEmail = rawEmail.strip();` | Chưa validate, chỉ strip | `trimmedEmail` |
| `var approvedOrders = orders.stream().filter(Order::paid).toList();` | Nhầm paid với approved | `paidOrders` nếu quy tắc là đã thanh toán |
| `var x = amountMillis;` | Mất đơn vị ở tên | Giữ `durationMillis` hoặc dùng `Duration` |
| `var user = findUser(id);` khi API trả Optional | Dễ tưởng có User chắc chắn | `maybeUser` hoặc tên thể hiện kết quả tìm |
| `var listOfEveryPaidOrderWithAnId = ...` | Quá dài, lặp thông tin | `paidOrders` nếu mọi Order đều có ID |
| `var productNames = new ArrayList<>();` | Tên không quyết định generic T | Chỉ rõ `new ArrayList<String>()` hoặc kiểu đích |

Không có tên nào tốt cho mọi hoàn cảnh. Tên `result` đôi khi hợp lý trong một hàm chuyển đổi có đúng một kết quả duy nhất; vấn đề là tên có **gây mơ hồ trong phạm vi đang đọc hay không**.

## 16. Kiểm tra khi review hoặc đổi tên bằng IDE

Đọc code chứa `var` theo hai trục:

**Kiểu tĩnh:** hover biến trong IDE để xem kiểu được suy luận; kiểm tra generic parameter, `Optional<T>`, `Stream<T>`/`List<T>`, primitive và kiểu trả về API. Khi không rõ, biên dịch với `javac` theo đúng version và language level của dự án. Không dùng cast không an toàn chỉ để “làm tên và kiểu khớp nhau”.

**Ngữ nghĩa:** hỏi biến mô tả thực thể gì, điều kiện lọc nào, trạng thái chuyển đổi nào, đơn vị nào và người đọc có thể hiểu phép dùng tiếp theo khi initializer nằm ngoài màn hình hay không.

IDE hỗ trợ Rename refactoring để đổi tên các tham chiếu trong scope an toàn hơn thay thế văn bản thủ công. Tuy vậy, IDE không thể tự xác minh `paid` có tương đương `approved` theo nghiệp vụ: con người vẫn cần review tên sau refactor.

Checklist ngắn:

1. Tên thể hiện dữ liệu và vai trò cụ thể, không chỉ là tên kiểu?
2. Tên số nhiều/số ít phù hợp collection hay phần tử?
3. Tên boolean đọc được như câu hỏi chính xác?
4. Số đo có đơn vị khi cần?
5. Tên trước–sau biến đổi phản ánh thao tác thật?
6. Tên Optional/Stream có tránh nhầm với đối tượng/kết quả terminal?
7. Kiểu mà `var` suy luận có đúng ý định?
8. Có nên ghi kiểu tường minh để truyền tải API contract?
9. Tên đủ ngắn, nhất quán và phù hợp domain?

## 17. Bài tập có lời giải

### Bài 1: Đổi tên theo vai trò và đơn vị

```java
// Giả sử orders là List<Order>
var a = 2500L;
var b = orders.stream().filter(Order::paid).toList();
var c = b.size();
```

`a` là thời gian chờ tính bằng mili giây. Đặt tên:

```java
var timeoutMillis = 2500L;
var paidOrders = orders.stream().filter(Order::paid).toList();
var paidOrderCount = paidOrders.size();
```

Kiểu lần lượt là `long`, `List<Order>`, `int`. `paidOrderCount` rõ hơn `c` và `timeoutMillis` cho biết đơn vị.

### Bài 2: Tên sai với Stream

```java
var orderCount = orders.stream().filter(Order::paid);
```

Biến đang là `Stream<Order>`, chưa phải count. Nếu muốn số đếm:

```java
var paidOrderCount = orders.stream()
        .filter(Order::paid)
        .count(); // long
```

Nếu muốn giữ pipeline, tên `paidOrderStream` là phù hợp.

### Bài 3: Giá trị có thể vắng mặt

```java
var displayName = findDisplayName(namesById, userId);
```

Giả sử `findDisplayName` trả `Optional<String>`. Tên `displayName` dễ làm người đọc tưởng đây là `String`. Có thể sửa:

```java
var maybeDisplayName = findDisplayName(namesById, userId);
var displayName = maybeDisplayName.orElse("Guest");
```

Như vậy tên thứ hai mới thực sự giữ một chuỗi dùng được.

### Bài 4: Có tên tốt nhưng kiểu chưa đúng

```java
var productNames = new java.util.ArrayList<>();
productNames.add("Mouse");
// String first = productNames.get(0);
```

Dòng gán cho `String` nếu bỏ chú thích sẽ không biên dịch vì kiểu phần tử bị suy luận `Object`. Hãy khai báo `var productNames = new ArrayList<String>();` hoặc `List<String> productNames = new ArrayList<>();`. Tên `productNames` không tự thay đổi generic type.

### Bài 5: Trạng thái chưa được đảm bảo

```java
var approvedOrders = orders.stream()
        .filter(Order::paid)
        .toList();
```

Nếu `paid` chỉ biểu thị đã thanh toán, tên nên là `paidOrders`; chỉ gọi `approvedOrders` sau khi điều kiện approved thật sự được áp dụng.

### Bài 6: Tên trước và sau biến đổi

```java
var x = "  Hello  ";
var y = x.strip();
```

Đề xuất `rawGreeting` và `trimmedGreeting`. Không đặt `validatedGreeting` nếu chưa kiểm tra bất kỳ ràng buộc hợp lệ nào.

## 18. Ghi nhớ

Khi dùng `var`, **kiểu tĩnh** đến từ initializer, còn **ý nghĩa dữ liệu** đến từ tên và ngữ cảnh. Tên nên diễn đạt đúng thực thể, trạng thái, mục đích, số lượng, khả năng vắng mặt hoặc đơn vị nếu chúng ảnh hưởng cách sử dụng. Tránh tên sai nghĩa dù compiler vẫn chấp nhận; tránh cho rằng tên đẹp có thể sửa generic inference sai. Chọn kiểu tường minh khi nó làm hợp đồng API rõ hơn. Một tên tốt giúp người đọc hiểu được đoạn code ngay cả khi không nhìn thấy cả dòng initializer, trong khi `javac` vẫn bảo đảm quy tắc kiểu tĩnh của Java.