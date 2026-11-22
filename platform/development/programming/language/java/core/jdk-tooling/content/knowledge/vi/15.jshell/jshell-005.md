# Khai báo method trong JShell

**JShell** là môi trường tương tác (REPL) đi kèm JDK, cho phép nhập và thực thi biểu thức, câu lệnh, khai báo biến, lớp và phương thức Java ngay trong phiên làm việc. Khi khai báo method trong JShell, bạn có thể định nghĩa một thao tác có tên, truyền tham số, trả về kết quả rồi gọi lại nhiều lần mà không cần tạo một lớp ứng dụng hoàn chỉnh.

Method được nhập ở cấp cao nhất của JShell và được lưu như một snippet trong trạng thái phiên hiện tại. Sau khi khai báo thành công, method có thể được gọi từ các biểu thức, câu lệnh hoặc method khác trong cùng phiên.

## 1. Khởi động JShell

JShell được cung cấp từ JDK 9 trở lên. Mở Terminal hoặc PowerShell và kiểm tra:

```sh
jshell --version
```

Khởi động:

```sh
jshell
```

Khi vào phiên tương tác, JShell hiển thị dấu nhắc:

```text
jshell>
```

Nhập biểu thức Java để thử nhanh:

```java
jshell> 2 + 3
$1 ==> 5
```

Tên biến tạm như `$1` do JShell tự tạo cho kết quả biểu thức; số thứ tự thay đổi theo lịch sử phiên. Khi khai báo một method, JShell lưu khai báo đó để có thể gọi lại ở các prompt tiếp theo.

Thoát khỏi phiên:

```text
jshell> /exit
```

## 2. Cú pháp khai báo method

Cú pháp tổng quát của method Java:

```java
[modifiers] returnType methodName(parameterList) {
    // method body
}
```

Các thành phần:

- **Modifiers:** từ khóa bổ nghĩa nếu cần, ví dụ `public`, `private`, `static`.
- **Return type:** kiểu dữ liệu method trả về, ví dụ `int`, `String`, `boolean`, hoặc `void` nếu không trả về giá trị.
- **Method name:** tên method theo quy tắc định danh Java.
- **Parameter list:** danh sách tham số, mỗi tham số có kiểu và tên.
- **Method body:** các câu lệnh được thực thi khi gọi method.

Trong JShell, nhập khai báo method trực tiếp ở prompt, không cần đặt nó bên trong một lớp do người dùng tự khai báo.

Ví dụ:

```java
jshell> int add(int a, int b) {
   ...>     return a + b;
   ...> }
```

Dấu nhắc `...>` cho biết JShell đang chờ phần tiếp theo của khai báo nhiều dòng. Khi đóng ngoặc nhọn và khai báo hoàn chỉnh, JShell biên dịch snippet. Nếu không có lỗi, method đã sẵn sàng để sử dụng.

Gọi method:

```java
jshell> add(4, 6)
$1 ==> 10
```

Method `add` nhận hai tham số kiểu `int`, cộng chúng và trả về kết quả kiểu `int`.

## 3. Khai báo method trả về giá trị

Nếu method cần tạo ra một kết quả để nơi gọi sử dụng, hãy khai báo kiểu trả về phù hợp và dùng `return`.

Ví dụ method tính bình phương:

```java
jshell> int square(int number) {
   ...>     return number * number;
   ...> }
```

Gọi method:

```java
jshell> square(7)
$1 ==> 49
```

Có thể dùng kết quả trực tiếp trong biểu thức khác:

```java
jshell> square(3) + square(4)
$2 ==> 25
```

Với method có kiểu trả về khác `void`, mọi nhánh thực thi bình thường phải trả về giá trị tương thích với kiểu đã khai báo.

Ví dụ method kiểm tra số chẵn:

```java
jshell> boolean isEven(int number) {
   ...>     return number % 2 == 0;
   ...> }
```

```java
jshell> isEven(12)
$3 ==> true

jshell> isEven(9)
$4 ==> false
```

Không thể thay đổi kiểu trả về tùy ý khi gọi method. Giá trị trả về phải phù hợp với kiểu mà khai báo method quy định.

## 4. Khai báo method void

Dùng `void` khi method thực hiện một hành động nhưng không trả về giá trị.

Ví dụ:

```java
jshell> void greet(String name) {
   ...>     System.out.println("Xin chao, " + name + "!");
   ...> }
```

Gọi method:

```java
jshell> greet("Lan")
Xin chao, Lan!
```

Method `greet` nhận một tham số `String`, in lời chào và kết thúc. Vì kiểu trả về là `void`, không cần câu lệnh `return` có giá trị. Có thể dùng `return;` để kết thúc sớm một method void khi cần.

Ví dụ kiểm tra đầu vào:

```java
jshell> void printName(String name) {
   ...>     if (name == null || name.isBlank()) {
   ...>         System.out.println("Ten khong hop le");
   ...>         return;
   ...>     }
   ...>     System.out.println("Ten: " + name);
   ...> }
```

```java
jshell> printName("An")
Ten: An

jshell> printName(" ")
Ten khong hop le
```

Phân biệt method trả về giá trị và method void theo mục đích sử dụng:

| Loại method | Khai báo | Kết quả |
|---|---|---|
| Trả về dữ liệu | `int calculate(...)` | Nơi gọi nhận giá trị để tiếp tục xử lý |
| Thực hiện hành động | `void print(...)` | Thực hiện side effect, không trả giá trị |

## 5. Tham số và đối số

**Tham số (parameter)** là biến được khai báo trong danh sách tham số của method. **Đối số (argument)** là giá trị thực tế truyền vào khi gọi method.

Ví dụ:

```java
jshell> double calculateTotal(double price, int quantity) {
   ...>     return price * quantity;
   ...> }
```

Khi gọi:

```java
jshell> calculateTotal(19.5, 3)
$1 ==> 58.5
```

Trong khai báo, `price` và `quantity` là tham số. Trong lời gọi, `19.5` và `3` là đối số.

Java kiểm tra số lượng và kiểu đối số:

- Số lượng đối số phải phù hợp với danh sách tham số.
- Kiểu đối số phải tương thích với kiểu tham số theo quy tắc chuyển đổi của Java.
- Thứ tự đối số phải đúng với thứ tự tham số.
- Tham số chỉ có phạm vi bên trong method đó.

Ví dụ method có hai tham số:

```java
jshell> int subtract(int first, int second) {
   ...>     return first - second;
   ...> }
```

```java
jshell> subtract(10, 4)
$2 ==> 6
```

Gọi `subtract(10)` sẽ gây lỗi vì thiếu một đối số; gọi `subtract(10, 4, 2)` cũng sai vì truyền thừa đối số.

Java truyền đối số theo giá trị (pass-by-value). Với kiểu tham chiếu, giá trị được sao chép là giá trị tham chiếu; method có thể thay đổi trạng thái đối tượng được tham chiếu, nhưng gán lại biến tham số không làm biến của nơi gọi trỏ sang đối tượng khác.

## 6. Khai báo method nhiều dòng và nhiều câu lệnh

Method có thể gồm nhiều câu lệnh, biến cục bộ, điều kiện và vòng lặp. Dùng ngoặc nhọn để bao toàn bộ thân method.

Ví dụ tính tổng các số từ 1 đến n:

```java
jshell> int sumTo(int n) {
   ...>     if (n < 0) {
   ...>         throw new IllegalArgumentException("n must be non-negative");
   ...>     }
   ...>     int sum = 0;
   ...>     for (int i = 1; i <= n; i++) {
   ...>         sum += i;
   ...>     }
   ...>     return sum;
   ...> }
```

Gọi method:

```java
jshell> sumTo(5)
$1 ==> 15

jshell> sumTo(0)
$2 ==> 0
```

Method dùng biến cục bộ `sum` và `i`. Các biến này chỉ tồn tại trong phạm vi thực thi của method. Không thể truy cập trực tiếp chúng sau khi method kết thúc.

Khi nhập nhiều dòng, hãy bảo đảm mỗi dấu ngoặc mở có dấu ngoặc đóng tương ứng. Nếu JShell vẫn hiển thị `...>`, snippet có thể chưa hoàn chỉnh hoặc còn thiếu dấu đóng.

## 7. Method gọi method khác

Các method đã khai báo trong JShell có thể được gọi từ method khác. Đây là cách chia một tác vụ lớn thành những bước nhỏ có tên rõ ràng.

Ví dụ:

```java
jshell> int square(int n) {
   ...>     return n * n;
   ...> }
```

Khai báo method tính tổng bình phương:

```java
jshell> int sumOfSquares(int a, int b) {
   ...>     return square(a) + square(b);
   ...> }
```

Gọi:

```java
jshell> sumOfSquares(3, 4)
$1 ==> 25
```

Method `sumOfSquares` tái sử dụng `square`, nhờ đó tránh lặp lại biểu thức nhân và làm mục đích của từng bước rõ ràng hơn.

Nếu method được gọi chưa tồn tại hoặc không có chữ ký phù hợp, JShell sẽ báo lỗi biên dịch. Hãy khai báo dependency trước, hoặc kiểm tra tên và kiểu tham số của method được gọi.

## 8. Overloading: nhiều method cùng tên

Java cho phép khai báo nhiều method cùng tên nếu danh sách tham số khác nhau. Cơ chế này gọi là **method overloading**.

Ví dụ:

```java
jshell> String describe(int value) {
   ...>     return "So nguyen: " + value;
   ...> }
```

```java
jshell> String describe(String value) {
   ...>     return "Van ban: " + value;
   ...> }
```

Gọi theo kiểu đối số:

```java
jshell> describe(42)
$1 ==> "So nguyen: 42"

jshell> describe("Java")
$2 ==> "Van ban: Java"
```

Trình biên dịch chọn overload phù hợp dựa trên tên method, số lượng và kiểu đối số, cùng các quy tắc overload resolution của Java.

**Chỉ thay đổi kiểu trả về không tạo được overload.** Hai method có cùng tên và cùng danh sách kiểu tham số nhưng khác kiểu trả về là khai báo xung đột.

Ví dụ hợp lệ:

```java
int convert(int value) { return value; }
String convert(String value) { return value; }
```

Ví dụ không hợp lệ nếu khai báo cả hai:

```java
int calculate(int value) { return value; }
double calculate(int value) { return value; }
```

Hai method trên có cùng tên và cùng kiểu tham số; khác biệt kiểu trả về không đủ để phân biệt chữ ký.

Khi có nhiều overload, hãy chọn kiểu tham số rõ ràng. Một lời gọi như `process(null)` có thể mơ hồ nếu có nhiều overload nhận các kiểu tham chiếu không có quan hệ ưu tiên rõ ràng.

## 9. Varargs và tham số mảng

Method có thể nhận số lượng đối số thay đổi bằng cú pháp varargs `...`. Tham số varargs phải đứng cuối danh sách tham số.

Ví dụ:

```java
jshell> int sum(int... values) {
   ...>     int result = 0;
   ...>     for (int value : values) {
   ...>         result += value;
   ...>     }
   ...>     return result;
   ...> }
```

Gọi với nhiều đối số:

```java
jshell> sum(1, 2, 3, 4)
$1 ==> 10
```

Cũng có thể truyền trực tiếp một mảng `int[]`:

```java
jshell> sum(new int[] { 5, 6 })
$2 ==> 11
```

Bên trong method, tham số varargs được xử lý như một mảng. Varargs thuận tiện cho API có số đối số thay đổi, nhưng không nên lạm dụng nếu danh sách đầu vào thực chất là một collection hoặc một mảng đã có sẵn.

## 10. Method generic

Method có thể khai báo tham số kiểu để làm việc với nhiều kiểu dữ liệu mà vẫn giữ kiểm tra kiểu lúc biên dịch.

Ví dụ:

```java
jshell> <T> T identity(T value) {
   ...>     return value;
   ...> }
```

Gọi với các kiểu khác nhau:

```java
jshell> identity("Java")
$1 ==> "Java"

jshell> identity(100)
$2 ==> 100
```

`T` là tham số kiểu được khai báo trước kiểu trả về. Trình biên dịch suy luận kiểu từ đối số khi gọi method. Generic method hữu ích khi thuật toán không phụ thuộc vào một kiểu cụ thể, nhưng vẫn muốn giữ quan hệ kiểu giữa đầu vào và đầu ra.

Ví dụ dùng giới hạn kiểu:

```java
jshell> <T extends Number> double toDouble(T value) {
   ...>     return value.doubleValue();
   ...> }
```

Method này chỉ nhận kiểu `Number` hoặc kiểu con của nó. Nếu truyền một đối tượng không thuộc giới hạn đó, lời gọi sẽ không biên dịch.

## 11. Đệ quy trong method

Một method có thể gọi chính nó. Đây là **đệ quy (recursion)**. Mọi lời gọi đệ quy cần có điều kiện dừng để tránh gọi vô hạn.

Ví dụ tính giai thừa:

```java
jshell> long factorial(int n) {
   ...>     if (n < 0) {
   ...>         throw new IllegalArgumentException("n must be non-negative");
   ...>     }
   ...>     if (n <= 1) {
   ...>         return 1L;
   ...>     }
   ...>     return n * factorial(n - 1);
   ...> }
```

Gọi:

```java
jshell> factorial(5)
$1 ==> 120
```

Điều kiện `n <= 1` là trường hợp cơ sở. Với `n > 1`, method giảm dần đối số cho đến khi đạt trường hợp cơ sở.

Đệ quy có thể làm mã dễ hiểu với một số bài toán, nhưng mỗi lần gọi tạo một frame trên call stack. Đầu vào quá lớn có thể gây `StackOverflowError`; với vòng lặp, một số thuật toán có thể sử dụng bộ nhớ ít hơn.

## 12. Phạm vi, trạng thái và vòng đời method trong JShell

Khai báo method là một snippet được lưu trong trạng thái của phiên JShell. Method có thể được gọi lại sau khi prompt đã trở về `jshell>`.

Ví dụ:

```java
jshell> int triple(int value) {
   ...>     return value * 3;
   ...> }

jshell> triple(8)
$1 ==> 24
```

Method vẫn dùng được trong cùng phiên cho đến khi snippet bị loại bỏ hoặc trạng thái JShell được reset. Khi thoát và khởi động phiên mới, các khai báo trước đó không tự động được giữ lại trừ khi bạn lưu và nạp lại nội dung.

Các lệnh hữu ích:

| Lệnh JShell | Công dụng |
|---|---|
| `/methods` | Liệt kê method đang có trong phiên |
| `/list` | Liệt kê các snippet đã nhập |
| `/list -all` | Xem cả snippet không còn hoạt động và snippet hiện tại |
| `/vars` | Liệt kê các biến đã khai báo |
| `/types` | Liệt kê các kiểu đã khai báo |
| `/drop <id>` | Loại bỏ snippet theo ID |
| `/reset` | Reset trạng thái phiên JShell |
| `/help` | Xem trợ giúp các lệnh |
| `/exit` | Thoát JShell |

Ví dụ kiểm tra method:

```text
jshell> /methods
```

JShell hiển thị các khai báo method hiện hoạt cùng chữ ký của chúng. Dùng `/list` để xem nội dung snippet và ID tương ứng.

Nếu muốn loại bỏ một method, tìm ID snippet bằng `/list`, sau đó dùng:

```text
jshell> /drop <id>
```

Thay `<id>` bằng ID thực tế hiển thị trong phiên. Nếu method khác phụ thuộc vào snippet bị loại bỏ, những snippet liên quan có thể không còn hợp lệ; hãy kiểm tra thông báo JShell và khai báo lại dependency cần thiết.

`/reset` xóa trạng thái phiên, bao gồm method, biến, lớp và import đã khai báo. Chỉ dùng khi thực sự muốn bắt đầu lại.

## 13. Cập nhật một method đã khai báo

Trong quá trình thử nghiệm, có thể khai báo lại method với cùng tên và cùng danh sách kiểu tham số để thay đổi phần thân.

Ví dụ khai báo ban đầu:

```java
jshell> int applyDiscount(int price) {
   ...>     return price - 10;
   ...> }
```

```java
jshell> applyDiscount(100)
$1 ==> 90
```

Khai báo lại cùng chữ ký với quy tắc mới:

```java
jshell> int applyDiscount(int price) {
   ...>     return price - 20;
   ...> }
```

Gọi lại:

```java
jshell> applyDiscount(100)
$2 ==> 80
```

JShell hỗ trợ thay thế khai báo method trong phiên tương tác. Dùng `/methods` để xem các method đang hoạt động và `/list` để theo dõi lịch sử snippet. Khi method có nhiều overload, cần chú ý đúng danh sách tham số đang được cập nhật.

## 14. Lỗi thường gặp khi khai báo method

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `';' expected` hoặc lỗi cú pháp | Thiếu dấu chấm phẩy trong thân method, thiếu ngoặc hoặc sai cú pháp | Kiểm tra từng câu lệnh và cặp ngoặc |
| JShell tiếp tục hiển thị `...>` | Khai báo nhiều dòng chưa hoàn chỉnh, thường thiếu dấu `}` | Hoàn thành thân method và đóng đủ ngoặc |
| `missing return statement` | Method có kiểu trả về nhưng một nhánh có thể kết thúc mà không trả giá trị | Bổ sung `return` cho mọi nhánh thực thi bình thường |
| `incompatible types` | Giá trị trả về không tương thích kiểu đã khai báo | Đổi kiểu trả về hoặc chuyển đổi dữ liệu đúng cách |
| `cannot find symbol` | Gọi method chưa khai báo, sai tên hoặc sai chữ ký | Kiểm tra tên, tham số và khai báo dependency trước |
| `method ... cannot be applied to given types` | Số lượng hoặc kiểu đối số không phù hợp | Truyền đúng số lượng và kiểu đối số |
| `reference to ... is ambiguous` | Nhiều overload cùng phù hợp với lời gọi | Làm rõ kiểu đối số hoặc thiết kế lại overload |
| `method is already defined` hoặc khai báo xung đột | Hai khai báo có cùng chữ ký không được phân biệt hợp lệ trong trạng thái hiện tại | Xem `/methods`, `/list` và cập nhật đúng snippet |
| `non-static ... cannot be referenced from a static context` | Ngữ cảnh method yêu cầu thành viên static nhưng đang tham chiếu thành viên instance | Xem lại modifier và cách tổ chức trạng thái/đối tượng |
| `StackOverflowError` | Đệ quy không có điều kiện dừng hoặc độ sâu quá lớn | Sửa trường hợp cơ sở hoặc chuyển sang vòng lặp |

Khi có lỗi, đọc thông báo ngay tại prompt. JShell biên dịch khai báo method trước khi kích hoạt snippet; lỗi biên dịch cần được sửa trong khai báo rồi nhập lại. Không nên tiếp tục gọi một method chưa được khai báo thành công.

## 15. Thực hành tổng hợp

Trong một phiên JShell mới, nhập lần lượt các method sau.

Method tính tiền sau giảm giá:

```java
double finalPrice(double price, double discountRate) {
    if (price < 0 || discountRate < 0 || discountRate > 1) {
        throw new IllegalArgumentException("Invalid price or discount");
    }
    return price * (1 - discountRate);
}
```

Method định dạng kết quả:

```java
String formatPrice(double price) {
    return String.format("%.2f", price);
}
```

Method kết hợp hai bước:

```java
String checkout(double price, double discountRate) {
    double result = finalPrice(price, discountRate);
    return "Total: " + formatPrice(result);
}
```

Gọi method:

```java
checkout(200.0, 0.10)
```

Kết quả:

```text
$1 ==> "Total: 180.00"
```

Các method được khai báo riêng nhưng có thể gọi lẫn nhau. `checkout` điều phối luồng xử lý, `finalPrice` tính toán và `formatPrice` định dạng. Cách chia này làm mỗi method có một trách nhiệm cụ thể, dễ kiểm tra và thay đổi.

Có thể thử thêm các tình huống:

- `checkout(0.0, 0.0)` để kiểm tra giá trị biên.
- `checkout(200.0, 1.0)` để kiểm tra giảm giá 100%.
- `checkout(-1.0, 0.1)` để kiểm tra ngoại lệ.
- `checkout(200.0, 1.5)` để kiểm tra tỷ lệ giảm giá không hợp lệ.

Với hai trường hợp cuối, method ném `IllegalArgumentException`; JShell hiển thị stack trace thay vì một giá trị trả về thông thường.

## 16. Lưu và sử dụng lại khai báo

Phiên JShell mặc định là môi trường tương tác tạm thời. Để giữ các snippet và nạp lại trong phiên sau, có thể dùng lệnh lưu và mở tệp:

```text
jshell> /save methods.jsh
```

Trong phiên mới:

```text
jshell> /open methods.jsh
```

Tệp được lưu có thể chứa các snippet khác ngoài method, tùy trạng thái phiên và tùy chọn lưu. Hãy xem nội dung tệp trước khi chia sẻ hoặc sử dụng lại trong môi trường khác.

Nếu cần dùng thư viện ngoài khi khởi động JShell, có thể truyền classpath:

```sh
jshell --class-path "lib/*"
```

Sau đó khai báo import và method sử dụng kiểu từ thư viện đó. Dependency phải tồn tại đúng vị trí và tương thích với JDK đang chạy JShell.

## 17. Nguyên tắc viết method rõ ràng

- Đặt tên method bằng động từ hoặc cụm động từ thể hiện hành động, ví dụ `calculateTotal`, `findUser`, `printReport`.
- Mỗi method nên có một trách nhiệm chính.
- Chọn kiểu trả về phản ánh đúng kết quả; dùng `void` khi chỉ thực hiện hành động.
- Đặt tên tham số có ý nghĩa và dùng kiểu dữ liệu phù hợp.
- Kiểm tra đầu vào ở nơi cần thiết, đặc biệt với giá trị null, số âm và giới hạn miền dữ liệu.
- Tránh method quá dài hoặc có quá nhiều nhánh lồng nhau.
- Dùng overloading khi các thao tác có cùng ý nghĩa nhưng nhận các kiểu đầu vào khác nhau.
- Tránh overloading gây mơ hồ, đặc biệt với kiểu tham chiếu và giá trị `null`.
- Với đệ quy, luôn xác định trường hợp cơ sở và giới hạn độ sâu hợp lý.
- Dùng JShell để thử nhanh hành vi, sau đó chuyển các method đã ổn định vào lớp và dự án có cấu trúc khi phát triển ứng dụng thực tế.

## 18. Checklist

- [ ] Đã khởi động JShell từ JDK 9 trở lên.
- [ ] Khai báo method ở cấp cao nhất của prompt.
- [ ] Đã xác định kiểu trả về hoặc dùng `void` phù hợp.
- [ ] Danh sách tham số có kiểu và tên rõ ràng.
- [ ] Thân method có đủ dấu ngoặc và câu lệnh hợp lệ.
- [ ] Method trả về giá trị ở mọi nhánh cần thiết.
- [ ] Đã gọi thử với nhiều đối số hợp lệ và giá trị biên.
- [ ] Đã kiểm tra overload và tránh chữ ký trùng.
- [ ] Đã dùng `/methods` và `/list` để kiểm tra snippet.
- [ ] Đã lưu khai báo nếu cần sử dụng lại trong phiên sau.

Khai báo method trong JShell giúp thử nghiệm thuật toán và API nhanh chóng, đồng thời rèn luyện cách chia chương trình thành những thao tác có tên, tham số và kiểu trả về rõ ràng. Khi hiểu cách khai báo, gọi, overload và quản lý snippet, bạn có thể kiểm tra logic từng bước trước khi đưa method vào một dự án Java hoàn chỉnh.