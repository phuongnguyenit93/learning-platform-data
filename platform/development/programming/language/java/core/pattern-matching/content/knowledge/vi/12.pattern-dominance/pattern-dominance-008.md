# Sắp xếp case theo độ đặc hiệu trong Java pattern matching

## 1. Vì sao thứ tự case quyết định chương trình có đúng hay không?

Khi viết `switch` với pattern matching trong Java 21, nhiều nhãn `case` có thể cùng khớp **một giá trị**. Ví dụ, chuỗi `"Java"` vừa là `String`, vừa là `CharSequence`, vừa là `Object`. Số nguyên `Integer 8` vừa là `Integer`, vừa là `Number`, vừa là `Object`.

Nếu dùng các nhãn theo thứ tự không hợp lý:

~~~java
switch (value) {
    case Number n -> System.out.println("Number");
    case Integer i -> System.out.println("Integer"); // LỖI dominance
    default -> System.out.println("Other");
}
~~~

compiler từ chối vì mọi `Integer` đã bị `case Number n` trước đó khớp. Nhãn `Integer` không thể được chọn. Hiện tượng một nhãn trước bao trùm một nhãn sau như vậy gọi là **dominance**.

Trọng tâm bài này là **sắp xếp các case từ đặc hiệu đến tổng quát** để chương trình vừa biên dịch được vừa thể hiện đúng ý định nghiệp vụ. Với Java 21, có thể ghi nhớ:

> **Hằng cụ thể → pattern có guard cụ thể → pattern không guard theo thứ bậc kiểu từ con đến cha → fallback bao quát.** Xử lý `null` rõ ràng khi cần.

Đây là **quy tắc tổ chức dễ đọc**, không phải một thuật toán tự động phân loại “độ đặc hiệu” của mọi biểu thức Java. Đặc biệt, compiler không luôn chứng minh được tính bao hàm của hai guard động; mã có thể **biên dịch nhưng chạy vào nhánh ngoài dự định**.

Sau bài này bạn sẽ:

- Phân biệt **thứ tự chọn case lúc chạy** với **dominance được kiểm tra khi biên dịch**.
- Xếp đúng subtype trước supertype/interface rộng, nhãn hằng trước type pattern, nhãn có `when` trước nhãn chung.
- Hiểu vì sao `case Number n when n > 0` không tự động làm `case Integer i` phía sau bị dominated.
- Nhận biết trường hợp một guard động “bắt mất” giá trị của một nhãn hằng phía sau dù compiler vẫn cho phép.
- Sắp xếp record patterns, sealed hierarchy, xử lý `null` và `default`.
- Viết và kiểm thử mã Java 21 để phòng lỗi ordering và lỗi logic.

**Phiên bản:** pattern matching for `switch` và record patterns ổn định từ **Java 21**. Tất cả chương trình đầy đủ trong bài dùng `javac --release 21` và không cần bật preview.

## 2. Hai câu hỏi riêng: matching order và dominance

### 2.1. Matching order: Java thử các nhãn như thế nào?

Java chọn case phù hợp theo quy tắc của switch block; các pattern label được kiểm tra theo thứ tự xuất hiện. Với một nhãn có guard:

~~~java
case String s when s.length() > 4 -> "LONG";
~~~

Java chỉ đánh giá `s.length() > 4` **sau khi** giá trị selector khớp `String s`. Nếu guard trả `false`, Java có thể thử nhãn phù hợp tiếp theo. Một rule mũi tên `->` được chọn thì không fall-through sang rule khác.

Ví dụ hợp lý:

~~~java
case String s when s.isBlank() -> "BLANK";
case String s -> "TEXT";
~~~

Một chuỗi blank được nhãn đầu xử lý; chuỗi còn lại được nhãn sau xử lý.

### 2.2. Dominance: compiler loại bỏ nhãn không thể được chọn

Một nhãn `case` ở sau bị **dominated** nếu theo các quy tắc dominance của Java, một nhãn phía trước đã bao trùm trường hợp của nó. Khi đó compiler báo lỗi, thường có thông điệp:

~~~text
error: this case label is dominated by a preceding case label
~~~

Ví dụ `case CharSequence cs` trước `case String s` là sai vì mọi `String` đều thực thi interface `CharSequence`.

Dominance là **quy tắc ngôn ngữ kiểm tra tại compile time**; nó không phải kết quả của việc chạy thử vài giá trị. Ngược lại, có những miền điều kiện phức tạp của guard mà compiler không chứng minh bao hàm được. Code hợp lệ vẫn có thể chọn một nhánh rộng trước nhánh đặc biệt phía sau.

### 2.3. “Đặc hiệu” là chiến lược viết mã, không phải ưu tiên tự động

Java **không tự động xếp case từ kiểu con đến kiểu cha** cho bạn. Người viết đặt thứ tự các nhãn. Nếu định nghĩa nghiệp vụ yêu cầu “số nguyên dương trước, các số nguyên còn lại sau, số thực sau nữa”, bạn phải đưa các case vào đúng thứ tự đó.

Không nên hiểu rằng Java sẽ tự chọn case “đúng nhất” theo cảm giác. Một `case Number n` đứng trước vẫn có thể chặn `case Integer i`, dẫn đến lỗi dominance, thay vì Java tự ưu tiên `Integer`.

## 3. Công thức sắp xếp thực dụng

Khi các nhãn có thể chồng lấn, áp dụng thứ tự tham khảo:

1. **Giá trị hằng cần xử lý riêng:** `case 1`, `case "OK"`, enum constant, nếu thích hợp với kiểu selector.
2. **Pattern có guard đặc thù:** `case String s when s.isBlank()`, `case Integer n when n > 0`.
3. **Pattern kiểu con/record cụ thể không guard:** `case Integer n`, `case String s`, `case Circle(int radius)`.
4. **Pattern kiểu cha/interface rộng hơn:** `case Number n`, `case CharSequence cs`, `case Shape s`.
5. **Fallback bao quát:** `case Object o` hoặc `default` khi hợp lệ và cần thiết.

`case null` không nằm trong một cây subtype thông thường. Type pattern như `String s` hay `Object o` không khớp `null`; nên xử lý `null` một cách tường minh, thường đặt ở đầu switch cho dễ đọc. Không hiểu “đặt null đầu” như một yêu cầu bắt buộc của cú pháp.

**Điều kiện quan trọng:** thứ tự trên chỉ là khung ban đầu. Ví dụ, `String` không phải subtype của `Number`; hai case này không bao trùm nhau, nên có thể đặt theo mục đích phân loại. Khi quan hệ kiểu hoặc guard làm các nhánh giao nhau, hãy kiểm tra cụ thể bằng compiler và test runtime.

## 4. Subtype trước supertype: quy tắc quan trọng nhất

Xét quan hệ:

~~~text
Object
├── Number
│   ├── Integer
│   ├── Long
│   └── Double
└── CharSequence (interface)
    ├── String
    └── StringBuilder
~~~

Sơ đồ chỉ mô tả các mối quan hệ kế thừa/triển khai liên quan; `StringBuilder` không phải subclass của `String` mà cả hai cùng triển khai `CharSequence`.

Hai thứ tự **sai**:

~~~java
case Number n -> "NUMBER";
case Integer i -> "INTEGER"; // Bị Number bao trùm
~~~

~~~java
case CharSequence cs -> "SEQUENCE";
case String s -> "STRING"; // Bị CharSequence bao trùm
~~~

Đây là các đoạn nhãn minh họa **cố ý không biên dịch**.

Thứ tự đúng:

~~~java
case Integer i -> "INTEGER";
case Number n -> "NUMBER";
~~~

~~~java
case String s -> "STRING";
case CharSequence cs -> "SEQUENCE";
~~~

Với `value = Integer.valueOf(10)`, case `Integer` được chọn. Với `value = Double.valueOf(2.5)`, `Integer` không khớp và case `Number` được chọn.

**Độ đặc hiệu theo quan hệ kiểu** khác với độ dài tên lớp hay thứ tự khai báo trong code. Muốn phân tích, hãy hỏi: “Mọi đối tượng khớp pattern B có chắc khớp pattern A không?” Nếu A đứng trước B và luôn bao phủ B, thứ tự thường sai.

Cũng cần xét interface và record: một class có thể thực thi nhiều interface không có quan hệ cha–con, nên không phải hai nhãn interface bất kỳ cũng bị dominance với nhau. Khi không có quan hệ bao hàm, thứ tự vẫn có thể ảnh hưởng hành vi đối với một lớp triển khai **cả hai** interface. Đây là quyết định nghiệp vụ cần test, không phải lúc nào cũng là lỗi compile-time.

## 5. Cùng một kiểu: guard cụ thể trước pattern không guard

Khi nhiều case cùng dùng `String s`, những điều kiện riêng phải đứng trước nhánh chung:

~~~java
case String s when s.isBlank() -> "BLANK";
case String s when s.length() >= 5 -> "LONG";
case String s -> "OTHER_STRING";
~~~

- Một chuỗi chỉ có khoảng trắng khớp guard `isBlank()` trước.
- Một chuỗi không blank, có đủ 5 ký tự có thể khớp nhánh `LONG`.
- Những chuỗi khác đi tới `case String s` không guard.

Đảo ngược như sau là **lỗi biên dịch**:

~~~java
case String s -> "STRING";
case String s when s.isBlank() -> "BLANK"; // Dominated
~~~

Nhãn không guard bắt được tất cả đối tượng `String` nên nhãn có guard phía sau không bao giờ được chọn.

Điểm tinh tế là hai guard động không nhất thiết có quan hệ bao hàm rõ ràng để compiler kiểm tra. Ví dụ:

~~~java
case String s when s.length() >= 3 -> "AT_LEAST_THREE";
case String s when s.startsWith("A") -> "STARTS_A";
case String s -> "OTHER";
~~~

Đây là cú pháp hợp lệ về nguyên tắc trong một switch tương ứng, nhưng chuỗi `"Alice"` sẽ đi vào case độ dài trước, **không** tới case `startsWith("A")`. Nếu nghiệp vụ muốn ưu tiên tiền tố `A`, phải đổi thứ tự hai guard. Cách kiểm tra đúng là viết test cho giá trị thuộc **giao của hai điều kiện**, không chỉ giá trị khớp một guard.

## 6. Chương trình tổng hợp: pattern đặc hiệu trước, tổng quát sau

Lưu thành `SpecificityOrderDemo.java`:

~~~java
public class SpecificityOrderDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "BLANK";
            case String s when s.length() >= 5 -> "LONG_TEXT:" + s;
            case String s -> "TEXT:" + s;
            case Integer n when n > 0 -> "POS_INT:" + n;
            case Integer n -> "INT:" + n;
            case Number n -> "NUMBER:" + n;
            case CharSequence cs -> "CHAR_SEQUENCE:" + cs.length();
            case Object o -> "OBJECT";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify("   "));
        System.out.println(classify("Java!"));
        System.out.println(classify("Hi"));
        System.out.println(classify(8));
        System.out.println(classify(-2));
        System.out.println(classify(2.5));
        System.out.println(classify(new StringBuilder("abc")));
        System.out.println(classify(new Object()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 21 SpecificityOrderDemo.java
java SpecificityOrderDemo
~~~

Kết quả chính xác:

~~~text
NULL
BLANK
LONG_TEXT:Java!
TEXT:Hi
POS_INT:8
INT:-2
NUMBER:2.5
CHAR_SEQUENCE:3
OBJECT
~~~

Đọc thứ tự của các case:

| Giá trị | Case được chọn | Lý do |
| --- | --- | --- |
| `null` | `case null` | Type pattern không khớp null |
| `"   "` | `String s when s.isBlank()` | Điều kiện đặc biệt đứng đầu trong nhóm String |
| `"Java!"` | `String s when s.length() >= 5` | Guard blank sai, guard độ dài đúng |
| `"Hi"` | `String s` | Hai guard String đều sai |
| `8` | `Integer n when n > 0` | Nhánh Integer dương trước Integer chung |
| `-2` | `Integer n` | Guard số dương sai |
| `2.5` | `Number n` | Đây là Double, không phải Integer |
| `new StringBuilder("abc")` | `CharSequence cs` | Không phải String, nhưng triển khai CharSequence |
| `new Object()` | `Object o` | Không khớp các nhãn trước |

Hai ý cần phân biệt:

- `case Number n` rộng hơn `case Integer n`, nên phải đứng **sau** các case Integer nếu muốn xử lý riêng.
- `case CharSequence cs` rộng hơn `case String s`, nên phải đứng sau các case String. Thứ tự giữa `Number` và `CharSequence` ở ví dụ này không gây dominance vì hai nhánh không có quan hệ bao hàm trực tiếp.

**Tính exhaustive:** `case Object o` là pattern bao phủ mọi giá trị **Object không null** của selector; `case null` xử lý giá trị null. Do đó ví dụ không cần thêm `default`. Đừng thêm nhãn `default` dư thừa sau pattern tổng quát `Object o` nếu compiler xác định nó đã bao trùm mọi trường hợp còn lại.

## 7. Hằng cụ thể trước guarded pattern: cả lỗi compile và lỗi logic

### 7.1. Pattern chung có thể dominate hằng

Giả sử selector là `String`:

~~~java
case String s -> "ANY_STRING";
case "OK" -> "EXACT"; // LỖI dominance
~~~

Nhãn `case String s` không guard đã khớp mọi chuỗi không null, bao gồm `"OK"`. Vì thế `case "OK"` phía sau bị dominated.

Viết đúng:

~~~java
case "OK" -> "EXACT";
case String s -> "ANY_STRING";
~~~

### 7.2. Guard động không nhất thiết dominate một hằng theo luật compiler

Khác với nhãn không guard, một nhãn:

~~~java
case Integer i when i > 0 -> "POSITIVE";
~~~

có biểu thức điều kiện động `i > 0`. Phần lớn guard động **không được xem là dominance vô điều kiện** với một nhãn hằng phía sau. Vì vậy đoạn:

~~~java
case Integer i when i > 0 -> "POSITIVE";
case 1 -> "ONE";
case Integer i -> "OTHER";
~~~

có thể **biên dịch**, nhưng với giá trị `1`, guard đầu đã đúng và nhãn `case 1` **không được chọn**. Đây là **lỗi logic về thứ tự**, không phải lỗi dominance được compiler phát hiện.

Nguyên tắc an toàn từ tài liệu Oracle: **hằng cụ thể trước, guarded pattern sau, unguarded pattern cuối**. Nếu ưu tiên nghiệp vụ của bạn thực sự khác, phải thể hiện có chủ đích và test rõ.

### 7.3. Chương trình kiểm chứng

Lưu thành `ConstantGuardOrderDemo.java`:

~~~java
public class ConstantGuardOrderDemo {
    static String good(Integer value) {
        return switch (value) {
            case 1 -> "ONE";
            case -1 -> "MINUS_ONE";
            case Integer i when i > 0 -> "POSITIVE";
            case Integer i -> "OTHER_INTEGER";
            case null -> "NULL";
        };
    }

    static String legalButSurprising(Integer value) {
        return switch (value) {
            case Integer i when i > 0 -> "POSITIVE";
            case 1 -> "ONE";
            case Integer i -> "OTHER_INTEGER";
            case null -> "NULL";
        };
    }

    public static void main(String[] args) {
        System.out.println("good(1)=" + good(1));
        System.out.println("good(2)=" + good(2));
        System.out.println("good(-1)=" + good(-1));
        System.out.println("good(0)=" + good(0));
        System.out.println("good(null)=" + good(null));
        System.out.println("surprising(1)=" + legalButSurprising(1));
    }
}
~~~

~~~bash
javac --release 21 ConstantGuardOrderDemo.java
java ConstantGuardOrderDemo
~~~

Kết quả:

~~~text
good(1)=ONE
good(2)=POSITIVE
good(-1)=MINUS_ONE
good(0)=OTHER_INTEGER
good(null)=NULL
surprising(1)=POSITIVE
~~~

Phương thức `good` ưu tiên hai giá trị hằng `1` và `-1` trước guard số dương, sau đó mới tới các số nguyên khác. Phương thức `legalButSurprising` cho thấy nhãn `case 1` có thể bị bỏ qua **tại runtime**, dù trình biên dịch không báo dominance.

**Ngoại lệ cần nhớ:** guard là constant expression `true` được JLS Java 21 xem như **unguarded** cho quy tắc dominance. Nếu viết `case Integer i when true` trước `case 1`, compiler báo dominance; đây không phải là một guard động bình thường. Guard là constant expression `false` không được chấp nhận trong case label.

## 8. Guard rộng theo kiểu cha chưa chắc dominate pattern con

Một ví dụ thú vị:

~~~java
case Number n when n.intValue() > 0 -> "POSITIVE";
case Integer i -> "OTHER_INTEGER";
case Number n -> "OTHER_NUMBER";
~~~

Nhãn đầu sử dụng `Number` rộng, nhưng có guard động. Nếu guard sai, chương trình có thể đi tới nhãn `Integer` dù giá trị vẫn là một đối tượng `Integer`. Do đó Java **không mặc nhiên** từ chối thứ tự này bằng dominance như trường hợp `case Number n` không guard.

Chương trình đầy đủ `GuardDoesNotDominateDemo.java`:

~~~java
public class GuardDoesNotDominateDemo {
    static String classify(Number value) {
        return switch (value) {
            case Number n when n.intValue() > 0 -> "POSITIVE";
            case Integer n -> "OTHER_INTEGER";
            case Number n -> "OTHER_NUMBER";
            case null -> "NULL";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(3));
        System.out.println(classify(0));
        System.out.println(classify(-2.5));
        System.out.println(classify(7L));
        System.out.println(classify(null));
    }
}
~~~

~~~bash
javac --release 21 GuardDoesNotDominateDemo.java
java GuardDoesNotDominateDemo
~~~

Kết quả:

~~~text
POSITIVE
OTHER_INTEGER
OTHER_NUMBER
POSITIVE
NULL
~~~

Với `3`, nhãn `Number` có guard được chọn, dù phía sau có case `Integer`. Với `0`, guard sai và chương trình tới `case Integer n`. Đây là **quy tắc Java hợp lệ**, nhưng dễ gây bất ngờ.

Nếu mục tiêu của chương trình là phân loại **Integer trước các Number khác** bất kể giá trị dương/âm, hãy ưu tiên case Integer, hoặc đặt guard trên `Integer` riêng. Đừng trông chờ compiler đọc được ý định nghiệp vụ của bạn từ các biểu thức điều kiện.

Một số guard có thể ném ngoại lệ hoặc có side effect; đổi thứ tự case có thể thay đổi số lần guard được gọi. Khi refactor thứ tự, cần kiểm thử cả **giá trị kết quả** và **tác dụng phụ** nếu guard không thuần.

## 9. Record patterns và thứ tự từ điều kiện riêng đến tổng quát

Record pattern cho phép phân rã component ngay trong case:

~~~java
case Rectangle(int w, int h) when w == h -> "SQUARE";
case Rectangle(int w, int h) -> "RECTANGLE";
~~~

Cả hai nhãn đều nhận cùng kiểu `Rectangle`; guard `w == h` là điều kiện đặc thù, nên đứng trước record pattern không guard.

Nếu đảo:

~~~java
case Rectangle(int w, int h) -> "RECTANGLE";
case Rectangle(int w, int h) when w == h -> "SQUARE"; // LỖI
~~~

compiler từ chối nhãn thứ hai vì nó bị record pattern trước bao trùm.

### Chương trình record + sealed hierarchy

Lưu `RecordSpecificityDemo.java`:

~~~java
sealed interface Shape permits Circle, Rectangle {}
record Circle(int radius) implements Shape {}
record Rectangle(int width, int height) implements Shape {}

public class RecordSpecificityDemo {
    static String describe(Shape shape) {
        return switch (shape) {
            case Circle(int r) when r == 0 -> "POINT";
            case Circle(int r) when r > 0 -> "CIRCLE:" + r;
            case Circle(int r) -> "INVALID_CIRCLE:" + r;
            case Rectangle(int w, int h) when w == h -> "SQUARE:" + w;
            case Rectangle(int w, int h) -> "RECTANGLE:" + w + "x" + h;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Circle(0)));
        System.out.println(describe(new Circle(3)));
        System.out.println(describe(new Circle(-1)));
        System.out.println(describe(new Rectangle(4, 4)));
        System.out.println(describe(new Rectangle(4, 5)));
    }
}
~~~

~~~bash
javac --release 21 RecordSpecificityDemo.java
java RecordSpecificityDemo
~~~

Kết quả chính xác:

~~~text
POINT
CIRCLE:3
INVALID_CIRCLE:-1
SQUARE:4
RECTANGLE:4x5
~~~

Giải thích:

- `Circle(0)` đi tới record pattern có guard `r == 0`.
- `Circle(3)` đi tới guard `r > 0`.
- `Circle(-1)` không thỏa hai guard nhưng vẫn khớp `Circle(int r)` không guard.
- `Rectangle(4,4)` khớp guard `w == h`, được phân loại là square.
- `Rectangle(4,5)` đi tới case Rectangle chung.

`Shape` là sealed interface có hai implementation được phép, và các nhánh `Circle`/`Rectangle` không guard bao phủ chúng. Vì vậy switch expression **exhaustive** mà không cần `default`. Điều này không ngăn `describe(null)` ném `NullPointerException` do chưa có `case null`.

Nếu thêm `case Shape s` đứng trước các record pattern `Circle` và `Rectangle`, nó sẽ bao trùm các subtype đó và làm mất khả năng xử lý riêng. Với sealed types, thường xếp các nhánh subtype cụ thể trước nhánh interface/parent tổng quát nếu có.

## 10. Thứ tự nhãn hằng, interface, Object, null và default

### 10.1. Hằng trước type pattern bao quát

Đối với selector `String`, nếu có giá trị cần ưu tiên `"OK"` hoặc `"ERROR"`, đặt case hằng trước `case String s`. Đối với selector `Integer`, nếu số `0`, `1` có ý nghĩa riêng, đặt nhãn hằng trước pattern rộng tương ứng. Nếu thay bằng guard, phải quyết định rõ thứ tự giữa guard và hằng.

### 10.2. Interface không nhất thiết có quan hệ bao hàm nhau

`String` là subtype của `CharSequence`; do đó `CharSequence` trước `String` gây dominance. Nhưng nếu hai interface `Readable` và `AutoCloseable` không có quan hệ cha–con, một lớp có thể triển khai cả hai. Khi ấy thứ tự hai case interface có thể quyết định xử lý đối tượng đó, dù compiler không có một quan hệ subtype trực tiếp để coi một pattern bao trùm pattern còn lại.

Với các interface không liên quan, hãy đặt điều kiện nghiệp vụ được ưu tiên trước và bổ sung test cho đối tượng đồng thời triển khai cả hai interface.

### 10.3. Object pattern rất rộng

Với selector `Object`:

~~~java
case String s -> "STRING";
case Number n -> "NUMBER";
case Object o -> "OTHER_OBJECT";
~~~

`case Object o` ở cuối là một pattern tổng quát cho mọi object **không null** còn lại. Nếu đưa `case Object o` lên trước các case String/Number, compiler báo dominance. Trong một switch block đã có pattern tổng quát như vậy, tránh thêm nhãn chung trùng chức năng khiến compiler báo lỗi.

### 10.4. null là trường hợp riêng

`null` không phải subtype theo mô hình dispatch của type pattern. Java 21 cho phép:

~~~java
case null -> "NULL";
case String s -> "STRING";
default -> "OTHER";
~~~

**Đây là trích đoạn trong switch thích hợp**, không phải chương trình độc lập. `case null` nên được viết tường minh khi muốn nhận null. `default` đứng riêng không nhất thiết xử lý null: với pattern switch Java 21, switch trên null thường ném `NullPointerException` nếu không có nhãn null phù hợp.

Không cần ép `case null` phải ở đầu vì dominance; đặt ở đầu chỉ là lựa chọn làm code dễ hiểu.

### 10.5. default không phải công cụ sửa mọi lỗi ordering

`default` giúp bao phủ kiểu dữ liệu khác, nhưng **không sửa được** chuyện một nhãn cụ thể bị nhãn rộng đứng trước dominate. Ví dụ có `case Number n` trước `case Integer i` rồi thêm `default` ở cuối thì nhãn Integer vẫn bị compiler từ chối.

Khi sửa lỗi dominance, phải **đổi thứ tự hoặc thay đổi điều kiện/pattern** làm các nhãn chồng lấn, không chỉ thêm một nhánh dự phòng.

## 11. Danh sách lỗi dominance đã được compiler xác nhận

Các đoạn dưới **cố ý không biên dịch** với `javac --release 21`. Mỗi đoạn giả định được đặt trong switch có selector và kiểu kết quả phù hợp.

**Lỗi 1 — Number bao trùm Integer**

~~~java
case Number n -> "NUMBER";
case Integer i -> "INTEGER";
~~~

Mọi Integer là Number, nên `Integer` ở sau bị dominated.

**Lỗi 2 — CharSequence bao trùm String**

~~~java
case CharSequence cs -> "CHAR_SEQUENCE";
case String s -> "STRING";
~~~

Mọi String thực thi CharSequence, nên `String` ở sau bị dominated.

**Lỗi 3 — Pattern String chung đứng trước guard**

~~~java
case String s -> "STRING";
case String s when s.isBlank() -> "BLANK";
~~~

Case chung đã nhận mọi String, nên case có guard không thể được chọn.

**Lỗi 4 — Pattern String chung đứng trước hằng**

~~~java
case String s -> "ANY_STRING";
case "OK" -> "EXACT";
~~~

Hằng `"OK"` luôn là String và đã được pattern trước bắt.

**Lỗi 5 — Record pattern chung đứng trước record pattern có guard**

~~~java
case Metric(int n) -> "METRIC";
case Metric(int n) when n > 0 -> "POSITIVE";
~~~

Giả sử `record Metric(int value) {}`; case đầu đã nhận tất cả Metric. Nhãn sau bị dominated.

**Lỗi 6 — Object ở đầu**

~~~java
case Object o -> "OBJECT";
case String s -> "STRING";
~~~

`Object` đã nhận mọi String không null, nên nhãn String không thể được chọn.

**Lỗi 7 — Guard hằng true được coi như không guard**

~~~java
case Integer i when true -> "ALL";
case 1 -> "ONE";
~~~

Trong Java 21, `when true` là một guard hằng đúng, nhãn được xem là không guard cho dominance. Case `1` phía sau bị dominated.

Lỗi điển hình của `javac` ở các trường hợp này:

~~~text
error: this case label is dominated by a preceding case label
~~~

**Không nên “sửa” bằng cách xóa case đặc thù** nếu yêu cầu nghiệp vụ cần giữ nó. Sắp xếp lại từ giá trị hằng/guard cụ thể đến pattern rộng hơn. Nếu hai điều kiện thực sự chồng lấn, viết lại để miền dữ liệu của mỗi nhánh dễ hiểu và có test.

## 12. Phân biệt dominance, duplicate labels và exhaustiveness

Đây là ba loại quy tắc khác nhau:

| Khái niệm | Câu hỏi compiler cần bảo đảm | Ví dụ |
| --- | --- | --- |
| **Dominance** | Có nhãn nào bị một nhãn trước bao trùm không? | `case Number` trước `case Integer` |
| **Duplicate case constants** | Có hai hằng case trùng giá trị không? | Hai nhãn `case 1` |
| **Exhaustiveness** | Switch có bao phủ đủ các giá trị đầu vào có thể có không? | Switch expression trên `Object` chỉ có String/Integer mà thiếu fallback |

Một switch có thứ tự tốt vẫn có thể **không exhaustive** nếu bỏ sót kiểu dữ liệu. Ngược lại, một switch có `default` vẫn có thể **bị dominance** nếu case rộng che khuất case đặc thù trước khi tới default.

Với switch expression trên `Object`, thường cần một `default` hoặc một total type pattern thích hợp để bao phủ các kiểu còn lại. Với sealed types, compiler có thể chứng minh bao phủ nhờ tất cả subtype cho phép, như ví dụ `Shape`.

`case null` cần được quyết định riêng theo hợp đồng đầu vào; một switch expression có thể exhaustive theo kiểm tra của compiler mà vẫn ném ngoại lệ với null nếu không có nhánh null phù hợp.

## 13. Khi dùng switch statement dạng dấu hai chấm

Cùng ý nghĩa lựa chọn case, nhưng có hai dạng body cần phân biệt:

~~~java
// Switch statement dùng rule mũi tên
switch (value) {
    case String s -> System.out.println("STRING:" + s);
    case Number n -> System.out.println("NUMBER:" + n);
    default -> System.out.println("OTHER");
}
~~~

~~~java
// Switch statement dùng statement group dấu hai chấm
switch (value) {
    case String s:
        System.out.println("STRING:" + s);
        break;
    case Number n:
        System.out.println("NUMBER:" + n);
        break;
    default:
        System.out.println("OTHER");
}
~~~

Đây là các đoạn **minh họa** đặt trong một phương thức có `Object value`. Quy tắc dominance về nhãn vẫn cần tuân thủ ở cả hai dạng.

Khác biệt vận hành: dạng `case ... ->` không fall-through; dạng `case ...:` có thể fall-through nếu không chặn luồng bằng `break`, `return` hoặc `throw`. Với pattern variable, Java còn cấm đường rơi **vào** một case khai báo biến pattern nếu biến có thể chưa được khởi tạo.

Vì vậy, khi tập trung vào **độ đặc hiệu của nhãn**, dạng mũi tên thường dễ review hơn. Nếu bắt buộc dùng dấu hai chấm, kiểm tra cả **thứ tự case** và **luồng fall-through**; chỉ sắp xếp đúng subtype trước supertype chưa đủ để bảo đảm toàn bộ switch an toàn.

## 14. Checklist sắp xếp và review pattern switch

Khi gặp một switch có nhiều case, hãy tự kiểm tra:

1. **Kiểu tĩnh selector là gì?** `Object`, `Number`, một interface, record hay sealed hierarchy?
2. **Có quan hệ subtype–supertype không?** `Integer` trước `Number`, `String` trước `CharSequence` nếu cần phân biệt.
3. **Có nhãn hằng cần ưu tiên không?** `case 1` hoặc `case "OK"` nên đứng trước guarded/unguarded type pattern bao quát.
4. **Các guard cùng kiểu có thứ tự hợp lý chưa?** Điều kiện đặc thù trước case cùng kiểu không guard.
5. **Guard trước có thể bắt dữ liệu của case hằng sau không?** Compiler không nhất thiết báo lỗi; phải test giá trị giao nhau.
6. **Có nhánh `case Object o`, pattern kiểu cha quá rộng hoặc `default` ở cuối không?** Đừng để pattern rộng che case cụ thể.
7. **Record patterns và subtype của sealed hierarchy đã được xếp đúng chưa?** Các guard đặc thù trước pattern record chung.
8. **Có nhãn bị duplicate hoặc dominated không?** Chạy compiler và đọc đúng lỗi, không chữa bằng việc thêm default bừa bãi.
9. **Switch đã exhaustive chưa?** Với `Object` thường cần fallback; với sealed hierarchy có thể bao phủ đủ subtype.
10. **`null` được xử lý theo ý định chưa?** `case null` nếu muốn xử lý nó thành một kết quả.
11. **Nếu dùng `case ...:`, có fall-through không mong muốn không?** Tránh rơi vào nhãn khai báo pattern variable.
12. **Có test cho trường hợp thuộc nhiều nhánh không?** Test miền giao thường tìm được lỗi ordering mà compiler không phát hiện.

## 15. Bài tập tự kiểm tra và đáp án

### Bài 1 — Sửa thứ tự kiểu

Cho:

~~~java
case Number n -> "NUMBER";
case Integer i -> "INTEGER";
case Double d -> "DOUBLE";
~~~

Hãy sắp xếp lại để xử lý riêng Integer và Double, rồi mới nhận Number còn lại.

**Đáp án:**

~~~java
case Integer i -> "INTEGER";
case Double d -> "DOUBLE";
case Number n -> "NUMBER";
~~~

Các case cần nằm trong một switch có selector thích hợp và các nhánh bao phủ còn lại nếu cần.

### Bài 2 — Hằng và guard

Cho selector kiểu `Integer`:

~~~java
case Integer n when n > 0 -> "POSITIVE";
case 1 -> "ONE";
case Integer n -> "OTHER";
~~~

Đoạn này có nhất thiết bị compiler báo dominance không? `value = 1` đi vào nhánh nào?

**Đáp án:** Guard `n > 0` là động nên đoạn có thể biên dịch. Với `1`, guard đầu đúng nên nhận `POSITIVE`, không nhận `ONE`. Muốn `1` đặc biệt, đặt `case 1` lên trước guard.

### Bài 3 — Guard cụ thể trước

Hãy sắp xếp:

~~~java
case String s -> "TEXT";
case String s when s.isBlank() -> "BLANK";
case String s when s.length() > 10 -> "VERY_LONG";
~~~

để biên dịch và phân loại chuỗi blank trước, chuỗi dài sau, cuối cùng là các chuỗi khác.

**Đáp án:**

~~~java
case String s when s.isBlank() -> "BLANK";
case String s when s.length() > 10 -> "VERY_LONG";
case String s -> "TEXT";
~~~

Một chuỗi blank dài hơn 10 ký tự vẫn được ưu tiên là `BLANK` vì guard đầu đứng trước.

### Bài 4 — Record pattern

Với `record Point(int x, int y) {}`, bạn muốn phân biệt điểm gốc, điểm trên đường chéo và điểm khác. Sắp xếp các nhãn:

**Đáp án tham khảo:**

~~~java
case Point(int x, int y) when x == 0 && y == 0 -> "ORIGIN";
case Point(int x, int y) when x == y -> "DIAGONAL";
case Point(int x, int y) -> "OTHER_POINT";
~~~

Điểm gốc cũng thỏa `x == y` nên phải nằm trước guard đường chéo nếu muốn có nhãn riêng.

### Bài 5 — Interface

Tại sao `case CharSequence cs` trước `case String s` là dominance, nhưng `case Number n` và `case CharSequence cs` có thể cùng tồn tại theo cả hai thứ tự trong `switch (Object value)`?

**Đáp án:** Mọi `String` là `CharSequence`, nên case rộng trước bao trùm case con. `Number` và `CharSequence` không có quan hệ subtype trực tiếp để một pattern tự bao trùm pattern kia; trong ví dụ cơ bản cả hai đều hợp lệ và phục vụ các nhóm đối tượng khác nhau.

### Bài 6 — Exhaustiveness và null

Một switch expression trên selector `Object` có các case `String`, `Integer` và `Number`. Đã exhaustive chưa? Thêm `case null` đã đủ chưa?

**Đáp án:** Chưa. Những đối tượng như `new Object()` hoặc `StringBuilder` vẫn không khớp các nhãn. Cần một fallback bao quát như `default` hoặc pattern `Object o` thích hợp; xử lý null là một vấn đề riêng. Thêm `case null` **không** tự giúp bao phủ tất cả kiểu khác.

### Bài 7 — Chẩn đoán compiler

Nếu `javac` báo `this case label is dominated by a preceding case label`, có nên xóa `default` hoặc thêm `break` để sửa không?

**Đáp án:** Thông thường không. Dominance liên quan khả năng khớp của **nhãn case** theo thứ tự; hãy xác định nhãn trước đã bao trùm nhãn sau ra sao, rồi đổi thứ tự hoặc thiết kế lại pattern/guard. `break` chỉ liên quan luồng điều khiển ở switch statement dạng dấu hai chấm.

## 16. Kết luận và tài liệu tham khảo

Một pattern switch dễ đọc nên được tổ chức **từ trường hợp đặc hiệu tới tổng quát**. Hãy ưu tiên hằng cụ thể, guarded pattern theo nhu cầu nghiệp vụ, rồi type/record pattern không guard theo quan hệ subtype–supertype, sau cùng là fallback rộng. `null` cần được quyết định rõ.

Điểm phân biệt quan trọng nhất: **compiler bắt lỗi dominance theo các quy tắc xác định; compiler không bảo đảm mọi thứ tự guard động đều đúng ý định nghiệp vụ**. Vì vậy, ngoài việc biên dịch thành công, hãy test những giá trị có thể khớp **nhiều nhãn**.

Tài liệu chính thức:

- Java SE 21 JLS `14.11.1 — Switch Blocks, dominance và guarded case labels: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
- Java SE 21 JLS `15.28 — Switch Expressions: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- Oracle Java 21 — Pattern Matching for switch Expressions and Statements, mục Pattern Label Dominance: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
