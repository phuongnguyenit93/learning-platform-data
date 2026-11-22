# Record chỉ bảo đảm bất biến nông — hiểu đúng `final`, aliasing và defensive copy trong Java 17+

Một `record` của Java là dạng class đặc biệt dùng để biểu diễn một nhóm **record components** cố định. Khi viết `record User(String name, List<String> roles) {}`, Java tạo các private final component fields và accessors tương ứng như `name()`, `roles()`. Bạn không thể gán lại component field của một record đã xây dựng, nhưng **đối tượng mà một component reference trỏ tới vẫn có thể thay đổi**.

Đó là ý nghĩa quan trọng của nhận định **“record chỉ bảo đảm bất biến nông”**: cấu trúc các **component references** cố định sau construction, chứ Java **không tự đóng băng toàn bộ object graph** đằng sau những references đó.

~~~java
record Group(java.util.List<String> members) {
}
~~~

Đây là khai báo record hợp lệ. Một caller có thể tạo một `ArrayList`, truyền nó vào Group, rồi sửa ArrayList. Accessor `members()` mặc định cũng trả reference tới list đang được lưu, vì vậy người khác có thể gọi `add` trên list ấy.

Ngược lại, `record Point(int x, int y) {}` chỉ chứa hai primitives, nên không có mutable object bên dưới các component references. Point là một trường hợp **giá trị ổn định** đơn giản hơn Group. Như vậy, mức bất biến quan sát được phụ thuộc **kiểu components, constructor, accessors và các objects được chia sẻ**, không chỉ từ khóa `record`.

Bài thuộc **Java core – class-object**, nhóm **Record**, chủ đề **Record chỉ bảo đảm bất biến nông**. Tất cả chương trình độc lập viết cho **Java 17+**, có tên file, lệnh `javac`/`java` và stdout đã phân tích cụ thể. Các snippets không có `main` và mã cố ý sai được phân biệt riêng.

## 1. Kết quả học tập

Sau bài, bạn có thể:

1. Giải thích khác biệt giữa **field reference final** và **object bất biến**.
2. Xác định nơi có thể xảy ra **aliasing** trước và sau khi tạo record.
3. Biết rằng accessor mặc định trả component value; với reference component, đó là **reference** tới object.
4. Phân biệt **modifiable collection**, **unmodifiable view**, **unmodifiable snapshot** và **deep immutability**.
5. Dùng **compact canonical constructor** hoặc explicit canonical constructor để defensive copy dữ liệu đầu vào.
6. Biết khi nào cần override accessor, đặc biệt với mảng.
7. Hiểu `List.copyOf`, `Set.copyOf`, `Map.copyOf` không tự deep-copy elements và values.
8. Phân tích mutable elements trong một list vốn đã unmodifiable.
9. Dự đoán tác động của state mutable lên `equals`, `hashCode`, `toString` của record.
10. Thiết kế value-record với nested collections hoặc mutable Java legacy types.
11. Phân biệt **bất biến** với **thread safety** và tính nhất quán của dữ liệu.
12. Xây một chính sách ownership/copying rõ ở ranh giới API.

## 2. Record thực sự sinh ra những gì?

Khai báo:

~~~java
record OrderLine(String sku, int quantity) {
}
~~~

Java tạo những thành phần chính sau, theo ngữ nghĩa của record:

- Một class có tên `OrderLine`, implicitly `final`, kế thừa `java.lang.Record`.
- Private final fields tương ứng `sku` và `quantity`.
- Public component accessors `sku()` và `quantity()` nếu bạn không định nghĩa chúng.
- Canonical constructor với các tham số `String sku, int quantity`.
- `equals(Object)`, `hashCode()`, `toString()` theo components, nếu không override.

**Record không mặc định sinh setters.** Không có API `line.setSku("X")` trừ khi bạn tự định nghĩa một method tên như thế, nhưng cũng không thể dùng method đó để gán lại component field final.

Một lớp record còn bị hạn chế về việc khai báo **instance fields bổ sung**. Bạn có thể thêm methods, static members và nested types thích hợp, nhưng không thể biến record thành một JavaBean với nhiều instance variables tự do.

Điều Java bảo đảm là **field không bị gán lại sau construction**, không phải “mọi thứ truy cập qua field cũng bất biến”.

## 3. Phân biệt ba tầng trạng thái

Hãy tách ba tầng sau:

| Tầng | Ví dụ | Điều gì bị khóa? |
| --- | --- | --- |
| Component field trong record | `private final List<String> roles` | Reference lưu trong field không thể gán lại sau khi được khởi tạo |
| Object do reference trỏ tới | `ArrayList<String>` | **Không** tự khóa; `add`, `remove`, `set` vẫn có thể sửa |
| Elements của collection | `MutableUser`, `StringBuilder` | **Không** tự khóa; object element có thể tiếp tục mutate |

Sơ đồ:

~~~text
Record instance User
    |
    +-- final name ----------> String "An" (immutable)
    |
    +-- final roles ---------> ArrayList object (mutable)
                                  |
                                  +-- element 0 --> String "reader"
                                  +-- element 1 --> String "editor"

Record khóa reference roles, không khóa các operations trên ArrayList.
~~~

Nếu accessors trả references trực tiếp, code bên ngoài còn có thể **chạm tới object đích** mà record nắm. Nếu caller đã giữ reference ấy từ trước khi tạo record, thay đổi cũng lan ngược vào record.

Đây là **shallow immutability (bất biến nông)**, không phải deep immutability.

## 4. Chương trình 1 — hai đường thay đổi một record component

Tạo tệp **`MutableRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

record Group(List<String> members) {
}

public class MutableRecordDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        Group group = new Group(source);
        System.out.println("initial=" + group.members());

        source.add("Binh");
        System.out.println("after source=" + group.members());

        group.members().add("Chi");
        System.out.println("after accessor=" + source);
        System.out.println("record=" + group);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 MutableRecordDemo.java
java MutableRecordDemo
~~~

**Stdout chính xác:**

~~~text
initial=[An]
after source=[An, Binh]
after accessor=[An, Binh, Chi]
record=Group[members=[An, Binh, Chi]]
~~~

Dòng `source.add("Binh")` cho thấy **đầu vào được chia sẻ**. Dòng `group.members().add("Chi")` cho thấy **accessor mặc định làm lộ mutable reference**. Đây là hai đường thay đổi từ hai phía ranh giới API.

Không có phép gán `group.members = otherList`, nhưng nội dung list mà field final tham chiếu vẫn đổi.

## 5. `final` bảo vệ assignment, không bảo vệ mutation

Trong một record:

~~~java
record Basket(java.util.List<String> items) {
    void add(String item) {
        items.add(item);
    }
}
~~~

Đây là code Java **hợp lệ**. `Basket.add` có thể mutate List hiện tại, dù `items` là final field. Tuy nhiên, đây là cách thiết kế dễ khiến người đọc tưởng record giống value object bất biến mà thực chất còn mutable behavior.

Phép gán trực tiếp `this.items = anotherList` sau construction là bất hợp lệ; nhưng `this.items.add(...)` là lời gọi method trên object đích, không phải gán field.

Đối với primitive `int quantity`, không có nội dung object để mutate. Bạn cũng không được `quantity++` trong instance method record vì component field là final. Với `String`, bản thân String immutable; một reference tới String vì vậy cũng ổn định về nội dung ký tự. Nhưng với `List`, `Date`, array hay custom mutable DTO, cần policy riêng.

## 6. Aliasing: nguyên nhân sâu của bất biến nông

**Aliasing** là khi hai hay nhiều references trỏ tới **cùng một object**.

~~~text
caller.source -----+
                   |
                   v
             ArrayList object
                   ^
                   |
record.items ------+

Gọi source.add("X") hoặc record.items().add("Y")
đều sửa cùng ArrayList.
~~~

Trong một constructor record mặc định, component reference được nhận rồi lưu lại mà không copy. Vì vậy caller và record thường là hai bên giữ aliases tới cùng object.

Cả hai câu sau đều cần xét:

- **Input aliasing:** caller còn giữ `source` và sửa nó sau khi truyền vào record.
- **Output aliasing:** caller gọi accessor, nhận component reference, rồi sửa object đó.

Một record đạt **shallow immutability** về fields vẫn có thể bị thay đổi state quan sát được từ cả hai đường này. Nếu record dùng làm cấu hình, dữ liệu giao dịch hoặc key của một map, rủi ro sẽ trở nên đáng kể.

## 7. Cách phòng vệ với List: copy trong canonical constructor

Nếu component là `List<String>`, một phương án phổ biến là:

~~~java
import java.util.List;
import java.util.Objects;

record Team(String name, List<String> members) {
    Team {
        Objects.requireNonNull(name, "name");
        members = List.copyOf(
                Objects.requireNonNull(members, "members"));
    }
}
~~~

Đây là một **record hoàn chỉnh**, chưa có `main`. `Team { ... }` là **compact canonical constructor**.

- Biến tham số `members` được thay bằng `List.copyOf(...)`, tạo một snapshot **không hỗ trợ thay đổi cấu trúc**.
- Sau khi block compact constructor hoàn tất, compiler gán component field `members` từ **tham số đã được thay**.
- Đối tượng list caller truyền vào có thể tiếp tục thay đổi mà không làm list đã snapshot nhận các additions/removals đó.
- Accessor mặc định `members()` có thể trả thẳng component reference, vì list đang lưu là unmodifiable về cấu trúc.

`List.copyOf` không cho null list và null elements. Nếu domain cho phép null elements, cần một chiến lược copying khác.

**Chú ý:** “copy” ở đây là **shallow copy của elements/references**, không sao chép mọi object con.

## 8. Chương trình 2 — copy lúc nhận vào, accessor không cho sửa

Tệp **`DefensiveListRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Team(String name, List<String> members) {
    Team {
        Objects.requireNonNull(name, "name");
        members = List.copyOf(
                Objects.requireNonNull(members, "members"));
    }
}

public class DefensiveListRecordDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        Team team = new Team("Core", source);

        source.add("Binh");
        System.out.println("source=" + source);
        System.out.println("team=" + team.members());

        try {
            team.members().add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot add="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("still=" + team.members());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 DefensiveListRecordDemo.java
java DefensiveListRecordDemo
~~~

**Stdout:**

~~~text
source=[An, Binh]
team=[An]
cannot add=UnsupportedOperationException
still=[An]
~~~

Chính **compact constructor** bảo vệ đầu vào. Nếu chỉ đặt modifier `final` trên local variable `source` của caller thì vẫn không khóa list.

Với `List<String>`, các elements là immutable strings, nên snapshot cấu trúc thường đủ cho một record có state quan sát được ổn định.

## 9. `Collections.unmodifiableList` không tự tạo snapshot

Cần phân biệt hai cách:

~~~java
List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);
~~~

Đây là snippets trong method, cần imports. Cả `view` và `snapshot` **không cho sửa cấu trúc trực tiếp** qua interface List. Nhưng:

- `Collections.unmodifiableList(source)` tạo **unmodifiable view** của chính source. Nếu source bị sửa qua reference khác, view phản ánh thay đổi.
- `List.copyOf(source)` cung cấp một **unmodifiable list theo nội dung tại thời điểm gọi**, không phải view live của mutable source.
- `List.copyOf` có thể **tái sử dụng một unmodifiable list** phù hợp thay vì cấp object mới; API không hứa luôn tạo object riêng.
- Cả hai chỉ kiểm soát việc sửa **collection structure**, không tự deep-copy elements.

Nếu constructor record dùng `Collections.unmodifiableList(input)` trực tiếp, nhưng caller còn reference tới `input`, record vẫn chịu **input aliasing**.

Muốn view unmodifiable **và** tách nguồn mutable khi có null elements, có thể dùng `Collections.unmodifiableList(new ArrayList<>(input))`. Đây là snapshot cấu trúc trong một mutable copy riêng được bọc lại, miễn bạn không công bố copy cho nơi khác.

## 10. Chương trình 3 — view và snapshot khác nhau

Tệp **`ViewVsSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

record ViewBox(List<String> values) {
    ViewBox {
        values = Collections.unmodifiableList(values);
    }
}

record SnapshotBox(List<String> values) {
    SnapshotBox {
        values = List.copyOf(values);
    }
}

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        ViewBox live = new ViewBox(source);
        SnapshotBox frozen = new SnapshotBox(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("view=" + live.values());
        System.out.println("snapshot=" + frozen.values());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
~~~

**Stdout:**

~~~text
source=[A, B]
view=[A, B]
snapshot=[A]
~~~

Unmodifiable **không nhất thiết** đồng nghĩa independent snapshot. Đây là lỗi phổ biến khi triển khai defensive copy cho record components.

Nếu code thật cần một view live có chủ đích, hãy ghi rõ trong API rằng record không có state hoàn toàn ổn định; đừng đặt tên `Immutable...` gây hiểu nhầm.

## 11. Một List đã snapshot vẫn có thể chứa elements mutable

Giả sử:

~~~java
final class MutableMember {
    private String name;

    MutableMember(String name) {
        this.name = name;
    }

    void rename(String next) {
        name = next;
    }

    String name() {
        return name;
    }
}
~~~

Dù record giữ `List.copyOf(members)`, nó vẫn giữ **references tới các MutableMember objects cũ**. Caller có thể giữ một member reference và gọi `rename`.

Sơ đồ:

~~~text
source List --------> MutableMember("An")
                          ^
                          |
snapshot List ------------+

Snapshot cắt chia sẻ phần cấu trúc List,
nhưng KHÔNG tự tạo một MutableMember mới.
~~~

Do đó `List.copyOf` có thể ngăn `record.members().add(...)`, nhưng không ngăn `record.members().get(0).rename(...)` nếu phần tử công bố method mutate.

Muốn bất biến sâu ở phạm vi cấu trúc ấy, nên dùng elements bất biến (ví dụ record chỉ chứa immutable values) hoặc tạo **defensive element copies** và không làm lộ mutable children.

## 12. Chương trình 4 — phần tử của unmodifiable list vẫn đổi

Tệp **`MutableElementRecordDemo.java`**:

~~~java
import java.util.List;

final class MutableMember {
    private String name;

    MutableMember(String name) {
        this.name = name;
    }

    void rename(String newName) {
        name = newName;
    }

    @Override
    public String toString() {
        return name;
    }
}

record Squad(List<MutableMember> members) {
    Squad {
        members = List.copyOf(members);
    }
}

public class MutableElementRecordDemo {
    public static void main(String[] args) {
        MutableMember first = new MutableMember("An");
        Squad squad = new Squad(List.of(first));

        System.out.println("before=" + squad.members());

        first.rename("Binh");
        System.out.println("after external="
                + squad.members());

        squad.members().get(0).rename("Chi");
        System.out.println("after accessor="
                + squad.members());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 MutableElementRecordDemo.java
java MutableElementRecordDemo
~~~

**Stdout:**

~~~text
before=[An]
after external=[Binh]
after accessor=[Chi]
~~~

Trong demo này, list không cho thay đổi cấu trúc, nhưng phần tử MutableMember vẫn đổi trạng thái. Vì accessor trả List chứa reference tới MutableMember ấy, caller thậm chí có đường truy cập trực tiếp để đổi phần tử.

Điều kiện “list unmodifiable” **không đủ** để kết luận record chứa list ấy là deep immutable.

## 13. Thiết kế phần tử bất biến và chuyển đổi ở ranh giới

Một cách an toàn hơn là **dùng một kiểu value bất biến** cho phần tử, ví dụ:

~~~java
record MemberName(String value) {
    MemberName {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("bad name");
        }
    }
}

record SquadSnapshot(List<MemberName> members) {
    SquadSnapshot {
        members = List.copyOf(members);
    }
}
~~~

Hai record trên có component types là String và List<MemberName>. String không mutable; MemberName cũng không có mutable child. List được snapshot unmodifiable nên trong phạm vi đồ thị này state ổn định.

Khi nguồn ban đầu là DTO có setters, **chuyển mỗi DTO thành value record mới**:

~~~java
// Ý tưởng bên trong một method có source kiểu List<MutableMember>:
List<MemberName> stable = source.stream()
        .map(item -> new MemberName(item.name()))
        .toList();
SquadSnapshot snapshot = new SquadSnapshot(stable);
~~~

Đây là snippet trong method với các types như đã khai báo. `Stream.toList()` trả unmodifiable list, nhưng quan trọng nhất là `new MemberName(item.name())` **tạo value element**, không giữ mutable DTO cũ.

**Lưu ý:** nếu source bị sửa đồng thời trong khi copy, cần đồng bộ/snapshot ở ranh giới nguồn để có dữ liệu nhất quán. Defensive copying không tự giải quyết data races trong quá trình sao chép.

## 14. Chương trình 5 — thay mutable elements bằng immutable values

Tệp **`DeepValueSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class MutablePerson {
    private String name;

    MutablePerson(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    void rename(String name) {
        this.name = name;
    }
}

record PersonName(String value) {
    PersonName {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("bad name");
        }
    }
}

record GroupSnapshot(List<PersonName> members) {
    GroupSnapshot {
        members = List.copyOf(members);
    }

    static GroupSnapshot from(List<MutablePerson> source) {
        List<PersonName> values = new ArrayList<>();
        for (MutablePerson person : source) {
            values.add(new PersonName(person.name()));
        }
        return new GroupSnapshot(values);
    }
}

public class DeepValueSnapshotDemo {
    public static void main(String[] args) {
        MutablePerson person = new MutablePerson("An");
        List<MutablePerson> source = new ArrayList<>();
        source.add(person);

        GroupSnapshot group = GroupSnapshot.from(source);

        person.rename("Binh");
        source.add(new MutablePerson("Chi"));

        System.out.println("group=" + group.members());
        System.out.println("source size=" + source.size());
        System.out.println("first source name="
                + source.get(0).name());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 DeepValueSnapshotDemo.java
java DeepValueSnapshotDemo
~~~

**Stdout:**

~~~text
group=[PersonName[value=An]]
source size=2
first source name=Binh
~~~

GroupSnapshot không chia sẻ những MutablePerson instances của source: nó chỉ giữ PersonName immutable values. Việc đổi person hoặc thêm entry mới vào source không tác động tới snapshot.

Đây là **deep snapshot trong phạm vi object graph được chọn**; không phải một thuật toán copy sâu tổng quát cho mọi class trong Java. Chính sách copy phải biết domain và những tầng mutable nào thật sự tồn tại.

## 15. Mảng là trường hợp dễ bỏ sót nhất

Array trong Java mutable. Với:

~~~java
record Packet(byte[] bytes) {
}
~~~

constructor ngầm định lưu reference mảng truyền vào; accessor `bytes()` trả chính reference đó.

Hai đường mutation:

~~~java
byte[] source = {1, 2};
Packet packet = new Packet(source);

source[0] = 9;
packet.bytes()[1] = 8;
~~~

Đây là snippet hợp lệ trong method. Mảng nằm trong record giờ chứa `[9,8]`, dù component field `bytes` là final.

**Lỗi thường gặp:** chỉ clone đầu vào `bytes = bytes.clone();` trong compact constructor rồi vẫn dùng accessor mặc định. Khi ấy caller không sửa qua **source cũ** được nữa, nhưng vẫn sửa qua **`packet.bytes()`** được.

Với mảng muốn không cho mutate từ bên ngoài, cần copy ở **cả input và output boundaries**.

## 16. Chương trình 6 — mảng không được bảo vệ bởi record mặc định

Tệp **`ShallowArrayRecordDemo.java`**:

~~~java
import java.util.Arrays;

record Packet(int[] values) {
}

public class ShallowArrayRecordDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};
        Packet packet = new Packet(source);

        System.out.println("initial="
                + Arrays.toString(packet.values()));

        source[0] = 9;
        System.out.println("after source="
                + Arrays.toString(packet.values()));

        packet.values()[1] = 8;
        System.out.println("after accessor="
                + Arrays.toString(source));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ShallowArrayRecordDemo.java
java ShallowArrayRecordDemo
~~~

**Stdout:**

~~~text
initial=[1, 2]
after source=[9, 2]
after accessor=[9, 8]
~~~

Mảng là một object độc lập có mutation operations qua index. `final` bảo đảm record không đổi reference tới mảng khác, nhưng không cấm `packet.values()[0] = ...`.

## 17. Copy đầu vào và đầu ra cho array component

Với một record `SafePacket(byte[] data)`, chiến lược phòng vệ thường là:

~~~java
import java.util.Objects;

record SafePacket(byte[] data) {
    SafePacket {
        data = Objects.requireNonNull(data, "data").clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
~~~

Đây là record hợp lệ. Compact canonical constructor đổi **parameter `data`** sang bản clone; compiler gán component field từ bản clone sau body. Accessor override trả một clone mới, không để caller giữ reference tới array nội bộ.

Nếu không override accessor, chỉ có **input protection**, chưa có **output protection**.

Cần chú ý hai điểm thiết kế:

1. `clone()` với array primitives như `byte[]` sao chép các primitive elements đầy đủ. Với `MutableItem[]`, clone **chỉ sao chép array container**, còn element references vẫn trỏ tới MutableItem cũ.
2. Record-generated `equals`/`hashCode` cho array components **không so nội dung phần tử theo `Arrays.equals`**. Nếu muốn byte arrays có value semantics, cần override `equals`/`hashCode` một cách nhất quán.

## 18. Chương trình 7 — clone hai chiều và equality theo nội dung mảng

Tệp **`SafeBytePacketDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

record SafeBytePacket(byte[] data) {
    SafeBytePacket {
        data = Objects.requireNonNull(data, "data").clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof SafeBytePacket that
                    && Arrays.equals(data, that.data));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(data);
    }
}

public class SafeBytePacketDemo {
    public static void main(String[] args) {
        byte[] source = {1, 2};
        SafeBytePacket first = new SafeBytePacket(source);
        SafeBytePacket second =
                new SafeBytePacket(new byte[] {1, 2});

        source[0] = 9;
        byte[] external = first.data();
        external[1] = 8;

        System.out.println("source="
                + Arrays.toString(source));
        System.out.println("external="
                + Arrays.toString(external));
        System.out.println("record="
                + Arrays.toString(first.data()));
        System.out.println("same content="
                + first.equals(second));
        System.out.println("same hash="
                + (first.hashCode() == second.hashCode()));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SafeBytePacketDemo.java
java SafeBytePacketDemo
~~~

**Stdout:**

~~~text
source=[9, 2]
external=[1, 8]
record=[1, 2]
same content=true
same hash=true
~~~

Chúng ta chủ động override `equals`/`hashCode` để so byte contents, đồng thời bảo vệ mảng nội bộ. Không in `first.toString()` trong demo vì toString mặc định của array component có thể thể hiện array identity, không phải các bytes theo định dạng ổn định. Nếu yêu cầu output ổn định/đẹp, có thể override `toString` có chủ đích.

**Không thể suy** rằng record sinh equality theo nội dung mảng chỉ vì array nằm trong record.

## 19. Record-generated `equals`, `hashCode`, `toString` phụ thuộc components

Record thường được chọn làm **value carrier** vì các methods do compiler sinh dựa trên record components:

~~~java
record Label(java.util.List<String> tags) {
}
~~~

Nếu `tags` là ArrayList mutable:

- `Label.equals` dựa trên giá trị component List; `List.equals` so các elements theo thứ tự.
- `Label.hashCode` phụ thuộc hashCode của List, và hashCode của một List mutable có thể thay đổi khi elements thay đổi.
- `Label.toString` hiển thị thông tin component; phần hiển thị list có thể thay đổi sau mutation.
- Hai record có cùng reference list có thể cùng quan sát một lần mutate, dù record fields vẫn final.

Điều này rất nguy hiểm khi record được dùng làm **key trong HashMap** hoặc element của **HashSet**. Các collections dựa vào hash/equality của key tương đối ổn định trong khi key đang được lưu.

Với một record chứa only immutable value components, những hành vi đó tự nhiên ổn định hơn. Với mutable references, constructor cần bảo đảm trạng thái theo value contract mong muốn.

## 20. Chương trình 8 — equality và hash thay đổi dù field final

Tệp **`MutableRecordEqualityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

record TagKey(List<String> tags) {
}

public class MutableRecordEqualityDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        TagKey key = new TagKey(source);
        TagKey original = new TagKey(List.of("A"));

        int hashBefore = key.hashCode();

        System.out.println("before equal="
                + key.equals(original));

        source.set(0, "B");

        System.out.println("after equal="
                + key.equals(original));
        System.out.println("current=" + key.tags());
        System.out.println("hash changed="
                + (hashBefore != key.hashCode()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 MutableRecordEqualityDemo.java
java MutableRecordEqualityDemo
~~~

**Stdout:**

~~~text
before equal=true
after equal=false
current=[B]
hash changed=true
~~~

Trong demo, `List.of("A")` và `ArrayList` chứa A ban đầu so bằng nhau theo List equality. Sau khi ArrayList bị sửa từ A sang B, record-generated equality thay đổi.

Hash của List có phần phụ thuộc element hash; String `"A"` và `"B"` có hash khác nhau, nên dòng `hash changed=true` có kết quả xác định cho ví dụ này. Không cần in số hash cụ thể hay giả định object allocation layout.

**Hậu quả:** nếu dùng key mutable này làm HashMap key, việc sửa nó sau khi lưu có thể khiến lookup không hoạt động như mong đợi. Cách phòng ngừa là đặt **stable immutable value components** vào keys.

## 21. `List.copyOf` giúp ổn định equality khi phần tử cũng bất biến

Với:

~~~java
record TagKey(java.util.List<String> tags) {
    TagKey {
        tags = java.util.List.copyOf(tags);
    }
}
~~~

component List lúc này là unmodifiable snapshot của input, còn elements là String immutable, nên hash/equality ổn định đối với các operations thông thường trên object graph ấy.

Nếu thay `String` bằng `MutablePart` có `equals`/`hashCode` dựa trên một field mutable, `List.copyOf` **không giải quyết** rủi ro: hash và equality có thể vẫn thay đổi do component elements mutate.

**Nguyên tắc:** muốn record hoạt động như **stable hash key**, mọi dữ liệu mà `equals` và `hashCode` phụ thuộc phải có trạng thái quan sát được ổn định trong thời gian key được lưu.

Đừng cố chữa bằng cách cache hashCode từ lần tạo trong record (record cũng không cho thêm ordinary instance field tùy ý): hash cache không sửa được equality đã bị mutation phá vỡ.

## 22. Nhiều tầng collection: copy từng tầng mutable cần bảo vệ

Một kiểu component phổ biến là:

~~~java
record Permissions(
        java.util.Map<String, java.util.List<String>> roles) {
}
~~~

Nếu chỉ viết `roles = Map.copyOf(roles)`, bạn tạo **map không cho thay đổi cấu trúc**, nhưng các List values có thể vẫn mutable.

Ví dụ:

~~~text
Mutable Map source
    "admin" ----> Mutable List ["READ"]
                     ^
                     |
Map.copyOf(source) giữ cùng List reference cho key "admin"

source.get("admin").add("WRITE") làm record nhìn thấy WRITE.
~~~

Muốn một snapshot ổn định khi map keys và list elements là String immutable, bạn cần copy **mỗi list value** rồi copy **map container**. Đây là phòng vệ theo từng tầng.

Các factory methods `Map.copyOf` và `List.copyOf` từ chối null keys/values/elements theo contract. Hãy kiểm tra đầu vào trước khi xây snapshot nếu cần message ngoại lệ rõ ràng.

## 23. Chương trình 9 — snapshot map của các lists

Tệp **`NestedCollectionSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

record Permissions(Map<String, List<String>> roles) {
    Permissions {
        Objects.requireNonNull(roles, "roles");
        Map<String, List<String>> copy = new HashMap<>();
        for (Map.Entry<String, List<String>> entry
                : roles.entrySet()) {
            copy.put(
                    Objects.requireNonNull(
                            entry.getKey(), "role"),
                    List.copyOf(
                            Objects.requireNonNull(
                                    entry.getValue(), "permissions")));
        }
        roles = Map.copyOf(copy);
    }
}

public class NestedCollectionSnapshotDemo {
    public static void main(String[] args) {
        List<String> admin = new ArrayList<>();
        admin.add("READ");

        Map<String, List<String>> source = new HashMap<>();
        source.put("admin", admin);

        Permissions permissions = new Permissions(source);

        admin.add("WRITE");
        source.put("guest", List.of("READ"));

        System.out.println("source admin="
                + source.get("admin"));
        System.out.println("record admin="
                + permissions.roles().get("admin"));
        System.out.println("record keys="
                + permissions.roles().size());

        try {
            permissions.roles().get("admin").add("DELETE");
        } catch (UnsupportedOperationException ex) {
            System.out.println("list protected=true");
        }

        try {
            permissions.roles().put("guest", List.of("READ"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("map protected=true");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 NestedCollectionSnapshotDemo.java
java NestedCollectionSnapshotDemo
~~~

**Stdout chính xác:**

~~~text
source admin=[READ, WRITE]
record admin=[READ]
record keys=1
list protected=true
map protected=true
~~~

Chương trình dùng `get` và `size` thay vì in toàn bộ HashMap, nên kết quả không phụ thuộc thứ tự iteration của HashMap hay Map.copyOf. Snapshot đã tách cả Map container lẫn List containers khỏi nguồn, đồng thời các String elements là immutable.

Nếu values là `List<MutableUser>`, bạn vẫn cần copy/convert từng MutableUser thành một representation immutable trước khi khẳng định bất biến sâu.

## 24. `Map.copyOf`, `Set.copyOf` và quy tắc dữ liệu

Cách tương ứng cho các kiểu collection:

- `List.copyOf(source)`: unmodifiable snapshot của list structure, bảo toàn thứ tự phần tử, từ chối null elements.
- `Set.copyOf(source)`: unmodifiable set, từ chối null; duplicate elements của input collection được hợp nhất theo Set semantics và không bảo đảm chọn instance duplicate nào nếu chúng equal nhưng khác identity.
- `Map.copyOf(source)`: unmodifiable map, từ chối null keys/values; không hứa iteration order như một LinkedHashMap.
- `Collections.unmodifiableList(source)`: view live của source, không snapshot; giữ alias nếu source mutable.
- `new ArrayList<>(source)`: mutable container copy; đủ tách cấu trúc khỏi source nhưng accessor có thể sửa bản sao nội bộ nếu trả trực tiếp.
- `Collections.unmodifiableList(new ArrayList<>(source))`: unmodifiable view của một copy mới có thể làm snapshot cấu trúc kể cả khi source có null elements; vẫn shallow với mutable elements.

**Không nhầm**:
- Unmodifiable: không thay cấu trúc qua API collection đó.
- Immutable snapshot: cấu trúc/value graph quan sát được không thay đổi theo những aliases được bên ngoài giữ.
- Deep immutable: tất cả reachable mutable state trong phạm vi đã chọn không thể thay đổi qua đường truy cập bên ngoài.

Một collection immutable có thể chứa object mutable; vì vậy từ khóa “immutable” cần luôn nói rõ **tầng nào**.

## 25. Các record components phổ biến và lựa chọn copy

| Component type | Rủi ro chính | Chiến lược hợp lý |
| --- | --- | --- |
| `int`, `long`, `boolean` | Không có mutable object bên dưới | Validation theo domain |
| `String` | String immutable | Null/format validation |
| `BigDecimal` | Immutable class | Kiểm tra scale/rounding theo domain |
| `LocalDate`, `Instant` | Java time immutable values | Validation |
| `List<String>` | Mutable container | `List.copyOf` |
| `List<MutableThing>` | Mutable elements | Convert/copy từng element và collection |
| `Set<String>` | Mutable container | `Set.copyOf` |
| `Map<String,String>` | Mutable container | `Map.copyOf` |
| `Map<String,List<String>>` | Mutable map và nested lists | Copy từng list, rồi copy map |
| `byte[]`, `int[]` | Mutable array cả hai phía | Clone input và accessor; xem equality |
| `Date` (legacy) | Mutable object | Copy ở input và output |
| `AtomicInteger` | Mutable holder thread-safe ở một số phép toán | Đừng gọi đây là immutable value chỉ vì field final |
| Custom DTO có setters | Aliases và state mutation | Immutable DTO/record snapshot với mapping rõ |

Với Java time types, có thể ưu tiên `java.time` thay legacy `java.util.Date` khi API cho phép; nhưng đừng tự chuyển dữ liệu thời gian không có chính sách timezone rõ ràng.

## 26. Legacy `Date`: constructor copy thôi chưa đủ

`java.util.Date` là một mutable class: `setTime(long)` có thể thay đổi timestamp mà Date object biểu diễn.

Nếu record định nghĩa:

~~~java
record Appointment(java.util.Date when) {
}
~~~

thì caller có thể thay `when` qua reference đã truyền vào hoặc lấy reference qua accessor. Điều này tương tự array/list, khác ở methods mutate của Date.

Một dạng phòng vệ:

~~~java
record Appointment(java.util.Date when) {
    Appointment {
        when = new java.util.Date(
                java.util.Objects.requireNonNull(
                        when, "when").getTime());
    }

    @Override
    public java.util.Date when() {
        return new java.util.Date(when.getTime());
    }
}
~~~

Record này tạo bản Date riêng lúc nhận và trả Date mới lúc đọc. Component field vẫn là `Date`, nhưng không có alias mutable từ phía caller đối với Date nội bộ qua hai đường thông thường ấy.

Đối với nhiều bài toán, lưu `Instant` immutable sẽ đơn giản và ít lỗi hơn.

## 27. Chương trình 10 — phòng vệ `Date` ở hai phía

Tệp **`LegacyDateRecordDemo.java`**:

~~~java
import java.util.Date;
import java.util.Objects;

record Appointment(Date when) {
    Appointment {
        when = new Date(
                Objects.requireNonNull(when, "when").getTime());
    }

    @Override
    public Date when() {
        return new Date(when.getTime());
    }
}

public class LegacyDateRecordDemo {
    public static void main(String[] args) {
        Date source = new Date(1_000L);
        Appointment appointment = new Appointment(source);

        source.setTime(2_000L);
        Date external = appointment.when();
        external.setTime(3_000L);

        System.out.println("source=" + source.getTime());
        System.out.println("external=" + external.getTime());
        System.out.println("record="
                + appointment.when().getTime());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LegacyDateRecordDemo.java
java LegacyDateRecordDemo
~~~

**Stdout:**

~~~text
source=2000
external=3000
record=1000
~~~

Dùng `Date.getTime()` (số milliseconds cố định) thay vì in `Date.toString()` để output **không phụ thuộc timezone** của máy.

Constructor và accessor tạo Date mới từ timestamp, tách record khỏi các alias trực tiếp bên ngoài. Tuy nhiên, bản thân record với component Date vẫn không phải mẫu deep immutable tuyệt đối nếu thiết kế có thêm một đường truy cập tới Date nội bộ; dùng immutable `Instant` phù hợp hơn khi có thể.

## 28. Hình thức record tốt nhất đôi khi là đổi kiểu component

Thay vì:

~~~java
record Appointment(java.util.Date when) {
}
~~~

có thể dùng:

~~~java
record Appointment(java.time.Instant when) {
    Appointment {
        java.util.Objects.requireNonNull(when, "when");
    }
}
~~~

Khi chuyển đổi từ Date sang Instant:

~~~java
// Trong method có Date source khác null:
Appointment appointment =
        new Appointment(source.toInstant());
~~~

`Instant` là immutable value type; Date caller bị thay đổi sau đó không làm thay đổi Instant mà record lưu.

Cách này đơn giản hơn duy trì constructor/accessor clones của Date. Nhưng **không phải luôn thay được** nếu API phải trả Date legacy, hoặc nếu domain biểu diễn local calendar date thay vì một instant trên timeline. Chọn `Instant`, `LocalDate`, `LocalDateTime`, `ZonedDateTime` theo đúng semantics thời gian.

**Ưu tiên representation bất biến từ đầu** hơn là bổ sung defensive copying phức tạp ở mọi lối ra vào.

## 29. Record không tự thread-safe

Một hiểu lầm lớn: “record có final fields nên mọi thao tác trên nó thread-safe”.

Ví dụ:

~~~java
record SharedCounter(
        java.util.concurrent.atomic.AtomicInteger value) {
}
~~~

Component field `value` không bị gán lại. Nhưng `AtomicInteger` vẫn chứa **state thay đổi được**. Đây là state được quản lý bởi công cụ atomic, nên một số operations như `incrementAndGet` có thread-safety riêng.

Ngược lại, nếu record chứa `ArrayList` và nhiều threads cùng gọi `add`, việc field List là final **không biến ArrayList thành concurrent collection**. Người đọc vẫn cần phân biệt visibility, atomicity, safe publication và synchronization theo Java Memory Model.

Một record có graph bất biến và được xuất bản hợp lệ thường dễ chia sẻ giữa threads hơn; nhưng **bất biến của component references** không đủ để bảo đảm an toàn cho mọi object reachable.

## 30. Chương trình 11 — final reference tới một counter vẫn mutate

Tệp **`MutableCounterRecordDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

record Metrics(AtomicInteger count) {
}

public class MutableCounterRecordDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Metrics metrics = new Metrics(new AtomicInteger(0));

        Thread a = new Thread(
                () -> metrics.count().incrementAndGet());
        Thread b = new Thread(
                () -> metrics.count().incrementAndGet());

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("count="
                + metrics.count().get());

        metrics.count().incrementAndGet();
        System.out.println("after main="
                + metrics.count().get());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 MutableCounterRecordDemo.java
java MutableCounterRecordDemo
~~~

**Stdout sau khi các threads hoàn tất bình thường:**

~~~text
count=2
after main=3
~~~

`Metrics.count` là private final field, nhưng `AtomicInteger` có thể thay đổi từ 0 đến 2 rồi 3. Giá trị cuối có thể dự đoán trong ví dụ vì `incrementAndGet` là atomic và main gọi `join` trước khi đọc.

**Thread safety của phép tăng** đến từ `AtomicInteger`, không đến từ record. Nếu chỉ cần cấu hình bất biến, không nên đặt một mutable counter làm component rồi gọi record đó là immutable config.

## 31. Các record làm key trong `HashMap`/element trong `HashSet`

Khi dùng record làm key, hãy hỏi:

- Thành phần nào tham gia `equals` và `hashCode`?
- Những thành phần ấy có thể mutate sau khi key được lưu không?
- Copy container đã đủ chưa, hay mutable element vẫn có thể thay đổi hash?
- Accessor có làm lộ mutable object không?
- Có khả năng hai threads đang mutate data mà key còn được tra cứu không?

Một pattern tốt với tag names:

~~~java
record StableTagKey(java.util.List<String> tags) {
    StableTagKey {
        tags = java.util.List.copyOf(tags);
    }
}
~~~

Khi components dùng stable String values và list snapshot, key có value semantics rõ. Với byte arrays, muốn nội dung là identity của key thì cần clone hai chiều và custom `equals`/`hashCode`.

Không sửa mutable object mà record key tham chiếu sau khi thêm vào hash-based collection. Nếu bắt buộc cập nhật nội dung key, **tạo key mới**, xóa key cũ theo đúng API và thêm key mới.

## 32. Bất biến nông không đồng nghĩa serialization snapshot

Record có thể được serialize nếu đáp ứng hợp đồng Serializable và components/object graph tương ứng hỗ trợ. Nhưng **serialization không thay thế defensive copying** cho API thông thường.

Nếu record giữ một List mutable, việc gửi dữ liệu qua serialization có thể quan sát state ở một thời điểm phụ thuộc quá trình đọc graph và concurrency. Không nên trông chờ serialization “đóng băng” một record đang được mutate bởi nơi khác.

Ngoài ra, một component trỏ tới object không serializable có thể làm serialization thất bại, dù record type đã implements Serializable. Cần kiểm tra cả **đồ thị object** thực tế.

Khi cần một message/DTO bền vững qua ranh giới service, nên tạo một **immutable value snapshot** có fields/components với schema rõ trước khi mã hóa hoặc gửi đi, không chỉ dựa vào modifier `record`.

## 33. `toString()` có thể thay đổi khi component mutable

Generated `toString()` được dùng để mô tả component values. Nếu một component là List mutable, phần mô tả list trong output có thể đổi sau mutation, như Chương trình 1.

Điều này ảnh hưởng tới:

- Debug logs: cùng record object nhưng log ở hai thời điểm thể hiện dữ liệu khác.
- Caching: nếu tạo cache key từ `toString()`, kết quả thay đổi không mong muốn.
- Tests: một test có thể qua khi không có mutation nhưng fail khi shared object bị sửa.
- Domain reasoning: người đọc nghĩ record là một immutable event nhưng payload lại biến đổi.

**Không dùng `toString()` làm giao thức lưu trữ hoặc identifier ổn định**. Với arrays, default string representation của array còn không biểu diễn contents như `Arrays.toString`.

Một bản copy ở ranh giới, cộng với immutable component values, giúp toString đáng tin hơn cho mục đích debug; vẫn không thay thế schema serialization chính thức.

## 34. Chọn copy lúc nào và bao nhiêu tầng?

Không phải mọi record cần deep copy toàn bộ object graph. Copying có chi phí bộ nhớ/CPU và đôi khi **phá semantics chia sẻ state có chủ đích**.

Phân loại ba trường hợp:

1. **Value object/snapshot:** caller kỳ vọng record không thay đổi sau construction. Nên dùng immutable types hoặc defensive copy đủ các tầng mutable reachable.
2. **Read-only view của mutable model:** caller kỳ vọng nhìn thấy state mới, nhưng không được sửa qua accessor. Có thể dùng unmodifiable view và tài liệu hóa rằng dữ liệu **sẽ thay đổi theo nguồn**. Khi đó record không deep immutable.
3. **Handle tới service/state holder:** component có thể là `AtomicInteger`, client hay listener, vì mục tiêu là nắm giữ một dependency. Đừng gọi record này là value snapshot; có thể nên dùng class thường để diễn đạt lifecycle/identity.

Một phương án phòng vệ đúng phải bắt đầu từ **hợp đồng API**, chứ không chỉ thêm `copyOf` cơ học.

## 35. Cẩn thận với null và dữ liệu có tính chu kỳ

Các factory copy như `List.copyOf`, `Set.copyOf`, `Map.copyOf` có chính sách **không nhận null elements/keys/values**. Nếu domain cần null, có thể:

- Biểu diễn “không có dữ liệu” bằng `Optional` ở API nơi phù hợp, nhưng cân nhắc sử dụng Optional làm field/component theo style dự án.
- Dùng một giá trị domain explicit như `Unknown`, `Missing`.
- Dùng một bản copy mutable có null được phép, rồi unmodifiable wrapper trên bản copy **không công bố**.
- Validate và reject null sớm với message rõ.

Với các object graphs có **cycles**, “copy sâu tổng quát” không chỉ là gọi `clone` đệ quy; nó còn cần xử lý identity, chu kỳ, chia sẻ aliases và khả năng không copy được external resources. Trong domain model, thường hiệu quả hơn thiết kế representation immutable **không có cycles ngoài ý muốn**, hoặc chuyển thành DTO snapshot với quy tắc mapping rõ.

Không cố deep-copy `Thread`, `Socket`, database connection hay service object chỉ vì một record field trỏ tới chúng: các objects ấy thường có **identity và lifecycle**, không phải value data.

## 36. Chuẩn hóa ở compact constructor không tự biến object graph bất biến

Compact constructor có thể xử lý parameter reference trước khi compiler gán component field:

~~~java
record Report(String title, java.util.List<String> tags) {
    Report {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title");
        }
        title = title.strip();
        tags = java.util.List.copyOf(tags);
    }
}
~~~

Đây là record hợp lệ. Sau khi constructor hoàn thành:

- Component `title` giữ một String đã strip.
- Component `tags` giữ unmodifiable snapshot của List container.
- Các tag elements là Strings, vì vậy object graph được dùng ở đây có value semantics ổn định.
- Caller không thể gán lại `report.title` hoặc `report.tags` vì chúng là private final component fields.

Nếu đổi component `tags` thành List<MutableTag>, `List.copyOf` không còn đủ cho deep immutability. Phải nhận diện chính xác phần nào mutable, tránh suy luận từ riêng cú pháp compact.

## 37. Chương trình 12 — value record có snapshot và normalization

Tệp **`StableReportRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Report(String title, List<String> tags) {
    Report {
        title = Objects.requireNonNull(title, "title").strip();
        if (title.isEmpty()) {
            throw new IllegalArgumentException("blank title");
        }
        tags = List.copyOf(
                Objects.requireNonNull(tags, "tags"));
    }
}

public class StableReportRecordDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("java");

        Report first = new Report("  Tutorial  ", source);

        source.add("mutable");
        Report second =
                new Report("Tutorial", List.of("java"));

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("equal=" + first.equals(second));

        try {
            first.tags().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("protected="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 StableReportRecordDemo.java
java StableReportRecordDemo
~~~

**Stdout:**

~~~text
first=Report[title=Tutorial, tags=[java]]
second=Report[title=Tutorial, tags=[java]]
equal=true
protected=UnsupportedOperationException
~~~

Hai records có cùng giá trị sau normalization và snapshot nên `equals` trả true. Dữ liệu thêm vào source sau khi tạo first không xuất hiện trong first. Accessor của List component trả unmodifiable list, nên mutation trực tiếp bị từ chối.

**Điểm cần nhớ:** chính sách này phù hợp vì String và các tag strings bất biến; ví dụ không đại diện cho một giải pháp universal deep-copy mọi loại object.

## 38. “Bất biến nông” có phải lỗi của record?

Không. **Record thực hiện đúng hợp đồng mà Java thiết kế:** nó cố định tập record components và các field references của object, đồng thời tạo API minh bạch cho việc quan sát dữ liệu.

Một record với `AtomicInteger` hoặc MutableThing component không vi phạm ngôn ngữ. Nó chỉ cần được **đặt tên và tài liệu hóa đúng semantics**.

Lỗi xuất hiện khi người thiết kế hoặc caller suy luận sai:

- Tin rằng `record` giống một cơ chế deep-freeze toàn bộ object graph.
- Đặt `List` mutable làm component mà không defensive copy nhưng công bố API là “immutable value”.
- Dùng record chứa mutable components làm HashMap key ổn định.
- Trả trực tiếp mảng nội bộ qua accessor.
- Dùng unmodifiable view nhưng tưởng đã snapshot.
- Bỏ qua mutable elements sau khi đã copy collection structure.
- Cho nhiều threads dùng cùng mutable state mà nghĩ final field tự đồng bộ writes.

Vì vậy, câu chính xác là **record bảo đảm structural/shallow immutability của các component fields**, còn immutable behavior sâu là **trách nhiệm của kiểu components và thiết kế constructor/accessors**.

## 39. Các sai lầm và cách sửa

| Cách hiểu/lối viết | Vấn đề | Cách làm thích hợp |
| --- | --- | --- |
| `record Box(List<String> items) {}` được xem là hoàn toàn immutable | List caller/ accessor vẫn có thể mutate | `List.copyOf` khi cần value snapshot |
| Chỉ dùng `final List<String>` | Final chỉ khóa reference | Copy/wrap collection theo contract |
| `Collections.unmodifiableList(source)` nghĩa là snapshot | View vẫn thấy mutations của source | `List.copyOf` hoặc wrapper của copy riêng |
| `List.copyOf(List<MutableItem>)` là deep copy | Mutable elements còn aliased | Copy/convert từng element |
| Clone array trong constructor nhưng không override accessor | Caller sửa array nội bộ qua getter | Override accessor trả clone |
| Clone `MutableItem[]` được coi là deep copy | Clone chỉ array container | Clone/convert từng element |
| Record-generated equals tự so array contents | Array component equality thường theo identity | Override equals/hashCode hoặc đổi representation |
| Record key chứa ArrayList được sửa sau `put` | Hash/equality có thể đổi | Stable immutable key |
| `Map.copyOf` bảo vệ mọi nested lists | Map snapshot chỉ một tầng | Copy từng list và map |
| Unmodifiable collection nghĩa là mutable value objects bị khóa | Không có cơ chế deep freeze | Immutable element types |
| Record có AtomicInteger là immutable value | Counter state vẫn mutable | Mô tả đây là state holder, không phải value snapshot |
| Record có final references nên thread-safe | Mutable objects vẫn có race | Concurrency controls riêng |
| Dựa `Date.toString` làm output ổn định | Có thể phụ thuộc timezone | Dùng timestamps/Instant theo domain |
| Deep-copy mọi dependency | Copy service/resources sai semantics | Phân biệt value với handle/lifecycle |
| Sao chép trong khi source bị sửa đồng thời không đồng bộ | Snapshot có thể không nhất quán | Đồng bộ/source snapshot policy |
| Nghĩ record luôn thích hợp làm entity mutable | Record nhấn mạnh value carrier | Xem xét class thường cho mutable identity entity |

## 40. Quy trình kiểm tra một record có bất biến sâu không

Khi đọc record bất kỳ, hãy đi theo các bước:

1. Liệt kê tất cả **record components** và types của chúng.
2. Đánh dấu components dạng **primitive/immutable value** và dạng **reference tới mutable type**.
3. Xác định **caller có còn giữ input aliases** không.
4. Đọc canonical constructor: có defensive copies/normalization không?
5. Nếu copy, xác định copy **ở tầng container hay cả elements**.
6. Đọc component accessors: mặc định trả reference hay đã được override để trả copy?
7. Tìm đường mutation qua nested objects: `get(0).set...`, arrays, dates, maps of lists.
8. Xem generated/custom `equals` và `hashCode` đang dựa vào dữ liệu có thể đổi hay không.
9. Nếu object dùng làm HashMap key/Set element, đánh giá **ổn định hash**.
10. Nếu chia sẻ giữa threads, phân tích synchronization và publication.
11. Nếu API hứa snapshot, kiểm thử “sửa nguồn sau construction”.
12. Nếu API hứa không cho sửa qua accessor, thử mutation từ accessor.
13. Nếu elements mutable, kiểm thử “sửa element gốc sau snapshot”.
14. Nếu có arrays, kiểm thử cả input và output clones, equality theo nội dung.
15. Ghi rõ contract null/duplicate/order/lifecycle của collection components.

Bạn có thể kết luận “bất biến sâu” chỉ **trong phạm vi object graph đã xác định** và sau khi không còn đường mutation khả dụng trong phạm vi ấy; không thể chỉ dựa vào keyword `record`.

## 41. Bài tập tự luyện

**Câu 1.** `record Point(int x,int y) {}` có những nguy cơ mutable reference thông thường giống `record Box(List<String> items) {}` không?

**Câu 2.** Nếu record có component `final List<String>`, tại sao `items.add("A")` vẫn có thể hợp lệ?

**Câu 3.** Khác biệt giữa sửa `record.items` và sửa `record.items().add(...)` là gì?

**Câu 4.** Vì sao caller sửa ArrayList sau khi truyền vào record làm record đổi dữ liệu quan sát được?

**Câu 5.** Accessor mặc định của List component có trả defensive copy không?

**Câu 6.** `List.copyOf(source)` khác `Collections.unmodifiableList(source)` ra sao?

**Câu 7.** Nếu domain cho phép null list elements, có thể dùng `List.copyOf` trực tiếp không?

**Câu 8.** `List.copyOf(List<MutableItem>)` có clone MutableItem không?

**Câu 9.** Muốn list members ổn định khi source elements mutable, một chiến lược thích hợp là gì?

**Câu 10.** Nếu component là `byte[]`, constructor clone input đã đủ chưa?

**Câu 11.** Với `byte[]`, accessor cần làm gì để ngăn caller sửa array nội bộ?

**Câu 12.** Generated `equals` của record có byte[] components có mặc định gọi `Arrays.equals` không?

**Câu 13.** Nếu muốn BytePacket so bytes theo giá trị, bạn cần override các methods nào cho nhất quán?

**Câu 14.** Một record chứa List mutable, record-generated hashCode có thể thay đổi theo thời gian không?

**Câu 15.** Tại sao dùng record có mutable components làm HashMap key có thể không an toàn?

**Câu 16.** `Map.copyOf(Map<String,List<String>>)` đã khóa các List values chưa?

**Câu 17.** Làm thế nào snapshot cả Map và các List values khi elements là String?

**Câu 18.** `Date` có bất biến như `Instant` không?

**Câu 19.** Nếu record chứa Date legacy, cần bảo vệ ở những ranh giới nào?

**Câu 20.** Record chứa AtomicInteger có thể mutate được không? Thao tác atomic là do đâu?

**Câu 21.** Một unmodifiable view có phải luôn không thay đổi theo thời gian không?

**Câu 22.** Vì sao không nên dùng `record.toString()` làm stable persisted key?

**Câu 23.** Khi nào “deep copy mọi thứ” là một quyết định sai?

**Câu 24.** Nếu source List bị sửa đồng thời khi constructor đang copy, `List.copyOf` tự tạo transactional snapshot không?

**Câu 25.** Vì sao record không tự thread-safe khi component giữ ArrayList?

**Câu 26.** Nếu component list là `List<String>` và đã dùng List.copyOf, tại sao tình huống đơn giản này thường đủ an toàn làm value snapshot?

### Đáp án và giải thích

1. Không. Hai primitive components không tham chiếu tới mutable object.
2. `final` khóa component reference, không khóa List object.
3. Gán lại component field bị cấm; gọi method mutate trên object được tham chiếu vẫn có thể hợp lệ.
4. Record và caller cùng trỏ tới một List object (*aliasing*).
5. Không; default accessor trả component value, tức reference nếu component là reference type.
6. List.copyOf tạo unmodifiable snapshot cấu trúc; unmodifiableList(source) là view live.
7. Không; List.copyOf từ chối null elements. Cần copy/wrapper khác nếu domain chấp nhận null.
8. Không; chỉ copy list structure/references.
9. Chuyển MutableItem sang immutable value type riêng rồi snapshot collection.
10. Chưa; accessor mặc định vẫn trả reference array nội bộ.
11. Override accessor trả clone/defensive copy.
12. Không; arrays có equality theo identity mặc định.
13. `equals` và `hashCode` dùng `Arrays.equals`/`Arrays.hashCode`; xem toString nếu cần format ổn định.
14. Có; List.hashCode có thể đổi khi contents đổi.
15. Hash-based lookup giả định key hash/equality phù hợp theo thời gian key được lưu.
16. Chưa; List values vẫn có thể mutable.
17. Copy từng List bằng List.copyOf, rồi Map.copyOf của map mới.
18. Không; Date mutable, Instant immutable.
19. Copy input và copy output accessor; hoặc đổi sang representation immutable.
20. Có; AtomicInteger state thay đổi, tính atomic đến từ API AtomicInteger chứ không từ record.
21. Không. View có thể phản ánh những thay đổi của mutable backing collection.
22. Output có thể thay đổi do mutable components và không phải schema dữ liệu bền vững.
23. Khi components là service/resource handles hoặc code cần chia sẻ identity/lifecycle có chủ đích.
24. Không; cần chính sách đồng bộ hoặc nguồn dữ liệu bảo đảm nhất quán.
25. Final reference không đồng bộ các thao tác trên ArrayList.
26. Strings immutable, list đã snapshot/unmodifiable nên cấu trúc và contents trong graph ấy không đổi theo các mutations thông thường từ bên ngoài.

## 42. Checklist trước khi công bố record như một immutable value

- [ ] Mọi components đã được liệt kê và phân loại mutable/immutable?
- [ ] Có hiểu `record` chỉ tự bảo đảm private final component fields?
- [ ] Nếu có List mutable đầu vào, constructor tạo snapshot phù hợp?
- [ ] Nếu dùng unmodifiable wrapper, đã tách backing mutable collection khi cần?
- [ ] Nếu có mutable elements, đã chuyển đổi hoặc defensive-copy elements?
- [ ] Nếu có nested map/list, đã copy tất cả container levels cần bảo vệ?
- [ ] Nếu có arrays, đã clone ở đầu vào và tại accessor?
- [ ] Với array value semantics, đã làm `equals`/`hashCode` nhất quán?
- [ ] Với Date legacy, đã copy hai chiều hoặc dùng Java time immutable type?
- [ ] Các factory copy có tuân null/duplicate/order policy của domain?
- [ ] Các component types là immutable thì không copy vô ích?
- [ ] Generated equality và hashCode có ổn định khi record dùng làm key?
- [ ] Đã xác định sẽ có hay không chia sẻ mutable state có chủ đích?
- [ ] Nếu có multi-thread access, đã phân tích concurrency riêng?
- [ ] Không ngầm gọi unmodifiable view là independent snapshot?
- [ ] Không gọi shallow copy là deep copy?
- [ ] Nếu API hứa value object, test thay đổi input sau construction?
- [ ] Test caller cố thay đổi dữ liệu qua accessor?
- [ ] Test thay đổi mutable element gốc?
- [ ] Đã xác định lifecycle/ownership với dependencies không thể copy?
- [ ] Có tài liệu hóa ranh giới bất biến của object graph?
- [ ] Không dựa vào `toString()` làm serial format hoặc business key?

## 43. Tài liệu Java 17 chính thức

- [JLS 17 §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): đặc điểm của record, components và accessors.
- [JLS 17 §8.10.1 — Record Components](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.1): record header và component declarations.
- [JLS 17 §8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): private final fields, accessors, `equals`/`hashCode`/`toString`.
- [JLS 17 §8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): compact canonical constructor và chuẩn hóa/copy input.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): `final` và ý nghĩa cấm gán lại biến.
- [Java SE 17 — Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): hợp đồng cơ bản của record.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable list và null policy.
- [Java SE 17 — Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): copy thành set không sửa cấu trúc.
- [Java SE 17 — Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): unmodifiable map copy.
- [Java SE 17 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable view của list.
- [Java SE 17 — Arrays.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#equals(byte[],byte[])): so array contents.
- [Java SE 17 — Arrays.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#hashCode(byte[])): hash array contents.
- [Java SE 17 — Date](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Date.html): mutable legacy time type.
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): immutable timestamp.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic mutable state.

## 44. Tổng kết

**Record không tự bảo đảm bất biến sâu.** Java cố định tập component fields và không cho gán lại các fields đã khởi tạo, nhưng một component `List`, `Map`, array, `Date` hoặc một DTO mutable vẫn có thể thay đổi thông qua aliases ở bên ngoài. Accessors mặc định có thể làm lộ những references ấy.

Khi xây record có **value semantics ổn định**:

1. **Chọn immutable component types** nếu có thể.
2. Với `List<String>`, dùng `List.copyOf` trong canonical constructor để có unmodifiable structural snapshot.
3. Với mutable elements, **copy/convert từng element**; copy list container một mình chưa đủ.
4. Với arrays và Date legacy, bảo vệ **cả chiều vào và chiều ra**, không chỉ clone input.
5. Với nested collections, copy **các tầng cần bảo vệ** và xem xét null/duplicate/order policy.
6. Khi dùng records làm keys, bảo đảm những dữ liệu tham gia `equals`/`hashCode` không đổi.
7. Khi có concurrency, dùng đúng synchronization/concurrent APIs; `final` không tự làm mutable objects thread-safe.

**Tính bất biến sâu là một quyết định thiết kế của toàn bộ object graph**, không phải một hiệu ứng tự động từ từ khóa `record`. Biết phân biệt shallow và deep immutability giúp bạn chọn đúng constructor, accessor, kiểu dữ liệu, chiến lược defensive copy và hợp đồng API.
