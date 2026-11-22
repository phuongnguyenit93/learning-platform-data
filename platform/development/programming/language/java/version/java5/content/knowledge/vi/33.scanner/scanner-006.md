# Phân biệt nextLine() với đọc token trong Scanner

## 1. Hai cách đặt ranh giới dữ liệu

Khi đọc văn bản, cần quyết định **một giá trị kết thúc ở đâu**. Với danh sách số, dấu cách hoặc xuống dòng thường đều là dấu ngăn cách. Với họ tên hoặc địa chỉ, khoảng trắng lại là một phần của giá trị.

Scanner có hai nhóm thao tác để biểu đạt hai nhu cầu đó:

- **Đọc token:** `next()`, `nextInt()` và các phương thức tương tự đọc một phần dữ liệu được phân cách theo mẫu delimiter.
- **Đọc dòng:** `nextLine()` lấy phần còn lại của dòng hiện tại, bỏ dấu kết thúc dòng và chuyển vị trí đọc sang đầu dòng sau.

Điểm quyết định là **vị trí đọc hiện tại**. `nextLine()` không có nghĩa “bỏ dòng hiện tại rồi lấy dòng tiếp theo”, và `nextInt()` không có nghĩa “đọc cả dòng chứa một số”. Hợp đồng chi tiết có trong [Scanner API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Scanner.html).

## 2. Bảng đối chiếu

| Đặc điểm | Đọc token | Đọc dòng |
| --- | --- | --- |
| Phương thức thường dùng | `next()`, `nextInt()`, `nextDouble()` | `nextLine()` |
| Ranh giới | Mẫu delimiter đang cấu hình | Dấu kết thúc dòng |
| Với cấu hình mặc định | Bỏ qua khoảng trắng trước token | Giữ khoảng trắng trong phần dòng được trả về |
| Chuỗi `Alice Nguyen` trên một dòng | Hai lần `next()` nhận hai token | Một lần `nextLine()` nhận cả tên |
| Dòng rỗng | Với delimiter mặc định, không tạo giá trị token | Có thể trả về `""` |
| Giá trị trả về | String hoặc kiểu số tương ứng | String |
| Kiểm tra có dữ liệu | `hasNext()`, `hasNextInt()`... | `hasNextLine()` |

Delimiter mặc định nhận các ký tự trắng theo quy tắc Java, gồm các trường hợp thông dụng như dấu cách, tab và xuống dòng. Không nên diễn giải nó thành “chỉ dấu cách ASCII”. Nếu tự thay delimiter thì hành vi phân tách token thay đổi theo mẫu mới; nhận định về bỏ dòng trống trong bảng áp dụng cho cấu hình mặc định.

`nextLine()` không dùng delimiter đang cấu hình để xác định ranh giới dòng. Chẳng hạn đổi delimiter thành dấu phẩy không biến `nextLine()` thành phương thức đọc từng trường CSV.

## 3. Quan sát trực tiếp cùng một đầu vào

Lưu thành `TokenVsLineDemo.java`:

```java
import java.util.Scanner;

public class TokenVsLineDemo {
    public static void main(String[] args) {
        String data = "Alice Nguyen\n\nHa Noi\n";

        System.out.println("TOKENS");
        try (Scanner tokens = new Scanner(data)) {
            while (tokens.hasNext()) {
                System.out.println("[" + tokens.next() + "]");
            }
        }

        System.out.println("LINES");
        try (Scanner lines = new Scanner(data)) {
            while (lines.hasNextLine()) {
                System.out.println("[" + lines.nextLine() + "]");
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 TokenVsLineDemo.java
java TokenVsLineDemo
```

Stdout chính xác:

```text
TOKENS
[Alice]
[Nguyen]
[Ha]
[Noi]
LINES
[Alice Nguyen]
[]
[Ha Noi]
```

Hai Scanner ở ví dụ này đọc hai nguồn String độc lập có nội dung giống nhau. Nhờ vậy, phép so sánh không bị ảnh hưởng bởi việc một Scanner đã tiêu thụ đầu vào trước đó.

Kết quả thể hiện hai lựa chọn mô hình dữ liệu:

- Nếu bài toán là đếm từ hoặc đọc dãy giá trị cách nhau bằng khoảng trắng, đọc token phù hợp.
- Nếu bài toán là đọc tên, câu, địa chỉ hoặc giữ dòng trống, đọc dòng phù hợp.
- Dấu xuống dòng cuối chuỗi kết thúc dòng `Ha Noi`; nó không tự tạo thêm một lần đọc chuỗi rỗng ở sau EOF. Ngược lại, cặp `\n\n` ở giữa tạo một dòng rỗng thực sự.

Dấu `[` và `]` trong kết quả do chương trình thêm vào để nhìn rõ chuỗi rỗng và khoảng trắng, không thuộc dữ liệu đầu vào.

## 4. Vì sao nextLine() trả chuỗi rỗng sau nextInt()?

Xét đầu vào:

```text
42
Alice Nguyen
```

Có thể biểu diễn dữ liệu và vị trí bằng `|`:

```text
Ban đầu:         |42\nAlice Nguyen\n
Sau nextInt():   42|\nAlice Nguyen\n
Sau nextLine():  42\n|Alice Nguyen\n
```

`nextInt()` đọc giá trị `42` và dừng trước delimiter đi sau token. Vị trí đang ở ngay trước dấu kết thúc dòng. Khi gọi `nextLine()`, phần còn lại của dòng ấy không có ký tự nào, nên kết quả là `""`. Dấu kết thúc dòng vẫn được tiêu thụ đúng theo công việc của `nextLine()`.

Nếu có hai dấu cách sau số, kết quả lại là `"  "`, không phải chuỗi rỗng. Nếu còn họ tên trên cùng dòng, kết quả có thể là `" Alice Nguyen"`. Vì vậy, không nên ghi nhớ thành quy tắc máy móc “sau nextInt, nextLine luôn trả rỗng”.

### Ví dụ chạy được với CRLF, dòng trống và dòng cuối không xuống dòng

Lưu thành `ScannerPositionDemo.java`:

```java
import java.util.Scanner;

public class ScannerPositionDemo {
    public static void main(String[] args) {
        String data = "42  Alice Nguyen\r\n\r\nHa Noi\nlast";

        try (Scanner scanner = new Scanner(data)) {
            System.out.println("number = " + scanner.nextInt());
            System.out.println("remainder = [" + scanner.nextLine() + "]");
            System.out.println("blank = [" + scanner.nextLine() + "]");
            System.out.println("city = [" + scanner.nextLine() + "]");
            System.out.println("last = [" + scanner.nextLine() + "]");
            System.out.println("hasNextLine = " + scanner.hasNextLine());
        }

        try (Scanner scanner = new Scanner("42\nAlice Nguyen\n")) {
            System.out.println("numberOnly = " + scanner.nextInt());
            System.out.println("emptyRemainder = ["
                    + scanner.nextLine() + "]");
            System.out.println("name = [" + scanner.nextLine() + "]");
        }
    }
}
```

Chạy:

```shell
javac -encoding UTF-8 ScannerPositionDemo.java
java ScannerPositionDemo
```

Stdout chính xác:

```text
number = 42
remainder = [  Alice Nguyen]
blank = []
city = [Ha Noi]
last = [last]
hasNextLine = false
numberOnly = 42
emptyRemainder = []
name = [Alice Nguyen]
```

Ở chuỗi đầu:

1. `nextInt()` chỉ nhận `42`.
2. `nextLine()` tiếp theo nhận cả hai dấu cách và họ tên còn lại.
3. `\r\n` kết thúc dòng và không xuất hiện trong String kết quả.
4. Cặp `\r\n` tiếp theo biểu diễn một dòng rỗng.
5. `last` vẫn là một dòng đọc được dù không có dấu xuống dòng ở cuối nguồn.

## 5. Chọn cách tổ chức nhập liệu

### Cách A: mỗi trường nằm trên một dòng

Với biểu mẫu nhập tuổi rồi nhập họ tên, có thể thống nhất dùng `nextLine()`, sau đó phân tích dòng tuổi. Cách này làm ranh giới tiêu thụ dữ liệu dễ theo dõi: mỗi lần thử đọc tuổi đã tiêu thụ đúng một dòng, kể cả dòng sai.

Lưu thành `LineFormDemo.java`:

```java
import java.util.Scanner;

public class LineFormDemo {
    private static int readAge(Scanner scanner) {
        while (scanner.hasNextLine()) {
            String line = scanner.nextLine();

            try {
                int age = Integer.parseInt(line.strip());
                if (age >= 0 && age <= 150) {
                    return age;
                }
            } catch (NumberFormatException ex) {
                // Dòng sai đã được tiêu thụ; lần sau đọc dòng mới.
            }

            System.out.println("Invalid age line");
        }

        throw new IllegalArgumentException("Missing age");
    }

    public static void main(String[] args) {
        String input = "oops\n19\nNguyen Van An\n";

        try (Scanner scanner = new Scanner(input)) {
            int age = readAge(scanner);

            if (!scanner.hasNextLine()) {
                throw new IllegalArgumentException("Missing name");
            }

            String name = scanner.nextLine();
            if (name.isBlank()) {
                throw new IllegalArgumentException("Blank name");
            }

            System.out.println("age = " + age);
            System.out.println("name = [" + name + "]");
        }
    }
}
```

Chạy:

```shell
javac -encoding UTF-8 LineFormDemo.java
java LineFormDemo
```

Stdout chính xác:

```text
Invalid age line
age = 19
name = [Nguyen Van An]
```

Chương trình dùng String cố định để tái lập kết quả. Trong ứng dụng tương tác, nguồn của Scanner có thể là stdin do ứng dụng sở hữu; quy tắc đọc dòng vẫn như trên.

`strip()` chỉ được áp dụng cho dòng tuổi vì ví dụ cho phép khoảng trắng ngoài cùng của số. Họ tên được giữ nguyên. Không tự động xóa khoảng trắng của mọi trường nếu hợp đồng dữ liệu cần bảo toàn chúng.

`Integer.parseInt()` nhận một chuỗi biểu diễn số nguyên và có thể ném `NumberFormatException` khi chuỗi không hợp lệ hoặc vượt phạm vi int. Nó không thay thế toàn bộ cơ chế số theo Locale của Scanner. Xem [Integer.parseInt](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String)). Ví dụ chọn quy tắc đơn giản: cả dòng sau khi bỏ trắng ngoài cùng phải là một số tuổi hợp lệ.

Chẳng hạn dòng `19 20` bị từ chối, còn `nextInt()` có thể đọc riêng token `19` trước. Đây là khác biệt về yêu cầu dữ liệu, không phải một bên “đọc số tốt hơn”.

### Cách B: đọc token rồi xử lý rõ phần còn lại

Nếu định dạng thật sự kết hợp token và dòng, vẫn có thể dùng cả hai nhóm, miễn là chỉ rõ phần nào phải giữ, kiểm tra hoặc bỏ đi.

Đoạn minh họa sau giả sử đã có `Scanner scanner`, dòng đầu chỉ được chứa một số nguyên:

```java
int age = scanner.nextInt();
String remainder = scanner.nextLine();

if (!remainder.isBlank()) {
    throw new IllegalArgumentException(
            "Unexpected text after age: " + remainder);
}

if (!scanner.hasNextLine()) {
    throw new IllegalArgumentException("Missing name");
}
String name = scanner.nextLine();
```

Đây không phải chương trình độc lập và chưa xử lý mọi lỗi đầu vào của ứng dụng. Nó minh họa rằng việc đọc phần dư là một quyết định có chủ đích, có kiểm tra.

Nếu hợp đồng cho phép `42 Alice Nguyen` trên cùng dòng, `remainder` chính là nơi có dữ liệu tên. Thêm một lệnh `nextLine()` rồi bỏ kết quả sẽ làm mất tên. Chỉ “đọc bỏ dòng” khi định dạng cho phép bỏ phần còn lại; nếu đó là dữ liệu sai, nên báo lỗi để người dùng biết.

Không thay `nextLine()` bằng `next()` chỉ để tránh chuỗi rỗng nếu yêu cầu vẫn là họ tên đầy đủ: tên `Nguyen Van An` sẽ bị tách thành ba token.

## 6. Kiểm tra dữ liệu phải cùng đơn vị với cách đọc

Đọc token:

```java
while (scanner.hasNext()) {
    String token = scanner.next();
    // Xử lý một token.
}
```

Đọc dòng:

```java
while (scanner.hasNextLine()) {
    String line = scanner.nextLine();
    // Xử lý một dòng, kể cả dòng rỗng.
}
```

Hai đoạn trên giả sử biến Scanner đã tồn tại. Không dùng `hasNext()` để điều khiển việc bảo toàn mọi dòng. Một nguồn chỉ có `"\n"` có một dòng rỗng đọc được, nhưng không có token theo delimiter mặc định.

Cũng cần phân biệt:

- `""` từ `nextLine()`: một dòng hoặc phần dòng rỗng đã được đọc.
- `hasNextLine() == false`: không còn dòng để đọc, nếu nguồn kết thúc bình thường.
- Gọi `nextLine()` khi hết dữ liệu: ném `NoSuchElementException`, không trả về `null`.
- `hasNextInt() == false`: có thể do token tiếp theo không phải số nguyên, không nhất thiết đã hết dữ liệu.

Các phương thức `hasNext...` kiểm tra mà không tiến vị trí tiêu thụ dữ liệu. Nếu đã xác định token sai và muốn bỏ nó, cần một thao tác đọc hoặc bỏ qua có chủ đích. Chỉ lặp lại `hasNextInt()` trên cùng token sai có thể khiến chương trình không tiến triển. Tương tự, khi `nextInt()` ném `InputMismatchException`, token gây lỗi chưa bị tiêu thụ; phải quyết định bỏ token, bỏ phần dòng hay kết thúc.

Với nguồn I/O, nên kiểm tra `scanner.ioException()` sau khi đọc xong nếu cần phân biệt hết dữ liệu bình thường với lỗi đọc nguồn. Bài này dùng String để tập trung quan sát ranh giới token và dòng.

## 7. Các lỗi thường gặp và cách xét lại

| Cách làm | Hệ quả có thể xảy ra | Cách xét lại |
| --- | --- | --- |
| Luôn thêm một `nextLine()` sau mọi `nextInt()` | Bỏ mất dữ liệu còn trên cùng dòng | Vẽ vị trí đọc và xác định phần dư |
| Đọc họ tên bằng `next()` | Chỉ lấy từ đầu | Đọc cả dòng nếu tên là một trường |
| Đọc tên bằng `nextLine()` ngay sau số | Nhận phần dòng số thay vì tên ở dòng sau | Thống nhất đọc dòng, hoặc xử lý phần dư rõ ràng |
| Dùng `hasNext()` cho vòng đọc dòng | Bỏ sót cấu trúc dòng trắng | Ghép `hasNextLine()` với `nextLine()` |
| Dùng `trim()` hoặc `strip()` cho mọi dòng | Xóa khoảng trắng có ý nghĩa | Chỉ chuẩn hóa trường được hợp đồng cho phép |
| Tạo hai Scanner trên cùng System.in | Các bộ đệm đọc trước có thể làm luồng xử lý khó đoán | Một nơi sở hữu nguồn và truyền Scanner vào hàm |
| Chờ `nextLine()` trả `null` ở EOF | Xử lý EOF sai | Kiểm tra `hasNextLine()` |

Với nguồn tương tác, cả kiểm tra lẫn đọc đều có thể chờ thêm đầu vào. “Có phương thức hasNext” không đồng nghĩa với “không bao giờ chặn”. Một dòng rất dài hoặc nguồn không gửi dấu kết thúc dòng cũng có thể làm thao tác đọc dòng phải giữ nhiều dữ liệu; chọn cách nhập phù hợp với giới hạn của nguồn.

## 8. Tự kiểm chứng vị trí đọc

Thử thay đầu vào trong `ScannerPositionDemo` rồi dự đoán trước khi chạy:

1. Với `"42   \nAlice Nguyen\n"`, lần `nextLine()` đầu sau số trả ba dấu cách.
2. Với `"42"`, sau `nextInt()` nguồn đã hết; `hasNextLine()` là `false`, không có “dòng dư rỗng” để đọc.
3. Với `"\n"`, `hasNextLine()` là `true` trước lần đọc đầu và `nextLine()` trả `""`.
4. Với `"A B,C D\n"` và delimiter dấu phẩy, `next()` có thể nhận `"A B"`; `nextLine()` vẫn tuân theo dòng, không theo dấu phẩy.

Mỗi lần phân tích, ghi ba thứ: vị trí trước lệnh, dữ liệu lệnh trả về, vị trí sau lệnh. Thói quen này giải thích được cả trường hợp chuỗi rỗng lẫn trường hợp mất dữ liệu khi trộn đọc token và đọc dòng.
