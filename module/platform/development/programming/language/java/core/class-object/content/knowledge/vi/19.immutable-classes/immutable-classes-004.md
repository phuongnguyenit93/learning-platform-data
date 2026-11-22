# Kiểm soát kế thừa để bảo vệ cam kết bất biến trong Java

Một **đối tượng bất biến (immutable object)** là đối tượng có trạng thái quan sát được không thay đổi sau khi được xây dựng thành công, theo một hợp đồng rõ ràng. Trong Java, khai báo trường `private final` là một yếu tố quan trọng, **nhưng không đủ** để đảm bảo rằng mọi đối tượng của một kiểu — đặc biệt các **subclasses** — luôn bất biến.

Ví dụ:

~~~java
class Value {
    private final int amount;

    Value(int amount) {
        this.amount = amount;
    }

    public int amount() {
        return amount;
    }
}
~~~

`Value` giữ `amount` trong field final. Tuy nhiên vì class **không final**, một subclass có thể thêm state mutable hoặc override `amount()` để kết quả thay đổi theo thời gian. Vì vậy không thể khẳng định chắc chắn rằng “mọi đối tượng được nhìn qua kiểu Value đều bất biến” chỉ từ việc thấy một field final ở class cha.

Để **bảo vệ cam kết bất biến qua ranh giới kế thừa**, cần lựa chọn chiến lược: **cấm kế thừa** bằng `final class`; hoặc **kiểm soát chặt toàn bộ hierarchy** bằng sealed types, protected/final API, constructors và kiểm tra từng subtype; hoặc **ưu tiên composition** thay cho subclassing khi muốn mở rộng hành vi.

Bài viết thuộc **Java Core — Class & Object / Lớp bất biến**, dùng **Java 17+**. Những chương trình đầy đủ có tên file, lệnh `javac`/`java` và stdout để tự đối chiếu. Mã minh họa không đầy đủ được ghi rõ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **immutable object**, **immutable class**, **immutability contract** và một **immutable view**.
2. Giải thích `final field` khác `final class` và `final method`.
3. Chỉ ra vì sao **cho phép kế thừa tùy ý** làm suy yếu lời hứa “mọi instance của kiểu này bất biến”.
4. Viết class bất biến không thể bị subclass với `public final class`.
5. Biết rằng `final class` vẫn cần validation, defensive copying và tránh lộ mutable state.
6. Phát hiện một subclass có thể override getter để làm hành vi quan sát được thay đổi.
7. Hiểu việc thêm mutable fields vào subclass vẫn hợp lệ nếu superclass không final.
8. Phân biệt phần state bất biến của superclass với **tính bất biến của toàn object**.
9. Dùng `final method` để cố định hành vi quan trọng, và hiểu giới hạn của nó.
10. Nhận diện nguy cơ **gọi overridable method trong constructor**.
11. Biết tại sao không được publish `this` khi object chưa xây dựng xong.
12. Phân biệt **defensive copy**, **unmodifiable live view**, **shallow snapshot** và **deep immutability**.
13. Sử dụng những immutable element/value types thích hợp trong collections.
14. Hiểu vai trò của `record`, `sealed class/interface` và subclass permissions trong Java 17.
15. Biết sealed hierarchy **không tự làm mọi permitted subtype bất biến**.
16. Ưu tiên composition, interface và immutable snapshots nếu cần đa dạng hành vi.
17. Thiết kế constructor/factory không tự làm mất invariant.
18. Hiểu rủi ro inheritance đối với `equals`, `hashCode` và stable value semantics.
19. Đánh giá tính an toàn khi sử dụng objects giữa threads.
20. Viết các test chứng minh hành vi và state vẫn ổn định sau các attempts thay đổi từ bên ngoài.

## 2. “Bất biến” là một cam kết hành vi, không chỉ một modifier

Một immutable type nên có hợp đồng tương tự:

> Sau khi constructor/factory trả về thành công, trạng thái logic quan sát được của đối tượng này không bị sửa bởi những thao tác được API cung cấp hoặc bởi aliases tới mutable state mà nó nắm giữ.

Các thuộc tính thường cần:

- Không có phương thức thay đổi state đã xây dựng.
- Những fields cốt lõi được thiết lập đầy đủ trong constructor, thường là `private final`.
- Không xuất bản trực tiếp tham chiếu tới mutable internal state.
- Dữ liệu mutable nhận vào được **copy hoặc chuyển đổi thành immutable representation**.
- Nếu chứa nested objects, nested state cũng được kiểm soát theo hợp đồng.
- Không cho subclasses phá hợp đồng qua extra mutable state, method overrides hoặc constructor hooks.
- Object được xây dựng đầy đủ trước khi chia sẻ cho code khác, không để `this` escape.

“Bất biến” có thể là **bất biến sâu** (toàn bộ object graph mà API quan sát cũng ổn định) hoặc **bất biến nông** (reference fields không bị gán lại nhưng target object vẫn mutable). Phải nói rõ cấp độ, không dùng `final` như bằng chứng duy nhất.

### Một ví dụ dễ sai

~~~java
final class BadContainer {
    private final java.util.List<String> items;

    BadContainer(java.util.List<String> items) {
        this.items = items;
    }

    java.util.List<String> items() {
        return items;
    }
}
~~~

Class `final` cấm subclass, nhưng caller giữ `items` có thể `add/remove` và getter trả cùng mutable List. **Final class vẫn không đủ**.

## 3. Ba loại `final` cần phân biệt

| Cú pháp | Bảo đảm trực tiếp | Không tự bảo đảm |
| --- | --- | --- |
| `private final int count` | Field gán đúng theo quy tắc rồi không reassign | Những inherited/overridden methods ổn định |
| `private final List<T> values` | Reference field không gán lại | List hoặc elements bất biến |
| `public final class Money` | Không thể có subclass của Money | Fields/reference graph không bị mutate |
| `public final int amount()` | Subclass không thể override method | Subclass không có mutable fields/methods khác |
| `final localVariable` | Biến local không được gán lại | Object mà local giữ reference trở nên immutable |

**Final ở class** và **final ở field** phục vụ hai chiều của hợp đồng:

1. `final class` đóng **khả năng mở rộng theo kế thừa**.
2. `final fields` hạn chế **thay đổi những tham chiếu/giá trị được lưu**.
3. Defensive copying và API design bảo vệ **state nằm sau các tham chiếu**.

Một thiết kế immutable robust thường dùng nhiều yếu tố cùng lúc.

## 4. Vì sao subclass khiến hợp đồng “mọi Value đều bất biến” có thể sai?

Class cha:

~~~java
class BaseValue {
    private final int amount;

    BaseValue(int amount) {
        this.amount = amount;
    }

    public int amount() {
        return amount;
    }
}
~~~

Một subclass có thể làm hai điều:

- Thêm field mutable, khiến **toàn bộ object** chứa state thay đổi được.
- Override `amount()`, khiến behavior mà caller quan sát qua kiểu BaseValue biến đổi.

~~~java
class MutableValue extends BaseValue {
    private int current;

    MutableValue(int original) {
        super(original);
        current = original;
    }

    public void change(int next) {
        current = next;
    }

    @Override
    public int amount() {
        return current;
    }
}
~~~

Dù `BaseValue.amount` là private final, method `amount()` không final, nên subclass được quyền override. Caller thấy `BaseValue reference = new MutableValue(5)` và nhận amount thay đổi từ 5 sang 9.

### Chương trình chạy: phá cam kết qua override

Tạo **`MutableSubclassDemo.java`**:

~~~java
public class MutableSubclassDemo {
    static class BaseValue {
        private final int original;

        BaseValue(int original) {
            this.original = original;
        }

        public int amount() {
            return original;
        }
    }

    static final class MutableValue extends BaseValue {
        private int current;

        MutableValue(int original) {
            super(original);
            current = original;
        }

        void change(int next) {
            current = next;
        }

        @Override
        public int amount() {
            return current;
        }
    }

    public static void main(String[] args) {
        MutableValue concrete = new MutableValue(5);
        BaseValue abstractView = concrete;

        System.out.println("before=" + abstractView.amount());
        concrete.change(9);
        System.out.println("after=" + abstractView.amount());
    }
}
~~~

~~~bash
javac -encoding UTF-8 MutableSubclassDemo.java
java MutableSubclassDemo
~~~

Stdout:

~~~text
before=5
after=9
~~~

**Ý nghĩa:** Superclass chỉ bảo vệ private final field `original`, không bảo vệ contract rằng kết quả `amount()` của **mọi subclasses** luôn ổn định.

## 5. Mutable subclass có thể không override bất cứ method nào

Ví dụ:

~~~java
class ImmutableCore {
    private final int core;

    ImmutableCore(int core) {
        this.core = core;
    }

    public final int core() {
        return core;
    }
}

class MutableExtension extends ImmutableCore {
    private int counter;

    MutableExtension(int core) {
        super(core);
    }

    void increment() {
        counter++;
    }

    int counter() {
        return counter;
    }
}
~~~

`ImmutableCore.core()` luôn ổn định trong mọi subclass nhờ `final` method và private final field. Nhưng một `MutableExtension` object **không bất biến toàn bộ** vì `counter` thay đổi.

### Hai phát biểu rất khác

- **Đúng trong ví dụ:** “Giá trị `core()` thuộc API của ImmutableCore không thay đổi qua những operations thông thường.”
- **Không đúng:** “Bất kỳ object nào extends ImmutableCore đều bất biến.”

Nếu tài liệu của superclass chỉ cam kết **phần state riêng của nó** không thay đổi, hierarchy còn có thể hợp lý. Nhưng nếu public contract tuyên bố **mọi instance của loại này là một value object bất biến hoàn toàn**, hãy kiểm soát các subclasses.

## 6. Cách đơn giản nhất: `final class`

Với value object không cần subclassing:

~~~java
public final class Money {
    private final long cents;

    public Money(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("negative money");
        }
        this.cents = cents;
    }

    public long cents() {
        return cents;
    }

    public Money plus(Money other) {
        java.util.Objects.requireNonNull(other, "other");
        return new Money(Math.addExact(cents, other.cents));
    }
}
~~~

`final class` có nghĩa code Java thông thường không thể khai báo `class SpecialMoney extends Money`. Điều đó **đóng đường subclass thêm mutable fields hoặc override methods**.

Đối với immutable value object, các operations như `plus` tạo **đối tượng mới**, không sửa trạng thái của receiver.

### Ví dụ chạy đầy đủ

Tạo **`FinalMoneyDemo.java`**:

~~~java
import java.util.Objects;

public class FinalMoneyDemo {
    static final class Money {
        private final long cents;

        Money(long cents) {
            if (cents < 0) {
                throw new IllegalArgumentException("negative amount");
            }
            this.cents = cents;
        }

        long cents() {
            return cents;
        }

        Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            return new Money(Math.addExact(cents, other.cents));
        }
    }

    public static void main(String[] args) {
        Money first = new Money(125);
        Money second = new Money(75);
        Money total = first.plus(second);

        System.out.println("first=" + first.cents());
        System.out.println("second=" + second.cents());
        System.out.println("total=" + total.cents());
        System.out.println("same object=" + (first == total));

        try {
            new Money(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinalMoneyDemo.java
java FinalMoneyDemo
~~~

Stdout:

~~~text
first=125
second=75
total=200
same object=false
rejected=negative amount
~~~

`Money` không thể bị subclass; state cents là private final, constructor validation từ chối giá trị âm, và plus trả một Money mới. `Math.addExact` phát hiện overflow thay vì lặng lẽ wrap số.

**Giới hạn:** Ví dụ chỉ mô hình hóa một đơn vị “cents” giả định và không mang currency. Trong phần mềm tài chính thật phải biểu diễn tiền tệ, scale, rounding và quy tắc domain phù hợp. Bất biến không tự đồng nghĩa mô hình nghiệp vụ hoàn chỉnh.

## 7. `final class` không đóng băng mutable fields

Ngay cả khi class bị khóa kế thừa, code sau không an toàn:

~~~java
final class CalendarState {
    private final java.util.Date date;

    CalendarState(java.util.Date date) {
        this.date = date;
    }

    java.util.Date date() {
        return date;
    }
}
~~~

`Date` mutable. Caller có thể sửa object được truyền vào sau khi constructor chạy; hoặc gọi getter lấy cùng Date reference rồi sửa nó. `final` chỉ đóng băng **reference field**, không đóng băng object được tham chiếu.

### Defensive copy từ cả hai phía

~~~java
final class CalendarState {
    private final java.util.Date date;

    CalendarState(java.util.Date supplied) {
        java.util.Objects.requireNonNull(supplied);
        this.date = new java.util.Date(supplied.getTime());
    }

    java.util.Date date() {
        return new java.util.Date(date.getTime());
    }
}
~~~

Copy ở **đầu vào** chống sửa alias đã được caller giữ. Copy ở **đầu ra** chống sửa trực tiếp internal state thông qua getter.

Với API Java hiện đại, `java.time.Instant`, `LocalDate` hoặc các immutable time types thường dễ quản lý hơn mutable `Date`, nếu phù hợp bài toán. Hãy dùng value types có contract rõ để giảm nhu cầu defensive copy.

## 8. Ví dụ chạy: defensive copy mảng trong final class

Tạo **`SafeBytesDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class SafeBytesDemo {
    static final class SafeBytes {
        private final byte[] data;

        SafeBytes(byte[] source) {
            Objects.requireNonNull(source, "source");
            this.data = source.clone();
        }

        byte[] toArray() {
            return data.clone();
        }

        int size() {
            return data.length;
        }
    }

    public static void main(String[] args) {
        byte[] source = {1, 2, 3};
        SafeBytes bytes = new SafeBytes(source);

        source[0] = 9;
        byte[] copy = bytes.toArray();
        copy[1] = 8;

        System.out.println("source=" + Arrays.toString(source));
        System.out.println("copy=" + Arrays.toString(copy));
        System.out.println("stored=" +
                Arrays.toString(bytes.toArray()));
        System.out.println("size=" + bytes.size());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeBytesDemo.java
java SafeBytesDemo
~~~

Stdout:

~~~text
source=[9, 2, 3]
copy=[1, 8, 3]
stored=[1, 2, 3]
size=3
~~~

Mảng được clone ở đầu vào/đầu ra nên người giữ references bên ngoài không thể đổi internal bytes bằng cách sửa source hoặc copy returned. `SafeBytes` là final và không cung cấp mutator, tạo một hợp đồng bất biến rõ.

Với array của mutable **reference elements**, `clone()` chỉ shallow copy array structure; phải xem từng element có immutable không hoặc cần deep defensive representation.

## 9. `private` và `final` cần đi cùng kiểm soát API

Ba nguyên tắc:

1. **`private`** hạn chế caller/subclass sửa trực tiếp fields qua source-level access thông thường.
2. **`final`** khiến field không thể reassign sau initialization theo Java rules.
3. **API không trả mutable internals** và không cho methods thay đổi trạng thái logic.

Ví dụ sai:

~~~java
public final class UnsafeRoster {
    private final java.util.List<String> names;

    public UnsafeRoster(java.util.List<String> names) {
        this.names = names;
    }

    public java.util.List<String> names() {
        return names;
    }
}
~~~

`names` reference final, class final, nhưng List bên trong mutable và bị expose.

### Dùng immutable snapshot

~~~java
public final class Roster {
    private final java.util.List<String> names;

    public Roster(java.util.List<String> names) {
        this.names = java.util.List.copyOf(names);
    }

    public java.util.List<String> names() {
        return names;
    }
}
~~~

`List.copyOf` bảo vệ collection structure và từ chối null elements; String immutable nên các elements trong ví dụ là value objects phù hợp. Nếu elements mutable, chỉ copy structure không đủ để bảo đảm deep immutability.

## 10. Ví dụ chạy: `List.copyOf` ngăn mutation qua aliases

Tạo **`ImmutableRosterDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ImmutableRosterDemo {
    static final class Roster {
        private final List<String> names;

        Roster(List<String> source) {
            names = List.copyOf(source);
        }

        List<String> names() {
            return names;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Mai");

        Roster roster = new Roster(input);
        input.add("An");

        System.out.println("input=" + input);
        System.out.println("roster=" + roster.names());

        try {
            roster.names().add("Binh");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot mutate roster list");
        }

        System.out.println("roster again=" + roster.names());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableRosterDemo.java
java ImmutableRosterDemo
~~~

Stdout:

~~~text
input=[Mai, An]
roster=[Mai]
cannot mutate roster list
roster again=[Mai]
~~~

Input List thay đổi sau constructor nhưng snapshot trong Roster không thay đổi. Getter trả một unmodifiable List. Vì element type là String, không còn đường thay state từng name.

**Chú ý:** `Collections.unmodifiableList(source)` thường tạo unmodifiable **view** trên List nguồn: không thêm qua view được nhưng nếu nguồn bị sửa, view vẫn phản ánh thay đổi. `List.copyOf(source)` tạo cấu trúc snapshot tách khỏi mutable source (theo contract). Hai cơ chế khác nhau.

## 11. Shallow immutability: mutable elements vẫn có thể thay đổi

Giả sử giữ `List<Member>`, trong đó Member có method `rename`:

~~~java
final class Group {
    private final java.util.List<Member> members;

    Group(java.util.List<Member> members) {
        this.members = java.util.List.copyOf(members);
    }

    java.util.List<Member> members() {
        return members;
    }
}
~~~

List không bị thêm/xóa, nhưng caller có thể sửa Member object đã cung cấp. `List.copyOf` không clone Members.

### Chương trình chạy chứng minh lỗi

Tạo **`ShallowImmutableDemo.java`**:

~~~java
import java.util.List;

public class ShallowImmutableDemo {
    static final class Member {
        private String name;

        Member(String name) {
            this.name = name;
        }

        void rename(String next) {
            name = next;
        }

        String name() {
            return name;
        }
    }

    static final class Group {
        private final List<Member> members;

        Group(List<Member> source) {
            members = List.copyOf(source);
        }

        String firstName() {
            return members.get(0).name();
        }
    }

    public static void main(String[] args) {
        Member member = new Member("Mai");
        Group group = new Group(List.of(member));

        System.out.println("before=" + group.firstName());
        member.rename("An");
        System.out.println("after=" + group.firstName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShallowImmutableDemo.java
java ShallowImmutableDemo
~~~

Stdout:

~~~text
before=Mai
after=An
~~~

Class Group final, field members final, List.copyOf unmodifiable, nhưng **observable state** qua `firstName()` thay đổi. Đây là lý do khi nói “bảo vệ cam kết bất biến” phải xét **object graph** chứ không chỉ field modifiers hoặc việc cấm subclassing.

## 12. Chuyển mutable elements thành immutable snapshots

Giải pháp: chuyển dữ liệu mutable sang immutable value type khi xây dựng object.

~~~java
record MemberSnapshot(String name) {
    MemberSnapshot {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
    }
}
~~~

Thay vì lưu `Member` mutable, Group lưu `List<MemberSnapshot>` được tạo từ trạng thái của Members ở thời điểm constructor.

### Ví dụ chạy

Tạo **`DeepSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DeepSnapshotDemo {
    static final class MutableMember {
        private String name;

        MutableMember(String name) {
            this.name = name;
        }

        void rename(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    record MemberSnapshot(String name) {}

    static final class Group {
        private final List<MemberSnapshot> members;

        Group(List<MutableMember> source) {
            List<MemberSnapshot> snapshots = new ArrayList<>();
            for (MutableMember member : source) {
                snapshots.add(new MemberSnapshot(member.name()));
            }
            members = List.copyOf(snapshots);
        }

        String firstName() {
            return members.get(0).name();
        }
    }

    public static void main(String[] args) {
        MutableMember member = new MutableMember("Mai");
        Group group = new Group(List.of(member));

        System.out.println("before=" + group.firstName());
        member.rename("An");
        System.out.println("after=" + group.firstName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DeepSnapshotDemo.java
java DeepSnapshotDemo
~~~

Stdout:

~~~text
before=Mai
after=Mai
~~~

Group lưu **bản chụp giá trị String** từ nguồn. Sửa mutable Member gốc không ảnh hưởng snapshot. Với object graph phức tạp hoặc cyclic, “deep copy” đòi thiết kế có chủ đích; ở đây ví dụ đã chuyển thành **immutable representation** nhỏ, không giả vờ rằng mọi objects có thể clone tự động.

## 13. Kế thừa làm mở rộng đường thay đổi trạng thái

Khi class không final, người viết superclass không kiểm soát toàn bộ state mà subclasses có thể khai báo:

~~~java
class StableBase {
    private final int base;

    StableBase(int base) {
        this.base = base;
    }

    public final int base() {
        return base;
    }
}
~~~

Một subclass được phép:

~~~java
class MutableChild extends StableBase {
    private int revision;

    MutableChild(int base) {
        super(base);
    }

    void advance() {
        revision++;
    }

    int revision() {
        return revision;
    }
}
~~~

Superclass không thể cấm mọi state mới trong arbitrary subclasses chỉ bằng cách đặt các fields của nó private final. `final int base()` vẫn đảm bảo method base không bị override, nhưng **không đảm bảo object MutableChild immutable toàn bộ**.

### Hợp đồng phải nói rõ mức độ

Nếu thư viện muốn “**`StableBase.base()` luôn ổn định**”, thiết kế này có thể hợp lý.

Nếu thư viện muốn “**mọi đối tượng `StableBase` là immutable value object**”, thiết kế mở subclassing tùy ý không chứng minh lời hứa đó.

Nên chọn **final class** cho concrete immutable value object trừ khi có lý do rõ để hỗ trợ hierarchy.

## 14. `final method` giúp bảo vệ invariant nhưng không đóng hierarchy

Giả sử:

~~~java
class AccountView {
    private final String id;

    AccountView(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    public final String id() {
        return id;
    }
}
~~~

Subclass không được override `id()`, nên mọi lời gọi method đó dùng body của AccountView. Nhưng subclass vẫn có thể thêm mutable state:

~~~java
class RichAccountView extends AccountView {
    private int refreshCount;

    RichAccountView(String id) {
        super(id);
    }

    void refresh() {
        refreshCount++;
    }
}
~~~

**Kết luận chính xác:** final method bảo vệ **một đường quan sát/hành vi**. Nó không biến mọi subclass thành immutable.

### Khi nào vẫn nên dùng final methods?

- Bảo vệ một method kiểm tra invariant nội bộ của base class.
- Ngăn subclasses thay đổi semantics bảo mật hoặc consistency của operation.
- Khi framework chủ ý cho extension hooks nhưng **khóa những operations quan trọng**.

Tuy nhiên cần xem các methods khác có gọi overridable hooks không; nếu có, hành vi tổng thể có thể vẫn phụ thuộc mutable subclass.

## 15. Method override có thể làm “getter” mất ổn định

Một subclass có thể override method mà caller tưởng chỉ đọc private final field của superclass.

Tạo **`FinalMethodBoundaryDemo.java`**:

~~~java
public class FinalMethodBoundaryDemo {
    static class Base {
        private final int id;

        Base(int id) {
            this.id = id;
        }

        public final int id() {
            return id;
        }

        public String label() {
            return "base";
        }
    }

    static final class Child extends Base {
        private String label = "first";

        Child(int id) {
            super(id);
        }

        void changeLabel(String next) {
            label = next;
        }

        @Override
        public String label() {
            return label;
        }
    }

    public static void main(String[] args) {
        Child child = new Child(7);
        Base view = child;

        System.out.println("id=" + view.id());
        System.out.println("label before=" + view.label());
        child.changeLabel("second");
        System.out.println("id again=" + view.id());
        System.out.println("label after=" + view.label());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinalMethodBoundaryDemo.java
java FinalMethodBoundaryDemo
~~~

Stdout:

~~~text
id=7
label before=first
id again=7
label after=second
~~~

Một contract “`id()` không thay đổi” được bảo vệ. Contract “mọi observable method trên Base view bất biến” **không** được đảm bảo vì `label()` overridable.

Nếu class public mô tả mình là immutable hoàn toàn, người dùng có thể đưa ra kết luận sai khi method không final và subclass unrestricted.

## 16. Nguy cơ gọi overridable method trong constructor

Một constructor superclass có thể gọi method **được override** bởi subclass:

~~~java
abstract class Base {
    Base() {
        System.out.println(value());
    }

    abstract int value();
}
~~~

Đừng nghĩ trong Base constructor JVM luôn gọi implementation của Base. Với virtual call, nó có thể dispatch tới **subclass implementation**, trong khi subclass fields **chưa chạy initializers**.

### Ví dụ chạy: trạng thái chưa khởi tạo của subclass

Tạo **`ConstructorDispatchDemo.java`**:

~~~java
public class ConstructorDispatchDemo {
    static abstract class Base {
        Base() {
            System.out.println("during=" + value());
        }

        abstract int value();
    }

    static final class Child extends Base {
        private final int number = 42;

        @Override
        int value() {
            return number;
        }

        void show() {
            System.out.println("after=" + value());
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        child.show();
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorDispatchDemo.java
java ConstructorDispatchDemo
~~~

Stdout:

~~~text
during=0
after=42
~~~

**Vì sao?** Khi constructor Base chạy, toàn bộ object đã được cấp phát và fields ban đầu có default values, nhưng Child field initializer `number = 42` chưa thực thi. Virtual call tới Child.value đọc number=0. Sau khi superclass constructor hoàn tất, subclass initializer gán number=42.

### Liên quan bất biến

Nếu Base constructor gọi overridable `validate()` hoặc `hashCode()`, subclass có thể đọc state chưa thiết lập, ghi ra state không hợp lệ hoặc tạo side effects. Đó là lý do nên:

- Không gọi overridable methods từ constructor.
- Dùng `private` hoặc `final` helper nếu cần logic constructor không bị override.
- Hoàn tất validation bằng các arguments/fields thuộc chính class đang xây dựng.
- Chỉ publish object sau khi xây dựng hoàn chỉnh.
- Nếu cần extension hooks, gọi chúng từ một phase lifecycle **sau construction**, với tài liệu rõ.

## 17. Không để `this` escape trong lúc constructor chạy

Một object có private final fields vẫn có thể gây vấn đề nếu đưa reference `this` ra ngoài trước khi constructor hoàn thành:

~~~java
class Dangerous {
    Dangerous(Registry registry) {
        registry.register(this); // Có thể publish object chưa hoàn thiện.
        // Tiếp tục khởi tạo...
    }
}
~~~

Đây là mã minh họa, Registry cần được định nghĩa. Sau khi đăng ký, code khác hoặc thread khác có thể gọi methods trên object chưa hoàn chỉnh.

### Các đường escape thường gặp

- Đăng ký listener/callback bằng `this` ngay trong constructor.
- Start một thread có closure/reference tới `this`.
- Lưu `this` vào static mutable collection.
- Gọi overridable method để subclass publish reference.
- Truyền `this` cho helper không kiểm soát được lifecycle.

Một invariant bất biến cần đúng **khi object được quan sát**. Nếu object bị lộ giữa chừng, caller có thể nhìn thấy state chưa hoàn tất.

### Thiết kế tốt hơn

Tạo object đầy đủ trước:

~~~java
final class Listener {
    private final String id;

    Listener(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    String id() {
        return id;
    }
}
~~~

Sau constructor trả về, caller mới `registry.register(listener)`. Factory có thể điều phối tạo rồi đăng ký, không publish sớm từ constructor.

## 18. Java Memory Model, `final` fields và immutable objects

Java có những **final field semantics** giúp visibility của fields được khởi tạo đúng cách trong constructors khi objects được xây dựng và chia sẻ hợp lệ.

Tuy nhiên:

- `final` không làm mutable referenced object trở nên thread-safe.
- `final` không thay thế synchronization cho các operations sửa state của object khác.
- Nếu `this` escape trong constructor, một số bảo đảm về safe construction không còn áp dụng theo cách mong đợi.
- Một immutable graph đúng nghĩa có thể dễ chia sẻ giữa threads **không cần lock cho thao tác chỉ đọc**, vì không có races trên state không đổi.
- External resources/I/O/cache mutable được dùng trong methods vẫn cần chính sách thread safety riêng.

Không nên nói “chỉ cần `final class` thì mọi method tự thread-safe”. Một final class có thể chứa mutable `ArrayList` và cập nhật nó, vẫn cần concurrency control.

## 19. Khi superclass được thiết kế để kế thừa thì cần làm gì?

Đôi khi inheritance thực sự phục vụ domain. Hãy xác định **bề mặt mở rộng** và chỉ cho phép subclasses ở những điểm đã kiểm soát.

Một base type có thể:

1. Giữ fields `private final`, không có setters.
2. Dùng constructors validate invariants.
3. Cho immutable getters `final` nếu cần khóa semantics.
4. Không gọi overridable methods trong constructors.
5. Chỉ cho subclass tác động qua những extension points có contract rõ.
6. Hạn chế visibility của internal state; tránh `protected mutable fields`.
7. Kiểm soát subclass set qua `sealed` hierarchy hoặc module/package restrictions.
8. Kiểm tra từng subclass có mutable fields/aliases/side effects không.
9. Cân nhắc một value object final chứa interface-backed strategy thay vì subclass.

**Quan trọng:** Thực hiện những bước này không biến arbitrary untrusted subclasses thành immutable. Nếu public API thực sự hứa toàn bộ hierarchy immutable, chỉ một **closed/audited hierarchy** hoặc cấu trúc không subclassing mới đủ tin cậy theo mô hình thông thường.

## 20. `protected` mutable state dễ bị subclass phá hỏng

Ví dụ không tốt:

~~~java
class BaseConfig {
    protected java.util.List<String> hosts =
            new java.util.ArrayList<>();

    public java.util.List<String> hosts() {
        return java.util.List.copyOf(hosts);
    }
}
~~~

Một subclass có thể `hosts.add(...)` vì field protected, kể cả khi getter trả unmodifiable snapshot. Thêm `final` trên protected reference cũng không ngăn subclass mutate List:

~~~java
protected final List<String> hosts = new ArrayList<>();
~~~

`final` chỉ ngăn reassign reference, không ngăn List mutation.

### Thay thế

- Dùng `private final List<String> hosts = List.copyOf(input)`.
- Trả immutable snapshot hoặc immutable value DTO.
- Không cung cấp protected method làm lộ mutable alias.
- Nếu cần subclass tạo object, truyền state vào protected constructor và validate/copy trước khi lưu.
- Với thư viện mở extension points, tài liệu hóa rõ những operations nào được phép, không dựa vào “subclass sẽ tự giữ an toàn”.

## 21. Ví dụ chạy: protected reference gây hỏng giả định

Tạo **`ProtectedLeakDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ProtectedLeakDemo {
    static class BaseConfig {
        protected final List<String> hosts = new ArrayList<>();

        List<String> snapshot() {
            return List.copyOf(hosts);
        }
    }

    static final class SubConfig extends BaseConfig {
        void addHost(String host) {
            hosts.add(host);
        }
    }

    public static void main(String[] args) {
        SubConfig config = new SubConfig();
        BaseConfig view = config;

        System.out.println("before=" + view.snapshot());
        config.addHost("server-1");
        System.out.println("after=" + view.snapshot());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ProtectedLeakDemo.java
java ProtectedLeakDemo
~~~

Stdout:

~~~text
before=[]
after=[server-1]
~~~

Getter `snapshot()` trả List không sửa qua caller được, nhưng subclass vẫn thay internal List. Nếu BaseConfig quảng cáo bất biến thì đây là một thiết kế sai. `protected final` không thay `private immutable representation`.

## 22. `record` có giúp bảo vệ khỏi subclass không?

Trong Java 17, một `record` là class đặc biệt được **implicitly final**. Không thể định nghĩa một class kế thừa record type của bạn.

~~~java
record Point(int x, int y) {}
~~~

`Point` được ngăn subclass thêm mutable state hoặc override accessors. Các record components được lưu theo mô hình fields final, và compiler tạo constructor/accessors/equals/hashCode/toString theo quy tắc record.

Nhưng **record không tự đảm bảo deep immutability**. Nếu một component là mutable array hoặc List, caller có thể sửa shared reference nếu constructor/accessor không kiểm soát.

### Ví dụ sai

~~~java
record UnsafeRecord(java.util.List<String> names) {
}
~~~

Caller tạo record từ mutable List rồi thêm phần tử; generated accessor `names()` trả cùng List reference. Record vẫn final, nhưng observable names thay đổi.

## 23. Record compact constructor và defensive copy

Tạo **`SafeRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeRecordDemo {
    record Roster(List<String> names) {
        Roster {
            names = List.copyOf(names);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Mai");

        Roster roster = new Roster(input);
        input.add("An");

        System.out.println("input=" + input);
        System.out.println("roster=" + roster.names());

        try {
            roster.names().add("Binh");
        } catch (UnsupportedOperationException ex) {
            System.out.println("record list is unmodifiable");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeRecordDemo.java
java SafeRecordDemo
~~~

Stdout:

~~~text
input=[Mai, An]
roster=[Mai]
record list is unmodifiable
~~~

Trong compact constructor, tham số component `names` được thay bằng snapshot `List.copyOf(names)`; record mechanism gán field từ giá trị cuối cùng của parameter theo quy tắc Java. Generated accessor trả immutable List.

Do element là `String` immutable, record này có state logic ổn định theo API của demo. Nếu component chứa mutable Person objects, phải chuyển sang immutable snapshots tương tự bài Group ở trên.

## 24. Record với array: copy cả lúc nhận lẫn lúc trả

Mảng mutable cần kiểm soát hai chiều. Với record, generated accessor mặc định trả reference, nên khi muốn immutable array-backed value phải **override accessor** để clone.

Tạo **`SafeArrayRecordDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class SafeArrayRecordDemo {
    record Bytes(byte[] value) {
        Bytes {
            Objects.requireNonNull(value);
            value = value.clone();
        }

        @Override
        public byte[] value() {
            return value.clone();
        }

        int length() {
            return value.length;
        }
    }

    public static void main(String[] args) {
        byte[] input = {1, 2};
        Bytes record = new Bytes(input);

        input[0] = 9;
        byte[] external = record.value();
        external[1] = 8;

        System.out.println("input=" + Arrays.toString(input));
        System.out.println("external=" + Arrays.toString(external));
        System.out.println("stored=" +
                Arrays.toString(record.value()));
        System.out.println("length=" + record.length());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeArrayRecordDemo.java
java SafeArrayRecordDemo
~~~

Stdout:

~~~text
input=[9, 2]
external=[1, 8]
stored=[1, 2]
length=2
~~~

**Một điểm thêm:** Generated `equals/hashCode` của record với array component thường dùng array **reference equality/hashCode**, không so sánh elements như `Arrays.equals`. Nếu record cần **value equality theo byte contents**, nên tự thiết kế equals/hashCode tương thích hoặc dùng representation khác. Ngăn mutable alias không tự quyết định tất cả value semantics.

## 25. `sealed class` trong Java 17: kiểm soát tập subclasses

`sealed` cho phép giới hạn **những direct subclasses được phép**. Ví dụ:

~~~java
sealed abstract class Shape permits Circle, Rectangle {
}

final class Circle extends Shape {
}

final class Rectangle extends Shape {
}
~~~

Nếu Shape, Circle, Rectangle thuộc scope/module/package hợp lệ, chỉ những types được permit mới trực tiếp extends Shape. Các permitted subclasses phải đáp ứng quy tắc về `final`, `sealed` hoặc `non-sealed` theo ngữ cảnh.

### Sealed có bảo vệ bất biến không?

**Không tự động.** `sealed` giới hạn **ai được phép kế thừa**. Nó không tự động làm permitted subclass fields final, không copy mutable values, và không cấm mutators.

Bảo đảm hierarchy immutable khi:

1. Superclass state bất biến và constructor đúng.
2. **Từng permitted subtype** được audit về state/methods.
3. Không có nhánh `non-sealed` mở cho subclass tùy ý nếu hợp đồng toàn hierarchy đòi bất biến.
4. API không lộ mutable state.
5. Không có invalid construction/escape paths.
6. Future changes to permitted set cũng được review theo contract.

## 26. Ví dụ chạy: sealed hierarchy với toàn bộ permitted subtypes final

Tạo **`SealedImmutableHierarchyDemo.java`**:

~~~java
public class SealedImmutableHierarchyDemo {
    sealed abstract static class Measure
            permits Length, DurationValue {
        private final long baseUnits;

        protected Measure(long baseUnits) {
            if (baseUnits < 0) {
                throw new IllegalArgumentException("negative units");
            }
            this.baseUnits = baseUnits;
        }

        public final long baseUnits() {
            return baseUnits;
        }

        public abstract String unit();
    }

    static final class Length extends Measure {
        Length(long millimeters) {
            super(millimeters);
        }

        @Override
        public String unit() {
            return "mm";
        }
    }

    static final class DurationValue extends Measure {
        DurationValue(long milliseconds) {
            super(milliseconds);
        }

        @Override
        public String unit() {
            return "ms";
        }
    }

    public static void main(String[] args) {
        Measure a = new Length(120);
        Measure b = new DurationValue(300);

        System.out.println(a.baseUnits() + " " + a.unit());
        System.out.println(b.baseUnits() + " " + b.unit());
        System.out.println("sealed=" + Measure.class.isSealed());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SealedImmutableHierarchyDemo.java
java SealedImmutableHierarchyDemo
~~~

Stdout:

~~~text
120 mm
300 ms
sealed=true
~~~

Base Measure giữ private final long, constructor validate, `baseUnits()` final. Hai permitted concrete classes đều final, không chứa mutable fields, chỉ trả constant unit strings. Vì hierarchy được đóng và audit trong demo, có cơ sở bảo vệ immutable contract.

**Không nên suy luận** một Measure value tương đương về đơn vị giữa Length và DurationValue chỉ vì có cùng số baseUnits; đó là hai domain quantities khác nhau. Kế thừa cần được đánh giá theo substitutability và ý nghĩa domain, không chỉ thuận tiện cú pháp.

## 27. Nhánh `non-sealed` có thể mở lại kế thừa

Ví dụ minh họa:

~~~java
sealed interface Value permits FixedValue, ExtensibleValue {
}

record FixedValue(int number) implements Value {
}

non-sealed class ExtensibleValue implements Value {
    private int number;

    public void change(int value) {
        number = value;
    }
}
~~~

`Value` sealed nhưng permitted `ExtensibleValue` là `non-sealed`, mở khả năng subclassing tiếp và có mutable state. Vì vậy **một sealed interface tự nó không đủ** để hứa mọi Value implementations bất biến.

Tương tự, nếu `sealed` base permits một `sealed` child tiếp tục cho phép những mutable descendants, phải audit toàn bộ phần cây cho đến mọi concrete leaf.

### Khi nên chọn sealed?

- Domain có tập biến thể biết trước, ví dụ `Result` thành công/thất bại.
- Muốn exhaustively reason về variants khi API hỗ trợ.
- Muốn kiểm soát subtype authors và bảo vệ contract.
- Chấp nhận chi phí versioning khi thêm permitted subtype mới.

Nếu không cần subtype hierarchy, **final class hoặc record đơn giản hơn**.

## 28. Composition thay thế inheritance để mở rộng hành vi

Nhu cầu “thêm behavior” không nhất thiết đòi subclass immutable value. Ta có thể giữ **immutable state** trong final class, còn behavior được đưa vào một strategy object riêng.

Ví dụ:

~~~java
final class Message {
    private final String text;

    Message(String text) {
        this.text = java.util.Objects.requireNonNull(text);
    }

    String text() {
        return text;
    }
}

interface Formatter {
    String format(Message message);
}
~~~

Formatter implementations khác nhau không thay đổi Message. Caller truyền Message vào một Formatter, nhận string khác nhau mà **không cần subclass Message**.

### Lợi ích

- Message vẫn final, bảo vệ contract.
- Strategy instances có thể hoán đổi độc lập.
- Test behavior bằng fake formatter.
- Không phụ thuộc protected state hoặc constructor hooks.
- Có thể bổ sung formatter mới mà không sửa hierarchy của Message.

## 29. Ví dụ chạy: final value + strategy interface

Tạo **`CompositionStrategyDemo.java`**:

~~~java
import java.util.Objects;

public class CompositionStrategyDemo {
    static final class Message {
        private final String text;

        Message(String text) {
            this.text = Objects.requireNonNull(text);
        }

        String text() {
            return text;
        }
    }

    interface Formatter {
        String format(Message value);
    }

    static final class Plain implements Formatter {
        @Override
        public String format(Message value) {
            return value.text();
        }
    }

    static final class Bracketed implements Formatter {
        @Override
        public String format(Message value) {
            return "[" + value.text() + "]";
        }
    }

    static void show(Message value, Formatter formatter) {
        System.out.println(formatter.format(value));
    }

    public static void main(String[] args) {
        Message message = new Message("Java");
        show(message, new Plain());
        show(message, new Bracketed());
        System.out.println("original=" + message.text());
    }
}
~~~

~~~bash
javac -encoding UTF-8 CompositionStrategyDemo.java
java CompositionStrategyDemo
~~~

Stdout:

~~~text
Java
[Java]
original=Java
~~~

Thêm cách trình bày không cần extend Message. Nếu Formatter tự có mutable state, điều đó không làm Message trở nên mutable, miễn API không cho Formatter sửa bên trong Message. **Tách trách nhiệm biến đổi/hiển thị** khỏi immutable data value.

## 30. Interface và hợp đồng bất biến: compiler không tự ép implementation immutable

Giả sử:

~~~java
interface StableItem {
    String label();
}
~~~

Không có modifier trong interface khiến mọi implementing classes phải immutable. Một class có thể implement `label()` từ mutable field và thay nó qua setter.

~~~java
class MutableItem implements StableItem {
    private String label;

    MutableItem(String label) {
        this.label = label;
    }

    @Override
    public String label() {
        return label;
    }

    void rename(String next) {
        label = next;
    }
}
~~~

Nếu `StableItem` tài liệu hóa “label không bao giờ đổi”, MutableItem vi phạm **behavioral contract**, nhưng Java compiler không chứng minh bất biến sâu.

### Khi dùng interface vẫn hợp lý

Interface có thể mô tả **read-only API** hoặc **snapshot contract**, nhưng đó là tài liệu/hành vi cần test. Nếu caller cần một immutable value guaranteed, factory có thể **copy vào final concrete type** hoặc API trả immutable record/final class, thay vì tin mọi arbitrary implementation.

Một interface “không có setter” không đồng nghĩa tất cả implementing objects immutable: chúng có thể bị sửa qua reference khác hoặc background task.

## 31. Public immutable base class và equals/hashCode inheritance

Ngay cả khi subclasses không có mutable state, mở inheritance có thể làm value semantics khó giữ:

- Một subclass có thể thêm dữ liệu mới phải tham gia equality.
- Superclass `equals` dùng `instanceof Base` có thể coi object Child bằng Base theo base fields.
- Child `equals` lại yêu cầu cùng Child type và thêm fields.
- Kết quả dễ phá **symmetry** hoặc **transitivity** của `equals`.
- Hash codes phải nhất quán với equals, không được dựa vào mutable fields.

Ví dụ conceptual:

~~~java
class Point {
    final int x, y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Point point
                && point.x == x && point.y == y;
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(x, y);
    }
}
~~~

Nếu subclass `ColoredPoint extends Point` thêm `color` và override equals để yêu cầu cùng color, một Point có thể thấy ColoredPoint “bằng” nó, trong khi ColoredPoint không thấy Point “bằng” nó — vi phạm symmetry.

### Giải pháp

- **Final value class** với equals/hashCode đồng bộ toàn bộ immutable state.
- Record khi phù hợp với value semantics.
- Tránh subclassing value types theo chiều “thêm state mới làm thay equality”.
- Nếu bắt buộc hierarchy, định nghĩa một strategy equals rõ, kiểm thử symmetry/transitivity và kiểm soát subclasses.

Cấm subclass không tự làm equals đúng, nhưng **giảm đáng kể không gian các kiểu có thể phá hợp đồng**.

## 32. Ví dụ chạy: equality bị phá vì mở kế thừa

Tạo **`EqualityInheritancePitfallDemo.java`**:

~~~java
import java.util.Objects;

public class EqualityInheritancePitfallDemo {
    static class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Point p
                    && p.x == x && p.y == y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColoredPoint extends Point {
        private final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = color;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof ColoredPoint p
                    && super.equals(p)
                    && Objects.equals(color, p.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColoredPoint red = new ColoredPoint(1, 2, "red");

        System.out.println("plain.equals(red)=" +
                plain.equals(red));
        System.out.println("red.equals(plain)=" +
                red.equals(plain));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EqualityInheritancePitfallDemo.java
java EqualityInheritancePitfallDemo
~~~

Stdout:

~~~text
plain.equals(red)=true
red.equals(plain)=false
~~~

Đây là **anti-example có chủ ý**, không phải cách viết equals được đề xuất. Hai classes chỉ có fields final, nhưng equals bị phá do subclass thay đổi tiêu chí. Khi immutable value objects được dùng làm Map/Set keys, equality contract sai sẽ dẫn tới behavior khó hiểu. `final class` ngăn subclass kiểu này phá semantics của base class.

## 33. Constructor và factory nên dùng instance type final khi cần guarantee

Nếu public API trả interface hoặc non-final base type:

~~~java
StableValue value = supplier.get();
~~~

caller phải dựa vào contract của **implementation** để biết object thật bất biến. Nếu supplier có thể trả mutable implementation, type interface tự nó chưa đủ.

Một cách mạnh hơn là **copy inputs vào final snapshot type**:

~~~java
final class StableName {
    private final String text;

    StableName(String text) {
        this.text = java.util.Objects.requireNonNull(text);
    }

    String text() {
        return text;
    }
}
~~~

Factory:

~~~java
static StableName snapshot(NameSource source) {
    return new StableName(source.text());
}
~~~

Các đoạn ở trên cần interface `NameSource` được khai báo phù hợp. Điểm cốt lõi: factory không giữ alias tới potentially mutable NameSource; nó lấy immutable String value rồi tạo StableName.

### Một lưu ý concurrency

Nếu NameSource mutable và bị thay đồng thời khi đọc nhiều fields, factory cần một **consistent snapshot** theo domain (lock/transaction/versioning), không chỉ đọc lần lượt rồi mặc định state nhất quán. Bản thân final output không thể sửa chữa dữ liệu đầu vào đã bị đọc không đồng bộ.

## 34. Copy constructor không được tin overridable getter từ source tùy ý

Một “copy constructor” cho non-final base:

~~~java
class Value {
    private final int amount;

    Value(int amount) {
        this.amount = amount;
    }

    Value(Value other) {
        this.amount = other.amount();
    }

    int amount() {
        return amount;
    }
}
~~~

Nếu `other.amount()` có thể override trong subclass, một source object do bên ngoài cung cấp có thể trả giá trị biến thiên hoặc phát sinh side effects. Copy constructor tưởng đang đọc immutable base state, thực tế lại gọi dynamic dispatch.

**Phương án an toàn** khi vẫn kiểm soát cùng class implementation: private helper truy cập trực tiếp private final state của một Value instance, hoặc static factory xác định rõ validation, hoặc cấm subclass bằng final class.

Điểm không phải “đừng bao giờ gọi method từ constructor”, mà là **đừng gọi overridable method trên những objects không tin cậy để suy ra immutable invariant**. Hãy xác định hợp đồng và đường dữ liệu rõ.

## 35. Constructor normalization, invariants và kế thừa

Một class bất biến nên có constructor:

- Validate null/range/format.
- Normalize dữ liệu về canonical representation.
- Copy mutable inputs trước khi publish.
- Không giữ references có thể sửa state từ ngoài.
- Không gọi overridable methods.
- Không để `this` escape.
- Không tạo object ở trạng thái tạm mà caller có thể quan sát.

Ví dụ `DurationValue`:

~~~java
public final class DurationValue {
    private final long millis;

    public DurationValue(long millis) {
        if (millis < 0) {
            throw new IllegalArgumentException("negative duration");
        }
        this.millis = millis;
    }

    public long millis() {
        return millis;
    }
}
~~~

Bằng `final class`, không có subclass bên ngoài tạo method khác nhằm làm `millis()` biến đổi hoặc bổ sung mutable state dưới danh nghĩa DurationValue.

### Validation không tự đến từ final

`final class` cho phép constructor sai, ví dụ chấp nhận `millis = -10` dù domain invariant yêu cầu không âm. Kiểm soát kế thừa là **một mảnh của thiết kế bất biến**, không thay cho validation.

## 36. Bất biến và cache/lazy initialization

Một class final có thể giữ immutable logical value nhưng dùng một cache nội bộ:

~~~java
final class ParsedText {
    private final String text;
    private String cachedNormalized;

    ParsedText(String text) {
        this.text = text;
    }
}
~~~

Đây là **logical immutability** có mutable implementation detail, cần thiết kế cẩn thận. Nếu cache cập nhật từ nhiều threads, phải xét visibility/data races. Không tự nói “final class + private field” nghĩa trạng thái vật lý bất biến.

### Hai cách rõ ràng hơn cho người mới

1. Tính toán trong constructor, lưu trong `private final` field.
2. Nếu phải lazy compute, dùng một synchronization/volatile/caching policy hợp lệ theo Java Memory Model, đảm bảo giá trị logic không thay đổi.

Chỉ nên tuyên bố immutable contract theo **observable semantics và thread safety guarantees đã chứng minh**, không che giấu mutable state vô điều kiện rồi gọi là “fully immutable”.

## 37. Bất biến và serialization/framework construction

Một số framework tạo objects qua reflection, deserialization hoặc bytecode generation. Những quá trình ấy có thể có quy tắc khác constructor invocation thông thường.

Khi thiết kế immutable type cho framework:

- Kiểm tra framework có hỗ trợ final classes/records không.
- Đảm bảo mọi đường tạo instance hợp lệ đều validate/copy.
- Không cung cấp public no-arg constructor rồi setters phá invariant chỉ để tương thích framework nếu có giải pháp tốt hơn.
- Cẩn thận với deserialization bypass, class proxies và lazy loaded associations.
- Không mặc định framework proxy được phép subclass `final class`.
- Nếu framework thật sự cần proxy subclass, cân nhắc tách mutable persistence entity và immutable domain/DTO snapshot.

Java language-level final class ngăn **source-level subclassing thông thường**, nhưng không thay thế các giải pháp security toàn JVM trước mọi dạng reflection/agent/instrumentation được cấp quyền.

## 38. Lựa chọn giữa `final`, `sealed` và composition

| Nhu cầu | Gợi ý | Lý do |
| --- | --- | --- |
| Một immutable value type không cần subtype | `final class` hoặc `record` | Ngăn subclass override/mutable state |
| Có tập biến thể cố định và được kiểm soát | `sealed` base + audited final leaves | Giữ hierarchy đóng |
| Cần plugin implementations không biết trước | Interface + contract tests; copy vào immutable snapshots nếu cần guarantee | Không thể compile-time enforce bất biến của arbitrary plugin |
| Cần thêm cách hiển thị/chuyển đổi value | Composition/strategy | Không thay value type để thêm behavior |
| Chỉ cần bảo vệ một operation base | `final method` | Ngăn override operation đó, không đảm bảo toàn object immutable |
| Có state mutable chia sẻ bởi owner | Tách owner mutable và immutable read model | Không giả vờ toàn object graph bất biến |
| Muốn phần tử collection ổn định | Immutable elements + `List.copyOf` | Chặn cả structure alias lẫn element alias |
| Framework yêu cầu proxy subclasses | Tách persistence model khỏi immutable value object nếu hợp lý | Tránh xung đột final subclass restriction |
| Type dùng làm `HashMap` key | Immutable value + stable equals/hashCode | Tránh key mutation và hierarchy equality pitfalls |

Không có một modifier duy nhất thay thế việc **chọn ownership, representation và contract**.

## 39. Quy trình thiết kế một immutable class có thể tin cậy

**Bước 1 — Định nghĩa trạng thái logic:** Những properties caller được quyền quan sát là gì? Những properties ấy có được thay đổi sau xây dựng không?

**Bước 2 — Chọn extension policy:** Nếu không cần kế thừa, khai báo class `final` (hoặc record). Nếu cần variants, xem `sealed` hierarchy với final leaves và audit từng subtype.

**Bước 3 — Chọn immutable representation:** Ưu tiên primitives, String, Java time immutable types, custom final value classes, records với immutable components.

**Bước 4 — Validate mọi input:** Null, range, duplicates, overflow, cross-field constraints.

**Bước 5 — Defensive copy ở đầu vào:** Không lưu alias tới mảng/List/Date mutable do caller nắm giữ.

**Bước 6 — Bảo vệ output:** Không trả raw mutable internal fields; dùng snapshot/copy hoặc immutable typed views đúng nghĩa.

**Bước 7 — Không có mutators:** Các operations thay đổi logical value nên trả một immutable instance mới hoặc một result rõ.

**Bước 8 — Kiểm soát constructor:** Không gọi overridable hooks, không publish `this` sớm, không giữ inconsistent intermediate states.

**Bước 9 — Bảo vệ equality:** Nếu là value object, equals/hashCode/toString ổn định, tuân thủ hợp đồng và không bị subclasses phá.

**Bước 10 — Test aliases và inheritance:** Sửa input sau construction, thử mutate getter result, thử subclass/override (compile-fail tests nếu phù hợp), kiểm tra concurrency behavior.

**Bước 11 — Kiểm tra framework boundaries:** Serializer/ORM/mapping/reflection có thể tạo hoặc thay đổi state qua con đường nào?

**Bước 12 — Công bố đúng mức bảo đảm:** Deep immutable, shallow immutable, read-only view hay snapshot — tài liệu hóa rõ ràng.

## 40. Test bảo vệ immutability: ví dụ tổng hợp

Tạo **`ImmutableContractTestDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ImmutableContractTestDemo {
    static final class Preferences {
        private final List<String> tags;

        Preferences(List<String> source) {
            tags = List.copyOf(source);
        }

        List<String> tags() {
            return tags;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("java");

        Preferences pref = new Preferences(input);
        input.add("spring");

        check(pref.tags().equals(List.of("java")),
                "input alias changed snapshot");

        boolean rejected = false;
        try {
            pref.tags().add("kotlin");
        } catch (UnsupportedOperationException ex) {
            rejected = true;
        }

        check(rejected, "getter leaked mutable collection");
        check(pref.tags().equals(List.of("java")),
                "observable value changed");

        System.out.println("input alias test PASS");
        System.out.println("output mutation test PASS");
        System.out.println("immutable value test PASS");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableContractTestDemo.java
java ImmutableContractTestDemo
~~~

Stdout:

~~~text
input alias test PASS
output mutation test PASS
immutable value test PASS
~~~

Ví dụ kiểm tra mutability từ hai directions: external alias tới constructor input và attempted mutation qua getter. Nếu phần tử là mutable, test còn phải cố sửa element qua alias. Nếu class được phép subclass, cần thêm tests cho các implementing subclasses để xác nhận chúng không phá behavioral contract.

`private final` là hữu ích, nhưng **mỗi đường từ bên ngoài có thể ảnh hưởng observable state** mới là thứ cần kiểm thử.

## 41. Thử ngăn subclass: compile-time negative test

Giả sử đã viết:

~~~java
public final class ImmutableId {
    private final String value;

    public ImmutableId(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    public String value() {
        return value;
    }
}
~~~

Cố gắng:

~~~java
// class BrokenId extends ImmutableId {
//     BrokenId() {
//         super("X");
//     }
// }
~~~

Nếu bỏ comment và khai báo trong context phù hợp, javac từ chối vì **cannot inherit from final ImmutableId**.

Đây là một ví dụ **cố ý không biên dịch**, dùng để xác nhận restriction của ngôn ngữ; không đưa vào chương trình runnable thông thường rồi kỳ vọng có stdout.

### Record cũng như vậy

~~~java
record Coordinate(int x, int y) {}
// class MutableCoordinate extends Coordinate {} // Không hợp lệ.
~~~

Record implicitly final nên không mở subtype theo cách class thông thường. Nhưng vẫn cần defensive copy nếu component mutable.

## 42. Bài tập 1 — Lớp final có List final có bất biến không?

Cho:

~~~java
final class Notes {
    private final List<String> values;

    Notes(List<String> values) {
        this.values = values;
    }

    List<String> values() {
        return values;
    }
}
~~~

**Câu hỏi:** Class có `final`, field có `private final`. Vì sao vẫn chưa bất biến?

**Đáp án:** List mutable được chia sẻ ở input và output. Caller có thể sửa source List hoặc getter result, làm observable values thay đổi. Cần `List.copyOf`/defensive copy, và kiểm tra element types.

## 43. Bài tập 2 — Override getter phá hợp đồng

Base class có `private final int number`, getter `public int number()` không final. Subclass override getter để trả mutable field. Caller `Base value = new Subclass(...)` sẽ thấy `value.number()` thay đổi hay không?

**Đáp án:** Có thể thay đổi. Dynamic dispatch chọn subclass override theo runtime type. Nếu muốn mọi Base objects immutable, cần ngăn subclass tùy ý (final class/sealed controlled hierarchy), không chỉ private final field.

## 44. Bài tập 3 — Final getter có đủ không?

Base có `public final int id()` trả private final field, nhưng subclass thêm `int counter` và `increment()`.

**Đáp án:** `id()` không thay đổi nhưng **subclass object có mutable state**. Vì thế chỉ có thể cam kết “id ổn định”, không thể khẳng định toàn bộ subtype instance bất biến.

## 45. Bài tập 4 — Constructor overridable call

Trong Base constructor gọi abstract/overridable `value()`. Subclass có `private final int value = 42` và override `value()` để trả field.

**Đáp án:** Lời gọi từ Base constructor có thể thấy 0 vì subclass initializer chưa chạy. Không gọi overridable methods khi chưa kết thúc initialization; dùng final/private helpers và lập luận về thứ tự xây dựng.

## 46. Bài tập 5 — Record component mutable

~~~java
record Box(byte[] data) {
}
~~~

Input byte[] đổi sau khi tạo Box, `box.data()[0]` có đổi không?

**Đáp án:** Có thể đổi, vì record mặc định giữ reference tới array và accessor trả reference ấy. Clone mảng ở constructor và getter. Nếu dùng record như value object, xét thêm equals/hashCode semantics đối với arrays.

## 47. Bài tập 6 — Sealed hierarchy có tự bất biến không?

Một sealed interface permits một final immutable record và một `non-sealed` mutable class.

**Đáp án:** Không. Sealed chỉ giới hạn direct permitted types; non-sealed child mở lại kế thừa và có thể chứa mutable state. Muốn hierarchy immutable phải audit toàn bộ permitted implementations và không để nhánh mở không kiểm soát.

## 48. Bài tập 7 — Composition thay inheritance

Một immutable `ReportData` muốn có thêm định dạng HTML, Markdown và Plain Text.

**Đáp án gợi ý:** Giữ `final ReportData` với String/immutable content, tạo `Formatter` interface và ba implementations nhận ReportData. Không cần `HtmlReportData extends ReportData` để đổi cách trình bày, không mở cửa mutable subclasses của immutable data type.

## 49. Bài tập 8 — Shallow snapshot

`List.copyOf(List.of(mutableMember))` bảo vệ cái gì, và chưa bảo vệ cái gì?

**Đáp án:** Bảo vệ cấu trúc List, không deep-copy Member object. Nếu Member mutable và còn alias bên ngoài, observed member state vẫn có thể đổi. Dùng immutable MemberSnapshot hoặc chuyển/copy element values theo contract.

## 50. Bài tập 9 — Equals và subclass

Superclass `Point.equals` dùng `other instanceof Point`. Subclass `ColoredPoint.equals` chỉ chấp nhận ColoredPoint cùng color.

**Đáp án:** Có thể vi phạm symmetry: plain.equals(colored) true nhưng colored.equals(plain) false. Với value objects, final classes/records hoặc contract equality được thiết kế chặt giúp tránh.

## 51. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Mọi field final nghĩa object immutable.” | Referenced objects có thể mutable | Copy và chọn immutable representations |
| “Class final nghĩa tất cả nội bộ bất biến.” | Class vẫn có mutable List/Date/array | Validate, private fields, defensive copies |
| “Superclass final fields làm mọi subclasses bất biến.” | Subclass có thể thêm mutable state | Final class hoặc closed/audited hierarchy |
| “Private field không thể làm getter biến đổi.” | Getter có thể bị override | Final methods/controlled inheritance |
| “Final method làm toàn object immutable.” | Subclass vẫn thêm mutable fields | Phân biệt API invariant với whole-object |
| “Protected final List không thể bị subclass sửa.” | Final chỉ cấm reassign reference | Private immutable snapshot |
| “Constructor gọi subclass override sau khi subclass initialized.” | Có thể dispatch trước subclass initializers | Không gọi overridable methods trong constructor |
| “Object publish từ constructor vẫn an toàn vì fields final.” | Có thể thấy object chưa hoàn chỉnh | Không để this escape |
| “List.copyOf deep copies elements.” | Chỉ shallow structure snapshot | Immutable elements/snapshot values |
| “Collections.unmodifiableList tạo frozen snapshot.” | Thường live view phản ánh source changes | List.copyOf khi cần snapshot |
| “Record mặc nhiên deep immutable.” | Components có thể mutable | Compact ctor copy + safe accessors |
| “Sealed tự động làm permitted classes immutable.” | Có thể cho mutable/non-sealed subclasses | Audit từng leaf, close hierarchy |
| “Interface read-only đồng nghĩa immutable implementation.” | Class implement vẫn có mutable aliases | Behavioral contract + snapshots |
| “Copy constructor dùng overridable getter luôn an toàn.” | Subclass có thể thay behavior | Direct trusted state/validate/final class |
| “Open value inheritance không ảnh hưởng equals.” | Subclass thêm value state có thể phá symmetry | Final value types/consistent equality |
| “Final class tự thread-safe.” | Mutable internals vẫn race | Deep immutability hoặc synchronization |
| “Reflection lúc nào cũng vô hại.” | Có thể construct, invoke, mutate theo permissions | Thiết kế boundaries và error handling |

## 52. Checklist cuối bài

- [ ] Tôi phân biệt immutable state và chỉ final reference.
- [ ] Tôi hiểu `final class` ngăn subclasses, `final method` ngăn overrides.
- [ ] Tôi biết private final fields không bảo đảm arbitrary subclasses immutable.
- [ ] Tôi chứng minh được subclass override getter làm kết quả thay đổi.
- [ ] Tôi biết subclass có thể thêm mutable fields dù superclass final getters.
- [ ] Tôi phân biệt “base projection ổn định” với “whole object immutable”.
- [ ] Tôi biết `final class` không tự ngăn mutation qua List/Date/array aliases.
- [ ] Tôi defensive copy mutable inputs.
- [ ] Tôi không trả mutable internal state qua getters.
- [ ] Tôi biết `List.copyOf` là snapshot structure, không deep-copy elements.
- [ ] Tôi biết `Collections.unmodifiableList` thường là live unmodifiable view.
- [ ] Tôi biết chuyển mutable element data thành immutable snapshots khi cần.
- [ ] Tôi không gọi overridable methods trong constructors.
- [ ] Tôi không publish `this` trước khi construction hoàn tất.
- [ ] Tôi hiểu những giới hạn của Java final-field visibility semantics.
- [ ] Tôi dùng record final nhưng vẫn kiểm tra mutable components.
- [ ] Tôi copy record array components khi nhận/trả.
- [ ] Tôi biết record array equality cần xem riêng.
- [ ] Tôi biết sealed kiểm soát permitted subclasses nhưng không tự bảo đảm bất biến.
- [ ] Tôi audit mọi permitted subtype và chú ý non-sealed branch.
- [ ] Tôi biết composition/strategy để mở rộng behavior mà không subclass value object.
- [ ] Tôi biết interface không tự enforce immutable implementations.
- [ ] Tôi tránh protected mutable references làm lộ internals.
- [ ] Tôi cân nhắc equals/hashCode khi thiết kế value hierarchy.
- [ ] Tôi biết test cả input alias, output mutation và subclass behavior.
- [ ] Tôi biết các framework có thể cần mô hình snapshot riêng với ORM/proxies.
- [ ] Tôi dùng exact Java 17 programs và hiểu stdout đã cho.

**Kết luận:** Một cam kết bất biến vững chắc không bắt đầu và kết thúc ở từ khóa `final` của field. Nếu một class có thể bị subclass tùy ý, subclass có thể thêm mutable state hoặc thay đổi hành vi getter, khiến mọi lời hứa về **toàn bộ instance** không còn đúng. Với immutable value type cụ thể, **`final class` hoặc record + private final state + validation + defensive copying** là lựa chọn đơn giản và rõ nhất. Khi thật sự cần hierarchy, hãy **đóng và kiểm soát nó bằng sealed types**, audit từng permitted subtype và bảo vệ những methods giữ invariant. Khi chỉ muốn mở rộng cách xử lý giá trị, **composition/strategy** thường tránh được rủi ro inheritance. Bảo vệ tốt nghĩa là không còn đường hợp lệ nào từ API, aliases hoặc subclasses có thể làm biến đổi trạng thái logic mà contract đã hứa sẽ ổn định.
