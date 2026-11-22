# NoSuchElementException và cuối nguồn dữ liệu trong Scanner

## 1. Hết dữ liệu là một trạng thái bình thường

Mọi nguồn dữ liệu hữu hạn đều có điểm kết thúc: chuỗi đã đọc hết, tệp đến cuối hoặc luồng đầu vào đã đóng phía cung cấp. Trạng thái này thường gọi là **cuối nguồn (end of input, EOF)**.

EOF không tự động là lỗi. Một vòng lặp đọc các dòng của tệp có thể kết thúc bình thường khi không còn dòng. Nhưng nếu định dạng yêu cầu ba số mà nguồn chỉ cung cấp hai số, EOF xuất hiện trước khi bản ghi hoàn chỉnh và trở thành lỗi thiếu dữ liệu của ứng dụng.

**NoSuchElementException** phát sinh khi yêu cầu Scanner trả về một phần tử không còn tồn tại, chẳng hạn gọi next() khi không còn token hoặc nextLine() khi không còn dòng. Cách xử lý tốt bắt đầu từ câu hỏi: **phần tử tiếp theo là tùy chọn hay bắt buộc theo định dạng?**

| Tình huống | Ý nghĩa với ứng dụng |
| --- | --- |
| Đọc các dòng cho đến hết tệp | EOF là điểm kết thúc tự nhiên |
| Đọc một bản ghi bắt buộc còn thiếu trường | EOF là lỗi bản ghi chưa đầy đủ |
| Người dùng chủ động kết thúc luồng nhập | Có thể là thao tác hủy hoặc kết thúc theo giao diện |
| Nguồn phát sinh lỗi I/O | Phải phân biệt với kết thúc thành công |

Các cơ chế đọc và thông tin lỗi nguồn được quy định trong [Java SE 21 Scanner API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html).

## 2. Ghép đúng phép kiểm tra với thao tác đọc

Đọc từng token:

```java
while (scanner.hasNext()) {
    String token = scanner.next();
    // Xu ly token.
}
```

Đọc từng dòng:

```java
while (scanner.hasNextLine()) {
    String line = scanner.nextLine();
    // Xu ly line, ke ca dong rong neu dinh dang cho phep.
}
```

Đây là các đoạn minh họa bên trong phương thức có biến scanner. **hasNext() và hasNextLine() không tiêu thụ phần tử**; thao tác next hoặc nextLine mới tiến vị trí đọc.

Không ghép hasNext() với nextLine() như một quy tắc chung. Với nguồn chỉ chứa ba dấu cách và delimiter mặc định:

- hasNext() trả false vì không có token không phải delimiter.
- hasNextLine() trả true vì vẫn có phần dòng chứa ba dấu cách.
- nextLine() trả chuỗi dài 3.

Vòng lặp đọc dòng nhưng dùng hasNext() có thể bỏ sót các dòng cuối chỉ chứa khoảng trắng. Chọn phép kiểm tra theo đơn vị dữ liệu cần đọc.

### hasNextInt() trả false chưa chứng minh đã hết nguồn

Có hai nguyên nhân thông thường:

1. Không còn token.
2. Có token nhưng nó không thể chuyển thành int theo cấu hình hiện tại hoặc nằm ngoài phạm vi int.

Muốn phân biệt hai trường hợp, kiểm tra hasNext() trước, rồi hasNextInt(). Một vòng lặp while (hasNextInt()) có thể dừng ngay tại chữ sai ở giữa nguồn và để lại toàn bộ phần sau chưa đọc.

## 3. Phân biệt các loại ngoại lệ

| Ngoại lệ | Trường hợp tiêu biểu | Hướng xử lý |
| --- | --- | --- |
| NoSuchElementException | Yêu cầu token/dòng khi không còn phần tử | Kết thúc hoặc báo trường bắt buộc bị thiếu |
| InputMismatchException | Token còn tồn tại nhưng không phù hợp kiểu cần đọc | Báo sai dạng, sửa dữ liệu hoặc phục hồi theo định dạng |
| IllegalStateException | Scanner đã đóng mà vẫn yêu cầu đọc | Sửa quản lý vòng đời nguồn |
| IOException từ nguồn | Nguồn không đọc được trong quá trình quét | Kiểm tra scanner.ioException(), báo lỗi nguồn |

**InputMismatchException kế thừa NoSuchElementException.** Do đó catch (NoSuchElementException ...) cũng bắt lỗi sai dạng. Nếu muốn phân loại riêng, bắt InputMismatchException trước:

```java
try {
    int value = scanner.nextInt();
    // Su dung value.
} catch (InputMismatchException ex) {
    // Con token nhung token khong phu hop int.
} catch (NoSuchElementException ex) {
    // Khong con token de doc.
}
```

Đảo thứ tự hai nhánh catch sẽ khiến nhánh dành cho lớp con không thể chạy và bị trình biên dịch từ chối. Quan hệ kế thừa này được xác nhận trong [Java SE 21 InputMismatchException API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/InputMismatchException.html).

Sau InputMismatchException, Scanner không tự đi qua token gây lỗi. Nếu bắt ngoại lệ rồi đọc lại y hệt mà không tiến vị trí, vòng lặp có thể lặp mãi trên cùng token sai. Việc bỏ một token hay bỏ cả dòng phải dựa trên cấu trúc dữ liệu, không thực hiện tùy tiện.

## 4. Dòng rỗng khác không còn dòng

Ba nguồn dưới đây khác nhau:

| Nguồn String trong mã Java | Cách đọc theo dòng |
| --- | --- |
| "" | Không có dòng để trả về |
| "\n" | Có một dòng rỗng; sau đó không còn dòng |
| "last line" | Có một dòng cuối dù không có dấu xuống dòng |

Không yêu cầu tệp phải có dấu xuống dòng cuối thì nextLine() mới trả được nội dung dòng cuối. Với "last line", lần đọc đầu trả chuỗi đó; lần đọc kế tiếp khi đã cạn nguồn mới gây NoSuchElementException.

Tương tự, một token số cuối nguồn vẫn có thể được đọc thành công mà không cần dấu cách phía sau. EOF giúp xác định kết thúc token. Không được kết luận “không có newline cuối” đồng nghĩa “không có dữ liệu”.

Một chuỗi rỗng trả về bởi nextLine() là một giá trị đã đọc được. Nó không phải ký hiệu EOF. Nếu dòng rỗng bị cấm, đó là quy tắc kiểm tra nội dung riêng.

## 5. Đọc trường bắt buộc và phát hiện bản ghi bị cắt

Giả sử định dạng là:

```text
<count> <value[0]> <value[1]> ... <value[count - 1]>
```

Đầu vào «3 10 20 30» hợp lệ. Đầu vào «3 10 20» thiếu value[2]. Không nên im lặng chấp nhận tổng 30 như thể đã đọc xong một bản ghi hợp lệ.

Hàm requiredInt trong chương trình sau thực hiện hai kiểm tra:

1. Có token hay không: thiếu thì phát NoSuchElementException có tên trường.
2. Token có đọc thành int được không: sai thì phát InputMismatchException có tên trường.

sumRecord còn kiểm tra count trong khoảng minh họa 0..1000 và từ chối dữ liệu thừa. Đây là hợp đồng của ví dụ, không phải hạn chế của Scanner. Math.addExact giúp phát hiện tràn tổng bằng ArithmeticException thay vì âm thầm cuộn giá trị int.

## 6. Chương trình hoàn chỉnh có thể chạy lại

Lưu **ScannerEndDemo.java**. Chương trình dùng String và một nguồn Readable mô phỏng lỗi, nên không phụ thuộc nhập bàn phím hay tệp bên ngoài. Cú pháp và API dùng được trên Java 17 trở lên.

```java
import java.io.IOException;
import java.nio.CharBuffer;
import java.util.InputMismatchException;
import java.util.NoSuchElementException;
import java.util.Scanner;

public class ScannerEndDemo {
    private static int requiredInt(Scanner scanner, String field) {
        if (!scanner.hasNext()) {
            throw new NoSuchElementException("Missing " + field);
        }
        if (!scanner.hasNextInt()) {
            throw new InputMismatchException("Invalid " + field);
        }
        return scanner.nextInt();
    }

    private static int sumRecord(String input) {
        try (Scanner scanner = new Scanner(input)) {
            int count = requiredInt(scanner, "count");
            if (count < 0 || count > 1000) {
                throw new IllegalArgumentException("Invalid count range");
            }
            int sum = 0;
            for (int i = 0; i < count; i++) {
                sum = Math.addExact(sum, requiredInt(scanner, "value[" + i + "]"));
            }
            if (scanner.hasNext()) {
                throw new IllegalArgumentException("Unexpected extra data");
            }
            return sum;
        }
    }

    private static final class BrokenReadable implements Readable {
        private boolean delivered;

        @Override
        public int read(CharBuffer target) throws IOException {
            if (!delivered) {
                target.put("7 ");
                delivered = true;
                return 2;
            }
            throw new IOException("simulated read failure");
        }
    }

    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("")) {
            try {
                scanner.next();
            } catch (NoSuchElementException ex) {
                System.out.println("empty-next=" + ex.getClass().getSimpleName());
            }
        }

        try (Scanner scanner = new Scanner("last line")) {
            System.out.println("last=[" + scanner.nextLine() + "]");
            System.out.println("more-lines=" + scanner.hasNextLine());
            try {
                scanner.nextLine();
            } catch (NoSuchElementException ex) {
                System.out.println("after-last=" + ex.getClass().getSimpleName());
            }
        }

        try (Scanner scanner = new Scanner("   ")) {
            System.out.println("spaces-has-token=" + scanner.hasNext());
            System.out.println("spaces-has-line=" + scanner.hasNextLine());
            System.out.println("spaces-line-length=" + scanner.nextLine().length());
        }

        try (Scanner scanner = new Scanner("\n")) {
            System.out.println("blank-has-line=" + scanner.hasNextLine());
            System.out.println("blank-line=[" + scanner.nextLine() + "]");
            System.out.println("blank-more-lines=" + scanner.hasNextLine());
        }

        try (Scanner scanner = new Scanner("wrong")) {
            try {
                scanner.nextInt();
            } catch (InputMismatchException ex) {
                System.out.println("bad-int=" + ex.getClass().getSimpleName());
                System.out.println("retained=[" + scanner.next() + "]");
            }
        }

        System.out.println("record-sum=" + sumRecord("3 10 20 30"));
        try {
            sumRecord("3 10 20");
        } catch (InputMismatchException ex) {
            System.out.println("record-invalid=" + ex.getMessage());
        } catch (NoSuchElementException ex) {
            System.out.println("record-missing=" + ex.getMessage());
        }

        try (Scanner scanner = new Scanner(new BrokenReadable())) {
            System.out.println("partial-value=" + scanner.nextInt());
            System.out.println("partial-more=" + scanner.hasNext());
            IOException failure = scanner.ioException();
            System.out.println("io-failure=" + (failure != null));
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 ScannerEndDemo.java
java ScannerEndDemo
```

Kết quả:

```text
empty-next=NoSuchElementException
last=[last line]
more-lines=false
after-last=NoSuchElementException
spaces-has-token=false
spaces-has-line=true
spaces-line-length=3
blank-has-line=true
blank-line=[]
blank-more-lines=false
bad-int=InputMismatchException
retained=[wrong]
record-sum=60
record-missing=Missing value[2]
partial-value=7
partial-more=false
io-failure=true
```

Dấu ngoặc vuông được thêm khi in để nhìn thấy dòng rỗng và khoảng trắng. Chương trình in tên lớp ngoại lệ cho các lỗi do Scanner tạo; không dựa vào thông báo lỗi nội bộ vì không nên coi câu chữ thông báo là giao diện ổn định.

Các dòng record-missing chứa thông báo do chính requiredInt tạo. Chỉ số 2 là phần tử thứ ba vì chỉ số mảng và vòng lặp bắt đầu từ 0.

## 7. Lỗi đọc nguồn có thể trông giống EOF

BrokenReadable cung cấp trước chuỗi «7 », sau đó phát IOException khi Scanner yêu cầu thêm dữ liệu. Trong ví dụ:

1. nextInt() vẫn nhận được số 7 đã có đủ ranh giới token.
2. hasNext() thử đọc tiếp và trả false sau khi nguồn báo lỗi.
3. ioException() khác null, cho biết có lỗi I/O.

Vì vậy, **đọc đến lúc hasNext() trả false chưa đủ để tuyên bố tệp đã được xử lý thành công** nếu nguồn có thể lỗi trong lúc đọc. Với nhập tệp hoặc luồng, kiểm tra ioException() khi kết thúc:

```java
while (scanner.hasNextLine()) {
    String line = scanner.nextLine();
    // Xu ly line.
}
IOException failure = scanner.ioException();
if (failure != null) {
    throw new java.io.UncheckedIOException("Cannot finish reading input", failure);
}
```

Đoạn minh họa cần import java.io.IOException và biến scanner đã được tạo. Ứng dụng có thể truyền tiếp IOException theo chữ ký phương thức hoặc bọc bằng UncheckedIOException như trên.

Nếu việc xử lý có tác dụng bên ngoài, phải xác định thêm điều gì xảy ra với phần đã xử lý trước lỗi: giữ phần thành công, đánh dấu nhập chưa hoàn tất hay chỉ công bố sau khi kiểm tra cả nguồn. Không tự báo “hoàn tất” chỉ vì vòng lặp đã dừng.

Lỗi mở tệp ngay khi tạo Scanner là một bước khác với lỗi phát sinh trong quá trình đọc. Nó phải được xử lý tại bước mở nguồn; ioException() không thay thế việc xử lý lỗi khởi tạo.

sumRecord trong chương trình chỉ nhận String cố định, nên không có lỗi I/O nền trong nguồn đó. Nếu chuyển hàm sang nhận Scanner của một tệp, cần đưa việc kiểm tra lỗi nguồn vào hợp đồng kết quả.

## 8. EOF, đang chờ dữ liệu và nguồn đã đóng

### 8.1. Đang chờ không đồng nghĩa hết dữ liệu

Với System.in hoặc nguồn có thể tiếp tục cung cấp dữ liệu, hasNext() và hasNextLine() có thể chờ. Không thấy kết quả ngay không có nghĩa phương thức đang lặp vô hạn hoặc đã trả false.

Nhấn Enter tạo ranh giới dòng. Nó không mặc nhiên kết thúc toàn bộ luồng nhập. Nếu một chương trình đọc mọi dòng cho đến EOF, nó có thể tiếp tục chờ dòng sau sau khi đã xử lý dòng hiện tại.

Không dùng InputStream.available() làm phép thử EOF hay thay thế hasNext(): số byte có thể đọc ngay và việc nguồn đã kết thúc là hai thông tin khác nhau.

### 8.2. Scanner đóng là lỗi vòng đời

EOF là trạng thái của nguồn đang được đọc; close() là hành động kết thúc quyền sử dụng Scanner. Khi đã đóng Scanner mà tiếp tục đọc, kết quả thông thường là IllegalStateException, không phải một cách biểu diễn EOF bằng NoSuchElementException.

Với một nguồn đã cạn, tạo một Scanner mới trên **cùng luồng đang ở cuối** không làm dữ liệu cũ xuất hiện trở lại. Muốn đọc lại một tệp cần mở nguồn mới; muốn quét lại String có thể tạo Scanner từ chính String đó.

Scanner có thể đóng cả nguồn mà nó bọc nếu nguồn hỗ trợ đóng. Vì vậy hàm nhận Scanner do bên ngoài truyền vào thường không tự đóng nó. Nơi tạo và sở hữu nguồn chịu trách nhiệm vòng đời, đặc biệt với System.in dùng chung.

## 9. Những cách xử lý dễ che lỗi

- **Bắt mọi NoSuchElementException rồi coi là kết thúc thành công:** có thể nuốt cả InputMismatchException hoặc che việc thiếu trường bắt buộc.
- **Dùng hasNextInt làm điều kiện duy nhất rồi thông báo “đã đọc hết”:** có thể dừng tại token chữ, không phải EOF.
- **Gọi nextLine để dọn dữ liệu sau bất kỳ lỗi nào:** có thể loại bỏ các trường hợp lệ còn lại cùng dòng.
- **Bắt lỗi nhưng không tiến vị trí:** đọc lại token sai mãi.
- **Dùng vòng lặp while(true) chỉ chờ ngoại lệ:** làm lẫn kết thúc bình thường và lỗi dữ liệu khi một phép kiểm tra trực tiếp đã đủ rõ.
- **Không kiểm tra ioException trên nguồn tệp/luồng:** có thể chấp nhận dữ liệu bị cắt do lỗi đọc.
- **Coi dòng rỗng là EOF:** làm mất bản ghi rỗng có ý nghĩa hoặc dừng quá sớm.

Dùng phép kiểm tra để điều khiển trường hợp kết thúc bình thường. Dùng thông báo lỗi có ngữ cảnh khi bản ghi bắt buộc chưa hoàn chỉnh. Hai việc này có thể cùng xuất hiện trong một bộ đọc.

## 10. Thực hành

1. Thay đầu vào hợp lệ của sumRecord bằng "0". Kết quả phải là 0 vì không có phần tử cần đọc.
2. Thay bằng "3 10 wrong 30". Lỗi phải được phân loại là InputMismatchException ở value[1], không phải thiếu dữ liệu.
3. Thay bằng "2 10 20 30". Hàm phải từ chối dữ liệu thừa sau hai giá trị.
4. Thay bằng "3 10 20". Xác nhận thông báo thiếu value[2]; không trả tổng của một phần bản ghi.
5. Thay nguồn dòng cuối bằng "last line\n". Đọc một dòng thành công rồi kết thúc; không tự suy ra một dòng rỗng bổ sung sau dấu xuống dòng cuối.
6. Thay BrokenReadable bằng new java.io.StringReader("7 "). Sau khi đọc hết, ioException() phải là null, giúp phân biệt kết thúc bình thường với nguồn mô phỏng lỗi.

Một bộ đọc đáng tin cậy phải phân biệt được: không còn phần tử, còn dữ liệu sai dạng, bản ghi thiếu trường, nguồn lỗi I/O và đối tượng đã đóng. Khi các trạng thái này được xử lý rõ ràng, NoSuchElementException trở thành dấu hiệu có thể chẩn đoán thay vì một lỗi cần bắt rồi bỏ qua.
