# `PipedInputStream`, `PipedOutputStream` và giao tiếp giữa luồng trong Java

`PipedInputStream` và `PipedOutputStream` trong `java.io` tạo thành một **ống dẫn byte một chiều (byte pipe)** giữa hai phần công việc trong **cùng JVM**. Một luồng (thread) có thể ghi byte vào đầu ra, còn luồng khác đọc những byte ấy ở đầu vào. Khác với `ByteArrayInputStream`/`ByteArrayOutputStream` lưu dữ liệu đã có trong bộ nhớ, pipe có **bộ đệm hữu hạn và khả năng chờ (blocking)**: nếu chưa có dữ liệu, phía đọc có thể đợi; nếu bộ đệm đầy, phía ghi có thể đợi phía đọc tiêu thụ.

Điểm quan trọng nhất là **kết nối đúng hai đầu, chạy bên ghi và bên đọc đồng thời, đóng bên ghi khi hoàn tất và xử lý lỗi ở cả hai phía**. Pipe chuyển **dòng byte** theo thứ tự, không tự tạo ranh giới “thông điệp” và không biến `read()` thành thao tác bất đồng bộ.

## 1. Hai lớp đảm nhiệm việc gì?

- `PipedOutputStream`: đầu **ghi**. Producer gọi `write(int)` hoặc `write(byte[], off, len)` để đẩy byte vào pipe.
- `PipedInputStream`: đầu **đọc**. Consumer gọi `read()` hoặc `read(byte[])` để nhận các byte theo thứ tự đã ghi.
- **Kết nối**: một đầu input và một đầu output được nối với nhau bằng constructor hoặc `connect(...)`. Không được nối lại một đầu đã kết nối.
- **Vòng đời**: khi producer đóng đầu output sau khi ghi xong, consumer có thể đọc hết các byte còn trong buffer rồi nhận `-1` (EOF). Ngược lại, đóng đầu input quá sớm có thể khiến việc ghi của producer thất bại.
- **Bộ đệm**: phần đệm thuộc cơ chế pipe trong bộ nhớ, không phải file hay kết nối mạng. `PipedInputStream(int pipeSize)` cho phép chọn kích thước bộ đệm bằng số byte dương.

Sơ đồ:

```text
Thread producer                         Thread consumer
      |                                       ^
      | write(bytes)                          | read(bytes)
      v                                       |
PipedOutputStream ---- kết nối ----> PipedInputStream
                                   [bộ đệm byte hữu hạn]
```

Đây là cơ chế giao tiếp **một chiều**: dữ liệu đi từ output sang input. Nếu ứng dụng cần trao đổi hai chiều, cần hai pipe có chiều ngược nhau hoặc một cơ chế giao tiếp phù hợp hơn.

### Các cách khởi tạo/kết nối hợp lệ

```java
// Cách 1: Tạo input trước, đưa vào constructor của output.
PipedInputStream input = new PipedInputStream();
PipedOutputStream output = new PipedOutputStream(input);

// Cách 2: Tạo output trước, đưa vào constructor của input.
PipedOutputStream output2 = new PipedOutputStream();
PipedInputStream input2 = new PipedInputStream(output2);

// Cách 3: Tạo hai đầu rời rồi kết nối một lần.
PipedInputStream input3 = new PipedInputStream(4096);
PipedOutputStream output3 = new PipedOutputStream();
output3.connect(input3);
```

Các đoạn trên là **minh họa**, cần `import java.io.PipedInputStream; import java.io.PipedOutputStream;` và đặt bên trong phương thức có xử lý `IOException`. Chỉ chọn **một** cách cho mỗi cặp input/output, không phải ba cách cho cùng một pipe. `connect()` có thể ném `IOException` nếu đầu tương ứng đã nối, bị đóng hoặc kết nối không hợp lệ; thao tác đọc/ghi trước khi nối cũng có thể lỗi.

`PipedInputStream` mặc định có bộ đệm hữu hạn; không nên dựa vào một dung lượng mặc định cụ thể để thiết kế logic. Khi cần giới hạn sức chứa, hãy chỉ định rõ `pipeSize` dương và xem đó là giới hạn của **bộ đệm byte**, không phải độ dài lớn nhất của cả dòng dữ liệu.

## 2. Ví dụ hoàn chỉnh: một thread ghi, thread khác đọc

Đoạn dưới đây sử dụng một thread từ `ExecutorService` làm producer, còn thread `main` làm consumer. Bộ đệm của pipe chỉ có **4 byte** để minh họa rằng hai phía phải tiến triển đồng thời. Producer ghi toàn bộ dữ liệu UTF-8 rồi đóng output; consumer đọc cho đến EOF và cuối cùng decode lại các byte.

```java
// PipeHelloDemo.java
import java.io.ByteArrayOutputStream;
import java.io.PipedInputStream;
import java.io.PipedOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class PipeHelloDemo {
    public static void main(String[] args) throws Exception {
        PipedInputStream input = new PipedInputStream(4);
        PipedOutputStream output = new PipedOutputStream(input);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> producer = executor.submit(() -> {
                try (PipedOutputStream writer = output) {
                    writer.write("Xin chào, pipe!"
                            .getBytes(StandardCharsets.UTF_8));
                }
                return null;
            });

            try (PipedInputStream reader = input) {
                ByteArrayOutputStream received = new ByteArrayOutputStream();
                byte[] buffer = new byte[3];
                int count;

                while ((count = reader.read(buffer)) != -1) {
                    received.write(buffer, 0, count);
                }

                producer.get(); // Chuyển lỗi của producer về main.
                System.out.println("text="
                        + received.toString(StandardCharsets.UTF_8));
                System.out.println("bytes=" + received.size());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch/chạy với **Java 17+**:

```bash
javac -encoding UTF-8 PipeHelloDemo.java
java PipeHelloDemo
```

Đầu ra:

```text
text=Xin chào, pipe!
bytes=16
```

Giải thích:

1. `PipedOutputStream(input)` kết nối output vào input.
2. `executor.submit(...)` chạy công việc ghi trên thread khác. `main` không cần chờ producer hoàn tất trước khi bắt đầu đọc.
3. Vì bộ đệm chỉ có 4 byte mà payload UTF-8 dài 16 byte, producer phải chờ consumer giải phóng chỗ trống khi cần.
4. `reader.read(buffer)` trả về **số byte thực sự nhận**; vòng lặp chỉ ghi `count` byte hợp lệ sang `ByteArrayOutputStream`.
5. Producer đóng `writer`, báo đã hết dữ liệu. Consumer nhận `-1` sau khi đọc hết phần còn trong pipe.
6. `producer.get()` đợi tác vụ hoàn tất và phát hiện exception từ producer (dưới dạng lỗi của `Future`), thay vì để lỗi trong worker bị bỏ qua.
7. UTF-8 có ký tự `à` nhiều byte; ghép byte rồi giải mã toàn bộ giúp không vô tình tách một ký tự đa byte ở ranh giới các lần `read()`.

**Không gọi `producer.get()` trước vòng lặp đọc** trong ví dụ này: nếu producer đang ghi quá dung lượng pipe, nó sẽ đợi consumer đọc; nếu `main` lại đợi producer hoàn tất trước khi đọc, chương trình có thể bị **deadlock**.

Lưu ý trong chương trình thực tế, nếu consumer lỗi sớm, cần đóng input để giải phóng tài nguyên và xử lý/cancel producer; đồng thời giới hạn thời gian chờ khi thích hợp. Ví dụ tập trung vào đường đi thành công và truyền lỗi producer.

## 3. Blocking, backpressure và thứ tự byte

Hai đầu pipe giao tiếp nhờ vùng đệm có dung lượng hữu hạn:

| Tình huống | Bên đọc | Bên ghi |
| --- | --- | --- |
| Chưa có byte và đầu ghi còn hoạt động | `read()` có thể **chờ** dữ liệu | Có thể ghi byte vào bộ đệm nếu còn chỗ |
| Bộ đệm đang còn byte | `read()` trả một hoặc nhiều byte | Ghi tiếp nếu còn chỗ |
| Bộ đệm đã đầy | Consumer đọc sẽ giải phóng chỗ | `write()` có thể **chờ** đến khi có chỗ |
| Đầu ghi đã đóng sau khi ghi xong | Đọc byte còn đệm, sau đó `read()` trả `-1` | Không ghi tiếp được qua đầu đã đóng |
| Đầu đọc bị đóng khi producer vẫn ghi | Không đọc tiếp được | Lệnh ghi có thể báo `IOException` |

Việc bên ghi tự nhiên phải đợi khi bộ đệm đầy được gọi là **backpressure**: tốc độ producer bị giới hạn bởi khả năng consumer nhận dữ liệu. Đây là tác dụng hữu ích với một luồng byte, nhưng cũng là lý do không được lạm dụng pipe trong những tác vụ thực hiện tuần tự trên cùng thread.

### Ví dụ hoàn chỉnh: quan sát ghi bị chặn khi bộ đệm đầy

Để tránh đo bằng `sleep()` hoặc thời gian may rủi, chương trình tạo pipe dung lượng **2 byte** và cho producer ghi **3 byte**. Trước khi main đọc byte nào, việc ghi đủ ba byte không thể hoàn thành thành công. Khi main đọc một byte, producer có chỗ để ghi byte thứ ba và kết thúc.

```java
// PipeBackpressureDemo.java
import java.io.PipedInputStream;
import java.io.PipedOutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class PipeBackpressureDemo {
    public static void main(String[] args) throws Exception {
        PipedInputStream input = new PipedInputStream(2);
        PipedOutputStream output = new PipedOutputStream(input);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> writeTask = executor.submit(() -> {
                try (PipedOutputStream writer = output) {
                    writer.write(new byte[] {10, 20, 30});
                }
                return null;
            });

            try (PipedInputStream reader = input) {
                System.out.println("doneBeforeRead=" + writeTask.isDone());
                System.out.println("first=" + reader.read());

                writeTask.get();
                System.out.println("doneAfterRead=" + writeTask.isDone());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac PipeBackpressureDemo.java
java PipeBackpressureDemo
```

Đầu ra dự kiến khi producer và consumer hoạt động đúng:

```text
doneBeforeRead=false
first=10
doneAfterRead=true
```

Với dung lượng 2, producer không thể ghi thành công cả ba byte **trước khi có lần đọc giải phóng ít nhất một vị trí**, nên `writeTask.isDone()` ban đầu là `false` (hoặc tác vụ chưa được lập lịch). Sau `reader.read()` trả byte đầu `10`, việc ghi có thể hoàn tất; `writeTask.get()` đợi chính xác thời điểm producer xong. Đây là minh họa **điều kiện bộ đệm**, không phải benchmark đo thời gian.

Nếu viết kiểu sau trên cùng thread:

```java
// MÃ SAI VỀ THIẾT KẾ: chỉ minh họa, không chạy riêng.
PipedInputStream input = new PipedInputStream(2);
PipedOutputStream output = new PipedOutputStream(input);
output.write(new byte[] {10, 20, 30}); // Có thể bị chặn.
int first = input.read();               // Có thể không bao giờ tới đây.
```

Thread đang cố ghi nhiều hơn dung lượng đệm sẽ chờ consumer, nhưng consumer nằm ở dòng lệnh **sau** trong chính thread đó. Đó là bẫy deadlock phổ biến.

### `read()` không bảo đảm trả đủ một “message”

Pipe là **byte stream**, nên một lần `read(byte[])` có thể trả ít byte hơn yêu cầu. Kích thước buffer của consumer, cách producer chia các lần `write` và thời điểm lập lịch **không phải ranh giới bản ghi**. Dù producer gọi `write(message)` một lần, consumer vẫn có thể nhận thông điệp qua nhiều lần `read`.

Do đó, không được gắn ý nghĩa “mỗi `read` = một message”. Muốn trao đổi message, ứng dụng phải có giao thức đóng khung (framing), ví dụ prefix chứa chiều dài, dấu phân cách có escape, hoặc codec ở tầng trên.

## 4. Đóng đầu ghi, EOF và vòng đời hai phía

Một quan hệ quan trọng:

```text
Producer ghi dữ liệu ---> Producer đóng output
       |                        |
       v                        v
Consumer đọc phần còn đệm ---> read() == -1 (EOF)
```

Khi bên ghi **đóng hợp lệ**, byte đã ghi trước đó vẫn được consumer lấy ra trước khi đến EOF. `read()` trên đầu đọc không tự trở thành `-1` chỉ vì tạm thời không có dữ liệu; khi đầu ghi còn mở và chưa có dữ liệu, nó có thể chờ.

Đóng **đầu đọc** không giống đóng **đầu ghi**:

- Đóng `PipedOutputStream` là cách producer thông báo “không còn byte mới” theo luồng dữ liệu và cho phép consumer kết thúc bằng EOF sau khi đọc hết dữ liệu đã đệm.
- Đóng `PipedInputStream` khi producer chưa xong có thể làm producer nhận `IOException` lúc ghi. Không dùng nó làm “tín hiệu bình thường” cho producer đã xong.
- Một worker bị chết hoặc kết thúc **mà không đóng đúng đầu pipe** có thể gây các lỗi “broken pipe”/“write end dead”/“read end dead” tùy trạng thái và implementation. Không dựa vào nội dung thông báo lỗi cụ thể để thay giao thức hoàn tất.
- `flush()` không thay thế `close()` làm dấu hiệu kết thúc luồng. Đặc biệt, `flush()` không phát ra marker EOF.

### Quyền sở hữu tài nguyên khi dùng wrapper

Bạn có thể bọc pipe bằng các lớp khác:

```java
// Minh họa một cặp wrapper đọc/ghi dữ liệu nhị phân.
DataInputStream reader = new DataInputStream(pipedInput);
DataOutputStream writer = new DataOutputStream(pipedOutput);
```

Ví dụ trên giả định `pipedInput` và `pipedOutput` đã nối và các import sẵn có. Khi mỗi thread **sở hữu** một đầu của pipe, dùng `try-with-resources` với **wrapper ngoài cùng** của đầu đó. `DataOutputStream.close()` đóng đầu output bên dưới; `DataInputStream.close()` đóng đầu input bên dưới. Đừng đóng raw pipe đang được thread kia sử dụng khi nó chưa xong.

Nếu dùng `BufferedOutputStream`/`BufferedWriter` bọc output, dữ liệu có thể còn nằm trong bộ đệm **ngoài** pipe; cần `flush()` ở thời điểm thông điệp phải được consumer nhìn thấy ngay, hoặc `close()` đúng lúc kết thúc. Tránh tình huống reader chờ data trong pipe nhưng writer lại chờ reader trong khi dữ liệu vẫn nằm ở buffer của writer.

## 5. Pipe chỉ truyền byte: cần framing nếu muốn giao tiếp theo thông điệp

Giả sử producer muốn gửi hai chuỗi `"A"` và `"Xin chào"`. Nếu cứ nối byte UTF-8 liên tiếp, consumer không biết đâu là ranh giới chuỗi đầu tiên. Một cách rõ ràng là gửi:

1. Số nguyên `int` 4 byte (`writeInt`) biểu diễn độ dài **byte** của payload.
2. Đúng số byte payload.
3. Lặp lại cho message kế tiếp.
4. Gửi sentinel chiều dài `-1` để kết thúc giao thức ví dụ này, rồi đóng output.

Consumer dùng `readInt()` đọc kích thước, kiểm tra phạm vi, rồi `readFully()` để nhận **đúng** số byte. `readFully()` tự gọi đọc nhiều lần nếu cần và ném `EOFException` khi stream đóng quá sớm; không nhầm short read thành message hoàn chỉnh.

```java
// PipeMessagesDemo.java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.PipedInputStream;
import java.io.PipedOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class PipeMessagesDemo {
    private static void send(DataOutputStream writer, String text)
            throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        writer.writeInt(payload.length);
        writer.write(payload);
    }

    public static void main(String[] args) throws Exception {
        PipedInputStream input = new PipedInputStream(8);
        PipedOutputStream output = new PipedOutputStream(input);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> producer = executor.submit(() -> {
                try (DataOutputStream writer = new DataOutputStream(output)) {
                    send(writer, "A");
                    send(writer, "Xin chào");
                    writer.writeInt(-1);
                }
                return null;
            });

            try (DataInputStream reader = new DataInputStream(input)) {
                int messages = 0;

                while (true) {
                    int length = reader.readInt();

                    if (length == -1) {
                        break;
                    }
                    if (length < 0 || length > 1024) {
                        throw new IOException("Invalid message length");
                    }

                    byte[] payload = new byte[length];
                    reader.readFully(payload);
                    System.out.println("message="
                            + new String(payload, StandardCharsets.UTF_8));
                    messages++;
                }

                producer.get();
                System.out.println("count=" + messages);
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 PipeMessagesDemo.java
java PipeMessagesDemo
```

Đầu ra:

```text
message=A
message=Xin chào
count=2
```

Đây là một **giao thức ví dụ do ứng dụng định nghĩa**, không phải định dạng mặc định của `PipedInputStream`/`PipedOutputStream`. Sentinel `-1` chỉ có ý nghĩa vì hai đầu đã thỏa thuận trước; `readInt()` **không** coi `-1` là EOF của pipe. Nếu producer đóng trước khi gửi đủ header hoặc payload, consumer nhận `EOFException`; đó là lỗi thông điệp chưa hoàn chỉnh, khác với sentinel bình thường.

Kiểm tra `length` trước khi cấp phát mảng để tránh một nguồn lỗi/cố ý gửi kích thước rất lớn gây cạn bộ nhớ. Trong thực tế, cần thêm quy tắc về version, checksum, timeout, lỗi nội dung và giới hạn ứng dụng.

Có thể thay framing bằng newline khi **quy ước nội dung không chứa newline không escape**, hoặc dùng `InputStreamReader`/`BufferedReader` cho text protocol. Khi nội dung có dấu phân cách/escape phức tạp, parser phải hiểu grammar; bản thân pipe vẫn chỉ là phương tiện vận chuyển byte.

## 6. Byte, ký tự và UTF-8: tránh giải mã từng khối tùy ý

`PipedInputStream`/`PipedOutputStream` **không tự hiểu Unicode**. UTF-8 chuyển ký tự thành 1–4 byte, vì vậy một lần `read(buffer)` có thể dừng **giữa** các byte của một ký tự.

Không nên làm:

```java
// MÃ MINH HỌA SAI: có thể giải mã từng chunk UTF-8 bị cắt giữa ký tự.
byte[] buffer = new byte[2];
int n;
while ((n = input.read(buffer)) != -1) {
    System.out.print(new String(buffer, 0, n, StandardCharsets.UTF_8));
}
```

Đoạn trên giả định `input` là stream đã mở. `new String(...)` trên mỗi chunk dùng **decoder mới**; nếu một ký tự đa byte bị cắt, kết quả có thể là ký tự thay thế `�` thay vì văn bản gốc.

Hai lựa chọn đúng theo nhu cầu:

- **Tầng byte:** giữ nguyên các byte của payload đến khi đủ message (như `readFully` trong ví dụ trên), rồi giải mã *toàn bộ payload* bằng UTF-8.
- **Tầng ký tự:** bọc `PipedInputStream` bằng `InputStreamReader(input, StandardCharsets.UTF_8)` một lần, có thể bọc thêm `BufferedReader`. Decoder khi ấy giữ trạng thái qua nhiều lần đọc. Nếu muốn truyền ký tự phía ghi, bọc `PipedOutputStream` bằng `OutputStreamWriter(output, StandardCharsets.UTF_8)`.

Dùng `Reader`/`Writer` cũng không tự tạo ranh giới message. Cần delimiter hoặc framing ở tầng ứng dụng và `flush()` thích hợp nếu writer có bộ đệm.

## 7. Lỗi thường gặp, ngắt luồng và chẩn đoán deadlock

### 7.1. Viết trước, đọc sau trên cùng một thread

Nếu producer ghi vượt sức chứa mà chưa có consumer chạy, `write()` có thể chặn mãi. **Khắc phục:** chạy producer và consumer đồng thời; không gọi `join()` hoặc `Future.get()` trên producer **trước khi** consumer bắt đầu đọc nếu producer có thể bị kẹt vì buffer đầy.

### 7.2. Không đóng output

Nếu producer đã gửi byte cuối nhưng vẫn để đầu output mở, consumer tiếp tục chờ ở lần `read()` tiếp theo. Không dùng `available() == 0` để kết luận đã hết: `available()` chỉ phản ánh số byte có thể đọc mà không chặn tại thời điểm kiểm tra, **không chứng minh EOF**. Khắc phục: thiết kế kết thúc hợp lệ, đóng writer trong `finally`/`try-with-resources`, hoặc có giao thức message kết thúc rõ ràng.

### 7.3. Đóng input quá sớm

Consumer gặp lỗi hoặc tự thoát khi writer đang gửi sẽ khiến writer có thể nhận `IOException`. Khắc phục: xác định rõ chính sách hủy, đóng các đầu thích hợp để đánh thức tác vụ đang chờ khi có lỗi, truyền lỗi của hai phía về nơi điều phối. Không bỏ qua `Future.get()` trong code sản xuất nếu lỗi producer quan trọng.

### 7.4. Đầu pipe chưa nối hoặc đã nối hai lần

Các thao tác đọc/ghi trên đầu chưa nối có thể gây `IOException` (thông điệp tùy môi trường). Nối lại hai đầu đã nối cũng không hợp lệ. Khắc phục: cấu hình cặp input/output **một lần** trước khi khởi động thread, bàn giao cho hai phía sử dụng.

### 7.5. Thread chết bất thường

Pipe trong Java có kiểm tra trạng thái thread đọc/ghi trong một số tình huống; khi thread đầu kia kết thúc không đúng cách, có thể phát sinh `IOException` dạng broken/dead pipe. **Không** xem việc phát hiện thread chết là tín hiệu kết thúc nghiệp vụ tin cậy. Cần đóng bình thường, truyền exception qua `Future`/cơ chế điều phối và định nghĩa protocol rõ ràng.

### 7.6. Interrupt và hủy tác vụ

Các thao tác pipe blocking có thể phản ứng với interrupt bằng `InterruptedIOException` hoặc lỗi liên quan theo API/implementation. Trong chương trình cần hủy được, hãy thiết kế rõ cách ngắt công việc, đóng pipe để giải phóng những thread đang chờ, và không nuốt lỗi interrupt. `Future.cancel(true)` chỉ gửi yêu cầu ngắt nếu worker đang chạy; không nên giả định nó tự giải phóng mọi resource hoặc đảm bảo thoát tức thì.

### 7.7. Nhiều producer/consumer dùng chung một pipe

Pipe nhắm đến mô hình giao tiếp giữa các thread, thường là **một writer và một reader** cho mỗi cặp. Dùng nhiều writer không biến các lần `write()` thành những thông điệp nguyên tử; dữ liệu có thể xen kẽ ở mức ứng dụng khi các lần ghi xen nhau. Dùng nhiều consumer có thể chia nhau byte, không phải mỗi consumer đều nhận một bản sao. Nếu cần nhiều nhà sản xuất/tiêu thụ với ranh giới phần tử và điều phối rõ ràng, cân nhắc `BlockingQueue<T>` hoặc cơ chế concurrent phù hợp.

### 7.8. Dùng pipe để thay hàng đợi thông điệp

`PipedInputStream` xử lý **byte**. Nó không có `put(Message)`, cơ chế broadcast, retry, ack, persist hay schema. Nếu mục tiêu là chuyển các object hoặc task giữa worker, `BlockingQueue<T>` thường trực tiếp và dễ kiểm soát hơn. Nếu mục tiêu là kết nối một API sản xuất `OutputStream` vào API tiêu thụ `InputStream` mà không tạo file trung gian, pipe lại rất hữu ích.

## 8. So sánh với các giải pháp I/O trong bộ nhớ khác

| Giải pháp | Dạng dữ liệu | Có blocking vì chờ đầu kia? | Mục đích tiêu biểu |
| --- | --- | --- | --- |
| `ByteArrayOutputStream` / `ByteArrayInputStream` | Mảng byte | Không theo cơ chế pipe | Tạo dữ liệu rồi đọc lại trong RAM, không cần producer/consumer chạy cùng lúc. |
| `PipedOutputStream` / `PipedInputStream` | Byte stream nối hai đầu | **Có**: đọc đợi dữ liệu, ghi có thể đợi chỗ trống | Streaming dữ liệu giữa producer và consumer trong JVM. |
| `StringWriter` / `StringReader` | Ký tự trong bộ nhớ | Không theo cơ chế pipe | Xây dựng và xử lý chuỗi ký tự. |
| `BlockingQueue<T>` | Phần tử kiểu `T` | **Có**, tùy thao tác và dung lượng queue | Bàn giao message/task giữa thread, giữ ranh giới phần tử. |
| `java.nio.channels.Pipe` | Byte qua `SourceChannel`/`SinkChannel` | Có thể cấu hình chế độ blocking của channel theo API | Kết hợp với mô hình NIO và channel. |

`java.nio.channels.Pipe` cũng là cơ chế truyền byte một chiều, nhưng là API channel với các đặc tính và phương thức khác. Không đồng nhất nó với cặp `java.io.PipedInputStream`/`PipedOutputStream`; đặc biệt cách chờ, tương tác selector và các lựa chọn thiết kế cần xem theo từng channel/provider.

### Khi nào nên chọn `PipedInputStream`/`PipedOutputStream`?

Phù hợp khi:

- Cần nối một API **ghi `OutputStream`** với một API **đọc `InputStream`** trong cùng ứng dụng.
- Muốn producer phát dữ liệu dần và consumer xử lý đồng thời, không cần tạo file tạm hay giữ toàn bộ payload trong RAM.
- Chấp nhận mô hình byte stream, backpressure và việc quản lý vòng đời thread.

Không phù hợp khi:

- Chỉ cần đọc lại byte đã tạo xong: `ByteArrayOutputStream` và `ByteArrayInputStream` đơn giản hơn.
- Cần hàng đợi các object có ranh giới message, nhiều producer/consumer: dùng queue.
- Cần giao tiếp giữa **hai tiến trình** hoặc máy khác: dùng cơ chế IPC/network tương ứng; các lớp `Piped*Stream` này không phải named pipe của hệ điều hành.
- Cần tốc độ/độ phức tạp concurrency cao, timeout, cancellation và quản lý lỗi chuyên biệt: có thể cần channel, queue hoặc pipeline concurrency được thiết kế rõ.

## 9. Checklist thiết kế giao tiếp bằng pipe

Trước khi triển khai, xác định:

1. **Ai tạo/kết nối pipe?** Kết nối hai đầu đúng một lần, trước khi các worker sử dụng.
2. **Ai là producer/consumer?** Chạy hai phía đồng thời trên các thread phù hợp; không tự tạo tình huống writer chờ reader trong cùng thread.
3. **Kích thước bộ đệm bao nhiêu?** Cân đối RAM, lưu lượng, tần suất blocking. Không dùng dung lượng buffer làm ranh giới message.
4. **Định dạng dữ liệu là gì?** Byte thô, charset được xác định, hay protocol có length prefix/delimiter? Nếu có message, chỉ rõ framing.
5. **Điều kiện kết thúc?** Producer đóng output; consumer đọc tới EOF hoặc giải mã sentinel protocol được quy định.
6. **Ai đóng resource?** Mỗi phía sở hữu đầu của mình và wrapper ngoài cùng; đóng đúng thứ tự.
7. **Lỗi ở một phía được truyền thế nào?** Dùng `Future.get()`, shared error state hoặc tầng điều phối; xử lý hủy để không bỏ lại thread bị chặn.
8. **Có giới hạn input không?** Nếu đọc length prefix, kiểm tra độ dài trước khi cấp phát; nếu streaming dữ liệu ngoài, giới hạn tổng bytes khi cần.
9. **Có dùng buffered/character wrapper không?** Hiểu `flush()` và charset; tránh deadlock do dữ liệu còn trong buffer writer.
10. **Có thực sự cần byte stream không?** Nếu giao tiếp ở cấp độ object/task, cân nhắc `BlockingQueue`.

## 10. Câu hỏi tự kiểm tra

**1.** Pipe có thể dùng để thread A ghi byte và thread B đọc byte ngay khi dữ liệu được phát sinh không?

**Đáp án:** Có. Kết nối `PipedOutputStream` với `PipedInputStream`; chạy producer và consumer đồng thời. Đây là một byte stream một chiều.

**2.** Pipe có 4 byte đệm; một thread đơn lẻ gọi `write` 100 byte rồi mới gọi `read`. Có an toàn không?

**Đáp án:** Không. Lệnh ghi có thể bị chặn khi buffer đầy mà không có consumer đang chạy để giải phóng chỗ.

**3.** Bên đọc không còn byte sẵn trong buffer, nhưng bên ghi vẫn mở. `read()` bắt buộc trả `-1`?

**Đáp án:** Không. Nó có thể chờ dữ liệu. EOF `-1` thường xuất hiện sau khi bên ghi đã đóng và dữ liệu đệm đã được tiêu thụ.

**4.** Producer gọi `write(byte[])` một lần. Consumer có chắc nhận toàn bộ array trong một lần `read(byte[])`?

**Đáp án:** Không. Pipe không bảo toàn ranh giới các lần `write` thành message. Consumer phải dùng giao thức framing và lặp đọc để lấy đủ dữ liệu.

**5.** Nếu gửi văn bản UTF-8, có nên chuyển từng chunk tùy ý thành `String` riêng?

**Đáp án:** Không. Ký tự đa byte có thể bị tách ở biên chunk. Dùng decoder giữ trạng thái (`InputStreamReader`) hoặc ghép đủ payload byte rồi mới decode.

**6.** `flush()` trên writer có báo “đã hết stream” cho consumer không?

**Đáp án:** Không. `flush()` đẩy dữ liệu đang đệm; producer phải đóng đầu ghi hoặc gửi tín hiệu kết thúc theo giao thức ứng dụng.

**7.** Khi gửi các object/tác vụ nhiều producer tới nhiều consumer, pipe có phải lựa chọn đầu tiên không?

**Đáp án:** Thường không. `BlockingQueue<T>` quản lý phần tử và điều phối producer/consumer thuận tiện hơn. Pipe phù hợp hơn với byte stream.

**8.** Vì sao trong ví dụ `PipeHelloDemo` gọi `producer.get()` **sau** vòng đọc?

**Đáp án:** Nếu gọi trước, thread main có thể chờ writer hoàn tất trong khi writer đang chờ main đọc để giải phóng bộ đệm, gây deadlock. Đọc đồng thời rồi mới đợi Future kết thúc giúp hai phía tiến triển.

**Ghi nhớ:** `PipedOutputStream` + `PipedInputStream` là **ống dẫn byte một chiều, có blocking và bộ đệm hữu hạn, hoạt động giữa các thread của cùng JVM**. Kết nối trước khi chạy, đọc/ghi đồng thời, đóng phía ghi để consumer nhận EOF, và tự định nghĩa framing nếu cần thông điệp. Khi vấn đề ở cấp độ object/task chứ không phải byte stream, hãy cân nhắc hàng đợi concurrent.
