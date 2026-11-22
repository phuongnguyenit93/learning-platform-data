# Chọn lớp lồng hay lớp cấp cao nhất trong Java

Khi thiết kế một ứng dụng Java, việc một class được đặt **bên trong class khác** hay là một **top-level class** không chỉ quyết định số lượng file `.java`. Lựa chọn này thể hiện **mức độ độc lập của khái niệm**, **phạm vi sử dụng**, **đóng gói**, **quyền truy cập**, **mối liên hệ với đối tượng bao ngoài**, **khả năng tái sử dụng**, **khả năng kiểm thử** và **vòng đời đối tượng**.

Giả sử bạn đang viết `Order` và có các kiểu:

- `OrderLine`: biểu diễn dòng hàng của đơn.
- `Node`: nút liên kết nội bộ để lưu một cấu trúc dữ liệu của Order.
- `Builder`: hỗ trợ tạo Order.
- `TaxPolicy`: quy tắc thuế dùng ở nhiều module.
- `Cursor`: thao tác trên đúng một Order instance.

Có nên viết tất cả là lớp lồng của `Order`? Không nhất thiết. Mỗi loại có **phạm vi sở hữu và khả năng tái sử dụng** khác nhau.

Một nguyên tắc thực dụng:

> **Nếu một class là chi tiết triển khai của đúng một enclosing class, hãy cân nhắc nested class. Nếu class là một khái niệm độc lập, được nhiều phần hệ thống dùng và có vòng đời/API riêng, hãy cân nhắc top-level class.**

Khi đã chọn nested, câu hỏi tiếp theo:

> **Class ấy có thực sự cần một enclosing instance không? Nếu không, thường chọn static nested member class thay vì non-static member inner class.**

Bài học trình bày trên **Java 17+**, gồm top-level versus nested, private/package-private/public API, static nested và member inner, local và anonymous, lựa chọn cho builders/value objects/callbacks, những thay đổi khi refactor, bytecode/JVM, module boundaries, testability, memory retention, design smells và nhiều ví dụ có thể lưu thành file rồi chạy với `javac`/`java`.

## 1. Hai cách khai báo class và ý nghĩa ban đầu

Một **top-level class** được khai báo trực tiếp trong một compilation unit, không nằm trong body của một class khác:

```java
class Product {
    private final String sku;

    Product(String sku) {
        this.sku = sku;
    }
}
```

Một **nested member class** nằm trong một enclosing type:

```java
class Order {
    private static class Node {
        String sku;
        Node next;
    }
}
```

Ở đây `Node` có ý nghĩa chủ yếu như một **chi tiết triển khai của Order**. Người dùng bên ngoài không cần thấy tên `Order.Node` khi chỉ tạo hoặc thao tác với Order theo API công khai.

Nhưng đặt class trong một class khác **không tự động bảo đảm thiết kế tốt**. Nếu `Node` dần trở thành domain type mà nhiều phần hệ thống cần, việc ép nó vào Order có thể làm API khó dùng.

### Hai chiều nên xét riêng

1. **Vai trò khái niệm:** đây là domain concept độc lập hay helper chỉ có ý nghĩa cùng owner?
2. **Quan hệ instance:** khi class được khởi tạo, nó có cần tham chiếu ngầm định đến một enclosing object cụ thể không?

Một helper chỉ thuộc Order nhưng **không cần Order instance** → thường là `private static class Helper`.

Một đối tượng cần giữ quan hệ với **đúng một Order instance** → có thể là `class InnerHelper`.

Một domain `Money` được dùng trong Order, Invoice, Refund và Accounting → thường đáng là một **top-level value type**, dù ban đầu chỉ được tạo từ Order.

## 2. Sơ đồ phân loại

```text
Java type declaration
│
├── Top-level class
│   └── public hoặc package-private
│
└── Nested class
    │
    ├── Member class trong body enclosing type
    │   ├── static nested member
    │   └── non-static member inner
    │
    ├── Local class (có tên trong phạm vi block)
    │
    └── Anonymous class (không có tên source)
```

Các lựa chọn thiết kế chính được phân biệt bởi **declaration site**, **accessibility** và **enclosing instance requirement**.

Trong ngữ nghĩa Java, từ **inner class** có phạm vi kỹ thuật rộng hơn non-static member inner: local và anonymous classes thích hợp cũng là inner classes. Tuy nhiên khi đặt cạnh “static nested”, tài liệu thực hành thường dùng “member inner” để chỉ **non-static member class**.

**Lambda không phải một anonymous class declaration.** Lambda cung cấp behavior cho functional interface với semantics riêng về `this`, capture và implementation.

## 3. Bảng so sánh nhanh

| Tiêu chí | Top-level | Static member nested | Non-static member inner | Local | Anonymous |
| --- | --- | --- | --- | --- | --- |
| Độc lập tên source? | Có | Tên `Outer.Nested` | Tên `Outer.Inner` | Tên chỉ trong block | Không có source class name |
| Khai báo ở đâu? | Ở mức compilation unit | Body enclosing type | Body enclosing class | Trong block/context | Ngay biểu thức tạo instance |
| Cần enclosing instance? | Không | Không | Có trong tạo object bình thường | Tùy enclosing context | Tùy enclosing context |
| Có thể private member type? | Không | Có | Có | Không cùng kiểu access modifiers | Không cùng kiểu access modifiers |
| Có thể dùng lại rộng rãi? | Dễ nhất | Có nếu accessible; chịu qualified name | Có nhưng phụ thuộc owner instance | Bị giới hạn scope tên | Thường một chỗ |
| Lý tưởng cho | Domain/service/value type độc lập | Helper, Node, Builder, API subordinate type | View/cursor/command gắn owner | Helper chỉ trong một method | Implementation inline ngắn |
| Nguy cơ coupling owner? | Không tự có | Theo name/access, không implicit instance | Có enclosing instance relation | Tùy context/capture | Tùy context/capture |

Không nên đưa mọi lựa chọn về một điểm số duy nhất. **Khả năng tái sử dụng** không phải lúc nào quan trọng hơn **encapsulation**; **số lượng file ít** không phải lúc nào quan trọng hơn **độc lập domain**.

## 4. Top-level class: khi nào phù hợp?

Top-level class thường thích hợp nếu một kiểu:

- Có **ý nghĩa domain độc lập**: `Money`, `Address`, `CustomerId`.
- Có thể được dùng bởi nhiều classes hoặc nhiều packages.
- Có public contract/versioning riêng.
- Có nhiều hành vi cần test riêng.
- Có lifecycle độc lập với một object owner.
- Cần được DI framework, serialization library hoặc API consumer tham chiếu dễ dàng theo tên.
- Có khả năng trở thành extension point cho những nhóm phát triển khác.
- Không thật sự là chi tiết cài đặt của một enclosing class.

Ví dụ thiết kế:

```text
com.example.billing
├── Money.java
├── Invoice.java
├── TaxPolicy.java
└── InvoiceService.java
```

`Money` và `TaxPolicy` có thể được sử dụng cả ở `Invoice` lẫn `Refund`. Ép `Money` thành `Invoice.Money` sẽ tạo cách đặt tên gây hiểu nhầm nếu Money không thuộc riêng Invoice.

### Top-level không nhất thiết là public

Một top-level class có thể **package-private** (không khai báo `public`):

```java
package demo;

final class LocalRateTable {
    // Chỉ code có package-access phù hợp mới dùng trực tiếp.
}
```

Vì thế không đúng khi nói “muốn giấu type thì bắt buộc nested”. Top-level package-private cũng là một hình thức encapsulation hợp lệ, nhưng phạm vi của nó là **package**, không phải **chỉ một enclosing class**.

## 5. Quy tắc access modifier của top-level và member class

Top-level ordinary class trong Java source thường có:
- `public`;
- Hoặc không có access modifier (package-private).

**Không thể khai báo top-level class với `private`, `protected` hay `static`** như một class độc lập ở mức compilation unit.

Ví dụ không hợp lệ:

```java
// private class Secret { }   // Sai top-level.
// protected class Helper { } // Sai top-level.
// static class Utility { }   // Sai top-level.
```

Ngược lại, member nested class có thể được công bố hoặc giấu theo quy tắc member:

```java
public class Container {
    public static class PublicResult {
    }

    protected static class ProtectedHelper {
    }

    private static class InternalNode {
    }
}
```

`private static class InternalNode` chỉ dành cho implementation mà enclosing/nest có quyền truy cập, không phải là type do client ngoài hệ thống tự ý dùng.

### Một compilation unit có bao nhiêu public top-level classes?

Theo quy tắc thông dụng khi biên dịch source từ file bằng `javac`, mỗi file Java công khai một **public top-level class/interface** tương ứng tên file. Ví dụ public `Invoice` ở `Invoice.java`.

Bạn có thể khai báo thêm các **package-private top-level classes** trong cùng compilation unit, nhưng khi chúng bắt đầu lớn và có trách nhiệm riêng, tách file thường dễ đọc/tìm kiếm hơn.

Không nên dùng “nhét nhiều package-private classes cùng một file” để né việc thiết kế ranh giới type.

## 6. Runnable: package-private top-level helper

Lưu file **`TopLevelChoiceDemo.java`**:

```java
final class PriceFormatter {
    String format(int cents) {
        int units = cents / 100;
        int fractional = cents % 100;

        return units + "." + (fractional < 10 ? "0" : "")
                + fractional;
    }
}

public class TopLevelChoiceDemo {
    public static void main(String[] args) {
        PriceFormatter formatter = new PriceFormatter();

        System.out.println(formatter.format(1250));
        System.out.println(formatter.format(205));
    }
}
```

```bash
javac -encoding UTF-8 TopLevelChoiceDemo.java
java TopLevelChoiceDemo
```

Stdout:

```text
12.50
2.05
```

`PriceFormatter` là **top-level package-private class**, không có quan hệ enclosing instance với `TopLevelChoiceDemo`.

Ví dụ formatter chỉ minh họa tổ chức type; ứng dụng tiền tệ thực tế cần xử lý dấu âm, overflow, currency/scale và rounding theo domain, không dùng logic đơn giản này như thư viện tài chính.

## 7. Static nested class: khi nào là lựa chọn tốt nhất?

Chọn **static nested member class** nếu:

1. Type thực chất là **implementation detail hoặc companion type** của một enclosing class.
2. Nó không cần truy cập implicit `Outer.this`.
3. Muốn đặt tên và hạn chế visibility theo owner.
4. Có thể cần đọc private members qua reference truyền tường minh, nhưng không cần gắn vĩnh viễn với owner instance.
5. Nó không xứng đáng là public top-level concept độc lập.

Ví dụ:

```java
public final class IntStack {
    private Node head;

    private static final class Node {
        final int value;
        final Node next;

        Node(int value, Node next) {
            this.value = value;
            this.next = next;
        }
    }
}
```

`Node` là một type riêng về mặt JVM, nhưng ở API source, nó là **chi tiết của IntStack**. Không có một `IntStack` reference bắt buộc nằm trong mỗi Node chỉ vì Node được khai báo nested.

### Không nhầm “static nested class” với static singleton

`static` trên member class **không** tạo singleton hoặc chỉ một instance. Mỗi lệnh:

```java
new IntStack.Node(...);
```

nếu được viết từ nơi có access và tham số hợp lệ, vẫn có thể tạo một Node instance khác.

Ở đây Node là private, nên ví dụ minh họa quyền tạo nằm trong phạm vi IntStack chứ không phải client bên ngoài.

## 8. Runnable: private static Node cho stack

Lưu **`NestedNodeStackDemo.java`**:

```java
public final class NestedNodeStackDemo {
    private Node top;

    private static final class Node {
        private final int value;
        private final Node next;

        Node(int value, Node next) {
            this.value = value;
            this.next = next;
        }
    }

    public void push(int value) {
        top = new Node(value, top);
    }

    public int pop() {
        if (top == null) {
            throw new IllegalStateException("empty");
        }

        int result = top.value;
        top = top.next;
        return result;
    }

    public static void main(String[] args) {
        NestedNodeStackDemo stack = new NestedNodeStackDemo();

        stack.push(4);
        stack.push(9);

        System.out.println(stack.pop());
        System.out.println(stack.pop());
    }
}
```

```bash
javac -encoding UTF-8 NestedNodeStackDemo.java
java NestedNodeStackDemo
```

Stdout:

```text
9
4
```

Nếu chuyển Node thành public top-level class mà không có nhu cầu độc lập, bạn có thể làm phình public API và bắt client phải hiểu một type không liên quan đến việc dùng stack.

## 9. Static nested class vẫn truy cập private members của enclosing class

Một static nested class có thể truy cập private static members trực tiếp, và private instance members **thông qua instance reference**.

```java
class Outer {
    private int value = 7;

    private static class Reader {
        int read(Outer owner) {
            return owner.value;
        }
    }
}
```

Điều này hợp lệ vì **nesting cho phép private access thích hợp**. Nhưng static nested Reader **không có `Outer.this`**.

Ví dụ không hợp lệ trong Reader:

```java
// return value; // Sai nếu không có Outer instance.
// return Outer.this.value; // Không có implicit enclosing Outer.
```

Do vậy việc chọn static nested **không cấm sử dụng state của Outer**, mà buộc dependency vào **một object cụ thể** phải rõ ràng.

### Vì sao dependency tường minh quan trọng?

Khi đọc method `read(Outer owner)`, caller và người review thấy:
- Nó đọc state từ một reference được truyền vào.
- Một Reader có thể dùng để đọc nhiều Outer instances.
- Không có lifetime coupling mặc định tới một Outer instance cụ thể.

Member inner class diễn đạt relation khác: nó gắn với một enclosing Outer instance từ khi tạo.

## 10. Runnable: static helper với owner tham số

Lưu **`StaticHelperAccessDemo.java`**:

```java
public final class StaticHelperAccessDemo {
    private final String code;

    StaticHelperAccessDemo(String code) {
        this.code = code;
    }

    private static final class Inspector {
        String inspect(StaticHelperAccessDemo target) {
            return "[" + target.code + "]";
        }
    }

    public static void main(String[] args) {
        StaticHelperAccessDemo a =
                new StaticHelperAccessDemo("A");
        StaticHelperAccessDemo b =
                new StaticHelperAccessDemo("B");

        Inspector inspector = new Inspector();

        System.out.println(inspector.inspect(a));
        System.out.println(inspector.inspect(b));
    }
}
```

```bash
javac -encoding UTF-8 StaticHelperAccessDemo.java
java StaticHelperAccessDemo
```

Stdout:

```text
[A]
[B]
```

`Inspector` có thể sử dụng private `code` mà không cần một implicit enclosing instance. Quan hệ đọc state **được chỉ ra bằng method parameter**.

## 11. Non-static member inner class: nên chọn khi nào?

Một **non-static member inner class** thường hợp lý nếu instance của nó **có ý nghĩa gắn với đúng một enclosing object**:

- Cursor gắn với một Document.
- Một Command thao tác lên một Editor instance.
- Một View gắn với state của một Session instance.
- Một handler là thành phần của một owner có lifecycle được quản lý.

Ví dụ:

```java
class Counter {
    private int count;

    class Increment {
        void apply() {
            count++;
        }
    }
}
```

`Increment` gắn với `Counter` instance được dùng để tạo nó.

Tạo từ bên ngoài:

```java
Counter counter = new Counter();
Counter.Increment command = counter.new Increment();
```

`Counter.Increment` không tự extends Counter. Enclosing relation **khác** inheritance.

### Không nên dùng inner chỉ vì “đã viết trong class”

Nếu helper không cần state Outer, dùng inner thường làm quan hệ giữa objects trở nên mạnh hơn cần thiết. Chọn `static nested` sẽ diễn đạt ý định rõ hơn.

## 12. Runnable: member inner command gắn với owner

Lưu **`OwnerBoundCommandDemo.java`**:

```java
public final class OwnerBoundCommandDemo {
    private final String name;
    private int count;

    OwnerBoundCommandDemo(String name) {
        this.name = name;
    }

    public final class Increment implements Runnable {
        @Override
        public void run() {
            count++;
        }
    }

    public static void main(String[] args) {
        OwnerBoundCommandDemo first =
                new OwnerBoundCommandDemo("first");
        OwnerBoundCommandDemo second =
                new OwnerBoundCommandDemo("second");

        Runnable firstCommand = first.new Increment();
        Runnable secondCommand = second.new Increment();

        firstCommand.run();
        firstCommand.run();
        secondCommand.run();

        System.out.println(first.name + "=" + first.count);
        System.out.println(second.name + "=" + second.count);
    }
}
```

```bash
javac -encoding UTF-8 OwnerBoundCommandDemo.java
java OwnerBoundCommandDemo
```

Stdout:

```text
first=2
second=1
```

Hai commands có cùng declared implementation type nhưng **gắn hai enclosing instances khác nhau**. Vì behavior cần update đúng owner, inner class diễn đạt coupling này trực tiếp.

**Không nên suy ra thread-safety:** nếu gọi nhiều commands trên cùng owner từ nhiều threads, thao tác `count++` cần synchronization phù hợp.

## 13. Member inner class có chi phí coupling và lifecycle

Một member inner object gắn với enclosing instance. Nếu nó được lưu trong một nơi sống lâu hơn owner, owner có thể còn reachable ngoài ý muốn.

Ví dụ tình huống:

```text
Long-lived event bus
  └── registered listener
        └── enclosing Screen object
              └── large UI model
```

Nếu listener là member inner class của `Screen`, quan hệ instance này có thể gây **memory retention**. Không phải mọi inner class luôn gây memory leak; leak/retention xuất hiện khi vòng đời references không được quản lý đúng.

Hướng giải quyết:
- Dùng **static nested listener** khi không cần Outer instance.
- Truyền state/dependencies tối thiểu nếu cần, thay vì capture nguyên owner.
- Gỡ đăng ký listener theo lifecycle (`unregister`/`close`).
- Không lưu inner object vào global registry nếu owner phải có tuổi thọ ngắn mà không có cleanup.
- Xem lại ownership: nếu listener thật sự là thành phần sống cùng owner, việc giữ reference có thể là đúng.

### Không dùng inner class làm cách né constructor parameters

“Đỡ phải truyền đối tượng” chưa hẳn tốt hơn. Dependency ẩn có thể làm:
- Khó kiểm thử riêng.
- Khó suy luận GC/lifecycle.
- Code dễ gọi private mutable state quá rộng.
- Tăng coupling giữa helper và enclosing class.

Nếu một helper cần vài scalar immutable values, static nested với constructor nhận các values đó có thể rõ hơn.

## 14. Runnable: inner vs static nested về dependency

Lưu **`DependencyChoiceDemo.java`**:

```java
public final class DependencyChoiceDemo {
    private final String prefix;

    DependencyChoiceDemo(String prefix) {
        this.prefix = prefix;
    }

    final class InnerFormatter {
        String format(String message) {
            return prefix + ":" + message;
        }
    }

    static final class StaticFormatter {
        private final String prefix;

        StaticFormatter(String prefix) {
            this.prefix = prefix;
        }

        String format(String message) {
            return prefix + ":" + message;
        }
    }

    public static void main(String[] args) {
        DependencyChoiceDemo owner =
                new DependencyChoiceDemo("app");

        InnerFormatter inner = owner.new InnerFormatter();

        StaticFormatter helper =
                new StaticFormatter("app");

        System.out.println(inner.format("ready"));
        System.out.println(helper.format("ready"));
    }
}
```

```bash
javac -encoding UTF-8 DependencyChoiceDemo.java
java DependencyChoiceDemo
```

Stdout:

```text
app:ready
app:ready
```

Cả hai implementations cho cùng kết quả, nhưng **relationship** khác:
- `InnerFormatter` mang quan hệ enclosing owner.
- `StaticFormatter` giữ đúng `String prefix` nó cần.

Nếu formatter thực chất chỉ phụ thuộc vào prefix, static nested thường dễ tái sử dụng/test hơn.

## 15. Public static nested type: đôi khi là API tốt

Không phải nested class nào cũng nên private. Một **public static nested class** có thể mô tả một kiểu **phụ thuộc khái niệm** vào một API owner:

- `Map.Entry<K,V>` là ví dụ quen thuộc về **nested interface** trong API Java.
- `Outer.Builder` cho fluent builder của Outer.
- `Response.Status` nếu Status không có nghĩa độc lập ngoài Response theo domain.
- `Parser.Token` nếu Token là một phần của public parser API.

Ví dụ:

```java
public final class HttpRequest {
    public static final class Builder {
        // ...
    }
}
```

Client nhìn thấy `HttpRequest.Builder` và hiểu vai trò builder đi cùng HttpRequest.

### Nhưng public nested cũng tạo coupling

Nếu một public nested type bắt đầu được nhiều module dùng mà **không cần enclosing API**, qualified name dài `Outer.Nested` có thể mô tả quan hệ sở hữu sai.

Một public `Invoice.Money` chỉ hợp lý nếu “Money là type chỉ có nghĩa trong Invoice”. Nếu Money dùng chung cho refund/pricing, top-level `Money` thường rõ ràng hơn.

**Quy tắc:** public nested phù hợp khi **qualified name thêm thông tin hữu ích**, chứ không chỉ giúp giảm số file source.

## 16. Runnable: public static nested Builder

Lưu **`RequestBuilderChoiceDemo.java`**:

```java
public final class RequestBuilderChoiceDemo {
    private final String path;
    private final int retries;

    private RequestBuilderChoiceDemo(Builder builder) {
        path = builder.path;
        retries = builder.retries;
    }

    @Override
    public String toString() {
        return "Request[path=" + path
                + ", retries=" + retries + "]";
    }

    public static final class Builder {
        private String path = "/";
        private int retries = 0;

        public Builder path(String value) {
            path = value;
            return this;
        }

        public Builder retries(int value) {
            retries = value;
            return this;
        }

        public RequestBuilderChoiceDemo build() {
            return new RequestBuilderChoiceDemo(this);
        }
    }

    public static void main(String[] args) {
        RequestBuilderChoiceDemo request =
                new RequestBuilderChoiceDemo.Builder()
                        .path("/health")
                        .retries(3)
                        .build();

        System.out.println(request);
    }
}
```

```bash
javac -encoding UTF-8 RequestBuilderChoiceDemo.java
java RequestBuilderChoiceDemo
```

Stdout:

```text
Request[path=/health, retries=3]
```

Builder tồn tại **trước khi Request được tạo**, nên làm non-static member inner class của Request sẽ tạo dependency ngược rất kỳ lạ: phải có Request instance để build một Request mới.

## 17. Local class: chỉ dùng trong một block, nhưng có tên

Một **local class** phù hợp khi logic:
- Chỉ được dùng trong một method/block.
- Đủ lớn để đáng có một tên type, instance fields hoặc nhiều methods.
- Cần capture một vài biến cục bộ `final`/`effectively final`.
- Không đáng trở thành member nested hoặc top-level type.

Ví dụ:

```java
void execute() {
    int limit = 3;

    class LocalChecker {
        boolean valid(int value) {
            return value < limit;
        }
    }

    LocalChecker checker = new LocalChecker();
}
```

Đây chỉ là snippet minh họa thân method. Tên `LocalChecker` không được code ngoài method nhìn thấy.

### Không nhầm scope tên với object lifetime

Local class instance có thể được trả về qua một interface và sống lâu hơn method tạo nó. Nó vẫn là object Java thông thường; chỉ **tên class trong source** bị giới hạn scope.

Nếu local class dần được dùng trong hai hoặc ba methods khác nhau, thường nên đưa thành một member nested class hoặc top-level class.

## 18. Runnable: local class làm chiến lược tạm thời

Lưu **`LocalStrategyChoiceDemo.java`**:

```java
public class LocalStrategyChoiceDemo {
    interface Labeler {
        String label(int value);
    }

    static Labeler makeLabeler(String prefix) {
        int factor = 2;

        class LocalLabeler implements Labeler {
            @Override
            public String label(int value) {
                return prefix + "-" + (value * factor);
            }
        }

        return new LocalLabeler();
    }

    public static void main(String[] args) {
        Labeler first = makeLabeler("A");
        Labeler second = makeLabeler("B");

        System.out.println(first.label(3));
        System.out.println(second.label(5));
    }
}
```

```bash
javac -encoding UTF-8 LocalStrategyChoiceDemo.java
java LocalStrategyChoiceDemo
```

Stdout:

```text
A-6
B-10
```

- `LocalLabeler` có tên nhưng chỉ nhìn thấy trong `makeLabeler`.
- `prefix` và `factor` được capture dưới yêu cầu effectively final.
- Caller chỉ cần API `Labeler`, không cần biết local implementation type.

Nếu behavior chỉ một biểu thức và interface có một abstract method, lambda cũng có thể là lựa chọn gọn hơn.

## 19. Anonymous class: chỗ nào cần một implementation inline?

Một **anonymous class** được viết ngay trong biểu thức tạo object:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("hello");
    }
};
```

Thường phù hợp khi:
- Implementation rất ngắn.
- Chỉ được dùng tại một chỗ.
- Không cần tên source type.
- Muốn override method của một superclass hoặc implement interface inline.
- Không cần constructor riêng có tên anonymous class.

Nếu anonymous block trở thành 100 dòng, nhiều fields và nhiều nhánh, hãy cân nhắc class có tên.

**Lưu ý:** nếu mục tiêu chỉ là một functional interface, lambda thường dễ đọc hơn anonymous class. Nhưng lambda và anonymous class không có cùng semantics về `this`, scope và construction; không thay một cách máy móc khi behavior phụ thuộc các chi tiết ấy.

## 20. Runnable: anonymous class cho callback một lần

Lưu **`AnonymousChoiceDemo.java`**:

```java
public class AnonymousChoiceDemo {
    interface Formatter {
        String format(int value);
    }

    public static void main(String[] args) {
        Formatter formatter = new Formatter() {
            @Override
            public String format(int value) {
                return "[" + value + "]";
            }
        };

        System.out.println(formatter.format(7));
    }
}
```

```bash
javac -encoding UTF-8 AnonymousChoiceDemo.java
java AnonymousChoiceDemo
```

Stdout:

```text
[7]
```

Trong riêng ví dụ này, `Formatter formatter = value -> "[" + value + "]";` cũng là một cách viết tốt vì Formatter là functional interface. Anonymous class vẫn hữu ích khi cần instance state, multiple methods hoặc subclass semantics.

## 21. Anonymous class và lambda không thay thế nhau mọi trường hợp

Một số khác biệt:

| Vấn đề | Anonymous class | Lambda |
| --- | --- | --- |
| Có anonymous class declaration? | Có | Không |
| Target được phép là | Interface phù hợp hoặc superclass không bị cấm subclass | Functional interface |
| `this` trong body instance | Chính anonymous object | `this` từ enclosing lexical context |
| Có thể khai báo instance fields | Có | Không khai báo class body fields riêng kiểu anonymous |
| Có thể override nhiều methods | Có nếu cần | Chỉ cung cấp functional method implementation |
| Có thể gọi `super` của anonymous subclass | Có khi hợp lệ | Không có anonymous subclass super như vậy |
| Truy cập local variables | Final/effectively final | Final/effectively final |
| Thích hợp cho | Subclass/callback có state/class semantics | Behavior ngắn của functional interface |

### Cẩn thận khi đổi anonymous thành lambda

Anonymous class trong một instance method có `this` là anonymous object. Lambda trong cùng method có `this` là enclosing instance. Nếu body gọi `this.someMethod()`, refactor có thể đổi target method hoặc thậm chí không compile.

Vì vậy “chỉ muốn giảm số dòng” chưa đủ để chọn refactor: kiểm tra `this`, overload resolution, shadowing và state đã capture.

## 22. Top-level package-private hay private static nested?

Đây là một câu hỏi thiết kế quan trọng.

Giả sử `Order` dùng `OrderValidator` nội bộ.

**Phương án A — package-private top-level:**

```java
final class OrderValidator {
    boolean valid(int quantity) {
        return quantity > 0;
    }
}
```

Các classes khác trong **cùng package** có thể gọi tên này theo access rules.

**Phương án B — private static nested:**

```java
final class Order {
    private static final class Validator {
        boolean valid(int quantity) {
            return quantity > 0;
        }
    }
}
```

`Validator` bị giấu chặt theo enclosing/nest access boundary. Đặt tên `Order.Validator` thể hiện đây là chi tiết thuộc Order.

### Quyết định thế nào?

- Helper phục vụ **nhiều classes trong cùng package**, nhưng không muốn public → top-level package-private.
- Helper phục vụ **chỉ một class** và không có independent meaning → private static nested.
- Helper có ý nghĩa public cho nhiều packages → top-level public hoặc public nested nếu thuộc owner khái niệm.
- Helper cần owner instance cho mỗi operation → member inner hoặc static helper truyền owner, tùy lifecycle/coupling.

**Không nên lạm dụng private nested** để trộn nhiều responsibilities vào cùng một class. Enclosing class vẫn nên có một mục đích rõ.

## 23. Runnable: helper private static nested cho validator

Lưu **`ScopedValidatorDemo.java`**:

```java
public final class ScopedValidatorDemo {
    private final int quantity;

    ScopedValidatorDemo(int quantity) {
        if (!Validator.isValid(quantity)) {
            throw new IllegalArgumentException("quantity");
        }
        this.quantity = quantity;
    }

    private static final class Validator {
        static boolean isValid(int quantity) {
            return quantity > 0;
        }
    }

    public static void main(String[] args) {
        ScopedValidatorDemo valid =
                new ScopedValidatorDemo(3);

        System.out.println(valid.quantity);

        try {
            new ScopedValidatorDemo(0);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 ScopedValidatorDemo.java
java ScopedValidatorDemo
```

Stdout:

```text
3
quantity
```

`Validator` là chi tiết của `ScopedValidatorDemo`, không cần một owner instance. Nếu validation rules sau đó dùng ở nhiều domain types, có thể tách chúng thành một top-level package-private/public type với contract rõ.

## 24. Những tiêu chí thiết kế nên ưu tiên theo thứ tự

Một quy trình đơn giản:

**Câu 1 — Type có ý nghĩa riêng không?** Nếu có, top-level thường là ứng viên mạnh.

**Câu 2 — Type có phục vụ một owner duy nhất không?** Nếu có, nested có thể giúp đóng gói tốt.

**Câu 3 — Có cần enclosing instance thực sự không?** Nếu không, ưu tiên static nested member.

**Câu 4 — Có chỉ dùng trong một method không?** Nếu có và logic cần tên, local class có thể đủ.

**Câu 5 — Có chỉ một implementation nhỏ tại một call site không?** Nếu có, anonymous hoặc lambda khi phù hợp.

**Câu 6 — Nếu public, qualified name giúp API rõ nghĩa hay gây coupling?** Cần kiểm tra trước khi xuất bản type.

**Câu 7 — Class sẽ tồn tại bao lâu?** Kiểm tra reference retention, callback lifecycle, shared state và memory boundaries.

**Câu 8 — Khi thay đổi thiết kế, bao nhiêu callers phải sửa?** Một public nested type chuyển thành top-level là thay đổi API có thể lan rộng.

Đừng bắt đầu bằng “muốn ít file Java nhất”; bắt đầu bằng **trách nhiệm của type**.

## 25. Decision tree cho lựa chọn thực tế

```text
Kiểu mới có một vai trò độc lập, tái dùng nhiều nơi?
  ├── Có → cân nhắc top-level class/record/interface
  └── Không
       │
       ├── Chỉ là helper của một enclosing type?
       │     ├── Có → cần enclosing object cụ thể?
       │     │          ├── Có → member inner hoặc static + owner rõ
       │     │          └── Không → private/public static nested theo API
       │     └── Không → xét package-private top-level
       │
       └── Chỉ xuất hiện trong một block/call site?
             ├── Cần tên/type state tương đối dài → local class
             └── Implementation ngắn → anonymous/lambda phù hợp
```

Sơ đồ là **gợi ý lựa chọn**, không phải ngữ pháp có duy nhất một đáp án. Một helper chỉ xuất hiện một chỗ vẫn có thể đáng tách top-level nếu nó có behavior phức tạp, cần test độc lập hoặc dễ phát triển thành concept riêng.

## 26. Cohesion: trách nhiệm càng gần nhau, nesting càng có lý

**Cohesion** nói về mức độ những thành phần trong một module/type phục vụ cùng trách nhiệm.

Một `LinkedList` có private `Node`:
- Node mô tả đơn vị lưu trữ để LinkedList hoạt động.
- Node không đại diện cho domain concept public.
- Node sẽ đổi khi LinkedList đổi implementation.
- Private static nested Node là cách tổ chức hợp lý.

Ngược lại, `Order` và `Customer` có thể tương tác nhưng không có nghĩa Customer là chi tiết triển khai của Order:
- Customer có identity/lifecycle riêng.
- Nhiều Orders trỏ cùng Customer.
- Customer dùng bởi nhiều services.
- Top-level `Customer` thường rõ hơn `Order.Customer`.

### “Cùng dùng chung file” không đồng nghĩa cohesion

Nếu hai classes chỉ tình cờ được viết cùng một file vì một người phụ trách, nesting có thể che giấu ranh giới domain cần tách.

**Hãy xét nguyên nhân thay đổi**:
- Hai types thường cần sửa cùng lúc vì chung một invariant? Nesting có thể hợp lý.
- Một type thay đổi theo lý do độc lập? Top-level thường tránh coupling không cần thiết.

## 27. Encapsulation: private nested giúp giấu representation

Một class public có thể giữ internal data structure không lộ ra ngoài:

```java
public class UserIndex {
    private Node first;

    private static final class Node {
        final String username;
        Node next;

        Node(String username) {
            this.username = username;
        }
    }
}
```

Lợi ích:
- Consumer chỉ biết public methods của UserIndex.
- Thay Node representation không bắt consumer compile theo source type.
- Có thể sử dụng private access qua nest, giảm boilerplate getters chỉ để hai classes giao tiếp.
- Type helper không được code package không liên quan dùng sai mục đích.

**Nhưng tính đóng gói không phải giấu mọi logic bằng private classes.** Nếu Node/Index cùng phình to, có thể một interface hoặc một dedicated top-level abstraction sẽ làm responsibilities rõ hơn.

## 28. Testability: khi nào class lồng khó test?

Một private static nested helper không được test từ code bên ngoài bằng tên riêng. Nhưng điều này **không nhất thiết là vấn đề** nếu nó hoàn toàn là implementation detail:
- Test public operations của owner.
- Kiểm tra observable behavior và invariants.
- Tránh tests bám cứng cấu trúc implementation private.

Nếu helper có logic phức tạp và business-critical:
- Có thể tách thành **package-private top-level class** để test trong cùng package.
- Có thể tách thành public service/domain type nếu nó có contract thực.
- Có thể truyền dependencies/inject strategy để test riêng.
- Hoặc giữ private nested nhưng viết thorough tests qua owner khi coverage và maintainability đủ.

### Đừng công khai implementation chỉ để test một field

Một sai lầm là đổi private nested thành public nested chỉ để unit test truy cập một method. Thay đổi visibility có thể mở API không mong muốn. Trước tiên xem lại behavioral test và ranh giới trách nhiệm.

### Static nested dễ test hơn inner khi không cần owner

Với inner class, test thường phải dựng enclosing instance. Nếu helper độc lập về logic, static nested hoặc top-level class làm setup đơn giản hơn.

## 29. Rủi ro lộ private implementation qua public API

Ví dụ:

```java
public class Catalog {
    private static class InternalEntry {
        String code;
    }

    // Không nên thiết kế public API quanh InternalEntry.
}
```

Một public method có thể về mặt source khai báo return type private nested, nhưng caller ngoài không có cách sử dụng đầy đủ type ấy một cách bình thường. API như vậy khó học, khó maintain và phụ thuộc implementation.

Nên công bố:
- `public record EntryView(String code)` nếu đây là public data carrier thuộc Catalog;
- Hoặc top-level `CatalogEntry` nếu là domain concept độc lập;
- Hoặc một interface công khai phù hợp.

### Return value qua abstraction công khai

Bản thân class thực thi có thể private nested, nhưng return type public:

```java
public java.util.Iterator<String> iterator() {
    return new PrivateIterator();
}
```

Đoạn này là minh họa chữ ký; `PrivateIterator` cần implementation phù hợp trong owner.

Người dùng API không cần biết class implementation. Đây là chiến lược encapsulation hợp lý.

## 30. Nested type và Java module system (JPMS)

Trong một named module, việc một class là public **không tự có nghĩa** mọi module khác dùng nó được. Access liên module còn phụ thuộc:
- Module chứa package có `exports` package đó cho consumer hay không.
- Member/class accessibility.
- Compile/readability relationships giữa modules.
- Reflection có thể cần `opens` hoặc cơ chế khác nếu truy cập deep internals.

Ví dụ module descriptor:

```java
module com.example.billing {
    exports com.example.billing.api;
}
```

Một public top-level type trong package `com.example.billing.internal` không tự trở thành API exported chỉ vì public. Ngược lại, public static nested type trong package API exported có thể là một phần public surface của module.

**Nestmate private access và JPMS exports là hai tầng khác nhau**:
- Nesting có thể cho private access giữa classes liên quan.
- Export/module rules kiểm soát việc module khác truy cập package/types.
- Không nên dùng nested private class để vượt modular encapsulation.

Chọn top-level hay nested cùng với **package boundary** và **module API surface**, không chỉ nhìn một file source.

## 31. Package organization và trách nhiệm miền nghiệp vụ

Trong dự án lớn, package structure thường quan trọng không kém nesting.

Ví dụ:

```text
com.acme.orders
    Order.java
    OrderLine.java
    OrderService.java

com.acme.pricing
    Money.java
    PricingPolicy.java

com.acme.orders.internal
    OrderIndex.java
```

Nếu `OrderLine` có tên và hành vi public của domain, top-level `OrderLine` là lựa chọn dễ giải thích. Nếu `Order` tự dùng một `Node` để thực hiện linked buffer nội bộ, private static nested Node phù hợp.

### Package-private top-level như một điểm giữa

Không phải mọi class độc lập phải public:
- Top-level package-private helper cho phép **nhiều classes trong cùng package** phối hợp.
- Nó không ép helper thuộc một owner duy nhất.
- Nó không làm helper trở thành API chung cho code ở package khác.
- Khi helper phát triển, có thể chuyển sang dedicated file mà không đổi qualified type theo cách đã công bố trong cùng package.

### Nhưng tên package không bảo đảm dependency architecture

Dù top-level types được sắp xếp đẹp, nếu hai modules tham chiếu vòng tròn hoặc expose internals tùy tiện thì thiết kế vẫn có vấn đề. Nesting chỉ là một phần của kiến trúc.

## 32. Tên type: `Outer.Part` có phải hợp ngữ nghĩa?

Một nested public type tạo cách gọi `Outer.Part`.

Chọn nested nếu một tên như:
- `Request.Builder`;
- `Parser.Token`;
- `StateMachine.Transition`;

làm người dùng hiểu ngay ngữ cảnh.

Tránh nested nếu:
- `Order.Money` khi Money cần cho nhiều aggregates.
- `User.DateRange` khi DateRange là khái niệm thời gian chung.
- `Screen.Logger` khi Logger là service dùng toàn hệ thống.

Đôi khi type công khai giống tên trong nhiều miền, qualified nested name giảm ambiguity. Nhưng nếu nesting chỉ để tránh xung đột tên, xem lại domain naming và packages trước.

## 33. Nested interface, enum và record

Không chỉ ordinary classes mới có thể nested. Trong Java 17:
- Nested interfaces có **static semantics** theo rules.
- Member records là **implicitly static**.
- Member enums có static semantics tương ứng.
- Interface nested types không có implicit enclosing instance giống member inner class.

Ví dụ:

```java
public final class Job {
    public enum Status {
        NEW, DONE
    }

    public record Result(Status status, String message) {
    }
}
```

Có thể dùng `Job.Status.DONE` và `new Job.Result(...)` mà không cần một Job instance.

### Khi nào cho enum/record nested?

- Nếu `Status` thật sự mô tả lifecycle của Job và không mang ý nghĩa ngoài Job, `Job.Status` làm API rõ.
- Nếu `Status` dùng xuyên nhiều aggregates với semantics thống nhất, top-level enum có thể phù hợp hơn.
- Nếu `Result` là kết quả duy nhất của Job API, nested record có thể gọn; nếu nhiều APIs chia sẻ kiểu ấy, xem xét top-level.

### Record tự động “an toàn”?

Record thường là final, components final, nhưng nếu component chứa array/List mutable thì không tự deep immutable. Quyết định nested/top-level **không thay thế** thiết kế mutable ownership.

## 34. Runnable: nested record, enum đi cùng owner

Lưu **`NestedResultChoiceDemo.java`**:

```java
public final class NestedResultChoiceDemo {
    public enum Status {
        OK, REJECTED
    }

    public record Result(Status status, String message) {
    }

    public static Result evaluate(int quantity) {
        if (quantity > 0) {
            return new Result(Status.OK, "accepted");
        }
        return new Result(Status.REJECTED, "invalid");
    }

    public static void main(String[] args) {
        System.out.println(evaluate(3));
        System.out.println(evaluate(0));
    }
}
```

```bash
javac -encoding UTF-8 NestedResultChoiceDemo.java
java NestedResultChoiceDemo
```

Stdout:

```text
Result[status=OK, message=accepted]
Result[status=REJECTED, message=invalid]
```

Nested enum/record thể hiện hai types có ngữ nghĩa sát với owner API; chúng không cần enclosing instance.

## 35. Nested generic types và tính độc lập

Một generic enclosing class:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    class Reader {
        T read() {
            return value;
        }
    }

    static class Holder<U> {
        final U value;

        Holder(U value) {
            this.value = value;
        }
    }
}
```

- Member inner `Reader` có thể dùng `T` của enclosing generic instance.
- Static nested `Holder<U>` có type parameter `U` riêng.
- Static nested class không thể dùng trực tiếp `T` của Box như type parameter của instance Outer.

Khi thiết kế, nếu nested helper bắt đầu cần type parameters độc lập và được dùng ở nhiều contexts, có thể là dấu hiệu top-level generic helper phù hợp hơn.

Ngược lại, `Box<T>.Reader` thể hiện **Reader gắn với một Box<T> instance**, đúng nếu semantics require owner.

## 36. Runnable: generic Outer với inner và static nested

Lưu **`GenericClassChoiceDemo.java`**:

```java
public final class GenericClassChoiceDemo<T> {
    private final T value;

    GenericClassChoiceDemo(T value) {
        this.value = value;
    }

    class Reader {
        T read() {
            return value;
        }
    }

    static class Holder<U> {
        private final U value;

        Holder(U value) {
            this.value = value;
        }

        U read() {
            return value;
        }
    }

    public static void main(String[] args) {
        GenericClassChoiceDemo<String> box =
                new GenericClassChoiceDemo<>("Java");

        GenericClassChoiceDemo<String>.Reader reader =
                box.new Reader();

        GenericClassChoiceDemo.Holder<Integer> holder =
                new GenericClassChoiceDemo.Holder<>(17);

        System.out.println(reader.read());
        System.out.println(holder.read());
    }
}
```

```bash
javac -encoding UTF-8 GenericClassChoiceDemo.java
java GenericClassChoiceDemo
```

Stdout:

```text
Java
17
```

Kiểu của Reader gắn với một parameterization của generic enclosing type; Holder độc lập và có type parameter của riêng nó.

## 37. “Static nested class chạy nhanh hơn inner class” có đúng không?

Không nên đưa ra một kết luận hiệu năng tuyệt đối chỉ từ keyword `static`.

Khác biệt thiết kế:
- Inner class có enclosing-instance relationship, nên có thể kéo theo reference/coupling và chi phí liên quan.
- Static nested không cần implicit enclosing object.
- JVM/JIT có nhiều tối ưu, layout/escape analysis và representation details không nên biến thành giả định cứng.
- Phần logic/allocations/locks bên trong class thường ảnh hưởng performance lớn hơn từ khóa ở declaration.

**Chọn static nested vì đúng dependency semantics trước**, rồi đo profile nếu performance thực sự quan trọng.

Không dùng dự đoán kích thước object/bytecode làm lý do duy nhất để thay đổi public API.

## 38. Lifetime và garbage collection: điều nên nhìn

Mọi object còn reachable từ GC roots qua reference paths có thể tiếp tục được giữ.

Đối với nested/member inner:
- Một inner instance có thể duy trì quan hệ tới enclosing instance.
- Một anonymous/local callback có thể capture references, tùy context.
- Long-lived registry/thread/executor có thể kéo dài tuổi thọ của callback.
- Khi callback giữ owner reference, owner có thể còn reachable.

Đối với static nested:
- Không có implicit Outer instance do nesting.
- Nhưng nếu constructor nhận `Outer owner` và lưu field, nó **vẫn giữ owner**.
- Vì vậy chỉ chuyển `class Inner` thành `static class Helper` rồi tiếp tục giữ `owner` cũng không tự loại bỏ retention.

**Giải quyết bằng việc quản lý ownership và lifecycle**, không chỉ thay keyword.

### Ví dụ anti-pattern nhận diện

```java
class Screen {
    class Listener {
        void onEvent() {
            // Dùng state của Screen.
        }
    }
}
```

Nếu Listener được đăng ký global và không unregister, Screen có thể sống lâu hơn mong đợi. Một static nested listener chỉ nhận immutable ID và unregister đúng lúc có thể tốt hơn nếu requirements cho phép.

## 39. Nested classes và `synchronized`/thread safety

Chọn class nested hay top-level **không tự cung cấp synchronization**.

```java
class Outer {
    private int count;

    class Inner {
        void increment() {
            count++;
        }
    }
}
```

Một số người lầm tưởng vì Inner nằm bên trong Outer và truy cập private field, Java tự khóa owner. **Không đúng.**

- `count++` không là atomic increment cho nhiều threads.
- Nesting không tạo lock.
- Static nested class cũng không tự thread-safe.
- Local/anonymous classes capture mutable references nhưng cũng không tự tạo happens-before guarantees.

Nếu đối tượng được chia sẻ giữa threads, dùng phù hợp:
- Immutable state/snapshots;
- `synchronized`/locks với invariant rõ;
- Atomic classes/collections;
- Hoặc cơ chế concurrency cao cấp khác.

## 40. Tổ chức file source và class file được sinh

Một source file `Outer.java` có nested classes có thể tạo ra nhiều `.class` files khi biên dịch.

Ví dụ:

```java
class Outer {
    static class Helper {
    }

    class Inner {
    }
}
```

Compiler có thể sinh các class files có tên tương tự:
- `Outer.class`;
- `Outer$Helper.class`;
- `Outer$Inner.class`.

**Không dùng tên generated `$...` như public business contract.** Những đặc điểm compiler-generated đối với local/anonymous classes có thể thay đổi và không phải thứ người dùng source API cần dựa vào.

### Có phải nested class “chạy bên trong” Outer không?

Không theo nghĩa runtime objects chia cùng memory body. Một nested class vẫn là một runtime type riêng, có class metadata và instances phù hợp. Nesting là khái niệm declaration/access/enclosing context, không phải “một object nằm vật lý trong object kia”.

## 41. Reflection để quan sát kiểu

Java Reflection có:
- `Class.isMemberClass()`;
- `Class.isLocalClass()`;
- `Class.isAnonymousClass()`;
- `Class.getEnclosingClass()`;
- `Class.getDeclaringClass()`;
- `Modifier.isStatic(clazz.getModifiers())`.

Trong việc chọn class organization:
- Reflection classification có thể hỗ trợ framework/debug tooling.
- Nhưng **không dùng reflection để thay thế thiết kế API**.
- Frameworks có rules constructor/visibility riêng, cần đánh giá contract của framework cụ thể.

### Lưu ý “nested” khác static modifier ở runtime

Một static nested member class và một member inner class đều có thể là `isMemberClass() == true`; static modifier giúp phân biệt.

Một top-level class bình thường không là member/local/anonymous class.

## 42. Runnable: phân biệt top-level và static nested qua reflection

Lưu **`ReflectionChoiceDemo.java`**:

```java
import java.lang.reflect.Modifier;

final class PackageHelper {
}

public class ReflectionChoiceDemo {
    static class Nested {
    }

    class Inner {
    }

    public static void main(String[] args) {
        Class<?> top = PackageHelper.class;
        Class<?> nested = Nested.class;
        Class<?> inner = Inner.class;

        System.out.println(top.isMemberClass());
        System.out.println(nested.isMemberClass());
        System.out.println(inner.isMemberClass());

        System.out.println(Modifier.isStatic(
                nested.getModifiers()));
        System.out.println(Modifier.isStatic(
                inner.getModifiers()));
    }
}
```

```bash
javac -encoding UTF-8 ReflectionChoiceDemo.java
java ReflectionChoiceDemo
```

Stdout:

```text
false
true
true
true
false
```

Mã không dựa vào các tên class files do compiler sinh. Nó chỉ dùng các classification APIs có contract rõ.

## 43. Kế thừa và nesting là hai vấn đề độc lập

Một class có thể:
- Extend superclass;
- Implement interfaces;
- Là top-level hoặc nested;
- Có visibility độc lập phù hợp với declaration;
- Có hoặc không enclosing instance.

Ví dụ:

```java
class Worker implements Runnable {
    @Override
    public void run() {
    }
}
```

và:

```java
class Outer {
    private static class Worker implements Runnable {
        @Override
        public void run() {
        }
    }
}
```

đều triển khai Runnable. Khác biệt chính là **placement/access/naming**, không phải việc implement interface có khác ý nghĩa.

Một inner class `Outer.Inner` **không tự extends Outer**.

**Không chọn nested chỉ vì “phải kế thừa Outer”**; nếu cần is-a relationship, khai báo inheritance đúng và đánh giá domain semantics.

## 44. Thay đổi top-level thành nested: những gì phải xem lại

Refactor từ:

```java
public class Token {
}
```

sang:

```java
public class Parser {
    public static class Token {
    }
}
```

có thể làm thay đổi:
- Source type name: `Token` → `Parser.Token` tại call sites/imports.
- Binary name của class.
- Public API signatures ở nơi dùng type.
- Reflection/class-loading tên type.
- Serialization/configuration/deserialization nơi lưu tên class.
- Module packaging/export expectations.
- Framework annotations và class discovery.
- Constructor call/visibility.

Nếu đây là internal private helper chưa bị ai ngoài owner dùng, refactor có thể đơn giản. Nếu là **published public type**, đây thường là **breaking API change**.

### Không giả định đổi nesting chỉ sửa một file

Phạm vi callers có thể rộng hơn nhiều: tests, generated code, reflection config, persisted data và binary dependencies. Cần hiểu compatibility contract trước.

## 45. Thay member inner thành static nested: rủi ro

Chuyển:

```java
class Outer {
    class Inner {
        String describe() {
            return Outer.this.toString();
        }
    }
}
```

thành:

```java
class Outer {
    static class Inner {
        // Không còn Outer.this.
    }
}
```

không phải chỉ thêm `static`. Nếu class dùng enclosing instance:
- Phải truyền một `Outer` reference cụ thể khi tạo helper.
- Các constructors/call sites `outer.new Inner()` phải đổi sang `new Outer.Inner(owner)` hoặc factory tương ứng.
- Phải xem lại lifetime, equality và captured state.
- Nếu public, source/binary compatibility có thể thay.
- Phải test behavior khi có nhiều Outer instances.

Nếu helper **không cần** enclosing instance, việc chuyển sang static nested thường là bước cải tiến dễ hiểu hơn.

## 46. Thay static nested thành top-level: khi nào hợp lý?

Tín hiệu helper đang lớn lên thành type độc lập:
- Được import/reuse bởi nhiều owners.
- Có nhiều collaborators và state không liên quan đến Outer.
- Có unit tests trực tiếp như một API.
- Có business rules riêng, nhiều reasons-to-change.
- Cần public contract riêng hoặc package-level ownership.
- Qualified name `Outer.Helper` gây hiểu nhầm ownership.

Phương án:
1. Xác định chính xác trách nhiệm và public contract.
2. Tạo top-level type với tên/package thích hợp.
3. Di chuyển behavior; thay private access bằng API/dependency rõ thay vì mở hết fields.
4. Cập nhật callers/imports.
5. Chạy compile/tests của module consumers.
6. Nếu là API public, xem xét compatibility/migration strategy.

**Không nên tách chỉ vì class dài 200 dòng** nếu nó vẫn là một implementation detail rất cohesive của Outer. Độ dài là một tín hiệu cần review, không phải quy tắc cứng.

## 47. Khi top-level class muốn truy cập private state của một owner

Một top-level class **không** tự có quyền truy cập private fields của một class khác, kể cả khi ở cùng package.

Ví dụ:

```java
class Outer {
    private int secret = 7;
}

class Helper {
    int read(Outer outer) {
        // return outer.secret; // Không hợp lệ: private.
        return 0;
    }
}
```

Nếu `Helper` là private static nested class của Outer, nó có thể truy cập `outer.secret` theo nesting access.

Đừng vội thêm public getter cho mọi private field chỉ để giúp helper dùng được; làm vậy có thể lộ state rộng hơn mong muốn. Xem xét:
- Giữ helper nested nếu nó thực sự thuộc implementation detail.
- Cho Helper nhận một **value snapshot**/interface được owner định nghĩa.
- Cung cấp package-private operation có ranh giới hợp lý nếu trong package.
- Tách abstraction/domain responsibility nếu nhu cầu vượt một owner.

## 48. Code tổ chức đơn giản hơn đôi khi là method, không phải class mới

Trước khi chọn nested hoặc top-level, hãy hỏi:

> Ta có thực sự cần một **class** mới không?

Nếu chỉ có một phép biến đổi stateless:

```java
private static boolean validQuantity(int quantity) {
    return quantity > 0;
}
```

một private static method trong owner có thể rõ hơn tạo `private static class Validator` chỉ có đúng một static method.

Nếu logic mang nhiều state/invariants và cần constructor, class có ý nghĩa hơn. Nếu logic là value carrier đơn giản, record có thể phù hợp. Nếu logic là một behavior đóng gói được truyền đi, functional interface + lambda cũng đáng xét.

**Đừng tạo quá nhiều nested classes chỉ để nhóm vài dòng code** khi method/record/enum đã đáp ứng rõ.

## 49. Không lạm dụng “utility class”

Một `private static class Utils` khổng lồ chứa:
- Date parsing;
- Currency conversion;
- HTTP calls;
- Validation;
- Logging;
- Formatting;

có cohesion rất thấp. Việc nó nằm nested không sửa được vấn đề thiết kế.

Tách responsibilities theo ranh giới thật:
- Domain value concepts có thể top-level.
- Implementation helper chỉ thuộc owner có thể private static nested.
- Cross-cutting service/utility có thể là top-level class với API rõ.
- Operations nhỏ nên vẫn là methods.

**Đặt tên “Utils” hoặc “Helper” thường là dấu hiệu cần tìm một tên có nghĩa hơn**, nhưng không phải mọi Helper đều sai.

## 50. Local/anonymous quá nhiều có thể làm code khó tìm

Nếu một method chứa nhiều anonymous implementations, logic nghiệp vụ có thể bị ẩn trong callback blocks:

```java
register(new Callback() { /* nhiều logic */ });
schedule(new Runnable() { /* nhiều logic */ });
transform(new Function<>() { /* nhiều logic */ });
```

Đây là các snippets minh họa, không phải standalone runnable.

Hướng cải tiến:
- Các callback ngắn → lambda.
- Một behavior dài nhưng chỉ dùng trong method → local named class.
- Reusable helper riêng của owner → private static nested.
- Business strategy độc lập → top-level implementation/service.

Cân nhắc **debuggability** và **testability** bên cạnh việc giảm số dòng source.

## 51. Tình huống thiết kế: Parser, Token và Lexer

Một Parser cần tokens khi phân tích dữ liệu.

**Phương án nested:**

```java
public final class Parser {
    public record Token(String text, int position) {
    }
}
```

Hợp lý nếu:
- Token chỉ có ý nghĩa trong Parser API.
- Client luôn làm việc qua Parser.
- Qualified `Parser.Token` giảm nhầm lẫn với token khác.
- Không cần một tokenizer độc lập.

**Phương án top-level:**

```java
public record Token(String text, int position) {
}
```

Hợp lý nếu:
- Token được dùng bởi Lexer, Parser, SyntaxHighlighter, IDE, Analytics.
- Nó có contract riêng và versioning độc lập.
- Nhiều modules cần import Token mà không phụ thuộc Parser naming.

**Không có câu trả lời đúng tuyệt đối**, nhưng trách nhiệm của Token cần được quyết định trước.

## 52. Tình huống thiết kế: Builder của immutable value object

Một immutable `Config` có constructor nhiều tham số. `Config.Builder`:
- Mang ý nghĩa tạo Config.
- Không phải domain entity độc lập.
- Có thể mutable trong giai đoạn build.
- Không cần Config instance có sẵn.

**Chọn public static nested Builder** khi public builder là cách xây Config:

```java
Config config = new Config.Builder()
        .host("localhost")
        .port(8080)
        .build();
```

Ví dụ là đoạn sử dụng ý tưởng; class Config và methods cần được định nghĩa theo API thực.

Không chọn member inner Builder vì nó yêu cầu enclosing Config instance, trái mục đích xây Config mới.

## 53. Tình huống thiết kế: Iterator của collection

Một collection có thể cung cấp Iterator.

**Member inner iterator** hợp lý nếu:
- Nó cần đọc/sửa chính owner instance.
- Việc gắn vòng đời/owner là một phần thiết kế.
- Cần truy cập state bao ngoài thường xuyên.

**Static nested iterator** hợp lý nếu:
- Nó chỉ cần explicit collection reference/array snapshot.
- Muốn làm rõ dependency.
- Không muốn implicit enclosing relation.

**Top-level iterator** hợp lý khi iterator là abstraction độc lập/reusable ở nhiều collection types, có contract riêng.

Không có luật “iterator luôn phải inner”; nhiều implementations Java dùng các cấu trúc khác nhau.

## 54. Tình huống thiết kế: DTO, request, response

Một `PaymentResponse.Result` nested record có thể hợp lý nếu chỉ thuộc PaymentResponse.

Nhưng `Money` và `CurrencyAmount` nên được xem xét như **top-level domain value objects** khi nhiều requests/responses dùng.

### Đừng nhầm nested type với JSON hierarchy

JSON:

```text
{
  "order": {
    "id": "O1",
    "amount": 100
  }
}
```

không buộc Java classes phải nested theo cấu trúc JSON. Một `OrderDto` top-level vẫn có thể được serialize thành nested JSON object; đó là trách nhiệm của DTO mapping/serializer.

**Java nesting là quyết định source/API**, không phải yêu cầu cấu trúc payload.

## 55. Tình huống thiết kế: event listeners

Một listener chỉ dùng một lần để in log đơn giản → lambda.

Một listener dài nhưng chỉ dùng trong setup method → local class hoặc named helper.

Một listener là implementation detail của one screen/controller → private static nested nếu không cần enclosing instance, hoặc inner nếu owner relation được mong muốn.

Một event handler/service sử dụng ở nhiều phần hệ thống → top-level class phù hợp hơn.

**Bắt buộc xét lifecycle**: listener đăng ký với event bus có thể sống lâu. Giấu listener làm inner class không miễn trừ trách nhiệm unregister.

## 56. Tình huống thiết kế: Strategy pattern

Một `PricingPolicy` interface và nhiều implementations:

```java
interface PricingPolicy {
    int price(int base);
}
```

Nếu policies là reusable business rules, top-level classes như `SeasonalPricingPolicy`, `MemberPricingPolicy` thường phù hợp.

Nếu chỉ một specialized policy áp dụng bên trong một owner và không tái dùng, private static nested class hoặc local class đủ rõ.

Nếu policy chỉ một biểu thức và interface là functional, lambda:

```java
PricingPolicy tenPercentOff = base -> base * 9 / 10;
```

đơn giản hơn một class có tên.

**Đừng dùng class placement để che domain decisions**: một policy có semantics business lớn cần tên và test riêng dù chỉ có một caller hiện tại.

## 57. Tình huống thiết kế: value object được nhiều aggregates chia sẻ

`Address`, `EmailAddress`, `Money`, `DateRange` thường là candidates cho top-level record/class vì:
- Không phụ thuộc một parent instance.
- Có invariants và validation riêng.
- Dùng lại trong nhiều aggregates.
- Có value equality/hashing tự thân.
- Dễ tìm bằng IDE/search.

Ví dụ:

```java
public record Money(long cents, String currency) {
}
```

Nếu Money chỉ còn trong Invoice package, có thể package-private top-level thay vì public; cân nhắc public surface theo consumer.

**Record không phải lý do bắt buộc top-level**: nested record vẫn hợp lệ và hữu ích nếu domain thật sự subordinated.

## 58. Public API stability và source compatibility

Khi public type tồn tại trong thư viện:
- Tên package + type name là một phần source API.
- Với nested class, tên qualified `Outer.Inner` có ý nghĩa cho imports và references.
- Chuyển nested → top-level có thể buộc caller sửa imports và method signatures.
- Binary name, reflection, serialized forms và framework discovery có thể bị ảnh hưởng.

Nếu chỉ là private static Node, implementation có thể thay mà không cam kết với client. Đó là một lợi ích lớn của encapsulation.

### Nguyên tắc

**Đóng kín điều gì chưa phải contract; công bố điều gì có ý nghĩa ổn định với consumers.**

Đừng công khai `Outer.InternalNode` chỉ để tiện truy cập dữ liệu nội bộ, trừ khi đó thật sự là API có ý nghĩa và được hỗ trợ dài hạn.

## 59. Unit testing sau khi refactor placement

Một chiến lược xác minh:
1. Compile tất cả nguồn dưới JDK/`--release` mục tiêu.
2. Chạy unit tests trên behavior công khai.
3. Nếu helper tách top-level, viết tests trực tiếp cho contract riêng.
4. Nếu inner chuyển static, test nhiều enclosing instances để tránh trỏ nhầm owner.
5. Kiểm tra memory retention/lifecycle callback nếu có.
6. Kiểm tra serialization/reflection/framework registration nếu công khai type name.
7. Kiểm tra access từ packages/modules thực tế.
8. Kiểm tra generics/type parameters và constructor call sites.
9. Không assert compiler-generated names như `Outer$1` một cách máy móc.
10. Nếu API library được dùng bởi binary clients, kiểm tra binary/source compatibility theo chính sách phiên bản.

Chỉ unit test một method mà không compile callers thường không đủ sau một public type move.

## 60. Bài tập 1 — Chọn Node

Một `LinkedStack` có Node chỉ chứa `int value` và `Node next`. Node không bao giờ cần `LinkedStack.this`, code khác không dùng Node.

**Đáp án:** `private static class Node` trong LinkedStack là lựa chọn tốt. Top-level Node sẽ mở rộng scope tên không cần thiết, member inner sẽ gắn implicit enclosing instance không mang ý nghĩa.

## 61. Bài tập 2 — Chọn Money

`Money` dùng trong Order, Invoice, Refund và Ledger; có equality/invariant riêng.

**Đáp án:** Thường là **top-level immutable value object** (record hoặc final class), public/package-private tùy module API. `Order.Money` khiến Money có vẻ thuộc riêng Order.

## 62. Bài tập 3 — Chọn Builder

`UserProfile` immutable cần builder tạo object trước khi UserProfile instance tồn tại.

**Đáp án:** Public/private **static nested Builder** (tùy public API). Không dùng member inner Builder yêu cầu một UserProfile enclosing instance sẵn có.

## 63. Bài tập 4 — Chọn Cursor

`Document.Cursor` đọc và thay thế nội dung đúng một Document instance; cursor không có ý nghĩa nếu tách khỏi owner.

**Đáp án:** Member inner class là ứng viên tốt. Nếu muốn dependency/lifecycle tường minh, static nested Cursor nhận `Document owner` trong constructor cũng có thể đúng.

## 64. Bài tập 5 — Chọn Validator dùng trong hai classes cùng package

`OrderValidator` được Order và ReturnRequest dùng, nhưng không cần là public API.

**Đáp án:** Package-private top-level `OrderValidator` thường phù hợp. Private nested bên trong Order buộc ReturnRequest phụ thuộc hoặc lặp logic, không nhất thiết tốt.

## 65. Bài tập 6 — Top-level private có hợp lệ?

```java
private class Helper {
}
```

nằm ngoài mọi enclosing class.

**Đáp án:** Không. Top-level ordinary class không được private. Chọn package-private top-level hoặc private member nested tùy scope mong muốn.

## 66. Bài tập 7 — Static nested có được đọc private field?

```java
class Outer {
    private int x = 7;

    static class Helper {
        int get(Outer owner) {
            return owner.x;
        }
    }
}
```

**Đáp án:** Có. Nested access cho phép đọc private field qua explicit `owner` reference. Nhưng Helper không có `Outer.this`.

## 67. Bài tập 8 — Static nested tự là singleton?

```java
class Outer {
    static class Helper {
    }
}
```

**Đáp án:** Không. `new Outer.Helper()` nhiều lần tạo nhiều instances. `static` trong class declaration chỉ nói về enclosing-instance relation và membership.

## 68. Bài tập 9 — Member inner có tự extends Outer?

```java
class Outer {
    class Inner {
    }
}
```

**Đáp án:** Không. Nesting khác inheritance. Inner không tự là subtype của Outer.

## 69. Bài tập 10 — Local class dùng lại ở ba methods?

Một named local class được dùng trong một method, rồi yêu cầu reuse logic ở ba methods khác.

**Đáp án:** Xem xét private static nested member class nếu logic thuộc một owner và không cần instance; hoặc top-level package-private nếu nhiều classes trong package dùng. Không copy-paste ba local declarations.

## 70. Bài tập 11 — Callback nhỏ một lần

Một handler chỉ cần gọi `System.out.println("done")` khi callback.

**Đáp án:** Nếu API dùng functional interface, lambda thường là lựa chọn đầu tiên. Anonymous class cũng hợp lệ, nhưng dài hơn. Nếu cần anonymous `this`/subclass semantics thì mới ưu tiên anonymous.

## 71. Bài tập 12 — Anonymous class chứa 200 dòng

Một anonymous implementation có 200 dòng, mutable fields và helper methods, cần test độc lập.

**Đáp án:** Nên cân nhắc named class; private static nested khi chỉ thuộc owner, top-level khi là logic độc lập. Không giữ anonymous chỉ vì ban đầu nó xuất hiện ở một call site.

## 72. Bài tập 13 — Public nested type chuyển top-level

Thư viện công bố `Parser.Token`; phiên bản mới đổi thành `Token` top-level.

**Đáp án:** Đây thường là thay đổi API; cập nhật imports, signatures, reflection/serialization assumptions và xét compatibility trước khi phát hành. Không được coi là refactor nội bộ vô hại.

## 73. Bài tập 14 — Giữ owner qua listener

Một non-static inner listener được event bus singleton giữ sau khi UI screen đóng.

**Đáp án:** Có nguy cơ memory retention của enclosing screen; dùng lifecycle unregister và xem static helper/capture tối thiểu nếu không cần owner instance.

## 74. Bài tập 15 — Package-private vs private nested

Helper chỉ được `Order` dùng. Có nên package-private top-level hay private static nested?

**Đáp án:** Nếu nó thực sự là implementation detail riêng của Order và không cần owner instance, private static nested diễn đạt ownership rõ hơn và giấu chặt hơn. Package-private top-level không sai, nhưng scope rộng hơn.

## 75. Bài tập 16 — Top-level type chứa resource

Một `PaymentGateway` giữ connection/lifecycle riêng và được inject vào nhiều services.

**Đáp án:** Thường là top-level service type/interface, không nested dưới Order chỉ vì Order gọi nó. Resource/dependency nên quản lý lifecycle độc lập.

## 76. Bài tập 17 — Nested enum

`Job.Status` chỉ nói về lifecycle Job.

**Đáp án:** Public nested enum `Job.Status` là thiết kế có thể hợp lý. Nếu nhiều aggregates chia sẻ trạng thái theo cùng contract, top-level enum có thể rõ hơn.

## 77. Bài tập 18 — Inner class và generic outer

`Box<T>.Reader` muốn đọc private `T value` từ đúng Box instance.

**Đáp án:** Member inner class phù hợp. Static nested sẽ không có implicit enclosing instance/type parameter T từ Box và phải nhận owner/type parameter phù hợp tường minh.

## 78. Bài tập 19 — Package export

Một `public class Internal` nằm trong package không được module export.

**Đáp án:** Module khác không tự truy cập class đó chỉ vì public. Phải xét module exports/readability. Nested hay top-level không thay cơ chế JPMS.

## 79. Bài tập 20 — “Không muốn nhiều file”

Một developer đặt `User`, `Order`, `Payment`, `Invoice` thành nested types của `Application` để giảm số file.

**Đáp án:** Đây thường là lý do yếu. Những types có responsibilities độc lập nên top-level/package/module design phù hợp, dù có nhiều file. Ít file không bảo đảm cohesion.

## 80. Bài tập 21 — Inner class mà không dùng owner

Một `class Helper` bên trong Outer không truy cập fields/methods của Outer, không có lifecycle owner requirement.

**Đáp án:** Thường nên cân nhắc thêm `static` cho nested member class, để bỏ implicit enclosing instance coupling. Nếu helper là independent concept, cân nhắc top-level.

## 81. Bài tập 22 — Static nested vẫn giữ owner?

Một static nested Helper constructor nhận `Outer owner` và lưu vào field `private final Outer owner`.

**Đáp án:** Có thể vẫn giữ Outer sống lâu thông qua reference tường minh. `static` không tự xóa memory retention do các fields bạn chủ động lưu.

## 82. Bài tập 23 — Một method có helper logic ba dòng

Để validate `quantity > 0`, cần tạo private static nested `QuantityValidator` không?

**Đáp án:** Không nhất thiết. Một private static method có thể đơn giản hơn, trừ khi logic cần own state, extensibility hoặc type có trách nhiệm đáng đặt tên.

## 83. Bài tập 24 — Nested class và performance

Một member inner và một static nested cùng thực hiện phép cộng đơn giản. Có thể khẳng định static nested luôn nhanh hơn không?

**Đáp án:** Không. Khác biệt chính là dependency/enclosing instance semantics. Performance runtime còn do compiler/JIT, data layout, allocations và behavior thực tế; đo khi có yêu cầu.

## 84. Bài tập 25 — Testability của private Node

Một `LinkedStack` có private static nested Node. Unit test bên ngoài không truy cập Node trực tiếp.

**Đáp án:** Điều đó không nhất thiết xấu. Test `push/pop` và invariants qua public API; nếu Node thành reusable domain concept với contract riêng mới cân nhắc tách type/visibility.

## 85. Bảng lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Lựa chọn đúng hơn |
| --- | --- | --- |
| Đặt mọi class vào một Outer cho ít file | God class, cohesion thấp | Top-level theo responsibilities |
| Mặc định dùng inner cho mọi helper | Coupling/lifetime owner không cần | Static nested nếu không cần `Outer.this` |
| Public mọi nested implementation | API phình to, khó thay đổi | Private nested hoặc package-private |
| Đặt Money dưới Order dù nhiều modules dùng | Qualified name sai ngữ nghĩa | Top-level Money |
| Dùng top-level public chỉ để test internal helper | Mở rộng API vô ý | Test behavior hoặc package-private |
| Chọn static nested vì nghĩ singleton | Hiểu sai modifier | Thiết kế singleton riêng nếu cần |
| Inner class tưởng subtype của Outer | Sai quan hệ type | Phân biệt nesting và inheritance |
| Dùng local class từ method khác | Tên ngoài scope | Member/top-level named class |
| Refactor anonymous → lambda mà không xét `this` | Behavior có thể đổi | Kiểm tra lexical scope |
| Dùng anonymous dài với nhiều responsibilities | Khó debug/test | Named class |
| Dùng nested helper để truy cập private khắp nơi | Coupling quá lớn | Thu hẹp interface/invariant |
| Inner listener global không unregister | Giữ owner lâu | Lifecycle cleanup, static helper |
| Static nested lưu owner rồi nghĩ hết leak | Owner vẫn reachable | Quản lý explicit references |
| Đổi public nested thành top-level không kiểm tra clients | Breaking source/binary APIs | Compatibility/migration |
| Cho rằng top-level private hợp lệ | Lỗi biên dịch | Package-private hoặc private nested |
| Cho rằng public tự vượt JPMS export | Lỗi module access | Thiết kế exports/open đúng |
| Cho rằng nested nhanh/chậm chắc chắn | Quyết định thiếu bằng chứng | Đo benchmark/profile khi cần |
| Dùng generated class names làm hợp đồng | Compiler detail không ổn định | Public type names/contracts |
| Nhầm record nested thành inner instance | Sai static semantics | Xác định nested record implicitly static |
| Cho rằng nesting tạo thread safety | Data races vẫn có | Concurrency contract độc lập |

## 86. Checklist chọn tổ chức lớp

1. Type mới có **khái niệm nghiệp vụ độc lập** không?
2. Có reuse bởi nhiều classes/packages không?
3. Có lifecycle riêng không?
4. Có cần được công bố trong public API không?
5. Nếu public, tên `Outer.Type` có giúp hiểu ownership không?
6. Nếu chỉ phục vụ một owner, có thật sự là implementation detail không?
7. Helper có **cần enclosing instance `Outer.this`** không?
8. Nếu không cần, đã cân nhắc `private static nested` chưa?
9. Nếu cần owner, có nên giữ implicit relation hay explicit reference?
10. Có risk event listener/callback giữ owner sống quá lâu không?
11. Có thể chỉ dùng một private method thay vì class mới không?
12. Logic chỉ trong một method? Local named class có phù hợp không?
13. Logic inline ngắn? Anonymous/lambda có phù hợp không?
14. Nếu anonymous, có dùng anonymous `this`, super hoặc fields không?
15. Nếu refactor anonymous → lambda, đã kiểm tra lexical scope chưa?
16. Nếu local/anonymous capture variables, có final/effectively final không?
17. Captured mutable objects có thread-safe nếu dùng concurrent không?
18. Top-level type cần public hay package-private?
19. Member nested type cần public, protected, private hay package-private?
20. Có đang mở rộng visibility chỉ để test một implementation không?
21. Type lớn lên có nhiều reasons-to-change không?
22. Type có static generics/enclosing generic parameter dependencies không?
23. API đã phân biệt nested interface/enum/record với member inner chưa?
24. Thay nesting có làm đổi source/binary name được công bố không?
25. Java modules/packages có export đúng các public types dự định không?
26. Reflection/serialization/frameworks có dùng class name cụ thể không?
27. File organization có giúp IDE/search/find-usages dễ hiểu không?
28. Một implementation riêng có cần unit tests độc lập hay test qua owner đủ?
29. Có dependency được ẩn quá mức khi dùng private access giữa nested classes không?
30. Có đang suy đoán hiệu năng từ `static` mà không đo không?
31. Với concurrent behavior, đã tách thread safety khỏi lựa chọn nesting chưa?
32. Có ưu tiên **trách nhiệm và ownership** hơn số lượng file/source lines không?

## Kết luận

**Chọn top-level class** khi type là một khái niệm độc lập, có lifecycle/API riêng, được dùng bởi nhiều thành phần hoặc cần mở rộng ngoài một owner. Top-level có thể `public` hoặc **package-private**, không nhất thiết phải phơi bày ra toàn hệ thống.

**Chọn static nested member class** khi type là chi tiết triển khai hoặc companion type sát một enclosing class nhưng **không cần implicit enclosing instance**. Đây thường là lựa chọn tốt cho `Node`, `Builder`, `Helper`, formatter hoặc implementation nội bộ.

**Chọn non-static member inner class** khi một instance thực sự **thuộc và làm việc với một enclosing object cụ thể**. Đồng thời đánh giá coupling, vòng đời và nguy cơ giữ owner reference lâu ngoài ý muốn.

**Chọn local class** khi cần một named implementation chỉ có ý nghĩa trong một block; **chọn anonymous class** cho implementation inline ngắn khi class semantics cần thiết; cân nhắc **lambda** cho một behavior ngắn của functional interface.

Quyết định tốt nhất không phải là thiết kế có nhiều hay ít class files, mà là thiết kế khiến **tên type, scope, quan hệ owner, access level và API boundary** truyền đạt đúng ý nghĩa của hệ thống. Mỗi class nên được đặt ở nơi phản ánh chính xác **ai sở hữu trách nhiệm của nó** và **ai thật sự cần dùng nó**.
