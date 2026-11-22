# Raw type ở lớp bên trong và giới hạn kiểu tham số hóa một phần trong Java Generics

## 1. Vấn đề: vì sao không thể tùy ý kết hợp raw và generic?

Một lớp generic có thể khai báo lớp thành viên bên trong:

~~~java
class Outer<T> {
    class Inner<U> {
    }
}
~~~

Ở đây có **hai tham số kiểu thuộc hai khai báo khác nhau**:

- `T` được khai báo bởi `Outer<T>`. Mọi đối tượng `Inner<U>` không static được gắn với một đối tượng `Outer<T>`, nên có thể sử dụng các thành viên mang kiểu T của đối tượng ngoài.
- `U` được khai báo bởi `Inner<U>`. Nó điều khiển những thành viên dùng U của lớp bên trong.

Các cách biểu diễn sau rất quan trọng:

~~~java
Outer<String>.Inner<Integer> complete; // Hợp lệ về mặt kiểu.
Outer rawOuter;                         // Raw Outer.
Outer.Inner rawInner;                   // Raw member type.
~~~

Ngược lại, với lớp `Inner<U>` được khai báo trực tiếp bên trong `Outer<T>` như trên, Java **không cho phép tham số hóa chỉ một phần** bằng cách kết hợp một outer raw với một inner có type argument, hoặc outer parameterized với một inner raw:

~~~java
// Outer.Inner<Integer> bad1; // Không hợp lệ.
// Outer<String>.Inner bad2;   // Không hợp lệ.
~~~

Hai ví dụ cố ý sai được đặt trong comment, để bạn không vô tình đưa chúng vào chương trình chạy. Lỗi không đơn giản chỉ là “quên dấu <>”. Java có quy tắc về **raw member types** và **các kiểu được khai báo ở những mức lồng nhau**, giúp tránh một kiểu kết hợp nửa có thông tin generic, nửa đã đánh mất ngữ cảnh generic bao quanh.

Bài học này tập trung vào **member classes**, đặc biệt là **non-static inner classes** của generic outer class; sau đó phân biệt với **static nested classes**, lớp member không tự khai báo U, diamond, wildcard và những tình huống gây cảnh báo unchecked.

## 2. Khái niệm nền tảng: member, inner, nested và enclosing type

Với Java:

~~~java
class Outer<T> {
    class Inner<U> { }       // Non-static member class (inner class).
    class PlainInner { }    // Inner class không có type parameter riêng.
    static class Nested<V> { } // Static nested class.
}
~~~

Có ba khái niệm cần tách biệt:

**Member class** là một class được khai báo là thành viên của class/interface khác. Nó có thể static hoặc non-static.

**Inner class** trong ví dụ là class thành viên **không static**, gắn với một đối tượng bên ngoài. Một đối tượng `Outer<String>.Inner<Integer>` liên kết với một đối tượng `Outer<String>` cụ thể; phương thức bên trong có thể đọc trường T của outer và trường U của inner.

**Static nested class** là class thành viên static. Nó **không có đối tượng outer ngầm định** và không sử dụng trực tiếp tham số kiểu T của `Outer<T>`. Nếu static nested class muốn generic, nó phải khai báo type parameter riêng, như `V`.

Không nên gọi tất cả nested classes là inner classes. Khác biệt static/non-static quyết định cách truy cập tham số kiểu của outer và quy tắc tạo đối tượng.

## 3. Quy tắc raw type của member class

Một *raw type* là cách dùng tên của generic class/interface mà không cung cấp các type arguments (theo ngữ cảnh mà Java cho phép). Với `Outer<T>`, tên `Outer` đứng một mình ở vị trí kiểu là raw.

Khi một non-static member class được **khai báo trực tiếp** trong raw outer class, kiểu thành viên của raw outer cũng bị coi là raw. Điều này vẫn quan trọng nếu chính member class không tự khai báo type parameter.

~~~java
class Outer<T> {
    class Inner<U> {
        T ownerValue;
        U innerValue;
    }

    class PlainInner {
        T ownerValue;
    }
}
~~~

Các trường hợp:

| Cú pháp tên kiểu | Hợp lệ? | Ý nghĩa |
| --- | --- | --- |
| `Outer<String>.Inner<Integer>` | Có | Outer có T = String, Inner có U = Integer. |
| `Outer.Inner` | Có | Raw Outer và raw member Inner; thông tin generic liên quan bị xóa. |
| `Outer<String>.Inner<?>` | Có | Outer biết String; phần tử U chưa biết, được biểu diễn bằng wildcard. |
| `Outer<?>.Inner<?>` | Có | Cả hai mức đều có tham số hóa bằng wildcard, không phải raw. |
| `Outer.Inner<Integer>` | Không | Không thể gắn U = Integer lên Inner của raw Outer. |
| `Outer<String>.Inner` | Không | Không thể giữ Outer<String> nhưng dùng raw Inner<U> kiểu này. |
| `Outer<String>.PlainInner` | Có | PlainInner không có U riêng, nhưng biết T của outer. |
| `Outer.PlainInner` | Có | Member type của raw Outer; thành viên dùng T bị nhìn qua erasure. |

Bảng này dựa trên cấu trúc **member class được khai báo trực tiếp** trong Outer ở ví dụ. Với member type được kế thừa từ một superclass hay superinterface, cần xem chính xác nơi member được khai báo; không nên áp dụng máy móc quy tắc cho mọi tên có dấu chấm.

Cần hiểu “không tham số hóa một phần” trong phạm vi cụ thể: quy tắc này **không cấm mọi kiểu thiếu dấu ngoặc nhọn <> ở cấp trong**. Ví dụ `Outer<String>.PlainInner` hoàn toàn hợp lệ vì `PlainInner` không có type parameter U nào cần cung cấp. Ngược lại `Inner<U>` là generic member class nên cách bỏ U sẽ mang ý nghĩa raw trong tổ hợp không hợp lệ.

## 4. Chương trình chạy hoàn chỉnh trên Java 17+

Lưu chương trình sau vào tệp **RawInnerDemo.java**:

~~~java
public class RawInnerDemo {
    static class Outer<T> {
        private final T label;

        Outer(T label) {
            this.label = label;
        }

        class Inner<U> {
            private final U value;

            Inner(U value) {
                this.value = value;
            }

            T ownerLabel() {
                return label;
            }

            U payload() {
                return value;
            }
        }

        // Không generic ở cấp PlainMember, nhưng dùng T của Outer.
        class PlainMember {
            T ownerLabel() {
                return label;
            }
        }

        // Không sử dụng trực tiếp T của Outer.
        static class StaticNested<V> {
            private final V value;

            StaticNested(V value) {
                this.value = value;
            }

            V get() {
                return value;
            }
        }
    }

    public static void main(String[] args) {
        Outer<String> typed = new Outer<>("owner");

        // Cả outer và inner được tham số hóa đầy đủ.
        Outer<String>.Inner<Integer> inner = typed.new Inner<>(7);
        System.out.println(
                "typed=" + inner.ownerLabel() + "/" + inner.payload()
        );

        // PlainMember không có U riêng, nhưng biết outer T = String.
        Outer<String>.PlainMember plain = typed.new PlainMember();
        System.out.println("plain=" + plain.ownerLabel());

        // Wildcard vẫn là tham số hóa, không phải raw.
        Outer<?> wildcardOuter = typed;
        Outer<?>.Inner<?> unknown = wildcardOuter.new Inner<>("text");
        Object read = unknown.payload();
        System.out.println("wildcard=" + read);

        // Raw Outer khiến member Inner được dùng ở dạng raw.
        Outer rawOuter = typed;
        Outer.Inner rawInner = rawOuter.new Inner(42);
        Object rawOwner = rawInner.ownerLabel();
        Object rawPayload = rawInner.payload();
        System.out.println("raw=" + rawOwner + "/" + rawPayload);

        // Member không generic cũng bị ảnh hưởng bởi raw outer.
        Outer.PlainMember rawPlain = rawOuter.new PlainMember();
        Object rawPlainOwner = rawPlain.ownerLabel();
        System.out.println("rawPlain=" + rawPlainOwner);

        // Static nested class có tham số kiểu độc lập với T.
        Outer.StaticNested<String> nested =
                new Outer.StaticNested<>("static");
        System.out.println("nested=" + nested.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -Xlint:rawtypes -Xlint:unchecked RawInnerDemo.java
java RawInnerDemo
~~~

`-Xlint:rawtypes` giúp báo nơi dùng raw class/member type; `-Xlint:unchecked` báo các thao tác raw có kiểm tra kiểu không đầy đủ, chẳng hạn gọi constructor `Inner(U)` qua raw member type. Cảnh báo của javac không nằm trong stdout của chương trình.

Stdout khi chương trình chạy:

~~~text
typed=owner/7
plain=owner
wildcard=text
raw=owner/42
rawPlain=owner
nested=static
~~~

### Vì sao mỗi dòng có kiểu như vậy?

- `typed` là `Outer<String>` nên `inner.ownerLabel()` được trình biên dịch nhìn như trả `String`. `inner` là `Inner<Integer>` nên `payload()` trả `Integer`.
- `PlainMember` không có tham số riêng; nó vẫn nhìn thấy T từ `Outer<String>` nên `plain.ownerLabel()` trả `String`.
- Với `Outer<?>.Inner<?>`, kiểu T và U chưa xác định; có thể đọc kết quả dưới dạng `Object`, nhưng vẫn giữ cơ chế kiểm tra generic theo wildcard.
- `rawOuter` có kiểu raw `Outer` dù đối tượng runtime vẫn chính là đối tượng đã tạo cho biến `typed`. Thành viên `Inner` qua raw Outer cũng raw. Do đó cả `ownerLabel()` và `payload()` được nhìn theo kiểu đã xóa, ở ví dụ này là `Object`.
- `Outer.PlainMember` dùng raw outer, nên getter phụ thuộc T cũng được nhìn sau erasure là `Object`.
- `StaticNested<String>` là một generic type hoàn chỉnh của **static member class**; không có đối tượng outer, và type argument String độc lập với T.

Lưu ý: việc chương trình biên dịch và chạy với raw types **không chứng minh raw an toàn**. Đây là ví dụ chủ ý để làm rõ vị trí thông tin kiểu đã mất.

## 5. Tại sao Outer.Inner<Integer> bị từ chối?

Xét lại:

~~~java
class Outer<T> {
    class Inner<U> {
        T ownerValue;
        U value;
    }
}
~~~

Dòng sau là **cú pháp kiểu không hợp lệ**:

~~~java
// Outer.Inner<Integer> invalid;
~~~

`Outer` là raw. Theo quy tắc raw member type, `Inner` đi theo raw Outer trong trường hợp này; Java không cho phép “khôi phục lại” chỉ tham số U thành Integer trong khi vẫn bỏ tham số T của outer.

Khi thử trong Java 17+, javac có thể báo:

~~~text
improperly formed type, type arguments given on a raw type
~~~

Cách sửa là tham số hóa outer và inner đầy đủ:

~~~java
Outer<String>.Inner<Integer> valid;
~~~

Nếu chưa biết kiểu T của outer, wildcard cũng có thể giữ cấu trúc tham số hóa:

~~~java
Outer<?>.Inner<Integer> validWithUnknownOuter;
~~~

Dòng khai báo phía trên hợp lệ về mặt kiểu; cần một đối tượng `Outer<?>` tương ứng và cú pháp `outerInstance.new Inner<>(...)` để khởi tạo vì Inner là non-static. Không thể tạo inner tùy ý mà bỏ đối tượng outer liên kết.

### Trường hợp chỉ biết U nhưng không biết T

Đừng chọn raw Outer để lách lỗi. Có thể dùng:

~~~java
Outer<?> anyOuter = new Outer<String>("owner");
Outer<?>.Inner<Integer> value = anyOuter.new Inner<>(99);
Object ownerPart = value.ownerLabel();
Integer innerPart = value.payload();
~~~

Phần T chưa biết được biểu diễn bằng wildcard; U vẫn rõ ràng là Integer. `ownerPart` chỉ đọc được an toàn như Object, còn `innerPart` là Integer. Đây là sự khác biệt lớn giữa **không biết type argument** và **bỏ hẳn hệ thống tham số kiểu bằng raw**.

## 6. Tại sao Outer<String>.Inner cũng bị từ chối?

Dòng sau cũng không hợp lệ với generic Inner<U>:

~~~java
// Outer<String>.Inner invalid;
~~~

Một outer đã tham số hóa không được kết hợp với inner raw ở vị trí kiểu này. Javac thường chẩn đoán:

~~~text
improperly formed type, some parameters are missing
~~~

Lập trình viên có thể muốn biểu diễn “outer chắc chắn chứa String, nhưng tôi chưa biết kiểu U”. Cú pháp thích hợp là **wildcard**:

~~~java
Outer<String>.Inner<?> validUnknownInner;
~~~

Nếu đã biết U là Integer:

~~~java
Outer<String>.Inner<Integer> validKnownInner;
~~~

Nếu cần xử lý nhiều kiểu U khác nhau, có thể khai báo phương thức nhận `Outer<String>.Inner<?>` và đọc `payload()` như Object, đồng thời giữ quan hệ String của owner.

**Không dùng raw type chỉ để thể hiện “không biết”.** `?` chính là cách diễn đạt sự không biết mà vẫn chịu các quy tắc kiểm tra của generics.

## 7. Vì sao lớp member không generic vẫn có thể bị ảnh hưởng?

Một ví dụ tinh tế:

~~~java
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    class PlainInner {
        T readOuter() {
            return value;
        }
    }
}
~~~

Bản thân `PlainInner` không có tham số kiểu riêng, nhưng nó **dùng T của Outer**.

~~~java
Outer<String> typed = new Outer<>("hello");
Outer<String>.PlainInner a = typed.new PlainInner();
String x = a.readOuter();
~~~

Cách viết này hợp lệ và giữ được String nhờ qualifier `Outer<String>`.

Khi outer bị dùng raw:

~~~java
Outer raw = typed;
Outer.PlainInner b = raw.new PlainInner();
Object y = b.readOuter();
~~~

Giá trị runtime có thể vẫn là String, nhưng kiểu compile-time của kết quả `readOuter()` qua raw member là Object do mất quan hệ generic với outer.

Điều này cho thấy raw member class không chỉ xuất hiện khi chính inner khai báo `<U>`. Quy tắc liên quan đến **member type của raw enclosing class**, không chỉ đến số type parameters nằm ngay sau tên inner.

## 8. Static nested class là trường hợp khác

Với:

~~~java
class Outer<T> {
    static class Nested<V> {
        V value;

        Nested(V value) {
            this.value = value;
        }
    }
}
~~~

`Nested<V>` là static. Nó không có enclosing instance của `Outer<T>` và không thể trực tiếp dùng biến kiểu T của Outer làm một thành viên instance phụ thuộc T, vì static member không gắn với tham số hóa của outer.

Cách tham số hóa đúng:

~~~java
Outer.Nested<String> a = new Outer.Nested<>("text");
Outer.Nested<Integer> b = new Outer.Nested<>(123);
~~~

`Outer` ở đây là **tên đủ điều kiện của static nested class**, không biểu thị rằng outer instance raw được dùng để tạo inner instance. `Nested<String>` vẫn là parameterized type đầy đủ của chính nested class.

Cú pháp sau bị từ chối:

~~~java
// Outer<String>.Nested<Integer> bad; // Không hợp lệ.
~~~

javac có thể báo:

~~~text
cannot select a static class from a parameterized type
~~~

Vì static Nested không cần outer instance và không phụ thuộc vào T, bạn không được gắn `Outer<String>` vào tên của nó theo cách trên.

Một non-generic static nested class như `Outer.Helper` là kiểu không generic nếu chính Helper không khai báo type parameter. Không nên áp quy tắc raw non-static member lên static nested class chỉ vì nó xuất hiện bên trong một class generic.

## 9. Raw outer và lời gọi constructor

Khi có biến outer đã tham số hóa:

~~~java
Outer<String> outer = new Outer<>("label");
Outer<String>.Inner<Integer> inner = outer.new Inner<>(42);
~~~

Cú pháp `outer.new Inner<>(42)` thực hiện hai việc:

1. Liên kết đối tượng Inner vừa tạo với **đối tượng outer** cụ thể.
2. Suy luận type argument U nhờ constructor hoặc ngữ cảnh đích; ở đây U là Integer.

Diamond `<>` không tạo raw type. Nó biểu thị **suy luận type arguments**.

Ngược lại:

~~~java
Outer raw = new Outer("label");
Outer.Inner inner = raw.new Inner(42);
~~~

Ví dụ này dùng raw Outer và raw Inner; javac có thể báo rawtypes/unchecked. Phần `(42)` không khiến compiler tự nâng `Inner` thành `Inner<Integer>`, vì nó được gọi thông qua raw enclosing type.

Chính sự khác biệt giữa **raw construction** và **diamond construction** dễ khiến người đọc nhầm rằng compiler lúc nào cũng tự suy luận được U từ đối số constructor. Khi enclosing type đã raw, phải tuân thủ giới hạn raw member type.

## 10. Đọc đúng lỗi và các lựa chọn sửa

| Mục tiêu | Viết dễ sai | Cách biểu diễn đúng |
| --- | --- | --- |
| Outer String, Inner Integer | `Outer<String>.Inner<Integer>` | Giữ nguyên, đã hợp lệ. |
| Outer chưa biết T, Inner Integer | `Outer.Inner<Integer>` | `Outer<?>.Inner<Integer>` |
| Outer String, Inner chưa biết U | `Outer<String>.Inner` | `Outer<String>.Inner<?>` |
| Cả T và U đều chưa biết | `Outer.Inner` nếu chỉ cần quan sát dữ liệu | Ưu tiên `Outer<?>.Inner<?>` |
| Member không có U riêng | Nhầm `Outer<String>.PlainMember` là thiếu type arguments | `Outer<String>.PlainMember` hợp lệ. |
| Static nested generic | `Outer<String>.Nested<Integer>` | `Outer.Nested<Integer>` |

Dòng “cả T và U chưa biết” đáng chú ý: raw `Outer.Inner` vẫn là tên kiểu có thể biên dịch trong một số đoạn mã, nhưng vì thiếu thông tin generic, nó không phải lựa chọn an toàn cho API mới. `Outer<?>.Inner<?>` giúp thể hiện rõ sự không biết của từng lớp tham số và giữ lại các ràng buộc.

### Vì sao không cast raw Inner sang kiểu tham số hóa rồi dùng?

Ép kiểu unchecked không thể phục hồi thông tin kiểu bị bỏ đi một cách đáng tin:

~~~java
// Giả sử rawInner là Outer.Inner:
@SuppressWarnings("unchecked")
Outer<String>.Inner<Integer> guessed =
        (Outer<String>.Inner<Integer>) rawInner;
~~~

Đây là **mảnh mã minh họa** và không độc lập để chạy. Runtime thông thường không thể kiểm tra đầy đủ cả T = String và U = Integer của đối tượng generic. Nếu dữ liệu thực tế không khớp, lỗi có thể xuất hiện ở chỗ đọc một trường hoặc gọi phương thức sau đó.

Hướng ưu tiên: giữ type arguments đúng ngay tại lúc tạo outer/inner; nếu nhận dữ liệu raw từ API cũ, giới hạn nó ở ranh giới tích hợp và xác minh đối tượng/dữ liệu cần sử dụng.

## 11. Type erasure và nguy cơ heap pollution

Raw type không có nghĩa JVM tạo một bản class hoàn toàn khác cho mỗi giá trị type parameter. Đối với generic thông thường, phần lớn tham số kiểu được xóa khi biên dịch.

Ở ví dụ:

~~~java
class Outer<T> {
    class Inner<U> {
        T owner();
        U value();
    }
}
~~~

(Đây là minh họa chữ ký; một chương trình Java độc lập cần cung cấp phần thân phương thức hoặc khai báo phù hợp.)

Khi T và U đều không có bound cụ thể, descriptor trả về sau erasure của các phương thức đó là Object. Nhưng đối với biến có kiểu `Outer<String>.Inner<Integer>`, compiler vẫn dùng generic signature để kiểm tra dữ liệu tương ứng String/Integer và có thể chèn cast khi cần.

Khi dùng raw `Outer.Inner`, compiler không còn thông tin T/U tương ứng. Một chương trình có thể vô tình gắn dữ liệu không phù hợp với khai báo parameterized được giữ ở nơi khác. Rủi ro là **heap pollution** hoặc `ClassCastException` khi dữ liệu được đọc theo kiểu cụ thể.

**Không nhầm nguyên nhân và kết quả:** bản thân việc có raw reference chưa chắc đã gây lỗi ngay. Vấn đề phát sinh khi đường raw cho phép những thao tác mà compiler không thể chứng minh an toàn; lỗi có thể xuất hiện muộn ở call site khác.

## 12. Phân biệt wildcard, raw và Object

Ba cách thể hiện chưa biết thông tin generic khác nhau:

~~~java
Outer.Inner rawMember;                 // Raw member.
Outer<?>.Inner<?> unknownMember;      // Hai wildcard.
Outer<Object>.Inner<Object> objectMember; // T và U đều Object.
~~~

- **Raw**: bỏ type arguments của các generic types liên quan; những thao tác cần kiểm tra T/U có thể sinh cảnh báo unchecked.
- **Wildcard**: biết đối tượng có dạng generic với type arguments nào đó nhưng không biết chính xác; compiler giới hạn thao tác ghi một cách phù hợp.
- **Object arguments**: khẳng định T và U chính là Object; vẫn là parameterized type và vẫn chịu kiểm tra theo Object.

`Outer<String>.Inner<Integer>` không tự chuyển thành `Outer<Object>.Inner<Object>`. Các generic types Java nhìn chung **invariant**. Wildcard có thể nhận những kiểu tham số hóa khác nhau theo quy tắc tương thích; Object không thay thế được wildcard một cách máy móc.

Nếu mục tiêu chỉ đọc giá trị từ một đối tượng inner bất kỳ, một API dùng wildcard thường diễn đạt ý định rõ hơn raw hoặc ép thành Object parameters.

## 13. Các sai lầm thường gặp trong code review

### Sai lầm A: chỉ thêm <Integer> sau một raw inner

~~~java
// Outer.Inner<Integer> fixed; // Vẫn sai.
~~~

Nếu outer thiếu type argument, phải xử lý qualifier của outer trước. Dùng `Outer<?>.Inner<Integer>` khi T chưa biết hoặc `Outer<String>.Inner<Integer>` khi đã biết T = String.

### Sai lầm B: dùng Outer<String>.Inner mà nghĩ “Inner tự hiểu U = Object”

~~~java
// Outer<String>.Inner value; // Không hợp lệ.
~~~

Nếu thật sự muốn U = Object, phải viết `Outer<String>.Inner<Object>`. Nếu chưa biết U, dùng `Outer<String>.Inner<?>`. Không thể bỏ ngoặc kiểu ở mức Inner<U> rồi trông chờ compiler hiểu thành Object.

### Sai lầm C: coi PlainMember là generic vì nó nằm trong Outer<T>

`PlainMember` không khai báo U riêng. `Outer<String>.PlainMember` đúng, trong khi `Outer<String>.PlainMember<Integer>` không đúng nếu PlainMember không khai báo type parameter. Nó vẫn dùng được T của outer thông qua ngữ cảnh.

### Sai lầm D: coi static nested class như inner class

`Outer.Nested<Integer>` không có enclosing instance. `Outer<String>.Nested<Integer>` không phù hợp vì static Nested độc lập với tham số T của Outer.

### Sai lầm E: dùng raw để giải quyết mọi mismatch

Raw member có thể làm một số đoạn code cũ biên dịch kèm warning, nhưng đánh đổi kiểm tra kiểu. Cần xem lại type arguments, mô hình dữ liệu và cách sử dụng wildcard/generic method thay vì lạm dụng raw và suppress toàn bộ cảnh báo.

### Sai lầm F: nhầm quy tắc trực tiếp với mọi trường hợp thừa kế

Các ví dụ trong bài dùng member classes **khai báo trực tiếp** trong Outer. Khi một member type xuất hiện qua lớp con do kế thừa, quy tắc về tên kiểu và raw member phải xét **nơi member được khai báo**. Không suy luận toàn bộ chỉ từ tên lớp đứng bên trái dấu chấm.

## 14. Cách thiết kế API tránh raw inner

Khi thiết kế một API với outer/inner generic, nên:

1. Đặt kiểu rõ ràng ở cả outer và inner khi chúng thật sự mang hai tập dữ liệu có kiểu độc lập.
2. Cung cấp factory hoặc phương thức truy cập phù hợp nếu syntax `outer.new Inner<>(...)` khiến người sử dụng phải lặp lại kiểu quá nhiều, nhưng không giấu mối quan hệ với outer instance.
3. Dùng wildcard ở chữ ký nhận dữ liệu khi không biết T hoặc U nhưng vẫn cần giữ kiểm tra generic.
4. Chọn static nested class khi thành viên không cần truy cập trạng thái hoặc type parameter của outer instance.
5. Giữ raw type ở biên tích hợp legacy code, ưu tiên viết adapter kiểm tra dữ liệu thay vì để raw lan sang nghiệp vụ.
6. Bật `javac -Xlint:rawtypes -Xlint:unchecked` khi rà soát code liên quan generic; xem warning là dấu hiệu cần hiểu và xử lý.
7. Phân biệt tên kiểu hợp lệ với khả năng tạo đối tượng: non-static inner cần đối tượng outer, trong khi static nested class không cần.

Không phải cứ có Outer<T> là tất cả lớp nằm bên trong đều phải có tham số generic. Hãy chọn non-static inner, static nested hay một top-level class dựa trên **quan hệ dữ liệu thật sự cần**, sau đó áp dụng quy tắc type arguments tương ứng.

## 15. Câu hỏi tự kiểm tra

**1.** Với `class Outer<T> { class Inner<U> {} }`, tại sao `Outer.Inner<Integer>` không hợp lệ?

**Đáp án:** Outer đang ở dạng raw; non-static member Inner được dùng trong ngữ cảnh raw và không thể chỉ tham số hóa U trong khi qualifier Outer thiếu T. Dùng `Outer<?>.Inner<Integer>` hoặc một Outer có T cụ thể.

**2.** Vì sao `Outer<String>.Inner` bị từ chối dù đã biết T của outer?

**Đáp án:** Inner vẫn có type parameter U; một raw Inner trong qualifier Outer<String> là tổ hợp tham số hóa một phần không hợp lệ. Dùng `Inner<?>` nếu chưa biết U hoặc `Inner<Integer>` nếu biết.

**3.** `Outer<String>.PlainInner` có hợp lệ nếu PlainInner không khai báo U riêng không?

**Đáp án:** Có. PlainInner không có type parameter riêng để bỏ, và T của Outer đã được xác định là String.

**4.** `Outer.PlainInner` có thể bị ảnh hưởng bởi raw type dù PlainInner không generic không?

**Đáp án:** Có, với một non-static member class khai báo trực tiếp trong raw Outer; những thành viên của PlainInner phụ thuộc T được nhìn qua erasure.

**5.** Vì sao `Outer.Nested<String>` là cú pháp đúng với static generic nested class?

**Đáp án:** Nested là static và không gắn với một đối tượng hoặc T của Outer; type parameter String thuộc chính Nested<V>. Không được chọn static class bằng `Outer<String>.Nested`.

**6.** `Outer<?>.Inner<?>` có phải raw type không?

**Đáp án:** Không. Cả hai vị trí đều có type argument là wildcard; đây là parameterized types, và compiler vẫn kiểm tra các ràng buộc generic phù hợp.

**7.** Diamond trong `typed.new Inner<>(7)` có biến Inner thành raw không?

**Đáp án:** Không. Diamond yêu cầu suy luận U; với outer được tham số hóa đầy đủ và initializer phù hợp, inner có type argument đúng.

**8.** Nếu một lời gọi bị javac cảnh báo unchecked khi dùng raw Outer.Inner, điều đó có nghĩa chương trình chắc chắn ném exception không?

**Đáp án:** Không. Warning có nghĩa compiler không chứng minh đầy đủ an toàn kiểu; chương trình có thể chạy, nhưng nguy cơ lỗi hoặc heap pollution tăng lên khi dữ liệu không đúng kiểu thực sự được đưa vào và sử dụng.

## 16. Ghi nhớ

Trong cây generic có non-static member class, **tên outer và inner tạo thành một ngữ cảnh tham số kiểu liên quan**. Khi inner generic được khai báo trực tiếp trong outer generic:

- `Outer<T>.Inner<U>` mô tả hai tham số kiểu rõ ràng.
- `Outer.Inner` mô tả cách dùng raw liên quan.
- `Outer.Inner<U>` và `Outer<T>.Inner` là hai dạng tham số hóa một phần không hợp lệ trong cấu trúc này.
- `Outer<?>.Inner<?>` cho phép thể hiện hai kiểu chưa biết mà không bỏ kiểm tra generics.
- `Outer<T>.PlainInner` hợp lệ nếu member không có type parameter U riêng.
- `Outer.Nested<V>` của static nested class có quy tắc độc lập vì không gắn với một enclosing instance.

Khi gặp lỗi `improperly formed type`, hãy kiểm tra **cả qualifier của outer lẫn generic declaration của member class**, rồi thay raw/missing type arguments bằng kiểu cụ thể hoặc wildcard theo đúng thông tin hiện có.
