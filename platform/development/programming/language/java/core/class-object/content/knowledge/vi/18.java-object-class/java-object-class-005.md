# Danh tính tham chiếu và bằng nhau theo giá trị với `equals()` trong Java

## 1. Hai câu hỏi khác nhau: “cùng object” và “cùng giá trị”

Khi làm việc với đối tượng Java, ta phải phân biệt:

- **Danh tính tham chiếu (*reference identity*):** hai references trỏ **chính cùng một object**. Toán tử `==` giữa các toán hạng reference tương thích kiểm tra điều đó.
- **Bằng nhau theo giá trị/logic (*value or logical equality*):** hai objects được class xem như có cùng ý nghĩa theo **`equals(Object)`**; chúng có thể được tạo bởi hai lần `new` khác nhau.
- **`Object.equals(Object)` mặc định:** chỉ coi hai references bằng nhau khi chúng trỏ cùng object. Value equality phải đến từ một implementation được override (hoặc một type vốn đã cung cấp).

Một ví dụ điển hình:

```java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false: hai objects
System.out.println(first.equals(second)); // true: cùng nội dung
```

Hai đối tượng `String` là khác nhau về identity; nhưng `String` override `equals` để so nội dung. **Không phải mọi class đều có behavior giống String.**

> **Ghi nhớ:** `==` giữa **references** hỏi “có đúng cùng object không?”. `equals()` hỏi “theo định nghĩa của class, hai objects có bằng nhau không?”.

Bài thuộc chủ đề **Lớp `Object`**, sẽ giúp bạn hiểu mô hình references, equality contracts, `hashCode`, cách override đúng, các góc cạnh của inheritance, String, array, record và hành vi của hash-based collections.

## 2. Sơ đồ tham chiếu và aliasing

Xét:

```java
StringBuilder a = new StringBuilder("A");
StringBuilder b = a;
StringBuilder c = new StringBuilder("A");
```

Sơ đồ theo ngữ nghĩa:

```text
a ──────────┐
            ├─────> StringBuilder X {text: "A"}
b ──────────┘

c ────────────────> StringBuilder Y {text: "A"}
```

- `a == b` true: hai biến giữ cùng giá trị tham chiếu.
- `a == c` false: `new` tạo một object StringBuilder khác.
- `a.equals(c)` false trong ví dụ này: `StringBuilder` không định nghĩa equals theo text contents, mà dùng equality mặc định kế thừa Object.
- `b.append("B")` thay đổi **X**, nên đọc `a.toString()` cũng cho `"AB"`; object Y không đổi.

Sơ đồ là cách hình dung **đối tượng và alias**, không cam kết địa chỉ vật lý, layout heap/stack hay một chiến lược tối ưu hóa cụ thể của JVM.

### “Reference bằng nhau” không đồng nghĩa “trạng thái giống nhau”

Hai aliases cùng trỏ X luôn nhìn thấy cùng object, kể cả khi X mutable và state thay đổi. Hai objects X/Y có thể chứa cùng dữ liệu tại một thời điểm nhưng có vòng đời/identity riêng. Do đó không được lấy `toString()` giống nhau hoặc cùng field values để suy `==` true.

## 3. Ví dụ Java 17+ đầu tiên: object, alias, state

Tạo tệp **`IdentityDemo.java`**:

```java
class Box {
    private int value;

    Box(int value) {
        this.value = value;
    }

    void change(int next) {
        value = next;
    }

    int value() {
        return value;
    }
}

public class IdentityDemo {
    public static void main(String[] args) {
        Box first = new Box(10);
        Box alias = first;
        Box second = new Box(10);

        System.out.println("alias=" + (first == alias));
        System.out.println("different=" + (first == second));
        System.out.println("equals=" + first.equals(second));

        alias.change(20);

        System.out.println("first=" + first.value());
        System.out.println("second=" + second.value());
    }
}
```

```bash
javac IdentityDemo.java
java IdentityDemo
```

**Standard output:**

```text
alias=true
different=false
equals=false
first=20
second=10
```

`Box` không override `equals`, nên dùng identity equality của Object. Phép `alias.change(20)` thay state object mà `first` cùng trỏ, không làm `second` đổi.

**Điểm quan trọng:** `new Box(10)` hai lần không tạo “cùng object” chỉ vì constructor nhận tham số giống nhau. Muốn coi hai boxes có cùng value là logically equal phải **thiết kế equality contract** cho Box; việc ấy không diễn ra tự động.

## 4. Toán tử `==`: cần biết kiểu hai toán hạng

`==` không phải lúc nào cũng kiểm identity:

| Toán hạng | Ý nghĩa của `==` |
| --- | --- |
| Hai biểu thức reference tương thích | Cùng reference / cùng null |
| Hai primitive numeric values | So giá trị theo numeric promotion rules |
| Hai `boolean` values | So true/false |
| Kết hợp một wrapper và một primitive trong trường hợp hợp lệ | Có thể có unboxing/numeric promotion; không còn đơn thuần là identity |

Ví dụ:

```java
int a = 3;
int b = 3;
System.out.println(a == b); // true, primitive values
```

So sánh hai `String` **references**:

```java
String x = new String("A");
String y = new String("A");
System.out.println(x == y); // false
```

**Không override được `==` trong Java.** Class có thể override `equals`, nhưng cannot alter `==` semantics dành cho reference identity.

Khi thấy `Integer` wrappers và `==`, đừng dựa vào cache boxing để so logical numbers. Nếu một operand primitive, Java có thể unbox theo rules; nếu hai operands là wrapper references, identity có thể khác nhau. Hãy dựa trên **static types và contract**, không dựa vào một giá trị kiểm thử tình cờ trả true.

## 5. `null`: so sánh được bằng `==`, nhưng không gọi được instance method

`null` là giá trị reference không trỏ object.

```java
String first = null;
String second = null;
String third = "Java";

System.out.println(first == second); // true
System.out.println(first == third);  // false
```

Nhưng:

```java
// first.equals(second); // NullPointerException vì first là null.
```

Để so logical equality khi có thể null, dùng:

```java
java.util.Objects.equals(first, second)
```

`Objects.equals(a,b)` có semantics null-safe: cùng null → true; một null → false; non-null → dùng equals phù hợp.

**Không viết:** `a.equals(b)` khi `a` có thể null mà không có kiểm tra. Cũng không nhầm `x.equals(null)==false` (với x non-null, theo contract) với `null.equals(x)` — biểu thức thứ hai không có receiver object.

## 6. Implementation mặc định từ `java.lang.Object`

Một ordinary class không override `equals(Object)` thừa hưởng implementation của Object. Theo contract của nó, equality mặc định dựa trên object identity.

Ví dụ:

```java
class Item {
    private final String code;

    Item(String code) {
        this.code = code;
    }
}
```

Hai `new Item("X")` là hai objects riêng; dù code field giống nhau, `equals` mặc định **không so field code**.

### Chương trình runnable

Tệp **`DefaultEqualsDemo.java`**:

```java
class Item {
    private final String code;

    Item(String code) {
        this.code = code;
    }
}

public class DefaultEqualsDemo {
    public static void main(String[] args) {
        Item one = new Item("X");
        Item two = new Item("X");
        Item alias = one;

        System.out.println(one == two);
        System.out.println(one.equals(two));
        System.out.println(one.equals(alias));
    }
}
```

```bash
javac DefaultEqualsDemo.java
java DefaultEqualsDemo
```

```text
false
false
true
```

Không được nói “`equals()` luôn so sánh tất cả fields”. Chính **class implementation** quyết định những dữ liệu nào tạo nên giá trị logic. Có những objects như connection/session/callback mà identity equality mặc định là điều mong muốn.

## 7. `String`: value equality theo nội dung

`String` override equals để so nội dung ký tự. Nhưng String literals còn có cơ chế interning/constant expressions, nên `==` trên một số literals cũng có thể true một cách hợp lệ mà **không có nghĩa String nên được so nội dung bằng `==`**.

Tệp **`StringEqualityDemo.java`**:

```java
public class StringEqualityDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String folded = "Ja" + "va";
        String allocated = new String("Java");

        System.out.println(literal == folded);
        System.out.println(literal == allocated);
        System.out.println(literal.equals(allocated));
        System.out.println(allocated.intern() == literal);
    }
}
```

```bash
javac StringEqualityDemo.java
java StringEqualityDemo
```

```text
true
false
true
true
```

Diễn giải:

- `"Ja" + "va"` là constant expression; Java dùng cùng interned literal representation, nên `literal == folded` true.
- `new String("Java")` tạo object khác identity với literal.
- `equals` so String contents, vì thế true.
- `intern()` trả canonical string reference trong pool cho cùng contents.

**Quy tắc làm việc:** So text bằng `left.equals(right)` khi receiver chắc chắn non-null; dùng `Objects.equals(left,right)` nếu cả hai có thể null. Không viết application logic dựa trên hai Strings có được intern tình cờ hay không.

### `StringBuilder` không giống `String`

`StringBuilder` có mutable text và không override equals để so text contents. Hai `new StringBuilder("A")` khác nhau về identity sẽ không equals theo nội dung. Nếu thật sự cần so text, có thể gọi `a.toString().equals(b.toString())`, với lưu ý về mutable state/concurrency.

## 8. Khi định nghĩa `equals(Object)`, phải giữ quan hệ tương đương

Khác `==` chỉ so identity, `equals` có thể đại diện domain equality. Mỗi override phải giữ **phản xạ, đối xứng, bắc cầu, nhất quán khi state liên quan không đổi** và `x.equals(null) == false` với x không null. Tên method và chữ ký phải đúng `public boolean equals(Object other)`; `equals(MyType)` chỉ là overload.

Bài này đặt câu hỏi **khi nào value equality phù hợp hơn identity**: ví dụ hai `Money` objects cùng amount/currency có thể bằng về giá trị, nhưng hai customer entities giống tên chưa hẳn là một khách hàng. Từ lựa chọn ấy mới thiết kế criteria, xử lý null/type và tests.

**Tự kiểm tra:** nếu `parent.equals(child)` true nhưng `child.equals(parent)` false thì hợp đồng **đối xứng bị phá**; khi đó `HashSet`/collections không thể được tin cậy theo equality dự định. Ví dụ kế thừa ở mục 16 cho thấy lỗi này bằng stdout cụ thể. Bài *hợp đồng equals/hashCode* đi sâu vào cách triển khai và kiểm thử đầy đủ năm điều kiện.

## 9. Chọn identity equality hay value equality theo miền nghiệp vụ

Không phải mọi object phải value-equal khi fields giống nhau.

**Dùng identity khi danh tính/vòng đời instance riêng là điều cốt lõi:**

- Hai network connection objects cấu hình giống nhau vẫn là hai connections.
- Hai transactions độc lập có tổng tiền bằng nhau không nhất thiết là cùng transaction.
- Hai mutable view/controller objects có nội dung giống nhau có thể vẫn là những entities khác.

**Dùng value equality khi những fields cụ thể là “giá trị” của object:**

- Tọa độ `(x,y)`.
- Mã sản phẩm chuẩn hóa `ProductId("A1")`.
- Khoảng `[start,end]`.
- Ngày, cặp giá trị, cấu hình bất biến nếu contract xác định.

Câu hỏi nên đặt ra là: **hai objects được tạo riêng với cùng business value có thay thế nhau được trong so sánh, Set, Map, cache hoặc nghiệp vụ không?** Nếu có, value equality thường là lựa chọn phù hợp.

Đối với entities có ID, equality có thể dựa trên ID theo contract. Nhưng nếu ID được tạo muộn, đổi được hoặc chịu cơ chế proxy của ORM, phải thiết kế cẩn thận. **Không tự động** lấy toàn bộ fields của một entity mutable để làm equals.

## 10. Override `equals(Object)` đúng chữ ký

Một triển khai value object tốt nên:

1. Xử lý nhanh `this == other` nếu cùng object.
2. Kiểm tra null/type an toàn.
3. So đúng những fields quyết định equality.
4. Có `hashCode()` nhất quán.
5. Hạn chế fields mutable tham gia equality khi cần dùng làm key.
6. Cân nhắc `final class` để tránh hierarchy equality phức tạp.

### Ví dụ hoàn chỉnh Java 17+

Tạo **`ProductIdDemo.java`**:

```java
import java.util.Objects;

final class ProductId {
    private final String value;

    ProductId(String value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof ProductId id)) {
            return false;
        }
        return value.equals(id.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }

    @Override
    public String toString() {
        return "ProductId[" + value + "]";
    }
}

public class ProductIdDemo {
    public static void main(String[] args) {
        ProductId first = new ProductId("A1");
        ProductId second = new ProductId("A1");
        ProductId third = new ProductId("B2");

        System.out.println("same reference=" + (first == second));
        System.out.println("same value=" + first.equals(second));
        System.out.println("different=" + first.equals(third));
        System.out.println("null=" + first.equals(null));
        System.out.println("hash matches=" +
                (first.hashCode() == second.hashCode()));
        System.out.println(first);
    }
}
```

```bash
javac ProductIdDemo.java
java ProductIdDemo
```

```text
same reference=false
same value=true
different=false
null=false
hash matches=true
ProductId[A1]
```

**Vì sao đúng?**

- Hai lần `new` tạo identities khác nhau nhưng String value giống nhau.
- `instanceof ProductId id` kiểm type và đồng thời tạo pattern variable (Java 17).
- `value.equals(id.value)` gọi String value equality.
- `hashCode()` dùng cùng `value` nên equal ProductIds có equal hashes.
- `final class` chặn subclasses thêm state gây đối xứng rắc rối.
- `private final String value` dùng String immutable, giúp equality ổn định suốt vòng đời object.

Đừng hiểu `final` trên field là nguyên nhân duy nhất tạo immutability: nếu field trỏ `ArrayList` mutable, vẫn cần protective API/defensive copy.

## 11. `hashCode()` phải thống nhất với logical equality

Điều kiện cơ bản: **hai objects `equals()` nhau thì bắt buộc có cùng `hashCode()`**. Hash bằng nhau không chứng minh equality vì collisions hợp lệ. Vì vậy khi override `equals` theo value fields, hãy override `hashCode` phù hợp theo các fields ấy.

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hash(region, code);
}
~~~

Đây là method fragment trong class có `region`, `code`; không phải chương trình độc lập. Với `HashSet` và `HashMap`, sai điều kiện này có thể làm một key “bằng nhau” theo domain nhưng không tra cứu được như kỳ vọng.

Bài hiện tại dùng hashing như **hệ quả thực tế của việc chọn equality**. Bài hợp đồng tiếp theo phân tích collision, tính nhất quán, inheritance, arrays/records và kiểm thử hash. Nếu các fields tham gia equality có thể thay đổi sau khi chèn vào hash collection, bài mutable keys sẽ giải thích rủi ro retention/lookup riêng.

## 12. Test bằng `HashSet`: loại trùng dựa trên equality

Tệp **`HashSetEqualityDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

final class Code {
    private final String value;

    Code(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Code code
                && value.equals(code.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}

public class HashSetEqualityDemo {
    public static void main(String[] args) {
        Set<Code> codes = new HashSet<>();

        System.out.println(codes.add(new Code("X")));
        System.out.println(codes.add(new Code("X")));
        System.out.println(codes.add(new Code("Y")));
        System.out.println("size=" + codes.size());
        System.out.println(codes.contains(new Code("X")));
    }
}
```

```bash
javac HashSetEqualityDemo.java
java HashSetEqualityDemo
```

```text
true
false
true
size=2
true
```

`Code("X")` thứ hai là một object mới, khác reference, nhưng có cùng equality/hash nên `HashSet.add` trả false. `contains(new Code("X"))` vẫn true dù lookup bằng một object mới.

Đây là minh họa vì sao **value equality không phải chỉ để in boolean**: nó ảnh hưởng hành vi dữ liệu trong collections.

## 13. `HashMap` tìm khóa bằng value equality

Tệp **`HashMapEqualityDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

record UserId(String value) {
    UserId {
        Objects.requireNonNull(value);
    }
}

public class HashMapEqualityDemo {
    public static void main(String[] args) {
        Map<UserId, String> users = new HashMap<>();

        UserId stored = new UserId("u-1");
        UserId lookup = new UserId("u-1");

        users.put(stored, "An");

        System.out.println(stored == lookup);
        System.out.println(stored.equals(lookup));
        System.out.println(users.get(lookup));
        System.out.println(users.containsKey(lookup));
    }
}
```

```bash
javac HashMapEqualityDemo.java
java HashMapEqualityDemo
```

```text
false
true
An
true
```

Record `UserId` ở Java 17 tự có equals/hashCode dựa trên components. Hai UserId instances khác identity nhưng cùng String value, nên Map lookup thành công.

Nếu `UserId` không có value equality hoặc dùng mutable key không ổn định, kết quả có thể khác. **Hash-based lookup là lý do phải quan tâm hashCode song song với equals**.

## 14. `Objects.equals`: so sánh null-safe

Tệp **`NullSafeEqualityDemo.java`**:

```java
import java.util.Objects;

public class NullSafeEqualityDemo {
    public static void main(String[] args) {
        String a = null;
        String b = null;
        String c = "Java";
        String d = new String("Java");

        System.out.println(Objects.equals(a, b));
        System.out.println(Objects.equals(a, c));
        System.out.println(Objects.equals(c, d));
        System.out.println(c == d);
    }
}
```

```bash
javac NullSafeEqualityDemo.java
java NullSafeEqualityDemo
```

```text
true
false
true
false
```

Nói giản lược, `Objects.equals(a,b)` tương đương:

```java
a == b || (a != null && a.equals(b))
```

Đây là **mảnh biểu thức** trong method có `a`/`b` đã khai báo, không phải program độc lập.

`Objects.equals` xử lý null, sau đó vẫn phụ thuộc `equals` của class. Nó **không** tự deep-compare arrays, tự sửa symmetry/transitivity của custom equality, hoặc biến mutable objects thành immutable.

## 15. Bẫy: `equals(MyClass)` là overload, không override

Một lỗi rất phổ biến:

```java
class Key {
    private final String text;

    Key(String text) {
        this.text = text;
    }

    boolean equals(Key other) {
        return other != null && text.equals(other.text);
    }
}
```

Method trên có parameter `Key`, trong khi `Object.equals` có parameter `Object`. Đây là **overloading**, không phải overriding.

Tệp **`EqualsOverloadDemo.java`**:

```java
class Key {
    private final String text;

    Key(String text) {
        this.text = text;
    }

    boolean equals(Key other) {
        return other != null && text.equals(other.text);
    }
}

public class EqualsOverloadDemo {
    public static void main(String[] args) {
        Key first = new Key("A");
        Key second = new Key("A");
        Object asObject = second;

        System.out.println(first.equals(second));
        System.out.println(first.equals(asObject));
        System.out.println(((Object) first).equals(second));
    }
}
```

```bash
javac EqualsOverloadDemo.java
java EqualsOverloadDemo
```

```text
true
false
false
```

Vì overload được chọn theo static type của argument, kết quả khác nhau: `equals(Key)` so text, nhưng inherited `equals(Object)` so identity.

**Sửa:** viết **`@Override public boolean equals(Object other)`**. Annotation giúp compiler phát hiện nếu tên hoặc parameter signature sai. Không viết `boolean equal(Object)` (thiếu `s`), `private boolean equals(Object)` hoặc `boolean equals(Key)` rồi tưởng đã thay hành vi Object.equals.

## 16. Kế thừa có thể phá tính đối xứng của equality

Superclass có thể định nghĩa equality theo `name`, subclass lại muốn so `name` và `level`. Khi đó hai chiều `equals` có nguy cơ không đối xứng.

Tệp **`EqualitySymmetryDemo.java`** — code chạy được nhưng cố ý mô tả **một thiết kế equality sai**:

```java
class BaseValue {
    final String name;

    BaseValue(String name) {
        this.name = name;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BaseValue base
                && name.equals(base.name);
    }

    @Override
    public int hashCode() {
        return name.hashCode();
    }
}

class DetailedValue extends BaseValue {
    final int level;

    DetailedValue(String name, int level) {
        super(name);
        this.level = level;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof DetailedValue detail
                && name.equals(detail.name)
                && level == detail.level;
    }

    @Override
    public int hashCode() {
        return 31 * super.hashCode() + level;
    }
}

public class EqualitySymmetryDemo {
    public static void main(String[] args) {
        BaseValue base = new BaseValue("A");
        DetailedValue detail = new DetailedValue("A", 2);

        System.out.println(base.equals(detail));
        System.out.println(detail.equals(base));
    }
}
```

```bash
javac EqualitySymmetryDemo.java
java EqualitySymmetryDemo
```

```text
true
false
```

`base.equals(detail)` true nhưng `detail.equals(base)` false → **vi phạm symmetry**. Class hierarchy còn có thể phá hashCode consistency khi những fields dùng tính hash khác nhau.

**Cách tránh đơn giản với value object:** dùng `final class` hoặc record nếu không cần inheritance. Với open hierarchy, phải thiết kế equality xuyên subclasses có chủ đích và test đầy đủ symmetry/transitivity; không chỉ thêm `instanceof` tùy tiện.

## 17. `getClass()` hay `instanceof` trong `equals`?

Hai kiểu kiểm tra type:

**Exact runtime class:**

```java
if (other == null || getClass() != other.getClass()) {
    return false;
}
```

**Chấp nhận subtype thỏa instanceof:**

```java
if (!(other instanceof ProductId id)) {
    return false;
}
```

Sự lựa chọn phụ thuộc contract:

- `getClass` check chỉ nhận runtime class đúng loại, có thể giúp tránh base-subclass equality không đối xứng nhưng đôi khi không hợp với proxy/domain.
- `instanceof` tiện khi type là `final`, vì không có subclasses thêm fields gây ambiguity.
- Với inheritance mở, subclass equality cần phối hợp cả hierarchy để bảo đảm contract.
- Với persistence frameworks tạo proxies, cần hiểu runtime class/proxy behavior trước khi đặt rule equality cứng.

**Không có một công thức đúng cho mọi class.** Hãy quyết định xem equality có được phép giữa subtype instances không và subtype state có tham gia identity/value definition không.

## 18. Record trong Java 17 tự định nghĩa value equality

Tệp **`RecordEqualityDemo.java`**:

```java
record Point(int x, int y) {
}

public class RecordEqualityDemo {
    public static void main(String[] args) {
        Point first = new Point(2, 3);
        Point second = new Point(2, 3);
        Point other = new Point(3, 2);

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.equals(other));
        System.out.println(
                first.hashCode() == second.hashCode());
        System.out.println(first);
    }
}
```

```bash
javac RecordEqualityDemo.java
java RecordEqualityDemo
```

```text
false
true
false
true
Point[x=2, y=3]
```

Records có equals/hashCode/toString được tạo theo component semantics. Với primitive components `x`, `y`, đây là value equality dễ hiểu. Tuy nhiên **record không tự deep-copy hoặc deep-freeze mutable component objects**, đặc biệt arrays.

## 19. Record có array component vẫn có thể dùng identity cho array

Tệp **`RecordWithArrayDemo.java`**:

```java
record Numbers(int[] values) {
}

public class RecordWithArrayDemo {
    public static void main(String[] args) {
        int[] shared = {1, 2};

        Numbers a = new Numbers(shared);
        Numbers b = new Numbers(new int[] {1, 2});
        Numbers c = new Numbers(shared);

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.values() == c.values());
    }
}
```

```bash
javac RecordWithArrayDemo.java
java RecordWithArrayDemo
```

```text
false
true
true
```

Record equality cho array component không tự dùng `Arrays.equals`. Array references khác nhau nhưng contents giống nhau → false; cùng source array reference → true.

Nếu cần so array contents, phải định nghĩa custom equals/hashCode nhất quán (cùng defensive-copy contract) hoặc lưu dữ liệu bằng immutable value representation phù hợp. Record accessor trả array reference mặc định cũng có thể làm lộ mutable contents.

## 20. Arrays: `array.equals` so identity, `Arrays.equals` so contents

Tệp **`ArrayEqualityDemo.java`**:

```java
import java.util.Arrays;

public class ArrayEqualityDemo {
    public static void main(String[] args) {
        int[] first = {1, 2, 3};
        int[] second = {1, 2, 3};
        int[] alias = first;

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first == alias);
        System.out.println(Arrays.equals(first, second));
    }
}
```

```bash
javac ArrayEqualityDemo.java
java ArrayEqualityDemo
```

```text
false
false
true
true
```

Mảng Java là objects nhưng không override equals theo nội dung. `Arrays.equals(int[],int[])` có contract so các slots tương ứng.

Với nested arrays, so nội dung nhiều tầng bằng `Arrays.deepEquals` khi phù hợp.

### Mảng lồng nhau

Tệp **`DeepArrayEqualityDemo.java`**:

```java
import java.util.Arrays;

public class DeepArrayEqualityDemo {
    public static void main(String[] args) {
        int[][] a = {{1, 2}, {3}};
        int[][] b = {{1, 2}, {3}};

        System.out.println(a == b);
        System.out.println(Arrays.equals(a, b));
        System.out.println(Arrays.deepEquals(a, b));
        System.out.println(Arrays.deepToString(a));
    }
}
```

```bash
javac DeepArrayEqualityDemo.java
java DeepArrayEqualityDemo
```

```text
false
false
true
[[1, 2], [3]]
```

`Arrays.equals(a,b)` ở đây so references tới các inner arrays (một tầng). `Arrays.deepEquals` so sâu nested array contents theo API. Đừng nhầm nó với so sánh đồ thị objects arbitrary có circular references; deepEquals có điều kiện/giới hạn với những vòng lặp arrays.

## 21. Collections: List/Set/Map có logical equality

Nhiều collections trong Java có contracts cụ thể:

- **`List.equals`**: cùng số phần tử và các phần tử tương ứng bằng nhau **theo thứ tự**.
- **`Set.equals`**: cùng tập elements theo equality, thứ tự iteration không quyết định.
- **`Map.equals`**: cùng các key-value mappings, thứ tự iteration không phải điều kiện equality.

Tệp **`CollectionEqualityDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CollectionEqualityDemo {
    public static void main(String[] args) {
        List<String> first =
                new ArrayList<>(List.of("A", "B"));
        List<String> second =
                new ArrayList<>(List.of(new String("A"), "B"));
        List<String> reversed = List.of("B", "A");

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.equals(reversed));

        System.out.println(Set.of("A", "B")
                .equals(Set.of("B", "A")));
        System.out.println(Map.of("A", 1, "B", 2)
                .equals(Map.of("B", 2, "A", 1)));
    }
}
```

```bash
javac CollectionEqualityDemo.java
java CollectionEqualityDemo
```

```text
false
true
false
true
true
```

Ở ví dụ này, hai `new ArrayList<>(...)` là hai objects riêng, nên `first==second` chắc chắn false. Nội dung List tương ứng equal nên `first.equals(second)` true.

**Tránh một phép kiểm không được bảo đảm:** `List.of(...) == List.of(...)` không phải test identity đáng tin, vì những unmodifiable value-based factory results không có lời hứa reference identity ổn định. Chỉ dùng contract `List.equals` khi muốn so contents.

## 22. `BigDecimal.equals` khác `compareTo` về scale

Một ngoại lệ quan trọng: `BigDecimal.equals` không chỉ so numeric magnitude mà còn đòi cùng **scale**; `compareTo` so numerical order.

Tệp **`BigDecimalEqualityDemo.java`**:

```java
import java.math.BigDecimal;

public class BigDecimalEqualityDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a.compareTo(b) == 0);
        System.out.println(a.scale());
        System.out.println(b.scale());
    }
}
```

```bash
javac BigDecimalEqualityDemo.java
java BigDecimalEqualityDemo
```

```text
false
false
true
1
2
```

Giá trị số bằng nhau nhưng scale khác. `HashSet<BigDecimal>` dùng equals/hashCode; `TreeSet<BigDecimal>` dùng order/compareTo. Nếu ordering không nhất quán với equals, hai structures có thể cho kết quả xem là “trùng” khác nhau theo contract của chúng.

**Bài học:** equality phụ thuộc **type contract**. Không tự quy định mọi class phải coi hai representations cùng số là equal.

## 23. Khi `==` là đúng: null, alias và enum

`==` phù hợp nếu yêu cầu **identity**:

- `object == null`.
- Hai references có trỏ cùng component instance hay không.
- Kiểm alias trong object graph.
- So enum constants.
- `this == other` trong equals implementation.

Tệp **`EnumIdentityDemo.java`**:

```java
enum Status {
    NEW, DONE
}

public class EnumIdentityDemo {
    public static void main(String[] args) {
        Status first = Status.NEW;
        Status second = Status.NEW;
        Status third = Status.DONE;

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first == third);
    }
}
```

```bash
javac EnumIdentityDemo.java
java EnumIdentityDemo
```

```text
true
true
false
```

Enum constants có identity theo type constants, không cho caller tùy ý tạo `new Status()`. `==` là cách so sánh phù hợp và null-safe cho enum values; `equals` cũng cho cùng kết quả với đúng constants nhưng cần receiver non-null.

## 24. `IdentityHashMap`: key equality theo reference identity

`HashMap` dùng logical equality/hashCode của keys. Nhưng Java cũng có `IdentityHashMap` để cố ý dùng identity semantics với keys.

Tệp **`IdentityHashMapDemo.java`**:

```java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class IdentityHashMapDemo {
    public static void main(String[] args) {
        String a = new String("A");
        String b = new String("A");

        Map<String, Integer> values = new HashMap<>();
        values.put(a, 1);
        values.put(b, 2);

        Map<String, Integer> identities = new IdentityHashMap<>();
        identities.put(a, 1);
        identities.put(b, 2);

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println("value keys=" + values.size());
        System.out.println("identity keys=" + identities.size());
    }
}
```

```bash
javac IdentityHashMapDemo.java
java IdentityHashMapDemo
```

```text
false
true
value keys=1
identity keys=2
```

`HashMap` thấy String contents equal nên hai lần put cùng logical key, size=1. `IdentityHashMap` coi hai `new String("A")` là hai keys riêng, size=2.

Đây là **map có behavior đặc biệt**, thích hợp cho một số thuật toán theo object identity; không nên dùng thay HashMap mặc định chỉ vì hai classes tên giống nhau.

## 25. `System.identityHashCode` không phải unique object ID

`System.identityHashCode(x)` lấy hash dựa trên identity semantics của Object ngay cả khi `x` override hashCode. Nhưng:

- Hash values **có thể collision**, không được bảo đảm unique.
- Không phải địa chỉ bộ nhớ bắt buộc.
- Không dùng làm khóa nghiệp vụ hay identifier lâu dài.
- Không mang ý nghĩa “nếu hai objects hash giống nhau thì cùng object”.
- `System.identityHashCode(null)` trả 0 theo API.

Ví dụ expression:

```java
int identityHash = System.identityHashCode(object);
```

Đây là **mảnh code** cần có biến `object`; không có stdout cố định cho giá trị identityHash. Nếu cần biết có cùng instance hay không, `a==b` là phép kiểm trực tiếp. Nếu cần business identifier, hãy mô hình hóa trường ID có contract rõ.

## 26. Mutable key: cảnh báo khi sử dụng logical equality trong `HashMap`

Một class có thể implement `equals/hashCode` đúng theo **state hiện tại**, nhưng trở thành key không ổn định nếu field được dùng cho hash bị sửa **sau khi chèn**.

~~~java
record StableKey(String code) {
    StableKey {
        java.util.Objects.requireNonNull(code);
    }
}
~~~

Đây là record declaration hợp lệ. Khi component `code` là String immutable và không bị thay reference trong record, key có equality/hash ổn định cho phạm vi ví dụ. Trái lại, record chứa List/array mutable vẫn có thể giữ state có khả năng đổi; `record` không tự bảo đảm deep immutability.

**Quy tắc dùng:** ưu tiên immutable value keys, và không thay mutable equality fields trên objects đang giữ trong `HashMap`/`HashSet`. Bài *hệ quả của thay đổi trường equals/hashCode* cung cấp chương trình điều tra trạng thái key còn tồn tại trong collection nhưng lookup không được đảm bảo.

## 27. Equality với nhiều fields: phải thống nhất dữ liệu tham gia

Nếu class đại diện mã sản phẩm trong một khu vực, có thể cần cả `region` và `code`.

Tệp **`CompositeKeyDemo.java`**:

```java
import java.util.Objects;

final class CatalogKey {
    private final String region;
    private final String code;

    CatalogKey(String region, String code) {
        this.region = Objects.requireNonNull(region);
        this.code = Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof CatalogKey key)) {
            return false;
        }
        return region.equals(key.region)
                && code.equals(key.code);
    }

    @Override
    public int hashCode() {
        return Objects.hash(region, code);
    }
}

public class CompositeKeyDemo {
    public static void main(String[] args) {
        CatalogKey a = new CatalogKey("VN", "P1");
        CatalogKey b = new CatalogKey("VN", "P1");
        CatalogKey c = new CatalogKey("US", "P1");

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.hashCode() == b.hashCode());
    }
}
```

```bash
javac CompositeKeyDemo.java
java CompositeKeyDemo
```

```text
true
false
true
```

Hai keys equal khi **cả region lẫn code equal**. Hash tính từ cùng fields. Đừng thêm một field vào equals rồi quên hashCode; cũng đừng tự thay nghĩa equality của public value class mà không xét data structures, cache hoặc các clients đang phụ thuộc.

Với hot path, `Objects.hash` có thể tạo overhead varargs; có thể dùng công thức băm trực tiếp nếu profiling chứng minh cần, nhưng contract đúng quan trọng hơn tối ưu sớm.

## 28. Kiểm thử equals bằng các tình huống chuẩn

Một tập tests nên bao gồm:

1. **Self:** `x.equals(x)`.
2. **Equal twin:** hai instances khác identity, cùng business value.
3. **Different:** ít nhất một field tham gia equality khác.
4. **Null:** `x.equals(null)` trả false.
5. **Unrelated type:** `x.equals("text")` trả false.
6. **Symmetry:** hai chiều `x.equals(y)` và `y.equals(x)` trùng kết quả.
7. **Transitivity:** ba objects equal pairwise theo contract.
8. **Consistency:** lặp khi equality state chưa đổi.
9. **hashCode:** equal objects có equal hashes.
10. **Collections:** set dedup và map lookup hoạt động như định nghĩa.

Tệp **`EqualsSelfTest.java`**:

```java
import java.util.HashSet;
import java.util.Set;

record Point(int x, int y) {
}

public class EqualsSelfTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Point a = new Point(2, 3);
        Point b = new Point(2, 3);
        Point c = new Point(2, 3);
        Point different = new Point(3, 2);

        check(a.equals(a), "reflexive");
        check(a.equals(b) && b.equals(a), "symmetric");
        check(a.equals(b) && b.equals(c) && a.equals(c),
                "transitive");
        check(!a.equals(different), "different");
        check(!a.equals(null), "null");
        check(!a.equals("text"), "unrelated type");
        check(a.hashCode() == b.hashCode(), "hash code");

        Set<Point> points = new HashSet<>();
        points.add(a);
        points.add(b);
        check(points.size() == 1, "set dedup");

        System.out.println("equals checks passed");
    }
}
```

```bash
javac EqualsSelfTest.java
java EqualsSelfTest
```

```text
equals checks passed
```

Đây là self-test bằng main, không phải JUnit; nó **không chứng minh** mọi trường hợp đã đúng. Với inheritance hoặc custom equality phức tạp, cân nhắc property-based tests trên nhiều input và nhiều subtype combinations.

## 29. Một vài góc cạnh nâng cao của Java equality

### So các số thực

`Double.equals` có quy tắc riêng cho `NaN` và dấu của zero không hoàn toàn giống primitive `double ==`. Khi dùng floating-point làm business value, hãy kiểm những trường hợp `NaN`, `+0.0`, `-0.0` và sai số.

**Không** dùng quan hệ “hai số chênh lệch dưới epsilon” làm `equals` thông thường nếu nó phá transitivity. Dùng method riêng như `approximatelyEqual(a,b,tolerance)`.

### So `BigDecimal` theo giá trị số

Nếu mục đích là “2.0 và 2.00 cùng magnitude”, `compareTo==0` có thể phù hợp thay vì `equals`. Nhưng lúc ấy cần thiết kế Set/Map keys cho đúng: không đơn giản đổi hashCode semantics của BigDecimal từ bên ngoài.

### Getter và mutable state

Nếu equality tính từ mutable list hoặc timestamp thay đổi, object có thể chuyển từ equal sang unequal theo thời gian. Về mặt contract, consistency chỉ áp dụng khi thông tin liên quan không đổi; nhưng các thay đổi này vẫn nguy hiểm với caches/hash sets.

### Kế thừa

Không tự chọn `instanceof` hoặc `getClass` mà không cân nhắc base/subclass equality. Cần đối xứng, bắc cầu, cùng scope của hash, và behavior ổn định với clients.

### `Objects.deepEquals`

`Objects.deepEquals(a,b)` dùng array-aware semantics khi cả hai là arrays, nhưng **không làm mọi object graph tự nhiên trở thành deep value equal**. Với cấu trúc nested phức tạp hoặc cyclic objects, hãy định nghĩa rõ logical equality của domain.

## 30. Bảng lỗi thường gặp

| Sai lầm | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| `string1 == string2` để so content | Identity khác dù text giống | `equals`/`Objects.equals` |
| Nghĩ `Object.equals` so fields | Mặc định dựa identity | Override hoặc dùng value type |
| Viết `equals(MyType)` | Overload, không override | `@Override equals(Object)` |
| Viết `equal(Object)` | Sai tên | `equals(Object)` |
| `private boolean equals(Object)` | Không được giảm quyền public của Object.equals | `public` |
| Quên `hashCode` khi override equals | Có thể phá hash-based collections | Override nhất quán |
| `equals(null)` gây NPE | Vi phạm contract | Kiểm null/type trước |
| Thêm fields ở subclass vào equals không xét superclass | Phá symmetry/transitivity | Thiết kế hierarchy hoặc final value class |
| Dùng mutable fields làm key hash | Hash có thể đổi sau put | Immutable key |
| Dùng raw hashCode làm ID duy nhất | Có thể collision | Business ID riêng |
| Nghĩ cùng hash nghĩa equals | Hash collision hợp lệ | Kiểm equals |
| Gọi `null.equals(x)` | Null receiver | `Objects.equals` |
| Dùng `array.equals` so elements | Array default identity | `Arrays.equals/deepEquals` |
| Nghĩ record array component so sâu | Không tự deep compare | Custom equality/immutable components |
| Dùng `List.of(...) == List.of(...)` làm contract | Identity không được bảo đảm | List.equals |
| Nhầm List và Set equality | List quan tâm thứ tự, Set không | Chọn đúng contract |
| Nhầm `BigDecimal.equals` với compareTo | Scale ảnh hưởng equals | Chọn nghĩa số hay representation |
| Dùng `==` cho wrapper numbers mà không xét kiểu | Boxing/unboxing/identity khác nhau | Type-correct value comparison |
| Dùng `IdentityHashMap` thay HashMap mọi nơi | Thay semantics key không mong muốn | Chỉ dùng khi cần identity |
| Cho rằng `System.identityHashCode` là địa chỉ RAM | Không được đảm bảo | Không suy địa chỉ từ hash |
| Dùng near-equality không bắc cầu trong equals | Phá contract | Method riêng cho tolerance |
| Tưởng `final` field đảm bảo deep immutable | Reference final nhưng object mutable | Defensive copy/immutable component |
| Cho rằng `equals` luôn symmetric dù implementation sai | Có thể bị lập trình sai | Test đủ hai chiều |

## 31. Bài thực hành tổng hợp: entity identity và value key

Tạo **`IdentityValueTraceDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

record BookId(String code) {
    BookId {
        Objects.requireNonNull(code);
    }
}

final class Book {
    private final BookId id;
    private String title;

    Book(BookId id, String title) {
        this.id = Objects.requireNonNull(id);
        this.title = title;
    }

    BookId id() {
        return id;
    }

    String title() {
        return title;
    }

    void rename(String newTitle) {
        title = newTitle;
    }
}

public class IdentityValueTraceDemo {
    public static void main(String[] args) {
        BookId id1 = new BookId("B1");
        BookId id2 = new BookId("B1");

        Book first = new Book(id1, "Java");
        Book second = new Book(id2, "Java");
        Book alias = first;

        System.out.println("id identity=" + (id1 == id2));
        System.out.println("id value=" + id1.equals(id2));
        System.out.println("book identity=" + (first == second));
        System.out.println("book equals=" + first.equals(second));

        alias.rename("Java Core");
        System.out.println("first title=" + first.title());
        System.out.println("second title=" + second.title());

        Map<BookId, String> labels = new HashMap<>();
        labels.put(first.id(), "entry");
        System.out.println("lookup=" + labels.get(second.id()));
    }
}
```

```bash
javac IdentityValueTraceDemo.java
java IdentityValueTraceDemo
```

```text
id identity=false
id value=true
book identity=false
book equals=false
first title=Java Core
second title=Java
lookup=entry
```

### Truy vết

1. `id1` và `id2` là hai record instances khác nhau nhưng logical value giống nhau.
2. `first` và `second` là hai Book objects; Book không override equals nên dùng identity equality của Object.
3. `alias=first` tạo reference alias; `alias.rename` mutate first Book, không mutate second Book.
4. HashMap lưu key `id1` nhưng tra bằng `id2` vẫn được, vì record value equality và hashCode phù hợp.
5. Một miền nghiệp vụ hoàn toàn có thể dùng **identity equality cho object có vòng đời riêng** và **value equality cho ID**; không cần ép tất cả classes so fields giống nhau.

## 32. Câu hỏi tự kiểm tra

**1.** Hai references cùng object thì `==` trả gì?  
**Đáp án:** True. Theo contract equals đúng, `a.equals(b)` cũng true nếu receiver non-null.

**2.** Hai objects khác nhau nhưng fields giống nhau, `==` có true không?  
**Đáp án:** Không. `equals` tùy implementation.

**3.** Class không override equals thì equality gì?  
**Đáp án:** Mặc định Object identity equality.

**4.** Với hai `new String("A")` độc lập, so content bằng gì?  
**Đáp án:** `String.equals` hoặc `Objects.equals` nếu có null.

**5.** `a == null` có NPE không?  
**Đáp án:** Không. `a.equals(...)` có thể NPE nếu a null.

**6.** Chữ ký đúng để override là gì?  
**Đáp án:** `public boolean equals(Object other)`, nên dùng `@Override`.

**7.** `equals(MyType)` sai ở đâu nếu muốn override?  
**Đáp án:** Nó overload; inherited equals(Object) vẫn tồn tại.

**8.** Hai equal objects bắt buộc có hashCode như thế nào?  
**Đáp án:** Phải bằng nhau.

**9.** Hai hashCode bằng nhau chứng minh equals true không?  
**Đáp án:** Không, collision hợp lệ.

**10.** Có thể dùng `final` class để giảm rủi ro equality inheritance không?  
**Đáp án:** Có, nhất là với value objects.

**11.** `record Point(int x,int y)` có equals không?  
**Đáp án:** Có, tự tạo từ components.

**12.** Record có array component có tự so elements sâu không?  
**Đáp án:** Không; array thường dùng identity equality.

**13.** `Arrays.equals` và `Arrays.deepEquals` khác gì?  
**Đáp án:** Một mức so các phần tử, còn deepEquals xét nested arrays theo contract.

**14.** `HashMap.get(new EqualKey(...))` có thể tìm key từ instance khác không?  
**Đáp án:** Có nếu equals/hashCode hợp lệ và key state ổn định.

**15.** `IdentityHashMap` khác `HashMap` ở đâu?  
**Đáp án:** So key reference identity thay vì standard logical equality.

**16.** `BigDecimal("2.0").equals(BigDecimal("2.00"))`?  
**Đáp án:** False vì scale khác, nhưng compareTo có thể bằng 0.

**17.** `enum` nên so bằng gì?  
**Đáp án:** `==` là phù hợp cho constants.

**18.** Nếu key bị mutate sau khi `put`, có nguy cơ gì?  
**Đáp án:** Hash/equals không ổn định, lookup không đáng tin.

**19.** `equals` cần những tính chất nào?  
**Đáp án:** Phản xạ, đối xứng, bắc cầu, nhất quán; so với null phải false.

**20.** `equals` trong class cha và con có thể khác nhau thế nào?  
**Đáp án:** Có thể gây xung đột symmetry/transitivity khi class con thêm state; phải thiết kế toàn hierarchy.

## 33. Checklist review trước khi công bố API equality

- [ ] Đã quyết định class cần reference identity hay value equality theo domain?
- [ ] Tập fields tạo giá trị logic đã được mô tả rõ?
- [ ] Nếu override, đúng `public boolean equals(Object)` và có `@Override`?
- [ ] `equals(null)` false và không có dereference null?
- [ ] `equals` phản xạ, đối xứng, bắc cầu, nhất quán?
- [ ] `hashCode` dùng cùng tập dữ liệu quyết định equality?
- [ ] Hai values equal có hashes equal?
- [ ] Có fields mutable tham gia equality khi object được dùng làm key/set element?
- [ ] Nếu có inheritance, đã test cả base→subclass và subclass→base?
- [ ] Có nên dùng `final` value class hoặc record để giảm bớt hierarchy issues?
- [ ] Nếu dùng array, đã chọn `Arrays.equals`/`deepEquals` và hash tương ứng?
- [ ] Nếu dùng record với mutable components, đã bảo vệ aliases/copy policy?
- [ ] Đã tránh `==` để so nội dung String/List?
- [ ] Đã dùng null-safe `Objects.equals` khi receiver có thể null?
- [ ] Đã xét BigDecimal scale và floating-point corner cases?
- [ ] Có unit/self-tests cho equal twin, different value, null, unrelated type?
- [ ] Có test `HashSet` dedup và `HashMap` lookup bằng key object khác nhưng equal?
- [ ] Không dùng raw identityHashCode như một unique ID?
- [ ] Không viết test dựa vào reference identity của value-based factory outputs?
- [ ] Các ví dụ Java 17+ có file/public class đúng và stdout không phụ thuộc vào raw hashes hay collection iteration order?

---

**Ghi nhớ:** `==` giữa references trả lời **“có trỏ cùng một object không?”**; `equals(Object)` trả lời **“class này định nghĩa hai objects bằng nhau như thế nào?”**. `Object.equals` mặc định theo identity; `String`, records và collections có contract value equality riêng. Khi tự định nghĩa equality, phải **override đúng chữ ký**, tuân thủ **reflexive, symmetric, transitive, consistent và null rule**, đồng thời cung cấp **`hashCode` nhất quán**. Cẩn thận với **inheritance, arrays, mutable keys và null**. Chọn equality theo ý nghĩa nghiệp vụ và bảo vệ contract ấy trong suốt vòng đời objects.