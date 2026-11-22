# Collection không thể sửa đổi và đối tượng bất biến trong Java hiện đại

## 1. Mục tiêu học tập

Một **collection không thể sửa đổi** (*unmodifiable collection*) chặn những thao tác như thêm, xóa hoặc thay phần tử thông qua chính collection đó. Một **đối tượng bất biến** (*immutable object*) có trạng thái quan sát được không thay đổi sau khi khởi tạo. Hai khái niệm liên quan nhưng **không đồng nghĩa**: một collection không cho sửa cấu trúc vẫn có thể giữ tham chiếu tới những phần tử mutable; một *unmodifiable view* còn có thể phản ánh thay đổi từ collection nguồn.

Java 10 bổ sung `List.copyOf`, `Set.copyOf`, `Map.copyOf` và nhóm `Collectors.toUnmodifiable...`, giúp tạo bản sao hoặc kết quả Stream không cho sửa cấu trúc. Những API này vẫn được sử dụng trong các JDK hiện đại, bên cạnh `List.of`, `Set.of`, `Map.of` được giới thiệu từ Java 9.

Sau bài này, bạn có thể:

- Phân biệt **mutable collection**, **unmodifiable view**, **unmodifiable snapshot** và **immutable object**.
- Chọn đúng `Collections.unmodifiableList`, `List.copyOf`, `List.of` hoặc `Collectors.toUnmodifiableList` theo nhu cầu.
- Giải thích *shallow immutability* và vì sao `List.copyOf` không sao chép sâu các phần tử.
- Chống lỗi thay đổi dữ liệu ngoài ý muốn bằng **defensive copy** khi nhận và trả dữ liệu.
- Hiểu chính sách `null`, phần tử/key trùng, thứ tự duyệt, so sánh giá trị và chia sẻ giữa các luồng.
- Biên dịch và chạy một ví dụ Java 17+ minh họa các trường hợp thực tế.

**Phạm vi:** Chỉ các quy tắc và API còn hữu ích trong Java hiện đại. Các API của Java 9/16 được đề cập để phân biệt thời điểm giới thiệu; trọng tâm Java 10 là họ `copyOf` và các collector không cho sửa đổi.

## 2. Các thuật ngữ phải phân biệt

| Khái niệm | Có thể sửa collection qua tham chiếu đang giữ? | Thay đổi từ nguồn có phản ánh không? | Phần tử mutable có đổi trạng thái được không? |
| --- | --- | --- | --- |
| **Mutable collection** như `ArrayList` | Có, tùy thao tác/API | Chính đối tượng đang được sửa | Có |
| **Unmodifiable view** như `Collections.unmodifiableList(source)` | Không | **Có** nếu nguồn được sửa qua tham chiếu khác | Có |
| **Unmodifiable snapshot** như `List.copyOf(source)` | Không | **Không** đối với thay đổi cấu trúc nguồn sau khi chụp | Có nếu phần tử là mutable |
| **Immutable object/giá trị thực sự bất biến** | Không áp dụng như thao tác sửa trạng thái | Không thể quan sát thay đổi trạng thái sau khởi tạo | Các thành phần có thể truy cập không được cho phép làm đổi trạng thái quan sát được |

Trong Java Collections Framework, *unmodifiable* chủ yếu diễn đạt **hợp đồng của thao tác cập nhật collection**. Nó không tự bảo đảm tất cả đối tượng trong đồ thị tham chiếu đều bất biến.

**Ví dụ đơn giản:** một danh sách `List<String>` được tạo bởi `List.of("A", "B")` vừa không cho sửa cấu trúc vừa chứa các `String` bất biến, nên thường có thể xem giá trị danh sách là bất biến. Nhưng `List<StringBuilder>` dù tạo bằng `List.of(...)` vẫn giữ các `StringBuilder` có thể thay đổi.

## 3. Unmodifiable collection khác immutable object thế nào?

### 3.1. Không sửa cấu trúc collection

Một `List` không cho sửa đổi phải từ chối các thao tác cập nhật qua API của nó như `add`, `remove`, `clear` và `set`:

~~~java
var names = List.of("An", "Binh"); // List.of: Java 9+
// names.add("Chi");               // UnsupportedOperationException khi chạy
// names.set(0, "Chi");            // UnsupportedOperationException khi chạy
~~~

Các câu lệnh bị chú thích **có thể biên dịch** vì `List` có những phương thức đó; chúng sẽ ném `UnsupportedOperationException` khi thực thi trên danh sách không sửa được. Đây là lỗi runtime, không phải compiler tự cấm lời gọi.

Với `Set` và `Map`, các thao tác như `add`, `remove`, `put`, `replace` cũng bị từ chối nếu cố sửa cấu trúc từ đối tượng không cho sửa đổi.

### 3.2. Đối tượng bên trong vẫn có thể thay đổi

~~~java
var element = new StringBuilder("draft");
var safeOuterList = List.of(element);

element.append("-edited");
System.out.println(safeOuterList.get(0)); // draft-edited
~~~

`safeOuterList` không cho thêm, xóa hoặc thay vị trí phần tử. Tuy nhiên, đối tượng `StringBuilder` đang được tham chiếu vẫn mutable. Danh sách quan sát thấy nội dung mới của **cùng một phần tử**.

Đây là **bất biến nông** (*shallow immutability*): cấu trúc bên ngoài được bảo vệ, trạng thái sâu bên trong đối tượng không được tự động sao chép hoặc đóng băng.

Với một đối tượng nghiệp vụ, tính bất biến cần xét cả **trạng thái quan sát được** qua API. Field `final` chỉ ngăn gán lại tham chiếu; nếu tham chiếu trỏ tới `ArrayList` thì vẫn có thể gọi `add` trên danh sách đó.

## 4. Các factory method không cho sửa đổi

### 4.1. `List.of`, `Set.of` và `Map.of` (Java 9+)

Dùng khi các phần tử hoặc các cặp key/value đã có tại thời điểm khởi tạo:

~~~java
var cities = List.of("Ha Noi", "Da Nang", "Hue");
var roles = Set.of("reader", "writer");
var limits = Map.of("retry", 3, "batch", 20);
~~~

- `List.of` giữ thứ tự các đối số và **cho phép phần tử trùng lặp**.
- `Set.of` không cho phần tử trùng theo `equals`; nếu truyền phần tử trùng, phương thức ném `IllegalArgumentException`.
- `Map.of` không cho key trùng; key trùng gây `IllegalArgumentException`. Với nhiều hơn số cặp được hỗ trợ trong overload cố định, có thể dùng `Map.ofEntries(...)`.
- Ba nhóm factory này **không chấp nhận `null`** làm phần tử, key hoặc value tương ứng; vi phạm gây `NullPointerException`.
- Kết quả không cho sửa cấu trúc. Không dựa vào thứ tự duyệt của `Set.of` hoặc `Map.of`, vì API không cam kết thứ tự ổn định.

`List.of` thích hợp với dữ liệu cố định từ mã nguồn. Nếu dữ liệu đã được tập hợp trong một collection có thể sửa đổi, `copyOf` của Java 10 thường đúng mục đích hơn.

### 4.2. `List.copyOf`, `Set.copyOf`, `Map.copyOf` (Java 10+)

Ba phương thức này tạo collection không cho sửa đổi dựa trên **dữ liệu đang có**:

~~~java
var mutableList = new ArrayList<>(List.of("A", "B"));
var snapshotList = List.copyOf(mutableList);

var mutableSet = new HashSet<>(Set.of("reader", "writer"));
var snapshotSet = Set.copyOf(mutableSet);

var mutableMap = new HashMap<String, Integer>();
mutableMap.put("retry", 3);
var snapshotMap = Map.copyOf(mutableMap);
~~~

| Phương thức | Đầu vào | Đặc điểm |
| --- | --- | --- |
| `List.copyOf(Collection<? extends E>)` | Collection các phần tử | Danh sách kết quả giữ **thứ tự duyệt của đầu vào** tại thời điểm tạo; không cho sửa cấu trúc. |
| `Set.copyOf(Collection<? extends E>)` | Collection các phần tử | Loại trùng theo quy tắc `Set`; không hứa thứ tự duyệt. |
| `Map.copyOf(Map<? extends K, ? extends V>)` | Map key/value | Giữ các ánh xạ tại thời điểm tạo; không cho sửa; không hứa thứ tự duyệt. |

Các factory `copyOf` từ chối `null` ở đầu vào và từ chối phần tử `null`; với Map, **cả key lẫn value không được `null`**.

**Ý nghĩa snapshot:** khi tạo từ một collection có thể sửa đổi, snapshot **không phản ánh việc thêm/xóa/thay ánh xạ ở nguồn sau đó**. Nếu đối tượng nguồn ban đầu đã thực sự không cho sửa đổi, runtime có thể tái sử dụng instance thay vì tạo mới. **Không dựa vào phép so sánh `==` để kết luận có hay không có một bản sao**, và không dùng danh tính instance làm hợp đồng API.

### 4.3. Khác biệt khi có phần tử trùng

~~~java
var duplicates = List.of("A", "A", "B");

var list = List.copyOf(duplicates); // vẫn có 3 phần tử
var set = Set.copyOf(duplicates);   // có 2 phần tử
// Set.of("A", "A");                 // ném IllegalArgumentException khi chạy
~~~

`Set.copyOf` không ném lỗi chỉ vì nguồn `Collection` có phần tử trùng; nó giữ một phần tử đại diện trong mỗi nhóm tương đương theo `equals`. Nếu các đối tượng khác nhau nhưng được xem là bằng nhau, việc chọn **đối tượng đại diện** không được cam kết. Không dựa vào chi tiết đó để chọn “bản ghi thắng”.

## 5. Unmodifiable view khác unmodifiable snapshot

Đây là khác biệt quan trọng nhất khi thiết kế ranh giới API.

### 5.1. View: `Collections.unmodifiableList(source)`

~~~java
var source = new ArrayList<>(List.of("A", "B"));
var view = Collections.unmodifiableList(source);

source.add("C");
System.out.println(view); // [A, B, C]
~~~

`view` chặn thao tác cập nhật **thông qua `view`**, nhưng vẫn dùng trạng thái hiện tại của `source`. Nếu người khác giữ tham chiếu `source` và thêm/xóa phần tử, giá trị quan sát qua `view` sẽ thay đổi.

### 5.2. Snapshot: `List.copyOf(source)`

~~~java
var source = new ArrayList<>(List.of("A", "B"));
var snapshot = List.copyOf(source);

source.add("C");
System.out.println(snapshot); // [A, B]
~~~

`snapshot` giữ các phần tử tại thời điểm sao chép cấu trúc. Sau `source.add("C")`, snapshot vẫn có hai phần tử.

### 5.3. So sánh trực tiếp

| Tiêu chí | `Collections.unmodifiableList(source)` | `List.copyOf(source)` |
| --- | --- | --- |
| Có thể gọi `add`, `set` trực tiếp lên kết quả? | Không | Không |
| Thay đổi cấu trúc nguồn có hiện lên kết quả? | Có, vì là view | Không |
| Thích hợp làm snapshot tại ranh giới API? | Không nếu nguồn còn có thể bị sửa | Có |
| Có sao chép sâu phần tử mutable? | Không | Không |
| Nếu nguồn đã không sửa được? | Vẫn là một view | Có thể tái sử dụng collection không sửa được |
| Chính sách `null` ở kết quả | Phụ thuộc collection nguồn | Từ chối `null` |

**Ví dụ phản trực giác:** nếu view được tạo từ một danh sách chứa `null`, việc đó không tự bị cấm. Ngược lại, `List.copyOf` từ chối giá trị `null`. Vì vậy “unmodifiable” **không tự đồng nghĩa** với “không chứa null”; phải đọc hợp đồng của từng API.

### 5.4. Khi nào unmodifiable view vẫn có ích?

View vẫn là công cụ hợp lệ khi chủ sở hữu collection **cố ý muốn người khác đọc trạng thái mới nhất** nhưng chỉ muốn cấp quyền truy cập qua giao diện không cho sửa đổi. Ví dụ bộ theo dõi tiến trình có một danh sách được cập nhật nội bộ và có view để các thành phần khác chỉ đọc.

Nhưng view không cung cấp snapshot ổn định. Nếu có nhiều luồng đọc/ghi collection nguồn, chỉ dùng unmodifiable view **không tự giải quyết đồng bộ hóa và thread safety**.

## 6. `copyOf` là shallow copy: phần tử mutable vẫn chung tham chiếu

~~~java
var note = new StringBuilder("first");
var source = new ArrayList<StringBuilder>();
source.add(note);

var copy = List.copyOf(source);
note.append("-changed");

System.out.println(copy.get(0)); // first-changed
~~~

`List.copyOf` chỉ sao chép **các tham chiếu phần tử vào cấu trúc mới nếu cần**, không gọi `clone()` trên từng phần tử. `source.get(0)` và `copy.get(0)` có thể trỏ tới **cùng đối tượng** `StringBuilder`.

Vì thế, hai điều đều đúng:

1. `copy.add(new StringBuilder("extra"))` không được cho phép.
2. `copy.get(0).append("...")` có thể hợp lệ vì `get(0)` trả phần tử mutable.

Tương tự, `Map.copyOf` tạo map không cho thêm/xóa/sửa ánh xạ nhưng không tự sao chép sâu các value; nếu value là một `List` có thể thay đổi, người giữ tham chiếu đến value vẫn có thể tác động tới nội dung được quan sát qua map.

**Lưu ý riêng cho `Set` và key của `Map`:** các đối tượng được dùng trong `equals`/`hashCode` nên có thuộc tính xác định equality ổn định. Thay đổi trạng thái dùng cho hash/equality sau khi đưa vào Set hoặc dùng làm key của Map có thể làm hỏng giả định tra cứu. Tốt nhất dùng khóa bất biến.

## 7. Tạo đối tượng nghiệp vụ thật sự bất biến bằng defensive copy

Một lớp/record có field `final` không tự động bảo vệ collection được truyền vào constructor. Cần **sao chép phòng vệ khi nhận dữ liệu**, đồng thời không trả ra một tham chiếu cho phép sửa dữ liệu nội bộ.

### 7.1. Ví dụ dễ bị rò rỉ trạng thái

~~~java
record UnsafeTicket(String id, List<String> labels) { }
~~~

`record` tự có accessor `labels()` và các thành phần được lưu vào field cuối cùng, nhưng **không tự sao chép `labels`**:

~~~java
var labels = new ArrayList<>(List.of("open"));
var ticket = new UnsafeTicket("T-1", labels);
labels.add("late"); // ticket.labels() cũng phản ánh phần tử mới
~~~

Đây là ví dụ cú pháp theo Java 17+. `UnsafeTicket` biểu diễn sự khác nhau giữa “field tham chiếu không gán lại” và “đối tượng bất biến”.

### 7.2. Defensive copy bằng `List.copyOf`

~~~java
import java.util.List;
import java.util.Objects;

record Ticket(String id, List<String> labels) {
    public Ticket {
        Objects.requireNonNull(id);
        labels = List.copyOf(labels);
    }
}
~~~

Đây là **định nghĩa record độc lập ở cấp lớp/package**, không phải nội dung gõ tùy ý vào giữa một phương thức.

Trong compact constructor của record, `labels = List.copyOf(labels)` chuẩn hóa dữ liệu trước khi Java gán vào field record. Vì vậy:

~~~java
var original = new ArrayList<>(List.of("open"));
var ticket = new Ticket("T-1", original);

original.add("late");     // không làm đổi ticket.labels()
// ticket.labels().add("x"); // UnsupportedOperationException
~~~

Với `String` là phần tử bất biến, record này bảo vệ được trạng thái quan sát qua `labels()` khỏi các thao tác sửa collection. Dùng `List.copyOf` còn loại bỏ `null` phần tử theo một quy tắc rõ ràng.

Nếu cần cho phép `null` hoặc muốn giữ kiểu collection có thể sửa được nội bộ, phải thiết kế hợp đồng rõ ràng thay vì mặc định `copyOf` luôn thích hợp.

### 7.3. Các đối tượng lồng nhau cần xử lý từng cấp

Giả sử có `List<List<String>>`:

~~~java
var inner = new ArrayList<>(List.of("A"));
var outer = new ArrayList<List<String>>();
outer.add(inner);

var outerCopy = List.copyOf(outer);
inner.add("B");

System.out.println(outerCopy.get(0)); // [A, B]
~~~

`outerCopy` không cho thay danh sách con ở vị trí 0, nhưng vẫn giữ tham chiếu tới `inner` mutable.

Để bất biến ở **hai cấp danh sách**, có thể sao chép từng danh sách con:

~~~java
var twoLevelCopy = outer.stream()
        .map(List::copyOf)
        .toList();
~~~

`Stream.toList()` có từ Java 16, trả danh sách không cho sửa. `List.copyOf` cho từng danh sách con có từ Java 10. Cách làm này chỉ bảo vệ **hai cấp collection đang xét**; không phải một thuật toán deep copy tổng quát cho mọi đồ thị đối tượng.

Nếu danh sách chứa các đối tượng nghiệp vụ mutable, cần chuyển chúng thành **giá trị bất biến** (ví dụ record chỉ chứa `String`, primitive, giá trị bất biến khác) hoặc chủ động tạo snapshot cho từng đối tượng theo hợp đồng riêng.

## 8. Collectors tạo kết quả Stream không cho sửa (Java 10+)

Java 10 có các collector:

| API | Kết quả | Điều cần nhớ |
| --- | --- | --- |
| `Collectors.toUnmodifiableList()` | Danh sách không sửa được | Giữ encounter order nếu Stream có thứ tự; từ chối `null`. |
| `Collectors.toUnmodifiableSet()` | Tập hợp không sửa được | Loại phần tử trùng; không hứa thứ tự; từ chối `null`. |
| `Collectors.toUnmodifiableMap(keyMapper, valueMapper)` | Map không sửa được | Trùng key ném `IllegalStateException`; key/value `null` bị từ chối. |
| `Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)` | Map không sửa được | Tự quy định cách gộp khi key trùng. |

Ví dụ lọc dữ liệu rồi chốt danh sách:

~~~java
var words = List.of("java", "api", "java");
var selected = words.stream()
        .filter(value -> value.length() > 3)
        .collect(Collectors.toUnmodifiableList());

System.out.println(selected); // [java, java]
~~~

Vì `List` cho phép giá trị trùng, hai phần tử `"java"` vẫn có mặt. Với collector thành `Set`, phần tử trùng theo equality chỉ xuất hiện một lần; không dựa vào thứ tự duyệt khi in tập hợp.

Ví dụ đếm nhóm key trùng:

~~~java
var counts = List.of("tea", "water", "tea").stream()
        .collect(Collectors.toUnmodifiableMap(
                word -> word,
                word -> 1,
                Integer::sum));

System.out.println(counts.get("tea")); // 2
~~~

Nếu bỏ `Integer::sum` và dùng overload chỉ nhận hai mapper, hai phần tử cùng key `"tea"` khiến collector ném `IllegalStateException`. Khi nghiệp vụ có key trùng, bắt buộc chọn quy tắc gộp rõ ràng thay vì tin map tự chọn bản ghi.

### 8.1. So sánh với những phương thức gần giống

- `Collectors.toList()` **không cam kết** collection trả về sửa được hay không, không nên coi nó là hợp đồng immutable.
- `Stream.toList()` (Java 16+) trả **danh sách không cho sửa** và giữ encounter order khi có. Nó khác `Collectors.toUnmodifiableList()` ở chính sách `null`; không thay thế hai phương thức máy móc nếu luồng có thể chứa `null`.
- `Collectors.toCollection(ArrayList::new)` tạo một danh sách cụ thể có thể sửa khi nghiệp vụ cần tiếp tục cập nhật.
- `List.copyOf(existing)` phù hợp để chốt collection có sẵn; `Collectors.toUnmodifiableList()` phù hợp để chốt đầu ra pipeline; `List.of(...)` phù hợp với phần tử định nghĩa ngay lúc tạo.

## 9. Null, thứ tự duyệt, identity và các quy tắc khó thấy

### 9.1. Chính sách `null`

~~~java
// List.of("A", null);       // NullPointerException
// Set.of("A", null);        // NullPointerException
// Map.of("x", null);        // NullPointerException

var values = new ArrayList<String>();
values.add(null);
// List.copyOf(values);       // NullPointerException
~~~

Các factory `of`/`copyOf` và collector `toUnmodifiable...` được thiết kế với chính sách không chấp nhận `null`. Nhưng một **unmodifiable view** của danh sách có `null` có thể vẫn chứa `null`. Khi nhập dữ liệu từ database/JSON hoặc bên ngoài, hãy quyết định giá trị thiếu là lỗi, giá trị mặc định hay trạng thái hợp lệ **trước** khi tạo snapshot.

### 9.2. Trùng lặp và thứ tự

| Trường hợp | Hành vi |
| --- | --- |
| `List.of("A", "A")` hoặc `List.copyOf(...)` | Cho phần tử trùng và giữ thứ tự danh sách. |
| `Set.of("A", "A")` | Ném `IllegalArgumentException`. |
| `Set.copyOf(List.of("A", "A"))` | Kết quả chỉ có một phần tử `"A"`. |
| `Map.of("k", 1, "k", 2)` | Ném `IllegalArgumentException` vì key trùng. |
| `Collectors.toUnmodifiableMap(...)` với key trùng, không có merge function | Ném `IllegalStateException`. |
| `Set.of`, `Set.copyOf`, `Map.of`, `Map.copyOf` | Không cam kết thứ tự duyệt; tránh logic dựa vào thứ tự hiện trên console. |

Nếu cần biểu diễn một thứ tự nghiệp vụ, hãy chọn cấu trúc và hợp đồng sắp xếp phù hợp (ví dụ danh sách đã được sort), thay vì giả định Map/Set từ các factory sẽ giữ thứ tự thêm vào.

### 9.3. Đừng dùng `==` làm thước đo “bản sao”

Các collection tạo bởi factory `List.of`/`copyOf`, tương tự `Set`/`Map` factory, có thể là **value-based**. Chúng được phép tái sử dụng instance; hợp đồng nên dựa vào **giá trị** qua `equals`, không dựa vào reference equality (`==`), `System.identityHashCode` hay việc khóa `synchronized` trên chính instance đó.

~~~java
var first = List.of("A", "B");
var second = List.copyOf(first);

System.out.println(first.equals(second)); // true
// Không dựa vào first == second.
~~~

Chức năng bảo vệ dữ liệu khỏi sửa cấu trúc không đòi hai đối tượng bắt buộc khác địa chỉ bộ nhớ.

## 10. `final`, array, record và ý nghĩa của bất biến

Một số khái niệm trông giống nhau nhưng có hợp đồng khác nhau:

- **`final List<String> names = new ArrayList<>();`**: chỉ cấm gán lại biến `names`; có thể thêm/xóa phần tử vì bản thân `ArrayList` mutable.
- **`List<String> names = List.of("A");`**: không thể sửa cấu trúc danh sách; biến `names` vẫn có thể được gán tham chiếu khác nếu không khai báo `final`.
- **`final List<String> names = List.copyOf(source);`**: vừa không gán lại được biến, vừa không sửa cấu trúc collection qua tham chiếu đó; vẫn cần xem phần tử có mutable hay không.
- **`final byte[] data`**: array vẫn cho sửa `data[0]`; `final` không biến array thành bất biến.
- **Record có thành phần mutable**: record không tự clone list, array hoặc đối tượng được truyền vào. Muốn bất biến về trạng thái quan sát được, phải dùng defensive copy hoặc giá trị bất biến.

**Một tiêu chí kiểm tra tốt:** hỏi “người gọi hoặc thành phần khác còn giữ đường đi nào để thay đổi trạng thái mà đối tượng của tôi trả về hay không?”. Nếu còn, thiết kế chưa bảo đảm bất biến quan sát được.

## 11. Chia sẻ collection giữa các luồng

Collection không cho sửa cấu trúc thường dễ chia sẻ để **đọc** vì không có thao tác cập nhật cấu trúc từ chính đối tượng đó. Tuy nhiên:

1. **Unmodifiable view** có thể phản ánh thay đổi nguồn; nếu luồng khác sửa nguồn mà không đồng bộ, vẫn có thể có race condition và quan sát không nhất quán.
2. **Unmodifiable snapshot** không thay đổi cấu trúc sau khi tạo, nhưng nếu chứa phần tử mutable được sửa từ luồng khác thì dữ liệu quan sát được vẫn có thể thay đổi và phát sinh race.
3. **Đối tượng bất biến thực sự** với các thành phần bất biến và được công bố (*published*) an toàn thường phù hợp cho chia sẻ đọc giữa nhiều luồng mà không cần khóa để bảo vệ trạng thái bất biến đó.

Unmodifiable collection **không phải** cấu trúc đồng bộ tự động. Nếu cần cập nhật đồng thời, hãy chọn chiến lược quản lý concurrency đúng với nghiệp vụ; không chỉ thêm `Collections.unmodifiableList` bên ngoài một danh sách đang bị sửa đồng thời rồi coi là đã an toàn.

## 12. Chương trình Java 17+ đầy đủ, có thể chạy

Tạo file **`UnmodifiableVsImmutableDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

public class UnmodifiableVsImmutableDemo {
    static final class Tag {
        private String name;

        Tag(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        void rename(String next) {
            name = next;
        }
    }

    record Ticket(String id, List<String> labels) {
        public Ticket {
            Objects.requireNonNull(id);
            labels = List.copyOf(labels); // defensive copy
        }
    }

    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("A", "B"));
        var view = Collections.unmodifiableList(source);
        var snapshot = List.copyOf(source);

        source.add("C");
        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            view.add("D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("view add blocked");
        }

        try {
            snapshot.set(0, "Z");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot set blocked");
        }

        var tag = new Tag("draft");
        var shallow = List.copyOf(List.of(tag));
        tag.rename("edited");
        System.out.println("shared element=" + shallow.get(0).name());

        var raw = new ArrayList<>(List.of("open"));
        var ticket = new Ticket("T-1", raw);
        raw.add("late");
        System.out.println("ticket labels=" + ticket.labels());

        var counts = List.of("tea", "water", "tea").stream()
                .collect(Collectors.toUnmodifiableMap(
                        word -> word,
                        word -> 1,
                        Integer::sum));
        System.out.println("tea count=" + counts.get("tea"));

        var unique = Set.copyOf(List.of("A", "A", "B"));
        System.out.println("unique count=" + unique.size());

        var nullable = new ArrayList<String>();
        nullable.add(null);
        try {
            List.copyOf(nullable);
        } catch (NullPointerException ex) {
            System.out.println("null rejected");
        }
    }
}
~~~

Chạy từ thư mục chứa file bằng **JDK 17 hoặc mới hơn**:

~~~bash
javac UnmodifiableVsImmutableDemo.java
java UnmodifiableVsImmutableDemo
~~~

**Stdout chính xác:**

~~~text
source=[A, B, C]
view=[A, B, C]
snapshot=[A, B]
view add blocked
snapshot set blocked
shared element=edited
ticket labels=[open]
tea count=2
unique count=2
null rejected
~~~

### Giải thích kết quả theo từng phần

1. `source` đã được thêm `"C"`. `view` phản ánh thay đổi vì nó là **view**; `snapshot` vẫn giữ `[A, B]` vì là bản sao cấu trúc.
2. `view.add` và `snapshot.set` đều bị chặn bằng `UnsupportedOperationException`.
3. `shallow` không thể bị thay đổi cấu trúc qua API List, nhưng vẫn chứa chính đối tượng `Tag` mutable. `tag.rename("edited")` làm phần tử được đọc thành `edited`.
4. `Ticket` sao chép `labels` bằng `List.copyOf` trong compact constructor. Vì vậy việc thêm `"late"` vào `raw` không làm thay đổi `ticket.labels()`; ở đây phần tử `String` cũng bất biến.
5. Collector `toUnmodifiableMap` chốt kết quả không sửa được; `Integer::sum` xử lý key `"tea"` xuất hiện hai lần, tạo count `2`.
6. `Set.copyOf` loại phần tử trùng; chương trình chỉ in **kích thước** để không phụ thuộc thứ tự duyệt không được cam kết.
7. `List.copyOf` từ chối `null` bằng `NullPointerException`, được bắt để minh họa rõ chính sách dữ liệu.

Chương trình chỉ phụ thuộc JDK chuẩn, và có thể biên dịch trên Java 17+. Các API Java 10 như `List.copyOf`/`Set.copyOf`/`Collectors.toUnmodifiableMap` vẫn hoạt động nguyên ý nghĩa trong JDK hiện đại.

## 13. Lỗi thường gặp và cách sửa

| Lỗi/giả định sai | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `Collections.unmodifiableList(source)` rồi coi dữ liệu là snapshot | Người giữ `source` có thể khiến view thay đổi | Dùng `List.copyOf(source)` khi cần chốt dữ liệu. |
| Tạo `List.copyOf` chứa phần tử mutable rồi coi là bất biến sâu | Đối tượng phần tử vẫn có thể đổi | Chuyển phần tử thành giá trị bất biến hoặc sao chép có kiểm soát. |
| Chỉ gắn `final` cho tham chiếu `ArrayList` | Không chặn `add`/`remove` | Thiết kế bất biến cho chính collection hoặc chuyển sang factory không cho sửa. |
| Record chứa `List` nhưng constructor không sao chép | Caller còn giữ tham chiếu có thể sửa | Defensive copy trong canonical/compact constructor. |
| Truyền `null` vào `of`/`copyOf` | Ném `NullPointerException` | Chốt chính sách dữ liệu thiếu trước khi tạo. |
| Gọi `Set.of` với phần tử trùng | Ném `IllegalArgumentException` | Loại trùng trước hoặc dùng `Set.copyOf` khi mong muốn gom trùng. |
| Dùng `toUnmodifiableMap` với key trùng | Ném `IllegalStateException` | Cung cấp `mergeFunction` có ngữ nghĩa nghiệp vụ. |
| Phụ thuộc thứ tự in của `Map.of`/`Set.of` | Kết quả có thể thay đổi qua lần chạy | Sắp xếp khi cần hoặc dùng cấu trúc có hợp đồng thứ tự phù hợp. |
| Dựa vào `==` để nhận biết copy hay reuse | Có thể sai khi runtime tái sử dụng instance | So sánh giá trị bằng `equals`; tuân theo API contract. |
| Giả định unmodifiable view an toàn khi nguồn bị sửa đa luồng | Có nguy cơ race và trạng thái không nhất quán | Quản lý concurrency hoặc dùng snapshot với thành phần bất biến và safe publication. |

## 14. Bài tập tự kiểm tra

**Câu 1.** Cho:

~~~java
var source = new ArrayList<>(List.of("x"));
var view = Collections.unmodifiableList(source);
var copy = List.copyOf(source);
source.add("y");
~~~

Hãy dự đoán `view.size()` và `copy.size()`.

**Đáp án:** `view.size() == 2` và `copy.size() == 1`. View theo nguồn; copy không theo thay đổi cấu trúc sau đó.

**Câu 2.** Vì sao `List.of(new StringBuilder("a"))` không phải giá trị bất biến sâu?

**Đáp án:** List không sửa cấu trúc, nhưng phần tử `StringBuilder` mutable. Tham chiếu đến phần tử có thể gọi `append`, khiến nội dung quan sát được thay đổi.

**Câu 3.** `Set.copyOf(List.of("a", "a", "b"))` có ném lỗi do trùng không? `Set.of("a", "a", "b")` thì sao?

**Đáp án:** `Set.copyOf` tạo set có 2 phần tử; `Set.of` ném `IllegalArgumentException`.

**Câu 4.** Nếu một record có component `List<String> labels` và không sao chép trong constructor, record đó có bảo vệ dữ liệu trước việc caller thêm vào danh sách nguồn không?

**Đáp án:** Không. Record lưu cùng tham chiếu được truyền vào. Hãy dùng `labels = List.copyOf(labels);` trong compact constructor khi mục đích là một snapshot không sửa được.

**Câu 5.** Vì sao `Collectors.toList()` và `Collectors.toUnmodifiableList()` không nên được coi là tương đương?

**Đáp án:** `Collectors.toList()` không cam kết đặc tính sửa được/không sửa được của kết quả; `toUnmodifiableList()` cam kết không sửa cấu trúc và không chấp nhận phần tử `null`.

**Câu 6.** Một `Map<String, ArrayList<String>>` được chuyển bằng `Map.copyOf`. Người dùng vẫn có thể đổi danh sách ở value không?

**Đáp án:** Có, nếu họ giữ tham chiếu tới `ArrayList` bên trong. `Map.copyOf` không deep copy value. Cần sao chép từng value thành danh sách không sửa được hoặc dữ liệu bất biến theo yêu cầu.

**Câu 7.** Có được dùng `synchronized(snapshot)` hoặc `snapshot1 == snapshot2` làm cơ sở logic của các List tạo từ factory không?

**Đáp án:** Không nên. Những collection factory này có thể là value-based; không dựa vào danh tính object cho đồng bộ hoặc hợp đồng logic. Dùng cơ chế đồng bộ chuyên biệt khi cần.

## 15. Checklist trước khi trả collection ra khỏi API

- [ ] Tôi có muốn **live view** cập nhật theo nguồn, hay **snapshot** độc lập với thay đổi cấu trúc?
- [ ] Collection có cần sửa tiếp sau khi khởi tạo không? Nếu có, dùng mutable collection phù hợp.
- [ ] Nếu dùng `copyOf`, đầu vào có thể chứa `null` không? Tôi đã xác định chính sách xử lý chưa?
- [ ] Nếu dùng `Set`/`Map`, dữ liệu có thể trùng phần tử/key không? Quy tắc gom trùng là gì?
- [ ] Giá trị bên trong có mutable không? Nếu có, cần defensive copy từng cấp hay chuyển sang immutable value?
- [ ] Constructor, getter hoặc API khác có làm lộ tham chiếu mutable nội bộ không?
- [ ] Code có vô tình phụ thuộc thứ tự duyệt hoặc identity của factory collection không?
- [ ] Nếu chia sẻ giữa các luồng, dữ liệu có bất biến thực sự và được công bố an toàn không?
- [ ] Tôi đã chọn đúng API theo mục đích: `of`, `copyOf`, `toUnmodifiable...`, `Stream.toList` hay `Collections.unmodifiable...`?

## 16. Tài liệu chính thức

- [Oracle Java 25 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): sự khác nhau giữa snapshot, view, các phần tử mutable, xử lý trùng lặp, thứ tự duyệt và thread safety.
- [Java SE 25 — `List` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): hợp đồng `List.of`, `List.copyOf`, `null`, value-based instances và snapshot.
- [Java SE 25 — `Set` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html): quy tắc `of`/`copyOf`, phần tử trùng và thứ tự.
- [Java SE 25 — `Map` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): key/value, factory methods và unmodifiable maps.
- [Java SE 25 — `Collections` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html): `unmodifiableList` và các **read-only views**.
- [Java SE 25 — `Collectors` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): `toUnmodifiableList`/`Set`/`Map` và xử lý key trùng.
- [Java SE 25 — `Stream` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#toList()): `Stream.toList` từ Java 16.
- [Java SE 25 — `UnsupportedOperationException` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/UnsupportedOperationException.html): ngoại lệ khi thao tác không được hỗ trợ.

**Ghi nhớ:** `unmodifiable` nói về **những thao tác bị cấm trên collection**, `copyOf` tạo **snapshot của cấu trúc**, còn **immutable object** đòi trạng thái quan sát được không thể thay đổi qua bất kỳ tham chiếu còn được cấp phép nào. Phân biệt ba mức này giúp thiết kế API Java an toàn, dễ hiểu và dễ bảo trì.