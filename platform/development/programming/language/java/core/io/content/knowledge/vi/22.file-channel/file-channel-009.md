# Dùng FileChannel đồng thời: vị trí chia sẻ và thao tác có vị trí tường minh

## 1. Vấn đề: một FileChannel, nhiều thread

`java.nio.channels.FileChannel` cung cấp hai nhóm thao tác đọc/ghi cơ bản:

- **Thao tác tương đối với vị trí hiện tại**: `read(ByteBuffer dst)`, `write(ByteBuffer src)` dùng **vị trí chung của channel**. Khi đọc/ghi thành công, vị trí này tiến lên theo số byte đã xử lý.
- **Thao tác có vị trí tường minh** (*positional I/O*): `read(ByteBuffer dst, long position)` và `write(ByteBuffer src, long position)` nhận offset bắt đầu bằng byte trong tệp; chúng **không thay đổi vị trí hiện tại của channel**.

Cả hai nhóm đều có thể được gọi từ nhiều thread, nhưng có cách quản lý trạng thái và khả năng chạy song song khác nhau. Theo hợp đồng của `FileChannel`, bản thân channel **có thể được sử dụng bởi nhiều thread đồng thời**. Điều này **không** đồng nghĩa mọi thao tác đều chạy cùng lúc, một chuỗi nhiều lời gọi tự động trở thành nguyên tử hoặc `ByteBuffer` truyền vào an toàn khi bị chia sẻ.

Câu hỏi cốt lõi là: *Các tác vụ có muốn dùng chung một con trỏ tệp để xử lý tuần tự, hay mỗi tác vụ cần truy cập một vị trí do nó tự xác định?*

## 2. Hai loại vị trí không được nhầm lẫn

Một phép đọc/ghi qua `FileChannel` có thể liên quan đến **hai loại position** độc lập:

1. **File position của channel**, lấy/đặt bằng `channel.position()` và `channel.position(long)`. Đây là chỉ số byte trong tệp; mỗi `FileChannel` có vị trí riêng của chính nó.
2. **Position của `ByteBuffer`**, lấy/đặt bằng `buffer.position()`. Đây là chỉ số byte **bên trong buffer**. Các phép đọc/ghi của channel vẫn thường di chuyển position của buffer theo số byte được truyền, kể cả khi gọi overload có offset tường minh.

Ví dụ giả sử tệp chứa `ABCDEFGHIJ`, channel đang ở offset 3, còn buffer mới cấp phát có `position=0`:

~~~java
ByteBuffer dst = ByteBuffer.allocate(2);
int n = channel.read(dst, 7L);
~~~

Đây là **mảnh mã minh họa**, giả sử `channel` đang mở để đọc và tệp đủ dài. Khi đọc được hai byte, `dst` chứa `HI` và `dst.position() == 2`; trong khi **vị trí của channel vẫn là 3**. Muốn đọc nội dung vừa ghi vào buffer, cần `dst.flip()` rồi sử dụng `get()` hoặc charset decoder.

Ngược lại, gọi `channel.read(dst)` dùng **file position hiện tại**. Nếu đọc được hai byte ở offset 3, channel tiến lên offset 5 và buffer tiến lên position 2.

| API | Vị trí bắt đầu trong tệp | Thay đổi file position của channel? | Thay đổi buffer position? |
| --- | --- | --- | --- |
| `channel.read(dst)` | `channel.position()` tại lúc đọc | **Có**, theo số byte đọc được | **Có** |
| `channel.write(src)` | `channel.position()` tại lúc ghi | **Có**, theo số byte ghi được | **Có** |
| `channel.read(dst, offset)` | `offset` được truyền vào | **Không** | **Có** |
| `channel.write(src, offset)` | `offset` được truyền vào | **Không** | **Có** |
| `channel.position(offset)` | Đặt vị trí dùng cho thao tác tương đối tiếp theo | **Có**, thay thế giá trị hiện tại | Không |
| `channel.size()` | Xem độ dài tệp | Không chủ động dịch con trỏ | Không |
| `channel.truncate(size)` | Giảm kích thước tệp nếu cần | Có thể điều chỉnh file position nếu vượt kích thước mới | Không |

Ở mỗi lần đọc/ghi, số byte thực tế có thể **nhỏ hơn** `dst.remaining()` hoặc `src.remaining()`; cần kiểm tra giá trị trả về. Với `read`, `-1` báo kết thúc tệp. Các ví dụ có vòng lặp sau đây không giả định một lệnh là đủ cho cả vùng dữ liệu.

## 3. FileChannel thread-safe: chính xác được bảo đảm điều gì?

Hợp đồng Java SE của `FileChannel` quy định:

- Các instance `FileChannel` dùng được từ nhiều thread.
- **Tại một thời điểm, chỉ một thao tác trên cùng channel liên quan đến vị trí channel hoặc có thể thay đổi kích thước tệp được phép đang thực hiện.** Thao tác thứ hai thuộc nhóm này có thể phải chờ thao tác thứ nhất kết thúc.
- Những thao tác khác, đặc biệt là thao tác nhận **vị trí tường minh**, *có thể* thực hiện đồng thời; việc chúng thực sự chạy song song hay bị tuần tự hóa còn tùy implementation.
- `close()` có thể được gọi từ thread khác theo hợp đồng `Channel`; nếu đóng giữa khi một thao tác còn đang chạy có thể phát sinh lỗi như `AsynchronousCloseException`.

Như vậy, câu “FileChannel thread-safe” nói về **hợp đồng phối hợp ở mức thao tác channel**, chứ không bảo đảm:

1. Hai lệnh đọc tương đối liên tiếp của thread A được xem như một giao dịch không thể xen kẽ với lệnh của B.
2. Một `channel.position(n)` sau đó `channel.read(dst)` luôn đọc tại `n` nếu thread khác có thể thay đổi vị trí giữa hai lệnh.
3. Hai writer ghi **cùng vùng byte** bằng positional I/O sẽ cho ra một record nhất quán hoặc “writer thắng” nào đó theo thứ tự bạn mong muốn.
4. Việc mở hai `FileChannel` khác nhau tới cùng một tệp tự tạo một khóa chung cho cả hai instance.
5. Mọi buffer được đưa vào channel đều thread-safe. `ByteBuffer` có position/limit mutable riêng và không tự bảo đảm an toàn cho việc dùng chung đồng thời.

Phân biệt **an toàn nội bộ của một lời gọi** với **tính đúng đắn của thao tác nghiệp vụ gồm nhiều lời gọi** là phần quan trọng nhất khi dùng `FileChannel` trong hệ thống đa luồng.

## 4. Lỗi khi phối hợp position() + read()

Giả sử hai thread muốn đọc tại hai offset khác nhau:

~~~java
// Thread A
channel.position(100);
channel.read(bufferA);

// Thread B
channel.position(200);
channel.read(bufferB);
~~~

Đây là **mã minh họa**. Không có bảo đảm các lời gọi của A sẽ thực hiện liên tục: một thứ tự có thể là:

~~~text
A: channel.position(100)
B: channel.position(200)
A: channel.read(bufferA)  // Có thể đọc ở offset 200
B: channel.read(bufferB)  // Tiếp tục sau phần A vừa đọc
~~~

Việc channel tuần tự hóa từng lời gọi liên quan đến file position **không** tự bao bọc cặp `position(...) + read(...)` thành một giao dịch. Cùng một tình huống xảy ra với `position(...) + write(...)`.

Nếu tác vụ cần đọc tại offset cụ thể, cách trực tiếp hơn là:

~~~java
channel.read(bufferA, 100L);
channel.read(bufferB, 200L);
~~~

Hai lời gọi này có offset độc lập và không thay đổi vị trí chung của channel. Chúng vẫn làm di chuyển **position của từng buffer**, vì thế tốt nhất mỗi tác vụ dùng buffer riêng. Nếu cần đọc đủ một record, lặp positional read và cộng offset theo số byte thực sự nhận được.

Khi thao tác nghiệp vụ thật sự cần con trỏ chung, có thể khóa một vùng lệnh:

~~~java
synchronized (channel) {
    channel.position(100);
    while (bufferA.hasRemaining()) {
        int n = channel.read(bufferA);
        if (n < 0) throw new java.io.EOFException();
        if (n == 0) throw new java.io.IOException("No read progress");
    }
}
~~~

Đây là **mảnh mã minh họa**, giả sử channel/buffer đã khai báo. Khóa chỉ phát huy tác dụng nếu **mọi code liên quan đến vị trí chung cùng tuân theo giao thức này**. Monitor trên `channel` không ngăn một thành phần khác gọi `channel.read(...)` mà không lấy monitor đó. Khi chỉ cần offset định trước, overload positional thường làm hợp đồng đơn giản hơn.

## 5. Ví dụ chạy được: chia sẻ con trỏ và đọc ở offset độc lập

Chương trình Java 17+ dưới đây tạo một tệp tạm có 10 byte ASCII, sau đó cho hai thread dùng **cùng một `FileChannel`** qua hai kiểu truy cập.

Phần A: hai thread đọc bằng `read(buffer)`, cùng đi trên một file position. `CountDownLatch` buộc A đọc trước 2 byte, B đọc tiếp 2 byte, rồi A đọc byte cuối. Ví dụ dùng `synchronized(channel)` trong helper để toàn bộ vòng lặp đọc một khối không bị chen ngang nếu `FileChannel.read` trả về ít byte hơn yêu cầu. Vì thế output không dựa vào may rủi của race.

Phần B: hai thread dùng `read(buffer, offset)` với các offset 0 và 5, mỗi thread giữ `ByteBuffer` riêng. Khi chỉ có concurrent reads trên một tệp không thay đổi, chúng thu được hai vùng đúng mong muốn, trong khi file position của channel không dịch.

Tạo tệp `ChannelPositionDemo.java`:

~~~java
import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.concurrent.*;

public class ChannelPositionDemo {
  static void await(CountDownLatch latch) {
    try {
      latch.await();
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException(e);
    }
  }

  static String relative(FileChannel ch, int size) throws IOException {
    ByteBuffer b = ByteBuffer.allocate(size);
    synchronized (ch) {
      while (b.hasRemaining()) {
        int n = ch.read(b);
        if (n < 0) throw new EOFException();
        if (n == 0) throw new IOException("No read progress");
      }
    }
    return new String(b.array(), StandardCharsets.US_ASCII);
  }

  static String at(FileChannel ch, long p, int size) throws IOException {
    ByteBuffer b = ByteBuffer.allocate(size);
    while (b.hasRemaining()) {
      int n = ch.read(b, p);
      if (n < 0) throw new EOFException();
      if (n == 0) throw new IOException("No read progress");
      p += n;
    }
    return new String(b.array(), StandardCharsets.US_ASCII);
  }

  public static void main(String[] args) throws Exception {
    Path path = Files.createTempFile("nio-demo-", ".bin");
    try (FileChannel ch = FileChannel.open(path,
        StandardOpenOption.READ, StandardOpenOption.WRITE)) {
      ByteBuffer input = ByteBuffer.wrap(
          "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII));
      while (input.hasRemaining()) {
        int n = ch.write(input, (long) input.position());
        if (n <= 0) throw new IOException("No write progress");
      }
      System.out.println("Initial position: " + ch.position());

      CountDownLatch aDone = new CountDownLatch(1);
      CountDownLatch bDone = new CountDownLatch(1);
      String[] a = new String[2], b = new String[1];

      Thread ta = new Thread(() -> {
        try {
          a[0] = relative(ch, 2);
          aDone.countDown();
          await(bDone);
          a[1] = relative(ch, 1);
        } catch (IOException e) {
          throw new UncheckedIOException(e);
        }
      });
      Thread tb = new Thread(() -> {
        await(aDone);
        try {
          b[0] = relative(ch, 2);
          bDone.countDown();
        } catch (IOException e) {
          throw new UncheckedIOException(e);
        }
      });
      ta.start();
      tb.start();
      ta.join();
      tb.join();

      System.out.println("A relative: " + a[0] + " then " + a[1]);
      System.out.println("B relative: " + b[0]);
      System.out.println("Position after relative: " + ch.position());

      ch.position(0);
      String[] result = new String[2];
      Thread t1 = new Thread(() -> {
        try {
          result[0] = at(ch, 0, 5);
        } catch (IOException e) {
          throw new UncheckedIOException(e);
        }
      });
      Thread t2 = new Thread(() -> {
        try {
          result[1] = at(ch, 5, 5);
        } catch (IOException e) {
          throw new UncheckedIOException(e);
        }
      });
      t1.start();
      t2.start();
      t1.join();
      t2.join();

      System.out.println("At 0: " + result[0]);
      System.out.println("At 5: " + result[1]);
      System.out.println("Position after positional: " + ch.position());
    } finally {
      Files.deleteIfExists(path);
    }
  }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac ChannelPositionDemo.java
java ChannelPositionDemo
~~~

Stdout:

~~~text
Initial position: 0
A relative: AB then E
B relative: CD
Position after relative: 5
At 0: ABCDE
At 5: FGHIJ
Position after positional: 0
~~~

Code đã được chạy thử trên JDK với đầu ra như trên; phiên bản có thêm kiểm tra tiến độ trong vòng lặp giữ nguyên logic cho tệp thông thường.

**Cách đọc kết quả:**

1. Lần ghi `write(input, offset)` đi từ offset tường minh, nên sau khi ghi 10 byte, `ch.position()` vẫn là 0. Buffer `input` lại dịch position tới cuối dữ liệu.
2. Trong phần tương đối, thread A đọc `AB`; B tiếp tục đọc `CD`; A sau đó đọc `E`. Không thread nào có file position “của riêng mình”; `ch.position()` sau ba lượt bằng 5.
3. Sau khi chủ động đặt `ch.position(0)`, hai thread khác đọc trực tiếp các đoạn [0, 4] và [5, 9] bằng `read(buffer, offset)`. Cả hai thu được dữ liệu đúng, và file position vẫn là 0.
4. `CountDownLatch` tạo thứ tự xác định cho lượt đọc đầu. `Thread.join()` chờ thread hoàn tất và bảo đảm main nhìn thấy kết quả được ghi vào hai mảng trong ví dụ.
5. Mỗi lời gọi helper dùng buffer **mới**. Hai thread không có data race trên `ByteBuffer.position()`. Phần positional không có concurrent writer nên không phải giải quyết xung đột nội dung tệp.

**Lưu ý về xử lý lỗi ví dụ:** để tập trung vào file position, code dùng thread thường và in kết quả sau `join()`. Ứng dụng thực tế nên thu nhận lỗi phát sinh trong thread bằng `Future.get()`, `CompletableFuture` hoặc cơ chế tương đương, rồi đảm bảo latch/future thất bại đúng cách; không để một thread chờ vô hạn khi thread khác kết thúc vì exception.

## 6. Chọn thao tác tương đối hay có vị trí tường minh?

| Tình huống | Lựa chọn | Lý do |
| --- | --- | --- |
| Một luồng đọc tuần tự cả tệp | `read(dst)` | File position tự tiến, code đơn giản |
| Các thread xử lý record ở offset riêng | `read(dst, offset)` | Không tranh chấp file position chung |
| Nhiều worker ghi block không giao nhau | `write(src, offset)` + mỗi worker có buffer riêng | Mỗi worker biết rõ vị trí |
| Cần một con trỏ đọc tuần tự phục vụ nhiều consumer | Xác định rõ một owner hoặc dùng lock/queue | Tránh xen kẽ logic giữa các lời gọi |
| Phải thay đổi vị trí rồi đọc một giao dịch gồm nhiều lời gọi | Khóa bao trọn chuỗi, hoặc đổi sang positional | `position()+read()` không nguyên tử |
| Cần cập nhật một record nhiều trường cùng lúc | Thiết kế cơ chế lock/version/transaction ở tầng record | Positional write một mình không cho atomicity |
| Cần append từ nhiều producer | Một writer tập trung, cơ chế cấp phát offset hoặc chính sách append có kiểm chứng | Concurrent append phụ thuộc nền tảng và chính sách ghi |

Dùng **positional I/O** không có nghĩa có thể bỏ qua giới hạn file size, độ dài buffer, quyền truy cập hoặc phối hợp khi nhiều thread ghi trùng vùng.

## 7. Kích thước tệp và các thao tác thay đổi file size

`FileChannel` có quy tắc tuần tự hóa đặc biệt với thao tác **có thể thay đổi kích thước tệp**, ngay cả khi nó nhận vị trí tường minh. Chẳng hạn, ghi tại offset lớn hơn EOF hiện tại có thể làm file dài hơn. Vì vậy không được nói “mọi `write(buffer, offset)` chắc chắn chạy song song” hay dùng việc có tham số `offset` làm bằng chứng tối ưu hóa concurrency.

Một số trường hợp:

- **Đọc ở offset ngoài EOF**: `read(dst, offset)` trả về `-1` khi đang ở hoặc vượt cuối tệp (nếu buffer còn byte để ghi), không tự thêm dữ liệu.
- **Ghi vượt EOF**: `write(src, offset)` có thể mở rộng tệp. Khoảng trống giữa EOF cũ và offset ghi chịu quy tắc của file system; không suy diễn đây là một record hợp lệ.
- **`truncate(newSize)`** có thể làm tệp ngắn đi. Nếu file position đang lớn hơn size sau truncate, vị trí channel được điều chỉnh theo hợp đồng API. Reader cùng lúc có thể gặp EOF sớm hơn hoặc mất phần dữ liệu dự kiến.
- **`size()` trả trạng thái tại một thời điểm**. Phép `long pos = channel.size(); channel.write(src, pos);` không tự tạo append nguyên tử. Nhiều thread có thể cùng đọc một size rồi cùng chọn offset đó.
- **`force(true)`** yêu cầu đẩy các cập nhật xuống thiết bị lưu trữ theo bảo đảm API và thiết bị, nhưng không thay thế mutex, không cấp transaction và không khiến nhiều write thành một phép cập nhật nguyên tử.

Nếu thiết kế nhiều thread cần append, hãy cấp phát offset không trùng bằng một coordinator có đồng bộ; nếu file size thay đổi động, cần quản lý vòng đời/trạng thái cấu trúc của tệp. Hạn chế trộn `truncate` hoặc mở rộng file với những worker đang dùng offset cũ mà không có giao thức.

## 8. Buffer được truyền vào FileChannel cũng là tài nguyên có trạng thái

Các overload positional giữ nguyên **file position**, nhưng vẫn cập nhật **buffer position**. Ví dụ hai thread đều gọi:

~~~java
channel.read(sharedBuffer, 0L);
channel.read(sharedBuffer, 128L);
~~~

Đây là đoạn minh họa sai nếu hai thread dùng chung `sharedBuffer` mà thiếu đồng bộ/ownership. Dù offset file khác nhau, cả hai còn tranh chấp `sharedBuffer.position()`, có thể cùng ghi vào backing storage. `ByteBuffer` không mặc nhiên thread-safe.

Cách tổ chức thường dùng:

- Mỗi thread/tác vụ sở hữu `ByteBuffer` riêng và không giao buffer đó cho thread khác trước khi xong.
- Nếu dùng `duplicate()`/`slice()`, các view có cursor riêng nhưng **vẫn chia sẻ backing storage**. Chỉ ghi an toàn khi vùng nhớ không chồng lấn hoặc có đồng bộ phù hợp.
- Nếu đọc một dữ liệu bất biến, có thể dùng view chỉ đọc với safe publication và bảo đảm không alias nào đang ghi. `asReadOnlyBuffer()` ngăn ghi qua view, **không** làm byte nền bất biến.
- Một tác vụ bất đồng bộ còn sử dụng buffer thì không được đưa buffer về pool và `clear()` quá sớm.

Trong ví dụ đầy đủ, helper `at(...)` tạo `ByteBuffer.allocate(size)` mới cho từng lần đọc, tách trạng thái buffer một cách rõ ràng.

## 9. Xử lý partial read/write và offset theo số byte thực tế

Một lời gọi `read(dst, offset)` có thể trả về ít byte hơn `dst.remaining()`. Khi đọc cả record kích thước cố định, cần tăng **offset file tường minh** sau từng lần đọc:

~~~java
long current = recordOffset;
while (dst.hasRemaining()) {
    int n = channel.read(dst, current);
    if (n < 0) throw new java.io.EOFException("Truncated record");
    if (n == 0) throw new java.io.IOException("No progress");
    current += n;
}
~~~

Đây là **mảnh mã minh họa**, giả sử `recordOffset`, `channel` và `dst` hợp lệ. Quan trọng là tăng `current` theo `n`; nếu luôn đọc lại ở cùng `recordOffset` trong vòng lặp, dữ liệu có thể bị lặp trong buffer.

Tương tự với positional write:

~~~java
long current = recordOffset;
while (src.hasRemaining()) {
    int n = channel.write(src, current);
    if (n <= 0) throw new java.io.IOException("No write progress");
    current += n;
}
~~~

Ở đây `src.position()` cũng tăng theo `n`, nhưng **file position chung** không đổi. Khi tính offset cho record thứ N, dùng `long` và phép kiểm tra tràn:

~~~java
long offset = Math.addExact(
        headerSize, Math.multiplyExact(recordIndex, recordSize));
~~~

Đây là mảnh minh họa giả sử `headerSize`, `recordIndex` và `recordSize` là các giá trị kiểu `long` không âm hợp lệ. Nếu offset được tính sai hoặc hai worker nhận cùng index, positional I/O có thể ghi đè dữ liệu của nhau mặc dù hoàn toàn không tranh chấp file position.

## 10. Ghi đồng thời: không có bảo đảm một record là nguyên tử

Hai thread được giao các vùng không giao nhau như [0, 999] và [1000, 1999] có thể dùng cùng channel với positional I/O. Thiết kế đó tránh trùng vị trí dữ liệu nếu từng thread có buffer riêng, tệp đã được chuẩn bị kích thước phù hợp và không có thread khác `truncate` hoặc sửa chồng lấn.

Nhưng nếu hai thread ghi **cùng vùng**:

~~~java
// Writer A
channel.write(dataA, 4096L);

// Writer B
channel.write(dataB, 4096L);
~~~

Đây là **mảnh mã minh họa**. Không thể mặc định toàn bộ bytes cuối cùng chắc chắn là của A hoặc B, hay một lời gọi `write` luôn ghi đủ cả buffer. Việc các lời gọi được tuần tự hóa trong vài hoàn cảnh cũng không làm **toàn bộ chuỗi read-modify-write** thành giao dịch nguyên tử. Với thao tác cập nhật số dư, số phiên bản, trạng thái và checksum trong cùng một record, cần khóa/chốt phiên bản hoặc giao thức storage nhất quán ở tầng cao hơn.

Nếu cần cập nhật bền vững và khôi phục sau crash, cân nhắc copy-on-write, checksum + version, write-ahead log hoặc cơ sở dữ liệu có transaction. Tránh coi `channel.force(true)` hay `channel.lock()` là bằng chứng tự động có transaction.

## 11. FileLock và nhiều FileChannel đến cùng một tệp

`FileChannel.lock(...)` hoặc `tryLock(...)` hỗ trợ khóa vùng tệp trong những trường hợp cần điều phối truy cập. Nhưng cần biết:

- Khóa tệp được tổ chức ở tầng hệ điều hành/provider và có các khác biệt theo nền tảng (advisory hoặc mandatory, mức hỗ trợ vùng, thời điểm áp dụng).
- Khóa theo vùng byte, không phải luôn lock mọi dữ liệu. Phải định nghĩa rõ vùng cần bảo vệ.
- Khóa file **được giữ thay mặt cho toàn bộ JVM**. Khi cố lấy khóa chồng lấn với khóa JVM đã giữ hoặc yêu cầu đang chờ, có thể nhận `OverlappingFileLockException` thay vì khóa này trở thành mutex lý tưởng giữa hai thread cùng JVM.
- Đừng dùng `FileLock` làm cơ chế khóa thread nội bộ duy nhất. Dùng `synchronized`, `ReentrantLock` hoặc bộ quản lý ownership trong JVM khi cần phối hợp giữa worker; dùng file lock khi cần hợp tác với tiến trình khác và đã xác định rõ giới hạn nền tảng.
- Nếu nhiều channel khác nhau cùng mở một tệp, chúng có **file position riêng**, nhưng chia sẻ nội dung tệp. Hai channel ghi vào cùng vùng vẫn cần phối hợp.

Có thể sử dụng một channel dùng chung cho nhiều worker nếu hợp đồng owner và vùng byte rõ ràng; cũng có thể dùng nhiều channel riêng tùy chi phí quản lý và đặc tính I/O. Việc có nhiều channel không tự giúp cập nhật cùng vùng trở thành an toàn.

## 12. Các lỗi phổ biến và cách sửa

| Nhận định hoặc thao tác sai | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “FileChannel thread-safe nên `position(100); read(dst)` luôn bắt đầu ở 100” | Thread khác có thể xen vào giữa hai lời gọi | Dùng `read(dst, 100L)` hoặc khóa cả chuỗi |
| “Hai thread dùng `read(dst)` nên mỗi thread có con trỏ riêng” | Một `FileChannel` có file position dùng chung | Một owner đọc tuần tự, hoặc positional I/O |
| “`read(dst, offset)` không đổi trạng thái nào cả” | Buffer position vẫn tăng | Mỗi tác vụ có buffer riêng hoặc đồng bộ |
| “Có offset nghĩa là FileChannel buộc chạy song song” | Hợp đồng cho phép implementation tuần tự hóa | Không dựa vào tính song song làm tính đúng đắn |
| “Ghi explicit offset không thể kéo dài file” | Ghi vượt EOF có thể tăng kích thước | Kiểm soát size, ranh giới và cấp phát offset |
| “Hai thread đọc `size()` rồi cùng append là ổn” | Cả hai có thể chọn cùng offset | Cấp phát offset bằng coordinator |
| “Gọi `read` một lần luôn điền đủ buffer” | Partial I/O được phép | Lặp, theo dõi bytes và xử lý EOF |
| “Dùng chung `ByteBuffer` là được vì channel có lock” | Buffer có cursor và backing memory riêng | Không chia sẻ mutable buffer ngoài hợp đồng |
| “`force(true)` làm các update nguyên tử” | Durability và atomicity khác nhau | Transaction/WAL/version tùy yêu cầu |
| “Một `FileLock` là mutex hoàn chỉnh giữa các thread trong JVM” | Cơ chế khóa file và lock overlap khác mutex nội bộ | Dùng khóa JVM và giao thức ownership |
| “Có thể `close()` channel khi thread khác còn I/O” | Có thể gây `AsynchronousCloseException`/đọc ghi thất bại | Một owner quản lý đóng sau khi worker kết thúc |

### Quy trình chọn API trong ứng dụng

1. Xác định tác vụ đọc/ghi **tuần tự** hay có **offset riêng**.
2. Xác định mỗi thread có `ByteBuffer` riêng hay có cùng backing storage.
3. Nếu thao tác có nhiều lời gọi, xác định cần nguyên tử ở **mức một lời gọi** hay **mức một record/giao dịch**.
4. Kiểm tra liệu ghi có làm thay đổi **file size** hoặc xung đột với truncate hay không.
5. Với nhiều writer, xác lập cơ chế cấp phát vùng không chồng lấn và chính sách retry/error.
6. Đóng channel chỉ sau khi mọi task sử dụng nó đã hoàn thành; truyền lỗi về nơi sở hữu để không bỏ sót I/O thất bại.

## 13. Tự kiểm tra

**Câu 1.** `channel.position() == 10`; thread A đọc được 3 byte bằng `read(dst, 100)`. File position của channel thành bao nhiêu?

**Đáp án:** 10. Overload có offset tường minh không thay đổi file position; `dst.position()` lại tăng thêm 3 nếu đọc được 3 byte.

**Câu 2.** Hai thread cùng gọi `channel.position(x)` rồi `channel.read(buffer)` theo hai offset khác nhau. Tại sao vẫn có lỗi dù channel thread-safe?

**Đáp án:** Vì hai lời gọi của một thread không được coi là một giao dịch. Thread khác có thể thay đổi vị trí chung giữa `position(x)` và `read(buffer)`.

**Câu 3.** Hai thread đọc hai vùng không chồng lấn với `read(dst, offset)`. Có cần dùng chung một `ByteBuffer` cho tiết kiệm bộ nhớ không?

**Đáp án:** Không. Nên dùng buffer riêng cho mỗi task để tách trạng thái cursor và byte nền; offset file không thay đổi không có nghĩa buffer position không thay đổi.

**Câu 4.** Hai `write(src, offset)` có offset khác nhau có luôn chạy song song không?

**Đáp án:** Không. Hợp đồng cho phép concurrency trong nhiều trường hợp, nhưng việc thực thi song song tùy implementation; nếu thao tác có thể đổi kích thước tệp còn có quy tắc tuần tự hóa liên quan.

**Câu 5.** Ghi block mới tại EOF bằng `long p = channel.size(); channel.write(src, p)` ở 10 thread có đảm bảo append không trùng không?

**Đáp án:** Không. Tính size và ghi là hai thao tác tách rời; nhiều thread có thể lấy cùng `p`. Cần cơ chế cấp phát offset hoặc writer điều phối.

**Câu 6.** `FileChannel.lock()` có thay thế luôn `ReentrantLock` dùng giữa các thread trong JVM không?

**Đáp án:** Không. File lock hướng đến phối hợp quyền truy cập vùng tệp và có đặc tính phụ thuộc hệ điều hành; khóa chồng lấn trong cùng JVM có thể ném `OverlappingFileLockException`.

## Tài liệu API

- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): hợp đồng concurrent access; overload read/write với vị trí chung và vị trí tường minh; file locking, truncate, force.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): buffer position/limit, chuyển byte khi read/write, thread safety của buffer.
- [Java SE 17 — FileLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileLock.html): khóa vùng, phạm vi JVM và các giới hạn theo nền tảng.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối thứ tự và quan hệ happens-before.
