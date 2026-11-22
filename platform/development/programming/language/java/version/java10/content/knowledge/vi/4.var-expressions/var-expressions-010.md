# Biểu thức điều kiện `?:` và kiểu chung được suy luận với `var` (Java 10+)

## 1. Vấn đề: hai nhánh khác kiểu, `var` nhận kiểu nào?

Trong Java 10 trở lên, `var` cho phép khai báo biến cục bộ mà không lặp lại tên kiểu khi **biểu thức khởi tạo** đã cung cấp đủ thông tin. Với toán tử điều kiện `?:`, điều này đặt ra câu hỏi quan trọng: **kiểu của biến được suy luận từ toàn bộ biểu thức, không chỉ từ nhánh thực sự chạy**.

Cú pháp:

```java
var result = condition ? expressionWhenTrue : expressionWhenFalse;
```

Trong đó:

- `condition` phải có kiểu `boolean` hoặc `Boolean`.
- Toán tử kiểm tra điều kiện trước, sau đó chỉ đánh giá **một trong hai** biểu thức ở nhánh kết quả.
- **Kiểu ở thời điểm biên dịch** được tính từ quy tắc của cả hai nhánh, bất kể nhánh nào chạy lúc runtime.
- `var` không phải kiểu động: khi compiler đã suy luận kiểu, biến chịu những kiểm tra kiểu thông thường của Java.

Ví dụ:

```java
boolean isDiscounted = true;
var price = isDiscounted ? 10 : 12.5;
System.out.println(price); // 10.0
```

Dù điều kiện là `true` và nhánh thực thi tạo số nguyên `10`, kiểu của biểu thức là `double` do hai nhánh `int` và `double` được áp dụng **numeric promotion**. Giá trị in ra là `10.0`. Khi chọn `var`, ta phải hiểu cả cách tính **giá trị** lẫn cách xác định **kiểu**.

## 2. Cơ chế thực thi của toán tử ba ngôi

Hình thức `condition ? a : b` có thể hiểu như một phép chọn một giá trị:

```java
String state;
if (isReady) {
    state = "ready";
} else {
    state = "waiting";
}
```

Khi dùng biểu thức điều kiện:

```java
String state = isReady ? "ready" : "waiting";
```

Cả hai cách trên đều chọn giá trị theo điều kiện. Tuy nhiên, toán tử `?:` là **biểu thức có một kiểu riêng**, được compiler xác định theo Java Language Specification (JLS); điều này đặc biệt quan trọng nếu thay `String` ở vế trái bằng `var`.

Chỉ nhánh được chọn mới thực thi:

```java
boolean enabled = true;
var value = enabled ? 100 : 10 / 0;
System.out.println(value); // 100
```

Nhánh `10 / 0` không được đánh giá ở ví dụ này, vì thế không ném `ArithmeticException`. Compiler **vẫn phân tích cả hai nhánh về mặt kiểu và cú pháp**; một nhánh có lỗi biên dịch không trở nên hợp lệ chỉ vì điều kiện thường chọn nhánh kia.

Khi điều kiện có kiểu `Boolean` và giá trị là `null`, quá trình unboxing điều kiện để kiểm tra `true/false` có thể ném `NullPointerException` trước khi chọn nhánh.

## 3. `var` dùng kiểu của biểu thức, không tự suy luận theo giá trị runtime

Trong khai báo cục bộ:

```java
boolean premium = false;
var category = premium ? "PREMIUM" : "STANDARD"; // String
var amount = premium ? 1 : 2L;                  // long
var percent = premium ? 0.2 : 0.05;              // double
```

- `category` là `String` vì cả hai nhánh đều là `String`.
- `amount` là `long` vì hai nhánh số nguyên `int` và `long` dẫn đến kiểu `long`.
- `percent` là `double` vì literal thập phân ở đây mặc định là `double`.

Không phải compiler đợi chương trình chạy rồi mới biết kiểu. Trường hợp:

```java
var count = premium ? 1 : 2;
count = 3;         // Hợp lệ: int
// count = "three"; // Lỗi biên dịch: String không gán cho int
```

`count` luôn có kiểu `int` trong phạm vi biến. Muốn kiểu khác, cần thiết kế biểu thức hoặc khai báo kiểu cụ thể ngay từ đầu.

Đặc biệt, biểu thức khởi tạo của `var` được xử lý **như một biểu thức độc lập, không có kiểu đích từ bên trái** (*standalone expression*). Đây là điểm mấu chốt khi hai nhánh mang kiểu tham chiếu/generic khác nhau; mục 6 sẽ giải thích sự khác biệt với khai báo `List<String>` tường minh.

## 4. Ba nhóm quy tắc xác định kiểu của `?:`

Theo JLS ```15.25, toán tử điều kiện được phân loại thành **boolean conditional**, **numeric conditional** hoặc **reference conditional**. Không có một công thức đơn giản kiểu “luôn lấy `Object`” hoặc “luôn lấy nhánh bên trái” áp dụng cho mọi biểu thức.

### 4.1. Boolean conditional: `boolean` và `Boolean`

Khi cả hai nhánh là biểu thức boolean:

```java
boolean flag = true;
var first = flag ? true : false;                 // boolean
var second = flag ? Boolean.TRUE : Boolean.FALSE; // Boolean
var third = flag ? true : Boolean.FALSE;         // boolean
```

Quy tắc cơ bản: nếu cả hai toán hạng nhánh có kiểu `Boolean` thì kết quả có kiểu `Boolean`; ngoài trường hợp đó, kết quả là kiểu nguyên thủy `boolean`. Trong các trường hợp cần chuyển `Boolean` thành `boolean`, compiler có thể thêm **unboxing**. Giá trị `Boolean null` ở nhánh cần unbox sẽ gây `NullPointerException`.

Đừng nhầm việc kết quả được suy luận là `boolean` với bảo đảm rằng mọi toán hạng đóng hộp đều khác `null`.

### 4.2. Numeric conditional: kiểu số và các quy tắc nâng kiểu

Khi cả hai nhánh là biểu thức số, JLS áp dụng các trường hợp riêng cho kiểu bằng nhau, primitive và wrapper tương ứng, hằng `int` nằm trong miền `byte/short/char`, và **binary numeric promotion** khi cần.

Ví dụ thường gặp:

| Biểu thức | Kiểu suy luận | Giải thích |
| --- | --- | --- |
| `flag ? 1 : 2` | `int` | Cả hai nhánh là `int`. |
| `flag ? 1 : 2L` | `long` | Nâng kiểu số từ `int` sang `long`. |
| `flag ? 1 : 2.5` | `double` | Nâng kiểu số sang `double`. |
| `flag ? (byte) 1 : 2` | `byte` | Hằng `int` giá trị 2 nằm trong miền `byte` (quy tắc riêng). |
| `flag ? 1 : Integer.valueOf(2)` | `int` | Nhánh primitive `int` và wrapper `Integer` tương ứng. |

Bảng minh họa các trường hợp phổ biến và một ngoại lệ; **không** nên thay toàn bộ quy tắc JLS bằng nhận xét “toán tử `?:` luôn chọn kiểu số rộng nhất”. Ví dụ `byte` với hằng `int` phù hợp có thể giữ kiểu `byte`.

Hai nhánh có thể bị chuyển đổi kiểu trước khi kết quả được gán cho `var`. Vì vậy không được suy luận kiểu chỉ từ dạng chữ của nhánh mà điều kiện đang chọn.

### 4.3. Reference conditional: kiểu tham chiếu chung

Khi biểu thức không thuộc hai nhóm trên, nó được xử lý như **reference conditional**.

Trường hợp đơn giản:

```java
var title = flag ? "Intro" : "Advanced";   // String
var defaultName = flag ? null : "Guest";    // String
```

Ở `defaultName`, một nhánh là literal `null` và nhánh còn lại là `String`, nên kiểu tĩnh có thể suy luận là `String`. **Giá trị runtime vẫn có thể là `null`** nếu `flag` là `true`; việc suy luận được kiểu không tự thêm kiểm tra non-null.

Nếu hai nhánh có kiểu tham chiếu khác nhau, compiler có thể tìm **least upper bound (LUB)** – kiểu cha chung thích hợp theo quy tắc ngôn ngữ, có thể kết hợp interface, generic wildcard và trong một số trường hợp là intersection type. Không thể khẳng định kết quả luôn là `Object` hoặc luôn là một lớp cha đơn giản.

```java
Number value = flag ? Integer.valueOf(1) : Double.valueOf(2.5);
```

Dòng này có khai báo **kiểu đích tường minh** `Number` nên phép gán được kiểm tra với kiểu đó. Tuy nhiên, trong ngữ cảnh toán tử `?:`, hai nhánh đều mang kiểu wrapper của số, vì vậy **đây là numeric conditional**, có thể xảy ra unboxing và nâng kiểu trước khi boxing để gán vào `Number`. Không lấy dòng này làm ví dụ về LUB tham chiếu.

Ví dụ reference conditional rõ ràng hơn:

```java
var text = flag ? new StringBuilder("A") : new StringBuffer("B");
```

Cả hai nhánh là đối tượng khác loại; `text` có kiểu tĩnh được xác định theo quy tắc kiểu tham chiếu chung. Không giả định nó là `StringBuilder` hoặc `StringBuffer` chỉ vì điều kiện thường chọn một nhánh. Nếu muốn API chỉ phơi bày chuỗi ký tự, có thể chỉ rõ:

```java
CharSequence text = flag ? new StringBuilder("A") : new StringBuffer("B");
```

Biến `text` lúc này có hợp đồng rõ là `CharSequence`, mặc dù object runtime của mỗi nhánh vẫn là kiểu cụ thể của nó.

## 5. Phân biệt “kiểu chung” với kiểu đối tượng thực tế

Giả sử hai nhánh khởi tạo các implementation khác nhau của cùng interface:

```java
boolean chooseArray = true;
java.util.List<String> result = chooseArray
        ? new java.util.ArrayList<String>()
        : new java.util.LinkedList<String>();
```

Ở dòng này:

- **Kiểu tĩnh của biến `result`:** `List<String>`, vì khai báo bên trái quy định như vậy.
- **Kiểu object runtime:** `ArrayList` hoặc `LinkedList` tùy điều kiện.
- **Quyền gọi phương thức:** được compiler kiểm tra theo `List<String>`, chứ không tự chuyển đổi thành kiểu object runtime sau mỗi lần chạy.

Nếu viết:

```java
var result = chooseArray
        ? new java.util.ArrayList<String>()
        : new java.util.LinkedList<String>();
```

Kiểu suy luận dựa trên reference conditional độc lập, có thể là kiểu chung phức tạp hơn một tên interface cụ thể. Trong thực tế thường vẫn gọi được các thao tác chung như `add(String)`, nhưng **không nên dựa vào một tên kiểu suy luận cụ thể khi nó khó đọc hoặc khi thay đổi kiểu của một nhánh có thể ảnh hưởng hợp đồng sau đó**.

Lưu ý: cả hai phiên bản đều **chỉ tạo một object ở nhánh được chọn**, không tạo đồng thời hai collection.

## 6. `var` có thể làm khác kết quả suy luận generic vì thiếu kiểu đích

Đây là khác biệt quan trọng giữa hai kiểu khai báo sau:

```java
boolean chooseArray = false;

// Có target type: compiler biết cần List<String>.
java.util.List<String> names = chooseArray
        ? new java.util.ArrayList<>()
        : new java.util.LinkedList<>();
names.add("JDK");

// Không có target type từ vế trái.
var inferred = chooseArray
        ? new java.util.ArrayList<>()
        : new java.util.LinkedList<>();
inferred.add(10);
inferred.add("mixed");
```

Trong biến `names`, kiểu đích `List<String>` giúp các phép tạo collection dùng `<>` suy luận phần tử `String`. Do đó `names.add(10)` sẽ bị từ chối ở thời điểm biên dịch.

Trong biến `inferred`, `var` không cung cấp `List<String>` làm kiểu đích; những phép tạo collection `new ArrayList<>()`/`new LinkedList<>()` trong các nhánh có thể suy luận tham số kiểu `Object`. Kết quả là `inferred.add(10)` và `inferred.add("mixed")` đều có thể biên dịch. Đây là **mất ràng buộc kiểu phần tử mà người viết có thể không mong muốn**.

Cách xử lý:

```java
var inferredNames = chooseArray
        ? new java.util.ArrayList<String>()
        : new java.util.LinkedList<String>();
inferredNames.add("JDK");
// inferredNames.add(10); // Lỗi kiểu: Integer không phải String.
```

Hoặc chọn khai báo `List<String>` tường minh khi hợp đồng dữ liệu quan trọng hơn việc tiết kiệm tên kiểu.

Về thuật ngữ JLS:

- Reference conditional là **poly expression** khi ở **assignment context** hoặc **invocation context**, nơi nó nhận được target type.
- Nếu không ở hai ngữ cảnh đó, nó là **standalone expression** và kiểu được xác định từ các nhánh.
- Với `var variable = initializer;`, compiler xem initializer như **không có assignment context để cung cấp target type cho chính initializer**. Vì vậy không thể suy luận rằng nó hoàn toàn giống `List<String> variable = initializer;`.

Hai cách viết trông gần nhau có thể dẫn đến **các kiểu generic khác nhau**. Đây là lý do không nên thay hàng loạt khai báo tường minh bằng `var` mà không xem initializer.

### Không nhầm với kiểu trả về của generic method

```java
var first = java.util.List.of("a", "b"); // List<String>
```

Dù `var` không đưa kiểu đích từ bên trái, các lời gọi generic vẫn có thể suy luận kiểu từ **đối số truyền vào**, nên ví dụ trên nhận `List<String>`. Vấn đề rõ nhất xuất hiện khi thông tin kiểu **không có trong constructor/lời gọi** như `new ArrayList<>()`, hoặc khi hai nhánh có các kiểu tham chiếu khó dung hòa.

Không có quy tắc “`var` luôn suy luận `Object`”. Kiểu thực tế phụ thuộc biểu thức và các quy tắc Java.

## 7. `null`: suy luận được kiểu chưa chắc an toàn runtime

Cần phân biệt ba tình huống.

**Tình huống A: một nhánh `null` và một nhánh tham chiếu**

```java
boolean useNull = false;
var message = useNull ? null : "fallback"; // String
System.out.println(message);               // fallback
```

Compiler suy luận kiểu `String`, nhưng khi `useNull == true` thì giá trị là `null`. Nếu gọi `message.length()` lúc đó, chương trình sẽ ném `NullPointerException`.

**Tình huống B: cả hai nhánh đều là `null`**

```java
boolean flag = true;
// var notAllowed = flag ? null : null; // Lỗi: không thể suy luận kiểu từ null type.
```

`var` không nhận initializer có kiểu `null`. Nếu thật sự cần giá trị nullable, khai báo kiểu phù hợp:

```java
String allowed = flag ? null : null;
```

**Tình huống C: một nhánh primitive và một nhánh wrapper có giá trị `null`**

```java
boolean choosePrimitive = false;
Integer boxed = null;
// var total = choosePrimitive ? 1 : boxed; // Có thể NPE khi chọn boxed.
```

Vì nhánh `int` và nhánh `Integer` tạo numeric conditional có kiểu `int`, compiler có thể **unbox** `boxed`. Nếu chọn nhánh chứa `Integer null` thì xảy ra `NullPointerException`. Khai báo `var` không tự bảo vệ null:

- Nếu null là dữ liệu hợp lệ, chọn chiến lược kiểu/giao diện thể hiện rõ chính sách null.
- Nếu null không hợp lệ, kiểm tra hoặc chuẩn hóa dữ liệu trước.
- Tránh trộn primitive với wrapper nullable trong một `?:` nếu chưa hiểu chuyển đổi kiểu.

## 8. Ví dụ Java 10+ chạy đầy đủ: kiểu số, reference, generic và null

Tạo tệp `ConditionalInferenceDemo.java` với nội dung:

```java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;
import java.util.Locale;

public class ConditionalInferenceDemo {
    static String chooseLabel(boolean condition) {
        var label = condition ? "active" : "inactive";
        return label.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        boolean useFirst = false;
        var score = useFirst ? 5 : 2.5;
        System.out.println("score=" + score);

        var tags = useFirst ? List.of("java", "core") : List.of("api");
        System.out.println("tags=" + tags);

        List<String> names = useFirst ? new ArrayList<>() : new LinkedList<>();
        names.add("JDK");
        System.out.println("names=" + names);

        var inferred = useFirst ? new ArrayList<>() : new LinkedList<>();
        inferred.add(10);
        inferred.add("mixed");
        System.out.println("inferred=" + inferred);
        System.out.println("label=" + chooseLabel(useFirst));

        var fallback = useFirst ? null : "default";
        System.out.println("fallback=" + fallback);

        Integer boxed = null;
        try {
            var unsafe = useFirst ? 1 : boxed;
            System.out.println("unsafe=" + unsafe);
        } catch (NullPointerException ex) {
            System.out.println("nullable branch caused unboxing");
        }
    }
}
```

Biên dịch theo đúng cú pháp/ngôn ngữ Java 10, sau đó chạy bằng JDK 10+:

```bash
javac --release 10 ConditionalInferenceDemo.java
java ConditionalInferenceDemo
```

Đầu ra xác định:

```text
score=2.5
tags=[api]
names=[JDK]
inferred=[10, mixed]
label=INACTIVE
fallback=default
nullable branch caused unboxing
```

Phân tích từng dòng:

1. `score` là `double` vì nhánh `5` (`int`) và `2.5` (`double`) được nâng kiểu số; khi `useFirst` là `false`, giá trị `2.5` được in ra.
2. `tags` được tạo từ một trong hai lời gọi `List.of(...)`. Dữ liệu cả hai bên đều là chuỗi, và chương trình chọn danh sách `["api"]`.
3. `names` có kiểu `List<String>` tường minh; các diamond constructor nhận ngữ cảnh kiểu ấy.
4. `inferred` xuất phát từ hai constructor diamond **không có kiểu đích**; thêm cả số nguyên và chuỗi được compiler chấp nhận, cho ra `[10, mixed]`.
5. `chooseLabel(false)` tạo `"inactive"` rồi viết hoa thành `"INACTIVE"`; `label` có kiểu `String` suy luận từ hai nhánh.
6. `fallback` có kiểu `String` dù một nhánh là `null`; chương trình chọn `"default"`.
7. `unsafe` có kiểu `int` theo quy tắc primitive/wrapper; nhánh `boxed == null` buộc unboxing nên đi vào `catch`. Phần này được cố ý bắt lỗi để chương trình demo chạy tiếp, **không** phải khuyến nghị dùng ngoại lệ để xử lý null hằng ngày.

Khi chạy bằng một JDK hiện đại, tùy cách cài đặt môi trường cần có `javac`/`java` trên `PATH`. Lệnh `--release 10` giúp kiểm tra rằng cú pháp và API chương trình nằm trong giới hạn Java 10; nếu dự án dùng Java 17 hoặc 21 thì ví dụ vẫn hợp lệ.

## 9. Những lỗi thiết kế thường gặp

### 9.1. Nghĩ compiler chọn kiểu theo nhánh sẽ chạy

```java
boolean flag = true;
var result = flag ? 1 : 2.0; // double, không phải int
```

Compiler không thay đổi kiểu của biến theo điều kiện ở runtime. Điều kiện `true` chỉ quyết định **giá trị**, không làm biến thành `int`.

### 9.2. Cho rằng mọi kiểu tham chiếu khác nhau đều trả `Object`

`var value = flag ? objectA : objectB;` có thể nhận một kiểu cha hoặc tập hợp interface chung từ phép tính LUB. Khi kiểu này phức tạp, phương thức dùng được trên `value` có thể không như người viết nghĩ. Nếu API kỳ vọng một interface cụ thể, hãy dùng khai báo kiểu đó hoặc một phương thức factory trả về interface được định nghĩa rõ.

### 9.3. Cho rằng kiểu chung của số là “kiểu của biến có kích thước lớn hơn”

Quy tắc số có các trường hợp hằng `int` với `byte/short/char`, primitive-wrapper và phép nâng kiểu số. Thay vì đoán, kiểm tra JLS ```15.25.2 hoặc biên dịch một ví dụ nhỏ. Với code nghiệp vụ, ép kiểu hoặc khai báo kiểu rõ ràng khi thực sự cần kiểm soát chính xác.

### 9.4. Dùng `var` với hai nhánh generic có diamond thiếu ngữ cảnh

```java
var result = flag
        ? new java.util.ArrayList<>()
        : new java.util.LinkedList<>();
```

Đoạn này có thể suy luận kiểu phần tử là `Object`. Nếu hai nhánh cần quản lý `String`, hãy viết `new ArrayList<String>()`/`new LinkedList<String>()` hoặc khai báo `List<String> result`.

### 9.5. Nhầm suy luận kiểu với kiểm tra `null`

`var text = flag ? null : "ok";` hợp lệ về mặt kiểu nhưng `text` vẫn có thể là `null`. Ngược lại, `var number = flag ? 1 : nullableInteger;` có nguy cơ NPE do unboxing. Hãy giải quyết khả năng null của từng nhánh như một vấn đề dữ liệu riêng.

### 9.6. Lồng `?:` quá sâu

```java
var level = score >= 90 ? "excellent"
        : score >= 70 ? "good"
        : score >= 50 ? "pass"
        : "retry";
```

Toán tử điều kiện có tính **kết hợp từ phải sang trái**, nhưng nhiều lớp lồng sẽ khó đọc. Khi có nhiều quy tắc phân loại, logging, exception hoặc side effect, một chuỗi `if/else` hoặc phương thức có tên thể hiện nghiệp vụ thường rõ hơn.

### 9.7. Dùng biểu thức không tạo được giá trị

Hai nhánh của `?:` phải phù hợp với quy tắc một biểu thức điều kiện; không thể sử dụng lời gọi trả về `void` làm nhánh giá trị. Ví dụ sau **cố ý không biên dịch**:

```java
// var x = flag ? System.out.println("A") : System.out.println("B");
```

Nếu mục tiêu chỉ là thao tác theo điều kiện, dùng `if/else`:

```java
if (flag) {
    System.out.println("A");
} else {
    System.out.println("B");
}
```

## 10. Chọn `var` hay khai báo kiểu tường minh?

| Tình huống | Cách viết nên cân nhắc | Vì sao |
| --- | --- | --- |
| Hai nhánh là chuỗi, cùng ý nghĩa | `var label = flag ? "on" : "off";` | Kiểu `String` rõ từ biểu thức. |
| Hai nhánh là số khác kiểu | `var value = flag ? 1 : 2.5;`, sau khi kiểm tra `double` có đúng ý | Tránh bất ngờ về numeric promotion. |
| Hai implementation cùng một API | `List<String> list = flag ? new ArrayList<>() : new LinkedList<>();` | Khóa rõ contract về interface và generic. |
| Một nhánh `null` | Khai báo kiểu tham chiếu rõ hoặc dùng cách biểu diễn null có chủ đích | Dễ thấy chính sách null tại điểm dùng. |
| Hai nhánh là object thuộc các loại xa nhau | Cân nhắc một interface/DTO chung hoặc tách logic | Giúp API dễ hiểu hơn một kiểu LUB phức tạp. |
| Chỉ muốn chạy một trong hai hành động `void` | `if/else` | `?:` phải sản sinh giá trị phù hợp. |

Quy tắc thực dụng: **dùng `var` khi cả hai nhánh và kiểu kết quả dễ thấy; giữ kiểu tường minh khi kiểu chung, generic hoặc chuyển đổi số là thông tin quan trọng với người đọc.** Không cần loại bỏ `var` khỏi mã Java hiện đại; điều cần làm là hiểu đúng kiểu được suy luận từ biểu thức.

## 11. Câu hỏi tự kiểm tra

**1.** `var x = flag ? 3 : 4L;` có kiểu gì nếu `flag == true`?

**Đáp án:** `long`. Kiểu được xác định từ cả hai nhánh và phép nâng kiểu số, không dựa vào nhánh chạy.

**2.** `var name = flag ? null : "Guest";` có lỗi biên dịch không? Có luôn khác `null` không?

**Đáp án:** Không lỗi; kiểu suy luận là `String`. Tuy nhiên khi `flag == true`, kết quả là `null`.

**3.** Vì sao `List<String> chosen = flag ? new ArrayList<>() : new LinkedList<>();` an toàn hơn `var chosen = flag ? new ArrayList<>() : new LinkedList<>();` nếu danh sách chỉ nhận chuỗi?

**Đáp án:** Kiểu khai báo `List<String>` cung cấp ngữ cảnh suy luận cho diamond constructor và bảo đảm kiểu phần tử. Với `var`, biểu thức khởi tạo không có target type từ bên trái và có thể suy luận kiểu phần tử là `Object`.

**4.** Với `Integer boxed = null; var x = flag ? 1 : boxed;`, tại sao có thể xảy ra NPE?

**Đáp án:** Kết quả numeric conditional có kiểu `int`; nếu chọn nhánh `boxed`, giá trị `Integer null` phải được unbox.

**5.** Có thể dùng `var x = flag ? null : null;` để tạo biến nullable chưa chọn kiểu không?

**Đáp án:** Không. Hai nhánh đều thuộc `null type` và không cung cấp kiểu hữu ích cho `var`; cần một kiểu tham chiếu tường minh.

**6.** Khi điều kiện là `true`, Java có bỏ qua lỗi kiểu ở nhánh còn lại vì nhánh đó không thực thi không?

**Đáp án:** Không. Nhánh không chọn không được đánh giá ở runtime, nhưng compiler vẫn kiểm tra cú pháp và quy tắc kiểu của cả hai nhánh.

## Tài liệu tham khảo chính thức còn áp dụng

- [Java Language Specification, ```15.25 — Conditional Operator `?:`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.25): phân loại boolean/numeric/reference conditional, kiểu kết quả, poly expression và standalone expression.
- [Java Language Specification, ```14.4.1 — Local Variable Declarators and Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4.1): cách xác định kiểu của biến khai báo bằng `var`.
- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): thiết kế tính năng `var` được đưa vào Java 10.
- [OpenJDK Local Variable Type Inference Style Guidelines](https://openjdk.org/projects/amber/guides/lvti-style-guide): hướng dẫn dùng `var` dễ đọc, tránh làm mờ thông tin kiểu.
