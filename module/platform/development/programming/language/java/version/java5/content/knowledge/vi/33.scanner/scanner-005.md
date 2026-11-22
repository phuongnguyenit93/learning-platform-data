# Scanner: next, hasNext và các phương thức đọc kiểu số

## 1. Mô hình cần nắm: kiểm tra rồi đọc một token

`Scanner` phân tích văn bản theo những đơn vị gọi là **token**. Với cấu hình mặc định, khoảng trắng, tab và xuống dòng phân tách các token. Với đầu vào:

~~~text
Lan 12 3.5
~~~

ta có ba token `Lan`, `12` và `3.5`. Muốn đọc chúng, cần phân biệt hai việc:

- **Kiểm tra**: token tiếp theo có tồn tại không, hoặc có đọc được theo kiểu mong đợi không?
- **Tiêu thụ**: lấy token đó ra, chuyển đổi nếu cần và tiến tới phần dữ liệu tiếp theo.

`hasNext...` thuộc nhóm kiểm tra; `next...` thuộc nhóm tiêu thụ. Nhầm hai vai trò này thường gây đọc thiếu dữ liệu, vòng lặp không tiến lên hoặc ngoại lệ sai kiểu.

Bài dùng Java 17 trở lên và những API vẫn áp dụng trong Java hiện nay. Các ví dụ dùng chuỗi đầu vào cố định để quan sát đúng hành vi, không phụ thuộc bàn phím hay locale của máy.

## 2. next() và hasNext() làm gì?

| Lời gọi | Kết quả | Có tiêu thụ token không? |
| --- | --- | --- |
| `hasNext()` | `boolean`: còn token tiếp theo hay không | Không |
| `next()` | `String` chứa token tiếp theo | Có, nếu đọc thành công |
| `hasNextInt()` | `boolean`: token tiếp theo có đọc được thành `int` không | Không |
| `nextInt()` | Giá trị `int` từ token tiếp theo | Có, nếu đọc thành công |

### next() lấy một token, không lấy cả dòng

Với `"Nguyen Van An"`, ba lần `next()` lần lượt trả `"Nguyen"`, `"Van"`, `"An"`. Nếu trường họ tên có khoảng trắng và yêu cầu lấy toàn bộ dòng, phải lựa chọn chiến lược theo dòng; không thể coi một lần `next()` là một lần đọc cả họ tên.

Dữ liệu `"007"` được `next()` trả nguyên dạng chuỗi `"007"`. Nếu dùng `nextInt()` theo cơ số mặc định 10, kết quả là số `7`. Đây là khác biệt giữa **văn bản biểu diễn** và **giá trị số**: mã hàng, số điện thoại hoặc mã bưu chính thường cần giữ dưới dạng chuỗi dù trông giống số.

### hasNext() không đọc hộ cho next()

Sau hai lần `hasNext()`, token kế tiếp vẫn chưa bị tiêu thụ. Chỉ khi gọi `next()` hoặc một phương thức đọc thành công thì vị trí phân tích mới đi qua token đó.

Tuy nhiên, “không tiêu thụ token” không có nghĩa “không chạm vào nguồn”. Scanner có thể đọc trước để quyết định kết quả và giữ dữ liệu trong bộ đệm. Không trộn việc đọc trực tiếp nguồn bên dưới với việc đọc qua scanner.

### Ví dụ chạy đầy đủ

Lưu thành `ScannerTokenDemo.java`:

~~~java
import java.util.Locale;
import java.util.Scanner;

public class ScannerTokenDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("Lan 12 3.5 tail")) {
            scanner.useLocale(Locale.US);

            System.out.println("hasToken=" + scanner.hasNext());
            System.out.println("hasTokenAgain=" + scanner.hasNext());
            System.out.println("name=" + scanner.next());

            System.out.println("int?=" + scanner.hasNextInt());
            System.out.println("count=" + scanner.nextInt());
            System.out.println("price=" + scanner.nextDouble());
            System.out.println("left=" + scanner.next());
            System.out.println("end=" + scanner.hasNext());
        }
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 ScannerTokenDemo.java
java ScannerTokenDemo
~~~

Stdout chính xác:

~~~text
hasToken=true
hasTokenAgain=true
name=Lan
int?=true
count=12
price=3.5
left=tail
end=false
~~~

Hai dòng `hasToken` đều là `true` nhưng `name` vẫn là `Lan`, chứng minh việc kiểm tra không lấy mất token đầu. `Locale.US` được đặt rõ để dấu chấm trong `3.5` mang nghĩa phần thập phân theo quy ước của đầu vào.

## 3. Các cặp phương thức đọc số

Chọn phương thức theo **kiểu kết quả cần nhận**, không chỉ theo hình dạng token.

| Kiểu kết quả | Kiểm tra | Đọc |
| --- | --- | --- |
| `byte` | `hasNextByte()` | `nextByte()` |
| `short` | `hasNextShort()` | `nextShort()` |
| `int` | `hasNextInt()` | `nextInt()` |
| `long` | `hasNextLong()` | `nextLong()` |
| `float` | `hasNextFloat()` | `nextFloat()` |
| `double` | `hasNextDouble()` | `nextDouble()` |
| `BigInteger` | `hasNextBigInteger()` | `nextBigInteger()` |
| `BigDecimal` | `hasNextBigDecimal()` | `nextBigDecimal()` |

`BigInteger` và `BigDecimal` thuộc `java.math`. Không có `nextNumber()` để scanner tự chọn một kiểu số chung, cũng không có `nextChar()` trong API Scanner.

### Kiểm tra bao gồm phạm vi của kiểu

Token `2147483648` có các chữ số hợp lệ nhưng vượt `Integer.MAX_VALUE`:

- `hasNextInt()` trả `false`.
- `hasNextLong()` có thể trả `true` với token đó.
- `nextInt()` ném `InputMismatchException`.
- `nextLong()` đọc được giá trị `2147483648L`.

Tương tự, `128` không đọc được thành `byte`, dù đọc được thành `short` hoặc `int`. Đừng dùng `hasNextInt()` rồi gọi `nextByte()`: điều kiện kiểm tra cần khớp kiểu đọc.

Token `12.0` không tự được coi là `int` chỉ vì phần lẻ bằng 0. Nếu quy ước đầu vào là số nguyên, dùng cách đọc số nguyên; nếu cho phép số thập phân rồi ép về nguyên, phải xác định rõ quy tắc làm tròn và kiểm tra phạm vi.

### Kiểu dữ liệu và ý nghĩa nghiệp vụ là hai lớp kiểm tra

`hasNextInt()` có thể chấp nhận `-5`. Điều đó chỉ cho biết token phù hợp với kiểu `int` trong cấu hình hiện tại, không chứng minh đây là tuổi hợp lệ hoặc số lượng hợp lệ.

Với tuổi, có thể cần:

~~~java
if (!scanner.hasNextInt()) {
    throw new IllegalArgumentException("Age must be an integer");
}

int age = scanner.nextInt();
if (age < 0 || age > 150) {
    throw new IllegalArgumentException("Age is outside the allowed range");
}
~~~

Đây là mảnh mã đặt trong một phương thức đã có biến `Scanner scanner`, không phải chương trình chạy độc lập. Quy tắc `0..150` chỉ là quy tắc minh họa; ứng dụng phải chọn giới hạn đúng với yêu cầu thực tế.

Nếu cần phân biệt “thiếu trường” với “trường có dữ liệu sai kiểu”, kiểm tra `hasNext()` trước rồi mới `hasNextInt()`. Một kết quả `hasNextInt() == false` đơn lẻ chưa phân biệt được hai tình huống đó.

## 4. Đọc đủ các kiểu số trong một chương trình

Lưu thành `ScannerNumericTypesDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.Locale;
import java.util.Scanner;

public class ScannerNumericTypesDemo {
    public static void main(String[] args) {
        String input =
                "127 32000 2147483647 9223372036854775807 "
                + "1.25 2.5 123456789012345678901234567890 19.90";

        try (Scanner scanner = new Scanner(input)) {
            scanner.useLocale(Locale.US);

            byte small = scanner.nextByte();
            short medium = scanner.nextShort();
            int count = scanner.nextInt();
            long large = scanner.nextLong();
            float ratio = scanner.nextFloat();
            double value = scanner.nextDouble();
            BigInteger huge = scanner.nextBigInteger();
            BigDecimal amount = scanner.nextBigDecimal();

            System.out.println("byte=" + small);
            System.out.println("short=" + medium);
            System.out.println("int=" + count);
            System.out.println("long=" + large);
            System.out.println("float=" + ratio);
            System.out.println("double=" + value);
            System.out.println("bigInteger=" + huge);
            System.out.println("bigDecimal=" + amount.toPlainString());
            System.out.println("remaining=" + scanner.hasNext());
        }
    }
}
~~~

~~~shell
javac --release 17 -encoding UTF-8 ScannerNumericTypesDemo.java
java ScannerNumericTypesDemo
~~~

Stdout chính xác:

~~~text
byte=127
short=32000
int=2147483647
long=9223372036854775807
float=1.25
double=2.5
bigInteger=123456789012345678901234567890
bigDecimal=19.90
remaining=false
~~~

Đầu vào ở đây do chương trình tự quy định nên các lần đọc trực tiếp đã biết thứ tự và loại token. Khi xử lý dữ liệu từ bên ngoài, cần thêm chính sách kiểm tra, báo lỗi hoặc yêu cầu nhập lại.

`BigInteger` phù hợp khi số nguyên vượt phạm vi `long`. `BigDecimal` biểu diễn số thập phân với độ chính xác tùy ý và giữ được phần thập phân như `19.90` trong ví dụ. Chúng vẫn chịu giới hạn tài nguyên; không nên nhận token dài tùy ý từ một nguồn không kiểm soát.

`float` và `double` là số dấu phẩy động nhị phân. Đọc thành công không loại bỏ sai số của biểu diễn nhị phân. Khi cần phép tính thập phân chính xác theo quy tắc tài chính, cân nhắc đọc trực tiếp bằng `nextBigDecimal()` rồi áp dụng quy tắc làm tròn rõ ràng.

Không đọc `double` trước rồi mới tạo `BigDecimal` nếu mục tiêu là giữ chính xác giá trị thập phân ban đầu.

## 5. Sai kiểu, hết dữ liệu và scanner đã đóng

| Tình huống | Hành vi tiêu biểu |
| --- | --- |
| Gọi `next()` khi không còn token | `NoSuchElementException` |
| Gọi `nextInt()` khi đã hết token | `NoSuchElementException` |
| Còn token nhưng không biểu diễn được thành `int` | `InputMismatchException` |
| Gọi thao tác đọc/kiểm tra trên scanner đã đóng | `IllegalStateException` |
| Dùng cơ số ngoài khoảng hợp lệ | `IllegalArgumentException` |

`InputMismatchException` là lớp con của `NoSuchElementException`. Nếu viết hai nhánh `catch` cho cả hai loại, đặt nhánh cụ thể trước; đặt lớp cha trước sẽ làm nhánh lớp con không thể chạy.

Sau `InputMismatchException`, token gây lỗi vẫn còn. Nếu chỉ bắt lỗi rồi thử lại `nextInt()` ngay, chương trình lại gặp chính token đó. Cần chọn một trong các hướng:

- Tiêu thụ token sai bằng `next()` rồi tiếp tục, nếu yêu cầu cho phép bỏ qua.
- Báo lỗi và dừng xử lý bản ghi.
- Chuyển sang đọc kiểu khác, nếu định dạng của ứng dụng cho phép.
- Với giao diện tương tác, bỏ phần nhập sai theo chính sách rồi yêu cầu nhập lại.

Không tự bỏ dữ liệu sai nếu yêu cầu nghiệp vụ cần từ chối toàn bộ bản ghi.

### Chương trình minh họa phục hồi

Lưu thành `ScannerRecoveryDemo.java`:

~~~java
import java.util.InputMismatchException;
import java.util.Scanner;

public class ScannerRecoveryDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("10 x 20 2147483648 -3")) {
            long total = 0;

            while (scanner.hasNext()) {
                if (scanner.hasNextInt()) {
                    int value = scanner.nextInt();
                    total = Math.addExact(total, value);
                    System.out.println("accepted=" + value);
                } else {
                    String rejected = scanner.next();
                    System.out.println("rejected=" + rejected);
                }
            }

            System.out.println("total=" + total);
        }

        try (Scanner scanner = new Scanner("oops 7")) {
            try {
                scanner.nextInt();
            } catch (InputMismatchException failure) {
                System.out.println("badToken=" + scanner.next());
            }

            System.out.println("afterRecovery=" + scanner.nextInt());
        }
    }
}
~~~

~~~shell
javac --release 17 -encoding UTF-8 ScannerRecoveryDemo.java
java ScannerRecoveryDemo
~~~

Stdout chính xác:

~~~text
accepted=10
rejected=x
accepted=20
rejected=2147483648
accepted=-3
total=27
badToken=oops
afterRecovery=7
~~~

Hai token `x` và `2147483648` bị từ chối vì hai lý do khác nhau: một token sai dạng số nguyên, một token vượt phạm vi `int`. Cả hai đều cần được tiêu thụ nếu muốn tiếp tục vòng lặp.

Ví dụ chủ động chọn chính sách “ghi nhận token bị từ chối rồi đọc tiếp”. Tổng dùng `long`, còn `Math.addExact` phát hiện tràn số khi cộng, vì việc từng token đọc được thành `int` không chứng minh tổng của rất nhiều token sẽ nằm trong phạm vi.

## 6. Vì sao vòng lặp có thể dừng sớm hoặc lặp mãi?

### Dừng sớm khi chỉ dùng hasNextInt()

~~~java
while (scanner.hasNextInt()) {
    System.out.println(scanner.nextInt());
}
~~~

Đây là mảnh mã có biến `scanner` đã tạo sẵn. Với `"10 x 20"`, nó chỉ in `10`. Khi gặp `x`, điều kiện trả `false` và vòng lặp dừng; `20` vẫn chưa được xử lý.

Mẫu này đúng nếu yêu cầu là “đọc dãy số nguyên liên tiếp ở đầu nguồn”. Nó không đúng nếu người viết tưởng rằng vòng lặp sẽ tự bỏ mọi token không phải số.

### Lặp mãi vì không tiêu thụ token

~~~java
while (scanner.hasNext()) {
    if (scanner.hasNextInt()) {
        System.out.println(scanner.nextInt());
    }
}
~~~

Đây là **mảnh mã sai cố ý**, không nên chạy với đầu vào có token như `x`. `hasNext()` trả `true`, `hasNextInt()` trả `false`, thân vòng lặp không đọc gì, và vòng sau lại nhìn đúng token đó.

Mỗi đường đi tiếp tục của vòng lặp phải làm một việc giúp tiến triển: tiêu thụ dữ liệu, đổi trạng thái theo chính sách hợp lệ hoặc thoát. Với ví dụ bỏ qua token sai, nhánh `else` cần gọi `scanner.next()` như trong `ScannerRecoveryDemo`.

Một lỗi tương tự:

~~~java
while (scanner.hasNextInt()) {
    System.out.println("Found an integer");
}
~~~

Đây cũng là **mảnh mã sai cố ý**: thông báo được in liên tục vì không gọi `nextInt()`.

## 7. Locale và cơ số là một phần của hợp đồng đầu vào

### Locale quyết định quy ước biểu diễn số

Cùng dấu phẩy hoặc dấu chấm có thể mang ý nghĩa khác nhau giữa các locale. Không nên để một tệp dữ liệu có dấu chấm thập phân vô tình phụ thuộc cấu hình vùng của máy chạy.

Dùng `useLocale(...)` theo quy ước của đầu vào. Phải đặt trước cả bước kiểm tra lẫn bước đọc. Đổi locale giữa `hasNextDouble()` và `nextDouble()` có thể khiến điều vừa kiểm tra không còn phù hợp.

Đừng dùng `replace(",", ".")` như cách sửa chung cho mọi số: dấu phẩy có thể là dấu phân nhóm hoặc dấu phân cách trường, không chỉ là dấu thập phân.

### Cơ số quyết định cách đọc số nguyên

`nextInt(16)` đọc số nguyên cơ số 16; `nextInt(2)` đọc cơ số 2. Dùng cặp kiểm tra tương ứng, chẳng hạn `hasNextInt(16)` rồi `nextInt(16)`.

Các phương thức số nguyên `byte`, `short`, `int`, `long` và `BigInteger` có biến thể nhận cơ số. `useRadix(16)` đổi cơ số mặc định cho các phương thức số nguyên không truyền cơ số; một lần `nextInt(16)` chỉ dùng cơ số đó cho lời gọi ấy.

Cơ số hợp lệ nằm trong `Character.MIN_RADIX..Character.MAX_RADIX`, tức `2..36`. Không suy từ cú pháp literal Java sang dữ liệu Scanner: ví dụ đầu vào `ff` đọc được theo cơ số 16, còn không nên giả định `0xff`, `1_000` hay hậu tố `L` được xử lý như trong mã nguồn Java.

### Thí nghiệm chạy đầy đủ

Lưu thành `ScannerNumberConventionsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Scanner;

public class ScannerNumberConventionsDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("1,234.50")) {
            scanner.useLocale(Locale.US);
            BigDecimal value = scanner.nextBigDecimal();
            System.out.println("US=" + value.toPlainString());
        }

        try (Scanner scanner = new Scanner("1.234,50")) {
            scanner.useLocale(Locale.GERMANY);
            BigDecimal value = scanner.nextBigDecimal();
            System.out.println("DE=" + value.toPlainString());
        }

        try (Scanner scanner = new Scanner("ff 1010")) {
            System.out.println("hex?=" + scanner.hasNextInt(16));
            System.out.println("hex=" + scanner.nextInt(16));
            System.out.println("binary=" + scanner.nextInt(2));
            System.out.println("defaultRadix=" + scanner.radix());
        }

        try (Scanner scanner = new Scanner("0.10 0.20")) {
            scanner.useLocale(Locale.US);
            BigDecimal first = scanner.nextBigDecimal();
            BigDecimal second = scanner.nextBigDecimal();
            System.out.println("decimalSum="
                    + first.add(second).toPlainString());
        }
    }
}
~~~

~~~shell
javac --release 17 -encoding UTF-8 ScannerNumberConventionsDemo.java
java ScannerNumberConventionsDemo
~~~

Stdout chính xác:

~~~text
US=1234.50
DE=1234.50
hex?=true
hex=255
binary=10
defaultRadix=10
decimalSum=0.30
~~~

Hai quy ước biểu diễn khác nhau được chuyển thành cùng giá trị thập phân. Đọc một lần với cơ số 16 không làm `scanner.radix()` đổi từ 10 sang 16. Phép cộng cuối cùng đọc trực tiếp hai số thập phân vào `BigDecimal`.

## 8. Đọc thành công chưa đủ để chấp nhận dữ liệu

### Giá trị đặc biệt của số dấu phẩy động

Với `float`/`double`, cần lưu ý `NaN` và vô cực. Một token được phương thức đọc số thực chấp nhận chưa chắc phù hợp với yêu cầu “một số hữu hạn trong khoảng cho phép”.

Nếu đại lượng bắt buộc hữu hạn, sau khi đọc có thể kiểm tra:

~~~java
double value = scanner.nextDouble();
if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("A finite value is required");
}
~~~

Đây là mảnh mã trong phương thức có `scanner`, không phải chương trình độc lập. Sau kiểm tra hữu hạn, ứng dụng có thể còn cần giới hạn miền giá trị như `value >= 0`.

### hasNext() có thể chờ

Tên “has” không bảo đảm một phép kiểm tra tức thời. Với đầu vào tương tác hoặc luồng đang truyền dữ liệu, `hasNext()` và các phương thức liên quan có thể chặn để chờ đủ dữ liệu. Việc một lời gọi kiểm tra đã trả về không tạo ra một cam kết chung rằng mọi lời gọi tiếp theo đều không chặn. [Hợp đồng đọc của Scanner](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Scanner.html).

Không dùng chúng như phép thăm dò “bàn phím đã có gì chưa” trong một vòng lặp giao diện cần phản hồi liên tục.

### Lỗi I/O khác lỗi định dạng

Khi đọc từ tệp hoặc luồng, nguồn có thể gặp lỗi I/O. Scanner lưu lỗi đó ở `ioException()` và có thể biểu hiện như đã tới cuối nguồn. Nếu cần xác nhận toàn bộ dữ liệu đã được đọc thành công, kiểm tra lỗi nguồn sau vòng đọc; đừng chỉ dựa vào `hasNext() == false`.

Các chương trình dùng chuỗi ở trên nhằm cô lập hành vi phân tích token; chúng không thay thế việc xử lý lỗi mở/đọc tài nguyên trong ứng dụng thực tế.

### Không chia sẻ scanner để nhiều luồng cùng đọc

Nếu một luồng khác tiêu thụ token hoặc đổi cấu hình giữa bước kiểm tra và bước đọc, giả định về “token tiếp theo” có thể bị phá vỡ. Tổ chức một nơi chịu trách nhiệm đọc hoặc đồng bộ cả chuỗi thao tác cần nhất quán.

## 9. Quan hệ với nextLine()

`next()` và các phương thức đọc số làm việc theo token. `nextLine()` làm việc theo phần còn lại của dòng.

Với đầu vào `"12\nLan\n"`, sau `nextInt()`, phần còn lại của dòng chứa `12` là chuỗi rỗng. Một lần `nextLine()` ngay sau đó sẽ trả chuỗi rỗng ấy; nó không tự nhảy đến `Lan` theo ý người viết.

Nếu định dạng là mỗi trường nằm trọn trên một dòng, có thể đọc dòng rồi chuyển đổi theo quy tắc của trường. Nếu định dạng theo token, dùng nhất quán các phương thức token. Không thêm tùy tiện một `nextLine()` để “chữa” mọi chương trình: khi có dữ liệu có ý nghĩa ở cuối dòng, hành động đó có thể bỏ mất nó.

Phần cần nhớ ở đây là chọn phương thức theo **đơn vị dữ liệu**, không theo cảm giác tên phương thức.

## 10. Tự kiểm tra hiểu biết

1. Với đầu vào `"42"`, gọi `hasNextInt()` ba lần rồi `nextInt()` một lần. Dự đoán cả bốn kết quả và vị trí đọc sau mỗi bước.
2. Với `"10 bad 20"`, so sánh vòng lặp chỉ dùng `hasNextInt()` và vòng lặp phục hồi có nhánh `else`. Mẫu nào phù hợp nếu bản ghi phải bị từ chối ngay khi sai?
3. Với `"128"`, kiểm tra lần lượt `hasNextByte()`, `hasNextShort()` rồi đọc `nextShort()`. Giải thích vì sao các phép kiểm tra không lấy mất dữ liệu.
4. Sửa chương trình cơ số để dùng `useRadix(16)`. Đối chiếu `nextInt()`, `nextInt(2)` và giá trị `radix()` sau từng lời gọi.
5. Viết hàm đọc số lượng bắt buộc thuộc `1..100`. Phân biệt rõ ba lỗi: thiếu token, sai kiểu số nguyên và số nguyên ngoài khoảng nghiệp vụ.
6. Thử token `"NaN"` với `hasNextDouble()` rồi kiểm tra `Double.isFinite(...)`. Giải thích vì sao hợp lệ ở tầng phân tích chưa đủ ở tầng nghiệp vụ.

Khi thiết kế một lượt đọc, hãy xác định: token có tồn tại không, có khớp kiểu và cấu hình hiện tại không, ai tiêu thụ nó, và làm gì khi dữ liệu không hợp lệ.
