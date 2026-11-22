# checkedCollection, checkedList, checkedSet và checkedMap

## 1. Kiểm tra kiểu ở đúng nơi dữ liệu đi vào

Một biến khai báo là `List<String>` cho người đọc biết danh sách chứa chuỗi. Trong chương trình sử dụng generics đúng cách, trình biên dịch giúp duy trì điều đó: lời gọi thêm một `Integer` vào danh sách này không biên dịch được. Vấn đề xuất hiện khi danh sách đi qua mã cũ sử dụng kiểu thô (raw type), phép ép kiểu không được kiểm tra (unchecked cast) hoặc một thư viện không tuân thủ khai báo kiểu.

Giả sử một thư viện nhận danh sách tên người dùng dưới dạng `List` rồi thêm số `42`. `ArrayList` không tự ghi nhớ rằng tham số kiểu ban đầu là `String`. Lần ghi sai có thể hoàn tất; lỗi chỉ lộ ra khi một đoạn mã khác đọc phần tử và dùng nó như chuỗi. Dấu vết ngăn xếp khi ấy chỉ tới nơi đọc, khiến việc tìm nơi đã ghi sai khó hơn.

Các hàm `Collections.checkedCollection`, `checkedList`, `checkedSet` và `checkedMap` tạo một **khung nhìn kiểm tra kiểu lúc chạy** (dynamically typesafe view). Khi có dữ liệu không tương thích được đưa vào qua khung nhìn, thao tác bị chặn bằng `ClassCastException`. Mục đích thực tế là kéo lỗi về gần điểm ghi sai, nơi còn biết thành phần nào đã cung cấp dữ liệu.

Trong bài này:

- **Cấu trúc gốc** (backing collection/map) thực sự giữ các phần tử hoặc ánh xạ.
- **Lớp bọc** (wrapper) là đối tượng do hàm `checked...` trả về; nó chuyển tiếp thao tác tới cấu trúc gốc sau bước kiểm tra cần thiết.
- **Đối tượng mô tả kiểu lúc chạy** (type token) là đối tượng `Class` như `String.class` hoặc `Integer.class`.
- **Nhiễm kiểu** (heap pollution) là tình trạng một tham chiếu có kiểu tham số hóa không còn phù hợp với đối tượng/dữ liệu thực tế mà nó đại diện.

Luồng ghi cần hình dung:

```text
Mã gọi
  -> khung nhìn checked, giữ type token
  -> kiểm tra phần tử / khóa / giá trị sắp ghi
  -> thao tác trên cấu trúc gốc

Ghi thẳng vào cấu trúc gốc
  -> không đi qua bước kiểm tra của khung nhìn
```

Khung nhìn vẫn chia sẻ dữ liệu với cấu trúc gốc. Nó không tạo bản sao, không tự khóa truy cập và không biến các đối tượng phần tử thành bất biến. Vì vậy, bài toán ở đây là bảo vệ một ranh giới ghi dữ liệu trước sai lệch kiểu, gắn với cách quản lý các tham chiếu đang cùng trỏ vào cấu trúc đó. [API `checkedCollection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#checkedCollection(java.util.Collection,java.lang.Class)) mô tả trực tiếp trường hợp tích hợp thư viện và truy tìm lỗi kiểu.

## 2. Chọn đúng hàm theo hợp đồng cần giữ

Các chữ ký dưới đây được rút gọn để đọc; đây là khai báo API, không phải chương trình chạy độc lập:

```java
static <E> Collection<E> checkedCollection(Collection<E> c, Class<E> type);
static <E> List<E> checkedList(List<E> list, Class<E> type);
static <E> Set<E> checkedSet(Set<E> s, Class<E> type);
static <K, V> Map<K, V> checkedMap(
        Map<K, V> map, Class<K> keyType, Class<V> valueType);
```

| Hàm | Kết quả nhìn từ mã gọi | Dữ liệu cần kiểm tra khi ghi | Khi nên chọn |
| --- | --- | --- | --- |
| `checkedCollection` | `Collection<E>` | Phần tử | Chỉ cần giao diện collection tổng quát |
| `checkedList` | `List<E>` | Phần tử thêm hoặc thay thế | Cần chỉ số, `set`, `ListIterator`, `subList` |
| `checkedSet` | `Set<E>` | Phần tử được đưa vào tập hợp | Cần giữ ý nghĩa tập hợp và hợp đồng bằng nhau của `Set` |
| `checkedMap` | `Map<K,V>` | Khóa và giá trị; cả giá trị thay thế | Cần giữ ánh xạ khóa–giá trị |

Hàm được chọn quyết định giao diện của lớp bọc. Bọc một `ArrayList` bằng `checkedCollection` không tạo ra một `List` chỉ vì cấu trúc gốc là list. Mã gọi không nên ép kết quả này về `List` để lấy `get` hoặc `set`. Nếu hợp đồng cần list, hãy tạo bằng `checkedList` ngay từ đầu.

Tương tự, gán kết quả của `checkedList` vào biến `Collection<String>` chỉ thu hẹp những phương thức có thể gọi qua biến ấy; đối tượng vẫn là một khung nhìn `List`. Hai tình huống “chọn hàm tạo lớp bọc tổng quát” và “khai báo biến bằng siêu giao diện” có tác động khác nhau.

### 2.1. Khác biệt về equals và hashCode

`Collection` không quy định một phép so sánh nội dung chung có thể áp dụng đồng thời cho list và set. `List` so sánh theo dãy phần tử; `Set` có hợp đồng của tập hợp. Do đó, `checkedCollection` dùng cách so sánh và mã băm theo `Object`, không chuyển tiếp `equals` và `hashCode` sang cấu trúc gốc.

Ví dụ, hai khung nhìn tổng quát chứa cùng dãy số không vì thế mà bằng nhau. Ngược lại, khung nhìn được tạo bằng `checkedList` vẫn phải đáp ứng hợp đồng bằng nhau của `List`, và `checkedSet` phải đáp ứng hợp đồng của `Set`. Chọn hàm bọc theo giao diện thực sự cần cung cấp; đừng dùng `checkedCollection` như một bản thay thế hoàn toàn tương đương của cả ba loại.

Đây cũng là lý do không nên suy luận một lớp bọc “chuyển tiếp tất cả mọi phương thức y hệt” chỉ từ việc `toString` của nó trông giống dữ liệu gốc.

## 3. Generics và Class phối hợp như thế nào?

Generics phát hiện lỗi dựa trên kiểu mà trình biên dịch nhìn thấy. Đối tượng mô tả kiểu cung cấp một phép kiểm tra bổ sung khi chương trình đang chạy. Hai lớp kiểm tra phục vụ những thời điểm khác nhau.

Đoạn minh họa sau cố ý có một dòng không biên dịch; không dùng nó như một tệp chạy độc lập:

```java
List<String> names =
        Collections.checkedList(new ArrayList<>(), String.class);

names.add("Mai");   // Hop le.
names.add(42);      // Loi bien dich: 42 khong phai String.
```

Trong mã thô, lời gọi thêm số có thể vượt qua kiểm tra tĩnh với cảnh báo. Lớp bọc vẫn giữ `String.class` nên kiểm tra lúc chạy tiếp tục có hiệu lực. Ép biến lớp bọc về kiểu thô không làm biến mất đối tượng lớp bọc.

### 3.1. “Đúng kiểu” là tương thích gán, không phải cùng một lớp cụ thể

Một `Collection<Number>` được bọc với `Number.class` có thể nhận `Integer`, `Double` và các kiểu con phù hợp khác. Một collection được bọc với `CharSequence.class` có thể nhận `String` hoặc `StringBuilder`.

Điều kiện không phải `value.getClass() == type`. Mô hình phù hợp hơn với giá trị khác `null` là phép thử `type.isInstance(value)`. [`Class.isInstance`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isInstance(java.lang.Object)) mô tả việc chấp nhận kiểu con và kiểu triển khai giao diện.

Điều này giải thích hai kết quả khác nhau:

- `Number.class` chấp nhận đối tượng `Integer` mang giá trị `7`.
- `Integer.class` không chấp nhận đối tượng `Long` mang giá trị `7L`, dù hai số có cùng giá trị toán học.

Lớp bọc không phân tích chuỗi, không chuyển `Long` thành `Integer` và không kiểm tra số dương hay số âm. Việc chuyển đổi và quy tắc nghiệp vụ cần được xử lý ở tầng nhận dữ liệu.

### 3.2. Chọn Integer.class thay cho int.class

Collection chứa tham chiếu đến đối tượng. Với `List<Integer>`, hãy truyền `Integer.class`. Giá trị `7` trong lời gọi `add(7)` được đóng hộp thành `Integer` trước khi tới phương thức.

Một điểm dễ gây bất ngờ là biểu thức `int.class` vẫn có thể được truyền vào lời gọi suy luận `Class<Integer>`. Tuy nhiên, đối tượng lớp đó đại diện cho kiểu nguyên thủy `int`, không đại diện cho lớp `Integer`. `int.class.isInstance(...)` luôn trả về `false`; lớp bọc vì vậy từ chối đối tượng số đã đóng hộp. Chương trình thứ ba sẽ chứng minh tình huống này. Không dùng token nguyên thủy như một cách viết ngắn hơn của token lớp bao.

### 3.3. Null là một chính sách riêng

Một đối tượng `Class` hợp lệ không tự tạo ra quy tắc cấm `null`. Với cấu trúc gốc cho phép `null`, khung nhìn có kiểm tra kiểu thông thường vẫn cho phép phần tử `null`; map còn có thể cho phép khóa hoặc giá trị `null` theo chính sách của map gốc.

Do đó:

- `checkedList(new ArrayList<>(), String.class)` có thể nhận `null`.
- Khi bọc một cấu trúc gốc vốn cấm `null`, lớp bọc không gỡ bỏ lệnh cấm đó.
- Truyền chính đối số collection/map là `null`, hoặc truyền đối tượng mô tả kiểu là `null`, gây `NullPointerException` khi tạo lớp bọc.
- Với `Map.merge`, đối số giá trị đưa vào còn chịu hợp đồng riêng của `merge`; map cho phép lưu `null` không có nghĩa mọi phương thức nhận đối số `null` theo cùng cách.

Không thể suy ra “danh sách này không có giá trị rỗng” từ tên `checkedList`. Nếu miền nghiệp vụ cấm `null`, cần xác thực ràng buộc đó khi nhận dữ liệu.

## 4. Các đường ghi phải cùng đi qua lớp bọc

Với một `List`, ghi dữ liệu không chỉ có `add`. Còn có `set`, `add(index, value)`, `addAll`, `ListIterator.add`, `ListIterator.set` và việc sửa qua `subList`. Một lớp bọc kiểm tra đúng hợp đồng phải giữ ranh giới kiểu qua các đường này.

Với một `Set`, phần tử vẫn phải qua kiểm tra kiểu trước khi có thể được chấp nhận vào tập hợp. Quy tắc phần tử trùng lặp tiếp tục thuộc về tập hợp. `checkedSet` không biến kết quả `add` thành “luôn thêm thành công” và không tạo thứ tự duyệt mới.

Với một `Map`, một ánh xạ mới cần cả khóa lẫn giá trị phù hợp. Cập nhật giá trị của khóa đã có cũng phải được kiểm tra. Đặc biệt, `Map.Entry.setValue` trên entry lấy từ `checkedMap.entrySet()` không được trở thành lối đi vòng qua kiểm tra.

Các phương thức nhận một hàm gọi lại (callback) cũng có thể tạo ra dữ liệu ghi mới. Ví dụ:

| Thao tác | Kết quả cần quan tâm |
| --- | --- |
| `List.replaceAll` | Phần tử do hàm biến đổi trả về |
| `Map.compute`, `computeIfAbsent`, `computeIfPresent` | Giá trị tính ra nếu thao tác sẽ ghi ánh xạ |
| `Map.merge` | Giá trị đầu vào và giá trị hợp nhất sẽ được lưu |
| `Map.replaceAll` | Giá trị thay thế do hàm gọi lại trả về |
| `Map.Entry.setValue` | Giá trị mới đi vào entry |

Với hàm gọi lại có khai báo kiểu đúng, trình biên dịch đã giúp ngăn nhiều sai lệch. Nếu mã thô làm hàm gọi lại trả về đối tượng sai kiểu, lớp bọc vẫn phải chặn dữ liệu ấy khi nó sắp được ghi. Điều này không có nghĩa lớp bọc kiểm soát mọi tác dụng phụ của hàm gọi lại: hàm gọi lại có thể đã ghi log, sửa một đối tượng khác hoặc thực hiện một hành động bên ngoài trước khi kết quả bị từ chối.

Đừng nhầm ràng buộc kiểu với quyền sửa. Bọc một list không cho phép sửa bằng `checkedList` không làm nó hỗ trợ `add`. Một thao tác đúng kiểu vẫn có thể thất bại vì `UnsupportedOperationException`, chỉ số không hợp lệ, giới hạn của cấu trúc gốc hoặc quy tắc so sánh của nó. Khi một lời gọi vi phạm nhiều điều kiện, không xây dựng luồng điều khiển dựa trên giả định thứ tự ưu tiên giữa các ngoại lệ.

[Hợp đồng `List`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html) và [`Map.Entry`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html) giúp phân biệt thao tác cập nhật, thao tác tùy chọn và đối tượng entry gắn với map.

## 5. Chương trình 1: Collection, List và Set

Chương trình này dùng dữ liệu có thứ tự xác định để đầu ra dễ đối chiếu. `LinkedHashSet` được chọn để giữ thứ tự chèn; đây là đặc tính của cấu trúc gốc được chọn, không phải tính năng tạo thứ tự của `checkedSet`.

Các biến kiểu thô và `@SuppressWarnings` chỉ phục vụ thí nghiệm mô phỏng mã cũ. Chương trình vẫn dừng bằng `AssertionError` nếu một trường hợp dự kiến bị chặn lại được chấp nhận.

Tệp `CheckedViewsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.ListIterator;
import java.util.Set;

public class CheckedViewsDemo {
    private static void rejected(String label, Runnable action) {
        try {
            action.run();
        } catch (ClassCastException expected) {
            System.out.println(label + "=ClassCastException");
            return;
        }
        throw new AssertionError(label + " was accepted");
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("first"));
        List<String> checked = Collections.checkedList(source, String.class);
        List rawList = checked;
        rejected("list.add", () -> rawList.add(42));
        rejected("list.set", () -> rawList.set(0, 42));

        ListIterator rawIterator = checked.listIterator();
        rawIterator.next();
        rejected("iterator.set", () -> rawIterator.set(42));
        rejected("iterator.add", () -> rawIterator.add(42));

        List rawSubList = checked.subList(0, 1);
        rejected("subList.add", () -> rawSubList.add(42));
        checked.set(0, "updated");
        checked.add(null);
        source.add("owner");
        System.out.println("list=" + checked);
        System.out.println("listEquals=" +
                checked.equals(java.util.Arrays.asList("updated", null, "owner")));

        Collection<Number> numbers = Collections.checkedCollection(
                new ArrayList<>(), Number.class);
        numbers.add(7);
        numbers.add(2.5);
        Collection rawNumbers = numbers;
        rejected("collection.add", () -> rawNumbers.add("7"));
        System.out.println("numbers=" + numbers);
        System.out.println("genericCollectionEqualsList=" +
                numbers.equals(List.of(7, 2.5)));

        Set<String> tags = Collections.checkedSet(
                new LinkedHashSet<>(), String.class);
        System.out.println("set.addFirst=" + tags.add("java"));
        System.out.println("set.addDuplicate=" + tags.add("java"));
        Set rawSet = tags;
        rejected("set.add", () -> rawSet.add(42));
        System.out.println("set=" + tags);
        System.out.println("setEquals=" + tags.equals(Set.of("java")));

        Collection<CharSequence> texts = Collections.checkedCollection(
                new ArrayList<>(), CharSequence.class);
        StringBuilder builder = new StringBuilder("a");
        texts.add(builder);
        builder.append("b");
        System.out.println("elementCanChange=" + texts);
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp, bằng JDK hỗ trợ Java 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 CheckedViewsDemo.java
java CheckedViewsDemo
```

Đầu ra:

```text
list.add=ClassCastException
list.set=ClassCastException
iterator.set=ClassCastException
iterator.add=ClassCastException
subList.add=ClassCastException
list=[updated, null, owner]
listEquals=true
collection.add=ClassCastException
numbers=[7, 2.5]
genericCollectionEqualsList=false
set.addFirst=true
set.addDuplicate=false
set.add=ClassCastException
set=[java]
setEquals=true
elementCanChange=[ab]
```

### 5.1. Đọc kết quả theo từng lớp trách nhiệm

Năm lỗi đầu tiên cùng bảo vệ một `List<String>`: lời gọi qua biến thô, qua iterator và qua danh sách con đều không đưa số vào dữ liệu gốc. Sau các lần bị chặn, list vẫn cho phép sửa hợp lệ. Việc `source.add("owner")` xuất hiện trong `checked` cho thấy hai tham chiếu cùng quan sát một dữ liệu sống.

`null` được thêm thành công vì `ArrayList` cho phép nó. Đây không phải một lỗ hổng kiểm tra kiểu: thiếu giá trị và sai kiểu là hai điều kiện cần được định nghĩa riêng.

`numbers` nhận cả `Integer` và `Double` nhờ token `Number.class`, rồi từ chối chuỗi `"7"`. Kết quả `genericCollectionEqualsList=false` minh họa sự khác biệt giữa lớp bọc tổng quát và một list có hợp đồng so sánh theo nội dung.

Set vẫn trả về `false` khi thêm lại `"java"`. Ràng buộc không trùng lặp của set vẫn hoạt động bên cạnh kiểm tra kiểu.

Cuối cùng, `StringBuilder` được chấp nhận qua token giao diện `CharSequence.class`. Sau khi đối tượng ấy bị sửa từ `"a"` thành `"ab"`, nội dung nhìn thấy qua collection cũng thay đổi. Lớp bọc kiểm tra loại đối tượng được thêm vào; nó không đóng băng trạng thái của đối tượng đó.

## 6. Chương trình 2: Bảo vệ cả khóa, giá trị và Entry của Map

Một map tên bài học và số lượng ví dụ cần khóa `String`, giá trị `Integer`. Chỉ kiểm tra `put` trực tiếp sẽ chưa đủ nếu bên nhận còn lấy được entry và gọi `setValue` hoặc sử dụng hàm gọi lại để thay giá trị.

Tệp `CheckedMapDemo.java`:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public class CheckedMapDemo {
    private static void rejected(String label, Runnable action) {
        try {
            action.run();
        } catch (ClassCastException expected) {
            System.out.println(label + "=ClassCastException");
            return;
        }
        throw new AssertionError(label + " was accepted");
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) {
        Map<String, Integer> source = new LinkedHashMap<>();
        Map<String, Integer> checked = Collections.checkedMap(
                source, String.class, Integer.class);
        checked.put("a", 1);
        Map rawMap = checked;

        rejected("put.key", () -> rawMap.put(42, 2));
        rejected("put.value", () -> rawMap.put("b", "two"));
        rejected("replace.value", () -> rawMap.replace("a", "two"));

        Map.Entry rawEntry = checked.entrySet().iterator().next();
        rejected("entry.setValue", () -> rawEntry.setValue("two"));
        rawEntry.setValue(3);
        System.out.println("afterEntry=" + checked);

        rejected("compute.result", () ->
                rawMap.compute("b", (key, value) -> "two"));
        rejected("merge.result", () ->
                rawMap.merge("a", 4, (oldValue, newValue) -> "two"));
        rejected("replaceAll.result", () ->
                rawMap.replaceAll((key, value) -> "two"));
        System.out.println("afterRejected=" + checked);
        System.out.println("missingBadKey=" + checked.get(42));

        checked.compute("a", (key, value) -> value + 1);
        checked.merge("a", 4, Integer::sum);
        checked.put(null, null);
        source.put("owner", 9);
        System.out.println("finalMap=" + checked);

        checked.values().remove(9);
        System.out.println("afterViewRemoval=" + source);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CheckedMapDemo.java
java CheckedMapDemo
```

Đầu ra:

```text
put.key=ClassCastException
put.value=ClassCastException
replace.value=ClassCastException
entry.setValue=ClassCastException
afterEntry={a=3}
compute.result=ClassCastException
merge.result=ClassCastException
replaceAll.result=ClassCastException
afterRejected={a=3}
missingBadKey=null
finalMap={a=8, null=null, owner=9}
afterViewRemoval={a=8, null=null}
```

### 6.1. Vì sao kết quả có a=8?

Ánh xạ ban đầu là `a=1`. Lời gọi `rawEntry.setValue(3)` hợp lệ nên dữ liệu trở thành `a=3`. Các hàm gọi lại cố trả về chuỗi đều bị chặn; trong những trường hợp cụ thể này, map không nhận thêm hay thay bằng giá trị sai.

Sau đó `compute` tăng `3` thành `4`, và `merge` cộng thêm `4` để được `8`. Kiểm tra kiểu không làm thay đổi ý nghĩa tính toán của hàm gọi lại hợp lệ.

`checked.put(null, null)` được phép vì `LinkedHashMap` gốc cho phép cả hai. `source.put("owner", 9)` xuất hiện ngay trong khung nhìn, chứng minh đây không phải bản chụp dữ liệu. Khi xóa `9` qua `checked.values()`, ánh xạ tương ứng cũng biến mất khỏi map gốc.

### 6.2. Entry phải được lấy từ đúng map

`rawEntry` trong thí nghiệm được lấy qua `checked.entrySet()`. Nó vẫn bảo vệ giá trị khi `setValue` được gọi qua kiểu thô.

Nếu ứng dụng giữ một entry lấy trực tiếp từ `source.entrySet()` rồi trao entry ấy ra ngoài, entry đó không tự được thay thế bằng entry của lớp bọc. Nó là một đường truy cập khác tới dữ liệu gốc. Bọc map sau khi đã làm lộ tham chiếu không thu hồi được những tham chiếu đã phát ra.

Chỉ sử dụng entry trong điều kiện mà hợp đồng `Map.Entry` cho phép. Không giữ một entry qua các lần sửa cấu trúc map rồi mặc nhiên cho rằng nó tiếp tục là một “cửa cập nhật” hợp lệ mãi mãi.

### 6.3. Truy vấn sai kiểu không đồng nghĩa với ghi sai kiểu

`checked.get(42)` biên dịch được vì tham số của `Map.get` là `Object`. Trong thí nghiệm với `LinkedHashMap`, nó trả về `null` vì không có khóa ấy. Không có ánh xạ sai kiểu nào được tạo ra.

Không suy ra mọi checked map đều phải ném `ClassCastException` cho mọi truy vấn sai kiểu, hoặc mọi cấu trúc gốc đều phải trả `null`. Hợp đồng truy vấn và giới hạn kiểu của cấu trúc gốc vẫn có vai trò. Ranh giới đang bảo vệ là dữ liệu được lưu, không phải một cơ chế cưỡng chế chữ ký `get(K)` lúc chạy.

[API `Map`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) quy định riêng các thao tác truy vấn, view và cập nhật bằng hàm gọi lại; cần đọc cùng chính sách của map gốc.

## 7. Hai điều kiện để giữ dữ liệu đúng kiểu lâu dài

Muốn kết luận “collection không chứa phần tử sai kiểu”, chỉ có lớp bọc là chưa đủ. Cần duy trì cả hai điều kiện:

1. Dữ liệu đã đúng kiểu trước khi tạo khung nhìn.
2. Mọi đường có thể đưa dữ liệu mới hoặc giá trị thay thế vào cấu trúc đều đi qua khung nhìn được kiểm tra phù hợp.

Với map, điều kiện thứ nhất áp dụng cho cả khóa và giá trị. Điều kiện thứ hai bao gồm những collection view và entry được lấy từ map bọc.

### 7.1. Tạo lớp bọc không phải là kiểm tra toàn bộ dữ liệu cũ

Một danh sách đã chứa số nhưng bị khai báo/ép thành `List<String>` không tự được làm sạch khi truyền vào `checkedList`. Lớp bọc được tạo thành công không phải giấy xác nhận từng phần tử hiện hữu đã qua kiểm tra.

Lúc đọc, việc dùng kết quả như `String` có thể làm lộ dữ liệu sai. Cần phân biệt nơi kiểm tra khi ghi của lớp bọc với phép ép kiểu mà trình biên dịch chèn ở nơi đọc. Một giá trị đọc ra như `Object` có thể chưa gặp lỗi; yêu cầu dùng nó như `String` mới làm `ClassCastException` xuất hiện.

Vì thế, “đã bọc mà vẫn lỗi ở `get`” chưa chứng minh lớp bọc không hoạt động. Có thể dữ liệu sai đã có từ trước, hoặc đi vào qua một tham chiếu khác.

### 7.2. Một tham chiếu đến cấu trúc gốc vẫn có thể đi vòng

Nếu cùng một `ArrayList` có hai tham chiếu, trong đó một tham chiếu trỏ tới lớp bọc và một tham chiếu trỏ thẳng tới list gốc, lời gọi qua list gốc không đi qua lớp bọc. Kiểu khai báo của tham chiếu gốc cũng có thể bị mã thô làm suy yếu.

Một thiết kế ranh giới rõ hơn là tạo cấu trúc gốc rỗng ngay trong thành phần sở hữu, bọc nó rồi chỉ cung cấp tham chiếu đã bọc. Đối tượng gốc không bị “khóa” bằng một tính năng JVM đặc biệt; cách thiết kế đang giảm số đường truy cập có thể bỏ qua kiểm tra.

Việc sửa dữ liệu hợp lệ qua tham chiếu gốc trong hai chương trình đầu chỉ nhằm chứng minh khung nhìn chia sẻ dữ liệu. Trong một tích hợp cần bảo đảm kiểu, chính đường ghi ngoài lớp bọc đó phải được quản lý, không thể xem như đương nhiên an toàn.

### 7.3. Kiểm tra kiểu bên ngoài không xác nhận kiểu lồng bên trong

`List.class` có thể giúp xác nhận một phần tử là `List`. Nó không cung cấp thông tin “mọi phần tử trong list ấy đều là `String`”. Java không có biểu thức lớp `List<String>.class`.

Đây là hệ quả cần hiểu khi làm việc với xóa kiểu (type erasure): nhiều tham số kiểu chỉ phục vụ kiểm tra khi biên dịch. Một `List<Integer>` và một `List<String>` đều có thể được biểu diễn bằng đối tượng list lúc chạy; một token `Class` cho `List` không mang toàn bộ cấu trúc kiểu lồng.

Ví dụ, nếu bọc một danh sách ngoài với `List.class`, đưa `ArrayList<Integer>` vào vẫn qua được kiểm tra lớp bên ngoài. Một phép ép kiểu tiếp theo không biến số trong danh sách con thành chuỗi. Khi đọc số ấy như `String`, lỗi lại xuất hiện.

Muốn bảo vệ cấu trúc lồng, cần xác thực từng tầng theo cấu trúc dữ liệu thực tế, kiểm soát các tham chiếu tới từng collection con hoặc chuyển dữ liệu sang mô hình miền có ràng buộc rõ ràng. Ép một `Class` thô thành `Class<List<String>>` bằng unchecked cast không bổ sung năng lực kiểm tra sâu mà token không có.

[Tài liệu về xóa kiểu của Java](https://docs.oracle.com/javase/tutorial/java/generics/erasure.html) giải thích vì sao tham số kiểu không tự được giữ như một token lớp đầy đủ để lớp bọc sử dụng.

## 8. Chương trình 3: Dữ liệu cũ, đường đi vòng và kiểu lồng

Chương trình sau cố tình vi phạm giả định của generics ở các điểm được cô lập trong `main`. Đây là thí nghiệm chẩn đoán các giới hạn, không phải mẫu để tiếp nhận dữ liệu không tin cậy trong mã ứng dụng.

Tệp `CheckedLimitationsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CheckedLimitationsDemo {
    private static void rejected(String label, Runnable action) {
        try {
            action.run();
        } catch (ClassCastException expected) {
            System.out.println(label + "=ClassCastException");
            return;
        }
        throw new AssertionError(label + " was accepted");
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) {
        List dirty = new ArrayList();
        dirty.add(42);
        List<String> claimedStrings = dirty;
        List<String> wrappedDirty =
                Collections.checkedList(claimedStrings, String.class);
        Object oldValue = ((List) wrappedDirty).get(0);
        System.out.println("existingType=" + oldValue.getClass().getSimpleName());
        rejected("existingTypedRead", () -> wrappedDirty.get(0).length());

        List<String> source = new ArrayList<>();
        List<String> checked = Collections.checkedList(source, String.class);
        List rawSource = source;
        rawSource.add(99);
        System.out.println("bypassedSize=" + checked.size());
        rejected("bypassedTypedRead", () -> checked.get(0).length());

        List<List> lists = Collections.checkedList(
                new ArrayList<>(), List.class);
        lists.add(new ArrayList<>(List.of(123)));
        System.out.println("nestedType=" +
                lists.get(0).get(0).getClass().getSimpleName());
        List<String> assumedInner = lists.get(0);
        rejected("nestedTypedRead", () -> assumedInner.get(0).length());

        List<Integer> goodIntegers = Collections.checkedList(
                new ArrayList<>(), Integer.class);
        goodIntegers.add(7);
        System.out.println("boxedToken=" + goodIntegers);

        List<Integer> primitiveToken = Collections.checkedList(
                new ArrayList<>(), int.class);
        rejected("primitiveToken", () -> primitiveToken.add(7));

        List<String> partial = Collections.checkedList(
                new ArrayList<>(List.of("a", "b")), String.class);
        List rawPartial = partial;
        rejected("replaceAll.partial", () ->
                rawPartial.replaceAll(value -> value.equals("a") ? "A" : 42));
        System.out.println("afterPartial=" + partial);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CheckedLimitationsDemo.java
java CheckedLimitationsDemo
```

Đầu ra:

```text
existingType=Integer
existingTypedRead=ClassCastException
bypassedSize=1
bypassedTypedRead=ClassCastException
nestedType=Integer
nestedTypedRead=ClassCastException
boxedToken=[7]
primitiveToken=ClassCastException
replaceAll.partial=ClassCastException
afterPartial=[A, b]
```

### 8.1. Ba nguồn lỗi khác nhau có thể cùng lộ khi đọc

`existingType=Integer` xuất hiện vì danh sách đã sai từ trước khi bọc. Tạo lớp bọc không quét lại và từ chối dữ liệu ấy.

`bypassedSize=1` xuất hiện vì thao tác ghi đi thẳng vào `source`. Lớp bọc nhìn thấy phần tử mới vì nó chia sẻ dữ liệu, nhưng đã không có cơ hội kiểm tra lúc ghi.

`nestedType=Integer` xuất hiện vì token `List.class` chỉ kiểm tra list con là một list. Các phần tử bên trong list con chưa có ràng buộc chuỗi ở thời điểm thêm list đó vào danh sách ngoài.

Cả ba trường hợp đều có thể dẫn đến lỗi ở một biểu thức đọc chuỗi. Cách khắc phục phụ thuộc vào nguồn gốc: xác thực dữ liệu ban đầu, thu hẹp đường ghi ngoài lớp bọc hoặc kiểm tra cấu trúc lồng. Thêm một lớp ép kiểu để hết cảnh báo không giải quyết được bất kỳ nguồn lỗi nào trong ba trường hợp.

### 8.2. Token và tự động đóng hộp không phải cùng một cơ chế

`boxedToken=[7]` cho thấy `Integer.class` phù hợp với đối tượng số mà list thực sự giữ. `primitiveToken=ClassCastException` cho thấy đối số `int.class` không tự được đổi thành token của lớp bao dù lời gọi `add(7)` tự đóng hộp giá trị.

Sự phân biệt này hữu ích khi một hàm tiện ích nhận `Class<E>` từ thành phần khác. Cần xác định hợp đồng token đầu vào; đừng chỉ kiểm tra rằng biến token khác `null` rồi mặc nhiên coi mọi lớp nguyên thủy là tương đương lớp bao.

### 8.3. Kiểm tra kiểu không bao hàm hoàn tác

Trong phần cuối, `replaceAll` biến `"a"` thành `"A"` đúng kiểu. Khi hàm gọi lại tới `"b"`, nó trả về số `42` và bị từ chối. Kết quả `[A, b]` giữ lại phần thay đổi đã thực hiện trước lỗi.

Đây là một minh chứng cụ thể với `ArrayList` được bọc và cách triển khai đã chạy. Bảo đảm “không lưu giá trị sai kiểu qua lớp bọc” không kéo theo “mọi thao tác nhiều phần tử đều hoàn tác nếu có ngoại lệ”.

Trong mã nguồn OpenJDK 17, các đường `addAll` và `putAll` chuẩn bị/kiểm tra dữ liệu đầu vào trước bước ghi; cách đó giúp tránh việc vừa thêm dần vừa mới phát hiện kiểu sai trong lô. Đây là chi tiết triển khai cần phân biệt với một giao dịch tổng quát: giới hạn của cấu trúc gốc, ngoại lệ khác, hàm gọi lại và truy cập đồng thời không vì thế có cơ chế hoàn tác chung.

[Mã nguồn `Collections` của OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Collections.java) thể hiện rõ bước kiểm tra đầu vào và việc kiểm tra kết quả hàm gọi lại. Không phụ thuộc vào tên lớp lớp bọc nội bộ hoặc thông điệp ngoại lệ cụ thể để viết mã ứng dụng.

## 9. Kiểm tra dữ liệu đầu vào và kiểm tra khi ghi là hai giai đoạn

Giả sử cần nhận một danh sách từ một thư viện cũ rồi cho các thành phần khác tiếp tục cập nhật. Có hai câu hỏi khác nhau:

- Các phần tử đang có đã đúng dạng dữ liệu mong muốn chưa?
- Những cập nhật tiếp theo có đi qua một ranh giới kiểm tra được kiểm soát không?

Chỉ gọi `checkedList` trên danh sách vừa nhận mới trả lời được một phần câu hỏi thứ hai. Một quy trình dễ kiểm soát hơn là:

1. Nhận đầu vào qua kiểu có thể mô tả sự chưa biết, chẳng hạn `Collection<?>`, thay vì giả vờ nó đã là `Collection<String>`.
2. Duyệt và kiểm tra từng phần tử theo kiểu, chính sách `null` và ràng buộc nghiệp vụ đã xác định.
3. Xây dựng cấu trúc mới do thành phần hiện tại sở hữu; việc kiểm tra và tạo kết quả diễn ra trước khi công bố kết quả ấy ra ngoài.
4. Tạo khung nhìn có kiểm tra kiểu phù hợp nếu còn cần cho phép cập nhật từ các ranh giới dễ mất thông tin kiểu.
5. Không trao thêm cấu trúc gốc, iterator hoặc entry có khả năng ghi ngoài ranh giới đã chọn.

Nếu gặp một giá trị sai, quyết định từ chối toàn bộ đầu vào hay báo lỗi từng mục phải thuộc hợp đồng của ứng dụng. Lớp bọc không tự đưa ra chính sách chuyển `"42"` thành số, bỏ các phần tử sai hoặc thay `null` bằng giá trị mặc định.

Một bản sao collection thông thường như `new ArrayList<>(input)` chỉ sao chép các tham chiếu phần tử. Nó không tự trở thành quá trình xác minh sâu toàn bộ cấu trúc kiểu hoặc bản sao sâu trạng thái các đối tượng. Nếu đầu vào có thể thay đổi đồng thời, quy trình nhận dữ liệu còn cần một chiến lược nhất quán phù hợp; lớp bọc không tạo ảnh chụp nguyên tử của dữ liệu đang bị sửa.

### 9.1. Sửa chỗ dùng raw type vẫn là hướng chính

Nếu toàn bộ mã nguồn nằm trong quyền kiểm soát và có thể khai báo generics đúng, hãy sửa chữ ký kiểu và giải quyết cảnh báo không được kiểm tra tại nguyên nhân. Đặt khung nhìn có kiểm tra kiểu ở một ranh giới cần phòng vệ hoặc dùng tạm thời để chẩn đoán có giá trị; rải unchecked cast kèm `@SuppressWarnings` rồi trông chờ lớp bọc xử lý mọi hậu quả sẽ làm mất nhiều thông tin tĩnh hữu ích.

Một khung nhìn có kiểm tra kiểu cũng không chứng minh một hàm nhận collection sử dụng đúng mọi quy tắc nghiệp vụ. Ví dụ, danh sách `String` vẫn có thể nhận chuỗi rỗng, tên trùng hoặc một tên không tồn tại. Các quy tắc ấy không được biểu diễn bởi `String.class`.

## 10. Phân biệt với các loại lớp bọc và bản sao khác

| Cách tạo/cung cấp dữ liệu | Ràng buộc chính | Có giữ liên hệ dữ liệu với cấu trúc gốc không? | Có tự kiểm tra sâu dữ liệu lồng không? |
| --- | --- | --- | --- |
| `checkedList` trên list cho phép sửa | Kiểu của phần tử ghi qua view | Có | Không |
| `unmodifiableList` | Không cho phép sửa cấu trúc qua view | Có | Không |
| `synchronizedList` | Đồng bộ truy cập theo hợp đồng lớp bọc | Có | Không |
| `new ArrayList<>(source)` | Tạo một list khác chứa các tham chiếu phần tử | Không chia sẻ cấu trúc list | Không |
| `List.copyOf(source)` | Tạo kết quả không cho sửa, cấm phần tử `null` | Không phản ánh các lần sửa cấu trúc nguồn về sau | Không |

Bảng chỉ so sánh trách nhiệm trực tiếp liên quan tới bài. Không suy ra một cơ chế thay thế được các cơ chế còn lại.

Ví dụ, một API cho thư viện cũ bổ sung tên có thể cần khung nhìn có kiểm tra kiểu. Một API chỉ để đọc cần xem xét quyền sửa dữ liệu. Một API chia sẻ giữa nhiều luồng cần xem xét cách đồng bộ và tính nguyên tử của chuỗi thao tác. Cả ba yêu cầu có thể xuất hiện trong cùng hệ thống nhưng cần được thiết kế riêng.

Nếu kết hợp nhiều lớp bọc, phải xác định đối tượng nào được trao ra ngoài và những tham chiếu khác còn tồn tại. Một lớp `unmodifiable` bên ngoài khung nhìn có kiểm tra kiểu sẽ chặn các lần sửa qua lớp ngoài; nó không tạo ra cơ hội để bên nhận ghi dữ liệu hợp lệ. Một lớp checked bên ngoài list không cho phép sửa cũng không trao thêm quyền sửa mà list gốc thiếu.

Không cần dựa vào tên lớp thực thi nội bộ, thứ tự của các lớp bọc trong thông điệp lỗi hay kiểm tra `getClass().getName()` để mô tả hợp đồng API công khai.

### 10.1. Chú ý với phần tử của Set và khóa của Map

Một phần tử có thể vẫn thuộc đúng lớp nhưng bị sửa các trường ảnh hưởng đến `equals` hoặc `hashCode`. Khung nhìn có kiểm tra kiểu không ngăn việc đó. Nếu đối tượng đang là phần tử của hash set hoặc khóa của hash map, việc sửa như vậy có thể làm hỏng giả định tra cứu.

Do đó, “mọi khóa đều thuộc lớp `CustomerKey`” và “các khóa có trạng thái phù hợp với hợp đồng map trong suốt thời gian lưu” là hai bất biến khác nhau. Đối tượng mô tả kiểu chỉ giúp với loại đối tượng; thiết kế khóa và quyền sửa trạng thái của khóa vẫn thuộc về ứng dụng. [Hợp đồng `Set`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html) và [`Map`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) cảnh báo trực tiếp về các đối tượng có trạng thái thay đổi ảnh hưởng đến phép so sánh.

## 11. Chi phí và cách dùng để truy tìm lỗi

Với cấu trúc gốc rỗng do ứng dụng sở hữu, có thể tạo lớp bọc ngay khi khởi tạo, rồi đưa lớp bọc qua ranh giới thư viện. Mỗi lần có dữ liệu cần ghi, ứng dụng trả thêm chi phí cho việc kiểm tra tương thích kiểu và chuyển tiếp lời gọi. Lớp bọc không thay đổi nền tảng lưu trữ để biến một thuật toán tuyến tính thành truy cập hằng số.

Đừng suy luận các thao tác lô luôn chỉ cần bộ nhớ phụ hằng số. Như quan sát ở OpenJDK 17, việc chuẩn bị bản dữ liệu đầu vào đã kiểm tra cho `addAll` hoặc `putAll` có thể cần bộ nhớ phụ theo số phần tử đầu vào. Chi phí thật cần xét theo thao tác đang dùng và cấu trúc gốc; không có một con số tăng thời gian cố định đúng cho mọi khung nhìn có kiểm tra kiểu.

Một quy trình chẩn đoán hữu ích khi đang gặp `ClassCastException` ở nơi đọc:

1. Xác định collection/map chứa dữ liệu sai và loại phần tử, khóa hoặc giá trị mong muốn.
2. Kiểm tra xem dữ liệu đã sai trước khi lớp bọc có hiệu lực hay chưa.
3. Tạo khung nhìn có kiểm tra kiểu tại điểm sở hữu hoặc điểm trao collection cho thành phần nghi ngờ.
4. Đảm bảo lần tái hiện thực sự sử dụng lớp bọc; kiểm tra cả tham chiếu gốc và view/entry từng bị phát ra.
5. Tái hiện và đọc dấu vết ngăn xếp của lần ghi bị chặn.
6. Sửa chữ ký generics hoặc nơi tạo dữ liệu sai, rồi giữ hay bỏ lớp bọc tùy vai trò phòng vệ của ranh giới.

Bắt `ClassCastException` rồi tiếp tục im lặng thường chỉ che mất dữ liệu không hợp lệ. Nếu ứng dụng cần chấp nhận một tập đầu vào hỗn hợp, hãy mô tả kiểu hỗn hợp một cách có chủ ý, chẳng hạn mô hình miền hoặc quy trình chuyển đổi rõ ràng, thay vì gắn nhãn sai `List<String>`.

## 12. Tự thực hành và kiểm tra hiểu biết

### Bài 1: Đổi đối tượng mô tả kiểu

Trong chương trình thứ nhất, thay collection số bằng một collection được kiểm tra với `Integer.class`, rồi thử thêm `7`, `7L`, `2.5` và `"7"`.

**Điểm cần giải thích:** số nguyên `7` được đóng hộp thành `Integer` nên phù hợp; `Long`, `Double` và `String` không trở thành `Integer` chỉ vì có thể diễn giải thành số. Nếu vẫn khai báo `Collection<Number>` nhưng truyền trực tiếp `Integer.class`, cần xem lại chữ ký `Class<E>`: mối quan hệ kiểu tại thời điểm biên dịch cũng phải nhất quán. Hãy khai báo `Collection<Integer>` cho thí nghiệm token này.

### Bài 2: Tìm đường truy cập không được bảo vệ

Một thành phần giữ `Map<String,Integer> source`, cung cấp `checkedMap(source, String.class, Integer.class)` cho thư viện A, nhưng cung cấp `source.entrySet()` cho thư viện B.

**Điểm cần giải thích:** entry lấy trực tiếp từ map gốc là một đường cập nhật khác. Nếu B dùng mã thô để sửa giá trị của entry, khung nhìn có kiểm tra kiểu mà A nhận không can thiệp vào lời gọi đó. Cần quản lý toàn bộ các tham chiếu có thể ghi, không chỉ biến map được trả về từ một phương thức.

### Bài 3: Tạo lớp bọc sau khi nhiễm kiểu

Dùng kiểu thô để thêm số vào `ArrayList`, gán nó thành `List<String>`, rồi mới gọi `checkedList`. So sánh việc đọc như `Object`, gọi `size` và dùng phần tử như `String`.

**Điểm cần giải thích:** `size` và đọc như `Object` không tự xác nhận mọi phần tử là chuỗi. Lỗi lộ ở phép sử dụng yêu cầu `String`. Cách sửa là kiểm tra dữ liệu ban đầu hoặc sửa đường ghi gốc, không phải bọc lại nhiều lần.

### Bài 4: Phân biệt kiểu ngoài và kiểu trong

Bọc danh sách ngoài bằng `List.class`, thêm một list chứa số, rồi đọc số đó như chuỗi qua một phép gán không được kiểm tra.

**Điểm cần giải thích:** danh sách con thỏa kiểm tra lớp ngoài. Đối tượng mô tả kiểu không mô tả tham số kiểu của danh sách con. Muốn đảm bảo sâu phải có một bước xác thực cấu trúc sâu và kiểm soát các lần sửa tiếp theo ở tầng đó.

### Bài 5: Kiểm tra tác động khi hàm gọi lại thất bại

Chạy lại đoạn `replaceAll` cuối chương trình thứ ba, rồi viết một quy trình chỉ công bố danh sách mới sau khi toàn bộ kết quả biến đổi đã được kiểm tra.

**Điểm cần giải thích:** lớp bọc giữ ràng buộc kiểu của từng giá trị được ghi; nó không cung cấp hoàn tác chung. Xây dựng kết quả riêng rồi công bố sau thành công là một lựa chọn thiết kế khác, cần định nghĩa cả quyền sửa và chia sẻ tham chiếu của các phần tử.

Khi có thể tự giải thích tại sao một lời ghi bị chặn, tại sao một lời ghi khác đi vòng được và tại sao dữ liệu lồng vẫn có thể sai, người học đã nắm được ranh giới mà bốn hàm `checked...` thực sự bảo vệ.
