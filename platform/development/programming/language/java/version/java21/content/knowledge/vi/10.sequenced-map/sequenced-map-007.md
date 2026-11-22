# Reversed view và quan hệ thứ tự giữa map với các view

Trong Java 21, `SequencedMap<K, V>` cung cấp `reversed()` để lấy một **view có encounter order đảo ngược** của map. View này được liên kết trực tiếp với map gốc: thay đổi được hỗ trợ ở một phía được phản ánh ở phía còn lại. `reversed()` không tạo bản sao và cũng không sắp xếp lại dữ liệu.

Thứ tự đảo ảnh hưởng đến cách nhìn mapping đầu/cuối và các view của key, value, entry. Ví dụ, `reversed.firstEntry()` tương ứng mapping cuối của map gốc; `reversed.putFirst(...)` đặt mapping vào đầu view đảo, tức cuối map gốc. Hiểu quan hệ này giúp dùng `SequencedMap` nhất quán mà không cần tự sao chép hoặc đảo danh sách mapping.

## 1. Reversed view là gì?

`SequencedMap<K, V>` thuộc `java.util` và biểu diễn map có encounter order xác định. Phương thức:

```java
SequencedMap<K, V> reversed();
```

trả về một map view có encounter order ngược với map ban đầu. Nếu map gốc có thứ tự `A, B, C`, view đảo quan sát thứ tự `C, B, A`.

Điểm quan trọng:

- View và map gốc cùng phản ánh một tập mapping.
- Thay đổi được hỗ trợ qua view sẽ được phản ánh vào map gốc, và thay đổi map gốc được phản ánh vào view.
- Tạo view không sao chép mapping và không thay đổi thứ tự của map gốc.
- Các thao tác đọc và sửa đổi trên view tuân theo khả năng của map nền. Nếu map nền không cho sửa, view cũng không trở thành mutable.
- Gọi `reversed()` trên một map view khác sẽ đảo hướng encounter order của view hiện tại. Hai lần đảo cho thứ tự quan sát giống map gốc; không dựa vào việc hai tham chiếu có cùng object identity.

## 2. Ví dụ với LinkedHashMap

`LinkedHashMap` ở chế độ mặc định duy trì thứ tự thêm mapping, nên rất phù hợp để quan sát quan hệ giữa map và reversed view:

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

public class ReversedMapDemo {
    public static void main(String[] args) {
        SequencedMap<String, Integer> map = new LinkedHashMap<>();
        map.put("A", 1);
        map.put("B", 2);
        map.put("C", 3);

        SequencedMap<String, Integer> reversed = map.reversed();

        System.out.println(map.sequencedKeySet());
        System.out.println(reversed.sequencedKeySet());
        System.out.println(map.firstEntry());
        System.out.println(reversed.firstEntry());
    }
}
```

Kết quả:

```text
[A, B, C]
[C, B, A]
A=1
C=3
```

Map gốc vẫn giữ encounter order `A, B, C`. View đảo chỉ trình bày cùng các mapping theo hướng `C, B, A`. Không cần tạo `new LinkedHashMap<>(...)` hoặc tự đảo một danh sách key để có thứ tự ngược.

## 3. Quan hệ giữa các thao tác hai đầu

Khi nhìn qua reversed view, hai đầu đổi vị trí:

| Thao tác trên view đảo | Mapping tương ứng trong map gốc |
|---|---|
| `reversed.firstEntry()` | `map.lastEntry()` |
| `reversed.lastEntry()` | `map.firstEntry()` |
| `reversed.pollFirstEntry()` | Lấy và xóa mapping cuối của map gốc |
| `reversed.pollLastEntry()` | Lấy và xóa mapping đầu của map gốc |
| `reversed.putFirst(key, value)` | Đặt mapping ở cuối map gốc |
| `reversed.putLast(key, value)` | Đặt mapping ở đầu map gốc |

Ánh xạ vị trí của `putFirst`/`putLast` mô tả hướng của view. Tuy nhiên, hợp đồng không xác định hành vi định vị hai đầu trên sorted map như `TreeMap`; không dùng các thao tác này để cố thay đổi thứ tự do comparator quyết định.

Ví dụ đọc hai đầu:

```java
SequencedMap<String, Integer> map = new LinkedHashMap<>();
map.put("first", 10);
map.put("middle", 20);
map.put("last", 30);

SequencedMap<String, Integer> reversed = map.reversed();

System.out.println(map.firstEntry());       // first=10
System.out.println(map.lastEntry());        // last=30
System.out.println(reversed.firstEntry());  // last=30
System.out.println(reversed.lastEntry());   // first=10
```

Các thao tác `poll` có tác dụng xóa mapping khỏi map nền. Vì vậy, gọi `reversed.pollFirstEntry()` cũng làm giảm số mapping của `map`; đây không phải thao tác chỉ đọc.

## 4. Sửa thứ tự qua reversed view

Với map hỗ trợ định vị mapping ở hai đầu như `LinkedHashMap`, thao tác sửa qua view đảo được phản ánh lên map gốc. Ví dụ:

```java
SequencedMap<String, Integer> map = new LinkedHashMap<>();
map.put("A", 1);
map.put("B", 2);
map.put("C", 3);

SequencedMap<String, Integer> reversed = map.reversed();

reversed.putFirst("D", 4);
System.out.println(reversed.sequencedKeySet()); // [D, C, B, A]
System.out.println(map.sequencedKeySet());      // [A, B, C, D]

reversed.putLast("Z", 0);
System.out.println(reversed.sequencedKeySet()); // [D, C, B, A, Z]
System.out.println(map.sequencedKeySet());      // [Z, A, B, C, D]
```

`putFirst` và `putLast` đặt mapping ở đầu hoặc cuối theo encounter order của đối tượng nhận lời gọi. Vì `reversed` có hướng ngược, đầu của nó là cuối map gốc và cuối của nó là đầu map gốc.

Nếu key đã tồn tại, `LinkedHashMap.putFirst`/`putLast` thay value theo lời gọi và định vị lại mapping ở đầu/cuối tương ứng nếu cần. Không áp dụng hành vi định vị này cho map sắp xếp như `TreeMap`: hợp đồng `SequencedMap` không xác định hành vi `putFirst`/`putLast` trên sorted map, vì thứ tự của nó do comparator quyết định.

## 5. Quan hệ với sequencedKeySet, sequencedValues và sequencedEntrySet

`SequencedMap` cung cấp ba view sequenced để truy cập riêng key, value và entry theo cùng encounter order của map:

| Phương thức | Kiểu trả về | Nội dung và thứ tự |
|---|---|---|
| `sequencedKeySet()` | `SequencedSet<K>` | Các key theo encounter order của map |
| `sequencedValues()` | `SequencedCollection<V>` | Các value theo encounter order của map |
| `sequencedEntrySet()` | `SequencedSet<Map.Entry<K, V>>` | Các mapping dưới dạng entry theo encounter order của map |

Các view này được liên kết với map nền. Khi lấy chúng từ reversed view, encounter order của từng view cũng đảo theo:

```java
SequencedMap<String, Integer> map = new LinkedHashMap<>();
map.put("A", 1);
map.put("B", 2);
map.put("C", 3);

SequencedMap<String, Integer> reversed = map.reversed();

System.out.println(map.sequencedKeySet());
System.out.println(reversed.sequencedKeySet());

System.out.println(map.sequencedValues());
System.out.println(reversed.sequencedValues());

System.out.println(map.sequencedEntrySet());
System.out.println(reversed.sequencedEntrySet());
```

Kết quả minh họa:

```text
[A, B, C]
[C, B, A]
[1, 2, 3]
[3, 2, 1]
[A=1, B=2, C=3]
[C=3, B=2, A=1]
```

Các phương thức quen thuộc `keySet()`, `values()` và `entrySet()` vẫn trả về các kiểu tổng quát `Set` hoặc `Collection`. Nếu cần thể hiện rõ API hai đầu và encounter order trong kiểu khai báo, hãy dùng các phương thức sequenced tương ứng.

## 6. Sửa map qua các view và giới hạn mutability

Các view sequenced phản ánh map nền. Ví dụ, xóa key qua key set sẽ xóa mapping tương ứng khỏi map:

```java
SequencedMap<String, Integer> map = new LinkedHashMap<>();
map.put("A", 1);
map.put("B", 2);
map.put("C", 3);

SequencedMap<String, Integer> reversed = map.reversed();
reversed.sequencedKeySet().remove("B");

System.out.println(map); // {A=1, C=3}
```

Các thao tác xóa qua view chỉ thực hiện được nếu map nền hỗ trợ sửa đổi. Các view không biến một map bất biến thành map có thể sửa. Ngoài ra, không phải mọi view đều hỗ trợ thêm phần tử: chẳng hạn, thêm key độc lập vào key set hoặc thêm value trực tiếp vào values collection không thể xác định mapping tương ứng nên thường không được hỗ trợ.

Nếu cần một map đảo độc lập, có thể tạo map mới và sao chép các mapping theo thứ tự mong muốn. Cần phân biệt rõ hai nhu cầu:

- `reversed()`: view đảo được liên kết với map gốc; không sao chép dữ liệu.
- Tạo map mới rồi chép mapping: cấu trúc độc lập, chiếm bộ nhớ riêng và không tự đồng bộ thay đổi với map ban đầu.

Chỉ tạo bản sao khi ứng dụng cần snapshot hoặc vòng đời độc lập. Nếu chỉ cần duyệt từ cuối về đầu, reversed view thường là cách trực tiếp hơn.

## 7. reversed view với LinkedHashMap và TreeMap

### LinkedHashMap

Với `LinkedHashMap` insertion-order, reversed view đảo thứ tự thêm mapping. Nếu map được cấu hình access-order, view đảo encounter order hiện tại, bao gồm những thay đổi thứ tự do thao tác truy cập. Vì vậy, không nên diễn giải `reversed()` là “đảo thứ tự thêm ban đầu” trong mọi cấu hình.

### TreeMap

`TreeMap` duy trì mapping theo thứ tự key do natural ordering hoặc comparator. Reversed view trình bày thứ tự ngược với thứ tự đó, tương tự một view descending. Ví dụ:

```java
import java.util.SequencedMap;
import java.util.TreeMap;

SequencedMap<Integer, String> sorted = new TreeMap<>();
sorted.put(10, "Low");
sorted.put(20, "Normal");
sorted.put(30, "High");

SequencedMap<Integer, String> descending = sorted.reversed();

System.out.println(sorted.sequencedKeySet());     // [10, 20, 30]
System.out.println(descending.sequencedKeySet()); // [30, 20, 10]
```

Đây là view theo hướng comparator ngược, không phải thao tác thay comparator hoặc sắp xếp lại một bản sao. Vì `TreeMap` là sorted map, không dựa vào `putFirst`/`putLast` để ghi đè vị trí theo ý muốn; thứ tự vẫn do quy tắc sắp xếp quyết định.

## 8. Lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tưởng `reversed()` đã đảo map gốc | Nhầm view đảo với thao tác thay đổi thứ tự map | Ghi nhớ map gốc giữ encounter order của nó; chỉ view có hướng quan sát ngược |
| Thay đổi qua view không thấy ở map gốc | Đang thao tác trên bản sao tự tạo hoặc map nền không hỗ trợ thay đổi | Xác định đối tượng là backed view hay copy và kiểm tra mutability |
| `reversed.firstEntry()` khác `map.firstEntry()` | Đầu của view đảo tương ứng cuối của map gốc | Đối chiếu hai đầu theo bảng ánh xạ |
| Gọi `putFirst`/`putLast` trên TreeMap nhưng thứ tự không đổi theo mong muốn | Sorted map quyết định encounter order bằng comparator; hành vi định vị hai đầu không được quy định | Thay đổi key/comparator theo yêu cầu hoặc dùng map insertion-order phù hợp |
| View key/value/entry có thứ tự ngược dự kiến | Đang đọc từ reversed map view | Xác định view lấy từ map gốc hay reversed view trước khi xử lý |
| `UnsupportedOperationException` khi sửa qua view | Map nền hoặc view không hỗ trợ thao tác sửa đổi | Dùng map mutable phù hợp hoặc tạo bản sao nếu cần cấu trúc độc lập |
| Vòng lặp gặp thay đổi ngoài dự kiến | Map bị sửa trong khi đang duyệt view | Tránh sửa cấu trúc trong lúc duyệt, hoặc dùng cơ chế đồng bộ phù hợp |

## 9. Checklist khi sử dụng reversed view

- Xác định map có triển khai `SequencedMap` và có encounter order rõ ràng.
- Nhớ `reversed()` tạo backed view, không tạo bản sao và không đảo map gốc tại chỗ.
- Đổi chiều first/last khi thao tác qua view đảo.
- Hiểu `putFirst`/`putLast` theo hướng của view; tránh dựa vào chúng với sorted map.
- Dùng `sequencedKeySet()`, `sequencedValues()` và `sequencedEntrySet()` khi cần các view có API sequenced.
- Nhớ thao tác sửa hoặc xóa qua view tác động lên map gốc nếu implementation hỗ trợ.
- Kiểm tra mutability của map nền; reversed view không mở rộng quyền sửa đổi.
- Chọn bản sao độc lập thay vì view khi cần snapshot không bị ảnh hưởng bởi thay đổi về sau.

`SequencedMap.reversed()` cung cấp một góc nhìn ngược chiều trên cùng các mapping. Quan hệ đảo chiều áp dụng nhất quán cho entry ở hai đầu, thao tác định vị và các view key/value/entry. Khi phân biệt được backed view với bản sao, đồng thời hiểu encounter order của implementation, có thể xử lý thứ tự hai đầu mà không tự xây dựng cấu trúc dữ liệu phụ.
