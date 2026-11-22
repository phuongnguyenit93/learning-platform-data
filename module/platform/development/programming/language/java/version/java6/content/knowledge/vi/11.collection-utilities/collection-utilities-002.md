# Điều kiện map ban đầu phải rỗng khi dùng Collections.newSetFromMap

## 1. Map rỗng là điều kiện tại thời điểm tạo set

`Collections.newSetFromMap(map)` tạo một `Set` sử dụng map được truyền vào làm vùng lưu trữ nền (backing map).

Điều kiện quan trọng: **map phải không chứa bất kỳ cặp khóa–giá trị nào tại thời điểm gọi phương thức**. Nếu map đã có dù chỉ một ánh xạ, phương thức ném `IllegalArgumentException`.

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.Set;

// Đoạn minh họa.
Set<String> names = Collections.newSetFromMap(
        new HashMap<String, Boolean>());
```

Sau khi tạo thành công, có thể thêm phần tử qua `names.add(...)`. Map nền lúc đó có dữ liệu là bình thường. Yêu cầu “ban đầu rỗng” không có nghĩa set phải luôn luôn rỗng.

Quy tắc này là hợp đồng hiện hành của API, không phải mẹo riêng cho một phiên bản triển khai. Xem [Collections.newSetFromMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#newSetFromMap(java.util.Map)). Phương thức có từ Java 6 và vẫn dùng được trong Java hiện nay; ví dụ trong bài chạy với Java 17 trở lên.

## 2. Set và map nền liên hệ như thế nào?

Một set biểu diễn việc phần tử có thuộc tập hợp hay không. Một map biểu diễn ánh xạ từ khóa sang giá trị. Với set tạo từ map, phần tử set được biểu diễn bằng các khóa của map:

```text
set ở phía ứng dụng       vùng lưu trữ map ở phía trong
       "An"       ─────→       khóa "An"
       "Binh"     ─────→       khóa "Binh"
```

Tham số có dạng `Map<E, Boolean>`: kiểu khóa cũng là kiểu phần tử set, còn giá trị Boolean phục vụ cách biểu diễn của bộ thích nghi. Ứng dụng thao tác qua giao diện set, không dùng giá trị Boolean như trạng thái nghiệp vụ riêng.

Chữ ký:

```java
public static <E> Set<E> newSetFromMap(Map<E, Boolean> map)
```

Đây là chữ ký API để đọc, không phải một hàm cần khai báo lại.

Điều kiện rỗng giúp bắt đầu với một vùng lưu trữ dành riêng cho set, chưa có dữ liệu map tồn tại từ mục đích khác. Cần hiểu đây là quy tắc sử dụng API; không được suy luận rằng có thể tự bỏ qua chỉ vì các khóa hiện có “có vẻ dùng được làm phần tử set”.

### Boolean.TRUE cũng không tạo ngoại lệ cho quy tắc

Các map sau đều không rỗng:

```text
{"An" → true}
{"An" → false}
{"An" → null}   nếu loại map cho phép giá trị null
```

Cả ba đều không thỏa điều kiện khởi tạo. Rỗng nghĩa là không có ánh xạ, không phải “mọi giá trị đều false”, “mọi giá trị đều true” hay “mọi giá trị đều null”.

Ngay cả việc dữ liệu sẵn có đã dùng `Boolean.TRUE` cũng không biến phương thức thành API bọc một map đang có dữ liệu.

## 3. Những khái niệm không được nhầm với rỗng

| Tình trạng | Có thỏa điều kiện map rỗng không? |
| --- | --- |
| `new HashMap<>()` vừa tạo, chưa thêm gì | Có |
| `new HashMap<>(64)` vừa tạo, chưa thêm gì | Có; dung lượng dự kiến không phải số phần tử |
| Map từng có dữ liệu nhưng hiện đã xóa hết | Có tại thời điểm gọi, nếu thật sự không còn ánh xạ |
| Map có một khóa ánh xạ tới false | Không |
| Map có một khóa ánh xạ tới null | Không |
| Map là null | Không phải map rỗng; gây `NullPointerException` |

Điều kiện xét trạng thái hiện tại, không xét lịch sử map. Dù vậy, cách dễ quản lý nhất thường là tạo một map mới ngay tại lời gọi, thay vì tận dụng lại một map từng được nhiều thành phần sử dụng.

Không xóa dữ liệu của một map đang dùng chỉ để ép điều kiện thành đúng. `clear()` là hành động làm mất mọi ánh xạ; nó không phải thao tác chuyển đổi an toàn dữ liệu map thành set.

## 4. Chương trình đầy đủ: điều kiện hợp lệ và các trường hợp bị từ chối

Lưu tệp **EmptyBackingMapDemo.java**:

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class EmptyBackingMapDemo {
    private static void rejectNonEmpty(
            String label, Boolean existingValue) {
        Map<String, Boolean> map = new HashMap<>();
        map.put("existing", existingValue);

        try {
            Collections.newSetFromMap(map);
            throw new AssertionError("Non-empty map was accepted");
        } catch (IllegalArgumentException e) {
            System.out.println(label + ": rejected");
        }
    }

    public static void main(String[] args) {
        Set<String> names = Collections.newSetFromMap(
                new HashMap<String, Boolean>(64));

        System.out.println("initially empty: " + names.isEmpty());
        System.out.println("first add: " + names.add("An"));
        System.out.println("duplicate add: " + names.add("An"));
        System.out.println("size after add: " + names.size());
        System.out.println("remove: " + names.remove("An"));
        System.out.println("empty after remove: " + names.isEmpty());

        rejectNonEmpty("true value", Boolean.TRUE);
        rejectNonEmpty("false value", Boolean.FALSE);
        rejectNonEmpty("null value", null);

        try {
            Collections.<String>newSetFromMap(null);
            throw new AssertionError("Null map was accepted");
        } catch (NullPointerException e) {
            System.out.println("null map: rejected");
        }

        Set<String> readOnlyBacked = Collections.newSetFromMap(
                Map.<String, Boolean>of());
        try {
            readOnlyBacked.add("An");
            throw new AssertionError("Unmodifiable map accepted add");
        } catch (UnsupportedOperationException e) {
            System.out.println("empty but unmodifiable: cannot add");
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac EmptyBackingMapDemo.java
java EmptyBackingMapDemo
```

Stdout:

```text
initially empty: true
first add: true
duplicate add: false
size after add: 1
remove: true
empty after remove: true
true value: rejected
false value: rejected
null value: rejected
null map: rejected
empty but unmodifiable: cannot add
```

### Những điều ví dụ chứng minh

Map mới có dung lượng dự kiến 64 vẫn không có phần tử, nên hợp lệ. Sau khi tạo, mọi thay đổi đều đi qua set.

`add("An")` lần đầu thành công; lần thứ hai không làm tăng số phần tử. Việc set trở thành không rỗng sau lần thêm đầu tiên không vi phạm điều kiện đã kiểm tra lúc khởi tạo.

Ba map trong `rejectNonEmpty` đều bị từ chối bất kể giá trị Boolean. Chương trình không sử dụng lại chúng làm map nền của một set đã tạo thành công.

Đoạn cuối minh họa một giới hạn khác: **rỗng chưa đủ để bảo đảm mọi thao tác sửa set đều được hỗ trợ**. `Map.of()` tạo map không thể sửa, nên set dùng nó làm nền không thêm được phần tử. Đây là vấn đề về khả năng sửa, khác với điều kiện rỗng. Xem [đặc tính Map.of](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#of()).

## 5. Sau khi tạo thành công, không tiếp tục dùng map trực tiếp

Hợp đồng của `newSetFromMap` còn yêu cầu tránh truy cập trực tiếp map sau khi phương thức trả về. Cách dùng rõ ràng nhất là:

```java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

// Phương thức thành viên minh họa.
static <E> Set<E> newIdentitySet() {
    return Collections.newSetFromMap(
            new IdentityHashMap<E, Boolean>());
}
```

Ở đây map:

1. Được tạo mới trong trạng thái rỗng.
2. Được truyền ngay vào phương thức tạo set.
3. Không để lại một tham chiếu map cho phần còn lại của ứng dụng.
4. Chỉ được sử dụng thông qua set trả về.

Sau đó thêm dữ liệu:

```java
// Đoạn minh họa; initialElements là tập dữ liệu nguồn.
Set<String> names = newIdentitySet();
names.addAll(initialElements);
```

Không làm theo kiểu “tạo set xong rồi nạp dữ liệu bằng `map.putAll`”. Cũng không giữ cả set và map như hai giao diện nghiệp vụ để tùy ý đọc, ghi qua lại.

Đây không chỉ là vấn đề đa luồng. Ngay cả chương trình một luồng cũng cần tôn trọng quyền quản lý vùng lưu trữ đã bàn giao cho set. Không có ngoại lệ trong hợp đồng cho việc truy cập map trực tiếp chỉ vì ứng dụng đang chạy một luồng.

### Kiểm tra isEmpty trước chưa giải quyết quyền sở hữu

Tự kiểm tra `map.isEmpty()` trước lời gọi không thay thế việc tạo và bàn giao map đúng cách. Nếu map đang chia sẻ, một thành phần khác có thể thêm dữ liệu giữa lần kiểm tra và lần tạo set, hoặc tiếp tục sử dụng nó sau đó.

Map hỗ trợ đồng thời cũng không làm trình tự này tự trở thành một thao tác khởi tạo nguyên tử. Hãy hoàn tất cấu trúc set trước khi chia sẻ set; không chia sẻ map nền ra ngoài.

## 6. Tại sao dùng map có hành vi đặc biệt?

Nếu chỉ cần set dựa trên băm thông thường, dùng `HashSet` thường diễn tả trực tiếp hơn việc tự tạo `HashMap` rồi gọi `newSetFromMap`.

Tiện ích này hữu ích khi muốn set có đặc tính tương ứng với một kiểu map, ví dụ set phân biệt đối tượng theo danh tính với `IdentityHashMap`.

`IdentityHashMap` so sánh khóa theo `==`, vì vậy hai đối tượng khác nhau dù `equals` trả true vẫn là hai phần tử khác nhau. Đây là ngữ nghĩa đặc biệt, chỉ dùng khi bài toán thật sự cần nhận diện từng đối tượng; không xem nó là set thông thường dựa trên `equals`. Tham khảo [IdentityHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/IdentityHashMap.html).

Điều kiện map rỗng vẫn giữ nguyên với loại map đặc biệt. Cách đúng để khởi tạo có dữ liệu là tạo set từ map mới rỗng, rồi thêm các phần tử **qua set**, theo ngữ nghĩa của set đó.

### Ví dụ chạy: nạp dữ liệu sau khi tạo identity set

Lưu tệp **InitializeIdentitySetDemo.java**:

```java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public class InitializeIdentitySetDemo {
    public static void main(String[] args) {
        String first = new String("same");
        String second = new String("same");
        List<String> initial = List.of(first, second);

        Set<String> seen = Collections.newSetFromMap(
                new IdentityHashMap<String, Boolean>());
        seen.addAll(initial);

        System.out.println("equal contents: " + first.equals(second));
        System.out.println("same reference: " + (first == second));
        System.out.println("identity set size: " + seen.size());
        System.out.println("add same reference again: " + seen.add(first));
    }
}
```

Chạy:

```shell
javac InitializeIdentitySetDemo.java
java InitializeIdentitySetDemo
```

Stdout:

```text
equal contents: true
same reference: false
identity set size: 2
add same reference again: false
```

`new String` trong ví dụ được dùng có chủ ý để tạo hai đối tượng khác nhau cho việc quan sát danh tính, không phải khuyến nghị tạo chuỗi dư thừa trong mã ứng dụng.

Điểm chính là thứ tự khởi tạo: map rỗng → tạo set → thêm dữ liệu qua set. Không nạp `first` và `second` vào map rồi mới gọi phương thức tạo set.

## 7. Nếu đã có một map chứa dữ liệu

Trước tiên phân biệt nhu cầu thật:

| Nhu cầu | Cách diễn đạt phù hợp |
| --- | --- |
| Chỉ muốn xem tập các khóa đang có và phản ánh thay đổi của map | `existing.keySet()` |
| Muốn một set độc lập về vùng chứa, lấy khóa hiện tại theo ngữ nghĩa thông thường | `new HashSet<>(existing.keySet())` |
| Muốn set có ngữ nghĩa đặc biệt của một map nền | Tạo map nền mới rỗng, tạo set, rồi thêm dữ liệu qua set |
| Chỉ cần set thông thường mới | `new HashSet<>()` |

`keySet()` là khung nhìn, không phải một set độc lập. Việc xóa khóa qua khung nhìn có thể làm mất ánh xạ trong map tương ứng; giao diện `Map.keySet()` không hỗ trợ thêm khóa bằng `add` hoặc `addAll` vì không có giá trị map tương ứng để thêm. Xem [Map.keySet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#keySet()).

Nếu tạo `HashSet` từ khóa, set mới có ngữ nghĩa `equals/hashCode` của `HashSet`. Khi nguồn có ngữ nghĩa khóa đặc biệt như `IdentityHashMap`, việc đổi sang `HashSet` có thể gộp các đối tượng mà nguồn coi là khác nhau. Hãy chọn trước ngữ nghĩa mong muốn, không chỉ chọn cách làm hết ngoại lệ.

Mẫu nạp từ nguồn có sẵn:

```java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

// Đoạn minh họa; existing là nguồn dữ liệu, không phải map nền.
Set<Object> result = Collections.newSetFromMap(
        new IdentityHashMap<Object, Boolean>());
result.addAll(existing.keySet());
```

Map mới bên trong phục vụ riêng set. `existing` vẫn là nguồn dữ liệu riêng, không bị `clear()` và không được bàn giao làm vùng lưu trữ của set.

Bản sao set chỉ tách vùng chứa: đối tượng khóa vẫn là những đối tượng được tham chiếu từ nguồn. Nếu chúng có thể thay đổi, cần hiểu tác động của việc thay đổi đó đối với ngữ nghĩa tập hợp được chọn.

## 8. Liên hệ với set dùng đồng thời

Nếu mục tiêu hiện tại chỉ là set dùng đồng thời dựa trên băm, Java hiện đại có cách trực tiếp:

```java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

// Đoạn minh họa.
Set<String> visited = ConcurrentHashMap.newKeySet();
```

Cách này tránh để ứng dụng tự quản lý tham chiếu map nền. Nó không đòi hỏi bạn nạp sẵn dữ liệu vào một map rồi chuyển đổi. Khi cần dữ liệu ban đầu, thêm qua set sau khi tạo.

`ConcurrentHashMap.newKeySet()` là API hiện hành có từ Java 8; xem [tài liệu newKeySet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#newKeySet()). Đây là lựa chọn theo mục đích sử dụng, không làm thay đổi tiền điều kiện của `Collections.newSetFromMap` khi bạn chọn dùng phương thức đó.

Không suy ra rằng một map rỗng bất kỳ sẽ tạo set an toàn giữa nhiều luồng. Đặc tính của vùng lưu trữ nền vẫn quan trọng; việc tuân thủ điều kiện rỗng không tự thêm cơ chế đồng bộ.

## 9. Những lỗi phổ biến và cách sửa đúng ý định

- **Nạp map trước vì muốn set có phần tử ngay:** tạo set trước, sau đó `addAll` qua set.
- **Cho rằng giá trị true thì hợp lệ:** mọi ánh xạ đều làm map không rỗng; đổi giá trị không giải quyết điều kiện.
- **Xem map null là rỗng:** cần một đối tượng map thực sự.
- **Dùng Map.of() vì nó rỗng, rồi mong thêm được:** chọn map hỗ trợ sửa nếu set cần thay đổi.
- **Gọi clear() trên map đang giữ dữ liệu nghiệp vụ:** không dùng xóa dữ liệu làm bước chuyển đổi; tạo vùng lưu trữ mới.
- **Giữ map để kiểm tra hoặc cập nhật sau khi tạo set:** chỉ công bố set, không công bố map nền.
- **Dùng HashSet thay identity set mà không xem xét ngữ nghĩa:** có thể gộp nhầm các đối tượng khác danh tính.

## 10. Tự thực hành

1. Một `HashMap` có dung lượng dự kiến 100 nhưng chưa thêm khóa nào có dùng được không? Giải thích dựa trên số ánh xạ, không dựa trên cấu hình dung lượng.
2. Map có duy nhất một khóa mang giá trị `Boolean.FALSE` có thỏa điều kiện không? Đổi sang `Boolean.TRUE` có giúp không?
3. Viết một hàm tạo set theo danh tính có dữ liệu ban đầu, bảo đảm không giữ tham chiếu map nền và chỉ nạp dữ liệu qua set.
4. Nếu muốn tập khóa của một map đang có dữ liệu tiếp tục phản ánh map, so sánh `keySet()` với một `HashSet` mới từ khóa.
5. Tìm trong một thiết kế giả định xem ai đang giữ map sau khi nó được bàn giao cho `newSetFromMap`. Sửa quyền sở hữu thay vì chỉ thêm một lần gọi `isEmpty()`.

Điều cần bảo đảm là đúng thứ tự và đúng quyền sở hữu: tạo map rỗng dành riêng cho set, tạo set, rồi thực hiện các thao tác dữ liệu thông qua set.
