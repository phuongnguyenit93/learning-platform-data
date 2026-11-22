# Đọc cảnh báo và lỗi pattern của javac (Java 21)

## 1. Mục tiêu: hiểu thông báo compiler, sửa đúng nguyên nhân

Khi học **pattern matching** trong Java, nhiều lỗi được phát hiện ngay lúc biên dịch, trước khi chương trình chạy. Ví dụ một `case` bị nhánh tổng quát che khuất, một `switch` chưa bao phủ mọi kiểu, biến pattern được dùng ngoài phạm vi, hoặc record pattern có sai số component. Những lỗi này liên quan trực tiếp đến cách trình biên dịch Java kiểm tra **kiểu**, **luồng điều khiển** và **khả năng khớp của pattern**.

Bài học hướng dẫn đọc chẩn đoán của **`javac`**, phân biệt `error`, `warning` và `note`, hiểu nguyên nhân thường gặp, rồi chỉnh code có kiểm chứng. Trọng tâm là **type patterns**, **record patterns**, **pattern matching cho `switch`** và điều kiện `when`.

Sau khi học, bạn có thể:
- Đọc vị trí file, dòng, ký hiệu `^` và thông điệp của `javac`.
- Dùng `--release 21`, `-Xlint:all`, `-Xlint:unchecked` và `-Xdiags:verbose` đúng mục đích.
- Phân biệt **lỗi bắt buộc phải sửa** với **cảnh báo cần đánh giá rủi ro**.
- Sửa các lỗi pattern phổ biến: *dominated case*, *non-exhaustive switch*, *cannot find symbol*, sai record arity, kiểu generic không reifiable và guard không phải boolean.
- Kiểm thử sau mỗi lần sửa thay vì chỉ làm im thông báo.

**Phạm vi phiên bản:** `instanceof` với type pattern là tính năng chuẩn từ Java 16. **Record patterns (JEP 440)** và **pattern matching cho `switch` (JEP 441)** là tính năng chuẩn từ **Java 21**. Để chạy các ví dụ chính thức trong bài, dùng **JDK 21 trở lên** với `javac --release 21`. Không cần `--enable-preview` cho những tính năng đã ổn định trong Java 21.

## 2. Cách đọc một diagnostic của javac

Ví dụ một chẩn đoán có dạng:

```text
BadOrder.java:8: error: this case label is dominated by a preceding case label
            case String s -> "string";
                 ^
1 error
```

Đây là **dạng trình bày minh họa** (tên file, số dòng, khoảng trắng và vị trí dấu `^` phụ thuộc mã cụ thể và phiên bản trình biên dịch). Mỗi phần mang ý nghĩa:

| Phần | Ý nghĩa | Việc cần làm |
| --- | --- | --- |
| `BadOrder.java` | File nguồn mà `javac` báo lỗi | Mở đúng file, không đoán từ file khác |
| `:8:` | Dòng trong file đang được compiler tham chiếu | Đọc cả vài dòng trước đó, nhất là case đứng trước |
| `error: ...` | Lỗi khiến biên dịch thất bại | Xác định quy tắc ngôn ngữ bị vi phạm |
| Dòng code được in lại | Nơi compiler phát hiện vấn đề | So sánh với thứ tự case/kiểu selector |
| `^` | Vị trí compiler làm nổi bật | Đây là vị trí phát hiện, không nhất thiết là nguyên nhân gốc |
| `1 error` | Số lỗi trong lượt biên dịch | Sửa và biên dịch lại để nhận trạng thái mới |

**Điểm cốt lõi:** Nơi `javac` chỉ vào đôi khi chỉ là *triệu chứng*. Với lỗi `dominated`, compiler chỉ vào `case String` nhưng **nguyên nhân** là case tổng quát đã nằm phía trước. Với lỗi `cannot find symbol`, vị trí không tìm thấy biến có thể do pattern được khai báo ở nhánh điều kiện không bảo đảm đã khớp.

### Error, warning và note khác nhau

- **`error`:** Vi phạm quy tắc biên dịch, như `switch` thiếu coverage hay type pattern sai. `javac` không tạo bản build thành công từ nguồn có lỗi đó. Không xử lý bằng cách bỏ cờ lint.
- **`warning`:** Compiler phát hiện nguy cơ hoặc tình huống nên xem lại, ví dụ phép ép kiểu generic không thể kiểm tra đầy đủ ở runtime. Thông thường build vẫn có thể thành công nếu không dùng `-Werror`.
- **`note`:** Thông tin thêm, đôi khi gợi ý dùng cờ `-Xlint:...` để thấy cảnh báo chi tiết. Note không tự đồng nghĩa với error.
- **`-Werror`:** Khi bật, có warning sẽ khiến biên dịch thất bại; vì vậy phải phân biệt *nguyên nhân cảnh báo* với chính sách build coi warning là lỗi.

Không kết luận “pattern matching có lỗi” chỉ vì một warning xuất hiện trong cùng file. Cần đọc đúng loại diagnostic và biểu thức gây ra nó.

## 3. Các lệnh javac hữu ích khi điều tra

Biên dịch một file Java 21:

```bash
javac --release 21 JavacPatternDiagnosticsDemo.java
```

Bật các cảnh báo và thông tin chẩn đoán chi tiết:

```bash
javac --release 21 -Xlint:all -Xdiags:verbose JavacPatternDiagnosticsDemo.java
```

Chỉ tập trung vào unchecked operations:

```bash
javac --release 21 -Xlint:unchecked JavacPatternDiagnosticsDemo.java
```

Trong môi trường kiểm thử/CI muốn coi warning là lỗi:

```bash
javac --release 21 -Xlint:all -Werror JavacPatternDiagnosticsDemo.java
```

Các lệnh trên là **những cách chạy riêng biệt**, không cần thực hiện đồng thời. Với các đoạn mã cố ý sai bên dưới, hãy đặt chúng vào file minh họa phù hợp rồi chạy compiler để xem lỗi; không ghép các đoạn cố ý sai vào chương trình hoàn chỉnh.

**Giải thích tùy chọn:**
- `--release 21`: biên dịch theo ngôn ngữ và API Java SE 21 trên JDK hỗ trợ target này; không tự bảo đảm máy chạy có Java 21.
- `-Xlint:all`: yêu cầu `javac` phát ra các nhóm warning được hỗ trợ, không chỉ warning liên quan pattern.
- `-Xlint:unchecked`: làm rõ phép cast/hoạt động generic không thể kiểm tra an toàn tại thời điểm biên dịch.
- `-Xdiags:verbose`: yêu cầu dạng diagnostic chi tiết hơn; không thay đổi ngữ nghĩa Java hay tự sửa lỗi.
- `-Werror`: yêu cầu build thất bại nếu có warning; không biến một phép cast không an toàn thành phép cast an toàn.

Kiểm tra phiên bản compiler bằng `javac -version`. Với Java 21, dùng `case T x when ...`; các ví dụ về `switch` và record pattern từ những bản *preview* trước đó có thể có cú pháp khác. Đừng bật `--enable-preview` theo thói quen để “sửa” lỗi của code Java 21 vốn đã là tính năng chính thức.

## 4. Ví dụ chạy đúng: một chương trình không có lỗi pattern

Tạo file **`JavacPatternDiagnosticsDemo.java`**:

```java
public class JavacPatternDiagnosticsDemo {

    sealed interface Result permits Message, Count {}

    record Message(String content) implements Result {}

    record Count(int value) implements Result {}

    static String describe(Result value) {
        return switch (value) {
            case Message(String s) when s == null ->
                "message=null";

            case Message(String s) when s.isBlank() ->
                "message=blank";

            case Message(String s) ->
                "message=" + s;

            case Count(int n) when n < 0 ->
                "count=negative";

            case Count(int n) ->
                "count=" + n;

            case null ->
                "null input";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Message("ok")));
        System.out.println(describe(new Message(" ")));
        System.out.println(describe(new Message(null)));
        System.out.println(describe(new Count(-2)));
        System.out.println(describe(new Count(3)));
        System.out.println(describe(null));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 -Xlint:all -Xdiags:verbose JavacPatternDiagnosticsDemo.java
java JavacPatternDiagnosticsDemo
```

**Kết quả stdout:**

```text
message=ok
message=blank
message=null
count=negative
count=3
null input
```

Giải thích lý do code biên dịch được:

1. `Result` là `sealed interface`, chỉ cho phép hai record con `Message` và `Count`.
2. Case `Message(String s) when s == null` xử lý component chuỗi `null`.
3. Case `Message(String s) when s.isBlank()` xử lý chuỗi rỗng/trắng, sau khi null đã được xử lý.
4. Case `Message(String s)` không guard xử lý các `Message` còn lại.
5. Case `Count(int n) when n < 0` xử lý giá trị âm; case `Count(int n)` không guard xử lý mọi `Count` còn lại.
6. `case null` xử lý selector `value == null`.
7. Các case không guard bao phủ mọi subtype của `Result`, nên switch expression này **exhaustive** dù không có `default`.

**Phân biệt hai loại null:** `case null` nhận chính selector null. Nhưng component `String s` nằm trong `Message(String s)` vẫn có thể là null: tại vị trí component khai báo kiểu `String`, pattern này là unconditional. Đừng nhầm với `null instanceof String`, vốn là `false`.

Chương trình là ví dụ chạy hoàn chỉnh; các đoạn lỗi phía sau là ví dụ **cố ý không biên dịch** để luyện đọc diagnostic.

## 5. Error: case label is dominated by a preceding case label

### Mã gây lỗi

```java
// Ví dụ cố ý sai, đặt trong một phương thức nhận Object value:
return switch (value) {
    case CharSequence seq -> "char sequence";
    case String text -> "string";
    case null -> "null";
    default -> "other";
};
```

`String` triển khai `CharSequence`, do đó mọi giá trị `String` đã khớp `case CharSequence seq`. Case `String text` phía sau không thể được chọn.

Một diagnostic thực tế của `javac` là:

```text
error: this case label is dominated by a preceding case label
```

Đây là **error**, không phải warning. Nó đến từ quan hệ bao phủ giữa những pattern.

### Sửa

Đặt case cụ thể lên trước case tổng quát:

```java
return switch (value) {
    case String text -> "string";
    case CharSequence seq -> "char sequence";
    case null -> "null";
    default -> "other";
};
```

Tương tự, với record pattern:

```java
// Sai thứ tự nếu các case nằm trong cùng switch:
case Message(String s) -> "any message";
case Message(String s) when s.isBlank() -> "blank";
```

Case `Message` không guard đã bao phủ nhánh có guard phía sau. **Sửa:** case có guard trước, case không guard sau. Với hai pattern cùng subtype nhưng guard khác nhau, dùng case dự phòng nếu các guard không bao phủ hết giá trị.

**Mẹo đọc lỗi:** Khi compiler chỉ vào một case bị dominated, hãy nhìn **lên trên** để tìm case cha hoặc case không guard đã nhận toàn bộ giá trị của nó.

## 6. Error: the switch expression does not cover all possible input values

### Mã gây lỗi

```java
// value có kiểu Object:
return switch (value) {
    case String text -> text;
};
```

`Object` còn có thể chứa `Integer`, `Double`, record tự định nghĩa, v.v. Case `String` không thể bao phủ hết miền giá trị. Một diagnostic được `javac` phát ra là:

```text
error: the switch expression does not cover all possible input values
```

### Sửa

Thêm case cho các kiểu cần xử lý và fallback cho phần còn lại:

```java
return switch (value) {
    case String text -> text;
    case Integer number -> "number=" + number;
    case null -> "null";
    default -> "other";
};
```

Nếu selector là một **sealed hierarchy** đóng kín, hãy dùng case cho đủ các subtype hợp lệ. Không nhất thiết thêm `default`: việc để compiler kiểm tra exhaustive giúp phát hiện subtype mới mà chưa được xử lý khi biên dịch lại.

**Phân biệt statement:** Java 21 cũng yêu cầu **enhanced switch statement** (ví dụ switch có pattern labels) phải exhaustive. Với switch statement truyền thống chỉ có constant labels, quy tắc về exhaustive có thể khác. Không nên áp dụng mẹo “switch statement không cần default” một cách máy móc cho pattern switch.

**Một nhánh có `when` thường không bao phủ hết subtype:** `case Count(int n) when n < 0` không xử lý `Count(3)`. Muốn exhaustive, thêm `case Count(int n)` không guard hoặc pattern bao phủ phù hợp.

## 7. Error: cannot find symbol — biến pattern nằm ngoài phạm vi

### Mã gây lỗi

```java
// Ví dụ cố ý sai; value có kiểu Object:
if (value instanceof String text) {
    System.out.println(text);
}

System.out.println(text.length());
```

Biến `text` chỉ được ràng buộc tại những vị trí Java chứng minh pattern đã khớp. Sau `if`, điều đó không còn chắc chắn. `javac` phát ra diagnostic kiểu:

```text
error: cannot find symbol
  symbol:   variable text
```

### Sửa cách 1: dùng biến trong nhánh đã khớp

```java
if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("not a string");
}
```

### Sửa cách 2: thoát sớm khi pattern không khớp

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

Ở cách 2, sau khi thoát khỏi trường hợp không khớp bằng `return`, compiler biết nhánh còn lại đã khớp `String`; biến `text` được phép dùng.

**Mẹo đọc lỗi:** Khi gặp `cannot find symbol` cho pattern variable, đừng vội khai báo lại một biến trùng tên. Hãy xem **flow scoping** của `instanceof`, `&&`, `||`, `if` và từng `case` trong `switch`.

## 8. Error: incorrect number of nested patterns — record pattern sai số component

Giả sử record được khai báo:

```java
record Pair(int left, int right) {}
```

### Mã gây lỗi

```java
// value có kiểu Object:
if (value instanceof Pair(int left)) {
    System.out.println(left);
}
```

`Pair` khai báo **hai** record component, nhưng pattern chỉ cung cấp **một** nested pattern. `javac` có thể thông báo:

```text
error: incorrect number of nested patterns
  required: int,int
  found:    int
```

### Sửa

Viết một pattern cho **mỗi record component**, đúng thứ tự khai báo:

```java
if (value instanceof Pair(int left, int right)) {
    System.out.println(left + right);
}
```

Các record pattern không có cú pháp “bỏ qua một vị trí” bằng cách giảm số component. Nếu chỉ cần một component mà không cần phân loại cấu trúc, dùng accessor `pair.left()` trên một `Pair` đã biết kiểu cũng là lựa chọn đơn giản.

**Mẹo đọc lỗi:** So đối chiếu số và kiểu component trong header `record Name(T1 a, T2 b, ...)` với danh sách trong `Name(pattern1, pattern2, ...)`. Với nested record pattern nhiều cấp, kiểm tra từng record từ ngoài vào trong.

## 9. Error: generic pattern không kiểm tra an toàn được

### Mã gây lỗi

```java
// value có kiểu Object:
if (value instanceof java.util.List<String> items) {
    System.out.println(items.size());
}
```

`List<String>` là một kiểu parameterized không reifiable theo cách cần để runtime phân biệt `List<String>` với `List<Integer>`. `javac` báo lỗi kiểu:

```text
error: java.lang.Object cannot be safely cast to java.util.List<java.lang.String>
```

Đây là **error** của pattern `instanceof` trong tình huống này, **không phải unchecked warning** để chỉ cần tắt lint.

### Sửa

Dùng kiểu có thể kiểm tra tại runtime như `List<?>` và kiểm tra phần tử khi cần:

```java
if (value instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println("string=" + text);
        } else {
            System.out.println("not a string");
        }
    }
}
```

Ở đây `List<?>` xác nhận object là một list nhưng **không chứng minh mọi phần tử là String**. Kiểm tra từng phần tử tránh suy diễn không an toàn về generic type.

**Phân biệt quan trọng:** `instanceof List<String>` trên `Object` có thể là **error**. Trong khi đó phép cast `(List<String>) value` có thể biên dịch kèm **unchecked warning**. Hai tình huống khác nhau và phải sửa theo nguyên nhân thực tế.

## 10. Error: incompatible types — guard when phải trả boolean

### Mã gây lỗi

```java
// value có kiểu Object; đoạn nằm trong một switch expression:
case String text when text.length() -> text;
```

`text.length()` có kiểu `int`, trong khi `when` yêu cầu một biểu thức điều kiện kiểu `boolean`. `javac` có thể ghi:

```text
error: incompatible types: int cannot be converted to boolean
```

### Sửa

Viết phép so sánh boolean rõ ràng:

```java
case String text when text.length() > 0 -> text;
```

Cần có các case phù hợp khác để xử lý chuỗi rỗng, null và các loại object khác. Nếu guard gọi phương thức có thể ném exception, ví dụ `text.isBlank()` hoặc `text.length()` trên một biến có thể null, hãy kiểm tra null trước hoặc dùng điều kiện an toàn.

Trong Java 21, cú pháp guard là **`when`**. Một số tutorial từ Java preview trước có thể dùng cú pháp khác; luôn xác định bản Java đang biên dịch trước khi sao chép.

## 11. Warning: unchecked cast — khác với lỗi pattern

Xét phương thức:

```java
// Đoạn mã minh họa, không phải một pattern:
static java.util.List<String> asStrings(Object value) {
    return (java.util.List<String>) value;
}
```

Nếu biên dịch cùng `-Xlint:unchecked`, `javac` có thể phát ra:

```text
warning: [unchecked] unchecked cast
  required: java.util.List<java.lang.String>
  found:    java.lang.Object
```

Một số phiên bản hiển thị phần phân loại, cách căn dòng hoặc chú thích khác nhau. Bản chất vẫn là compiler **không thể chứng minh** cast từ `Object` thành `List<String>` an toàn đối với kiểu phần tử. Runtime chỉ kiểm tra được phần thô như `List`, không đảm bảo list chứa toàn `String`.

### Cách xử lý an toàn hơn

Nếu mục tiêu là nhận mọi phần tử kiểu `String` và từ chối phần tử khác:

```java
static java.util.List<String> copyStrings(Object value) {
    if (!(value instanceof java.util.List<?> items)) {
        throw new IllegalArgumentException("Not a list");
    }

    java.util.List<String> result = new java.util.ArrayList<>();
    for (Object item : items) {
        if (item instanceof String text) {
            result.add(text);
        } else {
            throw new IllegalArgumentException("Non-string element");
        }
    }
    return result;
}
```

Cách này trả về một list mới sau khi kiểm tra từng phần tử. Nếu input rỗng, vẫn tạo list rỗng hợp lệ; nếu có `null`, ví dụ này chủ động từ chối vì `null instanceof String` là `false`. Quy tắc nhận hay không nhận null là quyết định thiết kế của ứng dụng.

**Không chỉ thêm `@SuppressWarnings("unchecked")` để che đi rủi ro.** Annotation này chỉ có ý nghĩa nếu đã có bất biến/kiểm chứng bên ngoài và chấp nhận rủi ro; nó không biến phép cast thành an toàn. Trong CI có `-Werror`, warning như vậy có thể làm build fail.

## 12. Phân nhóm diagnostic để sửa nhanh

| Diagnostic hoặc triệu chứng | Loại thường gặp | Nguyên nhân pattern | Hướng sửa |
| --- | --- | --- | --- |
| `this case label is dominated ...` | **error** | Case rộng nằm trước case hẹp | Đặt case cụ thể/guard trước hoặc bỏ case bị che |
| `switch expression does not cover ...` | **error** | Chưa exhaustive | Bổ sung subtype, fallback hoặc default phù hợp |
| `cannot find symbol: variable x` | **error** | Biến pattern ngoài flow scope | Dùng trong nhánh chắc chắn khớp; refactor điều kiện |
| `incorrect number of nested patterns` | **error** | Record pattern không đủ/thừa component | Căn theo record header |
| `cannot be safely cast to List<String>` | **error** | Generic type không thể kiểm tra kiểu phần tử tại runtime | Dùng `List<?>` và kiểm tra element |
| `int cannot be converted to boolean` | **error** | Guard `when` không tạo boolean | Dùng phép so sánh/biểu thức boolean |
| `unchecked cast` | **warning** | Cast generic không kiểm chứng an toàn | Kiểm tra dữ liệu, copy/validate hoặc thiết kế type tốt hơn |
| `warnings found and -Werror specified` | **error do chính sách build** | Có warning nhưng cờ `-Werror` được bật | Xử lý warning gốc trước |
| Thông báo cần `--enable-preview` | Tùy JDK và tính năng | Code dùng syntax preview/khác version | Kiểm tra JDK và trạng thái tính năng; Java 21 pattern chính thức không cần preview |

Một chuỗi lỗi có thể bắt nguồn từ **một lỗi cú pháp hoặc kiểu ban đầu**. Sửa nguyên nhân ở vị trí sớm nhất, biên dịch lại, rồi xem các lỗi còn lại. Không đánh đồng hàng chục chẩn đoán thứ cấp thành hàng chục vấn đề độc lập.

## 13. Quy trình thực tế khi javac báo lỗi pattern

**Bước 1 — Ghi nhận lệnh và phiên bản:** Chạy `javac -version`. Xác định `--release`/`--source`, cờ preview và cờ lint đang dùng. Ví dụ code Java 21 không được mặc định sẽ chạy trên compiler Java 17 không có các tính năng final của Java 21.

**Bước 2 — Đọc lỗi đầu tiên và source liên quan:** Ghi nhận file, dòng, phần diagnostic và case/biểu thức gần đó. Nếu thông báo nói `dominated`, soát các nhánh trước; nếu `not exhaustive`, xem toàn bộ hierarchy và fallback.

**Bước 3 — Xác định loại kiểm tra:** Lỗi thuộc cú pháp, kiểu tĩnh, flow scope, record deconstruction, dominance hay exhaustiveness? Mỗi nhóm có cách sửa khác nhau; không sửa bằng ép kiểu mù.

**Bước 4 — Sửa tối thiểu nhưng đúng ngữ nghĩa:** Đổi thứ tự case, bổ sung case fallback, điều chỉnh record arity, viết guard boolean hoặc đưa biến vào phạm vi hợp lệ. Không thêm `default` bừa bãi nếu muốn compiler tiếp tục nhắc về subtype mới của sealed hierarchy.

**Bước 5 — Biên dịch lại với cờ hữu ích:** Chạy lại `javac --release 21 -Xlint:all -Xdiags:verbose` và tách warnings còn lại khỏi errors. Nếu đội dùng `-Werror`, xác định warning gốc và xử lý từ nguồn.

**Bước 6 — Kiểm thử runtime:** Khi build qua, chạy test cho nhánh cụ thể, nhánh fallback, selector null, record component null, giá trị biên guard và dữ liệu generic không hợp lệ. Compiler kiểm tra pattern đúng luật, nhưng không đảm bảo mọi quy tắc nghiệp vụ đã đúng.

### Một checklist ngắn khi đọc case pattern

- Selector có kiểu tĩnh là gì? Có `null` không?
- Pattern đang kiểm tra kiểu ngoài hay các component của record?
- Case phía trước đã bao phủ case hiện tại chưa?
- Những case có guard có một case không guard/fallback tương ứng không?
- Sealed hierarchy có subtype nào chưa được xử lý?
- Biến pattern đang được dùng tại vị trí compiler biết đã khớp chứ?
- Generic type đó có thể kiểm tra an toàn tại runtime không?
- Diagnostic thực sự là `error`, `warning` hay `note`?

## 14. Bài tập: chủ động tạo lỗi và đọc lại javac

**Bài tập 1 — Dominance.** Trong `JavacPatternDiagnosticsDemo`, đưa `case Message(String s) -> ...` lên trước case `Message(String s) when s == null`. Biên dịch lại để quan sát lỗi dominated. Sau đó khôi phục thứ tự từ cụ thể tới tổng quát.

**Bài tập 2 — Exhaustiveness.** Thêm `record Failure(String reason) implements Result {}` và cập nhật `permits` của `Result` nhưng chưa thêm case `Failure` vào `describe`. Biên dịch lại để quan sát yêu cầu bao phủ subtype mới. Sau đó bổ sung case `Failure(String reason) -> "failure=" + reason;`.

**Bài tập 3 — Scope.** Viết một phương thức `int length(Object value)` cố ý dùng biến `text` sau một `if (value instanceof String text)` mà nhánh không khớp vẫn đi tới phần sử dụng. Quan sát `cannot find symbol`; sửa bằng nhánh `else` hoặc `return` sớm.

**Bài tập 4 — Record arity.** Đổi `case Count(int n)` thành `case Count(int n, int other)`. `Count` chỉ có một component; đọc diagnostic về số nested patterns, rồi sửa lại đúng một component.

**Bài tập 5 — Warning đối lập error.** Tạo hai hàm: một hàm kiểm tra `Object` bằng `instanceof List<String>` và một hàm cast `(List<String>) value`. Chạy với `-Xlint:unchecked`. Giải thích vì sao hàm thứ nhất gây error trong trường hợp này, còn hàm thứ hai có thể tạo unchecked warning. Cuối cùng thay cả hai bằng kiểm tra `List<?>` và từng phần tử.

**Ghi nhớ:** `javac` báo vị trí lỗi, nhưng người lập trình cần đọc **quy tắc type checking/flow checking** phía sau thông báo. Với pattern matching Java 21, bốn câu hỏi quan trọng nhất là **pattern có thể khớp không, nhánh có bị che không, biến có ở đúng phạm vi không, và switch có exhaustive không**. Cảnh báo unchecked khác về bản chất với lỗi pattern không hợp lệ; hãy sửa theo nguyên nhân thay vì chỉ tìm cách tắt diagnostic.

## Tài liệu tham khảo

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — `javac` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Java Language Specification SE 21 — Pattern Matching for `instanceof`, `switch` và pattern scopes: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html
- OpenJDK JEP 440: https://openjdk.org/jeps/440
- OpenJDK JEP 441: https://openjdk.org/jeps/441
