# Trả collection chỉ đọc từ API — thiết kế dữ liệu an toàn với Java 10+

## 1. Bài toán: bảo vệ trạng thái bên trong nhưng vẫn cho caller đọc dữ liệu

Một service thường lưu dữ liệu trong `List`, `Set` hoặc `Map` có thể chỉnh sửa để phục vụ nghiệp vụ. Nếu phương thức API trả **thẳng collection đang lưu nội bộ**, mã bên ngoài có thể sửa trạng thái mà không đi qua quy tắc của service:

```java
class UnsafeCatalog {
    private final java.util.List<String> names =
            new java.util.ArrayList<>();

    public java.util.List<String> names() {
        return names; // Làm lộ mutable collection nội bộ.
    }
}
```

Một caller có thể gọi `catalog.names().clear()` hoặc `add(...)` và làm thay đổi dữ liệu mà service đang quản lý. Việc field được khai báo `private final` **không giải quyết vấn đề**: `private` chỉ giới hạn truy cập trực tiếp vào field; `final` chỉ cấm gán lại tham chiếu field. Object `ArrayList` vẫn mutable và tham chiếu đã bị rò rỉ qua phương thức.

Mục tiêu của **API trả collection chỉ đọc** là bảo đảm: người gọi được xem dữ liệu, tìm kiếm và duyệt, nhưng **không thể thay đổi cấu trúc collection trả về thông qua API collection ấy**. Từ Java 10, các hàm `List.copyOf`, `Set.copyOf` và `Map.copyOf` cho phép tạo snapshot *unmodifiable* với cú pháp rõ ràng.

Bài học này trả lời:

- Cần trả `List.copyOf`, `Set.copyOf` hay `Map.copyOf` khi nào?
- Khác biệt giữa **snapshot unmodifiable** và **unmodifiable view** là gì?
- Vì sao một collection “không sửa được” vẫn có thể chứa object mutable?
- Làm sao tạo API an toàn với DTO/record và defensive copy?
- Những ràng buộc của `null`, phần tử trùng, thứ tự, hiệu năng và concurrency cần được công bố như thế nào?
- Làm sao kiểm thử **hợp đồng API** mà không phụ thuộc lớp triển khai nội bộ?

Tất cả quy tắc chính về `copyOf` là kiến thức **còn áp dụng trong Java hiện đại**. Chương trình đầy đủ bên dưới dùng Java 17 để minh họa `record`; bản thân các phương thức `copyOf` đã có từ **Java 10**.

## 2. Phân biệt “kiểu trả về” với “khả năng được sửa”

Chữ ký:

```java
public java.util.List<ProductView> products()
```

không tự nói rằng caller có thể `add` hay `set`. `List<E>` là interface chứa cả các phương thức đọc và các *optional mutator*. Java cho phép implementation của `List` từ chối các phương thức sửa bằng `UnsupportedOperationException`.

Ngược lại, chỉ khai báo kiểu `List` hoặc `Collection`, hoặc dùng `final`, **không làm object bất biến**:

```java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("Ada"); // Hợp lệ.

final java.util.List<String> reference = names;
reference.add("Grace"); // Vẫn hợp lệ: final không khóa object.
```

Muốn một API có hợp đồng chỉ đọc, hãy **trả một object mà các mutator thực sự không được hỗ trợ** và xác định rõ nguồn/element có thể thay đổi ở đâu.

Thuật ngữ cần nhớ:

| Thuật ngữ | Ý nghĩa | Có được `copyOf` tự bảo đảm? |
| --- | --- | --- |
| **Unmodifiable collection** | Không cho sửa qua mutator của collection | Có |
| **Snapshot cấu trúc** | Thay đổi thêm/xóa/đổi tham chiếu ở source về sau không phản ánh vào kết quả | Có, với nguồn mutable thông thường |
| **Unmodifiable view** | Caller không sửa qua view nhưng vẫn thấy thay đổi ở backing collection | Không phải hành vi của `copyOf`; là wrapper `Collections.unmodifiable*` |
| **Shallow copy** | Sao chép các tham chiếu phần tử, không clone sâu object | Có, đây là giới hạn cần biết |
| **Deep immutable graph** | Không thể làm thay đổi trạng thái bất kỳ object con nào có thể quan sát | Không; cần thiết kế thêm |

Vì vậy, không đồng nhất **read-only reference**, **unmodifiable collection** và **immutable dữ liệu ở mọi cấp**.

## 3. Cách tiêu chuẩn từ Java 10: `List.copyOf`, `Set.copyOf`, `Map.copyOf`

Với một state mutable:

```java
private final java.util.List<ProductView> products =
        new java.util.ArrayList<>();

private final java.util.Set<String> categories =
        new java.util.HashSet<>();

private final java.util.Map<Long, ProductView> indexed =
        new java.util.HashMap<>();
```

API có thể trả:

```java
public java.util.List<ProductView> products() {
    return java.util.List.copyOf(products);
}

public java.util.Set<String> categories() {
    return java.util.Set.copyOf(categories);
}

public java.util.Map<Long, ProductView> productsById() {
    return java.util.Map.copyOf(indexed);
}
```

Hai đoạn trên là **các thành viên cần đặt trong class có định nghĩa `ProductView`**, không phải chương trình độc lập; một file chạy hoàn chỉnh xuất hiện ở mục 12.

### Các hợp đồng quan trọng

- **`List.copyOf(Collection)`:** tạo list unmodifiable, giữ phần tử theo iteration order của nguồn. List giữ phần tử lặp lại; không tự distinct, không tự sort.
- **`Set.copyOf(Collection)`:** tạo set unmodifiable, loại các phần tử trùng theo quan hệ bằng nhau. Không bảo đảm iteration order và không bảo đảm giữ bản sao “đầu tiên” nếu nhiều object khác nhau nhưng `equals()` bằng nhau.
- **`Map.copyOf(Map)`:** tạo map unmodifiable với các cặp key–value của nguồn. Không cam kết iteration order; không deep-copy key/value.

Cả ba yêu cầu **nguồn không `null` và không chứa phần tử/key/value `null`**. Trường hợp không hợp lệ ném `NullPointerException`.

Mọi mutator thực sự trên kết quả (ví dụ `add`, `clear`, `set`, `put`, `remove`, `replace`, `compute`) đều không được hỗ trợ. Chỉ dùng các phương thức đọc như `get`, `contains`, `size`, duyệt và `stream`.

### Cách gọi khi có ít giá trị cố định

Khi các phần tử đã biết ở lúc viết mã, có thể dùng `List.of(...)`, `Set.of(...)` và `Map.of(...)`, đã được giới thiệu từ Java 9. Chúng tạo collection unmodifiable trực tiếp:

```java
var levels = java.util.List.of("BEGINNER", "ADVANCED");
var enabled = java.util.Set.of("web", "api");
var limits = java.util.Map.of("free", 10, "pro", 100);
```

Khác biệt: `Set.of("A", "A")` ném `IllegalArgumentException` do truyền hai phần tử bằng nhau, còn `Set.copyOf(List.of("A", "A"))` tạo tập chỉ có một phần tử. Tương tự, `Map.of` từ chối hai key trùng, trong khi nguồn của `Map.copyOf` vốn đã là một `Map`, không thể có hai key tương đương cùng tồn tại theo hợp đồng Map.

## 4. Snapshot: caller không thể thay đổi kết quả và không thấy thay đổi cấu trúc nguồn về sau

```java
var source = new java.util.ArrayList<>(
        java.util.List.of("A", "B"));
var snapshot = java.util.List.copyOf(source);

source.add("C");

System.out.println(source);   // [A, B, C]
System.out.println(snapshot); // [A, B]
```

`snapshot` chứa hai phần tử đã được chốt ở thời điểm copy. `source.add(...)` sau đó không làm snapshot có thêm phần tử. Điều này thích hợp khi method muốn thể hiện **trạng thái tại thời điểm gọi**, không phải một cửa sổ luôn cập nhật.

Tương tự với map:

```java
var source = new java.util.HashMap<String, Integer>();
source.put("A", 1);

var snapshot = java.util.Map.copyOf(source);
source.put("B", 2);

System.out.println(snapshot.size());       // 1
System.out.println(snapshot.containsKey("B")); // false
```

Cả list và map ở đây **không cho caller ghi đè** và **không nhận thêm thay đổi cấu trúc từ nguồn**.

**Điểm tinh tế:** các API `copyOf` có thể **tái sử dụng instance** khi đầu vào đã là collection unmodifiable thích hợp. Không nên kết luận “`copyOf` luôn cấp phát object mới” hoặc dùng `source == snapshot` để kiểm tra mức độ bảo vệ. Điều đáng tin cậy là **hợp đồng hành vi**, không phải danh tính object.

Một caller muốn dữ liệu mới phải **gọi API thêm lần nữa** hoặc dùng cơ chế cập nhật do service định nghĩa. Snapshot cũ không phải một live feed.

## 5. Unmodifiable view khác snapshot: chọn đúng khi thiết kế API

Trước Java 10 và vẫn còn hữu ích trong những ngữ cảnh phù hợp, Java có wrapper như `Collections.unmodifiableList(source)`. Tuy nhiên, wrapper này **là view lên danh sách gốc**:

```java
var source = new java.util.ArrayList<>(
        java.util.List.of("A"));

var view = java.util.Collections.unmodifiableList(source);
var snapshot = java.util.List.copyOf(source);

source.add("B");

System.out.println(view);     // [A, B]
System.out.println(snapshot); // [A]
```

- Caller gọi `view.add("C")` sẽ gặp `UnsupportedOperationException`.
- Nhưng chủ sở hữu nguồn vẫn gọi được `source.add("B")` và `view` **nhìn thấy** thay đổi đó.
- `snapshot` của `List.copyOf` không thay đổi cấu trúc tương ứng.

Với `Set` và `Map`, cũng có `Collections.unmodifiableSet(source)` và `Collections.unmodifiableMap(source)` theo nguyên tắc view tương tự.

Đừng suy luận wrapper unmodifiable **tự làm bản sao**; nếu mục tiêu là tách biệt khỏi thay đổi nguồn, dùng `List.copyOf`/`Set.copyOf`/`Map.copyOf` hoặc kết hợp copy mutable + wrapper trong trường hợp có yêu cầu `null` khác.

### Khi nào view có ích?

Nếu đặc tả API thật sự là **“cửa sổ chỉ đọc luôn phản ánh trạng thái hiện hành của nguồn”**, view có thể phù hợp. Nhưng cần kiểm soát:

- Ai sở hữu tham chiếu mutable backing collection.
- Cơ chế đồng bộ khi nhiều thread đọc/ghi.
- Việc duyệt view trong lúc backing collection thay đổi có thể tạo lỗi hoặc kết quả không nhất quán.
- Thời gian tồn tại của view so với source.

Không dùng view chỉ vì cú pháp trông ngắn. Nếu API công bố snapshot mà trả live view, người dùng có thể nhìn thấy dữ liệu thay đổi ngoài ý muốn.

## 6. Bảo vệ tại ranh giới API: phòng vệ cả đầu vào lẫn đầu ra

Chỉ xử lý tại getter đôi khi chưa đủ. Ví dụ, service lưu trực tiếp list mà caller đưa vào qua constructor:

```java
final class UnsafeSettings {
    private final java.util.List<String> options;

    UnsafeSettings(java.util.List<String> options) {
        this.options = options; // Giữ nguyên tham chiếu mutable từ caller.
    }

    java.util.List<String> options() {
        return java.util.List.copyOf(options);
    }
}
```

Getter có snapshot, nhưng caller cũ vẫn có thể sửa `options` qua list đưa vào constructor. Nếu service kỳ vọng cấu hình không đổi sau khi tạo, việc lưu nguyên tham chiếu đầu vào là **aliasing bug**.

Một thiết kế phòng vệ:

```java
final class SafeSettings {
    private final java.util.List<String> options;

    SafeSettings(java.util.List<String> options) {
        this.options = java.util.List.copyOf(options);
    }

    java.util.List<String> options() {
        return options; // Đã là unmodifiable snapshot từ constructor.
    }
}
```

Ở đây service:

1. Copy ở **đầu vào** để tách khỏi những thay đổi về sau của list caller.
2. Giữ collection unmodifiable trong field riêng.
3. Có thể trả chính field khi phần tử (ở đây `String`) là immutable và state không bao giờ phải đổi.

Nếu service cần quản lý state mutable theo thời gian, giữ một list mutable nội bộ và **copy lúc xuất bản** là lựa chọn phù hợp. Đừng tạo một snapshot cố định rồi kỳ vọng nó tự cập nhật.

## 7. Shallow copy: collection chỉ đọc không đóng băng object phần tử

Đây là ranh giới quan trọng nhất khi xuất bản collection đối tượng miền nghiệp vụ (*domain objects*).

Giả sử:

```java
final class MutableProduct {
    String name;
    MutableProduct(String name) { this.name = name; }
}

var product = new MutableProduct("Draft");
var published = java.util.List.copyOf(
        java.util.List.of(product));

product.name = "Approved";
System.out.println(published.get(0).name); // Approved
```

Chỉ có **tham chiếu phần tử ở index 0** được giữ trong snapshot. Object `MutableProduct` vẫn là object mutable đó; caller hoặc nguồn khác có thể thay đổi nó.

Phân biệt:

- `published.set(0, anotherProduct)`: **không được**, vì muốn thay phần tử trong list.
- `published.get(0).name = "Changed"`: **có thể được** nếu field truy cập được và mutable, vì đang sửa **object ở bên trong**.
- `List.copyOf` không tự gọi `clone()`, constructor copy hay serializing object để tạo bản sao sâu.

Tương tự với `Map.copyOf`: value mutable có thể đổi trạng thái, còn key mutable có `equals()/hashCode()` phụ thuộc field thay đổi có thể làm tra cứu mất tính nhất quán. Hợp đồng `Map` không bảo đảm hành vi hợp lệ nếu key bị thay đổi theo cách ảnh hưởng đến so sánh `equals()` trong khi nó đang nằm trong map.

Vì vậy **“return unmodifiable collection” chưa đủ để hứa “deep immutable data”**. Nếu caller không được sửa dữ liệu miền nghiệp vụ, hãy sử dụng các phần tử immutable/DTO chỉ đọc hoặc tạo defensive copy cho chúng.

## 8. DTO bất biến và `record`: bảo vệ cả thành phần collection

Từ Java 16, `record` là một công cụ phù hợp để mô tả dữ liệu trả về. Ví dụ trên Java 17:

```java
record ProductView(long id, String name, java.util.List<String> labels) {
    ProductView {
        java.util.Objects.requireNonNull(name);
        labels = java.util.List.copyOf(labels);
    }
}
```

Điểm quan trọng không chỉ là `record`:

- `id` là primitive, `name` là `String` immutable.
- `labels` có kiểu `List<String>` và được **defensive-copy** trong compact constructor.
- Dù caller đưa vào một `ArrayList` rồi chỉnh sửa nó về sau, nội dung `ProductView.labels()` không thay đổi theo list nguồn.
- Vì các phần tử label là `String` immutable, không còn trạng thái mutable lồng sâu trong ví dụ này.

Ví dụ:

```java
var external = new java.util.ArrayList<>(
        java.util.List.of("java", "api"));

var product = new ProductView(1L, "Guide", external);
external.add("hijacked");

System.out.println(product.labels()); // [java, api]
```

Nếu thiếu dòng `labels = List.copyOf(labels);`, `record` **không tự deep-copy** list, bởi record chỉ cố định tham chiếu tới thành phần đó. Cần thiết kế phòng vệ theo chiều sâu phù hợp với kiểu phần tử thực tế.

Với Java 10 không có cú pháp `record`; có thể dùng `final class` với field `private final`, constructor kiểm tra đầu vào và defensive copy. Đó vẫn là thiết kế hợp lệ trong Java 17/21/25; không phải một cơ chế bị loại bỏ.

## 9. Phân biệt thiết kế trả List, Set và Map

Mỗi loại collection diễn đạt một **hợp đồng dữ liệu** khác nhau, độc lập với chuyện có thể sửa hay không:

| Kiểu trả | Nên dùng khi | Điều caller có thể dựa vào | Cẩn trọng |
| --- | --- | --- | --- |
| `List<T>` | Cần thứ tự và có thể giữ phần tử trùng | Thứ tự đã chốt trong list, truy cập theo index | `List.copyOf` không nhận phần tử null |
| `Set<T>` | Cần tính duy nhất của phần tử | Không có hai phần tử bằng nhau theo hợp đồng Set | `Set.copyOf` không hứa iteration order |
| `Map<K,V>` | Cần ánh xạ từ khóa sang giá trị | Tra cứu bằng key và quan hệ key–value | Key phải có danh tính/`equals()/hashCode()` ổn định |

### List: thứ tự có ý nghĩa

Nếu API trả lịch sử sự kiện theo thời gian, việc chọn `List.copyOf(events)` phù hợp khi service đã đưa sự kiện vào đúng thứ tự. `List.copyOf` **không tự sort**. Cần xác định quy tắc sắp xếp trước khi xuất bản.

### Set: không có thứ tự ngầm

`Set.copyOf(List.of("B", "A", "B"))` cho tập hai phần tử, nhưng không bảo đảm kết quả duyệt luôn `A` rồi `B`. Nếu API cần trật tự hiển thị ổn định, trả **List đã sorted** hoặc công bố một abstraction có thứ tự phù hợp; đừng chuyển sang Set chỉ vì muốn “loại trùng” mà đánh mất yêu cầu order.

Nếu nhiều object khác nhau nhưng được xem là bằng nhau, `Set.copyOf` có thể giữ một đại diện tùy ý. Khi bản đại diện nào được giữ có ý nghĩa nghiệp vụ, hãy xử lý lựa chọn trước khi xây dựng set.

### Map: cần key ổn định

Đừng dùng toàn bộ entity mutable làm key nếu `equals()/hashCode()` dựa vào trạng thái có thể thay đổi. Ưu tiên khóa kiểu `String` hoặc value object bất biến; nếu value mutable, hãy cân nhắc tạo DTO/value immutable riêng khi publish.

Không dựa vào việc `Map.copyOf` phải giữ iteration order của `LinkedHashMap`. Nếu order cần là một phần contract, có thể trả **List các entry DTO đã sắp xếp** hoặc một abstraction có thứ tự và phòng vệ cụ thể.

## 10. Null, duplicate và exception: đừng thay đổi API mà không xét hợp đồng

### Null trong `copyOf`

Các hàm `List.copyOf` và `Set.copyOf` từ chối phần tử `null`; `Map.copyOf` từ chối key hoặc value `null`. Nguồn `null` cũng không hợp lệ:

```java
var input = new java.util.ArrayList<String>();
input.add(null);

// var result = java.util.List.copyOf(input);
// Ném NullPointerException khi chạy.
```

Khi service trước đây trả danh sách có null như một sentinel, việc chuyển thẳng sang `List.copyOf` không chỉ thay đổi khả năng sửa mà còn **thay đổi chính sách dữ liệu**. Cần quyết định rõ: validate và trả lỗi, lọc (nếu nghiệp vụ cho phép), hoặc biểu diễn giá trị vắng mặt bằng kiểu dữ liệu phù hợp.

Không âm thầm loại bỏ null vì “copyOf không thích null” nếu null là một phần hợp đồng cũ.

### Duplicate

- `List.copyOf` cho phép các phần tử trùng, giữ số lượng và thứ tự theo nguồn.
- `Set.copyOf` loại các phần tử bằng nhau; nếu các instance bằng nhau về `equals()` nhưng mang metadata khác, không cam kết instance nào được chọn.
- `Set.of("A","A")` sẽ ném `IllegalArgumentException`, khác `Set.copyOf(List.of("A","A"))`.
- `Map.of(k1, v1, k2, v2)` từ chối hai key trùng; `Map.copyOf` nhận một Map vốn đã có tính duy nhất của key.

Trước khi sửa một API, hãy viết test về duplicate, null và order để không vô tình đổi ý nghĩa dữ liệu.

### Lỗi sửa kết quả

Những lời gọi như:

```java
var safe = java.util.List.copyOf(java.util.List.of("A", "B"));

// safe.add("C"); // UnsupportedOperationException
// safe.set(0, "X"); // UnsupportedOperationException
// safe.sort(java.util.Comparator.naturalOrder()); // Không thể sort in-place
```

là phép sửa không hợp lệ với object unmodifiable. Không “bắt ngoại lệ rồi tiếp tục” như một cách xử lý dữ liệu hàng ngày; thay vào đó, nếu caller cần sửa **bản riêng**, hãy tạo mutable copy có chủ đích.

## 11. Các luồng xây dựng và chuyển đổi trước khi xuất bản

### Mutable builder → snapshot chỉ đọc

```java
var working = new java.util.ArrayList<String>();
working.add("B");
working.add("A");
working.sort(java.util.Comparator.naturalOrder());

java.util.List<String> published = java.util.List.copyOf(working);
System.out.println(published); // [A, B]
```

Đừng gọi `published.sort(...)`; sắp xếp **trước khi** copy, hoặc tạo một collection kết quả mới.

### Snapshot chỉ đọc → bản mutable riêng khi cần

```java
var received = java.util.List.copyOf(
        java.util.List.of("A", "B"));

var editable = new java.util.ArrayList<>(received);
editable.add("C");

System.out.println(received); // [A, B]
System.out.println(editable); // [A, B, C]
```

Nếu API trả `List<T>` unmodifiable, caller vẫn có quyền chủ động tạo bản sao mutable cho công việc nội bộ. Điều API cần ngăn là **sửa trực tiếp state được service quản lý**.

### Stream và collector: cần hiểu đúng hợp đồng

Từ Java 10:

```java
var published = java.util.stream.Stream.of("A", "B")
        .collect(java.util.stream.Collectors.toUnmodifiableList());

var publishedSet = java.util.stream.Stream.of("A", "B", "A")
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
```

Hai collector đều từ chối null và kết quả unmodifiable. Ngược lại, `Collectors.toList()`/`toSet()` **không bảo đảm** loại implementation hoặc mutability của collection kết quả, nên không nên dựa vào chúng để công bố một API unmodifiable hay một API chắc chắn mutable.

Từ Java 16, `Stream.toList()` cũng cho unmodifiable list:

```java
var list = java.util.stream.Stream.of("A", "B").toList();
// list.add("C"); // UnsupportedOperationException
```

`Stream.toList()` không phải cùng phương thức với `Collectors.toList()`; khi refactor cần đọc hợp đồng của đúng API.

Nếu caller cần một danh sách mutable cụ thể:

```java
var editable = java.util.stream.Stream.of("A", "B")
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));

editable.add("C");
```

Thích hợp nhất là **chọn collection cho mục tiêu rõ ràng**, không dùng một collector có hợp đồng mơ hồ rồi ép kiểu runtime.

## 12. Ví dụ Java 17+ hoàn chỉnh: API snapshot, DTO an toàn và sự khác biệt với view

Tạo tệp **`ReadOnlyCollectionApiDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public final class ReadOnlyCollectionApiDemo {
    record ProductView(long id, String name, List<String> labels) {
        ProductView {
            Objects.requireNonNull(name);
            labels = List.copyOf(labels);
        }
    }

    static final class CatalogApi {
        private final List<ProductView> products = new ArrayList<>();
        private final Set<String> labels = new HashSet<>();
        private final Map<Long, ProductView> byId = new HashMap<>();

        void add(ProductView view) {
            Objects.requireNonNull(view);
            if (byId.containsKey(view.id())) {
                throw new IllegalArgumentException("Duplicate id");
            }
            products.add(view);
            labels.addAll(view.labels());
            byId.put(view.id(), view);
        }

        List<ProductView> products() { return List.copyOf(products); }
        Set<String> labels() { return Set.copyOf(labels); }
        Map<Long, ProductView> byId() { return Map.copyOf(byId); }
    }

    static void showMutation(String operation, Runnable attempt) {
        try {
            attempt.run();
            System.out.println(operation + ": unexpectedly succeeded");
        } catch (UnsupportedOperationException expected) {
            System.out.println(operation + ": UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        var catalog = new CatalogApi();
        var inputLabels = new ArrayList<>(List.of("java", "api"));
        var first = new ProductView(101L, "Guide", inputLabels);
        inputLabels.add("edited outside");
        System.out.println("record labels=" + first.labels());

        catalog.add(first);
        var listSnapshot = catalog.products();
        var setSnapshot = catalog.labels();
        var mapSnapshot = catalog.byId();

        showMutation("list.add", () ->
                listSnapshot.add(new ProductView(999L, "Other", List.of())));
        showMutation("set.clear", setSnapshot::clear);
        showMutation("map.put", () -> mapSnapshot.put(999L, first));

        catalog.add(new ProductView(102L, "Reference", List.of("java", "docs")));
        System.out.println("old list size=" + listSnapshot.size());
        System.out.println("current list size=" + catalog.products().size());
        System.out.println("old map contains 102=" + mapSnapshot.containsKey(102L));
        System.out.println("current map contains 102=" + catalog.byId().containsKey(102L));
        System.out.println("old labels=" + new TreeSet<>(setSnapshot));
        System.out.println("current labels=" + new TreeSet<>(catalog.labels()));

        var working = new ArrayList<>(List.of("A"));
        var readonlyView = Collections.unmodifiableList(working);
        var detachedCopy = List.copyOf(working);
        working.add("B");
        System.out.println("view after source edit=" + readonlyView);
        System.out.println("copy after source edit=" + detachedCopy);

        var mutableCopy = new ArrayList<>(listSnapshot);
        mutableCopy.add(new ProductView(103L, "Workbook", List.of()));
        System.out.println("editable copy size=" + mutableCopy.size());
        System.out.println("original snapshot size=" + listSnapshot.size());

        var nullable = new ArrayList<String>();
        nullable.add(null);
        try {
            List.copyOf(nullable);
        } catch (NullPointerException expected) {
            System.out.println("null element: NullPointerException");
        }
    }
}
```

Dùng JDK 17+:

```bash
javac --release 17 ReadOnlyCollectionApiDemo.java
java ReadOnlyCollectionApiDemo
```

Stdout **chính xác**, đã biên dịch và chạy:

```text
record labels=[java, api]
list.add: UnsupportedOperationException
set.clear: UnsupportedOperationException
map.put: UnsupportedOperationException
old list size=1
current list size=2
old map contains 102=false
current map contains 102=true
old labels=[api, java]
current labels=[api, docs, java]
view after source edit=[A, B]
copy after source edit=[A]
editable copy size=2
original snapshot size=1
null element: NullPointerException
```

Giải thích:

1. `ProductView` là record có `List<String> labels` được defensive-copy; sửa `inputLabels` sau khi tạo record **không làm đổi** `first.labels()`.
2. Ba getter `products()`, `labels()` và `byId()` dùng lần lượt `List.copyOf`, `Set.copyOf`, `Map.copyOf`, nên các lần sửa thông qua snapshot bị từ chối.
3. `listSnapshot` và `mapSnapshot` lấy trước khi service thêm sản phẩm 102 không thấy sản phẩm mới. Getter được gọi lại phản ánh state mới.
4. Trong demo, `TreeSet` được dùng **chỉ để in tập nhãn theo thứ tự xác định**. Không suy luận rằng bản thân `Set.copyOf` bảo đảm thứ tự.
5. `Collections.unmodifiableList(working)` phản ánh việc bổ sung phần tử B ở `working`, còn `List.copyOf(working)` được tạo trước đó giữ snapshot [A].
6. `new ArrayList<>(listSnapshot)` cho một bản sao mutable riêng; thêm phần tử vào nó không đổi snapshot cũ.
7. `List.copyOf` từ chối phần tử null bằng `NullPointerException`.

`CatalogApi` trong demo **không thiết kế cho ghi/đọc đồng thời không đồng bộ**. Demo minh họa ranh giới unmodifiable, không phải giải pháp concurrency hoàn chỉnh.

Chương trình dùng `record` nên biên dịch với Java 17; với dự án Java 10, có thể thay `ProductView` bằng một `final class` bất biến, giữ nguyên logic `List.copyOf/Set.copyOf/Map.copyOf`.

## 13. Thread-safety và tính nhất quán của snapshot

Một nhận định dễ gây lỗi: “Cứ `List.copyOf` là thread-safe”. Thực tế:

- Snapshot unmodifiable không có mutator làm thay đổi cấu trúc của **chính snapshot**.
- Nhưng việc **tạo snapshot từ collection nguồn đang bị sửa đồng thời** cần bảo đảm an toàn bằng thiết kế lock, ownership, copy-on-write hay một mô hình dữ liệu bất biến phù hợp. `ArrayList`/`HashMap` không tự trở thành thread-safe chỉ vì một phương thức getter gọi `copyOf`.
- Nếu các phần tử là object mutable dùng chung giữa các thread, `copyOf` không tự bảo đảm an toàn cho trạng thái bên trong từng phần tử.
- Nếu service cập nhật nhiều collection liên quan (List sản phẩm, Set nhãn, Map chỉ mục), ba getter được gọi ở ba thời điểm **không tự tạo một snapshot nguyên tử của cả ba**. Muốn dữ liệu nhất quán xuyên nhiều collection, thiết kế một snapshot tổng hợp ở một thời điểm đồng bộ rõ ràng.

Một hướng thiết kế cho read-mostly state: xây dựng một **state object bất biến** chứa các snapshot, sau đó publish nguyên object đó qua cơ chế an toàn cho nhiều thread, chẳng hạn một tham chiếu `volatile` hoặc `AtomicReference<State>`. Cách này giúp các trường trong state được nhìn thấy nhất quán theo từng phiên bản. Cần kiểm chứng riêng yêu cầu đồng bộ khi build state mới.

Không được suy luận rằng “đã trả collection chỉ đọc” tự động giải quyết mọi race condition.

## 14. Hiệu năng và lựa chọn thời điểm tạo bản copy

Mỗi lần tạo snapshot từ một collection mutable lớn có thể cần thời gian/không gian tương ứng với số phần tử. Nếu API được gọi liên tục trong một hot path, copy toàn bộ danh sách ở mỗi lượt đọc có thể tạo áp lực CPU, allocation hoặc GC.

Nhưng **đừng tối ưu bằng cách làm lộ mutable state**. Các phương án tùy tần suất ghi/đọc:

- **Build một lần:** dùng `List.copyOf`/`Set.copyOf`/`Map.copyOf` trong constructor rồi trả field unmodifiable.
- **Ghi ít, đọc nhiều:** cập nhật một snapshot bất biến mới mỗi lần có thay đổi nghiệp vụ, rồi tái sử dụng snapshot cho nhiều lượt đọc.
- **Ghi nhiều, đọc ít:** giữ cấu trúc mutable nội bộ và tạo snapshot tại lần đọc hoặc tại điểm chuyển giao dữ liệu.
- **Cần streaming/paging dữ liệu lớn:** cân nhắc API phân trang hoặc iterator/stream được quản lý lifecycle phù hợp; đừng truyền toàn bộ state chỉ để đọc vài phần tử.

Không đưa ra giả định rằng mọi lần `copyOf` đều tạo object mới. Một số đầu vào unmodifiable có thể được tái sử dụng theo hợp đồng API. Đồng thời, cũng không phụ thuộc vào việc JDK có tối ưu như vậy; hãy benchmark theo workload cụ thể khi cần.

API có dữ liệu immutable ở cấp phần tử thường dễ cache và chia sẻ hơn, nhưng vẫn cần thiết kế các ranh giới concurrency nếu state tổng thể thay đổi.

## 15. Thiết kế chữ ký API để hợp đồng rõ ràng

Một API có thể khai báo:

```java
public java.util.List<ProductView> products();
```

Lợi ích: caller phụ thuộc vào **abstraction `List`**, không phụ thuộc `ArrayList`, `ImmutableCollections` hay class nội bộ của JDK. Nhưng **chỉ chữ ký không thể hiện unmodifiable bằng hệ kiểu Java thông thường**. Hãy mô tả trong Javadoc/API contract:

> Trả một snapshot không cho sửa của danh sách sản phẩm tại thời điểm gọi. Danh sách giữ thứ tự được service công bố; caller không được sửa trực tiếp. Các phần tử `ProductView` được thiết kế có trạng thái bất biến.

Đây là mô tả hợp đồng ví dụ, cần điều chỉnh theo hệ thống thực tế. Nếu API cố ý trả live view, hãy ghi rõ “view phản ánh thay đổi của nguồn” thay vì gọi nó là snapshot. Nếu dữ liệu chỉ là read-only ở mức collection nhưng element còn mutable, **phải công bố giới hạn đó**.

Điểm thực dụng: đừng dùng `List.copyOf` rồi trả về kiểu triển khai nội bộ, ví dụ class tên đặc thù của JDK. Hãy giữ abstraction phù hợp và kiểm thử hành vi.

### Tránh lộ tham chiếu mutable qua một đường phụ

Nếu class có getter `List.copyOf(products)` nhưng một phương thức khác lại trả `products` trực tiếp, hoặc trả một object element mutable mà caller có thể đổi state, ranh giới bảo vệ vẫn bị thủng. Audit các đường aliasing:

- Constructor và setter nhận collection đầu vào.
- Getter trả collection hay subList.
- Iterator/stream được mở trực tiếp trên state mutable.
- Getter phần tử trả object có field mutable.
- API trả Map mà key/value chính là object domain mutable.

Bảo vệ hệ thống theo **toàn bộ đường đi của dữ liệu**, không chỉ một getter đẹp.

## 16. Các sai lầm phổ biến và cách sửa

**Sai lầm 1: Trả trực tiếp `private final ArrayList`.** `final` không ngăn caller sửa object qua tham chiếu được trả. Dùng `List.copyOf` khi cần snapshot.

**Sai lầm 2: Dùng `Collections.unmodifiableList(internal)` rồi nói là snapshot.** Đây là view có thể phản ánh nguồn; dùng `List.copyOf(internal)` nếu muốn tách thay đổi cấu trúc.

**Sai lầm 3: Cho rằng `List.copyOf` tạo deep copy.** Object phần tử mutable vẫn có thể đổi. Trả DTO/value object bất biến hoặc defensive copy ở cấp phần tử.

**Sai lầm 4: Dùng `Set.copyOf` rồi kiểm thử thứ tự duyệt.** Set kết quả không hứa order; nếu order quan trọng, chọn List đã sort hoặc API có hợp đồng ordered rõ ràng.

**Sai lầm 5: Chuyển collection nullable sang `copyOf` mà không kiểm tra.** Null bị từ chối; cần chính sách xử lý rõ.

**Sai lầm 6: Dùng `Collectors.toList()` để cam kết unmodifiable.** Collector này không hứa mutable hay unmodifiable. Chọn `toUnmodifiableList()`/`Stream.toList()`/`List.copyOf(...)` theo yêu cầu.

**Sai lầm 7: Tưởng `Stream.toList()` tạo `ArrayList` mutable.** Từ Java 16, kết quả unmodifiable. Nếu cần chỉnh sửa, sao chép sang `ArrayList` hoặc dùng `toCollection(ArrayList::new)`.

**Sai lầm 8: Dùng key mutable trong `Map.copyOf`.** Thay đổi `equals()/hashCode()` của key đang ở trong map làm hành vi map không được bảo đảm. Dùng key ID bất biến.

**Sai lầm 9: Dùng `record` chứa `ArrayList` mutable mà không sao chép.** Record không deep-freeze object. Cần defensive-copy thành phần collection và object con.

**Sai lầm 10: Tin unmodifiable bằng thread-safe.** Snapshot không giải quyết việc nguồn bị ghi đồng thời hoặc element mutable được chia sẻ.

**Sai lầm 11: Thử sửa object rồi bắt exception để “làm đúng nghiệp vụ”.** Nếu cần biến đổi dữ liệu, thực hiện trên mutable builder/copy, sau đó xuất bản snapshot mới.

**Sai lầm 12: Dựa vào identity/implementation của kết quả `copyOf`.** Không phụ thuộc `==`, `getClass().getName()` hoặc việc JDK có tạo bản sao vật lý hay không.

## 17. Checklist code review

- [ ] Đã xác định API trả **snapshot** hay **live view**; Javadoc và mã triển khai khớp nhau.
- [ ] Không có đường trả tham chiếu mutable nội bộ ngoài ý muốn.
- [ ] Không nhầm field `private final` với collection unmodifiable.
- [ ] Đã chọn đúng `List`/`Set`/`Map` theo yêu cầu order, uniqueness và lookup.
- [ ] Source và các phần tử/key/value đã xử lý chính sách `null` tương thích với `copyOf`.
- [ ] Nếu Set nhận phần tử trùng theo `equals()`, việc chọn đại diện bất kỳ có phù hợp nghiệp vụ?
- [ ] Key của Map có `equals()/hashCode()` ổn định trong suốt vòng đời map.
- [ ] Các element/DTO có thực sự immutable ở cấp dữ liệu cần bảo vệ, kể cả collection lồng trong record?
- [ ] Nếu return collection chứa object mutable, giới hạn shallow copy đã được ghi rõ.
- [ ] Đã xem xét concurrency trong lúc tạo snapshot và khi publish state qua nhiều trường.
- [ ] Nếu dữ liệu lớn hoặc getter gọi nhiều, đã xem xét tần suất copy và caching snapshot?
- [ ] Test kiểm tra hành vi API, không phụ thuộc tên class implementation hoặc thứ tự không được bảo đảm.
- [ ] Caller cần sửa bản riêng có cách `new ArrayList<>(...)`/`new HashMap<>(...)`/`new HashSet<>(...)` rõ ràng.

## 18. Câu hỏi tự kiểm tra

**1.** Vì sao `private final List<X> data` không đủ để bảo đảm caller không sửa được?

**Đáp án:** `final` chỉ ngăn gán lại biến/field tham chiếu. Nếu getter trả object `ArrayList` nội bộ, caller vẫn có thể gọi `add/remove/set` trên object ấy.

**2.** Khác biệt giữa `List.copyOf(source)` và `Collections.unmodifiableList(source)` là gì?

**Đáp án:** `copyOf` tạo snapshot cấu trúc unmodifiable, không phản ánh thay đổi thêm/xóa sau đó ở source mutable. `unmodifiableList` tạo view chỉ đọc nhưng thấy những thay đổi của backing list do nơi khác thực hiện.

**3.** `List.copyOf` có khiến mỗi `ProductView` mutable thành immutable không?

**Đáp án:** Không. Đây là shallow copy; object phần tử vẫn có thể thay đổi qua tham chiếu khác.

**4.** Nếu API cần danh sách theo thứ tự nhưng có phần tử lặp lại, dùng `Set.copyOf` có phù hợp không?

**Đáp án:** Không. Set loại trùng và không hứa iteration order. Nên giữ List, sắp thứ tự trước khi xuất bản nếu cần.

**5.** Vì sao `record Product(List<String> labels)` vẫn có thể bị thay đổi gián tiếp?

**Đáp án:** Thành phần là tham chiếu tới list; caller còn giữ list mutable và có thể sửa nó. Trong constructor, dùng `labels = List.copyOf(labels);` để phòng vệ cấu trúc (và bảo đảm phần tử cũng immutable nếu cần deep immutability).

**6.** Tại sao không nên viết `return Collections.unmodifiableList(internalList);` khi API công bố snapshot?

**Đáp án:** Caller có thể thấy dữ liệu thay đổi về sau khi service sửa `internalList`; đó là live view, không phải snapshot tách biệt.

**7.** `Map.copyOf` có phù hợp khi key là object mutable có mã hash phụ thuộc `status` thường xuyên đổi không?

**Đáp án:** Không an toàn. `copyOf` không bảo vệ key; cần khóa bất biến, thường là ID riêng không đổi.

**8.** `List.copyOf` nhận một List có phần tử `null` sẽ làm gì?

**Đáp án:** Ném `NullPointerException`; cần xử lý chính sách null trước khi copy.

**9.** Vì sao `Set.of("A","A")` không giống `Set.copyOf(List.of("A","A"))`?

**Đáp án:** `Set.of` từ chối phần tử trùng bằng `IllegalArgumentException`, còn `Set.copyOf` loại bản trùng theo hợp đồng Set.

**10.** Nếu cần sửa list kết quả từ API mà không làm thay đổi snapshot gốc, phải làm gì?

**Đáp án:** Tạo `new ArrayList<>(returnedList)`, chỉnh sửa bản mutable mới, rồi có thể `List.copyOf` một lần nữa nếu muốn kết quả cuối unmodifiable.

**11.** Một API trả `List.copyOf(state)` có tự đảm bảo an toàn khi thread khác đang thêm/xóa `state` trong lúc copy không?

**Đáp án:** Không. Phải bảo đảm đồng bộ/ownership hoặc sử dụng kiến trúc publish state bất biến phù hợp.

**12.** Muốn API trả dữ liệu hoàn toàn bất biến và dễ cache, cần chú ý gì ngoài `copyOf`?

**Đáp án:** Thiết kế phần tử và object lồng trong phần tử có trạng thái bất biến, phòng vệ đầu vào/đầu ra, đảm bảo key ổn định, cùng cơ chế publish/cập nhật state thích hợp.

## Tài liệu Java chính thức đang còn hiệu lực

- [Java SE 25 — `List.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): snapshot unmodifiable, giữ iteration order của nguồn, từ chối null.
- [Java SE 25 — `Set.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): tập unmodifiable, cách xử lý phần tử trùng, không bảo đảm iteration order.
- [Java SE 25 — `Map.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): bản sao map unmodifiable và các giới hạn về key/value mutable.
- [Java SE 25 — `Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): wrapper live view trên backing list.
- [Java SE 25 — `Collection`: Unmodifiable và View Collections](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html): phân biệt khả năng sửa và tính bất biến của phần tử.
- [Oracle — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): hướng dẫn lựa chọn snapshot hay view và đặc tính unmodifiable collection.
- [Java SE 25 — `Collectors.toUnmodifiableList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): collector tạo list không cho sửa từ Java 10.
- [Java SE 25 — `Stream.toList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#toList()): list unmodifiable từ Java 16.
- [OpenJDK — JEP 395: Records](https://openjdk.org/jeps/395): cú pháp record được chuẩn hóa từ Java 16, không tự tạo deep immutability.
