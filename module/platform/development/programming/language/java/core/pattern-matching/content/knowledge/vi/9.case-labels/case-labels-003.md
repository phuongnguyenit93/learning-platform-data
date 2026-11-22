# Case default và nhánh dự phòng trong Java Pattern Matching

Trong Java, `default` là **nhãn dự phòng** của `switch`: khi selector không được một nhãn `case` áp dụng nào xử lý và có `default` hợp lệ, Java chọn nhánh này. Nó giúp xác định hành vi với giá trị còn lại, nhưng **không phải một type pattern**, không khai báo pattern variable, không tự bắt mọi ngoại lệ, và **không tự xử lý selector `null`**.

Từ Java 21, `switch` hỗ trợ **type pattern**, **record pattern**, guard `when` và `case null` chính thức. Vì thế `default` được dùng trong nhiều tình huống hơn `switch` chỉ có hằng số ở Java 17: nó có thể xử lý một **kiểu không được hỗ trợ**, một **giá trị không thỏa guard**, hoặc một **tổ hợp dữ liệu không khớp record pattern nào**. Đồng thời, compiler có thể chứng minh các nhãn đã bao phủ tất cả kiểu hợp lệ và **không cần `default`** trong một số trường hợp.

Bài này trình bày ý nghĩa, cú pháp, quá trình chọn nhánh, tính đầy đủ (*exhaustiveness*), cách xử lý `null` và chiến lược thiết kế nhánh dự phòng. Các ví dụ có type pattern/`when`/`case null` dùng **Java 21+**; phần `switch` truyền thống cũng có ví dụ **Java 17+**.

## 1. `default` là gì, và khi nào chạy?

Một ví dụ `switch expression` với đầu vào `Object`:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        case null -> "Missing";
        default -> "Unsupported";
    };
}
```

- `describe("Java")` chọn `case String text`.
- `describe(42)` chọn `case Integer number`.
- `describe(null)` chọn `case null`.
- `describe(3.5)` chọn `default`, vì giá trị thực tế là `Double`, không khớp những nhãn dành cho `String` hoặc `Integer`.
- `default` không cấp cho ta biến `text` hay `number`: các pattern variable ấy chỉ có ý nghĩa trong nhánh được match tương ứng.

### Các vai trò trong cú pháp

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Selector expression | `value` trong `switch (value)` | Được đánh giá để lấy giá trị cần phân nhánh |
| Constant case | `case 404 -> ...` | So khớp với một hằng được phép |
| Type pattern case | `case String text -> ...` | Thử kiểu và binding `text` khi khớp |
| Guarded pattern | `case String text when text.isBlank() -> ...` | Pattern phải khớp, rồi guard phải đúng |
| Null case label | `case null -> ...` | Xử lý riêng selector bằng `null` |
| Default label | `default -> ...` | Nhánh dự phòng khi các nhãn khác không áp dụng theo quy tắc của `switch` |

Có thể đọc `default` là “còn lại sau các phép thử hợp lệ”, thay vì “bất cứ chuyện gì xảy ra”. Nếu việc đánh giá selector hoặc guard ném exception thì exception **không được tự động chuyển** vào `default`.

## 2. Quá trình chọn nhánh với pattern và guard

Khi đánh giá `switch`, Java trước tiên **đánh giá selector expression**, sau đó xét những nhãn `case` được áp dụng. Với pattern case, việc áp dụng có thể phụ thuộc kiểu runtime, nội dung record component và `when` guard.

```text
Đánh giá selector expression
            |
            +-- ném exception --------------------> exception lan ra
            |
            v
     giá trị selector
            |
            +-- null, có case null --------------> nhánh case null
            |
            +-- null, thiếu case null -----------> NullPointerException
            |
            +-- khác null
                    |
                    v
            Xét các case hợp lệ
                    |
              pattern/constant/guard
                    |
              +-----+------+
              |            |
            khớp       không nhãn nào áp dụng
              |            |
          nhánh case    nhánh default nếu có
```

Với các pattern được xét theo thứ tự, nếu một type pattern khớp nhưng guard trả về `false`, việc chọn nhánh tiếp tục với nhãn thích hợp tiếp theo. Sau khi không tìm được nhãn áp dụng, `default` mới đóng vai trò dự phòng.

**Không phải mọi trường hợp `case` thất bại đều đồng nghĩa `default` được chạy ngay**: có thể còn một pattern khác ở phía sau, như một `case String text` không có guard để xử lý toàn bộ chuỗi.

## 3. Ví dụ hoàn chỉnh Java 21+: `default` xử lý kiểu lạ và guard không đạt

Lưu thành tệp **`DefaultFallbackDemo.java`**:

```java
public class DefaultFallbackDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "missing";
            case String text when text.isBlank() -> "blank";
            case String text -> "text:" + text;
            case Integer number when number >= 0 -> "nonnegative:" + number;
            case Integer number -> "negative:" + number;
            default -> "unsupported:" + value.getClass().getSimpleName();
        };
    }

    static String onlyGuard(Object value) {
        return switch (value) {
            case null -> "null";
            case String text when text.length() > 3 -> "long:" + text;
            default -> "fallback";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify(" "));
        System.out.println(classify("Java"));
        System.out.println(classify(3));
        System.out.println(classify(-2));
        System.out.println(classify(3.5));
        System.out.println(onlyGuard("Go"));
        System.out.println(onlyGuard("Java"));
        System.out.println(onlyGuard(42));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac DefaultFallbackDemo.java
java DefaultFallbackDemo
```

Đầu ra chính xác:

```text
missing
blank
text:Java
nonnegative:3
negative:-2
unsupported:Double
fallback
long:Java
fallback
```

Cách đọc kết quả:

1. `null` được `case null` xử lý; không đi tới `default`.
2. `" "` khớp `String` và `isBlank()` là `true`; chọn nhánh `blank`.
3. `"Java"` khớp pattern `String`, guard `isBlank()` là `false`, nhưng nhánh `case String text` tiếp theo vẫn khớp. Vì vậy `default` không chạy.
4. `3` khớp `Integer` và guard không âm; `-2` không qua guard nhưng được `case Integer number` tiếp theo xử lý.
5. `3.5` là `Double`, không khớp các type pattern `String`/`Integer`, nên chọn `default`. Lời gọi `value.getClass()` trong nhánh dự phòng là an toàn ở ví dụ này vì selector `null` đã được xử lý riêng.
6. Trong `onlyGuard`, `"Go"` là `String` nhưng `text.length() > 3` sai; không có nhánh `String` khác, nên chọn `default`. `"Java"` qua guard nên chọn `long:Java`, còn `42` không khớp type pattern nên cũng dùng `default`.

Vì thế `default` là **fallback của cả quá trình chọn nhánh**, không phải “else riêng cho một pattern”.

## 4. `default` không bắt `null`

Điểm đặc biệt quan trọng trong Java 21:

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "text";
        default -> "other";
    };
}
```

Với `classify(null)`, `switch` **ném `NullPointerException`**. `default` không nhận `null` thay cho `case null`. Type pattern `String text` cũng không match `null`.

Muốn xử lý `null` như một trạng thái nghiệp vụ hợp lệ:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text";
        default -> "other";
    };
}
```

Có thể dùng nhãn kết hợp khi chính sách cho `null` và giá trị không được hỗ trợ là như nhau:

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "text:" + text;
        case null, default -> "other-or-null";
    };
}
```

`case null, default` được hỗ trợ từ Java 21. Một nhãn `case null` **không thể tùy tiện ghép với một type pattern** như `case null, String text`, vì pattern variable `text` không có binding khi selector là `null`.

**Điểm cần nhớ:** sự hiện diện của `default` là điều kiện giúp bao phủ các kiểu không khớp ở compile time, nhưng **không hứa hẹn rằng tất cả giá trị runtime, đặc biệt `null`, đều đi tới `default`**.

## 5. `switch expression` và `switch statement` dùng `default` khác nhau thế nào?

### 5.1. `switch expression`: phải cung cấp giá trị hoặc ném exception

`switch expression` tạo ra một giá trị:

```java
int score = switch (status) {
    case "OK" -> 100;
    case "RETRY" -> 50;
    default -> 0;
};
```

*Đây là đoạn mã minh họa với biến `status` có kiểu `String`, không phải một lớp đầy đủ.*

Mỗi nhánh được chọn phải hoàn thành theo các quy tắc của `switch expression`, chẳng hạn cung cấp giá trị tương thích hoặc ném exception. Nếu dùng một block với nhiều câu lệnh, sử dụng `yield`:

```java
int score = switch (status) {
    case "OK" -> 100;
    default -> {
        System.out.println("Unknown status: " + status);
        yield 0;
    }
};
```

Một `switch expression` **phải exhaustive**: compiler phải chứng minh các trường hợp thuộc miền giá trị hợp lệ được bao phủ. Với selector kiểu `Object` và chỉ có pattern `String`/`Integer`, thiếu `default` hoặc các nhánh bao phủ còn lại thường dẫn tới lỗi biên dịch:

```java
// KHÔNG BIÊN DỊCH trong Java 21:
// static String invalid(Object input) {
//     return switch (input) {
//         case String text -> text;
//     };
// }
```

Lý do: có thể nhận `Integer`, `Double` hoặc nhiều kiểu khác; compiler không thấy nhãn bao phủ các giá trị này. Thêm `default` có thể biến `switch expression` thành exhaustive.

### 5.2. `switch statement`: thực hiện hành động, không nhất thiết tạo giá trị

`switch statement` dạng mũi tên:

```java
switch (status) {
    case "OK" -> System.out.println("success");
    case "RETRY" -> System.out.println("try again");
    default -> System.out.println("unrecognized");
}
```

Với các nhánh mũi tên `->`, không có fall-through sang nhánh sau.

Với cú pháp dấu hai chấm truyền thống, `default:` là một nhãn trong nhóm câu lệnh, và **có thể xảy ra fall-through nếu thiếu `break`**. Khi dùng nhãn có pattern variable, Java còn có các hạn chế nhằm tránh đường đi khiến biến pattern chưa được khởi tạo. Để code dễ đọc và ít lỗi, ưu tiên mũi tên `->` khi không cần chủ đích fall-through.

**Phân biệt tính đầy đủ:** `switch statement` truyền thống chỉ có nhãn hằng có thể bỏ `default` và không làm gì nếu không khớp nhãn nào. Còn **enhanced switch statement** có pattern hoặc nhãn `null` của Java 21 phải thỏa yêu cầu exhaustive; `default` là một cách thông dụng để đạt yêu cầu đó.

### 5.3. Ví dụ Java 17+ hoàn chỉnh

Lưu **`ClassicDefaultDemo.java`**:

```java
public class ClassicDefaultDemo {
    static String byCode(int code) {
        return switch (code) {
            case 200 -> "OK";
            case 404 -> "NOT_FOUND";
            default -> "UNMAPPED";
        };
    }

    static void withoutDefault(int code) {
        switch (code) {
            case 200:
                System.out.println("statement: OK");
                break;
            case 404:
                System.out.println("statement: NOT_FOUND");
                break;
        }
        System.out.println("statement: done");
    }

    public static void main(String[] args) {
        System.out.println(byCode(200));
        System.out.println(byCode(503));
        withoutDefault(503);
    }
}
```

```bash
javac ClassicDefaultDemo.java
java ClassicDefaultDemo
```

```text
OK
UNMAPPED
statement: done
```

Ở `byCode(503)`, `default` tạo giá trị `UNMAPPED` cho `switch expression`. Ở `withoutDefault(503)`, `switch statement` truyền thống không có nhãn khớp, nên không in trong khối `switch`; chương trình tiếp tục và in `statement: done`. Đây là khác biệt dễ gặp khi chuyển từ cấu trúc `switch` cũ sang pattern matching.

## 6. Khi nào không cần `default`: exhaustive với sealed và enum

`default` rất hữu ích khi input có miền mở, chẳng hạn `Object` hoặc dữ liệu đến từ API bên ngoài. Nhưng với một tập hợp kiểu được giới hạn và compiler có thể chứng minh đã bao phủ hết, `default` **có thể không cần**.

### 6.1. Sealed hierarchy

Giả sử Java 21 có một `sealed interface` với hai trường hợp được phép:

```java
sealed interface Response permits Success, Failure {}
record Success(String data) implements Response {}
record Failure(int code) implements Response {}
```

`switch expression` sau có thể exhaustive mà không cần `default`:

```java
static String show(Response response) {
    return switch (response) {
        case Success success -> "success:" + success.data();
        case Failure failure -> "failure:" + failure.code();
    };
}
```

Compiler biết `Response` chỉ có thể được triển khai bởi `Success` và `Failure` trong cấu trúc này. Nếu sau này thêm một nhánh được phép khác và biên dịch lại các nguồn liên quan, chỗ `switch` thường cần được cập nhật. Bỏ `default` giúp compiler chỉ ra chỗ xử lý chưa đủ. Nếu một bản nhị phân cũ đã được biên dịch với giả định exhaustive nhưng hierarchy thay đổi không tương thích, Java có thể ném `MatchException` khi không có nhánh runtime nào áp dụng; cần biên dịch lại những lớp liên quan.

Ví dụ đầy đủ, lưu **`ExhaustiveDemo.java`**:

```java
sealed interface Response permits Success, Failure {}
record Success(String data) implements Response {}
record Failure(int code) implements Response {}

public class ExhaustiveDemo {
    static String show(Response value) {
        return switch (value) {
            case Success success -> "success:" + success.data();
            case Failure failure -> "failure:" + failure.code();
        };
    }

    public static void main(String[] args) {
        System.out.println(show(new Success("ok")));
        System.out.println(show(new Failure(403)));
        try {
            System.out.println(show(null));
        } catch (NullPointerException ex) {
            System.out.println("null: NullPointerException");
        }
    }
}
```

```bash
javac ExhaustiveDemo.java
java ExhaustiveDemo
```

```text
success:ok
failure:403
null: NullPointerException
```

**Exhaustive không đồng nghĩa với xử lý `null`:** thiếu `case null` nên `show(null)` vẫn ném NPE. Điều này không phủ nhận việc các kiểu khác `null` đã được compiler bao phủ.

### 6.2. Enum

Với `enum`, nếu một `switch expression` đã có case cho **mọi hằng enum**, compiler có thể không cần `default`. Điều này thường giúp nhận ra khi có hằng enum mới và phải cập nhật xử lý cho trường hợp mới.

Tuy vậy, lúc thiết kế nên cân nhắc: một nhánh `default` chung có thể làm thay đổi yêu cầu nghiệp vụ khi enum hoặc sealed hierarchy được mở rộng. Đối với miền kiểu đóng mà **mỗi trường hợp cần xử lý riêng**, bỏ `default` thường giúp phát hiện thiếu case trong quá trình biên dịch lại. Đối với dữ liệu không được hỗ trợ từ bên ngoài, có `default` rõ ràng vẫn hợp lý.

## 7. Không thể luôn thêm `default` cạnh một unconditional pattern

Trong Java 21, pattern có thể bao phủ tất cả giá trị khác `null` của selector, chẳng hạn:

```java
static String describe(Object value) {
    return switch (value) {
        case Object obj -> "object";
    };
}
```

Ở đây `case Object obj` là **unconditional pattern** đối với selector kiểu `Object`: mọi đối tượng khác `null` đều thuộc `Object`. Thử thêm `default` riêng trong cùng một `switch` sẽ gây lỗi biên dịch:

```java
// KHÔNG BIÊN DỊCH:
// static String describe(Object value) {
//     return switch (value) {
//         case Object obj -> "object";
//         default -> "unreachable";
//     };
// }
```

Compiler báo rằng `switch` có cả unconditional pattern và `default`. Vì vậy không phải lúc nào cũng được “thêm `default` cho chắc”. Nếu chỉ cần một nhánh tổng quát cho mọi đối tượng, dùng unconditional pattern theo đúng phạm vi và xử lý `null` riêng nếu muốn hỗ trợ `null`.

Ngoài ra, compiler áp dụng **dominance checking** với type patterns để tránh những nhánh cụ thể bị một pattern quá rộng phía trước che khuất:

```java
// KHÔNG BIÊN DỊCH: nhánh String bị CharSequence đứng trước che khuất.
// switch (value) {
//     case CharSequence seq -> ...;
//     case String text -> ...;
//     default -> ...;
// }
```

Hãy đặt các pattern cụ thể ở vị trí hợp lý trước pattern rộng; dùng `default` cho giá trị còn lại và tránh nhầm lẫn giữa nhánh có pattern với nhánh dự phòng không có pattern.

## 8. `default` không chia sẻ pattern variable từ nhánh trước

Ví dụ:

```java
switch (value) {
    case String text -> System.out.println(text.toUpperCase());
    case Integer number -> System.out.println(number + 1);
    case null -> System.out.println("missing");
    default -> System.out.println("unsupported");
}
```

Nhánh `default` không thể truy cập `text` hay `number`, bởi vì khi nó được chọn, không có bảo đảm một trong hai pattern trước đó đã khớp. `default` không khai báo binding của riêng nó. Nếu cần thông tin về giá trị chưa hỗ trợ, hãy dùng **biến selector được khai báo trước**, ví dụ:

```java
default -> System.out.println("unsupported: " + value.getClass().getName());
```

Trong ví dụ này có thể gọi `getClass()` khi một nhánh `case null` đã tách `null` và không có lỗi khác trước đó. Nếu thiếu `case null`, giá trị `null` làm `switch` ném NPE trước khi chạy `default`.

Nếu cần xử lý một kiểu mới, khai báo một type pattern riêng:

```java
case java.time.LocalDate date -> System.out.println(date.getYear());
```

Đây là một case mới có binding `date`; không phải cách dùng lại biến pattern của case trước.

## 9. Nhánh dự phòng nên trả giá trị gì?

`default` là nơi **xác định chính sách khi input không được các nhánh chuyên biệt hỗ trợ**. Có ba lựa chọn phổ biến:

1. **Giá trị dự phòng hợp lệ** — thích hợp với UI/hiển thị hoặc báo cáo: `default -> "UNKNOWN"`. Cần làm rõ giá trị này có được người dùng hoặc các xử lý phía sau chấp nhận không.
2. **Từ chối đầu vào một cách tường minh** — thích hợp với invariant/domain chặt: `default -> throw new IllegalArgumentException(...)`.
3. **Ghi nhận thông tin rồi trả fallback** — hữu ích khi muốn quan sát loại đầu vào chưa hỗ trợ: dùng block `default -> { log(...); yield value; }` trong `switch expression`.

Không dùng `default` như một cách che giấu dữ liệu bất thường khi ứng dụng cần phát hiện loại input chưa được hỗ trợ. Không nên trả `null` tùy tiện làm fallback nếu các lệnh gọi phía sau sẽ dereference nó.

### Ví dụ: fallback mặc định, fail-fast và gộp `null`

Lưu **`FallbackPolicyDemo.java`** (Java 21+):

```java
public class FallbackPolicyDemo {
    static String strict(Object input) {
        return switch (input) {
            case null -> "missing";
            case String text -> "text:" + text;
            case Integer number -> "integer:" + number;
            default -> throw new IllegalArgumentException(
                    "Unsupported: " + input.getClass().getSimpleName());
        };
    }

    static String combined(Object input) {
        return switch (input) {
            case String text -> "text:" + text;
            case null, default -> "other-or-null";
        };
    }

    public static void main(String[] args) {
        System.out.println(strict("hello"));
        System.out.println(strict(null));
        try {
            System.out.println(strict(2.5));
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
        System.out.println(combined(null));
        System.out.println(combined(2.5));
    }
}
```

```bash
javac FallbackPolicyDemo.java
java FallbackPolicyDemo
```

```text
text:hello
missing
Unsupported: Double
other-or-null
other-or-null
```

`strict` coi kiểu không hỗ trợ là lỗi và ném `IllegalArgumentException` có thông điệp rõ. `combined` chủ động gộp `null` cùng loại không được hỗ trợ vào cùng một fallback. Hai chính sách khác nhau; hãy chọn theo hợp đồng dữ liệu thực tế.

## 10. Lưu ý về guard và ngoại lệ

Trong ví dụ:

```java
return switch (value) {
    case String text when text.length() >= 4 -> "long text";
    default -> "other";
};
```

Nếu `value` là chuỗi ngắn, pattern `String text` đã khớp nhưng guard trả về `false`, nên `default` có thể được chọn. Còn nếu biểu thức trong guard hoặc việc lấy selector ném exception, `default` **không tự bắt exception** đó. Xử lý exception bằng chính sách lỗi thích hợp, chẳng hạn `try/catch` ở ranh giới nơi thật sự cần phục hồi.

Với record patterns, có thể có các pattern chỉ áp dụng khi thành phần đúng kiểu hoặc có cấu trúc phù hợp. Khi pattern thành phần không khớp mà không có pattern tiếp theo, `default` là nhánh dự phòng hợp lệ cho đối tượng khác `null` — nhưng không phải công cụ để biến một lỗi truy cập dữ liệu thành match thất bại.

**Không đặt `default` vào guard** như thể `default when ...` là một guarded pattern: `when` gắn với **pattern case** và kiểm tra điều kiện sau khi pattern đã khớp, không gắn với nhãn `default`. Nếu muốn hai fallback theo điều kiện, hãy đưa điều kiện đó vào thân `default` hoặc tạo các pattern/guard phù hợp ở các nhánh trước.

## 11. Quy tắc cú pháp và những sai lầm thường gặp

| Sai lầm | Giải thích đúng |
| --- | --- |
| Nghĩ `default` bắt cả `null` | Trong Java 21, selector `null` thiếu `case null` gây `NullPointerException` |
| Nghĩ `default` là một type pattern | `default` là nhãn dự phòng; không kiểm tra kiểu hay tạo pattern variable |
| Nghĩ guard sai sẽ luôn đi thẳng `default` | Có thể còn một `case` khác áp dụng, ví dụ `case String text` không guard |
| Đưa `default` vào `switch expression` rồi quên trả giá trị | Nhánh phải cung cấp giá trị bằng expression/`yield` hoặc kết thúc bằng `throw` |
| Bỏ `default` trong `switch expression` trên `Object` mà không exhaustive | Compiler từ chối nếu các nhãn không bao phủ những kiểu có thể tới |
| Bỏ `default` trong `switch statement` truyền thống | Có thể hợp lệ; khi không case khớp, statement tiếp tục mà không thực hiện nhóm nào |
| Tưởng `switch statement` có pattern cũng luôn được bỏ `default` | Enhanced switch dùng pattern/`null` phải exhaustive |
| Tưởng thiếu `default` luôn là lỗi | Enum/sealed hoặc unconditional pattern có thể bao phủ kiểu mà không cần `default` |
| Ghép unconditional pattern với `default` | Java từ chối khi đã có pattern bao phủ toàn bộ kiểu selector |
| Gọi biến pattern của `case String text` trong `default` | Biến ấy không nằm trong scope của `default` |
| Dùng `default` thay cho `catch` | Exception lúc đánh giá selector, guard hoặc thân nhánh không tự chuyển vào `default` |
| Dùng `default:` với cú pháp cũ mà quên `break` | Có thể dẫn đến fall-through; cú pháp `->` rõ ràng hơn nếu không cần rơi xuống |

Một quy tắc về **vị trí**: thường đặt `default` cuối khối để người đọc nhận ra đây là hành vi dự phòng. Đối với pattern case, luôn chú ý **thứ tự, dominance và tính exhaustive** theo luật của compiler; thứ tự cách viết có thể thay đổi nhánh được chọn khi có pattern rộng và guard.

## 12. Checklist thiết kế và kiểm thử

Khi viết hoặc review `switch` có `default`:

1. **Xác định kiểu tĩnh và miền giá trị của selector.** Nó là `Object`, `String`, `enum` hay sealed hierarchy?
2. **Xem loại `switch`.** Expression cần exhaustive; statement truyền thống và enhanced statement có quy tắc riêng.
3. **Kiểm tra null.** Nếu null hợp lệ, có `case null` hay `case null, default` trong Java 21+ không? Nếu null bị cấm, có quy ước từ chối đầu vào rõ ràng không?
4. **Duyệt từng case có pattern và `when`.** Khi guard sai, còn case nào có thể xử lý cùng kiểu hay phải đi tới `default`?
5. **Đánh giá chính sách fallback.** Trả giá trị đại diện, ném lỗi domain, hay ghi nhận rồi trả fallback?
6. **Kiểm tra các trường hợp exhaustive.** Với sealed/enum, liệu để compiler bắt buộc cập nhật từng case có tốt hơn che mọi nhánh mới bằng `default`?
7. **Không phụ thuộc pattern variable ở `default`.** Sử dụng selector, dữ liệu đã xác thực hoặc khai báo pattern mới.
8. **Kiểm tra tình huống khó:** giá trị khớp pattern, giá trị khác kiểu, guard đúng/sai, `null`, nhánh mới của enum/sealed và exception từ các biểu thức liên quan.
9. **Biên dịch đúng Java version.** Pattern matching cho `switch` và `case null` được chuẩn hóa ở Java 21. Java 17 có `switch expression` với hằng số nhưng không dùng những pattern/`when` của ví dụ Java 21.
10. **Kiểm tra đầu ra và tác dụng phụ.** Đặc biệt chú ý `yield` trong block của `switch expression`, `break` của statement truyền thống và không để fallback che mất lỗi thật.

### Tóm tắt các tình huống

```text
switch (value) {
  case String text -> ...;
  case Integer number -> ...;
  case null -> ...;
  default -> ...;
}

value == "Java"  -> String case
value == 42      -> Integer case
value == 3.14    -> default
value == null    -> case null

Nếu bỏ case null: null -> NullPointerException, không vào default.
Nếu các nhãn case đã exhaustive: có thể không cần default.
Nếu đã có unconditional pattern: không thêm default riêng.
```

**Ghi nhớ:** `default` định nghĩa chính sách cho trường hợp không có nhãn `case` nào áp dụng; nó không đảm nhiệm kiểm tra kiểu, không cung cấp pattern variable và không thay thế `case null`. Sử dụng `default` khi thật sự tồn tại các giá trị ngoài tập trường hợp đã phân loại; với miền đóng exhaustive, hãy cân nhắc để compiler giúp kiểm tra tính đầy đủ.

## Tài liệu tham khảo

- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): pattern labels, `when`, dominance, type coverage, `case null` và `case null, default`.
- [Oracle Java 21 — Switch Expressions](https://docs.oracle.com/en/java/javase/21/language/switch-expressions.html): cú pháp `switch expression`, `yield` và giá trị trả về.
- [Java Language Specification 21 — `14.11 switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11) và [`15.28 switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): quy tắc exhaustiveness và thực thi.
