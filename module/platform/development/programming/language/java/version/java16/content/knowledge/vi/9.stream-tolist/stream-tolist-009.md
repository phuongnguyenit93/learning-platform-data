# Tạo bản sao `ArrayList` khi bên nhận thực sự cần danh sách mutable

`Stream.toList()` trả về một `List` không sửa đổi được. Nếu bên nhận cần thêm, xóa, thay thế hoặc sắp xếp phần tử, có thể tạo một bản sao mutable bằng constructor `new ArrayList<>(result)`. Cách này tạo một cấu trúc danh sách mới, độc lập với cấu trúc của kết quả ban đầu.

Việc tạo bản sao nên gắn với một nhu cầu cụ thể: bên nhận cần quyền sở hữu một danh sách có thể chỉnh sửa. Nếu không có thao tác sửa đổi, giữ kết quả từ `toList()` giúp tránh một lần cấp phát và sao chép không cần thiết. Nếu ngay từ đầu pipeline cần tạo `ArrayList`, có thể thu thập trực tiếp bằng `Collectors.toCollection(ArrayList::new)`.

## 1. Vì sao cần tạo bản sao?

`Stream.toList()` có từ Java 16 và trả về danh sách unmodifiable. Các thao tác đọc vẫn hoạt động, nhưng mọi mutator method như `add`, `remove`, `set`, `clear`, `replaceAll` hoặc `sort` đều ném `UnsupportedOperationException`.

```java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi").stream().toList();

System.out.println(names.get(0)); // An
names.add("Dung"); // UnsupportedOperationException
```

Nếu yêu cầu nghiệp vụ là tiếp tục chỉnh sửa kết quả, hãy tạo một `ArrayList` mới:

```java
import java.util.ArrayList;
import java.util.List;

List<String> readOnlyNames = List.of("An", "Bình", "Chi").stream().toList();
List<String> editableNames = new ArrayList<>(readOnlyNames);

editableNames.add("Dung");
editableNames.set(0, "Anh");
editableNames.remove("Bình");

System.out.println(readOnlyNames); // [An, Bình, Chi]
System.out.println(editableNames); // [Anh, Chi, Dung]
```

`editableNames` có thể thay đổi cấu trúc mà không làm thay đổi số lượng hoặc thứ tự phần tử trong `readOnlyNames`. Đây là lý do chính để dùng copy constructor tại ranh giới nơi một thành phần cần quyền chỉnh sửa riêng.

## 2. `ArrayList(Collection)` sao chép điều gì?

Constructor `ArrayList(Collection<? extends E>)` tạo một `ArrayList` mới chứa các phần tử của collection đầu vào theo thứ tự iterator của collection đó. Với nguồn là `List`, thứ tự phần tử được giữ lại.

```java
import java.util.ArrayList;
import java.util.List;

List<String> source = List.of("Java", "Stream", "API");
List<String> copy = new ArrayList<>(source);

System.out.println(copy); // [Java, Stream, API]
```

Sau khi tạo bản sao:

- Hai danh sách có cấu trúc riêng. Thêm hoặc xóa phần tử ở `copy` không thay đổi kích thước của `source`.
- `copy` là `ArrayList` mutable, nên có thể gọi các mutator method được `ArrayList` hỗ trợ.
- Các phần tử được sao chép theo tham chiếu. Constructor không tự tạo object mới cho từng phần tử.
- Các phần tử trùng lặp và `null` trong nguồn được giữ lại vì `ArrayList` cho phép cả hai.

Vì vậy, đây là **bản sao nông** (*shallow copy*). Cấu trúc collection được tách riêng, còn object phần tử có thể vẫn được chia sẻ.

## 3. Bản sao nông và object mutable bên trong

Với phần tử immutable như `String`, việc dùng chung tham chiếu không gây ra thay đổi trạng thái. Với object mutable, hai danh sách có thể cùng tham chiếu đến một object; thay đổi object đó thông qua danh sách này sẽ được nhìn thấy khi đọc qua danh sách kia.

```java
import java.util.ArrayList;
import java.util.List;

StringBuilder first = new StringBuilder("Java");
List<StringBuilder> source = List.of(first);
List<StringBuilder> copy = new ArrayList<>(source);

copy.add(new StringBuilder("Stream"));
copy.get(0).append(" 16");

System.out.println(source.size());       // 1
System.out.println(copy.size());         // 2
System.out.println(source.get(0));       // Java 16
System.out.println(copy.get(0));         // Java 16
```

`copy.add(...)` chỉ thay đổi cấu trúc của `copy`, nên `source.size()` vẫn là 1. Nhưng `copy.get(0)` và `source.get(0)` cùng tham chiếu tới `first`; lời gọi `append()` làm thay đổi object mà cả hai danh sách cùng nhìn thấy.

Nếu cần bản sao độc lập cả về trạng thái phần tử, phải tạo object mới cho từng phần tử theo quy tắc của kiểu dữ liệu. Ví dụ, chuyển entity mutable thành record snapshot chứa các giá trị immutable:

```java
import java.math.BigDecimal;
import java.util.List;

class MutableProduct {
    private final String code;
    private BigDecimal price;

    MutableProduct(String code, BigDecimal price) {
        this.code = code;
        this.price = price;
    }

    String code() { return code; }
    BigDecimal price() { return price; }
    void changePrice(BigDecimal newPrice) { this.price = newPrice; }
}

record ProductSnapshot(String code, BigDecimal price) {}

class ProductSnapshots {
    static List<ProductSnapshot> create(List<MutableProduct> products) {
        return products.stream()
            .map(product -> new ProductSnapshot(product.code(), product.price()))
            .toList();
    }

    public static void main(String[] args) {
        MutableProduct product = new MutableProduct("SP-01", new BigDecimal("120.00"));
        List<ProductSnapshot> snapshots = create(List.of(product));

        product.changePrice(new BigDecimal("150.00"));
        System.out.println(snapshots.get(0).price()); // 120.00
        System.out.println(product.price());          // 150.00
    }
}
```

`String` và `BigDecimal` là immutable, nên snapshot không chia sẻ trạng thái mutable của `MutableProduct`. Đây là chuyển đổi dữ liệu theo mô hình miền, khác với việc chỉ sao chép collection.

## 4. Tạo bản sao ở đâu: nơi tạo dữ liệu hay nơi sử dụng?

Vị trí tạo bản sao phụ thuộc vào hợp đồng của phương thức và nhu cầu của bên gọi.

**Bên tạo dữ liệu trả về kết quả chỉ đọc:** nếu phần lớn bên gọi chỉ cần đọc, phương thức có thể trả về kết quả `toList()`. Bên gọi nào thực sự cần sửa sẽ tự tạo bản sao:

```java
import java.util.List;

class NameService {
    List<String> findNames(List<String> source) {
        return source.stream()
            .filter(name -> !name.isBlank())
            .map(String::trim)
            .toList();
    }
}

class NameEditor {
    void edit(NameService service, List<String> source) {
        List<String> editable = new java.util.ArrayList<>(
            service.findNames(source)
        );
        editable.add("Dung");
    }
}
```

Cách này giữ hợp đồng kết quả chỉ đọc ở service và chỉ trả chi phí sao chép cho nơi thật sự cần chỉnh sửa.

**Bên tạo dữ liệu cam kết trả về danh sách mutable:** nếu mọi bên gọi đều cần chỉnh sửa kết quả, service có thể thu thập trực tiếp vào `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

class EditableNameService {
    List<String> findNames(List<String> source) {
        return source.stream()
            .filter(name -> !name.isBlank())
            .map(String::trim)
            .collect(Collectors.toCollection(ArrayList::new));
    }
}
```

Không cần tạo `toList()` rồi lại sao chép sang `ArrayList` trong trường hợp này, vì pipeline có thể thu thập thẳng vào collection đích.

**Bên nhận một `List` không rõ mutability:** nếu một phương thức nhận `List<T>` từ caller nhưng cần chỉnh sửa nội bộ, hãy tạo bản sao trước khi thao tác. Interface `List` không cho biết collection cụ thể có mutable hay không:

```java
import java.util.ArrayList;
import java.util.List;

class NameTools {
    static List<String> appendDefault(List<String> input) {
        List<String> result = new ArrayList<>(input);
        result.add("Mặc định");
        return result;
    }
}
```

Phương thức này không sửa collection mà caller truyền vào. Nó trả về một danh sách mới mà bên gọi có thể tiếp tục chỉnh sửa.

## 5. Không sao chép nếu bên nhận chỉ cần đọc

Tạo bản sao có chi phí bộ nhớ và thời gian tỷ lệ với số phần tử. Với `ArrayList(Collection)`, các tham chiếu phần tử được đưa vào mảng lưu trữ mới. Nếu danh sách lớn và không cần sửa đổi, việc sao chép chỉ làm tăng cấp phát và công việc cần thực hiện.

```java
import java.util.List;

List<String> source = List.of("An", "Bình", "Chi");

List<String> names = source.stream()
    .filter(name -> !name.isBlank())
    .toList();

// Đọc trực tiếp, không cần tạo ArrayList khác.
names.forEach(System.out::println);
```

Nếu cần sắp xếp hoặc biến đổi thứ tự, ưu tiên thực hiện trong pipeline trước khi gọi `toList()`:

```java
import java.util.List;

List<String> source = List.of("An", "Bình", "Chi");

List<String> sortedNames = source.stream()
    .filter(name -> !name.isBlank())
    .map(String::trim)
    .sorted()
    .toList();
```

Chỉ tạo `ArrayList` nếu có yêu cầu chỉnh sửa sau khi thu thập, hoặc API đích yêu cầu một collection mutable cụ thể.

## 6. Bản sao giữ thứ tự, phần tử trùng lặp và null

`ArrayList(Collection)` giữ thứ tự iterator của collection nguồn và không loại bỏ phần tử trùng lặp. Nó cũng chấp nhận null:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> source = Stream.of("An", null, "An", "Bình").toList();
List<String> copy = new ArrayList<>(source);

System.out.println(copy); // [An, null, An, Bình]
copy.add(null);            // Hợp lệ
```

Nếu dữ liệu không được phép chứa null, hãy xác thực hoặc lọc trước khi sao chép. Nếu nghiệp vụ cần giữ null, `ArrayList` có thể lưu chúng. Việc tạo bản sao không tự làm sạch, sắp xếp hay loại bỏ trùng lặp dữ liệu.

## 7. Defensive copy khi thiết kế API

Một class có thể muốn giữ quyền kiểm soát collection nội bộ. Khi nhận collection từ caller, tạo bản sao để caller không thể thay đổi cấu trúc nội bộ qua tham chiếu gốc. Khi trả dữ liệu ra ngoài, có thể trả bản sao mutable nếu hợp đồng cho phép người gọi chỉnh sửa độc lập.

Ví dụ một class lưu danh sách mutable nội bộ nhưng không chia sẻ trực tiếp tham chiếu đó:

```java
import java.util.ArrayList;
import java.util.List;

class Playlist {
    private final List<String> tracks;

    Playlist(List<String> tracks) {
        this.tracks = new ArrayList<>(tracks);
    }

    List<String> editableTracks() {
        return new ArrayList<>(tracks);
    }

    List<String> readOnlyTracks() {
        return List.copyOf(tracks);
    }
}
```

- Constructor sao chép đầu vào để thay đổi cấu trúc list gốc từ caller không ảnh hưởng đến cấu trúc `tracks` nội bộ.
- `editableTracks()` trả về bản sao mutable. Thay đổi bản sao không sửa `tracks` bên trong.
- `readOnlyTracks()` trả về một bản sao danh sách không sửa đổi được và không chấp nhận null; phù hợp khi component bảo đảm không có null và caller chỉ cần đọc.

Các ví dụ này vẫn là defensive copy nông. Nếu phần tử là object mutable, caller có thể thay đổi trạng thái object thông qua tham chiếu phần tử được trả về. Khi cần đóng gói sâu, hãy dùng phần tử immutable hoặc sao chép từng phần tử ở cả chiều vào và chiều ra.

## 8. Bản sao mutable không đồng nghĩa thread-safe

`ArrayList` mutable không tự đồng bộ hóa các thao tác. Tạo bản sao giúp tách cấu trúc danh sách khỏi nguồn, nhưng không làm cho các object phần tử trở nên thread-safe và cũng không cho phép nhiều thread sửa cùng `ArrayList` một cách an toàn.

Nếu bản sao chỉ thuộc quyền sử dụng của một thread, `ArrayList` thường phù hợp. Nếu chia sẻ cho nhiều thread, cần xác định rõ mô hình truy cập: chỉ đọc sau khi công bố an toàn, đồng bộ hóa khi có ghi, hoặc chọn collection concurrent nếu nghiệp vụ thực sự cần thao tác đồng thời.

## 9. Cách chọn trong thực tế

| Nhu cầu của bên nhận | Cách làm phù hợp | Vì sao |
| --- | --- | --- |
| Chỉ duyệt, tra cứu hoặc hiển thị kết quả | Dùng trực tiếp `stream.toList()` | Không cần cấp phát thêm danh sách. |
| Cần thêm, xóa, thay thế hoặc sắp xếp sau khi nhận kết quả | `new ArrayList<>(result)` | Tạo cấu trúc mutable độc lập. |
| Pipeline ngay từ đầu phải trả `ArrayList` mutable | `collect(Collectors.toCollection(ArrayList::new))` | Thu thập trực tiếp vào loại collection đích. |
| Nhận `List` từ caller nhưng cần sửa nội bộ | Sao chép vào `new ArrayList<>(input)` | Không phụ thuộc mutability của đối số và không sửa cấu trúc list gốc. |
| Cần tách cả trạng thái của object mutable | Tạo bản sao từng phần tử hoặc snapshot immutable | Copy constructor chỉ sao chép tham chiếu phần tử. |

Trước khi tạo bản sao, hãy trả lời ba câu hỏi: bên nhận có thực sự cần thay đổi cấu trúc danh sách không; có thể thu thập trực tiếp vào collection đích không; và có cần tách trạng thái object phần tử hay chỉ cần tách cấu trúc list? Những câu trả lời này xác định đúng cách sao chép và vị trí nên thực hiện.

## Tài liệu tham khảo

- [ArrayList(Collection) – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection))
- [Stream.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Collectors.toCollection() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier))
- [List.copyOf() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
