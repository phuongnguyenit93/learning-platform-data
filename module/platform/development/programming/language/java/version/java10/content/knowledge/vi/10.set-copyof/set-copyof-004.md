# Khác biệt xử lý trùng giữa `Set.copyOf` và `Set.of` trong Java

> **Trọng tâm Java 10:** `Set.copyOf(Collection)` được bổ sung ở Java 10, còn `Set.of(...)` đã có từ Java 9. Cả hai API vẫn được sử dụng trên JDK hiện đại được hỗ trợ. Khác biệt quan trọng nhất: **`Set.of` từ chối phần tử trùng bằng ngoại lệ; `Set.copyOf` chấp nhận collection đầu vào có phần tử trùng và chỉ giữ một đại diện của mỗi nhóm phần tử bằng nhau.**

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Dự đoán chính xác khi nào `Set.of(...)` ném `IllegalArgumentException` và vì sao `Set.copyOf(...)` không làm vậy chỉ do đầu vào có phần tử trùng.
2. Hiểu “trùng” trong `Set` theo `equals`/`hashCode`, không đơn thuần là cùng tham chiếu đối tượng hoặc trông giống nhau khi in ra.
3. Giải thích vì sao `Set.copyOf` có thể giữ **bất kỳ** phần tử nào trong nhóm phần tử được coi là bằng nhau, nên không được dùng kết quả để chọn bản ghi “đầu tiên” hay “cuối cùng”.
4. Dùng đúng overload: `Set.of(element1, element2, ...)` để khai báo tập phần tử xác định sẵn, `Set.copyOf(collection)` để chuyển collection đã có thành tập không cho sửa.
5. Xử lý đúng `null`, thứ tự duyệt không được bảo đảm, biến đổi nguồn sau copy và giới hạn “unmodifiable” so với “deep immutable”.
6. Chọn chiến lược **báo lỗi khi có trùng** hoặc **tự loại trùng** theo hợp đồng nghiệp vụ, kiểm thử bằng ví dụ Java hoàn chỉnh.

## 2. Quy tắc cốt lõi trong 30 giây

```java
// Có ba phần tử trong List, nhưng giá trị "A" xuất hiện hai lần.
var source = java.util.List.of("A", "B", "A");

// Java 10: cho phép nguồn có phần tử trùng và chỉ giữ các phần tử phân biệt.
var copied = java.util.Set.copyOf(source);
System.out.println(copied.size());      // 2
System.out.println(copied.contains("A")); // true

// Java 9+: việc chỉ định trùng ngay trong Set.of là lỗi runtime.
var direct = java.util.Set.of("A", "B", "A");
// Nếu thực thi dòng cuối: IllegalArgumentException.
```

Đoạn trên cố ý đặt dòng `Set.of` có thể ném lỗi ở cuối để đối chiếu; không phải chương trình hoàn chỉnh có thể chạy hết mà không bắt exception. Chương trình lab ở phần 7 có xử lý các ngoại lệ và output xác định.

**Không nhầm lẫn:** hai lời gọi đều **biên dịch hợp lệ**. `IllegalArgumentException` từ `Set.of("A", "B", "A")` xảy ra **khi chạy lời gọi tạo Set**, không phải lỗi cú pháp hay lỗi generic ở thời điểm `javac` biên dịch.

### Bảng so sánh

| Tiêu chí | `Set.of(e1, e2, ...)` | `Set.copyOf(collection)` |
| --- | --- | --- |
| Ra đời | **Java 9** | **Java 10** |
| Dạng đầu vào | Các phần tử riêng lẻ (hoặc mảng qua varargs) | Một `Collection<? extends E>` |
| Hai phần tử bằng nhau theo `equals` | **Ném `IllegalArgumentException`** | **Không ném lỗi vì trùng; loại trùng** |
| Một nhóm phần tử bằng nhau, khác identity/trạng thái ngoài `equals` | Không tạo kết quả: từ chối | Giữ **một phần tử bất kỳ** trong nhóm |
| Phần tử `null` | **Ném `NullPointerException`** | **Ném `NullPointerException`** |
| Collection/mảng truyền vào là `null` | Với mảng varargs null có thể ném `NullPointerException` | Ném `NullPointerException` khi `collection == null` |
| Có thể `add`/`remove` trên kết quả? | Không: `UnsupportedOperationException` | Không: `UnsupportedOperationException` |
| Thứ tự duyệt | Không được bảo đảm | Không được bảo đảm |
| Nguồn mutable thay đổi sau khi tạo | Không áp dụng cho danh sách phần tử độc lập; các đối tượng phần tử vẫn có thể mutable | Thay đổi **cấu trúc** collection nguồn không phản ánh vào Set kết quả |
| Khi nào nên dùng | Bộ phần tử khai báo rõ; trùng là sai cấu hình hoặc sai dữ liệu | Chuyển List/Collection sang tập giá trị duy nhất; trùng được chấp nhận |

Lưu ý: `Set.copyOf` chỉ bảo đảm bản chụp **thành viên** của nguồn, không phải deep copy của chính các đối tượng thành viên.

## 3. Vì sao `Set.of` từ chối, còn `Set.copyOf` tự loại trùng?

### 3.1. `Set.of` dành cho việc tạo Set từ danh sách phần tử chỉ định tường minh

```java
var roles = java.util.Set.of("USER", "ADMIN", "EDITOR");
```

Hợp đồng của lời gọi là “tạo một tập không cho sửa chứa đúng các phần tử chỉ định”. Nếu lập trình viên chỉ định cùng một phần tử hai lần, có thể đó là lỗi cấu hình, sai hằng số hoặc sao chép nhầm. `Set.of` chọn chiến lược **fail fast**: báo lỗi ngay bằng `IllegalArgumentException` thay vì âm thầm loại bớt.

```java
java.util.Set.of("USER", "USER"); // Biên dịch được; ném IllegalArgumentException khi chạy.
```

Quy tắc áp dụng với các overload 0–10 tham số và dạng varargs cho số phần tử bất kỳ; không phải chỉ trường hợp 2 hoặc 3 đối số. Với dữ liệu lấy từ mảng, `Set.of(array)` cũng từ chối phần tử trùng trong các phần tử của mảng.

### 3.2. `Set.copyOf` nhận Collection — một nguồn có thể chứa trùng hợp lệ

```java
var requests = java.util.List.of("READ", "WRITE", "READ");
var permissions = java.util.Set.copyOf(requests);
System.out.println(permissions.size()); // 2
```

Một `List` cho phép phần tử trùng. Khi chuyển nó sang `Set`, mục tiêu thường là lấy **các giá trị phân biệt**. Theo hợp đồng của `Set.copyOf`, các phần tử trùng trong nguồn được thu gọn thành một đại diện, không phát sinh ngoại lệ chỉ vì trùng.

Điều này không có nghĩa `Set.copyOf` là công cụ **xác thực dữ liệu không trùng**. Nếu nghiệp vụ cấm nhập hai quyền giống nhau, sử dụng `Set.copyOf` một mình sẽ che mất dấu hiệu lỗi. Cần kiểm tra trùng và báo lỗi **trước khi** tạo snapshot, hoặc dùng một luồng tạo Set có chủ đích từ chối trùng.

### 3.3. Khi nguồn đã là Set

```java
var mutable = new java.util.HashSet<>(java.util.List.of("A", "B", "A"));
var result = java.util.Set.copyOf(mutable);
System.out.println(mutable.size()); // 2
System.out.println(result.size());  // 2
```

`HashSet` đã khử trùng khi xây dựng; `Set.copyOf` không cần xử lý thêm giá trị trùng. Nhưng nó vẫn hữu ích để công bố một collection **không cho sửa**. Đừng dựa vào việc `copyOf` luôn tạo object mới: nếu nguồn đã là Set không cho sửa phù hợp, JVM/JDK có thể tái sử dụng instance. Hợp đồng cần dựa vào là giá trị, tính không cho sửa và snapshot của thành viên, **không phải so sánh `==`**.

## 4. “Trùng” được xác định bởi `equals` và `hashCode`

### 4.1. Hai đối tượng khác nhau vẫn có thể trùng

```java
var a = new String("Java");
var b = new String("Java");

System.out.println(a == b);      // false: hai object khác nhau
System.out.println(a.equals(b));  // true: nội dung String bằng nhau
```

`Set.of(a, b)` ném `IllegalArgumentException` vì hai chuỗi **bằng nhau theo `equals`**, dù `a != b`. `Set.copyOf(List.of(a, b))` trả Set có `size() == 1`. Điều này là tính chất của `Set`, không phải Java chỉ so sánh tham chiếu.

Một `Set` thông thường dùng `equals` để xác định phần tử trùng; các implementation dựa trên hashing cần `hashCode` tuân thủ hợp đồng: **nếu hai đối tượng bằng nhau theo `equals` thì hash code phải bằng nhau**.

### 4.2. Tùy domain object, “bằng nhau” có nghĩa khác nhau

Giả sử class `Ticket` có hai trường `id` và `label`, nhưng `equals/hashCode` chỉ xét `id`:

```java
var first = new Ticket("T1", "first");
var second = new Ticket("T1", "second");

System.out.println(first.equals(second)); // true
```

Hai đối tượng khác nhau về `label` nhưng Set coi chúng trùng vì cùng `id`. Khi:

```java
var unique = java.util.Set.copyOf(java.util.List.of(first, second));
```

`unique` có **một** phần tử; nhưng Javadoc cho phép nó giữ **bất kỳ phần tử nào** trong hai phần tử được coi là bằng nhau. Vì thế, việc in `unique.iterator().next().label` và chốt kỳ vọng chính xác `"first"` hoặc `"second"` là một bài test **không hợp đồng bảo đảm**.

Trong chương trình lab bên dưới, chỉ kiểm tra `size` và `contains(new Ticket("T1", ...))` để giữ output đáng tin trên các JDK.

### 4.3. Muốn chọn rõ bản ghi “đầu tiên” hoặc “cuối cùng” thì sao?

Nếu nghiệp vụ muốn chọn bản ghi đầu tiên theo `id`, đừng phó mặc cho `Set.copyOf`:

```java
var firstById = new java.util.LinkedHashMap<String, Ticket>();
for (var ticket : ticketsInEncounterOrder) {
    firstById.putIfAbsent(ticket.id, ticket);
}
```

Đây là **đoạn minh họa bên trong một phương thức**, giả sử `ticketsInEncounterOrder` là `List<Ticket>` và `Ticket` được định nghĩa trong chương trình lab. `putIfAbsent` bảo toàn giá trị gắn với lần đầu gặp mỗi `id` nếu các giá trị không null; danh sách đầu vào có thứ tự rõ ràng.

Nếu muốn ưu tiên bản ghi cuối, quy tắc có thể là `lastById.put(ticket.id, ticket)` khi duyệt theo thứ tự, nhưng phải xác nhận đó là chính sách nghiệp vụ. Có thể công bố `Map.copyOf(firstById)` khi dữ liệu đã ổn định (giá trị phần tử mutable vẫn cần cân nhắc). **Không dùng `Set.copyOf` để quyết định precedence.**

### 4.4. Phân biệt `equals` với thứ tự sắp xếp

Ví dụ `new BigDecimal("1.0")` và `new BigDecimal("1.00")` có thể so sánh số học bằng `compareTo` nhưng **không bằng nhau theo `equals`**, vì scale khác nhau. Một `Set.of` có thể chứa cả hai theo hợp đồng equality của `BigDecimal`.

Điểm này quan trọng khi khử trùng dữ liệu tài chính: cần định nghĩa rõ “trùng” là cùng đối tượng miền, cùng mã, hay cùng giá trị đã chuẩn hóa. Nếu cần so sánh theo quy tắc miền khác `equals`, hãy chuẩn hóa dữ liệu hoặc dùng một cấu trúc/khóa định danh phù hợp **trước** khi tạo Set.

## 5. Đừng dùng `Set.of(collection)` để chuyển collection sang Set

Lỗi rất dễ gặp:

```java
var list = java.util.List.of("A", "B", "A");
var wrong = java.util.Set.of(list);      // Set<List<String>> có MỘT phần tử là list.
var right = java.util.Set.copyOf(list);  // Set<String> có HAI phần tử A, B.

System.out.println(wrong.size()); // 1
System.out.println(right.size()); // 2
```

`Set.of` nhận **các phần tử**, không có overload nhận `Collection` rồi tự phân rã thành các phần tử của collection đó. Khi truyền một `List` như **một đối số**, phần tử của Set chính là **List** ấy. `Set.copyOf(list)` mới là cách chuyển các phần tử trong List sang Set không cho sửa.

Nếu bạn có **mảng** phần tử, `Set.of(array)` dùng overload varargs (mảng là các phần tử cần thêm) và **vẫn từ chối trùng**:

```java
String[] array = {"A", "B", "A"};
java.util.Set.of(array); // Ném IllegalArgumentException.
```

Đây là khác biệt đáng nhớ giữa `Set.of(aCollection)` với `Set.of(anArray)`. Với mảng primitive, phải chú ý generic/varargs sẽ không tự boxing từng phần tử như một `String[]`; dùng kiểu phần tử tham chiếu phù hợp hoặc chuyển đổi có chủ đích.

## 6. Những quy tắc chung vẫn phải tuân thủ

### 6.1. `null` bị từ chối ở cả hai API

```java
var nullable = new java.util.ArrayList<String>();
nullable.add(null);

java.util.Set.copyOf(nullable);      // NullPointerException.
java.util.Set.of("A", (String) null); // NullPointerException.
```

`Set.copyOf` không biến `null` thành “một phần tử phân biệt hợp lệ”; nó từ chối. `Set.of` cũng vậy. Khi nguồn có thể thiếu dữ liệu, xác định chính sách: báo lỗi đầu vào, bỏ các phần tử null sau khi được phép, hay dùng một kiểu miền biểu diễn “không có giá trị”. Không che lỗi bằng cách âm thầm loại `null` nếu nghiệp vụ yêu cầu báo lỗi.

Cũng phải phân biệt `Set.copyOf(null)` (collection nguồn là null) với `Set.copyOf(collectionContainingNull)` (có phần tử null); cả hai đều vi phạm hợp đồng và ném `NullPointerException`.

### 6.2. Kết quả của cả hai đều không cho sửa

```java
var copied = java.util.Set.copyOf(java.util.List.of("A", "B"));
copied.add("C");   // Ném UnsupportedOperationException khi chạy.
copied.remove("A"); // Cũng không được phép.
```

Không nhầm “unmodifiable” với việc một tham chiếu `final Set<String>`: `final` chỉ ngăn gán lại tham chiếu, không quyết định collection có hỗ trợ `add/remove`.

Nếu cần Set mutable, dùng `new HashSet<>(source)`, hoặc `new LinkedHashSet<>(source)` khi hợp đồng cần thứ tự chèn. Chúng tự loại trùng theo quy tắc Set nhưng **cho phép thêm/xóa**.

### 6.3. Thứ tự duyệt không được bảo đảm

```java
var letters = java.util.Set.copyOf(java.util.List.of("B", "A", "B"));
System.out.println(letters.size());        // 2
System.out.println(letters.contains("A")); // true
```

Đừng khẳng định `letters.iterator()` luôn trả `"B"` trước `"A"`. `Set.of` và `Set.copyOf` không cam kết thứ tự duyệt; output `Set.toString()` phụ thuộc vào iteration order nên cũng không thích hợp để snapshot-test theo thứ tự.

Khi cần kiểm thử:

- Dùng `size()`, `contains(...)` hoặc `set.equals(expectedSet)`.
- Không chốt kỳ vọng bằng `Set.toString()` hoặc vị trí phần tử.
- Nếu thứ tự hiển thị là một yêu cầu, dùng `List` hoặc cấu trúc có contract thứ tự rõ ràng, sau đó chỉ chuyển thành Set khi ý nghĩa nghiệp vụ thực sự là tính duy nhất.

### 6.4. `Set.copyOf` là snapshot cấu trúc, không phải deep copy

```java
var source = new java.util.ArrayList<>(java.util.List.of("A", "B"));
var snapshot = java.util.Set.copyOf(source);
source.add("C");

System.out.println(snapshot.contains("C")); // false
```

Khi thêm/xóa phần tử trong collection nguồn sau lúc tạo, tập kết quả không phản ánh thay đổi đó. Tuy nhiên, nếu một phần tử có trạng thái mutable, cùng đối tượng đó vẫn được giữ bởi bản chụp; việc thay đổi thuộc tính phần tử có thể quan sát và thậm chí gây hành vi bất nhất nếu `equals/hashCode` phụ thuộc vào thuộc tính bị sửa.

Khuyến nghị: với phần tử được dùng làm khóa/định danh Set, ưu tiên **đối tượng bất biến về những trường tham gia `equals/hashCode`**. Khi cần deep immutable snapshot, thực hiện defensive copying hoặc ánh xạ sang value object bất biến trước khi gọi `Set.copyOf`.

### 6.5. Một lời gọi có thể trả lại cùng instance

Nếu nguồn đã là một Set không cho sửa, `Set.copyOf` có thể tái sử dụng instance thay vì sao chép. Đừng kiểm tra `copy == source` như một yêu cầu nghiệp vụ; các instance từ `Set.of/copyOf` có ngữ nghĩa value-based và không nên dùng danh tính của chúng để làm khóa đồng bộ.

## 7. Lab Java chạy được: đối chiếu đầy đủ cả hai cách tạo

### 7.1. Chuẩn bị

Dùng một bản phân phối JDK hiện đại **đang được hỗ trợ và cập nhật bảo mật** (chẳng hạn JDK 21 hoặc 25 LTS của nhà cung cấp phù hợp). `Set.copyOf` đã có từ Java 10 và vẫn áp dụng ở hiện tại; `Set.of` đã có từ Java 9. Không yêu cầu cài đặt runtime Java 10 cũ.

```bash
java -version
javac -version
```

Lưu nguyên chương trình dưới đây thành **`DuplicateSetLab.java`**. Tên tệp khớp với tên `public class`.

### 7.2. Mã nguồn đầy đủ

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public class DuplicateSetLab {
    static final class Ticket {
        final String id;
        final String label;

        Ticket(String id, String label) {
            this.id = id;
            this.label = label;
        }

        // Theo hợp đồng miền, Ticket trùng khi có cùng id.
        @Override
        public boolean equals(Object obj) {
            return obj instanceof Ticket && id.equals(((Ticket) obj).id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("A", "B", "A"));
        var copied = Set.copyOf(source);

        System.out.println("source size: " + source.size());
        System.out.println("copy size: " + copied.size());
        System.out.println("copy contains A: " + copied.contains("A"));

        try {
            Set.of("A", "B", "A");
        } catch (IllegalArgumentException ex) {
            System.out.println("Set.of duplicate: IllegalArgumentException");
        }

        var literal = Set.of("A", "B");
        System.out.println("same members: " + copied.equals(literal));

        source.add("C");
        System.out.println("snapshot contains C: " + copied.contains("C"));

        try {
            copied.add("D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("copy add: UnsupportedOperationException");
        }

        // Hai instance Ticket khác nhau nhưng equals/hashCode coi là trùng.
        var candidates = List.of(
                new Ticket("T1", "first"),
                new Ticket("T1", "second"));
        var selected = Set.copyOf(candidates);

        System.out.println("equal objects size: " + selected.size());
        System.out.println("equal objects lookup: "
                + selected.contains(new Ticket("T1", "lookup")));

        // Nếu yêu cầu chọn phần tử đầu tiên, tự thiết kế quy tắc đó.
        var firstById = new LinkedHashMap<String, Ticket>();
        for (var candidate : candidates) {
            firstById.putIfAbsent(candidate.id, candidate);
        }
        System.out.println("explicit first label: "
                + firstById.get("T1").label);

        var nullable = new ArrayList<String>();
        nullable.add(null);
        try {
            Set.copyOf(nullable);
        } catch (NullPointerException ex) {
            System.out.println("Set.copyOf null: NullPointerException");
        }

        try {
            Set.of("A", (String) null);
        } catch (NullPointerException ex) {
            System.out.println("Set.of null: NullPointerException");
        }

        var collected = List.of("A", "A", "B").stream()
                .collect(Collectors.toUnmodifiableSet());
        System.out.println("collector size: " + collected.size());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac DuplicateSetLab.java
java DuplicateSetLab
```

### 7.3. Stdout chính xác

```text
source size: 3
copy size: 2
copy contains A: true
Set.of duplicate: IllegalArgumentException
same members: true
snapshot contains C: false
copy add: UnsupportedOperationException
equal objects size: 1
equal objects lookup: true
explicit first label: first
Set.copyOf null: NullPointerException
Set.of null: NullPointerException
collector size: 2
```

Đây là **13 dòng output có thể kiểm chứng** và không phụ thuộc vào thứ tự duyệt Set hoặc việc JDK chọn đối tượng đại diện nào trong một nhóm phần tử bằng nhau. Đoạn lab đã xử lý các ngoại lệ dự kiến bằng `try/catch` để chương trình chạy đến cuối.

### 7.4. Giải thích từng nhóm output

1. **Ba đầu vào → hai giá trị:** `source` chứa `"A","B","A"` nên `size()==3`. `Set.copyOf(source)` loại trùng theo `equals` và có `size()==2`; `contains("A")` là `true`.
2. **`Set.of` fail fast:** cùng ba giá trị truyền trực tiếp đến `Set.of` gây `IllegalArgumentException`. Đây là lỗi **runtime**, không phải lỗi compiler.
3. **Nội dung tập bằng nhau:** `copied.equals(Set.of("A","B"))` là `true` bất kể Set được triển khai hoặc duyệt theo thứ tự nào.
4. **Snapshot của nguồn:** sau `source.add("C")`, `copied.contains("C")` vẫn là `false` vì Set copy không là live view của danh sách nguồn.
5. **Không cho sửa:** `copied.add("D")` ném `UnsupportedOperationException`. Việc đầu vào từng là `ArrayList` mutable không khiến kết quả copy mutable.
6. **Trùng theo đối tượng miền:** hai `Ticket` có cùng `id` nhưng khác `label` có `equals==true`, nên kết quả chỉ còn một; `contains(new Ticket("T1", "lookup"))` đúng nhờ cùng `id`. Không đoán đại diện giữ nhãn `"first"` hay `"second"`.
7. **Thứ tự chọn bản ghi phải tường minh:** vòng lặp `LinkedHashMap.putIfAbsent` với nguồn `List` theo thứ tự làm `firstById.get("T1").label` luôn bằng `"first"` trong tình huống này. Nó **không** lấy từ đại diện mà `Set.copyOf` chọn.
8. **`null`:** cả hai lời gọi riêng đều ném `NullPointerException`. Bắt exception theo kiểu đã dự kiến giúp kiểm tra hợp đồng, không dùng exception message vốn có thể khác giữa các JDK.
9. **Collector Java 10:** `Collectors.toUnmodifiableSet` cũng chấp nhận phần tử trùng trong Stream, giữ tập các phần tử phân biệt, nên `size()==2`. Collector được bổ sung ở Java 10; khác với `toUnmodifiableMap` có quy tắc duplicate **key** riêng.

## 8. Chọn đúng API theo hợp đồng nghiệp vụ

### Trường hợp A — tập hằng số/hằng quyền cấu hình phải không trùng

```java
static final Set<String> SUPPORTED_STATES =
        Set.of("NEW", "READY", "DONE");
```

Đoạn là **khai báo field trong một class**, không phải chương trình đầy đủ. Khi nhập nhầm một phần tử trùng vào literal, `Set.of` sẽ báo lỗi ngay lúc biểu thức được đánh giá. Điều này thích hợp khi **trùng phải là bug**.

Cẩn trọng: nếu field được khởi tạo lúc load class và lỗi không được xử lý, chương trình có thể không khởi tạo được class; đó vẫn là hậu quả tốt để phát hiện cấu hình sai, nhưng cần được kiểm thử.

### Trường hợp B — đầu vào List có trùng nhưng nghiệp vụ muốn quyền duy nhất

```java
// Trong một phương thức, requests là Collection<String> đã được xác thực.
Set<String> unique = Set.copyOf(requests);
```

Dùng `Set.copyOf` nếu việc gộp các giá trị bằng nhau là **mong muốn** (ví dụ tập quyền, mã tính năng, nhãn phân loại). Cần xét null và đảm bảo normalize đúng các giá trị trước khi gộp nếu quy tắc domain yêu cầu phân biệt hoa/thường hoặc khoảng trắng.

### Trường hợp C — đầu vào List có trùng và trùng phải gây lỗi

Nếu nhận một `List<String> requests` mà hợp đồng yêu cầu mọi giá trị khác nhau, hãy xác thực **trước** khi chuyển sang tập:

```java
// Minh họa bên trong một phương thức; requests có kiểu List<String>.
var seen = new java.util.HashSet<String>();
for (var value : requests) {
    java.util.Objects.requireNonNull(value, "permission must not be null");
    if (!seen.add(value)) {
        throw new IllegalArgumentException("Duplicate permission: " + value);
    }
}
var unique = Set.copyOf(seen);
```

Cách này nêu rõ duplicate nào bị từ chối, có thể kèm thông tin dòng dữ liệu nếu ứng dụng cần. Trường hợp đầu vào là mảng chuỗi hoặc danh sách đã được kiểm tra null, một lối tắt là `Set.of(requests.toArray(new String[0]))` để áp dụng chính sách fail-fast của `Set.of`; khác với `Set.of(requests)` vốn tạo Set chứa **một List**.

### Trường hợp D — muốn sửa Set sau khi tạo

```java
var mutable = new java.util.HashSet<>(
        java.util.List.of("A", "B", "A")); // HashSet<String>, size == 2.
mutable.add("C");                         // Hợp lệ.
```

`Set.copyOf` và `Set.of` không được thiết kế để thêm/xóa phần tử sau khi tạo. Nếu cần snapshot không cho sửa **sau** quá trình xây dựng, dùng `Set.copyOf(mutable)` tại thời điểm công bố. Đừng tạo `copyOf` sau mỗi lần `add` nếu không có yêu cầu phiên bản hóa rõ ràng.

### Trường hợp E — cần giữ phần tử trùng và thứ tự

Khi “mỗi lần xuất hiện” đều có ý nghĩa (ví dụ dòng đơn hàng hoặc sự kiện), **không dùng Set**. Giữ `List`:

```java
var events = java.util.List.of("LOGIN", "LOGIN", "LOGOUT");
System.out.println(events.size()); // 3
```

Nếu cần snapshot không cho sửa từ List nguồn, chọn `List.copyOf(source)`: giữ các lần xuất hiện, không loại trùng. Việc đổi List sang Set sẽ làm mất thông tin mà không thể khôi phục từ Set.

## 9. Mối liên hệ với `Collectors.toUnmodifiableSet()`

Ngoài `Set.copyOf`, Java 10 còn có collector tạo tập không cho sửa:

```java
var distinct = java.util.List.of("A", "A", "B").stream()
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
System.out.println(distinct.size()); // 2
```

Giống `Set.copyOf`, collector này **không ném lỗi chỉ vì phần tử trùng**. Nếu các phần tử khác identity nhưng bằng nhau theo `equals`, việc giữ đại diện nào cũng **không được bảo đảm**. Nó phù hợp khi kết quả cần **tính duy nhất**, không cần audit nơi dữ liệu bị trùng.

Ngược lại, `Collectors.toUnmodifiableMap(keyMapper, valueMapper)` ném `IllegalStateException` khi duplicate keys mà không có hàm merge. Không suy rộng quy tắc duplicate-key của Map sang `Set.copyOf` hay `toUnmodifiableSet`.

Nếu cần chính sách loại trùng có thứ tự ưu tiên xác định trên Stream, hãy tìm hiểu `distinct()` trên **ordered stream**, hoặc tự nhóm theo khóa với merge rule cụ thể. Đừng dùng `Set.copyOf` rồi cố suy ngược ra phần tử gốc nào được chọn.

## 10. Các lỗi dễ gặp

| Nhận định / lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `Set.of("A","A")` tự khử trùng | Lúc chạy ném `IllegalArgumentException` | Dùng `Set.copyOf(List.of("A","A"))` khi việc gộp trùng được phép. |
| Nghĩ `Set.copyOf(list)` kiểm tra dữ liệu phải duy nhất | Dữ liệu trùng bị gộp nên dấu hiệu lỗi biến mất | Kiểm tra trùng và ném lỗi trước `copyOf` nếu nghiệp vụ cấm. |
| Nghĩ `Set.of(list)` chuyển List thành Set giá trị | Tạo Set chứa **một đối tượng List** | Dùng `Set.copyOf(list)` hoặc chuyển thành mảng và chấp nhận chính sách của `Set.of`. |
| Nghĩ hai đối tượng khác tham chiếu thì không trùng | `equals` có thể cho kết quả `true` | Hiểu và kiểm tra `equals/hashCode` của loại phần tử. |
| Trông cậy `copyOf` giữ phần tử đầu tiên | Representative được chọn tùy implementation | Chọn first/last bằng quy tắc riêng rồi công bố kết quả. |
| Trông cậy `Set.toString()` giữ thứ tự đầu vào | Thứ tự duyệt `Set.of/copyOf` không xác định | Test bằng `contains/size/equals`. |
| Có null trong đầu vào | `NullPointerException` ở cả hai API | Kiểm tra hoặc chuẩn hóa null theo hợp đồng. |
| Gọi `add/remove` trên kết quả | `UnsupportedOperationException` | Dùng `HashSet` hoặc `LinkedHashSet` khi cần mutable. |
| Tưởng `Set.copyOf` deep-copy các phần tử | Phần tử mutable vẫn được chia sẻ | Dùng value objects bất biến hoặc defensive copying. |
| Dùng `HashSet` để xác định phần tử nào “thắng” khi trùng | Hành vi chọn phần tử không phải hợp đồng nghiệp vụ | Duyệt List nguồn và tự chọn qua Map/merge. |
| Gọi `Set.copyOf` với nguồn có `equals/hashCode` không nhất quán | Set có thể có hành vi khó đoán | Sửa hợp đồng equality, ưu tiên khóa/giá trị bất biến. |

## 11. Bài tập tự luyện (có đáp án)

### Bài 1 — Dự đoán kết quả và ngoại lệ

```java
var list = java.util.List.of("red", "blue", "red");
var a = java.util.Set.copyOf(list);
var b = java.util.Set.of("red", "blue", "red");
```

**Đáp án:** `a.size()==2`. Dòng tạo `b` ném `IllegalArgumentException` trong lúc chạy. Hai dòng đều có cú pháp hợp lệ khi biên dịch. Không dự đoán thứ tự `a`.

### Bài 2 — `Set.of(list)` và `Set.copyOf(list)`

```java
var list = java.util.List.of("A", "B", "A");
var a = java.util.Set.of(list);
var b = java.util.Set.copyOf(list);
```

**Đáp án:** `a` là `Set<List<String>>` có một phần tử `list`. `b` là `Set<String>` chứa hai giá trị phân biệt `A` và `B`. Không có exception từ `Set.of(list)` vì nó chỉ nhận **một phần tử**, dù List bên trong chứa trùng.

### Bài 3 — Phân biệt equality và identity

Cho `a = new String("X")`, `b = new String("X")`. `a == b` là `false` nhưng `a.equals(b)` là `true`. `Set.of(a,b)` ra sao? `Set.copyOf(List.of(a,b))` ra sao?

**Đáp án:** `Set.of(a,b)` ném `IllegalArgumentException`. `Set.copyOf(...)` có `size()==1`. Không cần biết đại diện được giữ có identity là `a` hay `b`.

### Bài 4 — Khi trùng bị cấm về nghiệp vụ

Đầu vào là `List.of("ADMIN","USER","ADMIN")` và contract yêu cầu **không trùng**. Dùng `Set.copyOf` là đúng hay sai?

**Đáp án:** Không đủ, vì `Set.copyOf` sẽ âm thầm gộp trùng. Dùng vòng lặp `HashSet.add` kết hợp kiểm tra giá trị trả về (false khi trùng), ném lỗi và báo vị trí, rồi mới công bố snapshot.

### Bài 5 — Lỗi null

```java
var list = new java.util.ArrayList<String>();
list.add("A");
list.add(null);
java.util.Set.copyOf(list);
```

**Đáp án:** `NullPointerException`. `Set.of("A", (String)null)` cũng ném `NullPointerException`. Không có hành vi “giữ một null” như một số implementation Set mutable có thể cho phép.

### Bài 6 — Kết quả có giữ thứ tự không?

`Set.copyOf(List.of("C","B","A","C"))` có thể được kiểm tra bằng `size()==3`, `contains("A")`, `contains("B")` và `contains("C")`. Có nên yêu cầu `toString()` đúng `[C, B, A]`?

**Đáp án:** Không. `Set.copyOf` không cam kết iteration order. Nếu thứ tự quan trọng, giữ thêm mô hình List có thứ tự hoặc dùng cấu trúc có contract rõ.

### Bài 7 — Phần tử nào được chọn?

Hai `Ticket` có cùng `id` nhưng `label` khác. `Set.copyOf(List.of(first, second))` có thể dùng để lấy bản ghi có label `first` không?

**Đáp án:** Không bảo đảm. Javadoc quy định một đại diện bất kỳ được giữ. Nếu yêu cầu “first wins”, dùng vòng lặp duyệt List theo thứ tự + `LinkedHashMap.putIfAbsent` như trong lab.

### Bài 8 — Chọn collector hay copy

Dữ liệu đến từ `Stream<String>` và cần một tập không cho sửa. Có thể dùng `Collectors.toUnmodifiableSet()`; nó loại trùng. Nếu kết quả đã là List/Collection và cần một Set không cho sửa, `Set.copyOf(collection)` diễn đạt trực tiếp hơn. Cả hai không phù hợp khi trùng bắt buộc phải báo lỗi mà chưa có bước kiểm tra.

### Checklist

- [ ] Nêu được sự khác biệt **`Set.of`: lỗi nếu trùng** và **`Set.copyOf`: chấp nhận rồi khử trùng**.
- [ ] Phân biệt Java 9 (`Set.of`) và Java 10 (`Set.copyOf`) mà không dùng kiến thức legacy.
- [ ] Phân biệt Set của **một List** với Set của **các phần tử trong List**.
- [ ] Nắm vai trò `equals/hashCode`; không dùng `==` để định nghĩa trùng trong Set.
- [ ] Không phụ thuộc đại diện trùng được giữ hoặc thứ tự duyệt của Set kết quả.
- [ ] Biết cả hai API từ chối null và tạo tập không cho sửa.
- [ ] Hiểu snapshot thành viên không phải deep copy phần tử.
- [ ] Chọn `Set.copyOf` khi duplicate hợp lệ; kiểm tra riêng hoặc dùng `Set.of` khi duplicate là lỗi.
- [ ] Chạy `DuplicateSetLab.java` và đối chiếu đúng **13 dòng stdout**.
- [ ] Viết được test assertions dựa trên size/contains/equals thay vì thứ tự hiển thị.

## 12. Tóm tắt thực hành

Chọn `Set.of(...)` khi muốn tạo ngay một tập nhỏ từ các phần tử **đã xác định**, và nếu chỉ định trùng là lỗi mà bạn muốn phát hiện sớm. Chọn `Set.copyOf(collection)` khi có một collection nguồn có thể chứa trùng và **ý nghĩa nghiệp vụ là giữ các phần tử phân biệt** dưới dạng không cho sửa. Nếu duplicate có ý nghĩa tiêu cực (nhập liệu bị lặp, lỗi phân quyền, trùng mã), đừng để `copyOf` che nó; kiểm tra và báo lỗi trước khi gộp.

Phân biệt thêm ba ý: `null` vẫn bị cấm, `equals` quyết định thế nào là trùng, và `Set.copyOf` không được dùng như phép chọn “first wins”. Các hợp đồng này vẫn còn nguyên giá trị trên JDK hiện đại.

## Tài liệu chính thức

- [Oracle Java 25 API — Set, mục `of` và `copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html): mô tả exception khi trùng, null, đại diện bất kỳ và tính không cho sửa.
- [Oracle — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): giải thích sự khác biệt khi chuyển `List` có trùng sang `Set.copyOf` và cách công bố collection không cho sửa.
- [Oracle Java 25 API — Collectors.toUnmodifiableSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableSet()): collector tạo unmodifiable Set từ Stream; xử lý phần tử trùng.
- [Oracle Java 25 API — List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): `List` cho phép phần tử trùng, phù hợp khi mọi lần xuất hiện đều mang ý nghĩa.
- [Oracle Java 25 API — HashSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashSet.html): cấu trúc mutable có nguyên tắc phần tử duy nhất theo Set.