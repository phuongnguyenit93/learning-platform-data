# Quan hệ bằng nhau có thể áp dụng giữa các lớp triển khai cùng hợp đồng

## 1. Cùng một giao diện, khác lớp triển khai: có thể `equals()` trả về `true`?

Trong Java, `ArrayList` và `LinkedList` là hai lớp khác nhau nhưng đều triển khai giao diện `List`. Khi hai danh sách chứa **các phần tử bằng nhau ở cùng vị trí**, chúng được coi là bằng nhau theo hợp đồng của `List.equals(Object)`, cho dù kiểu triển khai và cấu trúc dữ liệu nội bộ khác nhau.

```java
List<String> a = new ArrayList<>(List.of("java", "core"));
List<String> b = new LinkedList<>(List.of("java", "core"));

System.out.println(a.equals(b)); // true
System.out.println(b.equals(a)); // true
```

Đây là fragment minh họa; cần import `java.util.List`, `ArrayList` và `LinkedList`. Ví dụ chạy hoàn chỉnh xuất hiện ở phần sau.

**Điểm cốt lõi:** bình đẳng của các collection tiêu chuẩn thường được định nghĩa bằng **hợp đồng của giao diện trừu tượng** (`List`, `Set`, `Map`) thay vì bắt buộc `a.getClass() == b.getClass()`. Ta có thể so sánh hai lớp triển khai khác nhau khi chúng cùng tuân thủ một quan hệ bằng nhau có ngữ nghĩa thống nhất.

Nhưng không được mở rộng phát biểu này thành “mọi `Collection` đều so sánh theo nội dung”: **`Collection` không áp đặt một thuật toán `equals()` chung cho mọi loại collection**. Sự tương thích xuyên lớp phụ thuộc hợp đồng cụ thể của kiểu đang so sánh và việc triển khai đúng hợp đồng đó.

## 2. Vì sao các lớp khác nhau vẫn có thể bằng nhau?

`Object.equals(Object)` chỉ quy định các tính chất của quan hệ bằng nhau (phản xạ, đối xứng, bắc cầu, nhất quán và không bằng `null`). Lớp tự quyết định tiêu chí bản sắc logic miễn tuân thủ các tính chất này.

Với các collection, nhiều tiêu chí được chuẩn hóa ở cấp giao diện:

| Loại | Điều kiện bằng nhau theo hợp đồng | Ví dụ khác triển khai có thể bằng nhau |
| --- | --- | --- |
| `List` | Đối tượng còn lại là `List`, cùng kích thước, từng vị trí tương ứng có phần tử bằng nhau | `ArrayList` và `LinkedList` |
| `Set` | Đối tượng còn lại là `Set`, cùng kích thước, chứa các phần tử tương đương theo ngữ nghĩa phần tử | `HashSet` và `LinkedHashSet` hoặc `TreeSet` với thứ tự phù hợp |
| `Map` | Đối tượng còn lại là `Map`, cùng tập ánh xạ khóa → giá trị; không phụ thuộc thứ tự duyệt | `HashMap`, `LinkedHashMap` và `TreeMap` với so sánh khóa phù hợp |

Khi các lớp của một loại cùng tuân thủ tiêu chí này, thuật toán nội bộ, thứ tự lưu trữ, độ phức tạp và khả năng đồng bộ có thể khác nhau mà kết quả `equals()` vẫn đúng.

Ví dụ, `ArrayList` lưu phần tử trong mảng động còn `LinkedList` là danh sách liên kết. Những khác biệt đó không xuất hiện trong định nghĩa `List.equals`; thứ được so sánh là **chuỗi giá trị theo vị trí**.

## 3. So sánh hai List khác implementation

Với hai `List`, điều kiện bằng nhau là **cùng kích thước và các phần tử ở từng vị trí tương ứng bằng nhau**. Vì vậy, `ArrayList` và `LinkedList` có thể bằng nhau theo cả hai chiều:

```java
List<String> array = new ArrayList<>(List.of("A", "B"));
List<String> linked = new LinkedList<>(List.of("A", "B"));
System.out.println(array.equals(linked)); // true
System.out.println(linked.equals(array)); // true
```

Đây là đoạn minh họa cần import các kiểu từ `java.util`. Đảo hai vị trí trong `linked` sẽ làm danh sách khác giá trị; thay lớp triển khai mà giữ nội dung theo thứ tự thì không. Hai list bằng nhau phải có hash giống nhau theo công thức của `List`, dù chi tiết lưu trữ nội bộ khác. Bài chuyên đề `List.equals()` phân tích các vị trí lặp, `null` và phần tử có `equals` riêng.

## 4. So sánh hai Set khác implementation

`HashSet` và `LinkedHashSet` có thể bằng nhau dù thứ tự chèn khác; `Set.equals()` yêu cầu hai bên là `Set`, có cùng kích thước và cùng các phần tử theo quan hệ thành viên tương thích:

```java
Set<String> hash = new HashSet<>(List.of("A", "B"));
Set<String> linked = new LinkedHashSet<>(List.of("B", "A"));
System.out.println(hash.equals(linked)); // true
System.out.println(linked.equals(hash)); // true
```

Ví dụ cần các import `java.util`. Cả hai có cùng hash theo hợp đồng tổng mã băm phần tử. `TreeSet` cũng có thể tham gia so sánh xuyên implementation khi `Comparator`/thứ tự tự nhiên nhận diện trùng phù hợp với `equals`; nếu comparator coi hai chuỗi khác nhau theo `equals` là một, tính đối xứng có thể bị phá (xem mục 7). Bài `Set.equals()` đã triển khai kỹ nguyên tắc thành viên và thứ tự duyệt.

## 5. So sánh hai Map khác implementation

`HashMap` và `LinkedHashMap` bằng nhau khi cùng các ánh xạ **khóa → giá trị**, cho dù thứ tự chèn hoặc duyệt không giống nhau:

```java
Map<String, Integer> hash = new HashMap<>();
hash.put("A", 1);
hash.put("B", 2);
Map<String, Integer> linked = new LinkedHashMap<>();
linked.put("B", 2);
linked.put("A", 1);
System.out.println(hash.equals(linked)); // true
```

Đây là fragment với các import `java.util` phù hợp. Khác giá trị của cùng một khóa, hoặc giá trị khác kiểu mà `equals` từ chối (ví dụ `Integer(1)` và `Long(1)`), thì hai map khác nhau. Map bằng nhau phải có hash giống nhau, do cùng tổng hash của các entry. `TreeMap` chỉ tương thích xuyên implementation khi comparator của khóa không làm lệch quan hệ bình đẳng; mục 7 và bài `Map.equals()` trình bày các ranh giới cụ thể.

## 6. Chương trình Java 17 chứng minh các tình huống

Lưu mã sau dưới tên `CollectionContractEqualityDemo.java`. Chương trình có các case `List`, `Set`, `Map`, một `Collection` không sử dụng so sánh nội dung chung, và ví dụ comparator `TreeSet` cố ý không nhất quán với `equals()`.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class CollectionContractEqualityDemo {
    public static void main(String[] args) {
        List<String> array = new ArrayList<>(List.of("java", "core"));
        List<String> linked = new LinkedList<>(List.of("java", "core"));
        List<String> swapped = new LinkedList<>(List.of("core", "java"));

        System.out.println("list cross implementation: "
                + array.equals(linked));
        System.out.println("list symmetric: " + linked.equals(array));
        System.out.println("list order matters: "
                + array.equals(swapped));
        System.out.println("list same hash: "
                + (array.hashCode() == linked.hashCode()));

        Set<String> hashSet = new HashSet<>(List.of("java", "core"));
        Set<String> linkedSet = new LinkedHashSet<>(
                List.of("core", "java"));
        Set<String> treeSet = new TreeSet<>(
                List.of("java", "core"));

        System.out.println("set cross implementation: "
                + hashSet.equals(treeSet));
        System.out.println("set symmetric: " + treeSet.equals(hashSet));
        System.out.println("set order ignored: "
                + hashSet.equals(linkedSet));
        System.out.println("set same hash: "
                + (hashSet.hashCode() == treeSet.hashCode()));

        Map<String, Integer> hashMap = new HashMap<>();
        hashMap.put("alice", 1);
        hashMap.put("bob", 2);

        Map<String, Integer> linkedMap = new LinkedHashMap<>();
        linkedMap.put("bob", 2);
        linkedMap.put("alice", 1);
        Map<String, Integer> treeMap = new TreeMap<>(linkedMap);

        System.out.println("map cross implementation: "
                + hashMap.equals(linkedMap));
        System.out.println("map symmetric: "
                + linkedMap.equals(hashMap));
        System.out.println("map TreeMap cross: "
                + hashMap.equals(treeMap));
        System.out.println("map same hash: "
                + (hashMap.hashCode() == linkedMap.hashCode()));

        Collection<String> deque = new ArrayDeque<>(
                List.of("java", "core"));
        System.out.println("list vs deque: " + array.equals(deque));
        System.out.println("deque vs list: " + deque.equals(array));
        System.out.println("Objects.equals(list, linked): "
                + Objects.equals(array, linked));

        // CỐ Ý SAI VỀ TÍNH TƯƠNG THÍCH CỦA COMPARATOR VỚI equals().
        Set<String> insensitive = new TreeSet<>(
                String.CASE_INSENSITIVE_ORDER);
        insensitive.add("java");
        Set<String> sensitive = new HashSet<>();
        sensitive.add("JAVA");

        System.out.println("bad comparator tree to hash: "
                + insensitive.equals(sensitive));
        System.out.println("bad comparator hash to tree: "
                + sensitive.equals(insensitive));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac CollectionContractEqualityDemo.java
java CollectionContractEqualityDemo
```

Kết quả stdout:

```text
list cross implementation: true
list symmetric: true
list order matters: false
list same hash: true
set cross implementation: true
set symmetric: true
set order ignored: true
set same hash: true
map cross implementation: true
map symmetric: true
map TreeMap cross: true
map same hash: true
list vs deque: false
deque vs list: false
Objects.equals(list, linked): true
bad comparator tree to hash: true
bad comparator hash to tree: false
```

### Đọc những điểm quan trọng trong kết quả

- `ArrayList` và `LinkedList` cùng hai chuỗi theo đúng thứ tự → bằng nhau **theo cả hai chiều**, hash giống nhau. Đảo thứ tự trong list → không bằng nhau.
- `HashSet`, `LinkedHashSet` và `TreeSet` dùng natural ordering của `String` cùng biểu diễn đúng tập chuỗi → bằng nhau bất chấp cách lưu trữ và thứ tự duyệt.
- `HashMap`, `LinkedHashMap` và `TreeMap` có cùng hai ánh xạ chuỗi → số nguyên → bằng nhau, hash giống nhau, dù thứ tự chèn/duyệt khác.
- `ArrayDeque` thuộc `Collection`, nhưng không triển khai `List.equals`; đối với hai đối tượng khác nhau trong ví dụ, `deque.equals(array)` vẫn là so sánh danh tính và trả `false`. `array.equals(deque)` cũng `false` vì `deque` không phải `List`.
- `Objects.equals(array, linked)` gọi `array.equals(linked)` nên vẫn `true`; nó chỉ cung cấp lớp bảo vệ null, không thay đổi hợp đồng nội dung.

Hai dòng “bad comparator” cố ý cho kết quả trái chiều để phơi bày một trường hợp không bảo đảm hợp đồng; **đừng dùng comparator không nhất quán với `equals()` trong set/map mà chương trình cần so sánh với các implementation khác**.

## 7. Khi nào cùng giao diện mà bình đẳng xuyên lớp có thể gặp vấn đề?

### a. Comparator không nhất quán với `equals()`

`TreeSet` có thể dùng `String.CASE_INSENSITIVE_ORDER` để coi `"java"` và `"JAVA"` là tương đương trong cấu trúc cây. Trong khi đó `HashSet` dựa trên `String.equals()`, phân biệt chữ hoa/chữ thường.

Trong chương trình:

- `insensitive` chỉ chứa `"java"`, và có thể tìm `"JAVA"` bằng comparator không phân biệt hoa/thường.
- `sensitive` chỉ chứa `"JAVA"`, và không coi `"java"` là cùng chuỗi theo `String.equals`.
- `insensitive.equals(sensitive)` có thể trả `true` do việc kiểm tra `containsAll` dựa trên comparator của `TreeSet`.
- `sensitive.equals(insensitive)` trả `false` do `HashSet.contains("java")` không tìm được chuỗi giống chính xác.

Đây là **sự không nhất quán của tiêu chí nhận diện phần tử**, dẫn đến vi phạm kỳ vọng đối xứng khi so sánh giữa các set. Không phải lỗi của `String.equals()`. Theo hợp đồng `SortedSet`, thứ tự nên **nhất quán với equals** nếu sorted set phải triển khai đúng hợp đồng `Set`; trường hợp khác là một cấu trúc theo comparator có ngữ nghĩa tập phần tử khác, và cần hiểu rõ giới hạn.

`TreeMap` có vấn đề tương tự về việc comparator có thể coi hai khóa bằng nhau (`compare(k1,k2) == 0`) dù `k1.equals(k2)` là `false`. Vì vậy sự tương thích `Map.equals` giữa `TreeMap` và `HashMap` cũng phụ thuộc chính sách bằng nhau của khóa. Ví dụ chuẩn của phần 6 sử dụng natural ordering của `String`, vốn nhất quán với `String.equals`.

### b. Một custom implementation không tuân theo hợp đồng

Giao diện không tự động cưỡng chế mọi implementation viết đúng `equals()` và `hashCode()`. Nếu tự xây một lớp `List` mà `equals()` chỉ so sánh `getClass()`, lớp đó có thể không đáp ứng hợp đồng `List.equals()` và làm hỏng tính đối xứng với `ArrayList` hoặc `LinkedList`.

Vì thế, khi viết collection tùy biến, đọc hợp đồng giao diện và kiểm thử cả **hai hướng** khi so sánh với các implementation chuẩn, thay vì chỉ dựa trên kết quả một lần gọi. Cần bảo đảm giá trị hash nhất quán với quan hệ bằng nhau.

### c. Phần tử bên trong có `equals()` bất thường

List, set và map dựa vào quan hệ bằng nhau của **phần tử, khóa và giá trị**. Nếu một class phần tử dùng epsilon không bắc cầu, phụ thuộc trạng thái thay đổi, so sánh lớp cha/con không đối xứng hoặc tạo hash trái hợp đồng, các collection sử dụng đối tượng đó cũng có thể thể hiện hành vi bất ngờ.

Ví dụ, `HashSet` không thể “sửa” một cặp phần tử có `equals()` sai. Trước khi so sánh collection, bảo đảm từng kiểu giá trị liên quan có quan hệ bằng nhau hợp lệ và hash tương ứng.

### d. Hai kiểu collection có bản chất khác nhau

Một `List` có thứ tự và có thể chứa phần tử lặp; một `Set` không cho phép hai phần tử trùng theo quan hệ bằng nhau. Dù chúng cùng xuất hiện dưới tham chiếu `Collection` hoặc cùng chứa những chuỗi giống nhau, **không có hợp đồng bắt buộc `List.equals(Set)` phải trả `true`**. Thực tế các lớp chuẩn không định nghĩa chúng là bằng nhau.

`Queue` hoặc `Deque` cũng không mặc nhiên thực hiện so sánh nội dung như `List`. Chẳng hạn `ArrayDeque` thừa hưởng `equals()` theo danh tính đối tượng. Thấy hai collection in ra các phần tử giống nhau hoặc có cùng thứ tự duyệt chưa đủ để kết luận bằng nhau.

## 8. Giá trị, sự thay đổi và cách sử dụng trong collection khác

### Vì sao quan hệ bằng nhau cần ổn định?

Một `List` chứa phần tử có trạng thái thay đổi có thể đổi kết quả `equals()` và `hashCode()` khi phần tử được sửa. Một `Set` hoặc `Map` chứa khóa có trường tham gia hash thay đổi sau khi chèn có thể không còn tìm được khóa bằng chính giá trị hiện tại theo cách mong đợi.

Với các đối tượng được dùng làm **phần tử của `HashSet` hoặc khóa của `HashMap`**, ưu tiên các lớp bất biến hoặc khóa bất biến. Ngay cả khi tập/map giữ đối tượng đó bằng tham chiếu, thay đổi giá trị liên quan `equals()`/`hashCode()` sau khi lưu có thể phá vỡ các phép `contains`/`get`/`remove`.

### Cẩn thận khi dùng collection làm key của map hoặc phần tử của set khác

Nếu một `List` được dùng làm khóa `HashMap`, việc thêm/xóa/sắp xếp phần tử trong list sẽ thay đổi `List.hashCode()`. Map có thể không tìm lại được khóa ở bucket cũ. Một list bất biến bằng `List.copyOf` hoặc `List.of` có thể phù hợp khi phần tử cũng ổn định, nhưng chỉ sự bất biến cấu trúc list **không đảm bảo bất biến sâu** của các đối tượng chứa trong list.

`Set.hashCode()` cũng phụ thuộc mã băm phần tử; `Map.hashCode()` phụ thuộc mã băm entry. Khi dùng tập/map làm khóa hoặc phần tử của một cấu trúc hash khác, cần bảo đảm nội dung tạo nên bản sắc không bị thay đổi trong vòng đời lưu trữ.

## 9. Kiểm thử hợp đồng khi so sánh xuyên implementation

Một bộ kiểm thử nhỏ nên bao gồm:

1. **Giữa cùng loại:** `ArrayList` ↔ `LinkedList` cùng phần tử/thứ tự, `HashSet` ↔ `TreeSet` với comparator hợp lệ, `HashMap` ↔ `LinkedHashMap` cùng ánh xạ.
2. **Hai chiều:** kiểm tra cả `a.equals(b)` lẫn `b.equals(a)` để phát hiện lỗi đối xứng.
3. **Bắc cầu:** nếu `a`, `b`, `c` dùng ba implementation nhưng cùng biểu diễn giá trị theo hợp đồng, `a.equals(b) && b.equals(c)` phải kéo theo `a.equals(c)`.
4. **Hash:** khi hai đối tượng bằng nhau, hash phải giống nhau, dù không yêu cầu hai đối tượng khác nhau có hash khác nhau.
5. **Phản ví dụ cố ý:** list đảo thứ tự; set thiếu một phần tử; map cùng khóa nhưng khác value; comparator không nhất quán với equals; phần tử thay đổi trạng thái.
6. **Null và implementation đặc biệt:** `HashMap` và `HashSet` thường cho phép `null`; `Map.of`/`Set.of` cấm `null`. Khi tạo dữ liệu test, chọn cách khởi tạo tương thích với chính collection.

Ví dụ mẫu (fragment giả sử đã có hai đối tượng không null `a`, `b` của cùng một hợp đồng bằng nhau):

```java
if (a.equals(b) != b.equals(a)) {
    throw new AssertionError("equals() is not symmetric");
}
if (a.equals(b) && a.hashCode() != b.hashCode()) {
    throw new AssertionError("equal objects have different hashes");
}
```

Hai điều kiện trên kiểm tra đối xứng và kết hợp hash trên **một cặp** đã chọn. Chúng không chứng minh mọi giá trị đều đúng; phải kết hợp kiểm thử biên, bộ ba và phân tích định nghĩa bằng nhau.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `new ArrayList<>(List.of("A", "B")).equals(new LinkedList<>(List.of("A", "B")))` trả gì?  
**Đáp án:** `true`, do cả hai cùng tuân thủ hợp đồng `List.equals` theo thứ tự phần tử, không yêu cầu cùng lớp triển khai.

**Câu 2.** `new HashSet<>(List.of("A", "B")).equals(new LinkedHashSet<>(List.of("B", "A")))` trả gì?  
**Đáp án:** `true`; set không xét thứ tự chèn hay thứ tự duyệt.

**Câu 3.** `HashMap` và `LinkedHashMap` có cùng entry nhưng thứ tự chèn ngược nhau có bằng nhau không?  
**Đáp án:** Có, nếu khóa và giá trị tuân thủ ngữ nghĩa `equals()` đúng; `Map.equals` dựa trên ánh xạ, không xét thứ tự entry.

**Câu 4.** Vì sao `ArrayDeque` và `ArrayList` cùng chứa `"A", "B"` thường không bằng nhau?  
**Đáp án:** `ArrayDeque` không cam kết `List.equals`; bản thân `Collection` không áp đặt so sánh nội dung chung cho mọi implementation.

**Câu 5.** Có thể luôn coi `TreeSet` và `HashSet` chứa “cùng chữ cái” là bằng nhau không?  
**Đáp án:** Không. Nếu comparator của `TreeSet` xác định tương đương khác với `equals()` của phần tử, thậm chí có thể mất tính đối xứng trong so sánh xuyên implementation.

## Ghi nhớ

**Quan hệ bằng nhau theo giá trị có thể vượt qua ranh giới lớp triển khai khi các lớp cùng tuân thủ một hợp đồng ngữ nghĩa.** `ArrayList` và `LinkedList` so theo vị trí phần tử; các `Set` chuẩn so theo tập phần tử; các `Map` chuẩn so theo tập ánh xạ. Điều kiện thiết yếu là thuật toán và chính sách nhận diện phần tử/khóa phải thống nhất. `Collection` nói chung không có một quy tắc `equals()` nội dung áp dụng cho mọi kiểu, còn comparator hoặc phần tử không tuân thủ hợp đồng có thể làm hỏng tính đối xứng, tính bắc cầu và hành vi collection.
