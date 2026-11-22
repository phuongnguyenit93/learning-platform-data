# Tạo sequenced set bằng `Collections.newSequencedSetFromMap`

## 1. Mục đích của `newSequencedSetFromMap`

Java 21 bổ sung `Collections.newSequencedSetFromMap(SequencedMap<E, Boolean> map)` để tạo một **`SequencedSet` được backing bởi một `SequencedMap`**. Set sử dụng key của map làm phần tử và lưu `Boolean.TRUE` làm value tương ứng. Thứ tự encounter của set được lấy từ thứ tự của các key trong map.

Factory này hữu ích khi ứng dụng cần các đặc tính của set (không chứa phần tử trùng lặp theo quy tắc key của map) đồng thời muốn kiểm soát thứ tự phần tử thông qua một sequenced map.

Ví dụ cơ bản:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.SequencedMap;
import java.util.SequencedSet;

static SequencedSet<String> createTags() {
    SequencedMap<String, Boolean> backing = new LinkedHashMap<>();
    return Collections.newSequencedSetFromMap(backing);
}
```

`LinkedHashMap` duy trì encounter order và hỗ trợ các thao tác định vị entry ở đầu/cuối. Set được trả về vì vậy có thể dùng các method của `SequencedSet`, bao gồm `addFirst`, `addLast`, `getFirst`, `getLast` và `reversed`.

## 2. Hợp đồng của backing map

`newSequencedSetFromMap` có một số yêu cầu quan trọng:

1. Tham số phải là một `SequencedMap<E, Boolean>` khác `null`.
2. Map phải rỗng tại thời điểm gọi factory. Nếu map không rỗng, factory ném `IllegalArgumentException`.
3. Set được trả về dùng map đã truyền vào làm backing storage; factory không tạo một bản sao độc lập của map.
4. Các phần tử set được lưu làm key, với value tương ứng là `Boolean.TRUE`.
5. Sau khi factory trả về, không nên truy cập trực tiếp backing map. Hãy thao tác thông qua `SequencedSet` để giữ nhất quán giữa hợp đồng của set và map.

Ví dụ hợp lệ:

```java
SequencedMap<String, Boolean> backing = new LinkedHashMap<>();
SequencedSet<String> tags =
        Collections.newSequencedSetFromMap(backing);

tags.add("java");
tags.add("collections");
```

Ví dụ không hợp lệ vì map đã có entry:

```java
SequencedMap<String, Boolean> backing = new LinkedHashMap<>();
backing.put("java", Boolean.TRUE);

SequencedSet<String> tags =
        Collections.newSequencedSetFromMap(backing); // IllegalArgumentException
```

Factory yêu cầu map rỗng để bắt đầu với một set rỗng và kiểm soát toàn bộ các mapping được tạo ra sau đó. Không dùng factory như cách chuyển đổi một map đã có dữ liệu thành set; nếu cần chuyển dữ liệu, hãy tạo backing map mới rồi thêm các key mong muốn thông qua set.

### 2.1. Không sử dụng backing map sau khi tạo set

Mặc dù biến map vẫn có thể còn trong scope, tài liệu API khuyến nghị không truy cập map trực tiếp sau khi đã truyền nó vào factory. Nếu sửa map qua alias, các mapping có thể không còn tuân thủ quy ước mà set sử dụng.

Ví dụ, không nên viết:

```java
SequencedMap<String, Boolean> backing = new LinkedHashMap<>();
SequencedSet<String> tags =
        Collections.newSequencedSetFromMap(backing);

backing.put("manual", Boolean.FALSE); // Không thao tác backing map trực tiếp
```

Hãy chỉ giữ và chia sẻ tham chiếu `SequencedSet` sau khi tạo. Nếu cần đóng gói việc tạo set, có thể đặt factory trong một method riêng và không để backing map thoát ra ngoài:

```java
static SequencedSet<String> newOrderedTags() {
    SequencedMap<String, Boolean> backing = new LinkedHashMap<>();
    return Collections.newSequencedSetFromMap(backing);
}
```

## 3. Thứ tự encounter của set

Set được tạo từ map kế thừa thứ tự key của backing map. Vì vậy, lựa chọn implementation cho map quyết định cách set duy trì thứ tự.

```java
SequencedSet<String> tags = newOrderedTags();

tags.addLast("backend");
tags.addLast("java");
tags.addFirst("important");

System.out.println(tags);
// [important, backend, java]
System.out.println(tags.getFirst()); // important
System.out.println(tags.getLast());  // java
```

Với backing map là `LinkedHashMap`, thứ tự có thể được điều khiển theo thao tác thêm ở đầu/cuối. `add` thông thường thêm phần tử mới theo chính sách encounter order của map; `addFirst` và `addLast` thể hiện rõ vị trí cần đặt.

`SequencedSet` vẫn là một `Set`. Vì vậy, thứ tự ảnh hưởng đến việc duyệt và các thao tác đầu/cuối, nhưng quy tắc equality của Set không biến thành so sánh theo thứ tự. Hai set có cùng phần tử vẫn có thể bằng nhau dù encounter order khác nhau.

## 4. `reversed()` tạo view có thứ tự ngược

Vì factory trả về `SequencedSet`, ta có thể gọi `reversed()` để lấy view có encounter order ngược với set gốc:

```java
SequencedSet<String> tags = newOrderedTags();
tags.addLast("A");
tags.addLast("B");
tags.addLast("C");

SequencedSet<String> reverseView = tags.reversed();
System.out.println(reverseView); // [C, B, A]

reverseView.addFirst("D");
System.out.println(tags);        // [A, B, C, D]
```

`reversed()` trả về view liên kết với set gốc, không phải bản sao. Thao tác trên view được phản ánh vào set ban đầu theo góc nhìn thứ tự tương ứng. Trong ví dụ, thêm `D` vào đầu view đảo ngược tương ứng với thêm `D` vào cuối set gốc.

Nếu cần một set độc lập, hãy tạo một backing map mới và thêm các phần tử từ view vào set mới. Không nhầm reversed view với snapshot.

## 5. Lựa chọn backing map

Không phải mọi `SequencedMap` đều cho phép thay đổi encounter order. Hãy chọn map theo yêu cầu của set.

| Backing map | Thứ tự set nhận được | Hành vi với thao tác đầu/cuối |
|---|---|---|
| `LinkedHashMap` | Thứ tự duy trì theo insertion/access và các thao tác định vị | Hỗ trợ `addFirst`/`addLast` thông qua map backing |
| `TreeMap` | Thứ tự theo key tự nhiên hoặc comparator | `addFirst`/`addLast` không được hỗ trợ; ném `UnsupportedOperationException` |
| Unmodifiable `SequencedMap` | Giữ thứ tự của map nguồn | Các thao tác thay đổi set không được hỗ trợ |

### 5.1. Dùng `LinkedHashMap` khi cần thứ tự tùy chỉnh

Đây là lựa chọn phù hợp khi ứng dụng cần điều khiển thứ tự phần tử:

```java
static SequencedSet<String> newLinkedSequencedSet() {
    return Collections.newSequencedSetFromMap(new LinkedHashMap<>());
}

SequencedSet<String> recent = newLinkedSequencedSet();
recent.addLast("file-a");
recent.addLast("file-b");
recent.addFirst("pinned-file");
```

### 5.2. Dùng `TreeMap` khi thứ tự phải được sắp xếp

`TreeMap` cũng triển khai `SequencedMap`, vì `SortedMap` trong Java 21 có thứ tự encounter được xác định bởi comparator. Tuy nhiên, thứ tự này do key quyết định. Các thao tác `putFirst` và `putLast` của `SortedMap` không được hỗ trợ, do đó các thao tác `addFirst` và `addLast` của set backing bởi `TreeMap` cũng không thể dùng để ép vị trí.

```java
SequencedSet<String> sortedNames =
        Collections.newSequencedSetFromMap(new TreeMap<>());

sortedNames.add("Charlie");
sortedNames.add("An");
sortedNames.add("Binh");

System.out.println(sortedNames); // [An, Binh, Charlie]

sortedNames.addFirst("Duy"); // UnsupportedOperationException
```

Thao tác `add` thông thường vẫn hoạt động và thứ tự được duy trì theo key. Nếu cần vị trí đầu/cuối do ứng dụng quyết định, dùng `LinkedHashMap` thay vì map sắp xếp.

## 6. Khả năng thay đổi và `UnsupportedOperationException`

Factory không tự làm cho backing map có thể thay đổi. Các thao tác của set được hỗ trợ hay không phụ thuộc vào map được truyền vào.

- Với backing map mutable như `LinkedHashMap`, thêm và xóa phần tử được hỗ trợ; các thao tác định vị đầu/cuối cũng được hỗ trợ.
- Với backing map có thứ tự sắp xếp như `TreeMap`, thêm/xóa thông thường được hỗ trợ nhưng định vị đầu/cuối không được hỗ trợ.
- Với backing map unmodifiable, các thao tác làm thay đổi set có thể ném `UnsupportedOperationException`.

Ví dụ dùng unmodifiable backing map:

```java
SequencedMap<String, Boolean> readOnlyMap =
        Collections.unmodifiableSequencedMap(new LinkedHashMap<>());

SequencedSet<String> readOnlySet =
        Collections.newSequencedSetFromMap(readOnlyMap);

System.out.println(readOnlySet.isEmpty()); // true
readOnlySet.add("java");                  // UnsupportedOperationException
```

Set có thể được tạo vì backing map đang rỗng và có kiểu phù hợp, nhưng không thể thêm phần tử qua set vì map không cho phép thay đổi.

## 7. Ràng buộc về key và tính duy nhất

Vì set dùng key của map để lưu phần tử, các quy tắc về key của backing map cũng áp dụng cho set:

- Khả năng chấp nhận `null` phụ thuộc map. `LinkedHashMap` cho phép một key `null`; `TreeMap` với natural ordering không chấp nhận key `null`.
- Quy tắc xác định key trùng lặp phụ thuộc vào cách map xác định hai key tương đương. Với map hash-based, điều đó dựa trên `equals` và `hashCode`; với sorted map, comparator hoặc thứ tự tự nhiên quyết định vị trí và tính tương đương.
- Nếu dùng comparator, nên bảo đảm comparator nhất quán với `equals` để giữ đúng kỳ vọng chung của hợp đồng `Set`.

Ví dụ với `LinkedHashMap`, thêm cùng một phần tử lần thứ hai không tạo thêm một phần tử thứ hai:

```java
SequencedSet<String> values = newOrderedTags();

boolean first = values.add("java");
boolean second = values.add("java");

System.out.println(first);  // true
System.out.println(second); // false
System.out.println(values); // [java]
```

Factory không thay đổi quy tắc equality của key. Hãy chọn backing map có semantics phù hợp với cách ứng dụng định nghĩa hai phần tử là giống nhau.

## 8. So sánh với `newSetFromMap`

`Collections.newSetFromMap(Map<E, Boolean>)` là factory đã có từ các phiên bản Java trước để tạo `Set` backed bởi một `Map`. Factory mới `newSequencedSetFromMap(SequencedMap<E, Boolean>)` phục vụ trường hợp cần thêm hợp đồng encounter order và API `SequencedSet`.

| Factory | Kiểu đầu vào | Kiểu kết quả | Khi nên dùng |
|---|---|---|---|
| `Collections.newSetFromMap(map)` | `Map<E, Boolean>` | `Set<E>` | Cần set backed bởi map nhưng không cần API sequenced |
| `Collections.newSequencedSetFromMap(map)` | `SequencedMap<E, Boolean>` | `SequencedSet<E>` | Cần set backed bởi map và cần encounter order cùng thao tác đầu/cuối |

`newSetFromMap` vẫn là API hợp lệ; nó không bị deprecated. Khi yêu cầu của ứng dụng là sequenced set, hãy dùng factory mới để kiểu trả về thể hiện đúng khả năng cần thiết.

## 9. Các lưu ý khi thiết kế

1. **Truyền map rỗng**: không dùng backing map đã chứa dữ liệu.
2. **Không truy cập map trực tiếp sau factory**: thao tác qua set để giữ quy ước lưu trữ.
3. **Chọn implementation đúng thứ tự**: dùng `LinkedHashMap` khi cần điều khiển encounter order; dùng `TreeMap` khi thứ tự sắp xếp là yêu cầu chính.
4. **Kiểm tra khả năng thay đổi**: factory không đảm bảo backing map mutable.
5. **Hiểu view**: `reversed()` trả về view liên kết, không tạo bản sao.
6. **Xác định semantics của key**: null, equality và comparator đến từ map backing.
7. **Đừng nhầm set với map**: caller làm việc với phần tử; `Boolean.TRUE` chỉ là chi tiết biểu diễn nội bộ.

## 10. Tài liệu tham khảo chính thức

- [Java SE 21 API — `Collections.newSequencedSetFromMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#newSequencedSetFromMap(java.util.SequencedMap)): hợp đồng factory, yêu cầu map rỗng và quan hệ backing.
- [Java SE 21 API — `SequencedSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html): encounter order, thao tác đầu/cuối và reversed view.
- [Java SE 21 API — `SequencedMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): thứ tự entry và thao tác định vị map.
- [Java SE 21 API — `LinkedHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): implementation map duy trì encounter order.
- [Java SE 21 API — `TreeMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html): map sắp xếp theo key và giới hạn thao tác định vị.
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431): mục tiêu và thiết kế các sequenced collection được đưa vào Java 21.

`Collections.newSequencedSetFromMap` tạo một set có thứ tự bằng cách dùng key của một sequenced map làm phần tử. Map phải rỗng khi gọi factory và không nên được truy cập trực tiếp sau đó. Muốn điều khiển vị trí đầu/cuối, chọn backing map như `LinkedHashMap`; nếu dùng map sắp xếp hoặc unmodifiable map, các thao tác định vị hoặc thay đổi tương ứng sẽ không được hỗ trợ.
