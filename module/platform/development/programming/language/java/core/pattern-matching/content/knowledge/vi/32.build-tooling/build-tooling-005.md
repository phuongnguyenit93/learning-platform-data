# Compiler warning liên quan pattern: phân loại, tái hiện và xử lý khi build Java

Khi thêm **pattern matching** vào dự án Java, bạn có thể gặp thông báo từ `javac` về *preview feature*, *unchecked cast*, *raw type* hoặc *redundant cast*. Đồng thời, những lỗi như **dominated case** và **switch expression không exhaustive** đôi khi bị gọi nhầm là "warning" dù thực tế **là lỗi biên dịch**. Đọc đúng loại diagnostic giúp chọn cách xử lý: sửa mã, cấu hình toolchain, cập nhật mức Java, hay chủ động bật một kiểm tra lint.

Bài thuộc chủ đề **Build và tooling**. Mục tiêu là sử dụng compiler để hiểu cảnh báo liên quan tới mã có pattern, thay vì chỉ học cú pháp `instanceof`/`switch`.

**Phạm vi phiên bản:**
- Type patterns trong `instanceof` đã **final từ Java 16** (JEP 394).
- Record patterns và pattern matching cho `switch` đã **final từ Java 21** (JEP 440, JEP 441).
- Ví dụ chính trong bài được kiểm chứng với **`javac 24.0.2 --release 21`**, nghĩa là biên dịch theo quy tắc ngôn ngữ Java 21, **không cần `--enable-preview`**.
- Phần minh họa **primitive patterns preview trên JDK 24** có cờ `--enable-preview --release 24` riêng. Đây là ví dụ về cảnh báo preview **ở đúng JDK 24**, không phải lời khẳng định primitive patterns còn preview ở mọi phiên bản Java về sau.

## 1. Phân biệt warning, error và hành vi runtime

| Loại | Khi nào xuất hiện? | Ảnh hưởng build | Ví dụ |
| --- | --- | --- | --- |
| **Warning** | `javac` nhận ra mã hợp lệ nhưng có yếu tố đáng chú ý | Thường vẫn tạo `.class` nếu không bật `-Werror` | `[unchecked]`, `[rawtypes]`, `[cast]`, `[preview]` |
| **Error** | Mã vi phạm quy tắc cú pháp/kiểu/dominance/exhaustiveness | Không biên dịch được phần có lỗi | `this case label is dominated ...` |
| **Runtime exception** | Mã đã biên dịch nhưng lúc chạy gặp dữ liệu hoặc trạng thái gây lỗi | Xảy ra khi thực thi | `NullPointerException` do component `null` |

**Nguyên tắc quan trọng:** pattern matching là tính năng **final** không có nghĩa compiler sẽ ngừng cảnh báo các thao tác nguy hiểm **xung quanh** pattern. Ví dụ:

```java
if (value instanceof java.util.List<?> list) {
    return (java.util.List<String>) list; // Vẫn là unchecked cast.
}
```

Pattern kiểm tra được đối tượng là một `List`, nhưng không chứng minh các phần tử đều là `String`. Vì vậy compiler vẫn có lý do phát warning về cast generic, mặc dù `instanceof List<?> list` là hợp lệ và đã ổn định.

Ngược lại, dùng đúng cú pháp final:

```java
if (value instanceof String text) {
    return text.length();
}
```

không tự tạo warning chỉ vì có từ khóa `instanceof`.

## 2. Các cờ javac hữu ích

Các lệnh cơ bản:

```bash
javac -version
javac --help-lint
javac --release 21 -Xlint:all PatternWarningDemo.java
javac --release 21 -Xlint:all -Werror PatternWarningDemo.java
```

Trong thực tế, chỉ chạy những lệnh có tên tệp nguồn đã tồn tại. Danh sách `--help-lint` phụ thuộc vào compiler đang dùng.

| Cờ | Mục đích | Liên hệ với pattern |
| --- | --- | --- |
| `-Xlint:all` | Bật tất cả các nhóm cảnh báo lint được hỗ trợ | Dễ phát hiện vấn đề xung quanh mã refactor dùng pattern |
| `-Xlint:cast` | Báo các phép cast không cần thiết | Cast thừa sau `instanceof Type variable` |
| `-Xlint:unchecked` | Báo thao tác generic không được compiler chứng minh an toàn | Cast từ `List<?>` sang `List<String>` |
| `-Xlint:rawtypes` | Báo sử dụng kiểu generic ở dạng raw | `List raw` trong mã legacy |
| `-Xlint:preview` | Báo việc sử dụng tính năng ngôn ngữ đang là preview | Preview ở đúng bản JDK được bật |
| `-Xlint:fallthrough` | Báo một số trường hợp rơi từ nhánh sang nhánh trong `switch` dạng cũ | Chủ yếu liên quan switch kiểu colon, không phải cảnh báo mặc định cho các case dạng `->` |
| `-Werror` | Xem cảnh báo đã phát hiện là nguyên nhân **thất bại build** | Dùng trong CI để không cho warning mới đi qua |
| `--release N` | Chọn mức ngôn ngữ, target class file và API nền tảng của Java `N` | Ngăn dùng nhầm cú pháp Java 21 khi dự án chỉ cam kết Java 17 |
| `--enable-preview` | Bật tính năng preview của **mức source hợp lệ với compiler đó** | Chỉ dùng khi thực sự cần feature chưa final ở JDK tương ứng |

**Phân biệt `-Xlint:all` và `-Werror`:** cờ đầu quyết định nhiều nhóm warning được phát ra; cờ sau quyết định warning đó có làm **compile fail** hay không. `-Werror` không biến mã sai thành hợp lệ và không biến tất cả runtime bug thành diagnostic.

`javac` có thể in dạng `Note: ... uses unchecked or unsafe operations` khi không bật lint chi tiết. Nếu cần tìm nguyên nhân, biên dịch lại với `-Xlint:unchecked` thay vì dựa vào dòng "Note" ngắn.

## 3. Ví dụ Java 21 final: pattern hợp lệ không tự gây warning

Đây là chương trình Java 21 hoàn chỉnh, **đã biên dịch với `-Xlint:all -Werror` mà không có warning**.

Lưu thành **`PatternWarningDemo.java`**:

```java
import java.util.List;

public class PatternWarningDemo {
    sealed interface Entry permits Text, Count {}
    record Text(String value) implements Entry {}
    record Count(int value) implements Entry {}

    static String classify(Entry entry) {
        return switch (entry) {
            case null -> "null";
            case Text(var value) when value == null -> "missing";
            case Text(var value) -> "text=" + value;
            case Count(int n) when n < 0 -> "negative=" + n;
            case Count(var n) -> "count=" + n;
        };
    }

    static String checkList(Object value) {
        if (!(value instanceof List<?> elements)) {
            return "not-a-list";
        }
        for (Object element : elements) {
            if (!(element instanceof String)) {
                return "mixed-list";
            }
        }
        return "string-list-size=" + elements.size();
    }

    public static void main(String[] args) {
        System.out.println(classify(new Text("Java")));
        System.out.println(classify(new Text(null)));
        System.out.println(classify(new Count(-1)));
        System.out.println(classify(new Count(2)));
        System.out.println(classify(null));
        System.out.println(checkList(List.of("A", "B")));
        System.out.println(checkList(List.of("A", 1)));
        System.out.println(checkList(null));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 -encoding UTF-8 -Xlint:all -Werror PatternWarningDemo.java
java PatternWarningDemo
```

**Stdout chính xác:**

```text
text=Java
missing
negative=-1
count=2
null
string-list-size=2
mixed-list
not-a-list
```

Giải thích:

1. `Text` và `Count` là hai subtype `final` của `sealed interface Entry`. Switch xử lý đủ hai subtype và selector `null`.
2. `Text(var value)` tách thành phần của record. Component `value` có thể `null`, nên guard `value == null` được đặt trước nhánh chung.
3. `Count(int n) when n < 0` là nhánh có guard; `Count(var n)` còn lại bắt giá trị số không âm.
4. `value instanceof List<?> elements` là type pattern có thể dùng vì `List<?>` là kiểu **reifiable** cho mục đích kiểm tra runtime; nó không tuyên bố rằng `elements` là `List<String>`.
5. `for (Object element : elements)` kiểm tra **từng phần tử** thay vì cast generic không an toàn.
6. `null` trong `checkList` khiến `instanceof` trả `false`, nên phương thức trả `not-a-list`, không gây NPE.

Compiler `javac 24.0.2` với `--release 21 -Xlint:all -Werror` đã chấp nhận toàn bộ ví dụ và trả **exit code 0**. Từ đó có thể khẳng định **cú pháp pattern final của ví dụ này không tạo lint warning** trong cấu hình đã thử, chứ không suy ra mọi mã có pattern đều sạch warning.

## 4. [cast]: cast thừa sau type pattern

Một bước refactor thường chuyển:

```java
if (value instanceof String) {
    String text = (String) value;
    return text;
}
```

thành:

```java
if (value instanceof String text) {
    return text; // Không cần (String) text.
}
```

Đôi khi lập trình viên giữ lại cast dù `text` đã có kiểu `String`. Mẫu đầy đủ để tái hiện warning:

```java
public class RedundantCastDemo {
    static String read(Object value) {
        if (value instanceof String text) {
            return (String) text;
        }
        return "other";
    }
}
```

Biên dịch:

```bash
javac --release 21 -Xlint:cast RedundantCastDemo.java
```

**Diagnostic chính đã kiểm chứng:**

```text
warning: [cast] redundant cast to String
            return (String) text;
                   ^
1 warning
```

Lệnh **không** thất bại theo mặc định: warning này nhắc bỏ phép cast không cần thiết, chứ không có nghĩa cast làm thay đổi kiểu runtime. Sửa đúng là `return text;`.

**Lưu ý:** Không được tự động xóa **mọi cast** trong mã Java. Một cast có thể có vai trò về chọn overload, kiểu của biểu thức, kiểm tra kiểu runtime hoặc generic API. Chỉ xóa khi compiler xác nhận đó là redundant cast hoặc khi phân tích kiểu cho thấy tương đương về hành vi.

## 5. [unchecked] và [rawtypes] quanh legacy generic cast

Pattern matching không thay thế cơ chế type erasure của Java generics. Đoạn mã sau là chương trình hoàn chỉnh dùng để **tái hiện cảnh báo**, không phải phương án xử lý list an toàn.

Lưu **`LegacyWarnings.java`**:

```java
import java.util.List;

public class LegacyWarnings {
    static List<String> uncheckedList(Object value) {
        if (value instanceof List<?> list) {
            return (List<String>) list; // unchecked cast despite the pattern
        }
        return List.of();
    }

    static int rawSize(Object value) {
        if (value instanceof List<?> list) {
            List raw = list; // rawtypes warning
            return raw.size();
        }
        return 0;
    }
}
```

Biên dịch với hai nhóm lint:

```bash
javac --release 21 -Xlint:unchecked,rawtypes LegacyWarnings.java
```

Hai cảnh báo đã kiểm chứng (rút gọn đường dẫn và số dòng):

```text
warning: [unchecked] unchecked cast
  required: List<String>
  found:    List<CAP#1>

warning: [rawtypes] found raw type: List
  missing type arguments for generic class List<E>

2 warnings
```

Giải thích chính xác:

- **`List<?> list`:** compiler chỉ biết đây là một `List` chứa phần tử chưa biết kiểu. Kiểm tra `instanceof List<?>` không thể kiểm tra generic type arguments do type erasure.
- **`(List<String>) list`:** ép kiểu này không có phép chứng minh runtime rằng mọi phần tử là `String`. Với list hỗn hợp, phương thức trả `List<String>` có thể khiến code gọi phía sau gặp `ClassCastException` khi đọc phần tử.
- **`List raw`:** dùng raw type bỏ qua thông tin generic. Nó có thể làm mất các bảo đảm của type system và khiến lỗi kiểu xuất hiện muộn.
- **Warning không tự biến mất khi bọc trong pattern:** `instanceof List<?>` là hợp lệ, nhưng cast cụ thể phía sau vẫn phải được xem xét.

Nếu chỉ cần duyệt list và kiểm tra từng phần tử, cách ở `PatternWarningDemo.checkList` rõ ràng hơn:

```java
static boolean allStrings(Object input) {
    if (!(input instanceof List<?> list)) {
        return false;
    }
    for (Object item : list) {
        if (!(item instanceof String)) {
            return false;
        }
    }
    return true;
}
```

Đây là phương thức minh họa, cần có `import java.util.List;` trong lớp chứa nó. Cách duyệt có thể xác minh nội dung **tại thời điểm kiểm tra**, nhưng không tự khiến một list có thể bị bên ngoài sửa đổi về sau trở thành cấu trúc vĩnh viễn an toàn. Nếu API yêu cầu `List<String>`, cân nhắc tạo bản sao đã được xác thực kiểu vào một list mới để bảo vệ bất biến.

### Có nên dùng @SuppressWarnings("unchecked")?

Chỉ nên cân nhắc khi có **lý do an toàn kiểu cụ thể** được thiết lập bên ngoài compiler, chẳng hạn contract của một API cũ đã được kiểm soát. Hãy giới hạn suppression vào biến/phương thức nhỏ nhất có thể và ghi rõ invariant. Không sử dụng suppression để che một cast chưa có bằng chứng an toàn.

Giải pháp ưu tiên: **sửa kiểu**, dùng `List<?>` khi không cần kiểu phần tử, kiểm tra phần tử rõ ràng hoặc thay API raw bằng generic API.

## 6. [preview]: warning khi dùng tính năng đang preview

Tính năng preview được bật riêng theo **phiên bản JDK**. Ví dụ lịch sử: pattern matching cho `switch` từng preview từ Java 17 đến Java 20, nhưng đã final ở Java 21. Do đó **`case String s -> ...` trên `--release 21` không còn là preview feature**.

Để tái hiện warning preview thật, môi trường kiểm chứng đã dùng **JDK 24.0.2** và một tính năng **còn preview ở Java 24**: *primitive types in patterns, instanceof, and switch* (JEP 488, second preview ở Java 24).

Lưu **`PreviewPrimitiveDemo.java`**:

```java
public class PreviewPrimitiveDemo {
    static String explain(long value) {
        return switch (value) {
            case 0L -> "zero";
            case long n when n > 0 -> "positive";
            case long n -> "negative";
        };
    }
    public static void main(String[] args) {
        System.out.println(explain(0));
        System.out.println(explain(7));
        System.out.println(explain(-2));
    }
}
```

**Chỉ chạy ví dụ preview này với JDK 24** và các cờ tương ứng:

```bash
javac --enable-preview --release 24 -Xlint:preview PreviewPrimitiveDemo.java
java --enable-preview PreviewPrimitiveDemo
```

**Diagnostic đã quan sát (rút gọn):**

```text
warning: [preview] primitive patterns are a preview feature and may be removed in a future release.
3 warnings
```

Trình biên dịch đưa ra ba warning preview trong ví dụ, còn mã vẫn được biên dịch khi không bật `-Werror`. Chạy với `java --enable-preview` trả:

```text
zero
positive
negative
```

Ví dụ này minh họa đúng mục đích `-Xlint:preview`: **cảnh báo về việc sử dụng một ngữ nghĩa chưa final trong bản Java được chọn**, không báo rằng toàn bộ `switch` hoặc mọi record pattern là preview.

### Cấu hình preview nào hợp lệ?

Một số nguyên tắc:

1. Nếu dùng một feature đang preview trên **JDK N**, bật preview với **mức nguồn hiện hành N** mà compiler hỗ trợ, và bật preview trên runtime khi chạy mã sử dụng preview.
2. Không kỳ vọng `javac` của JDK mới hỗ trợ `--enable-preview --release` của một bản cũ tùy ý. Ví dụ `javac 24` với `--enable-preview --release 21` báo lỗi `invalid source release 21 with --enable-preview`.
3. Không dùng preview flag để “nâng” `--release 17` thành Java 21. Record patterns Java 21 không tồn tại trong ngôn ngữ final của Java 17.
4. Khi tính năng đã **final** ở phiên bản đang build, bỏ preview flag nếu không còn sử dụng một preview feature **khác**. Cấu hình không cần thiết có thể gây lỗi tổ hợp options hoặc khiến pipeline khó bảo trì.
5. Trạng thái preview có thể thay đổi ở các bản sau JDK 24. Khi nâng JDK, cần tra JEP và đặc tả **đúng phiên bản**, không sao chép nguyên một lệnh build cũ.

**Không khuyến nghị dùng preview mặc định trong thư viện triển khai rộng** nếu chưa thống nhất toolchain, runtime và chính sách thay đổi cú pháp theo JDK.

## 7. -Werror: tại sao warning làm CI đỏ?

Đối với mã `LegacyWarnings.java` ở mục 5, biên dịch thường có hai warning nhưng vẫn trả exit code 0. Khi thêm `-Werror`:

```bash
javac --release 21 -Xlint:unchecked,rawtypes -Werror LegacyWarnings.java
```

Compiler vẫn báo đúng hai warning rồi kết thúc bằng lỗi:

```text
error: warnings found and -Werror specified
1 error
2 warnings
```

Lần kiểm chứng cho mã này có **exit code 1**. Chức năng của `-Werror` là biến sự hiện diện của warning thành **lý do làm build thất bại**; nó không làm thay đổi bản chất warning `unchecked` hoặc `rawtypes` thành một lỗi kiểu độc lập.

Vì vậy, khi CI đỏ nhưng developer local vẫn build được:

- Xem CI có thêm `-Werror` không.
- So sánh nhóm lint được bật ở hai môi trường.
- Kiểm tra compiler version, `--release` và cấu hình build tool thực tế.
- Đọc **cảnh báo gốc xuất hiện trước** thông báo `warnings found and -Werror specified`; xử lý cảnh báo gốc trước.
- Tránh xử lý bằng cách tắt toàn bộ lint nếu warning phản ánh rủi ro type safety cần sửa.

Một số tổ chức chỉ bật `-Werror` cho module riêng hoặc khi bộ warning hiện tại đã được xử lý để tránh chặn toàn bộ hệ thống vì tồn đọng cũ. Dù chọn chính sách nào, phải hiểu warning nào bị coi là lỗi build.

## 8. Dominated case và non-exhaustive switch là compiler error, không phải lint warning

Trong pattern matching cho `switch` Java 21, hai sai sót phổ biến thường được gọi nhầm là warning:

### Case rộng đứng trước case cụ thể

```java
// Ví dụ cố ý SAI: chỉ minh họa diagnostic, không dùng để chạy.
static String bad(Object value) {
    return switch (value) {
        case CharSequence chars -> "chars";
        case String text -> "text";
        default -> "other";
    };
}
```

Mọi `String` đều là `CharSequence`. Case `String text` ở phía sau bị case đầu che. Với `javac --release 21`, diagnostic được kiểm chứng là:

```text
error: this case label is dominated by a preceding case label
```

Đây là **error ngay cả khi không bật `-Xlint` hoặc `-Werror`**. Sửa bằng cách đưa `case String text` trước `case CharSequence chars`.

### Switch expression thiếu biến thể

Giả sử có model:

```java
sealed interface Item permits Text, Count {}
record Text(String value) implements Item {}
record Count(int value) implements Item {}
```

Phương thức này **cố ý sai**:

```java
static String classify(Item input) {
    return switch (input) {
        case Text(var value) -> "text";
        // Thiếu Count.
    };
}
```

Vì `switch expression` phải **exhaustive**, compiler Java 21 từ chối với thông báo đã được kiểm chứng:

```text
error: the switch expression does not cover all possible input values
```

Sửa bằng cách thêm `case Count(var value) -> ...` với hành vi nghiệp vụ chính xác, thay vì thêm `default` chỉ để che lỗi nếu domain `sealed` cần được bảo trì theo từng subtype.

### Không có warning không có nghĩa không còn bug

Một `switch` trên `sealed` có thể exhaustive đối với các subtype mà **vẫn ném NPE nếu selector là `null`** và không có `case null`. Điều này thuộc về **ngữ nghĩa/runtime**, không mặc nhiên là một lint warning về việc thiếu `null`.

Tương tự, record pattern có thể tách một component tham chiếu `null` rồi code gọi phương thức trên nó và ném NPE. `-Xlint:all` không phải công cụ chứng minh rằng toàn bộ dữ liệu nghiệp vụ đều non-null. Cần guard, bất biến ở constructor và kiểm thử dữ liệu biên.

## 9. Các diagnostic thường gặp trong quá trình refactor

| Diagnostic hoặc triệu chứng | Phân loại | Cách xử lý |
| --- | --- | --- |
| `[cast] redundant cast to String` | Warning khi bật `-Xlint:cast` | Bỏ cast thừa đã được pattern variable đảm bảo kiểu |
| `[unchecked] unchecked cast` | Warning khi bật `-Xlint:unchecked` | Không giả định `List<?>` thành `List<String>`; xác minh phần tử hoặc sửa API |
| `[rawtypes] found raw type` | Warning khi bật `-Xlint:rawtypes` | Tránh `List raw`; dùng generic type phù hợp |
| `[preview] ... may be removed in a future release` | Warning với preview feature đúng JDK | Kiểm tra JDK/cờ preview/JEP; ưu tiên final nếu yêu cầu ổn định |
| `warnings found and -Werror specified` | Error do warning bị nâng thành lỗi build | Sửa warning gốc hoặc điều chỉnh chính sách build có chủ đích |
| `this case label is dominated...` | **Compiler error** | Đưa case cụ thể/guard trước case tổng quát |
| `switch expression does not cover all possible input values` | **Compiler error** | Bổ sung case còn thiếu; kiểm tra `sealed` hierarchy |
| `invalid source release N with --enable-preview` | **Compiler option error** | Dùng đúng mức preview hiện hành hoặc bỏ flag cho final feature |
| `UnsupportedClassVersionError` lúc chạy | **Runtime/linkage error** | Chạy bằng Java hỗ trợ class-file target hoặc build lại đúng release |
| `NullPointerException` trong case body | **Runtime error** | Kiểm tra selector và component null, không dựa vào lint một cách mù quáng |

**Lưu ý:** câu chữ diagnostic có thể khác giữa các bản `javac`. Dùng nhóm lint, số dòng, code liên quan và phiên bản compiler để suy luận, không viết tool parser phụ thuộc tuyệt đối vào một thông điệp tiếng Anh.

## 10. Quy trình điều tra compiler warning từng bước

1. **Ghi nhận đúng toolchain.** Chạy `javac -version`, `java -version`, rồi xem `--release` thực tế của Maven/Gradle/IDE. Máy local có JDK mới không có nghĩa CI đang dùng JDK đó.
2. **Phân loại warning hay error.** Tìm tiền tố `warning:`, `error:`, nhóm trong dấu `[...]` và exit code. Với `-Werror`, thông báo cuối có thể là error dù nguồn gốc là warning.
3. **Tái hiện với lint có mục đích.** Chạy `javac --release 21 -Xlint:cast,unchecked,rawtypes ...` hoặc `-Xlint:all`. Dùng `javac --help-lint` xem các nhóm được compiler hỗ trợ.
4. **Tìm biểu thức gây cảnh báo.** Warning `unchecked` thường ở cast generic, không phải trong type pattern `List<?> list`. Warning `cast` thường ở ép kiểu lại pattern variable đã có kiểu.
5. **Kiểm tra trạng thái feature theo JDK.** Cú pháp đã final ở Java 21 không cần bật preview. Với một feature preview ở phiên bản cụ thể, kiểm tra JEP và cờ của đúng bản.
6. **Sửa type safety trước khi suppression.** Bỏ cast thừa; thay raw list; kiểm tra từng phần tử trước khi chuyển vào một collection có kiểu cụ thể.
7. **Nếu có compiler error, sửa cấu trúc.** Với dominance, sắp case hẹp trước rộng; với exhaustiveness, cập nhật các case theo domain. `-Xlint` không giải quyết các lỗi này.
8. **Biên dịch lại dưới release mục tiêu.** Lệnh `--release 21` giúp phát hiện source sử dụng tính năng vượt quá mức đã chọn.
9. **Chạy test runtime.** Tập trung selector null, record component null, giá trị biên và guard true/false. Cảnh báo sạch không bảo đảm kết quả nghiệp vụ đúng.
10. **Đưa kiểm tra vào CI.** Dùng bộ cờ ổn định và nhất quán giữa local/CI, có chính sách xử lý warning cũ trước khi bật `-Werror` trên mọi module.

### Checklist ngắn trước khi đóng một warning

- Có biết **warning được phát bởi compiler hay plugin khác** (annotation processor, static analyzer, IDE) không?
- Có xác định được **nhóm warning** và dòng source gây ra không?
- Cảnh báo thuộc **pattern final**, **preview**, hay **generic/legacy code xung quanh pattern**?
- Sửa xong, có kiểm tra lại **compiler exit code** và **runtime behavior**?
- Nếu dùng `@SuppressWarnings`, đã có bằng chứng an toàn và phạm vi suppression nhỏ chưa?

Không nên giải quyết bằng cách thêm `@SuppressWarnings("all")` hoặc tắt toàn bộ kiểm tra: điều đó làm mất tín hiệu từ compiler cho các vấn đề mới.

## 11. Tích hợp vào Maven, Gradle và CI

Tùy build tool đang dùng, nên thống nhất các quyết định sau:

- **JDK toolchain** cố định (ví dụ Java 21 cho source dùng record patterns final).
- **Mức phát hành** dùng `--release 21` hoặc tính năng tương đương trong build tool.
- **Lint** được bật với chính sách rõ ràng: `-Xlint:all` hoặc các nhóm `cast,unchecked,rawtypes` theo nhu cầu.
- **`-Werror`** nếu tổ chức muốn không nhận warning mới, nhưng phải chuẩn bị xử lý warning tồn đọng.
- **Preview flags** chỉ khi mã thực sự dùng preview ở đúng JDK, và cấu hình cả các task compile/test/run cần thiết.

Ví dụ ý tưởng cấu hình **Maven Compiler Plugin**: đặt `release` thành `21` và đưa các compiler arguments `-Xlint:all`, `-Werror` vào cấu hình plugin của dự án. Chi tiết cú pháp XML/plugin version cần xem tài liệu của phiên bản plugin mà dự án đang dùng; không nên coi `maven.compiler.release=21` một mình là đã bật lint.

Với **Gradle**, có thể dùng Java toolchain ở `21`, đặt `options.release = 21` cho JavaCompile và thêm `-Xlint:all`/`-Werror` qua compilerArgs. Đảm bảo `Test`/`JavaExec` cũng chạy bằng runtime phù hợp nếu có tính năng preview hoặc lớp cần Java 21.

**Không cần tự động thêm `--enable-preview` chỉ vì module dùng `switch` với pattern** khi nguồn đang biên dịch bằng Java 21: đây đã là tính năng final. Cờ preview thêm không đúng chỗ có thể làm CI fail.

## 12. Kiểm chứng và giới hạn kết luận

Các thử nghiệm thực tế dưới đây đã chạy trên **javac 24.0.2**:

| Thử nghiệm | Tùy chọn | Quan sát |
| --- | --- | --- |
| PatternWarningDemo | `--release 21 -Xlint:all -Werror` | Biên dịch thành công, **0 warning**, chạy 8 dòng stdout chính xác |
| RedundantCastDemo | `--release 21 -Xlint:cast` | **1 warning `[cast]`**, vẫn biên dịch thành công |
| LegacyWarnings | `--release 21 -Xlint:unchecked,rawtypes` | **2 warning** (`[unchecked]`, `[rawtypes]`), exit code 0 |
| LegacyWarnings với Werror | Như trên, thêm `-Werror` | **2 warning + 1 error**, exit code 1 |
| PreviewPrimitiveDemo (JDK 24) | `--enable-preview --release 24 -Xlint:preview` | **3 warning `[preview]`**, vẫn biên dịch, chạy 3 dòng đúng |
| Case String bị CharSequence che | `--release 21` | Compiler **error** `dominated by a preceding case label` |
| Switch sealed thiếu subtype | `--release 21` | Compiler **error** `does not cover all possible input values` |

Vì các phép thử `--release 21` được thực hiện với compiler **JDK 24** (biên dịch theo mức nguồn Java 21), đây **không** phải bằng chứng rằng đã chạy trực tiếp `javac` của bản phân phối JDK 21 riêng. Kết quả đủ xác nhận ví dụ và thông báo của compiler đã sử dụng. Khi dự án nhắm đến runtime Java 21, hãy test thêm bằng JDK 21 của pipeline sản phẩm.

### Khi nào cần thêm static analysis?

`javac -Xlint` là điểm khởi đầu, không thay thế mọi công cụ phân tích tĩnh. Nullness analysis, các công cụ kiểm tra lỗi gọi API hoặc rule style trong IDE có thể phát hiện những tình huống compiler không báo. Hãy ghi rõ công cụ nào tạo ra warning; không đổ mọi diagnostic trong IDE cho `javac`.

Đối với generic collections và dữ liệu nullable, **test và kiểm tra bất biến domain** vẫn là phần không thể thiếu dù compiler không còn warning.

## 13. Bài tập tự luyện

**Bài 1.** Mã sau có cast thừa không?

```java
if (input instanceof String text) {
    System.out.println(((String) text).length());
}
```

*Đáp án:* Có thể bỏ `(String)` vì `text` đã có kiểu `String`. Với `-Xlint:cast`, compiler có thể cảnh báo redundant cast.

**Bài 2.** Vì sao `if (value instanceof List<?> list)` không bảo đảm cast sang `List<String>` an toàn?

*Đáp án:* Java generics dùng type erasure; `instanceof List<?>` kiểm tra kiểu list ở runtime, không kiểm tra kiểu từng phần tử. Cast sang `List<String>` là unchecked nếu compiler không có chứng minh khác.

**Bài 3.** `case CharSequence cs -> ...` đứng trước `case String s -> ...` gây warning hay error?

*Đáp án:* **Compiler error** vì case `String` bị dominated. Không có cách bật/tắt `-Xlint` nào làm thứ tự đó hợp lệ.

**Bài 4.** Trên JDK 24, vì sao `javac --enable-preview --release 21` sai dù record patterns đã final ở Java 21?

*Đáp án:* Preview flag chỉ áp dụng mức source preview mà compiler hiện tại cho phép. Nếu source chỉ dùng feature final Java 21, phải bỏ `--enable-preview` và dùng `--release 21`.

**Bài 5.** CI có `-Werror` và xuất hiện `warning: [unchecked]`. Nên sửa thế nào?

*Đáp án:* Xác định cast generic, hiểu bất biến của dữ liệu, sửa API hoặc kiểm tra phần tử trước khi tạo collection đúng kiểu. Chỉ suppression có phạm vi hẹp nếu chứng minh được an toàn; không tắt toàn bộ lint một cách vô cớ.

**Bài 6.** Chương trình Java 21 sử dụng record patterns đã chạy qua `-Xlint:all -Werror`. Có thể kết luận nó không còn lỗi với dữ liệu `null`?

*Đáp án:* Không. Cú pháp/kiểu có thể hợp lệ nhưng record component nullable bị dereference hoặc `switch` không có `case null` vẫn có thể gây NPE. Cần test những tình huống đó.

**Bài 7.** Có nên xem `fallthrough` là warning đặc trưng của pattern matching `switch` với các nhánh `->` không?

*Đáp án:* Không. `-Xlint:fallthrough` chủ yếu dành cho kiểu switch statement có nhãn colon cho phép chuyển từ nhóm câu lệnh này sang nhóm khác. Pattern switch dạng arrow `->` không dùng cơ chế fall-through truyền thống đó.

## 14. Tài liệu tham khảo

- [Oracle javac tool guide – JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): các tùy chọn `--release`, `-Xlint`, `-Werror`, `--enable-preview`.
- [JEP 394 – Pattern Matching for instanceof](https://openjdk.org/jeps/394): type pattern đã final Java 16.
- [JEP 440 – Record Patterns](https://openjdk.org/jeps/440): record patterns đã final Java 21.
- [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441): pattern switch đã final Java 21.
- [JEP 488 – Primitive Types in Patterns, instanceof, and switch (Second Preview)](https://openjdk.org/jeps/488): ví dụ preview ở Java 24.
- [JEP 12 – Preview Features](https://openjdk.org/jeps/12): cơ chế preview và yêu cầu opt-in.
- [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): case pattern, guard, exhaustiveness, null.
- [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): deconstruction và component patterns.
- [JLS Java 21 – `14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): quy tắc switch, case và dominance.
