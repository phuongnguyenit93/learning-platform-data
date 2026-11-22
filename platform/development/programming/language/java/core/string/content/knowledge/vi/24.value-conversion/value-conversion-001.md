# String.valueOf với primitive và Object trong Java

## 1. Mục tiêu bài học

`String.valueOf(...)` là nhóm **phương thức tĩnh** của `java.lang.String` dùng để tạo biểu diễn dạng chuỗi từ một giá trị. Nó đặc biệt hữu ích khi chuyển `boolean`, `char`, các kiểu số nguyên, số thực hoặc một đối tượng sang `String` để hiển thị, ghép thông báo hay đưa vào một API nhận chuỗi.

Sau bài này, bạn sẽ:
- Phân biệt các overload `valueOf` dành cho **primitive**, `Object` và `char[]`.
- Hiểu khi nào giá trị được biểu diễn bằng chuỗi có sẵn, khi nào `toString()` được gọi.
- Giải thích vì sao `String.valueOf((Object) null)` trả `"null"`, còn `String.valueOf((char[]) null)` gây lỗi.
- Biết cách biểu diễn mảng và dữ liệu số khi `valueOf` không đáp ứng định dạng mong muốn.
- Chọn đúng giữa `String.valueOf`, `Objects.toString`, `Integer.toString` và `String.format` theo mục đích.

## 2. Các overload của String.valueOf

Những khai báo thường gặp trong Java 17:

```java
public static String valueOf(boolean b);
public static String valueOf(char c);
public static String valueOf(int i);
public static String valueOf(long l);
public static String valueOf(float f);
public static String valueOf(double d);

public static String valueOf(Object obj);
public static String valueOf(char[] data);
public static String valueOf(char[] data, int offset, int count);
```

Java chọn overload dựa trên **kiểu biểu thức lúc biên dịch** cùng các quy tắc phân giải lời gọi phương thức. Sau đó mỗi overload tạo nội dung chuỗi tương ứng.

| Giá trị đầu vào | Overload điển hình | Ví dụ | Kết quả |
| --- | --- | --- | --- |
| `boolean` | `valueOf(boolean)` | `String.valueOf(true)` | `"true"` |
| `char` | `valueOf(char)` | `String.valueOf('J')` | `"J"` |
| `byte`, `short` | `valueOf(int)` qua mở rộng kiểu | `String.valueOf((byte) 7)` | `"7"` |
| `int` | `valueOf(int)` | `String.valueOf(-42)` | `"-42"` |
| `long` | `valueOf(long)` | `String.valueOf(5000000000L)` | `"5000000000"` |
| `float` | `valueOf(float)` | `String.valueOf(1.25f)` | `"1.25"` |
| `double` | `valueOf(double)` | `String.valueOf(2.5d)` | `"2.5"` |
| `Object` | `valueOf(Object)` | `String.valueOf((Object) null)` | `"null"` |
| `char[]` | `valueOf(char[])` | `String.valueOf(new char[]{'A','B'})` | `"AB"` |

**Không có overload dành riêng cho `byte` và `short`**; đối số primitive tương ứng có thể mở rộng sang `int`. Các kiểu wrapper như `Integer`, `Boolean` hoặc `Double` là **đối tượng** khi bạn truyền một biến có kiểu wrapper; Java có thể chọn overload `Object` thông qua chuyển đổi tham chiếu, và biểu diễn đầu ra thông thường vẫn giống dạng chuỗi của giá trị.

Một trường hợp riêng là **mảng ký tự `char[]`**. Đây không phải kiểu primitive đơn lẻ `char` và được xử lý bằng overload chuyên biệt.

## 3. Chuyển các kiểu primitive

### Boolean: chỉ có "true" và "false"

```java
String yes = String.valueOf(true);    // "true"
String no = String.valueOf(false);    // "false"
```

Đây là hai chuỗi chữ thường theo quy tắc của Java, không phụ thuộc locale. `String.valueOf(boolean)` không dịch sang “Có/Không” hay “Đúng/Sai”; việc bản địa hóa phải thực hiện riêng.

### Char: tạo chuỗi từ một ký tự

```java
char initial = 'K';
String text = String.valueOf(initial); // "K"
```

Một `char` trong Java là một **đơn vị mã UTF-16**, không phải lúc nào cũng đại diện cho một ký tự Unicode hoàn chỉnh. Những ký tự nằm ngoài Basic Multilingual Plane (ví dụ nhiều emoji) cần cặp surrogate; nếu có một code point Unicode, có thể dùng `Character.toChars(codePoint)` rồi tạo chuỗi từ mảng `char[]`.

```java
int codePoint = 0x1F600;
String emoji = String.valueOf(Character.toChars(codePoint));
// Một chuỗi chứa emoji U+1F600
```

### Số nguyên: dạng thập phân có dấu khi cần

```java
String quantity = String.valueOf(125);       // "125"
String negative = String.valueOf(-12L);      // "-12"
String small = String.valueOf((short) 8);    // "8"
```

Định dạng mặc định của `valueOf` cho số nguyên là **hệ thập phân**, không tự thêm dấu phân cách hàng nghìn hoặc số 0 ở đầu. Nếu cần cơ số khác, dùng API phù hợp:

```java
String hex = Integer.toHexString(255); // "ff"
String binary = Integer.toBinaryString(5); // "101"
String base16 = Integer.toString(255, 16); // "ff"
```

### Số thực: biểu diễn mặc định, không phải khuôn mẫu hiển thị cố định

```java
String a = String.valueOf(1.25f); // "1.25"
String b = String.valueOf(2.0d);  // "2.0"
String c = String.valueOf(Double.NaN); // "NaN"
String d = String.valueOf(Double.POSITIVE_INFINITY); // "Infinity"
```

Các overload cho `float` và `double` theo quy tắc biểu diễn chuỗi tương ứng của `Float` và `Double`. Tùy giá trị, kết quả có thể dùng ký pháp khoa học, và số chữ số sau dấu thập phân không phải một số cố định.

Đừng dùng `String.valueOf(12.5)` khi yêu cầu là luôn đúng **hai chữ số thập phân** hoặc dấu nhóm hàng nghìn theo ngôn ngữ. Khi đó dùng `String.format(Locale.US, "%.2f", 12.5)` để được `"12.50"` hoặc `NumberFormat` cho giao diện có locale.

`String.valueOf` chỉ quyết định **biểu diễn**, không làm thay đổi độ chính xác của giá trị `float`/`double` và không giải quyết sai số số học dấu chấm động.

## 4. `String.valueOf(Object)`: biểu diễn đối tượng và xử lý null

Khi đối số có **kiểu tĩnh `Object`**, Java chọn `valueOf(Object)`. Overload này trả chữ `"null"` nếu tham chiếu bằng `null`; nếu khác `null`, nó gọi `toString()` theo lớp thực tế của đối tượng:

```java
Object count = Integer.valueOf(42);
Object missing = null;
System.out.println(String.valueOf(count));   // 42
System.out.println(String.valueOf(missing)); // null
```

Vì kết quả phụ thuộc `toString()`, một đối tượng có thể in mô tả tùy chỉnh hoặc dạng mặc định như `Type@hexHash`. Đây là cách biểu diễn văn bản, không phải serialization hay ép kiểu thành `String`. Gọi `obj.toString()` trực tiếp trên `null` sẽ ném `NullPointerException`.

**Bẫy overload:** `String.valueOf(null)` với **literal null không ép kiểu** chọn overload `char[]` cụ thể hơn `Object`, nên ném `NullPointerException`. Viết `String.valueOf((Object) null)` nếu muốn chữ `"null"`. Bài riêng về `null` của chương giải thích cơ chế phân giải overload theo kiểu tĩnh cùng các trường hợp ép kiểu.

## 5. Overload `char[]`: lấy nội dung ký tự

Khác `Object`, `char[]` được `String.valueOf` xử lý như **dữ liệu văn bản**:

```java
char[] chars = {'J', 'a', 'v', 'a'};
String entire = String.valueOf(chars);       // "Java"
String middle = String.valueOf(chars, 1, 2); // "av"
```

Với overload ba tham số, `offset` là chỉ số bắt đầu, `count` là **số phần tử `char`** lấy từ mảng. Mảng `null` gây `NullPointerException`; phạm vi sai gây `IndexOutOfBoundsException`. Chuỗi đã tạo không thay đổi khi sau đó sửa mảng nguồn. Dữ liệu `char[]` là các đơn vị UTF-16, vì vậy muốn cắt theo Unicode code point phải xác định ranh giới đúng.

`String.valueOf((Object) chars)` chuyển sang overload `Object` và in biểu diễn đối tượng mảng như `[C@...`, **không** phải `"Java"`. Khi tập trung vào thao tác sao chép và lấy đoạn mảng, `String.copyValueOf(char[])` và `new String(char[])` cũng có hợp đồng tạo nội dung chuỗi tương ứng.

## 6. Mảng khác không tự chuyển thành danh sách phần tử

`valueOf(char[])` là overload đặc biệt. Với mảng như `int[]`, `double[]` hoặc `String[]`, lời gọi `valueOf` thông thường nhận `Object`, nên kết quả mặc định mô tả **đối tượng mảng**, không liệt kê phần tử:

```java
int[] ids = {1, 2, 3};
System.out.println(String.valueOf(ids).startsWith("[I@")); // true
System.out.println(java.util.Arrays.toString(ids));        // [1, 2, 3]

int[][] grid = {{1, 2}, {3, 4}};
System.out.println(java.util.Arrays.deepToString(grid));   // [[1, 2], [3, 4]]
```

Dùng `Arrays.toString` để quan sát phần tử mảng một chiều và `Arrays.deepToString` cho mảng đối tượng lồng nhau. Đó là quyết định **định dạng đầu ra**, khác với `valueOf` chỉ dựa trên `toString()` của đối tượng truyền vào.

## 7. Chương trình Java 17+ hoàn chỉnh

Lưu mã sau vào tệp `ValueOfDemo.java` bằng UTF-8:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;

public class ValueOfDemo {
    private record Product(String code, int quantity) {
        @Override
        public String toString() {
            return code + " x " + quantity;
        }
    }

    public static void main(String[] args) {
        System.out.println("boolean: " + String.valueOf(true));
        System.out.println("char: " + String.valueOf('J'));
        System.out.println("int: " + String.valueOf(-42));
        System.out.println("long: " + String.valueOf(5000000000L));
        System.out.println("float: " + String.valueOf(1.25f));
        System.out.println("double: " + String.valueOf(2.5));

        Product p = new Product("P01", 3);
        System.out.println("object: " + String.valueOf(p));

        Object missing = null;
        System.out.println("null object: " + String.valueOf(missing));
        System.out.println("fallback: " +
                Objects.toString(missing, "(trống)"));

        char[] data = {'J', 'a', 'v', 'a'};
        System.out.println("char array: " + String.valueOf(data));
        System.out.println("char slice: " +
                String.valueOf(data, 1, 2));

        String copy = String.valueOf(data);
        data[0] = 'Z';
        System.out.println("copy preserved: " + copy);

        int[] ids = {1, 2, 3};
        System.out.println("array items: " + Arrays.toString(ids));

        System.out.println("formatted: " +
                String.format(Locale.US, "%.2f", 2.5));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 ValueOfDemo.java
java ValueOfDemo
```

Stdout chính xác:

```text
boolean: true
char: J
int: -42
long: 5000000000
float: 1.25
double: 2.5
object: P01 x 3
null object: null
fallback: (trống)
char array: Java
char slice: av
copy preserved: Java
array items: [1, 2, 3]
formatted: 2.50
```

Các dòng minh họa cùng một họ phương thức nhưng nhiều kiểu đầu vào. Ví dụ đối tượng `Product` dùng phương thức `toString()` riêng; `char[]` tạo chuỗi từ nội dung ký tự; `int[]` được in đúng phần tử bằng `Arrays.toString`; `String.format` tạo hai chữ số thập phân, trái với `String.valueOf(2.5)`.

## 8. Chọn giữa `valueOf`, `toString` và `Objects.toString`

| Cách gọi | Đối tượng không null | Đối tượng null |
| --- | --- | --- |
| `String.valueOf(obj)` khi `obj` có kiểu tĩnh `Object` | Dùng `obj.toString()` | Chuỗi `"null"` |
| `obj.toString()` | Gọi trực tiếp `toString()` | `NullPointerException` |
| `Objects.toString(obj)` | Dùng `toString()` | Chuỗi `"null"` |
| `Objects.toString(obj, fallback)` | Dùng `toString()` | Dùng `fallback` (có thể là null) |

Nếu muốn một thông điệp dự phòng có chủ ý, `Objects.toString(value, "(trống)")` rõ nghĩa hơn chữ `"null"`. Với biến đã là `String`, dùng trực tiếp biến thường đơn giản nhất; `String.toString()` trả chính đối tượng chuỗi đó. Bài riêng về `toString()` giải thích chi tiết override, mảng và biểu diễn của từng lớp.

`String.valueOf(obj)` **không tương đương ép kiểu `(String) obj`**: phép ép kiểu yêu cầu đối tượng runtime thật sự là `String` tương thích, trong khi `valueOf` tạo biểu diễn văn bản của đối tượng bất kỳ.

## 9. valueOf trong phép nối chuỗi và StringBuilder

Khi nối chuỗi với toán tử `+`, Java sử dụng quy tắc chuyển đổi sang chuỗi tương ứng với kiểu đối số. Trong nhiều tình huống, bạn **không cần viết `String.valueOf(...)` tường minh**:

```java
int count = 3;
String a = "Số lượng: " + count;
String b = "Số lượng: " + String.valueOf(count);
// Cả a và b đều là "Số lượng: 3"
```

Trình biên dịch/runtime có thể tối ưu phép nối chuỗi; đừng giả định mã bytecode của mọi phiên bản Java đều gọi đúng một overload `String.valueOf`. Điều cần hiểu ở mức ngôn ngữ là **quy tắc kết quả**, không phụ thuộc một cách cài đặt bytecode cụ thể.

Với nhiều bước ghép trong vòng lặp, `StringBuilder` hữu ích:

```java
StringBuilder builder = new StringBuilder();
builder.append("ID=").append(12).append(", active=").append(true);
String result = builder.toString();
// "ID=12, active=true"
```

`StringBuilder.append(...)` cũng có overload cho primitive và Object. Không cần chuyển từng giá trị bằng `String.valueOf` trước rồi mới `append`, trừ khi bạn muốn kiểm soát biểu diễn cụ thể.

## 10. Khi nào cần formatter hoặc converter chuyên biệt?

### Giá trị số có yêu cầu trình bày

```java
import java.util.Locale;

double amount = 1234.5;

String raw = String.valueOf(amount); // "1234.5"
String fixed = String.format(Locale.US, "%,.2f", amount);
// "1,234.50"
```

`String.valueOf` không tự phân nhóm hàng nghìn, không tự chọn đơn vị tiền tệ và không theo locale. Với số tiền, thường cần `BigDecimal` để tính toán chính xác và `NumberFormat` hoặc một format policy rõ ràng để hiển thị.

### Chuyển String ngược lại thành primitive

`String.valueOf(42)` chuyển **int → String**, còn `Integer.parseInt("42")` chuyển **String → int**; đây là hai hướng khác nhau.

```java
String text = String.valueOf(42); // "42"
int back = Integer.parseInt(text); // 42
```

Nếu dữ liệu không hợp lệ, `Integer.parseInt(...)` có thể ném `NumberFormatException`. `valueOf` không kiểm tra xem một chuỗi bất kỳ có phải là số hợp lệ không, vì bản thân nó đang chuyển từ một giá trị có kiểu sang văn bản.

### Chuyển String thành đối tượng nghiệp vụ

Đối với đối tượng có `toString()` tùy biến, không mặc nhiên có phép đảo `String.valueOf(object)` thành lại object. Muốn chuyển ngược, cần parser/factory thích hợp hoặc định dạng serialization có quy tắc rõ ràng.

## 11. Những lỗi phổ biến

**1. Gọi `String.valueOf(null)` và kỳ vọng `"null"`.** Vì có overload `char[]`, biểu thức literal null có thể chọn overload đó và ném `NullPointerException`. Viết `String.valueOf((Object) null)` hoặc dùng biến `Object` nếu mục tiêu là văn bản `"null"`.

**2. Cho rằng mọi mảng đều được in phần tử.** `char[]` có overload riêng, còn `int[]`/`String[]` dùng `Object.toString()`. Hãy chọn `Arrays.toString` hoặc `Arrays.deepToString` khi cần nhìn thấy phần tử.

**3. Dùng `toString()` trực tiếp khi dữ liệu có thể null.** `String.valueOf((Object) ref)` an toàn trước null theo nghĩa trả `"null"`; `ref.toString()` có thể ném `NullPointerException`.

**4. Cho rằng `String.valueOf(double)` luôn có hai chữ số thập phân.** Số thực được biểu diễn theo quy tắc mặc định. Muốn fixed precision, dấu nhóm hoặc locale, cần formatter.

**5. Dùng `String.valueOf(obj)` như thao tác ép kiểu.** Phương thức trả String biểu diễn đối tượng; nó không trả về đối tượng ban đầu được ép thành String.

**6. Để `toString()` của đối tượng chứa dữ liệu không mong muốn.** `valueOf(Object)` tuân theo `toString()` và có thể in tên lớp + mã băm, hoặc nội dung nhạy cảm do lớp tự định nghĩa. Hãy thiết kế `toString()` có chủ đích và thận trọng khi log.

**7. Trộn biểu diễn kỹ thuật và biểu diễn cho người dùng.** `true/false`, dấu thập phân và cách hiển thị object của `valueOf` không tự thích ứng ngôn ngữ hay quy tắc giao diện.

**8. Nhầm tham số `count` với chỉ số cuối khi cắt `char[]`.** `String.valueOf(chars, 1, 2)` lấy **2 ký tự**, bắt đầu từ index `1`.

## 12. Bài tập tự luyện

### Bài 1. Dự đoán kết quả

```java
String a = String.valueOf(false);
String b = String.valueOf((byte) -5);
String c = String.valueOf(10.0d);
String d = String.valueOf('Z');
```

Đáp án: `a = "false"`, `b = "-5"`, `c = "10.0"`, `d = "Z"`.

### Bài 2. Phân biệt null

Xét các lời gọi sau (không thực hiện đồng thời nếu dòng có thể ném ngoại lệ):

```java
Object x = null;
char[] y = null;

String a = String.valueOf(x);
String b = String.valueOf((Object) null);
// String c = String.valueOf(y);
// String d = String.valueOf(null);
```

Đáp án: `a` và `b` là chuỗi `"null"`. Các lời gọi ở hai dòng cuối, nếu bỏ comment, có thể ném `NullPointerException` vì overload `char[]` được chọn.

### Bài 3. Cắt mảng ký tự

Cho `char[] chars = {'s','t','r','i','n','g'};`. Tạo chuỗi `"rin"` mà không cần vòng lặp.

```java
char[] chars = {'s', 't', 'r', 'i', 'n', 'g'};
String answer = String.valueOf(chars, 2, 3);
// "rin"
```

### Bài 4. In nội dung mảng số nguyên

Vì sao `String.valueOf(new int[]{10, 20})` không trả `"[10, 20]"`?

Đáp án: không có overload `int[]`; mảng được chuyển qua `Object` và biểu diễn mặc định không liệt kê phần tử. Dùng:

```java
String result = java.util.Arrays.toString(new int[]{10, 20});
// "[10, 20]"
```

### Bài 5. Định dạng số thực

Yêu cầu hiển thị `2.5` thành `"2.50"` trên mọi máy, cách nào phù hợp?

```java
String result = String.format(
        java.util.Locale.US, "%.2f", 2.5);
// "2.50"
```

Lý do: `valueOf(double)` không có tham số số chữ số thập phân, còn formatter có.

## 13. Ghi nhớ

- **`String.valueOf(...)` là phương thức tĩnh**, trả chuỗi biểu diễn giá trị đầu vào.
- Có overload cho **boolean, char, int, long, float, double, Object, char[]** và một đoạn `char[]`.
- **`byte`/`short` primitive** có thể đi qua `valueOf(int)` bằng mở rộng kiểu.
- **`String.valueOf(Object)`**: khác null thì dùng `toString()`; null thì trả chuỗi chữ `"null"`.
- **Literal `null` không ép kiểu** có thể chọn `char[]` và gây `NullPointerException`. Khi cần overload Object, hãy chỉ rõ kiểu.
- **`char[]`** được chuyển từ các ký tự; **mảng khác** không tự in phần tử. Dùng `Arrays.toString`/`deepToString` khi thích hợp.
- **`valueOf` không phải công cụ format theo locale, serialize dữ liệu hay parse chuỗi.** Chọn `String.format`, `NumberFormat`, `Integer.parseInt` hoặc serializer phù hợp khi có yêu cầu đó.

Tài liệu tham khảo: [Java SE 17 — String.valueOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#valueOf(java.lang.Object)), [Java SE 17 — Object.toString](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#toString()), [Java SE 17 — Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html), [Java SE 17 — Objects.toString](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#toString(java.lang.Object,java.lang.String)).
