# Sao chép phòng vệ đối với mảng và collection có thể sửa trong record

## 1. Vấn đề: field `final` không làm đối tượng bên trong bất biến

Một `record` là **bộ mang dữ liệu bất biến nông** (*shallowly immutable data carrier*). Record khai báo trạng thái bằng các component trong header và Java tự tạo các trường tương ứng là `private final`. Tuy nhiên, nếu component là **tham chiếu tới đối tượng có thể thay đổi**, ví dụ `int[]`, `ArrayList<String>` hay `List<MutableMember>`, từ khóa `final` chỉ ngăn gán lại *tham chiếu field*, chứ không chặn thay đổi đối tượng được tham chiếu.

~~~java
record UnsafeScores(int[] values) {}

int[] source = {2, 4};
UnsafeScores scores = new UnsafeScores(source);
source[0] = 99;           // Sửa qua tham chiếu bên ngoài.
scores.values()[1] = 88;  // Sửa qua accessor mặc định của record.
~~~

Đây là **đoạn mã minh họa** cần đặt trong phạm vi phương thức cùng các khai báo phù hợp. Sau hai thao tác, mảng mà record giữ có nội dung `[99, 88]`. Cả `source` và `scores.values()` cùng trỏ đến **một mảng**, vì constructor và accessor mặc định không tự sao chép component.

**Sao chép phòng vệ** (*defensive copying*) là tạo bản sao độc lập đúng mức cần thiết khi **nhận dữ liệu vào** và, nếu cần, khi **trả dữ liệu ra**. Mục tiêu là không để người gọi thay đổi trạng thái logic của record qua một tham chiếu nằm ngoài quyền kiểm soát của nó.

Trong Java 14, record còn là tính năng preview. Record đã là tính năng **chính thức từ Java 16** và còn được dùng trong Java hiện hành. Các ví dụ ở đây viết cho **Java 17+**, không dùng cú pháp preview hay cờ biên dịch lỗi thời.

Sau bài này bạn cần nắm:
- Vì sao record với array/collection mutable vẫn có nguy cơ bị sửa từ ngoài.
- Cách dùng `clone()`, `Arrays.copyOf(...)` và accessor riêng để bảo vệ mảng.
- Khi nào `List.copyOf`, `Set.copyOf`, `Map.copyOf` thực sự giải quyết vấn đề.
- Sự khác biệt giữa **bản sao độc lập**, **view không thể sửa**, và **sao chép nông/sâu**.
- Vấn đề riêng của `equals`, `hashCode` với **array component** trong record.
- Cách chọn thiết kế đơn giản, đúng hợp đồng giá trị và tránh sao chép thừa.

## 2. Hai hướng rò rỉ tham chiếu

Với một component mutable, cần kiểm tra **hai đường đi**:

~~~text
ĐẦU VÀO                            ĐẦU RA

Mã gọi -> mảng/collection -> record -> accessor() -> mã gọi
          ^                 |          |
          |                 v          v
     Có thể sửa         Field final    Có thể sửa phần tử
     sau khởi tạo       chỉ giữ ref    nếu trả ref gốc
~~~

### Rò rỉ từ đầu vào (*inbound aliasing*)

~~~java
record BadInventory(List<String> names) {}

List<String> input = new ArrayList<>(List.of("A", "B"));
BadInventory inventory = new BadInventory(input);
input.add("C");
System.out.println(inventory.names()); // [A, B, C]
~~~

Đây là đoạn minh họa cần import `java.util.List` và `java.util.ArrayList`. Constructor mặc định giữ nguyên tham chiếu `input`, nên thao tác của bên gọi sau khi xây dựng record làm thay đổi dữ liệu được quan sát từ record.

### Rò rỉ từ đầu ra (*outbound aliasing*)

~~~java
BadInventory inventory = new BadInventory(new ArrayList<>(List.of("A", "B")));
inventory.names().clear();
System.out.println(inventory.names()); // []
~~~

Accessor mặc định trả nguyên tham chiếu tới collection đang lưu. Vì thế người gọi có thể sửa danh sách qua kết quả `names()`.

**Quy tắc:** Không chỉ hỏi “field có phải `final` hay không?”. Hãy hỏi **đối tượng mà field tham chiếu có thể sửa không**, và liệu bên ngoài còn giữ tham chiếu tới nó hoặc nhận được nó thông qua accessor không.

## 3. Mảng: sao chép khi nhận vào VÀ khi trả ra

Mảng Java luôn có thể thay đổi phần tử, kể cả khi biến tham chiếu tới mảng là `final`. Với một component `int[]`, cách thông dụng là:

~~~java
import java.util.Objects;

record SafeScores(int[] values) {
    SafeScores {
        values = Objects.requireNonNull(values, "values").clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }
}
~~~

Đây là **kiểu record độc lập** nếu đặt trong tệp phù hợp với import. Có hai bước khác nhau:

1. **Trong compact canonical constructor:** `values = ...clone();` tạo mảng mới trước khi record lưu dữ liệu. Vì đây là compact constructor, Java tự gán tham số đã được chuẩn hóa vào component field sau khi thân constructor kết thúc bình thường. Không được viết `this.values = ...` trong compact constructor.
2. **Trong accessor tường minh:** `return values.clone();` tạo mảng mới mỗi khi bên ngoài đọc. Mã gọi có thể sửa mảng kết quả mà không làm biến đổi mảng đang nằm trong record.

Nếu chỉ copy **đầu vào** mà accessor trả mảng gốc, người dùng vẫn có thể sửa mảng qua accessor. Nếu chỉ copy **đầu ra** mà constructor giữ tham chiếu đầu vào, người gọi vẫn có thể sửa record bằng mảng gốc. Với mục tiêu ngăn chỉnh sửa ngoài ý muốn, **cả hai hướng đều quan trọng**.

Có thể dùng `Arrays.copyOf(values, values.length)` thay cho `values.clone()` trong trường hợp mảng một chiều. Hai cách đều tạo một mảng mới với phần tử được sao chép. Với `int[]`, phần tử là giá trị nguyên thủy nên sao chép một chiều đã đủ để tách các giá trị.

### 3.1. Tham số null và accessor

`Objects.requireNonNull(values, "values")` chủ động từ chối `null` bằng `NullPointerException` có thông tin rõ. Nếu hợp đồng cho phép không có dữ liệu, hãy đưa ra chính sách riêng (ví dụ biểu diễn bằng mảng rỗng) thay vì để `clone()` tình cờ ném lỗi.

Khi một accessor khai báo tường minh cho component, phương thức đó phải phù hợp với quy tắc accessor record: tên đúng component, không có tham số, kiểu trả về đúng component và `public`. `@Override` trong ví dụ dùng được và giúp biểu thị ý định thay thế accessor ngầm định.

### 3.2. Mảng nhiều chiều và mảng phần tử mutable

`clone()` **chỉ sao chép lớp mảng ngoài**. Ví dụ, với `int[][] matrix`, `matrix.clone()` tạo mảng ngoài mới nhưng các `int[]` ở từng hàng vẫn là tham chiếu chung. Với `MutablePerson[]`, clone mảng cũng **không clone từng đối tượng `MutablePerson`**.

Với `int[][]` không có hàng `null`, một hàm sao chép sâu hơn có thể viết:

~~~java
static int[][] copyGrid(int[][] original) {
    Objects.requireNonNull(original, "original");
    int[][] copy = new int[original.length][];
    for (int i = 0; i < original.length; i++) {
        copy[i] = Objects.requireNonNull(original[i], "row").clone();
    }
    return copy;
}
~~~

Đây là **phương thức minh họa** cần đặt trong lớp và import `java.util.Objects`. Gọi nó ở **constructor** và **accessor** khi component là mảng hai chiều. Nếu phần tử là **đối tượng mutable**, cần quyết định sao chép đối tượng đó hoặc chuyển sang mô hình immutable; chỉ clone container không đủ.

## 4. Collection: snapshot không sửa được bằng `copyOf`

Với collection mang các phần tử bất biến như `String` hoặc `Integer`, Java hiện đại thường ưu tiên các factory có sẵn:

| Component | Mẫu trong compact constructor | Tính chất |
| --- | --- | --- |
| `List<T>` | `items = List.copyOf(items);` | Danh sách không sửa được, duy trì thứ tự duyệt nguồn lúc sao chép |
| `Set<T>` | `roles = Set.copyOf(roles);` | Tập hợp không sửa được, không đảm bảo thứ tự duyệt cụ thể |
| `Map<K, V>` | `values = Map.copyOf(values);` | Map không sửa được, không đảm bảo thứ tự duyệt cụ thể |

Ví dụ:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

record Settings(List<String> endpoints,
                Set<String> flags,
                Map<String, Integer> limits) {
    Settings {
        endpoints = List.copyOf(endpoints);
        flags = Set.copyOf(flags);
        limits = Map.copyOf(limits);
    }
}
~~~

Khi đầu vào là collection có thể sửa, các phương thức `copyOf` lưu một **snapshot không sửa được** của các phần tử tại lúc tạo record. Thêm/xóa phần tử trong nguồn sau đó không làm thay đổi danh sách/tập/map lưu trong record. Accessor mặc định trả chính collection không sửa được, vì vậy thường **không phải sao chép thêm ở đầu ra**.

Một số điểm quan trọng:

- `List.copyOf`, `Set.copyOf` và `Map.copyOf` không cho phép `null` ở đầu vào hoặc ở các phần tử (với map là key/value). Nếu mô hình dữ liệu cho phép `null`, hãy có chiến lược thay thế phù hợp.
- `List.copyOf` giữ thứ tự phần tử theo thứ tự duyệt collection nguồn; `Set.copyOf` và `Map.copyOf` **không có cam kết về iteration order**. Không dựa vào thứ tự của chúng khi cần kết quả đầu ra cố định.
- `Set.copyOf` tạo tập hợp; nếu collection nguồn chứa phần tử trùng bằng nhau, kết quả chỉ giữ một phần tử tương ứng. Đây là **ngữ nghĩa của Set**, không phải thao tác copy của List.
- Với collection vốn đã là một triển khai unmodifiable phù hợp, `copyOf` **có thể sử dụng lại** instance; không nên dựa vào việc luôn nhận đối tượng có danh tính mới. Hợp đồng cần quan tâm là **không sửa được cấu trúc và không phụ thuộc vào việc thêm/xóa từ nguồn mutable**.
- Các factory này đã tồn tại từ Java 10, nên phù hợp với Java 17+ và những phiên bản mới.

### 4.1. `List.copyOf` khác `Collections.unmodifiableList`

Đây là lỗi rất phổ biến:

~~~java
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
source.add("B");
System.out.println(view); // [A, B]
~~~

Đây là đoạn minh họa cần import `List`, `ArrayList` và `Collections`. `view` chặn thao tác `view.add(...)` nhưng vẫn là **view bọc cùng danh sách nguồn**; khi `source` đổi, `view` cũng cho thấy thay đổi.

Ngược lại:

~~~java
List<String> source = new ArrayList<>(List.of("A"));
List<String> snapshot = List.copyOf(source);
source.add("B");
System.out.println(snapshot); // [A]
~~~

`snapshot` không phụ thuộc vào thao tác thêm/xóa trên danh sách nguồn.

Nếu bắt buộc lưu các phần tử `null`, một lựa chọn là `Collections.unmodifiableList(new ArrayList<>(source))`: **copy danh sách trước**, rồi mới bọc unmodifiable view. Việc này bảo vệ cấu trúc danh sách bên trong, nhưng **vẫn không copy sâu các phần tử mutable**. Hãy dùng `List.copyOf` khi hợp đồng từ chối `null`, vì nó đơn giản và biểu đạt ý định tốt hơn.

### 4.2. Tại sao `new ArrayList<>(input)` chưa đủ?

~~~java
record NotEnough(List<String> items) {
    NotEnough {
        items = new ArrayList<>(items);
    }
}
~~~

Constructor đã tạo một danh sách độc lập, nên sửa `input` không ảnh hưởng record. Nhưng accessor `items()` mặc định vẫn trả danh sách `ArrayList` bên trong; bên gọi có thể chạy `record.items().clear()` và làm mất dữ liệu. Nếu muốn giữ mutable list, còn cần trả bản sao ở accessor hoặc view bảo vệ. Với dữ liệu chỉ đọc, `List.copyOf` thường là lựa chọn ngắn gọn hơn.

## 5. “Unmodifiable” không đồng nghĩa “deeply immutable”

`List.copyOf` làm cho **cấu trúc danh sách** không thể thêm, xóa, thay thế phần tử qua API của list; nó **không biến từng phần tử thành immutable**.

Giả sử có lớp mutable:

~~~java
final class Member {
    private String name;

    Member(String name) { this.name = name; }
    String name() { return name; }
    void rename(String newName) { name = newName; }
}

record Group(List<Member> members) {
    Group {
        members = List.copyOf(members);
    }
}
~~~

Với `Member m = new Member("An")` và `Group group = new Group(List.of(m))`, lệnh `m.rename("Binh")` **vẫn khiến** `group.members().get(0).name()` trả `"Binh"`. `List.copyOf` chỉ giữ lại **cùng đối tượng `Member`**, không đóng băng hoặc clone nó.

Giải pháp đúng tùy hợp đồng:

1. **Dùng phần tử vốn bất biến**, như `String`, `Integer` hoặc một record chỉ gồm các thành phần bất biến.
2. **Tạo immutable snapshot cho từng phần tử mutable** tại ranh giới nhận dữ liệu, ví dụ `new MemberSnapshot(m.name())` rồi `List.copyOf(...)`. Khi nguồn `Member` thay đổi, snapshot không đổi.
3. Nếu vẫn phải giữ phần tử mutable, cần **copy từng phần tử ở cả đầu vào và đầu ra** bằng cơ chế sao chép được định nghĩa rõ cho kiểu đó. Không có cách copy sâu tự động, tổng quát và an toàn cho mọi object graph.
4. Với cấu trúc lồng nhau như `Map<String, List<String>>`, `Map.copyOf(map)` chỉ bảo vệ map bên ngoài; các danh sách bên trong vẫn cần `List.copyOf` riêng (và các phần tử sâu hơn cần được xét tiếp).

Nếu không có nhu cầu lưu các đối tượng mutable sâu, **ưu tiên thiết kế component bằng các kiểu giá trị bất biến** ngay từ đầu. Điều này giúp `equals`, `hashCode`, logging, caching và xử lý đa luồng dễ dự đoán hơn.

## 6. Chương trình đầy đủ: array copy, collection snapshot và mutable element

Lưu chương trình sau vào tệp **`RecordDefensiveCopyDemo.java`**. Mã sử dụng API và cú pháp chuẩn Java 17, có thể biên dịch/chạy trên JDK mới hơn mà không bật preview.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public final class RecordDefensiveCopyDemo {
    public record Scores(int[] points) {
        public Scores {
            points = Objects.requireNonNull(points, "points").clone();
        }

        @Override
        public int[] points() {
            return points.clone();
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof Scores other
                    && Arrays.equals(points, other.points);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(points);
        }

        @Override
        public String toString() {
            return "Scores" + Arrays.toString(points);
        }
    }

    public record Labels(List<String> values) {
        public Labels {
            values = List.copyOf(values);
        }
    }

    static final class MutableMember {
        private String name;

        MutableMember(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        void rename(String name) {
            this.name = name;
        }
    }

    public record ShallowGroup(List<MutableMember> members) {
        public ShallowGroup {
            members = List.copyOf(members);
        }
    }

    public record MemberSnapshot(String name) {
    }

    public record SafeGroup(List<MemberSnapshot> members) {
        public SafeGroup {
            members = List.copyOf(members);
        }
    }

    public static void main(String[] args) {
        int[] input = {2, 4};
        Scores scores = new Scores(input);
        input[0] = 99;
        int[] exposed = scores.points();
        exposed[1] = 88;
        System.out.println("Array contents: " + Arrays.toString(scores.points()));
        System.out.println("Array equals by contents: "
                + scores.equals(new Scores(new int[]{2, 4})));

        List<String> names = new ArrayList<>(List.of("api", "java"));
        Labels labels = new Labels(names);
        names.add("later");
        System.out.println("List snapshot: " + labels.values());
        try {
            labels.values().add("illegal");
        } catch (UnsupportedOperationException expected) {
            System.out.println("List mutation blocked: true");
        }

        MutableMember member = new MutableMember("An");
        ShallowGroup shallow = new ShallowGroup(List.of(member));
        SafeGroup safe = new SafeGroup(List.of(new MemberSnapshot(member.name())));
        member.rename("Binh");
        System.out.println("Mutable element: " + shallow.members().get(0).name());
        System.out.println("Snapshot element: " + safe.members().get(0).name());

        List<String> original = new ArrayList<>(List.of("x"));
        List<String> view = Collections.unmodifiableList(original);
        original.add("y");
        System.out.println("Unmodifiable view: " + view);
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 --release 17 RecordDefensiveCopyDemo.java
java RecordDefensiveCopyDemo
~~~

**Stdout chính xác (đã kiểm chứng):**

~~~text
Array contents: [2, 4]
Array equals by contents: true
List snapshot: [api, java]
List mutation blocked: true
Mutable element: Binh
Snapshot element: An
Unmodifiable view: [x, y]
~~~

### 6.1. Phân tích từng kết quả

**`Array contents: [2, 4]`**: cả việc sửa mảng `input[0]` lẫn việc sửa mảng nhận từ `scores.points()` đều không tác động đến mảng đang giữ trong `Scores`. Constructor và accessor tạo bản sao khác nhau.

**`Array equals by contents: true`**: `Scores` định nghĩa lại `equals` để so sánh nội dung mảng bằng `Arrays.equals`. Hai bản ghi chứa các mảng khác tham chiếu nhưng cùng các số `2, 4` được coi là bằng nhau.

**`List snapshot: [api, java]`**: sau khi xây dựng `Labels`, mã gọi thêm `"later"` vào danh sách `names` gốc, nhưng `labels.values()` không đổi.

**`List mutation blocked: true`**: `List.copyOf` trả danh sách unmodifiable, nên `labels.values().add(...)` ném `UnsupportedOperationException`. Ngoại lệ được bắt trong ví dụ để tiếp tục các phép kiểm tra khác.

**`Mutable element: Binh`**: danh sách bên trong `ShallowGroup` không thể thêm/xóa, nhưng nó tham chiếu đến `MutableMember` cũ. Khi gọi `rename` bên ngoài, giá trị quan sát được đổi.

**`Snapshot element: An`**: `SafeGroup` lưu một `MemberSnapshot` độc lập được tạo khi tên vẫn là `"An"`. Bản ghi `MemberSnapshot(String name)` chỉ mang `String` bất biến, nên đổi tên đối tượng nguồn sau đó không tác động snapshot.

**`Unmodifiable view: [x, y]`**: `Collections.unmodifiableList(original)` là view; thao tác thêm `"y"` qua `original` vẫn xuất hiện trong view. Chặn phương thức sửa trên view **không đồng nghĩa** sao chép dữ liệu của nguồn.

## 7. Lưu ý đặc biệt: array component và `equals` / `hashCode` của record

Record thường được chọn để biểu diễn **giá trị**. Tuy nhiên, với:

~~~java
record RawBytes(byte[] data) {}
~~~

Java tự tạo `equals`/`hashCode` dựa trên component `byte[]`. Mảng Java **không định nghĩa so sánh bằng nhau theo từng phần tử** thông qua `Object.equals`; vì vậy mặc định hai `byte[]` khác đối tượng dù chứa cùng các byte sẽ **không được coi là bằng nhau**.

Ngay cả nếu bạn sao chép mảng trong constructor và accessor nhưng **không** thay đổi `equals`, hai record được tạo từ các bản sao mảng khác nhau vẫn có thể `equals` là `false`. Điều này dễ làm bất ngờ khi dùng record làm key trong map, phần tử trong set hay khi kiểm tra giá trị.

Trong chương trình `Scores` ở trên:
- `Arrays.equals(points, other.points)` so sánh **nội dung** hai mảng `int[]`.
- `Arrays.hashCode(points)` tạo mã băm dựa trên cùng nội dung, giữ hợp đồng `equals/hashCode`.
- `Arrays.toString(points)` cung cấp chuỗi hiển thị các phần tử thay vì dạng định danh mặc định của mảng.

Với mảng lồng nhau có ý nghĩa giá trị, cần cân nhắc `Arrays.deepEquals` và `Arrays.deepHashCode`, đồng thời bảo vệ các mảng con ở constructor/accessor. Nếu các phần tử là đối tượng mutable, phải xác định ngữ nghĩa snapshot và equality cho **các phần tử** nữa.

### 7.1. Bảo toàn “copy invariant” của record

Đặc tả record kỳ vọng rằng tạo lại một record từ các accessor của nó sẽ tạo ra một giá trị tương đương:

~~~java
Scores original = new Scores(new int[]{2, 4});
Scores copy = new Scores(original.points());
System.out.println(original.equals(copy)); // true với Scores đã override equals.
~~~

Vì accessor `points()` trả mảng **clone**, `copy` sẽ có mảng tham chiếu khác `original`. Nếu record chỉ dùng `equals` ngầm định cho component `int[]`, phép so sánh trên có thể trả `false`. Viết `equals/hashCode` dựa trên nội dung như `Scores` giúp thiết kế phù hợp hơn với hợp đồng giá trị.

Với `List<String>` có các phần tử immutable, `List.copyOf` đi cùng `equals/hashCode` mặc định của record thường là lựa chọn đơn giản hơn: bản thân `List.equals` đã so sánh các phần tử theo vị trí.

## 8. Chọn mức sao chép theo cấu trúc dữ liệu

| Kiểu dữ liệu component | Khi nhận vào | Khi trả ra | Lưu ý còn lại |
| --- | --- | --- | --- |
| `int[]`, `byte[]` | `clone()` hoặc `Arrays.copyOf` | Clone lần nữa | Nếu cần value equality, override `equals/hashCode` theo nội dung |
| `String[]` | Clone mảng ngoài | Clone mảng ngoài | `String` bất biến nên không cần clone phần tử |
| `MutableItem[]` | Clone mảng và tạo snapshot/copy từng item | Không lộ item mutable gốc | Clone mỗi container không đủ |
| `List<String>` | `List.copyOf` | Dùng accessor mặc định | Nguồn thay đổi không ảnh hưởng; loại bỏ/null cần chính sách |
| `Set<String>` | `Set.copyOf` | Dùng accessor mặc định | Không phụ thuộc thứ tự duyệt |
| `Map<String, Integer>` | `Map.copyOf` | Dùng accessor mặc định | Key và value đã là immutable |
| `List<MutableItem>` | Copy danh sách **và** snapshot/copy từng item | Chỉ trả các item bất biến hoặc copy lại | `List.copyOf` đơn lẻ vẫn còn alias của item |
| `Map<String, List<String>>` | Copy từng list value, sau đó `Map.copyOf` | Thường dùng accessor mặc định khi mọi list value đã unmodifiable | Copy map ngoài không copy các list trong |

**Cân nhắc hiệu năng:** Mỗi lần gọi accessor mảng có clone tạo một mảng mới và sao chép phần tử, chi phí khoảng `O(n)` theo độ dài mảng. Với dữ liệu lớn hoặc đường gọi rất nóng, cân nhắc dùng collection immutable được xây dựng một lần, API thao tác chỉ đọc hoặc kiểu thiết kế khác; vẫn phải giữ đúng hợp đồng an toàn dữ liệu. Không tối ưu bằng cách trả thẳng mảng mutable bên trong record khi rò rỉ tham chiếu là nguy cơ thực tế.

## 9. Những lỗi thường gặp và cách sửa

### Lỗi A — Tin rằng record tự động sao chép component

~~~java
record R(int[] numbers) {} // Không tự clone.
~~~

**Sửa:** Khai báo compact canonical constructor để clone **đầu vào**, và accessor riêng để clone **đầu ra**. Nếu cần so sánh theo giá trị, triển khai `equals/hashCode` đồng bộ.

### Lỗi B — Chỉ copy một phía

~~~java
record HalfSafe(byte[] payload) {
    HalfSafe {
        payload = payload.clone(); // Chỉ bảo vệ đầu vào.
    }
}
~~~

`new HalfSafe(data).payload()[0] = 42;` vẫn sửa mảng nội bộ thông qua accessor mặc định. **Sửa:** thêm `public byte[] payload() { return payload.clone(); }`. Đồng thời xét vấn đề equality nếu dùng record như giá trị.

### Lỗi C — Dùng `Collections.unmodifiableList(source)` trực tiếp

Đây là **view**, không phải snapshot độc lập. Nguồn vẫn có thể thay đổi qua tham chiếu đang giữ ở bên ngoài.

**Sửa:** ưu tiên `List.copyOf(source)`, hoặc `Collections.unmodifiableList(new ArrayList<>(source))` nếu cần giữ các phần tử `null` theo hợp đồng.

### Lỗi D — Sao chép list nhưng phần tử vẫn mutable

`List.copyOf(mutableItems)` giữ cùng các tham chiếu phần tử. Người gọi có thể đổi từng item dù không thêm/xóa item.

**Sửa:** chuyển item thành một kiểu immutable hoặc tạo bản sao/snapshot từng item, và bảo đảm đường accessor không lộ item mutable gốc.

### Lỗi E — Dùng `clone()` trên mảng nhiều chiều rồi tưởng đã deep copy

`matrix.clone()` chỉ copy outer array. Các `matrix[i]` vẫn là mảng con dùng chung.

**Sửa:** copy các hàng (và sâu hơn nếu cần) ở cả đường vào/ra; kiểm tra null và mô hình dữ liệu.

### Lỗi F — Không nêu chính sách null

`List.copyOf` / `Map.copyOf` / `Set.copyOf` từ chối null theo API; `array.clone()` trên null sẽ gây `NullPointerException`.

**Sửa:** Định nghĩa rõ null có được chấp nhận không, báo lỗi sớm hoặc chuẩn hóa sang giá trị rỗng khi phù hợp. Không âm thầm đổi nghiệp vụ chỉ để tránh exception.

### Lỗi G — Lạm dụng defensive copy ở mọi nơi

Nếu component là `String`, `Integer`, record bất biến hoặc snapshot unmodifiable với các phần tử immutable, copy lại một cách tùy tiện có thể tốn chi phí mà không tăng độ an toàn.

**Sửa:** Xác định các ranh giới **ownership**, độ mutable của container và từng phần tử, rồi chọn copy đúng nơi cần.

## 10. Bài tập ứng dụng

Viết record `TaskTags(String taskId, List<String> tags)` với yêu cầu:

1. Không chấp nhận `taskId == null`, `taskId` rỗng sau `strip()` hoặc `tags == null`.
2. Chuẩn hóa `taskId` bằng `strip()`.
3. Tránh rò rỉ danh sách qua cả constructor và accessor; từ chối phần tử `null`.
4. Không khai báo thêm instance field; dùng compact canonical constructor.
5. Kiểm tra: thêm một tag vào danh sách đầu vào **sau khi** tạo record không làm thay đổi `record.tags()`; không được sửa danh sách trả về.

**Đáp án tham khảo** (tệp `TaskTags.java`):

~~~java
import java.util.List;
import java.util.Objects;

public record TaskTags(String taskId, List<String> tags) {
    public TaskTags {
        taskId = Objects.requireNonNull(taskId, "taskId").strip();
        if (taskId.isEmpty()) {
            throw new IllegalArgumentException("taskId is blank");
        }
        tags = List.copyOf(tags);
    }
}
~~~

Giải thích:
- `Objects.requireNonNull(...)` + `strip()` + điều kiện rỗng bảo đảm mã tác vụ hợp lệ.
- `List.copyOf(tags)` đồng thời tạo snapshot unmodifiable và từ chối danh sách hoặc phần tử `null`. Accessor mặc định `tags()` đã đủ vì không thể sửa cấu trúc danh sách.
- `String` bất biến nên không cần copy riêng `taskId`; các tag cũng là `String`, nên không có rò rỉ sâu từ phần tử.

Thử trong một phương thức sau khi import `ArrayList`, `List`:

~~~java
List<String> source = new ArrayList<>(List.of("backend"));
TaskTags record = new TaskTags("  T-1  ", source);
source.add("urgent");
System.out.println(record.taskId()); // T-1
System.out.println(record.tags());   // [backend]
~~~

Nếu cần một bài mở rộng, thay `List<String>` bằng `List<MutableTask>` rồi xác định cách tạo **immutable snapshot** cho từng task; chỉ thay `List.copyOf` là chưa đủ.

## 11. Ghi nhớ để thiết kế record an toàn

- **Record chỉ bất biến nông:** component field `final` không làm mảng hay collection mutable tự động bất biến.
- **Mảng:** copy khi vào và khi ra; với array component mang ngữ nghĩa giá trị, cần cân nhắc `Arrays.equals` và `Arrays.hashCode` để bảo toàn equality/invariant.
- **Collection:** dùng `List.copyOf`, `Set.copyOf`, `Map.copyOf` cho snapshot unmodifiable, nhưng hiểu chính sách `null`, thứ tự và việc có thể tái sử dụng instance.
- **Không nhầm view với copy:** `Collections.unmodifiableList(source)` vẫn phản ánh sửa đổi của `source`.
- **Không nhầm unmodifiable với deep immutable:** phần tử mutable và container lồng nhau vẫn có thể thay đổi.
- **Chọn đúng mức copy:** snapshot dữ liệu tại constructor, không trả tham chiếu mutable nội bộ, ưu tiên component có kiểu immutable khi cần hợp đồng giá trị ổn định.

**Tài liệu chính thức:**
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395) — ngữ nghĩa record và trạng thái tính năng chính thức.
- [Java SE 17 — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html) — record bất biến nông, canonical constructor/accessor, defensive copy và invariant.
- [Java SE 21 — `List.copyOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) — snapshot, unmodifiable list, phần tử mutable và null.
- [Java SE 21 — `Set.copyOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)) và [`Map.copyOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)) — ngữ nghĩa sao chép set/map.
- [Java SE 21 — `Arrays`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html) — `equals`, `hashCode`, `deepEquals` và `copyOf`.
- [Java SE 21 — `Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) — đặc điểm unmodifiable view.
