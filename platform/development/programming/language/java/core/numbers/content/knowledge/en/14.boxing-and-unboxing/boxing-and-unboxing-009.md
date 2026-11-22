# Toán tử ?: có thể unbox nhánh wrapper trong Java

> **Java core – numbers · Boxing và unboxing**  
> **Mục tiêu:** Hiểu vì sao biểu thức điều kiện `condition ? expression1 : expression2` đôi khi tự động chuyển `Integer`, `Long`, `Double`… thành primitive; biết lúc nào giá trị `null` gây `NullPointerException`, lúc nào nhánh không chọn không được đánh giá, và cách thiết kế xử lý giá trị tùy chọn an toàn trong Java 17+.

## 1. Một dòng Java có thể ném NullPointerException dù không gọi .intValue()

Xét đoạn mã:

```java
Integer boxed = null;
boolean chooseBoxed = true;

Integer result = chooseBoxed ? boxed : 0;
// NullPointerException khi chạy!
```

Thoạt nhìn, biến nhận có kiểu `Integer` nên ta dễ nghĩ nhánh `boxed` sẽ được giữ nguyên là `null`. Nhưng trong ví dụ này, một nhánh là **`Integer`** và nhánh còn lại là **`int`** (literal `0`). Theo quy tắc kiểu của **numeric conditional expression**, toán tử `?:` có thể xác định kiểu kết quả là **primitive `int`**.

Khi điều kiện là `true`, Java phải **unbox** nhánh `boxed` thành `int` để tạo giá trị của biểu thức `?:`. Vì `boxed == null`, thao tác này ném `NullPointerException`. Phép boxing để gán vào biến `Integer result` sẽ **không xảy ra**, bởi quá trình đánh giá biểu thức đã thất bại.

Cùng một nhánh wrapper nhưng điều kiện `false`:

```java
Integer boxed = null;
Integer result = false ? boxed : 0;
System.out.println(result); // 0
```

Lúc này Java chọn nhánh primitive `0`, nên không đọc giá trị `boxed` và không xảy ra lỗi.

**Điểm cốt lõi:** kiểu của **toàn bộ biểu thức điều kiện** được xác định **khi biên dịch** dựa trên quy tắc của Java; khi chạy, chỉ nhánh được chọn được đánh giá. Nếu nhánh được chọn là wrapper cần chuyển sang primitive, việc **unboxing có thể xảy ra ngay trong toán tử `?:`**, trước bước gán cuối.

## 2. Ôn tập: boxing, unboxing, primitive và wrapper

**Boxing** chuyển giá trị primitive sang đối tượng wrapper; **unboxing** lấy giá trị primitive từ wrapper.

| Primitive | Wrapper | Ví dụ unbox |
| --- | --- | --- |
| `byte` | `Byte` | `Byte.byteValue()` |
| `short` | `Short` | `Short.shortValue()` |
| `int` | `Integer` | `Integer.intValue()` |
| `long` | `Long` | `Long.longValue()` |
| `float` | `Float` | `Float.floatValue()` |
| `double` | `Double` | `Double.doubleValue()` |
| `char` | `Character` | `Character.charValue()` |
| `boolean` | `Boolean` | `Boolean.booleanValue()` |

Ví dụ:

```java
int n = 7;
Integer boxed = n;            // boxing, gần với Integer.valueOf(n)
int original = boxed;         // unboxing, gần với boxed.intValue()

Integer nullable = null;
// int failed = nullable;     // biên dịch được nhưng ném NPE khi chạy
```

Wrapper là kiểu **tham chiếu**, nên `Integer` có thể là `null`. Primitive `int` không chứa được `null`. Mỗi khi ngữ cảnh đòi chuyển wrapper đang bằng `null` về primitive, Java ném `NullPointerException`.

Trong thực tế unboxing có thể bị ẩn trong:

- phép cộng/trừ/nhân/chia như `boxed + 1`;
- so sánh wrapper với primitive, ví dụ `boxed == 5`;
- gán wrapper sang primitive, ví dụ `int x = boxed;`;
- điều kiện `if (boxedBoolean)` nếu `boxedBoolean` có kiểu `Boolean`;
- **toán tử `?:`**, khi quy tắc chọn kiểu cần primitive.

Bài này tập trung vào trường hợp cuối, đặc biệt những biểu thức nhìn có vẻ đang “chọn một đối tượng”.

## 3. Quy tắc nền tảng của toán tử điều kiện ?:

Cú pháp:

```java
condition ? whenTrue : whenFalse
```

Trình tự:

1. Đánh giá biểu thức `condition`.
2. Nếu điều kiện đúng, **chỉ đánh giá `whenTrue`**.
3. Nếu điều kiện sai, **chỉ đánh giá `whenFalse`**.
4. Chuyển giá trị nhánh được chọn thành **kiểu mà toán tử điều kiện yêu cầu**, nếu cần, rồi tạo kết quả biểu thức.

Hai nhánh **không chạy cả hai**. Nhưng compiler phải xác định được **kiểu chung/kiểu kết quả của biểu thức** theo ngữ pháp và quy tắc type system của Java trước khi chương trình chạy.

Một ví dụ không có wrapper:

```java
int x = true ? 10 : 20;    // 10
int y = false ? 10 : 20;   // 20
```

Toán tử `?:` cũng có thể lồng nhau; nó được nhóm theo hướng **phải sang trái**:

```java
int result = a ? 1 : b ? 2 : 3;
// Nhóm: a ? 1 : (b ? 2 : 3)
```

Ở đây `a` và `b` là các biến `boolean` đã có sẵn; đây là ví dụ **cú pháp minh họa**, không phải chương trình hoàn chỉnh. Khi lồng nhiều biểu thức, từng toán tử `?:` có quy tắc chọn kiểu riêng, vì vậy càng dễ xảy ra chuyển kiểu ngầm khó nhìn.

### Điều kiện boolean cũng có thể unbox

Ngay **condition** cũng có thể gây NPE:

```java
Boolean enabled = null;
// int status = enabled ? 1 : 0; // NPE khi unbox enabled để lấy boolean
```

Trường hợp này **khác** lỗi do nhánh wrapper được chọn: lỗi xảy ra **trước khi chọn nhánh**. Cần nhận biết đúng vị trí unboxing khi đọc stack trace hoặc kiểm thử.

## 4. Vì sao Integer và int có thể tạo kết quả primitive int?

Xét:

```java
Integer nullable = null;
int fallback = 0;

Integer value = choose ? nullable : fallback;
```

Đây là **numeric conditional expression** do hai nhánh có kiểu liên quan đến số. Với cặp nhánh `Integer` và `int`, kiểu của biểu thức điều kiện là `int`. Nếu chọn `nullable`, nó cần được **unbox**.

Diễn giải ý nghĩa của dòng mã trên theo các bước:

```text
condition ? Integer : int
          └── kiểu biểu thức theo quy tắc: int

Khi condition == true:
1. Lấy nullable (Integer).
2. Chuyển Integer -> int (unboxing).
3. Nếu nullable == null: ném NullPointerException.
4. Nếu thành công, kết quả int có thể được boxing khi
   gán vào biến Integer value.

Khi condition == false:
1. Lấy fallback (int).
2. Kết quả có kiểu int.
3. Boxing nếu đích gán có kiểu Integer.
```

Trong biểu thức có `Integer` và `long`, Java có thể cần mở rộng số sang `long`:

```java
Integer maybe = null;
// long value = true ? maybe : 0L; // NPE: nhánh Integer cần unbox rồi widen
```

**Không** suy diễn quy tắc tổng quát quá đơn giản như “hễ có một wrapper và một primitive, kết quả luôn là primitive có tên giống wrapper”. Các bảng chọn kiểu của toán tử `?:` có những trường hợp đặc biệt cho constant expression kiểu `int`, `byte`/`short`/`char` và các kiểu numeric khác. Cần xác định **cặp kiểu thực tế** của hai nhánh và kiểu của biểu thức lồng, không đoán từ kiểu biến đích.

Tuy nhiên, ví dụ nền tảng `Integer ? int` gây unboxing là đủ để thấy rủi ro.

## 5. Kiểu biến nhận không nhất thiết ngăn unboxing

So sánh:

```java
Integer boxed = null;
boolean c = true;

// Cả hai có thể ném NPE khi chọn boxed:
 // int primitiveResult = c ? boxed : 0;
 // Integer wrapperResult = c ? boxed : 0;
```

Vì trong cả hai biểu thức, chính nhánh `boxed` và literal `0` đã quyết định kiểu numeric conditional là `int`. Việc khai báo biến nhận là `Integer` **không tự biến nhánh `0` thành `Integer` trước khi toán tử tính xong**.

Tương tự, khi gán vào `Object`:

```java
Integer boxed = null;
// Object objectResult = true ? boxed : 0; // vẫn có thể NPE
```

Ngữ cảnh này không bảo đảm giữ nguyên tham chiếu `boxed`. Biểu thức điều kiện vẫn được xác định kiểu theo hai nhánh; giá trị `int` chỉ được boxing thành đối tượng **sau** khi đã đánh giá thành công.

Để tránh suy luận sai, hãy kiểm tra biểu thức từ **bên trong ra bên ngoài**: kiểu của từng nhánh → kiểu của `?:` → kiểu của phép gán. Đừng đi ngược bằng cách xem biến đích rồi suy ra mọi chuyển kiểu trung gian.

## 6. Cả hai nhánh đều Integer: khác biệt quan trọng

Bây giờ thay literal primitive `0` bằng một wrapper `Integer`:

```java
Integer nullable = null;
Integer zeroBox = Integer.valueOf(0);

Integer chosen = true ? nullable : zeroBox;
System.out.println(chosen == null); // true
```

Khi **cả hai nhánh đều có cùng kiểu `Integer`**, quy tắc chọn kiểu của biểu thức giữ kết quả kiểu `Integer`. Nếu chọn nhánh `nullable`, kết quả là tham chiếu `null`; không có lý do phải unbox tại toán tử này.

Một cách viết dễ đọc khác:

```java
Integer chosen = true
        ? nullable
        : Integer.valueOf(0); // cùng kiểu Integer với nhánh kia
```

Lúc này có thể giữ `null` trong biến nhận kiểu `Integer`. Tuy nhiên, nếu chuyển giá trị được chọn sang **primitive sau đó**, NPE vẫn xảy ra:

```java
Integer nullable = null;
Integer other = Integer.valueOf(0);

// Toán tử ?: trả Integer có thể null, nhưng phép gán sang int cần unbox.
// int number = true ? nullable : other; // NPE tại unboxing để gán
```

Câu hỏi cần trả lời không chỉ là “`?:` có unbox hay không”, mà còn là **bước dùng kết quả tiếp theo có yêu cầu unbox không**.

### Cùng kiểu wrapper nhưng có giá trị null ở một nhánh

```java
Integer a = null;
Integer b = 7;
Integer selectedA = true ? a : b;  // null
Integer selectedB = false ? a : b; // 7
```

Hai dòng đều an toàn **ở bước chọn nhánh và gán cho `Integer`**. Việc truy cập `selectedA.intValue()` hoặc cộng `selectedA + 1` sau đó mới phát sinh NPE.

**Cảnh báo:** `Integer` là một kiểu numeric wrapper; chỉ vì cả hai nhánh được viết trông giống đối tượng không có nghĩa mọi trường hợp trộn với kiểu numeric khác đều bảo toàn tham chiếu. Những trường hợp trên an toàn vì **cả hai nhánh có cùng kiểu `Integer`** và đích nhận cũng là `Integer`.

## 7. Điều kiện true/false quyết định có xảy ra unboxing lúc chạy

Một biểu thức có thể **có chuyển kiểu ngầm trong quy tắc kiểu** nhưng không ném lỗi ở mọi lần thực thi.

```java
Integer maybe = null;

int a = false ? maybe : 10; // 10; nhánh maybe không được đánh giá

// int b = true ? maybe : 10; // NPE; chọn nhánh maybe
```

Cơ chế **chỉ đánh giá nhánh được chọn** rất quan trọng: Java không chạy cả hai biểu thức rồi chọn giá trị. Nếu nhánh không được chọn có gọi hàm gây tác dụng phụ, ném ngoại lệ hoặc chứa một wrapper null, nó không bị đánh giá.

Ví dụ:

```java
static Integer loadNullable() {
    System.out.println("called");
    return null;
}

// Không in "called", không NPE:
int safe = false ? loadNullable() : 100;

// In "called" rồi NPE:
// int failed = true ? loadNullable() : 100;
```

Đây là mã minh họa; phương thức `loadNullable` phải được đặt trong một class, các câu lệnh khác trong phương thức có ngữ cảnh phù hợp.

Đồng thời, compiler vẫn **type-check cả hai nhánh**. Nhánh không chọn không có nghĩa bạn được phép viết mã không hợp lệ cú pháp/kiểu tại đó.

## 8. Boolean wrapper là một trường hợp riêng

Với wrapper `Boolean` có thể `null`, có ít nhất **hai điểm** cần cảnh giác.

### 8.1. Unbox để dùng làm điều kiện

```java
Boolean condition = null;

// String text = condition ? "yes" : "no"; // NPE khi dùng condition
```

Phần điều kiện phải có giá trị `boolean` (hoặc `Boolean` được unbox). Nếu `condition` là `null` thì không thể chọn nhánh.

Nếu ý nghĩa nghiệp vụ là **chỉ `Boolean.TRUE` được coi là đúng**, có thể viết:

```java
Boolean condition = null;
String text = Boolean.TRUE.equals(condition) ? "yes" : "no";
System.out.println(text); // no
```

Đây là **quy tắc nghiệp vụ được chọn**, không phải định nghĩa tự nhiên cho `null`. Hệ thống có trạng thái ba giá trị `true`/`false`/`unknown` có thể cần giữ nguyên trạng thái unknown, không âm thầm biến thành false.

### 8.2. Một nhánh Boolean, một nhánh boolean

```java
Boolean nullable = null;
// boolean selected = true ? nullable : false; // NPE khi chọn nullable
```

Tương tự numeric wrapper, trong trường hợp trộn `Boolean` với primitive `boolean`, chuyển kiểu có thể yêu cầu unboxing nhánh wrapper.

Nếu muốn giữ kết quả kiểu `Boolean` cho phép `null`:

```java
Boolean nullable = null;
Boolean fallback = Boolean.FALSE;
Boolean selected = true ? nullable : fallback;
System.out.println(selected == null); // true
```

Đừng dùng wrapper chứa null ở điều kiện `if`/`while` hoặc các toán tử `&&`, `||` mà không có quy tắc rõ ràng; việc unbox null sẽ ném NPE khi tới lượt đánh giá toán hạng đó.

## 9. Ví dụ với Long, Double và các wrapper số khác

Rủi ro không chỉ xảy ra với `Integer`. Ví dụ:

```java
Long nullableLong = null;
// long x = true ? nullableLong : 0L; // NPE

Double nullableDouble = null;
// double y = true ? nullableDouble : 0.0; // NPE

Float nullableFloat = null;
// float z = true ? nullableFloat : 0.0f; // NPE
```

Ở những ví dụ này, hai nhánh tương ứng trộn wrapper với primitive cùng loại numeric, dẫn tới kết quả primitive và unboxing nếu chọn nhánh null.

Với hai wrapper cùng loại, có thể trả một tham chiếu null:

```java
Long a = null;
Long b = Long.valueOf(0L);
Long x = true ? a : b;
System.out.println(x == null); // true
```

### Trộn numeric wrapper khác loại

Ví dụ `Integer` và `Double` là các kiểu wrapper khác nhau:

```java
Integer count = Integer.valueOf(2);
Double ratio = Double.valueOf(1.5);

double result = true ? count : ratio;
System.out.println(result); // 2.0
```

Trong ví dụ numeric conditional này, Java dùng quy tắc chuyển đổi số để cho kết quả `double`; khi chọn `count` cần unbox `Integer` rồi mở rộng số sang `double`. Nếu `count` là `null`, nhánh được chọn sẽ ném NPE.

**Không dựa vào “cả hai nhánh đều là object nên không unbox”.** Với numeric conditional expression, quy tắc kiểu numeric có thể yêu cầu giá trị primitive ngay cả khi mỗi nhánh bắt đầu từ wrapper.

## 10. Autoboxing lại ở bước cuối có thể che giấu bước unboxing trước đó

Xét chuỗi các bước:

```java
Integer maybe = Integer.valueOf(5);
Integer answer = true ? maybe : 0;
System.out.println(answer); // 5
```

Trong trường hợp này:

1. `maybe` có kiểu `Integer`;
2. nhánh kia là `int 0`;
3. conditional expression có kiểu `int`;
4. khi chọn `maybe`, Java unbox nó thành 5;
5. phép gán tới `Integer answer` có thể boxing lại 5.

Khi `maybe` khác null, chương trình vẫn chạy và người đọc có thể không nhận thấy **unboxing → boxing** đã diễn ra. Chỉ khi giá trị `null` xuất hiện mới bộc lộ NPE.

Vì vậy các bộ test chỉ sử dụng wrapper khác null **không đủ** để chứng minh một biểu thức chọn giá trị là null-safe. Cần test cả nhánh chứa null và các điều kiện true/false tương ứng.

## 11. Cách sửa: định nghĩa rõ hợp đồng null trước khi chọn giá trị

Không có một “bản sửa” duy nhất cho mọi bài toán. Cần xác định một trong ba yêu cầu:

1. **Giữ `null`** để thể hiện “không có giá trị”.
2. **Dùng một fallback** như 0 hoặc 1 khi wrapper null.
3. **Từ chối null** bằng ngoại lệ có thông điệp rõ ràng.

### 11.1. Muốn giữ nguyên null

Sử dụng hai nhánh cùng kiểu wrapper và đích nhận wrapper:

```java
Integer nullable = null;
Integer fallbackBoxed = Integer.valueOf(0);

Integer result = true ? nullable : fallbackBoxed;
System.out.println(result == null); // true
```

Hoặc viết `if/else` để thể hiện rõ:

```java
Integer result;
if (true) {
    result = nullable;
} else {
    result = fallbackBoxed;
}
```

Đoạn `if (true)` chỉ để minh họa luồng điều khiển; trong chương trình thực tế thay bằng điều kiện nghiệp vụ. **Không unbox `result` về sau nếu null vẫn hợp lệ.**

### 11.2. Muốn fallback khi wrapper null

Nếu cần số nguyên primitive khác null:

```java
Integer maybe = null;
int count = maybe != null ? maybe.intValue() : 0;
System.out.println(count); // 0
```

Ở đây **điều kiện kiểm tra chính giá trị wrapper**; khi `maybe == null`, nhánh gọi `intValue()` không được đánh giá. Cách viết rất rõ rằng `null` sẽ biến thành `0` theo quy tắc đã chọn.

Nếu còn một điều kiện nghiệp vụ `choose` nữa:

```java
Integer maybe = null;
boolean choose = true;
int result = choose && maybe != null ? maybe.intValue() : 0;
```

Cần xác định liệu “không chọn” và “chọn nhưng không có giá trị” có thực sự cùng được quy về 0 hay không. Nếu hai trạng thái có ý nghĩa khác nhau, đừng nhập chúng bằng một fallback.

Cũng có thể dùng `Objects.requireNonNullElse` khi cần một wrapper có fallback **khác null**, nhưng vẫn phải hiểu nó là lựa chọn thay thế null theo quy ước, không phải Java tự động áp dụng cho `?:`:

```java
import java.util.Objects;

Integer maybe = null;
Integer result = Objects.requireNonNullElse(
        maybe, Integer.valueOf(0));
System.out.println(result); // 0
```

### 11.3. Muốn từ chối null

```java
import java.util.Objects;

Integer maybe = null;
// int x = Objects.requireNonNull(maybe, "Missing count"); // ném NPE rõ thông điệp
```

Hoặc chủ động ném `IllegalArgumentException` ở ranh giới API nếu null là dữ liệu đầu vào không hợp lệ. Không nên che giấu lỗi bằng catch `NullPointerException` bao trùm một biểu thức lớn rồi âm thầm thay 0: cách đó dễ nuốt các lỗi lập trình khác.

## 12. Khi nào nên viết if/else thay cho ?:

Toán tử `?:` phù hợp khi hai nhánh ngắn, dễ đọc và kiểu kết quả rõ ràng. Khi có nhiều kiểu wrapper, nullability hoặc logic điều kiện phức tạp, `if/else` thường làm **bước unboxing** lộ rõ hơn:

```java
static Integer chooseNullable(boolean choose, Integer input) {
    if (choose) {
        return input;     // có thể trả null
    }
    return Integer.valueOf(0);
}

static int choosePrimitive(boolean choose, Integer input) {
    if (choose) {
        if (input == null) {
            throw new IllegalArgumentException("Missing input");
        }
        return input.intValue();
    }
    return 0;
}
```

Hai phương thức này có **hợp đồng khác nhau**:

- `chooseNullable` có thể trả `null`, cần người gọi xử lý.
- `choosePrimitive` luôn trả `int` hoặc ném một ngoại lệ chủ động nếu không có số cần dùng.

So sánh với phương thức dễ gây hiểu lầm:

```java
static Integer subtle(boolean choose, Integer input) {
    return choose ? input : 0;
}
```

Mặc dù chữ ký trả `Integer`, nhánh `input` vẫn có thể được unbox bởi numeric conditional expression. **Kiểu trả về của phương thức không tự sửa cách xác định kiểu của `?:` bên trong.**

Một thiết kế API tốt nên công bố rõ: tham số/giá trị trả về có cho phép null không, và có fallback nào được áp dụng.

## 13. Không ép kiểu tùy tiện để né NullPointerException

Có thể thấy cách “ép thành Object để Java không unbox”:

```java
Integer nullable = null;
Object selected = true ? (Object) nullable : 0;
System.out.println(selected == null); // true
```

Vì một nhánh có kiểu `Object`, biểu thức này thuộc nhóm **reference conditional expression** và có thể giữ tham chiếu null. Nhưng đó **không phải giải pháp mặc định** cho biến cần kiểu `Integer` hay `int`, vì trả về `Object` làm yếu type safety và có thể yêu cầu cast về sau.

Tương tự, đổi toàn bộ nhánh sang kiểu reference khác mà không nắm quy tắc conditional typing có thể che lỗi tại chỗ này rồi dời sang chỗ khác. Ưu tiên:

- cùng kiểu wrapper khi thật sự muốn giữ null;
- kiểm tra null rõ ràng khi cần primitive;
- `if/else` khi cần nhiều bước xử lý hoặc thông điệp lỗi tốt.

### Cẩn thận với Optional

`Optional<Integer>` biểu diễn việc có hoặc không có số nguyên:

```java
import java.util.Optional;

Integer maybe = null;
int count = Optional.ofNullable(maybe).orElse(0);
System.out.println(count); // 0
```

Đây là lựa chọn cho **một số ranh giới API**, không cần thiết cho mọi phép cộng đơn giản. `Optional` cũng không “trị” mọi lỗi null: vẫn cần chọn fallback, ném lỗi hoặc xử lý trường hợp vắng mặt một cách có chủ đích.

## 14. Java 17+ demo chạy độc lập

Tạo tệp **`ConditionalUnboxingDemo.java`**:

```java
import java.util.Objects;

public class ConditionalUnboxingDemo {
    private static Integer chooseNullable(boolean choose, Integer value) {
        return choose ? value : Integer.valueOf(0);
    }

    private static Integer subtle(boolean choose, Integer value) {
        return choose ? value : 0;
    }

    private static void runCase(String name, Runnable action) {
        try {
            action.run();
        } catch (NullPointerException ex) {
            System.out.println(name + ": NullPointerException");
        }
    }

    public static void main(String[] args) {
        Integer missing = null;

        runCase("selected Integer+int", () -> {
            Integer result = true ? missing : 0;
            System.out.println(result);
        });

        Integer notSelected = false ? missing : 0;
        System.out.println("unselected null = " + notSelected);

        Integer keptNull = true
                ? missing
                : Integer.valueOf(0);
        System.out.println("two Integer branches null = "
                + (keptNull == null));

        Integer fromMethod = chooseNullable(true, missing);
        System.out.println("nullable method null = "
                + (fromMethod == null));

        runCase("method returning Integer", () -> {
            System.out.println(subtle(true, missing));
        });

        runCase("assignment to int", () -> {
            Integer left = null;
            Integer right = Integer.valueOf(0);
            int number = true ? left : right;
            System.out.println(number);
        });

        int safe = missing != null ? missing.intValue() : 0;
        System.out.println("explicit fallback = " + safe);

        Integer fallback = Objects.requireNonNullElse(
                missing, Integer.valueOf(0));
        System.out.println("Objects fallback = " + fallback);

        runCase("Boolean condition", () -> {
            Boolean enabled = null;
            int status = enabled ? 1 : 0;
            System.out.println(status);
        });

        runCase("Long+long", () -> {
            Long amount = null;
            long total = true ? amount : 0L;
            System.out.println(total);
        });

        Integer a = Integer.valueOf(2);
        Double b = Double.valueOf(1.5);
        double mixed = true ? a : b;
        System.out.println("mixed numeric = " + mixed);

        Object keptObject = true ? (Object) missing : 0;
        System.out.println("Object branch null = "
                + (keptObject == null));
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac ConditionalUnboxingDemo.java
java ConditionalUnboxingDemo
```

**Đầu ra dự kiến trên Java 17+:**

```text
selected Integer+int: NullPointerException
unselected null = 0
two Integer branches null = true
nullable method null = true
method returning Integer: NullPointerException
assignment to int: NullPointerException
explicit fallback = 0
Objects fallback = 0
Boolean condition: NullPointerException
Long+long: NullPointerException
mixed numeric = 2.0
Object branch null = true
```

**Giải thích:**

1. `true ? missing : 0` tạo numeric conditional type `int`, nên phải unbox `missing` và ném NPE.
2. `false ? missing : 0` không đánh giá nhánh null; kết quả 0.
3. Hai nhánh `Integer` tạo giá trị tham chiếu, vì vậy có thể giữ null; nhưng gán kết quả vào `int` vẫn yêu cầu unbox.
4. Phương thức trả `Integer` không tự ngăn unboxing nếu biểu thức bên trong trộn `Integer` và `int`.
5. Kiểm tra `missing != null`, `Objects.requireNonNullElse` là hai cách định nghĩa fallback 0 rõ ràng.
6. `Boolean` null ở phần điều kiện và `Long` null được chọn trong numeric conditional đều có thể ném NPE.
7. Trộn `Integer` và `Double` tạo numeric result có thể được xử lý bằng chuyển kiểu số; chọn nhánh `Integer 2` cho kết quả `double 2.0`.
8. Ép nhánh sang `Object` minh họa reference conditional expression có thể giữ null, nhưng phải cân nhắc type safety.

## 15. Bảng phân biệt các tình huống thường gặp

Trong bảng này, `n` là biến `Integer n = null;`; `zero` là `Integer zero = Integer.valueOf(0);`.

| Biểu thức / hoàn cảnh | Kiểu hoặc chuyển đổi cốt lõi | Khi chạy |
| --- | --- | --- |
| `Integer x = true ? n : 0;` | `Integer` + `int` → kết quả `int` rồi boxing khi gán | **NPE** |
| `Integer x = false ? n : 0;` | Chọn nhánh primitive `int` | `x = 0` |
| `int x = true ? n : 0;` | Chọn `n` rồi unbox | **NPE** |
| `Object x = true ? n : 0;` | Toán tử numeric trước khi boxing sang Object | **NPE** |
| `Integer x = true ? n : zero;` | Hai nhánh cùng `Integer` | `x = null` |
| `int x = true ? n : zero;` | Toán tử giữ `Integer` nhưng gán sang primitive | **NPE tại gán** |
| `Integer x = n != null ? n : zero;` | Có kiểm tra null và nhánh được chọn cùng `Integer` | `x = 0` |
| `int x = n != null ? n.intValue() : 0;` | Unbox chỉ trong nhánh đã kiểm tra | `x = 0` |
| `boolean x = ((Boolean) null) ? true : false;` | Điều kiện phải unbox Boolean | **NPE trước chọn nhánh** |
| `Object x = true ? (Object)n : 0;` | Một nhánh ép Object → reference conditional | `x = null` |

**Độ chính xác về thời điểm:** cùng là NPE nhưng có thể xảy ra ở **điều kiện**, ở **nhánh được chọn** trong biểu thức `?:`, hoặc ở **bước chuyển kiểu sau khi toán tử trả giá trị**. Sửa lỗi nên bắt đầu bằng xác định đúng bước ấy.

## 16. Những hiểu lầm dễ dẫn đến lỗi

| Hiểu lầm | Giải thích đúng |
| --- | --- |
| “Biến nhận kiểu `Integer` nghĩa là không unbox” | Kiểu `?:` có thể là `int` trước khi boxing vào biến nhận |
| “Nhánh `null` không bao giờ gây NPE vì null là reference” | Nếu nhánh wrapper được chọn cần unbox, null gây NPE |
| “Toán tử `?:` luôn đánh giá cả hai nhánh” | Chỉ một nhánh được đánh giá; nhánh không chọn không gây tác dụng phụ runtime |
| “Cả hai nhánh đều wrapper thì luôn trả wrapper” | Với **cùng kiểu wrapper**, có thể giữ reference; nhưng khác loại numeric wrapper có thể bị numeric promotion |
| “Đổi `0` thành `Integer.valueOf(0)` luôn xóa mọi NPE” | Chỉ ngăn unboxing tại `?:` trong trường hợp hai nhánh cùng Integer; nếu đích là `int` vẫn có thể NPE |
| “`Objects.equals(n, 0)` giống `n == 0` khi n null” | `Objects.equals` null-safe, còn `n == 0` có thể unbox null |
| “Cứ cast Object thì kiểu nào cũng an toàn” | Có thể giữ null tại bước chọn, nhưng mất type safety và còn lỗi khi cast/unbox sau |
| “Boolean null tự được coi là false” | Không; dùng làm điều kiện cần unbox và có thể ném NPE |
| “Nếu code chạy với các giá trị khác null thì ?: an toàn” | Phải kiểm thử nhánh wrapper null và nhánh đối diện |
| “Compiler sẽ chọn loại nhánh dựa trên giá trị true/false đang biết” | Type-checking xác định kiểu từ hai operand theo quy tắc ngôn ngữ, bất kể nhánh nào được chọn khi chạy |
| “Chỉ cần catch NPE ở cuối là được” | NPE có thể phản ánh lỗi khác; cần kiểm tra null và nêu hợp đồng tại chỗ dùng dữ liệu |

## 17. Bài tập tự kiểm tra và lời giải

**Bài 1.** Với `Integer n = null;`, đánh giá `Integer r = true ? n : 0;`. Vì sao không chỉ nhận null?  
**Đáp án:** Hai nhánh `Integer` và `int` tạo numeric conditional type `int`. Chọn `n` cần unbox null, ném `NullPointerException` trước khi có thể boxing kết quả để gán.

**Bài 2.** `Integer r = false ? n : 0;` (với `n=null`) có NPE không?  
**Đáp án:** Không. Java chỉ đánh giá nhánh `0` vì điều kiện false; kết quả sau boxing là `Integer 0`.

**Bài 3.** `Integer z = Integer.valueOf(0); Integer r = true ? n : z;` có NPE khi `n=null` không?  
**Đáp án:** Không tại bước chọn/gán: cả hai nhánh đều là `Integer`, biểu thức trả tham chiếu `null`, `r=null`. Nhưng nếu dùng `int x=r;` sau đó sẽ NPE.

**Bài 4.** Vì sao `int x = true ? n : z;` vẫn có NPE, dù hai nhánh cùng Integer?  
**Đáp án:** Toán tử `?:` có thể trả `Integer null`, nhưng phép gán vào `int` buộc unbox tham chiếu null.

**Bài 5.** Với `Boolean b=null;`, `int x=b ? 1:0;` báo lỗi ở bước nào?  
**Đáp án:** Tại unboxing của **điều kiện** `b` để lấy primitive `boolean`, trước khi chọn một trong hai nhánh số.

**Bài 6.** Sửa `int r = choose ? nullable : 0;` theo yêu cầu: null được coi là 0.  
**Đáp án:** `int r = choose && nullable != null ? nullable.intValue() : 0;`, với `choose` là boolean và `nullable` có kiểu `Integer`. Điều kiện kiểm tra null trước khi gọi `intValue()`.

**Bài 7.** Sửa cùng biểu thức theo yêu cầu: khi choose=true và nullable=null, **phải trả null**.  
**Đáp án:** Kết quả phải là `Integer` và hai nhánh cùng wrapper: `Integer r = choose ? nullable : Integer.valueOf(0);`. Người gọi tiếp tục chịu trách nhiệm xử lý null.

**Bài 8.** `Object o = true ? nullable : 0;` có luôn tránh NPE không?  
**Đáp án:** Không. Kiểu của numeric conditional được xác định từ nhánh `Integer`/`int` trước, có thể unbox null. Việc gán vào `Object` không sửa lại bước đã xảy ra.

**Bài 9.** Nếu nhánh không được chọn chứa `Integer null` hoặc một phương thức ném lỗi, nó có chạy không?  
**Đáp án:** Không. Toán tử chỉ đánh giá một nhánh đã chọn; nhưng hai nhánh vẫn phải hợp lệ về cú pháp và kiểu khi biên dịch.

**Bài 10.** Khi review PR, thấy `return condition ? boxed : 0;` trong phương thức trả `Integer`. Cần kiểm tra điều gì?  
**Đáp án:** Kiểm tra `boxed` có thể null không, vì `?:` có thể là kiểu `int` và unbox trước khi boxing trả về. Nếu null được phép, dùng `Integer.valueOf(0)` làm nhánh còn lại hoặc viết `if/else` để giữ kiểu wrapper; nếu null không hợp lệ, kiểm tra và báo lỗi rõ ràng.

## 18. Checklist khi dùng ? với wrapper

1. Xác định kiểu của **condition**: `boolean` hay `Boolean` có thể null?
2. Xác định kiểu **từng nhánh**, không chỉ nhìn biến nhận: primitive, wrapper cùng loại hay wrapper numeric khác loại?
3. Xác định kiểu kết quả **của chính `?:`** theo quy tắc Java; không giả định vế gán `Integer` đồng nghĩa kết quả trước đó là wrapper.
4. Hỏi nhánh wrapper có thể `null` không; nếu được chọn, có cần unbox không?
5. Hỏi **đích sử dụng kết quả** có unbox tiếp không, ngay cả nếu `?:` giữ reference?
6. Nếu muốn null được giữ, dùng **hai nhánh cùng kiểu wrapper** và đích wrapper, đồng thời ghi rõ hợp đồng nullability.
7. Nếu muốn primitive bắt buộc, **kiểm tra null trước** hoặc từ chối dữ liệu với ngoại lệ có chủ đích.
8. Nếu cần fallback, ghi rõ đó là **quy tắc nghiệp vụ**; 0 không tự đồng nghĩa “không có giá trị”.
9. Viết kiểm thử đủ các trường hợp **condition true/false**, nhánh wrapper null/non-null, giá trị đã boxing và nested ternary.
10. Khi biểu thức phức tạp hoặc gây tranh luận về kiểu, **dùng `if/else`** để làm rõ ý định.

**Ghi nhớ:** `?:` chỉ đánh giá **một nhánh**, nhưng kiểu kết quả đã được chọn theo quy tắc khi biên dịch. Nếu kiểu ấy yêu cầu **primitive**, nhánh wrapper được chọn có thể bị **unbox tự động** và ném `NullPointerException` khi mang `null`—ngay cả khi biến nhận hoặc kiểu trả về cuối là wrapper. Muốn viết an toàn, hãy kiểm tra null và làm rõ kiểu của cả **biểu thức `?:`** lẫn nơi tiêu thụ kết quả.
