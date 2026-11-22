# Java 10 — List.copyOf: Thứ tự phần tử theo thứ tự duyệt nguồn

## Mục tiêu bài học

`List.copyOf(Collection<? extends E> source)` được giới thiệu ở **Java 10** để tạo một `List` **không cho sửa đổi** từ một collection đã có. Một đặc điểm quan trọng, thường bị hiểu sai, là **thứ tự của kết quả chính là thứ tự duyệt các phần tử của collection nguồn tại lúc copy**.

Sau bài học, bạn sẽ:
1. Giải thích chính xác khái niệm **thứ tự duyệt nguồn** (*iteration order*) và sự khác biệt với thứ tự thêm, thứ tự sắp xếp hoặc thứ tự mà bạn ngầm mong muốn.
2. Dự đoán kết quả `List.copyOf` từ `List`, `LinkedHashSet`, `TreeSet` và hiểu vì sao không được dự đoán thứ tự cố định từ `HashSet`.
3. Phân biệt danh sách kết quả **cố định về cấu trúc** với **view** nhìn vào collection gốc và với **bất biến sâu** của các đối tượng phần tử.
4. Chọn cách làm rõ thứ tự trước khi gọi `copyOf` khi tính đúng đắn của ứng dụng phụ thuộc vào thứ tự.
5. Viết ví dụ và kiểm thử bảo đảm hợp đồng của collection, tránh những giả định tình cờ đúng trên một JDK hoặc một lần chạy.

Bài tập trung vào API và quy tắc **vẫn áp dụng trên Java 17, Java 21 và các JDK hiện đại**. Ví dụ chính dùng Java 17+; một phần mở rộng Java 21 được ghi rõ mức phiên bản riêng. Không cần API đã lỗi thời hoặc cơ chế legacy.

## 1. Hợp đồng chính thức của `List.copyOf`

Chữ ký:

```java
static <E> List<E> copyOf(Collection<? extends E> coll)
```

Đây là **chữ ký API để tham khảo**, không phải một khai báo phương thức tự viết trong class của bạn.

Ý nghĩa thiết yếu:

- Đầu vào là một `Collection`, không nhất thiết phải là `List`.
- Đầu ra là một `List` không cho thêm, xóa hoặc thay thế phần tử thông qua các thao tác sửa cấu trúc/nội dung danh sách.
- Đầu ra chứa các phần tử được lấy từ collection nguồn **theo đúng thứ tự mà collection đó được duyệt**.
- Nếu sau khi copy, collection nguồn thay đổi về cấu trúc (thêm/xóa/sắp lại phần tử), danh sách kết quả không phản ánh những thay đổi đó.
- Collection nguồn và các phần tử của nó không được là `null`; nếu có, `copyOf` ném `NullPointerException`.
- Nếu đầu vào đã là một danh sách không cho sửa đổi thích hợp, implementation có thể tái sử dụng instance. **Không được dựa vào `==` để kiểm chứng việc copy.**

Điểm về thứ tự được quy định trực tiếp trong tài liệu `List.copyOf` của Oracle: kết quả giữ thứ tự duyệt của collection được truyền vào. Đây là **hợp đồng API**, không chỉ là hành vi tình cờ của `ArrayList`.

### 1.1. Hình dung theo chuỗi phần tử

Giả sử iterator của collection nguồn lần lượt trả:

```text
"C"  ->  "A"  ->  "B"  ->  "A"
```

Thì:

```text
List.copyOf(source) = ["C", "A", "B", "A"]
                       0    1    2    3
```

Công thức khái niệm: nếu quá trình duyệt nguồn hợp lệ trả `e0, e1, …, en-1` thì danh sách kết quả có phần tử ở vị trí `i` tương ứng `ei`. Không có bước sắp xếp hoặc loại trùng ngầm nào do `List.copyOf` thực hiện.

**Phải tránh diễn giải sai:** “Giữ thứ tự” **không có nghĩa** “luôn theo thứ tự đã thêm vào collection”, “luôn tăng dần” hoặc “luôn giống nhau ở mọi lần chạy”. Chỉ khi chính **collection nguồn có hợp đồng duyệt theo thứ tự đó**, danh sách được copy mới có bảo đảm tương ứng.

### 1.2. “Iteration order” và “encounter order”

`Iteration order` là thứ tự collection đưa các phần tử ra khi duyệt. Trong xử lý stream, thuật ngữ `encounter order` cũng thường được dùng để diễn đạt thứ tự phần tử được nguồn stream cung cấp khi có thứ tự được xác định. Với `List.copyOf`, hãy bám vào **hợp đồng iterator/duyệt của `Collection`**, không giả định rằng mọi nguồn đều có thứ tự có ý nghĩa.

Một `List` có các vị trí từ 0 đến `size() - 1`, nên việc duyệt theo thứ tự của list là rõ ràng. Một `Set` lại có thể:
- Giữ thứ tự thêm (`LinkedHashSet`);
- Giữ thứ tự theo comparator (`TreeSet`);
- Không cam kết thứ tự (`HashSet`, `Set.of`).

`List.copyOf` có thể tạo một `List` từ **bất kỳ** nguồn nào ở trên, nhưng tính xác định của thứ tự kết quả phụ thuộc vào nguồn.

## 2. Bảng so sánh những nguồn thường gặp

| Nguồn truyền cho `List.copyOf` | Hợp đồng thứ tự duyệt nguồn | Thứ tự danh sách kết quả |
|---|---|---|
| `ArrayList`, `LinkedList` hoặc `List.of` | Theo chỉ số trong list | **Đúng thứ tự phần tử của list** |
| `LinkedHashSet` dùng theo thứ tự thêm thông thường | Theo thứ tự thêm phần tử lần đầu; thêm lại phần tử sẵn có không đổi thứ tự trong trường hợp thông thường | **Đúng thứ tự duyệt của `LinkedHashSet`** |
| `TreeSet` | Theo thứ tự tự nhiên hoặc `Comparator` được cấu hình | **Đúng thứ tự sorted set đang duyệt** |
| `HashSet` | **Không bảo đảm thứ tự**, kể cả tính ổn định qua thời gian | Giữ thứ tự iterator cung cấp trong lần copy, **nhưng không có thứ tự cố định được bảo đảm từ đầu** |
| `Set.of(...)` | Thứ tự duyệt không được cam kết | Không nên assert một thứ tự chỉ dựa vào cách viết đối số `Set.of` |
| `LinkedHashMap.values()` hoặc `entrySet()` | Theo thứ tự duyệt của map (thông thường là thứ tự chèn key với `LinkedHashMap` mặc định) | Đúng thứ tự collection view mà map cung cấp |
| `HashMap.values()` | Không bảo đảm thứ tự có ý nghĩa | Không nên suy ra thứ tự chèn key hoặc thứ tự alphabet |
| `TreeMap.values()` | Theo thứ tự key được quản lý bởi map | Danh sách các value theo thứ tự key; **không** tự sắp theo value |

**Lưu ý với `LinkedHashMap`:** có thể cấu hình chế độ access-order; lúc đó thứ tự duyệt không nhất thiết là thứ tự thêm key. Luôn dựa vào hợp đồng và cấu hình **nguồn thực tế**.

**Lưu ý với `TreeSet`:** comparator có thể cho thứ tự giảm dần hoặc quy tắc riêng; `List.copyOf` không “đổi lại thành tự nhiên”. Nó giữ thứ tự mà chính collection đang trả ra.

## 3. Trường hợp đơn giản nhất: nguồn là `List`

Giả sử nguồn là một `ArrayList`:

```java
var source = new ArrayList<>(List.of("C", "A", "B", "A"));
var copy = List.copyOf(source);
```

Đây là **mảnh code**, cần import `java.util.ArrayList`, `java.util.List` và đặt trong phương thức.

Kết quả `copy`:

```text
[C, A, B, A]
```

Các sự thật quan trọng:

- Phần tử đầu tiên vẫn là `"C"`, mặc dù `"A"` có thể đứng trước khi xếp theo alphabet.
- Hai lần xuất hiện của `"A"` **đều còn** vì `List` cho phép phần tử trùng.
- Dùng `copy.get(0)` nhận `"C"`, `copy.get(1)` nhận `"A"`; `List.copyOf` không tạo một tập hợp.
- Sau khi copy, nếu thêm/xóa hoặc sắp lại phần tử của `source` thì vị trí và số lượng phần tử trong `copy` **không thay đổi** theo.

Vì vậy, một yêu cầu như “giữ nguyên thứ tự đã cho để hiển thị” phù hợp với `List.copyOf` nếu nguồn đã là `List` có thứ tự chính xác. Nhưng nếu yêu cầu là “hiển thị theo tên tăng dần”, cần thực hiện sắp xếp **trước khi tạo kết quả**, chứ `copyOf` không tự làm việc đó.

## 4. Ví dụ đầy đủ Java 17+: bốn kiểu nguồn và kiểm chứng quy tắc

Lưu thành **`SourceOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.TreeSet;

public class SourceOrderDemo {
    public static void main(String[] args) {
        // List: giữ cả thứ tự lẫn phần tử trùng.
        var source = new ArrayList<>(List.of("C", "A", "B", "A"));
        var snapshot = List.copyOf(source);

        // Nguồn thay đổi sau đó: snapshot không đổi cấu trúc.
        source.clear();
        source.add("D");
        System.out.println("listCopy=" + snapshot);
        System.out.println("sourceAfter=" + source);

        // LinkedHashSet: giữ thứ tự chèn lần đầu, không có phần tử trùng.
        var insertionOrder = new LinkedHashSet<>(List.of("C", "A", "B"));
        System.out.println("linkedSetCopy=" + List.copyOf(insertionOrder));

        // TreeSet: duyệt theo thứ tự tự nhiên của String.
        var sorted = new TreeSet<>(List.of("C", "A", "B"));
        System.out.println("treeSetCopy=" + List.copyOf(sorted));

        // HashSet: không kiểm thử thứ tự cụ thể vì API không hứa hẹn.
        var unordered = new HashSet<>(List.of("C", "A", "B"));
        var arbitraryOrder = List.copyOf(unordered);
        System.out.println("hashSetSize=" + arbitraryOrder.size());
        System.out.println("hashSetMembers="
                + arbitraryOrder.containsAll(List.of("A", "B", "C")));

        // Danh sách kết quả không cho sửa đổi.
        try {
            snapshot.add("E");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable=true");
        }

        // Phần tử null trong nguồn bị từ chối.
        var withNull = new ArrayList<String>();
        withNull.add(null);
        try {
            List.copyOf(withNull);
        } catch (NullPointerException ex) {
            System.out.println("nullRejected=true");
        }
    }
}
```

Biên dịch, chạy bằng JDK 17+:

```bash
javac --release 17 SourceOrderDemo.java
java SourceOrderDemo
```

**Stdout chính xác** của chương trình, không dựa vào thứ tự ngẫu nhiên của `HashSet`:

```text
listCopy=[C, A, B, A]
sourceAfter=[D]
linkedSetCopy=[C, A, B]
treeSetCopy=[A, B, C]
hashSetSize=3
hashSetMembers=true
unmodifiable=true
nullRejected=true
```

Đọc kết quả:

1. `source` bắt đầu là `[C, A, B, A]`. `snapshot` giữ đúng cả thứ tự và phần tử trùng; dù nguồn đổi thành `[D]`, danh sách snapshot vẫn là `[C, A, B, A]`.
2. `LinkedHashSet` duyệt theo thứ tự chèn, nên danh sách kết quả là `[C, A, B]`.
3. `TreeSet` với `String` và comparator tự nhiên duyệt `A`, `B`, `C`, nên kết quả là `[A, B, C]`.
4. `HashSet` không có cam kết thứ tự; ví dụ chỉ kiểm tra **kích thước và tập phần tử**, không so sánh với một thứ tự cố định.
5. `snapshot.add(...)` bị từ chối với `UnsupportedOperationException`.
6. `List.copyOf` từ chối nguồn có phần tử `null` với `NullPointerException`.

Nếu chỉ chạy `System.out.println(List.copyOf(new HashSet<>(...)))` trên máy của bạn, có thể sẽ thấy một thứ tự trông ổn định; đừng viết kiểm thử hoặc thuật toán dựa trên kết quả quan sát ngẫu nhiên đó.

## 5. Vì sao `List.copyOf(HashSet)` không có thứ tự đáng tin cậy?

Nhận định “`List.copyOf` giữ nguyên thứ tự duyệt nguồn” **vẫn đúng** ngay cả với `HashSet`. Nhưng hợp đồng của `HashSet` không xác định thứ tự duyệt, nên không tồn tại một dãy phần tử chuẩn để người gọi dự đoán.

Xét:

```java
var set = new HashSet<>(List.of("C", "A", "B"));
var result = List.copyOf(set);
```

Đây là mảnh mã cần import `HashSet` và `List`.

Bạn có thể tin rằng `result` là một list chứa đúng ba phần tử `A`, `B`, `C` (và không cho sửa), nhưng **không nên khẳng định** kết quả nhất định là `[C, A, B]` hoặc `[A, B, C]`.

Nguyên nhân:
- `HashSet` dựa trên hash table; thứ tự iterator không nằm trong hợp đồng công khai.
- Thứ tự có thể bị ảnh hưởng bởi trạng thái nội bộ, mã hash, thay đổi kích thước bảng, cách xây dựng tập hợp hoặc implementation/JDK.
- Một list được copy sẽ có các vị trí ổn định sau khi tạo; điều đó **không biến thứ tự của HashSet thành một thứ tự được Java bảo đảm trong mọi lần chạy**.

**Quy tắc review:** nếu tính đúng đắn dựa vào thứ tự, nguồn `HashSet` là một dấu hiệu phải làm rõ thứ tự trước khi copy. Không được giải quyết bằng cách thêm `List.copyOf` và hy vọng “chuyển sang List thì tự có thứ tự chèn”.

### 5.1. Cẩn thận với `Set.copyOf` và `Set.of`

`List.copyOf`, `Set.copyOf` và `List.of` là những API khác nhau:

- `List.of(a, b, c)` có từ **Java 9** và tạo danh sách có thứ tự đúng theo các phần tử cung cấp.
- `List.copyOf(collection)` có từ **Java 10** và giữ đúng thứ tự duyệt của collection nguồn; cho phép các phần tử bằng nhau xuất hiện nhiều lần.
- `Set.copyOf(collection)` có từ **Java 10** tạo set không cho sửa; **không hứa giữ thứ tự** của list nguồn và không giữ các phần tử trùng theo nghĩa list.
- `Set.of(a, b, c)` có từ **Java 9**; không nên coi thứ tự liệt kê đối số là thứ tự iterator có cam kết.

Đặc biệt:

```java
var first = List.of("C", "A", "B");
var copiedList = List.copyOf(first);             // [C, A, B]
var copiedSet = Set.copyOf(first);
var backToList = List.copyOf(copiedSet);         // Thứ tự không bảo đảm
```

Đây là mảnh minh họa cần `import java.util.List;` và `import java.util.Set;`.

Việc chuyển dữ liệu qua một `Set` không cam kết thứ tự có thể **làm mất thông tin thứ tự ban đầu**. `List.copyOf` ở bước sau không thể tái tạo một thứ tự mà nguồn đã không còn cam kết.

## 6. Muốn có thứ tự xác định, hãy quy định thứ tự ở nguồn

`List.copyOf` không phải một phương thức sắp xếp. Khi đầu ra phải theo một quy tắc cụ thể, hãy **sắp xếp hoặc xây dựng collection có thứ tự trước khi copy**.

### 6.1. Muốn giữ thứ tự chèn và loại bỏ phần tử trùng

```java
var source = List.of("C", "A", "B", "A");
var uniqueByFirstAppearance = new LinkedHashSet<>(source);
var result = List.copyOf(uniqueByFirstAppearance);
// result: [C, A, B]
```

Đây là mảnh code cần import `List` và `LinkedHashSet`. `LinkedHashSet` xử lý **loại trùng + giữ lần xuất hiện đầu tiên**. `List.copyOf` giữ đúng thứ tự duyệt kết quả mà `LinkedHashSet` cung cấp. Hai bước có vai trò riêng.

### 6.2. Muốn thứ tự alphabet nhưng vẫn giữ phần tử trùng

```java
var source = List.of("C", "A", "B", "A");
var sorted = new ArrayList<>(source);
sorted.sort(String::compareTo);
var result = List.copyOf(sorted);
// result: [A, A, B, C]
```

Đây là mảnh code cần import `List`, `ArrayList`. `sort` làm rõ yêu cầu thứ tự; `List.copyOf` đóng băng cấu trúc danh sách sau khi sắp xếp. Hai phần tử `A` vẫn còn, khác với việc chuyển qua `TreeSet`.

Nếu cần quy tắc khác (giảm dần, không phân biệt chữ hoa/thường, theo nhiều field nghiệp vụ), truyền `Comparator` phù hợp thay vì mặc định dựa vào cách so sánh `String`.

### 6.3. Muốn thứ tự tăng dần và loại trùng

```java
var source = List.of("C", "A", "B", "A");
var sortedUnique = new TreeSet<>(source);
var result = List.copyOf(sortedUnique);
// result: [A, B, C]
```

Đây là mảnh code cần import `List`, `TreeSet`. `TreeSet` quyết định thứ tự và tính duy nhất theo so sánh; `List.copyOf` chỉ chuyển thứ tự duyệt đã có thành một danh sách không cho sửa.

**Lưu ý:** comparator của `TreeSet` quyết định khi nào hai phần tử bị coi là cùng vị trí trong tập. Không dùng `TreeSet` để “chỉ sắp xếp” nếu bạn cần giữ mọi bản ghi trùng.

### 6.4. Nếu thứ tự không quan trọng, đừng tạo kỳ vọng không cần thiết

Khi mục tiêu chỉ là trả về một tập các nhãn độc nhất, một `Set` có thể là kiểu API biểu đạt đúng ý định hơn `List`. Chuyển `HashSet` sang `List` chỉ để chọn kiểu trả về thuận tiện có thể khiến code downstream vô tình dựa vào vị trí `get(0)` mà thực tế không có ý nghĩa.

Quyết định dựa vào **hợp đồng dữ liệu**: thứ tự có ý nghĩa hay không, có cho phép trùng không, có cần truy cập theo index không.

## 7. Snapshot về cấu trúc khác với view không cho sửa

Đây là khác biệt quan trọng khi nói `List.copyOf` “giữ thứ tự”.

- `List.copyOf(source)` cho danh sách không cho sửa và **không thay đổi theo sửa đổi sau đó của collection nguồn**.
- `Collections.unmodifiableList(source)` tạo một **view không cho sửa thông qua view**, nhưng khi `source` tự thay đổi, view có thể **phản ánh** thay đổi ấy.

Cả hai API vẫn có ích trong Java hiện đại, nhưng hợp đồng khác nhau. `Collections.unmodifiableList` không tự cung cấp snapshot độc lập khỏi nguồn.

Ví dụ chạy độc lập, lưu file **`SnapshotVsViewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SnapshotVsViewDemo {
    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("B", "A"));
        var view = Collections.unmodifiableList(source);
        var copy = List.copyOf(source);

        source.add("C");

        System.out.println("view=" + view);
        System.out.println("copy=" + copy);
    }
}
```

```bash
javac --release 17 SnapshotVsViewDemo.java
java SnapshotVsViewDemo
```

```text
view=[B, A, C]
copy=[B, A]
```

Với view, thao tác thêm `C` vào nguồn làm `view` cũng thấy `C`. Với `copyOf`, danh sách kết quả giữ đúng cấu trúc `[B, A]` đã thu được. Nếu sau khi copy, nguồn bị sắp xếp hoặc xóa phần tử, các vị trí trên `copy` vẫn không biến đổi tương ứng.

**Đừng viết kiểm thử `copy != source` để kiểm chứng snapshot.** Nếu nguồn đã là list không cho sửa phù hợp, `copyOf` có thể tái sử dụng instance; hợp đồng quan trọng là nội dung, thứ tự và khả năng không cho sửa theo quy tắc API, không phải danh tính object.

## 8. “Không cho sửa” không đồng nghĩa bất biến sâu

`List.copyOf` không sao chép sâu các object phần tử. Nó giữ **tham chiếu đến phần tử**. Nếu một phần tử có thể thay đổi nội tại, sự thay đổi ấy vẫn quan sát được qua list kết quả.

Ví dụ chạy được, lưu file **`MutableElementDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class MutableElementDemo {

    static final class Label {
        String value;

        Label(String value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return value;
        }
    }

    public static void main(String[] args) {
        var item = new Label("old");
        var source = new ArrayList<>(List.of(item));
        var copy = List.copyOf(source);

        item.value = "new";
        source.add(new Label("another"));

        System.out.println("copy=" + copy);
        System.out.println("source=" + source);
        System.out.println("sameElement=" + (copy.get(0) == item));
    }
}
```

```bash
javac --release 17 MutableElementDemo.java
java MutableElementDemo
```

```text
copy=[new]
source=[new, another]
sameElement=true
```

Cấu trúc của `copy` vẫn có **một phần tử ở index 0**; object tại index đó là cùng instance `item` và thuộc tính của nó đã đổi từ `"old"` sang `"new"`. Trong khi đó `source` đã nhận thêm phần tử thứ hai. Điều này không vi phạm hợp đồng của `List.copyOf`.

Khi dữ liệu cần một snapshot **bất biến hoàn toàn**, hãy dùng value object không thể thay đổi hoặc tạo bản sao phù hợp cho từng phần tử trước khi đưa vào `copyOf`. Việc sao chép phần tử phụ thuộc mô hình dữ liệu; `List.copyOf` không thực hiện thay bạn.

## 9. Lưu ý khi dùng `List.copyOf` với Stream hoặc Map

### 9.1. Kết quả từ Stream

Giả sử một stream duyệt những phần tử đã có thứ tự. Trên Java 17+, có thể viết:

```java
var source = List.of("C", "A", "B");
var ordered = source.stream()
        .sorted()
        .toList();
var snapshot = List.copyOf(ordered);
// [A, B, C]
```

`Stream.toList()` có từ **Java 16**, còn `List.copyOf` có từ Java 10. Ở đây `sorted()` mới tạo thứ tự tăng dần; `copyOf` chỉ giữ thứ tự đó. `toList()` đã trả list không cho sửa, nên `copyOf` có thể không cần thiết nếu không có yêu cầu riêng khi chuẩn hóa dữ liệu.

Nếu bắt đầu từ một nguồn stream **không có encounter order**, không nên suy luận rằng chỉ vì gọi `toList()` mà kết quả sẽ tự đúng theo thứ tự chèn. Hãy dùng bước sắp xếp có nghĩa nếu thuật toán cần thứ tự xác định.

### 9.2. Kết quả từ `Map.values()`

`Map.values()` là collection view; thứ tự duyệt của view phụ thuộc map:

```java
var map = new LinkedHashMap<String, Integer>();
map.put("C", 30);
map.put("A", 10);
map.put("B", 20);
var values = List.copyOf(map.values());
// values: [30, 10, 20] vì LinkedHashMap mặc định duyệt theo thứ tự key được chèn.
```

Đây là mảnh code cần `import java.util.LinkedHashMap;` và `java.util.List;`.

Nếu đổi `LinkedHashMap` thành `HashMap`, **không** được khẳng định `values` vẫn là `[30, 10, 20]`. Nếu dùng `TreeMap`, các value được duyệt theo thứ tự key đã sắp xếp, không phải tự sắp theo giá trị 10, 20, 30 nếu key không phản ánh điều đó.

Ngoài ra, `map.values()` có thể có giá trị trùng và `List.copyOf` vẫn giữ trùng; nhưng map có thể cho giá trị `null`, trong trường hợp đó `List.copyOf` sẽ ném `NullPointerException`. Xác minh dữ liệu nguồn trước khi copy.

## 10. Java 21+: duyệt theo hướng ngược với `SequencedCollection`

Java 21 bổ sung các interface hỗ trợ collection có thứ tự tuần tự (`SequencedCollection`, `SequencedSet`) và một số phép thao tác thứ tự, trong đó có `reversed()`. Điều này giúp tạo một **view duyệt ngược** ở những kiểu collection hỗ trợ.

Ví dụ sau **yêu cầu Java 21+**; nó không phải tính năng gốc Java 10 ngoài lời gọi `List.copyOf`:

Tệp: **`ReverseOrder21.java`**

```java
import java.util.LinkedHashSet;
import java.util.List;

public class ReverseOrder21 {
    public static void main(String[] args) {
        var ordered = new LinkedHashSet<>(List.of("A", "B", "C"));
        var reversedCopy = List.copyOf(ordered.reversed());

        System.out.println("reversed=" + reversedCopy);
    }
}
```

```bash
javac --release 21 ReverseOrder21.java
java ReverseOrder21
```

```text
reversed=[C, B, A]
```

Tại thời điểm copy, `ordered.reversed()` cung cấp một view có thứ tự duyệt `C, B, A`. `List.copyOf` giữ đúng thứ tự duyệt này. Nếu sau đó thay đổi `ordered`, cấu trúc `reversedCopy` vẫn giữ nguyên. Lưu ý: một dự án đang target Java 17 có thể dùng cách xây dựng/sắp xếp riêng thích hợp thay vì phụ thuộc vào `reversed()` của Java 21.

## 11. Những giới hạn ảnh hưởng đến thứ tự và tính đúng đắn

### 11.1. Không copy khi nguồn đang bị thay đổi đồng thời một cách thiếu phối hợp

`List.copyOf` không phải một thao tác transactional bảo đảm quan sát **một thời điểm nguyên tử** với mọi loại collection. Nếu thread khác đồng thời thêm/xóa/sắp xếp nguồn mà không có cơ chế phối hợp thích hợp:
- Iterator của một số collection có thể phát hiện thay đổi và ném `ConcurrentModificationException` theo cơ chế fail-fast;
- Các iterator khác có thể có quy tắc weak consistency;
- Không nên tin rằng danh sách kết quả nhất thiết biểu diễn một trạng thái nhất quán theo thời điểm bạn mong muốn.

**Quy ước:** nếu cần snapshot nhất quán khi có nhiều thread, bảo đảm nguồn ổn định trong khoảng copy bằng cơ chế đồng bộ hoặc dùng thiết kế dữ liệu/concurrent collection đáp ứng đúng yêu cầu. Không dựa vào việc “không thấy exception” để kết luận đã an toàn.

### 11.2. `null` và phần tử trùng

- `List.copyOf(null)` và `List.copyOf` từ collection có phần tử `null` đều không được chấp nhận theo hợp đồng (ném `NullPointerException`).
- Nguồn `List` có thể có phần tử trùng; `List.copyOf` **không khử trùng**.
- Nguồn `Set` theo hợp đồng là tập các phần tử khác nhau; nếu từ `List` chuyển sang `Set` trước khi copy, những phần tử trùng có thể bị loại **ở bước tạo Set**, không phải do `List.copyOf`.
- `List.copyOf` không tự loại bỏ phần tử theo comparator hoặc sắp xếp theo hash code.

### 11.3. Không phụ thuộc vào concrete implementation hoặc identity

Kiểu kết quả mà API cam kết là `List<E>` không cho sửa. Một JDK cụ thể có thể sử dụng các lớp nội bộ tối ưu về bộ nhớ hoặc trả lại cùng instance của một list không cho sửa. Không nên:
- Kiểm thử tên lớp cụ thể của kết quả;
- So sánh danh tính bằng `==` để xác định việc copy;
- Giả định list kết quả luôn được cấp phát mới;
- Thực hiện ép kiểu sang `ArrayList` hoặc phụ thuộc vào mutable implementation.

### 11.4. Cẩn thận khi phần tử có trạng thái ảnh hưởng đến `equals`/`hashCode`

Bản thân vị trí của tham chiếu trong `List.copyOf` không đổi, nhưng nếu object phần tử có trường ảnh hưởng đến `equals` hoặc biểu diễn `toString`, dữ liệu hiển thị hoặc kết quả so sánh có thể khác sau khi phần tử bị sửa. Vì vậy, “thứ tự được giữ” là thứ tự các tham chiếu/phần tử đã duyệt, **không** là cam kết rằng nội dung bên trong phần tử không thể thay đổi.

## 12. Hướng dẫn kiểm thử thứ tự đúng theo hợp đồng

Khi viết unit test, tách **thứ tự được bảo đảm** khỏi **thứ tự không được bảo đảm**.

### Test 1 — Nguồn list có thứ tự rõ ràng

```java
var source = List.of("C", "A", "B", "A");
var result = List.copyOf(source);

if (!result.equals(List.of("C", "A", "B", "A"))) {
    throw new AssertionError("Wrong order");
}
```

Đây là **mảnh code** cần import `java.util.List` và đặt trong phương thức. Dùng `List.equals` để kiểm tra **cả số lượng, thứ tự và giá trị**.

### Test 2 — Nguồn `LinkedHashSet` có thứ tự chèn

```java
var source = new LinkedHashSet<>(List.of("C", "A", "B"));
var result = List.copyOf(source);

if (!result.equals(List.of("C", "A", "B"))) {
    throw new AssertionError("Insertion order was lost");
}
```

Cần import `List` và `LinkedHashSet`; thứ tự được bảo đảm bởi collection nguồn nên assert này hợp lệ.

### Test 3 — Nguồn `TreeSet` có comparator xác định

```java
var source = new TreeSet<>(List.of("C", "A", "B"));
var result = List.copyOf(source);

if (!result.equals(List.of("A", "B", "C"))) {
    throw new AssertionError("Sorted order was lost");
}
```

Cần import `List` và `TreeSet`; thứ tự duyệt của `TreeSet` đã được bảo đảm.

### Test 4 — Nguồn `HashSet` không hứa thứ tự

**Không nên viết:**

```java
var source = new HashSet<>(List.of("C", "A", "B"));
var result = List.copyOf(source);
// Không assert result.equals(List.of("A", "B", "C")).
```

Thay vào đó, nếu thứ tự thực sự không quan trọng, kiểm tra phần tử và số lượng:

```java
if (result.size() != 3 || !result.containsAll(List.of("A", "B", "C"))) {
    throw new AssertionError("Unexpected members");
}
```

Các đoạn này là mảnh code trong phương thức, cần import `HashSet` và `List`.

Nếu yêu cầu nghiệp vụ cần một thứ tự cố định, hãy **thay thiết kế** để chọn thứ tự từ đầu (`LinkedHashSet`, `TreeSet` hoặc sắp xếp list) rồi kiểm thử đúng thứ tự ấy.

### Test 5 — Snapshot không đổi khi nguồn đổi

```java
var source = new ArrayList<>(List.of("B", "A"));
var result = List.copyOf(source);
source.add("C");

if (!result.equals(List.of("B", "A"))) {
    throw new AssertionError("Copy must not track source modifications");
}
```

Cần import `ArrayList` và `List`. Kiểm thử **nội dung** phù hợp hơn kiểm thử object identity.

## 13. Các hiểu nhầm thường gặp

| Nhận định dễ sai | Cách hiểu đúng |
|---|---|
| “`List.copyOf` luôn sắp xếp đầu ra theo alphabet.” | Không, nó giữ thứ tự duyệt nguồn. |
| “`List.copyOf` luôn giữ thứ tự thêm vào collection.” | Chỉ khi iterator của nguồn có hợp đồng theo thứ tự thêm. |
| “Dùng `HashSet` xong copy sang List sẽ lấy lại thứ tự chèn.” | Không, `HashSet` không bảo đảm thứ tự duyệt. |
| “Nguồn `TreeSet` rồi copy sẽ giữ lại thứ tự ban đầu khi thêm.” | Không; `TreeSet` duyệt theo comparator/tự nhiên. |
| “`List.copyOf` loại phần tử trùng.” | Không; list có thể chứa phần tử trùng. Nếu chuyển qua set trước đó, set mới là bước loại trùng. |
| “Danh sách copy sẽ thay đổi khi thêm vào nguồn.” | Không: cấu trúc kết quả không theo thay đổi nguồn sau copy. |
| “Danh sách không cho sửa nghĩa là phần tử cũng bất biến.” | Không: object phần tử có thể còn mutable. |
| “`Collections.unmodifiableList(source)` và `List.copyOf(source)` là cùng một dạng snapshot.” | Không: cái thứ nhất là view, còn `copyOf` không phản ánh sửa đổi cấu trúc nguồn sau đó. |
| “Nếu chạy `List.copyOf(hashSet)` nhiều lần ra cùng kết quả, Java bảo đảm thứ tự ấy.” | Không: đó chỉ là quan sát trong các điều kiện cụ thể. |
| “Kết quả `copyOf` luôn là object mới.” | Không: có thể tái sử dụng một list không cho sửa phù hợp. |
| “`List.copyOf` có thể tự sửa vấn đề thread safety khi nguồn thay đổi đồng thời.” | Không: cần phối hợp truy cập nguồn phù hợp với yêu cầu nhất quán. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Kết quả của `List.copyOf(List.of("C", "A", "B"))` theo thứ tự nào?

**Đáp án:** `[C, A, B]`. `List` duyệt theo thứ tự vị trí từ đầu đến cuối.

**Câu 2.** `var set = new LinkedHashSet<>(List.of("C", "A", "B"));` rồi `List.copyOf(set)` cho thứ tự nào?

**Đáp án:** `[C, A, B]`; `LinkedHashSet` thông thường duyệt theo thứ tự thêm phần tử lần đầu.

**Câu 3.** Vì sao `List.copyOf(new TreeSet<>(List.of("C", "A", "B")))` cho `[A, B, C]`?

**Đáp án:** `TreeSet` sắp và duyệt theo thứ tự tự nhiên của chuỗi; `copyOf` giữ thứ tự đó.

**Câu 4.** Nếu nguồn là `HashSet` chứa `A`, `B`, `C`, có thể khẳng định phần tử đầu tiên là `A` không?

**Đáp án:** Không. `HashSet` không cam kết iteration order; không nên phụ thuộc vào index 0.

**Câu 5.** Nguồn list `[A, B, A]` sau `List.copyOf` có còn hai phần tử `A` không?

**Đáp án:** Có. `List.copyOf` không khử trùng.

**Câu 6.** Nguồn mutable list có thứ tự `[B, A]` được copy, rồi nguồn thêm `C`. Kết quả copy có trở thành `[B, A, C]` không?

**Đáp án:** Không, kết quả vẫn là `[B, A]` về cấu trúc và vị trí.

**Câu 7.** Một object phần tử thay đổi thuộc tính sau khi copy. List kết quả có thể hiện giá trị thuộc tính mới không?

**Đáp án:** Có. List copy chứa tham chiếu tới object, không deep-copy nội dung phần tử.

**Câu 8.** Muốn một danh sách tăng dần nhưng vẫn giữ phần tử trùng, nên dùng `TreeSet` rồi `List.copyOf` không?

**Đáp án:** Không nếu phải giữ trùng. Sắp xếp một list trước, rồi `List.copyOf`; `TreeSet` là một set và có thể loại phần tử trùng.

**Câu 9.** Tại sao không nên assert `List.copyOf(aSet) == aSet` hoặc `!=` để kiểm tra copy?

**Đáp án:** Cách dùng identity không diễn đạt hợp đồng API, và `copyOf` có thể tái sử dụng instance list không cho sửa thích hợp. Kiểm tra nội dung, thứ tự và tính không cho sửa theo trường hợp.

**Câu 10.** Với dữ liệu vừa được thêm/xóa từ thread khác trong lúc copy, kết quả có phải snapshot nguyên tử tuyệt đối không?

**Đáp án:** Không có bảo đảm chung như thế cho mọi `Collection`. Cần thiết kế đồng bộ hoặc chọn nguồn có hợp đồng nhất quán thích hợp.

## 15. Tài liệu chính thức để đối chiếu

- [Oracle Java SE 21 — `List.copyOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): đặc tả **thứ tự duyệt nguồn**, `null`, không phản ánh thay đổi nguồn và khả năng tái sử dụng instance. `Since: 10`.
- [Oracle Java SE 21 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/21/core/creating-immutable-lists-sets-and-maps.html): cách dùng `copyOf` và sự khác nhau giữa collection nguồn với kết quả không cho sửa.
- [Oracle Java SE 21 — `LinkedHashSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html): iteration order theo insertion order trong cấu hình thông thường.
- [Oracle Java SE 21 — `HashSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html): **không bảo đảm thứ tự duyệt**.
- [Oracle Java SE 21 — `TreeSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html): sắp và duyệt theo natural order hoặc comparator.
- [Oracle Java SE 21 — `SequencedCollection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): API `reversed()`, phần mở rộng từ Java 21.
- [OpenJDK JEP 269 — Convenience Factory Methods for Collections](https://openjdk.org/jeps/269): bối cảnh các collection factory được bổ sung ở Java 9; phân biệt `List.of` với `List.copyOf` của Java 10.

**Ghi nhớ:** `List.copyOf` **giữ thứ tự phần tử đúng theo cách collection nguồn được duyệt tại lần copy**, tạo list không cho sửa và không phản ánh các sửa đổi cấu trúc nguồn sau đó. Muốn kết quả theo thứ tự chèn hoặc tăng dần, hãy chọn **nguồn có hợp đồng duyệt tương ứng** hoặc **sắp xếp trước khi copy**. Không dựa vào thứ tự của `HashSet`, không nhầm snapshot cấu trúc với bất biến sâu.