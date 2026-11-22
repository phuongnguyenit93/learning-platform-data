# Java 10 – Map.copyOf: Khả năng tái sử dụng Map nguồn phù hợp

> **Ngữ cảnh:** Java 10 → **Map.copyOf** → **Khả năng tái sử dụng Map nguồn phù hợp**. Bài học tập trung vào các quy tắc vẫn còn hiệu lực với Java 17+ và các JDK hiện đại. `Map.copyOf` được bổ sung ở Java 10; `Map.of` và `Map.ofEntries` có từ Java 9. Các ví dụ chính sử dụng cú pháp Java 17 trở xuống và được kiểm thử bằng `javac --release 17`.

## 1. Mục tiêu và thông điệp cốt lõi

Sau bài học, bạn có thể:

1. Giải thích vì sao `Map.copyOf(source)` **có thể tái sử dụng** một Map nguồn thích hợp đã không thể sửa, thay vì luôn cấp phát một Map mới.
2. Phân biệt rõ **cam kết API** về nội dung snapshot với **ghi chú triển khai** về khả năng tránh sao chép/khả năng cùng identity.
3. Hiểu vì sao hai Map bằng nhau về nội dung theo `equals` nhưng không nhất thiết là cùng object (`==`), và vì sao không nên dựa vào identity của kết quả unmodifiable factory.
4. Phân biệt Map thật sự không thể sửa cấu trúc với **unmodifiable view** tạo bằng `Collections.unmodifiableMap` trên backing Map vẫn có thể bị thay đổi.
5. Dự đoán điều gì xảy ra khi nguồn là `HashMap`/`LinkedHashMap` mutable, `Map.of`, kết quả `Map.copyOf` khác, unmodifiable wrapper hoặc custom Map.
6. Phân biệt **shallow structural snapshot** với **deep immutability** của key và value.
7. Áp dụng nguyên tắc khi thiết kế DTO, config, cache snapshot và hệ thống nhiều thread; tránh tự tạo giả định về performance, iteration order, serialization hay synchronization.
8. Kiểm thử đúng các hành vi được đặc tả trên nhiều phiên bản Java và không vô tình kiểm thử một optimization nội bộ.

**Thông điệp chính:** `Map.copyOf` công bố một **Map không cho sửa cấu trúc** với các cặp key/value tại thời điểm sao chép; API có thể **không cần tạo một Map mới** khi nguồn đã phù hợp. **Không có bảo đảm kết quả là cùng object hoặc là object khác.** Code phải dựa trên **nội dung và hợp đồng**, không dựa trên identity hay giả định về số lần cấp phát.

## 2. Chữ ký và hợp đồng của `Map.copyOf`

Trong `java.util.Map`:

~~~java
static <K,V> Map<K,V> copyOf(Map<? extends K, ? extends V> map)
~~~

Các ý quan trọng của tài liệu Java SE:

- Nhận một `Map` nguồn và trả một **unmodifiable Map** chứa các entry từ nguồn.
- Không nhận đối số nguồn `null`.
- Không chấp nhận bất kỳ key hoặc value `null` nào trong nguồn.
- Nếu nguồn được **sửa sau khi thao tác copy hoàn tất**, Map kết quả **không phản ánh** những thay đổi cấu trúc/key/value mapping ấy.
- Không cho phép thêm, xóa hoặc cập nhật entry qua API Map trả về. Các mutator như `put`, `remove`, `clear` được xác định là không được hỗ trợ.
- **Thứ tự duyệt** entry/key/value của các Map từ unmodifiable factory này **không được cam kết**.
- Key/value là **tham chiếu đến object**; method không thực hiện deep copy của object đó.
- API có một **Implementation Note**: nếu đầu vào đã là một unmodifiable Map thì lời gọi `copyOf` nói chung có thể không cần tạo bản sao.

Điểm thứ tám liên quan trực tiếp đề bài. Tài liệu cố tình dùng cách nói về **triển khai**, không biến nó thành một lời hứa về identity, object allocation hay complex­ity cố định trong mọi trường hợp.

### 2.1. Phân biệt “copy” của API với việc luôn cấp phát mới

Tên `copyOf` dễ khiến người đọc hiểu rằng luôn có một object mới. Nhưng mục đích quan trọng nhất là **bảo vệ khả năng bị thay đổi của cấu trúc Map đã công bố**. Nếu nguồn đã nằm trong một dạng không thể sửa cấu trúc và không phụ thuộc backing Map mutable, việc tái sử dụng object đó có thể vẫn thỏa mãn mục tiêu.

Một lớp thư viện có thể chọn:

- Tạo Map mới unmodifiable với các entry nguồn;
- Trả lại chính nguồn đã được công nhận là dạng unmodifiable phù hợp;
- Dùng lại một singleton/canonical instance cho trường hợp đặc biệt như Map rỗng;
- Đổi cách tối ưu giữa các phiên bản/implementation JDK, miễn giữ hợp đồng API.

**Không nên suy luận** rằng một class cụ thể, ví dụ `java.util.ImmutableCollections$...`, là một phần của hợp đồng ổn định. Những tên class nội bộ có thể đổi, không phải loại để phụ thuộc trong code nghiệp vụ.

### 2.2. Hợp đồng API và Implementation Note khác nhau thế nào?

| Điều cần khẳng định | Mức độ |
| --- | --- |
| Kết quả Map unmodifiable | **Hợp đồng** |
| Kết quả chứa các cặp mapping của source tại thời điểm xử lý hợp lệ | **Hợp đồng** |
| Sửa Map nguồn sau đó không làm kết quả đổi mapping | **Hợp đồng** |
| Nguồn/key/value không được null | **Hợp đồng** |
| Nguồn unmodifiable **có thể** được tái sử dụng, tránh copy | **Ghi chú triển khai/khả năng tối ưu** |
| `Map.copyOf(source) == source` luôn true | **Không được bảo đảm** |
| `Map.copyOf(source) != source` luôn true | **Cũng không được bảo đảm** |
| Chỉ tốn `O(1)` khi nguồn unmodifiable | **Không có cam kết hiệu năng tổng quát** |
| Kết quả giữ insertion order hoặc là một class nội bộ cụ thể | **Không được bảo đảm** |

Khi review code, câu hỏi tốt hơn “nó có tạo object mới không?” là: *“Nếu Map nguồn bị sửa, bản snapshot của tôi có còn đúng không? Những object key/value có thực sự an toàn để chia sẻ không?”*

## 3. Nguồn phù hợp để có thể được tái sử dụng

### 3.1. `Map.of` tạo Map không sửa được ngay từ đầu

~~~java
import java.util.Map;

Map<String, Integer> base = Map.of("a", 1, "b", 2);
Map<String, Integer> result = Map.copyOf(base);

System.out.println(result.equals(base)); // true
System.out.println(result.get("a"));      // 1
~~~

`Map.of` từ Java 9 tạo Map unmodifiable, không có backing `HashMap` mutable được đưa vào constructor. Một implementation có thể nhận ra nguồn như vậy và **dùng lại** nó khi xử lý `Map.copyOf(base)`. Nhưng dù có hay không có reuse, `result.equals(base)` vẫn là bài kiểm tra hợp đồng hợp lệ.

Không viết:

~~~java
// Không phải kiểm tra hợp đồng API:
assert result == base;
~~~

Lệnh `==` có thể true trong một JDK hiện tại hoặc với một nhóm implementation nhất định, nhưng ứng dụng không được cần điều đó để chạy đúng.

### 3.2. `Map.ofEntries` cũng tạo dữ liệu unmodifiable thích hợp

~~~java
var base = Map.ofEntries(
    Map.entry("region", "VN"),
    Map.entry("tier", "gold")
);
var result = Map.copyOf(base);
~~~

Với một tập entry được xây dựng bằng unmodifiable factory, Map đã có đặc tính không cho sửa cấu trúc. `copyOf` có thể tối ưu việc tạo bản sao. Tuy nhiên **đừng phụ thuộc vào việc có cùng identity**, và đừng dùng `result.entrySet().iterator().next()` để giả định entry đầu tiên luôn là `region`.

`Map.of`/`Map.ofEntries` từ chối key/value null và trùng key được truyền khi tạo Map; `Map.copyOf` nhận một Map **đã tồn tại** (bản thân Map theo hợp đồng không có hai entry cùng key), nên không phải API để xử lý hai duplicate key trước khi Map hình thành.

### 3.3. Kết quả của `Map.copyOf` có thể làm đầu vào cho lần gọi tiếp theo

~~~java
Map<String, Integer> first = Map.copyOf(Map.of("x", 1));
Map<String, Integer> second = Map.copyOf(first);

System.out.println(first.equals(second)); // true
~~~

Về ngữ nghĩa, `second` có cùng mapping với `first` và không cho sửa. Implementation có thể tiết kiệm chi phí bằng cách tái sử dụng `first`; không có lý do ứng dụng phải hỏi nó có tạo ra object mới hay không.

**Quy tắc kiểm thử:** dùng `assertEquals(first, second)` hoặc so sánh mapping của từng key. Không ép `assertSame(first, second)`/`assertNotSame(first, second)` khi mục đích là kiểm tra hợp đồng Java SE.

### 3.4. Map rỗng và singleton

~~~java
var empty = Map.<String, Integer>of();
var copiedEmpty = Map.copyOf(empty);

System.out.println(copiedEmpty.isEmpty()); // true
~~~

Implementation có thể sử dụng một instance rỗng có thể dùng lại. Nhưng đừng thiết kế singleton của ứng dụng dựa trên `empty == copiedEmpty`. Nếu cần shared named constant, tự nắm giữ tham chiếu trong một field:

~~~java
private static final Map<String, Integer> NO_COUNTERS = Map.of();
~~~

Đây là một constant được khai báo rõ trong ứng dụng; giá trị không cho sửa, nhưng đừng dùng chính Map factory-produced này làm lock đồng bộ (`synchronized(NO_COUNTERS)`), vì các unmodifiable Map từ static factory có đặc tính value-based và không cam kết identity ổn định thích hợp cho synchronization.

## 4. Nguồn mutable: tạo kết quả độc lập về **mapping cấu trúc**

Ví dụ nguồn là `LinkedHashMap`:

~~~java
var source = new java.util.LinkedHashMap<String, Integer>();
source.put("count", 1);

var snapshot = java.util.Map.copyOf(source);

source.put("count", 2);
source.put("new", 3);

System.out.println(source.get("count")); // 2
System.out.println(snapshot.get("count")); // 1
System.out.println(snapshot.containsKey("new")); // false
~~~

Kết quả `snapshot` không nhận giá trị mới của key `count` và không tự xuất hiện key `new`. Đây là **hành vi API phải giữ**, không phải chi tiết implementation. Có thể source là `HashMap`, `LinkedHashMap` hoặc một Map mutable khác đáp ứng các tiền điều kiện; nguyên tắc vẫn áp dụng khi thao tác copy đã hoàn tất đúng cách.

`Map.copyOf` không phải **live view** liên kết với source. Khác với:

~~~java
var backing = new java.util.LinkedHashMap<String, String>();
backing.put("key", "old");

var live = java.util.Collections.unmodifiableMap(backing);
backing.put("key", "new");

System.out.println(live.get("key")); // new
~~~

Wrapper `live` không cho caller gọi `live.put(...)`, nhưng nguồn `backing` còn mutable và vẫn có thể làm nội dung quan sát qua wrapper thay đổi.

### 4.1. Hậu quả quan trọng khi copy một **unmodifiable view**

~~~java
var backing = new java.util.LinkedHashMap<String, String>();
backing.put("key", "old");

var view = java.util.Collections.unmodifiableMap(backing);
var detached = java.util.Map.copyOf(view);

backing.put("key", "new");

System.out.println(view.get("key"));     // new
System.out.println(detached.get("key")); // old
~~~

Đây là tình huống dễ nhầm khi nghe “nếu nguồn unmodifiable, Map.copyOf có thể tái sử dụng”.

- `view` là một **unmodifiable Map về khả năng gọi mutator qua tham chiếu view**.
- Nhưng `view` vẫn là **view trực tiếp** của backing Map có thể thay đổi.
- `Map.copyOf(view)` phải giữ hợp đồng không phản ánh lần sửa nguồn xảy ra **sau** copy thành công; ví dụ JDK hiện đại tạo một kết quả tách cấu trúc khỏi backing nguồn.
- Không được diễn giải Implementation Note thành luật “cứ là `Collections.unmodifiableMap` thì `copyOf` trả nguyên wrapper”.
- Phân biệt **khả năng không thể gọi mutator thông qua một reference** với **khả năng dữ liệu thay đổi qua reference/alias khác**.

Một custom unmodifiable Map do ứng dụng tự tạo cũng không nhất thiết được JDK nhận diện để tái sử dụng. Compiler/JVM không có nghĩa vụ tối ưu mọi loại Map bên ngoài dựa trên tên class hoặc việc method `put` ném lỗi. Chọn `copyOf` vì **hợp đồng bảo vệ snapshot**, không phải vì muốn ép một optimization riêng.

### 4.2. Nếu dùng `new HashMap<>(source)` thì sao?

~~~java
var source = java.util.Map.of("a", 1);
var mutableCopy = new java.util.HashMap<>(source);
mutableCopy.put("b", 2); // HỢP LỆ
~~~

`new HashMap<>(source)` tạo Map mutable và có thể chứa null theo quy tắc `HashMap`; `Map.copyOf(source)` trả Map unmodifiable, từ chối null. Cả hai đều dùng các mapping trong input để khởi tạo, nhưng **hợp đồng khác nhau**. Nếu mục đích là xây tiếp dữ liệu mutable, dùng `HashMap`; nếu muốn đóng băng cấu trúc và công bố read-only snapshot, dùng `Map.copyOf`.

## 5. Một “bản sao” của Map không nhất thiết deep-copy key/value

`Map.copyOf` xử lý **cấu trúc ánh xạ** giữa các key và value. Nó không tự tạo object key/value mới.

Xét value mutable:

~~~java
final class MutableValue {
    private String label;
    MutableValue(String label) { this.label = label; }
    void rename(String next) { label = next; }
    String label() { return label; }
}

var value = new MutableValue("draft");
var source = new java.util.HashMap<String, MutableValue>();
source.put("id", value);

var snapshot = java.util.Map.copyOf(source);
value.rename("changed");

System.out.println(snapshot.get("id").label()); // changed
~~~

**Vì sao thấy `changed`?** Mapping `"id" → value reference` không đổi, nhưng field của **cùng object value** đã bị sửa. Ngay cả khi JVM tạo Map instance mới, phần tử value vẫn là cùng object trừ khi code chủ động thực hiện copy riêng.

Suy ra:

- `Map.copyOf` bảo vệ cấu trúc: không thể thêm/xóa/thay mapping qua kết quả.
- `Map.copyOf` **không** biến `MutableValue` thành immutable.
- Nếu value là `List` mutable, array hoặc custom entity có setter, caller còn nắm alias có thể làm thay đổi dữ liệu được quan sát qua Map.
- Nếu key là object có field dùng trong `equals`/`hashCode` và field đó bị thay đổi sau khi đưa vào Map, việc lookup có thể trở nên không đáng tin; nên dùng **key immutable**.

### 5.1. Bản sao độc lập cấu trúc không đồng nghĩa snapshot bất biến sâu

| Cấp độ | `Map.copyOf` bảo đảm? | Ví dụ |
| --- | --- | --- |
| Không thêm key mới qua result | Có | `result.put("x", value)` bị từ chối |
| Không xóa key qua result | Có | `result.remove("x")` bị từ chối |
| Không thay mapping qua result | Có | `result.replace("x", other)` bị từ chối |
| Không phản ánh source `put/remove` sau copy | Có, khi copy hoàn tất hợp lệ | Source thay `count=1` thành `count=2` |
| Không thay đổi trạng thái của object value | Không | `MutableValue.rename` vẫn hoạt động |
| Không thay đổi trạng thái của object key | Không | Key mutable có thể phá invariant |
| Luôn tạo Map object riêng | Không | Source immutable phù hợp có thể được tái sử dụng |
| Luôn giữ insertion order | Không | Iteration order không được cam kết |

### 5.2. Cách tạo data snapshot có giá trị immutable

Một ví dụ dùng `record` (tính năng chính thức từ Java 16):

~~~java
record Settings(java.util.Map<String, String> entries) {
    Settings {
        entries = java.util.Map.copyOf(entries);
    }
}
~~~

Nếu key/value đều là `String` immutable, record không có setter và constructor chốt Map đầu vào thì đây là cấu trúc đơn giản để công bố snapshot. Khi biến `entries` được truyền vào là một `HashMap` mutable, caller sửa map đó sau khi tạo `Settings` cũng không làm thay đổi mapping của record.

~~~java
var input = new java.util.HashMap<String, String>();
input.put("mode", "safe");
var settings = new Settings(input);

input.put("mode", "unsafe");
System.out.println(settings.entries().get("mode")); // safe
~~~

Nếu Map chứa `MutableValue`, record chứa `Map.copyOf` vẫn **chưa deep immutable**. Cần chuyển từng value thành immutable DTO hoặc defensive copy thích hợp trước khi xây Map. Việc trả trực tiếp `entries()` là phù hợp khi Map và các object lồng nhau thực sự không thể đổi; nếu value mutable thì caller vẫn có thể sửa element qua getter.

## 6. Identity của Map: `==` không phải tiêu chuẩn đúng cho `copyOf`

Đây là phần dễ rơi vào tối ưu hóa sai lầm nhất.

### 6.1. Bằng về nội dung khác cùng identity

~~~java
var source = java.util.Map.of("a", 1);
var copy = java.util.Map.copyOf(source);

boolean sameMappings = source.equals(copy); // true
boolean sameReference = source == copy;     // Có thể true hoặc false; không dựa vào
~~~

`Map.equals` so sánh nội dung các mapping theo hợp đồng Map; còn `==` kiểm tra hai reference có trỏ đến **cùng object** hay không. Thông thường bài toán application cần `sameMappings`, không cần `sameReference`.

Nếu bạn cần kiểm tra liệu một hệ thống có thay đổi **phiên bản dữ liệu**, hãy dùng `version`, `generation`, `timestamp` có hợp đồng rõ hoặc một version token do ứng dụng quản lý; không dùng identity Map factory-produced làm số phiên bản.

### 6.2. Vì sao không nên dùng factory Map làm monitor khóa?

Các Map trả từ `Map.of`, `Map.ofEntries` và `Map.copyOf` được mô tả là value-based: chương trình không nên giả định identity ổn định của object kết quả.

Không nên:

~~~java
// KHÔNG làm trong code đồng thời:
var state = java.util.Map.of("ready", true);
// synchronized (state) { ... } // tránh đồng bộ dựa trên identity Map value-based
~~~

Nếu cần lock, dùng object monitor **riêng do ứng dụng sở hữu**:

~~~java
private final Object lock = new Object();

void doWork() {
    synchronized (lock) {
        // cập nhật trạng thái mutable được bảo vệ
    }
}
~~~

Đây là **đoạn minh họa bên trong một class**, không phải chương trình độc lập. Từ khóa `final` trên reference hoặc việc Map unmodifiable không biến nó thành một lock có identity được API khuyến nghị sử dụng.

### 6.3. Đừng dùng kết quả identity test làm quyết định nghiệp vụ

Một experiment local:

~~~java
var src = java.util.Map.of("a", 1);
var copy = java.util.Map.copyOf(src);
System.out.println(src == copy);
~~~

Bạn có thể thấy `true` trên một bản OpenJDK cụ thể. Đây là **quan sát về implementation đang chạy**, không phải stdout chuẩn để dùng trong bài kiểm thử cross-JDK hoặc lý do để gỡ bỏ `copyOf` ở nơi cần hợp đồng defensive snapshot. Code tương lai, VM khác hoặc một custom Map có thể tạo kết quả khác mà vẫn tuân thủ Java SE.

## 7. Nguồn “phù hợp” cần thỏa những gì?

Để một thao tác copy có thể được tối ưu thành tái sử dụng mà vẫn đúng API, hãy xét ít nhất các đặc điểm sau:

1. Source thực sự không thể bị thay đổi **cấu trúc và mapping** sau thời điểm trả kết quả, kể cả thông qua alias/backing Map.
2. Kết quả phải hỗ trợ hành vi unmodifiable theo Java SE.
3. Mọi key và value trong nguồn phải **khác null**; source phải khác null.
4. Generic type parameter và các mapping phải phù hợp với chữ ký `Map.copyOf`; không phụ thuộc vào raw-type tricks.
5. Không thêm yêu cầu không có trong API như “Map result phải giữ insertion order”.
6. Để **trạng thái dữ liệu thực sự ổn định sâu**, key/value cũng cần immutable hoặc được bảo vệ riêng. Điều này không phải luôn là điều kiện để Map.copyOf hoạt động, nhưng là điều kiện cho nhiều trường hợp **chia sẻ trạng thái**.

Đây là các **yếu tố để hiểu tính hợp lệ của một optimization**, không phải một danh sách có thể kiểm tra từ source code rồi kết luận chắc chắn JVM sẽ trả cùng object. Java API không đưa ra hàm `isReusableMap` hay tiêu chuẩn công khai bảo đảm identity.

| Nguồn | Có thể suy ra điều gì về kết quả? | Có cam kết reuse cùng reference? |
| --- | --- | --- |
| `Map.of("a", 1)` | Unmodifiable, không có backing mutable bên ngoài theo thiết kế | **Không**; optimization có thể xảy ra |
| `Map.ofEntries(...)` | Unmodifiable, các mapping đã chốt | **Không** |
| `Map.copyOf(previous)` | Unmodifiable structural snapshot | **Không** |
| `new HashMap<>(...)` | Source mutable; result phải tách cấu trúc khỏi sửa đổi sau đó | **Không** |
| `new LinkedHashMap<>(...)` | Source mutable, insertion order của source không phải order result | **Không** |
| `Collections.unmodifiableMap(backing)` | Wrapper không cho sửa **qua wrapper**, backing có thể thay đổi | **Không**; không được suy ra sẽ reuse |
| Custom immutable Map | Tùy hợp đồng và implementation của Map | **Không** |
| Map có mutable values | Map result không cho sửa mapping, nhưng state của value vẫn có thể đổi | **Không** |

Trong production, quyết định dùng `Map.copyOf` dựa vào **yêu cầu ranh giới dữ liệu**; để JDK lựa chọn có cấp phát/copy lại hay không.

## 8. Map unmodifiable và null/duplicate/order

### 8.1. Key hoặc value null bị từ chối

~~~java
var source = new java.util.HashMap<String, String>();
source.put("key", null);

// java.util.Map.copyOf(source); // ném NullPointerException khi chạy
~~~

Tương tự với null key:

~~~java
var source = new java.util.HashMap<String, String>();
source.put(null, "value");

// java.util.Map.copyOf(source); // ném NullPointerException khi chạy
~~~

`Map.copyOf(null)` cũng ném `NullPointerException`. Trước khi công bố cấu hình từ nguồn dữ liệu bên ngoài, hãy validate/normalize null theo nghiệp vụ thay vì mong nó được giữ nguyên. `HashMap` có thể chứa null, còn unmodifiable factory Maps không cho phép.

### 8.2. Duplicate keys không phải vấn đề được giải quyết bởi `Map.copyOf`

~~~java
// mapFactory cố tạo hai entry cùng key:
java.util.Map.of("a", 1, "a", 2); // ném IllegalArgumentException
~~~

Một Map hợp lệ không chứa **hai mapping** với cùng key theo `equals`. Khi đã có một `Map` nguồn, các phép `put` trùng key thường thay giá trị cũ; `Map.copyOf` chỉ copy các mapping còn lại. Nó không thể biết các event gốc nào đã bị overwrite trước khi Map được hình thành.

Nếu dữ liệu thực tế có nhiều cặp cùng key và cần chính sách first/last/reject duplicates, hãy xử lý trong quá trình tạo Map hoặc dùng `Collectors.toMap` với merge function rõ ràng. `Map.copyOf` không phải bộ xử lý duplicate key có khả năng phục hồi các bản ghi đã mất.

### 8.3. Thứ tự duyệt của Map kết quả không được cam kết

~~~java
var linked = new java.util.LinkedHashMap<String, Integer>();
linked.put("first", 1);
linked.put("second", 2);
var immutable = java.util.Map.copyOf(linked);
~~~

Không được viết test đòi `immutable.keySet()` luôn duyệt theo thứ tự `first, second`. `LinkedHashMap` có insertion order nhưng `Map.copyOf` trả loại unmodifiable Map không cam kết iteration order. Nếu ứng dụng cần thứ tự xuất báo cáo, hãy sắp xếp keys hoặc cấu trúc riêng:

~~~java
var sortedKeys = immutable.keySet().stream().sorted().toList(); // Java 16+
System.out.println(sortedKeys); // [first, second]
~~~

Hoặc giữ một `List` có thứ tự bên cạnh Map, tùy domain. Đừng biến thứ tự Map factory-produced thành contract ngầm cho JSON/API hoặc test.

## 9. Khi nào tái sử dụng nguồn thực sự có ích?

### 9.1. Tránh copy thừa khi dữ liệu đã được chốt

Giả sử một module đã chuẩn hóa một immutable config:

~~~java
Map<String, String> canonical = Map.of(
    "region", "ap-southeast",
    "mode", "strict"
);
~~~

Một lớp khác muốn tiếp nhận config theo hợp đồng “không cho sửa cấu trúc”:

~~~java
class ReaderConfig {
    private final Map<String, String> entries;

    ReaderConfig(Map<String, String> entries) {
        this.entries = Map.copyOf(entries);
    }

    Map<String, String> entries() { return entries; }
}
~~~

Khi caller truyền `canonical`, implementation có thể tránh copy lại vì nguồn đã thích hợp. Khi caller truyền `HashMap` mutable, lời gọi **vẫn bảo vệ** kết quả khỏi thay đổi mapping của source. Đây là lợi ích lớn của việc viết một constructor **đơn giản, có hợp đồng nhất quán**, thay vì tự viết nhiều nhánh đoán concrete class Map.

### 9.2. Không cần tự tối ưu bằng `instanceof` implementation nội bộ

Không nên:

~~~java
// Tránh kiểu code lệ thuộc chi tiết triển khai:
if (map.getClass().getName().contains("ImmutableCollections")) {
    // giả định sẽ giữ nguyên identity, bỏ qua bước chốt hợp đồng
}
~~~

Tên class nội bộ không ổn định và không phải tiêu chuẩn để đánh giá source có backing mutable/alias khác hay không. Nếu API của bạn yêu cầu một Map unmodifiable snapshot, hãy viết `Map.copyOf(map)`. JVM/JDK được tự do tái sử dụng khi phù hợp.

### 9.3. Không suy ra tốc độ tuyệt đối từ từ “copyOf”

- Có source mà copy là bước tạo và chốt entry mới; chi phí phải phụ thuộc số entry hoặc chi tiết cấu trúc.
- Có source thích hợp mà implementation có thể dùng lại, tránh một phần allocation.
- Trong một số workload, CPU/GC của việc tạo snapshot liên tục có thể đáng kể; cần benchmark **đúng phiên bản JDK, kích thước dữ liệu, loại nguồn và tần suất gọi**.
- Không được hứa rằng `Map.copyOf` là `O(1)` hoặc “zero allocation” cho mọi Map unmodifiable.
- Tránh dùng reflection để cố truy cập và dựa vào class nội bộ của `ImmutableCollections`. Chọn thiết kế dựa trên hợp đồng và đo hiệu năng khi có bằng chứng.

### 9.4. Nếu không cần snapshot, đừng copy chỉ để rồi tiếp tục mutate

Ví dụ đang xây index mutable:

~~~java
var index = new java.util.HashMap<String, Integer>();
index.put("one", 1);
index.put("two", 2);

// Chỉ chốt khi cần công bố:
var snapshot = java.util.Map.copyOf(index);
~~~

Không nên gọi `Map.copyOf(index)` sau mọi lần `put` nếu mục tiêu chỉ là hoàn thành một builder trong cùng thread. Khi hệ thống cần nhiều phiên bản snapshot vì reader đồng thời, hãy cân nhắc tradeoff giữa chi phí copy và yêu cầu nhất quán.

## 10. Ví dụ Java 17+ hoàn chỉnh đã kiểm chứng

Lưu chương trình sau vào **`MapCopyReuseDemo.java`**. Bài chạy không dựa vào việc `Map.copyOf` giữ nguyên identity, cũng không in toàn bộ HashMap ở thứ tự không được cam kết. Nó chỉ kiểm tra **các mapping** theo key, hành vi của wrapper và object value.

~~~java
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

public class MapCopyReuseDemo {
    static final class MutableValue {
        private String label;
        MutableValue(String label) { this.label = label; }
        void rename(String next) { this.label = next; }
        String label() { return label; }
    }

    record Settings(Map<String, String> entries) {
        Settings { entries = Map.copyOf(entries); }
    }

    public static void main(String[] args) {
        Map<String, Integer> immutable = Map.of("a", 1, "b", 2);
        var maybeReused = Map.copyOf(immutable);
        System.out.println("same-content=" + maybeReused.equals(immutable));
        System.out.println("immutable-a=" + maybeReused.get("a"));

        var source = new LinkedHashMap<String, Integer>();
        source.put("count", 1);
        var snapshot = Map.copyOf(source);
        source.put("count", 2);
        source.put("new", 3);
        System.out.println("source-count=" + source.get("count"));
        System.out.println("snapshot-count=" + snapshot.get("count"));
        System.out.println("snapshot-has-new=" + snapshot.containsKey("new"));

        try {
            snapshot.put("blocked", 9);
        } catch (UnsupportedOperationException e) {
            System.out.println("snapshot-write=blocked");
        }

        var backing = new LinkedHashMap<String, String>();
        backing.put("key", "old");
        var view = Collections.unmodifiableMap(backing);
        var detached = Map.copyOf(view);
        backing.put("key", "new");
        System.out.println("live-view=" + view.get("key"));
        System.out.println("detached-copy=" + detached.get("key"));

        var value = new MutableValue("draft");
        var values = new HashMap<String, MutableValue>();
        values.put("v", value);
        var shallow = Map.copyOf(values);
        value.rename("changed");
        System.out.println("mutable-value=" + shallow.get("v").label());

        var mutableSettings = new LinkedHashMap<String, String>();
        mutableSettings.put("mode", "safe");
        var settings = new Settings(mutableSettings);
        mutableSettings.put("mode", "unsafe");
        System.out.println("settings-mode=" + settings.entries().get("mode"));

        var withNullValue = new HashMap<String, String>();
        withNullValue.put("key", null);
        try {
            Map.copyOf(withNullValue);
        } catch (NullPointerException e) {
            System.out.println("null-value=rejected");
        }

        var withNullKey = new HashMap<String, String>();
        withNullKey.put(null, "value");
        try {
            Map.copyOf(withNullKey);
        } catch (NullPointerException e) {
            System.out.println("null-key=rejected");
        }

        var repeated = Map.copyOf(snapshot);
        System.out.println("repeat-equal=" + repeated.equals(snapshot));

        var registry = new AtomicReference<Map<String, String>>(Map.of());
        var next = new HashMap<String, String>();
        next.put("flag", "on");
        registry.set(Map.copyOf(next));
        next.put("flag", "off");
        System.out.println("published-flag=" + registry.get().get("flag"));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file:

~~~bash
javac --release 17 MapCopyReuseDemo.java
java MapCopyReuseDemo
~~~

**Stdout chính xác** của chương trình:

~~~text
same-content=true
immutable-a=1
source-count=2
snapshot-count=1
snapshot-has-new=false
snapshot-write=blocked
live-view=new
detached-copy=old
mutable-value=changed
settings-mode=safe
null-value=rejected
null-key=rejected
repeat-equal=true
published-flag=on
~~~

### 10.1. Diễn giải output

1. `same-content=true`: hai Map bằng nhau về mapping; không kiểm tra `==`, do identity không phải hợp đồng.
2. `immutable-a=1`: đọc kết quả từ nguồn `Map.of` hợp lệ.
3. `source-count=2`, `snapshot-count=1` và `snapshot-has-new=false`: `Map.copyOf` không phản ánh các cập nhật mapping thực hiện **sau** khi copy.
4. `snapshot-write=blocked`: không thể sửa cấu trúc result qua `put`.
5. `live-view=new` nhưng `detached-copy=old`: unmodifiable wrapper vẫn đọc backing Map, còn `Map.copyOf(view)` cho kết quả không phản ánh cập nhật sau copy.
6. `mutable-value=changed`: value object trong result vẫn bị sửa qua alias; không có deep copy.
7. `settings-mode=safe`: record giữ một Map snapshot của nguồn mutable chứa String/String, giúp cô lập mapping cấu hình.
8. `null-value=rejected` và `null-key=rejected`: `Map.copyOf` từ chối null key/value.
9. `repeat-equal=true`: hai snapshot có mapping như nhau; không suy ra identity hoặc số lần cấp phát.
10. `published-flag=on`: ứng dụng công bố một immutable mapping qua `AtomicReference`, rồi sửa source mutable sau đó không ảnh hưởng snapshot đã công bố. Đây chỉ là ví dụ logic tuần tự; để đánh giá concurrency thật phải xét hợp đồng memory consistency của các thao tác atomic và immutability của key/value.

## 11. Thiết kế API an toàn khi tiếp nhận một Map từ caller

### 11.1. Pattern khuyến nghị với dữ liệu config nhỏ

~~~java
public final class FeatureFlags {
    private final Map<String, Boolean> flags;

    public FeatureFlags(Map<String, Boolean> input) {
        this.flags = Map.copyOf(input);
    }

    public boolean enabled(String name) {
        return Boolean.TRUE.equals(flags.get(name));
    }

    public Map<String, Boolean> all() {
        return flags;
    }
}
~~~

Đây là **đoạn minh họa cho một file class có import `java.util.Map`**, không phải chương trình chạy độc lập. Vì `String` và `Boolean` là immutable, việc lưu `Map.copyOf(input)` bảo vệ các mapping khỏi alias mutation của caller. Getter `all()` trả Map unmodifiable, nên caller không thay mapping qua getter.

Chính sách `enabled` ở trên coi key không tồn tại là `false`. Nếu doanh nghiệp phân biệt “chưa cấu hình” với `false`, cần công bố quy tắc rõ (có thể trả `Optional<Boolean>` hoặc phương thức khác).

### 11.2. Pattern cho DTO có phần tử mutable

Nếu value là đối tượng mutable:

~~~java
record RequestLimit(int perMinute) {}

static Map<String, RequestLimit> snapshotLimits(
        Map<String, MutableLimit> incoming) {
    var converted = new java.util.HashMap<String, RequestLimit>();

    incoming.forEach((key, value) -> {
        converted.put(key, new RequestLimit(value.perMinute()));
    });

    return Map.copyOf(converted);
}
~~~

Đây là **đoạn minh họa cần class `MutableLimit` có method `perMinute()`**, không phải chương trình độc lập. Ý quan trọng là chuyển từng object value sang immutable value object **trước khi** chốt Map. Đừng mặc định `Map.copyOf(incoming)` đã tạo deep copy.

### 11.3. Chỉ kiểm tra ở ranh giới, đừng tạo vòng lặp `copyOf` vô ích

Nếu service luôn trả `Map.copyOf` với key/value immutable, nhiều caller có thể tiếp nhận kết quả mà không phải tự tay clone. Tuy nhiên module khác vẫn có thể gọi lại `Map.copyOf` để thực thi hợp đồng riêng của nó; JDK có quyền tối ưu reuse. Khi profiling cho thấy một phần chi phí lớn đến từ việc xây snapshot, hãy tối ưu thiết kế/cadence dữ liệu trước, không thay giả định `copyOf` bằng một nhánh `instanceof` lỏng lẻo.

## 12. Chia sẻ Map giữa các luồng: reuse không đồng nghĩa safe publication

Có ba vấn đề riêng biệt:

1. **Nguồn mutable có thể đổi mapping sau khi copy không?** `Map.copyOf` bảo vệ mapping kết quả sau khi thao tác hoàn tất đúng.
2. **Key/value có mutable không?** `Map.copyOf` không đóng băng object phần tử.
3. **Thread khác có nhận/quan sát snapshot đúng cách không?** Cần quan hệ `happens-before` hoặc cơ chế chia sẻ có memory-consistency guarantee khi công bố/cập nhật tham chiếu.

### 12.1. Ví dụ snapshot + `AtomicReference`

~~~java
final class Registry {
    private final java.util.concurrent.atomic.AtomicReference<
            java.util.Map<String, String>> current =
            new java.util.concurrent.atomic.AtomicReference<>(java.util.Map.of());

    void replace(java.util.Map<String, String> next) {
        current.set(java.util.Map.copyOf(next));
    }

    java.util.Map<String, String> snapshot() {
        return current.get();
    }
}
~~~

Đây là đoạn minh họa đặt trong một class có thể biên dịch khi các import/kiểu đầy đủ, không phải chương trình `main` độc lập. `AtomicReference.set/get` mang các bảo đảm memory tương đương thao tác volatile phù hợp; việc xây Map rồi `set` là cách công bố một snapshot cho thread khác.

Reader nên gọi `snapshot()` một lần và dùng cùng bản đó trong một nghiệp vụ nếu cần nhất quán theo phiên bản. Nếu writer có thể thay snapshot giữa hai lần đọc, reader gọi `snapshot()` hai lần có thể quan sát hai phiên bản khác nhau. Không phụ thuộc Map instance identity để nhận dạng version; dùng version token riêng khi cần.

### 12.2. Copy nguồn đang bị sửa đồng thời không tự cho atomic snapshot

~~~java
// Thread A: source.put(...)
// Thread B: Map.copyOf(source)
~~~

Nếu nguồn là `HashMap`/`LinkedHashMap` mutable và các thread sửa/duyệt không có đồng bộ, `Map.copyOf` không tự khóa nguồn. Có nguy cơ data race, lỗi duyệt hoặc dữ liệu không nhất quán. Với `ConcurrentHashMap`, thao tác concurrent được hỗ trợ theo hợp đồng riêng nhưng iterator có thể weakly consistent; việc sao chép không mặc nhiên là ảnh nguyên tử của một thời điểm toàn cục.

Nếu cần snapshot nhất quán, bảo vệ quá trình cập nhật/copy bằng cùng lock hoặc thiết kế immutable state được publish theo phiên bản:

~~~java
final class SafeConfigSource {
    private final Object lock = new Object();
    private final java.util.Map<String, String> mutable =
            new java.util.HashMap<>();

    void put(String key, String value) {
        synchronized (lock) {
            mutable.put(key, value);
        }
    }

    java.util.Map<String, String> snapshot() {
        synchronized (lock) {
            return java.util.Map.copyOf(mutable);
        }
    }
}
~~~

Các thao tác phải tuân thủ cùng giao thức lock; không lộ `mutable` ra ngoài cho caller tự sửa. Với nhiều writer làm read-modify-write, một `AtomicReference.set` đơn lẻ không ngăn lost update; khi đó cần CAS/updateAndGet hoặc lock tùy yêu cầu.

### 12.3. Bản thân Map unmodifiable không tự khiến object value thread-safe

~~~java
var flags = java.util.Map.copyOf(mutableValues);
~~~

Nếu `mutableValues` chứa các object thay đổi bên trong (ví dụ StringBuilder, entity với setter), nhiều thread cùng đọc/sửa những object ấy có thể race dù Map không cho thêm/xóa key. Để chia sẻ an toàn, chọn immutable key/value và công bố đúng. `final` trên field tham chiếu Map cũng không thay thế cơ chế đồng bộ cho phần tử mutable.

## 13. Kiểm thử đúng hợp đồng thay vì kiểm thử tối ưu hóa

### 13.1. Những assertion nên có

~~~java
var source = new java.util.HashMap<String, Integer>();
source.put("a", 1);

var snapshot = java.util.Map.copyOf(source);

assert snapshot.get("a") == 1;
source.put("a", 2);
assert snapshot.get("a") == 1;
assert snapshot.size() == 1;
~~~

Lưu ý với `assert` của Java: assertion có thể bị tắt mặc định khi chạy; nếu dùng test framework như JUnit, nên dùng các assertion của framework. Đoạn trên chỉ minh họa các **điều kiện đúng cần kiểm tra**, không phải một test chạy độc lập.

Nên bổ sung kiểm thử exception khi source có null, kiểm thử các method mutator bị từ chối và kiểm thử giá trị DTO immutable sau khi caller sửa nguồn. Khi test cross-JDK, đừng phụ thuộc vào thứ tự duyệt Map.

### 13.2. Những assertion không nên có

~~~java
var base = java.util.Map.of("a", 1);
var copied = java.util.Map.copyOf(base);

// Không phải hợp đồng Java SE:
assert copied == base;
assert copied != base;
// Không giả định class name:
assert copied.getClass().getName().contains("ImmutableCollections");
~~~

Đó là kiểm thử implementation detail. Cả `assertSame` và `assertNotSame` đều không phản ánh giá trị học tập/correctness của `Map.copyOf` trong trường hợp này. Dù một bản OpenJDK hôm nay trả cùng instance, JDK/VM khác có thể vẫn tuân thủ hợp đồng nhưng không làm thế.

### 13.3. Quan sát identity chỉ để nghiên cứu, không để quyết định hành vi

Nếu bạn đang nghiên cứu hiệu năng, có thể in kết quả `base == Map.copyOf(base)` để thấy optimization ở môi trường cụ thể, nhưng **không dùng output đó làm tiêu chuẩn tính đúng đắn**. Muốn đánh giá chi phí thật, đo workload và JVM với công cụ profiling/benchmark phù hợp. Tránh so sánh allocation bằng vài lệnh `System.nanoTime` đơn lẻ vì JIT, escape analysis, warmup và GC có thể làm kết quả sai lệch.

## 14. Những nhầm lẫn cần sửa trong code review

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`Map.copyOf` luôn tạo một HashMap mới” | Nó trả unmodifiable Map; implementation có thể dùng lại Map phù hợp |
| “Nguồn unmodifiable thì `copyOf` chắc chắn trả đúng cùng instance” | Implementation Note không bảo đảm identity; không dùng `==` làm hợp đồng |
| “`Collections.unmodifiableMap` luôn là bản copy độc lập” | Đây là view, backing Map có thể vẫn thay đổi qua alias |
| “Map.copyOf sẽ tái sử dụng luôn unmodifiable view” | Không được suy ra; kết quả vẫn phải bảo vệ mapping khỏi sửa đổi nguồn sau copy |
| “Map.copyOf là deep copy cả key và value” | Không; object key/value vẫn là cùng tham chiếu |
| “Map mới khác identity thì chắc chắn dữ liệu đã immutable sâu” | Identity Map khác không biến mutable values thành immutable |
| “Map.copyOf cho phép null như HashMap” | Không; null source/key/value bị từ chối |
| “Map.copyOf giữ insertion order của LinkedHashMap” | Thứ tự duyệt của unmodifiable Map không được cam kết |
| “Map.copyOf giải quyết duplicate keys trong raw events” | Map nguồn đã có unique keys; cần merge ở bước dựng Map |
| “Tái sử dụng Map không đổi nghĩa là thread-safe mọi thứ” | Safe publication và mutable object bên trong vẫn phải được xử lý |
| “`copyOf` có performance complexity cố định cho mọi source” | Không có bảo đảm chung; đo thực tế khi cần |
| “Có thể đồng bộ bằng `synchronized(mapCopy)`” | Map từ factory là value-based; tránh dùng identity làm monitor |
| “Đổi Map nguồn nhưng giữ nguyên cùng object sau copy là điều phải tránh” | Có thể reuse hợp lệ; caller nên dựa mapping và contract |
| “Thử một phiên bản JVM rồi viết test identity cross-platform” | Quan sát implementation không phải cam kết Java SE |

## 15. Bài tập tự kiểm tra kèm đáp án

**Bài 1.** Với `var a = Map.of("x", 1); var b = Map.copyOf(a);`, điều gì được bảo đảm?

**Đáp án:** `a.equals(b)` là `true`, `b` unmodifiable. **Không** có bảo đảm `a == b` hoặc `a != b`.

**Bài 2.** Tại sao JVM có thể tránh copy khi `source` là một Map factory-produced đã chốt?

**Đáp án:** Vì Map đó đã không cho sửa mapping, nên trả lại reference phù hợp vẫn có thể thỏa hợp đồng không phản ánh thay đổi cấu trúc nguồn. API không bắt cấp phát mới.

**Bài 3.** `Map.copyOf(new HashMap<>(Map.of("a",1)))` có yêu cầu phải cho phép put không?

**Đáp án:** Không. Dù source mutable, kết quả của `Map.copyOf` là unmodifiable Map, nên `put` bị từ chối.

**Bài 4.** Source mutable có `"a"→1`, tạo snapshot, rồi source `put("a",2)`. Snapshot có giá trị gì?

**Đáp án:** Vẫn là `1`, với điều kiện thao tác copy nguồn hoàn thành hợp lệ trước khi sửa; Map.copyOf không phải live view.

**Bài 5.** `Collections.unmodifiableMap(backing)` có luôn an toàn để lưu như snapshot cấu hình không?

**Đáp án:** Không, vì wrapper thường phản ánh cập nhật backing Map từ code giữ alias. Nếu cần snapshot độc lập về mapping, dùng `Map.copyOf` trên nguồn được đọc nhất quán.

**Bài 6.** Vì sao không được kết luận `Map.copyOf(view) == view` khi `view` là unmodifiable wrapper?

**Đáp án:** Đây không phải identity contract, và backing của wrapper vẫn có thể sửa qua alias; Map.copyOf phải giữ yêu cầu không phản ánh sửa mapping của source sau copy.

**Bài 7.** `Map.copyOf` có tạo bản sao riêng của một object `MutableValue` không?

**Đáp án:** Không. Value object giữ cùng tham chiếu; sửa field qua alias có thể hiện ra khi đọc từ Map result.

**Bài 8.** Nếu một key chứa trường dùng trong `hashCode` và trường đó bị sửa sau khi đưa vào Map, điều gì nguy hiểm?

**Đáp án:** Map có thể không còn lookup key nhất quán vì hash/equality biến đổi trong khi entry đã được lưu theo trạng thái cũ. Nên dùng key immutable.

**Bài 9.** `Map.copyOf` có trả thứ tự iteration của `LinkedHashMap` nguồn không?

**Đáp án:** Không được cam kết. Nếu order quan trọng, giữ danh sách có thứ tự riêng hoặc sắp xếp khóa/cặp dữ liệu khi xuất.

**Bài 10.** `Map.copyOf(Map.of())` có nhất thiết cấp phát Map mới không?

**Đáp án:** Không. Dạng rỗng có thể dùng lại instance unmodifiable; identity vẫn không phải API contract.

**Bài 11.** Khi nào nên dùng `new HashMap<>(source)` thay cho `Map.copyOf(source)`?

**Đáp án:** Khi cần một **Map mutable** để tiếp tục thêm/bớt mapping. `Map.copyOf` phù hợp khi cần công bố hoặc lưu Map không cho sửa cấu trúc.

**Bài 12.** Có thể đồng bộ nhiều luồng trên Map trả từ `Map.of`/`Map.copyOf` không?

**Đáp án:** Không nên, vì đối tượng factory-produced được mô tả là value-based, không có identity contract phù hợp để làm monitor. Dùng lock object do ứng dụng sở hữu hoặc các primitive đồng bộ.

**Bài 13.** `Map.copyOf` có thể hoạt động đúng khi source chứa key/value null không?

**Đáp án:** Không, nó ném `NullPointerException`. Validate/normalize null trước khi xây snapshot.

**Bài 14.** Một `HashMap` source bị writer sửa trong khi thread khác gọi `Map.copyOf`. Bản copy có là snapshot nguyên tử không?

**Đáp án:** Không có bảo đảm. Phải đồng bộ hóa mutate và copy hoặc dùng kiến trúc snapshot theo phiên bản.

**Bài 15.** Vì sao kiểm thử `assertSame(base, Map.copyOf(base))` không phù hợp với một thư viện Java đa nền tảng?

**Đáp án:** Vì tái sử dụng reference là optimization có thể thay đổi; tính đúng đắn của `Map.copyOf` không phụ thuộc identity. Test nội dung, unmodifiable, null handling và sự độc lập đối với lần sửa source sau copy.

**Bài 16.** Một record chứa `Map<String,String>` đã defensive-copy bằng `Map.copyOf`, có tự động safe publication giữa mọi thread chưa?

**Đáp án:** Bất biến dữ liệu và công bố tham chiếu là hai vấn đề. Record có state phù hợp để chia sẻ, nhưng các lần thay thế/chuyển state giữa thread phải tuân thủ cơ chế đồng bộ/handoff của Java Memory Model khi cần.

## 16. Checklist cho ứng dụng Java hiện đại

Khi dùng `Map.copyOf`, hãy xem xét:

1. Tôi muốn **unmodifiable mapping** hay một bản **mutable copy** để chỉnh sửa tiếp?
2. Source là factory immutable Map, mutable Map hay **unmodifiable view** có backing mutable?
3. Tôi có đang dựa vào `==`, class name hoặc một thứ tự iteration không được đặc tả?
4. Key/value có null không? Quy tắc validate dữ liệu nguồn đã rõ?
5. Key/value có mutable object lồng nhau không? Có cần deep copy/immutable DTO?
6. Mapping nguồn có được đọc **nhất quán** hay đang bị writer khác thay đổi?
7. Kết quả có được công bố cho thread khác bằng mechanism có happens-before rõ ràng không?
8. Độ lớn Map/tần suất tạo snapshot có cần profiling? Có đang copy trong hot loop không?
9. Test đã khẳng định **hành vi API** thay vì optimization nội bộ chưa?
10. Hợp đồng public API có mô tả rõ unmodifiable snapshot, null, thứ tự và thread safety không?

## 17. Tài liệu chính thức còn áp dụng

- [Java SE 17 – `Map.copyOf(Map)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): chữ ký Java 10, hợp đồng unmodifiable, từ chối null, không phản ánh sửa đổi nguồn và Implementation Note về khả năng không tạo bản sao mới.
- [Java SE 25 – `Map`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): đặc điểm unmodifiable Maps, value-based identity, iteration order và các factory hiện hành.
- [Oracle Java 25 – Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): phân biệt unmodifiable copy với view và lý do tái sử dụng nguồn khi đã không thể sửa.
- [Java SE 17 – `Collections.unmodifiableMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): wrapper read-only view có backing Map.
- [Java SE 17 – `HashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): Map mutable và hỗ trợ null khác với Map factory.
- [Java SE 17 – `AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): cách công bố/thay reference theo semantics bộ nhớ.
- [Java Language Specification – Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, happens-before và final-field semantics.
- [OpenJDK – JEP 269](https://openjdk.org/jeps/269): convenience factory methods trong Java 9; nền tảng cho các unmodifiable collection hiện đại.
- [OpenJDK – JEP 286](https://openjdk.org/jeps/286): `var` trong Java 10, được dùng ở ví dụ để tránh lặp kiểu cục bộ.

**Kết luận:** `Map.copyOf` có thể tiết kiệm allocation bằng cách **tái sử dụng một Map nguồn đã phù hợp**, nhưng đó là **quyền tối ưu của implementation**, không phải cam kết identity. Đối với caller, điều có giá trị lâu dài là Map kết quả **không thể sửa mapping**, **không phản ánh cập nhật mapping của nguồn sau khi copy** và không chứa key/value null. Khi cần dữ liệu thực sự bất biến và an toàn chia sẻ, hãy kiểm soát tiếp key/value mutable, tính nhất quán lúc đọc nguồn và safe publication giữa các luồng.
