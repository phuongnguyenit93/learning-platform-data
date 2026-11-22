# Tập hợp không cho sửa cấu trúc không đồng nghĩa với bất biến sâu trong Java

## 1. Vấn đề: không gọi được `add()` vẫn chưa có nghĩa dữ liệu không đổi

Trong Java, một tập hợp có thể **không cho phép thay đổi cấu trúc thông qua giao diện của chính nó**, nhưng giá trị mà người dùng nhìn thấy qua tập hợp đó vẫn thay đổi. Nguyên nhân là tập hợp lưu **tham chiếu tới các phần tử**, và có thể chỉ là một *view* trên tập hợp nguồn.

Xét hai ví dụ:

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
source.add("B");
// view giờ là [A, B], dù view.add(...) không được hỗ trợ.
```

```java
StringBuilder item = new StringBuilder("A");
List<StringBuilder> list = List.of(item);
item.append("B");
// list.get(0).toString() giờ là "AB", dù list.add(...) không được hỗ trợ.
```

Hai đoạn là mảnh minh họa (cần import `java.util.*`); chương trình Java 17 đầy đủ có ở phần 6. Trong ví dụ thứ nhất, **collection nguồn** tiếp tục thay đổi và *unmodifiable view* phản ánh thay đổi đó. Trong ví dụ thứ hai, chính **đối tượng phần tử** thay đổi, dù container có giao diện không sửa được.

Do đó cần phân biệt ba khái niệm:

1. **Không sửa được cấu trúc qua tham chiếu đang cầm** (*unmodifiable interface/view*): không thể gọi thành công `add`, `remove`, `set`, `put` hoặc các thao tác cập nhật tương ứng qua tham chiếu đó.
2. **Bản chụp cấu trúc độc lập** (*structural snapshot*): việc thêm, xóa, thay thế phần tử trong collection nguồn về sau không làm thay đổi danh sách/phần tử liên kết được giữ trong bản chụp.
3. **Bất biến sâu** (*deep immutability*): không có đường sửa hợp lệ nào qua các tham chiếu được cung cấp hoặc chia sẻ để thay đổi cả cấu trúc container lẫn trạng thái mutable của những phần tử được coi là một phần giá trị.

Điểm mấu chốt: `unmodifiable` nói về **các thao tác bị cấm qua một API**; `immutable` nói về **trạng thái có thể quan sát có thay đổi theo thời gian không**. Một lớp có thể đáp ứng điều thứ nhất mà không đáp ứng hai điều còn lại.

## 2. Hai trục độc lập: cấu trúc collection và trạng thái phần tử

Một collection chứa các tham chiếu, không phải bản sao tự động của object phần tử. Vì vậy có ít nhất hai kiểu biến đổi cần xem xét:

| Loại biến đổi | Ví dụ | Container unmodifiable có ngăn được không? |
| --- | --- | --- |
| Thêm phần tử mới | `list.add(newItem)` | Ngăn qua API của chính list đó |
| Xóa phần tử | `list.remove(0)` | Ngăn qua API của chính list đó |
| Thay phần tử ở vị trí | `list.set(0, other)` | Ngăn qua API của chính list đó |
| Sửa chính object ở vị trí 0 | `list.get(0).rename("X")` | **Không**, nếu phần tử mutable và lộ tham chiếu |
| Sửa qua alias tới collection nguồn | `backing.add(newItem)` | **Không** với unmodifiable *view* bọc backing mutable |
| Sửa collection lồng trong collection | `list.get(0).add("X")` | **Không**, nếu danh sách con còn mutable |

Một sơ đồ tham chiếu giúp nhận ra rủi ro:

```text
source (ArrayList) ──────────────┐
                                 ▼
unmodifiableView ────────────> backing ArrayList ──> MutableItem #1
                                                       ▲
                                                       │
caller.item ────────────────────────────────────────────┘

view.add(...)                 => bị từ chối
source.add(...)               => thay đổi dữ liệu view thấy được
caller.item.rename(...)       => thay đổi phần tử view thấy được
```

Trong sơ đồ, hai đường thay đổi cuối cùng **không cần** gọi một phương thức sửa trên `unmodifiableView`.

## 3. `Collections.unmodifiableXxx`: view không sửa được

Các hàm như `Collections.unmodifiableList`, `unmodifiableSet`, `unmodifiableMap` trả một lớp bọc không hỗ trợ sửa qua giao diện wrapper. Phần tử và cấu trúc vẫn có thể biến đổi qua **backing collection** nếu mã khác tiếp tục giữ tham chiếu đến nó.

Ví dụ có thể dự đoán:

```java
List<String> backing = new ArrayList<>(List.of("red"));
List<String> view = Collections.unmodifiableList(backing);

backing.add("blue");
System.out.println(view); // [red, blue]

view.add("green"); // Ném UnsupportedOperationException
```

Một `unmodifiableList` không tự gọi `new ArrayList<>(backing)` để tách nguồn. Tương tự, `Collections.unmodifiableMap(map)` không tự chụp một bản độc lập của map, còn `Collections.unmodifiableSet(set)` không tự tách set gốc.

Không nên nhầm với **read-only view** có chủ đích: trong một số API, ta *muốn* người nhận nhìn thấy các cập nhật tiếp theo từ chủ sở hữu nhưng không có quyền cập nhật qua view. Đây là một ngữ nghĩa hợp lệ nếu được thiết kế và mô tả rõ ràng. Nhưng nếu API hứa “bản chụp tại thời điểm gọi” hoặc “giá trị không đổi”, chỉ wrapper là chưa đủ.

Muốn có bản chụp về **cấu trúc**, có thể sao chép trước rồi mới bọc:

```java
List<String> snapshot =
    Collections.unmodifiableList(new ArrayList<>(backing));
```

Sau đó `backing.add(...)` không đổi kích thước `snapshot`. Dù vậy, nếu danh sách chứa `MutableItem` thay vì `String`, cả bản chụp và nguồn vẫn có thể trỏ tới cùng `MutableItem`; việc sửa phần tử còn ảnh hưởng.

## 4. `List.of`, `List.copyOf` và `Stream.toList` bảo đảm gì?

### 4.1. `List.of(...)`

`List.of(a, b, ...)` tạo một list không hỗ trợ thay đổi cấu trúc. Nó không cho phép phần tử `null`. Tuy nhiên, nếu `a` hoặc `b` là mutable object, các object đó **vẫn mutable**; list giữ tham chiếu chứ không tự tạo clone của phần tử.

```java
StringBuilder name = new StringBuilder("A");
List<StringBuilder> names = List.of(name);
name.append("B");
System.out.println(names.get(0)); // AB
```

### 4.2. `List.copyOf(source)`

`List.copyOf` (Java 10+) trả một list không sửa được chứa các phần tử của collection đầu vào tại thời điểm copy, theo thứ tự lặp được quan sát. Khi `source` là một collection mutable thông thường, thay đổi cấu trúc nguồn về sau sẽ không đổi nội dung cấu trúc của list kết quả.

Nhưng:

- Đây là bản sao **nông về phần tử**: các object mutable bên trong vẫn được chia sẻ bằng tham chiếu.
- `List.copyOf` không cho phần tử `null`; nếu input chứa `null` sẽ ném `NullPointerException`.
- Nếu input đã là unmodifiable list phù hợp, JDK có thể **tái sử dụng chính instance đó**; không được phụ thuộc vào việc `copyOf` luôn cấp phát object list mới.
- Bản chụp không tự định nghĩa ngữ nghĩa equality của phần tử; `List.equals()` và `List.hashCode()` sử dụng quan hệ equality/hash của phần tử.

### 4.3. `Stream.toList()` trong Java 17

`stream.toList()` trả một `List` không cho sửa qua các thao tác cập nhật thông thường, giữ thứ tự encounter của stream nếu có. Khác `List.copyOf`, `Stream.toList()` có thể chứa `null`. Việc list không cho sửa **không** khiến mutable object phần tử bất biến. Không dùng tính chất “không sửa được” của kết quả stream để suy ra “bất biến sâu”.

### 4.4. `Set` và `Map` cũng có vấn đề tương tự

- `Set.of`, `Set.copyOf` và `Map.of`, `Map.copyOf` tạo container không sửa được nhưng không sao chép sâu key/value mutable.
- `Set.of` từ chối phần tử trùng theo equality; `Set.copyOf` từ collection có phần tử trùng chỉ giữ một đại diện, không có bảo đảm sẽ giữ đại diện nào trong các bản bằng nhau. Nếu thông tin trùng lặp quan trọng, đừng chuyển danh sách thành set một cách máy móc.
- `Map.copyOf` không nhận key/value `null`; `Set.copyOf` không nhận `null`. Việc chuyển có thể thay đổi chính sách null đang được API chấp nhận.
- Thứ tự duyệt của các collection không sửa được từ `Set.of/copyOf` và `Map.of/copyOf` không nên được giả định là thứ tự chèn hay thứ tự sắp xếp.
- Nếu mutable object được dùng làm key trong map hoặc phần tử set và bị sửa những trường tham gia `equals/hashCode`, lookup có thể hỏng **ngay cả khi chính map/set không sửa được cấu trúc**.

## 5. Bản sao nông và bất biến sâu khác nhau như thế nào?

**Shallow copy** tạo container mới nhưng vẫn giữ các tham chiếu phần tử. Với phần tử bất biến như `String`, `Integer` hoặc một record chỉ chứa giá trị bất biến, shallow copy thường đủ để bảo vệ toàn bộ giá trị mà API quan tâm.

Với phần tử mutable, shallow copy không đủ:

```java
StringBuilder part = new StringBuilder("A");
List<StringBuilder> input = new ArrayList<>();
input.add(part);

List<StringBuilder> shallow = List.copyOf(input);
part.append("B");

System.out.println(shallow.get(0)); // AB
```

Nếu bên ngoài giữ `part`, họ vẫn có thể thay đổi dữ liệu mà `shallow` trình bày. Muốn snapshot thực sự ổn định, phải **sao chép hoặc chuyển đổi từng phần tử mutable** sang biểu diễn bất biến tương ứng:

```java
List<String> stable =
    input.stream()
         .map(StringBuilder::toString)
         .toList();
```

Ở đây `StringBuilder::toString` tạo giá trị `String` bất biến tại thời điểm duyệt; sửa builder sau đó không thay đổi các String đã ghi. Đây là một **phương án snapshot theo giá trị** phù hợp khi chỉ cần nội dung chuỗi, không bảo toàn bản sắc của từng builder.

Với dữ liệu lồng nhau, copy cần đi qua từng cấp mutable:

```java
// input: List<List<String>>, các danh sách con ban đầu mutable.
// Sau thao tác này, cả container ngoài và từng container trong đều
// không sửa được; String cũng bất biến.
List<List<String>> nestedSnapshot = List.copyOf(
    input.stream().map(List::copyOf).toList()
);
```

Đây là mảnh minh họa dùng `java.util.List`, đặt trong bối cảnh có biến `input` đúng kiểu. Trường hợp `List<List<MutableItem>>` vẫn cần sao chép/chuyển đổi từng `MutableItem`; wrapper hai tầng chưa thành deep immutability.

Một điểm quan trọng: “bất biến sâu” phải được xét đối với **đồ thị trạng thái liên quan**. Nếu object con là một kết nối mạng, một đối tượng có ID định danh hay một nguồn dữ liệu sống, việc sao chép mọi thứ theo kiểu clone tổng quát vừa không luôn khả thi vừa có thể sai nghĩa. Lớp cần xác định dữ liệu nào thuộc giá trị và ranh giới nào cần snapshot.

## 6. Ví dụ Java 17 chạy được: view, snapshot và phần tử mutable

Ví dụ đầy đủ dưới đây đối chiếu bốn trường hợp: view phản ánh backing list; structural snapshot tách backing nhưng chưa tách phần tử; snapshot sâu của giá trị phần tử; danh sách lồng nhau được sao chép từng cấp.

Lưu thành **`CollectionDeepImmutabilityDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class CollectionDeepImmutabilityDemo {
    static final class MutableItem {
        private String code;

        MutableItem(String code) {
            this.code = Objects.requireNonNull(code);
        }

        String code() {
            return code;
        }

        void rename(String newCode) {
            this.code = Objects.requireNonNull(newCode);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof MutableItem that)) return false;
            return code.equals(that.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    record ImmutableItem(String code) {
        ImmutableItem {
            Objects.requireNonNull(code);
        }
    }

    static final class Catalog {
        private final List<ImmutableItem> items;

        Catalog(List<MutableItem> source) {
            Objects.requireNonNull(source);
            this.items = source.stream()
                .map(item -> new ImmutableItem(item.code()))
                .toList();
        }

        List<ImmutableItem> items() {
            return items;
        }
    }

    static final class ShallowKey {
        private final List<MutableItem> parts;

        ShallowKey(List<MutableItem> source) {
            parts = List.copyOf(source);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof ShallowKey that)) return false;
            return parts.equals(that.parts);
        }

        @Override
        public int hashCode() {
            return parts.hashCode();
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("red"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("blue");
        System.out.println("View: " + view);
        System.out.println("Snapshot: " + snapshot);
        try {
            view.add("green");
        } catch (UnsupportedOperationException ex) {
            System.out.println("View rejects add: true");
        }

        MutableItem item = new MutableItem("A");
        List<MutableItem> shallow = List.copyOf(List.of(item));
        Catalog catalog = new Catalog(List.of(item));
        item.rename("B");

        System.out.println("Shallow item: " + shallow.get(0).code());
        System.out.println("Catalog item: " + catalog.items().get(0).code());
        try {
            catalog.items().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("Catalog rejects clear: true");
        }

        List<String> inner = new ArrayList<>(List.of("x"));
        List<List<String>> outer = new ArrayList<>();
        outer.add(inner);
        List<List<String>> outerOnly = List.copyOf(outer);
        List<List<String>> allLevels = List.copyOf(
            outer.stream().map(List::copyOf).toList()
        );

        inner.add("y");
        System.out.println("Outer-only nested: " + outerOnly.get(0));
        System.out.println("All-level nested: " + allLevels.get(0));

        MutableItem keyPart = new MutableItem("K1");
        ShallowKey key = new ShallowKey(List.of(keyPart));
        Set<ShallowKey> keys = new HashSet<>();
        keys.add(key);
        int before = key.hashCode();
        keyPart.rename("K2");
        System.out.println("Key hash changed: "
            + (before != key.hashCode()));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên** trong thư mục chứa tệp:

```bash
javac CollectionDeepImmutabilityDemo.java
java CollectionDeepImmutabilityDemo
```

Kết quả chuẩn:

```text
View: [red, blue]
Snapshot: [red]
View rejects add: true
Shallow item: B
Catalog item: A
Catalog rejects clear: true
Outer-only nested: [x, y]
All-level nested: [x]
Key hash changed: true
```

Giải thích chi tiết:

1. `Collections.unmodifiableList(source)` là **view** trên `source`; khi thêm `"blue"` vào nguồn, view hiện `[red, blue]`. `List.copyOf(source)` đã tạo structural snapshot ban đầu `[red]`, nên không thay đổi.
2. View không cho `add` thông qua nó; exception chỉ xác nhận API view không sửa được, **không xác nhận backing không đổi**.
3. `shallow` giữ chính tham chiếu `MutableItem`. Dù container không cho cập nhật, `item.rename("B")` làm giá trị phần tử quan sát được đổi sang `B`.
4. `Catalog` chuyển mỗi `MutableItem` thành một `ImmutableItem` có field kiểu `String` bất biến. Kết quả thu tại thời điểm `"A"`, độc lập với việc đổi `item` về sau. `Stream.toList()` cho container không sửa được, nên cả cấu trúc lẫn các giá trị record trong ví dụ đều ổn định.
5. `outerOnly` copy **list ngoài** nhưng vẫn tham chiếu `inner` mutable; khi sửa `inner`, nội dung của `outerOnly.get(0)` đổi. `allLevels` copy list con trước khi copy list ngoài; giá trị `[x]` được giữ nguyên.
6. `ShallowKey` copy container bằng `List.copyOf` nhưng vẫn chứa một `MutableItem` có equality/hash dựa trên `code` mutable. Đổi code từ `K1` sang `K2` làm hash của cả `ShallowKey` thay đổi. Điều này nguy hiểm nếu `ShallowKey` đang được dùng làm khóa trong `HashSet`/`HashMap`. Ví dụ chỉ kiểm tra hash đã đổi, không phụ thuộc giả định về bucket hay kết quả tra cứu cụ thể của implementation.

## 7. Liên hệ hợp đồng `equals()` và `hashCode()`

Trong Java, một `List` được so sánh theo thứ tự phần tử: `List.equals` lần lượt so các phần tử bằng quy tắc equality; `List.hashCode` tổng hợp hash của các phần tử theo thứ tự. `Set` và `Map` có hợp đồng equality/hash dựa trên các phần tử hoặc entry tương ứng.

Nếu một phần tử mutable nằm trong list, thay đổi của phần tử có thể thay đổi:

- Kết quả `list.equals(otherList)`.
- Giá trị `list.hashCode()`.
- Giá trị `hashCode()` của một đối tượng bọc list và sử dụng list làm thành phần equality/hash.

Đây là lý do một khóa được tạo bằng `List.copyOf(mutableElements)` **vẫn có thể là khóa không ổn định** dù list không cho thay đổi cấu trúc. Khi object đã nằm trong một cấu trúc hash, nên tránh thay đổi các thông tin dùng trong `equals()` và `hashCode()` của khóa. Nếu cần khóa theo nội dung, hãy lưu các phần tử dưới dạng value object bất biến hoặc snapshot.

Các nguyên tắc cần tuân theo:

- **Equal implies same hash:** nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()` phải là `true`; chiều đảo lại không bắt buộc.
- **Hash nhất quán theo trạng thái equality:** mã hash phải giữ ổn định khi các thông tin được dùng trong equality không đổi. Sửa mutable element có thể làm cả equality và hash biến đổi.
- **Không dùng tính unmodifiable của container để chứng minh an toàn khi làm hash key.** Kiểm tra cả keys, values và các đối tượng lồng nhau.
- **Không đưa object mutable làm key của một `Map` chỉ vì map đã được tạo bằng `Map.copyOf`.** Bất biến cấu trúc map và tính ổn định của key là hai chuyện khác nhau.

Nếu một phần tử mutable **không** dùng những trường thay đổi trong `equals/hashCode` (ví dụ class kế thừa identity equality), sửa dữ liệu hiển thị có thể không làm hash của list đổi. Nhưng list đó vẫn **không bất biến sâu**: nội dung có thể quan sát từ phần tử vẫn biến đổi. Đây là hai tiêu chí riêng cần kiểm tra.

## 8. Thiết kế API bảo vệ giá trị collection

### 8.1. Khi collection chứa giá trị bất biến

Ví dụ với `List<String>`:

```java
final class Tags {
    private final List<String> tags;

    Tags(List<String> input) {
        tags = List.copyOf(input);
    }

    List<String> tags() {
        return tags;
    }
}
```

Đây là một lớp minh họa Java hoàn chỉnh không có `main`. `Tags` giữ snapshot cấu trúc bằng `List.copyOf` và `String` là bất biến. Vì vậy getter có thể trả trực tiếp list đã lưu: caller không thể `add/set/remove` qua đó và không thể sửa nội dung String. Nếu business domain cho phép `null` hoặc đòi bảo toàn một cấu trúc khác, phải chọn cách sao chép theo hợp đồng thay vì áp dụng `copyOf` bất kể dữ liệu.

### 8.2. Khi collection chứa phần tử mutable

Đừng dừng ở `List.copyOf(input)`:

```java
// Ví dụ: giá trị cần công bố chỉ là tên tại thời điểm tạo.
List<String> namesSnapshot = input.stream()
    .map(Person::name)
    .toList();
```

Đây là mảnh code minh họa, giả định `input` là `List<Person>` và `Person.name()` trả `String`. Kết quả là list không sửa được của các String bất biến. Nếu cần toàn bộ trạng thái người, hãy thiết kế immutable DTO/record snapshot:

```java
record PersonSnapshot(String id, String name) {}
// Trong luồng chuyển đổi, nếu Person có các getter tương ứng:
List<PersonSnapshot> snapshots = input.stream()
    .map(p -> new PersonSnapshot(p.id(), p.name()))
    .toList();
```

Đây cũng là mảnh code minh họa; record trên chỉ đủ bất biến sâu nếu các component là giá trị bất biến. Nếu đưa `List<MutableAddress>` vào record thì record không tự copy sâu chúng.

### 8.3. Khi giá trị lồng nhau là map/list

Với `Map<String, List<String>>` và String bất biến, có thể copy từng list rồi copy map:

```java
// input là Map<String, List<String>>.
Map<String, List<String>> nested = new HashMap<>();
input.forEach((key, value) ->
    nested.put(key, List.copyOf(value)));
Map<String, List<String>> snapshot = Map.copyOf(nested);
```

Đoạn này cần import `java.util.Map` và `java.util.HashMap`, là mảnh code minh họa ở phạm vi có biến `input`. Kết quả không cho sửa cấu trúc map và list value, còn String ở cả key và value là bất biến. Nếu map chứa các object mutable làm key hoặc value, phải xử lý chúng. Nếu cần giữ thứ tự chèn hoặc giá trị `null`, cần dùng loại collection và cách bọc phù hợp, không tự ý đổi nghĩa dữ liệu.

### 8.4. Phân biệt snapshot với dữ liệu sống

Một API có thể chọn một trong hai hợp đồng:

- **Snapshot:** “Dữ liệu nhận được là giá trị tại thời điểm gọi; cập nhật tiếp theo từ chủ sở hữu không phản ánh vào bản trả về.”
- **View đang sống:** “Dữ liệu trả về có thể phản ánh cập nhật từ chủ sở hữu; bên nhận không thể cập nhật qua view này.”

Cả hai đều hợp lệ nếu tài liệu hóa rõ. Để hỗ trợ an toàn luồng hoặc hashing, cần thêm cam kết về đồng bộ và tính ổn định của **đối tượng phần tử**; chỉ API unmodifiable không giải quyết toàn bộ.

## 9. Các ngộ nhận thường gặp

| Ngộ nhận | Thực tế | Cách xử lý |
| --- | --- | --- |
| “Gọi `add` bị exception thì list bất biến sâu” | Có thể chỉ là view và/hoặc chứa phần tử mutable | Kiểm tra backing alias và từng cấp phần tử |
| “`Collections.unmodifiableList` tự sao chép source” | Là view bọc backing collection | Copy trước rồi bọc nếu cần snapshot |
| “`List.copyOf` clone từng object phần tử” | Sao chép tham chiếu phần tử | Chuyển thành DTO/giá trị bất biến hoặc deep copy thích hợp |
| “`List.of` chứa phần tử mutable mà vẫn immutable sâu” | Container không sửa được, phần tử vẫn mutable | Tạo snapshot giá trị phần tử |
| “`final List<Person>` là một danh sách bất biến” | `final` chỉ ngăn gán lại field; không khóa nội dung list/person | Lưu immutable snapshot và kiểm soát getter |
| “Record luôn bất biến sâu” | Record component có thể trỏ tới array/collection/object mutable | Copy-in, copy-out và xử lý từng component mutable |
| “Copy một list ngoài đủ cho mọi nested list” | List con vẫn có thể được chia sẻ | Copy các tầng có thể sửa |
| “Unmodifiable `Map` bảo vệ giá trị mutable” | Value mutable vẫn thay đổi từ alias | Copy hoặc dùng value bất biến |
| “Collection unmodifiable làm `hashCode` ổn định” | Hash có thể phụ thuộc các phần tử mutable | Dùng trường/giá trị ổn định trong equality/hash |
| “Copy luôn là snapshot nguyên tử trong concurrency” | Nguồn có thể bị sửa trong quá trình copy | Đồng bộ khi đọc/ghi hoặc dùng snapshot bất biến theo thiết kế |

## 10. Những giới hạn cần biết

### 10.1. Không có một `deepCopy` tổng quát cho mọi object graph

Đối tượng có thể tham chiếu vòng, chứa tài nguyên hệ thống, cache, trạng thái đa luồng hoặc khóa nhận diện duy nhất. Sao chép tất cả node có thể làm sai ngữ nghĩa. Nên xác định rõ **biểu diễn giá trị cần bất biến**, xây immutable representation riêng hoặc đặt quyền sở hữu dữ liệu rõ ràng.

Ví dụ, với một `Person` có danh sách `Address` mutable, có thể lưu `List<AddressSnapshot>` với từng địa chỉ gồm các trường String và số bất biến. Đây là copy theo giá trị nghiệp vụ, thường rõ hơn cố clone mù toàn bộ `Person`.

### 10.2. Tính bất biến và thread safety không đồng nhất

Một graph thực sự bất biến sau khi được khởi tạo và **công bố an toàn** có thể được chia sẻ để đọc mà không cần khóa cho việc bảo vệ giá trị đó. Nhưng bản thân việc gọi `List.copyOf(source)` khi một thread khác đang sửa `source` không bảo đảm có snapshot nguyên tử; có thể phát sinh dữ liệu không nhất quán hoặc exception tùy cấu trúc. Cần giao thức đồng bộ giữa bên ghi và bên sao chép, hoặc chuyển quyền sở hữu/trao đổi snapshot bất biến.

Unmodifiable view của `ArrayList` không tự làm `ArrayList` thread-safe. Tương tự, object phần tử mutable trong immutable container vẫn cần cơ chế đồng bộ nếu bị nhiều thread truy cập thay đổi.

### 10.3. Chi phí sao chép và lựa chọn đường API

Copy container có chi phí tỷ lệ với kích thước collection; copy sâu còn cộng chi phí từng phần tử và dữ liệu lồng nhau. Nếu getter thường xuyên tạo snapshot của danh sách lớn, có thể cân nhắc lưu immutable snapshot một lần, trả thao tác truy vấn dạng `size()`/`get()` cho giá trị bất biến, hoặc tổ chức cơ chế version/snapshot phù hợp. Không tối ưu bằng cách vô tình trả alias mutable làm lộ bất biến.

## 11. Quy trình review một trường collection

Khi đánh giá class có field `List`, `Set` hoặc `Map`, hãy lần lượt trả lời:

1. Collection được tạo ở đâu? Có caller nào vẫn giữ tham chiếu đến backing collection không?
2. Constructor có giữ nguyên tham chiếu của collection đầu vào, dùng wrapper view hay tạo structural snapshot?
3. Getter có trả bản sao, immutable container hoặc view đang sống? Hợp đồng có nêu rõ sự khác biệt không?
4. Phần tử thuộc loại bất biến hay mutable? Có thể sửa từng phần tử thông qua alias bên ngoài hoặc `get` không?
5. Các phần tử có chứa array, list, map hay object mutable bên trong không? Đã bảo vệ tới độ sâu cần thiết chưa?
6. Key/value của map và phần tử của set có equality/hash dựa vào trạng thái mutable không?
7. Có yêu cầu đặc biệt về `null`, phần tử trùng, thứ tự hoặc tính tương thích của dữ liệu không?
8. Khi thread khác sửa source lúc copy, dữ liệu snapshot có cần nhất quán không và cơ chế nào bảo đảm điều đó?
9. Bài test có thử thay đổi source sau constructor, sửa phần tử qua tham chiếu giữ lại, sửa thông qua getter và sửa collection lồng nhau không?

Một phép kiểm tra thực tế tốt là vừa thử `add` lên list trả về, **vừa thử sửa backing list, từng object phần tử và nested collection**. Chỉ kiểm tra ngoại lệ từ `add` là chưa đủ để kết luận bất biến sâu.

## 12. Tự kiểm tra

**Câu 1.** `Collections.unmodifiableList(backing)` trả view; sau đó `backing.add("B")`. View có hiển thị `"B"` không?

**Đáp án:** Có. Wrapper cấm cập nhật qua view nhưng phản ánh thay đổi của backing collection.

**Câu 2.** `List.copyOf(source)` chứa `MutableItem`. Sau copy, bên gọi có thể gọi `item.rename("B")` và thấy tên đổi qua list không?

**Đáp án:** Có, nếu list và bên gọi vẫn giữ cùng tham chiếu `MutableItem`. `List.copyOf` chỉ sao chép cấu trúc/phần tử dưới dạng tham chiếu, không clone từng object mutable.

**Câu 3.** Bạn lưu `List<String>` từ `List.copyOf` vào một field cuối và chỉ trả chính list đó qua getter. Bất biến sâu đối với những chuỗi ấy được bảo vệ chưa?

**Đáp án:** Có, nếu không có dữ liệu mutable khác trong graph liên quan, bởi list không sửa được và String là bất biến. Việc container có phải instance mới ở mỗi lần gọi hay không không ảnh hưởng tính bất biến của giá trị này.

**Câu 4.** Tạo `List<List<String>> outerCopy = List.copyOf(outer)` trong khi các list con vẫn mutable. Bất biến sâu đã có chưa?

**Đáp án:** Chưa. Cần snapshot từng list con trước (ví dụ `List.copyOf(inner)`) rồi mới đóng băng list ngoài.

**Câu 5.** Vì sao `Map.copyOf(source)` không bảo đảm khóa map an toàn khi dùng trong cấu trúc hash nếu key mutable?

**Đáp án:** `Map.copyOf` không sao chép sâu key. Nếu key bị thay đổi dữ liệu tham gia `equals/hashCode`, quan hệ equality hoặc hash có thể thay đổi, làm hỏng việc tìm kiếm dù bản thân map cấm sửa cấu trúc.

**Câu 6.** Một class trả `Collections.unmodifiableList(new ArrayList<>(source))`. Đây là snapshot sâu chưa?

**Đáp án:** Đây là snapshot **cấu trúc** độc lập ở cấp list ngoài; chưa phải snapshot sâu nếu source chứa các object mutable hoặc collection lồng nhau.

**Câu 7.** Một record chỉ chứa component `List<MutableItem>`. Record tự động làm giá trị đó bất biến sâu không?

**Đáp án:** Không. Trường component là final nhưng mutable list và mutable item có thể bị thay đổi qua tham chiếu chia sẻ; cần thiết kế copy-in/copy-out và snapshot của phần tử khi cần.

---

**Ghi nhớ:** “Không cho sửa cấu trúc” mới bảo vệ **các thao tác lên container thông qua một tham chiếu**. Một *unmodifiable view* vẫn có thể phản ánh cập nhật của backing collection; một immutable structural snapshot vẫn có thể chứa object mutable. Muốn bất biến sâu, hãy xem toàn bộ graph dữ liệu có thể quan sát, bảo vệ alias ở cả đầu vào và đầu ra, và chuyển các thành phần mutable liên quan thành giá trị hoặc snapshot bất biến.