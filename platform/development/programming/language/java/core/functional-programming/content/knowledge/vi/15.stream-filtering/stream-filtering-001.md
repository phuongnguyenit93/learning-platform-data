# filter() và thiết kế Predicate không thay đổi nguồn trong Java

## 1. Mục tiêu bài học

Khi làm việc với danh sách sản phẩm, đơn hàng hay tài khoản, ta thường cần **chọn các phần tử phù hợp với một điều kiện** mà không muốn thay đổi dữ liệu gốc. Trong Java, **Stream.filter(Predicate)** là một cách biểu đạt ý định ấy rõ ràng: mô tả quy tắc kiểm tra từng phần tử và tạo một Stream chỉ chứa các phần tử thỏa điều kiện.

Bài này tập trung vào hai kỹ năng gắn với nhau:

1. **Dùng filter() để chọn phần tử**, hiểu nó là thao tác trung gian lazy và chỉ được đánh giá khi có terminal operation.
2. **Thiết kế Predicate<T> không can thiệp vào nguồn (non-interfering), không có trạng thái thay đổi bất ngờ (stateless)**, giúp pipeline dễ kiểm thử, dễ bảo trì và an toàn hơn khi thay đổi chiến lược thực thi.

Sau khi học, bạn có thể viết Predicate rõ nghĩa, ghép điều kiện bằng and/or/negate, tách chọn lọc khỏi biến đổi, bảo toàn thứ tự khi cần, phân biệt không sửa **cấu trúc collection nguồn** với **không sửa phần tử mutable**, và tránh các lỗi với null, side effect, parallel stream, stateful predicate và short-circuit.

## 2. filter() làm việc gì?

Chữ ký quan trọng của **Stream<T>**:

~~~java
Stream<T> filter(Predicate<? super T> predicate)
~~~

Nó tạo một Stream chứa các phần tử từ Stream nguồn mà **predicate.test(element)** trả **true**. Các phần tử bị kiểm tra false không đi tiếp trong pipeline. **Kiểu T của phần tử không đổi** vì filter chỉ lựa chọn, không biến đổi kiểu.

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);

List<Integer> even = numbers.stream()
        .filter(n -> n % 2 == 0)
        .toList();

System.out.println(even);   // [2, 4, 6]
System.out.println(numbers); // [1, 2, 3, 4, 5, 6]
~~~

Ở ví dụ tuần tự trên, danh sách **numbers** vẫn nguyên vẹn; **even** là danh sách kết quả của terminal **toList()**. Java 16+ định nghĩa **Stream.toList()** trả danh sách **unmodifiable**: không thể thêm, xóa hoặc thay phần tử bằng các thao tác mutation thông thường.

Điểm cần nói chính xác: **filter không sửa collection nguồn** khi Predicate không làm việc đó. Nhưng nếu Predicate cố tình sửa một object được truyền qua, bản thân filter **không ngăn** side effect. Vì vậy, thiết kế Predicate là phần quan trọng của bài học.

### 2.1. Điều kiện true/false

~~~java
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> evenNumber = n -> n % 2 == 0;

System.out.println(positive.test(5));  // true
System.out.println(evenNumber.test(5)); // false
~~~

**Predicate<T>** là functional interface trong package **java.util.function**, có phương thức trừu tượng duy nhất:

~~~java
boolean test(T t);
~~~

Hãy đọc Predicate như một **câu hỏi** về dữ liệu:

- **isActive(user)** — tài khoản có đang hoạt động không?
- **hasStock(product)** — sản phẩm còn hàng không?
- **isEligible(order)** — đơn hàng có đủ điều kiện không?
- **isHighValue(order)** — giá trị đơn đạt ngưỡng không?

Một Predicate nên trả lời câu hỏi bằng boolean, thay vì bí mật cập nhật trạng thái ở nơi khác.

## 3. Ba bước: source, filter và terminal

~~~java
Stream<Integer> pending = List.of(10, 15, 20).stream()
        .filter(n -> n >= 15);

// Tại đây chỉ tạo pipeline; chưa yêu cầu lấy kết quả.
List<Integer> result = pending.toList();
~~~

**filter là intermediate operation lazy**. Việc viết **.filter(...)** không đồng nghĩa callback đã chạy ngay. Terminal như **toList()**, **collect(...)**, **forEach(...)**, **findFirst()**, **count()** hoặc **anyMatch(...)** mới yêu cầu thực thi đủ để có kết quả.

Hình dung:

~~~text
Nguồn List<Order>
      |
      v
stream()
      |
      v
filter(isEligible)  --- chỉ mô tả việc chọn phần tử
      |
      v
map(toView)         --- chỉ mô tả cách biến đổi
      |
      v
toList()            --- yêu cầu đánh giá pipeline
      |
      v
List<OrderView>
~~~

Với nguồn có encounter order như List, **filter giữ thứ tự tương đối của các phần tử còn lại**. Nếu phần tử A đứng trước B ở nguồn và cả hai đều được chọn, A vẫn đứng trước B trong một ordered pipeline.

### 3.1. Lazy và fusion

Trong pipeline:

~~~java
List<String> names = List.of(" A ", " ", " B ").stream()
        .map(String::strip)
        .filter(s -> !s.isEmpty())
        .map(String::toUpperCase)
        .toList();
~~~

Kết quả là **[A, B]**. Trên sequential pipeline với các thao tác stateless như map/filter, Stream thường kết hợp các bước trong **một quá trình duyệt**, không tạo sẵn nhiều List trung gian cho từng phép toán. Tuy nhiên, không nên phụ thuộc vào số lần callback chạy trong mọi pipeline: terminal có thể short-circuit, các thao tác stateful có thể thay đổi chiến lược và JDK có quyền tối ưu trong phạm vi hợp đồng.

**Lazy không có nghĩa bất đồng bộ.** Một Stream tuần tự vẫn chạy tại thời điểm terminal được gọi; nó không tự tạo thread nền.

## 4. Non-interfering: không sửa nguồn đang duyệt

**Non-interference** nghĩa là các behavioral parameter của pipeline không can thiệp vào nguồn dữ liệu đang được duyệt, ngoại trừ những trường hợp nguồn được thiết kế đặc biệt cho concurrent modification theo hợp đồng của nó.

Ví dụ **không nên làm**:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

List<Integer> result = numbers.stream()
        .filter(n -> {
            numbers.remove(n); // Sửa nguồn trong lúc duyệt.
            return n % 2 == 0;
        })
        .toList();
~~~

Đây là **phản ví dụ**, không phải code cần chạy. Với ArrayList, việc sửa cấu trúc trong lúc duyệt có thể dẫn đến **ConcurrentModificationException**, kết quả sai hoặc hành vi không mong muốn tùy cách thực thi. Không nên viết test mong một exception cố định để biện minh cho mô hình này.

Cách đúng khi muốn lọc:

~~~java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));

List<Integer> selected = source.stream()
        .filter(n -> n % 2 == 0)
        .toList();

// source vẫn có [1, 2, 3, 4].
// selected là [2, 4].
~~~

Nếu nghiệp vụ thực sự yêu cầu **xóa phần tử khỏi collection gốc**, hãy dùng API mutation rõ ràng như **Collection.removeIf(Predicate)** tại thời điểm phù hợp, **không nhét mutation đó vào Predicate của Stream.filter()**.

### 4.1. filter và removeIf khác nhau

| Tiêu chí | **stream().filter(...).toList()** | **collection.removeIf(...)** |
| --- | --- | --- |
| Mục đích | Tạo kết quả đã lọc | Thay đổi collection gốc bằng cách xóa phần tử |
| Giá trị trả về | Danh sách kết quả của Stream.toList | boolean cho biết collection đã thay đổi hay chưa |
| Predicate true | **Giữ** phần tử | **Xóa** phần tử |
| Nguồn được thay đổi? | Không, nếu callback không can thiệp | Có thể bị thay đổi |
| Thích hợp | Chọn dữ liệu, xử lý immutable-style | Xóa phần tử có chủ đích trên collection mutable |

Ví dụ:

~~~java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4));
values.removeIf(n -> n % 2 == 0);
System.out.println(values); // [1, 3]
~~~

**removeIf** loại các phần tử được Predicate đánh giá true. Vì thế điều kiện trong removeIf có ý nghĩa ngược về **giữ/xóa** so với filter. Trong API nghiệp vụ, hãy đặt tên rõ như **shouldKeep** và **shouldRemove** để tránh đảo nghĩa.

## 5. Stateless: Predicate không dựa trên trạng thái thay đổi theo lần gọi

Một Predicate lý tưởng cho Stream thường là **stateless**: kết quả xét một phần tử không phụ thuộc vào biến mutable bị thay đổi bởi quá trình đánh giá những phần tử trước đó.

Ví dụ **tốt**:

~~~java
Predicate<Integer> atLeastTen = n -> n >= 10;
~~~

Với cùng giá trị **n**, quy tắc trên luôn đưa ra cùng kết quả trong điều kiện bình thường; không cần biết bao nhiêu phần tử đã đi qua.

Ví dụ **có vấn đề**:

~~~java
AtomicInteger seen = new AtomicInteger();

Predicate<Integer> everySecondCall =
        n -> seen.incrementAndGet() % 2 == 0;
~~~

Trong ví dụ thứ hai, kết quả phụ thuộc **thứ tự và số lần gọi**, không chỉ phụ thuộc n. Khi đổi nguồn, terminal, short-circuit hoặc sang parallel stream, kết quả được chọn có thể thay đổi. AtomicInteger giúp thao tác tăng bộ đếm nguyên tử nhưng **không biến một quy tắc phụ thuộc thứ tự thành stateless**.

Nếu cần **lấy hai phần tử đầu**, dùng **limit(2)** trên nguồn có thứ tự thích hợp. Nếu cần chọn phần tử có **chỉ số chẵn**, hãy mô hình hóa chỉ số rõ ràng (ví dụ dùng IntStream.range và dữ liệu indexed), thay vì đếm số lần Predicate được gọi.

### 5.1. Capture cấu hình cố định là hợp lý

~~~java
int minimumScore = 80;
Predicate<Student> passes =
        s -> s.score() >= minimumScore;
~~~

Đây là đoạn minh họa với lớp/record **Student** có phương thức **score()**. **minimumScore** là biến cục bộ **effectively final**, nên có thể được lambda capture. Việc dùng một giá trị ngưỡng cố định không khiến Predicate trở thành stateful.

Nếu ngưỡng nằm trong object cấu hình mutable được thay đổi đồng thời, logic có thể cho kết quả không nhất quán giữa các phần tử. Hãy dùng snapshot cấu hình bất biến hoặc chính sách đồng bộ phù hợp khi cần.

### 5.2. Stateless không tự đồng nghĩa hàm thuần

Một Predicate có thể chỉ đọc một clock, database hoặc trạng thái bên ngoài mà không tự ghi gì. Dù không trực tiếp mutate, kết quả của nó vẫn có thể thay đổi giữa các lời gọi và tạo vấn đề về tính tái lập. Khi muốn lọc dữ liệu theo **thời điểm**, có thể truyền một thời điểm tham chiếu cố định do tầng điều phối cung cấp.

Ví dụ:

~~~java
Instant referenceTime = Instant.parse("2026-01-01T00:00:00Z");
Predicate<Event> activeAtReference =
        event -> !event.expireAt().isBefore(referenceTime);
~~~

Đây là **mảnh ghép minh họa** cần import Instant và có kiểu Event phù hợp. Predicate này dựa vào **referenceTime** cố định, thay vì gọi **Instant.now()** mỗi lần xem một Event, nên các phần tử được xét theo cùng mốc thời gian.

## 6. Thiết kế Predicate như một quy tắc nghiệp vụ có tên

Giả sử có danh sách Order. Thay vì nhét một điều kiện rất dài vào filter:

~~~java
orders.stream().filter(o ->
        o != null && o.quantity() > 0
        && o.unitPriceVnd() >= 0 && o.paid()
        && (o.vip() || o.quantity() >= 5)
);
~~~

Ta có thể tách thành các quy tắc nhỏ, có tên:

~~~java
Predicate<Order> notNull = Objects::nonNull;
Predicate<Order> positiveQuantity = o -> o.quantity() > 0;
Predicate<Order> nonNegativePrice = o -> o.unitPriceVnd() >= 0;
Predicate<Order> paid = Order::paid;

Predicate<Order> valid = notNull
        .and(positiveQuantity)
        .and(nonNegativePrice)
        .and(paid);
~~~

Các đoạn là **mảnh ghép** cần khai báo record Order và import Predicate, Objects; chương trình độc lập ở phần 12 sẽ hoàn thiện tình huống.

Tác dụng:

- **Tên thể hiện ý định**: không cần đọc một biểu thức lớn để đoán mục đích.
- **Dễ unit test từng quy tắc** và test trường hợp biên.
- **Có thể tái sử dụng** ở API khác.
- **Dễ lắp ghép** bằng and/or/negate theo chính sách cụ thể.
- **Không chứa mutation** hay side effect bất ngờ nếu mỗi rule chỉ đọc dữ liệu.

**Không nhất thiết chia quá nhỏ:** biểu thức đơn giản `o -> o.paid()` có thể viết thành method reference **Order::paid**; nếu một tên rule rõ hơn và được tái sử dụng thì tách ra mới có lợi.

### 6.1. Null safety và thứ tự điều kiện

`notNull.and(positiveQuantity)` an toàn với phần tử null vì **Predicate.and** có short-circuit: nếu `notNull.test(null)` false, phần tiếp theo không chạy.

Nhưng:

~~~java
Predicate<Order> unsafe = positiveQuantity.and(notNull);
~~~

sẽ gọi `positiveQuantity.test(null)` trước, dẫn đến **NullPointerException** khi truy cập **quantity()**. Đặt kiểm tra **null** trước các dereference là một phần của hợp đồng.

Với `Stream.of(...)`, không phải mọi nguồn cho phép phần tử null; ví dụ `List.of(null)` ném NPE ngay khi tạo danh sách. Vì vậy hãy chọn nguồn phù hợp nếu minh họa lọc null.

## 7. Ghép Predicate: and, or, negate và not

Các phương thức:

| Toán tử | Ý nghĩa | Đặc tính quan trọng |
| --- | --- | --- |
| **p.and(q)** | Cả p và q cùng true | Nếu p false thì không gọi q |
| **p.or(q)** | Chỉ cần một trong p/q true | Nếu p true thì không gọi q |
| **p.negate()** | Đảo boolean của p | Kết quả trả true nếu p false |
| **Predicate.not(p)** | Phủ định p (Java 11+) | Thường hữu ích với method reference |

Ví dụ:

~~~java
Predicate<String> notBlank =
        Predicate.not(String::isBlank);

List<String> names = List.of("An", " ", "Chi")
        .stream()
        .filter(notBlank)
        .toList();

System.out.println(names); // [An, Chi]
~~~

**Short-circuit không nên dùng để giấu side effect.** Nếu q có nhiệm vụ ghi log bắt buộc hoặc cập nhật dữ liệu, `p.and(q)` có thể không gọi q và làm mất hiệu ứng. Predicate nên dùng để **quyết định**, không dùng để điều phối transaction.

### 7.1. Một quy tắc có thể khác với cách viết tương đương về mặt boolean

Nếu cả p và q **thuần và không phụ thuộc trạng thái**, biểu thức **p.and(q)** và **q.and(p)** có cùng truth value. Nhưng nếu một trong hai có thể ném exception, null-dereference hay có side effect, đổi thứ tự có thể thay đổi hành vi. Vì vậy, giữ rõ thứ tự các điều kiện bảo vệ.

## 8. filter trước map hay map trước filter?

Hãy xác định **Predicate áp dụng cho kiểu dữ liệu nào** và **điều kiện thuộc trạng thái nào**.

### 8.1. Lọc Order rồi map sang DTO

~~~java
List<OrderView> views = orders.stream()
        .filter(isEligible)
        .map(toView)
        .toList();
~~~

Tại đây, **isEligible** nhận Order, còn **toView** trả OrderView. Nếu mục tiêu là loại Order không hợp lệ **trước khi tính DTO**, cách viết này rõ ràng; các Order bị loại không đi qua mapper.

### 8.2. Biến đổi rồi mới lọc kết quả biến đổi

~~~java
List<OrderView> expensiveViews = orders.stream()
        .map(toView)
        .filter(view -> view.totalVnd() >= 100_000)
        .toList();
~~~

Nếu điều kiện cần **totalVnd được tính bởi toView**, ta phải map trước rồi filter. Đổi vị trí không phải lúc nào cũng hợp lệ: đôi khi chức năng của Predicate chỉ tồn tại **sau biến đổi**.

Khi cả hai cách có cùng ngữ nghĩa và mapper tốn tài nguyên, lọc sớm **có thể** giảm số phép chuyển đổi. Nhưng tối ưu phải dựa trên tính tương đương thực sự, dữ liệu biên và kết quả kiểm thử, không chỉ suy đoán.

### 8.3. filter và distinct

~~~java
List<String> unique = List.of("A", "B", "A", "C")
        .stream()
        .filter(s -> !s.equals("B"))
        .distinct()
        .toList();
~~~

Kết quả **[A, C]**. **filter** kiểm tra Predicate; **distinct** là một thao tác trung gian **stateful** loại trùng dựa trên equals/hashCode. Với ordered stream, distinct giữ encounter order trong số các phần tử không trùng. Nếu đối tượng mutable được dùng làm khóa hash rồi thay đổi bất ngờ, cả hoạt động distinct và các cấu trúc dựa trên hash có thể gây khó hiểu.

## 9. filter với limit, findFirst và anyMatch

### 9.1. limit thay đổi số lượng đầu vào cần duyệt

~~~java
List<Integer> firstTwoEven = List.of(1, 2, 3, 4, 5, 6)
        .stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();
~~~

Kết quả **[2, 4]**. Với ordered sequential pipeline đơn giản, sau khi đã có hai số chẵn, phần tử phía sau có thể không cần được xét.

Ngược lại:

~~~java
List<Integer> evenAmongFirstTwo = List.of(1, 2, 3, 4, 5, 6)
        .stream()
        .limit(2)
        .filter(n -> n % 2 == 0)
        .toList();
~~~

Kết quả **[2]**, vì chỉ hai phần tử 1 và 2 được đưa qua filter. **Đổi thứ tự filter và limit có thể đổi ý nghĩa**.

### 9.2. findFirst

~~~java
Optional<Integer> firstEven = List.of(1, 3, 4, 6)
        .stream()
        .filter(n -> n % 2 == 0)
        .findFirst();
~~~

`firstEven` chứa 4. **findFirst** là terminal operation có thể dừng sớm và trả Optional.empty nếu không có phần tử nào được chọn. Nó tôn trọng encounter order nếu stream có thứ tự.

### 9.3. anyMatch đôi khi phù hợp hơn filter + find

Khi chỉ cần trả lời **“có phần tử nào đạt điều kiện không?”**:

~~~java
boolean anyEven = List.of(1, 3, 4, 6)
        .stream()
        .anyMatch(n -> n % 2 == 0); // true
~~~

**anyMatch(predicate)** thể hiện ý định trực tiếp hơn so với `filter(predicate).findAny().isPresent()`. Cả hai có thể dừng sớm, nhưng không nên lấy số lần callback được gọi làm hợp đồng nghiệp vụ.

### 9.4. filter không tự bắt ngoại lệ

Nếu Predicate ném exception, terminal operation có thể thất bại. **filter** không âm thầm “bỏ qua phần tử lỗi” trừ khi Predicate chủ động bắt lỗi và trả false. Cần tránh bắt mọi lỗi mạng/database rồi coi đó là dữ liệu không hợp lệ nếu nghiệp vụ phải phân biệt các trường hợp ấy.

## 10. Chương trình Java 17 hoàn chỉnh: lọc đơn hàng, không thay đổi nguồn

Ví dụ dưới đây có năm đơn hàng. Chúng ta sẽ:

- Định nghĩa các **Predicate có tên** cho dữ liệu hợp lệ và điều kiện thanh toán.
- Chọn đơn hợp lệ nhưng không sửa danh sách nguồn.
- Chọn thêm đơn VIP bằng cách ghép Predicate.
- Biến đổi kết quả sang nhãn hiển thị sau khi lọc.
- Minh họa tính lazy bằng một bộ đếm phục vụ quan sát **trong test/demo**, không coi bộ đếm là nghiệp vụ.

Tạo tệp **FilterPredicateDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;
import java.util.stream.Stream;

public class FilterPredicateDemo {
    record Order(
            String id,
            int quantity,
            long unitPriceVnd,
            boolean paid,
            boolean vip) { }

    static List<String> ids(List<Order> orders) {
        return orders.stream().map(Order::id).toList();
    }

    public static void main(String[] args) {
        List<Order> source = List.of(
                new Order("A", 2, 15_000, true, true),
                new Order("B", 1, 10_000, true, false),
                new Order("C", 0, 7_000, true, true),
                new Order("D", 3, 4_000, false, true),
                new Order("E", 1, 9_000, true, true)
        );

        Predicate<Order> positiveQuantity =
                o -> o != null && o.quantity() > 0;
        Predicate<Order> nonNegativePrice =
                o -> o.unitPriceVnd() >= 0;
        Predicate<Order> paid = Order::paid;
        Predicate<Order> vip = Order::vip;

        Predicate<Order> eligible = positiveQuantity
                .and(nonNegativePrice)
                .and(paid);

        List<Order> accepted = source.stream()
                .filter(eligible)
                .toList();

        List<Order> vipAccepted = source.stream()
                .filter(eligible.and(vip))
                .toList();

        List<String> vipTotals = vipAccepted.stream()
                .map(o -> o.id() + ":" + Math.multiplyExact(
                        (long) o.quantity(), o.unitPriceVnd()))
                .toList();

        System.out.println("source IDs: " + ids(source));
        System.out.println("eligible IDs: " + ids(accepted));
        System.out.println("VIP IDs: " + ids(vipAccepted));
        System.out.println("VIP totals: " + vipTotals);
        System.out.println("source size: " + source.size());

        AtomicInteger examined = new AtomicInteger();
        Stream<Order> pending = source.stream()
                .filter(o -> {
                    examined.incrementAndGet();
                    return eligible.test(o);
                });

        System.out.println("before terminal: " + examined.get());
        long count = pending.count();
        System.out.println("eligible count: " + count);
        System.out.println("after terminal: " + examined.get());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac FilterPredicateDemo.java
java FilterPredicateDemo
~~~

**Đầu ra chính xác cho chương trình tuần tự này:**

~~~text
source IDs: [A, B, C, D, E]
eligible IDs: [A, B, E]
VIP IDs: [A, E]
VIP totals: [A:30000, E:9000]
source size: 5
before terminal: 0
eligible count: 3
after terminal: 5
~~~

### 10.1. Giải thích kết quả

1. **source** là List.of gồm năm record Order; nó giữ nguyên thứ tự A, B, C, D, E.
2. **positiveQuantity** trả false cho C vì quantity=0. Các đơn khác có quantity dương.
3. **paid** trả false cho D, nên D bị loại. Kết quả của **eligible** là A, B, E; thứ tự gặp ban đầu được giữ.
4. **eligible.and(vip)** loại thêm B vì không phải VIP, nên còn A và E.
5. **map** chạy sau filter, tính nhãn `id:totalVnd`. A có 2 × 15.000 = 30.000; E có 1 × 9.000 = 9.000. **Math.multiplyExact** phát hiện overflow long nếu có.
6. **source size: 5** cho thấy chọn lọc không xóa bản ghi khỏi nguồn.
7. Pipeline **pending** được xây dựng với filter nhưng chưa được tiêu thụ, nên **before terminal: 0**.
8. Terminal **count()** trên pipeline với filter phải xác định có bao nhiêu phần tử đạt điều kiện, nên với List tuần tự này nó gọi Predicate của filter cho năm Order: **eligible count: 3**, **after terminal: 5**.

**Lưu ý quan trọng:** việc tăng **examined** bên trong Predicate chỉ dùng để minh họa lazy evaluation. Nó là một side effect; không nên dùng bộ đếm này làm phần không thể thiếu của nghiệp vụ, bởi kết quả về số lần callback có thể thay đổi khi terminal, nguồn và chiến lược thực thi thay đổi. Với pipeline `count()` có `filter` trong ví dụ, đếm bằng cách duyệt là hợp lý; nhưng `count()` trên nguồn có kích thước biết trước **và không có filter** có thể tối ưu mà không chạy `map/peek` phía trước.

### 10.2. Vì sao records hỗ trợ ví dụ?

**Order** là record chứa String và primitive, nên trong ví dụ nó có trạng thái dữ liệu ổn định. Predicate chỉ đọc accessor và trả boolean, không thay đổi record. Điều này giúp ví dụ dễ lý luận và kiểm thử.

Tuy nhiên, **record không tự đảm bảo bất biến sâu**: nếu record chứa một List mutable, code vẫn có thể sửa nội dung List qua tham chiếu. Khi cần snapshot dữ liệu có ý nghĩa nghiệp vụ, hãy xác định rõ quyền sở hữu và mức độ sao chép.

## 11. Không đổi cấu trúc nguồn không có nghĩa không đổi object

Nếu danh sách chứa các object mutable:

~~~java
class Product {
    private int stock;

    Product(int stock) {
        this.stock = stock;
    }

    int stock() {
        return stock;
    }

    void decrease() {
        stock--;
    }
}
~~~

Một Predicate được viết như sau là **có vấn đề**:

~~~java
Predicate<Product> hasStock = product -> {
    product.decrease();           // Side effect.
    return product.stock() > 0;
};
~~~

Đây là đoạn code minh họa với Product đã khai báo ở trên; không nên dùng cách này để lọc.

Mặc dù filter không thêm/xóa phần tử vào List nguồn, **mỗi Product vẫn là chính đối tượng được tham chiếu từ nguồn**. Gọi decrease làm Product thay đổi. Do đó không thể kết luận “danh sách gốc không thay đổi” theo nghĩa **mọi trạng thái của phần tử đều giữ nguyên**.

Thiết kế nên là:

~~~java
Predicate<Product> hasStock =
        product -> product != null && product.stock() > 0;
~~~

Và nếu cần cập nhật stock, hãy làm ở **bước nghiệp vụ riêng** có hợp đồng về xác thực, khóa, transaction và xử lý lỗi. Tương tự, sau khi `toList()`, danh sách kết quả là unmodifiable nhưng các phần tử mutable trong đó vẫn có thể bị sửa thông qua phương thức của object.

## 12. Source snapshot và thay đổi đồng thời

Một pipeline Stream thông thường **không đồng nghĩa snapshot nguồn tại thời điểm gọi stream()**. Nếu một danh sách mutable bị thread khác sửa trong lúc terminal đang duyệt, có thể gặp exception, dữ liệu không nhất quán hoặc hành vi không mong muốn tùy nguồn. Stream API yêu cầu behavioral parameter non-interfering trừ các trường hợp nguồn được thiết kế cho concurrent access.

Nếu bạn cần lọc một ảnh chụp danh sách ở một thời điểm xác định:

~~~java
List<Order> snapshot = List.copyOf(orders);
List<Order> selected = snapshot.stream()
        .filter(eligible)
        .toList();
~~~

Đây là mảnh ghép có biến **orders** và **eligible** trong ngữ cảnh. **List.copyOf** tạo một list không hỗ trợ mutation và không chấp nhận phần tử null; nó **không sao chép sâu** Order mutable. Ngoài ra, nếu chính danh sách nguồn đang bị sửa đồng thời trong lúc tạo bản sao, hành vi vẫn cần được quản lý bằng cơ chế đồng bộ/ownership phù hợp.

Mục tiêu chính không phải luôn tạo bản sao — đôi khi danh sách nguồn vốn bất biến hoặc chỉ thuộc một thread — mà là **biết rõ ai có quyền sửa nguồn và khi nào**.

## 13. filter trên parallel stream: Predicate phải phù hợp

~~~java
List<Integer> result = numbers.parallelStream()
        .filter(n -> n > 0)
        .toList();
~~~

Một Predicate chỉ đọc n và không giữ trạng thái mutable có thể được thư viện áp dụng đồng thời cho nhiều phần tử. Khi có nguồn có encounter order (ví dụ List), kết quả từ `toList()` vẫn phù hợp với thứ tự được bảo đảm của stream; nhưng **thứ tự/thời điểm gọi Predicate trên các thread không cố định**.

Ví dụ nguy hiểm:

~~~java
int[] counter = {0};

Predicate<Integer> alternate = n ->
        ++counter[0] % 2 == 0;
~~~

Lambda capture **tham chiếu mảng** effectively final nhưng **sửa nội dung mảng**, nên vẫn có side effect. Với parallel stream, đây còn là shared mutable state không đồng bộ, gây race condition. Dù dùng AtomicInteger để sửa race, kết quả lọc vẫn phụ thuộc thứ tự callback, không phải một quy tắc ổn định trên dữ liệu.

Những lựa chọn tốt hơn:

- Chuyển predicate thành phép kiểm tra dựa trên dữ liệu của phần tử, không dựa trên thứ tự gọi.
- Khi nghiệp vụ phụ thuộc vào vị trí, dùng chỉ số tường minh trên nguồn có thứ tự, chẳng hạn `IntStream.range(0, list.size())`.
- Nếu thực sự phải cập nhật state, tách cập nhật khỏi filter, dùng collector hoặc API nghiệp vụ có kiểm soát.
- Chỉ dùng parallel sau khi đo hiệu năng, xem xét chi phí chia/gom và tính an toàn của toàn pipeline.

Không phải cứ `parallel()` là nhanh hơn; với dữ liệu nhỏ hoặc công việc nhẹ, overhead có thể lớn hơn lợi ích.

## 14. Null, exception và quy tắc lọc dữ liệu lỗi

### 14.1. Null trong nguồn

Nếu nguồn có thể chứa null, có thể lọc trước:

~~~java
List<String> values = new ArrayList<>();
values.add("An");
values.add(null);
values.add("Chi");

List<String> safe = values.stream()
        .filter(Objects::nonNull)
        .filter(s -> !s.isBlank())
        .toList();
~~~

Đoạn này cần import List, ArrayList và Objects. Kết quả **[An, Chi]**; thứ tự điều kiện quan trọng vì `String::isBlank` sẽ ném NPE nếu gặp null trước khi lọc.

### 14.2. Phân biệt phần tử không đạt điều kiện với dữ liệu bị lỗi

Nếu rule kiểm tra điều kiện kinh doanh thông thường như “đơn đã thanh toán”, **false** nghĩa là đơn **không được chọn**. Nhưng nếu việc kiểm tra phải truy vấn database và gặp lỗi kết nối, trả false tùy tiện sẽ **che giấu sự cố thành không hợp lệ**.

Khi cần nguyên nhân, thay vì chỉ Predicate trả boolean có thể dùng một kiểu kết quả như `ValidationResult` hay `Decision` chứa thông tin. Nếu nghiệp vụ yêu cầu báo lỗi cho mọi đơn không hợp lệ, **filter rồi bỏ phần tử** có thể không phù hợp; hãy chia dữ liệu thành nhóm hợp lệ và nhóm lỗi hoặc tạo kết quả có trạng thái.

### 14.3. Checked exception

SAM của Predicate là `boolean test(T t)`, không khai báo checked exception. Lambda gọi một phương thức có checked exception phải tự xử lý hoặc dùng abstraction khác phù hợp. Không nên bắt `Exception` rộng rồi trả false cho mọi lỗi chỉ để làm cho `filter` tiếp tục.

## 15. Hiệu năng và trình tự tối ưu

### 15.1. Điều kiện rẻ trước điều kiện đắt

Trong `p.and(q)`, nếu p false thì q không chạy. Khi hai điều kiện **thuần, tương đương về logic và không phụ thuộc thứ tự**, đặt một điều kiện kiểm tra rẻ, có khả năng loại nhiều phần tử trước có thể giảm công việc:

~~~java
Predicate<Order> validQuantity = o -> o.quantity() > 0;
Predicate<Order> expensiveEligibility = o -> checkRule(o);

Predicate<Order> combined =
        validQuantity.and(expensiveEligibility);
~~~

Ở đây `checkRule` là phương thức minh họa chưa được định nghĩa. Chỉ nên đổi thứ tự khi không phá vỡ ý nghĩa, điều kiện null safety hoặc hợp đồng lỗi. Nếu expensiveEligibility có side effect cần thực thi bất kể điều kiện đầu, **đó không nên là Predicate dùng trong and**.

### 15.2. Lọc trước các bước biến đổi nặng khi đúng ngữ nghĩa

~~~java
List<View> views = orders.stream()
        .filter(isEligible)
        .map(thisService::expensiveView)
        .toList();
~~~

Đây là mảnh ghép trong lớp có biến và phương thức tương ứng. Nếu một Order bị loại, mapper không cần tạo View của nó. Nhưng nếu quyết định eligible dựa trên một giá trị được tính trong expensiveView, phải thiết kế lại dữ liệu hoặc thứ tự pipeline đúng với yêu cầu.

### 15.3. Chú ý số lần duyệt và kích thước nguồn

Nếu cần dùng nhiều kết quả lọc, có thể lưu kết quả một lần:

~~~java
List<Order> eligibleOrders = orders.stream()
        .filter(isEligible)
        .toList();

long count = eligibleOrders.size();
~~~

Không nên dựng lại pipeline nhiều lần khi việc lọc tốn kém, có phụ thuộc trạng thái hay dữ liệu có thể thay đổi giữa các lượt. Ngược lại, nếu dữ liệu rất lớn và chỉ cần một con số, **count()** có thể phù hợp hơn việc tạo List. Chọn theo nhu cầu, không mặc định materialize mọi stream.

## 16. Kiểm thử Predicate và filter

### 16.1. Unit test cho Predicate riêng

Với rule eligible ở ví dụ phần 10, hãy kiểm tra:

1. Quantity > 0, unitPrice >= 0 và paid = true → true.
2. Quantity = 0 → false.
3. Quantity âm → false.
4. UnitPrice âm → false.
5. Chưa thanh toán → false.
6. Null → false nếu rule có kiểm tra null đầu tiên.

Ví dụ:

~~~java
Order valid = new Order("X", 1, 1000, true, false);
Order invalid = new Order("Y", 0, 1000, true, true);

if (!eligible.test(valid)) {
    throw new AssertionError("Valid order rejected");
}
if (eligible.test(invalid)) {
    throw new AssertionError("Invalid order accepted");
}
~~~

Đây là đoạn code dùng các khai báo Order và eligible trong chương trình ở phần 10, không phải một file độc lập.

### 16.2. Kiểm thử không sửa nguồn

Trong code dùng record bất biến như ví dụ:

~~~java
List<Order> before = List.copyOf(source);

List<Order> selected = source.stream()
        .filter(eligible)
        .toList();

if (!source.equals(before)) {
    throw new AssertionError("Source changed");
}
~~~

Với **record chứa field bất biến về mặt giá trị** như ví dụ Order, phép kiểm tra này giúp chứng minh các phần tử nguồn được giữ nguyên trong test. Nếu dữ liệu chứa object mutable, chỉ so sánh hai List có cùng tham chiếu phần tử có thể **không phát hiện sự thay đổi nội dung**; khi đó cần so sánh snapshot giá trị của các thuộc tính liên quan.

### 16.3. Kiểm thử thứ tự và kết quả

Với source List có encounter order, kiểm tra đúng danh sách ID đã chọn, không chỉ số lượng. Kết quả đúng không có nghĩa một Predicate với side effect đã hoạt động an toàn trong mọi mode; cần kiểm tra cả tính không can thiệp, tính độc lập trạng thái và cách xử lý lỗi.

### 16.4. Kiểm thử short-circuit và terminal

Một test có thể chứng minh **filter lazy** bằng cách quan sát bộ đếm trước terminal. Tuy nhiên không nên ràng buộc số lần gọi callback của mọi terminal/parallel pipeline thành một invariant nếu hợp đồng không bảo đảm. Test production nên ưu tiên kết quả cuối và những hiệu ứng được định nghĩa rõ ràng ở ranh giới nghiệp vụ.

## 17. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Sửa collection trong `filter` | Can thiệp nguồn, kết quả không đáng tin | Predicate chỉ kiểm tra; dùng removeIf riêng nếu cần xóa |
| Sửa field object trong Predicate | Kết quả có thể làm biến đổi dữ liệu nguồn | Tách mutation khỏi lọc |
| Dùng counter mutable để quyết định giữ/xóa | Phụ thuộc số lần và thứ tự callback | Dùng rule stateless hoặc chỉ số tường minh |
| Dùng `filter` mà quên terminal | Pipeline chưa được tiêu thụ | Thêm terminal phù hợp |
| Gọi `filter(...).count()` rồi dùng lại stream | Stream chỉ được tiêu thụ một lần | Tạo stream mới |
| Cho rằng `toList()` tạo deep copy | Phần tử mutable vẫn được chia sẻ | Snapshot sâu khi nghiệp vụ yêu cầu |
| Cho rằng `toList()` trả ArrayList mutable | `Stream.toList()` không hỗ trợ mutation | Dùng collector/bản sao mutable nếu cần |
| Quên kiểm tra null trước dereference | NullPointerException | `Objects::nonNull` hoặc rule bảo vệ trước |
| Dùng `filter` để nuốt lỗi hệ thống | Lỗi database bị hiểu như “không đạt điều kiện” | Phân biệt false với exception/kết quả lỗi |
| Đảo `limit` và `filter` | Chọn tập phần tử khác | Giữ đúng thứ tự nghiệp vụ |
| Dùng `parallelStream` với mutable predicate | Race condition, không ổn định | Predicate stateless/non-interfering |
| Nhầm `removeIf` và `filter` | Thao tác giữ/xóa ngược nghĩa | Nhớ filter true = giữ, removeIf true = xóa |
| Đặt log bắt buộc vào `peek` | Callback có thể bị tối ưu bỏ qua | Đặt hiệu ứng trong bước được thiết kế để thực thi |

## 18. Bài tập tự luyện

### Bài 1 — Lọc sản phẩm còn hàng

Cho record:

~~~java
record Product(String name, int stock, boolean active) { }
~~~

Viết Predicate chọn sản phẩm **active** và **stock > 0**.

**Gợi ý đáp án:**

~~~java
Predicate<Product> hasStock = p -> p.stock() > 0;
Predicate<Product> active = Product::active;
Predicate<Product> available = hasStock.and(active);
~~~

Đây là mảnh ghép với record Product ở trên; trong hệ thống cho phép null, hãy thêm `p != null` trước khi dereference. Sản phẩm có stock=0 không được chọn; sản phẩm active=false cũng bị loại.

### Bài 2 — filter với limit

Cho dãy `[1, 2, 3, 4, 5, 6]`. So sánh:

~~~java
numbers.stream().filter(n -> n % 2 == 0).limit(2).toList();
numbers.stream().limit(2).filter(n -> n % 2 == 0).toList();
~~~

**Đáp án:** lần lượt **[2, 4]** và **[2]**. Cách đầu lấy **hai số chẵn đầu tiên**, cách sau chỉ kiểm tra **hai phần tử đầu**.

### Bài 3 — Sửa side effect trong filter

Mã cũ:

~~~java
List<Customer> selected = customers.stream()
        .filter(c -> {
            c.setChecked(true);
            return c.isActive();
        })
        .toList();
~~~

Hãy thiết kế lại để Predicate chỉ hỏi **c.isActive()**. Nếu nghiệp vụ cần đánh dấu đã xử lý, hãy tạo bước riêng có trách nhiệm ghi state và xử lý lỗi, thay vì coi lần gọi Predicate chắc chắn là một transaction.

**Gợi ý:**

~~~java
Predicate<Customer> active = Customer::isActive;
List<Customer> selected = customers.stream()
        .filter(active)
        .toList();
~~~

Đây là đoạn minh họa với lớp Customer có `isActive()`. Nếu vẫn cần đánh dấu, hãy làm ở một thao tác nghiệp vụ có hợp đồng rõ, không nhét vào Predicate.

### Bài 4 — Thiết kế API nhận Predicate

Viết một phương thức nhận danh sách T và điều kiện chọn, trả danh sách mới:

~~~java
static <T> List<T> select(
        List<T> source,
        Predicate<? super T> predicate) {
    return source.stream().filter(predicate).toList();
}
~~~

**Gợi ý cải tiến:** kiểm tra null cho source/predicate theo hợp đồng API. `? super T` cho phép truyền Predicate nhận một supertype của T. Kiểm thử với List<String> và Predicate<CharSequence>.

### Bài 5 — Lọc dữ liệu nhưng vẫn báo lỗi

Một batch gồm mười đơn, ba đơn sai dữ liệu. Nghiệp vụ yêu cầu **hiển thị danh sách lỗi cho cả ba đơn**, không chỉ loại bỏ chúng. Có nên dùng riêng `filter(valid)`?

**Đáp án:** không đủ. `filter` chỉ giữ/loại theo boolean và không lưu nguyên nhân. Hãy tạo `ValidationResult` hoặc quy trình chia dữ liệu thành hai nhóm hợp lệ/lỗi có chi tiết, rồi mới xử lý nhóm hợp lệ. Có thể vẫn dùng Predicate cho điều kiện đơn giản, nhưng cần một kiểu kết quả giàu thông tin hơn cho báo lỗi.

## 19. Ghi nhớ

**Stream.filter(Predicate)** mô tả một phép **chọn phần tử**, trả Stream cùng kiểu T và không cần sửa collection nguồn. Bản thân **filter là lazy**; terminal operation mới yêu cầu đánh giá pipeline. Với ordered source, filter giữ thứ tự tương đối của các phần tử được chọn.

Một Predicate tốt để dùng trong Stream nên:

- **Chỉ kiểm tra** và trả boolean; không sửa nguồn đang duyệt.
- **Không phụ thuộc trạng thái mutable giữa các lần gọi**; dùng cấu hình ổn định.
- **Có tên và hợp đồng rõ**, nhất là với các điều kiện nghiệp vụ có thể ghép bằng and/or/negate.
- **Xử lý null/exception có chủ đích**, không lẫn false với lỗi hạ tầng.
- **Không dựa vào số lần/thứ tự callback** khi có short-circuit, tối ưu hoặc parallel.
- **Phân biệt cấu trúc danh sách và trạng thái đối tượng**: kết quả toList không sửa cấu trúc nguồn nhưng không deep-copy phần tử mutable.

Khi cần lọc, hãy dùng **filter**. Khi cần xóa khỏi collection gốc, dùng một thao tác mutation có tên rõ như **removeIf**. Khi cần báo lỗi thay vì loại phần tử, chọn một mô hình kết quả có thông tin validation. Tách được ba trách nhiệm ấy sẽ giúp pipeline Java vừa dễ đọc vừa đáng tin cậy.
