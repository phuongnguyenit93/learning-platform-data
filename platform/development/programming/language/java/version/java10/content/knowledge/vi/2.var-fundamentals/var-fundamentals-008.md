# Java 10 – Phân biệt biến không thể gán lại với đối tượng bất biến

> **Chủ đề:** Java 10 → Nền tảng `var` → Phân biệt biến không thể gán lại với đối tượng bất biến. Bài học dùng kiến thức còn hiệu lực trong Java hiện đại; các ví dụ hoàn chỉnh chạy với Java 17 trở lên. `var` và `List.copyOf` xuất hiện từ Java 10; `final`, `String` và các nguyên lý bất biến đã tồn tại từ trước; `record` (Java 16) được dùng như một ví dụ hiện đại để làm rõ khái niệm.

## 1. Mục tiêu

Sau bài học, bạn có thể:

1. Giải thích riêng ba khái niệm: **suy luận kiểu** (`var`), **không thể gán lại biến** (`final`) và **trạng thái đối tượng không thay đổi** (immutability).
2. Phân biệt **gán lại tham chiếu** (`reference reassignment`) với **sửa đối tượng đang được tham chiếu** (`object mutation`).
3. Nhận diện mức độ đảm bảo của `String`, array, `List.of`, `List.copyOf` và `Collections.unmodifiableList`.
4. Thiết kế lớp chứa dữ liệu theo hướng bất biến bằng cách bảo vệ đầu vào/đầu ra và ngăn sửa trạng thái thông qua alias.
5. Hiểu tác động với `final var`, lambda, `record`, lập trình đồng thời và API nghiệp vụ.

## 2. Ba khái niệm độc lập: `var`, `final` và immutable

| Khái niệm | Áp dụng cho | Đảm bảo thực sự | Không đảm bảo |
| --- | --- | --- | --- |
| `var` | Khai báo biến cục bộ Java 10+ có initializer | Trình biên dịch **suy ra kiểu tĩnh** từ biểu thức gán ban đầu | Không khóa biến, không biến đối tượng thành immutable |
| `final` trên biến | Biến cục bộ, tham số, field | Sau khi biến đã được gán hợp lệ, không thể **gán giá trị/tham chiếu khác** cho chính biến đó | Không chặn sửa đối tượng mà tham chiếu đang trỏ đến |
| Immutable object | Thiết kế và hợp đồng của **đối tượng** | Trạng thái quan sát được không thay đổi sau khi tạo | Không tự động phát sinh chỉ từ `final` ở một field |
| Unmodifiable collection | API của collection | Không thể thay đổi cấu trúc collection thông qua API collection đó | Không nhất thiết là deep immutable, không nhất thiết tách khỏi nguồn |

Ví dụ ngắn:

~~~java
var n = 10;             // suy luận int; vẫn có thể gán n = 20
final var limit = 10;   // suy luận int và không được gán lại

var text = "A";         // String là immutable, nhưng biến text có thể gán tham chiếu khác
text = "B";             // hợp lệ

final var names = new java.util.ArrayList<String>();
names.add("An");       // hợp lệ: thay đổi nội dung đối tượng
// names = new java.util.ArrayList<>(); // KHÔNG hợp lệ: gán lại biến final
~~~

**Ý cốt lõi:** Tính chất của **biến** và tính chất của **đối tượng** là hai trục độc lập. Một biến có thể bị khóa gán lại trong khi đối tượng bên trong vẫn sửa được; một biến có thể gán lại dù nó đang trỏ đến một đối tượng bất biến.

## 3. Tham chiếu là gì và chuyện gì xảy ra khi gán lại?

Với object trong Java, một biến kiểu tham chiếu giữ **giá trị tham chiếu** tới đối tượng, không phải toàn bộ đối tượng. Lệnh gán biến và lệnh gọi phương thức chỉnh sửa có tác động khác nhau:

~~~java
var labels = new java.util.ArrayList<>(java.util.List.of("A"));
var alias = labels;                // cả hai biến cùng trỏ một danh sách

labels.add("B");                   // sửa cùng đối tượng
System.out.println(alias);       // [A, B]

labels = new java.util.ArrayList<>(); // chỉ labels trỏ đối tượng khác
System.out.println(alias);       // [A, B]
System.out.println(labels);      // []
~~~

Sơ đồ tư duy:

~~~text
Ban đầu:
labels ─┐
        ├──> ArrayList #1 ["A"]
alias  ─┘

Sau labels.add("B"):
labels ─┐
        ├──> ArrayList #1 ["A", "B"]
alias  ─┘

Sau labels = new ArrayList<>():
labels ───> ArrayList #2 []
alias  ───> ArrayList #1 ["A", "B"]
~~~

Chọn `final var labels = ...` sẽ cấm bước **gán lại** ở cuối, nhưng vẫn cho phép `labels.add("B")` nếu đối tượng là danh sách có thể chỉnh sửa.

Với **kiểu nguyên thủy** như `int`, biến giữ chính giá trị kiểu nguyên thủy, không trỏ tới object. `final int count = 2;` không thể bị gán `count = 3;`; không có “nội dung bên trong object” để sửa qua biến này.

### 3.1. `var` là suy luận kiểu tĩnh, không phải dynamic typing

~~~java
var count = 10;            // int
count = 11;               // hợp lệ
// count = "eleven";       // KHÔNG biên dịch: String không gán cho int

var values = java.util.List.of("x"); // kiểu suy ra: List<String>
values = new java.util.ArrayList<>(values); // hợp lệ: đều là List<String>
values.add("y");            // hợp lệ sau khi biến trỏ đến ArrayList
~~~

Tại dòng `values = new ArrayList<>(values)`, **kiểu khai báo của biến không đổi**; chỉ đối tượng được tham chiếu thay đổi. Ban đầu `List.of` trả về danh sách không cho sửa, sau đó biến được gán danh sách có thể sửa. Vì vậy không thể xác định tính bất biến của đối tượng chỉ bằng cách nhìn thấy từ khóa `var`.

### 3.2. `final var` kết hợp hai quy tắc khác nhau

`final var items = new ArrayList<String>();` vừa cho trình biên dịch suy luận kiểu `ArrayList<String>`, vừa cấm gán lại `items`. Phần tử của `items` vẫn thêm/bớt được.

`final` không làm `var` suy luận sang interface như `List<String>`; kiểu suy ra vẫn dựa trên biểu thức khởi tạo. Khi muốn cam kết rằng code chỉ phụ thuộc giao diện `List`, hãy dùng `final List<String> items = new ArrayList<>();`. Dùng kiểu tường minh khi nó làm hợp đồng API dễ hiểu hơn.

`var` chỉ được dùng cho một số khai báo **biến cục bộ** có biểu thức khởi tạo (bao gồm biến vòng lặp và tài nguyên `try-with-resources`). Không dùng `var` như kiểu field, kiểu trả về phương thức hay kiểu tham số phương thức thông thường. Các cách viết `var x;` và `var x = null;` không hợp lệ vì thiếu kiểu có thể suy ra. Đây vẫn là các giới hạn cần nhớ trên Java hiện đại.

## 4. `final` khóa gán lại biến, không khóa trạng thái object

### 4.1. Trường hợp object có thể chỉnh sửa

~~~java
final var queue = new java.util.ArrayList<>(java.util.List.of("A"));
queue.add("B");          // OK: gọi phương thức sửa nội dung ArrayList
queue.set(0, "X");       // OK: thay phần tử
System.out.println(queue); // [X, B]

// queue = new java.util.ArrayList<>(); // lỗi biên dịch: queue là final
~~~

Một biến `final` là tham chiếu ổn định, không phải “đóng băng” đối tượng. Điều này cũng đúng với field:

~~~java
class Counter {
    private final java.util.List<Integer> history = new java.util.ArrayList<>();

    void add(int value) {
        history.add(value);  // hợp lệ: field final vẫn trỏ cùng List, List đổi nội dung
    }
}
~~~

Không có setter cho field và khai báo `final` vẫn chưa đủ để kết luận instance `Counter` immutable: gọi `add` làm trạng thái quan sát được thay đổi.

### 4.2. Trường hợp object bất biến nhưng biến gán lại được

~~~java
var label = "Java"; // String là immutable
label = label.concat(" 10");
System.out.println(label); // Java 10
~~~

`concat` không sửa đối tượng `String` cũ; nó trả về một `String` đại diện cho kết quả. Lệnh `label = ...` cập nhật tham chiếu của biến. Nếu khai báo `final var label = "Java";`, vẫn có thể gọi `label.concat(" 10")`, nhưng không thể gán kết quả trở lại `label`; muốn giữ kết quả cần biến mới.

Các kiểu giá trị quen thuộc có thiết kế immutable gồm `String`, `Integer`, `BigInteger`, `LocalDate`, `Instant`. Đây là ví dụ của immutability **theo hợp đồng class**, độc lập với biến tham chiếu có được đánh dấu `final` hay không.

### 4.3. `final` với array

~~~java
final int[] digits = {1, 2};
digits[0] = 9;                            // OK
System.out.println(java.util.Arrays.toString(digits)); // [9, 2]

// digits = new int[] {3, 4};            // KHÔNG biên dịch
~~~

Array Java là đối tượng có thể sửa theo index, dù biến tham chiếu được khai báo `final`. Nếu lưu array bên trong lớp bất biến, phải sao chép lúc nhận và lúc trả ra (xem mục 7).

### 4.4. Phạm vi đảm bảo của `final`

- **Biến cục bộ:** Không gán lại sau khi đã được khởi tạo theo quy tắc của trình biên dịch. Biến `final` khai báo không có initializer vẫn có thể được gán **đúng một lần trên mỗi luồng điều khiển hợp lệ** trước khi dùng; riêng `final var` cần initializer để suy ra kiểu.
- **Tham số phương thức:** `final` cấm gán lại tham số trong body, nhưng không cấm sửa object được truyền vào. Cơ chế truyền tham số Java vẫn là **pass-by-value**, tức giá trị tham chiếu được sao chép vào biến tham số.
- **Field:** `final` buộc field được gán trong quá trình khởi tạo đối tượng theo quy tắc ngôn ngữ. Nếu field chứa object mutable, trạng thái object đó vẫn có thể đổi.
- **Class/method `final`:** Từ khóa này còn có nghĩa “không được kế thừa” cho class hoặc “không được override” cho method; đó là một quy tắc khác, không có nghĩa mọi object của class trở nên immutable.

## 5. Unmodifiable collection, immutable collection và defensive copy

Đây là nguồn gây nhầm lẫn phổ biến nhất khi kết hợp `final var` với List/Set/Map.

### 5.1. Collection có thể chỉnh sửa

~~~java
final var items = new java.util.ArrayList<>(java.util.List.of("A"));
items.add("B");
items.remove("A");
System.out.println(items); // [B]
~~~

Biến `items` không thể gán lại, nhưng collection vẫn có các thao tác sửa.

### 5.2. `List.of` – danh sách không cho sửa cấu trúc

~~~java
var items = java.util.List.of("A", "B");
// items.add("C");  // ném UnsupportedOperationException khi chạy
items = java.util.List.of("C"); // hợp lệ: biến không final
~~~

`List.of` có từ Java 9, nhưng API này vẫn rất hữu ích trên Java hiện đại. Nó tạo danh sách không cho thêm, bớt, thay phần tử; nó không cho phép phần tử `null`. Bản thân `items` vẫn là biến có thể **gán lại** nếu không có `final`. Đừng nhầm `UnsupportedOperationException` khi sửa nội dung với lỗi **biên dịch** khi gán lại biến `final`.

### 5.3. `Collections.unmodifiableList` là read-only view, không bảo đảm snapshot

~~~java
var source = new java.util.ArrayList<>(java.util.List.of("A"));
var view = java.util.Collections.unmodifiableList(source);
source.add("B");

System.out.println(view); // [A, B]
~~~

Không thể gọi `view.add(...)` thành công, nhưng ai giữ tham chiếu `source` vẫn sửa được danh sách gốc và thay đổi **hiện ra trong view**. “Không thể sửa qua view” không có nghĩa “nội dung giữ nguyên mãi”.

### 5.4. `List.copyOf` – bản sao cấu trúc không cho sửa (Java 10)

~~~java
var source = new java.util.ArrayList<>(java.util.List.of("A"));
var snapshot = java.util.List.copyOf(source);
source.add("B");

System.out.println(source);   // [A, B]
System.out.println(snapshot); // [A]
~~~

`List.copyOf` hữu ích để chặn thay đổi **cấu trúc** của một source collection mutable ảnh hưởng đến danh sách được công bố. Java 10 cũng có `Set.copyOf` và `Map.copyOf`; bộ ba vẫn là API phổ biến trong Java hiện đại.

Lưu ý chính xác:

- Các `copyOf` trả collection không cho chỉnh sửa qua API thông thường, đồng thời từ chối `null` trong source/giá trị chứa. Chúng **không deep-copy** object phần tử.
- Nếu đầu vào vốn là một collection không thể sửa phù hợp, implementation có thể tái sử dụng đối tượng, vì vậy đừng phụ thuộc vào identity mới như `snapshot != source`.
- `Set.copyOf` không bảo đảm thứ tự duyệt và có thể gộp phần tử trùng nhau; `Map.copyOf` không bảo đảm thứ tự duyệt. Chỉ phụ thuộc vào thứ tự khi API công khai cam kết điều đó.
- Nếu gọi `List.copyOf(source)` rồi cố sửa `snapshot` bằng `add`/`set`/`remove`, thao tác ném `UnsupportedOperationException`.
- Với collection chứa **phần tử mutable**, snapshot cấu trúc vẫn không có nghĩa trạng thái toàn bộ đồ thị object đã bất biến.

### 5.5. Vẫn có thể sửa object bên trong List không cho sửa

~~~java
final class UserProfile {
    private String name;
    UserProfile(String name) { this.name = name; }
    void rename(String newName) { name = newName; }
    @Override public String toString() { return name; }
}

var profile = new UserProfile("An");
var users = java.util.List.of(profile);
profile.rename("Binh");

System.out.println(users); // [Binh]
~~~

`users.add(...)` không cho phép, nhưng `profile.rename(...)` vẫn làm thay đổi trạng thái phần tử đã có. Tương tự với `List.copyOf`: nó giữ các **tham chiếu phần tử**, không tạo bản sao sâu của từng đối tượng.

Nếu cần dữ liệu bất biến thực sự, ưu tiên danh sách phần tử vốn immutable (như `String` hay record được thiết kế đúng), hoặc tạo bản sao immutable của từng phần tử trước khi chốt danh sách. Cần phân biệt rõ “bất biến cấu trúc collection” và “bất biến sâu của dữ liệu”.

### 5.6. Bảng chọn API theo nhu cầu

| Cách khai báo | Có gán lại biến được? | Sửa collection qua biến? | Thay đổi của source có hiện ra? |
| --- | --- | --- | --- |
| `var xs = new ArrayList<String>()` | Có | Có | Cùng collection nếu các biến là alias |
| `final var xs = new ArrayList<String>()` | Không | Có | Có nếu sửa qua alias |
| `var xs = List.of("A")` | Có | Không | Không có mutable source truyền vào |
| `final var xs = List.copyOf(source)` | Không | Không | Không với các thay đổi cấu trúc sau khi copy từ source mutable |
| `final var xs = Collections.unmodifiableList(source)` | Không | Không qua view | **Có**, nếu source bị sửa |

Cột cuối nói về **cấu trúc và vị trí phần tử**, không khẳng định từng object phần tử bất biến sâu.

## 6. Thế nào là một đối tượng bất biến đúng nghĩa?

Ở góc nhìn thiết kế API, object được xem là immutable nếu trạng thái quan sát được của chính object đó **không đổi sau khi tạo thành công**. Thực thi chi tiết có thể phức tạp, nhưng nên giữ các bất biến sau:

1. Thiết lập trạng thái đầy đủ ngay khi khởi tạo.
2. Không cung cấp phương thức thay đổi trạng thái hiện có.
3. Không công bố trực tiếp tham chiếu nội bộ có thể sửa; getter không được cho caller sửa state bên trong.
4. Sao chép dữ liệu mutable nhận từ bên ngoài nếu nó cần được lưu giữ, và sao chép dữ liệu mutable khi trả ra nếu cần.
5. Với field là collection, xem xét **tính mutable của từng phần tử**; `List.copyOf` chưa phải deep copy.
6. Bảo vệ invariant như kiểm tra `null`, giá trị hợp lệ và quy ước không đổi. Không để tham chiếu `this` thoát khỏi constructor khi trạng thái chưa hoàn chỉnh.
7. Ưu tiên field `private final` và lớp không bị mở rộng tùy ý khi cách kế thừa có thể làm mất hợp đồng immutable.

### 6.1. Ví dụ lớp bất biến với dữ liệu phần tử immutable

~~~java
import java.util.List;
import java.util.Objects;

public final class ProductSnapshot {
    private final String id;
    private final List<String> tags;

    public ProductSnapshot(String id, List<String> tags) {
        this.id = Objects.requireNonNull(id);
        this.tags = List.copyOf(Objects.requireNonNull(tags));
    }

    public String id() { return id; }
    public List<String> tags() { return tags; }
}
~~~

Giải thích:

- `String` vốn immutable; không có setter cho `id`.
- `tags` được chốt bằng `List.copyOf` để caller không sửa cấu trúc qua danh sách đã đưa vào constructor. Danh sách trả ra từ getter không cho chỉnh sửa.
- Do phần tử có kiểu `String` là immutable, không tồn tại nguy cơ caller gọi phương thức làm thay đổi nội dung từng phần tử.
- Nếu chuyển `List<String>` thành `List<MutableItem>`, mẫu này **chưa đủ**: cần tạo snapshot của từng `MutableItem` thành kiểu dữ liệu immutable thích hợp.

### 6.2. Với array, phải copy cả lúc nhận và lúc trả

~~~java
public final class Packet {
    private final byte[] payload;

    public Packet(byte[] input) {
        this.payload = input.clone(); // ngắt alias với array của caller
    }

    public byte[] payload() {
        return payload.clone(); // caller không sửa được array nội bộ qua getter
    }
}
~~~

Nếu constructor viết `this.payload = input;`, caller có thể sửa `input[0]` sau khi tạo `Packet`. Nếu getter trả trực tiếp `payload`, caller có thể làm `packet.payload()[0] = 9;`. `final` trên field chỉ khóa **tham chiếu array**, không khóa từng ô. Bản sao `clone()` trên array nguyên thủy sao chép nội dung byte, phù hợp ở đây.

### 6.3. `record` không tự động tạo deep immutability

Java 16 đưa `record` vào ngôn ngữ. Một record mang field thành phần không thể gán lại, nhưng tham chiếu đến collection mutable vẫn có thể dẫn tới object mutable:

~~~java
record UnsafeTeam(java.util.List<String> members) {}

var input = new java.util.ArrayList<>(java.util.List.of("An"));
var team = new UnsafeTeam(input);
input.add("Binh");
System.out.println(team.members()); // [An, Binh]
~~~

Một thiết kế tốt hơn:

~~~java
record SafeTeam(java.util.List<String> members) {
    SafeTeam {
        members = java.util.List.copyOf(members);
    }
}
~~~

Trong compact canonical constructor của record, tham số `members` được thay bằng bản sao không cho sửa trước khi Java khởi tạo field thành phần. Với `List<String>`, đây là cấu trúc dữ liệu phù hợp để chia sẻ; với object phần tử mutable, vẫn phải sao chép hoặc thiết kế immutable cho phần tử. `record` là ví dụ hữu ích trên JDK hiện đại, **không phải tính năng mới của riêng Java 10**.

## 7. Ví dụ Java 17+ hoàn chỉnh, có thể biên dịch và chạy

Lưu mã sau thành tệp **`FinalVsImmutable.java`**. Chương trình minh họa mười tình huống: `final var` vẫn cho sửa object, `var` có thể gán lại, `String` immutable, view so với snapshot, mutable element, defensive copy, record, array và lambda.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class FinalVsImmutable {
    static final class MutableItem {
        private String name;
        MutableItem(String name) { this.name = name; }
        void rename(String newName) { this.name = newName; }
        @Override public String toString() { return name; }
    }

    static final class Catalog {
        private final List<String> names;
        Catalog(List<String> names) {
            this.names = List.copyOf(Objects.requireNonNull(names));
        }
        List<String> names() { return names; }
    }

    record SafeConfig(List<String> flags) {
        SafeConfig { flags = List.copyOf(flags); }
    }

    public static void main(String[] args) {
        final var fixed = new ArrayList<>(List.of("A"));
        fixed.add("B");
        System.out.println("final-var list: " + fixed);

        var replaceable = List.of("A");
        replaceable = new ArrayList<>(replaceable);
        replaceable.add("B");
        System.out.println("var reassigned: " + replaceable);

        final var text = "Java";
        var newText = text.concat(" 10");
        System.out.println("string old/new: " + text + " / " + newText);

        var source = new ArrayList<>(List.of("core"));
        var view = Collections.unmodifiableList(source);
        var snapshot = List.copyOf(source);
        source.add("api");
        System.out.println("view: " + view);
        System.out.println("copy: " + snapshot);

        var item = new MutableItem("draft");
        var shallow = List.of(item);
        item.rename("changed");
        System.out.println("shallow: " + shallow);

        var names = new ArrayList<>(List.of("stable"));
        var catalog = new Catalog(names);
        names.add("later");
        System.out.println("safe catalog: " + catalog.names());

        var flags = new ArrayList<>(List.of("fast"));
        var config = new SafeConfig(flags);
        flags.add("slow");
        System.out.println("record: " + config.flags());

        final int[] digits = {1, 2};
        digits[0] = 9;
        System.out.println("array: " + Arrays.toString(digits));

        var state = new ArrayList<>(List.of("one"));
        Runnable action = () -> System.out.println("lambda sees: " + state.size());
        state.add("two");
        action.run();
    }
}
~~~

Tại thư mục chứa tệp:

~~~bash
javac --release 17 FinalVsImmutable.java
java FinalVsImmutable
~~~

Output chính xác (đã đối chiếu với mã biên dịch và chạy trên JDK hiện đại):

~~~text
final-var list: [A, B]
var reassigned: [A, B]
string old/new: Java / Java 10
view: [core, api]
copy: [core]
shallow: [changed]
safe catalog: [stable]
record: [fast]
array: [9, 2]
lambda sees: 2
~~~

Diễn giải:

- `fixed` là `final` nên không thể trỏ tới list mới, nhưng `fixed.add("B")` vẫn thực hiện được.
- `replaceable` không final và được suy luận là `List<String>`, nên có thể đổi từ `List.of` sang `ArrayList` và sau đó sửa nội dung.
- `text.concat` tạo kết quả mới, không sửa `String` cũ.
- `view` phản ánh khi `source` thay đổi, còn `snapshot` được chốt bằng `List.copyOf`.
- `shallow` không thể thêm phần tử, nhưng `item.rename` thay đổi state của phần tử.
- `Catalog` và `SafeConfig` tự chốt `List<String>` đầu vào nên sửa list của caller về sau không ảnh hưởng kết quả.
- `digits` là array có thể sửa, dù biến tham chiếu `final`.
- `state` được lambda capture và không gán lại nhưng các phần tử vẫn có thể thêm; lambda thấy kích thước hiện tại của cùng danh sách.

## 8. “Effectively final” trong lambda không có nghĩa immutable

Java yêu cầu một biến cục bộ được lambda capture phải là `final` hoặc **effectively final** (không bị gán lại sau khi khởi tạo, dù không ghi từ khóa `final`). Quy tắc này liên quan đến tính ổn định của **biến cục bộ được capture**, không tự đóng băng object.

~~~java
var messages = new java.util.ArrayList<String>();
Runnable report = () -> System.out.println(messages.size());
messages.add("ok");
report.run(); // 1
~~~

`messages` effectively final vì không có phép gán lại `messages = ...`; nó vẫn trỏ đến `ArrayList` cho phép `add`. Nếu thêm `messages = new ArrayList<>();` cùng phạm vi, việc capture sẽ **không biên dịch** vì biến không còn effectively final.

Không dùng thủ thuật object mutable trong lambda chỉ để “vượt” ràng buộc capture; nếu nghiệp vụ cần tích lũy giá trị, cân nhắc return value, stream reduction, collector hoặc thiết kế state riêng có kiểm soát. Trong luồng đồng thời, việc capture một tham chiếu không tự đảm bảo truy cập thread-safe.

## 9. Bất biến và thread safety: liên hệ nhưng không đồng nghĩa

Dữ liệu immutable giúp tránh tình huống nhiều thread thay đổi cùng trạng thái đã chia sẻ. Tuy nhiên:

- `final` trên tham chiếu **không** khiến đối tượng mutable trở nên thread-safe. `final var list = new ArrayList<String>();` vẫn là ArrayList không đồng bộ cho các thao tác chỉnh sửa đồng thời.
- `Collections.unmodifiableList(mutableSource)` không tạo snapshot; nếu một thread sửa nguồn, thread khác đọc view có thể cần cơ chế đồng bộ.
- Một object bất biến được **khởi tạo đúng và công bố an toàn** thuận lợi cho việc chia sẻ giữa thread. Final-field semantics của Java hỗ trợ một số đảm bảo khởi tạo, nhưng không thay thế các quy tắc safe publication, kiểm soát alias và đồng bộ đối với dữ liệu mutable.
- Bất biến sâu của object chứa object khác chỉ đạt được khi **các thành phần quan sát được cũng bất biến** hoặc được sao chép/phòng vệ đúng.
- Mutable state không phải lúc nào cũng xấu: đối tượng phục vụ xử lý cục bộ trong một thread có thể dùng `ArrayList` rất hợp lý; nên tạo immutable snapshot khi đưa kết quả qua ranh giới API hay chia sẻ giữa module/thread.

Trong dự án thực tế, chọn immutable DTO/snapshot cho cấu hình, thông tin trả về và dữ liệu chia sẻ; dùng mutable builder/buffer trong giai đoạn xây dựng. Đừng mặc định `final` đủ để giải quyết race condition.

## 10. Những lỗi tư duy cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`var` nghĩa là kiểu biến thay đổi khi chạy” | Kiểu được suy luận **một lần ở compile time**; các phép gán sau vẫn phải tương thích kiểu |
| “`final List` không thêm phần tử được” | Chỉ biến tham chiếu không thể gán lại; `ArrayList.add` vẫn hoạt động |
| “`final String` mới là String bất biến” | `String` immutable do thiết kế class, kể cả biến thường; `final` khóa gán lại biến |
| “`List.of` nghĩa là biến không gán lại được” | `List.of` tạo object không cho sửa; biến vẫn có thể trỏ object khác |
| “`Collections.unmodifiableList` giữ nguyên dữ liệu mãi” | Wrapper là view; source thay đổi thì view có thể thay đổi theo |
| “`List.copyOf` deep-copy tất cả phần tử” | Chỉ tạo collection không cho sửa cấu trúc; phần tử mutable vẫn mutable |
| “`record` luôn immutable sâu” | Component field được chốt tham chiếu; component mutable vẫn phải phòng vệ |
| “`final` làm dữ liệu an toàn giữa nhiều thread” | Không đủ khi object mutable hoặc công bố trạng thái không an toàn |
| “Getter trả array trực tiếp là không sao vì field final” | Caller có thể sửa array trả ra; cần defensive copy |

### 10.1. Checklist khi review code

Trước khi kết luận “bất biến”, tự hỏi:

1. Tôi đang nói về **biến** (`final`) hay **đối tượng**?
2. Đối tượng có method nào sửa được trạng thái không?
3. Caller có giữ alias đến mutable input không? Có getter nào lộ mutable field không?
4. Nếu field là List/Map/Set, tôi đang có view hay snapshot? Các phần tử có mutable không?
5. Các biến `var` được suy luận đúng kiểu mong muốn chưa? Có cần kiểu interface tường minh?
6. Đối tượng có đi qua thread boundary không? Có phần mutable nào chưa đồng bộ hoặc chưa chốt snapshot không?
7. Tôi có đang dựa vào thứ tự collection, null hay identity object mà API không cam kết không?

## 11. Bài tập tự kiểm tra và đáp án

**Bài 1.** Xác định đoạn nào lỗi biên dịch và vì sao:

~~~java
final var text = "A";
// text = "B";     // (a)
var other = "A";
other = "B";        // (b)
~~~

**Đáp án:** (a) lỗi biên dịch nếu bỏ comment vì `text` là `final`; (b) hợp lệ vì `other` không final và kiểu của cả hai giá trị là `String`. Cả hai object `String` đều immutable.

**Bài 2.** Điều gì xảy ra?

~~~java
final var list = new java.util.ArrayList<>(java.util.List.of("A"));
list.add("B");
System.out.println(list);
~~~

**Đáp án:** In `[A, B]`. `final` không cấm sửa object `ArrayList`.

**Bài 3.** Hai cách làm này khác nhau thế nào?

~~~java
var input = new java.util.ArrayList<>(java.util.List.of("X"));
var view = java.util.Collections.unmodifiableList(input);
var copy = java.util.List.copyOf(input);
input.add("Y");
~~~

**Đáp án:** `view` đọc được `[X, Y]`; `copy` vẫn là `[X]`. View quan sát cùng source, còn copy cố định cấu trúc tại thời điểm tạo snapshot từ list mutable.

**Bài 4.** Có thể sửa object nằm trong `List.copyOf` không?

**Đáp án:** Có, nếu phần tử tự nó mutable và còn tham chiếu để chỉnh sửa. `copyOf` không tạo deep immutable. Với `List<String>`, phần tử `String` không đổi trạng thái; với `List<MutableItem>`, từng item vẫn có thể đổi.

**Bài 5.** Tại sao lớp chứa `private final byte[] bytes` vẫn có thể bị thay đổi?

**Đáp án:** Vì phần tử array có thể đổi. Nếu constructor giữ nguyên tham chiếu đầu vào hoặc getter trả trực tiếp array, caller có thể sửa dữ liệu. Cần `clone()`/copy cả hai phía khi muốn giữ trạng thái cố định.

**Bài 6.** Biến `var state = new ArrayList<String>()` được lambda dùng, sau đó gọi `state.add("X")` có hợp lệ không?

**Đáp án:** Có, nếu biến `state` không bị gán lại; nó là effectively final. Lambda vẫn nhìn thấy nội dung mutable của cùng object; việc capture không tạo snapshot.

**Bài 7.** Để trả về một danh sách nhãn đơn giản mà caller không được sửa cấu trúc, nên chọn gì?

**Đáp án:** Với danh sách cố định, `List.of("A", "B")`. Với dữ liệu đến từ collection mutable, `List.copyOf(source)`. Nếu phần tử là mutable object thì phải quyết định thêm chính sách snapshot/deep copy cho từng phần tử.

**Bài 8.** `final var list = List.of("A")` chứa mấy lớp bảo vệ và còn hạn chế gì?

**Đáp án:** `final` ngăn biến gán lại; `List.of` ngăn sửa cấu trúc; `String` phần tử là immutable. Tuy nhiên các điều này không đồng nghĩa cơ chế tổng quát để deep-freeze mọi object nếu thay `String` bằng kiểu mutable.

## 12. Tài liệu tra cứu chính thức

- [JEP 286: Local-Variable Type Inference](https://openjdk.org/jeps/286) – ý nghĩa và phạm vi của `var` từ Java 10.
- [Java Language Specification – Final Variables](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.4) – quy tắc `final` và effectively final.
- [Java SE API – List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html) – `List.of`, `List.copyOf`, tính unmodifiable và ràng buộc phần tử.
- [Java SE API – Collections](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html) – `unmodifiableList` và các view.
- [Java SE API – String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html) – hợp đồng immutable của String.
- [Java SE API – Record](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html) – cơ sở của record; thiết kế component bất biến cần xử lý riêng.

**Nguyên tắc mang sang mọi phiên bản Java hiện đại:** `var` quyết định cách khai báo **kiểu tĩnh**; `final` giới hạn việc **gán lại biến**; immutability là **hợp đồng trạng thái của object**. Khi thiết kế API, phải kiểm tra cả ba câu hỏi độc lập thay vì xem chúng như những từ đồng nghĩa.
