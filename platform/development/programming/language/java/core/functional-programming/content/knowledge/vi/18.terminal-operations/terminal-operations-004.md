# anyMatch(), allMatch() và noneMatch() trong Java Stream

## 1. Ba thao tác kết thúc dùng để trả lời câu hỏi có/không

Trong `java.util.stream.Stream`, ba phương thức `anyMatch()`, `allMatch()` và `noneMatch()` kiểm tra một điều kiện (*predicate*) trên các phần tử của stream rồi trả kết quả kiểu nguyên thủy **`boolean`**. Chúng là **terminal operations**: việc gọi chúng kích hoạt quá trình tiêu thụ pipeline; kết quả không phải stream mới.

Ba câu hỏi:

- **`anyMatch(predicate)`**: **Có ít nhất một** phần tử thỏa điều kiện không?
- **`allMatch(predicate)`**: **Tất cả** phần tử có thỏa điều kiện không?
- **`noneMatch(predicate)`**: **Không có phần tử nào** thỏa điều kiện phải không?

Ví dụ với `List.of(2, 4, 7)`:

~~~java
List<Integer> values = List.of(2, 4, 7);

boolean hasOdd = values.stream().anyMatch(n -> n % 2 != 0);  // true
boolean allEven = values.stream().allMatch(n -> n % 2 == 0); // false
boolean noNegative = values.stream().noneMatch(n -> n < 0); // true
~~~

Các câu lệnh trên là **đoạn minh họa**, cần import `java.util.List` và đặt trong phương thức. Mỗi lời gọi `values.stream()` tạo **một stream mới**. Stream không thể dùng lại sau terminal operation.

Khác với `filter()`, ba phương thức trên **không thu thập hoặc giữ lại các phần tử**; chúng trả lời trực tiếp một câu hỏi dạng đúng/sai. `filter()` là intermediate operation và trả `Stream<T>`, còn `anyMatch`/`allMatch`/`noneMatch` trả `boolean`.

**Cách chọn nhanh:** Nếu bài toán được diễn đạt bằng “có ít nhất một”, dùng `anyMatch`; “mọi”, dùng `allMatch`; “không có bất kỳ”, dùng `noneMatch`.

## 2. Chữ ký API và vai trò của Predicate

Chữ ký trên `Stream<T>`:

~~~java
boolean anyMatch(Predicate<? super T> predicate);
boolean allMatch(Predicate<? super T> predicate);
boolean noneMatch(Predicate<? super T> predicate);
~~~

Đây là chữ ký rút gọn từ Java SE API, **không phải mã tự khai báo lại interface `Stream`**.

`Predicate<T>` là functional interface trong `java.util.function`, có phương thức trừu tượng duy nhất:

~~~java
boolean test(T value);
~~~

Vì vậy, biểu thức `n -> n > 10` được gán cho `Predicate<Integer>` khi nguồn là `Stream<Integer>`, hoặc cho `IntPredicate` nếu nguồn là `IntStream`. `Predicate` phải trả **`boolean`** hoặc kết quả tương thích với `boolean`; Java không coi một số khác 0 là `true`.

~~~java
Predicate<String> nonBlank = s -> !s.isBlank();

boolean hasNonBlank = List.of("", "  ", "Java")
        .stream()
        .anyMatch(nonBlank);             // true
~~~

Đoạn này cần import `java.util.List` và `java.util.function.Predicate`. `String.isBlank()` có từ Java 11; ví dụ phù hợp với Java 17+.

Các biến thể dành cho primitive stream nhận predicate chuyên biệt để không phải boxing từng phần tử:

| Nguồn stream | Kiểu callback | SAM |
|---|---|---|
| `Stream<T>` | `Predicate<? super T>` | `boolean test(T)` |
| `IntStream` | `IntPredicate` | `boolean test(int)` |
| `LongStream` | `LongPredicate` | `boolean test(long)` |
| `DoubleStream` | `DoublePredicate` | `boolean test(double)` |

Ví dụ `IntStream.rangeClosed(1, 5).allMatch(n -> n > 0)` trả `true`. Cả ba thao tác matching có mặt trên các primitive stream tương ứng.

## 3. Bảng chân trị quan trọng — kể cả stream rỗng

Giả sử predicate `P(x)` trả `true` cho phần tử đạt điều kiện.

| Tình trạng nguồn | `anyMatch(P)` | `allMatch(P)` | `noneMatch(P)` |
|---|---:|---:|---:|
| Có ít nhất một phần tử và **tất cả đều đạt** | `true` | `true` | `false` |
| Có phần tử đạt và phần tử không đạt | `true` | `false` | `false` |
| Có ít nhất một phần tử và **không phần tử nào đạt** | `false` | `false` | `true` |
| **Không có phần tử nào** (stream rỗng) | `false` | `true` | `true` |

Dòng cuối rất quan trọng:

~~~java
Stream.<Integer>empty().anyMatch(n -> n > 0)  // false
Stream.<Integer>empty().allMatch(n -> n > 0)  // true
Stream.<Integer>empty().noneMatch(n -> n > 0) // true
~~~

**Vì sao `allMatch` trên nguồn rỗng trả `true`?** Phát biểu “mọi phần tử đều thỏa” chỉ sai nếu tìm được **một phản ví dụ**. Trong nguồn rỗng không có phần tử nào vi phạm, nên theo logic toán học phát biểu đó đúng; hiện tượng này gọi là **đúng một cách rỗng** (*vacuous truth*). `noneMatch` cũng đúng vì không tìm thấy phần tử thỏa. Ngược lại, `anyMatch` cần **một chứng cứ tồn tại**, và nguồn rỗng không có chứng cứ nào.

Đừng kết luận `allMatch` trả `true` đồng nghĩa “dữ liệu có ít nhất một phần tử và tất cả đều đạt”. Nếu nghiệp vụ **bắt buộc có dữ liệu**, cần kiểm tra điều kiện không rỗng **riêng** hoặc cấu trúc kiểm tra khác.

### 3.1. Ví dụ nghiệp vụ: danh sách trống có được coi là hợp lệ?

Giả sử cần xác minh “tất cả mục trong đơn đều có số lượng dương”, nhưng yêu cầu nghiệp vụ còn nói “đơn phải có ít nhất một mục”. Chỉ viết:

~~~java
boolean valid = lines.stream().allMatch(line -> line.quantity() > 0);
~~~

là **chưa đủ** vì nếu `lines` trống, `valid` vẫn bằng `true`. Với `lines` là `List<Line>` đã có, cách kiểm tra phù hợp hơn:

~~~java
boolean valid = !lines.isEmpty()
        && lines.stream().allMatch(line -> line.quantity() > 0);
~~~

Phần `!lines.isEmpty()` xác nhận điều kiện tồn tại; phần `allMatch` xác nhận tính đúng của tất cả mục. Toán tử `&&` dừng sớm nên khi danh sách rỗng, không cần tạo và duyệt stream phía sau.

## 4. Cơ chế dừng sớm (short-circuit)

Cả ba matching method là **short-circuiting terminal operations**: chúng có thể kết luận trước khi duyệt toàn bộ phần tử, tùy những gì đã thấy.

- `anyMatch(P)` có thể trả **`true` ngay khi tìm thấy một phần tử thỏa**. Nếu không phần tử nào thỏa trong nguồn hữu hạn, nó phải xét đủ để kết luận `false`.
- `allMatch(P)` có thể trả **`false` ngay khi tìm thấy một phần tử không thỏa**. Nếu mọi phần tử trong nguồn hữu hạn thỏa, nó cần xét đủ để trả `true`.
- `noneMatch(P)` có thể trả **`false` ngay khi tìm thấy một phần tử thỏa**. Nếu không phần tử nào thỏa trong nguồn hữu hạn, nó cần xét đủ để trả `true`.

Sơ đồ khái niệm:

~~~text
anyMatch(P):    gặp P(x) == true  ──► kết luận true
allMatch(P):    gặp P(x) == false ──► kết luận false
noneMatch(P):   gặp P(x) == true  ──► kết luận false
~~~

Điều này **không có nghĩa Java luôn chỉ gọi predicate đúng N lần** trong mọi cấu hình: thứ tự đánh giá, trạng thái parallel, tối ưu hóa pipeline và các intermediate operation có thể ảnh hưởng số lời gọi thực tế. Đặc biệt, **parallel stream có thể kiểm tra nhiều phần tử đồng thời**, nên các tác dụng phụ không được dựa vào thứ tự hoặc số lần kiểm tra.

### 4.1. Chương trình hoàn chỉnh: đếm lần gọi theo trình tự xác định

Lưu file **`MatchShortCircuitDemo.java`**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;

public class MatchShortCircuitDemo {
    static Predicate<Integer> traced(
            String label,
            AtomicInteger checks,
            Predicate<Integer> rule) {
        return value -> {
            checks.incrementAndGet();
            System.out.println(label + ":" + value);
            return rule.test(value);
        };
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4);

        AtomicInteger anyChecks = new AtomicInteger();
        boolean any = numbers.stream().anyMatch(
                traced("any", anyChecks, n -> n == 2));

        AtomicInteger allChecks = new AtomicInteger();
        boolean all = numbers.stream().allMatch(
                traced("all", allChecks, n -> n < 3));

        AtomicInteger noneChecks = new AtomicInteger();
        boolean none = numbers.stream().noneMatch(
                traced("none", noneChecks, n -> n == 3));

        System.out.println("any=" + any + ",checks=" + anyChecks.get());
        System.out.println("all=" + all + ",checks=" + allChecks.get());
        System.out.println("none=" + none + ",checks=" + noneChecks.get());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac MatchShortCircuitDemo.java
java MatchShortCircuitDemo
~~~

Stdout của **pipeline tuần tự trên `List.of(1,2,3,4)`**:

~~~text
any:1
any:2
all:1
all:2
all:3
none:1
none:2
none:3
any=true,checks=2
all=false,checks=3
none=false,checks=3
~~~

Giải thích:

1. `anyMatch(n -> n == 2)` kiểm tra `1` rồi `2`; tìm thấy kết quả đúng và dừng nên không cần kiểm tra `3`, `4`.
2. `allMatch(n -> n < 3)` kiểm tra `1`, `2` rồi gặp `3` sai điều kiện, kết luận `false`.
3. `noneMatch(n -> n == 3)` gặp `3` thỏa predicate nên mệnh đề “không có ai thỏa” sai, kết luận `false`.
4. `AtomicInteger` chỉ nhằm minh họa số lời gọi; không cần dùng nó cho một predicate thuần khiết. Việc in bên trong predicate là **side effect có chủ ý để học cơ chế**, không phải mẫu phù hợp cho mọi pipeline.

Trong chương trình này ta dùng **ba stream riêng**, tạo bằng `numbers.stream()` cho mỗi phép matching. Một stream đã tiêu thụ bởi terminal operation không được dùng lại.

## 5. Chương trình Java 17: phân loại dữ liệu và nguồn rỗng

Lưu thành **`MatchBusinessDemo.java`**:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class MatchBusinessDemo {
    record Item(String name, int quantity, boolean approved) {}

    static boolean canSubmit(List<Item> items) {
        return !items.isEmpty()
                && items.stream().allMatch(item ->
                        item.quantity() > 0 && item.approved());
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("Pen", 2, true),
                new Item("Book", 1, true),
                new Item("Bag", 0, false)
        );

        boolean anyUnavailable = items.stream()
                .anyMatch(item -> item.quantity() == 0);
        boolean allApproved = items.stream()
                .allMatch(Item::approved);
        boolean noneNegative = items.stream()
                .noneMatch(item -> item.quantity() < 0);

        System.out.println("unavailable=" + anyUnavailable);
        System.out.println("allApproved=" + allApproved);
        System.out.println("noneNegative=" + noneNegative);
        System.out.println("canSubmit=" + canSubmit(items));

        List<Item> empty = List.of();
        System.out.println("emptyAny=" +
                empty.stream().anyMatch(Item::approved));
        System.out.println("emptyAll=" +
                empty.stream().allMatch(Item::approved));
        System.out.println("emptyNone=" +
                empty.stream().noneMatch(Item::approved));
        System.out.println("emptyCanSubmit=" + canSubmit(empty));

        boolean someMultipleOfFour = IntStream.rangeClosed(1, 10)
                .anyMatch(n -> n % 4 == 0);
        System.out.println("primitive=" + someMultipleOfFour);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MatchBusinessDemo.java
java MatchBusinessDemo
~~~

Stdout chính xác:

~~~text
unavailable=true
allApproved=false
noneNegative=true
canSubmit=false
emptyAny=false
emptyAll=true
emptyNone=true
emptyCanSubmit=false
primitive=true
~~~

**Đọc từng kiểm tra:**

- `anyUnavailable` là `true` vì `Bag` có `quantity() == 0`.
- `allApproved` là `false` vì `Bag.approved()` bằng `false`.
- `noneNegative` là `true` vì không có mục nào có số lượng âm. **Không có số âm** không đồng nghĩa **mọi số dương**: số `0` vẫn tồn tại.
- `canSubmit` dùng cả yêu cầu có ít nhất một mục và mọi mục có `quantity() > 0 && approved`; vì `Bag` không hợp lệ, kết quả `false`.
- Với danh sách rỗng, `anyMatch`/`allMatch`/`noneMatch` lần lượt là `false`, `true`, `true`; `canSubmit(empty)` vẫn `false` nhờ điều kiện `!items.isEmpty()`.
- `IntStream.rangeClosed(1,10)` tạo số nguyên primitive; predicate nhận `int` qua `IntPredicate`. Có các số chia hết cho 4 (chẳng hạn `4`), nên `primitive` là `true`.

Ứng dụng thực tế nên làm rõ nghiệp vụ: “không có mục bị lỗi” có thể đúng với tập rỗng, trong khi “một đơn hàng đủ điều kiện gửi” thường đòi hỏi ít nhất một mục. Sự khác biệt đến từ yêu cầu nghiệp vụ chứ không phải lỗi trong Java Stream.

## 6. Toán học đằng sau ba phương thức

Có thể hiểu ba phép matching qua các lượng từ trong logic:

~~~text
anyMatch(P)   ⇔  ∃x trong stream: P(x)
allMatch(P)   ⇔  ∀x trong stream: P(x)
noneMatch(P)  ⇔  không tồn tại x: P(x)
~~~

Trong đó `∃` là “tồn tại” và `∀` là “với mọi”.

Với cùng một dãy dữ liệu hữu hạn và predicate **thuần khiết, xác định** (không phụ thuộc state, thời gian hoặc side effect), ta có các quan hệ logic:

~~~java
noneMatch(P)  == !anyMatch(P)
allMatch(P)   == !anyMatch(P.negate())
noneMatch(P)  == allMatch(P.negate())
anyMatch(P)   == !noneMatch(P)
~~~

Đây là **quan hệ về kết quả boolean**, không phải đoạn code gọi các biến `P` trực tiếp. Khi áp dụng trong Java, cần tạo **stream mới** cho mỗi lần thực hiện terminal operation. Ví dụ:

~~~java
Predicate<Integer> positive = n -> n > 0;

boolean a = numbers.stream().noneMatch(positive);
boolean b = !numbers.stream().anyMatch(positive);

// Với cùng nội dung nguồn ổn định, a và b bằng nhau.
~~~

Đây là đoạn minh họa, cần `numbers` kiểu collection số và import `java.util.function.Predicate`.

**Không coi các công thức trên là tương đương về tác dụng phụ.** Hai cách kiểm tra có thể gọi predicate với số lần/thứ tự khác nhau khi dùng nguồn khác nhau, parallel stream, hay predicate đọc thời gian/biến thay đổi; thậm chí có thể ném exception ở thời điểm khác. Chúng tương đương về **ý nghĩa logic trên cùng tập phần tử và predicate ổn định**.

### 6.1. Phân biệt `allMatch(P)` và `noneMatch(P)`

Đừng mặc định `noneMatch(P)` là `allMatch(P)` chỉ vì cả hai có thể trả true. Với nguồn `[2,4]` và `P(n) = (n % 2 == 0)`:

- `allMatch(P)` trả `true` vì mọi phần tử đều chẵn.
- `noneMatch(P)` trả `false` vì thực tế **có** phần tử chẵn.
- `noneMatch(n -> n % 2 != 0)` trả `true` vì không có số lẻ.

Nếu yêu cầu “mọi bản ghi đều không bị khóa”, có thể viết `allMatch(record -> !record.locked())` hoặc `noneMatch(Record::locked)`. Lựa chọn có tên rõ ràng nhất cho nghiệp vụ và tránh lồng phủ định quá nhiều lần.

### 6.2. Không dùng `anyMatch(P)` làm phủ định của `allMatch(P)`

`!allMatch(P)` nghĩa là **tồn tại ít nhất một phần tử không thỏa `P`**, không phải “không tồn tại phần tử thỏa `P`”. Ví dụ dữ liệu `[1,2]` với `P(n) = (n > 1)`: `allMatch(P)` false và `anyMatch(P)` true cùng lúc. Phải dùng `anyMatch(P.negate())` mới phản ánh phủ định của `allMatch(P)`.

## 7. Khi nên dùng `match` thay cho `filter`, `count` hoặc `findAny`?

So sánh hai cách hỏi “có ít nhất một phần tử lớn hơn 100 không?”:

~~~java
boolean exists = values.stream().anyMatch(n -> n > 100);
~~~

và:

~~~java
boolean exists = values.stream()
        .filter(n -> n > 100)
        .count() > 0;
~~~

Hai dạng có thể cho cùng kết quả trên một collection hữu hạn với predicate thuần khiết, nhưng dạng **`anyMatch` thể hiện ý định tồn tại trực tiếp** và hỗ trợ dừng sớm khi đã thấy một phần tử thỏa. `filter(...).count()` được diễn đạt như một bài toán **đếm**, có thể phải xét đủ nguồn theo yêu cầu count, dù các tối ưu hóa được Stream API cho phép có thể thay đổi cách thực thi.

### 7.1. Khi `findAny` tốt hơn?

`findAny()` trả `Optional<T>`, hữu ích khi bạn cần **chính phần tử tìm được**, không chỉ một cờ boolean:

~~~java
Optional<Integer> found = values.stream()
        .filter(n -> n > 100)
        .findAny();
~~~

Nếu chỉ cần câu trả lời đúng/sai, `anyMatch` thường rõ hơn. Nếu cần lấy record đầu tiên theo encounter order, cân nhắc `findFirst()` trên nguồn có thứ tự; `anyMatch` không trả phần tử nào và không hứa cho biết phần tử đã khiến điều kiện đúng.

### 7.2. `noneMatch` thay cho `filter(...).findAny().isEmpty()`

~~~java
boolean noInvalid = records.stream()
        .noneMatch(record -> !record.isValid());
~~~

Đoạn này nêu rõ yêu cầu “không có bản ghi không hợp lệ”. Có thể dùng `allMatch(Record::isValid)` để giảm phủ định kép nếu phương thức `isValid()` có nghĩa tích cực và dễ đọc.

### 7.3. Khi thật sự cần count, cứ dùng `count`

Nếu nghiệp vụ cần “có bao nhiêu bản ghi bị lỗi”, `filter(...).count()` mới diễn đạt đúng bài toán. `anyMatch` chỉ có `boolean`, không thể thay một phép đếm cần biết số lượng.

## 8. Kết hợp với map, filter và flatMap

Các matching operations thường nằm cuối một pipeline.

### 8.1. Kiểm tra dữ liệu sau khi chuyển đổi

~~~java
boolean hasBlank = names.stream()
        .map(String::strip)
        .anyMatch(String::isEmpty);
~~~

Nếu `names` là `List<String>` không chứa null, pipeline kiểm tra có chuỗi nào chỉ gồm khoảng trắng hoặc rỗng sau `strip()` hay không. Với input có thể null, `String::strip` có thể ném `NullPointerException`; cần chính sách null riêng.

### 8.2. Kiểm tra phần tử ở các nhóm lồng nhau

~~~java
boolean hasNegative = groups.stream()
        .flatMap(List::stream)
        .anyMatch(n -> n < 0);
~~~

Với `groups` kiểu `List<List<Integer>>` không chứa group null, `flatMap(List::stream)` biến các nhóm thành một luồng phẳng, rồi `anyMatch` xác định có **bất kỳ số âm** nào trên toàn bộ nhóm.

Nếu mục tiêu là “mọi nhóm đều có ít nhất một số âm”, ý nghĩa khác:

~~~java
boolean everyGroupHasNegative = groups.stream()
        .allMatch(group -> group.stream().anyMatch(n -> n < 0));
~~~

Dòng thứ hai kiểm tra **theo từng nhóm**, nên với nhóm rỗng: `group.stream().anyMatch(...)` false. Với `groups` rỗng thì `allMatch` tầng ngoài true theo quy tắc vacuous truth; nếu đòi hỏi tồn tại nhóm, cần `!groups.isEmpty()`.

Chú ý sự khác nhau giữa hai lượng từ:

~~~text
Có ít nhất một số âm ở bất kỳ nhóm nào:
    ∃ group, ∃ n ∈ group: n < 0

Mọi nhóm đều có ít nhất một số âm:
    ∀ group, ∃ n ∈ group: n < 0
~~~

Đừng làm phẳng quá sớm nếu yêu cầu cần kiểm tra một điều kiện **riêng cho từng nhóm**. `flatMap` làm mất ranh giới nhóm nếu không giữ lại thông tin cha.

### 8.3. Kết hợp predicate có tên

Thay vì lambda điều kiện dài:

~~~java
Predicate<String> goodName = name ->
        name != null && !name.isBlank() && name.length() <= 30;

boolean allGood = names.stream().allMatch(goodName);
~~~

Ta có thể trích điều kiện thành method nghiệp vụ dễ kiểm thử, hoặc dùng `Predicate.and`/`or`/`negate` khi rõ hơn. `Predicate` có thể tái sử dụng trong nhiều matching operations; song cần tránh predicate có mutable state hoặc side effect làm kết quả phụ thuộc số lần gọi.

## 9. Stream vô hạn và short-circuit: có thể kết thúc, nhưng không được bảo đảm

Với một nguồn `Stream.generate` hay `Stream.iterate` vô hạn, matching **có khả năng** kết thúc nếu điều kiện quyết định xuất hiện:

~~~java
boolean exists = java.util.stream.Stream.iterate(1, n -> n + 1)
        .anyMatch(n -> n == 5);  // true, có thể dừng khi gặp 5.
~~~

Nhưng một câu hỏi không có bằng chứng kết luận sớm có thể **không bao giờ trả về**:

~~~java
// KHÔNG CHẠY: nguồn vô hạn luôn dương, không có phản ví dụ để allMatch trả false.
java.util.stream.Stream.generate(() -> 1)
        .allMatch(n -> n > 0);
~~~

Tương tự, `noneMatch(n -> n < 0)` trên nguồn vô hạn luôn trả số dương không thể kết luận true sau một số hữu hạn phần tử, vì vẫn có thể xuất hiện phần tử âm ở tương lai. `anyMatch(n -> n < 0)` cũng không thể kết luận false nếu chưa xác định được nguồn đã hết.

Trong thực tế, **đặt giới hạn hữu hạn** hoặc dùng nguồn có điểm dừng rõ:

~~~java
boolean allPositive = java.util.stream.IntStream.rangeClosed(1, 10)
        .allMatch(n -> n > 0);
~~~

**Cảnh báo về số học:** `Stream.iterate(1, n -> n + 1)` dùng boxed `Integer` có thể overflow nếu chạy quá xa, nhưng ví dụ tìm `5` dừng sớm. Không dùng các nguồn vô hạn để minh họa tính đúng trên tập dữ liệu lớn nếu không kiểm soát điểm dừng.

## 10. Parallel stream và yêu cầu predicate không có tác dụng phụ

Các matching operations đều hỗ trợ parallel stream, nhưng **không cam kết duyệt theo thứ tự hoặc gọi predicate đúng một lần cho từng phần tử trong mọi tình huống**. Khi một worker tìm thấy điều kiện quyết định, những worker khác có thể đã bắt đầu xử lý các phần tử khác.

Ví dụ:

~~~java
boolean anyError = records.parallelStream()
        .anyMatch(Record::hasError);
~~~

Đoạn trên minh họa với `records` là collection record có phương thức `hasError()`. Kết quả boolean là mục tiêu chính. Nếu `hasError` thuần khiết, thread-safe và không phụ thuộc thứ tự, mã dễ suy luận hơn.

**Không nên** đặt logic ghi database, gửi email, phát sự kiện hoặc tăng bộ đếm nghiệp vụ trong predicate rồi trông chờ tất cả phần tử được duyệt:

~~~java
// Ví dụ KHÔNG KHUYẾN NGHỊ:
boolean found = records.parallelStream()
        .anyMatch(record -> {
            audit(record);   // side effect không được hứa chạy cho mọi record.
            return record.hasError();
        });
~~~

Vì `anyMatch` có thể dừng sớm, một số bản ghi không được audit. Nếu predicate là stateful không an toàn luồng, chạy song song có thể còn gây race condition. Hãy tách bước audit bắt buộc khỏi phép hỏi tồn tại hoặc dùng API điều khiển nghiệp vụ khác.

Với stream tuần tự, việc chèn `peek` để đếm số lần kiểm tra cũng chỉ nên dành cho debug, không nên biến nó thành hợp đồng nghiệp vụ.

## 11. Xử lý null, ngoại lệ và dữ liệu sai

### 11.1. Phần tử null

`List.of(...)` không cho phép phần tử null, nhưng một số collection khác có thể chứa null. Nếu predicate gọi method trên phần tử null:

~~~java
boolean hasLong = nullableNames.stream()
        .anyMatch(name -> name.length() > 10);
~~~

có thể ném `NullPointerException`. Nếu muốn bỏ qua null:

~~~java
boolean hasLong = nullableNames.stream()
        .anyMatch(name -> name != null && name.length() > 10);
~~~

Nếu muốn coi null là không hợp lệ:

~~~java
boolean allValid = nullableNames.stream()
        .allMatch(name -> name != null && !name.isBlank());
~~~

Các đoạn là ví dụ minh họa với `nullableNames` là collection `String` có thể chứa null. Điều kiện `&&` short-circuit nên không gọi `length()`/`isBlank()` khi `name == null`.

### 11.2. Predicate null

Truyền `null` làm đối số predicate bị API từ chối với `NullPointerException`. Truyền lambda tạo kết quả `Boolean` bằng null rồi mong Java unboxing thành `boolean` cũng có thể gây lỗi runtime nếu thực sự thực hiện phép unboxing đó; nên viết predicate có kết quả boolean rõ ràng.

### 11.3. Checked exception

`Predicate.test(T)` không khai báo checked exception. Nếu kiểm tra một phần tử đòi hỏi thao tác I/O có thể ném `IOException`, lambda không thể để nó thoát ra như checked exception mà không xử lý. Giải pháp tùy nghiệp vụ gồm xử lý tại vị trí phù hợp, bọc thành unchecked exception có kiểm soát, hoặc dùng API kiểm tra riêng có hợp đồng lỗi rõ.

### 11.4. Exception không phải kết quả false

Nếu predicate ném exception, `anyMatch` không tự đổi exception thành `false`, `allMatch` không tự đổi thành `false`, và `noneMatch` không tự đổi thành `true`. Exception sẽ được truyền theo cơ chế xử lý lỗi của pipeline/Java; không được suy luận rằng các phương thức là “safe check” bất kể logic bên trong.

### 11.5. Kết quả có thể đổi nếu dữ liệu nguồn bị thay đổi

Các behavioral parameters của Stream nên **non-interfering** và thường nên stateless. Nếu predicate vừa duyệt vừa sửa nguồn collection, có thể vi phạm hợp đồng Stream, dẫn đến ngoại lệ hoặc kết quả khó đoán. Nếu nguồn dữ liệu bị thay đổi đồng thời không có đồng bộ phù hợp, một phép matching có thể không còn đại diện cho snapshot nhất quán.

## 12. Những lỗi phổ biến khi chọn matching operation

| Sai lầm | Vì sao sai/nguy hiểm | Cách sửa |
|---|---|---|
| Nghĩ `allMatch` trên stream rỗng trả false | “Mọi phần tử đều đạt” đúng một cách rỗng | Nếu cần ít nhất một phần tử, kiểm tra không rỗng riêng |
| Nghĩ `noneMatch(P) == allMatch(P)` | Một bên “không ai đạt”, bên kia “ai cũng đạt” | Dùng `allMatch(P.negate())` khi cùng predicate ổn định |
| Dùng `!anyMatch(P)` để kiểm tra “mọi phần tử đều đạt” | `!anyMatch(P)` nghĩa là không ai đạt | Dùng `allMatch(P)` |
| Lấy `anyMatch` khi muốn chính bản ghi tìm được | Trả boolean, không trả phần tử | Dùng `filter(...).findAny()`/`findFirst()` |
| Dùng `filter(...).count() > 0` chỉ để hỏi tồn tại | Diễn đạt ý định kém trực tiếp | Ưu tiên `anyMatch` |
| Mong predicate luôn chạy với tất cả phần tử | Matching có thể dừng sớm | Không đặt side effect bắt buộc trong predicate |
| Mong kết quả `allMatch` chứng minh collection có phần tử | Luồng rỗng vẫn trả true | Thêm kiểm tra không rỗng nếu cần |
| Dùng lại cùng stream cho ba phép matching | Stream đã bị terminal operation tiêu thụ | Tạo stream mới cho mỗi phép |
| Dùng matching trên nguồn vô hạn không có bằng chứng kết thúc | Có thể chạy mãi | Giới hạn nguồn/đổi điều kiện kết thúc |
| Dùng predicate không an toàn trong parallel stream | Race và thứ tự callback không xác định | Dùng predicate stateless, thread-safe |
| Dựa vào `null` là false trong điều kiện | Có thể ném NPE | Xác định chính sách null rõ ràng |
| Dùng `allMatch` để tính tổng hay đếm | Chỉ cho boolean | Dùng `sum`, `count`, `reduce` hoặc collector |

Đọc chính xác tên phương thức và yêu cầu nghiệp vụ thường giải quyết phần lớn lỗi: ba phương thức trả lời **ba loại mệnh đề khác nhau**, không phải chỉ là cách viết tương đương của một vòng lặp.

## 13. Bài tập áp dụng có đáp án

### 13.1. Kiểm tra mã sản phẩm

Giả sử `codes` là `List<String>` không null:

~~~java
boolean anyBlank = codes.stream().anyMatch(String::isBlank);
boolean allNonBlank = codes.stream().allMatch(code -> !code.isBlank());
boolean noneBlank = codes.stream().noneMatch(String::isBlank);
~~~

Với cùng dữ liệu ổn định, `allNonBlank` và `noneBlank` có cùng kết quả. Nếu `codes` rỗng, **cả hai đều `true`**; nếu điều kiện nghiệp vụ yêu cầu danh sách có mã, thêm `!codes.isEmpty()`.

### 13.2. Kiểm tra thứ tự điều kiện

Với `numbers = List.of(1, 2, 3)`:

~~~java
numbers.stream().anyMatch(n -> n > 2)    // true
numbers.stream().allMatch(n -> n > 2)    // false
numbers.stream().noneMatch(n -> n > 2)   // false
~~~

Thay predicate bằng `n -> n > 10` thì:

~~~java
anyMatch(n -> n > 10)  // false
allMatch(n -> n > 10)  // false
noneMatch(n -> n > 10) // true
~~~

Các dòng trong phần này là **bảng minh họa kết quả của phép gọi trên nguồn mới mỗi lần**, không phải một file Java độc lập.

### 13.3. Mọi nhóm đều hợp lệ

Với `List<List<Integer>> groups`, yêu cầu “mọi nhóm có ít nhất một số dương”:

~~~java
boolean valid = !groups.isEmpty()
        && groups.stream().allMatch(
                group -> !group.isEmpty()
                        && group.stream().anyMatch(n -> n > 0));
~~~

Đã thêm kiểm tra cả danh sách ngoài và từng nhóm rỗng, vì nghiệp vụ **đòi hỏi có ít nhất một nhóm và mỗi nhóm có ít nhất một phần tử đạt**. Nếu chỉ dùng `allMatch` tầng ngoài và dữ liệu trống, kết quả mặc định true có thể không phản ánh điều kiện tồn tại.

### 13.4. Dãy vô hạn có thể dừng sớm không?

~~~java
boolean found = java.util.stream.Stream.iterate(1, n -> n + 1)
        .anyMatch(n -> n == 3);
~~~

Với execution tuần tự và logic ổn định, có thể dừng ngay khi thấy `3`. Nhưng câu hỏi “không có số `3` trong dãy vô hạn này?” đòi hỏi xác minh một mệnh đề toàn cục; `noneMatch(n -> n == 3)` cũng có thể dừng sớm ở `3` để trả **`false`**, chứ không trả `true`. Đừng nhầm việc dừng sớm với việc tự chứng minh các mệnh đề lượng từ trên vô hạn.

## 14. Checklist khi review code Java Stream

1. **Nguồn dữ liệu có thể rỗng không?** Nếu có, hiểu rõ `false/true/true` tương ứng.
2. **Bài toán cần boolean hay cần chính phần tử/số lượng?** Nếu cần record, dùng `findFirst`/`findAny`; nếu cần đếm, dùng `count`.
3. **Phát biểu nghiệp vụ dùng “tồn tại”, “mọi” hay “không có”?** Chọn `anyMatch`, `allMatch`, `noneMatch` theo ngôn ngữ tự nhiên.
4. **Predicate có thuần khiết và không ảnh hưởng nguồn không?** Tránh side effect bắt buộc, đặc biệt trong parallel stream.
5. **Có dữ liệu null hoặc exception không?** Xác định policy trước khi dùng method reference có thể dereference null.
6. **Có đang tái sử dụng cùng một stream không?** Mỗi terminal operation yêu cầu stream mới.
7. **Nguồn vô hạn hoặc có filter trước matching không?** Cần bảo đảm có khả năng kết thúc.
8. **Có làm mất ranh giới nhóm bởi flatMap không?** Nếu cần một mệnh đề cho mỗi nhóm, giữ cấu trúc nhóm.
9. **Có đang phủ định nhiều tầng khiến điều kiện khó đọc không?** Có thể đổi `noneMatch(P)` thành `allMatch(P.negate())` hoặc ngược lại nếu phản ánh đúng ý định.
10. **Có kiểm thử trường hợp rỗng, mọi phần tử đúng, mọi phần tử sai và dữ liệu trộn không?** Đây là bốn tình huống phân biệt rõ ba phép toán.

Một bài kiểm thử tốt phải gồm **stream rỗng** và **ít nhất một phần tử khiến matching dừng sớm**. Cả hai dạng thường phát hiện lỗi hiểu sai hơn là chỉ thử các tập dữ liệu thông thường.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `List.of(1, 2, 3).stream().anyMatch(n -> n % 2 == 0)` trả gì?

**Câu 2.** `List.of(1, 2, 3).stream().allMatch(n -> n > 0)` trả gì?

**Câu 3.** `List.of(1, 2, 3).stream().noneMatch(n -> n < 0)` trả gì?

**Câu 4.** Trên stream rỗng, vì sao `allMatch(P)` trả true mà `anyMatch(P)` trả false?

**Câu 5.** `noneMatch(P)` tương đương với phủ định của phương thức nào khi dữ liệu và predicate ổn định?

**Câu 6.** Vì sao không nên ghi audit bắt buộc trong predicate của `anyMatch`?

**Câu 7.** Khi cần lấy một bản ghi thỏa điều kiện thay vì boolean, nên dùng API nào?

**Câu 8.** Nếu doanh nghiệp yêu cầu “ít nhất một mục, và tất cả mục hợp lệ”, chỉ dùng `allMatch` đã đủ chưa?

**Câu 9.** Với `Stream.generate(() -> 1)` vô hạn, `allMatch(n -> n == 1)` có chắc kết thúc không?

**Đáp án:** (1) `true` vì có số `2`. (2) `true` vì mọi số đều dương. (3) `true` vì không có số âm. (4) `allMatch` không tìm được phản ví dụ, trong khi `anyMatch` không tìm được phần tử làm chứng. (5) `!anyMatch(P)`. (6) Short-circuit có thể bỏ qua nhiều phần tử; parallel càng không cam kết thứ tự/số lần gọi. (7) `filter(...).findAny()` hoặc `findFirst()` tùy yêu cầu thứ tự. (8) Chưa, cần kiểm tra nguồn không rỗng. (9) Không, vì không có phản ví dụ để kết luận false và nguồn không có điểm dừng.

## 16. Nguồn tham khảo chính thức

- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): các phương thức `anyMatch`, `allMatch`, `noneMatch`, tính chất short-circuiting terminal operations và kết quả khi stream rỗng.
- [Java SE 17 API — Predicate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Predicate.html): phương thức `test(T)` cùng `negate`, `and`, `or`.
- [Java SE 17 API — IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): các biến thể matching cho nguồn `int`.
- [Java SE 17 Package — java.util.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): đặc tính lazy, non-interference, stateless behavioral parameters và các lưu ý khi xử lý song song.

**Ghi nhớ:** `anyMatch(P)` hỏi **có ai thỏa P không**, `allMatch(P)` hỏi **có phải ai cũng thỏa P**, còn `noneMatch(P)` hỏi **có phải không ai thỏa P**. Với stream rỗng, kết quả lần lượt **`false`, `true`, `true`**. Cả ba đều trả `boolean`, dừng sớm khi đã đủ bằng chứng, và **không bảo đảm predicate chạy cho mọi phần tử**.