# Giữ nhất quán equals, hashCode, view và các phương thức mặc định

## 1. Một cấu trúc dữ liệu có nhiều đường đi vào cùng một trạng thái

Bạn viết một danh sách chỉ nhận số không âm. `add(-1)` đã bị chặn. Nhưng người dùng vẫn có thể gọi `listIterator().set(-1)`, `subList(...).set(...)` hoặc `replaceAll(...)`. Nếu một đường cập nhật bỏ qua kiểm tra, điều kiện “mọi phần tử không âm” không còn đúng.

Với map, vấn đề còn dễ bị che khuất hơn: bạn kiểm tra trong `put`, nhưng một đối tượng `Map.Entry` được trả ra có thể cho phép gọi `setValue` trực tiếp. Một số phương thức mặc định dùng chính đường này.

Bên cạnh đó, cấu trúc còn phải làm việc với những cài đặt khác của cùng giao diện. Một `List` tự viết có cùng các phần tử theo cùng thứ tự phải có quan hệ bằng nhau và mã băm phù hợp với `ArrayList` hoặc `LinkedList`. Không thể chỉ kiểm tra hai đối tượng cùng lớp rồi kết luận hợp đồng đã đúng.

Bài này tập trung vào bốn điều liên hệ với nhau:

1. **`equals`:** hai trạng thái nào được xem là bằng nhau?
2. **`hashCode`:** trạng thái bằng nhau có cho mã băm tương thích không?
3. **Khung nhìn (view):** những đối tượng nào cùng đọc/sửa một dữ liệu nền?
4. **Phương thức mặc định và kế thừa:** những thuật toán có sẵn sẽ cập nhật dữ liệu qua thao tác nào?

Một **bất biến** là điều kiện bạn muốn giữ sau mọi thao tác được hỗ trợ, chẳng hạn không có phần tử trùng, giá trị không âm hoặc không cho sửa từ một giao diện chỉ đọc. Giữ nhất quán nghĩa là mọi đường quan sát và cập nhật đều tôn trọng cùng hợp đồng, kể cả đường bạn không tự viết mã trong lớp con.

Mô hình tư duy cần dùng:

```text
Lời gọi trực tiếp ───────────────┐
Bộ duyệt / ListIterator ────────┤
Khung nhìn ────────────────────┼─→ thao tác cập nhật thực tế
Phương thức mặc định/kế thừa ──┘       ↓
                              dữ liệu và bất biến chung
                                      ↓
                          equals / hashCode / cách quan sát
```

Mục tiêu là lần theo các đường này, không phải ghi đè mọi phương thức một cách máy móc. Ba chương trình sẽ lần lượt kiểm chứng hợp đồng bằng nhau, danh sách có khung nhìn và map có các cửa cập nhật được kiểm tra.

## 2. equals và hashCode phải khớp ngữ nghĩa của giao diện

### 2.1. Hợp đồng nền của Object

Theo [Object.equals và Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html), phép bằng nhau cần có tính phản xạ, đối xứng, bắc cầu và nhất quán khi dữ liệu liên quan không đổi; một đối tượng khác `null` phải trả `false` khi so với `null`.

Điều kéo theo cho mã băm là:

```text
a.equals(b) == true  ⇒  a.hashCode() == b.hashCode()
```

Chiều ngược lại không bắt buộc đúng. Hai đối tượng khác nhau có thể có cùng mã băm. Nếu dùng `hashCode` bằng nhau để kết luận `equals` bằng nhau, bạn biến va chạm băm hợp lệ thành một lỗi so sánh.

Không nhất thiết phải viết lại hai phương thức trong mọi lớp. Nhưng khi tự thay quy tắc `equals`, bạn phải giữ quy tắc `hashCode` tương ứng. Nếu lớp nền đã cung cấp đúng hợp đồng collection mà bạn cần, giữ cài đặt ấy thường ít rủi ro hơn việc tự viết lại.

### 2.2. Cùng chứa phần tử chưa có nghĩa dùng cùng phép bằng nhau

| Loại API | Điều kiện bằng nhau theo nội dung | Mã băm cần tương thích |
| --- | --- | --- |
| `List` | Đối phương cũng là `List`, cùng độ dài, từng cặp ở cùng vị trí bằng nhau | Tích lũy theo thứ tự, bắt đầu từ 1, mỗi bước nhân 31 rồi cộng mã băm phần tử. |
| `Set` | Đối phương cũng là `Set`, cùng các phần tử, không xét thứ tự | Tổng mã băm của các phần tử. |
| `Map` | Đối phương cũng là `Map`, cùng các ánh xạ khóa–giá trị | Tổng mã băm của các mục trong `entrySet`. |
| `Map.Entry` | Đối phương cũng là `Entry`, khóa bằng nhau và giá trị bằng nhau | Mã băm khóa XOR mã băm giá trị. |
| `Collection` không phải `List`/`Set` | Không có một phép so sánh nội dung chung được tự động áp đặt | Giữ hợp đồng `Object` hoặc một hợp đồng riêng được thiết kế đúng. |

Trong các công thức phần tử, `null` đóng góp 0. Các phép tính mã băm dùng `int` có thể tràn theo phép tính số nguyên của Java; không thay công thức chuẩn chỉ vì tổng vượt một giá trị dương lớn.

Nguồn định nghĩa cụ thể là [List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) và [Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

Một danh sách không bằng một tập hợp chỉ vì cả hai in ra `[A, B]`. Thứ tự và số lần xuất hiện thuộc ngữ nghĩa của danh sách, trong khi tập hợp không có phần tử trùng và không dùng thứ tự để xác định bằng nhau.

Nếu lớp tự viết thực hiện `List`, đừng giới hạn `equals` bằng kiểm tra “phải cùng lớp cụ thể với tôi”. Điều này có thể khiến lớp bạn từ chối bằng một danh sách chuẩn trong khi danh sách chuẩn lại nhận bằng lớp bạn. Tính đối xứng bị phá vỡ dù dữ liệu giống nhau.

Với một kiểu giá trị thông thường không thực hiện các giao diện collection này, việc chọn phạm vi lớp được phép bằng nhau là một quyết định thiết kế riêng. Ở đây, hợp đồng giao diện công khai đã đặt yêu cầu tương tác giữa các cài đặt.

### 2.3. Chương trình kiểm chứng giữa các cài đặt

`Words` là một danh sách chỉ đọc nhỏ, dùng mảng sao chép và kế thừa phép bằng nhau/mã băm của `AbstractList`. Chương trình còn kiểm tra tập hợp, map và mục ánh xạ thuộc những lớp khác nhau.

Lưu thành `EqualityContractsDemo.java`:

```java
import java.util.AbstractList;
import java.util.AbstractMap;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;

public class EqualityContractsDemo {
    public static void main(String[] args) {
        List<String> custom = new Words("A", "B");
        List<String> standard = Arrays.asList("A", "B");
        System.out.println("list equality both ways = "
                + (custom.equals(standard) && standard.equals(custom)));
        System.out.println("list hash agrees = "
                + (custom.hashCode() == standard.hashCode()));
        System.out.println("reordered list equals = " + custom.equals(List.of("B", "A")));

        Set<String> firstSet = new LinkedHashSet<>(List.of("A", "B"));
        Set<String> secondSet = new HashSet<>(List.of("B", "A"));
        System.out.println("set equality = " + firstSet.equals(secondSet));
        System.out.println("set hash agrees = "
                + (firstSet.hashCode() == secondSet.hashCode()));
        System.out.println("list equals set = " + custom.equals(firstSet));

        Map<String, Integer> firstMap = new HashMap<>(Map.of("A", 1, "B", 2));
        Map<String, Integer> secondMap = new TreeMap<>(Map.of("B", 2, "A", 1));
        System.out.println("map equality = " + firstMap.equals(secondMap));
        System.out.println("map hash agrees = "
                + (firstMap.hashCode() == secondMap.hashCode()));

        Map.Entry<String, Integer> entry = Map.entry("A", 3);
        Map.Entry<String, Integer> copied =
                new AbstractMap.SimpleImmutableEntry<>("A", 3);
        System.out.println("entry equality both ways = "
                + (entry.equals(copied) && copied.equals(entry)));
        int requiredHash = Objects.hashCode(entry.getKey())
                ^ Objects.hashCode(entry.getValue());
        System.out.println("entry XOR hash agrees = " + (entry.hashCode() == requiredHash));
        System.out.println("Objects.hash pair agrees = "
                + (entry.hashCode() == Objects.hash("A", 3)));

        CollisionKey one = new CollisionKey(1);
        CollisionKey two = new CollisionKey(2);
        System.out.println("collision has same hash = " + (one.hashCode() == two.hashCode()));
        System.out.println("collision keys equal = " + one.equals(two));
        System.out.println("collision set size = " + Set.of(one, two).size());
    }

    private static final class Words extends AbstractList<String> {
        private final String[] data;

        private Words(String... words) {
            data = words.clone();
        }

        @Override
        public String get(int index) {
            Objects.checkIndex(index, data.length);
            return data[index];
        }

        @Override
        public int size() {
            return data.length;
        }
    }

    private record CollisionKey(int value) {
        @Override
        public int hashCode() {
            return 0;
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all EqualityContractsDemo.java
java EqualityContractsDemo
```

Kết quả:

```text
list equality both ways = true
list hash agrees = true
reordered list equals = false
set equality = true
set hash agrees = true
list equals set = false
map equality = true
map hash agrees = true
entry equality both ways = true
entry XOR hash agrees = true
Objects.hash pair agrees = false
collision has same hash = true
collision keys equal = false
collision set size = 2
```

### 2.4. Điều mỗi nhóm kết quả chứng minh

Với danh sách, cả hai chiều so sánh đều đúng và mã băm bằng nhau. Khi đảo thứ tự, kết quả bằng nhau đổi thành `false`. `Words` không tự viết một phiên bản `equals` khác làm mất khả năng tương tác.

Với tập hợp và map, thứ tự xây dựng khác nhau không làm thay đổi quan hệ bằng nhau. Không dựa vào thứ tự duyệt của `HashMap` hoặc `HashSet` để in kết quả; chương trình chỉ in các giá trị logic đã xác định.

Với `Map.Entry`, công thức XOR được kiểm chứng trực tiếp. `Objects.hash("A",3)` không phải công thức thay thế cho `Entry.hashCode()`: nó tính mã băm kết hợp theo một cách khác. Ví dụ cụ thể cho kết quả khác nhau; không được suy ra hai công thức tương đương chỉ vì cả hai đều nhận khóa và giá trị.

`CollisionKey` cố ý trả mã băm 0 cho mọi giá trị. Hai khóa có giá trị khác nhau vẫn không bằng nhau và cùng được giữ trong tập hợp. Đây là ví dụ về mã băm có nhiều va chạm nhưng chưa vi phạm điều kiện “bằng nhau thì cùng mã băm”. Nó có thể gây hiệu năng xấu ở cấu trúc băm, nhưng không phải lý do hợp lệ để coi hai đối tượng là một.

### 2.5. Trạng thái thay đổi kéo theo phép so sánh thay đổi

Một collection có thể có mã băm thay đổi khi phần tử, thứ tự hoặc ánh xạ của nó thay đổi. Vì thế, đừng lưu một mã băm tính ở lần đầu rồi dùng mãi nếu dữ liệu liên quan còn có thể sửa. Bộ đếm thay đổi cấu trúc cũng không đủ: thay giá trị bằng `set` có thể không đổi kích thước nhưng làm mã băm danh sách thay đổi.

Tương tự, khóa trong map hoặc phần tử trong set cần được dùng cẩn thận nếu các trường tham gia `equals` còn có thể sửa. Hợp đồng [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) và [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html) không xác định hành vi khi sự thay đổi ấy ảnh hưởng phép bằng nhau trong lúc đối tượng đang được lưu. Không nên dạy rằng “sau khi sửa chắc chắn contains sẽ trả false”; đó là một cách dự đoán quá mức cho trường hợp đã ra ngoài hợp đồng.

Nếu cần thay giá trị nhận diện, một hướng rõ ràng là lấy/xóa đối tượng theo trạng thái cũ trước, tạo giá trị mới phù hợp rồi đưa vào lại theo chính sách của bài toán. Dùng khóa giá trị bất biến giúp giảm vấn đề này.

Với cấu trúc sắp xếp, còn phải xét quan hệ `compare(a,b) == 0`. Nếu quan hệ này không nhất quán với `equals`, cấu trúc có thể coi hai phần tử là một theo phép so sánh nhưng đối tượng lại nói chúng khác nhau. [Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html) giải thích ảnh hưởng tới hợp đồng `Set`/`Map`. Đừng tự thêm việc bỏ qua hoa thường hoặc chuẩn hóa khóa ở một vài phương thức rồi giả định mọi phép tìm, xóa, so sánh và mã băm đã tự nhất quán.


## 3. Khung nhìn chia sẻ dữ liệu, không chỉ chia sẻ kiểu

### 3.1. Ba quan hệ cần phân biệt

| Đối tượng được trả về | Có theo dõi thay đổi cấu trúc/nội dung ở nền không? | Có cho sửa từ đối tượng này không? |
| --- | --- | --- |
| Khung nhìn có thể sửa như `subList` | Có liên hệ với danh sách nền, trong phạm vi hợp đồng sử dụng | Có, nếu nền và thao tác tương ứng hỗ trợ. |
| Khung nhìn không cho sửa như `Collections.unmodifiableList` | Các truy vấn đọc qua nền nên thấy thay đổi hợp lệ ở nền | Không cho sửa qua khung nhìn. |
| Bản sao cấu trúc như `List.copyOf` | Không phản ánh các thay đổi sau đó của cấu trúc nguồn | Không cho sửa bản danh sách trả về. |

“Không cho sửa” mô tả khả năng của một đường truy cập. Nó không có nghĩa dữ liệu nền không thể thay đổi qua một tham chiếu khác. “Bản sao” cũng không mặc nhiên là sao chép sâu mọi đối tượng phần tử.

[Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) và [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) là hai API cần đọc tách biệt. `List.copyOf` không nhận phần tử `null`; nó không phải lựa chọn thay thế vô điều kiện cho một bản sao có chính sách cho phép `null`.

Nếu bạn tự cài một phương thức được công bố là trả khung nhìn nhưng lại trả một bản sao không liên hệ với nguồn, phía gọi sẽ có kỳ vọng sai về việc cập nhật. Ngược lại, trả thẳng dữ liệu nền khi đã công bố bản sao có thể làm thay đổi ngoài ý muốn đi ngược vào cấu trúc gốc.

### 3.2. Một chính sách phải tồn tại trên mọi đường sửa của List

Với danh sách không âm, hãy lần theo các đường:

```text
addAll(...)               → thêm từng phần tử → add(index, value)
ListIterator.add(value)   → add(index, value)
ListIterator.set(value)   → set(index, value)
subList(...).set(...)     → set ở chỉ số tương ứng trên nền
List.replaceAll(...)      → ListIterator.set(...) trong cài đặt mặc định
List.sort(...)            → ghi kết quả sắp xếp qua bộ duyệt trong cài đặt mặc định
removeIf(...)             → Iterator.remove() trong cài đặt mặc định
```

Đây là bản đồ cho kiểu danh sách dùng lớp khung và không ghi đè các thuật toán ấy. Lớp cụ thể khác có thể ghi đè, nên khi tối ưu hoặc viết lớp bọc, phải xem lại cài đặt thực tế.

Cần phân biệt thuật ngữ Java:

- `Collection.removeIf`, `List.replaceAll`, `List.sort` là các phương thức `default` được khai báo ở giao diện.
- Một phương thức như `addAll` kế thừa từ lớp trừu tượng là phương thức có thân của lớp nền; nó không trở thành phương thức `default` của giao diện chỉ vì bạn không tự viết nó.

Cả hai loại đều có thể gọi trở lại các thao tác của lớp bạn. Vì thế, việc kiểm tra bất biến phải bao phủ cả phương thức mặc định lẫn phương thức kế thừa.

### 3.3. Chương trình: danh sách không âm, khung nhìn và thuật toán có sẵn

`NonNegativeList` chấp nhận các `Integer` khác `null` và lớn hơn hoặc bằng 0. Nó giữ nơi lưu riêng, kiểm tra ở `add(int,Integer)` và `set(int,Integer)`, hỗ trợ xóa, và ghi nhận thay đổi cấu trúc cho cơ chế kế thừa.

Lưu thành `ViewsAndDefaultsDemo.java`:

```java
import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.ListIterator;
import java.util.Objects;
import java.util.RandomAccess;

public class ViewsAndDefaultsDemo {
    public static void main(String[] args) {
        NonNegativeList list = new NonNegativeList();
        list.addAll(List.of(1, 2, 3, 4));
        List<Integer> readOnlyView = Collections.unmodifiableList(list);
        List<Integer> snapshot = List.copyOf(list);
        List<Integer> middle = list.subList(1, 3);

        middle.set(0, 20);
        list.replaceAll(value -> value * 2);
        System.out.println("after view set and replaceAll = " + list);
        middle.clear();
        System.out.println("after subList clear = " + list);
        System.out.println("read-only view = " + readOnlyView);
        System.out.println("snapshot = " + snapshot);

        list.removeIf(value -> value > 5);
        list.addAll(List.of(5, 3));
        list.sort(Comparator.reverseOrder());
        System.out.println("after removeIf and sort = " + list);
        expect("negative replaceAll", IllegalArgumentException.class,
                () -> list.replaceAll(value -> -value));
        ListIterator<Integer> cursor = list.listIterator();
        cursor.next();
        expect("negative iterator set", IllegalArgumentException.class,
                () -> cursor.set(-1));
        expect("read-only add", UnsupportedOperationException.class,
                () -> readOnlyView.add(6));
        System.out.println("after rejected changes = " + list);
        System.out.println("updated read-only view = " + readOnlyView);
    }

    private static final class NonNegativeList
            extends AbstractList<Integer> implements RandomAccess {
        private final List<Integer> data = new ArrayList<>();

        @Override
        public Integer get(int index) {
            return data.get(index);
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public Integer set(int index, Integer value) {
            Objects.checkIndex(index, data.size());
            check(value);
            return data.set(index, value);
        }

        @Override
        public void add(int index, Integer value) {
            if (index < 0 || index > data.size()) {
                throw new IndexOutOfBoundsException("index: " + index);
            }
            check(value);
            data.add(index, value);
            modCount++;
        }

        @Override
        public Integer remove(int index) {
            Integer previous = data.remove(index);
            modCount++;
            return previous;
        }

        private static void check(Integer value) {
            Objects.requireNonNull(value, "value");
            if (value < 0) {
                throw new IllegalArgumentException("nonnegative value required");
            }
        }
    }

    private static void expect(String label, Class<? extends RuntimeException> type,
                               Runnable action) {
        try {
            action.run();
            throw new AssertionError("operation unexpectedly succeeded");
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all ViewsAndDefaultsDemo.java
java ViewsAndDefaultsDemo
```

Kết quả:

```text
after view set and replaceAll = [2, 40, 6, 8]
after subList clear = [2, 8]
read-only view = [2, 8]
snapshot = [1, 2, 3, 4]
after removeIf and sort = [5, 3, 2]
negative replaceAll -> IllegalArgumentException
negative iterator set -> IllegalArgumentException
read-only add -> UnsupportedOperationException
after rejected changes = [5, 3, 2]
updated read-only view = [5, 3, 2]
```

### 3.4. Những cập nhật nào đã đi qua kiểm tra?

`middle` ban đầu trỏ tới vị trí 1 và 2 của danh sách. `middle.set(0,20)` cập nhật danh sách nền thành `[1,20,3,4]`. `replaceAll(value -> value * 2)` gọi các thao tác thay thế phù hợp và cho `[2,40,6,8]`.

`middle.clear()` sau đó xóa đoạn tương ứng, để lại `[2,8]`. Khung nhìn chỉ đọc nhìn thấy chính trạng thái này, còn `snapshot` vẫn giữ `[1,2,3,4]`. Không có yêu cầu sao chép nào được suy ra từ tên biến; kết quả đến từ API đã dùng để tạo từng đối tượng.

Tiếp theo, `removeIf` xóa 8, rồi danh sách nhận thêm 5 và 3. `sort` sắp xếp lại thành `[5,3,2]`. Trong ví dụ, các giá trị vẫn hợp lệ nên việc ghi lại bằng `set` không vi phạm bất biến.

Hai nỗ lực ghi giá trị âm đều thất bại:

- `replaceAll` tạo kết quả âm ngay tại phần tử đầu, rồi bị `set` từ chối.
- `ListIterator.set(-1)` cũng đi qua `set` có kiểm tra.

Điều quan trọng là cả hai không cần biết một phương thức kiểm tra riêng của ứng dụng. Chúng dùng cùng thao tác nền, nên nhận cùng chính sách. Khung nhìn chỉ đọc vẫn từ chối `add` của chính nó nhưng tiếp tục thấy những sửa đổi hợp lệ qua danh sách nền.

Trong lớp này, `set` không đổi kích thước và không tăng `modCount`; thêm/xóa thành công tăng một lần. Đây là quyết định của cài đặt minh họa dùng bộ duyệt kế thừa. Không suy ra mọi lớp `List` khác, đặc biệt lớp đã ghi đè `sort` hoặc bộ duyệt, phải ghi nhận thay đổi theo hệt cách này.

### 3.5. subList là một vùng vị trí, không phải nhóm phần tử được gắn danh tính

Khung nhìn của danh sách ánh xạ chỉ số và phạm vi về nền. Nó không giữ lời hứa “luôn đi theo đúng hai đối tượng ban đầu” khi bạn thay nội dung hoặc sắp xếp lại các vị trí.

Sau một thay đổi cấu trúc trên nền ngoài đường khung nhìn, đừng tiếp tục dùng khung nhìn cũ như thể nó được tự đồng bộ lại. [List.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)) quy định ngữ nghĩa không xác định trong tình huống sửa cấu trúc nền ngoài khung nhìn. Một triển khai có thể ném `ConcurrentModificationException` để phát hiện, nhưng ngoại lệ không phải giao thức làm mới vùng dữ liệu.

Chương trình ngừng dùng `middle` sau khi xóa đoạn qua chính nó. Những sửa đổi cấu trúc sau đó diễn ra trên danh sách gốc và chỉ được quan sát qua khung nhìn chỉ đọc toàn danh sách, không qua `subList` cũ.

### 3.6. Không cho sửa container chưa đủ để chặn sửa đối tượng bên trong

Trong ví dụ, phần tử là `Integer` nên không có thao tác thay đổi nội dung của chính đối tượng số. Nếu phần tử là một đối tượng có thể sửa, khung nhìn không cho thêm/xóa vẫn có thể trả đối tượng ấy cho phía gọi.

Điều tương tự xảy ra với một collection chứa `Map.Entry` có `setValue`. Chỉ bọc tập hợp chứa entry bằng `Collections.unmodifiableSet` không tự biến các entry bên trong thành bất biến. Một entry còn có khả năng ghi xuyên về map nếu vẫn giữ liên hệ với map nền.

Nếu cần một map chỉ đọc, dùng [Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)) phù hợp giúp áp dụng chính sách qua cả các khung nhìn của map. Nếu tự bọc, bạn phải bảo vệ cả container lẫn khả năng ghi xuyên của những đối tượng được trả ra.

Ngoài ra, đừng cho rằng mọi lớp bọc `Collection` đều ủy quyền phép bằng nhau theo nội dung. `Collections.unmodifiableCollection` dùng `Object.equals` và `Object.hashCode`, còn các API chuyên biệt cho `List`/`Set` giữ nghĩa của giao diện tương ứng. Chọn API đúng loại ngữ nghĩa và đọc hợp đồng, thay vì dựa vào một giả định chung cho mọi lớp bọc.


## 4. Map: put không phải cửa cập nhật duy nhất

### 4.1. Ba khung nhìn cần cùng mô tả một map

Map có ba khung nhìn chính:

| Khung nhìn | Phần dữ liệu được nhìn thấy | Xóa một mục có nghĩa gì? |
| --- | --- | --- |
| `keySet()` | Các khóa | Xóa ánh xạ mang khóa tương ứng. |
| `values()` | Các giá trị, có thể trùng | Xóa ánh xạ tương ứng với lần xuất hiện bị xóa. |
| `entrySet()` | Các cặp khóa–giá trị | Xóa ánh xạ khớp cả khóa và giá trị của mục. |

Đây là các khung nhìn có nền, không phải những bản sao tùy ý. Khi thao tác xóa được hỗ trợ, việc xóa qua chúng phải phản ánh vào map. Các khung nhìn chuẩn này không hỗ trợ thêm bằng `add`/`addAll`; chỉ có một khóa hoặc một giá trị không xác định đầy đủ ánh xạ cần thêm.

`values` không phải một `Set`: hai khóa có thể cùng ánh xạ đến một giá trị. `values().remove(v)` không có nghĩa xóa mọi ánh xạ cùng giá trị; nếu muốn lọc mọi mục thỏa điều kiện, cần một thao tác có ý nghĩa tương ứng, chẳng hạn `removeIf`.

Với `entrySet().contains` hoặc `entrySet().remove`, không được chỉ so khóa rồi bỏ qua giá trị. Một mục `A=10` khác `A=20` dù cùng khóa.

Nguồn hợp đồng là [các khung nhìn của Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html). Cách lớp khung xây chúng có thể được xem thêm ở [AbstractMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.html).

### 4.2. Lần theo các thuật toán trước khi đặt kiểm tra

Với một lớp con của `AbstractMap` dùng các phương thức giao diện mặc định, những đường quan trọng gồm:

```text
putAll(...)                          → put(...) từng ánh xạ
putIfAbsent / replace                → đọc trạng thái, rồi put(...) khi cần
compute / computeIfAbsent / merge    → tính kết quả, rồi put/remove khi cần
Map.replaceAll(...)                  → entrySet() → Entry.setValue(...)
keySet / values / entrySet removal   → đường xóa được khung nhìn hỗ trợ
```

`putAll` trong ví dụ là phương thức kế thừa của `AbstractMap`; `compute`, `merge`, `replaceAll` là các phương thức `default` của `Map`. Không gộp hai khái niệm khi đọc mã.

Điểm dễ bỏ sót là `replaceAll`: cài đặt mặc định không bắt buộc gọi `put` của bạn cho từng kết quả. Nó cập nhật bằng `Entry.setValue`. Nếu `entrySet` trả entry của kho nền nguyên trạng, kiểm tra trong `put` có thể bị vượt qua.

Bài toán “map chỉ giữ số không âm” cần bảo vệ ít nhất hai đường ghi đang công bố: `put` và `Entry.setValue`. Các đường xóa vẫn có thể được hỗ trợ vì xóa một ánh xạ không tạo số âm.

### 4.3. Chương trình: map kiểm tra cả put lẫn entry

`ScoreMap` dưới đây dùng `LinkedHashMap` để kết quả duyệt trong minh họa ổn định. Nó không cho thêm khóa `null`, giá trị `null` hoặc giá trị âm. Nó vẫn cho phép xóa qua các khung nhìn.

Điểm cốt lõi nằm ở `checked`: entry trả ra được bọc để kiểm tra `setValue` và vẫn thực hiện đúng `equals`/`hashCode` của `Map.Entry`. Dữ liệu nền không được công khai.

Lưu thành `CheckedMapDemo.java`:

```java
import java.util.AbstractMap;
import java.util.AbstractSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Map.Entry;
import java.util.Objects;
import java.util.Set;

public class CheckedMapDemo {
    public static void main(String[] args) {
        ScoreMap<String> scores = new ScoreMap<>();
        scores.put("A", 10);
        scores.put("B", 20);
        System.out.println("initial = " + scores);
        Map<String, Integer> reference = Map.of("A", 10, "B", 20);
        System.out.println("map equality both ways = "
                + (scores.equals(reference) && reference.equals(scores)));
        System.out.println("map hash agrees = " + (scores.hashCode() == reference.hashCode()));
        expect("negative put", IllegalArgumentException.class, () -> scores.put("X", -1));
        expect("negative compute", IllegalArgumentException.class,
                () -> scores.compute("A", (key, value) -> -1));
        expect("negative replace", IllegalArgumentException.class,
                () -> scores.replace("A", -2));
        scores.compute("A", (key, value) -> value + 5);
        scores.merge("B", 3, Integer::sum);
        scores.putIfAbsent("C", 7);
        System.out.println("after compute merge putIfAbsent = " + scores);

        Iterator<Entry<String, Integer>> cursor = scores.entrySet().iterator();
        Entry<String, Integer> first = cursor.next();
        Entry<String, Integer> standard = Map.entry("A", 15);
        System.out.println("entry equality agrees = "
                + (first.equals(standard) && standard.equals(first)));
        System.out.println("entry hash agrees = " + (first.hashCode() == standard.hashCode()));
        expect("negative entry setValue", IllegalArgumentException.class,
                () -> first.setValue(-3));
        System.out.println("entry previous value = " + first.setValue(16));
        scores.replaceAll((key, value) -> value + 1);
        System.out.println("after replaceAll = " + scores);

        scores.values().removeIf(value -> value >= 20);
        scores.keySet().remove("C");
        System.out.println("after view removals = " + scores);
        expect("keySet add", UnsupportedOperationException.class,
                () -> scores.keySet().add("X"));
        scores.computeIfPresent("A", (key, value) -> null);
        System.out.println("after null compute result = " + scores);
        expect("null put", NullPointerException.class, () -> scores.put("N", null));

        Map<String, Integer> updates = new LinkedHashMap<>();
        updates.put("D", 4);
        updates.put("E", -1);
        expect("partly applied putAll", IllegalArgumentException.class,
                () -> scores.putAll(updates));
        System.out.println("after rejected putAll = " + scores);

        ScoreMap<String> partial = new ScoreMap<>();
        partial.put("A", 1);
        partial.put("B", 2);
        expect("partly applied replaceAll", IllegalArgumentException.class,
                () -> partial.replaceAll((key, value) -> key.equals("B") ? -1 : value + 10));
        System.out.println("after rejected replaceAll = " + partial);
    }

    private static final class ScoreMap<K> extends AbstractMap<K, Integer> {
        private final Map<K, Integer> data = new LinkedHashMap<>();
        private final Set<Entry<K, Integer>> entries = new AbstractSet<>() {
            @Override
            public int size() {
                return data.size();
            }

            @Override
            public Iterator<Entry<K, Integer>> iterator() {
                Iterator<Entry<K, Integer>> delegate = data.entrySet().iterator();
                return new Iterator<>() {
                    @Override
                    public boolean hasNext() {
                        return delegate.hasNext();
                    }

                    @Override
                    public Entry<K, Integer> next() {
                        return checked(delegate.next());
                    }

                    @Override
                    public void remove() {
                        delegate.remove();
                    }
                };
            }
        };

        @Override
        public Integer put(K key, Integer value) {
            Objects.requireNonNull(key, "key");
            check(value);
            return data.put(key, value);
        }

        @Override
        public Set<Entry<K, Integer>> entrySet() {
            return entries;
        }

        private Entry<K, Integer> checked(Entry<K, Integer> delegate) {
            return new Entry<>() {
                @Override
                public K getKey() {
                    return delegate.getKey();
                }

                @Override
                public Integer getValue() {
                    return delegate.getValue();
                }

                @Override
                public Integer setValue(Integer value) {
                    check(value);
                    return delegate.setValue(value);
                }

                @Override
                public boolean equals(Object other) {
                    return other instanceof Entry<?, ?> entry
                            && Objects.equals(getKey(), entry.getKey())
                            && Objects.equals(getValue(), entry.getValue());
                }

                @Override
                public int hashCode() {
                    return Objects.hashCode(getKey()) ^ Objects.hashCode(getValue());
                }

                @Override
                public String toString() {
                    return getKey() + "=" + getValue();
                }
            };
        }

        private static void check(Integer value) {
            Objects.requireNonNull(value, "value");
            if (value < 0) {
                throw new IllegalArgumentException("nonnegative value required");
            }
        }
    }

    private static void expect(String label, Class<? extends RuntimeException> type,
                               Runnable action) {
        try {
            action.run();
            throw new AssertionError("operation unexpectedly succeeded");
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all CheckedMapDemo.java
java CheckedMapDemo
```

Kết quả:

```text
initial = {A=10, B=20}
map equality both ways = true
map hash agrees = true
negative put -> IllegalArgumentException
negative compute -> IllegalArgumentException
negative replace -> IllegalArgumentException
after compute merge putIfAbsent = {A=15, B=23, C=7}
entry equality agrees = true
entry hash agrees = true
negative entry setValue -> IllegalArgumentException
entry previous value = 15
after replaceAll = {A=17, B=24, C=8}
after view removals = {A=17}
keySet add -> UnsupportedOperationException
after null compute result = {}
null put -> NullPointerException
partly applied putAll -> IllegalArgumentException
after rejected putAll = {D=4}
partly applied replaceAll -> IllegalArgumentException
after rejected replaceAll = {A=11, B=2}
```

### 4.4. Hai điểm kiểm tra bao phủ những đường nào?

Ở đầu chương trình, map tùy chỉnh bằng map tham chiếu theo cả hai chiều và có cùng mã băm. Điều này kiểm chứng khả năng tương tác, không chỉ việc tự in một chuỗi trông giống map.

Ba cách ghi số âm qua `put`, `compute` và `replace` đều bị từ chối. Hai phương thức sau dùng thao tác `put` có kiểm tra khi cần lưu kết quả. Sau đó các phép tính hợp lệ cập nhật A thành 15, B thành 23 và thêm C với 7.

Một entry của A được lấy trong quá trình duyệt. Nó bằng `Map.entry("A",15)` ở cả hai chiều và có mã băm tương thích. Thử `setValue(-3)` thất bại; `setValue(16)` thành công và trả giá trị cũ 15.

`replaceAll` tiếp theo đi qua các entry có kiểm tra, làm map thành `{A=17, B=24, C=8}`. Nếu chỉ trả entry của kho nền mà không bọc, thao tác này là một đường có thể đưa giá trị không hợp lệ vào mà không qua `put`.

Phần xóa qua khung nhìn chứng minh chiều liên hệ ngược về map: `values().removeIf(...)` xóa ánh xạ B, `keySet().remove("C")` xóa C. `keySet().add("X")` bị từ chối; một khóa đơn không tự tạo được giá trị ánh xạ.

`computeIfPresent` trả kết quả `null` cho A, làm A bị xóa. Điều đó khác với `put("N",null)`, vốn cố lưu một giá trị không được phép và bị từ chối.

### 4.5. Vì sao wrapper Entry phải giữ cả hợp đồng đọc và bằng nhau?

Nếu chỉ chặn `setValue` nhưng entry bọc vẫn dùng `Object.equals` và `Object.hashCode`, `entrySet` có thể không còn biểu diễn đúng một tập hợp ánh xạ. So sánh hoặc mã băm map kế thừa cũng có thể sai theo.

`checked` dùng khóa và giá trị hiện có của entry nền để thực hiện ba việc:

- Trả dữ liệu của cùng ánh xạ đang được duyệt.
- So sánh khóa và giá trị theo hợp đồng entry, kể cả khi đối phương thuộc lớp khác.
- Tính mã băm XOR đúng; không dựa vào danh tính của đối tượng bọc.

Đối tượng bọc không được coi là một vé cập nhật tồn tại vĩnh viễn. [Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html) giới hạn liên hệ của entry lấy từ khung nhìn trong quá trình duyệt và quy định hành vi không xác định khi map thay đổi theo những cách ngoài các trường hợp được hỗ trợ. Đừng giữ entry rồi dùng lại sau khi xóa ánh xạ để kỳ vọng một cơ chế gắn lại tự động.

Nếu cần giữ lại một cặp dữ liệu độc lập, tạo bản sao entry phù hợp. `Map.Entry.copyOf` tạo entry độc lập không cho sửa, với chính sách không nhận khóa/giá trị `null` như `Map.entry`. `AbstractMap.SimpleImmutableEntry` là một lựa chọn khác cần đọc theo chính sách phần tử của nó. Các cách ấy chỉ tách cặp ánh xạ; chúng không sao chép sâu đối tượng khóa hay giá trị.

### 4.6. Cẩn thận khi tối ưu đường trả entry

Trong ví dụ, `entrySet` dựa trên `AbstractSet` và chỉ cung cấp cách duyệt đã bọc. Những đường kế thừa dùng bộ duyệt sẽ nhận entry được kiểm tra.

Nếu sau này tự ghi đè `toArray`, `forEach` hoặc `spliterator` để chạy nhanh hơn bằng cách chuyển thẳng sang kho nền, bạn có thể vô tình trả entry chưa bọc ra ngoài. Khi đó chính sách bị hở trở lại dù `iterator().next()` vẫn trông đúng.

Vì vậy, khi một đối tượng trả ra còn có khả năng sửa dữ liệu nền, kiểm tra mọi đường trả đối tượng ấy, không chỉ bộ duyệt thông thường. Việc giữ một trường `data` là `private` không đủ nếu các đối tượng có quyền ghi xuyên vẫn thoát ra ngoài.

Lớp ví dụ ưu tiên đường gọi rõ ràng hơn tối ưu tra cứu. Một số thao tác kế thừa của `AbstractMap` tìm bằng cách duyệt `entrySet`. Nó là minh họa về hợp đồng và kiểm tra đầu vào, chưa phải một map tối ưu thay thế mọi nhu cầu thực tế.

## 5. Phương thức mặc định không bổ sung mọi bảo đảm bạn muốn

### 5.1. null có nhiều ý nghĩa khác nhau trong Map

Một map cho phép giá trị `null` cần phân biệt “không có khóa” và “có khóa nhưng giá trị là null”. Chỉ nhìn `get(k) == null` không phân biệt được hai trạng thái này; `containsKey` có thể cần thiết.

Các thao tác có quy tắc riêng:

| Thao tác | Vai trò của null cần nhớ |
| --- | --- |
| `getOrDefault(k,d)` | Nếu khóa tồn tại với giá trị `null`, kết quả vẫn là `null`, không phải `d`. |
| `putIfAbsent` | Giá trị hiện tại `null` được xử lý như trường hợp cần gán giá trị mới. |
| `computeIfAbsent` | Có thể tính khi giá trị hiện tại là `null`; kết quả `null` không tạo một ánh xạ mới. |
| `computeIfPresent` | Chỉ tính khi đang có giá trị khác `null`; kết quả `null` xóa ánh xạ đó. |
| `compute` | Có thể nhận giá trị cũ `null`; kết quả `null` làm ánh xạ không còn tồn tại. |
| `merge` | Giá trị truyền vào phải khác `null`; khi không có giá trị khác `null`, dùng giá trị truyền vào mà không cần gọi hàm gộp. Kết quả `null` của hàm gộp xóa ánh xạ. |
| `replaceAll` | Kết quả `null` là một giá trị muốn gán, không phải tín hiệu xóa. Map có thể từ chối nếu không nhận `null`. |

Riêng `computeIfAbsent`, nếu khóa đã có ánh xạ `null` và hàm tính trả `null`, đừng suy ra ánh xạ ấy được xóa. Hành vi “không ghi giá trị mới” khác hành vi xóa của `compute` hay `computeIfPresent`.

`ScoreMap` không lưu giá trị `null`, nên `get` trả `null` biểu diễn trường hợp không có ánh xạ. Nhưng khi tự thiết kế một lớp tổng quát nhận `null`, bạn phải giữ sự phân biệt ở các thao tác đọc, thay có điều kiện và tính toán.

Nguồn đối chiếu là từng phương thức trong [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html). Đừng gán một quy tắc chung “null luôn là xóa” cho mọi API.

### 5.2. Giữ bất biến khác với hoàn tác toàn bộ thao tác

Cuối chương trình có hai kết quả dễ hiểu nhầm:

- `putAll` thêm D=4 trước, rồi từ chối E=-1. D vẫn còn.
- `replaceAll` thay A=1 thành A=11 trước, rồi từ chối kết quả âm cho B. A vẫn là 11, B vẫn là 2.

Cả hai trạng thái cuối đều giữ bất biến không có giá trị âm. Nhưng thao tác hàng loạt chưa hoàn tất toàn bộ. Ngoại lệ không tự làm những cập nhật hợp lệ trước đó quay lại trạng thái cũ.

Trong ví dụ, thứ tự này ổn định vì dùng `LinkedHashMap` cho nguồn/cấu trúc nền liên quan. Với cấu trúc không cam kết thứ tự duyệt, không được hứa phần tử nào đã thay đổi trước khi lỗi xảy ra.

Nếu yêu cầu nghiệp vụ là “tất cả cùng thành công hoặc không thay đổi gì”, cần một thiết kế khác có bước chuẩn bị/kiểm tra và cơ chế công bố phù hợp. Chỉ thêm vòng kiểm tra đầu vào trước chưa tự giải quyết việc nhiều luồng thay đổi hoặc hàm tính có tác dụng phụ.

Các hàm truyền vào `compute`/`merge` nên tính kết quả mà không sửa chính map đang được tính. Một phép kiểm tra ở lớp bọc không thể hoàn tác các tác dụng phụ tùy ý mà hàm gọi đã gây ra ở nơi khác.

### 5.3. Phương thức default của Map không mặc nhiên nguyên tử

Một chuỗi “đọc hiện tại → tính → ghi” có thể thực hiện đúng trong một luồng nhưng không cung cấp bảo đảm nguyên tử khi nhiều luồng truy cập. Hợp đồng các phương thức mặc định của `Map` không tự hứa đồng bộ hóa hoặc nguyên tử.

Không đổi tên lớp bọc thành một map đồng thời chỉ vì nó có `compute` hay `putIfAbsent`. Nếu cần những bảo đảm ấy, phải dùng hoặc cài đặt một hợp đồng đồng thời phù hợp, áp dụng nhất quán qua phương thức và khung nhìn, rồi công bố rõ ràng.

Các chương trình trong bài chỉ chạy một luồng. Chúng kiểm chứng đường cập nhật, bằng nhau và kết quả quan sát; chúng không phải bằng chứng an toàn cho truy cập đồng thời.

### 5.4. Không được hỗ trợ cũng là một chính sách phải nhất quán

Một cấu trúc chỉ đọc có thể từ chối thao tác sửa bằng `UnsupportedOperationException`. Nhưng đừng lấy một lần gọi không làm thay đổi dữ liệu, chẳng hạn xóa mục không tồn tại hoặc thêm một tập rỗng, để khẳng định cấu trúc hỗ trợ sửa.

Ngược lại, khi viết lớp bọc chỉ đọc, không chỉ chặn `put`/`add` rồi để mặc các phương thức mới, bộ duyệt hay khung nhìn ghi xuyên. Cần rà soát cả những phương thức giao diện mặc định và những đối tượng có thể trả ra.

Khi phiên bản Java mục tiêu thay đổi, kiểm tra bề mặt API mới và các phương thức mới được kế thừa. Bản chất yêu cầu vẫn là: mọi đường vào cùng một dữ liệu phải giữ chính sách mà lớp đã công bố.


## 6. Cách rà soát một cài đặt tùy chỉnh có hệ thống

### 6.1. Viết hợp đồng trước khi chọn điểm ghi đè

Trước khi kiểm tra mã, ghi rõ những điều lớp muốn công bố:

- Nó thực hiện `Collection`, `List`, `Set` hay `Map`? Phép bằng nhau theo hợp đồng nào?
- Cho phép phần tử/khóa/giá trị `null` không? Chấp nhận trùng, thứ tự và phép so sánh nào?
- Cho thêm, thay thế, xóa hay chỉ một phần trong số đó?
- Khung nhìn nào có thể sửa? Đối tượng trả ra có quyền ghi xuyên không?
- Lỗi ở thao tác hàng loạt có cho phép trạng thái áp dụng một phần không?
- Có bảo đảm đồng thời nào thật sự được cung cấp không?

Không cần thêm một chính sách nghiệp vụ vào mọi phương thức bằng cách sao chép cùng một đoạn mã. Tìm các thao tác nền bao phủ được nhiều đường, rồi xác nhận không có đường vòng. Ví dụ danh sách đặt kiểm tra ở `add` theo vị trí và `set`; ví dụ map đặt ở `put` và entry ghi xuyên.

Nếu kế thừa một lớp cụ thể rồi ủy quyền thẳng một phương thức tối ưu sang kho nền, hãy kiểm tra lại: bạn có đang bỏ qua các điểm bảo vệ ở lớp ngoài không? Mục tiêu tái sử dụng mã không cho phép thay đổi hợp đồng một cách vô tình.

### 6.2. Kiểm tra theo nhóm hợp đồng, không chỉ theo tên phương thức

| Nhóm cần kiểm chứng | Tình huống có giá trị |
| --- | --- |
| Quan hệ bằng nhau | Cùng nội dung với một cài đặt chuẩn; kiểm tra cả hai chiều; cùng loại API nhưng khác lớp. |
| Mã băm | Mọi cặp đã được xác định bằng nhau có cùng mã băm; không đòi cặp khác nhau phải khác mã băm. |
| Ngữ nghĩa loại dữ liệu | Danh sách đổi thứ tự phải được xét lại; tập hợp không trùng; map so ánh xạ chứ không so thứ tự duyệt. |
| Đường sửa trực tiếp | Thêm, thay, xóa, đầu vào không hợp lệ và giá trị biên. |
| Đường qua bộ duyệt | `Iterator.remove`, `ListIterator.add/set/remove` khi được hỗ trợ. |
| Đường qua khung nhìn | `subList`, `keySet`, `values`, `entrySet` và entry ghi xuyên. |
| Thuật toán mặc định/kế thừa | `removeIf`, `replaceAll`, `sort`, `putAll`, các phép tính và thay có điều kiện của map. |
| Lỗi giữa chừng | Theo dõi chính xác những cập nhật đã thành công và bất biến còn được giữ hay không. |
| Đường trả dữ liệu | Bộ duyệt, mảng, duyệt bằng hàm, stream: có trả đối tượng bỏ qua kiểm tra không? |

Một phép thử chỉ so `custom.equals(custom)` không kiểm chứng được tương tác giữa các cài đặt. Một phép thử chỉ gọi `put` không nhìn thấy lỗi qua `Entry.setValue`. Một phép thử chỉ dùng đầu vào hợp lệ không xác nhận chính sách từ chối.

Khi có ngẫu nhiên trong kiểm thử, nên giữ đầu vào hoặc hạt giống có thể lặp lại. Nhưng với các vấn đề trong bài, những ví dụ nhỏ được chọn đúng thường cho bằng chứng rõ hơn một lần chạy nhiều thao tác mà không biết đường gọi nào đang được kiểm tra.

### 6.3. So sánh trạng thái quan sát được sau từng bước

Với một thao tác được hỗ trợ, kiểm tra cả:

1. Kết quả trả về hoặc loại ngoại lệ.
2. Nội dung, kích thước và quan hệ giữa các khung nhìn sau đó.
3. Bất biến còn đúng trên mọi phần tử/ánh xạ.
4. Quan hệ bằng nhau và mã băm khi so với trạng thái tham chiếu tương ứng.

Đừng chỉ kiểm tra “đã có ngoại lệ”. Ví dụ `replaceAll` từ chối số âm nhưng để một số âm lọt vào trước khi ném vẫn là lỗi bất biến. Ngược lại, việc đã thay A hợp lệ trước khi từ chối B không tự là lỗi nếu hợp đồng không hứa hoàn tác cả thao tác.

Cũng không dùng chuỗi `toString` làm định nghĩa duy nhất của bằng nhau. Nó hữu ích để quan sát ví dụ, nhưng thứ tự in có thể khác trong những cấu trúc không hứa thứ tự; hai đối tượng in giống nhau cũng không tự có cùng hợp đồng API.

### 6.4. Tách hợp đồng, cài đặt nền và bằng chứng chạy

Ba lớp thông tin cần được giữ riêng:

- **Hợp đồng:** điều mà API Java và lớp của bạn công bố cho phía gọi.
- **Cài đặt:** thuật toán cụ thể đang dùng, gồm lớp nền và những phương thức đã ghi đè.
- **Bằng chứng:** một phép chạy hoặc kiểm thử xác nhận một số tình huống xác định.

Trong bài, Java 17 là mức API/cú pháp được chọn khi biên dịch. Các đường mặc định được đối chiếu với tài liệu Java 17 và mã nguồn OpenJDK 17u. Ba chương trình xác nhận các tình huống đã in trên một runtime thực tế.

Không nâng một kết quả đơn lẻ thành bảo đảm ngoài hợp đồng, chẳng hạn mọi lỗi sẽ ném trước khi sửa, mọi map đều duyệt theo thứ tự thêm hoặc mọi phương thức tên `compute` đều nguyên tử.

## 7. Thực hành có lời giải

### Câu 1. List tùy chỉnh chỉ bằng đối tượng cùng lớp

Bạn viết `equals` của một `List` bằng cách yêu cầu `other.getClass() == getClass()`. Nó chứa `["A","B"]` và một `ArrayList` cũng chứa như vậy. Có thể xảy ra lỗi gì?

**Lời giải:** danh sách tùy chỉnh có thể trả `false` khi so với `ArrayList`, trong khi `ArrayList` trả `true` khi so ngược. Điều này vi phạm tính đối xứng và hợp đồng bằng nhau giữa các cài đặt `List`. Giữ quy tắc danh sách hoặc dùng cài đặt nền phù hợp, không tự hạn chế bằng nhau theo lớp cụ thể.

**Thực hành:** lấy `Words` ở chương trình đầu, kiểm tra thêm với `LinkedList` và một danh sách cùng phần tử nhưng khác thứ tự. So sánh cả hai chiều và mã băm cho các cặp bằng nhau.

### Câu 2. Hai entry bằng nhau nhưng mã băm khác

Một wrapper entry so khóa/giá trị đúng, nhưng `hashCode` dùng `Objects.hash(key,value)`. Vì sao việc tự so hai wrapper vẫn có thể bỏ sót lỗi?

**Lời giải:** hai wrapper cùng công thức sai có thể cho cùng kết quả, nhưng không tương thích với một `Map.Entry` chuẩn biểu diễn cùng ánh xạ. Phải dùng công thức XOR của hợp đồng entry và kiểm tra chéo với một cài đặt khác. Sai ở entry còn có thể ảnh hưởng mã băm của `entrySet` và map.

**Thực hành:** thử cả khóa/giá trị khác `null` và các trường hợp `null` nếu kiểu entry mục tiêu cho phép. Không tạo trường hợp `null` bằng một API vốn từ chối `null` rồi hiểu nhầm ngoại lệ là lỗi của công thức.

### Câu 3. Chặn số âm trong put nhưng trả entry nền

Một lớp bọc map ghi đè `put` để từ chối số âm, còn `entrySet` trả thẳng `data.entrySet()`. Hai cách nào có thể vượt qua lớp kiểm tra?

**Lời giải:** gọi `setValue(-1)` trên entry được trả ra; hoặc dùng cài đặt mặc định `replaceAll` tạo kết quả âm, vì nó cập nhật qua `Entry.setValue`. Cần bảo vệ entry ghi xuyên hoặc từ chối rõ ràng khả năng ấy và cung cấp những thao tác được công bố theo cách phù hợp.

**Thực hành:** trong một bản thử riêng, thay đường entry được bọc của `ScoreMap` bằng đường nền rồi quan sát bất biến bị phá. Sau đó phục hồi wrapper và kiểm chứng cả phép bằng nhau/mã băm của entry, không chỉ ngoại lệ khi cập nhật.

### Câu 4. Bọc entrySet bằng unmodifiableSet đã đủ làm map chỉ đọc chưa?

**Lời giải:** chưa. Việc cấm thêm/xóa khỏi tập hợp không tự cấm `setValue` của đối tượng entry nằm trong tập hợp. Một khung nhìn map chỉ đọc cần bảo vệ khả năng ghi xuyên của entry, các phương thức sửa và các khung nhìn liên quan. API `Collections.unmodifiableMap` là điểm xuất phát thích hợp khi cần chính sách này với một map có sẵn.

**Thực hành:** phân biệt container không cho sửa với phần tử không cho sửa. Liệt kê các đường có thể nhận entry: bộ duyệt, mảng và stream; xác định đường nào phải cung cấp entry được bảo vệ.

### Câu 5. Khung nhìn chỉ đọc thay đổi sau khi nền đổi

Bạn tạo `Collections.unmodifiableList(source)` rồi thêm vào `source`. Khung nhìn thấy phần tử mới có vi phạm lời hứa chỉ đọc không?

**Lời giải:** không. Khung nhìn không cho sửa qua chính nó nhưng vẫn đọc từ nguồn. Nếu cần không phản ánh các thay đổi cấu trúc sau đó, chọn một bản sao với hợp đồng phù hợp. Với `List.copyOf`, cần lưu ý chính sách từ chối `null` và việc không sao chép sâu phần tử.

**Thực hành:** dùng hai đối tượng như chương trình danh sách: một khung nhìn chỉ đọc và một bản sao. Thay phần tử, thêm và xóa ở nguồn; dự đoán từng trạng thái trước khi chạy.

### Câu 6. null từ compute và null từ replaceAll

Map không cho lưu giá trị `null`. Hàm của `computeIfPresent` trả `null`, còn hàm của `replaceAll` cũng trả `null`. Chúng có cùng ý nghĩa không?

**Lời giải:** không. `computeIfPresent` dùng kết quả `null` để xóa ánh xạ đang có giá trị khác `null`. `replaceAll` muốn gán kết quả ấy vào entry; map không nhận `null` có thể từ chối. Không suy ra “map cấm null nên mọi hàm tính trả null đều phải ném lỗi”.

**Thực hành:** mở rộng `ScoreMap` bằng một phép thử cho từng phương thức và kiểm tra trạng thái sau đó. Khi thử thao tác hàng loạt, ghi nhận cả khả năng áp dụng một phần.

### Câu 7. Đã giữ bất biến thì thao tác có nguyên tử chưa?

`replaceAll` thay A thành 11 rồi bị từ chối ở B, và mọi giá trị còn lại đều không âm. Có thể kết luận thao tác đã được hoàn tác hoặc nguyên tử không?

**Lời giải:** không. Bất biến không âm vẫn được giữ nhưng trạng thái đã áp dụng một phần. Tính nguyên tử và hoàn tác là những yêu cầu riêng, không được thêm vào chỉ từ sự tồn tại của kiểm tra giá trị. Với nhiều luồng, các phương thức mặc định `Map` cũng không tự mang bảo đảm đồng thời.

**Thực hành:** viết trạng thái trước và sau của phần `partial` trong chương trình map. Nêu chính xác điều đã được chứng minh: không có giá trị âm, A đã đổi, B giữ nguyên; không thêm kết luận về giao dịch hoặc nhiều luồng.

## 8. Kiểm chứng và tài liệu tra cứu

Ba chương trình trong bài được biên dịch với `javac --release 17 -encoding UTF-8 -Xlint:all` và chạy trên OpenJDK 24.0.2; đầu ra khớp các khối `text` đã nêu. `--release 17` xác định mức cú pháp/API khi biên dịch, không có nghĩa lần chạy này dùng JVM 17.

Các ví dụ không phụ thuộc thứ tự duyệt của `HashMap`/`HashSet` để in một danh sách phần tử. Ví dụ map kiểm tra cập nhật một phần dùng `LinkedHashMap` để thứ tự liên quan được xác định. Mọi phép chạy đều trong một luồng.

Nguồn chính:

- [Object — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): hợp đồng bằng nhau và mã băm.
- [Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html), [List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): ngữ nghĩa collection, khung nhìn và thuật toán mặc định liên quan.
- [Map — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): các khung nhìn, tính toán, thay có điều kiện, quy tắc `null` và giới hạn bảo đảm nguyên tử mặc định.
- [Map.Entry — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html): phép bằng nhau, XOR mã băm, ghi xuyên và vòng đời của entry.
- [Collections — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): các lớp bọc không cho sửa.
- [AbstractMap — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.html): cách dùng `entrySet` làm nền cho một cài đặt.
- [Mã Map trong OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/Map.java) và [mã List](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/List.java): đối chiếu những đường gọi của phương thức mặc định đang bàn; lớp cụ thể có thể ghi đè chúng.
