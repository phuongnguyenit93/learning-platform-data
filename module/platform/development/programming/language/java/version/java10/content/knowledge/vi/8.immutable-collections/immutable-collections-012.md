# Tiêu chí chọn cấu trúc có thể sửa hoặc chỉ đọc trong Java

> **Ngữ cảnh Java 10 — Collection chỉ đọc.** Bài tập trung vào quyết định thiết kế: khi nào dùng collection có thể sửa (*modifiable/mutable*), khi nào công bố collection không cho sửa (*unmodifiable*), và khi nào cần một bản chụp độc lập với dữ liệu gốc. Các API `List.copyOf`, `Set.copyOf`, `Map.copyOf` và `Collectors.toUnmodifiable*` được bổ sung trong Java 10; chúng vẫn hữu ích trên các JDK hiện đại được nhà cung cấp hỗ trợ. Bài không yêu cầu cài JDK 10 hoặc dùng tính năng đã lỗi thời.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt **collection có thể sửa**, **bản chụp không cho sửa** và **view không cho sửa**.
2. Chọn `ArrayList`, `HashSet`/`LinkedHashSet`, `HashMap`/`LinkedHashMap` khi cần cập nhật dữ liệu; chọn các API Java 10 `copyOf` hoặc `toUnmodifiable*` khi muốn phát hành kết quả chỉ đọc.
3. Đánh giá các tiêu chí thực tế: ai sở hữu dữ liệu, có thêm/xóa/sửa sau khi tạo không, có được chia sẻ cho caller không, có cần snapshot, null, trùng lặp, thứ tự và đồng thời hay không.
4. Giải thích đúng vì sao **không cho sửa cấu trúc** chưa đồng nghĩa với **bất biến sâu** hoặc **an toàn luồng**.
5. Chạy được một chương trình Java để so sánh các cách lựa chọn và tránh lỗi phổ biến khi thiết kế API.

## 2. Thuật ngữ: ba dạng thường bị nhầm

| Dạng | Ví dụ | Có thể thay đổi qua tham chiếu trả về? | Có phản ánh thay đổi cấu trúc của nguồn? |
| --- | --- | --- | --- |
| Collection có thể sửa (*modifiable*) | `new ArrayList<>()`, `new HashMap<>()` | **Có**, qua `add/remove/set/put` khi được hỗ trợ | Chính collection đó thay đổi nếu caller được quyền thao tác. |
| **Bản chụp** không cho sửa (*unmodifiable snapshot*) | `List.copyOf(source)`, `Map.copyOf(source)` | **Không**, thao tác sửa cấu trúc ném `UnsupportedOperationException` | **Không** đối với thêm/xóa/thay phần tử hoặc entry ở nguồn sau lúc copy. |
| **View** không cho sửa (*unmodifiable view*) | `Collections.unmodifiableList(source)` | **Không qua view** | **Có**: thay đổi thực hiện trên danh sách gốc có thể hiện ra ở view. |

**“Read-only” là mô tả về cách sử dụng, không phải tên một interface tách biệt trong Java Collections Framework.** Khai báo kiểu `List<String>` không bảo đảm instance sẽ cho sửa hay không: cả `ArrayList<String>` và kết quả `List.copyOf(...)` đều là `List<String>`. Phải xét **hợp đồng API**, dữ liệu được tạo thế nào và quyền sở hữu tham chiếu.

Ví dụ:

```java
// Đoạn minh họa bên trong một phương thức:
var source = new java.util.ArrayList<>(java.util.List.of("A", "B"));
var view = java.util.Collections.unmodifiableList(source);
var snapshot = java.util.List.copyOf(source);
source.add("C");

System.out.println(view);     // [A, B, C]
System.out.println(snapshot); // [A, B]
```

`view.add("D")` và `snapshot.add("D")` đều ném `UnsupportedOperationException`, nhưng ý nghĩa đối với sự thay đổi ở nguồn khác nhau. Việc bạn **không gọi `add` được trên view** không ngăn người còn giữ tham chiếu `source` sửa nó.

Một biến `final List<String> x` chỉ cấm **gán lại biến `x`**, không cấm `x.add(...)` nếu đối tượng đích là `ArrayList`. Tương tự, `var` chỉ suy luận kiểu cục bộ, không xác định collection có thể sửa hay không.

## 3. Bảng quyết định: chọn theo nhu cầu nghiệp vụ

| Tình huống / tiêu chí | Lựa chọn điển hình | Vì sao |
| --- | --- | --- |
| Tạo danh sách và liên tục thêm/xóa/chỉnh phần tử trong thuật toán | `ArrayList<E>` | Cập nhật trực tiếp thuận tiện; không phải tạo bản sao sau mỗi bước. |
| Cần tập hợp không trùng, vẫn phải thêm/xóa | `HashSet<E>`; `LinkedHashSet<E>` khi cần duy trì thứ tự chèn | Chọn cấu trúc phù hợp ngữ nghĩa và thứ tự mong muốn. |
| Tra cứu theo khóa, nội dung cần cập nhật | `HashMap<K,V>`; `LinkedHashMap<K,V>` khi cần thứ tự chèn | `put/remove/compute` phục vụ cập nhật. |
| Bộ hằng số nhỏ được xác định ngay lúc viết code | `List.of(...)`, `Set.of(...)`, `Map.of(...)` | Tạo trực tiếp collection không cho sửa; các factory này có từ **Java 9** và vẫn dùng được. |
| Nhận collection có thể sửa, cần giữ trạng thái tại thời điểm nhận/giao dữ liệu | `List.copyOf(source)`, `Set.copyOf(source)`, `Map.copyOf(source)` | Tạo bản chụp cấu trúc không cho sửa theo hợp đồng Java 10. |
| Dữ liệu được `filter/map` qua Stream và kết quả không được sửa | `Collectors.toUnmodifiableList/Set/Map` | Thu thập kết quả trực tiếp thành collection không cho sửa; Java 10. |
| Stream cần trả kết quả **có thể sửa** với loại collection xác định | `Collectors.toCollection(ArrayList::new)` hoặc collector có supplier phù hợp | Yêu cầu tính mutability và implementation một cách tường minh. |
| Cố ý muốn người đọc nhìn thấy thay đổi ở một collection do nơi khác sở hữu | `Collections.unmodifiableList(source)` | Đây là **live view**; cần tài liệu hóa lifetime, quyền sửa nguồn và tương tác với caller. |
| Lấy dữ liệu từ API ngoài rồi trả cho nhiều thành phần | Bản chụp `copyOf` sau khi kiểm tra/chuẩn hóa | Ngăn caller và chủ nguồn thay đổi cấu trúc đã công bố. |
| Có nhiều lần cập nhật liên tiếp, thỉnh thoảng cần phát hành phiên bản chỉ đọc | Dữ liệu nội bộ mutable + `copyOf` tại mốc công bố | Tránh sao chép toàn bộ collection sau từng `add` nhỏ. |

**Câu hỏi quyết định nhanh:** Dữ liệu có phải thay đổi **sau** thời điểm trả cho bên khác không? Nếu không, ưu tiên công bố snapshot không cho sửa. Nếu có, hãy xác định **ai** được sửa, thay đổi có phải phản ánh cho reader ngay không, và cơ chế đồng bộ được thiết kế ra sao. Không để một view ngẫu nhiên vô tình trở thành hợp đồng cập nhật hai chiều.

## 4. Tiêu chí 1 — quyền sở hữu và ranh giới API

### 4.1. Nội bộ xây dựng mutable, bên ngoài nhận snapshot

Một service có thể cần danh sách mutable trong quá trình tính toán:

```java
// Ví dụ bên trong phương thức:
var working = new java.util.ArrayList<String>();
working.add("alpha");
working.add("beta");
return java.util.List.copyOf(working);
```

Đây là cách phổ biến tại **ranh giới API**: code xây dựng giữ quyền sửa dữ liệu làm việc; caller chỉ nhận phiên bản không cho sửa. Nếu `working` có thay đổi về sau, `List.copyOf(working)` đã trả không đổi về cấu trúc. Cần đặc biệt hữu ích khi dữ liệu đến từ tham số constructor, tham số setter hoặc collection được trả ra từ method.

Ví dụ class đầy đủ **về thiết kế** (đoạn này độc lập trong một tệp riêng khi thêm imports tương ứng):

```java
import java.util.Collection;
import java.util.List;

public final class TagCatalog {
    private final List<String> tags;

    public TagCatalog(Collection<String> suppliedTags) {
        this.tags = List.copyOf(suppliedTags);
    }

    public List<String> tags() {
        return tags;
    }
}
```

Constructor tạo bản chụp cấu trúc để caller không sửa được dữ liệu catalog bằng `suppliedTags.add(...)` sau khi xây dựng. Getter trả lại collection không cho sửa, không cần copy lại mỗi lần nếu trạng thái đã bất biến theo hợp đồng.

**Lưu ý:** `List.copyOf` có thể tái sử dụng instance nguồn nếu nguồn đã là unmodifiable list phù hợp. Không dựa vào `==` hoặc danh tính đối tượng được trả về. Hợp đồng bạn cần dựa vào là **giá trị và hành vi không cho sửa**, không phải “mỗi lần gọi tạo object mới”.

### 4.2. Khi nào dùng live view?

`Collections.unmodifiableList(backing)` hữu ích khi thiết kế **có chủ ý** cho một bên quan sát thay đổi do chủ sở hữu thực hiện:

```java
var backing = new java.util.ArrayList<>(java.util.List.of("A"));
var liveView = java.util.Collections.unmodifiableList(backing);
backing.add("B");
System.out.println(liveView); // [A, B]
```

Caller không thể sửa qua `liveView`, nhưng sẽ thấy thay đổi của `backing`. Điều này là một **hợp đồng quan sát dữ liệu sống**, khác mục tiêu “đóng băng dữ liệu tại thời điểm xuất bản”. Nó còn đòi hỏi xử lý rõ ràng khi nguồn đang bị sửa và nhiều luồng cùng đọc. Không dùng live view để kỳ vọng có snapshot độc lập.

Một lựa chọn tương đương về ý tưởng trên JDK cũ là `Collections.unmodifiableList(new ArrayList<>(source))`: bản sao mutable được tạo trước và bọc bởi view không cho sửa. Trên JDK hiện đại, `List.copyOf(source)` thường diễn đạt snapshot trực tiếp, ngắn và dễ hiểu hơn **khi dữ liệu không chứa null**.

## 5. Tiêu chí 2 — cấu trúc dữ liệu: List, Set hay Map?

Đừng quyết định theo tên “read-only” trước khi biết cấu trúc cần biểu diễn điều gì.

### 5.1. `List`: cần thứ tự và cho phép trùng

`List` thích hợp khi dữ liệu có thứ tự vị trí, `get(index)`, hoặc có thể có nhiều giá trị giống nhau. `List.copyOf(source)` giữ **thứ tự duyệt** của collection nguồn tại lúc copy. `Collectors.toUnmodifiableList()` giữ encounter order nếu Stream có encounter order.

```java
var ordered = java.util.List.copyOf(
        java.util.List.of("A", "B", "A"));
System.out.println(ordered); // [A, B, A]
```

Dùng `new ArrayList<>(source)` nếu caller cần chỉnh sửa danh sách riêng của họ; dùng `List.copyOf` nếu caller chỉ được đọc.

### 5.2. `Set`: cần duy nhất, không dựa vào thứ tự không được bảo đảm

`Set.copyOf(source)` tạo tập không cho sửa, loại các phần tử trùng theo `equals`. Nếu nguồn có các phần tử bằng nhau, không nên dựa vào danh tính của phần tử nào được giữ; cũng **không dựa vào thứ tự duyệt** của kết quả `Set.copyOf`/`Set.of`.

```java
var distinct = java.util.Set.copyOf(java.util.List.of("A", "B", "A"));
System.out.println(distinct.size());      // 2
System.out.println(distinct.contains("A")); // true
```

Nếu kết quả buộc phải được duyệt theo thứ tự xác định, cân nhắc `LinkedHashSet` mutable khi còn cần cập nhật; hoặc biểu diễn danh sách đã khử trùng với thứ tự rõ ràng, rồi tạo `List.copyOf` khi công bố. Tập bất biến không nên bị dùng thay danh sách có thứ tự nghiệp vụ.

### 5.3. `Map`: cần ánh xạ khóa → giá trị

`Map.copyOf(source)` chụp lại entries không cho sửa. Key và value đều phải khác `null`. Không viết test dựa vào thứ tự duyệt của map được tạo từ `Map.copyOf` hoặc `Map.of`; thay bằng `get(key)` hay `containsKey(key)`.

```java
var source = new java.util.HashMap<String, Integer>();
source.put("A", 1);
var snapshot = java.util.Map.copyOf(source);
source.put("A", 7);
System.out.println(snapshot.get("A")); // 1
```

Chọn `HashMap` mutable khi nghiệp vụ cần cập nhật. Nếu thứ tự là phần của hợp đồng công khai, chọn kiểu dữ liệu/thao tác thể hiện yêu cầu ấy thay vì giả định `Map.copyOf` bảo toàn thứ tự.

## 6. Tiêu chí 3 — đang xử lý Stream: mutable hay unmodifiable?

Từ Java 10, các collector `Collectors.toUnmodifiableList()`, `toUnmodifiableSet()` và `toUnmodifiableMap(...)` thu thập dữ liệu đã qua Stream thành kết quả không cho sửa.

```java
var cleanCodes = java.util.List.of(" A ", "B", " A ").stream()
        .map(String::trim)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
// cleanCodes là List<String> không cho sửa: [A, B, A].
```

Đây là lựa chọn hợp lý khi pipeline tạo **kết quả cuối cùng** cần trao cho caller. Với danh sách muốn tiếp tục thêm/xóa, chọn:

```java
var editable = java.util.List.of("A", "B").stream()
        .collect(java.util.stream.Collectors.toCollection(java.util.ArrayList::new));
editable.add("C"); // Hợp lệ; editable có thể sửa.
```

**Không mặc định rằng `Collectors.toList()` luôn tạo `ArrayList` hoặc luôn cho phép sửa.** Javadoc của `Collectors.toList()` không bảo đảm loại, mutability, serializability hay thread-safety của kết quả. Khi hành vi **có thể sửa** là điều kiện bắt buộc, nêu rõ supplier bằng `toCollection(ArrayList::new)`.

`Stream.toList()` là một API được bổ sung **sau Java 10**, cũng cho kết quả không cho sửa, nhưng có hợp đồng riêng. Không đánh đồng nó với `Collectors.toUnmodifiableList()` trong các kiểm tra null hoặc khi ghi chú “được bổ sung ở Java 10”. Với bài tập kiến thức Java 10, sử dụng đúng bộ `toUnmodifiable*`.

### 6.1. Khóa trùng khi thu thập Map

`Collectors.toUnmodifiableMap(keyMapper, valueMapper)` **ném `IllegalStateException`** nếu hai phần tử tạo cùng khóa. Khi trùng khóa là tình huống được phép, dùng overload có merge function:

```java
var counts = java.util.List.of("A", "B", "A").stream()
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                code -> code,
                code -> 1,
                Integer::sum));
System.out.println(counts.get("A")); // 2
```

Ở đây `Integer::sum` là quy tắc hợp nhất rõ ràng: hai bản ghi có cùng khóa `A` được cộng số lần xuất hiện. Không tự ý merge nếu nghiệp vụ yêu cầu báo lỗi khi trùng khóa.

## 7. Tiêu chí 4 — null, phần tử trùng và lỗi ở ranh giới dữ liệu

### 7.1. Các factory/copy Java 10 không chấp nhận null

`List.copyOf` và `Set.copyOf` từ chối phần tử `null`. `Map.copyOf` từ chối khóa hoặc giá trị `null`. `Collectors.toUnmodifiable*` cũng từ chối các phần tử hoặc key/value null tương ứng. Lỗi thường là `NullPointerException` trong lúc tạo kết quả.

```java
var nullable = new java.util.ArrayList<String>();
nullable.add(null);
java.util.List.copyOf(nullable); // Ném NullPointerException.
```

`ArrayList` có thể chứa null. `Collections.unmodifiableList(nullable)` cũng phản ánh null đang có trong nguồn, nhưng việc chọn view như vậy **không tự giải quyết được vấn đề dữ liệu thiếu**. Với hợp đồng mới, nên xác định rõ null có hợp lệ không, chuẩn hóa/loại bỏ/biểu diễn khác trước khi tạo collection công bố.

### 7.2. Trùng trong List, Set, Map khác nhau

| Nguồn trùng | Cách tạo | Kết quả |
| --- | --- | --- |
| `List.of("A","A")` | `List.copyOf(...)` | Giữ hai phần tử theo thứ tự `["A","A"]`. |
| `List.of("A","A")` | `Set.copyOf(...)` | Chỉ giữ một giá trị phân biệt. |
| Stream có hai khóa `A` | `toUnmodifiableMap(k, v)` | `IllegalStateException` nếu thiếu merge function. |
| Stream có hai khóa `A` | `toUnmodifiableMap(k, v, Integer::sum)` | Gộp theo quy tắc được chỉ định. |

Cần lựa chọn dựa trên **ý nghĩa dữ liệu**, không vì một API ngắn hơn vài ký tự. Danh sách đơn hàng có thể cần giữ bản ghi trùng, tập quyền hạn thường cần duy nhất, còn map thống kê phải có quy tắc gộp khóa rõ ràng.

## 8. Tiêu chí 5 — bất biến nông, đối tượng phần tử và thread safety

### 8.1. Unmodifiable không phải deep immutable

`List.copyOf` giữ tham chiếu đến **các phần tử** có trong nguồn. Nếu phần tử có trạng thái mutable, thay đổi trạng thái của nó vẫn có thể quan sát qua danh sách:

```java
var builder = new StringBuilder("v1");
var snapshot = java.util.List.copyOf(java.util.List.of(builder));
builder.append("-v2");
System.out.println(snapshot.get(0)); // v1-v2
```

Không thể `snapshot.set(0, ...)` hoặc `snapshot.add(...)`, nhưng `StringBuilder` ban đầu vẫn thay đổi được. Vì vậy:

- Khi dữ liệu phần tử là những giá trị bất biến như `String`, `Integer` hoặc domain object được thiết kế bất biến, snapshot dễ trở thành giá trị ổn định.
- Khi phần tử là `StringBuilder`, mảng, bean có setters hoặc collection lồng nhau, cần **sao chép/đóng băng các phần tử theo nghiệp vụ** trước khi đưa vào snapshot nếu yêu cầu bất biến sâu.
- Một `record` (nếu dùng trong JDK mới) chỉ có các thành phần final về tham chiếu; nếu chứa mảng hoặc collection mutable thì **không tự bảo đảm bất biến sâu**. Phải quyết định defensive copy ở constructor/accessor phù hợp.

### 8.2. “Chỉ đọc” không tự động an toàn luồng

Một `Collections.unmodifiableList(mutableBacking)` không ngăn luồng khác sửa `mutableBacking`, do đó không tự giải quyết race condition hoặc tính nhất quán của phép duyệt. Collection không cho sửa chứa phần tử mutable cũng không tự bảo đảm truy cập an toàn đến nội dung phần tử.

Một snapshot không cho sửa với các phần tử bất biến, được **công bố an toàn** giữa các luồng, thường dễ dùng hơn làm trạng thái để đọc. Nhưng cần thiết kế cơ chế publish/synchronization/happens-before phù hợp nếu dữ liệu xây dựng hoặc được thay thế giữa các luồng. Chỉ thêm `copyOf` không tự sửa toàn bộ vấn đề concurrency.

### 8.3. “Read-only” cũng không bảo đảm bảo mật dữ liệu

Nếu một caller còn giữ tham chiếu đến nguồn mutable hoặc đến đối tượng phần tử có setters, một view không cho sửa không thể thu hồi quyền sửa qua các tham chiếu đó. Để bảo vệ bất biến nghiệp vụ, cần encapsulation và chính sách ownership rõ ràng — không chỉ thêm một wrapper bên ngoài.

## 9. Tiêu chí 6 — chi phí cập nhật, sao chép và bộ nhớ

Các collection mutable được thiết kế cho những thay đổi lặp lại. Nếu nghiệp vụ có 1.000 lần `add`, không nên tạo `List.copyOf` sau **từng** lần thêm trừ khi đó là yêu cầu versioning rõ ràng. Việc sao chép có chi phí tỷ lệ theo lượng dữ liệu; cập nhật liên tục bằng bản copy có thể tốn thời gian và bộ nhớ không cần thiết.

Mô hình thường rõ ràng hơn:

```java
var working = new java.util.ArrayList<String>();
for (var i = 0; i < 1000; i++) {
    working.add("id-" + i);
}
var published = java.util.List.copyOf(working);
```

Đây là cách **build mutable → publish unmodifiable**. Collection không cho sửa tạo bằng factory hiện đại có thể tiết kiệm overhead cấu trúc và giúp tránh sửa nhầm, nhưng đừng khẳng định mọi trường hợp đều tiết kiệm hay nhanh hơn: hiệu quả phụ thuộc kích thước, pattern truy cập, loại phần tử và implementation JDK. Chỉ tối ưu theo profiling/benchmark khi cần.

Nếu bên nhận phải chỉnh sửa riêng mà không ảnh hưởng chủ nguồn, hãy trao cho họ **bản sao mutable** như `new ArrayList<>(source)`; đừng trả view để rồi họ phải bất ngờ bắt `UnsupportedOperationException`. Ngược lại, nếu contract trả ra read-only, không cần tạo một bản mutable rồi khuyến khích caller tự sửa.

## 10. Lab hoàn chỉnh: ba loại List, snapshot Map, collector và lỗi thường gặp

### 10.1. Chuẩn bị

Dùng một bản phân phối **JDK hiện đang được nhà cung cấp hỗ trợ và cập nhật bản vá** (ví dụ JDK 21 hoặc 25 LTS nếu phù hợp chính sách dự án). Các API chính của lab có từ Java 10; không cần cài JDK 10.

```bash
java -version
javac -version
```

Tạo tệp **`CollectionChoiceLab.java`** với mã đầy đủ sau:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class CollectionChoiceLab {
    // Ứng dụng nhận dữ liệu ngoài và công bố bản chụp chỉ đọc.
    static final class Tags {
        private final List<String> values;

        Tags(Collection<String> source) {
            values = List.copyOf(source);
        }

        List<String> readOnly() {
            return values;
        }
    }

    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("alpha", "beta"));
        var editableCopy = new ArrayList<>(source);
        var view = Collections.unmodifiableList(source);
        var snapshot = List.copyOf(source);

        source.add("gamma");
        editableCopy.add("local");

        System.out.println("source: " + source);
        System.out.println("editable copy: " + editableCopy);
        System.out.println("view: " + view);
        System.out.println("snapshot: " + snapshot);

        try {
            snapshot.add("blocked");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot add: blocked");
        }

        var owner = new Tags(source);
        source.add("delta");
        System.out.println("owner: " + owner.readOnly());

        var normalized = List.of(" A ", "B", " A ").stream()
                .map(String::trim)
                .collect(Collectors.toUnmodifiableList());
        System.out.println("normalized list: " + normalized);

        var distinct = Set.copyOf(normalized);
        System.out.println("distinct: size=" + distinct.size()
                + ", hasA=" + distinct.contains("A"));

        var counts = normalized.stream()
                .collect(Collectors.toUnmodifiableMap(
                        s -> s, s -> 1, Integer::sum));
        System.out.println("count A: " + counts.get("A"));

        try {
            normalized.stream()
                    .collect(Collectors.toUnmodifiableMap(
                            s -> s, String::length));
        } catch (IllegalStateException ex) {
            System.out.println("duplicate map key: blocked");
        }

        var scores = new LinkedHashMap<String, Integer>();
        scores.put("A", 1);
        var scoresSnapshot = Map.copyOf(scores);
        scores.put("A", 7);
        System.out.println("score source/snapshot: "
                + scores.get("A") + "/" + scoresSnapshot.get("A"));

        var builder = new StringBuilder("v1");
        var shallow = List.copyOf(List.of(builder));
        builder.append("-v2");
        System.out.println("mutable element: " + shallow.get(0));

        var withNull = new ArrayList<String>();
        withNull.add(null);
        try {
            List.copyOf(withNull);
        } catch (NullPointerException ex) {
            System.out.println("null in copyOf: blocked");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac CollectionChoiceLab.java
java CollectionChoiceLab
```

### 10.2. Output chính xác

```text
source: [alpha, beta, gamma]
editable copy: [alpha, beta, local]
view: [alpha, beta, gamma]
snapshot: [alpha, beta]
snapshot add: blocked
owner: [alpha, beta, gamma]
normalized list: [A, B, A]
distinct: size=2, hasA=true
count A: 2
duplicate map key: blocked
score source/snapshot: 7/1
mutable element: v1-v2
null in copyOf: blocked
```

Chương trình cố tình **không in toàn bộ Set hay Map** có thứ tự duyệt không được hợp đồng API bảo đảm. Nó chỉ kiểm tra `size`, `contains` hoặc `get(key)`, nên output ổn định trên JDK phù hợp.

### 10.3. Giải thích output theo từng quyết định

**Bước A — nguồn và bản sao mutable:** `source` ban đầu có `alpha, beta`. `editableCopy` là bản sao mutable tách khỏi cấu trúc nguồn. Thêm `gamma` vào nguồn không cập nhật bản sao; thêm `local` vào bản sao không cập nhật nguồn. Vì vậy hai dòng in khác nhau.

**Bước B — view và snapshot:** `view` bọc `source`, phản ánh `gamma` sau khi nguồn được sửa. `snapshot` giữ hai phần tử ban đầu. Gọi `snapshot.add` ném `UnsupportedOperationException`; catch có thông điệp riêng, không phụ thuộc stack trace JVM.

**Bước C — đóng gói API:** `new Tags(source)` xảy ra sau khi nguồn đã thêm `gamma` nhưng trước khi thêm `delta`. Constructor gọi `List.copyOf`, nên `owner.readOnly()` chỉ có `alpha, beta, gamma`. Điều này là minh họa của quy tắc **copy khi nhận dữ liệu**.

**Bước D — Stream và trùng:** `normalized` là `[A, B, A]`, giữ trùng và encounter order. `Set.copyOf(normalized)` có hai giá trị phân biệt; `contains("A")` đúng. `Collectors.toUnmodifiableMap(..., Integer::sum)` đếm `A` hai lần, trả `2`. Nếu không truyền merge function, hai khóa `A` gây `IllegalStateException`.

**Bước E — Map snapshot:** `scoresSnapshot` lấy `A=1` ở thời điểm `Map.copyOf`. Khi `scores` được cập nhật thành `A=7`, giá trị trong snapshot vẫn là `1`. Không suy luận thứ tự map từ việc `scores` dùng `LinkedHashMap`, vì `Map.copyOf` không cam kết giữ thứ tự duyệt.

**Bước F — bất biến nông:** `StringBuilder` là mutable; việc `builder.append("-v2")` khiến `shallow.get(0)` in `v1-v2` dù không có thao tác sửa cấu trúc list.

**Bước G — null:** `List.copyOf` từ chối phần tử null và ném `NullPointerException`. Trong mã nghiệp vụ, nên xử lý null ở biên dữ liệu (validate, filter hoặc biểu diễn trạng thái thiếu) thay vì chờ lỗi lan đến nơi xa hơn.

## 11. Cách áp dụng trong code thực tế

### 11.1. Configuration được nạp một lần

Dùng bản chụp `Map.copyOf(config)` sau khi kiểm tra dữ liệu nếu các giá trị phải ổn định cho một phiên cấu hình. Nếu có tính năng hot reload, tạo **snapshot mới** và publish qua cơ chế đồng bộ phù hợp; không biến view trên map mutable thành “snapshot” rồi kỳ vọng các lần đọc luôn nhất quán.

### 11.2. Tìm kiếm có nhiều bước lọc

Tại thời điểm tập kết quả còn cần bổ sung/loại bớt, dùng danh sách mutable. Sau khi đã lọc/sắp xếp xong, phát hành `List.copyOf(result)`. Với kết quả đi thẳng từ Stream và không còn sửa, có thể dùng `toUnmodifiableList()`. Nếu caller cần sắp xếp theo ý riêng, hãy xác định contract cho phép họ nhận bản sao mutable.

### 11.3. Danh sách quyền hoặc nhãn

Dùng `Set` khi trùng lặp không mang ý nghĩa; dùng `Set.copyOf` để công bố một tập quyền chỉ đọc. Nếu thứ tự hiển thị quyền mang ý nghĩa nghiệp vụ, giữ mô hình thứ tự riêng và không trông chờ thứ tự duyệt của unmodifiable `Set`.

### 11.4. Giỏ hàng đang được cập nhật

Giỏ hàng thường còn thêm/xóa sản phẩm: một cấu trúc mutable nội bộ có thể phù hợp hơn. Khi tạo đơn đặt hàng hoặc phát sự kiện, tạo snapshot chỉ đọc **tại mốc xác nhận**; nếu sản phẩm/line item là mutable, cần chuyển sang các giá trị phần tử bất biến hoặc defensive copy theo hợp đồng.

### 11.5. Getter của domain object

Tránh trả thẳng `private final ArrayList<Item> items` để caller sửa nội bộ. Trả `List.copyOf(items)` nếu cần snapshot mỗi lần đọc hoặc giữ một snapshot unmodifiable đã công bố nếu trạng thái không thay đổi. Nếu thay đổi liên tục, cân nhắc chi phí sao chép và nhất quán giữa các luồng; lựa chọn phụ thuộc mô hình ownership và concurrency.

## 12. Lỗi thường gặp khi lựa chọn

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Trả `Collections.unmodifiableList(source)` nhưng nói đó là snapshot | View vẫn phản ánh thay đổi của nguồn. | Dùng `List.copyOf(source)` khi cần snapshot. |
| Nghĩ `List.copyOf` là deep copy | Nó chỉ sao chép cấu trúc và giữ tham chiếu phần tử. | Dùng phần tử bất biến hoặc defensive copy sâu nếu cần. |
| Trả `ArrayList` mutable cho caller không được sửa | Caller có thể gọi `add/remove/set`. | Công bố `List.copyOf` hoặc collector unmodifiable. |
| Dùng `List.copyOf` khi dữ liệu có null | Ném `NullPointerException`. | Xác định contract về null rồi chuẩn hóa trước. |
| In `Set.copyOf(...)` và test thứ tự | Thứ tự duyệt không được bảo đảm. | Test `size/contains`, hoặc chọn cấu trúc có contract thứ tự phù hợp. |
| Dùng `toUnmodifiableMap` với khóa trùng mà không nghĩ cách xử lý | Ném `IllegalStateException`. | Có merge function theo nghiệp vụ hoặc kiểm tra trùng để báo lỗi. |
| Giả định `Collectors.toList()` luôn mutable | API không cam kết. | Nếu cần mutable, dùng `toCollection(ArrayList::new)`. |
| Tạo `copyOf` sau mỗi `add` trong một vòng lặp dài | Dễ phát sinh chi phí sao chép lặp lại. | Cập nhật mutable, tạo snapshot ở mốc cần publish. |
| Dùng `Collections.unmodifiableList` như bảo đảm thread-safety | Mutable backing vẫn có thể bị luồng khác sửa. | Thiết kế concurrency và safe publication riêng. |
| Đánh đồng `final` với “không sửa được” | `final` chỉ ngăn gán lại reference. | Dựa vào loại collection và hợp đồng API. |
| Dùng `Arrays.asList(...)` và coi đó là immutable | Danh sách có kích thước cố định nhưng có thể `set` thay phần tử. | Dùng `List.of` hoặc `List.copyOf` nếu cần unmodifiable với dữ liệu hợp lệ. |

## 13. Bài tập thực hành có hướng giải

**Bài A — Chọn cấu trúc cho một màn hình tìm kiếm.** Kết quả được thêm dần khi tải nhiều trang dữ liệu, sau đó gửi tới tầng hiển thị không được sửa. Hãy chọn collection ở hai giai đoạn. **Hướng giải:** dùng `ArrayList<Result>` khi thu thập; khi hoàn tất và nếu phần tử đáp ứng hợp đồng bất biến, dùng `List.copyOf(results)` để công bố. `Result` là kiểu domain minh họa của ứng dụng.

**Bài B — Phân tích live view.** Cho:

```java
var source = new java.util.ArrayList<>(java.util.List.of("one"));
var v = java.util.Collections.unmodifiableList(source);
source.add("two");
System.out.println(v);
```

**Đáp án:** `[one, two]`. `v` không cho sửa qua API list nhưng phản ánh thay đổi nguồn. Nếu yêu cầu là giữ riêng `[one]`, thay `v` bằng `List.copyOf(source)` **trước** khi thêm `two`.

**Bài C — Chọn List hay Set.** Danh sách đầu vào là `List.of("ADMIN","USER","ADMIN")`. Nếu đầu ra chỉ cần tập quyền phân biệt, dùng `Set.copyOf(...)`; xác nhận `size()==2` và `contains("ADMIN")` đúng. Nếu đầu ra cần giữ cả ba lần xuất hiện và thứ tự, dùng `List.copyOf(...)`. Không in thứ tự Set làm điều kiện pass.

**Bài D — Mục tiêu cập nhật tiếp sau Stream.** Từ `List.of("A","B")`, thu thập danh sách cần thêm `"C"` sau đó. **Đáp án:** `stream().collect(Collectors.toCollection(ArrayList::new))`. Nếu dùng `toUnmodifiableList()` thì `add` ném `UnsupportedOperationException`, phù hợp chỉ khi business không cho phép cập nhật.

**Bài E — Khóa trùng trong Map.** `List.of("A","B","A")` cần đếm tần suất. **Đáp án:** dùng `Collectors.toUnmodifiableMap(s -> s, s -> 1, Integer::sum)`. `get("A")` bằng `2`; bản collector không merge sẽ ném `IllegalStateException`.

**Bài F — Đánh giá bất biến sâu.** Bạn nhận một `List<StringBuilder>` và gọi `List.copyOf`. Có thể tuyên bố mọi nội dung văn bản không thay đổi nữa không? **Đáp án:** Không. Phần tử `StringBuilder` có thể tiếp tục thay đổi. Nếu cần snapshot giá trị chuỗi, chuyển từng phần tử thành `String` trước rồi tạo `List.copyOf` hoặc collector unmodifiable, ví dụ:

```java
var stable = builders.stream()
        .map(StringBuilder::toString)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

`builders` là biến `List<StringBuilder>` đã được khai báo ở nơi gọi; đoạn này minh họa bên trong phương thức. `String` là loại dữ liệu bất biến, nên những thay đổi tiếp theo trên `StringBuilder` gốc không đổi giá trị các chuỗi đã thu thập.

**Bài G — Công bố dữ liệu cho nhiều luồng.** Một thread liên tục thay đổi danh sách, các thread khác đọc qua `Collections.unmodifiableList`. Có thể gọi đó là thread-safe không? **Đáp án:** Không. Cần chọn mô hình đồng bộ và cách công bố trạng thái rõ ràng; có thể xây dựng snapshot có phần tử bất biến và publish an toàn ở những mốc cập nhật. Wrapper không thay thế cơ chế đồng bộ.

**Bài H — Xác định phạm vi sửa được của interface.** API khai báo trả `List<String>`. Có thể suy luận caller được gọi `add` không? **Đáp án:** Không. Interface `List` có thao tác sửa nhưng một implementation có thể từ chối bằng `UnsupportedOperationException`. Javadoc/hợp đồng của phương thức phải nói rõ kết quả có thể sửa hay chỉ đọc.

### Checklist hoàn thành

- [ ] Phân biệt được mutable collection, unmodifiable snapshot và unmodifiable live view.
- [ ] Chọn `List`/`Set`/`Map` theo yêu cầu trùng lặp, thứ tự và ánh xạ khóa-giá trị.
- [ ] Biết khi nào dùng `List.of` và khi nào cần `List.copyOf` từ nguồn có sẵn.
- [ ] Hiểu giới hạn `null`, duplicate keys và merge function với `Collectors.toUnmodifiableMap`.
- [ ] Không giả định `Collectors.toList()` có implementation hay mutability cụ thể.
- [ ] Phân biệt unmodifiable cấu trúc với bất biến sâu của phần tử.
- [ ] Không ngộ nhận chỉ đọc là thread-safe hoặc `final` làm collection bất biến.
- [ ] Chạy `CollectionChoiceLab.java` và đối chiếu **13 dòng stdout**.
- [ ] Thiết kế được flow **mutable trong lúc xây dựng → snapshot khi phát hành**.
- [ ] Có thể giải thích quyết định chọn cấu trúc bằng ownership, contract, chi phí và chính sách cập nhật.

## 14. Ghi nhớ để áp dụng

Khi **còn cần sửa**, chọn cấu trúc mutable thích hợp và giữ quyền thay đổi ở đúng thành phần sở hữu dữ liệu. Khi **công bố trạng thái đã hoàn tất**, dùng `copyOf` hoặc collector không cho sửa để người nhận không thể thay đổi cấu trúc và thay đổi cấu trúc nguồn về sau không làm lệch snapshot. Chỉ dùng `Collections.unmodifiableList` cho dữ liệu có chủ ý phản ánh thay đổi của nguồn và được tài liệu hóa. Nếu phần tử mutable, có nhiều thread hoặc dữ liệu có null, phải giải quyết các yêu cầu ấy riêng; từ “read-only” không thay thế hợp đồng thiết kế.

Những lựa chọn này phù hợp với Java hiện đại. Không cần dùng bản Java 10 đã hết vòng đời để luyện API Java 10 vẫn được hỗ trợ trong các JDK về sau.

## Tài liệu chính thức để tra cứu

- [Oracle Java 25 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html) — khi nào dùng collection mutable/unmodifiable, `copyOf` và các ví dụ snapshot.
- [Oracle Java 25 API — List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html) — `List.of`, `List.copyOf`, tính unmodifiable, null, thứ tự và tính bất biến nông.
- [Oracle Java 25 API — Set](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html) — `Set.copyOf`, cách xử lý phần tử trùng và lưu ý thứ tự.
- [Oracle Java 25 API — Map](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html) — `Map.of`, `Map.copyOf` và hạn chế null.
- [Oracle Java 25 API — Collections](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html) — wrapper `Collections.unmodifiableList` là view.
- [Oracle Java 25 API — Collectors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html) — `toUnmodifiableList/Set/Map`, merge function và `toCollection`.