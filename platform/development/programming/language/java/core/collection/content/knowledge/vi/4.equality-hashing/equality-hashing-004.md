# Ngữ nghĩa equals của List, Set và Map

Hai collection chứa những giá trị nhìn giống nhau chưa chắc bằng nhau. Java xác định bình đẳng theo **mô hình dữ liệu** của cấu trúc:

- `List` là một chuỗi phần tử có thứ tự.
- `Set` là một tập thành viên, không có lần xuất hiện trùng.
- `Map` là một tập ánh xạ từ khóa đến giá trị.

Vì vậy, “bằng nhau” phải trả lời một câu hỏi khác nhau ở mỗi nhóm. Hai danh sách cần có cùng thứ tự; hai tập không cần cùng thứ tự duyệt; hai map cần cùng các cặp khóa–giá trị chứ không chỉ cùng khóa hoặc cùng giá trị.

Bài này trình bày hợp đồng chung của `List`, `Set` và `Map`, với ví dụ Java 17 trở lên. Các kết luận giả định kiểu phần tử, khóa và giá trị có quy tắc bình đẳng hợp lệ; những cấu trúc dùng quan hệ đặc biệt cần đọc hợp đồng riêng.

## 1. Bản đồ ba kiểu bình đẳng

| Cấu trúc | Khi nào bằng nhau? | Thứ tự có ý nghĩa? |
| --- | --- | --- |
| `List` | Đối tượng kia cũng là `List`, cùng số phần tử và từng cặp cùng vị trí bằng nhau | Có |
| `Set` | Đối tượng kia cũng là `Set`, có cùng các thành viên | Không xét thứ tự duyệt |
| `Map` | Đối tượng kia cũng là `Map`, biểu diễn cùng các ánh xạ | Không xét thứ tự duyệt entry |

Ví dụ ngắn:

```text
List [A, B] và List [B, A]       → không bằng nhau
Set  {A, B} và Set  {B, A}       → bằng nhau
Map  A→1, B→2 và Map B→2, A→1    → bằng nhau
Map  A→1, B→2 và Map A→2, B→1    → không bằng nhau
```

Ký hiệu dấu ngoặc nhọn trong sơ đồ chỉ mô tả tập/map, không phải cú pháp literal của Java.

Không cần hai đối tượng thuộc cùng lớp cụ thể: `ArrayList` có thể bằng `LinkedList`; `HashMap` có thể bằng `TreeMap` nếu cùng ánh xạ và quy tắc khóa phù hợp.

## 2. List.equals: cùng độ dài, cùng thứ tự, cùng giá trị

### 2.1. So theo từng vị trí

Hai danh sách bằng nhau khi:

1. Đối tượng được so sánh cũng là `List`.
2. Số phần tử bằng nhau.
3. Ở mỗi vị trí, hai phần tử bằng nhau theo quy tắc giá trị tương ứng.

```java
List<String> first =
        new ArrayList<>(List.of("A", "B", "A"));

List<String> same =
        new LinkedList<>(List.of("A", "B", "A"));

List<String> reordered = List.of("A", "A", "B");

System.out.println(first.equals(same));      // true
System.out.println(first.equals(reordered)); // false
```

Đây là đoạn minh họa trong một phương thức; cần import các kiểu `java.util` được dùng.

`first` và `same` lưu bằng hai cách khác nhau nhưng có cùng chuỗi giá trị. `reordered` có cùng các giá trị và cùng số lần xuất hiện, nhưng vị trí khác nên không bằng.

Bình đẳng danh sách không đồng nghĩa “có cùng tập thành viên” hoặc “có cùng số lần xuất hiện nếu bỏ thứ tự”. [Java 17: List.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#equals(java.lang.Object))

### 2.2. Phần tử trùng có ý nghĩa

```java
List<String> twice = List.of("A", "A");
List<String> once = List.of("A");

System.out.println(twice.equals(once)); // false
```

Danh sách biểu diễn từng lần xuất hiện. Một thao tác chuyển sang `Set` sẽ làm mất thông tin này.

Vì vậy, cách so sau không kiểm tra bình đẳng danh sách:

```java
new HashSet<>(first).equals(new HashSet<>(second))
```

Nó đang hỏi “hai danh sách có cùng các giá trị phân biệt không”, bỏ cả thứ tự lẫn số lần xuất hiện. Chỉ dùng phép biến đổi này khi đó chính là yêu cầu nghiệp vụ.

Ngay cả ghép thêm kiểm tra `size` cũng chưa đủ để so đa tập: `[A, A, B]` và `[A, B, B]` cùng kích thước và cùng tập giá trị phân biệt nhưng khác số lần xuất hiện.

### 2.3. Quyền sửa không tham gia bình đẳng

```java
List<String> editable =
        new ArrayList<>(List.of("A", "B"));

List<String> unmodifiable = List.of("A", "B");

System.out.println(editable.equals(unmodifiable)); // true
```

`equals` không hỏi danh sách nào thêm/xóa được hoặc được tạo bằng factory nào. Nó so chuỗi phần tử.

Dữ liệu có thể thay đổi về sau; hai danh sách bằng nhau ở một thời điểm không có nghĩa mãi bằng nhau. Sự kiện thêm, xóa hoặc thay phần tử có thể đổi kết quả.

## 3. Set.equals: cùng thành viên, không xét thứ tự duyệt

### 3.1. Thứ tự chèn và cách lưu không đổi nghĩa tập

```java
Set<String> first =
        new LinkedHashSet<>(List.of("A", "B"));

Set<String> second =
        new HashSet<>(List.of("B", "A"));

System.out.println(first.equals(second)); // true
```

`LinkedHashSet` giữ thứ tự chèn để duyệt. `HashSet` không cam kết thứ tự duyệt. Nhưng thứ tự ấy không tham gia `Set.equals`.

Hai tập phải có cùng thành viên. Không thể kết luận bằng nhau chỉ vì cùng kích thước:

```java
System.out.println(
        Set.of("A", "B").equals(Set.of("A", "C"))
); // false
```

Tập không biểu diễn số lần xuất hiện trùng. Nếu đầu vào có `A` nhiều lần, sau khi đưa vào một tập bình đẳng phù hợp thì chỉ còn một thành viên `A`. [Java 17: Set.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#equals(java.lang.Object))

### 3.2. Cùng nội dung in ra không làm List bằng Set

```java
List<String> list = List.of("A", "B");
Set<String> set = new LinkedHashSet<>(list);

System.out.println(list.equals(set)); // false
System.out.println(set.equals(list)); // false
```

Danh sách và tập là hai mô hình khác nhau. Dù khi in có thể đều trông như `[A, B]`, chúng không bằng nhau theo hai hợp đồng này.

Đối xứng được giữ vì `List.equals` chỉ nhận đối tượng `List` cho so sánh nội dung, còn `Set.equals` chỉ nhận `Set`.

Đừng so sánh collection bằng chuỗi `toString()`: định dạng hiển thị và thứ tự không đủ biểu đạt loại cấu trúc hoặc hợp đồng bình đẳng.

## 4. Map.equals: phải đúng cặp khóa–giá trị

### 4.1. Bình đẳng ánh xạ không phụ thuộc thứ tự put

```java
Map<String, Integer> first = new LinkedHashMap<>();
first.put("A", 1);
first.put("B", 2);

Map<String, Integer> second = new TreeMap<>();
second.put("B", 2);
second.put("A", 1);

System.out.println(first.equals(second)); // true
```

Đoạn minh họa cần import các kiểu tương ứng.

Hai map biểu diễn cùng ánh xạ: `A` đi đến 1 và `B` đi đến 2. Không cần cùng thứ tự thêm, cùng thứ tự duyệt hoặc cùng lớp triển khai.

Một cách diễn đạt của hợp đồng là hai `entrySet` bằng nhau. Mỗi entry liên kết khóa với giá trị tương ứng. [Java 17: Map.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#equals(java.lang.Object))

### 4.2. Cùng khóa hoặc cùng tập giá trị đều chưa đủ

```java
Map<String, Integer> first = Map.of("A", 1, "B", 2);
Map<String, Integer> swapped = Map.of("A", 2, "B", 1);

System.out.println(first.keySet().equals(swapped.keySet())); // true
System.out.println(first.equals(swapped));                  // false
```

Hai map cùng các khóa và cùng các giá trị 1, 2, nhưng ghép cặp khác.

Nếu chỉ so `keySet`, ta đang kiểm tra phạm vi khóa, không kiểm tra nội dung ánh xạ. Nếu đưa `values()` vào một tập để so, ta còn làm mất thông tin giá trị trùng và quan hệ với khóa.

Ví dụ map `A→1, B→1` có hai ánh xạ dù tập giá trị phân biệt chỉ có một giá trị. Số ánh xạ và số giá trị phân biệt là hai đại lượng khác nhau.

### 4.3. Giá trị null không làm mất ý nghĩa của khóa

Với map có hỗ trợ `null`:

```java
Map<String, String> first = new HashMap<>();
first.put("A", null);

Map<String, String> second = new HashMap<>();
second.put("B", null);

System.out.println(first.equals(second)); // false
```

Cả hai cùng kích thước và cùng có giá trị `null`, nhưng khóa khác nhau.

Không tự viết phép so map chỉ bằng `other.get(key)` rồi coi `null` là đủ chứng minh tương đương. `get` có thể trả `null` khi không có khóa; ánh xạ “có khóa với giá trị null” khác “không có khóa”.

Khi so đúng hợp đồng map, sự tồn tại của khóa và giá trị tương ứng đều phải được giữ.

## 5. HashCode của mỗi cấu trúc phải khớp nghĩa equals

Nếu hai đối tượng bằng nhau, chúng phải có cùng hash. Vì vậy, các interface quy định cách tính hash phù hợp với mô hình bình đẳng.

### 5.1. List có hash phụ thuộc thứ tự

Công thức của danh sách có thể diễn đạt:

```java
int hash = 1;
for (Object element : list) {
    hash = 31 * hash + (element == null ? 0 : element.hashCode());
}
```

Đây là đoạn mô tả công thức, không phải chương trình độc lập. Nó không hứa hash là duy nhất.

Với phần tử `Integer`:

```text
List [1, 2]:
  bắt đầu 1
  sau 1: 31 × 1 + 1 = 32
  sau 2: 31 × 32 + 2 = 994
```

Thứ tự có ảnh hưởng đến phép tích lũy. Tuy nhiên, hai danh sách khác nhau vẫn có thể va chạm hash; không dùng so hash để thay `equals`.

### 5.2. Set có hash không phụ thuộc thứ tự

Hash của tập là tổng hash của các phần tử; phần tử `null`, nếu được hỗ trợ, đóng góp 0.

Vì phép cộng không phụ thuộc thứ tự, hai tập cùng thành viên có cùng hash dù duyệt khác thứ tự. Chẳng hạn tập số nguyên `{1, 2}` có tổng hash bằng 3 theo quy tắc hash của các phần tử này.

Không thể suy ngược từ tổng hash bằng nhau ra cùng tập. `{1, 2}` và `{3}` có thể cùng tổng nhưng rõ ràng khác thành viên.

### 5.3. Map có hash theo các entry

Hash của map là tổng hash các entry. Hash một entry được xác định bằng XOR giữa hash khóa và hash giá trị, dùng 0 cho thành phần `null` khi hợp lệ:

```text
entryHash = keyHash XOR valueHash
mapHash   = tổng entryHash của các ánh xạ
```

Thứ tự duyệt entry không ảnh hưởng tổng. Hai map bằng nhau theo ánh xạ có cùng hash.

Một lần nữa, cùng hash không chứng minh các cặp khóa–giá trị bằng nhau. [Java 17: List.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#hashCode()), [Set.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#hashCode()), [Map.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#hashCode()), [Map.Entry.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html#hashCode())

Các công thức này giúp bảo đảm bình đẳng xuyên qua các lớp triển khai cùng mô hình. Một `ArrayList` bằng `LinkedList` phải có cùng hash, chứ không được tự lấy hash theo địa chỉ vùng lưu riêng.

## 6. Bình đẳng lồng nhau theo kiểu của từng thành phần

Khi phần tử hoặc giá trị là một collection khác, quy tắc được áp dụng theo từng lớp cấu trúc.

### 6.1. Map chứa List

```java
Map<String, List<Integer>> first =
        Map.of("scores", List.of(1, 2));

Map<String, List<Integer>> second =
        Map.of("scores", List.of(2, 1));

System.out.println(first.equals(second)); // false
```

Map không xét thứ tự duyệt các khóa, nhưng giá trị tại khóa `"scores"` là một danh sách. Danh sách ấy xét thứ tự phần tử, nên hai giá trị không bằng nhau.

### 6.2. List chứa Set

Hai danh sách có thể bằng nhau nếu mỗi cặp tập cùng vị trí có cùng thành viên, dù thứ tự duyệt bên trong tập khác nhau.

Nhưng đổi vị trí hai tập khác nhau trong danh sách vẫn có thể làm hai danh sách không bằng. “Không xét thứ tự” của tập không lan ra để xóa ý nghĩa thứ tự của danh sách ngoài.

### 6.3. Set chứa List

Trong một tập các danh sách, `[1, 2]` và `[2, 1]` là hai phần tử khác nhau vì danh sách so theo thứ tự.

Tập ngoài không quan tâm hai danh sách được duyệt theo thứ tự nào; nó vẫn dùng bình đẳng của từng danh sách làm thành viên.

Hãy đọc cấu trúc từ ngoài vào: mỗi tầng có quy tắc riêng, không có một chế độ “so sâu và bỏ mọi thứ tự” mặc định.

## 7. Mảng bên trong collection không tự được so theo nội dung

Một điểm dễ gây bất ngờ:

```java
int[] firstArray = {1, 2};
int[] secondArray = {1, 2};

List<int[]> first = List.of(firstArray);
List<int[]> second = List.of(secondArray);

System.out.println(first.equals(second)); // false
System.out.println(Arrays.equals(firstArray, secondArray)); // true
```

Hai danh sách đều có một phần tử, nhưng các phần tử là hai đối tượng mảng khác nhau. Mảng không ghi đè `equals` thành phép so nội dung phần tử, nên `List.equals` không tự gọi `Arrays.equals` thay thế.

Dùng mảng primitive `int[]` trong ví dụ cũng làm rõ mỗi mảng là một phần tử `List<int[]>`.

Nếu mô hình cần bình đẳng theo nội dung mảng, có thể:

- So tường minh bằng `Arrays.equals` trong đúng phép kiểm tra.
- Chọn một kiểu giá trị có `equals`/`hashCode` theo nội dung.
- Chuyển sang cấu trúc giá trị phù hợp như danh sách phần tử, nếu điều đó đúng yêu cầu.

Một wrapper chỉ ghi đè `equals` theo nội dung mảng nhưng giữ hash theo nhận dạng mảng vẫn sai hợp đồng. Nếu dùng nó trong tập/map băm, cần tính hash nội dung tương ứng, chẳng hạn theo API `Arrays.hashCode`. [Java 17: Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)

“Lồng nhau” không đồng nghĩa collection tự biết mọi cấu trúc tùy ý để thực hiện deep equality.

## 8. Collection không có một hợp đồng nội dung chung cho mọi lớp

`Collection` là interface gốc cho nhiều nhóm, nhưng nó không áp đặt một phép `equals` theo nội dung duy nhất cho mọi cách triển khai.

`List` và `Set` bổ sung những hợp đồng riêng. Nếu một biến khai báo `Collection<String>` nhưng đối tượng thật là `ArrayList`, lời gọi `equals` vẫn dùng hành vi của đối tượng danh sách; kiểu khai báo không đổi mô hình lúc chạy.

Ngược lại, không được giả định mọi queue, deque hoặc wrapper bất kỳ đều so nội dung giống `List`. Cần đọc hợp đồng lớp cụ thể.

Nếu một lớp tùy chỉnh không phải `List` hay `Set` muốn định nghĩa bình đẳng nội dung, nó phải đặc biệt giữ đối xứng khi so với các mô hình đã có. Không thiết kế lớp “bằng mọi collection chứa cùng các phần tử” trong khi các collection kia không xem nó bằng. [Java 17: Collection, equals và hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

## 9. Các ranh giới cần lưu ý

### 9.1. Thứ tự comparator phải phù hợp bình đẳng khi dùng tập cây

`TreeSet` tìm thành viên bằng thứ tự tự nhiên hoặc comparator. Nếu comparator xem hai phần tử là tương đương nhưng `equals` lại coi khác, hành vi so với một tập khác có thể vi phạm những kỳ vọng của hợp đồng tập.

Ví dụ một bên coi chữ hoa và chữ thường giống nhau, bên còn lại dùng bình đẳng chuỗi phân biệt hoa thường. Đừng kết luận “cùng nội dung hiển thị là đủ”; phải bảo đảm các cấu trúc đang dùng cùng quan hệ giá trị phù hợp.

Tài liệu `TreeSet` yêu cầu thứ tự nhất quán với `equals` nếu muốn tuân thủ đầy đủ hợp đồng `Set`. [Java 17: TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

### 9.2. IdentityHashMap là trường hợp đặc biệt có chủ đích

`IdentityHashMap` sử dụng bình đẳng tham chiếu cho khóa và giá trị, thay vì bình đẳng logic thông thường. Tài liệu lớp nói rõ nó có chủ đích khác hợp đồng map thông thường ở điểm này.

Không đưa cấu trúc dùng identity vào một phép so nội dung với map thông thường rồi mặc định mọi tính chất sẽ tương đương. Chỉ dùng kiểu đặc biệt đó khi yêu cầu chính là theo dõi nhận dạng đối tượng. [Java 17: IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)

### 9.3. Null là phần tử khác với việc thiếu phần tử

Hai danh sách có `null` ở cùng vị trí có thể bằng nhau nếu cách triển khai chấp nhận dữ liệu đó. Một danh sách chứa một `null` không bằng danh sách rỗng.

Tương tự, tập có `null` khác tập rỗng; map có ánh xạ đến `null` khác map không có ánh xạ ấy.

Các factory như `List.of` hoặc `Map.of` có chính sách đầu vào riêng. Không cố tạo dữ liệu `null` bằng một factory không hỗ trợ rồi nhầm lỗi khởi tạo với kết quả của `equals`.

## 10. Dữ liệu có thể sửa làm kết quả bình đẳng thay đổi

Một danh sách được dùng làm phần tử của `HashSet` có hash phụ thuộc nội dung của nó. Nếu sau khi thêm vào tập, chương trình sửa danh sách, hash và bình đẳng của phần tử có thể đổi.

Điều đó có thể làm cấu trúc băm không còn tìm thấy theo cách mong muốn. Rủi ro tương tự tồn tại với:

- Danh sách hoặc tập làm khóa map.
- Một map làm phần tử trong tập.
- Collection ngoài chứa phần tử có `equals`/`hashCode` phụ thuộc trạng thái thay đổi.
- Danh sách không sửa được nhưng chứa đối tượng phần tử vẫn sửa được.

Khi cần khóa theo nội dung, nên dùng biểu diễn giá trị đủ ổn định và bảo vệ cả dữ liệu thành phần. Chỉ bọc một lớp không cho sửa cấu trúc chưa chắc giải quyết được mọi trạng thái bên trong.

Hai collection bằng nhau ở một thời điểm không hứa rằng chúng có cùng chủ sở hữu, cùng vòng đời hoặc cùng dữ liệu bất biến.

Ngoài ra, không gọi phép so trên dữ liệu đang bị sửa đồng thời mà không có cơ chế phù hợp. Một lần `equals` không tự tạo ảnh chụp giao dịch chung cho hai cấu trúc.

Cấu trúc tự chứa chính nó hoặc có chu trình cũng cần tránh trong mô hình bình đẳng đơn giản: các phép so hoặc hash đệ quy có thể không được định nghĩa rõ hoặc không kết thúc như mong muốn.

## 11. Chương trình Java 17 hoàn chỉnh

Lưu vào `CollectionEqualityDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

public class CollectionEqualityDemo {
    public static void main(String[] args) {
        List<String> firstList =
                new ArrayList<>(List.of("A", "B", "A"));
        List<String> sameList =
                new LinkedList<>(List.of("A", "B", "A"));
        List<String> reordered = List.of("A", "A", "B");

        System.out.println("different list classes equal = "
                + firstList.equals(sameList));
        System.out.println("list order matters = "
                + firstList.equals(reordered));
        System.out.println("equal list hashes = "
                + (firstList.hashCode() == sameList.hashCode()));

        Set<String> firstSet =
                new LinkedHashSet<>(List.of("A", "B"));
        Set<String> secondSet =
                new HashSet<>(List.of("B", "A"));
        System.out.println("set order ignored = "
                + firstSet.equals(secondSet));
        System.out.println("equal set hashes = "
                + (firstSet.hashCode() == secondSet.hashCode()));
        System.out.println("list equals set = "
                + List.of("A", "B").equals(firstSet));
        System.out.println("set equals list = "
                + firstSet.equals(List.of("A", "B")));

        Map<String, Integer> firstMap = new LinkedHashMap<>();
        firstMap.put("A", 1);
        firstMap.put("B", 2);
        Map<String, Integer> secondMap = new TreeMap<>();
        secondMap.put("B", 2);
        secondMap.put("A", 1);
        System.out.println("different map classes equal = "
                + firstMap.equals(secondMap));
        System.out.println("equal map hashes = "
                + (firstMap.hashCode() == secondMap.hashCode()));
        System.out.println("same values wrong keys = "
                + firstMap.equals(Map.of("A", 2, "B", 1)));

        Map<String, String> nullAtA = new HashMap<>();
        nullAtA.put("A", null);
        Map<String, String> nullAtB = new HashMap<>();
        nullAtB.put("B", null);
        System.out.println("null values different keys = "
                + nullAtA.equals(nullAtB));

        Map<String, List<Integer>> nestedA =
                Map.of("scores", List.of(1, 2));
        Map<String, List<Integer>> nestedB =
                Map.of("scores", List.of(2, 1));
        System.out.println("nested list order matters = "
                + nestedA.equals(nestedB));

        int[] arrayA = {1, 2};
        int[] arrayB = {1, 2};
        List<int[]> arraysA = List.of(arrayA);
        List<int[]> arraysB = List.of(arrayB);
        System.out.println("list of distinct arrays equal = "
                + arraysA.equals(arraysB));
        System.out.println("array contents equal explicitly = "
                + Arrays.equals(arrayA, arrayB));

        List<String> editable = new ArrayList<>(List.of("A", "B"));
        System.out.println("mutability ignored by list equals = "
                + editable.equals(List.of("A", "B")));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CollectionEqualityDemo.java
java CollectionEqualityDemo
```

Stdout:

```text
different list classes equal = true
list order matters = false
equal list hashes = true
set order ignored = true
equal set hashes = true
list equals set = false
set equals list = false
different map classes equal = true
equal map hashes = true
same values wrong keys = false
null values different keys = false
nested list order matters = false
list of distinct arrays equal = false
array contents equal explicitly = true
mutability ignored by list equals = true
```

Các nhãn như `list order matters` đi kèm kết quả của phép `equals`: `false` ở dòng đó nghĩa là hai danh sách đổi thứ tự **không bằng nhau**.

Cách đọc minh chứng:

1. Danh sách khác lớp vẫn bằng nếu cùng chuỗi phần tử, và có cùng hash.
2. Đổi thứ tự danh sách làm kết quả so khác.
3. Tập có cùng thành viên bằng nhau dù cách lưu và thứ tự thêm khác.
4. Danh sách không bằng tập ở cả hai chiều.
5. Map khác lớp bằng nếu cùng ánh xạ, nhưng đổi ghép cặp giá trị thì khác.
6. Hai giá trị `null` tại hai khóa khác nhau không làm map bằng nhau.
7. Map chứa danh sách vẫn chịu quy tắc thứ tự của danh sách ở tầng giá trị.
8. Hai mảng riêng cùng nội dung không tự làm hai danh sách chứa chúng bằng nhau.
9. Khả năng sửa danh sách không phải tiêu chí `List.equals`.

Chương trình không so chuỗi in trực tiếp của các map/tập không có thứ tự. Kết quả boolean dựa trên hợp đồng mô hình.

## 12. Chọn đúng phép so cho yêu cầu

Trước khi gọi `equals`, diễn đạt yêu cầu bằng một câu:

| Yêu cầu | Hướng xử lý |
| --- | --- |
| Cùng chuỗi theo vị trí và số lần xuất hiện | `List.equals` |
| Cùng các thành viên phân biệt, bỏ thứ tự và số lần lặp | So tập đã được tạo theo quy tắc phù hợp |
| Cùng số lần xuất hiện, không xét thứ tự | Xây bảng tần suất theo quan hệ bằng nhau cần dùng |
| Cùng ánh xạ khóa đến giá trị | `Map.equals` |
| Chỉ cần cùng khóa | So `keySet` |
| So mảng theo nội dung | API `Arrays.equals` hoặc kiểu giá trị tương ứng |
| So theo một vài thuộc tính nghiệp vụ | Phép so hoặc khóa giá trị được thiết kế rõ |

Không thay `equals` bằng cách so hash, so `size`, so `containsAll` một chiều hoặc so `toString`. Mỗi cách chỉ cung cấp một phần thông tin.

Ví dụ, `first.containsAll(second)` chưa chứng minh hai danh sách bằng nhau: nó không xét thứ tự và không tự đếm số lần xuất hiện. Muốn so kiểu đa tập, cần xử lý tần suất.

## 13. Lỗi thường gặp

| Hiểu nhầm | Điều cần nhớ |
| --- | --- |
| Khác lớp triển khai thì không thể bằng | Các lớp cùng mô hình có thể bằng theo hợp đồng interface |
| Mọi collection có cùng các phần tử đều bằng | `List`, `Set` và những nhóm khác có hợp đồng khác |
| Set có thứ tự chèn thì equals cũng xét thứ tự chèn | Thứ tự duyệt của tập không tham gia `Set.equals` |
| Map bằng khi cùng các giá trị | Phải đúng giá trị tại từng khóa |
| Có cùng hash thì có cùng nội dung | Hash có thể va chạm |
| Bỏ trùng rồi so Set là cách so mọi List | Nó làm mất thứ tự và số lần xuất hiện |
| Collection lồng nhau luôn được deep compare tùy ý | Mỗi tầng dùng `equals` của phần tử; mảng vẫn là trường hợp khác |
| Danh sách không sửa được có hash mãi ổn định | Phần tử bên trong vẫn có thể thay đổi |
| Dữ liệu đang thay đổi vẫn so như một ảnh chụp nguyên tử | Phải có cơ chế quan sát nhất quán phù hợp |
| TreeSet và HashSet luôn dùng cùng phép tương đương | Comparator không nhất quán với equals có thể phá kỳ vọng |

## 14. Tự luyện

1. `[A, B, A]` có bằng `[A, A, B]` theo `List.equals` không?  
   **Đáp án:** không, vì thứ tự khác.

2. Hai `LinkedHashSet` được thêm A rồi B và B rồi A có bằng nhau không?  
   **Đáp án:** có, nếu cùng hai thành viên và quy tắc bình đẳng hợp lệ.

3. Map `A→1, B→2` có bằng map `A→2, B→1` không?  
   **Đáp án:** không. Cùng tập khóa và tập giá trị chưa đủ.

4. Hai danh sách mỗi bên chứa một mảng `int[]` mới có cùng số bên trong có tự bằng nhau không?  
   **Đáp án:** không; danh sách không tự thay phép `equals` mảng bằng `Arrays.equals`.

5. Vì sao một `ArrayList` và một `LinkedList` bằng nhau phải có cùng hash?  
   **Đáp án:** chúng tuân thủ cùng hợp đồng bình đẳng và băm của `List`; cách lưu riêng không được phá điều kiện bằng nhau thì cùng hash.

Khi hiểu đúng mô hình, `equals` trở thành một câu hỏi chính xác: cùng chuỗi, cùng thành viên hay cùng ánh xạ. Chọn câu hỏi đó trước, rồi kiểm tra quy tắc bình đẳng của các thành phần bên trong.
