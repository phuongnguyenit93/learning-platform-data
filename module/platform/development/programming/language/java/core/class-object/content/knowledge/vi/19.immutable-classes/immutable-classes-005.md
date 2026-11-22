# Sao chép phòng vệ đầu vào và đầu ra có thể thay đổi trong Java

## 1. Mục tiêu: một lớp bất biến phải bảo vệ những dữ liệu nào?

Một object **bất biến** (*immutable object*) là object có trạng thái quan sát được không thay đổi sau khi được khởi tạo hoàn chỉnh theo hợp đồng của lớp. Trong Java 17+, `private final` fields và `final class` giúp xây dựng mô hình đó, nhưng **không tự bảo đảm bất biến sâu** nếu một field chứa tham chiếu đến object mutable như `Date`, array, `List`, `Map` hoặc một class có setters.

Ví dụ lớp trông bất biến nhưng không phải:

~~~java
import java.util.Date;

final class Event {
    private final Date when;

    Event(Date when) {
        this.when = when;       // Giữ nguyên tham chiếu đầu vào.
    }

    Date when() {
        return when;            // Trả lại mutable field.
    }
}
~~~

Đây là **đoạn khai báo minh họa**, không phải chương trình Java độc lập.

Caller có thể sửa object qua **hai đường**:

~~~java
Date date = new Date(1_000);
Event event = new Event(date);

date.setTime(9_000);           // Rò trạng thái qua input alias.
event.when().setTime(8_000);  // Rò qua getter output.
~~~

Field `when` là final nên không thể được gán lại từ code trong class sau construction; nhưng object `Date` được tham chiếu vẫn có thể đổi nội dung. Khi bên ngoài giữ một tham chiếu (*alias*) đến đúng object đó, mọi mutations hợp lệ trên alias làm thay đổi nội dung mà Event nhìn thấy.

**Defensive copying (sao chép phòng vệ)** là tạo một bản sao phù hợp tại **ranh giới sở hữu dữ liệu** để external code không thể sửa trạng thái nội bộ thông qua các tham chiếu mà nó đã có hoặc vừa nhận được.

Chủ đề của bài: **sao chép phòng vệ đầu vào và đầu ra có thể thay đổi**, thuộc Java Core → Class/Object → Lớp bất biến. Bài bao gồm constructor/input aliases, getter/output aliases, arrays, `Date`, collections, nested mutable objects, shallow/deep copying, unmodifiable views, records Java 17, builder, validation/TOCTOU, concurrency, performance, các lỗi thường gặp và bài tập. Các chương trình mẫu có tên tệp, lệnh `javac`/`java` và stdout có thể đối chiếu.

## 2. Aliasing: lý do cốt lõi cần copy

~~~java
StringBuilder first = new StringBuilder("A");
StringBuilder second = first;
second.append("B");
System.out.println(first); // AB
~~~

`first` và `second` chỉ cùng một StringBuilder. Phép gán tham chiếu **không sao chép object**. Ngay cả khi hai variables ở hai classes khác nhau, chúng vẫn có thể chỉ đến cùng mutable object.

Sơ đồ khi constructor giữ nguyên input:

~~~text
Caller ───── input ────────┐
                           ▼
                         Date A
                           ▲
Event ───── field ─────────┘
~~~

Sơ đồ khi getter trả thẳng field:

~~~text
Event ─── field ────────> Date A
                           ▲
                           │
Caller <── getter ─────────┘
~~~

Nếu class copy đúng ở cả hai chiều:

~~~text
Caller ── input ──────> Date A
                            │  copy khi nhận
                            ▼
Event ─── field ──────> Date B
                            │  copy khi trả
                            ▼
Caller <── getter ────> Date C
~~~

Những thay đổi trên Date A và Date C không đổi Date B. Các đối tượng là độc lập về mutable state được snapshot.

### 2.1. Lỗi đầu vào

~~~java
class Config {
    private final List<String> roles;

    Config(List<String> roles) {
        this.roles = roles; // Không tạo snapshot.
    }
}
~~~

Caller vẫn giữ `roles` và gọi `roles.clear()` sau khi Config được tạo. Config không kiểm soát được danh sách mà nó được hứa sẽ lưu cố định.

### 2.2. Lỗi đầu ra

~~~java
List<String> roles() {
    return roles; // Caller có thể clear/add nếu List mutable.
}
~~~

Một getter public hoặc package-private cũng có thể làm lộ state cho code gọi được nó. `private` trên field chỉ che tên field, **không bảo vệ object sau khi getter đưa tham chiếu ra ngoài**.

### 2.3. Quy tắc hai chiều

| Constructor/input | Getter/output | Kết quả |
| --- | --- | --- |
| Giữ tham chiếu mutable | Trả tham chiếu mutable | Rò cả hai phía |
| Copy mutable input | Trả field mutable | Getter vẫn làm lộ nội bộ |
| Giữ tham chiếu mutable | Copy output | Caller vẫn sửa qua input |
| Copy mutable input | Copy output hoặc trả immutable view/snapshot an toàn | Có thể bảo vệ trạng thái, tùy độ sâu của copy |

Một instance có thể **không cần sao chép** khi giá trị đã bất biến thật sự như `String`, `Instant`, `LocalDate` hoặc một immutable value object không chứa mutable children. Chia sẻ immutable references thường là giải pháp đơn giản nhất.

## 3. Bước quan trọng: nhận diện mutable types và observable state

Một số kiểu đáng kiểm tra:

- `java.util.Date` có `setTime(long)`.
- `Calendar` có thể sửa các fields thời gian.
- `byte[]`, `char[]`, `int[][]` có thể gán lại các phần tử.
- `ArrayList`, `HashSet`, `HashMap` và nhiều implementations mutable có `add`, `remove`, `put`.
- `StringBuilder`/`StringBuffer` có operations sửa nội dung.
- `ByteBuffer` có thể share backing bytes kể cả khi trả một read-only view.
- Custom POJO như `Address`, `OrderLine`, `MutableProduct` có setter.
- Java records có private final component references, **nhưng có thể chứa List/Date mutable**.

Bất biến phải được đánh giá theo **tất cả những gì caller có thể quan sát**, không chỉ những field được gán một lần.

Hỏi rõ:

1. External caller có giữ alias đến input object không?
2. Internal object có thể được sửa qua getter/callback/stream không?
3. Copy outer container có còn share nested mutable elements không?
4. Equality/hashCode có phụ thuộc vào nested mutable state không?
5. API chủ ý cung cấp snapshot hay live view?
6. Có thread nào khác được phép sửa dữ liệu khi snapshot đang được tạo không?

Chính **hợp đồng sở hữu và thay đổi dữ liệu** quyết định cần defensive copy ở đâu.

## 4. Sao chép `Date` tại constructor và getter

`Date` là ví dụ rõ vì chỉ cần sửa milliseconds bằng `setTime` là đã thay state. Một class giữ khoảng thời gian có thể tự bảo vệ bằng hai nguyên tắc:

- Constructor tạo **Date objects mới** từ input values.
- Getter trả **Date objects mới** thay vì internal fields.

### 4.1. Chương trình hoàn chỉnh 1 — input và output đều được bảo vệ

Tạo tệp **`DefensiveDateRangeDemo.java`**:

~~~java
import java.util.Date;
import java.util.Objects;

public class DefensiveDateRangeDemo {
    static final class Period {
        private final Date start;
        private final Date end;

        Period(Date inputStart, Date inputEnd) {
            Objects.requireNonNull(inputStart, "start");
            Objects.requireNonNull(inputEnd, "end");

            Date startCopy = new Date(inputStart.getTime());
            Date endCopy = new Date(inputEnd.getTime());

            if (startCopy.after(endCopy)) {
                throw new IllegalArgumentException("Khoảng thời gian sai");
            }

            this.start = startCopy;
            this.end = endCopy;
        }

        Date start() {
            return new Date(start.getTime());
        }

        Date end() {
            return new Date(end.getTime());
        }

        long durationMillis() {
            return Math.subtractExact(end.getTime(), start.getTime());
        }
    }

    public static void main(String[] args) {
        Date from = new Date(1_000);
        Date to = new Date(5_000);
        Period period = new Period(from, to);

        from.setTime(100_000);
        to.setTime(200_000);

        System.out.println("Stored start = "
                + period.start().getTime());
        System.out.println("Stored end = "
                + period.end().getTime());

        Date output = period.start();
        output.setTime(-10_000);

        System.out.println("After getter mutation = "
                + period.start().getTime());
        System.out.println("Duration = " + period.durationMillis());

        try {
            new Period(new Date(9_000), new Date(1_000));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 DefensiveDateRangeDemo.java
java DefensiveDateRangeDemo
~~~

**Stdout chính xác:**

~~~text
Stored start = 1000
Stored end = 5000
After getter mutation = 1000
Duration = 4000
Rejected = Khoảng thời gian sai
~~~

### 4.2. Giải thích từng bước

- Constructor gọi `new Date(inputStart.getTime())` và `new Date(inputEnd.getTime())`. Đó là hai objects mới, không giữ Date references bên ngoài.
- Code đổi `from` và `to` sau construction; internal start/end không đổi.
- `period.start()` tạo một Date mới. Sửa biến `output` bằng `setTime` chỉ ảnh hưởng bản copy vừa trả.
- Duration vẫn `5000 - 1000 = 4000`.
- Khi startCopy sau endCopy, constructor ném exception và không trả về Period hợp lệ.

### 4.3. Vì sao phải **copy trước khi validate**?

Thao tác:

~~~java
if (inputStart.after(inputEnd)) {
    throw new IllegalArgumentException();
}
this.start = new Date(inputStart.getTime());
this.end = new Date(inputEnd.getTime());
~~~

có thể kiểm tra **một trạng thái**, nhưng lưu **trạng thái khác** nếu một alias đổi input giữa lúc kiểm tra và lúc copy. Tốt hơn:

~~~java
Date s = new Date(inputStart.getTime());
Date e = new Date(inputEnd.getTime());
if (s.after(e)) {
    throw new IllegalArgumentException();
}
this.start = s;
this.end = e;
~~~

Đây là **fragments**, với `inputStart`/`inputEnd`/fields tương ứng. Validation được thực hiện trên **bản sao thật sự sẽ được lưu**. Điều này giảm một nhóm lỗi *time of check / time of use*.

**Giới hạn:** sao chép hai mutable Date objects riêng rẽ không tạo atomic snapshot xuyên cả hai dưới concurrent mutations từ threads khác. Nếu yêu cầu nhất quán tại **cùng một thời điểm**, phải có ownership/synchronization protocol hoặc một immutable aggregate input. Với API mới, thường ưu tiên `Instant` hoặc `LocalDate` để loại bỏ phần lớn vấn đề.

## 5. Mảng: vì sao `clone()` hữu ích nhưng cần hiểu độ sâu

Mảng Java là mutable reference objects:

~~~java
byte[] raw = {1, 2};
raw[0] = 9;
~~~

Nếu một class muốn giữ bytes cố định:

~~~java
private final byte[] payload;

Packet(byte[] source) {
    this.payload = source.clone();
}

byte[] payload() {
    return payload.clone();
}
~~~

`clone()` của **mảng một chiều các primitives** tạo một array mới chứa các primitive values tương ứng. Caller không thể thay internal payload bằng cách sửa source hoặc mảng do getter trả về.

### 5.1. Chương trình hoàn chỉnh 2 — bảo vệ `byte[]`

Tạo tệp **`DefensiveArrayDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class DefensiveArrayDemo {
    static final class Packet {
        private final byte[] payload;

        Packet(byte[] source) {
            Objects.requireNonNull(source, "source");
            payload = source.clone();
        }

        byte[] payload() {
            return payload.clone();
        }

        int sumUnsigned() {
            int sum = 0;
            for (byte b : payload) {
                sum += Byte.toUnsignedInt(b);
            }
            return sum;
        }
    }

    public static void main(String[] args) {
        byte[] input = {10, 20, 30};
        Packet packet = new Packet(input);

        input[0] = 99;
        System.out.println("After input edit = "
                + Arrays.toString(packet.payload()));

        byte[] output = packet.payload();
        output[1] = 88;
        System.out.println("After output edit = "
                + Arrays.toString(packet.payload()));

        System.out.println("Sum = " + packet.sumUnsigned());
        System.out.println("Output independent = "
                + (output != packet.payload()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 DefensiveArrayDemo.java
java DefensiveArrayDemo
~~~

**Stdout chính xác:**

~~~text
After input edit = [10, 20, 30]
After output edit = [10, 20, 30]
Sum = 60
Output independent = true
~~~

### 5.2. `Arrays.copyOf` có thể thay cho clone

~~~java
byte[] safe = Arrays.copyOf(source, source.length);
~~~

Tạo mảng mới có elements như mảng nguồn trong phạm vi copy, với semantics về length theo API. Đây là một lựa chọn tương tự khi snapshot array primitives.

### 5.3. Mảng hai chiều: clone outer array chưa đủ

~~~java
int[][] original = {{1, 2}, {3, 4}};
int[][] outerOnly = original.clone();

outerOnly[0][0] = 99;
System.out.println(original[0][0]); // 99
~~~

`outerOnly[0]` vẫn trỏ tới cùng `int[]` như `original[0]`. Muốn bảo vệ đến hàng:

~~~java
int[][] deep = new int[original.length][];
for (int i = 0; i < original.length; i++) {
    deep[i] = original[i].clone();
}
~~~

Đây là fragment áp dụng với rows không null. Với arrays của mutable objects, ngay cả clone từng row vẫn giữ **references tới cùng objects con**; cần quyết định tạo bản sao của từng object nếu state của chúng phải bất biến.

## 6. Collections: ba khái niệm cần tách

### 6.1. Mutable List

`ArrayList` cho phép thêm, sửa, xóa phần tử. Nếu class giữ và trả thẳng `ArrayList`, external code có thể phá invariant.

### 6.2. Unmodifiable view

~~~java
List<String> view = Collections.unmodifiableList(source);
~~~

`view.add("B")` ném `UnsupportedOperationException`. Nhưng source có thể vẫn được sửa qua **reference gốc**. Nếu `source.add("B")`, view thường **cũng hiển thị B**. Nó chặn mutation **thông qua view**, không phải snapshot độc lập.

### 6.3. Unmodifiable snapshot

~~~java
List<String> snapshot = List.copyOf(source);
~~~

`List.copyOf` tạo một List unmodifiable với elements phù hợp trạng thái đầu vào khi copy; thay đổi cấu trúc `source` sau đó không thay danh sách snapshot. API có thể tái sử dụng một số unmodifiable inputs thay vì bắt buộc cấp phát object mới. Dựa vào **semantics**, không phụ thuộc vào việc `snapshot != source`.

**`List.copyOf` chỉ copy references của elements**, không deep-copy mutable element objects. Trong `List<String>`, String immutable nên thường đủ. Trong `List<MutableProduct>`, caller vẫn có thể sửa một Product được chia sẻ.

### 6.4. Chương trình hoàn chỉnh 3 — view và snapshot

Tạo tệp **`ListSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListSnapshotDemo {
    static final class Catalog {
        private final List<String> names;

        Catalog(List<String> input) {
            names = List.copyOf(input);
        }

        List<String> names() {
            return names;
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);
        Catalog catalog = new Catalog(source);

        source.add("B");

        System.out.println("Source = " + source);
        System.out.println("View = " + view);
        System.out.println("Snapshot = " + snapshot);
        System.out.println("Catalog = " + catalog.names());

        try {
            catalog.names().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Catalog list cannot be edited");
        }
        System.out.println("Catalog after attempt = "
                + catalog.names());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ListSnapshotDemo.java
java ListSnapshotDemo
~~~

**Stdout chính xác:**

~~~text
Source = [A, B]
View = [A, B]
Snapshot = [A]
Catalog = [A]
Catalog list cannot be edited
Catalog after attempt = [A]
~~~

### 6.5. Vì sao Catalog trả thẳng `names` vẫn an toàn?

Catalog đã lưu một **unmodifiable snapshot với String immutable elements**. Không có backing ArrayList mutable được Catalog giữ và trả cho code bên ngoài; việc `return names` không trao quyền mutate state đó.

**Không máy móc copy mọi lần getter chạy:** nếu internal representation đã thực sự immutable, chia sẻ nó vừa đúng vừa tiết kiệm allocation.

### 6.6. Null trong `List.copyOf`

`List.copyOf` từ chối null elements bằng `NullPointerException`. Nếu domain hợp lệ cho phép null, phải thiết kế copy khác, ví dụ:

~~~java
List<String> output = Collections.unmodifiableList(
        new ArrayList<>(source));
~~~

Đây là fragment. Wrapper chặn sửa cấu trúc qua output; bên trong là một ArrayList mới không lộ alias nếu bạn không chia sẻ nó ở chỗ khác. Nhưng mutable elements vẫn shared. **Unmodifiable view của bản copy** khác **unmodifiable view của chính source**.

## 7. Shallow copy và deep copy

- **Shallow copy (sao chép nông):** tạo container/outer object mới, nhưng giữ references tới nested objects.
- **Deep copy (sao chép sâu theo một phạm vi):** tạo bản sao thích hợp cho các nested mutable objects mà trạng thái của whole phụ thuộc.
- **Immutable value:** không cần sao chép để tránh mutation nếu mọi observable nested state cũng immutable.
- **Unmodifiable view:** không cho sửa qua view, nhưng có thể hiển thị thay đổi ở backing object do alias khác thực hiện.

### 7.1. List mutable elements: shallow chưa đủ

~~~java
final class MutableAddress {
    String city;

    MutableAddress(String city) {
        this.city = city;
    }
}

List<MutableAddress> source =
        new ArrayList<>(List.of(new MutableAddress("Hanoi")));

List<MutableAddress> list = List.copyOf(source);
source.get(0).city = "Hue";
System.out.println(list.get(0).city); // Hue
~~~

List structure không bị sửa, nhưng cùng MutableAddress object được chia sẻ. Nếu class hứa snapshot địa chỉ, phải copy từng Address (hoặc chuyển thành immutable value).

### 7.2. Copy đến mức nào?

Không có một operation Java Core duy nhất tự deep-copy mọi object graph đúng cho mọi domain. Bạn phải quyết định:

- Primitive fields: copy values.
- `String`, `Instant`, immutable records: thường reuse references.
- Mutable arrays/Lists/Maps: copy container.
- Mutable elements: copy từng element khi cần.
- Nested mutable references: tiếp tục theo scope contract.
- Cyclic/shared graphs: có thể cần identity tracking hoặc tạo immutable DTO projection.

**Đừng clone resources như sockets, database connections hoặc threads** chỉ vì outer object có reference đến chúng; resource ownership/lifecycle là vấn đề khác.

## 8. Chương trình hoàn chỉnh 4 — copy mutable object con

Tạo tệp **`NestedObjectCopyDemo.java`**:

~~~java
import java.util.Objects;

public class NestedObjectCopyDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = Objects.requireNonNull(city);
        }

        Address(Address other) {
            this(other.city);
        }

        void moveTo(String next) {
            city = Objects.requireNonNull(next);
        }

        String city() {
            return city;
        }
    }

    static final class ContactSnapshot {
        private final String name;
        private final Address address;

        ContactSnapshot(String name, Address inputAddress) {
            this.name = Objects.requireNonNull(name);
            this.address = new Address(
                    Objects.requireNonNull(inputAddress));
        }

        String name() {
            return name;
        }

        Address address() {
            return new Address(address);
        }
    }

    public static void main(String[] args) {
        Address input = new Address("Hanoi");
        ContactSnapshot contact = new ContactSnapshot("Lan", input);

        input.moveTo("Hue");
        System.out.println("After input change = "
                + contact.address().city());

        Address output = contact.address();
        output.moveTo("Danang");
        System.out.println("After output change = "
                + contact.address().city());

        System.out.println("Name = " + contact.name());
        System.out.println("Copies are distinct = "
                + (output != contact.address()));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 NestedObjectCopyDemo.java
java NestedObjectCopyDemo
~~~

**Stdout chính xác:**

~~~text
After input change = Hanoi
After output change = Hanoi
Name = Lan
Copies are distinct = true
~~~

Ở đây Address copy constructor tạo object riêng. Vì Address chỉ giữ String immutable, bản copy đủ sâu đối với contract minh họa. Nếu Address có mutable `int[] coordinates`, copy constructor cũng cần copy coordinates.

### 8.1. Khi nào nên thay bằng immutable Address?

Nếu domain không cần một Address có setter, dùng:

~~~java
record AddressValue(String city) {
    AddressValue {
        Objects.requireNonNull(city);
    }
}
~~~

Với String immutable, có thể chia sẻ AddressValue reference an toàn; không cần copy ở mỗi getter. **Defensive copying là biện pháp bảo vệ ranh giới mutable, còn loại bỏ mutability không cần thiết thường đơn giản hơn.**

## 9. Maps, Sets và các collections lồng nhau

Trong Java 17:

| API | Tính chất | Điều không tự bảo đảm |
| --- | --- | --- |
| `List.copyOf(source)` | Unmodifiable List snapshot cấu trúc | Deep-copy mutable elements |
| `Set.copyOf(source)` | Unmodifiable Set | Deep-copy mutable elements |
| `Map.copyOf(source)` | Unmodifiable Map snapshot cấu trúc | Deep-copy mutable keys/values |
| `Collections.unmodifiableList(source)` | View không sửa qua view | Snapshot độc lập với source |
| `Collections.unmodifiableMap(source)` | View không sửa qua view | Immutable backing map |
| `new ArrayList<>(source)` | Mutable List structure copy | Ngăn caller sửa List copy nếu lộ ra |
| `new HashMap<>(source)` | Mutable Map structure copy | Deep-copy nested objects |

`List.copyOf`, `Set.copyOf`, `Map.copyOf` không chấp nhận null elements/keys/values trong các vị trí tương ứng. Khi domain cho phép null, thiết kế representation khác.

Một unmodifiable Map có `StringBuilder` value vẫn có thể bị đổi nội dung:

~~~java
Map<String, StringBuilder> map =
        Map.of("title", new StringBuilder("A"));
map.get("title").append("B"); // Hợp lệ: sửa value object.
~~~

Map không hỗ trợ `put`, nhưng nó không tự làm StringBuilder bất biến.

### 9.1. Map of Lists cần copy cả hai tầng

Đối với `Map<String,List<String>>`, nếu class muốn một snapshot:

~~~java
Map<String, List<String>> nested = new HashMap<>();
for (Map.Entry<String, List<String>> entry : input.entrySet()) {
    nested.put(entry.getKey(), List.copyOf(entry.getValue()));
}
this.groups = Map.copyOf(nested);
~~~

Đây là constructor fragment cần field `groups` tương ứng. Với String keys/elements immutable, representation được bảo vệ ở cả hai tầng.

**Không in toàn bộ `Map.copyOf` rồi khẳng định một thứ tự output cụ thể**: API không bảo đảm iteration order khớp insertion order. Nếu thứ tự là contract, chọn representation khác có documented ordering.

### 9.2. Chương trình hoàn chỉnh 5 — nested List trong Map

Tạo tệp **`NestedCollectionsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class NestedCollectionsDemo {
    static final class Directory {
        private final Map<String, List<String>> groups;

        Directory(Map<String, List<String>> input) {
            Objects.requireNonNull(input, "input");

            Map<String, List<String>> copy = new HashMap<>();
            for (Map.Entry<String, List<String>> entry
                    : input.entrySet()) {
                copy.put(entry.getKey(),
                        List.copyOf(entry.getValue()));
            }
            groups = Map.copyOf(copy);
        }

        List<String> members(String group) {
            return groups.getOrDefault(group, List.of());
        }

        int groupCount() {
            return groups.size();
        }
    }

    public static void main(String[] args) {
        List<String> team = new ArrayList<>(List.of("Lan"));
        Map<String, List<String>> input = new HashMap<>();
        input.put("dev", team);

        Directory directory = new Directory(input);

        team.add("Minh");
        input.put("ops", new ArrayList<>(List.of("Hoa")));

        System.out.println("Members = " + directory.members("dev"));
        System.out.println("Group count = "
                + directory.groupCount());
        System.out.println("Unknown = "
                + directory.members("missing"));

        try {
            directory.members("dev").add("Extra");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Members are unmodifiable");
        }

        System.out.println("Members after attempt = "
                + directory.members("dev"));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 NestedCollectionsDemo.java
java NestedCollectionsDemo
~~~

**Stdout chính xác:**

~~~text
Members = [Lan]
Group count = 1
Unknown = []
Members are unmodifiable
Members after attempt = [Lan]
~~~

`team.add` thay mutable List của caller, `input.put` thay caller Map. Directory giữ những snapshots khác nên cả hai thao tác không tác động dữ liệu đã nhận. Getter trả unmodifiable Lists chứa Strings, vì thế không cần copy lặp ở chiều ra.

## 10. Record Java 17: private final components vẫn có thể là mutable references

~~~java
record UnsafeRecord(Date created) {
}
~~~

Record không có setter do compiler sinh, nhưng:

~~~java
Date d = new Date(1_000);
UnsafeRecord unsafe = new UnsafeRecord(d);
d.setTime(5_000);
unsafe.created().setTime(9_000);
~~~

vẫn làm record quan sát Date state thay đổi. Getter do compiler sinh **trả reference**; `final` component reference không làm Date immutable.

### 10.1. Compact constructor phòng vệ đầu vào

~~~java
record SafeRecord(Date created) {
    SafeRecord {
        Objects.requireNonNull(created);
        created = new Date(created.getTime());
    }
}
~~~

Trong compact constructor, ta gán parameter `created` thành bản copy; record dùng giá trị mới khi implicit field assignment diễn ra sau body. Không viết những phép gán field không hợp lệ theo rules của compact constructor.

### 10.2. Accessor phòng vệ đầu ra

~~~java
record SafeRecord(Date created) {
    SafeRecord {
        Objects.requireNonNull(created);
        created = new Date(created.getTime());
    }

    @Override
    public Date created() {
        return new Date(created.getTime());
    }
}
~~~

Copy constructor **chưa đủ** nếu accessor vẫn trả internal Date. Override accessor như trên tạo một Date mới cho caller.

### 10.3. Chương trình hoàn chỉnh 6 — record có List và Date

Tạo tệp **`DefensiveRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Objects;

public class DefensiveRecordDemo {
    record Document(List<String> tags, Date created) {
        Document {
            tags = List.copyOf(tags);
            Objects.requireNonNull(created, "created");
            created = new Date(created.getTime());
        }

        @Override
        public Date created() {
            return new Date(created.getTime());
        }
    }

    public static void main(String[] args) {
        List<String> tags = new ArrayList<>(List.of("draft"));
        Date date = new Date(1_000);

        Document doc = new Document(tags, date);

        tags.add("external");
        date.setTime(5_000);

        System.out.println("Tags = " + doc.tags());
        System.out.println("Created = " + doc.created().getTime());

        doc.created().setTime(10_000);
        System.out.println("Created again = "
                + doc.created().getTime());

        try {
            doc.tags().add("edited");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Tags are unmodifiable");
        }
        System.out.println("Tags again = " + doc.tags());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 DefensiveRecordDemo.java
java DefensiveRecordDemo
~~~

**Stdout chính xác:**

~~~text
Tags = [draft]
Created = 1000
Created again = 1000
Tags are unmodifiable
Tags again = [draft]
~~~

### 10.4. Record và `equals/hashCode`

Record-generated equality/hashCode phụ thuộc các components. Nếu component là mutable object không được copy, thay object đó có thể khiến equality/hashCode thay đổi trong lúc record được dùng làm key của `HashMap`/`HashSet`. Defensive copy bảo vệ cả immutable contract lẫn tính ổn định của key khi phù hợp.

Lưu ý thêm: record có array component không tự deep-compare bytes bằng `Arrays.equals` như bạn có thể mong đợi cho value type. Nếu cần equality theo nội dung array, phải thiết kế riêng.

## 11. Các loại mutable input khác

### 11.1. `StringBuilder`: thường chuyển sang String

~~~java
StringBuilder input = new StringBuilder("A");
String fixed = input.toString();
input.append("B");
System.out.println(fixed); // A
~~~

`String` immutable, nên class có thể lưu `fixed` và trả nó qua getter mà không copy.

### 11.2. `Calendar` và `java.sql.Timestamp`

Đây là các kiểu có mutable state; chỉ giữ reference của caller có thể làm state trong class đổi. Với code mới, cân nhắc snapshot sang các immutable `java.time` types theo ngữ nghĩa thời gian thực tế (Instant cho thời điểm, LocalDate cho ngày không timezone, v.v.).

Đừng đổi Date/Calendar/Timestamp sang LocalDate/Instant **máy móc**: time zone, precision và domain semantics có thể khác nhau. Sao chép/convert phải giữ đúng ý nghĩa dữ liệu.

### 11.3. `ByteBuffer`: read-only view chưa chắc snapshot

`buffer.asReadOnlyBuffer()` trả một read-only view, nhưng buffer view có thể **chia sẻ backing bytes**. Nếu caller vẫn giữ writable alias tới backing buffer, họ có thể đổi nội dung được quan sát qua read-only view. Khi API phải giữ binary snapshot bất biến, hãy copy bytes cần lưu vào storage riêng theo một chính sách rõ về position/limit/slice.

### 11.4. Getter trả iterator hoặc stream

~~~java
Stream<Item> items() {
    return internalItems.stream();
}
~~~

Đây là fragment phụ thuộc field và `java.util.stream.Stream`. Nó **không tự tạo snapshot**. Stream có thể vẫn quan sát mutable internal elements/collection. Nếu thật sự cần immutable snapshot, tạo snapshot trước rồi stream từ representation ổn định.

### 11.5. Callback làm lộ mutable object

~~~java
listener.onChanged(internalMutableState);
~~~

Dù getters đã phòng vệ, callback vẫn có thể trao thẳng internal object cho listener. Trong hệ thống có code bên ngoài hoặc plugins, nên gửi immutable event DTO/snapshot thay vì mutable object sở hữu nội bộ.

## 12. Copy-before-validate và việc tránh đọc lại input

Một constructor cần validate List không rỗng:

**Không nên làm:**

~~~java
if (input.isEmpty()) {
    throw new IllegalArgumentException("Empty");
}
this.values = List.copyOf(input);
~~~

Nếu thread khác sửa input giữa `isEmpty` và `List.copyOf`, validation có thể kiểm tra khác với snapshot được lưu.

**Nên làm:**

~~~java
List<String> snapshot = List.copyOf(input);
if (snapshot.isEmpty()) {
    throw new IllegalArgumentException("Empty");
}
this.values = snapshot;
~~~

Bây giờ code validate **chính snapshot** định lưu.

### 12.1. Không lấy snapshot hai lần

~~~java
List<String> first = List.copyOf(input);
validate(first);
this.values = List.copyOf(input); // Có thể là trạng thái khác!
~~~

Tốt hơn:

~~~java
List<String> snapshot = List.copyOf(input);
validate(snapshot);
this.values = snapshot;
~~~

Fragments trên giả định có `validate` và field tương ứng. Đọc mutable source **một lần**, validate trên bản snapshot và lưu chính nó giảm rủi ro TOCTOU cũng như lãng phí.

### 12.2. Không có atomic snapshot xuyên nhiều data sources một cách mặc định

Nếu constructor nhận hai mutable Lists được thread khác cập nhật, copy lần lượt có thể lấy dữ liệu ở hai thời điểm khác nhau. Nếu quan hệ giữa hai Lists cần invariant chung, phải xây dựng **transaction/synchronized snapshot protocol** hoặc truyền một immutable aggregate. Defensive copy giúp không bị sửa từ ngoài **sau** khi snapshot được lưu; không tự bảo đảm mọi thứ có cùng thời điểm.

## 13. Sao chép input ở setter của lớp mutable

Defensive copying không chỉ dành cho classes immutable. Một mutable class có thể cần đảm bảo caller không làm thay đổi internal state **ngoài một API cập nhật hợp lệ**:

~~~java
class RegionService {
    private List<String> regions = List.of();

    void setRegions(List<String> input) {
        List<String> snapshot = List.copyOf(input);
        if (snapshot.isEmpty()) {
            throw new IllegalArgumentException("Empty regions");
        }
        regions = snapshot;
    }

    List<String> regions() {
        return regions;
    }
}
~~~

Service có quyền thay `regions` thông qua setter, nên **service object không bất biến**, nhưng mỗi snapshot được lưu là unmodifiable và không bị external input alias sửa. Nếu multithreaded, cần visibility/synchronization protocol cho việc publish snapshot reference; đây là một vấn đề riêng.

### 13.1. Builder và factory methods

Một mutable builder thường tích lũy List/Map rồi tạo value object. `build()` nên tạo snapshot/immutable representation; nếu giữ raw builder reference, caller có thể tiếp tục thêm phần tử vào builder sau khi object được tạo và vô tình thay nội dung object.

~~~java
final class Config {
    private final List<String> regions;

    Config(List<String> input) {
        regions = List.copyOf(input);
    }
}
~~~

Một builder có thể gọi `new Config(builderRegions)`. Dù builder tiếp tục được dùng, Config đã chụp snapshot độc lập.

### 13.2. Unmodifiable getter có nhất thiết luôn phải tạo List mới?

Không. Nếu class đã lưu `List.copyOf(input)` và elements là immutable, getter có thể trả chính immutable snapshot. Nếu class giữ một mutable ArrayList nội bộ vì cần thay đổi, getter có thể trả `List.copyOf(internal)` để caller có snapshot cấu trúc tại thời điểm gọi.

**Thiết kế tốt mô tả rõ getter trả “snapshot” hay “live view”.**

## 14. Unmodifiable view có khi nào đủ để giữ một snapshot?

Có thể đủ khi class **tự tạo một mutable backing collection hoàn toàn riêng, không có alias nào khác có quyền sửa**, rồi chỉ trả unmodifiable wrapper:

~~~java
List<String> copy = new ArrayList<>(input);
this.names = Collections.unmodifiableList(copy);
~~~

Nếu code không giữ biến copy nơi khác, không có mutator làm đổi nó về sau, và elements là String immutable, wrapper giữ state ổn định.

Điểm khác với:

~~~java
this.names = Collections.unmodifiableList(input);
~~~

là caller vẫn giữ `input` và có thể sửa backing list. Bọc không làm source ngoài trở nên immutable.

Khi null không cần hỗ trợ, `List.copyOf(input)` thường ngắn gọn và truyền đạt ý định snapshot rõ hơn. Khi null elements được phép, `List.copyOf` sẽ ném NPE; copy vào ArrayList rồi unmodifiable wrapping có thể là một giải pháp có chủ đích.

## 15. Sao chép sâu và object graphs phức tạp

Nếu một immutable-looking class giữ `Map<String,List<MutableItem>>`, copy outer Map + nested List vẫn chỉ copy references tới MutableItem. Khi caller giữ MutableItem và sửa nó, state trong snapshot có thể đổi.

Có thể chụp một DTO immutable:

~~~java
record ItemView(String sku, long priceCents) {
}
~~~

và chuyển mutable items thành các `ItemView` objects:

~~~java
List<ItemView> safe = items.stream()
        .map(x -> new ItemView(x.sku(), x.priceCents()))
        .toList();
~~~

`Stream.toList()` (Java 16+) cho unmodifiable List; các ItemView components là String/long immutable. Nhưng cần xem liệu `sku()` và `priceCents()` có thể thay đồng thời giữa hai lần đọc không; nếu cần atomic item snapshot, owner phải hỗ trợ snapshot method hoặc synchronization.

### 15.1. Graph có cycles

Một graph Parent ↔ Child có references qua lại không thể deep-copy bằng đệ quy vô điều kiện; dễ vô hạn hoặc làm mất shared identity. Cần thiết kế:

- Object nào thực sự thuộc value snapshot?
- Có cần giữ các back references không?
- Có cần memoization qua `IdentityHashMap<Original,Copy>` để xử lý cycles không?
- Có thể tạo một immutable, acyclic DTO projection đơn giản hơn không?

Không dùng “deep copy mọi thứ” như quy tắc mặc định, đặc biệt với resources hay domain entities phức tạp.

## 16. `clone()` không có nghĩa deep-copy

`Object.clone()` với `Cloneable` thường thực hiện **shallow copy** ở mức fields của class object, khi cơ chế clone được gọi hợp lệ. Một field `List<String>` có thể vẫn trỏ cùng List sau clone. Với mutable nested objects, bản clone có thể chia sẻ state ngoài mong đợi.

Một **copy constructor** hoặc explicit factory giúp diễn tả scope rõ hơn:

~~~java
final class NoteSnapshot {
    private final String text;
    private final List<String> tags;

    NoteSnapshot(String text, List<String> tags) {
        this.text = text;
        this.tags = List.copyOf(tags);
    }
}
~~~

Đây là fragment; trong code production cần validate null theo contract. Với immutable String/List elements, copy cấu trúc là đủ. Với nested mutable elements, cần xử lý sâu hơn.

Không cần `new String(oldString)` chỉ để phòng vệ vì String immutable. Copy không làm tăng sự an toàn khi nguồn đã bất biến.

## 17. Immutable objects, hashing và collections

Khi class là value object dùng làm `HashMap` key hoặc `HashSet` member, `equals/hashCode` thường phụ thuộc fields bên trong.

~~~java
final class TagsKey {
    private final List<String> tags;

    TagsKey(List<String> input) {
        tags = List.copyOf(input);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof TagsKey key
                && tags.equals(key.tags);
    }

    @Override
    public int hashCode() {
        return tags.hashCode();
    }
}
~~~

Vì List structure đã snapshot và String elements immutable, caller sửa original input List không làm TagsKey hash/equality đổi. Nếu constructor chỉ giữ List reference mutable, thay contents có thể làm hash đổi khi object đã được dùng làm key trong HashMap, dẫn tới lookup bất thường.

**Quan trọng:** defensive copy chỉ bảo vệ dữ liệu. Bạn vẫn cần đúng các hợp đồng `equals` (reflexive, symmetric, transitive, null, consistency) và `hashCode` (equal objects có equal hash code). Không phải mọi entity nên override equality theo toàn bộ fields mutable.

## 18. Concurrency: defensive copy không tự là transaction

Giả sử thread A copy mutable List trong khi thread B add/remove. Snapshot có thể không nhất quán, ném exception hoặc có behavior tùy API/synchronization nếu collection không hỗ trợ concurrent modification.

Các rủi ro cần phân biệt:

1. **External mutation sau snapshot:** defensive copy phù hợp sẽ ngăn state nội bộ đổi.
2. **Concurrent mutation ngay trong lúc copy:** cần synchronized snapshot / immutable input / thread-safe contract phù hợp.
3. **Shared mutable elements sau shallow copy:** vẫn có data races nếu elements được chia sẻ.
4. **Công bố object trước khi constructor hoàn tất:** có thể khiến thread khác quan sát incomplete state (*this escape*).
5. **Atomic consistency xuyên nhiều inputs:** copy riêng từng input không bảo đảm same-instant snapshot.

### 18.1. Final field không làm nested object thread-safe

`private final List<Item> items` không tự biến Item mutable thành thread-safe. Java final-field semantics hỗ trợ safe initialization trong những điều kiện phù hợp, nhưng không cấm mutate nội dung reference.

### 18.2. `Collections.synchronizedList` không đồng nghĩa bất biến

`Collections.synchronizedList` hỗ trợ synchronization qua các operations theo contract, nhưng list vẫn mutable. `List.copyOf` tạo unmodifiable structural snapshot, nhưng mutable elements vẫn rủi ro. Đó là hai mục tiêu khác nhau.

## 19. Hiệu năng: copy đúng chỗ, không copy vô nghĩa

Defensive copying có chi phí memory/CPU tùy số phần tử và độ sâu. Không nên bỏ copy chỉ dựa vào đoán hiệu năng, nhưng cũng không nên copy immutable objects mỗi lần đọc.

Hướng cân bằng:

1. Dùng `Instant`, `LocalDate`, `String` hoặc immutable value records cho API mới.
2. Copy **một lần tại constructor/boundary** nếu đủ.
3. Không copy lại `List.copyOf` snapshot chứa immutable elements ở mọi getter.
4. Chỉ deep-copy nested mutable values thực sự cần bảo vệ.
5. Nếu output là byte array lớn, cân nhắc streaming hoặc ownership-transfer API rõ ràng thay vì expose writable internal array.
6. Nếu dùng persistent immutable data structures, có thể chia sẻ cấu trúc nhưng phải hiểu contract của library.
7. Benchmark với workload thực trước khi chọn một kỹ thuật khác vì performance.

**Copy-on-write** là một pattern riêng: giữ snapshot đã công bố, khi thay đổi thì tạo state mới. Nó không có nghĩa mọi getter phải tạo một bản sao. `CopyOnWriteArrayList` có trade-off cho workloads nhiều reads/ít writes, không phải lựa chọn bắt buộc cho mọi immutable class.

## 20. Các nguồn rò trạng thái ít rõ ràng hơn

### 20.1. Trả stream/iterator trên mutable backing collection

`internal.stream()` và `internal.iterator()` không tạo immutable snapshot một cách tự động. Caller vẫn có thể nhìn thấy mutable elements hoặc collection đang bị đổi. Snapshot trước nếu API yêu cầu tính độc lập.

### 20.2. Callback nhận mutable internal state

Nếu method gọi `listener.accept(internalMutableObject)`, listener có thể mutate object nếu API cho phép. Truyền immutable DTO/snapshot hoặc một view không cho mutation phù hợp.

### 20.3. Nắm giữ mutable builder sau build

Một builder có thể được sửa sau lần `build()`. Object đã build phải giữ snapshot nếu hứa bất biến; không giữ raw builder reference để lấy state mỗi lần gọi.

### 20.4. Getter trả read-only ByteBuffer

Read-only view có thể chia sẻ underlying storage với writable alias. Cấm caller sửa qua view **không chứng minh underlying bytes không đổi**. Snapshot binary data phải copy bytes hoặc sở hữu storage độc quyền theo contract.

### 20.5. Deserialization và frameworks

Một framework có thể tạo/reconstitute objects qua con đường khác public constructor, dùng proxies/hydration hoặc giữ references mutable. Nếu immutable contract quan trọng, cần kiểm tra framework-specific initialization, validation và defensive copying ở mọi đường đưa dữ liệu vào object. Với Java serialization cũ, cần review deserialize hooks thay vì mặc định public constructor luôn thực hiện copy.

### 20.6. Subclassing phá invariant

Một immutable-looking class có thể bị subclass thêm mutable observable state hoặc override methods. `final class` thường giúp giữ hợp đồng đóng, nhưng **không thay thế defensive copy** của nested objects.

## 21. Lỗi thường gặp

1. Đánh dấu `private final Date` rồi kết luận Date không đổi.
2. Copy mutable input nhưng trả trực tiếp field qua getter.
3. Copy output nhưng constructor giữ input alias.
4. Dùng `Collections.unmodifiableList(source)` thay cho snapshot.
5. Tin `List.copyOf` deep-copy elements.
6. Dùng record với `Date`/List components nhưng không copy.
7. Quên override record accessor khi internal component vẫn mutable.
8. Chỉ clone outer array của `int[][]`.
9. Mặc định `Object.clone()` tạo deep copy.
10. Validate mutable input trước rồi copy sau.
11. Copy source nhiều lần và validate bản khác với bản lưu.
12. Nghĩ copy nhiều mutable inputs tạo atomic snapshot.
13. Trả writable `ByteBuffer` hoặc read-only view chia sẻ backing bytes rồi quảng bá snapshot.
14. Trả stream/iterator của mutable internal collection.
15. Đưa internal mutable object cho callback/listener.
16. Coi unmodifiable List là thread-safe cho mutable elements.
17. Dùng `Map.copyOf` rồi kiểm thử thứ tự iteration như insertion order.
18. Dùng `List.copyOf` trong domain cho phép null elements mà không có policy.
19. Nghĩ `final List<Item>` khiến Item immutable.
20. Copy hàng loạt immutable String/Instant không cần thiết.
21. Dùng generated equals/hashCode trên nested mutable reference, tạo unstable HashMap key.
22. Giữ mutable builder reference trong object sau build.
23. Deep-copy resource như socket/file/connection khi đáng ra cần ownership/close policy.
24. Dùng read-only wrapper nhưng để caller giữ writable backing alias.
25. Không mô tả rõ API trả snapshot hay live view.

## 22. Bài tập tự kiểm tra có đáp án

**Câu 1.** `private final Date when` có đủ làm object bất biến không?

**Đáp án:** Không. Final chỉ chặn gán lại reference; Date vẫn mutable.

**Câu 2.** Tại sao phải phòng vệ cả constructor lẫn getter?

**Đáp án:** Copy constructor ngăn external input alias, còn copy getter ngăn caller sửa internal mutable object qua output. Thiếu một trong hai vẫn có đường mutation.

**Câu 3.** Với `String` đầu vào, có cần copy không?

**Đáp án:** Không. String immutable nên chia sẻ reference an toàn với mutation concerns.

**Câu 4.** `Date` nên được copy bằng cách nào trong ví dụ?

**Đáp án:** `new Date(input.getTime())` khi nhận; `new Date(field.getTime())` khi trả, cùng validation trên snapshot.

**Câu 5.** Vì sao copy trước validation?

**Đáp án:** Để validate chính snapshot sẽ lưu; tránh caller mutate nguồn giữa check và copy.

**Câu 6.** `byte[] source.clone()` có làm array riêng không?

**Đáp án:** Có, tạo byte array object mới chứa copied primitive values.

**Câu 7.** `int[][] outerCopy = source.clone()` có tách inner arrays không?

**Đáp án:** Không. Phải copy từng row nếu cần snapshot hai chiều.

**Câu 8.** `List.copyOf` khác `Collections.unmodifiableList(source)`?

**Đáp án:** List.copyOf cung cấp unmodifiable structural snapshot; unmodifiableList(source) là view có thể phản ánh mutation của backing source.

**Câu 9.** `List.copyOf(List<MutableItem>)` có bảo vệ Item khỏi external mutation không?

**Đáp án:** Không. Items vẫn được tham chiếu, cần immutable elements hoặc deep copy khi hợp đồng yêu cầu.

**Câu 10.** Nếu Catalog đã giữ `List.copyOf(input)` và elements là String, getter có cần tạo List mới không?

**Đáp án:** Không. Trả chính immutable snapshot có thể an toàn và tiết kiệm.

**Câu 11.** `Collections.unmodifiableList(new ArrayList<>(source))` có thể là snapshot cấu trúc không?

**Đáp án:** Có, nếu backing copy không lộ/mutate về sau. Mutable elements vẫn shared.

**Câu 12.** `List.copyOf` cho phép null element không?

**Đáp án:** Không, sẽ ném NullPointerException.

**Câu 13.** Record `record R(Date date)` có tự copy Date không?

**Đáp án:** Không. Constructor/accessor phải có phòng vệ hoặc dùng immutable type thay thế.

**Câu 14.** Compact constructor record copy List thế nào?

**Đáp án:** `tags = List.copyOf(tags)` trong body; compiler gán parameter đã được thay vào component field.

**Câu 15.** `Map.copyOf(Map<String,List<String>>)` có đủ deep immutable không?

**Đáp án:** Không nếu nested Lists mutable. Phải copy nested Lists khi cần.

**Câu 16.** Read-only `ByteBuffer` view có luôn không thay đổi khi original buffer được sửa không?

**Đáp án:** Không. Read-only view có thể share backing bytes.

**Câu 17.** Một mutable class có nên phòng vệ input ở setter không?

**Đáp án:** Có thể cần nếu muốn ngăn caller sửa internal collection ngoài API; điều đó không biến class thành immutable nếu chính setter vẫn đổi state.

**Câu 18.** Nếu thread khác sửa input ngay trong lúc constructor copy, copy có tự atomic không?

**Đáp án:** Không. Cần synchronization/immutable snapshot protocol khi consistency giữa các nguồn quan trọng.

**Câu 19.** Vì sao defensive copy quan trọng với hashCode?

**Đáp án:** Mutable nested data có thể đổi equality/hash của một value key sau khi đưa vào HashMap/HashSet; copy immutable giúp key ổn định.

**Câu 20.** `Object.clone()` của một class có mutable List field có chắc tách list không?

**Đáp án:** Không. Shallow clone có thể giữ cùng List reference.

**Câu 21.** `Instant` có ưu thế gì trước `Date` trong immutable DTO?

**Đáp án:** Instant immutable, có thể chia sẻ qua input/output mà không cần Date-style copies.

**Câu 22.** Có thể bảo vệ immutable class bằng cách chỉ cấm setters không?

**Đáp án:** Không. External aliases qua constructor, getters, callbacks hoặc nested elements vẫn có thể sửa observable state.

**Câu 23.** Nếu cần deep-copy graph có vòng tham chiếu, có thể luôn đệ quy copy vô điều kiện không?

**Đáp án:** Không. Có thể cần memoization/identity-preserving graph copying hoặc immutable DTO projection.

**Câu 24.** Có phải defensive copying luôn tốt bất kể memory/time costs không?

**Đáp án:** Không. Copy đúng những mutable boundaries cần bảo vệ; chia sẻ immutable objects khi an toàn, đo performance nếu cần.

**Câu 25.** Điều quan trọng nhất khi review một getter là gì?

**Đáp án:** Xác định dữ liệu được trả có mutable hay chứa mutable nested objects không, caller có thể dùng nó để thay đổi state nội bộ không, và API hứa snapshot hay live view.

## 23. Checklist khi thiết kế lớp bất biến

1. Class/instance có trạng thái quan sát được cố định theo contract không?
2. Có mutable inputs từ constructor, builder hoặc factory không?
3. Đã copy những mutable inputs cần giữ độc lập chưa?
4. Có **validate chính snapshot** được lưu không?
5. Có đọc lại mutable input sau khi validate không?
6. Getter/accessor có trả mutable internal field không?
7. Nếu getter trả unmodifiable collection, backing data còn mutable alias không?
8. Nested mutable elements có được copy hoặc thay bằng immutable values không?
9. `List.copyOf` có phù hợp với null contract của domain không?
10. `Map.copyOf` có bị giả định iteration order không đúng không?
11. Có array nhiều chiều hoặc array chứa mutable elements không?
12. Record có mutable components nhưng thiếu compact constructor/accessor phòng vệ không?
13. Có thể chuyển `Date` thành `Instant` hoặc `StringBuilder` thành String không?
14. Có stream/iterator/callback làm lộ object mutable không?
15. Builder có tiếp tục giữ reference đến object sau build không?
16. `final` fields có đang bị hiểu nhầm là deep immutability không?
17. Có keys với `equals/hashCode` phụ thuộc nested mutable state không?
18. Copying có diễn ra đồng thời với external writers không?
19. Cross-field validation có cần atomic snapshot không?
20. Có công bố `this` sớm trước khi constructor hoàn tất không?
21. Có resources không nên copy mà cần ownership/lifecycle riêng không?
22. Copy một lần ở boundary có đủ thay vì copy mọi getter không?
23. Có test sửa **input sau construction** rồi kiểm tra state không đổi không?
24. Có test sửa **output từ getter** rồi kiểm tra state không đổi không?
25. Có test nested mutable elements và null/invalid inputs không?

## Kết luận

**Sao chép phòng vệ** không chỉ là thêm `clone()` hay `List.copyOf()` vào bất kỳ chỗ nào. Đó là quyết định **ai sở hữu dữ liệu mutable và ai được phép thay đổi trạng thái nào**. Đối với lớp bất biến, constructor không nên giữ tham chiếu mutable do caller có thể sửa; getter không nên trao tham chiếu nội bộ có thể sửa. Các container dạng List/Map/array cần xem cả outer structure và mutable elements bên trong.

Làm đúng gồm: **copy đầu vào trước khi validate; lưu snapshot phù hợp; trả copy nếu nội bộ còn mutable, hoặc trả an toàn một immutable snapshot; hiểu shallow/deep copying; tránh lộ qua callback/stream/builder; bổ sung synchronization nếu cần atomic snapshot khi có threads khác cập nhật**.

Khi có thể, hãy ưu tiên **immutable value types** như String, Instant hoặc một record với các components thực sự immutable. Khi cần mutable inputs, defensive copying bảo vệ invariant tại ranh giới. Nhờ vậy, tính bất biến trở thành một **bảo đảm hành vi có thể kiểm thử**, chứ không chỉ là các từ khóa `private` và `final`.
