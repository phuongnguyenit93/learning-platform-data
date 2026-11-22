# Kiểu giao (intersection type) và quyền truy cập thành viên trong Java Generics

Trong Java Generics, một tham số kiểu không nhất thiết chỉ bị giới hạn bởi một lớp hoặc interface. Ta có thể yêu cầu kiểu thực tế **đồng thời thỏa nhiều giới hạn** (*multiple bounds*) bằng toán tử `&`. Các ràng buộc này tạo nên một **kiểu giao (intersection type)**: một giá trị phải phù hợp với tất cả các thành phần của giao.

Ví dụ:

```java
interface Named {
    String name();
}

interface Versioned {
    int version();
}

static <T extends Named & Versioned> String describe(T item) {
    return item.name() + "@" + item.version();
}
```

Hai interface và phương thức trên là **mã minh họa**, cần đặt trong class phù hợp trước khi biên dịch. Chữ ký `<T extends Named & Versioned>` bảo đảm rằng **bất kỳ kiểu thực tế `T` nào được chấp nhận** đều có thể dùng qua cả hợp đồng `Named` và `Versioned`. Vì vậy, trong thân phương thức, compiler cho gọi cả `item.name()` lẫn `item.version()` mà không cần cast.

**Cốt lõi:** với một biến kiểu `T extends A & B`, **tập thành viên có thể truy cập lúc biên dịch được quyết định bởi những thành viên hợp lệ của các giới hạn `A` và `B`**, cùng các quy tắc truy cập, kế thừa và giải quyết phương thức của Java. Không phải mọi phương thức của lớp runtime đều tự nhiên được nhìn thấy.

## 1. Intersection type nghĩa là gì?

Trong lý thuyết kiểu của Java, giao `A & B` biểu thị yêu cầu một giá trị phải đồng thời phù hợp với `A` **và** `B`. Nó không tạo ra một interface Java mới mang tên `A&B`; đó là **mô tả kiểu kết hợp** trong những ngữ cảnh cú pháp cho phép.

Hãy tưởng tượng:

- `Named` là giao diện cấp khả năng `name()`.
- `Versioned` là giao diện cấp khả năng `version()`.
- `Document` là lớp triển khai cả `Named` và `Versioned`.

Khi `Document implements Named, Versioned`, một đối tượng `Document` có thể được dùng tại vị trí yêu cầu `Named`, tại vị trí yêu cầu `Versioned` hoặc tại vị trí một type parameter phải thỏa **đồng thời** hai interface.

```java
class Document implements Named, Versioned {
    @Override
    public String name() {
        return "Java";
    }

    @Override
    public int version() {
        return 17;
    }
}
```

Đây là **định nghĩa lớp minh họa** dựa trên hai interface đã khai báo. `Document` thỏa ràng buộc `<T extends Named & Versioned>`; còn một lớp chỉ `implements Named` thì không thỏa, dù nó có phương thức `name()`.

Phân biệt với kế thừa thông thường:

| Khai báo | Ràng buộc compile-time | Có thể gọi trên biến kiểu `T` |
|---|---|---|
| `<T>` | Không có bound tường minh; upper bound ngầm là `Object` | Những thành viên `Object` truy cập được |
| `<T extends Named>` | `T` phù hợp với `Named` | `name()` và các thành viên hợp lệ từ bound |
| `<T extends Named & Versioned>` | `T` phù hợp với cả hai | `name()` **và** `version()` |
| `<T extends Asset & Named & Versioned>` | `T` là subtype của `Asset` và phù hợp hai interface | Thành viên truy cập được của cả `Asset`, `Named`, `Versioned` |

**Chú ý:** `extends` trong khai báo generic bound dùng chung cho cả **class bound** và **interface bounds**, kể cả khi Java dùng từ khóa `implements` ở khai báo `class Document implements Named`.

## 2. Nhận diện cú pháp intersection để phân tích kiểu

Một type parameter dùng `&` để kết hợp nhiều upper bounds:

```java
<T extends Named & Versioned>
<T extends Asset & Named & Versioned>
```

Đây là các **mẫu khai báo** đặt vào class hoặc generic method phù hợp, không phải statements Java độc lập. Nếu `Asset` là class, nó phải đứng đầu; các bound còn lại là interfaces. `T` cần thỏa **tất cả** bounds. Dấu phẩy `,` dùng để tách **các type parameters khác nhau**, còn `&` biểu diễn intersection của những yêu cầu trên **một** parameter.

Trong bài này, điều quan trọng hơn cú pháp là: tại mỗi vị trí sử dụng `T`, compiler cho phép gọi những member nào từ `Named`, `Versioned` và `Asset`? Ví dụ, chỉ `<T extends Named & Versioned>` **không cho gọi** một `id()` riêng của `Asset`, dù object thực có thể là subclass của `Asset`. Phải ghi rõ bound cung cấp method đó và tuân thủ access modifiers.

Giới hạn phải tương thích; các interface có signature/return type xung đột hoặc các instantiations không tương thích của cùng generic interface không tạo ra intersection hợp lệ. Khi xét runtime, phân biệt **intersection bound ở khai báo** với **intersection cast** có kiểm tra kiểu tương ứng.

## 3. Tại sao intersection bound thay đổi quyền truy cập thành viên?

Xét hai method nhận cùng loại object thực tế nhưng có hợp đồng kiểu khác nhau:

```java
static <T extends Named> String oneCapability(T item) {
    return item.name();
}

static <T extends Named & Versioned> String twoCapabilities(T item) {
    return item.name() + "@" + item.version();
}
```

Hai phương thức là **đoạn minh họa** cần đặt trong class nhìn thấy `Named` và `Versioned`.

Trong `oneCapability`, compiler chỉ có bảo đảm `T extends Named`. Nó cho gọi `name()`, nhưng không có cơ sở cho phép `item.version()`, **ngay cả khi người gọi sau này truyền một `Document` có cả hai method**.

Trong `twoCapabilities`, compiler biết đồng thời hai giới hạn nên chấp nhận cả hai lời gọi. Đây là khác biệt giữa **kiểu tĩnh** và **lớp runtime**:

- Kiểu runtime của object có thể là `Document`, `Deployment` hoặc bất kỳ lớp triển khai đủ interface.
- **Kiểu tĩnh `T` cùng các bounds trong chữ ký** quyết định method nào được gọi hợp lệ trong thân generic method.
- Runtime dynamic dispatch vẫn chọn đúng phần triển khai của object khi method được gọi.

Mã sau **không biên dịch**, dù lời gọi thực tế có thể chỉ truyền `Document`:

```java
// static <T extends Named> int invalid(T item) {
//     return item.version(); // Không có version() trong bound Named.
// }
```

Giải pháp tốt là bổ sung `& Versioned` khi API **thực sự cần** cả hai khả năng, hoặc nhận một interface duy nhất đã mô tả đầy đủ hợp đồng. Không dùng cast tùy tiện bên trong generic method để “sửa” một bound chưa đủ mạnh: cast sẽ chuyển lỗi từ compile-time sang runtime nếu đối tượng không thỏa điều kiện.

## 4. Class bound đứng đầu, interface bounds theo sau

Khi cần sử dụng đồng thời hành vi của một lớp cơ sở và nhiều interface:

```java
class Asset {
    private final String id;

    Asset(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}

interface Named {
    String name();
}

interface Versioned {
    int version();
}

static <T extends Asset & Named & Versioned> String describe(T item) {
    return item.id() + ":" + item.name() + "@" + item.version();
}
```

Đây là **một cụm khai báo minh họa**: các interface, class và method cần nằm ở các vị trí hợp lệ (method trong class) trước khi biên dịch thành một chương trình. Phần giới hạn có ba khả năng:

- `Asset` cho phép truy cập `id()`.
- `Named` cho phép truy cập `name()`.
- `Versioned` cho phép truy cập `version()`.

Một kiểu thực tế `Document extends Asset implements Named, Versioned` thỏa tất cả. Nhưng `Document` không nhất thiết là lớp duy nhất thỏa ràng buộc đó.

**Không thể đảo thành `<T extends Named & Asset & Versioned>`** nếu `Asset` là class; thứ tự class-first là quy tắc cú pháp/kiểu của Java, không chỉ quy tắc trình bày. Nếu các bound đều là interface, Java cho phép đặt một interface ở vị trí đầu, song **thứ tự vẫn có thể quan trọng với erasure và binary compatibility** (xem phần 9).

Các quyền truy cập trong thân generic method còn bị chi phối bởi Java access control: `private`, package-private, `protected`, `public` không bị vô hiệu hóa bởi kiểu giao. Ví dụ một trường `private` trong `Asset` không tự truy cập được từ một class khác chỉ vì `T extends Asset`. Dùng API truy cập hợp lệ như `id()`.

## 5. Ví dụ Java 17 chạy độc lập

Lưu toàn bộ chương trình sau vào tệp **`IntersectionBoundsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class IntersectionBoundsDemo {

    interface Named {
        String name();
    }

    interface Versioned {
        int version();
    }

    static class Asset {
        private final String id;

        Asset(String id) {
            this.id = id;
        }

        public String id() {
            return id;
        }
    }

    static final class Document extends Asset
            implements Named, Versioned {
        private final String title;
        private final int revision;

        Document(String id, String title, int revision) {
            super(id);
            this.title = title;
            this.revision = revision;
        }

        @Override
        public String name() {
            return title;
        }

        @Override
        public int version() {
            return revision;
        }
    }

    static final class Deployment implements Named, Versioned {
        private final String environment;
        private final int release;

        Deployment(String environment, int release) {
            this.environment = environment;
            this.release = release;
        }

        @Override
        public String name() {
            return environment;
        }

        @Override
        public int version() {
            return release;
        }
    }

    static final class NamedOnly implements Named {
        private final String text;

        NamedOnly(String text) {
            this.text = text;
        }

        @Override
        public String name() {
            return text;
        }
    }

    static <T extends Named & Versioned> String label(T item) {
        return item.name() + "#" + item.version();
    }

    static <T extends Asset & Named & Versioned>
            String describe(T item) {
        return item.id() + ":" + item.name() + "@"
                + item.version();
    }

    static <T extends Named & Versioned>
            List<String> labels(List<T> items) {
        List<String> result = new ArrayList<>();
        for (T item : items) {
            result.add(label(item));
        }
        return List.copyOf(result);
    }

    static <T extends Number & Comparable<T>> T larger(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        Document first = new Document("doc-7", "Generics", 3);
        Document second = new Document("doc-8", "Streams", 2);
        Deployment release = new Deployment("prod", 5);

        System.out.println("full: " + describe(first));
        System.out.println("interfaces: " + label(release));

        Named namedView = first;
        System.out.println("named view: " + namedView.name());
        System.out.println("cast version: "
                + ((Named & Versioned) namedView).version());

        System.out.println("bulk: " + labels(List.of(first, second)));
        System.out.println("larger: " + larger(3, 7));

        Object oneCapability = new NamedOnly("solo");
        System.out.println("has both: "
                + (oneCapability instanceof Named
                && oneCapability instanceof Versioned));

        try {
            ((Named & Versioned) oneCapability).name();
            System.out.println("unexpected");
        } catch (ClassCastException exception) {
            System.out.println("cast failed: ClassCastException");
        }
    }
}
```

Chạy trong thư mục chứa tệp, với JDK 17 hoặc mới hơn:

```bash
javac IntersectionBoundsDemo.java
java IntersectionBoundsDemo
```

**Kết quả stdout:**

```text
full: doc-7:Generics@3
interfaces: prod#5
named view: Generics
cast version: 3
bulk: [Generics#3, Streams#2]
larger: 7
has both: false
cast failed: ClassCastException
```

### Phân tích cơ chế theo output

1. **`describe(first)` yêu cầu ba bounds:** `Document` là subtype của `Asset` đồng thời triển khai `Named` và `Versioned`. Thân `describe` gọi `id()`, `name()`, `version()` hợp lệ; kết quả `doc-7:Generics@3`.
2. **`label(release)` chỉ yêu cầu hai interface:** `Deployment` không kế thừa `Asset` nhưng vẫn hợp lệ với `<T extends Named & Versioned>`. Nó trả `prod#5`. Nếu gọi `describe(release)`, compiler sẽ từ chối vì `Deployment` không thỏa class bound `Asset`.
3. **`Named namedView = first;` làm mất quyền truy cập tĩnh vào `version()`:** qua biến này chỉ nhìn thấy hợp đồng `Named`. Lời gọi `namedView.name()` hợp lệ; `namedView.version()` sẽ không biên dịch dù object thực tế là `Document`.
4. **`((Named & Versioned) namedView)` là intersection cast:** nó yêu cầu runtime object phù hợp **cả hai** interface; `first` thỏa điều kiện và cho gọi `version()`, in `3`.
5. **`labels(List.of(first, second))` giữ `T = Document`:** danh sách các `Document` thỏa hai bounds; vòng lặp trong method generic gọi được cả `name()` và `version()`, trả danh sách chuỗi `[Generics#3, Streams#2]`.
6. **`larger(3, 7)` thể hiện giao giữa class và generic interface:** `T` được suy luận thành `Integer` qua boxing; `Integer` là subtype của `Number` và triển khai `Comparable<Integer>`. `compareTo` chọn `7`.
7. **`NamedOnly` chỉ thỏa một bound:** biểu thức `instanceof Named && instanceof Versioned` trả `false`. Intersection cast ở ví dụ cuối không đạt đủ hai kiểm tra runtime và ném `ClassCastException`, được bắt để in một dòng ổn định.

**Phân biệt rõ:** các type bounds trong generic method giúp kiểm tra **trước khi chạy**; intersection cast `(A & B) object` thực hiện **chuyển kiểu tường minh có kiểm tra runtime**. Hai cơ chế liên quan đến cùng ý tưởng giao các hợp đồng nhưng không thay thế nhau.

## 6. Intersection bounds trong generic class và interface

Không chỉ phương thức, generic class và generic interface cũng có thể khai báo nhiều bounds:

```java
interface Named {
    String name();
}

interface Versioned {
    int version();
}

final class Registry<T extends Named & Versioned> {
    private final T item;

    Registry(T item) {
        this.item = item;
    }

    String describe() {
        return item.name() + "@" + item.version();
    }

    T get() {
        return item;
    }
}
```

Đây là **định nghĩa minh họa riêng**, không sao chép các interface trùng tên vào cùng scope với những khai báo trước đó. Với `Registry<Document>` nếu `Document` triển khai đủ interface:

- Khi xây `Registry<Document>`, type argument `Document` phải thỏa cả hai bounds.
- Trong lớp `Registry`, trường `item` có kiểu tĩnh `T`, nên có thể gọi cả `name()` và `version()`.
- Phương thức `get()` trả **đúng `T`**, giữ lại kiểu cụ thể của object cho người gọi.
- Với lớp chỉ triển khai `Named`, `Registry<NamedOnly>` sẽ không biên dịch.

Một generic interface cũng có thể tự khai báo bound:

```java
interface Inspector<T extends Named & Versioned> {
    String inspect(T item);
}
```

Đây là một interface minh họa; class triển khai `Inspector<Document>` sẽ dùng đúng `T = Document` trong chữ ký. Nếu một generic subclass kế thừa hoặc thực thi type đã có bound, lớp con phải truyền đối số kiểu thỏa mọi ràng buộc của supertype; ví dụ `class AdvancedRegistry<U extends Named & Versioned> extends Registry<U>` chỉ hợp lệ về mặt bound nếu `Registry` được thiết kế cho kế thừa (không `final`) và có constructor/phương thức cần thiết.

## 7. Intersection cast và cách kiểm tra runtime

Java cho phép một số biểu thức cast dùng nhiều reference bounds:

```java
Object object = new Document("doc-1", "Intro", 1);
Named named = (Named & Versioned) object;
String title = named.name();
```

Đây là **các dòng minh họa**, giả sử đã có `Document`, `Named` và `Versioned` như trong ví dụ chạy độc lập và đặt vào method. Cast bảo đảm runtime object đáp ứng cả `Named` và `Versioned`, nhưng biến `named` **được khai báo là `Named`**, nên về sau chỉ có các method của `Named` ở kiểu tĩnh của biến.

Nếu muốn gọi cả hai ngay trong một biểu thức, dùng cast làm kiểu của receiver:

```java
int version = ((Named & Versioned) object).version();
```

Lưu ý dấu ngoặc: `(Named & Versioned)` là phần kiểu trong cast; `((Named & Versioned) object)` là biểu thức đối tượng đã cast. Nếu object không triển khai đủ hai interface, lệnh cast có thể ném `ClassCastException` ở runtime.

Trước khi cast, có thể kiểm tra riêng:

```java
if (object instanceof Named named
        && object instanceof Versioned versioned) {
    System.out.println(named.name() + "@" + versioned.version());
}
```

`instanceof` pattern trong ví dụ trên có sẵn ở Java 17. Nó thiết lập hai biến pattern với hai kiểu tĩnh riêng; không tạo một biến được khai báo bằng cú pháp `Named & Versioned` như tên kiểu thông thường.

**Phân biệt các vị trí cú pháp:**

| Vị trí | Viết được? | Ghi chú |
|---|---|---|
| Khai báo type parameter `<T extends A & B>` | Có | Cách chủ đạo để dùng intersection bounds trong generic API |
| Cast `(A & B) object` | Có nếu các bound/cast tương thích | Kiểm tra runtime; có thể ném `ClassCastException` |
| Khai báo biến `A & B value` | Không | Không phải cú pháp khai báo biến trực tiếp thông thường |
| Type argument `List<A & B>` | Không | Type argument không viết trực tiếp dưới dạng giao như vậy |
| Wildcard `List<? extends A & B>` | Không | Wildcard bound trong Java không dùng cú pháp giao nhiều thành phần này |
| Type check `object instanceof A & B` | Không | Kiểm tra riêng hai loại bằng `&&` hoặc pattern phù hợp |

Dù không viết được `List<A & B>`, bạn có thể viết generic method nhận `List<T>` với `<T extends A & B>`, như `labels(List<T>)` trong ví dụ. Tên `T` là cách biểu đạt mối liên hệ kiểu an toàn giữa danh sách đầu vào và các thành viên được phép truy cập.

## 8. Interface xung đột: không phải giao nào cũng hợp lệ

Hai bound phải tương thích về các method được kế thừa. Xét hai interface không tương thích:

```java
interface A {
    String read();
}

interface B {
    Integer read();
}

// static <T extends A & B> T invalid(T value) { return value; }
```

Đây là **ví dụ lỗi**, trong đó hai interface có method cùng tên và cùng danh sách tham số nhưng kiểu trả về không thể cùng được một triển khai hợp lệ đáp ứng. Không thể chỉ thêm `&` rồi tự động “kết hợp” hai kiểu trả về. Java sẽ áp dụng quy tắc xung đột method/return-type trong quá trình kiểm tra bound hoặc khi khai báo class thực thi; thiết kế nên tránh các hợp đồng loại trừ nhau.

Một kiểu xung đột khác liên quan tới **default methods**:

```java
interface Left {
    default String tag() {
        return "L";
    }
}

interface Right {
    default String tag() {
        return "R";
    }
}

// class Ambiguous implements Left, Right { }
// Sai nếu không giải quyết hai default tag() xung đột.

final class Resolved implements Left, Right {
    @Override
    public String tag() {
        return Left.super.tag() + Right.super.tag();
    }
}
```

Đây là **cụm khai báo minh họa**, không nằm trong chương trình `IntersectionBoundsDemo.java`. `Resolved.tag()` trả `"LR"` nhờ override tường minh. Trong thiết kế bound, không được xem `<T extends Left & Right>` là cách tự động giải quyết các default method mâu thuẫn; phải xem tính hợp lệ của giao diện kết hợp và cung cấp một hợp đồng không xung đột.

Một trường hợp cần phân biệt: hai interface cùng khai báo **một abstract method tương thích** có thể được thực thi bằng **một** phương thức trên class. Vì vậy, “hai interface có method trùng tên” **không tự động là lỗi**; lỗi phát sinh khi hợp đồng xung đột theo các quy tắc của Java, chẳng hạn kiểu trả về không tương thích hoặc default implementations mơ hồ.

Các marker interface như `java.io.Serializable` có thể tham gia bound nhưng không thêm method nghiệp vụ nào để gọi. Chẳng hạn `<T extends Named & java.io.Serializable>` vừa yêu cầu `name()` vừa yêu cầu marker serialization, nhưng không tạo thêm method `serialize()` trên `T`.

## 9. Type erasure: bound đầu tiên ảnh hưởng biểu diễn biên dịch

Java generics thông thường dùng **type erasure**. Với type parameter không có bound, erasure thường là `Object`; với type parameter có nhiều bounds, **erasure của type variable được xác định từ bound đầu tiên**.

Ví dụ:

```java
static <T extends Asset & Named & Versioned> String describe(T item) {
    return item.id() + item.name() + item.version();
}
```

`T` ở đây có erasure là `Asset`, vì `Asset` là bound đầu tiên. Điều này **không xóa quyền gọi** `name()` và `version()` khi biên dịch: compiler đã biết intersection bounds, kiểm tra các lời gọi hợp lệ và tạo mã bytecode phù hợp, có thể bao gồm chuyển kiểu sang interface để gọi method.

Nếu chỉ có interface bounds:

```java
static <T extends Named & Versioned> String label(T item) {
    return item.name() + item.version();
}
```

erasure của `T` là `Named` (bound đầu tiên). Compiler vẫn bảo đảm `T` thỏa `Versioned` ở compile time.

**Hệ quả thiết kế API:** thứ tự các **interface bounds** dù có thể giữ nguyên ý nghĩa ràng buộc ở source level vẫn có thể làm thay đổi erasure và phần chữ ký được biểu diễn trong bytecode. Thay đổi thứ tự bound trong API public của một thư viện đã biên dịch có thể ảnh hưởng binary compatibility. Đừng đổi thứ tự bừa bãi chỉ để làm đẹp code; xem xét các tác động tương thích khi phát hành thư viện.

Erasure cũng giải thích vì sao:

- Không thể kiểm tra trực tiếp `obj instanceof T` với type variable `T` thông thường.
- Không thể tạo `new T()` chỉ dựa vào bound.
- Không thể dùng `T.class` để truy vấn đầy đủ kiểu thực tế đã truyền.
- Không thể overload chỉ bằng thay đổi type parameters/bounds nếu **erased signatures bị trùng**.
- Intersection bound **không** tạo một runtime class đặc biệt kết hợp `Named` và `Versioned`.

Nếu cần thông tin kiểu runtime, một API có thể yêu cầu `Class<T>` hoặc một cơ chế type token phù hợp, nhưng việc thêm runtime token **không thay thế** toàn bộ kiểm tra quan hệ kiểu trong chữ ký generic.

## 10. Intersection type và suy luận kiểu

Ngoài cú pháp khai báo bound và intersection cast, Java type system còn sử dụng intersection types khi suy luận kiểu trong một số ngữ cảnh (ví dụ tính **least upper bound** cho nhiều kiểu đầu vào). Điều này giúp biểu diễn những khả năng chung giữa các nhánh hoặc đối số.

Ví dụ về ý tưởng: nếu hai lớp độc lập đều triển khai `Named` và `Versioned`, trình biên dịch có thể tìm một kiểu chung kết hợp các interface khi phân tích một biểu thức phù hợp. Tuy nhiên, **kiểu suy luận cụ thể** phụ thuộc vào ngữ cảnh, quy tắc của Java và các supertype khác; không nên khẳng định mọi `var x = condition ? a : b` đều có đúng kiểu tĩnh `Named & Versioned`.

Để làm rõ hợp đồng của một phương thức công khai, khai báo bound tường minh thường dễ hiểu hơn:

```java
static <T extends Named & Versioned> String label(T item) {
    return item.name() + "@" + item.version();
}
```

Java có thể suy luận `T` khi gọi `label(document)` hoặc `label(deployment)`, miễn kiểu đối số thỏa bound. Cách viết này cũng cho phép compiler báo lỗi sớm nếu truyền `NamedOnly` chỉ có `Named`.

Đặc biệt, các type parameters trong một generic method có thể có quan hệ với nhau:

```java
static <T extends Named & Versioned, R> R map(
        T source,
        java.util.function.Function<? super T, ? extends R> mapper) {
    return mapper.apply(source);
}
```

Đây là **method minh họa** cần đặt trong class nhìn thấy hai interface. `T` buộc source thỏa cả hai interface, còn `R` mô tả kiểu đầu ra của mapper và không phải tự thỏa các bound của `T`. Dấu phẩy giữa `T`, `R` **khác** với dấu `&` nối nhiều bound của cùng `T`.

Nếu có nhu cầu tính toán trên một danh sách giá trị đa loại, phải lựa chọn giữa **kiểu phần tử đồng nhất có bound rõ ràng**, **wildcard đọc dữ liệu**, và **đối tượng bao/interface chung**. Một phép suy luận rộng ở một lời gọi không làm cho mọi thao tác ghi vào collection trở nên hợp lệ.

## 11. Truy cập thành viên: những giới hạn quan trọng

### 11.1. Chỉ truy cập các thành viên được giới hạn bảo đảm

`<T extends Named & Versioned>` không cho phép trực tiếp gọi `item.id()`, dù đối tượng thực tế có thể là `Document extends Asset`. Nếu method cần `id()`, hãy thêm bound `Asset` ở vị trí đầu hoặc bổ sung `id()` vào một interface phù hợp.

### 11.2. Bound không loại trừ `null`

`T extends Named & Versioned` bảo đảm về **kiểu tĩnh**, không có nghĩa `item` chắc chắn khác null. Truyền `null` có thể được chấp nhận nếu không có ràng buộc null riêng; sau đó `item.name()` có thể ném `NullPointerException`. Khi muốn cấm null, dùng `Objects.requireNonNull(item)` hoặc một hợp đồng/kiểm tra null thích hợp.

### 11.3. Java access control vẫn tồn tại

Một class bound có field `private` không đồng nghĩa mọi generic method ở class khác đều truy cập được field đó. Type bounds kiểm tra **khả năng kiểu**, còn access modifier kiểm tra **quyền truy cập theo vị trí mã**.

### 11.4. Multiple bounds không tạo multiple class inheritance

`<T extends Base & I1 & I2>` cho phép tối đa **một class bound** theo vị trí đầu, sau đó là interface bounds. Nó không cho phép `T` kế thừa đồng thời hai class độc lập. Nếu cần tái sử dụng hai dạng trạng thái, cân nhắc composition và interface.

### 11.5. Không biến phần tử của `List` thành một intersection type bằng cast danh sách

`List<Named>` và `List<Versioned>` vẫn invariant; không thể cast `List<Named>` thành `List<Named & Versioned>` vì cú pháp type argument giao không hợp lệ. Nếu cần một API đọc tập các phần tử thỏa cả hai giới hạn, dùng `<T extends Named & Versioned> void work(List<T> items)` với danh sách đã có type element phù hợp.

### 11.6. Thêm interface bound có thể làm API chặt hơn

Đổi `<T extends Named>` thành `<T extends Named & Versioned>` làm **một số lời gọi trước đây không còn hợp lệ** (những kiểu chỉ implements Named). Đây là thay đổi hợp đồng API, không phải cải tiến miễn phí. Cân nhắc hiệu ứng lên code client và binary compatibility.

## 12. Lỗi thường gặp và cách sửa

**Lỗi 1 — Dùng dấu phẩy thay vì `&`.** `<T extends Named, Versioned>` không biểu diễn hai bound cho `T`; nó không khai báo đúng danh sách type parameters. Viết `<T extends Named & Versioned>`.

**Lỗi 2 — Lặp từ khóa `extends`.** `<T extends Named extends Versioned>` sai cú pháp. Chỉ một `extends`, nối bằng `&`.

**Lỗi 3 — Đặt class bound sau interface bound.** `<T extends Named & Asset>` sai nếu `Asset` là class. Viết `<T extends Asset & Named>`.

**Lỗi 4 — Cho rằng bound đầu tiên là bound duy nhất có thể gọi method.** Với `<T extends Asset & Named & Versioned>`, method có thể dùng các member truy cập được từ **cả ba** bound; erasure về `Asset` không ngăn compiler kiểm tra `name()` và `version()`.

**Lỗi 5 — Cho rằng object runtime đủ khả năng thì generic method mặc nhiên gọi được.** Trong `<T extends Named>`, `item.version()` vẫn không biên dịch nếu bound không bảo đảm `version()`. Nâng hợp đồng lên `Named & Versioned` thay vì dựa vào các đối tượng tình cờ được truyền khi chạy.

**Lỗi 6 — Nghĩ `<T extends A & B>` bắt buộc `A`, `B` là hai class.** Java chỉ cho nhiều interface bounds; nếu có class, nó đứng đầu và duy nhất.

**Lỗi 7 — Dùng `List<A & B>`.** Đây không phải cú pháp type argument hợp lệ. Thiết kế generic method nhận `List<T>` với `T extends A & B`.

**Lỗi 8 — Nghĩ `? extends A & B` dùng như bound của wildcard.** Java không cho wildcard intersection bound trực tiếp như thế. Hãy đặt type parameter có tên để diễn đạt quan hệ cần giữ.

**Lỗi 9 — Dùng cast `(A & B)` thay cho giới hạn kiểu tĩnh mà không kiểm tra.** Cast có thể ném `ClassCastException`; generic bound buộc kiểu đối số phù hợp ngay lúc biên dịch và thường nên ưu tiên khi thiết kế API.

**Lỗi 10 — Hiểu nhầm `extends Serializable` tự thêm method.** `Serializable` là marker interface; nó giới hạn các kiểu được chấp nhận nhưng không thêm một `serialize()` member để gọi.

**Lỗi 11 — Quên kiểm tra xung đột giữa các interface.** Hai bound có method cùng signature nhưng return type không tương thích, hoặc nhiều default methods không thể giải quyết hợp lệ, có thể làm giao không hợp lệ. Sửa các hợp đồng hoặc tách riêng nhu cầu.

**Lỗi 12 — Nhầm type erasure với mất type checking.** Erasure là chiến lược runtime/bytecode; compiler vẫn xác minh mọi bound và member access ở source level trước khi sinh bytecode.

**Lỗi 13 — Đổi thứ tự interface bounds tùy tiện trong thư viện đã phát hành.** Bound đầu tiên quyết định erasure của type variable, có thể ảnh hưởng API binary. Đọc kỹ hợp đồng trước khi sửa.

**Lỗi 14 — Quên null và accessibility.** Multiple bounds không ngăn `NullPointerException` và không bỏ qua `private`/`protected`/package visibility. Cần tự thiết kế validation và mức truy cập phù hợp.

**Lỗi 15 — Viết `instanceof A & B`.** Java không có cú pháp kiểm tra kiểu như vậy trong biểu thức `instanceof`. Dùng `obj instanceof A && obj instanceof B` hoặc pattern `instanceof` riêng từng giao diện.

## 13. Quy tắc thiết kế API sử dụng intersection bounds

Cân nhắc nhiều bounds khi **một tham số thật sự cần đồng thời nhiều khả năng độc lập**. Ví dụ một bộ xử lý cần đối tượng vừa có tên vừa có phiên bản, nhưng không muốn tạo interface mới chỉ để gom hai khả năng đó:

```java
static <T extends Named & Versioned> String keyOf(T value) {
    return value.name() + ":" + value.version();
}
```

Thiết kế này cho phép các class không cùng superclass nghiệp vụ — như `Document` và `Deployment` — tham gia nếu cùng đáp ứng hợp đồng.

Tuy vậy, nếu cặp khả năng `Named + Versioned` xuất hiện nhiều lần trong domain, có thể cân nhắc một interface kết hợp:

```java
interface NamedVersioned extends Named, Versioned { }

static String keyOf(NamedVersioned value) {
    return value.name() + ":" + value.version();
}
```

Đây là **hai khai báo minh họa**. Một interface kết hợp tạo tên miền rõ ràng, nhưng những lớp chỉ `implements Named, Versioned` **không tự động được xem là triển khai `NamedVersioned`** nếu chúng không khai báo hoặc kế thừa interface ấy. Đây là sự khác biệt thực tế:

- **Intersection bound `T extends Named & Versioned`** chấp nhận mọi kiểu thỏa cả hai giao diện, không đòi một interface con mới được khai báo trên lớp.
- **Named interface `NamedVersioned`** đòi lớp thực hiện quan hệ `implements NamedVersioned` thích hợp; đổi lại API có một tên hợp đồng dễ tham chiếu.

Nên dùng type parameter có tên khi cần giữ quan hệ kiểu ở kết quả, ví dụ `static <T extends Named & Versioned> T verified(T item)` trả lại đúng `T`. Nếu chỉ cần hành vi và không cần giữ kiểu cụ thể, một interface miền nghiệp vụ có thể đơn giản hơn.

## 14. Câu hỏi tự kiểm tra có đáp án

**1.** `<T extends Named & Versioned>` yêu cầu điều gì?  
**Đáp án:** Type argument `T` phải phù hợp cả hai interface; trong phương thức có thể gọi các member hợp lệ từ cả `Named` và `Versioned`.

**2.** Vì sao không viết `<T extends Named extends Versioned>`?  
**Đáp án:** Java chỉ dùng một `extends` trong khai báo bound và nối các bound tiếp theo bằng `&`.

**3.** Nếu `Asset` là class, thứ tự đúng giữa `Asset`, `Named`, `Versioned` là gì?  
**Đáp án:** `<T extends Asset & Named & Versioned>`; class bound phải đứng đầu.

**4.** Với `<T extends Named>`, có gọi `item.version()` được không nếu người gọi truyền một `Document` implements cả hai interface?  
**Đáp án:** Không. Chữ ký chỉ bảo đảm `Named`; compiler không dựa vào object runtime trong từng lời gọi để mở thêm thành viên.

**5.** Với `<T extends Asset & Named & Versioned>`, những method nào có thể gọi được từ ba hợp đồng minh họa?  
**Đáp án:** `id()`, `name()` và `version()`, nếu tất cả các method đó truy cập được tại vị trí mã.

**6.** `NamedOnly` có thể truyền vào method `<T extends Named & Versioned>` không?  
**Đáp án:** Không, vì thiếu `Versioned`.

**7.** Intersection cast `((Named & Versioned) obj)` có đảm bảo thành công với mọi object `Named` không?  
**Đáp án:** Không; object còn phải thỏa `Versioned`. Nếu không, cast có thể ném `ClassCastException`.

**8.** Một biến `Named named = (Named & Versioned) obj;` có trực tiếp gọi `named.version()` được không?  
**Đáp án:** Không, vì kiểu tĩnh của biến là `Named`; muốn truy cập `version()`, dùng một API bảo toàn cả hai khả năng hoặc cast trong biểu thức khi an toàn.

**9.** `List<Named & Versioned>` hợp lệ không?  
**Đáp án:** Không. Hãy dùng named type parameter `<T extends Named & Versioned>` với `List<T>`.

**10.** `<T extends Number & Comparable<T>>` có chấp nhận `Integer` không?  
**Đáp án:** Có, vì `Integer` là `Number` và thực thi `Comparable<Integer>`.

**11.** Bound đầu tiên ảnh hưởng đến điều gì khi biên dịch generics?  
**Đáp án:** Erasure của type variable; ví dụ trong `T extends Asset & Named`, erasure là `Asset`.

**12.** Có thể dùng hai class bounds như `<T extends Asset & AnotherClass>` không?  
**Đáp án:** Không. Java không hỗ trợ multiple class inheritance; sau class bound, các bound bổ sung phải là interface.

**13.** `Serializable` trong một bound có tự cấp method nghiệp vụ cho biến `T` không?  
**Đáp án:** Không; nó là marker interface không có method nghiệp vụ riêng.

**14.** `T extends Named & Versioned` có loại trừ `null` không?  
**Đáp án:** Không; cần quy tắc validation/nullness riêng nếu API không chấp nhận `null`.

**15.** Type variable có intersection bounds có làm Java giữ tất cả type arguments nguyên vẹn tại runtime không?  
**Đáp án:** Không. Java generics thông thường vẫn dùng type erasure, dù compiler kiểm tra mọi bound khi biên dịch.

**16.** Nên dùng interface mới `NamedVersioned` hay intersection bound?  
**Đáp án:** Intersection bound thuận lợi khi cần chấp nhận mọi kiểu đã thực hiện độc lập hai interface; interface mới phù hợp nếu cần một tên hợp đồng chung rõ ràng và các class được chủ động khai báo theo nó.

**17.** `instanceof Named & Versioned` có hợp lệ không?  
**Đáp án:** Không. Dùng `obj instanceof Named && obj instanceof Versioned` hoặc hai `instanceof` pattern phù hợp.

**18.** Vì sao đổi thứ tự các interface bound trong thư viện có thể rủi ro dù code source vẫn trông tương đương?  
**Đáp án:** Bound đầu tiên quyết định erasure và có thể làm thay đổi chữ ký bytecode, ảnh hưởng tương thích nhị phân.

**Tổng kết:** intersection type diễn đạt một **hợp đồng kết hợp**: `T` phải đồng thời thỏa nhiều bound. Từ đó compiler cho phép đọc/gọi những thành viên mà **tất cả các yêu cầu về kiểu và truy cập** cho phép. Cú pháp đúng thường là `<T extends ClassBound & Interface1 & Interface2>` hoặc `<T extends Interface1 & Interface2>`. Hãy phân biệt khai báo bound (an toàn kiểu compile-time) với intersection cast (kiểm tra runtime), lưu ý bound đầu tiên ảnh hưởng erasure, và dùng kiểu giao khi nhiều khả năng thực sự cần xuất hiện trong một chữ ký API.
