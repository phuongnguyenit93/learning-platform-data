# Sao chép phòng vệ ở đầu vào của đối tượng — thiết kế dữ liệu chỉ đọc (Java 10+)

## 1. Vấn đề cần giải quyết

**Sao chép phòng vệ (defensive copying)** khi nhận dữ liệu đầu vào là tạo một biểu diễn độc lập với các thay đổi về sau từ phía caller trước khi lưu vào trạng thái bên trong đối tượng. Nó đặc biệt quan trọng khi constructor, static factory, builder hoặc một method lưu tham chiếu đến collection, mảng hay object có trạng thái thay đổi được.

Ví dụ thiết kế chưa an toàn:

```java
final class Team {
    private final java.util.List<String> names;

    Team(java.util.List<String> input) {
        this.names = input;
    }

    java.util.List<String> names() {
        return names;
    }
}
```

Khi caller thực hiện:

```java
var input = new java.util.ArrayList<String>(
        java.util.List.of("An", "Binh"));
var team = new Team(input);

input.add("Chi");
System.out.println(team.names()); // [An, Binh, Chi]
```

`Team` chưa hề nhận lệnh cập nhật, nhưng dữ liệu bên trong đã thay đổi. Vì constructor lưu **reference** của list thay vì lưu **snapshot**, caller và object cùng trỏ tới một list mutable. `private` và `final` không thể ngăn caller sửa một object mà họ đang giữ alias.

Trong Java 10+, với danh sách không chứa `null` và các phần tử bất biến như `String`, có thể thiết kế:

```java
final class SafeTeam {
    private final java.util.List<String> names;

    SafeTeam(java.util.Collection<String> input) {
        this.names = java.util.List.copyOf(input);
    }

    java.util.List<String> names() {
        return names;
    }
}
```

`List.copyOf` trả về list không cho sửa, giữ các phần tử theo thứ tự duyệt của input tại thời điểm gọi. Sửa cấu trúc input về sau không thay đổi list nội bộ. Với phần tử `String` bất biến, getter trả list đó cũng không tạo đường sửa dữ liệu.

**Quy tắc trung tâm:** sao chép **ngay tại ranh giới nhận dữ liệu** khi object cần sở hữu một trạng thái ổn định, nhưng đừng nhầm sao chép collection với sao chép sâu mọi object phần tử.

Bài học thuộc chủ đề **Thiết kế dữ liệu chỉ đọc** và chỉ dùng các kiến thức Java vẫn còn áp dụng hiện nay. `List.copyOf`, `Set.copyOf` và `Map.copyOf` có từ Java 10; chương trình độc lập được kiểm tra bằng Java 17+.

## 2. Kết quả học tập

Sau khi học, bạn có thể:

- Nhận biết rủi ro từ alias của mutable input.
- Phân biệt `private final`, unmodifiable collection, immutable element và deep immutability.
- Dùng đúng `List.copyOf`, `Set.copyOf`, `Map.copyOf` trong constructor.
- Phân biệt unmodifiable **view** và independent **snapshot**.
- Giải thích tại sao `List.copyOf(List<MutableItem>)` vẫn có thể quan sát thay đổi bên trong phần tử.
- Tạo bản sao phòng vệ của mảng và dữ liệu lồng nhau.
- Viết compact constructor và accessor của record để không lộ mảng mutable.
- Kiểm tra input theo đúng snapshot sẽ lưu.
- Đánh giá `null`, duplicate, thứ tự duyệt, tính mutable, tính đồng thời và chi phí sao chép.
- Viết test chứng minh caller không thể ảnh hưởng đến object sau khi tạo.

## 3. Cơ chế alias: chép reference khác chép dữ liệu

Một phép gán biến tham chiếu không tạo bản sao:

```java
var original = new java.util.ArrayList<String>();
original.add("A");

var alias = original;
alias.add("B");

System.out.println(original); // [A, B]
System.out.println(alias == original); // true
```

Nếu constructor viết `this.items = input`, hai tham chiếu trỏ đến cùng list. Dù field là `private final List<String>`, caller vẫn có thể `input.add(...)` hoặc `input.set(...)`.

Mô hình:

```text
Caller                                Object nội bộ

input ──────────┐
                ▼
           [List mutable] ◄────────── this.items
                ▲
input.add("X") ─┘

Không có bản sao: trạng thái đọc qua this.items thay đổi.
```

Với copy phòng vệ:

```text
Caller                                 Object nội bộ

input ──► [List mutable]               this.items ──► [List unmodifiable]
                  │                                      ▲
                  └──── copy khi khởi tạo ────────────────┘

Sửa input sau thời điểm copy không thay đổi tập phần tử của this.items.
```

Sơ đồ thứ hai mô tả **hai tập phần tử độc lập về mặt cấu trúc**, không cam kết copyOf luôn tạo instance list mới trong mọi trường hợp. Nếu input đã là unmodifiable list phù hợp, JDK có thể tái sử dụng chính instance đó mà vẫn đáp ứng hợp đồng.

## 4. `List.copyOf`: mẫu constructor phổ biến

```java
final class Options {
    private final java.util.List<String> values;

    Options(java.util.Collection<String> input) {
        this.values = java.util.List.copyOf(input);
    }

    java.util.List<String> values() {
        return values;
    }
}
```

### Hợp đồng cần nhớ

- Bản sao là **unmodifiable list**: `add`, `remove`, `set` và các mutator tương đương không được hỗ trợ.
- Thứ tự phần tử theo **thứ tự duyệt** của collection truyền vào.
- List vẫn **giữ phần tử trùng**.
- Input và từng phần tử **không được `null`**; nếu vi phạm, `List.copyOf` ném `NullPointerException`.
- Sửa các phần tử trong input list sau khi gọi không làm kết quả đổi về mặt **membership/element reference tại mỗi vị trí**.
- Nếu phần tử là mutable object, sửa **trạng thái của chính object** qua một alias khác vẫn có thể hiện ra trong list kết quả.
- Không được kiểm tra kiểu `result instanceof ArrayList` hoặc đồng nhất instance identity như một hợp đồng API.

Ví dụ:

```java
var source = new java.util.ArrayList<String>(
        java.util.List.of("C", "A", "C"));
var snapshot = java.util.List.copyOf(source);

source.add("B");

System.out.println(source);   // [C, A, C, B]
System.out.println(snapshot); // [C, A, C]
```

Nếu nguồn là `HashSet`, `List.copyOf(source)` chỉ giữ **thứ tự duyệt mà source cung cấp**, không tự sắp xếp. Muốn kết quả A–Z, hãy sắp xếp có chủ đích trước khi lưu.

## 5. Vì sao `Collections.unmodifiableList(input)` không tương đương snapshot?

`Collections.unmodifiableList(input)` trả về **view không cho sửa qua view**, không tạo list độc lập khỏi backing list.

```java
var source = new java.util.ArrayList<String>(
        java.util.List.of("A"));
var view = java.util.Collections.unmodifiableList(source);

source.add("B");
System.out.println(view); // [A, B]
```

`view.add("C")` bị chặn, nhưng `source.add("B")` vẫn được. Nếu constructor chỉ bọc nguồn do caller giữ, các thay đổi input vẫn tác động đến trạng thái đọc qua object.

Muốn chụp snapshot mà vẫn giữ `null` có chủ đích:

```java
var copy = new java.util.ArrayList<String>(input);
java.util.List<String> snapshot =
        java.util.Collections.unmodifiableList(copy);
```

**Điều kiện:** không lộ reference `copy` sau khi bọc. Nếu lộ backing copy ở một getter hoặc field khác, ai giữ alias đó vẫn có thể sửa nó.

Bảng lựa chọn:

| Yêu cầu | Cách làm | Giới hạn |
| --- | --- | --- |
| Snapshot List không có null | `List.copyOf(input)` | Không deep-copy phần tử mutable |
| Snapshot List có thể chứa null | `Collections.unmodifiableList(new ArrayList<>(input))` | Không deep-copy phần tử |
| Chỉ cần list mutable mới | `new ArrayList<>(input)` | Caller của getter phải được kiểm soát |
| View live thể hiện thay đổi backing | `Collections.unmodifiableList(input)` | **Không cắt alias nguồn** |
| Dữ liệu snapshot sâu | Copy/convert từng phần tử và collection lồng nhau | Phải xác định ý nghĩa copy theo kiểu dữ liệu |

Đừng dùng view live chỉ vì tên có chữ `unmodifiable`. Chỉ chọn view khi API **chủ đích** cho client nhìn thấy trạng thái cập nhật từ nguồn mà không cấp quyền sửa qua view.

## 6. `Set.copyOf` và `Map.copyOf` ở boundary

### 6.1. `Set.copyOf` có thể làm mất trùng

```java
var input = java.util.List.of("A", "B", "A");
var unique = java.util.Set.copyOf(input);

System.out.println(unique.size());        // 2
System.out.println(unique.contains("A")); // true
```

`Set.copyOf` chụp tập thành viên, trả unmodifiable set và từ chối phần tử `null`. Nếu input là List, phần tử bằng nhau theo `equals` sẽ được gộp; khi có nhiều object bằng nhau nhưng có payload khác, **một đại diện bất kỳ** được giữ, không cam kết giữ phần tử đầu tiên. Không cam kết thứ tự duyệt set.

Chỉ dùng `Set.copyOf` nếu nghiệp vụ thật sự cần **tập hợp giá trị duy nhất**. Nếu cần lưu thứ tự và số lần lặp của item, chọn `List.copyOf`.

### 6.2. `Map.copyOf` giữ mapping nhưng không giữ iteration order

```java
var source = new java.util.HashMap<String, Integer>();
source.put("A", 1);
source.put("B", 2);

var fixed = java.util.Map.copyOf(source);
source.put("C", 3);

System.out.println(fixed.size());           // 2
System.out.println(fixed.containsKey("C")); // false
```

`Map.copyOf`:

- Trả map không cho thêm/xóa/thay mapping qua API của kết quả.
- Giữ các mapping tại thời điểm copy; thay mapping nguồn về sau không ảnh hưởng tập mapping kết quả.
- **Không cho `null` làm key hoặc value.**
- **Không cam kết iteration order**, kể cả khi nguồn là `LinkedHashMap` hoặc `TreeMap`.
- Không clone sâu object key/value.

Nếu cần snapshot giữ thứ tự chèn, có thể tạo `new LinkedHashMap<>(source)` rồi bọc `Collections.unmodifiableMap(...)` trên backing copy không bị lộ. Nếu cần sorted map, sao chép sang `TreeMap` với comparator thích hợp và bọc `Collections.unmodifiableSortedMap(...)`.

### 6.3. Không đổi loại collection chỉ để “bất biến hơn”

`List.copyOf` giữ thứ tự và phần tử trùng; `Set.copyOf` loại trùng; `Map.copyOf` giữ key-value. **Chúng không phải ba API thay thế nhau**. Kiểu dữ liệu cần phản ánh hợp đồng của object.

## 7. Giới hạn lớn nhất: `copyOf` là shallow copy

Giả sử có mutable bean:

```java
final class Member {
    private String name;

    Member(String name) {
        this.name = name;
    }

    String name() { return name; }
    void rename(String value) { name = value; }
}
```

Khi copy list:

```java
var member = new Member("An");
var source = java.util.List.of(member);
var snapshot = java.util.List.copyOf(source);

member.rename("Anh");
System.out.println(snapshot.get(0).name()); // Anh
```

Membership của list không đổi (vẫn một reference `member`) nhưng **trạng thái object `member`** đổi. Việc list không cho gọi `set` không hề cấm `member.rename`.

Phân biệt ba tầng:

1. **Biến `final`:** không thể gán lại reference biến/field.
2. **Unmodifiable collection:** không thể sửa cấu trúc collection qua reference trả về.
3. **Deep immutable object graph:** không có đường reference nào làm thay đổi dữ liệu quan sát được của toàn bộ cấu trúc.

`List.copyOf` đạt tầng 2; nếu các phần tử bất biến thì có thể đáp ứng mục tiêu tầng 3 đối với vùng dữ liệu đó, nhưng điều này **không tự động đúng** cho mọi `T`.

### Ví dụ rất ngắn với `StringBuilder`

```java
var builder = new StringBuilder("A");
var list = java.util.List.of(builder);

builder.append("B");
System.out.println(list.get(0).toString()); // AB
```

Ngay cả `List.of` cũng không đóng băng `StringBuilder`. Tương tự, `Map.copyOf` vẫn chia sẻ key/value mutable và `Set.copyOf` vẫn chia sẻ object phần tử mutable.

## 8. Sao chép từng phần tử thành value object bất biến

Một cách đáng tin hơn khi caller truyền entity mutable là **projection** sang dữ liệu mà object cần giữ.

```java
record MemberInfo(String name) {}

final class Directory {
    private final java.util.List<MemberInfo> members;

    Directory(java.util.List<Member> input) {
        var copy = new java.util.ArrayList<MemberInfo>();
        for (var member : input) {
            copy.add(new MemberInfo(member.name()));
        }
        members = java.util.List.copyOf(copy);
    }

    java.util.List<MemberInfo> members() {
        return members;
    }
}
```

Đây là hai khai báo minh họa dùng class `Member` của mục 7. Khi `member.rename("Anh")` sau constructor:

- Input vẫn chứa `Member` mutable với tên mới.
- `Directory` chỉ giữ `MemberInfo` mới tạo với `String` bất biến, nên tên snapshot cũ vẫn ổn định.
- `List.copyOf` chặn việc sửa collection qua getter.

**Đừng chỉ viết `List.copyOf(input)` nếu mục tiêu là snapshot giá trị của mỗi entity.** Hãy xác định field nào là phần dữ liệu cần sao chép và chuyển sang immutable DTO/record hoặc dùng copy constructor phù hợp.

**Record chưa chắc deep immutable:** nếu một component là mảng, mutable bean hay `List<MutableItem>`, record mặc định vẫn giữ reference tới component đó. Cần copy tương ứng trong constructor/accessor.

## 9. Map có giá trị là list: cần copy từng tầng

Giả sử object nhận `Map<String,List<String>>`:

```java
var tags = new java.util.ArrayList<String>(
        java.util.List.of("read"));
var source = new java.util.HashMap<String, java.util.List<String>>();
source.put("admin", tags);

var onlyOuter = java.util.Map.copyOf(source);
tags.add("write");

System.out.println(onlyOuter.get("admin")); // [read, write]
```

`Map.copyOf` đã cắt alias của **outer map**, nhưng value bên trong vẫn là reference tới list `tags`. Caller có thể sửa trạng thái quan sát được của value.

Mẫu copy hai tầng:

```java
static java.util.Map<String, java.util.List<String>> copyRules(
        java.util.Map<String, ? extends java.util.Collection<String>> input) {

    java.util.Objects.requireNonNull(input, "input");
    var result = new java.util.HashMap<String, java.util.List<String>>();

    for (var entry : input.entrySet()) {
        var key = java.util.Objects.requireNonNull(entry.getKey());
        var values = java.util.List.copyOf(
                java.util.Objects.requireNonNull(entry.getValue()));
        result.put(key, values);
    }

    return java.util.Map.copyOf(result);
}
```

Đây là phương thức minh họa đặt trong class Java. Với key và element là `String` bất biến:

- Tầng ngoài là unmodifiable map.
- Mỗi value là unmodifiable list riêng, không phản ánh thay đổi cấu trúc list nguồn.
- Không có reference tới một mutable list trong cấu trúc được trả về.

Nếu value là `List<Member>` mutable, vẫn cần copy/convert từng `Member`. Nếu cần thứ tự chèn của map, không dùng `Map.copyOf` để bảo toàn thứ tự; thay bằng `LinkedHashMap` copy sau khi copy từng value, bọc `Collections.unmodifiableMap` và không để lộ backing map.

### Phân biệt shallow, hai tầng và deep copy

- `Map.copyOf(input)`: snapshot outer mappings.
- `Map.copyOf(mapWithListCopies)`: snapshot outer mappings **và** cấu trúc list value.
- Copy từng immutable element của list value: snapshot đủ sâu cho vùng dữ liệu muốn bảo vệ.

“Deep copy” phải được đánh giá theo **object graph và mục tiêu nghiệp vụ**, không chỉ đếm số tầng `copyOf`.

## 10. Mảng: phải copy ở chiều vào **và** chiều ra

Mảng Java cho phép sửa phần tử nếu caller có reference. Với `byte[]`, `int[]`, `String[]` và các mảng khác, `final` không làm nội dung mảng trở nên immutable.

Ví dụ lỗi:

```java
final class UnsafePacket {
    private final byte[] bytes;

    UnsafePacket(byte[] input) {
        bytes = input; // Alias vào
    }

    byte[] bytes() {
        return bytes; // Alias ra
    }
}
```

Sửa đúng cho mảng primitive một chiều:

```java
final class Packet {
    private final byte[] bytes;

    Packet(byte[] input) {
        bytes = java.util.Objects.requireNonNull(input).clone();
    }

    byte[] bytes() {
        return bytes.clone();
    }
}
```

Hai lớp trên chỉ là minh họa. Tại constructor, clone cắt alias với mảng caller; tại getter, clone ngăn caller sửa mảng nội bộ.

`java.util.Arrays.copyOf(input, input.length)` cũng tạo mảng mới. Với `int[][]`, cần copy cả từng hàng nếu cần snapshot sâu hai chiều:

```java
static int[][] copyMatrix(int[][] input) {
    var copy = new int[input.length][];
    for (var i = 0; i < input.length; i++) {
        copy[i] = java.util.Objects.requireNonNull(input[i]).clone();
    }
    return copy;
}
```

Mẫu này giả sử mảng ngoài không null và hàng không null; bổ sung `Objects.requireNonNull(input)` nếu muốn fail fast rõ ràng. Với `Member[][]`, clone mỗi hàng **không** tự clone mutable `Member`.

## 11. Record: compact constructor và accessor phòng vệ

Record có từ Java 16, hợp lệ trong ví dụ Java 17+, nhưng record có mutable component **không tự bất biến sâu**.

### Cách chưa an toàn

```java
record UnsafePacket(byte[] bytes) {}
```

Constructor mặc định giữ reference tới mảng; accessor `bytes()` mặc định cũng trả reference đó. Cả caller truyền input và caller nhận mảng từ getter đều sửa được nội dung.

### Cách an toàn hơn cho `byte[]`

```java
record SafePacket(byte[] bytes) {
    public SafePacket {
        bytes = java.util.Objects.requireNonNull(bytes).clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
```

Kỹ thuật:

- Trong **compact constructor**, gán lại tham số `bytes` thành bản copy. Sau khi thân constructor chạy, Java gán giá trị tham số đó cho field record.
- Accessor tùy chỉnh trả bản sao để không lộ field mảng.
- Với mảng một chiều primitive, clone là đủ đối với dữ liệu phần tử.
- Vì bản copy được tạo và trả mỗi lần, test nên so sánh **nội dung**; không dùng `==` như tiêu chí đúng của dữ liệu.

Record với `List<String>`:

```java
record Tags(java.util.List<String> values) {
    public Tags {
        values = java.util.List.copyOf(values);
    }
}
```

Khi `String` bất biến và list đã unmodifiable, accessor mặc định trả list không gây lộ mutable collection. Ngược lại, record `record Members(List<Member> values)` vẫn cần giải quyết mutable elements.

## 12. Validation đúng snapshot rồi mới lưu

Đối tượng chỉ đọc thường có invariant, ví dụ “danh sách tên không rỗng và không có tên trắng”.

Mẫu kém vững:

```java
for (var name : input) {
    if (name.isBlank()) throw new IllegalArgumentException();
}
this.names = java.util.List.copyOf(input);
```

Nếu input là mutable và có thể thay đổi giữa thời điểm validate và copy, dữ liệu đã kiểm tra không nhất thiết là dữ liệu cuối cùng lưu.

Mẫu tốt hơn:

```java
var snapshot = java.util.List.copyOf(input);
for (var name : snapshot) {
    if (name.isBlank()) {
        throw new IllegalArgumentException("blank name");
    }
}
this.names = snapshot;
```

Lợi ích: validation chạy trên **chính snapshot** sẽ gán vào field. Nếu snapshot đã có phần tử null, `List.copyOf` fail fast trước vòng lặp.

**Giới hạn rất quan trọng:** Nếu thread khác đang sửa collection nguồn **ngay trong lúc `copyOf` thực hiện**, thao tác copy không tự mang tính nguyên tử hay transaction. Thiết kế cần bảo đảm nguồn ổn định trong thời gian copy hoặc có cơ chế đồng bộ hóa thích hợp.

Ngoài ra, tránh công bố `this` từ constructor trước khi invariant được thiết lập (chẳng hạn đăng ký callback gọi ngược vào object hoặc chạy thread có thể đọc object quá sớm).

## 13. Builder, static factory và method: copy ở đâu?

### 13.1. Static factory

```java
static SafeTeam fromNames(java.util.Collection<String> names) {
    return new SafeTeam(names);
}
```

Nếu `SafeTeam` đã copy ở constructor, factory không cần copy thêm vô điều kiện. Mỗi ranh giới nhận dữ liệu chỉ cần một thiết kế ownership rõ.

### 13.2. Builder còn được sửa sau `build()`

Giả sử:

```java
var builder = new ExampleBuilder();
builder.add("A");
var first = builder.build();
builder.add("B");
var second = builder.build();
```

Đây là **minh họa API builder chưa định nghĩa**, không phải chương trình chạy độc lập. Nếu `first` là immutable snapshot, nó không được tự đổi khi builder thêm `B`. `build()` hoặc constructor của object kết quả phải chụp trạng thái builder tại thời điểm thích hợp.

### 13.3. Method chỉ xử lý, không lưu reference

Nếu method chỉ duyệt input, tính tổng rồi trả về số, nó có thể không cần defensive copy. Việc sao chép mọi collection không cần thiết sẽ gây chi phí bộ nhớ và CPU.

Hãy copy khi object **giữ dữ liệu lâu dài** hoặc cần snapshot nhất quán theo một thời điểm, chứ không phải vì API nhận `List`.

### 13.4. Có nên trả trực tiếp field?

- Field là `List<String>` từ `List.copyOf`: thường có thể trả thẳng.
- Field là `List<Member>`, các phần tử mutable: trả list không sửa được **vẫn cho caller chạm tới Member**; cần cân nhắc snapshot projection ở output.
- Field là `byte[]`: trả clone hoặc một representation thực sự immutable.
- Field là mutable map: getter có thể trả immutable snapshot hoặc có controlled API thay vì lộ backing map.

Defensive copying là **thiết kế cả inbound và outbound**, không chỉ một câu lệnh ở constructor.

## 14. Concurrency và chi phí sao chép

**Defensive copy không có nghĩa auto-thread-safe.** `List.copyOf` có thể giúp ngăn thay đổi membership về sau nhưng không đồng bộ những object phần tử mutable. `Collections.unmodifiableList(input)` là live view, nên nếu backing list bị sửa đồng thời, việc đọc/duyệt cần phối hợp phù hợp.

Các yếu tố khi chọn copy:

- **Dung lượng:** copy collection lớn cần thời gian và bộ nhớ; tính toán yêu cầu isolation thực sự.
- **Thời điểm:** khi cần snapshot, tạo nó ở boundary một lần thường dễ kiểm soát hơn copy rải rác.
- **Độ sâu:** copy toàn bộ object graph có thể đắt; ưu tiên immutable value object với trường cần thiết.
- **Nguồn đồng thời:** bảo đảm hợp đồng nguồn ổn định hoặc đồng bộ hóa khi snapshot.
- **Khóa dùng trong Map/Set:** nếu key/element có `equals/hashCode` dựa trên field mutable, thay field ấy có thể phá các giả định tra cứu sau copy.
- **Khả năng đọc mã:** `List.copyOf(input)` rõ hơn một chuỗi chuyển đổi vòng vèo khi hợp đồng của nó phù hợp.

`final`, `record` và unmodifiable wrapper không thay thế được một kế hoạch về ownership, defensive copy, invariant và concurrency.

## 15. Chương trình Java 17+ độc lập kiểm chứng alias và phòng vệ

Tạo tệp **`DefensiveCopyInputDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class DefensiveCopyInputDemo {
    static final class LeakyTeam {
        private final List<String> names;

        LeakyTeam(List<String> input) {
            names = input;
        }

        List<String> names() {
            return names;
        }
    }

    static final class ViewTeam {
        private final List<String> names;

        ViewTeam(List<String> input) {
            names = Collections.unmodifiableList(input);
        }

        List<String> names() {
            return names;
        }
    }

    static final class SafeTeam {
        private final List<String> names;

        SafeTeam(Collection<String> input) {
            var snapshot = List.copyOf(input);
            for (var name : snapshot) {
                if (name.isBlank()) {
                    throw new IllegalArgumentException("blank name");
                }
            }
            names = snapshot;
        }

        List<String> names() {
            return names;
        }
    }

    static final class MutableMember {
        private String name;

        MutableMember(String name) {
            this.name = Objects.requireNonNull(name);
        }

        String name() {
            return name;
        }

        void rename(String newName) {
            name = Objects.requireNonNull(newName);
        }
    }

    record MemberInfo(String name) {
        MemberInfo {
            Objects.requireNonNull(name);
        }
    }

    static final class Directory {
        private final List<MemberInfo> members;

        Directory(List<MutableMember> input) {
            var snapshot = new ArrayList<MemberInfo>();
            for (var member : input) {
                snapshot.add(new MemberInfo(member.name()));
            }
            members = List.copyOf(snapshot);
        }

        List<MemberInfo> members() {
            return members;
        }
    }

    record Packet(byte[] bytes) {
        public Packet {
            bytes = Objects.requireNonNull(bytes).clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    static final class NestedRules {
        private final Map<String, List<String>> permissions;

        NestedRules(Map<String, List<String>> source) {
            var copy = new LinkedHashMap<String, List<String>>();
            for (var entry : source.entrySet()) {
                copy.put(Objects.requireNonNull(entry.getKey()),
                        List.copyOf(entry.getValue()));
            }
            permissions = Collections.unmodifiableMap(copy);
        }

        Map<String, List<String>> permissions() {
            return permissions;
        }
    }

    public static void main(String[] args) {
        var input = new ArrayList<String>(List.of("An", "Binh"));
        var leaky = new LeakyTeam(input);
        var live = new ViewTeam(input);
        var safe = new SafeTeam(input);

        input.add("Chi");
        System.out.println("leaky=" + leaky.names());
        System.out.println("live=" + live.names());
        System.out.println("safe=" + safe.names());

        try {
            safe.names().add("Du");
        } catch (UnsupportedOperationException expected) {
            System.out.println("safeAddBlocked=true");
        }

        var mutable = new MutableMember("An");
        var members = new ArrayList<MutableMember>();
        members.add(mutable);
        var shallow = List.copyOf(members);
        var directory = new Directory(members);
        mutable.rename("Anh");
        System.out.println("shallowMember=" + shallow.get(0).name());
        System.out.println("snapshotMember=" + directory.members().get(0).name());

        var originalBytes = new byte[] {1, 2, 3};
        var packet = new Packet(originalBytes);
        originalBytes[0] = 9;
        var leakedGetterCopy = packet.bytes();
        leakedGetterCopy[1] = 8;
        System.out.println("packet=" + Arrays.toString(packet.bytes()));

        var tags = new ArrayList<String>(List.of("read"));
        var sourceRules = new LinkedHashMap<String, List<String>>();
        sourceRules.put("admin", tags);
        var shallowRules = Map.copyOf(sourceRules);
        var nestedRules = new NestedRules(sourceRules);

        tags.add("write");
        sourceRules.put("guest", new ArrayList<>(List.of("view")));
        System.out.println("outerOnly=" + shallowRules.get("admin"));
        System.out.println("nested=" + nestedRules.permissions().get("admin"));
        System.out.println("nestedHasGuest="
                + nestedRules.permissions().containsKey("guest"));

        var repeated = List.of("A", "B", "A");
        System.out.println("listSize=" + List.copyOf(repeated).size());
        System.out.println("setSize=" + Set.copyOf(repeated).size());

        var nullable = new ArrayList<String>(
                Arrays.asList("A", null));
        try {
            new SafeTeam(nullable);
        } catch (NullPointerException expected) {
            System.out.println("nullRejected=true");
        }

        var mapWithNull = new HashMap<String, String>();
        mapWithNull.put("A", null);
        try {
            Map.copyOf(mapWithNull);
        } catch (NullPointerException expected) {
            System.out.println("mapNullRejected=true");
        }

        var nullableSnapshot = Collections.unmodifiableList(
                new ArrayList<>(nullable));
        nullable.add("B");
        System.out.println("nullableSnapshot=" + nullableSnapshot);
        System.out.println("nullableInputSize=" + nullable.size());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 DefensiveCopyInputDemo.java
java DefensiveCopyInputDemo
```

**Stdout dự kiến chính xác:**

```text
leaky=[An, Binh, Chi]
live=[An, Binh, Chi]
safe=[An, Binh]
safeAddBlocked=true
shallowMember=Anh
snapshotMember=An
packet=[1, 2, 3]
outerOnly=[read, write]
nested=[read]
nestedHasGuest=false
listSize=3
setSize=2
nullRejected=true
mapNullRejected=true
nullableSnapshot=[A, null]
nullableInputSize=3
```

Các kết quả cho thấy:

1. `LeakyTeam` giữ alias trực tiếp; `ViewTeam` chỉ tạo live unmodifiable view. Khi caller thêm `Chi`, cả hai cùng phản ánh phần tử mới.
2. `SafeTeam` copy input ngay trong constructor, nên giữ hai tên ban đầu; getter list không cho `add`.
3. `Directory` chuyển từng mutable `Member` thành immutable `MemberInfo`, nên không thấy lần `rename` sau đó; `shallow` vẫn thấy.
4. `Packet` clone ở input và accessor; cả hai thay đổi ở mảng caller không ảnh hưởng mảng nội bộ.
5. `Map.copyOf` chỉ copy outer mappings; `NestedRules` copy cả value lists nên không thấy `write` hoặc key `guest` thêm vào nguồn.
6. `List.copyOf` vẫn giữ trùng, `Set.copyOf` loại trùng; cả hai từ chối null theo hợp đồng.
7. Với yêu cầu có `null`, wrapper trên `new ArrayList<>(nullable)` tạo snapshot phù hợp mà không dựa vào `List.copyOf`.

Không có output nào phụ thuộc iteration order không được cam kết của `Map.copyOf` hoặc `Set.copyOf`.

## 16. Những lỗi thiết kế thường gặp và cách sửa

### Lỗi A: `private final` được hiểu là “dữ liệu bất biến”

```java
private final List<String> values;
values = input; // Vẫn là mutable list do caller giữ
```

**Sửa:** copy input; `final` chỉ cố định reference của field, không tự copy và không làm object được trỏ tới trở nên immutable.

### Lỗi B: unmodifiable wrapper được hiểu là snapshot

```java
var view = Collections.unmodifiableList(input);
input.add("A"); // view vẫn thấy "A"
```

**Sửa:** `List.copyOf(input)` nếu hợp đồng không cho null; nếu cần null, copy vào `ArrayList` rồi bọc trên bản copy.

### Lỗi C: copy lúc getter, không copy lúc nhận

Nếu constructor lưu input gốc rồi getter mới gọi `List.copyOf(field)`, thay đổi của caller trước thời điểm getter đã tác động lên field. Copy ở **đầu vào** mới ngăn ảnh hưởng tương lai ngay từ lúc object được tạo.

### Lỗi D: quên mutable elements

`List.copyOf(List.of(new StringBuilder("A")))` vẫn cho phép gọi `append` trên chính `StringBuilder`. **Sửa:** dùng immutable projection hoặc copy từng element.

### Lỗi E: quên nested collections

`Map.copyOf(mapOfMutableLists)` không làm list value immutable. **Sửa:** copy từng value rồi tạo unmodifiable outer map.

### Lỗi F: record chứa `byte[]` mà không phòng vệ

Record mặc định chỉ giữ reference và trả reference qua accessor. **Sửa:** compact constructor copy mảng và accessor copy mảng ở output.

### Lỗi G: đổi từ List sang Set làm mất duplicate

`Set.copyOf(List.of("A","A"))` có size 1. Chọn kiểu collection đúng với nghiệp vụ thay vì chỉ dựa trên tên hàm `copyOf`.

### Lỗi H: quên `null` và thứ tự

`List/Set/Map.copyOf` từ chối null ở những vị trí được quy định. `Set.copyOf` và `Map.copyOf` không cam kết thứ tự duyệt. Không tự ý lọc null hay dựa vào thứ tự khi chưa có quy tắc nghiệp vụ.

### Lỗi I: validate input rồi copy khác thời điểm

Đã kiểm dữ liệu đầu vào nhưng lúc lưu lại đọc input thay đổi. **Sửa:** snapshot trước, validate snapshot, gán snapshot; đồng thời kiểm soát việc source có thể bị sửa trong lúc copy.

### Lỗi J: kết luận “đã copy nên an toàn đa luồng”

Không. Nếu mutable object phần tử vẫn chia sẻ hoặc nguồn bị sửa đồng thời khi copy, thread-safety chưa được bảo đảm. **Sửa:** thiết kế dữ liệu bất biến, safe publication và cơ chế phối hợp đúng.

## 17. Checklist review

Trước khi chấp nhận input vào một object chỉ đọc:

1. Đối tượng có giữ dữ liệu lâu dài không, hay method chỉ đọc rồi trả ngay?
2. Caller còn giữ reference và có thể sửa input không?
3. Nếu copy, cần snapshot membership hay snapshot toàn bộ giá trị?
4. Kiểu dữ liệu chính là List, Set, Map, array hay nested object graph?
5. Có cần giữ encounter order, sorted order hay duplicate không?
6. Có `null` và có ý nghĩa nghiệp vụ không?
7. Phần tử là immutable value hay mutable bean/array?
8. Với map, value có là collection lồng nhau không?
9. Constructor có validate **chính bản snapshot** sẽ được lưu không?
10. Getter có làm lộ mutable state sau khi đã bảo vệ đầu vào không?
11. Builder có thể bị sửa tiếp sau lần `build()` không?
12. Có thread đồng thời thay đổi nguồn khi copy hay không?
13. Test đã sửa input **sau** khi tạo object và đối chiếu state chưa?
14. Test đã sửa mutable element qua alias khác và sửa array nhận từ getter chưa?
15. Nếu copy tốn kém, có thể thiết kế immutable value object để giảm chi phí không?

Không cần copy vô điều kiện nếu input đã thực sự immutable và có hợp đồng sở hữu rõ. Mục tiêu là **ngăn những thay đổi trái phép đi qua ranh giới object**, không phải tạo càng nhiều bản sao càng tốt.

## 18. Bài tập tự kiểm tra

**Câu 1.** `this.values = input;` trong constructor giữ lại rủi ro gì khi caller có thể gọi `input.add(...)`?

**Câu 2.** `Collections.unmodifiableList(input)` khác `List.copyOf(input)` thế nào nếu caller còn giữ input?

**Câu 3.** Khi list chứa `String` và không có `null`, cách copy nào phù hợp để tạo immutable snapshot?

**Câu 4.** `List.copyOf(List.of("A","A","B"))` và `Set.copyOf(List.of("A","A","B"))` có size lần lượt bao nhiêu?

**Câu 5.** Vì sao `Map.copyOf(Map<String,List<String>>)` có thể chưa đủ để bảo vệ cấu hình permission?

**Câu 6.** Với `record Packet(byte[] data) {}`, caller có thể thay đổi dữ liệu record qua những đường nào?

**Câu 7.** Muốn snapshot một list có phần tử `null` hợp lệ và không cho sửa qua getter, nên chọn cấu trúc nào?

**Câu 8.** `List.copyOf` có luôn tạo một list instance mới không?

**Câu 9.** Tại sao nên validate bản snapshot thay vì validate input rồi copy?

**Câu 10.** `List.copyOf(List<Member>)` có làm `Member` thành immutable không?

**Câu 11.** Khi một method chỉ tính độ dài list rồi trả `int`, không lưu input, có nhất thiết copy không?

**Câu 12.** Constructor đã clone `byte[]` nhưng getter trả thẳng field `byte[]`. Rủi ro nào còn tồn tại?

**Đáp án:**

1. Caller và object vẫn giữ alias tới cùng mutable list, nên sửa input làm state quan sát được của object đổi.
2. Wrapper là live view; `List.copyOf` là snapshot membership không cho sửa theo hợp đồng.
3. `List.copyOf(input)`, nếu cần validate thêm hãy validate chính kết quả sẽ lưu.
4. List size 3, Set size 2 vì gộp các phần tử bằng nhau theo `equals`.
5. Map outer không sửa được nhưng list value vẫn có thể được sửa qua reference khác; phải copy từng value list.
6. Sửa mảng truyền vào sau khi tạo và sửa mảng nhận từ accessor mặc định. Cần copy ở cả hai chiều.
7. `Collections.unmodifiableList(new ArrayList<>(input))`, không làm lộ backing copy.
8. Không. Nếu input đã là unmodifiable list phù hợp, JDK có thể tái sử dụng instance.
9. Để dữ liệu được kiểm tra và dữ liệu lưu là cùng snapshot; vẫn cần kiểm soát đồng thời khi đang copy nguồn.
10. Không. Snapshot list chỉ giữ các reference phần tử; mutable member vẫn có thể đổi.
11. Không bắt buộc; phụ thuộc nhu cầu giữ snapshot và ownership.
12. Caller sửa được field nội bộ qua reference getter; phải trả clone hoặc immutable representation.

## 19. Ghi nhớ và tài liệu Java còn áp dụng

- Defensive copying ở **input boundary** giúp object không bị thay đổi qua alias của mutable input.
- `List.copyOf`, `Set.copyOf`, `Map.copyOf` có từ Java 10 và vẫn được sử dụng trong Java hiện đại.
- `Collections.unmodifiableList(input)` là **view**, không phải snapshot độc lập.
- Factory `copyOf` bảo vệ **cấu trúc collection/mappings**, **không deep-copy mutable elements**.
- Nếu phần tử hoặc value lồng nhau mutable, chuyển đổi thành immutable value và copy từng tầng cần thiết.
- Mảng và record chứa mảng cần **copy ở constructor và getter**.
- Snapshot trước rồi validate snapshot thường bảo vệ invariant tốt hơn việc validate input và copy lại.
- Defensive copy **không** tự tạo snapshot nguyên tử trong khi input bị sửa đồng thời; cần hợp đồng concurrency phù hợp.

Nguồn chính thức:

1. [Java SE 27 — List.copyOf và Unmodifiable Lists](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): thứ tự phần tử, null, snapshot và tính không cho sửa.
2. [Java SE 27 — Set.copyOf](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): trùng phần tử, phần tử đại diện, null và unordered set.
3. [Java SE 27 — Map.copyOf](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): snapshot ánh xạ, null và không cam kết iteration order.
4. [Java SE 27 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): live view backing list.
5. [Java SE 27 — Record](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Record.html): record không tự clone component mutable.
6. [Java SE 27 — Arrays.copyOf](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Arrays.html): sao chép mảng.
