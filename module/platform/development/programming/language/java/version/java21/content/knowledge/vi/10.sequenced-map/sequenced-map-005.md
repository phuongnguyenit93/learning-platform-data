# `putFirst`, `putLast` và định vị lại entry

## 1. Vai trò của `putFirst` và `putLast`

Java 21 bổ sung `SequencedMap` để biểu diễn map có **encounter order** (thứ tự duyệt) rõ ràng. Bên cạnh các thao tác đọc entry đầu/cuối như `firstEntry()` và `lastEntry()`, interface này cung cấp hai method để chủ động đặt một mapping ở đầu hoặc cuối thứ tự:

- `putFirst(key, value)`: thêm hoặc cập nhật mapping rồi đặt entry ở đầu encounter order.
- `putLast(key, value)`: thêm hoặc cập nhật mapping rồi đặt entry ở cuối encounter order.

Hai method có kiểu trả về `void`. Chúng tập trung vào việc định vị entry trong map, khác với `Map.put()` vốn trả về giá trị cũ của key nếu có.

Ví dụ với `LinkedHashMap`:

```java
SequencedMap<String, Integer> scores = new LinkedHashMap<>();

scores.putLast("An", 8);
scores.putLast("Binh", 9);
scores.putLast("Chi", 10);

System.out.println(scores);
// {An=8, Binh=9, Chi=10}

scores.putFirst("Chi", 11);
System.out.println(scores);
// {Chi=11, An=8, Binh=9}

scores.putLast("An", 12);
System.out.println(scores);
// {Chi=11, Binh=9, An=12}
```

Lần gọi đầu tiên thêm ba key mới. Lần gọi `putFirst("Chi", 11)` cập nhật value của key `Chi` và đưa entry đó lên đầu. Sau đó `putLast("An", 12)` cập nhật value của `An` và chuyển entry này xuống cuối. Map vẫn chỉ có một entry cho mỗi key.

## 2. Điều gì xảy ra khi key đã tồn tại?

`putFirst` và `putLast` xử lý cả hai tình huống:

1. **Key chưa tồn tại**: tạo mapping mới và đặt mapping ở vị trí được yêu cầu.
2. **Key đã tồn tại**: thay value cũ bằng value mới và định vị lại mapping hiện tại ở đầu hoặc cuối encounter order.

Ví dụ:

```java
SequencedMap<String, String> cache = new LinkedHashMap<>();
cache.putLast("A", "value-A");
cache.putLast("B", "value-B");
cache.putLast("C", "value-C");

cache.putFirst("B", "updated-B");

System.out.println(cache);
// {B=updated-B, A=value-A, C=value-C}
```

Key `B` không được thêm lần thứ hai. Mapping cũ được cập nhật và entry được đưa lên đầu. Điều này hữu ích khi cần đánh dấu một entry là quan trọng, đưa một mục lên đầu danh sách ưu tiên hoặc đặt một mapping ở vị trí cuối mà không phải xóa rồi chèn lại thủ công.

Nếu key đã ở đúng vị trí đầu/cuối, gọi method tương ứng vẫn cập nhật value theo quy tắc của map; thứ tự quan sát được vẫn ở vị trí đó.

## 3. Khác biệt giữa `put`, `putFirst` và `putLast`

`Map.put()` cập nhật hoặc thêm mapping theo chính sách thứ tự của implementation. Nó không cung cấp yêu cầu định vị entry ở đầu/cuối. Hai method mới của `SequencedMap` thể hiện rõ ý định đó.

```java
SequencedMap<String, Integer> map = new LinkedHashMap<>();
map.put("A", 1);
map.put("B", 2);
map.put("C", 3);

map.put("A", 10);       // Cập nhật value; không chuyển A trong insertion-order mode
System.out.println(map); // {A=10, B=2, C=3}

map.putFirst("C", 30);  // Cập nhật và đưa C lên đầu
System.out.println(map); // {C=30, A=10, B=2}

map.putLast("A", 100);  // Cập nhật và đưa A xuống cuối
System.out.println(map); // {C=30, B=2, A=100}
```

Trong ví dụ này, `LinkedHashMap` sử dụng chế độ insertion-order mặc định. Nếu tạo `LinkedHashMap` ở chế độ access-order, các thao tác truy cập entry có thể thay đổi encounter order theo chính sách truy cập. Khi dùng chế độ đó, cần tính đến các lần đọc hoặc cập nhật tiếp theo có thể làm thứ tự thay đổi sau khi đã định vị entry.

| Method | Thêm key mới | Key đã tồn tại | Mục đích chính |
|---|---|---|---|
| `put(key, value)` | Thêm theo chính sách của map | Cập nhật mapping theo chính sách của map | Thêm hoặc cập nhật mapping |
| `putFirst(key, value)` | Thêm ở đầu | Cập nhật và đặt entry ở đầu | Đưa entry lên đầu encounter order |
| `putLast(key, value)` | Thêm ở cuối | Cập nhật và đặt entry ở cuối | Đưa entry xuống cuối encounter order |

Không cần gọi `remove(key)` trước khi gọi `putFirst` hoặc `putLast`. Các method này đã xử lý trường hợp key tồn tại và thực hiện việc định vị lại entry.

## 4. Sử dụng với `LinkedHashMap`

`LinkedHashMap` là implementation phổ biến của `SequencedMap`. Nó duy trì encounter order và hỗ trợ `putFirst` cùng `putLast`.

```java
SequencedMap<String, String> navigation = new LinkedHashMap<>();

navigation.putLast("home", "/");
navigation.putLast("products", "/products");
navigation.putLast("orders", "/orders");

// Đưa trang được ghim lên đầu.
navigation.putFirst("support", "/support");

// Đưa trang mới truy cập gần đây xuống cuối.
navigation.putLast("profile", "/profile");

System.out.println(navigation.keySet());
// [support, home, products, orders, profile]
```

Đây là cách biểu diễn một menu có thứ tự tùy chỉnh, danh sách mục ưu tiên hoặc một danh sách mapping mà thứ tự được ứng dụng điều khiển. Nếu thứ tự là một phần của nghiệp vụ, `SequencedMap` giúp thể hiện ý định rõ hơn so với việc phải xây dựng lại toàn bộ map.

### 4.1. `LinkedHashMap` ở chế độ access-order

`LinkedHashMap` có thể được tạo ở chế độ insertion-order hoặc access-order. Ở chế độ access-order, thứ tự duyệt phản ánh lần truy cập gần nhất: một số thao tác như `get` có thể đưa entry được truy cập về cuối encounter order.

```java
SequencedMap<String, Integer> lru =
        new LinkedHashMap<>(16, 0.75f, true);

lru.put("A", 1);
lru.put("B", 2);
lru.put("C", 3);

lru.get("A");
System.out.println(lru.keySet());
// [B, C, A]

lru.putFirst("C", 30);
System.out.println(lru.keySet());
// [C, B, A]
```

`putFirst` và `putLast` cho phép đặt entry ở đầu/cuối một cách tường minh. Tuy nhiên, với access-order map, các thao tác truy cập sau đó vẫn có thể làm encounter order thay đổi theo chính sách LRU. Vì vậy, khi dùng `LinkedHashMap` làm cache, cần phân biệt thao tác định vị chủ động với thay đổi thứ tự do truy cập.

## 5. `putFirst` và `putLast` trên reversed view

`SequencedMap.reversed()` trả về một view có encounter order ngược với map gốc. Đây là view liên kết với map nền, không phải bản sao độc lập.

```java
SequencedMap<String, Integer> original = new LinkedHashMap<>();
original.putLast("A", 1);
original.putLast("B", 2);
original.putLast("C", 3);

SequencedMap<String, Integer> reversed = original.reversed();
System.out.println(reversed.keySet()); // [C, B, A]

reversed.putFirst("B", 20);
System.out.println(reversed.keySet()); // [B, C, A]
System.out.println(original.keySet()); // [A, C, B]
System.out.println(original.get("B")); // 20
```

`putFirst` trên reversed view đặt entry ở đầu thứ tự đảo ngược, tương ứng với cuối thứ tự của map gốc. Vì view và map gốc cùng phản ánh một mapping, value được cập nhật cũng nhìn thấy từ cả hai phía.

Tương tự:

- `reversed.putFirst(key, value)` tương ứng với `original.putLast(key, value)`.
- `reversed.putLast(key, value)` tương ứng với `original.putFirst(key, value)`.

Quy tắc này giúp xử lý thứ tự từ góc nhìn ngược mà không cần tự đảo map hoặc sao chép dữ liệu.

## 6. Vì sao `SortedMap` không hỗ trợ `putFirst` và `putLast`?

`SortedMap` và `SortedSet` xác định thứ tự dựa trên thứ tự tự nhiên hoặc comparator. Vị trí của entry được quyết định bởi key, không phải bởi yêu cầu chèn ở đầu hoặc cuối của caller.

Trong Java 21, `SortedMap` cũng là một `SequencedMap`, nhưng `putFirst` và `putLast` không được hỗ trợ. Gọi các method này trên `TreeMap` sẽ ném `UnsupportedOperationException`:

```java
SequencedMap<String, Integer> sorted = new TreeMap<>();
sorted.put("B", 2);
sorted.put("A", 1);

System.out.println(sorted.keySet()); // [A, B]

sorted.putFirst("C", 3); // UnsupportedOperationException
```

`TreeMap` vẫn hỗ trợ `put`, `remove`, `firstEntry` và `lastEntry`. Nó từ chối các method yêu cầu caller điều khiển vị trí entry vì điều đó mâu thuẫn với thứ tự do comparator quyết định.

Nếu nghiệp vụ cần thứ tự tùy chỉnh theo thao tác, hãy chọn implementation hỗ trợ như `LinkedHashMap`. Nếu cần thứ tự sắp xếp theo key, hãy dùng `TreeMap` và để comparator xác định vị trí.

## 7. Các trường hợp không hỗ trợ hoặc đầu vào không hợp lệ

`putFirst` và `putLast` là thao tác thay đổi map. Kết quả phụ thuộc vào implementation và các ràng buộc của map.

| Tình huống | Kết quả có thể gặp |
|---|---|
| Map hỗ trợ thay đổi thứ tự, chẳng hạn `LinkedHashMap` | Mapping được thêm/cập nhật và đặt ở đầu/cuối |
| Map không hỗ trợ thao tác định vị, chẳng hạn `TreeMap` | `UnsupportedOperationException` |
| Map không cho phép key `null` nhưng caller truyền key `null` | `NullPointerException` |
| Map không cho phép value `null` nhưng caller truyền value `null` | `NullPointerException` |
| Key không tương thích với kiểu hoặc comparator của map | Có thể ném `ClassCastException` |
| Map là unmodifiable map hoặc unmodifiable sequenced view | `UnsupportedOperationException` |

Không nên bắt `UnsupportedOperationException` rồi bỏ qua. Nếu việc định vị entry là yêu cầu bắt buộc, hãy chọn implementation hỗ trợ ngay từ đầu hoặc để exception được truyền lên để caller xử lý đúng.

## 8. Kết hợp với unmodifiable `SequencedMap`

Java 21 cung cấp `Collections.unmodifiableSequencedMap(map)` để tạo view không cho phép thay đổi mapping qua view đó. Các thao tác như `put`, `putFirst`, `putLast`, `remove`, `pollFirstEntry` và `pollLastEntry` đều không được phép qua wrapper này.

```java
SequencedMap<String, Integer> source = new LinkedHashMap<>();
source.putLast("A", 1);
source.putLast("B", 2);

SequencedMap<String, Integer> readOnly =
        Collections.unmodifiableSequencedMap(source);

System.out.println(readOnly.firstEntry()); // A=1
readOnly.putFirst("C", 3);                // UnsupportedOperationException
```

Đây là unmodifiable view. Nếu code vẫn giữ tham chiếu đến `source`, thay đổi trực tiếp trên `source` có thể được quan sát qua `readOnly`. Wrapper ngăn sửa đổi thông qua view; nó không làm cho map nền trở nên bất biến.

Nếu cần tạo một map mới có thể thay đổi độc lập, hãy sao chép:

```java
SequencedMap<String, Integer> copy = new LinkedHashMap<>(source);
copy.putFirst("C", 3);
```

Constructor của `LinkedHashMap` sao chép các mapping từ map nguồn theo encounter order của nguồn. Bản sao sau đó có thể được định vị lại mà không thay đổi map ban đầu.

## 9. Khi nào nên sử dụng `putFirst` và `putLast`?

Hai method phù hợp khi encounter order có ý nghĩa nghiệp vụ và ứng dụng cần thay đổi vị trí entry một cách trực tiếp:

- Đưa một mục được ghim lên đầu menu hoặc danh sách điều hướng.
- Đưa một entry mới vào cuối lịch sử thao tác.
- Cập nhật một key hiện có và đồng thời chuyển nó lên đầu/cuối danh sách.
- Quản lý thứ tự ưu tiên trong một map insertion-order.
- Làm việc với reversed view mà vẫn thao tác theo góc nhìn hiện tại.

Không nên dùng `putFirst` hoặc `putLast` khi thứ tự cần được quyết định bởi comparator, hoặc khi map chỉ cung cấp quyền đọc. Trong những trường hợp đó, hãy chọn `TreeMap`, unmodifiable map hoặc một API phù hợp với hợp đồng dữ liệu.

Trước khi gọi method, hãy xác định:

1. Kiểu thực tế của map có hỗ trợ định vị entry không?
2. Key đã tồn tại chưa, và nếu tồn tại thì có chủ đích cập nhật value hay không?
3. Thứ tự là insertion-order, access-order hay sorted-order?
4. Đang thao tác trên map gốc hay reversed view?
5. Map có cho phép null key/value và có cho phép thay đổi không?

## 10. Tài liệu tham khảo chính thức

- [Java SE 21 API — `SequencedMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): hợp đồng của `putFirst`, `putLast`, reversed view và các sequenced views.
- [Java SE 21 API — `LinkedHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): hỗ trợ định vị entry, insertion-order và access-order.
- [Java SE 21 API — `SortedMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html): thứ tự theo comparator và giới hạn của các thao tác đầu/cuối.
- [Java SE 21 API — `TreeMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html): implementation sorted map và các thao tác không hỗ trợ.
- [Java SE 21 API — `Collections.unmodifiableSequencedMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableSequencedMap(java.util.SequencedMap)): tạo view không cho phép sửa đổi sequenced map.
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431): mục tiêu thiết kế và các interface sequenced được bổ sung trong Java 21.

`putFirst` và `putLast` giúp điều khiển encounter order của mapping mà không phải xóa rồi thêm lại bằng nhiều bước. Hãy nhớ rằng key đã tồn tại sẽ được cập nhật và định vị lại; khả năng này phụ thuộc implementation. `LinkedHashMap` hỗ trợ thao tác, còn `TreeMap` và unmodifiable sequenced map từ chối vì thứ tự hoặc hợp đồng của chúng không cho phép thay đổi vị trí theo yêu cầu caller.
