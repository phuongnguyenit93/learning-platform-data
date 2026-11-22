# Static analysis cho switch exhaustiveness trong Java 21

## 1. Mục tiêu: phát hiện nhánh còn thiếu trước khi chạy chương trình

Một `switch` không xử lý hết những giá trị đầu vào hợp lệ có thể tạo lỗi khó tìm. Ví dụ, hôm nay một hệ thống có hai loại kết quả `Success` và `Failure`; ngày mai thêm `Retry` nhưng quên cập nhật phần xử lý. Nếu không có cơ chế kiểm tra, nhánh mới có thể bị bỏ qua hoặc bị đưa vào một `default` quá rộng.

**Switch exhaustiveness** (tính bao phủ đầy đủ của `switch`) là việc xác định liệu các nhãn `case` có đủ để xử lý **toàn bộ tập giá trị được hệ kiểu cho phép** hay chưa. Trong Java 21, compiler thực hiện một phần phân tích này **ngay khi biên dịch**. Đây chính là nền tảng của **static analysis cho switch exhaustiveness** trong chủ đề *Build và tooling*.

Bài này giúp bạn:

- Hiểu khi nào `javac` bắt buộc `switch` phải exhaustive, và khi nào không.
- Dùng `enum`, `sealed interface/class`, type patterns và record patterns để compiler kiểm tra các nhánh.
- Nhận biết `when` chỉ lọc một nhánh, không tự chứng minh mọi giá trị cùng kiểu đều đã được xử lý.
- Hiểu sự khác nhau giữa `case null`, `default` và một pattern bao quát.
- Biết phân biệt lỗi **non-exhaustive switch** với lỗi **dominated case label**.
- Tích hợp kiểm tra vào lệnh `javac`, Maven, Gradle và CI, đồng thời viết regression tests cho hành vi từng nhánh.
- Hiểu giới hạn giữa kiểm tra tĩnh ở build time và lỗi runtime khi dữ liệu hoặc binary thay đổi.

**Phiên bản:** Ví dụ chính dùng **Java 21**: pattern matching for `switch` được chuẩn hóa qua **JEP 441**, record patterns qua **JEP 440**. Các tính năng này không cần `--enable-preview` ở Java 21. `switch expression` đã là tính năng chuẩn trước Java 21, nhưng pattern cases/`when` có lịch phát triển riêng.

## 2. Exhaustiveness là gì và compiler đang chứng minh điều gì?

Xét một kiểu enum:

```java
enum Stage { NEW, RUNNING, DONE }
```

Một `switch expression` như sau bao phủ cả ba hằng enum:

```java
static int stageWeight(Stage stage) {
    return switch (stage) {
        case NEW -> 1;
        case RUNNING -> 2;
        case DONE -> 3;
    };
}
```

Compiler xác nhận rằng, đối với một giá trị `Stage` **khác null** phù hợp với định nghĩa enum tại thời điểm biên dịch, có nhánh xử lý tương ứng. Do đó không cần `default`.

Nhưng nếu xóa `case DONE`:

```java
// KHÔNG BIÊN DỊCH: switch expression không bao phủ Stage.DONE.
static int incomplete(Stage stage) {
    return switch (stage) {
        case NEW -> 1;
        case RUNNING -> 2;
    };
}
```

Compiler Java sẽ báo lỗi tương đương **“the switch expression does not cover all possible input values”**.

Điều này kiểm tra **độ bao phủ theo kiểu tĩnh**, không chứng minh biểu thức trong mỗi nhánh đúng về nghiệp vụ. Ví dụ, `case DONE -> -999` vẫn làm `switch` exhaustive dù giá trị trả về có thể sai.

### 2.1. Các nguồn tạo tính exhaustive

Trong Java 21, compiler có thể xác định độ bao phủ dựa trên:

- **Hằng enum:** đủ mọi hằng enum ở những `case` không bị guard.
- **Sealed hierarchy:** các nhánh bao phủ mọi subtype được phép của kiểu selector.
- **Type pattern bao quát:** ví dụ một pattern không guard phù hợp với toàn bộ các giá trị khác null của selector.
- **Record patterns:** trong những trường hợp compiler chứng minh được tập các record patterns bao phủ kiểu của selector, kể cả khi có các component lồng.
- **`default`:** một nhánh fallback cho các giá trị không được các nhánh trước xử lý.

Không phải mọi biểu thức `when` đều góp phần tạo độ bao phủ. Nếu có `case Success(var v) when v != null`, nó **không bao phủ mọi `Success`**, vì `v` có thể bằng null.

### 2.2. Exhaustive không đồng nghĩa xử lý null

Một `switch` có thể exhaustive về kiểu nhưng **vẫn ném `NullPointerException` khi selector là null**, nếu không có chính sách xử lý null. Ví dụ `stageWeight` ở trên không có `case null`. Nếu hợp đồng yêu cầu trả giá trị riêng cho null, thêm nhánh:

```java
static int stageWeightOrZero(Stage stage) {
    return switch (stage) {
        case null -> 0;
        case NEW -> 1;
        case RUNNING -> 2;
        case DONE -> 3;
    };
}
```

Tập enum vẫn được bao phủ nhờ `NEW/RUNNING/DONE`; `case null` làm rõ **hành vi đối với null**. Đừng coi `default` là cách tự động bắt null trong mọi pattern switch: không có `case null`, selector null thường gây `NullPointerException`.

## 3. Dùng sealed hierarchy để compiler nhắc xử lý subtype mới

Đây là trường hợp static exhaustiveness đặc biệt hữu ích. Cho:

```java
sealed interface Result permits Success, Retry, Failure {}

record Success(String value) implements Result {}
record Retry(int seconds) implements Result {}
record Failure(String reason) implements Result {}
```

Một `sealed interface` chỉ cho phép những implementation được khai báo theo quy tắc của `permits`. Các record trên là `final` theo ngữ nghĩa record, nên tập subtype hợp lệ tại compile time được giới hạn rõ.

Viết `switch expression`:

```java
static String describe(Result result) {
    return switch (result) {
        case null -> "no-result";
        case Success(var value) when value != null && !value.isBlank()
                -> "success:" + value;
        case Success(var value) -> "invalid-success";
        case Retry(var seconds) when seconds > 0 -> "retry:" + seconds;
        case Retry(var seconds) -> "invalid-retry";
        case Failure(var reason) -> "failure:" + reason;
    };
}
```

**Không cần `default`:** mọi `Success`, `Retry` và `Failure` đều có nhánh không guard tương ứng, trong khi hai nhánh có `when` chỉ xử lý trường hợp hẹp hơn. `case null` làm rõ đầu vào null.

Nhờ cách viết này, nếu sửa hierarchy để cho phép một subtype mới, ví dụ `Cancelled`, mà quên cập nhật `describe`, **khi biên dịch lại mã nguồn phụ thuộc với hierarchy mới**, compiler có thể báo thiếu bao phủ. Đây là cơ chế rất phù hợp với CI: một thay đổi ở mô hình dữ liệu buộc nhóm phát triển phải xem lại toàn bộ nơi phân loại.

### 3.1. Tại sao không nên thêm default vô điều kiện?

Bạn có thể viết:

```java
// Ý tưởng: fallback này khiến compiler không còn bắt thiếu subtype.
return switch (result) {
    case Success(var v) -> "success";
    case Retry(var seconds) -> "retry";
    case Failure(var reason) -> "failure";
    default -> "other";
};
```

Đoạn này là snippet nằm trong phương thức có biến `result` kiểu `Result`. Nó có thể vẫn tạo mã hợp lệ, nhưng nếu sau đó thêm subtype vào hierarchy, `default` sẽ bao phủ subtype ấy. **Compiler không còn buộc bạn viết logic riêng cho subtype mới.**

Không có nghĩa `default` luôn xấu. Nếu selector là kiểu mở `Object` hoặc một API chủ ý có fallback cho các kiểu tương lai, `default` là lựa chọn hợp lý. Với hierarchy nghiệp vụ đóng, muốn **fail at compile time** khi xuất hiện subtype mới, thường nên liệt kê đủ các nhánh mà không dùng `default`.

### 3.2. Lưu ý về hệ kiểu sealed

Nếu một `sealed class/interface` cho phép một subtype `non-sealed`, subtype ấy mở rộng cho các lớp con khác. Để bao phủ, một `case NonSealedSubtype x` không guard thường có thể xử lý toàn bộ các lớp con của nó. Không nên mặc định rằng compiler có thể liệt kê mọi lớp con cuối cùng như với các `record` final.

Nếu kiểu selector là `Object` thay vì `Result`, compiler không thể dựa riêng vào danh sách `permits` của `Result` để chứng minh toàn bộ không gian `Object` đã được xử lý. **Kiểu tĩnh của selector rất quan trọng.**

## 4. Guard when: nhánh có điều kiện không chứng minh bao phủ toàn bộ kiểu

Giả sử bạn viết:

```java
// KHÔNG BIÊN DỊCH: một Success có value null hoặc blank vẫn chưa có case.
static String guardOnly(Result result) {
    return switch (result) {
        case Success(var value) when value != null && !value.isBlank()
                -> "ok:" + value;
        case Retry(var seconds) -> "retry";
        case Failure(var reason) -> "failure";
    };
}
```

Đây là một lỗi **non-exhaustive**, dù đã có tên cả ba subtype. Vì `when` false đối với một số `Success`, không có nhánh nào khác nhận những trường hợp đó.

Sửa bằng một case `Success` không guard đứng **sau** case đặc thù:

```java
static String guarded(Result result) {
    return switch (result) {
        case Success(var value) when value != null && !value.isBlank()
                -> "ok:" + value;
        case Success(var value) -> "bad-success";
        case Retry(var seconds) -> "retry";
        case Failure(var reason) -> "failure";
    };
}
```

Đoạn `guarded` là snippet hoàn chỉnh về logic, đặt trong class đã định nghĩa `Result` và ba record. Nó vẫn sẽ ném NPE nếu đầu vào null và không có `case null`; việc compiler chấp nhận exhaustiveness **không tự động bảo vệ null**.

**Thứ tự cũng rất quan trọng:** nếu đặt `case Success(var value)` không guard ở trước, case có `when` sau đó có thể bị báo **dominated** vì nhánh rộng đã bao phủ toàn bộ Success.

Nên test các giá trị biên:

| Đầu vào | Guard `value != null && !value.isBlank()` | Nhánh |
| --- | --- | --- |
| `new Success("A")` | true | Nhánh Success có `when` |
| `new Success(" ")` | false | Nhánh Success không guard |
| `new Success(null)` | false | Nhánh Success không guard |

Một switch có đủ case để compiler chấp nhận vẫn cần regression tests cho nội dung xử lý mỗi nhánh.

## 5. Enum: khác biệt giữa switch expression và switch statement truyền thống

Đừng phát biểu chung rằng “mọi switch Java 21 đều phải exhaustive”. Điều đó **không đúng** đối với các `switch statement` truyền thống được giữ để tương thích ngược.

### 5.1. Switch expression bắt buộc exhaustive

```java
enum State { STARTED, PAUSED, STOPPED }

static String label(State state) {
    return switch (state) {
        case STARTED -> "started";
        case PAUSED -> "paused";
        case STOPPED -> "stopped";
    };
}
```

Nếu bỏ `STOPPED` mà không thêm fallback, compiler báo lỗi.

### 5.2. Switch statement truyền thống có thể bỏ thiếu case

```java
static void logState(State state) {
    switch (state) {
        case STARTED -> System.out.println("started");
        case PAUSED -> System.out.println("paused");
        // Không có STOPPED, vẫn là switch statement truyền thống hợp lệ.
    }
}
```

Code này không tự nhiên báo lỗi compile-time chỉ vì bỏ thiếu `STOPPED`. Khi nhận giá trị `STOPPED`, statement có thể không làm gì; đó là lý do cần code review và tests ngay cả khi build thành công.

### 5.3. Enhanced switch statement trong Java 21 phải exhaustive

Một **enhanced switch statement** (chẳng hạn statement có type/record pattern case hoặc `case null`, hay selector là reference type không thuộc nhóm selector truyền thống) **phải exhaustive**. Ví dụ:

```java
// KHÔNG BIÊN DỊCH: enhanced switch statement còn thiếu fallback.
static void logObject(Object input) {
    switch (input) {
        case String text -> System.out.println(text);
    }
}
```

Sửa bằng nhánh bao quát:

```java
static void logObject(Object input) {
    switch (input) {
        case null -> System.out.println("missing");
        case String text -> System.out.println(text);
        default -> System.out.println("other");
    }
}
```

Như vậy, khi review, hãy phân biệt **switch expression**, **enhanced switch statement** và **switch statement truyền thống**. `switch` có dấu `->` chưa đủ để kết luận là expression: `switch (x) { case ... -> System.out.println(...); }` vẫn là statement.

## 6. Open world: selector Object và vai trò của default

Một hierarchy `sealed` giúp xác định tập subtype. Trái lại, với selector kiểu `Object`, tập runtime type quá rộng để chỉ vài nhánh cụ thể bao phủ hết.

Ví dụ:

```java
static String openWorld(Object value) {
    return switch (value) {
        case null -> "null-object";
        case String text -> "text:" + text;
        case Integer number -> "int:" + number;
        default -> "other:" + value.getClass().getSimpleName();
    };
}
```

Ở đây `default` là có chủ đích: các giá trị như `Long`, `Double`, `Boolean` hoặc record bất kỳ không khớp `String`/`Integer` nên được xử lý tại fallback.

Nếu xóa `default`:

```java
// KHÔNG BIÊN DỊCH: Object còn vô số kiểu khác String/Integer.
static String incompleteOpen(Object value) {
    return switch (value) {
        case String text -> text;
        case Integer number -> number.toString();
    };
}
```

Compiler báo non-exhaustive. Thêm nhiều case không phải lúc nào cũng tốt: nếu nghiệp vụ chủ động chấp nhận những kiểu ngoài danh sách, cần một fallback rõ ràng thay vì liệt kê vô hạn.

Có thể dùng type pattern bao quát cho các giá trị khác null khi hợp lệ, nhưng tránh làm nhánh rộng **che khuất** những nhánh cụ thể cần xử lý.

### 6.1. Default không đồng nghĩa nuốt lỗi

Một `default -> null` hoặc `default -> ""` có thể khiến dữ liệu mới im lặng đi qua. Nếu nhận một kiểu ngoài dự kiến là **lỗi hợp đồng**, cân nhắc:

```java
default -> throw new IllegalArgumentException(
        "Unexpected type: " + value.getClass().getName()
);
```

Snippet này cần đặt sau các `case` trong một `switch expression` với `value` khác null trên nhánh default. Nếu selector null mà không có `case null`, behavior thường là NPE trước khi vào default. Chọn chính sách lỗi, không chỉ chọn cú pháp để compiler ngừng phàn nàn.

## 7. Domination là một loại lỗi khác, không phải non-exhaustiveness

Ví dụ sau **không biên dịch**:

```java
static String dominated(Object input) {
    return switch (input) {
        case CharSequence cs -> "characters";
        case String s -> "string";
        default -> "other";
    };
}
```

Vì mọi `String` đều là `CharSequence`, `case CharSequence cs` đứng trước đã bao phủ case String không null. Compiler báo lỗi tương đương **“this case label is dominated by a preceding case label”**.

Sửa thứ tự:

```java
static String ordered(Object input) {
    return switch (input) {
        case String s -> "string";
        case CharSequence cs -> "characters";
        default -> "other";
    };
}
```

Hai vấn đề khác nhau cần được xử lý riêng:

- **Non-exhaustiveness:** còn có giá trị đầu vào hợp lệ không được bao phủ. Giải pháp là thêm case hoặc fallback hợp lý.
- **Domination:** một case bị case trước đó bao trùm. Giải pháp thường là đặt case hẹp trước case rộng, hoặc xóa case dư thừa.

Một codebase có thể gặp cả hai lỗi trong các đoạn khác nhau. Đừng thêm `default` để chữa nhánh bị dominated; default không làm nhánh đã bị che khuất trở nên hợp lệ.

## 8. Ví dụ Java 21 hoàn chỉnh: 11 phép kiểm tra hành vi

Tạo tệp **`ExhaustiveSwitchAnalysisDemo.java`**:

```java
public class ExhaustiveSwitchAnalysisDemo {
    sealed interface Result permits Success, Retry, Failure {}
    record Success(String value) implements Result {}
    record Retry(int seconds) implements Result {}
    record Failure(String reason) implements Result {}

    enum Stage { NEW, RUNNING, DONE }

    static String describe(Result result) {
        return switch (result) {
            case null -> "no-result";
            case Success(var value) when value != null && !value.isBlank() -> "success:" + value;
            case Success(var value) -> "invalid-success";
            case Retry(var seconds) when seconds > 0 -> "retry:" + seconds;
            case Retry(var seconds) -> "invalid-retry";
            case Failure(var reason) -> "failure:" + reason;
        };
    }

    static int stageWeight(Stage stage) {
        return switch (stage) {
            case null -> 0;
            case NEW -> 1;
            case RUNNING -> 2;
            case DONE -> 3;
        };
    }

    static String openWorld(Object value) {
        return switch (value) {
            case null -> "null-object";
            case String text -> "text:" + text;
            case Integer number -> "int:" + number;
            default -> "other:" + value.getClass().getSimpleName();
        };
    }

    static int checked;
    static void check(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + " expected=" + expected + " actual=" + actual);
        }
        ++checked;
        System.out.println("PASS " + label + " => " + actual);
    }

    public static void main(String[] args) {
        check("success", "success:A", describe(new Success("A")));
        check("blank", "invalid-success", describe(new Success(" ")));
        check("null-value", "invalid-success", describe(new Success(null)));
        check("retry", "retry:5", describe(new Retry(5)));
        check("zero", "invalid-retry", describe(new Retry(0)));
        check("failure", "failure:timeout", describe(new Failure("timeout")));
        check("null-result", "no-result", describe(null));
        check("enum", "2", Integer.toString(stageWeight(Stage.RUNNING)));
        check("enum-null", "0", Integer.toString(stageWeight(null)));
        check("object-string", "text:hey", openWorld("hey"));
        check("object-long", "other:Long", openWorld(3L));
        System.out.println("checks=" + checked);
    }
}
```

Biên dịch/chạy với **JDK 21 trở lên** (không cần preview):

```bash
javac --release 21 ExhaustiveSwitchAnalysisDemo.java
java ExhaustiveSwitchAnalysisDemo
```

**Stdout chính xác:**

```text
PASS success => success:A
PASS blank => invalid-success
PASS null-value => invalid-success
PASS retry => retry:5
PASS zero => invalid-retry
PASS failure => failure:timeout
PASS null-result => no-result
PASS enum => 2
PASS enum-null => 0
PASS object-string => text:hey
PASS object-long => other:Long
checks=11
```

Các điểm cần chú ý:

1. `describe` nhận `Result` sealed: compiler bao phủ mọi subtype mà không cần default.
2. `case Success ... when ...` nhận chuỗi không null và không blank; nhánh Success tiếp theo xử lý cả chuỗi blank/null.
3. `Retry(0)` không thỏa guard `seconds > 0`, nhưng vẫn được nhánh Retry không guard xử lý.
4. Null của **selector** đi vào `case null`; khác với `Success(null)`, vốn vẫn là object Success và vào nhánh Success tổng quát.
5. `stageWeight` liệt kê đủ enum constants và xử lý null riêng.
6. `openWorld` có fallback cho kiểu mở `Object`; `3L` được box thành `Long` nên không khớp Integer, đi vào `default`.
7. Hàm `check` chỉ in PASS nếu expected bằng actual; mỗi sai khác ném `AssertionError` để chương trình thất bại.

Ví dụ này vừa chứng minh các `switch expression` là **hợp lệ về độ bao phủ khi biên dịch** vừa kiểm thử hành vi thực tế của một số nhánh. Hai loại bằng chứng có vai trò khác nhau: compiler không chứng minh chuỗi `"invalid-success"` là kết quả đúng theo nghiệp vụ; test chỉ so sánh các đầu vào đã lựa chọn.

## 9. Các ví dụ cố ý biên dịch thất bại để kiểm tra static analysis

Những đoạn dưới đây dùng để **quan sát thông báo compiler**. Chúng không phải phần của tệp runnable ở mục 8. Đặt từng ví dụ trong class/context đã có khai báo kiểu tương ứng, rồi biên dịch với source Java 21.

### 9.1. Quên một subtype trong sealed hierarchy

```java
// KHÔNG BIÊN DỊCH: chưa xử lý Failure.
static String missingSubtype(Result result) {
    return switch (result) {
        case Success(var value) -> "success";
        case Retry(var seconds) -> "retry";
    };
}
```

Mặc dù đã có hai nhánh, kiểu `Result` cho phép `Failure`, nên `switch expression` không exhaustive.

### 9.2. Có tên mọi subtype nhưng guard chưa phủ hết

```java
// KHÔNG BIÊN DỊCH: Success có value null/blank không được xử lý.
static String guardOnly(Result result) {
    return switch (result) {
        case Success(var value) when value != null && !value.isBlank()
                -> "success";
        case Retry(var seconds) -> "retry";
        case Failure(var reason) -> "failure";
    };
}
```

Giải pháp: thêm `case Success(var value) -> ...` không guard **sau** nhánh Success đặc thù.

### 9.3. Selector Object nhưng không có case bao quát

```java
// KHÔNG BIÊN DỊCH: Boolean, Long, Object... không có nhánh.
static String openWithoutDefault(Object value) {
    return switch (value) {
        case String s -> s;
        case Integer n -> n.toString();
    };
}
```

Giải pháp: dùng `default` hoặc type pattern bao quát hợp lý nếu hợp đồng cần xử lý mọi Object.

### 9.4. Case hẹp đứng sau case rộng

```java
// KHÔNG BIÊN DỊCH: case String bị case CharSequence trước đó che.
static String dominated(Object value) {
    return switch (value) {
        case CharSequence cs -> "characters";
        case String s -> "string";
        default -> "other";
    };
}
```

Đây là lỗi domination, không phải thiếu nhánh. Đảo thứ tự case String lên trước CharSequence.

**Ghi chú về build test:** Một test compilation-negative có thể đặt mã cố ý sai trong fixtures riêng và xác nhận `javac` trả mã lỗi khác 0 cùng nhóm thông báo kỳ vọng. Không đưa những đoạn `KHÔNG BIÊN DỊCH` vào thư mục source sản phẩm mà CI đang build, nếu không build thường sẽ thất bại vĩnh viễn.

## 10. Tích hợp exhaustiveness check vào build và CI

### 10.1. Compiler là hàng rào đầu tiên

Một số phân tích như exhaustive/non-exhaustive và dominated cases được kiểm tra bởi **`javac`**. Không cần cài công cụ bên ngoài để nhận các lỗi ngôn ngữ cơ bản đó.

Ví dụ:

```bash
javac --release 21 ExhaustiveSwitchAnalysisDemo.java
java ExhaustiveSwitchAnalysisDemo
```

Nếu `switch expression` không exhaustive, compiler trả lỗi và dừng build cho tệp đó. `-Xlint:all` có thể bật thêm cảnh báo khác, nhưng **không phải điều kiện bắt buộc để phát hiện lỗi exhaustiveness**. `-Werror` biến warning thành lỗi trong trường hợp phù hợp; nó không biến một `switch` chưa exhaustive thành lỗi mới vì bản thân code đã là lỗi biên dịch.

**Đừng tự động sửa bằng `default`** chỉ để build xanh: trước khi thêm fallback, xem liệu một subtype mới cần logic nghiệp vụ riêng hay không.

### 10.2. Maven

Với dự án sử dụng Maven Compiler Plugin và JDK 21:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Đoạn cấu hình là một phần của `pom.xml`, không phải file XML độc lập. Kiểm tra Maven chạy trên đúng JDK/toolchain có thể biên dịch target 21, rồi dùng:

```bash
mvn test
```

Quá trình test build sẽ biên dịch code trước. Nếu có `switch expression` không exhaustive, lỗi compiler phải làm build thất bại trước khi chạy các test tương ứng. Không nhất thiết phải cài plugin static analysis riêng để bắt lỗi đã được ngôn ngữ quy định.

### 10.3. Gradle Groovy DSL

Ví dụ cấu hình toolchain trong `build.gradle` của Java project:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

Chạy:

```bash
gradle test
```

Trong project có Gradle Wrapper, nên dùng `./gradlew test` trên môi trường Unix-like hoặc `gradlew.bat test` trên Windows để cố định phiên bản Gradle của dự án. Đừng mặc định rằng `java -version` trong một terminal luôn bằng toolchain mà Gradle hay Maven thực sự sử dụng.

### 10.4. Cách kết hợp CI và review

Một pipeline hữu ích:

1. **Compile với đúng release level** (Java 21 nếu dùng JEP 440/441), không tắt bước compilation.
2. **Chạy unit tests** cho từng nhánh có ý nghĩa, đặc biệt `when` true/false, null và fallback.
3. **Chạy static analysis bổ sung** nếu team đã sử dụng công cụ như IDE inspections, Error Prone, PMD, Checkstyle hoặc SpotBugs; khả năng phân tích pattern switch phụ thuộc vào phiên bản và cấu hình mỗi công cụ.
4. **Review thay đổi hierarchy/enum**: khi thêm subtype/hằng, xem những nơi có `switch` cùng kiểu và xem `default` có đang che một nhánh cần xử lý riêng không.
5. **Theo dõi code coverage** để phát hiện nhánh chưa được test; kết hợp giá trị biên và assertions thay vì kết luận 100% branch coverage là đủ.

Không nên nói một công cụ ngoài có thể **thay thế** kiểm tra exhaustiveness chuẩn của compiler. Các công cụ ngoài có thể hỗ trợ thêm quy tắc style và bug patterns; `javac` vẫn là nguồn quyết định cú pháp/kiểu cho target Java đã chọn.

## 11. Giới hạn: compile-time proof không bảo đảm mọi runtime đều an toàn

### 11.1. Khi hierarchy thay đổi mà không biên dịch đồng bộ

Một `switch` được biên dịch tại thời điểm hierarchy sealed có ba subtype có thể đã được compiler coi là exhaustive. Nếu các module/binary triển khai thay đổi không đồng bộ hoặc phiên bản runtime và binary không khớp, có thể xuất hiện giá trị runtime không được các nhánh đã biên dịch dự đoán.

Theo ngữ nghĩa Java 21, một `switch` được thiết kế exhaustive nhưng thực thi không có nhãn phù hợp **có thể ném `java.lang.MatchException`** trong kịch bản như vậy. Đây là ngoại lệ bất thường liên quan tương thích binary/triển khai, không phải một nhánh thay thế mà người viết switch nên dựa vào để điều khiển nghiệp vụ.

Biện pháp tốt: kiểm tra version compatibility của các module, build lại mã tiêu thụ hierarchy sau khi thay đổi kiểu, có integration tests cho tổ hợp phiên bản hỗ trợ, và tránh triển khai các binary không đồng bộ ngoài chủ đích.

### 11.2. Null selector không phải MatchException

Khi selector null mà không được xử lý bởi `case null` (hoặc cách tương đương hợp lệ), chương trình thường ném `NullPointerException`. Đừng nhầm NPE do null selector với `MatchException` do không có pattern áp dụng tại runtime.

### 11.3. Compiler không kiểm thử nội dung record

Một record như `Success(String value)` vẫn có thể chứa `value == null` hoặc chuỗi trắng, trừ khi constructor/hợp đồng có validation. Exhaustiveness chỉ đảm bảo có nhánh cho kiểu `Success`, không khẳng định dữ liệu component hợp lệ.

Vì vậy `case Success(var value) when value != null && !value.isBlank()` cần nhánh Success không guard nếu muốn cover mọi Success. Đây là ví dụ điển hình cho việc phải kết hợp **static exhaustiveness** với **negative tests**.

## 12. Checklist review switch theo hướng static analysis

| Câu hỏi | Hành động nên làm |
| --- | --- |
| Đây là `switch expression` hay statement? | Expression bắt buộc exhaustive; enhanced statement Java 21 cũng vậy; traditional statement có ngoại lệ tương thích ngược. |
| Kiểu tĩnh của selector là gì? | Với `Object`, cần fallback bao quát; với `sealed`/`enum` có thể liệt kê hết. |
| Có `default` không? | Xem nó có cần thiết hay đang che subtype mới. |
| Có case `when` không? | Kiểm tra nhánh không guard hoặc các case còn lại có bao phủ khi guard false. |
| Thứ tự case có hợp lệ không? | Đặt pattern hẹp trước pattern rộng để tránh domination. |
| Có `null` không? | Quyết định trả fallback, chấp nhận null hay chủ động ném NPE; test riêng. |
| Có record patterns lồng không? | Kiểm tra component có thể null/sai kiểu và liệu tập case có thật sự bao phủ cây dữ liệu. |
| Enum hoặc sealed vừa thêm giá trị mới? | Biên dịch lại, xem nơi thiếu case và các default có che nhánh mới hay không. |
| Maven/Gradle/IDE đang dùng release nào? | Xác nhận compiler, toolchain, source level và CI nhất quán. |
| Có static analysis bổ sung? | Dùng làm lớp kiểm tra thứ hai, không gán cho chúng bảo đảm thay compiler. |
| Test bao phủ guard true/false và giá trị biên? | Dùng assertions và expected result đúng theo hợp đồng. |
| Các binary triển khai đồng bộ? | Kiểm tra compatibility để hạn chế MatchException trong kịch bản riêng biệt. |

## 13. Bài tập thực hành

### Bài A — Tìm lỗi non-exhaustive

Cho:

```java
sealed interface Command permits Add, Remove, Update {}
record Add(int id) implements Command {}
record Remove(int id) implements Command {}
record Update(int id) implements Command {}
```

Phương thức:

```java
// KHÔNG BIÊN DỊCH.
static String label(Command command) {
    return switch (command) {
        case Add(var id) -> "add:" + id;
        case Remove(var id) -> "remove:" + id;
    };
}
```

**Câu hỏi:** Vì sao không biên dịch? Nên thêm `default` hay thêm nhánh cụ thể?

**Đáp án:** Thiếu `Update`. Nên thêm `case Update(var id) -> "update:" + id;` khi yêu cầu nghiệp vụ cần xử lý tường minh mọi subtype. Đừng dùng `default` chỉ để che thiếu nhánh nếu muốn compiler nhắc cập nhật khi thêm subtype.

### Bài B — Guard không làm kiểu được bao phủ hết

Cho:

```java
record Payment(int amount) {}

// Snippet trong hàm nhận Object raw:
return switch (raw) {
    case Payment(var amount) when amount > 0 -> "valid";
    default -> "other";
};
```

**Câu hỏi:** Với `Payment(0)`, code trả gì? Nếu yêu cầu phải phân biệt Payment không hợp lệ với object khác, sửa ra sao?

**Đáp án:** Với `Payment(0)`, guard false nên vào `default -> "other"`. Để phân biệt, thêm case `Payment(var amount) -> "invalid-payment"` ngay **sau** case có guard. Vì selector `Object`, giữ `default` để xử lý các kiểu còn lại.

### Bài C — Lỗi bị che bởi default

Một `sealed interface State permits Idle, Active` được xử lý bởi switch có `case Idle`, `case Active` và `default`. Sau đó project thêm `Paused`; build vẫn thành công.

**Giải thích:** `default` đã bao phủ `Paused`, nên compiler không cần buộc viết case mới. Nếu ý định là phải xử lý rõ từng trạng thái, bỏ default khỏi switch exhaustive trên sealed hierarchy và bổ sung case khi compiler yêu cầu. Trường hợp muốn có fallback cho subtype tương lai thì giữ default, nhưng phải coi đó là một lựa chọn về hợp đồng và test riêng.

### Bài D — Traditional statement khác enhanced statement

Trong Java 21, đoạn:

```java
enum Phase { A, B, C }

static void log(Phase phase) {
    switch (phase) {
        case A -> System.out.println("A");
        case B -> System.out.println("B");
    }
}
```

là một **traditional switch statement** không exhaustive nhưng hợp lệ về cú pháp. Khi gặp `Phase.C`, nó không in gì. Muốn buộc xử lý đủ mọi enum constant ngay ở compile-time, có thể thay bằng **switch expression** tạo một giá trị, hoặc áp dụng chính sách phân tích/test của dự án để phát hiện statement bỏ thiếu case.

Các bài tập trong mục này là snippet minh họa hoặc cố ý sai để thực hành phân tích compiler; tệp Java 21 hoàn chỉnh đã chạy và có stdout chính xác nằm ở mục 8.

## 14. Kết luận

**Static analysis cho switch exhaustiveness** giúp chuyển một phần rủi ro “quên xử lý loại dữ liệu mới” từ runtime sang **compile time**. Với Java 21, `switch expression` và enhanced `switch statement` được compiler kiểm tra tính đầy đủ. Những kiểu có không gian giá trị rõ như `enum` và `sealed hierarchy` rất phù hợp để liệt kê case tường minh, thường **không cần `default`**.

Tuy nhiên, kiểm tra tĩnh không xác nhận logic của mỗi case, không tự xử lý null, không thay thế kiểm tra `when` false hay các trạng thái dữ liệu không hợp lệ, và không bảo đảm các binary triển khai khác phiên bản tương thích. Một quy trình build đáng tin nên kết hợp **javac Java 21 + kiểm thử nhánh + review default/guard + kiểm tra CI/toolchain**.

**Tài liệu chính thức:**

- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [Java SE 21 Language Specification, §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1)
- [Java SE 21 Language Specification, §14.11.2 — Enhanced Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.2)
- [Oracle Java 21 — Pattern Matching with switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
