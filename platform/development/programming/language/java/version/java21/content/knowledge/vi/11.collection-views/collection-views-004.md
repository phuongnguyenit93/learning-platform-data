# Tạo `unmodifiableSequencedCollection`, `unmodifiableSequencedSet` và `unmodifiableSequencedMap`

## Mục tiêu

Java 21 bổ sung các phương thức `Collections.unmodifiableSequencedCollection()`, `Collections.unmodifiableSequencedSet()` và `Collections.unmodifiableSequencedMap()` để tạo view không cho phép sửa đổi trên các sequenced collection. Các view này giữ nguyên hợp đồng encounter order của collection nền, đồng thời chặn thao tác thay đổi thông qua tham chiếu view.

Điểm quan trọng là **unmodifiable view không đồng nghĩa với immutable snapshot**. Nếu code vẫn giữ tham chiếu đến collection nền và sửa nó, thay đổi đó vẫn xuất hiện khi đọc qua view. Bài học này hướng dẫn tạo ba loại view, sử dụng API đầu/cuối và chiều đảo ngược, xử lý các đường sửa đổi gián tiếp, và tạo bản sao có thứ tự khi cần dữ liệu độc lập.

## 1. Sequenced collections và unmodifiable view

Java 21 đưa vào các interface có encounter order rõ ràng:

- `SequencedCollection<E>` biểu diễn collection có thứ tự duyệt xác định và hỗ trợ thao tác ở đầu/cuối.
- `SequencedSet<E>` bổ sung tính duy nhất của `Set` cho collection có thứ tự.
- `SequencedMap<K, V>` biểu diễn map có thứ tự encounter của các ánh xạ và cung cấp view theo thứ tự cho key, value và entry.

Các phương thức unmodifiable tương ứng nằm trong `java.util.Collections`:

| Phương thức | Kiểu trả về | Đối tượng nền cần truyền vào |
|---|---|---|
| `unmodifiableSequencedCollection(collection)` | `SequencedCollection<E>` | Một `SequencedCollection` |
| `unmodifiableSequencedSet(set)` | `SequencedSet<E>` | Một `SequencedSet` |
| `unmodifiableSequencedMap(map)` | `SequencedMap<K, V>` | Một `SequencedMap` |

Các phương thức này có trong Java 21 và là API ổn định, không cần bật preview feature. Chúng tạo wrapper để người dùng đọc dữ liệu theo hợp đồng sequenced nhưng không thể thay đổi cấu trúc qua wrapper.

## 2. Tạo unmodifiable sequenced collection

`Collections.unmodifiableSequencedCollection()` nhận một `SequencedCollection` và trả về view không cho phép sửa collection qua view đó.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.SequencedCollection;

class UnmodifiableSequencedCollectionExample {
    public static void main(String[] args) {
        SequencedCollection<String> source =
                new ArrayList<>(List.of("Java", "Kotlin", "Scala"));

        SequencedCollection<String> view =
                Collections.unmodifiableSequencedCollection(source);

        System.out.println(view);           // [Java, Kotlin, Scala]
        System.out.println(view.getFirst()); // Java
        System.out.println(view.getLast());  // Scala

        // view.add("Groovy"); // UnsupportedOperationException
    }
}
```

`view` vẫn có thể được dùng để đọc, duyệt, kiểm tra kích thước và truy cập phần tử ở hai đầu. Các thao tác làm thay đổi collection như `add`, `addFirst`, `addLast`, `remove`, `removeFirst`, `removeLast`, `clear` hoặc `removeIf` sẽ ném `UnsupportedOperationException` khi được gọi qua view.

Vì kiểu trả về là `SequencedCollection`, code có thể dùng các API như `getFirst()`, `getLast()` và `reversed()` mà không cần biết collection nền là `ArrayList` hay một implementation sequenced khác.

## 3. Tạo unmodifiable sequenced set

Khi cần vừa giữ encounter order vừa bảo đảm phần tử không trùng lặp, dùng `Collections.unmodifiableSequencedSet()`:

```java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;

class UnmodifiableSequencedSetExample {
    public static void main(String[] args) {
        SequencedSet<String> source =
                new LinkedHashSet<>(List.of("red", "green", "blue"));

        SequencedSet<String> view =
                Collections.unmodifiableSequencedSet(source);

        System.out.println(view);            // [red, green, blue]
        System.out.println(view.getFirst()); // red
        System.out.println(view.getLast());  // blue

        // view.addFirst("black"); // UnsupportedOperationException
        // view.addLast("white");  // UnsupportedOperationException
    }
}
```

`LinkedHashSet` là lựa chọn phù hợp khi cần thứ tự chèn. Wrapper giữ nguyên encounter order của set nền và chặn các thao tác thay đổi thông qua view, bao gồm `add`, `addFirst`, `addLast`, `remove`, `removeFirst`, `removeLast`, `clear` và các thao tác xóa theo điều kiện.

Set vẫn tuân theo quy tắc duy nhất dựa trên `equals()` và `hashCode()`. Wrapper không thay đổi cách xác định hai phần tử trùng nhau; nó chỉ giới hạn khả năng sửa đổi qua tham chiếu view.

## 4. Tạo unmodifiable sequenced map

`Collections.unmodifiableSequencedMap()` tạo view không cho phép sửa một `SequencedMap`. Với `LinkedHashMap`, encounter order mặc định là thứ tự chèn:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.SequencedMap;

class UnmodifiableSequencedMapExample {
    public static void main(String[] args) {
        SequencedMap<String, Integer> source = new LinkedHashMap<>();
        source.put("An", 85);
        source.put("Binh", 92);
        source.put("Chi", 78);

        SequencedMap<String, Integer> view =
                Collections.unmodifiableSequencedMap(source);

        System.out.println(view);                 // {An=85, Binh=92, Chi=78}
        System.out.println(view.firstEntry());    // An=85
        System.out.println(view.lastEntry());     // Chi=78
        System.out.println(view.sequencedKeySet()); // [An, Binh, Chi]

        // view.put("Dung", 90);       // UnsupportedOperationException
        // view.putFirst("Dung", 90);  // UnsupportedOperationException
        // view.putLast("Dung", 90);   // UnsupportedOperationException
    }
}
```

Ngoài các phương thức `put`, `remove`, `clear` và các thao tác cập nhật map thông thường, wrapper cũng chặn các phương thức thay đổi thứ tự hoặc nội dung của sequenced map như `putFirst`, `putLast`, `pollFirstEntry` và `pollLastEntry`.

Các view `sequencedKeySet()`, `sequencedValues()` và `sequencedEntrySet()` cũng không cho phép sửa map nền thông qua những view đó. Entry lấy qua các view này không cho phép gọi `setValue()` để thay đổi giá trị trong map.

## 5. View đảo ngược vẫn giữ giới hạn unmodifiable

Các interface sequenced cung cấp `reversed()` để tạo view có encounter order đảo ngược. Khi gọi qua unmodifiable wrapper, view đảo ngược vẫn được bảo vệ khỏi thao tác sửa đổi:

```java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;

class UnmodifiableReversedViewExample {
    public static void main(String[] args) {
        SequencedSet<String> source =
                new LinkedHashSet<>(List.of("A", "B", "C"));
        SequencedSet<String> view =
                Collections.unmodifiableSequencedSet(source);

        SequencedSet<String> reversed = view.reversed();
        System.out.println(reversed); // [C, B, A]

        // reversed.removeFirst(); // UnsupportedOperationException
        // reversed.addLast("D"); // UnsupportedOperationException
    }
}
```

`reversed()` thay đổi hướng encounter order, không tạo một collection độc lập. View đảo ngược vẫn liên kết với collection nền và vẫn không cho phép sửa qua wrapper. Nếu collection nền thay đổi qua một tham chiếu khác, cả view gốc và view đảo ngược đều phản ánh thứ tự mới tương ứng.

Tương tự, `SequencedMap.reversed()` cho phép đọc map theo thứ tự ngược. Các view key, value và entry vẫn là view không thể dùng để sửa map thông qua unmodifiable wrapper.

## 6. Unmodifiable view không phải immutable snapshot

Đây là khác biệt quan trọng nhất khi sử dụng các phương thức `Collections.unmodifiable...`. Wrapper không sao chép collection nền. Nếu bên gọi vẫn giữ tham chiếu gốc, mọi thay đổi qua tham chiếu đó sẽ được nhìn thấy qua view.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.SequencedCollection;

class BackedViewExample {
    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("A", "B"));
        SequencedCollection<String> view =
                Collections.unmodifiableSequencedCollection(source);

        source.add("C");
        System.out.println(view); // [A, B, C]

        // view.add("D"); // UnsupportedOperationException
    }
}
```

`view` không thể tự thêm `D`, nhưng `source` vẫn có thể thêm `C`; vì thế `view` hiển thị `C`. Đây là một **read-only view có liên kết với collection nền**, không phải bản sao bất biến tách biệt.

Nếu muốn dữ liệu có cấu trúc độc lập với nguồn, hãy sao chép trước rồi mới bọc wrapper:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.SequencedCollection;

class SequencedCollectionSnapshotExample {
    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("A", "B"));
        SequencedCollection<String> snapshot =
                Collections.unmodifiableSequencedCollection(new ArrayList<>(source));

        source.add("C");
        System.out.println(snapshot); // [A, B]
    }
}
```

Với set và map, dùng implementation có thứ tự như `LinkedHashSet` và `LinkedHashMap` khi cần giữ encounter order:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedMap;
import java.util.SequencedSet;

class OrderedSnapshotExamples {
    public static void main(String[] args) {
        SequencedSet<String> sourceSet =
                new LinkedHashSet<>(List.of("A", "B"));

        SequencedMap<String, Integer> sourceMap = new LinkedHashMap<>();
        sourceMap.put("A", 1);
        sourceMap.put("B", 2);

        SequencedSet<String> setSnapshot =
                Collections.unmodifiableSequencedSet(new LinkedHashSet<>(sourceSet));
        SequencedMap<String, Integer> mapSnapshot =
                Collections.unmodifiableSequencedMap(new LinkedHashMap<>(sourceMap));

        System.out.println(setSnapshot);
        System.out.println(mapSnapshot);
    }
}
```

Các bản sao này độc lập về cấu trúc với collection nguồn. Đây vẫn là **sao chép nông (shallow copy)**: nếu phần tử của set, key/value của map hoặc object trong collection có trạng thái mutable, các object đó vẫn có thể được thay đổi qua tham chiếu khác. Muốn có dữ liệu bất biến sâu, cần dùng phần tử bất biến hoặc thực hiện sao chép sâu phù hợp với mô hình dữ liệu.

## 7. Các đường sửa đổi gián tiếp cần chú ý

Khi review một unmodifiable view, không chỉ kiểm tra các lời gọi `add()` hoặc `put()`. Cần kiểm tra mọi đường có thể làm thay đổi cấu trúc hoặc entry:

| Đối tượng | Đường sửa đổi bị chặn qua view |
|---|---|
| `SequencedCollection` | `add`, `addFirst`, `addLast`, `remove`, `removeFirst`, `removeLast`, `clear`, `removeIf`, `Iterator.remove` |
| `SequencedSet` | Các thao tác sửa đổi của `Set` và `SequencedCollection`, bao gồm thêm/xóa ở hai đầu |
| `SequencedMap` | `put`, `putFirst`, `putLast`, `remove`, `clear`, `replace`, `replaceAll`, `compute`, `merge`, `pollFirstEntry`, `pollLastEntry` |
| Map views | Thao tác sửa đổi qua `sequencedKeySet`, `sequencedValues`, `sequencedEntrySet`; `Map.Entry.setValue` trên entry được trả về |

Các thao tác mutator được gọi trên unmodifiable wrapper sẽ ném `UnsupportedOperationException`, kể cả khi lời gọi không làm thay đổi nội dung thực tế. Không nên dựa vào việc thêm một phần tử đã tồn tại hoặc xóa một phần tử không có trong set/map để tránh ngoại lệ.

Ví dụ, không thể dùng iterator để xóa phần tử từ view:

```java
import java.util.SequencedCollection;

class IteratorMutationAttempt {
    static void removeFirst(SequencedCollection<String> view) {
        var iterator = view.iterator();
        if (iterator.hasNext()) {
            iterator.next();
            // iterator.remove(); // UnsupportedOperationException
        }
    }
}
```

Với map, cũng không thể sửa value thông qua entry được lấy từ view:

```java
import java.util.SequencedMap;

class EntryMutationAttempt {
    static void changeFirst(SequencedMap<String, Integer> view) {
        var entry = view.sequencedEntrySet().getFirst();
        // entry.setValue(100); // UnsupportedOperationException
    }
}
```

## 8. Chọn đúng phương thức wrapper

Hãy chọn phương thức dựa trên hợp đồng kiểu dữ liệu mà code cần công khai:

| Nhu cầu | Nên dùng |
|---|---|
| Collection có thứ tự, cho phép phần tử trùng lặp | `unmodifiableSequencedCollection()` |
| Set có thứ tự, không cho phần tử trùng lặp | `unmodifiableSequencedSet()` |
| Map có thứ tự cho các cặp key-value | `unmodifiableSequencedMap()` |
| Chỉ cần một danh sách không thể sửa đổi và muốn bản sao cấu trúc | Có thể cân nhắc `List.copyOf()` |
| Cần set/map snapshot có thứ tự chèn | Sao chép sang `LinkedHashSet`/`LinkedHashMap`, sau đó bọc bằng unmodifiable sequenced wrapper |

Không truyền một `Set` bất kỳ vào `unmodifiableSequencedSet()` nếu nó không triển khai `SequencedSet`; tương tự, map phải là `SequencedMap` và collection phải là `SequencedCollection`. Nếu nguồn chưa có hợp đồng sequenced, hãy chọn hoặc chuyển đổi sang implementation có thứ tự trước khi bọc.

## 9. Giới hạn về thread safety và tính bất biến

Unmodifiable wrapper chỉ giới hạn thao tác thông qua wrapper. Nó không:

- Làm collection nền trở nên bất biến nếu nơi khác vẫn giữ tham chiếu mutable.
- Làm các phần tử, key hoặc value trở thành immutable.
- Tự đồng bộ hóa truy cập giữa nhiều thread.
- Ngăn một thread khác thay đổi collection nền qua tham chiếu riêng.

Nếu collection nền được chia sẻ giữa nhiều thread và có thể bị thay đổi, cần thiết kế đồng bộ hóa phù hợp cho cả việc cập nhật lẫn truy cập. Unmodifiable wrapper không phải cơ chế thay thế cho lock, concurrent collection hoặc quy tắc xuất bản dữ liệu an toàn.

## 10. Ví dụ tổng hợp: công khai cấu hình chỉ đọc có thứ tự

Một class có thể giữ collection mutable nội bộ để xây dựng dữ liệu, nhưng chỉ công khai các unmodifiable sequenced view cho phần còn lại của ứng dụng:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.SequencedMap;
import java.util.SequencedSet;

class ApplicationCatalog {
    private final LinkedHashSet<String> featureNames = new LinkedHashSet<>();
    private final LinkedHashMap<String, Integer> limits = new LinkedHashMap<>();

    private final SequencedSet<String> featureView =
            Collections.unmodifiableSequencedSet(featureNames);
    private final SequencedMap<String, Integer> limitView =
            Collections.unmodifiableSequencedMap(limits);

    void addFeature(String name) {
        featureNames.add(name);
    }

    void setLimit(String name, int limit) {
        limits.put(name, limit);
    }

    SequencedSet<String> features() {
        return featureView;
    }

    SequencedMap<String, Integer> limits() {
        return limitView;
    }
}
```

Class này kiểm soát các thao tác ghi qua method `addFeature()` và `setLimit()`, trong khi caller chỉ nhận `SequencedSet` và `SequencedMap` không thể sửa đổi qua API được trả về. Các view vẫn cập nhật khi class thêm dữ liệu vào collection nền, vì thế caller luôn nhìn thấy trạng thái mới nhất theo encounter order.

Nếu muốn caller nhận snapshot tại một thời điểm, hãy tạo bản sao có thứ tự trong getter thay vì trả view trực tiếp:

```java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class FeatureSnapshotExample {
    private final LinkedHashSet<String> featureNames = new LinkedHashSet<>();

    SequencedSet<String> featureSnapshot() {
        return Collections.unmodifiableSequencedSet(
                new LinkedHashSet<>(featureNames));
    }
}
```

Lựa chọn giữa view và snapshot là một phần của hợp đồng API: view phản ánh cập nhật mới từ chủ sở hữu; snapshot giữ cấu trúc tại thời điểm tạo.

## Kết luận

Trong Java 21, `Collections.unmodifiableSequencedCollection()`, `unmodifiableSequencedSet()` và `unmodifiableSequencedMap()` tạo các view có thứ tự nhưng chặn thao tác sửa đổi qua wrapper. Chúng giữ encounter order và cung cấp các API sequenced như truy cập đầu/cuối hoặc `reversed()`. Vì wrapper vẫn liên kết với collection nền, thay đổi qua tham chiếu gốc sẽ xuất hiện trong view. Khi cần snapshot độc lập, hãy sao chép sang implementation có thứ tự trước khi bọc; đồng thời nhớ rằng sao chép nông không làm các phần tử bên trong trở nên bất biến sâu hoặc thread-safe.
