# Ranh giới giữa quyền sở hữu cấu trúc và quyền sở hữu phần tử trong thiết kế dữ liệu chỉ đọc (Java 10+)

## 1. Mục tiêu bài học

Khi thiết kế API Java trả về một `List`, `Set` hoặc `Map` **chỉ đọc**, câu hỏi “người gọi có thể sửa collection không?” mới giải quyết **một phần** vấn đề. Cần hỏi thêm: “**ai còn quyền thay đổi các object được chứa trong collection?**”.

Ví dụ:

```java
var item = new MutableItem("P1", "Bản nháp");
var items = java.util.List.of(item);
```

`List.of` (Java 9+) trả về một `List` không thể thay đổi cấu trúc qua API `List`. Nhưng nếu `MutableItem` có phương thức `rename`, người đang giữ reference `item` vẫn có thể thay đổi tên mà người đọc `items.get(0)` quan sát được. Vì vậy, **collection không sửa được không đồng nghĩa đồ thị dữ liệu bên trong đã bất biến**.

Từ Java 10, `List.copyOf`, `Set.copyOf` và `Map.copyOf` giúp lấy kết quả *unmodifiable* từ một collection/map nguồn; tuy vậy các phương thức này **không thực hiện deep copy** mọi phần tử. Bài học phân biệt rạch ròi:

- **Quyền sở hữu cấu trúc (*structural ownership*)**: ai được thêm, xóa, đổi vị trí, thay phần tử hoặc sửa ánh xạ khóa–giá trị?
- **Quyền sở hữu phần tử (*element ownership*)**: ai đang giữ reference đến các object nằm trong collection, và ai có quyền thay đổi trạng thái các object đó?
- **Ranh giới API**: khi dữ liệu đi từ bên gọi vào một đối tượng, hoặc được trả ra ngoài, những reference nào vẫn được chia sẻ?
- **Giá trị snapshot thực tế**: muốn một kết quả ổn định chỉ về *cấu trúc*, hay cả về *trạng thái lồng nhau*?

Đây là nguyên tắc thiết kế vẫn áp dụng với Java hiện hành, không phụ thuộc lớp triển khai nội bộ của JDK.

## 2. Java không có cơ chế ownership tự động cho mọi reference

Trong Java, các biến có kiểu tham chiếu trỏ tới object. Khi hai biến trỏ đến cùng object, đây là tình huống **aliasing**:

```java
var source = new java.util.ArrayList<String>();
var alias = source;

alias.add("A");
System.out.println(source); // [A]
```

`source` và `alias` cùng tham chiếu một `ArrayList`, nên sửa qua biến nào cũng thay đổi cùng object.

Từ “quyền sở hữu” trong bài là **quy ước thiết kế và hợp đồng API**, không phải một từ khóa `owner` của Java hay cơ chế bắt buộc tương tự *linear types*. Java không tự cấm mọi alias; muốn bảo vệ dữ liệu, lập trình viên phải thiết kế **hợp đồng mutability**, encapsulation và defensive copying phù hợp.

Đối với collection, cần nhìn hai tầng:

```text
Reference của người gọi
       |
       v
Collection / cấu trúc danh sách
       |-- tham chiếu --> Element A (có thể mutable)
       |-- tham chiếu --> Element B (có thể mutable)
       |-- tham chiếu --> Element C (có thể mutable)
              ^
              |
    Reference khác vẫn có thể giữ Element C
```

Dù reference của người gọi không được quyền `add`/`remove`, reference khác đến **Element C** vẫn có thể sửa object đó. Vì vậy, “đã chặn sửa List” và “đã chặn sửa trạng thái của các phần tử” là **hai bảo đảm khác nhau**.

## 3. Các thao tác nào thuộc về cấu trúc, thao tác nào thuộc về phần tử?

Giả sử có `List<MutableItem>` với các object `MutableItem` có trường `label` có thể thay đổi.

| Thao tác | Nó tác động lên tầng nào? | Nếu dùng `List.copyOf` thì sao? |
| --- | --- | --- |
| `list.add(item)` | Cấu trúc List: thêm một phần tử | Bị từ chối với `UnsupportedOperationException` |
| `list.remove(0)` | Cấu trúc List: xóa reference | Bị từ chối |
| `list.set(0, another)` | Cấu trúc List: thay reference tại vị trí | Bị từ chối |
| `list.sort(...)` | Thứ tự các reference trong List | Bị từ chối với List không sửa được |
| `list.get(0)` | Đọc reference của phần tử | Hợp lệ |
| `list.get(0).rename("Mới")` | **Trạng thái bên trong phần tử** | Có thể hợp lệ nếu `MutableItem.rename` cho phép |
| `item.rename("Mới")` qua một alias khác | Trạng thái phần tử, ngoài List | Vẫn có thể thay đổi thứ mà List quan sát |
| `list.get(0).details().put(...)` | Dữ liệu lồng bên trong phần tử | Có thể thay đổi nếu accessor trả ra một Map mutable |

Điểm mấu chốt: một unmodifiable List **không có quyền ngăn mọi phương thức của object phần tử**. Nó chỉ đảm bảo các phép thay đổi List theo hợp đồng của nó không được thực hiện.

Với `Map<K,V>`, ngoài cấu trúc ánh xạ (`put`, `remove`, `replace`), còn có trạng thái của **khóa** và **giá trị**. Với `Set<E>`, object phần tử chính là thứ dùng cho kiểm tra membership/uniqueness. Các tầng sở hữu này phải được xem xét riêng.

## 4. Ba kiểu chia sẻ collection cần phân biệt

### 4.1. Alias trực tiếp của collection mutable

```java
var source = new java.util.ArrayList<>(java.util.List.of("A"));
var exposed = source; // Cùng một object
exposed.add("B");
System.out.println(source); // [A, B]
```

Người gọi có thể sửa **cấu trúc** qua `exposed`. Đây không phải API chỉ đọc. Cả hai bên đều nắm reference đến cùng collection.

### 4.2. `Collections.unmodifiableList`: khóa thao tác qua view, không tách cấu trúc

```java
var source = new java.util.ArrayList<>(java.util.List.of("A"));
var view = java.util.Collections.unmodifiableList(source);

source.add("B");
System.out.println(view); // [A, B]
```

`view.add("C")` sẽ ném `UnsupportedOperationException`. Nhưng nguồn `source` vẫn thuộc bên đang nắm nó và có thể sửa; view **đọc xuyên qua (*read through*)** tới backing list. Khi `source` thêm `"B"`, `view` nhìn thấy.

Đây là lựa chọn hợp lý nếu API **chủ động muốn cung cấp một view chỉ đọc nhưng luôn phản ánh trạng thái cập nhật của nguồn**. Nó **không** phải lựa chọn đúng nếu API hứa rằng dữ liệu không đổi kể từ lúc trả về.

### 4.3. `List.copyOf`: tách cấu trúc nguồn sau thời điểm copy

```java
var source = new java.util.ArrayList<>(java.util.List.of("A"));
var snapshot = java.util.List.copyOf(source);

source.add("B");
System.out.println(snapshot); // [A]
```

`List.copyOf` (Java 10+) trả một List **không sửa được** chứa các phần tử theo thứ tự duyệt của nguồn tại thời điểm tạo. Thay đổi **cấu trúc** của `source` sau đó không được phản ánh vào `snapshot`.

Tuy nhiên, `snapshot` chỉ có bảo đảm snapshot ở **tầng cấu trúc**. Nếu phần tử chứa object mutable, các **reference phần tử** vẫn được chia sẻ. Không được gọi đây là deep copy.

### 4.4. Bảng chọn theo hợp đồng

| Cách tạo reference trả ra | Người gọi có thể sửa cấu trúc qua kết quả? | Nguồn thêm/xóa phần tử sau đó có phản ánh vào kết quả? | Object phần tử được sao chép sâu? |
| --- | --- | --- | --- |
| `return source;` với `ArrayList` mutable | Có | Có, vì cùng object | Không |
| `return Collections.unmodifiableList(source);` | Không | **Có thể có**, vì backing vẫn là `source` | Không |
| `return List.copyOf(source);` | Không | **Không** đối với thay đổi cấu trúc sau khi copy | Không |
| `return Collections.unmodifiableList(new ArrayList<>(source));` | Không | Không với thay đổi cấu trúc của `source` sau copy, nếu bản copy không bị lộ ra ngoài | Không |
| Chuyển phần tử thành **immutable value/DTO**, rồi `List.copyOf` | Không | Không với cấu trúc nguồn; trạng thái DTO cũng có thể ổn định | Chỉ phần dữ liệu đã chủ động chuyển thành value bất biến |

**Lưu ý:** nếu `source` vốn là unmodifiable List phù hợp, `List.copyOf(source)` **được phép tái sử dụng chính object List**, không bảo đảm tạo instance mới. Điều đó không làm yếu hợp đồng về nội dung và tính unmodifiable. Đừng assert `snapshot != source` như một yêu cầu của API.

## 5. Vì sao `List.copyOf` vẫn có thể cho thấy phần tử thay đổi?

Xét một object với thuộc tính mutable:

```java
class MutableItem {
    private String label;

    MutableItem(String label) {
        this.label = label;
    }

    String label() {
        return label;
    }

    void rename(String next) {
        this.label = next;
    }
}
```

Trong một phương thức chứa các lệnh sau:

```java
var item = new MutableItem("Cũ");
var source = new java.util.ArrayList<MutableItem>();
source.add(item);

var snapshot = java.util.List.copyOf(source);

source.clear();        // Cấu trúc source thay đổi
item.rename("Mới");    // Trạng thái object item thay đổi

System.out.println(snapshot.size());         // 1
System.out.println(snapshot.get(0).label()); // Mới
```

Hai đoạn trên là **mã minh họa**, cần đặt định nghĩa lớp và câu lệnh vào ngữ cảnh Java thích hợp; chương trình độc lập hoàn chỉnh ở phần sau.

Vì sao có kết quả đó?

1. `List.copyOf` tách cấu trúc khỏi thao tác `source.clear()` nên snapshot vẫn có một phần tử.
2. `snapshot.get(0)` là reference tới **chính object `item`** đã có trước đó.
3. `item.rename("Mới")` đổi trạng thái object đó, nên `snapshot.get(0).label()` đọc được `"Mới"`.

Do đó, **sao chép một collection không đồng nghĩa sao chép object được chứa**. Đây là sự khác nhau giữa *shallow copy* (sao chép cấu trúc/references) và *deep copy* hoặc *immutable projection* (xử lý toàn bộ dữ liệu cần giữ ổn định).

## 6. Ranh giới ownership khi nhận dữ liệu vào một class

Giả sử một class xây dựng cấu hình từ danh sách đầu vào:

```java
final class BadCatalog {
    private final java.util.List<MutableItem> items;

    BadCatalog(java.util.List<MutableItem> input) {
        this.items = input;
    }
}
```

Dù `items` được khai báo `final`, điều đó chỉ có nghĩa **field không thể được gán sang reference khác sau khi khởi tạo**. Nó **không** làm object List hoặc các phần tử của List bất biến. Người gọi vẫn có thể `input.add(...)`, `input.remove(...)` hoặc sửa trạng thái phần tử; `BadCatalog` thấy cùng dữ liệu thay đổi.

### 6.1. Bảo vệ cấu trúc đầu vào

Một bước cải thiện:

```java
final class ShallowCatalog {
    private final java.util.List<MutableItem> items;

    ShallowCatalog(java.util.List<MutableItem> input) {
        this.items = java.util.List.copyOf(input);
    }
}
```

`ShallowCatalog` không phản ánh thay đổi thêm/xóa phần tử trên `input` sau khi khởi tạo. Tuy nhiên, **nó vẫn chia sẻ các object `MutableItem`** với người gọi.

Nếu yêu cầu là “Catalog luôn hiển thị nhãn tại thời điểm khởi tạo”, thiết kế này **chưa đủ**.

### 6.2. Bảo vệ cả trạng thái được công bố

Thay vì giữ reference đến object mutable bên ngoài, ta chuyển các dữ liệu cần thiết thành một giá trị bất biến:

```java
record ItemView(String code, String label) {}
```

`ItemView` ở đây chỉ chứa hai `String` vốn bất biến. Trong constructor, thay mỗi `MutableItem` nguồn bằng một `ItemView` mới lấy giá trị hiện có:

```java
var converted = new java.util.ArrayList<ItemView>();
for (var item : input) {
    converted.add(new ItemView(item.code(), item.label()));
}
var snapshot = java.util.List.copyOf(converted);
```

Khi người gọi sửa một `MutableItem` nguồn sau đó, `ItemView` đã tạo **không đổi**. Bây giờ ta bảo vệ cả:

- **cấu trúc**: `snapshot` không cho thay đổi phần tử;
- **các giá trị thuộc API này**: `ItemView` giữ `code` và `label` bằng những `String` không thể sửa nội tại.

Đây là một **immutable projection**: chỉ trích xuất dữ liệu cần thiết thành kiểu mới, không nhất thiết phải sao chép toàn bộ đồ thị object nguồn. Nếu object còn chứa collection lồng nhau, mảng hoặc component mutable khác, phải xử lý từng tầng cần bảo vệ; chỉ dùng `record` không làm chúng bất biến sâu.

**Quan trọng với đồng thời:** việc đọc nguồn để xây snapshot cần được thực hiện trong thời điểm nguồn ổn định hoặc dưới cơ chế phối hợp phù hợp; `List.copyOf` và vòng lặp chuyển đổi không tự tạo một snapshot nguyên tử nếu bên khác đang sửa dữ liệu cùng lúc.

## 7. Ranh giới ownership khi trả dữ liệu ra khỏi class

Sau khi lưu một danh sách dữ liệu nội bộ, class có thể thiết kế accessor theo hợp đồng:

### 7.1. Trả trực tiếp danh sách mutable nội bộ — rò rỉ cấu trúc

```java
// Không nên dùng nếu class cần sở hữu cấu trúc độc quyền:
List<ItemView> getItems() {
    return mutableInternalItems;
}
```

Người nhận có thể `add`/`clear` và làm thay đổi state của class từ bên ngoài.

### 7.2. Trả một view không sửa được của danh sách nội bộ

```java
List<ItemView> getItems() {
    return Collections.unmodifiableList(mutableInternalItems);
}
```

Người nhận không sửa qua view được; nhưng nếu class chủ sở hữu vẫn sửa `mutableInternalItems`, người nhận **có thể thấy những cập nhật đó**. Đây là hợp đồng *live read-only view*, không phải snapshot.

### 7.3. Trả snapshot cấu trúc

```java
List<ItemView> getItems() {
    return List.copyOf(mutableInternalItems);
}
```

Kết quả không phản ánh thêm/xóa phần tử sau đó từ `mutableInternalItems`. Với các `ItemView` bất biến như ví dụ này, kết quả là một **snapshot giá trị ổn định của những trường đã được mô hình hóa**.

### 7.4. Đã lưu dữ liệu bất biến thì có thể trả cùng reference

Nếu class đã khởi tạo:

```java
private final List<ItemView> items;
```

và **không có alias mutable của cấu trúc/phần tử** làm sai hợp đồng, accessor có thể trả:

```java
List<ItemView> items() {
    return items;
}
```

Không cần sao chép mỗi lần chỉ để “cho chắc”; điều cốt lõi là **đối tượng đã được bảo vệ đúng từ lúc tạo** và không có đường sửa ngầm khác. Nếu `ItemView` chứa một `List` mutable hoặc `byte[]` mà accessor trả nguyên trạng, đánh giá phải thay đổi.

## 8. Mảng, List lồng nhau và record: `final` không đủ

### 8.1. Mảng luôn có thể thay đổi phần tử

```java
final class Packet {
    private final byte[] data;

    Packet(byte[] input) {
        this.data = input.clone(); // Sao chép lúc nhận vào
    }

    byte[] data() {
        return data.clone();       // Sao chép khi trả ra
    }
}
```

Đây là một class minh họa độc lập về ownership mảng. Nếu constructor chỉ gán `this.data = input`, người gọi vẫn sửa mảng bên trong bằng reference `input`. Nếu accessor trả `return data;`, người nhận sửa được chính mảng nội bộ. **Sao chép ở cả hai ranh giới** tránh hai đường rò rỉ đó.

Phép `clone()` ở đây phù hợp cho `byte[]` vì các phần tử là primitive. Với mảng chứa object mutable, clone mảng **chỉ sao chép cấu trúc mảng**, còn phần tử vẫn dùng chung reference; cần đánh giá từng object.

### 8.2. Record có field `final` nhưng component có thể mutable

`record` trở thành tính năng chính thức từ Java 16. Nó rất hữu ích để biểu diễn dữ liệu, nhưng:

```java
record UnsafeRecord(java.util.List<String> tags) {}
```

Record này có field `tags` final nhưng **không tự bảo vệ List đầu vào**:

```java
var input = new java.util.ArrayList<>(
        java.util.List.of("alpha"));

var unsafe = new UnsafeRecord(input);
input.add("beta");

System.out.println(unsafe.tags()); // [alpha, beta]
```

Một cách làm tốt hơn với component List là defensive copy trong compact constructor:

```java
record SafeRecord(java.util.List<String> tags) {
    SafeRecord {
        tags = java.util.List.copyOf(tags);
    }
}
```

Khi đó `SafeRecord` cất một List không sửa được, tách khỏi việc thêm/xóa phần tử trên `input` sau khi tạo. Vì phần tử là `String` bất biến, ví dụ này đạt hợp đồng dữ liệu ổn định theo giá trị. Với `List<MutableItem>`, vẫn phải chuyển phần tử mutable hoặc tạo bản sao đúng nghĩa cho từng phần tử.

**Phân biệt phiên bản:** `List.copyOf` có từ Java 10; `record` có từ Java 16 và được dùng trong ví dụ Java 17+ vì là tính năng ổn định, còn áp dụng hiện nay. Với codebase bắt buộc chạy Java 10, có thể thay record bằng class `final` có các field private final, constructor và accessor được thiết kế tương đương.

## 9. Ví dụ Java 17+ đầy đủ: ba ranh giới, ba kết quả

Lưu toàn bộ nội dung sau vào tệp **`OwnershipBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class OwnershipBoundaryDemo {

    static final class MutableItem {
        private final String code;
        private String label;

        MutableItem(String code, String label) {
            this.code = Objects.requireNonNull(code);
            this.label = Objects.requireNonNull(label);
        }

        String code() {
            return code;
        }

        String label() {
            return label;
        }

        void rename(String next) {
            label = Objects.requireNonNull(next);
        }
    }

    // Hai String là giá trị bất biến.
    record ItemView(String code, String label) {}

    static final class Catalog {
        private final List<ItemView> entries;

        Catalog(List<MutableItem> source) {
            Objects.requireNonNull(source);
            var converted = new ArrayList<ItemView>();
            for (var item : source) {
                var safeItem = Objects.requireNonNull(item);
                converted.add(new ItemView(
                        safeItem.code(), safeItem.label()));
            }
            this.entries = List.copyOf(converted);
        }

        List<ItemView> entries() {
            return entries;
        }
    }

    record UnsafeRecord(List<String> tags) {}

    record SafeRecord(List<String> tags) {
        SafeRecord {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        var item = new MutableItem("P1", "old");
        var input = new ArrayList<MutableItem>();
        input.add(item);

        // View thấy thay đổi của backing list.
        var liveView = Collections.unmodifiableList(input);

        // Snapshot cấu trúc nhưng vẫn giữ reference MutableItem.
        var shallow = List.copyOf(input);

        // Snapshot các giá trị thành ItemView bất biến.
        var catalog = new Catalog(input);

        input.add(new MutableItem("P2", "second"));
        item.rename("new");

        System.out.println("inputSize=" + input.size());
        System.out.println("viewSize=" + liveView.size());
        System.out.println("shallowSize=" + shallow.size());
        System.out.println("shallowLabel=" + shallow.get(0).label());
        System.out.println("catalogSize=" + catalog.entries().size());
        System.out.println(
                "catalogLabel=" + catalog.entries().get(0).label());

        // Record không mặc nhiên sao chép List component.
        var tags = new ArrayList<>(List.of("alpha"));
        var unsafe = new UnsafeRecord(tags);
        var safe = new SafeRecord(tags);
        tags.add("beta");

        System.out.println("recordUnsafe=" + unsafe.tags());
        System.out.println("recordSafe=" + safe.tags());

        try {
            shallow.add(new MutableItem("P3", "third"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("shallowAddRejected=true");
        }

        try {
            safe.tags().add("gamma");
        } catch (UnsupportedOperationException expected) {
            System.out.println("recordAddRejected=true");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 OwnershipBoundaryDemo.java
java OwnershipBoundaryDemo
```

**Kết quả stdout chính xác:**

```text
inputSize=2
viewSize=2
shallowSize=1
shallowLabel=new
catalogSize=1
catalogLabel=old
recordUnsafe=[alpha, beta]
recordSafe=[alpha]
shallowAddRejected=true
recordAddRejected=true
```

### Phân tích theo từng tầng ownership

1. `inputSize=2`: chủ sở hữu `input` đã thêm sản phẩm thứ hai.
2. `viewSize=2`: `Collections.unmodifiableList(input)` chỉ chặn sửa qua view, **không tách** khỏi list nguồn.
3. `shallowSize=1`: `List.copyOf(input)` đã tách **cấu trúc** tại thời điểm sao chép; việc thêm phần tử về sau không được phản ánh.
4. `shallowLabel=new`: object `MutableItem` đầu tiên vẫn được chia sẻ giữa `item` và `shallow.get(0)`; thay đổi trường `label` được nhìn thấy.
5. `catalogSize=1` và `catalogLabel=old`: `Catalog` tạo `ItemView` mới, chứa hai chuỗi bất biến được chụp tại thời điểm khởi tạo, rồi khóa cấu trúc bằng `List.copyOf`. Những thay đổi sau đó của `input` hoặc `item` không ảnh hưởng các giá trị đã công bố.
6. `recordUnsafe=[alpha, beta]`: record không tự sao chép List component, nên giữ alias mutable. `recordSafe=[alpha]`: compact constructor đã tạo snapshot bằng `List.copyOf`.
7. Hai dòng cuối chứng minh `shallow` và `safe.tags()` đều **không sửa được qua reference trả về**.

Ví dụ này có thể chạy ổn định trên Java 17+, không dùng tính năng preview. Các factory `List.of`/`List.copyOf` vẫn thuộc API hiện hành.

## 10. Với `Map` và `Set`, ownership phần tử có thể làm sai cả tra cứu

### 10.1. Mutable key của Map

`Map.copyOf` (Java 10+) trả một Map unmodifiable; tuy nhiên nó **không clone khóa và giá trị**. Nếu khóa là object mutable và việc sửa object làm thay đổi `equals`/`hashCode`, khả năng tra cứu có thể bị phá vỡ.

```java
// Ví dụ về thiết kế cần tránh:
// key có hashCode() dựa trên trường code mutable.
// Map.copyOf(source) không làm key trở nên bất biến.
// Nếu code bị sửa sau khi tạo Map, việc get(key) có thể bất thường.
```

Java `Map` cũng cảnh báo không được dựa vào hành vi khi một key bị sửa theo cách ảnh hưởng so sánh `equals` lúc đang được dùng làm khóa. Để API chỉ đọc ổn định, ưu tiên **khóa bất biến về mặt giá trị** (ví dụ `String`), hoặc ánh xạ object nguồn sang một kiểu khóa bất biến trước khi tạo bản sao.

### 10.2. Mutable value của Map

`Map.copyOf` không cho thay ánh xạ qua `put`, nhưng một giá trị `V` là object mutable vẫn có thể đổi trạng thái qua reference khác. Nếu nhu cầu là snapshot các giá trị, hãy chuyển giá trị sang immutable DTO trước khi gọi `Map.copyOf`.

### 10.3. Mutable element của Set

`Set.copyOf` chặn thêm/xóa phần tử qua Set mới, **không** làm các object phần tử bất biến. Nếu `equals`/`hashCode` của một phần tử phụ thuộc state mutable, sửa state có thể làm sai membership/deduplication. Vì thế, vấn đề sở hữu phần tử thường **nguy hiểm hơn** khi object được dùng làm key hoặc phần tử Set so với một phần tử List chỉ đọc theo chỉ số.

**Lưu ý:** `Set.of`/`Map.of` và các bản `copyOf` không cho `null` theo hợp đồng tương ứng; đừng dùng chúng nếu chính sách dữ liệu bắt buộc cho phép `null` mà chưa có cách biểu diễn khác.

## 11. Thread safety và thời điểm tạo snapshot

Một collection chỉ đọc **không đồng nghĩa tất cả tác vụ với nó đều thread-safe**:

- `Collections.unmodifiableList(mutable)` là view; nếu backing bị sửa đồng thời mà không phối hợp, các thao tác đọc/duyệt có thể gặp trạng thái không nhất quán hoặc ngoại lệ theo đặc tính của collection nguồn.
- `List.copyOf(source)` cho snapshot cấu trúc sau khi tạo, **nhưng không tự bảo đảm snapshot nguyên tử** khi nguồn đang bị sửa trong lúc copy. Cần bảo đảm nguồn ổn định hoặc áp dụng chính sách đồng bộ phù hợp khi tạo dữ liệu.
- Nếu phần tử là mutable và được nhiều luồng chia sẻ, thay đổi trạng thái của phần tử vẫn cần các quy tắc visibility và đồng bộ của Java.
- Một đối tượng chứa `private final List<T>` có lợi cho thiết kế, nhưng `final` không biến mọi object được trỏ đến thành immutable. Cần đóng các đường alias mutable và công bố object an toàn theo Java Memory Model.

Nếu dữ liệu đã thực sự được biểu diễn bằng các phần tử bất biến và collection không sửa được, các thao tác **đọc** thông thường có thể đơn giản hơn nhiều; vẫn phải bảo đảm **safe publication** của object và hiểu đúng API được sử dụng.

Không dùng việc một test chạy đồng thời “có vẻ ổn” làm bằng chứng rằng ownership đã được giải quyết.

## 12. Checklist thiết kế API chỉ đọc

Trước khi trả dữ liệu ra ngoài module, kiểm tra những câu hỏi sau:

1. **Ai sở hữu cấu trúc gốc?** Có nơi nào khác giữ `ArrayList`, `HashMap` hoặc một collection mutable và có thể sửa nó sau khi API trả kết quả không?
2. **Hợp đồng muốn view hay snapshot?** Nếu muốn cập nhật live qua nguồn, `Collections.unmodifiableX` có thể phù hợp; nếu muốn không phản ánh thay đổi cấu trúc nguồn, chọn `List.copyOf`/`Set.copyOf`/`Map.copyOf` hoặc bản sao tương ứng.
3. **Những phần tử có mutable không?** Kiểm tra field, mảng, collection lồng nhau, đối tượng do thư viện bên ngoài sở hữu và các accessor trả về mutable reference.
4. **Cần snapshot ở độ sâu nào?** Chỉ số lượng/thứ tự phần tử, hay phải giữ nguyên cả giá trị của từng object? Dùng immutable projection hoặc bản sao ở đúng tầng.
5. **Có rò rỉ khi nhận dữ liệu?** Constructor có lưu thẳng list/mảng của người gọi vào field không?
6. **Có rò rỉ khi trả dữ liệu?** Accessor có trả trực tiếp list/mảng mutable nội bộ hoặc object mutable đang được chia sẻ không?
7. **Có quy tắc `null` và thứ tự không?** Các factory `of`/`copyOf` có thể từ chối `null`; `List` có thứ tự, còn `Set.of` và `Map.of` không hứa một thứ tự duyệt cố định.
8. **Có đồng thời không?** Tạo snapshot phải đọc nguồn nhất quán; đối tượng mutable được chia sẻ giữa các thread cần chiến lược phù hợp.
9. **Có phụ thuộc identity hay lớp triển khai không?** Các kết quả factory unmodifiable có thể là value-based, không hứa đối tượng mới hoặc class nội bộ cụ thể. Chỉ dựa trên hợp đồng công khai.
10. **Lỗi có được kiểm thử theo đúng tầng?** Kiểm thử thao tác `add`/`put` bị từ chối **và** kiểm thử việc sửa nguồn hoặc object phần tử ở bên ngoài không làm sai hợp đồng mong muốn.

## 13. Những ngộ nhận cần tránh

**Ngộ nhận 1: “`List.copyOf` là deep copy.”**  
Sai. Nó tạo kết quả tách cấu trúc khỏi những sửa đổi nguồn sau đó, nhưng vẫn chia sẻ reference object phần tử.

**Ngộ nhận 2: “`Collections.unmodifiableList` là snapshot bất biến.”**  
Sai. Nó là **view** được backing bởi nguồn. Người khác vẫn có thể sửa nguồn qua reference gốc.

**Ngộ nhận 3: “`private final List<T>` đủ khiến cả dữ liệu bất biến.”**  
Sai. `final` bảo vệ việc gán lại field, không khóa trạng thái của List hoặc các object bên trong.

**Ngộ nhận 4: “Record luôn bất biến sâu.”**  
Sai. Record có component fields final, nhưng component kiểu `List`, `Map`, array hoặc object mutable có thể vẫn chia sẻ state. Dùng defensive copy ở constructor/accessor khi cần.

**Ngộ nhận 5: “Không sửa được cấu trúc thì thay đổi `item.rename(...)` cũng bị chặn.”**  
Sai. Mutator của phần tử hoạt động trên **object phần tử**, không phải phương thức mutator của List.

**Ngộ nhận 6: “Đã tạo snapshot thì đọc đồng thời luôn an toàn.”**  
Sai. Thời điểm copy có thể không nhất quán nếu nguồn bị sửa trong lúc đọc; phần tử mutable vẫn có thể có data race.

**Ngộ nhận 7: “Dùng `var` làm mất quyền kiểm tra kiểu.”**  
Sai. `var snapshot = List.copyOf(source);` suy luận một kiểu tĩnh như `List<MutableItem>`. `var` không kiểm soát ownership hoặc mutability, cũng không khiến Java trở thành ngôn ngữ kiểu động.

**Ngộ nhận 8: “Dùng `==` để kiểm tra đã sao chép hay chưa.”**  
Sai. Các factory không hứa identity mới; so sánh nội dung bằng `equals` và kiểm tra hành vi được đặc tả.

## 14. Tự kiểm tra kiến thức

**Câu 1:** `var snapshot = List.copyOf(source);`; sau đó `source.add(x)`. `snapshot` có tự thêm `x` không?  
**Đáp án:** Không. Thay đổi cấu trúc `source` sau thời điểm copy không được phản ánh trong kết quả.

**Câu 2:** `snapshot.get(0).rename("Mới")` có thể biên dịch và chạy không?  
**Đáp án:** Có thể, nếu kiểu phần tử có phương thức `rename` và quyền truy cập phù hợp. `List.copyOf` chỉ cấm sửa **collection**, không cấm phương thức của phần tử.

**Câu 3:** Nếu `Collections.unmodifiableList(source)` được trả cho API, phía giữ `source` có thể làm cho view thấy phần tử mới không?  
**Đáp án:** Có. View đọc qua backing list; cấu trúc nguồn thay đổi có thể xuất hiện ở kết quả.

**Câu 4:** Muốn snapshot các nhãn của `MutableItem`, có đủ nếu chỉ dùng `List.copyOf(List<MutableItem>)` không?  
**Đáp án:** Không. Cần sao chép hoặc chuyển **giá trị nhãn** sang một kiểu bất biến như `ItemView(String code, String label)`, rồi khóa cấu trúc của danh sách kết quả.

**Câu 5:** `record SafeRecord(List<String> tags)` có chắc chắn an toàn không nếu không có constructor tùy chỉnh?  
**Đáp án:** Không. Record không tự defensive-copy List component. Có thể viết compact constructor `tags = List.copyOf(tags)`; vì `String` bất biến, cách này ổn định cả cấu trúc lẫn các giá trị chuỗi.

**Câu 6:** Vì sao mutable key trong `Map.copyOf` có thể gây lỗi logic?  
**Đáp án:** `Map.copyOf` không clone key. Nếu `equals`/`hashCode` của key thay đổi, tính nhất quán của tra cứu có thể bị phá vỡ dù map không thể `put`.

## 15. Ghi nhớ

1. **Quyền sở hữu cấu trúc** và **quyền sở hữu object phần tử** là hai ranh giới khác nhau. Java không tự động cưỡng chế ownership chỉ bằng kiểu `List` hay `var`.
2. `Collections.unmodifiableList` là **view**; `List.copyOf` (Java 10+) tạo kết quả không phản ánh sửa đổi cấu trúc sau đó; **cả hai đều không deep-copy phần tử**.
3. Khi bảo vệ API, đánh giá **cả đầu vào và đầu ra**: sao chép hoặc chuyển đổi dữ liệu phù hợp lúc nhận, không làm lộ mutable reference khi trả.
4. `final` và `record` không tự tạo bất biến sâu. Dùng giá trị bất biến, immutable projection, defensive copies của các collection/mảng lồng nhau khi cần.
5. `Map`/`Set` với key/element mutable có thêm rủi ro về `equals`/`hashCode`, không chỉ rủi ro hiển thị thông tin mới.
6. Một snapshot muốn ổn định phải có **nguồn đọc nhất quán** và **phần tử được bảo vệ đúng độ sâu**. Read-only không tự bảo đảm thread safety.
7. Thiết kế theo **hợp đồng quan sát được**, không phụ thuộc lớp triển khai, identity hoặc hành vi ngẫu nhiên của một bản JDK.

## Tài liệu tham khảo chính thức còn áp dụng

- Java SE 26 — `List`, *Unmodifiable Lists*, `List.copyOf` và quy tắc khi phần tử mutable: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html
- Java SE 26 — `Collections.unmodifiableList` và ý nghĩa của view được backing bởi List nguồn: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html
- Java SE 26 — `Map`, cảnh báo về mutable keys và unmodifiable maps: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html
- Java SE 26 — `Set`, unmodifiable sets và các rủi ro khi phần tử mutable: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html
- Java SE 25 — Record Classes và compact canonical constructors: https://docs.oracle.com/en/java/javase/25/language/records.html
- Dev.java — Using Records to Model Immutable Data, defensive copy mutable component: https://dev.java/learn/using-record-to-model-immutable-data/
- OpenJDK JEP 286 — Local-Variable Type Inference (Java 10): https://openjdk.org/jeps/286
