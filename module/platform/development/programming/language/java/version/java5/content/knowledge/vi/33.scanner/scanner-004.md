# Delimiter bằng biểu thức chính quy trong Scanner

## 1. Delimiter giải quyết vấn đề gì?

Khi đọc chuỗi «A;B;C», ta muốn nhận lần lượt ba đơn vị dữ liệu A, B, C. Một đơn vị mà Scanner trả về qua **next()** gọi là **token**. **Dấu phân cách (delimiter)** xác định phần văn bản ngăn cách các token và được bỏ qua khi đọc token.

Đối số của **useDelimiter(...)** là **biểu thức chính quy (regex) mô tả phần cần phân cách**, không phải biểu thức mô tả dữ liệu cần nhận. Muốn đọc các số cách nhau bởi dấu chấm phẩy, delimiter phải mô tả dấu chấm phẩy; việc kiểm tra và chuyển token thành số thuộc về **hasNextInt() / nextInt()**.

| Thành phần | Trách nhiệm |
| --- | --- |
| Nguồn đầu vào | Cung cấp văn bản, chẳng hạn String hoặc tệp |
| Delimiter | Xác định ranh giới và phần ngăn cách token |
| next() | Đọc token dưới dạng String |
| nextInt(), nextDouble() | Đọc và chuyển token sang kiểu số |
| Locale | Quy định cách diễn giải số theo vùng, chẳng hạn dấu thập phân |

Bài này dùng API đang áp dụng trong Java hiện đại. Chương trình hoàn chỉnh dùng cú pháp và API có trên Java 17 trở lên.

## 2. Cấu hình delimiter và hiểu quá trình đọc

Đoạn minh họa sau đặt bên trong một phương thức, với import java.util.Scanner:

```java
try (Scanner scanner = new Scanner("A;B;C")) {
    scanner.useDelimiter(";");
    while (scanner.hasNext()) {
        System.out.println(scanner.next());
    }
}
```

Khi cần token tiếp theo, Scanner bỏ qua delimiter tại vị trí đang đọc, xác định token đến delimiter kế tiếp hoặc hết dữ liệu, rồi trả token. Trong ví dụ, ba lần println lần lượt in A, B, C, mỗi giá trị một dòng. **hasNext()** kiểm tra khả năng đọc token nhưng không tiến qua token; **next()** đọc và tiến vị trí.

Delimiter mặc định tương ứng với regex **\p{javaWhitespace}+**, nghĩa là một hay nhiều ký tự thỏa Character.isWhitespace. Vì vậy dấu cách, tab và xuống dòng thông thường đều phân cách token. Gọi useDelimiter **thay thế** cấu hình mặc định. Sau useDelimiter(";"), dấu cách không tự động tiếp tục phân cách token.

Có thể truyền chuỗi regex hoặc Pattern đã biên dịch:

```java
scanner.useDelimiter("\\s*;\\s*");
// Hoặc, với import java.util.regex.Pattern:
scanner.useDelimiter(Pattern.compile("\\s*;\\s*"));
```

Đây là hai lựa chọn tương đương về ý nghĩa; không cần gọi liên tiếp. Pattern hữu ích khi nhiều Scanner dùng chung biểu thức. Thay delimiter chỉ đổi cách đọc từ vị trí hiện tại, không quay lại đầu nguồn. Có thể xem cấu hình qua scanner.delimiter().

Cơ chế của các phương thức đọc token được mô tả trong [Java SE 21 Scanner API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html).

## 3. Hai lớp cú pháp: chuỗi Java và regex

Trong mã nguồn, chuỗi phải đi qua hai lần diễn giải:

```text
Chuỗi trong mã Java          Regex nhận được           Ý nghĩa
"\\s+"                      \s+                       Một hay nhiều whitespace
"\\."                       \.                        Dấu chấm thật
"[.]"                       [.]                       Dấu chấm thật
"\\|"                       \|                        Dấu gạch đứng thật
"\\s*;\\s*"                 \s*;\s*                   Dấu ; và whitespace bao quanh
```

Dấu gạch chéo ngược cần được bảo vệ ở lớp chuỗi Java. Để regex nhận \s, trong chuỗi Java phải viết "\\s".

Trong Java 17+, chuỗi Java "\s+" vẫn hợp lệ nhưng **\s ở lớp Java trở thành một dấu cách**. Regex nhận được khi ấy là " +", chỉ khớp một hay nhiều dấu cách, không phải lớp whitespace của regex. Đây là lỗi dễ bỏ sót vì chương trình vẫn biên dịch.

Dấu chấm trong regex thường khớp một ký tự, tùy cờ và ký tự xuống dòng. Dấu gạch đứng là phép lựa chọn. Dấu cộng là phép lặp. Không truyền các dấu này như thể chúng luôn có nghĩa nguyên văn.

Khi dấu phân cách lấy từ cấu hình dưới dạng văn bản nguyên nghĩa, dùng Pattern.quote:

```java
String separator = "|";
scanner.useDelimiter(Pattern.quote(separator));
```

Cách này cũng dùng được với dấu phân cách nhiều ký tự như "||" hoặc "[END]". Cần từ chối cấu hình rỗng nếu định dạng yêu cầu dấu phân cách thật. Ngược lại, đừng quote cấu hình chủ đích là regex: các ký hiệu regex sẽ bị biến thành ký tự thường.

Quy tắc escape, lớp ký tự và cờ Unicode được định nghĩa trong [Java SE 21 Pattern API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html).

## 4. Chọn regex theo ý nghĩa của dữ liệu

### 4.1. Một dấu cố định và khoảng trắng bao quanh

Dữ liệu «A;B;C» chỉ cần delimiter ";". Dữ liệu «A B;C D» với cùng delimiter tạo hai token «A B» và «C D», giữ dấu cách bên trong mỗi trường.

Delimiter không tự gọi trim(). Dữ liệu « A ; B » với delimiter ";" vẫn chứa dấu cách trong các token. Nếu chúng thuộc dữ liệu có ý nghĩa, phải giữ; nếu chỉ là phần trang trí của định dạng, mới loại theo một quy tắc rõ ràng.

Regex "\\s*;\\s*" xử lý cả «A;B», «A ; B» và «A;   B». Hai phần \s* có thể dài bằng 0, nhưng **toàn bộ delimiter vẫn phải chứa dấu ;**, nên không khớp chuỗi rỗng.

Regex này không tự loại khoảng trắng ở đầu nguồn trước token đầu tiên hoặc ở cuối nguồn sau token cuối cùng khi tại đó không có dấu chấm phẩy. Nó cũng có thể ăn ký tự xuống dòng cạnh dấu phân cách. Nếu bản ghi có cấu trúc theo dòng và chỉ cho phép khoảng trắng ngang quanh dấu chấm phẩy, cân nhắc "\\h*;\\h*".

### 4.2. Nhiều loại dấu phân cách

Nếu mọi dấu phẩy, chấm phẩy và whitespace đều tương đương trong định dạng, có thể dùng:

```java
scanner.useDelimiter("[,;\\s]+");
```

Lớp ký tự quy định loại dấu phân cách; dấu cộng gom một dãy liên tiếp thành một delimiter. Đổi lại, «A,,B» thành hai token A và B; thông tin trường rỗng ở giữa bị mất. Regex này cũng tách họ tên có dấu cách, nên không phù hợp nếu cần giữ họ tên như một trường.

Nếu delimiter là các chuỗi nhiều ký tự, dùng nhánh regex thay vì lớp ký tự:

```java
scanner.useDelimiter("(?:END|STOP)");
```

Đoạn minh họa này tách ở chuỗi END hoặc STOP. Lớp ký tự "[END]" chỉ khớp **một ký tự thuộc tập E, N, D**, không phải cả chuỗi END.

### 4.3. Whitespace và Unicode

Lớp \s ở chế độ regex mặc định không bao phủ mọi ký tự Unicode trông giống dấu cách. Nếu định dạng yêu cầu lớp whitespace Unicode của regex, có thể bật Pattern.UNICODE_CHARACTER_CLASS khi tạo Pattern. Nếu muốn giữ đúng tiêu chí mặc định của Scanner, dùng \p{javaWhitespace}+.

Hai tiêu chí không hoàn toàn giống nhau. Hãy chọn theo hợp đồng dữ liệu, đặc biệt với nội dung sao chép từ trang web có dấu cách không ngắt dòng, thay vì dựa vào hình thức hiển thị.

## 5. Trường rỗng: dấu phẩy đơn khác dãy dấu phẩy

Với đầu vào «A,,B,»:

- Delimiter "," tạo token A, chuỗi rỗng, B. Hai dấu phẩy ở giữa để lại một token rỗng.
- Delimiter ",+" gom hai dấu phẩy ở giữa, chỉ còn token A và B.
- Trong cả hai trường hợp trên, dấu phẩy cuối nguồn không tạo thêm token rỗng.

Ở đầu nguồn, «,A» với delimiter "," bắt đầu bằng token A vì delimiter đầu tiên được bỏ qua. Nhưng «,,A» cho token rỗng rồi đến A. Vì vậy không coi Scanner là công cụ bảo toàn mọi trường rỗng theo vị trí cột.

Nếu đã có một dòng đơn giản trong String và cần giữ cả trường rỗng cuối dòng, có thể dùng line.split(regex, -1), sau đó kiểm tra số trường. Cách này vẫn chỉ tách chuỗi đơn giản, chưa xử lý quy tắc CSV có dấu ngoặc kép.

## 6. Chương trình hoàn chỉnh và kết quả

Lưu tệp **DelimiterDemo.java**. Chương trình dùng String làm nguồn, không phụ thuộc thao tác nhập bàn phím.

```java
import java.util.Locale;
import java.util.Scanner;
import java.util.regex.Pattern;

public class DelimiterDemo {
    private static void show(String label, String input, String delimiter) {
        System.out.print(label + ":");
        try (Scanner scanner = new Scanner(input)) {
            if (delimiter != null) {
                scanner.useDelimiter(delimiter);
            }
            while (scanner.hasNext()) {
                System.out.print("[" + scanner.next() + "]");
            }
        }
        System.out.println();
    }

    public static void main(String[] args) {
        show("default", "A \t B\nC", null);
        show("semicolon", "A ; B;C", "\\s*;\\s*");
        show("one-comma", "A,,B,", ",");
        show("comma-run", "A,,B,", ",+");
        show("leading", ",,A", ",");
        show("literal-pipe", "A|B|C", Pattern.quote("|"));
        show("mixed", "A, B;;C\nD", "[,;\\s]+");
        show("spaces-kept", "A B;C D", ";");

        try (Scanner scanner = new Scanner("12; 34;56")) {
            scanner.useDelimiter("\\s*;\\s*");
            int sum = 0;
            while (scanner.hasNextInt()) {
                sum += scanner.nextInt();
            }
            System.out.println("sum=" + sum);
        }

        try (Scanner scanner = new Scanner("1,5;2,5")) {
            scanner.useDelimiter(";");
            scanner.useLocale(Locale.GERMANY);
            double sum = scanner.nextDouble() + scanner.nextDouble();
            System.out.println("decimal-sum=" + sum);
        }

        try (Scanner scanner = new Scanner("A;B\nC;D")) {
            scanner.useDelimiter(";");
            System.out.println("first=[" + scanner.next() + "]");
            System.out.println("rest-of-line=[" + scanner.nextLine() + "]");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 DelimiterDemo.java
java DelimiterDemo
```

Kết quả chuẩn:

```text
default:[A][B][C]
semicolon:[A][B][C]
one-comma:[A][][B]
comma-run:[A][B]
leading:[][A]
literal-pipe:[A][B][C]
mixed:[A][B][C][D]
spaces-kept:[A B][C D]
sum=102
decimal-sum=4.0
first=[A]
rest-of-line=[;B]
```

Dấu ngoặc vuông do chương trình in thêm để thấy ranh giới token. Cặp [] thể hiện token rỗng, không phải token chứa hai dấu ngoặc.

Ví dụ cộng số dùng đầu vào đã biết hợp lệ. Trong chương trình nhận dữ liệu bên ngoài, vòng lặp while (hasNextInt()) dừng cả khi hết nguồn lẫn khi gặp token không phải số. Muốn phân biệt, kiểm tra hasNext() và báo lỗi nếu token tiếp theo không thỏa hasNextInt(); không coi việc vòng lặp dừng là bằng chứng toàn bộ nguồn hợp lệ.

## 7. Delimiter, số và dòng là ba vấn đề khác nhau

### 7.1. Đổi delimiter không đổi cách biểu diễn số

Trong «1,5;2,5», dấu chấm phẩy phân cách hai số; dấu phẩy thuộc phần thập phân theo Locale.GERMANY. Chọn đúng delimiter và locale thì tổng là 4.0.

Nếu đưa dấu phẩy vào delimiter, hai số thập phân bị cắt sai trước bước chuyển kiểu. Cần biết một ký tự là dấu phân cách trường hay thành phần của giá trị trước khi chọn regex.

### 7.2. nextLine() không đọc theo delimiter tùy chỉnh

Hai dòng cuối trong kết quả minh họa:

1. next() đọc A từ nguồn «A;B\nC;D».
2. Vị trí đọc nằm ngay trước dấu chấm phẩy.
3. nextLine() trả phần còn lại của dòng là «;B», rồi đi qua ký tự xuống dòng.

nextLine() hoạt động theo dòng. Đổi delimiter sang dấu chấm phẩy không khiến phương thức này trả riêng trường B. Khi bản ghi có ranh giới theo dòng, có thể đọc dòng trước rồi phân tích từng dòng theo định dạng.

### 7.3. Mẫu kiểm tra token không phải delimiter

Trong đoạn minh họa scanner.next("[A-Z]+"), đối số là mẫu mà **toàn bộ token tiếp theo phải thỏa**, không phải một delimiter mới. Với nguồn «A;B» và delimiter mặc định, token vẫn là «A;B», nên mẫu trên không tự tách riêng A.

Các phương thức findInLine, findWithinHorizon và skip có cơ chế riêng; không suy luận rằng mọi phương thức của Scanner đều phân tách token theo cùng một cách.

## 8. Lỗi thường gặp và giới hạn áp dụng

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| Dấu cách còn trong giá trị | Delimiter chỉ là ";" | Giữ nếu có ý nghĩa; hoặc quy định rõ cách xử lý khoảng trắng |
| Token bị cắt gần như từng ký tự | Dùng dấu chấm như ký tự thường trong regex | Escape dấu chấm hoặc dùng Pattern.quote |
| Regex báo lỗi với dấu cộng | Dấu cộng bị diễn giải như phép lặp | Quote nếu cấu hình là dấu nguyên văn |
| Thiếu các trường trống | Gom nhiều delimiter bằng dấu cộng hoặc mong giữ cột cuối rỗng | Chọn cách phân tích có hợp đồng bảo toàn trường rỗng |
| nextDouble() đọc sai | Delimiter xung đột dấu thập phân hoặc locale sai | Xác định riêng ranh giới trường và cách biểu diễn số |
| Nhiều dòng thành một token | Delimiter mới không chứa xuống dòng | Bổ sung quy tắc xuống dòng hoặc đọc theo dòng |
| hasNext() trên console chưa trả về | Nguồn chưa đủ dữ liệu để xác định token hoặc chưa kết thúc | Kiểm tra ranh giới token và cách kết thúc nguồn |

Không chọn "\\s*" chỉ vì muốn bỏ khoảng trắng: mẫu có thể khớp chuỗi rỗng, khiến ranh giới token khác ý định. Chọn "\\s+" khi ý nghĩa là một hay nhiều whitespace, hoặc giữ mặc định khi đã phù hợp.

Regex không hợp lệ có thể gây PatternSyntaxException. Với regex do người dùng cấu hình, cần xử lý lỗi và giới hạn biểu thức phức tạp có thời gian xử lý khó dự đoán. Với dấu phân cách nguyên văn, Pattern.quote làm hợp đồng cấu hình rõ ràng hơn.

Scanner phù hợp với văn bản đơn giản cần đọc token rồi chuyển kiểu. Nó không tự hiểu dấu phẩy trong trường CSV được bao bằng ngoặc kép, ký tự escape hoặc bản ghi CSV trải nhiều dòng. Khi đầu vào có các quy tắc này, chọn thư viện phân tích đúng định dạng.

Các Scanner trong ví dụ được đóng bằng try-with-resources vì chỉ sở hữu nguồn String cục bộ. Khi Scanner bọc nguồn dùng chung như System.in, đóng Scanner có thể đóng cả nguồn; nơi sở hữu nguồn cần quyết định vòng đời.

## 9. Thực hành

1. Đổi delimiter của trường hợp spaces-kept thành "[;\\s]+". Dự đoán rồi chạy: «A B;C D» cho bốn token A, B, C, D. Giải thích vì sao họ tên có dấu cách không còn nguyên vẹn.
2. Đọc «AA||BB||CC» với dấu phân cách nguyên văn "||". Dùng Pattern.quote("||"); kết quả mong đợi là ba token AA, BB, CC.
3. Với «A,,B,», giải thích vì sao đổi từ "," sang ",+" làm mất token rỗng ở giữa nhưng không giải quyết yêu cầu giữ trường rỗng cuối.
4. Với «1,5;2,5», giữ locale Đức nhưng đổi delimiter thành "[,;]". Hai token số đầu khi ấy là 1 và 5, thay vì hai số thập phân ban đầu. Xác định thông tin bị mất ở bước phân tách.

Trước khi hoàn tất cách đọc dữ liệu, kiểm tra ít nhất: nguồn rỗng, một token, delimiter liên tiếp, delimiter đầu/cuối, khoảng trắng, xuống dòng và ký tự delimiter có thể nằm trong giá trị.
