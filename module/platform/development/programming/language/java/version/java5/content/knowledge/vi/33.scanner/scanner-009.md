# Scanner: InputMismatchException và xử lý token không hợp lệ

## 1. Lỗi này nói điều gì?

`InputMismatchException` xuất hiện khi `Scanner` đang có một token nhưng không đọc được token ấy theo yêu cầu của lời gọi hiện tại. Hai nguyên nhân điển hình là:

- Token không khớp dạng dữ liệu mong đợi, chẳng hạn đọc `"abc"` bằng `nextInt()`.
- Token có dạng số nhưng giá trị vượt phạm vi kiểu kết quả, chẳng hạn đọc `"2147483648"` bằng `nextInt()`.

Đây là một ngoại lệ không bắt buộc phải khai báo bằng `throws`, vì nó thuộc nhánh `RuntimeException`. Việc không bị trình biên dịch buộc xử lý không có nghĩa ứng dụng nên để dữ liệu nhập sai làm dừng chương trình một cách khó hiểu. [Định nghĩa InputMismatchException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/InputMismatchException.html).

Tình huống thường gặp là nhập số lượng hàng. Chương trình yêu cầu một số nguyên nhưng nhận `"ba"`, `"3.5"` hoặc một số quá lớn. Cần vừa báo lỗi đúng, vừa quyết định đọc tiếp ở đâu. **Bắt ngoại lệ chỉ là phát hiện lỗi; phục hồi cần một chính sách tiêu thụ hoặc từ chối dữ liệu.**

Các ví dụ dưới đây chạy trên Java 17 trở lên, dùng những API hiện hành và đầu vào chuỗi cố định để kiểm chứng được chính xác kết quả.

## 2. Hiểu đúng token trước khi xử lý lỗi

Với dấu phân cách mặc định, đầu vào:

~~~text
10 sai 20
~~~

gồm ba token `10`, `sai` và `20`. Một lần `nextInt()` thành công tiêu thụ token `10`. Lần `nextInt()` tiếp theo gặp `sai` và ném `InputMismatchException`.

Điểm quyết định việc phục hồi là: **scanner không đi qua token gây InputMismatchException**. Token `sai` vẫn có thể được đọc bằng `next()` hoặc xử lý theo cách khác. Gọi lại `nextInt()` ngay mà không thay đổi gì sẽ gặp cùng lỗi.

~~~text
Trước khi đọc:        [10] [sai] [20]
nextInt() thành công:      [sai] [20]
nextInt() thất bại:        [sai] [20]
next() lấy token sai:            [20]
nextInt() thành công:                 hết token
~~~

Sơ đồ biểu diễn vị trí token ở tầng phân tích. Scanner có thể đã đọc trước từ nguồn vào bộ đệm; không nên hiểu rằng vị trí byte của tệp luôn trùng với token vừa xử lý.

“Đọc lại” cũng không đồng nghĩa với tạo scanner mới từ cùng một luồng. Scanner cũ có thể đã giữ dữ liệu trong bộ đệm, còn đóng nó có thể đóng cả nguồn. Hãy phục hồi bằng scanner đang sở hữu lượt đọc.

## 3. Những trường hợp nào gây mismatch?

| Lời gọi | Token | Vì sao thất bại? |
| --- | --- | --- |
| `nextInt()` | `abc` | Không biểu diễn được thành số nguyên |
| `nextInt()` | `2.5` | Số thập phân không tự chuyển thành số nguyên |
| `nextInt()` | `2147483648` | Vượt giá trị lớn nhất của `int` |
| `nextByte()` | `128` | Vượt phạm vi `byte` |
| `nextBoolean()` | `yes` | Không khớp dạng boolean mà Scanner chấp nhận |
| `next("[A-Z]{2}")` | `Ab` | Token không khớp toàn bộ biểu thức chính quy đã yêu cầu |

Bảng giả định các cấu hình phù hợp thông thường; locale, cơ số và dấu phân cách cũng ảnh hưởng cách scanner nhận diện dữ liệu. Không phải mọi chuỗi người dùng gọi là “số” đều hợp lệ theo cấu hình chương trình.

Ví dụ `ff` có thể là số nguyên hợp lệ khi dùng `nextInt(16)`, nhưng không hợp lệ khi đọc theo cơ số 10. Một dấu phẩy có thể là dấu thập phân, dấu phân nhóm hoặc dấu phân cách trường tùy quy ước đầu vào.

### Tách lỗi phân tích khỏi lỗi nghiệp vụ

Nếu yêu cầu số lượng nằm trong `1..100`, token `0` vẫn đọc được bằng `nextInt()`. Scanner không tự biết giới hạn nghiệp vụ của ứng dụng.

Quá trình kiểm tra cần hai tầng:

1. Token có chuyển được sang kiểu mong đợi không?
2. Giá trị sau chuyển đổi có được ứng dụng cho phép không?

Không nên gọi mọi dữ liệu sai nghiệp vụ là `InputMismatchException`. Giữ tên và thông báo lỗi phản ánh đúng điều đã thất bại.

## 4. Thí nghiệm: token lỗi vẫn còn

Lưu thành `ScannerMismatchTrace.java`:

~~~java
import java.util.InputMismatchException;
import java.util.Scanner;

public class ScannerMismatchTrace {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("bad 2147483648 8")) {
            for (int attempt = 0; attempt < 2; attempt++) {
                try {
                    scanner.nextInt();
                } catch (InputMismatchException failure) {
                    System.out.println("mismatch");
                    System.out.println("stillHasToken="
                            + scanner.hasNext());
                    System.out.println("removed=" + scanner.next());
                }
            }

            System.out.println("valid=" + scanner.nextInt());
            System.out.println("remaining=" + scanner.hasNext());
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 ScannerMismatchTrace.java
java ScannerMismatchTrace
~~~

Stdout chính xác:

~~~text
mismatch
stillHasToken=true
removed=bad
mismatch
stillHasToken=true
removed=2147483648
valid=8
remaining=false
~~~

Lần lỗi đầu liên quan đến định dạng; lần lỗi sau liên quan đến phạm vi `int`. Cả hai đều để lại token. `scanner.next()` trong nhánh `catch` tiêu thụ token đó, nhờ vậy scanner có thể tiến tới `8`.

Ví dụ dùng một scanner trong một luồng xử lý duy nhất và dữ liệu đã biết. Không dựa vào thông báo `failure.getMessage()` để phân loại nguyên nhân: thông báo không phải giao thức dữ liệu ổn định cho ứng dụng.

## 5. Chọn chính sách trước khi viết catch

Không tồn tại một cách phục hồi đúng cho mọi định dạng.

| Bối cảnh | Chính sách thường phù hợp | Ranh giới dữ liệu cần giữ |
| --- | --- | --- |
| Người dùng nhập một giá trị tương tác | Báo lỗi rồi yêu cầu nhập lại | Một token hoặc một dòng, theo thiết kế nhập |
| Luồng token độc lập, cho phép lọc bỏ dữ liệu sai | Ghi nhận token bị loại rồi đọc tiếp | Một token |
| Một dòng là một bản ghi nhiều trường | Từ chối cả bản ghi khi có trường sai | Một dòng |
| Tệp bắt buộc mọi bản ghi phải đúng | Báo lỗi và dừng trước khi chấp nhận kết quả | Toàn bộ đơn vị xử lý |
| Mã định danh trông như số | Đọc dưới dạng `String` nếu cần giữ nguyên văn | Giá trị chuỗi đầy đủ |

Ví dụ dòng `"SP01 wrong 50000"` có ba trường mã hàng, số lượng và giá. Nếu số lượng sai mà ta chỉ bỏ `wrong` rồi coi `50000` là số lượng, dữ liệu bị lệch cột. Chương trình có thể chạy tiếp nhưng tạo kết quả sai.

Bởi vậy, “luôn gọi next() trong catch” chỉ đúng khi chính sách cho phép bỏ đúng token đó. Với bản ghi có cấu trúc, có thể cần từ chối cả bản ghi thay vì nối token của trường sau vào trường trước.

Đừng âm thầm thay dữ liệu sai bằng `0`. Số 0 có thể là một giá trị hợp lệ, làm mất dấu hiệu lỗi và gây khó truy vết.

## 6. Cách 1: kiểm tra bằng hasNextInt() rồi đọc

`hasNextInt()` kiểm tra token tiếp theo theo kiểu `int`, bao gồm phạm vi của kiểu, nhưng không tiêu thụ token. `false` có thể do token sai hoặc do không còn token; khi cần phân biệt, dùng `hasNext()`.

Một cấu trúc dễ theo dõi:

~~~text
Còn token?
  không -> kết thúc nguồn
  có    -> đọc được int?
             không -> xử lý token sai theo chính sách
             có    -> tiêu thụ int -> kiểm tra quy tắc nghiệp vụ
~~~

Chương trình sau chọn chính sách: bỏ token không phải `int`; từ chối giá trị ngoài `1..100`; trả về số lượng hợp lệ đầu tiên; nếu hết nguồn thì báo vắng giá trị.

Lưu thành `ScannerQuantityReader.java`:

~~~java
import java.util.OptionalInt;
import java.util.Scanner;

public class ScannerQuantityReader {
    private static OptionalInt readQuantity(Scanner scanner) {
        while (scanner.hasNext()) {
            if (!scanner.hasNextInt()) {
                String invalid = scanner.next();
                System.out.println("rejected-format=" + invalid);
                continue;
            }

            int quantity = scanner.nextInt();
            if (quantity < 1 || quantity > 100) {
                System.out.println("rejected-range=" + quantity);
                continue;
            }

            return OptionalInt.of(quantity);
        }

        return OptionalInt.empty();
    }

    public static void main(String[] args) {
        String input = "wrong 2147483648 0 101 25 60";

        try (Scanner scanner = new Scanner(input)) {
            OptionalInt first = readQuantity(scanner);
            OptionalInt second = readQuantity(scanner);
            OptionalInt third = readQuantity(scanner);

            System.out.println("first=" + first.orElseThrow());
            System.out.println("second=" + second.orElseThrow());
            System.out.println("thirdPresent=" + third.isPresent());
        }
    }
}
~~~

~~~shell
javac --release 17 -encoding UTF-8 ScannerQuantityReader.java
java ScannerQuantityReader
~~~

Stdout chính xác:

~~~text
rejected-format=wrong
rejected-format=2147483648
rejected-range=0
rejected-range=101
first=25
second=60
thirdPresent=false
~~~

`rejected-format` trong ví dụ nghĩa rộng là không đọc được bằng `nextInt()`, bao gồm cả vượt phạm vi kiểu. Chương trình không khẳng định token `2147483648` không phải số trong mọi kiểu dữ liệu.

`OptionalInt.empty()` biểu diễn hết nguồn mà chưa tìm được giá trị hợp lệ. Nó tránh dùng một số đặc biệt như `-1` để đồng thời đóng hai vai trò “dữ liệu” và “không có dữ liệu”.

Hàm `readQuantity(...)` nhận scanner của bên gọi nên không đóng scanner. Khối `main` tạo và sở hữu scanner, chịu trách nhiệm đóng một lần. Điều đó cho phép gọi hàm nhiều lần trên cùng nguồn.

Trong chương trình tương tác, có thể bổ sung thông báo yêu cầu nhập lại. Vẫn cần xử lý kết thúc nguồn; đừng viết vòng lặp yêu cầu nhập mãi khi không còn dữ liệu.

## 7. Cách 2: bắt đúng InputMismatchException

Dùng `try/catch` khi cách đọc trực tiếp phù hợp và việc phục hồi sau thất bại đã rõ.

~~~java
try {
    int quantity = scanner.nextInt();
    System.out.println("Read: " + quantity);
} catch (InputMismatchException failure) {
    String invalid = scanner.next();
    System.out.println("Not a valid int: " + invalid);
}
~~~

Đây là mảnh mã trong một phương thức đã có `Scanner scanner` và các import tương ứng, không phải chương trình chạy độc lập. Nó minh họa một lần đọc có token sai; chưa xử lý trường hợp nguồn đã hết.

Nếu nguồn có thể hết, bổ sung kiểm tra tồn tại hoặc xử lý `NoSuchElementException` theo yêu cầu. Không bắt `Exception` cho toàn bộ chương trình rồi in “nhập sai” cho mọi lỗi, vì lỗi tài nguyên hoặc lỗi lập trình sẽ bị báo nhầm.

### Thứ tự catch

`InputMismatchException` kế thừa `NoSuchElementException`. Khi cần phân biệt sai token và hết token, nhánh cụ thể phải đứng trước nhánh lớp cha:

~~~java
try {
    int value = scanner.nextInt();
    System.out.println(value);
} catch (InputMismatchException failure) {
    String invalid = scanner.next();
    System.out.println("Invalid token: " + invalid);
} catch (java.util.NoSuchElementException end) {
    System.out.println("No more input");
}
~~~

Đây cũng là mảnh mã trong phương thức với biến scanner đã có. Đảo hai nhánh `catch` sẽ khiến nhánh `InputMismatchException` không thể được tiếp cận và bị trình biên dịch từ chối.

Không coi scanner đã đóng là một token sai. `IllegalStateException` ở thao tác đọc thường chỉ ra vấn đề vòng đời; gọi `next()` trong nhánh xử lý ấy không thể làm scanner hoạt động trở lại.

## 8. Cách 3: từ chối cả dòng có lỗi

Khi một dòng là một bản ghi độc lập, cách dễ giữ ranh giới là đọc dòng từ nguồn bên ngoài, rồi dùng scanner riêng để kiểm tra nội dung của dòng. Bản ghi chỉ được chấp nhận sau khi đủ trường, đúng kiểu, đúng quy tắc và không có phần dư không được phép.

Ví dụ định dạng tối giản: `<mã-hàng> <số-lượng>`, số lượng phải dương. Không có trường chứa khoảng trắng và không có quy tắc CSV.

Lưu thành `ScannerStrictRecordDemo.java`:

~~~java
import java.util.Scanner;

public class ScannerStrictRecordDemo {
    private static String parseRecord(String line) {
        try (Scanner scanner = new Scanner(line)) {
            if (!scanner.hasNext()) {
                throw new IllegalArgumentException("Missing code");
            }
            String code = scanner.next();

            if (!scanner.hasNext()) {
                throw new IllegalArgumentException("Missing quantity");
            }
            if (!scanner.hasNextInt()) {
                throw new IllegalArgumentException(
                        "Quantity must be an int");
            }

            int quantity = scanner.nextInt();
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "Quantity must be positive");
            }

            if (scanner.hasNext()) {
                throw new IllegalArgumentException("Extra fields");
            }

            return code + ":" + quantity;
        }
    }

    public static void main(String[] args) {
        String[] lines = {
                "A 3",
                "B three",
                "C",
                "D 0",
                "E 2 extra"
        };

        for (String line : lines) {
            try {
                String record = parseRecord(line);
                System.out.println("accepted=" + record);
            } catch (IllegalArgumentException failure) {
                System.out.println("rejected=" + line
                        + " | " + failure.getMessage());
            }
        }
    }
}
~~~

~~~shell
javac --release 17 -encoding UTF-8 ScannerStrictRecordDemo.java
java ScannerStrictRecordDemo
~~~

Stdout chính xác:

~~~text
accepted=A:3
rejected=B three | Quantity must be an int
rejected=C | Missing quantity
rejected=D 0 | Quantity must be positive
rejected=E 2 extra | Extra fields
~~~

Chương trình giữ riêng lỗi thiếu trường, sai kiểu, sai quy tắc nghiệp vụ và thừa trường. `parseRecord(...)` không trả về kết quả cho một bản ghi chưa vượt qua toàn bộ kiểm tra.

Với dữ liệu mẫu nhỏ, chương trình in nguyên dòng để dễ quan sát. Trong hệ thống thực tế, thông báo nên có vị trí dòng/trường cần sửa và giới hạn độ dài; tránh ghi nguyên mật khẩu, khóa truy cập hoặc dữ liệu nhạy cảm vào log.

Nếu nguồn bên ngoài là scanner đọc dòng, scanner cho từng dòng chỉ bọc một `String`; đóng scanner của dòng không đóng nguồn ngoài. Nguồn ngoài vẫn được quản lý theo quyền sở hữu của nó.

## 9. Hai vòng lặp sai thường gặp

### Bắt lỗi nhưng không đi qua token

~~~java
while (scanner.hasNext()) {
    try {
        System.out.println(scanner.nextInt());
    } catch (InputMismatchException failure) {
        System.out.println("Please enter an integer");
    }
}
~~~

Đây là **mảnh mã sai cố ý**. Khi gặp `abc`, scanner vẫn đứng ở `abc`; vòng lặp có thể in thông báo không ngừng. Không chạy mẫu này với dữ liệu có token sai.

Cách sửa tùy chính sách: lấy và loại token bằng `next()`, từ chối bản ghi, hoặc dừng. Chỉ thêm `continue` hay thêm một thông báo không làm dữ liệu tiến lên.

### Dùng hasNextInt() rồi tưởng đã đọc hết nguồn

~~~java
while (scanner.hasNextInt()) {
    System.out.println(scanner.nextInt());
}
~~~

Đây là mảnh mã hợp lệ cho yêu cầu “đọc dãy số nguyên liên tiếp ở đầu nguồn”. Với `"1 wrong 2"`, vòng lặp chỉ đọc `1` rồi dừng ở `wrong`.

Nếu cần báo dữ liệu sai, phải kiểm tra phần còn lại và xử lý nó; không kết luận “mọi số đã được xử lý” chỉ vì vòng lặp kết thúc.

## 10. Những cách chữa nhầm cần tránh

### Gọi nextLine() như một lệnh xóa lỗi chung

`nextLine()` tiêu thụ phần còn lại của dòng hiện tại. Nếu các trường sau token lỗi vẫn có giá trị cần giữ, nó có thể bỏ mất chúng.

Chỉ bỏ cả dòng khi ranh giới bản ghi hoặc chính sách nhập đã xác định là một dòng. Với luồng token độc lập, `next()` bỏ một token; hai hành động này không thay thế tùy tiện cho nhau.

### Gọi reset() để xóa token sai

`reset()` đặt lại cấu hình scanner như dấu phân cách, locale và cơ số; nó không phải nút xóa bộ đệm và không đưa vị trí đọc về đầu. Nếu token vẫn không phù hợp, đọc lại vẫn có thể lỗi.

Đổi locale hoặc cơ số chỉ hợp lý khi đó là quy ước đúng của dữ liệu. Không thử lần lượt các cấu hình đến khi một giá trị được chấp nhận nếu yêu cầu đầu vào chưa cho phép.

### Bắt NumberFormatException thay cho InputMismatchException

`Integer.parseInt(raw)` báo lỗi chuyển đổi bằng `NumberFormatException`. `scanner.nextInt()` báo token không đọc được bằng `InputMismatchException`. Hai đường đi có điểm tiêu thụ dữ liệu khác nhau.

Nếu chọn cách:

~~~java
String raw = scanner.next();
int value = Integer.parseInt(raw);
~~~

thì token đã được `next()` lấy ra trước khi `parseInt` chạy. Đây là mảnh mã minh họa có thể ném `NumberFormatException`. Sau lỗi, không gọi thêm `scanner.next()` chỉ để bỏ token vừa lỗi: nó đã bị tiêu thụ, và lời gọi mới sẽ bỏ token kế tiếp.

Ngoài ra, `parseInt` và Scanner không có mọi quy tắc nhận diện số giống nhau, nhất là khi Scanner được cấu hình locale/cơ số. Chọn một hợp đồng phân tích rõ ràng thay vì thay API chỉ để đổi loại ngoại lệ.

### Dùng kiểu rộng hơn để mọi dữ liệu sai đều qua

Đổi `int` thành `long` có thể giải quyết một giới hạn phạm vi thật sự. Nó không giải quyết token `abc` hoặc quy tắc số lượng phải dương. Chọn kiểu theo miền giá trị cần biểu diễn, rồi kiểm tra quy tắc ứng dụng.

### Nghĩ rằng không có mismatch nghĩa là dữ liệu chắc chắn đúng

Một số dấu phẩy động như `NaN` hoặc vô cực có thể được phương thức đọc số thực chấp nhận. Nếu yêu cầu giá trị hữu hạn, kiểm tra thêm `Double.isFinite(value)` hoặc `Float.isFinite(value)`.

Tương tự, số âm có thể hợp lệ với `int` nhưng sai với số lượng. Thành công ở tầng chuyển kiểu chỉ là một cổng kiểm tra.

## 11. Lỗi I/O và kết thúc nguồn phải được tách riêng

`hasNext() == false` thường giúp kết thúc vòng đọc, nhưng nguồn tệp/luồng cũng có thể gặp lỗi I/O. Scanner lưu lỗi đọc ở `ioException()`; khi cần xác nhận nguồn được đọc trọn vẹn, phải kiểm tra lỗi đó trước khi chấp nhận kết quả cuối.

`InputMismatchException` chỉ ra vấn đề token theo yêu cầu phân tích; nó không phải tín hiệu chung cho mất kết nối, không mở được tệp hay thiếu quyền đọc. [Hợp đồng Scanner về token lỗi và lỗi nguồn](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Scanner.html).

Với nguồn tương tác, `hasNext()` có thể chờ dữ liệu. Đừng dùng vòng lặp kiểm tra như cơ chế không chặn; khi nguồn kết thúc, dừng hoặc trả trạng thái vắng dữ liệu theo thiết kế.

## 12. Tự thực hành

1. Bỏ dòng `scanner.next()` trong nhánh `catch` của thí nghiệm đầu. Giải thích token nào còn lại và vì sao lần đọc sau không tiến lên như mong muốn.
2. Cho `ScannerQuantityReader` nhận `"0 x 100 101"`. Dự đoán lần gọi nào trả giá trị, lần nào trả rỗng và token nào bị loại.
3. Đổi yêu cầu số lượng từ `1..100` sang `1..1_000_000`. Xác định phần nào cần đổi và phần nào vẫn thuộc việc kiểm tra `int`.
4. Với định dạng `mã số-lượng giá`, viết chính sách từ chối cả dòng khi số lượng sai. Kiểm tra rằng giá không bị lấy nhầm làm số lượng.
5. So sánh lỗi từ `new Scanner("bad").nextInt()` với `Integer.parseInt("bad")`. Nêu rõ loại ngoại lệ và thời điểm token được tiêu thụ.
6. Bổ sung trường hợp dòng rỗng và dòng chỉ có khoảng trắng cho `ScannerStrictRecordDemo`. Kết quả phải phản ánh thiếu trường, không phải số lượng bằng 0.

Một bộ xử lý đầu vào đáng tin cần biết: lỗi nằm ở token, ở kiểu dữ liệu, ở quy tắc nghiệp vụ hay ở nguồn; sau lỗi, ranh giới dữ liệu nào vẫn còn và chương trình sẽ tiến lên bằng cách nào.
