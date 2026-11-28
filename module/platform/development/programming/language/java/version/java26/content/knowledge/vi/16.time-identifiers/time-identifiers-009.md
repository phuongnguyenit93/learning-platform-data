# Comparator.min, max và hợp đồng thứ tự

Từ Java 26, java.util.Comparator có hai default method mới là min(U, U) và max(U, U). Chúng trả về một trong hai đối tượng đầu vào theo thứ tự do chính comparator xác định. Đây là API Java SE chính thức, không phải preview hoặc incubator. Điểm đáng chú ý là nếu comparator xem hai đối tượng bằng nhau (compare trả về 0), cả min và max đều trả về đối số thứ nhất.

Hai phương thức này hữu ích khi xử lý từng cặp giá trị, ví dụ chọn thời điểm sớm hơn hoặc muộn hơn, chọn phiên bản ưu tiên hơn, hoặc hợp nhất hai kết quả theo một quy tắc sắp thứ tự. Để dùng đúng, cần hiểu hợp đồng của compare, cách xử lý giá trị bằng nhau, null và quan hệ giữa thứ tự của comparator với equals.

## 1. Comparator định nghĩa thứ tự như thế nào?

Comparator<T> là một hàm so sánh hai đối tượng cùng miền kiểu. Phương thức compare(o1, o2) trả về:

- Số âm nếu o1 đứng trước o2 theo thứ tự comparator.
- Số 0 nếu comparator xem o1 và o2 tương đương về thứ tự.
- Số dương nếu o1 đứng sau o2.

Giá trị trả về không cần là -1, 0 hoặc 1. Chỉ dấu âm, bằng 0 hay dương mới có ý nghĩa theo hợp đồng.

Ví dụ:

~~~java
Comparator<String> byLength =
    Comparator.comparingInt(String::length);

System.out.println(byLength.compare("cat", "tiger")); // số âm
System.out.println(byLength.compare("dog", "ant"));   // 0
System.out.println(byLength.compare("elephant", "ox")); // số dương
~~~

Comparator không nhất thiết dùng thứ tự tự nhiên của đối tượng. Nó có thể so sánh theo một thuộc tính, nhiều thuộc tính, thứ tự đảo ngược hoặc quy tắc nghiệp vụ riêng.

Một comparator hợp lệ phải tạo ra một thứ tự nhất quán trên tập giá trị mà nó so sánh. Đây là điều kiện quan trọng khi dùng với sort, min/max, TreeSet, TreeMap và PriorityQueue.

## 2. Hợp đồng bắt buộc của compare

Java SE quy định ba điều kiện cốt lõi.

### 2.1. Tính đối xứng theo dấu

Với mọi x và y:

~~~java
signum(compare(x, y)) == -signum(compare(y, x))
~~~

Nếu x nhỏ hơn y thì y phải lớn hơn x. Nếu compare(x, y) bằng 0 thì compare(y, x) cũng phải bằng 0. Hai chiều cũng phải có hành vi ném exception tương ứng.

Không được viết comparator mà kết quả phụ thuộc vào thứ tự gọi một cách tùy tiện.

### 2.2. Tính bắc cầu

Nếu x lớn hơn y và y lớn hơn z thì x phải lớn hơn z:

~~~java
compare(x, y) > 0 && compare(y, z) > 0
    implies compare(x, z) > 0
~~~

Tương tự, nếu x nhỏ hơn y và y nhỏ hơn z thì x phải nhỏ hơn z. Nếu vi phạm tính bắc cầu, thuật toán sắp xếp hoặc cấu trúc dữ liệu dựa trên thứ tự có thể cho kết quả sai hoặc ném IllegalArgumentException.

### 2.3. Các phần tử bằng nhau theo comparator phải có quan hệ giống nhau với phần tử thứ ba

Nếu compare(x, y) == 0 thì với mọi z:

~~~java
signum(compare(x, z)) == signum(compare(y, z))
~~~

Nói cách khác, nếu comparator xem x và y là cùng một lớp tương đương về thứ tự, chúng phải có cùng vị trí tương đối với mọi phần tử khác. Điều này giúp thứ tự có tính nhất quán thay vì thay đổi tùy vào đối tượng được so sánh cùng.

## 3. compare == 0 không bắt buộc đồng nghĩa equals

Comparator thường được thiết kế sao cho:

~~~java
compare(x, y) == 0
~~~

có cùng kết quả với:

~~~java
x.equals(y)
~~~

Tuy nhiên, hợp đồng Comparator không bắt buộc hai điều kiện này phải tương đương. Một comparator có thể chỉ xét một phần dữ liệu.

Ví dụ:

~~~java
record User(String id, String displayName) { }

Comparator<User> byDisplayName =
    Comparator.comparing(User::displayName);
~~~

Hai User khác id nhưng có cùng displayName sẽ được comparator xem là bằng nhau về thứ tự, mặc dù equals của record trả về false.

Điều này có thể chấp nhận khi chỉ cần sắp xếp hoặc chọn một phần tử theo tên. Nhưng khi dùng comparator trong TreeSet hoặc TreeMap, compare == 0 được xem là cùng vị trí khóa/phần tử. Hai User khác nhau theo equals nhưng bằng nhau theo comparator có thể khiến TreeSet chỉ giữ một trong hai.

Nếu cần phân biệt từng User, thêm khóa phụ duy nhất:

~~~java
Comparator<User> byNameThenId =
    Comparator.comparing(User::displayName)
        .thenComparing(User::id);
~~~

Khi đó các user có cùng displayName vẫn được sắp thứ tự theo id. Hãy quyết định rõ comparator đang biểu diễn thứ tự hiển thị hay định danh duy nhất.

## 4. Comparator.min và Comparator.max từ Java 26

Java 26 thêm hai default method vào Comparator:

~~~java
default <U extends T> U min(U o1, U o2)
default <U extends T> U max(U o1, U o2)
~~~

Cách dùng:

~~~java
Comparator<Integer> order = Comparator.naturalOrder();

int smaller = order.min(12, 7); // 7
int greater = order.max(12, 7); // 12
~~~

Đây là phương thức instance trên một comparator đã được cấu hình. Không gọi như một static method trên Comparator.

Về mặt hành vi, implementation tương đương:

~~~java
// min
compare(o1, o2) <= 0 ? o1 : o2

// max
compare(o1, o2) >= 0 ? o1 : o2
~~~

Cả hai phương thức đều trả về một trong hai đối số ban đầu; không tạo bản sao và không biến đổi đối tượng.

### 4.1. Khi hai đối số bằng nhau theo comparator

Nếu compare(o1, o2) == 0:

- min trả về o1.
- max cũng trả về o1.

Đây là quy tắc API, không phải hành vi tình cờ của một implementation cụ thể.

Ví dụ:

~~~java
record Candidate(String id, int score) { }

Comparator<Candidate> byScore =
    Comparator.comparingInt(Candidate::score);

Candidate first = new Candidate("A", 90);
Candidate second = new Candidate("B", 90);

Candidate min = byScore.min(first, second);
Candidate max = byScore.max(first, second);

System.out.println(min.id()); // A
System.out.println(max.id()); // A
~~~

Comparator chỉ xét score nên hai candidate có cùng score. Cả min và max giữ đối số thứ nhất. Nếu nghiệp vụ yêu cầu chọn id nhỏ hơn khi điểm bằng nhau, phải thêm tie-breaker bằng thenComparing.

### 4.2. Kiểu trả về giữ subtype

Generic method dùng U extends T nên khi comparator được khai báo cho một kiểu cha, hai đối số cùng là subtype có thể được trả về dưới subtype đó.

~~~java
Comparator<CharSequence> byLength =
    Comparator.comparingInt(CharSequence::length);

String shorter = byLength.min("Java", "JDK");
~~~

Kết quả có kiểu String vì U được suy luận từ hai đối số, trong khi comparator có thể so sánh mọi CharSequence.

## 5. Chọn thời điểm sớm nhất hoặc muộn nhất

Comparator.min/max đặc biệt hữu ích với các giá trị thời gian. Instant có thứ tự tự nhiên theo timeline, vì vậy có thể dùng Comparator.naturalOrder hoặc so sánh theo trường Instant trong một record.

~~~java
import java.time.Instant;
import java.util.Comparator;

record Event(String id, Instant occurredAt) { }

public class EventSelection {
    private static final Comparator<Event> BY_TIME =
        Comparator.comparing(Event::occurredAt);

    static Event earlier(Event first, Event second) {
        return BY_TIME.min(first, second);
    }

    static Event later(Event first, Event second) {
        return BY_TIME.max(first, second);
    }
}
~~~

Nếu hai event có cùng Instant, comparator trên xem chúng tương đương về thứ tự. min/max trả event truyền ở vị trí đầu tiên. Nếu cần kết quả xác định độc lập với thứ tự đối số, thêm id làm khóa phụ:

~~~java
private static final Comparator<Event> BY_TIME_THEN_ID =
    Comparator.comparing(Event::occurredAt)
        .thenComparing(Event::id);
~~~

Điều này thường hữu ích với log, sự kiện, lịch sử giao dịch và bản ghi đồng bộ. Timestamp xác định thứ tự thời gian; id tạo thứ tự phụ ổn định khi nhiều bản ghi có cùng thời điểm.

## 6. Kết hợp nhiều khóa bằng thenComparing

Comparator có thể mô tả thứ tự từ khóa ưu tiên cao đến khóa phụ:

~~~java
record Task(
    int priority,
    Instant deadline,
    String id
) { }

Comparator<Task> taskOrder =
    Comparator.comparingInt(Task::priority)
        .thenComparing(Task::deadline)
        .thenComparing(Task::id);
~~~

Trong ví dụ, priority nhỏ hơn được xếp trước; nếu bằng nhau thì deadline sớm hơn được xếp trước; nếu cả hai vẫn bằng nhau thì id được dùng.

Sau đó có thể chọn giữa hai task:

~~~java
Task preferred = taskOrder.min(taskA, taskB);
Task lessPreferred = taskOrder.max(taskA, taskB);
~~~

Hãy đọc min/max theo thứ tự comparator, không theo cách diễn đạt mơ hồ như "ưu tiên cao nhất". Nếu priority 1 là mức cao nhất, comparator tự nhiên tăng dần sẽ làm min trả task có priority 1. Nếu quy ước số lớn hơn là ưu tiên cao hơn, cần dùng comparator tương ứng hoặc reversed.

## 7. Phân biệt Comparator.min/max với Collections và Stream

Các API có tên gần nhau nhưng phạm vi khác nhau:

| API | Đầu vào | Kết quả | Mục đích |
|---|---|---|---|
| Comparator.min(o1, o2) | Hai giá trị | Một trong hai giá trị | Chọn nhỏ hơn theo comparator |
| Comparator.max(o1, o2) | Hai giá trị | Một trong hai giá trị | Chọn lớn hơn theo comparator |
| Collections.min(collection, comparator) | Collection | Phần tử nhỏ nhất | Tìm min trên toàn collection |
| Collections.max(collection, comparator) | Collection | Phần tử lớn nhất | Tìm max trên toàn collection |
| Stream.min(comparator) | Stream | Optional<T> | Tìm min trong stream |
| Stream.max(comparator) | Stream | Optional<T> | Tìm max trong stream |
| BinaryOperator.minBy(comparator) | Comparator | BinaryOperator<T> | Tạo hàm chọn min để dùng trong reduce/merge |
| BinaryOperator.maxBy(comparator) | Comparator | BinaryOperator<T> | Tạo hàm chọn max để dùng trong reduce/merge |

Ví dụ với hai phần tử:

~~~java
String smaller = byLength.min("pear", "fig");
~~~

Ví dụ với collection:

~~~java
List<String> words = List.of("pear", "fig", "watermelon");

String shortest = Collections.min(words, byLength);
String longest = Collections.max(words, byLength);
~~~

Ví dụ với stream:

~~~java
Optional<String> shortest =
    words.stream().min(byLength);
~~~

Comparator.min/max không thay thế Collections.min/max hoặc Stream.min/max. Chúng bổ sung thao tác chọn giữa đúng hai đối số, hữu ích trong reduce thủ công, hợp nhất hai kết quả hoặc xử lý cặp giá trị.

## 8. Xử lý null một cách tường minh

Comparator.naturalOrder() và Comparator.reverseOrder() không chấp nhận null. Nếu có thể nhận null, cần chọn chính sách:

~~~java
Comparator<String> nullFirst =
    Comparator.nullsFirst(Comparator.naturalOrder());

Comparator<String> nullLast =
    Comparator.nullsLast(Comparator.naturalOrder());
~~~

Với nullFirst, null được xem là nhỏ hơn mọi giá trị không null. Vì vậy:

~~~java
String min = nullFirst.min(null, "Java"); // null
String max = nullFirst.max(null, "Java"); // "Java"
~~~

Với nullLast, null được xem là lớn hơn mọi giá trị không null; kết quả min/max sẽ đảo theo chính sách đó.

Một chi tiết dễ bỏ qua: nullsFirst(null) hoặc nullsLast(null) không có comparator cho các giá trị khác null. Theo hợp đồng, trong trường hợp comparator bên trong là null, tất cả giá trị không null được xem là bằng nhau. Không dùng cách này nếu muốn sắp thứ tự các giá trị thông thường; hãy truyền comparator thật.

Nếu null không phải giá trị hợp lệ trong miền nghiệp vụ, nên kiểm tra đầu vào và từ chối null thay vì âm thầm gán nó vào đầu hoặc cuối thứ tự.

## 9. Đảo thứ tự và quan hệ giữa min/max

reversed() trả về comparator có thứ tự ngược. Vì vậy, với hai giá trị không có tie:

~~~java
Comparator<Integer> ascending =
    Comparator.naturalOrder();

Comparator<Integer> descending =
    ascending.reversed();

ascending.min(3, 8);  // 3
descending.min(3, 8); // 8

ascending.max(3, 8);  // 8
descending.max(3, 8); // 3
~~~

Về mặt ý nghĩa:

- min của comparator đảo thứ tự tương đương max của comparator ban đầu.
- max của comparator đảo thứ tự tương đương min của comparator ban đầu.

Khi comparator xem hai đối số bằng nhau, quy tắc trả đối số thứ nhất vẫn áp dụng cho cả hai comparator. reversed không tạo tie-breaker mới.

## 10. Tránh comparator sai do phép trừ

Không viết comparator số nguyên bằng cách lấy hiệu:

~~~java
Comparator<Integer> wrong = (a, b) -> a - b;
~~~

Nếu a và b ở gần hai đầu miền int, phép trừ có thể overflow và làm dấu kết quả đảo ngược. Điều đó phá vỡ hợp đồng thứ tự.

Dùng:

~~~java
Comparator<Integer> correct = Integer::compare;
Comparator<Long> byLong = Long::compare;
~~~

Khi so sánh field số trong object, dùng comparingInt hoặc comparingLong:

~~~java
Comparator<Task> byPriority =
    Comparator.comparingInt(Task::priority);

Comparator<Event> byEpochSecond =
    Comparator.comparingLong(
        event -> event.occurredAt().getEpochSecond()
    );
~~~

Cách này diễn đạt rõ khóa so sánh và tránh phép trừ dễ overflow.

## 11. Comparator không nên phụ thuộc trạng thái thay đổi

Comparator nên cho cùng kết quả khi so sánh cùng một cặp giá trị trong suốt thời gian một thao tác sắp xếp hoặc khi các phần tử nằm trong sorted collection.

Tránh các mẫu:

- Đọc thời gian hiện tại trong compare để quyết định thứ tự.
- Dựa vào bộ đếm tăng dần hoặc số ngẫu nhiên.
- So sánh theo field mutable có thể thay đổi trong lúc phần tử đang nằm trong TreeSet hoặc TreeMap.
- Gọi dịch vụ mạng hoặc truy vấn database trong compare.
- Dùng locale hoặc cấu hình có thể đổi giữa một lần sort mà không cố định snapshot.

Ví dụ không nên dùng:

~~~java
Comparator<Job> unstable =
    Comparator.comparing(job ->
        Instant.now().isAfter(job.deadline())
    );
~~~

Kết quả so sánh thay đổi theo thời gian. Một cấu trúc dữ liệu đã được sắp theo comparator này có thể mất invariant khi thời gian trôi qua.

Hãy tính trước khóa cần so sánh và dùng giá trị bất biến trong suốt vòng đời sắp xếp:

~~~java
record ScheduledJob(String id, Instant deadline) { }

Comparator<ScheduledJob> stable =
    Comparator.comparing(ScheduledJob::deadline)
        .thenComparing(ScheduledJob::id);
~~~

## 12. Kiểm thử hợp đồng comparator

Unit test chỉ kiểm tra một vài cặp cụ thể có thể bỏ sót lỗi bắc cầu hoặc lỗi khi có giá trị bằng nhau. Với comparator nghiệp vụ, nên kiểm tra các tính chất trên tập dữ liệu mẫu có biên và dữ liệu trùng khóa.

Ví dụ kiểm tra dấu đối xứng và bắc cầu:

~~~java
static <T> void assertComparatorContract(
        Comparator<T> comparator,
        List<T> values) {

    for (T x : values) {
        for (T y : values) {
            int xy = Integer.signum(comparator.compare(x, y));
            int yx = Integer.signum(comparator.compare(y, x));

            if (xy != -yx) {
                throw new AssertionError("Sign symmetry violated");
            }

            for (T z : values) {
                int yz = comparator.compare(y, z);
                int xz = comparator.compare(x, z);

                if (comparator.compare(x, y) > 0 && yz > 0 && xz <= 0) {
                    throw new AssertionError("Transitivity violated");
                }

                if (comparator.compare(x, y) == 0 &&
                        Integer.signum(xz) !=
                        Integer.signum(comparator.compare(y, z))) {
                    throw new AssertionError(
                        "Equivalent elements compare differently to a third element"
                    );
                }
            }
        }
    }
}
~~~

Đoạn test trên kiểm tra cả ba điều kiện cốt lõi trên tập mẫu hữu hạn. Bộ dữ liệu nên chứa:

- Giá trị nhỏ nhất/lớn nhất của kiểu số.
- Các khóa bằng nhau nhưng object khác nhau.
- Null nếu comparator cho phép.
- Chuỗi khác chữ hoa/chữ thường nếu dùng comparator không phân biệt case.
- Các thời điểm trùng nhau nhưng id khác nhau.
- Giá trị biên của quy tắc nghiệp vụ.

Ngoài kiểm tra contract, test riêng hành vi tie của Comparator.min/max:

~~~java
Comparator<String> byLength =
    Comparator.comparingInt(String::length);

String first = new String("cat");
String second = new String("dog");

if (byLength.min(first, second) != first) {
    throw new AssertionError("min must return the first argument on a tie");
}
if (byLength.max(first, second) != first) {
    throw new AssertionError("max must return the first argument on a tie");
}
~~~

Hai chuỗi khác object identity nhưng cùng độ dài, nên comparator xem chúng bằng nhau và cả hai method trả đúng đối số đầu tiên.

## 13. Tương thích phiên bản và migration

Comparator.min và Comparator.max được thêm vào interface java.util.Comparator trong JDK 26 dưới dạng default methods. Chúng là API Java SE ổn định, không cần --enable-preview và không cần module bổ sung.

| Môi trường | Có thể gọi Comparator.min/max? |
|---|---|
| JDK 25 trở xuống | Không, API chưa tồn tại |
| JDK 26 trở lên | Có |
| JDK 26 biên dịch với --release 25 | Không, API bị giới hạn theo release target |
| JDK 26 với --release 26 | Có, không cần preview flag |

Các method này tiếp tục có trong API JDK 27. Đây là thay đổi tương thích của interface: khi một lớp hoặc interface khác đã khai báo default method cùng chữ ký, compiler có thể yêu cầu lớp triển khai override để giải quyết xung đột default method. Nếu thư viện đa ngôn ngữ hoặc framework có interface kế thừa nhiều nguồn, hãy biên dịch lại và xử lý xung đột chữ ký khi nâng lên JDK 26.

Ví dụ biên dịch:

~~~sh
javac --release 26 ComparatorMinMaxDemo.java
java ComparatorMinMaxDemo
~~~

Nếu thư viện phải hỗ trợ JDK 25 trở xuống, không gọi trực tiếp các method mới trong bytecode chung. Có thể giữ helper tương thích:

~~~java
static <T> T min(
        Comparator<? super T> comparator,
        T first,
        T second) {
    return comparator.compare(first, second) <= 0
        ? first
        : second;
}
~~~

Helper này thể hiện cùng quy tắc tie trả first. Nếu chỉ hỗ trợ JDK 26 trở lên, ưu tiên method chuẩn của Comparator để code thống nhất và dễ đọc.

## 14. Lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Gọi Comparator.min(a, b) như static method | Không đúng chữ ký API | Gọi comparator.min(a, b) |
| Nghĩ min/max tìm trong cả collection | Chỉ so sánh đúng hai đối số | Dùng Collections.min/max hoặc Stream.min/max cho collection |
| Nghĩ tie trả object bằng equals | Tie được xác định bằng compare == 0 | Thêm thenComparing nếu cần tie-break |
| Comparator chỉ xét tên nhưng dùng làm TreeSet key | Phần tử khác nhau theo equals có thể bị xem là trùng | Thêm khóa phụ hoặc ghi rõ ordering không consistent with equals |
| Comparator dùng phép trừ int/long | Overflow có thể đảo thứ tự | Dùng Integer.compare, Long.compare hoặc comparingInt/Long |
| Comparator không bắc cầu | Sort hoặc sorted collection hoạt động sai | Sửa quy tắc so sánh và kiểm thử contract |
| Không định nghĩa null policy | Có thể gặp NullPointerException | Dùng nullsFirst/nullsLast hoặc từ chối null sớm |
| Comparator phụ thuộc dữ liệu mutable | Thứ tự thay đổi khi phần tử đã được lưu trong cấu trúc có thứ tự | So sánh theo khóa bất biến |
| Dùng min/max để quyết định nghiệp vụ nhưng comparator thiếu tie-break | Kết quả có thể phụ thuộc thứ tự đối số | Bổ sung khóa phụ xác định |
| Dùng API trên JDK 25 | Không biên dịch hoặc không liên kết được | Nâng target lên JDK 26 hoặc dùng helper tương thích |

## 15. Checklist áp dụng

- [ ] Xác định rõ comparator đang biểu diễn thứ tự nào.
- [ ] Đảm bảo dấu đối xứng, tính bắc cầu và quy tắc compare == 0.
- [ ] Quyết định có cần consistent with equals hay không.
- [ ] Nếu dùng TreeSet/TreeMap, hiểu rằng compare == 0 xác định phần tử/khóa trùng theo comparator.
- [ ] Dùng Comparator.min/max cho đúng hai giá trị.
- [ ] Nhớ tie trả về đối số thứ nhất ở cả min và max.
- [ ] Thêm thenComparing khi cần kết quả xác định giữa các phần tử trùng khóa chính.
- [ ] Chọn nullsFirst/nullsLast hoặc từ chối null rõ ràng.
- [ ] Dùng Integer.compare/Long.compare/comparingInt/comparingLong thay phép trừ.
- [ ] Không để comparator phụ thuộc thời gian, random, side effect hoặc trạng thái mutable.
- [ ] Dùng Collections.min/max hoặc Stream.min/max khi cần tìm trên toàn bộ collection.
- [ ] Xác nhận JDK target là 26 trở lên trước khi gọi hai method mới.

## Tài liệu tham khảo

- [Java SE 26 — Comparator API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html): chữ ký min/max, tie trả đối số đầu tiên, null behavior và hợp đồng compare.
- [Java SE 27 — Comparator API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Comparator.html): xác nhận min/max tiếp tục có trong JDK 27.
- [JDK 26 Release Notes — New default methods min(T, T) and max(T, T) in Comparator](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): xác nhận hai default method mới trong JDK 26, JDK-8356995.
- [Java SE 26 — Collections API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html): min/max trên collection và hành vi khi collection rỗng.
- [Java SE 26 — Stream API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): min/max trên stream và kết quả Optional.
- [Java SE 26 — TreeSet API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeSet.html): cách comparator xác định thứ tự và tính duy nhất của phần tử trong sorted set.
- [Java SE 26 — Comparator New API List](https://docs.oracle.com/en/java/javase/26/docs/api/new-list.html): xác nhận Comparator.min và Comparator.max được thêm ở release 26.

