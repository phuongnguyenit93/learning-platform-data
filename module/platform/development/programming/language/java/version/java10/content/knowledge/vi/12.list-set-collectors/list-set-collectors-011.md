# Giới hạn giả định về kiểu triển khai của kết quả Collector danh sách và tập (Java 10+)

## 1. Trọng tâm: kết quả là `List`/`Set`, không nhất thiết là `ArrayList`/`HashSet`

Khi xử lý Stream, Java cung cấp nhiều cách tích lũy phần tử thành danh sách (*List*) hoặc tập hợp (*Set*). Một lỗi thiết kế phổ biến là thấy một lần chạy trả `ArrayList` hoặc `HashSet` rồi coi đó là **cam kết của API**:

```java
var items = stream.collect(java.util.stream.Collectors.toList());
var unique = stream.collect(java.util.stream.Collectors.toSet());
```

Hai dòng trên là mã minh họa, với `stream` cần được khai báo phù hợp trong một phương thức. Theo hợp đồng chính thức của `Collectors.toList()` và `Collectors.toSet()`, **không có bảo đảm về lớp triển khai cụ thể, tính có thể sửa, khả năng serialization hoặc thread-safety của collection kết quả**. Vì vậy, chỉ nên xem những gì API cam kết là ràng buộc của chương trình.

Ví dụ, với `toList()` có thể dùng các thao tác của interface `List` phù hợp với hợp đồng; không được khẳng định `items instanceof ArrayList` luôn đúng. Với `toSet()` không được khẳng định tập kết quả là `HashSet` hoặc việc duyệt tập trả phần tử theo thứ tự đã thấy trong một lần chạy.

Từ **Java 10**, có thêm `Collectors.toUnmodifiableList()` và `Collectors.toUnmodifiableSet()` để yêu cầu **kết quả không thể sửa**. Từ **Java 16**, có `Stream.toList()` với hợp đồng **unmodifiable List**. Các API này không có nghĩa chương trình được quyền phụ thuộc vào tên lớp triển khai cụ thể của chúng.

Bài học này tập trung vào giới hạn các giả định về **kiểu implementation và thuộc tính kết quả**, thay vì chỉ học cú pháp collector.

### Sau bài này, bạn cần làm được

1. Phân biệt **kiểu trả về khai báo** của collector, **lớp triển khai lúc chạy** và **hợp đồng hành vi**.
2. Không suy luận tính mutable, thứ tự duyệt, serialization hoặc thread-safety từ tên một lớp đã quan sát.
3. So sánh đúng `Collectors.toList()`, `Collectors.toSet()`, `toUnmodifiableList()`, `toUnmodifiableSet()` và `Stream.toList()`.
4. Dùng `Collectors.toCollection(Supplier)` khi dự án thật sự cần `ArrayList`, `LinkedHashSet` hoặc `TreeSet` cụ thể.
5. Tránh cast mong manh, đồng nhất `toList` của collector với `toList` của stream, hoặc phụ thuộc vào thứ tự in ra của `Set`.
6. Thiết kế API ưu tiên interface và công bố chính xác các bảo đảm thực sự quan trọng.

Tất cả quy tắc dùng trong bài **vẫn áp dụng trong Java hiện đại**. Các phần có phiên bản yêu cầu mới hơn Java 10 được ghi rõ.

## 2. Ba khái niệm phải tách biệt

Xét:

```java
java.util.List<String> names =
        java.util.stream.Stream.of("Ada", "Grace", "Linus")
                .collect(java.util.stream.Collectors.toList());
```

Có ba tầng:

- **Kiểu khai báo ở thời điểm biên dịch:** `List<String>`. Phương thức `Collectors.toList()` công bố kết quả theo interface `List<T>`.
- **Lớp của object lúc chạy:** một implementation nào đó của `List`. Trên một bản JDK, bạn có thể quan sát một tên lớp cụ thể, nhưng **quan sát đó không trở thành hợp đồng của `Collectors.toList()`**.
- **Tính chất được API bảo đảm:** các phần tử được đưa vào một `List` theo encounter order của stream, nếu thứ tự ấy tồn tại; tài liệu collector không hứa kết quả phải mutable hay là loại list có khả năng đặc biệt nào.

Kể cả khi một implementation hiện tại dùng `ArrayList` bên trong, nhà cung cấp JDK có thể thay đổi lựa chọn triển khai mà vẫn đáp ứng đặc tả. Vì vậy, không viết logic phụ thuộc vào tên lớp nội bộ.

Một collection **có kiểu tĩnh `List`** cũng không đồng nghĩa mọi mutator `List` đều được hỗ trợ: interface Java Collections Framework có các *optional operations*. Một list được công bố là unmodifiable sẽ ném `UnsupportedOperationException` khi bị sửa, dù về mặt cú pháp lời gọi `add`/`set` có thể biên dịch.

## 3. `Collectors.toList()`: đừng đoán `ArrayList` hay mutable

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> result = Stream.of("c", "a", "b")
        .collect(Collectors.toList());

System.out.println(result); // [c, a, b]
```

Đây là **mã minh họa trong thân phương thức** với các import tương ứng. Với stream có encounter order, list được tạo có các phần tử theo thứ tự đó.

Hợp đồng chính thức của `Collectors.toList()` **không bảo đảm**:

- Lớp triển khai là `ArrayList`, `LinkedList` hay một tên cụ thể khác.
- Có thể `add`, `remove`, `set` hay `sort`.
- Có thể serialize theo một hình thức hay điều kiện cụ thể.
- Collection kết quả thread-safe.

Sai lầm điển hình:

```java
var result = Stream.of("a", "b").collect(Collectors.toList());

// Không an toàn về hợp đồng:
// java.util.ArrayList<String> concrete =
//         (java.util.ArrayList<String>) result;
//
// concrete.ensureCapacity(100);
```

Phép ép kiểu có thể thành công trên một runtime cụ thể nếu object tình cờ là `ArrayList`, nhưng có thể gây `ClassCastException` khi implementation thay đổi. `getClass()`, `instanceof ArrayList` và tên lớp in từ debugger chỉ là **thông tin quan sát**, không phải bảo đảm từ phương thức collector.

### Cách đúng khi thực sự cần `ArrayList`

```java
java.util.ArrayList<String> editable =
        Stream.of("a", "b")
                .collect(Collectors.toCollection(
                        java.util.ArrayList::new));

editable.add("c");
editable.ensureCapacity(100); // Hợp lệ: kiểu và object đều là ArrayList.
```

`toCollection(ArrayList::new)` yêu cầu collector tạo collection từ supplier đã chỉ định. Chữ ký generic của phương thức cho phép khai báo trực tiếp `ArrayList<String>` mà **không cast**; đây mới là cách có hợp đồng rõ khi cần thao tác riêng của class đó.

Nếu không cần một lớp cụ thể, **giữ `List<T>` trong chữ ký và dùng các phương thức của interface**. Việc cố lấy `ArrayList` chỉ để được dùng `add` có thể không cần thiết; nếu yêu cầu mutable là ràng buộc, có thể chủ động copy bằng `new ArrayList<>(result)` tại nơi cần sửa.

## 4. `Collectors.toSet()`: đừng đoán `HashSet` hay thứ tự

```java
var unique = java.util.stream.Stream.of("b", "a", "b", "c")
        .collect(java.util.stream.Collectors.toSet());

System.out.println(unique.size());       // 3
System.out.println(unique.contains("a")); // true
```

`Collectors.toSet()` đưa phần tử vào một `Set` và dùng quan hệ bằng nhau của phần tử để không giữ các phần tử trùng theo hợp đồng `Set`. Nhưng đặc tả không hứa:

- Kết quả luôn là `HashSet`.
- Kết quả mutable, serializable hoặc thread-safe.
- Thứ tự duyệt giống thứ tự stream đầu vào.
- Kết quả được sắp xếp tự nhiên hoặc bảo đảm thứ tự chèn.

Quan trọng hơn, `Collectors.toSet()` là **unordered collector**. Với stream `"b", "a", "b", "c"`, đừng viết bài kiểm tra phụ thuộc trực tiếp vào việc `unique.toString()` phải là `[a, b, c]` hay `[b, a, c]`.

Nếu cần in kết quả để kiểm thử mà muốn thứ tự ổn định đối với các `String`:

```java
var sortedForDisplay = new java.util.TreeSet<>(unique);
System.out.println(sortedForDisplay); // [a, b, c]
```

Việc tạo `TreeSet` **là một bước chuyển đổi riêng**, không có nghĩa collector mặc định đã tạo `TreeSet`.

### Khi cần giữ thứ tự chèn

```java
java.util.LinkedHashSet<String> ordered =
        java.util.stream.Stream.of("b", "a", "b", "c")
                .collect(java.util.stream.Collectors.toCollection(
                        java.util.LinkedHashSet::new));

System.out.println(ordered); // [b, a, c]
```

Trong ví dụ stream **sequential và có encounter order**, `LinkedHashSet` giữ thứ tự thêm phần tử, nên giá trị `"b"` lặp lại không được thêm lần thứ hai. Nếu đó là hợp đồng sản phẩm, hãy chỉ rõ `LinkedHashSet` thay vì phỏng đoán hành vi hiện thời của `Collectors.toSet()`.

### Khi cần một SortedSet

```java
java.util.TreeSet<String> alphabetically =
        java.util.stream.Stream.of("b", "a", "c")
                .collect(java.util.stream.Collectors.toCollection(
                        java.util.TreeSet::new));

System.out.println(alphabetically); // [a, b, c]
```

`TreeSet` áp dụng thứ tự tự nhiên hoặc comparator. Với các loại phần tử tự định nghĩa, cần bảo đảm chúng có thứ tự phù hợp; việc xác định phần tử trùng theo comparator của `TreeSet` có thể khác với cách một hash-based set dùng `equals()`. Đừng thay `toSet()` bằng `TreeSet` chỉ vì muốn biết tên lớp nếu việc thay đổi quy tắc so sánh có thể làm mất dữ liệu.

## 5. Collector Java 10: `toUnmodifiableList()` và `toUnmodifiableSet()`

Hai collector này được đưa vào **Java 10**, đúng với chủ đề module, và **vẫn là API hiện hành**:

```java
var labels = java.util.stream.Stream.of("c", "a", "b")
        .collect(java.util.stream.Collectors.toUnmodifiableList());

var distinct = java.util.stream.Stream.of("b", "a", "b", "c")
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
```

Bảo đảm:

- `labels` là một **unmodifiable `List`** giữ encounter order của stream.
- `distinct` là một **unmodifiable `Set`**, không giữ những phần tử trùng theo `equals()`, **không bảo đảm iteration order**.
- Các thao tác nhằm sửa cấu trúc kết quả, như `add`, `remove` và `set`/`sort` cho list, sẽ bị từ chối.
- Cả hai collector **không chấp nhận phần tử `null`**: khi nhận null sẽ ném `NullPointerException`.
- Không nên suy luận một tên concrete class cho kết quả của chúng. Điều cần dựa vào là **hợp đồng unmodifiable**, không phải chi tiết triển khai.

Ví dụ về thao tác bị từ chối:

```java
// labels.add("d");    // UnsupportedOperationException
// labels.set(0, "x"); // UnsupportedOperationException
// distinct.add("d");  // UnsupportedOperationException
```

Các dòng comment là thao tác **cố ý sai lúc chạy**, không phải hướng dẫn chỉnh sửa collection. Nếu cần tạo phiên bản mới:

```java
var editable = new java.util.ArrayList<>(labels);
editable.add("d");

var nextUnmodifiable = java.util.List.copyOf(editable);
```

`List.copyOf` cũng có từ Java 10. Nó tạo snapshot cấu trúc unmodifiable mới từ list đã chỉnh sửa; không biến `labels` ban đầu thành mutable.

### Với `toUnmodifiableSet()`, phần tử trùng bằng nhau có thể giữ bản nào?

Tài liệu `Collectors.toUnmodifiableSet()` nêu rõ: nếu đầu vào có các phần tử trùng theo quan hệ bằng nhau, collector có thể **giữ tùy ý một phần tử trong nhóm trùng đó**.

Với các object có `equals()/hashCode()` chỉ phụ thuộc ID nhưng trường hiển thị khác nhau, không dựa vào việc đối tượng **đầu tiên** hoặc **cuối cùng** được giữ. Nếu sản phẩm cần quy tắc merge cụ thể (ví dụ ưu tiên bản cập nhật mới nhất), hãy xác định chính sách trước khi tạo Set hoặc sử dụng cấu trúc khác cho phép merge rõ ràng.

Ví dụ an toàn chỉ nên kiểm tra rằng hai object cùng ID được nhìn như một phần tử, không giả định trường `label` nào sẽ còn lại.

## 6. Dễ nhầm: `Stream.toList()` không phải `Collectors.toList()`

Hai cú pháp:

```java
var fromCollector = java.util.stream.Stream.of("a", "b")
        .collect(java.util.stream.Collectors.toList());

var fromStream = java.util.stream.Stream.of("a", "b")
        .toList();
```

Trông cùng mang chữ `toList` nhưng **khác hợp đồng**:

| API | Có từ | Kiểu giao diện trả về | Tính mutable được cam kết? |
| --- | --- | --- | --- |
| `Collectors.toList()` | Java 8 | `List<T>` | **Không có bảo đảm mutable hay unmodifiable** |
| `Collectors.toSet()` | Java 8 | `Set<T>` | **Không có bảo đảm mutable hay unmodifiable** |
| `Collectors.toUnmodifiableList()` | Java 10 | `List<T>` | **Bảo đảm unmodifiable** |
| `Collectors.toUnmodifiableSet()` | Java 10 | `Set<T>` | **Bảo đảm unmodifiable** |
| `Stream.toList()` | Java 16 | `List<T>` | **Bảo đảm unmodifiable** |
| `Collectors.toCollection(ArrayList::new)` | Java 8 | `ArrayList<T>` | Mutable theo hợp đồng của `ArrayList` |
| `Collectors.toCollection(LinkedHashSet::new)` | Java 8 | `LinkedHashSet<T>` | Mutable, iteration theo thứ tự chèn |

Với `Stream.toList()`, Javadoc còn ghi **không bảo đảm lớp implementation hoặc khả năng serialization**. Instance trả về **có thể là value-based**; không dựa vào `==`, identity hash code hoặc synchronization dựa trên danh tính đối tượng.

**Không được suy luận rằng `Stream.toList()` trả `ArrayList` mutable** từ tên gọi hoặc từ một ví dụ trong debugger. Nếu code cần `add` hoặc `set`:

```java
var editable = new java.util.ArrayList<>(
        java.util.stream.Stream.of("a", "b").toList());

editable.add("c");
```

Vì `Stream.toList()` có từ Java 16, đoạn này phù hợp Java 17+, còn trên Java 10 hãy dùng `Collectors.toCollection(ArrayList::new)` hoặc `Collectors.toUnmodifiableList()` tùy nhu cầu.

## 7. Giới hạn về thứ tự: List khác Set

Thứ tự là một phần hợp đồng của **List** khi stream có encounter order; không phải một thuộc tính bạn tự động được nhận khi chuyển sang **Set**.

```java
var list = java.util.stream.Stream.of("c", "a", "b")
        .collect(java.util.stream.Collectors.toList());

System.out.println(list); // [c, a, b]
```

Một stream tạo từ `List` hoặc `Stream.of(...)` có encounter order. `toList` của collector và `toUnmodifiableList` giữ thứ tự phần tử tương ứng. `Stream.toList()` cũng bảo toàn encounter order nếu tồn tại.

Với set:

```java
var set = java.util.stream.Stream.of("c", "a", "b")
        .collect(java.util.stream.Collectors.toSet());
```

Đừng phụ thuộc thứ tự duyệt của `set`. Ngay cả khi một lần chạy tình cờ in đúng `[a, b, c]`, thứ tự đó không phải hợp đồng.

Các lựa chọn khi thứ tự quan trọng:

- **Thứ tự chèn:** `toCollection(LinkedHashSet::new)` từ một stream có encounter order.
- **Thứ tự sắp xếp theo comparator:** `toCollection(TreeSet::new)` hoặc một `TreeSet` có comparator được truyền cho supplier.
- **Giữ cả trùng lặp và thứ tự:** dùng `List`, không phải `Set`.
- **Trình bày deterministic:** có thể lấy một bản sorted độc lập để hiển thị, tránh lồng logic UI vào implementation không được bảo đảm của Set.

Không nhầm “một stream có thứ tự” với “mọi collector phải bảo toàn thứ tự”; `toSet()` và `toUnmodifiableSet()` được công bố là **unordered collector**.

## 8. Giới hạn về null: không đánh đồng các API khác nhau

`Collectors.toUnmodifiableList()` và `Collectors.toUnmodifiableSet()` **từ chối phần tử `null`** theo đặc tả:

```java
// Hai lời gọi này ném NullPointerException khi chạy:
//
// Stream.of("A", (String) null)
//       .collect(Collectors.toUnmodifiableList());
//
// Stream.of("A", (String) null)
//       .collect(Collectors.toUnmodifiableSet());
```

Điều này không có nghĩa tất cả các cách tạo `List`/`Set` khác nhau đều phải có cùng chính sách null. Nếu dữ liệu có thể vắng mặt, hãy lựa chọn chính sách riêng: xác thực, lọc có chủ đích, ánh xạ sang kiểu giá trị thích hợp, hoặc chọn collection tương thích với yêu cầu đó.

Đừng đổi `Collectors.toList()` sang `toUnmodifiableList()` hàng loạt mà không kiểm tra input nullable: ngoài giới hạn mutator, **hợp đồng về null** cũng có thể thay đổi.

Một cách lọc có chủ đích:

```java
var safeNames = java.util.stream.Stream.of(
        "A", null, "B")
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

Việc bỏ `null` chỉ đúng nếu nghiệp vụ cho phép; nếu `null` biểu diễn một giá trị có ý nghĩa thì phải xử lý khác. Đặc biệt với giá trị là object mutable, unmodifiable collection cũng không tự tạo **deep immutability** cho object phần tử.

## 9. Serialization và thread safety không suy luận từ debugger

Một khi Javadoc ghi **không có bảo đảm về serializability/thread safety**, test chạy trên một phiên bản JDK không biến hai thuộc tính đó thành cam kết. Ngay cả nếu object một lần chạy:

- `instanceof java.io.Serializable` cho kết quả `true`; hoặc
- có class name trông như `ArrayList`/`HashSet`; hoặc
- vượt qua một bài test đa luồng nhỏ,

thì kết luận “mọi kết quả của collector này đều serializable/thread-safe” vẫn **không hợp lệ**.

Nếu cần serialization ổn định qua ranh giới hệ thống, nên dùng DTO/formats có hợp đồng rõ và chọn một cấu trúc dữ liệu kiểm soát được. Nếu cần truy cập đồng thời, hãy thiết kế concurrency bằng ownership, đồng bộ hóa, immutable elements hoặc các concurrent collection thích hợp; đừng đoán từ việc stream dùng `parallel()` hay collector đang hoạt động trong pipeline song song.

`Collectors.toCollection(ArrayList::new)` cũng **không biến `ArrayList` thành thread-safe**. Supplier kiểm soát **lớp collection**, không tự tạo một hợp đồng đồng thời.

## 10. Tại sao `var` không giải quyết được giả định sai?

Vì đây là module Java 10, nhiều khai báo dùng `var`. Nhưng `var` chỉ suy luận từ **kiểu tĩnh của biểu thức khởi tạo**:

```java
var unknownImplementation = java.util.stream.Stream.of("a", "b")
        .collect(java.util.stream.Collectors.toList());

var controlledImplementation = java.util.stream.Stream.of("a", "b")
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));
```

- `unknownImplementation` có kiểu tĩnh `List<String>`. `var` không nhìn vào object runtime để đổi kiểu thành `ArrayList<String>`.
- `controlledImplementation` được suy luận có kiểu tĩnh `ArrayList<String>` nhờ chữ ký generic và supplier của `toCollection`.
- Khi type của collector là interface, tránh ép kiểu xuống implementation chỉ để sử dụng method chuyên biệt. Khi yêu cầu đã là implementation cụ thể, **nói rõ ngay trong collector**.

Ví dụ sau **không biên dịch** nếu bỏ comment:

```java
// unknownImplementation.ensureCapacity(100);
// Vì kiểu tĩnh List không có ensureCapacity().
```

Trong khi:

```java
controlledImplementation.ensureCapacity(100); // Hợp lệ.
```

Đừng suy luận kiểu từ việc IDE hiển thị class runtime khi debug. Khác biệt giữa **static type** và **runtime implementation** vẫn có ý nghĩa như trong các khai báo Java tường minh.

## 11. Ví dụ hoàn chỉnh Java 17+: kiểm chứng đúng hợp đồng thay vì tên class

Tạo tệp **`CollectorImplementationContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class CollectorImplementationContractDemo {
    static final class Token {
        final String id;
        final String label;

        Token(String id, String label) {
            this.id = id;
            this.label = label;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Token token && id.equals(token.id);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id);
        }
    }

    private static void tryEdit(String name, Runnable change) {
        try {
            change.run();
            System.out.println(name + "=success");
        } catch (UnsupportedOperationException ex) {
            System.out.println(name + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<String> defaultList = Stream.of("c", "a", "b")
                .collect(Collectors.toList());
        Set<String> defaultSet = Stream.of("b", "a", "b", "c")
                .collect(Collectors.toSet());

        System.out.println("toList=" + defaultList);
        System.out.println("toSet sorted view=" + new TreeSet<>(defaultSet));

        ArrayList<String> editableList = Stream.of("c", "a", "b")
                .collect(Collectors.toCollection(ArrayList::new));
        editableList.add("d");
        editableList.sort(Comparator.naturalOrder());
        System.out.println("ArrayList controlled=" + editableList);

        LinkedHashSet<String> insertionOrder = Stream.of("b", "a", "b", "c")
                .collect(Collectors.toCollection(LinkedHashSet::new));
        insertionOrder.add("d");
        System.out.println("LinkedHashSet controlled=" + insertionOrder);

        List<String> noEditList = Stream.of("c", "a", "b")
                .collect(Collectors.toUnmodifiableList());
        Set<String> noEditSet = Stream.of("b", "a", "b", "c")
                .collect(Collectors.toUnmodifiableSet());
        System.out.println("unmodifiableList=" + noEditList);
        System.out.println("unmodifiableSet size=" + noEditSet.size());
        tryEdit("unmodifiableList.add", () -> noEditList.add("d"));
        tryEdit("unmodifiableSet.add", () -> noEditSet.add("d"));

        List<String> streamResult = Stream.of("c", "a", "b").toList();
        System.out.println("Stream.toList=" + streamResult);
        tryEdit("Stream.toList.set", () -> streamResult.set(0, "x"));

        ArrayList<String> fromUnmodifiable = new ArrayList<>(streamResult);
        fromUnmodifiable.set(0, "x");
        System.out.println("mutable copy=" + fromUnmodifiable);

        var first = new Token("ID-1", "first");
        var second = new Token("ID-1", "second");
        var duplicates = Stream.of(first, second)
                .collect(Collectors.toUnmodifiableSet());
        System.out.println("equal tokens retained=" + duplicates.size());

        try {
            Stream.of("a", (String) null)
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException ex) {
            System.out.println("unmodifiableList null=NullPointerException");
        }

        try {
            Stream.of("a", (String) null)
                    .collect(Collectors.toUnmodifiableSet());
        } catch (NullPointerException ex) {
            System.out.println("unmodifiableSet null=NullPointerException");
        }
    }
}
```

Biên dịch theo Java 17 (dùng `Stream.toList()` và pattern matching cho `instanceof`):

```bash
javac --release 17 CollectorImplementationContractDemo.java
java CollectorImplementationContractDemo
```

Đầu ra chính xác đã được kiểm tra:

```text
toList=[c, a, b]
toSet sorted view=[a, b, c]
ArrayList controlled=[a, b, c, d]
LinkedHashSet controlled=[b, a, c, d]
unmodifiableList=[c, a, b]
unmodifiableSet size=3
unmodifiableList.add=UnsupportedOperationException
unmodifiableSet.add=UnsupportedOperationException
Stream.toList=[c, a, b]
Stream.toList.set=UnsupportedOperationException
mutable copy=[x, a, b]
equal tokens retained=1
unmodifiableList null=NullPointerException
unmodifiableSet null=NullPointerException
```

Giải thích chính xác:

1. `toList=[c, a, b]` cho thấy dữ liệu từ stream có encounter order được lưu theo thứ tự. **Không** dựa vào điều này để xác định tên class implementation.
2. `toSet sorted view=[a, b, c]` là kết quả khi **chủ động tạo `TreeSet` từ set mặc định chỉ để hiển thị**; nó không chứng minh `Collectors.toSet()` đã trả `TreeSet`.
3. `ArrayList controlled` minh họa supplier `ArrayList::new`: có thể `add` và `sort` theo contract của `ArrayList`.
4. `LinkedHashSet controlled` giữ thứ tự chèn trong pipeline sequential và chỉ giữ một phần tử `"b"`.
5. `toUnmodifiableList` và `toUnmodifiableSet` có hành vi unmodifiable được cam kết; các phép `add` được bắt lỗi có chủ đích.
6. `Stream.toList()` từ Java 16 cũng không cho `set`; muốn sửa thì tạo một `ArrayList` mới.
7. Hai object `Token` có cùng `id` và khác `label` được xem là bằng nhau; `toUnmodifiableSet` giữ một object. Chương trình **không in label được giữ** vì đặc tả không hứa chọn object đầu hay cuối.
8. Hai collector unmodifiable đều từ chối phần tử `null`.

Lệnh chạy dùng Java 17 nhưng các collector được giới thiệu từ Java 10 vẫn là kiến thức có hiệu lực trên JDK mới. Với dự án đặt giới hạn Java 10, bỏ lời gọi `Stream.toList()` và đổi cú pháp `instanceof Token token` thành kiểu kiểm tra/cast cổ điển; nguyên tắc về `Collectors.toList/toSet/toCollection/toUnmodifiable*` không đổi.

## 12. Chọn API theo hợp đồng bạn thực sự cần

| Nhu cầu | API phù hợp | Lý do |
| --- | --- | --- |
| Tích lũy thành list, không phụ thuộc implementation | `collect(Collectors.toList())` | Giao diện `List`, thứ tự phần tử theo encounter order |
| Tích lũy thành set, không phụ thuộc implementation/thứ tự | `collect(Collectors.toSet())` | Giao diện `Set`, loại phần tử trùng theo hợp đồng |
| Muốn list **unmodifiable** từ Java 10 | `collect(Collectors.toUnmodifiableList())` | Hợp đồng unmodifiable rõ, từ chối `null` |
| Muốn set **unmodifiable** từ Java 10 | `collect(Collectors.toUnmodifiableSet())` | Không sửa, không chấp nhận `null` |
| Muốn list unmodifiable trên Java 16+ | `stream.toList()` | Cú pháp trực tiếp, không cho mutator |
| Cần `ArrayList` editable rõ ràng | `collect(Collectors.toCollection(ArrayList::new))` | Supplier và kiểu trả về xác định |
| Cần `LinkedHashSet` theo thứ tự chèn | `collect(Collectors.toCollection(LinkedHashSet::new))` | Implementation rõ, giữ insertion order |
| Cần `TreeSet` sắp thứ tự | `collect(Collectors.toCollection(TreeSet::new))` | Sorted set và quy tắc so sánh rõ |
| Nhận kết quả unmodifiable nhưng muốn sửa bản riêng | `new ArrayList<>(result)` hoặc `new LinkedHashSet<>(result)` | Sao chép sang object mutable tách biệt |

Nếu hệ thống không cần tính chất riêng của class, **không nên phụ thuộc vào class**. Khi class là điều kiện thật sự của thuật toán, đặt yêu cầu đó trong code theo cách được Javadoc công bố, không dựa vào cast hoặc việc quan sát kết quả tại runtime.

## 13. Những lỗi review thường gặp

### 13.1. Cast kết quả `toList()` thành `ArrayList`

```java
var list = java.util.stream.Stream.of("A", "B")
        .collect(java.util.stream.Collectors.toList());

// Rủi ro ClassCastException do không có bảo đảm concrete type:
// java.util.ArrayList<String> assumed =
//         (java.util.ArrayList<String>) list;
```

Thay bằng `toCollection(ArrayList::new)` hoặc dùng một constructor `new ArrayList<>(list)`. Không cần cast khi đã có supplier.

### 13.2. Nghĩ `toSet()` luôn trả `HashSet`

Sai. Đây là một cách triển khai có thể quan sát, không phải API contract. Phương thức collector còn được công bố là **unordered**. Dùng `toCollection(HashSet::new)` khi cần `HashSet` cụ thể, `LinkedHashSet::new` khi cần thứ tự chèn, hoặc `TreeSet::new` khi cần sắp xếp.

### 13.3. Nghĩ `Collectors.toList()` chắc chắn mutable

Sai. Javadoc nói **không bảo đảm tính mutable**. Nếu cần sửa, hãy tạo collection mutable bằng supplier hoặc constructor rõ ràng.

### 13.4. Nghĩ hai tên `toList` có cùng hợp đồng

Sai. `Stream.toList()` từ Java 16 **cam kết unmodifiable**, còn `Collectors.toList()` không cam kết mutable hay unmodifiable. Đổi một cú pháp sang cú pháp kia có thể làm lệnh `add` vốn đang hoạt động trên một runtime bị `UnsupportedOperationException`.

### 13.5. Dùng kết quả `Set` để kiểm tra thứ tự hiển thị

Sai. `toSet()` và `toUnmodifiableSet()` là unordered collectors. Nếu thứ tự là yêu cầu sản phẩm, chọn collection phù hợp ngay từ đầu hoặc sắp xếp bản hiển thị độc lập.

### 13.6. Cho rằng `toUnmodifiableSet()` luôn chọn bản trùng xuất hiện đầu

Sai. Khi hai object `equals()` bằng nhau nhưng dữ liệu hiển thị khác nhau, collector có thể giữ một bản **tùy ý**. Cần chính sách merge trước khi collect nếu bản nào được giữ có ý nghĩa.

### 13.7. Thấy triển khai là `Serializable` rồi mặc định dữ liệu luôn serialize được

Sai. Những collector không cam kết serialization không phải abstraction cho một format lưu trữ ổn định; khi cần điều này phải kiểm tra hợp đồng của từng kiểu và tất cả phần tử.

### 13.8. Nghĩ collection unmodifiable làm phần tử bất biến

Sai. Danh sách/tập hợp có thể không sửa được qua interface nhưng object phần tử vẫn mutable. Nếu `equals()/hashCode()` của phần tử Set phụ thuộc field mutable, việc thay đổi có thể làm hành vi tập hợp không nhất quán. Chọn immutable element khi cần bộ dữ liệu thực sự ổn định.

### 13.9. Cho rằng `parallelStream()` biến collection kết quả thành thread-safe

Sai. Các cơ chế tích lũy song song và đặc tính thread-safety của **collection cuối cùng** là hai vấn đề khác nhau. Nếu chia sẻ mutable collection giữa nhiều thread, thiết kế đồng bộ hóa/ownership riêng.

## 14. Checklist kiểm tra khi viết và review Collector

- [ ] Code chỉ dựa vào API `List`/`Set` nếu collector không cam kết concrete implementation.
- [ ] Không cast đầu ra `Collectors.toList()` sang `ArrayList` hay `toSet()` sang `HashSet` dựa trên một lần debug.
- [ ] Nếu cần concrete class, dùng `toCollection(Supplier)` với class mục tiêu.
- [ ] Nếu cần mutable, chọn loại collection mutable hoặc tạo bản mutable copy rõ ràng.
- [ ] Nếu cần unmodifiable, chọn `toUnmodifiableList/Set` (Java 10+) hoặc `Stream.toList()` (Java 16+) phù hợp.
- [ ] Nhận diện chính xác chính sách `null` của từng API; không tự thay collector khi dữ liệu nullable.
- [ ] Không dựa vào thứ tự duyệt của Set tạo từ unordered collector.
- [ ] Nếu phần tử Set có thể trùng theo `equals()`, đã xác định xử lý/merge trước nếu quan trọng bản nào còn lại.
- [ ] Không dùng `getClass()`, `==` hoặc serialization thành cơ sở suy ra những hợp đồng Javadoc không cam kết.
- [ ] Không coi một mutable result collection tự động thread-safe.
- [ ] Tính bất biến của object phần tử đã được xem xét riêng, không đánh đồng với unmodifiable collection.
- [ ] Bài test kiểm tra **hành vi cần thiết** thay vì tên implementation tình cờ trên một JDK.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `Collectors.toList()` có bảo đảm trả về `ArrayList` không?

**Đáp án:** Không. Nó trả một `List` và không cam kết class triển khai cụ thể, mutability, serializability hoặc thread-safety.

**Câu 2.** Nếu cần gọi `ensureCapacity()` trên kết quả, nên viết gì?

**Đáp án:** Dùng `collect(Collectors.toCollection(ArrayList::new))` để nhận `ArrayList` thực sự, hoặc chủ động tạo `new ArrayList<>(result)`. Không cast kết quả mặc định theo giả định.

**Câu 3.** Với stream `"b", "a", "b"`, có thể bảo đảm `Collectors.toSet()` duyệt theo thứ tự `"b", "a"` không?

**Đáp án:** Không. `toSet()` là unordered collector. Muốn thứ tự chèn, dùng `toCollection(LinkedHashSet::new)` từ stream có encounter order.

**Câu 4.** `Collectors.toUnmodifiableList()` và `Stream.toList()` có cùng thời điểm xuất hiện trong Java không?

**Đáp án:** Không. Collector unmodifiable list có từ Java 10; phương thức trực tiếp `Stream.toList()` có từ Java 16. Cả hai trả list không sửa được, nhưng không nên suy luận chúng có cùng class triển khai.

**Câu 5.** Kết quả `Collectors.toList()` hiện tại gọi `add` thành công. Có thể viết production code dựa vào hành vi đó không?

**Đáp án:** Không nên. Đặc tả collector không bảo đảm mutable; muốn một list mutable thì yêu cầu rõ bằng `toCollection(ArrayList::new)`.

**Câu 6.** Hai object có cùng ID theo `equals()` nhưng nhãn khác nhau được đưa vào `toUnmodifiableSet()`. Có bảo đảm nhãn nào được giữ không?

**Đáp án:** Không. Collector chọn một phần tử trùng bất kỳ. Nếu chọn bản nào quan trọng, hãy xử lý trước bằng quy tắc nghiệp vụ cụ thể.

**Câu 7.** `toUnmodifiableList()` có tự bỏ phần tử `null` hay cho phép giữ chúng?

**Đáp án:** Không. Collector này từ chối `null` bằng `NullPointerException`. Cần xử lý null theo yêu cầu nghiệp vụ trước khi thu thập.

**Câu 8.** Tại sao in `new TreeSet<>(resultSet)` không chứng minh `Collectors.toSet()` là sorted collector?

**Đáp án:** Thứ tự đến từ việc tạo **một TreeSet mới**, không từ Set do collector mặc định sinh ra.

**Câu 9.** `var result = stream.collect(Collectors.toList());` có suy luận kiểu tĩnh `ArrayList` nếu runtime đang dùng `ArrayList` không?

**Đáp án:** Không. `var` dựa vào kiểu khai báo của biểu thức, tức `List<T>`. Khi dùng `toCollection(ArrayList::new)` thì kiểu trả về suy luận có thể là `ArrayList<T>`.

**Câu 10.** Có thể dùng kết quả `toCollection(ArrayList::new)` để chia sẻ giữa nhiều thread mà không đồng bộ vì collector hỗ trợ stream song song không?

**Đáp án:** Không. `ArrayList` không tự thread-safe; cách collect dữ liệu và việc truy cập kết quả sau đó là hai khía cạnh riêng.

## Tài liệu chính thức còn áp dụng

- [Java SE — `Collectors.toList`, `toSet`, `toCollection`, `toUnmodifiableList`, `toUnmodifiableSet`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): hợp đồng kiểu kết quả, độ ổn định, mutability và unordered collector.
- [Java SE — `Stream.toList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#toList()): list unmodifiable từ Java 16, không bảo đảm implementation type hoặc serializability.
- [Java SE — `Collection`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html): optional mutator, unmodifiable collection và sự khác biệt với deep immutable.
- [Java SE — `List.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): cách tạo một snapshot unmodifiable từ một collection.
- [Java SE — `LinkedHashSet`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedHashSet.html): bảo đảm iteration theo thứ tự chèn.
- [Java SE — `TreeSet`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html): sorted set theo natural ordering hoặc comparator.
- [Oracle — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): đặc tính của `toUnmodifiable*`, thứ tự duyệt và cách chọn tùy ý phần tử trùng.
