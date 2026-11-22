# Migration từ preview feature sang Java ổn định: Java Core Pattern Matching

## 1. Vì sao cần migration, không chỉ bỏ `--enable-preview`?

Trong quá trình phát triển pattern matching, Java đã phát hành nhiều phiên bản **preview** để thu thập phản hồi trước khi chốt ngữ nghĩa và cú pháp. Mã biên dịch/chạy tốt trên một bản preview **không nhất thiết** còn biên dịch nguyên trạng trên Java 21: có cú pháp được đổi, có dạng pattern bị loại bỏ và có quy tắc xử lý `null`, dominance hoặc exhaustiveness được điều chỉnh.

Mục tiêu của một đợt migration tốt là:

1. Chốt **phiên bản Java đích** và phân loại các feature đang dùng: đã chính thức hay vẫn preview ở phiên bản đó.
2. Sửa source tương ứng với **cú pháp và ngữ nghĩa chính thức**, không dùng raw type, unchecked cast hoặc `default` quá rộng để che vấn đề.
3. Thay cấu hình build/test/runtime để biên dịch và chạy trên đúng JDK đích.
4. **Clean build lại toàn bộ class file**, không tái sử dụng binary preview của JDK cũ.
5. Kiểm tra hồi quy các nhánh pattern, guard, subtype, `null`, nested records và quy trình triển khai các module cùng nhau.

Trong bài này, đích chính là **Java 21** với các tính năng pattern matching **đã final**, nên ví dụ đầy đủ biên dịch với `javac --release 21` **không cần bật preview**. Nếu một ứng dụng còn sử dụng một preview feature **khác** của Java 21, cần xử lý riêng feature ấy trước khi bỏ mọi cờ preview trên toàn dự án.

## 2. Lộ trình preview → final cần biết

| Tính năng | Các bản preview quan trọng | Phiên bản chính thức | Ghi chú migration |
| --- | --- | --- | --- |
| Pattern matching cho `instanceof` | Java 14 — JEP 305; Java 15 — JEP 375 | **Java 16 — JEP 394** | Pattern variable không còn ngầm `final`; một số phép thử kiểu luôn đúng bị compiler từ chối |
| Records | Java 14 — JEP 359; Java 15 — JEP 384 | **Java 16 — JEP 395** | Record là data carrier; không đồng nghĩa với record pattern |
| Sealed classes/interfaces | Java 15 — JEP 360; Java 16 — JEP 397 | **Java 17 — JEP 409** | `sealed`, `permits`, `final`, `non-sealed` là nền tảng cho exhaustive `switch` |
| Pattern matching cho `switch` | Java 17 — JEP 406; Java 18 — JEP 420; Java 19 — JEP 427; Java 20 — JEP 433 | **Java 21 — JEP 441** | Guard chuyển sang `when`; quy tắc `null`, exhaustiveness, dominance và cú pháp tiếp tục được điều chỉnh qua các preview |
| Record patterns | Java 19 — JEP 405; Java 20 — JEP 432 | **Java 21 — JEP 440** | Hỗ trợ deconstruction và nested records; một số cú pháp preview không tồn tại trong final |

**Không nhầm phiên bản feature với phiên bản toàn bộ ứng dụng.** Ví dụ Java 17 dùng được `instanceof String text`, records và sealed classes mà không cần preview; nhưng pattern matching trong `switch` **vẫn là preview** trên Java 17. Java 21 mới đưa `switch` patterns và record patterns thành tính năng chính thức.

Một source file dùng nhiều tính năng có thể có **trạng thái preview hỗn hợp**. Vì vậy hãy kiểm tra từng cấu trúc, không chỉ tìm xem file có từ khóa `switch` hay không.

Nguồn chuẩn để đối chiếu là bảng [Oracle Java SE 21 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html) và các JEP ở cuối bài.

## 3. Cờ preview ở thời điểm trước và sau migration

### Khi còn dùng preview trong đúng JDK phát hành nó

Ví dụ **trên JDK 20**, với source thực sự sử dụng một preview feature của Java 20:

```bash
javac --enable-preview --release 20 PreviewApp.java
java --enable-preview PreviewApp
```

Đây là **ví dụ lệnh lịch sử**, chỉ phù hợp khi dùng **JDK 20** và đúng source Java 20 preview. Không thể dùng tùy tiện một JDK mới rồi yêu cầu `--enable-preview --release 20`: compiler thông thường chỉ hỗ trợ bật preview cho **release hiện tại của chính compiler đó**.

### Khi chuyển sang Java 21 với pattern features đã final

```bash
javac --release 21 MigrationSwitchDemo.java
java MigrationSwitchDemo
```

Không cần `--enable-preview` cho type patterns trong `instanceof`, sealed types, `switch` patterns và record patterns chính thức của Java 21.

**Cẩn thận:** việc thêm `--enable-preview` vào lệnh Java 21 không phải là một “chế độ tương thích với mọi cú pháp preview trước đây”. Flag này bật **các preview features của chính Java 21**, không hồi sinh cú pháp Java 17/18/19/20 đã bị thay thế. Nếu dự án có một preview feature độc lập khác ở Java 21, đừng xóa cờ mà chưa kiểm kê feature đó.

## 4. Rủi ro lớn: class file preview của JDK cũ không chuyển nguyên sang JDK mới

Mỗi class file có **major/minor version**. Với preview class files của các release từ Java 12 trở đi, **minor version 65535** đánh dấu việc phụ thuộc preview của release ấy. Ví dụ thường gặp:

- Java 20 class file chuẩn: **64.0**.
- Java 20 class file dùng preview của Java 20: **64.65535**.
- Java 21 class file chuẩn: **65.0**.

Theo JVMS, một class file phụ thuộc preview của một release **chỉ được load trên cùng release với preview được bật**; nó **không được load trên release khác**, kể cả khi release mới cũng có `--enable-preview`.

Điều đó có nghĩa: không thể tin rằng một JAR chứa Java 20 preview class file sẽ chạy trên Java 21 chỉ vì tính năng ấy đã trở thành final. **Phải biên dịch lại từ source phù hợp Java 21.** Một số class file khác trong JAR không dùng preview có thể vẫn chạy theo quy tắc binary compatibility thông thường, nhưng nên clean rebuild toàn bộ dự án để tránh sót file preview.

Có thể quan sát metadata class file:

```bash
javap -verbose MigrationSwitchDemo
```

Trong output, chú ý các dòng `major version` và `minor version`. Với class build bình thường bằng `javac --release 21` không dùng preview, kỳ vọng **major 65, minor 0**.

**Đừng sửa bytecode minor version bằng tay** để né kiểm tra: class file preview còn có thể phụ thuộc vào cú pháp/ngữ nghĩa và hợp đồng runtime cũ. Biện pháp đúng là rebuild, test và phát hành artifact mới.

## 5. Bảng migration cú pháp phổ biến

| Mã preview / ngữ cảnh cũ | Mã/chiến lược Java 21 | Nguyên nhân |
| --- | --- | --- |
| `case String s && test(s) ->` trong `switch` preview Java 17/18 | `case String s when test(s) ->` | Guard dùng `when` từ preview Java 19, được giữ trong Java 21 |
| `case (String s) ->` từng có parenthesized pattern | `case String s ->` | Parenthesized patterns bị loại trong Java 21 |
| `for (Point(var x, var y) : points)` từ record-pattern-enhanced-for preview Java 20 | `for (Point p : points) { ... }`, lấy component hoặc matching trong body | Record patterns trong header enhanced `for` **không được giữ** ở Java 21 |
| Named record pattern dạng `Point(int x, int y) point` từ preview Java 19 | Dùng `Point(var x, var y)` nếu chỉ cần component; hoặc `Point point` rồi gọi accessor nếu cần whole record | Named record patterns không còn được hỗ trợ từ preview Java 20 |
| `switch` dựa trên total pattern cũ để tiếp nhận `null` | Xác định rõ `case null` hoặc hợp đồng không-null | Java 19 preview trở đi thay đổi xử lý null; Java 21 không coi `default` là nhánh xử lý null |
| `switch` exhaustive có `default` thêm chỉ để qua compiler | Liệt kê case đúng subtype, giữ `default` **chỉ khi chủ đích** | Tránh che case mới hoặc hành vi chưa được xem xét |

**Không thực hiện search-and-replace mù.** Ví dụ `&&` vẫn hoàn toàn hợp lệ bên trong biểu thức guard:

```java
case String text when !text.isBlank() && text.length() < 20 ->
        "short-nonblank";
```

Điều cần thay là **dấu nối giữa pattern và guard trong nhãn `case`**, không phải mọi `&&` của chương trình.

## 6. Migration cụ thể: guard syntax `&&` → `when`

### Mã lịch sử của bản preview Java 17/18

```java
// Chỉ minh họa cú pháp preview cũ; KHÔNG biên dịch bằng Java 21.
static String classify(Object input) {
    return switch (input) {
        case String s && s.length() >= 4 -> "long-text";
        case String s -> "short-text";
        default -> "other";
    };
}
```

Ở preview cũ, guard được biểu diễn như một phần kết hợp với pattern bằng `&&`.

### Java 21 sau migration

```java
static String classify(Object input) {
    return switch (input) {
        case String s when s.length() >= 4 -> "long-text";
        case String s -> "short-text";
        case null -> "missing";
        default -> "other";
    };
}
```

Đây là **phương thức minh họa bên trong class**, không phải tệp chạy độc lập. Bản mới không chỉ thay cú pháp guard: nó **chủ động xác định hành vi của `null`** thông qua `case null`.

**Khi review**, cần test cả hai đường đi của guard: `"java"` trả `"long-text"` và `"go"` trả `"short-text"`. Kiểu sai như `Integer` đi `default`, còn `null` đi `case null`.

Nếu một case có `when` nhưng không có nhánh cùng kiểu không guard hoặc một pattern tổng quát phù hợp, `switch` có thể **không exhaustive**, dù đã có một case cho subtype ấy. Đừng coi guard là bao phủ toàn bộ kiểu.

## 7. Migration parenthesized pattern và named record pattern

### Parenthesized pattern bị loại trong Java 21

```java
// Cố tình không hợp lệ trên Java 21:
static String old(Object input) {
    return switch (input) {
        case (String s) -> s;
        default -> "other";
    };
}
```

Bản Java 21 bỏ cặp ngoặc quanh pattern:

```java
static String migrated(Object input) {
    return switch (input) {
        case String s -> s;
        case null -> "missing";
        default -> "other";
    };
}
```

Hai đoạn là **phương thức minh họa trong class**; không đặt chúng cùng source set production trước khi sửa đoạn lỗi.

### Named record pattern trong preview Java 19

Bản preview Java 19 từng có thể khai báo identifier cho cả record pattern:

```java
// Dạng lịch sử không còn hợp lệ trong Java 21:
if (input instanceof Point(int x, int y) point) {
    System.out.println(point);
}
```

Khi cần hai component, dùng:

```java
if (input instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

Khi cần **chính đối tượng record** (cho log, identity, method...), dùng type pattern và accessor:

```java
if (input instanceof Point point) {
    System.out.println(point);
    System.out.println(point.x() + point.y());
}
```

Các ví dụ trên giả định đã khai báo `record Point(int x, int y) {}`. Java 21 không có cú pháp deconstruction pattern **đồng thời đặt tên cả record** theo kiểu preview Java 19. Đừng cố thay bằng raw cast hoặc thêm biến `point` ngoài phạm vi.

## 8. Điểm dễ sót: record pattern trong header enhanced `for` bị loại

Java 20 preview cho phép record pattern xuất hiện ở header enhanced `for`, ví dụ dạng:

```java
// Cú pháp Java 20 preview, KHÔNG HỢP LỆ trong Java 21:
for (Point(var x, var y) : points) {
    System.out.println(x + y);
}
```

Theo Java 21 final (JEP 440), hỗ trợ cấu trúc này **đã bị loại bỏ**, dù record patterns trong `instanceof` và `switch` vẫn hoạt động.

Thay bằng enhanced `for` thông thường và truy cập component rõ ràng:

```java
for (Point point : points) {
    System.out.println(point.x() + point.y());
}
```

Hoặc nếu muốn giữ pattern matching trong thân vòng lặp:

```java
for (Point point : points) {
    if (point instanceof Point(var x, var y)) {
        System.out.println(x + y);
    }
}
```

Với mảng có thể chứa `null`, cách thứ hai **bỏ qua `null`** vì record pattern không khớp `null`; cách gọi `point.x()` trực tiếp sẽ ném `NullPointerException` với phần tử `null`. Vì vậy migration phải **xác định chính sách null và kiểm thử hành vi**; không coi hai ví dụ là tương đương tuyệt đối trên mọi input.

Chương trình hoàn chỉnh `EnhancedForMigrationDemo.java`:

```java
public class EnhancedForMigrationDemo {
    record Point(int x, int y) {}

    public static void main(String[] args) {
        Point[] points = {
            new Point(2, 3),
            null,
            new Point(4, 1)
        };

        for (Point point : points) {
            if (point instanceof Point(var x, var y)) {
                System.out.println("sum=" + (x + y));
            }
        }
    }
}
```

```bash
javac --release 21 EnhancedForMigrationDemo.java
java EnhancedForMigrationDemo
```

Output:

```text
sum=5
sum=5
```

Đây là cách viết Java 21 rõ ràng và có chính sách `null` cụ thể. Nếu nghiệp vụ không cho phép phần tử `null`, hãy chủ động validate và báo lỗi thay vì bỏ qua.

## 9. Một chương trình Java 21 hoàn chỉnh sau migration

Ví dụ này kết hợp **sealed hierarchy**, **records**, **record patterns**, `switch` expressions, `when` guard và `case null`. Không có preview flag.

Lưu tệp `MigrationSwitchDemo.java`:

```java
public class MigrationSwitchDemo {
    sealed interface Result permits Accepted, Rejected {}

    record Accepted(String id, long cents) implements Result {}
    record Rejected(String id, String reason)
            implements Result {}

    static String describe(Result value) {
        return switch (value) {
            case Accepted(var id, var cents) when cents >= 1000 ->
                    "large:" + id;

            case Accepted(var id, var cents) ->
                    "accepted:" + id + ":" + cents;

            case Rejected(var id, var reason) ->
                    "rejected:" + id + ":" + reason;

            case null ->
                    "null-result";
        };
    }

    static void check(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + " expected=" + expected
                            + " actual=" + actual);
        }

        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        check("small", "accepted:A:500",
                describe(new Accepted("A", 500)));

        check("large", "large:B",
                describe(new Accepted("B", 1500)));

        check("rejected", "rejected:C:blocked",
                describe(new Rejected("C", "blocked")));

        check("null", "null-result", describe(null));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 MigrationSwitchDemo.java
java MigrationSwitchDemo
```

**Stdout chính xác:**

```text
PASS small
PASS large
PASS rejected
PASS null
```

### Điểm cần kiểm tra trong migration

- `Result` là sealed interface: chỉ cho hai subtype trực tiếp `Accepted` và `Rejected`.
- Mỗi record là `final`; do đó biểu thức `switch` có thể **exhaustive mà không cần `default`**.
- `Accepted` có guard `when cents >= 1000`; case `Accepted` thứ hai **không có guard**, nên bao phủ các giá trị `Accepted` còn lại.
- `case null` tách chính sách selector `null` khỏi type coverage của sealed hierarchy.
- Test kiểm tra cả guard đúng/sai và cả subtype; phương thức `check` ném `AssertionError` trực tiếp, **không phụ thuộc tùy chọn `-ea`**.

Nếu sau này thêm `Pending implements Result`, cần cập nhật `permits` và xem lại `switch` trong lần biên dịch kế tiếp. Nếu chỉ thêm `default` để “xanh build”, consumer có thể mất cơ hội phát hiện nghiệp vụ chưa xử lý biến thể mới.

## 10. Generic record patterns khi chuyển từ preview

Một thay đổi đáng chú ý trong preview Java 20 là khả năng **suy luận type arguments** cho generic record patterns, được giữ và hoàn thiện trong bản chính thức Java 21.

Giả sử:

```java
record Box<T>(T value) {}
record Envelope<T>(T payload) {}
```

Khi đã có kiểu tĩnh đầy đủ:

```java
Box<Box<String>> typed = new Box<>(new Box<>("hello"));

if (typed instanceof Box(Box(var text))) {
    String s = text; // Compiler suy luận được String.
    System.out.println(s);
}
```

Đây là **đoạn minh họa với record đã khai báo**. Kiểu của `text` được suy luận nhờ **static generic type** `Box<Box<String>>`, chứ không phải do JVM khôi phục type argument bị type erasure xóa mất.

Khi input chỉ có kiểu `Object`, nên kiểm tra **component thực tế** bằng type patterns:

```java
Object input = new Envelope<>(new Box<>("hello"));

if (input instanceof Envelope(Box(String text))) {
    System.out.println(text);
}
```

Đừng refactor thành `input instanceof Envelope<Box<String>>(...)` rồi ngạc nhiên khi compiler từ chối unchecked conversion; type arguments cụ thể không được runtime kiểm chứng từ một giá trị `Object` tùy ý.

### Ví dụ đầy đủ kiểm thử nested record patterns sau migration

Lưu `NestedRecordMigrationDemo.java`:

```java
public class NestedRecordMigrationDemo {
    record Box<T>(T value) {}
    record Envelope<T>(T payload) {}

    static String unpack(Object input) {
        return switch (input) {
            case Envelope(Box(String value)) ->
                    "text:" + value;

            case Envelope(Box(var value)) ->
                    "box-other:" +
                    (value == null
                            ? "null"
                            : value.getClass().getSimpleName());

            case Envelope(var payload) ->
                    "envelope-other:" +
                    (payload == null
                            ? "null"
                            : payload.getClass().getSimpleName());

            case null ->
                    "null";

            default ->
                    "other";
        };
    }

    public static void main(String[] args) {
        Object[] cases = {
            new Envelope<>(new Box<>("hello")),
            new Envelope<>(new Box<>(42)),
            new Envelope<>(new Box<>(null)),
            new Envelope<>(null),
            null,
            "plain"
        };

        for (Object value : cases) {
            System.out.println(unpack(value));
        }
    }
}
```

```bash
javac --release 21 NestedRecordMigrationDemo.java
java NestedRecordMigrationDemo
```

Stdout:

```text
text:hello
box-other:Integer
box-other:null
envelope-other:null
null
other
```

**Lưu ý về `null`:** record pattern lồng `Box(...)` không khớp khi chính component `Box` là `null`; nhánh `Envelope(var payload)` có thể nhận payload `null`. Đồng thời `Box(String value)` không khớp với component `null`; nhánh `Box(var value)` trong cùng cấu trúc có thể ràng buộc component `null`.

Đây là lý do migration nên có test riêng cho **outer null, nested null và component null**, không chỉ test dữ liệu hợp lệ phổ biến.

## 11. Null semantics thay đổi qua các preview — cần test lại

Qua các lần preview của pattern `switch`, quy tắc liên quan `null` đã được điều chỉnh. Java 21 final có nguyên tắc rõ ràng:

```java
static String describe(Object value) {
    return switch (value) {
        case String s -> "text:" + s;
        case null -> "missing";
        default -> "other";
    };
}
```

- `describe("a")` trả `"text:a"`.
- `describe(42)` trả `"other"`.
- `describe(null)` trả `"missing"`.

Nếu **bỏ `case null`**, mặc dù `default` còn tồn tại, `switch(null)` thông thường vẫn ném **`NullPointerException`**.

Vì vậy khi nâng cấp từ preview cũ:

1. Tìm mọi `switch` nhận reference hoặc nullable selector.
2. Xác định hợp đồng xử lý `null`: chấp nhận, từ chối hay báo lỗi.
3. Dùng `case null` nếu business logic phải xử lý trực tiếp; còn nếu không cho phép `null`, validate ở boundary hoặc test đúng lỗi đã quy định.
4. **Không** thay tất cả case thiếu bằng `default` rồi cho rằng đã xử lý `null`.
5. Test nested record component `null` riêng với selector `null`.

Thay đổi về null-matching có thể làm chương trình vẫn biên dịch mà **đổi nhánh được chọn**, nên kiểm thử hồi quy quan trọng không kém việc sửa lỗi cú pháp.

## 12. Exhaustiveness và dominance sau khi bỏ preview

Java 21 yêu cầu `switch` expression và enhanced pattern `switch` statement đáp ứng các quy tắc exhaustiveness phù hợp; quy tắc dominance cũng ngăn những case bị che bởi pattern tổng quát trước đó.

Ví dụ **cố ý không biên dịch**:

```java
static String wrong(Object value) {
    return switch (value) {
        case CharSequence seq -> "sequence";
        case String text -> "string"; // Bị CharSequence che.
        default -> "other";
    };
}
```

`String` implements `CharSequence`; với type pattern `CharSequence` đứng trước, case `String` không thể được chọn. Trong Java 21 compiler phát hiện lỗi dominance.

Bản sửa là **đặt subtype cụ thể trước supertype**:

```java
static String correct(Object value) {
    return switch (value) {
        case String text -> "string";
        case CharSequence seq -> "sequence";
        case null -> "null";
        default -> "other";
    };
}
```

Cả hai đoạn là **phương thức minh họa bên trong class**, đoạn `wrong` chỉ dùng cho negative compile test.

Với sealed hierarchy trong `MigrationSwitchDemo`, `Accepted` có case có guard và không guard. Nếu xóa case không guard, một số `Accepted` không đạt điều kiện `cents >= 1000` sẽ thiếu đường đi; `switch` có thể bị compiler từ chối vì không exhaustive.

**Migration guideline:** hãy **sửa để compiler chứng minh đủ nhánh**, không tạo `default -> null` một cách máy móc. Nếu domain cần xử lý subtype mới rõ ràng, `default` quá rộng che lỗi nghiệp vụ và mất bảo đảm khi mở rộng type hierarchy.

## 13. Preview source compatibility khác với binary compatibility

Một bản nâng cấp Java có ít nhất ba lớp cần đánh giá:

| Lớp | Câu hỏi kiểm tra | Ví dụ rủi ro |
| --- | --- | --- |
| **Source compatibility** | Source cũ có biên dịch bằng Java 21 final không? | Guard dùng `&&`, parenthesized pattern, enhanced-for record pattern header |
| **Preview binary compatibility** | Artifact `.class` đã build với preview cũ có load được bởi Java 21 không? | Java 20 preview class file với minor `65535` không load trên release Java 21 |
| **Runtime/domain compatibility** | Consumer đã biên dịch và data hiện hành có vẫn hoạt động đúng không? | Sealed hierarchy thêm subtype; consumer cũ có `switch` từng exhaustive có thể gặp `MatchException` |

Một source “đã sửa cho compile” có thể vẫn làm thay đổi logic khi chuyển `null` hay guard. Ngược lại, một JAR được build lại có thể load bình thường nhưng consumer khác đã biên dịch trước đó không biết subtype mới.

**`MatchException` không phải bằng chứng preview class file load được**: đó là một lỗi runtime riêng khi pattern matching thất bại theo các điều kiện nhất định, ví dụ consumer cũ nhận subtype mới sau thay đổi domain. Lỗi tải class preview cũ và lỗi exhaustive switch qua versioning là hai nhóm khác nhau.

Khi deploy nhiều module, nên build/test toàn bộ những consumer xử lý shared sealed hierarchy hoặc message schema. Kiểm tra chỉ một module nguồn không đủ cho hệ thống có client/server nâng cấp khác thời điểm.

## 14. Nếu sản phẩm vẫn phải chạy Java 17 thì sao?

Nếu target runtime vẫn là Java 17, **không được dùng pattern `switch` và record patterns final của Java 21** trong source biên dịch `--release 17`. Java 17 chỉ hỗ trợ pattern matching for `switch` ở trạng thái preview; đừng bật preview trong production nếu chính sách yêu cầu tính năng ổn định.

Giải pháp tương thích Java 17 là dùng **type pattern cho `instanceof`** (đã final từ 16), sealed hierarchy và accessor của records (records final từ 16).

Ví dụ độc lập `Java17FallbackDemo.java`:

```java
public class Java17FallbackDemo {
    sealed interface Result permits Good, Bad {}

    record Good(String value) implements Result {}
    record Bad(int code) implements Result {}

    static String render(Result result) {
        if (result instanceof Good good) {
            return "ok:" + good.value();
        }

        if (result instanceof Bad bad) {
            return "bad:" + bad.code();
        }

        throw new IllegalArgumentException("null or unknown");
    }

    public static void main(String[] args) {
        System.out.println(render(new Good("ready")));
        System.out.println(render(new Bad(3)));
    }
}
```

```bash
javac --release 17 Java17FallbackDemo.java
java Java17FallbackDemo
```

Output:

```text
ok:ready
bad:3
```

Mã trên không sử dụng pattern `switch` hoặc record deconstruction, nên có thể biên dịch với target Java 17. Khi gọi `render(null)`, hàm ném `IllegalArgumentException`, và code Java 21 thay thế phải quyết định có giữ hành vi ấy hay không.

**Đánh đổi:** Java 17 không có exhaustive pattern switch final tương ứng, nên cần unit tests, code review và quy ước kiểm tra từng subtype để tránh thiếu nhánh khi thêm biến thể.

## 15. Cách điều chỉnh Maven khi mục tiêu là Java 21 final

Trong `pom.xml` của dự án Maven, bảo đảm compiler target release là 21, ví dụ:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Đây là **một đoạn `pom.xml`**, không phải file Maven hoàn chỉnh. Phải dùng Maven Compiler Plugin/JDK tương thích và kiểm tra cấu hình thực tế của project.

Nếu trước đây bật preview, cần rà soát **đúng vị trí** có các cờ:

- Compiler: `--enable-preview` trong `maven-compiler-plugin`/compiler args.
- Unit tests: `--enable-preview` trong `maven-surefire-plugin`, `maven-failsafe-plugin` hoặc JVM argLine.
- Ứng dụng lúc chạy: `--enable-preview` trong startup script, container image, server flags.
- IDE: language level được chọn là preview của JDK cũ.

Khi toàn bộ source dùng **pattern features đã final trong Java 21** và **không còn feature preview nào khác**, bỏ các cờ ấy và build sạch:

```bash
mvn clean verify
```

**Không xóa cờ preview một cách toàn cục nếu dự án còn sử dụng preview feature khác.** Xử lý/loại bỏ hoặc phân tách tính năng đó theo policy riêng rồi mới quyết định cờ cho các task cụ thể.

Ở project nhiều module, Maven toolchain/compiler release của từng module phải thống nhất mục tiêu hợp đồng; không được giả định module Java 21 chạy trên runtime Java 17.

## 16. Cách điều chỉnh Gradle và môi trường CI

Với dự án Gradle dùng Kotlin DSL, cấu hình Java toolchain/release có thể viết:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
```

Đây là **đoạn cấu hình trong `build.gradle.kts`** khi Java plugin và các type/API tương ứng đã sẵn có, không phải toàn bộ script. Cần xác nhận test task/JavaExec task cũng chạy với JVM thích hợp nếu project dùng cấu hình custom.

Với một project chỉ còn tính năng Java 21 final, cần rà soát/xóa flag preview từng được thêm vào:

```text
--enable-preview
```

ở `JavaCompile.options.compilerArgs`, `Test.jvmArgs`, `JavaExec.jvmArgs`, IDE run configuration hoặc command khởi động thực tế.

**CI nên xác nhận cả JDK chạy test, không chỉ compiler target.** `--release 21` kiểm soát tương thích source/standard API/class file target trong quá trình compile, nhưng một test chạy trên JDK khác có thể cho kết quả vận hành khác với môi trường production. Với migration quan trọng, nên chạy ít nhất một lane trên JDK 21 thực tế và dùng cùng JVM flags dự kiến deploy.

## 17. Chiến lược kiểm thử migration: compile, behavior và integration

Một test plan có thể chia theo lớp:

| Tầng | Thao tác | Kỳ vọng |
| --- | --- | --- |
| **Compile-positive** | `javac --release 21` không preview cho source mới | Không còn cú pháp preview đã bị bỏ |
| **Compile-negative** | Thử fixture với cú pháp `case String s && ...` hoặc `for (Point(var x, var y) : ...)` | Compiler Java 21 **từ chối** fixture như dự kiến |
| **Runtime branch tests** | Giá trị đúng kiểu, sai kiểu, guard đúng/sai | Kết quả tương ứng đúng |
| **Null regression** | Selector `null`, nested record null, component null | Đúng chính sách đã chọn |
| **Exhaustiveness test** | Thêm subtype vào sealed hierarchy, biên dịch lại consumer | Compiler phát hiện case thiếu khi không có catch-all phù hợp |
| **Binary scan** | Dùng `javap -verbose` với artifact build | Không còn preview class file từ release cũ |
| **Integration/rollout** | Chạy consumer + shared libraries phiên bản đích | Không gặp lỗi class loading, schema hoặc mismatch subtype |

**Negative compile test** cố ý chứa source không biên dịch nên phải đặt trong fixture riêng, không trộn vào `src/main/java` khiến build production thất bại. Nếu tự động kiểm tra lỗi, ưu tiên so `javac` exit code khác 0 thay vì phụ thuộc tuyệt đối vào câu chữ diagnostic.

Các test runtime nên có cả **boundary case của guard** (`999`, `1000` khi ngưỡng là `>= 1000`) và trường hợp subtype mới. Bỏ `default` một cách có chủ đích ở sealed `switch` thường giúp compiler nhắc consumer cập nhật khi type hierarchy mở rộng.

## 18. Triển khai theo từng bước để giảm rủi ro

**Bước 1 — Inventory.** Tìm các source/module có `--enable-preview`, `switch` type/record patterns, `case ... && ...`, named/parenthesized patterns hoặc record pattern trong header enhanced `for`. Xác định từng vị trí đang dùng tính năng thuộc release nào.

**Bước 2 — Chọn target.** Nếu có thể dùng Java 21, các pattern features trong bài đã final. Nếu phải giữ Java 17, chọn đường fallback với `instanceof` và accessors.

**Bước 3 — Sửa cú pháp đã thay đổi.** Chuyển guard sang `when`, bỏ parenthesized pattern, thay named record pattern, viết lại enhanced-for header. Với mỗi thay đổi, lưu lại hợp đồng null/guard/exhaustiveness cần giữ.

**Bước 4 — Xem lại domain.** Nếu code dùng sealed hierarchy, kiểm tra `permits` và mọi consumer switch khi thêm subtype. Đừng dùng `default` để bỏ qua logic mới.

**Bước 5 — Clean rebuild với JDK đích.** Không tái sử dụng build cache hoặc JAR preview cũ như một đường tắt. Đảm bảo các thư viện nội bộ dùng chung cũng đã được phát hành với target phù hợp.

**Bước 6 — Test chạy được và negative compile.** Kiểm tra cú pháp final, null, nested components và các nhánh guard bằng test đáng tin. So sánh kết quả với hành vi nghiệp vụ mong muốn, không chỉ với cách một bản preview cụ thể từng chạy.

**Bước 7 — Chốt build/runtime flags.** Khi không còn preview feature khác, bỏ `--enable-preview` khỏi compiler, test runner và startup. Kiểm tra manifest/docker/IDE nếu cần.

**Bước 8 — Integration và rollout.** Test application, service consumers, deserializer/persistence và các shared domain artifacts trong tổ hợp phiên bản được triển khai thực tế.

Nếu dự án có các môi trường nâng cấp lệch pha, triển khai theo giai đoạn với contract tests riêng; Java 21 source chạy tốt trong một service **không bảo đảm** client cũ đã sẵn sàng hiểu subtype hay schema mới.

## 19. Cạm bẫy cần tránh

1. **“`--enable-preview` trên JDK 21 cho phép mọi cú pháp preview từ JDK 17–20.”** Sai. Flag này chỉ bật preview của release hiện hành.
2. **“Pattern matching đã final, nên các `.class` preview cũ chạy được luôn.”** Sai. Preview class files gắn với một release và cần rebuild.
3. **“Mọi pattern matching đều final từ Java 16.”** Sai. `instanceof` final ở 16; `switch` pattern và record patterns final ở 21.
4. **“Guard `&&` của preview có thể giữ nguyên trong Java 21.”** Sai ở vị trí nối pattern với guard; dùng `when`.
5. **“Record pattern trong enhanced-for header còn hoạt động vì record patterns final ở 21.”** Sai. Cú pháp header ấy bị loại.
6. **“Có thể giữ `Point(int x, int y) point` của preview Java 19.”** Sai. Dùng record pattern không gắn identifier cho whole record, hoặc dùng type pattern `Point point`.
7. **“`case null` và `default` là một.”** Sai. Không có `case null`, selector null thường gây `NullPointerException`.
8. **“Thêm `default` luôn là cách đúng để sửa exhaustive switch.”** Sai. Có thể che thiếu logic cho subtype mới.
9. **“`record Box<T>` khôi phục type argument qua runtime.”** Sai. Generic type erasure vẫn tồn tại; pattern inference dựa trên static type hoặc component checks.
10. **“Biên dịch thành công là migration xong.”** Sai. Phải kiểm tra runtime behavior, binary preview, nested null, versioning và deployment.
11. **“`--release 21` có thể dùng rồi chạy cùng bytecode ấy trên Java 17.”** Sai. Java 17 không hỗ trợ class-file version 65 của Java 21.
12. **“Nên thay tất cả preview code bằng `instanceof`/cast để tránh chỉnh build.”** Không cần. Java 21 final đã có pattern switch và record patterns; dùng cú pháp chính thức giúp code an toàn và biểu đạt domain rõ hơn.

## 20. Checklist review trước khi kết thúc migration

- Target runtime/JDK đã được ghi rõ là Java 21 hay bản khác chưa?
- Đã phân biệt `instanceof` final Java 16, sealed final Java 17, `switch`/record pattern final Java 21 chưa?
- Còn `case ... && ...`, parenthesized pattern, named record pattern hoặc record pattern trong enhanced-for header không?
- Đã kiểm tra `when` guard cho cả true/false và ngưỡng biên chưa?
- Đã kiểm tra `null` của selector, record lồng và component chưa?
- Các sealed `switch` có còn exhaustive khi thêm subtype không? `default` có che case chưa xử lý không?
- Đã clean rebuild và xác nhận artifact không còn preview class files cũ chưa?
- Các module dùng chung Java 21 đã được build/deploy đồng bộ và thử nghiệm cùng nhau chưa?
- `--enable-preview` có được bỏ **chỉ sau khi** loại trừ những preview feature khác đang dùng không?
- Maven/Gradle/IDE/CI/test runtime có cùng target và flags hợp lệ không?
- Có bộ test runnable và negative compile test tách biệt, không đưa source lỗi vào production không?
- Đã ghi rõ đường rollback và giám sát lỗi class loading/`MatchException` trong rollout chưa?

**Kết luận:** Migration từ Java preview sang Java 21 final là **migration source + binary + hành vi**, không chỉ là xóa một cờ compiler. Giữ ưu điểm của pattern matching, sửa cú pháp đã thay, kiểm tra `null`/guards/exhaustiveness, **rebuild toàn bộ artifact preview** và chạy kiểm thử tương thích trên JDK đích là con đường đáng tin cậy.

## Tài liệu tham khảo

- [Oracle Java SE 21 — Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Oracle Java SE 21 — Language Changes Summary](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-summary.html)
- [JEP 305 — Pattern Matching for `instanceof` (Preview)](https://openjdk.org/jeps/305)
- [JEP 375 — Pattern Matching for `instanceof` (Second Preview)](https://openjdk.org/jeps/375)
- [JEP 394 — Pattern Matching for `instanceof` (Final)](https://openjdk.org/jeps/394)
- [JEP 409 — Sealed Classes (Final)](https://openjdk.org/jeps/409)
- [JEP 406 — Pattern Matching for `switch` (Preview)](https://openjdk.org/jeps/406)
- [JEP 420 — Pattern Matching for `switch` (Second Preview)](https://openjdk.org/jeps/420)
- [JEP 427 — Pattern Matching for `switch` (Third Preview)](https://openjdk.org/jeps/427)
- [JEP 433 — Pattern Matching for `switch` (Fourth Preview)](https://openjdk.org/jeps/433)
- [JEP 441 — Pattern Matching for `switch` (Final)](https://openjdk.org/jeps/441)
- [JEP 405 — Record Patterns (Preview)](https://openjdk.org/jeps/405)
- [JEP 432 — Record Patterns (Second Preview)](https://openjdk.org/jeps/432)
- [JEP 440 — Record Patterns (Final)](https://openjdk.org/jeps/440)
- [Java SE 21 JVMS §1.5 — Preview Features](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-1.html#jvms-1.5)
- [Java SE 21 JLS §14.11 — `switch` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
