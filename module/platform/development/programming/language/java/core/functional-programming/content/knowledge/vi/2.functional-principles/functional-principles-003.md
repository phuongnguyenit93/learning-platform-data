# Tính minh bạch tham chiếu và khả năng thay biểu thức bằng giá trị

## Mục tiêu bài học

Hiểu **referential transparency** (tính minh bạch tham chiếu) ở mức biểu thức: khi nào có thể thay một biểu thức bằng kết quả của chính nó mà hành vi quan sát được của chương trình vẫn giữ nguyên. Từ đó phân biệt hàm thuần với hàm có tác dụng phụ, nhận diện những điểm phá vỡ tính thay thế trong Java, và thiết kế phần tính toán dễ kiểm thử, tái sử dụng, tối ưu hóa.

Đây là một nguyên lý cốt lõi của lập trình hàm, không phải một từ đồng nghĩa của “dùng lambda”, “dùng Stream” hay “tránh vòng lặp”.

## 1. Tính minh bạch tham chiếu là gì?

Một **biểu thức minh bạch tham chiếu** khi ta có thể thay sự xuất hiện của biểu thức ấy bằng **giá trị mà nó tính ra**, trong một ngữ cảnh phù hợp, mà không thay đổi hành vi quan sát được của chương trình. Quan hệ này thường được diễn đạt bằng khả năng *substitution* (thay thế) hay *equational reasoning* (suy luận bằng các phép biến đổi tương đương).

Ví dụ toán học:

```text
f(x) = x * x + 1

f(4) + f(4)
= 17 + 17
= 34
```

Nếu `f` chỉ dùng đối số `x` và không thay đổi gì bên ngoài, mỗi lần tính `f(4)` đều cho `17`. Ta có thể nghĩ về biểu thức `f(4)` thông qua giá trị `17` mà không phải quan tâm nó được gọi ở thời điểm nào hay đã được gọi bao nhiêu lần.

Trong Java, biểu thức tương đương:

```java
static int squarePlusOne(int x) {
    return x * x + 1;
}

// Với x = 4 và không có tràn số:
int result = squarePlusOne(4) + squarePlusOne(4); // 34
```

Đoạn này minh họa phép thay thế; **không phải chương trình độc lập**. Chúng ta sẽ có một chương trình Java hoàn chỉnh ở phần sau.

Điểm quan trọng: tính minh bạch tham chiếu được xét theo **hành vi quan sát được**, không chỉ dựa vào việc hai biểu thức in ra cùng một chuỗi hoặc hai đối tượng có `equals` bằng nhau. Những điều có thể được quan sát gồm kết quả, ngoại lệ, thao tác I/O, thay đổi trạng thái, thứ tự thực thi, danh tính đối tượng trong ngữ cảnh dùng `==` và tương tác với luồng khác. Vì vậy, khả năng thay thế cần được phát biểu có điều kiện, đặc biệt trong Java là ngôn ngữ cho phép trạng thái và tác dụng phụ.

## 2. Vì sao hàm thuần giúp biểu thức thay thế được?

Một **hàm thuần** (*pure function*) có hai tính chất thực dụng:

1. **Kết quả chỉ do đầu vào quyết định:** với cùng đầu vào và cùng ngữ nghĩa kiểu dữ liệu, phép tính trả cùng kết quả, không bí mật phụ thuộc đồng hồ, biến toàn cục, trạng thái cơ sở dữ liệu hoặc bộ đếm thay đổi.
2. **Không có tác dụng phụ quan sát được:** không sửa đối tượng có thể quan sát bên ngoài, không ghi tệp, gửi yêu cầu mạng, cập nhật cơ sở dữ liệu, in log hoặc thay đổi một bộ đếm chia sẻ.

Các phương thức thuần trên dữ liệu bất biến tạo nền tảng cho phép thay thế biểu thức. Chẳng hạn, `Math.multiplyExact(7, 6)` cho `42` trong mọi lần tính với hai đối số này và không làm thay đổi trạng thái bên ngoài. Phương thức này có thể ném `ArithmeticException` nếu tràn số; đó là lý do khi phát biểu “thay bằng giá trị”, cần xét các lời gọi **trả về bình thường** và giữ nguyên ngữ nghĩa lỗi ở những trường hợp khác.

Đối chiếu với phương thức sau:

```java
static int nextId(java.util.concurrent.atomic.AtomicInteger counter) {
    return counter.incrementAndGet();
}
```

Nếu bộ đếm ban đầu bằng `0`, hai lần gọi liên tiếp cho `1` rồi `2`. Dù đối số tham chiếu vẫn là cùng một `counter`, kết quả phụ thuộc trạng thái hiện tại và lời gọi còn làm biến đổi bộ đếm. Thay cả hai lần gọi bằng `1` sẽ thay đổi giá trị lẫn tác dụng phụ: **không có phép thay thế tương đương như với hàm thuần**.

| Biểu thức hoặc hành động | Có thể thay bằng một giá trị cố định trong cùng điều kiện? | Giải thích |
| --- | --- | --- |
| `5 * 8` | Có | Không đọc hay sửa trạng thái ngoài |
| `Math.max(3, 9)` | Có | Kết quả ổn định với đối số đã cho |
| `price * quantity`, với hai biến primitive không đổi | Có | Phụ thuộc đầu vào ổn định; lưu ý quy tắc tràn số |
| `counter.incrementAndGet()` | Không | Đọc và sửa trạng thái bộ đếm |
| `Instant.now()` | Không | Đọc thời điểm của môi trường; lần sau có thể khác |
| `System.out.println("Hello")` | Không | Tạo tác dụng phụ I/O, dù trả về `void` |
| `order.total()` với `order` bất biến và phép tính thuần | Có, trong điều kiện đã nêu | Giá trị không đổi; nếu đối tượng hoặc các phần tử bị sửa thì kết luận có thể không còn đúng |

**Tính tất định (determinism) chưa đủ để là thuần.** Một phương thức luôn trả `100` nhưng đồng thời ghi log hoặc tăng bộ đếm vẫn có tác dụng phụ. Ngược lại, phương thức nhận dữ liệu bằng đối số rõ ràng nhưng lén sửa dữ liệu đó cũng không thể coi là thuần chỉ vì nhiều lần kiểm thử tình cờ cho cùng kết quả.

## 3. Thay biểu thức bằng giá trị: cách suy luận đúng

Xét một đơn hàng cố định có tổng tiền `230_000` và hàm giảm giá thuần `discountPercent`:

```text
discountPercent(total(items), 10)
= discountPercent(230_000, 10)
= 207_000
```

Phép thay này hợp lệ **trong ngữ cảnh** `items` và từng phần tử được giữ bất biến trong khi tính, `total` không có tác dụng phụ, phép giảm giá sử dụng cùng quy tắc tính tiền. Nếu sau đó nội dung `items` thay đổi, không được lấy kết quả `230_000` ở thời điểm cũ để thay mọi lời gọi `total(items)` ở thời điểm mới.

Lợi ích là có thể suy luận từng đoạn: chứng minh `total(items) == 230_000`; chứng minh `discountPercent(230_000, 10) == 207_000`; rồi kết hợp hai kết quả. Mỗi bước có thể kiểm thử riêng.

Đối với phép tính có trạng thái, không thể áp dụng cùng lập luận:

```text
nextId(counter) + nextId(counter)
```

Khi `counter` khởi đầu bằng `0`, thứ tự đánh giá từ trái sang phải của Java tạo `1 + 2 = 3` và bộ đếm kết thúc ở `2`. Nếu thay cả hai lời gọi bằng một giá trị `1` thì phép cộng thành `2` và bộ đếm không tăng: cả kết quả lẫn trạng thái quan sát được đều khác.

**Lưu ý về phạm vi phép biến đổi:** Java đánh giá đối số theo quy tắc cụ thể, có ngoại lệ, danh tính đối tượng, short-circuit (`&&`, `||`) và các tác dụng phụ. Không được tự ý dời, bỏ hoặc thực thi thêm một biểu thức nếu điều đó thay đổi thời điểm ném lỗi, trạng thái hoặc hành vi quan sát được. Tính minh bạch tham chiếu là tiêu chuẩn để biện minh cho phép thay thế, không phải giấy phép tối ưu hóa tùy ý mọi lời gọi Java.

## 4. Chương trình Java 17 chạy được

Ví dụ dưới đây đặt dữ liệu đơn hàng trong một `record`, dùng danh sách phần tử bất biến và tính tổng qua một hàm thuần theo những điều kiện đã nêu. Nó đối chiếu với hàm cấp số thứ tự có trạng thái và thao tác đọc thời gian một cách tường minh.

Lưu vào tệp **`ReferentialTransparencyDemo.java`**:

```java
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class ReferentialTransparencyDemo {
    record Item(String name, int quantity, long unitPrice) {
        Item {
            Objects.requireNonNull(name, "name");
            if (name.isBlank() || quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("Invalid item");
            }
        }

        long subtotal() {
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    static long total(List<Item> items) {
        Objects.requireNonNull(items, "items");
        return items.stream()
                .mapToLong(Item::subtotal)
                .reduce(0L, Math::addExact);
    }

    static long discountPercent(long amount, int percent) {
        if (amount < 0 || percent < 0 || percent > 100) {
            throw new IllegalArgumentException("Invalid discount");
        }
        return Math.multiplyExact(amount, 100L - percent) / 100;
    }

    static int nextId(AtomicInteger counter) {
        return counter.incrementAndGet();
    }

    static boolean beforeDeadline(Instant observedAt, Instant deadline) {
        return observedAt.isBefore(deadline);
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("Sách", 2, 100_000),
                new Item("Bút", 3, 10_000)
        );

        long savedTotal = total(items);
        long direct = discountPercent(total(items), 10);
        long substituted = discountPercent(savedTotal, 10);

        System.out.println("Tổng: " + savedTotal);
        System.out.println("Thay thế tương đương: " + (direct == substituted));
        System.out.println("Giá sau giảm: " + direct);

        AtomicInteger counter = new AtomicInteger(0);
        int first = nextId(counter);
        int second = nextId(counter);
        System.out.println("Số vé: " + first + ", " + second);

        Instant observedAt = Instant.parse("2026-10-28T12:00:00Z");
        Instant deadline = Instant.parse("2026-11-01T00:00:00Z");
        System.out.println("Trước hạn: " + beforeDeadline(observedAt, deadline));
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn:

```bash
javac ReferentialTransparencyDemo.java
java ReferentialTransparencyDemo
```

Kết quả chuẩn:

```text
Tổng: 230000
Thay thế tương đương: true
Giá sau giảm: 207000
Số vé: 1, 2
Trước hạn: true
```

**Phân tích:**

- `Item` giữ bất biến về tên, số lượng và đơn giá ở constructor. `String` là immutable và hai thành phần còn lại là primitive; mọi `Item` trong ví dụ không thể bị sửa sau khi tạo. `List.of` là danh sách không thể thêm/xóa/sửa phần tử. Nhờ đó, đầu vào của `total(items)` ổn định.
- `subtotal` lấy toàn bộ đầu vào từ trạng thái bất biến của `Item` và không thay đổi bên ngoài. `total` chỉ đọc danh sách, chuyển các phần tử thành `long` rồi cộng; dùng `Math.addExact` và `Math.multiplyExact` để phát hiện tràn số. Trong ví dụ với giá không âm và không tràn, tổng ổn định là `230000`.
- `discountPercent` tính `230000 * 90 / 100 = 207000`. Việc thay `total(items)` bằng `savedTotal` hợp lệ tại đây vì dữ liệu không đổi và không có tác dụng phụ. Phép chia số nguyên làm tròn xuống; trong ứng dụng tài chính thực tế cần quy định đơn vị tiền và chính sách làm tròn phù hợp.
- `nextId` truy cập rồi sửa bộ đếm bên ngoài. Dù có cùng đối số tham chiếu, mỗi lần gọi nhận một trạng thái khác và gây tác dụng phụ. `AtomicInteger` bảo đảm phép tăng nguyên tử cho bộ đếm nhưng **không làm phương thức trở thành thuần**.
- `beforeDeadline` nhận thời điểm quan sát làm đối số, không tự gọi `Instant.now()`. Với hai `Instant` đã cho, kết quả `true` ổn định và có thể kiểm chứng ở bất cứ ngày chạy nào.

Trong mẫu này, `record` và `List.of` là công cụ giúp quản lý dữ liệu, nhưng **không tự động bảo đảm mọi hàm dùng chúng đều thuần**. Chẳng hạn, một phương thức vẫn có thể ghi log hoặc truy vấn mạng bên trong. Tính thuần phải xét toàn bộ hành vi.

## 5. Trạng thái ẩn: ba nguyên nhân phổ biến làm mất tính thay thế

### 5.1. Đọc trạng thái toàn cục hoặc môi trường

```java
// Minh họa, không phải chương trình Java độc lập.
static boolean isExpired(java.time.Instant deadline) {
    return java.time.Instant.now().isAfter(deadline);
}
```

Cùng một `deadline`, phương thức có thể trả `false` trước hạn và `true` sau hạn. Nếu cần kết quả thuần, truyền thời điểm đã quan sát vào:

```java
static boolean isExpired(
        java.time.Instant deadline,
        java.time.Instant observedAt) {
    return observedAt.isAfter(deadline);
}
```

Trong kiến trúc thực tế, phần điều phối (*imperative shell*) có thể gọi `clock.instant()` đúng thời điểm quyết định rồi truyền `Instant` sang phần tính (*functional core*). Chỉ truyền đối tượng `Clock` vào một hàm rồi để hàm gọi `clock.instant()` chưa đủ để bảo đảm tính thuần nếu `Clock` là đồng hồ tiến theo thời gian.

Tương tự, đọc biến cấu hình có thể thay đổi, bộ nhớ đệm mutable, `System.getenv` hoặc cơ sở dữ liệu ngay trong hàm tính có thể làm cho kết quả phụ thuộc môi trường thay vì chỉ phụ thuộc tham số.

### 5.2. Gây tác dụng phụ dù kết quả trả về không đổi

```java
// Minh họa, không phải chương trình Java độc lập.
static int priceWithLog(int price) {
    System.out.println("Đang tính giá");
    return price;
}
```

Hai lần gọi vẫn trả cùng số nhưng in ra hai dòng. Thay các lời gọi bằng giá trị `price` sẽ xóa những dòng log đó, tức thay đổi hành vi quan sát được. Vì vậy, **kết quả như nhau không đồng nghĩa với minh bạch tham chiếu**.

Tác dụng phụ còn là sửa bộ sưu tập ngoài, cập nhật một biến `static`, tăng metric, gửi sự kiện, ghi database, thay trạng thái trong một đối tượng được truyền vào. Một thao tác có thể hữu ích và có chủ đích, nhưng nên để tại ranh giới rõ ràng nếu muốn giữ phần tính toán thuần.

### 5.3. Đầu vào là tham chiếu đến dữ liệu mutable

```java
// Minh họa, không phải chương trình Java độc lập.
static int sum(java.util.List<Integer> numbers) {
    return numbers.stream().mapToInt(Integer::intValue).sum();
}

java.util.List<Integer> numbers = new java.util.ArrayList<>();
numbers.add(2);
int first = sum(numbers); // 2
numbers.add(3);
int second = sum(numbers); // 5
```

Cùng một **tham chiếu** `numbers` nhưng nội dung danh sách đã khác. Không thể thay tất cả `sum(numbers)` bằng `2` cho suốt thời gian chạy. Trong một lần tính với snapshot ổn định và không có tác dụng phụ, phép tính vẫn có thể dễ suy luận; điều cần tránh là tuyên bố giá trị không phụ thuộc thời gian khi trạng thái có thể thay đổi.

`final` chỉ ngăn gán lại biến tham chiếu; nó không ngăn sửa đối tượng. `record` là shallow immutable theo các component, không tự đóng băng đối tượng mutable được chứa bên trong. `List.copyOf` tạo danh sách không thể thay đổi cấu trúc, nhưng phần tử kiểu mutable vẫn có thể tự thay đổi. Với bài toán cần thay thế an toàn, nên dùng value object bất biến, defensive copy đúng mức hoặc snapshot rõ ràng.

## 6. Bẫy riêng của Java: giá trị, danh tính và ngoại lệ

Trong toán học, hai giá trị bằng nhau có thể thường được thay thế cho nhau. Trong Java, **đối tượng có cả trạng thái và danh tính**, và danh tính có thể quan sát bằng `==`. Ví dụ:

```java
String a = new String("Java");
String b = new String("Java");

System.out.println(a.equals(b)); // true
System.out.println(a == b);      // false
```

Đây là đoạn minh họa (cần đặt trong phương thức để chạy). Hai chuỗi có cùng **nội dung** nhưng là hai đối tượng riêng biệt. Nếu ngữ cảnh chương trình dùng `==`, `System.identityHashCode`, khóa bằng identity hoặc khóa đồng bộ trên object, việc thay một phép tạo object bằng một object dùng chung có thể làm đổi kết quả. **Không được coi `equals` bằng nhau là bằng chứng đầy đủ về tính thay thế trong mọi ngữ cảnh Java**.

Một phương thức trả về danh sách mới mỗi lần gọi có thể cho các phần tử bằng nhau nhưng danh tính danh sách khác nhau. Nếu caller giữ lại rồi sửa danh sách, hoặc so sánh tham chiếu, sự khác biệt còn dễ quan sát hơn. Khi cần suy luận theo giá trị, dùng các kiểu bất biến, tránh để identity trở thành một phần không cần thiết của hợp đồng nghiệp vụ, và xác định rõ ngữ cảnh quan sát.

**Ngoại lệ cũng là hành vi.** Ví dụ `Math.divideExact` không tồn tại trong Java 17; ngay cả phép `a / b` đơn giản cũng ném `ArithmeticException` nếu `b == 0` đối với phép chia số nguyên. Một phép thay thế chỉ được làm sau khi biết kết quả là giá trị bình thường hoặc phải giữ nguyên cả khả năng ném lỗi, vị trí và ảnh hưởng của lỗi. Trong ví dụ chính, `Math.multiplyExact` cố ý ném lỗi khi tràn, thay vì âm thầm trả số sai.

**Đánh giá biểu thức còn có chi phí và thời điểm thực thi.** Chuyển một phép tính thuần ra khỏi vòng lặp có thể giữ giá trị nhưng đổi thời điểm tính, chi phí bộ nhớ và thời điểm xuất hiện lỗi. Khi hiệu năng và exception timing là một phần yêu cầu, phải kiểm chứng thêm, không suy diễn rằng “thuần” đồng nghĩa mọi phép biến đổi đều không có rủi ro.

## 7. Lambda và Stream có giúp giữ tính minh bạch tham chiếu không?

Có, **khi những hàm được truyền vào thực sự thuần và dữ liệu nguồn ổn định**. Các API `Function<T,R>`, `Predicate<T>` và `Stream` cho phép biểu đạt phép biến đổi như:

```java
// Minh họa với List<Integer> cố định:
List<Integer> doubled = List.of(1, 2, 3).stream()
        .map(x -> x * 2)
        .toList(); // [2, 4, 6]
```

Lambda `x -> x * 2` không sửa trạng thái và cho cùng giá trị với cùng `x`. Pipeline trở nên dễ đọc và dễ kiểm thử. Tuy nhiên **lambda chỉ là cú pháp**, không bảo đảm thuần:

```java
// Minh họa với counter là AtomicInteger đã được tạo.
List<Integer> ids = List.of("A", "B", "C").stream()
        .map(name -> counter.incrementAndGet())
        .toList();
```

Ở đây, `map` đang sửa bộ đếm; các kết quả phụ thuộc trạng thái trước đó. Với parallel stream, shared mutable state còn gây khó khăn trong suy luận thứ tự và tính an toàn. Tương tự, `peek(System.out::println)` tạo I/O và có thể có hành vi khó dự đoán khi pipeline được tối ưu, dừng sớm hoặc không chạy terminal operation. Không dùng `peek` làm cơ chế chính cho tác vụ nghiệp vụ có side effect.

Khi pipeline được xây từ phép biến đổi thuần, một số tối ưu như chia công việc hoặc cache kết quả trở nên dễ xét hơn. Nhưng các phép tổng hợp vẫn phải có điều kiện riêng: một reducer dùng song song cần tính kết hợp và identity phù hợp; cộng `double` theo các thứ tự khác nhau có thể khác do sai số dấu chấm động, ngay cả khi từng phép cộng không ghi trạng thái. Với `long`, cần xét tràn số. Tính thuần là nền tảng suy luận, không tự nó bảo đảm mọi thứ tự thực thi đều trả kết quả bit-for-bit giống nhau.

## 8. Từ nguyên lý đến thiết kế ứng dụng

Có thể tổ chức luồng nghiệp vụ theo mô hình **functional core, imperative shell**:

```text
HTTP/CLI/Scheduler
       |
       v
Đọc dữ liệu, clock, cấu hình, database  <-- có I/O và trạng thái
       |
       v
Tạo snapshot đầu vào bất biến
       |
       v
Hàm tính toán thuần: input -> output
       |
       v
Ghi kết quả, phát sự kiện, gọi dịch vụ   <-- có I/O và trạng thái
```

Ví dụ dịch vụ đặt hàng:

1. **Shell** tải giá và tồn kho, ghi nhận một `Instant`, xác định chính sách giảm giá đang có hiệu lực.
2. **Core** nhận các giá trị rõ ràng, tính tiền, điều kiện hợp lệ và quyết định nghiệp vụ; trả về một object kết quả bất biến.
3. **Shell** gửi giao dịch đến cổng thanh toán rồi cập nhật database theo kết quả. Các thao tác này được kiểm soát lỗi, retry và giao dịch riêng.

Ưu điểm không nằm ở việc loại bỏ mọi side effect: ứng dụng thực tế bắt buộc có I/O. Mục tiêu là **giữ phần tính toán có thể suy luận theo giá trị**, còn những thao tác với môi trường nằm ở chỗ dễ theo dõi và kiểm thử tích hợp.

Khi một quy tắc cần dữ liệu thay đổi theo thời gian, hãy đưa dữ liệu ấy thành **tham số**. Khi cần kết quả mới, ưu tiên trả object mới thay vì sửa object đầu vào. Khi cần tác dụng phụ, làm rõ nó qua tên phương thức và API thay vì giấu trong mapper hoặc predicate.

## 9. Lợi ích và giới hạn thực tế

**Dễ kiểm thử.** Hàm `discountPercent(230_000, 10)` có thể kiểm tra độc lập với thời gian, mạng hay database. Test case chủ yếu gồm đầu vào, đầu ra và điều kiện biên, không phải dựng trạng thái hệ thống phức tạp.

**Dễ suy luận và refactor.** Một biểu thức thuần có thể được đặt tên, trích thành hàm, dùng lại hoặc được tính trước trong những ngữ cảnh bảo toàn ngữ nghĩa. Đây là nền tảng cho các phép suy luận tương đương ở cấp chương trình.

**Có cơ hội memoization/caching.** Khi đầu ra chỉ phụ thuộc dữ liệu bất biến được dùng làm khóa, có thể lưu kết quả để tránh tính lại. Tuy nhiên cache có state, chi phí bộ nhớ và chính sách vòng đời riêng; cần khóa đại diện đầy đủ cho đầu vào, xử lý đồng thời và xác định chính xác ngữ nghĩa lỗi. Không tự động cache hàm đọc đồng hồ hoặc dữ liệu mutable vì kết quả cũ có thể không còn hợp lệ.

**Thuận lợi cho concurrency.** Hàm không chia sẻ mutable state giảm nguy cơ race condition khi nhiều luồng tính đồng thời. Điều đó không có nghĩa mọi dữ liệu nguồn, accumulator hoặc API được sử dụng đã thread-safe; cần xem xét toàn bộ đường xử lý.

**Không bắt buộc áp dụng mọi nơi.** Những dịch vụ ghi database, bộ đếm, logger, UI event handler và các thao tác mạng không phải hàm thuần. Với nghiệp vụ có trạng thái, một object quản lý state rõ ràng có thể đúng đắn và dễ hiểu hơn việc cố nhét mọi thứ vào Stream hay lambda.

## 10. Lỗi nhận thức thường gặp

- **“Cùng đầu ra nghĩa là minh bạch tham chiếu.”** Sai nếu lời gọi còn log, thay trạng thái hoặc ném lỗi khác nhau.
- **“Thêm `final` làm hàm thuần.”** Sai: `final` của biến tham chiếu không ngăn sửa nội dung đối tượng.
- **“`record` và `List.copyOf` luôn tạo dữ liệu immutable sâu.”** Sai với phần tử hoặc component tham chiếu đến đối tượng mutable.
- **“Lambda và Stream mặc định là functional/pure.”** Sai: body lambda vẫn có thể truy cập biến toàn cục và thực hiện I/O.
- **“Hai object `equals` bằng nhau luôn có thể thay cho nhau.”** Chưa đủ trong ngữ cảnh quan sát identity, aliasing hoặc trạng thái.
- **“Có thể thay mọi lần gọi bằng một lần tính trước.”** Sai khi đầu vào thay đổi, có side effect hoặc cần giữ nguyên thời điểm ném lỗi.
- **“Hàm thuần bảo đảm parallel stream luôn ra cùng kết quả.”** Chưa đủ nếu phép gộp không kết hợp chính xác hoặc nguồn bị thay đổi đồng thời.

## 11. Bài tự kiểm tra

1. Với `int square(int x) { return x * x; }` và `x = 5`, có thể thay `square(5)` bằng `25` khi nào? Hãy nêu giả định về kiểu số và hành vi quan sát.
2. Vì sao `int f() { log(); return 5; }` không minh bạch tham chiếu, dù gọi nhiều lần đều trả `5`?
3. `long price(List<Item> items)` chỉ đọc từng phần tử. Liệu có thể luôn cache kết quả theo **tham chiếu danh sách**? Nếu danh sách hoặc phần tử mutable, điều gì xảy ra?
4. So sánh `isExpired(deadline)` dùng `Instant.now()` với `isExpired(deadline, observedAt)` nhận thời gian làm đối số. Phương án nào dễ kiểm thử bằng hai thời điểm cố định?
5. Trong Java, vì sao dùng `==` trên hai object làm suy luận “cùng nội dung, thay thế như nhau” trở nên nguy hiểm?

**Gợi ý đáp án:** (1) Với `5` cố định, phép nhân trong phạm vi `int` không tràn, không side effect; kết quả `25`. (2) Bỏ lời gọi làm mất lần log. (3) Không, nếu dữ liệu thay đổi theo thời gian thì cùng key tham chiếu có thể đại diện dữ liệu khác. (4) Bản nhận `observedAt` thuần hơn và không phụ thuộc giờ hệ thống. (5) `==` so danh tính tham chiếu, khác với `equals` so nội dung/hợp đồng giá trị.

**Kết luận:** Tính minh bạch tham chiếu cho phép thay biểu thức bằng giá trị của nó mà vẫn giữ hành vi quan sát được. Trong Java, cách thực hành hiệu quả là thiết kế các phép tính thuần trên dữ liệu bất biến, truyền rõ dữ liệu môi trường vào hàm và giữ side effect tại ranh giới tích hợp. Nhờ đó, chương trình dễ suy luận, kiểm thử và thay đổi hơn mà vẫn sử dụng được đầy đủ các khả năng hướng đối tượng của Java.
