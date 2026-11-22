# SequencedCollection, SequencedSet và SequencedMap trong Java 21

Java 21 bổ sung ba interface SequencedCollection, SequencedSet và SequencedMap để mô hình hóa các collection có encounter order được xác định rõ ràng. Chúng cung cấp một bộ thao tác thống nhất để làm việc với phần tử hoặc ánh xạ ở đầu và cuối, đồng thời cho phép lấy view theo thứ tự ngược.

Điểm quan trọng là encounter order không nhất thiết phải là thứ tự thêm vào. LinkedHashSet và LinkedHashMap có thể giữ thứ tự chèn, LinkedHashMap còn có chế độ thứ tự truy cập, trong khi TreeSet và TreeMap giữ thứ tự theo comparator. Các kiểu này đều có thể biểu diễn thứ tự bằng các interface sequenced tương ứng.

## 1. Vì sao cần Sequenced Collections?

Trước Java 21, các kiểu collection có thứ tự cung cấp những API khác nhau. List có thể truy cập phần tử theo chỉ số, Deque có các thao tác ở hai đầu, còn LinkedHashSet và LinkedHashMap duy trì encounter order nhưng không có chung một hợp đồng API cho đầu và cuối.

Các interface mới chuẩn hóa khái niệm thứ tự và thao tác ở hai đầu:

- **SequencedCollection** mô tả một collection có thứ tự gặp phần tử xác định.
- **SequencedSet** kết hợp đặc tính Set với thứ tự gặp phần tử xác định.
- **SequencedMap** mô tả một map có thứ tự gặp các ánh xạ xác định.

Nhờ đó, mã có thể nhận một kiểu interface chung và thao tác với đầu, cuối hoặc view đảo thứ tự mà không phụ thuộc vào lớp triển khai cụ thể.

## 2. Quan hệ giữa các interface

Ba interface tạo thành phần mở rộng của Collection và Map:

~~~text
Collection
    |
    +-- SequencedCollection
            |
            +-- List
            |
            +-- Deque
            |
            +-- SequencedSet
                    |
                    +-- SortedSet

Map
    |
    +-- SequencedMap
            |
            +-- SortedMap
~~~

Sơ đồ chỉ thể hiện các quan hệ chính liên quan đến thứ tự. Một số interface con khác như NavigableSet và NavigableMap kế thừa SortedSet và SortedMap, nên cũng nhận hợp đồng sequenced.

Các lớp triển khai quen thuộc có thể dùng qua các interface này:

| Kiểu cụ thể | Interface sequenced | Encounter order |
|---|---|---|
| ArrayList | SequencedCollection qua List | Thứ tự phần tử trong list |
| LinkedList | SequencedCollection qua List và Deque | Thứ tự phần tử trong list/deque |
| ArrayDeque | SequencedCollection qua Deque | Thứ tự hai đầu của deque |
| LinkedHashSet | SequencedSet | Thứ tự chèn |
| TreeSet | SequencedSet qua NavigableSet | Thứ tự theo comparator |
| LinkedHashMap | SequencedMap | Thứ tự chèn hoặc thứ tự truy cập tùy cấu hình |
| TreeMap | SequencedMap qua NavigableMap | Thứ tự theo comparator của key |

Không phải mọi Collection, Set hoặc Map đều là sequenced. HashSet và HashMap không cam kết encounter order, vì vậy không thể dựa vào chúng để có thứ tự đầu/cuối ổn định.

## 3. SequencedCollection: thao tác ở đầu và cuối

SequencedCollection mở rộng Collection và bổ sung các phương thức sau:

| Phương thức | Ý nghĩa |
|---|---|
| addFirst(E element) | Thêm phần tử vào đầu encounter order |
| addLast(E element) | Thêm phần tử vào cuối encounter order |
| getFirst() | Lấy phần tử đầu mà không xóa |
| getLast() | Lấy phần tử cuối mà không xóa |
| removeFirst() | Lấy và xóa phần tử đầu |
| removeLast() | Lấy và xóa phần tử cuối |
| reversed() | Trả về view có encounter order đảo ngược |

Ví dụ với ArrayList:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.SequencedCollection;

public class CollectionExample {
    public static void main(String[] args) {
        SequencedCollection<String> tasks =
                new ArrayList<>(List.of("build", "test", "deploy"));

        tasks.addFirst("compile");
        tasks.addLast("monitor");

        System.out.println(tasks.getFirst()); // compile
        System.out.println(tasks.getLast());  // monitor

        for (String task : tasks.reversed()) {
            System.out.println(task);
        }

        String removed = tasks.removeFirst();
        System.out.println("Removed: " + removed);
    }
}
~~~

Mã chỉ phụ thuộc vào SequencedCollection. Cùng cách viết này có thể dùng với các implementation khác hỗ trợ thao tác tương ứng.

List cũng là SequencedCollection, vì vậy có thể dùng các phương thức đầu/cuối thay cho việc phải tính chỉ số cuối. Deque đã có các thao tác hai đầu từ trước; nay nó tham gia cùng hợp đồng SequencedCollection.

## 4. reversed() trả về view đảo thứ tự

reversed() không được hiểu là tạo một collection mới bằng cách sao chép rồi đảo các phần tử. Phương thức trả về một view có encounter order ngược với collection gốc.

~~~java
List<String> original =
        new ArrayList<>(List.of("A", "B", "C"));

SequencedCollection<String> reverse = original.reversed();

System.out.println(reverse.getFirst()); // C
System.out.println(reverse.getLast());  // A

reverse.addFirst("D");

System.out.println(original); // [A, B, C, D]
System.out.println(reverse);  // [D, C, B, A]
~~~

View và collection gốc cùng phản ánh dữ liệu nền. Thao tác qua view được diễn giải theo thứ tự đảo: thêm vào đầu của view tương ứng với thêm vào cuối của collection gốc. Khả năng sửa đổi vẫn phụ thuộc collection nền; nếu collection không hỗ trợ thao tác thay đổi, view cũng không thể làm cho thao tác đó trở nên hợp lệ.

Có thể dùng reversed() để duyệt từ cuối về đầu mà không cần tạo bản sao hoặc thay đổi thứ tự lưu trữ của collection gốc.

## 5. SequencedSet: Set có thứ tự gặp phần tử

SequencedSet mở rộng cả SequencedCollection và Set. Vì vậy, nó có encounter order xác định nhưng vẫn giữ quy tắc mỗi phần tử chỉ xuất hiện một lần.

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;

public class SequencedSetExample {
    public static void main(String[] args) {
        SequencedSet<String> roles =
                new LinkedHashSet<>(List.of("reader", "editor", "admin"));

        roles.addFirst("guest");
        roles.addLast("auditor");

        System.out.println(roles.getFirst()); // guest
        System.out.println(roles.getLast());  // auditor

        System.out.println(roles.reversed());
    }
}
~~~

Trong ví dụ, LinkedHashSet duy trì thứ tự chèn và cung cấp các thao tác đầu/cuối. Set vẫn không chứa hai phần tử bằng nhau theo quy tắc equals/hashCode của implementation.

SequencedSet hữu ích khi ứng dụng cần cả hai đặc tính: kiểm tra membership theo Set và xử lý phần tử theo vị trí đầu/cuối. View reversed() của SequencedSet vẫn là một SequencedSet.

### SortedSet cũng là sequenced

Từ Java 21, SortedSet mở rộng SequencedSet. Điều này có nghĩa các sorted set như TreeSet có encounter order rõ ràng theo thứ tự comparator, và có thể lấy phần tử đầu/cuối hoặc view đảo thứ tự.

~~~java
import java.util.SequencedSet;
import java.util.TreeSet;

SequencedSet<Integer> numbers =
        new TreeSet<>(java.util.List.of(8, 2, 5));

System.out.println(numbers.getFirst()); // 2
System.out.println(numbers.getLast());  // 8
System.out.println(numbers.reversed()); // [8, 5, 2]
~~~

Thứ tự của TreeSet được quyết định bởi comparator. Vì vậy, các thao tác yêu cầu chèn tùy ý vào đầu hoặc cuối như addFirst và addLast không phù hợp với hợp đồng sắp xếp và có thể ném UnsupportedOperationException. Dùng add để thêm giá trị rồi để comparator xác định vị trí của nó.

## 6. SequencedMap: thao tác với ánh xạ đầu và cuối

SequencedMap mở rộng Map và bổ sung các thao tác theo encounter order:

| Phương thức | Ý nghĩa |
|---|---|
| putFirst(K key, V value) | Đặt ánh xạ ở đầu encounter order |
| putLast(K key, V value) | Đặt ánh xạ ở cuối encounter order |
| firstEntry() | Lấy ánh xạ đầu mà không xóa |
| lastEntry() | Lấy ánh xạ cuối mà không xóa |
| pollFirstEntry() | Lấy và xóa ánh xạ đầu |
| pollLastEntry() | Lấy và xóa ánh xạ cuối |
| sequencedKeySet() | View các key theo encounter order |
| sequencedValues() | View các value theo encounter order |
| sequencedEntrySet() | View các entry theo encounter order |
| reversed() | View map với thứ tự ánh xạ đảo ngược |

Ví dụ với LinkedHashMap:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.SequencedMap;

public class SequencedMapExample {
    public static void main(String[] args) {
        SequencedMap<String, Integer> scores = new LinkedHashMap<>();

        scores.putLast("An", 9);
        scores.putLast("Binh", 8);
        scores.putFirst("Chi", 10);

        Map.Entry<String, Integer> first = scores.firstEntry();
        Map.Entry<String, Integer> last = scores.lastEntry();

        System.out.println(first); // Chi=10
        System.out.println(last);  // Binh=8

        scores.sequencedEntrySet().forEach(System.out::println);

        Map.Entry<String, Integer> removed = scores.pollLastEntry();
        System.out.println("Removed: " + removed);

        scores.reversed().forEach((name, score) ->
                System.out.println(name + ": " + score));
    }
}
~~~

firstEntry() và lastEntry() không xóa ánh xạ. pollFirstEntry() và pollLastEntry() vừa trả về ánh xạ tương ứng vừa xóa nó khỏi map. Các entry trả về bởi những phương thức lấy đầu/cuối này là snapshot của ánh xạ tại thời điểm gọi và không hỗ trợ setValue.

Các view sequencedKeySet(), sequencedValues() và sequencedEntrySet() giữ thứ tự tương ứng với map. Đây là view gắn với map nền, vì vậy thay đổi được hỗ trợ qua view cũng ảnh hưởng đến map.

## 7. SortedMap và thứ tự theo key

SortedMap mở rộng SequencedMap từ Java 21. Với TreeMap, encounter order là thứ tự key theo comparator, không phải thứ tự gọi put.

~~~java
import java.util.SequencedMap;
import java.util.TreeMap;

SequencedMap<String, Integer> inventory = new TreeMap<>();
inventory.put("pear", 4);
inventory.put("apple", 7);
inventory.put("orange", 3);

System.out.println(inventory.firstEntry()); // apple=7
System.out.println(inventory.lastEntry());  // pear=4
System.out.println(inventory.reversed());   // thứ tự key đảo ngược
~~~

TreeMap có thể cung cấp firstEntry(), lastEntry(), các view và reversed() theo thứ tự comparator. Tuy nhiên, putFirst() và putLast() không thể ép một key vào vị trí tùy ý mà vẫn giữ invariant sắp xếp, nên các thao tác này không được hỗ trợ và có thể ném UnsupportedOperationException. Dùng put() để thêm hoặc cập nhật mapping.

Điều này cho thấy sequenced không đồng nghĩa với insertion-ordered. Nó có nghĩa là encounter order được xác định và có thể quan sát hoặc đảo ngược thông qua API chung.

## 8. Xử lý collection rỗng và thao tác không được hỗ trợ

Các phương thức lấy hoặc xóa phần tử ở hai đầu của SequencedCollection có hành vi khi collection rỗng:

- getFirst() và getLast() ném NoSuchElementException nếu không có phần tử.
- removeFirst() và removeLast() cũng ném NoSuchElementException nếu collection rỗng.
- firstEntry(), lastEntry(), pollFirstEntry() và pollLastEntry() trả về null nếu map không có ánh xạ tương ứng.

Không nên dùng null để suy ra rằng map chắc chắn rỗng nếu implementation cho phép value null; hãy kiểm tra kết quả entry hoặc trạng thái map theo logic cần thiết.

Các thao tác thay đổi như addFirst(), addLast(), removeFirst(), removeLast(), putFirst() và putLast() có thể ném UnsupportedOperationException khi implementation hoặc view không hỗ trợ thay đổi. SortedSet và SortedMap là ví dụ điển hình cho việc các thao tác ép vị trí đầu/cuối không tương thích với thứ tự comparator. Collection bất biến hoặc view chỉ đọc cũng không cho phép sửa đổi.

Vì vậy, kiểu tham chiếu SequencedCollection hoặc SequencedMap không tự bảo đảm mọi thao tác thay đổi đều được hỗ trợ. Hãy kiểm tra hợp đồng của implementation và khả năng sửa đổi của collection cụ thể.

## 9. Khi nào nên dùng từng interface?

| Nhu cầu | Kiểu nên dùng |
|---|---|
| Dãy phần tử có thứ tự, có thể có phần tử trùng | SequencedCollection |
| Tập hợp không trùng phần tử nhưng cần thứ tự đầu/cuối | SequencedSet |
| Ánh xạ key-value có thứ tự gặp xác định | SequencedMap |
| Cần giữ thứ tự chèn của phần tử | LinkedHashSet qua SequencedSet |
| Cần giữ thứ tự chèn của ánh xạ | LinkedHashMap qua SequencedMap |
| Cần thứ tự theo comparator và thao tác đầu/cuối | TreeSet hoặc TreeMap qua interface sequenced |
| Cần duyệt ngược mà không sao chép dữ liệu | reversed() |

Khi thiết kế API, nên khai báo kiểu tham số ở mức interface sequenced nếu logic chỉ cần hợp đồng thứ tự và thao tác hai đầu. Chọn implementation cụ thể theo nhu cầu về thứ tự chèn, sắp xếp, hiệu năng và khả năng sửa đổi.

## 10. Tóm tắt các điểm cần nhớ

- SequencedCollection, SequencedSet và SequencedMap là API chuẩn từ Java 21.
- SequencedCollection chuẩn hóa thao tác ở đầu/cuối và view đảo thứ tự.
- SequencedSet giữ quy tắc không trùng phần tử của Set.
- SequencedMap cung cấp thao tác với ánh xạ đầu/cuối cùng các view key, value và entry có thứ tự.
- Encounter order có thể là thứ tự chèn, thứ tự truy cập hoặc thứ tự comparator; không phải mọi sequenced collection đều insertion-ordered.
- reversed() trả về view đảo thứ tự, không phải bản sao độc lập.
- Collection rỗng, collection bất biến và sorted collection có những giới hạn riêng đối với các thao tác lấy, xóa hoặc chèn ở hai đầu.

Các interface sequenced giúp mã Java biểu đạt rõ ràng thứ tự mà ứng dụng dựa vào, đồng thời cung cấp cùng một cách thao tác ở hai đầu cho nhiều cấu trúc dữ liệu khác nhau.
