# `Collectors.toCollection()` và chọn cấu trúc lưu trữ (Java 8+)

`Collectors.toCollection(...)` là **collector** dùng với `Stream.collect(...)` để gom các phần tử vào **kiểu `Collection` do bạn chủ động chọn**. Đây là một terminal operation: nó tiêu thụ stream, tạo collection kết quả và cho phép sử dụng các thao tác của cấu trúc đó sau khi thu thập.

Bài học tập trung vào câu hỏi thực tế: khi kết quả của một stream cần giữ trùng lặp, loại trùng, giữ thứ tự xuất hiện, sắp xếp, hoặc xử lý như hàng đợi thì nên chọn `ArrayList`, `HashSet`, `LinkedHashSet`, `TreeSet`, `ArrayDeque` hay `EnumSet`? Các lớp và API được trình bày đều còn được hỗ trợ trong Java hiện đại. Mọi ví dụ chính dùng API có từ Java 8; các lựa chọn xuất hiện ở Java mới hơn được ghi rõ phiên bản.

## 1. Vì sao cần `toCollection`?

Một stream không phải là nơi lưu dữ liệu lâu dài: nó mô tả chuỗi xử lý rồi được **tiêu thụ đúng một lần** khi gọi terminal operation như `collect`. Để dùng kết quả trong chương trình, bạn có thể gom các phần tử đã xử lý vào một collection.

Ví dụ, cùng dữ liệu đầu vào:

```java
List<String> words = Arrays.asList("beta", "alpha", "beta", "gamma", "alpha");

ArrayList<String> all = words.stream()
    .collect(Collectors.toCollection(ArrayList::new));

LinkedHashSet<String> uniqueInOrder = words.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

TreeSet<String> sortedUnique = words.stream()
    .collect(Collectors.toCollection(TreeSet::new));
```

Ba cấu trúc tạo ra ba kết quả khác nhau:

- `ArrayList` → `[beta, alpha, beta, gamma, alpha]`: **giữ mọi phần tử**, bao gồm phần tử trùng nhau, theo thứ tự gặp trong stream có thứ tự.
- `LinkedHashSet` → `[beta, alpha, gamma]`: **loại phần tử trùng**, giữ thứ tự xuất hiện đầu tiên.
- `TreeSet` → `[alpha, beta, gamma]`: **loại phần tử trùng và sắp xếp** theo thứ tự tự nhiên của `String`.

**Điểm mấu chốt:** `toCollection` không tự quyết định quy tắc loại trùng, thứ tự khi lặp, hay cách truy cập kết quả; các quy tắc đó đến từ **cấu trúc lưu trữ** được bạn cấp cho collector.

## 2. Cơ chế: cung cấp factory tạo collection

Dạng API:

```java
// Chữ ký rút gọn để giải thích kiểu generic:
static <T, C extends Collection<T>>
Collector<T, ?, C> toCollection(Supplier<C> collectionFactory)
```

- `T`: kiểu phần tử stream.
- `C`: kiểu collection kết quả, phải là một subtype của `Collection<T>`.
- `Supplier<C>`: hàm **tạo một collection mới và rỗng** để chứa các phần tử.
- `collect(...)` dùng collector để nhận các phần tử, tích lũy vào collection và ghép các kết quả bộ phận nếu cần.

Cách viết phổ biến nhất là **constructor reference**:

```java
ArrayList<Integer> values = Stream.of(3, 1, 3)
    .collect(Collectors.toCollection(ArrayList::new));
```

Tương đương cách truyền lambda tạo đối tượng mới:

```java
ArrayList<Integer> values = Stream.of(3, 1, 3)
    .collect(Collectors.toCollection(() -> new ArrayList<>()));
```

Đây là **hai ví dụ độc lập** (không khai báo cả hai biến `values` trong cùng phạm vi).

Nếu có lý do để đặt kích thước khởi tạo cho `ArrayList`, factory cũng có thể nhận cấu hình:

```java
ArrayList<String> result = words.stream()
    .collect(Collectors.toCollection(() -> new ArrayList<>(64)));
```

Số `64` là **capacity ban đầu**, không phải số phần tử hay giới hạn tối đa; `ArrayList` ban đầu vẫn rỗng và có thể mở rộng. Chỉ dùng tối ưu hóa này khi có căn cứ về quy mô dữ liệu; mặc định `ArrayList::new` thường đủ.

**Không dùng chung một collection đã tạo sẵn làm factory:**

```java
ArrayList<String> shared = new ArrayList<>();

// Sai về hợp đồng factory: cùng một instance có thể được dùng lại.
 // words.parallelStream().collect(Collectors.toCollection(() -> shared));
```

Collector có thể gọi factory **nhiều lần**, đặc biệt trong parallel stream. Mỗi lần gọi phải cho ra **instance mới, rỗng, độc lập**. Cấu trúc chọn làm kết quả cũng **không tự trở thành thread-safe** chỉ vì pipeline được chạy song song.

## 3. Bảng chọn cấu trúc lưu trữ theo nhu cầu

| Nhu cầu chính | Factory cho `toCollection` | Quy tắc dữ liệu và thứ tự |
| --- | --- | --- |
| Danh sách, có thể có trùng, truy cập theo chỉ số | `ArrayList::new` | Giữ trùng và thứ tự gặp, truy cập `get(index)` nhanh |
| Loại trùng, không cần thứ tự lặp xác định | `HashSet::new` | Loại trùng dựa trên `equals/hashCode`; không bảo đảm thứ tự lặp |
| Loại trùng nhưng vẫn giữ thứ tự xuất hiện đầu tiên | `LinkedHashSet::new` | Loại trùng theo `equals/hashCode` và giữ thứ tự chèn |
| Tập hợp duy nhất và được sắp xếp | `TreeSet::new` hoặc lambda truyền `Comparator` | Sắp xếp và xác định trùng theo phép so sánh |
| Cần queue/deque/stack sau khi gom | `ArrayDeque::new` | Giữ các phần tử theo thứ tự chèn, cho phép trùng, cấm `null` |
| Tập giá trị thuộc một kiểu `enum` | `() -> EnumSet.noneOf(Status.class)` | Set dành cho enum; lặp theo thứ tự khai báo enum |

Chỉ cần nhớ một nguyên tắc: **chọn cấu trúc theo thao tác sẽ thực hiện sau khi `collect`**, không chọn theo tên collector. Với danh sách có truy cập ngẫu nhiên, `ArrayList` thường hợp lý; với queue/stack, `ArrayDeque` thường phù hợp hơn `LinkedList`. `LinkedList` vẫn là API được hỗ trợ, nhưng `get(index)` phải duyệt các nút và ít khi là lựa chọn mặc định cho hai nhu cầu trên.

### Đánh đổi hiệu năng thường gặp

- `ArrayList`: truy cập theo chỉ số thường `O(1)`; thêm cuối thường `O(1)` trung bình theo phân tích amortized; chèn/xóa ở giữa thường `O(n)` vì dịch phần tử.
- `HashSet` và `LinkedHashSet`: `add`/`contains` thường `O(1)` trung bình nếu hash phân bố phù hợp. `LinkedHashSet` tốn thêm bộ nhớ để giữ thứ tự chèn.
- `TreeSet`: `add`/`contains`/`remove` thường `O(log n)` và có chi phí so sánh; đổi lại dữ liệu luôn theo thứ tự của comparator.
- `ArrayDeque`: phù hợp thao tác thêm/lấy ở hai đầu; không hỗ trợ truy cập theo chỉ số như `List`.

Đây là đặc tính thường gặp, không phải lời hứa về thời gian chạy cụ thể cho mọi dữ liệu hoặc phần cứng. `collect` luôn có chi phí lưu các phần tử được giữ lại; nếu chỉ cần số lượng, tổng, min/max thì có thể dùng terminal operation tổng hợp thay vì tạo collection lớn.

## 4. Khi cần `List`: kiểm soát kiểu và khả năng chỉnh sửa

`Collectors.toList()` (có từ Java 8) tạo một `List` nhưng **không cam kết** kiểu cài đặt cụ thể, khả năng sửa, khả năng tuần tự hóa hoặc thread-safety của kết quả. Vì vậy đừng ép kiểu:

```java
List<String> data = words.stream().collect(Collectors.toList());

// Không được giả định:
// ArrayList<String> unsafe = (ArrayList<String>) words.stream()
//     .collect(Collectors.toList());
```

Nếu API phía sau cần **một `ArrayList` có thể chỉnh sửa**, hãy nói rõ ngay từ đầu:

```java
ArrayList<String> editable = words.stream()
    .map(String::trim)
    .collect(Collectors.toCollection(ArrayList::new));

editable.add("delta");
editable.remove("beta");
```

Các ví dụ `ArrayList` cho phép trùng lặp; việc gọi `remove("beta")` chỉ xóa **một lần xuất hiện đầu tiên**.

**Nếu cần kết quả không chỉnh sửa được**, hiện nay có lựa chọn khác:

| API | Có từ | Hợp đồng quan trọng |
| --- | --- | --- |
| `Collectors.toCollection(ArrayList::new)` | Java 8 | Chỉ định `ArrayList`, chỉnh sửa được |
| `Collectors.toList()` | Java 8 | Kết quả là `List`, không bảo đảm loại cài đặt hay mutability |
| `Collectors.toUnmodifiableList()` | Java 10 | `List` không chỉnh sửa được; **không nhận phần tử `null`** |
| `Stream.toList()` | Java 16 | `List` không chỉnh sửa được; không cam kết kiểu cài đặt cụ thể |

Ví dụ (chỉ dùng khi chạy Java 16+):

```java
List<String> view = words.stream().map(String::toUpperCase).toList();
// view.add("NEW"); // Ném UnsupportedOperationException
```

Đối với Java 8, muốn một kiểu danh sách cụ thể, có thể sửa, `toCollection(ArrayList::new)` là lựa chọn rõ ràng. Một danh sách **không chỉnh sửa được** cũng không tự biến các **đối tượng bên trong** thành bất biến.

## 5. Khi cần `Set`: trùng lặp và thứ tự lặp

### `HashSet`: loại trùng khi không cần thứ tự

```java
HashSet<String> unique = words.stream()
    .collect(Collectors.toCollection(HashSet::new));
```

`HashSet` dùng `equals` và `hashCode` để nhận diện phần tử trùng. Thứ tự trả về khi lặp **không được cam kết**. Đừng dựa vào thứ tự đang thấy trong một lần chạy hoặc một phiên bản JDK.

`Collectors.toSet()` cũng tạo `Set`, nhưng không bảo đảm implementation, mutability hay thứ tự lặp. Khi chọn `HashSet` là yêu cầu cụ thể của chương trình, `toCollection(HashSet::new)` diễn đạt đúng hợp đồng mong muốn.

### `LinkedHashSet`: loại trùng, giữ thứ tự xuất hiện đầu tiên

```java
LinkedHashSet<String> firstSeen = words.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(firstSeen); // [beta, alpha, gamma]
```

`LinkedHashSet` giữ thứ tự chèn. Khi "beta" xuất hiện lần thứ hai, set **không thêm phần tử mới**, đồng thời vị trí "beta" đã có **không bị chuyển xuống cuối** do phép thêm trùng. Đây là lựa chọn phổ biến khi muốn danh sách duy nhất nhưng vẫn có thứ tự dễ giải thích.

Lưu ý: quy tắc trên dựa vào **encounter order** của stream đầu vào. `List.stream()` thông thường có thứ tự; nguồn `HashSet.stream()` không có thứ tự encounter đáng tin để giữ nguyên "thứ tự xuất hiện" từ nguồn.

### `TreeSet`: tập hợp được sắp xếp

```java
TreeSet<String> alphabetical = words.stream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(alphabetical); // [alpha, beta, gamma]
```

`TreeSet` dùng thứ tự tự nhiên khi tạo bằng `TreeSet::new`. Phần tử phải so sánh được với nhau. Nếu muốn thứ tự riêng, truyền comparator qua factory:

```java
TreeSet<String> byLengthThenName = words.stream()
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(
            Comparator.comparingInt(String::length)
                      .thenComparing(Comparator.naturalOrder())
        )
    ));

System.out.println(byLengthThenName); // [beta, alpha, gamma]
```

Comparator trước tiên so độ dài, sau đó so tên khi độ dài bằng nhau. Việc thêm tiêu chí phá hòa có ý nghĩa quan trọng: trong `TreeSet`, hai phần tử có `compare(a,b) == 0` được coi là **trùng theo thứ tự của cây** và chỉ giữ một phần tử, ngay cả khi `equals` nói chúng khác nhau. Để `TreeSet` tuân thủ đầy đủ ngữ nghĩa `Set`, comparator nên **consistent with equals** với miền dữ liệu. Ví dụ chỉ so `String::length` sẽ coi "cat" và "dog" như một phần tử và loại mất một giá trị dù hai chuỗi khác nhau.

Đừng dùng `TreeSet` chỉ để giữ thứ tự input: nó **sắp xếp lại** kết quả. Nếu chỉ muốn giữ encounter order sau khi loại trùng, `LinkedHashSet` đúng mục đích hơn.

## 6. Khi cần queue/deque hoặc một tập enum

### `ArrayDeque`: queue, deque và stack

`ArrayDeque` thực thi `Deque` và có thể là kết quả của `toCollection` vì `Deque` là một `Collection`. Nó phù hợp khi kết quả cần thao tác ở hai đầu:

```java
ArrayDeque<String> queue = words.stream()
    .collect(Collectors.toCollection(ArrayDeque::new));

String first = queue.peekFirst(); // "beta", không xóa
String removed = queue.removeFirst(); // "beta", có xóa
queue.addLast("delta");
```

Thứ tự chèn được giữ để thao tác theo queue/deque, phần tử trùng được chấp nhận. **`ArrayDeque` không chấp nhận `null`**; nếu đầu vào có thể chứa `null`, làm sạch rõ ràng trước khi gom:

```java
ArrayDeque<String> nonNull = words.stream()
    .filter(Objects::nonNull)
    .collect(Collectors.toCollection(ArrayDeque::new));
```

Nếu cần một queue mà việc lấy ra theo **độ ưu tiên** khác với thứ tự chèn, `PriorityQueue` có thể sử dụng với `toCollection(PriorityQueue::new)`; tuy nhiên thứ tự **lặp bằng iterator/toString không được bảo đảm là đã sắp xếp**. Chỉ phương thức lấy đầu hàng đợi như `poll()` mới phản ánh thứ tự ưu tiên.

### `EnumSet`: tập lựa chọn thuộc một enum

Ví dụ ứng dụng lưu các trạng thái khác nhau mà đã nhìn thấy:

```java
enum Stage { NEW, ACTIVE, DONE }

List<Stage> stages = Arrays.asList(Stage.DONE, Stage.NEW, Stage.DONE);

EnumSet<Stage> uniqueStages = stages.stream()
    .collect(Collectors.toCollection(() -> EnumSet.noneOf(Stage.class)));

System.out.println(uniqueStages); // [NEW, DONE]
```

`EnumSet.noneOf(Stage.class)` trả về **một set rỗng đúng kiểu enum**; không dùng constructor reference `EnumSet::new` vì `EnumSet` không tạo trực tiếp theo cách đó. `EnumSet` loại trùng và lặp theo **thứ tự khai báo các hằng enum**, không phải encounter order của stream; không chấp nhận `null`. Loại này thường gọn và hiệu quả khi miền giá trị là một kiểu enum xác định.

## 7. Dùng `toCollection` làm downstream collector

`toCollection` không chỉ dùng trực tiếp với `Stream.collect`. Nó còn được truyền làm collector thứ cấp cho `groupingBy` để **chọn cấu trúc lưu trữ của mỗi nhóm**.

```java
List<String> tags = Arrays.asList(
    "blue", "amber", "blue", "black", "apple");

Map<Character, LinkedHashSet<String>> byFirstLetter = tags.stream()
    .collect(Collectors.groupingBy(
        word -> word.charAt(0),
        LinkedHashMap::new,
        Collectors.toCollection(LinkedHashSet::new)
    ));

System.out.println(byFirstLetter);
// {b=[blue, black], a=[amber, apple]}
```

Ở đây có **hai quyết định độc lập**:

1. `LinkedHashMap::new` quyết định thứ tự lặp các **nhóm**: `b` đến trước `a` vì "blue" gặp đầu tiên.
2. `LinkedHashSet::new` quyết định cách lưu **phần tử trong từng nhóm**: loại trùng và giữ thứ tự gặp trong nhóm.

Nếu chỉ định downstream `toSet()` và không chọn loại `Map`, chương trình không có cùng bảo đảm về thứ tự khi in kết quả. Ví dụ này có thể biên dịch độc lập nếu đặt trong một phương thức phù hợp với các `import` từ chương trình ở mục 8.

## 8. Chương trình hoàn chỉnh để chạy và so sánh

Tạo file **`JavaToCollectionDemo.java`**. Chương trình chỉ dùng các API có từ Java 8 nên vẫn chạy được với JDK 17, 21, 26 và các bản mới hỗ trợ tương thích.

```java
import java.util.*;
import java.util.stream.*;

public class JavaToCollectionDemo {
    enum Stage { NEW, ACTIVE, DONE }

    public static void main(String[] args) {
        List<String> words = Arrays.asList(
                "beta", "alpha", "beta", "gamma", "alpha");

        ArrayList<String> all = words.stream()
                .collect(Collectors.toCollection(ArrayList::new));

        LinkedHashSet<String> firstSeen = words.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));

        TreeSet<String> sorted = words.stream()
                .collect(Collectors.toCollection(TreeSet::new));

        ArrayDeque<String> queue = words.stream()
                .collect(Collectors.toCollection(ArrayDeque::new));

        System.out.println("ArrayList: " + all);
        System.out.println("LinkedHashSet: " + firstSeen);
        System.out.println("TreeSet: " + sorted);
        System.out.println("Queue peek: " + queue.peekFirst());

        queue.removeFirst();
        System.out.println("Queue after remove: " + queue);

        List<Stage> stages = Arrays.asList(
                Stage.DONE, Stage.NEW, Stage.DONE);
        EnumSet<Stage> uniqueStages = stages.stream()
                .collect(Collectors.toCollection(
                        () -> EnumSet.noneOf(Stage.class)));
        System.out.println("EnumSet: " + uniqueStages);

        TreeSet<String> byLengthThenName = words.stream()
                .collect(Collectors.toCollection(
                        () -> new TreeSet<>(
                                Comparator.comparingInt(String::length)
                                          .thenComparing(Comparator.naturalOrder()))));
        System.out.println("Length + name: " + byLengthThenName);

        all.add("delta");
        System.out.println("Mutable list size: " + all.size());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 JavaToCollectionDemo.java
java JavaToCollectionDemo
```

Kết quả chuẩn:

```text
ArrayList: [beta, alpha, beta, gamma, alpha]
LinkedHashSet: [beta, alpha, gamma]
TreeSet: [alpha, beta, gamma]
Queue peek: beta
Queue after remove: [alpha, beta, gamma, alpha]
EnumSet: [NEW, DONE]
Length + name: [beta, alpha, gamma]
Mutable list size: 6
```

Giải thích: `ArrayList` giữ đủ năm phần tử và được thêm "delta" nên có kích thước 6; `LinkedHashSet` giữ các giá trị đầu tiên theo thứ tự input; `TreeSet` loại trùng và sắp theo tên; `ArrayDeque` lấy "beta" ở đầu rồi còn bốn phần tử; `EnumSet` lặp theo thứ tự khai báo `NEW, ACTIVE, DONE`; comparator của tập cuối sắp theo độ dài trước, sau đó theo chữ cái.

Mỗi lời gọi `words.stream()` tạo **một stream mới**. Không thể gọi hai terminal operation liên tiếp trên cùng instance stream đã tiêu thụ.

## 9. Những lỗi thường gặp

| Sai lầm | Hậu quả và cách xử lý |
| --- | --- |
| Giả định `Collectors.toList()` luôn trả `ArrayList` có thể sửa | API không bảo đảm; cần `ArrayList` thì dùng `toCollection(ArrayList::new)` |
| Dùng `toSet()`/`HashSet` rồi dựa vào thứ tự hiển thị | Không có hợp đồng thứ tự; muốn giữ thứ tự gặp dùng `LinkedHashSet` |
| Chọn `TreeSet` chỉ để bỏ giá trị trùng | Có thể đổi thứ tự và loại các phần tử comparator coi bằng nhau; cân nhắc `LinkedHashSet` |
| Đưa `null` vào `ArrayDeque` hoặc `EnumSet` | Ném `NullPointerException`; xử lý dữ liệu đầu vào trước |
| Đưa `null` vào `TreeSet` với thứ tự tự nhiên | Thường ném `NullPointerException`; lọc `null` hoặc thiết kế comparator có chủ đích |
| Dùng supplier trả về cùng một collection dùng chung | Vi phạm hợp đồng factory; phải tạo **mới, rỗng** cho mỗi lần gọi |
| Muốn lưu theo thứ tự encounter nhưng lấy nguồn vốn unordered | Không thể cam kết "thứ tự ban đầu"; xác định nguồn có thứ tự hoặc sắp xếp trước |
| Giả định collection kết quả thread-safe vì dùng `parallelStream()` | Pipeline có thể ghép kết quả bộ phận an toàn theo collector, nhưng collection nhận được vẫn theo đặc tính của chính nó |
| Dùng `toCollection(ArrayList::new)` khi chỉ cần đếm | Tốn bộ nhớ để lưu các phần tử; dùng `count()` khi chỉ cần số lượng |
| Dùng `PriorityQueue` rồi cho rằng `toString()` đã sắp xếp | Thứ tự duyệt của heap không được bảo đảm; lấy lần lượt bằng `poll()` nếu cần thứ tự ưu tiên |

Đối với stream song song, các collector tiêu chuẩn như `toCollection` cung cấp cơ chế tạo/tích lũy/ghép kết quả; không cần tự tạo collection chia sẻ giữa các worker thread. Tuy nhiên, xử lý song song có chi phí điều phối và không phải lúc nào cũng nhanh hơn. Sau khi trả về, `ArrayList`, `LinkedHashSet`, `TreeSet` và `ArrayDeque` thông thường **không an toàn cho nhiều luồng cùng sửa** nếu không có cơ chế đồng bộ phù hợp.

## 10. Tự luyện tập và chọn đúng cấu trúc

Cho nguồn:

```java
List<String> events = Arrays.asList(
    "login", "view", "login", "pay", "view");
```

- Muốn lưu đầy đủ lịch sử, bao gồm sự kiện lặp: chọn `toCollection(ArrayList::new)` → `[login, view, login, pay, view]`.
- Muốn danh sách tên sự kiện duy nhất nhưng giữ thứ tự xuất hiện đầu: chọn `toCollection(LinkedHashSet::new)` → `[login, view, pay]`.
- Muốn tên sự kiện duy nhất theo bảng chữ cái: chọn `toCollection(TreeSet::new)` → `[login, pay, view]`.
- Muốn xử lý lần lượt theo FIFO: chọn `toCollection(ArrayDeque::new)` rồi sử dụng `pollFirst()`; phần tử lấy đầu tiên là `"login"`.
- Nếu pipeline chỉ cần **3 loại sự kiện khác nhau**, chọn collector set rồi gọi `size()` khi thực sự cần lưu set; nếu chỉ cần số lượng giá trị khác nhau, `events.stream().distinct().count()` trực tiếp hơn.

**Quy tắc lựa chọn:** xác định trước liệu dữ liệu có được phép lặp không, thứ tự cần duy trì là encounter order hay thứ tự sắp xếp, các thao tác sau khi gom là theo chỉ số/tìm kiếm/đầu hàng đợi, và kết quả có cần chỉnh sửa được không. Sau đó chọn đúng factory cho `toCollection`.

### Tài liệu API đang được duy trì

- [`Collectors.toCollection` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): factory tạo collection mới, quy tắc encounter order và hợp đồng `toList`.
- [`Stream.toList` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): kết quả `List` không chỉnh sửa được (Java 16+).
- [`LinkedHashSet` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/LinkedHashSet.html): thứ tự chèn và quy tắc phần tử trùng.
- [`TreeSet` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeSet.html): thứ tự so sánh, tính duy nhất theo comparator.
- [`ArrayDeque` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ArrayDeque.html): cấu trúc deque và quy tắc về `null`.
- [`EnumSet` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/EnumSet.html): set chuyên biệt cho enum.