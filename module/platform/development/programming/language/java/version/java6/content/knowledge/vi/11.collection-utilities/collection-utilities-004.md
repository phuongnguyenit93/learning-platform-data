# Không truy cập trực tiếp backing map sau khi tạo `Set`

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích tại sao `Collections.newSetFromMap(Map<E, Boolean>)` tạo được một `Set` từ một `Map` và vì sao `Map` phải rỗng.
- Giữ đúng quyền sở hữu dữ liệu: sau khi tạo `Set`, thao tác thêm, xóa, kiểm tra phần tử thông qua `Set`; không tiếp tục sử dụng tham chiếu `Map` làm backing store.
- Phân biệt `Collections.newSetFromMap(...)` với `Map.keySet()`, biết khi nào nên dùng `HashSet`, `LinkedHashSet` hoặc `ConcurrentHashMap.newKeySet()`.
- Nhận diện những lỗi dễ mắc về giá trị `Boolean`, tính đồng thời và vòng đời của phần tử khi dùng `WeakHashMap`.

## 1. Backing map là gì?

`Set<E>` biểu diễn một tập hợp phần tử không trùng lặp. Một cách hiện thực tập hợp là đặt mỗi phần tử vào **khóa (key)** của `Map<E, Boolean>`; giá trị `Boolean` chỉ là dữ liệu phụ trợ của cách hiện thực. Khi đó:

| Thao tác qua `Set` | Ý nghĩa ở backing map |
| --- | --- |
| `set.add(e)` | Ghi khóa `e` vào map; trả `true` khi `e` mới xuất hiện theo ngữ nghĩa của set |
| `set.contains(e)` | Kiểm tra map có khóa `e` hay không |
| `set.remove(e)` | Loại bỏ khóa `e` khỏi map |
| `set.size()` / `set.clear()` | Phản ánh số khóa / xóa các ánh xạ trong map |

JDK cung cấp phương thức:

```java
public static <E> Set<E> newSetFromMap(Map<E, Boolean> map)
```

Đây là một API **vẫn được hỗ trợ trong Java hiện đại**, dùng khi cần đặc tính của một loại `Map` nhưng không có loại `Set` tương ứng phù hợp. Ví dụ: `WeakHashMap` có khóa tham chiếu yếu; nhờ đó có thể tạo một `Set` với đặc tính tham chiếu yếu.

Điều quan trọng: `Set` trả về **được backing bởi chính map đã truyền vào**, không phải bản sao độc lập. Hành vi về thứ tự, khả năng đồng thời và hiệu năng phụ thuộc vào loại map đó.

## 2. Hai ràng buộc bắt buộc phải hiểu

Theo hợp đồng của `Collections.newSetFromMap(...)`:

1. **Map phải rỗng tại thời điểm gọi factory.** Nếu map đã có phần tử, phương thức ném `IllegalArgumentException`.
2. **Sau khi factory trả về, không truy cập trực tiếp backing map nữa.** Tạo map ngay trong lời gọi và không giữ lại tham chiếu là cách đơn giản để tuân thủ quy tắc.

Cách viết đúng:

```java
Set<Object> weakSet = Collections.newSetFromMap(
        new WeakHashMap<Object, Boolean>());
```

Ở đây, mã bên ngoài chỉ giữ tham chiếu `weakSet`. Mọi thao tác nghiệp vụ sử dụng `weakSet.add(...)`, `weakSet.remove(...)`, `weakSet.contains(...)`, `weakSet.clear()`...

Cách viết dễ vi phạm hợp đồng:

```java
Map<String, Boolean> backing = new HashMap<>();
Set<String> names = Collections.newSetFromMap(backing);

names.add("An");
backing.put("Bình", null); // SAI: tiếp tục sửa backing map trực tiếp
backing.clear();           // SAI: bỏ qua API Set
```

Đoạn trên **chỉ minh họa cách dùng sai, không phải mẫu để chạy hay tái sử dụng**. `HashMap` cho phép giá trị `null`, trong khi factory quản lý giá trị phụ trợ theo cách riêng. Việc tự ghi `null`, `Boolean.FALSE`, xóa khóa hoặc thay đổi map qua đường khác có thể phá vỡ các giả định nội bộ của tập hợp, khiến kết quả các thao tác (đặc biệt giá trị trả về của `add`/`remove`) không còn đáng tin. Ngay cả khi một thay đổi trực tiếp *có vẻ* được phản ánh trong `Set`, đó cũng không phải quyền sử dụng được hợp đồng factory khuyến khích.

Tương tự, đoạn này thất bại ngay khi khởi tạo:

```java
Map<String, Boolean> prefilled = new HashMap<>();
prefilled.put("An", Boolean.TRUE);
Set<String> invalid = Collections.newSetFromMap(prefilled);
// IllegalArgumentException: map không rỗng
```

## 3. Vì sao không được dùng cả hai tham chiếu?

**Một cấu trúc dữ liệu cần một giao diện sở hữu thao tác nhất quán.** Với `newSetFromMap`, giao diện đó là `Set`.

- **Bảo toàn ngữ nghĩa:** `Set` coi khóa là phần tử; `Map` lại cho phép người gọi thao tác với giá trị phụ trợ, trong đó `HashMap` chấp nhận cả `null`. Trộn hai giao diện dễ khiến giả định về `add`, `remove` và tính hiện diện bị sai.
- **Tránh thay đổi ngoài luồng:** Mã khác giữ map có thể gọi `put`, `remove`, `clear` mà không đi qua API mà thành phần sở hữu `Set` dự kiến sử dụng. Khi gặp lỗi sẽ rất khó tìm nơi thực sự gây thay đổi.
- **Giữ đúng đặc tính của map:** Map có thứ tự, khóa yếu hoặc hỗ trợ truy cập đồng thời theo cách riêng. Thao tác sai có thể phá vỡ logic dùng những đặc tính đó; factory không tự bổ sung cơ chế đồng bộ hay kiểm soát vòng đời.
- **Giảm rủi ro khi duyệt:** Việc sửa map trong lúc duyệt set có thể tạo ra kết quả không xác định hoặc lỗi tùy cấu trúc map và ngữ cảnh; không được xem một lần chạy thành công là bảo đảm về đồng thời.

Quy tắc thực hành: **tạo map rỗng → chuyển ngay cho factory → chỉ truyền và dùng `Set` về sau**. Không lưu backing map vào field, không trả về cả map và set, không truyền map này cho một thành phần khác để cập nhật.

## 4. Ví dụ Java hoàn chỉnh, chạy được

Ví dụ sử dụng `WeakHashMap` khi *thực sự* muốn phần tử không được giữ sống chỉ bởi tập hợp. Biến `token` còn giữ tham chiếu mạnh nên kết quả trong ví dụ là xác định; ví dụ không phụ thuộc vào thời điểm garbage collector chạy. Phần cuối dùng cách ngắn gọn hiện đại để tạo tập hợp cập nhật đồng thời.

Tệp **`BackingMapSetDemo.java`**:

```java
import java.util.Collections;
import java.util.Set;
import java.util.WeakHashMap;
import java.util.concurrent.ConcurrentHashMap;

public class BackingMapSetDemo {
    public static void main(String[] args) {
        Object token = new Object();

        Set<Object> observed = Collections.newSetFromMap(
                new WeakHashMap<Object, Boolean>());

        System.out.println(observed.add(token));
        System.out.println(observed.contains(token));
        System.out.println(observed.add(token));
        System.out.println(observed.remove(token));
        System.out.println(observed.isEmpty());

        Set<String> runningTasks = ConcurrentHashMap.newKeySet();
        runningTasks.add("task-01");
        System.out.println(runningTasks.contains("task-01"));
    }
}
```

Biên dịch và chạy trên **JDK 17+**:

```bash
javac BackingMapSetDemo.java
java BackingMapSetDemo
```

Kết quả chuẩn:

```text
true
true
false
true
true
true
```

Diễn giải: lần thêm đầu thành công, kiểm tra có phần tử trả `true`, lần thêm trùng trả `false`, xóa trả `true`, tập hợp đã rỗng, và `runningTasks` nhận được mã tác vụ. Không dòng nào trong chương trình cần truy cập backing map sau khi tạo tập hợp.

**Lưu ý riêng với `WeakHashMap`:** Khi một khóa không còn tham chiếu mạnh từ bên ngoài, garbage collector *có thể* thu hồi và mục tương ứng biến mất khỏi set; không dựa vào thời điểm xảy ra sự kiện này. `WeakHashMap` không tự bảo đảm an toàn luồng. Chỉ chọn đặc tính tham chiếu yếu nếu bài toán thật sự cần nó; không dùng như tập hợp lưu trữ bền vững.

## 5. Đừng nhầm với `map.keySet()`

Hai API cùng cho ra `Set` liên quan đến `Map` nhưng có mục đích khác nhau:

| API | Mục đích | Có thể thêm qua `Set.add`? | Có dùng trực tiếp map nguồn? |
| --- | --- | --- | --- |
| `Collections.newSetFromMap(emptyMap)` | Xây dựng một tập hợp mới bằng map rỗng và **chuyển quyền sử dụng sang set** | Có, nếu backing map hỗ trợ `put` | **Không nên** sau khi tạo; đây là ràng buộc tài liệu API |
| `map.keySet()` | Lấy **view sống** của các khóa trong một map đang dùng | Với view thông thường của `Map`: **không** (`UnsupportedOperationException`) | **Có thể**, nếu chủ động muốn làm việc với map và hiểu view phản ánh thay đổi |

Ví dụ về view sống có chủ ý (khác mục đích với factory):

```java
Map<String, Integer> scores = new HashMap<>();
scores.put("An", 10);
Set<String> keys = scores.keySet();

keys.remove("An");              // Xóa cả ánh xạ "An" trong scores
System.out.println(scores.isEmpty()); // true
// keys.add("Bình");            // Không hỗ trợ thêm khóa qua view thông thường
```

Ở trường hợp này, `scores` là dữ liệu gốc; `keys` chỉ là view các khóa. Việc dùng `scores.put(...)` rồi đọc `keys` là hành vi có chủ đích của `Map.keySet()`. Tuy nhiên, không sửa map trong khi đang duyệt view nếu không có bảo đảm phù hợp từ loại map đang dùng. Nếu muốn một **bản sao tách biệt**, có thể dùng `new HashSet<>(scores.keySet())`; các cập nhật về sau đối với map không tự làm thay đổi bản sao.

**Không áp dụng máy móc** quy tắc “không đụng đến backing map” lên mọi `Map.keySet()`. Quy tắc của bài này nhắm cụ thể đến factory `Collections.newSetFromMap(...)` và việc thiết kế quyền sở hữu rõ ràng.

## 6. Chọn cách tạo `Set` phù hợp hiện nay

| Nhu cầu | Giải pháp thường nên dùng | Lý do |
| --- | --- | --- |
| Tập hợp thông thường, không yêu cầu thứ tự duyệt | `new HashSet<>()` | Rõ mục đích, không cần tạo hoặc quản lý map |
| Duy trì thứ tự chèn | `new LinkedHashSet<>()` | Có sẵn triển khai set tương ứng |
| Duyệt theo thứ tự sắp xếp | `new TreeSet<>()` | Có sẵn triển khai set có sắp xếp |
| Nhiều luồng cùng thêm/xóa phần tử | `ConcurrentHashMap.<E>newKeySet()` | Tập hợp hỗ trợ đồng thời, không phơi lộ map trung gian |
| Chỉ muốn tập hợp giữ khóa bằng tham chiếu yếu | `Collections.newSetFromMap(new WeakHashMap<E, Boolean>())` | Trường hợp có đặc tính map phù hợp mà set tiêu chuẩn không cung cấp trực tiếp |
| Đã có map nghiệp vụ và muốn xem/sửa qua tập khóa | `map.keySet()` | View sống liên kết với map; cần hiểu giới hạn thao tác |
| Cần tập khóa độc lập với map | `new HashSet<>(map.keySet())` | Sao chép các khóa tại thời điểm tạo, không phụ thuộc thay đổi map sau đó |

Với `ConcurrentHashMap.newKeySet()`, các phép thêm/xóa phần tử an toàn cho nhiều luồng theo hợp đồng của cấu trúc đồng thời, nhưng điều đó **không** biến một chuỗi nhiều thao tác thành một giao dịch nguyên tử. Không suy diễn thứ tự duyệt cố định. Đặc tính cho phép `null` cũng phụ thuộc từng loại set/map; ví dụ `ConcurrentHashMap` không chấp nhận khóa `null`.

Với `Collections.newSetFromMap(...)`, đặc tính an toàn luồng **đến từ backing map**, không phải do factory tự tạo ra. Tránh chọn một map thông thường rồi giả định set tạo từ nó tự nhiên thread-safe.

## 7. Quy trình áp dụng trong mã thực tế

1. **Xác định nhu cầu.** Nếu `HashSet`, `LinkedHashSet`, `TreeSet` hay `ConcurrentHashMap.newKeySet()` đã đáp ứng, ưu tiên cách trực tiếp đó.
2. **Chỉ dùng factory cho đặc tính map cụ thể.** Chọn `Map<E, Boolean>` rỗng, có đúng đặc tính cần dùng.
3. **Chuyển giao trong một biểu thức.** Ví dụ `Collections.newSetFromMap(new WeakHashMap<E, Boolean>())`; không tạo biến `backing` tồn tại lâu ở nơi khác.
4. **Đóng gói API.** Các thành phần khác chỉ biết `Set<E>`. Thao tác `add`, `remove`, `contains`, `clear` được thực hiện qua set.
5. **Kiểm tra các đặc tính không mặc định.** Đánh giá đồng thời, thứ tự, khả năng chấp nhận `null` và tham chiếu yếu theo tài liệu của map thực tế.
6. **Khi thật sự cần cả map và view khóa**, thiết kế quanh `Map<K,V>` và sử dụng `map.keySet()` với ý thức đó là view; không gượng dùng `newSetFromMap`.

## 8. Lỗi phổ biến cần tự kiểm tra

- **Truyền map đã có dữ liệu:** factory ném `IllegalArgumentException` ngay; nó không “chuyển đổi map đang có” thành set.
- **Giữ biến backing map để sửa tiếp:** vi phạm hướng dẫn của API ngay cả khi đoạn code biên dịch được; tránh cả truy cập qua alias khác.
- **Nhầm giá trị `Boolean` với phần tử:** phần tử của set là **key**; giá trị map không phải dữ liệu nghiệp vụ để ứng dụng tự ghi `true`/`false`/`null`.
- **Nhầm view `keySet` với set từ factory:** `map.keySet()` thông thường không hỗ trợ `add`, trong khi set từ `newSetFromMap` có thể thêm nếu map có `put`.
- **Dùng `WeakHashMap` cho dữ liệu cần tồn tại chắc chắn:** khóa có thể biến mất khi không còn được tham chiếu mạnh; không có lịch thu hồi chính xác.
- **Giả định set được tạo bằng factory là thread-safe:** phải xét loại map thật sự; cần tập hợp đồng thời phổ thông thì dùng `ConcurrentHashMap.newKeySet()`.

## 9. Tự kiểm tra hiểu biết

**Tình huống A:** Cần một tập ID tác vụ được cập nhật từ nhiều luồng; không cần giá trị đi kèm. **Chọn:** `ConcurrentHashMap.newKeySet()` rồi chỉ làm việc qua `Set`.

**Tình huống B:** Bạn có `Map<String, Integer> scores` và muốn xóa một người qua danh sách tên, để bản đồ điểm cũng cập nhật. **Chọn:** `scores.keySet().remove(name)` là một cách hợp lệ vì đây là view sống của map đã có, không phải set do factory tạo.

**Tình huống C:** Muốn set có ngữ nghĩa khóa yếu và viết:

```java
Map<Object, Boolean> m = new WeakHashMap<>();
Set<Object> s = Collections.newSetFromMap(m);
m.put(new Object(), Boolean.TRUE);
```

**Đánh giá:** Dòng cuối truy cập trực tiếp backing map sau khi tạo set, trái hướng dẫn API. Viết `Set<Object> s = Collections.newSetFromMap(new WeakHashMap<Object, Boolean>());` và chỉ gọi `s.add(...)`, đồng thời hiểu rằng phần tử có thể mất khi không còn tham chiếu mạnh bên ngoài.

## Tài liệu đối chiếu

- [`Collections.newSetFromMap` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html#newSetFromMap(java.util.Map))
- [`Map.keySet` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#keySet())
- [`ConcurrentHashMap.newKeySet` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#newKeySet())
- [`WeakHashMap` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/WeakHashMap.html)

**Ghi nhớ:** Với `Collections.newSetFromMap`, hãy **đưa vào một map rỗng rồi chỉ giữ và thao tác trên set trả về**. Với `map.keySet()`, hãy hiểu rõ đó là view sống của map gốc và sử dụng theo đúng hợp đồng khác biệt của nó.
