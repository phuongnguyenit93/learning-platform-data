# Scanner: khả năng chặn khi chờ dữ liệu

## 1. Vì sao chương trình có vẻ đứng yên?

Một chương trình chạy đến `scanner.nextInt()` rồi không in gì tiếp chưa chắc đã bị lỗi hoặc rơi vào vòng lặp vô hạn. Nó có thể đang **chờ đầu vào**.

Một thao tác đọc có tính chặn (blocking) khi luồng thực thi chưa thể đi tiếp cho đến khi nguồn cung cấp đủ dữ liệu, báo kết thúc hoặc báo lỗi. Trong khoảng chờ ấy, các câu lệnh phía sau lời gọi chưa được thực hiện.

Với Scanner, cần phân biệt ba điều:

1. Nguồn hiện đã cung cấp byte hoặc ký tự nào chưa?
2. Scanner đã xác định được token/dòng cần đọc chưa?
3. Nguồn đã kết thúc hẳn chưa?

Có một ít ký tự chưa chắc đã đủ trả về một token hoàn chỉnh. Không có dữ liệu ở thời điểm hiện tại cũng chưa chắc là hết nguồn.

Bài dùng Java 17 trở lên và API hiện hành. Trọng tâm là hiểu việc chờ dữ liệu để tổ chức lượt đọc đúng, không phải xây dựng một thư viện I/O bất đồng bộ.

## 2. Hai tầng có thể làm Scanner phải chờ

~~~text
Nguồn dữ liệu
  -> đọc byte / ký tự
  -> bộ đệm của Scanner
  -> nhận diện dấu phân cách / kết thúc dòng / EOF
  -> trả token hoặc giá trị số cho chương trình
~~~

### Tầng nguồn

`System.in`, một reader nối với pipe hoặc một luồng mạng có thể chưa nhận được dữ liệu tiếp theo. Scanner gọi đọc ở nguồn và phải chờ.

Một tệp thông thường có giới hạn kết thúc; một `String` đã có trọn nội dung trong bộ nhớ. Hai nguồn này thường dễ tạo ví dụ kết thúc hơn đầu vào tương tác hoặc một luồng còn mở.

Không nên suy ra mọi nguồn được gọi là “tệp” đều nhanh như nhau: việc truy cập đĩa, hệ thống tệp từ xa hoặc một đối tượng đặc biệt vẫn có thể tốn thời gian. Cần tách chuyện chờ I/O khỏi chuyện chờ ranh giới của văn bản.

### Tầng phân tích

Giả sử nguồn còn mở và mới gửi:

~~~text
12
~~~

Nếu chưa có dấu phân cách hay tín hiệu kết thúc, dữ liệu sau đó có thể là `"3 "`, tạo thành token `123`. Scanner không thể tùy ý coi mọi lần nguồn trả về một nhóm ký tự là một token hoàn chỉnh.

Với dấu phân cách mặc định, gửi thêm khoảng trắng có thể xác định kết thúc token. Với dấu phân cách tự cấu hình, dấu kết thúc thích hợp phải tuân theo chính cấu hình đó.

`flush()` đẩy dữ liệu đang được đệm ở phía ghi xuống nguồn kế tiếp; nó không tự chèn khoảng trắng, xuống dòng hoặc EOF. “Đã flush” không đồng nghĩa với “bản tin đã hoàn chỉnh”.

## 3. hasNext không phải phép thăm dò tức thời

Tên `hasNext()` dễ khiến người học nghĩ đây là một câu hỏi không chờ: “hiện tại có gì để đọc không?”. Thực tế, Scanner có thể phải đọc thêm để trả lời.

Nhóm `hasNext...` không tiêu thụ token nhưng vẫn có thể thực hiện I/O và chặn. Nhóm `next...` cũng có thể chặn. Không có cam kết chung rằng một lời gọi kiểm tra đã trả về sẽ làm lời gọi đọc đi kèm không chặn. [Hợp đồng chặn của Scanner](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Scanner.html).

Đặc biệt, một phép kiểm tra có thể biết đã có token bắt đầu mà lời gọi đọc vẫn cần xác định điểm kết thúc token. Vì vậy:

~~~java
if (scanner.hasNext()) {
    String token = scanner.next();
}
~~~

Đây là mảnh mã trong phương thức có `Scanner scanner`, không phải chương trình độc lập. Nó giúp tránh đọc token khi nguồn đã kết thúc, nhưng **không biến scanner thành API không chặn**.

Tương tự, không dùng `hasNextInt()` như cách bảo đảm “nếu chưa nhập xong thì trả false ngay”. `false` liên quan đến việc token không đọc được thành `int` hoặc không còn token, không phải một thông báo chung rằng người dùng đang tạm ngừng gõ.

## 4. Thí nghiệm có điều khiển: có dữ liệu vẫn có thể cần chờ

Chương trình sau dùng `PipedWriter` để chủ động gửi dữ liệu vào `PipedReader`. Scanner được một luồng duy nhất sở hữu. Luồng chính chỉ ghi đầu vào và quan sát kết quả qua các đối tượng đồng bộ.

Có bốn bước:

1. Bên đọc đã yêu cầu đọc nhưng bên ghi chưa gửi gì: `hasNext()` đang chờ.
2. Bên ghi gửi `hello`, chưa có dấu phân cách: trong thí nghiệm này `hasNext()` trả `true`.
3. `next()` cần đọc thêm trong khi nguồn còn mở: vẫn chưa trả token.
4. Bên ghi gửi một khoảng trắng: scanner xác định được token `hello` và trả về.

Lớp `ObservedReader` chỉ ghi nhận lúc yêu cầu đọc thứ nhất và thứ hai bắt đầu. Các latch giúp kiểm tra thứ tự sự kiện; chương trình không đoán trạng thái bằng cách `sleep` một khoảng thời gian rồi hy vọng luồng đã chạy tới đó.

Lưu thành `ScannerBlockingDemo.java`:

~~~java
import java.io.IOException;
import java.io.PipedReader;
import java.io.PipedWriter;
import java.io.Reader;
import java.util.Scanner;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ScannerBlockingDemo {
    private static final class ObservedReader extends Reader {
        private final Reader source;
        private final CountDownLatch firstRead = new CountDownLatch(1);
        private final CountDownLatch secondRead = new CountDownLatch(1);
        private int calls;

        private ObservedReader(Reader source) {
            this.source = source;
        }

        @Override
        public int read(char[] target, int offset, int length)
                throws IOException {
            calls++;
            if (calls == 1) {
                firstRead.countDown();
            } else if (calls == 2) {
                secondRead.countDown();
            }
            return source.read(target, offset, length);
        }

        @Override
        public void close() throws IOException {
            source.close();
        }
    }

    private static void await(CountDownLatch signal) throws Exception {
        if (!signal.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Expected read did not start");
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CompletableFuture<Boolean> hasToken = new CompletableFuture<>();

        try (PipedReader pipe = new PipedReader();
             PipedWriter producer = new PipedWriter(pipe)) {
            ObservedReader observed = new ObservedReader(pipe);

            Future<String> token = executor.submit(() -> {
                try (Scanner scanner = new Scanner(observed)) {
                    hasToken.complete(scanner.hasNext());
                    return scanner.next();
                }
            });

            await(observed.firstRead);
            System.out.println("hasNextInitiallyWaiting="
                    + !hasToken.isDone());

            producer.write("hello");
            producer.flush();
            System.out.println("hasNext="
                    + hasToken.get(5, TimeUnit.SECONDS));

            await(observed.secondRead);
            System.out.println("nextStillWaiting=" + !token.isDone());

            producer.write(" ");
            producer.flush();
            System.out.println("token="
                    + token.get(5, TimeUnit.SECONDS));
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 ScannerBlockingDemo.java
java ScannerBlockingDemo
~~~

Stdout chính xác khi thí nghiệm hoàn thành bình thường:

~~~text
hasNextInitiallyWaiting=true
hasNext=true
nextStillWaiting=true
token=hello
~~~

Khoảng chờ 5 giây trong các lời gọi đồng bộ là giới hạn để thí nghiệm thất bại rõ ràng nếu sự kiện mong đợi không xảy ra. Nó không phải thời gian Scanner cần để đọc, cũng không phải một timeout được cài vào Scanner.

Kết quả cho thấy điều gì?

- `hasNextInitiallyWaiting=true`: một lời gọi kiểm tra cũng chưa trả về khi nguồn chưa cung cấp dữ liệu.
- `hasNext=true`: bên đọc đã xác định có token.
- `nextStillWaiting=true`: tác vụ lấy token chưa xong dù đã có kết quả kiểm tra phía trước.
- `token=hello`: khoảng trắng gửi sau cùng giúp hoàn tất token theo dấu phân cách mặc định.

Đây là bằng chứng bằng chương trình cho tình huống cụ thể, không phải một yêu cầu rằng mọi loại nguồn hoặc mọi mẫu phân cách phải đi qua đúng hai lần đọc. Không viết logic ứng dụng dựa vào số lần Scanner đọc bộ đệm.

Cặp pipe là công cụ mô phỏng một nguồn được ghi dần. Việc một lần đọc pipe phải chờ dữ liệu, EOF hoặc lỗi là hành vi được API mô tả. [PipedReader.read](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/PipedReader.html#read(char%5B%5D,int,int)).

## 5. EOF khác với khoảng lặng tạm thời

EOF (end of input/end of stream) nghĩa là nguồn đã báo kết thúc, không còn dữ liệu tiếp theo trong lượt đọc đó. Nó khác việc một nguồn còn mở nhưng chưa gửi thêm.

| Trạng thái | Có thể có dữ liệu sau đó không? | Cách hiểu |
| --- | --- | --- |
| Nguồn còn mở, chưa có ký tự mới | Có | Có thể phải chờ |
| Nguồn có một phần token nhưng chưa có ranh giới | Có | Có thể cần đọc tiếp để xác định token |
| Nguồn đã báo EOF, vẫn còn ký tự trong bộ đệm | Không có ký tự mới từ nguồn | Scanner vẫn có thể trả token/dòng cuối |
| Nguồn đã báo EOF và không còn token | Không | `hasNext()` trả `false` |

Một token cuối không bắt buộc phải có khoảng trắng sau nó nếu nguồn đã kết thúc. Scanner có thể dùng EOF làm bằng chứng rằng token sẽ không dài thêm.

Với `String`, toàn bộ nguồn là hữu hạn ngay từ đầu. Vì thế `new Scanner("42").nextInt()` không phải chờ ai gửi một dấu cách: scanner có thể đọc đến kết thúc chuỗi.

### Chương trình kiểm tra nguồn hữu hạn

Lưu thành `ScannerFiniteInputDemo.java`:

~~~java
import java.util.Scanner;

public class ScannerFiniteInputDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("42")) {
            System.out.println("number=" + scanner.nextInt());
            System.out.println("moreTokens=" + scanner.hasNext());
        }

        try (Scanner scanner = new Scanner("last line")) {
            System.out.println("hasLine=" + scanner.hasNextLine());
            System.out.println("line=" + scanner.nextLine());
            System.out.println("moreLines=" + scanner.hasNextLine());
        }

        try (Scanner scanner = new Scanner("   ")) {
            System.out.println("onlyWhitespace=" + scanner.hasNext());
        }
    }
}
~~~

~~~shell
javac --release 17 -encoding UTF-8 ScannerFiniteInputDemo.java
java ScannerFiniteInputDemo
~~~

Stdout chính xác:

~~~text
number=42
moreTokens=false
hasLine=true
line=last line
moreLines=false
onlyWhitespace=false
~~~

Dòng `last line` không có ký tự xuống dòng cuối nhưng vẫn được trả về vì nguồn đã kết thúc. Chuỗi chỉ có khoảng trắng không tạo token với dấu phân cách mặc định.

## 6. nextLine và hasNextLine cũng có thể chờ

`nextLine()` cần phần còn lại của dòng hiện tại. Nếu nguồn chưa gửi dấu kết thúc dòng và chưa báo EOF, thao tác có thể cần đọc tiếp. `hasNextLine()` cũng có thể đọc thêm để quyết định có dòng hay không.

Một token có thể đã đủ để đọc nhưng một dòng vẫn chưa hoàn chỉnh. Với dữ liệu:

~~~text
hello 
~~~

khoảng trắng sau `hello` có thể đủ cho `next()`, nhưng chưa phải kết thúc dòng cho `nextLine()`. Nếu định dạng giao tiếp theo dòng, bên ghi cần gửi dấu kết thúc dòng thích hợp hoặc kết thúc nguồn.

Với dữ liệu rất dài không có xuống dòng, việc tìm dòng có thể cần đệm nhiều dữ liệu. Nếu đầu vào bên ngoài cần giới hạn chiều dài bản tin, phải có chiến lược giới hạn phù hợp ở tầng nhận/định dạng; Scanner không tự cung cấp một chính sách giới hạn dòng cho ứng dụng.

### Enter và terminal

Trên nhiều terminal ở chế độ nhập theo dòng, ký tự người dùng gõ chỉ được chuyển tới chương trình sau Enter. Đó là hành vi của môi trường nhập và cấu hình terminal, không phải quy tắc rằng mọi Scanner luôn cần phím Enter.

Một scanner đọc từ chuỗi, tệp hoặc pipe không biết người dùng có nhấn phím nào. Nó thấy ký tự, dấu phân cách, ranh giới dòng và kết thúc nguồn.

Lệnh báo EOF từ bàn phím phụ thuộc môi trường chạy; IDE hoặc terminal cũng có thể xử lý khác nhau. Khi kiểm thử hành vi kết thúc, nguồn chuỗi hoặc đầu vào được điều khiển thường dễ tái hiện hơn việc dựa vào tổ hợp phím.

## 7. Vòng lặp đọc tới hết nguồn có thể chờ đúng thiết kế

~~~java
while (scanner.hasNext()) {
    String token = scanner.next();
    System.out.println(token);
}
~~~

Đây là mảnh mã với scanner đã được tạo. Với nguồn hữu hạn, nó đọc tới cuối. Với một luồng còn mở, sau khi đọc hết dữ liệu hiện có, lần `hasNext()` tiếp theo có thể chờ phần tiếp theo hoặc EOF.

Điều đó phù hợp với chương trình có nhiệm vụ tiếp tục nhận đầu vào. Nhưng nếu chương trình đáng lẽ chỉ cần một giá trị hoặc một bản tin, vòng lặp “đọc đến EOF” có thể tạo cảm giác treo vì bên gửi không có ý định đóng kết nối.

Cần xác định điều kiện hoàn tất của giao tiếp:

- Đọc một số lượng trường cố định.
- Đọc đến ký hiệu kết thúc được quy ước.
- Đọc một dòng hoặc một bản tin có ranh giới rõ ràng.
- Đọc tới EOF khi thực sự coi việc đóng nguồn là kết thúc dữ liệu.

Không thêm một `break` tùy tiện chỉ để chương trình ngừng chờ; phải gắn điều kiện dừng với hợp đồng đầu vào.

Nếu vòng lặp không hề tiêu thụ token, đó lại là vấn đề khác:

~~~java
while (scanner.hasNext()) {
    System.out.println("There is input");
}
~~~

Đây là **mảnh mã sai cố ý** cho một vòng lặp muốn xử lý token. Khi một token đã sẵn có, `hasNext()` có thể trả `true` liên tục vì chương trình không lấy token ấy ra. Đây có thể là vòng lặp bận, khác với luồng đang chờ I/O.

## 8. available và ready không xác nhận token hoàn chỉnh

Không dùng `System.in.available()` để quyết định một lần `scanner.nextInt()` chắc chắn sẽ không chặn.

`InputStream.available()` chỉ ước lượng số byte có thể đọc mà không chặn ở tầng nguồn. Nó không hiểu token, bảng mã hay bộ đệm riêng của Scanner. Giá trị `0` có thể xuất hiện cả khi hiện chưa có byte đọc ngay được hoặc khi đã tới cuối nguồn. [Hợp đồng InputStream.available](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStream.html#available()).

Ngay cả khi nguồn có byte:

- Byte đó có thể mới là một phần ký tự trong bảng mã nhiều byte.
- Có ký tự chưa chắc đã có dấu phân cách kết thúc token.
- Scanner có thể đã đọc trước dữ liệu vào bộ đệm, khiến quan sát trực tiếp nguồn không phản ánh phần Scanner còn giữ.

`Reader.ready()` cũng thuộc tầng đọc ký tự; nó không có nghĩa “một lời gọi Scanner bất kỳ sẽ hoàn thành”. Đừng trộn nhiều cơ chế đọc trên cùng nguồn để tự thăm dò: chúng có thể tranh nhau dữ liệu hoặc bỏ qua bộ đệm của nhau.

`Thread.sleep(...)` không tạo thêm dữ liệu và không xác định ranh giới token. Tăng thời gian ngủ chỉ thay đổi thời điểm kiểm tra, không sửa một giao thức thiếu dấu kết thúc.

## 9. Timeout và hủy phải được thiết kế ở đúng tầng

Scanner không có phương thức cấu hình chung kiểu `setReadTimeout(...)`. Nếu cần giới hạn thời gian, phải xem API của nguồn và cách tổ chức tác vụ.

### Giới hạn chờ của bên gọi không đồng nghĩa dừng việc đọc

Mảnh mã:

~~~java
String result = future.get(2, java.util.concurrent.TimeUnit.SECONDS);
~~~

có thể làm bên gọi nhận `TimeoutException` sau giới hạn chờ. Nó không tự chèn EOF, không làm token hoàn chỉnh và không tự dừng tác vụ đang chạy ở luồng khác.

Tương tự, `future.cancel(true)` yêu cầu hủy và có thể gửi ngắt tới luồng thực thi; một nguồn đọc bất kỳ không bắt buộc phải phản ứng theo cùng một cách. Không tuyên bố rằng bọc Scanner trong `Future` là đã giải quyết trọn vẹn timeout và thu hồi tài nguyên. [Future.get và Future.cancel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

### Nguồn có thể cung cấp cơ chế riêng

Một số API mạng hỗ trợ timeout ở tầng socket hoặc có quy tắc cụ thể khi đóng nguồn. Phải đọc hợp đồng của chính nguồn đó và kiểm tra cách lỗi được Scanner biểu hiện. Lỗi đọc ở nguồn có thể được lưu vào `scanner.ioException()` thay vì xuất hiện trực tiếp như ngoại lệ từ phương thức token.

Nếu hủy tác vụ bằng cách đóng tài nguyên, chỉ thực hiện khi tầng sở hữu cho phép và API nguồn bảo đảm hành vi phù hợp. Không dùng việc đóng `System.in` dùng chung như một thao tác “reset lượt nhập”.

Scanner không an toàn cho nhiều luồng cùng thao tác nếu thiếu đồng bộ ngoài. Không vừa cho một luồng đọc, vừa cho luồng khác gọi các phương thức Scanner để dò trạng thái hoặc đóng nó rồi giả định đó là cơ chế hủy phổ quát.

Trong chương trình thí nghiệm, chỉ tác vụ đọc chạm vào Scanner. Luồng chính giao tiếp với nguồn ghi, latch và future; các đối tượng ấy phục vụ quan sát, không phải cơ chế thay đổi nội bộ scanner.

## 10. Tổ chức ứng dụng để việc chờ không làm hỏng trải nghiệm

Với chương trình dòng lệnh đơn giản, chờ đầu vào thường là đúng. In lời nhắc trước lượt đọc và nói rõ dữ liệu mong đợi giúp người dùng hiểu chương trình đang chờ gì.

Nếu lời nhắc dùng `print(...)` và môi trường có đệm đầu ra, `System.out.flush()` có thể giúp lời nhắc xuất hiện trước khi chờ. Việc flush đầu ra vẫn độc lập với điều kiện để đầu vào hoàn tất.

Với giao diện đồ họa, đặt đọc chặn trên luồng xử lý giao diện có thể khiến cửa sổ không phản hồi. Với ứng dụng phục vụ nhiều yêu cầu, để quá nhiều tác vụ chờ vô hạn có thể giữ tài nguyên lâu hơn dự kiến.

Khi yêu cầu sản phẩm cần đáp ứng trong lúc đầu vào chưa tới, hãy tổ chức tầng nhận dữ liệu và điều kiện hoàn tất phù hợp: tác vụ nền có vòng đời rõ, giới hạn nguồn/tài nguyên, hoặc API sự kiện/không chặn theo kiến trúc ứng dụng. Chuyển việc đọc sang luồng khác giúp luồng gọi tiếp tục làm việc nhưng không tự làm I/O bên trong trở thành không chặn.

Trước khi chọn cách triển khai, cần trả lời:

1. Ai gửi dữ liệu và khi nào gửi dấu phân cách/kết thúc dòng?
2. Một lượt đọc hoàn tất bằng token, dòng, số trường hay EOF?
3. Nếu không có thêm dữ liệu, chương trình được phép chờ bao lâu?
4. Ai sở hữu nguồn, có quyền đóng/hủy nó và phải thu hồi tài nguyên thế nào?
5. Lỗi nguồn và dữ liệu không hợp lệ được trả về cho bên gọi theo cách nào?

## 11. Quy trình tìm nguyên nhân khi chương trình đang chờ

| Quan sát | Điều cần kiểm tra tiếp |
| --- | --- |
| Chưa có ký tự nào tới | Bên gửi có hoạt động, đã gửi/flush đúng chỗ chưa? |
| Có ký tự nhưng chưa trả token | Dấu phân cách đúng chưa, token đã hoàn chỉnh hay nguồn đã EOF chưa? |
| Đọc token được nhưng đọc dòng chưa xong | Có dấu kết thúc dòng không, hay chương trình đang đợi tới EOF? |
| Bên gọi timeout nhưng tác vụ còn chạy | Đã có cơ chế dừng I/O và thu hồi tài nguyên ở tầng nguồn chưa? |
| In cùng thông báo liên tục | Có tiêu thụ dữ liệu hoặc đổi điều kiện dừng trong vòng lặp không? |
| Vòng đọc kết thúc bất ngờ | Có lỗi ở `ioException()` hoặc dữ liệu không hợp lệ bị hiểu nhầm là hết nguồn không? |

Từ “chặn” trong I/O không đồng nghĩa rằng `Thread.getState()` nhất thiết trả đúng enum `BLOCKED`. Trạng thái luồng Java và việc một thao tác đang chờ đầu vào là hai góc nhìn khác nhau. Chẩn đoán dựa trên lời gọi đang chờ và hợp đồng nguồn sẽ rõ hơn chỉ nhìn một nhãn trạng thái. [Định nghĩa Thread.State](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.State.html).

## 12. Tự thực hành

1. Trong thí nghiệm pipe, thay `producer.write(" ");` cuối cùng bằng việc đóng bên ghi sau khi gửi `hello`. Dự đoán EOF sẽ giúp xác định token cuối thế nào.
2. Sửa tác vụ đọc thành `nextLine()`. Gửi một khoảng trắng rồi cuối cùng gửi `"\n"`; quan sát dấu nào thực sự kết thúc dòng.
3. Dùng `new Scanner("hello")` với `next()`. Giải thích vì sao không cần người khác gửi thêm dấu cách.
4. Thiết kế định dạng nhập ba số nguyên. Nêu điều kiện dừng khi đọc đủ ba số, thay vì vô tình đợi EOF của terminal.
5. Viết mô tả cho một timeout: giới hạn chờ của bên gọi, hành động với tác vụ đọc còn sống và nơi thu hồi nguồn. Không gộp ba việc thành một lời gọi `Future.get(...)`.
6. Tạo hai ví dụ riêng: vòng lặp có dữ liệu nhưng không tiêu thụ token và một lần đọc thiếu dữ liệu. Phân biệt vòng lặp bận với chờ I/O.

Điều quan trọng khi đọc Scanner là xác định đúng ranh giới hoàn tất: **có dữ liệu, có token/dòng hoàn chỉnh và đã hết nguồn là ba trạng thái khác nhau.**
