# reversed như một view có thứ tự ngược

Java 21 bổ sung `reversed()` cho các collection có thứ tự thông qua hệ thống `SequencedCollection`, `SequencedSet` và `SequencedMap`. Phương thức này cung cấp một *view* (góc nhìn) có encounter order đảo ngược so với collection gốc. View dùng chung dữ liệu với collection ban đầu: thay đổi nhìn thấy qua view cũng được phản ánh ở collection gốc và ngược lại.

Điểm quan trọng là `reversed()` không yêu cầu đảo lại dữ liệu đang lưu hoặc tạo một bản sao độc lập. Nó cung cấp một cách truy cập cùng collection theo thứ tự ngược. Cách hiểu này giúp sử dụng API đầu-cuối, duyệt dữ liệu, xử lý stream và thao tác với map có thứ tự một cách nhất quán.

## 1. reversed() trong Sequenced Collections

Java 21 định nghĩa ba interface chính để biểu diễn collection có thứ tự:

- `SequencedCollection<E>` mở rộng `Collection<E>`, cung cấp thứ tự encounter xác định và các thao tác ở hai đầu như `getFirst()`, `getLast()`, `addFirst()`, `addLast()`, `removeFirst()`, `removeLast()` cùng `reversed()`.
- `SequencedSet<E>` mở rộng `Set<E>` và `SequencedCollection<E>`, giữ tính duy nhất của phần tử đồng thời có thứ tự encounter.
- `SequencedMap<K, V>` mở rộng `Map<K, V>`, cung cấp thứ tự encounter cho các mapping và các thao tác đầu-cuối như `firstEntry()`, `lastEntry()`, `putFirst()`, `putLast()`, `pollFirstEntry()`, `pollLastEntry()` cùng `reversed()`.

Các interface chuyên biệt khai báo `reversed()` với kiểu trả về phù hợp hơn:

| Kiểu khai báo | Kiểu trả về của `reversed()` |
|---|---|
| `SequencedCollection<E>` | `SequencedCollection<E>` |
| `List<E>` | `List<E>` |
| `SequencedSet<E>` | `SequencedSet<E>` |
| `SequencedMap<K, V>` | `SequencedMap<K, V>` |

Ví dụ, biến có kiểu `List<String>` vẫn nhận được một `List<String>` khi gọi `reversed()`, vì `List` cung cấp kiểu trả về hiệp biến. Nếu chỉ giữ collection trong biến có kiểu `Collection<String>`, phương thức `reversed()` không có trong kiểu khai báo đó; cần dùng một kiểu sequenced phù hợp.

## 2. reversed() trả về view, không tạo bản sao

Ví dụ với `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));
List<String> reverseView = names.reversed();

System.out.println(names);       // [An, Binh, Chi]
System.out.println(reverseView); // [Chi, Binh, An]
```

Hai biến tham chiếu đến hai góc nhìn của cùng một dữ liệu. `names` giữ encounter order ban đầu; `reverseView` trình bày encounter order theo chiều ngược lại.

Vì đây là view được backing collection hỗ trợ, thay đổi thông qua một phía được phản ánh ở phía còn lại:

```java
reverseView.addFirst("Dung");

System.out.println(reverseView); // [Dung, Chi, Binh, An]
System.out.println(names);       // [An, Binh, Chi, Dung]

names.removeLast();

System.out.println(names);       // [An, Binh, Chi]
System.out.println(reverseView); // [Chi, Binh, An]
```

`addFirst("Dung")` thêm phần tử vào đầu của view đảo ngược, tức cuối của list gốc. Tương tự, `removeLast()` trên list gốc loại bỏ phần tử cuối của list gốc, nên phần tử tương ứng cũng biến mất ở cuối view đảo ngược.

Nếu collection gốc hỗ trợ sửa đổi, view cũng hỗ trợ sửa đổi theo hợp đồng của collection đó. Nếu collection gốc không hỗ trợ sửa đổi, view cũng không thể được dùng để vượt qua giới hạn này; các thao tác tùy chọn không được hỗ trợ có thể ném `UnsupportedOperationException`. `reversed()` không tự biến collection bất biến thành collection có thể sửa đổi.

## 3. Hiểu ánh xạ giữa hai đầu của view và collection gốc

Với một list có encounter order:

```text
List gốc:      first  -> A -> B -> C <- last
View reversed: first  -> C -> B -> A <- last
```

Các thao tác ở đầu và cuối của view tương ứng với đầu đối diện ở collection gốc:

| Thao tác trên view đảo ngược | Tác động tương ứng lên list gốc |
|---|---|
| `getFirst()` | Đọc phần tử cuối của list gốc |
| `getLast()` | Đọc phần tử đầu của list gốc |
| `addFirst(value)` | Thêm vào cuối list gốc |
| `addLast(value)` | Thêm vào đầu list gốc |
| `removeFirst()` | Xóa phần tử cuối list gốc |
| `removeLast()` | Xóa phần tử đầu list gốc |

Ví dụ:

```java
List<String> tasks = new ArrayList<>(List.of("compile", "test", "package"));
List<String> newestFirst = tasks.reversed();

System.out.println(newestFirst.getFirst()); // package
newestFirst.addLast("prepare-release");

System.out.println(tasks); // [prepare-release, compile, test, package]
```

`addLast` của view thêm phần tử vào cuối thứ tự mà view đang trình bày. Vì thứ tự đó ngược với list gốc, phần tử mới xuất hiện ở đầu list gốc.

Đối với `List`, các thao tác theo chỉ số cũng quan sát thứ tự của view. Phần tử ở chỉ số `0` trong list đảo ngược là phần tử cuối cùng của list gốc; chỉ số cuối của view tương ứng phần tử đầu của list gốc. Các thao tác thêm, thay thế hoặc xóa theo chỉ số được thực hiện theo quy tắc vị trí của list view.

## 4. Duyệt và tạo stream theo thứ tự ngược

Iterator và các thao tác duyệt trên view sử dụng encounter order của view. Vì vậy, có thể duyệt từ phần tử cuối về đầu mà không cần tự viết vòng lặp chỉ số hoặc sao chép list rồi đảo.

```java
List<String> steps = List.of("read", "validate", "save");

for (String step : steps.reversed()) {
    System.out.println(step);
}
// save
// validate
// read
```

Stream tạo từ view cũng quan sát thứ tự của view:

```java
List<String> reverseSteps = steps.reversed().stream().toList();
System.out.println(reverseSteps); // [save, validate, read]
```

Trong ví dụ này, `toList()` tạo một list kết quả không thể sửa đổi từ stream; list kết quả là một đối tượng riêng. Điều đó không làm thay đổi bản chất của `steps.reversed()`: chính `reversed()` trả về view, còn thao tác terminal `toList()` mới tạo kết quả thu thập riêng.

## 5. reversed() với SequencedSet

`SequencedSet` là set có encounter order xác định. Các implementation có thứ tự như `LinkedHashSet` có thể cung cấp view đảo ngược thông qua `reversed()`.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

SequencedSet<String> roles = new LinkedHashSet<>();
roles.add("viewer");
roles.add("editor");
roles.add("admin");

SequencedSet<String> reverseRoles = roles.reversed();

System.out.println(reverseRoles); // [admin, editor, viewer]
```

View vẫn giữ quy tắc duy nhất phần tử của set. Nếu thêm một phần tử chưa tồn tại vào đầu view, phần tử đó được thêm vào cuối thứ tự của set gốc:

```java
reverseRoles.addFirst("owner");

System.out.println(reverseRoles); // [owner, admin, editor, viewer]
System.out.println(roles);        // [viewer, editor, admin, owner]
```

`reversed()` chỉ đảo encounter order; nó không biến một set không có thứ tự thành set có thứ tự. Ví dụ, `HashSet` không triển khai `SequencedSet`, nên không thể gọi `reversed()` trên biến có kiểu `HashSet` hoặc `Set` thông thường chỉ vì muốn xem thứ tự ngược. Hãy dùng một implementation đáp ứng hợp đồng sequenced nếu thứ tự là yêu cầu của chương trình.

## 6. reversed() với SequencedMap

`SequencedMap<K, V>` biểu diễn map có thứ tự encounter cho các mapping. `reversed()` trả về một view có thứ tự mapping ngược lại. View và map gốc chia sẻ các mapping, nên cập nhật hoặc xóa mapping qua view được phản ánh ở map gốc.

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

SequencedMap<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 8);
scores.put("Binh", 9);
scores.put("Chi", 10);

SequencedMap<String, Integer> newestScores = scores.reversed();

System.out.println(newestScores.firstEntry()); // Chi=10
System.out.println(newestScores.lastEntry());  // An=8
```

Các thao tác đầu-cuối trên view đảo ngược tương ứng với đầu đối diện của map gốc:

```java
newestScores.putFirst("Dung", 7);

System.out.println(newestScores.firstEntry()); // Dung=7
System.out.println(scores.lastEntry());         // Dung=7

newestScores.pollFirstEntry();

System.out.println(scores.containsKey("Dung")); // false
```

`putFirst` trên view đặt mapping ở đầu thứ tự của view, tương ứng cuối thứ tự của map gốc. `pollFirstEntry` trên view lấy và xóa mapping đầu tiên của view, do đó cũng xóa mapping cuối cùng của map gốc.

Khi cần duyệt riêng khóa, giá trị hoặc entry theo encounter order đảo ngược, dùng các view có thứ tự của `SequencedMap`:

```java
for (String key : newestScores.sequencedKeySet()) {
    System.out.println(key);
}

for (Integer score : newestScores.sequencedValues()) {
    System.out.println(score);
}
```

`sequencedKeySet()`, `sequencedValues()` và `sequencedEntrySet()` thể hiện thứ tự của map tương ứng. Với `newestScores`, thứ tự đó là chiều ngược so với `scores`.

`HashMap` không đảm bảo encounter order và không triển khai `SequencedMap`, vì vậy không thể dùng `reversed()` để yêu cầu một thứ tự ngược có ý nghĩa trên một `HashMap` thông thường. Khi thứ tự là một phần của yêu cầu dữ liệu, hãy chọn implementation có hợp đồng sequenced, chẳng hạn `LinkedHashMap`.

## 7. Phân biệt reversed() với Collections.reverse() và bản sao đảo ngược

Ba thao tác sau có mục đích và tác động khác nhau:

| Cách làm | Kết quả | Có thay đổi collection gốc? |
|---|---|---|
| `list.reversed()` | Trả về view có encounter order ngược | Không đảo dữ liệu gốc; view chia sẻ dữ liệu với gốc |
| `Collections.reverse(list)` | Đảo thứ tự các phần tử ngay trong list được truyền vào | Có, thay đổi list gốc tại chỗ |
| Tạo list mới rồi đảo hoặc thu thập từ view | Tạo collection kết quả độc lập | Không thay đổi thứ tự của list gốc |

Ví dụ dùng `reversed()`:

```java
List<String> original = new ArrayList<>(List.of("A", "B", "C"));
List<String> view = original.reversed();

System.out.println(original); // [A, B, C]
System.out.println(view);     // [C, B, A]
```

Ví dụ dùng `Collections.reverse()`:

```java
import java.util.Collections;

List<String> original = new ArrayList<>(List.of("A", "B", "C"));
Collections.reverse(original);

System.out.println(original); // [C, B, A]
```

`Collections.reverse()` thay đổi thứ tự trong list được truyền vào và không trả về một view. Nó yêu cầu list có thể sửa đổi. Ngược lại, `reversed()` cho phép đọc và thao tác trên thứ tự đảo ngược thông qua một view tuân theo khả năng sửa đổi của collection nền.

Nếu cần một bản sao độc lập theo thứ tự ngược, có thể thu thập từ view:

```java
List<String> original = new ArrayList<>(List.of("A", "B", "C"));
List<String> copy = new ArrayList<>(original.reversed());

copy.add("D");

System.out.println(copy);     // [C, B, A, D]
System.out.println(original); // [A, B, C]
```

Ở đây, `new ArrayList<>(...)` tạo bản sao. Các thay đổi cấu trúc trên `copy` không tác động đến `original`.

## 8. Giới hạn và lưu ý khi dùng reversed view

**View chia sẻ dữ liệu.** Không giữ view với giả định nó là snapshot tại thời điểm gọi `reversed()`. Nếu collection gốc thay đổi, view quan sát trạng thái mới theo thứ tự ngược. Tương tự, sửa đổi qua view tác động đến collection gốc.

**Khả năng sửa đổi phụ thuộc collection nền.** `reversed()` không đảm bảo mọi thao tác sửa đổi đều được hỗ trợ. Các thao tác tùy chọn như thêm hoặc xóa có thể ném `UnsupportedOperationException` nếu collection nền không hỗ trợ chúng.

**Không bổ sung thread safety.** View không tự tạo cơ chế đồng bộ hóa hoặc bảo đảm an toàn khi nhiều luồng cùng sửa collection. Hãy tuân thủ quy tắc đồng bộ hóa và giới hạn sửa đổi của implementation gốc.

**Không giả định độ phức tạp hoặc identity.** API cam kết ngữ nghĩa view và thứ tự ngược, không nên suy ra mọi implementation đều có cùng chi phí thao tác hoặc `reversed().reversed()` phải trả về đúng cùng một object theo phép so sánh `==`. Hai lần đảo khôi phục encounter order về chiều ban đầu, nhưng không nên phụ thuộc vào identity của view.

**Kiểu khai báo phải hỗ trợ API.** `reversed()` thuộc các interface sequenced. Một biến chỉ có kiểu `Collection`, `Set` hoặc `Map` không tự có phương thức này. Hãy khai báo hoặc chuyển đổi dữ liệu sang một kiểu có hợp đồng sequenced thích hợp; không ép kiểu tùy tiện nếu đối tượng thực tế không triển khai interface đó.

**Thứ tự có ý nghĩa phải được bảo đảm từ đầu.** Dùng `reversed()` khi collection đã có encounter order xác định. Nó chỉ đảo thứ tự mà implementation cung cấp, không sắp xếp theo giá trị, không tạo thứ tự theo thời gian và không thay thế thao tác sort.

## 9. Chọn cách sử dụng phù hợp

| Nhu cầu | Cách làm phù hợp |
|---|---|
| Duyệt list từ cuối về đầu mà vẫn giữ list gốc | `list.reversed()` |
| Lấy phần tử cuối của list như phần tử đầu | `list.reversed().getFirst()` hoặc `list.getLast()` |
| Thêm/xóa ở đầu view đảo ngược | Dùng `addFirst`/`removeFirst` trên view; thao tác tương ứng với cuối collection gốc |
| Duyệt set có thứ tự theo chiều ngược | `sequencedSet.reversed()` |
| Duyệt mapping từ cuối về đầu | `sequencedMap.reversed()` |
| Đảo thứ tự list gốc tại chỗ | `Collections.reverse(list)` |
| Có kết quả đảo ngược độc lập | Tạo collection mới từ `list.reversed()` |

Khi lựa chọn, hãy xác định rõ có cần một góc nhìn tạm thời hay một cấu trúc dữ liệu mới. View phù hợp khi cần truy cập cùng dữ liệu theo chiều ngược; bản sao phù hợp khi cần snapshot hoặc muốn thay đổi kết quả mà không tác động đến nguồn.

## Kết luận

Trong Java 21, `reversed()` cung cấp view có encounter order ngược cho `SequencedCollection`, `SequencedSet`, `SequencedMap` và các kiểu chuyên biệt như `List`. View chia sẻ dữ liệu với collection nền, nên thay đổi được phản ánh hai chiều; các thao tác đầu-cuối cũng đổi vị trí tương ứng. Hãy dùng view khi cần duyệt hoặc thao tác theo thứ tự ngược mà vẫn làm việc với cùng collection, và tạo bản sao riêng khi cần dữ liệu độc lập.

## Tài liệu tham khảo

- [Java SE 21 API — SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html)
- [Java SE 21 API — SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html)
- [Java SE 21 API — SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html)
- [Java SE 21 API — List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html)
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
