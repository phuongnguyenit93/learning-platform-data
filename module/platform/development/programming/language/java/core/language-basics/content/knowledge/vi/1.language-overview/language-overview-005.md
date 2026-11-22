# Kiểu dữ liệu tĩnh và những lỗi được phát hiện khi biên dịch

Một chương trình có thể sai ngay cả khi **chưa chạy**. Ví dụ, bạn muốn lưu số lượng sản phẩm trong một biến số nguyên nhưng lại gán cho biến đó chuỗi `"ba"`. Java sẽ không đợi chương trình gặp dữ liệu này lúc chạy: trình biên dịch `javac` phát hiện rằng hai kiểu không tương thích.

Đây là ý nghĩa quan trọng của **hệ kiểu tĩnh (static typing)**: kiểu của biểu thức và biến được xác định và kiểm tra theo các quy tắc của ngôn ngữ **trong quá trình biên dịch**. Điều này giúp loại sớm nhiều lỗi, nhưng không bảo đảm chương trình không có ngoại lệ khi chạy hoặc luôn cho kết quả nghiệp vụ đúng.

Sau bài này, bạn có thể nhận biết lỗi về kiểu, tự sửa những lỗi biên dịch Java thường gặp, chọn phép chuyển kiểu phù hợp và dự đoán được những tình huống mà kiểm tra kiểu tĩnh chưa thể bảo vệ.

## 1. Kiểu dữ liệu tĩnh nghĩa là gì?

Trong Java, một biến hoặc một biểu thức có **kiểu**. Kiểu cho trình biên dịch biết giá trị có thể được dùng trong những phép toán nào và phương thức nào có thể được gọi.

~~~java
int quantity = 3;
long unitPriceVnd = 120_000L;
boolean available = true;
String productCode = "JAVA-01";
~~~

Ý nghĩa của từng khai báo:

| Thành phần | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `quantity` | `int` | Số lượng nguyên trong phạm vi của `int` |
| `unitPriceVnd` | `long` | Giá tiền theo VND nguyên, có miền giá trị rộng hơn `int` |
| `available` | `boolean` | Chỉ có `true` hoặc `false` |
| `productCode` | `String` | Chuỗi ký tự biểu diễn mã hàng |

Ví dụ:

~~~java
int count = 3;
count = 5;         // Hợp lệ: giá trị mới vẫn là int.
// count = "nam";  // Lỗi biên dịch: String không thể gán cho int.
~~~

Giá trị biến `count` thay đổi từ 3 thành 5, nhưng **kiểu khai báo của biến không đổi**. Hệ kiểu tĩnh không có nghĩa giá trị bất biến.

Đừng nhầm **static typing** với từ khóa **`static`**. `static` dùng khi khai báo thành viên thuộc về lớp; nó không phải từ khóa làm cho một ngôn ngữ trở thành ngôn ngữ có kiểu tĩnh. Một biến instance thông thường vẫn chịu kiểm tra kiểu tĩnh.

### Các nhóm kiểu quan trọng

Java có hai nhóm mà người mới thường cần phân biệt:

- **Primitive:** `byte`, `short`, `int`, `long`, `float`, `double`, `char` và `boolean`. Những biến này lưu giá trị primitive.
- **Reference type:** ví dụ `String`, một lớp tự định nghĩa, interface hoặc kiểu mảng như `int[]`. Một biến kiểu tham chiếu lưu tham chiếu tới đối tượng hoặc có thể là `null` nếu ngữ cảnh cho phép.

~~~java
int age = 20;          // Primitive int
String name = "An";    // Kiểu tham chiếu String
int[] scores = {7, 8}; // Mảng là đối tượng
~~~

`String` không phải một kiểu primitive, dù rất thường xuyên được sử dụng. `null` cũng không phải một chuỗi rỗng; gọi phương thức qua biến tham chiếu đang bằng `null` có thể gây lỗi khi chạy.

## 2. Từ mã nguồn đến kiểm tra kiểu của `javac`

~~~mermaid
flowchart TD
    A["Tệp .java"] --> B["javac: phân tích cú pháp và ngữ nghĩa"]
    B --> C{"Có lỗi biên dịch?"}
    C -->|Có| D["Báo lỗi và yêu cầu sửa mã"]
    C -->|Không| E["Tạo bytecode .class"]
    E --> F["JVM chạy chương trình"]
    F --> G["Kết quả, ngoại lệ lúc chạy hoặc lỗi logic"]
~~~

Một số việc quan trọng mà trình biên dịch có thể kiểm tra:

1. Câu lệnh có đúng ngữ pháp Java không: dấu `;`, ngoặc, từ khóa, cấu trúc lớp.
2. Tên biến, lớp hoặc phương thức được dùng có được khai báo và có thể truy cập từ vị trí đó không.
3. Biểu thức có kiểu phù hợp với phép toán, lời gọi phương thức, phép gán và giá trị trả về không.
4. Biến cục bộ đã chắc chắn được gán giá trị trước khi đọc chưa (*definite assignment*).
5. Đường điều khiển có đáp ứng một số quy tắc như trả về giá trị cho phương thức không có kiểu `void`, xử lý checked exception khi bắt buộc hay không.

Nếu biên dịch thất bại, hãy nhìn vị trí lỗi, đọc loại lỗi và **sửa nguyên nhân trong mã**. Thông báo có thể khác đôi chút giữa phiên bản JDK; đừng phụ thuộc vào một chuỗi thông báo duy nhất.

Cần nhớ: `javac` **không chạy thử tất cả đầu vào** hay tự hiểu yêu cầu nghiệp vụ. Nó có thể chấp nhận một chương trình tính thuế sai công thức nếu các phép toán vẫn đúng kiểu.

## 3. Chương trình Java chạy được: dùng kiểu đúng để mô hình hóa dữ liệu

Hãy tạo tệp chính xác tên **`StaticTypesDemo.java`** và chép mã sau. Ví dụ dùng JDK 17 trở lên, không yêu cầu thư viện ngoài JDK.

~~~java
import java.util.Locale;

public class StaticTypesDemo {
    static long calculateAmount(int quantity, long unitPriceVnd) {
        if (quantity < 0 || unitPriceVnd < 0) {
            throw new IllegalArgumentException(
                    "So luong va don gia phai khong am");
        }
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }

    static String classifyScore(int score) {
        if (score < 0 || score > 10) {
            throw new IllegalArgumentException(
                    "Diem phai tu 0 den 10");
        }
        return score >= 5 ? "Dat" : "Chua dat";
    }

    public static void main(String[] args) {
        int quantity = 3;
        long unitPriceVnd = 120_000L;
        String productCode = "JAVA-01";
        int score = 8;

        long totalVnd = calculateAmount(quantity, unitPriceVnd);
        double average = (7 + 8 + 9) / 3.0;
        boolean canBuy = score >= 5 && quantity > 0;

        System.out.println("Tong tien: " + totalVnd + " VND");
        System.out.println("Ket qua: " + classifyScore(score));
        System.out.printf(
                Locale.ROOT, "Diem TB: %.1f%n", average);
        System.out.println("Duoc mua: " + canBuy);
        System.out.println("Ma hang: " + productCode);
        System.out.println(
                "Chuyen long sang int: " + Math.toIntExact(42L));

        // Thử bỏ chú thích từng dòng sau để xem lỗi javac:
        // quantity = "ba";
        // boolean wrong = 1;
        // int narrowed = 3.5;
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
java -version
javac -version
javac -encoding UTF-8 StaticTypesDemo.java
java StaticTypesDemo
~~~

Kết quả dự kiến:

~~~text
Tong tien: 360000 VND
Ket qua: Dat
Diem TB: 8.0
Duoc mua: true
Ma hang: JAVA-01
Chuyen long sang int: 42
~~~

Diễn giải theo dữ liệu:

- `quantity` có kiểu `int` và `unitPriceVnd` có kiểu `long`. Phương thức `calculateAmount` khai báo đầu vào rõ ràng và trả về `long`.
- `(long) quantity` chuyển số lượng sang `long` trước phép nhân. `Math.multiplyExact` giúp phát hiện nếu **kết quả kiểu long** bị tràn; phép nhân số nguyên thông thường không nhất thiết tự báo lỗi tràn.
- `classifyScore` trả `String`; cả hai nhánh của toán tử `?:` đều trả chuỗi.
- `average` có kiểu `double`. Viết `3.0` để phép chia ra kết quả chấm động, khác với chia hai số nguyên.
- `canBuy` là `boolean` được tạo từ các biểu thức so sánh và toán tử logic `&&`.
- `printf(Locale.ROOT, ...)` cố định dấu thập phân thành `.` để đầu ra ví dụ dễ kiểm chứng trên nhiều cấu hình vùng.

Đọc kiểu trả về là cách rất nhanh để dự đoán phương thức được phép dùng như thế nào:

~~~java
long amount = StaticTypesDemo.calculateAmount(2, 20_000L);
String result = StaticTypesDemo.classifyScore(7);
// boolean result = StaticTypesDemo.classifyScore(7); // Không biên dịch.
~~~

Đoạn cuối chỉ là minh họa khi được đặt trong một phương thức khác; dòng sai đã được chú thích.

## 4. Những lỗi kiểu dữ liệu `javac` phát hiện sớm

Mỗi ví dụ trong bảng dưới đây được cố ý viết sai. Hãy **chỉ thử một lỗi mỗi lần** để không bị nhiều thông báo che mất nguyên nhân.

| Dòng mã không hợp lệ | Vì sao không biên dịch? | Hướng sửa |
| --- | --- | --- |
| `int count = "3";` | `String` không tự chuyển thành `int` | `Integer.parseInt("3")` khi dữ liệu đến từ chuỗi |
| `String label = 3;` | Không có phép gán tự động từ `int` thành `String` | `String.valueOf(3)` hoặc `"3"` |
| `boolean active = 1;` | Java không xem số 1 là `true` | Dùng `true` hoặc một biểu thức điều kiện |
| `int amount = 3.5;` | Literal chấm động không thể thu hẹp tự động thành `int` | Chọn `double` hoặc làm tròn/chuyển kiểu có chủ đích |
| `char symbol = "A";` | `"A"` là `String`, còn `char` là một đơn vị mã UTF-16 | Dùng `'A'` khi muốn `char` |
| `int number = 3_000_000_000;` | Literal số nguyên không hậu tố vượt miền `int` | Dùng `long number = 3_000_000_000L;` |
| `unknownName++;` | Không có khai báo tên phù hợp trong phạm vi | Khai báo đúng tên/kiểm tra chính tả |
| `int x = Math.toIntExact("5");` | Tham số yêu cầu `long`, không phải `String` | Chuyển chuỗi thành số bằng API thích hợp trước |
| `return "text";` trong method khai báo trả `int` | Kiểu trả về không tương thích | Trả `int` hoặc đổi hợp đồng method |

Không phải lúc nào thông báo lỗi nằm chính xác ở dòng gây ra nguyên nhân. Một dấu ngoặc thiếu phía trước có thể làm `javac` báo lỗi ở nhiều dòng sau. Hãy sửa lỗi đầu tiên hợp lý, biên dịch lại rồi mới xem tiếp.

### Thử một lỗi thật bằng tệp ngắn

Tạo riêng `WrongType.java`:

~~~java
public class WrongType {
    public static void main(String[] args) {
        int quantity = "ba";
        System.out.println(quantity);
    }
}
~~~

Chạy:

~~~bash
javac WrongType.java
~~~

Biên dịch **thất bại** vì không thể chuyển `String` thành `int`. Không cần học thuộc từng từ của thông báo; trọng tâm là xác định vế nhận cần `int` và vế gán lại là `String`. Sửa:

~~~java
int quantity = Integer.parseInt("3");
~~~

Dòng sửa biên dịch được, nhưng `Integer.parseInt("ba")` vẫn ném `NumberFormatException` **khi chạy**. Như vậy, kiểu tĩnh ngăn việc gán sai loại dữ liệu nhưng không bảo đảm chuỗi đầu vào chứa số hợp lệ.

## 5. Chuyển kiểu: mở rộng, thu hẹp và mất dữ liệu

Java cho phép một số phép chuyển kiểu **mở rộng tự động** (*widening conversion*), nhưng nhiều phép chuyển thu hẹp đòi hỏi ép kiểu hoặc một phương thức kiểm tra.

~~~java
int small = 42;
long larger = small; // Hợp lệ: int -> long, giữ nguyên giá trị.

// int narrowed = larger; // Lỗi biên dịch: long -> int.
// int narrowed = (int) larger; // Có thể biên dịch nhưng có nguy cơ mất dữ liệu.

int checked = Math.toIntExact(larger); // 42; ném lỗi nếu ngoài miền int.
~~~

Khi ép kiểu rõ ràng, trình biên dịch biết bạn **chủ ý cho phép phép chuyển**, nhưng không chứng minh giá trị vẫn chính xác. Ví dụ:

~~~java
long big = 3_000_000_000L;
int unsafe = (int) big; // Biên dịch, nhưng giá trị int không còn là 3000000000.
// Math.toIntExact(big); // Ném ArithmeticException vì quá miền int.
~~~

### Hai phép chia trông gần giống nhau

~~~java
int a = 10;
int b = 4;

double first = a / b;          // 2.0: chia int trước, rồi đổi sang double.
double second = (double) a / b; // 2.5: chuyển a sang double trước khi chia.
~~~

Kiểu biểu thức quyết định phép chia được thực hiện theo quy tắc nào. Việc biến kết quả khai báo `double` không thể làm phần thập phân đã bị mất ở phép chia số nguyên tự xuất hiện trở lại.

Đặc biệt, hằng số kiểu `int` có thể được Java cho phép gán vào `byte`, `short` hoặc `char` khi compiler **biết giá trị nằm trong miền hợp lệ**, nhưng điều đó không có nghĩa mọi biến `int` đều thu hẹp tự động. Ví dụ:

~~~java
byte smallConstant = 100; // Hợp lệ: hằng int trong miền byte.
int generalNumber = 100;
// byte copy = generalNumber; // Không biên dịch: giá trị biến có thể thay đổi.
~~~

Không nên ép kiểu chỉ để “hết lỗi đỏ”. Trước khi ép, hãy hỏi **miền giá trị, độ chính xác và ý nghĩa nghiệp vụ** của dữ liệu.

## 6. Biến chưa được gán và từ khóa `final`

Với **biến cục bộ**, Java yêu cầu biến đã được **gán chắc chắn** trước khi đọc. Ví dụ:

~~~java
public class DefiniteAssignmentDemo {
    public static void main(String[] args) {
        int score;
        boolean hasExam = true;

        if (hasExam) {
            score = 8;
        }

        // System.out.println(score); // Không biên dịch:
        // nhánh hasExam == false có thể khiến score chưa được gán.

        int safeScore = hasExam ? 8 : 0;
        System.out.println(safeScore); // 8
    }
}
~~~

Một biến field được khởi tạo mặc định theo quy tắc Java, nhưng không vì thế mà biến cục bộ không được gán lại tự có giá trị 0. Đây là hai tình huống khác nhau.

`final` ngăn **gán lại biến** sau khi đã được gán theo quy tắc definite assignment:

~~~java
final int passMark = 5;
// passMark = 6; // Không biên dịch: không được gán lại.

final StringBuilder text = new StringBuilder("Java");
text.append(" core"); // Hợp lệ: nội dung đối tượng vẫn có thể đổi.
// text = new StringBuilder(); // Không biên dịch: gán lại tham chiếu final.
~~~

**`final` không tự biến đối tượng thành bất biến.** Với kiểu tham chiếu, nó bảo vệ *giá trị tham chiếu của biến*, không cấm mọi thay đổi bên trong đối tượng.

## 7. Kiểu của biến tham chiếu và khả năng gọi phương thức

Cùng một đối tượng có thể được giữ qua các biến có **kiểu khai báo khác nhau**. Trình biên dịch kiểm tra lời gọi dựa trên **kiểu của biểu thức ở vị trí gọi**, không chỉ dựa trên lớp runtime của đối tượng.

~~~java
Object value = "Hello";

// System.out.println(value.length()); // Không biên dịch:
// Object không công bố method length().

String text = (String) value;
System.out.println(text.length()); // 5
~~~

Dòng ép kiểu làm chương trình biên dịch, nhưng không đảm bảo luôn an toàn với mọi đối tượng:

~~~java
Object value = Integer.valueOf(42);
// String text = (String) value; // Biên dịch được nếu bỏ comment,
// nhưng khi chạy sẽ ném ClassCastException.
~~~

Trong một phương thức thật, nên tránh ép kiểu không có cơ sở. Nếu cần kiểm tra, dùng `instanceof` để xác định một đối tượng có kiểu tương thích trước khi sử dụng:

~~~java
Object item = "Java";
if (item instanceof String) {
    String text = (String) item;
    System.out.println(text.length()); // 4
}
~~~

Tính đa hình còn khiến **triển khai nào của một instance method được thực thi** phụ thuộc vào đối tượng runtime. Kiểm tra kiểu của lời gọi khi biên dịch và lựa chọn phần triển khai lúc chạy là hai lớp cơ chế khác nhau, không mâu thuẫn với nhau.

### Generic giúp bắt lỗi tập hợp sai kiểu

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("An");
// names.add(42); // Không biên dịch: danh sách khai báo nhận String.

String first = names.get(0); // Kiểu kết quả được kiểm tra là String.
~~~

Generics tăng khả năng kiểm tra tĩnh, nhưng Java sử dụng *type erasure* ở nhiều khía cạnh của việc thực thi generic. Dùng raw type, ép kiểu không an toàn hoặc dữ liệu ngoài chương trình có thể khiến lỗi xuất hiện khi chạy. Vì vậy, **generic không phải bằng chứng chương trình miễn nhiễm với mọi lỗi kiểu**.

## 8. `var` vẫn là kiểu tĩnh, không phải biến kiểu động

Từ Java 10, trong một số khai báo biến cục bộ, có thể để trình biên dịch **suy luận kiểu** từ biểu thức khởi tạo:

~~~java
var count = 3;         // Suy luận int.
var title = "Java";    // Suy luận String.

count = 5;             // Hợp lệ.
// count = "five";     // Không biên dịch: count đã được suy luận là int.
~~~

`var` không có nghĩa biến sẽ tự đổi kiểu qua từng phép gán. Nó cũng không thay thế được kiểu khai báo ở mọi nơi:

~~~java
// var withoutValue; // Không hợp lệ: thiếu giá trị khởi tạo.
// var empty = null;  // Không thể suy luận kiểu từ null.
// void test(var x) {} // Không dùng var như kiểu tham số method thường.
~~~

Dùng `var` khi kiểu đã hiển nhiên và mã dễ đọc hơn; dùng tên kiểu tường minh khi điều đó giúp người học hoặc người bảo trì nhìn rõ hợp đồng của dữ liệu.

## 9. Những lỗi không được hệ kiểu tĩnh loại bỏ hoàn toàn

So sánh ba tình huống:

| Loại vấn đề | Ví dụ | Java phát hiện khi nào? |
| --- | --- | --- |
| Sai kiểu hoặc cú pháp | `int score = "8";` | Khi biên dịch |
| Ngoại lệ lúc chạy | `10 / zero` với `zero = 0` ở runtime | Khi chạy đến phép toán |
| Sai logic | Dùng `>` thay vì `>=` cho ngưỡng đạt | Có thể chạy bình thường; cần kiểm thử theo yêu cầu |

Ví dụ những đoạn **có thể biên dịch** nhưng vẫn gặp vấn đề:

~~~java
int zero = 0;
// System.out.println(10 / zero); // Ném ArithmeticException khi chạy.

int[] values = {2, 4};
// System.out.println(values[2]); // Ném ArrayIndexOutOfBoundsException.

String message = null;
// System.out.println(message.length()); // Ném NullPointerException.

int tooLarge = Integer.MAX_VALUE;
tooLarge++;
System.out.println(tooLarge); // -2147483648: int tràn và quay vòng.
~~~

Ở ví dụ cuối, Java không tự ném lỗi khi tăng `int` thông thường vượt miền. Khi cần phát hiện tràn trong phép cộng số nguyên, có thể dùng `Math.addExact(...)` hoặc một phương pháp kiểm tra miền giá trị phù hợp.

### Checked exception cũng được kiểm tra lúc biên dịch

Một số API có thể khai báo **checked exception**. Java yêu cầu caller **bắt hoặc khai báo tiếp** các loại checked exception cần xử lý. Ví dụ:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ReadTextDemo {
    static String readText(Path path) throws IOException {
        return Files.readString(path);
    }
}
~~~

Ở đây, chữ ký `throws IOException` thừa nhận thao tác đọc có thể thất bại khi chạy. Trình biên dịch giúp kiểm tra sự hiện diện của cơ chế **bắt hoặc khai báo**, nhưng không dự đoán tệp có tồn tại, quyền đọc có hợp lệ hay ổ đĩa có gặp lỗi hay không.

Ngược lại, các lỗi runtime phổ biến như `NullPointerException` thường là *unchecked exception*; Java không bắt buộc method phải ghi `throws NullPointerException` hoặc caller phải bắt nó.

## 10. Cách đọc và sửa thông báo lỗi `javac`

Khi thấy thông báo lỗi, hãy làm theo quy trình:

1. **Xác định tệp và dòng lỗi.** Đọc biểu thức ngay tại dòng đó và vài dòng trước nếu cần.
2. **Tìm kiểu được yêu cầu và kiểu đang có.** Ví dụ vế trái cần `int` nhưng biểu thức bên phải là `String`.
3. **Xem dữ liệu có đúng ý nghĩa không.** Số lượng nên là số, mã hàng thường là chuỗi; đừng ép kiểu sai bản chất.
4. **Chọn cách sửa an toàn:** sửa khai báo, chuyển chuỗi bằng API có kiểm tra, bổ sung gán giá trị, hoặc thay lời gọi phương thức đúng.
5. **Biên dịch lại** sau mỗi nhóm sửa nhỏ, sau đó **chạy và kiểm thử** vì hết lỗi compile chưa đồng nghĩa đúng yêu cầu.

Một số dạng thông báo thường gặp:

| Dấu hiệu | Hướng điều tra |
| --- | --- |
| `incompatible types` | Sai kiểu khi gán, trả về hoặc truyền tham số |
| `cannot find symbol` | Sai tên, thiếu khai báo hoặc thiếu import |
| `possible lossy conversion` | Chuyển thu hẹp có nguy cơ mất dữ liệu |
| `variable ... might not have been initialized` | Biến cục bộ chưa được gán chắc chắn |
| `method ... cannot be applied to given types` | Sai số lượng hoặc kiểu đối số |
| `unreported exception ...` | Checked exception chưa bắt/khai báo |
| `';' expected` | Có thể thiếu dấu kết thúc câu lệnh hoặc cú pháp trước đó sai |

Đừng sửa lỗi bằng cách đổi mọi thứ sang `String` hoặc chèn ép kiểu hàng loạt. Như vậy có thể làm chương trình biên dịch được nhưng mất kiểm soát dữ liệu và vẫn sai khi chạy.

## 11. Các trường hợp biên đáng kiểm tra

Bảng sau nhấn mạnh rằng kiểm tra kiểu và kiểm tra **giá trị hợp lệ** là hai việc bổ sung cho nhau.

| Trường hợp | `javac` có chặn không? | Điều gì cần xảy ra? |
| --- | --- | --- |
| `int age = "20";` | Có | Sửa kiểu/giao tiếp chuyển chuỗi |
| `int age = -1;` | Không | Nếu tuổi không được âm, tự kiểm tra quy tắc |
| `Long.parseLong("abc")` | Không | Khi chạy có thể ném `NumberFormatException` |
| `int x = Integer.MAX_VALUE; x++;` | Không | Tràn theo ngữ nghĩa `int`; cần kiểm tra nếu không được phép |
| `long big = 3_000_000_000;` | Có | Literal cần hậu tố `L` |
| `byte x = 100;` | Không | Hằng nằm trong giới hạn `byte` |
| `byte x = 200;` | Có | Hằng vượt miền `byte` |
| `Object x = "Hi"; x.length();` | Có | Kiểu `Object` không công bố `length()` |
| `Object x = 42; (String) x;` | Không đối với cast hợp lệ về mặt kiểu | Có thể `ClassCastException` khi chạy |
| `String s = null; s.length();` | Thường không | Có thể `NullPointerException` khi chạy |
| `double x = 10 / 4;` | Không | Kết quả là `2.0`, cần đổi cách chia nếu muốn `2.5` |
| `int[] a = {1}; a[1]` | Không | Có thể `ArrayIndexOutOfBoundsException` |

Lưu ý về dòng ép kiểu ở bảng: dạng `(String) x` là một **biểu thức**; trong chương trình Java cần đặt nó vào một câu lệnh hợp lệ, ví dụ `String text = (String) x;`. Mục đích ở đây là minh họa khả năng kiểm tra kiểu, không phải tệp mã độc lập.

## 12. Bài tập tự luyện và đáp án

**Bài 1 — Tìm lỗi biên dịch.** Đọc đoạn sau và chỉ ra vì sao từng dòng bị chú thích sẽ sai nếu bỏ chú thích:

~~~java
int tickets = 2;
// tickets = "two";
// boolean paid = 1;
// char grade = "A";
~~~

*Đáp án:* `tickets` đã có kiểu `int`, chuỗi không gán được trực tiếp; `boolean` không dùng 1 thay cho `true`; `char` cần một literal `'A'` thay vì `String` `"A"`.

**Bài 2 — Sửa phép chia.**

~~~java
int sum = 7 + 8 + 9;
double average = sum / 3;
System.out.println(average);
~~~

*Dự đoán:* In `8.0` vì chia nguyên cho ra 8. Để diễn đạt đúng ý định nếu tổng không chia hết, viết `(double) sum / 3` hoặc `sum / 3.0`. Với tổng này, cả hai cách vẫn cho 8.0; thử `sum = 25` để thấy khác biệt (chia nguyên thành 8, chia chấm động thành khoảng 8.333...).

**Bài 3 — Lỗi runtime hay compile?** Với `Object anything = "Java";`, vì sao `anything.length()` không được biên dịch, nhưng `((String) anything).length()` lại hợp lệ? Nếu thay đối tượng thực thành `Integer.valueOf(7)` thì chuyện gì xảy ra?

*Đáp án:* Kiểu khai báo `Object` không có `length()`; cast sang `String` mở quyền gọi ở mức biên dịch. Nếu runtime là `Integer`, ép sang `String` gây `ClassCastException`.

**Bài 4 — Giá trị lớn.** Tại sao `long money = 3_000_000_000;` không biên dịch? Viết đúng và giải thích vì sao chỉ đổi kiểu biến ở vế trái chưa đủ.

*Đáp án:* Literal không hậu tố được xử lý theo quy tắc literal `int` và quá miền; dùng `3_000_000_000L`, hậu tố `L` cho literal kiểu `long`.

**Bài 5 — Thiết kế ca kiểm thử.** Viết phương thức `static int positiveCount(String raw)` nhận chuỗi số nguyên và từ chối số âm. Phân biệt các lỗi cần xử lý cho ba input `"5"`, `"-2"` và `"abc"`.

*Gợi ý một lời giải:*

~~~java
static int positiveCount(String raw) {
    int count = Integer.parseInt(raw);
    if (count < 0) {
        throw new IllegalArgumentException("Khong duoc am");
    }
    return count;
}
~~~

Kết quả: `"5"` trả 5; `"-2"` ném `IllegalArgumentException` theo quy tắc; `"abc"` ném `NumberFormatException` khi parse (là lớp con của `IllegalArgumentException`). Dù mã hợp lệ về kiểu, phải **kiểm tra dữ liệu** lúc chạy.

**Bài 6 — Phân biệt `final` và kiểu tĩnh.** Cho `final StringBuilder sb = new StringBuilder("A");`. Vì sao `sb.append("B")` chạy được nhưng `sb = new StringBuilder("C")` lại không biên dịch?

*Đáp án:* `final` cấm gán lại biến sau khi đã gán; đối tượng `StringBuilder` vẫn mutable. Kiểu của `sb` không đổi trong cả hai trường hợp.

## 13. Checklist trước khi nộp một chương trình Java

- [ ] Tệp `.java` và lớp `public` khớp tên.
- [ ] Tên biến có ý nghĩa và kiểu phù hợp với đơn vị, miền giá trị.
- [ ] Không gán nhầm `String` cho kiểu số hoặc `int` cho `boolean`.
- [ ] Hiểu chuyển kiểu mở rộng/thu hẹp và nguy cơ mất dữ liệu.
- [ ] Biến cục bộ đã được gán chắc chắn trước khi dùng.
- [ ] Tham số truyền vào đúng kiểu và số lượng phương thức yêu cầu.
- [ ] Không dùng cast chỉ để né lỗi kiểu; có kiểm tra khi cần.
- [ ] Giá trị đầu vào được validate theo quy tắc nghiệp vụ.
- [ ] Đã biên dịch bằng `javac`, chạy bằng `java` và thử trường hợp biên.
- [ ] Phân biệt **hết lỗi biên dịch** với **không còn lỗi khi chạy và kết quả đúng**.

## Ghi nhớ

**Kiểu dữ liệu tĩnh là một hàng rào phát hiện sớm**, giúp Java từ chối nhiều cách dùng dữ liệu sai trước khi chạy. Khi compiler báo lỗi, hãy hỏi “biểu thức này có kiểu gì?” và “vị trí sử dụng đòi hỏi kiểu gì?”. Nhưng khi compiler không báo lỗi, bạn vẫn phải hỏi “giá trị có hợp lệ không?” và “thuật toán có đúng yêu cầu không?”. Hiểu cả ba lớp — **kiểm tra kiểu, kiểm tra dữ liệu, kiểm tra logic** — là nền tảng để viết Java đáng tin cậy.
