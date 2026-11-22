# List.copyOf, Set.copyOf, Map.copyOf và giới hạn sao chép nông trong Java 17

**Chủ đề:** Java 17 → Collection và Stream  
**Trọng tâm:** Tạo collection không thể sửa bằng `List.copyOf`, `Set.copyOf`, `Map.copyOf`; hiểu khác biệt giữa bản sao và view không thể sửa; nhận diện giới hạn của sao chép nông (*shallow copy*) khi phần tử hoặc giá trị bên trong vẫn có thể thay đổi.

Từ Java 10, Java cung cấp ba phương thức `copyOf` để tạo một `List`, `Set` hoặc `Map` không thể sửa từ collection hiện có. Các phương thức này có sẵn trong Java 17 và thường được dùng khi muốn trả dữ liệu ra khỏi một lớp mà không để người gọi thêm, xóa hoặc thay thế phần tử trong collection.

Tuy nhiên, **collection không thể sửa không đồng nghĩa với dữ liệu bên trong hoàn toàn bất biến**. `copyOf` chỉ tạo một collection mới ở mức cấu trúc; các đối tượng được tham chiếu vẫn là những đối tượng cũ. Nếu phần tử là `StringBuilder`, đối tượng nghiệp vụ mutable hoặc một collection lồng nhau, người dùng vẫn có thể thay đổi trạng thái bên trong qua tham chiếu đó.

## 1. Ba phương thức copyOf

Java SE 17 cung cấp:

| Phương thức | Tham số đầu vào | Kết quả |
| --- | --- | --- |
| `List.copyOf(Collection<? extends E>)` | Một `Collection` | `List<E>` không thể sửa, giữ thứ tự lặp và các phần tử trùng lặp. |
| `Set.copyOf(Collection<? extends E>)` | Một `Collection` | `Set<E>` không thể sửa, loại bỏ phần tử trùng theo quy tắc bằng nhau của `Set`. |
| `Map.copyOf(Map<? extends K, ? extends V>)` | Một `Map` | `Map<K,V>` không thể sửa, giữ các ánh xạ key-value. |

Ví dụ:

~~~java
import java.util.List;
import java.util.Set;
import java.util.Map;

public class CopyOfIntro {
    public static void main(String[] args) {
        List<String> names = List.copyOf(List.of("An", "Binh", "An"));
        Set<String> roles = Set.copyOf(List.of("USER", "ADMIN", "USER"));
        Map<String, Integer> scores = Map.copyOf(
            Map.of("An", 90, "Binh", 85)
        );

        System.out.println(names);
        System.out.println(roles);
        System.out.println(scores);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~shell
javac --release 17 CopyOfIntro.java
java CopyOfIntro
~~~

Danh sách `names` giữ cả hai lần xuất hiện của `"An"` vì `List` cho phép phần tử trùng. Tập `roles` chỉ giữ một phần tử `"USER"` vì `Set` không chứa hai phần tử bằng nhau. Thứ tự hiển thị của `Set` và `Map` không được các phương thức `copyOf` bảo đảm.

## 2. Tính chất không thể sửa (unmodifiable)

Collection trả về từ `copyOf` không cho phép thay đổi cấu trúc bằng các thao tác như:

- `add`, `addAll`: thêm phần tử.
- `remove`, `removeAll`, `removeIf`, `clear`: xóa phần tử.
- `List.set`: thay phần tử tại vị trí.
- Các thao tác sửa trên iterator/list iterator.
- `Map.put`, `putAll`, `remove`, `replace`, `compute`, `merge`, `clear`.
- `Map.Entry.setValue` trên entry lấy từ map không thể sửa.

Nếu gọi một thao tác sửa, collection không thể sửa ném `UnsupportedOperationException`.

~~~java
import java.util.List;

public class UnmodifiableListDemo {
    public static void main(String[] args) {
        List<String> names = List.copyOf(List.of("An", "Binh"));

        System.out.println(names.get(0));
        System.out.println(names.size());

        names.add("Chi"); // UnsupportedOperationException
    }
}
~~~

Tính chất này hữu ích khi:

1. Một lớp muốn trả danh sách kết quả mà caller chỉ được đọc.
2. Một cấu hình được tạo xong rồi dùng trong phần còn lại của chương trình.
3. Một API công khai muốn ngăn caller vô tình thêm/xóa ánh xạ nội bộ.
4. Một luồng xử lý cần giữ cấu trúc collection ổn định sau khi tạo.

**Không thể sửa collection** chỉ giới hạn những thao tác trên chính collection đó. Nó không cấm thay đổi trạng thái của từng đối tượng được collection tham chiếu; phần này sẽ được phân tích ở mục sao chép nông.

## 3. Khác biệt giữa List.copyOf và Collections.unmodifiableList

Đây là điểm rất quan trọng khi chọn API. `Collections.unmodifiableList(source)` tạo một **view chỉ đọc** dựa trên collection nguồn. `List.copyOf(source)` tạo một kết quả không thể sửa, tách khỏi các thay đổi cấu trúc tiếp theo của một nguồn mutable thông thường.

### 3.1. View không thể sửa vẫn có thể thay đổi khi nguồn đổi

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableViewDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> view = Collections.unmodifiableList(source);

        source.add("B"); // Sửa collection gốc.

        System.out.println(view); // [A, B]

        // view.add("C"); // UnsupportedOperationException
    }
}
~~~

`view.add("C")` bị chặn, nhưng `source.add("B")` vẫn thành công. Vì `view` phản ánh collection `source`, caller có thể nhìn thấy phần tử mới dù không thể sửa qua `view`.

### 3.2. copyOf tách khỏi thay đổi cấu trúc tiếp theo của nguồn mutable

~~~java
import java.util.ArrayList;
import java.util.List;

public class CopyOfSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> snapshot = List.copyOf(source);
        source.add("B");

        System.out.println(source);   // [A, B]
        System.out.println(snapshot); // [A]
    }
}
~~~

`snapshot` không phản ánh phần tử `"B"` được thêm vào `source` sau khi tạo. Đây là khác biệt thực tế giữa một **kết quả không thể sửa, tách khỏi thay đổi cấu trúc nguồn** và một **view không thể sửa nhưng còn được nguồn mutable điều khiển**.

### 3.3. Bảng so sánh

| Tiêu chí | `List.copyOf(source)` | `Collections.unmodifiableList(source)` |
| --- | --- | --- |
| Caller thêm/xóa qua kết quả | Không cho phép | Không cho phép |
| Nguồn mutable thay đổi cấu trúc sau khi tạo | Kết quả không phản ánh thay đổi cấu trúc đó | View phản ánh thay đổi từ nguồn |
| Tạo một bản sao cấu trúc | Có, với nguồn mutable thông thường | Không; chỉ tạo view |
| Cho phép phần tử `null` | Không | Phụ thuộc collection nguồn; wrapper không tự loại null |
| Phần tử mutable bên trong | Vẫn có thể thay đổi | Vẫn có thể thay đổi |
| Dùng khi | Cần kết quả không thể sửa, độc lập với thay đổi cấu trúc tiếp theo của nguồn mutable | Cần bọc một collection có sẵn thành view chỉ đọc |

### 3.4. Lưu ý với nguồn vốn đã không thể sửa

Javadoc cho phép implementation tận dụng collection đầu vào vốn đã không thể sửa, thay vì luôn tạo một object mới. Vì vậy:

- Không dựa vào việc `copyOf` luôn trả về một instance khác nguồn.
- Không dùng `==`, `System.identityHashCode` hoặc khóa đồng bộ dựa trên identity của collection kết quả.
- Hãy dựa vào hợp đồng về nội dung và tính không thể sửa, không dựa vào identity của object.

Nếu nguồn là một **view không thể sửa nhưng được backing collection mutable thay đổi**, và ứng dụng cần một snapshot cấu trúc độc lập chắc chắn, có thể tạo một collection mutable trung gian trước rồi gọi `copyOf`:

~~~java
List<String> stableSnapshot = List.copyOf(
    new ArrayList<>(readOnlyView)
);
~~~

`ArrayList` trung gian nhận các phần tử tại thời điểm sao chép; `List.copyOf` sau đó tạo kết quả không thể sửa từ danh sách trung gian này. Thao tác vẫn chỉ sao chép nông: tham chiếu phần tử được giữ nguyên.

## 4. List.copyOf: giữ thứ tự và phần tử trùng

`List.copyOf` nhận một `Collection` và tạo danh sách không thể sửa theo thứ tự lặp của collection đầu vào.

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
            List.of("Java", "Kotlin", "Java")
        );

        List<String> copy = List.copyOf(source);

        System.out.println(copy); // [Java, Kotlin, Java]
        System.out.println(copy.get(0)); // Java
        System.out.println(copy.get(2)); // Java
    }
}
~~~

Các đặc điểm:

- Thứ tự phần tử được giữ theo thứ tự lặp của nguồn.
- Các phần tử trùng lặp được giữ nguyên.
- Không cho phép phần tử `null`.
- Kết quả không thể thêm, xóa hoặc thay thế phần tử.
- Các đối tượng phần tử không được clone; chỉ các tham chiếu được đưa vào danh sách kết quả.

`List.copyOf` phù hợp khi muốn trả danh sách theo đúng thứ tự đã xác định, ví dụ danh sách bước trong quy trình, các dòng kết quả hoặc thứ tự ưu tiên.

## 5. Set.copyOf: loại phần tử trùng và không bảo đảm thứ tự

`Set.copyOf` tạo một tập không thể sửa từ collection đầu vào.

~~~java
import java.util.List;
import java.util.Set;

public class SetCopyDemo {
    public static void main(String[] args) {
        List<String> source = List.of(
            "ADMIN", "USER", "USER", "AUDITOR"
        );

        Set<String> roles = Set.copyOf(source);

        System.out.println(roles);
        System.out.println(roles.contains("ADMIN")); // true
        System.out.println(roles.size()); // 3
    }
}
~~~

### 5.1. Điều gì xảy ra với phần tử trùng?

Nếu collection nguồn chứa các phần tử bằng nhau theo `equals`, kết quả `Set` chỉ chứa một phần tử đại diện cho mỗi giá trị. Javadoc quy định nếu đầu vào có phần tử trùng, **một phần tử bất kỳ trong nhóm trùng** được giữ lại.

~~~java
record User(String id, String displayName) {
}

List<User> source = List.of(
    new User("u1", "An"),
    new User("u1", "Nguyen An")
);

Set<User> users = Set.copyOf(source);
~~~

Hai record `User` trên có cùng `id` nhưng khác `displayName`, vì vậy theo `equals` mặc định của record, chúng **không bằng nhau** do mọi component đều tham gia so sánh. Kết quả sẽ chứa cả hai.

Nếu muốn định nghĩa hai user có cùng `id` là trùng, cần thiết kế kiểu/logic tập hợp theo đúng khóa nghiệp vụ; không được giả định `Set.copyOf` tự hiểu rằng `id` là khóa duy nhất.

Đối với hai phần tử thật sự bằng nhau theo `equals`, không dựa vào identity của phần tử nào được giữ lại. Nếu việc chọn instance đại diện có ý nghĩa, hãy tự xử lý quy tắc đó trước khi gọi `Set.copyOf`.

### 5.2. Thứ tự của Set

`Set.copyOf` **không bảo đảm thứ tự lặp** giống collection đầu vào. Không nên viết logic nghiệp vụ dựa vào phần tử đầu tiên khi duyệt set kết quả.

Nếu cần duy trì thứ tự chèn, hãy dùng một cấu trúc có quy định thứ tự như `LinkedHashSet` và bọc bản sao bằng `Collections.unmodifiableSet`:

~~~java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;

Set<String> orderedRoles = Collections.unmodifiableSet(
    new LinkedHashSet<>(source)
);
~~~

Ở đây `LinkedHashSet` giữ thứ tự chèn. `unmodifiableSet` là view trên bản sao `LinkedHashSet` vừa tạo; nếu không giữ tham chiếu tới set mutable trung gian ở nơi khác, cấu trúc kết quả sẽ không bị caller bên ngoài sửa.

## 6. Map.copyOf: sao chép các ánh xạ key-value

`Map.copyOf` tạo map không thể sửa từ một map nguồn:

~~~java
import java.util.HashMap;
import java.util.Map;

public class MapCopyDemo {
    public static void main(String[] args) {
        Map<String, Integer> source = new HashMap<>();
        source.put("An", 90);
        source.put("Binh", 85);

        Map<String, Integer> scores = Map.copyOf(source);
        source.put("Chi", 95);

        System.out.println(source);
        System.out.println(scores);
        System.out.println(scores.get("An"));
    }
}
~~~

`Map.copyOf` giữ các ánh xạ key-value có trong map nguồn tại thời điểm tạo kết quả. Các thao tác thay đổi map kết quả bị cấm.

### 6.1. Không bảo đảm thứ tự lặp

Map nguồn có thể là `LinkedHashMap` hoặc `TreeMap`, nhưng `Map.copyOf` không hứa giữ thứ tự lặp của nguồn. Nếu thứ tự là một phần của hợp đồng API, hãy chọn cách tạo bản sao và wrapper có thứ tự rõ ràng:

~~~java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Integer> orderedCopy = Collections.unmodifiableMap(
    new LinkedHashMap<>(source)
);
~~~

`LinkedHashMap` giữ thứ tự chèn từ các entry được duyệt trong `source`; wrapper không thể sửa ngăn caller thay đổi map thông qua tham chiếu kết quả.

Nếu cần thứ tự theo khóa, có thể dùng `TreeMap` trước khi bọc:

~~~java
import java.util.Collections;
import java.util.Map;
import java.util.TreeMap;

Map<String, Integer> sortedCopy = Collections.unmodifiableMap(
    new TreeMap<>(source)
);
~~~

### 6.2. Key và value phải khác null

`Map.copyOf` không chấp nhận key hoặc value `null`:

~~~java
import java.util.HashMap;
import java.util.Map;

Map<String, String> source = new HashMap<>();
source.put("name", "An");
source.put("nickname", null);

// Ném NullPointerException vì value của nickname là null.
Map<String, String> copy = Map.copyOf(source);
~~~

Điều này khác với một số implementation như `HashMap`, vốn cho phép một key null và nhiều value null. Trước khi dùng `Map.copyOf`, hãy xác định rõ chính sách null của dữ liệu.

Nếu `null` mang ý nghĩa nghiệp vụ, hãy biểu diễn nó theo cách rõ ràng, chẳng hạn:

- Bỏ entry nếu không có giá trị.
- Dùng kiểu giá trị biểu diễn trạng thái có/không có.
- Dùng `Optional` ở biên API thích hợp, không mặc định biến mọi field thành `Optional`.
- Tách rõ “không có key” và “key có value rỗng” theo hợp đồng dữ liệu.

Không thay null bằng một chuỗi giả như `"null"` nếu chuỗi đó có thể là dữ liệu hợp lệ.

## 7. Null bị từ chối ở cả ba phương thức

Các collection không thể sửa được tạo bởi `copyOf` không cho phép phần tử null:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.Map;

List<String> listWithNull = Arrays.asList("A", null);
Set<String> setWithNull = Set.of("A"); // set này không có null

// Cả hai lời gọi sau đều ném NullPointerException:
// List<String> list = List.copyOf(listWithNull);
// Set<String> set = Set.copyOf(listWithNull);

Map<String, String> mapWithNull = new java.util.HashMap<>();
mapWithNull.put("key", null);
// Map<String, String> map = Map.copyOf(mapWithNull);
~~~

`List.copyOf` và `Set.copyOf` ném `NullPointerException` nếu collection đầu vào là null hoặc có phần tử null. `Map.copyOf` ném `NullPointerException` nếu map đầu vào là null, hoặc có key/value null.

Lý do thực tế là các collection không thể sửa của API này hướng đến mô hình dữ liệu không có null, giúp caller ít phải xử lý trạng thái mơ hồ. Nếu miền nghiệp vụ cho phép null, hãy xử lý trước khi tạo bản sao.

## 8. Sao chép nông (shallow copy) là gì?

`List.copyOf`, `Set.copyOf`, `Map.copyOf` sao chép **cấu trúc collection và các tham chiếu đến phần tử**, chứ không tạo bản sao độc lập của từng đối tượng bên trong.

Ví dụ, với:

~~~java
List<StringBuilder> source = ...;
List<StringBuilder> copy = List.copyOf(source);
~~~

Hai collection khác nhau về cấu trúc, nhưng `source.get(0)` và `copy.get(0)` tham chiếu đến **cùng một `StringBuilder`**.

Sơ đồ:

~~~text
Trước khi copy:

source ──> [ reference A ] ──> StringBuilder("draft")

Sau List.copyOf:

source ──> [ reference A ] ──┐
                            ├──> cùng StringBuilder("draft")
copy   ──> [ reference A ] ──┘
~~~

Thay đổi cấu trúc `source` sau khi copy không làm cấu trúc `copy` thay đổi. Nhưng thay đổi đối tượng được tham chiếu sẽ được nhìn thấy qua cả hai collection.

### 8.1. Ví dụ chứng minh sao chép nông

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShallowCopyDemo {
    public static void main(String[] args) {
        StringBuilder note = new StringBuilder("draft");

        List<StringBuilder> source = new ArrayList<>();
        source.add(note);

        List<StringBuilder> copy = List.copyOf(source);

        source.clear();             // Chỉ xóa phần tử khỏi source.
        note.append(" updated");    // Thay đổi đối tượng được chia sẻ.

        System.out.println(source.size()); // 0
        System.out.println(copy.size());   // 1
        System.out.println(copy.get(0));   // draft updated
    }
}
~~~

Kết quả cho thấy hai điều cùng đúng:

1. `copy` độc lập với việc thêm/xóa phần tử của `source`.
2. `copy` vẫn thấy trạng thái mới của `StringBuilder`, vì hai collection giữ cùng tham chiếu tới đối tượng đó.

Đây là **shallow copy**, không phải deep copy.

## 9. Sao chép nông với Map cũng có giới hạn tương tự

Map chứa cả key và value. `Map.copyOf` sao chép các ánh xạ, nhưng các object key/value không được clone.

~~~java
import java.util.HashMap;
import java.util.Map;

public class ShallowMapCopyDemo {
    public static void main(String[] args) {
        StringBuilder description = new StringBuilder("new");

        Map<String, StringBuilder> source = new HashMap<>();
        source.put("status", description);

        Map<String, StringBuilder> copy = Map.copyOf(source);

        source.put("other", new StringBuilder("value"));
        description.append(" -> reviewed");

        System.out.println(source.size()); // 2
        System.out.println(copy.size());   // 1
        System.out.println(copy.get("status")); // new -> reviewed
    }
}
~~~

Map kết quả không nhận entry `"other"` được thêm vào map nguồn sau khi copy, nhưng value `"status"` vẫn trỏ đến `StringBuilder` cũ. Khi object đó thay đổi, đọc qua `copy.get("status")` cũng thấy thay đổi.

Nếu key là object mutable và các trường tham gia `equals`/`hashCode` bị thay đổi sau khi đưa vào map, cấu trúc hash-based map có thể trở nên khó truy cập hoặc vi phạm kỳ vọng của ứng dụng. Vì vậy, key nên là kiểu bất biến hoặc có quy tắc equality/hash ổn định.

## 10. Muốn deep copy thì cần làm gì?

Java không thể tự động deep copy mọi object vì không biết:

- Đối tượng cần sao chép những trường nào.
- Trường nào nên được chia sẻ (ví dụ `String`, enum, đối tượng immutable).
- Trường nào cần tạo bản sao mới.
- Quan hệ tham chiếu vòng hoặc object graph được xử lý ra sao.
- Có được phép sao chép tài nguyên như file handle, socket, thread hay không.

Vì thế, `copyOf` không gọi constructor clone, không gọi `clone()` và không tự tuần tự hóa/deserialization để tạo object mới.

### 10.1. Tự định nghĩa thao tác copy cho phần tử mutable

Ví dụ một kiểu mutable:

~~~java
final class Task {
    private String title;
    private int progress;

    Task(String title, int progress) {
        this.title = title;
        this.progress = progress;
    }

    String title() {
        return title;
    }

    int progress() {
        return progress;
    }

    void setProgress(int progress) {
        this.progress = progress;
    }

    Task copy() {
        return new Task(title, progress);
    }

    @Override
    public String toString() {
        return title + " (" + progress + "%)";
    }
}
~~~

Tạo danh sách phần tử mới:

~~~java
import java.util.List;

List<Task> source = List.of(
    new Task("Read", 20),
    new Task("Practice", 40)
);

List<Task> deepCopiedElements = List.copyOf(
    source.stream()
        .map(Task::copy)
        .toList()
);
~~~

Ở đây:

- `Task.copy()` tạo object `Task` mới với trạng thái được sao chép.
- `map(Task::copy)` tạo một chuỗi các đối tượng Task mới.
- `toList()` tạo danh sách không thể sửa từ stream trong Java 17.
- `List.copyOf(...)` nhấn mạnh hợp đồng kết quả không thể sửa; với đầu vào vốn đã không thể sửa, implementation có thể không cần tạo thêm một danh sách mới.

Vì `Task` hiện chỉ chứa `String` và `int`, thao tác copy trong ví dụ đã đủ để tách trạng thái mutable của `Task`. Nếu `Task` chứa một `List` mutable khác, `copy()` phải sao chép tiếp phần danh sách lồng nhau theo chính sách của ứng dụng. Chỉ gọi `new Task(title, progress)` không phải deep copy cho một object graph phức tạp.

### 10.2. Không phải lúc nào cũng cần deep copy

Nếu phần tử là kiểu immutable như `String`, `Integer`, `LocalDate` hoặc một record được thiết kế chỉ chứa các component immutable, chia sẻ tham chiếu thường an toàn.

~~~java
record Address(String city, String country) {
}

List<Address> addresses = List.of(
    new Address("Hanoi", "Vietnam"),
    new Address("Da Nang", "Vietnam")
);

List<Address> copy = List.copyOf(addresses);
~~~

Vì `Address` ở đây chỉ chứa `String`, hai collection có thể chia sẻ tham chiếu đến các record mà không làm lộ trạng thái mutable. Tuy nhiên, **record không tự động immutable sâu**: một record chứa `List<StringBuilder>` vẫn có thể tham chiếu đến collection hoặc phần tử mutable.

## 11. CopyOf, List.of và Stream.toList

Ba API này có quan hệ gần nhau nhưng mục đích đầu vào khác nhau:

| API | Đầu vào | Kết quả |
| --- | --- | --- |
| `List.of(a, b, ...)` | Các phần tử truyền trực tiếp | List không thể sửa, không cho null. |
| `List.copyOf(collection)` | Một collection hiện có | List không thể sửa, theo thứ tự lặp của nguồn, không cho null. |
| `stream.toList()` | Một stream | List không thể sửa chứa các phần tử stream phát ra, theo thứ tự encounter nếu stream có thứ tự. |
| `Collectors.toList()` | Một stream qua collector | Không bảo đảm loại, khả năng sửa hay tính thread-safe của list kết quả. |
| `Collectors.toUnmodifiableList()` | Một stream qua collector | List không thể sửa, không cho null. |

Ví dụ:

~~~java
import java.util.List;

List<String> source = List.of("A", "B", "C");

List<String> copied = List.copyOf(source);

List<String> fromStream = source.stream()
    .filter(s -> !s.isBlank())
    .toList();
~~~

`Stream.toList()` đã trả về một list không thể sửa từ Java 16. Không cần bọc thêm `Collections.unmodifiableList` chỉ để ngăn caller thêm/xóa phần tử. `List.copyOf` hữu ích khi đầu vào đã là một `Collection` và ta muốn áp dụng rõ hợp đồng không thể sửa.

Với `Set` và `Map`, có các collector không thể sửa tương ứng như `Collectors.toUnmodifiableSet()` và `Collectors.toUnmodifiableMap(...)`. Những collector này cũng không cho null và cần xử lý chính sách phần tử trùng/khóa trùng theo hợp đồng của collector.

## 12. Bảo đảm về thứ tự: List khác Set và Map

Không nên coi mọi phương thức `copyOf` đều bảo toàn thứ tự:

| Collection | Thứ tự được bảo đảm |
| --- | --- |
| `List.copyOf` | Giữ thứ tự lặp của nguồn. |
| `Set.copyOf` | Không bảo đảm thứ tự lặp. |
| `Map.copyOf` | Không bảo đảm thứ tự lặp của các entry. |

Nếu API công khai cần thứ tự ổn định:

- Dùng `List.copyOf` nếu dữ liệu có thứ tự và có thể trùng.
- Dùng `Collections.unmodifiableSet(new LinkedHashSet<>(source))` nếu cần tập không trùng nhưng giữ thứ tự chèn.
- Dùng `Collections.unmodifiableMap(new LinkedHashMap<>(source))` nếu cần map giữ thứ tự chèn.
- Dùng `Collections.unmodifiableMap(new TreeMap<>(source))` nếu cần thứ tự theo comparator của key.

Đừng dựa vào thứ tự hiển thị của `Set.copyOf` hoặc `Map.copyOf` trong log, test snapshot hay giao thức API.

## 13. CopyOf và null: thiết kế hợp đồng dữ liệu

Vì cả ba phương thức đều từ chối null, trước khi gọi cần xác định dữ liệu nào được phép thiếu.

Ví dụ, nếu một danh sách đầu vào có thể chứa null:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

List<String> source = new ArrayList<>();
source.add("A");
source.add(null);
source.add("B");

// Cách 1: loại null theo chính sách rõ ràng.
List<String> nonNull = List.copyOf(
    source.stream()
        .filter(Objects::nonNull)
        .toList()
);
~~~

Hoặc nếu null là dữ liệu không hợp lệ, hãy kiểm tra và báo lỗi tại biên hệ thống thay vì âm thầm bỏ:

~~~java
List<String> requiredValues = List.copyOf(source);
~~~

Lời gọi trên ném `NullPointerException`, giúp phát hiện đầu vào vi phạm hợp đồng. Chọn cách loại bỏ hay từ chối null tùy ý nghĩa nghiệp vụ; đừng lọc null một cách tự động nếu điều đó có thể làm mất thông tin.

Với map, có thể lọc entry có key/value khác null trước khi tạo bản sao:

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, String> clean = sourceMap.entrySet().stream()
    .filter(entry ->
        entry.getKey() != null && entry.getValue() != null
    )
    .collect(Collectors.toUnmodifiableMap(
        Map.Entry::getKey,
        Map.Entry::getValue
    ));
~~~

Đoạn này tạo map không thể sửa từ các entry hợp lệ. Nếu dữ liệu có key trùng sau một phép biến đổi, collector có thể ném `IllegalStateException`; cần định nghĩa rõ chính sách hợp nhất thay vì để mất dữ liệu tùy tiện.

## 14. Value-based collection và identity

Các collection không thể sửa được tạo bởi factory method như `List.of`, `Set.of`, `Map.of` và `copyOf` nên được xem như **value-based objects** theo tài liệu API. Chúng được thiết kế để so sánh theo nội dung, không phải để caller phụ thuộc vào identity của instance.

Tránh:

~~~java
if (List.copyOf(source) == List.copyOf(source)) {
    // Không dựa vào kết quả này.
}
~~~

Không nên:

- Dùng `==` để xác định hai collection `copyOf` có phải cùng một instance.
- Dùng `System.identityHashCode` làm định danh nghiệp vụ.
- Dùng collection value-based làm monitor cho `synchronized`.
- Giữ tham chiếu identity của collection làm khóa cache nếu mục đích thực sự là so sánh nội dung.

Hãy dùng `equals` khi cần so sánh nội dung:

~~~java
List<String> first = List.copyOf(List.of("A", "B"));
List<String> second = List.copyOf(List.of("A", "B"));

System.out.println(first.equals(second)); // true
~~~

Hai list bằng nhau theo nội dung và thứ tự, dù ứng dụng không cần biết chúng có cùng identity hay không.

## 15. Dùng copyOf khi trả collection từ lớp

Một mẫu phổ biến là giữ collection mutable bên trong lớp để phục vụ cập nhật nội bộ, nhưng trả ra một bản không thể sửa:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CourseCatalog {
    private final List<String> lessons = new ArrayList<>();

    public void addLesson(String title) {
        lessons.add(title);
    }

    public List<String> lessons() {
        return List.copyOf(lessons);
    }
}
~~~

Caller có thể đọc danh sách nhưng không thể thêm/xóa phần tử trên kết quả:

~~~java
CourseCatalog catalog = new CourseCatalog();
catalog.addLesson("Collections");

List<String> visible = catalog.lessons();
// visible.add("Streams"); // UnsupportedOperationException
~~~

Nếu catalog sau đó thêm lesson khác, danh sách `visible` đã trả về không tự cập nhật. Caller cần gọi `lessons()` lại để lấy snapshot cấu trúc mới.

### 15.1. Bảo vệ trạng thái khi có nhiều thread

`copyOf` tự nó không tạo một snapshot giao dịch an toàn nếu một thread khác đang sửa nguồn trong khi copy. Nếu collection nguồn mutable được truy cập đồng thời, cần đồng bộ việc đọc và ghi theo cùng một cơ chế.

Ví dụ với synchronized block:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SynchronizedCatalog {
    private final List<String> lessons = new ArrayList<>();

    public synchronized void addLesson(String title) {
        lessons.add(title);
    }

    public synchronized List<String> lessons() {
        return List.copyOf(lessons);
    }
}
~~~

Ở đây cả đọc và ghi đều dùng monitor của cùng object, nên quá trình sao chép không chạy đồng thời với `addLesson`. Nếu ứng dụng dùng một cơ chế khóa khác, mọi đường ghi và đọc liên quan phải tuân theo cùng chính sách. Chỉ bọc collection bằng `copyOf` không tự làm cho thao tác trên nguồn mutable trở nên thread-safe.

## 16. Những lỗi thường gặp

| Lỗi | Vì sao không đúng kỳ vọng | Cách xử lý |
| --- | --- | --- |
| Nghĩ `copyOf` làm mọi object bên trong immutable | Nó chỉ sao chép cấu trúc, tham chiếu phần tử vẫn dùng chung. | Thiết kế phần tử immutable hoặc tự copy sâu theo mô hình dữ liệu. |
| Dùng `Collections.unmodifiableList(source)` để tạo snapshot | Đây là view, thay đổi nguồn vẫn hiện ra. | Dùng `List.copyOf` với nguồn mutable ổn định. |
| Cho rằng `Set.copyOf` giữ thứ tự nguồn | Set không bảo đảm iteration order. | Dùng `LinkedHashSet` và wrapper nếu cần thứ tự chèn. |
| Cho rằng `Map.copyOf` giữ thứ tự của `LinkedHashMap` | Map kết quả không bảo đảm iteration order. | Dùng bản sao `LinkedHashMap` và wrapper. |
| Truyền null vào list/set/map | Các phương thức copyOf từ chối null. | Kiểm tra, loại bỏ hoặc biểu diễn trạng thái thiếu theo chính sách rõ ràng. |
| Cho rằng `Set.copyOf` báo lỗi khi nguồn có phần tử trùng | Set kết quả chỉ giữ một phần tử trong nhóm trùng; một instance bất kỳ có thể được giữ. | Tự xác định phần tử đại diện nếu identity có ý nghĩa. |
| So sánh kết quả bằng `==` | Collection value-based không cam kết identity. | Dùng `equals` để so sánh nội dung. |
| Dùng `copyOf` trong khi thread khác sửa nguồn | Không có bảo đảm snapshot nguyên tử từ thao tác copy đơn lẻ. | Đồng bộ nguồn hoặc dùng cấu trúc phù hợp với truy cập đồng thời. |
| Gọi copyOf rồi giả định dữ liệu nested không đổi | Collection lồng nhau hoặc value mutable vẫn có thể bị sửa. | Sao chép đệ quy hoặc dùng mô hình dữ liệu bất biến. |

## 17. Chương trình tổng hợp: snapshot cấu trúc nhưng chia sẻ phần tử

Tệp **`CopyOfShallowDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CopyOfShallowDemo {
    public static void main(String[] args) {
        StringBuilder mutableItem = new StringBuilder("draft");
        List<StringBuilder> sourceList = new ArrayList<>();
        sourceList.add(mutableItem);

        List<StringBuilder> listCopy = List.copyOf(sourceList);
        sourceList.add(new StringBuilder("later"));
        mutableItem.append(" updated");

        System.out.println("Source list size: " + sourceList.size());
        System.out.println("Copy list size: " + listCopy.size());
        System.out.println("Copied element: " + listCopy.get(0));

        Set<String> setCopy = Set.copyOf(
            List.of("USER", "ADMIN", "USER")
        );
        System.out.println("Set size: " + setCopy.size());

        Map<String, Integer> mapCopy = Map.copyOf(
            Map.of("An", 90, "Binh", 85)
        );
        System.out.println("Map value: " + mapCopy.get("An"));
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 CopyOfShallowDemo.java
java CopyOfShallowDemo
~~~

Kết quả phần list:

~~~text
Source list size: 2
Copy list size: 1
Copied element: draft updated
~~~

Phần set có kích thước 2 vì hai chuỗi `USER` bằng nhau nên chỉ giữ một; map vẫn đọc được ánh xạ `An -> 90`. Thứ tự in các phần tử của set hoặc map không phải một bảo đảm của `copyOf`.

## 18. Câu hỏi thường gặp

**List.copyOf có luôn tạo object mới không?**  
Không nên dựa vào điều đó. Implementation có thể tái sử dụng collection đầu vào vốn đã không thể sửa. Hãy dựa vào hợp đồng nội dung và tính không thể sửa, không dựa vào identity.

**copyOf có clone từng phần tử không?**  
Không. Nó sao chép cấu trúc collection và các tham chiếu đến phần tử. Muốn deep copy, ứng dụng phải tự xác định cách tạo bản sao cho từng loại đối tượng và các đối tượng lồng nhau.

**List.copyOf có giữ phần tử trùng không?**  
Có. List giữ thứ tự và số lần xuất hiện của phần tử theo nguồn.

**Set.copyOf có báo lỗi khi collection nguồn chứa phần tử trùng không?**  
Không. Các phần tử bằng nhau được gộp thành một; một phần tử bất kỳ trong nhóm trùng được giữ lại.

**Map.copyOf có giữ thứ tự của LinkedHashMap không?**  
Không có bảo đảm về thứ tự lặp. Nếu thứ tự là một phần của hợp đồng, hãy tạo bản sao LinkedHashMap rồi bọc bằng Collections.unmodifiableMap.

**Tại sao Map.copyOf ném NullPointerException với HashMap có value null?**  
Vì map không thể sửa do copyOf tạo ra không cho phép key hoặc value null, dù HashMap nguồn cho phép null.

**Collections.unmodifiableList có giống List.copyOf không?**  
Không. Wrapper là view trên nguồn; thay đổi cấu trúc nguồn vẫn phản ánh qua view. copyOf tạo kết quả không thể sửa, tách khỏi thay đổi cấu trúc tiếp theo của nguồn mutable thông thường.

**Record có bảo đảm phần tử bất biến sâu khi đưa vào List.copyOf không?**  
Không. Record chỉ có component field final; nếu component trỏ đến list mutable hoặc object mutable thì trạng thái đó vẫn có thể thay đổi.

**Có nên gọi List.copyOf(stream.toList()) không?**  
Thường không cần nếu mục tiêu chỉ là có list không thể sửa, vì Stream.toList() trong Java 17 đã trả list không thể sửa. Hãy dùng copyOf khi đầu vào là collection và cần hợp đồng tương ứng.

## 19. Tài liệu tham khảo chính thức

- [Java SE 17 API — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): thứ tự, null, tính không thể sửa và việc có thể tái sử dụng nguồn đã không thể sửa.
- [Java SE 17 API — Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): loại phần tử trùng, null và thứ tự lặp.
- [Java SE 17 API — Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): ánh xạ, null, tính không thể sửa và thứ tự.
- [Java SE 17 API — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): hợp đồng view chỉ đọc trên list nguồn.
- [Java SE 17 API — Collections.unmodifiableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)) và [unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): các wrapper không thể sửa.
- [Java SE 17 API — Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): tạo list không thể sửa từ các phần tử của stream.
- [JEP 269 — Convenience Factory Methods for Collections](https://openjdk.org/jeps/269): bối cảnh các factory method cho collection không thể sửa được đưa vào Java.

**Nguyên tắc áp dụng:** Dùng List.copyOf, Set.copyOf và Map.copyOf để tạo collection không thể sửa, với chính sách null và thứ tự phù hợp. Hãy nhớ chúng chỉ sao chép nông: cấu trúc collection được tách ra, nhưng các đối tượng phần tử/key/value vẫn được chia sẻ. Khi cần bất biến sâu, thứ tự cụ thể hoặc snapshot đồng bộ, phải thiết kế thêm chính sách tương ứng.
