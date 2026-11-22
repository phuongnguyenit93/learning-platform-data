# Scanner và mô hình tách token từ nguồn văn bản

## 1. Scanner làm gì với dữ liệu đầu vào?

`Scanner` đọc văn bản, chia thành các phần gọi là **token**, rồi có thể chuyển một token thành int, double, boolean hoặc kiểu được hỗ trợ khác.

Mô hình cơ bản:

```text
Nguồn văn bản
      |
Đọc các ký tự cần thiết
      |
Dùng mẫu phân cách — delimiter
      |
Nhận diện token kế tiếp
      |
Trả chuỗi hoặc chuyển token sang kiểu cần đọc
```

Ví dụ nguồn:

```text
Lan   21
true  3.5
```

Với cách phân cách mặc định, các token theo thứ tự là:

```text
"Lan", "21", "true", "3.5"
```

Scanner không tự biết Lan là tên, 21 là tuổi hay 3.5 là điểm. Chương trình quyết định lần lượt đọc bằng `next()`, `nextInt()`, `nextBoolean()` hay `nextDouble()`.

Scanner xuất hiện từ Java 5 và vẫn phù hợp trên Java hiện đại, đặc biệt cho dữ liệu văn bản đơn giản và chương trình tương tác nhỏ. Các ví dụ trong bài chạy với Java 17+.

## 2. Nguồn, delimiter, token và vị trí đọc

### Nguồn văn bản

Nguồn có thể là:

- Một String đã có trong bộ nhớ.
- Dữ liệu ký tự từ một Readable.
- InputStream hoặc kênh byte, kèm bước giải mã theo charset.
- Tệp/Path, được mở và đọc theo constructor tương ứng.

`new Scanner("12 34")` quét chính nội dung chuỗi. Nó không coi chuỗi ấy là tên tệp.

Muốn đọc tệp thì dùng constructor cho tệp hoặc Path. Nếu đầu vào là byte, phải phân biệt **charset** với delimiter: charset biến byte thành ký tự, còn delimiter chia ký tự thành token.

### Delimiter — mẫu phân cách

Mặc định Scanner dùng mẫu nhận diện khoảng trắng theo quy tắc của `Character.isWhitespace()`. Dấu cách, tab và dấu xuống dòng thường gặp đều có thể đóng vai trò phân cách.

Delimiter là **biểu thức chính quy (regular expression)**, không phải chỉ một ký tự “phím Enter”.

Vì vậy `next()` không có nghĩa “đọc tới hết dòng”. Nó đọc token kế tiếp theo mẫu phân cách hiện hành.

### Token

Token là phần văn bản giữa các vùng phân cách theo quy tắc quét. Với delimiter mặc định, nhiều khoảng trắng liên tiếp thường chỉ ngăn hai token, không tạo ra một token cho từng dấu cách.

Khi đổi mẫu phân cách, cách xử lý token rỗng có thể thay đổi. Không mặc định mọi delimiter đều hoạt động giống mẫu khoảng trắng mặc định.

### Vị trí đọc

Scanner giữ trạng thái đọc của chính nó. Mỗi lần lấy token thành công tiến vị trí quét theo hợp đồng, nên lời gọi sau xử lý phần còn lại.

Dữ liệu đã tiêu thụ không tự quay lại. `reset()` đặt lại những cấu hình quét được hợp đồng quy định, không phải lệnh tua nguồn về đầu.

Hợp đồng tổng thể được mô tả trong [Scanner](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html).

## 3. next và hasNext khác nhau ở việc tiêu thụ token

| Phương thức | Câu hỏi/hành động |
| --- | --- |
| hasNext() | Có thể có token tiếp theo không? |
| next() | Lấy token tiếp theo dưới dạng String |
| hasNextInt() | Token tiếp theo có thể đọc thành int theo cấu hình hiện tại không? |
| nextInt() | Lấy token tiếp theo và chuyển thành int |

`hasNext()` không trả token và không tiến qua token như `next()`. Có thể kiểm tra nhiều lần rồi vẫn lấy đúng token ấy:

```java
Scanner scanner = new Scanner("A B");
boolean firstCheck = scanner.hasNext();
boolean secondCheck = scanner.hasNext();
String firstToken = scanner.next();
```

Cần import `java.util.Scanner`, đặt đoạn vào phương thức và quản lý đóng Scanner phù hợp. Hai kiểm tra đều cho true, còn firstToken là A.

“Không tiêu thụ token” không có nghĩa Scanner không đọc thêm dữ liệu từ nguồn. Nó có thể đọc đệm để xác định câu trả lời. Điều này rất quan trọng khi nhiều thành phần cùng cố đọc một InputStream: dữ liệu đã được một Scanner đọc trước vào bộ đệm không còn đơn giản nằm nguyên ở nguồn để Scanner khác lấy theo suy đoán.

Nên có một bên chịu trách nhiệm điều phối việc đọc từ một nguồn tuần tự, thay vì tạo nhiều Scanner độc lập trên cùng nguồn rồi xen kẽ tùy ý.

## 4. Đọc kiểu dữ liệu là kiểm tra token theo hợp đồng

Khi gọi `nextInt()`, Scanner không chỉ lấy các ký tự có vẻ là chữ số. Nó kiểm tra token theo cú pháp số, cơ số và miền int tương ứng.

Ví dụ:

- `"12"` có thể đọc thành int trong cơ số 10.
- `"twelve"` không phù hợp.
- Một chuỗi chữ số biểu diễn giá trị quá lớn cho int cũng không phù hợp, dù không chứa chữ cái.

`hasNextInt()` trả false có thể có hai lý do khác nhau: không còn token hoặc token hiện tại không thể đọc thành int. Nếu cần phân biệt, kiểm tra `hasNext()` và xử lý token còn lại.

Không dùng vòng:

```java
while (scanner.hasNextInt()) {
    int value = scanner.nextInt();
}
```

rồi mặc định toàn bộ nguồn đã được đọc hết. Gặp token x ở giữa nguồn sẽ làm vòng dừng trước x, dù phía sau vẫn còn dữ liệu.

### Locale và radix là một phần của trạng thái quét

Cơ số mặc định cho số nguyên là 10; có thể cấu hình bằng `useRadix` hoặc dùng overload tương ứng.

Locale ảnh hưởng cách Scanner hiểu các số có dấu phân cách thập phân/phân nhóm. Nếu dữ liệu có quy ước cố định, cấu hình locale tường minh để kết quả không phụ thuộc môi trường chạy.

```java
scanner.useLocale(Locale.ROOT);
```

Cần import `java.util.Locale`. Cấu hình delimiter và locale giải quyết hai vấn đề riêng: delimiter tìm ranh giới token, locale diễn giải nội dung token số.

Ví dụ dùng dấu phẩy làm delimiter có thể xung đột với dữ liệu dùng dấu phẩy làm dấu thập phân. Không thể giải quyết chỉ bằng đổi locale nếu token đã bị cắt sai từ bước trước.

## 5. Ví dụ mô hình token với kiểu dữ liệu và dòng

Lưu thành `ScannerTokenModelDemo.java`:

```java
import java.util.Locale;
import java.util.Scanner;

public class ScannerTokenModelDemo {
    public static void main(String[] args) {
        String input = " \tLan   21\ntrue\t3.5 ";

        try (Scanner scanner = new Scanner(input)) {
            scanner.useLocale(Locale.ROOT);

            System.out.println("First check: " + scanner.hasNext());
            System.out.println("Second check: " + scanner.hasNext());

            String name = scanner.next();
            int age = scanner.nextInt();
            boolean enabled = scanner.nextBoolean();
            double score = scanner.nextDouble();

            System.out.println("Name: " + name);
            System.out.println("Age: " + age);
            System.out.println("Enabled: " + enabled);
            System.out.println("Score: " + score);
            System.out.println("More tokens: " + scanner.hasNext());
        }

        try (Scanner scanner = new Scanner("42\nhello world\n")) {
            int number = scanner.nextInt();
            String restOfCurrentLine = scanner.nextLine();
            String nextLine = scanner.nextLine();

            System.out.println("Number: " + number);
            System.out.println("Remainder: [" + restOfCurrentLine + "]");
            System.out.println("Next line: [" + nextLine + "]");
        }
    }
}
```

Chạy:

```shell
javac ScannerTokenModelDemo.java
java ScannerTokenModelDemo
```

Stdout:

```text
First check: true
Second check: true
Name: Lan
Age: 21
Enabled: true
Score: 3.5
More tokens: false
Number: 42
Remainder: []
Next line: [hello world]
```

Ở phần đầu, tab và xuống dòng đều góp phần phân cách token. Việc gọi hasNext hai lần không lấy mất Lan.

Ở phần sau, `nextInt()` lấy token 42. `nextLine()` kế tiếp đọc phần còn lại của dòng hiện tại, vốn rỗng trước dấu kết thúc dòng, và đi qua dấu kết thúc dòng đó. Lần nextLine sau mới trả hello world.

## 6. nextLine không thuộc cùng mô hình delimiter với next

`nextLine()` đọc phần còn lại của dòng hiện tại và bỏ qua dấu kết thúc dòng, không trả dấu kết thúc dòng trong String kết quả. Nó không dùng delimiter để chỉ lấy một token.

Ví dụ chuỗi:

```text
42 hello world
```

Nếu nextInt đã lấy 42, nextLine sau đó có thể trả phần còn lại bao gồm dấu cách trước hello. Nó không tự trim theo yêu cầu nghiệp vụ.

Trong ví dụ dòng 42 riêng, phần còn lại là chuỗi rỗng. Đây là hệ quả của vị trí đọc và loại phương thức, không phải Scanner tự “bỏ qua một lần nhập”.

Khi thiết kế nhập liệu, nên chọn một giao thức rõ:

- Dữ liệu là chuỗi token theo một cấu trúc đã biết: dùng các phương thức token nhất quán.
- Dữ liệu được tổ chức theo từng dòng: đọc dòng rồi phân tích dòng theo quy tắc thích hợp.
- Nếu cần trộn, xác định rõ phần còn lại của dòng hiện tại có ý nghĩa gì trước khi gọi nextLine.

Không thêm một lệnh nextLine “cho hết lỗi” ở mọi nơi. Nó có thể bỏ mất dữ liệu hợp lệ nếu phần còn lại dòng không rỗng.

## 7. Đổi delimiter là đổi ranh giới token

Ví dụ muốn đọc danh sách đơn giản:

```text
red, green, blue
```

Có thể dùng mẫu dấu phẩy rồi khoảng trắng tùy chọn:

```java
scanner.useDelimiter(",\\s*");
```

Chuỗi Java cần hai dấu gạch chéo để tạo `\s` cho regex. Ở đây regex không phải ngôn ngữ khuôn của printf; phải phân biệt từng lớp cú pháp.

Với nguồn trên, token lần lượt là red, green, blue.

Điều quan trọng là useDelimiter **thay thế** mẫu hiện hành; nó không mặc định “thêm dấu phẩy vào mọi khoảng trắng”. Nếu muốn khoảng trắng ở vị trí khác cũng được xử lý, cần một mẫu phù hợp với cấu trúc dữ liệu đó.

Không dùng một delimiter dấu phẩy đơn giản để tự nhận là đã hỗ trợ CSV đầy đủ. Dấu phẩy trong trường có ngoặc kép, escape và trường nhiều dòng cần một giao thức phân tích khác.

Mẫu có thể khớp chuỗi rỗng hoặc nhiều lần phân cách liền nhau cũng cần phân tích riêng. Bài này dùng dữ liệu và mẫu đơn giản, không suy rộng rằng mọi cách tách đều loại bỏ token rỗng.

## 8. Token sai vẫn còn sau InputMismatchException

Nếu nextInt không thể chuyển token hiện tại thành int, Scanner ném `InputMismatchException`. Token gây lỗi chưa bị tự loại khỏi luồng token theo hợp đồng, nên chương trình có thể lấy nó bằng next hoặc bỏ qua có chủ đích.

Mẫu xử lý đơn giản:

```java
while (scanner.hasNext()) {
    if (scanner.hasNextInt()) {
        int value = scanner.nextInt();
        process(value);
    } else {
        String invalid = scanner.next();
        report(invalid);
    }
}
```

Đây là đoạn minh họa; process và report là hàm nghiệp vụ cần được triển khai ở nơi sử dụng. Điểm quyết định là nhánh token sai vẫn **tiêu thụ** nó hoặc chọn kết thúc có chủ đích.

Nếu chỉ báo lỗi rồi lặp lại hasNextInt/nextInt trên cùng token, chương trình có thể lặp mãi mà không tiến triển.

[InputMismatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/InputMismatchException.html) bao gồm cả token sai mẫu và giá trị nằm ngoài miền của kiểu mong đợi.

## 9. Ví dụ delimiter riêng và cách tiến qua token sai

Lưu thành `ScannerConsumptionDemo.java`:

```java
import java.util.InputMismatchException;
import java.util.Scanner;

public class ScannerConsumptionDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("red, green, blue")) {
            scanner.useDelimiter(",\\s*");
            while (scanner.hasNext()) {
                System.out.println("Color: [" + scanner.next() + "]");
            }
        }

        try (Scanner scanner =
                     new Scanner("10 x 20 999999999999999")) {
            int sum = 0;

            while (scanner.hasNext()) {
                if (scanner.hasNextInt()) {
                    sum += scanner.nextInt();
                } else {
                    System.out.println("Rejected: " + scanner.next());
                }
            }
            System.out.println("Sum: " + sum);
        }

        try (Scanner scanner = new Scanner("oops 7")) {
            try {
                scanner.nextInt();
            } catch (InputMismatchException e) {
                System.out.println("Mismatch: "
                        + e.getClass().getSimpleName());
                System.out.println("Still current: " + scanner.next());
            }

            System.out.println("Next integer: " + scanner.nextInt());
        }
    }
}
```

Chạy:

```shell
javac ScannerConsumptionDemo.java
java ScannerConsumptionDemo
```

Stdout:

```text
Color: [red]
Color: [green]
Color: [blue]
Rejected: x
Rejected: 999999999999999
Sum: 30
Mismatch: InputMismatchException
Still current: oops
Next integer: 7
```

Token số rất lớn bị từ chối cho int, không phải vì chứa ký tự không phải chữ số. Sau lỗi với oops, lệnh next vẫn lấy được chính oops; chỉ sau đó nextInt mới đọc 7.

Tổng 30 an toàn trong dữ liệu cố định của ví dụ. Nếu cộng dữ liệu bất kỳ, chương trình còn phải thiết kế xử lý tràn số; Scanner không tự bảo vệ phép cộng diễn ra sau khi parse.

## 10. Nguồn có thể chưa kết thúc: hasNext cũng có thể chờ

Với một String hữu hạn, Scanner đã có nguồn văn bản có điểm kết thúc rõ. Với console, socket hoặc nguồn đang mở, nó có thể cần đọc thêm để xác định một token hay xác định đã hết dữ liệu.

Cả `hasNext()` và `next()` đều có thể chặn chờ dữ liệu. Tên “has” không biến phương thức thành phép kiểm tra không chặn.

Không dùng hasNext như cách thử ngay xem bàn phím có dữ liệu chưa. Cũng không suy ra rằng một lời gọi hasNext trước đó cho kết quả thì mọi lời gọi đọc về sau chắc chắn không chờ trong mọi tình huống.

Phím Enter thường đưa ký tự kết thúc dòng vào nguồn, không tự đồng nghĩa EOF của toàn nguồn. Vòng while(hasNext()) có thể tiếp tục chờ token sau dòng đầu vì nguồn vẫn mở.

Khi không còn token và nguồn đã kết thúc:

- hasNext trả false.
- next gọi trực tiếp không còn phần tử thì ném NoSuchElementException.
- Phương thức chuyển kiểu có thể ném InputMismatchException nếu còn token nhưng không phù hợp.
- Scanner đã đóng không còn dùng được để quét và có hợp đồng lỗi trạng thái riêng.

## 11. Quản lý nguồn và lỗi I/O

Với String hoặc nguồn do đoạn mã tự sở hữu, try-with-resources giúp đóng Scanner rõ ràng.

Với tệp, nên nêu charset:

```java
try (Scanner scanner =
             new Scanner(Path.of("numbers.txt"), StandardCharsets.UTF_8)) {
    while (scanner.hasNext()) {
        String token = scanner.next();
        System.out.println(token);
    }

    if (scanner.ioException() != null) {
        throw scanner.ioException();
    }
}
```

Đây là đoạn minh họa đọc tệp cần có thật, không phải chương trình độc lập. Cần import Scanner, Path và StandardCharsets, đồng thời xử lý hoặc khai báo IOException ở phương thức bao ngoài.

Scanner có thể xem IOException từ nguồn Readable như dấu hiệu đã kết thúc việc đọc, đồng thời giữ lỗi gần nhất để lấy qua ioException. Với công việc cần phân biệt EOF bình thường và đọc lỗi, phải kiểm tra kênh này theo hợp đồng.

Đóng Scanner sẽ đóng nguồn nếu nguồn triển khai Closeable. Nếu tạo Scanner trên System.in rồi đóng nó, nguồn nhập dùng chung cũng có thể bị đóng. Quyết định đóng thuộc về bên sở hữu vòng đời nguồn; không áp try-with-resources máy móc cho một thành phần chỉ mượn System.in của cả ứng dụng.

Scanner không tự an toàn khi nhiều luồng cùng dùng nếu thiếu cơ chế đồng bộ bên ngoài. Việc nó có bộ đệm và nhiều phương thức tiện dụng không tạo quyền đọc đồng thời tùy ý.

## 12. Scanner phù hợp với mô hình nào?

| Nhu cầu | Cân nhắc |
| --- | --- |
| Đọc token số/văn bản đơn giản từ đầu vào nhỏ | Scanner diễn đạt trực tiếp |
| Nhập tương tác theo từng dòng | Có thể dùng Scanner.nextLine, rồi phân tích rõ cấu trúc dòng |
| Đọc tệp rất lớn với yêu cầu thông lượng cao | Đo đạc; có thể cần Reader/bộ đệm và parser phù hợp hơn |
| CSV/JSON có ngữ pháp đầy đủ | Dùng parser hiểu định dạng |
| Nguồn không kết thúc, cần điều khiển chờ/hủy chặt | Xét hợp đồng I/O và cơ chế điều phối phù hợp |

Không có yêu cầu phải thay Scanner chỉ vì nó có từ Java 5. Cần chọn theo cấu trúc dữ liệu, độ lớn, hiệu năng và yêu cầu vòng đời nguồn.

## 13. Tự kiểm tra

**new Scanner("data.txt") có mở tệp data.txt không?**  
Không. Nó quét nội dung chuỗi data.txt.

**hasNext có lấy mất token kế tiếp không?**  
Không tiêu thụ token theo cách next làm, nhưng có thể đọc đệm từ nguồn và có thể chặn chờ.

**hasNextInt trả false có nghĩa EOF không?**  
Chưa chắc. Có thể token hiện tại không phải int hoặc vượt miền int.

**Tại sao nextLine sau nextInt đôi khi trả chuỗi rỗng?**  
Vì nó đọc phần còn lại của dòng hiện tại sau token số; nếu số nằm ngay trước dấu kết thúc dòng thì phần còn lại rỗng.

**Sau InputMismatchException, lặp lại nextInt ngay có tự sang token khác không?**  
Không. Cần xử lý token gây lỗi hoặc kết thúc theo chính sách.

Mô hình cần giữ là nguồn ký tự, mẫu phân cách, token, vị trí đọc và bước chuyển kiểu. Khi phân biệt rõ từng phần, hành vi Scanner có thể được dự đoán từ giao thức đầu vào thay vì sửa bằng những lệnh đọc thêm không rõ mục đích.
