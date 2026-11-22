# ioException và lỗi đọc của nguồn trong Scanner

## 1. Vì sao vòng lặp dừng chưa chứng minh đã đọc thành công?

Một vòng lặp Scanner có thể kết thúc vì đã đọc hết nguồn. Nó cũng có thể kết thúc sau khi nguồn phát sinh lỗi I/O, chẳng hạn tệp không đọc tiếp được hoặc luồng kết nối bị gián đoạn.

Điểm cần biết: khi **Readable.read(...) của nguồn phát IOException**, Scanner ghi nhận ngoại lệ và xử lý nguồn như đã kết thúc. Các thao tác đọc thông thường không tự truyền nguyên IOException đó cho nơi gọi. Muốn biết lỗi nguồn đã xảy ra hay chưa, dùng **scanner.ioException()**.

Phương thức này trả về IOException gần nhất được ghi nhận từ nguồn, hoặc null nếu chưa có lỗi đó. Nó **không ném lỗi, không đọc thêm, không thử kết nối lại và không xóa trạng thái lỗi**.

Hợp đồng đọc và phương thức ioException được mô tả trong [Java SE 21 Scanner API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html#ioException()).

Có hai lớp trách nhiệm:

| Lớp | Trách nhiệm |
| --- | --- |
| Nguồn Readable/Reader | Cung cấp ký tự; có thể báo lỗi truy cập dữ liệu |
| Scanner | Tách token, đọc dòng và chuyển kiểu trên ký tự đã nhận |
| Ứng dụng | Kiểm tra kết thúc có thành công không; quyết định chấp nhận hay từ chối phần dữ liệu đã có |

Nếu đang nhập danh sách cấu hình, nhận được 40 dòng rồi mất nguồn không tương đương với một tệp chỉ có đúng 40 dòng. Kết quả có thể đúng cú pháp nhưng chưa đầy đủ.

## 2. Cách kiểm tra tối thiểu sau khi đọc

Đoạn minh họa sau nằm trong một phương thức có biến scanner; cần import java.io.IOException:

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

Điểm quyết định là kiểm tra **sau thao tác có thể yêu cầu đọc nguồn**, đặc biệt trước khi thông báo hoàn tất hoặc công bố kết quả.

Kiểm tra ioException() ngay sau khi tạo Scanner chỉ cho biết chưa có lỗi được ghi nhận ở thời điểm đó. Nhiều Scanner chưa cần đọc nguồn khi khởi tạo, nên null lúc này không đảm bảo các thao tác tiếp theo thành công.

Nếu tầng gọi đã có hợp đồng throws IOException, có thể truyền tiếp ngoại lệ đã ghi nhận. Nếu không muốn thêm ngoại lệ được kiểm tra vào chữ ký phương thức, UncheckedIOException là một cách bọc có giữ nguyên nguyên nhân. Không chỉ lấy getMessage() rồi bỏ đối tượng ngoại lệ, vì khi đó mất thông tin phục vụ chẩn đoán.

## 3. Bốn trường hợp không nên gộp chung

| Trường hợp | Dấu hiệu tiêu biểu | ioException có vai trò gì? |
| --- | --- | --- |
| Hết nguồn bình thường | Không còn token hoặc dòng | Thường null nếu không có lỗi nguồn trước đó |
| Token sai dạng | nextInt() phát InputMismatchException | Không đại diện cho lỗi chuyển kiểu |
| Yêu cầu đọc khi đã hết phần tử | next()/nextLine() phát NoSuchElementException | Có thể cần xem thêm để biết nguồn kết thúc do lỗi I/O hay bình thường |
| Nguồn gặp lỗi đọc | Nguồn phát IOException; Scanner có thể dừng như EOF | Cung cấp ngoại lệ nguồn đã được giữ lại |

InputMismatchException không làm ioException() tự xuất hiện. Sai kiểu dữ liệu và lỗi vận chuyển ký tự là hai vấn đề riêng.

Ngoài ra, lỗi **mở nguồn** và lỗi **đọc sau khi mở** khác nhau. Nếu Files.newBufferedReader(...) không mở được tệp, ngoại lệ phát tại bước mở Reader, trước khi có Scanner để hỏi ioException(). Phải xử lý lỗi tại đúng bước phát sinh.

ioException() trả null cũng không chứng minh dữ liệu đúng định dạng, đủ bản ghi hoặc có nội dung mong đợi. Muốn bảo đảm những điều đó phải kiểm tra hợp đồng dữ liệu riêng.

## 4. Dữ liệu trong bộ đệm có thể vẫn được trả về sau lỗi nguồn

Giả sử nguồn đã cung cấp:

```text
alpha\nbet
```

Sau đó nguồn phát IOException thay vì cung cấp phần còn lại của từ beta. Trong ký hiệu trên, \n là ký tự xuống dòng.

Scanner đã có ký tự trong bộ đệm, nên có thể trả dòng alpha và phần còn lại bet. Phần bet trông giống một dòng cuối không có dấu xuống dòng, nhưng thực chất nguồn đã hỏng khi dữ liệu còn dang dở.

Điều này dẫn đến hai kết luận:

1. Đọc được một token hoặc dòng không chứng minh toàn bộ nguồn đã được nhận đầy đủ.
2. Dòng cuối không có newline có thể hợp lệ khi EOF bình thường; không thể chỉ nhìn nội dung để phân biệt với một nguồn bị cắt. Cần kiểm tra trạng thái I/O và quy tắc bản ghi.

Không được cố đọc lại từ chính Scanner sau lỗi rồi mong nó tiếp tục lấy dữ liệu như chưa có chuyện gì. Scanner đã coi nguồn là kết thúc. Nếu nghiệp vụ cho phép thử lại, phải mở nguồn mới và thiết kế việc đọc lại tránh nhân đôi tác dụng đã thực hiện.

## 5. Chương trình đầy đủ: lỗi đọc và kết quả chỉ được chấp nhận sau kiểm tra

Chương trình sau có nguồn ControlledSource để chủ động tạo các tình huống:

- Cung cấp đủ ký tự rồi kết thúc bình thường.
- Cung cấp một phần ký tự rồi phát IOException khi đọc tiếp.
- Chỉ lỗi lúc đóng nguồn.
- Lỗi khi đọc và sau đó lỗi cả lúc đóng.

Hàm readAllChecked sở hữu nguồn được truyền vào và đóng nó. Hàm tích lũy dữ liệu cục bộ, chỉ trả kết quả khi đã kiểm tra xong. Các hàm xử lý nguồn dùng chung không nên tự sao chép hợp đồng sở hữu này nếu nơi gọi vẫn cần nguồn.

Lưu **IoExceptionDemo.java**. Cú pháp và API dùng được trên Java 17 trở lên.

```java
import java.io.Closeable;
import java.io.IOException;
import java.io.StringReader;
import java.nio.CharBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Scanner;

public class IoExceptionDemo {
    private static final class ControlledSource implements Readable, Closeable {
        private final String content;
        private final boolean failRead;
        private final boolean failClose;
        private int position;

        ControlledSource(String content, boolean failRead, boolean failClose) {
            this.content = content;
            this.failRead = failRead;
            this.failClose = failClose;
        }

        @Override
        public int read(CharBuffer target) throws IOException {
            if (!target.hasRemaining()) {
                return 0;
            }
            if (position < content.length()) {
                int count = Math.min(target.remaining(), content.length() - position);
                target.put(content, position, position + count);
                position += count;
                return count;
            }
            if (failRead) {
                throw new IOException("read failed");
            }
            return -1;
        }

        @Override
        public void close() throws IOException {
            if (failClose) {
                throw new IOException("close failed");
            }
        }
    }

    private static List<String> readAllChecked(Readable source) throws IOException {
        Scanner scanner = new Scanner(source);
        List<String> lines = new ArrayList<>();
        IOException readFailure;
        try (scanner) {
            while (scanner.hasNextLine()) {
                lines.add(scanner.nextLine());
            }
            readFailure = scanner.ioException();
        }

        IOException latestFailure = scanner.ioException();
        if (readFailure != null) {
            if (latestFailure != null && latestFailure != readFailure) {
                readFailure.addSuppressed(latestFailure);
            }
            throw readFailure;
        }
        if (latestFailure != null) {
            throw latestFailure;
        }
        return List.copyOf(lines);
    }

    private static void runCase(String label, Readable source) {
        try {
            List<String> lines = readAllChecked(source);
            System.out.println(label + ": accepted=" + lines);
        } catch (IOException ex) {
            System.out.println(label + ": rejected=" + ex.getMessage()
                    + "; suppressed=" + ex.getSuppressed().length);
        }
    }

    public static void main(String[] args) {
        try (Scanner scanner = new Scanner(
                new ControlledSource("alpha\nbet", true, false))) {
            while (scanner.hasNextLine()) {
                System.out.println("raw-line=[" + scanner.nextLine() + "]");
            }
            System.out.println("raw-io-error=" + (scanner.ioException() != null));
        }

        runCase("normal", new StringReader("alpha\nbeta\n"));
        runCase("read-error", new ControlledSource("alpha\nbet", true, false));
        runCase("close-error", new ControlledSource("alpha\nbeta\n", false, true));
        runCase("both-errors", new ControlledSource("alpha\nbet", true, true));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 IoExceptionDemo.java
java IoExceptionDemo
```

Kết quả:

```text
raw-line=[alpha]
raw-line=[bet]
raw-io-error=true
normal: accepted=[alpha, beta]
read-error: rejected=read failed; suppressed=0
close-error: rejected=close failed; suppressed=0
both-errors: rejected=read failed; suppressed=1
```

Các thông báo read failed và close failed do ControlledSource của ví dụ tạo, không phải thông báo nội bộ cố định của Scanner.

Ba dòng raw đầu tiên chỉ quan sát hành vi: Scanner có thể trả cả phần bet rồi mới cho ứng dụng kết luận nguồn không hợp lệ qua ioException. Hàm readAllChecked không chấp nhận danh sách đó như một kết quả đọc thành công.

ControlledSource tôn trọng dung lượng CharBuffer được cấp: mỗi lần chỉ ghi tối đa số ký tự còn chỗ, trả số ký tự đã ghi, trả -1 khi kết thúc bình thường. Chỉ nhánh mô phỏng lỗi mới phát IOException. Nó giúp kiểm tra lỗi nguồn mà không cần phá kết nối thật hay tạo tệp hỏng.

## 6. Vì sao chương trình giữ lỗi trước khi đóng?

Scanner triển khai close() mà không khai báo throws IOException. Khi đóng một nguồn Closeable và nguồn phát IOException, Scanner giữ ngoại lệ đó làm lỗi gần nhất; nó có thể thay lỗi đọc đã được ghi trước đó.

Hành vi này và việc ioException() vẫn trả trạng thái đã lưu được thể hiện trong [mã nguồn OpenJDK 21 của Scanner](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/classes/java/util/Scanner.java).

Vì vậy readAllChecked làm theo thứ tự:

1. Đọc đến khi vòng lặp kết thúc.
2. Lưu lỗi đọc vào readFailure **trước close**.
3. Để try-with-resources đóng Scanner và nguồn.
4. Xem lỗi gần nhất sau đóng.
5. Ưu tiên lỗi đọc nếu có; thêm lỗi đóng khác biệt vào danh sách suppressed của lỗi đọc.
6. Chỉ trả danh sách khi không có lỗi thuộc hai giai đoạn đó.

Nếu lỗi đọc và lỗi đóng cùng xảy ra, đối tượng lỗi đọc vẫn là nguyên nhân chính. Nhánh kiểm tra latestFailure != readFailure tránh tự thêm một ngoại lệ vào chính danh sách suppressed của nó.

Trong ví dụ, việc thêm lỗi phụ là trách nhiệm của hàm readAllChecked. Không được suy luận try-with-resources tự tạo lỗi phụ này khi Scanner.close đã giữ IOException bên trong.

Đây là phần mở rộng khi cần kiểm tra cả vòng đời nguồn. Nếu chỉ quan tâm lỗi đọc, tối thiểu phải lưu và xử lý ioException sau vòng lặp, trước khi kết luận thành công. Không cần tự viết lại toàn bộ bộ quản lý nguồn cho mọi bài tập nhỏ.

Hàm trong ví dụ tập trung vào I/O khi quét và đóng, không phải khuôn bao bắt mọi RuntimeException có thể xảy ra trong mã xử lý dòng. Nếu bổ sung bộ phân tích riêng có thể phát lỗi, hãy giữ nguyên nguyên nhân chính và thiết kế việc báo nhiều lỗi phù hợp với hợp đồng của ứng dụng.

## 7. Áp dụng khi đọc tệp thật

Bên trong một lớp có hàm readAllChecked tương ứng, có thể mở Reader bằng charset rõ ràng:

```java
java.nio.file.Path path = java.nio.file.Path.of("input.txt");
List<String> lines = readAllChecked(
        java.nio.file.Files.newBufferedReader(
                path, java.nio.charset.StandardCharsets.UTF_8));
```

Đây là đoạn tích hợp, không phải một chương trình độc lập. Phương thức chứa nó cần khai báo throws IOException hoặc xử lý ngoại lệ.

Reader do đoạn này tạo được chuyển quyền sở hữu cho readAllChecked, nên hàm đó đóng Reader thông qua Scanner. Lỗi mở tệp phát trực tiếp từ newBufferedReader; lỗi đọc sau đó được kiểm tra qua ioException. Chọn charset rõ ràng giúp hợp đồng giải mã nhất quán, nhưng vẫn phải kiểm tra lỗi đọc và nội dung.

Với tệp nhỏ, giữ danh sách cục bộ đến khi xác nhận thành công thường đơn giản. Với tệp lớn, giữ toàn bộ trong bộ nhớ có thể không phù hợp. Có thể xử lý theo lô, ghi vào vùng tạm hoặc dùng giao dịch, nhưng phải quyết định trước cách ứng xử khi nguồn hỏng giữa chừng.

## 8. Tác dụng bên ngoài và giới hạn của việc thử lại

Nếu mỗi dòng đọc được lập tức tạo một bản ghi trong cơ sở dữ liệu hoặc gửi một yêu cầu ra ngoài, phát hiện ioException cuối cùng không tự hoàn tác các tác dụng trước đó.

Tùy nghiệp vụ, chọn một trong các cách:

- Tích lũy và kiểm tra trước khi công bố kết quả nếu dữ liệu đủ nhỏ.
- Dùng giao dịch hoặc vùng nhập tạm, chỉ chuyển trạng thái thành hoàn tất khi toàn bộ nguồn được xác nhận.
- Cho phép nhập từng phần nhưng lưu rõ trạng thái chưa hoàn tất và vị trí tiếp tục.
- Thiết kế thao tác có tính lặp lại an toàn trước khi mở lại nguồn để thử lại.

Không tự khởi động lại việc đọc sau mọi IOException. Mất quyền truy cập, sai đường dẫn, nguồn không tồn tại hoặc lỗi bền vững không được sửa bằng vòng lặp thử vô hạn. Chỉ thử lại khi loại lỗi và hợp đồng nguồn cho phép, có giới hạn và kiểm soát dữ liệu đã xử lý.

## 9. Lỗi thường gặp

| Cách làm | Vì sao chưa đủ |
| --- | --- |
| Chỉ catch IOException quanh scanner.nextLine() | IOException của Readable có thể đã được Scanner giữ bên trong |
| Chỉ kiểm tra ioException trước khi đọc | Lỗi có thể phát sinh ở lần đọc sau |
| Thấy hasNextLine false rồi báo hoàn tất | Nguồn lỗi cũng có thể khiến việc quét kết thúc |
| Thấy ioException null rồi kết luận bản ghi đúng | Trạng thái I/O không thay kiểm tra định dạng, số trường hay nội dung |
| Chỉ xem lỗi sau close | Có thể làm mất nhận diện lỗi đọc trước đó nếu close ghi lỗi mới |
| Gọi reset() để thử sửa nguồn lỗi | Đổi cấu hình Scanner không khôi phục nguồn đã bị coi là kết thúc |
| Bắt Exception rồi trả danh sách hiện có | Che lỗi và dễ biến dữ liệu thiếu thành kết quả thành công |
| Đóng Scanner bọc nguồn dùng chung trong hàm con | Có thể đóng cả nguồn mà nơi gọi vẫn cần dùng |

Nếu API ứng dụng dùng kết quả có cấu trúc thay vì ném ngoại lệ, kết quả phải phân biệt thành công, lỗi nguồn và dữ liệu một phần. Không trả một danh sách trần giống hệt nhau cho cả ba trạng thái.

## 10. Thực hành

1. Đổi nội dung của nhánh read-error thành chuỗi rỗng và giữ failRead=true. Không có dòng nào được cung cấp, nhưng readAllChecked vẫn phải từ chối do lỗi đọc, không coi là tệp rỗng hợp lệ.
2. Giữ nội dung "alpha\nbet" nhưng đặt failRead=false và failClose=false. Hai dòng có thể được chấp nhận vì dòng cuối không bắt buộc có dấu xuống dòng.
3. Giữ failRead=true, đổi nội dung thành "alpha\nbeta\n". Dù các dòng có vẻ hoàn chỉnh, hàm vẫn phải báo lỗi vì nguồn không xác nhận kết thúc bình thường.
4. Với both-errors, in ex.getSuppressed()[0].getMessage(). Giá trị phải là close failed; lỗi chính vẫn là read failed.
5. Bỏ bước kiểm tra readFailure trong một bản thử nghiệm riêng và quan sát nguy cơ chấp nhận bet như dữ liệu thành công. Sau đó khôi phục kiểm tra trước khi dùng mã vào ứng dụng.

Điểm cần tự kiểm tra là thời điểm ứng dụng tuyên bố hoàn tất: phải sau thao tác đọc cần thiết, sau kiểm tra lỗi nguồn và sau kiểm tra hợp đồng dữ liệu. Đọc được một phần văn bản chỉ là bằng chứng đã nhận được phần đó.
