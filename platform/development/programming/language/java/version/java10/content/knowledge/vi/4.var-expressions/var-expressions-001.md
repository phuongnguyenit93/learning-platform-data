# Java 10 – Suy luận kiểu từ literal số nguyên, số thực, boolean và chuỗi

> **Phạm vi:** Java 10 → `var và biểu thức` → `Suy luận kiểu từ literal số nguyên, số thực, boolean và chuỗi`. Tập trung vào những quy tắc ngôn ngữ Java còn áp dụng trên Java 17+ và các JDK hiện đại. `var` được giới thiệu ở Java 10 (JEP 286); quy tắc về kiểu của literal và phép toán là quy tắc của ngôn ngữ Java, không phải kiểu dữ liệu tự thay đổi lúc chạy.

## 1. Mục tiêu

Sau bài học, bạn có thể:

1. Xác định chính xác kiểu suy luận của `var x = ...` với literal số nguyên, số thực, `true`/`false` và chuỗi ký tự.
2. Dự đoán tác động của hậu tố `L`, `F`, `D`, tiền tố `0b`/`0x`, dấu gạch dưới trong số, và biểu thức chứa nhiều toán hạng.
3. Phân biệt số nguyên `1` với số thực `1.0`, primitive `boolean` với `Boolean`, chuỗi `"A"` với ký tự `'A'`.
4. Phát hiện lỗi biên dịch do literal vượt miền giá trị hoặc phép gán không đúng kiểu, cũng như lỗi logic do phép chia số nguyên.
5. Viết và chạy chương trình Java 17+ để tự quan sát kiểu **tại thời điểm biên dịch** thông qua overload phương thức.

## 2. Cơ chế: `var` suy luận kiểu từ biểu thức khởi tạo

Từ Java 10, có thể khai báo biến cục bộ theo hai cách sau:

~~~java
int count = 42;  // kiểu khai báo tường minh: int
var size = 42;   // trình biên dịch suy luận: int
~~~

Ở cách thứ hai, trình biên dịch xem **toàn bộ biểu thức bên phải dấu `=`**, xác định kiểu của biểu thức đó theo các quy tắc của Java, rồi gán kiểu tĩnh ấy cho biến `size`. `var` không phải tên của một kiểu runtime, không phải `Object` mặc định và không làm Java trở thành ngôn ngữ có kiểu động.

~~~java
var count = 42;       // count: int
count = 100;          // OK
// count = 100L;      // LỖI biên dịch: long không tự ép hẹp xuống int
// count = "100";     // LỖI biên dịch: String không thể gán cho int
~~~

Dấu `=` ở các lệnh gán tiếp theo **không kích hoạt suy luận kiểu lại**. Giá trị có thể thay đổi nếu biến không `final`; **kiểu khai báo** thì vẫn như cũ.

Điểm quan trọng khi đọc `var`: **kiểu suy luận phụ thuộc biểu thức**, chứ không phụ thuộc tên biến, số có vẻ nhỏ hay lớn về mặt ý nghĩa nghiệp vụ, hoặc kiểu mà người viết “muốn” sử dụng về sau. Ví dụ `var taxRate = 2;` là `int` ngay cả khi tên `taxRate` gợi ý số thực.

### 2.1. Bảng tóm tắt cần nhớ

| Biểu thức khởi tạo | Kiểu suy luận | Nguyên nhân |
| --- | --- | --- |
| `var a = 42;` | `int` | Literal số nguyên thập phân không có `L` mặc định là `int` |
| `var b = 42L;` | `long` | Hậu tố `L` chỉ định literal `long` |
| `var c = 3.14;` | `double` | Literal số thực không có hậu tố mặc định là `double` |
| `var d = 3.14f;` | `float` | Hậu tố `f`/`F` chỉ định `float` |
| `var e = 3.14d;` | `double` | Hậu tố `d`/`D` chỉ định `double` |
| `var f = 1e3;` | `double` | Dạng mũ thập phân không hậu tố vẫn là `double` |
| `var g = true;` | `boolean` | Literal boolean có kiểu nguyên thủy `boolean` |
| `var h = false;` | `boolean` | Tương tự với `false` |
| `var i = "Java";` | `String` | Literal chuỗi có kiểu `java.lang.String` |
| `var j = 'J';` | `char` | Một ký tự trong dấu nháy đơn là literal `char` |
| `var k = 1 / 2;` | `int` | Hai toán hạng số nguyên cho phép chia nguyên |
| `var m = 1 / 2.0;` | `double` | Có toán hạng `double` nên kết quả là `double` |
| `var n = 1 + 2L;` | `long` | Numeric promotion nâng phép cộng lên `long` |
| `var o = "Java " + 10;` | `String` | Phép cộng có toán hạng chuỗi là nối chuỗi |

Bảng nêu **kiểu tĩnh** chứ không suy diễn kiểu qua tên lớp của object sau khi primitive được autoboxing.

## 3. Literal số nguyên: mặc định `int`

Một literal thập phân như `0`, `7`, `42` hoặc `1_000_000` có kiểu `int` khi không có hậu tố `L`. Khoảng giá trị của `int` là từ `-2_147_483_648` đến `2_147_483_647`.

~~~java
var zero = 0;                 // int
var count = 12;               // int
var million = 1_000_000;      // int
var max = 2_147_483_647;      // int
~~~

**Số nhỏ không tự trở thành `byte` hoặc `short`.** Ví dụ `var small = 12;` có kiểu `int`. Nếu thực sự cần loại primitive nhỏ hơn, có thể dùng kiểu tường minh hoặc ép kiểu có chủ đích:

~~~java
byte smallByte = 12;          // Java cho phép thu hẹp hằng int khi giá trị hợp lệ
var inferredByte = (byte) 12; // byte nhờ biểu thức ép kiểu
var inferredShort = (short) 12; // short
~~~

Đừng tự động ép kiểu nhỏ chỉ để tiết kiệm vài byte khi viết code nghiệp vụ. Hãy chọn theo hợp đồng API, dữ liệu nhị phân, giao thức hoặc cấu trúc lưu trữ cần thiết.

### 3.1. Literal `long` cần hậu tố `L`

~~~java
var id = 42L;                     // long dù giá trị 42 vẫn vừa int
var huge = 3_000_000_000L;        // long; giá trị vượt int
var upper = 9_223_372_036_854_775_807L; // long lớn nhất
~~~

Nếu viết `var huge = 3_000_000_000;` (không có `L`), đây là lỗi biên dịch: literal thập phân vượt giới hạn `int`. Java không tự thử lần lượt `int` rồi `long` theo kích thước số. Phải chỉ rõ `L`; nên dùng **`L` viết hoa** để không nhầm với số `1`.

Giới hạn `long` là từ `-9_223_372_036_854_775_808` đến `9_223_372_036_854_775_807`. Phân biệt quy tắc literal với cách viết biểu thức âm (toán tử `-` được áp dụng sau): giá trị nhỏ nhất có dạng đặc biệt `-2147483648` với `int` hoặc `-9223372036854775808L` với `long`. Trong code dễ đọc, dùng `Integer.MIN_VALUE` và `Long.MIN_VALUE` khi cần ranh giới.

**Sai thường gặp:** Viết `var amount = 10_000_000_000;` rồi mong Java tự suy luận `long`. Hãy viết `10_000_000_000L` hoặc dùng phương thức/API trả `long`.

### 3.2. Hệ cơ số không đổi quy tắc suy luận

Java hỗ trợ các cách viết số nguyên:

~~~java
var decimal = 10;          // int, thập phân
var binary = 0b1010;       // int, nhị phân: 10
var hexadecimal = 0xA;     // int, thập lục phân: 10
var binaryLong = 0b1010L;  // long, do hậu tố L
~~~

Dạng nhị phân và thập lục phân vẫn được phân loại là `int` hoặc `long` theo quy tắc literal; **không** có kiểu `binary` hay `hex` trong Java. Một số mẫu bit hex lớn có bit dấu bật có thể được diễn giải dưới dạng `int` âm hoặc `long` âm, nên đừng lấy dạng in thập phân để suy luận kiểu/bit width khi xử lý bit mask.

Các số bắt đầu bằng `0` như `012` là literal **bát phân**, khác số thập phân `12`; trong ứng dụng thông thường nên tránh số 0 đứng đầu không cần thiết vì dễ đọc nhầm. Dấu gạch dưới chỉ để phân nhóm chữ số, ví dụ `1_000_000`, không thay đổi giá trị hay kiểu. Không đặt `_` ở đầu/cuối literal, sát dấu chấm thập phân hoặc ở vị trí tách sai cấu trúc token.

## 4. Literal số thực: mặc định `double`

Literal có dấu chấm hoặc dạng số mũ, chẳng hạn `1.0`, `0.5`, `3.14` hay `1e3`, mặc định có kiểu `double`.

~~~java
var price = 3.14;      // double
var integerLooking = 5.0; // double dù phần thập phân bằng 0
var exponent = 1e3;    // double, giá trị 1000.0
var doubleExplicit = 2.5D; // double
~~~

Muốn literal `float`, ghi hậu tố `f`/`F`:

~~~java
var ratio = 0.75f;       // float
var velocity = 1.25F;    // float
var precision = 0.75d;  // double
~~~

Tổng quát:

| Cách viết | Kiểu | Ghi chú |
| --- | --- | --- |
| `1` | `int` | Số nguyên, không chứa dấu chấm |
| `1L` | `long` | Số nguyên có hậu tố |
| `1.0` | `double` | Số thực mặc định |
| `1.0d` hoặc `1.0D` | `double` | Chỉ rõ double |
| `1.0f` hoặc `1.0F` | `float` | Chỉ rõ float |
| `1e3` | `double` | Ký pháp khoa học, giá trị 1000.0 |
| `1e3F` | `float` | Ký pháp khoa học có hậu tố float |
| `0x1.8p1` | `double` | Số thực hệ hex, mũ nhị phân: giá trị 3.0 |

Không phải cứ “có một số thập phân nhỏ” thì Java suy luận `float`. Ví dụ `var average = 0.5;` luôn có kiểu `double`, còn `var average = 0.5f;` có kiểu `float`.

### 4.1. Giá trị gần đúng của `float` và `double`

`float` (binary32) và `double` (binary64) biểu diễn số thực theo dấu phẩy động nhị phân. Nhiều số thập phân không có biểu diễn nhị phân hữu hạn, nên phép tính có thể làm lộ sai số:

~~~java
var sum = 0.1 + 0.2; // double
System.out.println(sum); // 0.30000000000000004
~~~

`double` thường có nhiều độ chính xác và dải số lớn hơn `float`, nhưng **không** bảo đảm tính toán thập phân chính xác tuyệt đối. Với tiền tệ hoặc phép tính thập phân yêu cầu độ chính xác và quy tắc làm tròn xác định, cân nhắc `BigDecimal` từ chuỗi hoặc các giá trị nguyên biểu diễn đơn vị nhỏ nhất:

~~~java
var amount = new java.math.BigDecimal("0.1")
        .add(new java.math.BigDecimal("0.2"));
System.out.println(amount); // 0.3
~~~

Đây là **suy luận từ biểu thức constructor trả kiểu `BigDecimal`**, không phải suy luận từ literal `double`. Không nên tạo `BigDecimal` bằng `new BigDecimal(0.1)` khi muốn đúng giá trị thập phân `0.1` vì phép tạo này nhận một `double` vốn đã xấp xỉ.

## 5. Literal boolean: `true` và `false` có kiểu `boolean`

~~~java
var active = true;     // boolean nguyên thủy
var expired = false;   // boolean nguyên thủy
var allowed = 10 > 3;  // boolean, kiểu kết quả của phép so sánh
~~~

Java không dùng số nguyên `0`/`1` như boolean một cách ngầm định. `var condition = 1;` tạo `int`, không dùng trực tiếp làm điều kiện `if (condition)` được.

Đặc biệt, **`true` là literal boolean**, còn **`"true"` là String**:

~~~java
var enabled = true;     // boolean
var enabledText = "true"; // String
// enabled = "false";    // lỗi biên dịch: String không gán được cho boolean
~~~

Nếu dữ liệu đến từ form, cấu hình hoặc JSON, hãy phân biệt rõ bước parse với literal:

~~~java
var fromText = Boolean.parseBoolean("true"); // boolean, giá trị true
var boxed = Boolean.valueOf(true);           // Boolean object, không phải boolean primitive
~~~

`Boolean.parseBoolean` trả `true` (không phân biệt hoa/thường) khi văn bản bằng `"true"`; các chuỗi khác trả `false`, vì thế phải kiểm tra riêng nếu nghiệp vụ yêu cầu xác thực chặt chuỗi đầu vào. `Boolean.valueOf` trả object kiểu `Boolean`. `var` giữ đúng kiểu biểu thức initializer: primitive hay wrapper.

## 6. Literal chuỗi: dấu nháy kép tạo `String`

~~~java
var language = "Java";     // java.lang.String
var empty = "";            // String rỗng
var versionName = "Java 10"; // String
var letter = 'J';          // char (nháy đơn), không phải String
var oneCharText = "J";     // String (nháy kép)
~~~

`String` là class bất biến: không có thao tác thay đổi nội dung của cùng object, nhưng **biến** `var language` vẫn có thể gán tham chiếu String khác nếu không có `final`.

~~~java
var title = "Java";
title = title + " 10";          // hợp lệ: title vẫn có kiểu String
System.out.println(title);    // Java 10
// title = 10;                 // lỗi biên dịch: int không gán cho String
~~~

Đừng nhầm độ dài và kiểu: `""` là `String` dài 0; `"A"` là `String` dài 1; `'A'` mới là `char`. Dấu nháy đơn và kép có ý nghĩa cú pháp khác nhau. Chuỗi có escape như `"A\nB"` vẫn có kiểu `String`; Java không tự phân tích chuỗi số `"123"` thành `int` chỉ vì nội dung trông như số.

### 6.1. Nối chuỗi và thứ tự thực hiện

Toán tử `+` có hành vi nối chuỗi khi một toán hạng là `String`. Kết quả biểu thức cũng là `String`:

~~~java
var result = "Count: " + 10;    // String: "Count: 10"
var a = "Count: " + 1 + 2;      // String: "Count: 12"
var b = "Count: " + (1 + 2);    // String: "Count: 3"
~~~

Dấu ngoặc thay đổi biểu thức được tính trước. Với `a`, phép `+` kết hợp từ trái sang phải: `"Count: " + 1` đã tạo String, rồi nối tiếp `2`; với `b`, `1 + 2` là phép cộng số nguyên trước khi nối chuỗi.

Không dùng nối chuỗi để đổi kiểu của biến `int`:

~~~java
var number = 10;           // int
var description = "" + number; // String mới
// number = description;   // lỗi biên dịch
~~~

Khi xây dựng thông điệp phức tạp, có thể dùng `String.format`, `formatted` hoặc StringBuilder tùy yêu cầu; cơ chế suy luận kiểu vẫn dựa trên kiểu trả về của biểu thức.

## 7. Biểu thức mới là đối tượng được suy luận – tránh nhầm với từng literal

`var` không chỉ nhìn “literal cuối cùng” hoặc “literal đầu tiên”. Nó nhìn **kiểu của toàn bộ biểu thức khởi tạo** sau khi các toán tử và quy tắc chuyển kiểu được áp dụng.

### 7.1. Chia nguyên và chia số thực

~~~java
var q1 = 1 / 2;           // int: giá trị 0
var q2 = 1 / 2.0;         // double: giá trị 0.5
var q3 = 1.0f / 2;        // float: giá trị 0.5f
var q4 = (double) 1 / 2;  // double: giá trị 0.5
var q5 = (double) (1 / 2); // double: giá trị 0.0
~~~

Vì cả hai toán hạng `1` và `2` đều `int`, biểu thức `1 / 2` thực hiện **phép chia nguyên** trước khi `var` suy luận `int`. Nếu ép kiểu sau phép chia thì phần lẻ đã mất. Muốn kết quả số thực, cần làm cho ít nhất một toán hạng có kiểu số thực **trước khi chia**, chẳng hạn `1.0 / 2`.

### 7.2. Numeric promotion trong phép toán

~~~java
var a = 1 + 2;        // int: 3
var b = 1 + 2L;       // long: 3
var c = 1 + 2.0f;     // float: 3.0
var d = 1 + 2.0;      // double: 3.0
var e = 1.0f + 2.0;   // double: 3.0 (double chi phối float)
~~~

Trong các toán tử số học nhị phân thông thường, Java áp dụng **binary numeric promotion**: nếu có `double` thì kết quả `double`; nếu không có `double` mà có `float` thì `float`; tiếp theo `long`; còn lại `int` (các loại `byte`, `short` và `char` thường được nâng lên `int`). `var` suy luận theo **kiểu kết quả** này.

~~~java
var character = 'A';     // char
var nextCode = 'A' + 1;  // int do numeric promotion, giá trị 66
~~~

Hãy phân biệt phần “định kiểu literal” với phần “định kiểu biểu thức”. Một literal `'A'` có kiểu `char`, nhưng biểu thức `'A' + 1` trả `int`.

### 7.3. Điều kiện và toán tử ba ngôi

~~~java
var safe = 10 > 0;         // boolean
var amount = true ? 1 : 2; // int
var label = safe ? "yes" : "no"; // String
~~~

Toán tử `?:` có các quy tắc xác định kiểu riêng dựa trên hai nhánh và ngữ cảnh; với các ví dụ trên, kiểu là `int` hoặc `String`. Với các nhánh khác kiểu, đặc biệt số nguyên, wrapper, null hoặc generic, hãy kiểm tra quy tắc Java Language Specification hoặc khai báo kiểu tường minh để tránh suy luận không như mong muốn.

## 8. Những trường hợp literal dễ làm sai suy luận

| Viết như sau | Kết quả/nhận xét | Cách làm đúng khi cần |
| --- | --- | --- |
| `var n = 127;` và nghĩ là `byte` | Suy luận `int` | `byte n = 127;` hoặc `var n = (byte) 127;` |
| `var n = 3_000_000_000;` | Lỗi: literal thập phân vượt `int` | `var n = 3_000_000_000L;` |
| `var rate = 5;` và đợi số thực | `rate` là `int` | `var rate = 5.0;` |
| `var ratio = 1 / 2;` | Suy luận `int`, giá trị `0` | `var ratio = 1.0 / 2;` |
| `var precision = 0.1;` và nghĩ là `float` | Suy luận `double` | `var precision = 0.1f;` nếu thực sự muốn `float` |
| `var ok = "true";` | `String`, không phải `boolean` | `var ok = true;` hoặc parse text |
| `var c = "A";` và nghĩ là `char` | `String` | `var c = 'A';` |
| `var s = 1 + "2";` | `String` chứa `"12"` | Dùng toán học trước nếu muốn cộng số |
| `var n = null;` | Không suy ra được kiểu; lỗi biên dịch | Khai báo `String n = null;` hoặc `var n = (String) null;` |
| `var n;` | Thiếu initializer; lỗi biên dịch | `var n = 0;` hoặc dùng kiểu tường minh |
| `var n = 1; n = 1L;` | Lỗi phép gán `long` sang `int` | Khởi tạo `var n = 1L;` nếu cần long |
| `var n = Integer.valueOf(7);` | Suy luận `Integer`, không phải `int` | Dùng literal `7` nếu cần `int` |

Lưu ý: `var n = (String) null;` hợp lệ về cú pháp vì biểu thức đã mang kiểu `String`, nhưng nếu sử dụng `n` mà không kiểm tra null vẫn có nguy cơ `NullPointerException`. Không nên dùng cast chỉ để “qua” quy tắc suy luận nếu code có thể khai báo kiểu rõ ràng và xử lý null tốt hơn.

### 8.1. `var` và ép kiểu

Ép kiểu là một phần của **biểu thức initializer**, do đó có thể chủ động thay kiểu suy luận:

~~~java
var a = 10;               // int
var b = (long) 10;        // long
var c = (float) 10;       // float
var d = (double) (1 + 2); // double, giá trị 3.0
var e = (byte) 10;        // byte
~~~

Nhưng ép kiểu không tự sửa lỗi logic: `(double) (1 / 2)` vẫn ra `0.0` vì phần chia nguyên đã xảy ra rồi.

### 8.2. Primitive và boxed wrapper

~~~java
var primitive = 7;               // int
var wrapper = Integer.valueOf(7); // Integer
var logical = true;              // boolean
var logicalWrapper = Boolean.TRUE; // Boolean
~~~

Kiểu của `var` xuất phát từ **kiểu tĩnh initializer**. Autoboxing có thể diễn ra khi gọi API hoặc gán trong ngữ cảnh khác, nhưng không nên dùng `variable.getClass()` để suy đoán kiểu nguyên thủy: primitive không gọi phương thức trực tiếp, còn khi truyền qua kiểu `Object` có thể đã bị boxed.

Nếu kiểu wrapper có thể mang giá trị `null`, unboxing tự động trong phép toán có thể gây `NullPointerException`. Dùng primitive khi không cần trạng thái nullable và phù hợp với API.

## 9. Chương trình kiểm chứng đầy đủ trên Java 17+

Chương trình sau dùng **overload phương thức** để minh họa kiểu tĩnh mà trình biên dịch xác định. Mỗi overload nhận đúng một kiểu; Java chọn overload dựa trên kiểu của biến tại **compile time**, vì vậy cách kiểm tra này dễ hiểu hơn việc ép các primitive thành `Object` rồi hỏi `getClass()`.

Lưu tệp với tên chính xác **`LiteralInferenceDemo.java`**:

~~~java
public class LiteralInferenceDemo {
    private static void show(String label, int value) {
        System.out.println(label + " -> int: " + value);
    }
    private static void show(String label, long value) {
        System.out.println(label + " -> long: " + value);
    }
    private static void show(String label, float value) {
        System.out.println(label + " -> float: " + value);
    }
    private static void show(String label, double value) {
        System.out.println(label + " -> double: " + value);
    }
    private static void show(String label, boolean value) {
        System.out.println(label + " -> boolean: " + value);
    }
    private static void show(String label, String value) {
        System.out.println(label + " -> String: " + value);
    }
    private static void show(String label, char value) {
        System.out.println(label + " -> char: " + value);
    }
    private static void show(String label, Integer value) {
        System.out.println(label + " -> Integer: " + value);
    }
    public static void main(String[] args) {
        var integer = 42;
        var large = 3_000_000_000L;
        var binary = 0b1010;
        var hex = 0xFF;
        var decimal = 3.5;
        var singlePrecision = 3.5f;
        var exponent = 1e3;
        var truth = true;
        var comparison = 10 > 3;
        var text = "Java";
        var sentence = "Java " + 10;
        var letter = 'J';
        var intDivision = 1 / 2;
        var doubleDivision = 1 / 2.0;
        var promoted = 1 + 2L;
        var sum = 0.1 + 0.2;
        var boxed = Integer.valueOf(7);
        integer = 43;

        show("integer", integer);
        show("large", large);
        show("binary", binary);
        show("hex", hex);
        show("decimal", decimal);
        show("singlePrecision", singlePrecision);
        show("exponent", exponent);
        show("truth", truth);
        show("comparison", comparison);
        show("text", text);
        show("sentence", sentence);
        show("letter", letter);
        show("intDivision", intDivision);
        show("doubleDivision", doubleDivision);
        show("promoted", promoted);
        show("sum", sum);
        show("boxed", boxed);
    }
}
~~~

Dùng JDK 17+ và chạy tại thư mục chứa file:

~~~bash
javac --release 17 LiteralInferenceDemo.java
java LiteralInferenceDemo
~~~

**Stdout chính xác** của mã trên (đã biên dịch và chạy thử):

~~~text
integer -> int: 43
large -> long: 3000000000
binary -> int: 10
hex -> int: 255
decimal -> double: 3.5
singlePrecision -> float: 3.5
exponent -> double: 1000.0
truth -> boolean: true
comparison -> boolean: true
text -> String: Java
sentence -> String: Java 10
letter -> char: J
intDivision -> int: 0
doubleDivision -> double: 0.5
promoted -> long: 3
sum -> double: 0.30000000000000004
boxed -> Integer: 7
~~~

Giải thích từng nhóm:

- `integer` in `43` vì sau khi suy luận `int` vẫn được phép **gán lại** giá trị `42` thành `43`.
- `large` có hậu tố `L` và thuộc `long`; `binary`/`hex` chỉ đổi cách biểu diễn literal, vẫn là `int`.
- `decimal` và `exponent` mang kiểu `double`; `singlePrecision` có hậu tố `f` nên là `float`.
- `truth` và `comparison` đều là `boolean`; trong một trường hợp nguồn là literal, trường hợp còn lại là biểu thức so sánh.
- `text` và `sentence` là `String`; `letter` là `char` do dùng dấu nháy đơn.
- `intDivision` thực hiện phép chia nguyên và cho `0`; `doubleDivision` ra `0.5`.
- `promoted` là `long` vì có toán hạng `2L`; `sum` là `double` nhưng không biểu diễn chính xác phép cộng thập phân `0.1 + 0.2`.
- `boxed` suy luận là class `Integer` do `Integer.valueOf`; overload `show(String, Integer)` được chọn thay vì overload `int`.

Trong bài này, `show` có nhiều overload để dạy kiểu; code sản xuất không cần tự viết nhiều overload chỉ để in kiểu biến.

## 10. Những đoạn mã không biên dịch và cách sửa

Các đoạn dưới đây **minh họa lỗi**, không phải chương trình Java độc lập. Không copy nguyên các dòng bị đánh dấu lỗi vào tệp chạy thử.

### 10.1. Không suy luận được kiểu từ `null`

~~~java
// var value = null;       // lỗi biên dịch: không suy luận được kiểu
String value = null;       // cú pháp hợp lệ, nhưng phải xử lý null khi sử dụng
~~~

### 10.2. Không có biểu thức khởi tạo

~~~java
// var count;              // lỗi biên dịch: var cần initializer
int count;                 // biến cục bộ có thể khai báo trước
count = 10;                // phải được gán trước khi đọc
~~~

### 10.3. Literal vượt miền `int`

~~~java
// var count = 3_000_000_000; // lỗi: literal thập phân vượt int
var count = 3_000_000_000L;   // đúng: long
~~~

### 10.4. Kiểu biến không đổi sau một phép gán

~~~java
var count = 1;     // int
// count = 2L;     // lỗi: long không gán ngầm về int
count = 2;         // đúng
~~~

### 10.5. String không tự thành boolean hoặc số nguyên

~~~java
var text = "true";               // String
// if (text) { }                 // lỗi: điều kiện if cần boolean/Boolean
var flag = Boolean.parseBoolean(text); // boolean

var numberText = "123";          // String
var number = Integer.parseInt(numberText); // int
~~~

`Integer.parseInt` có thể ném `NumberFormatException` nếu nội dung không đúng định dạng số nguyên; nên kiểm soát dữ liệu đầu vào trước khi parse. Việc parse là hoạt động **runtime**, không phải suy luận từ literal.

### 10.6. Không dùng `var` cho mọi vị trí khai báo

~~~java
class Example {
    // var field = 1;             // lỗi: không dùng var làm kiểu của field
    int field = 1;

    // var answer() { return 1; } // lỗi: không dùng var làm return type
    int answer() { return 1; }
}
~~~

Đối với lambda không có kiểu đích, `var fn = x -> x + 1;` cũng không biên dịch; hãy dùng một functional interface, ví dụ `IntUnaryOperator fn = x -> x + 1;`. Đây là giới hạn của local-variable type inference, không phải lỗi của literal số nguyên.

## 11. Nguyên tắc áp dụng trong code thật

- **Dùng `var` khi kiểu của biểu thức bên phải rõ ràng**, ví dụ `var maxRetries = 3;` hoặc `var enabled = true;`. Với cấu hình quan trọng dễ nhầm số nguyên/số thực, dùng hậu tố hoặc kiểu tường minh: `var timeoutMillis = 5_000L;` nếu API mong `long`.
- **Viết literal theo kiểu mong muốn, không chờ tự động suy luận:** `3.0` để được `double`; `3.0f` để được `float`; `3L` để được `long`.
- **Kiểm tra phép toán trước khi gán `var`:** `var average = total / count;` có thể là phép chia nguyên nếu hai biến đều `int`, dù `average` nghe như số thực.
- **Đặt tên thể hiện đơn vị và ý nghĩa:** `timeoutMillis`, `taxRate`, `userCount` giúp đọc code, nhưng tên **không** điều khiển kiểu của `var`.
- **Không dùng `float`/`double` khi cần toán thập phân chính xác** cho tiền tệ hoặc một số quy tắc nghiệp vụ; chọn biểu diễn và làm tròn được kiểm soát.
- **Không dùng chuỗi thay cho dữ liệu có kiểu** nếu có thể parse và validate tại ranh giới đầu vào. `"false"` và `false` thuộc hai kiểu khác nhau, không thể hoán đổi tùy ý.
- **Biết khi nào nên khai báo tường minh:** nếu nhìn initializer mà người đọc khó đoán kiểu hoặc cần khẳng định hợp đồng API, `long count = ...`, `double rate = ...` hoặc `String label = ...` có thể rõ hơn `var`.
- **Không đánh giá kiểu primitive bằng `getClass()`:** đó là hành vi của object và autoboxing, không chứng minh trực tiếp kiểu primitive ở compile time. Trình biên dịch, IDE và overload là công cụ phù hợp hơn.

## 12. Bài tập tự kiểm tra có đáp án

Dự đoán **kiểu suy luận**, **giá trị**, hoặc **lỗi biên dịch**, rồi so sánh với đáp án.

**Bài 1.** `var a = 7; var b = 7L; var c = 7.0; var d = 7.0f;` có kiểu gì?

**Đáp án:** `a: int`; `b: long`; `c: double`; `d: float`. Hậu tố và cách viết literal quyết định kiểu.

**Bài 2.** `var x = 5 / 2;` và `var y = 5 / 2.0;` khác nhau thế nào?

**Đáp án:** `x` là `int`, giá trị `2`; `y` là `double`, giá trị `2.5`. Phép chia số nguyên bỏ phần dư.

**Bài 3.** `var n = 100; n = 100L;` hợp lệ không?

**Đáp án:** Không; `n` đã có kiểu `int`. Muốn `long`, khởi tạo `var n = 100L;` hoặc khai báo `long n = 100;`.

**Bài 4.** Tại sao `var score = 5;` không có kiểu `byte` dù số 5 vừa miền giá trị `byte`?

**Đáp án:** Literal thập phân `5` không hậu tố là `int`. `var` không áp dụng quy tắc thu hẹp theo kích thước giá trị như một số trường hợp gán hằng cho `byte`/`short` tường minh.

**Bài 5.** `var a = "5" + 2;` và `var b = 5 + 2;` có kiểu, giá trị gì?

**Đáp án:** `a` là `String` chứa `"52"`, do nối chuỗi; `b` là `int` có giá trị `7`.

**Bài 6.** `var flag = "true";` có thể dùng trực tiếp trong `if (flag)` không?

**Đáp án:** Không. `flag` là `String`; dùng literal `true` hoặc parse và kiểm tra đầu vào để có giá trị `boolean`.

**Bài 7.** `var n = 0x10;` có kiểu gì, giá trị thập phân bao nhiêu?

**Đáp án:** `int`, giá trị `16`. Tiền tố `0x` đổi hệ cơ số chứ không đổi sang kiểu dữ liệu khác.

**Bài 8.** `var sum = 0.1 + 0.2;` có kiểu gì và vì sao không in chính xác `0.3`?

**Đáp án:** `double`; đây là phép cộng binary floating-point, nên các literal thập phân không được biểu diễn chính xác tuyệt đối dưới dạng nhị phân. `Double.toString` biểu diễn kết quả tương ứng là `0.30000000000000004`.

**Bài 9.** `var x = null;` và `var y = (String) null;` dòng nào hợp lệ?

**Đáp án:** Dòng đầu không suy luận được kiểu và không biên dịch; dòng sau biên dịch vì biểu thức đã có kiểu `String`. Tuy nhiên `y` vẫn null khi chạy.

**Bài 10.** `var answer = true ? 1 : 2.0;` có kiểu gì?

**Đáp án:** `double`, giá trị `1.0`; quy tắc của toán tử điều kiện với hai nhánh số `int` và `double` cho kết quả `double`.

**Bài 11.** `var s = 'A'; var t = "A";` có giống kiểu nhau không?

**Đáp án:** Không. `s: char`; `t: String`. Hai literal khác nhau bởi dấu nháy đơn và nháy kép.

**Bài 12.** `var a = 1.0f + 2.0;` có kiểu gì?

**Đáp án:** `double` vì phép cộng trộn `float` và `double` được nâng lên `double`.

## 13. Tài liệu chính thức

1. [JEP 286 – Local-Variable Type Inference](https://openjdk.org/jeps/286): ý nghĩa `var`, phạm vi áp dụng và các giới hạn.
2. [Java Language Specification – Lexical Structure, Literals](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10): literal số nguyên, số thực, boolean, ký tự, chuỗi và null.
3. [Java Language Specification – Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): khai báo biến cục bộ và suy luận kiểu.
4. [Java Language Specification – Numeric Promotion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.6): kiểu kết quả khi trộn các toán hạng số.
5. [Java Language Specification – Additive Operators](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.18): phép cộng số và nối chuỗi.

**Ghi nhớ:** Literal có **kiểu mặc định cụ thể**. `var` chỉ giúp trình biên dịch lấy kiểu đó từ initializer; `var` không tự chọn kiểu dựa theo ý định tương lai và không tự chuyển số nguyên thành số thực. Khi initializer là **biểu thức** (chia, cộng, so sánh, nối chuỗi), kết quả của toán tử được xác định trước, rồi `var` mới suy luận kiểu biến.
