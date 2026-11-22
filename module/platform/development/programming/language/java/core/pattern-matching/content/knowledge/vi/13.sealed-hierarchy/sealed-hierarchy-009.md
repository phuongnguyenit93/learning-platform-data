# Kết hợp sealed type với record trong Java

**Chủ đề:** Java Core Pattern Matching → *Sealed hierarchy*. Bài trình bày cách kết hợp **`sealed class` / `sealed interface`** và **`record`** để mô hình hóa một tập trạng thái hữu hạn, từ đó viết `switch` exhaustive và record pattern dễ đọc, ít ép kiểu, có kiểm tra compile time. Các ví dụ dùng **Java 21** (record pattern và pattern matching for switch đã ổn định), không yêu cầu preview.

## 1. Bài toán: một kiểu cha, nhiều dạng dữ liệu hợp lệ

Hãy hình dung một bộ tính toán phải xử lý ba loại biểu thức:

- Giá trị số: một số nguyên, ví dụ `3`.
- Phép cộng: hai biểu thức con, ví dụ `3 + 5`.
- Phép đổi dấu: một biểu thức con, ví dụ `-(5)`.

Nếu dùng một lớp duy nhất với trường `kind` cùng nhiều trường có thể `null`, người viết phải tự duy trì bất biến: `kind == SUM` thì hai toán hạng phải hiện diện; `kind == NUMBER` thì không nên dùng các trường của phép cộng. Java compiler không tự kiểm tra tính nhất quán của các cờ và trường này.

Nếu dùng interface thông thường:

```java
interface Expr { }

record Num(int value) implements Expr { }

record Sum(Expr left, Expr right) implements Expr { }
```

ta có lợi ích của đa hình nhưng **bất kỳ lớp nào được phép theo quy tắc truy cập cũng có thể triển khai `Expr`**. Khi một `switch` muốn xử lý mọi kiểu `Expr`, compiler không biết danh sách subtype là đóng.

Thêm `sealed` làm rõ tập kiểu con trực tiếp được phép:

```java
sealed interface Expr permits Num, Sum, Neg { }

record Num(int value) implements Expr { }
record Sum(Expr left, Expr right) implements Expr { }
record Neg(Expr inner) implements Expr { }
```

Đây là sự kết hợp phù hợp: **`sealed` giới hạn *các biến thể có thể có*, `record` mô tả *dữ liệu của từng biến thể*.** Nhờ vậy, một `switch` trên `Expr` có thể được kiểm tra bao phủ toàn bộ các biến thể đã định nghĩa.

## 2. Vai trò riêng của `sealed` và `record`

### 2.1. `sealed` kiểm soát cấu trúc kế thừa

Một `sealed interface` hoặc `sealed class` xác định danh sách những kiểu **được phép mở rộng/triển khai trực tiếp** thông qua `permits` (hoặc suy luận theo quy tắc JLS trong một số trường hợp cùng compilation unit).

```java
sealed interface Payment permits Cash, Card { }

record Cash(int amount) implements Payment { }
record Card(String token) implements Payment { }
```

Ở đây, chỉ `Cash` và `Card` là các implementor trực tiếp được khai báo là được phép của `Payment`. Nếu một kiểu khác cố triển khai `Payment` trực tiếp mà không được phép, compiler sẽ báo lỗi.

Điều cần chú ý:

- `permits` liệt kê **subtype trực tiếp**, không phải tùy ý mọi hậu duệ ở bất kỳ cấp nào.
- Một subtype trực tiếp của sealed class/interface phải có một trạng thái đóng/mở thích hợp: `final`, `sealed` hoặc `non-sealed` (hiển thị hoặc ngầm định theo loại khai báo).
- Nếu một nhánh được khai báo `non-sealed`, hậu duệ bên dưới nhánh ấy có thể mở rộng thêm; `sealed` của cha không có nghĩa mọi cấp trong cây đều đóng mãi mãi.
- Khi dùng named module, các subtype được `permits` phải thuộc cùng module; với unnamed module, chúng phải thuộc cùng package. Đây là ràng buộc của Java, không chỉ là quy ước tổ chức mã.
- Có thể bỏ `permits` khi những subtype trực tiếp phù hợp được suy luận theo JLS trong cùng compilation unit. Với bài học và thư viện công khai, ghi rõ `permits` thường làm thiết kế dễ hiểu hơn.

### 2.2. `record` lưu dữ liệu của một biến thể

Một record như:

```java
record Cash(int amount) implements Payment { }
```

có component `amount`; Java sinh ra các thành phần như field tương ứng, accessor `amount()`, canonical constructor (nếu không tự định nghĩa), và các phương thức `equals`, `hashCode`, `toString` theo quy tắc record.

`Cash` **ngầm định là `final`**. Vì thế, một record có thể trực tiếp implement một sealed interface mà **không cần viết thêm `final`**. Mỗi record diễn tả một cấu trúc dữ liệu rõ ràng.

Tuy nhiên, record **không tự xác thực** mọi điều kiện nghiệp vụ: `amount < 0` vẫn có thể được tạo nếu constructor không chặn. Record cũng chỉ có tính bất biến **nông** (*shallow immutability*): nếu một component tham chiếu đến object mutable, object đó có thể bị thay đổi.

### 2.3. Vì sao thường dùng `sealed interface` thay vì `sealed class` khi kết hợp record?

Record có superclass do Java quy định là `java.lang.Record` và **không được khai báo `extends SomeClass`**. Record có thể `implements` interface.

Đúng:

```java
sealed interface Event permits Started, Stopped { }
record Started(long epochMillis) implements Event { }
record Stopped(String reason) implements Event { }
```

Sai (minh họa **không biên dịch**):

```java
// KHÔNG BIÊN DỊCH:
// sealed abstract class Event permits Started { }
// record Started(long time) extends Event { }
```

Record không được mở rộng một lớp cha tùy ý. Nếu muốn tất cả biến thể là record, **sealed interface thường là kiểu cha tự nhiên**. Nếu phải dùng sealed class do cần state/implementation chung, các subtype trực tiếp cần là những class thích hợp; không thể khiến record `extends` lớp đó.

## 3. Một mô hình dữ liệu dạng algebraic data type

Cấu trúc:

```java
sealed interface Expr permits Num, Sum, Neg { }

record Num(int value) implements Expr { }
record Sum(Expr left, Expr right) implements Expr { }
record Neg(Expr inner) implements Expr { }
```

có thể đọc như một “tổng của các khả năng”:

```text
Expr =
    Num(value: int)
  | Sum(left: Expr, right: Expr)
  | Neg(inner: Expr)
```

Đây là cách mô hình hóa gần với **algebraic data type (ADT)** trong lập trình hàm, nhưng sử dụng các tính năng Java: hierarchy đóng cho các “nhánh” và record cho các “trường”.

**Điểm mạnh:**

- Không phải lưu một tag `kind` rồi tự nhớ tag ứng với trường nào.
- Không thể tạo một loại `Expr` mới bên ngoài tập cho phép nếu cây vẫn đóng.
- Dữ liệu của `Sum` và `Neg` có kiểu `Expr`, nên có thể biểu diễn cây đệ quy.
- `switch` phân loại từng record và có thể phân rã component ngay trong nhãn.
- Khi thêm subtype hợp lệ mới và biên dịch lại, compiler có thể chỉ ra `switch` chưa đầy đủ.

**Giới hạn:** Sealed hierarchy chỉ đóng **tập kiểu**, không tự chứng minh mọi **giá trị component** là hợp lệ. Một `Sum(null, null)` về mặt kiểu vẫn có thể được tạo nếu constructor không kiểm tra.

## 4. Dùng type pattern để xử lý từng record

Bản đơn giản sử dụng type pattern:

```java
static int eval(Expr expr) {
    return switch (expr) {
        case Num n -> n.value();
        case Sum s -> Math.addExact(eval(s.left()), eval(s.right()));
        case Neg n -> Math.negateExact(eval(n.inner()));
    };
}
```

Đây là ví dụ **trong cùng ngữ cảnh đã khai báo `Expr`, `Num`, `Sum`, `Neg`** ở trên. Khi selector có kiểu tĩnh `Expr`, JLS có thể kiểm tra các permitted subtype và nhận ra ba nhãn đã bao phủ đầy đủ hierarchy hiện tại.

Không cần thêm `default`. Nếu thêm biến thể mới vào sealed hierarchy và biên dịch lại, biểu thức trên sẽ bị compiler yêu cầu xem xét.

Bất lợi nhẹ của type pattern là cần gọi accessor để lấy dữ liệu: `n.value()`, `s.left()`, `s.right()`.

## 5. Record pattern: kiểm tra kiểu *và* phân rã dữ liệu

Java 21 cho phép dùng **record pattern**:

```java
static int eval(Expr expr) {
    return switch (expr) {
        case Num(int n) -> n;
        case Sum(Expr left, Expr right) ->
                Math.addExact(eval(left), eval(right));
        case Neg(Expr inner) -> Math.negateExact(eval(inner));
    };
}
```

`Num(int n)` có ý nghĩa: giá trị phải là đối tượng `Num`, và component `int value` được gắn vào biến pattern `n`. `Sum(Expr left, Expr right)` trích xuất hai component; `Neg(Expr inner)` trích xuất một component.

Phân tích một nhãn:

```java
case Sum(Expr left, Expr right) ->
        Math.addExact(eval(left), eval(right));
```

1. Java kiểm tra selector có khớp record class `Sum` không.
2. Nếu khớp, record pattern xét lần lượt các component bằng các pattern thành phần.
3. Các biến `left`, `right` được tạo trong phạm vi thích hợp của nhãn khi matching thành công.
4. Thân nhánh gọi đệ quy `eval` rồi cộng bằng `Math.addExact`.

`Math.addExact` ném `ArithmeticException` nếu phép cộng tràn miền `int`. Nó không làm giảm độ đúng của ví dụ; đây là lựa chọn rõ ràng thay vì để phép cộng int tràn âm thầm.

### Record pattern và type pattern là hai mức chi tiết

| Type pattern | Record pattern | Khi chọn |
| --- | --- | --- |
| `case Num n -> n.value()` | `case Num(int n) -> n` | Muốn chỉ dùng component `value` |
| `case Sum s -> eval(s.left()) + eval(s.right())` | `case Sum(Expr a, Expr b) -> eval(a) + eval(b)` | Muốn đọc trực tiếp cấu trúc hai vế |
| `case Neg n -> ...` | `case Neg(Expr inner) -> ...` | Muốn diễn đạt cấu trúc ngay ở nhãn |
| Có biến trỏ đến nguyên record | Có biến từ các component đã khớp | Cần gọi nhiều method trên record hay chỉ cần component? |

Không có yêu cầu bắt buộc tất cả case phải dùng record pattern. Với record lớn hoặc logic cần đối tượng nguyên vẹn, type pattern có thể rõ ràng hơn. Với cấu trúc nhỏ và quan tâm trực tiếp component, record pattern thường ngắn gọn và dễ nhìn.

## 6. Kết hợp record pattern lồng nhau

Các biểu thức dạng cây đặc biệt phù hợp với **nested record patterns**. Ví dụ, muốn nhận đúng một `Sum` có hai đối số là `Num`:

```java
static String inspect(Expr expr) {
    return switch (expr) {
        case Sum(Num(int a), Num(int b)) -> "sum-two-literals:" + a + "," + b;
        case Sum(Expr left, Expr right) -> "other-sum";
        case Num(int n) -> "number:" + n;
        case Neg(Expr inner) -> "negative-expression";
    };
}
```

Với `new Sum(new Num(1), new Num(2))`, nhánh đầu trả `sum-two-literals:1,2`. Với `new Sum(new Num(1), new Neg(new Num(2)))`, nhánh đầu không khớp vì vế phải là `Neg`; nhánh `Sum(Expr left, Expr right)` sau đó xử lý và trả `other-sum`.

Hai lưu ý quan trọng:

- Đặt nhánh **cụ thể** như `Sum(Num(...), Num(...))` trước nhánh `Sum(Expr, Expr)` **tổng quát**. Nếu đảo thứ tự, nhánh cụ thể có thể bị *dominate* và gây lỗi biên dịch.
- Nested record pattern mô tả **cấu trúc dữ liệu**, không tự đảm bảo điều kiện giá trị như “`a > 0`”. Dùng `when` nếu cần lọc theo giá trị.

Cây `Expr` là mô hình đệ quy, nhưng **matching của mỗi nhãn không tự đi sâu vô hạn**. Nó phân rã đúng những component được biểu thức pattern nêu ra; muốn duyệt cả cây, dùng đệ quy có điểm dừng như `eval` hoặc `describe`.

## 7. Guard `when` trên sealed record pattern

Một kiểu `Num` có thể có nhiều nhóm nghiệp vụ:

```java
static String describe(Expr expr) {
    return switch (expr) {
        case Num(int n) when n < 0 -> "negative literal:" + n;
        case Num(int n) -> "literal:" + n;
        case Sum(Expr left, Expr right) ->
                "sum(" + describe(left) + "," + describe(right) + ")";
        case Neg(Expr inner) -> "neg(" + describe(inner) + ")";
    };
}
```

Guard `when n < 0` chỉ được đánh giá **sau khi record pattern `Num(int n)` đã khớp**, nên biến `n` sẵn sàng để dùng. Nếu guard sai, Java tiếp tục xét nhãn khác; `case Num(int n)` không guard sẽ xử lý những số còn lại.

**Đừng chỉ viết các nhánh có guard rồi mặc nhiên nghĩ compiler sẽ nhận là exhaustive.** Java không chứng minh mọi biểu thức boolean tùy ý bao phủ hết giá trị. Với một biến thể cần phân nhánh bằng guard, nên để một nhãn **không guard** bao phủ phần còn lại.

### Guard khác với `if` trong thân case

Nếu chỉ muốn phân loại `Num` nội bộ, có thể viết:

```java
case Num(int n) -> {
    if (n < 0) {
        yield "negative literal:" + n;
    }
    yield "literal:" + n;
}
```

Đây chỉ là **một nhánh** dùng trong `switch expression`; khi `Num` đã được chọn, điều kiện `if` không làm Java chọn lại các case khác. Với `when`, guard sai khiến nhãn hiện tại không áp dụng. Dùng cách phù hợp với ý định xử lý.

## 8. Exhaustiveness: lý do sealed + record mạnh hơn phân loại Object

Khi selector có kiểu tĩnh `Expr`:

```java
static int eval(Expr expr) {
    return switch (expr) {
        case Num(int n) -> n;
        case Sum(Expr left, Expr right) -> eval(left) + eval(right);
        case Neg(Expr inner) -> -eval(inner);
    };
}
```

compiler có thể suy luận tập type con từ sealed hierarchy và kiểm tra switch exhaustive.

Nhưng khi đổi tham số thành `Object`:

```java
// KHÔNG BIÊN DỊCH (switch expression chưa exhaustive).
static String incomplete(Object input) {
    return switch (input) {
        case Num(int n) -> "number";
        case Sum(Expr a, Expr b) -> "sum";
        case Neg(Expr inner) -> "neg";
    };
}
```

`Object` có thể chứa `String`, `Integer`, các class khác. Ba record patterns chỉ bao phủ `Expr`, **không bao phủ mọi Object**.

Cách sửa nếu API nhận `Object`:

```java
static String inspect(Object input) {
    return switch (input) {
        case null -> "missing";
        case Expr expr -> "expr:" + describe(expr);
        default -> "not-expr";
    };
}
```

Ở đây pattern `Expr expr` là một type pattern tổng quát dành cho tập subtype của `Expr`, nhưng `default` vẫn cần thiết cho những kiểu không thuộc `Expr` vì selector là `Object`.

**Bài học API:** hãy khai báo tham số kiểu `Expr` nếu phương thức **chỉ chấp nhận biểu thức hợp lệ**. Chỉ mở lên `Object` tại ranh giới thật sự cần phân loại dữ liệu đầu vào đa dạng. Một API rộng không phải lúc nào cũng là API tốt.

### Không thêm `default` máy móc cho hierarchy đóng

```java
// KHÔNG NÊN DÙNG default chỉ để tránh phải xem xét subtype mới.
static String maybeHidesFutureCase(Expr expr) {
    return switch (expr) {
        case Num(int n) -> "num";
        case Sum(Expr a, Expr b) -> "sum";
        default -> "other";
    };
}
```

Mã hiện tại biên dịch, nhưng khi thêm subtype mới, `default` khiến việc thiếu xử lý cụ thể có thể bị che. Với mô hình đóng, ưu tiên liệt kê đủ ba nhánh `Num`, `Sum`, `Neg` và bỏ `default` nếu mỗi biến thể thực sự có hành vi riêng.

## 9. Xử lý null trên hai tầng khác nhau

**Tầng 1: chính selector `Expr` là `null`.** Pattern loại record ở selector ngoài không khớp null. Một `switch` expression exhaustive về kiểu `Expr` nhưng không có `case null` vẫn có thể ném **`NullPointerException`** khi được gọi với null.

```java
static String label(Expr expr) {
    return switch (expr) {
        case Num(int n) -> "num";
        case Sum(Expr a, Expr b) -> "sum";
        case Neg(Expr inner) -> "neg";
    };
}
```

Nếu gọi `label(null)`, hành vi là NPE, không phải chuyển sang nhánh record nào. Nếu null là đầu vào hợp lệ cần xử lý, thêm:

```java
case null -> "missing";
```

vào `switch` trên.

**Tầng 2: selector là một record khác null nhưng component của nó là null.** Ví dụ `new Sum(null, new Num(1))` có thể tồn tại nếu constructor không kiểm tra. Nó **không phải null selector**, vì chính `Sum` là một đối tượng.

Đây là vấn đề **bất biến của mô hình**, không đơn thuần là vấn đề `case null`. Với cây biểu thức trong bài này, chọn chính sách **không cho component null**:

```java
record Sum(Expr left, Expr right) implements Expr {
    Sum {
        java.util.Objects.requireNonNull(left, "left");
        java.util.Objects.requireNonNull(right, "right");
    }
}
```

Đây là **compact canonical constructor**. Khi tạo `new Sum(null, new Num(1))`, `requireNonNull` ném NPE với thông điệp `left`. Các instance `Sum` tạo qua constructor này luôn có hai component khác null.

Có thể viết constructor kiểm tra tương tự cho `Neg(Expr inner)`.

**Chú ý sâu:** ở Java 21, việc một pattern con có thể khớp component null hay không phụ thuộc loại pattern và quan hệ kiểu; không nên áp quy tắc “null không khớp bất kỳ pattern nào” từ selector ngoài sang mọi component lồng nhau. Cách đơn giản và an toàn hơn trong mô hình này là **đặt bất biến non-null ở constructor**, không giao trách nhiệm bảo vệ cấu trúc cho từng nhánh `switch`.

## 10. Record có thật sự immutable?

Record bảo đảm các **component fields** là `private final`, không có setter mặc định và không cho khai báo thêm instance field tùy ý. Tuy nhiên đây là **bất biến nông**. Ví dụ:

```java
record Tags(java.util.List<String> names) { }

java.util.List<String> source = new java.util.ArrayList<>();
source.add("first");
Tags tags = new Tags(source);
source.add("second");

// tags.names() hiện có thể quan sát thấy phần tử "second".
```

Lý do: `names` là tham chiếu `final` tới một danh sách mutable, không phải bản sao bất biến.

Để hạn chế điều này với mô hình record:

```java
record Tags(java.util.List<String> names) {
    Tags {
        names = java.util.List.copyOf(names);
    }
}
```

`List.copyOf` tạo hoặc tái sử dụng danh sách không sửa được và không chấp nhận phần tử null. Khi một record chứa collection, array hoặc đối tượng mutable, cần xem xét **defensive copy**, API trả về và mức độ bất biến sâu của phần tử.

Một record triển khai sealed interface không tự thay đổi quy tắc immutable này. **`sealed` kiểm soát ai được làm subtype; `record` kiểm soát cấu trúc state và API sinh tự động**, không phải phép bảo chứng an toàn dữ liệu tùy ý.

## 11. Generic sealed interface + generic record

Kết hợp sealed và record không chỉ dùng cho kiểu không có tham số. Một mô hình phản hồi tổng quát:

```java
sealed interface Result<T> permits Ok, Failure { }

record Ok<T>(T value) implements Result<T> { }

record Failure<T>(String reason) implements Result<T> { }
```

Đây là một tập biến thể đóng `Ok` hoặc `Failure`, trong khi kiểu giá trị thành công vẫn tổng quát theo `T`.

Với `Result<String>`, Java 21 có thể suy luận type argument trong record pattern:

```java
static String display(Result<String> result) {
    return switch (result) {
        case Ok(var value) -> "ok:" + value.toUpperCase();
        case Failure(var reason) -> "error:" + reason;
    };
}
```

`Ok(var value)` được suy luận theo ngữ cảnh kiểu `Result<String>`; `value` có kiểu tĩnh `String` nên `toUpperCase()` hợp lệ. Không cần thêm `default` khi hai biến thể bao phủ hierarchy generic thích hợp.

**Giới hạn cần hiểu đúng:**

- Generic parameter `T` không tự được lưu đầy đủ tại runtime do **type erasure**.
- Kiểu tĩnh của selector rất quan trọng. Nếu selector chỉ là `Object` từ dữ liệu không tin cậy, không được mặc nhiên dùng record pattern generic để khẳng định `T == String`.
- `record Ok<T>` không tự kiểm tra `value != null`. Ví dụ `new Ok<String>(null)` vẫn có thể được tạo; `display` trên sẽ ném NPE tại `value.toUpperCase()`. Nếu null không hợp lệ, khai báo constructor kiểm tra ngay tại record.
- Không cần generic hóa mọi hierarchy; chỉ thêm `T` khi nó biểu đạt quan hệ kiểu hữu ích cho người gọi.

### Ví dụ generic tối giản chạy độc lập

Tạo tệp `GenericResultDemo.java`:

```java
public class GenericResultDemo {
    sealed interface Result<T> permits Ok, Failure {}
    record Ok<T>(T value) implements Result<T> {}
    record Failure<T>(String reason) implements Result<T> {}

    static String display(Result<String> result) {
        return switch (result) {
            case Ok(var value) -> "ok:" + value.toUpperCase();
            case Failure(var reason) -> "error:" + reason;
        };
    }

    public static void main(String[] args) {
        System.out.println(display(new Ok<>("ok")));
        System.out.println(display(new Failure<String>("unavailable")));
    }
}
```

Biên dịch/chạy bằng JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 GenericResultDemo.java
java GenericResultDemo
```

Kết quả:

```text
ok:OK
error:unavailable
```

Đây là ví dụ cho khả năng kết hợp **tập biến thể đóng** với **generic result type**, trong đó pattern matching sử dụng thông tin compile-time đúng cách.

## 12. Chương trình hoàn chỉnh: cây biểu thức sealed + record

Tạo tệp **`SealedRecordPatternsDemo.java`**. Chương trình có constructor xác thực invariant, switch exhaustive, record pattern, guard và xử lý null tại ranh giới `Object`:

```java
public class SealedRecordPatternsDemo {
    sealed interface Expr permits Num, Sum, Neg {}

    record Num(int value) implements Expr {}

    record Sum(Expr left, Expr right) implements Expr {
        Sum {
            java.util.Objects.requireNonNull(left, "left");
            java.util.Objects.requireNonNull(right, "right");
        }
    }

    record Neg(Expr inner) implements Expr {
        Neg {
            java.util.Objects.requireNonNull(inner, "inner");
        }
    }

    static int eval(Expr expr) {
        return switch (expr) {
            case Num(int n) -> n;
            case Sum(Expr left, Expr right) ->
                    Math.addExact(eval(left), eval(right));
            case Neg(Expr inner) ->
                    Math.negateExact(eval(inner));
        };
    }

    static String describe(Expr expr) {
        return switch (expr) {
            case Num(int n) when n < 0 -> "negative literal:" + n;
            case Num(int n) -> "literal:" + n;
            case Sum(Expr left, Expr right) ->
                    "sum(" + describe(left) + "," + describe(right) + ")";
            case Neg(Expr inner) ->
                    "neg(" + describe(inner) + ")";
        };
    }

    static String inspect(Object candidate) {
        return switch (candidate) {
            case null -> "missing";
            case Expr expr -> "expr:" + describe(expr);
            default -> "not-expr";
        };
    }

    public static void main(String[] args) {
        Expr tree = new Sum(new Num(3), new Neg(new Num(5)));

        System.out.println(describe(tree));
        System.out.println("eval=" + eval(tree));
        System.out.println(describe(new Num(-2)));

        System.out.println(inspect(null));
        System.out.println(inspect(new Num(7)));
        System.out.println(inspect("other"));

        try {
            new Sum(null, new Num(1));
        } catch (NullPointerException e) {
            System.out.println("invalid:" + e.getMessage());
        }

        try {
            eval(null);
        } catch (NullPointerException e) {
            System.out.println("eval-null:NPE");
        }
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac --release 21 -encoding UTF-8 SealedRecordPatternsDemo.java
java SealedRecordPatternsDemo
```

Kết quả:

```text
sum(literal:3,neg(literal:5))
eval=-2
negative literal:-2
missing
expr:literal:7
not-expr
invalid:left
eval-null:NPE
```

### Đọc kết quả và cách các tính năng phối hợp

1. `tree` là `Sum(Num(3), Neg(Num(5)))`. Mỗi node là một record trong sealed hierarchy `Expr`.
2. `describe` phân rã từng record theo nhãn: `Sum` có hai vế, `Neg` có một biểu thức con, `Num` có số nguyên.
3. `eval` tính `3 + (-5)`, trả **`-2`**. Compiler chấp nhận biểu thức không có default vì mọi biến thể `Num`, `Sum`, `Neg` đều được bao phủ.
4. Với `Num(-2)`, guard `when n < 0` chọn nhãn chuyên biệt; nếu guard sai, nhãn `Num(int n)` tiếp theo sẽ xử lý.
5. `inspect(null)` trả `missing` vì có `case null`. `inspect(new Num(7))` khớp type pattern `Expr expr`; `inspect("other")` đi vào `default` vì selector kiểu `Object` nhận được những giá trị không thuộc `Expr`.
6. `new Sum(null, new Num(1))` bị constructor chặn trước khi trở thành một node hợp lệ. Mã bắt NPE và in tên component `left`.
7. `eval(null)` không có `case null` nên dù exhaustive về các subtype, nó vẫn ném NPE. Đây là chính sách thể hiện rằng `eval` nhận một `Expr` hợp lệ khác null; với API công khai có thể thêm `Objects.requireNonNull` để có thông báo chủ động.

**Giới hạn chương trình:** mã dùng đệ quy; cây rất sâu có thể làm tràn stack. `Math.addExact` và `Math.negateExact` cũng có thể ném `ArithmeticException` khi tràn số. Đây là những giới hạn thuật toán độc lập với exhaustiveness của `switch`.

## 13. Thay đổi mô hình: compiler giúp phát hiện chỗ còn thiếu

Giả sử mô hình mở rộng thêm phép nhân:

```java
record Mul(Expr left, Expr right) implements Expr { }
```

Với sealed interface đang khai báo `permits Num, Sum, Neg`, không thể chỉ thêm dòng record trên: **`Mul` chưa nằm trong danh sách được phép**. Phải đổi hierarchy:

```java
sealed interface Expr permits Num, Sum, Neg, Mul { }
```

Đây là ví dụ minh họa **một thay đổi trên mô hình đầy đủ**, không phải mã biên dịch độc lập; đồng thời cần khai báo `Mul` và giữ tất cả subtype liên quan.

Khi biên dịch lại `eval` và `describe` trên sealed hierarchy mới, những `switch` exhaustive nhưng chưa có `case Mul(...)` sẽ bị compiler yêu cầu cập nhật. Đó là lợi ích quan trọng của **không viết default bừa bãi** cho hierarchy đóng.

Một lựa chọn gây mất tín hiệu:

```java
// Trong một switch có các case Num/Sum/Neg:
default -> throw new IllegalArgumentException("unexpected expression");
```

Nếu luôn có default, compiler có thể xem switch đã exhaustive và không buộc thêm nhánh Mul. Runtime mới phát hiện trường hợp Mul khi chạy. Với tập biến thể do ứng dụng quản lý, muốn hỗ trợ subtype mới một cách đầy đủ thì **ưu tiên không có default** và để compiler chỉ ra các chỗ phải sửa.

### Binary compatibility và `MatchException`

Nếu một module chứa `switch` được biên dịch với hierarchy cũ, rồi tại runtime nó nhận một subtype được bổ sung trong module khác mà **không biên dịch lại switch**, một switch exhaustive lúc compile time vẫn có thể không tìm thấy nhãn khớp. Java 21 có thể ném **`MatchException`**.

Điểm thực hành: khi phát hành thay đổi đối với enum/sealed hierarchy, **recompile các module phụ thuộc và chạy kiểm thử tương thích**. Lỗi runtime này không phải lý do để luôn thêm `default` im lặng; đó là dấu hiệu cần quản lý phiên bản triển khai.

## 14. Mô hình nào phù hợp? So sánh với các cách khác

### Sealed interface + record

Dùng khi có **số biến thể hữu hạn, khác nhau về dữ liệu, nhưng cùng một khái niệm nghiệp vụ**: các loại event, command, result, biểu thức AST, phương thức thanh toán, trạng thái trả về.

Ưu điểm: API tự diễn đạt tập trạng thái hợp lệ, ít boilerplate, pattern matching/exhaustiveness có ích. Chi phí: thêm biến thể mới có thể buộc sửa nhiều `switch`, điều này là **chủ đích** nếu mọi hành vi phải cập nhật.

### Enum + trường dữ liệu

`enum` rất phù hợp nếu tập trạng thái chủ yếu là các **giá trị không có payload riêng theo từng variant**, ví dụ `NEW`, `DONE`, `FAILED`. Nếu `FAILED` cần chuỗi lỗi còn `DONE` cần timestamp khác kiểu, sealed record thường cho biểu diễn rõ hơn là enum kết hợp nhiều trường `nullable`.

### Interface/class mở rộng bình thường

Dùng khi bên ngoài cần tạo các hiện thực mới theo hợp đồng plugin/SPI. `sealed` có thể gây hạn chế sai về yêu cầu mở rộng. Nếu cần extension bên ngoài, cân nhắc interface thường, hoặc một nhánh `non-sealed` **có chủ đích** để mở rộng.

### Đa hình qua method thay vì nhiều `switch`

Nếu một hành vi gắn tự nhiên với từng variant và không thường xuyên thêm nhiều phép toán mới, có thể khai báo một method trên interface rồi để từng record triển khai, ví dụ `int eval()`. Cách này giảm `switch` rải rác.

Ngược lại, với AST cần nhiều thao tác độc lập (`eval`, `format`, `optimize`, `serialize`), một mô hình sealed record kèm các bộ phân loại exhaustive là lựa chọn rõ ràng. Không có quy tắc “sealed record luôn tốt hơn đa hình”; đây là sự đánh đổi giữa **mở rộng tập subtype** và **mở rộng tập thao tác**.

## 15. Lỗi biên dịch và lỗi mô hình thường gặp

### 15.1. Record không được mở rộng một class

```java
// KHÔNG BIÊN DỊCH:
// sealed abstract class Root permits Child {}
// record Child(int x) extends Root {}
```

Record kế thừa `java.lang.Record` và không có `extends` trong cú pháp. Dùng `sealed interface` nếu muốn record implement trực tiếp.

### 15.2. Record không thể khai báo `non-sealed` hoặc `sealed`

```java
// KHÔNG BIÊN DỊCH:
// non-sealed record Num(int value) implements Expr {}
```

Record đã implicitly final. Không thể cho người dùng tạo subclass từ record, kể cả khi record là một subtype trong sealed hierarchy.

### 15.3. Quên `permits` hoặc định nghĩa subtype ngoài danh sách

```java
// Giả sử sealed interface Expr permits Num, Sum, Neg;
// KHÔNG BIÊN DỊCH khi thêm trực tiếp:
// record Mul(Expr left, Expr right) implements Expr {}
```

Hãy thay đổi danh sách permitted subtype ở đúng nơi định nghĩa sealed type và kiểm tra module/package theo JLS.

### 15.4. Không có nhánh cho subtype mới

Nếu cập nhật `permits` để thêm subtype mới nhưng `switch` expression không có nhánh tương ứng và không có case tổng quát, compiler báo không exhaustive. Đây là tín hiệu cần **cập nhật hành vi**, không phải lỗi nên che ngay bằng `default -> null`.

### 15.5. Đặt nhánh tổng quát trước nhánh chuyên biệt

```java
// KHÔNG BIÊN DỊCH:
static String invalid(Expr expr) {
    return switch (expr) {
        case Expr e -> "any expression";
        case Num(int n) -> "number"; // Bị nhãn Expr phía trước dominate.
    };
}
```

Nhãn `Expr e` không guard đã bao phủ mọi `Expr` khác null. Đặt pattern cụ thể trước nếu cần, hoặc chỉ giữ nhánh tổng quát khi không cần phân loại subtype.

### 15.6. Dùng record pattern nhưng không xét component

Nhánh `Sum(Num(int a), Num(int b))` chỉ khớp Sum có hai Num; nó **không xử lý tất cả Sum**. Nếu chỉ có nhánh lồng rất cụ thể mà thiếu `Sum(Expr left, Expr right)` tổng quát, compiler có thể xem switch chưa exhaustive.

### 15.7. Cho rằng record tự cấm null hoặc giá trị sai

Constructor mặc định của `record Sum(Expr left, Expr right)` không tự từ chối `null`. Nếu null vi phạm bất biến, thêm compact canonical constructor và test lỗi.

### 15.8. Nhầm exhaustiveness với null handling

Dù `switch` trên `Expr` đã bao phủ Num/Sum/Neg, selector null vẫn gây NPE nếu không có `case null`. Quy định rõ đầu vào null là hợp lệ hay không và thực thi nhất quán.

### 15.9. Dùng record cho state có tài nguyên mutable phức tạp mà không cân nhắc

Một record chứa `List`, `Map` hay buffer mutable không tự deep-copy. Nếu tính bất biến quan trọng, dùng defensive copy hoặc loại đối tượng phù hợp hơn.

### 15.10. Nhầm tính đóng trực tiếp với tính đóng toàn bộ cây

Sealed type có thể cho phép `non-sealed` subtype, mở cây bên dưới nhánh đó. Muốn toàn bộ biến thể là những record cụ thể hữu hạn, hãy để các biến thể trực tiếp là record implicitly final hoặc final class phù hợp.

## 16. Bài tập có đáp án

**Bài tập 1 — chuyển thiết kế tag sang sealed record**

Bạn có một lớp giao dịch với `kind` bằng chuỗi `"CASH"`/`"CARD"` và các trường `amount`, `token` thường xuyên null. Hãy mô hình hóa hai biến thể mà không dùng tag string.

**Đáp án tham khảo:**

```java
sealed interface Payment permits Cash, Card {}
record Cash(int amount) implements Payment {}
record Card(String token) implements Payment {}
```

Sau đó viết switch exhaustive theo type/record pattern. Có thể thêm validation cho amount/token theo yêu cầu nghiệp vụ.

**Bài tập 2 — exhaustive**

Với `Expr` gồm `Num`, `Sum`, `Neg`, tại sao một switch trên tham số `Expr` chỉ có ba nhánh record pattern tương ứng không cần default, còn switch trên tham số `Object` cần thêm nhánh bao phủ các kiểu khác?

**Đáp án:** Kiểu tĩnh `Expr` là sealed hierarchy có tập subtype được phép, compiler biết mức bao phủ từ `permits`. `Object` là kiểu mở và có nhiều giá trị không phải Expr.

**Bài tập 3 — record lồng**

Với `new Sum(new Num(1), new Neg(new Num(2)))`, nhánh nào khớp?

```java
case Sum(Num(int a), Num(int b)) -> "two-nums";
case Sum(Expr left, Expr right) -> "other-sum";
```

**Đáp án:** Nhánh `other-sum`, vì vế phải là `Neg`, không phải `Num`.

**Bài tập 4 — null**

Có thể tạo `new Sum(null, new Num(1))` nếu record Sum không khai báo constructor kiểm tra không? `case null` của switch trên Expr có bắt đối tượng Sum đó không?

**Đáp án:** Constructor mặc định cho phép component null; `case null` chỉ bắt **selector null**, không bắt một record khác null với component null. Hãy xác thực non-null khi tạo record nếu đó là bất biến.

**Bài tập 5 — generic**

Với `Result<String>` gồm hai generic record `Ok<T>` và `Failure<T>`, vì sao `case Ok(var value)` có thể cho `value` kiểu String mà không cần `Class<String>` runtime token?

**Đáp án:** Kiểu tĩnh `Result<String>` và generic record pattern inference của Java 21 cho compiler thông tin để suy ra kiểu. Đây không phải bằng chứng runtime rằng mọi dữ liệu không đáng tin từ `Object` có thể tự chuyển thành Result<String>.

**Bài tập 6 — thêm subtype**

Nếu thêm `Mul` vào danh sách `permits` rồi recompile, điều gì giúp bạn tìm các xử lý còn thiếu? Tại sao thêm `default -> "unknown"` vào tất cả switch có thể là lựa chọn tệ?

**Đáp án:** Compiler có thể báo các switch expression chưa exhaustive. Default tổng quát có thể che thay đổi yêu cầu xử lý subtype mới, dẫn tới kết quả nghiệp vụ sai.

**Bài tập 7 — chọn đa hình hay switch**

Một mô hình chỉ có hành vi tính giá trị của từng node nhưng liên tục được bổ sung nhiều loại node mới. Có nên đặt method `eval()` trên interface và triển khai ở mỗi record không?

**Đáp án:** Có thể, nếu mỗi biến thể tự sở hữu hành vi và thay đổi thường là thêm subtype. Nếu nhu cầu là nhiều thao tác độc lập trên tập subtype đóng, sealed record + switch exhaustive thường thuận lợi hơn. Quyết định dựa trên chiều mở rộng của ứng dụng.

## 17. Checklist trước khi đưa mô hình vào production

1. **Tập biến thể đã biết và do cùng nhóm kiểm soát?** Nếu không, sealed có thể quá chặt.
2. **Các biến thể đều mang payload nhỏ, mô tả bằng component?** Record là ứng viên tốt.
3. **Record có cần extends class khác ngoài Record?** Nếu có, record không phù hợp; xem xét class thường.
4. **Danh sách `permits` đúng subtype trực tiếp và đúng ràng buộc module/package?**
5. **Mỗi permitted subtype đã chọn final/sealed/non-sealed phù hợp?** Record implicitly final.
6. **Có component nào cần kiểm tra non-null, giới hạn số, defensive copy?** Viết constructor.
7. **Switch đang nhận kiểu cha sealed hay Object?** Câu trả lời quyết định việc compiler có thể giúp kiểm tra exhaustiveness đến đâu.
8. **Đã tách case null và xử lý null component rõ ràng?**
9. **Có guard nào cần nhãn không guard để bao phủ phần còn lại?**
10. **Có default đang che việc thêm subtype mới?** Nếu mọi biến thể phải được xử lý riêng, cân nhắc loại bỏ.
11. **Các record pattern có quá sâu hoặc quá khó đọc không?** Nếu có, dùng type pattern/accessor hoặc helper.
12. **Đã test mọi biến thể, lỗi constructor, null và thay đổi hierarchy?** Quản lý recompile các module phụ thuộc để tránh mismatch runtime.

**Kết luận:** sự kết hợp `sealed interface` + `record` tạo mô hình Java mạnh cho một tập biến thể hữu hạn có dữ liệu khác nhau. `sealed` đưa **giới hạn subtype** vào hệ thống kiểu; `record` đưa **cấu trúc dữ liệu** vào khai báo; Java 21 record pattern và exhaustive `switch` cho phép xử lý đủ từng biến thể với ít boilerplate, đồng thời buộc nhóm phát triển xem xét sự thay đổi của mô hình.

## Tài liệu tham khảo chính thức

- [JLS Java SE 21 `9.1 — Interface Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1): sealed interface, permitted direct implementations và quy tắc khai báo.
- [JLS Java SE 21 `8.1.1.2 — sealed, non-sealed, final Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2): trạng thái đóng/mở của các lớp trong hierarchy.
- [JLS Java SE 21 `8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.6): permits, same module/package và subtype trực tiếp.
- [JLS Java SE 21 `8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10): component, implicit final, canonical constructor và thành viên tự sinh.
- [JLS Java SE 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type pattern, record pattern, matching và pattern properties.
- [JLS Java SE 21 `14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): kiểm tra exhaustive trên sealed hierarchy.
- [JLS Java SE 21 `18.5.5 — Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5): suy luận generic record pattern.
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): ví dụ sealed coverage, record patterns và thay đổi hierarchy giữa compile/runtime.
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): phân rã record và các lưu ý về null.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
