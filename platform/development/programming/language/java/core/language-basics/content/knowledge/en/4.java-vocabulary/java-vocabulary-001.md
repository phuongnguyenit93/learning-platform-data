# Token trong Java: tên định danh, từ khóa, literal, toán tử và dấu phân cách

> **Java core — language-basics / Từ vựng Java**  
> **Áp dụng:** Java 17 trở lên, dùng JDK để biên dịch và chạy.  
> **Mục tiêu:** Nhận diện năm loại token cơ bản trong mã nguồn Java; phân biệt tên định danh với từ khóa, literal với toán tử, và dấu phân cách với nội dung có ý nghĩa ngữ pháp. Tự đọc được một dòng Java dưới góc nhìn của bộ phân tích từ vựng (*lexer*), dự đoán lỗi đặt tên và chạy một chương trình tối thiểu.

## 1. Token là gì và vì sao cần hiểu?

Khi nhìn dòng mã:

~~~java
int total = quantity * price;
~~~

người đọc hiểu đây là phép tính. Trước khi phân tích cấu trúc câu lệnh, Java xử lý mã nguồn thành những đơn vị từ vựng gọi là **token**. Có thể tách dòng trên thành:

| Thứ tự | Token | Loại | Vai trò |
| ---: | --- | --- | --- |
| 1 | `int` | Từ khóa | Kiểu số nguyên nguyên thủy |
| 2 | `total` | Tên định danh | Tên biến nhận kết quả |
| 3 | `=` | Toán tử | Phép gán |
| 4 | `quantity` | Tên định danh | Tên biến đầu vào |
| 5 | `*` | Toán tử | Phép nhân |
| 6 | `price` | Tên định danh | Tên biến đầu vào |
| 7 | `;` | Dấu phân cách | Kết thúc câu lệnh khai báo |

**Token không đồng nghĩa với từ ngữ có nghĩa trong tiếng Anh.** Chẳng hạn, `total` không phải từ khóa Java; đó là tên do lập trình viên tự đặt. Dấu `;` cũng là token dù chỉ dài một ký tự.

Sơ đồ khái niệm:

~~~mermaid
flowchart LR
    A["Ký tự mã nguồn Java"] --> B["Xử lý từ vựng"]
    B --> C["Dãy token"]
    C --> D["Phân tích cú pháp"]
    D --> E["Cấu trúc chương trình"]
~~~

**Khoảng trắng, xuống dòng và chú thích** giúp phân tách hoặc giải thích mã nguồn, nhưng không được tính là token Java theo nhóm năm loại đang học. Riêng dấu cách **bên trong** một chuỗi literal lại là một phần nội dung của literal đó.

## 2. Năm nhóm token theo Java

| Nhóm | Ví dụ | Cách nhận diện |
| --- | --- | --- |
| **Identifier — tên định danh** | `studentCount`, `totalPrice`, `println` | Tên của biến, lớp, phương thức, package… được khai báo hoặc tham chiếu |
| **Keyword — từ khóa** | `class`, `public`, `int`, `if`, `return` | Các từ được ngôn ngữ dành riêng theo quy tắc cú pháp |
| **Literal — giá trị viết trực tiếp** | `42`, `12_000L`, `3.14`, `'A'`, `"Java"`, `true`, `null` | Biểu diễn trực tiếp một giá trị trong mã |
| **Operator — toán tử** | `+`, `=`, `==`, `&&`, `++`, `->` | Thực hiện phép tính, so sánh, gán hoặc thể hiện thao tác trong biểu thức |
| **Separator — dấu phân cách** | `( )`, `{ }`, `[ ]`, `;`, `,`, `.`, `@`, `::` | Phân định thành phần, danh sách, khối, truy cập thành viên hoặc cú pháp liên quan |

Các từ như “identifier” hay “operator” là **loại token ở mức từ vựng**. Việc ghép token thành khai báo, biểu thức, câu lệnh hoặc lớp là bước **phân tích cú pháp**; một token hợp lệ chưa bảo đảm toàn bộ dòng mã hợp lệ.

Ví dụ `int = ;` gồm những token Java nhận diện được, nhưng không phải câu lệnh khai báo hợp lệ vì thiếu tên biến và giá trị/biểu thức thích hợp.

## 3. Tên định danh (identifier): quy tắc và cách đặt tên

Tên định danh được dùng cho lớp, phương thức, biến, field, package và nhiều thành phần khác. Java **phân biệt chữ hoa và chữ thường**:

~~~java
int count = 2;
int Count = 5;
System.out.println(count + Count); // 7
~~~

`count` và `Count` là **hai tên khác nhau**.

### Quy tắc tên trong Java 17

- Ký tự đầu phải hợp lệ cho vị trí bắt đầu identifier theo quy tắc Unicode của Java; những ký tự tiếp theo có thể bao gồm chữ số. Các chữ cái ASCII, `_` và `$` có thể tham gia tên theo quy tắc đó.
- **Không** bắt đầu một identifier ASCII bằng chữ số: `2items` không phải tên hợp lệ.
- **Không** sử dụng các từ khóa dành riêng như `class`, `int` hoặc `return` để đặt tên identifier thông thường.
- Ký tự gạch dưới đơn độc `_` **không được dùng làm identifier** trong Java 17 (từ Java 9 nó là một từ khóa dành riêng).
- Java hỗ trợ nhiều chữ cái Unicode trong identifier, chẳng hạn `soLuong` và `sốLượng`, nhưng viết tên ổn định, dễ đọc giúp code nhất quán hơn.

| Ví dụ | Hợp lệ như tên biến Java 17? | Giải thích |
| --- | --- | --- |
| `studentCount` | Có | Bắt đầu bằng chữ, các ký tự tiếp theo hợp lệ |
| `_count` | Có | Dấu `_` kết hợp với ký tự khác, không đứng một mình |
| `$cache` | Có | `$` được phép, nhưng nên tránh trong tên tự viết nếu không cần |
| `sốLượng` | Có | Java hỗ trợ identifier Unicode phù hợp |
| `2ndValue` | Không | Bắt đầu bằng chữ số |
| `item-count` | Không phải một identifier | Java đọc thành `item`, toán tử `-` và `count` |
| `class` | Không | Từ khóa dành riêng |
| `_` | Không | Dấu gạch dưới đơn độc được dành riêng từ Java 9 |

**Quy ước nên dùng:** tên biến/method là `lowerCamelCase` (`itemCount`), tên class là `UpperCamelCase` (`InvoiceCalculator`), hằng `static final` thường theo `UPPER_SNAKE_CASE` (`MAX_ITEMS`). Đây là **quy ước đặt tên** chứ không phải các bộ luật khác nhau của lexer.

### Identifier không nhất thiết là từ khóa

`String` là tên một lớp chuẩn của Java; `System` là tên một lớp; `println` là tên method; `main` và `args` là tên identifier. Chúng không vì “đặc biệt” hay “được Java dùng nhiều” mà biến thành từ khóa ngôn ngữ.

## 4. Từ khóa (keyword) và các từ bị hạn chế theo ngữ cảnh

Từ khóa có vai trò do ngôn ngữ Java quy định. Những ví dụ phổ biến:

| Nhóm ý nghĩa | Một số từ khóa Java 17 | Ví dụ sử dụng |
| --- | --- | --- |
| Khai báo lớp/kiểu | `class`, `interface`, `enum` | `class Person { }` |
| Quyền truy cập và thành phần | `public`, `private`, `protected`, `static`, `final` | `private int age;` |
| Điều khiển chương trình | `if`, `else`, `switch`, `for`, `while`, `return`, `break` | `if (ready) { ... }` |
| Kiểu nguyên thủy | `int`, `long`, `double`, `boolean`, `char`, `void` | `double rate = 1.5;` |
| Đối tượng và ngoại lệ | `new`, `this`, `super`, `try`, `catch`, `throw` | `new Object()` |

**Một số trường hợp dễ nhầm:**

- `true` và `false` là **boolean literals**; `null` là **null literal**. Chúng không nằm trong danh sách từ khóa Java dù cũng không thể dùng làm tên biến thông thường.
- `const` và `goto` được Java **dành riêng như từ khóa**, dù Java không có những câu lệnh hoạt động bình thường mang hai tên đó.
- Java 17 có những **restricted/contextual identifiers hoặc keywords** như `var`, `record`, `yield`, `sealed`, `permits` và `non-sealed`. Chúng chịu các quy tắc riêng tùy vị trí cú pháp; **không nên coi mọi lần xuất hiện của chúng giống một từ khóa luôn bị cấm như `class`**.

Ví dụ Java 17:

~~~java
var message = "Hello";   // var dùng trong khai báo biến cục bộ có khởi tạo.
System.out.println(message);
~~~

`var` không phải tên một kiểu class có thể dùng ở bất kỳ chỗ nào; compiler suy luận kiểu của biến trong các ngữ cảnh mà ngôn ngữ cho phép. Bài này chỉ nhằm nhận diện vai trò từ vựng, chưa đi sâu tính năng suy luận kiểu.

## 5. Literal: giá trị được viết trực tiếp trong mã

**Literal** là cách đặt một giá trị cụ thể ngay trong mã nguồn, không cần tham chiếu biến.

| Loại literal | Ví dụ hợp lệ | Ghi chú |
| --- | --- | --- |
| Số nguyên thập phân | `0`, `42`, `1_000` | `_` giữa các chữ số tăng khả năng đọc |
| Số nguyên hệ khác | `0b1010`, `0xFF`, `077` | Nhị phân, thập lục phân và bát phân |
| Số nguyên `long` | `12_000L` | Hậu tố `L`; chữ `L` hoa dễ phân biệt với số 1 |
| Số thực | `3.14`, `2.5e3`, `1.5f` | Mặc định là `double`; `f` tạo `float` |
| Ký tự `char` | `'A'`, `'\n'` | Dùng nháy đơn, có thể dùng escape |
| Chuỗi `String` | `"Java 17"`, `"A\nB"` | Dùng nháy kép |
| Boolean | `true`, `false` | Hai giá trị logic |
| Null | `null` | Giá trị null reference |

Trong Java 17, **text block** cũng là cú pháp literal để viết chuỗi nhiều dòng:

~~~java
String message = """
        Xin chào
        Java 17
        """;
~~~

Dấu `"""` mở đầu text block phải được theo sau bởi một dấu kết thúc dòng; nội dung dòng và xử lý thụt lề theo quy tắc Java text block. Không nhầm dấu `"""` với ba chuỗi rỗng ghép nhau.

### Ba lỗi lexical/literal thường gặp

**1. Dấu âm là toán tử riêng.** Ở biểu thức `int temperature = -5;`, lexer nhận dấu `-` và literal số nguyên `5` riêng rẽ. `-5` không phải một “literal âm” đơn lẻ theo cách phân loại token này.

**2. Dấu gạch dưới trong số phải đúng vị trí.** `1_000` hợp lệ, nhưng `_1000` không phải integer literal có dấu gạch dưới: lexer có thể nhận đó là identifier; đặt nó làm giá trị số sẽ lỗi cú pháp/ngữ nghĩa. Dạng `1000_` cũng không phải integer literal hợp lệ.

**3. Nháy đơn và nháy kép không thay thế nhau.** `'A'` là char literal; `"A"` là String literal. `'AB'` không phải một char literal hợp lệ.

Những từ `true`, `false` và `null` phải được hiểu là **literal**, ngay cả khi xuất hiện tại vị trí mà cú pháp Java không cho phép dùng chúng.

## 6. Toán tử (operator): đọc đúng token rồi mới hiểu phép toán

Các toán tử nhận giá trị hoặc đối tượng theo quy tắc của Java:

| Nhóm | Token tiêu biểu | Ví dụ |
| --- | --- | --- |
| Số học | `+`, `-`, `*`, `/`, `%` | `amount * count` |
| Gán | `=`, `+=`, `-=`, `*=`, `/=` | `total += 10` |
| So sánh | `==`, `!=`, `<`, `<=`, `>`, `>=` | `count >= 2` |
| Logic ngắn mạch | `&&`, `\|\|`, `!` | `ready && enabled` |
| Tăng/giảm | `++`, `--` | `count++` |
| Bit và dịch bit | `&`, `\|`, `^`, `~`, `<<`, `>>`, `>>>` | `flags & 0xFF` |
| Điều kiện và lambda | `?`, `:`, `->` | `ok ? 1 : 0`; `x -> x + 1` |

**Đừng nhầm `=` với `==`:** `=` thực hiện phép gán, `==` dùng để so sánh theo quy tắc kiểu. Đặc biệt, với reference object, `==` so sánh tham chiếu chứ không tự kiểm tra nội dung bằng `equals`.

### Ưu tiên ghép token dài hơn khi có thể

Java sử dụng nguyên tắc nhận diện token dài nhất hợp lệ trong quá trình phân tích từ vựng (*maximal munch*). Chẳng hạn:

~~~java
count++;         // ++ là một toán tử, không phải hai token + liền nhau.
total += 3;      // += là một toán tử gán kết hợp.
boolean ok = a >= b && b != 0;
~~~

Trong dòng cuối, `>=`, `&&`, `!=` đều là những token toán tử hoàn chỉnh. Khoảng trắng giúp đọc mã nhưng không được dùng để “tách đôi” một toán tử cố định tùy tiện. Ngược lại, `a + +b` dùng **hai toán tử cộng khác nhau** ở hai vị trí cú pháp.

**Phân tích token khác với phân tích thứ tự tính toán.** Nhận ra `+`, `*` và `=` là token chỉ là bước đầu; độ ưu tiên toán tử, kiểu dữ liệu và quy tắc đánh giá biểu thức sẽ quyết định ý nghĩa tính toán.

## 7. Dấu phân cách (separator): ranh giới của cấu trúc

Các dấu phân cách phổ biến trong Java 17:

| Token | Chức năng quen thuộc | Ví dụ |
| --- | --- | --- |
| `(`, `)` | Nhóm điều kiện, tham số, biểu thức | `if (ready)`, `print(x)` |
| `{`, `}` | Thân class/method/block hoặc initializer | `class App { ... }` |
| `[`, `]` | Khai báo hoặc truy cập mảng | `int[] a`, `a[0]` |
| `;` | Kết thúc khai báo/câu lệnh theo ngữ pháp | `int x = 1;` |
| `,` | Phân tách phần tử, tham số hoặc khai báo phù hợp | `print(a, b)` |
| `.` | Truy cập tên thành viên/định danh được phân tách | `System.out.println` |
| `...` | Ký hiệu tham số biến số lượng (*varargs*) | `String... args` |
| `@` | Mở đầu một annotation | `@Override` |
| `::` | Method reference | `String::valueOf` |

Trong `System.out.println("OK");`, lexer nhìn thấy các identifier `System`, `out`, `println`, các dấu `.`, `(`, `)`, `;` và chuỗi literal `"OK"`. Không có một token duy nhất tên `System.out.println`.

**Lưu ý:** `::` là dấu phân cách trong phân loại lexical token của Java, còn `->` là toán tử. Chúng thường được nhắc cùng nhau khi học lambda/method reference, nhưng không thuộc cùng một nhóm từ vựng.

## 8. Chương trình Java 17+ minh họa năm nhóm token

Tạo một tệp **TokenDemo.java**:

~~~java
public class TokenDemo {
    public static void main(String[] args) {
        int quantity = 3;
        long unitPrice = 12_000L;
        long total = quantity * unitPrice;

        boolean qualified = total >= 30_000L && quantity > 0;
        String productName = "Java";
        char grade = 'A';

        System.out.println(productName + ": " + total);
        System.out.println("qualified=" + qualified + ", grade=" + grade);
    }
}
~~~

Chạy trong terminal (Bash, PowerShell hoặc Command Prompt) tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 TokenDemo.java
java TokenDemo
~~~

Kết quả **chính xác**:

~~~text
Java: 36000
qualified=true, grade=A
~~~

Trong mã:

- `public`, `class`, `static`, `void`, `int`, `long`, `boolean` và `char` là **keywords**.
- `TokenDemo`, `main`, `args`, `quantity`, `unitPrice`, `total`, `qualified`, `String`, `productName` và `grade` là **identifiers** (trong đó `String` là tên lớp).
- `3`, `12_000L`, `30_000L`, `0`, `"Java"`, `'A'` và các chuỗi truyền cho `println` là **literals**.
- `=`, `*`, `>=`, `&&`, `>`, `+` là **operators**.
- `{ }`, `( )`, `[ ]`, `;`, `,` và `.` là **separators**.

Ví dụ có chứa khoảng trắng và dòng trống để dễ đọc; chúng không làm thay đổi loại token. Chương trình sử dụng cú pháp class và `main` quen thuộc, không cần cài thư viện phụ trợ ngoài JDK.

## 9. Các bẫy thường gặp: token hợp lệ nhưng chương trình vẫn lỗi

| Mảnh mã hoặc trường hợp | Chẩn đoán | Cách sửa |
| --- | --- | --- |
| `int class = 1;` | `class` là từ khóa, không thể dùng làm identifier | Đổi thành `classCount` hoặc tên thích hợp |
| `int 2items = 3;` | Chữ số không thể bắt đầu tên biến kiểu này | Dùng `items2` |
| `int item-count = 3;` | `-` là toán tử, không phải ký tự nối trong identifier | Dùng `itemCount` hoặc `item_count` |
| `int _ = 1;` | `_` đơn độc là từ khóa dành riêng trong Java 17 | Chọn tên cụ thể như `unusedCount` |
| `int value = "7";` | Chuỗi literal không gán trực tiếp vào biến `int` | Dùng `7` hoặc chuyển chuỗi với `Integer.parseInt` khi thích hợp |
| `char c = "A";` | `"A"` là String, không phải char | Dùng `'A'` |
| `boolean ok = True;` | `True` không phải boolean literal `true`; Java phân biệt hoa/thường | Dùng `true` |
| `int v = 1__000;` | **Hợp lệ**: nhiều dấu gạch dưới liên tiếp giữa các chữ số được Java chấp nhận | Không tự kết luận mọi `__` đều sai |
| `int x = -5;` | Dấu trừ là toán tử riêng, không phải thành phần của literal `5` | Đọc token theo `=`, `-`, `5`, `;` |
| `int n = 8 / 0;` | Token hợp lệ nhưng phép toán số nguyên tại runtime gây lỗi | Kiểm tra mẫu số; cú pháp từ vựng không bảo đảm phép toán an toàn |

**Một lưu ý kỹ thuật:** một số lỗi trong bảng có thể được compiler phát hiện ngay khi phân tích cú pháp hoặc kiểm tra kiểu; một số khác chỉ xảy ra lúc chạy. Biết token không thay thế cho kiểm tra **kiểu**, **phạm vi biến** và **ngữ nghĩa chương trình**.

## 10. Thực hành phân tích dãy token

Hãy thử phân loại dòng sau, không cần chạy trước:

~~~java
boolean accepted = total >= 100 && quantity != 0;
~~~

| Nhóm | Các token có mặt |
| --- | --- |
| Keywords | `boolean` |
| Identifiers | `accepted`, `total`, `quantity` |
| Literals | `100`, `0` |
| Operators | `=`, `>=`, `&&`, `!=` |
| Separators | `;` |

Sau đó thay `>=` thành `> =` và thử biên dịch trong một chương trình có đủ khai báo biến: hai token `>` và `=` **không thay thế được** một toán tử `>=` trong biểu thức so sánh đó.

Một bài phân tích khác:

~~~java
System.out.println("Hi");
~~~

Hãy đếm: identifier `System`, separator `.`, identifier `out`, separator `.`, identifier `println`, separator `(`, string literal `"Hi"`, separator `)`, separator `;`. Tổng cộng **9 token**.

**Chú thích không biến thành token:** ở `int x = 1; // note`, các token vẫn kết thúc ở `;`; phần `// note` là comment. Ở `String s = "a b";`, dấu cách **nằm trong literal** và vì vậy là một phần giá trị chuỗi.

## 11. Bài tập tự luyện và đáp án định hướng

**Bài 1 — Nhận diện.** Với `long distance = 10_000L;`, hãy chỉ ra từ khóa, identifier, operator, literal và separator.

*Đáp án:* `long`; `distance`; `=`; `10_000L`; `;`.

**Bài 2 — Đặt tên.** Trong `price2`, `2price`, `price_total`, `total-price`, `_` và `$cache`, tên nào có thể là identifier Java 17? Vì sao vẫn nên hạn chế dùng `$` trong tên tự đặt?

*Định hướng:* `price2`, `price_total` và `$cache` hợp lệ; `2price`, `total-price`, `_` không là một identifier hợp lệ. `$` được phép nhưng kém phù hợp với quy ước đặt tên thông thường.

**Bài 3 — Keyword hay literal?** Phân biệt `boolean` với `true`; phân biệt `String` với `class`; giải thích tại sao `null` không phải identifier.

**Bài 4 — Toán tử dài nhất.** Phân tích `i++;` thành các token. Vì sao không đọc thành `i`, `+`, `+`, `;`? Phân tích tiếp `total += 1;`.

**Bài 5 — Sửa lỗi.** Sửa `int class = 3;` và `char unit = "A";`. Chỉ ra loại lỗi của mỗi dòng thay vì chỉ đưa đáp án.

**Bài 6 — Tự chạy.** Biên dịch `TokenDemo.java`, đổi literal `12_000L` thành `15_000L` và dự đoán cả hai dòng kết quả; tiếp tục thử dùng `'A'` thay cho `"Java"` ở biến `String` để quan sát lỗi kiểu.

## 12. Checklist cuối bài

- [ ] Biết **token là đơn vị từ vựng**, khác với câu lệnh/chương trình hợp lệ.
- [ ] Phân biệt được identifier, keyword, literal, operator và separator ngay trong một dòng Java.
- [ ] Nhớ `String`, `System`, `println` không phải từ khóa; `true`, `false`, `null` là literals.
- [ ] Biết tên biến Java 17 phân biệt chữ hoa/thường, không bắt đầu bằng số, và `_` không là identifier hợp lệ khi đứng đơn độc.
- [ ] Nhận ra `-5` gồm toán tử `-` và literal `5`; `++` là một token toán tử.
- [ ] Giải thích được vai trò của `;`, `.`, `( )` và `{ }` mà không nhầm chúng với toán tử.
- [ ] Tự biên dịch `TokenDemo.java` bằng `javac` và chạy bằng `java`, đối chiếu kết quả.

**Tổng kết:** Hiểu từ vựng Java giúp bạn đọc mã chính xác từ từng ký hiệu, chọn tên hợp lệ và phân biệt lỗi token với lỗi cú pháp/kiểu/ngữ nghĩa. Token là **vật liệu đầu vào** để ngôn ngữ ghép thành những cấu trúc chương trình có ý nghĩa.
