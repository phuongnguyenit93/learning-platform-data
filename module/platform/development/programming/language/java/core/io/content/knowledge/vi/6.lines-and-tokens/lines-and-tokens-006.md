# `Scanner.next()`, `nextLine()` và phần xuống dòng còn lại

Khi nhập dữ liệu trong Java, một lỗi thường gặp là: chương trình đọc số bằng `Scanner.nextInt()`, ngay sau đó hỏi tên bằng `nextLine()`, nhưng biến tên lại là chuỗi rỗng hoặc chương trình dường như “bỏ qua” câu hỏi. Tương tự, gọi `next()` trước `nextLine()` có thể khiến kết quả lần đọc sau chỉ là **phần còn lại của dòng**, thay vì một dòng hoàn toàn mới.

Để hiểu và xử lý chính xác, cần phân biệt hai cách đọc trong `java.util.Scanner`:

- **Đọc token:** `next()`, `nextInt()`, `nextDouble()`… làm việc với từng mục được ngăn bằng **delimiter** (dấu phân tách).
- **Đọc dòng:** `nextLine()` đọc **phần còn lại của dòng hiện tại**, đến hết dấu kết thúc dòng và chuyển vị trí đọc sang dòng kế tiếp.

Vấn đề không nằm ở việc `nextLine()` bị lỗi; đó là hệ quả của **vị trí quét hiện tại** sau một thao tác đọc token. Bài học này giải thích cơ chế, minh họa trường hợp có/không có dấu cách còn lại, và giới thiệu các cách viết code đúng tùy loại dữ liệu nhập.

## 1. Token và line khác nhau như thế nào?

### Token: một đơn vị tách bởi delimiter

`Scanner` sử dụng một mẫu delimiter để chia đầu vào thành token. Theo mặc định, delimiter nhận diện các ký tự khoảng trắng theo quy tắc của Java, bao gồm khoảng trắng thông thường và dấu xuống dòng.

Với chuỗi đầu vào:

~~~text
Java Core
27
Nguyễn Văn An
~~~

Các lần gọi `next()` liên tiếp nhận các token như:

~~~text
"Java" -> "Core" -> "27" -> "Nguyễn" -> "Văn" -> "An"
~~~

`next()` bỏ qua delimiter ở trước token kế tiếp, sau đó trả về token tương ứng. Nó **không tự trả lại cả dòng có khoảng trắng** và không có khái niệm “một tên đầy đủ” nếu tên có nhiều từ. Các phương thức như `nextInt()` cũng dùng cơ chế tìm token rồi chuyển đổi token theo kiểu dữ liệu cần đọc.

### Line: phần văn bản tới dấu kết thúc dòng

`nextLine()` hoạt động theo đường **dòng văn bản**. Nó trả về văn bản **còn lại của dòng tại vị trí đang quét**, không bao gồm dấu xuống dòng kết thúc dòng đó. Sau đó vị trí quét được đặt sang đầu dòng tiếp theo.

Với cùng chuỗi đầu vào và vị trí bắt đầu:

~~~java
String firstLine = scanner.nextLine(); // "Java Core"
String secondLine = scanner.nextLine(); // "27"
String thirdLine = scanner.nextLine(); // "Nguyễn Văn An"
~~~

Đây là các dòng minh họa với `scanner` là `Scanner` đã tạo từ đúng dữ liệu trên. Mỗi lần đọc lấy một **dòng**, bao gồm khoảng trắng nằm trong dòng. `nextLine()` có thể trả về `""` nếu vị trí hiện tại đang ngay trước một dấu kết thúc dòng.

**Mô hình dễ nhớ:** `next()` hỏi “token tiếp theo là gì?”, còn `nextLine()` hỏi “từ vị trí hiện tại đến hết dòng còn gì?”.

## 2. Vì sao `next()` và `nextLine()` cho kết quả bất ngờ?

Xét đầu vào một dòng `Java Core`, kết thúc bằng Enter. Để nhìn rõ khoảng trắng và ký tự kết thúc dòng, ta biểu diễn `↵` là Enter:

~~~text
Java Core↵
^^^^       next() lấy token "Java"
    ^^^^^  nextLine() kế tiếp lấy " Core" (bao gồm dấu cách đầu)
         ↵ dấu kết thúc dòng được nextLine() tiêu thụ
~~~

Nếu gọi `next()` trước, nó trả về token `Java`; vị trí quét nằm tại phần phân tách theo sau token. Khi gọi `nextLine()` ngay sau đó, phương thức **không tự bỏ phần còn lại để nhảy tới dòng mới**: nó trả về `" Core"`, có dấu cách ở đầu.

Nếu đầu vào là:

~~~text
Java↵
Core↵
~~~

thì sau `next()` lấy `"Java"`, phần còn lại trước Enter **không có ký tự nội dung**. Vì thế lần `nextLine()` kế tiếp trả về **`""`**, tiêu thụ Enter rồi đưa vị trí đến đầu dòng `Core`.

Hai trường hợp chỉ khác việc có chữ ở phần còn lại của dòng hay không. Do đó, không nên ghi nhớ máy móc rằng “sau `next()` thì `nextLine()` luôn rỗng”. Nó trả **phần còn lại của dòng hiện tại**, có thể rỗng, có khoảng trắng hoặc chứa cả văn bản.

## 3. Trường hợp quen thuộc: `nextInt()` rồi `nextLine()`

Giả sử chương trình yêu cầu tuổi và họ tên:

~~~text
27↵
Nguyễn Văn An↵
~~~

Cách viết dễ gặp:

~~~java
System.out.print("Tuổi: ");
int age = scanner.nextInt();

System.out.print("Họ tên: ");
String fullName = scanner.nextLine();
~~~

Đây là **đoạn minh họa** đặt bên trong một phương thức có `scanner` đang đọc từ đầu vào. Với mẫu dữ liệu trên, `nextInt()` nhận token số `27` nhưng **không đọc cả dòng như `nextLine()`**. Phần còn lại trước Enter trống, nên `nextLine()` ngay sau đó nhận chuỗi `""` và tiêu thụ dấu kết thúc dòng. Tên trên dòng kế tiếp **chưa được đọc**.

Minh họa vị trí quét:

~~~text
Trước:
27↵
Nguyễn Văn An↵

Sau nextInt():
27|↵              ("|" là vị trí đọc đang xét)
Nguyễn Văn An↵

Sau nextLine():
27↵
|Nguyễn Văn An↵  (nextLine đã trả "")
~~~

Lưu ý: đây là mô hình trực quan về **hành vi logic**; không nên suy diễn đây là mô tả byte hoặc chỉ số buffer nội bộ của `Scanner`.

### Nếu sau số có hai dấu cách thì sao?

Với:

~~~text
27··↵
Nguyễn Văn An↵
~~~

ở đây `·` biểu diễn một dấu cách. Sau `nextInt()`, gọi `nextLine()` trả về **hai dấu cách** (`"  "`) chứ không phải chuỗi rỗng. Vì vậy, kiểm tra `fullName.isEmpty()` không đủ để phát hiện mọi trường hợp “chưa đọc tên”.

Nếu trên **cùng một dòng** có nội dung sau số, ví dụ `27 Nguyễn Văn An↵`, `nextLine()` có thể trả về `" Nguyễn Văn An"`. Đó là dữ liệu có ý nghĩa và **không nên tự ý bỏ**.

## 4. Ví dụ Java 17 chạy được: cùng dữ liệu, ba hành vi

Chương trình sau đọc từ `String` để kết quả ổn định, không cần nhập tay khi kiểm tra. Nó tạo nhiều `Scanner` độc lập nhằm so sánh rõ:

1. `next()` + `nextLine()` trên một dòng nhiều từ.
2. `nextInt()` + `nextLine()` ngay tại ranh giới dòng.
3. Đọc **toàn bộ dòng** rồi mới chuyển số, tránh tình trạng sót newline.
4. Phần đuôi dòng chỉ gồm hai dấu cách sau token số.

Lưu tệp **`ScannerTokenLineDemo.java`**:

~~~java
import java.util.Scanner;

public class ScannerTokenLineDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("Java Core\n")) {
            String token = scanner.next();
            String restOfLine = scanner.nextLine();
            System.out.println("Token: [" + token + "]");
            System.out.println("Remaining line: [" + restOfLine + "]");
        }

        String input = "27\nNguyễn Văn An\n";
        try (Scanner scanner = new Scanner(input)) {
            int age = scanner.nextInt();
            String tail = scanner.nextLine();
            String name = scanner.nextLine();

            System.out.println("Age: " + age);
            System.out.println("After nextInt: [" + tail + "]");
            System.out.println("Next full line: [" + name + "]");
        }

        try (Scanner scanner = new Scanner(input)) {
            int age = Integer.parseInt(scanner.nextLine().trim());
            String name = scanner.nextLine();

            System.out.println("Line-based age: " + age);
            System.out.println("Line-based name: [" + name + "]");
        }

        try (Scanner scanner = new Scanner("27  \nAn\n")) {
            int age = scanner.nextInt();
            String tail = scanner.nextLine();
            System.out.println("Age with spaces: " + age);
            System.out.println("Tail with spaces: [" + tail + "]");
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 ScannerTokenLineDemo.java
java ScannerTokenLineDemo
~~~

Kết quả chuẩn (những khoảng trắng bên trong dấu ngoặc vuông là **cố ý**):

~~~text
Token: [Java]
Remaining line: [ Core]
Age: 27
After nextInt: []
Next full line: [Nguyễn Văn An]
Line-based age: 27
Line-based name: [Nguyễn Văn An]
Age with spaces: 27
Tail with spaces: [  ]
~~~

Giải thích:

- Dòng `Remaining line: [ Core]` có **một khoảng trắng** trước `Core` vì `next()` chỉ lấy token đầu tiên `Java`.
- `After nextInt: []` rỗng vì sau `27` là dấu xuống dòng, và `nextLine()` tiêu thụ nó.
- Sau khi `nextLine()` đầu tiên đã lấy phần đuôi rỗng, lần `nextLine()` thứ hai mới trả lại tên đầy đủ.
- Phương án đọc theo dòng `Integer.parseInt(scanner.nextLine().trim())` chuyển văn bản số thành `int` sau khi đã tiêu thụ hết dòng, nên lần `nextLine()` tiếp theo đọc được tên ngay.
- Dòng `Tail with spaces: [  ]` chứa **hai khoảng trắng**, chứng tỏ phương thức trả về phần còn lại của dòng chứ không luôn trả chuỗi rỗng.
- `Scanner` được tạo từ `String` nên không sử dụng `System.in`; đóng bằng `try-with-resources` không làm ảnh hưởng đến luồng nhập chuẩn của ứng dụng.

Khi hiển thị trên terminal không hỗ trợ Unicode hoặc cấu hình encoding không phù hợp, tên tiếng Việt trên màn hình có thể hiển thị khác; hành vi phân tách token/dòng trong `String` vẫn như minh họa.

## 5. Ba cách xử lý đúng và khi nào chọn

### Cách A — Ưu tiên đọc toàn dòng, rồi phân tích dữ liệu

Nếu mỗi câu hỏi/giá trị dùng **một dòng riêng**, cách rõ ràng nhất là thống nhất dùng `nextLine()`:

~~~java
int age = Integer.parseInt(scanner.nextLine().trim());
String fullName = scanner.nextLine();
~~~

Ưu điểm:

- Không trộn hai cơ chế token và line.
- Có thể đọc tên, địa chỉ, câu văn nhiều từ mà không cắt mất khoảng trắng ở giữa.
- Tương đối dễ kiểm tra từng dòng, hiển thị lỗi và yêu cầu người dùng nhập lại.

Nhược điểm:

- Phải tự xử lý lỗi chuyển đổi: `Integer.parseInt` có thể ném `NumberFormatException` khi dòng nhập rỗng, không phải số hoặc vượt phạm vi `int`.
- `trim()` chỉ nên áp dụng cho dòng tuổi khi muốn bỏ khoảng trắng đầu/cuối; với tên, password hoặc dữ liệu mà khoảng trắng có ý nghĩa, **không tự ý trim** nếu đặc tả không yêu cầu.
- Nếu dữ liệu có nhiều trường trên cùng một dòng, cần quy ước tách trường riêng hoặc parse dòng có cấu trúc.

Một cách xác thực an toàn là đọc dòng vào biến trước:

~~~java
String ageLine = scanner.nextLine();
try {
    int age = Integer.parseInt(ageLine.trim());
    // Xử lý tuổi hợp lệ tại đây.
} catch (NumberFormatException ex) {
    // Yêu cầu nhập lại hoặc báo lỗi theo thiết kế ứng dụng.
}
~~~

Đây là **đoạn phương thức minh họa**; muốn tránh lỗi khi hết dữ liệu cần kiểm tra `hasNextLine()` trước. Lưu ý comment trong khối `try`/`catch` biểu diễn nơi ứng dụng xử lý nghiệp vụ cụ thể, không tự thực hiện yêu cầu nhập lại.

### Cách B — Đọc token, rồi chủ động bỏ phần còn lại của dòng

Nếu thực sự muốn dùng `nextInt()` cho tuổi và **biết chắc** phần còn lại của dòng không chứa dữ liệu cần giữ:

~~~java
int age = scanner.nextInt();
scanner.nextLine();          // Tiêu thụ phần còn lại của dòng tuổi.
String fullName = scanner.nextLine();
~~~

Lệnh `scanner.nextLine()` ở giữa không có nghĩa “xóa newline” theo một lệnh chuyên biệt. Nó **đọc và bỏ toàn bộ phần còn lại của dòng hiện tại, kể cả phần nội dung nếu có**, rồi đưa vị trí sang dòng tiếp theo.

**Chỉ sử dụng khi định dạng đầu vào được xác định rõ:** mỗi dòng tuổi chỉ có token tuổi (và có thể có khoảng trắng cuối dòng), còn tên bắt đầu ở dòng kế tiếp. Nếu người dùng nhập `27 Nguyễn Văn An` trên cùng một dòng, lời gọi bổ sung đó sẽ **bỏ mất tên**.

Cũng không cần thêm `nextLine()` sau **mọi** lời gọi `nextInt()`: nếu đang cố ý đọc nhiều token trên cùng một dòng, việc bỏ phần còn lại sẽ làm mất dữ liệu. Quy tắc phải dựa trên **định dạng nhập** và vị trí của dữ liệu tiếp theo.

### Cách C — Đọc toàn dòng rồi dùng `Scanner` riêng để tách token

Nếu mỗi dòng chứa một record nhiều trường, ví dụ:

~~~text
27 Nguyễn Văn An
~~~

có thể lấy nguyên dòng từ luồng chính, sau đó xử lý cấu trúc dòng trong một `Scanner` khác:

~~~java
String record = scanner.nextLine();
try (Scanner lineScanner = new Scanner(record)) {
    int age = lineScanner.nextInt();
    String name = lineScanner.nextLine().stripLeading();
    // age = 27; name = "Nguyễn Văn An"
}
~~~

Đây là **đoạn minh họa**, trong đó `scanner` đọc dữ liệu đầu vào của ứng dụng. `stripLeading()` bỏ khoảng trắng đầu của phần tên sau token số, **không xóa các dấu cách bên trong tên**. Nếu record có cấu trúc cố định hơn (CSV, TSV, JSON…), hãy dùng parser phù hợp với định dạng đó thay vì tự tạo quy ước tách bằng khoảng trắng.

Chỉ nên đặt `lineScanner` trên **chuỗi dòng đã lấy**, tránh tạo nhiều `Scanner` độc lập cùng đọc `System.in` vì mỗi scanner có buffer riêng và có thể đọc trước dữ liệu làm scanner khác không nhận được điều mình mong đợi.

## 6. `hasNext()` và `hasNextLine()`: kiểm tra đúng thứ sắp đọc

Hai phương thức kiểm tra có mục đích khác nhau:

| Gọi kiểm tra | Câu hỏi trả lời | Thường đi với |
|---|---|---|
| `hasNext()` | Còn **token** tiếp theo không? | `next()` |
| `hasNextInt()` | Token tiếp theo có đọc được thành `int` không? | `nextInt()` |
| `hasNextLine()` | Còn **dòng** nào để đọc không? | `nextLine()` |

Ví dụ duyệt từng dòng an toàn:

~~~java
while (scanner.hasNextLine()) {
    String line = scanner.nextLine();
    System.out.println("Line: [" + line + "]");
}
~~~

Còn nếu chỉ lấy các token:

~~~java
while (scanner.hasNext()) {
    String token = scanner.next();
    System.out.println("Token: [" + token + "]");
}
~~~

Hai vòng lặp là các **đoạn minh họa** dùng `scanner` đã được tạo. Một dòng trắng có thể được `nextLine()` trả thành `""`, trong khi `next()` với delimiter mặc định **bỏ qua khoảng trắng** và không đưa ra token rỗng cho dòng trắng đó.

`hasNextInt()` hữu ích để tránh `InputMismatchException` khi token không thể chuyển sang số; tuy nhiên, nếu token sai, bạn phải quyết định **bỏ token đó, báo lỗi hoặc đọc lại**. Gọi `hasNextInt()` nhiều lần mà không di chuyển vị trí đọc sẽ không tự sửa đầu vào.

Các phương thức đọc hoặc kiểm tra trên luồng nhập tương tác có thể **chờ dữ liệu**. `hasNextLine()` không bảo đảm dữ liệu tiếp theo đã có sẵn ngay lập tức.

## 7. Dấu kết thúc dòng, khoảng trắng và delimiter tùy chỉnh

### Dấu kết thúc dòng

Dấu kết thúc dòng thường là LF (`\n`) hoặc CRLF (`\r\n`) tùy nguồn và môi trường. `Scanner.nextLine()` nhận diện các dạng kết thúc dòng theo hợp đồng Java, **trả nội dung dòng mà không kèm dấu kết thúc dòng**.

Nếu vị trí đọc đang trước dấu xuống dòng, `nextLine()` có thể nhận `""`. Một dòng trống thực sự trong file cũng có thể cho `""`. Cùng kết quả chuỗi rỗng **không đủ để suy ra nguyên nhân**; phải biết vị trí đọc và dữ liệu đầu vào.

Nếu dòng cuối **không có dấu kết thúc dòng** nhưng vẫn còn nội dung, `nextLine()` vẫn có thể trả về phần nội dung cuối. Đừng giả định dòng cuối cần bắt buộc có Enter.

### Khoảng trắng còn lại

Dấu cách hoặc tab trước Enter có thể trở thành nội dung trả về từ `nextLine()` sau khi một token được đọc. Để phát hiện “phần còn lại chỉ có khoảng trắng”:

~~~java
String remainder = scanner.nextLine();
boolean onlyWhitespace = remainder.isBlank();
~~~

`isBlank()` cũng trả `true` với chuỗi rỗng. Tuy nhiên, **phát hiện không đồng nghĩa với tự động xóa**: một số định dạng xem khoảng trắng là dữ liệu hợp lệ. Nếu cần bảo toàn dữ liệu, giữ `remainder` nguyên vẹn.

### Delimiter tùy chỉnh

`Scanner.useDelimiter(pattern)` thay đổi quy tắc tách token. Ví dụ:

~~~java
try (Scanner scanner = new Scanner("red,blue,green")) {
    scanner.useDelimiter(",");
    System.out.println(scanner.next()); // red
    System.out.println(scanner.next()); // blue
    System.out.println(scanner.next()); // green
}
~~~

Đây là đoạn Java có thể đặt vào phương thức `main` với import `java.util.Scanner`; nó chỉ minh họa việc thay delimiter. **`nextLine()` không trở thành “đọc đến dấu phẩy”**: nó vẫn làm việc theo dòng văn bản. Vì vậy, thay delimiter tùy chỉnh càng khiến việc pha trộn `next()` và `nextLine()` cần suy xét.

`useDelimiter` nhận **biểu thức chính quy**, không nhất thiết là chuỗi ký tự thuần túy. Với delimiter đặc biệt như dấu chấm (`.`) cần escape đúng regex; truyền thẳng `"."` sẽ mang ý nghĩa “bất kỳ ký tự nào” trong regex.

## 8. Khi nhập từ bàn phím thật: một scanner, vòng đời rõ ràng

Ví dụ tương tác với terminal, dùng **một `Scanner` duy nhất** cho `System.in` và đọc cả hai trường theo dòng:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Scanner;

public class ConsoleProfile {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);

        System.out.print("Tuổi: ");
        if (!scanner.hasNextLine()) return;
        String rawAge = scanner.nextLine();

        int age;
        try {
            age = Integer.parseInt(rawAge.trim());
        } catch (NumberFormatException ex) {
            System.out.println("Tuổi không hợp lệ.");
            return;
        }

        System.out.print("Họ tên: ");
        if (!scanner.hasNextLine()) return;
        String name = scanner.nextLine();

        System.out.println("Tuổi: " + age);
        System.out.println("Họ tên: " + name);
    }
}
~~~

Lưu thành **`ConsoleProfile.java`**, biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 ConsoleProfile.java
java ConsoleProfile
~~~

Một **phiên chạy mẫu** khi người dùng lần lượt nhập `27` và `Nguyễn Văn An` rồi Enter (hai dòng người dùng nhập là phần phản hồi bàn phím):

~~~text
Tuổi: 27
Họ tên: Nguyễn Văn An
Tuổi: 27
Họ tên: Nguyễn Văn An
~~~

Trong ví dụ, `new Scanner(System.in, StandardCharsets.UTF_8)` quy định cách đọc byte đầu vào thành ký tự. Chọn charset phù hợp với terminal thực tế. `Scanner.close()` cũng đóng nguồn đầu vào nếu nguồn triển khai `Closeable`; bởi `System.in` thường là tài nguyên chung thuộc vòng đời ứng dụng, ví dụ **không tự đóng `System.in`** khi kết thúc thao tác ngắn này.

Nếu ứng dụng tự tạo và sở hữu nguồn (tệp hoặc `StringReader` chẳng hạn), hãy dùng `try-with-resources` để đóng scanner đúng lúc. Với input được caller/framework sở hữu, cần tuân thủ hợp đồng ownership của tầng cấp tài nguyên.

## 9. Ngoại lệ và những nhầm lẫn cần tránh

| Nhầm lẫn | Vì sao sai? | Cách xử lý |
|---|---|---|
| “`next()` đọc một dòng.” | Nó đọc một **token** theo delimiter hiện tại. | Dùng `nextLine()` nếu cần cả dòng. |
| “`nextLine()` sau `nextInt()` luôn rỗng.” | Có thể còn khoảng trắng hoặc văn bản cùng dòng. | Hiểu nó trả về phần còn lại của dòng. |
| “Thêm một `nextLine()` ở mọi nơi là hết lỗi.” | Có thể bỏ nhầm dữ liệu hợp lệ trên cùng dòng. | Chỉ bỏ phần đuôi khi quy ước input cho phép. |
| “Gọi `nextLine()` sẽ lấy dòng tiếp theo cho dù đang đứng giữa dòng.” | Nó bắt đầu từ vị trí **hiện tại**, không tự nhảy trước một dòng. | Xác định vị trí sau thao tác token trước. |
| “Đọc `nextInt()` rồi trim tên là đủ.” | Nếu tên bị bỏ qua thì trim không khôi phục được. | Thiết kế lại cách đọc hoặc tiêu thụ ranh giới dòng có chủ ý. |
| “`hasNext()` và `hasNextLine()` như nhau.” | Một bên kiểm tra token; bên kia kiểm tra line, đặc biệt khác với dòng trống. | Dùng kiểm tra tương ứng với thao tác đọc. |
| “`nextInt()` đọc giá trị nào cũng được.” | Token không phải số hoặc vượt giới hạn có thể ném `InputMismatchException`. | Kiểm tra `hasNextInt()` hoặc đọc dòng rồi parse/validate. |
| “`nextLine()` luôn có dòng.” | Khi dữ liệu cạn, có thể ném `NoSuchElementException`. | Kiểm tra `hasNextLine()` hoặc xử lý hết input. |
| “Có thể tạo nhiều Scanner cùng đọc `System.in`.” | Buffer đọc trước khiến scanner này có thể lấy dữ liệu mà scanner kia cần. | Dùng một scanner với vòng đời rõ ràng. |
| “`scanner.close()` chỉ đóng wrapper.” | Nó đóng input source nếu source là `Closeable`. | Xác định ownership trước khi đóng scanner bọc `System.in`. |

### Trường hợp phân tích số có dấu phẩy thập phân

`Scanner.nextDouble()` xử lý định dạng số theo **locale**. Dấu chấm hoặc dấu phẩy có thể có ý nghĩa khác nhau giữa các locale. Đây là vấn đề **phân tích nội dung token**, tách biệt với vấn đề **ranh giới dòng**: ngay cả khi token số hợp lệ, `nextLine()` sau đó vẫn đọc phần còn lại của dòng.

Khi cần quy ước số ổn định, có thể chủ động `useLocale(...)` theo yêu cầu đầu vào; không nên coi việc đặt locale là cách sửa lỗi newline.

## 10. Tự kiểm tra

**Câu 1.** Input là `"An Bình\n"`. `next()` trả gì, `nextLine()` ngay sau đó trả gì?

> **Đáp án:** `next()` trả `"An"`; `nextLine()` trả `" Bình"`, gồm một khoảng trắng đầu. Dấu `\n` không nằm trong chuỗi trả về.

**Câu 2.** Input là `"42\nHà Nội\n"`. Sau `nextInt()` rồi `nextLine()`, kết quả đọc dòng là gì?

> **Đáp án:** `nextInt()` trả `42`; `nextLine()` trả `""` vì phần còn lại ngay sau token số đến cuối dòng là rỗng. Gọi `nextLine()` tiếp mới đọc `"Hà Nội"`.

**Câu 3.** Input là `"42  Hà Nội\n"` (hai dấu cách giữa số và tên). Có nên bỏ kết quả `nextLine()` đầu tiên sau `nextInt()` không?

> **Đáp án:** Không nếu cần giữ tên. `nextLine()` trả `"  Hà Nội"`; bỏ chuỗi này làm mất dữ liệu trên cùng một dòng.

**Câu 4.** Muốn nhập tuổi ở dòng 1 và họ tên có nhiều từ ở dòng 2, cách nào dễ hiểu và ít lỗi nhất?

> **Đáp án:** `Integer.parseInt(scanner.nextLine().trim())` cho tuổi (có xử lý lỗi), rồi `scanner.nextLine()` cho tên. Cả hai cùng theo **ranh giới dòng**.

**Câu 5.** Input gồm một dòng trống rồi một dòng `"hello"`. Vì sao vòng lặp `nextLine()` và `next()` cho kết quả khác?

> **Đáp án:** `nextLine()` nhận cả dòng trống, trả `""` trước `"hello"`; `next()` bỏ qua khoảng trắng mặc định nên token đầu tiên là `"hello"`.

**Câu 6.** Có nên đóng scanner trong một helper nhận `System.in` của ứng dụng không?

> **Đáp án:** Chỉ khi hợp đồng cho phép đóng nguồn đó. Vì đóng `Scanner` có thể đóng luôn `System.in`, helper chỉ mượn nguồn chung cần để chủ sở hữu quản lý vòng đời.

## Ghi nhớ

**`next()`/`nextInt()` đọc token; `nextLine()` đọc phần còn lại của dòng tại vị trí hiện tại và tiêu thụ dấu kết thúc dòng.** Phần còn lại ấy có thể rỗng, chỉ có khoảng trắng, hoặc chứa văn bản thực sự. Hãy chọn một chiến lược nhập nhất quán: nếu dữ liệu được tổ chức theo dòng, **đọc dòng trước rồi mới parse**; nếu trộn token và dòng, chỉ chủ động bỏ phần đuôi khi chắc chắn nó không mang dữ liệu cần giữ.

**Tài liệu tham khảo:** [Java SE 17 — `java.util.Scanner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html).