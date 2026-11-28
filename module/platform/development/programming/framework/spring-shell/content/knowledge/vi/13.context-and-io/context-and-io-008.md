# Flush, bộ đệm và thời điểm dữ liệu xuất hiện

Một command có thể đã gọi print() hoặc write() nhưng người dùng chưa thấy dữ liệu xuất hiện ngay trên terminal. Nguyên nhân thường là dữ liệu vẫn nằm trong một hoặc nhiều bộ đệm. Bộ đệm giúp gom nhiều thao tác nhỏ thành những lần ghi hiệu quả hơn; đổi lại, ứng dụng cần biết khi nào phải đẩy dữ liệu ra tầng tiếp theo.

Trong Java, flush() yêu cầu writer hoặc stream đẩy dữ liệu đang giữ trong bộ đệm xuống luồng bên dưới. close() thường flush trước khi giải phóng tài nguyên. Hai thao tác này có ý nghĩa khác nhau: flush để dữ liệu sẵn sàng cho bên nhận ở tầng kế tiếp, còn close kết thúc việc sử dụng tài nguyên. Flush cũng không đồng nghĩa dữ liệu đã được lưu bền vững xuống thiết bị hoặc đã được ứng dụng ở đầu bên kia xử lý.

Spring Shell nhận kết quả command và chuyển qua cơ chế rendering để hiển thị trên terminal. Khi command trả về một giá trị, framework quản lý việc trình bày kết quả. Nếu command tự ghi qua writer hoặc stream riêng, ứng dụng cần hiểu bộ đệm của writer đó và flush đúng thời điểm. Bài này kết nối cách hoạt động của Java I/O với thời điểm người dùng nhìn thấy kết quả trong CLI.

Sau bài này, bạn có thể:

- Giải thích vì sao dữ liệu được ghi nhưng chưa xuất hiện ngay.
- Phân biệt buffer, flush, close và lưu trữ bền vững.
- Xác định những thời điểm cần flush trong command tương tác và tác vụ chạy lâu.
- Hiểu hành vi auto-flush của PrintStream và PrintWriter.
- Dùng try-with-resources để đóng writer và stream đúng cách.
- Tránh flush quá thường xuyên, đóng nhầm stream do framework quản lý hoặc ghi output từ nhiều luồng không đồng bộ.

## 1. Dữ liệu đi qua nhiều tầng trước khi xuất hiện

Khi một command ghi kết quả, dữ liệu có thể đi qua nhiều tầng:

1. Mã ứng dụng tạo chuỗi hoặc byte.
2. BufferedWriter hoặc BufferedOutputStream giữ dữ liệu trong bộ đệm của ứng dụng.
3. Writer chuyển ký tự thành byte qua encoder như OutputStreamWriter.
4. Stream bên dưới chuyển byte tới file, pipe, socket hoặc terminal.
5. Hệ điều hành và thiết bị nhận dữ liệu.
6. Terminal emulator hoặc chương trình tiêu thụ hiển thị hay xử lý dữ liệu.

~~~mermaid
flowchart LR
    A[Command / service] --> B[Writer hoặc stream]
    B --> C[Bộ đệm ứng dụng]
    C --> D[Stream bên dưới]
    D --> E[Hệ điều hành]
    E --> F[Terminal / file / pipe / socket]
    F --> G[Người dùng hoặc tiến trình nhận]
~~~

Không phải ứng dụng nào cũng có đủ tất cả các tầng này. Ví dụ, ghi trực tiếp vào ByteArrayOutputStream không có thiết bị terminal ở cuối; ghi qua socket có thêm tầng mạng và chương trình ở đầu nhận.

Điểm quan trọng là lệnh write() có thể chỉ đưa dữ liệu vào bộ đệm hiện tại. Khi bộ đệm đầy, khi gọi flush() hoặc khi đóng writer/stream, dữ liệu mới được chuyển tiếp. Sau đó, tầng bên dưới vẫn có thể tiếp tục buffering.

## 2. Bộ đệm là gì và vì sao cần dùng?

Bộ đệm (buffer) là vùng nhớ tạm giữ dữ liệu trước khi chuyển tới đích. Thay vì ghi từng ký tự hoặc từng byte ngay lập tức, ứng dụng gom nhiều dữ liệu rồi ghi theo khối.

Ví dụ, ghi từng byte vào file có thể tạo ra nhiều lần gọi I/O. Dùng BufferedOutputStream giúp gom byte trong bộ nhớ và ghi theo từng khối lớn hơn:

~~~java
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public void writeBytes(Path path, byte[] data) throws IOException {
    try (BufferedOutputStream output =
                 new BufferedOutputStream(Files.newOutputStream(path))) {
        for (byte value : data) {
            output.write(value);
        }
    }
}
~~~

Mỗi lần gọi write(value) không nhất thiết tạo một lần ghi xuống filesystem. Bộ đệm giữ byte cho đến khi cần đẩy xuống stream bên dưới. Khi thoát khối try, close() được gọi; stream sẽ flush dữ liệu còn lại rồi giải phóng tài nguyên.

| Lợi ích | Đánh đổi |
|---|---|
| Giảm số lần gọi I/O nhỏ | Dữ liệu có thể chưa tới đích ngay sau write() |
| Tăng thông lượng khi ghi nhiều dữ liệu | Cần xác định thời điểm flush |
| Gom dữ liệu để xử lý theo khối | Tốn một phần bộ nhớ cho buffer |
| Hữu ích với file, pipe và socket | Nếu tiến trình dừng bất thường, dữ liệu còn trong bộ đệm có thể mất |

Không phải lúc nào cũng cần tự thêm buffer. Một số API đã trả về writer hoặc stream có buffering; bọc nhiều tầng không cần thiết làm luồng khó hiểu và có thể khiến người viết quên flush đúng đối tượng.

## 3. flush() thực hiện điều gì?

flush() yêu cầu đối tượng xuất đẩy dữ liệu đang giữ trong bộ đệm xuống đích bên dưới. Với các lớp bọc nhau, flush thường được truyền tiếp qua chuỗi writer/stream để các tầng đệm bên dưới cũng có cơ hội đẩy dữ liệu.

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public void writeInStages(Path path) throws IOException {
    try (BufferedWriter writer =
                 Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
        writer.write("Bắt đầu xử lý");
        writer.newLine();
        writer.flush();

        // Một tiến trình khác có thể cần đọc phần đã ghi ở thời điểm này.
        writer.write("Hoàn tất xử lý");
        writer.newLine();
    }
}
~~~

Sau lần flush() đầu tiên, writer đẩy phần đầu xuống tầng bên dưới mà không đóng file. Phần thứ hai được ghi sau đó và được flush khi writer đóng ở cuối khối try.

Flush không thêm ký tự xuống dòng. Nếu ghi chuỗi "Đang xử lý" rồi flush, dữ liệu được đẩy đi nhưng con trỏ terminal vẫn có thể ở cùng dòng. Muốn xuống dòng, gọi newLine() hoặc ghi ký tự xuống dòng theo format của ứng dụng.

### Flush lan qua các lớp bọc

Ví dụ chuỗi writer:

~~~text
BufferedWriter
    -> OutputStreamWriter
        -> BufferedOutputStream
            -> FileOutputStream
~~~

Gọi flush() trên BufferedWriter sẽ đẩy ký tự đang đệm qua OutputStreamWriter; writer mã hóa ký tự thành byte rồi flush stream bên dưới. Nếu chỉ flush một stream bên trong nhưng writer bên ngoài vẫn giữ ký tự chưa mã hóa, phần ký tự đó chưa được chuyển đi. Vì vậy, hãy flush ở lớp ngoài cùng mà ứng dụng đang dùng để ghi.

Một số lớp nền có thể triển khai flush() thành thao tác không làm gì nếu bản thân chúng không giữ bộ đệm. Ý nghĩa thực tế phụ thuộc lớp cụ thể, không phải mọi lần gọi flush đều tương ứng với một lệnh ghi vật lý.

## 4. close() khác flush() như thế nào?

close() kết thúc việc sử dụng tài nguyên. Với writer và stream có buffer, đóng thường flush phần còn lại trước rồi đóng tài nguyên bên dưới. Sau khi đóng, không được tiếp tục ghi vào writer hoặc stream đó.

| Thao tác | Đẩy dữ liệu đang đệm | Giải phóng tài nguyên | Có thể ghi tiếp? |
|---|---:|---:|---:|
| write() | Có thể chưa | Không | Có |
| flush() | Có | Không | Có |
| close() | Thường có | Có | Không |

Với file do command mở, dùng try-with-resources để bảo đảm đóng ngay cả khi có exception:

~~~java
try (BufferedWriter writer =
             Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Dữ liệu báo cáo");
}
~~~

Không cần gọi flush() ngay trước close() nếu không có yêu cầu dữ liệu phải được đẩy ra giữa quá trình ghi. Việc đóng writer đã thực hiện flush cuối cùng.

### Không đóng stream do runtime hoặc framework sở hữu

Không đóng System.out, System.err, terminal writer hoặc stream mà Spring Shell/JLine quản lý. Đây là tài nguyên dùng chung cho toàn bộ phiên shell. Nếu một command đóng chúng, các command chạy sau có thể không ghi được output.

Hãy đóng tài nguyên mà command tự mở, ví dụ Files.newBufferedWriter(...), Files.newInputStream(...) hoặc socket do command tạo. Với writer/terminal được inject từ framework, tuân theo vòng đời do framework quản lý; chỉ flush khi hợp đồng API yêu cầu và không tự đóng.

## 5. Khi nào dữ liệu xuất hiện trên terminal?

Thời điểm người dùng nhìn thấy dữ liệu phụ thuộc vào loại writer/stream và cách terminal được cấu hình:

| Cách ghi | Điều có thể xảy ra |
|---|---|
| write() vào BufferedWriter | Dữ liệu có thể còn trong buffer cho đến khi buffer đầy, flush hoặc close |
| print() vào writer không auto-flush | Dữ liệu có thể chưa được đẩy đi, kể cả khi chuỗi không có newline |
| println() vào PrintWriter có autoFlush = true | PrintWriter flush sau thao tác println() |
| Ghi newline vào PrintWriter | Không tự động flush chỉ vì có newline; auto-flush của PrintWriter gắn với println, printf hoặc format |
| Ghi newline vào PrintStream có auto-flush | Có thể kích hoạt flush theo hợp đồng của PrintStream |
| Gọi flush() | Yêu cầu đẩy dữ liệu qua các tầng đệm của đối tượng xuất |
| Gọi close() | Flush phần còn lại rồi đóng tài nguyên |

Đừng suy luận rằng cứ có newline là dữ liệu luôn xuất hiện ngay. Hành vi phụ thuộc loại stream và cấu hình auto-flush.

### PrintWriter và auto-flush

PrintWriter có constructor nhận cờ autoFlush. Khi cờ này là true, các phương thức println, printf và format sẽ flush sau khi ghi:

~~~java
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public void writeLog(Path path) throws IOException {
    try (PrintWriter writer = new PrintWriter(
            Files.newBufferedWriter(path, StandardCharsets.UTF_8),
            true)) {
        writer.println("Bắt đầu");
        writer.printf("Đã xử lý %d mục%n", 10);
        if (writer.checkError()) {
            throw new IOException("Không thể ghi log.");
        }
    }
}
~~~

PrintWriter thuận tiện cho việc in chuỗi và format, nhưng có một đặc điểm cần nhớ: nhiều lỗi I/O được giữ bên trong thay vì ném IOException trực tiếp từ các phương thức ghi. Có thể gọi checkError() để kiểm tra lỗi ghi sau thao tác. Nếu cần xử lý lỗi I/O bằng exception, dùng Writer/BufferedWriter trực tiếp hoặc kiểm tra checkError() khi dùng PrintWriter.

### PrintStream và auto-flush

PrintStream có chế độ auto-flush. Khi được tạo với autoFlush = true, tài liệu JDK quy định flush trong các trường hợp như ghi mảng byte, gọi phương thức println hoặc ghi ký tự xuống dòng. Không nên dựa vào hành vi này nếu stream được tạo ở nơi khác mà không biết cấu hình.

System.out và System.err là các stream chuẩn do runtime cung cấp. Chúng thường được dùng cho output và thông báo lỗi, nhưng có thể được chuyển hướng tới file hoặc pipe khi ứng dụng khởi chạy. Nếu cần bảo đảm một thông báo tiến độ được đẩy khỏi buffer hiện tại, gọi flush rõ ràng:

~~~java
System.out.print("Đang xử lý dữ liệu...");
System.out.flush();
~~~

Không gọi System.out.close() trong command. Khi ứng dụng chạy dưới Spring Shell, ưu tiên trả kết quả cho framework thay vì tự ghi System.out cho output thông thường.

## 6. Kết quả command trong Spring Shell

Với command Spring Shell, cách thông thường là trả về kết quả từ phương thức:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class StatusCommands {

    @ShellMethod(key = "job status", value = "Hiển thị trạng thái công việc.")
    public String status() {
        return "Công việc đã hoàn tất.";
    }
}
~~~

Spring Shell nhận giá trị trả về và chuyển qua cơ chế xử lý kết quả để hiển thị. Command không cần gọi flush() trên chuỗi trả về; chuỗi không phải writer hay stream. Cơ chế rendering của framework chịu trách nhiệm đưa kết quả ra terminal.

Nếu command cần ghi tiến độ trong khi vẫn đang chạy, cần chọn cơ chế output phù hợp với phiên bản và loại terminal. Khi tự quản lý một Writer, flush writer đó tại mốc tiến độ cần người dùng nhìn thấy. Khi dùng JLine Terminal hoặc LineReader, không đóng writer do terminal sở hữu; đồng thời tránh ghi từ background thread làm xen kẽ với prompt hoặc input của người dùng.

Ví dụ Java thuần minh họa tiến độ cần hiển thị trước khi tác vụ tiếp tục:

~~~java
public void processWithProgress() throws InterruptedException {
    System.out.print("Đang chuẩn bị...");
    System.out.flush();

    Thread.sleep(500);

    System.out.println(" xong.");
}
~~~

Trong command Spring Shell thực tế, không nên dùng Thread.sleep() để tạo tiến độ. Ví dụ chỉ cho thấy vì sao cần flush khi đã ghi thông báo chưa có newline nhưng muốn người dùng nhìn thấy trước bước tiếp theo.

## 7. Flush trong command chạy lâu và output dạng streaming

Một command có thể xử lý hàng nghìn bản ghi, xuất báo cáo hoặc theo dõi một tác vụ lâu. Nếu chỉ flush khi đóng writer, người dùng hoặc tiến trình đọc file sẽ không thấy kết quả trung gian.

Có thể flush theo mốc:

- Sau khi ghi header hoặc thông tin bắt đầu.
- Sau mỗi batch có ý nghĩa, ví dụ 100 hoặc 1.000 bản ghi.
- Khi ghi trạng thái cần người dùng phản hồi trước bước tiếp theo.
- Trước khi chờ input hoặc chờ một thao tác bên ngoài.
- Trước khi ghi thông báo lỗi sang một output channel khác nếu thứ tự hiển thị quan trọng.

Ví dụ ghi file theo batch:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public void exportRows(Path path, List<String> rows) throws IOException {
    try (BufferedWriter writer =
                 Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
        writer.write("id,name");
        writer.newLine();

        int count = 0;
        for (String row : rows) {
            writer.write(row);
            writer.newLine();
            count++;

            if (count % 500 == 0) {
                writer.flush();
            }
        }
    }
}
~~~

Flush mỗi 500 dòng là lựa chọn minh họa, không phải con số tối ưu cho mọi hệ thống. Chọn kích thước batch theo độ lớn dữ liệu, yêu cầu độ trễ, tốc độ đích và chi phí I/O.

### Flush quá thường xuyên

Flush sau mỗi ký tự hoặc mỗi dòng có thể làm giảm hiệu năng vì ngăn buffer gom dữ liệu. Với file lớn, thường nên ghi theo khối và để close flush phần cuối. Với tiến độ tương tác, chỉ flush tại những mốc mà người dùng thực sự cần quan sát.

| Nhu cầu | Chiến lược |
|---|---|
| Xuất file lớn, không cần đọc khi đang chạy | Ghi theo buffer, flush khi cần, close ở cuối |
| Ghi log cần theo dõi gần thời gian thực | Flush theo dòng hoặc theo batch nhỏ, tùy độ trễ |
| Hiển thị prompt trước khi chờ nhập | Flush prompt writer trước khi đọc input |
| In tiến độ của tác vụ dài | Flush tại các mốc tiến độ |
| Ghi vào pipe cho tiến trình khác xử lý | Flush theo đơn vị bản ghi hoặc batch mà giao thức yêu cầu |

## 8. Flush không đồng nghĩa với lưu bền vững

Flush chỉ yêu cầu dữ liệu đi qua buffer của các đối tượng xuất và được chuyển tới tầng bên dưới. Nó không đảm bảo byte đã được ghi vật lý lên thiết bị lưu trữ. Hệ điều hành, bộ điều khiển thiết bị hoặc filesystem vẫn có thể có cache riêng.

Với file, cần phân biệt:

1. writer.flush(): đẩy ký tự/byte qua buffer của writer và stream.
2. writer.close(): flush rồi đóng writer và stream bên dưới.
3. FileChannel.force(...) hoặc FileDescriptor.sync(): yêu cầu hệ điều hành đồng bộ thay đổi của file tới thiết bị lưu trữ theo hợp đồng API.

Ví dụ dùng FileChannel khi ứng dụng có yêu cầu đồng bộ file rõ ràng:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public void writeAndForce(Path path, String content) throws IOException {
    try (FileChannel channel = FileChannel.open(
            path,
            StandardOpenOption.CREATE,
            StandardOpenOption.WRITE,
            StandardOpenOption.TRUNCATE_EXISTING)) {
        ByteBuffer buffer = StandardCharsets.UTF_8.encode(content);
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
        channel.force(true);
    }
}
~~~

force(true) yêu cầu đồng bộ nội dung và metadata liên quan của file. Đây là thao tác có chi phí cao hơn flush thông thường; chỉ dùng khi yêu cầu độ bền dữ liệu cần thiết. Nó cũng không thay thế thiết kế transaction, backup hoặc cơ chế đảm bảo tính nhất quán của ứng dụng.

Với socket, flush không bảo đảm ứng dụng phía nhận đã đọc hoặc xử lý dữ liệu. Nó chỉ đẩy dữ liệu qua tầng stream hiện tại; TCP và hệ điều hành vẫn quản lý truyền nhận. Nếu cần xác nhận bên nhận đã xử lý, giao thức phải có phản hồi hoặc acknowledgement ở tầng ứng dụng.

## 9. Output chuẩn, error stream và thứ tự thông báo

Ứng dụng CLI thường có hai kênh:

- System.out: kết quả bình thường, dữ liệu mà script có thể chuyển tiếp hoặc lưu lại.
- System.err: thông báo lỗi, cảnh báo và chẩn đoán.

Có thể chuyển hướng hai kênh độc lập:

~~~powershell
java -jar app.jar > result.txt 2> error.txt
~~~

Khi output được chuyển hướng, người dùng không còn nhìn thấy dữ liệu trực tiếp trên terminal. Một tiến trình khác có thể đọc file hoặc pipe sau khi dữ liệu được flush. Không nên giả định stdout luôn line-buffered như một số môi trường C; hành vi phụ thuộc Java stream, wrapper và cách khởi chạy.

Nếu cần thứ tự rõ giữa hai kênh, flush stdout trước khi ghi lỗi sang stderr:

~~~java
System.out.println("Đã xử lý 10 bản ghi.");
System.out.flush();

System.err.println("Không thể xử lý bản ghi tiếp theo.");
System.err.flush();
~~~

Hai kênh là hai luồng độc lập; khi bị redirect hoặc được thu thập bởi hệ thống khác, thứ tự quan sát có thể khác thứ tự các lệnh ghi nếu chưa flush hoặc đồng bộ. Nếu cần output có thứ tự tuyệt đối, cân nhắc ghi qua một writer duy nhất hoặc thêm timestamp/sequence number.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ghi xong nhưng chưa thấy output | Dữ liệu còn trong buffer | Flush writer/stream đang sở hữu buffer hoặc đóng tài nguyên nếu đã kết thúc |
| Có newline nhưng vẫn chưa thấy dữ liệu | Writer không auto-flush | Gọi flush() hoặc dùng API auto-flush phù hợp |
| Đóng writer rồi không ghi tiếp được | close() đã kết thúc tài nguyên | Tạo writer mới hoặc giữ writer mở trong toàn bộ phạm vi cần ghi |
| Dữ liệu cuối file bị thiếu khi kết thúc bất thường | Chưa flush/close hoặc tiến trình bị dừng đột ngột | Dùng try-with-resources và xác định yêu cầu độ bền dữ liệu |
| PrintWriter không ném IOException | Lớp này giữ trạng thái lỗi nội bộ | Gọi checkError() hoặc dùng writer ném IOException |
| Command sau không in được kết quả | Một command trước đã đóng System.out hoặc terminal writer dùng chung | Không đóng stream do runtime/framework sở hữu |
| Tiến độ bị trễ | Chỉ flush ở cuối command hoặc buffer chưa đầy | Flush tại các mốc tiến độ cần quan sát |
| Ghi log chậm sau mỗi dòng | Flush quá thường xuyên | Dùng batch hoặc cấu hình appender phù hợp |
| File đã flush nhưng chưa chắc bền vững | Flush không đồng bộ cache thiết bị | Dùng FileChannel.force() khi có yêu cầu durability |
| Output xen lẫn prompt | Ghi từ background thread hoặc nhiều writer cùng terminal | Đồng bộ output và dùng cơ chế terminal phù hợp |

## 11. Checklist chọn thời điểm flush

- Xác định writer/stream nào đang giữ buffer.
- Flush lớp ngoài cùng mà ứng dụng dùng để ghi.
- Không cho rằng newline luôn tự flush.
- Dùng auto-flush chỉ khi hành vi đó phù hợp với tần suất output.
- Flush prompt hoặc thông báo tiến độ trước khi chờ hoặc thực hiện tác vụ lâu.
- Ghi theo batch khi thông lượng quan trọng.
- Để try-with-resources đóng writer do command tự mở.
- Không đóng System.out, System.err hoặc terminal writer do framework sở hữu.
- Kiểm tra lỗi nếu dùng PrintWriter.
- Dùng FileChannel.force() khi cần yêu cầu đồng bộ file tới thiết bị.
- Không xem flush socket là xác nhận phía nhận đã xử lý.
- Tránh ghi trực tiếp từ background thread vào terminal đang có prompt.

## 12. Bài tập thực hành

Tạo command report export xuất danh sách dữ liệu ra file:

1. Ghi header và 2.000 dòng bằng BufferedWriter.
2. Chạy lần đầu chỉ close ở cuối và quan sát thời điểm file có thể được đọc.
3. Chạy lần hai, flush sau mỗi 500 dòng; dùng một tiến trình khác theo dõi file để quan sát dữ liệu được đẩy ra theo batch.
4. Thêm thông báo tiến độ trên terminal trước mỗi batch và flush output tiến độ.
5. Thử PrintWriter với autoFlush = true và false; so sánh println() với write() có newline.
6. Thử một trường hợp gây lỗi ghi để quan sát cách PrintWriter.checkError() khác với BufferedWriter ném IOException.
7. Không đóng System.out; chạy command tiếp theo để xác nhận terminal vẫn hoạt động.
8. Nếu yêu cầu bài tập là dữ liệu phải được đồng bộ xuống thiết bị trước khi báo thành công, thử FileChannel.force(true) và so sánh chi phí với flush thông thường.

Khi hoàn thành, giải thích rõ dữ liệu đã đi qua tầng nào sau mỗi lần flush và vì sao điều đó chưa chắc đồng nghĩa dữ liệu đã được người dùng nhìn thấy hoặc đã bền vững trên thiết bị.

## Tài liệu tham khảo

- [Java SE 21 – Writer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Writer.html): hợp đồng ghi ký tự, flush và close.
- [Java SE 21 – BufferedWriter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedWriter.html): ghi ký tự có bộ đệm và phương thức flush.
- [Java SE 21 – PrintWriter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintWriter.html): auto-flush, println/printf/format và checkError.
- [Java SE 21 – PrintStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintStream.html): auto-flush và hành vi của stream in.
- [Java SE 21 – FileChannel.force](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html#force(boolean)): yêu cầu đồng bộ cập nhật file tới thiết bị lưu trữ.
- [Spring Shell 3.3 – Command Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html): cách Spring Shell chạy command trong các chế độ thực thi.
- [JLine 3 – Terminal](https://jline.org/docs/terminal/): terminal abstraction và writer trong môi trường tương tác.
