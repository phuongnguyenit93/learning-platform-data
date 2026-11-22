# Xử lý lỗi biên dịch, ngoại lệ và trạng thái chưa giải quyết trong JShell

JShell cho phép thử nghiệm Java theo từng snippet ngay trong một phiên tương tác. Khi một snippet thất bại, cần xác định nó thất bại ở giai đoạn nào: trình biên dịch từ chối mã, mã đã biên dịch nhưng ném ngoại lệ khi chạy, hay một khai báo được chấp nhận tạm thời vì còn tham chiếu chưa được định nghĩa. Ba tình huống này có cách khắc phục khác nhau. JShell thường giữ phiên hoạt động sau một lỗi, nên bạn có thể sửa nguyên nhân và tiếp tục ngay.

## 1. Phân biệt ba loại vấn đề

| Loại | Thời điểm xảy ra | Dấu hiệu trong JShell | Cách xử lý chính |
|---|---|---|---|
| Lỗi biên dịch | Trước khi snippet được thực thi | `Error`, thông báo kiểu dữ liệu, cú pháp, tên hoặc quyền truy cập; snippet bị từ chối | Sửa mã, kiểu, import hoặc chữ ký rồi gửi lại snippet |
| Ngoại lệ lúc chạy | Sau khi mã đã biên dịch và bắt đầu thực thi | `Exception ...` cùng stack trace hoặc thông báo do `try/catch` in ra | Đọc loại ngoại lệ và stack trace; kiểm tra dữ liệu, điều kiện và tác dụng phụ |
| Tham chiếu chưa được giải quyết | Khi khai báo phụ thuộc vào biến, phương thức hoặc kiểu chưa có | JShell có thể báo đã tạo khai báo nhưng chưa thể gọi cho đến khi định nghĩa phụ thuộc xuất hiện | Bổ sung định nghĩa hoặc dependency đúng; kiểm tra lại trạng thái snippet |

Lỗi biên dịch thường có nghĩa snippet hiện tại chưa được chấp nhận. Ngoại lệ cho biết chương trình đã chạy đến một điểm cụ thể rồi thất bại. Tham chiếu chưa được giải quyết là trạng thái trung gian của một số khai báo: JShell có thể giữ khai báo đó và thử phân giải lại khi phiên nhận thêm định nghĩa phù hợp.

## 2. Đọc và sửa lỗi biên dịch

Trình biên dịch kiểm tra cú pháp, kiểu dữ liệu, tên thành viên, khả năng truy cập và quy tắc ngôn ngữ trước khi chạy snippet. Ví dụ sau gán một chuỗi cho biến `int`, nên JShell đưa ra chẩn đoán kiểu dữ liệu:

```text
jshell> int quantity = "12";
|  Error:
|  incompatible types: java.lang.String cannot be converted to int
```

Không có giá trị hợp lệ nào được gán cho `quantity` từ snippet bị từ chối. Hãy chuyển đổi dữ liệu một cách tường minh:

```java
int quantity = Integer.parseInt("12");
System.out.println(quantity);
```

Stdout:

```text
12
```

Khi đọc chẩn đoán, hãy bắt đầu từ thông báo đầu tiên và vị trí được đánh dấu. Các thông báo tiếp theo đôi khi chỉ là hệ quả của lỗi ban đầu. Kiểm tra lần lượt:

- Tên có đúng chính tả và đúng chữ hoa/chữ thường không.
- Kiểu của biểu thức có tương thích với kiểu đích hoặc kiểu tham số không.
- Đã import đúng package hay dùng tên đầy đủ chưa.
- Phương thức có đúng số lượng, thứ tự và kiểu đối số không.
- Thành viên có thể truy cập từ vị trí hiện tại không.
- Cú pháp của khai báo, dấu ngoặc, dấu chấm phẩy và generic có hợp lệ không.

Không nên sửa nhiều điểm cùng lúc khi chưa biết lỗi gốc. Hãy sửa một nguyên nhân, gửi lại snippet, rồi đọc chẩn đoán mới nếu còn lỗi.

### Lỗi tên chưa tồn tại

Ví dụ `new LocalDate()` không hợp lệ vì `LocalDate` không có constructor public không tham số. Đọc Javadoc để chọn factory hoặc constructor phù hợp; với ngày hiện tại, dùng `LocalDate.now()`. Nếu tên kiểu không được nhận diện, kiểm tra import hoặc dùng tên đầy đủ `java.time.LocalDate` để xác định có phải chỉ thiếu import hay không.

### Lỗi kiểu dữ liệu và overload

Khi một lời gọi có nhiều overload, kiểu thực tế của đối số quyết định phương thức nào được chọn. Không ép kiểu tùy tiện để làm mất lỗi. Hãy kiểm tra chữ ký trong Javadoc hoặc dùng Tab để xem các thành viên có thể gọi trên biểu thức hiện tại.

## 3. Xử lý ngoại lệ lúc chạy

Snippet có thể biên dịch thành công nhưng thất bại khi thực thi vì dữ liệu hoặc trạng thái lúc chạy. Ví dụ phương thức chia số nguyên dưới đây hợp lệ về cú pháp và kiểu, nhưng mẫu số bằng 0 gây `ArithmeticException`: 

```java
int divide(int numerator, int denominator) {
    return numerator / denominator;
}
```

Thử hai lời gọi:

```text
jshell> divide(10, 0)
|  Exception java.lang.ArithmeticException: / by zero

jshell> divide(10, 2)
$... ==> 5
```

Phần `$...` là tên biến kết quả tạm do JShell cấp; số thứ tự cụ thể thay đổi theo phiên. Sau ngoại lệ, phiên vẫn dùng được và lời gọi tiếp theo có thể thành công.

### Bắt ngoại lệ khi có thể xử lý tại chỗ

Nếu đầu vào không đáng tin cậy, dùng `try/catch` để xử lý trường hợp dự kiến thay vì để stack trace xuất hiện mỗi lần:

```java
try {
    int value = Integer.parseInt("not-a-number");
    System.out.println(value);
} catch (NumberFormatException ex) {
    System.out.println("Đầu vào không phải số nguyên hợp lệ");
}
```

Stdout:

```text
Đầu vào không phải số nguyên hợp lệ
```

Chỉ bắt loại ngoại lệ mà đoạn mã có thể xử lý có ý nghĩa. Nếu cần ghi nhận thông tin để chẩn đoán, có thể in loại ngoại lệ hoặc message; tránh nuốt lỗi bằng một `catch` rỗng. Không bắt `Throwable` để che mọi lỗi, vì `Error` thường biểu thị tình huống nghiêm trọng mà ứng dụng không nên cố tiếp tục như bình thường.

### Kiểm tra tác dụng phụ trước khi chạy lại

JShell không tự hoàn tác các thao tác đã thực hiện trước thời điểm ngoại lệ. Nếu snippet đã tăng bộ đếm, ghi tệp, cập nhật cơ sở dữ liệu hoặc gửi yêu cầu mạng rồi mới ném ngoại lệ, tác dụng phụ đó có thể vẫn còn. Ví dụ:

```java
int[] attempts = {0};
attempts[0]++;
throw new IllegalStateException("demo");
```

Sau khi JShell hiển thị ngoại lệ, kiểm tra:

```text
jshell> attempts[0]
$... ==> 1
```

Điều này cho thấy lệnh tăng bộ đếm đã hoàn tất trước khi ngoại lệ xảy ra. Trước khi chạy lại một snippet có tác dụng phụ, hãy xác định phần nào đã thực hiện và liệu việc lặp lại có an toàn hay không.

## 4. Hiểu tham chiếu chưa được giải quyết

JShell hỗ trợ khai báo một số phương thức ngay cả khi phần thân còn tham chiếu đến tên chưa được định nghĩa. Khai báo được giữ ở trạng thái có thể khôi phục, nhưng chưa thể gọi cho đến khi dependency được bổ sung. Ví dụ, mở một phiên JShell mới và nhập phương thức sau trước:

```java
long calculateTaxCents(long subtotalCents) {
    return Math.round(subtotalCents * taxRate);
}
```

JShell báo đã tạo phương thức nhưng chưa thể gọi cho đến khi biến `taxRate` được khai báo. Đây là tham chiếu chưa được giải quyết, không giống lỗi cú pháp hay lỗi kiểu khiến snippet bị từ chối.

Định nghĩa dependency với kiểu phù hợp:

```java
double taxRate = 0.08;
calculateTaxCents(2500);
```

Kết quả của lời gọi là `200`, vì 8% của 2.500 cent bằng 200 cent. Khi `taxRate` xuất hiện, JShell phân giải lại khai báo phương thức và phương thức có thể được gọi.

### Điều gì có thể còn thiếu?

Tham chiếu chưa được giải quyết thường xuất phát từ một trong các nguyên nhân:

- Biến hoặc phương thức được khai báo sau phương thức đang tham chiếu đến nó.
- Kiểu người dùng cần thiết chưa được định nghĩa trong phiên.
- Tên bị viết sai hoặc khác chữ hoa/chữ thường.
- Thư viện chứa kiểu cần dùng chưa có trên classpath hoặc module path.
- Import cần thiết chưa có hoặc tên kiểu đang bị nhầm với một kiểu khác.

Với biến hoặc phương thức cùng phiên, hãy khai báo dependency trước rồi kiểm tra lại. Với thư viện bên ngoài, khởi chạy JShell cùng classpath/module path đúng phiên bản; nếu môi trường khởi chạy không chứa thư viện, việc đổi tên trong snippet không thể giải quyết nguyên nhân.

### Trạng thái snippet trong Java Shell API

Ở mức API `jdk.jshell`, `Snippet.Status` biểu diễn trạng thái của từng snippet. Một phương thức có tham chiếu chưa giải quyết có thể ở trạng thái `RECOVERABLE_DEFINED`; khi dependency xuất hiện và khai báo được phân giải, trạng thái có thể chuyển thành `VALID`. Snippet bị trình biên dịch từ chối có trạng thái `REJECTED`. Các trạng thái này thuộc API lập trình JShell; chúng không phải lệnh cần gõ tại dấu nhắc `jshell>`.

Đừng nhầm trạng thái snippet với kết quả của một lần chạy. Một phương thức có thể ở trạng thái `VALID` nhưng một lời gọi cụ thể vẫn ném ngoại lệ vì dữ liệu lúc chạy không hợp lệ.

## 5. Xem lại phiên và tìm snippet cần sửa

Khi phiên đã có nhiều khai báo, hãy kiểm tra trạng thái thực tế trước khi tạo thêm tên trùng:

```text
jshell> /vars
jshell> /methods
jshell> /types
jshell> /imports
jshell> /list -all
jshell> /history
```

- `/vars` liệt kê biến đã khai báo.
- `/methods` liệt kê phương thức trong phiên.
- `/types` liệt kê các kiểu do người dùng khai báo.
- `/imports` cho biết các import đang có hiệu lực.
- `/list -all` liệt kê các snippet và ID để bạn tìm lại khai báo.
- `/history` hiển thị những lệnh đã nhập trong phiên.

Dùng `/help` hoặc `/help <command>` để xem cú pháp của một lệnh JShell. Nếu cần thay đổi một snippet, `/edit` mở trình soạn thảo của JShell; dùng `/help edit` để xem cách chọn snippet. Lệnh `/drop <id>` loại bỏ snippet theo ID hiển thị trong danh sách. Sau khi loại bỏ khai báo, những snippet phụ thuộc vào nó có thể trở lại trạng thái chưa giải quyết.

`/reset` khởi động lại phiên JShell và loại bỏ các khai báo trong phiên. Chỉ dùng khi bạn muốn bắt đầu lại; lệnh này không hoàn tác tác dụng phụ đã xảy ra bên ngoài JShell, chẳng hạn dữ liệu đã ghi vào tệp hoặc dịch vụ.

## 6. Quy trình chẩn đoán theo từng bước

1. **Đọc loại thông báo.** `Error` trước khi chạy thường là lỗi biên dịch; `Exception` kèm stack trace là lỗi lúc chạy; thông báo phương thức chưa thể gọi cho đến khi một biến hoặc kiểu được khai báo cho biết có dependency chưa được giải quyết.
2. **Xác định snippet liên quan.** Dùng `/list -all`, `/vars`, `/methods`, `/types` và `/imports` để tìm khai báo, ID và trạng thái phiên.
3. **Sửa đúng nguyên nhân.** Lỗi biên dịch cần sửa cú pháp hoặc kiểu; tham chiếu chưa giải quyết cần thêm dependency; ngoại lệ cần kiểm tra dữ liệu, điều kiện và vị trí ném lỗi.
4. **Thử lại bằng đầu vào nhỏ.** Dùng một giá trị biên và một giá trị bình thường để xác nhận cả nhánh lỗi lẫn nhánh thành công.
5. **Kiểm tra trạng thái sau sửa.** Gọi lại phương thức, xem biến hoặc liệt kê snippet để chắc chắn dependency đã được phân giải.
6. **Đánh giá tác dụng phụ.** Trước khi chạy lại thao tác ghi dữ liệu hoặc gọi dịch vụ, xác nhận lần chạy trước đã thực hiện đến đâu.

## 7. Ví dụ tổng hợp

Trong phiên mới, nhập phương thức tính phí trước biến cấu hình:

```java
long calculateTaxCents(long subtotalCents) {
    return Math.round(subtotalCents * taxRate);
}
```

Sau khi JShell báo tham chiếu `taxRate` chưa được giải quyết, khai báo biến:

```java
double taxRate = 0.08;
calculateTaxCents(2500);
```

Kết quả mong đợi của phép tính là `200`. Tiếp theo, thử truyền dữ liệu sai kiểu để thấy lỗi biên dịch:

```java
int subtotal = "2500";
```

Snippet cuối bị từ chối vì `String` không thể gán trực tiếp cho `int`; phương thức và biến đã khai báo trước đó vẫn còn trong phiên. Cuối cùng, thử lỗi lúc chạy:

```java
int divide(int a, int b) { return a / b; }
divide(10, 0);
divide(10, 2);
```

Lời gọi đầu ném `ArithmeticException`; lời gọi sau trả về `5`. Ba tình huống cho thấy cần phân loại lỗi trước khi chọn cách sửa.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Phương thức được tạo nhưng chưa thể gọi | Phần thân còn dùng biến, kiểu hoặc phương thức chưa được định nghĩa | Khai báo dependency với đúng tên và kiểu; sau đó gọi lại |
| `cannot find symbol` hoặc tên không được nhận diện | Thiếu khai báo, import, hoặc dependency | Kiểm tra `/vars`, `/methods`, `/types`, `/imports`; thêm import hoặc classpath/module path phù hợp |
| `incompatible types` | Giá trị trả về hoặc đối số không tương thích kiểu | Sửa kiểu hoặc chuyển đổi tường minh, có kiểm tra |
| `NoSuchMethodError` hoặc `NoClassDefFoundError` lúc chạy | Môi trường runtime nạp phiên bản thư viện khác hoặc thiếu lớp | Đồng bộ dependency và classpath/module path với môi trường chạy |
| `ArithmeticException` | Chia số nguyên cho 0 hoặc phép toán không hợp lệ | Kiểm tra mẫu số và điều kiện đầu vào trước phép toán |
| `NumberFormatException` | Chuỗi không biểu diễn số theo định dạng mong đợi | Kiểm tra dữ liệu hoặc bắt ngoại lệ cụ thể |
| Gọi lại snippet làm thay đổi dữ liệu lần nữa | Lần chạy trước đã thực hiện một phần tác dụng phụ | Kiểm tra trạng thái bên ngoài và thiết kế thao tác có thể lặp an toàn khi cần |

## 9. Nguyên tắc làm việc an toàn trong JShell

- Đọc chẩn đoán đầu tiên và sửa một nguyên nhân tại một thời điểm.
- Dùng tên biến, kiểu và phương thức có ý nghĩa để dễ nhận diện dependency.
- Tách phần tính toán thuần khỏi phần ghi tệp, gọi mạng hoặc cập nhật dữ liệu để dễ thử lại.
- Bắt ngoại lệ cụ thể và chỉ xử lý khi có hành động khôi phục hợp lý.
- Dùng `/list -all` và các lệnh kiểm tra phiên trước khi xóa hoặc định nghĩa lại snippet.
- Chỉ dùng `/reset` khi chấp nhận loại bỏ toàn bộ trạng thái trong phiên.
- Ghi lại phiên bản JDK và dependency khi chia sẻ cách tái hiện lỗi.

## Kết luận

Trong JShell, lỗi biên dịch nghĩa là snippet không được chấp nhận; ngoại lệ nghĩa là mã đã chạy và gặp điều kiện lỗi; tham chiếu chưa được giải quyết nghĩa là một số khai báo cần thêm dependency trước khi có thể sử dụng. Phân biệt đúng ba trường hợp, kiểm tra trạng thái phiên và xác nhận tác dụng phụ sẽ giúp sửa lỗi có kiểm soát mà không phải khởi động lại mọi thử nghiệm.