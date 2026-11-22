# Danh sách lỗi thường gặp và tiêu chí tự đánh giá thiết kế lớp — Java 17

## 1. Mục tiêu: kiểm tra *thiết kế* chứ không chỉ kiểm tra cú pháp

Một lớp Java có thể biên dịch, chạy qua vài ví dụ cơ bản và vẫn có thiết kế kém: cho phép tạo trạng thái không hợp lệ, làm rò rỉ danh sách nội bộ, dùng `static` sai chỗ, có `equals/hashCode` không nhất quán, khó kiểm thử, hoặc đóng tài nguyên dựa vào garbage collector. Ngược lại, một lớp có nhiều dòng code hơn đôi khi lại dễ dùng và an toàn hơn nếu nó thể hiện rõ **trách nhiệm, invariant, ownership và API contract**.

README này cung cấp **danh mục lỗi thực hành** và **bộ tiêu chí tự đánh giá thiết kế lớp** dành cho Java 17. Mỗi nhóm gồm dấu hiệu nhận diện, nguyên nhân, hậu quả, hướng sửa và khi phù hợp có chương trình Java độc lập để kiểm chứng.

Sau khi học, bạn có thể:

- Xác định lớp có **một mục đích rõ**, dữ liệu thuộc quyền sở hữu của ai và invariant nào luôn phải đúng.
- Phân biệt **public API** với implementation details, chọn access modifiers thích hợp.
- Đánh giá constructor/factory: validation, default state, lỗi khởi tạo, không lộ `this`.
- Kiểm soát mutability, aliasing, defensive copies và không lộ internal collections/arrays.
- Chọn đúng semantics `equals`, `hashCode`, identity, `toString` và map keys.
- Đánh giá inheritance, composition, polymorphism, `final`, `sealed`, `record`, `enum`.
- Nhận ra lỗi `static`, shared mutable state và concurrency.
- Kiểm tra generic type safety, exception policies, tài nguyên `AutoCloseable`.
- Biến nhận xét mơ hồ như “class xấu” thành **tiêu chí có bằng chứng, cách kiểm thử và thứ tự ưu tiên**.

**Phạm vi:** Java Core class/object và thực hành review thiết kế. Các ví dụ dùng **Java 17**. Không mặc định dùng framework hay build tool ngoài JDK; một số mẫu tích hợp được ghi rõ là snippet.

## 2. Một mẫu review gồm năm câu hỏi

Với bất kỳ class nào, hãy đọc theo thứ tự:

1. **Vai trò:** lớp đại diện giá trị, entity, service, resource owner, utility hay một nhóm hằng?
2. **Bất biến (invariant):** trạng thái nào tuyệt đối không được xảy ra, cả sau constructor lẫn sau mọi public method?
3. **Biên API:** caller nhìn thấy/gọi được gì, có đường nào làm thay đổi state trái ý định không?
4. **Quan hệ:** class phụ thuộc loại nào, extends/implements có đúng *is-a*, có vòng reference, global state hay ownership khó hiểu không?
5. **Bằng chứng:** có test cho thành công, invalid inputs, mutation, equality, failure paths, concurrent access và resource cleanup nếu liên quan không?

Một review có giá trị phải chỉ được **đoạn code tạo lỗi** và **hành vi bị vi phạm**, không chỉ chê class quá dài hay có nhiều getters.

## 3. Phân nhóm lỗi để ưu tiên

| Nhóm lỗi | Ví dụ | Mức ưu tiên gợi ý |
| --- | --- | --- |
| Sai tính đúng đắn | Có thể tạo `Account(-10)`; transition NEW→SHIPPED không validate | Critical |
| Lộ state/ownership | Trả mutable list/array của owner, client sửa data | Critical/High |
| Equality/hash contract | HashMap key thay đổi, equals không đối xứng | High |
| Concurrency | `count++` trên shared object, check-then-act race | High nếu có đa luồng |
| Resource lifetime | Socket/stream không close đúng đường lỗi | High |
| API/encapsulation | Public mutable field, public setter không kiểm tra | High/Medium |
| Abstraction | Inheritance sai is-a, subclass phải throw unsupported | High/Medium |
| Maintainability | “God class”, nhiều lý do thay đổi, hard-coded dependency | Medium |
| Cú pháp/style | Tên khó hiểu, code lặp, formatter chưa đồng nhất | Low/Medium |

**Không biến mức ưu tiên này thành quy định cứng.** Một public field có thể là API data carrier có chủ đích, một class có nhiều dòng vẫn có một trách nhiệm mạch lạc. Phân loại phải dựa trên invariant và tác động thực tế.

## 4. Lỗi 1 — Public mutable fields phá encapsulation

Dấu hiệu:

```java
class Account {
    public long balance;
    public String id;
}
```

Caller có thể gán `balance=-1`, `id=null` mà không qua validation. Một class đang được dùng làm entity với invariant “số dư không âm” không thể tự bảo vệ.

**Hướng sửa:** giữ fields `private`, đặt những operations có ý nghĩa nghiệp vụ và validate tại mọi mutation path:

```java
final class Account {
    private final String id;
    private long balance;

    Account(String id, long initial) {
        if (id == null || id.isBlank() || initial < 0) {
            throw new IllegalArgumentException("invalid");
        }
        this.id = id;
        balance = initial;
    }

    void deposit(long amount) {
        if (amount <= 0) throw new IllegalArgumentException("amount");
        balance = Math.addExact(balance, amount);
    }

    long balance() { return balance; }
}
```

Đây là **snippet** minh họa API, chưa phải chương trình chạy độc lập.

### Cách tự kiểm tra

Hỏi: “Có lệnh hợp lệ nào từ bên ngoài class có thể khiến invariant sai mà không qua methods được kiểm soát?” Nếu có, class có lỗ hổng encapsulation.

## 5. Runnable: field riêng và method giữ invariant

Lưu **`EncapsulationDemo.java`**:

```java
final class Wallet {
    private long cents;

    Wallet(long cents) {
        if (cents < 0) throw new IllegalArgumentException("negative");
        this.cents = cents;
    }

    void add(long value) {
        if (value <= 0) throw new IllegalArgumentException("amount");
        cents = Math.addExact(cents, value);
    }

    long cents() { return cents; }
}

public class EncapsulationDemo {
    public static void main(String[] args) {
        Wallet wallet = new Wallet(100);
        wallet.add(25);
        System.out.println(wallet.cents());

        try {
            wallet.add(-1);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
        System.out.println(wallet.cents());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EncapsulationDemo.java
java EncapsulationDemo
```

Stdout:

```text
125
amount
125
```

Invalid operation bị từ chối mà không phá state đang hợp lệ.

## 6. Lỗi 2 — Constructor không tạo một object hợp lệ

Dấu hiệu:
- Constructor cho phép `null` ở field bắt buộc.
- Setter được gọi sau `new` mới “hoàn thiện” object.
- Không validate giới hạn min/max và quan hệ giữa fields.
- Có nhiều constructors nhưng quy tắc validation khác nhau.
- Constructor ném exception sau khi đã đăng ký `this` vào singleton/listener.

Ví dụ sai về contract:

```java
class Range {
    int start;
    int end;
    Range(int start, int end) {
        this.start = start;
        this.end = end; // Có thể start > end.
    }
}
```

Một invariant phải được giữ từ **construction success**. Nếu class mutable, mỗi operation còn phải giữ invariant sau khi mutate.

**Hướng sửa:** kiểm tra trước khi publish reference; tránh cho `this` escape khỏi constructor (khởi động thread, callback registry, gọi method overridable nguy hiểm). Nếu nhiều cách tạo, tập trung invariant trong constructor/factory cốt lõi.

## 7. Runnable: constructor giữ invariant

Lưu **`ConstructorInvariantDemo.java`**:

```java
record Range(int from, int to) {
    Range {
        if (from > to) {
            throw new IllegalArgumentException("from > to");
        }
    }

    int length() { return to - from; }
}

public class ConstructorInvariantDemo {
    public static void main(String[] args) {
        Range range = new Range(2, 7);
        System.out.println(range.length());

        try {
            new Range(8, 3);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ConstructorInvariantDemo.java
java ConstructorInvariantDemo
```

Stdout:

```text
5
from > to
```

Record compact constructor cũng cần validation; cú pháp record **không** tự kiểm tra business rules.

## 8. Lỗi 3 — Getter/setter không phải lúc nào cũng là API tốt

Một class `Order` chỉ có `setStatus`, `setTotal`, `setPaidAt` có thể cho caller tạo trạng thái “PAID nhưng paidAt null”.

API định hướng hành vi:

```java
order.pay(receipt);
order.cancel(reason);
```

rõ hơn nếu operations này kiểm tra transition và cập nhật các fields liên quan như một đơn vị.

### Tiêu chí

- Có bao nhiêu setter tồn tại chỉ để framework binding?
- Caller có phải gọi đúng **thứ tự setters** để tránh invalid intermediate state không?
- Các operations có thể được đặt tên theo nghiệp vụ không?
- Một object data carrier/DTO có thể đơn giản là record thay vì class đầy setters không?
- Nếu object cần state thay đổi, mutations có được nhóm đúng theo transactional boundary không?

Không phải mọi setter đều xấu: một `PointEditor#setZoom` ở UI có thể hoàn toàn hợp lý. Vấn đề là **setter mở đường vi phạm invariant**.

## 9. Lỗi 4 — Lộ mutable collection qua accessor

Sai:

```java
class Team {
    private final List<String> members = new ArrayList<>();
    List<String> members() { return members; }
}
```

Caller có thể gọi `team.members().clear()`, bypass việc class muốn kiểm soát membership.

Các lựa chọn:
- Trả snapshot `List.copyOf(members)`.
- Trả unmodifiable view nếu **chủ đích** cho caller quan sát thay đổi về sau nhưng không sửa qua view.
- Trả stream/iterator có semantics rõ nếu phù hợp.
- Công bố operations `addMember/removeMember` để giữ invariant.
- Với records/value objects, defensive copy cả **input** lẫn **output** theo loại dữ liệu.

**Lưu ý:** `Collections.unmodifiableList(source)` là view, có thể phản ánh thay đổi của source; `List.copyOf(source)` là unmodifiable shallow snapshot. Nếu elements mutable, cả hai **không deep-copy elements**.

## 10. Runnable: bản sao chặn mutation của caller

Lưu **`DefensiveListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Team {
    private final List<String> members = new ArrayList<>();

    void add(String member) {
        if (member == null || member.isBlank()) {
            throw new IllegalArgumentException("member");
        }
        members.add(member);
    }

    List<String> members() {
        return List.copyOf(members);
    }
}

public class DefensiveListDemo {
    public static void main(String[] args) {
        Team team = new Team();
        team.add("An");
        List<String> snapshot = team.members();

        team.add("Binh");

        System.out.println(snapshot);
        System.out.println(team.members());

        try {
            snapshot.add("Chi");
        } catch (UnsupportedOperationException error) {
            System.out.println("unmodifiable");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DefensiveListDemo.java
java DefensiveListDemo
```

Stdout:

```text
[An]
[An, Binh]
unmodifiable
```

Hành vi snapshot rất rõ: giá trị trước không tự cập nhật khi owner đổi.

## 11. Lỗi 5 — Nghĩ `final`/`record` tự làm object bất biến

Ba nhầm lẫn:
- `final class`: chỉ chặn subclasses, **không** bắt buộc instance fields final.
- `final List<String> field`: chỉ chặn gán lại field, **không** cấm `field.add(...)`.
- `record Holder(List<String> items)`: component field là final, nhưng list có thể mutable.

Đối với value object, cần kiểm tra **mọi đường mutable aliases**. Nếu dùng mảng, clone input/output; nếu dùng collection, copy đúng mức; nếu elements mutable thì cần immutable values hoặc deep copy strategy thích hợp.

### Tiêu chí tự đánh giá

1. Object còn observable state có thể đổi sau construction không?
2. Caller có giữ reference đến mutable input không?
3. Accessor có trả nội bộ trực tiếp không?
4. Generated `equals/hashCode` có phụ thuộc mutable state không?
5. Nếu cần deep immutable, có test sửa nested element sau construction không?

## 12. Runnable: record mutable component rồi sửa

Lưu **`RecordAliasingReviewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record UnsafeTeam(List<String> members) { }

record SafeTeam(List<String> members) {
    SafeTeam {
        members = List.copyOf(members);
    }
}

public class RecordAliasingReviewDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        UnsafeTeam unsafe = new UnsafeTeam(source);
        SafeTeam safe = new SafeTeam(source);

        source.add("B");

        System.out.println(unsafe.members());
        System.out.println(safe.members());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordAliasingReviewDemo.java
java RecordAliasingReviewDemo
```

Stdout:

```text
[A, B]
[A]
```

`SafeTeam` an toàn với list of immutable Strings theo ý định của ví dụ; với list of mutable elements, `List.copyOf` vẫn chỉ copy nông.

## 13. Lỗi 6 — Mutable array bị trả trực tiếp

Mảng là đối tượng mutable, và Java không có `Collections.unmodifiableArray`. Với `byte[]`/`int[]` lưu trong value object:
- Constructor nên `clone()` array đầu vào.
- Accessor trả `clone()` nếu cần công bố dữ liệu.
- Equality/hashCode phải được xem xét: record-generated equality trên component array mặc định dựa vào **array reference**, không deep-content equality.
- Nếu cần value semantics theo nội dung, `Arrays.equals` và `Arrays.hashCode` phải nhất quán.

**Anti-pattern:** `record Packet(byte[] payload){}` rồi giả định Packet deep immutable và `new Packet(new byte[]{1}).equals(new Packet(new byte[]{1}))` là true.

## 14. Runnable: immutable wrapper quanh mảng

Lưu **`ArrayValueReviewDemo.java`**:

```java
import java.util.Arrays;

final class Bytes {
    private final byte[] data;

    Bytes(byte[] data) {
        this.data = data.clone();
    }

    byte[] toArray() {
        return data.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Bytes that
                && Arrays.equals(data, that.data);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(data);
    }
}

public class ArrayValueReviewDemo {
    public static void main(String[] args) {
        byte[] raw = {1, 2};
        Bytes a = new Bytes(raw);
        Bytes b = new Bytes(new byte[]{1, 2});

        raw[0] = 9;
        byte[] detached = a.toArray();
        detached[1] = 8;

        System.out.println(Arrays.toString(a.toArray()));
        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ArrayValueReviewDemo.java
java ArrayValueReviewDemo
```

Stdout:

```text
[1, 2]
true
true
```

Đối tượng che representation và định nghĩa value equality theo nội dung; code dài hơn record nhưng đúng contract hơn khi dữ liệu nền là mutable array.

## 15. Lỗi 7 — `equals` và `hashCode` không nhất quán

Một quy tắc bắt buộc của Java `Object` contract:

> Nếu `a.equals(b)` là true, `a.hashCode() == b.hashCode()` phải là true.

Chiều ngược lại **không bắt buộc**: cùng hash không đồng nghĩa equals.

Các lỗi thường gặp:
- Override `equals` nhưng quên `hashCode`.
- Dùng fields khác nhau cho equals và hash.
- Equals không đối xứng do inheritance và `instanceof`/`getClass` không được thiết kế cẩn thận.
- Dùng mutable fields để hash rồi mutate object khi đang là key của HashMap/HashSet.
- `equals` ném exception cho `null` hoặc kiểu khác thay vì trả false theo contract thích hợp.

Với **value object** immutable, record có thể cung cấp generated equality phù hợp **nếu tất cả components có đúng equality semantics**.

## 16. Runnable: record equality và HashSet

Lưu **`EqualityContractDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

record Point(int x, int y) { }

public class EqualityContractDemo {
    public static void main(String[] args) {
        Point first = new Point(2, 3);
        Point second = new Point(2, 3);

        Set<Point> points = new HashSet<>();
        points.add(first);

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(points.contains(second));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EqualityContractDemo.java
java EqualityContractDemo
```

Stdout:

```text
false
true
true
```

Chọn record vì **tọa độ** là value, không phải vì mọi class nên tự động equals theo fields.

## 17. Lỗi 8 — Identity của entity bị đồng nhất với mọi fields

Một `Customer` có business ID ổn định và mutable address không nhất thiết nên có equality theo cả address. Nếu ghi `equals/hashCode` trên mọi fields:
- Một update address đổi equality/hash.
- Entity có thể “đổi identity” trong một Set.
- Hai khách hàng khác nhau cùng tên/địa chỉ có thể bị coi như một.
- Khi ORM proxies/lifecycle xuất hiện, cách định nghĩa equality càng cần xem framework contract.

**Đặt câu hỏi:** “Cùng entity” nghĩa là cùng object reference, cùng generated ID, cùng natural key, hay cùng toàn bộ state snapshot?

- **Entity:** thường có stable business identity; equality policy cần document rõ.
- **Value:** equality theo dữ liệu; record có thể phù hợp.
- **DTO snapshot:** có thể equality theo components, không thay thế trực tiếp entity identity.
- **Enum:** identity theo constants; `==` phù hợp.

### Không cho rằng mọi entity phải override equals theo ID

Nếu ID được database gán *sau* khi object tạo, equality theo ID đòi hỏi xử lý `null` và transients cẩn thận. Có thể chọn identity-based semantics tùy layer. Quan trọng là **nhất quán qua lifecycle**.

## 18. Lỗi 9 — Mutable key làm mất khả năng tìm trong HashMap

Nếu field tham gia `hashCode` thay đổi sau khi dùng làm Map key, lookup có thể sai. Vấn đề ở invariant của hash-based container, không phải “HashMap bị lỗi”.

Snippet anti-pattern:

```java
class MutableKey {
    String code;
    // equals/hashCode sử dụng code...
}
Map<MutableKey, String> map = new HashMap<>();
MutableKey key = new MutableKey();
key.code = "A";
map.put(key, "value");
key.code = "B"; // Vi phạm ổn định hash của key đang trong map.
```

**Sửa:** immutable record/class làm key, hoặc stable ID không đổi; không mutate identity/equality fields của object trong hash collection.

## 19. Runnable: key ổn định bằng record

Lưu **`StableMapKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

record OrderKey(String tenant, String number) { }

public class StableMapKeyDemo {
    public static void main(String[] args) {
        Map<OrderKey, String> orders = new HashMap<>();
        orders.put(new OrderKey("VN", "100"), "PAID");

        System.out.println(
                orders.get(new OrderKey("VN", "100")));
        System.out.println(
                orders.containsKey(new OrderKey("VN", "999")));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 StableMapKeyDemo.java
java StableMapKeyDemo
```

Stdout:

```text
PAID
false
```

Record components ở đây là immutable Strings. Việc sử dụng record làm key an toàn vì equality/hash stable theo dữ liệu, không có mutation API.

## 20. Lỗi 10 — `toString()` làm lộ secrets hoặc duyệt graph quá lớn

`toString` thường phục vụ debug và logs, nhưng có thể gây:
- Lộ password, token, session cookie, số tài khoản chưa mask.
- Lộ PII khi object được log tự động.
- Kéo toàn object graph thành một chuỗi rất lớn.
- Infinite recursion/stack overflow với references chu trình nếu tự viết không cẩn thận.
- Gọi getters gây side effects/I/O.

**Record-generated toString** công bố component names/values; vì thế record chứa `password`/`apiKey` có thể lộ thông tin khi log. Không dùng record “miễn phí” cho secrets mà quên exposure.

### Cách sửa

- Chỉ in safe identifiers và metadata.
- Redact/mask credentials.
- Giới hạn độ dài collections/text.
- Không gọi business methods có side effects từ `toString`.
- Với security logs, dùng structured logging fields chọn lọc thay vì log toàn bộ object.

## 21. Runnable: redact trong `toString`

Lưu **`SafeToStringDemo.java`**:

```java
final class ApiCredential {
    private final String label;
    private final String secret;

    ApiCredential(String label, String secret) {
        this.label = label;
        this.secret = secret;
    }

    String secret() {
        return secret;
    }

    @Override
    public String toString() {
        return "ApiCredential[label=" + label
                + ",secret=<redacted>]";
    }
}

public class SafeToStringDemo {
    public static void main(String[] args) {
        ApiCredential key = new ApiCredential("service", "TOP-SECRET");
        System.out.println(key);
        System.out.println(key.secret().length());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SafeToStringDemo.java
java SafeToStringDemo
```

Stdout:

```text
ApiCredential[label=service,secret=<redacted>]
10
```

Dòng cuối chỉ minh họa API nội bộ vẫn có dữ liệu; không coi getter secret là API nên public. Với secrets thật, cân nhắc không giữ chúng lâu hơn cần thiết và tránh ghi độ dài/metadata nhạy cảm vào logs.

## 22. Lỗi 11 — Dùng `static` cho state thuộc từng object

Sai về mô hình:

```java
class Session {
    static String currentUser;
}
```

Nếu nhiều `Session` objects độc lập, static field bị chia sẻ giữa mọi instances, làm session nọ ghi đè session kia.

`static` phù hợp với:
- Constants thực sự độc lập instances.
- Stateless utility methods.
- Factories.
- Shared registries được thiết kế rõ ownership/concurrency (cần thận trọng).

Nó **không** phù hợp chỉ vì “muốn mọi methods dễ truy cập biến này”.

### Đối chiếu

- `private String userId;`: state của từng Session object.
- `private static final int DEFAULT_TIMEOUT = 30;`: constant của type.
- `private static final Map<...> CACHE = ...`: shared mutable graph, cần eviction/thread safety/lifecycle rõ.

## 23. Runnable: static state chia sẻ ngoài ý muốn

Lưu **`StaticStatePitfallDemo.java`**:

```java
final class BadSession {
    static String user;
    BadSession(String name) { user = name; }
}

final class GoodSession {
    private final String user;
    GoodSession(String name) { user = name; }
    String user() { return user; }
}

public class StaticStatePitfallDemo {
    public static void main(String[] args) {
        BadSession a = new BadSession("An");
        BadSession b = new BadSession("Binh");

        System.out.println(a.user);
        System.out.println(b.user);

        GoodSession c = new GoodSession("An");
        GoodSession d = new GoodSession("Binh");

        System.out.println(c.user());
        System.out.println(d.user());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 StaticStatePitfallDemo.java
java StaticStatePitfallDemo
```

Stdout:

```text
Binh
Binh
An
Binh
```

Trong Java, truy cập static qua instance được cho phép nhưng gây hiểu lầm và có thể tạo compiler warning; trong production hãy dùng `BadSession.user` để thể hiện rõ state chung.

## 24. Lỗi 12 — Shared mutable state không có concurrency strategy

`counter++` **không** là thao tác nguyên tử cho mục đích shared increment vì là read-modify-write. `volatile int counter` giúp visibility, **không** biến `counter++` thành atomic increment.

Chiến lược tùy use case:
- Thread confinement (mỗi thread một object).
- Immutable snapshots.
- `synchronized`/locks.
- `AtomicInteger` hoặc concurrent collections.
- Database transactions/optimistic locking cho persistence.

Không chọn strategy theo “mọi shared fields đều volatile”; trước tiên xác định **invariant nào cần atomicity**, operation boundaries và consistency requirements.

## 25. Runnable: AtomicInteger cho shared counter

Lưu **`AtomicCounterDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

final class Hits {
    private final AtomicInteger count = new AtomicInteger();

    int hit() {
        return count.incrementAndGet();
    }

    int count() {
        return count.get();
    }
}

public class AtomicCounterDemo {
    public static void main(String[] args) {
        Hits hits = new Hits();

        hits.hit();
        hits.hit();

        System.out.println(hits.count());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AtomicCounterDemo.java
java AtomicCounterDemo
```

Stdout:

```text
2
```

Ví dụ chỉ khẳng định counter operation atomic theo `AtomicInteger`; với workflow gồm nhiều fields, một atomic integer đơn lẻ không đủ giữ multi-field invariants.

## 26. Lỗi 13 — Kế thừa chỉ để tái sử dụng vài dòng code

Một subclass phải đáp ứng hợp đồng của superclass. Nếu thiết kế:

```java
class Rectangle {
    void setWidth(int width) { ... }
    void setHeight(int height) { ... }
}

class Square extends Rectangle {
    // Override setters có thể phá kỳ vọng caller về width/height.
}
```

đoạn này là **pseudocode snippet** về bài toán Liskov substitution, không phải chương trình runnable.

Nếu client kỳ vọng chỉnh width không đổi height, còn Square phải giữ hai cạnh bằng nhau, subclass có thể vi phạm hợp đồng của Rectangle.

**Lỗi thiết kế:** dùng `extends` vì hai classes có data/method giống nhau, không phải vì subclass **thực sự thay thế được** superclass trong mọi ngữ cảnh hợp lệ.

### Thay bằng composition hoặc common interface

```java
interface Shape {
    int area();
}

final class Square implements Shape { ... }
final class Rectangle implements Shape { ... }
```

Shared calculator/dependency có thể được đưa vào helper hoặc collaborator. Kế thừa chỉ đáng dùng khi có một *is-a contract* ổn định.

## 27. Runnable: polymorphism qua interface

Lưu **`CompositionVsInheritanceDemo.java`**:

```java
interface Shape {
    int area();
}

record Rectangle(int width, int height) implements Shape {
    @Override
    public int area() {
        return width * height;
    }
}

record Square(int side) implements Shape {
    @Override
    public int area() {
        return side * side;
    }
}

public class CompositionVsInheritanceDemo {
    public static void main(String[] args) {
        Shape a = new Rectangle(3, 4);
        Shape b = new Square(5);

        System.out.println(a.area());
        System.out.println(b.area());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CompositionVsInheritanceDemo.java
java CompositionVsInheritanceDemo
```

Stdout:

```text
12
25
```

Hai records implement cùng **behavior contract** mà không phải cưỡng ép quan hệ Square extends Rectangle.

## 28. Lỗi 14 — Class cho subclass mở rộng không kiểm soát

Khi public class không final, một client có thể subclass (nếu constructors/visibility cho phép). Nếu superclass:
- Gọi overridable method trong constructor;
- Phụ thuộc private invariant mà subclass có thể phá qua overrides;
- Ghi `equals` nhưng subclass thêm state ảnh hưởng equality;
- Không document rules khi override;

thì inheritance API rất khó bảo trì.

### Tự hỏi

- Class có được thiết kế **có chủ đích để extends** không?
- Methods được cho phép override có documented contract không?
- Nếu không cần extends, có thể dùng `final` không?
- Nếu muốn whitelist subtypes trong Java 17, `sealed`/`permits` có phù hợp không?
- Một interface + composition có truyền tải extension point rõ hơn không?

**Không dùng `final` vô thức** khi framework thật sự cần proxy/subclass; phải kiểm tra contract/version của framework.

## 29. Lỗi 15 — Gọi overridable method trong constructor

Trong Java, dynamic dispatch có thể gọi override của subclass **khi subclass chưa khởi tạo xong fields**. Đây là một lỗi tinh tế.

Anti-pattern:

```java
class Base {
    Base() {
        hook(); // Dynamic dispatch trong constructor.
    }

    void hook() { }
}

class Child extends Base {
    private final String value = "ready";

    @Override
    void hook() {
        // Có thể quan sát value chưa khởi tạo.
    }
}
```

**Sửa:** constructor chỉ dùng private/final helpers an toàn, hoặc xây xong object rồi gọi một lifecycle method có kiểm soát nếu API thật sự cần. Không publish `this` trong constructor cho external callbacks.

## 30. Runnable: dynamic dispatch khi đang construct

Lưu **`ConstructorDispatchPitfallDemo.java`**:

```java
class Base {
    Base() {
        show();
    }

    void show() {
        System.out.println("base");
    }
}

final class Child extends Base {
    private final String message = "ready";

    @Override
    void show() {
        System.out.println(message);
    }
}

public class ConstructorDispatchPitfallDemo {
    public static void main(String[] args) {
        Child child = new Child();
        child.show();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ConstructorDispatchPitfallDemo.java
java ConstructorDispatchPitfallDemo
```

Stdout:

```text
null
ready
```

Trong `Base` constructor, dynamic dispatch gọi Child.show **trước khi Child instance field initializer chạy**. Sau construction, field đã là "ready".

## 31. Lỗi 16 — Nhầm overloading, overriding, static hiding

Các lỗi compile-time/runtime thường bắt nguồn từ:
- Nhầm method overload `print(Object)` với override `print(String)`.
- Cho rằng static methods được dynamic dispatch như instance methods.
- Nhầm private methods có thể override.
- Không dùng `@Override` nên lỗi signature không được phát hiện nhanh.
- Không xét checked exception/return type/covariance rules.

### Checklist nhanh

- **Overloading**: cùng tên, khác parameter list; compiler chọn theo static types, conversions và applicability.
- **Overriding**: subclass cung cấp implementation cho inherited instance method có thể override; runtime dispatch theo object class.
- **Static hiding**: chọn method dựa trên compile-time reference type, không dynamic dispatch như instance override.
- **`@Override`**: compiler kiểm tra annotation giúp phát hiện “tưởng override nhưng thực ra overload”.

## 32. Runnable: overload khác override

Lưu **`OverrideVsOverloadDemo.java`**:

```java
class Parent {
    String action(Object value) {
        return "parent:Object";
    }
}

final class Child extends Parent {
    @Override
    String action(Object value) {
        return "child:Object";
    }

    String action(String value) {
        return "child:String";
    }
}

public class OverrideVsOverloadDemo {
    public static void main(String[] args) {
        Parent parent = new Child();
        Child child = new Child();

        System.out.println(parent.action("A"));
        System.out.println(child.action("A"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OverrideVsOverloadDemo.java
java OverrideVsOverloadDemo
```

Stdout:

```text
child:Object
child:String
```

Overload resolution dựa vào static type (`Parent` chỉ có action(Object)); instance override body vẫn dispatch tới Child.action(Object).

## 33. Lỗi 17 — Class quá nhiều trách nhiệm (*God class*)

Dấu hiệu `OrderManager` đồng thời:
- Validate order;
- Query database;
- Gọi payment gateway;
- Render HTML;
- Gửi email;
- Tính VAT;
- Ghi log hệ thống;
- Duy trì cache;
- Quản lý thread pool.

Đây có thể là một **điểm điều phối ứng dụng hợp lý** nếu chỉ orchestration. Nhưng nếu toàn bộ low-level implementation logic nằm trong một class, nó có **nhiều lý do thay đổi** và khó test riêng.

### Đánh giá bằng change drivers

Hỏi “những nhóm thay đổi độc lập nào khiến file phải sửa?”
- Chính sách tiền tệ;
- HTML template;
- API payment provider;
- Database schema;
- Email provider;
- Workflow state machine.

Nếu những thay đổi này bị buộc sửa một class, xem xét chia **cohesive collaborators** theo trách nhiệm. Không chia cực đoan thành một class cho từng method; abstraction phải giảm coupling thực.

## 34. Lỗi 18 — Hard-coded dependency ngăn unit test

Anti-pattern:

```java
class ReportService {
    void publish() {
        new RealEmailClient().send(...);
    }
}
```

Code production và integration dependency bị cố định trong method. Test muốn xác minh “publish gọi send” phải truy cập network hoặc monkey patch phức tạp.

### Constructor injection

```java
interface Notifier {
    void send(String message);
}

final class ReportService {
    private final Notifier notifier;

    ReportService(Notifier notifier) {
        this.notifier = java.util.Objects.requireNonNull(notifier);
    }

    void publish() {
        notifier.send("report-ready");
    }
}
```

Đây là **snippet** hợp lệ trong scope/class declarations. Bằng cách nhận dependency qua constructor, test dùng fake in-memory notifier, không cần framework DI.

## 35. Runnable: constructor injection và fake dependency

Lưu **`DependencyInjectionDemo.java`**:

```java
interface Notifier {
    void send(String message);
}

final class RecordingNotifier implements Notifier {
    private String last;

    @Override
    public void send(String message) {
        last = message;
    }

    String last() {
        return last;
    }
}

final class ReportService {
    private final Notifier notifier;

    ReportService(Notifier notifier) {
        this.notifier = java.util.Objects.requireNonNull(notifier);
    }

    void publish() {
        notifier.send("ready");
    }
}

public class DependencyInjectionDemo {
    public static void main(String[] args) {
        RecordingNotifier fake = new RecordingNotifier();
        ReportService service = new ReportService(fake);

        service.publish();

        System.out.println(fake.last());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DependencyInjectionDemo.java
java DependencyInjectionDemo
```

Stdout:

```text
ready
```

Testability cao vì service phụ thuộc **interface contract**, không tự tạo hidden external dependency.

## 36. Lỗi 19 — Nhiều getters dẫn đến *feature envy* / dài chuỗi gọi

Đoạn:

```java
order.getCustomer().getAddress().getCountry().getTaxZone()
```

cho thấy caller đang biết nhiều chi tiết bên trong graph. Không phải mọi method chain đều sai; đọc immutable DTO graph có thể hoàn toàn hợp lý. Nhưng nếu caller còn **chỉnh sâu** state:
- Encapsulation yếu;
- Một thay đổi internal layout làm nhiều callers vỡ;
- Invariant bị phân tán;
- Null handling trải khắp nơi.

Có thể đưa behavior về owner:

```java
order.taxZone();
order.calculateTax(policy);
```

hoặc service chuyên biệt nếu operation vượt trách nhiệm của Order.

**Tiêu chí tốt:** ai có đủ dữ liệu và business context để giữ invariant? Đặt behavior ở đó thay vì chuyển hết logic ra utility/service khổng lồ.

## 37. Lỗi 20 — Dùng raw generic types và unchecked casts

Sai:

```java
List values = new ArrayList();
values.add("A");
values.add(123);
```

Với raw `List`, compiler mất type checks; consumers có thể gặp `ClassCastException`.

Đúng khi biết element type:

```java
List<String> values = new ArrayList<>();
values.add("A");
```

Đánh giá:
- Có raw types chỉ vì code legacy không?
- Có `@SuppressWarnings("unchecked")` che vấn đề thay vì cô lập và validate?
- Generic bounds/tham số có thể diễn đạt contract rõ hơn không?
- `List<?>` có phù hợp khi chỉ đọc objects từ list không?
- Có unchecked heap pollution từ varargs/arrays không?

**Diamond `<>` không phải raw type.** `new ArrayList<>()` vẫn sử dụng type inference; `new ArrayList()` mới là raw constructor use.

## 38. Runnable: diamond và type safety

Lưu **`GenericApiReviewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericApiReviewDemo {
    static int totalLength(List<String> words) {
        int sum = 0;
        for (String word : words) {
            sum += word.length();
        }
        return sum;
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("Java");
        words.add("17");

        System.out.println(totalLength(words));
    }
}
```

```bash
javac --release 17 -Xlint:rawtypes,unchecked -encoding UTF-8 GenericApiReviewDemo.java
java GenericApiReviewDemo
```

Stdout:

```text
6
```

Một API parameterized ngăn caller đưa Integer vào list qua các thao tác compile-time checked thông thường.

## 39. Lỗi 21 — Quá nhiều null và sentinel states không hợp lệ

Dấu hiệu:
- Getter trả `null` mà không document.
- Constructor hợp lệ với trường bắt buộc null rồi mọi method phải check lại.
- Sử dụng `-1` làm “chưa có giá trị” ở mọi nơi.
- Một enum có `UNKNOWN`, `NONE`, `UNSET`, `NOT_APPLICABLE` nhưng ý nghĩa chồng lấn.
- Catch exception rồi trả null che nguyên nhân thất bại.

### Hướng sửa

- Validate required constructor parameters với `Objects.requireNonNull`.
- Dùng empty collections thay null nếu đó là contract hợp lý.
- Với một giá trị **có thể không có**, cân nhắc `Optional<T>` ở return boundary, không lạm dụng làm mọi field.
- Với nhiều loại kết quả thành công/thất bại có payload riêng, cân nhắc sealed interface + record variants.
- Nếu null là giá trị hợp lệ, document rõ (và code/test xử lý).

## 40. Runnable: Optional ở return boundary

Lưu **`OptionalReturnDemo.java`**:

```java
import java.util.Map;
import java.util.Optional;

final class Directory {
    private final Map<String, String> names =
            Map.of("a", "An");

    Optional<String> lookup(String id) {
        return Optional.ofNullable(names.get(id));
    }
}

public class OptionalReturnDemo {
    public static void main(String[] args) {
        Directory directory = new Directory();

        System.out.println(directory.lookup("a").orElse("missing"));
        System.out.println(directory.lookup("b").orElse("missing"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OptionalReturnDemo.java
java OptionalReturnDemo
```

Stdout:

```text
An
missing
```

`Optional` làm caller xử lý trường hợp không có value mà không cần tin vào undocumented null. Không dùng Optional để thay mọi loại errors cần diagnostics.

## 41. Lỗi 22 — Catch rộng, nuốt lỗi hoặc đổi thành trạng thái giả

`catch (Exception ignored) { }` có thể làm class “hoạt động” nhưng giữ state sai và che root cause.

Đánh giá:
- Method có thể recover tại đây không?
- Exception thuộc **programming error** hay **expected business validation**?
- Nếu recovery không thể, nên propagate với context phù hợp?
- Cleanup có chạy khi error không?
- Có log nhiều lần cùng exception ở mọi layer (log spam) không?
- Có ném exception chứa secret/PII không?

### Chọn checked vs unchecked theo contract

Không có một quy tắc “mọi lỗi domain đều checked” hay “mọi lỗi unchecked”. Trong Java Core, checked exceptions thể hiện caller thường phải handle/declare; unchecked dùng cho một số programming errors/invalid arguments. Quan trọng là API documented và consistent.

## 42. Lỗi 23 — Resource không được close đúng scope

Đối tượng quản lý `InputStream`, `Socket`, JDBC `Connection` hoặc native handle không nên chờ GC/`finalize()`.

Mẫu:

```java
try (InputStream stream = Files.newInputStream(path)) {
    // consume(stream)
}
```

Đây là snippet giả định imports/path và xử lý IOException phù hợp.

Review:
- Ai sở hữu resource?
- `close()` có được gọi trên cả success và error paths?
- Có constructor acquisition failure không?
- `AutoCloseable` implementation có lifecycle rõ không?
- Borrower có vô tình close resource của owner không?
- Multiple resources close đúng dependency order?
- `Cleaner` nếu dùng chỉ làm backstop, không thay explicit close?

Java 17 `Object.finalize()` đã deprecated từ Java 9, **không dùng để quản lý tài nguyên**. `try-with-resources` có deterministic close theo Java control flow và suppressed exceptions.

## 43. Runnable: close cả khi body lỗi

Lưu **`ResourceOwnershipDemo.java`**:

```java
final class Handle implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("close");
    }

    void work() {
        System.out.println("work");
    }
}

public class ResourceOwnershipDemo {
    public static void main(String[] args) {
        try (Handle handle = new Handle()) {
            handle.work();
            throw new IllegalStateException("failed");
        } catch (IllegalStateException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ResourceOwnershipDemo.java
java ResourceOwnershipDemo
```

Stdout:

```text
work
close
failed
```

Không có System.gc(), sleep hay finalize hook; cleanup xảy ra khi thoát scope.

## 44. Lỗi 24 — Đặt `ThreadLocal` mà không dọn trong thread pool

`ThreadLocal<T>` giúp lưu state riêng cho thread, nhưng worker thread có thể phục vụ nhiều requests. Nếu context được `set` mà không `remove`:
- Request tiếp theo có thể nhìn thấy state cũ.
- References bị giữ lâu ngoài vòng đời nghiệp vụ.
- Memory leak hoặc classloader retention có thể xảy ra tùy runtime.

Dùng:

```java
CONTEXT.set(requestId);
try {
    process();
} finally {
    CONTEXT.remove();
}
```

**Snippet**, giả định CONTEXT/process đã định nghĩa. Không có chuyện ThreadLocal tự reset mỗi task. Nếu có cross-thread async execution, cần truyền context phù hợp; ThreadLocal không tự propagate sang mọi thread.

## 45. Lỗi 25 — Thiếu defensive state với concurrent snapshots

Một class có:

```java
private int x;
private int y;

Point snapshot() {
    return new Point(x, y);
}
```

Nếu writers thay x/y không đồng bộ, snapshot có thể quan sát cặp giá trị không thuộc cùng logical update. Một record `Point` bất biến **không tự** làm read từ mutable owner nhất quán.

Giải pháp tùy invariant:
- Bảo vệ update và snapshot bằng cùng lock.
- Lưu một immutable State record trong `volatile`/AtomicReference rồi **swap toàn bộ state**.
- Transaction ở persistence boundary.
- Thread confinement.

**Tư duy review:** kiểm tra **atomicity của invariant nhiều fields**, không chỉ xem mỗi field có volatile/final hay không.

## 46. Runnable: AtomicReference giữ immutable snapshot

Lưu **`AtomicSnapshotDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicReference;

record Position(int x, int y) { }

final class Tracker {
    private final AtomicReference<Position> current =
            new AtomicReference<>(new Position(0, 0));

    void move(int dx, int dy) {
        current.updateAndGet(old ->
                new Position(old.x() + dx, old.y() + dy));
    }

    Position snapshot() {
        return current.get();
    }
}

public class AtomicSnapshotDemo {
    public static void main(String[] args) {
        Tracker tracker = new Tracker();
        Position before = tracker.snapshot();

        tracker.move(2, 3);

        System.out.println(before);
        System.out.println(tracker.snapshot());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AtomicSnapshotDemo.java
java AtomicSnapshotDemo
```

Stdout:

```text
Position[x=0, y=0]
Position[x=2, y=3]
```

Update thay **một reference đến immutable record**. Snapshot `before` giữ cặp cũ; không có trạng thái nửa cập nhật x/y trong một Position object.

## 47. Lỗi 26 — Chọn sai mutable class, immutable class, record hoặc enum

Các đối chiếu khi review:
- **Entity có ID và state đổi** → mutable class hoặc thiết kế immutable entity snapshots có chủ đích; không chọn record chỉ vì có 3 fields.
- **Value object ít components, equality theo values** → record nếu deep immutability/data semantics phù hợp.
- **Value object cần ẩn array/representation/custom equality** → immutable class có thể tốt hơn.
- **Fixed set of symbols** → enum, tránh lưu ordinal như database ID bền vững.
- **Variant types với payload khác nhau** → sealed interface + records/final classes.
- **Resource owner có close lifecycle** → class với AutoCloseable rõ, không coi record là resource manager mặc định.

### Câu hỏi chốt

“**Một caller mới có thể dùng type này sai theo cách nào dù code compile?**” Cấu trúc ngôn ngữ tốt phải làm đường dùng sai khó hơn hoặc compiler từ chối ngay khi có thể.

## 48. Lỗi 27 — `enum` chứa mutable shared state

Enum constants là các instance định nghĩa trước. Nếu:

```java
enum Mode {
    ACTIVE;
    int count;
}
```

thì `Mode.ACTIVE.count` là **state chung của constant**, không phải riêng mỗi user/request. Trong server đa luồng, còn nguy cơ race.

**Thiết kế tốt:** Enum mô tả loại/status ổn định, còn state của mỗi request nằm ở object riêng. Nếu cần external code bền vững, khai báo field `private final String code` và ánh xạ hai chiều; không dùng `ordinal()` làm persistent ID.

## 49. Runnable: enum và record thành hai vai trò riêng

Lưu **`EnumRoleDemo.java`**:

```java
enum Status {
    NEW, PAID
}

record OrderView(String id, Status status) { }

public class EnumRoleDemo {
    public static void main(String[] args) {
        OrderView first = new OrderView("O1", Status.NEW);
        OrderView second = new OrderView("O2", Status.PAID);

        System.out.println(first.status());
        System.out.println(second.id());
        System.out.println(first.status() == Status.NEW);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumRoleDemo.java
java EnumRoleDemo
```

Stdout:

```text
NEW
O2
true
```

`Status` là fixed symbols; `OrderView` là các independent data values.

## 50. Lỗi 28 — Visibility quá rộng hoặc quá hẹp

Review:
- Public class/member nào cần được caller gọi thực sự?
- Public field có biến implementation thành external contract không?
- Package-private có đủ cho các collaborating types trong package không?
- `protected` có đúng là một extension point, hay chỉ vì muốn tests gọi được?
- Private helpers có giấu invariant đúng không?
- Java named modules có exported packages/open reflective access phù hợp không?

**Nhớ:** `public` không có nghĩa mọi module trên module path đều truy cập được khi package không được export từ named module. `protected` có các quy tắc truy cập liên quan subclass/package, không phải “public cho mọi subclasses bất kể ngữ cảnh”.

### Một nguyên tắc tốt

**Công bố bề mặt API tối thiểu đủ dùng**, sau đó mở rộng khi có nhu cầu thật, thay vì public hết rồi phải hỗ trợ compatibility vĩnh viễn.

## 51. Lỗi 29 — Hệ phân cấp `sealed` không khớp ý định mở rộng

Java 17 sealed hierarchy:
- `sealed Parent permits A, B` kiểm soát **direct** subtypes.
- Direct class child chọn `final`, `sealed` hoặc `non-sealed`.
- Direct subinterface của sealed interface chọn `sealed` hoặc `non-sealed` (interface không final).
- `non-sealed` mở một nhánh cho descendants bình thường, không tự làm mọi classes con cháu của root được liệt kê vào permits.
- Records implicitly final và có thể implements sealed interface.
- Trong named module, permitted direct types cùng module; trong unnamed module, cùng package.

**Lỗi thiết kế:** “muốn closed domain”, nhưng đặt một `non-sealed` child chỉ để sửa compile error. Nhánh đó có thể được mở rộng ngoài mong muốn.

Chọn final leaves cho các variants cuối, sealed intermediates cho các nhóm con được kiểm soát và non-sealed chỉ khi thực sự muốn extension point.

## 52. Runnable: thiết kế hierarchy đã đóng

Lưu **`SealedReviewDemo.java`**:

```java
sealed interface Result permits Success, Failure { }

record Success(String data) implements Result { }

record Failure(String reason) implements Result { }

public class SealedReviewDemo {
    static String describe(Result result) {
        if (result instanceof Success ok) {
            return "ok:" + ok.data();
        }
        if (result instanceof Failure fail) {
            return "error:" + fail.reason();
        }
        throw new IllegalStateException("unhandled");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success("A")));
        System.out.println(describe(new Failure("bad")));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedReviewDemo.java
java SealedReviewDemo
```

Stdout:

```text
ok:A
error:bad
```

`instanceof` pattern matching là tính năng chính thức Java 17. Không dùng pattern matching `switch` trên sealed types làm ví dụ Java 17 không preview: tính năng ấy chưa ổn định ở Java 17.

## 53. Lỗi 30 — Thiếu hợp đồng về lỗi và thứ tự side effects

Nếu một public method:
1. Trừ tiền,
2. Gọi remote API,
3. Ghi event,
4. Mới validate input,

thì nếu validation hoặc remote call fail, state có thể đã thay đổi nửa chừng.

**Review:**
- Validate sớm phần có thể validate.
- Thiết kế transaction/rollback/compensation cho side effects.
- Không có public method nào để object ở trạng thái vi phạm invariant khi exception được ném.
- Nếu fail một bước sau mutation, có cơ chế phục hồi/atomicity phù hợp không?
- Đặt naming/documentation cho partial success/failure rõ ràng.
- Đừng kỳ vọng một Java `try/finally` tự rollback database/business actions.

Đây là lỗi thiết kế class *ở boundary hành vi*, không chỉ cú pháp exception handling.

## 54. Lỗi 31 — Biến value object thành global singleton không cần thiết

Một immutable configuration/value nhỏ có thể được dùng chung, nhưng không tự suy rằng mọi giá trị cùng contents phải là một singleton object toàn JVM.

Dùng singleton khi:
- Có đúng một **dịch vụ/registry** theo application scope;
- Lifecycle và dependency context rõ;
- Concurrency và testing không bị phá.

Tránh singleton khi:
- Dữ liệu phụ thuộc user/tenant/request;
- Test cases cần isolated state;
- App có nhiều environments/class loaders;
- Mutable singleton giữ dữ liệu không liên quan qua tests.

**Singleton là ownership/lifecycle decision**, không phải mẹo tránh cấp phát object.

## 55. Lỗi 32 — Dùng inheritance thay vì dependency/interface

Một `ReportService extends DatabaseClient` thường đáng nghi nếu ReportService không thực sự là “một loại DatabaseClient”. Nó chỉ **dùng** database client, không phải tự thân một database client.

Nên cân nhắc:

```java
final class ReportService {
    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = repository;
    }
}
```

**Snippet:** ReportRepository phải được khai báo nơi thích hợp. Quan hệ này là **has-a/dependency**. Constructor injection giúp test fake implementations, tránh làm public surface của ReportService nhận toàn bộ inherited API từ DatabaseClient.

## 56. Lỗi 33 — Quá nhiều boolean flags trong constructor

`new Policy(true,false,true,false)` khó đọc và dễ đảo nhầm. Nếu các cờ có domain meaning:
- Dùng enum cho finite choice;
- Dùng records chứa options;
- Dùng named factories;
- Dùng builder nếu có nhiều optional attributes;
- Tách các modes tương phản thành types nếu khác invariants.

Ví dụ thay:

```java
new ExportJob(true, false);
```

bằng:

```java
new ExportJob(OutputFormat.CSV, Compression.NONE);
```

Các đoạn là **snippets**, chưa định nghĩa đầy đủ ExportJob/OutputFormat/Compression.

### Không lạm dụng builder

Một record `Point(int x,int y)` đơn giản không cần builder 300 dòng. Builder là để giảm ambiguity/phức tạp cấu hình, không phải tiêu chí chất lượng tự thân.

## 57. Lỗi 34 — Copy/paste một thuật toán vào nhiều classes

Khi nhiều classes nhân bản validation hoặc cách tính giống nhau:
- Sửa một bản, quên bản khác.
- Business rules phân kỳ.
- Tests không bao phủ mọi biến thể.
- Một thay đổi về rounding/policy thành bug production.

**Hướng sửa:** chỉ trừu tượng hóa khi logic **thực sự cùng semantics và cùng lý do thay đổi**. Shared helper/service/value object có thể hợp lý. Đừng ép hai algorithms khác domain vào một utility chỉ vì cùng vài dòng if.

## 58. Lỗi 35 — Hằng số không ổn định hoặc magic values

`if (status == 3)` hoặc `if (timeout > 5000)` không cho caller biết ý nghĩa. Một constant:

```java
private static final int MAX_RETRIES = 3;
```

có thể cải thiện readability. Nếu tập lựa chọn finite, `enum` có thể phù hợp. Nếu timeout đo bằng thời gian, dùng `Duration` giúp type diễn tả đơn vị:

```java
private static final Duration TIMEOUT =
        Duration.ofSeconds(5);
```

**Snippet:** `java.time.Duration` cần import/qualified name.

Tránh đặt hằng số không liên quan vào một global `Constants` class khổng lồ; hằng nên gần nơi chứa logic sở hữu nó.

## 59. Lỗi 36 — Tên class/method không diễn đạt behavior

Các tên `Data`, `Util`, `Manager`, `Process` không mặc nhiên sai, nhưng thường che trách nhiệm. Review:
- Method `save` lưu vào memory, disk hay remote?
- `update` có mutate receiver hay trả copy?
- `get` có I/O/throw/bất kỳ side effect đáng chú ý nào?
- `isValid` có thay đổi state không?
- `close` có idempotent/thread-safe và exception contract thế nào?

Ưu tiên tên nhất quán với **observable contract**. Không đặt `getBalance` cho method vừa đọc vừa reset balance; không gọi `immutableCopy` nếu nó trả view live mutable.

## 60. Lỗi 37 — Public constructor khiến caller bỏ qua factory invariant

Có khi factory cần:
- Normalize input.
- Trả cached value hoặc subtype.
- Chọn implementation phù hợp.
- Trả `Optional/Result` khi không tạo được.
- Ẩn internal representation.

Nếu public constructor và factory cùng tồn tại, caller có thể bypass normalization do factory làm nếu constructor không validate.

**Nguyên tắc:** dù dùng constructor hay factory, **mọi đường tạo object thành công phải giữ invariant**. Một factory không bù được constructor công khai dễ tạo invalid state.

## 61. Runnable: named factory có validation rõ

Lưu **`FactoryInvariantDemo.java`**:

```java
final class Email {
    private final String value;

    private Email(String value) {
        this.value = value;
    }

    static Email of(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("null");
        }
        String cleaned = raw.strip();
        if (cleaned.isBlank() || !cleaned.contains("@")) {
            throw new IllegalArgumentException("invalid email");
        }
        return new Email(cleaned);
    }

    String value() { return value; }
}

public class FactoryInvariantDemo {
    public static void main(String[] args) {
        Email email = Email.of("  a@b.test  ");
        System.out.println(email.value());

        try {
            Email.of("bad");
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 FactoryInvariantDemo.java
java FactoryInvariantDemo
```

Stdout:

```text
a@b.test
invalid email
```

Đây là **validation tối thiểu để minh họa factory**, không phải bộ kiểm tra mọi địa chỉ email theo chuẩn Internet. Production cần policy rõ và có thể cần xác minh ngoài ứng dụng.

## 62. Lỗi 38 — Ném exception kiểu chung, che context

`throw new RuntimeException("error")` tại mọi nơi khó giúp caller quyết định recovery. Chọn loại exception phù hợp:
- `IllegalArgumentException` cho argument sai contract;
- `IllegalStateException` khi trạng thái receiver không cho phép operation;
- Checked `IOException` cho I/O failures theo API;
- Custom exception nếu caller có nhu cầu phân biệt domain failure (không tạo vô ích).

Đừng ném exception từ getter cho trạng thái bình thường “không có”, trừ khi đó là contract cần thể hiện rõ. Đồng thời, đừng dùng return null để giấu network exception.

### Error messages

Nên ghi tên invariant hoặc thông tin đã được phép log, tránh đưa secrets nguyên văn vào exception messages.

## 63. Lỗi 39 — Không tự đánh giá compatibility trước khi đổi class

Một thay đổi tưởng là “cleanup” có thể phá clients:
- Thêm `final` ngăn subclass existing.
- Đổi constructor public thành private.
- Đổi class thành record làm accessor names/serialization behavior khác.
- Đổi `equals/hashCode` làm Map/Set semantics khác.
- Đổi enum constant name, ordinal, external wire code.
- Chuyển mutable getter sang snapshot khiến code dựa vào live view đổi behavior.
- Chuyển checked exception sang unchecked hoặc ngược lại.

Review một thay đổi ở **public API** bằng cách hỏi: “Existing callers compile không? Runtime/binary compatibility? Data đã lưu trước đây vẫn đọc đúng không?”

Không được bảo đảm tương thích chỉ vì các unit tests nội bộ đang xanh.

## 64. Thực hành — review một class nhiều lỗi

Xét anti-pattern **snippet cố ý thiết kế kém**:

```java
class ShoppingCart {
    public static java.util.List<String> items =
            new java.util.ArrayList<>();

    public int totalCents;

    public ShoppingCart(int total) {
        totalCents = total;
    }

    public void setTotalCents(int value) {
        totalCents = value;
    }

    public java.util.List<String> getItems() {
        return items;
    }
}
```

Vấn đề:
1. `items` là static → tất cả carts dùng chung items, trái ý định cart riêng.
2. `items` public mutable → mọi caller mutate không kiểm soát.
3. `totalCents` public mutable → bypass mọi validation.
4. Constructor cho negative total.
5. Setter cho negative total.
6. `getItems` lộ collection nội bộ.
7. Không có operation `addItem` giữ invariant/price rule.
8. Thay total thủ công có thể khác sum của line items.
9. Không có business ID/ownership contract nếu cart là entity.
10. Không có tests cho independent instances.

**Không phải cứ sửa thành record là xong**: nếu cart phải cập nhật items theo workflow, một mutable class với encapsulated operations phù hợp hơn.

## 65. Refactor một cart có operations rõ

Thiết kế gọn cho demo: items gồm giá tiền đơn vị cents dương. Total tính từ items, không giữ một field có thể lệch.

Lưu **`ShoppingCartRefactorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class ShoppingCart {
    private final List<Long> itemPrices = new ArrayList<>();

    void addPrice(long cents) {
        if (cents <= 0) {
            throw new IllegalArgumentException("price");
        }
        itemPrices.add(cents);
    }

    List<Long> itemPrices() {
        return List.copyOf(itemPrices);
    }

    long totalCents() {
        long total = 0;
        for (long price : itemPrices) {
            total = Math.addExact(total, price);
        }
        return total;
    }
}

public class ShoppingCartRefactorDemo {
    public static void main(String[] args) {
        ShoppingCart first = new ShoppingCart();
        ShoppingCart second = new ShoppingCart();

        first.addPrice(200);
        first.addPrice(300);
        second.addPrice(50);

        System.out.println(first.totalCents());
        System.out.println(second.totalCents());
        System.out.println(first.itemPrices());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ShoppingCartRefactorDemo.java
java ShoppingCartRefactorDemo
```

Stdout:

```text
500
50
[200, 300]
```

Class này vẫn là mutable vì items thay đổi. Nó không có shared static list, không public total field và không cho caller sửa trực tiếp internal list.

### Còn cần cải tiến gì cho production?

- Thay Long prices bằng immutable `CartLine(productId, quantity, unitPrice)`.
- Phân biệt currencies, taxes/discounts/rounding.
- Đặt business ID/aggregate lifecycle.
- Xem xét concurrency/transactions và pricing policy.
- Đảm bảo caller không thể bypass rule qua persistence/deserialization.

Điểm chính là **refactor bắt đầu bằng invariant** chứ không phải bằng syntax makeover.

## 66. Checklist phỏng vấn thiết kế class — 12 tiêu chí cốt lõi

Cho điểm từng mục **0, 1 hoặc 2**:

| # | Tiêu chí | 0 — lỗi rõ ràng | 1 — cần cải thiện | 2 — rõ và kiểm chứng được |
| --- | --- | --- | --- | --- |
| 1 | Trách nhiệm/cohesion | Nhiều tác vụ không liên quan | Ranh giới hơi mờ | Một mục đích mạch lạc |
| 2 | Encapsulation/API | Public mutable internals | Có exposure phụ | Bề mặt nhỏ, bảo vệ state |
| 3 | Invariants | Tạo/mutate invalid state dễ dàng | Một vài paths chưa kiểm tra | Mọi path giữ invariant |
| 4 | Constructors/factories | Khởi tạo chưa hoàn chỉnh | Validation rải rác | Tạo thành công là object hợp lệ |
| 5 | Mutability/ownership | Aliases ngoài kiểm soát | Một vài mutable boundaries | Owner/copy policy rõ |
| 6 | Equality/identity | Mâu thuẫn/hash thay đổi | Semantics chưa document | Phù hợp domain, tests |
| 7 | Dependencies/coupling | Hard-code và vòng phụ thuộc | Còn vài điểm tight coupling | Interfaces/composition khi hữu ích |
| 8 | Inheritance/polymorphism | Vi phạm is-a/contract | Extension policy mơ hồ | Substitutability rõ |
| 9 | Error handling | Nuốt lỗi/partial state | Diagnostics còn thiếu | Failure contract và cleanup rõ |
| 10 | Concurrency/lifecycle | Race/resource leak | Chưa test đầy đủ | Strategy phù hợp workload |
| 11 | Testability | Cần network/global state để unit test | Có thể fake một phần | Unit test deterministic |
| 12 | Compatibility/docs | API dễ phá, contract ẩn | Docs/test thiếu | Constraints/changes documented |

**Tổng tối đa: 24 điểm.**

Thang đánh giá *gợi ý nội bộ* (không phải tiêu chuẩn chính thức của Java):
- **21–24:** thiết kế tốt ở phạm vi được đánh giá; vẫn cần test tích hợp và rà bảo mật.
- **17–20:** tương đối ổn, ưu tiên 1–2 lỗ hổng đáng kể.
- **12–16:** cần kế hoạch cải thiện rõ trước khi mở rộng/public API.
- **0–11:** rủi ro cao; nên xem lại abstraction/invariants trước khi thêm tính năng.

**Điều kiện chặn (gates):** dù đạt 22 điểm, không phê duyệt nếu có lỗi nghiêm trọng ở invariants, unauthorized state mutation, data exposure, race nguy hiểm hoặc resource ownership. Score là công cụ giao tiếp, không thay severity/critical review.

## 67. Cách chấm đúng: bằng chứng thay vì cảm giác

Mỗi điểm nên kèm:
- **Source location:** method/constructor/field cụ thể.
- **Điều kiện tái hiện:** input/call sequence gây vấn đề.
- **Invariant bị vi phạm:** điều gì trở thành sai?
- **Mức ảnh hưởng:** data corruption, security, concurrency, resource, maintainability.
- **Đề xuất:** thay đổi nhỏ nhất bảo vệ contract.
- **Test:** test đỏ trước và xanh sau refactor khi khả thi.

Ví dụ:
- **Không tốt:** “Thiết kế dở vì dùng public fields.”
- **Tốt:** “`Wallet.balance` public nên caller gán -1 không qua `deposit/withdraw`; invariant `balance>=0` bị phá. Đề xuất private field + validated methods, thêm test invalid mutation.”

Mục tiêu review là có một đường sửa rõ, tránh cảm tính.

## 68. Chấm một lớp ví dụ

Với anti-pattern `ShoppingCart` ở trên, giả sử bạn có bằng chứng:
- Trách nhiệm: 1/2 — xử lý cart nhưng giữ total rời items.
- Encapsulation: 0/2 — public static mutable list/public total.
- Invariants: 0/2 — negative total được chấp nhận.
- Construction: 0/2 — constructor không validate.
- Ownership: 0/2 — list chia sẻ toàn ứng dụng.
- Equality/identity: 1/2 — chưa có contract rõ.
- Dependencies: 2/2 — không hard-code external dependency trong demo.
- Inheritance: 1/2 — class mở nhưng extension contract không rõ.
- Error handling: 0/2 — không báo input invalid.
- Concurrency/lifecycle: 0/2 — static ArrayList mutable có shared races.
- Testability: 1/2 — có thể test nhưng static state gây nhiễm giữa tests.
- Compatibility/docs: 0/2 — không có API contract.

**Tổng minh họa: 6/24**. Đây chỉ là ví dụ chấm theo bằng chứng nêu ra, không phải điểm bắt buộc cho mọi class tên ShoppingCart.

Sau khi refactor, **chấm lại trên behavior/test**; đừng tăng điểm chỉ vì class có thêm private/final keywords.

## 69. Bộ kiểm tra nhanh trước commit

- [ ] Class name và trách nhiệm chính được mô tả trong một câu.
- [ ] Public API chỉ expose những thứ callers cần.
- [ ] Không có public mutable field trừ lý do thiết kế được kiểm chứng.
- [ ] Constructors/factories tạo object hợp lệ hoặc ném exception.
- [ ] Không publish `this` sớm; không gọi overridable method nguy hiểm trong constructor.
- [ ] Mọi state-changing method bảo toàn invariants.
- [ ] Ownership của collections/arrays/references được xác định.
- [ ] Defensive copy của mutable input/output khi API hứa immutable snapshot.
- [ ] `final`/record/enum không bị hiểu sai thành deep immutability.
- [ ] `equals/hashCode` phù hợp identity/value contract.
- [ ] Không mutate hash fields khi object đang ở Set/Map keys.
- [ ] `toString`/logs không tiết lộ secrets.
- [ ] Không có global static mutable state không chủ đích.
- [ ] Có concurrency strategy nếu shared mutable state được dùng nhiều threads.
- [ ] Inheritance có is-a/substitution rõ; nếu không, composition.
- [ ] Override/overload được phân biệt; dùng `@Override`.
- [ ] Sealed/final/non-sealed extension policy đúng ý định.
- [ ] Generics dùng parameterized types, tránh raw/unchecked code.
- [ ] Null/invalid inputs có contract rõ, không swallow exceptions.
- [ ] Resource owners đóng bằng AutoCloseable/try-with-resources.
- [ ] ThreadLocal/listener/registry registrations được cleanup.
- [ ] Dependencies có thể fake/test nếu liên quan I/O.
- [ ] Behavior tests bao gồm happy path và boundary/failure cases.
- [ ] API/documentation/serialization compatibility được xem khi refactor.

## 70. Bộ kiểm tra dài hơn cho review public API

### API surface
- [ ] Mọi public/protected method có lý do tồn tại.
- [ ] Không bắt consumer biết internal fields để làm nghiệp vụ.
- [ ] Tên method phản ánh mutation, I/O, ownership, exception semantics.
- [ ] Package/module visibility phù hợp, không mở package phản xạ vô điều kiện.
- [ ] Không ràng buộc public API vào một implementation cụ thể nếu interface đủ.

### Construction
- [ ] Các overloads không tạo ambiguity khó hiểu.
- [ ] Không có partially valid instance sau constructor thành công.
- [ ] Null/empty/range/cross-field rules được validate.
- [ ] Constructor failure không để lại resource leak.
- [ ] Không khởi thread, register listener hoặc publish `this` quá sớm.

### State và immutability
- [ ] State có thể thay đổi chỉ qua API được kiểm soát.
- [ ] Snapshot khác live view được đặt tên/document rõ.
- [ ] Các mutable nested objects được xử lý ở mức đủ sâu.
- [ ] Nếu records có arrays/list/BigDecimal, equality semantics đúng domain.
- [ ] Nếu dùng final class, không nhầm final với immutable/thread-safe.

### Identity, equality, collections
- [ ] Entity ID khác object identity và value equality nếu cần.
- [ ] `equals` có reflexive/symmetric/transitive/consistent/null behaviors phù hợp.
- [ ] `hashCode` nhất quán với equals và ổn định trong usage.
- [ ] Không dùng mutable hashing key trong map.
- [ ] Enum codes dùng external stable mapping, không ordinal mặc định.

### Behavior và error paths
- [ ] Operations được đặt gần owner của invariant.
- [ ] Exceptions rõ type/cause, không swallow.
- [ ] Multi-step updates có transaction/compensation strategy.
- [ ] Không trả success khi một bước quan trọng bị lỗi.
- [ ] Cleanup chạy trên mọi exit path.

### Concurrency
- [ ] Object được share hay thread-confined?
- [ ] Visibility và atomicity là những yêu cầu khác nhau.
- [ ] Locking strategy không tạo deadlock dễ thấy.
- [ ] Không callback external code khi giữ lock rộng nếu tránh được.
- [ ] Snapshot nhiều fields có tính nhất quán phù hợp.
- [ ] ThreadLocal/context cleanup theo request/task.

### Bảo mật, vận hành, testing
- [ ] Không log secrets/PII không cần thiết.
- [ ] Mọi input không tin cậy được validate tại boundary.
- [ ] Không giữ resources quá lâu bởi caches/registries.
- [ ] Metrics/logging đủ để debug mà không tiết lộ dữ liệu.
- [ ] Dependencies fake được trong unit tests.
- [ ] Có negative tests và regression tests.
- [ ] Changes của public contracts có migration path.

## 71. Thực hành 1 — tìm đường phá invariant

```java
class Temperature {
    public int celsius;
    Temperature(int celsius) { this.celsius = celsius; }
}
```

**Yêu cầu:** giả sử business range `-50..100`, chỉ ra lỗi và sửa.

**Đáp án:** Constructor không validate; public mutable field cho client bỏ qua validation. Đặt private field, validate constructor và mọi operation thay đổi; nếu không cần mutation, dùng immutable class/record với compact validation.

## 72. Thực hành 2 — alias qua getter

```java
class Labels {
    private final List<String> labels = new ArrayList<>();
    List<String> getLabels() { return labels; }
}
```

**Đáp án:** Lộ mutable list. Nếu contract là read-only snapshot, trả `List.copyOf(labels)`; nếu caller cần mutate, định nghĩa operations và test invariants.

## 73. Thực hành 3 — record chứa mutable array

```java
record Token(byte[] bytes) { }
```

**Đáp án:** Không deep immutable; accessor trả array; default equality của array component không so nội dung. Nếu yêu cầu content value, dùng immutable wrapper + clone + Arrays.equals/hashCode, hoặc customize record thật cẩn thận.

## 74. Thực hành 4 — mutable map key

Class có `equals/hashCode` dùng `name`, nhưng có `setName`; object được dùng làm key.

**Đáp án:** Rủi ro lookup không ổn định khi name thay đổi. Dùng immutable name/key hoặc stable ID độc lập mutation.

## 75. Thực hành 5 — constructor gọi override

Base constructor gọi `render()`; Child override dùng final field initializer.

**Đáp án:** Override có thể quan sát default field value vì Child chưa initialize. Bỏ dynamic dispatch khỏi constructor hoặc thiết kế lifecycle sau construction.

## 76. Thực hành 6 — static cho data của request

`static String lastUserId` nằm trong Request object.

**Đáp án:** State bị chia sẻ; request khác có thể ghi đè. Đặt instance field hoặc explicit request context, test hai instances độc lập.

## 77. Thực hành 7 — raw List

`List data = new ArrayList();` và caller thêm cả String/Integer.

**Đáp án:** Raw type làm mất generic type safety; dùng `List<String> data = new ArrayList<>()` hoặc wildcard/abstraction hợp lý.

## 78. Thực hành 8 — inheritance sai

`EmailService extends DatabaseConnection` để tận dụng `execute`.

**Đáp án:** Không phải is-a; dùng dependency/composition `EmailService(DatabaseClient client)`.

## 79. Thực hành 9 — logic validation rải rác

Từng setter kiểm tra một phần nhưng caller phải gọi đúng thứ tự.

**Đáp án:** Constructor/factory nhận đầy đủ required state; operations chuyển trạng thái theo đơn vị nghiệp vụ. Tránh invalid intermediate externally observable states.

## 80. Thực hành 10 — enum ordinal được lưu database

Enum thêm constant vào giữa làm records cũ đọc sai.

**Đáp án:** Dùng stable explicit code và migration mapping của dữ liệu ordinal legacy.

## 81. Thực hành 11 — singleton gây nhiễm test

Một singleton mutable cache giữ records từ testcase trước.

**Đáp án:** Xác định lifecycle và reset/eviction; tốt hơn inject cache per test/service scope hoặc dùng immutable settings. Không để test order chi phối kết quả.

## 82. Thực hành 12 — tài nguyên và GC

Class đóng socket trong `finalize()`.

**Đáp án:** Dùng AutoCloseable/try-with-resources với owner rõ. Java 17 finalize đã deprecated từ Java 9, GC timing không bảo đảm resource release đúng lúc.

## 83. Thực hành 13 — List.copyOf với mutable elements

`record Snapshot(List<MutableOrder> orders)` dùng List.copyOf.

**Đáp án:** Chỉ snapshot structure; các MutableOrder elements còn thay đổi. Chuyển thành immutable OrderView elements hoặc có copy strategy phù hợp.

## 84. Thực hành 14 — swallowed exception

`try { send(); } catch(Exception ignored) {}` rồi trả success.

**Đáp án:** Method báo thành công dù operation có thể thất bại. Xây result/exception contract, retry/compensate nếu hợp lệ, log context không lộ secret.

## 85. Thực hành 15 — object identity vs business ID

Hai `Customer` objects có cùng name nhưng different customer IDs.

**Đáp án:** Không lấy name equality làm entity identity. Xem stable business ID/lifecycle, tránh autogenerated equals theo mọi mutable fields.

## 86. Thực hành 16 — enum shared mutable field

`enum Flag { ACTIVE; int lastOrderId; }`.

**Đáp án:** lastOrderId bị share toàn application trong một enum constant; chuyển per-order data vào class/record của order.

## 87. Thực hành 17 — lock và callback

Class giữ synchronized lock rồi gọi arbitrary listener code.

**Đáp án:** Dễ deadlock/reentrancy/latency nếu callback block hoặc gọi lại class. Cân nhắc snapshot listeners dưới lock rồi invoke ngoài lock theo contract; thiết kế concurrency boundaries rõ.

## 88. Thực hành 18 — constructor overload khó hiểu

`new RetryPolicy(3, true, false)`.

**Đáp án:** Các booleans khó hiểu. Dùng named factory/builder hoặc enum options có semantics rõ, không builder tràn lan nếu chỉ 2 params đơn giản.

## 89. Thực hành 19 — record DTO chứa password

`record LoginRequest(String username, String password)` được log thẳng bằng `logger.info("{}", request)`.

**Đáp án:** Generated toString có thể lộ password. Redact/sanitize logs, tránh log raw request, định nghĩa safe representation nếu cần.

## 90. Thực hành 20 — class lớn

Một OrderManager có cả payment client, SQL, email templates, product pricing và receipt renderer.

**Đáp án:** Xem change drivers; tách collaborators theo cohesive responsibility, giữ một orchestration layer hợp lý. Không tạo class mới chỉ để giảm số dòng.

## 91. Trắc nghiệm Đúng/Sai

1. Code compile nghĩa là invariant được bảo toàn.
2. `private` fields giúp giới hạn đường truy cập nhưng không tự bảo đảm invariant.
3. `final class` không thể có mutable instance fields.
4. `record` auto deep-copy List/array components.
5. `List.copyOf` tạo unmodifiable shallow snapshot.
6. Override equals mà quên hashCode có thể gây lỗi trong HashSet.
7. Hai instances equal theo value luôn có cùng reference identity.
8. HashMap key với mutable hash fields là rủi ro.
9. `static` field thuộc từng instance của class.
10. `volatile count++` bảo đảm atomic increment.
11. Composition thường phù hợp nếu quan hệ là has-a.
12. Gọi overridable method trong superclass constructor có thể chạy trước child initialization.
13. `@Override` giúp compiler kiểm tra ý định override.
14. Dùng raw types làm type safety mạnh hơn diamond.
15. `try-with-resources` giúp gọi close cả trên exception paths.
16. Java 17 `instanceof` pattern matching là ổn định.
17. Java 17 pattern switch trên sealed class mặc định là feature không preview.
18. Enum constants có thể chứa mutable shared fields nếu code khai báo.
19. Một điểm số checklist cao luôn đủ phê duyệt code dù có security flaw nghiêm trọng.
20. Review tốt cần chỉ ra code, invariant, ảnh hưởng và test.

**Đáp án:** 1 sai; 2 đúng; 3 sai; 4 sai; 5 đúng; 6 đúng; 7 sai; 8 đúng; 9 sai; 10 sai; 11 đúng; 12 đúng; 13 đúng; 14 sai; 15 đúng; 16 đúng; 17 sai; 18 đúng; 19 sai; 20 đúng.

## 92. Kiểu bài tự đánh giá có điểm

**Đề:** Một class `UserSettings` có các đặc điểm:
- `public static Map<String,String> values`.
- Constructor không validate null.
- Getter trả map trực tiếp.
- Method `save()` tự mở file nhưng không đóng stream.
- `equals` so toàn bộ map; `hashCode` dùng identity từ Object.
- `toString` in cả API token.
- Test chỉ chạy trường hợp một user, một thread.

**Yêu cầu:** Tìm ít nhất sáu lỗi, xếp thứ tự và đề xuất giải pháp.

**Gợi ý đáp án:**
1. Shared static mutable map phá cô lập users (Critical).
2. Public map cho caller bypass validation (High).
3. Null input không validate (High nếu required).
4. Getter trả internal map (High).
5. File stream không close (High).
6. Equals/hashCode inconsistent (High).
7. toString lộ token (Critical security).
8. Tests thiếu isolation/multiple users/concurrency/failure (High).
9. Đơn vị trách nhiệm của storage và in-memory settings chưa rõ; cân nhắc tách repository (Medium).

**Phương án:** value `SettingsSnapshot` immutable với validated copies; per-user owner object; injected repository/serializer; try-with-resources; safe logging; stable equality policy; tests negative/cross-user/error paths.

## 93. Một quy trình review trong 15 phút (gợi ý)

**Phút 1–3: Đọc API và vai trò**
- Đọc class declaration, constructors và public methods.
- Viết một câu: “Lớp này chịu trách nhiệm ...”.
- Phân loại mutable entity/value/data carrier/resource/service/enum symbol.

**Phút 4–7: Tìm đường phá invariant**
- Public fields/setters;
- Nullable required fields;
- Aliasing qua arrays/collections;
- Constructor escape;
- Multi-step state transition.

**Phút 8–11: Quan hệ và runtime**
- Identity, equals/hash;
- Inheritance/composition;
- Static/shared state;
- Concurrency/resource ownership;
- Exception paths.

**Phút 12–15: Chấm và đề xuất**
- Chấm 12 tiêu chí 0–2;
- Nêu 1–3 rủi ro cao nhất;
- Viết test tái hiện;
- Đưa ra một refactor nhỏ có phạm vi kiểm soát;
- Ghi compatibility risks nếu là public API.

Thời gian chỉ là hướng dẫn tổ chức review nhanh; một class security-sensitive hoặc library core có thể cần điều tra lâu hơn đáng kể.

## 94. Thế nào là “thiết kế tốt” trong Java?

Không phải:
- Có nhiều interfaces, design patterns hoặc getters;
- Có càng ít dòng càng tốt;
- Mọi class đều final, immutable, record hoặc enum;
- Không dùng static ở bất kỳ đâu;
- Dùng dependency injection framework cho mọi constructor;
- Có điểm checklist cao nhưng thiếu tests.

Thường là:
- **Mục đích dễ hiểu** và trách nhiệm mạch lạc;
- **Invariant được bảo vệ** ngay từ construction;
- **Public API khó dùng sai** và hợp đồng được mô tả rõ;
- **Đúng semantics** identity/value/mutability/lifecycle;
- **Dependencies phù hợp**, tránh coupling không cần;
- **Failure paths và concurrency** có kế hoạch;
- **Đủ bằng chứng test** cho hành vi quan trọng;
- **Dễ thay đổi an toàn** mà không làm vỡ những clients không liên quan.

**Chất lượng là mức phù hợp với yêu cầu thực tế**, không phải số lượng keyword `final`, `private` hay số design patterns.

## 95. Kết luận: dùng rubric để làm class tốt lên từng bước

Một class Java 17 tốt có thể là:
- Mutable aggregate giữ business identity và state transitions;
- Immutable value class bọc array/representation đặc biệt;
- Record mô tả value components với validation và defensive copies;
- Enum công bố finite states/codes;
- Service phụ thuộc collaborators qua interfaces;
- AutoCloseable wrapper chịu trách nhiệm explicit resource release.

Không có lựa chọn luôn đúng. **Sai lầm thường gặp nhất là không nêu rõ contract rồi để callers quyết định ngẫu nhiên.** Hãy kiểm tra những gì object hứa hẹn, thử phá lời hứa bằng invalid inputs/aliases/overrides/concurrency, rồi sửa API sao cho invariant được giữ ở chỗ phù hợp.

**Ba câu hỏi cuối trước khi approve:**

1. Caller có thể tạo hoặc đưa object vào trạng thái **không hợp lệ** qua một đường API hợp lệ không?
2. Khi code fail hoặc chạy đồng thời, object có còn **đúng contract** và cleanup tài nguyên đúng không?
3. Một maintainer chưa biết implementation có thể **hiểu, test và thay đổi** class mà không phải đoán semantics không?

Nếu cả ba trả lời được bằng **code, tests và API contract**, thiết kế đã có nền tảng đáng tin.

## 96. Tài liệu tham khảo chính thức Java SE 17

- **JLS `8 — Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html
- **JLS `8.10 — Record Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10
- **JLS `8.9 — Enum Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9
- **JLS `8.1.1.2 — sealed/final class modifiers**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2
- **JLS `15.12 — Method Invocation Expressions**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12
- **Java SE 17 `Object.equals/hashCode/toString` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html
- **Java SE 17 `List.copyOf` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)
- **Java SE 17 `AutoCloseable` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
- **Java SE 17 `AtomicReference` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html
- **Java SE 17 `Enum` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html
