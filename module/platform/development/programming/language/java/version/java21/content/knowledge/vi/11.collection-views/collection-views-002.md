# Thay đổi qua reversed view và tác động đến collection gốc

Trong Java 21, `reversed()` của `SequencedCollection`, `SequencedSet`, `SequencedMap` và `List` trả về một view có encounter order ngược với đối tượng ban đầu. View này được backing bởi collection hoặc map gốc. Vì vậy, nếu implementation hỗ trợ thao tác sửa đổi, thay đổi thực hiện qua reverse view sẽ được ghi vào dữ liệu gốc; thay đổi thực hiện trên dữ liệu gốc cũng được nhìn thấy qua view.

Điểm cần nhớ khi làm việc với reverse view là **đảo hướng truy cập không tạo ra một bản sao độc lập**. Điều này ảnh hưởng đến thao tác thêm, xóa, cập nhật, iterator, stream, các view con và khả năng sửa đổi của collection. API Sequenced Collections được chuẩn hóa trong Java 21 qua [JEP 431](https://openjdk.org/jeps/431).

## 1. Reverse view là một góc nhìn được backing bởi collection gốc

Ví dụ với `List`:

```java
import java.util.ArrayList;
import java.util.List;

List<String> original = new ArrayList<>(List.of("A", "B", "C"));
List<String> reversed = original.reversed();

System.out.println(original); // [A, B, C]
System.out.println(reversed); // [C, B, A]
```

Hai biến tham chiếu đến hai góc nhìn của cùng dữ liệu. `original` có encounter order `[A, B, C]`; `reversed` quan sát cùng các phần tử theo thứ tự `[C, B, A]`.

Thay đổi qua reverse view được phản ánh vào collection gốc:

```java
reversed.set(0, "X");
System.out.println(original); // [A, B, X]
System.out.println(reversed); // [X, B, A]
```

`set(0, "X")` cập nhật phần tử đầu của view, tức phần tử cuối của danh sách gốc. Không tạo một phần tử mới; cùng một vị trí dữ liệu được quan sát từ hai hướng khác nhau.

Chiều ngược lại cũng đúng:

```java
original.set(0, "Y");
System.out.println(original); // [Y, B, X]
System.out.println(reversed); // [X, B, Y]
```

Nếu thêm hoặc xóa phần tử qua `original`, kích thước và nội dung quan sát qua `reversed` cũng thay đổi tương ứng. Gọi `reversed()` trên reverse view tạo góc nhìn theo thứ tự ban đầu; không nên dựa vào việc hai lời gọi trả về cùng một object, mà hãy dựa vào hợp đồng về encounter order và backing relationship.

## 2. Thao tác hai đầu qua view tác động đến đầu đối diện của gốc

Trên reverse view, đầu và cuối bị đảo so với collection gốc. Vì thế, thao tác ở đầu view tương ứng với thao tác ở cuối gốc, và ngược lại.

Giả sử trạng thái ban đầu:

```text
original: [A, B, C]
reversed: [C, B, A]
```

| Thao tác trên `reversed` | Tác động lên `original` | Kết quả trên `original` |
| --- | --- | --- |
| `getFirst()` | Lấy phần tử cuối | `C` |
| `getLast()` | Lấy phần tử đầu | `A` |
| `addFirst("X")` | Thêm vào cuối | `[A, B, C, X]` |
| `addLast("Y")` | Thêm vào đầu | `[Y, A, B, C]` |
| `removeFirst()` | Xóa phần tử cuối | `[A, B]` |
| `removeLast()` | Xóa phần tử đầu | `[B, C]` |

Ví dụ đầy đủ:

```java
List<String> original = new ArrayList<>(List.of("A", "B", "C"));
List<String> reversed = original.reversed();

reversed.addFirst("X");
System.out.println(original); // [A, B, C, X]

reversed.addLast("Y");
System.out.println(original); // [Y, A, B, C, X]

String removed = reversed.removeFirst();
System.out.println(removed);  // X
System.out.println(original); // [Y, A, B, C]
```

Các thao tác `getFirst()`, `getLast()`, `removeFirst()` và `removeLast()` ném `NoSuchElementException` nếu collection rỗng. `addFirst()` và `addLast()` là thao tác sửa đổi; chúng có thể ném `UnsupportedOperationException` nếu collection hoặc implementation không hỗ trợ thêm tại vị trí đó.

## 3. Thao tác theo index của `List.reversed()`

Vì `List.reversed()` trả về một `List`, có thể dùng `get(index)`, `set(index, element)`, `add(index, element)`, `remove(index)` và `subList()` trên reverse view. Index được tính theo thứ tự của view, không phải theo collection gốc.

Với danh sách gốc có `n` phần tử và chỉ số hợp lệ `i`:

- `get(i)`, `set(i, x)` và `remove(i)` trên view tương ứng với vị trí `n - 1 - i` trong danh sách gốc.
- `add(i, x)` trên view chèn trước phần tử đang ở vị trí `i` của view; vị trí chèn tương ứng trong danh sách gốc là `n - i`.

Ví dụ:

```java
List<String> original = new ArrayList<>(List.of("A", "B", "C", "D"));
List<String> reversed = original.reversed(); // [D, C, B, A]

System.out.println(reversed.get(1)); // C

reversed.set(1, "X");
System.out.println(original); // [A, B, X, D]

reversed.add(1, "Y");
System.out.println(reversed); // [D, Y, X, B, A]
System.out.println(original); // [A, B, X, Y, D]

reversed.remove(0);
System.out.println(original); // [A, B, X, Y]
```

Quy tắc index này giúp hiểu vì sao `add(i, x)` không dùng công thức `n - 1 - i`: thao tác thêm chèn vào một vị trí giữa các phần tử, còn `get`, `set` và `remove` làm việc với phần tử đã tồn tại.

`subList(fromIndex, toIndex)` trên reverse view cũng là một view. Nếu sửa đổi qua sublist và thao tác đó được hỗ trợ, thay đổi sẽ tác động đến reverse view và collection gốc. Cần tuân thủ quy tắc của `List.subList`: tránh sửa cấu trúc danh sách gốc qua một đường truy cập khác trong khi đang sử dụng sublist.

## 4. Các thao tác sửa đổi khác cũng ghi vào dữ liệu gốc

Reverse view không chỉ phản ánh các thao tác hai đầu. Mọi thao tác sửa đổi được view hỗ trợ đều tác động lên backing collection theo encounter order của view:

```java
List<String> original = new ArrayList<>(List.of("A", "B", "C", "D"));
List<String> reversed = original.reversed(); // [D, C, B, A]

reversed.remove("C");
System.out.println(original); // [A, B, D]

reversed.replaceAll(String::toLowerCase);
System.out.println(original); // [a, b, d]

reversed.sort(String.CASE_INSENSITIVE_ORDER);
System.out.println(reversed); // [a, b, d]
System.out.println(original); // [d, b, a]
```

Trong ví dụ, `remove` xóa phần tử khỏi gốc, `replaceAll` cập nhật từng phần tử của gốc, còn `sort` sắp xếp theo thứ tự của reverse view và do đó làm thay đổi encounter order nhìn thấy từ danh sách gốc.

Các phương thức như `clear()`, `removeIf()`, `removeAll()` và `retainAll()` cũng thay đổi backing collection nếu implementation hỗ trợ thao tác đó. Luôn xem thao tác đang gọi theo thứ tự của view; kết quả cuối cùng ở collection gốc có thể nhìn khác vì hướng quan sát đã đảo.

## 5. Tác động qua iterator và stream

Iterator của reverse view duyệt phần tử theo encounter order ngược. Nếu iterator hỗ trợ `remove()`, thao tác này xóa phần tử tương ứng khỏi collection gốc:

```java
List<String> original = new ArrayList<>(List.of("A", "B", "C"));

var iterator = original.reversed().iterator();
while (iterator.hasNext()) {
    if (iterator.next().equals("B")) {
        iterator.remove();
    }
}

System.out.println(original); // [A, C]
```

Không nên thay đổi cấu trúc collection gốc qua một đường truy cập khác trong lúc iterator của reverse view đang hoạt động. Với implementation fail-fast, một số thay đổi ngoài iterator có thể làm iterator ném `ConcurrentModificationException`; fail-fast chỉ là cơ chế phát hiện best-effort, không phải bảo đảm đồng bộ hoặc bảo đảm mọi thay đổi đều bị phát hiện.

Stream được tạo từ reverse view có encounter order của view. Vì vậy, các thao tác phụ thuộc thứ tự như `findFirst()`, `limit()` và `skip()` tính từ phần tử cuối của collection gốc. `toList()` tạo một danh sách kết quả độc lập và không sửa đổi được; sửa danh sách kết quả không tác động ngược lại nguồn.

```java
List<String> original = new ArrayList<>(List.of("A", "B", "C"));

String last = original.reversed().stream().findFirst().orElse("empty");
List<String> snapshot = original.reversed().stream().toList();

System.out.println(last);     // C
System.out.println(snapshot); // [C, B, A]
```

`stream()` không tạo snapshot ngay tại thời điểm gọi. Không sửa nguồn hoặc reverse view trong khi stream pipeline đang thực thi, trừ khi có hợp đồng rõ ràng cho việc đó. Với parallel stream, `forEach()` không đảm bảo hành động theo encounter order; dùng `forEachOrdered()` khi thứ tự ngược là yêu cầu của chương trình.

## 6. Ảnh hưởng với `SequencedSet`

`SequencedSet.reversed()` trả về một `SequencedSet` view có thứ tự ngược và vẫn giữ tính duy nhất của phần tử. Thêm hoặc xóa qua view được phản ánh vào set gốc nếu implementation hỗ trợ thao tác đó.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

SequencedSet<String> original = new LinkedHashSet<>();
original.add("compile");
original.add("test");
original.add("package");

SequencedSet<String> reversed = original.reversed();
reversed.addFirst("deploy");

System.out.println(reversed); // [deploy, package, test, compile]
System.out.println(original); // [compile, test, package, deploy]
```

`addFirst(e)` và `addLast(e)` của sequenced set tuân theo tính duy nhất của `Set`: nếu `e` đã có, nó được chuyển đến đầu hoặc cuối encounter order thay vì tạo phần tử trùng. Trên reverse view, chuyển phần tử đến đầu view tương đương chuyển đến cuối set gốc. Không phải mọi implementation đều hỗ trợ định vị tùy ý; `LinkedHashSet` hỗ trợ `addFirst`/`addLast`, còn `TreeSet` sắp xếp theo comparator và ném `UnsupportedOperationException` cho các thao tác định vị đầu/cuối tùy ý.

## 7. Ảnh hưởng với `SequencedMap`

`SequencedMap.reversed()` trả về reverse-ordered view được backing bởi map gốc. Thay đổi giá trị hoặc thứ tự qua view tác động đến map ban đầu. Các view có thứ tự `sequencedKeySet()`, `sequencedValues()` và `sequencedEntrySet()` cũng quan sát encounter order ngược.

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

SequencedMap<String, Integer> original = new LinkedHashMap<>();
original.put("An", 8);
original.put("Binh", 9);
original.put("Chi", 10);

SequencedMap<String, Integer> reversed = original.reversed();
reversed.putFirst("Dung", 7);
reversed.put("An", 11);

System.out.println(reversed.sequencedKeySet()); // [Dung, Chi, Binh, An]
System.out.println(original); // {An=11, Binh=9, Chi=10, Dung=7}
```

`putFirst` trên reverse view định vị entry ở đầu view, tức cuối map gốc. Cập nhật giá trị cho khóa `An` qua view cũng cập nhật mapping của khóa đó trong map gốc. Các thao tác `firstEntry`, `lastEntry`, `pollFirstEntry` và `pollLastEntry` cũng được hiểu theo encounter order của view; các thao tác poll làm xóa mapping tương ứng khỏi map gốc.

Map view cũng được backing bởi map. Chẳng hạn, xóa một khóa qua `reversed.sequencedKeySet()` sẽ xóa mapping tương ứng khỏi map gốc nếu thao tác được hỗ trợ. Không gọi `stream()` trực tiếp trên `SequencedMap`; hãy stream một trong các sequenced views của nó.

## 8. Khả năng sửa đổi, unmodifiable view và snapshot

`reversed()` không thay đổi khả năng sửa đổi của collection. Nếu collection gốc hỗ trợ thao tác sửa đổi, reverse view có thể hỗ trợ cùng thao tác; nếu collection gốc không sửa đổi được, thao tác sửa qua reverse view sẽ không thành công.

Ví dụ với collection không sửa đổi được:

```java
import java.util.List;

List<String> fixed = List.of("A", "B", "C");
List<String> reversed = fixed.reversed();

System.out.println(reversed); // [C, B, A]
reversed.addFirst("X");       // UnsupportedOperationException
```

Nếu dùng một unmodifiable wrapper quanh collection mutable, wrapper và reverse view của nó không cho sửa đổi qua view, nhưng vẫn có thể phản ánh thay đổi thực hiện trên collection backing thông qua một tham chiếu khác:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> backing = new ArrayList<>(List.of("A", "B", "C"));
List<String> protectedView = Collections.unmodifiableList(backing.reversed());

backing.add("D");
System.out.println(protectedView); // [D, C, B, A]
// protectedView.add("X"); // UnsupportedOperationException
```

`protectedView` ngăn người gọi sửa qua chính view đó, nhưng không phải snapshot độc lập. Muốn có bản sao không sửa đổi và không liên kết với nguồn, dùng `List.copyOf()`:

```java
List<String> snapshot = List.copyOf(backing.reversed());
```

`List.copyOf()` tạo danh sách không sửa đổi theo encounter order tại thời điểm gọi và ném `NullPointerException` nếu nguồn chứa phần tử `null`. Nếu cần bản sao mutable hoặc cần giữ `null`, dùng `new ArrayList<>(backing.reversed())`.

| Cách tạo | Có phản ánh thay đổi từ backing collection? | Có sửa được qua kết quả? |
| --- | --- | --- |
| `original.reversed()` | Có | Có, nếu backing collection hỗ trợ thao tác tương ứng. |
| `Collections.unmodifiableList(original.reversed())` | Có | Không qua wrapper. |
| `List.copyOf(original.reversed())` | Không | Không. |
| `new ArrayList<>(original.reversed())` | Không | Có. |

## 9. Đồng bộ và an toàn khi dùng chung

Reverse view không tự bổ sung cơ chế đồng bộ cho collection. Nếu nhiều luồng cùng truy cập backing collection, hãy tuân thủ chính sách đồng bộ của implementation gốc. Không coi việc tạo reverse view là cách tạo một collection thread-safe.

Khi đang duyệt view, tránh sửa cấu trúc backing collection từ một tham chiếu khác. Nếu cần xóa phần tử trong lúc duyệt, dùng `Iterator.remove()` khi iterator hỗ trợ. Nếu cần thêm hoặc thay đổi cấu trúc, hãy kết thúc lượt duyệt rồi thực hiện thay đổi, hoặc chọn một collection có hợp đồng đồng thời phù hợp với nhu cầu.

Đối với `Collections.synchronizedList`, tài liệu API yêu cầu đồng bộ trên list wrapper khi duyệt qua iterator, spliterator hoặc stream. Khi sử dụng reverse view của wrapper này, cần giữ đúng cơ chế đồng bộ được tài liệu của wrapper quy định và không giả định reverse view tự tạo một khóa đồng bộ mới an toàn cho mọi truy cập.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nghĩ rằng `reversed()` tạo bản sao | API trả về view được backing bởi collection gốc. | Dùng `new ArrayList<>(view)` hoặc `List.copyOf(view)` nếu cần snapshot. |
| Sửa view nhưng thấy collection gốc đổi | Hai góc nhìn chia sẻ dữ liệu. | Đây là hành vi đúng; dùng bản sao nếu cần độc lập. |
| Gọi `addFirst()` trên view nhưng phần tử xuất hiện cuối danh sách gốc | Đầu view tương ứng cuối gốc. | Quy đổi đầu/cuối theo hướng của view. |
| Index trên reverse list cho kết quả khác mong đợi | Index được tính từ đầu view. | Dùng `n - 1 - i` cho truy cập phần tử và `n - i` cho vị trí chèn. |
| Reverse view không cho thêm hoặc xóa | Collection gốc hoặc thao tác cụ thể không hỗ trợ sửa đổi. | Kiểm tra mutability và hợp đồng của implementation. |
| Unmodifiable wrapper vẫn thay đổi khi nguồn đổi | Wrapper cấm sửa qua wrapper nhưng vẫn là view sống của backing collection. | Tạo snapshot bằng `List.copyOf()` nếu cần độc lập. |
| Iterator ném `ConcurrentModificationException` | Collection bị sửa cấu trúc ngoài iterator trong lúc duyệt. | Dùng `iterator.remove()` nếu phù hợp hoặc thay đổi sau khi duyệt xong. |
| Nghĩ reverse view làm collection thread-safe | View không thay đổi chính sách đồng bộ của backing collection. | Dùng đúng cơ chế đồng bộ hoặc collection đồng thời phù hợp. |

## 11. Tài liệu tham khảo chính thức

- [Java SE 21 API — `SequencedCollection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): hợp đồng reverse-ordered view, backing relationship và các thao tác hai đầu.
- [Java SE 21 API — `List`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html): hành vi `List.reversed()`, index và các thao tác list.
- [Java SE 21 API — `SequencedSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html): thứ tự, tính duy nhất và các thao tác định vị phần tử.
- [Java SE 21 API — `SequencedMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): reverse view, map views và thao tác hai đầu.
- [Java SE 21 API — `Collections`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): unmodifiable wrappers và synchronized wrappers.
- [Java SE 21 API — `Stream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): encounter order, `findFirst`, `forEachOrdered` và `toList()`.
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431): mục tiêu thiết kế và API Sequenced Collections trong Java 21.
