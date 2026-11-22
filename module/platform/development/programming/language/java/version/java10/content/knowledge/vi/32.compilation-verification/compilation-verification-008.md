# Đánh giá thời gian sống tham chiếu trong for-each theo phạm vi sử dụng

*Chủ đề Java 10 — Biên dịch và kiểm chứng. Bài Knowledge tập trung vào biến phần tử trong vòng lặp **enhanced `for` / for-each**, đặc biệt cú pháp `for (var element : source)` được Java 10 hỗ trợ qua JEP 286. Mục tiêu là phân biệt **phạm vi tên biến trong mã nguồn (lexical scope)**, **thời gian còn cần giá trị tham chiếu để tính toán (liveness)**, **khả năng truy cập đối tượng bằng chuỗi tham chiếu mạnh (strong reachability)** và **thời điểm GC có thể thu hồi**. Các chương trình chính được biên dịch bằng Java 17 và kiểm thử trên HotSpot JDK 24; cơ chế còn áp dụng ở JDK hiện đại.*

## 1. Câu trả lời cốt lõi

Đoạn mã:

~~~java
for (var item : items) {
    process(item);
}
~~~

có một biến cục bộ `item` được **khai báo trong phần đầu vòng for-each**. Theo Java Language Specification (JLS `6.3 và `14.14.2), phạm vi của tên `item` là **statement thân vòng lặp**. Mỗi lượt duyệt gán cho biến phần tử của lượt ấy. Tên `item` **không còn dùng được sau vòng lặp**.

Nhưng có bốn khẳng định rất khác nhau:

1. **Tên biến hết scope:** không thể viết `System.out.println(item)` ở ngoài vòng lặp vì không còn định danh hợp lệ ở vị trí đó.
2. **Giá trị biến không còn được cần đến:** JVM/JIT có thể xác định một tham chiếu không cần cho việc tính toán tiếp theo ngay cả **trước khi kết thúc scope**.
3. **Đối tượng không còn strong references:** điều này phụ thuộc mọi đường tham chiếu từ các GC roots, không chỉ một biến `item`.
4. **Đối tượng đã được GC thu hồi:** không được suy ngay từ ba câu trên; thời điểm và quyết định thu gom thuộc JVM/GC.

**Nguyên tắc đúng:** scope của biến lặp là một đặc tính **biên dịch và khả năng truy cập theo tên**, **không** là bảo đảm “đối tượng sống đến hết dấu `}`” hoặc “GC thu hồi ngay khi sang vòng tiếp theo”.

Đặc biệt, nếu `items` là `List<Item>` hoặc mảng `Item[]` đang giữ các phần tử bằng tham chiếu mạnh, thì đối tượng vẫn có thể được truy cập qua cấu trúc chứa **dù biến `item` đã hết scope**.

## 2. Liên hệ Java 10: `var` trong enhanced for

JEP 286 của Java 10 cho phép suy luận kiểu biến cục bộ và biến phần tử trong enhanced for:

~~~java
List<String> names = List.of("Lan", "Minh");
for (var name : names) {
    System.out.println(name.toUpperCase());
}
~~~

Compiler biết kiểu của `names` là `List<String>`, vì vậy kiểu biên dịch của `name` là `String`. Chữ `var` không tạo kiểu động và cũng không tạo tham chiếu yếu.

Đây tương đương về **kiểu biến** với:

~~~java
for (String name : names) {
    System.out.println(name.toUpperCase());
}
~~~

`var` chỉ giúp lược bớt phần khai báo kiểu khi ngữ cảnh đủ rõ. Nó **không** sửa vòng đời đối tượng, chính sách GC, cách giữ tham chiếu của collection hay phạm vi hợp lệ của tên biến.

### 2.1. `var` là suy luận kiểu tại biên dịch

| Biểu thức sau dấu `:` | Kiểu biến suy luận thông thường | Hệ quả |
| --- | --- | --- |
| `List<String>` | `String` | Có thể gọi `String` methods |
| `List<Person>` | `Person` | Có thể truy cập API `Person` |
| `Iterable<? extends Number>` | Một kiểu thích hợp dựa trên phần tử và wildcard | Dùng an toàn như `Number` trong code minh họa |
| `List<?>` | Kiểu suy luận với upper bound thích hợp | Chỉ các thao tác cho phép trên kiểu đó |
| Raw `Iterable` | Thông thường là `Object` | Có thể cần kiểm tra/cast |
| `int[]` | `int` | Là biến primitive, **không có object reference** |
| `String[]` | `String` | Là biến tham chiếu tới phần tử mảng |

Đừng viết một bài giảng về “reference lifetime” rồi ngầm cho rằng `for (var n : intArray)` cũng là vòng đời tham chiếu. Với primitive array, giá trị phần tử được sao chép vào biến kiểu primitive và GC reachability của object không liên quan trực tiếp tới biến `n`.

### 2.2. `var` không cần initializer ở chính tên biến for-each

Với local-variable statement thông thường:

~~~java
var label = "done";
~~~

compiler suy luận kiểu từ initializer. Trong enhanced for:

~~~java
for (var label : labels) {
    System.out.println(label);
}
~~~

kiểu được suy từ **kiểu phần tử của mảng/Iterable** ở vế phải dấu `:`. Không viết thêm `= ...` sau `label`: cú pháp for-each không cho initializer riêng ở variable declarator như for thông thường.

### 2.3. `final var` có được không?

Có. Ví dụ:

~~~java
for (final var person : people) {
    person.setDisplayName("updated");
}
~~~

`final` cấm **gán lại biến `person`** trong thân vòng lặp, nhưng nếu đối tượng `Person` mutable thì code có thể đổi trạng thái của nó. `final` **không biến tham chiếu mạnh thành yếu** và **không biến đối tượng thành immutable**.

## 3. Scope của biến lặp: quy tắc JLS chính xác

JLS `6.3 quy định phạm vi của local variable khai báo ở header enhanced for là **contained Statement**. Trường hợp thân vòng lặp là block `{...}`, ta dùng biến bên trong block:

~~~java
for (var item : items) {
    System.out.println(item); // hợp lệ
}
~~~

Nhưng đoạn sau **không biên dịch**:

~~~java
for (var item : items) {
    System.out.println(item);
}
System.out.println(item); // lỗi: item không còn trong scope
~~~

Đây là đoạn **cố ý sai để minh họa scope**, không phải chương trình chạy độc lập. Thông báo diagnostic của `javac` thường thuộc nhóm `cannot find symbol` nhưng có thể khác theo bối cảnh và release.

### 3.1. Phân biệt với biến khai báo bên ngoài

~~~java
String last = null;
for (var element : List.of("A", "B")) {
    last = element;
}
System.out.println(last); // B
~~~

`last` khai báo **ngoài** vòng lặp, có scope dài hơn và nhận tham chiếu đến phần tử cuối. Việc `element` không tồn tại sau vòng lặp **không khiến đối tượng cuối vô hình**: `last` vẫn giữ tham chiếu.

Nếu cần duy trì một kết quả sau for-each, hãy khai báo **biến kết quả có chủ đích** ngoài loop hoặc trả về từ method. Tránh chuyển tất cả biến phần tử ra ngoài loop chỉ vì muốn truy cập tên sau đó.

### 3.2. Tên biến trong biểu thức nguồn

Không thể sử dụng tên `element` vừa khai báo ở header để tự định nghĩa iterable ở bên phải:

~~~java
for (var element : element) {
    // Không phải cách tham chiếu tới biến lặp đang khởi tạo.
}
~~~

JLS đặt scope của biến ở **contained Statement**, không bao trùm **Expression** phía sau dấu `:`. Nếu ngữ cảnh bên ngoài có một biến cũng tên `element`, việc tìm tên trong expression được xử lý theo luật scope/shadowing của ngữ cảnh ấy; đừng viết dạng khó đọc này.

### 3.3. Không thể khai báo lại cùng tên trong block thân

~~~java
for (var item : items) {
    var item = "another"; // lỗi biên dịch: trùng tên local variable
}
~~~

Đây là đoạn **cố ý sai**. Hãy dùng tên khác, hoặc một block/method riêng có phạm vi độc lập phù hợp. Khả năng tái sử dụng tên `item` ở **vòng for-each khác sau vòng đầu** là chuyện khác, vì các scope không chồng lên nhau.

### 3.4. `break`, `continue` và exception

Khi `break`, `return` hoặc exception làm rời vòng lặp, code không thể tiếp tục truy cập tên `item` ngoài scope. Điều đó vẫn **không** cam kết dọn tất cả objects ngay lúc rẽ nhánh: nguồn, iterator, các biến khác, closures và GC roots có thể còn giữ references.

## 4. Mỗi iteration nhận phần tử như thế nào?

Theo JLS `14.14.2, enhanced for được định nghĩa qua phép dịch tương đương sang for cơ bản. Có hai trường hợp quan trọng:

### 4.1. Với `Iterable<E>`: có iterator bên trong

~~~java
List<Item> items = ...;
for (var item : items) {
    use(item);
}
~~~

Ở mức ý nghĩa, tương ứng với cấu trúc kiểu:

~~~java
for (Iterator<Item> iterator = items.iterator();
     iterator.hasNext();) {
    Item item = iterator.next();
    use(item);
}
~~~

Đây là **minh họa phép dịch**. Tên `iterator` ở đoạn minh họa không nhất thiết xuất hiện trong source code thật; compiler có thể tạo biến ẩn và áp dụng ép kiểu/kiểm tra tương ứng theo JLS.

Các chi tiết quan trọng:

1. Biểu thức `items` được **đánh giá một lần** để tạo iterator, không được đánh giá lại tùy tiện ở mỗi vòng.
2. `iterator.hasNext()` và `iterator.next()` cung cấp các phần tử.
3. Ở mỗi lượt, biến `item` nhận phần tử vừa lấy.
4. Iterator hoặc collection backing nó **có thể giữ những references** mà chương trình vẫn cần.
5. Biến `item` không được dùng sau loop, nhưng `items`/iterator/các nơi khác có thể giữ element objects.

### 4.2. Với mảng: có chỉ số và mảng được lưu trong biến ẩn

~~~java
Item[] array = ...;
for (var item : array) {
    use(item);
}
~~~

Ở mức ý nghĩa tương ứng:

~~~java
Item[] storedArray = array;
for (int i = 0; i < storedArray.length; i++) {
    Item item = storedArray[i];
    use(item);
}
~~~

Nếu `array` là mảng object, mỗi `item` là **bản sao giá trị tham chiếu** ở ô mảng tương ứng (đều trỏ tới cùng object khi chưa đổi tham chiếu). Nếu `array` là mảng primitive, phần tử primitive được sao chép theo giá trị.

Phép dịch này giúp hiểu vì sao gán lại biến `item` **không** sửa slot mảng ban đầu.

### 4.3. Mảng và Iterable có cơ chế giữ phần tử khác nhau

| Cấu trúc nguồn | Cách lấy phần tử | Tham chiếu còn ở đâu ngoài biến `item`? |
| --- | --- | --- |
| `List<Item>` | `Iterator<Item>` | Danh sách backing, các alias/copy/snapshot, iterator tùy implementation |
| `Set<Item>` | Iterator của Set | Tập và các references khác |
| `Map<K,V>.entrySet()` | Iterator qua entries | Map/backing entries, keys/values |
| `Item[]` | Mảng + index | Chính các slot mảng |
| `int[]` | Mảng + index | Không có reference ở biến lặp primitive |
| Custom `Iterable<Item>` | Iterator do implementation cung cấp | Phụ thuộc implementation của Iterator/Iterable |

**Cần tránh suy luận quá mức:** việc có một iterator không có nghĩa mọi implementation luôn giữ toàn bộ collection bằng cùng một cấu trúc. Cần xem implementation thực. Nhưng loại bỏ biến `item` **không đủ** để chứng minh phần tử đã trở nên unreachable.

## 5. Gán lại reference và sửa đối tượng là hai thao tác khác nhau

Xét:

~~~java
class Item {
    String name;
    Item(String name) { this.name = name; }
}

List<Item> items = new ArrayList<>();
items.add(new Item("A"));
items.add(new Item("B"));

for (var item : items) {
    if ("B".equals(item.name)) {
        item = new Item("TEMP");
    }
}
~~~

Sau loop, phần tử thứ hai trong `items` **vẫn là object có `name="B"`**. Vì sao? Biến `item` chỉ giữ một giá trị tham chiếu cục bộ. Câu `item = new Item(...)` gán cho biến đó một tham chiếu **khác**, không thay slot trong List.

Trong code tương tự với mảng object:

~~~java
for (var item : array) {
    item = new Item("TEMP");
}
~~~

cũng không đổi tham chiếu chứa ở `array[i]`.

Ngược lại:

~~~java
for (var item : items) {
    if ("B".equals(item.name)) {
        item.name = "B*";
    }
}
~~~

làm thay đổi trạng thái của **object được List tham chiếu**, vì `item.name` ghi trực tiếp vào object cùng identity.

### 5.1. Bảng dự đoán thay đổi

| Thao tác trong for-each | Có đổi phần tử trong collection? | Giải thích |
| --- | --- | --- |
| `item = new Item("X")` | **Không** | Chỉ gán lại local alias |
| `item = null` | **Không** | Không xóa slot List/array |
| `item.name = "X"` | **Có thể thấy** nếu object mutable | Cùng object được nhiều tham chiếu trỏ tới |
| `item.setValue("X")` | **Có thể thấy** nếu method đổi object | Method có tác dụng trên instance |
| `array[index] = new Item("X")` | **Có** | Ghi trực tiếp slot mảng khi có index hợp lệ |
| `list.set(index, new Item("X"))` | **Có** | Dùng API List để thay element |
| `list.removeIf(predicate)` | **Có** trên mutable collection phù hợp | Thay cấu trúc collection qua API |
| `list.clear()` sau loop | **Có** | Xóa references do List lưu giữ, nhưng không xóa references khác |

Trường hợp collection immutable/unmodifiable hoặc array read-only qua API khác phải đánh giá theo contract cụ thể. `List.copyOf` tạo danh sách **không cho sửa cấu trúc**, nhưng vẫn giữ references đến các object (shallow copy), không deep clone objects.

### 5.2. Đánh giá vòng đời sau một phép gán lại

Nếu `item = null` trong thân loop, có thể làm giá trị mà **local alias** đang giữ không còn trỏ object đó. Nhưng object có thể vẫn được List, array, iterator, callback hoặc field giữ. **Không thể dùng `item=null` như bảo đảm thu hồi object hay cắt memory leak.**

## 6. Ba thuật ngữ cần luôn phân biệt

### 6.1. Lexical scope — phạm vi của tên

JLS `6.3 trả lời: “Ở vị trí nào trong source code, tên `item` có thể được dùng để tham chiếu tới local variable?”. Với for-each, là **contained Statement**.

Đây là quy tắc **biên dịch**, được kiểm tra ngay cả khi chương trình chưa chạy.

### 6.2. Liveness — giá trị còn cần cho phần tính toán tiếp theo?

Một compiler/JIT có thể biết rằng một local reference đã có **last use**, dù source scope vẫn tiếp tục. Liveness của giá trị và hình thái bytecode local slot/JIT register có thể khác cách người đọc tưởng tượng từ dấu `{ }`.

Ví dụ:

~~~java
for (var item : items) {
    use(item);
    expensiveCalculationThatDoesNotUse(item);
}
~~~

Nếu `expensiveCalculationThatDoesNotUse` thực sự không cần tham chiếu `item`, VM được phép tối ưu theo ngữ nghĩa Java. **Không nên tự động suy item được giữ mạnh đến hết method chỉ vì tên vẫn hợp lệ về mặt scope**.

Ngược lại, liveness của biến `items`, iterator, array hoặc các captures có thể kéo dài hơn phần thân một iteration.

### 6.3. Reachability — đối tượng vẫn có đường tham chiếu mạnh?

Một object được coi là **strongly reachable** khi còn có thể tiếp cận từ các roots bằng chuỗi references mạnh phù hợp, không cần đi qua referent của `SoftReference`/`WeakReference`/`PhantomReference`.

GC roots có thể gồm những references trong stack/thread state, static fields, JNI handles và các roots mà VM quản lý. Hệ quy chiếu chính xác phụ thuộc runtime và collector. Mỗi object có thể được giữ bởi **nhiều đường**:

~~~text
GC roots
   ├─ main thread → List<Item> items → Item B
   ├─ main thread → List<Item> snapshot → Item B
   ├─ main thread → lambda/Supplier → Item B
   └─ static cache → Item B
~~~

Khi local `item` hết scope, các đường khác vẫn có thể tồn tại.

### 6.4. Reclamation — khi nào GC thật sự dọn?

Đối tượng không còn cần và có thể được thu gom **không đồng nghĩa** JVM sẽ thu gom ngay lập tức. JVM có thể trì hoãn GC; cũng có thể không chạy GC trước khi tiến trình kết thúc. `System.gc()` chỉ là một yêu cầu/nỗ lực theo API, không phải cam kết dọn một object cụ thể.

**Không viết test như sau:**

~~~java
WeakReference<Item> ref = ...;
System.gc();
assert ref.get() == null; // kiểm thử sai: GC không bảo đảm đúng ngay
~~~

Đoạn là ví dụ **cố ý không nên dùng**: có thể fail ngẫu nhiên giữa JVMs, GC algorithms và thời điểm thực thi. Test reference lifetime nên ưu tiên xác minh **đồ thị tham chiếu/ownership** và các hành vi xác định được; dùng heap profiling nếu cần kiểm chứng memory retention.

## 7. Khi nào biến for-each có thể “thoát” khỏi iteration?

Bản thân tên biến lặp không thoát scope, nhưng **giá trị tham chiếu mà nó đang giữ có thể được lưu ra ngoài**.

### 7.1. Lưu vào collection khác

~~~java
List<Item> selected = new ArrayList<>();
for (var item : items) {
    if (isImportant(item)) {
        selected.add(item);
    }
}
~~~

Đây là đoạn logic trong method, với `isImportant` là method của ứng dụng. `selected` giữ những references được thêm vào. Ngay cả khi `items.clear()`, các object trong `selected` vẫn được giữ.

Nếu muốn snapshot **giá trị** không giữ object gốc, hãy sao chép dữ liệu cần dùng sang DTO/record immutable khi thích hợp, thay vì chỉ sao chép references.

### 7.2. Capture qua lambda

~~~java
List<Supplier<String>> callbacks = new ArrayList<>();
for (var item : items) {
    callbacks.add(() -> item.name());
}
~~~

Mỗi lambda có thể giữ tham chiếu đến `item` của iteration tương ứng nếu được capture. Sau khi loop kết thúc, callback còn được lưu trong `callbacks` và có thể truy cập object mà nó tham chiếu.

**Quan trọng:** biến `item` dùng trong lambda phải là `final` hoặc **effectively final**. Việc vòng lặp chuyển sang phần tử khác ở iteration tiếp theo **không làm vi phạm** điều này; mỗi iteration được mô tả bằng một local variable được khởi tạo riêng về mặt ngữ nghĩa.

### 7.3. Capture bị lỗi nếu biến bị gán lại

Đoạn này **không biên dịch**:

~~~java
for (var item : items) {
    Runnable action = () -> System.out.println(item);
    item = anotherItem; // item không còn effectively final
}
~~~

Java không cho lambda capture một local variable bị reassign theo quy tắc effectively final. Đây không phải cơ chế “giữ object an toàn cho GC”; nó là quy tắc biên dịch giúp capture ổn định.

Sửa bằng cách **không gán lại** biến được capture, hoặc tạo một biến snapshot có ý nghĩa rõ:

~~~java
for (var item : items) {
    var selected = item;
    Runnable action = () -> System.out.println(selected);
    enqueue(action);
}
~~~

`enqueue` ở đây là method do ứng dụng cung cấp, chưa định nghĩa trong đoạn nên **không phải chương trình độc lập**. `selected` vẫn giữ **cùng object reference**, không deep copy.

### 7.4. Async tasks có thể kéo dài vòng đời object

~~~java
for (var item : items) {
    executor.submit(() -> process(item));
}
~~~

Đây là đoạn minh họa với `executor` và `process` do ứng dụng định nghĩa. Executor giữ task cho đến khi xử lý; task có thể capture `item` và kéo dài mạnh tham chiếu **sau khi for-each đã kết thúc**. Với queue backlog lớn, lượng object retained có thể rất cao.

Các hành động phù hợp:

- Giới hạn queue/task concurrency và áp dụng backpressure.
- Không truyền cả object graph lớn khi chỉ cần một ID hoặc các trường nhỏ.
- Không để `Future`, callback hoặc completed task list tồn tại vô hạn.
- Quản lý shutdown/cancel và lifecycle theo contract của Executor.
- Nếu object là resource cần đóng, định nghĩa ownership và việc đóng sau khi task hoàn thành.

**Không** coi việc khép `}` của for-each là cơ chế giải phóng native resources cho async tasks.

### 7.5. Method return và static field cũng có thể tạo escape

~~~java
for (var item : items) {
    cache.put(item.id(), item);
}
~~~

`cache` có thể giữ object lâu hơn cả method. Tương tự, nếu method trả về `item` hay đưa vào field của một object dài hạn, thời gian tham chiếu sẽ theo **container/owner đó**, không theo scope tên ban đầu.

## 8. Source collection vẫn giữ object sau vòng lặp

Nhiều ví dụ sai về memory leak chỉ nhìn:

~~~java
for (var item : largeList) {
    consume(item);
}
~~~

rồi nói “GC sẽ giải phóng mỗi item sau mỗi iteration”. Đây là lời hứa **không chính xác** khi `largeList` vẫn giữ references đến toàn bộ items.

Mặc dù `item` của iteration trước không còn được dùng theo tên ở iteration sau, `largeList` vẫn tham chiếu đến mọi element (trừ khi collection/producer tự thay đổi).

### 8.1. `List.clear` và ownership

~~~java
List<Item> items = loadBatch();
try {
    for (var item : items) {
        consume(item);
    }
} finally {
    items.clear();
}
~~~

Đây là đoạn trong method với `loadBatch`/`consume` là API ứng dụng. Nếu `items` là mutable List và ứng dụng đã xử lý xong, `clear()` bỏ references mà List đang giữ. Nhưng:

- References đã được capture trong callbacks còn tồn tại.
- Một `List.copyOf(items)` tạo trước đó vẫn giữ elements.
- Field/static cache khác vẫn có thể giữ objects.
- Iterator hoặc thread khác có thể vẫn giữ references tùy implementation.
- Chỉ vì clear không có nghĩa GC ngay lập tức dọn mọi Item.

Không gọi `clear` bừa bãi trên collection được **shared** giữa thread hoặc được module khác sở hữu. Cần đánh giá ownership và synchronization; với collection không cho sửa, `clear` ném exception.

### 8.2. `List.copyOf` không deep copy

~~~java
List<Item> snapshot = List.copyOf(items);
~~~

Phương thức này tồn tại từ Java 10. Nó tạo danh sách **unmodifiable** chứa các element references, không clone trạng thái sâu của từng Item.

Nếu `item.setName("changed")`, cả `items` và `snapshot` có thể thấy object đã đổi. Nếu `items.clear()`, `snapshot` vẫn giữ tham chiếu tới các objects mà nó chứa.

Đừng chọn `List.copyOf` như giải pháp tự động rút ngắn lifetime của elements; nó có thể **kéo dài** lifetime nếu snapshot được lưu lâu.

### 8.3. `Stream.toList` cũng có thể giữ references

~~~java
var selected = items.stream().filter(this::important).toList();
~~~

`Stream.toList()` từ Java 16 tạo list unmodifiable theo contract, nhưng các phần tử là references của objects đã được chọn; nó không deep copy object graph. Biến `selected` có thể giữ objects sau loop ban đầu.

`this::important` minh họa method instance của ứng dụng; không phải chương trình độc lập.

## 9. Mảng: thay slot khác sửa object

Mảng object:

~~~java
StringBuilder[] builders = {
        new StringBuilder("X"), new StringBuilder("Y")
};
for (var builder : builders) {
    builder = new StringBuilder("OTHER");
}
~~~

Sau loop:

~~~text
[X, Y]
~~~

Bởi `builder` chỉ là local variable được gán lại.

Nhưng:

~~~java
for (var builder : builders) {
    builder.append("!");
}
~~~

sau đó kết quả:

~~~text
[X!, Y!]
~~~

vì object `StringBuilder` cũ đã thay đổi.

Muốn **thay phần tử mảng**, phải ghi vào slot theo index, ví dụ:

~~~java
for (int i = 0; i < builders.length; i++) {
    builders[i] = new StringBuilder("new-" + i);
}
~~~

**Memory caveat:** khi thay slot, reference cũ có thể không còn trong mảng; nhưng nó vẫn có thể được giữ ở nơi khác. Không suy GC tức thì.

### 9.1. Mảng primitive

~~~java
int[] numbers = {1, 2, 3};
for (var number : numbers) {
    number = 99;
}
~~~

Kết quả `Arrays.toString(numbers)` là:

~~~text
[1, 2, 3]
~~~

vì `number` là bản sao giá trị `int`, không phải reference tới một ô mảng có thể thay bằng phép gán vào biến.

### 9.2. Phần tử `null`

Với `List<String>` cho phép `null`, biến for-each `var element` có kiểu `String` nhưng giá trị runtime có thể là `null`:

~~~java
for (var element : nullableList) {
    if (element != null) {
        System.out.println(element.length());
    }
}
~~~

Đừng nhầm “var cần initializer không-null trong local statement thông thường” với việc biến for-each không thể mang giá trị `null`. Java `var` suy luận kiểu **tại compile time** dựa trên collection element type, còn phần tử runtime có thể là `null` nếu loại collection cho phép.

Nếu **chính biểu thức source** là `null`, for-each không có iterable/array để duyệt và thường gây `NullPointerException` khi bắt đầu loop; đây là lỗi nguồn, không phải phần tử null hợp lệ.

## 10. Chương trình hoàn chỉnh: biến lặp, bản sao tham chiếu và resource scope

Ví dụ này biên dịch bằng Java 17, chạy trên Java 17+, chỉ dùng Java SE và cố ý tránh assertions phụ thuộc timing của GC.

### 10.1. File `ForEachReferenceLifetimeDemo.java`

~~~java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public final class ForEachReferenceLifetimeDemo {
    static final class Item {
        private String name;

        Item(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        void rename(String changed) {
            name = changed;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    static final class TrackedResource implements AutoCloseable {
        private final String name;
        private final List<String> events;

        TrackedResource(String name, List<String> events) {
            this.name = name;
            this.events = events;
            events.add("open-" + name);
        }

        void use() {
            events.add("use-" + name);
        }

        @Override
        public void close() {
            events.add("close-" + name);
        }
    }

    static List<WeakReference<Item>> buildWeakReferences() {
        var values = new ArrayList<Item>();
        values.add(new Item("temporary-1"));
        values.add(new Item("temporary-2"));

        var refs = new ArrayList<WeakReference<Item>>();
        for (var item : values) {
            refs.add(new WeakReference<>(item));
        }
        values.clear();
        return refs;
    }

    public static void main(String[] args) {
        var items = new ArrayList<>(
                List.of(new Item("A"), new Item("B"), new Item("C")));

        // (1) Rebind local alias: KHÔNG sửa slot List.
        for (var item : items) {
            if ("B".equals(item.name())) {
                item = new Item("TEMP");
            }
        }
        System.out.println("list after alias rebinding = " + items);

        // (2) final var cấm rebind nhưng cho phép đổi object mutable.
        for (final var item : items) {
            if ("B".equals(item.name())) {
                item.rename("B*");
            }
        }
        System.out.println("list after object mutation = " + items);

        // (3) Các owner khác giữ cùng object references.
        var snapshot = List.copyOf(items);
        var tasks = new ArrayList<Supplier<String>>();
        for (var item : items) {
            tasks.add(() -> item.name());
        }

        items.clear();
        System.out.println("source size after clear = " + items.size());
        System.out.println("snapshot still sees = " + snapshot);
        System.out.println("closures still see = "
                + tasks.stream().map(Supplier::get).toList());

        // (4) Biểu thức Iterable tạo iterator một lần cho một loop.
        var calls = new AtomicInteger();
        Iterable<String> values = () -> {
            calls.incrementAndGet();
            return List.of("x", "y").iterator();
        };
        var visited = new ArrayList<String>();
        for (var text : values) {
            visited.add(text);
        }
        System.out.println("iterable visited = " + visited);
        System.out.println("iterator() calls = " + calls.get());

        // (5) Rebind trên array khác với mutate element object.
        StringBuilder[] array = {
                new StringBuilder("X"), new StringBuilder("Y")
        };
        for (var value : array) {
            if (value.toString().equals("X")) {
                value = new StringBuilder("OTHER");
            }
        }
        System.out.println("array after rebinding = "
                + Arrays.toString(array));
        for (var value : array) {
            value.append("!");
        }
        System.out.println("array after mutation = "
                + Arrays.toString(array));

        // (6) Primitive values được sao chép.
        int[] numbers = {1, 2, 3};
        for (var value : numbers) {
            value = 99;
        }
        System.out.println("primitive array after loop = "
                + Arrays.toString(numbers));

        // (7) Resource được đóng deterministically từng iteration.
        var events = new ArrayList<String>();
        for (var id : List.of("r1", "r2")) {
            try (var resource = new TrackedResource(id, events)) {
                resource.use();
            }
        }
        System.out.println("resources = " + events);

        // (8) Weak refs được tạo, KHÔNG assert thời điểm GC.
        var weak = buildWeakReferences();
        System.out.println("weak references created = " + weak.size());

        // Đảm bảo snapshot còn strongly reachable tới đây nếu cần.
        Reference.reachabilityFence(snapshot);
        System.out.println("completed = true");
    }
}
~~~

### 10.2. Biên dịch và chạy

~~~bash
javac --release 17 ForEachReferenceLifetimeDemo.java
java ForEachReferenceLifetimeDemo
~~~

Nếu dùng file `.java` ở một thư mục khác, hãy điều chỉnh `-cp` tương ứng. Chương trình không yêu cầu library/JVM flags đặc biệt. `Stream.toList()` dùng trong demo có sẵn ở Java 17.

### 10.3. Stdout chính xác từ lượt kiểm thử trên HotSpot JDK 24

~~~text
list after alias rebinding = [A, B, C]
list after object mutation = [A, B*, C]
source size after clear = 0
snapshot still sees = [A, B*, C]
closures still see = [A, B*, C]
iterable visited = [x, y]
iterator() calls = 1
array after rebinding = [X, Y]
array after mutation = [X!, Y!]
primitive array after loop = [1, 2, 3]
resources = [open-r1, use-r1, close-r1, open-r2, use-r2, close-r2]
weak references created = 2
completed = true
~~~

Những dòng này cố tình **không báo GC đã thu hồi** bất kỳ object nào, vì đó là trạng thái không xác định theo thời gian nếu không có cơ chế đồng bộ/đảm bảo riêng.

### 10.4. Ý nghĩa từng nhóm kết quả

**Gán lại alias:** sau `item = new Item("TEMP")`, List vẫn là `[A, B, C]`. Không có `list.set(...)`, vì vậy object cũ vẫn được list giữ.

**Sửa trạng thái object:** `final var item` vẫn gọi `rename("B*")` trên object B; List cho thấy `[A, B*, C]`. `final` áp dụng cho biến, không phải mọi field của object.

**Snapshot và closures:** `items.clear()` đưa source size về 0, nhưng `snapshot` và các `Supplier` giữ tham chiếu đến ba Item; do đó vẫn xem được `[A, B*, C]`. Đây là bằng chứng có thể lặp lại về **references còn giữ**, không cần chờ GC.

**Iterable:** `iterator() calls = 1` xác nhận implementation của Iterable được hỏi một lần trong run mẫu. JLS `14.14.2` xác định phép dịch qua iterator.

**Arrays:** local rebind không sửa slot; gọi method của object thay đổi object mà slot trỏ tới.

**Resource:** có cặp `open/use/close` tương ứng từng iteration vì `try-with-resources`. Không phải do end-of-scope tự đóng tài nguyên.

**Weak references:** tạo 2 weak refs, nhưng không giả định chúng bị clear vào thời điểm nào.

**Reachability fence:** `Reference.reachabilityFence(snapshot)` đảm bảo snapshot vẫn mạnh tới điểm đó, khi đúng nhu cầu ngữ nghĩa cần giữ object cho xử lý resource. Không dùng nó như cơ chế thu hồi memory.

## 11. Xem bytecode để hiểu iterator và mảng

Bên cạnh compile/run, ta có thể dùng:

~~~bash
javap -c -p ForEachReferenceLifetimeDemo
~~~

Trong bản `javac --release 17` đã kiểm thử, phần bytecode tương ứng có các instruction/call liên quan tới:

~~~text
java/util/Iterator.hasNext
java/util/Iterator.next
arraylength
java/lang/ref/Reference.reachabilityFence
~~~

**Điều này có nghĩa:**

- Đường duyệt `Iterable` có các lời gọi Iterator.
- Đường duyệt mảng sử dụng chiều dài mảng và index.
- `reachabilityFence` xuất hiện khi đã gọi rõ trong source.

Đừng lấy số local slot, line offset hoặc tên synthetic variable do một phiên bản compiler tạo ra để định nghĩa hợp đồng sống của object. JVM/JIT có thể tái sử dụng slot, inline method và tối ưu register/stack liveness khác với bytecode.

### 11.1. Phân biệt bytecode local slot và object identity

Một slot có thể chứa các references khác nhau qua iterations. Điều đó **không** đồng nghĩa các Item khác nhau trở thành “cùng một object”, cũng không đồng nghĩa slot ấy là GC root mạnh cho mọi bước chạy về sau.

Các lớp phân tích:

~~~text
Java source lexical scope
       ↓ javac
bytecode / local variable slots / stack maps
       ↓ runtime/JIT
liveness/reachability được collector và optimized code sử dụng
       ↓
điều kiện GC có thể reclaim objects khi không còn reachable
~~~

Từng lớp có quy tắc và vai trò riêng; tránh suy một cách máy móc từ một tầng sang tầng khác.

### 11.2. LocalVariableTable có thể không xuất hiện đầy đủ

Thông tin debug như `LocalVariableTable` phụ thuộc compiler flags và class file. Việc debugger có thể hiển thị hoặc không hiển thị một local variable ở một điểm dừng không phải bằng chứng object đã được thu hồi hoặc còn strongly reachable.

**Đừng** đặt invariant sản phẩm dựa trên vị trí bytecode/local slot của một bản HotSpot cụ thể.

## 12. GC reachability và tối ưu JIT: tại sao cuối dấu `}` không phải đồng hồ

Theo JLS `12.6.1, compiler/JVM được phép áp dụng các tối ưu khiến số object còn reachable **ít hơn trực giác nhìn source** trong giới hạn được chuẩn cho phép. Chẳng hạn local variable không còn được sử dụng có thể được coi là không còn giữ object dù block chứa nó chưa kết thúc.

Ví dụ:

~~~java
void handle(Item item) {
    long code = item.id();
    doWorkUsingOnly(code);
}
~~~

`handle` ở đây là minh họa trong một class có `Item.id()`, `doWorkUsingOnly` chưa định nghĩa, **không phải chương trình độc lập**. Nếu JVM không còn cần object `item` sau khi lấy `code`, optimizer có thể thay đổi thời gian strong reachability phù hợp luật Java. Nhưng nếu `item` được giữ trong list/static field hoặc captured task khác, object còn có thể reachable.

### 12.1. Điều gì làm object “không thể GC” trong một thời điểm?

Không thể kết luận chỉ từ lexical scope. Hãy xem **đồ thị GC roots** và việc object còn cần cho các hành động tiếp theo.

Ví dụ:

~~~text
Root 1:  appController → cachedList → Item B
Root 2:  taskQueue → Runnable capture → Item B
Root 3:  pendingResult → ResultDTO → Item B

Kết thúc một iteration:
  local item B không còn được dùng → vẫn còn Root 1/2/3.
~~~

Đến khi những đường này không còn, object mới có thể trở nên eligible. Sự thu hồi vật lý vẫn theo lịch GC.

### 12.2. Trường hợp đặc biệt: native handles/`Cleaner`

Có những tình huống resource được cleanup khi Java object không còn reachable, nhưng native operation vẫn cần resource sống cho tới một điểm. JIT có thể xác định object không còn cần sớm hơn ý định của người lập trình.

Java cung cấp:

~~~java
Reference.reachabilityFence(resource);
~~~

để **đảm bảo `resource` strongly reachable ít nhất đến sau invocation đó**. Đây là API được đưa vào từ Java 9 và còn hoạt động trên JDK 17+.

Dùng `reachabilityFence` có ý nghĩa khi **liveness object ảnh hưởng tới resource cleanup** (ví dụ `Cleaner`/native handle), không phải lựa chọn mặc định cho mọi vòng lặp. Nếu quản lý resource qua `AutoCloseable`/`try-with-resources` đúng cách, cơ chế đóng tường minh thường dễ hiểu hơn.

### 12.3. `reachabilityFence` không ép GC

API `Reference.reachabilityFence(x)`:

- Kéo dài strong reachability của `x` đến sau điểm gọi.
- **Không** trigger garbage collection.
- **Không** tự đóng stream/socket/direct buffer.
- **Không** giải quyết references bị lưu lâu ngoài ý muốn trong cache.
- Không thay thế ownership/lifecycle của resource.

Cũng không nên gọi `reachabilityFence(null)` để “dọn” gì đó: tài liệu xác nhận với `null` phương thức không có tác dụng.

### 12.4. Tránh giải pháp dựa vào finalization

Các mẫu trông chờ `Object.finalize()` chạy đúng lúc là di sản **đã bị deprecated for removal** trên Java hiện đại. Không dùng finalizer làm chủ sở hữu tài nguyên trong bài tập về lifetime. Ưu tiên `AutoCloseable`, `try-with-resources`, và `Cleaner` chỉ khi phù hợp với thư viện/native resource, tuân thủ các hợp đồng reachability.

## 13. Thời gian sống resource không nên phụ thuộc biến lặp

### 13.1. Sai: chỉ dựa vào dấu `}`

~~~java
for (var stream : streams) {
    process(stream);
} // Không bảo đảm stream đã được close!
~~~

Đây là đoạn logic với `streams`/`process` thuộc ứng dụng, không phải chương trình độc lập. `stream` ra khỏi lexical scope **không gọi `stream.close()`**. Tài nguyên file descriptor/socket có thể bị giữ lâu nếu không có owner đóng.

### 13.2. Đúng: xác định ownership và đóng tường minh

Một pattern khi **vòng lặp tạo resource riêng cho mỗi iteration**:

~~~java
for (var path : paths) {
    try (var input = Files.newInputStream(path)) {
        consume(input);
    }
}
~~~

Đây là đoạn bên trong method, cần `import java.nio.file.Files`, biến `paths` và hàm `consume`. Mỗi `input` đóng **khi rời try block**, bao gồm đường exception theo semantics try-with-resources.

Nếu vòng lặp duyệt **danh sách resource đã được tạo từ trước**, phải xác định liệu loop có **sở hữu quyền đóng** từng resource hay không. Không tự đóng resource do caller chia sẻ chỉ vì bạn thấy nó trong for-each.

### 13.3. Asynchronous use phải giữ resource tới khi task hoàn tất

~~~java
for (var task : tasks) {
    executor.submit(() -> task.run());
}
~~~

Nếu task tham chiếu resource sẽ được đóng ở vòng lặp ngoài, cần bảo đảm lifecycle phù hợp. **Không** đóng resource khi tác vụ còn đang dùng nó, và cũng không giữ toàn bộ task/resource trong một queue không giới hạn.

Một kiến trúc tốt có thể:

- Để task tự sở hữu và đóng resource trong `try-with-resources`.
- Hoặc bảo vệ resource shared bằng cơ chế reference counting/lifecycle đã được thiết kế.
- Hoặc chờ các `Future` hoàn tất và đóng ở đúng điểm bảo đảm.

Chọn theo contract, không theo việc biến `task` có scope ngắn.

## 14. Memory retention do dữ liệu lớn: chiến lược đúng

### 14.1. Đọc toàn bộ dữ liệu rồi for-each

~~~java
var records = Files.readAllLines(path);
for (var record : records) {
    consume(record);
}
~~~

Đây là đoạn trong method; `path` và `consume` phải được định nghĩa. `Files.readAllLines` đưa **toàn bộ dữ liệu** vào List trước khi duyệt. Dù `record` chỉ sống trong source body, `records` vẫn giữ tất cả strings cho tới khi List không còn giữ chúng.

Với file lớn, vấn đề bộ nhớ có thể nằm ở **cấu trúc load-all**, không phải tên `record`.

### 14.2. Đọc từng dòng với stream và try-with-resources

~~~java
try (var lines = Files.lines(path)) {
    lines.forEach(this::consume);
}
~~~

Đây là đoạn ở instance method với `path` và `consume` hợp lệ. `Files.lines` trả về stream chứa resource I/O, nên cần đóng stream qua try-with-resources. Tuy nhiên, `Stream.forEach` **không phải enhanced-for syntax** và có semantics riêng (có thể khác về parallelism/order), không dùng nó làm bằng chứng scope của `for (var x : iterable)`.

Nếu cần loop syntax duyệt từ reader:

~~~java
try (var reader = Files.newBufferedReader(path)) {
    String line;
    while ((line = reader.readLine()) != null) {
        consume(line);
    }
}
~~~

Đoạn này không tự giữ toàn bộ file dưới dạng List, nhưng `consume`/cache có thể vẫn làm dữ liệu bị retained.

### 14.3. Producer/iterator lazy cũng có thể giữ references

Một custom `Iterable` có thể sinh phần tử theo nhu cầu thay vì giữ mọi phần tử trong List. Nhưng cần kiểm tra:

- Iterator có prefetch/buffer không?
- Nó có giữ resource/connection đến hết iteration không?
- Có cần đóng resource khi thoát do `break`/exception không?
- Các callbacks/task queues có giữ phần tử không?
- Có phát sinh object graph lớn mỗi iteration không?

**Không** nói “Iterable luôn memory O(1)”: `Iterable` chỉ quy định khả năng cung cấp iterator, không ràng buộc dung lượng backing structure hoặc resource lifecycle.

### 14.4. Thay đổi nguồn trong lúc duyệt

Với một mutable `ArrayList`, làm:

~~~java
for (var item : items) {
    items.remove(item); // tránh: sửa cấu trúc trong khi Iterator đang duyệt
}
~~~

có thể gây `ConcurrentModificationException` hoặc hành vi không đáng dựa vào; fail-fast detection chỉ là **best effort** theo collection contract. Nếu cần xóa phần tử dựa vào predicate, dùng:

~~~java
items.removeIf(item -> shouldRemove(item));
~~~

hoặc explicit `Iterator.remove()` khi iterator của collection hỗ trợ. `shouldRemove` thuộc ứng dụng; các ví dụ là đoạn logic, không phải file biên dịch độc lập.

Với concurrent collections, iterator có thể có semantics yếu nhất quán hoặc snapshot khác, cần đọc contract của collection cụ thể.

## 15. Cách thử và đo “lifetime” mà không viết test GC mong manh

### 15.1. Bắt đầu từ điều chắc chắn ở compile time

Viết một chương trình `javac --release 17` kiểm tra:

- `for (var item : items)` được chấp nhận.
- `for (final var item : items)` được chấp nhận.
- `item` ngoài statement thân vòng lặp bị từ chối theo JLS.
- Capture trong lambda hợp lệ khi `item` effectively final.
- Capture + reassign `item` không hợp lệ.
- Gán lại `item` không sửa List/array.

Đây là các **thuộc tính ngôn ngữ** đáng kiểm chứng bằng compiler.

### 15.2. Kiểm tra identity và dữ liệu, không đoán GC

Thay vì dự đoán khi nào object chết, ta có thể kiểm:

~~~java
var item = new Item("A");
var list = new ArrayList<Item>();
list.add(item);

for (var current : list) {
    assert current == item;
}
~~~

Đây là đoạn trong method và class `Item` tương ứng; phép `==` trên object refs kiểm **cùng identity**. Để kiểm thử tại runtime không phụ thuộc cờ `-ea`, có thể dùng điều kiện if + `AssertionError` hoặc test framework.

Dù sau đó `list.clear()`, biến `item` bên ngoài vẫn giữ strong reference. **Không** đoán GC dựa trên mỗi `list.size()`.

### 15.3. WeakReference dùng để quan sát, không thay đảm bảo lifecycle

~~~java
WeakReference<Item> weak = new WeakReference<>(item);
~~~

Nếu object chỉ còn weakly reachable, collector **có thể** clear referent trong quá trình xử lý GC theo contract. Nhưng:

- `weak.get() != null` ở một thời điểm không chứng minh object sẽ sống lâu.
- `weak.get() == null` nói referent đã bị clear, không nói chính xác thời gian object “ra khỏi scope”.
- Nếu vẫn có List/snapshot/lambda giữ mạnh, referent có thể tiếp tục được giữ.
- Không thể dùng `System.gc()` làm đồng hồ đảm bảo clear weak ref sau một số milliseconds.
- Reference objects và queue bản thân chúng cũng cần được giữ reachable để ứng dụng quan sát events.

Trong production, `WeakReference`/`ReferenceQueue` có use cases rõ như caches/metadata; không dùng chúng thay cho việc giới hạn cache, đóng tài nguyên hoặc quản lý ownership.

### 15.4. Dùng heap dump và profiler khi có leak thật

Nếu ứng dụng tăng bộ nhớ sau mỗi batch, các câu hỏi hữu ích:

1. Những object nào retained sau khi batch hoàn tất?
2. Dominator nào giữ chúng: List, static Map, async queue, ThreadLocal, listener, stream?
3. Có references từ `List.copyOf`/closures/Futures không?
4. Bản thân source collection còn giữ data không?
5. Có resource native chưa đóng dù object heap nhỏ không?

Dùng JFR, heap dump/histogram hoặc profiler phù hợp với môi trường. Đừng ép `System.gc()` trong request path như một cách “giải phóng reference sau for-each”.

## 16. Các trường hợp biên về phạm vi

### 16.1. Vòng lặp lồng nhau

~~~java
for (var outer : groups) {
    for (var inner : outer) {
        use(inner);
    }
}
~~~

Tên `inner` chỉ trong thân vòng trong, `outer` chỉ trong thân vòng ngoài. Liveness của group/iterator/element vẫn phụ thuộc object graph. Chỉ có thêm dấu ngoặc không tạo deep-freeze hay auto-GC.

### 16.2. Cùng tên ở hai vòng loop nối tiếp

~~~java
for (var item : firstList) {
    use(item);
}
for (var item : secondList) {
    use(item);
}
~~~

Hợp lệ khi tên `item` trong hai contained statements không chồng scope. Compiler có thể tái sử dụng slot trong bytecode, nhưng điều đó không ảnh hưởng object identity hoặc quyền sở hữu của hai Lists.

### 16.3. `final var` trong loop

~~~java
for (final var item : items) {
    use(item);
}
~~~

Mỗi iteration nhận một giá trị được gán khi khai báo, sau đó biến ấy không được gán lại trong body. `final` không khiến collection immutable. Nếu `use(item)` sửa object, những nơi khác có cùng object ref vẫn thấy kết quả theo quy tắc memory model/concurrency tương ứng.

### 16.4. `continue`

~~~java
for (var item : items) {
    if (skip(item)) {
        continue;
    }
    use(item);
}
~~~

Một iteration bị bỏ qua phần xử lý sau `continue`, nhưng nguồn List/iterator có thể vẫn giữ Item. Không vì `continue` mà GC ngay lập tức được phép thu mọi object thuộc iteration đó.

### 16.5. Labelled break

~~~java
outer:
for (var group : groups) {
    for (var item : group) {
        if (mustStop(item)) {
            break outer;
        }
    }
}
~~~

Kết thúc sớm loop không tự đóng custom iterator/resource. Nếu `groups` được đọc từ file/database, dùng ownership/try-with-resources thích hợp.

### 16.6. Null source và null element khác nhau

~~~java
List<String> values = new ArrayList<>();
values.add(null);
for (var value : values) {
    System.out.println(value == null); // true
}
~~~

Hợp lệ vì ArrayList cho phép null. Trái lại, nếu `values == null`, evaluation source for-each sẽ thất bại khi cố gọi iterator. Cả hai hiện tượng không làm biến `value` đổi kiểu tĩnh từ `String` sang dynamic `null type`.

## 17. “Biên dịch và kiểm chứng” — quy trình review kết hợp source, bytecode, runtime

Một reviewer nên kiểm tra lần lượt:

### 17.1. Tầng source/JLS

- Vòng lặp ở dạng enhanced for thật hay `Stream.forEach`?
- `var` suy luận kiểu nào: reference hay primitive?
- Scope chính xác của item variable?
- Có reassign item, sửa object, hay sửa container?
- Có lambda/method reference/async capture?
- Có biến kết quả nằm ngoài loop hoặc static field?
- Có resource cần deterministic close không?

### 17.2. Tầng build/bytecode

- Biên dịch bằng đúng `--release` mà ứng dụng hỗ trợ.
- Dùng `javap -c` xem iterator/array translation nếu hành vi gây nghi ngờ.
- Không khẳng định số stack-slot/local-slot cố định giữa các JDK/compiler.
- Đảm bảo “compile negative cases” là cố ý sai, không để trong demo chính.

### 17.3. Tầng runtime

- Dùng deterministic output để xác nhận alias vs mutation, capture/retention.
- Xem heap retention graph thay vì đoán từ lexical braces.
- Đối chiếu số lượng objects và ownership sau batch.
- Nếu dùng native resource, xác định điểm `close()`/`reachabilityFence` có ý nghĩa.
- Không dùng weak ref/GC timing làm điều kiện logic.

### 17.4. Tầng concurrency

- Element object mutable có được chia sẻ giữa nhiều threads không?
- Lambda capture đưa reference vào queue có giới hạn không?
- Có happens-before/visibility đúng khi các threads sửa fields không?
- Các tasks dùng resource sau khi loop/owner đóng không?
- Có cơ chế cancel/timeout/cleanup khi execution thất bại không?

**Một biến có scope ngắn không tự tạo thread safety.** Nếu nhiều threads dùng cùng object, Java Memory Model vẫn áp dụng đầy đủ.

## 18. Những sai lầm thường gặp

| Ngộ nhận | Điều đúng |
| --- | --- |
| “`var` trong for-each là kiểu động.” | Kiểu được suy luận tại compile time theo phần tử source. |
| “Biến hết scope nghĩa object được GC ngay.” | Scope, liveness, reachability và reclamation khác nhau. |
| “Biến còn scope nghĩa object chắc chắn sống đến dấu `}`.” | JIT có thể xem local ref không còn cần trước đó theo chuẩn. |
| “`for (var e : list)` tạo deep copy của từng phần tử.” | `e` nhận giá trị tham chiếu, vẫn cùng object identity. |
| “`e = new E()` thay phần tử List.” | Chỉ thay local alias; dùng `List.set`/API phù hợp để thay container. |
| “`e = null` xóa object khỏi collection.” | Không xóa slot List/array hoặc references khác. |
| “`final var` khiến object immutable.” | Cấm gán lại biến, không cấm sửa trạng thái object. |
| “Sau vòng lặp, object trong list tự hết reachable.” | List/iterator/captures có thể giữ chúng. |
| “`List.copyOf` sao chép sâu từng object.” | Shallow unmodifiable list, giữ element references. |
| “Lambda không thể capture biến for-each.” | Capture được khi local variable effectively final. |
| “Capture + reassign trong cùng iteration vẫn biên dịch.” | Không, vì biến không còn effectively final. |
| “Các callback chạy sau loop không thể dùng Item.” | Callback có thể giữ Item reference ngoài scope tên lặp. |
| “`break` tự đóng Iterator/resource.” | Không có bảo đảm auto-close. |
| “Hết block tự đóng `InputStream`.” | Cần `close` hoặc try-with-resources/ownership. |
| “`System.gc` bảo đảm weak refs được clear.” | Không, GC timing không được cam kết. |
| “Bytecode local slot là GC root giữ object suốt method.” | Runtime liveness có thể khác; JIT tối ưu theo ngữ nghĩa. |
| “Mảng primitive cũng giữ object reference ở biến phần tử.” | Primitive values không phải object references. |
| “`Iterable` luôn bộ nhớ O(1).” | Không, backing iterable/iterator có thể giữ nhiều objects. |
| “Xóa trực tiếp List trong for-each luôn an toàn.” | Iterator semantics có thể bị vi phạm; dùng API thích hợp. |
| “`WeakReference` là cách đóng socket/file.” | Weak ref không quản resource lifetime; dùng AutoCloseable. |
| “JDK mới loại bỏ quy tắc scope for-each từ Java 10.” | Quy tắc JLS về contained statement và `var` vẫn áp dụng. |
| “Scope ngắn tự làm code đa luồng an toàn.” | Shared mutable objects vẫn cần synchronization/memory visibility. |

## 19. Bài tập và lời giải

### Bài 1 — Scope biến

~~~java
for (var text : List.of("A")) {
    System.out.println(text);
}
System.out.println(text);
~~~

**Hỏi:** Biên dịch được không?

**Đáp án:** Không. `text` chỉ có scope trong contained Statement của enhanced for; dòng sau loop dùng tên không còn in scope.

### Bài 2 — `var` với List

**Hỏi:** `List<String> strings` được duyệt bằng `for (var s : strings)` thì `s` có kiểu tĩnh nào?

**Đáp án:** `String`; `var` suy luận từ element type, không biến Java thành dynamic typing.

### Bài 3 — `var` với mảng

**Hỏi:** `for (var n : new int[]{1,2})` biến `n` là gì?

**Đáp án:** `int` primitive, không phải một reference tới object `Integer`.

### Bài 4 — Reassign local alias

~~~java
for (var builder : builders) {
    builder = new StringBuilder("OTHER");
}
~~~

**Hỏi:** Mảng `builders` có đổi các slots không?

**Đáp án:** Không. `builder` là local variable; array slots vẫn giữ references trước đó.

### Bài 5 — Mutation

**Hỏi:** Nếu thay phép gán ở bài 4 bằng `builder.append("!")` thì sao?

**Đáp án:** Chính object `StringBuilder` được mảng trỏ tới thay đổi; mảng vẫn giữ object ấy.

### Bài 6 — `final var`

**Hỏi:** Trong `for (final var person : people)` có được gọi `person.rename("X")` không?

**Đáp án:** Có nếu `rename` là method hợp lệ và `Person` mutable. `final` cấm `person = anotherPerson`, không đóng băng object.

### Bài 7 — Hết scope có GC ngay không?

**Đáp án:** Không. GC cần xét strong reachability qua toàn bộ graph, và không có cam kết thu hồi object ngay sau loop.

### Bài 8 — Copy list

**Hỏi:** Sau `var snapshot = List.copyOf(items)` rồi `items.clear()`, snapshot còn giữ elements không?

**Đáp án:** Có, nó vẫn chứa element references trong snapshot. `copyOf` không deep copy object state.

### Bài 9 — Lambda capture

**Hỏi:** Tại sao `callbacks.add(() -> item.name())` trong enhanced for có thể biên dịch?

**Đáp án:** Mỗi iteration có biến phần tử được khởi tạo và có thể effectively final; lambda capture reference của iteration đó.

### Bài 10 — Lambda + reassign

**Hỏi:** Nếu trong cùng body có `item = null` sau khi tạo lambda capture item, chuyện gì xảy ra?

**Đáp án:** Compile-time error theo quy tắc effectively final. Không phải chỉ “lambda nhìn thấy null”; compiler từ chối.

### Bài 11 — Async tasks

**Hỏi:** 10.000 tasks giữ reference tới payload lớn trong queue; loop đã xong. Payload được GC ngay không?

**Đáp án:** Không nếu tasks/queue vẫn giữ strongly reachable object graph. Giới hạn queue/capture data và lifecycle.

### Bài 12 — Source List

**Hỏi:** `largeList` có 1 triệu Item, for-each dùng từng Item. Có thể nói mỗi Item được giải phóng ngay sau lượt xử lý?

**Đáp án:** Không. `largeList` có thể giữ toàn bộ references đến khi list bị clear/không còn reachable, và còn có các owners khác.

### Bài 13 — Arrays vs Iterable

**Hỏi:** Source là `Item[]` thì for-each dùng `Iterator<Item>` không?

**Đáp án:** Theo phép dịch JLS, mảng dùng index/length; `Iterable` dùng `Iterator`.

### Bài 14 — Mỗi iteration có source evaluation mới?

**Hỏi:** Custom Iterable có `iterator()` đếm số lần; for-each chạy hai phần tử trong một loop. Method đó thường được gọi mấy lần trong ví dụ chuẩn?

**Đáp án:** Một lần để lấy iterator, sau đó `hasNext/next` cho từng phần tử. Demo xác nhận count=1.

### Bài 15 — Weak refs

**Hỏi:** Gọi `System.gc()` rồi `weak.get()==null` có luôn đúng không?

**Đáp án:** Không, timing và việc thu hồi/clear references không được bảo đảm theo số lần gọi GC.

### Bài 16 — Resource

**Hỏi:** Vì sao try-with-resources được ưu tiên hơn việc hy vọng biến `stream` tự mất sau mỗi iteration?

**Đáp án:** Try-with-resources gọi `close()` deterministically khi rời block theo contract, không phụ thuộc GC.

### Bài 17 — Reachability fence

**Hỏi:** `Reference.reachabilityFence(resource)` dùng để làm gì?

**Đáp án:** Đảm bảo `resource` strongly reachable ít nhất đến sau lời gọi, có ích khi native/Cleaner cleanup có thể quan sát; nó không trigger GC hoặc close resource.

### Bài 18 — Iterator remove

**Hỏi:** Muốn xóa các phần tử matching predicate khỏi mutable List, nên xóa trực tiếp trong for-each không?

**Đáp án:** Không nên. Dùng `removeIf` hoặc explicit Iterator.remove với collection hỗ trợ và kiểm tra semantics.

### Bài 19 — Tên biến lặp được tái sử dụng

**Hỏi:** Hai vòng `for (var item : first)` và `for (var item : second)` đứng nối tiếp có được dùng cùng tên không?

**Đáp án:** Được khi scopes không chồng nhau. Việc trùng tên không làm hai vòng chia sẻ object identity hay data.

### Bài 20 — Object có nhiều owners

**Hỏi:** Một Item được giữ bởi List, static cache và một lambda. Bỏ List và rời scope của for-each đã đủ eligible để GC chưa?

**Đáp án:** Chưa, nếu static cache/lambda còn reachable thì Item vẫn có đường strong reference.

### Bài 21 — Thread safety

**Hỏi:** Mỗi thread có biến for-each riêng nhưng tham chiếu tới cùng một object mutable. Có thể bỏ synchronization không?

**Đáp án:** Không. Scope local riêng không tránh data race trên object chung; cần contract immutability/thread-safe operations hoặc synchronization thích hợp.

### Bài 22 — Kiểm chứng bytecode

**Hỏi:** `javap -c` thấy Iterator.next và arraylength thì kết luận gì?

**Đáp án:** Có hai phép duyệt tương ứng với source Iterable và array. Không thể kết luận thời điểm GC reclaim chính xác từ số local slot ở bytecode.

## 20. Checklist đọc và review code Java hiện đại

- [ ] Đã xác định rõ code dùng **enhanced for** thay vì `Stream.forEach` chưa?
- [ ] Có hiểu `for (var item : items)` vẫn có static inferred type không?
- [ ] Có biết tên `item` chỉ thuộc contained Statement theo JLS `6.3` không?
- [ ] Có phân biệt lexical scope, liveness, reachability, reclamation không?
- [ ] Có tránh khẳng định object được GC ngay khi kết thúc iteration không?
- [ ] Có xem source List/array/Iterable còn giữ item references không?
- [ ] Có xem object có được lưu vào field/static cache/return value không?
- [ ] Có xem lambda/method reference/async queue giữ element không?
- [ ] Có tránh hiểu `List.copyOf` là deep copy không?
- [ ] Có phân biệt gán lại `item` với mutation của object/slot container không?
- [ ] Có hiểu `final var` cấm rebind nhưng không cấm object mutable methods không?
- [ ] Có phân biệt primitive array và reference array không?
- [ ] Có hiểu Iterable tạo Iterator, array được duyệt qua length/index theo JLS không?
- [ ] Có không viết logic phụ thuộc chính xác GC timing hoặc `System.gc()` không?
- [ ] Có sử dụng `Reference.reachabilityFence` chỉ khi có lý do native/Cleaner rõ không?
- [ ] Có dùng try-with-resources để bảo đảm close khi application sở hữu resource không?
- [ ] Có kiểm tra ownership trước khi clear/close collection được chia sẻ không?
- [ ] Có dùng `removeIf`/Iterator API đúng khi sửa cấu trúc collection không?
- [ ] Có xem task queue, futures, listeners và callback storage không bị unbounded không?
- [ ] Có hạn chế capture nguyên object graph nếu async chỉ cần ID/DTO không?
- [ ] Có xem bytecode bằng `javap` khi cần nhưng không suy sai GC từ local slots không?
- [ ] Có dùng heap dump/profiler cho memory leaks thay vì dự đoán từ dấu `}` không?
- [ ] Có giữ ví dụ compile-negative tách khỏi chương trình runnable không?
- [ ] Có kiểm tra code với `javac --release 17` hoặc runtime release mục tiêu không?
- [ ] Có áp dụng quy tắc đồng bộ/memory visibility khi objects được nhiều threads dùng không?

## 21. Nguồn chính thức, còn áp dụng

- [JLS 25 — `6.3 Scope of a Declaration`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3): phạm vi local variable trong enhanced for là contained Statement.
- [JLS 25 — `14.14.2 The Enhanced `for` Statement`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.14.2): quy tắc khởi tạo phần tử ở mỗi lượt, kiểu biến và phép dịch qua Iterator/array.
- [JEP 286 — Local-Variable Type Inference (Java 10)](https://openjdk.org/jeps/286): dùng `var` cho enhanced for và suy luận kiểu tĩnh.
- [Oracle Java 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): `var` trong for-each còn được hỗ trợ ở Java 17+.
- [JLS 25 — `12.6.1 Reachability Optimizations`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.6.1): compiler có thể rút ngắn object reachability khi local value không còn cần.
- [Java SE 25 — `java.lang.ref.Reference.reachabilityFence`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): đảm bảo strong reachability qua điểm cần thiết, không khởi động GC.
- [Java SE 25 — `java.lang.ref` package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/package-summary.html): phân loại strong/soft/weak/phantom references và reachability.
- [Java SE 25 — `WeakReference`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/WeakReference.html): weak references không ngăn GC trong điều kiện referent chỉ weakly reachable.
- [Java SE 25 — `Iterator`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html): `hasNext`, `next`, optional `remove`, điều kiện thay đổi backing collection.
- [Java SE 25 — `Collection.removeIf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)): xóa phần tử qua iterator theo contract.
- [Java SE 17 — `List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): danh sách unmodifiable, shallow element references.
- [Java SE 25 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html): tài nguyên được đóng qua `try-with-resources`.
- [Java SE 25 — `Runtime.gc`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#gc()): gọi GC không bảo đảm thu hồi một object cụ thể.

**Kết luận:** Với `for (var item : items)` từ Java 10, **tên biến `item` chỉ có scope trong thân vòng lặp**; mỗi lượt lấy một giá trị phần tử theo phép dịch Iterator hoặc array. Nhưng **scope không quyết định thời điểm object bị GC**: source collection, array slots, snapshots, lambdas, async tasks và nhiều owners khác có thể giữ tham chiếu mạnh lâu hơn, trong khi JIT có thể xác định local value không còn cần trước dấu `}`. Đánh giá lifetime theo **đồ thị tham chiếu, quyền sở hữu và last use**; dùng deterministic closing cho resources, tránh kiểm thử dựa vào GC timing.