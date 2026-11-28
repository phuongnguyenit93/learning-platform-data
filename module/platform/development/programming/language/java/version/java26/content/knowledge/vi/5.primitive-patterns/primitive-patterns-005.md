# instanceof và phép chuyển đổi biểu diễn chính xác

Trong Java truyền thống, `instanceof` chủ yếu kiểm tra quan hệ giữa các kiểu tham chiếu. Từ Java 26, một tính năng preview mở rộng phép kiểm tra này sang kiểu nguyên thủy: chương trình có thể hỏi liệu một giá trị có chuyển sang kiểu nguyên thủy đích mà không làm mất thông tin hay không.

Ví dụ, khi chuyển `int` sang `byte`, phép ép kiểu thông thường luôn tạo ra một giá trị `byte`, kể cả khi giá trị ban đầu nằm ngoài phạm vi của `byte`. Kết quả có thể bị đổi dấu hoặc mất phần dữ liệu. Với primitive `instanceof`, phép kiểm tra chỉ thành công nếu giá trị chuyển đổi chính xác; dạng pattern còn cung cấp luôn biến chứa kết quả đã chuyển đổi.

## 1. Trạng thái tính năng trên các JDK

| JDK | JEP | Trạng thái |
|---|---|---|
| Java 23 | JEP 455 | Preview lần đầu |
| Java 24 | JEP 488 | Preview lần thứ hai |
| Java 25 | JEP 507 | Preview lần thứ ba |
| Java 26 | JEP 530 | Preview lần thứ tư |

Trên JDK 26, primitive types trong patterns, `instanceof` và `switch` vẫn là preview, chưa phải tính năng Java SE final. Bản preview thứ tư tinh chỉnh định nghĩa về chuyển đổi chính xác vô điều kiện và siết quy tắc dominance trong `switch`. Vì thế, không nên mô tả cú pháp này như API ổn định đã được chuẩn hóa.

Tài liệu Java SE 27 hiện cũng liệt kê JEP 532 là lần preview thứ năm. Điều này tiếp tục cho thấy thiết kế còn được đánh giá qua các bản preview. Khi chọn JDK mới hơn, phải kiểm tra JEP và tài liệu ngôn ngữ đúng phiên bản thay vì giả định mã preview của JDK 26 sẽ giữ nguyên.

## 2. Khác biệt giữa ép kiểu và kiểm tra chuyển đổi chính xác

Ép kiểu số nguyên thủy trong Java có thể làm mất thông tin mà không ném `ClassCastException`. Ví dụ:

```java
int original = 2_345_323;
byte narrowed = (byte) original;

System.out.println(narrowed); // 107
```

Giá trị `2_345_323` không thể biểu diễn bằng `byte`, nhưng phép ép kiểu vẫn thực hiện chuyển đổi narrowing và kết quả là `107`. Nếu dữ liệu này là mã trạng thái, số lượng hoặc giá trị tài chính, việc âm thầm thay đổi giá trị có thể gây lỗi khó phát hiện.

Với primitive `instanceof`, phép kiểm tra có thể xác định trước liệu chuyển đổi có giữ nguyên thông tin hay không:

```java
int value = 42;

if (value instanceof byte) {
    System.out.println((byte) value); // 42
}
```

Ở đây `instanceof` được dùng như **toán tử so sánh kiểu**. Nó chỉ trả về `true` hoặc `false`; nó không tự tạo biến và không thực hiện phép ép kiểu để gán cho biến khác. Nếu muốn vừa kiểm tra vừa nhận giá trị đã chuyển đổi, hãy dùng type pattern:

```java
int value = 42;

if (value instanceof byte smallValue) {
    System.out.println(smallValue); // 42, kiểu byte
}
```

Biến `smallValue` chỉ được khởi tạo khi phép chuyển đổi chính xác và điều kiện `instanceof` thành công. Đây là dạng nên ưu tiên khi chương trình cần sử dụng ngay giá trị đích.

## 3. Thế nào là chuyển đổi chính xác?

Một *testing conversion* là chính xác (*exact*) nếu nó tạo ra kết quả mà không mất thông tin và không ném ngoại lệ. Nếu có mất thông tin, phép chuyển đổi là không chính xác (*inexact*), vì vậy phép kiểm tra không khớp.

Thông tin có thể bị mất theo các cách sau:

- **Magnitude:** độ lớn của giá trị thay đổi.
- **Precision:** các bit có nghĩa hoặc phần thập phân bị mất.
- **Range:** giá trị vượt khỏi phạm vi có thể biểu diễn của kiểu đích.
- **Sign:** dấu của giá trị bị thay đổi hoặc bị mất.

Ví dụ với narrowing từ `int` sang `byte`:

```java
int fits = 42;
int tooLarge = 1_000;

System.out.println(fits instanceof byte);     // true
System.out.println(tooLarge instanceof byte); // false

if (tooLarge instanceof byte b) {
    // Không chạy: 1000 không thể biểu diễn chính xác bằng byte.
    System.out.println(b);
}
```

Phạm vi của `byte` là từ `-128` đến `127`. Giá trị `42` nằm trong phạm vi và được giữ nguyên; `1_000` nằm ngoài phạm vi nên không khớp. Phép kiểm tra không trả về giá trị bị tràn như khi ép kiểu.

### 3.1. Chuyển đổi widening cũng có thể mất chính xác

Không phải mọi phép widening đều chính xác. Ví dụ, `int` rộng hơn `float` về độ chính xác số nguyên có thể biểu diễn. `float` có 24 bit độ chính xác nhị phân, nên không thể biểu diễn mọi số nguyên lớn của `int`:

```java
int exactlyRepresentable = 16_777_216;
int losesPrecision = 16_777_217;

System.out.println(exactlyRepresentable instanceof float); // true
System.out.println(losesPrecision instanceof float);       // false
```

`16_777_217` khi chuyển sang `float` bị làm tròn thành một giá trị lân cận. Dù đây là widening primitive conversion theo danh mục chuyển đổi của Java, nó không chính xác với giá trị cụ thể đó.

Ngược lại, chuyển `float` sang `double` là widening chính xác theo kiểu: mọi giá trị `float` đều có thể được biểu diễn trong `double` mà không mất thông tin. Chuyển `long` sang `double` không luôn chính xác vì `double` không thể biểu diễn mọi giá trị nguyên 64 bit.

### 3.2. Chuyển đổi từ số thực sang số nguyên

Khi chuyển `double` hoặc `float` sang kiểu nguyên, phần thập phân có thể bị bỏ và giá trị cũng có thể nằm ngoài phạm vi của kiểu đích. Primitive `instanceof` chỉ thành công khi giá trị đích biểu diễn được chính xác giá trị nguồn:

```java
double whole = 12.0;
double fractional = 12.5;

if (whole instanceof int n) {
    System.out.println(n); // 12
}

System.out.println(fractional instanceof int); // false
```

`12.5` không khớp với `int` vì việc bỏ phần thập phân sẽ làm mất thông tin. Giá trị vô cực, `NaN`, giá trị vượt phạm vi và số không âm có dấu cũng cần được xét theo quy tắc chính xác của JLS; đừng thay kiểm tra này bằng giả định rằng mọi phép ép kiểu số thực sang số nguyên đều an toàn.

## 4. Dùng primitive pattern để nhận giá trị đã chuyển đổi

Pattern giúp kết hợp kiểm tra và binding trong cùng một biểu thức. Điều này tránh phải lặp lại phép ép kiểu sau khi kiểm tra:

```java
static void printAsByte(int input) {
    if (input instanceof byte value) {
        System.out.println("byte hợp lệ: " + value);
    } else {
        System.out.println("Không thể chuyển chính xác sang byte: " + input);
    }
}

static void printAsInt(double input) {
    if (input instanceof int value) {
        System.out.println("int hợp lệ: " + value);
    } else {
        System.out.println("Không thể chuyển chính xác sang int: " + input);
    }
}
```

Pattern variable có kiểu là kiểu nguyên thủy được ghi trong pattern. Biến chỉ nằm trong phạm vi luồng điều khiển mà compiler xác định chắc chắn pattern đã khớp, ví dụ bên trong nhánh `if`. Không thể dùng biến đó sau nhánh nếu nó chưa được khởi tạo trên mọi đường đi.

Primitive pattern hữu ích khi nhận dữ liệu số từ nhiều nguồn và chỉ muốn tiếp tục xử lý nếu dữ liệu phù hợp với kiểu đích. Nó không thay thế validation nghiệp vụ: sau khi chuyển đổi chính xác, ứng dụng vẫn phải kiểm tra giới hạn nghiệp vụ như số lượng không âm, mức tiền tối đa hoặc mã định danh hợp lệ.

## 5. Pattern với wrapper và giá trị null

Tính năng mở rộng còn cho phép kiểm tra chuyển đổi từ wrapper sang primitive thông qua unboxing. Ví dụ:

```java
Integer boxed = 42;

if (boxed instanceof int value) {
    System.out.println(value); // 42
}

Integer missing = null;
System.out.println(missing instanceof int); // false
```

Khi `boxed` chứa một `Integer`, giá trị có thể được unbox sang `int` mà không mất thông tin. Khi wrapper là `null`, phép kiểm tra không khớp; nó không ném `NullPointerException` như một thao tác unboxing trực tiếp. Với nguồn có kiểu tham chiếu rộng hơn như `Object`, việc kiểm tra còn phải xác định được đối tượng runtime có thể chuyển về wrapper thích hợp rồi unbox hay không.

Đừng nhầm primitive pattern với việc kiểm tra lớp wrapper bằng reference pattern:

```java
Object value = Integer.valueOf(42);

if (value instanceof Integer integerValue) {
    // Kiểu biến là Integer; đây là reference type pattern đã ổn định.
}

if (value instanceof int primitiveValue) {
    // Kiểu biến là int; primitive pattern thuộc preview của JDK 26.
}
```

Reference type pattern trong ví dụ đầu đã là tính năng chuẩn từ các bản Java trước. Primitive type pattern ở ví dụ sau cần bật preview trên JDK 26.

## 6. Phân biệt exact theo giá trị và exact vô điều kiện

JLS dùng hai khái niệm để mô tả tính chính xác:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Exact theo giá trị khi chạy | Kết quả của lần chuyển đổi cụ thể không mất thông tin | `int` có giá trị `42` chuyển sang `byte` |
| Type-based unconditionally exact | Chỉ cần biết kiểu nguồn và đích là đủ kết luận mọi giá trị đều chuyển chính xác | `byte` sang `int`, `float` sang `double` |
| Value-based unconditionally exact | Giá trị là constant expression và compiler xác định được lần chuyển đổi cụ thể luôn chính xác | Hằng `42` từ `int` sang `byte` |

Hai dạng *unconditionally exact* quan trọng với compiler khi kiểm tra dominance và tính exhaustive của `switch`. Ví dụ, chuyển `byte` sang `int` luôn chính xác vì mọi giá trị `byte` đều nằm trong phạm vi `int`. Chuyển hằng số `42` từ `int` sang `byte` cũng được compiler biết là chính xác ngay từ compile time, dù chuyển đổi `int` sang `byte` nói chung không chính xác với mọi giá trị.

Phân biệt hai khái niệm này giúp đọc lỗi compile của `switch` dễ hơn: một pattern có thể không bao phủ mọi giá trị nếu phép chuyển đổi của nó có thể mất thông tin. JDK 26 còn tinh chỉnh quy tắc dominance để tránh một pattern đứng trước che khuất nhánh sau trong các trường hợp chuyển đổi không bảo đảm chính xác.

## 7. Tương tác với switch

Primitive patterns là một phần của cùng tính năng preview, không chỉ giới hạn ở `instanceof`. `switch` có thể dùng pattern primitive và kiểm tra chuyển đổi chính xác khi chọn nhánh. Ví dụ từ Java SE 26 Language Guide:

```java
static void showFloat(float value) {
    switch (value) {
        case double widened ->
            System.out.println("Biểu diễn double: " + widened);
    }
}
```

`float` sang `double` luôn chính xác, vì vậy pattern `double` có thể nhận mọi giá trị `float`. Nếu đổi pattern thành `case int narrowed`, phép chuyển đổi có thể làm mất phần thập phân hoặc vượt phạm vi `int`; compiler không thể xem một nhánh như vậy là bao phủ mọi giá trị `float`.

Khi dùng nhiều `case` pattern, phải đặt các nhánh cụ thể trước các nhánh tổng quát phù hợp với quy tắc dominance. Một pattern không thể đứng sau một pattern trước đó đã bao phủ toàn bộ giá trị của nó. Hãy dùng `when` để thêm điều kiện nghiệp vụ khi cần chia nhỏ các trường hợp đã match; guard không biến một phép chuyển đổi inexact thành exact.

## 8. Biên dịch và chạy trên JDK 26

Vì primitive patterns, primitive `instanceof` và các mở rộng `switch` trong JDK 26 vẫn là preview, phải bật preview khi biên dịch và chạy. Dùng đúng JDK 26 cho cả hai bước:

```bash
javac --release 26 --enable-preview PrimitiveInstanceofDemo.java
java --enable-preview PrimitiveInstanceofDemo
```

Nếu dùng Maven hoặc Gradle, cấu hình compiler để bật preview cho source set tương ứng và bảo đảm JVM chạy test/app cũng nhận `--enable-preview`. Chỉ bật cờ compiler là chưa đủ nếu ứng dụng chạy bằng JVM không cho phép preview.

Preview feature được gắn với release cụ thể. Bytecode được biên dịch với preview của JDK 26 phải chạy trên JDK 26 có `--enable-preview`; không thể lấy cờ này làm cam kết tương thích với JDK 25 hoặc JDK 27. Mỗi lần nâng JDK, hãy đọc lại JEP và tài liệu ngôn ngữ của phiên bản mới rồi biên dịch lại mã nguồn.

Nếu dự án cần tương thích Java SE ổn định mà không phụ thuộc preview, hãy dùng cách kiểm tra phạm vi hoặc điều kiện số học tường minh trước khi ép kiểu, hoặc giữ dữ liệu ở kiểu nguyên thủy rộng hơn. Chỉ đưa primitive patterns vào production khi nhóm chấp nhận chính sách preview, có kiểm thử cho đúng JDK và sẵn sàng cập nhật mã khi đặc tả thay đổi.

## 9. Quy tắc áp dụng

- Dùng `instanceof targetPrimitive variable` khi cần kiểm tra và nhận luôn giá trị đã chuyển đổi chính xác.
- Dùng `instanceof targetPrimitive` khi chỉ cần câu trả lời đúng/sai về khả năng chuyển đổi.
- Không dùng ép kiểu narrowing đơn lẻ như một phép validation; phép ép kiểu không chứng minh rằng giá trị được giữ nguyên.
- Với dữ liệu `float`/`double`, cân nhắc cả phần thập phân, phạm vi, `NaN`, vô cực và dấu của zero.
- Với wrapper, nhớ rằng `null` không khớp primitive pattern; kiểm tra null riêng nếu cần phân biệt dữ liệu thiếu với dữ liệu sai kiểu.
- Không coi preview là API final. Ghim JDK, bật preview ở compile và runtime, và kiểm tra lại mỗi lần nâng phiên bản.

## Tài liệu tham khảo

- [JEP 530: Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530)
- [Java SE 26 Language Guide: Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/26/language/primitive-types-patterns-instanceof-switch.html)
- [Java SE 26 Language Guide: Safe Casting with instanceof and switch](https://docs.oracle.com/en/java/javase/26/language/safe-casting-instanceof-switch.html)
- [Java SE 26 JLS Preview Specification: Exactness of Testing Conversions](https://docs.oracle.com/en/java/javase/26/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html)
- [Java Language Changes by Release: Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)
