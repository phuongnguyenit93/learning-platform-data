# Chọn cấu trúc Collection có thể sửa khi cần cập nhật dữ liệu

Java 9 bổ sung các phương thức factory như `List.of()`, `Set.of()` và `Map.of()` để tạo collection gọn, dễ đọc. Các collection này không cho phép thay đổi cấu trúc sau khi tạo. Khi chương trình cần thêm, xóa hoặc thay thế phần tử trong quá trình chạy, hãy chọn một collection có thể sửa, chẳng hạn `ArrayList`, `HashSet` hoặc `HashMap`.

Việc chọn đúng cấu trúc phụ thuộc vào cách dữ liệu được sử dụng: cần giữ thứ tự và cho phép phần tử trùng lặp thì dùng `List`; cần các phần tử duy nhất thì dùng `Set`; cần tra cứu giá trị theo khóa thì dùng `Map`. Sau đó chọn implementation có khả năng cập nhật phù hợp.

## 1. Phân biệt collection không sửa được và collection có thể sửa

Một collection *unmodifiable* không cho phép thay đổi cấu trúc thông qua các thao tác như `add`, `remove`, `clear` hoặc `put`. Gọi thao tác thay đổi không được hỗ trợ thường dẫn đến `UnsupportedOperationException`.

Ví dụ:

```java
List<String> languages = List.of("Java", "Kotlin");
languages.add("Scala");
```

Đoạn mã biên dịch được nhưng khi chạy, `add()` ném `UnsupportedOperationException`. `List.of()` tạo một list không sửa được; việc khai báo biến bằng `List<String>` không làm collection trở thành mutable.

Cũng cần phân biệt *unmodifiable* với bất biến sâu (deep immutability). Collection không cho phép thay đổi cấu trúc, nhưng nếu phần tử bên trong là đối tượng mutable thì trạng thái của các đối tượng đó vẫn có thể thay đổi thông qua tham chiếu khác. Tính không sửa được của collection không tự động làm mọi phần tử trở thành immutable.

## 2. Các factory method của Java 9

Java 9 cung cấp các phương thức factory tĩnh để tạo collection không sửa được:

| Factory method | Kiểu trả về | Đặc điểm chính |
| --- | --- | --- |
| `List.of(e1, e2, ...)` | `List<E>` | Giữ thứ tự, cho phép phần tử trùng lặp |
| `Set.of(e1, e2, ...)` | `Set<E>` | Không có phần tử trùng lặp |
| `Map.of(k1, v1, ...)` | `Map<K,V>` | Lưu cặp khóa và giá trị; khóa không được trùng |

Các factory này không chấp nhận `null`. `Set.of()` ném `IllegalArgumentException` nếu có phần tử trùng nhau; `Map.of()` ném `IllegalArgumentException` nếu có khóa trùng nhau. Các lỗi này xảy ra ngay khi tạo collection, giúp dữ liệu đầu vào không hợp lệ được phát hiện sớm.

`List.of()` vẫn cho phép phần tử trùng lặp, vì `List` biểu diễn một dãy có thứ tự. `Set.of()` yêu cầu mỗi phần tử duy nhất. `Map.of()` yêu cầu mỗi khóa duy nhất; giá trị có thể trùng nhau.

Với map có nhiều cặp khóa-giá trị, có thể dùng `Map.ofEntries(Map.entry(...), ...)`. Những phương thức factory này phù hợp với dữ liệu cố định, cấu hình nhỏ hoặc giá trị khởi tạo mà chương trình không cần sửa collection sau đó.

## 3. Tạo bản mutable từ collection factory

Nếu đã có dữ liệu ban đầu từ `List.of()`, `Set.of()` hoặc `Map.of()` nhưng cần cập nhật về sau, hãy tạo một collection mutable mới bằng constructor của implementation phù hợp:

```java
List<String> editableList = new ArrayList<>(List.of("Java", "Kotlin"));
Set<String> editableSet = new HashSet<>(Set.of("red", "blue"));
Map<String, Integer> editableMap = new HashMap<>(Map.of("A", 1, "B", 2));
```

Ba biến mới có thể được cập nhật:

```java
editableList.add("Scala");
editableList.set(0, "Java 9");

editableSet.add("green");
editableSet.remove("red");

editableMap.put("C", 3);
editableMap.remove("A");
```

Constructor nhận collection nguồn và sao chép các phần tử hoặc cặp ánh xạ vào collection mới. Việc thay đổi cấu trúc của collection mới không làm thay đổi cấu trúc collection nguồn. Đây là bản sao nông (shallow copy): nếu các phần tử là object mutable, collection mới và collection nguồn vẫn giữ tham chiếu đến cùng object đó.

Không cần tạo bản sao nếu dữ liệu thực sự chỉ đọc trong suốt vòng đời sử dụng. Giữ collection không sửa được giúp thể hiện rõ ý định và ngăn code khác vô tình thay đổi cấu trúc.

## 4. Chọn implementation theo cách cập nhật dữ liệu

**Khi cần một List có thể sửa:** `ArrayList` là lựa chọn mặc định phù hợp cho phần lớn trường hợp cần một dãy có thứ tự, cho phép phần tử trùng lặp, truy cập theo chỉ số và thêm phần tử ở cuối. Các thao tác thêm/xóa ở giữa có thể làm dịch chuyển nhiều phần tử.

**Khi cần một Set có thể sửa:**

- `HashSet` phù hợp khi chỉ cần bảo đảm phần tử duy nhất và tra cứu/thêm/xóa theo hash; không dựa vào thứ tự duyệt.
- `LinkedHashSet` giữ thứ tự chèn khi duyệt, hữu ích khi cần loại trùng nhưng vẫn giữ thứ tự dữ liệu đầu vào.
- `TreeSet` duy trì thứ tự sắp xếp theo thứ tự tự nhiên hoặc `Comparator`; việc duy trì thứ tự có chi phí so sánh.

**Khi cần một Map có thể sửa:**

- `HashMap` phù hợp cho tra cứu, thêm và xóa theo khóa; không cam kết thứ tự duyệt.
- `LinkedHashMap` giữ thứ tự chèn; cấu hình access-order còn hỗ trợ các trường hợp cần thứ tự truy cập.
- `TreeMap` duy trì thứ tự khóa theo thứ tự tự nhiên hoặc `Comparator`.

Chọn cấu trúc theo yêu cầu thật sự của dữ liệu. Không chọn `TreeSet` hoặc `TreeMap` chỉ vì muốn collection mutable; `HashSet` hoặc `HashMap` thường đơn giản hơn khi không cần sắp xếp. Tương tự, không dùng `List` nếu yêu cầu cốt lõi là duy nhất theo khóa.

## 5. Những API dễ nhầm về khả năng cập nhật

**`Arrays.asList()` tạo list có kích thước cố định.** Có thể dùng `set()` để thay thế phần tử, nhưng `add()` và `remove()` không được hỗ trợ. Vì vậy nó không phải lựa chọn cho một list cần tăng hoặc giảm số phần tử:

```java
List<String> values = java.util.Arrays.asList("A", "B");
values.set(0, "X"); // được hỗ trợ
// values.add("C"); // UnsupportedOperationException
```

Nếu cần list có thể thay đổi kích thước, có thể tạo `new ArrayList<>(Arrays.asList(...))` hoặc dùng `new ArrayList<>(List.of(...))`.

**`List.copyOf()` tạo list không sửa được.** API này có từ Java 10. Nó tạo một bản sao không sửa được của collection đầu vào; các thay đổi cấu trúc về sau ở collection nguồn không được phản ánh vào bản sao. Đây vẫn là bản sao nông đối với object phần tử.

**`Stream.toList()` trả về list không sửa được.** API này có từ Java 16. Nếu kết quả stream cần được cập nhật, hãy tạo collection mutable một cách tường minh:

```java
List<String> editable = names.stream()
        .filter(name -> !name.isBlank())
        .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
```

`Collectors.toList()` không cam kết implementation, khả năng sửa, khả năng tuần tự hóa hoặc tính thread-safe của list trả về. Khi khả năng cập nhật là yêu cầu của chương trình, `Collectors.toCollection(ArrayList::new)` thể hiện ý định rõ ràng hơn.

## 6. Ví dụ hoàn chỉnh

Chương trình sau minh họa một collection factory không sửa được và các bản sao mutable tương ứng. Tạo tệp `MutableCollections.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class MutableCollections {
    public static void main(String[] args) {
        List<String> fixedList = List.of("Java", "Kotlin");
        try {
            fixedList.add("Scala");
        } catch (UnsupportedOperationException ex) {
            System.out.println("List.of: unmodifiable");
        }

        List<String> editableList = new ArrayList<>(fixedList);
        editableList.set(0, "Java 9");
        editableList.add("Scala");
        System.out.println("List: " + editableList);

        Set<String> editableSet = new HashSet<>(Set.of("red", "blue"));
        editableSet.add("green");
        editableSet.remove("red");
        System.out.println("Set contains green: " + editableSet.contains("green"));
        System.out.println("Set size: " + editableSet.size());

        Map<String, Integer> editableMap = new HashMap<>(Map.of("A", 1, "B", 2));
        editableMap.put("C", 3);
        editableMap.remove("A");
        System.out.println("Map contains C: " + editableMap.containsKey("C"));
        System.out.println("Map size: " + editableMap.size());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 MutableCollections.java
java MutableCollections
```

Kết quả stdout:

```text
List.of: unmodifiable
List: [Java 9, Kotlin, Scala]
Set contains green: true
Set size: 2
Map contains C: true
Map size: 2
```

Ví dụ cho thấy `List.of()` không cho phép thêm phần tử, trong khi `ArrayList` được tạo từ list đó có thể thay thế và thêm phần tử. `HashSet` và `HashMap` cũng có thể nhận dữ liệu ban đầu từ factory method rồi tiếp tục thêm hoặc xóa dữ liệu.

## 7. Quy trình chọn collection khi thiết kế

1. Xác định dữ liệu có cần thay đổi cấu trúc sau khi khởi tạo hay chỉ đọc.
2. Nếu chỉ đọc, cân nhắc `List.of()`, `Set.of()`, `Map.of()` hoặc API tạo collection không sửa được phù hợp.
3. Nếu cần cập nhật, chọn đúng abstraction: `List`, `Set` hoặc `Map`.
4. Chọn implementation theo yêu cầu về thứ tự, duy nhất, sắp xếp và kiểu truy cập.
5. Nếu bắt đầu từ một collection không sửa được, tạo bản mutable bằng constructor tương ứng.
6. Kiểm tra các API trung gian như `Arrays.asList()`, `List.copyOf()` và `Stream.toList()` để không nhầm list có thể đọc với list có thể thay đổi.

Chọn collection mutable khi nghiệp vụ cần thêm, xóa hoặc thay thế dữ liệu. Chọn collection không sửa được khi dữ liệu cần giữ ổn định sau khởi tạo. Việc thể hiện đúng ý định ngay tại nơi tạo collection giúp tránh `UnsupportedOperationException` và làm cho trách nhiệm cập nhật dữ liệu rõ ràng hơn.