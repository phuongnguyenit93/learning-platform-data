# `var` trong hệ thống từ vựng của Java

## 1. `var` là gì, và vì sao phải hiểu theo ngữ cảnh?

Java 10 đưa `var` vào cú pháp khai báo biến cục bộ để trình biên dịch suy luận kiểu từ biểu thức khởi tạo. Tuy nhiên, chủ đề **“`var` trong hệ thống từ vựng của Java”** không chỉ nói về cách rút ngắn câu lệnh khai báo. Quan trọng hơn là phân biệt **chữ `var` có vai trò gì khi mã nguồn được tách thành token**: lúc nào là từ khóa theo ngữ cảnh, lúc nào là một tên định danh hợp lệ, và khi nào không được dùng làm tên kiểu.

Kết quả cần đạt:

- Phân biệt identifier (định danh), reserved keyword (từ khóa dành riêng) và contextual keyword (từ khóa theo ngữ cảnh).
- Nhận diện `var` ở vị trí khai báo kiểu biến cục bộ, trong tham số lambda và ở các cấu trúc Java hiện đại liên quan.
- Giải thích vì sao `int var = 5;` hoặc phương thức tên `var()` hợp lệ nhưng `class var {}` không hợp lệ.
- Phân biệt ý nghĩa từ vựng của `var` với cơ chế suy luận **kiểu tĩnh** lúc biên dịch.
- Đọc, biên dịch và dự đoán kết quả ví dụ Java 17+, cùng các trường hợp cố ý gây lỗi.

Nội dung chỉ dùng **quy tắc còn áp dụng trong Java hiện đại**. Java Language Specification (JLS) phiên bản gần đây đã chuẩn hóa thuật ngữ *contextual keyword*; vì vậy cần cẩn thận khi đọc cách mô tả từ tài liệu ban đầu của Java 10.

## 2. Từ mã nguồn đến token

Trình biên dịch không hiểu trực tiếp ý nghĩa nghiệp vụ của chuỗi ký tự. Nó áp dụng các quy tắc từ vựng để nhận diện các phần tử như định danh, từ khóa, literal, toán tử và dấu phân cách; tiếp đó mới phân tích cú pháp và kiểm tra ngữ nghĩa.

~~~text
Văn bản nguồn Java (Unicode)
    ↓ xử lý Unicode escape / kết thúc dòng
Luồng ký tự đầu vào
    ↓ phân tích từ vựng, bỏ qua khoảng trắng/comment phù hợp
Token: identifier / keyword / literal / operator / separator
    ↓ phân tích ngữ pháp theo từng vị trí
Khai báo, biểu thức, phương thức, kiểu, lambda, pattern...
    ↓ phân tích ngữ nghĩa và kiểm tra kiểu
Chương trình hợp lệ hoặc lỗi biên dịch
~~~

Ví dụ:

~~~java
var count = 10;
~~~

| Phần nguồn | Vai trò |
| --- | --- |
| `var` | Từ khóa **theo ngữ cảnh**, được nhận diện ở vị trí `LocalVariableType`. |
| `count` | `Identifier` đặt tên biến. |
| `=` | Toán tử gán. |
| `10` | Literal số nguyên, trong ví dụ này có kiểu `int`. |
| `;` | Dấu phân cách kết thúc câu lệnh. |

**Tách token và suy luận kiểu là hai bước khác nhau.** Việc thấy `var` ở đầu khai báo chưa tạo ra một kiểu dữ liệu mới. Trình biên dịch còn phải xác định kiểu của initializer `10`, rồi gán kiểu `int` cho biến `count` từ thời điểm biên dịch.

## 3. Vị trí của `var` trong nhóm keyword và identifier

### 3.1. Reserved keyword, contextual keyword, identifier

Trong JLS hiện đại, các khái niệm được phân biệt như sau:

| Nhóm | Ví dụ | Quy tắc cần nhớ |
| --- | --- | --- |
| **Reserved keyword** | `class`, `int`, `return`, `final` | Không thể dùng nguyên chữ đó làm identifier thông thường. |
| **Contextual keyword** | `var`, `record`, `yield` | Được xem như từ khóa ở một số vị trí cú pháp quy định; ở nơi khác có thể đóng vai trò identifier theo quy tắc tương ứng. |
| **Identifier** | `total`, `username`, đôi khi chính `var` | Tên dùng cho biến, phương thức, package và những thực thể cho phép. |

Theo **JLS `3.9** của Java 25/26, `var` thuộc tập **ContextualKeyword**, không thuộc tập **ReservedKeyword**. Kết luận “`var` là từ khóa bị cấm ở mọi vị trí đặt tên” vì thế **không chính xác**.

Tài liệu giai đoạn Java 10 có thể gọi `var` là *restricted type name* / *reserved type name* hoặc diễn giải “không phải keyword”. Các cách diễn giải này nhằm nhấn mạnh `var` không dành riêng mọi ngữ cảnh. Khi mô tả **đặc tả Java hiện đại**, thuật ngữ chuẩn là **contextual keyword**; vẫn giữ ý nghĩa quan trọng rằng `var` bị hạn chế khi đặt tên kiểu.

### 3.2. `Identifier` khác `TypeIdentifier`

`Identifier` là tên được tạo từ các ký tự được Java cho phép dùng ở đầu và phần tiếp theo của định danh. Java phân biệt chữ hoa/chữ thường, hỗ trợ ký tự Unicode, và không cho identifier trùng chính tả với reserved keyword, literal boolean hoặc literal `null`.

JLS `3.8 có quy tắc riêng cho **TypeIdentifier**. Ở Java hiện đại:

~~~text
TypeIdentifier:
    Identifier nhưng không được là:
    permits, record, sealed, var, yield
~~~

Một **TypeIdentifier** được dùng làm tên lớp, interface, tham số kiểu generic, v.v. Vì chữ `var` bị loại khỏi `TypeIdentifier` nên:

- `var` có thể hợp lệ là **tên biến** hoặc **tên phương thức**.
- `var` **không hợp lệ làm tên class, interface, record, enum hoặc type parameter**.
- Cú pháp `var name = expression;` không sử dụng một kiểu tên `var`; nó dùng quy tắc **LocalVariableType** của ngôn ngữ.

Phân biệt hai điều kiện: một chuỗi ký tự có thể được xem là identifier trong một ngữ cảnh, nhưng **không đủ điều kiện để làm TypeIdentifier** ở ngữ cảnh khai báo kiểu.

### 3.3. Các ngữ cảnh mà `var` mang ý nghĩa cú pháp đặc biệt

Ở Java hiện nay, ngữ pháp sử dụng `var` tại những vị trí cụ thể:

1. **`LocalVariableType`**: khai báo biến cục bộ có kiểu suy luận, xuất hiện từ **Java 10**.
2. **`LambdaParameterType`**: khai báo kiểu tham số lambda theo dạng `var`, được bổ sung từ **Java 11**.
3. Một số mẫu khai báo biến suy luận kiểu trong **record pattern lồng nhau**, dựa trên ngữ pháp biến cục bộ ở Java mới hơn (Java 21+).

Các phần sau minh họa từng trường hợp, nhưng trọng tâm xuyên suốt là **ý nghĩa từ vựng và sự phân biệt tên**.

## 4. `var` ở những vị trí hợp lệ

### 4.1. `var` đứng ở vị trí kiểu biến cục bộ

~~~java
// Các câu lệnh trong thân phương thức:
var title = "Java"; // String
var count = 10;     // int
final var limit = 3; // final int
~~~

Ở đây token `var` bắt đầu một khai báo biến cục bộ. Nó báo trình biên dịch suy luận kiểu từ biểu thức khởi tạo. `final` vẫn mang ý nghĩa thông thường là cấm gán lại biến, không làm cho kiểu trở thành “`final var`” đặc biệt.

### 4.2. `var` làm tên biến

~~~java
// Trong thân phương thức:
int var = 5;
System.out.println(var); // 5

var total = 10; // chữ var là cú pháp suy luận kiểu, total là tên biến
~~~

`int var = 5;` hợp lệ vì `var` lúc này ở **vị trí tên biến** và được xử lý như identifier. Biến vẫn mang kiểu `int` đã khai báo.

Đặc biệt, đoạn sau **hợp lệ** dù không nên dùng trong code sản phẩm vì khó đọc:

~~~java
var var = 9;
System.out.println(var); // 9
~~~

Hai chữ `var` đảm nhiệm hai vai trò khác nhau trong cùng một khai báo:

- `var` thứ nhất: từ khóa theo ngữ cảnh tại `LocalVariableType`.
- `var` thứ hai: tên biến (identifier).
- `9`: initializer giúp biến có kiểu `int`.

### 4.3. `var` làm tên phương thức

~~~java
class Calculations {
    static int var() {
        return 7;
    }
}
~~~

Tên phương thức `var` là hợp lệ. Lời gọi `var()` được nhận diện bằng cú pháp lời gọi phương thức; nó khác với việc sử dụng biểu thức tên biến `var` không có dấu ngoặc.

Trong một phương thức khác, có thể tồn tại biến cục bộ tên `var` và lời gọi phương thức `var()` mà không gây nhầm ý nghĩa: Java phân biệt bằng vị trí ngữ pháp và dấu ngoặc.

### 4.4. `var` có thể xuất hiện trong tên package

Các thành phần tên package sử dụng quy tắc identifier thích hợp, nên việc có một thành phần tên trùng chữ `var` là có thể hợp lệ. Nhưng kiểu viết package như thế dễ gây khó hiểu và không nên chủ động chọn cho dự án mới. Điều này **không** thay đổi hạn chế `TypeIdentifier` đối với tên lớp/interface.

## 5. Vì sao `class var` không hợp lệ?

Các dòng sau **cố ý sai**; đây là ví dụ nhận diện lỗi, không phải chương trình để chạy:

~~~java
// class var {}            // SAI: class name yêu cầu TypeIdentifier
// interface var {}        // SAI: interface name yêu cầu TypeIdentifier
// enum var { ACTIVE }     // SAI: enum name yêu cầu TypeIdentifier
// record var(int x) {}    // SAI: record name yêu cầu TypeIdentifier
// class Box<var> {}       // SAI: generic type parameter name yêu cầu TypeIdentifier
~~~

Thay bằng tên kiểu hợp lệ, có ý nghĩa rõ ràng:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T getValue() {
        return value;
    }
}
~~~

Tên `Box` và `T` đều dùng được làm TypeIdentifier. Chữ `var` không thể được dùng để thay `T` với ý nghĩa “tham số kiểu tự suy luận”.

Cũng không thể thay tên kiểu bằng `var` ở các vị trí **không hỗ trợ local-variable type inference**:

~~~java
class WrongPlaces {
    // private var id = 1;               // SAI: field
    // static var shared = 10;           // SAI: static field
    // public var calculate() { return 1; } // SAI: return type
    // void process(var input) {}        // SAI: regular method parameter
    // WrongPlaces(var id) {}            // SAI: constructor parameter
}
~~~

Các trường hợp này liên quan **cả vị trí cú pháp và quy tắc kiểu**, không có nghĩa `var` là reserved keyword như `class` hay `int`.

## 6. Phân tích chuỗi ký tự: khoảng trắng, ranh giới token và phân biệt hoa/thường

### 6.1. `varName` là một identifier duy nhất

~~~java
var name = "An";  // hai token đầu: var, name
int varName = 1;  // "varName" là một identifier
int variable = 2; // "variable" là một identifier
~~~

Trình phân tích từ vựng **không** tách `varName` thành `var` + `Name`. Java có quy tắc nhận dãy ký tự tạo token dài nhất phù hợp; đồng thời việc dùng contextual keyword cần ngữ cảnh và ranh giới token hợp lệ.

Nếu viết:

~~~java
// varcount = 10;
~~~

đây là phép gán cho một tên `varcount`, **không phải** khai báo `var count = 10;`. Nếu `varcount` chưa được khai báo, trình biên dịch báo lỗi tên biến chưa tồn tại.

Khi khai báo bằng `var`, cách đơn giản, đúng và dễ đọc là viết một khoảng trắng giữa từ `var` và tên biến: `var count = 10;`.

### 6.2. `var` khác `Var`

Java phân biệt chữ hoa và chữ thường:

~~~java
class Var {
    // Tên lớp Var hợp lệ vì khác chuỗi var.
}
~~~

Trong thân phương thức của lớp có thể viết:

~~~java
Var first = new Var(); // Var là tên một lớp
var second = new Var(); // var là cú pháp suy luận; second có kiểu Var
~~~

Không có quy tắc tự động biến chữ `Var` viết hoa thành contextual keyword `var`.

### 6.3. Chữ `var` trong chuỗi và comment không phải token khai báo

~~~java
String label = "var"; // ba ký tự của một String literal
// var trong comment chỉ là nội dung chú thích
~~~

Không nên kiểm tra việc dùng từ khóa bằng cách tìm mọi chuỗi con “var” trong mã nguồn; một công cụ phân tích đúng cần biết token và ngữ cảnh.

## 7. Cách dùng `var` còn hiệu lực trong Java hiện đại

### 7.1. Khai báo biến cục bộ, vòng lặp và tài nguyên

~~~java
// Những câu lệnh minh họa đặt trong một phương thức:
var value = "Java"; // String

for (var index = 0; index < 2; index++) {
    System.out.println(index);
}

for (var item : java.util.List.of("A", "B")) {
    System.out.println(item);
}

try (var reader = new java.io.StringReader("OK")) {
    System.out.println((char) reader.read());
}
~~~

Đoạn trên mô tả những vị trí cú pháp Java dùng được `var`. Với `for-each`, trình biên dịch biết kiểu phần tử từ kiểu iterable hoặc mảng; không cần initializer dạng `= ...` trong header vòng lặp. Với `try-with-resources`, tài nguyên phải thỏa các quy tắc của ngôn ngữ và phương thức I/O có thể yêu cầu xử lý ngoại lệ.

### 7.2. Lambda có kiểu tham số `var` (Java 11+)

~~~java
java.util.function.Function<String, Integer> length =
        (var text) -> text.length();
System.out.println(length.apply("Java")); // 4
~~~

`var` trong `(var text)` là cú pháp khai báo kiểu tham số lambda, **không** phải khai báo một kiểu tên `var`. Lambda cần ngữ cảnh có kiểu hàm phù hợp. Nếu có nhiều tham số, hãy dùng dạng khai báo nhất quán:

~~~java
java.util.function.BiFunction<Integer, Integer, Integer> add =
        (var left, var right) -> left + right;
System.out.println(add.apply(2, 3)); // 5

// (var left, int right) -> left + right
// SAI: trộn var với kiểu tường minh trong cùng danh sách tham số lambda.
~~~

Tính năng lambda `var` là của Java 11, không nên gán sai nguồn gốc cho Java 10.

### 7.3. `var` trong record pattern lồng nhau (Java 21+)

Java hiện đại còn hỗ trợ cú pháp suy luận kiểu ở các thành phần của record pattern:

~~~java
record Message(String text, int priority) {}

Object input = new Message("Java", 2);
if (input instanceof Message(var text, var priority)) {
    System.out.println(text + ": " + priority);
}
~~~

Đây là **đoạn minh họa cú pháp**: khai báo record phải đặt ở vị trí hợp lệ trong chương trình và các câu lệnh nằm trong phương thức/khối phù hợp. `var` suy luận kiểu của thành phần mẫu (nested pattern), không phải tên kiểu. Không được đồng nhất ví dụ này với việc dùng tùy ý `instanceof var value` ở vị trí top-level.

## 8. Vai trò từ vựng không thay thế quy tắc suy luận kiểu

`var` được phép xuất hiện ở vị trí cú pháp phù hợp nhưng một khai báo vẫn có thể **không hợp lệ** vì initializer không cho phép xác định kiểu:

~~~java
var count = 10;            // hợp lệ: count có kiểu int
count = 20;                // hợp lệ
// count = "twenty";       // SAI: String không gán được cho int

// var unknown;           // SAI: thiếu initializer
// var absent = null;     // SAI: null đơn lẻ không có kiểu phù hợp
// var values = {1, 2};   // SAI: array initializer trần
// var fn = x -> x + 1;   // SAI: lambda thiếu target type
~~~

Một số lỗi thường gặp khác và cách sửa:

| Đoạn cố ý sai | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `var a = 1, b = 2;` | `var` không hỗ trợ khai báo nhiều biến trong một câu lệnh. | `var a = 1; var b = 2;` |
| `var values[] = new int[2];` | Không được thêm `[]` sau tên biến khi dùng `var`. | `var values = new int[2];` |
| `var result = null;` | Không suy luận được kiểu từ `null` đơn lẻ. | `String result = null;` nếu đúng ý định. |
| `var fn = String::length;` | Method reference chưa có kiểu đích. | `Function<String, Integer> fn = String::length;` |
| `var self = self + 1;` | Initializer tự tham chiếu chính biến đang khai báo. | Khởi tạo từ biểu thức đã có dữ liệu hoặc khai báo kiểu tường minh đúng cách. |

Việc Java vẫn định kiểu tĩnh được thể hiện ngay ở ví dụ `var count = 10;`: `count` luôn có kiểu `int`, không tự biến thành `String` sau phép gán. Không tồn tại kiểu runtime đặc biệt tên `var` tương tự các ngôn ngữ định kiểu động.

## 9. Chương trình minh họa hoàn chỉnh, chạy bằng Java 17+

Tạo file **`VarLexicalDemo.java`**:

~~~java
import java.util.function.Function;

public class VarLexicalDemo {
    // var là tên phương thức hợp lệ.
    static int var() {
        return 7;
    }

    static int sameSpelling() {
        // var thứ nhất: kiểu suy luận; var thứ hai: tên biến.
        var var = 9;
        return var;
    }

    public static void main(String[] args) {
        var count = 2;
        int var = 5; // var là tên biến
        var total = count + var;
        var prefix = "Java";

        // Tham số lambda var cần Java 11+.
        Function<String, Integer> size = (var text) -> text.length();

        System.out.println("count=" + count);
        System.out.println("local named var=" + var);
        System.out.println("method named var=" + var());
        System.out.println("total=" + total);
        System.out.println("lambda length=" + size.apply(prefix));
        System.out.println("same spelling=" + sameSpelling());
    }
}
~~~

Trong thư mục chứa file, chạy:

~~~bash
javac VarLexicalDemo.java
java VarLexicalDemo
~~~

**Stdout chính xác:**

~~~text
count=2
local named var=5
method named var=7
total=7
lambda length=4
same spelling=9
~~~

Giải thích:

1. `var count = 2;` dùng `var` theo ngữ cảnh `LocalVariableType`; `count` có kiểu `int`.
2. `int var = 5;` sử dụng chữ `var` làm tên biến hợp lệ.
3. `var()` gọi phương thức tên `var` và trả về `7`.
4. `total` nhận kiểu `int` từ biểu thức `count + var`.
5. `(var text)` được dùng với functional interface `Function<String, Integer>` để suy luận `text` là `String`.
6. `var var = 9;` trong `sameSpelling()` chứng minh hai token cùng chính tả có thể mang hai vai trò cú pháp khác nhau.

Chương trình có kết quả xác định, không phụ thuộc hệ điều hành hoặc thứ tự của collection. Đây là ví dụ Java 17+ độc lập, có thể sao chép và thực thi; các đoạn đánh dấu cố ý sai ở mục trước không được đưa vào file này.

## 10. Tính tương thích và các ngộ nhận phổ biến

Một lý do thiết kế `var` theo ngữ cảnh là hạn chế tác động lên mã có tên biến, phương thức hoặc package trùng chữ `var`. Các định danh này có thể tiếp tục hợp lệ khi nâng phiên bản Java; còn mã dùng `var` làm **tên kiểu** cần được đổi tên để tương thích với Java 10+.

| Ngộ nhận | Điều chính xác |
| --- | --- |
| “`var` là reserved keyword giống `int`.” | Theo JLS hiện đại, `var` là **contextual keyword**. |
| “Có thể viết `class var` vì `var` không dành riêng mọi ngữ cảnh.” | Sai: `var` bị loại khỏi `TypeIdentifier`. |
| “`var` không thể làm tên biến/phương thức.” | Có thể, dù khó đọc và không nên dùng cho tên mới. |
| “`varName` mở đầu bằng keyword `var`.” | `varName` là một identifier độc lập. |
| “`Var` viết hoa có hiệu lực như `var`.” | Java phân biệt hoa/thường; `Var` có thể là tên lớp hợp lệ. |
| “`var` tạo ra kiểu động.” | Biến vẫn nhận **kiểu tĩnh** ở thời điểm biên dịch. |
| “Dùng `var` ở vị trí hợp lệ thì initializer nào cũng được.” | Không: thiếu initializer, `null` đơn lẻ, lambda không có target type... vẫn gây lỗi. |
| “`var` trong lambda là tính năng Java 10.” | Cú pháp tham số lambda `var` được thêm từ **Java 11**. |
| “IDE tô màu `var` giống keyword nghĩa là mọi cách dùng đều là keyword.” | Quyết định phụ thuộc cú pháp và ngữ cảnh, không phụ thuộc giao diện tô màu. |

Trong code thực tế, dù Java cho phép `int var = 5;`, hãy ưu tiên đặt tên biến có ý nghĩa như `count`, `retryLimit`, `sourcePath`. Dùng `var` ở vị trí suy luận kiểu khi initializer làm kiểu đủ rõ, chẳng hạn `var users = new ArrayList<String>();`. Khi muốn nhấn mạnh kiểu interface trong chữ ký biến, kiểu tường minh như `List<String> users = new ArrayList<>();` có thể dễ đọc hơn.

## 11. Bài tập và lời giải

**Bài 1.** Cho các khai báo:

~~~java
int var = 2;
var count = 3;
var varName = count + var;
~~~

Chữ `var` ở đâu mang nghĩa contextual keyword, ở đâu mang nghĩa identifier?

**Lời giải:** `var` trong `int var` là tên biến; `var` ở đầu hai khai báo tiếp theo là cú pháp suy luận kiểu. `varName` là identifier độc lập, không bị tách thành `var` và `Name`.

**Bài 2.** Phân loại:

~~~java
// class var {}        // (A)
// class Var {}        // (B)
// var var = 8;        // (C) bên trong phương thức
// int var = 8;        // (D) bên trong phương thức
~~~

**Lời giải:** (A) sai vì `var` không là `TypeIdentifier`; (B) hợp lệ; (C) và (D) hợp lệ nếu xét độc lập và không trùng khai báo trong cùng phạm vi.

**Bài 3.** Vì sao `var name = null;` sai nhưng `String name = null;` có thể hợp lệ?

**Lời giải:** Với `var`, trình biên dịch phải suy luận kiểu từ initializer, trong khi `null` đơn lẻ không đủ cho quy tắc đó. Với `String`, kiểu đã được khai báo tường minh.

**Bài 4.** Có thể đổi tên tham số kiểu generic `T` thành `var` không?

**Lời giải:** Không. Tên tham số kiểu yêu cầu `TypeIdentifier` và `var` bị loại khỏi tập tên đó.

**Bài 5.** Trong chương trình minh họa, vì sao có thể dùng đồng thời `var` và `var()`?

**Lời giải:** Tên biến và tên phương thức được diễn giải theo ngữ cảnh ngữ pháp khác nhau; lời gọi phương thức sử dụng dấu `()`.

**Bài 6.** Đâu là kiến thức có hiệu lực trong Java mới hơn Java 10?

**Lời giải:** Khai báo `var x = 1;` vẫn hợp lệ; `var` là contextual keyword theo JLS hiện đại; `var` trong tham số lambda được hỗ trợ từ Java 11; cú pháp `var` ở record pattern lồng nhau dùng từ Java 21+.

## 12. Nguồn kỹ thuật chính thống

- [Java Language Specification 26 — Chapter 3, Lexical Structure (`3.8, `3.9)](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-3.html): identifier, contextual keyword, TypeIdentifier, quy tắc tách token.
- [Java Language Specification 26 — `14.4 Local Variable Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html): vai trò `LocalVariableType`, initializer và các lỗi khi dùng `var`.
- [Java Language Specification 26 — `15.27 Lambda Expressions](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.27): tham số lambda và kiểu đích.
- [Oracle Java 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): cách áp dụng `var` trong mã Java.
- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): thiết kế của tính năng từ Java 10.

**Ghi nhớ:** `var` là **contextual keyword** trong Java hiện đại, được nhận diện với ý nghĩa đặc biệt ở vị trí cú pháp thích hợp. Tên biến hoặc phương thức có thể là `var`, nhưng **tên kiểu không được là `var`**. Dù dùng cú pháp nào, Java vẫn kiểm tra kiểu tĩnh khi biên dịch.