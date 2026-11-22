# instanceof với kiểu interface trong Java (Java 17+)

## 1. Ý nghĩa: kiểm tra một đối tượng có thực thi hợp đồng interface hay không

Trong Java, `interface` mô tả một **hợp đồng hành vi**. Nhiều lớp khác nhau có thể cùng `implements` một interface dù không cùng lớp cha trực tiếp. Toán tử `instanceof` cho phép hỏi tại **thời điểm chạy**: đối tượng được tham chiếu có thuộc một kiểu thực thi interface đó hay không?

```java
interface Printable {
    String render();
}

record Invoice(String id) implements Printable {
    @Override
    public String render() {
        return "Invoice " + id;
    }
}
```

Nếu `Object value = new Invoice("A1");`, thì `value instanceof Printable` trả về `true`. Một biến có **kiểu khai báo** `Object` vẫn có thể tham chiếu đến đối tượng `Invoice` thực tế. `instanceof` kiểm tra kiểu runtime của đối tượng, nên kết quả không phụ thuộc việc biến ban đầu được khai báo là `Object`, `Serializable`, một interface khác hay một lớp cha phù hợp.

Đây là **kiểm tra quan hệ kiểu**, không phải kiểm tra tên phương thức bằng chuỗi. Một class tự khai báo phương thức `render()` trùng tên nhưng **không** `implements Printable` sẽ không tự trở thành `Printable`.

## 2. Hai cách viết: `instanceof` boolean và type pattern

### Cách truyền thống: kiểm tra rồi ép kiểu

```java
static void printOld(Object value) {
    if (value instanceof Printable) {
        Printable printable = (Printable) value;
        System.out.println(printable.render());
    }
}
```

Biểu thức `value instanceof Printable` trả về `boolean`. Nếu đúng, ép kiểu `(Printable) value` trong nhánh `if` là hợp lệ với cùng đối tượng đã được kiểm tra. Cách viết này vẫn dùng được.

### Pattern matching: kiểm tra và khai báo biến cùng lúc

Từ Java 16 (JEP 394, ổn định), có thể viết **type pattern**:

```java
static void printNew(Object value) {
    if (value instanceof Printable printable) {
        System.out.println(printable.render());
    }
}
```

Cấu trúc `expression instanceof InterfaceName variable` có ba ý:

1. Kiểm tra đối tượng được đánh giá có khớp interface `InterfaceName` không.
2. Nếu khớp, tạo biến pattern `variable` với **kiểu tĩnh** là interface đó.
3. Cho phép sử dụng biến trong phạm vi mà compiler biết phép kiểm tra đã thành công.

Ở đây `printable` có kiểu `Printable`, vì vậy gọi được `render()` và các phương thức khác khai báo trên `Printable`. Không cần ép kiểu thủ công nữa.

**Lưu ý:** `Printable printable` ở đây là *type pattern*, không phải cú pháp khai báo tham số phương thức. `instanceof` chỉ kiểm tra và gán biến khi đối tượng khớp, không tạo mới đối tượng hay sao chép dữ liệu.

## 3. Chương trình chạy được: một interface, nhiều kiểu triển khai

Lưu toàn bộ mã sau vào tệp **InterfaceInstanceofDemo.java**. Ví dụ dùng cú pháp ổn định trong Java 17:

```java
public class InterfaceInstanceofDemo {

    interface Printable {
        String render();
    }

    interface Tagged {
        String tag();
    }

    record Invoice(String id, int total)
            implements Printable, Tagged {
        @Override
        public String render() {
            return "Invoice " + id + ": " + total;
        }

        @Override
        public String tag() {
            return "BILL";
        }
    }

    static final class Note implements Printable {
        private final String text;

        Note(String text) {
            this.text = text;
        }

        @Override
        public String render() {
            return "Note " + text;
        }
    }

    static void inspect(Object value) {
        if (value instanceof Printable printable) {
            System.out.println("Printable: " + printable.render());

            if (printable instanceof Tagged tagged) {
                System.out.println("Tag: " + tagged.tag());
            }
        } else {
            System.out.println("Not printable");
        }
    }

    public static void main(String[] args) {
        inspect(new Invoice("A1", 250));
        inspect(new Note("Hello"));
        inspect("plain text");
        inspect(null);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac InterfaceInstanceofDemo.java
java InterfaceInstanceofDemo
```

**Kết quả chính xác:**

```text
Printable: Invoice A1: 250
Tag: BILL
Printable: Note Hello
Not printable
Not printable
```

Giải thích theo từng đối tượng:

- `Invoice` vừa `implements Printable` vừa `implements Tagged`, nên khớp **cả hai** pattern. Dòng `render()` và `tag()` đều được in.
- `Note` chỉ `implements Printable`, nên khớp pattern đầu, còn `printable instanceof Tagged tagged` không khớp.
- `String` có thể in ra bằng `toString()` nhưng không vì thế mà `implements Printable`; nhánh `else` chạy.
- `null` không khớp với bất kỳ type pattern `instanceof` nào, nên cũng vào nhánh `else`.

Đặc biệt, biến `printable` bên trong `if` có kiểu khai báo `Printable` nhưng vẫn có thể tiếp tục kiểm tra `instanceof Tagged`: đối tượng runtime có thể thực thi **nhiều interface độc lập**. Không cần biết class cụ thể là `Invoice`.

## 4. Cơ chế khớp interface theo hệ thống kiểu

Giả sử:

```java
interface HasId {
    String id();
}

interface Auditable extends HasId {
    void audit();
}

class AuditEntry implements Auditable {
    @Override
    public String id() {
        return "E-1";
    }

    @Override
    public void audit() {
        System.out.println("audited");
    }
}
```

Đây là ví dụ minh họa độc lập với chương trình ở mục 3. Với `Object obj = new AuditEntry();`:

- `obj instanceof Auditable` là `true` vì class `AuditEntry` trực tiếp thực thi `Auditable`.
- `obj instanceof HasId` cũng là `true` vì `Auditable extends HasId`: đối tượng thực thi cả các interface được kế thừa.
- `obj instanceof Runnable` là `false` vì `AuditEntry` không thực thi `Runnable`.

Tương tự, nếu một lớp cha đã `implements HasId` thì instance của lớp con kế thừa hành vi kiểu đó cũng khớp `HasId`. Khi kiểm tra một interface, Java xét **kiểu thực tế và quan hệ extends/implements**, không xét chỉ tên class ghi cạnh biến.

Một đối tượng có thể khớp nhiều interface cùng lúc; các lần kiểm tra không loại trừ nhau. Vì thế `if (x instanceof A) { ... }` và `if (x instanceof B) { ... }` có thể cùng chạy, trong khi `if ... else if ...` chỉ chạy nhánh đầu tiên khớp.

## 5. Phạm vi biến pattern (flow scoping)

Compiler chỉ cho dùng biến pattern tại những điểm mà điều kiện đúng đã được bảo đảm.

### Trong nhánh `if` và toán tử `&&`

```java
static void printIfNonEmpty(Object input) {
    if (input instanceof Printable p
            && !p.render().isEmpty()) {
        System.out.println(p.render());
    }
}
```

Toán tử `&&` đánh giá vế sau chỉ khi vế trước đúng, nên `p` sẵn sàng ở vế phải và trong thân `if`. Ví dụ giả định `render()` trả về chuỗi khác `null`; nếu interface cho phép trả về `null`, cần kiểm tra riêng trước khi gọi `isEmpty()`.

Ngược lại, không thể sử dụng `p` như thể nó luôn được gán trong vế phải của `||`:

```java
// Sai: p chưa được bảo đảm tồn tại khi vế phải cần đánh giá.
// if (input instanceof Printable p || p.render().isEmpty()) { }
```

### Phủ định điều kiện và nhánh thoát sớm

```java
static String renderOrFallback(Object input) {
    if (!(input instanceof Printable p)) {
        return "unsupported";
    }
    return p.render();
}
```

Sau câu lệnh `if`, chương trình chỉ đi tiếp khi pattern đã khớp, bởi nhánh phủ định đã `return`. Vì vậy `p` có thể dùng ở dòng `return p.render()`. Với `new Invoice("A1", 250)`, kết quả trả về là `"Invoice A1: 250"`; với `null`, trả về `"unsupported"`.

Một biến khai báo trong type pattern không có phạm vi tự do trên toàn phương thức. Tránh dùng lại tên trong cùng phạm vi một cách khiến biến trùng khai báo và đọc lỗi biên dịch để xác định chính xác nơi biến có hiệu lực.

## 6. Kiểu interface cho phép gọi những phương thức nào?

Khi dùng `input instanceof Printable p`, biến `p` có **kiểu tĩnh Printable**. Compiler chỉ cho gọi phương thức đã được interface `Printable` công bố (cùng các phương thức `Object` thích hợp), dù class runtime có thêm các phương thức riêng.

Ví dụ, `Invoice` trong chương trình chính có accessor `id()`, `total()` của record; nhưng `Printable` không khai báo chúng:

```java
if (value instanceof Printable p) {
    p.render();      // Hợp lệ: Printable khai báo render().
    // p.total();    // Lỗi biên dịch: Printable không khai báo total().
}
```

Nếu thực sự cần chức năng của interface khác, hãy match interface đó:

```java
if (value instanceof Printable p
        && value instanceof Tagged t) {
    System.out.println(p.render() + " / " + t.tag());
}
```

Ví dụ này biểu đạt rõ đối tượng cần thỏa **cả hai hợp đồng**. Nếu cần một class cụ thể thì có thể match `Invoice invoice`, nhưng cách đó khiến code phụ thuộc trực tiếp vào một implementation. Ưu tiên match interface khi nghiệp vụ quan tâm đến **khả năng thực hiện hành vi**, thay vì danh tính class.

`instanceof` không gọi `render()` chỉ để kiểm tra có khớp hay không. Phương thức chỉ chạy khi code của bạn thực sự gọi nó sau phép kiểm tra.

## 7. Giá trị `null` và kiểu tĩnh đã biết

### Khi giá trị là `null`

```java
Object candidate = null;
System.out.println(candidate instanceof Printable); // false
```

Cả biểu thức boolean lẫn type pattern đều không match `null`. Không có `NullPointerException` chỉ vì phép kiểm tra `instanceof`; lỗi chỉ có thể xảy ra nếu bạn truy cập đối tượng hoặc gọi phương thức không an toàn ở nơi khác.

### Khi biến vốn đã có kiểu interface

```java
Printable p = new Invoice("A2", 100);
boolean present = p instanceof Printable; // true nếu p != null
```

Nếu mục đích chỉ là kiểm tra có đối tượng hay không, `p != null` thường rõ nghĩa hơn. Khi biến đã khai báo `Printable`, việc tiếp tục kiểm tra cùng interface không thêm thông tin về khả năng gọi `render()`.

Có một **khác biệt theo phiên bản Java**: Java 17 không cho dùng type pattern vô điều kiện `p instanceof Printable matched` nếu kiểu tĩnh `p` đã là subtype của `Printable`; Java 21+ cho phép một số unconditional patterns trong `instanceof`. Để ví dụ tương thích Java 17, hãy dùng `p != null` trong trường hợp này. Tuy nhiên `p instanceof Tagged t` vẫn có ích vì `Printable` và `Tagged` là hai interface độc lập, đối tượng runtime có thể thực thi cả hai.

### Kiểm tra có thể bị từ chối ngay khi biên dịch

Không phải mọi cặp kiểu đều có thể dùng `instanceof`. Nếu compiler chứng minh giá trị không thể thuộc kiểu cần kiểm tra theo quan hệ kiểu Java (chẳng hạn biến có kiểu class `final` không thực thi interface cần match), biểu thức có thể bị lỗi kiểu không tương thích tại thời điểm biên dịch. Nếu đối tượng đầu vào có nhiều khả năng kiểu, dùng tham chiếu kiểu cha/interface phù hợp, ví dụ `Object`, để kiểm tra runtime khi cần thiết.

## 8. Interface generic: có thể kiểm tra `List<?>`, không kiểm tra `List<String>`

Do **type erasure**, Java runtime không giữ đầy đủ đối số kiểu của phần lớn generic instance. Vì vậy không thể dùng `instanceof` để phân biệt `List<String>` với `List<Integer>` bằng cú pháp như sau:

```java
// Sai: tham số kiểu String không được kiểm chứng ở runtime.
// if (value instanceof java.util.List<String> names) { }
```

Thay vào đó dùng dạng reifiable với wildcard:

```java
import java.util.List;

static void inspectList(Object value) {
    if (value instanceof List<?> items) {
        System.out.println("size=" + items.size());

        if (!items.isEmpty()
                && items.get(0) instanceof String first) {
            System.out.println("first=" + first);
        }
    }
}
```

Với `inspectList(List.of("A", "B"))`, kết quả là:

```text
size=2
first=A
```

`List<?>` xác nhận đối tượng thực thi interface `List` nhưng **không khẳng định** phần tử có kiểu `String`. Vì thế `items.get(0)` trả về giá trị có kiểu tĩnh `Object`; kiểm tra tiếp bằng `instanceof String first` nếu logic yêu cầu phần tử là chuỗi. Kiểm tra một phần tử không chứng minh mọi phần tử đều là `String`; muốn xác nhận toàn bộ danh sách thì phải kiểm tra từng phần tử.

Đối với generic interface do bạn định nghĩa, áp dụng cùng nguyên tắc: các đối số kiểu không reifiable không thể được kiểm tra tùy ý bằng `instanceof`.

## 9. Các nhầm lẫn thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| `instanceof Printable` chỉ khớp class có tên `Printable`. | `Printable` là interface; **mọi class thực thi hợp đồng** (kể cả thông qua kế thừa) đều có thể khớp. |
| Chỉ cần một class có phương thức `render()` là khớp. | Java dùng quan hệ kiểu tường minh `implements`/`extends`; trùng tên phương thức chưa đủ. |
| Kiểu khai báo là `Object` nên không thể match interface. | `instanceof` xét kiểu runtime; `Object` có thể chứa tham chiếu tới instance thực thi interface. |
| `instanceof` gây lỗi khi biến `null`. | `null instanceof Interface` cho kết quả `false`. |
| Match `Printable p` thì gọi được mọi phương thức của class runtime. | `p` có kiểu tĩnh `Printable`; các phương thức ngoài interface cần kiểu hoặc kiểm tra bổ sung. |
| Chỉ một interface được khớp mỗi lần. | Một đối tượng có thể thực thi nhiều interface độc lập; các pattern có thể cùng khớp. |
| Match `List<?>` chứng minh tất cả phần tử là chuỗi. | Kiểm tra được interface `List`, không kiểm chứng đối số generic hay kiểu của mọi phần tử. |
| Biến pattern dùng được ở mọi vị trí sau `if`. | Phạm vi phụ thuộc đường điều khiển và việc match có được bảo đảm hay không. |

Một lỗi thiết kế khác là viết hàng loạt `if (x instanceof ConcreteA) ... else if (x instanceof ConcreteB) ...` trong khi các class cùng thực thi một interface đã cung cấp đúng phương thức cần gọi. Khi đó có thể chỉ cần làm việc với interface và tính đa hình:

```java
static void print(Printable printable) {
    if (printable != null) {
        System.out.println(printable.render());
    }
}
```

Dùng `instanceof` khi **đối tượng đến từ một kiểu rộng hơn** hoặc khi một hành vi phụ thuộc vào việc đối tượng có hỗ trợ **thêm một interface** hay không. Nếu caller đã đảm bảo `Printable`, gọi phương thức qua interface trực tiếp thường đơn giản hơn.

## 10. Bài tập và lời giải

### Bài 1 — Hai lớp triển khai chung một hợp đồng

Cho:

```java
interface Payable {
    int amount();
}

record Order(int amount) implements Payable {}
record Salary(int amount) implements Payable {}
```

Hãy viết phương thức nhận `Object`, trả về `amount()` nếu đối tượng thực thi `Payable`, ngược lại trả về `0`.

Lời giải (đoạn này đặt cùng các khai báo trên):

```java
static int amountOrZero(Object value) {
    if (value instanceof Payable payment) {
        return payment.amount();
    }
    return 0;
}
```

Kết quả: `amountOrZero(new Order(120)) == 120`, `amountOrZero(new Salary(500)) == 500`, và `amountOrZero(null) == 0`. Không cần phân biệt `Order` với `Salary` vì cả hai đã cung cấp `amount()`.

### Bài 2 — Đối tượng thực thi nhiều interface

Cho `Object value = new Invoice("Z9", 80);` của chương trình đầy đủ ở mục 3. Các biểu thức sau đúng hay sai?

- `value instanceof Printable`: **true**, vì `Invoice implements Printable`.
- `value instanceof Tagged`: **true**, vì `Invoice implements Tagged`.
- `value instanceof Runnable`: **false**, vì `Invoice` không thực thi `Runnable`.
- Sau `if (value instanceof Printable p)`, việc gọi `p.tag()` trực tiếp có hợp lệ không? **Không**, vì `tag()` nằm trên `Tagged`, không nằm trên `Printable`; cần kiểm tra hoặc dùng tham chiếu có kiểu `Tagged`.

### Bài 3 — Kiểm tra từng phần tử generic

Cho `Object value = java.util.List.of("Java", 21);`. Viết kiểm tra `value instanceof java.util.List<?> items` rồi phân loại phần tử đầu tiên. Đáp án minh họa:

```java
if (value instanceof java.util.List<?> items
        && !items.isEmpty()) {
    Object first = items.get(0);
    if (first instanceof String text) {
        System.out.println(text.toUpperCase());
    } else {
        System.out.println("first item is not a String");
    }
}
```

Ở đây in `JAVA`, vì phần tử đầu tiên là chuỗi `"Java"`. Dù danh sách có phần tử `Integer` ở vị trí khác, việc dùng `List<?>` là hợp lệ; không có giả định sai rằng tất cả phần tử cùng kiểu.

## 11. Ghi nhớ khi áp dụng

- **`x instanceof MyInterface`**: trả về `true` khi `x != null` và kiểu runtime của đối tượng thực thi `MyInterface` trực tiếp hoặc gián tiếp.
- **`x instanceof MyInterface m`**: vừa kiểm tra vừa mở biến kiểu `MyInterface` tại những vị trí được bảo đảm match; đây là type pattern ổn định từ Java 16 và dùng tốt trong Java 17+.
- Một đối tượng có thể khớp **nhiều interface**; type pattern không giúp truy cập phương thức nằm ngoài interface mà nó khai báo.
- `instanceof List<?>` chỉ chứng minh là `List`, không chứng minh kiểu đối số generic. `null` không bao giờ match.
- Khi phương thức đã nhận đúng kiểu interface, hãy ưu tiên gọi hành vi qua interface; sử dụng `instanceof` khi phải thu hẹp kiểu từ `Object` hoặc kiểm tra thêm khả năng tùy chọn.

Tài liệu tham khảo chính thức:
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java Language Specification — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
