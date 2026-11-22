# Collections.newSetFromMap và bộ nhớ đệm Boolean phía dưới

## 1. Hiểu đúng phần Boolean phía dưới

Một tập hợp `Set<E>` chỉ cần trả lời một phần tử có mặt hay không; một `Map<K,V>` còn cần giá trị đi kèm mỗi khóa. `Collections.newSetFromMap` nối hai mô hình đó: phần tử của tập hợp được lưu làm khóa của map, còn phần giá trị là một dấu đánh dấu kiểu `Boolean`.

Trong chủ đề này, cấu trúc phía dưới là **map làm nơi lưu trữ nền (backing map)**. Nó không phải bộ nhớ đệm tự tính và lưu một kết quả nghiệp vụ `true`/`false`. Nếu cần nhớ kết quả kiểm tra “được phép hay không”, bản thân `Map<Key, Boolean>` là một mô hình khác với tập hợp.

```text
giao diện bên dùng: Set<E>
          |
          v
map phía dưới: phần tử E -> dấu đánh dấu Boolean

có khóa    -> phần tử thuộc tập hợp
không khóa -> phần tử không thuộc tập hợp
```

Chẳng hạn tập hợp `{alpha, beta}` có thể được hình dung bằng hai mục map `alpha -> TRUE`, `beta -> TRUE`. Không cần một mục `gamma -> FALSE` để diễn đạt gamma vắng mặt; gamma chỉ đơn giản là không có khóa.

## 2. Chữ ký và hợp đồng sử dụng

Chữ ký phương thức:

```java
public static <E> Set<E> newSetFromMap(Map<E, Boolean> map)
```

Đây là chữ ký API để đọc, không phải đoạn khai báo cần chép vào chương trình. `E` vừa là kiểu khóa map vừa là kiểu phần tử tập hợp.

Phương thức tạo tập hợp được map cung cấp làm nền, không sao chép dữ liệu sang một `HashSet` độc lập. Map phải rỗng khi gọi; map không rỗng gây `IllegalArgumentException`. Sau khi tạo thành công, không truy cập trực tiếp map đó nữa. Cách rõ ràng là tạo map rỗng ngay trong đối số và không giữ tham chiếu khác. [Hợp đồng newSetFromMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#newSetFromMap(java.util.Map))

Ví dụ hợp lệ dùng ngữ nghĩa định danh đối tượng:

```java
Set<Object> visited = Collections.newSetFromMap(
        new IdentityHashMap<Object, Boolean>());
```

Đoạn trên cần import các kiểu từ `java.util`. Từ thời điểm đó, thao tác qua `visited`, không cố tìm lại map để thêm dữ liệu ngoài đường tập hợp.

Map rỗng cũng phải hỗ trợ những thay đổi mà ứng dụng cần. Truyền một map không sửa được không làm nó trở thành map sửa được chỉ vì được bọc bởi một `Set`.

## 3. Cơ chế: khóa là dữ liệu, Boolean là dấu có mặt

Trong triển khai OpenJDK 25, thao tác thêm đặt dấu `Boolean.TRUE` cho khóa và xác định kết quả thêm dựa vào việc trước đó đã có ánh xạ hay chưa. Các thao tác đọc/xóa chuyển xuống map hoặc tập khóa của map. [Mã nguồn SetFromMap trong OpenJDK](https://raw.githubusercontent.com/openjdk/jdk/jdk-25-ga/src/java.base/share/classes/java/util/Collections.java)

| Thao tác nhìn từ Set | Ý nghĩa đối với lưu trữ nền |
| --- | --- |
| `add(e)` | Đảm bảo có khóa tương ứng với `e`, gắn dấu có mặt |
| `contains(e)` | Kiểm tra có khóa phù hợp hay không |
| `remove(e)` | Loại ánh xạ của khóa tương ứng |
| `size()` | Đếm số khóa đang được giữ |
| Duyệt phần tử | Duyệt các khóa theo đặc điểm của map |
| `clear()` | Xóa nội dung đang được tập hợp quản lý |

Không tự viết giá trị `FALSE` vào map sau khi tạo rồi kỳ vọng phần tử biến mất. Vắng mặt được biểu diễn bằng **không có khóa**, không phải bằng một giá trị Boolean mang nghĩa phủ định. Việc can thiệp trực tiếp vào backing map còn phá điều kiện sử dụng mà API đã đặt ra.

`Boolean.TRUE` là một đối tượng hằng có sẵn. Việc dùng nó làm dấu không đòi hỏi mỗi khóa phải có một đối tượng Boolean mới. `Boolean.valueOf(true)` cũng trả về giá trị đối tượng tương ứng có sẵn; đây là chuyện tái sử dụng biểu diễn Boolean, không phải một thuật toán cache nghiệp vụ. [Tài liệu Boolean](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Boolean.html)

Dù cùng dùng một dấu, mỗi khóa vẫn cần chỗ trong cấu trúc map. Không suy ra tập hợp chỉ tốn một đối tượng Boolean nên gần như không chiếm bộ nhớ; khóa và các bảng/mục lưu trữ mới là phần tài nguyên cần xét.

## 4. Vì sao lại tạo Set từ Map?

Ý nghĩa chính là sử dụng đặc điểm của một map khi ứng dụng cần một giao diện tập hợp. Nếu đã có lớp tập hợp trực tiếp đáp ứng nhu cầu, lựa chọn trực tiếp thường dễ hiểu hơn.

| Nhu cầu | Map nền có thể dùng | Lựa chọn trực tiếp nên cân nhắc |
| --- | --- | --- |
| Duy nhất theo `equals`/`hashCode` | `HashMap<E, Boolean>` | `HashSet<E>` |
| Giữ thứ tự thêm thông thường | `LinkedHashMap<E, Boolean>` | `LinkedHashSet<E>` |
| Sắp theo thứ tự khóa | `TreeMap<E, Boolean>` | `TreeSet<E>` nếu cần giao diện sắp thứ tự |
| Phân biệt từng đối tượng bằng `==` | `IdentityHashMap<E, Boolean>` | `newSetFromMap` là cách hữu ích để biểu diễn tập định danh |
| Khóa có vòng đời tham chiếu yếu | `WeakHashMap<E, Boolean>` | Cần thiết kế rõ ý nghĩa phần tử tự biến mất |
| Tập hợp cập nhật đồng thời | `ConcurrentHashMap<E, Boolean>` | `ConcurrentHashMap.newKeySet()` trong Java hiện đại |

Map nền tác động đến thứ tự, hiệu năng và đặc điểm đồng thời của kết quả. Nhưng trả về `Set<E>` không có nghĩa tự có mọi giao diện mà map gợi ý. Chẳng hạn map nền có thứ tự sắp xếp không khiến kết quả của `newSetFromMap` tự trở thành `NavigableSet` để gọi `floor` hoặc `ceiling`.

Không đổi map nền như một tối ưu vô hại nếu ứng dụng đang dựa vào cách xác định phần tử trùng, thứ tự duyệt hoặc việc phần tử được giữ sống.

## 5. Chương trình minh chứng chạy được trên Java 17+

Ví dụ có ba phần: tập hợp giữ thứ tự thêm để quan sát thao tác cơ bản; tập hợp định danh để phân biệt hai đối tượng có giá trị bằng nhau; và tập hợp dùng map đồng thời để minh họa thêm trùng và giới hạn `null`.

Lưu thành `SetFromMapDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class SetFromMapDemo {
    public static void main(String[] args) {
        Set<String> ordered = Collections.newSetFromMap(
                new LinkedHashMap<String, Boolean>());
        System.out.println("add-alpha=" + ordered.add("alpha"));
        System.out.println("add-beta=" + ordered.add("beta"));
        System.out.println("add-alpha-again=" + ordered.add(new String("alpha")));
        System.out.println("order=" + new ArrayList<>(ordered));
        System.out.println("remove-beta=" + ordered.remove("beta"));
        System.out.println("remaining=" + new ArrayList<>(ordered));

        Map<String, Boolean> nonEmpty = new HashMap<>();
        nonEmpty.put("existing", Boolean.TRUE);
        try {
            Collections.newSetFromMap(nonEmpty);
            throw new AssertionError("A non-empty map was accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("non-empty-map=rejected");
        }

        String first = new String("same");
        String second = new String("same");
        Set<String> identity = Collections.newSetFromMap(
                new IdentityHashMap<String, Boolean>());
        Set<String> values = new HashSet<>();
        identity.add(first);
        identity.add(second);
        values.add(first);
        values.add(second);
        System.out.println("equal-values=" + first.equals(second));
        System.out.println("same-reference=" + (first == second));
        System.out.println("identity-size=" + identity.size());
        System.out.println("value-size=" + values.size());
        System.out.println("same-object-again=" + identity.add(first));

        Set<String> concurrent = Collections.newSetFromMap(
                new ConcurrentHashMap<String, Boolean>());
        System.out.println("claim-first=" + concurrent.add("job-1"));
        System.out.println("claim-again=" + concurrent.add("job-1"));
        try {
            concurrent.add(null);
            throw new AssertionError("ConcurrentHashMap accepted null");
        } catch (NullPointerException expected) {
            System.out.println("concurrent-null=rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 SetFromMapDemo.java
java SetFromMapDemo
```

Đầu ra:

```text
add-alpha=true
add-beta=true
add-alpha-again=false
order=[alpha, beta]
remove-beta=true
remaining=[alpha]
non-empty-map=rejected
equal-values=true
same-reference=false
identity-size=2
value-size=1
same-object-again=false
claim-first=true
claim-again=false
concurrent-null=rejected
```

Chương trình không đọc hay sửa trực tiếp backing map sau khi chuyển giao thành công. Map `nonEmpty` chỉ dùng để kiểm tra điều kiện đầu vào bị từ chối; vì lời gọi tạo tập hợp thất bại, không có một tập hợp hợp lệ nào được tạo từ map đó.

### Đọc kết quả tập hợp thông thường

`new String("alpha")` tạo một đối tượng khác nhưng có giá trị chuỗi bằng `"alpha"`. Với map dựa trên bình đẳng giá trị, thêm lần nữa trả `false`; tập hợp vẫn chỉ chứa một alpha.

Thứ tự `[alpha, beta]` trong ví dụ đến từ `LinkedHashMap` mặc định theo thứ tự thêm. Không lấy đầu ra này để suy ra mọi backing map đều giữ thứ tự. Nếu đổi thành `HashMap`, bài kiểm thử không nên cố định thứ tự in.

`remove-beta=true` báo một phần tử đã thực sự bị xóa. Tập hợp còn `[alpha]`, không có mục beta gắn với `FALSE`.

## 6. Tập hợp định danh: cùng giá trị chưa chắc cùng phần tử

`IdentityHashMap` so sánh khóa bằng định danh tham chiếu: hai khóa được coi là cùng khi `k1 == k2`. Nó được thiết kế cho nhu cầu đặc biệt và không tuân theo ngữ nghĩa bình đẳng giá trị thông thường của Map. [Tài liệu IdentityHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/IdentityHashMap.html)

Trong chương trình:

- `first.equals(second)` là `true` vì nội dung chuỗi giống nhau.
- `first == second` là `false` vì đây là hai đối tượng được tạo riêng.
- Tập hợp định danh giữ cả hai nên có kích thước 2.
- `HashSet` giữ một đại diện theo giá trị nên có kích thước 1.
- Thêm lại đúng đối tượng `first` vào tập hợp định danh trả `false`.

Một trường hợp ứng dụng là theo dõi những nút đối tượng đã thăm trong một cấu trúc đồ thị khi hai nút khác nhau vẫn phải được xử lý riêng dù chúng có dữ liệu bằng nhau.

Ngữ nghĩa này cần được thể hiện rõ trong tên và phạm vi sử dụng. Không dùng tập hợp định danh như một tập hợp giá trị thông thường rồi mặc định mọi phép so sánh, kết hợp hay chuyển đổi với `HashSet` vẫn giữ nguyên ý nghĩa. Khi chuyển sang `HashSet`, những đối tượng khác tham chiếu nhưng bằng giá trị có thể bị gộp lại.

Cũng không dùng chuỗi literal để minh họa hai đối tượng riêng biệt rồi kỳ vọng `==` là `false`: việc dùng chung literal có thể làm ví dụ quan sát sai điều muốn dạy. Chương trình dùng `new String` chỉ để cố ý tạo hai đối tượng riêng trong phép thử.

## 7. Map đồng thời: thao tác nguyên tử khác một quy trình nguyên tử

Tập hợp nền `ConcurrentHashMap` cho phép cập nhật đồng thời và không nhận phần tử `null`. Nếu chỉ cần tập hợp đồng thời thông thường, `ConcurrentHashMap.newKeySet()` là API trực tiếp hiện có; không cần luôn viết factory từ `Collections`. [Tài liệu ConcurrentHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Với một tập hợp như vậy, khi muốn chỉ một bên nhận quyền xử lý một mã đang chưa có mặt, hãy dựa vào kết quả của chính `add`:

```java
// Minh họa, seen là Set<String> dùng ConcurrentHashMap làm nền.
if (seen.add(jobId)) {
    process(jobId);
}
```

`jobId` và `process` thuộc ứng dụng. Không viết `if (!seen.contains(jobId)) { seen.add(jobId); process(jobId); }` rồi coi cả chuỗi là nguyên tử; hai bên có thể cùng quan sát chưa có trước khi thêm.

Ví dụ chạy được phía trên chỉ minh họa kết quả thêm tuần tự, không phải bài kiểm thử tranh chấp nhiều luồng. Hợp đồng nguyên tử cần dựa vào cấu trúc đồng thời được chọn, không được suy ra chỉ từ hai dòng `true`/`false` in ra.

Ngay cả khi chỉ một lời gọi `add` nhận `true`, đó cũng chỉ là quyền ghi nhận tại một tập hợp trong bộ nhớ. Nó không bảo đảm công việc xử lý thành công đúng một lần qua lỗi tiến trình, khởi động lại hay hệ thống nhiều máy. Nếu xử lý thất bại, giữ hay xóa mã, cho thử lại hay không là chính sách riêng.

Các thao tác hàng loạt và việc duyệt cũng không tự trở thành một giao dịch bao trùm toàn tập hợp. Không dùng một lần đọc `size()` làm bảo đảm rằng ngay sau đó không luồng nào thay đổi nội dung.

## 8. Tập hợp dùng WeakHashMap: vòng đời phần tử cũng thay đổi

Một ví dụ điển hình khác là:

```java
Set<Object> weakMembers = Collections.newSetFromMap(
        new WeakHashMap<Object, Boolean>());
```

Map nền dùng khóa yếu, nên việc có mặt trong tập hợp không tự ngăn đối tượng khóa bị thu gom khi không còn được giữ bằng những tham chiếu cần thiết bên ngoài. Phần tử có thể biến mất do hoạt động thu gom rác, dù mã ứng dụng không gọi `remove`. `WeakHashMap` cũng không tự an toàn cho cập nhật nhiều luồng. [Tài liệu WeakHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/WeakHashMap.html)

Không dùng loại tập hợp này để bảo đảm “mã công việc đã xử lý phải được nhớ mãi”. Nó có ích khi sự tồn tại của đối tượng ở nơi khác mới quyết định ta còn muốn theo dõi hay không.

Cũng không viết bài kiểm thử bắt buộc `System.gc()` làm kích thước thành 0 ngay sau đó. Thời điểm thu gom không phải lịch hẹn do ứng dụng điều khiển. Nếu giữ tham chiếu mạnh trong biến hoặc cấu trúc khác, đối tượng còn có thể tiếp tục được giữ sống.

Map giá trị Boolean ở đây không phải cache kết quả với thời gian sống cấu hình được. Factory không thêm TTL, giới hạn số phần tử, tải lại khi thiếu hoặc lịch loại bỏ riêng; những đặc điểm đó chỉ tồn tại nếu cấu trúc và thiết kế khác thực sự cung cấp.

## 9. Khác gì với map.keySet()?

`map.keySet()` phù hợp khi đã có một map nghiệp vụ và muốn xem các khóa đang có. Nó không cần map rỗng và không cần giá trị map là `Boolean`. Nhưng tập khóa thông thường không hỗ trợ thêm một khóa mới vì không biết giá trị nào phải gắn với khóa đó. [Hợp đồng Map.keySet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#keySet())

`newSetFromMap` nhận một map riêng, rỗng và chuyên dùng làm kho lưu cho tập hợp. Chính vì giá trị chỉ là dấu có mặt nên `Set.add` biết cách tạo ánh xạ.

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Duyệt/xóa các khóa của map nghiệp vụ đang có dữ liệu | `map.keySet()` theo hợp đồng view của map |
| Tạo tập hợp mới có các đặc điểm của một map riêng | `Collections.newSetFromMap` với map rỗng |
| Tạo bản sao độc lập các khóa | Một tập hợp mới nhận các khóa, ví dụ `new HashSet<>(map.keySet())` |

Không lấy một map cache nghiệp vụ đang có các kết quả `true`/`false` rồi đưa vào factory để “chuyển nó thành Set”. Điều kiện rỗng sẽ bị vi phạm, và ý nghĩa dữ liệu cũng không còn đúng với dấu có mặt.

## 10. Các lỗi sử dụng cần tránh

- **Giữ hai đường sửa cùng dữ liệu:** dùng Set và backing map trực tiếp sau khi tạo. Hãy giao map riêng cho tập hợp và chỉ đưa Set cho phần còn lại của ứng dụng.
- **Dùng Boolean làm trạng thái nghiệp vụ:** tập hợp chỉ biểu diễn có/không có phần tử. Nếu cần trạng thái được phép, từ chối, đang xử lý hoặc đã xong, hãy thiết kế kiểu trạng thái rõ ràng.
- **Cho rằng factory làm map thường thành an toàn luồng:** `HashMap`, `IdentityHashMap`, `WeakHashMap` không được bổ sung cơ chế đồng thời chỉ bởi thao tác bọc.
- **Cho rằng mọi loại Set đều nhận null:** đặc điểm này theo cấu trúc nền; ví dụ ConcurrentHashMap từ chối null.
- **Sửa trường tham gia equals/hashCode của khóa đang lưu:** với cấu trúc dựa trên băm giá trị, việc tra cứu sau đó có thể không còn phù hợp. Dấu Boolean không khắc phục được thay đổi đó.
- **Đoán hiệu năng giống HashSet trong mọi trường hợp:** chi phí và chính sách giữ dữ liệu phụ thuộc map; map sắp thứ tự, map định danh và map đồng thời phục vụ các nhu cầu khác nhau.

Nếu cần tập hợp thường theo giá trị, bắt đầu từ `HashSet`. Nếu cần một đặc điểm riêng chưa có API tập hợp trực tiếp phù hợp, hãy chọn map nền và ghi rõ hợp đồng khác biệt.

## 11. Bài tập tự kiểm tra

1. Với map nền theo giá trị, thêm hai đối tượng chuỗi khác nhau nhưng cùng nội dung: có bao nhiêu phần tử? Vì sao kết quả khác tập hợp định danh?
2. Tại sao `FALSE` không phải cách biểu diễn phần tử vắng mặt trong tập hợp từ map?
3. Vì sao map phải rỗng lúc tạo và không nên được truy cập trực tiếp sau đó?
4. Thay `LinkedHashMap` trong chương trình bằng `HashMap`: phần nào của kiểm thử phải bỏ giả định về thứ tự?
5. Nếu một mã trong `seen` đã được thêm nhưng xử lý thất bại, chính sách thử lại nào phù hợp với ứng dụng? Vì sao Set tự nó không quyết định được?
6. Nếu muốn phần tử còn được nhớ dù đối tượng không còn được giữ ở nơi khác, WeakHashMap có phù hợp không?

Điều cần nhìn xuyên qua factory là sự phân công: **Set cung cấp thao tác thành viên, map quyết định đặc điểm lưu trữ, Boolean chỉ làm dấu có mặt**.
