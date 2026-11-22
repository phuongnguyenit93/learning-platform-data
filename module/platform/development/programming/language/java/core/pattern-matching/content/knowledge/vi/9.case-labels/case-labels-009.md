# Giới hạn của pattern trong case (Java 21)

## 1. Vì sao cần hiểu giới hạn của case pattern?

Pattern matching cho `switch` giúp Java xử lý nhiều dạng đối tượng một cách ngắn gọn: `case String text` có thể kiểm tra kiểu và tạo biến `text`; `case Point(int x, int y)` có thể tách các thành phần của một `record`. Tuy nhiên, **không phải bất kỳ biểu thức, kiểu hoặc điều kiện nào cũng được đặt sau `case`**. Trình biên dịch kiểm tra cú pháp, tính tương thích kiểu, khả năng phân biệt các nhánh và tính đầy đủ của `switch`.

Khi không hiểu các giới hạn đó, những đoạn mã tưởng hợp lý như `case List<String> items`, `case String s, Integer n`, `case String s when s.length()` hoặc đặt `case Object o` trước `case String s` có thể không biên dịch. Một nhánh có guard còn có thể không được chọn dù kiểu đã khớp; `null` và `default` cũng có quy tắc riêng.

**Mục tiêu của bài:** Nhận ra các dạng nhãn `case` mà Java 21 hỗ trợ, giới hạn của type pattern/record pattern, guard và biến mẫu; hiểu các lỗi dominance, trùng nhãn, `null`, fall-through và exhaustiveness; viết được một `switch` dễ đọc và kiểm thử được.

Phạm vi là **Java 21 với các tính năng đã chính thức**, không mặc định dùng cú pháp preview hoặc mở rộng ở phiên bản JDK mới hơn. `switch expression` vốn có từ Java 14, `instanceof` pattern chính thức từ Java 16, còn pattern matching cho `switch` và record pattern chính thức từ Java 21.

## 2. Phân biệt case constant, case pattern, null và default

Trong Java 21, một nhãn `case` có thể là danh sách hằng, một literal `null` hoặc một pattern. `default` là nhãn dự phòng, **không phải pattern**.

| Loại nhãn | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Hằng số | `case 0, 1 -> ...` (selector `Integer` hoặc `int` phù hợp) | Chọn nhánh khi giá trị bằng một trong các hằng hợp lệ |
| Type pattern | `case String text -> ...` | Kiểm tra đối tượng thuộc `String` và ràng buộc biến `text` |
| Type pattern có guard | `case String text when text.isBlank() -> ...` | Sau khi khớp kiểu, kiểm tra thêm điều kiện boolean |
| Record pattern | `case Point(int x, int y) -> ...` | Đối sánh `record Point` và rút hai component |
| Null label | `case null -> ...` | Nhận selector bằng `null` |
| Default label | `default -> ...` | Nhận các đầu vào còn lại không-null trong ngữ cảnh thông thường |
| Null gộp default | `case null, default -> ...` | Gộp nhánh null với nhánh dự phòng, dùng đúng một lần và ở cuối switch |

Không thể viết trực tiếp điều kiện tùy ý ở vị trí pattern:

```java
// KHÔNG PHẢI case pattern hợp lệ trong Java 21:
case value > 0 -> "positive";
case text.startsWith("A") -> "starts A";
```

Đây là các **mảnh cú pháp cố ý sai**. Khi muốn kiểm tra thuộc tính của đối tượng đã khớp kiểu, viết **pattern + `when`**:

```java
// Hai case minh họa, giả định selector có kiểu Object:
case Integer n when n > 0 -> "positive";
case String text when text.startsWith("A") -> "starts A";
```

`when` chỉ hợp lệ khi gắn với **case pattern**. Nó không phải cách thêm điều kiện cho mọi case constant, ví dụ `case 1 when condition` không phải dạng nhãn Java 21 hợp lệ.

### Một switch có hằng số và pattern

Ví dụ dưới đây là **phương thức Java 21** dùng selector `Integer`:

```java
static String classify(Integer value) {
    return switch (value) {
        case 0, 1 -> "small";
        case Integer n when n < 0 -> "negative";
        case Integer n -> "other:" + n;
    };
}
```

Với `0`, `-3` và `8`, kết quả lần lượt là `small`, `negative` và `other:8`. Nếu `value` bằng `null`, biểu thức này không tự đi vào pattern `Integer`; nó ném `NullPointerException` vì không có `case null`. Trong chương trình thực tế, chọn rõ là cho phép hay từ chối null.

Hằng số và pattern **không hoàn toàn thay thế cho nhau**: chẳng hạn với selector có kiểu tĩnh `Object`, không thể tùy ý đặt `case 42` như hằng số nguyên; trường hợp đối sánh số nguyên có thể diễn đạt bằng `case Integer n when n == 42`.

## 3. Giới hạn về phiên bản Java và kiểu selector

### Cú pháp case pattern là tính năng Java 21

Với Java 17, đoạn sau **không phải cú pháp switch pattern chính thức**:

```java
return switch (value) {
    case String s -> s;
    default -> "other";
};
```

Ví dụ là mảnh biểu thức trong phương thức, cần **Java 21+** để dùng ổn định. Java 17 vẫn có `switch expression` trên hằng/enum và `instanceof String s`, nhưng không thể biên dịch pattern switch Java 21 với `javac --release 17`.

### Selector cũng có giới hạn

Trong Java 21, kiểu của biểu thức đưa vào `switch` phải là `char`, `byte`, `short`, `int` hoặc **một kiểu tham chiếu hợp lệ**. Các selector có **kiểu nguyên thủy** `boolean`, `long`, `float`, `double` không được hỗ trợ trong `switch` Java 21:

```java
long quantity = 5L;
// SAI với Java 21: selector là primitive long.
switch (quantity) {
    case 5L -> System.out.println("five");
    default -> System.out.println("other");
}
```

Mã trên cố ý không biên dịch với Java 21. Đừng nhầm với một đối tượng `Long` lưu trong `Object`: switch theo kiểu tham chiếu có thể xử lý nó bằng type pattern phù hợp.

Một pattern cũng phải **áp dụng được cho kiểu tĩnh của selector**. Ví dụ không thể đặt `case Integer n` trong `switch` có selector kiểu tĩnh `String` rồi kỳ vọng thực thi một nhánh không thể khớp. Đổi selector thành kiểu tổng quát hơn nếu đầu vào hợp đồng thực sự có thể chứa nhiều loại đối tượng; không mở kiểu chỉ để né lỗi biên dịch.

## 4. Giới hạn của type pattern ở vị trí case

Type pattern cơ bản có dạng `Type variableName`, ví dụ:

```java
case String text -> "length=" + text.length();
case Number number -> "number=" + number;
```

Đây là hai **nhãn case minh họa**, không phải switch đầy đủ. Trong Java 21:

- **Top-level type pattern dùng kiểu tham chiếu:** `case Integer n` hợp lệ trong ngữ cảnh phù hợp; `case int n` ở cấp ngoài không phải type pattern hợp lệ của Java 21. Các bản Java sau có thể phát triển riêng về primitive patterns, nên cần kiểm tra đúng `--release`.
- **Không dùng `var` như top-level type pattern:** `case var x -> ...` không phải cú pháp Java 21 tương đương `case Object x`. `var` có thể dùng trong **component pattern** của record như `case Point(var x, var y)`.
- **Pattern variable cần tên Java hợp lệ:** `case String 123abc` sai; các tên trùng với biến địa phương đang có hiệu lực ở vị trí xung đột cũng sai.
- **Không viết biểu thức gán trong khai báo:** `case String s = "x"` sai; biến `s` được ràng buộc khi pattern khớp.
- **Pattern phải tương thích với selector:** trình biên dịch kiểm tra các tổ hợp kiểu có thể kiểm tra được, không cho phép một nhánh hoàn toàn vô nghĩa do kiểu tĩnh bất khả tương thích.

### Giới hạn generic: type erasure

Giả sử selector có kiểu `Object`:

```java
// Hợp lệ ở Java 21:
case java.util.List<?> elements -> "size=" + elements.size();
```

Nhưng:

```java
// CỐ Ý SAI với Object selector:
case java.util.List<String> elements -> "size=" + elements.size();
```

`List<String>` không phải kiểu có thể kiểm tra đầy đủ bằng runtime type test trong ngữ cảnh này; Java xóa tham số kiểu (`type erasure`) khi chạy. `List<?>` kiểm tra được đối tượng có là một `List` hay không, **không chứng minh mọi phần tử là `String`**.

Nếu cần xử lý phần tử, hãy kiểm tra từng phần tử bằng `instanceof String text` hoặc buộc đầu vào tuân thủ một hợp đồng dữ liệu có kiểu rõ ràng. Không dùng ép kiểu unchecked để che cảnh báo rồi coi đó là kết quả pattern matching an toàn.

## 5. Record pattern chỉ tách các component của record phù hợp

Trong Java 21, record pattern cho phép đối sánh đối tượng record và rút các thành phần theo khai báo:

```java
record Point(int x, int y) {}

// Một case bên trong switch(Object value):
case Point(int x, int y) -> "(" + x + "," + y + ")";
```

`Point` có đúng hai component `int x` và `int y`, nên pattern phải có **đúng hai component pattern, theo đúng thứ tự**. Java kiểm tra kiểu phù hợp của từng component.

Ví dụ cú pháp sai:

```java
// CỐ Ý SAI: Point có hai component, thiếu một thành phần.
case Point(int x) -> "x=" + x;

// CỐ Ý SAI: String không phải record được khai báo component x, y.
case String(int x, int y) -> "wrong";
```

Trong component của record pattern, `var` có thể được dùng để suy luận kiểu:

```java
case Point(var x, var y) -> x + y;
```

Hai biến `x`, `y` được suy luận là `int`. Đây là **cú pháp component pattern**, không phải bằng chứng rằng `case var value` hợp lệ ở cấp ngoài.

Một record pattern có thể lồng record pattern khác nếu các component thực sự có kiểu tương ứng:

```java
record Segment(Point start, Point end) {}

// Minh họa bên trong switch(Object value):
case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
        "from " + x1 + "," + y1 + " to " + x2 + "," + y2;
```

Đây là mã minh họa, cần khai báo `Point` và `Segment` trong phạm vi hợp lệ, không phải một tệp chạy độc lập. Record pattern **không tự tách các trường private của một lớp thông thường**, không phải regex và cũng không bỏ qua các quy tắc null của dữ liệu lồng nhau.

Nếu component tham chiếu có thể là `null`, kiểm tra quy tắc khớp của **component pattern cụ thể** và hợp đồng dữ liệu; đừng khẳng định mọi pattern lồng nhau tự loại bỏ null. Lối thiết kế dễ đọc là dùng một nhánh kiểu record (`case Segment segment`) rồi kiểm tra accessor khi cần phân biệt null bên trong.

## 6. Giới hạn của nhãn case có nhiều phần tử

### Có thể nhóm nhiều hằng số cùng một nhánh

Với selector `Integer` hoặc `int` hợp lệ:

```java
case 0, 1 -> "small";
```

Một nhãn có thể mang **danh sách hằng số**; các hằng phải tương thích selector và không được trùng giá trị với nhãn khác trong cùng switch.

### Không viết nhiều pattern có biến ràng buộc vào cùng một nhãn

Cú pháp sau **không hợp lệ trong Java 21**:

```java
// CỐ Ý SAI (Java 21):
case String s, Integer n -> "text or integer";
```

Nếu selector là chuỗi thì `s` được gán còn `n` không; nếu selector là số nguyên thì ngược lại. Không có cách an toàn để một thân nhánh tham chiếu hai biến đó mà không biết pattern nào khớp. Ở Java 21, một nhãn `case` với pattern có cấu trúc như trên cần được viết thành **các nhãn riêng**:

```java
case String s -> "text: " + s;
case Integer n -> "integer: " + n;
```

Các mảnh này là nhãn minh họa. Nếu chỉ muốn kết quả chung và không cần dùng biến, có thể gom logic thành phương thức riêng được gọi từ từng nhánh.

Cũng tránh nhóm nhiều nhãn kiểu dấu hai chấm (`:`) trước thân nhánh có dùng pattern variable: luồng điều khiển có thể tới thân đó từ nhãn khác mà biến chưa được ràng buộc. Quy tắc Java 21 cấm các trường hợp gây nhập nhằng này.

Ví dụ cố ý sai do fall-through trong `switch statement`:

```java
// CỐ Ý SAI: có thể rơi từ nhánh String sang nhánh Integer.
switch (value) {
    case String s:
        System.out.println(s); // Không break.
    case Integer n:
        System.out.println(n);
        break;
    default:
        break;
}
```

Dùng nhánh `->` độc lập để tránh rơi xuyên, hoặc tổ chức statement group sao cho không có đường đi khiến pattern variable chưa được khởi tạo. Trong bài nhập môn, ưu tiên `->`.

## 7. Giới hạn của when guard

`when` bổ sung điều kiện boolean **sau khi pattern đã khớp**:

```java
case String text when text.isBlank() -> "blank";
case String text -> "text: " + text;
```

Ở case đầu, Java xác nhận selector là `String` và đã gán `text` trước khi đánh giá `text.isBlank()`. Guard sai thì nhánh đó không áp dụng, Java tiếp tục tìm case khác theo thứ tự.

Một guard phải có kiểu `boolean` hoặc `Boolean` (nếu `Boolean` là null và bị unbox, có thể ném `NullPointerException`). Những điều kiện không trả boolean là sai cú pháp/ngữ nghĩa:

```java
// CỐ Ý SAI: length() trả int, không phải boolean.
case String text when text.length() -> "wrong";
```

Sửa thành `text.length() > 0` hoặc điều kiện boolean rõ ràng. Với Java 21, guard là `when`, không phải `if`. Các guard hằng `false` bị từ chối; guard hằng `true` có thể khiến nhánh được xem như không có guard về dominance và ít có ích.

Guard cũng có giới hạn đối với biến địa phương/đối số bên ngoài: các biến được tham chiếu (mà guard không tự khai báo) phải tuân thủ yêu cầu `final` hoặc effectively final theo JLS. Đừng viết guard có thao tác gán vào biến ngoài hoặc dựa vào tác dụng phụ; như vậy vừa dễ vi phạm quy tắc, vừa khiến lựa chọn case khó đoán.

### Guard không thay thế một nhánh bao quát

```java
// Giả định selector có thể là bất kỳ Integer.
case Integer n when n > 0 -> "positive";
```

Nhánh này chỉ khớp số nguyên dương; giá trị `0`, âm hoặc kiểu khác cần một nhánh xử lý phù hợp. Thêm `case Integer n -> ...` phía sau khi muốn bao quát phần còn lại của chính kiểu `Integer`.

**Không để guard dereference dữ liệu nullable mà chưa kiểm tra.** `case Box b when b.value().isBlank()` không an toàn nếu `Box.value()` có thể `null`, dù bản thân `b` đã khớp kiểu.

## 8. Dominance: giới hạn về thứ tự các nhánh

Một case đứng trước **dominate** case đứng sau khi compiler xác định case trước có thể nhận mọi giá trị mà case sau nhận. Điều đó gây **lỗi biên dịch** vì nhánh sau không thể được chọn theo logic khớp mẫu.

### Mẫu tổng quát đặt trước mẫu cụ thể

```java
// CỐ Ý SAI:
return switch (value) {
    case CharSequence sequence -> "sequence";
    case String text -> "string"; // Không tới được.
    default -> "other";
};
```

`String` là kiểu con của `CharSequence`, nên mọi `String` đã khớp nhánh đầu. Cách sửa:

```java
return switch (value) {
    case String text -> "string";
    case CharSequence sequence -> "sequence";
    default -> "other";
};
```

Đây là các mảnh biểu thức trong phương thức có selector kiểu phù hợp (chẳng hạn `Object value`). Thêm `case null` khi hợp đồng nhận null.

### Nhánh cùng kiểu có guard đặt sau nhánh không guard

```java
// CỐ Ý SAI:
return switch (value) {
    case String text -> "any";
    case String text when text.isBlank() -> "blank"; // Bị che khuất.
    default -> "other";
};
```

Sửa bằng cách đặt trường hợp đặc biệt trước:

```java
case String text when text.isBlank() -> "blank";
case String text -> "any";
```

### Pattern có thể che cả hằng số

Trong `switch` với selector kiểu `Integer`, `case Integer n` không guard đứng trước `case 42` thì `case 42` bị che khuất. Nên sắp xếp **hằng số đặc biệt → pattern có guard → pattern không guard** khi cả ba loại phù hợp.

Compiler không giải bài toán suy luận mọi điều kiện logic của guard tùy ý. Vì vậy, dù hai guard về mặt toán học có thể chồng lấn, bạn vẫn phải thiết kế thứ tự theo mục đích nghiệp vụ và viết kiểm thử.

### Nhánh unconditional và default

Nếu selector kiểu `Object`, một nhánh `case Object o` không guard là **unconditional pattern** đối với kiểu selector; nó có vai trò bao quát và không thể đồng thời thêm một `default` phía sau để đóng vai trò dự phòng tương đương. Hãy giữ đúng một cách xử lý phần còn lại, cùng chính sách riêng cho null khi cần.

## 9. Null, default và nhãn trùng lặp

`case null` **không phải pattern**; nó là cách biểu diễn rõ đầu vào null cho switch tham chiếu. Trong Java 21, với switch pattern thông thường, `default` không tự nhận `null`: nếu không có case xử lý null thích hợp thì selector null dẫn tới `NullPointerException`.

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text";
        default -> "other";
    };
}
```

Trong một số bài toán, null và các giá trị còn lại có cùng ý nghĩa; Java 21 cho phép nhãn kết hợp:

```java
static String describeCombined(Object value) {
    return switch (value) {
        case String text -> "text";
        case null, default -> "other-or-missing";
    };
}
```

Nhãn `case null, default` phải là **nhãn cuối**; không được đặt các nhãn khác phía sau. Nó chỉ nên dùng khi muốn gộp hai loại tình huống một cách có chủ đích.

Các giới hạn cần nhớ:

- Một switch không được có hai nhãn `null` hoặc hai nhãn `default`.
- Không được lặp lại hằng số `case` với cùng giá trị.
- `default` đứng trước case pattern hoặc case null là lỗi biên dịch trong Java 21.
- `case null, default` phải ở cuối và không thể đứng cùng một `default` khác.
- Một pattern được compiler đánh giá là unconditional cho selector có thể đóng vai trò nhánh bao quát, vì vậy việc thêm `default` có thể bị coi là trùng phạm vi.

Đừng dùng `default` để giấu lỗi cấu trúc: với một hệ kiểu `sealed` cần nhận biết khi thêm kiểu con, liệt kê đủ pattern cụ thể thường mang lại ích lợi từ kiểm tra exhaustiveness.

## 10. Một ví dụ hoàn chỉnh: case hợp lệ và thứ tự đúng

Tạo tệp `CasePatternLimits21.java`:

```java
import java.util.List;

public class CasePatternLimits21 {

    record Point(int x, int y) {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "null";

            case String text when text.isBlank() ->
                    "blank";

            case String text ->
                    "text=" + text.strip();

            case Point(int x, int y) when x == 0 && y == 0 ->
                    "origin";

            case Point(int x, int y) ->
                    "point=" + x + "," + y;

            case List<?> list ->
                    "list=" + list.size();

            case Integer n ->
                    "int=" + n;

            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("   "));
        System.out.println(describe(" Java "));
        System.out.println(describe(new Point(0, 0)));
        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe(List.of("a", "b")));
        System.out.println(describe(7));
        System.out.println(describe(1.5));
    }
}
```

Biên dịch/chạy với JDK 21 trở lên:

```bash
javac -encoding UTF-8 --release 21 CasePatternLimits21.java
java CasePatternLimits21
```

Kết quả:

```text
null
blank
text=Java
origin
point=2,3
list=2
int=7
other
```

**Đọc theo các giới hạn đã học:**

- `case null` là nhánh rõ nghĩa cho null, không phụ thuộc `default`.
- Case `String` có guard đặt trước case `String` tổng quát; biến `text` chỉ được dùng ở nhánh khớp.
- Record pattern `Point(int x, int y)` có đúng hai component; case gốc tọa độ `(0,0)` đặt trước case `Point` bao quát còn lại.
- `List<?>` là kiểu kiểm tra được khi selector là `Object`; nó không giả định kiểu cụ thể của phần tử.
- `Integer` khác `Double`, nên `7` đi vào `int=7` còn `1.5` vào `default`.
- `switch expression` có `default` để bao quát những loại đối tượng khác khi selector có kiểu `Object`.

Các lỗi dominance và sai kiểu được minh họa ở phần trước là **bài thử lỗi riêng**; chúng không nằm trong chương trình chạy đầy đủ này.

## 11. Exhaustiveness và giới hạn của case trên sealed hierarchy

`switch expression` phải có kết quả hoặc ném lỗi ở mọi trường hợp hợp lệ. Với selector là `Object`, `default` thường giúp bao quát các kiểu khác. Với `sealed interface`, compiler biết những kiểu con trực tiếp được phép, nên có thể kiểm tra tính đầy đủ của các case pattern **mà không cần `default`**.

Tạo tệp `SealedCaseCoverage21.java`:

```java
public class SealedCaseCoverage21 {

    sealed interface Result permits Success, Failure {}

    record Success(int value) implements Result {}

    record Failure(String reason) implements Result {}

    static String status(Result result) {
        return switch (result) {
            case null -> "missing";

            case Success(int value) when value < 0 ->
                    "invalid-success";

            case Success(int value) ->
                    "success:" + value;

            case Failure(String reason) ->
                    "failure:" + reason;
        };
    }

    public static void main(String[] args) {
        System.out.println(status(null));
        System.out.println(status(new Success(-1)));
        System.out.println(status(new Success(5)));
        System.out.println(status(new Failure("timeout")));
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 --release 21 SealedCaseCoverage21.java
java SealedCaseCoverage21
```

Kết quả:

```text
missing
invalid-success
success:5
failure:timeout
```

**Vì sao không cần `default`?** `Result` là kiểu `sealed` có hai biến thể `Success` và `Failure`. Có case không guard cho mỗi biến thể; guard ở `Success` chỉ ưu tiên trường hợp giá trị âm, còn case `Success` không guard xử lý phần còn lại. `case null` chủ động giải quyết tham chiếu null. Nếu chỉ giữ `case Success(int value) when value < 0` mà xóa case `Success(int value)` không guard, switch còn thiếu các `Success` có giá trị không âm.

Thử thêm `record Pending() implements Result {}` và bổ sung vào `permits` mà chưa bổ sung case: compiler sẽ chỉ ra `switch expression` chưa exhaustive. Đó là tín hiệu để xử lý biến thể mới. Khi hệ phân cấp thật sự mở, `default` hoặc một nhánh bao quát khác là cần thiết.

Với `switch statement` dùng pattern trong Java 21, nhiều trường hợp được xem là **enhanced switch** và cũng phải exhaustive; không suy luận rằng chỉ `switch expression` mới cần xét tính đầy đủ.

## 12. Bảng lỗi điển hình và cách sửa

| Mã hoặc ý tưởng | Vấn đề | Hướng sửa |
| --- | --- | --- |
| `case int n` ở cấp ngoài (Java 21) | Primitive type pattern cấp ngoài chưa hỗ trợ | Dùng `case Integer n` khi selector phù hợp |
| `case var x` | `var` không phải top-level type pattern Java 21 | Ghi kiểu tham chiếu, ví dụ `case String x` |
| `case List<String> xs` với selector `Object` | Không kiểm tra được tham số generic khi chạy | `case List<?> xs` và kiểm tra phần tử khi cần |
| `case Point(int x)` cho `record Point(int x, int y)` | Sai số lượng component | Cung cấp đúng hai pattern |
| `case String s, Integer n` | Nhiều pattern có biến ràng buộc trong một nhãn | Tách thành hai case |
| `case 1 when condition` | Guard phải gắn với case pattern | Dùng hằng riêng hoặc `Integer n when ...` |
| `case String s when s.length()` | Guard trả `int` | Dùng `s.length() > 0` |
| `case String s when false` | Guard hằng `false` bị từ chối | Bỏ nhánh không thể xảy ra, viết điều kiện thực |
| `case CharSequence cs` trước `case String s` | Case sau bị dominance | Đặt case `String` trước |
| `case String s` trước `case String s when ...` | Guard phía sau bị che khuất | Đặt guard trước case tổng quát |
| `case Integer n` trước `case 42` với selector `Integer` | Pattern không guard đã bao hằng 42 | Đặt hằng đặc biệt trước pattern |
| `case null` lặp lại | Trùng nhãn null | Chỉ một nhãn null |
| `default` rồi tiếp tục `case String s` | Default đứng trước pattern | Chuyển default xuống cuối |
| `case null, default` rồi có case khác | Nhãn tổng hợp phải ở cuối | Đưa về cuối hoặc tách nhánh có chủ đích |
| Selector primitive `long` hoặc `double` | Java 21 không hỗ trợ selector kiểu đó | Xem lại kiểu đầu vào; với tham chiếu phù hợp dùng type pattern |
| Dùng biến mẫu ở case khác | Biến chỉ có hiệu lực trong phạm vi case/guard phù hợp | Dùng tên biến của chính pattern đang khớp |
| Guard cho phép null component rồi gọi phương thức | Có thể ném NPE | Kiểm tra component trước hoặc giữ bất biến không-null |

Đa số lỗi được phát hiện **khi biên dịch**, nhưng guard gây ngoại lệ hoặc hợp đồng null chưa rõ có thể chỉ xuất hiện khi chạy. Vì vậy phải làm cả kiểm tra biên dịch và kiểm thử đường đi.

## 13. Quy trình thiết kế case pattern an toàn

Một quy trình ngắn trước khi viết `switch` trong Java 21:

1. **Xác định kiểu selector** và những giá trị thực sự có thể tới, kể cả null. Đừng thay kiểu tĩnh thành `Object` nếu miền dữ liệu có thể được mô hình hóa chính xác hơn.
2. **Liệt kê kiểu nhãn cần có:** case constant cho giá trị cố định hợp lệ, type pattern cho phân nhánh kiểu, record pattern khi dữ liệu là record, `case null` cho null theo hợp đồng.
3. **Kiểm tra khả năng áp dụng:** kiểu pattern tương thích selector, generic có thể kiểm tra, record có đúng số lượng/kiểu component.
4. **Tách nhánh có biến ràng buộc:** không gộp nhiều pattern có biến vào một case của Java 21. Với `switch` nhóm dấu hai chấm, tránh fall-through qua nhánh cần pattern variable.
5. **Xếp từ cụ thể tới tổng quát:** hằng đặc biệt và guard trước type pattern bao quát; tránh dominance.
6. **Quyết định null và default:** để chúng có ý nghĩa đúng, không thêm default tùy tiện khi đã có case unconditional hoặc khi muốn compiler kiểm tra đầy đủ trên sealed hierarchy.
7. **Kiểm tra tính đầy đủ:** mỗi `switch expression` và enhanced switch statement cần có các trường hợp bao quát hợp lệ.
8. **Chạy ca kiểm thử:** giá trị null, case hằng, guard đúng/sai, các kiểu con, đầu vào chưa hỗ trợ và lỗi cú pháp có chủ đích.

Khi refactor, giữ một nhánh ngắn và dễ đọc; những phép tính dài hoặc có tác dụng phụ nên đưa vào phương thức có tên rõ ràng. Không biến mọi bài toán thành một `switch` lớn chỉ vì Java hỗ trợ pattern.

## 14. Bài tập thực hành

**Bài 1 — Phân biệt nhãn:** Cho các dòng `case 0, 1`, `case Integer n`, `case Point(int x, int y)`, `case null`, `default`. Chỉ ra đâu là hằng, đâu là pattern, đâu là nhãn đặc biệt; mô tả kiểu selector cần có.

**Bài 2 — Sửa pattern không hợp lệ:** Viết lại `case var x`, `case List<String> xs` (selector Object), `case Point(int x)` (Point có hai component) thành cú pháp phù hợp. Nêu giới hạn ngôn ngữ dẫn tới từng lỗi.

**Bài 3 — Thứ tự và dominance:** Tạo `switch` với `case CharSequence cs` trước `case String text` và quan sát lỗi. Sau đó thử đặt `case String s` trước nhánh `String s when s.isBlank()`, rồi sửa. Giải thích không chỉ thứ tự mà còn quan hệ bao hàm giữa các mẫu.

**Bài 4 — Null/default:** Dùng Java 21 viết hai phiên bản: một có `case null` riêng và `default`, một dùng `case null, default` ở cuối. Kiểm thử với `null`, `String` và `Integer`, so sánh ý nghĩa hai cách.

**Bài 5 — Nhãn gộp:** Với selector kiểu `Integer`, viết `case 0, 1`, `case Integer n when n < 0` và `case Integer n`. Sau đó thử nhóm `case String s, Integer n` với selector Object để xem lỗi cú pháp/khởi tạo biến; tách thành hai case.

**Bài 6 — Tính đầy đủ:** Chạy `SealedCaseCoverage21`, xóa case `Success` không guard rồi thử biên dịch. Thêm một kiểu con `Pending` vào `Result` và xác định case còn thiếu.

**Bài 7 — Giới hạn selector:** Viết `switch` với selector `long` nguyên thủy trên `--release 21` để quan sát lỗi, sau đó dùng `Object value = 5L` và `case Long n` để phân nhánh kiểu tham chiếu. Giải thích khác biệt giữa selector nguyên thủy và giá trị đóng gói trong `Object`.

### Câu hỏi tự đánh giá

- Tại sao `case 1, 2` có thể hợp lệ nhưng `case String s, Integer n` lại không được phép trong Java 21?
- Phần nào của `case String s when s.isBlank()` tạo ra biến `s`? Khi nào guard được đánh giá?
- Vì sao `case List<?> xs` không chứng minh mỗi phần tử là `String`?
- Khi nào một case pattern che khuất case constant hoặc một pattern khác?
- `case null`, `default` và `case null, default` khác nhau thế nào?
- Vì sao một tập case chỉ gồm các nhánh có guard thường không đủ để chứng minh exhaustiveness?
- Khi nào `sealed` giúp bỏ `default` một cách có cơ sở?
- Vì sao pattern variable trong `switch statement` dạng dấu hai chấm khiến fall-through bị hạn chế?

Khi có thể trả lời và giải thích các ví dụ không biên dịch, bạn đã nắm những giới hạn quan trọng để thiết kế **case label** chính xác trong Java 21.

## 15. Tài liệu chính thức

- [Java Language Specification 21 — `14.11 Switch Statement, Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): các dạng case label, thứ tự, compatibility, dominance và exhaustiveness.
- [Java Language Specification 21 — `14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type pattern, record pattern, khả năng áp dụng và quy tắc khớp.
- [Java Language Specification 21 — `15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): cách `switch` là biểu thức tạo giá trị.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): ví dụ thực tế về dominance, guard và null.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): thiết kế tính năng chính thức Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record pattern và component.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): biểu thức `switch`, arrow và `yield`.

Chỉ dùng cú pháp phù hợp với phiên bản Java của dự án, ví dụ `javac --release 21` khi cần pattern switch chính thức, và coi mọi lỗi biên dịch ở ví dụ “cố ý sai” là bài học về ràng buộc của ngôn ngữ.
