# Dữ liệu bất biến và hạn chế thay đổi trạng thái dùng chung trong Java

## 1. Vì sao đây là nguyên lý cốt lõi của functional programming?

**Dữ liệu bất biến (immutable data)** là dữ liệu mà trạng thái quan sát được không thay đổi sau khi tạo. **Trạng thái dùng chung (shared mutable state)** là dữ liệu có thể bị nhiều đoạn mã hoặc luồng thực thi cùng đọc và sửa. Hạn chế trạng thái dùng chung làm chương trình dễ suy luận, kiểm thử, kết hợp các phép biến đổi và xử lý đồng thời an toàn hơn.

Trong Java, functional programming là một *phong cách thiết kế*, không có nghĩa mọi biến hay mọi object đều phải bất biến. Mục tiêu thực tế là:

1. Mỗi bước xử lý nhận đầu vào, tạo **kết quả mới** thay vì ngầm sửa đầu vào.
2. Dùng các hàm ít hoặc không có tác dụng phụ (*side effects*) trong `map`, `filter`, `reduce` và các phép biến đổi khác.
3. Khi nhiều nơi cùng cần một giá trị, ưu tiên chia sẻ **giá trị bất biến**; nếu cần thay đổi, xác định rõ đối tượng sở hữu thay đổi đó.
4. Thực hiện ghi database, cập nhật UI, log, gọi API và các side effects khác tại những ranh giới được kiểm soát.

Xét một danh sách đơn hàng. Nếu hàm tính tiền âm thầm xóa dòng hàng, hoặc một lambda sửa biến đếm chung trong lúc đang `parallelStream()`, cùng một lời gọi có thể cho kết quả khó dự đoán. Nếu đầu vào được bảo vệ khỏi sửa ngoài ý muốn và tổng tiền là một hàm chỉ đọc, kết quả sẽ ổn định hơn.

## 2. Phân biệt `final`, bất biến và không cho sửa collection

Các khái niệm sau có phạm vi khác nhau:

| Cơ chế | Đảm bảo | Điều **không** được đảm bảo |
| --- | --- | --- |
| Biến cục bộ `final` | Không gán lại biến sang tham chiếu/giá trị khác | Không ngăn sửa object được tham chiếu |
| Trường `private final` | Trường được gán khi khởi tạo theo quy tắc của Java | Nếu trường tham chiếu object mutable, nội dung object vẫn có thể thay đổi |
| `record` | Tự sinh accessor, constructor, `equals`/`hashCode`/`toString` dựa trên các component; trường instance là `final` | Không tự sao chép sâu `List`, array hay các component mutable |
| `Collections.unmodifiableList(list)` | Chặn sửa *qua wrapper* | Dữ liệu nhìn qua wrapper vẫn thay đổi nếu người khác sửa `list` gốc |
| `List.copyOf(list)` | Danh sách kết quả không sửa được; tạo ảnh chụp cấu trúc không bị ảnh hưởng bởi sửa cấu trúc nguồn sau đó | Không làm các phần tử bên trong trở nên bất biến |
| `Stream.toList()` (Java 16+) | Danh sách kết quả không sửa được qua `add`, `set`, `remove` | Không sao chép sâu phần tử; không tự bảo vệ các object mutable được tham chiếu |

Ví dụ, `final List<String> names = new ArrayList<>()` vẫn cho phép `names.add("Lan")`; chỉ không cho phép `names = otherList`. `final` bảo vệ *biến tham chiếu*, còn bất biến đòi hỏi bảo vệ *trạng thái quan sát được của object*.

### Wrapper chỉ đọc là một “cửa sổ” nhìn vào collection gốc

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("B");

System.out.println(view);     // [A, B]
System.out.println(snapshot); // [A]
```

Đoạn trên là minh họa để đặt trong phương thức hoặc `jshell`. `view` không cho gọi `view.add(...)`, nhưng vẫn nhìn thấy phần tử được thêm vào `source`. `snapshot` không đổi theo việc thêm `B` vào `source`. Cả hai đều không cho thao tác sửa trực tiếp qua chính danh sách đó. Các phương thức tạo collection bất biến như `List.of` và `List.copyOf` cũng không nhận phần tử `null`.

> **Bất biến nông và bất biến sâu:** một danh sách không cho sửa cấu trúc vẫn có thể chứa các object mutable. Nếu `List<PersonMutable>` chứa một object có `setName`, thay đổi tên qua tham chiếu khác vẫn làm tên trong danh sách trông như thay đổi. Phải xem xét tính bất biến của toàn bộ đồ thị object liên quan, không chỉ của collection ngoài cùng.

## 3. Mô hình dữ liệu bất biến với Java 17

Ta dùng `record` để biểu diễn một dòng hàng và một đơn hàng. `String` và `BigDecimal` là các kiểu bất biến; danh sách dòng hàng được sao chép phòng vệ (*defensive copy*). Hàm tính tiền chỉ đọc dữ liệu và trả về một giá trị mới.

Bốn quy tắc quan trọng:

- **Xác thực đầu vào:** từ chối mã rỗng, số lượng không hợp lệ, giá âm và giá trị `null`.
- **Sao chép khi đi vào:** constructor nhận `List` từ bên ngoài thì gọi `List.copyOf`.
- **Không mở đường sửa qua accessor:** accessor `items()` trả về danh sách không sửa được.
- **Không giấu trạng thái mutable trong record:** các phần tử `Item` chỉ chứa `String`, `int` và `BigDecimal`.

Các quy tắc này tạo một object `Order` có trạng thái bất biến đối với các thao tác được công bố trong ví dụ. Record **không mặc nhiên sâu bất biến** nếu component chứa array, `Date` hoặc lớp mutable khác.

## 4. Chương trình hoàn chỉnh: sửa bằng cách tạo giá trị mới

Tạo tệp **`ImmutableOrderDemo.java`**. Ví dụ chạy trên **Java 17+**, không cần thư viện ngoài JDK.

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public class ImmutableOrderDemo {
    record Item(String sku, int quantity, BigDecimal unitPrice) {
        Item {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException("Invalid item");
            }
        }

        BigDecimal total() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record Order(String id, List<Item> items) {
        Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(items, "items");
            if (id.isBlank()) {
                throw new IllegalArgumentException("Blank order id");
            }
            items = List.copyOf(items); // Chặn sửa cấu trúc từ bên ngoài
        }

        BigDecimal total() {
            return items.stream()
                    .map(Item::total)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
        }
    }

    private static BigDecimal money(String value) {
        return new BigDecimal(value);
    }

    // Không sửa order ban đầu: tạo một Order mới với danh sách mới.
    private static Order withAdditionalItem(Order order, Item additional) {
        Objects.requireNonNull(order, "order");
        Objects.requireNonNull(additional, "additional");
        List<Item> next = new ArrayList<>(order.items());
        next.add(additional);
        return new Order(order.id(), next);
    }

    public static void main(String[] args) {
        List<Item> editable = new ArrayList<>(List.of(
                new Item("BOOK", 2, money("120000")),
                new Item("PEN", 3, money("10000"))
        ));

        Order original = new Order("A01", editable);

        // Sửa nguồn sau khi tạo Order không sửa dữ liệu trong Order.
        editable.clear();
        System.out.println("Nguon sau clear: " + editable.size());
        System.out.println("Don goc - so dong: " + original.items().size());
        System.out.println("Don goc - tong: " + original.total().toPlainString());

        Order updated = withAdditionalItem(
                original,
                new Item("BAG", 1, money("200000"))
        );
        System.out.println("Don moi - so dong: " + updated.items().size());
        System.out.println("Don moi - tong: " + updated.total().toPlainString());
        System.out.println("Don goc sau bien doi: "
                + original.total().toPlainString());

        Order second = new Order("A02", List.of(
                new Item("PEN", 5, money("10000"))
        ));
        List<Order> orders = List.of(original, second);

        // map + reduce: không cần biến tích lũy dùng chung.
        BigDecimal revenue = orders.stream()
                .map(Order::total)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("Tong hai don: " + revenue.toPlainString());

        // Collector tạo kết quả mới từ dữ liệu đầu vào.
        Map<String, BigDecimal> totalsById = orders.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Order::id,
                        Order::total
                ));
        System.out.println("A02 trong map: "
                + totalsById.get("A02").toPlainString());

        // Các hàm chỉ đọc + reduce cho phép tổng hợp song song an toàn.
        BigDecimal parallelTotal = orders.parallelStream()
                .map(Order::total)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("Tong song song: "
                + parallelTotal.toPlainString());
    }
}
```

Biên dịch và chạy trong thư mục có tệp:

```bash
javac --release 17 ImmutableOrderDemo.java
java ImmutableOrderDemo
```

**Stdout dự kiến chính xác:**

```text
Nguon sau clear: 0
Don goc - so dong: 2
Don goc - tong: 270000
Don moi - so dong: 3
Don moi - tong: 470000
Don goc sau bien doi: 270000
Tong hai don: 320000
A02 trong map: 50000
Tong song song: 320000
```

Các giá trị có thể kiểm tra bằng tay:

- A01 ban đầu: `2 × 120000 + 3 × 10000 = 270000`.
- A01 mới: `270000 + 1 × 200000 = 470000`. Giá trị `original` vẫn là `270000`.
- A02: `5 × 10000 = 50000`.
- Tổng `original` và A02 trong `orders`: `270000 + 50000 = 320000`. Danh sách `orders` cố ý chứa **original**, không chứa `updated`; đây là lý do kết quả không phải `520000`.
- `parallelStream` áp dụng `map` và `reduce` trên cùng tập hai đơn với phép cộng `BigDecimal`, nên tổng vẫn là `320000`.

Chương trình in trực tiếp giá trị theo mã đơn thay vì duyệt `Map`, bởi `Collectors.toUnmodifiableMap` **không cam kết thứ tự duyệt khóa**. `toUnmodifiableMap` cũng yêu cầu các khóa không trùng nhau trong overload hai tham số; hai đơn có cùng `id` sẽ gây `IllegalStateException` tại bước collect. Đây là điều cần kiểm tra khi mã đơn đến từ dữ liệu thực.

## 5. “Biến đổi” theo kiểu functional: từ giá trị cũ tạo giá trị mới

Hàm `withAdditionalItem` thực hiện ba bước:

1. Nhận `Order` đầu vào và một `Item` mới.
2. Tạo `ArrayList` **nội bộ** từ danh sách cũ, thêm phần tử trên bản sao.
3. Tạo `Order` mới; constructor lại bảo vệ danh sách bằng `List.copyOf`.

Dùng một biến mutable **cục bộ** trong lúc dựng kết quả không làm vi phạm mục tiêu giảm shared mutable state: danh sách tạm chỉ do một lời gọi hàm sở hữu, không bị trả ra ngoài. Điểm quan trọng là hàm **không sửa đối tượng đầu vào** và không giữ biến mutable đó để bên khác cùng tác động.

So sánh hai cách giải quyết một yêu cầu “thêm hàng vào đơn”:

```java
// Cách có tác dụng phụ, giả sử MutableOrder có getter trả về List mutable:
void addItemInPlace(MutableOrder order, Item item) {
    order.getItems().add(item); // Bên gọi có thể thấy Order cũ đổi trạng thái.
}

// Cách tạo giá trị mới, dùng kiểu Order bất biến của chương trình:
Order withAdditionalItem(Order order, Item item) {
    List<Item> next = new ArrayList<>(order.items());
    next.add(item);
    return new Order(order.id(), next);
}
```

Đoạn `MutableOrder` là **mã minh họa**, không phải phần bổ sung cần dán vào tệp `ImmutableOrderDemo.java`. Biến đổi bất biến thường tốn cấp phát/copy nhiều hơn thay đổi tại chỗ, nhưng đổi lại giảm các phụ thuộc ẩn. Với collection rất lớn hoặc số lần sửa nhiều, cân nhắc cấu trúc dữ liệu persistent/structural sharing từ thư viện thích hợp; JDK `List.copyOf` không cung cấp một cấu trúc persistent tổng quát cho việc thêm phần tử.

## 6. Hàm thuần, tác dụng phụ và tính dễ kiểm thử

Một hàm **thuần (pure function)** có hai tính chất:

- Với cùng đầu vào theo giá trị, cho cùng kết quả.
- Không có tác dụng phụ quan sát được: không sửa input, biến toàn cục, file, database, UI hay trạng thái ngoài.

`Item.total()`, `Order.total()` và `withAdditionalItem(...)` là những ví dụ gần với cách thiết kế thuần trong bài. Các hàm này dễ kiểm tra bằng cách truyền dữ liệu xác định và so sánh đầu ra; không cần dựng database, đồng hồ giả hay biến toàn cục. `Order.total()` còn dùng `BigDecimal` bất biến nên `add` tạo một giá trị mới, không chỉnh tổng trước đó.

Ngược lại, các thao tác sau có side effect: `System.out.println`, gửi HTTP, ghi file, gọi `repository.save(...)`, cập nhật `AtomicInteger` hoặc thêm phần tử vào một danh sách có người khác giữ tham chiếu. Side effect **không phải luôn sai**. Mã ứng dụng phải tương tác với thế giới bên ngoài; nên tổ chức chúng ở tầng điều phối/đầu vào-đầu ra, trong khi phần biến đổi nghiệp vụ có thể chạy độc lập và kiểm thử thuận tiện.

Ví dụ minh họa cách tách tính toán và hiển thị:

```java
// Hàm tính toán: không in và không sửa danh sách orders.
BigDecimal calculateRevenue(List<Order> orders) {
    return orders.stream()
            .map(Order::total)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
}

// Ở tầng gọi:
BigDecimal revenue = calculateRevenue(orders);
System.out.println(revenue.toPlainString());
```

Đây là **phác thảo phương thức** dùng các kiểu `Order` đã định nghĩa trong chương trình trước; không phải chương trình độc lập. Thiết kế này giúp test `calculateRevenue` mà không phải bắt stdout.

## 7. Lambda, biến `effectively final` và giới hạn thực sự của quy tắc

Lambda có thể đọc biến cục bộ được khai báo `final` hoặc **effectively final** (không bị gán lại sau khi khởi tạo):

```java
BigDecimal threshold = new BigDecimal("100000");
List<Order> expensive = orders.stream()
        .filter(order -> order.total().compareTo(threshold) > 0)
        .toList();
```

Dù không ghi từ khóa `final`, `threshold` vẫn effectively final vì không bị gán lại. Nếu cố gán lại `threshold` ở chỗ khác trong cùng phạm vi, lambda sử dụng nó sẽ không biên dịch. Tuy nhiên, tính effectively final **không làm trạng thái của object được capture trở nên bất biến**:

```java
// Phản ví dụ: biên dịch được nhưng có tác dụng phụ.
List<String> output = new ArrayList<>();
orders.stream()
        .map(Order::id)
        .forEach(output::add); // Ghi vào danh sách mutable bên ngoài.
```

Biến `output` không bị gán lại nhưng nội dung danh sách bị thay đổi. Trong pipeline tuần tự nhỏ, thao tác này có thể tạo ra kết quả mong đợi, song nó tăng phụ thuộc ẩn và dễ trở thành lỗi khi chuyển sang chạy song song.

Ưu tiên thu thập kết quả bằng một terminal operation:

```java
List<String> ids = orders.stream()
        .map(Order::id)
        .toList(); // Tạo danh sách kết quả không thể sửa qua API List.
```

`map` nên mô tả phép biến đổi. `peek` cũng không nên được dùng làm nơi cài logic cập nhật trạng thái: nó chủ yếu hỗ trợ quan sát/debug và không bảo đảm mọi side effect sẽ chạy trong mọi trường hợp tối ưu pipeline (ví dụ có short-circuit hoặc `count` trên nguồn có kích thước đã biết).

## 8. Vì sao shared mutable state gây lỗi đặc biệt khi xử lý song song?

Giả sử muốn cộng các số từ 1 đến 10000. Đoạn sau dùng một mảng làm ô chứa tổng rồi nhiều luồng cùng sửa:

```java
// PHẢN VÍ DỤ: không dùng để tính tổng đúng.
int[] shared = {0};
java.util.stream.IntStream.rangeClosed(1, 10_000)
        .parallel()
        .forEach(n -> shared[0] += n);

System.out.println(shared[0]); // Không có bảo đảm bằng 50005000.
```

`shared[0] += n` gồm đọc, cộng, ghi; đây không phải thao tác nguyên tử. Nhiều luồng có thể cùng đọc giá trị cũ và ghi đè kết quả của nhau (*lost update*). Java Memory Model cũng không đảm bảo các truy cập không đồng bộ này có quan hệ happens-before thích hợp. Việc chạy một lần ra đúng không chứng minh mã an toàn.

Cách diễn đạt phép tính dưới dạng **reduction**:

```java
int sum = java.util.stream.IntStream.rangeClosed(1, 10_000)
        .parallel()
        .sum();
System.out.println(sum); // 50005000
```

`sum()` để Stream API quản lý các kết quả trung gian và phép kết hợp. Với tập 1..10000, kết quả vừa trong `int`; với tổng có khả năng vượt giới hạn `int`, chọn `LongStream` hoặc `BigInteger` tùy yêu cầu.

Nếu phải cập nhật bộ đếm chung vì một lý do riêng (ví dụ bộ đo tác vụ bên ngoài pipeline), có thể dùng `AtomicLong`/`LongAdder` hoặc khóa phù hợp. Nhưng đếm/tổng hợp **kết quả của stream** thường nên thực hiện bằng `count()`, `sum()`, `reduce()` hoặc `collect()`, tránh thêm shared mutable state không cần thiết.

### Lưu ý về collector và toán tử kết hợp

Các toán tử dùng trong parallel reduction phải phù hợp về **tính kết hợp**, **phần tử đơn vị** và không tạo tác dụng phụ ngoài ý muốn:

- Cộng số nguyên trong phạm vi không tràn và cộng `BigDecimal` là ví dụ dễ hiểu.
- Không dùng phép trừ `a - b` làm toán tử tùy tiện cho `reduce(identity, accumulator)` trong parallel stream vì phép trừ không có tính kết hợp.
- Không để accumulator thay đổi cùng một `ArrayList` hay `HashMap` được nhiều nhánh stream dùng chung.
- `Collectors.toList()`/`groupingBy(...)` có cơ chế container/combiner riêng theo contract collector; bản thân kết quả có thể mutable, và điều đó **không có nghĩa** các luồng đang đua nhau ghi vào một container duy nhất theo cách làm tùy tiện.

`parallelStream()` cũng không tự động nhanh hơn: phân tách, phối hợp, cấp phát và kích thước dữ liệu ảnh hưởng hiệu năng. Chọn song song sau khi đã đúng về ngữ nghĩa và đo hiệu năng thực tế.

## 9. An toàn giữa các thread: bất biến giúp gì và không giúp gì?

Một object bất biến đã được khởi tạo đúng thường dễ chia sẻ giữa các thread vì các thread chỉ đọc cùng trạng thái. Đối với object có các trường `final`, Java Memory Model có các bảo đảm khởi tạo quan trọng khi constructor hoàn tất đúng cách; không để `this` thoát ra khi object còn đang được dựng. Trong ví dụ, `Order` chứa `List.copyOf` với các `Item` có component bất biến, nên thao tác đọc `total()` không cần khóa để bảo vệ trạng thái nội tại của `Order`.

Tuy vậy, cần phân biệt:

1. **Object bất biến**: trạng thái của riêng giá trị đó không đổi.
2. **Tham chiếu được công bố/chuyển giao đúng**: luồng khác nhận được tham chiếu theo cơ chế thích hợp. Sử dụng `final`, `volatile`, khóa, queue đồng thời hoặc các cơ chế đồng bộ theo tình huống.
3. **Chuỗi thao tác nghiệp vụ nguyên tử**: chẳng hạn “kiểm tra số dư rồi trừ tiền” vẫn cần giao dịch/đồng bộ ngay cả khi từng bản ghi giao dịch là một giá trị bất biến.

Ví dụ, thay toàn bộ cấu hình ứng dụng bằng một giá trị cấu hình bất biến mới có thể an toàn khi tham chiếu cấu hình được công bố qua `volatile` hoặc `AtomicReference`. Nếu cần cập nhật đồng thời dựa trên giá trị trước đó, phải dùng thao tác atomically compare-and-set hoặc đồng bộ thích hợp, chứ chỉ tạo object bất biến chưa đủ.

Cần tránh hai suy luận quá mức: **“record luôn thread-safe”** (sai nếu chứa component mutable hoặc phương thức truy cập trạng thái bên ngoài) và **“dùng Stream là tự động thread-safe”** (sai nếu lambda chạm vào biến mutable chia sẻ).

## 10. Lựa chọn chiến lược trong ứng dụng thật

| Tình huống | Hướng tiếp cận | Lý do |
| --- | --- | --- |
| DTO đọc dữ liệu, cấu hình, value object | `record` + các component bất biến + defensive copy | Dễ chia sẻ và đối chiếu giá trị |
| Danh sách đầu vào nhận từ caller | `List.copyOf` sau khi xác thực | Không bị sửa cấu trúc từ bên ngoài |
| Cần dựng một kết quả nhiều bước | Mutable builder hoặc `ArrayList` cục bộ, rồi snapshot | Tiện xây dựng nhưng không phát tán trạng thái tạm |
| Lọc, sắp xếp, tổng hợp dữ liệu | `filter`/`map`/`toList`/`reduce`/`collect` | Mỗi bước mô tả rõ phép chuyển đổi |
| Bộ đếm cập nhật đồng thời thật sự | `AtomicLong` hoặc `LongAdder` khi phù hợp | Đồng bộ cập nhật một trạng thái cần chia sẻ |
| Cập nhật quan hệ nhiều bản ghi | Transaction/lock/điều kiện cập nhật phù hợp | Đảm bảo bất biến nghiệp vụ giữa nhiều thao tác |
| Cache mutable hoặc cấu hình động | Chủ sở hữu trạng thái rõ ràng, synchronization/atomic publication | Bất biến riêng của value không thay thế cơ chế phối hợp |

Không phải lúc nào tạo bản sao cũng là lựa chọn rẻ nhất. Đối với mảng dữ liệu rất lớn, thuật toán hiệu năng cao hoặc xử lý khối lượng lớn, có thể dùng mutable buffer có chủ sở hữu độc quyền trong một phạm vi nhỏ. Phần cần tránh là truyền tham chiếu mutable sang nhiều nơi mà không xác định rõ quyền sửa và đồng bộ.

## 11. Những lỗi cần nhận diện khi review code

**Lỗi 1 — Tin rằng `final` khiến danh sách bất biến.** `final List<Item> items = new ArrayList<>()` vẫn cho phép `items.add(...)`. Muốn bảo vệ dữ liệu, kiểm soát cả constructor, accessor và kiểu của từng phần tử.

**Lỗi 2 — Record giữ nguyên tham chiếu mutable của caller.**

```java
// Phản ví dụ: caller vẫn có thể sửa danh sách items.
record UnsafeOrder(String id, List<String> items) {}

List<String> source = new ArrayList<>(List.of("BOOK"));
UnsafeOrder unsafe = new UnsafeOrder("A01", source);
source.add("PEN");
System.out.println(unsafe.items()); // [BOOK, PEN]
```

Đoạn trên minh họa lỗi record có **bất biến nông**. Phần constructor của `Order` trong chương trình chính dùng `List.copyOf(items)` để giải quyết trường hợp này.

**Lỗi 3 — Trả về `Collections.unmodifiableList` và cho rằng đã snapshot.** Wrapper vẫn phản ánh các sửa đổi vào danh sách gốc. Chọn `List.copyOf` nếu muốn một snapshot của cấu trúc danh sách.

**Lỗi 4 — Dùng `forEach` để tự tích lũy kết quả.** `list.parallelStream().forEach(x -> total[0] += x)` có data race. Thay bằng reduction/collector hoặc cơ chế cập nhật đồng bộ nếu yêu cầu thật sự là side effect.

**Lỗi 5 — Mặc định `collect` trả về dữ liệu bất biến.** `Collectors.toList()` không cam kết loại `List`, tính mutable, serializability hay thread safety của kết quả. Java 17 `Stream.toList()` cam kết danh sách không sửa được; với map dùng `Collectors.toUnmodifiableMap(...)` khi phù hợp và xử lý khóa trùng/`null` rõ ràng.

**Lỗi 6 — Mutate phần tử trong một danh sách không sửa được.** `List.copyOf` chỉ bảo vệ cấu trúc của danh sách; nó không biến `Date`, array, `StringBuilder` hay object do người dùng tự viết thành bất biến.

**Lỗi 7 — Gọi mã có side effect trong `map` rồi dựa vào số lần thực thi.** Stream có lazy evaluation và có thể có short-circuit; hãy viết các phép biến đổi không có side effect, và không phụ thuộc vào số lần lambda được gọi ngoài những điều được API bảo đảm.

**Lỗi 8 — Nhầm “không có shared state” với “không có state”.** Mutable state cục bộ, không thoát khỏi phương thức và không bị chia sẻ, có thể là chi tiết triển khai an toàn và đơn giản. Độ rõ ràng của quyền sở hữu dữ liệu mới là điểm cốt lõi.

## 12. Bài tập tự kiểm tra

1. Đổi `editable.clear()` thành `editable.add(new Item("BAG", 1, money("200000")))` sau khi tạo `original`. Giải thích vì sao `original.total()` vẫn là `270000`.
2. Tạo một record chứa `int[] scores`. Chỉ ra hai đường có thể sửa dữ liệu sau khi record đã tạo: thông qua mảng nguồn và qua accessor. Sửa bằng clone/sao chép khi nhận dữ liệu và khi trả dữ liệu, hoặc thiết kế API dùng một collection an toàn và phần tử bất biến.
3. Từ `orders`, xây danh sách mã đơn có tổng lớn hơn `100000` chỉ bằng `filter`, `map`, `toList`, không viết vào danh sách bên ngoài stream. Với dữ liệu của chương trình, kết quả phải chứa duy nhất `A01`.
4. Giải thích vì sao code `int[] acc = {0}; parallelStream().forEach(n -> acc[0] += n);` không đáng tin cậy dù `acc` là effectively final.
5. Tự viết phiên bản `calculateRevenue(List<Order>)` dùng `reduce`. Kiểm tra với danh sách rỗng phải ra `BigDecimal.ZERO` và với dữ liệu trên phải ra `320000`.
6. Đánh giá một tình huống cần dùng `AtomicInteger`, một tình huống cần database transaction và một tình huống chỉ cần `List.copyOf`. Nêu rõ **trạng thái nào được chia sẻ**, **ai có quyền sửa** và **cơ chế đảm bảo**.

**Checklist khi áp dụng:** dữ liệu đầu vào có thể bị sửa từ bên ngoài không; object có chứa thành phần mutable không; lambda có đọc/ghi state dùng chung không; phép tổng hợp có tính kết hợp và identity phù hợp không; object có được công bố an toàn khi dùng giữa thread không; thao tác nhiều bước có cần khóa hoặc transaction không. Nếu trả lời được các câu hỏi đó, việc thiết kế pipeline theo hướng bất biến sẽ có nền tảng vững chắc và có thể kiểm chứng.
