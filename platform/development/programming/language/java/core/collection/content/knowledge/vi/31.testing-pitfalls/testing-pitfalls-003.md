# Kiểm thử thứ tự chèn, thứ tự sắp xếp và thứ tự ưu tiên

## 1. “Đúng phần tử” chưa chắc đã “đúng thứ tự”

Một kết quả chứa đủ `A`, `B`, `C` vẫn có thể sai nếu người gọi cần nhận `B`, `A`, `C`. Ngược lại, một kiểm thử ép thứ tự `A`, `B`, `C` có thể sai nếu collection không hứa thứ tự đó.

Khi kiểm thử collection, cần phân biệt ba ý nghĩa:

- **Thứ tự chèn (insertion order):** thứ tự các phần tử hoặc khóa được thêm vào, theo quy tắc của cấu trúc.
- **Thứ tự sắp xếp (sorted order):** thứ tự do `Comparable` hoặc `Comparator` quyết định.
- **Thứ tự ưu tiên (priority order):** thứ tự lấy phần tử ra từ hàng đợi theo quy tắc ưu tiên.

Với dữ liệu chèn lần lượt `30`, `10`, `20`:

| Cấu trúc và hành động quan sát | Thứ tự cần kỳ vọng |
| --- | --- |
| Duyệt `LinkedHashSet` | `30, 10, 20` |
| Duyệt `TreeSet<Integer>` dùng thứ tự tự nhiên | `10, 20, 30` |
| Liên tục `poll()` trên `PriorityQueue<Integer>` dùng thứ tự tự nhiên | `10, 20, 30` |
| Duyệt `PriorityQueue` bằng iterator | Không có bảo đảm duyệt thành dãy đã sắp xếp |

Hai dòng cuối đặc biệt dễ bị nhầm. `PriorityQueue` bảo đảm lựa chọn phần tử đầu hàng đợi theo thứ tự ưu tiên; nó không biến mọi cách quan sát nội dung thành một dãy đã sắp xếp.

Mục tiêu kiểm thử là bảo vệ **thứ tự tại đúng điểm quan sát mà API hoặc nghiệp vụ cam kết**, đồng thời kiểm tra đủ phần tử và số lần xuất hiện.

## 2. Xác định hợp đồng trước khi chọn assertion

Một yêu cầu như “trả kết quả theo đúng thứ tự” còn thiếu thông tin. Cần làm rõ:

1. Thứ tự của phần tử, của khóa hay của giá trị?
2. Quan sát qua iterator, danh sách đầu ra hay chuỗi lấy-xóa phần tử?
3. Tăng dần hay giảm dần theo thuộc tính nào?
4. Nếu hai phần tử ngang nhau, có quy tắc phụ không?
5. Thêm lại, cập nhật hoặc truy cập một phần tử có làm đổi vị trí không?
6. Việc kiểm tra có được tiêu thụ cấu trúc nguồn không?

Ví dụ hai hợp đồng hàng đợi khác nhau:

```text
Hợp đồng A:
    số priority lớn hơn được xử lý trước;
    các việc có cùng priority được lấy theo thứ tự bất kỳ.

Hợp đồng B:
    số priority lớn hơn được xử lý trước;
    nếu bằng priority thì việc được đưa vào sớm hơn được xử lý trước.
```

Không được dùng assertion yêu cầu thứ tự cụ thể giữa các việc đồng hạng khi chỉ có hợp đồng A. Với hợp đồng B, phải có một cơ chế thể hiện thứ tự đưa vào và phải kiểm tra nó.

Trong các ví dụ của bài, `priority` càng lớn nghĩa là càng ưu tiên. Đây là lựa chọn nghiệp vụ của ví dụ, không phải cách Java tự diễn giải một trường có tên `priority`.

## 3. Kiểm thử thứ tự chèn

### 3.1. Chọn đầu vào có thể phân biệt thứ tự chèn với thứ tự sắp xếp

Nếu luôn chèn `A`, `B`, `C`, một cấu trúc vô tình sắp xếp tăng dần vẫn trả đúng dãy mong đợi. Hãy dùng dữ liệu như `B`, `A`, `C`.

Với `LinkedHashMap` theo thứ tự chèn mặc định:

```text
put(B, 2)
put(A, 1)
put(C, 3)

Thứ tự duyệt khóa mong đợi: B, A, C
```

Thay giá trị của khóa `A` đang tồn tại không chuyển khóa đó xuống cuối. Nhưng xóa khóa rồi thêm lại là một chuỗi thao tác khác: khóa được thêm mới ở cuối. [Tài liệu LinkedHashMap của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

Vì vậy nên có những ca phân biệt:

| Hành động sau khi có `B, A, C` | Thứ tự khóa mong đợi trong chế độ insertion-order |
| --- | --- |
| `put(A, giá_trị_mới)` | `B, A, C` |
| `get(B)` | `B, A, C` |
| `remove(A)`, rồi `put(A, ...)` | `B, C, A` |
| Thêm khóa `D` | `B, A, C, D` |

Kết quả kiểm thử phải theo đúng trạng thái trước từng ca. Tạo dữ liệu riêng hoặc khởi tạo lại khi các ca không được thiết kế để nối tiếp nhau.

### 3.2. LinkedHashSet: thêm trùng không phải xóa rồi thêm lại

Với `LinkedHashSet`, thêm một phần tử đã tồn tại không thay đổi thứ tự. Nguồn `B, A, B, C` tạo thứ tự duyệt `B, A, C`. Nếu xóa `A` rồi thêm lại, thứ tự trở thành `B, C, A`. [Tài liệu LinkedHashSet của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

Một ca chỉ so sánh tập giá trị không phát hiện được lỗi thứ tự này. Cần thu thứ tự duyệt thành `List` để so sánh.

### 3.3. Access-order là một chế độ khác

`LinkedHashMap` có constructor bật thứ tự truy cập:

```java
Map<String, Integer> cache = new LinkedHashMap<>(16, 0.75f, true);
```

Đây là đoạn minh họa cần import `java.util.Map` và `java.util.LinkedHashMap`. Với chế độ này, một lần `get` thành công có thể đưa mục được truy cập về phía được truy cập gần nhất. Ví dụ sau khi chèn `B, A, C`, gọi `get(B)` cho thứ tự duyệt `A, C, B`.

Không áp kỳ vọng của insertion-order cho một map được tạo ở chế độ access-order. Khi kiểm thử cấu trúc dùng làm cache, còn phải để ý rằng một lệnh đọc để “kiểm tra giá trị” có thể thay đổi trạng thái thứ tự trước assertion tiếp theo.

## 4. Kiểm thử thứ tự sắp xếp

### 4.1. TreeSet và TreeMap dựa trên quy tắc so sánh

`TreeSet` duyệt theo thứ tự tự nhiên hoặc comparator được cấu hình. `TreeMap` sắp xếp theo **khóa**, không tự sắp xếp theo giá trị. [Tài liệu TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html), [tài liệu TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

Một ca có khả năng phân biệt tốt:

```text
Các ánh xạ được đưa vào:
    B -> 2
    A -> 3
    C -> 1

Duyệt TreeMap theo khóa tự nhiên:
    khóa:    A, B, C
    giá trị: 3, 2, 1
```

Nếu chỉ dùng `A->1`, `B->2`, `C->3`, ta khó phát hiện nhầm lẫn giữa “sắp theo khóa” và “sắp theo giá trị”.

Các ca nên có đầu vào đã tăng, đã giảm và trộn thứ tự, nhưng kỳ vọng phải cùng tuân theo comparator. Không cần giữ thứ tự chèn trong cấu trúc đã cam kết sắp xếp.

### 4.2. Kiểm tra hướng so sánh và quy tắc phụ

Với số nguyên dùng thứ tự tự nhiên, tăng dần thường là điều mong đợi. Với cấu trúc dùng `Comparator.reverseOrder()`, thứ tự mong đợi đổi thành giảm dần.

Đối với đối tượng nghiệp vụ, nên có ít nhất:

- Hai phần tử khác nhau ở thuộc tính chính.
- Hai phần tử bằng nhau ở thuộc tính chính nhưng khác ở thuộc tính phụ.
- Các giá trị biên có ý nghĩa, nếu comparator xử lý số hoặc dữ liệu đặc biệt.

Không viết comparator số bằng phép trừ như `a.priority() - b.priority()`. Hiệu có thể tràn số nguyên và làm sai dấu so sánh. Dùng `Integer.compare`, `Comparator.comparingInt` hoặc hàm kết hợp phù hợp. API `Comparator` cung cấp các cách xây dựng, đảo và nối quy tắc so sánh. [Tài liệu Comparator của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)

### 4.3. compare bằng 0 có ý nghĩa đặc biệt với cấu trúc cây

`TreeSet` dùng kết quả so sánh để nhận diện phần tử cùng vị trí trong tập. Nếu comparator chỉ so độ dài chuỗi, `"AA"` và `"BB"` so sánh bằng `0`; tập có thể chỉ giữ một trong hai dù `String.equals()` trả false.

Điều đó có thể làm bộ kiểm thử thất bại không phải vì dãy bị sắp sai, mà vì đã mất phần tử theo một hợp đồng không phù hợp. Kiểm tra cả số lượng và nội dung, không chỉ tính tăng dần.

Đối với tập hợp/map sắp xếp cần tuân theo hợp đồng `Set`/`Map` thông thường, quy tắc thứ tự phải nhất quán với `equals`. Nếu bài toán muốn giữ nhiều đối tượng khác nhau cùng giá trị thuộc tính chính, có thể cần một quy tắc phụ đủ phân biệt hoặc một cấu trúc khác như danh sách được sắp xếp.

### 4.4. Tính ổn định của List.sort không tự truyền sang hàng đợi

`List.sort` có bảo đảm sắp xếp ổn định: các phần tử so sánh bằng nhau giữ thứ tự tương đối trước khi sắp. [Tài liệu List.sort của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator))

Ví dụ `B` và `C` cùng priority, với `B` đứng trước `C` trong danh sách nguồn. Sắp xếp ổn định chỉ theo priority giữ thứ tự tương đối đó.

Đây là bảo đảm của phép sắp xếp danh sách, không phải lý do để giả định `PriorityQueue` cũng xử lý các phần tử đồng hạng theo thứ tự chèn. Mỗi cấu trúc cần được kiểm thử theo bảo đảm riêng.

## 5. Kiểm thử thứ tự ưu tiên bằng chuỗi lấy phần tử

### 5.1. Phần tử nhỏ nhất theo comparator được lấy trước

Trong `PriorityQueue`, phần tử ở đầu là phần tử nhỏ nhất theo thứ tự tự nhiên hoặc comparator cấu hình. Nếu có nhiều phần tử đồng hạng ở đầu, hàng đợi không hứa chọn theo thứ tự chèn. Iterator không được bảo đảm duyệt theo thứ tự ưu tiên. [Tài liệu PriorityQueue của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

Với số nguyên và thứ tự tự nhiên:

```text
Chèn: 30, 10, 20, 10
poll liên tục: 10, 10, 20, 30
```

Với quy ước “số priority lớn hơn làm trước”, comparator cần đảo chiều của thuộc tính đó:

```java
Comparator<Job> byPriority = Comparator.comparingInt(Job::priority).reversed();
```

Đây là đoạn minh họa dùng kiểu `Job` trong chương trình đầy đủ bên dưới. Giá trị priority lớn trở thành phần tử “nhỏ hơn” theo comparator đã đảo, nên được lấy trước.

### 5.2. Không kiểm thử bằng thứ tự iterator của heap

Các cách sau chỉ lấy thứ tự duyệt nội bộ, không biểu diễn chuỗi lấy phần tử ưu tiên:

```java
new ArrayList<>(queue);
queue.toArray();
queue.stream().toList();
```

Chúng là những đoạn biểu thức minh họa, không phải assertion đúng cho thứ tự `poll()`. Kể cả khi một lần chạy cho ra dãy có vẻ đã sắp xếp, không biến quan sát đó thành bảo đảm API.

Nếu cần kiểm tra quá trình lấy việc ra, hãy thực sự lấy ra theo thao tác mà sản phẩm dùng. Nếu chỉ cần trình bày một bản sắp xếp của các giá trị, đó là một mục tiêu khác và nên được mô tả riêng.

### 5.3. Kiểm tra bằng bản sao để giữ nguyên hàng đợi nguồn

`poll()` xóa phần tử, nên một hàm trợ giúp cho kiểm thử có thể tạo bản sao của `PriorityQueue` rồi rút hết từ bản sao. Constructor nhận `PriorityQueue` giữ cùng quy tắc sắp xếp của nguồn.

```java
static <E> List<E> pollOrder(PriorityQueue<E> source) {
    PriorityQueue<E> copy = new PriorityQueue<>(source);
    List<E> result = new ArrayList<>();
    while (!copy.isEmpty()) {
        result.add(copy.poll());
    }
    return result;
}
```

Đoạn phương thức này cần các import tương ứng như chương trình đầy đủ. Nó dùng cho trường hợp không có sửa đổi đồng thời và phần tử không đổi thuộc tính so sánh trong lúc kiểm tra.

Bản sao giữ các tham chiếu phần tử; nó không sao chép sâu đối tượng. Không sửa priority bên trong một đối tượng rồi kỳ vọng hàng đợi tự định vị lại đối tượng đó. Ví dụ trong bài dùng record bất biến về các trường so sánh để tránh làm hỏng giả định này.

## 6. Phần tử đồng hạng: hai chiến lược assertion

### 6.1. Không yêu cầu thứ tự phụ: kiểm tra đúng mức bảo đảm

Giả sử `B` và `C` cùng priority `5`, `A` và `E` cùng priority `2`, còn `D` có priority `1`. Nếu hợp đồng chỉ có priority giảm dần, các chuỗi sau đều hợp lệ:

```text
B, C, A, E, D
C, B, E, A, D
```

Một cách kiểm tra gồm hai điều kiện:

1. Các phần tử lấy liên tiếp không đảo thứ tự theo comparator.
2. Tập các phần tử kèm số lần xuất hiện bằng đúng đầu vào.

Chỉ kiểm tra điều kiện thứ nhất không phát hiện việc thiếu phần tử. Chỉ chuyển sang `Set` để kiểm tra điều kiện thứ hai có thể làm mất thông tin phần tử trùng. Một map đếm số lần xuất hiện phù hợp khi phép bằng nhau của phần tử phản ánh đúng danh tính cần kiểm thử.

Có thể kiểm tra dãy priority là `[5, 5, 2, 2, 1]` và kiểm tra riêng đủ các việc; không ép thứ tự ID giữa những việc đồng hạng.

### 6.2. Cần xử lý đồng hạng theo thứ tự đưa vào: đưa thứ tự đó vào comparator

Có thể gắn số thứ tự tăng dần khi đưa việc vào:

```java
Comparator<Job> byPriorityThenSequence =
        Comparator.comparingInt(Job::priority).reversed()
                .thenComparingLong(Job::sequence);
```

Comparator này có hai quy tắc:

1. Priority giảm dần.
2. Nếu bằng priority, sequence tăng dần.

Để biểu đạt thứ tự đưa vào, sequence phải được gán theo đúng thời điểm/điểm điều phối đưa việc vào và đủ phân biệt trong phạm vi hàng đợi. Đừng dùng sequence trùng rồi vẫn hứa một thứ tự hoàn toàn xác định. Việc cấp sequence khi có nhiều luồng là yêu cầu thiết kế riêng; ví dụ ở đây chỉ xử lý dữ liệu trong một luồng.

Chú ý vị trí gọi `reversed()`:

```java
Comparator.comparingInt(Job::priority).reversed()
        .thenComparingLong(Job::sequence);
```

khác với đảo toàn bộ comparator sau khi đã nối sequence. Đảo toàn bộ sẽ đảo cả hướng của quy tắc phụ. Kiểm thử với nhiều phần tử cùng priority giúp phát hiện lỗi này.

## 7. Chương trình Java 17+ kiểm tra cả ba loại thứ tự

Chương trình dùng các hàm tự kiểm tra có ném `AssertionError` khi sai. Không cần thư viện ngoài và không cần bật `-ea`.

Lưu thành `CollectionOrderDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class CollectionOrderDemo {
    record Job(String id, int priority, long sequence) { }

    private static int passed;

    private static void checkEquals(String label, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        passed++;
    }

    private static <E> List<E> pollOrder(PriorityQueue<E> source) {
        PriorityQueue<E> copy = new PriorityQueue<>(source);
        List<E> result = new ArrayList<>();
        while (!copy.isEmpty()) {
            result.add(copy.poll());
        }
        return result;
    }

    private static <E> Map<E, Integer> frequencies(Collection<E> values) {
        Map<E, Integer> counts = new HashMap<>();
        for (E value : values) {
            counts.merge(value, 1, Integer::sum);
        }
        return counts;
    }

    private static <E> boolean isOrdered(List<E> values, Comparator<? super E> order) {
        for (int i = 1; i < values.size(); i++) {
            if (order.compare(values.get(i - 1), values.get(i)) > 0) {
                return false;
            }
        }
        return true;
    }

    private static List<String> ids(List<Job> jobs) {
        return jobs.stream().map(Job::id).toList();
    }

    public static void main(String[] args) {
        Map<String, Integer> insertion = new LinkedHashMap<>();
        insertion.put("B", 2);
        insertion.put("A", 1);
        insertion.put("C", 3);
        checkEquals("insertion order", List.of("B", "A", "C"),
                new ArrayList<>(insertion.keySet()));
        System.out.println("insertion keys = " + new ArrayList<>(insertion.keySet()));
        insertion.put("A", 10);
        checkEquals("updating existing key keeps insertion position",
                List.of("B", "A", "C"), new ArrayList<>(insertion.keySet()));
        insertion.remove("A");
        insertion.put("A", 20);
        checkEquals("remove then insert appends key", List.of("B", "C", "A"),
                new ArrayList<>(insertion.keySet()));

        Map<String, Integer> access = new LinkedHashMap<>(16, 0.75f, true);
        access.put("B", 2);
        access.put("A", 1);
        access.put("C", 3);
        access.get("B");
        checkEquals("access order after get", List.of("A", "C", "B"),
                new ArrayList<>(access.keySet()));

        Set<String> insertionSet = new LinkedHashSet<>(List.of("B", "A", "B", "C"));
        checkEquals("set duplicate does not move value", List.of("B", "A", "C"),
                new ArrayList<>(insertionSet));
        insertionSet.remove("A");
        insertionSet.add("A");
        checkEquals("set remove and reinsert", List.of("B", "C", "A"),
                new ArrayList<>(insertionSet));

        Set<String> sortedSet = new TreeSet<>(List.of("B", "A", "B", "C"));
        checkEquals("natural sorted set", List.of("A", "B", "C"),
                new ArrayList<>(sortedSet));
        Set<String> descendingSet = new TreeSet<>(Comparator.reverseOrder());
        descendingSet.addAll(List.of("B", "A", "C"));
        checkEquals("reverse sorted set", List.of("C", "B", "A"),
                new ArrayList<>(descendingSet));

        Map<String, Integer> sortedMap = new TreeMap<>();
        sortedMap.put("B", 2);
        sortedMap.put("A", 3);
        sortedMap.put("C", 1);
        checkEquals("map sorted by keys", List.of("A", "B", "C"),
                new ArrayList<>(sortedMap.keySet()));
        checkEquals("values follow keys, not value sorting", List.of(3, 2, 1),
                new ArrayList<>(sortedMap.values()));
        System.out.println("sorted keys = " + new ArrayList<>(sortedMap.keySet()));

        PriorityQueue<Integer> numbers = new PriorityQueue<>(List.of(30, 10, 20, 10));
        List<Integer> numberOrder = pollOrder(numbers);
        checkEquals("natural priority order with duplicate", List.of(10, 10, 20, 30),
                numberOrder);
        checkEquals("peek reads first priority", 10, numbers.peek());
        checkEquals("copy leaves source size unchanged", 4, numbers.size());
        System.out.println("priority values = " + numberOrder);

        List<Job> jobs = List.of(
                new Job("A", 2, 0),
                new Job("B", 5, 1),
                new Job("C", 5, 2),
                new Job("D", 1, 3),
                new Job("E", 2, 4));
        Comparator<Job> byPriority = Comparator.comparingInt(Job::priority).reversed();
        List<Job> stableSorted = new ArrayList<>(jobs);
        stableSorted.sort(byPriority);
        checkEquals("stable list sorting", List.of("B", "C", "A", "E", "D"),
                ids(stableSorted));

        PriorityQueue<Job> priorityOnly = new PriorityQueue<>(byPriority);
        priorityOnly.addAll(jobs);
        List<Job> priorityResult = pollOrder(priorityOnly);
        List<Integer> levels = priorityResult.stream().map(Job::priority).toList();
        checkEquals("priority levels", List.of(5, 5, 2, 2, 1), levels);
        checkEquals("all jobs preserved", frequencies(jobs), frequencies(priorityResult));
        checkEquals("ordered under comparator", true, isOrdered(priorityResult, byPriority));
        System.out.println("priority-only levels = " + levels);

        Comparator<Job> withSequence = byPriority.thenComparingLong(Job::sequence);
        PriorityQueue<Job> deterministic = new PriorityQueue<>(withSequence);
        deterministic.addAll(jobs);
        List<Job> exactOrder = pollOrder(deterministic);
        checkEquals("priority then sequence", List.of("B", "C", "A", "E", "D"),
                ids(exactOrder));
        checkEquals("job source queue not consumed", jobs.size(), deterministic.size());
        System.out.println("priority with sequence = " + ids(exactOrder));

        PriorityQueue<Integer> empty = new PriorityQueue<>();
        checkEquals("empty queue output", List.of(), pollOrder(empty));
        checkEquals("empty peek", null, empty.peek());
        PriorityQueue<Integer> singleton = new PriorityQueue<>(List.of(7));
        checkEquals("singleton queue output", List.of(7), pollOrder(singleton));

        System.out.println("PASS: " + passed + " checks");
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CollectionOrderDemo.java
java CollectionOrderDemo
```

Stdout khi các kiểm tra đạt:

```text
insertion keys = [B, A, C]
sorted keys = [A, B, C]
priority values = [10, 10, 20, 30]
priority-only levels = [5, 5, 2, 2, 1]
priority with sequence = [B, C, A, E, D]
PASS: 22 checks
```

Chương trình cố ý không in hoặc kiểm tra thứ tự ID của `priorityOnly` khi đồng hạng, vì hợp đồng của comparator đó không xác định thứ tự này. Nó vẫn kiểm tra dãy priority, tính không đảo thứ tự và số lần xuất hiện của từng việc.

`isOrdered()` trong chương trình nhận kết quả là một `ArrayList` do hàm `pollOrder()` tạo ra, nên truy cập chỉ số tại đây phù hợp. Nếu tái sử dụng hàm trợ giúp với danh sách liên kết lớn, nên chuyển sang duyệt iterator để không tìm lại chỉ số ở mỗi lần so sánh.

## 8. Vì sao Set.equals và Map.equals chưa kiểm tra được thứ tự?

Hai `LinkedHashSet` có thể chứa cùng phần tử nhưng duyệt theo thứ tự khác nhau. Phép bằng nhau của tập hợp vẫn xem chúng tương đương về nội dung. Tương tự, hai map chứa cùng ánh xạ vẫn có thể bằng nhau dù thứ tự duyệt khóa khác nhau.

Ví dụ dữ liệu:

```text
Map thứ nhất: chèn B rồi A
Map thứ hai:  chèn A rồi B

Cùng ánh xạ: có
Cùng thứ tự duyệt: không
```

Nếu cần kiểm tra thứ tự, hãy chuyển thứ tự quan sát thành một `List`:

```java
List<String> actualKeys = new ArrayList<>(actualMap.keySet());
```

Sau đó so sánh với một danh sách kỳ vọng có thứ tự. Nếu cần cả ánh xạ và thứ tự, kiểm tra cả hai; kiểm tra khóa có thứ tự không thay thế được việc kiểm tra giá trị ứng với từng khóa.

Trong JUnit 5, có thể dùng `assertIterableEquals(expectedList, actualMap.keySet())` hoặc so sánh các `List` bằng `assertEquals`. Với `PriorityQueue`, đối tượng quan sát nên là kết quả `pollOrder(queue)` thay vì chính iterator của queue. Các lệnh assertion này là gợi ý cho môi trường đã có JUnit Jupiter; chương trình đầy đủ ở mục 7 chạy độc lập.

## 9. Những cách kiểm tra làm mất thông tin cần bảo vệ

### 9.1. Sắp xếp actual trước khi so sánh thứ tự chèn

Giả sử hợp đồng cần `B, A, C`, nhưng mã trả `A, B, C`. Nếu kiểm thử sắp xếp cả expected và actual trước khi so sánh, hai bên đều thành `A, B, C` và lỗi bị che mất.

Việc chuẩn hóa bằng sắp xếp chỉ phù hợp khi hợp đồng không quan tâm thứ tự và mục tiêu là so thành phần. Không dùng nó cho một bài kiểm tra thứ tự chèn.

### 9.2. Chuyển kết quả ưu tiên sang Set

Một hàng đợi có thể chứa nhiều phần tử bằng nhau. Chuyển thành `Set` làm mất số lần xuất hiện, nên không phát hiện việc queue bị thiếu một bản sao hoặc thừa bản sao khác.

Để kiểm tra đủ nội dung khi không yêu cầu thứ tự phụ, dùng số đếm theo phần tử hoặc một biểu diễn đa tập tương đương. Trong bài, `frequencies()` dùng `HashMap` và hợp đồng `equals/hashCode` của record `Job`.

### 9.3. Tính expected bằng đúng comparator đang cần kiểm thử

Nếu comparator nghiệp vụ sai hướng, vừa dùng nó trong cấu trúc thật vừa dùng nó để sắp xếp expected có thể khiến hai bên cùng sai mà kiểm thử vẫn đạt.

Các ví dụ expected cụ thể như `[5, 5, 2, 2, 1]` hoặc `[B, C, A, E, D]` phải xuất phát từ quy tắc nghiệp vụ đã viết. Kiểm tra tính có thứ tự bằng comparator là một lớp kiểm tra bổ sung, không phải nguồn sự thật duy nhất về ý nghĩa ưu tiên.

### 9.4. Kiểm tra toString thay cho hành vi

Chuỗi in ra hữu ích để giải thích và chẩn đoán, nhưng một assertion dựa vào định dạng `toString()` của collection hoặc phần tử có thể hỏng vì thay cách hiển thị mà không đổi hành vi.

Trong chương trình, các dòng stdout chỉ là kết quả minh họa. Các kiểm tra thật so sánh `List`, map số đếm hoặc giá trị cụ thể.

## 10. Ma trận ca kiểm thử có khả năng phân biệt tốt

| Mục tiêu | Dữ liệu/hành động | Điều cần khẳng định |
| --- | --- | --- |
| Thứ tự chèn khác thứ tự tự nhiên | Chèn `B, A, C` | Duyệt ra đúng `B, A, C` |
| Cập nhật khóa đang tồn tại | Đổi giá trị của `A` | Vị trí giữ nguyên trong insertion-order; giá trị đổi đúng |
| Xóa rồi thêm lại | Xóa `A`, thêm `A` | `A` chuyển về cuối theo hợp đồng chèn |
| Chế độ access-order | Chèn `B, A, C`, đọc `B` | Duyệt thành `A, C, B` |
| Sắp theo khóa, không theo giá trị | `B->2`, `A->3`, `C->1` | Khóa `A,B,C`; giá trị theo khóa `3,2,1` |
| Đảo hướng sắp xếp | Comparator giảm dần | Dãy giảm đúng, không vô tình tăng dần |
| Đồng hạng trong TreeSet | Hai phần tử compare bằng 0 | Số lượng và chính sách nhận diện phần tử đúng |
| Đồng hạng trong PriorityQueue | Nhiều việc cùng priority | Kiểm tra nhóm ưu tiên; chỉ ép thứ tự phụ nếu được hứa |
| Quy tắc phụ sequence | Cùng priority, sequence khác | Sequence nhỏ hơn được lấy trước |
| Phần tử trùng trong queue | Hai giá trị `10` | Cả hai lần xuất hiện đều được lấy ra |
| Rỗng và singleton | Không phần tử hoặc chỉ một | Dãy đầu ra đúng; không truy cập phần tử không tồn tại |
| Giữ nguyên nguồn khi kiểm tra | Rút từ bản sao | Kích thước và trạng thái nguồn không bị tiêu thụ |
| Thêm ưu tiên mới sau một lần lấy | Poll một phần tử rồi offer việc mới | Các lần lấy tiếp chọn tốt nhất trong tập đang còn |

Ca cuối nhắc rằng hàng đợi động không có một dãy priority toàn cục luôn đơn điệu nếu ta tiếp tục đưa việc mới vào giữa các lần lấy. Một việc ưu tiên cao hơn có thể được thêm sau khi đã xử lý một việc thấp hơn. Khi đó, kiểm thử phải theo từng bước trạng thái: mỗi lần lấy chọn phần tử đứng đầu trong **tập hiện có tại thời điểm đó**, không áp một dãy sắp xếp tĩnh cho toàn bộ lịch sử.

## 11. Kiểm thử ưu tiên động và tránh thay đổi khóa sắp xếp tại chỗ

Một kịch bản nhỏ:

```text
Đưa vào: A(priority=2), B(priority=5)
Lấy ra: B
Đưa thêm: C(priority=9)
Lấy ra: C
Lấy ra: A
```

Dãy priority lấy ra là `5, 9, 2`. Nó không giảm dần trên toàn bộ lịch sử, nhưng từng lần lấy đều đúng với các việc đang có trong queue.

Không sửa trực tiếp trường priority của phần tử đang nằm trong queue rồi kỳ vọng cấu trúc tự sắp lại. Nếu ứng dụng cần thay đổi ưu tiên, thiết kế phải cập nhật cấu trúc theo một quy trình xác định, chẳng hạn tìm/xóa việc cũ rồi đưa phiên bản mới vào, hoặc dùng cấu trúc chuyên biệt. Kiểm thử quy trình đó riêng, bao gồm danh tính việc và chính sách xử lý bản cũ.

Với `TreeSet` hoặc khóa `TreeMap`, thay đổi thuộc tính dùng để so sánh khi phần tử/khóa còn trong cấu trúc cũng làm mất giả định tìm kiếm và thứ tự. Dùng khóa ổn định hoặc quy trình xóa/cập nhật/thêm lại rõ ràng.

## 12. Tự kiểm tra và thực hành

### Câu 1: Hai LinkedHashMap bằng nhau theo Map.equals có bảo đảm cùng thứ tự duyệt không?

Không. Phép bằng nhau kiểm tra các ánh xạ. Cần quan sát thứ tự khóa hoặc entry thành dãy và kiểm tra riêng khi thứ tự thuộc hợp đồng.

### Câu 2: Vì sao không dùng new ArrayList<>(priorityQueue) làm actual cho thứ tự ưu tiên?

Vì đó là thứ tự iterator, không phải chuỗi lấy phần tử ở đầu hàng đợi. Rút bằng `poll()` từ nguồn hoặc bản sao phù hợp mới quan sát hành vi cần kiểm tra.

### Câu 3: Hai việc cùng priority có phải được lấy theo thứ tự chèn không?

Không nếu chỉ dựa vào `PriorityQueue` và comparator chỉ so priority. Nếu cần quy tắc này, thêm một khóa phụ biểu đạt thứ tự đưa vào và kiểm tra nó.

### Câu 4: Dãy priority đã giảm dần có đủ chứng minh hàng đợi xử lý đúng toàn bộ đầu vào không?

Chưa. Có thể thiếu hoặc thừa phần tử mà dãy còn lại vẫn giảm dần. Cần kiểm tra nội dung và số lần xuất hiện, cùng chính sách đồng hạng.

### Bài thực hành

1. Thêm kiểm tra rằng đổi giá trị `A` trong insertion-order map vừa giữ thứ tự vừa thật sự cập nhật giá trị.
2. Thêm một việc priority bằng `Integer.MAX_VALUE` và một việc bằng `Integer.MIN_VALUE`; viết expected thủ công theo quy tắc priority lớn làm trước.
3. Viết kiểm thử kịch bản ưu tiên động ở mục 11; xác nhận từng lần `poll()` thay vì sắp xếp toàn bộ lịch sử.
4. Cố ý chuyển `reversed()` xuống sau `thenComparingLong()` và xác định ca kiểm thử nào phát hiện việc đảo cả quy tắc phụ.
5. Thay queue thành tập hợp trong một bản thử nghiệm; xác định ca nào chứng minh phần tử trùng hoặc đồng hạng đã bị mất ngoài hợp đồng.

Một kiểm thử thứ tự đáng tin phải chọn đúng hành động quan sát, dữ liệu phân biệt được các chính sách và assertion giữ nguyên thông tin quan trọng. Thứ tự chèn, thứ tự sắp xếp và thứ tự lấy theo ưu tiên cần những cách kiểm tra tương ứng.
