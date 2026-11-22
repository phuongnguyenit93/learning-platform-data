# PipedReader, PipedWriter và nguy cơ bế tắc khi dùng không đúng

> **Ngữ cảnh:** Java Core → I/O trong bộ nhớ. Bài học giải thích một cặp luồng ký tự nối hai tác vụ trong cùng JVM, vì sao đọc/ghi có thể chặn, trường hợp tạo bế tắc khi vận hành không đúng và cách tổ chức producer–consumer để có điểm kết thúc, dọn tài nguyên và báo lỗi rõ ràng. Các lớp này thuộc `java.io` từ Java 1.1; ví dụ độc lập bên dưới dùng Java 17.

## 1. Bản chất của pipe ký tự

`PipedWriter` là **đầu ghi** ký tự; `PipedReader` là **đầu đọc**. Sau khi kết nối hai đầu thành một pipe, các `char` được ghi ở đầu writer sẽ được lấy ra lần lượt ở đầu reader. Pipe chứa một **bộ đệm hữu hạn** nên hai phía có thể hoạt động với tốc độ khác nhau trong phạm vi dung lượng bộ đệm. Nó thường dùng cho giao tiếp producer–consumer **giữa các thread trong cùng JVM**. Không phải socket, không phải file trên ổ đĩa và không phải giải pháp gửi dữ liệu qua các process.

~~~text
Thread PRODUCER                       Thread CONSUMER
       |                                     ^
       | PipedWriter.write(...)              | PipedReader.read(...)
       v                                     |
       +-------------------------------------+
       |          bộ đệm char hữu hạn        |
       +-------------------------------------+
          rỗng → read phải chờ dữ liệu
          đầy  → write phải chờ có chỗ trống
          writer.close() → reader có thể tới EOF
~~~

Đối tượng truyền trong pipe là **UTF-16 code unit** theo `Reader`/`Writer`, không phải byte đã encode. Đối với tiếng Việt thông thường nhiều code point BMP, một `char` thường biểu diễn một code point; với emoji ngoài BMP, một code point cần **hai `char`** tạo surrogate pair. Nếu cần luân chuyển **byte nhị phân**, dùng `PipedInputStream` và `PipedOutputStream` hoặc giải pháp phù hợp khác.

### So với StringReader/StringWriter và queue

| Cách truyền | Phù hợp khi | Giới hạn |
| --- | --- | --- |
| `StringReader` / `CharArrayReader` | Một chuỗi/array đã có sẵn ở bộ nhớ, đọc lại cục bộ | Không tạo liên kết streaming tới thread ghi đang sản xuất. |
| `StringWriter` / `CharArrayWriter` | Thu thập output ký tự thành bộ đệm tăng dần rồi đọc sau | Có thể giữ toàn bộ nội dung trong RAM; không tự cung cấp blocking producer–consumer. |
| `PipedReader` + `PipedWriter` | Một producer tạo chuỗi ký tự tăng dần và consumer đọc như `Reader` | Bounded pipe; có thể chặn và bế tắc nếu không có thread đối ứng. |
| `BlockingQueue<String>` | Producer–consumer truyền **message** có ranh giới rõ | Phải tự chọn capacity, giao thức kết thúc và xử lý lỗi; không phải Reader/Writer. |
| `PipedInputStream` + `PipedOutputStream` | Kết nối bên gửi/nhận **byte** | Không tự giải mã charset; thường cũng cần hai thread. |

**Chọn đúng trừu tượng:** Nếu parser chỉ nhận `Reader` và dữ liệu được tạo dần từ một tác vụ khác, pipe ký tự có thể dùng được. Nếu giao tiếp là hàng đợi sự kiện hoặc từng message độc lập, một queue có giới hạn dung lượng cùng cơ chế đóng/kết thúc rõ ràng thường đơn giản hơn. Nếu chỉ cần trả về một `String` đã tạo sẵn, pipe có thể phức tạp không cần thiết.

## 2. Tạo cặp pipe và kết nối chính xác một lần

Có hai mẫu hợp lệ.

**Kết nối ngay bằng constructor:**

~~~java
// Fragment đặt trong phương thức có thể ném IOException.
PipedReader reader = new PipedReader(1024);
PipedWriter writer = new PipedWriter(reader);
~~~

**Hoặc khởi tạo rời rồi connect:**

~~~java
// Fragment đặt trong phương thức có thể ném IOException.
PipedReader reader = new PipedReader();
PipedWriter writer = new PipedWriter();
writer.connect(reader);       // Tương đương reader.connect(writer).
~~~

Đây là các **fragment**; để biên dịch cần import `java.io.PipedReader`, `java.io.PipedWriter` và khai báo/bắt `IOException` ở chỗ kết nối. Hai cách trên có ý nghĩa tương tự: writer và reader tạo thành một cặp giao tiếp một chiều.

- Một reader/writer **chưa kết nối** không dùng được cho thao tác đọc/ghi bình thường; có thể gặp `IOException` khi dùng.
- Gọi `connect` lần thứ hai sau khi cặp đã được kết nối (hoặc cố nối đầu đó với đối tượng khác) gây `IOException`. **Không** tạo lại cặp kết nối như một “reset”.
- `new PipedReader(int pipeSize)` cho biết kích thước buffer theo **số `char`**, yêu cầu `pipeSize > 0`; giá trị bằng 0 hoặc âm gây `IllegalArgumentException`. Overload chỉ định buffer có từ Java 6.
- `new PipedReader(writer, pipeSize)` tạo reader với buffer kích thước được chọn và kết nối nó với writer chưa kết nối. `new PipedWriter(reader)` là cách trực quan để kết nối vào một reader đã có.
- Buffer mặc định trong OpenJDK thông thường là 1.024 `char`, nhưng **không cần dựa vào con số mặc định để chứng minh chương trình không deadlock**. Mọi buffer đều hữu hạn, và tốc độ producer có thể vượt tốc độ consumer.

### 2.1. Trạng thái quan trọng

~~~text
UNCONNECTED
   └── connect một lần ──> CONNECTED
                            |       |
                            |       └── reader.close() → phía đọc không còn dùng được
                            └── writer.close() → phía ghi kết thúc,
                                                  reader đọc nốt buffer rồi EOF
~~~

Đây là mô hình khái niệm, **không phải** sơ đồ trạng thái chính thức đầy đủ của implementation. Writer đóng để báo không còn dữ liệu; reader đóng để ngừng tiêu thụ. Không coi một đầu đã đóng là có thể kết nối lại hoặc dùng lại để mở phiên mới.

## 3. Blocking và backpressure: nguyên nhân đầu tiên dẫn tới kẹt

Pipe có một vùng đệm hữu hạn. Hai quy tắc cơ bản:

1. `PipedReader.read()` có thể **chặn** cho đến khi có ít nhất một ký tự, EOF được phát hiện hoặc có lỗi. Khi writer đã đóng bình thường và buffer được đọc hết, `read()` trả `-1`.
2. `PipedWriter.write(...)` có thể **chặn** nếu bộ đệm đã đầy và phải đợi consumer đọc bớt. Với `write(char[], off, len)`, thao tác phải viết đủ số ký tự yêu cầu hoặc ném lỗi; một lần ghi dài có thể phải chờ nhiều vòng.

Đó là **backpressure**: producer nhanh bị giới hạn bởi khả năng nhận của consumer. Nó có thể hữu ích vì không phải lưu toàn bộ dữ liệu vào bộ nhớ, nhưng đòi hỏi producer và consumer có khả năng chạy tiến triển **độc lập**.

Giả sử buffer cho phép giữ 4 `char`:

~~~text
Producer ghi 'A','B','C','D' → [ A B C D ] (đầy)
Producer muốn ghi 'E'       → WAIT đến khi consumer lấy bớt
Consumer đọc 'A','B'        → [ C D _ _ ]
Producer có chỗ để ghi tiếp → tiến triển
~~~

Nếu consumer **chưa được chạy** hoặc đang chờ một việc chỉ producer mới hoàn thành được, thời gian chờ có thể thành vô hạn. Nếu producer **không bao giờ ghi hoặc không bao giờ đóng** mà consumer cứ đọc, consumer có thể chờ vô hạn. Dùng `Thread.sleep(...)` không sửa quan hệ phụ thuộc này.

## 4. Ba kiểu bế tắc/tắc nghẽn thường gặp

### 4.1. Cùng một thread gọi read trước write

~~~java
// PHẢN VÍ DỤ: KHÔNG CHẠY như một chương trình.
PipedReader reader = new PipedReader(4);
PipedWriter writer = new PipedWriter(reader);
int first = reader.read();       // Có thể CHỜ vì pipe trống.
writer.write('A');               // Không bao giờ được thực hiện.
~~~

Thread bị kẹt tại `reader.read()` khi đang chờ một ký tự mà **chính nó** định ghi ở dòng sau. JavaDocs khuyến nghị hai đầu pipe được vận hành bởi hai thread khác nhau; dùng hai đầu trong cùng một thread có thể deadlock.

### 4.2. Cùng thread ghi quá sức chứa trước khi đọc

~~~java
// PHẢN VÍ DỤ: KHÔNG CHẠY như một chương trình.
PipedReader reader = new PipedReader(4);
PipedWriter writer = new PipedWriter(reader);
writer.write("ABCDEFGHIJ");     // Dài hơn dung lượng 4 char; có thể kẹt.
char[] block = new char[10];
int n = reader.read(block);      // Không tới được đây để giải phóng buffer.
~~~

Một `write(String)` có thể phải truyền nhiều phần xuống pipe. Khi đầy, writer chờ reader lấy bớt, nhưng reader lại nằm sau lệnh ghi trên **cùng thread**. Nếu ví dụ ghi ít hơn dung lượng rồi đọc, chương trình **có thể** chạy được trong một số điều kiện; điều đó không biến thiết kế cùng-thread thành an toàn cho input có kích thước không giới hạn.

### 4.3. Main thread chờ producer kết thúc trước khi đọc

~~~java
// PHẢN VÍ DỤ: KHÔNG CHẠY nếu producer sẽ ghi quá buffer.
producer.start();
producer.join();                 // Main chờ producer hoàn thành.
while (reader.read() != -1) { }  // Nhưng consumer chỉ bắt đầu sau join.
~~~

Producer đang chờ có chỗ trống trong buffer, còn main chờ producer thoát; main không đọc được vì bị giữ ở `join()`. Đây là **vòng phụ thuộc chờ**. Muốn chạy đúng, **bắt đầu producer, tiêu thụ đồng thời, sau đó mới join** khi đã đạt EOF hoặc hoàn tất việc dọn tài nguyên. Dù đã dùng **hai thread**, đặt `join` sai vị trí vẫn có thể làm chương trình kẹt.

### Deadlock so với blocking hợp lệ

Một lần `read` đợi vài mili giây để producer sinh ra dữ liệu là **blocking hợp lệ**, chưa phải deadlock. Deadlock xảy ra khi các tác vụ tạo vòng phụ thuộc mà không tác vụ nào có thể tiếp tục. Với pipe, cũng có thể xảy ra **indefinite wait** khi một phía còn sống nhưng không gửi/đóng, hoặc thread xử lý bị ngừng mà phía khác chưa được thông báo. Đừng gộp mọi thời gian chờ thành deadlock; phải xem **ai đang chờ điều kiện gì và ai có khả năng tạo điều kiện đó**.

## 5. Ví dụ độc lập đúng: producer và consumer chạy đồng thời

Tạo tệp **`PipeCharsDemo.java`**:

~~~java
import java.io.IOException;
import java.io.PipedReader;
import java.io.PipedWriter;
import java.util.concurrent.atomic.AtomicReference;

public class PipeCharsDemo {
    public static void main(String[] args) throws Exception {
        // Buffer chỉ có 4 char; producer sẽ gửi nhiều hơn 4 char.
        PipedReader reader = new PipedReader(4);
        PipedWriter writer = new PipedWriter(reader);
        AtomicReference<IOException> producerError = new AtomicReference<>();

        Thread producer = new Thread(() -> {
            try (writer) {
                writer.write("HELLO\nJAVA");
                // Không cần dùng sleep() để phối hợp.
            } catch (IOException error) {
                producerError.set(error);
            }
            // try-with-resources đóng writer ngay khi producer xong.
        }, "pipe-producer");

        producer.start(); // Producer có cơ hội ghi/đợi trên thread riêng.

        StringBuilder received = new StringBuilder();
        try (reader) {
            char[] buffer = new char[3];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                received.append(buffer, 0, count);
            }
        }

        producer.join(); // Chỉ chờ sau khi đã tiêu thụ tới EOF.
        if (producerError.get() != null) {
            throw producerError.get(); // Không nuốt lỗi producer.
        }

        System.out.println("received="
                + received.toString().replace('\n', '|'));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 PipeCharsDemo.java
java PipeCharsDemo
~~~

**Stdout của lần chạy thành công:**

~~~text
received=HELLO|JAVA
~~~

Đây là ví dụ có đầu vào cố định; thời điểm producer và consumer được scheduler chạy **không xác định**, nhưng output giữ thứ tự ký tự. Đã kiểm tra ví dụ này trên JDK bằng cơ chế chạy Java tương đương.

Từng phần có ý nghĩa riêng:

1. `PipedReader(4)` chủ động đặt buffer nhỏ để chuỗi 10 ký tự không thể nằm toàn bộ trong buffer một lúc.
2. `new PipedWriter(reader)` tạo **đúng một kết nối**.
3. `producer.start()` cho phép thread ghi chạy song song với main đang đọc. Việc producer bị chặn khi buffer đầy **không chặn main** tiêu thụ.
4. `read(buffer)` trả số `char` thật đọc; phải append `count` ký tự thay vì toàn bộ mảng, vì lần đọc cuối có thể không đầy buffer.
5. Kết thúc khối `try (writer)` gọi `close()` ở phía ghi, giúp reader nhận **EOF** khi đọc hết dữ liệu đang đệm.
6. `producer.join()` thực hiện **sau vòng đọc**, nên main không chờ producer khi chính producer còn cần main tiêu thụ. `AtomicReference` giúp lỗi `IOException` từ producer được báo về main, thay vì biến mất trong thread khác.

**Ranh giới của demo:** Đây là đường chạy thành công minh họa quan hệ producer–consumer. Nếu consumer ném exception trước khi đọc hết hoặc bị hủy, chương trình production cần chiến lược **đóng đầu đọc, truyền tín hiệu hủy, dừng producer và join có giới hạn**, không để thread ghi mắc kẹt chờ buffer. Phần dưới trình bày nguyên tắc đó. Không áp dụng `Thread.stop()` để xử lý.

## 6. Vì sao phải đóng writer để reader nhận EOF?

Hãy phân biệt ba trạng thái:

- **Buffer rỗng, writer còn mở:** reader có thể đợi vì producer vẫn có thể gửi thêm.
- **Buffer còn ký tự, writer đã đóng bình thường:** reader vẫn đọc những ký tự đang có; sau khi hết buffer, `read()` trả `-1`.
- **Reader đã đóng:** đầu nhận không còn tiêu thụ; writer đang hoặc sẽ ghi có thể nhận `IOException`. Đóng reader **không phải** thủ tục báo hoàn thành bình thường cho một luồng dữ liệu đã được gửi trọn.

Sai lầm thường gặp:

~~~java
// Producer đã ghi xong nhưng không close().
writer.write("done");
// Reader khác vẫn đang while ((n = reader.read(...)) != -1)
// sẽ không nhất thiết thấy EOF; nó còn chờ "dữ liệu tiếp theo".
~~~

**Quy tắc thực hành:** trong mô hình một producer sở hữu writer, đóng writer bằng `try-with-resources` hoặc `finally` sau khi thực sự hoàn tất. Đừng chỉ `flush()` rồi chờ reader tự hiểu đã kết thúc.

`PipedWriter.flush()` thông báo cho các reader đang đợi biết dữ liệu trong pipe; khi đặt `BufferedWriter` phía ngoài, `bufferedWriter.flush()` còn đẩy dữ liệu từ buffer của wrapper xuống writer bên dưới. Nhưng **flush không phải tín hiệu EOF** và không tự đóng writer. Với một stream ký tự kéo dài, hãy có giao thức xác định thời điểm hoàn thành hoặc message kết thúc nếu cần, thay vì “không thấy dữ liệu nữa nên tự thoát”.

## 7. Có thật sự cần `flush()` không?

Dưới góc nhìn API:

- `PipedWriter` có phương thức `flush()` và tài liệu nêu nó đánh thức các reader đang đợi khi ký tự đang chờ trong pipe.
- `BufferedWriter` bọc bên ngoài có buffer **riêng**; một lần `write` có thể mới nằm ở đó. Khi consumer cần nhận ngay mà writer còn mở, `flush()` trên **BufferedWriter** chuyển ký tự xuống pipe.
- `close()` trên writer/wrapper cũng hoàn tất vòng đời ghi, thường flush dữ liệu ở tầng wrapper rồi đóng đích theo hợp đồng của lớp đó.
- `flush()` không bảo đảm producer đọc hết nguồn, không giải phóng capacity nếu consumer không đọc, và không khắc phục tình huống producer đang kẹt vì buffer đầy trong cùng thread.

Ví dụ fragment có buffering bên ngoài:

~~~java
// Fragment: pipe là PipedWriter đã kết nối.
try (java.io.BufferedWriter out =
        new java.io.BufferedWriter(pipe)) {
    out.write("part-1");
    out.flush(); // Đẩy dữ liệu từ BufferedWriter xuống pipe.
    out.write("part-2");
} // Đóng wrapper, và thông thường đóng writer bên trong.
~~~

Fragment này vẫn cần consumer đồng thời. Nếu consumer không chạy, dữ liệu có thể khiến `flush` hoặc `close` phải chờ khi buffer đầy; thêm `flush()` không phải một cách né deadlock.

## 8. Thread chết và khái niệm broken pipe

`PipedReader.read()` có thể ném `IOException` khi pipe **broken**, chưa connect, đã đóng hoặc I/O gặp lỗi. `PipedWriter.write(...)` cũng có thể báo pipe broken, chưa connect hoặc đóng. Một số implementation phát hiện rằng **thread từng thực hiện read/write không còn sống** và có thể báo lỗi “Read end dead” hoặc “Write end dead”.

Tuy nhiên, **không nên dùng việc phát hiện thread chết làm giao thức kết thúc chương trình**:

- Producer có thể kết thúc **mà không close writer**, khiến consumer đợi hoặc gặp lỗi tùy trạng thái; không nên xem đó là EOF hợp lệ.
- Consumer ngừng nhận dữ liệu mà producer vẫn còn ghi có thể khiến producer chờ buffer hoặc nhận lỗi; caller phải quyết định hủy/dọn dẹp.
- Kiểu lỗi và thời điểm phát hiện phụ thuộc trạng thái, scheduling và chi tiết implementation; đừng assert chính xác chuỗi exception message trong test.
- Một thread được coi còn sống nhưng không có kế hoạch ghi thêm cũng có thể khiến consumer đợi vô thời hạn; kiểm tra `isAlive()` đơn thuần không đủ chứng minh tiến triển.

Vì vậy, **close writer ở đường thành công**, còn ở đường thất bại cần **báo exception riêng**, đóng endpoints và quản lý task lifecycle có chủ đích. Việc consumer nhận EOF không tự bảo đảm producer đã hoàn tất thành công — xem thêm `Future.get()`, `join()` + kênh báo lỗi, hoặc cơ chế điều phối của ứng dụng.

## 9. Xử lý lỗi của producer không được im lặng

Mã chạy ở thread khác không tự truyền exception lên thread gọi `start()`. Nếu producer ném lỗi mà consumer cứ đợi thêm input, luồng đọc có thể bị treo hoặc báo broken pipe, làm mất **nguyên nhân gốc**. Trong ví dụ `PipeCharsDemo`, `AtomicReference<IOException>` giữ lỗi của producer và được kiểm tra sau khi `join()`. Thiết kế mở rộng có thể dùng:

- `ExecutorService.submit(...)` trả `Future<?>`. `future.get()` xác nhận task hoàn tất và nhận `ExecutionException` có cause, nhưng không được gọi `get()` **trước khi** consumer tiêu thụ đủ nếu producer còn có thể chặn vì pipe đầy.
- Một cấu trúc truyền kết quả/lỗi rõ ràng trong pipeline; reader nhận EOF rồi caller còn phải kiểm tra producer có thành công không.
- Cơ chế hủy toàn bộ tác vụ khi reader hoặc writer gặp lỗi, đóng đúng endpoints, sau đó chờ task dừng trong thời hạn phù hợp.
- Đường đi của exception cả hai phía, không chỉ producer: consumer `IOException` cũng có thể yêu cầu báo cho producer dừng.

**Không** hứa rằng `Thread.interrupt()` luôn giải phóng ngay mọi blocked I/O trong mọi JDK/provider. Nếu buộc phải hủy, kiểm tra hành vi interrupt của API cụ thể, có chiến lược close/resource cleanup, quản lý timeout ở **cấp task** và tránh để thread chờ không giới hạn.

## 10. Có thể vừa đọc vừa ghi trong một thread không?

Đối với nguồn nhỏ đã biết và không lấp đầy buffer, bạn **có thể quan sát** một chương trình dùng một thread mà vẫn chạy. Nhưng API Java cảnh báo dùng reader và writer của cặp pipe trong cùng thread **không được khuyến nghị** do nguy cơ deadlock; việc chạy được với chuỗi ngắn không đủ để an toàn với payload dài hơn, tốc độ thay đổi hoặc xử lý newline.

Nếu có một thread duy nhất và dữ liệu đã có sẵn:

- Chọn `StringReader` để trình parser một `Reader` sau khi tạo hoàn chỉnh chuỗi.
- Chọn `CharArrayReader`/`CharArrayWriter` khi muốn dữ liệu ở dạng `char[]`.
- Dùng `StringWriter` để gom dữ liệu rồi `new StringReader(writer.toString())` nếu thực sự cần giao diện Reader.
- Đối với file có thể đọc lại, sử dụng `Files.newBufferedReader` hoặc nguồn file phù hợp.

Dùng pipe để “chuyển String sang Reader” trên cùng thread chỉ tăng nguy cơ mắc kẹt trong khi `new StringReader(text)` đã đáp ứng bài toán.

## 11. Bộ đệm hữu hạn và chọn pipeSize

`pipeSize` là số **UTF-16 code unit** trong bộ đệm reader. Khi producer có thể gửi `String` dài không xác định, không có kích thước buffer cố định nào đủ để đảm bảo writer **không bao giờ phải chờ**. Mục tiêu của bounded buffer chính là điều tiết tốc độ hai phía.

Quy tắc chọn:

1. Bắt đầu với mức đủ cho một số khối ký tự phù hợp workload. Không đẩy lên hàng triệu ký tự chỉ để che một deadlock do tổ chức thread sai.
2. Đo throughput, thời gian chờ producer và memory pressure với dữ liệu thực tế. Buffer lớn có thể giảm số lần chờ trong tải burst nhưng chiếm RAM và tăng lượng dữ liệu đang nằm chờ.
3. Reader có thể `read(char[],off,len)` ít hơn `len`; mỗi lần chỉ xử lý **số được trả**. Đừng giả định một lần read trả đúng một “message” hoặc một dòng.
4. Nếu dữ liệu có ranh giới message, định nghĩa framing riêng, ví dụ length prefix, newline với escape hợp lệ hoặc queue chứa object; pipe là luồng ký tự tuần tự, không tự bảo toàn ranh giới của từng lời gọi `write`.
5. Khi kích thước bộ đệm quá nhỏ và các thao tác đòi đối phương làm việc ở thứ tự ngược, vấn đề cốt lõi thường là **vòng phụ thuộc**, không phải con số capacity.

**Đối với Unicode:** một emoji ngoài BMP chứa hai UTF-16 code unit; pipe có thể tách hai nửa giữa các lần `read(buffer)`. Nếu muốn hiển thị, phân tích hoặc mã hóa thành UTF-8, phải duy trì trạng thái ký tự qua ranh giới buffer thay vì coi mỗi khối đọc là chuỗi hoàn chỉnh độc lập.

## 12. Không nhầm ready(), read() và EOF

`PipedReader.ready()` báo liệu đầu đọc **đã có ký tự trong circular buffer** để một lời gọi đọc tiếp không bị chặn chờ input ở thời điểm kiểm tra. Nếu trả `false`, nó **không cam kết** rằng lần `read` sau chắc chắn chặn: producer có thể vừa ghi ký tự trong lúc đó.

~~~java
// Fragment: reader đã connect và còn mở.
if (reader.ready()) {
    int ch = reader.read(); // Có thể lấy ký tự đang sẵn.
}
// Nếu ready() là false, KHÔNG được suy ra reader đã EOF.
~~~

Không làm như sau:

~~~java
// PHẢN VÍ DỤ LOGIC:
while (reader.ready()) {
    System.out.print((char) reader.read());
}
// Thoát sớm khi buffer tạm rỗng dù producer sắp ghi tiếp.
~~~

Cách đọc hết luồng đúng là:

~~~java
// Fragment: trong method có thể ném IOException.
char[] block = new char[1024];
int n;
while ((n = reader.read(block)) != -1) {
    process(block, n); // process là hàm do ứng dụng định nghĩa.
}
~~~

Đây là **fragment**, chưa phải chương trình độc lập vì `reader` và `process` do caller cung cấp. Vòng lặp tới `-1` cần writer đóng hợp lệ để dừng. `read(char[], off, 0)` có thể trả 0, nhưng với yêu cầu số lượng dương, method sẽ cố đọc ít nhất một `char` hoặc trả `-1` theo hợp đồng tài liệu.

## 13. Hai đầu pipe và try-with-resources: ai sở hữu tài nguyên?

Cặp pipe cần **hai vòng đời**: producer sở hữu đầu ghi, consumer sở hữu đầu đọc. Cách phân chia này đơn giản hóa trách nhiệm.

| Tình huống | Producer / writer | Consumer / reader |
| --- | --- | --- |
| Chạy bình thường | Ghi từng phần, đóng writer sau khi hoàn tất | Đọc tới `-1`, đóng reader |
| Producer gặp lỗi | Lưu/gửi lỗi, vẫn đóng writer trong `finally` / try-with-resources | Có thể nhận EOF sau phần dữ liệu đã ghi; kiểm tra báo lỗi producer ở cấp điều phối |
| Consumer muốn dừng sớm | Nhận tín hiệu dừng qua controller hoặc phát hiện reader đóng | Đóng reader và thông báo hủy theo chính sách |
| Chương trình bị hủy | Dừng tạo dữ liệu, đóng đầu ghi và giải quyết blocked operation | Đóng đầu đọc, chờ task kết thúc có giới hạn |
| Writer đóng trước khi ghi gì | Đóng writer bình thường | Reader có thể tới EOF ngay |
| Writer không đóng sau khi hoàn tất | Không còn dữ liệu nhưng vẫn giữ pipe mở | Reader có thể chờ vô thời hạn |

Một lưu ý về Java try-with-resources: nếu bạn tạo cả hai endpoints trong **cùng một try block** và writer/reader cần chạy trên thread khác, vòng đời tài nguyên phải bao phủ khoảng thời gian hai thread thực sự sử dụng chúng. Không đóng đầu đọc trong main khi producer vẫn gửi; cũng không để producer giữ writer mở sau khi đã dừng.

### 13.1. Mô hình điều phối có timeout và cancellation

Ứng dụng thực tế nên có người điều phối biết:

1. Khi nào khởi động producer và consumer, kết nối bao nhiêu pipe.
2. Task nào đang chạy, cách nhận lỗi qua `Future`/result channel.
3. Khi nào đóng writer để đánh dấu hoàn tất; khi nào cần đóng reader vì không dùng nữa.
4. Khi nào dừng chờ (`Future.get(timeout, unit)` hoặc cơ chế task timeout tương đương).
5. Nếu hết thời hạn, cách hủy các task, đóng đầu liên quan, ghi lỗi và chờ chúng dừng; không giả định interrupt là giải pháp duy nhất.

**Cảnh báo về thứ tự:** `future.get()`/`thread.join()` có thể chính là mắt xích của deadlock nếu caller giữ nhiệm vụ tiêu thụ dữ liệu nhưng lại chờ producer trước. Thiết kế phải cho consumer được chạy đồng thời; nếu cả producer lẫn consumer là task riêng, controller có thể giám sát cả hai mà không tự làm consumer.

## 14. Vì sao pipe đôi khi trả IOException thay vì chờ mãi?

Javadoc mô tả `PipedReader.read()` có thể ném `IOException` khi broken/unconnected/closed hoặc gặp lỗi. Writer cũng có thể ném `IOException` trong tình huống tương tự. Một implementation có thể phát hiện thread phía đối ứng đã chết trong khi buffer không còn dữ liệu hoặc reader không còn nhận.

Điều này **không phải cơ chế đảm bảo phát hiện mọi lỗi concurrency** và cũng không phải thay thế `join`/`Future`/close. Chương trình nào phụ thuộc vào exception text “Pipe broken”, “Write end dead” hay “Read end dead” để truyền kết quả ứng dụng sẽ khó duy trì giữa phiên bản và môi trường.

Hãy luôn ghi nhận **exception gốc của task** thay vì chỉ thấy đầu kia báo lỗi pipe. Khi consumer bị lỗi parse, đừng tiếp tục writer bằng mọi giá rồi chỉ log IOException thứ cấp. Khi producer bị lỗi, đóng writer trong finally và báo nguyên nhân cho bộ điều phối để nó phân biệt “đã gửi đủ dữ liệu” với “bị EOF do tác vụ hỏng”.

## 15. Những sai lầm phổ biến

1. **Gọi `read()` trước `write()` trên cùng thread**: đọc chờ dữ liệu mà chính thread này chưa ghi.
2. **Ghi payload dài hơn pipeSize trước khi bắt đầu read trên cùng thread**: producer đầy buffer và không thể tự giải phóng chỗ.
3. **`join()` producer trước khi tiêu thụ pipe**: hai thread vẫn có vòng phụ thuộc chờ.
4. **Quên `writer.close()`**: consumer đang đọc tới EOF có thể đợi vô hạn.
5. **Gọi `flush()` rồi tưởng đã gửi EOF**: flush có thể báo dữ liệu đang sẵn nhưng writer vẫn mở.
6. **Dùng `ready() == false` để suy ra hết dữ liệu**: đó chỉ là trạng thái sẵn sàng tức thời.
7. **Ghi mà không connect hoặc connect hai lần**: vi phạm hợp đồng cặp pipe, có thể `IOException`.
8. **Đặt buffer rất lớn để “sửa deadlock”**: chỉ che vấn đề ở payload hiện tại; đòi hỏi thiết kế concurrency đúng.
9. **Đọc một lần vào mảng rồi giả định đã đủ n ký tự**: xử lý số `char` thực đọc và EOF.
10. **Dùng pipe ký tự để copy ảnh/ZIP**: chúng phải đi qua byte stream, không qua Reader/Writer.
11. **Để producer exception biến mất trong thread nền**: consumer chỉ thấy EOF/broken/wait mà không biết nguyên nhân.
12. **Coi thread bị interrupt là chắc chắn đã thoát mọi I/O**: phải có chiến lược cancel và close tài nguyên.
13. **Dùng chung nhiều producer/consumer tùy tiện trên một pipe**: pipe được mô tả cho kết nối một phía gửi và một phía đọc; muốn nhiều publisher, cần cơ chế phối hợp/truyền message ở cấp cao hơn.
14. **Đóng reader trước khi producer gửi xong mà không báo hủy**: producer có thể ném lỗi hoặc kẹt trong thao tác còn dở.
15. **Xem mỗi lần write là một message không thể chia**: Reader chỉ cho dãy ký tự; các lần read có thể chia/gộp tùy tình trạng bộ đệm.

## 16. Bài tập tự kiểm tra

1. Vì sao `PipedReader` và `PipedWriter` thường phải được vận hành trên hai thread khác nhau?
2. `new PipedReader(4)` có thể xử lý tổng cộng 10.000 ký tự không? Điều kiện để hoạt động thành công là gì?
3. Mô tả vòng phụ thuộc khi main gọi `producer.join()` trước vòng `reader.read()`.
4. `writer.flush()` và `writer.close()` khác nhau thế nào đối với việc consumer đạt EOF?
5. `reader.ready() == false` có phải là dấu hiệu producer đã kết thúc không?
6. Nếu producer ghi chuỗi UTF-16 chứa emoji ngoài BMP, pipe truyền bao nhiêu đơn vị `char` cho một emoji, và consumer cần tránh giả định gì?
7. Vì sao ứng dụng cần kênh báo lỗi producer riêng ngay cả khi consumer đọc tới `-1`?
8. Nếu chỉ muốn biến một `String` đã có thành `Reader` để parser dùng trên cùng thread, chọn `PipedReader` hay `StringReader`?
9. Một thread producer còn sống nhưng đứng im và writer chưa đóng; reader có thể chờ mãi không? Có phải mọi dạng chờ đó đều là deadlock?
10. Khi cần truyền message có ranh giới và nhiều producer, nên cân nhắc trừu tượng nào khác?

**Đáp án định hướng:**

1. Vì blocking khi pipe rỗng/đầy cần phía còn lại chạy để tạo dữ liệu hoặc giải phóng capacity.
2. **Có**, buffer chỉ chứa tối đa một phần tại một thời điểm; consumer phải đọc đồng thời và writer cần đóng khi xong.
3. Producer chờ consumer đọc để có chỗ, main chờ producer hoàn tất nên consumer không chạy.
4. Flush hỗ trợ chuyển/thông báo dữ liệu đang có; **close** hoàn tất đầu ghi và cho reader nhận EOF sau khi đọc hết buffer.
5. **Không**, đó là snapshot của buffer ở thời điểm kiểm tra.
6. Thường **hai `char`** cho một supplementary code point; không được coi một lần read hay một char là một ký tự Unicode hoàn chỉnh.
7. EOF báo kết thúc luồng dữ liệu; nó không khẳng định producer đã sinh đủ dữ liệu hoặc không bị lỗi.
8. `StringReader` trực tiếp và đơn giản.
9. **Có** thể chờ vô hạn; không phải mọi chờ lâu đều hình thành vòng phụ thuộc deadlock.
10. `BlockingQueue` có capacity và giao thức dừng, hoặc API messaging/concurrency phù hợp.

## 17. Tài liệu chuẩn

- [Oracle Java SE 21 – PipedReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PipedReader.html): kết nối, `pipeSize`, blocking read, `ready()`, EOF và lỗi.
- [Oracle Java SE 21 – PipedWriter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PipedWriter.html): kết nối, blocking write, `flush()` và `close()`.
- [Oracle Java SE 21 – Reader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Reader.html): contract của character-stream I/O và `read(char[],off,len)`.
- [Oracle Java SE 21 – PipedInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PipedInputStream.html) và [PipedOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PipedOutputStream.html): phiên bản tương ứng để trao đổi byte.
- [Oracle Java SE 21 – BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html): lựa chọn cho producer–consumer có đơn vị là message và chính sách capacity.

**Ghi nhớ:** pipe ký tự là một buffer hữu hạn nối writer và reader. Đọc khi rỗng và ghi khi đầy đều có thể chặn; do đó cần producer và consumer có khả năng chạy đồng thời, **đóng writer để phát EOF**, kiểm tra lỗi của thread và bố trí `join()/get()` sau khi đã cho bên nhận tiến triển.