# Đánh giá chi phí sao chép, cấp phát và tái sử dụng khi thiết kế dữ liệu chỉ đọc trong Java

## Mục tiêu bài học

Thiết kế dữ liệu **chỉ đọc (read-only)** không đơn thuần là thay một `ArrayList` bằng `List.copyOf`. Mỗi cách bảo vệ dữ liệu có sự đánh đổi giữa **an toàn trước thay đổi của nguồn**, **số lần duyệt và sao chép**, **cấp phát bộ nhớ**, **vòng đời đối tượng** và **khả năng tái sử dụng**.

Từ Java 10, `List.copyOf`, `Set.copyOf` và `Map.copyOf` hỗ trợ tạo collection không cho sửa từ nguồn có sẵn. Các phương thức này, cùng `List.of`/`Set.of`/`Map.of`, `Collections.unmodifiableXxx` và collector không cho sửa, đều vẫn phù hợp với Java hiện đại. Không có một lựa chọn tối ưu cho mọi tình huống; cần hiểu **hợp đồng ngữ nghĩa trước**, sau đó mới đánh giá hiệu năng.

Sau bài này, bạn sẽ:

- Phân biệt *snapshot*, *unmodifiable view*, collection mutable và immutable object.
- Nhận diện công việc phát sinh khi sao chép `List`, `Set` hoặc `Map`: đọc nguồn, kiểm tra dữ liệu, tạo lưu trữ, giữ tham chiếu và cấp phát.
- Giải thích vì sao `copyOf` **có thể** tái sử dụng một collection không cho sửa, nhưng không được dựa vào danh tính đối tượng hoặc một số lần cấp phát cố định.
- Tránh copy nhiều lần trên đường xử lý nóng, đồng thời không hy sinh yêu cầu defensive copy ở ranh giới sở hữu dữ liệu.
- Đánh giá chi phí một cách đo lường được bằng benchmark và profiler thay vì đoán từ tên API.
- Viết ví dụ Java 17+ cho một value object công bố danh sách không cho sửa.

## 1. Đầu tiên cần xác định “chỉ đọc” nghĩa là gì

Có ít nhất bốn yêu cầu thường bị gom làm một:

| Yêu cầu | Ví dụ | Điều thực sự được bảo đảm |
| --- | --- | --- |
| Không thể sửa qua tham chiếu nhận được | `Collections.unmodifiableList(source)` | Thao tác sửa qua wrapper bị từ chối; **nguồn vẫn có thể thay đổi** |
| Có snapshot cấu trúc ở một thời điểm | `List.copyOf(source)` | Kết quả không phản ánh các thay đổi cấu trúc về sau của nguồn |
| Có tập giá trị tạo sẵn, không cho sửa | `List.of("A", "B")` | Không cần một collection mutable làm nguồn |
| Trạng thái dữ liệu bất biến sâu | List chứa các value object bất biến | Cần bảo đảm cả **phần tử bên trong** không đổi, không chỉ cấu trúc List |

Đây là khác biệt về **đúng/sai nghiệp vụ**, không chỉ tối ưu vi mô. Không nên chọn view rẻ hơn nếu hợp đồng thực sự yêu cầu snapshot. Ngược lại, không cần tạo snapshot lặp đi lặp lại nếu người dùng cố ý muốn quan sát thay đổi trực tiếp của một nguồn đang được quản lý.

### Ví dụ snapshot và view

~~~java
var source = new ArrayList<>(List.of("An", "Binh"));

var snapshot = List.copyOf(source);
var view = Collections.unmodifiableList(source);

source.add("Chi");

System.out.println(snapshot); // [An, Binh]
System.out.println(view);     // [An, Binh, Chi]
~~~

Cả hai không cho sửa thông qua tham chiếu trả về. Nhưng `view` vẫn dựa trên `source`, trong khi `snapshot` giữ cấu trúc dữ liệu khi gọi `copyOf`. Tính đúng đắn của ứng dụng quyết định xem việc nhìn thấy `"Chi"` có mong muốn hay không.

## 2. So sánh lựa chọn và nguồn chi phí

| Cách tạo | Có sao chép cấu trúc nguồn? | Có thể thấy nguồn đổi về sau? | Đặc điểm cần đánh giá |
| --- | --- | --- | --- |
| `List.of(a, b)` | Không sao chép từ một collection nguồn | Không có collection nguồn được truyền vào | Tạo collection không cho sửa từ phần tử; implementation có thể tối ưu cho số lượng nhỏ |
| `List.copyOf(source)` | Có ngữ nghĩa snapshot; có thể tái sử dụng nguồn phù hợp | Không phản ánh thay đổi cấu trúc của nguồn | Duyệt/kiểm tra/cấp phát có thể cần thiết; phụ thuộc nguồn |
| `Set.copyOf(source)` | Có ngữ nghĩa snapshot và loại phần tử trùng | Không phản ánh thay đổi cấu trúc của nguồn | Có thêm vấn đề uniqueness, `equals`/`hashCode`, không cam kết thứ tự |
| `Map.copyOf(source)` | Có ngữ nghĩa snapshot ánh xạ; có thể tái sử dụng | Không phản ánh thay đổi ánh xạ của nguồn | Đọc entry, kiểm tra khóa/value khác null, tổ chức ánh xạ |
| `Collections.unmodifiableList(source)` | Không tạo snapshot nội dung | **Có** | Thường là wrapper/view nhẹ, nhưng không cô lập nguồn |
| `Collections.unmodifiableMap(source)` | Không tạo snapshot ánh xạ | **Có** | View không cho sửa, vẫn thấy thao tác trên Map gốc |
| `new ArrayList<>(source)` | Tạo bản sao cấu trúc List mới | Không phản ánh sửa cấu trúc nguồn | Kết quả **mutable**, thích hợp khi cần tiếp tục sửa |
| `new ArrayList<>(source)` rồi `unmodifiableList(...)` | Có sao chép rồi bọc view | Không, nếu không còn tham chiếu khác có thể sửa bản sao | Có thể dùng nếu cần giữ `null` mà `List.copyOf` từ chối |

**Quan trọng:** không coi “có sao chép” là số đối tượng hay số byte cố định. Đây là đặc tính về *hợp đồng dữ liệu*; số object, kiểu cấu trúc lưu trữ, chiến lược kiểm tra và khả năng tối ưu là chi tiết triển khai thay đổi theo JDK và loại nguồn.

## 3. Chi phí của `copyOf` phụ thuộc vào nguồn

Các factory phổ biến:

~~~java
List<String> names = List.copyOf(sourceNames);
Set<String> roles = Set.copyOf(sourceRoles);
Map<String, Integer> scores = Map.copyOf(sourceScores);
~~~

### 3.1. Nguồn mutable: thường cần đọc và đóng gói dữ liệu

Nếu nguồn là một `ArrayList` có thể thay đổi, kết quả `List.copyOf(source)` phải giữ nội dung cấu trúc ổn định sau khi lời gọi hoàn thành. Vì thế triển khai không thể đơn giản đặt một wrapper trực tiếp lên `source` rồi vẫn bảo đảm snapshot khi nguồn tiếp tục `add`/`remove`.

Trong trường hợp thông thường, để hình thành snapshot, runtime cần **đọc các phần tử và lưu tham chiếu vào cấu trúc kết quả**. Với `n` phần tử, lượng công việc và dung lượng lưu trữ liên quan đến số phần tử, thay vì chỉ với tên biến. Tuy nhiên:

- Không có một con số **thời gian hay byte/cấp phát chuẩn** được Java API hứa hẹn.
- Chi phí thực tế phụ thuộc kiểu nguồn, số lượng phần tử, cách triển khai, phân bố bộ nhớ, JIT và GC.
- `List.copyOf` cấm phần tử `null`; việc kiểm tra và xây dựng kết quả là một phần quan trọng của hợp đồng.
- Các object phần tử **không bị deep copy**. Sao chép danh sách 10.000 phần tử không có nghĩa tự sao chép 10.000 object nghiệp vụ bên trong; thông thường những **tham chiếu** được lưu giữ.

Với `Set.copyOf`, cần xử lý tính duy nhất của phần tử; `Set.copyOf(List.of("A","A"))` chỉ giữ một giá trị `"A"`. Với `Map.copyOf`, cần bảo toàn cặp ánh xạ và từ chối khóa hoặc giá trị `null`. Các trường hợp này có chi phí khác List và còn phụ thuộc chất lượng `equals`/`hashCode` của phần tử/khóa.

### 3.2. Nguồn đã không cho sửa: có thể tái sử dụng

~~~java
var original = List.of("A", "B");
var again = List.copyOf(original);
~~~

Khi nguồn là một unmodifiable List thích hợp, `List.copyOf` **có thể** tái sử dụng cùng instance, thay vì sao chép nội dung. Các factory `Set.copyOf` và `Map.copyOf` cũng có khả năng tái sử dụng nguồn không cho sửa phù hợp theo hợp đồng của chúng.

**Không coi đây là bảo đảm `original == again`** và cũng không dựa vào việc “không cấp phát”. Những collection được tạo bởi các factory này có tính chất **value-based**: code không nên phụ thuộc reference equality, `System.identityHashCode` hay dùng chúng như đối tượng để đồng bộ hóa. Nếu muốn so sánh nội dung, hãy dùng `equals`.

`Collections.unmodifiableList(mutableSource)` dù ngăn sửa qua wrapper nhưng vẫn là một **view có thể thay đổi nội dung quan sát được** khi `mutableSource` bị sửa. Vì thế không được mặc định `List.copyOf(view)` chỉ trả lại `view` mà vẫn bảo đảm snapshot. Tính không cho sửa qua một tham chiếu **khác** với việc nội dung không thể thay đổi từ tham chiếu khác.

### 3.3. Có nhiều tầng dữ liệu thì “copy” ở tầng nào?

~~~java
var source = new ArrayList<ArrayList<String>>();
var inner = new ArrayList<>(List.of("A"));
source.add(inner);

var outer = List.copyOf(source);
inner.add("B");

System.out.println(outer.get(0)); // [A, B]
~~~

`outer` không cho thêm/xóa phần tử, nhưng nó vẫn tham chiếu đến `inner`, một `ArrayList` mutable. Đây là **shallow snapshot** của danh sách bên ngoài. Nếu yêu cầu bất biến xuyên suốt, phải chủ động copy hoặc chuyển đổi từng phần tử và dùng value object phù hợp.

Ví dụ có thể xử lý từng List con bằng `List.copyOf` rồi tạo List ngoài bằng `List.copyOf`, sau khi kiểm tra chính sách `null`; tuy nhiên cách làm này có thêm chi phí sao chép. Hãy đánh giá nhu cầu bảo vệ **từng tầng**, không chỉ mỗi tầng ngoài.

## 4. Đánh đổi giữa cấp phát và vòng đời đối tượng

### 4.1. Allocation không đồng nghĩa ngay với hiệu năng kém

Một snapshot mới có thể tạo thêm object hoặc mảng lưu trữ; nhiều snapshot sống ngắn có thể góp phần gây áp lực lên bộ cấp phát và GC. Nhưng từ đây **không thể** kết luận một API luôn chậm hơn API khác:

- JIT có thể tối ưu các đường đi cụ thể, tùy điều kiện thực tế.
- Độ lớn collection và chi phí phần tử/mapper có thể lấn át chi phí wrapper.
- GC hiện đại tối ưu rất nhiều trường hợp object ngắn hạn; kết quả cần đo bằng tải ứng dụng tương ứng.
- Việc bỏ một defensive copy để tiết kiệm allocation có thể tạo lỗi dữ liệu lớn hơn mọi lợi ích đo được.

Khi so sánh, cần xác định **throughput**, **latency**, **allocation rate** hoặc **heap footprint** mới là mục tiêu. Các mục tiêu có thể cho kết quả khác nhau.

### 4.2. Copy nhiều lần có thể là chi phí thừa

~~~java
List<String> source = getNames();

// Thiết kế có thể tạo nhiều snapshot không cần thiết:
for (int i = 0; i < 100; i++) {
    useNames(List.copyOf(source));
}
~~~

Nếu `source` mutable và không đổi trong cả khoảng xử lý, mỗi lần gọi có thể phát sinh công việc sao chép hoặc kiểm tra lặp lại. Cách thường rõ hơn:

~~~java
List<String> namesSnapshot = List.copyOf(source);

for (int i = 0; i < 100; i++) {
    useNames(namesSnapshot);
}
~~~

Các đoạn này chỉ là **minh họa**: `getNames()`, `useNames(...)` cần được định nghĩa trong chương trình thực tế. Hoisting snapshot ra ngoài vòng lặp chỉ đúng khi ta cố ý giữ **cùng một phiên bản nội dung** trong 100 lần dùng. Nếu yêu cầu là đọc các cập nhật mới nhất từ nguồn ở mỗi lần lặp, hai đoạn không tương đương ngữ nghĩa.

### 4.3. Tạo snapshot đúng ranh giới sở hữu

Một thiết kế tốt thường:

1. Nhận dữ liệu mutable từ phía gọi.
2. Xác thực dữ liệu theo hợp đồng API.
3. Tạo **một defensive snapshot** tại constructor/factory hoặc ranh giới đưa dữ liệu vào đối tượng.
4. Giữ snapshot đó trong trường `final` khi phù hợp.
5. Trả lại chính tham chiếu snapshot không cho sửa qua getter, **không tạo lại snapshot mỗi lần đọc**.

Phương án này tránh việc bên ngoài thay đổi collection đầu vào sau khi khởi tạo object, đồng thời tránh copy lặp lại mỗi lần gọi getter.

Không có nghĩa mọi getter cần dùng `copyOf`: nếu đối tượng đã sở hữu một unmodifiable snapshot và bảo đảm không lộ con đường sửa khác, getter có thể trả lại tham chiếu đó.

## 5. Chương trình minh họa Java 17+ có thể chạy

Ví dụ minh họa snapshot, view, collection tạo sẵn, sao chép tại constructor, loại trùng của Set, snapshot Map và giới hạn shallow copy. Không đo thời gian bằng một phép đo đơn lẻ vì output thời gian sẽ thiếu ổn định và dễ dẫn đến kết luận sai.

Lưu toàn bộ mã vào **ReadOnlyCostDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ReadOnlyCostDemo {
    record Catalog(List<String> tags) {
        Catalog {
            tags = List.copyOf(tags); // Defensive snapshot ở ranh giới tạo object
        }
    }

    private static void checkUpdate(List<String> list) {
        try {
            list.add("Moi");
            System.out.println("snapshot update: allowed");
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                    "snapshot update: UnsupportedOperationException"
            );
        }
    }

    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("An", "Binh"));
        var snapshot = List.copyOf(source);
        var liveView = Collections.unmodifiableList(source);

        source.add("Chi");

        System.out.println("source: " + source);
        System.out.println("snapshot: " + snapshot);
        System.out.println("view: " + liveView);
        checkUpdate(snapshot);

        var fixed = List.of("Java", "SQL");
        var copied = List.copyOf(fixed);
        // So sánh theo nội dung, không theo danh tính object.
        System.out.println("logical content same: " + fixed.equals(copied));

        var catalogSource = new ArrayList<>(List.of("Backend", "Core"));
        var catalog = new Catalog(catalogSource);
        catalogSource.add("Extra");
        System.out.println("catalog tags: " + catalog.tags());
        System.out.println("catalog read size: " + catalog.tags().size());

        var unique = Set.copyOf(List.of("A", "A", "B"));
        System.out.println("unique size: " + unique.size());

        var sourceMap = new HashMap<String, Integer>();
        sourceMap.put("an", 9);
        var mapCopy = Map.copyOf(sourceMap);
        sourceMap.put("binh", 8);

        System.out.println("map snapshot size: " + mapCopy.size());
        System.out.println("map source size: " + sourceMap.size());

        var mutableElement = new StringBuilder("old");
        var shallow = List.copyOf(List.of(mutableElement));
        mutableElement.append("-new");
        System.out.println("shallow element: " + shallow.get(0));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file bằng JDK 17 trở lên:

~~~bash
javac ReadOnlyCostDemo.java
java ReadOnlyCostDemo
~~~

Kết quả chính xác:

~~~text
source: [An, Binh, Chi]
snapshot: [An, Binh]
view: [An, Binh, Chi]
snapshot update: UnsupportedOperationException
logical content same: true
catalog tags: [Backend, Core]
catalog read size: 2
unique size: 2
map snapshot size: 1
map source size: 2
shallow element: old-new
~~~

Giải thích:

- `snapshot` giữ hai phần tử ban đầu, còn `liveView` theo sát `source`; đó là khác biệt **ngữ nghĩa**, không thể hoán đổi chỉ vì một cách có vẻ nhẹ hơn.
- `checkUpdate(snapshot)` chứng minh collection kết quả không cho sửa.
- `fixed.equals(copied)` chứng minh nội dung bằng nhau, **không** đưa ra giả định `List.copyOf` có tạo object mới hay tái sử dụng.
- `Catalog` dùng compact constructor của record để tạo snapshot **một lần khi khởi tạo**; sửa `catalogSource` sau đó không làm `catalog.tags()` thay đổi. Các lần đọc `catalog.tags()` chỉ dùng giá trị đã lưu trong record, không gọi `copyOf` lại.
- `Set.copyOf` loại giá trị trùng. Output chỉ in `size()`, không phụ thuộc thứ tự duyệt của Set.
- `Map.copyOf` giữ snapshot ánh xạ lúc gọi. Output chỉ in `size()`, không phụ thuộc thứ tự duyệt Map.
- `shallow` là List không cho sửa nhưng `StringBuilder` bên trong vẫn mutable; thay đổi object bên ngoài vẫn được quan sát.

Trong chương trình, phần tử của `Catalog` đều là `String` bất biến. Nếu record chứa các object mutable, việc tạo `List.copyOf` ở constructor **chưa đủ** để bảo đảm bất biến sâu.

## 6. Khi nào `List.of` hiệu quả hơn việc tự tạo List rồi copy?

Nếu đã biết rõ các giá trị:

~~~java
var tags = List.of("java", "api", "core");
~~~

thường dễ hiểu hơn:

~~~java
var temp = new ArrayList<String>();
temp.add("java");
temp.add("api");
temp.add("core");
var tags = List.copyOf(temp);
~~~

Dòng đầu tránh việc ứng dụng **tự tạo một collection mutable trung gian** rồi chuyển thành unmodifiable collection, đồng thời diễn đạt rõ rằng dữ liệu được định nghĩa cố định tại chỗ. Tuy vậy, không từ đó suy ra mọi biểu thức `List.of` luôn cấp phát ít hơn hoặc nhanh hơn trong mọi hoàn cảnh; bytecode, runtime và tối ưu JIT đều có thể ảnh hưởng.

Tương tự, với các cặp khóa/giá trị cố định, có thể dùng `Map.of` hoặc `Map.ofEntries` thay cho việc tự xây `HashMap` rồi `Map.copyOf`. Nếu nguồn đã là một `Collection` hoặc `Map` do module khác cung cấp, `copyOf` có mục đích rõ ràng hơn và thường ít code hơn việc chuyển thủ công.

## 7. `copyOf` và unmodifiable view: không thể tối ưu khi đổi sai hợp đồng

Ví dụ một dịch vụ công bố danh sách người dùng có thể cập nhật:

~~~java
var source = new ArrayList<>(List.of("An"));
var view = Collections.unmodifiableList(source);

source.add("Binh");

System.out.println(view); // [An, Binh]
~~~

Ở đây view phản ánh nguồn và không hỗ trợ sửa thông qua tham chiếu view. Nếu yêu cầu của consumer là “đọc trạng thái mới nhất”, việc tạo snapshot một lần sẽ cho **dữ liệu cũ**. Do đó snapshot **không luôn thay thế được view**.

Ở chiều ngược lại, nếu yêu cầu là “kết quả không đổi sau khi trả về”, thì:

~~~java
var source = new ArrayList<>(List.of("An"));
var snapshot = List.copyOf(source);

source.add("Binh");
System.out.println(snapshot); // [An]
~~~

View của nguồn không đáp ứng hợp đồng đó. Việc chọn view chỉ để tránh copy có thể tạo bug khó kiểm soát, nhất là khi consumer dùng danh sách ở thời điểm khác với producer.

Một lựa chọn hợp lý trong một số thiết kế là **sở hữu riêng một collection mutable** không thoát khỏi module, cập nhật nó có kiểm soát, và chỉ trả một view không cho sửa. Tuy nhiên, code khác quan sát qua view sẽ thấy thay đổi về sau; đó phải là hành vi được mô tả rõ trong API.

## 8. Tái sử dụng snapshot thay vì sao chép lặp lại

### 8.1. Snapshot có thể được dùng chung giữa nhiều consumer

Khi dữ liệu thay đổi không thường xuyên, một module có thể tạo **một phiên bản snapshot không cho sửa**, rồi phân phối tham chiếu đó đến nhiều consumer. Điều này giúp tránh việc mỗi consumer lại phải copy toàn bộ dữ liệu.

Ý tưởng:

~~~java
final class CatalogService {
    private List<String> current = List.of();

    public synchronized void replaceAll(List<String> names) {
        current = List.copyOf(names);
    }

    public synchronized List<String> currentSnapshot() {
        return current; // Đã không cho sửa, không cần copy mỗi lần đọc
    }
}
~~~

Đây là **đoạn minh họa đặt trong file Java thích hợp**, không phải chương trình độc lập. Các phương thức synchronized minh họa cách truy cập được phối hợp để trường `current` được công bố nhất quán. Hợp đồng của API là mỗi lần gọi `currentSnapshot()` nhận **một phiên bản**: sau `replaceAll`, những lời gọi sau có thể nhận bản mới, còn consumer đã giữ snapshot cũ vẫn đọc bản cũ.

Với nhu cầu chỉ thay thế tham chiếu snapshot và đọc không chặn, một thiết kế khác có thể dùng `volatile List<String>` (hoặc `AtomicReference<List<String>>`) cùng với việc xây snapshot trước khi công bố. Cần bảo đảm **safe publication**, quy tắc cập nhật và lifetime của dữ liệu; unmodifiable collection **không tự động giải quyết mọi vấn đề đồng thời**.

### 8.2. Snapshot được tính trước có ích khi đọc nhiều hơn ghi

Nếu một cấu hình có hàng nghìn lượt đọc giữa hai lần cập nhật, việc tạo snapshot **một lần khi cập nhật** có thể giảm công việc so với copy ở từng lượt đọc. Ngược lại, nếu tập dữ liệu rất lớn và thay đổi liên tục, việc tạo lại toàn bộ snapshot mỗi lần cập nhật có thể đáng kể.

Đó là một đánh đổi giữa:

- **Read path:** cách nhanh chóng lấy nội dung đã công bố, thường có lợi khi tái sử dụng một snapshot.
- **Write/update path:** công việc tạo phiên bản mới, có thể bao gồm sao chép và xác thực.
- **Consistency:** consumer nhìn một phiên bản cố định hay cần thấy cập nhật ngay.
- **Memory retention:** có bao nhiêu phiên bản snapshot cũ còn đang được các consumer giữ tham chiếu.

Không nên chỉ tính chi phí của `copyOf` trong một lời gọi rồi bỏ qua tần suất gọi và vòng đời snapshot.

## 9. Ghi nhớ thêm về Set, Map, `null` và phần tử trùng

### 9.1. `Set.copyOf` phải bảo toàn tính duy nhất

~~~java
var source = List.of("A", "A", "B");
var unique = Set.copyOf(source);

System.out.println(unique.size()); // 2
~~~

`Set.copyOf` loại các phần tử trùng nhau theo `equals` và có thể giữ một đại diện bất kỳ trong các object được xem là bằng nhau. Không dựa vào thứ tự duyệt hoặc cho rằng phần tử đầu tiên/ cuối cùng luôn được giữ.

Việc tổ chức Set thường liên quan thêm đến so sánh phần tử và hashing. Chi phí sẽ chịu tác động của kiểu phần tử, chất lượng `hashCode`, số lượng phần tử trùng và implementation. Không nên kết luận rằng `Set.copyOf` có cùng chi phí với `List.copyOf` chỉ vì cùng tên.

### 9.2. `Map.copyOf` không giữ thứ tự của `LinkedHashMap`

~~~java
var source = new LinkedHashMap<String, Integer>();
source.put("A", 1);
source.put("B", 2);

var snapshot = Map.copyOf(source);
~~~

Kết quả không bảo đảm thứ tự duyệt `A` trước `B`. Nếu thứ tự hiển thị quan trọng, hãy mô hình hóa nhu cầu đó riêng; đừng dựa vào thứ tự của `entrySet()` trên Map snapshot.

Các factory này cũng cấm `null`:

- `List.copyOf` và `Set.copyOf` từ chối phần tử `null`.
- `Map.copyOf` từ chối nguồn `null`, bất kỳ khóa `null` hoặc giá trị `null`.
- `List.of`, `Set.of`, `Map.of` cũng không cho dữ liệu `null`.

Đừng “tối ưu” bằng cách thay `List.copyOf(source)` thành `Collections.unmodifiableList(source)` nếu việc xử lý `null` và việc cố định nội dung là một phần hợp đồng. Hai API không thay thế nhau về ngữ nghĩa.

### 9.3. Nguồn chứa `null` và snapshot vẫn cần giữ `null`

Nếu nghiệp vụ thực sự cho phép List chứa `null`, `List.copyOf` không phù hợp. Có thể chọn:

~~~java
var source = new ArrayList<String>();
source.add("A");
source.add(null);

// Snapshot cấu trúc rồi bọc, cho phép giữ null:
List<String> snapshotWithNull =
        Collections.unmodifiableList(new ArrayList<>(source));
~~~

Phương án này có bản sao mutable trung gian được giữ riêng bên trong wrapper và không bị lộ tham chiếu để sửa; vì vậy các thay đổi sau đó của `source` không lan sang `snapshotWithNull`. Đây là lựa chọn có **chi phí sao chép và wrapper**, nhưng giữ đúng chính sách dữ liệu đã yêu cầu.

`Stream.toList()` từ Java 16 cũng trả unmodifiable List và có thể chứa `null`, nhưng đừng lạm dụng việc chuyển một Collection thành Stream chỉ để thay `List.copyOf` khi bạn không thực sự cần pipeline. Chọn cách biểu đạt rõ hợp đồng nhất.

## 10. Tính bất biến và thread safety là hai vấn đề khác nhau

Nếu một thread đang sửa `ArrayList` hoặc `HashMap` trong lúc thread khác gọi `copyOf` mà không có phối hợp, không được giả định phép copy tạo được snapshot **nguyên tử và nhất quán** của toàn bộ dữ liệu. Tùy collection và thời điểm, thao tác có thể lỗi hoặc quan sát trạng thái không như mong muốn.

Khi dữ liệu đến từ nhiều thread:

1. Quy định rõ thread/lock nào được cập nhật nguồn.
2. Tạo bản snapshot từ một **trạng thái nguồn nhất quán** bằng cơ chế đồng bộ phù hợp.
3. Công bố snapshot an toàn cho consumer (chẳng hạn qua trường `final`, `volatile`, lock hoặc cơ chế concurrent thích hợp).
4. Không cho consumer sửa cấu trúc snapshot; kiểm soát thêm các key/value mutable bên trong.

Unmodifiable chỉ bảo đảm không sửa **thông qua collection trả về**, không tự bảo đảm mọi object được tham chiếu là thread-safe. Và `Collections.unmodifiableList` tạo view không chặn các thread khác cập nhật nguồn.

## 11. Đánh giá hiệu năng bằng đo lường thay vì suy diễn

Để quyết định một cách tạo snapshot có đáng chi phí hay không, nên đo **ngữ cảnh ứng dụng thật** và công bố giả định.

### 11.1. Những biến cần cố định khi so sánh

- **Kích thước nguồn:** `n` phần tử/entry và phân bố kích thước thực tế.
- **Kiểu nguồn:** `ArrayList`, `LinkedHashSet`, `HashMap`, unmodifiable factory result hay view bọc một nguồn mutable.
- **Loại phần tử:** object đơn giản, phần tử có `equals`/`hashCode` đắt, tỉ lệ phần tử trùng trong Set.
- **Chính sách `null`:** nếu hai cách khác nhau về chấp nhận `null`, phải xử lý ngữ nghĩa trước; không so sánh hai bài toán khác nhau.
- **Tần suất cập nhật/đọc:** snapshot mỗi lượt đọc khác snapshot mỗi lần cập nhật.
- **Số phiên bản đang sống:** có consumer giữ snapshot cũ lâu không?
- **Môi trường:** phiên bản JDK, hardware, warmup, GC, cấu hình heap.

### 11.2. Các chỉ số hữu ích

| Chỉ số | Câu hỏi |
| --- | --- |
| Latency hoặc throughput | Một chu kỳ tạo snapshot/đọc cấu hình mất bao nhiêu thời gian trong workload thực tế? |
| Allocated bytes/op | Mỗi phép gọi tạo bao nhiêu dữ liệu cấp phát mới theo công cụ đo? |
| Allocation rate | Với tần suất hiện tại, hệ thống tạo bao nhiêu byte/giây? |
| GC frequency/pause | Sự thay đổi này có gây thêm áp lực GC hoặc latency đáng kể không? |
| Retained heap | Những snapshot cũ có còn được giữ tham chiếu gây tăng bộ nhớ tồn tại lâu không? |
| Correctness | Consumer có thấy dữ liệu thay đổi ngoài ý muốn hay không? |

### 11.3. Cách benchmark đúng hướng

Với Java, công cụ **JMH (Java Microbenchmark Harness)** của OpenJDK phù hợp để benchmark vi mô; dùng warmup, nhiều lần đo/fork và cách tiêu thụ kết quả để tránh compiler loại bỏ công việc không dùng. Khi cần phân tích allocation/GC trong ứng dụng thật, có thể dùng Java Flight Recorder (JFR) hoặc profiler phù hợp.

Không đo một lần bằng:

~~~java
long start = System.nanoTime();
List<String> result = List.copyOf(source);
long nanos = System.nanoTime() - start;
~~~

rồi kết luận `copyOf` luôn nhanh hay chậm. Đo một lời gọi như vậy có thể bị nhiễu bởi JIT, đồng hồ, hoạt động của hệ thống, GC và đặc điểm dữ liệu. Đoạn trên chỉ minh họa cách lấy thời gian, **không phải benchmark đáng tin**.

Một benchmark tốt còn phải đảm bảo so sánh cùng mục tiêu. So sánh `List.copyOf(source)` với `Collections.unmodifiableList(source)` có thể cho thấy wrapper nhẹ hơn trong một thử nghiệm, nhưng wrapper **không tạo snapshot** — vì thế hai bên không có cùng hợp đồng dữ liệu.

## 12. Lỗi thường gặp khi cố tối ưu dữ liệu chỉ đọc

| Hiểu nhầm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| “`copyOf` luôn tạo một object mới” | Có thể tái sử dụng unmodifiable source phù hợp | Không dựa vào `==`; đo đúng case |
| “`copyOf` luôn chỉ tốn O(1)” | Với nguồn mutable, cần giữ snapshot; không thể chỉ wrap trực tiếp nguồn mà vẫn đảm bảo snapshot | Xem khối lượng dữ liệu và đo workload |
| “`Collections.unmodifiableList` cũng là snapshot” | View phản ánh thay đổi nguồn | Dùng `List.copyOf` khi cần cố định nội dung |
| “Copy ở từng getter mới an toàn” | Nếu field đã chứa snapshot riêng và không có đường sửa khác, copy lặp lại thường không cần | Snapshot tại ranh giới sở hữu |
| “Không cho sửa là bất biến sâu” | Object phần tử mutable vẫn có thể đổi trạng thái | Kiểm soát tầng phần tử, tránh mutable key |
| “Tối ưu `List.copyOf` bằng view luôn có lợi” | Có thể thay đổi ngữ nghĩa, gây dữ liệu đổi ngoài ý muốn | Đặt correctness trước benchmark |
| “`Set.copyOf` có cùng chi phí với `List.copyOf`” | Set phải xử lý phần tử trùng và equality | Đo theo kiểu và phân bố dữ liệu |
| “`Map.copyOf` giữ thứ tự `LinkedHashMap`” | Thứ tự duyệt của Map kết quả không được cam kết | Sắp xếp riêng nếu cần thứ tự |
| “Unmodifiable collection tự động thread-safe” | Nguồn có thể bị sửa đồng thời, element có thể mutable | Đồng bộ nguồn và công bố snapshot an toàn |
| “Một phép đo `nanoTime` là đủ” | Nhiễu lớn, JIT/GC và tối ưu compiler | Dùng JMH/profiler và workload đại diện |
| “Giảm allocation là tối ưu cuối cùng” | Latency, throughput, retention và correctness đều quan trọng | Đặt mục tiêu và đo nhiều chỉ số |

## 13. Bài tập tự kiểm tra

Cho đoạn mã độc lập trong một phương thức:

~~~java
var source = new ArrayList<>(List.of("A", "B"));
var copied = List.copyOf(source);
var view = Collections.unmodifiableList(source);

source.add("C");

// 1. copied.size() là bao nhiêu?
// 2. view.size() là bao nhiêu?
// 3. Có nên dựa vào copied == List.copyOf(copied) không?
// 4. Nếu tạo copied một lần khi xây object, có cần copy lại ở
//    mọi lần getter được gọi không?
// 5. Nếu phần tử trong copied là StringBuilder thì các
//    tham chiếu bên ngoài còn thay đổi nó được không?
~~~

**Đáp án:**

1. `copied.size() == 2`, vì nó là snapshot cấu trúc tại thời điểm gọi.
2. `view.size() == 3`, vì wrapper phản ánh việc nguồn thêm `"C"`.
3. **Không**. `List.copyOf` có thể tái sử dụng unmodifiable source, nhưng không hứa reference identity; các factory này nên được dùng theo giá trị.
4. **Không nhất thiết**. Nếu object đã giữ snapshot riêng, không thể sửa qua đường nào khác và hợp đồng trả về cho phép chia sẻ dữ liệu đó, getter có thể trả cùng tham chiếu đã không cho sửa.
5. **Có**. `List.copyOf` không deep copy phần tử; nếu object mutable bị sửa qua một tham chiếu khác, nội dung quan sát trong List cũng có thể đổi.

**Tình huống nâng cao:** một ứng dụng có 100.000 lượt đọc cấu hình và 1 lần cập nhật trong mỗi phút. Bạn nên copy trong từng lượt đọc hay tạo snapshot lúc cập nhật rồi công bố cho người đọc? Hãy cân nhắc cách **tạo snapshot khi cập nhật**, tái sử dụng trên đường đọc và kiểm soát safe publication. Nhưng đừng đưa ra kết luận cuối cùng về hiệu năng trước khi xác nhận cách sử dụng và đo dữ liệu thực.

## 14. Ghi nhớ và tài liệu hiện hành

- **`copyOf` là quyết định về hợp đồng dữ liệu trước khi là quyết định tối ưu.** Nó cung cấp snapshot không cho sửa từ nguồn, nhưng không deep copy phần tử.
- **`Collections.unmodifiableXxx` là view không cho sửa**, thường vẫn thấy thay đổi của nguồn; không thay được snapshot nếu consumer cần nội dung cố định.
- **`List.of`/`Set.of`/`Map.of`** phù hợp khi các giá trị được biết trực tiếp, tránh tự dựng một collection mutable trung gian không cần thiết.
- **Tái sử dụng là khả năng, không phải bảo đảm về identity hay allocation.** Không dựa vào `==` hoặc chi tiết implementation để chứng minh `copyOf` có cấp phát.
- **Giảm copy lặp lại** bằng cách tạo snapshot tại ranh giới sở hữu dữ liệu và trả lại snapshot đã công bố khi phù hợp.
- **Set và Map có chi phí và hợp đồng riêng**: Set loại phần tử trùng, Map tổ chức cặp ánh xạ, các factory `copyOf` từ chối `null`, không cam kết thứ tự duyệt của Set/Map.
- **Benchmark đúng bài toán** bằng JMH/JFR và workload thực tế; không đánh đổi tính đúng đắn chỉ để có số allocation thấp hơn.

Tài liệu tham khảo:

- [Java SE 17 — `List.of`, `List.copyOf` và Unmodifiable Lists](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)
- [Java SE 17 — `Set.copyOf`, Unmodifiable Sets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)
- [Java SE 17 — `Map.copyOf`, Unmodifiable Maps](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)
- [Java SE 17 — `Collections.unmodifiableList` và `unmodifiableMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://openjdk.org/projects/code-tools/jmh/)
- [Java SE 17 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/java.flightrecorder/module-summary.html)

**Kết luận:** Khi thiết kế dữ liệu chỉ đọc, hãy xác định trước **ai sở hữu nguồn, dữ liệu có phải giữ nguyên sau khi công bố, phần tử có mutable không, tần suất đọc/ghi thế nào và snapshot sống bao lâu**. Chỉ sau khi đáp ứng hợp đồng đó mới chọn `copyOf`, factory `of`, view hoặc cơ chế tái sử dụng, rồi đo chi phí cấp phát và hiệu năng trên workload thực.
