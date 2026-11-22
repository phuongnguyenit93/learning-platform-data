# Viết hàm chọn phần tử lớn nhất với giới hạn Comparable trong Java Generics

## 1. Mục tiêu và bài toán

Giả sử bạn cần chọn phần tử lớn nhất trong một nhóm dữ liệu:

- Số nguyên: từ `[3, 9, 7]` chọn `9`.
- Chuỗi: từ `["An", "Mai", "Binh"]` chọn `"Mai"` theo thứ tự tự nhiên của String.
- Ngày: chọn ngày muộn nhất trong nhiều `LocalDate`.
- Đối tượng nghiệp vụ: chọn `Ticket` có độ ưu tiên cao nhất, nếu class định nghĩa cách so sánh tự nhiên.

Viết riêng `maxInteger`, `maxString` và `maxDate` gây lặp thuật toán. Generics cho phép viết **một hàm chọn lớn nhất**, đồng thời yêu cầu compiler xác minh rằng các phần tử có thể so sánh theo cùng một quy tắc.

Ý tưởng cốt lõi:

```java
public static <T extends Comparable<? super T>> T max(
        Iterable<? extends T> values) {
    // Duyệt và giữ giá trị lớn nhất đã gặp.
}
```

Đây chưa phải thân hàm hoàn chỉnh; chương trình Java 17 có thể chạy ở phần 10 chứa implementation đầy đủ, xử lý cả trường hợp đầu vào rỗng và `null`.

Sau bài, bạn sẽ hiểu:

1. `Comparable<T>` là gì và `compareTo` có ý nghĩa ra sao.
2. Tại sao `<T extends Comparable<? super T>>` cần thiết cho một hàm max generic.
3. Khác biệt giữa `Comparable<T>`, `Comparable<? super T>` và `Comparator<? super T>`.
4. Vì sao cần kiểm tra input rỗng/null, dùng `compareTo > 0` và giữ phần tử thắng khi hòa.
5. Cách chọn kiểu nguồn đầu vào: `List<T>`, `Collection<? extends T>` hoặc `Iterable<? extends T>`.
6. Cách diễn giải lỗi type inference/bounds khi gọi hàm với kiểu không so sánh được hoặc dữ liệu trộn loại.
7. Cách kiểm thử, phân tích độ phức tạp và đối chiếu với `Collections.max`/`Stream.max`.

## 2. Tư duy thuật toán trước khi thêm generic

Một giải pháp đơn giản cho danh sách số nguyên:

```java
static Integer maxInteger(List<Integer> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("empty input");
    }
    Integer best = values.get(0);
    for (Integer value : values) {
        if (value.compareTo(best) > 0) {
            best = value;
        }
    }
    return best;
}
```

Hàm mẫu trên cần import `java.util.List`, và giả định phần tử không null. Một điểm có thể cải thiện: vì vòng lặp bắt đầu từ đầu list, giá trị đầu được so với chính nó ở lượt đầu. Thao tác này không làm sai kết quả nếu quy tắc so sánh bình thường, nhưng không cần thiết. Trong implementation hoàn chỉnh, ta lấy phần tử đầu qua iterator rồi duyệt **các phần tử còn lại**.

Thuật toán:

1. Nếu không có phần tử, không thể xác định max: xử lý trường hợp rỗng theo contract.
2. Dùng phần tử đầu làm `best`.
3. Với mỗi phần tử tiếp theo `candidate`, so `candidate.compareTo(best)`.
4. Nếu kết quả lớn hơn 0, cập nhật `best = candidate`.
5. Kết thúc, trả `best`.

**Bất biến vòng lặp:** sau khi xử lý k phần tử đầu, `best` là một phần tử lớn nhất trong k phần tử ấy theo thứ tự đã được định nghĩa. Mỗi phần tử mới hoặc thắng `best`, hoặc không; do đó sau n phần tử, `best` là một giá trị lớn nhất toàn tập.

Nếu nhiều phần tử được so sánh bằng nhau (kết quả 0), dùng toán tử `> 0` giữ **phần tử lớn nhất xuất hiện đầu tiên**. Đây là chính sách ổn định khi chọn tối đa một giá trị; không có nghĩa mọi implementation của max đều bắt buộc có cùng tie-breaking policy.

## 3. `Comparable<T>`: thứ tự tự nhiên do đối tượng định nghĩa

Java khai báo một interface về khả năng so sánh:

```java
public interface Comparable<T> {
    int compareTo(T other);
}
```

Chữ ký trên là dạng rút gọn để thấy phương thức cốt lõi của interface chuẩn, không phải yêu cầu tự viết lại `java.lang.Comparable` trong project.

Một class triển khai `Comparable<T>` xác định **natural ordering** — thứ tự tự nhiên của đối tượng:

```java
record Ticket(String id, int priority) implements Comparable<Ticket> {
    @Override
    public int compareTo(Ticket other) {
        return Integer.compare(priority, other.priority);
    }
}
```

Với quy tắc này, ticket có `priority` lớn hơn sẽ được xem là lớn hơn. `id` dùng nhận diện ticket, **không tham gia so sánh**. Hai ticket khác id nhưng cùng priority được coi là bằng nhau theo compareTo.

### Quy ước dấu của `compareTo`

| Kết quả `x.compareTo(y)` | Ý nghĩa |
| --- | --- |
| Âm (`< 0`) | x đứng trước y; x nhỏ hơn y theo natural ordering. |
| Bằng 0 | x và y tương đương về thứ tự so sánh. |
| Dương (`> 0`) | x đứng sau y; x lớn hơn y. |

**Đừng giả định `compareTo` chỉ trả -1, 0 hoặc 1.** API chỉ cam kết dấu âm/0/dương. Ví dụ các class chuẩn có thể trả nhiều giá trị âm/dương khác nhau. Vì thế so sánh `candidate.compareTo(best) > 0`, không dùng `== 1`.

### Khi nào `compareTo` không phù hợp?

Một số đối tượng không có thứ tự tự nhiên hợp lý, hoặc có nhiều tiêu chí so sánh tùy nghiệp vụ. Ví dụ một nhân viên có thể được sắp theo lương, ngày bắt đầu hay tên. Trong trường hợp đó, đừng bắt class triển khai một natural ordering tùy tiện; sử dụng `Comparator<T>` được truyền vào, như phần 13.

## 4. Vì sao khai báo bound `T extends Comparable...`?

Hãy thử viết:

```java
// Không hợp lệ nếu body gọi compareTo:
static <T> T max(List<T> values) {
    T candidate = values.get(0);
    T best = values.get(1);
    if (candidate.compareTo(best) > 0) {
        return candidate;
    }
    return best;
}
```

Lỗi nằm ở `candidate.compareTo`: compiler chỉ biết T là một reference type chưa bị giới hạn, gần như Object. `Object` không khai báo `compareTo`, nên không có bằng chứng mọi T đều hỗ trợ method đó.

Cách đưa ràng buộc vào generic method:

```java
static <T extends Comparable<T>> T maxSimple(List<T> values) {
    // T biết cách compareTo(T).
    return values.get(0);
}
```

`extends` trong **type parameter bound** được dùng cho cả class lẫn interface. `T extends Comparable<T>` không bắt buộc T phải là một subclass cụ thể của Comparable: `Comparable` là interface và `extends` chỉ thể hiện giới hạn kiểu.

Bound giúp compiler biết một T có method `int compareTo(T)`. Một chữ ký kiểu an toàn không chỉ trả “bất kỳ T” mà còn yêu cầu **khả năng so sánh**.

### Bound là điều kiện compile-time, không phải runtime cast

Khi caller viết `max(List.of(3, 9, 7))`, compiler có thể suy luận T là Integer; Integer triển khai Comparable<Integer>, nên hợp lệ.

Nếu caller truyền các `new Object()`:

```java
// Không biên dịch:
Object result = max(List.of(new Object(), new Object()));
```

`Object` không triển khai Comparable<Object> hay một Comparable phù hợp. Compiler từ chối tại điểm gọi. Điều đó tốt hơn đợi tới runtime rồi cast sang Comparable một cách không kiểm soát.

## 5. Bound linh hoạt hơn: `Comparable<? super T>`

Một API thường nên viết:

```java
<T extends Comparable<? super T>>
```

thay vì chỉ:

```java
<T extends Comparable<T>>
```

Lý do là một class con vẫn có thể **kế thừa khả năng so sánh với class cha**, không trực tiếp implements Comparable của chính kiểu con.

Ví dụ:

```java
static class Score implements Comparable<Score> {
    final int points;

    Score(int points) {
        this.points = points;
    }

    @Override
    public int compareTo(Score other) {
        return Integer.compare(points, other.points);
    }
}

static final class BonusScore extends Score {
    BonusScore(int points) {
        super(points);
    }
}
```

`Score` implements `Comparable<Score>`. `BonusScore` kế thừa `Score.compareTo(Score)` và do đó có thể so sánh các `BonusScore` (vì BonusScore là Score). Tuy nhiên, `BonusScore` không cần triển khai riêng `Comparable<BonusScore>`.

Nếu hàm max yêu cầu `T extends Comparable<T>`, lời gọi giữ kết quả kiểu `BonusScore` có thể không suy luận được:

```java
// Ví dụ lỗi với chữ ký quá hẹp:
static <T extends Comparable<T>> T maxTooStrict(List<T> list) {
    return list.get(0);
}

// BonusScore chosen = maxTooStrict(List.of(
//         new BonusScore(10), new BonusScore(20)));
```

Phương thức `maxTooStrict` trong ví dụ chỉ trả phần tử đầu để cô lập lỗi **bound**. Trường hợp trên đã được kiểm chứng với JDK 17: compiler báo `inference variable T has incompatible bounds` khi đích là BonusScore.

Trong khi đó, bound `Comparable<? super T>` chấp nhận một Comparable của T **hoặc của supertype mà T kế thừa**. Với T=BonusScore, Comparable<Score> là phù hợp vì Score là supertype của BonusScore. Chữ ký rộng hơn mà vẫn có cơ sở an toàn:

```java
static <T extends Comparable<? super T>> T max(
        Iterable<? extends T> values)
```

Vì method `compareTo` có thể nhận Score, truyền một BonusScore vào đó hoàn toàn hợp lệ.

### Đọc cú pháp từ trong ra ngoài

```text
<T extends Comparable<? super T>>
                 |          |
            khả năng      loại tham số compareTo
            so sánh       có thể là T hoặc supertype của T
```

Đây là **lower-bounded wildcard**. Đối với một nơi **tiêu thụ** T (tham số của compareTo), chấp nhận supertype của T giúp tái sử dụng khả năng so sánh của lớp cha. Nó liên hệ nguyên tắc PECS: **Consumer Super**.

### Không nên nhầm `Comparable<? super T>` với `Comparable<? extends T>`

`compareTo` **nhận** một giá trị làm input. Nếu comparator chỉ nhận một subtype chưa biết của T, compiler không có bảo đảm có thể đưa một T bất kỳ vào đó. Với `? super T`, bất kỳ T nào đều có thể dùng ở vị trí input.

## 6. Chọn tham số đầu vào: List, Collection hay Iterable?

Một version đơn giản có thể nhận `List<T>`:

```java
static <T extends Comparable<? super T>> T max(List<T> list) {
    // ...
}
```

Nhưng thuật toán chỉ cần **duyệt tuần tự**. Nó không cần `get(index)`, `set`, `sort`, `size`, hay khả năng chỉnh sửa list. Vì thế `Iterable<? extends T>` là một hợp đồng tổng quát phù hợp:

```java
public static <T extends Comparable<? super T>> T max(
        Iterable<? extends T> values)
```

Lợi ích:

- Dùng được với List và Set, hoặc các iterable domain-specific.
- Không yêu cầu cấu trúc indexable.
- Không mutating input; method chỉ đọc từng phần tử.
- Chấp nhận source có phần tử subtype của T nhờ `? extends T`.
- Caller vẫn nhận đúng kiểu T được compiler suy luận từ nguồn và ngữ cảnh.

`Iterable<? extends T>` là một producer của T; đây là **Producer Extends**. Kết hợp với `Comparable<? super T>` ta có cả hai ý tưởng PECS trong cùng một chữ ký:

- **Nguồn phần tử:** `? extends T` vì dữ liệu được đọc từ source.
- **Khả năng so sánh:** `? super T` vì compareTo tiêu thụ giá trị T.

**Tại sao không dùng `List<? super T>` làm input?** Một list với element type là supertype của T có thể chứa object không phải T, nên đọc từ đó thành T không được bảo đảm.

### Có luôn cần `Iterable` không?

Không. Nếu API cần `size()` hoặc dùng những tính năng của `Collection`, chọn `Collection<? extends T>`. Nếu cần truy cập ngẫu nhiên bằng index vì mục tiêu thuật toán cụ thể, `List<? extends T>` cũng có lý. Mục tiêu là **giao diện hẹp nhất nhưng đủ sức diễn đạt yêu cầu sử dụng**, không phải dùng Iterable theo thói quen.

## 7. Implementation đúng: duyệt một lần bằng Iterator

Implementation đề xuất:

```java
public static <T extends Comparable<? super T>> T max(
        Iterable<? extends T> values) {
    Objects.requireNonNull(values, "values");

    Iterator<? extends T> it = values.iterator();
    if (!it.hasNext()) {
        throw new IllegalArgumentException("empty input");
    }

    T best = Objects.requireNonNull(it.next(), "element");

    while (it.hasNext()) {
        T candidate = Objects.requireNonNull(it.next(), "element");
        if (candidate.compareTo(best) > 0) {
            best = candidate;
        }
    }
    return best;
}
```

Để đặt đoạn trong class, cần import `java.util.Iterator` và `java.util.Objects`. Chương trình đầy đủ ở phần 10 có import và main.

Phân tích từng bước:

1. `Objects.requireNonNull(values,"values")` bác bỏ tham chiếu iterable null từ đầu.
2. `values.iterator()` lấy trình duyệt; method không cần biết concrete collection.
3. `!it.hasNext()` xử lý input rỗng bằng `IllegalArgumentException` rõ ràng.
4. `it.next()` lấy phần tử đầu làm best; kiểm tra phần tử null.
5. Mỗi phần tử còn lại được kiểm tra null rồi so sánh với best.
6. `candidate.compareTo(best) > 0` thay best khi candidate lớn hơn.
7. Trả trực tiếp **một trong các object đã xuất hiện trong input**, không cần tạo bản sao.

### Tại sao không khởi tạo `T best = null`?

Làm vậy đòi thiết kế thêm quy tắc cho phần tử đầu và có thể che lỗi null. Lấy phần tử đầu làm best sau khi đã kiểm tra tập rỗng giúp invariant rõ ràng: khi bắt đầu vòng lặp, best là phần tử thực thuộc tập và không null.

### Tại sao không so sánh bằng `==` hoặc `>`?

Generics T là kiểu tham chiếu; toán tử `>` không định nghĩa cho mọi object kiểu T. `==` so sánh identity của object (trừ các tình huống primitive/boxing liên quan), không mô tả thứ tự. `compareTo` là hợp đồng so sánh đã được compiler bảo đảm.

### Tại sao không dùng `>= 0`?

Dùng `>= 0` cũng chọn được một phần tử lớn nhất nếu thứ tự hợp lệ, nhưng khi có hai phần tử tương đương (compareTo trả 0), nó sẽ chọn **phần tử đến sau** thay vì giữ phần tử đầu. Mẫu trên dùng `> 0` như một quy tắc tie-breaking cố định và dễ kiểm thử.

### Xử lý null trong contract

Ở đây mọi phần tử đều bắt buộc non-null. Khi gặp phần tử null, method ném `NullPointerException("element")`. Nếu một API muốn có null như giá trị tối thiểu/tối đa, cần định nghĩa ordering cho null và thường nên dùng `Comparator.nullsFirst`/`Comparator.nullsLast` trong phiên bản nhận Comparator. Không để null trôi vào `compareTo` mà không có chính sách rõ.

### Trường hợp nguồn bị thay đổi trong khi duyệt

Method không tự đồng bộ hóa collection. Nếu thread khác sửa collection trong lúc duyệt, kết quả phụ thuộc hợp đồng iterator của collection; có thể có `ConcurrentModificationException` hoặc hành vi khác theo loại collection. Trong code concurrent, cần snapshot hoặc cơ chế đồng bộ phù hợp, không dựa vào generic bound để giải quyết concurrency.

## 8. Độ phức tạp và tính đúng

Với n phần tử:

- Đọc phần tử đầu làm best: O(1).
- So sánh các phần tử còn lại: đúng **n-1 lần gọi compareTo** khi n ≥ 1 (không tính việc kiểm tra null và phép duyệt).
- Thời gian: O(n) nếu mỗi phép compareTo có chi phí O(1). Tổng quát hơn: O(n × chi phí so sánh).
- Bộ nhớ bổ sung của thuật toán: O(1), không tính iterator và các cấu trúc sẵn có trong nguồn. Nó chỉ giữ best, candidate và iterator.

Không thể xác định max trong trường hợp tổng quát bằng cách bỏ qua một phần tử chưa được kiểm tra: một phần tử chưa xét có thể lớn hơn tất cả những phần tử đã xét.

### Chứng minh invariant

**Ban đầu:** Sau khi đọc phần tử đầu, best rõ ràng lớn nhất trong tập gồm đúng phần tử ấy.

**Bước duy trì:** Giả sử best là lớn nhất trong k phần tử đã xử lý. Xét candidate kế tiếp:

- Nếu `candidate.compareTo(best)>0`, candidate lớn hơn best và do đó không thua bất kỳ phần tử trước.
- Nếu điều kiện không đúng, best không nhỏ hơn candidate theo thứ tự so sánh dự kiến; nó tiếp tục là phần tử lớn nhất trong k+1 phần tử.

**Kết thúc:** Sau khi duyệt toàn bộ n phần tử, best là một phần tử lớn nhất.

Chứng minh dựa trên việc `compareTo` tuân thủ **thứ tự nhất quán và hợp đồng Comparable**. Nếu compareTo vi phạm tính bắc cầu hoặc thay đổi kết quả theo trạng thái không ổn định, khái niệm phần tử lớn nhất có thể không rõ ràng và vòng lặp không thể bảo đảm ý nghĩa mong muốn.

## 9. Dạng tiện dụng cho nhiều đối số: `maxOf`

Thay vì tự dựng List, caller có thể muốn:

```java
int best = maxOf(5, 2, 8, 4);
```

Một overload/utility method dạng varargs:

```java
@SafeVarargs
public static <T extends Comparable<? super T>> T maxOf(
        T first, T... rest) {
    T best = Objects.requireNonNull(first, "first");
    for (T candidate : rest) {
        T checked = Objects.requireNonNull(candidate, "element");
        if (checked.compareTo(best) > 0) {
            best = checked;
        }
    }
    return best;
}
```

`maxOf` có một phần tử `first` bắt buộc, nên caller không thể gọi hoàn toàn không đối số. Bên trong không trả mảng varargs, không lưu tham chiếu mảng, không sửa slot bằng kiểu không phù hợp; nó chỉ duyệt và chọn best. Với Java 17, `@SafeVarargs` hợp lệ trên static varargs method và giúp xử lý các cảnh báo generic varargs theo cam kết an toàn của tác giả.

**Quan trọng:** Annotation không tự làm code an toàn. Nếu sau này refactor method để giữ, xuất bản hoặc ghi sai mảng varargs, phải đánh giá lại cam kết `@SafeVarargs`. Đặc biệt khi T non-reifiable, không nên trả `T[] rest` ra ngoài một cách tùy tiện.

### Có thể dùng `maxOf("A", "B")` không?

Có, vì String implements Comparable<String>. Nhưng đừng nhầm một invocation dùng chung T với khả năng so sánh giữa những loại tùy ý. `maxOf("A", 3)` không nhất thiết suy luận được một T phù hợp bound Comparable, dù cả String và Integer riêng lẻ đều Comparable.

### Lưu ý về overload

Nếu API có cả `max(List<T>)` và `maxOf(T, T...)`, đặt tên riêng `maxOf` như trên giúp tránh overload resolution khó hiểu với arrays và generics, đồng thời thể hiện contract không rỗng ở call site.

## 10. Chương trình Java 17 hoàn chỉnh có thể chạy

**Tệp `ComparableMaxDemo.java`**:

```java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

public class ComparableMaxDemo {
    public static <T extends Comparable<? super T>> T max(
            Iterable<? extends T> values) {
        Objects.requireNonNull(values, "values");
        Iterator<? extends T> it = values.iterator();
        if (!it.hasNext()) {
            throw new IllegalArgumentException("empty input");
        }
        T best = Objects.requireNonNull(it.next(), "element");
        while (it.hasNext()) {
            T candidate = Objects.requireNonNull(it.next(), "element");
            if (candidate.compareTo(best) > 0) {
                best = candidate;
            }
        }
        return best;
    }

    @SafeVarargs
    public static <T extends Comparable<? super T>> T maxOf(
            T first, T... rest) {
        T best = Objects.requireNonNull(first, "first");
        for (T candidate : rest) {
            T checked = Objects.requireNonNull(candidate, "element");
            if (checked.compareTo(best) > 0) {
                best = checked;
            }
        }
        return best;
    }

    public static <T> T maxBy(
            Iterable<? extends T> values, Comparator<? super T> comparator) {
        Objects.requireNonNull(values, "values");
        Objects.requireNonNull(comparator, "comparator");
        Iterator<? extends T> it = values.iterator();
        if (!it.hasNext()) {
            throw new IllegalArgumentException("empty input");
        }
        T best = Objects.requireNonNull(it.next(), "element");
        while (it.hasNext()) {
            T candidate = Objects.requireNonNull(it.next(), "element");
            if (comparator.compare(candidate, best) > 0) {
                best = candidate;
            }
        }
        return best;
    }

    record Ticket(String id, int priority) implements Comparable<Ticket> {
        @Override
        public int compareTo(Ticket other) {
            return Integer.compare(priority, other.priority);
        }
    }

    static class Score implements Comparable<Score> {
        final String label;
        final int points;

        Score(String label, int points) {
            this.label = label;
            this.points = points;
        }

        @Override
        public int compareTo(Score other) {
            return Integer.compare(points, other.points);
        }

        @Override
        public String toString() {
            return label + ":" + points;
        }
    }

    static final class BonusScore extends Score {
        BonusScore(String label, int points) {
            super(label, points);
        }
    }

    public static void main(String[] args) {
        System.out.println("integers=" + max(List.of(3, 9, 7)));
        System.out.println("strings=" + max(List.of("An", "Mai", "Binh")));
        System.out.println("dates=" + max(List.of(
                LocalDate.of(2026, 1, 3),
                LocalDate.of(2026, 1, 10))));
        System.out.println("varargs=" + maxOf(5, 2, 8, 4));

        List<Ticket> tickets = List.of(
                new Ticket("first", 5),
                new Ticket("second", 5),
                new Ticket("low", 3));
        System.out.println("tie=" + max(tickets).id());

        List<BonusScore> bonuses = List.of(
                new BonusScore("Bronze", 10),
                new BonusScore("Gold", 20));
        BonusScore bestBonus = max(bonuses);
        System.out.println("inheritedComparable=" + bestBonus);

        System.out.println("customComparator=" + maxBy(
                List.of("An", "Huyen", "Lan"),
                Comparator.comparingInt(String::length)));
        System.out.println("jdkMax=" + Collections.max(List.of(3, 9, 7)));

        try {
            max(List.<Integer>of());
        } catch (IllegalArgumentException e) {
            System.out.println("empty=" + e.getMessage());
        }

        try {
            max(Arrays.asList(1, null, 3));
        } catch (NullPointerException e) {
            System.out.println("null=" + e.getMessage());
        }
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all ComparableMaxDemo.java
java ComparableMaxDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
integers=9
strings=Mai
dates=2026-01-10
varargs=8
tie=first
inheritedComparable=Gold:20
customComparator=Huyen
jdkMax=9
empty=empty input
null=element
```

Lệnh `javac --release 17 -Xlint:all` đã biên dịch chương trình này mà không báo warning trong phép thử.

### Diễn giải kết quả

- `integers=9`: Integer implements Comparable<Integer>, chọn 9.
- `strings=Mai`: String có thứ tự từ điển theo quy tắc của `String.compareTo`; trong bộ dữ liệu này Mai đứng sau An và Binh. Điều này không có nghĩa String.compareTo hiểu collation tiếng Việt hay chữ hoa/chữ thường theo locale người dùng.
- `dates=2026-01-10`: LocalDate so sánh theo thứ tự thời gian.
- `varargs=8`: `maxOf` tìm phần tử lớn nhất trong những đối số nguyên.
- `tie=first`: hai Ticket priority=5 được so sánh bằng 0; dùng điều kiện `>0` nên phần tử đầu được giữ.
- `inheritedComparable=Gold:20`: BonusScore kế thừa Comparable<Score> từ Score và được bound `Comparable<? super T>` chấp nhận.
- `customComparator=Huyen`: comparator theo độ dài chuỗi chọn Huyen (5 ký tự) thay vì theo thứ tự tự nhiên của String.
- `jdkMax=9`: kết quả thư viện chuẩn phù hợp với phiên bản tự viết.
- `empty=empty input`: demo chủ động quyết định throw IllegalArgumentException với thông báo nhất quán.
- `null=element`: demo chủ động bác bỏ phần tử null trong nguồn.

## 11. Ví dụ lỗi biên dịch 1: T không Comparable

**Tệp `NonComparableMax.java` — cố ý không biên dịch:**

```java
import java.util.List;

class NonComparableMax {
    static <T extends Comparable<? super T>> T max(List<T> values) {
        return values.get(0);
    }

    static void test() {
        Object result = max(List.of(new Object(), new Object()));
    }
}
```

Lệnh:

```bash
javac --release 17 -Xdiags:verbose NonComparableMax.java
```

Compiler đã báo trọng tâm:

```text
method max in class NonComparableMax cannot be applied to given types
required: List<T>
found:    List<Object>
reason: inference variable E has incompatible bounds
upper bounds: Comparable<? super T>,Object
lower bounds: Object
```

`Object` không cung cấp Comparable cần thiết. Không nên ép `Object` thành Comparable chỉ để im lặng compiler nếu các object thực không thể so sánh. Hãy thiết kế một loại có natural ordering hoặc sử dụng comparator được xác định từ bên ngoài.

## 12. Ví dụ lỗi biên dịch 2: bound quá hẹp

**Tệp `WrongComparableBound.java` — cố ý không biên dịch:**

```java
import java.util.List;

class WrongComparableBound {
    static <T extends Comparable<T>> T max(List<T> values) {
        return values.get(0);
    }

    static class Base implements Comparable<Base> {
        @Override
        public int compareTo(Base other) {
            return 0;
        }
    }

    static class Child extends Base {}

    static void test() {
        Child result = max(List.of(new Child(), new Child()));
    }
}
```

Compiler Java 17 báo:

```text
incompatible types: inference variable T has incompatible bounds
equality constraints: Base,E
upper bounds: Child,Object,Comparable<T>
```

`Child` kế thừa `Comparable<Base>`, không có `Comparable<Child>` theo dạng bound chặt. Chữ ký method khi chỉ cần compareTo có thể sửa thành:

```java
static <T extends Comparable<? super T>> T max(List<T> values) {
    // Dùng thuật toán max thật như phần 7.
    return values.get(0);
}
```

Đoạn trên chỉ minh họa **chữ ký bound sửa đúng**, chưa phải implementation max. Với bound này, caller có thể nhận lại Child khi phần tử nguồn đều là Child.

**Đừng “sửa” bằng cách bắt Child implements Comparable<Child> riêng** nếu điều đó không phù hợp mô hình kế thừa. Dùng `? super T` giúp API tôn trọng Comparable<Base> mà class con đã có.

## 13. Ví dụ lỗi biên dịch 3: trộn kiểu không có ordering chung

**Tệp `MixedTypesMax.java` — cố ý không biên dịch:**

```java
import java.util.List;

class MixedTypesMax {
    static <T extends Comparable<? super T>> T max(List<T> values) {
        return values.get(0);
    }

    static void test() {
        Object result = max(List.of("A", 3));
    }
}
```

Compiler đã báo `method max cannot be applied` và `inference variable E has incompatible bounds`, với các ràng buộc từ String, Integer và Comparable.

Mỗi String hoặc Integer tự so sánh được với đối tượng **cùng họ phù hợp**, nhưng không có nghĩa String và Integer có một natural ordering chung mà hàm `compareTo` này có thể dùng. Điều kiện phải đảm bảo tương thích trên toàn bộ tập, không chỉ từng phần tử riêng rẽ.

Nếu nghiệp vụ thật sự cần so sánh dữ liệu khác loại, phải xác định **một quy tắc chung rõ ràng** và sử dụng Comparator phù hợp. Ví dụ chuyển cả hai thành một kiểu domain có tiêu chí so sánh thống nhất, hoặc chỉ so theo thuộc tính đo lường có nghĩa. Không ép các giá trị khác loại vào Comparable raw và đoán kết quả.

## 14. Ví dụ lỗi biên dịch 4: thêm bound Number không cần thiết

**Tệp `WrongNumberBound.java` — cố ý không biên dịch:**

```java
import java.util.List;

class WrongNumberBound {
    static <T extends Number & Comparable<? super T>> T max(
            List<T> values) {
        return values.get(0);
    }

    static void test() {
        String result = max(List.of("A", "B"));
    }
}
```

Compiler báo `incompatible bounds`, trong đó có:

```text
upper bounds: Number,Comparable<? super T>,Object
lower bounds: String
```

String có Comparable<String> nhưng **không extends Number**. Nếu thuật toán chỉ gọi compareTo, giới hạn Number là thừa và loại bỏ những kiểu hợp lệ như String, LocalDate, enum phù hợp, hoặc domain class Comparable.

Khi nào bound Number có ích? Khi body **thực sự cần method của Number** như `doubleValue()` bên cạnh compareTo. Khi đó:

```java
<T extends Number & Comparable<? super T>>
```

là hợp lý vì diễn đạt **hai yêu cầu**. Với multiple bounds, class bound `Number` phải đứng trước interface bound `Comparable`.

## 15. So sánh với thư viện chuẩn

Java đã cung cấp các API chọn max; bài tập tự viết nhằm hiểu Generics, bounds và invariant, chứ không bắt buộc tạo utility mới trong mọi project.

### `Collections.max`

`java.util.Collections.max(Collection<? extends T>)` sử dụng natural ordering và một bound của type parameter gần với `Comparable<? super T>`; API còn duy trì chi tiết bound vì tương thích nhị phân. Có thể viết:

```java
Integer best = Collections.max(List.of(3, 9, 7));
```

Cần import `java.util.Collections`. `Collections.max` đòi collection không rỗng; với đầu vào rỗng, API chuẩn ném `NoSuchElementException`, **khác với** IllegalArgumentException do hàm `max` tự viết cố ý chọn. Hãy xem exception contract khi thay implementation bằng API chuẩn.

`Collections.max(collection, comparator)` cũng có overload nhận Comparator để quyết định ordering bên ngoài.

### `Stream.max`

Với stream:

```java
Optional<Integer> best =
        List.of(3, 9, 7).stream().max(Integer::compareTo);
```

`Stream.max(Comparator)` trả `Optional<T>`, nên một stream rỗng có thể cho Optional.empty() thay vì buộc ném exception. Nếu ứng dụng muốn người gọi xử lý trường hợp không có phần tử, `Optional<T>` là một contract hữu ích. Đừng gọi `optional.get()` vô điều kiện trên Optional rỗng.

### Tự viết hay dùng thư viện?

Dùng `Collections.max` hoặc `Stream.max` khi hành vi của chúng đáp ứng contract. Tự viết khi cần:

- Dạy/học type bounds, iterator và generic inference.
- Quy định cách xử lý null, empty input và tie-breaking đặc thù.
- Có một Iterable mà API Collection/Stream không được cung cấp trực tiếp.
- Tích hợp logging, kiểm soát so sánh, hoặc xử lý domain-specific.

Không nên viết lại chỉ vì “generic hơn”: hãy so chi phí bảo trì và đảm bảo API chuẩn.

## 16. Comparator: mở rộng khi T không có natural ordering

Bound Comparable yêu cầu **bản thân T có natural ordering**. Nhiều loại dữ liệu không có hoặc không nên có thứ tự mặc định. Khi đó truyền vào một Comparator:

```java
public static <T> T maxBy(
        Iterable<? extends T> values,
        Comparator<? super T> comparator) {
    Objects.requireNonNull(values, "values");
    Objects.requireNonNull(comparator, "comparator");
    Iterator<? extends T> it = values.iterator();
    if (!it.hasNext()) {
        throw new IllegalArgumentException("empty input");
    }
    T best = Objects.requireNonNull(it.next(), "element");
    while (it.hasNext()) {
        T candidate = Objects.requireNonNull(it.next(), "element");
        if (comparator.compare(candidate, best) > 0) {
            best = candidate;
        }
    }
    return best;
}
```

Cần import `Comparator`, `Iterator`, `Objects`. Đoạn này có trong chương trình hoàn chỉnh phần 10.

Ví dụ:

```java
String longest = maxBy(
        List.of("An", "Huyen", "Lan"),
        Comparator.comparingInt(String::length));
System.out.println(longest); // Huyen
```

Ở đây không cần T extends Comparable vì comparator nhận trách nhiệm so sánh. `Comparator<? super T>` dùng super vì comparator **tiêu thụ** hai đối tượng T.

### Natural ordering và custom ordering

- `max(List.of("An","Huyen","Lan"))` dùng `String.compareTo`; kết quả natural order theo Unicode, không phải độ dài.
- `maxBy(..., comparingInt(String::length))` dùng chiều dài chuỗi; Huyen dài nhất trong ví dụ.
- Nếu nhiều chuỗi cùng độ dài, code này giữ chuỗi đầu tiên có độ dài lớn nhất, vì chỉ cập nhật khi so sánh dương.

### `Comparator.reversed()` có ảnh hưởng gì?

Nếu comparator định nghĩa `a < b` theo một tiêu chí, dùng `reversed()` đảo thứ tự. Khi gọi max với comparator đảo ngược, kết quả sẽ tương đương **phần tử nhỏ nhất theo comparator gốc**, theo logic sign của compare.

Đừng đổi chiều so sánh trong body theo cảm tính. Giữ invariant “candidate > best theo comparator được cung cấp” giúp tránh bug khi thêm ascending/descending mode.

## 17. Viết `compareTo` cho class nghiệp vụ đúng cách

Đây là đoạn rút gọn từ `Ticket`:

```java
record Ticket(String id, int priority) implements Comparable<Ticket> {
    @Override
    public int compareTo(Ticket other) {
        return Integer.compare(priority, other.priority);
    }
}
```

### Tránh phép trừ làm comparator

Mẫu dễ gây overflow:

```java
// KHÔNG NÊN:
return this.priority - other.priority;
```

Nếu một số gần `Integer.MAX_VALUE` và số khác gần `Integer.MIN_VALUE`, phép trừ có thể overflow và đảo dấu sai. Dùng `Integer.compare(this.priority, other.priority)` hoặc `Comparator.comparingInt(Ticket::priority)` sẽ rõ và an toàn hơn về dấu.

### Hợp đồng `Comparable`

Một ordering lành mạnh cần tuân thủ các thuộc tính như:

- Dấu của `x.compareTo(y)` phải đối xứng với dấu của `y.compareTo(x)`.
- Nếu x > y và y > z, x phải > z theo tính bắc cầu.
- Nếu x.compareTo(y)==0, quan hệ so sánh của x và y với các z phải tương thích với tính nhất quán của ordering.
- Cần xem chính sách `null`; nhiều implementation Comparable chuẩn không nhận null.

**Nhất quán với `equals` là điều được khuyến nghị, không phải lúc nào bắt buộc**. Ví dụ Ticket là record: equals xét cả id và priority, trong khi compareTo chỉ xét priority. Hai Ticket có id khác nhau nhưng priority bằng nhau được compareTo xem là tương đương. `max` vẫn có thể chọn một phần tử lớn nhất, nhưng khi dùng loại này trong `TreeSet`/`TreeMap`, những cấu trúc dựa trên comparison có thể xem chúng như khóa trùng nhau. Cần cân nhắc business identity và collection semantics.

### Ordering dựa trên trạng thái mutable

Nếu đối tượng bị thay đổi priority trong khi đang so sánh, kết quả max có thể không phản ánh một snapshot nhất quán. Hãy định nghĩa dữ liệu bất biến hoặc điều phối cập nhật trạng thái phù hợp khi dùng comparator trong thuật toán/collection sorted.

## 18. Ngữ nghĩa của String, Number, LocalDate và null

### String

`String.compareTo` so sánh chuỗi theo thứ tự từ điển dựa trên UTF-16 code units. Nó không thay thế một `Collator` cho thứ tự ngôn ngữ cụ thể. Vì vậy kết quả max String là **lớn nhất theo natural ordering của String**, không phải “tên xếp sau trong danh bạ tiếng Việt”.

Nếu cần thứ tự người dùng kỳ vọng theo locale, chọn comparator thích hợp thay vì thay đổi dữ liệu đầu vào tùy tiện.

### Integer, Long và Number

`Integer` và `Long` đều Comparable nhưng không cùng generic contract `Comparable<Number>`. Một List<Number> chứa cả Integer và Long không tự trở thành dãy có natural ordering chung. Giới hạn `T extends Number & Comparable<? super T>` không biến mọi Number thành so sánh được lẫn nhau.

Có thể tạo comparator xử lý Number theo một đại lượng xác định như `doubleValue()`, nhưng cần xét mất chính xác, NaN và các loại Number domain-specific. Đừng biến đổi sang double mà chưa xem yêu cầu tính toán.

### Float/Double

`Float.compareTo`/`Double.compareTo` định nghĩa ordering bao gồm các trường hợp `NaN` và signed zero theo hợp đồng lớp. Đừng dùng trực tiếp toán tử `>` để giả định tương đương với `compareTo` ở mọi giá trị floating-point đặc biệt.

### LocalDate

`LocalDate` có natural ordering dựa trên ngày, nên `max(List<LocalDate>)` chọn ngày muộn nhất. Nếu đang xử lý sự kiện có thời gian và timezone, hãy chọn kiểu domain như `Instant`, `ZonedDateTime` hoặc một comparator cụ thể phù hợp, thay vì so LocalDate rồi hiểu nhầm “thời điểm mới nhất”.

### Null

API demo chủ động không nhận null cho container hoặc các phần tử. `Objects.requireNonNull` làm điểm thất bại rõ ràng thay vì để compareTo ném lỗi ở vị trí không dự đoán được. Nếu null có nghĩa nghiệp vụ (ví dụ “chưa đánh giá”), nên định nghĩa thứ tự rõ bằng Comparator hoặc lọc null trước khi gọi max, và nêu điều này trong contract.

## 19. Edge cases và bảng kiểm thử

| Input | Kết quả kỳ vọng với implementation phần 7 | Giải thích |
| --- | --- | --- |
| `[3,9,7]` | 9 | Phần tử lớn nhất. |
| `[4]` | 4 | Một phần tử cũng là max. |
| `[5,5,3]` | Phần tử 5 đầu tiên | Giữ best khi compareTo bằng 0. |
| `[]` | IllegalArgumentException | Không có phần tử đầu để chọn. |
| `null` làm Iterable | NullPointerException, message `values` | Guard ở đầu method. |
| `[1,null,3]` | NullPointerException, message `element` | Contract từ chối null element. |
| `["An","Mai","Binh"]` | "Mai" | Thứ tự String tự nhiên. |
| `List<BonusScore>` | BonusScore điểm cao nhất | Bound wildcard super chấp nhận Comparable<Score>. |
| `List<Object>` | Lỗi compile tại invocation | Object không bảo đảm Comparable. |
| `List<String,Integer>` hỗn hợp | Không suy luận natural max chung | Các kiểu so sánh khác họ. |

Không phải mọi dữ liệu có thể biểu diễn bằng `List<?>` đều có natural max. Compiler cần một bound tương thích với toàn bộ phần tử theo kiểu tĩnh; cố né bằng raw/unchecked cast làm mất bảo đảm này.

### Kiểm thử tính đúng thay vì chỉ kiểm tra ví dụ thuận lợi

- Max ở đầu/cuối/giữa input.
- Nhiều phần tử trùng thứ tự (tie).
- Giá trị âm hoặc số lớn nếu dùng dữ liệu số.
- Phần tử null và container null.
- Input rỗng và chỉ một phần tử.
- Class con kế thừa Comparable của cha.
- Comparator đảo chiều hoặc comparator không phù hợp.
- Mutation/concurrency nếu source là collection mutable đang được chia sẻ.

Khi bài toán thay đổi quy tắc chọn (ví dụ tất cả các phần tử cùng max), API phải thay đổi kiểu kết quả; một method trả T không thể tự trả đủ toàn bộ các phần tử hòa nếu không đổi contract.

## 20. Các lỗi hiểu nhầm thường gặp

**Nhầm 1: “Generic T có thể gọi compareTo mà không cần bound.”** Không đúng; compiler chỉ biết những method bảo đảm bởi bound của T. Thêm `extends Comparable<? super T>` nếu yêu cầu natural ordering.

**Nhầm 2: “Bound phải là Comparable<T>, không dùng wildcard.”** Không đúng. `Comparable<? super T>` linh hoạt và an toàn hơn với lớp con kế thừa Comparable của cha.

**Nhầm 3: “Comparable<? super T> cho phép so sánh mọi hai loại Object.”** Không đúng. Nó chỉ chứng minh khả năng truyền một T vào compareTo phù hợp; không tạo ordering chung giữa String và Integer.

**Nhầm 4: “compareTo trả +1 nếu lớn hơn.”** Không đúng; chỉ cần dấu dương. So `>0`.

**Nhầm 5: “Phải cast T sang Comparable trong body.”** Không cần khi đã có bound đúng; cast raw làm yếu type safety.

**Nhầm 6: “Dùng List<Number> nhận List<Integer> vì Integer extends Number.”** Generics invariant. Đọc từ List<Integer> qua `List<? extends Number>` hoặc copy vào List<Number> mới.

**Nhầm 7: “Không cần xử lý input rỗng.”** Hàm trả T không có phần tử để trả khi rỗng. Throw hoặc đổi contract thành Optional<T>.

**Nhầm 8: “Kết quả max khi hòa không quan trọng.”** Đối với object khác identity nhưng compareTo=0, tie-breaking có thể ảnh hưởng id được trả, logic nghiệp vụ và test.

**Nhầm 9: “String max là sắp theo tiếng Việt.”** String.compareTo không cung cấp locale-aware collation.

**Nhầm 10: “Có Comparable thì equals phải tương đương compareTo.”** Được khuyến nghị cho nhiều use case, nhưng không bắt buộc. Khi không nhất quán, sorted collections có semantics cần chú ý.

**Nhầm 11: “Dùng comparator chỉ khác cú pháp.”** Comparator cho phép ordering tùy chiến lược, kể cả class không implements Comparable. Nó mở rộng miền ứng dụng của thuật toán.

**Nhầm 12: “Sửa cảnh báo bằng @SuppressWarnings là xong.”** Annotation không biến Object thành Comparable hoặc tạo ordering nhất quán, và không khắc phục compile error về incompatible bounds.

## 21. Bài tập thực hành có đáp án

### Bài 1. Điền bound

Cho body:

```java
static <T /* bound? */> T bigger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

**Đáp án:** `<T extends Comparable<? super T>>`. Bound bảo đảm `a.compareTo(b)` hợp lệ. Dùng `>=0` thì khi hòa trả a; nếu dùng `>0` và else b thì khi hòa trả b.

### Bài 2. Vì sao không viết `candidate > best`?

**Đáp án:** Toán tử > không áp dụng cho mọi reference type T. Java không overload toán tử > cho arbitrary object; cần compareTo hoặc Comparator.

### Bài 3. Điểm khác nhau giữa `Comparable<T>` và `Comparable<? super T>`?

**Đáp án:** Bound thứ hai cho phép T triển khai Comparable của một supertype T, hữu ích cho subclass như BonusScore kế thừa `Comparable<Score>`. Đây là nới lỏng an toàn tại vị trí nhận tham số compareTo.

### Bài 4. Tại sao `List.of("A", 3)` không hợp lệ cho max tự nhiên?

**Đáp án:** String và Integer có natural ordering riêng, không có guarantee rằng có một T chung thỏa Comparable<? super T> cho cả hai theo chữ ký. Compiler có thể báo incompatible bounds.

### Bài 5. Vì sao List Integer có thể truyền vào Iterable<? extends Number>?

**Đáp án:** Vì Iterable sản xuất phần tử để đọc, và Integer extends Number. Tuy nhiên muốn trả max với T=Number thì cần Number tự có Comparable phù hợp; chỉ có quan hệ Iterable không đủ cho Comparable bound.

### Bài 6. Tại sao cần kiểm tra empty?

**Đáp án:** Không tồn tại phần tử đầu để làm best; method trả T phải chọn một chính sách, như IllegalArgumentException, hoặc đổi sang Optional<T>.

### Bài 7. Hàm max ở phần 7 chọn phần tử nào khi bằng nhau?

**Đáp án:** Giữ phần tử lớn nhất đầu tiên vì chỉ thay best khi compareTo > 0. Nếu đổi >= 0, phần tử về sau sẽ thay phần tử trước khi hòa.

### Bài 8. Có thể dùng max cho một record Ticket không?

**Đáp án:** Có nếu Ticket implements Comparable<Ticket> với compareTo hợp lệ. Ví dụ phần 10 so theo priority và chọn Ticket đầu khi hai priority cùng 5.

### Bài 9. Tại sao không viết `this.priority - other.priority`?

**Đáp án:** Phép trừ int có thể overflow, đảo dấu sai; dùng `Integer.compare`.

### Bài 10. `Collections.max` khác hàm tự viết ở điểm nào?

**Đáp án:** Cùng mục tiêu natural max với collection phù hợp, nhưng ví dụ tự viết nhận Iterable và chọn IllegalArgumentException khi rỗng; Collections.max trên collection rỗng ném NoSuchElementException.

### Bài 11. Nếu class không có Comparable nhưng muốn chọn theo age?

**Đáp án:** Dùng `maxBy(values, Comparator.comparingInt(Person::age))` nếu có một kiểu Person định nghĩa accessor age; comparator cung cấp ordering độc lập với class.

### Bài 12. Hàm có thể trả một `BonusScore` từ List<BonusScore> dù nó chỉ Comparable<Score> không?

**Đáp án:** Có với bound `T extends Comparable<? super T>`; Score là supertype của BonusScore, nên compareTo(Score) nhận được BonusScore.

### Bài 13. Vì sao không coi Number là loại so sánh chung của mọi Integer/Double?

**Đáp án:** Number không định nghĩa compareTo và một List<Number> có thể chứa nhiều loại Number khác nhau. Cần comparator có chính sách chung hoặc convert domain type phù hợp.

### Bài 14. Độ phức tạp?

**Đáp án:** Với n≥1, method duyệt một lần và so sánh n-1 lần. Thời gian O(n) nếu compareTo O(1), bộ nhớ bổ sung thường O(1).

### Bài 15. Nếu người dùng muốn max theo nhiều tiêu chí?

**Đáp án:** Dùng Comparator có cấu trúc như `Comparator.comparingInt(...).thenComparing(...)` để xác định tiêu chí phụ, tránh gắn natural ordering tùy tiện vào class nếu có nhiều thứ tự nghiệp vụ khác nhau.

## 22. Checklist triển khai trong dự án

1. Đầu vào có natural ordering không, hay cần Comparator?
2. T đã có bound `Comparable<? super T>` chưa?
3. Bound có quá hẹp (Comparable<T>) hoặc quá rộng (raw Comparable) không?
4. API chỉ cần Iterable hay cần Collection/List?
5. Có cho null container, null elements và empty input không?
6. Tie-breaking là giữ phần tử đầu hay cuối khi compareTo==0?
7. compareTo có nhất quán, bắc cầu, ổn định với dữ liệu đang xét không?
8. Comparator có dựa trên state mutable hay external service làm ordering thay đổi không?
9. Có bị trộn các kiểu so sánh không tương thích không?
10. Có thể dùng Collections.max hoặc Stream.max thay code tự viết không?
11. Các ví dụ Java đã biên dịch với đúng tên class/file và stdout đã xác minh chưa?
12. Các case lỗi có được biên dịch riêng và chẩn đoán đúng type inference/bounds không?

## 23. Kết luận

Để viết hàm chọn phần tử lớn nhất có an toàn kiểu, hãy bắt đầu từ hợp đồng `Comparable` thay vì ép kiểu hoặc toán tử so sánh không áp dụng cho T. Chữ ký:

```java
public static <T extends Comparable<? super T>> T max(
        Iterable<? extends T> values)
```

thể hiện hai quan hệ then chốt: **T có thể so sánh với một T thông qua Comparable của T hoặc supertype phù hợp**, và **nguồn có thể cung cấp những phần tử là T hoặc subtype của T**. Phần thân chỉ cần duyệt một lần, giữ phần tử lớn nhất đã thấy và xử lý rõ đầu vào rỗng/null.

Với ordering tự nhiên, đây là bài tập điển hình của bounded type parameters trong Java Generics. Với ordering thay đổi theo nghiệp vụ, dùng một phiên bản nhận Comparator. Không làm yếu type safety bằng raw cast khi compiler báo incompatible bounds, và không quên các ràng buộc hành vi của compareTo.

**Ghi nhớ:** Bound không chỉ giúp code gọi được `compareTo`; nó là lời hứa compile-time rằng phép so sánh có ý nghĩa đối với loại phần tử mà API nhận và trả.
