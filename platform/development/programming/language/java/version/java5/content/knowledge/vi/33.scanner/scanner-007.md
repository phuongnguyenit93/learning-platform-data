# Phối hợp nextInt với nextLine

## 1. Vì sao đọc số xong lại nhận một dòng rỗng?

Một chương trình hỏi tuổi rồi hỏi họ tên thường viết nextInt() để nhận tuổi và nextLine() để nhận cả họ tên. Khi chạy, biến họ tên có thể nhận chuỗi rỗng ngay sau khi nhập tuổi.

Nguyên nhân là **hai phương thức sử dụng hai đơn vị đọc khác nhau**:

- **nextInt()** đọc một token có thể chuyển thành int. Với delimiter mặc định, các khoảng trắng trước token được bỏ qua, nhưng phương thức không tự tiêu thụ phần còn lại của dòng sau số.
- **nextLine()** đọc từ vị trí hiện tại đến hết dòng, trả phần văn bản đó không kèm dấu kết thúc dòng, rồi chuyển sang đầu dòng kế tiếp.

Vì vậy, nextLine() không có nghĩa là “luôn đọc dòng mới tiếp theo”. Nó đọc **phần còn lại của dòng hiện tại**. Nếu sau số chỉ còn dấu xuống dòng, phần còn lại là chuỗi rỗng.

Đây là cơ chế hiện hành của Scanner, không phải lỗi ngẫu nhiên hay lỗi bàn phím. Hợp đồng phương thức được mô tả trong [Java SE 21 Scanner API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html).

## 2. Hình dung vị trí đọc thay vì học thuộc mẹo

Giả sử nguồn chứa:

```text
23\nNguyen Van An\n
```

Trong hình minh họa, \n biểu diễn ký tự xuống dòng, không phải hai ký tự dấu gạch chéo và chữ n. Vị trí đọc thay đổi như sau:

```text
Ban đầu:
|23\nNguyen Van An\n

Sau nextInt() -> 23:
23|\nNguyen Van An\n

Sau nextLine() -> "":
23\n|Nguyen Van An\n

Sau nextLine() lần nữa -> "Nguyen Van An":
23\nNguyen Van An\n|
```

Dấu | chỉ đánh dấu vị trí đọc, không thuộc dữ liệu. Lần nextLine() đầu không “bỏ qua tên”: nó hoàn thành việc đọc dòng chứa số. Lần tiếp theo mới nhận dòng họ tên.

Nếu nguồn là «23   \nNguyen Van An\n», lần nextLine() sau nextInt() trả về **ba dấu cách**, không phải chuỗi rỗng. Nếu nguồn là «23 ghi-chu\nNguyen Van An\n», nó trả về « ghi-chu». Vì vậy mô tả chính xác là “phần còn lại của dòng”, không phải “một ký tự Enter còn thừa”.

Trên dữ liệu kết thúc dòng bằng \r\n, nextLine() nhận biết dấu kết thúc dòng và loại nó khỏi giá trị trả về. Không cần tự đọc hai ký tự để xử lý từng phần của \r\n.

## 3. Hai cách thiết kế đúng, tùy hợp đồng đầu vào

| Hợp đồng dữ liệu | Cách đọc phù hợp | Điểm phải quyết định |
| --- | --- | --- |
| Một số ở một dòng, họ tên ở dòng sau | nextInt(), xử lý phần còn lại của dòng, rồi nextLine() | Phần sau số có được bỏ hay phải kiểm tra? |
| Mỗi câu trả lời là một dòng hoàn chỉnh | nextLine() cho mọi câu trả lời; chuyển dòng số thành int | Quy tắc khoảng trắng, lỗi số và giới hạn giá trị |
| Số và họ tên nằm trên cùng một dòng | nextInt(), rồi dùng kết quả nextLine() làm phần tên | Có loại dấu cách đầu hay giữ nguyên? |
| Nhiều token số trước một đoạn văn | Đọc đủ token số, rồi chuyển chế độ tại ranh giới bản ghi | Dòng văn bắt đầu ở cùng dòng hay dòng sau? |

Điều quan trọng là xác định **một bản ghi bắt đầu và kết thúc ở đâu**. Không có quy tắc đúng cho mọi đầu vào rằng “sau nextInt luôn phải gọi thêm một nextLine rồi bỏ kết quả”.

## 4. Cách thứ nhất: đọc token rồi hoàn thành dòng hiện tại

Đoạn sau minh họa cấu trúc khi hợp đồng yêu cầu số ở dòng riêng và tên ở dòng kế tiếp. Mã đặt trong một phương thức có biến scanner:

```java
int age = scanner.nextInt();
String remainder = scanner.nextLine();
String name = scanner.nextLine();
```

Chỉ được bỏ biến remainder nếu phần còn lại của dòng không chứa dữ liệu cần giữ. Nếu quy tắc là “mỗi dòng tuổi chỉ có một số”, hãy **kiểm tra phần còn lại chỉ chứa khoảng trắng** thay vì âm thầm bỏ nội dung:

```java
int age = scanner.nextInt();
if (!scanner.hasNextLine()) {
    throw new IllegalArgumentException("Missing name line");
}
String remainder = scanner.nextLine();
if (!remainder.isBlank()) {
    throw new IllegalArgumentException("Unexpected text after age");
}
if (!scanner.hasNextLine()) {
    throw new IllegalArgumentException("Missing name line");
}
String name = scanner.nextLine();
```

Đây vẫn chưa phải bộ kiểm tra hoàn chỉnh cho hợp đồng “một số trên mỗi dòng”. nextInt() với delimiter mặc định có thể bỏ qua cả các dòng trống trước số. Nếu cần từ chối dòng tuổi rỗng ngay tại vị trí đó, cách đọc toàn dòng ở phần sau rõ ràng hơn.

### Trường hợp số và tên cùng dòng

Với nguồn «23 Nguyen Van An\n», gọi nextInt() rồi nextLine() thu được phần còn lại « Nguyen Van An». Nếu dòng này chứa tên cần giữ, gọi thêm nextLine() để “xóa Enter” sẽ làm mất tên.

Nếu định dạng quy định các khoảng trắng đầu phần tên chỉ là dấu ngăn cách, có thể áp dụng stripLeading() lên phần còn lại. Nếu khoảng trắng đầu/cuối là dữ liệu có ý nghĩa, không tự loại chúng.

## 5. Chương trình quan sát cả ba tình huống và hết nguồn

Lưu **MixedReadDemo.java**. Các nguồn String khiến kết quả có thể lặp lại mà không cần nhập bàn phím.

```java
import java.util.Scanner;

public class MixedReadDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("23\nNguyen Van An\n")) {
            int age = scanner.nextInt();
            String line = scanner.nextLine();
            String following = scanner.nextLine();
            System.out.println("age=" + age);
            System.out.println("first-line=[" + line + "]");
            System.out.println("following=[" + following + "]");
        }

        try (Scanner scanner = new Scanner("23\nNguyen Van An\n")) {
            int age = scanner.nextInt();
            String remainder = scanner.nextLine();
            String name = scanner.nextLine();
            System.out.println("mixed-age=" + age);
            System.out.println("remainder=[" + remainder + "]");
            System.out.println("mixed-name=[" + name + "]");
        }

        try (Scanner scanner = new Scanner("23 Nguyen Van An\n")) {
            int age = scanner.nextInt();
            String rest = scanner.nextLine();
            System.out.println("same-line-age=" + age);
            System.out.println("same-line-rest=[" + rest + "]");
        }

        try (Scanner scanner = new Scanner("23")) {
            int age = scanner.nextInt();
            System.out.println("eof-age=" + age);
            System.out.println("eof-has-line=" + scanner.hasNextLine());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac -encoding UTF-8 MixedReadDemo.java
java MixedReadDemo
```

Kết quả:

```text
age=23
first-line=[]
following=[Nguyen Van An]
mixed-age=23
remainder=[]
mixed-name=[Nguyen Van An]
same-line-age=23
same-line-rest=[ Nguyen Van An]
eof-age=23
eof-has-line=false
```

Cặp [] do chương trình in thêm để thấy chuỗi rỗng hoặc dấu cách.

Trường hợp cuối có nguồn chỉ gồm «23», không có dấu xuống dòng hay văn bản sau số. nextInt() vẫn đọc được số, nhưng hasNextLine() trả false. Gọi nextLine() vô điều kiện lúc này gây NoSuchElementException. Đây là lý do cần xét hết nguồn thay vì giả định sau số luôn có một dòng còn lại.

## 6. Cách thứ hai: đọc toàn dòng rồi chuyển thành số

Khi một câu trả lời tương ứng một dòng, ta có thể dùng nextLine() cho tất cả câu hỏi:

1. Đọc trọn dòng tuổi.
2. Áp dụng quy tắc khoảng trắng.
3. Chuyển thành int và kiểm tra miền giá trị.
4. Đọc trọn dòng họ tên.

Cách này không trộn hai đơn vị đọc. Một lần nhập sai cũng có ranh giới rõ ràng: toàn bộ dòng đã được tiêu thụ, nên lần thử tiếp theo bắt đầu ở dòng kế tiếp.

Ví dụ dưới dùng quy tắc minh họa: tuổi là số nguyên thập phân trong khoảng 0 đến 150, tên không rỗng sau khi bỏ khoảng trắng hai đầu. Giới hạn 150 là lựa chọn của ví dụ, không phải quy tắc của Java.

Lưu **LineInputDemo.java**:

```java
import java.util.NoSuchElementException;
import java.util.Scanner;

public class LineInputDemo {
    private static int readAge(Scanner scanner) {
        while (scanner.hasNextLine()) {
            String line = scanner.nextLine().strip();
            if (line.isEmpty()) {
                System.out.println("age: empty");
                continue;
            }
            try {
                int age = Integer.parseInt(line);
                if (age < 0 || age > 150) {
                    System.out.println("age: out-of-range");
                    continue;
                }
                return age;
            } catch (NumberFormatException ex) {
                System.out.println("age: invalid");
            }
        }
        throw new NoSuchElementException("Missing age");
    }

    private static String readName(Scanner scanner) {
        while (scanner.hasNextLine()) {
            String name = scanner.nextLine().strip();
            if (!name.isEmpty()) {
                return name;
            }
            System.out.println("name: empty");
        }
        throw new NoSuchElementException("Missing name");
    }

    public static void main(String[] args) {
        String input = "abc\n200\n\n23\n\nNguyen Van An\n";
        try (Scanner scanner = new Scanner(input)) {
            int age = readAge(scanner);
            String name = readName(scanner);
            System.out.println("accepted-age=" + age);
            System.out.println("accepted-name=[" + name + "]");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 LineInputDemo.java
java LineInputDemo
```

Kết quả:

```text
age: invalid
age: out-of-range
age: empty
name: empty
accepted-age=23
accepted-name=[Nguyen Van An]
```

Ba dòng đầu vào cho tuổi bị từ chối lần lượt vì sai dạng, ngoài miền cho phép và rỗng. Dòng 23 được chấp nhận. Dòng tên rỗng bị từ chối rồi mới nhận Nguyen Van An.

Các hàm nhận Scanner từ bên ngoài và **không tự đóng nó**. Hàm main sở hữu Scanner nên đóng ở một nơi bằng try-with-resources. Nếu hết nguồn trước khi có giá trị hợp lệ, hàm phát NoSuchElementException với thông báo rõ ràng; ứng dụng tương tác thực tế có thể bắt lỗi này ở tầng điều phối và kết thúc luồng nhập.

### parseInt khác nextInt ở đâu?

Integer.parseInt(line) xử lý một chuỗi số nguyên, không sử dụng delimiter hay Locale của Scanner. Dòng «23 extra» bị từ chối toàn bộ, thay vì chỉ đọc số 23 rồi để lại chữ extra.

Chuỗi có dạng không hợp lệ hoặc giá trị vượt phạm vi int gây NumberFormatException. Chương trình gọi strip() trước vì đã chọn cho phép khoảng trắng hai đầu; parseInt tự nó không thực hiện bước này. Các chi tiết chuyển đổi được quy định trong [Java SE 21 Integer.parseInt API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String)).

Cách này không tự hỗ trợ mọi cách viết số theo vùng, chẳng hạn dấu phân nhóm hàng nghìn. Nếu đầu vào cần quy tắc số theo Locale, hãy chọn bộ phân tích phù hợp và vẫn kiểm tra toàn bộ bản ghi. Không coi hai cách chuyển số là tương đương tuyệt đối.

## 7. Xử lý đầu vào sai khi vẫn dùng nextInt

Khi nextInt() gặp token không thể chuyển sang int, nó gây InputMismatchException và không đi qua token gây lỗi. Nếu bắt ngoại lệ rồi gọi nextInt() lại mà không thay đổi vị trí đọc, chương trình gặp lại cùng dữ liệu sai.

Với hợp đồng “mỗi lần nhập là một dòng”, có thể phục hồi bằng cách đọc hết dòng bị lỗi trước khi yêu cầu nhập lại. Nếu hợp đồng cho phép nhiều trường trên cùng dòng, việc bỏ cả dòng có thể làm mất trường hợp lệ; cần quy định cách phục hồi từ trước.

Không cần dùng ngoại lệ để thăm dò mọi lần đọc. Có thể kiểm tra hasNextInt(), nhưng vẫn phải phân biệt:

- Không còn token vì đã hết nguồn.
- Còn token nhưng token không phải int hợp lệ.
- Có số hợp lệ nhưng không thỏa miền giá trị của bài toán.

hasNextInt() không tiêu thụ token. hasNextLine() cũng không tiêu thụ dòng. Cả hai chỉ kiểm tra; muốn tiến lên phải có thao tác đọc tương ứng.

## 8. Những cách sửa dễ che mất dữ liệu

### 8.1. Đổi nextLine thành next

next() chỉ nhận một token theo delimiter. Họ tên «Nguyen Van An» với delimiter mặc định trở thành ba token. Đổi phương thức để tránh chuỗi rỗng có thể làm chương trình chỉ lưu «Nguyen», không đáp ứng yêu cầu nhận họ tên đầy đủ.

### 8.2. Luôn gọi thêm nextLine rồi bỏ kết quả

Cách này chỉ đúng nếu phần còn lại của dòng được phép bỏ. Nó sai với dữ liệu cùng dòng hoặc với ghi chú phải giữ. Gán kết quả cho biến và xác định rõ vai trò của nó giúp nhận ra lỗi thiết kế.

### 8.3. Dùng nextInt để đọc cờ rồi thêm lệnh “xóa bộ đệm”

Scanner không cần một lệnh xóa bộ đệm chung để sửa tình huống này. Vấn đề là vị trí và đơn vị đọc. Gọi System.in.skip(...) hoặc đọc ký tự từ một đối tượng khác có thể bỏ dữ liệu sai nơi vì Scanner có bộ đệm nội bộ.

Không tạo nhiều Scanner trên cùng System.in cho từng câu hỏi. Các đối tượng có thể đọc đón dữ liệu và làm vị trí nhìn thấy giữa chúng không thống nhất. Dùng một nơi sở hữu nguồn nhập và truyền Scanner hoặc giá trị đã phân tích cho các hàm cần dùng.

### 8.4. Dùng regex bỏ khoảng trắng quá rộng

Bỏ mọi whitespace trước khi đọc tên có thể bỏ luôn một hoặc nhiều dòng trống có ý nghĩa. Nếu dòng trống là câu trả lời hợp lệ, phải giữ nó. Nếu dòng trống không hợp lệ, từ chối theo quy tắc kiểm tra đầu vào, thay vì để một lệnh bỏ qua âm thầm thay đổi bản ghi.

### 8.5. Đóng rồi mở lại Scanner để “làm sạch”

Đóng Scanner có thể đóng nguồn được bọc, bao gồm System.in. Mở đối tượng mới không phải cách khôi phục một nguồn đã đóng. Quyền đóng thuộc về nơi quản lý vòng đời nguồn.

## 9. Phân biệt dòng trống, hết nguồn và đang chờ nhập

| Trạng thái | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| nextLine() trả chuỗi rỗng | Có phần dòng rỗng được đọc, thường do chỉ còn dấu xuống dòng | Xử lý theo hợp đồng dữ liệu |
| hasNextLine() trả false | Không còn dòng để đọc ở vị trí hiện tại | Kết thúc, trả kết quả thiếu dữ liệu hoặc báo lỗi |
| Phương thức chưa trả về trên console | Có thể đang chờ dữ liệu đủ để hoàn thành thao tác | Kiểm tra yêu cầu nhập và cách kết thúc nguồn |
| nextInt() gây InputMismatchException | Token không thể chuyển thành int theo cấu hình | Báo lỗi và tiến qua dữ liệu sai theo quy tắc |
| nextLine() gây NoSuchElementException | Không có dòng để trả về | Tránh gọi vô điều kiện khi đầu vào có thể cạn |

Nhấn Enter tạo ranh giới dòng, không đồng nghĩa kết thúc nguồn nhập. Với nguồn tương tác, các phép kiểm tra cũng có thể chờ dữ liệu, nên hasNextLine() không phải phép thử “không chờ” để kiểm tra bàn phím có sẵn ký tự hay chưa.

## 10. Thực hành và tiêu chí tự kiểm tra

1. Trong MixedReadDemo, thay nguồn đầu tiên bằng "23   \nNguyen Van An\n". Dự đoán first-line sẽ chứa ba dấu cách. Chạy và đối chiếu.
2. Thay nguồn bằng "23 Nguyen Van An\n". Giải thích vì sao phần tên nằm trong kết quả nextLine() ngay sau nextInt(), và không được bỏ.
3. Với LineInputDemo, thay dòng tuổi đầu bằng "23 extra". Chương trình phải báo age: invalid và đọc dòng kế tiếp, không chấp nhận riêng 23.
4. Thử số "2147483648". Giá trị vượt Integer.MAX_VALUE nên phải đi vào nhánh age: invalid, trước khi kiểm tra miền tuổi.
5. Thử kết thúc nguồn ngay sau dòng tuổi. Tên bị thiếu phải được phát hiện, không bị thay bằng một tên rỗng ngầm định.
6. Thay các dấu xuống dòng trong nguồn thử nghiệm bằng \r\n. Các giá trị số và tên được chấp nhận phải giữ nguyên.

Khi đọc lại chương trình của mình, hãy xác định được vị trí đọc sau từng phương thức, phần dữ liệu nào đã bị tiêu thụ, phần nào được giữ và dòng trống có ý nghĩa gì. Khi bốn điều đó rõ ràng, việc phối hợp nextInt với nextLine trở thành một quyết định về định dạng dữ liệu.
