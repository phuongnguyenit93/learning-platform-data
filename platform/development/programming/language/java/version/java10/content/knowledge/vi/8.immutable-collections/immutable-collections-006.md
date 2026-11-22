# Hành vi khi đối tượng phần tử vẫn có thể thay đổi trong Collection chỉ đọc (Java 10+)

## 1. Mấu chốt: collection không sửa được ≠ đối tượng bên trong bất biến

Trong Java, các collection thường được gọi là “chỉ đọc” (read-only) hoặc chính xác hơn là **unmodifiable collection** có thể chặn các thao tác thay đổi cấu trúc/nội dung phần tử của collection qua API của nó: thêm, xóa, thay tham chiếu ở một vị trí hoặc cập nhật ánh xạ. Tuy nhiên, nếu một phần tử bên trong là **đối tượng có trạng thái thay đổi được (mutable object)**, việc thay đổi **trạng thái của chính đối tượng đó** vẫn có thể xảy ra.

```java
class Member {
    String name;
    Member(String name) { this.name = name; }
}

var member = new Member("An");
var members = java.util.List.of(member);

member.name = "Anh";                       // Hợp lệ: sửa đối tượng Member
System.out.println(members.get(0).name);   // Anh
// members.add(new Member("Binh"));         // UnsupportedOperationException
// members.set(0, new Member("Chi"));       // UnsupportedOperationException
```

Đây là đoạn minh họa trong một ngữ cảnh có thể khai báo lớp `Member`. Danh sách vẫn chỉ có một tham chiếu phần tử, nhưng **đối tượng được tham chiếu đã đổi tên**.

**Kết luận cần nhớ:** *không thể sửa danh sách* không đồng nghĩa *không thể sửa các đối tượng mà danh sách chứa*. Quy tắc này áp dụng cho `List.of`, `List.copyOf`, `Set.of`, `Map.of`, các collector không sửa được và view `Collections.unmodifiable...` nếu phần tử/giá trị có thể thay đổi. Đây vẫn là hành vi của Java hiện đại, không phải kiến thức đã lỗi thời.

Sau bài này, bạn sẽ phân biệt các tầng có thể thay đổi, hiểu vai trò của alias/reference, so sánh snapshot và live view, đánh giá ảnh hưởng đến `equals/hashCode`, biết cách xây API thực sự an toàn hơn và kiểm chứng bằng chương trình Java 17+.

## 2. Ba tầng “không thay đổi” cần phân biệt

Cùng một biến danh sách, hãy tách ba câu hỏi:

1. **Có thể gán lại biến không?** Ví dụ `final var names = ...` cấm `names = otherList`, nhưng không tự đóng băng đối tượng được trỏ tới.
2. **Có thể sửa collection qua tham chiếu này không?** `List.of(...)`, `List.copyOf(...)` và `Collections.unmodifiableList(...)` chặn `add`, `remove`, `set`, `clear` và các thao tác sửa tương đương qua giao diện được trả về.
3. **Có thể sửa đối tượng phần tử không?** Nếu phần tử là một `Member` có phương thức `rename` hoặc trường có thể ghi, việc gọi `list.get(0).rename("...")` tác động trực tiếp lên phần tử, không phải là lời gọi sửa cấu trúc collection.

| Tình huống | Gán lại tên biến | Thêm/xóa/thay phần tử trong list | Sửa trạng thái phần tử |
| --- | --- | --- | --- |
| `var list = new ArrayList<Member>();` | Có | Có | Có, nếu `Member` mutable |
| `final var list = new ArrayList<Member>();` | Không | Có | Có |
| `var list = List.of(member);` | Có | Không qua list | Có, nếu `member` mutable |
| `final var list = List.copyOf(source);` | Không | Không qua list | Có, nếu phần tử mutable |
| `var view = Collections.unmodifiableList(source);` | Có | Không qua view | Có; thêm nữa, sửa `source` có thể hiện lên view |

“Collection chỉ đọc” đôi khi được dùng lỏng để nói rằng client chỉ được phép gọi API đọc. Trong tài liệu Java, hãy phân biệt **unmodifiable collection** và **unmodifiable view**, vì chúng có tính chất sao chép/tham chiếu khác nhau.

### Mô hình tham chiếu

```text
Member member  ──────────────┐
                             ▼
                       [Member{name="An"}]
                             ▲
List.of(member) ── phần tử 0 ┘

member.rename("Anh")  ──> [Member{name="Anh"}]
List.of(member).get(0) vẫn trỏ tới chính đối tượng đó.
```

Java không tự tạo bản sao sâu của đối tượng `Member` chỉ vì nó được đưa vào một collection không sửa được.

## 3. Phép sửa cấu trúc và phép sửa đối tượng khác nhau thế nào?

Với `List<Member> people = List.of(member);`:

**Những thao tác bị chặn trên list:**

```java
// Ví dụ cố ý gây ngoại lệ ở thời gian chạy:
// people.add(new Member("Binh"));        // Không thể thêm phần tử
// people.remove(0);                      // Không thể xóa phần tử
// people.set(0, new Member("Binh"));      // Không thể thay reference tại chỉ số 0
// people.clear();                        // Không thể xóa toàn bộ phần tử
```

Theo hợp đồng của `List.of` và `List.copyOf`, lời gọi mutator ném `UnsupportedOperationException`, kể cả khi một thao tác cụ thể có vẻ không làm thay đổi kết quả. Đừng dựa vào việc mutator trên danh sách rỗng sẽ được phép.

**Những thao tác vẫn có thể hợp lệ:**

```java
people.get(0).rename("Binh"); // Nếu Member có phương thức đổi tên
member.rename("Lan");         // Qua một reference khác cùng đối tượng
```

Không có `List.add` hay `List.set` nào ở đây. Phần tử list vẫn là **cùng một object reference**; chỉ các field của đối tượng thay đổi.

Với phần tử không có API sửa trạng thái, chẳng hạn `String` hoặc một kiểu dữ liệu bất biến được thiết kế tốt, vấn đề khác đi:

```java
var names = List.of("An", "Binh"); // String là bất biến
var newer = names.get(0).toUpperCase(); // Tạo/nhận một String khác
// names.set(0, newer);                  // Vẫn không hợp lệ
```

`String.toUpperCase()` không sửa đối tượng `String` gốc. Nhờ đó list các chuỗi thường ổn định hơn list các mutable beans. Tuy vậy không được suy rộng rằng mọi phần tử mang kiểu `record`, `final` hay chỉ có getter đều tự động bất biến sâu.

## 4. So sánh `List.of`, `List.copyOf` và `Collections.unmodifiableList`

Ba cách này đều đưa ra một list không thể sửa **thông qua tham chiếu được trả về**, nhưng có khác biệt quan trọng:

| Cách tạo | Có thể sửa list được trả về? | Thay đổi thêm/xóa ở nguồn có hiện lên không? | Thay đổi trạng thái của phần tử dùng chung có hiện lên không? |
| --- | --- | --- | --- |
| `List.of(a, b)` | Không | Không có backing list nguồn để theo dõi; tập phần tử được chọn lúc tạo | **Có**, nếu `a` hoặc `b` mutable |
| `List.copyOf(source)` | Không | **Không**: snapshot tập phần tử theo thời điểm gọi | **Có** nếu các object reference được chia sẻ và mutable |
| `Collections.unmodifiableList(source)` | Không qua wrapper | **Có**: đây là live view của `source` | **Có**, vì phần tử cũng được chia sẻ |
| `Collections.unmodifiableList(new ArrayList<>(source))` | Không qua wrapper | Không phản ánh các thay đổi cấu trúc tiếp theo ở `source` gốc | **Có**, nếu phần tử chỉ được copy reference |

Tất cả cách trên đều có thể chứa tham chiếu đến cùng một đối tượng mutable. Riêng `List.copyOf` dùng để tạo bản sao **tập phần tử**, không phải bản sao sâu của từng đối tượng. Với một input đã không sửa được, `List.copyOf` có thể tái sử dụng chính instance input; không nên kiểm tra `==` để suy đoán cơ chế sao chép.

### 4.1. `List.of(...)`: phần tử cố định, object vẫn có thể mutable

```java
var p = new Member("An");
var fixed = List.of(p);
p.rename("Anh");
System.out.println(fixed.get(0)); // In theo toString() của Member, có thể thấy "Anh"
```

Trong đoạn này, giả sử `Member.toString()` trả về tên; `List.of` không ngăn `p.rename`.

`List.of` không cho phép phần tử `null`. Nó không tạo một bản copy sâu của `p`.

### 4.2. `List.copyOf(source)`: snapshot cấu trúc, không snapshot trạng thái object

```java
var p = new Member("An");
var source = new ArrayList<Member>();
source.add(p);

var copy = List.copyOf(source); // snapshot gồm một reference tới p
source.add(new Member("Binh")); // source có 2 phần tử, copy vẫn có 1
p.rename("Anh");                // Cả source và copy đều thấy p.name == "Anh"
```

Thay đổi thứ tự phần tử, thêm hoặc xóa trong `source` sau thời điểm `copyOf` không làm thay đổi các phần tử được giữ trong `copy`. Nhưng khi sửa **chính object `p`**, cả hai cùng quan sát trạng thái mới.

`List.copyOf` không chứa `null`; nếu input có phần tử `null`, phương thức ném `NullPointerException`.

### 4.3. `Collections.unmodifiableList(source)`: live view

```java
var source = new ArrayList<String>(List.of("An"));
var view = Collections.unmodifiableList(source);

source.add("Binh");
System.out.println(view); // [An, Binh]
// view.add("Chi");        // UnsupportedOperationException
```

`view` không chặn mã khác giữ reference `source` sửa backing list. Nó chỉ ngăn thao tác thay đổi thông qua `view`.

**Bẫy:** gọi `Collections.unmodifiableList(source)` rồi trả `view` cho client **không đủ** để bảo vệ khỏi thay đổi từ mã vẫn giữ `source`. Nếu cần snapshot cấu trúc, dùng `List.copyOf(source)` (đồng thời xử lý vấn đề mutable elements).

### 4.4. Stream và collector không làm phần tử tự bất biến

```java
var snapshot = source.stream().toList();            // Java 16+: list không sửa được
var snapshot2 = source.stream()
        .collect(java.util.stream.Collectors.toUnmodifiableList()); // Java 10+
```

Hai cách tạo danh sách không sửa được nhưng thường vẫn lưu **reference** tới các object do stream phát ra. Nếu những object đó mutable, sửa object sau khi thu thập vẫn có thể làm kết quả hiển thị khác đi. `Stream.toList()` có thể chấp nhận phần tử `null`; `Collectors.toUnmodifiableList()` không chấp nhận `null`. Chọn phương thức đúng với hợp đồng dữ liệu và phiên bản Java của dự án.

## 5. Phân biệt hai nguồn thay đổi: alias phần tử và alias collection

Có hai kiểu alias (nhiều tham chiếu cùng trỏ một đối tượng) cần phân biệt.

### 5.1. Alias của phần tử

```java
var p = new Member("An");
var first = List.of(p);
var second = List.copyOf(first);

p.rename("Anh");
```

`p`, `first.get(0)` và `second.get(0)` đều trỏ đến **cùng một Member**. Không có list nào cần được sửa qua API của list; trạng thái quan sát được của cả hai vẫn đổi.

### 5.2. Alias của backing collection

```java
var original = new ArrayList<String>();
var view = Collections.unmodifiableList(original);

original.add("An"); // view thấy thêm "An"
```

Ở đây điều thay đổi là **backing list** được chia sẻ. Nếu `original` chứa `Member`, còn có thể xảy ra cả hai kiểu thay đổi: sửa list thông qua `original` và sửa từng `Member` qua bất kỳ alias nào.

**Kết luận:** một wrapper “chỉ đọc” không cắt bỏ các alias đang tồn tại. Hãy hỏi: *ai còn giữ tham chiếu đến list gốc? Ai còn giữ tham chiếu đến các phần tử?*

## 6. Hệ quả đối với kết quả đọc: `get`, `toString`, `contains` và phép so sánh

Với object mutable, không có bảo đảm rằng nội dung bạn nhìn thấy qua list hôm nay sẽ giống nội dung qua **cùng list** ở thời điểm khác.

### 6.1. Kết quả `get` và hiển thị có thể đổi

```java
var person = new Member("An");
var people = List.of(person);
var firstReference = people.get(0);

person.rename("Anh");
System.out.println(firstReference.name()); // "Anh" nếu name() trả field hiện tại
```

Biến `firstReference` không phải bản sao snapshot. Nó là reference tới object chung.

### 6.2. `contains`, `indexOf` và `equals`

Nếu class phần tử định nghĩa `equals` dựa trên field mutable, một phép tìm kiếm có thể trả kết quả khác sau khi field thay đổi:

```java
// Giả sử Member.equals so sánh thuộc tính name.
var person = new Member("An");
var people = List.of(person);

// people.contains(new Member("An")) có thể true nếu equals dựa trên name.
person.rename("Anh");
// people.contains(new Member("An")) có thể false.
```

Đây là **minh họa điều kiện**: kết quả thực tế phụ thuộc implementation `equals` của class `Member`, không phải hành vi mặc định của `Object.equals`. Trong chương trình chạy độc lập ở mục 12, `Member` **không override equals/hashCode**, nên không dùng ví dụ này để suy ra kết quả `contains` với một instance khác.

### 6.3. `hashCode` của collection cũng có thể thay đổi

`List.hashCode()` và `List.equals()` phụ thuộc vào các phần tử theo hợp đồng của list. Nếu `hashCode`/`equals` của phần tử dựa trên trạng thái mutable, thay đổi trạng thái có thể khiến kết quả `hashCode()` hoặc `equals(...)` của **chính collection không sửa được** thay đổi. Vì thế tránh coi unmodifiable list chứa mutable objects là một giá trị hoàn toàn cố định để dùng làm khóa map.

Không dựa vào giá trị hash cụ thể trong output: các kiểu triển khai khác nhau có thể có hash khác nhau theo hợp đồng của chính chúng.

## 7. Trường hợp nguy hiểm: phần tử hoặc khóa mutable trong `Set`/`Map`

Với `Set` và `Map`, tính nhất quán của quan hệ bằng nhau/hash càng quan trọng.

Giả sử class `Key` triển khai `equals` và `hashCode` dựa trên field `id` mutable:

```java
// Đoạn giả định Key có constructor, equals/hashCode theo id và setter.
var key = new Key("A");
var map = Map.of(key, "value");
key.setId("B");

// map.get(key) và map.containsKey(key) không còn được bảo đảm
// hoạt động theo kỳ vọng ban đầu nếu hashCode/equals của key đã đổi.
```

`Map.of` là map không thể thêm/xóa/thay mapping trực tiếp, nhưng nó **không đóng băng đối tượng `key`**. Làm thay đổi `equals/hashCode` của key sau khi đưa vào map/set có thể phá hỏng giả định tra cứu. Tránh khóa mutable theo các field được dùng làm khóa logic.

Với map có **giá trị mutable**:

```java
var member = new Member("An");
var owners = Map.of("leader", member);

member.rename("Anh");
// owners.get("leader").name() giờ có thể là "Anh", dù owners là unmodifiable map.
```

Không có `owners.put(...)` nào ở đây. Mapping từ khóa chuỗi `"leader"` đến reference `member` không đổi, nhưng **trạng thái object value** đã đổi.

Với `Set.of`, các phần tử không cho thêm/xóa, nhưng thay đổi field ảnh hưởng `equals/hashCode` của phần tử vẫn có thể gây hành vi không mong muốn khi tìm kiếm. Đừng tự kết luận kết quả `contains` cụ thể mà chưa kiểm tra class của phần tử và hợp đồng của implementation. `Set.of` cũng không chấp nhận phần tử `null`, không chấp nhận phần tử trùng khi tạo bằng factory, và không cam kết thứ tự duyệt như `List`.

## 8. “Sao chép” có nhiều mức: shallow copy và deep copy

Câu “đã copy list nên không thể thay đổi nội dung nữa” thường thiếu chính xác.

### 8.1. Sao chép reference của phần tử (shallow copy)

```java
var copyA = new ArrayList<>(source); // list mới, vẫn chứa reference cũ
var copyB = List.copyOf(source);     // list không sửa được, vẫn reference cũ
```

Nếu `source` chứa `Member` mutable, sửa một `Member` thông qua bất kỳ alias nào đều có thể hiện ra trong cả `copyA` và `copyB`. Khác nhau: `copyA` là list có thể chỉnh cấu trúc, `copyB` thì không.

### 8.2. Chuyển sang dữ liệu bất biến ở boundary

Nếu chỉ cần công khai tên, có thể tạo snapshot bằng `String`:

```java
List<String> nameSnapshot = source.stream()
        .map(Member::name)
        .toList(); // Java 16+, list unmodifiable gồm các String bất biến
```

Ở đây mỗi lời gọi `Member::name` trả về một `String` đại diện cho tên **tại thời điểm stream được xử lý**. Việc sau này đổi field tên trong `Member` sang một `String` khác **không sửa** giá trị chuỗi đã lưu trong `nameSnapshot`.

Tùy nghiệp vụ, nên chuyển object mutable thành một **DTO bất biến**:

```java
record MemberSnapshot(String id, String name) {
    MemberSnapshot {
        java.util.Objects.requireNonNull(id);
        java.util.Objects.requireNonNull(name);
    }
}
```

Nếu đầu vào chỉ gồm `String` bất biến, record trên không có setter và giữ được snapshot ổn định cho hai field đó. **Record không tự là bất biến sâu** nếu record chứa field kiểu `List<MutableItem>` hay mảng: cần phòng vệ từng thành phần.

### 8.3. Nếu phần tử chứa collection/mảng lồng nhau

```java
class Group {
    final List<String> tags;
    Group(List<String> tags) { this.tags = tags; }
}
```

`final` ngăn gán lại trường `tags` nhưng không ngăn mã khác sửa list `tags`. Dùng `List.of(new Group(mutableTags))` không giúp `tags` bất biến. Nếu muốn bảo vệ ở thời điểm khởi tạo:

```java
class GroupSnapshot {
    private final List<String> tags;
    GroupSnapshot(List<String> tags) {
        this.tags = List.copyOf(tags);
    }
    List<String> tags() { return tags; }
}
```

Vì `String` bất biến, danh sách trong `GroupSnapshot` là snapshot an toàn hơn. Nếu `tags` chứa object mutable, **còn cần copy/convert từng object** theo yêu cầu của hệ thống.

## 9. Thiết kế API: muốn chỉ đọc thì cần bảo vệ cả dữ liệu lẫn reference

Giả sử một đối tượng quản lý danh sách thành viên và đưa danh sách đó ra ngoài.

### Cách chưa đủ: chỉ bọc live view

```java
class Team {
    private final List<Member> members = new ArrayList<>();

    List<Member> members() {
        return Collections.unmodifiableList(members);
    }
}
```

Người nhận không gọi `add` trên view được, nhưng:

- `Team` vẫn có thể sửa `members` ở nơi khác; view phản ánh thay đổi.
- `members().get(0).rename(...)` có thể sửa `Member` nếu API cho phép.
- Một reference `Member` giữ từ trước có thể sửa phần tử mà không cần đi qua `Team`.

### Tốt hơn khi muốn snapshot cấu trúc

```java
List<Member> members() {
    return List.copyOf(members);
}
```

Cách này ngăn thay đổi **cấu trúc** từ danh sách gốc xuất hiện trong snapshot trả về, nhưng vẫn **chưa bảo vệ trạng thái các `Member`**.

### Khi cần snapshot dữ liệu công khai không đổi

```java
record MemberInfo(String name) {}

List<MemberInfo> membersSnapshot() {
    return members.stream()
            .map(m -> new MemberInfo(m.name()))
            .toList();
}
```

Đoạn minh họa giả sử `Member` có phương thức `name()` và `members` là danh sách nội bộ. Với `name` là `String`, caller nhận một list không sửa được gồm record không chứa mutable field. Việc `Member` nội bộ đổi tên sau đó không thay đổi snapshot được trả về.

**Bài toán không có một lời giải cho mọi trường hợp.** Nếu client cần cập nhật một object chung theo thời gian, một live view chứa mutable elements có thể được dùng có chủ đích, nhưng phải mô tả rõ hợp đồng: dữ liệu có thể thay đổi, thread-safety, vòng đời đối tượng và ai có quyền sửa. Nếu client cần giá trị ổn định (ví dụ lưu lịch sử, kiểm toán, cache snapshot), cần phòng vệ sâu hơn.

## 10. Không đồng nhất unmodifiable với thread-safe

Một list không cho sửa có thể được dùng trong nhiều luồng, nhưng **điều đó không tự làm các phần tử mutable trở nên thread-safe**.

```java
var person = new Member("An");
var people = List.of(person);

// Thread A: person.rename("Anh")
// Thread B: people.get(0).name()
```

Nếu các luồng cùng đọc/ghi trạng thái mutable mà không có cơ chế đồng bộ phù hợp, có thể phát sinh data race, quan sát không nhất quán hoặc vi phạm invariant của đối tượng. Việc list không cho gọi `add` không giải quyết được vấn đề bên trong `Member`.

Với `Collections.unmodifiableList(backing)`, còn phải chú ý việc **backing list vẫn được sửa bởi nơi khác**; duyệt và sửa đồng thời có thể dẫn tới lỗi hoặc kết quả không dự đoán được nếu thiếu phối hợp.

Khi cần chia sẻ giữa nhiều luồng:

1. Ưu tiên thiết kế các phần tử **thực sự bất biến** và xuất bản chúng an toàn.
2. Nếu trạng thái cần thay đổi, dùng đồng bộ hóa hoặc thiết kế concurrent phù hợp cho cả collection và phần tử.
3. Không sử dụng `List.of` hay `Collections.unmodifiableList` như một “khóa an toàn luồng” thay cho thiết kế concurrency.

Đừng suy diễn rằng có `final`, `record` hay unmodifiable wrapper thì mọi field lồng nhau sẽ tự động an toàn ở tất cả luồng.

## 11. Những giới hạn liên quan cần nắm để đọc API đúng

### 11.1. `final var` chỉ ngăn gán lại biến

```java
final var member = new Member("An");
final var people = List.of(member);

// people = List.of(new Member("Binh")); // Lỗi: final, không gán lại biến
member.rename("Anh");                  // Hợp lệ nếu Member cho phép
```

`final` điều khiển **tên biến**. `List.of` điều khiển **API sửa list**. Còn `Member` quyết định **trạng thái bên trong có sửa được không**.

### 11.2. Đừng dùng `List.copyOf` để “deep-clone”

```java
var list2 = List.copyOf(list1);
```

Hai danh sách có thể trỏ tới **cùng một object phần tử**. Trong những trường hợp input đã không sửa được, `copyOf` có thể tái sử dụng chính đối tượng list cũ. Bảo đảm quan trọng của API là snapshot cấu trúc, không phải mỗi phần tử có danh tính mới.

### 11.3. `null` và object mutable là hai vấn đề khác nhau

`List.of` và `List.copyOf` không cho phần tử `null`; `Collectors.toUnmodifiableList` cũng từ chối `null`. `Collections.unmodifiableList(source)` vẫn có thể hiển thị `null` nếu backing list chứa nó. Việc từ chối `null` **không chứng minh phần tử không thể sửa trạng thái**.

### 11.4. Loại phần tử ảnh hưởng mạnh đến kết quả

```java
var strings = List.of("A", "B");               // String bất biến
var builders = List.of(new StringBuilder("A")); // StringBuilder mutable
builders.get(0).append("B");                   // Hợp lệ, builder thành "AB"
```

Danh sách `builders` không thay đổi số phần tử, nhưng kết quả `builders.get(0).toString()` giờ là `"AB"`. Đây là ví dụ tối giản mà không cần khai báo class tùy chỉnh.

### 11.5. Thứ tự không được cam kết ở một số collection

`List.of` giữ thứ tự của các đối số; `Set.of` và `Map.of` không bảo đảm một thứ tự duyệt cụ thể để bạn dựa vào khi in `toString` hoặc kiểm thử. Khi viết test cho set/map, kiểm tra theo nội dung và khóa, không so sánh một chuỗi output phụ thuộc thứ tự ngẫu nhiên.

## 12. Chương trình Java 17+ độc lập: chứng minh hai loại thay đổi

Tạo tệp **`MutableElementsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class MutableElementsDemo {
    static final class Member {
        private String name;

        Member(String name) {
            this.name = Objects.requireNonNull(name);
        }

        String name() {
            return name;
        }

        void rename(String newName) {
            name = Objects.requireNonNull(newName);
        }

        @Override
        public String toString() {
            return name;
        }
    }

    record MemberView(String name) {
        MemberView {
            Objects.requireNonNull(name);
        }
    }

    public static void main(String[] args) {
        var an = new Member("An");
        var binh = new Member("Binh");

        var source = new ArrayList<Member>(List.of(an, binh));
        var view = Collections.unmodifiableList(source);
        var copy = List.copyOf(source);
        var literal = List.of(an, binh);

        System.out.println("initialSource=" + source);
        System.out.println("initialCopy=" + copy);

        an.rename("Anh");
        System.out.println("afterRenameView=" + view);
        System.out.println("afterRenameCopy=" + copy);
        System.out.println("afterRenameLiteral=" + literal);

        source.add(new Member("Chi"));
        System.out.println("sourceSize=" + source.size());
        System.out.println("viewSize=" + view.size());
        System.out.println("copySize=" + copy.size());
        System.out.println("literalSize=" + literal.size());

        copy.get(1).rename("Binh2");
        System.out.println("afterElementEditSource=" + source);
        System.out.println("afterElementEditCopy=" + copy);

        var nameSnapshot = copy.stream()
                .map(Member::name)
                .toList();
        System.out.println("nameSnapshot=" + nameSnapshot);

        an.rename("An2");
        System.out.println("afterSecondRenameCopy=" + copy);
        System.out.println("nameSnapshotAgain=" + nameSnapshot);

        var memberSnapshot = source.stream()
                .map(person -> new MemberView(person.name()))
                .toList();
        System.out.println("memberSnapshot=" + memberSnapshot);

        an.rename("An3");
        System.out.println("afterThirdRenameSource=" + source);
        System.out.println("memberSnapshotAgain=" + memberSnapshot);

        var owners = Map.of("leader", an);
        System.out.println("mapValue=" + owners.get("leader").name());

        try {
            copy.add(new Member("X"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("addBlocked=true");
        }

        try {
            view.set(0, new Member("Y"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("setBlocked=true");
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 MutableElementsDemo.java
java MutableElementsDemo
```

**Kết quả stdout chính xác:**

```text
initialSource=[An, Binh]
initialCopy=[An, Binh]
afterRenameView=[Anh, Binh]
afterRenameCopy=[Anh, Binh]
afterRenameLiteral=[Anh, Binh]
sourceSize=3
viewSize=3
copySize=2
literalSize=2
afterElementEditSource=[Anh, Binh2, Chi]
afterElementEditCopy=[Anh, Binh2]
nameSnapshot=[Anh, Binh2]
afterSecondRenameCopy=[An2, Binh2]
nameSnapshotAgain=[Anh, Binh2]
memberSnapshot=[MemberView[name=An2], MemberView[name=Binh2], MemberView[name=Chi]]
afterThirdRenameSource=[An3, Binh2, Chi]
memberSnapshotAgain=[MemberView[name=An2], MemberView[name=Binh2], MemberView[name=Chi]]
mapValue=An3
addBlocked=true
setBlocked=true
```

### Giải thích từng nhóm output

- `view`, `copy` và `literal` lúc đầu đều chứa reference đến các đối tượng `an`, `binh`. Khi `an.rename("Anh")`, cả ba cùng hiển thị tên mới.
- Khi `source.add(new Member("Chi"))`, `view.size()` thành 3 vì là live view. `copy` và `literal` vẫn giữ hai phần tử đã chọn khi tạo.
- `copy.get(1).rename("Binh2")` sửa `Member` thông qua reference lấy từ list không sửa được, nên `source` cũng thấy tên mới; **không có phép `copy.set(...)`**.
- `nameSnapshot` lưu các chuỗi bất biến tại thời điểm stream được thực thi; lần đổi `an` tiếp theo không làm thay các chuỗi này.
- `memberSnapshot` chứa các `MemberView` record với trường `String`, nên lần đổi `an` về sau không cập nhật record snapshot.
- `owners` là `Map.of` không cho sửa mapping, nhưng `owners.get("leader")` vẫn trỏ đến `an` với tên mới nhất.
- Hai đoạn `catch` chỉ xác nhận mutator bị chặn. Không phụ thuộc thông báo ngoại lệ hoặc thứ tự không được bảo đảm của `Set`/`Map`.

## 13. Lỗi thường gặp và cách sửa

### Lỗi A: “Danh sách không sửa được nên phần tử cũng không thể đổi”

```java
var item = new StringBuilder("A");
var data = List.of(item);
item.append("B"); // Hợp lệ; data.get(0).toString() trả "AB"
```

**Sửa cách hiểu:** phân biệt sửa **reference phần tử** với sửa **trạng thái bên trong phần tử**. Muốn dữ liệu ổn định, dùng kiểu phần tử bất biến hoặc tạo snapshot dữ liệu.

### Lỗi B: “Bọc `unmodifiableList` là đã copy độc lập”

```java
var source = new ArrayList<String>();
var view = Collections.unmodifiableList(source);
source.add("An");
System.out.println(view); // [An]
```

**Sửa:** dùng `List.copyOf(source)` nếu cần snapshot các phần tử (và source không chứa `null`), sau đó xét tiếp tính mutable của từng phần tử.

### Lỗi C: “`List.copyOf` là deep copy”

```java
var person = new Member("An");
var snapshot = List.copyOf(List.of(person));
person.rename("Anh");
// snapshot.get(0).name() là "Anh"
```

**Sửa:** chuyển đổi mỗi phần tử thành dạng bất biến, ví dụ `new MemberView(person.name())`, thay vì chỉ copy collection.

### Lỗi D: “Có `final` thì cả object graph bất biến”

```java
final var list = List.of(new StringBuilder("A"));
list.get(0).append("B"); // Hợp lệ
```

**Sửa:** kiểm tra field và đối tượng lồng nhau, không suy luận tính bất biến sâu từ từ khóa `final`.

### Lỗi E: Dùng mutable object làm key của map/set

Nếu `equals/hashCode` dựa trên field mutable, thay đổi field sau khi thêm phần tử có thể làm các phép tra cứu không còn đúng kỳ vọng. **Sửa:** dùng key bất biến (ví dụ `String` hoặc record chứa chỉ thành phần bất biến) hoặc thiết kế riêng một ID ổn định, không thay đổi sau khi đưa vào map/set.

### Lỗi F: Cho rằng không sửa collection nên tự động thread-safe

Một thread sửa `Member`, thread khác đọc `List.of(member)` vẫn có thể có data race. **Sửa:** dùng immutable snapshot và safe publication hoặc cơ chế đồng bộ phù hợp.

### Lỗi G: Bỏ qua khác biệt `null`

`List.copyOf(source)` ném `NullPointerException` nếu nguồn có phần tử `null`. `Collections.unmodifiableList(source)` không tự lọc hoặc cấm một phần tử `null` mà backing list đã chứa. **Sửa:** xác định hợp đồng dữ liệu null trước khi chọn API; không loại dữ liệu ngoài ý muốn.

## 14. Checklist thiết kế và code review

Trước khi trả về hoặc chia sẻ một collection “chỉ đọc”, hãy trả lời:

1. **Caller có được thêm, xóa hoặc thay phần tử không?** Nếu không, chọn unmodifiable API.
2. **Caller có nên thấy thay đổi cấu trúc trong nguồn sau đó không?** Nếu không, tránh live view trên backing list mutable; dùng snapshot như `List.copyOf`.
3. **Phần tử chứa loại dữ liệu nào?** `String` bất biến, `StringBuilder` mutable; entity/bean/array/nested collection có thể tiếp tục thay đổi.
4. **Ai còn giữ alias đến phần tử?** Copy list thông thường chỉ copy reference. Nếu một service khác vẫn giữ object, nó có thể thay state.
5. **Phần tử có dùng làm key/hash element không?** Nếu có, `equals/hashCode` phải dựa trên trạng thái ổn định cho thời gian phần tử nằm trong map/set.
6. **Dữ liệu cần live update hay snapshot?** Hãy đặt tên API và tài liệu rõ như `membersView()` hoặc `membersSnapshot()`.
7. **Có cần immutable snapshot sâu không?** Chuyển sang DTO/record chứa immutable fields và copy các collection lồng nhau khi cần.
8. **Có luồng đồng thời truy cập không?** Đừng nhầm unmodifiable với cơ chế đồng bộ.
9. **Có phần tử `null` không?** Kiểm tra hợp đồng của `List.of`, `List.copyOf` hoặc phương thức khác trước khi đổi API.
10. **Các test có kiểm cả hai loại thay đổi không?** Test sửa backing collection, sửa object phần tử, gọi mutator bị cấm, đọc lại snapshot và các ca cạnh tranh nếu có.

## 15. Bài tập và đáp án

**Câu 1.** `var s = new StringBuilder("A"); var list = List.of(s); s.append("B");`. `list.get(0).toString()` trả về gì? Có gọi `list.add(...)` được không?

**Câu 2.** `var source = new ArrayList<String>(List.of("A")); var view = Collections.unmodifiableList(source); var copy = List.copyOf(source); source.add("B");`. `view` và `copy` lần lượt có bao nhiêu phần tử?

**Câu 3.** Khi một `Member` có setter `rename` được dùng đồng thời trong `List.of(member)` và `List.copyOf(List.of(member))`, setter đó có bị cấm không?

**Câu 4.** Nếu cần trả về dữ liệu người dùng ổn định tại một thời điểm, tại sao `List.copyOf(userEntities)` có thể chưa đủ?

**Câu 5.** `final var names = List.of(new StringBuilder("A"));` có ngăn `names.get(0).append("B")` không?

**Câu 6.** Vì sao việc dùng key có `equals/hashCode` phụ thuộc vào field mutable trong `Map.of` hoặc `Set.of` không được khuyến nghị?

**Câu 7.** `Stream.toList()` và `Collectors.toUnmodifiableList()` có tự deep-copy phần tử mutable không? Điểm khác biệt đáng chú ý với `null`?

**Câu 8.** Nếu một đối tượng có field `List<String> tags` được khai báo `final`, điều đó có đủ để bảo đảm tags không bao giờ đổi không?

**Câu 9.** Khi nào lựa chọn một **live unmodifiable view** là đúng thay vì snapshot?

**Đáp án:**

1. `"AB"`; không thể `add` vì `List.of` trả list không sửa được.
2. `view.size() == 2`, còn `copy.size() == 1`. `view` phản ánh backing list; `copy` cố định tập phần tử ban đầu.
3. Không. Cả hai list chặn sửa cấu trúc nhưng vẫn chứa reference tới `Member` mutable.
4. `List.copyOf` không clone sâu entity; các alias còn lại vẫn sửa field của entity được. Cần projection/copy các giá trị cần giữ.
5. Không. `final` chỉ cấm gán lại biến; `StringBuilder` vẫn mutable.
6. Vì thay đổi khóa có thể làm sai các giả định tra cứu và tính nhất quán của `equals/hashCode`.
7. Không deep-copy phần tử. `Stream.toList()` cho phép `null` trong stream; `Collectors.toUnmodifiableList()` không cho `null`.
8. Không. `final` ngăn đổi reference field `tags`, không ngăn các thao tác thay đổi object list. Có thể cần `List.copyOf(tags)` trong constructor.
9. Khi chủ đích của API là cho client **xem danh sách cập nhật từ nguồn**, nhưng không cấp quyền sửa danh sách qua reference trả về; phải ghi rõ việc dữ liệu live và quy tắc concurrency.

## 16. Tóm tắt và tài liệu hiện hành

- **Unmodifiable** chỉ chặn thay đổi collection thông qua API; **không tự đóng băng trạng thái của các phần tử mutable**.
- **`List.of`** giữ những reference được đưa vào lúc tạo; **`List.copyOf`** chụp tập phần tử tại thời điểm sao chép nhưng là shallow copy.
- **`Collections.unmodifiableList`** tạo live view: sửa backing collection từ reference khác sẽ được phản ánh.
- `final`, `record` và unmodifiable wrapper không tự tạo **deep immutability**.
- Khi cần dữ liệu ổn định, hãy copy/projection thành giá trị bất biến và quản lý alias, mutability, null, hash key và concurrency.
- Nên đặt tên API theo sự khác biệt giữa **view live** và **snapshot**.

Các nguồn Java chính thức vẫn còn áp dụng:

1. [Java SE 26 API — List: Unmodifiable Lists, `List.of`, `List.copyOf`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html): quy tắc cấm mutator, `null`, snapshot và phần tử mutable.
2. [Java SE 26 Developer Guide — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/26/core/creating-immutable-lists-sets-and-maps.html): giải thích cụ thể alias, shallow immutability, snapshot, unmodifiable view và mutable elements.
3. [Java SE 26 API — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): wrapper view phản ánh những thay đổi của backing list.
4. [Java SE 26 API — Stream.toList](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList()): list không sửa được trả về từ stream, có từ Java 16.
5. [Java SE 26 API — Collectors.toUnmodifiableList](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): collector không sửa được, có từ Java 10.
