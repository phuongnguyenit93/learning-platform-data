# Java 10 – Tính bất biến của cấu trúc so với an toàn công bố giữa các luồng

> **Phạm vi:** Java 10 → **Collection chỉ đọc** → **Tính bất biến của cấu trúc so với an toàn công bố giữa các luồng**. Bài học dùng Java 17+ để thực hành. `List.copyOf`, `Set.copyOf` và `Map.copyOf` được giới thiệu từ Java 10 và còn dùng trong Java hiện đại. `List.of` đã có từ Java 9; `record` đã trở thành tính năng chính thức ở Java 16. Những cơ chế của Java Memory Model (`happens-before`, `volatile`, `final`, `synchronized`, thread và `java.util.concurrent`) vẫn là nền tảng hiện hành.

## 1. Mục tiêu và kết luận cần nắm trước

Sau bài học, bạn có thể:

1. Phân biệt **không cho sửa cấu trúc collection**, **bất biến của phần tử**, **bất biến sâu của đối tượng** và **công bố an toàn giữa các luồng**.
2. Giải thích chính xác `List.copyOf`, `List.of` và `Collections.unmodifiableList`: đâu là snapshot, đâu là view, có phản ánh sửa đổi nguồn không.
3. Hiểu tại sao dữ liệu không bị sửa sau khi tạo **chưa thay thế** quy tắc về khả năng quan sát giữa các luồng trong Java Memory Model.
4. Chọn cơ chế công bố thích hợp: `volatile`, `AtomicReference`, khóa `synchronized`, `static final`, `Thread.start/join` và các tiện ích `java.util.concurrent`.
5. Thiết kế mẫu **snapshot bất biến + công bố an toàn**, xử lý đúng phần tử mutable và quyền sở hữu dữ liệu.
6. Tránh những nhầm lẫn: `final List` tự thread-safe, wrapper chỉ đọc tương đương snapshot, hoặc copy collection khi nguồn đang bị sửa đồng thời sẽ luôn nhất quán.

**Một câu ghi nhớ:** *“Không cho sửa” nói về các thao tác được phép trên dữ liệu; “công bố an toàn” nói về cách dữ liệu đã tạo trở nên được quan sát đúng giữa các luồng.* Cả hai cần được xem xét độc lập.

## 2. Bốn lớp bảo đảm khác nhau

| Thuộc tính | Câu hỏi nó trả lời | Ví dụ | Điều nó không tự bảo đảm |
| --- | --- | --- | --- |
| Biến không gán lại | Biến này có thể trỏ sang object khác không? | `final List<String> names = ...` | Object nằm trong biến có thể vẫn mutable |
| Collection unmodifiable | Có thể thêm, bớt, thay vị trí phần tử qua collection API không? | `List.of`, `List.copyOf` | Phần tử mutable có thể đổi; không quyết định cách công bố |
| Object immutable / immutable sâu | Trạng thái quan sát được có thể đổi sau khi xây dựng không? | `String`; record bảo vệ cả phần tử lồng nhau | Chưa mô tả toàn bộ cơ chế trao đổi tham chiếu giữa thread |
| Safe publication | Ghi trước khi công bố có được thread nhận nhìn thấy theo `happens-before` không? | `volatile` reference, lock, `Thread.start` | Không chặn các thao tác sửa **sau** khi công bố |

Đây là các tính chất có thể kết hợp:

- `final var list = new ArrayList<String>();`: **biến** không thể gán lại; ArrayList vẫn sửa được.
- `var list = List.of("A");`: object List không cho sửa; **biến** vẫn có thể gán tham chiếu List khác.
- `volatile List<String> current = List.of();`: reference được đọc/ghi theo quy tắc `volatile`; object được gán không tự trở nên bất biến nếu thực tế là mutable List.
- `List.copyOf(source)`: chốt cấu trúc từ nguồn thích hợp; việc đưa kết quả cho thread khác vẫn cần thiết kế cơ chế handoff rõ ràng.

Không suy ra thuộc tính của một object chỉ từ tên biến hoặc modifier trên tham chiếu.

## 3. “Bất biến cấu trúc” của collection nghĩa là gì?

Giả sử:

~~~java
var snapshot = java.util.List.of("A", "B");
~~~

Đối tượng List này **unmodifiable**: các thao tác như `snapshot.add("C")`, `snapshot.remove("A")` hoặc `snapshot.set(0, "X")` không được hỗ trợ; chúng ném `UnsupportedOperationException`.

Bất biến **cấu trúc collection** có nghĩa:

- Kích thước, vị trí và các tham chiếu phần tử không thể thay đổi bằng API chỉnh sửa của collection đó.
- Người nhận tham chiếu không thể dùng API List để thêm, xóa hoặc thay thế phần tử.
- Nó **không** hứa nội dung từng object phần tử đã được sao chép sâu, và cũng **không** nói dữ liệu đã chuyển tới thread khác qua một cơ chế giao tiếp nào.

Nếu phần tử thuộc kiểu bất biến như `String`, danh sách `List<String>` tạo bởi `List.of` hoặc từ bản sao đúng cách thường rất thuận tiện để chia sẻ. Nếu phần tử là object mutable, trạng thái quan sát qua danh sách vẫn có thể thay đổi dù bản thân List unmodifiable.

### 3.1. `List.of`, `Set.of` và `Map.of`

~~~java
var flags = java.util.List.of("read", "write");    // List<String>
var roles = java.util.Set.of("admin", "viewer");    // Set<String>
var limits = java.util.Map.of("read", 10);          // Map<String,Integer>
~~~

Các factory này có từ Java 9 và còn phù hợp trên JDK hiện đại. Chúng tạo collection unmodifiable; với List, thứ tự phần tử đầu vào được bảo toàn. Không dựa vào thứ tự duyệt của Set/Map do các factory này tạo, vì thứ tự ấy không được cam kết.

Factory không chấp nhận phần tử `null` (Map không chấp nhận key/value null). Với Set.of, **phần tử trùng** bị từ chối; Map.of từ chối key trùng. Nếu cần xử lý nguồn có dữ liệu null hoặc khóa trùng, nên kiểm tra và chuẩn hóa ở ranh giới đầu vào trước khi tạo collection.

### 3.2. `List.copyOf`, `Set.copyOf` và `Map.copyOf` từ Java 10

~~~java
var source = new java.util.ArrayList<>(java.util.List.of("A"));
var snapshot = java.util.List.copyOf(source);
source.add("B");

System.out.println(source);   // [A, B]
System.out.println(snapshot); // [A]
~~~

`List.copyOf(source)` tạo kết quả unmodifiable giữ các tham chiếu phần tử của source tại thời điểm copy. Khi `source` là collection mutable và sau đó thêm/bớt phần tử, thay đổi **cấu trúc** này không hiện ra trong `snapshot`.

Tương tự:

~~~java
var userIds = java.util.Set.copyOf(java.util.List.of("u1", "u2"));
var quotas = java.util.Map.copyOf(java.util.Map.of("basic", 5));
~~~

- `List.copyOf` giữ thứ tự duyệt của source; `Set.copyOf` không bảo đảm thứ tự và có thể gộp phần tử trùng của nguồn; `Map.copyOf` không bảo đảm thứ tự.
- Các phương thức không chấp nhận null trong dữ liệu theo các hợp đồng liên quan.
- Bản sao **không phải deep copy** của từng object phần tử; các phần tử vẫn là cùng tham chiếu.
- Nếu đầu vào đã là unmodifiable collection tương thích, một implementation có thể dùng lại object; không giả định `copyOf` luôn cấp phát object mới.
- `List.of`/`List.copyOf` tạo các đối tượng List thuộc dạng value-based; không dựa vào identity của chúng và **không dùng chính những object đó làm khóa `synchronized`**.

### 3.3. `Collections.unmodifiableList` là view trực tiếp

~~~java
var source = new java.util.ArrayList<>(java.util.List.of("A"));
var view = java.util.Collections.unmodifiableList(source);
var snapshot = java.util.List.copyOf(source);

source.add("B");
System.out.println(view);     // [A, B]
System.out.println(snapshot); // [A]
~~~

`view` từ chối gọi `add` qua wrapper, nhưng vẫn tham chiếu đến source. Một phần khác của chương trình giữ source và sửa source sẽ làm **giá trị nhìn thấy qua view thay đổi**. Với snapshot từ `List.copyOf`, thêm phần tử vào source mutable sau khi copy không làm thay đổi cấu trúc snapshot.

**Hệ quả với concurrency:** Nếu một thread đang đọc unmodifiable view và thread khác sửa backing `ArrayList` không có đồng bộ, wrapper không ngăn data race và có thể phát sinh kết quả không nhất quán hoặc ngoại lệ khi duyệt. “Không thể chỉnh sửa qua view” **không đồng nghĩa** “an toàn để đọc đồng thời khi backing collection đang bị sửa”.

## 4. Bất biến của phần tử khác bất biến cấu trúc

### 4.1. Phần tử mutable vẫn thay đổi qua alias

Đoạn sau minh họa object `Label` được sửa thông qua tham chiếu khác dù List đã chốt:

~~~java
final class Label {
    private String text;
    Label(String text) { this.text = text; }
    void rename(String value) { text = value; }
    @Override public String toString() { return text; }
}

var item = new Label("draft");
var labels = java.util.List.copyOf(java.util.List.of(item));
item.rename("edited");
System.out.println(labels); // [edited]
~~~

`labels.add(...)` không được phép, nhưng `item.rename(...)` vẫn chạy. Tập phần tử tham chiếu trong List không đổi; **trạng thái được quan sát** khi truy cập phần tử đã thay đổi. Đây là lý do không được gọi một `List<MutableType>` là “deep immutable” chỉ vì dùng `List.copyOf`.

### 4.2. Chọn kiểu phần tử immutable và sao chép phòng vệ

Một lớp/record bất biến nên giữ các điều kiện:

1. Trạng thái được xác định đầy đủ khi xây dựng.
2. Không có thao tác thay đổi trạng thái đã công bố.
3. Không rò rỉ alias tới mutable field qua constructor hoặc getter.
4. Nếu có collection/array lồng nhau, phải bảo vệ phần tử hoặc sao chép sâu khi cần.
5. Không cho `this` thoát khỏi constructor trước khi hoàn thành khởi tạo.

Ví dụ hiện đại (record là Java 16+, dùng được trên Java 17+):

~~~java
record Rule(String id, java.util.List<String> permissions) {
    Rule {
        java.util.Objects.requireNonNull(id);
        permissions = java.util.List.copyOf(permissions);
    }
}
~~~

Trong compact constructor của record, tham số `permissions` được thay bằng danh sách không cho sửa trước khi field được gán. Vì phần tử là `String` (immutable), caller sửa danh sách đầu vào về sau không ảnh hưởng trạng thái `Rule`.

~~~java
var input = new java.util.ArrayList<>(java.util.List.of("read"));
var rule = new Rule("r1", input);
input.add("write");
System.out.println(rule.permissions()); // [read]
~~~

Nếu record chứa `List<Label>` với `Label` mutable, chỉ `List.copyOf` **chưa đủ**; nên chuyển mỗi Label thành một immutable DTO/value object, hoặc tạo bản sao sâu có quy tắc rõ ràng.

### 4.3. Cần đặc biệt lưu ý array

`byte[]` và `String[]` vẫn có thể sửa nội dung dù field giữ array được đánh dấu `final`. Một class muốn bất biến khi sở hữu array primitive cần defensive copy lúc vào và lúc ra:

~~~java
public final class Packet {
    private final byte[] payload;

    public Packet(byte[] input) {
        payload = input.clone();
    }

    public byte[] payload() {
        return payload.clone();
    }
}
~~~

`clone()` của `byte[]` sao chép các byte; với array chứa object mutable, clone array vẫn chỉ là bản sao **nông của các tham chiếu**, cần đánh giá từng phần tử.

## 5. Công bố an toàn (`safe publication`) là vấn đề của Java Memory Model

Trong ứng dụng nhiều thread, việc thread A **tạo** một object rồi thread B **nhận tham chiếu** của nó là hoạt động khác với việc object đó có mutable hay không. Java Memory Model quy định khi nào một phép ghi của thread A được bảo đảm **hiển thị** cho phép đọc của thread B và cách các hoạt động được sắp xếp hợp lệ.

Khái niệm trung tâm là quan hệ **`happens-before` (HB)**:

- Nếu hành động ghi A *happens-before* hành động đọc B, Java Memory Model bảo đảm các quan hệ về thứ tự/khả năng nhìn thấy phù hợp.
- **Trong cùng thread**, thứ tự chương trình tạo ra quan hệ HB.
- Các hành động đồng bộ hóa (`synchronized`, `volatile`, `Thread.start()`, `Thread.join()` và các utility `java.util.concurrent`) có thể tạo quan hệ HB xuyên thread.
- **Không có HB phù hợp**, việc một thread đọc shared mutable state đang được thread khác ghi có thể là data race; không được viện dẫn “máy thường chạy đúng” để coi là bảo đảm.

Đối chiếu hai câu hỏi độc lập:

| Câu hỏi | Cơ chế phù hợp |
| --- | --- |
| “Không ai được thay đổi các phần tử/chính cấu trúc snapshot sau khi tạo?” | `List.copyOf` + immutable elements/defensive copying |
| “Sau khi thread A hoàn tất tạo snapshot, thread B có chắc quan sát trạng thái đã tạo không?” | Công bố qua `volatile`, lock, static initialization, thread/task handoff đúng hợp đồng, v.v. |

Một List unmodifiable được chuẩn bị xong giúp **giảm nhu cầu đồng bộ hóa cho việc đọc sau công bố**, nhưng không được dùng tính unmodifiable để biện minh cho việc truyền tham chiếu theo cách có data race hoặc thay đổi object thành phần ở bên ngoài.

### 5.1. Công bố không an toàn – ví dụ để phân tích, không dùng trong production

~~~java
class UnsafeHolder {
    java.util.List<String> value;

    void publish(java.util.List<String> incoming) {
        value = java.util.List.copyOf(incoming); // reference field thường
    }

    java.util.List<String> read() {
        return value;
    }
}
~~~

Nếu writer và reader đồng thời gọi các method trên mà **không** có ràng buộc HB/đồng bộ nào khác, field `value` là tham chiếu dùng chung được ghi/đọc không đồng bộ. Việc RHS là `List.copyOf` không tự tạo volatile write hoặc monitor release cho field.

Không nên viết demo “thực nghiệm” rồi khẳng định chắc chắn reader sẽ thấy `null`/dữ liệu cũ trong một lần chạy; race có kết quả phụ thuộc môi trường và JVM được phép tối ưu theo các quy tắc JMM. Điều chắc chắn là code này **không định nghĩa đúng một giao thức công bố có bảo đảm** cho việc cập nhật giữa các thread.

### 5.2. `final` không đồng nghĩa một giao thức công bố cho mọi thay đổi

~~~java
final class Holder {
    private final java.util.List<String> values;

    Holder(java.util.List<String> source) {
        values = java.util.List.copyOf(source);
    }

    java.util.List<String> values() { return values; }
}
~~~

`final` trên field và việc không để `this` thoát khỏi constructor giúp tận dụng **final-field semantics** của JMM: các field `final` được khởi tạo đúng có bảo đảm đặc biệt về khả năng quan sát trạng thái khởi tạo. Nhưng cần phân biệt:

- `final` khóa gán lại **field**, không khóa mutation của object mà field trỏ đến.
- Final-field semantics không thay thế một giao thức HB tổng quát khi bạn muốn **thay phiên bản** object giữa thread hoặc khi có shared mutable state.
- Nếu object có nhiều field không-final, cấu trúc lồng nhau mutable, hoặc bị công bố trước khi hoàn tất khởi tạo (ví dụ `this` thoát khỏi constructor), không thể chỉ dựa vào từ khóa `final` mà kết luận tất cả đều an toàn.
- Với ứng dụng nhiều thread, chọn một **cơ chế truyền/công bố rõ ràng**, kể cả khi object được thiết kế bất biến tốt.

## 6. Các cơ chế tạo quan hệ `happens-before` vẫn dùng hiện nay

| Cơ chế | Bảo đảm quan trọng | Giới hạn và lưu ý |
| --- | --- | --- |
| `volatile` field | Ghi vào volatile happens-before các lần đọc volatile **sau đó theo synchronization order** của cùng field | Không làm object trỏ tới thành immutable; không biến một chuỗi thao tác riêng lẻ thành transaction |
| `synchronized` | Unlock của monitor happens-before lock tiếp theo của cùng monitor | Các thread phải dùng **cùng monitor** theo quy ước |
| `Thread.start()` | Hành động trước `start()` happens-before hành động trong thread được start | Không bảo đảm những lần mutate sau `start()` mà không đồng bộ |
| `Thread.join()` thành công | Các hành động trong thread đã kết thúc happens-before các hành động sau `join()` ở thread chờ | Không tự biến shared mutable object thành concurrent collection |
| `static final` khởi tạo an toàn | Class initialization tạo cơ chế phối hợp để các thread thấy giá trị khởi tạo đúng | Field vẫn có thể trỏ đến mutable object; cần bảo vệ state |
| `AtomicReference.set/get` | Có hiệu ứng bộ nhớ tương tự thao tác volatile tương ứng | Cần CAS/update atomically khi nhiều writer phụ thuộc phiên bản cũ |
| `Executor`, `Future.get()` | Task handoff/result retrieval có các memory-consistency guarantees trong `java.util.concurrent` | Mỗi API có hợp đồng riêng, cần dùng đúng thao tác được quy định |
| Concurrent collection | Đưa/lấy phần tử theo các phương thức có bảo đảm HB được JavaDoc nêu | Thread-safe container không tự sửa race trong object phần tử |

Tài liệu chuẩn để tra cứu các quan hệ là **JLS `17.4–17.5** và JavaDoc của package `java.util.concurrent`.

### 6.1. `volatile`: công bố nguyên cả **tham chiếu tới snapshot**

~~~java
final class Registry {
    private volatile java.util.List<Rule> current = java.util.List.of();

    void publish(java.util.List<Rule> next) {
        current = java.util.List.copyOf(next);
    }

    java.util.List<Rule> snapshot() {
        return current;
    }
}
~~~

Bên viết phải hoàn tất việc xây dựng `next`/các `Rule` rồi mới gán `current`. Ghi vào field `volatile` tạo điểm công bố; thread khác đọc `current` bằng volatile read và thấy **phiên bản tham chiếu** phù hợp với thứ tự đồng bộ hóa. Việc đọc tham chiếu ổn định **không** bảo đảm trạng thái phần tử bị một thread khác sửa sau công bố.

Để một lần xử lý không trộn hai phiên bản:

~~~java
var localSnapshot = registry.snapshot();
for (var rule : localSnapshot) {
    // Dùng cùng một phiên bản trong toàn bộ thao tác
}
~~~

Nếu gọi `registry.snapshot()` nhiều lần trong một nghiệp vụ, mỗi lần đọc có thể trả một **phiên bản khác** khi writer đang publish; điều đó không phải lỗi của volatile. Đọc một lần vào biến cục bộ giúp giữ nhất quán phiên bản cho lượt xử lý ấy.

### 6.2. `synchronized`: đồng bộ cả quá trình cập nhật và lấy bản sao

~~~java
final class SynchronizedRegistry {
    private java.util.List<String> mutable = new java.util.ArrayList<>();

    synchronized void add(String value) {
        mutable.add(value);
    }

    synchronized java.util.List<String> snapshot() {
        return java.util.List.copyOf(mutable);
    }
}
~~~

Vì cả đọc và ghi nguồn dùng **cùng monitor của instance**, `snapshot()` không chạy đồng thời với `add()` bên trong lớp. Bản sao được tạo trong trạng thái nguồn được bảo vệ. Lớp vẫn cần tránh rò rỉ tham chiếu `mutable` cho caller khác có thể sửa ngoài khóa.

Điều này khác với gọi `List.copyOf(source)` khi một thread đang sửa `source`: chỉ việc tạo bản sao **không** làm toàn bộ quá trình duyệt/copy thành atomic transaction, không tự loại trừ data race. Với `ArrayList` bị sửa đồng thời, kết quả có thể thiếu nhất quán hoặc có exception; không dựa vào một loại exception cụ thể làm tín hiệu đồng bộ.

### 6.3. `Executor` và `Future`: handoff qua API có hợp đồng

~~~java
var executor = java.util.concurrent.Executors.newSingleThreadExecutor();
try {
    var future = executor.submit(() -> java.util.List.of("A", "B"));
    var result = future.get(); // List<String>
    System.out.println(result); // [A, B]
} finally {
    executor.shutdown();
}
~~~

Đây là **đoạn minh họa bên trong một phương thức có `throws Exception` hoặc xử lý exception phù hợp**. `ExecutorService.submit` và `Future.get` có các memory-consistency effects theo JavaDoc: thao tác trước khi submit HB task; thao tác của task HB các thao tác sau khi `get` lấy kết quả. Kết quả `List.of` không cho sửa cấu trúc, nhưng bảo đảm công bố đến từ **cơ chế handoff**, không đến từ tên phương thức `List.of`.

`ExecutorService` trong Java 17 không được dùng với `try-with-resources` theo giả định từ JDK mới; `shutdown()` trong `finally` là cách hợp lệ cho ví dụ Java 17.

## 7. Thiết kế snapshot có phiên bản với `AtomicReference`

`AtomicReference<T>` hữu ích khi các thread cần đọc/đổi tham chiếu theo các thao tác atomic có semantics bộ nhớ rõ ràng:

~~~java
final class RouteTable {
    private final java.util.concurrent.atomic.AtomicReference<java.util.List<String>>
            routes = new java.util.concurrent.atomic.AtomicReference<>(java.util.List.of());

    java.util.List<String> snapshot() {
        return routes.get();
    }

    void replace(java.util.List<String> input) {
        routes.set(java.util.List.copyOf(input));
    }
}
~~~

Đây cũng là chiến lược **copy-on-write ở mức ứng dụng**: tạo xong object mới rồi đổi reference duy nhất. Độc giả giữ snapshot cũ vẫn đọc phiên bản cũ; độc giả mới có thể đọc bản mới. Khi object/element immutable, các reader không cần lock chỉ để duyệt snapshot đã nhận.

### 7.1. Nhiều writer cùng thêm phần tử: tránh lost update

Cách **sai** nếu nhiều thread đồng thời đọc-đổi:

~~~java
var old = routes.get();
var next = new java.util.ArrayList<>(old);
next.add("new");
routes.set(java.util.List.copyOf(next)); // writer khác có thể overwrite phiên bản trung gian
~~~

Đọc và `set` tách rời không biến toàn bộ “đọc → tính → ghi” thành atomic; hai writer cùng thấy bản cũ có thể làm mất một cập nhật. Nếu cần update dựa trên phiên bản hiện có, dùng CAS hoặc `updateAndGet`:

~~~java
routes.updateAndGet(old -> {
    var next = new java.util.ArrayList<>(old);
    next.add("new");
    return java.util.List.copyOf(next);
});
~~~

**Quan trọng:** Hàm đưa cho `updateAndGet` có thể được thực thi nhiều lần khi cạnh tranh CAS; hãy giữ hàm thuần theo dữ liệu input, không ghi database, gửi email, phát event hoặc tạo tác dụng phụ không thể lặp ở bên trong. Với tập dữ liệu lớn hoặc ghi thường xuyên, việc copy toàn bộ list trên mỗi update có chi phí đáng kể; cân nhắc cấu trúc concurrent hoặc lock phù hợp.

### 7.2. Nhiều field liên quan: đóng gói vào cùng một immutable state

Nếu trạng thái nghiệp vụ gồm `version`, `rules` và `updatedAt` phải nhất quán với nhau, công bố **một** object state:

~~~java
record State(long version, java.util.List<String> rules) {
    State {
        rules = java.util.List.copyOf(rules);
    }
}
~~~

Đặt `volatile State current` hoặc `AtomicReference<State> current` thay vì ba field mutable cập nhật lần lượt. Một lần đọc reference `current` đem lại **cùng một phiên bản** của toàn bộ state; bất biến lồng nhau vẫn phải được đảm bảo. Nếu có nhiều writer, dùng đồng bộ/CAS để tránh lost update.

## 8. Ví dụ chạy được: cấu trúc unmodifiable, phần tử mutable và safe publication

Lưu toàn bộ đoạn sau vào **`PublicationVsImmutability.java`**. Chương trình chạy với JDK 17+ và thể hiện các tình huống theo thứ tự chắc chắn. `Rule` dùng record (Java 16+) và `List.copyOf` (Java 10); `Registry` công bố snapshot qua field volatile. `Thread.join()` được sử dụng **chỉ để khiến output kiểm thử có thứ tự ổn định**, đồng thời cũng tạo quan hệ happens-before; vì vậy ví dụ không phải benchmark hay bằng chứng thực nghiệm để “đo hiệu lực” của volatile riêng lẻ.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class PublicationVsImmutability {
    static final class MutableLabel {
        private String value;

        MutableLabel(String value) {
            this.value = value;
        }

        void rename(String next) {
            value = next;
        }

        @Override
        public String toString() {
            return value;
        }
    }

    record Rule(String id, List<String> permissions) {
        Rule {
            Objects.requireNonNull(id);
            permissions = List.copyOf(permissions);
        }
    }

    static final class Registry {
        private volatile List<Rule> current = List.of();

        void publish(List<Rule> next) {
            current = List.copyOf(next);
        }

        List<Rule> snapshot() {
            return current;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        var source = new ArrayList<>(List.of("A"));
        var view = Collections.unmodifiableList(source);
        var snapshot = List.copyOf(source);
        source.add("B");
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException exception) {
            System.out.println("snapshot-write=blocked");
        }

        var item = new MutableLabel("draft");
        var shallow = List.copyOf(List.of(item));
        item.rename("edited");
        System.out.println("mutable-element=" + shallow);

        var permissions = new ArrayList<>(List.of("read"));
        var rule = new Rule("r1", permissions);
        permissions.add("write");
        System.out.println("rule-permissions=" + rule.permissions());

        var registry = new Registry();
        var before = registry.snapshot();
        Thread publisher = new Thread(() -> registry.publish(List.of(rule)));
        publisher.start();
        publisher.join();
        var after = registry.snapshot();
        System.out.println("before-publish=" + before);
        System.out.println("after-publish=" + after);
        System.out.println("same-old-snapshot=" + (before == registry.snapshot()));
    }
}
~~~

Biên dịch từ thư mục chứa file:

~~~bash
javac --release 17 PublicationVsImmutability.java
java PublicationVsImmutability
~~~

**Stdout chính xác**:

~~~text
view=[A, B]
snapshot=[A]
snapshot-write=blocked
mutable-element=[edited]
rule-permissions=[read]
before-publish=[]
after-publish=[Rule[id=r1, permissions=[read]]]
same-old-snapshot=false
~~~

### 8.1. Giải thích theo từng dòng quan trọng

1. `view=[A, B]` vì unmodifiable view vẫn thấy thay đổi của source; `snapshot=[A]` vì snapshot tạo trước lúc source thêm `B`.
2. `snapshot-write=blocked` vì thao tác `snapshot.add` ném `UnsupportedOperationException`; không có phép thêm nào diễn ra.
3. `mutable-element=[edited]` chứng minh unmodifiable List **không đóng băng object phần tử** khi còn alias `item` để sửa.
4. `rule-permissions=[read]` vì constructor của record sao chép `List<String>` đầu vào. Sửa nguồn `permissions` sau khi tạo record không làm cấu trúc List đã lưu thay đổi.
5. `Registry.current` là tham chiếu volatile, `publish` tạo List snapshot trước khi gán. `Thread.start`/`join` trong demo bảo đảm việc thực thi writer hoàn tất trước khi main in giá trị mới.
6. `before-publish=[]` và `after-publish=[Rule[...]]` cho thấy reader nắm hai phiên bản collection riêng biệt, dù mỗi phiên bản đều unmodifiable.
7. `same-old-snapshot=false` ở đây là phép so sánh **giữa hai biến tham chiếu khác phiên bản**, không phải khuyến nghị so sánh identity của các object trả từ `List.of`/`List.copyOf`. Trong code sản xuất không nên dùng identity của value-based collections làm tín hiệu version; hãy dùng mã phiên bản nghiệp vụ tường minh nếu cần.

**Giới hạn:** Đây là ví dụ đơn giản có một writer và trình tự xác định bằng `join`. Nó không kiểm chứng mọi lịch trình concurrent; cũng không kết luận rằng tham chiếu volatile biến class `MutableLabel` thành thread-safe. Muốn bảo đảm deep immutable, mọi object được chia sẻ trong snapshot cũng phải tuân thủ thiết kế immutable hoặc có cơ chế đồng bộ riêng.

## 9. Tại sao `volatile List<T>` không thay thế collection/thread-safe algorithms?

### 9.1. `volatile` đặt trên tham chiếu, không áp dụng tự động cho `ArrayList.add`

~~~java
class RiskyRegistry {
    volatile java.util.List<String> names = new java.util.ArrayList<>();

    void add(String name) {
        names.add(name); // không có đồng bộ cho state của ArrayList
    }
}
~~~

Nhiều thread gọi `add` trên **cùng** `ArrayList` vẫn có thể race. `volatile` trên field chỉ quy định thao tác đọc/ghi **giá trị tham chiếu field**, không bao bọc logic cập nhật nội bộ của object. Cách xử lý là:

- Nếu nhiều **reader, ít writer** và muốn snapshot nhất quán: tạo bản mới bất biến rồi publish bằng `volatile`/`AtomicReference`.
- Nếu nhiều **writer cùng sửa**: dùng lock phù hợp, `ConcurrentHashMap` cho map, collection/thread-safe structure thích hợp hoặc chia sẻ state theo task, theo yêu cầu thực tế.
- Nếu nhiệm vụ chỉ cần một object immutable đã tạo xong: handoff qua API có HB, rồi tránh mutate đối tượng/element sau publish.

### 9.2. `CopyOnWriteArrayList` là lựa chọn khác với `List.copyOf`

`CopyOnWriteArrayList` là collection concurrent: các thao tác cập nhật tạo mảng mới phía sau và có chi phí sao chép; iterator cung cấp ảnh chụp ổn định tại thời điểm tạo iterator. Nó hợp khi đọc/duyệt nhiều, ghi ít, kích thước dữ liệu phù hợp.

Nhưng `CopyOnWriteArrayList` **không phải immutable List**: nó vẫn cho phép thêm/bớt phần tử qua API, chỉ là quản lý việc sửa an toàn cho các thao tác được cung cấp. `List.copyOf` tạo một kết quả không sửa được; chọn kết quả đó khi muốn **công bố phiên bản chỉ đọc**, không cần người nhận cập nhật collection.

### 9.3. `ConcurrentHashMap` bảo vệ map operations, không đóng băng giá trị

`ConcurrentHashMap` hỗ trợ concurrent access theo hợp đồng; nhưng nếu value là một object mutable và các thread truy cập/sửa field của value không có phối hợp, map không tự đồng bộ **các field của object value**. Đồng thời iterator trên concurrent map có thể là weakly consistent; không nên coi nó là immutable snapshot cố định. Muốn snapshot hoàn chỉnh theo thời điểm logic cụ thể, cần thiết kế cơ chế lấy ảnh phù hợp.

## 10. Copy từ nguồn đang được sửa đồng thời: một ranh giới dễ bỏ quên

Giả sử:

~~~java
List<String> source = new ArrayList<>();
// Thread A: source.add(...)
// Thread B: List.copyOf(source)
~~~

Khi thao tác `add` và `copyOf` có thể chạy cùng lúc mà không có đồng bộ, không có bảo đảm rằng `copyOf` tạo “ảnh tại đúng một thời điểm” của `ArrayList`. Có thể phát sinh data race, dữ liệu không nhất quán hoặc exception. **Không dùng `List.copyOf` như một cơ chế khóa tự động**.

Nếu source được mọi writer cập nhật dưới cùng một lock, hãy copy khi giữ lock đó:

~~~java
final class LockedSource {
    private final Object lock = new Object();
    private final List<String> source = new ArrayList<>();

    void add(String value) {
        synchronized (lock) {
            source.add(value);
        }
    }

    List<String> snapshot() {
        synchronized (lock) {
            return List.copyOf(source);
        }
    }
}
~~~

Đây là **đoạn minh họa trong một lớp có import `List` và `ArrayList`**, không phải chương trình độc lập. Vì writer và copier dùng cùng `lock`, cấu trúc nguồn không bị thay đổi trong lúc sao chép. Nếu caller có được tham chiếu nguồn thật để sửa bên ngoài lock, đảm bảo này bị phá vỡ; nên để field `private` và không expose mutable alias.

Đối với `Collections.synchronizedList`, khi duyệt/copy qua wrapper, JavaDoc yêu cầu người dùng đồng bộ thủ công đúng monitor của wrapper trong những thao tác iteration thích hợp. Tránh tạo wrapper mà vẫn giữ một đường sửa dữ liệu trực tiếp qua backing list không sử dụng cùng quy ước.

## 11. Quy tắc thiết kế dữ liệu từ input tới các thread đọc

Một pipeline lành mạnh có thể theo các bước:

~~~text
Nguồn dữ liệu thay đổi (thread xử lý input)
       │
       ▼
Kiểm tra/chuẩn hóa, xây dựng dữ liệu
       │
       ▼
Sao chép phòng vệ và chốt từng phần tử immutable
       │
       ▼
List.copyOf / Map.copyOf → snapshot cấu trúc
       │
       ▼
Công bố tham chiếu qua volatile / AtomicReference / lock / task handoff
       │
       ▼
Reader đọc một lần vào biến local và chỉ duyệt snapshot ấy
~~~

Cơ chế này tách biệt rõ ba trách nhiệm:

- **Builder:** thực hiện mutation trong phạm vi kiểm soát, không công bố object khi đang xây dựng.
- **Publisher:** chốt phiên bản và chuyển tham chiếu bằng cơ chế có memory-consistency guarantee.
- **Reader:** nhận tham chiếu đã publish, xem như read-only; không sửa object phần tử và không tự đoán khi nào writer cập nhật.

Khi writer tạo phiên bản mới, reader đã nhận phiên bản cũ có thể hoàn tất công việc ổn định. Nếu ứng dụng yêu cầu tất cả reader thấy cập nhật ngay lập tức, một mô hình snapshot eventual-read có thể chưa đáp ứng; cần xây thêm yêu cầu phối hợp, versioning hoặc synchronization tùy nghiệp vụ.

### 11.1. Kiểu dữ liệu phù hợp làm element snapshot

Nên cân nhắc:

- `String`, `Integer`, `BigDecimal`, `Instant`, `LocalDate`: các kiểu immutable theo hợp đồng thông thường.
- Record chỉ chứa các kiểu immutable, hoặc record có compact constructor tạo defensive copy của collection/array lồng nhau.
- Custom final class với field `private final` và không leak mutable state.
- Data transfer object tách biệt với entity mutable của ORM hoặc cache.

Không tự coi một JPA entity, object chứa `List`, array hay custom mutable class là immutable vì nó có getter mà không có setter. Reflection/framework và các alias cũng có thể tác động trạng thái; cần xem hợp đồng của kiểu và cách lifecycle hoạt động.

## 12. Phương án nào phù hợp với workload?

| Nhu cầu thực tế | Cách chọn gợi ý | Đổi lại |
| --- | --- | --- |
| Danh sách cấu hình nhỏ, khởi tạo một lần | `List.of` hoặc `List.copyOf` trong state bất biến; truyền qua safe handoff | Mọi thay đổi cần tạo phiên bản khác |
| Rất nhiều reader, ít writer, cần mỗi lượt đọc nhất quán | `volatile List<ImmutableElement>` + build snapshot + gán một lần | Copy mỗi lần cập nhật, có thể tốn memory/CPU |
| Nhiều writer thêm/sửa theo phiên bản cũ | `AtomicReference<State>` với CAS/update, hoặc lock | Phải kiểm soát contention/lost update |
| Danh sách listener thay đổi ít nhưng được duyệt rất nhiều | `CopyOnWriteArrayList` | Chi phí ghi/copy cao |
| Nhiều thread cập nhật map theo key | `ConcurrentHashMap` với API atomic phù hợp | Iterator không phải immutable snapshot; value cần an toàn riêng |
| Source mutable cần snapshot tại thời điểm nhất quán | Lock source khi update và copy; hoặc snapshot từ kho dữ liệu có transaction | Đồng bộ có chi phí và có thể gây chờ |
| Chạy task ở executor và nhận kết quả | `submit`/`Future.get` theo hợp đồng memory consistency | Cần xử lý hủy, lỗi, thời gian chờ và shutdown |

Không có một cấu trúc tối ưu tuyệt đối cho mọi ứng dụng. Chọn theo tỉ lệ đọc/ghi, kích thước snapshot, yêu cầu nhất quán, latency và rủi ro mutation ở element.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Vì sao sai | Sửa theo hướng |
| --- | --- | --- |
| “`Collections.unmodifiableList` là snapshot” | Nó thường là view của backing list | Chọn `List.copyOf` nếu muốn tách cấu trúc khỏi mutable source |
| “`List.copyOf` đã làm mọi phần tử immutable” | Nó sao chép tham chiếu phần tử, không deep copy | Dùng immutable element hoặc copy từng element |
| “Unmodifiable thì tự safe publication” | Không quy định HB cho một shared field bị ghi/đọc không đồng bộ | Dùng volatile/lock/task handoff phù hợp |
| “`final List` bảo đảm an toàn đồng thời” | Final reference vẫn có thể trỏ ArrayList mutable | Không sửa sau công bố hoặc đồng bộ mutation |
| “`volatile ArrayList` thì mọi `add` thread-safe” | Volatile không khóa internal state của List | Dùng concurrent collection hoặc immutable snapshot |
| “`List.copyOf` luôn tạo object mới” | Có thể tái sử dụng unmodifiable instance | Không dựa vào identity; dùng phiên bản logic khi cần |
| “Copy từ list đang bị sửa sẽ tự atomic” | Không có khóa/snapshot transaction được đảm bảo | Phối hợp update/copy dưới cùng lock |
| “Một thread in đúng dữ liệu là chứng minh hết data race” | Race phụ thuộc lịch trình, JIT, CPU | Lập luận bằng HB và kiểm thử mô hình |
| “AtomicReference.set đủ cho nhiều writer đọc-sửa-ghi” | Hai writer có thể overwrite nhau | Dùng compare-and-set hoặc updateAndGet với hàm không side effect |
| “Record luôn deep immutable” | Component có thể chứa mutable array/List/object | Defensive copy và immutable elements |
| “Đọc volatile nhiều lần luôn cùng phiên bản” | Writer có thể publish giữa hai lần đọc | Chốt một local snapshot cho toàn bộ lượt xử lý |
| “Đồng bộ hóa vào List.of là an toàn” | Các List value-based không cam kết identity phù hợp để khóa | Dùng lock object riêng/monitor được sở hữu rõ ràng |

### 13.1. Vì sao test nhiều thread không thay thế được thiết kế đúng?

Một stress test chạy hàng triệu lần mà chưa thấy lỗi **không chứng minh** absence of data race. JMM cho phép nhiều lịch trình, khác nhau theo CPU, JIT, độ nóng chương trình và cách thực thi. Kiểm thử nên tập trung vào invariant: mỗi snapshot có cùng version, reader không thấy collection bị mutate ngoài ý muốn, nhiều writer không mất cập nhật, cancellation không để lại state dang dở.

Chất lượng của giải pháp đến từ **lập luận về happens-before + ownership/mutability + atomicity**, rồi dùng test để phát hiện lỗi implementation. Khi cần kiểm tra memory-model litmus test chuyên sâu, có thể tham khảo công cụ jcstress thuộc hệ sinh thái OpenJDK; đây là công cụ kiểm thử chuyên dụng, không thay thế JLS.

## 14. Bài tập tự kiểm tra có đáp án

**Bài 1.** `var source = new ArrayList<>(List.of("A")); var view = Collections.unmodifiableList(source); source.add("B");`. In `view` được gì?

**Đáp án:** `[A, B]`. Wrapper là view; source thay đổi thì dữ liệu quan sát qua view thay đổi.

**Bài 2.** Thay `view` bằng `List.copyOf(source)` trước khi `source.add("B")`, kết quả là gì?

**Đáp án:** `[A]`. Snapshot không phản ánh thay đổi **cấu trúc** của mutable source sau khi copy.

**Bài 3.** `var list = List.of(new MutableLabel("A"));`. Có thể gọi `list.get(0).rename("B")` không?

**Đáp án:** Có nếu method `rename` được truy cập hợp lệ và `MutableLabel` cho phép sửa. Danh sách không cho thêm/bớt phần tử, còn object phần tử vẫn mutable.

**Bài 4.** Trường hợp nào đủ để kết luận List có thể đọc an toàn nhiều thread nếu reader không sửa: `List.copyOf(List<MutableLabel>)` hay `List.copyOf(List<String>)`?

**Đáp án:** Với `List<String>` đã xây dựng đầy đủ và **được handoff an toàn**, cả cấu trúc List lẫn phần tử String đều không thay đổi, nên việc đọc cùng snapshot rất thuận lợi. Với `MutableLabel` còn bị thread khác sửa không đồng bộ, chỉ `copyOf` chưa đủ để đảm bảo đọc an toàn.

**Bài 5.** Tại sao `volatile List<String> names = new ArrayList<>()` không cho phép nhiều thread cùng `names.add(...)` an toàn?

**Đáp án:** Volatile trên **tham chiếu field** không biến các phép ghi vào state nội bộ ArrayList thành atomic hoặc synchronized.

**Bài 6.** Writer đã tạo `List.copyOf(input)` rồi gán vào field thường, reader ở thread khác liên tục đọc field. Có chắc reader sẽ quan sát lần cập nhật mới theo ý định không?

**Đáp án:** Không có đảm bảo HB nếu không có synchronization khác. Dùng volatile/lock/atomic hoặc một cơ chế handoff có HB phù hợp.

**Bài 7.** Điều gì sai nếu gọi `List.copyOf(arrayList)` cùng lúc với thread khác liên tục thêm/bớt `arrayList` mà không khóa?

**Đáp án:** Không có bảo đảm snapshot atomic và thiếu đồng bộ khi đọc/ghi source. Cần phối hợp việc copy với mutation nguồn, hoặc dùng cấu trúc snapshot phù hợp.

**Bài 8.** `private final List<String> names = new ArrayList<>();` có khiến object chứa field đó immutable không?

**Đáp án:** Không. Field final không được gán lại, nhưng nội dung ArrayList vẫn sửa được; nếu getter hoặc alias bên ngoài thao tác trên nó, trạng thái được quan sát có thể thay đổi.

**Bài 9.** Với `volatile List<String> current`, reader gọi `current` hai lần trong một nghiệp vụ. Có nhất thiết hai lần cùng một phiên bản không?

**Đáp án:** Không. Writer có thể thay tham chiếu giữa hai lần đọc. Đọc một lần vào local `var snapshot = current;` rồi dùng `snapshot` cho toàn bộ nghiệp vụ.

**Bài 10.** Tại sao `AtomicReference.set` có thể làm mất cập nhật trong mô hình hai writer cùng đọc rồi thêm một phần tử?

**Đáp án:** Hai writer có thể đều xây bản mới từ một phiên bản cũ, rồi writer sau ghi đè kết quả của writer trước. Dùng CAS/`updateAndGet` có logic retry đúng, hoặc khóa.

**Bài 11.** `Thread.join()` có vai trò gì trong chương trình chạy thử?

**Đáp án:** Nó đợi writer kết thúc, làm stdout có thứ tự ổn định và cung cấp quan hệ HB với main thread. Vì vậy demo không cô lập tác dụng của `volatile`; đúng ra phải dựa vào tài liệu JMM để hiểu từng cơ chế.

**Bài 12.** `CopyOnWriteArrayList` có giống một `List.copyOf` không?

**Đáp án:** Không. `CopyOnWriteArrayList` là collection mutable với cơ chế hỗ trợ concurrent operations và iterator snapshot; `List.copyOf` là collection không cho sửa. Chi phí và hợp đồng khác nhau.

**Bài 13.** Một record có component `byte[]` và field cuối cùng là final. Record ấy đã immutable sâu chưa?

**Đáp án:** Chưa. Array là mutable; cần copy khi nhận và không trả trực tiếp internal array nếu muốn bất biến dữ liệu.

**Bài 14.** Khi nhiều thread chỉ đọc một `List<String>` đã được tạo xong, cần giữ lock trên mỗi lần đọc không?

**Đáp án:** Nếu List có cấu trúc không đổi, phần tử String immutable, object được công bố an toàn và không có mutation nào khác, reader có thể đọc snapshot mà không cần khóa cho từng thao tác. Nếu List hoặc phần tử có thể bị sửa đồng thời, cần thiết kế lại hoặc thêm đồng bộ.

## 15. Checklist để đưa vào review code

Trước khi tuyên bố một collection “chỉ đọc và an toàn chia sẻ”, hãy hỏi:

1. **Cấu trúc:** Collection có thực sự unmodifiable, hay chỉ là wrapper view của source mutable?
2. **Phần tử:** Các phần tử có immutable sâu không? Có alias nào còn được mutate?
3. **Builder:** Tất cả field/element đã được khởi tạo đầy đủ trước khi publish chưa? Có bị leak `this` khi đang xây dựng?
4. **Snapshot:** Nếu copy từ collection mutable, ai bảo đảm source không đổi đồng thời trong lúc copy?
5. **Publication:** Cơ chế HB nào chuyển tham chiếu đến reader? Volatile, lock, static init, task handoff, Future?
6. **Phiên bản:** Reader có cần chốt local snapshot một lần cho mỗi transaction/operation không?
7. **Writer:** Có nhiều writer không? Nếu có, cách ngăn lost update là gì?
8. **Hợp đồng API:** Caller được sửa kết quả không? Snapshot hay live view? Thứ tự, null, thread safety được mô tả ra sao?
9. **Hiệu năng:** Kích thước snapshot, tần suất cập nhật, GC/allocations và memory footprint có phù hợp không?
10. **Kiểm thử:** Đã kiểm tra cả output chức năng và các invariant đồng thời thay vì chỉ tìm một kết quả race ngẫu nhiên?

## 16. Tài liệu chính thức còn áp dụng

1. [Java SE 25 API – `List`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): đặc điểm unmodifiable của `List.of`/`List.copyOf`, null, element mutability và value-based identity.
2. [Oracle – Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): snapshot vs view, copyOf, đặc tính thread safety khi elements immutable.
3. [Java Language Specification – Threads and Locks, `17.4 và `17.5`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html): `happens-before`, `synchronizes-with` và final-field semantics.
4. [Java SE API – Package `java.util.concurrent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html): memory consistency effects của executor, Future và concurrent collections.
5. [Java SE API – `AtomicReference`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): update atomically, get/set và compare-and-set.
6. [Java SE API – `CopyOnWriteArrayList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): snapshot-style iteration và chi phí copy khi ghi.
7. [Java SE API – `Collections`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html): `unmodifiableList` và `synchronizedList`.
8. [OpenJDK – JEP 286](https://openjdk.org/jeps/286): `var` được đưa vào Java 10; tính năng cú pháp này không ảnh hưởng Java Memory Model hay đặc tính đồng bộ.

**Kết luận bài học:** `List.copyOf` giúp bảo vệ **cấu trúc** của snapshot, còn immutable elements và defensive copying giúp bảo vệ **trạng thái sâu**. Khi nhiều thread chia sẻ dữ liệu, hãy dùng một cơ chế **công bố có quan hệ happens-before** và tránh mutation không được kiểm soát sau khi publish. Chỉ khi các điều kiện đó phối hợp đúng thì thiết kế collection chỉ đọc mới đáng tin trong ứng dụng đồng thời.
