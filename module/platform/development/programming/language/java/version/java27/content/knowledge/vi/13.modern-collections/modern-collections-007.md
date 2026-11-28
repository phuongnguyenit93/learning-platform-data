# View, bản sao, tính bất biến và chia sẻ dữ liệu an toàn trong Java 27

Một `List` có thể không cho phép gọi `add` nhưng vẫn thay đổi khi một thành phần khác sửa danh sách gốc. Một `Map` có thể được sao chép nhưng các đối tượng bên trong vẫn dùng chung tham chiếu. Một `record` có trường `List` cũng chưa chắc bất biến nếu constructor giữ nguyên danh sách mà người gọi truyền vào. Đây là những khác biệt quan trọng khi thiết kế API và chia sẻ dữ liệu trong Java.

Trong chương **Collections hiện đại** của **Java 27**, chúng ta sẽ phân biệt rõ **view (khung nhìn)**, **bản sao (copy/snapshot)**, **không sửa đổi được (unmodifiable)** và **bất biến theo chiều sâu (deep immutability)**. Sau đó áp dụng các API hiện hành như `List.of`, `List.copyOf`, `Collections.unmodifiableList`, `subList`, `reversed`, `Stream.toList` và các cấu trúc chia sẻ dữ liệu an toàn.

Nội dung dựa trên API Java SE 27 chính thức: [List](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html), [Set](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html), [Map](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html), [Collections](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html), [SequencedCollection](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/SequencedCollection.html) và [Stream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html). Các API preview mới hoặc kỹ thuật legacy không cần thiết không được sử dụng.

## 1. Bốn khái niệm phải phân biệt

### 1.1. Collection có thể thay đổi (mutable collection)

Một `ArrayList`, `HashSet` hoặc `HashMap` thông thường có thể cho phép thay đổi cấu trúc hoặc nội dung: thêm, xóa, thay thế phần tử hoặc cập nhật ánh xạ.

~~~~java
import java.util.ArrayList;
import java.util.List;

List<String> colors = new ArrayList<>(List.of("red", "blue"));
colors.add("green");
colors.set(0, "orange");

System.out.println(colors); // [orange, blue, green]
~~~~

Tính mutable của collection nói về các **phép thay đổi thông qua giao diện của collection**. Nó không trả lời được các câu hỏi: có biến khác cùng trỏ đến collection hay không, hoặc bản thân phần tử có thể thay đổi hay không.

### 1.2. View là một góc nhìn lên dữ liệu đang có

View thường giữ quan hệ với một **backing collection** hoặc cấu trúc bên dưới. Nó có thể chỉ hiển thị một phần, đổi thứ tự quan sát hoặc chặn thao tác ghi nhưng **không nhất thiết tạo bản sao độc lập**.

~~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> backing = new ArrayList<>(List.of("A", "B"));
List<String> readOnlyView = Collections.unmodifiableList(backing);

System.out.println(readOnlyView); // [A, B]

backing.add("C");
System.out.println(readOnlyView); // [A, B, C]

// readOnlyView.add("D"); // UnsupportedOperationException
~~~~

`Collections.unmodifiableList(backing)` là **view không cho sửa qua biến `readOnlyView`**. Nó không chặn code khác giữ biến `backing` thay đổi danh sách gốc. Vì vậy, “không sửa được qua view” **khác** “dữ liệu luôn giữ nguyên”.

### 1.3. Copy là tạo cấu trúc mới

Khi sao chép, ta tạo một cấu trúc collection khác. Thay đổi cấu trúc của collection ban đầu không tự xuất hiện trong bản sao:

~~~~java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> copy = new ArrayList<>(source);

source.add("C");
copy.set(0, "X");

System.out.println(source); // [A, B, C]
System.out.println(copy);   // [X, B]
~~~~

Bản sao này vẫn **mutable** vì dùng `ArrayList`. Sao chép không đồng nghĩa với bất biến. Bản sao ở đây cũng chỉ sao chép **tham chiếu phần tử** nếu phần tử là đối tượng.

### 1.4. Không sửa đổi được chưa chắc bất biến theo chiều sâu

`List.of` và `List.copyOf` trả về danh sách **unmodifiable**. Nhưng nếu phần tử bên trong có trạng thái mutable, nội dung được quan sát qua list vẫn có thể thay đổi:

~~~~java
import java.util.List;

StringBuilder builder = new StringBuilder("before");
List<StringBuilder> values = List.of(builder);

builder.append("-after");
System.out.println(values.getFirst()); // before-after

// values.set(0, new StringBuilder()); // UnsupportedOperationException
~~~~

Danh sách không đổi phần tử tham chiếu, nhưng `StringBuilder` được tham chiếu **có thể thay đổi trạng thái**. Muốn dữ liệu thực sự ổn định, cần xem xét cả mức collection, mức phần tử và các cấu trúc lồng nhau.

### 1.5. Bảng phân biệt nhanh

| Khái niệm | Tách cấu trúc khỏi nguồn? | Cho sửa qua tham chiếu trả về? | Phần tử mutable có thể đổi? |
| --- | --- | --- | --- |
| `new ArrayList<>(source)` | Có | Có | Có, nếu các phần tử là đối tượng mutable |
| `Collections.unmodifiableList(source)` | **Không**, là view | Không | Có |
| `List.copyOf(source)` | Tạo kết quả độc lập về **nội dung cấu trúc** so với thay đổi sau đó của nguồn | Không | Có |
| `List.of(element1, element2)` | Tạo list từ các tham chiếu được cung cấp | Không | Có |
| `source.subList(a, b)` | **Không**, là view | Tùy khả năng sửa của nguồn | Có |
| `source.reversed()` | View đảo thứ tự, không phải bản sao | Tùy implementation và khả năng sửa của nguồn | Có |
| `Collections.unmodifiableList(new ArrayList<>(source))` | Có, nếu backing copy không bị lộ | Không | Có |

**Lưu ý về `List.copyOf`:** hợp đồng API bảo đảm list kết quả không phản ánh những thay đổi **sau đó** của collection nguồn. Tuy nhiên, nếu nguồn vốn đã là một list không sửa đổi được thích hợp, implementation có thể **tái sử dụng** chính đối tượng đó, không bắt buộc cấp phát một đối tượng mới. Do đó không được phụ thuộc vào phép so sánh `==` để xác định “đã copy chưa”.

## 2. Những view quan trọng của Collections Framework

### 2.1. `Collections.unmodifiableList`, `unmodifiableSet` và `unmodifiableMap`

Các phương thức wrapper trong `Collections` tạo khung nhìn không sửa đổi được:

~~~~java
import java.util.*;

List<String> mutableNames = new ArrayList<>(List.of("An", "Binh"));
List<String> namesView = Collections.unmodifiableList(mutableNames);

Set<String> mutableRoles = new HashSet<>(Set.of("READER"));
Set<String> rolesView = Collections.unmodifiableSet(mutableRoles);

Map<String, Integer> mutableCounts = new HashMap<>();
mutableCounts.put("ok", 2);
Map<String, Integer> countsView =
        Collections.unmodifiableMap(mutableCounts);

mutableNames.add("Lan");
mutableRoles.add("EDITOR");
mutableCounts.put("failed", 1);

System.out.println(namesView);  // [An, Binh, Lan]
System.out.println(rolesView.contains("EDITOR")); // true
System.out.println(countsView.get("failed"));      // 1
~~~~

Các wrapper này hữu ích khi chỉ muốn **giới hạn khả năng thao tác** của code nhận view, nhưng vẫn muốn nó quan sát dữ liệu mới nhất do bên sở hữu cập nhật.

Tuy nhiên, wrapper **không phải ảnh chụp dữ liệu**. Nếu cần trả một kết quả ổn định tại một thời điểm, hãy tạo snapshot. Nếu backing mutable bị truy cập đồng thời mà không có cơ chế đồng bộ phù hợp, việc bọc bằng unmodifiable view cũng **không làm cho việc đọc trở nên thread-safe**.

### 2.2. `List.subList` là view của một đoạn

`subList(fromIndex, toIndex)` trả về một đoạn từ chỉ số bắt đầu **bao gồm** đến chỉ số kết thúc **không bao gồm**.

~~~~java
import java.util.ArrayList;
import java.util.List;

List<String> all = new ArrayList<>(List.of("A", "B", "C", "D"));
List<String> middle = all.subList(1, 3); // [B, C]

middle.set(0, "X");
System.out.println(all); // [A, X, C, D]

middle.clear();           // Thay đổi luôn backing list
System.out.println(all); // [A, D]
~~~~

Thay đổi qua `subList` (nếu list gốc cho phép) có thể ghi xuyên vào list gốc. Những thay đổi **không làm đổi cấu trúc** từ backing list cũng phản ánh qua view tương ứng.

**Bẫy quan trọng:** nếu list gốc bị **thay đổi cấu trúc theo cách khác ngoài qua subList**, ngữ nghĩa của subList có thể trở nên **không xác định theo hợp đồng API**. Đừng dựa vào việc luôn nhận `ConcurrentModificationException`; ngoại lệ đó không phải lời hứa cho mọi lần sử dụng.

Nếu muốn tách một đoạn để lưu lâu dài:

~~~~java
List<String> snapshotOfRange =
        List.copyOf(all.subList(0, Math.min(2, all.size())));
~~~~

Kết quả mới không phản ánh các thao tác thêm/xóa hoặc thay phần tử của `all` sau thời điểm sao chép.

### 2.3. `Arrays.asList` là view được hỗ trợ bởi mảng

`Arrays.asList(array)` trả về một list **kích thước cố định** dựa trên mảng gốc. Có thể `set` phần tử, nhưng không thể `add` hoặc `remove` làm đổi kích thước.

~~~~java
import java.util.Arrays;
import java.util.List;

String[] raw = {"A", "B"};
List<String> fixedSize = Arrays.asList(raw);

fixedSize.set(0, "X");
System.out.println(raw[0]); // X

raw[1] = "Y";
System.out.println(fixedSize); // [X, Y]

// fixedSize.add("Z"); // UnsupportedOperationException
~~~~

Với mảng nguyên thủy, có điểm cần nhớ:

~~~~java
int[] primitive = {1, 2, 3};
List<int[]> oneElement = Arrays.asList(primitive);
System.out.println(oneElement.size()); // 1, không phải 3
~~~~

`int[]` được truyền như **một đối tượng mảng** vào varargs, nên `Arrays.asList(int[])` **không** tự boxing thành `List<Integer>`. Nếu cần list số nguyên:

~~~~java
List<Integer> numbers = Arrays.stream(primitive).boxed().toList();
~~~~

`Stream.toList()` ở đây trả về list không sửa đổi được, không phải list hỗ trợ `add`.

### 2.4. View từ `Map.keySet`, `values` và `entrySet`

`Map` công bố ba collection view:

- `keySet()`: tập khóa.
- `values()`: collection các giá trị.
- `entrySet()`: tập các cặp khóa–giá trị.

Với một `HashMap` mutable thông thường, các view này được hỗ trợ bởi map gốc:

~~~~java
import java.util.*;

Map<String, Integer> scores = new HashMap<>();
scores.put("An", 80);
scores.put("Binh", 90);

Set<String> keys = scores.keySet();
Collection<Integer> values = scores.values();

keys.remove("An");                // Xóa ánh xạ trong map
System.out.println(scores);       // {Binh=90}

scores.put("Lan", 95);
System.out.println(values.contains(95)); // true
~~~~

Không phải mọi view hỗ trợ mọi thao tác. Ví dụ, `keySet().add(newKey)` không có thông tin về giá trị để thêm vào map và không được hỗ trợ bởi `HashMap.keySet()`. Các thao tác xóa qua iterator hoặc view cũng phụ thuộc hợp đồng của map cụ thể.

`entrySet()` có thể cung cấp các `Map.Entry` cho phép `setValue` nếu map hỗ trợ. Với API cần read-only, **không nên trả trực tiếp view của một map mutable** rồi nghĩ rằng đã bảo vệ nó.

### 2.5. `reversed()` và Sequenced Collections (Java 21+)

Từ Java 21, `SequencedCollection` cung cấp cách biểu diễn collection có thứ tự với hai đầu và phương thức `reversed()`. Trong Java 27, `List` kế thừa `SequencedCollection`; các kiểu như `SequencedSet` và `SequencedMap` cũng hỗ trợ view theo thứ tự ngược.

~~~~java
import java.util.ArrayList;
import java.util.List;

List<String> tasks = new ArrayList<>(List.of("first", "second", "third"));
List<String> reversed = tasks.reversed();

System.out.println(reversed); // [third, second, first]
System.out.println(reversed.getFirst()); // third

reversed.set(0, "latest");
System.out.println(tasks); // [first, second, latest]
~~~~

`reversed()` trả về **view**, không tạo một list mới gồm các phần tử đã sao chép. Với một list mutable hỗ trợ thao tác như ví dụ, thao tác trên view sẽ thay đổi backing list. Tài liệu API cho phép hành vi phản ánh những thay đổi **từ backing tới reversed view** phụ thuộc implementation; không tự suy diễn mọi view đều có cùng khả năng ghi hoặc phản ánh cập nhật.

Nếu muốn một **snapshot đảo thứ tự** ổn định:

~~~~java
List<String> reversedSnapshot = List.copyOf(tasks.reversed());
~~~~

Đừng nhầm view ngược với việc gọi một thuật toán đảo tại chỗ: `Collections.reverse(tasks)` sửa chính `tasks`, còn `tasks.reversed()` biểu diễn thứ tự ngược thông qua view.

## 3. Factory hiện đại: `List.of`, `Set.of`, `Map.of`

Các factory này tạo collection **unmodifiable**, thích hợp với danh sách cấu hình, tập quyền, bảng ánh xạ nhỏ hoặc giá trị cố định trong API.

~~~~java
import java.util.*;

List<String> steps = List.of("receive", "validate", "save");
Set<String> roles = Set.of("READ", "WRITE");
Map<String, Integer> retryPolicy = Map.of(
        "network", 3,
        "database", 2);

System.out.println(steps.get(0));        // receive
System.out.println(roles.contains("READ")); // true
System.out.println(retryPolicy.get("network")); // 3
~~~~

### 3.1. Chính sách null và phần tử trùng lặp

| API | Null | Phần tử/khóa trùng |
| --- | --- | --- |
| `List.of(...)` | Từ chối bằng `NullPointerException` | **Cho phép** phần tử trùng |
| `Set.of(...)` | Từ chối bằng `NullPointerException` | Từ chối bằng `IllegalArgumentException` |
| `Map.of(...)` | Từ chối null ở khóa/giá trị bằng `NullPointerException` | Từ chối khóa trùng bằng `IllegalArgumentException` |
| `Map.ofEntries(...)` | Từ chối null ở khóa/giá trị | Từ chối khóa trùng |

Ví dụ minh họa những tình huống **cố ý sai**:

~~~~java
// Các dòng này sẽ ném exception nếu thực thi:
// List.of("A", null);               // NullPointerException
// Set.of("A", "A");                // IllegalArgumentException
// Map.of("x", 1, "x", 2);         // IllegalArgumentException
// Map.of("x", null);               // NullPointerException
~~~~

Với nhiều cặp khóa–giá trị, dùng `Map.ofEntries`:

~~~~java
import static java.util.Map.entry;

Map<String, Integer> months = Map.ofEntries(
        entry("January", 1),
        entry("February", 2),
        entry("March", 3));
~~~~

### 3.2. Thứ tự duyệt có được bảo đảm?

`List.of` giữ nguyên thứ tự các phần tử được cung cấp; `List.copyOf` giữ thứ tự duyệt của nguồn. Tuy nhiên, **`Set.of`, `Set.copyOf`, `Map.of` và `Map.copyOf` không bảo đảm thứ tự iteration**. Không dùng thứ tự in ra màn hình làm hợp đồng nghiệp vụ hoặc snapshot để kiểm thử.

~~~~java
Set<String> tags = Set.of("blue", "green", "red");

// Không được giả định tags.iterator() luôn trả blue, green, red.
System.out.println(tags.contains("green")); // true
~~~~

Khi thứ tự duyệt là một yêu cầu thực sự, cân nhắc một list hoặc loại collection có hợp đồng thứ tự như `LinkedHashSet`, `LinkedHashMap`, `TreeSet` hoặc `TreeMap`. Nếu cần **snapshot không sửa được và giữ insertion order**, có thể sao chép vào `LinkedHashSet`/`LinkedHashMap` rồi bọc bằng `Collections.unmodifiableSet`/`unmodifiableMap`, miễn là không để lộ bản sao mutable bên dưới.

### 3.3. Không phụ thuộc danh tính đối tượng của factory collection

Những collection tạo bởi các factory `of`/`copyOf` có thể là **value-based objects**. Không dùng `==`, `System.identityHashCode` hoặc khóa `synchronized` trên các đối tượng này để làm cơ chế nghiệp vụ hay khóa luồng.

~~~~java
List<String> first = List.of("A", "B");
List<String> second = List.of("A", "B");

System.out.println(first.equals(second)); // true
// Không dựa vào first == second: danh tính không thuộc hợp đồng.
~~~~

So sánh **nội dung** bằng `equals`, không so sánh tham chiếu.

## 4. Sao chép collection: mutable copy và unmodifiable snapshot

### 4.1. Sao chép mutable khi muốn chỉnh sửa tiếp

Chọn collection đích theo quy tắc cần bảo toàn:

~~~~java
import java.util.*;

List<String> sourceList = List.of("A", "B", "B");
List<String> editableList = new ArrayList<>(sourceList);

Set<String> sourceSet = Set.of("READ", "WRITE");
Set<String> editableSet = new LinkedHashSet<>(sourceSet);

Map<String, Integer> sourceMap = Map.of("A", 10, "B", 20);
Map<String, Integer> editableMap = new HashMap<>(sourceMap);

editableList.add("C");
editableSet.add("ADMIN");
editableMap.put("C", 30);
~~~~

Với `List`, bản sao giữ cả các phần tử trùng và thứ tự duyệt. Với `Set`, các phần tử trùng không tồn tại theo hợp đồng. Với `Map`, chỉ có một giá trị cho mỗi khóa. `LinkedHashSet` giữ thứ tự duyệt của nguồn tại lúc sao chép; **không** biến thứ tự vốn không xác định của `Set.of` thành một thứ tự được xác định về mặt nghiệp vụ.

### 4.2. `List.copyOf`, `Set.copyOf`, `Map.copyOf`

Các `copyOf` được dùng khi muốn nhận bản sao **không cho sửa cấu trúc**:

~~~~java
import java.util.*;

List<String> input = new ArrayList<>(List.of("A", "B"));
List<String> stable = List.copyOf(input);

input.set(0, "X");
input.add("C");

System.out.println(input);  // [X, B, C]
System.out.println(stable); // [A, B]
~~~~

Tương tự cho `Set` và `Map`:

~~~~java
Set<String> stableRoles = Set.copyOf(
        List.of("READ", "WRITE", "READ"));
System.out.println(stableRoles.size()); // 2

Map<String, Integer> mutable = new HashMap<>();
mutable.put("network", 3);

Map<String, Integer> stableMap = Map.copyOf(mutable);
mutable.put("network", 99);

System.out.println(stableMap.get("network")); // 3
~~~~

Những chi tiết quan trọng:

- `List.copyOf` từ chối collection nguồn null hoặc có phần tử null.
- `Set.copyOf` từ chối null. Nếu nguồn có phần tử trùng theo `equals`, nó giữ **một đại diện tùy ý** trong các phần tử tương đương; **không** ném lỗi như `Set.of` với các đối số trùng.
- `Map.copyOf` từ chối null ở khóa hoặc giá trị. Nguồn là Map nên mỗi khóa đã là duy nhất theo hợp đồng Map.
- Kết quả `copyOf` không phản ánh các thay đổi cấu trúc sau đó của nguồn. Nhưng việc sao chép chỉ ở **mức collection**, không tự clone từng đối tượng.
- Implementation có thể tái sử dụng một input vốn đã là unmodifiable collection phù hợp. Không dựa vào danh tính để suy ra cách cấp phát.

Chú ý `Set.copyOf` có thể chọn đại diện tùy ý khi có hai đối tượng bằng nhau theo `equals` nhưng không cùng identity. Nếu cần chính xác phần tử nào được giữ, hãy định nghĩa chiến lược loại trùng tường minh thay vì dựa vào `Set.copyOf`.

### 4.3. Muốn giữ null trong snapshot?

Các factory `of` và `copyOf` trong `List` không chấp nhận null. Nếu nghiệp vụ **cố ý cho phép null** làm phần tử, có thể tạo bản sao riêng rồi bọc bằng view unmodifiable:

~~~~java
import java.util.*;

List<String> raw = new ArrayList<>();
raw.add("A");
raw.add(null);

List<String> stableWithNull =
        Collections.unmodifiableList(new ArrayList<>(raw));

raw.set(0, "X");
System.out.println(stableWithNull); // [A, null]
~~~~

Ở đây `new ArrayList<>(raw)` **tách cấu trúc** khỏi `raw`, và wrapper ngăn sửa qua `stableWithNull`. Phần tử mutable vẫn chỉ được sao chép tham chiếu. Hãy cân nhắc một kiểu dữ liệu rõ nghĩa hơn khi null được dùng để biểu diễn “không có dữ liệu”.

### 4.4. Sao chép trước khi kiểm tra để tránh alias bị sửa

Một thiết kế dễ sai:

~~~~java
// Phản ví dụ: dữ liệu có thể bị đổi sau bước kiểm tra.
void register(List<String> permissions) {
    validate(permissions);
    this.permissions = permissions;
}
~~~~

Nếu caller giữ danh sách mutable và sửa nó sau khi `register` trả về, trường `permissions` có thể thay đổi mà không qua validation của object sở hữu.

Hướng tốt hơn:

~~~~java
void register(List<String> permissions) {
    List<String> snapshot = List.copyOf(
            Objects.requireNonNull(permissions, "permissions"));

    validate(snapshot);
    this.permissions = snapshot;
}
~~~~

Điều quan trọng là **lưu bản sao đã được kiểm tra**, không kiểm tra một collection rồi lưu nguyên tham chiếu mutable. Nếu có nhiều luồng cùng thay đổi nguồn trong lúc `copyOf` đang đọc, bản sao không mặc nhiên là snapshot nguyên tử: cần quy ước đồng bộ hoặc cấu trúc dữ liệu phù hợp trước khi copy.

## 5. Shallow copy, deep copy và bất biến của phần tử

### 5.1. Sao chép collection không sao chép bản thân đối tượng

Phần lớn thao tác copy trong Collections Framework chỉ sao chép **các tham chiếu** đến phần tử. Điều này khác với việc tạo bản sao độc lập của từng đối tượng bên trong.

~~~~java
import java.util.ArrayList;
import java.util.List;

StringBuilder shared = new StringBuilder("draft");

List<StringBuilder> input = new ArrayList<>();
input.add(shared);

List<StringBuilder> copy = List.copyOf(input);
input.clear();

System.out.println(copy.size()); // 1: cấu trúc đã được tách

shared.append("-edited");
System.out.println(copy.getFirst()); // draft-edited
~~~~

`List.copyOf` giữ danh sách ổn định về **số lượng và tham chiếu phần tử**, nhưng `StringBuilder` bên trong vẫn mutable và được chia sẻ. `Collections.unmodifiableList(input)` còn khác hơn: nó cũng chia sẻ cả **cấu trúc** của `input`.

| Thành phần | `Collections.unmodifiableList(input)` | `List.copyOf(input)` |
| --- | --- | --- |
| Có thể thay đổi list qua kết quả | Không | Không |
| Thay đổi thêm/xóa ở input sau khi tạo | Có thể quan sát qua view | Không phản ánh trong kết quả |
| Thay đổi trạng thái object phần tử | Có thể quan sát | Có thể quan sát |
| Tạo bản sao sâu object phần tử | Không | Không |
| Phù hợp để phát hành snapshot cấu trúc | Không, nếu input tiếp tục bị sửa | Có, nếu thao tác copy có nguồn ổn định |

### 5.2. Cách làm đơn giản nhất: phần tử đã bất biến

Với những phần tử có mô hình giá trị bất biến, có thể xây dựng một snapshot có hành vi ổn định theo chiều sâu mà không phải clone thủ công ở nhiều cấp:

~~~~java
import java.util.List;

record LineItem(String sku, int quantity) {
    LineItem {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (quantity < 1) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}

List<LineItem> items = List.of(
        new LineItem("BOOK-01", 2),
        new LineItem("PEN-02", 5));
~~~~

`LineItem` có các component `String` và `int`. `String` là kiểu bất biến; `int` là giá trị nguyên thủy. Vì record không cung cấp setter và các component này không chứa trạng thái mutable, từng phần tử an toàn để chia sẻ theo giá trị.

**Record không tự động deep-immutable.** Nếu component là `List`, mảng, `Date`, `StringBuilder` hoặc object có thể thay đổi, record vẫn có thể bị ảnh hưởng bởi mutation thông qua tham chiếu. Cần defensive copy tương ứng.

### 5.3. Sao chép sâu khi phần tử mutable

Giả sử nguồn là danh sách các `StringBuilder` và mục tiêu là giữ **giá trị văn bản tại thời điểm sao chép**. Có thể **chuyển kiểu phần tử** sang `String` bất biến:

~~~~java
import java.util.List;

List<StringBuilder> source = List.of(
        new StringBuilder("Alice"),
        new StringBuilder("Bob"));

List<String> snapshot = source.stream()
        .map(StringBuilder::toString)
        .toList();

source.getFirst().append(" Smith");

System.out.println(snapshot); // [Alice, Bob]
~~~~

`StringBuilder::toString` tạo một giá trị String độc lập với những sửa đổi tiếp theo của builder. `Stream.toList()` trả về list unmodifiable, nên kết quả có **cả cấu trúc và phần tử String không sửa đổi được**.

Với object miền phức tạp, hãy tạo một immutable DTO/record tương ứng, hoặc sử dụng copy constructor có ngữ nghĩa rõ ràng:

~~~~java
import java.util.List;

record CustomerSnapshot(String id, String displayName) {
}

static List<CustomerSnapshot> snapshotCustomers(
        List<MutableCustomer> customers) {

    return customers.stream()
            .map(customer -> new CustomerSnapshot(
                    customer.id(), customer.displayName()))
            .toList();
}
~~~~

`MutableCustomer` trong đoạn trên là kiểu miền do ứng dụng định nghĩa (có hai accessor `id()` và `displayName()`). Ví dụ chỉ minh họa **chiến lược chuyển đổi**. Nếu getter của đối tượng mutable có thể thay đổi đồng thời hoặc trả về cấu trúc mutable, phải xác định thêm quy tắc khóa, snapshot hoặc deep copy phù hợp.

### 5.4. Cấu trúc lồng nhau cần xem từng cấp

~~~~java
import java.util.*;

Map<String, List<String>> source = new HashMap<>();
List<String> tags = new ArrayList<>(List.of("new"));
source.put("product-1", tags);

Map<String, List<String>> outerCopy = Map.copyOf(source);
tags.add("sale");

System.out.println(outerCopy.get("product-1")); // [new, sale]
~~~~

`Map.copyOf` đã tách cấu trúc **Map**, nhưng giá trị `List` của mỗi key vẫn được chia sẻ. Muốn snapshot nhiều cấp:

~~~~java
Map<String, List<String>> snapshot = new HashMap<>();
for (var entry : source.entrySet()) {
    snapshot.put(entry.getKey(), List.copyOf(entry.getValue()));
}
snapshot = Map.copyOf(snapshot);
~~~~

Với cấu trúc này, cả Map và các list giá trị đều unmodifiable và độc lập về cấu trúc so với nguồn. Bởi các phần tử là `String` bất biến, việc chia sẻ reference String không gây mutation. Nếu list chứa object mutable, cần tiếp tục copy/convert từng object.

Không có một phương thức `Collections.deepCopy` tổng quát nào tự hiểu mọi loại miền dữ liệu. **Deep copy là quyết định nghiệp vụ**: cần biết object nào phải độc lập, các quan hệ alias nào được phép giữ và trường hợp nào cần chia sẻ.

## 6. Thiết kế record và lớp bảo vệ dữ liệu đầu vào/đầu ra

### 6.1. Defensive copy trong compact constructor của record

Record giúp mô hình hóa dữ liệu được chia sẻ, nhưng **không tự động sao chép collection component**. Hãy kiểm tra và copy ngay khi nhận:

~~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;

record OrderSnapshot(
        String orderId,
        List<LineItem> items,
        Map<String, String> metadata) {

    OrderSnapshot {
        orderId = Objects.requireNonNull(orderId, "orderId");
        if (orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }

        items = List.copyOf(Objects.requireNonNull(items, "items"));
        metadata = Map.copyOf(
                Objects.requireNonNull(metadata, "metadata"));

        if (items.isEmpty()) {
            throw new IllegalArgumentException("items must not be empty");
        }
    }
}
~~~~

Đoạn này giả định `LineItem` là record bất biến đã khai báo ở mục trước. Trong **compact constructor**, Java gán các tham số component cuối cùng vào trường record **sau khi thân constructor hoàn thành bình thường**. Vì vậy có thể gán lại biến `items` và `metadata` bằng snapshot rồi để Java gán chúng vào trường tương ứng.

Lợi ích:

- Người tạo record có thể truyền một `ArrayList` hay `HashMap` mutable, nhưng record không lưu trực tiếp các cấu trúc đó.
- Getter `items()` và `metadata()` trả về collection không sửa đổi được; caller không thể thêm/xóa/phần tử qua getter.
- Các thay đổi cấu trúc sau đó của input không ảnh hưởng đến snapshot.
- `List.copyOf` và `Map.copyOf` từ chối null, giúp các invariant đơn giản hơn.

### 6.2. Nếu component là mảng thì phải chú ý cả chiều vào và chiều ra

Mảng Java luôn mutable. Một record chứa mảng không trở thành bất biến chỉ vì trường của record là final. Cách đơn giản nhất là **không công bố mảng mutable**; khi thực sự cần giữ mảng, sao chép khi nhận và khi trả:

~~~~java
import java.util.Arrays;
import java.util.Objects;

record BinaryPayload(byte[] bytes) {
    BinaryPayload {
        bytes = Arrays.copyOf(
                Objects.requireNonNull(bytes, "bytes"), bytes.length);
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~~

Đoạn này dùng defensive copy hai chiều: constructor tách khỏi mảng đầu vào, accessor trả mảng mới để caller không sửa trạng thái nội bộ. Tuy nhiên, **record chứa mảng có thêm một vấn đề**: `equals` và `hashCode` mặc định so sánh component mảng theo danh tính, không theo nội dung. Nếu yêu cầu là **value equality theo byte**, hãy tự triển khai quy tắc so sánh/hashCode tương ứng hoặc dùng một kiểu miền khác được thiết kế cho mục đích đó.

### 6.3. Defensive copy khi trả kết quả từ lớp mutable

Một lớp sở hữu dữ liệu có thể có trạng thái mutable nội bộ nhưng chỉ công bố snapshot:

~~~~java
import java.util.*;

final class Cart {
    private final List<String> skuItems = new ArrayList<>();

    public void addItem(String sku) {
        skuItems.add(Objects.requireNonNull(sku, "sku"));
    }

    public List<String> items() {
        return List.copyOf(skuItems);
    }
}
~~~~

`items()` trả giá trị danh sách **tại thời điểm copy**, tách khỏi các lần `addItem` sau đó. Điều này khác với `Collections.unmodifiableList(skuItems)`, vì view sẽ quan sát nội dung của Cart tiếp tục thay đổi.

Ví dụ chưa có đồng bộ đa luồng. Nếu Cart được truy cập đồng thời bởi nhiều thread, phải thiết kế khóa hoặc cơ chế snapshot đồng thời để bảo đảm dữ liệu được đọc nhất quán. `List.copyOf` một mình không giải quyết tranh chấp đọc/ghi đồng thời vào `ArrayList`.

## 7. Stream, Collector và khả năng sửa danh sách kết quả

Những API trông giống nhau có thể có **hợp đồng mutability khác nhau**.

| API | Tính sửa đổi của kết quả | Null | Lưu ý |
| --- | --- | --- | --- |
| `stream.toList()` | Unmodifiable | Có thể chứa null | Giữ encounter order nếu stream có order |
| `stream.collect(Collectors.toUnmodifiableList())` | Unmodifiable | **Không cho null** | Từ chối null bằng `NullPointerException` |
| `stream.collect(Collectors.toList())` | **Không có cam kết** về mutability/type cụ thể | Không có chính sách null duy nhất cho mọi implementation | Không giả định luôn là ArrayList |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Mutable `ArrayList` | ArrayList cho null | Dùng khi muốn kiểm soát implementation |
| `new ArrayList<>(stream.toList())` | Mutable `ArrayList` | Cho null | Tạo danh sách có thể sửa từ kết quả stream |

Ví dụ:

~~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> unmodifiable = Stream.of("An", "Binh")
        .map(String::toUpperCase)
        .toList();

List<String> mutable = Stream.of("An", "Binh")
        .collect(Collectors.toCollection(ArrayList::new));

mutable.add("Lan");
// unmodifiable.add("Lan"); // UnsupportedOperationException
~~~~

**Lỗi thiết kế thường gặp:** dùng `Collectors.toList()` rồi giả định kết quả là `ArrayList` mutable. API nói rõ **không bảo đảm** loại collection, khả năng sửa, khả năng tuần tự hóa hoặc tính thread-safe của kết quả. Nếu muốn mutable cụ thể, hãy dùng `toCollection(ArrayList::new)`.

### 7.1. Trường hợp có null

~~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> maybeNull = Stream.of("A", null, "C").toList();
System.out.println(maybeNull); // [A, null, C]
~~~~

`Stream.toList()` trả danh sách unmodifiable nhưng **không cấm null** như `List.of` hay `List.copyOf`. Do đó, các collection đều “không sửa được” nhưng vẫn có chính sách null khác nhau. Khi chuyển sang `List.copyOf(maybeNull)` hoặc `Collectors.toUnmodifiableList()`, null sẽ gây `NullPointerException`.

### 7.2. Đừng nhầm “kết quả stream” với “view sống”

`Stream.toList()` là một **terminal operation**, thu thập các phần tử thành list kết quả. Nó không phải view động luôn phản ánh các phép thêm/xóa tiếp theo ở collection nguồn.

~~~~java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> upper = source.stream().map(String::toUpperCase).toList();

source.add("C");
System.out.println(upper); // [A, B]
~~~~

Tuy nhiên, nếu stream mang theo **tham chiếu đến đối tượng mutable**, list kết quả vẫn có thể quan sát trạng thái mới của các phần tử ấy. Đây vẫn là giới hạn của **shallow copy**.

### 7.3. Collectors tạo Map hoặc Set

`Collectors.toUnmodifiableSet()` và `Collectors.toUnmodifiableMap()` tạo các collection không sửa đổi được, nhưng có quy tắc riêng về phần tử/khóa trùng và null. Với `toUnmodifiableMap`, nếu có khóa trùng mà không có merge function, phép thu thập sẽ thất bại; nếu muốn gộp các khóa trùng, phải xác định merge function.

~~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Product(String sku, int stock) {
}

List<Product> products = List.of(
        new Product("BOOK", 10),
        new Product("PEN", 20));

Map<String, Integer> stockBySku = products.stream()
        .collect(Collectors.toUnmodifiableMap(
                Product::sku, Product::stock));
~~~~

Chỉ dùng `toUnmodifiableMap` khi dữ liệu đáp ứng hợp đồng về null và khóa trùng. Nếu cần một Map có **insertion order và mutable**, có thể dùng overload `Collectors.toMap` với merge function cùng map factory `LinkedHashMap::new`. Không dựa vào thứ tự lặp của Map unmodifiable nếu API không cam kết.

## 8. Chia sẻ an toàn giữa các thread

### 8.1. Unmodifiable không đồng nghĩa với thread-safe

Một view có thể không cho gọi `add` nhưng vẫn dựa vào collection mutable bị thread khác thay đổi. Vì vậy câu lệnh sau **không tự giải quyết an toàn đa luồng**:

~~~~java
List<String> sharedView =
        Collections.unmodifiableList(mutableArrayList);
~~~~

Để chia sẻ dữ liệu đọc ổn định, thường cần kết hợp:

1. **Tách nguồn mutable** thành snapshot.
2. Bảo đảm các **phần tử** cũng an toàn để đọc đồng thời (ví dụ String, record có thành phần bất biến).
3. **Công bố** tham chiếu snapshot theo cơ chế có bảo đảm visibility và ordering, như thiết lập qua final field trong quá trình xây dựng đối tượng đúng cách, volatile/atomic reference hoặc synchronized.

Một snapshot unmodifiable không thay thế mọi cơ chế đồng bộ; nó chỉ giảm số nơi có thể phát sinh mutation.

### 8.2. Ví dụ: Snapshot registry dùng AtomicReference

Đây là chương trình **tự chứa**, có thể lưu thành `SnapshotRegistryDemo.java`. Registry cho nhiều luồng cùng đọc một danh sách công việc ổn định, còn các lần cập nhật xuất bản snapshot mới:

~~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

final class SnapshotRegistry {
    private final AtomicReference<List<String>> state =
            new AtomicReference<>(List.of());

    public List<String> current() {
        return state.get();
    }

    public void add(String taskName) {
        Objects.requireNonNull(taskName, "taskName");
        if (taskName.isBlank()) {
            throw new IllegalArgumentException("taskName must not be blank");
        }

        state.updateAndGet(current -> {
            List<String> next = new ArrayList<>(current);
            next.add(taskName);
            return List.copyOf(next);
        });
    }
}

public class SnapshotRegistryDemo {
    public static void main(String[] args) {
        SnapshotRegistry registry = new SnapshotRegistry();

        List<String> oldSnapshot = registry.current();
        registry.add("prepare");
        registry.add("publish");

        System.out.println(oldSnapshot);       // []
        System.out.println(registry.current()); // [prepare, publish]
    }
}
~~~~

**Vì sao cách này an toàn cho ví dụ?**

- Mỗi lần cập nhật tạo một `ArrayList` mới từ snapshot cũ rồi phát hành `List.copyOf(next)`.
- Snapshot cũ không bị sửa; thread đang đọc nó có thể tiếp tục đọc ổn định.
- `AtomicReference` thực hiện cập nhật nguyên tử và bảo đảm các quy tắc memory visibility của API.
- Phần tử `String` bất biến, nên không có object mutable bên trong cần khóa.

`AtomicReference.updateAndGet` có thể **gọi lại hàm cập nhật nhiều lần** khi có tranh chấp giữa các thread. Vì vậy lambda phải không tạo tác dụng phụ quan sát được bên ngoài, không ghi log nghiệp vụ đúng-một-lần hoặc gửi email từ trong lambda. Phần lambda ở ví dụ chỉ tạo cấu trúc mới và trả về snapshot.

Mô hình này phù hợp với dữ liệu không quá lớn và **đọc nhiều, cập nhật không thường xuyên**. Nếu cập nhật liên tục hoặc collection rất lớn, chi phí tạo bản sao mỗi lần có thể không phù hợp. Khi đó cần chọn cấu trúc concurrent hoặc cơ chế khóa theo nhu cầu thực tế.

### 8.3. Khi thật sự cần collection mutable dùng chung

Nếu các thread cùng thay đổi collection, hãy dùng cấu trúc hoặc quy ước đồng bộ có hợp đồng phù hợp:

- `ConcurrentHashMap` cho map truy cập đồng thời, có ngữ nghĩa nhất quán khác snapshot toàn bộ.
- `CopyOnWriteArrayList` cho tập listener hoặc danh sách ít ghi, đọc/lặp nhiều; mỗi thay đổi cấu trúc tạo bản sao mảng nội bộ.
- `Collections.synchronizedList`/`synchronizedMap` khi muốn wrapper đồng bộ trên collection hiện có, kèm quy tắc truy cập nhất quán.
- Sử dụng khóa `synchronized` hoặc `Lock` nếu cần nhiều thao tác kết hợp thành một **giao dịch nguyên tử**.

Ví dụ:

~~~~java
import java.util.*;

List<String> safeList =
        Collections.synchronizedList(new ArrayList<>());

safeList.add("A");
safeList.add("B");

// Phải đồng bộ thủ công khi duyệt bằng Iterator.
synchronized (safeList) {
    for (String value : safeList) {
        System.out.println(value);
    }
}
~~~~

Wrapper synchronized bảo vệ từng thao tác được hỗ trợ, nhưng **không tự làm một chuỗi thao tác riêng lẻ trở thành nguyên tử**. Với các phép kiểm tra-để-ghi (*check-then-act*) hoặc quá trình duyệt, cần khóa/thiết kế đồng bộ phù hợp. Đồng thời, code khác phải tránh truy cập trực tiếp backing collection bỏ qua wrapper.

### 8.4. An toàn chia sẻ không có nghĩa chỉ là chống concurrent modification

Tính an toàn còn bao gồm việc **ai sở hữu dữ liệu** và **ai được phép thay đổi trạng thái**. Ví dụ, nếu một dịch vụ trả view của map chứa hạn mức người dùng, khách hàng API có thể thấy những thay đổi mới mà không biết khi nào nó xảy ra. Nếu trả snapshot, người nhận có một ảnh dữ liệu tại thời điểm sao chép nhưng có thể cần yêu cầu snapshot mới để lấy cập nhật.

Không có lựa chọn nào luôn đúng trong mọi hoàn cảnh. Chọn **live view** khi mục đích là theo dõi trạng thái của một nguồn thuộc quyền kiểm soát và đã xác định đồng bộ; chọn **snapshot** khi ưu tiên tính ổn định, cách ly sửa đổi và tính lặp lại của phép tính.

## 9. Ví dụ tổng hợp: Từ dữ liệu cập nhật được đến kết quả công khai

Giả sử một dịch vụ nhận các sản phẩm, cần trả danh sách và bảng ánh xạ **ổn định về cấu trúc** cho API đọc:

~~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

record Item(String sku, int quantity) {
    Item {
        sku = Objects.requireNonNull(sku, "sku");
        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}

record InventorySnapshot(
        List<Item> items,
        Map<String, Integer> quantityBySku) {
    InventorySnapshot {
        items = List.copyOf(Objects.requireNonNull(items, "items"));
        quantityBySku = Map.copyOf(
                Objects.requireNonNull(quantityBySku, "quantityBySku"));
    }
}

public class InventorySnapshotDemo {
    static InventorySnapshot create(List<Item> input) {
        Objects.requireNonNull(input, "input");
        List<Item> copy = List.copyOf(input);

        Map<String, Integer> totals = new HashMap<>();
        for (Item item : copy) {
            totals.merge(item.sku(), item.quantity(), Math::addExact);
        }

        return new InventorySnapshot(copy, totals);
    }

    public static void main(String[] args) {
        List<Item> input = new ArrayList<>();
        input.add(new Item("BOOK", 2));
        input.add(new Item("PEN", 4));
        input.add(new Item("BOOK", 3));

        InventorySnapshot snapshot = create(input);

        input.clear();
        input.add(new Item("ERASER", 1));

        System.out.println(snapshot.items().size());  // 3
        System.out.println(snapshot.quantityBySku().get("BOOK")); // 5

        // snapshot.items().add(new Item("PEN", 1));
        // Dòng trên sẽ ném UnsupportedOperationException.
    }
}
~~~~

Đặc điểm của thiết kế:

1. `Item` là kiểu giá trị bất biến và kiểm tra dữ liệu đầu vào.
2. `create` sao chép list tại ranh giới để dùng một cấu trúc ổn định.
3. Các số lượng cùng mã được gộp bằng `Map.merge` và `Math.addExact`, tránh im lặng tràn số khi cộng.
4. `InventorySnapshot` thực hiện defensive copy ngay trong constructor, không giữ tham chiếu mutable đến `totals`.
5. Người nhận snapshot không thể thêm/xóa item hay thay ánh xạ trực tiếp.
6. Thay đổi list `input` sau khi tạo không ảnh hưởng kết quả; phần tử `Item` không chứa trường mutable.

Ví dụ là chương trình **đơn luồng**; nếu `input` được sửa đồng thời trong quá trình `List.copyOf(input)`, cần thêm cơ chế đồng bộ theo hợp đồng với bên cung cấp dữ liệu. Với `Map.copyOf`, thứ tự duyệt của các khóa không được bảo đảm.

## 10. Kiểm thử những hợp đồng quan trọng

Các kiểm thử nên xác nhận **hành vi** của view/snapshot thay vì dựa vào class implementation hoặc danh tính đối tượng.

| Trường hợp | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Unmodifiable view | Sửa backing sau khi lấy view | View có thể nhìn thấy thay đổi |
| Snapshot bằng `List.copyOf` | Sửa cấu trúc nguồn sau khi copy | Snapshot không đổi cấu trúc |
| Unmodifiable list | Gọi `add`/`set` trên kết quả | Báo `UnsupportedOperationException` |
| Shallow copy với phần tử mutable | Sửa object phần tử từ alias khác | Kết quả có thể thấy thay đổi |
| `List.of` có null | Tạo list chứa null | `NullPointerException` |
| `Set.of` có phần tử trùng | Truyền hai giá trị bằng nhau | `IllegalArgumentException` |
| `Set.copyOf` có phần tử trùng | Sao chép một collection chứa phần tử trùng | Còn một đại diện cho mỗi giá trị bằng nhau |
| `Map.of` khóa trùng | Truyền một key hai lần | `IllegalArgumentException` |
| `List.subList` | `set` một phần tử qua view trên ArrayList | Backing list thay đổi cùng vị trí |
| `List.reversed` | `set` qua reversed view của ArrayList | Backing list nhận giá trị tại đầu đối diện |
| `Stream.toList` | Gọi `add` | `UnsupportedOperationException` |
| Snapshot từ record | Sửa input sau khi tạo record | Getter không bị thay đổi về cấu trúc |
| CopyOnWrite/snapshot concurrency | Đọc khi writer công bố phiên bản mới | Reader thấy một phiên bản hợp lệ, không một list bị ghi dở |

Đối với tính ổn định đa luồng, kiểm thử nên bao phủ cả **khả năng nhìn thấy phiên bản mới** và **không thay đổi các snapshot cũ**. Đừng chỉ khẳng định an toàn dựa vào việc một bài test chạy vài lần không xuất hiện lỗi.

## 11. Những sai lầm dễ gặp

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Gọi `Collections.unmodifiableList` rồi cho rằng nguồn đã bị đóng băng | Wrapper là **view**, backing có thể đổi | Dùng `List.copyOf` hoặc tự tạo bản sao rồi bọc nếu cần snapshot |
| Cho rằng `List.copyOf` luôn tạo instance mới | API có thể tái sử dụng input đã unmodifiable | Kiểm tra `equals`/hành vi, không dựa vào `==` |
| Tưởng `List.copyOf` tự clone object phần tử | Copy nông ở mức collection | Dùng element bất biến hoặc sao chép/chuyển đổi từng phần tử |
| Trả `subList` của mutable list từ API công khai | Trả alias có thể sửa backing | Trả `List.copyOf(subList)` khi cần snapshot |
| Dùng `Arrays.asList` rồi `add` hoặc `remove` | List cố định kích thước do backing array | Dùng `new ArrayList<>(Arrays.asList(array))` |
| Dùng `Stream.toList()` rồi cố `add` | Kết quả unmodifiable | Dùng `toCollection(ArrayList::new)` hoặc tạo ArrayList mới |
| Mặc định `Collectors.toList()` mutable | API không bảo đảm | Yêu cầu implementation rõ ràng bằng `toCollection` |
| Cho phép null rồi dùng `List.copyOf` | `copyOf` từ chối null | Thay đổi hợp đồng null hoặc tự copy và bọc |
| Mong `Set.of` giữ thứ tự đối số | Iteration order không được bảo đảm | Dùng loại collection có encounter order phù hợp |
| Dùng object mutable làm key trong Map | Thay `equals`/`hashCode` có thể phá hợp đồng tra cứu | Dùng khóa bất biến hoặc giá trị ổn định |
| Nghĩ unmodifiable luôn thread-safe | Backing mutable hoặc phần tử mutable vẫn có data race | Sử dụng snapshot, safe publication và concurrency model đúng |
| Sao chép collection khi nguồn bị sửa đồng thời mà không đồng bộ | Không bảo đảm snapshot nguyên tử | Khóa nguồn hoặc dùng cấu trúc/thuật toán concurrent phù hợp |
| Coi `reversed()` là bản sao tĩnh | Đây là view theo thứ tự ngược | Dùng `List.copyOf(list.reversed())` khi cần snapshot |
| Khóa `synchronized` trên List.of/Map.of | Các đối tượng có thể value-based, không bảo đảm identity | Dùng khóa sở hữu riêng hoặc công cụ concurrent |

## 12. Hướng dẫn lựa chọn

| Nhu cầu thực tế | Lựa chọn khuyến nghị | Lý do |
| --- | --- | --- |
| Khai báo danh sách hằng đơn giản | `List.of` | Gọn, unmodifiable, không cho null |
| Khai báo tập giá trị hằng | `Set.of` | Không cho trùng và không cho null |
| Khai báo ánh xạ nhỏ | `Map.of` hoặc `Map.ofEntries` | Unmodifiable, từ chối key trùng/null |
| Nhận collection rồi lưu như snapshot | `List.copyOf`/`Set.copyOf`/`Map.copyOf` | Cách ly thay đổi cấu trúc sau khi copy |
| Trả view sống, quan sát backing | `Collections.unmodifiableList` hoặc wrapper tương ứng | Chặn sửa qua view nhưng tiếp tục phản ánh backing |
| Lấy một phần list để thao tác cùng list gốc | `subList` | View chia sẻ backing |
| Xem danh sách theo thứ tự đảo | `reversed()` | View đảo thứ tự, không cần tự copy |
| Muốn snapshot đảo thứ tự | `List.copyOf(list.reversed())` | Unmodifiable và không phụ thuộc thay đổi sau đó của nguồn |
| Muốn sao chép và tiếp tục chỉnh sửa | `new ArrayList<>(source)`/`new HashMap<>(source)` | Mutable copy |
| Muốn giữ null nhưng không cho sửa cấu trúc | `Collections.unmodifiableList(new ArrayList<>(source))` | Snapshot cấu trúc có thể chứa null |
| Muốn stream cho ra list không sửa được | `stream.toList()` | Ngắn gọn và hiện hành |
| Muốn stream cho ra ArrayList mutable | `collect(toCollection(ArrayList::new))` | Hợp đồng mutability và implementation rõ |
| Nhiều thread đọc, cập nhật hiếm | Snapshot unmodifiable được công bố an toàn | Reader không cần xử lý mutation tại chỗ của snapshot |
| Nhiều thread cùng cập nhật cấu trúc | Concurrent collection hoặc synchronization được thiết kế | Cung cấp ngữ nghĩa concurrency phù hợp |

### Checklist trước khi chia sẻ collection

- [ ] Đã xác định ai **sở hữu** collection gốc, ai được sửa và ai chỉ được đọc.
- [ ] Đã xác định cần **live view** hay **snapshot** tại một thời điểm.
- [ ] Nếu dùng view, đã chấp nhận rằng backing có thể thay đổi và hiểu quyền thao tác của view.
- [ ] Nếu dùng `copyOf`, đã xác định chính sách null, phần tử trùng và thứ tự duyệt.
- [ ] Đã xem xét các phần tử và giá trị lồng nhau có mutable hay không.
- [ ] Nếu nhận dữ liệu mutable rồi lưu, đã defensive copy **trước khi kiểm tra và lưu**.
- [ ] Nếu trả mảng hoặc mutable object, đã ngăn caller thay đổi trạng thái nội bộ ngoài ý muốn.
- [ ] Nếu dữ liệu chia sẻ giữa các thread, đã thiết kế visibility/atomicity và bảo đảm element safety.
- [ ] Không dựa vào identity hoặc loại implementation của các factory unmodifiable.
- [ ] Có kiểm thử cho aliasing, mutation sau khi copy, null, duplicate và truy cập đồng thời.

## Tài liệu tham khảo

- [Java SE 27 – List](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): `List.of`, `List.copyOf`, `subList`, `reversed` và hợp đồng unmodifiable list.
- [Java SE 27 – Set](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html): `Set.of`, `Set.copyOf`, chính sách null/duplicate và thứ tự.
- [Java SE 27 – Map](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html): `Map.of`, `Map.copyOf`, `keySet`, `values` và `entrySet`.
- [Java SE 27 – Collections](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html): các wrapper `unmodifiable*` và `synchronized*`.
- [Java SE 27 – SequencedCollection](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/SequencedCollection.html): encounter order và reversed view.
- [Java SE 27 – Stream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html) và [Collectors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collectors.html): `toList`, `toCollection`, `toUnmodifiableList` và `toUnmodifiableMap`.
- [Java SE 27 – AtomicReference](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): cập nhật nguyên tử và công bố snapshot.

**Tóm lại:** view trả một cách **quan sát hoặc thao tác dữ liệu đang có**; copy tạo **cấu trúc mới**; unmodifiable chặn **thao tác sửa qua giao diện**; còn bất biến theo chiều sâu đòi hỏi **phần tử và dữ liệu lồng nhau** cũng không có trạng thái mutable bị chia sẻ. Khi thiết kế API Java 27, chọn đúng một trong các hành vi này quan trọng hơn việc chỉ tìm một collection “không gọi được `add`”. Mô hình sở hữu, defensive copy và cơ chế chia sẻ giữa các thread mới là nền tảng để dữ liệu thực sự an toàn.
