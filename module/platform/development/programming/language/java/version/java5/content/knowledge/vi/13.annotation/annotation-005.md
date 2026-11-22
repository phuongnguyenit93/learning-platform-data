# Giá trị mặc định và quy tắc giá trị hằng trong annotation

## 1. Hai cơ chế cần tách riêng

Khi dùng annotation, ta thường gặp hai câu hỏi:

- Không ghi một phần tử thì Java lấy giá trị nào?
- Vì sao một biểu thức Java chạy được bình thường lại không được dùng làm giá trị annotation?

Câu hỏi thứ nhất liên quan đến **giá trị mặc định** khai báo bằng `default`. Câu hỏi thứ hai liên quan đến **giới hạn giá trị annotation**, trong đó phần tử kiểu nguyên thủy và `String` đòi hỏi biểu thức hằng phù hợp.

Ví dụ:

```java
@interface Retry {
    int attempts() default 2;
}
```

`@Retry` có thể bỏ `attempts`, vì phần tử đã có mặc định. Nhưng `@Retry(attempts = calculateAttempts())` không hợp lệ chỉ vì phương thức đó “luôn trả về 2”.

Annotation lưu siêu dữ liệu theo dạng ngôn ngữ quy định; nó không phải nơi chạy mã khởi tạo tùy ý. Các quy tắc trong bài vẫn áp dụng trên Java hiện hành; chương trình kiểm chứng dùng Java 17+.

## 2. Cú pháp default và phần tử bắt buộc

Khai báo:

```java
@interface Rule {
    String value();
    int attempts() default 2;
    String[] tags() default {};
}
```

Cách đọc:

| Phần tử | Có mặc định? | Khi sử dụng |
|---|---|---|
| `value` | Không | Bắt buộc cung cấp |
| `attempts` | Có, bằng 2 | Có thể bỏ qua |
| `tags` | Có, mảng rỗng | Có thể bỏ qua |

Các cách dùng hợp lệ:

```java
@Rule("A")
class First {
}

@Rule(value = "B", attempts = 5)
class Second {
}

@Rule(value = "C", tags = {"io", "retry"})
class Third {
}
```

Không hợp lệ:

```java
// Thiếu value; không được tự điền "" hoặc null:
// @Rule(attempts = 5)
```

`default` nằm trong khai báo phần tử của annotation, không phải nơi sử dụng. Muốn ghi đè mặc định tại một vị trí cụ thể, cung cấp giá trị tường minh:

```java
@Rule(value = "D", attempts = 0)
class ExplicitZero {
}
```

Giá trị 0 này được giữ nguyên; nó không có nghĩa là “quay về mặc định”. Java không dành riêng số 0, chuỗi rỗng hoặc mảng rỗng để biểu thị “bỏ qua phần tử”.

Giá trị mặc định phải hợp lệ theo cùng quy tắc giá trị của phần tử, không được dùng một biểu thức tùy ý rồi chờ đánh giá khi chương trình chạy. Quy định nằm trong [JLS §9.6.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.2).

### Default không phải phương thức có thân

Hai cú pháp sau khác nhau:

```java
// Phần tử annotation:
int attempts() default 2;

// Không phải cách khai báo phần tử annotation:
// default int attempts() { return 2; }
```

Phần tử annotation không có thân phương thức. Không đưa logic điều kiện đọc cấu hình, truy cập biến môi trường hay gọi dịch vụ vào phần mặc định.

## 3. Biểu thức hằng là gì?

Với phần tử kiểu nguyên thủy hoặc `String`, giá trị phải là **biểu thức hằng (constant expression)** phù hợp với kiểu phần tử.

Đây là khái niệm được ngôn ngữ định nghĩa, không phải nhận xét “lúc chạy kết quả không đổi”. Các ví dụ thường gặp gồm literal, các phép toán được phép trên hằng và tên tham chiếu tới biến hằng.

```java
class Constants {
    static final int ATTEMPTS = 1 + 2;
    static final long TIMEOUT = 1_000L;
    static final String LABEL = "job" + "-rule";
}
```

Những giá trị trên có thể dùng cho các phần tử annotation có kiểu tương ứng:

```java
@Rule(value = Constants.LABEL, attempts = Constants.ATTEMPTS)
class ConstantRule {
}
```

Một số ví dụ biểu thức hằng:

| Biểu thức | Vì sao có thể hợp lệ? |
|---|---|
| `3` | Literal số nguyên |
| `1 + 2` | Phép cộng các hằng |
| `1 << 3` | Phép dịch bit trên các hằng |
| `true ? 2 : 4` | Biểu thức điều kiện gồm các hằng phù hợp |
| `"job" + "-rule"` | Nối các chuỗi hằng |
| `Integer.MAX_VALUE` | Tham chiếu tới biến hằng kiểu `int` |
| `Constants.ATTEMPTS` | Trường `final int` khởi tạo bằng biểu thức hằng |

Quy tắc đầy đủ của biểu thức hằng được mô tả trong [JLS §15.29](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29).

Không suy ra rằng mọi phép toán không có tác dụng phụ đều là biểu thức hằng. Chẳng hạn:

```java
// Không hợp lệ làm giá trị int trong annotation:
// Math.max(1, 2)
// Integer.parseInt("3")
// calculateAttempts()
```

Các biểu thức trên có lời gọi phương thức. Trình biên dịch không chạy một phương thức tùy ý để quyết định rằng nó đủ “hằng”.

### Final chưa đủ

Các trường dưới đây có `final`, nhưng không phải tất cả đều là biến hằng theo nghĩa cần cho annotation:

```java
class Values {
    static final int GOOD = 2 + 1;
    static final String GOOD_TEXT = "Java";

    static final int FROM_METHOD = Integer.parseInt("3");
    static final String FROM_NEW = new String("Java");
    static final String FROM_METHOD_TEXT = String.valueOf(3);
    static final Integer BOXED = 3;
}
```

- `GOOD` và `GOOD_TEXT` là biến hằng phù hợp.
- `FROM_METHOD`, `FROM_NEW` và `FROM_METHOD_TEXT` không có biểu thức khởi tạo hằng.
- `BOXED` có kiểu bao `Integer`, không phải biến hằng kiểu nguyên thủy hoặc `String`. Việc mở hộp nó không biến biểu thức thành hằng hợp lệ cho annotation.

Biến hằng cần là biến `final` có kiểu nguyên thủy hoặc `String`, được khởi tạo bằng biểu thức hằng. `static` không phải điều kiện bắt buộc của khái niệm này: biến cục bộ `final` phù hợp cũng có thể là biến hằng. Các ví dụ dùng `static final` vì đây là cách thường gặp khi chia sẻ hằng giữa các khai báo.

Một trường `final` được gán trong khối khởi tạo thay vì bằng biểu thức khởi tạo hằng tại khai báo cũng không tự trở thành biến hằng.

## 4. Không phải mọi giá trị annotation đều là constant expression

Câu “giá trị annotation phải là hằng” chỉ là cách nói rút gọn và dễ dẫn tới hiểu sai. Mỗi nhóm kiểu có quy tắc riêng:

| Kiểu phần tử | Dạng giá trị phù hợp |
|---|---|
| Nguyên thủy hoặc `String` | Biểu thức hằng phù hợp với kiểu |
| `Class` hoặc dạng tham số hóa hợp lệ của `Class` | Class literal, ví dụ `String.class` |
| Enum | Hằng enum, ví dụ `Mode.SAFE` |
| Một kiểu annotation khác | Annotation lồng, ví dụ `@Owner("team")` |
| Mảng một chiều hợp lệ | Danh sách các giá trị phần tử phù hợp hoặc dạng rút gọn một phần tử |

Class literal, hằng enum và annotation lồng không cần được ép vào khái niệm constant expression của kiểu nguyên thủy/`String`. Chúng hợp lệ nhờ quy tắc giá trị annotation tương ứng trong [JLS §9.7.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.1).

### Enum: hằng enum khác với biến final giữ enum

```java
enum Mode {
    FAST, SAFE
}

@interface ModeRule {
    Mode value() default Mode.SAFE;
}

class Aliases {
    static final Mode ACTIVE = Mode.FAST;
}

@ModeRule(Mode.FAST)
class DirectEnum {
}

// Không hợp lệ:
// @ModeRule(Aliases.ACTIVE)
```

`Aliases.ACTIVE` giữ cùng giá trị enum lúc chạy nhưng vẫn là một trường tham chiếu, không phải cách chỉ định hằng enum mà vị trí annotation yêu cầu.

### Class: cần class literal

```java
@interface TypeRule {
    Class<?> value() default Void.class;
}

class Types {
    static final Class<?> TEXT = String.class;
}

@TypeRule(String.class)
class DirectType {
}

// Không hợp lệ:
// @TypeRule(Types.TEXT)
// @TypeRule(Class.forName("java.lang.String"))
```

Một biến `final Class<?>` không thay thế được cú pháp class literal tại giá trị annotation.

### Mảng: dùng cú pháp giá trị mảng annotation

```java
@interface Tags {
    String[] value() default {};
}

@Tags({"io", "retry"})
class TwoTags {
}

@Tags("io")
class OneTag {
}
```

Không dùng một biến mảng chỉ vì nó là `static final`:

```java
class TagArrays {
    static final String[] SHARED = {"io", "retry"};
}

// Không hợp lệ:
// @Tags(TagArrays.SHARED)

// Cũng không hợp lệ:
// @Tags(new String[] {"io", "retry"})
```

`final` với mảng chỉ ngăn thay đổi tham chiếu của biến; nó không biến mảng thành một hằng biên dịch dùng được trong annotation.

### Annotation lồng

Một mảnh khai báo hợp lệ:

```java
@interface Owner {
    String value();
}

@interface Owned {
    Owner owner() default @Owner("team");
}

@Owned(owner = @Owner("reviewer"))
class Reviewed {
}
```

Giá trị mặc định ở đây là một annotation lồng, không phải lời gọi constructor.

## 5. Null, giá trị vắng mặt và kiểm tra kiểu

### Null không phải giá trị mặc định hợp lệ

Không hợp lệ:

```java
// @interface BadLabel {
//     String value() default null;
// }
```

Cũng không thể cung cấp `null` tại nơi sử dụng, kể cả với `String`, `Class<?>`, annotation lồng hoặc mảng.

Nếu cần trạng thái “chưa chỉ định”, hãy định nghĩa quy ước rõ ràng, chẳng hạn:

- `String[] tags() default {};`: không có nhãn.
- Một hằng enum `UNSPECIFIED`: trạng thái chưa chọn.
- `Class<?> type() default Void.class;`: một giá trị quy ước do API tự định nghĩa.

`Void.class` không tự có ý nghĩa “không có giá trị” cho mọi annotation. Mã đọc annotation phải hiểu và áp dụng quy ước đó.

### Giá trị hằng vẫn phải phù hợp với kiểu

Với phần tử `byte`:

```java
@interface Small {
    byte value();
}

@Small(127)
class MaxByte {
}

// Không hợp lệ: 128 vượt miền giá trị byte.
// @Small(128)
```

Java cho phép chuyển hẹp một số hằng nguyên phù hợp miền giá trị trong ngữ cảnh gán. Không có nghĩa mọi literal `int` đều gán được cho `byte`.

Viết `@Small((byte) 128)` có thể biên dịch, nhưng phép ép kiểu cho kết quả -128. Ép kiểu để vượt qua lỗi biên dịch không giữ lại giá trị 128.

Tương tự, điều kiện nghiệp vụ không được kiểm tra tự động chỉ vì có annotation. Nếu `attempts` có kiểu `int`, một hằng -5 vẫn có thể hợp lệ về mặt ngôn ngữ; công cụ đọc annotation phải kiểm tra nếu hợp đồng yêu cầu số lần thử không âm.

## 6. Chương trình đầy đủ: đọc mặc định và giá trị tường minh

Tạo bốn tệp cùng thư mục:

```text
Mode.java
Constants.java
JobRule.java
DefaultsDemo.java
```

### Tệp Mode.java

```java
public enum Mode {
    FAST, SAFE
}
```

### Tệp Constants.java

```java
public final class Constants {
    public static final int RETRIES = 1 + 2;
    public static final String NAME = "job" + "-rule";

    private Constants() {
    }
}
```

### Tệp JobRule.java

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface JobRule {
    String value();
    int retries() default 2;
    long timeoutMillis() default 1_000L;
    String[] tags() default {};
    Mode mode() default Mode.SAFE;
    Class<?> type() default Void.class;
}
```

Annotation có `RUNTIME` để chương trình kiểm chứng bằng reflection. Bài tập trung vào giá trị; chính sách lưu giữ và vị trí annotation chỉ được cấu hình đủ cho thí nghiệm.

### Tệp DefaultsDemo.java

```java
import java.util.Arrays;

public class DefaultsDemo {
    @JobRule("default")
    static class DefaultCase {
    }

    @JobRule(
            value = Constants.NAME,
            retries = Constants.RETRIES,
            tags = {"io", "safe"},
            mode = Mode.FAST,
            type = String.class
    )
    static class ExplicitCase {
    }

    static void print(Class<?> type) {
        JobRule rule = type.getDeclaredAnnotation(JobRule.class);
        System.out.println(rule.value()
                + ": retries=" + rule.retries()
                + ", timeout=" + rule.timeoutMillis()
                + ", tags=" + Arrays.toString(rule.tags())
                + ", mode=" + rule.mode()
                + ", type=" + rule.type().getSimpleName());
    }

    public static void main(String[] args) {
        print(DefaultCase.class);
        print(ExplicitCase.class);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror -d out Mode.java Constants.java JobRule.java DefaultsDemo.java
java -cp out DefaultsDemo
```

Stdout:

```text
default: retries=2, timeout=1000, tags=[], mode=SAFE, type=Void
job-rule: retries=3, timeout=1000, tags=[io, safe], mode=FAST, type=String
```

Cách đọc:

- `DefaultCase` chỉ ghi phần tử bắt buộc `value`. Các phần tử khác dùng mặc định.
- `ExplicitCase` dùng hai biểu thức hằng qua `Constants`, một mảng giá trị annotation, một hằng enum và một class literal.
- `timeoutMillis` bị bỏ qua ở cả hai vị trí nên đều là 1000.
- Các giá trị chỉ là siêu dữ liệu; chương trình không thực hiện cơ chế thử lại hay tạo bộ đếm thời gian.

## 7. Mặc định không được chép vào mọi nơi sử dụng

Một điểm quan trọng của hợp đồng annotation: mặc định nằm trong khai báo kiểu annotation và được áp dụng khi đọc phần tử bị bỏ qua. Nó không được chép thành một cặp giá trị tường minh vào từng annotation chỉ vì phần tử đó có mặc định.

Có thể kiểm chứng bằng chính chương trình vừa chạy.

### Bước 1: giữ nguyên các lớp đã biên dịch

Sau lệnh biên dịch ở phần trước, các lớp `DefaultsDemo`, `DefaultCase` và `ExplicitCase` đã có trong `out`.

### Bước 2: chỉ sửa mặc định

Trong `JobRule.java`, đổi:

```java
int retries() default 2;
```

thành:

```java
int retries() default 4;
```

### Bước 3: chỉ biên dịch lại JobRule.java

```shell
javac --release 17 -Xlint:all -Werror -cp out -d out JobRule.java
java -cp out DefaultsDemo
```

Kết quả mới:

```text
default: retries=4, timeout=1000, tags=[], mode=SAFE, type=Void
job-rule: retries=3, timeout=1000, tags=[io, safe], mode=FAST, type=String
```

`DefaultCase` không ghi `retries`, nên lần chạy mới đọc được mặc định 4. `ExplicitCase` đã ghi `retries = Constants.RETRIES` tại lúc biên dịch; giá trị tường minh vẫn là 3.

Thí nghiệm không đổi tên phần tử, kiểu phần tử hay cấu trúc annotation; nó chỉ đổi giá trị mặc định. Không cần và không nên suy diễn kết quả này thành bảo đảm tương thích cho mọi thay đổi khác của annotation.

Cũng cần phân biệt hai cơ chế:

- **Giá trị mặc định bị bỏ qua tại nơi dùng:** lấy từ khai báo annotation được đọc.
- **Giá trị hằng được ghi tường minh tại nơi dùng:** được xác định khi biên dịch nơi dùng; không phải một lần đọc trường `Constants.RETRIES` động mỗi khi gọi `rule.retries()`.

Vì vậy, đổi mặc định của annotation có thể đổi hành vi của mã đang bỏ qua phần tử đó dù mã ấy chưa được biên dịch lại. Khi chọn mặc định cho API dùng chung, hãy xem nó là một phần của hợp đồng có ảnh hưởng đến bên sử dụng.

## 8. Lỗi thường gặp và cách xử lý

| Lỗi suy luận | Cách hiểu và xử lý |
|---|---|
| Không ghi một phần tử thì tự nhận giá trị 0/null của Java | Chỉ nhận mặc định được khai báo; nếu không có thì phần tử bắt buộc |
| Mọi `static final` đều dùng được | Kiểm tra kiểu biến và biểu thức khởi tạo có thật sự là hằng không |
| Một phương thức thuần luôn trả cùng kết quả nên dùng được | Lời gọi phương thức không trở thành constant expression theo suy luận đó |
| Biến `final` giữ enum tương đương hằng enum tại annotation | Ghi trực tiếp hằng enum phù hợp |
| Biến `final Class<?>` dùng thay `.class` | Dùng class literal tại giá trị annotation |
| Mảng `static final` dùng làm giá trị annotation được | Dùng cú pháp mảng annotation với các phần tử hợp lệ |
| Có thể dùng null để biểu thị bỏ qua | Chọn mặc định hoặc giá trị quy ước có ý nghĩa |
| Hằng đúng kiểu là chắc chắn đúng nghiệp vụ | Kiểm tra thêm miền hợp lệ do hợp đồng annotation quy định |
| Đổi mặc định thì mọi lớp cũ tiếp tục dùng bản mặc định cũ | Những vị trí bỏ qua phần tử có thể đọc mặc định mới |

Không giải quyết bằng cách thêm ép kiểu hoặc thay mọi giá trị bằng chuỗi. Trước hết xác định đúng nhóm kiểu của phần tử và dạng giá trị mà nhóm đó cho phép.

## 9. Thực hành nhận diện giá trị hợp lệ

Giả sử có:

```java
@interface Check {
    int value() default 2;
}

class TestValues {
    static final int A = 1 + 2;
    static final int B = Integer.parseInt("3");
    static final Integer C = 3;
}
```

Đánh giá các cách dùng:

| Cách dùng | Hợp lệ? | Lý do |
|---|---|---|
| `@Check` | Có | Dùng mặc định 2 |
| `@Check(1 + 2)` | Có | Biểu thức hằng kiểu nguyên |
| `@Check(TestValues.A)` | Có | Biến hằng phù hợp |
| `@Check(TestValues.B)` | Không | Khởi tạo qua lời gọi phương thức |
| `@Check(TestValues.C)` | Không | Biến có kiểu bao, không phải biến hằng phù hợp |
| `@Check(Math.max(1, 2))` | Không | Lời gọi phương thức |
| `@Check(-5)` | Có về cú pháp/kiểu | Ngôn ngữ không tự kiểm tra quy tắc nghiệp vụ |

Hãy tự giải thích thêm: tại sao `Mode.SAFE` dùng được cho một phần tử enum nhưng `static final Mode selected = Mode.SAFE` lại không dùng được theo cùng cách? Câu trả lời nằm ở việc **hằng enum** và **biến tham chiếu final** là hai dạng khác nhau trong quy tắc giá trị annotation.

Khi kiểm tra một giá trị, hãy lần lượt xác định **kiểu phần tử → dạng giá trị được phép → tính hằng nếu là nguyên thủy/String → chuyển đổi kiểu hợp lệ → mặc định hay giá trị tường minh → ràng buộc nghiệp vụ của bên đọc**.
