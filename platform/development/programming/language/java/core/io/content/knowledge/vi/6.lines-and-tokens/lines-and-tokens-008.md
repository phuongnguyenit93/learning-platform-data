# Scanner.hasNext(), InputMismatchException và xử lý token không hợp lệ

## 1. Bài toán: đầu vào có thể chứa token sai kiểu

**Scanner** trong gói **java.util** dùng để đọc văn bản, tách dữ liệu thành **token** theo một biểu thức phân cách (**delimiter**) rồi chuyển token sang kiểu Java như **int**, **double**, **boolean** hoặc lấy dưới dạng **String**. Delimiter mặc định là khoảng trắng theo quy tắc của **Character.isWhitespace**, thường bao gồm khoảng trắng, tab và dấu xuống dòng.

Ví dụ với đầu vào:

~~~text
12 abc 3.5 -7 2147483648 25
~~~

Có sáu token: **12**, **abc**, **3.5**, **-7**, **2147483648**, **25**. Nếu chương trình kỳ vọng tất cả là **int** thì **abc**, **3.5** và **2147483648** không đọc được bằng **nextInt()** (số cuối vượt giới hạn int 32-bit có dấu). Sai token không đồng nghĩa với việc luồng đã hết. Cần phân biệt:

- **Còn token không?** → **hasNext()**.
- **Token kế tiếp có thể đọc thành int không?** → **hasNextInt()**.
- **Đọc và chuyển token thành int** → **nextInt()**.
- **Token sai kiểu khi gọi nextInt()** → **InputMismatchException**.
- **Không còn token mà vẫn gọi nextInt()** → **NoSuchElementException**.

Điểm quan trọng nhất là **token gây InputMismatchException không tự bị Scanner bỏ qua**. Nếu cứ gọi lại **nextInt()** trên cùng token lỗi, chương trình có thể lặp lỗi vô hạn. Phải quyết định **bỏ token**, **bỏ cả dòng**, **thông báo người dùng nhập lại**, hoặc **dừng với thông báo lỗi** tùy bài toán.

## 2. Cơ chế token: delimiter, vị trí đọc và việc tiêu thụ dữ liệu

Scanner duy trì một vị trí đọc trên nguồn văn bản. Với delimiter mặc định, các dấu cách hoặc xuống dòng ngăn cách token; Scanner thường bỏ qua delimiter trước khi lấy token kế tiếp.

~~~text
Dữ liệu:       "  12   abc \n 25 "
Token:            12   abc    25
Sau nextInt():          ↑
                  token 12 đã được tiêu thụ;
                  token kế tiếp là abc.
~~~

| Phương thức | Trả về | Có tiêu thụ token hợp lệ? | Ý nghĩa |
| --- | --- | --- | --- |
| **hasNext()** | boolean | **Không** | Có một token kế tiếp bất kỳ hay không |
| **next()** | String | **Có** | Lấy token kế tiếp dưới dạng chuỗi |
| **hasNextInt()** | boolean | **Không** | Token kế tiếp chuyển được thành int theo radix/locale của Scanner không |
| **nextInt()** | int | **Có, nếu thành công** | Chuyển token kế tiếp thành số nguyên int |
| **hasNextDouble()** | boolean | **Không** | Token kế tiếp chuyển được thành double theo quy tắc tương ứng không |
| **nextDouble()** | double | **Có, nếu thành công** | Chuyển token kế tiếp thành double |

**hasNext() không phải là hasNextInt().** Khi token tiếp theo là **abc**, **hasNext() == true** nhưng **hasNextInt() == false**. Khi token là **3.5**, **hasNext()** vẫn là true, trong khi **hasNextInt()** là false dù **hasNextDouble()** có thể true với locale cho phép dấu chấm thập phân.

**hasNextInt() không lấy token**: hai lần gọi liên tiếp **hasNextInt()** sẽ kiểm tra cùng một token nếu chưa có thao tác khác tiêu thụ nó. Khi **nextInt()** chuyển đổi thành công, token mới được tiêu thụ và vị trí Scanner tiến lên.

Chú ý **hasNext() / hasNextInt()** có thể **chặn (block)** để chờ dữ liệu từ nguồn tương tác hoặc mạng. Một lần hasNext() trả true cũng không phải cam kết tuyệt đối lần next() tiếp theo sẽ không chặn, theo hợp đồng API. Không nên gọi chúng như thao tác bất đồng bộ, tức thời.

## 3. InputMismatchException là gì? Khi nào xảy ra?

**java.util.InputMismatchException** là một **unchecked exception** (kế thừa **NoSuchElementException**). Nó xảy ra khi token đang có **không khớp kiểu hoặc phạm vi giá trị** mà phương thức **nextXxx()** yêu cầu.

Ví dụ với **nextInt()**:

| Token kế tiếp | nextInt() (hệ thập phân) | Giải thích |
| --- | --- | --- |
| **42** | 42 | Hợp lệ |
| **-7** | -7 | Hợp lệ |
| **abc** | InputMismatchException | Không biểu diễn số nguyên |
| **3.14** | InputMismatchException | Không biểu diễn int |
| **2147483648** | InputMismatchException | Lớn hơn **Integer.MAX_VALUE = 2147483647** |
| **-2147483649** | InputMismatchException | Nhỏ hơn **Integer.MIN_VALUE = -2147483648** |
| Không còn token | NoSuchElementException | EOF/hết token, khác với sai kiểu |

Quy tắc nhận diện số cũng bị ảnh hưởng bởi **locale** và **radix**. Đừng mặc định mọi ký hiệu dấu thập phân/nhóm chữ số đều được diễn giải giống nhau trong mọi môi trường. Những ví dụ dưới đây dùng token ASCII đơn giản và đặt locale tường minh ở chỗ cần thiết.

### 3.1. Token gây lỗi vẫn còn nguyên để xử lý

Hãy hình dung:

~~~text
Scanner đang ở token "abc".
nextInt() → InputMismatchException.
Scanner vẫn ở token "abc".
nextInt() lần nữa → InputMismatchException lần nữa.
next() → "abc"; tiêu thụ token sai.
nextInt() tiếp theo → thử token đứng sau "abc".
~~~

Theo tài liệu Java, khi Scanner ném **InputMismatchException**, Scanner **không bỏ qua token** gây lỗi, để ứng dụng còn có thể đọc hoặc bỏ qua bằng phương thức khác. Đây là lý do phổ biến khiến vòng lặp **while (scanner.hasNext()) { scanner.nextInt(); }** bị dừng bởi exception ngay tại dữ liệu sai; nếu catch nhưng không tiến vị trí, vòng lặp có thể mắc kẹt.

**Không dùng hasNextInt() đơn độc làm điều kiện vòng lặp khi muốn tiếp tục sau token lỗi**:

~~~java
while (scanner.hasNextInt()) {
    System.out.println(scanner.nextInt());
}
~~~

Mảnh code trên **hợp lệ** nếu chỉ chấp nhận *dãy int liên tiếp đến token không phải int đầu tiên*. Nhưng khi dữ liệu là **1 bad 2**, vòng lặp chỉ đọc **1**, dừng tại **bad**, và không bao giờ tới **2**. Muốn **bỏ token lỗi rồi tiếp tục**, dùng vòng lặp **hasNext()** và nhánh xử lý token sai.

## 4. Chiến lược khuyến nghị: hasNext() + hasNextInt() + next()

Với một luồng token mà mục tiêu là **lọc số nguyên hợp lệ**, cách dễ đọc là:

1. Dùng **hasNext()** để biết còn token.
2. Dùng **hasNextInt()** để kiểm tra kiểu, **không làm tiến vị trí**.
3. Nếu hợp lệ, dùng **nextInt()** để tiêu thụ và sử dụng số.
4. Nếu không hợp lệ, dùng **next()** để **tiêu thụ đúng một token** và ghi nhận lỗi/bỏ qua.
5. Lặp đến khi hết token.

Ví dụ Java 17+ chạy độc lập. Lưu thành **ScannerTokenDemo.java**:

~~~java
import java.util.Locale;
import java.util.Scanner;

public class ScannerTokenDemo {
    public static void main(String[] args) {
        String data = "12 abc 3.5 -7 2147483648 25";

        try (Scanner scanner = new Scanner(data).useLocale(Locale.US)) {
            while (scanner.hasNext()) {
                if (scanner.hasNextInt()) {
                    int number = scanner.nextInt();
                    System.out.println("INT: " + number);
                } else {
                    String invalid = scanner.next();
                    System.out.println("INVALID: " + invalid);
                }
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ScannerTokenDemo.java
java ScannerTokenDemo
~~~

Kết quả chính xác:

~~~text
INT: 12
INVALID: abc
INVALID: 3.5
INT: -7
INVALID: 2147483648
INT: 25
~~~

**12**, **-7** và **25** đọc thành công. **abc** không là số, **3.5** là số thập phân chứ không phải int, **2147483648** vượt giới hạn int. Mỗi lần gặp token sai, **next()** tiêu thụ nó; vì thế vòng lặp **luôn có tiến triển** và vẫn đọc được **25** sau token lỗi.

**Locale.US** ở đây giúp làm rõ môi trường phân tích số. **nextInt()** trả về **int** thật; không cần dùng **Integer.parseInt(scanner.next())** một lần nữa sau khi đã kiểm tra thành công, trừ khi ứng dụng cố ý tự kiểm soát quy tắc kiểm tra theo String.

## 5. Chiến lược khác: try/catch InputMismatchException

Khi code cố tình gọi **nextInt()** trực tiếp, có thể dùng try/catch để xử lý sai kiểu. Điểm bắt buộc là nhánh **catch phải đảm bảo tiến vị trí** hoặc quyết định dừng, tránh gặp lại token lỗi.

Ví dụ Java 17+ chạy độc lập, lưu thành **ScannerMismatchDemo.java**:

~~~java
import java.util.InputMismatchException;
import java.util.Scanner;

public class ScannerMismatchDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("8 oops 9")) {
            while (scanner.hasNext()) {
                try {
                    int number = scanner.nextInt();
                    System.out.println("number=" + number);
                } catch (InputMismatchException ex) {
                    // nextInt() thất bại không tiêu thụ token.
                    String bad = scanner.next();
                    System.out.println("skipped=" + bad);
                }
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac ScannerMismatchDemo.java
java ScannerMismatchDemo
~~~

Kết quả:

~~~text
number=8
skipped=oops
number=9
~~~

Nếu bỏ dòng **scanner.next()** trong **catch**, vòng lặp sẽ bắt gặp “oops” mãi; **scanner.hasNext()** vẫn là true và **scanner.nextInt()** tiếp tục ném cùng exception. Do vậy khi có thể kiểm tra trước bằng **hasNextInt()**, cách ở mục 4 thường rõ ràng hơn và tránh dùng exception cho luồng xử lý dữ liệu sai vốn được dự kiến trước.

**Không catch Exception quá rộng chỉ để bỏ qua mọi lỗi**. Khi chương trình đang yêu cầu một cấu trúc dữ liệu nghiêm ngặt, gặp token sai có thể phải báo lỗi và dừng, thay vì im lặng loại bỏ dữ liệu.

## 6. InputMismatchException khác NoSuchElementException và IllegalStateException

Các tình huống thường gặp:

| Trạng thái Scanner | Thao tác | Kết quả |
| --- | --- | --- |
| Token hiện tại là **abc** | **hasNext()** | true |
| Token hiện tại là **abc** | **hasNextInt()** | false |
| Token hiện tại là **abc** | **nextInt()** | **InputMismatchException**, token chưa bị tiêu thụ |
| Đã hết token | **hasNext() / hasNextInt()** | false |
| Đã hết token | **next() / nextInt()** | **NoSuchElementException** |
| Scanner đã **close()** | **hasNext() / nextInt()** | **IllegalStateException** |

**InputMismatchException kế thừa NoSuchElementException**, vì vậy nếu cần bắt hai loại riêng thì **bắt InputMismatchException trước**, rồi mới tới **NoSuchElementException**. Nếu bắt lớp cha trước, catch lớp con phía sau trở thành unreachable và Java từ chối biên dịch.

Ví dụ đúng về thứ tự catch:

~~~java
try {
    int value = scanner.nextInt();
    System.out.println(value);
} catch (java.util.InputMismatchException ex) {
    System.out.println("Sai định dạng int");
} catch (java.util.NoSuchElementException ex) {
    System.out.println("Không còn token");
}
~~~

Đây là **mảnh minh họa**, giả định **scanner** đã được tạo và còn mở. Trong ứng dụng xử lý nhiều token, nếu bắt InputMismatchException để tiếp tục thì vẫn phải **tiêu thụ token lỗi** bằng **next()** hoặc chọn cách kết thúc. Mảnh catch này chỉ minh họa phân biệt ngoại lệ và thứ tự catch.

## 7. Token và dòng khác nhau: hasNext() không phải hasNextLine()

Một lỗi phổ biến là nghĩ **Scanner** luôn xử lý nguyên dòng. Thực ra:

- **hasNext() / next()** làm việc theo **token**, mặc định cách nhau bởi khoảng trắng, kể cả dấu xuống dòng.
- **hasNextLine() / nextLine()** làm việc theo **dòng**; **nextLine()** lấy phần còn lại của dòng hiện tại, *không kèm ký tự kết thúc dòng*, rồi chuyển qua dòng sau.
- Một dòng trống có thể được **nextLine()** trả về là String rỗng. **hasNext()** có thể là false khi nguồn chỉ còn khoảng trắng hoặc dòng trống.
- **nextInt()** đọc token số nhưng thường **để lại dấu xuống dòng**, nên gọi **nextLine()** ngay sau đó có thể lấy String rỗng vì chỉ đọc phần còn lại của cùng dòng.

Ví dụ Java 17+ chạy độc lập, lưu thành **ScannerLineDemo.java**:

~~~java
import java.util.Scanner;

public class ScannerLineDemo {
    public static void main(String[] args) {
        String data = "42\nhello world\n\nZ";

        try (Scanner scanner = new Scanner(data)) {
            int number = scanner.nextInt();
            String rest = scanner.nextLine();
            String line1 = scanner.nextLine();
            String line2 = scanner.nextLine();
            String line3 = scanner.nextLine();

            System.out.println("number=" + number);
            System.out.println("rest=[" + rest + "]");
            System.out.println("line1=[" + line1 + "]");
            System.out.println("line2=[" + line2 + "]");
            System.out.println("line3=[" + line3 + "]");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ScannerLineDemo.java
java ScannerLineDemo
~~~

Kết quả:

~~~text
number=42
rest=[]
line1=[hello world]
line2=[]
line3=[Z]
~~~

Sau **nextInt()**, Scanner đang ở ngay sau token **42** nhưng vẫn trong dòng đầu; **nextLine()** đầu tiên đọc phần dư rỗng rồi tiêu thụ dấu xuống dòng. **nextLine()** tiếp theo mới lấy “hello world”. Dòng trống tiếp theo thành **line2=[]**.

Nếu cấu trúc đầu vào là **mỗi dòng một bản ghi**, có thể dùng **while (scanner.hasNextLine())**, lấy **line = scanner.nextLine()**, sau đó tự xác thực token trong chính dòng đó. Phân tích theo dòng cho phép báo lỗi đúng số dòng và tránh vô ý tiêu thụ sang bản ghi khác. Còn nếu cấu trúc dữ liệu chỉ là **chuỗi token bất kể dòng**, dùng hasNext()/next() sẽ tự nhiên hơn.

## 8. Xử lý token lỗi: bỏ một token hay bỏ cả dòng?

Giả sử đầu vào:

~~~text
10 bad 20
30 40
~~~

**Bỏ đúng một token:** khi “bad” sai, gọi **scanner.next()**; sau đó chương trình vẫn đọc được **20**, **30**, **40**. Hợp khi token độc lập và mọi số hợp lệ đều có giá trị.

**Bỏ phần còn lại của dòng:** khi một bản ghi phải có cấu trúc cố định, gặp “bad” có thể cần gọi **scanner.nextLine()** để bỏ phần dư của dòng hiện tại. Khi ấy **20** cũng bị bỏ cùng dòng đầu; dòng sau vẫn có **30 40**. Không nên dùng chiến lược này nếu muốn giữ số 20.

**Dừng với thông báo:** khi mỗi dòng bắt buộc thỏa hợp đồng dữ liệu (ví dụ có đúng 3 trường số), tốt hơn là báo lỗi rõ dòng và từ chối bản ghi thay vì giả vờ dữ liệu vẫn đầy đủ.

**Yêu cầu nhập lại:** với tương tác console, sau khi người dùng nhập token sai, cần loại token sai hoặc dòng hiện tại rồi mới đọc câu trả lời mới; nếu không, lần lặp sau sẽ kiểm tra lại chính token cũ.

Không có một chính sách phục hồi đúng cho mọi ứng dụng. Quy tắc kỹ thuật chung là: **không để nhánh xử lý lỗi lặp lại vô hạn trên token không được tiêu thụ**.

## 9. Delimiter, locale, radix và lý do một token bị coi là không hợp lệ

### 9.1. Delimiter mặc định và delimiter tùy chỉnh

Với delimiter mặc định, đầu vào **"10 20"** có hai token. Nhưng **"10,20"** là một token vì dấu phẩy không mặc định là dấu phân cách của Scanner. Nếu muốn phân cách theo dấu phẩy, có thể cấu hình biểu thức chính quy:

~~~java
Scanner scanner = new Scanner("10,abc,20")
        .useDelimiter("\\s*,\\s*");
~~~

Mảnh code này giả định **import java.util.Scanner**; khi dùng thực tế hãy đóng Scanner nếu thuộc sở hữu của mình. Delimiter trên khớp dấu phẩy với khoảng trắng tùy chọn ở hai bên, phù hợp với ví dụ đơn giản. Nó **không phải bộ phân tích CSV đầy đủ**: CSV có dấu ngoặc kép và dấu phẩy bên trong trường thì cần parser CSV đúng chuẩn.

Nếu delimiter không đúng với định dạng dữ liệu, **hasNextInt()** có thể trả false chỉ vì token bị ghép sai, dù từng phần riêng lẻ đều là số.

### 9.2. Locale ảnh hưởng cú pháp số

**Scanner.useLocale(Locale.US)** giúp chọn quy tắc dấu phân cách hàng nghìn, dấu thập phân và hình thức số phù hợp locale. Ví dụ **1.5** thường là số thập phân hợp lệ ở Locale.US; tại locale khác, dấu thập phân có thể là **dấu phẩy**. Khi nhập/đọc số thập phân, đặt locale rõ ràng để tránh việc code chạy khác giữa môi trường phát triển và production.

**hasNextInt()** không “cắt lấy phần nguyên” của số thập phân. Token **3.5** không phải **int** trong cấu hình cơ bản; nếu yêu cầu số thực, dùng **hasNextDouble() / nextDouble()** hoặc quy tắc riêng.

### 9.3. Radix ảnh hưởng cách đọc số nguyên

Mặc định số nguyên được hiểu ở hệ **10**, nhưng có thể dùng **scanner.useRadix(16)** hoặc **nextInt(16)** để đọc hệ 16. Ví dụ:

~~~java
try (Scanner scanner = new Scanner("FF")) {
    scanner.useRadix(16);
    System.out.println(scanner.hasNextInt());
    System.out.println(scanner.nextInt());
}
~~~

Mảnh code này cần import **java.util.Scanner**; kết quả lần lượt là **true** và **255**. Nếu không đặt hệ 16, token **FF** không phải số nguyên thập phân. Vì vậy **InputMismatchException** còn có thể biểu thị *sai quy tắc diễn giải hiện hành*, không chỉ biểu thị chữ cái trong token.

Với token số quá lớn so với **int**, có thể lựa chọn **nextLong()** hoặc **nextBigInteger()** nếu hợp đồng thực sự cho phép miền giá trị lớn hơn; không nên đổi loại tùy tiện khi chương trình chỉ chấp nhận int.

## 10. Kiểm tra dữ liệu chặt chẽ so với lọc token tùy ý

Mẫu **hasNext() + hasNextInt() + next()** phù hợp khi muốn **lọc token hợp lệ** từ một chuỗi dữ liệu có thể lẫn ký hiệu sai. Tuy nhiên, nếu ứng dụng đọc giao thức có cấu trúc, cần yêu cầu **đúng thứ tự, đúng số trường, đúng kiểu và không có trường thừa**.

Ví dụ một bản ghi phải gồm chính xác **hai số nguyên** như:

~~~text
12 34
~~~

Không đủ nếu chỉ lặp để tìm hai token int bất kỳ, bởi đầu vào **12 wrong 34** sẽ bị bỏ “wrong” rồi vẫn được chấp nhận. Một cách xử lý chặt hơn là đọc cả dòng, tách đúng các trường mong đợi, xác nhận **mọi token** và từ chối dòng có dữ liệu thừa/không hợp lệ.

Có thể dùng một Scanner thứ hai trên String của mỗi dòng:

~~~java
String line = scanner.nextLine();
try (Scanner row = new Scanner(line)) {
    if (!row.hasNextInt()) {
        throw new IllegalArgumentException("Thiếu hoặc sai số thứ nhất");
    }
    int first = row.nextInt();

    if (!row.hasNextInt()) {
        throw new IllegalArgumentException("Thiếu hoặc sai số thứ hai");
    }
    int second = row.nextInt();

    if (row.hasNext()) {
        throw new IllegalArgumentException("Dữ liệu thừa trong bản ghi");
    }
    System.out.println(first + second);
}
~~~

Đây là **mảnh code minh họa**, giả định **scanner** đang mở để đọc các dòng đầu vào và đã import **java.util.Scanner**. Nếu dùng mỗi dòng một bản ghi, hãy kiểm tra **scanner.hasNextLine()** trước khi gọi **nextLine()** và đưa try/catch quanh từng dòng theo chính sách xử lý lỗi. Mảnh này minh họa việc **không âm thầm bỏ token sai** trong bản ghi bắt buộc đúng định dạng.

## 11. Những trường hợp biên, lỗi nguồn và tài nguyên

### 11.1. EOF và Scanner đọc từ console

Một **Scanner(System.in)** thường lấy dữ liệu do người dùng nhập. Nếu không có token và nguồn console vẫn mở, **hasNext()** có thể **đợi người dùng nhập**; false thường chỉ xuất hiện khi nguồn đạt EOF. Tại console, kết thúc nhập phụ thuộc hệ điều hành/terminal, ví dụ tổ hợp phím báo EOF. Không nên hiểu “chưa gõ gì” là hết dữ liệu ngay.

Khi sở hữu Scanner đọc file/String, dùng **try-with-resources**. Nhưng **đóng Scanner(System.in)** sẽ đóng cả nguồn **System.in** do Scanner đang bao bọc; tránh đóng khi phần còn lại của ứng dụng còn cần dùng standard input.

### 11.2. IOException có thể bị Scanner coi là hết đầu vào

Theo hợp đồng Scanner, khi nguồn **Readable** bên dưới ném **IOException** trong quá trình đọc, Scanner **giả định đã đến cuối input**. Có thể lấy IOException gần nhất qua **scanner.ioException()**. Trong ứng dụng cần phân biệt EOF bình thường với lỗi đọc file/network, hãy kiểm tra ioException khi kết thúc thay vì khẳng định mọi **hasNext() == false** đều là kết thúc thành công.

Ví dụ kiểm tra sau vòng lặp:

~~~java
java.io.IOException readFailure = scanner.ioException();
if (readFailure != null) {
    throw new java.io.UncheckedIOException(readFailure);
}
~~~

Mảnh code này giả định **scanner** còn mở. Nó minh họa cách không bỏ qua lỗi I/O khi chính sách hệ thống cần báo lỗi, dù kiểu dữ liệu đầu vào thường được Scanner tiêu thụ như token.

### 11.3. Scanner và hiệu năng

Scanner tiện lợi vì kết hợp delimiter regex, locale và parse kiểu, nhưng có overhead lớn hơn đọc theo byte/char rồi tự parse trong một số workload cực lớn. Với dữ liệu khối lượng cao và quy tắc đơn giản, **BufferedReader** cùng với xử lý String hoặc parser chuyên dụng có thể phù hợp hơn sau khi đo. Không đổi cách đọc chỉ vì giả định Scanner luôn chậm: hãy đo trên dữ liệu thực.

**Scanner không an toàn khi dùng đồng thời từ nhiều thread nếu thiếu đồng bộ bên ngoài.** Nếu chia sẻ một Scanner giữa các tác vụ, mỗi tác vụ có thể tiêu thụ token của tác vụ khác khiến hasNext/next không còn là một thao tác logic nguyên tử.

## 12. Các lỗi thường gặp

1. **Dùng hasNext() rồi tin rằng nextInt() luôn hợp lệ.** hasNext chỉ kiểm tra token tồn tại. Cần **hasNextInt()** nếu mong int.
2. **Dùng while (hasNextInt()) khi cần bỏ qua token không hợp lệ.** Vòng lặp dừng ở token sai đầu tiên, bỏ lỡ token hợp lệ phía sau; dùng **while (hasNext())** và nhánh xử lý.
3. **Catch InputMismatchException rồi gọi lại nextInt() ngay.** Token sai vẫn ở vị trí cũ; cần **next()** để bỏ nó hoặc đổi chiến lược.
4. **Nhầm sai định dạng với EOF.** nextInt trên token sai ném InputMismatchException; khi hết token, nó ném NoSuchElementException.
5. **Bỏ qua số vượt miền int.** “2147483648” có chữ số đúng định dạng nhưng không fit int. Xác định miền giá trị và chọn kiểu phù hợp.
6. **Trộn nextInt() và nextLine() mà không xét phần còn lại của dòng.** nextLine ngay sau nextInt có thể trả String rỗng; thiết kế rõ cấu trúc dòng/token.
7. **Dùng nextLine() để bỏ lỗi nhưng lại muốn giữ các token còn lại trên cùng dòng.** nextLine bỏ qua phần dư của dòng hiện tại; nếu chỉ muốn bỏ một token, dùng next().
8. **Mặc định dấu phẩy luôn là delimiter.** Scanner mặc định tách theo whitespace; hãy khai báo delimiter hoặc dùng parser định dạng chuyên biệt.
9. **Bỏ qua locale/radix.** Các phương thức số phụ thuộc quy tắc diễn giải; đặt locale và radix phù hợp cho đầu vào ổn định.
10. **Âm thầm bỏ token sai trong giao thức nghiêm ngặt.** Với bản ghi cần tính toàn vẹn, phải báo lỗi hoặc từ chối thay vì nối những token hợp lệ rời rạc.
11. **Bỏ qua IOException nguồn.** Scanner có thể coi I/O lỗi là EOF; kiểm tra **ioException()** khi cần phân biệt.
12. **Đóng Scanner(System.in) khi phần khác còn cần đọc.** Đóng wrapper có thể đóng luôn nguồn bên dưới.

## 13. Tự kiểm tra và đáp án

**Câu 1:** Scanner đang ở token **"abc"**. Kết quả của **hasNext()**, **hasNextInt()**, **nextInt()** lần lượt là gì?  
**Đáp:** **true**, **false**, rồi **InputMismatchException**. Token “abc” vẫn còn sau exception.

**Câu 2:** Vòng lặp **while (scanner.hasNextInt())** trên đầu vào **"1 bad 2"** đọc được những số nào?  
**Đáp:** Chỉ **1**. Nó dừng ở “bad”; muốn tiếp tục, phải xử lý token lỗi bằng **next()** hoặc phương pháp khác.

**Câu 3:** Vì sao **2147483648** không đọc được bằng **nextInt()**?  
**Đáp:** Vượt **Integer.MAX_VALUE (2147483647)**. Có thể dùng kiểu số lớn hơn nếu hợp đồng cho phép, nhưng không được âm thầm bỏ sai lệch phạm vi.

**Câu 4:** Gọi **nextInt()** sau khi nguồn đã hết token gây lỗi gì?  
**Đáp:** **NoSuchElementException**, không phải InputMismatchException.

**Câu 5:** Nếu cần bỏ token sai **nhưng giữ token phía sau trên cùng dòng**, nên gọi **next()** hay **nextLine()**?  
**Đáp:** **next()** chỉ tiêu thụ token sai; **nextLine()** có thể bỏ cả phần còn lại của dòng.

**Câu 6:** Vì sao **nextLine()** ngay sau **nextInt()** thường trả về String rỗng?  
**Đáp:** nextInt chỉ tiêu thụ token số, để lại ký tự xuống dòng; nextLine đọc phần còn lại của dòng hiện tại, có thể không còn ký tự nào.

**Câu 7:** Token **FF** có thể được **hasNextInt()** chấp nhận không?  
**Đáp:** Có, nếu Scanner đang dùng hệ 16 (**useRadix(16)**). Trong hệ thập phân mặc định, nó không phải int hợp lệ.

## 14. Kết luận

**hasNext()** xác định còn token hay không; **hasNextInt()** xác định token kế tiếp có đọc thành **int** được hay không; **nextInt()** tiêu thụ và chuyển đổi token nếu thành công. Khi token không đúng kiểu hoặc vượt phạm vi, **nextInt() ném InputMismatchException và giữ nguyên token sai**. Khi không còn token, **nextInt() ném NoSuchElementException**.

Để **lọc và tiếp tục đọc sau token sai**, dùng **while (hasNext())**, trong vòng lặp chọn **hasNextInt() → nextInt()** hoặc **next() để bỏ token lỗi**. Với dữ liệu có cấu trúc, xác thực đầy đủ từng dòng/bản ghi và báo lỗi theo hợp đồng thay vì lọc bỏ dữ liệu tùy tiện.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — Scanner](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html): delimiter, hasNext/next, hasNextInt/nextInt, token lỗi không bị tiêu thụ, ioException, locale, radix, blocking.
- [Oracle Java SE 21 — InputMismatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/InputMismatchException.html): lớp ngoại lệ và quan hệ kế thừa.
- [Oracle Java SE 21 — NoSuchElementException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NoSuchElementException.html): ngoại lệ khi không còn phần tử/token.
