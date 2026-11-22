# Thử biểu thức, biến và phương thức với JShell

## 1. JShell dùng để làm gì?

**JShell** là công cụ REPL (*Read–Evaluate–Print Loop*) đi kèm **JDK từ Java 9**. Bạn nhập một đoạn Java nhỏ (*snippet*), JShell biên dịch/đánh giá đoạn đó, hiển thị kết quả hoặc thông báo lỗi, rồi cho phép nhập tiếp. Đây là cách nhanh để tự kiểm tra một phép tính, thử API, tạo biến và khai báo phương thức **mà chưa cần tạo một class có `main`**.

~~~text
Bạn nhập biểu thức / khai báo / lệnh JShell
                 |
                 v
       JShell xử lý snippet Java
                 |
        +--------+---------+
        |                  |
     Hợp lệ              Có lỗi
        |                  |
  Cập nhật trạng thái     In chẩn đoán
  và hiện kết quả         không nhận snippet lỗi
        |
     Nhập tiếp
~~~

Khác với terminal hệ điều hành, dấu nhắc **`jshell>`** là nơi nhập *mã Java và lệnh nội bộ JShell*. Các lệnh `javac`, `java`, `cd` hay `ls` là lệnh shell hệ điều hành, không phải biểu thức Java để gõ trực tiếp tại `jshell>`.

JShell rất phù hợp để học ngôn ngữ, khám phá API và dựng ví dụ nhỏ. Nó không thay thế việc viết chương trình có cấu trúc, bộ test tự động hoặc hệ thống build cho dự án thực tế.

## 2. Chuẩn bị JDK và mở JShell

Bài này dùng **JDK 17 trở lên**. Mở Bash, PowerShell hoặc terminal của IDE và gõ:

**Bash (Linux/macOS/Git Bash):**

~~~bash
java -version
javac -version
jshell --version
jshell
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
jshell --version
jshell
~~~

Khi công cụ sẵn sàng, bạn thường thấy phần chào mừng và dấu nhắc gần giống:

~~~text
|  Welcome to JShell -- Version 17...
|  For an introduction type: /help intro

jshell>
~~~

Phiên bản và lời chào có thể khác theo bản JDK, tùy chọn và môi trường. Bạn **chỉ nhập phần sau `jshell>`**, không gõ lại dấu nhắc. Nếu hệ thống báo `jshell` không được nhận diện, kiểm tra bạn đã cài **JDK** và thư mục `bin` của JDK có trên `PATH`; việc chỉ có một runtime Java hoặc cấu hình `PATH` sai có thể làm thiếu công cụ này.

JShell nhận snippet ngay khi đoạn mã hoàn chỉnh. Với khai báo nhiều dòng hoặc block chưa đóng, nó sẽ tiếp tục chờ bạn hoàn thiện, thường bằng dấu nhắc nối dòng.

## 3. Thử biểu thức và quan sát kết quả

Nhập lần lượt vào JShell:

~~~java
2 + 3 * 4
(2 + 3) * 4
7 / 2
7.0 / 2
"Java".toUpperCase()
Math.max(10, 25)
~~~

Kết quả giá trị theo thứ tự là:

| Biểu thức | Giá trị | Vì sao? |
|---|---|---|
| `2 + 3 * 4` | `14` | Nhân có ưu tiên cao hơn cộng |
| `(2 + 3) * 4` | `20` | Ngoặc đổi cách nhóm |
| `7 / 2` | `3` | Hai toán hạng nguyên nên chia nguyên |
| `7.0 / 2` | `3.5` | Có toán hạng `double` |
| `"Java".toUpperCase()` | `"JAVA"` | Gọi phương thức `String` |
| `Math.max(10, 25)` | `25` | Trả số lớn hơn |

Ví dụ JShell có thể hiển thị kết quả của một biểu thức như:

~~~text
jshell> 2 + 3 * 4
$1 ==> 14
~~~

`$1` là **biến tạm tự sinh** cho kết quả snippet; ở phiên của bạn có thể là `$2`, `$3`... nếu đã nhập thêm lệnh khác. Vì vậy, khi hướng dẫn một phép tính cụ thể, hãy dựa vào **giá trị bên phải `==>`**, không lệ thuộc số thứ tự `$n`.

JShell cũng có thể nhận dấu `;` ở cuối các snippet thích hợp. Với biểu thức tương tác đơn giản, bỏ dấu chấm phẩy thường tiện hơn; khi viết chương trình Java trong tệp, hãy tuân thủ cú pháp đầy đủ của câu lệnh.

## 4. Tạo, đọc và cập nhật biến

Thử một giao dịch mua hàng rất nhỏ:

~~~java
int unitPrice = 120_000;
int quantity = 3;
int subtotal = unitPrice * quantity;
subtotal
quantity = 4;
subtotal
subtotal = unitPrice * quantity;
subtotal
~~~

Các giá trị đáng kiểm tra:

| Bước | Kết quả |
|---|---|
| Tạo `unitPrice` và `quantity` | 120.000 và 3 |
| Tính `subtotal` lần đầu | 360.000 |
| Gán lại `quantity = 4` | `quantity` là 4 |
| Đọc `subtotal` ngay sau đó | **Vẫn là 360.000** |
| Gán lại `subtotal = unitPrice * quantity` | **480.000** |

**Lưu ý:** biến `subtotal` giữ **giá trị đã tính tại thời điểm gán**, không phải một công thức bảng tính tự động cập nhật khi `quantity` thay đổi.

Bạn có thể hỏi JShell trạng thái hiện tại:

~~~text
/vars
~~~

Nó liệt kê các biến đã tạo trong phiên cùng kiểu/giá trị. Nếu nhập:

~~~java
var label = "Don hang";
label.length()
~~~

`var` suy ra kiểu `String` từ giá trị khởi tạo; Java vẫn kiểm tra kiểu tĩnh. `var` không có nghĩa biến được phép thay đổi sang một kiểu tùy ý về sau.

### Khi khai báo lại một tên

Trong JShell, bạn có thể thử:

~~~java
int level = 1;
level = 2;
level
~~~

Đây là **gán lại**, không phải khai báo mới. JShell còn hỗ trợ thay thế một snippet đã khai báo bằng snippet mới trong môi trường tương tác. Tuy nhiên, đừng nhầm quy tắc tiện dụng đó với việc có thể khai báo trùng hai biến cục bộ cùng tên trong một block Java bình thường.

## 5. Khai báo phương thức rồi gọi ngay

Một phương thức giúp đặt tên cho phép tính và thử cùng logic với nhiều đối số.

Nhập vào JShell:

~~~java
int square(int n) { return n * n; }
square(5)
square(-3)
~~~

Kết quả gọi lần lượt là `25` và `9`.

Tiếp theo:

~~~java
long lineTotal(long unitPrice, int quantity) {
    if (unitPrice < 0 || quantity < 0) {
        throw new IllegalArgumentException("Gia hoac so luong am");
    }
    return Math.multiplyExact(unitPrice, (long) quantity);
}
lineTotal(120_000L, 3)
lineTotal(120_000L, 4)
~~~

Giá trị lần lượt là `360000` và `480000`. JShell cho phép khai báo method tương tự thành viên của class, nhưng không yêu cầu bạn gõ cả `public class Demo { ... }` cho mỗi phép thử.

Kiểm tra danh sách method:

~~~text
/methods
~~~

### Biểu thức và lời gọi method khác nhau thế nào?

- `square(5)` là **biểu thức gọi method** có giá trị trả về `25`.
- `System.out.println(square(5));` là **câu lệnh gọi method** tạo hiệu ứng in ra `25`; `println` trả về `void`.
- `square` được định nghĩa trong trạng thái phiên JShell; bạn có thể gọi lại mà không khai báo lại ở mỗi dòng.

Một method cần phù hợp kiểu trả về: `int square(int n) { return "abc"; }` bị từ chối do `String` không thể trở thành `int` trong phép `return` này.

## 6. Thử nhanh điều kiện, chuỗi và null

Nhập lần lượt:

~~~java
int amount = 300_000;
boolean activeMember = true;
activeMember && amount >= 200_000
String customer = null;
customer != null && !customer.isBlank()
"Java".equals(customer)
~~~

Giá trị các biểu thức boolean lần lượt là **`true`**, **`false`**, **`false`**.

Phân tích:

- `&&` là toán tử ngắn mạch: khi `customer != null` là `false`, vế sau **không được đánh giá**, tránh gọi `isBlank()` trên `null`.
- `"Java".equals(customer)` an toàn với `customer == null`, vì đối tượng gọi method là chuỗi literal khác null.
- Với kiểu tham chiếu, `==` kiểm tra hai tham chiếu có cùng object hay không; nó không phải phép so sánh nội dung chuỗi chung cho mọi trường hợp.

Thử điều kiện ba ngôi:

~~~java
String category = amount >= 300_000 ? "LON" : "NHO";
category
~~~

Kết quả là `"LON"`. Khi cần nhiều nhánh hoặc xử lý phức tạp, viết method và dùng `if` sẽ dễ đọc hơn ghép nhiều toán tử ba ngôi lồng nhau.

## 7. Nhận diện lỗi từ phản hồi JShell

JShell thử biên dịch snippet và báo lỗi khi cú pháp, tên hoặc kiểu không hợp lệ:

| Thử trong JShell | Kết quả cần nhận ra |
|---|---|
| `int age = "hai muoi";` | Lỗi kiểu: không thể gán `String` vào `int` |
| `missing + 1` | Lỗi tên: biến `missing` chưa được định nghĩa |
| `square("5")` | Lỗi truyền đối số không phù hợp với `square(int)` |
| `7 / 0` | Phép chia nguyên cho 0 gây `ArithmeticException` **khi đánh giá** |
| `String s = null; s.length()` | `NullPointerException` khi gọi method qua `null` |
| `int x = Integer.MAX_VALUE; x + 1` | Tràn số `int`, kết quả là `-2147483648` |

Câu chữ cụ thể của thông báo lỗi có thể khác giữa các phiên bản JDK, nên hãy đọc **loại lỗi** và snippet gây lỗi thay vì học thuộc toàn bộ chuỗi thông báo.

Nếu một snippet lỗi bị từ chối, các snippet hợp lệ trước đó thông thường vẫn có trong trạng thái phiên; bạn có thể sửa và nhập lại.

Một biểu thức có thể **đúng cú pháp mà sai ý định**. Chẳng hạn `7 / 2` trả `3` chính xác theo quy tắc chia nguyên của Java, nhưng nếu bài toán yêu cầu `3.5` thì bạn cần đổi biểu thức sang `7.0 / 2`. JShell giúp quan sát hành vi, không thể tự đoán yêu cầu nghiệp vụ của bạn.

## 8. Lệnh JShell để xem và quản lý phiên

Những lệnh mở đầu bằng dấu `/` là **lệnh riêng của JShell**, không phải phép chia hay cú pháp Java.

| Lệnh | Tác dụng |
|---|---|
| `/help` | Xem trợ giúp và các lệnh hỗ trợ |
| `/help intro` | Xem hướng dẫn nhập môn |
| `/vars` | Liệt kê biến trong phiên |
| `/methods` | Liệt kê các method đã khai báo |
| `/types` | Liệt kê các kiểu đã định nghĩa |
| `/imports` | Xem các import đang dùng |
| `/list` | Hiển thị các snippet trong phiên kèm ID |
| `/drop <id-or-name>` | Bỏ snippet/khai báo đã chọn |
| `/reset` | Đặt lại trạng thái snippets, hữu ích khi muốn làm từ đầu |
| `/save <file>` | Lưu các snippet dưới dạng văn bản nguồn |
| `/open <file>` | Nạp và thực hiện snippets từ tệp |
| `/exit` | Thoát JShell |

Các ID cụ thể phụ thuộc lịch sử phiên. Hãy xem `/list` để xác định ID trước khi dùng `/drop`. Không chọn ID theo ảnh chụp của người khác.

Ví dụ:

~~~text
jshell> /vars
jshell> /methods
jshell> /list
jshell> /reset
jshell> /exit
~~~

Sau `/reset`, thử gọi lại `square(5)`: nếu bạn chưa nhập lại định nghĩa `square`, JShell không còn tìm thấy method ấy. Đây là cách chứng minh trạng thái JShell **thuộc phiên tương tác**, không tự trở thành một class trong dự án.

## 9. Lưu một bài thử JShell để dùng lại

Bạn có thể tạo tệp tên **`practice.jsh`** bằng editor, chứa các snippet Java sau (không cần `package`, không cần `main`):

~~~java
int price = 50_000;
int count = 2;
int subtotal = price * count;
int discounted(long amount, int percent) {
    if (amount < 0 || percent < 0 || percent > 100) {
        throw new IllegalArgumentException("Du lieu khong hop le");
    }
    return (int) (amount * (100 - percent) / 100);
}
subtotal
discounted(subtotal, 10)
~~~

Từ JShell, trong thư mục chứa tệp, nhập:

~~~text
/open practice.jsh
/vars
/methods
~~~

**Kết quả giá trị cần xác nhận:** `subtotal = 100000`, `discounted(subtotal, 10) = 90000`. Dạng hiển thị còn phụ thuộc cấu hình feedback của JShell.

Tệp `.jsh` dùng để lưu các snippet phiên, không phải một class Java biên dịch được bằng `javac practice.jsh`. Nếu muốn lưu trực tiếp những snippet bạn đã nhập trong phiên, dùng `/save practice.jsh`, rồi có thể `/reset` và `/open practice.jsh` để thử lại.

**Giới hạn số học của demo:** method `discounted` trong file chỉ dùng giá nhỏ cho bài thử nhanh; việc `amount * (100 - percent)` có thể tràn `long`, và ép `long` sang `int` có thể mất thông tin. Vì vậy không dùng đoạn này làm mô-đun tính tiền sản xuất. Ở bài tập cuối, bạn sẽ sửa cả công thức lẫn kiểu trả về.

### Chạy file snippet từ terminal

JShell có thể được khởi động với file snippets, ví dụ từ thư mục có `practice.jsh`:

**Bash:**

~~~bash
jshell practice.jsh
~~~

**PowerShell:**

~~~powershell
jshell .\practice.jsh
~~~

Dù chạy theo cách nào, các snippets được đánh giá trong JShell; bạn không có một file class ứng dụng chứa `public static void main` chỉ nhờ lưu `.jsh`.

## 10. Từ JShell sang một chương trình Java hoàn chỉnh

Khi một ý tưởng đã được thử, hãy chuyển thành class có `main` để đóng gói và chạy lặp lại có chủ đích. Tạo **`Experiment.java`**:

~~~java
public final class Experiment {
    private Experiment() {}

    static int square(int n) {
        return Math.multiplyExact(n, n);
    }

    public static void main(String[] args) {
        int value = args.length == 0 ? 5 : Integer.parseInt(args[0]);
        System.out.println("Binh phuong: " + square(value));
    }
}
~~~

Chạy bằng **JDK 17+**:

**Bash:**

~~~bash
javac --release 17 -encoding UTF-8 Experiment.java
java Experiment
java Experiment 7
~~~

**PowerShell:**

~~~powershell
javac --release 17 -encoding UTF-8 .\Experiment.java
java Experiment
java Experiment 7
~~~

Đầu ra của hai lần chạy tương ứng:

~~~text
Binh phuong: 25
Binh phuong: 49
~~~

Bài này cố tình phân biệt: nhập `square(5)` trong JShell dùng **trạng thái snippet của phiên**; chạy `java Experiment` dùng **class đã biên dịch có `main`**. Hai cách bổ sung nhau, không thay thế nhau trong mọi tình huống.

Với đối số không phải số nguyên, `Integer.parseInt` có thể ném `NumberFormatException`. Với số đủ lớn, `Math.multiplyExact` phát hiện tràn `int` bằng `ArithmeticException`. Chạy được với số 5 không có nghĩa chạy được với mọi đầu vào.

## 11. Một phiên thực hành có cấu trúc

Thực hiện các bước sau trong một phiên JShell mới, ghi lại **giá trị thực**, không chỉ dòng bạn nhập:

1. Mở `jshell`; dùng `/help intro` nếu chưa quen.
2. Tính `9 / 4` và `9.0 / 4`; giải thích vì sao là `2` và `2.25`.
3. Tạo `int price = 75_000;` và `int count = 2;`. Thử `price * count`.
4. Đổi `count = 3;`; kiểm tra lại biểu thức. Nếu đã gán kết quả vào biến riêng, quan sát giá trị cũ có tự đổi hay không.
5. Khai báo `long total(long unitPrice, int quantity)` với `Math.multiplyExact` và từ chối số lượng âm; gọi method với ít nhất ba đầu vào.
6. Nhập `/vars`, `/methods`, `/list` và chỉ ra những snippet đã tạo.
7. Thử một lỗi kiểu, một lỗi tên và một exception runtime; ghi lại khác biệt.
8. Lưu phiên bằng `/save`, mở lại sau `/reset` và xác minh có thể tái tạo các phép thử.

### Bảng kết quả gợi ý

| Thử nghiệm | Giá trị/kết quả cần xác nhận |
|---|---|
| `9 / 4` | `2` |
| `9.0 / 4` | `2.25` |
| `75_000 * 2` | `150000` |
| `75_000 * 3` | `225000` |
| `Math.multiplyExact(75_000L, 3L)` | `225000` |
| `"hello".substring(1, 4)` | `"ell"` |
| `(String) null` rồi gọi `.length()` | `NullPointerException` khi method được gọi |

## 12. Bài tập kèm hướng dẫn đáp án

### Bài A — viết phương thức kiểm tra điểm

Tạo `boolean passed(int score)` trả `true` khi `score >= 50`; từ chối điểm dưới 0 hoặc trên 100 bằng `IllegalArgumentException`.

Một đáp án:

~~~java
boolean passed(int score) {
    if (score < 0 || score > 100) {
        throw new IllegalArgumentException("Score 0..100");
    }
    return score >= 50;
}
~~~

Thử `passed(49)`, `passed(50)`, `passed(100)`, `passed(101)`. Kỳ vọng: `false`, `true`, `true`, rồi exception. Ngưỡng đúng `50` kiểm tra được sự khác biệt giữa `>` và `>=`.

### Bài B — sửa kiểu trả về và tràn số

Trong `practice.jsh`, thay đoạn tính tiền bằng phương thức trả `long`, giới hạn đầu vào và dùng các phép toán an toàn hơn:

~~~java
long discounted(long amount, int percent) {
    if (amount < 0 || percent < 0 || percent > 100) {
        throw new IllegalArgumentException("Invalid input");
    }
    long kept = 100L - percent;
    long numerator = Math.multiplyExact(amount, kept);
    return numerator / 100L;
}
~~~

`discounted(100_000L, 10)` cho `90000`. Khi `amount` rất lớn, `multiplyExact` có thể ném exception thay vì âm thầm tạo số sai. Đây là **cách phát hiện tràn**, chưa phải giải pháp tính mọi số `long` lớn; muốn tính chính xác trên toàn miền có thể dùng `BigInteger` hoặc thay đổi thuật toán theo yêu cầu nghiệp vụ.

### Bài C — giải thích trạng thái phiên

Sau `/reset`, gọi `passed(50)` trước khi định nghĩa lại method. Vì sao không hoạt động?

**Đáp án:** snippet định nghĩa `passed` thuộc trạng thái phiên đã được xóa; JShell không lưu method đó như một class trên classpath để các phiên sau tự nạp. Hãy nhập lại, dùng `/open` với file snippet phù hợp hoặc viết mã nguồn `.java` có cấu trúc.

## 13. Checklist hoàn thành

- [ ] Mở được JShell từ JDK 17+ trên Bash hoặc PowerShell.
- [ ] Phân biệt lệnh terminal (`jshell`, `javac`, `java`) với lệnh bên trong JShell (`/vars`, `/list`, `/exit`).
- [ ] Đánh giá được các biểu thức số học, chuỗi, boolean và giải thích được kiểu kết quả.
- [ ] Khai báo, đọc và cập nhật biến; hiểu biến lưu giá trị, không phải công thức tự cập nhật.
- [ ] Khai báo và gọi phương thức có tham số/kiểu trả về.
- [ ] Phân biệt lỗi biên dịch snippet và exception khi đánh giá.
- [ ] Dùng `/vars`, `/methods`, `/list`, `/reset` để quan sát trạng thái.
- [ ] Lưu/mở `.jsh`, hiểu nó không tương đương class Java có `main`.
- [ ] Biên dịch và chạy `Experiment.java` với đầu ra dự kiến.
- [ ] Nhận ra hạn chế của JShell: phù hợp để thử nhanh, không thay thế tests/build của dự án.

**Kết luận:** JShell là phòng thực hành ngắn gọn để học cách Java đánh giá biểu thức, lưu biến và gọi phương thức. Hãy quan sát kết quả và lỗi thực tế, hiểu trạng thái của phiên, rồi chuyển những đoạn mã cần kiểm thử và tái sử dụng lâu dài sang tệp `.java` với `main` hoặc bộ test thích hợp.