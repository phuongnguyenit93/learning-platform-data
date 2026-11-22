# `default` như phương án bao phủ trong exhaustive `switch` (Java 21)

**Chủ đề:** Java Core Pattern Matching → Exhaustive switch  
**Môi trường:** Java 21 trở lên. Pattern matching for `switch` chính thức trong JEP 441; bài sử dụng cú pháp ổn định, không cần `--enable-preview`.

## 1. Vì sao `switch` cần một phương án bao phủ?

Một `switch` phân loại giá trị selector qua các nhãn `case`. Nếu chỉ liệt kê vài giá trị hoặc kiểu cụ thể, sẽ có những đầu vào không khớp nhãn nào. Từ khóa **`default`** cung cấp một nhánh dự phòng cho các giá trị **không được nhánh nào khác chọn**, giúp một `switch` expression có thể trả kết quả cho toàn bộ miền đầu vào theo luật của ngôn ngữ.

Ví dụ:

```java
static String describe(Object input) {
    return switch (input) {
        case null -> "NULL";
        case String s -> "TEXT:" + s.length();
        case Integer n -> "INT:" + n;
        default -> "OTHER";
    };
}
```

Với `"abc"`, nhánh `String` trả `TEXT:3`; với `12`, nhánh `Integer` trả `INT:12`; với `2.5`, `true` hay một đối tượng khác, nhánh `default` trả `OTHER`. Đầu vào `null` được xử lý **riêng** bằng `case null`.

**Ý chính:** `default` là cơ chế bao phủ **các trường hợp còn lại theo quy tắc chọn nhánh**, không phải “loại đối tượng mặc định” và cũng không phải công cụ thay thế mọi kiểm tra tính đúng đắn trong nghiệp vụ.

## 2. Exhaustiveness là gì và `default` liên quan thế nào?

Một `switch` được gọi là *exhaustive* nếu compiler có thể xác nhận rằng các nhãn case bao phủ mọi giá trị cần xử lý theo các quy tắc dành cho kiểu selector. Với `switch` **expression**, tính exhaustive là yêu cầu bắt buộc: biểu thức phải tạo ra một giá trị khi hoàn tất bình thường.

```java
// KHÔNG BIÊN DỊCH: thiếu nhánh cho các kiểu Object khác.
static String incomplete(Object value) {
    return switch (value) {
        case String s -> "STRING";
        case Integer i -> "INTEGER";
    };
}
```

Sửa bằng một `default`:

```java
static String complete(Object value) {
    return switch (value) {
        case String s -> "STRING";
        case Integer i -> "INTEGER";
        default -> "OTHER";
    };
}
```

Ở mức kiểm tra exhaustiveness, compiler đã thấy nhánh dự phòng `default`. Tuy nhiên, **không suy ra rằng `null` sẽ đi vào `default`**: với selector `null`, Java 21 có quy tắc riêng được trình bày ở mục 4; `complete(null)` vẫn ném `NullPointerException`.

### `switch` statement có bắt buộc exhaustive không?

Cần phân biệt:

- **`switch` statement truyền thống** với selector như `int`, `String` hoặc `enum` có thể không liệt kê mọi nhãn. Khi không khớp và không có `default`, statement đơn giản kết thúc mà không thực hiện nhánh case nào.
- **Enhanced `switch` statement** trong Java 21 (chẳng hạn dùng type pattern trong case) có yêu cầu exhaustiveness. Một statement chứa pattern matching không được coi là “tự do thiếu case” chỉ vì nó không trả giá trị.
- **`switch` expression** luôn phải exhaustive; đây là lý do người học thấy `default` xuất hiện thường xuyên khi selector khai báo kiểu rộng như `Object`.

Mục đích `default` trong cả statement và expression là diễn đạt chính sách cho các trường hợp còn lại. Nhưng chỉ thêm `default` để cho code biên dịch, không xác định dữ liệu nào rơi vào nhánh này, có thể che giấu lỗi nghiệp vụ.

## 3. `default` trong `switch` với type pattern

Type pattern kiểm tra kiểu runtime và giới thiệu biến đã gắn kiểu. Có thể dùng `default` sau các type pattern:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String text -> "STRING:" + text;
        case Number number -> "NUMBER:" + number;
        default -> "UNKNOWN:" + value.getClass().getSimpleName();
    };
}
```

Trong ví dụ này:

1. `String` khớp `case String text`.
2. `Integer`, `Double`, `Long` và các subtype khác của `Number` có thể khớp `case Number number`.
3. `Boolean` hoặc một object không thuộc hai kiểu trên vào `default`; ở đây có thể gọi `value.getClass()` vì `null` đã được xử lý trước.
4. Biến `text` và `number` chỉ nằm trong nhánh khớp. Nhánh `default` không tự có pattern variable; nếu cần dữ liệu, dùng selector `value` hoặc xây dựng kết quả từ ngữ cảnh có sẵn.

Để kiểm thử nhánh dự phòng, đừng chỉ thử hai kiểu đã có `case`; hãy truyền ít nhất một đối tượng **thực sự không khớp** bất kỳ type pattern nào phía trước.

## 4. `default` không tự bắt `null`

Điểm dễ nhầm: trong Java 21, `null` không khớp type pattern cấp ngoài. Nếu selector của `switch` là `null` và không có nhãn xử lý `null` thích hợp, thông thường `switch` ném `NullPointerException` — **dù có `default`**.

```java
static String withoutNullCase(Object input) {
    return switch (input) {
        case String s -> "STRING";
        default -> "OTHER";
    };
}
// withoutNullCase(null) ném NullPointerException.
```

Nếu `null` là giá trị hợp lệ theo hợp đồng phương thức, dùng một nhánh riêng:

```java
static String withNullCase(Object input) {
    return switch (input) {
        case null -> "NULL";
        case String s -> "STRING";
        default -> "OTHER";
    };
}
```

Java 21 còn cho phép ghép `null` với nhánh dự phòng thành **một nhãn duy nhất**:

```java
static String withCombinedCase(Object input) {
    return switch (input) {
        case String s -> "STRING";
        case null, default -> "NOT_STRING";
    };
}
```

`withCombinedCase(null)` trả `NOT_STRING`; `withCombinedCase(123)` cũng vậy. Cú pháp `case null, default` là trường hợp kết hợp nhãn được hỗ trợ riêng, không có nghĩa có thể ghép tùy ý mọi `default` với các nhãn khác.

**Thiết kế đề xuất:** tách `case null` khi cần một lỗi hoặc kết quả khác biệt; dùng `case null, default` khi chính sách nghiệp vụ coi `null` và mọi trường hợp còn lại tương đương.

## 5. `default` và guard `when`

Guard `when` chia nhỏ một type pattern theo điều kiện. Nếu guard không đạt, `switch` tiếp tục xét nhánh phù hợp khác:

```java
static String numberBucket(Object input) {
    return switch (input) {
        case null -> "NULL";
        case Integer n when n < 0 -> "NEGATIVE";
        case Integer n when n == 0 -> "ZERO";
        case Integer n -> "POSITIVE";
        default -> "NOT_INTEGER";
    };
}
```

Với `-1`, nhánh âm khớp; với `0`, nhánh zero; với `1`, nhánh `Integer n` tổng quát; với `"1"`, `default`.

Điều quan trọng: **`default` không thay thế nhánh tổng quát của cùng một kiểu khi muốn xử lý riêng kiểu đó.** Nếu bỏ `case Integer n -> "POSITIVE"`, giá trị `1` sẽ vào `default` và nhận `NOT_INTEGER`, mặc dù nó là `Integer`. Compiler vẫn có thể chấp nhận vì `default` giúp exhaustive, nhưng kết quả sai nghiệp vụ.

Hãy đặt nhánh có guard trước nhánh cùng kiểu không có guard; nếu đặt `case Integer n` trước `case Integer n when n < 0`, compiler có thể báo lỗi **dominance** vì nhánh phía sau bị che.

Guard nên rõ, ít tác dụng phụ, dễ dựng dữ liệu biên. Test tối thiểu cho ví dụ trên: `null`, `-1`, `0`, `1`, và một giá trị không phải `Integer`.

## 6. `default` khi làm việc với enum

Với một enum đã biết đầy đủ các hằng:

```java
enum Direction { LEFT, RIGHT }

static String directionText(Direction direction) {
    return switch (direction) {
        case LEFT -> "L";
        case RIGHT -> "R";
    };
}
```

Ở thời điểm biên dịch, compiler biết tập các hằng trong `Direction`, nên `switch` expression trên có thể exhaustive **mà không cần viết `default`**. `direction == null` vẫn là một trường hợp riêng: nếu không có `case null`, gọi phương thức với `null` có thể ném `NullPointerException`.

Nếu thêm `UP` vào enum và biên dịch lại phần `switch`, nhánh còn thiếu có thể bị compiler phát hiện. Nếu ngay từ đầu viết:

```java
static String directionTextWithDefault(Direction direction) {
    return switch (direction) {
        case LEFT -> "L";
        case RIGHT -> "R";
        default -> "?";
    };
}
```

thì khi enum thêm một hằng mới, `default` có thể âm thầm nhận nó. Đó có thể là điều mong muốn với giao diện có fallback, nhưng cũng có thể làm bỏ sót yêu cầu nghiệp vụ phải xử lý riêng `UP`.

**Câu hỏi trước khi chọn `default`:** việc xuất hiện một enum constant mới cần làm code hiện có **không biên dịch cho tới khi được cập nhật**, hay có thể trả về một kết quả dự phòng? Tùy hợp đồng nghiệp vụ để quyết định, không đặt `default` theo thói quen.

## 7. Sealed hierarchy: exhaustive mà không cần `default`

Một tập subtype đóng có thể được mô hình hóa bằng `sealed interface` và các record triển khai:

```java
sealed interface Outcome permits Ok, Err {}
record Ok(String message) implements Outcome {}
record Err(int code) implements Outcome {}

static String render(Outcome outcome) {
    return switch (outcome) {
        case Ok ok -> "OK:" + ok.message();
        case Err err -> "ERR:" + err.code();
    };
}
```

Đây là các khai báo **minh họa** cần đặt vào một file/class phù hợp. Khi `Outcome` chỉ có hai subtype được cho phép và các case bao phủ cả hai, compiler có thể chứng minh exhaustiveness mà không cần `default`.

Nếu thêm một subtype `Pending` được phép vào hierarchy và biên dịch lại, phương thức `render` có thể bị yêu cầu bổ sung `case Pending p` trước khi code được chấp nhận. Đặc điểm này rất có ích với domain model mà mỗi biến thể mới **phải có hành vi riêng**.

Đối chiếu:

| Chiến lược | Lợi ích | Rủi ro/đánh đổi |
| --- | --- | --- |
| Liệt kê đủ case sealed/enum, không có `default` | Compiler giúp phát hiện trường hợp mới khi biên dịch lại | Phải cập nhật switch khi miền kiểu được mở rộng |
| Thêm `default` có kết quả an toàn | Ứng dụng có chính sách dự phòng rõ | Có thể che trường hợp mới chưa được xử lý riêng |
| `default -> throw ...` | Từ chối trạng thái không mong đợi tại runtime | Khi có biến thể mới, mã vẫn có thể biên dịch nhưng ném lỗi khi gặp trường hợp đó |
| `case null` riêng | Quy định rõ cách xử lý đầu vào thiếu | Cần thêm nhánh, và không thay thế việc bao phủ các kiểu không null |

Chú ý: **exhaustiveness theo các subtype không có nghĩa tự động “hỗ trợ null”**. Việc một `switch` có thể compile mà không có `default` không loại bỏ nhu cầu test selector `null` khi API cho phép `null`.

## 8. Khi nào nên `default -> throw`?

Trong một số hệ thống, gặp giá trị không nằm trong mô hình mong đợi là **lỗi lập trình hoặc lỗi dữ liệu**, không phải tình huống cần một chuỗi “UNKNOWN” rồi tiếp tục. Khi đó:

```java
static String strict(Object input) {
    return switch (input) {
        case null -> throw new IllegalArgumentException("input missing");
        case String s -> "TEXT:" + s;
        case Integer n -> "INT:" + n;
        default -> throw new IllegalArgumentException(
                "Unsupported type: " + input.getClass().getName());
    };
}
```

`throw` chấm dứt nhánh bằng ngoại lệ và vẫn là cách hợp lệ để xử lý trường hợp không có giá trị trả về bình thường trong `switch` expression. Nó khác với `yield` trong block case: `yield` trả một giá trị cho expression, còn `throw` báo lỗi.

**Chọn theo yêu cầu nghiệp vụ:**

- Dữ liệu lạ là hợp lệ → trả fallback mang ý nghĩa rõ, ví dụ `UNKNOWN`.
- Dữ liệu lạ là lỗi không được phép → ném ngoại lệ có chủ đích và test cả loại lỗi.
- Mọi subtype được phép cần logic riêng → ưu tiên switch exhaustive nhờ enum/sealed, không dùng `default` che thiếu nhánh.

Tránh `default -> null` vô cớ: có thể làm lỗi lan xa, phát sinh `NullPointerException` tại vị trí không liên quan, gây khó chẩn đoán.

## 9. `default` cũng liên quan đến dominance

Khi một type pattern **bao phủ tất cả giá trị không null** của selector, có thể không cần `default` để thỏa điều kiện exhaustiveness. Ví dụ một nhánh `case Object obj` có thể tổng quát đối với các giá trị `Object` không null; lúc đó việc kết hợp thêm `default` sẽ vướng quy tắc nhãn bao phủ hoặc nhãn match-all trùng lặp.

Hãy xem `default` như một nhánh cho **phần miền còn lại thực sự cần bao phủ**, không phải “dòng cuối bắt buộc” sau mọi pattern. Nếu compiler nói một nhãn bị dominated hoặc có nhiều nhãn match-all, phân tích sự bao phủ của các nhãn đứng trước thay vì di chuyển `default` tùy tiện.

Thông thường với các case `String`, `Integer`, `Number` và một selector `Object`, có miền các đối tượng khác chưa được bao phủ — vì vậy `default` là lựa chọn tự nhiên. Với enum/sealed đã liệt kê đủ, việc bỏ `default` có thể tạo rào chắn compile-time tốt hơn.

## 10. Chương trình Java 21 hoàn chỉnh: ba chiến lược bao phủ

Tạo tệp **`DefaultExhaustivenessDemo.java`**. Ví dụ chứa:

- `classify(Object)`: chọn `default` khi giá trị không phù hợp các type pattern trước.
- `traffic(int)`: dùng `default` làm fallback cho mã trạng thái không liệt kê.
- `outcome(Outcome)`: sealed hierarchy có các case đầy đủ, không cần `default`.
- `coalesce(Object)`: minh họa nhãn kết hợp `case null, default`.

```java
public class DefaultExhaustivenessDemo {
    sealed interface Outcome permits Ok, Err {}
    record Ok(String message) implements Outcome {}
    record Err(int code) implements Outcome {}

    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String text when text.isBlank() -> "BLANK";
            case String text -> "TEXT:" + text.length();
            case Integer n when n < 0 -> "NEGATIVE:" + n;
            case Integer n -> "INTEGER:" + n;
            default -> "OTHER:" + value.getClass().getSimpleName();
        };
    }

    static String traffic(int code) {
        return switch (code) {
            case 0 -> "STOP";
            case 1 -> "GO";
            default -> "UNRECOGNIZED:" + code;
        };
    }

    static String outcome(Outcome value) {
        return switch (value) {
            case null -> "NO_OUTCOME";
            case Ok ok -> "OK:" + ok.message();
            case Err err -> "ERR:" + err.code();
        };
    }

    static String coalesce(Object value) {
        return switch (value) {
            case String text -> "STRING";
            case null, default -> "NOT_STRING";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify("  "));
        System.out.println(classify("Java"));
        System.out.println(classify(-2));
        System.out.println(classify(7));
        System.out.println(classify(2.5));
        System.out.println(classify(true));

        System.out.println(traffic(0));
        System.out.println(traffic(9));

        System.out.println(outcome(new Ok("saved")));
        System.out.println(outcome(new Err(404)));
        System.out.println(outcome(null));

        System.out.println(coalesce(null));
        System.out.println(coalesce("hi"));
        System.out.println(coalesce(10));
    }
}
```

Biên dịch và chạy bằng JDK 21 hoặc mới hơn:

```bash
javac --release 21 DefaultExhaustivenessDemo.java
java DefaultExhaustivenessDemo
```

**Standard output chính xác:**

```text
NULL
BLANK
TEXT:4
NEGATIVE:-2
INTEGER:7
OTHER:Double
OTHER:Boolean
STOP
UNRECOGNIZED:9
OK:saved
ERR:404
NO_OUTCOME
NOT_STRING
STRING
NOT_STRING
```

Phân tích:

1. `classify(null)` dùng `case null`; `classify("  ")` vào guard `isBlank()`; `"Java"` vào case `String` chung.
2. `-2` vào nhánh số nguyên âm, `7` vào nhánh `Integer` còn lại.
3. `2.5` là `Double` và `true` là `Boolean`, nên `default` in tên class tương ứng. Vì `null` được tách trước, `value.getClass()` trong default là an toàn trong chương trình này.
4. `traffic(0)` khớp `case 0`; `traffic(9)` vào `default`. Phần dự phòng bao phủ giá trị nguyên không liệt kê.
5. `outcome(new Ok(...))` và `outcome(new Err(...))` khớp các subtype của sealed `Outcome`; `outcome(null)` vào `case null`. Không cần một `default` chỉ để thoả mãn exhaustiveness.
6. `coalesce(null)` và `coalesce(10)` đều chọn `case null, default`; `coalesce("hi")` vào nhánh `String`.

Ví dụ dùng các tính năng chính thức từ Java 21. Nếu môi trường đang dùng JDK 17, cần nâng JDK để biên dịch pattern switch và `when`.

## 11. Thiết kế bộ kiểm thử cho nhánh dự phòng

Để bảo đảm `default` không chỉ “cho qua compiler” mà thực hiện đúng yêu cầu, lập ma trận gồm trường hợp **khớp case cụ thể**, **không khớp case nào**, **đầu vào null**, và **điều kiện guard không đạt**.

| Test input | Lệnh kiểm tra | Kết quả kỳ vọng | Nhánh |
| --- | --- | --- | --- |
| `null` | `classify(null)` | `NULL` | `case null` |
| `"  "` | `classify("  ")` | `BLANK` | `String` có guard |
| `"Java"` | `classify("Java")` | `TEXT:4` | `String` tổng quát |
| `-2` | `classify(-2)` | `NEGATIVE:-2` | `Integer` có guard |
| `7` | `classify(7)` | `INTEGER:7` | `Integer` tổng quát |
| `2.5` | `classify(2.5)` | `OTHER:Double` | `default` |
| `true` | `classify(true)` | `OTHER:Boolean` | `default` |
| `9` | `traffic(9)` | `UNRECOGNIZED:9` | `default` |
| `null` | `coalesce(null)` | `NOT_STRING` | `case null, default` |
| `10` | `coalesce(10)` | `NOT_STRING` | `case null, default` |
| `new Ok("saved")` | `outcome(...)` | `OK:saved` | Sealed subtype |
| `new Err(404)` | `outcome(...)` | `ERR:404` | Sealed subtype |

Một số test biên nên thêm:

- Với số nguyên: `-1`, `0`, `1`; chú ý guard `n < 0` và case còn lại.
- Với chuỗi: `""`, `"\t"`, và `"x"`.
- Nếu `default` ném lỗi: test rằng đúng loại ngoại lệ được ném, thay vì chỉ quan sát lỗi trên console.
- Với enum/sealed: thêm một hằng/subtype mới trong nhánh phát triển để quan sát compiler có yêu cầu cập nhật `switch` hay không.

**Quan trọng:** một test chỉ chạy `default` không thể chứng minh các case trước đúng, và bộ test chỉ chạy “happy path” sẽ không nhận ra fallback vô tình hấp thụ những đầu vào lẽ ra cần xử lý riêng.

## 12. Các lỗi thường gặp khi dùng `default`

| Cách hiểu/viết sai | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Cho rằng `default` bắt cả `null` | `switch(null)` có thể ném `NullPointerException` | `case null` hoặc `case null, default` |
| Đặt `default` mà không xác định nghiệp vụ | Trạng thái không hợp lệ bị bỏ qua âm thầm | Thiết kế mã lỗi, giá trị fallback hoặc exception rõ ràng |
| Dùng `default` thay cho nhánh `Integer` khi guard false | Giá trị Integer hợp lệ đi vào fallback của kiểu khác | Thêm nhánh `case Integer n` sau các guard |
| Luôn thêm `default` cho enum/sealed đã liệt kê đủ | Compiler không còn buộc xem xét mọi biến thể mới khi biên dịch lại | Cân nhắc bỏ default để nhận lợi ích exhaustiveness |
| Đặt type pattern tổng quát trước subtype cụ thể | Nhánh cụ thể bị dominated, không biên dịch | Nhánh hẹp trước, nhánh bao quát sau |
| Dùng `default` cùng một type pattern match-all dư thừa | Có thể vi phạm quy tắc nhãn bao phủ/duplicate match-all | Xác định nhãn nào thực sự đã bao phủ miền còn lại |
| Coi `switch` statement pattern không cần exhaustive | Có thể bị compiler từ chối với enhanced switch statement | Phân biệt statement truyền thống và enhanced statement |
| Viết `default -> null` mà không có chủ đích | Gây lỗi xa nguồn và khó truy vết | Trả kết quả lỗi rõ ràng hoặc `throw` |
| Giả định `default` “là nhánh cuối theo thứ tự chạy” | Nhầm với cơ chế fall-through của colon statement | Hiểu đây là nhãn dự phòng khi không case nào khác được chọn |
| Chỉ test các nhánh cụ thể | Không biết `default` có xử lý đúng đầu vào khác kiểu | Có test riêng cho kiểu/giá trị chưa được liệt kê |

## 13. Bài tập tự luyện

1. Viết `switch (Object input)` có `case null`, `case String s`, `case Number n`, và `default`. Tạo test cho `null`, `"abc"`, `1`, `2.5`, `true`, rồi giải thích nhánh nào được chọn.
2. Thử bỏ `default` trong một `switch` expression nhận `Object` và không có type pattern bao trùm. Quan sát lỗi thiếu exhaustiveness; khôi phục nhánh dự phòng.
3. Viết một ví dụ `case Integer n when n < 0`, `case Integer n when n == 0`, `case Integer n`, `default`; giải thích vì sao `1` không nên rơi vào `default`.
4. Thử gọi một `switch` có `default` nhưng không có `case null` bằng `null`. Kiểm tra chính xác ngoại lệ; sau đó thêm `case null`.
5. Viết `enum Status { NEW, DONE }` với `switch` expression liệt kê đủ hai hằng và không có `default`. Thêm `CANCELED`, biên dịch lại và cập nhật nhánh phù hợp. So sánh phiên bản có `default`.
6. Tạo `sealed interface Message permits Email, Sms` với hai record triển khai. Viết `switch` exhaustive không có `default`; thêm subtype mới và giải thích lợi ích compiler buộc cập nhật xử lý.
7. Thiết kế hai chính sách fallback cho một hàm: `default -> "UNKNOWN"` và `default -> throw new IllegalArgumentException(...)`. Test sự khác biệt bằng đầu vào ngoài dự kiến.
8. Dùng `case null, default` khi `null` và kiểu không hỗ trợ có cùng ý nghĩa; đổi sang hai nhánh riêng khi yêu cầu thông báo lỗi khác nhau.
9. Đối chiếu toàn bộ 15 dòng stdout của `DefaultExhaustivenessDemo`. Bổ sung assertion hoặc test JUnit cho nhánh `default`, guard thất bại và selector null.

**Tiêu chí hoàn thành:** biết lúc nào `default` thực sự cần để exhaustive, hiểu ngoại lệ của `null`, chọn fallback có chủ đích, không vô tình che các enum constant/sealed subtype mới, và viết được test cho cả nhánh dự phòng lẫn các nhánh cụ thể.

**Tham khảo chính thức:**

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21, §14.11 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21, §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
