# Nối chuỗi bằng `+` khác phép cộng như thế nào trong Java?

## 1. Cùng một dấu `+`, hai hành vi khác nhau

Trong Java, dấu `+` là toán tử có **hai cách sử dụng chính** trong biểu thức:

- **Cộng số học** (*numeric addition*) khi hai toán hạng là các giá trị số có thể áp dụng quy tắc thăng cấp số học: `2 + 3` tạo ra số nguyên **5**.
- **Nối chuỗi** (*string concatenation*) khi ít nhất một toán hạng có kiểu `String`: `"2" + 3` tạo ra chuỗi **"23"**.

Những ví dụ đầu tiên:

| Biểu thức Java | Kiểu kết quả | Giá trị kết quả | Vì sao? |
|---|---|---|---|
| `2 + 3` | `int` | `5` | Cộng hai số nguyên |
| `2L + 3` | `long` | `5L` | Có `long` nên kết quả là `long` |
| `"2" + 3` | `String` | `"23"` | Nối văn bản "2" với giá trị 3 |
| `2 + "3"` | `String` | `"23"` | Nối số 2 đã được chuyển thành văn bản với "3" |
| `"2" + "3"` | `String` | `"23"` | Nối hai chuỗi |
| `'2' + 3` | `int` | `53` | Ký tự '2' có mã UTF-16 50, cộng với 3 |
| `"2" + '3'` | `String` | `"23"` | Một toán hạng là `String` |

**Giá trị `"23"` khác giá trị số `23`.** Chuỗi là dữ liệu văn bản và có thể gồm ký tự, khoảng trắng, đơn vị đo, mã định danh; phép cộng số học tạo kết quả số theo kiểu và miền giá trị của toán hạng.

Không phải hễ xuất hiện dấu `+` là Java cộng số, và cũng không phải hễ xuất hiện ký tự chữ số là một đối tượng `String`. Hãy luôn xác định **kiểu của từng toán hạng tại thời điểm toán tử `+` được đánh giá**.

## 2. Quy tắc chọn cộng số hay nối chuỗi

### 2.1. Hai toán hạng số: thăng cấp rồi cộng

Với các toán hạng nguyên thủy dạng số, phép `+` dùng *binary numeric promotion*:

1. `byte`, `short` và `char` được nâng thành `int`.
2. Nếu có toán hạng `long`, phép cộng tích phân sử dụng `long`.
3. Nếu không có `long`, phép cộng của các kiểu tích phân nguyên thủy cho kết quả `int`.

Ví dụ:

```java
byte a = 10;
byte b = 20;
int sum = a + b;     // 30, biểu thức a + b có kiểu int
long wide = a + 20L; // 30L, biểu thức có kiểu long
```

Không thể gán trực tiếp `byte c = a + b;` vì phép cộng hai biến `byte` trả `int`; muốn chuyển về `byte` phải ép kiểu có chủ đích, kèm kiểm tra miền khi cần.

### 2.2. Một toán hạng là `String`: chuyển thành văn bản rồi nối

Nếu tại một phép `+` nhị phân **một toán hạng có kiểu `String`**, Java dùng phép nối chuỗi. Toán hạng còn lại được biểu diễn bằng văn bản:

```java
String name = "Lan";
int points = 12;
String message = name + " có " + points + " điểm";
// "Lan có 12 điểm"
```

Ở phép nối cuối, số nguyên `points` được chuyển thành biểu diễn văn bản `"12"`. Đó là chuyển đổi **số sang chuỗi**, không phải cộng thêm 12 vào một con số khác.

Các kiểu nguyên thủy như `int`, `long`, `boolean`, `char` đều có thể xuất hiện trong phép nối với `String`. Giá trị tham chiếu cũng có thể nối: `null` được biểu diễn thành văn bản `"null"`; đối tượng khác có cách biểu diễn chuỗi tương ứng, thường liên quan đến `toString()`.

**Lưu ý phạm vi:** phép `+` được phép nối `String`, nhưng Java **không cho phép** dùng `-` hoặc `*` với chuỗi. Ví dụ `"8" - "3"` và `"8" * 3` đều là lỗi biên dịch. Muốn tính số từ chuỗi, phải **parse** sang kiểu số trước.

## 3. Thứ tự đánh giá và tính kết hợp trái gây kết quả bất ngờ

Toán tử `+` nhị phân có **tính kết hợp trái** (*left-associative*): khi không có dấu ngoặc, một dãy phép cộng/nối cùng mức được nhóm từ trái sang phải.

Do đó:

```java
String a = "Kết quả: " + 2 + 3;   // "Kết quả: 23"
String b = "Kết quả: " + (2 + 3); // "Kết quả: 5"
String c = 2 + 3 + " là tổng";     // "5 là tổng"
String d = 2 + "3" + 4;           // "234"
```

Phân tích từng bước:

- `"Kết quả: " + 2 + 3` được nhóm thành `("Kết quả: " + 2) + 3`. Bước đầu đã là nối chuỗi, cho `"Kết quả: 2"`; bước sau tiếp tục nối `"3"`.
- `"Kết quả: " + (2 + 3)`: ngoặc buộc `2 + 3` được tính bằng số nguyên trước, cho 5; sau đó mới nối thành `"Kết quả: 5"`.
- `2 + 3 + " là tổng"` được nhóm thành `(2 + 3) + " là tổng"`. Bước đầu cộng hai số thành 5, bước sau chuyển 5 thành chuỗi rồi nối.
- `2 + "3" + 4`: bước `2 + "3"` đã cho chuỗi `"23"`, nên toán tử tiếp theo nối thêm ký tự `4`; không có phép cộng số `23 + 4`.

**Điểm then chốt:** quyết định phép `+` là cộng hay nối được xét **ở mỗi nút của biểu thức**, không phải một quyết định chung cho toàn dòng. Khi một phần biểu thức đã cho `String`, những phép `+` tiếp theo với phần đó sẽ là nối chuỗi; dấu ngoặc có thể tạo một phép cộng số **độc lập** rồi mới nối.

### Độ ưu tiên với toán tử khác

Phép nhân `*` có độ ưu tiên cao hơn `+`:

```java
String x = "Tổng: " + 2 * 3;       // "Tổng: 6"
String y = "Tổng: " + (2 + 3) * 4; // "Tổng: 20"
```

Dấu ngoặc giúp thể hiện ý định, đặc biệt trong câu log, báo cáo, định dạng thông báo và chuỗi hiển thị kết quả tính toán. Không cần thêm ngoặc ở khắp nơi, nhưng nên dùng khi một người đọc có thể nhầm cộng số với nối chuỗi.

## 4. Chương trình Java 17+ để kiểm chứng

Tạo tệp `PlusOperatorDemo.java`:

```java
public class PlusOperatorDemo {
    public static void main(String[] args) {
        System.out.println("2 + 3 = " + (2 + 3));
        System.out.println("plain addition: " + (2 + 3));
        System.out.println("concat first: " + 2 + 3);
        System.out.println(2 + 3 + " is five");
        System.out.println("mixed: " + 2 + "3" + 4);
        System.out.println("multiply: " + 2 * 3);
        System.out.println("char arithmetic: " + ('A' + 1));
        System.out.println("char concat: " + 'A' + 1);

        String count = "count=";
        count += 4;
        count += 5;
        System.out.println(count);
    }
}
```

Biên dịch và chạy:

```bash
javac PlusOperatorDemo.java
java PlusOperatorDemo
```

Kết quả chính xác:

```text
2 + 3 = 5
plain addition: 5
concat first: 23
5 is five
mixed: 234
multiply: 6
char arithmetic: 66
char concat: A1
count=45
```

Các dòng `char` cho thấy một khác biệt quan trọng. `'A'` là literal **kiểu `char`**, có giá trị code unit số 65. Trong `'A' + 1`, Java nâng `char` lên `int`, cho **66**. Trong `"char concat: " + 'A'`, một toán hạng đã là `String`, nên ký tự **A** được nối vào chuỗi; phép `+ 1` tiếp theo lại nối văn bản **1**.

### `char` không giống `String`

```java
int numeric = '1' + 2;     // 49 + 2 = 51
String text = "1" + 2;      // "12"
String letters = 'A' + "" + 'B'; // "AB"
int codes = 'A' + 'B';      // 65 + 66 = 131
```

Dấu nháy đơn `'A'` biểu diễn `char`; nháy kép `"A"` biểu diễn `String`. Sự khác biệt **kiểu** này quyết định hành vi của `+`.

Một Unicode code point ngoài BMP có thể cần hai `char` (cặp surrogate), vì `char` là **UTF-16 code unit**, không phải mọi ký tự người dùng nhìn thấy. Khi nối một `String` với `char`, Java nối code unit đó theo biểu diễn chuỗi.

## 5. Nối chuỗi không chữa được overflow xảy ra trước đó

Phép cộng số nguyên có độ rộng hữu hạn. Với `int` 32 bit, `Integer.MAX_VALUE` là 2_147_483_647. Nếu cộng 1 **bằng `int`** thì tràn thành -2_147_483_648.

Xét:

```java
int max = Integer.MAX_VALUE;

String a = "sum=" + (max + 1);       // "sum=-2147483648"
String b = "sum=" + max + 1;         // "sum=21474836471"
String c = "sum=" + ((long) max + 1); // "sum=2147483648"
```

- Với `a`, dấu ngoặc buộc cộng hai số `int` trước → **tràn số**, rồi giá trị âm mới được đổi thành văn bản.
- Với `b`, `"sum=" + max` đã tạo chuỗi, nên `+ 1` chỉ nối văn bản `1`, thành một chuỗi số nhìn giống nhưng **không phải tổng số học**.
- Với `c`, `(long) max + 1` được tính bằng `long` nên cho kết quả số đúng, rồi mới nối chuỗi.

Viết `long result = max + 1;` cũng không khắc phục tràn: phép cộng hoàn tất ở `int` trước khi gán. Nếu tràn số phải bị từ chối, dùng `Math.addExact(max, 1)` để Java ném `ArithmeticException`, thay vì tính toán rồi định dạng một số sai.

**Nguyên tắc:** giải quyết **đúng kiểu và đúng phép tính số học trước**, sau đó mới nối phần văn bản trình bày. Đừng dùng giao diện hiển thị chuỗi như một cách kiểm chứng kết quả số.

## 6. Nối chuỗi với số thực, boolean, null và đối tượng

### 6.1. Số thực và boolean

```java
String temperature = "Temp: " + 23.5; // "Temp: 23.5"
String enabled = "Enabled: " + true;  // "Enabled: true"
```

`true` là `boolean`, không được cộng số học với `int`; nhưng `"Enabled: " + true` hợp lệ vì đó là **nối chuỗi**.

Số thực cũng được chuyển sang văn bản trong phép nối. Nếu giao diện cần quy tắc hiển thị rõ ràng (ví dụ hai chữ số thập phân, dấu phân cách theo locale), dùng API định dạng phù hợp thay vì dựa vào cách biểu diễn chuỗi mặc định của `double`.

### 6.2. `null` trong nối chuỗi

Khi một **tham chiếu** là `null` và tham gia phép nối chuỗi, văn bản được thêm là **"null"**:

```java
String name = null;
Object item = null;
System.out.println("name=" + name); // name=null
System.out.println("item=" + item); // item=null
```

Đây không phải một đối tượng `String` thực sự chứa `"null"` ở biến `name`: biến `name` vẫn là tham chiếu `null`. Văn bản `"null"` chỉ được tạo để biểu diễn nó trong chuỗi kết quả.

Với wrapper số như `Integer`, sự phân biệt càng quan trọng:

```java
Integer quantity = null;
System.out.println("quantity=" + quantity); // quantity=null

// int n = quantity + 1; // khi chạy sẽ ném NullPointerException
```

Trường hợp thứ nhất là nối chuỗi với **tham chiếu**; trường hợp thứ hai là cộng số, nên Java phải **unbox** `Integer` thành `int` trước, và việc unbox `null` ném `NullPointerException`.

### 6.3. Đối tượng và `toString()`

Một đối tượng thông thường được chuyển thành biểu diễn văn bản khi nối với `String`. Cách biểu diễn thường do `toString()` quyết định.

```java
record Item(String code, int quantity) {}

Item item = new Item("BK", 2);
String description = "item=" + item;
```

Đây là **đoạn mã minh họa** trong một phạm vi có thể khai báo `record` và sử dụng biến; muốn chạy độc lập cần đặt trong cấu trúc Java hoàn chỉnh. Với record Java, biểu diễn mặc định có dạng `Item[code=BK, quantity=2]` (nếu không ghi đè `toString()`).

**Đừng giả định tất cả đối tượng tự tạo đều có thông tin hữu ích khi nối chuỗi.** Nếu lớp không tự định nghĩa `toString()`, kết quả mặc định thường là tên lớp kèm dấu `@` và mã băm ở dạng hex, không phải các thuộc tính nghiệp vụ. Nếu cần hiển thị mảng, dùng `Arrays.toString(array)` hoặc `Arrays.deepToString(array)` cho mảng lồng phù hợp thay vì chỉ nối mảng với chuỗi.

## 7. Ví dụ xử lý `null` và hiển thị đối tượng có thể chạy

Tạo tệp `StringConversionDemo.java`:

```java
import java.util.Arrays;

public class StringConversionDemo {
    record Product(String code, int count) {}

    public static void main(String[] args) {
        Integer quantity = null;
        String name = null;
        int[] numbers = {1, 2, 3};

        System.out.println("quantity=" + quantity);
        System.out.println("name=" + name);
        System.out.println("array=" + Arrays.toString(numbers));
        System.out.println("product=" + new Product("BK", 2));

        try {
            int next = quantity + 1; // phải unbox null
            System.out.println(next);
        } catch (NullPointerException e) {
            System.out.println("numeric null: NullPointerException");
        }

        System.out.println("boolean=" + true);
        System.out.println("decimal=" + 23.5);
    }
}
```

Chạy:

```bash
javac StringConversionDemo.java
java StringConversionDemo
```

Kết quả:

```text
quantity=null
name=null
array=[1, 2, 3]
product=Product[code=BK, count=2]
numeric null: NullPointerException
boolean=true
decimal=23.5
```

Đoạn mã minh họa vì sao hai phép `+` có thể xử lý cùng một biến `quantity` theo hai cách: `"quantity=" + quantity` là nối chuỗi; `quantity + 1` là phép toán số học cần unboxing.

## 8. `+=`: cộng gán hay nối thêm?

Toán tử `+=` cũng phụ thuộc kiểu của biến bên trái:

```java
int number = 5;
number += 3;        // cộng số: number = 8

String label = "item";
label += 3;         // nối chuỗi: label = "item3"
label += 4;         // nối tiếp: label = "item34"
```

Với biến `String`, `s += x` có hiệu ứng nối giá trị `x` vào chuỗi cũ của `s`; kết quả vẫn là `String`. Với biến số, `+=` dùng phép tính số học và quy tắc gán kết hợp của Java, có thể bao gồm **ép kiểu ngầm** về kiểu biến vế trái.

```java
byte small = 120;
small += 10; // cho -126 do phép cộng int rồi thu hẹp về byte

String text = "120";
text += 10;  // "12010", không có overflow số học
```

Với `String`, toán tử `+=` có thể tạo kết quả mới vì **`String` là bất biến** (*immutable*): nội dung chuỗi đã tồn tại không bị sửa trực tiếp. Việc gán lại khiến biến `text` tham chiếu đến kết quả nối.

**Giới hạn chiều ngược lại:** `int x = 10; x += "20";` là lỗi biên dịch vì không thể gán kết quả chuỗi về biến `int`. Java không tự parse một chuỗi chữ số chỉ vì biến nhận là số.

## 9. Thứ tự đánh giá và tác dụng phụ trong phép `+`

Java đánh giá các toán hạng của toán tử nhị phân **từ trái sang phải**. Nếu toán hạng có hành động thay đổi trạng thái (ví dụ `i++`, gọi phương thức cập nhật biến), thứ tự đó ảnh hưởng đến chuỗi kết quả.

Ví dụ:

```java
int i = 1;
System.out.println("before=" + i++ + ", after=" + i);
```

Kết quả:

```text
before=1, after=2
```

Phép `i++` trả giá trị cũ 1 cho phép nối hiện tại, sau đó tăng `i` thành 2. Toán hạng `", after=" + i` được đánh giá sau nên quan sát được giá trị mới. Thứ tự đánh giá được ngôn ngữ Java xác định; nhưng để code dễ hiểu, tránh đưa nhiều tác dụng phụ vào một biểu thức nối chuỗi dài.

Một lưu ý khác: biểu thức `"result=" + calculate()` **vẫn gọi** `calculate()` trước khi có giá trị chuỗi, ngay cả nếu giá trị sau đó chỉ dùng để hiển thị. Không nên gọi hàm có side effect trong phép nối chỉ để định dạng.

## 10. Chuyển chuỗi chữ số thành số để tính toán thật

Nối chuỗi **không tự parse** chữ số:

```java
String left = "20";
String right = "3";

String joined = left + right;  // "203"
int total = Integer.parseInt(left) + Integer.parseInt(right); // 23
```

Nếu dữ liệu người dùng là số nhưng được nhập dạng text, phải xác thực đầu vào và chuyển bằng API thích hợp, chẳng hạn `Integer.parseInt` hoặc `Long.parseLong`. Khi chuỗi không phải định dạng số hợp lệ hoặc vượt miền kiểu đích, các phương thức parse ném `NumberFormatException`.

Ví dụ:

```java
String price = "120";
String quantity = "3";
int amount = Integer.parseInt(price) * Integer.parseInt(quantity);
// amount = 360
String display = "amount=" + amount; // "amount=360"
```

Trình tự dễ kiểm soát là **parse → tính toán → kiểm tra tràn/miền → định dạng kết quả**. Nếu phép tính có nguy cơ tràn, chọn kiểu rộng hoặc `Math.addExact`/`Math.multiplyExact` phù hợp trước khi chuyển kết quả sang chuỗi.

**Dấu `+` một ngôi:** `+5` và `+number` chỉ là dấu dương số học, không phải nối chuỗi; không thể dùng `+"hello"`. Chủ đề nối chuỗi ở đây nói về **toán tử `+` nhị phân** có hai toán hạng.

## 11. Hiệu năng, `StringBuilder` và cách viết rõ ràng

Vì `String` bất biến, việc nối trong **vòng lặp lớn** có thể tạo ra nhiều chuỗi trung gian và tốn bộ nhớ/cấp phát:

```java
String result = "";
for (int n = 1; n <= 3; n++) {
    result += n;
}
// result = "123"
```

Khi cần tích lũy nhiều đoạn văn bản trong vòng lặp, có thể dùng `StringBuilder`:

```java
StringBuilder builder = new StringBuilder();
for (int n = 1; n <= 3; n++) {
    builder.append(n);
}
String result = builder.toString(); // "123"
```

Một biểu thức nối thông thường như `"name=" + name + ", age=" + age` vẫn là cú pháp tự nhiên, dễ đọc; các phiên bản Java hiện đại có cơ chế tối ưu việc nối chuỗi ở lúc biên dịch/chạy. Không cần biến mọi phép `+` với `String` thành `StringBuilder`. Chỉ cân nhắc builder khi thực sự **lặp lại nhiều lần**, tích lũy văn bản lớn hoặc khi hiệu năng có bằng chứng là vấn đề.

Khi định dạng thông báo nhiều trường, cũng có thể dùng `String.format`, `System.out.printf` hoặc các công cụ định dạng phù hợp. Các API này hữu ích cho cấu trúc hiển thị, độ rộng trường, số chữ số thập phân và locale; bản chất phép cộng số học vẫn phải được xác định trước.

## 12. Lỗi phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách viết rõ ràng hơn |
|---|---|---|
| `"Sum=" + 2 + 3` in `Sum=23` | Nối chuỗi xuất hiện trước phép cộng số | `"Sum=" + (2 + 3)` |
| `2 + "3" + 4` thành `234` | Sau bước đầu kết quả là `String` | Parse/ngoặc phép tính theo mục đích |
| `'1' + 2` cho 51 | `char` thăng cấp thành `int`, '1' có mã 49 | Dùng `"1" + 2` để nối, hoặc chuyển chữ số sang số |
| `"x=" + (max + 1)` in số âm | Phép cộng `int` tràn trước khi nối | Nâng lên `long` hoặc dùng `Math.addExact` |
| `Integer value = null; value + 1` gây NPE | Số học cần unbox tham chiếu null | Kiểm tra null trước khi tính |
| `"obj=" + obj` in thông tin khó đọc | Chuỗi mặc định của đối tượng không mang dữ liệu mong muốn | Viết `toString()` hữu ích hoặc chọn trường rõ ràng |
| `"array=" + array` không in phần tử | Mảng không tự hiển thị nội dung qua phép nối | `Arrays.toString(array)` |
| `int x = 10; x += "20";` lỗi | Kết quả chuỗi không thể gán cho biến số | Parse chuỗi hoặc dùng biến `String` |
| Nối chuỗi lặp nhiều lần gây overhead | `String` bất biến; tích lũy nhiều chuỗi | Dùng `StringBuilder` cho vòng lặp lớn |

## 13. Bài tập tự kiểm tra

**Câu 1.** `System.out.println("Total: " + 10 + 20);` in gì?  
**Đáp án:** `Total: 1020`, vì toán tử đầu đã bắt đầu nối chuỗi.

**Câu 2.** Muốn in `Total: 30` từ hai số 10 và 20, viết gì?  
**Đáp án:** `System.out.println("Total: " + (10 + 20));`.

**Câu 3.** `System.out.println(10 + 20 + " items");` in gì?  
**Đáp án:** `30 items`, vì `10 + 20` là phép cộng số trước khi gặp `String`.

**Câu 4.** `'3' + 1` có bằng `"3" + 1` không?  
**Đáp án:** Không. `'3'` là `char` có mã 51, nên kết quả số là `int` 52; `"3"` là `String`, nên kết quả là `"31"`.

**Câu 5.** `String s = null; String t = "value=" + s;` cho `t` bằng gì?  
**Đáp án:** `"value=null"`. Biến `s` vẫn là tham chiếu `null`.

**Câu 6.** `Integer n = null; System.out.println("n=" + n);` có gây lỗi như `n + 1` không?  
**Đáp án:** Không. Phép đầu nối văn bản `"null"`; phép sau cần unbox `n` và ném `NullPointerException`.

**Câu 7.** Vì sao `"sum=" + (Integer.MAX_VALUE + 1)` in số âm?  
**Đáp án:** Vì tổng hai `int` tràn **trước** khi được chuyển thành chuỗi. Nâng toán hạng lên `long` trước phép cộng nếu cần miền lớn hơn.

**Câu 8.** Khi nào dùng `StringBuilder`?  
**Đáp án:** Khi tích lũy nhiều đoạn chuỗi qua vòng lặp hoặc cần giảm lượng chuỗi trung gian; với một câu ngắn, `+` thường rõ ràng và phù hợp.

**Câu 9.** `String s = "x"; s += 2; s += 3;` cho kết quả gì?  
**Đáp án:** `"x23"`, vì cả hai lần `+=` đều nối văn bản vào biến `String`.

**Câu 10.** `"Result: " + 2 * 3` cho gì, và tại sao?  
**Đáp án:** `"Result: 6"`. Toán tử nhân `*` có độ ưu tiên cao hơn `+`, nên tính số 6 trước khi nối chuỗi.

**Ghi nhớ:** Với `+` nhị phân, **hai toán hạng số → cộng số học; có `String` → nối văn bản**. Java nhóm các phép `+` cùng mức từ trái sang phải. Muốn hiển thị **tổng số**, đặt phép tính trong ngoặc (hoặc tính trước vào biến) rồi mới nối thành chuỗi; kết quả chuỗi không tự sửa lỗi tràn số đã xảy ra.
