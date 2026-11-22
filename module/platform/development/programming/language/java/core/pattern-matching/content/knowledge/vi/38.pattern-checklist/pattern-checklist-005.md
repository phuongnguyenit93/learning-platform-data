# Checklist exhaustive và sealed type trong Java 21

## 1. Mục tiêu của checklist

Khi dùng **pattern matching for `switch`**, chương trình cần trả lời câu hỏi quan trọng: **“Mọi giá trị hợp lệ của kiểu selector có đường xử lý hay chưa?”** Trong Java 21, compiler có thể kiểm tra tính *exhaustive* của `switch expression` và các `switch statement` có pattern/null labels. Với **sealed types** và **enum**, kiểm tra này đặc biệt hữu ích vì compiler biết các nhánh kiểu hoặc hằng được khai báo.

Bài thuộc nhóm **Checklist pattern**, tập trung vào **Checklist exhaustive và sealed type**. Mục tiêu không chỉ là nhớ “thêm đủ case”, mà là học cách review một tập nhánh theo đúng logic ngôn ngữ: subtype nào được phép, case nào bao phủ subtype đó, guard có thể false không, `null` được xử lý ra sao, nhánh rộng có che nhánh hẹp không, và điều gì xảy ra khi mô hình dữ liệu tiến hóa.

Sau bài học, bạn sẽ:

- Phân biệt *sealed hierarchy* (tập subtype trực tiếp có kiểm soát) và *switch exhaustiveness* (một tính chất cụ thể của từng switch).
- Xác định đủ nhánh cho `sealed interface` có nhiều `record`, cho `enum` và cho một nhánh `non-sealed`.
- Nhận ra **guarded case không nhất thiết bao phủ toàn bộ subtype**; cần fallback khi guard có thể false.
- Tránh lạm dụng `default` làm mất tín hiệu compile-time khi bổ sung subtype mới.
- Kiểm tra **null selector**, **null trong nested record** và **null ở component lá** như ba tình huống riêng.
- Phân biệt lỗi *non-exhaustive*, *dominated case*, cú pháp sai và lỗi nghiệp vụ dù code vẫn biên dịch.
- Sử dụng chương trình Java 21 tự chạy, bộ thử compiler cố ý sai và checklist thực hành trước khi merge pull request.

**Phiên bản:** Java 21 trở lên. Sealed classes/interfaces chính thức từ Java 17 (JEP 409); record patterns và pattern matching for `switch` chính thức từ Java 21 (JEP 440, JEP 441). Chương trình minh họa dùng `javac --release 21`, không cần `--enable-preview`.

## 2. Nền tảng: sealed không đồng nghĩa với “tự động exhaustive”

Xét phân cấp command:

```java
sealed interface Command permits Open, Fund, Close {}

record Open(String id) implements Command {}
record Fund(String id, int cents) implements Command {}
record Close(String id, String reason) implements Command {}
```

Các khai báo trên nằm trong cùng phạm vi minh họa; mục 6 đặt chúng vào một lớp đầy đủ để dễ chạy.

Ý nghĩa của `sealed interface Command`:

- Nó quy định **các direct permitted subtypes** là `Open`, `Fund` và `Close`.
- Các record trên mặc nhiên là `final`, không thể bị subclass tùy tiện.
- Compiler có thể dùng đồ thị subtype này để xét một `switch` có đủ đường xử lý cho mọi Command khác null hay chưa.
- `sealed` **không tự xác thực dữ liệu bên trong**. `new Open(null)` là đối tượng Open hợp lệ về mặt kiểu, dù nghiệp vụ có thể từ chối ID null.
- `sealed` **không tự xử lý selector null** và không tự viết logic đúng cho từng subtype.

Một `switch expression` đơn giản:

```java
static String kind(Command command) {
    return switch (command) {
        case Open open -> "OPEN";
        case Fund fund -> "FUND";
        case Close close -> "CLOSE";
    };
}
```

Ba type patterns bao phủ ba loại Command khác null hiện có. **Không cần `default` chỉ để làm exhaustive.** Nhưng nếu gọi `kind(null)` thì phiên bản không có `case null` có thể ném `NullPointerException`; exhaustive về kiểu **không tự tạo chính sách cho null**.

Trong ví dụ hoàn chỉnh, ta sẽ có `case null` để biểu diễn chính sách rõ ràng.

### 2.1. Sealed áp đặt ranh giới trực tiếp, không đóng toàn bộ hệ thống mã một cách thần kỳ

Một direct permitted subtype của sealed hierarchy phải tuân thủ các quy tắc modifier phù hợp, như `final`, `sealed` hoặc `non-sealed`. Nếu một nhánh là **`non-sealed`**, các lớp con của nhánh đó có thể mở rộng tiếp. Khi đó một `case NonSealedType value` bao phủ cả những đối tượng thuộc subclass của NonSealedType, nhưng một case chỉ xử lý các leaf cụ thể có thể không bao phủ hết nhánh mở.

**Checklist đầu tiên:** đọc định nghĩa `sealed ... permits ...` và các direct subtypes; không suy đoán tập subtype chỉ bằng các `case` đang có trong switch.

## 3. Checklist nhanh: 12 câu hỏi trước khi duyệt switch

| # | Điều cần xác minh | Vì sao quan trọng |
|---|---|---|
| 1 | Selector có **kiểu tĩnh** nào? | Exhaustiveness được xét theo kiểu selector và các quy tắc tương ứng, không chỉ theo một object được thử |
| 2 | Kiểu đó là `enum`, `sealed`, kiểu mở hay generic? | Quy tắc bao phủ khác nhau |
| 3 | Nếu sealed, **toàn bộ direct permitted subtypes** là gì? | Tránh bỏ sót một subtype, đặc biệt nhánh ít gặp |
| 4 | Subtype có phải `sealed` tiếp, `final` hay `non-sealed`? | Nhánh `non-sealed` có thể có nhiều subclass |
| 5 | Mỗi subtype có một case **đủ rộng** để bao phủ toàn bộ nó không? | Guard có thể false, record deconstruction có thể thất bại |
| 6 | Có guarded case nào thiếu fallback cùng subtype không? | Pattern match chưa có nghĩa guard đúng |
| 7 | Có một case tổng quát đứng trước case hẹp không? | Compiler có thể báo `dominated case label` |
| 8 | `null` được xử lý riêng hoặc bị từ chối theo hợp đồng? | `default` thông thường không thay thế `case null` |
| 9 | Nested record pattern có component record nullable không? | Nested record null có thể làm pattern sâu không match |
| 10 | Có `default` nào che thiếu subtype/enum constant không? | Có thể mất ưu thế exhaustive checking khi model thay đổi |
| 11 | Có test cho guard true/false, null và giá trị biên của mỗi subtype không? | Compiler không chứng minh điều kiện nghiệp vụ đúng |
| 12 | Khi thêm subtype mới, build/CI có báo thiếu xử lý không? | Đảm bảo hợp đồng tiến hóa của sealed hierarchy được duy trì |

**Câu kiểm tra chốt:** “Nếu ngày mai thêm một subtype mới, tôi muốn compiler bắt buộc sửa handler hay chủ ý cho subtype đó vào fallback?” Nếu muốn compiler nhắc, thường **không nên thêm `default` chung** ở closed-domain switch.

## 4. Ba tầng bao phủ: kiểu, record pattern và guard

Ví dụ handler phân loại command:

```java
return switch (command) {
    case null -> "NULL_COMMAND";

    case Open(var id) when hasText(id) -> "OPEN:" + id;
    case Open ignored -> "REJECT_OPEN";

    case Fund(var id, var cents)
            when hasText(id) && cents > 0
            -> "FUND:" + id + ":" + cents;
    case Fund ignored -> "REJECT_FUND";

    case Close(var id, var reason)
            when hasText(id) && hasText(reason)
            -> "CLOSE:" + id + ":" + reason;
    case Close ignored -> "REJECT_CLOSE";
};
```

Đây là snippet trong phương thức có biến `command` và helper `hasText`; chương trình chạy được có ở mục 6.

Phân biệt:

1. **Type coverage:** có `Open`, `Fund`, `Close` — ba direct subtypes.
2. **Pattern coverage:** mỗi `case Open(var id)` khớp record Open khác null và bind component `id`. Component kiểu tham chiếu có thể null khi bind bằng `var` ở record pattern.
3. **Guard coverage:** `when hasText(id)` có thể false. Vì vậy guarded Open **không** đủ cho mọi Open. Nhánh `case Open ignored` không guard bảo đảm xử lý phần còn lại.

Nếu chỉ có:

```java
case Fund(var id, var cents) when cents > 0 -> "POSITIVE";
```

thì Fund với `cents == 0` hoặc âm vẫn tồn tại. Guard false, nhánh không được chọn. Với một `switch expression` chỉ có nhánh Fund này và không có nhánh nào bao phủ phần còn lại, compiler có thể báo **non-exhaustive**.

### 4.1. Trường hợp đặc biệt: when true

Không nên học thuộc câu sai “mọi guarded case đều không thể exhaustive”. Trong Java 21, một guard hằng `when true` có thể được xem tương đương một pattern không guard khi xét tính bao phủ:

```java
class WhenTrueCheck {
    sealed interface Job permits Run {}
    record Run(int count) implements Job {}

    static String code(Job job) {
        return switch (job) {
            case Run(var count) when true -> "RUN";
        };
    }
}
```

**Đoạn trên đã được `javac --release 21` chấp nhận.** Tuy nhiên, `when true` không cải thiện tính rõ nghĩa; trong code review, nhánh không guard thường dễ hiểu hơn. Với điều kiện nghiệp vụ như `count > 0`, không được mặc định coi guard sẽ luôn true.

### 4.2. Quy tắc review nhánh có guard

Với mỗi `case Subtype(...) when condition`, hãy hỏi:

- Có giá trị nào thuộc subtype khiến `condition == false` không?
- Nếu có, một nhánh nào **phía sau** nhận giá trị đó?
- Nếu điều kiện dùng `&&`/`||`, có guard null an toàn và ngoặc đúng không?
- Có giá trị biên như `0`, `-1` hoặc chuỗi blank làm lộ fallback không?
- Nếu hai guarded cases cùng true, thứ tự ưu tiên có đúng hợp đồng không?

Compiler có thể phát hiện một số nhánh bị che theo quan hệ kiểu, nhưng nó không kiểm chứng đầy đủ logic nghiệp vụ của các biểu thức boolean phức tạp.

## 5. Null: exhaustive không đồng nghĩa null-safe

### 5.1. Null selector ở switch

Trong pattern switch Java 21, selector null cần chính sách cụ thể nếu không muốn nhận `NullPointerException`. Chẳng hạn:

```java
case null -> "NULL_COMMAND";
```

Một `default` thông thường **không tự thay `case null`**. Điều này khác `value instanceof Open open`, vốn trả false nếu `value == null`.

Ở ví dụ enum của chương trình chạy được, `phase(null)` **ném `NullPointerException`** vì `switch` enum đó không có nhánh null. Code minh họa còn bắt đúng exception để ghi ra stdout. Như vậy compiler cho phép enum switch exhaustive trên mọi hằng enum mà vẫn không yêu cầu một nhánh null.

### 5.2. Nested record null làm pattern sâu thất bại

Giả sử:

```java
record Envelope(String trace, Command command) {}
```

và một switch gồm:

```java
case Envelope(var trace, Open(var id)) -> "NESTED_OPEN:" + id;
case Envelope(var trace, Fund(var id, var cents))
        -> "NESTED_FUND:" + cents;
case Envelope(var trace, Close(var id, var reason))
        -> "NESTED_CLOSE:" + reason;
case Envelope ignored -> "NESTED_MISSING";
```

Nếu `new Envelope("e1", null)`, root Envelope **khác null**, nhưng component Command là null nên nested patterns `Open(...)`, `Fund(...)`, `Close(...)` **đều không match**. Nhánh `Envelope ignored` sẽ xử lý.

Như vậy, **dù ba subtype của Command đã được liệt kê**, một record sâu có thể cần thêm fallback vì **nested component nullable**. Không được suy luận rằng “tôi đã viết đủ subtype, vậy mọi nested record chắc chắn match”.

### 5.3. Component lá null có thể vẫn match

Với:

```java
new Envelope("e2", new Open(null))
```

nested `Open(var id)` **khớp** vì đối tượng Open tồn tại và `var id` có thể bind null. Chuỗi `"NESTED_OPEN:" + id` thành `NESTED_OPEN:null`. Nếu nghiệp vụ không cho phép ID null, cần validation guard riêng — exhaustiveness không chứng minh dữ liệu hợp lệ.

**Checklist null có ba ô riêng:** selector null, nested record null, component lá null. Các vị trí này có semantics khác nhau.

## 6. Chương trình Java 21 hoàn chỉnh với bộ kiểm tra tự động

Tạo file **`ExhaustivenessChecklistDemo.java`**. Mã không cần dependency ngoài JDK. Chương trình thể hiện:

- Một sealed hierarchy gồm ba record commands.
- `route` có guarded cases và fallback theo subtype.
- `kind` phân loại subtype với type patterns.
- `nested` phân rã record chứa Command và có fallback cho null nested.
- Một enum Phase với switch expression đủ ba hằng.
- Các assertions so với expected độc lập.

```java
import java.util.Objects;

public class ExhaustivenessChecklistDemo {
    sealed interface Command permits Open, Fund, Close {}
    record Open(String id) implements Command {}
    record Fund(String id, int cents) implements Command {}
    record Close(String id, String reason) implements Command {}
    record Envelope(String trace, Command command) {}
    enum Phase { NEW, RUNNING, DONE }

    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    static String route(Command command) {
        return switch (command) {
            case null -> "NULL_COMMAND";
            case Open(var id) when hasText(id) -> "OPEN:" + id;
            case Open ignored -> "REJECT_OPEN";
            case Fund(var id, var cents)
                    when hasText(id) && cents > 0 -> "FUND:" + id + ":" + cents;
            case Fund ignored -> "REJECT_FUND";
            case Close(var id, var reason)
                    when hasText(id) && hasText(reason)
                    -> "CLOSE:" + id + ":" + reason;
            case Close ignored -> "REJECT_CLOSE";
        };
    }

    static String kind(Command command) {
        return switch (command) {
            case null -> "NONE";
            case Open open -> "OPEN";
            case Fund fund -> "FUND";
            case Close close -> "CLOSE";
        };
    }

    static String nested(Envelope envelope) {
        return switch (envelope) {
            case null -> "NULL_ENVELOPE";
            case Envelope(var trace, Open(var id)) -> "NESTED_OPEN:" + id;
            case Envelope(var trace, Fund(var id, var cents))
                    -> "NESTED_FUND:" + cents;
            case Envelope(var trace, Close(var id, var reason))
                    -> "NESTED_CLOSE:" + reason;
            case Envelope ignored -> "NESTED_MISSING";
        };
    }

    static String phase(Phase value) {
        return switch (value) {
            case NEW -> "NEW";
            case RUNNING -> "RUNNING";
            case DONE -> "DONE";
        };
    }

    static void check(String label, Command command,
                      String expectedResult, String expectedKind) {
        String result = route(command);
        String actualKind = kind(command);
        if (!Objects.equals(expectedResult, result)
                || !Objects.equals(expectedKind, actualKind)) {
            throw new AssertionError(label + " result=" + result
                    + " kind=" + actualKind);
        }
        System.out.println(label + " => " + result + " | kind=" + actualKind);
    }

    static void checkNested(String label, Envelope envelope, String expected) {
        String result = nested(envelope);
        if (!Objects.equals(result, expected)) {
            throw new AssertionError(label + " expected=" + expected
                    + ", actual=" + result);
        }
        System.out.println(label + " => " + result);
    }

    public static void main(String[] args) {
        check("null command", null, "NULL_COMMAND", "NONE");
        check("open good", new Open("O1"), "OPEN:O1", "OPEN");
        check("open null id", new Open(null), "REJECT_OPEN", "OPEN");
        check("open blank id", new Open(" "), "REJECT_OPEN", "OPEN");
        check("open spaced id", new Open(" O2 "), "OPEN: O2 ", "OPEN");
        check("fund positive", new Fund("F1", 1), "FUND:F1:1", "FUND");
        check("fund large", new Fund("F2", 500), "FUND:F2:500", "FUND");
        check("fund zero", new Fund("F3", 0), "REJECT_FUND", "FUND");
        check("fund negative", new Fund("F4", -1), "REJECT_FUND", "FUND");
        check("fund null id", new Fund(null, 20), "REJECT_FUND", "FUND");
        check("fund blank id", new Fund("", 20), "REJECT_FUND", "FUND");
        check("close good", new Close("C1", "done"),
                "CLOSE:C1:done", "CLOSE");
        check("close null reason", new Close("C2", null),
                "REJECT_CLOSE", "CLOSE");
        check("close blank reason", new Close("C3", " "),
                "REJECT_CLOSE", "CLOSE");
        check("close null id", new Close(null, "done"),
                "REJECT_CLOSE", "CLOSE");
        check("close blank id", new Close("", "done"),
                "REJECT_CLOSE", "CLOSE");

        checkNested("null envelope", null, "NULL_ENVELOPE");
        checkNested("nested null command", new Envelope("e1", null),
                "NESTED_MISSING");
        checkNested("nested open", new Envelope("e2", new Open("O1")),
                "NESTED_OPEN:O1");
        checkNested("nested open null leaf",
                new Envelope("e3", new Open(null)), "NESTED_OPEN:null");
        checkNested("nested fund", new Envelope(null, new Fund("F1", 1)),
                "NESTED_FUND:1");
        checkNested("nested close", new Envelope("e5",
                new Close("C1", null)), "NESTED_CLOSE:null");

        for (Phase p : Phase.values()) {
            System.out.println("phase " + p + " => " + phase(p));
        }
        try {
            phase(null);
            throw new AssertionError("Expected NPE for null enum selector");
        } catch (NullPointerException expected) {
            System.out.println("phase null => NullPointerException");
        }
    }
}
```

### 6.1. Cách chạy

```bash
javac --release 21 ExhaustivenessChecklistDemo.java
java ExhaustivenessChecklistDemo
```

**Stdout đã kiểm chứng trực tiếp:**

```text
null command => NULL_COMMAND | kind=NONE
open good => OPEN:O1 | kind=OPEN
open null id => REJECT_OPEN | kind=OPEN
open blank id => REJECT_OPEN | kind=OPEN
open spaced id => OPEN: O2  | kind=OPEN
fund positive => FUND:F1:1 | kind=FUND
fund large => FUND:F2:500 | kind=FUND
fund zero => REJECT_FUND | kind=FUND
fund negative => REJECT_FUND | kind=FUND
fund null id => REJECT_FUND | kind=FUND
fund blank id => REJECT_FUND | kind=FUND
close good => CLOSE:C1:done | kind=CLOSE
close null reason => REJECT_CLOSE | kind=CLOSE
close blank reason => REJECT_CLOSE | kind=CLOSE
close null id => REJECT_CLOSE | kind=CLOSE
close blank id => REJECT_CLOSE | kind=CLOSE
null envelope => NULL_ENVELOPE
nested null command => NESTED_MISSING
nested open => NESTED_OPEN:O1
nested open null leaf => NESTED_OPEN:null
nested fund => NESTED_FUND:1
nested close => NESTED_CLOSE:null
phase NEW => NEW
phase RUNNING => RUNNING
phase DONE => DONE
phase null => NullPointerException
```

**Kết quả kiểm tra:** 16 ca command (mỗi ca kiểm tra đồng thời `route` và `kind`), 6 ca record `Envelope`, 3 ca enum non-null và 1 ca enum null có bắt ngoại lệ đúng chủ đích. Tổng **26 dòng kết quả** được in. Chương trình đã biên dịch thành công với `javac --release 21` và chạy không có `AssertionError` ngoài ý muốn.

Chú ý trường hợp `Open(" O2 ")`: helper `hasText` chỉ kiểm tra không null và không blank; nó **không trim**. Vì vậy output giữ dấu cách trong ID. Nếu domain yêu cầu chuẩn hóa ID, nên bổ sung quy tắc đó ở boundary và cập nhật tests, không mặc định coi `isBlank()` là hàm chuẩn hóa.

### 6.2. Chương trình này chứng minh gì?

- Các nhánh case hiện có được compiler chấp nhận là exhaustive cho ba subtype sealed.
- Guarded cases false sẽ đi vào fallback đúng subtype.
- Selector null được xử lý riêng khi có `case null`.
- Nested Command null được xử lý bởi fallback Envelope.
- Component lá null có thể được bind, và guard có thể từ chối theo chính sách.
- Enum switch có đủ constants để compile, nhưng vẫn có thể ném NPE với null selector.
- Bộ test có expected cố định, giúp phát hiện khác biệt hành vi nếu ai đó đổi thứ tự nhánh hoặc bỏ guard.

Bộ ví dụ **không chứng minh** mọi kiểu dữ liệu từ API ngoài đều hợp lệ, hay việc thay đổi classpath đã biên dịch sẵn sẽ an toàn; review và regression tests vẫn cần trong dự án thật.

## 7. Năm lỗi compiler tiêu biểu khi thiếu exhaustive hoặc sai thứ tự

Các mẫu dưới đây **cố ý không biên dịch**. Hãy lưu mỗi đoạn vào đúng tên tệp được chỉ định và chạy riêng; **đừng đặt chúng chung với chương trình mục 6**. Cả năm trường hợp đã được kiểm chứng là bị `javac --release 21` từ chối.

### 7.1. Thiếu một direct subtype

Tệp **`MissingSubtype.java`**:

```java
class MissingSubtype {
    sealed interface Command permits Open, Close {}
    record Open() implements Command {}
    record Close() implements Command {}

    static String route(Command command) {
        return switch (command) {
            case Open open -> "OPEN";
        };
    }
}
```

Biên dịch:

```bash
javac --release 21 MissingSubtype.java
```

**Vì sao lỗi?** Tập Command gồm cả Open và Close, nhưng switch expression chỉ có Open. Thiếu đường xử lý cho Close. **Cách sửa:** thêm `case Close close -> "CLOSE";` theo đúng hợp đồng, không vội thêm `default`.

### 7.2. Chỉ có guarded case

Tệp **`GuardOnly.java`**:

```java
class GuardOnly {
    sealed interface Command permits Fund {}
    record Fund(int cents) implements Command {}

    static String route(Command command) {
        return switch (command) {
            case Fund(var cents) when cents > 0 -> "POSITIVE";
        };
    }
}
```

Biên dịch:

```bash
javac --release 21 GuardOnly.java
```

**Vì sao lỗi?** Fund(-1) và Fund(0) là các giá trị Fund hợp lệ về mặt Java, nhưng guard `cents > 0` false. Switch không bao phủ chúng. **Cách sửa:** thêm `case Fund ignored -> "NOT_POSITIVE";` sau nhánh guarded.

Không thay logic bằng `when true` chỉ để đạt exhaustive, vì điều đó làm mất ý nghĩa yêu cầu chỉ chấp nhận số dương.

### 7.3. Nhánh rộng che hai nhánh hẹp

Tệp **`DominatedCase.java`**:

```java
class DominatedCase {
    sealed interface Command permits Open, Close {}
    record Open() implements Command {}
    record Close() implements Command {}

    static String route(Command command) {
        return switch (command) {
            case Command any -> "ANY";
            case Open open -> "OPEN";
            case Close close -> "CLOSE";
        };
    }
}
```

Biên dịch:

```bash
javac --release 21 DominatedCase.java
```

**Vì sao lỗi?** `case Command any` đã khớp mọi Command khác null. Các nhánh Open/Close ở sau bị **dominated**. **Cách sửa:** đặt các subtype cụ thể trước; bỏ nhánh tổng quát nếu nó không còn cần thiết.

### 7.4. Thiếu một enum constant

Tệp **`MissingEnumConstant.java`**:

```java
class MissingEnumConstant {
    enum Phase { NEW, RUNNING, DONE }

    static String route(Phase phase) {
        return switch (phase) {
            case NEW -> "NEW";
            case RUNNING -> "RUNNING";
        };
    }
}
```

Biên dịch:

```bash
javac --release 21 MissingEnumConstant.java
```

**Vì sao lỗi?** Thiếu hằng `DONE`. Với enum switch expression, liệt kê đầy đủ hằng giúp compiler kiểm tra. Nếu thêm `default`, việc thiếu `DONE` có thể không còn bị báo ở compile time. Nên bổ sung `case DONE -> "DONE";`.

### 7.5. Bỏ quên nhánh non-sealed

Tệp **`MissingNonSealed.java`**:

```java
class MissingNonSealed {
    sealed interface Signal permits Known, Extension {}
    record Known() implements Signal {}
    non-sealed static class Extension implements Signal {}

    static String route(Signal signal) {
        return switch (signal) {
            case Known known -> "KNOWN";
        };
    }
}
```

Biên dịch:

```bash
javac --release 21 MissingNonSealed.java
```

**Vì sao lỗi?** `Signal` có hai direct permitted subtypes: Known và Extension. Extension là `non-sealed`, có thể có các subclass khác, và nhánh này hoàn toàn chưa được xử lý. **Cách sửa:** thêm case cho `Extension` hoặc thiết kế fallback rõ ràng theo domain.

**Điểm chung:** lỗi compile-time không được chữa bằng test runtime. Bạn phải chỉnh tập nhánh hoặc mô hình kiểu trước, sau đó mới kiểm thử hành vi.

## 8. Non-sealed: bao phủ nhánh mở như thế nào?

Một sealed hierarchy có thể mở ở một nhánh:

```java
sealed interface Signal permits Known, Extension {}
record Known() implements Signal {}
non-sealed class Extension implements Signal {}
```

Điều này nghĩa là mọi Signal trực tiếp là Known hoặc Extension; nhưng những object thuộc subclass của Extension cũng là Extension. Vì vậy nhánh:

```java
case Extension extension -> "EXTENSION";
```

có thể bao phủ cả Extension lẫn subclass của nó.

### Chương trình kiểm chứng riêng

Tạo tệp **`NonSealedCoverageDemo.java`**:

```java
public class NonSealedCoverageDemo {
    sealed interface Signal permits Known, Extension {}
    record Known() implements Signal {}
    non-sealed static class Extension implements Signal {}
    static final class ExtensionChild extends Extension {}

    static String route(Signal signal) {
        return switch (signal) {
            case Known known -> "KNOWN";
            case Extension extension -> "EXTENSION";
        };
    }

    public static void main(String[] args) {
        System.out.println("known => " + route(new Known()));
        System.out.println("extension => " + route(new Extension()));
        System.out.println("extension child => " + route(new ExtensionChild()));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 21 NonSealedCoverageDemo.java
java NonSealedCoverageDemo
```

**Stdout đã kiểm chứng:**

```text
known => KNOWN
extension => EXTENSION
extension child => EXTENSION
```

Đây là điểm cần nêu trong review: **sealed** ràng buộc các subtype **trực tiếp**; khi một nhánh `non-sealed`, tập subtype gián tiếp có thể mở, nhưng một type pattern đúng tại nhánh đó vẫn có thể bao phủ tất cả hậu duệ.

Nếu chỉ liệt kê một vài subclass cụ thể của `Extension` mà không có case bao phủ chính `Extension`, compiler không có đủ cơ sở xác nhận mọi Extension hiện tại và tương lai đều được xử lý.

## 9. Enum switch: cách giữ ưu thế exhaustive khi thêm hằng

Với:

```java
enum Phase { NEW, RUNNING, DONE }
```

Một switch expression liệt kê đủ:

```java
static String label(Phase phase) {
    return switch (phase) {
        case NEW -> "NEW";
        case RUNNING -> "RUNNING";
        case DONE -> "DONE";
    };
}
```

Nếu source enum được cập nhật thêm `PAUSED` và bạn **biên dịch lại** toàn bộ module có switch này, compiler có thể yêu cầu cập nhật handler. Điều đó giúp tránh nhánh “unknown” mơ hồ cho một trạng thái hợp lệ mới.

### Khi nào default phù hợp?

`default` không bị cấm tuyệt đối. Với selector có kiểu mở (ví dụ `Object`) hoặc domain yêu cầu fallback chung cho giá trị chưa nhận diện, default có thể hợp lý. Hãy thể hiện quyết định đó bằng tên/kết quả có ý nghĩa và test riêng.

Tuy nhiên, với enum/sealed **do chính module kiểm soát**, nếu mục tiêu là **bắt buộc sửa handler khi thêm trạng thái mới**, không nên sử dụng default chung như:

```java
default -> "UNKNOWN";
```

Một default có thể khiến build tiếp tục thành công dù chưa ai quyết định cách xử lý `PAUSED`.

### Khác biệt giữa compile-time và deployment

Exhaustiveness được kiểm tra theo **thông tin kiểu ở thời điểm biên dịch**. Một hệ thống deploy các JAR đã biên dịch ở những thời điểm khác nhau có thể có rủi ro tương thích nhị phân hoặc hành vi runtime khi các biến thể thay đổi. Đừng xem exhaustive check là bảo đảm mọi tổ hợp runtime/classpath sẽ chạy đúng. Hãy rebuild, chạy regression tests và kiểm soát version của các module cùng phát triển.

## 10. Switch expression, enhanced switch statement và traditional switch

Trong Java 21, cần tránh gộp mọi loại `switch` thành một quy tắc đơn giản “switch luôn bắt buộc exhaustive”.

### Switch expression

```java
String result = switch (command) {
    case Open open -> "OPEN";
    case Fund fund -> "FUND";
    case Close close -> "CLOSE";
};
```

Switch expression phải exhaustive theo quy tắc ngôn ngữ. Ví dụ này giả định biến `command` có kiểu `Command`.

### Enhanced switch statement dùng pattern labels

```java
static void printCommand(Command command) {
    switch (command) {
        case Open open -> System.out.println("OPEN");
        case Fund fund -> System.out.println("FUND");
        case Close close -> System.out.println("CLOSE");
    }
}
```

Đây là một **enhanced switch statement** vì có pattern labels. Java 21 yêu cầu nó exhaustive, dù nó là statement chứ không phải expression. Ngược lại, nhiều **traditional switch statements** kiểu cũ với các constant case labels không phải luôn exhaustiveness-checked theo cùng cách.

### Traditional switch statement

```java
static void printLevel(int level) {
    switch (level) {
        case 1:
            System.out.println("LOW");
            break;
        case 2:
            System.out.println("HIGH");
            break;
    }
}
```

Đây là ví dụ minh họa cho phép `level` không thuộc 1/2 thì không in gì. Muốn xử lý toàn bộ miền số nguyên, phải có policy fallback; nhưng không nên suy luận từ việc traditional switch statement này compile rằng **mọi pattern switch** cũng có thể thiếu nhánh.

**Checklist khi review:** xác định rõ loại switch bạn đang đọc, selector type, các case labels và các quy tắc exhaustiveness tương ứng, thay vì áp một quy tắc mặc định cho tất cả.

## 11. Bảng phân biệt compile-time check và behavioral tests

| Điều cần xác minh | Compiler Java 21 | Unit test / code review |
|---|---|---|
| Pattern type có hợp lệ không | Có | Không thay thế compiler |
| Pattern variable có scope đúng không | Có | Có thể hỗ trợ phát hiện bug logic |
| Case có bị dominated không | Có theo quy tắc ngôn ngữ | Không có test runtime khi code không compile |
| Sealed subtype bị thiếu trong switch expression không | Có | Cần test hành vi sau khi bổ sung |
| Một guard có thể false trong thực tế không | Chỉ phân tích theo quy tắc ngôn ngữ nhất định | **Cần test các điều kiện nghiệp vụ** |
| Enum constant thiếu case trong switch expression không | Có | Cần test mỗi trạng thái |
| `null` có bị NPE hay được xử lý riêng | Không mặc định chọn chính sách thay developer | **Cần test** |
| Component lá null có được validation đúng | Compiler biết kiểu, không biết policy domain | **Cần test** |
| Nhánh Open có thực sự trả kết quả nghiệp vụ đúng | Không | **Cần test** |
| Side effects như DB/event có đúng hay không | Không | Integration tests, mock/fake, review |
| Build dùng đúng version/module subtype mới | Cần cấu hình build chính xác | CI/regression/deployment checks |

**Không đánh đồng compile success với exhaustive behavior đúng.** Compiler chứng minh những điều được mô tả bởi hệ thống kiểu và quy tắc switch; nó không biết một Fund(0) phải bị từ chối hay một Close có reason blank phải hiển thị lỗi gì.

## 12. Checklist test để bảo vệ tính exhaustive qua thời gian

Một bộ regression tests nên có nhiều loại:

1. **Từng direct subtype:** ít nhất một input thuộc Open, Fund, Close.
2. **Guard đạt:** Open ID có text, Fund cents dương, Close ID/reason có text.
3. **Guard không đạt:** ID null/blank, cents bằng 0/âm, reason null/blank.
4. **Root null:** xác minh `case null` hoặc exception được thiết kế.
5. **Nested record null:** root Envelope có Command component null.
6. **Leaf null:** Envelope chứa Open(null), có kết quả dự kiến riêng.
7. **Hằng enum:** mọi giá trị từ `Phase.values()` có nhãn mong đợi.
8. **Null enum:** nếu API có thể nhận null, xác nhận NPE hay xử lý null theo hợp đồng.
9. **Subtype mới:** cập nhật `permits` và xác nhận build buộc rà soát switch chưa bao phủ, sau đó bổ sung case/test.
10. **Nhánh non-sealed:** test cả direct Extension và một subclass nếu chính sách dùng case Extension.
11. **Test expected độc lập:** không chỉ so hai implementation với nhau vì chúng có thể cùng chứa một lỗi.
12. **CI clean rebuild:** chạy build theo source target đúng và đảm bảo mọi module liên quan đều được biên dịch lại.

Ví dụ JUnit 5 cho một phương thức của chương trình mục 6 (cần dependency JUnit và đặt test trong cùng package):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ExhaustivenessChecklistTests {
    @Test
    void openWithNullIdGoesToSubtypeFallback() {
        var command = new ExhaustivenessChecklistDemo.Open(null);
        assertEquals("REJECT_OPEN",
                ExhaustivenessChecklistDemo.route(command));
    }

    @Test
    void fundAtZeroDoesNotPassGuard() {
        var command = new ExhaustivenessChecklistDemo.Fund("F3", 0);
        assertEquals("REJECT_FUND",
                ExhaustivenessChecklistDemo.route(command));
    }

    @Test
    void nullableNestedCommandHasExplicitFallback() {
        var envelope = new ExhaustivenessChecklistDemo.Envelope("e1", null);
        assertEquals("NESTED_MISSING",
                ExhaustivenessChecklistDemo.nested(envelope));
    }
}
```

Đây là **snippet JUnit 5 minh họa**, không thuộc phần đã được biên dịch bằng `javac --release 21` không có classpath framework. Các phương thức và record trong chương trình chính có visibility mặc định nên snippet phải ở cùng package. Trong codebase thực, nên tách mô hình domain và test fixture phù hợp.

Một kiểm tra động dùng `Phase.values()` có thể phát hiện các hằng mới khi chạy, nhưng **đừng chỉ viết loop không có expected**. Nếu mọi hằng mới tự nhận một default, test “không ném exception” có thể pass mà domain chưa có xử lý đúng.

## 13. Checklist review pull request: quy trình trước khi merge

### Trước khi xem switch

- [ ] Xác nhận JDK/source level hỗ trợ Java 21 pattern switch và record patterns.
- [ ] Xem selector type: `Command`, `Object`, enum hay generic type.
- [ ] Mở định nghĩa `sealed ... permits ...` và ghi nhận direct subtypes.
- [ ] Với mỗi subtype, xác định nó `final`, `sealed` hoặc `non-sealed`.
- [ ] Xác định rõ selector null là input hợp lệ hay là lỗi.

### Khi xem từng case

- [ ] Có nhánh cho mỗi subtype theo policy, không dựa vào default mơ hồ.
- [ ] Guarded cases đứng trước fallback cùng subtype.
- [ ] Guard có thể false được xử lý bằng case tương ứng ở sau.
- [ ] Nested record nullable có fallback nếu cần.
- [ ] Component null không bị dereference trước khi kiểm tra.
- [ ] Không có nhánh rộng che nhánh hẹp; compiler không báo dominated.
- [ ] Enum constants được liệt kê đầy đủ nếu muốn exhaustive check.
- [ ] Không có default mới được thêm chỉ để che lỗi compiler.
- [ ] Nhánh switch expression trả đúng result type/behavior theo hợp đồng.

### Trước khi merge

- [ ] Clean build với `javac --release 21` hoặc cấu hình build tương đương.
- [ ] Unit tests đủ subtype, guard true/false, null và biên.
- [ ] Tests kiểm tra output độc lập, không chỉ “chạy không ném lỗi”.
- [ ] Có regression test cho subtype mới hoặc thuộc tính mới.
- [ ] Khi sealed hierarchy đổi ở module khác, CI rebuild và chạy test các consumer.
- [ ] Đã review side effects của từng nhánh và fallback.
- [ ] Không ép `default` chỉ vì formatter hoặc thói quen từ switch cũ.

Mục tiêu checklist là tránh **cả hai cực đoan**: một switch luôn có default nên không ai biết thiếu subtype mới; hoặc một switch “không có default” nhưng chỉ có guarded cases nên thực tế không exhaustive.

## 14. Các sai lầm dễ gặp

### 14.1. “Sealed có ba subtype, tôi đã viết ba guarded cases là đủ”

Không chắc. Một `Fund(cents=0)` có thể không thỏa guard cents > 0. Cần fallback không guard hoặc cách biểu đạt khác bao phủ Fund còn lại. Chương trình `GuardOnly.java` bị compiler từ chối đúng vì lý do đó.

### 14.2. “Đặt default thì lúc nào cũng an toàn hơn”

Default có thể là policy hợp lý cho tập kiểu mở, nhưng đối với sealed/enum, nó có thể làm mất tín hiệu cần cập nhật case khi thêm subtype/hằng mới. “Code build xanh” chưa chắc là “logic được review đầy đủ”.

### 14.3. “Không có default thì null tự vào case của subtype”

Không. Null root không phải object thuộc subtype. Nếu API muốn xử lý null thành thông điệp riêng, thêm `case null`. Enum switch ví dụ đã xác nhận null có thể ném NPE dù đủ ba hằng.

### 14.4. “Tôi đã liệt kê đủ nested record subtypes, nên không cần fallback”

Nested record component có thể null. `Envelope("e1", null)` không khớp các nested patterns Open/Fund/Close. Cần fallback Envelope nếu muốn xử lý trường hợp đó mà không ném lỗi do không có case match.

### 14.5. “Pattern đã match nên mọi component chắc chắn non-null”

Không. `Open(var id)` có thể bind `id == null`. Exhaustive matching không đồng nghĩa validation. Với business rules, cần guard như `hasText(id)`.

### 14.6. “Compiler biết tôi muốn Open trước Fund hay Fund trước Close”

Compiler biết các quy tắc typing/dominance; không biết toàn bộ ưu tiên nghiệp vụ. Với nhiều guards cùng subtype, hai điều kiện có thể đồng thời đúng. Thứ tự case là một phần của policy cần test.

### 14.7. “Switch statement nào cũng phải exhaustive”

Không chính xác. Phân biệt traditional switch statement và enhanced switch statement dùng pattern/null label; Java 21 có quy tắc riêng. Switch expression phải exhaustive, dù selector là enum hay sealed type.

### 14.8. “non-sealed không liên quan vì sealed đã liệt kê Extension”

Một nhánh `non-sealed` có thể có nhiều subclass. Một case type pattern `Extension extension` thường bao phủ cả các subclass; chỉ xử lý một vài lớp con cụ thể không đủ để tuyên bố bao phủ toàn bộ nhánh.

### 14.9. “Compiler sẽ chỉ rõ lỗi domain khi case trả sai nhãn”

Không. Compiler chấp nhận `case Open open -> "CLOSE";` nếu các kiểu hợp lệ. Chỉ behavioral tests và review mới phát hiện nhãn không đúng hợp đồng.

### 14.10. “Không cần rebuild các consumer khi model được mở rộng”

Khi sealed/enum được thay đổi ở module khác, source consumer chưa rebuild có thể không trải qua lần kiểm tra exhaustiveness mới. CI phải bảo đảm cơ chế kiểm tra phù hợp phiên bản giữa các module, tránh dựa vào một build local cũ.

## 15. Bài tập tự kiểm tra có đáp án

### Bài 1 — Thêm subtype mới

Bạn mở rộng:

```java
sealed interface Command permits Open, Fund, Close, Refund {}
record Refund(String id, int cents) implements Command {}
```

Nhưng không cập nhật `route`. Điều gì sẽ xảy ra khi biên dịch lại switch expression không có default?

**Đáp án:** Compiler có thể báo non-exhaustive vì Refund chưa có nhánh. Cần thiết kế `case Refund(...)` và tests cho dữ liệu hợp lệ/không hợp lệ; không tùy tiện thêm `default` để che thiếu logic.

### Bài 2 — Guard chưa bao phủ giá trị zero

Chỉ có:

```java
case Fund(var id, var cents) when cents > 0 -> "OK";
```

Fund(0) nhận kết quả nào trong switch expression không có case khác?

**Đáp án:** Không có nhánh cho Fund(0), nên switch expression không thể được coi là exhaustive theo quy tắc thông thường. Thêm `case Fund ignored -> "REJECT";` là một giải pháp.

### Bài 3 — Default và exhaustive check

Một handler enum có ba hằng, nhưng người viết chỉ liệt kê hai hằng rồi thêm default. Code có thể compile không? Nó có bắt buộc cập nhật khi thêm hằng thứ tư không?

**Đáp án:** Có thể compile nhờ default. Khi thêm hằng mới, default có thể tiếp tục nhận giá trị đó mà không buộc tác giả sửa nhánh. Nếu domain yêu cầu xử lý tường minh từng hằng, nên liệt kê đủ.

### Bài 4 — Null nested

Với `new Envelope("trace",null)`, các case `Envelope(var trace, Open(...))`, `Envelope(...,Fund(...))` và `Envelope(...,Close(...))` có match không?

**Đáp án:** Không. Nested component Command null nên không khớp bất kỳ nested record pattern nào. Fallback Envelope không guard bắt được.

### Bài 5 — Null leaf

Với `new Envelope("trace",new Open(null))`, case `Envelope(var trace,Open(var id))` có match không?

**Đáp án:** Có; Open record khác null, `var id` bind component null. Nếu yêu cầu ID non-null, cần guard riêng.

### Bài 6 — when true

Một case `case Run(var n) when true` có thể exhaustive trên sealed hierarchy chỉ có Run không?

**Đáp án:** Có theo phép thử Java 21 của bài. Nhưng nên viết case không guard nếu không có điều kiện thực sự để code dễ hiểu và tránh hiểu nhầm.

### Bài 7 — non-sealed

Một instance `ExtensionChild` kế thừa `Extension` được `case Extension e` bắt không?

**Đáp án:** Có. Type pattern cho Extension nhận cả các subclass; chương trình kiểm chứng mục 8 đã in `extension child => EXTENSION`.

### Bài 8 — Enum null

Switch expression enum đã xử lý đủ NEW/RUNNING/DONE. Nếu truyền null, có được trả về DONE hay default không?

**Đáp án:** Không tự động. Trong ví dụ không có nhánh null, nó ném NullPointerException; bổ sung chính sách nếu null là input cần được hỗ trợ.

### Bài 9 — Vì sao lỗi dominated khác non-exhaustive?

**Đáp án:** Dominated xảy ra khi case phía trước đã bao phủ các giá trị mà case phía sau cần xử lý, làm case sau không thể đến được. Non-exhaustive xảy ra khi còn giá trị trong miền selector chưa được bao phủ. Hai lỗi cần cách sửa khác nhau.

### Bài 10 — Check code có đủ kiểu nhưng sai nghiệp vụ

Có đủ `case Open`, `case Fund` và `case Close`; nhưng `Fund(-1)` bị đưa vào nhánh ghi nhận thanh toán thành công. Compiler có phát hiện không?

**Đáp án:** Không; theo Java, -1 vẫn là int hợp lệ. Hãy thêm guard validation và test giá trị âm, zero, dương theo chính sách nghiệp vụ.

## 16. Quy trình sử dụng checklist trong dự án thực tế

Khi mở một pull request có thay đổi sealed hierarchy, nên làm lần lượt:

1. **Xác định thay đổi của mô hình kiểu:** thêm/bớt/đổi subtype nào, có nhánh non-sealed hoặc hierarchy lồng nhau không?
2. **Tìm mọi switch consumer:** trong handler, mapping, serialization, view layer, audit, validation, test. Không chỉ sửa switch đầu tiên báo lỗi.
3. **Kiểm tra mỗi switch theo kiểu selector:** enum/sealed/generic/Object, statement hay expression, có guard và nested record không.
4. **Cho compiler làm việc:** build theo đúng `--release`, không dùng default để né thông báo thiếu case.
5. **Review fallback:** mỗi subtype có guarded cases cần nhánh nhận phần còn lại theo policy; nested null có cách xử lý nếu có thể xuất hiện.
6. **Review null:** root selector và nullable components đã có hợp đồng rõ chưa?
7. **Bổ sung behavioral tests:** success, invalid, boundary, null, event/state effects nếu có.
8. **Chạy clean CI:** biên dịch lại các module phụ thuộc vào sealed/enum domain và chạy regression tests.
9. **Xem lại default có chủ đích:** default hợp lý cho miền mở nhưng cần lý do; tránh thêm tự động vào miền đóng.
10. **Kiểm tra deployment compatibility:** các service chia sẻ protocol/domain có thể nâng version không đồng bộ; cần contract tests và chiến lược rollout phù hợp.

Checklist này giúp sử dụng một lợi thế quan trọng của Java 21: compiler không chỉ đọc cú pháp pattern, mà còn hỗ trợ kiểm tra **tập giá trị cần xử lý**. Điều đó không thay thế review nghiệp vụ, nhưng giảm đáng kể nguy cơ quên một subtype mới nếu cấu trúc sealed/enum được quản lý tốt.

## Kết luận

**Checklist exhaustive và sealed type** phải đi xa hơn câu “đã đủ case chưa”. Hãy bắt đầu từ **selector type**, xem **permits hierarchy**, xác định các nhánh `final/sealed/non-sealed`, kiểm tra **guard có thể false**, giữ **fallback cùng subtype** khi cần, rồi xác định chính sách cho **null** và **nested nullable records**. Tránh `default` thừa nếu mục tiêu là compiler bắt thay đổi kiểu mới, đồng thời phân biệt traditional switch statements với switch expressions và enhanced pattern switch statements.

Chương trình Java 21 trong bài cho thấy ba lớp kiểm tra phối hợp: **javac** xác minh cú pháp/kiểu/dominance/exhaustiveness; **runtime tests** xác minh null, guard và boundary; **review** quyết định policy của mỗi subtype. Khi ba lớp này được sử dụng đúng vai trò, sealed hierarchy và pattern matching trở thành công cụ giúp code dễ mở rộng mà vẫn giữ được tính kiểm soát.

## Tài liệu tham khảo chính thức

- [JEP 409 — Sealed Classes (Java 17)](https://openjdk.org/jeps/409)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JLS Java SE 21 — Switch Statements §14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS Java SE 21 — Switch Expressions §15.28](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [JLS Java SE 21 — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html)
