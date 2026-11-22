# Phân giải overload và ảnh hưởng của kiểu tại thời điểm biên dịch

Khi nhiều phương thức cùng tên nhưng có danh sách tham số khác nhau, Java cho phép **overloading** (nạp chồng). Điểm quan trọng là **`javac` chọn chữ ký phương thức sẽ được gọi dựa trên thông tin kiểu tại thời điểm biên dịch**: kiểu tĩnh của biểu thức nhận (receiver), kiểu của đối số, số lượng đối số, khả năng chuyển đổi kiểu, tính khả dụng của từng phương thức và các quy tắc chọn phương thức cụ thể nhất.

Giá trị runtime của đối tượng **không khiến Java tự chọn một overload khác**. Runtime có thể dùng cơ chế **overriding** để chọn phần triển khai của *chính chữ ký đã được chọn*, nhưng đó là một bước khác.

Bài này giải thích quy trình phân giải overload của `javac`, ảnh hưởng của kiểu tĩnh, primitive widening, boxing/unboxing, varargs, `null`, generic, tính mơ hồ (ambiguity), cách phân biệt overload với override và phương pháp chẩn đoán. Các ví dụ độc lập sử dụng Java 17+.

## 1. Overloading là gì?

Hai phương thức có thể cùng tên nếu **chữ ký** khác nhau ở danh sách kiểu tham số (và các yếu tố liên quan đến tham số kiểu theo quy tắc JLS):

```java
static void print(int value) {
    System.out.println("int: " + value);
}

static void print(String value) {
    System.out.println("String: " + value);
}
```

Đây là hai phương thức nạp chồng: `print(int)` và `print(String)`. Khi viết `print(12)`, biểu thức đối số có kiểu `int` nên `print(int)` là ứng viên trực tiếp; với `print("hello")` thì `print(String)` thích hợp hơn.

**Chỉ thay đổi kiểu trả về là không đủ để overload**:

```java
// KHÔNG BIÊN DỊCH ĐƯỢC khi đặt cả hai khai báo trong cùng một lớp.
int read(String key) { return 1; }
String read(String key) { return key; }
```

Hai phương thức trên có cùng tên và cùng kiểu tham số, vì vậy là khai báo trùng. Kiểu trả về không phải cách tạo hai overload cùng danh sách tham số. Các ví dụ cố ý lỗi trong bài được ghi rõ, không đặt chung với mã Java chạy được.

Một số điểm cần nhớ:

- Overload không nhất thiết có cùng kiểu trả về; nó cần các chữ ký khai báo hợp lệ khác nhau.
- Overload có thể gồm phương thức `static` hoặc instance, nhưng các quy tắc truy cập, kế thừa, che khuất và tính khả dụng vẫn áp dụng.
- Không thể phân biệt hai phương thức chỉ bằng tên của tham số: `take(int a)` và `take(int b)` vẫn trùng chữ ký.
- `int[]` và `int...` biểu diễn cùng kiểu tham số mảng `int[]` ở mức chữ ký khai báo; không thể dùng riêng hai dạng này để tạo hai overload trong cùng lớp.

## 2. Ví dụ hoàn chỉnh: cùng dữ liệu, khác kiểu tĩnh

Tạo file `OverloadWalkthrough.java`:

```java
public class OverloadWalkthrough {
    static void label(Object x) {
        System.out.println("Object");
    }

    static void label(String x) {
        System.out.println("String");
    }

    static void number(long x) {
        System.out.println("long");
    }

    static void number(Integer x) {
        System.out.println("Integer");
    }

    static void number(int... x) {
        System.out.println("int... " + x.length);
    }

    static class Parent {
        void show(Object x) {
            System.out.println("Parent Object");
        }
    }

    static class Child extends Parent {
        @Override
        void show(Object x) {
            System.out.println("Child Object");
        }

        void show(String x) {
            System.out.println("Child String");
        }
    }

    public static void main(String[] args) {
        Object o = "text";
        String s = "text";

        label(o);
        label(s);
        label(null);

        number(7);
        Integer boxed = 7;
        number(boxed);
        number();
        number(7, 8);

        Parent ref = new Child();
        ref.show("text");
        ((Child) ref).show("text");
    }
}
```

Từ thư mục chứa file, dùng JDK 17+:

```bash
javac --release 17 -encoding UTF-8 -d out OverloadWalkthrough.java
java -cp out OverloadWalkthrough
```

**Stdout chính xác**:

```text
Object
String
String
long
Integer
int... 0
int... 2
Child Object
Child String
```

Bản Java trên đã được kiểm chứng bằng `javac` và `java` với JDK 21 khi nhắm `--release 17`. Các dòng output này giúp quan sát ba cơ chế khác nhau: **kiểu tĩnh**, **thứ tự các pha overload** và **dispatch của phương thức override**.

Phần tiếp theo giải thích lần lượt, đặc biệt tại sao `number(7)` chọn `long` thay vì `Integer`, và vì sao `ref.show("text")` gọi `Child.show(Object)` dù lớp thực tế là `Child`.

## 3. Kiểu tĩnh của đối số quyết định overload

Trong ví dụ:

```java
Object o = "text";
String s = "text";

label(o); // label(Object)
label(s); // label(String)
```

Cả `o` và `s` đều đang trỏ đến đối tượng `String`. Tuy nhiên:

- `o` có **kiểu khai báo là `Object`**. `javac` không chọn `label(String)` chỉ vì ở runtime giá trị đang là `String`. `label(Object)` phù hợp với đối số kiểu `Object`.
- `s` có **kiểu khai báo là `String`**. Cả `label(Object)` và `label(String)` đều nhận được giá trị kiểu `String`, nhưng `label(String)` cụ thể hơn, nên được chọn.
- `label(null)` hợp lệ cho cả hai tham số kiểu tham chiếu; do `String` là subtype của `Object`, `label(String)` được chọn là overload cụ thể hơn.

Không thể kết luận overload từ `x.getClass()` rồi áp dụng ngược vào quá trình biên dịch. `x.getClass()` là thông tin runtime, trong khi overload được giải quyết khi compiler xử lý biểu thức lời gọi.

### Ép kiểu thay đổi cách javac nhìn biểu thức

```java
Object value = "hello";

label(value);           // label(Object)
label((String) value);  // label(String)
```

Dạng ép kiểu `(String) value` làm **biểu thức tại vị trí đối số có kiểu tĩnh `String`**. Nếu giá trị không thực sự là `String`, ép kiểu có thể ném `ClassCastException` trước khi lời gọi diễn ra. Cast không phải phép "bật" overload theo runtime một cách tự động; nó là biểu thức có quy tắc kiểm tra riêng.

Ví dụ khác:

```java
Object value = new Object();
// label((String) value); // Nếu bỏ comment, biên dịch được nhưng
// lúc chạy ném ClassCastException trước khi gọi label(String).
```

Nếu cần hành vi phụ thuộc loại thực tế, dùng kiểm tra kiểu và nhánh minh bạch:

```java
if (value instanceof String text) {
    label(text);  // text có kiểu String trong nhánh đúng.
} else {
    label(value);
}
```

Đây là đoạn **minh họa** đặt trong một phương thức có `label` và biến `value` trong phạm vi; không phải chương trình độc lập. Với `instanceof` pattern matching của Java 17, biến `text` được sử dụng trong phạm vi được xác định là đã khớp kiểu.

## 4. Javac tìm và chọn overload như thế nào?

Java Language Specification (JLS `15.12) mô tả quá trình bằng các bước có quy tắc:

1. **Xác định kiểu cần tìm phương thức** từ hình thức lời gọi và receiver (ví dụ `ref.method(...)`, `Type.method(...)` hoặc lời gọi không qualifier).
2. **Tìm ứng viên có tên và số đối số phù hợp tiềm năng**, gồm phương thức có thể truy cập từ kiểu cần tìm và các phương thức kế thừa, có xét quy tắc đặc biệt cho generic, lambda hoặc method reference.
3. **Xác định tính áp dụng (applicability)** theo ba pha có thứ tự. Chỉ chuyển sang pha sau khi không tìm được phương thức áp dụng ở pha trước.
4. **Chọn phương thức cụ thể nhất** trong tập áp dụng thuộc pha thành công đầu tiên. Nếu không có phương thức áp dụng hoặc có nhiều phương thức tối ưu nhưng không có lựa chọn duy nhất theo quy tắc JLS, trình biên dịch báo lỗi tương ứng.
5. **Kiểm tra tính thích hợp của lời gọi** theo các yêu cầu bổ sung. Thông tin chữ ký đã chọn tham gia vào biểu thức lời gọi và đường dispatch runtime.

Đây là mô hình đúng hơn quy tắc học thuộc lòng kiểu "Java luôn chọn phương thức có ít chuyển đổi nhất". Trình biên dịch không đơn giản cộng điểm cho từng phép chuyển đổi rồi chọn tổng nhỏ nhất; JLS quy định rõ **các pha**, khả năng áp dụng và quan hệ *more specific*.

### Ba pha overload resolution

| Pha | Tên trong JLS | Những chuyển đổi được xét ở mức khái quát | Varargs expansion |
| --- | --- | --- | --- |
| 1 | Strict invocation | Khớp kiểu, widening primitive, widening reference và các tương thích strict khác; **không cần boxing/unboxing** | Chưa mở rộng |
| 2 | Loose invocation | Thêm boxing/unboxing và các chuyển đổi hợp lệ theo loose invocation | Chưa mở rộng |
| 3 | Variable arity | Cho phép áp dụng lời gọi biến số đối số đối với phương thức `...`, cùng các quy tắc chuyển đổi được phép | Có |

**Tìm thấy ứng viên ở pha 1 thì không xét pha 2 để "so kèo" với ứng viên boxing.** Nếu pha 1 không có ứng viên, mới xét pha 2. Tương tự, varargs expansion thường bị hoãn đến pha 3.

Tại mỗi pha, phương thức varargs vẫn có thể được xét như **fixed arity** nếu argument thực sự tương thích với tham số mảng, chẳng hạn truyền một `int[]` cho `m(int...)`. Vì vậy không nên hiểu sai rằng mọi lời gọi phương thức khai báo `...` luôn rơi vào pha 3.

Trong generic method hoặc lời gọi có lambda/method reference, xác định "áp dụng được" phức tạp hơn bảng tóm tắt; trình biên dịch còn dùng inference và target typing. Khi kết luận một trường hợp khó, xem JLS thay vì áp dụng máy móc chỉ ba câu trên.

## 5. Primitive widening, boxing và unboxing: thứ tự quan trọng

Xét các overload trong `OverloadWalkthrough`:

```java
static void number(long x) { System.out.println("long"); }
static void number(Integer x) { System.out.println("Integer"); }
static void number(int... x) { System.out.println("int... " + x.length); }
```

Với lời gọi:

```java
number(7);
```

Literal `7` có kiểu `int`. Những đường chuyển đổi có thể nghĩ đến:

- `int -> long`: **widening primitive**, áp dụng ở pha 1.
- `int -> Integer`: **boxing**, xét ở pha 2 nếu pha 1 không có phương thức phù hợp.
- `int -> int...` dưới dạng một phần tử: **varargs expansion**, xét ở pha 3 nếu các pha trước đều không có phương thức phù hợp.

**Kết quả là `number(long)`.** Vì pha 1 đã tìm được ứng viên, compiler không cần cân nhắc boxing hay varargs expansion.

Với:

```java
Integer boxed = 7;
number(boxed);
```

Đối số có kiểu tĩnh `Integer`. Overload `number(Integer)` tương thích trực tiếp ở pha 1, còn chuyển `Integer -> long` đòi hỏi unboxing rồi widening nên không thắng ứng viên pha 1. Kết quả in `Integer`.

Với:

```java
number();      // không đối số -> int... 0
number(7, 8);  // hai đối số -> int... 2
```

Chỉ overload varargs `number(int...)` có thể nhận số lượng đối số tương ứng bằng cơ chế mở rộng `...`. Giá trị thực nhận là mảng `int[]` gồm 0 hoặc 2 phần tử.

### Widening có thể được chọn trước boxing

Quy tắc gần đúng hữu ích: **nếu một overload fixed-arity đã áp dụng bằng chuyển đổi strict (như widening) thì chưa đến pha boxing**. Tuy nhiên, điều này không tạo một bảng thứ tự tuyệt đối cho *mọi* kiểu và mọi overload.

Ví dụ khác (mã minh họa trong cùng lớp):

```java
static void route(Number n) {
    System.out.println("Number");
}
static void route(long n) {
    System.out.println("long");
}

Integer value = 10;
route(value); // route(Number): widening reference ở pha 1.
```

Ở đây `Integer -> Number` là widening reference, còn `Integer -> long` cần unboxing và widening primitive. Kết quả `Number`.

### Numeric literal không tự thu hẹp cho overload

Một literal `1` có kiểu `int` trừ khi có quy định kiểu khác. Trong Java có các trường hợp **gán hằng** cho `byte` hoặc `short` khi giá trị phù hợp, nhưng quy tắc đó **không đồng nghĩa** compiler tự thử narrowing primitive cho lời gọi phương thức:

```java
static void onlyByte(byte x) {}

byte b = 1;       // Gán hằng hợp lệ trong phạm vi giá trị byte.
onlyByte(b);      // Hợp lệ.
onlyByte((byte) 1); // Hợp lệ nhờ cast.
// onlyByte(1);   // LỖI BIÊN DỊCH: int -> byte không tự narrowing khi gọi.
```

Đoạn trên là ví dụ **nằm bên trong một lớp/phương thức phù hợp**, không phải source file độc lập. Nguyên tắc này giải thích nhiều hiện tượng overload tưởng như khác với phép gán.

## 6. Phương thức cụ thể nhất (most specific) là gì?

Nếu trong cùng pha có nhiều phương thức áp dụng được, compiler chọn overload **cụ thể nhất theo quy tắc JLS `15.12.2.5**. Với các lớp có quan hệ cha–con dễ hiểu, phương thức nhận kiểu con thường cụ thể hơn phương thức nhận kiểu cha.

```java
static void label(Object o) { System.out.println("Object"); }
static void label(String s) { System.out.println("String"); }
```

Với `label("abc")`, kiểu `String` có thể chuyển thành `Object`. Cả hai overload áp dụng ở pha 1, nhưng `String` cụ thể hơn `Object` nên chọn `label(String)`.

Với `label(null)`, literal `null` tương thích với kiểu tham chiếu và `String` vẫn cụ thể hơn `Object`; do đó cũng chọn `label(String)`.

Tuy nhiên, nếu kiểu tham số **không có quan hệ cụ thể hơn rõ ràng**, compiler có thể không có overload thắng duy nhất. Trường hợp đó là *ambiguous*, không phải ngẫu nhiên chọn overload xuất hiện đầu tiên trong file.

### Ambiguity vì null

Hai overload sau có thể cùng tồn tại:

```java
static void select(String value) {
    System.out.println("String");
}
static void select(Integer value) {
    System.out.println("Integer");
}
```

Các lời gọi:

```java
select("a");             // String
select(Integer.valueOf(1)); // Integer
// select(null);          // LỖI BIÊN DỊCH: ambiguous.
select((String) null);   // String
select((Integer) null);  // Integer
```

`null` không có kiểu thực thể String hoặc Integer tại runtime để compiler dựa vào. Cả hai overload đều nhận được `null`, và `String` không là subtype của `Integer` (cũng không ngược lại), nên không có phương thức thắng duy nhất theo quy tắc áp dụng ở đây. **Cast chỉ rõ kiểu tĩnh của biểu thức**, từ đó giải quyết ambiguity.

Đừng "sửa" bằng cách đảo thứ tự khai báo: thứ tự xuất hiện trong source không quyết định overload.

### Ambiguity vì hai tham số đối xứng

```java
static void mix(int a, long b) {}
static void mix(long a, int b) {}

// mix(1, 1); // LỖI BIÊN DỊCH: cả hai áp dụng, không bên nào cụ thể hơn.
mix(1, 1L);   // Chọn mix(int, long).
mix(1L, 1);   // Chọn mix(long, int).
```

Trong lời gọi `mix(1, 1)`, mỗi overload có một vị trí khớp `int` và một vị trí widening `int -> long`. Không có quy tắc "xem tham số thứ nhất là ưu tiên" để loại bỏ mơ hồ. Các literal mang hậu tố `L` trong hai lời gọi sau làm khác kiểu tĩnh của đối số, dẫn tới lựa chọn rõ ràng.

## 7. Varargs cũng là một phần của overload resolution

Varargs khai báo bằng `...`, nhưng phương thức thực tế có tham số mảng. Ví dụ:

```java
static void sum(int... numbers) {
    System.out.println(numbers.length);
}
```

Có hai cách gọi hợp lệ:

```java
sum(1, 2, 3);                 // Mở rộng varargs: 3 phần tử.
sum(new int[] {1, 2, 3});    // Truyền mảng kiểu int[] trực tiếp.
```

Cả hai dạng đều in `3`. Trường hợp truyền mảng có thể được xử lý như fixed-arity invocation; trường hợp ba đối số nguyên lẻ sử dụng variable-arity invocation.

Một ví dụ về ưu tiên fixed arity:

```java
static void send(int x) {
    System.out.println("fixed");
}
static void send(int... values) {
    System.out.println("varargs");
}

send(5);    // fixed
send(5, 6); // varargs
```

`send(5)` chọn bản fixed-arity `send(int)` ở pha 1; varargs expansion chưa được sử dụng. `send(5, 6)` không khớp `send(int)` vì số đối số khác, nên bản varargs phù hợp ở pha 3.

**Cẩn thận với literal `null` và varargs kiểu tham chiếu:** ví dụ một lời gọi `m(null)` vào `m(Object...)` có thể được xử lý như truyền **một mảng Object[] bằng null**, không phải mảng có một phần tử null; trình biên dịch có thể cảnh báo. Nếu muốn truyền một phần tử null, dùng `m((Object) null)`; nếu chủ ý truyền mảng null, dùng `m((Object[]) null)`. Không truy cập `array.length` khi mảng có thể null.

## 8. Kiểu tĩnh của receiver và khác biệt giữa overload với override

Đây là nơi dễ nhầm nhất. Quay lại ví dụ:

```java
static class Parent {
    void show(Object x) {
        System.out.println("Parent Object");
    }
}

static class Child extends Parent {
    @Override
    void show(Object x) {
        System.out.println("Child Object");
    }

    void show(String x) {
        System.out.println("Child String");
    }
}

Parent ref = new Child();
ref.show("text");
((Child) ref).show("text");
```

Ở lời gọi `ref.show("text")`:

1. **Kiểu tĩnh của receiver là `Parent`**, nên bước tìm overload được thực hiện dựa trên những phương thức hiện hữu/khả dụng theo kiểu `Parent`. Tại đây compiler tìm được `show(Object)`, còn overload `show(String)` chỉ được khai báo ở `Child` nên không nằm trong tập ứng viên khi receiver tĩnh là `Parent`.
2. **Compiler chọn chữ ký `show(Object)`**. Việc tham số thực tế là `String` chỉ cho phép widening reference thành `Object`.
3. **Runtime thấy receiver thật là `Child`**, nên với phương thức instance được override, JVM chạy phần triển khai `Child.show(Object)`. Output là `Child Object`.

Ở lời gọi `((Child) ref).show("text")`, biểu thức receiver đã được cast sang `Child`. Compiler nhìn thấy cả `show(Object)` và `show(String)`; overload `show(String)` cụ thể hơn. Output là `Child String`.

| Câu hỏi | Overload resolution | Override dispatch |
| --- | --- | --- |
| Diễn ra về mặt quyết định ở đâu? | Khi biên dịch (compile time) | Khi chạy đối với phương thức instance có dynamic dispatch |
| Dựa trên yếu tố nào? | Kiểu tĩnh receiver/đối số, danh sách ứng viên và quy tắc JLS | Kiểu runtime của receiver và chữ ký đã chọn |
| Có thể thay đổi chữ ký được chọn sau khi compile? | Không do runtime type tự quyết định | Không; chỉ chọn implementation tương ứng cùng chữ ký |
| Ví dụ | `show(Object)` hay `show(String)` | `Parent.show(Object)` hay `Child.show(Object)` |

**Kết luận kỹ thuật:** Có thể có **overload được phân giải tĩnh**, sau đó **override được phân giải động** trong một lời gọi. Nói đơn giản "Java method binding đều tĩnh" hoặc "Java luôn gọi method theo runtime type" đều thiếu điều kiện.

Phương thức `static` dùng cơ chế khác (method hiding, không có dynamic dispatch như instance override). Phương thức `private` và một số dạng gọi đặc biệt cũng không tuân theo trực giác virtual dispatch thông thường. Bài học này tập trung vào overload của lời gọi phương thức và ví dụ instance override phổ biến.

## 9. Generics và kiểu tĩnh của collection

Generics khiến việc khai báo biến qua interface càng quan trọng. Tạo file `GenericView.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class GenericView {
    static void inspect(Collection<?> c) {
        System.out.println("Collection");
    }

    static void inspect(List<?> l) {
        System.out.println("List");
    }

    public static void main(String[] args) {
        Collection<String> asCollection = new ArrayList<>();
        List<String> asList = new ArrayList<>();

        inspect(asCollection);
        inspect(asList);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 -d out GenericView.java
java -cp out GenericView
```

Stdout chính xác:

```text
Collection
List
```

Cả hai giá trị runtime đều là `ArrayList`, nhưng biến thứ nhất có kiểu tĩnh `Collection<String>` nên chỉ overload nhận `Collection<?>` là áp dụng từ kiểu biến đó trong ví dụ này. Biến thứ hai có kiểu tĩnh `List<String>`; vì `List` là subtype của `Collection`, overload `inspect(List<?>)` cụ thể hơn.

**Type erasure** cũng giới hạn cách overload theo generic. Hai phương thức sau **không thể cùng khai báo trong một lớp**:

```java
// LỖI BIÊN DỊCH: name clash do cùng erasure.
static void consume(java.util.List<String> values) {}
static void consume(java.util.List<Integer> values) {}
```

Sau erasure, cả hai có danh sách tham số hiệu dụng `List` nên gây xung đột. Đừng giả định Java có overload tách riêng `List<String>` với `List<Integer>` chỉ dựa vào kiểu đối số generic trong dấu ngoặc nhọn.

### Generic method và type inference

Với phương thức generic như:

```java
static <T extends Number> void accept(T value) {
    System.out.println("number");
}
```

Compiler phải suy luận tham số kiểu `T` sao cho thỏa ràng buộc và ngữ cảnh lời gọi. Khi có overload generic cạnh overload khác, Java không chỉ so tên class thô; **type inference, bounds, wildcard, poly expressions** có thể tham gia vào việc ứng viên nào áp dụng và ứng viên nào cụ thể hơn.

Mã `accept` trên là một minh họa về suy luận generic, **không phải một chương trình chạy độc lập**. Với những lời gọi generic phức tạp, xem JLS `18 (Type Inference) cùng `15.12, thay vì cố suy diễn từ quy tắc "runtime type".

## 10. Lambda, method reference và overload

Lambda/method reference nhận kiểu thông qua **target type** là một functional interface. Nếu có overload với hai functional interface khác nhau, compiler cần xét cả hình thức lambda, các kiểu tham số có thể suy luận, kiểu kết quả và độ cụ thể của ứng viên.

Ví dụ minh họa với hai overload:

```java
static void execute(Runnable r) {
    r.run();
}

static void execute(java.util.concurrent.Callable<String> c)
        throws Exception {
    System.out.println(c.call());
}
```

Lời gọi:

```java
execute(() -> System.out.println("running"));
```

Lambda này phù hợp với hành vi trả về `void` của `Runnable` nên chọn overload `execute(Runnable)`, in `running`. Còn:

```java
execute(() -> "result");
```

Lambda trả về `String`, nên phù hợp với `Callable<String>` hơn; overload này in `result`. Các mảnh ví dụ trên chỉ chạy khi đặt trong lớp với phương thức gọi có xử lý hoặc khai báo `throws Exception` cho nhánh `Callable`; chúng không phải file Java độc lập như `OverloadWalkthrough.java`.

Một lambda có thân/kiểu chưa xác định trước có thể khiến tính áp dụng của overload phụ thuộc vào target typing, và một số tổ hợp dẫn tới ambiguity. **Không thể chỉ nhìn runtime của đối tượng lambda** để chọn overload. Một số lambda hoặc method reference được xét theo các quy tắc “pertinent to applicability” cụ thể trong JLS `15.12 và `15.27; ví dụ đơn giản ở trên không thay thế toàn bộ quy tắc đó.

## 11. Khi nào lời gọi báo lỗi ambiguous hoặc không tìm được overload?

Hai lỗi thường gặp nhưng khác nhau:

- **No suitable method / cannot be applied:** không có ứng viên có thể nhận đối số theo quy tắc chuyển đổi hợp lệ; ví dụ chỉ có `read(byte)` nhưng gọi `read(1000)` với đối số `int`, Java không tự narrowing cho method invocation.
- **Reference to ... is ambiguous:** có ít nhất hai ứng viên áp dụng được nhưng không xác định được một lựa chọn thắng duy nhất; ví dụ `select(String)` và `select(Integer)` khi gọi `select(null)`.

Ví dụ `java.lang.String.valueOf(...)` có nhiều overload. Khi phân tích code thực tế, hãy đọc **danh sách overload đúng của API và đúng phiên bản JDK**, xác định kiểu tĩnh từng argument, rồi áp dụng quy trình; đừng suy đoán compiler từ giá trị được in ra.

### Compiler kiểm tra theo kiểu tĩnh, không “chạy thử” đối số

`javac` không thực thi chương trình để biết:

- Một biến kiểu `Object` có chắc chắn chứa String ở runtime hay không.
- Nhánh `if` nào sẽ được thực hiện dựa trên dữ liệu runtime.
- Kết quả trả về của hàm sẽ có đối tượng runtime subtype nào.
- Một cast sang subtype có thành công hay ném `ClassCastException` ở lần chạy cụ thể.

Compiler có thể dùng các thông tin tĩnh khác như flow-sensitive type của pattern variable, generic inference hoặc loại expression, nhưng đó vẫn là **phân tích ngôn ngữ ở thời điểm compile**.

### Cách sửa ambiguity đúng mục đích

1. Xác minh overload và kiểu thực sự của từng đối số tại nơi gọi.
2. Dùng biến có kiểu cụ thể hoặc cast **an toàn, có chủ đích** nếu muốn chọn một chữ ký xác định.
3. Nếu hai overload khiến API thường xuyên mơ hồ, cân nhắc **đặt tên phương thức rõ hơn** hoặc thiết kế lại tham số.
4. Không trông chờ overload khai báo sau sẽ được ưu tiên.
5. Không thêm cast thiếu kiểm tra chỉ để compiler hết lỗi rồi tạo `ClassCastException` lúc chạy.

## 12. Quan sát bytecode để thấy chữ ký đã chọn

Sau khi biên dịch file `OverloadWalkthrough.java`, chạy:

```bash
javap -classpath out -c OverloadWalkthrough
```

`javap -c` hiển thị các instruction của class file, bao gồm các lệnh gọi và thông tin phương thức đích như `label:(Ljava/lang/Object;)V`, `label:(Ljava/lang/String;)V`, `number:(J)V` hoặc `number:(Ljava/lang/Integer;)V` (cú pháp chi tiết output phụ thuộc `javap`/JDK).

Các descriptor này minh họa việc **chữ ký overload được quyết định khi compile**:

- `(Ljava/lang/Object;)V`: nhận một `Object`, trả về `void`.
- `(Ljava/lang/String;)V`: nhận một `String`, trả về `void`.
- `(J)V`: nhận một `long` primitive, trả về `void`.
- `(Ljava/lang/Integer;)V`: nhận `Integer`, trả về `void`.
- `([I)V`: nhận mảng `int[]`, trả về `void`, tương ứng tham số `int...`.

Mục đích của `javap` ở đây là xác minh chữ ký lựa chọn, không diễn giải chi tiết mọi instruction JVM. Bytecode có thể khác giữa các bản compiler; lựa chọn overload theo JLS vẫn phải được bảo toàn về hành vi quan sát được.

Với phương thức instance được override, bytecode chứa tham chiếu tới **descriptor đã chọn**; runtime virtual dispatch chọn phần triển khai tương ứng của receiver runtime nếu áp dụng. Nó không thử lần nữa để chuyển từ `show(Object)` sang `show(String)`.

## 13. Các lỗi nhận thức phổ biến

| Nhận định sai | Điều đúng | Ví dụ |
| --- | --- | --- |
| "Giá trị là String nên overload String sẽ chạy" | Cần xét kiểu **tĩnh** đối số | `Object o = "x"; label(o)` gọi `label(Object)` |
| "Java luôn thích boxing hơn widening" | Strict invocation được xét trước boxing | `number(7)` chọn `number(long)` |
| "Varargs được ưu tiên vì nhận nhiều đối số" | Fixed arity được xét trước varargs expansion | `send(5)` chọn `send(int)` |
| "Overload được quyết định theo class runtime" | Overload tĩnh; override động khi có virtual method | `Parent ref = new Child(); ref.show("x")` |
| "null luôn chọn Object" | Chọn ứng viên cụ thể nhất hoặc báo ambiguous | `label(null)` chọn String; `select(null)` mơ hồ |
| "Chỉ khác return type thì là overload" | Cùng danh sách tham số là trùng chữ ký | Hai `read(String)` khác return type lỗi |
| "List<String> và List<Integer> là hai overload riêng" | Erasure gây name clash khi chỉ khác kiểu đối số generic | Hai `consume(List<...>)` lỗi |
| "literal int tự thu hẹp cho byte param" | Method invocation không tự thực hiện constant narrowing như phép gán | `onlyByte(1)` lỗi |
| "Compiler chọn method xuất hiện trước" | Thứ tự khai báo không phải tiêu chí lựa chọn | `select(null)` vẫn ambiguous |
| "Compile thành công thì cast chắc chạy" | Runtime cast có thể ném lỗi | `(String) new Object()` |

## 14. Quy trình phân tích một lời gọi overload khó

Khi thấy một lời gọi gây bất ngờ, hãy tự trả lời theo thứ tự:

1. **Tên và hình thức lời gọi là gì?** Ví dụ `receiver.act(x)` hay `Type.act(x)`; là instance/static, có qualifier hay không?
2. **Kiểu tĩnh của receiver là gì?** Đừng dùng kiểu runtime làm đáp án. Kiểu này xác định lớp/interface cần tìm thành viên.
3. **Kiểu của từng biểu thức đối số là gì?** Bao gồm literal `int`/`long`, biến `Object`/`String`, `null`, cast, generic và lambda.
4. **Những overload nào hợp lệ và accessible?** Xem số lượng tham số, kế thừa, `static`/instance, quyền truy cập và chữ ký thực sự.
5. **Pha 1 có ứng viên không?** Xét strict invocation, widening primitive/reference, fixed arity.
6. **Nếu không, pha 2 có ứng viên không?** Xét boxing/unboxing và quy tắc loose invocation.
7. **Nếu vẫn không, pha 3 có ứng viên không?** Xét variable arity cho varargs.
8. **Phương thức cụ thể nhất trong pha thắng là gì?** Nếu không có người thắng duy nhất, báo ambiguity; không tự suy đoán.
9. **Nếu lời gọi instance virtual, runtime dispatch tới override nào?** Chỉ hỏi câu này **sau khi** đã có chữ ký overload.
10. **Xác minh nếu cần:** tạo ví dụ tối thiểu, biên dịch bằng `javac`, xem diagnostic và `javap -c`.

Khi compiler báo ambiguity và output khác kỳ vọng, có thể dùng:

```bash
javac -Xdiags:verbose -encoding UTF-8 Example.java
```

`Example.java` ở đây là tên file minh họa, phải thay bằng file thực. `-Xdiags:verbose` giúp cung cấp thêm thông tin diagnostic ở những phiên bản `javac` hỗ trợ. **Không có cách nào chạy ví dụ ambiguity đã lỗi biên dịch** trước khi sửa lỗi, và cú pháp thông báo lỗi cụ thể có thể thay đổi theo JDK.

## 15. Bài tập tự kiểm tra

### Bài 1: Kiểu biến hay giá trị?

```java
static void p(Object x) { System.out.println("O"); }
static void p(String x) { System.out.println("S"); }

Object x = "abc";
p(x);
p((String) x);
```

Đáp án: `O` rồi `S`. Cast ở lời gọi thứ hai thay đổi kiểu tĩnh của argument thành `String`. Đoạn mã minh họa cần đặt các khai báo phương thức trong lớp và các lệnh gọi trong một phương thức.

### Bài 2: Widening, boxing, varargs

Với các overload `number(long)`, `number(Integer)`, `number(int...)` của file chạy được:

```java
number(3);
Integer i = 3;
number(i);
number(3, 4);
```

Đáp án: `long`, `Integer`, `int... 2`. Lệnh gọi đầu được chọn ở pha strict; lệnh thứ hai khớp `Integer`; lệnh thứ ba phải dùng biến số đối số.

### Bài 3: Hai overload có mơ hồ?

```java
static void f(String x) {}
static void f(Integer x) {}

// f(null);       // Lỗi ambiguous.
f((String) null); // Hợp lệ.
```

Đáp án: `String` và `Integer` không có quan hệ subtype với nhau, nên `null` không chỉ ra phương thức cụ thể nhất. Cast sang `String` giúp chọn một overload.

### Bài 4: Overload hay override?

```java
Parent p = new Child();
p.show("hello");
((Child) p).show("hello");
```

Đáp án: lời gọi thứ nhất chọn **`show(Object)` ở compile time**, rồi runtime thực thi **`Child.show(Object)`**; lời gọi thứ hai chọn **`show(String)`** nhờ receiver tĩnh `Child`.

### Bài 5: Sự khác nhau của generic view

Một biến `Collection<String> c = new ArrayList<>();` và một biến `List<String> l = new ArrayList<>();` được truyền vào hai overload `inspect(Collection<?>)` và `inspect(List<?>)`. Đáp án: `inspect(c)` chọn `Collection<?>`, `inspect(l)` chọn `List<?>`. Không dựa vào class runtime đều là `ArrayList`.

### Bài 6: Nêu giới hạn của phương pháp ba pha

Nếu lời gọi chứa lambda, generic inference hoặc method reference, có thể áp dụng công thức “widening > boxing > varargs” một cách máy móc không? Đáp án: **Không**. Ba pha vẫn là cấu trúc cốt lõi, nhưng việc ứng viên nào hợp lệ và phương thức nào cụ thể nhất còn do quy tắc type inference, functional interface và target typing quy định.

## 16. Kết luận và nguồn chính thống

**Overload resolution là quyết định tại compile time**, dựa trên những khai báo nhìn thấy từ **kiểu tĩnh** và quy tắc áp dụng phương thức của Java. Bộ quy tắc không đơn thuần là “kiểu giống nhất”: `javac` lần lượt kiểm tra strict invocation, loose invocation và variable arity, sau đó chọn phương thức cụ thể nhất trong pha thành công. **Override dispatch là cơ chế riêng khi chạy** cho lời gọi instance virtual với **chữ ký đã chọn**.

Nguồn kỹ thuật chính thống:

- [Java Language Specification, Java SE 21 — `15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12): xác định lớp/interface cần tìm, các pha applicability, chọn most specific và runtime invocation.
- [Java Language Specification, Java SE 21 — `5.3 Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.3): những chuyển đổi kiểu hợp lệ khi gọi phương thức.
- [Java Language Specification, Java SE 21 — `8.4 Method Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4): chữ ký, overload, override và giới hạn khai báo.
- [Java Language Specification, Java SE 21 — `18 Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html): suy luận kiểu cho generic và tương tác với overload.
- [Oracle JDK 21 — javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): dùng compiler và tùy chọn diagnostic khi kiểm chứng.

Khi không chắc vì sao Java chọn một overload, hãy **ghi ra kiểu tĩnh, tập ứng viên, pha áp dụng thắng và quan hệ most specific**, sau đó mới xét override runtime. Cách giải thích ấy giúp cả người đọc mã và người debug đưa ra kết luận nhất quán với `javac`.