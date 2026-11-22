# UnsupportedOperationException trên factory, wrapper và view

## 1. Vì sao gọi được phương thức nhưng chạy lại bị từ chối?

Đoạn mã sau biên dịch hợp lệ nhưng lỗi khi chạy:

```java
List<String> names = List.of("An", "Binh");
names.add("Chi"); // UnsupportedOperationException
```

Đây là đoạn minh họa bên trong một phương thức có import `java.util.List`.

Kiểu `List` công bố phương thức `add`, nhưng không hứa rằng mọi đối tượng thực hiện `List` đều hỗ trợ thao tác này. Một số phương thức sửa đổi trong Java Collections là **thao tác tùy chọn (optional operation)**. Nếu đối tượng không hỗ trợ thao tác được yêu cầu, nó có thể ném `UnsupportedOperationException`, viết tắt trong phần giải thích là UOE. [Tài liệu Collection của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

UOE là ngoại lệ lúc chạy, không phải lỗi biên dịch. Nó thường cho biết mã đang yêu cầu một khả năng sửa đổi mà đối tượng hiện tại không cung cấp. Muốn sửa đúng, cần xem collection được tạo từ đâu và chính xác thao tác nào bị từ chối.

Ba nguồn thường gặp:

- **Factory:** phương thức tạo/trả collection, chẳng hạn `List.of`, `Arrays.asList` hoặc `Stream.toList`.
- **Wrapper:** đối tượng bao một collection khác, chẳng hạn `Collections.unmodifiableList`.
- **View:** cách nhìn liên kết tới dữ liệu nguồn, chẳng hạn `subList`, `keySet` hoặc `values`.

Đây không phải ba nhãn loại trừ nhau. `Arrays.asList` là factory trả về view của mảng; `Collections.unmodifiableList` là wrapper đồng thời cung cấp một view không cho sửa qua wrapper.

## 2. Tách ba câu hỏi về khả năng thay đổi

Khi đọc hợp đồng của một collection, đừng chỉ hỏi “có mutable không?”. Hãy hỏi cụ thể:

1. Có được thêm/xóa phần tử, tức thay đổi kích thước không?
2. Có được thay thế phần tử hoặc giá trị đang có không?
3. Nếu dữ liệu nguồn hoặc đối tượng phần tử thay đổi từ nơi khác, collection có nhìn thấy thay đổi không?

| Cách tạo ví dụ | Thêm/xóa phần tử | Thay phần tử bằng `set` | Quan hệ với dữ liệu nguồn |
| --- | --- | --- | --- |
| `new ArrayList<>(source)` | Có | Có | Cấu trúc mới; các tham chiếu phần tử vẫn có thể dùng chung |
| `Arrays.asList(array)` | Không đổi kích thước | Có | View của chính mảng |
| `List.of(...)` | Không | Không | Không có danh sách nền có thể sửa qua một tham chiếu nguồn do người gọi giữ |
| `List.copyOf(source)` | Không | Không | Kết quả không phản ánh việc thêm/xóa/thay tham chiếu trong source sau khi sao chép |
| `Collections.unmodifiableList(source)` | Không qua wrapper | Không qua wrapper | View đọc từ source; source còn có thể đổi qua tham chiếu khác |
| `source.subList(from, to)` | Phụ thuộc khả năng của source | Phụ thuộc source | View của một đoạn trong source |

Bảng nói về thao tác trên cấu trúc và các tham chiếu được lưu. Nó không hứa rằng đối tượng phần tử đã trở thành bất biến sâu.

Một biến `final List<String>` cũng không thay đổi hợp đồng này: `final` ngăn gán biến sang danh sách khác, không tự ngăn sửa đối tượng danh sách.

## 3. Factory không phải lúc nào cũng trả cùng một loại collection

### 3.1. List.of, Set.of và Map.of không cho sửa qua API

Các factory `List.of`, `Set.of`, `Map.of` trả collection/map không cho phép sửa đổi qua API của kết quả. Với `List.of`, ngay cả `set(index, value)` cũng không được hỗ trợ. Không phải chỉ có thao tác tăng/giảm kích thước mới bị từ chối.

Ví dụ:

```java
List<String> values = List.of("A", "B");
values.set(0, "X"); // UnsupportedOperationException
```

Các factory này còn có quy tắc dữ liệu riêng: `List.of` không cho phần tử null; `Map.of` không cho khóa/giá trị null. Một lỗi ở bước tạo dữ liệu do null không phải UOE do sửa một collection đã tạo xong. [Tài liệu List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [tài liệu Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [tài liệu Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

Không suy ra kiểu triển khai nội bộ từ factory. Ép kiểu kết quả thành `ArrayList` không biến nó thành collection có thể sửa; phép ép kiểu còn có thể gây `ClassCastException`.

### 3.2. Arrays.asList: kích thước cố định nhưng vẫn thay được phần tử

`Arrays.asList(array)` trả một danh sách có kích thước cố định, được chống lưng bởi mảng đã cho. `set` được hỗ trợ và thay đổi được nhìn thấy từ cả mảng lẫn danh sách. Các thao tác làm đổi kích thước không được hỗ trợ. [Tài liệu Arrays.asList của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...))

Ví dụ minh họa:

```java
String[] array = {"A", "B"};
List<String> fixed = Arrays.asList(array);
fixed.set(0, "X");  // hợp lệ; array[0] cũng là "X"
fixed.add("C");     // UnsupportedOperationException
```

Cần import `java.util.List` và `java.util.Arrays`.

Vì không đổi số phần tử, một thao tác như thay thế mọi giá trị hoặc sắp xếp lại có thể thực hiện trên danh sách này bằng các khả năng được hỗ trợ. Không gắn nhãn “không sửa được gì” chỉ từ việc `add` thất bại.

Lưu ý kiểu: danh sách nội bộ mà `Arrays.asList` trả không phải `java.util.ArrayList` chỉ vì tên lớp nội bộ có thể chứa chữ `ArrayList`. Dựa vào hợp đồng phương thức thay vì tên lớp quan sát được trong debugger.

### 3.3. Stream.toList khác với Collectors.toList

Trên Java 17:

- `stream.toList()` trả danh sách không cho sửa; gọi phương thức sửa đổi sẽ ném UOE.
- `stream.collect(Collectors.toList())` không cam kết kiểu triển khai hoặc khả năng sửa đổi của danh sách kết quả.
- Khi cần rõ một `ArrayList` có thể sửa, dùng `collect(Collectors.toCollection(ArrayList::new))`.

Đừng sửa lỗi bằng cách dựa vào việc một phiên bản triển khai tình cờ trả `ArrayList`. [Tài liệu Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()), [tài liệu Collectors.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList())

Đây là sự khác biệt về hợp đồng kết quả, không phải việc các phương thức có tên gần giống nhau chắc chắn tương đương.

## 4. Wrapper không cho sửa không đồng nghĩa dữ liệu đã đóng băng

### 4.1. Unmodifiable wrapper chặn đường sửa qua wrapper

Ví dụ:

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> exposed = Collections.unmodifiableList(source);
```

Đoạn minh họa cần import `java.util.List`, `java.util.ArrayList` và `java.util.Collections`.

`exposed.add(...)`, `exposed.set(...)` và sửa thông qua iterator của `exposed` bị từ chối. Nhưng nếu còn giữ `source`, mã khác vẫn có thể thêm hoặc thay phần tử ở nguồn; các thay đổi được quan sát qua `exposed` vì wrapper là view đọc từ nguồn. [Tài liệu Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))

```text
source -----> ArrayList nền
                  ^
                  |
exposed ---> wrapper chỉ cho đọc qua đường này
```

Wrapper kiểm soát một đường truy cập, không tước quyền sửa của mọi tham chiếu khác tới đối tượng nền.

Không phải wrapper nào cũng có mục tiêu cấm sửa. Chẳng hạn một wrapper đồng bộ hóa có trách nhiệm khác. Đọc đúng hợp đồng của phương thức tạo wrapper, không suy ra từ riêng chữ “wrapper”.

### 4.2. Bản chụp cấu trúc khác view đang liên kết

Nếu cần kết quả không phản ánh các thay đổi về danh sách nguồn sau khi tạo, có thể dùng `List.copyOf(source)` khi chính sách null của nó phù hợp. API cho phép tái sử dụng một kết quả không thể sửa đổi thích hợp; không kiểm thử dựa vào việc tham chiếu chắc chắn khác hay giống nguồn.

Sự khác biệt có thể kiểm tra bằng hành vi:

```text
Tạo source = [A]
Tạo live = unmodifiableList(source)
Tạo snapshot = List.copyOf(source)
Thêm B vào source

live quan sát [A, B]
snapshot vẫn quan sát [A]
```

“Bản chụp” ở đây nói về các phần tử/tham chiếu được lưu trong collection. Nếu một phần tử là đối tượng có thể thay đổi, sửa bên trong đối tượng đó vẫn có thể được nhìn thấy qua cả hai.

### 4.3. Không thể sửa collection không có nghĩa phần tử bất biến sâu

Ví dụ minh họa:

```java
StringBuilder item = new StringBuilder("A");
List<StringBuilder> values = List.of(item);
item.append("!"); // values.get(0).toString() giờ là "A!"
```

Không có thao tác thêm/xóa/thay phần tử trong `values`. Đối tượng được tham chiếu vẫn tự thay đổi trạng thái. Vì vậy, một kiểm thử chỉ xác nhận `add` ném UOE không chứng minh toàn bộ dữ liệu bất biến.

Nếu hợp đồng yêu cầu dữ liệu không thể thay đổi sâu, phải thiết kế kiểu phần tử và chính sách sao chép phù hợp, rồi kiểm thử chúng riêng.

## 5. View có thể cho sửa một số hướng và từ chối hướng khác

### 5.1. subList kế thừa khả năng của danh sách nền

`subList(from, to)` là view của đoạn `[from, to)`, không phải bản sao độc lập. Với nguồn `ArrayList` có thể sửa, thao tác `set`, thêm hoặc xóa qua sublist được phản ánh ở nguồn. Nếu nguồn không cho sửa hoặc chỉ có kích thước cố định, giới hạn tương ứng cũng xuất hiện ở view. [Tài liệu List.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int))

Ví dụ trạng thái:

```text
base = [A, B, C, D]
part = base.subList(1, 3)   -> [B, C]
part.set(0, X)             -> base = [A, X, C, D]
part.remove(1)             -> base = [A, X, D]
part.add(Y)                -> base = [A, X, Y, D]
```

Vì thế không kết luận “view luôn ném UOE khi sửa”.

Một vấn đề khác: nếu sửa cấu trúc của danh sách nền trực tiếp ngoài đường sublist, ngữ nghĩa của view trở thành không xác định theo hợp đồng. Không thiết kế kiểm thử chung đòi mọi triển khai phải ném chính xác `ConcurrentModificationException` trong mọi tình huống đó. Đó cũng không phải UOE do thao tác bị cấm.

### 5.2. keySet, values và entrySet không hỗ trợ add như collection độc lập

Với một map có thể sửa, các view thông thường từ `keySet()`, `values()` và `entrySet()` cho phép xóa ánh xạ qua những thao tác xóa được hỗ trợ. Nhưng chúng không hỗ trợ `add`/`addAll` theo hợp đồng các view này. [Tài liệu Map collection views](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#keySet())

Lý do cần hiểu về mô hình:

- Thêm một khóa vào `keySet` không cung cấp giá trị cho ánh xạ mới.
- Thêm một giá trị vào `values` không cung cấp khóa.
- Ngay cả `entrySet` cũng không được mặc nhiên coi như một tập độc lập hỗ trợ thêm entry.

Hãy thêm bằng `map.put(key, value)` hoặc API map phù hợp. Khi xóa qua view, nhớ rằng dữ liệu nguồn cũng bị xóa; đây có thể là hành vi mong muốn hoặc một tác dụng phụ ngoài ý định.

Nếu map nền không cho sửa, các đường xóa qua view cũng bị chặn. Phải xác định cả loại view lẫn khả năng của map nền.

### 5.3. Entry có đường sửa giá trị riêng

Entry lấy từ iterator của `HashMap`/`LinkedHashMap` có thể hỗ trợ `setValue`, cập nhật map nền. Entry qua `Collections.unmodifiableMap(...).entrySet()` không cung cấp đường sửa vòng qua wrapper: `setValue` bị từ chối.

Do đó khi kiểm thử map không cho sửa, đừng chỉ kiểm tra `put`. Kiểm tra cả các đường sửa liên quan như xóa qua `keySet` hoặc cập nhật entry nếu hợp đồng của API công bố những đường truy cập đó.

## 6. Không dùng thao tác không có tác dụng để đoán khả năng sửa đổi

Những phép thử sau không phải kiểm tra khả năng sửa tổng quát đáng tin:

```java
collection.addAll(List.of());
collection.remove("gia-tri-khong-ton-tai");
collection.clear(); // khi collection đang rỗng
```

Đây là các biểu thức minh họa. Ở mức hợp đồng collection tổng quát, thao tác sửa không có tác dụng thực tế có thể được phép không làm gì hoặc ném UOE nếu API cụ thể không quy định mạnh hơn. Vì vậy, “không ném exception” trong một ca no-op không chứng minh thao tác sửa có tác dụng sẽ được hỗ trợ. [Tài liệu Collection về thao tác không có tác dụng](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

Một factory cụ thể có thể công bố bảo đảm chặt hơn, chẳng hạn các phương thức sửa của kết quả `List.of` bị từ chối. Hãy tôn trọng bảo đảm đó, nhưng không áp nó lên mọi đối tượng chỉ vì cùng kiểu `List`.

Để kiểm tra hành vi từ chối sửa, chọn thao tác chắc chắn cần thay đổi nội dung và có đối số hợp lệ: thêm một phần tử mới, xóa một phần tử đang có, hoặc `set` tại chỉ số hiện hữu bằng giá trị khác.

## 7. Chương trình Java 17+ chạy đầy đủ

Chương trình dưới đây kiểm tra cả thao tác bị từ chối và các thay đổi hợp lệ. Nó dùng các hàm tự kiểm tra, không phụ thuộc `-ea` hoặc thư viện bên ngoài.

Lưu thành `UnsupportedOperationsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class UnsupportedOperationsDemo {
    private static int passed;

    private static void checkEquals(String label, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        passed++;
    }

    private static void expectUoe(String label, Runnable action) {
        try {
            action.run();
        } catch (UnsupportedOperationException expected) {
            passed++;
            return;
        }
        throw new AssertionError(label + ": expected UnsupportedOperationException");
    }

    public static void main(String[] args) {
        List<String> factory = List.of("A", "B");
        expectUoe("List.of add", () -> factory.add("C"));
        expectUoe("List.of set", () -> factory.set(0, "X"));
        expectUoe("List.of remove", () -> factory.remove(0));
        Iterator<String> factoryIterator = factory.iterator();
        factoryIterator.next();
        expectUoe("List.of iterator remove", factoryIterator::remove);
        expectUoe("Set.of add", () -> Set.of("A", "B").add("C"));
        expectUoe("Map.of put", () -> Map.of("A", 1).put("B", 2));

        String[] array = {"A", "B"};
        List<String> fixed = Arrays.asList(array);
        fixed.set(0, "X");
        checkEquals("set updates backing array", "X", array[0]);
        array[1] = "Y";
        checkEquals("array update visible in list", List.of("X", "Y"), fixed);
        expectUoe("fixed size add", () -> fixed.add("Z"));
        expectUoe("fixed size remove existing", () -> fixed.remove(0));
        fixed.replaceAll(String::toLowerCase);
        checkEquals("replace values without resizing", List.of("x", "y"),
                Arrays.asList(array));

        List<String> backing = new ArrayList<>(List.of("A"));
        List<String> live = Collections.unmodifiableList(backing);
        expectUoe("wrapper add", () -> live.add("B"));
        expectUoe("wrapper set", () -> live.set(0, "X"));
        backing.add("B");
        checkEquals("wrapper observes backing add", List.of("A", "B"), live);
        List<String> snapshot = List.copyOf(backing);
        backing.set(0, "X");
        checkEquals("wrapper observes backing set", List.of("X", "B"), live);
        checkEquals("copyOf snapshot stays unchanged", List.of("A", "B"), snapshot);
        expectUoe("copyOf add", () -> snapshot.add("Z"));

        StringBuilder item = new StringBuilder("A");
        List<StringBuilder> shallow = List.of(item);
        item.append("!");
        checkEquals("unmodifiable is not deep immutability", "A!",
                shallow.get(0).toString());

        List<String> base = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> part = base.subList(1, 3);
        part.set(0, "X");
        checkEquals("subList set updates parent", List.of("A", "X", "C", "D"), base);
        part.remove(1);
        checkEquals("subList remove updates parent", List.of("A", "X", "D"), base);
        part.add("Y");
        checkEquals("subList add updates parent", List.of("A", "X", "Y", "D"), base);
        List<String> readOnlyPart = Collections.unmodifiableList(base).subList(1, 3);
        expectUoe("unmodifiable subList set", () -> readOnlyPart.set(0, "Z"));
        List<String> fixedPart = fixed.subList(0, 1);
        expectUoe("fixed size subList add", () -> fixedPart.add("Z"));
        fixedPart.set(0, "Z");
        checkEquals("fixed size subList still supports set", "Z", array[0]);

        Map<String, Integer> map = new LinkedHashMap<>();
        map.put("A", 1);
        map.put("B", 2);
        expectUoe("keySet add", () -> map.keySet().add("C"));
        expectUoe("values add", () -> map.values().add(3));
        expectUoe("entrySet add", () -> map.entrySet().add(Map.entry("C", 3)));
        map.keySet().remove("A");
        checkEquals("keySet removal updates map", false, map.containsKey("A"));
        Map.Entry<String, Integer> entry = map.entrySet().iterator().next();
        entry.setValue(20);
        checkEquals("entry setValue updates map", 20, map.get("B"));
        Map<String, Integer> readOnlyMap = Collections.unmodifiableMap(map);
        Map.Entry<String, Integer> readOnlyEntry =
                readOnlyMap.entrySet().iterator().next();
        expectUoe("unmodifiable map entry setValue", () -> readOnlyEntry.setValue(30));
        expectUoe("unmodifiable map keySet remove", () -> readOnlyMap.keySet().remove("B"));
        checkEquals("map unchanged by rejected view edits", Map.of("B", 20), map);

        List<String> streamResult = Stream.of("A", "B").toList();
        expectUoe("Stream.toList add", () -> streamResult.add("C"));
        List<String> collected = Stream.of("A", "B")
                .collect(Collectors.toCollection(ArrayList::new));
        collected.add("C");
        checkEquals("explicit mutable collector", List.of("A", "B", "C"), collected);
        List<String> editable = new ArrayList<>(factory);
        editable.add("C");
        checkEquals("mutable copy", List.of("A", "B", "C"), editable);
        checkEquals("factory source preserved", List.of("A", "B"), factory);

        System.out.println("fixed-size list = " + fixed);
        System.out.println("live wrapper = " + live);
        System.out.println("snapshot = " + snapshot);
        System.out.println("mutable subList parent = " + base);
        System.out.println("map after view operations = " + map);
        System.out.println("PASS: " + passed + " checks");
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 UnsupportedOperationsDemo.java
java UnsupportedOperationsDemo
```

Stdout khi tất cả kiểm tra đạt:

```text
fixed-size list = [Z, y]
live wrapper = [X, B]
snapshot = [A, B]
mutable subList parent = [A, X, Y, D]
map after view operations = {B=20}
PASS: 36 checks
```

`expectUoe` chỉ coi UOE là kết quả mong đợi; một lỗi khác vẫn làm chương trình thất bại. Những thao tác sửa bị kiểm tra dùng phần tử hoặc chỉ số hợp lệ, nên không vô tình kiểm tra lỗi đầu vào thay cho giới hạn sửa đổi.

Phần `replaceAll` dùng dữ liệu chữ cái ASCII để tập trung vào khả năng thay phần tử. Trong một bài toán chuẩn hóa ngôn ngữ thực tế, chính sách chữ hoa/thường và locale cần được xác định riêng.

## 8. Đọc stack trace và sửa đúng ý định của mã

### 8.1. Truy ngược đến chỗ tạo collection

Khi gặp UOE, hãy kiểm tra:

1. Dòng mã nào yêu cầu sửa: `add`, `remove`, `set`, `sort`, `replaceAll`, iterator hay thao tác trên entry?
2. Đối tượng được tạo bởi constructor, factory, wrapper hay view nào?
3. Hợp đồng của đối tượng có hỗ trợ thao tác đó không?
4. Ý định của chương trình là sửa nguồn, sửa một bản sao hay chỉ đọc?

Tên lớp nội bộ trong stack trace có thể giúp truy tìm nguồn gốc, nhưng không nên trở thành điều kiện rẽ nhánh trong mã ứng dụng hoặc assertion phụ thuộc tên triển khai.

### 8.2. Cần bản có thể sửa: tạo collection thuộc quyền sửa của mình

Ví dụ:

```java
List<String> editable = new ArrayList<>(readOnlyValues);
editable.add("new-value");
```

Đoạn minh họa tạo cấu trúc mới có thể sửa; nó không làm `readOnlyValues` đổi khả năng. Với map có thể dùng `new HashMap<>(sourceMap)` hoặc `new LinkedHashMap<>(sourceMap)` tùy bảo đảm cần giữ.

Phải kiểm tra hệ quả:

- Sửa bản sao không cập nhật cấu trúc nguồn.
- Các đối tượng phần tử có thể vẫn dùng chung tham chiếu.
- Việc chuyển loại collection có thể ảnh hưởng thứ tự, cách xử lý khóa hoặc khả năng chứa dữ liệu đặc biệt.

Không tự sao chép nếu ý định nghiệp vụ là cập nhật đúng nguồn. Trong trường hợp đó cần thay thiết kế/cách cung cấp dữ liệu hoặc gọi API được hỗ trợ trên đối tượng sở hữu nguồn.

### 8.3. Chỉ cần đọc: bỏ thao tác sửa ngoài hợp đồng

Một hàm được thiết kế chỉ đọc không nên sắp xếp trực tiếp tham số rồi mới xử lý, vì `sort` sửa danh sách. Nếu cần dãy đã sắp để tính toán nhưng phải giữ nguồn, sao chép rồi sắp bản sao.

Tương tự, không dùng `clear()` để “dọn dẹp” một collection mà hàm không sở hữu quyền sửa. Việc nhận một tham số kiểu `List` hoặc `Map` không tự cấp quyền thay đổi mọi đối tượng truyền vào.

### 8.4. Đừng bắt UOE rồi bỏ qua

Bỏ qua lỗi có thể khiến dữ liệu mới không bao giờ được thêm nhưng luồng xử lý vẫn báo thành công. Tự động thử sửa nguồn rồi, nếu thất bại, tạo bản sao cũng dễ làm hành vi phụ thuộc dữ liệu và triển khai.

Ngoài ra, các thao tác sửa hàng loạt tổng quát không mang một bảo đảm giao dịch tự động chỉ vì dùng Collections API. Nếu một thao tác gặp lỗi sau khi đã thực hiện một phần công việc, không được mặc nhiên coi toàn bộ trạng thái đã hoàn tác. Hãy dựa vào bảo đảm cụ thể, hoặc chuẩn bị kết quả riêng trước khi thay dữ liệu thuộc quyền sở hữu.

## 9. Kiểm thử giới hạn sửa đổi như một phần của hợp đồng

### 9.1. Kiểm thử cả thao tác bị cấm lẫn khả năng được hứa

Một danh sách chỉ có kích thước cố định cần được kiểm tra khác danh sách không cho sửa:

| Đối tượng | Thao tác nên xác nhận hợp lệ | Thao tác nên xác nhận bị từ chối |
| --- | --- | --- |
| `Arrays.asList` với mảng hai phần tử | `set` phản ánh vào mảng | Thêm phần tử hoặc xóa chỉ số đang có |
| `List.of` có dữ liệu | Đọc nội dung đúng | `add`, `set`, `remove` |
| Unmodifiable wrapper | Quan sát cập nhật hợp lệ từ backing collection | Sửa trực tiếp hoặc qua iterator/view của wrapper |
| `ArrayList.subList` | Sửa qua view cập nhật đúng nguồn | Không tự gắn kỳ vọng UOE cho mọi thao tác sửa |
| View từ map có thể sửa | Xóa một ánh xạ hiện hữu qua view | `add` vào các collection view thông thường |
| View từ unmodifiable map | Đọc ánh xạ đúng | Xóa qua view hoặc `Entry.setValue` |

Không chỉ kiểm tra “ném lỗi đúng” rồi quên kiểm tra dữ liệu còn lại. Với API cụ thể được kiểm tra, xác nhận các thao tác bị từ chối không làm thay đổi dữ liệu mà hợp đồng bảo vệ.

### 9.2. Khoanh vùng đúng lời gọi khi kiểm thử ngoại lệ

Trong môi trường đã có JUnit Jupiter, có thể viết một phương thức kiểm thử tương tự:

```java
List<String> values = List.of("A", "B");
assertThrows(UnsupportedOperationException.class, () -> values.add("C"));
assertEquals(List.of("A", "B"), values);
```

Đây là đoạn minh họa bên trong phương thức kiểm thử có các static import từ `org.junit.jupiter.api.Assertions`. Nó không phải chương trình độc lập.

Tạo dữ liệu trước assertion giúp phân biệt lỗi chuẩn bị dữ liệu với lỗi thao tác đang cần kiểm tra. Đừng dùng chỉ số không hợp lệ hoặc phần tử không hợp lệ rồi kỳ vọng một loại lỗi nhất định khi có nhiều vi phạm cùng lúc.

Với iterator, gọi `next()` trước `remove()` khi mục tiêu là kiểm tra giới hạn sửa. Nếu iterator chưa có phần tử vừa trả về, một đối tượng có thể báo lỗi trạng thái; đó là mục tiêu kiểm thử khác.

### 9.3. Kiểm tra view, snapshot và phần tử ở những ca riêng

Ba kiểm tra độc lập:

- Thử sửa qua API của kết quả: có bị từ chối theo hợp đồng không?
- Sửa nguồn qua đường hợp lệ: kết quả phải nhìn thấy hay giữ nguyên?
- Sửa trạng thái đối tượng phần tử: hợp đồng có yêu cầu độc lập sâu không?

Trộn cả ba rồi kết luận chung “immutable” dễ làm kiểm thử hứa nhiều hơn điều mã thực sự cung cấp.

## 10. Những kết luận dễ sai

| Kết luận | Điểm cần sửa |
| --- | --- |
| “Khai báo List thì chắc add được.” | Phương thức sửa có thể là thao tác tùy chọn trên đối tượng cụ thể. |
| “Arrays.asList không sửa được.” | Không đổi kích thước, nhưng thay phần tử được và phản ánh vào mảng. |
| “Unmodifiable wrapper là một bản sao.” | Nó thường đọc xuyên tới collection nền; cần phân biệt với bản chụp. |
| “Mọi view đều chỉ đọc.” | Sublist của nguồn có thể sửa và các map view hỗ trợ một số hướng xóa. |
| “Map sửa được thì keySet.add cũng được.” | Các collection view không tương đương collection độc lập hỗ trợ thêm. |
| “Không add được nghĩa là phần tử không đổi được.” | Đối tượng phần tử có thể vẫn thay đổi trạng thái. |
| “remove phần tử không có không ném lỗi, vậy remove được.” | Một thao tác không có tác dụng chưa chứng minh khả năng sửa. |
| “Collectors.toList luôn trả ArrayList có thể sửa.” | Hợp đồng không bảo đảm điều đó; chỉ định factory khi cần khả năng rõ ràng. |
| “Bắt UOE là đã xử lý thành công.” | Cần thực hiện được ý định hoặc báo thất bại rõ ràng, không nuốt lỗi. |

## 11. Tự kiểm tra và thực hành

### Câu 1: Vì sao set thành công trên Arrays.asList nhưng thất bại trên List.of?

`Arrays.asList` cung cấp view có kích thước cố định nhưng cho thay thế phần tử. `List.of` trả danh sách không cho sửa qua API, bao gồm cả `set`. Hai factory có hợp đồng khác nhau.

### Câu 2: Unmodifiable list nhìn thấy phần tử mới do nguồn được thêm từ bên ngoài có mâu thuẫn không?

Không. Wrapper chặn sửa qua đường wrapper, nhưng đọc từ nguồn đang liên kết. Đó không phải bảo đảm giữ nguyên bản chụp nội dung.

### Câu 3: Vì sao keySet.remove có thể đổi map nhưng keySet.add lại bị từ chối?

Xóa khóa xác định được ánh xạ cần xóa. Thêm một khóa không cung cấp đủ một cặp khóa/giá trị, và hợp đồng view không hỗ trợ thao tác thêm. Muốn thêm ánh xạ, dùng API map.

### Câu 4: Copy sang ArrayList có giải quyết bất biến sâu của phần tử không?

Không. Nó tạo cấu trúc danh sách có thể sửa và độc lập về cấu trúc, nhưng các tham chiếu phần tử vẫn có thể dùng chung. Cần chính sách riêng cho đối tượng phần tử.

### Bài thực hành

1. Thêm kiểm tra rằng xóa qua iterator của unmodifiable wrapper bị từ chối sau khi đã gọi `next()` hợp lệ.
2. Tạo `subList` từ `Arrays.asList`, xác nhận `set` đổi mảng gốc còn `add` bị từ chối.
3. So sánh `unmodifiableList(source)` với `unmodifiableList(new ArrayList<>(source))` khi nguồn thay đổi sau khi tạo kết quả.
4. Viết hàm trả danh sách đã sắp xếp mà giữ nguyên đầu vào, rồi kiểm thử với `ArrayList`, `List.of` và `Arrays.asList`.
5. Xác định rõ trong một API của bạn: người gọi được sửa kết quả không, kết quả là view hay bản chụp và các phần tử có thể thay đổi không?

Khi gặp UOE, hãy xác định thao tác bị yêu cầu, hợp đồng của đối tượng thực tế và quyền sửa dữ liệu mà chương trình cần. Cách sửa đúng xuất phát từ ba điều đó, thay vì thay tên factory hoặc bắt ngoại lệ theo phỏng đoán.
