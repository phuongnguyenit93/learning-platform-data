# Đánh giá xung đột source khi lớp riêng bổ sung các phương thức trùng API collection mới

Java 21 tích hợp các interface Sequenced Collections vào hệ thống Collections Framework qua JEP 431. Thay đổi này bổ sung các phương thức như `getFirst()`, `getLast()`, `addFirst()`, `addLast()`, `removeFirst()`, `removeLast()` và `reversed()` vào các kiểu collection có encounter order. `SequencedMap` cũng bổ sung API thao tác ở hai đầu và view theo thứ tự đảo ngược.

Phần lớn mã chỉ sử dụng `ArrayList`, `LinkedList`, `LinkedHashSet` hoặc `LinkedHashMap` không cần thay đổi. Rủi ro tập trung ở mã tự triển khai collection, lớp kế thừa collection có sẵn, interface riêng kết hợp nhiều nhánh collection và mã dựa vào kiểu được suy luận bằng `var`.

Khi nâng cấp từ JDK 20 lên JDK 21, cần kiểm tra ba nhóm xung đột: phương thức riêng trùng tên nhưng khác chữ ký tương thích, default method `reversed()` có kiểu trả về không thể hợp nhất, và thay đổi kiểu suy luận do hệ thống interface mới tạo ra least upper bound (LUB) khác trước.

## 1. Những thay đổi API có thể ảnh hưởng đến mã hiện có

JEP 431 thêm ba interface:

- `SequencedCollection<E>`: collection có encounter order rõ ràng, hỗ trợ thao tác ở đầu và cuối, đồng thời có view đảo thứ tự.
- `SequencedSet<E>`: kết hợp đặc tính set với encounter order.
- `SequencedMap<K,V>`: map có encounter order và thao tác trên entry đầu/cuối.

Một số interface và lớp hiện có được đưa vào hệ thống mới:

| Kiểu hiện có | Thay đổi trong Java 21 |
|---|---|
| `List<E>` | Mở rộng `SequencedCollection<E>` |
| `Deque<E>` | Mở rộng `SequencedCollection<E>` |
| `SortedSet<E>` | Mở rộng `SequencedSet<E>` |
| `NavigableSet<E>` | Nằm trong nhánh `SequencedSet` qua `SortedSet` |
| `LinkedHashSet<E>` | Triển khai `SequencedSet<E>` |
| `SortedMap<K,V>` | Mở rộng `SequencedMap<K,V>` |
| `NavigableMap<K,V>` | Nằm trong nhánh `SequencedMap` qua `SortedMap` |
| `LinkedHashMap<K,V>` | Triển khai `SequencedMap<K,V>` |

Các API mới quan trọng của `SequencedCollection`:

```java
void addFirst(E element);
void addLast(E element);
E getFirst();
E getLast();
E removeFirst();
E removeLast();
SequencedCollection<E> reversed();
```

Trong API thật, sáu phương thức thao tác ở hai đầu là default method; `reversed()` được khai báo ở `SequencedCollection` và được các interface con override với kiểu trả về covariant.

Các interface con có thể cung cấp kiểu trả về covariant. Ví dụ `List.reversed()` trả `List<E>`, còn `Deque.reversed()` trả `Deque<E>`.

`SequencedMap` bổ sung các phương thức như `reversed()`, `sequencedKeySet()`, `sequencedValues()`, `sequencedEntrySet()`, `putFirst()`, `putLast()`, `firstEntry()`, `lastEntry()`, `pollFirstEntry()` và `pollLastEntry()`.

Các phương thức mới được đưa vào bằng default method ở những interface cần duy trì khả năng tương thích với các implementation hiện có. Tuy vậy, việc thêm default method và thay đổi quan hệ kế thừa vẫn có thể tạo xung đột với mã nguồn đã tồn tại.

## 2. Nhóm 1: tên phương thức riêng trùng với API mới

Một lớp trước đây có thể khai báo phương thức riêng mang tên giống phương thức mới của interface collection. Trước Java 21, phương thức đó không xung đột vì interface mà lớp triển khai chưa khai báo phương thức cùng chữ ký. Sau khi nâng cấp, lớp có thể không còn biên dịch được.

### Ví dụ: getFirst() trả Optional

Giả sử trước Java 21 có một custom list:

```java
import java.util.List;
import java.util.Optional;

class MyList<E> implements List<E> {
    // Các phương thức List khác được triển khai ở đây.

    /** Trả Optional.empty() nếu danh sách rỗng. */
    public Optional<E> getFirst() {
        // Logic riêng của thư viện.
        return Optional.empty();
    }
}
```

Trước Java 21, `List` chưa có `getFirst()`, nên phương thức trên là API riêng hợp lệ. Trong Java 21, `List` kế thừa `getFirst()` từ `SequencedCollection`, với kiểu trả về `E`.

Hai phương thức có cùng tên và danh sách tham số nhưng kiểu trả về không tương thích:

```java
Optional<E> getFirst()
E getFirst()
```

Java không cho overload phương thức chỉ bằng kiểu trả về. `Optional<E>` cũng không phải kiểu con của `E`, nên phương thức cũ không thể override phương thức mới. Khi biên dịch lại với JDK 21, lớp gặp source incompatibility.

### Cách xử lý khi cần giữ semantics cũ

Nếu phương thức cũ biểu diễn kết quả có thể không tồn tại, hãy đổi tên để giữ rõ ý nghĩa:

```java
class MyList<E> implements List<E> {
    public Optional<E> firstOptional() {
        // Trả Optional.empty() nếu danh sách rỗng.
        return Optional.empty();
    }

    @Override
    public E getFirst() {
        // Tuân theo hợp đồng SequencedCollection:
        // ném NoSuchElementException nếu danh sách rỗng.
        throw new java.util.NoSuchElementException();
    }
}
```

Trong implementation thật, `getFirst()` cần trả phần tử đầu nếu có. Phương thức `firstOptional()` giữ hợp đồng cũ và không còn trùng API mới.

Nếu phương thức cũ đã có đúng semantics của API mới, hãy sửa kiểu trả về và visibility để nó trở thành override hợp lệ:

```java
@Override
public E getFirst() {
    if (isEmpty()) {
        throw new NoSuchElementException();
    }
    return get(0);
}
```

Phương án này chỉ phù hợp khi semantics thực sự tương đương. Không đổi `Optional<E>` thành `E` một cách máy móc nếu điều đó làm thay đổi hợp đồng công khai của thư viện.

### Xung đột về access modifier

Phương thức interface là `public`. Một phương thức cũ có cùng chữ ký nhưng package-private hoặc `protected` không thể override phương thức interface:

```java
class MyList<E> implements List<E> {
    // Không hợp lệ khi getLast() mới được kế thừa từ List.
    E getLast() {
        return null;
    }
}
```

Nếu phương thức đó được thiết kế để triển khai API mới, cần tăng visibility lên `public` và bảo đảm đúng semantics. Nếu nó là chi tiết nội bộ với semantics khác, hãy đổi tên hoặc chuyển nó sang helper riêng.

Một phương thức `static` cùng chữ ký cũng không thể dùng để triển khai instance method của interface. Khi rà soát, cần kiểm tra cả return type, visibility, static/instance và generic signature, không chỉ tìm tên phương thức.

### Phạm vi các tên cần rà soát

Với lớp triển khai `List`, `Deque`, `SequencedSet`, `SortedSet`, `SequencedMap` hoặc `SortedMap`, hãy tìm các tên API mới tương ứng:

| Nhóm | Tên phương thức cần kiểm tra |
|---|---|
| `SequencedCollection` | `addFirst`, `addLast`, `getFirst`, `getLast`, `removeFirst`, `removeLast`, `reversed` |
| `SequencedMap` | `reversed`, `sequencedKeySet`, `sequencedValues`, `sequencedEntrySet`, `putFirst`, `putLast`, `firstEntry`, `lastEntry`, `pollFirstEntry`, `pollLastEntry` |

Không phải mọi `Map` hoặc `Set` đều kế thừa các API sequenced. Ví dụ, một lớp chỉ triển khai `HashMap`-style `Map` không tự động trở thành `SequencedMap`. Chỉ rà các interface và lớp nằm trong nhánh API thực sự được mở rộng.

## 3. Nhóm 2: xung đột default method do covariant return type

Java 21 bổ sung default method `reversed()` cho cả `List` và `Deque`, nhưng mỗi interface khai báo kiểu trả về riêng: `List<E> List.reversed()` và `Deque<E> Deque.reversed()`.

Hai kiểu trả về `List<E>` và `Deque<E>` không phải subtype của nhau. Một lớp triển khai cả hai interface sẽ kế thừa hai default method có cùng tên, cùng tham số nhưng kiểu trả về không thể chọn một cách tự động.

### Ví dụ: collection vừa là List vừa là Deque

```java
class MyDoubleEndedList<E> implements List<E>, Deque<E> {
    // Triển khai các phương thức List và Deque.
}
```

Kiểu khai báo này có thể biên dịch trên JDK 20, nhưng khi biên dịch với JDK 21, compiler không thể chọn default `reversed()` nào để kế thừa. Đây là default-method conflict.

### Cách xử lý: override bằng kiểu trả về chung

Lớp cần tự khai báo một `reversed()` có kiểu trả về là subtype của cả `List<E>` và `Deque<E>`. Bản thân `MyDoubleEndedList<E>` đáp ứng điều kiện đó:

```java
class MyDoubleEndedList<E> implements List<E>, Deque<E> {
    // Các phương thức List và Deque được triển khai ở đây.

    @Override
    public MyDoubleEndedList<E> reversed() {
        return createReverseView();
    }

    private MyDoubleEndedList<E> createReverseView() {
        // Trả view đảo thứ tự, ghi thay đổi về collection gốc
        // theo semantics mà implementation công bố.
        // Phần triển khai view được lược bỏ trong ví dụ.
        return new ReverseView<>(this);
    }
}
```

Ví dụ trên minh họa cách giải quyết kiểu trả về; `ReverseView` là implementation riêng có kiểu con của `MyDoubleEndedList` và cần được triển khai thực tế. View phải giữ đúng semantics của collection, gồm encounter order và hành vi sửa đổi theo hợp đồng của implementation.

Nếu có nhiều lớp cùng kết hợp `List` và `Deque`, có thể định nghĩa interface trung gian:

```java
interface DoubleEndedList<E> extends List<E>, Deque<E> {
    @Override
    DoubleEndedList<E> reversed();
}
```

Interface trung gian khai báo một kiểu trả về covariant chung. Lớp cụ thể triển khai interface này và cung cấp reverse view tương ứng.

### Tham khảo cách JDK xử lý

`LinkedList<E>` của JDK triển khai cả `List<E>` và `Deque<E>`. JDK 21 bổ sung implementation `LinkedList.reversed()` trả về một reverse-ordered view có kiểu `LinkedList<E>`, là subtype của cả hai interface. Đây là ví dụ trực tiếp về cách giải quyết xung đột covariant override.

Không nên giải quyết bằng cách ép kiểu hoặc trả một `List<E>` thông thường nếu object đó không đồng thời thỏa hợp đồng `Deque<E>`. Kiểu trả về phải đúng với tất cả interface mà phương thức override.

### Lưu ý binary compatibility

Default method conflict có thể ảnh hưởng đến cả mã nguồn và binary cũ. Một class file được biên dịch trước Java 21 có thể chưa khai báo override `reversed()`. Khi chạy với interface mới, nếu JVM phải chọn giữa các default method không liên quan có cùng signature, lời gọi có thể thất bại với `IncompatibleClassChangeError`.

Vì vậy, với thư viện có custom collection được phát hành dưới dạng binary, cần kiểm tra cả hai việc: biên dịch lại source với JDK 21 và chạy các binary đã build trước đó trên JDK 21. Recompile thành công ở một module không chứng minh mọi consumer binary đều an toàn.

## 4. Nhóm 3: thay đổi LUB làm `var` suy luận kiểu khác

JEP 431 thay đổi quan hệ kế thừa của collection interface. Vì vậy, kiểu chung gần nhất (least upper bound - LUB) của một số biểu thức có thể khác so với JDK 20.

Điều này ảnh hưởng đến mã dùng `var`, bởi compiler suy luận kiểu từ biểu thức khởi tạo. Nếu phần còn lại của chương trình kỳ vọng kiểu cũ, mã có thể không biên dịch sau khi nâng cấp.

### Ví dụ với ArrayDeque và List

```java
List<Collection<String>> createCollections() {
    var list = List.of(
            new ArrayDeque<String>(),
            List.of("foo"));

    return list;
}
```

Trước Java 21, common supertype được suy luận cho hai phần tử là `Collection<String>`, nên biểu thức có kiểu `List<Collection<String>>` và phù hợp với kiểu trả về.

Trong Java 21, `ArrayDeque<String>` thuộc nhánh `Deque`, còn `List<String>` thuộc nhánh `List`. Cả hai cùng có superinterface mới là `SequencedCollection<String>`. Vì thế LUB được suy luận có thể trở thành `SequencedCollection<String>`, làm biến `list` có kiểu `List<SequencedCollection<String>>`.

Generic type trong Java là invariant. `List<SequencedCollection<String>>` không phải subtype của `List<Collection<String>>`, dù `SequencedCollection<String>` là subtype của `Collection<String>`. Vì vậy, câu lệnh `return list` không còn hợp lệ.

### Cách xử lý: khai báo kiểu đích rõ ràng

Nếu hợp đồng của phương thức vẫn cần `List<Collection<String>>`, hãy khai báo kiểu biến rõ ràng:

```java
List<Collection<String>> createCollections() {
    List<Collection<String>> list = List.of(
            new ArrayDeque<String>(),
            List.of("foo"));

    return list;
}
```

Hoặc chỉ định type argument cho `List.of`:

```java
List<Collection<String>> createCollections() {
    var list = List.<Collection<String>>of(
            new ArrayDeque<String>(),
            List.of("foo"));

    return list;
}
```

Cả hai cách đều thể hiện rõ kiểu mong muốn tại điểm tạo collection và không phụ thuộc vào LUB mới được suy luận từ hệ thống interface.

Nếu API thực sự muốn trả một list các sequenced collection, có thể thay đổi kiểu trả về thành `List<SequencedCollection<String>>`. Chỉ chọn cách này khi đó là thay đổi hợp đồng có chủ đích; không đổi kiểu public API chỉ để làm compiler hết báo lỗi.

## 5. Phân biệt source incompatibility và binary incompatibility

Không phải mọi xung đột đều có cùng tác động:

| Loại xung đột | Khi biên dịch lại source | Với binary đã biên dịch trước Java 21 |
|---|---|---|
| Phương thức cũ trùng tên nhưng return type không tương thích | Có thể lỗi biên dịch | Thường vẫn gọi được phương thức cũ vì descriptor JVM chứa return type; lời gọi API mới có thể đi đến default method |
| Visibility cũ không đủ `public` | Lỗi biên dịch | Cần kiểm tra cách binary cũ và lời gọi mới liên kết; không xem việc compile source là bằng chứng duy nhất |
| Hai default `reversed()` không tương thích | Lỗi biên dịch khi lớp kế thừa cả hai | Có thể gặp `IncompatibleClassChangeError` khi lời gọi cần chọn giữa các default method không liên quan |
| LUB thay đổi do interface hierarchy | Lỗi biên dịch ở biểu thức có kiểu kỳ vọng không còn phù hợp | Binary đã compile vẫn giữ kiểu và descriptor cũ; cần kiểm tra behavior khi chạy với runtime mới |

Ở JVM, method descriptor bao gồm cả kiểu trả về. Vì vậy, một method cũ như `getFirst()Ljava/util/Optional;` khác descriptor với API mới sau erasure như `getFirst()Ljava/lang/Object;`. Điều này giải thích vì sao một số binary cũ vẫn gọi được method cũ dù source không thể biên dịch lại.

Tuy nhiên, binary compatibility không đồng nghĩa source compatibility hoặc behavioral compatibility. Sau khi nâng cấp, code consumer biên dịch với JDK 21 có thể gọi API mới qua interface reference và nhận semantics của API mới. Cần kiểm tra cả hợp đồng public và cách consumer sử dụng class.

## 6. Phạm vi mã cần kiểm tra khi nâng cấp

Ưu tiên rà soát các thành phần sau:

1. **Custom collection implementation:** lớp `implements List`, `Deque`, `SortedSet`, `NavigableSet`, `SequencedSet`, `SortedMap`, `NavigableMap` hoặc `SequencedMap`.
2. **Collection subclass:** lớp kế thừa `AbstractList`, `AbstractSequentialList`, `LinkedList`, `LinkedHashSet`, `LinkedHashMap` hoặc implementation collection khác rồi thêm method riêng.
3. **Interface kết hợp:** interface riêng kế thừa nhiều nhánh collection, đặc biệt kết hợp `List` và `Deque`.
4. **Utility API:** helper trả collection, method overload hoặc API public có dùng `var` và dựa vào kiểu suy luận.
5. **Binary dependencies:** thư viện nội bộ hoặc bên thứ ba cung cấp custom collection đã build với JDK cũ.

Mã chỉ gọi `list.add(...)`, `map.get(...)` hoặc dùng implementation chuẩn thường ít bị ảnh hưởng. Không cần sửa hàng loạt mọi nơi sử dụng collection; hãy tập trung vào lớp định nghĩa hoặc kế thừa API bị thay đổi và các biểu thức có kiểu suy luận liên quan.

## 7. Quy trình migration thực tế

### Bước 1: xác định baseline

Ghi lại JDK đang dùng để build và test trước nâng cấp. Nếu còn giữ môi trường JDK 20, chạy build/test hiện tại để có baseline. Sau đó chạy lại bằng JDK 21 với đúng dependency và cấu hình build.

### Bước 2: tìm các method name có nguy cơ trùng

Tìm trong source custom collection các method:

```text
addFirst
addLast
getFirst
getLast
removeFirst
removeLast
reversed
putFirst
putLast
firstEntry
lastEntry
pollFirstEntry
pollLastEntry
sequencedKeySet
sequencedValues
sequencedEntrySet
```

Sau khi tìm thấy, kiểm tra class/interface đó thực sự implements hoặc extends nhánh collection nào. So sánh tên, tham số, return type, generic type, visibility và static/instance.

### Bước 3: sửa method naming conflict

- Nếu method cũ có semantics khác, đổi tên để giữ API cũ rõ ràng.
- Nếu method cũ thực sự có semantics của API mới, sửa return type/visibility và đánh dấu `@Override`.
- Nếu không thể đổi public API ngay, cân nhắc major version hoặc adapter riêng; không thể overload chỉ bằng return type.

### Bước 4: xử lý default method conflict

- Xác định các interface cùng khai báo default method có cùng signature nhưng kiểu trả về covariant không tương thích.
- Override trong class bằng kiểu trả về là subtype của tất cả interface liên quan.
- Nếu nhiều class có cùng cấu trúc, tạo interface trung gian với covariant override chung.
- Bảo đảm reverse view giữ đúng encounter order và mutation semantics.

### Bước 5: ổn định type inference

- Tìm `var` khởi tạo bằng `List.of`, `Set.of`, `Map.of` hoặc biểu thức kết hợp nhiều implementation collection khác nhau.
- Kiểm tra lỗi ở generic assignment, return type và overload resolution.
- Dùng explicit local type hoặc explicit type witness khi hợp đồng cần kiểu cụ thể.
- Chỉ đổi public API sang `SequencedCollection` hoặc `SequencedSet` nếu semantics của API thực sự muốn yêu cầu encounter order.

### Bước 6: kiểm thử source và binary

- Biên dịch toàn bộ module phụ thuộc bằng JDK 21, không chỉ module ứng dụng chính.
- Chạy unit test và integration test cho custom collection.
- Nếu phát hành thư viện, kiểm thử consumer compile với API mới.
- Chạy binary đã build trước đó trên JDK 21, nhất là class triển khai nhiều collection interface.
- Kiểm tra method `reversed()` có trả đúng view và các thao tác trên view có tuân theo hợp đồng không.

### Bước 7: kiểm tra cấu hình release

Nếu dự án cần phát hành artifact cho Java 21, dùng cấu hình compile tương ứng như `--release 21` hoặc cấu hình build tool tương đương. Nếu vẫn hỗ trợ nhiều release, cần compile/test theo từng release được công bố; không chỉ đổi JDK cài trên máy developer.

## 8. Checklist review cho pull request migration

- [ ] Đã xác định tất cả custom class triển khai hoặc kế thừa collection interface bị thay đổi.
- [ ] Đã rà soát method name mới và kiểm tra return type, visibility, static/instance.
- [ ] Các method cũ có semantics khác đã được đổi tên hoặc chuyển sang API riêng.
- [ ] Các lớp kết hợp `List` và `Deque` có override `reversed()` với kiểu trả về chung.
- [ ] Reverse view được kiểm thử về encounter order và hành vi sửa đổi.
- [ ] Các biểu thức `var` có LUB thay đổi đã được khai báo kiểu rõ ràng hoặc điều chỉnh hợp đồng có chủ đích.
- [ ] Toàn bộ source và dependency nội bộ biên dịch với JDK 21.
- [ ] Binary cũ và consumer mới đã được kiểm tra nếu thư viện cần binary compatibility.
- [ ] Test chạy trên runtime Java 21 mục tiêu.
- [ ] Tài liệu public API đã cập nhật nếu semantics hoặc method name thay đổi.

## 9. Những cách sửa nên tránh

- **Chỉ đổi return type để compiler im lặng:** có thể phá semantics và source compatibility của consumer.
- **Ép kiểu `reversed()` sang `List` hoặc `Deque`:** không giải quyết hợp đồng nếu object không thực sự implement cả hai interface.
- **Trả một bản copy thay cho reverse view mà không công bố:** có thể làm sai kỳ vọng về write-through và quan hệ với collection gốc.
- **Dùng raw type hoặc cast unchecked để né LUB:** che cảnh báo kiểu và tạo rủi ro lỗi runtime.
- **Chỉ build module chính:** xung đột có thể nằm trong thư viện collection nội bộ hoặc plugin được compile riêng.
- **Chỉ chạy source mới:** binary cũ có thể gặp vấn đề khi JVM phải phân giải các default method xung đột.

## 10. Tổng kết

JDK 21 đưa `SequencedCollection`, `SequencedSet` và `SequencedMap` vào hệ thống Collections Framework. Thay đổi này tạo API thống nhất cho encounter order nhưng có thể làm source cũ không còn biên dịch được ở các lớp tự triển khai hoặc kết hợp nhiều interface collection.

Ba nhóm cần kiểm tra là method riêng trùng tên với API mới nhưng khác return type/visibility, default `reversed()` xung đột giữa `List` và `Deque`, và LUB thay đổi khiến `var` suy luận kiểu khác. Hãy sửa theo đúng semantics: đổi tên method riêng khi cần, override bằng kiểu trả về chung khi có nhiều default method, và khai báo kiểu generic rõ ràng khi hợp đồng yêu cầu. Cuối cùng, kiểm thử cả source và binary trên JDK 21 để xác nhận migration hoàn chỉnh.

## Tài liệu tham khảo

- [JEP 431: Sequenced Collections](https://openjdk.org/jeps/431) — thiết kế các interface sequenced và thay đổi trong Collections Framework.
- [Inside Java: Quality Outreach Heads-up — JDK 21 Sequenced Collections Incompatibilities](https://inside.java/2023/05/12/quality-heads-up/) — ba nhóm xung đột source/binary: method naming, covariant default methods và type inference.
- [Java SE 21 API — SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html) — các default method và hợp đồng encounter order.
- [Java SE 21 API — List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html) — `List.reversed()` và các phương thức đầu/cuối.
- [Java SE 21 API — Deque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html) — `Deque.reversed()` và kiểu trả về covariant.
- [Java SE 21 API — LinkedList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedList.html) — implementation `reversed()` giải quyết việc `LinkedList` đồng thời là `List` và `Deque`.
