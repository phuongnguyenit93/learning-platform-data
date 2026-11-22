# Tính bắc cầu của happens-before

## 1. Một bảo đảm có thể đi qua nhiều mắt xích

Quan hệ **happens-before**, viết tắt HB, cho phép suy luận về thứ tự và khả năng nhìn thấy dữ liệu giữa các hành động trong chương trình Java.

Tính bắc cầu phát biểu:

```text
A happens-before B
B happens-before C
───────────────────
A happens-before C
```

A, B và C là các hành động, không nhất thiết nằm cùng một luồng. Nhờ quy tắc này, dữ liệu có thể được công bố qua một chuỗi luồng hoặc công cụ đồng bộ, thay vì người đọc cuối phải trao đổi trực tiếp với người ghi đầu. [JLS §17.4.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5)

Mỗi mắt xích phải có cơ sở. “Luồng B có vẻ chạy sau luồng A” hoặc “đã đợi một giây” không tự tạo happens-before.

## 2. Hai loại mắt xích thường ghép với nhau

### Thứ tự trong cùng một luồng

Một hành động có quan hệ HB với hành động đi sau theo thứ tự chương trình của chính luồng đó. Ví dụ:

```text
ghi payload
    → gọi phương thức công bố
```

### Quan hệ giữa các luồng

Các cơ chế như monitor, volatile, start/join và những lớp concurrent có hợp đồng tạo các quan hệ cần thiết. Ví dụ với latch:

```text
Luồng A: các hành động trước countDown
    → Luồng B: các hành động sau await thành công tương ứng
```

Không chỉ thao tác trên biến cờ được công bố. Các ghi dữ liệu diễn ra trước điểm công bố cũng có thể nằm trong chuỗi HB đến người nhận. [Hiệu ứng bộ nhớ CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

## 3. Ví dụ chuỗi ba luồng

Giả sử có hai latch:

- `prepared`: producer báo dữ liệu đầu đã sẵn sàng.
- `forwarded`: relay báo giai đoạn trung gian đã xong.

Chuỗi hành động:

```text
Producer:
  ghi payload = 42
  countDown(prepared)
          ↓
Relay:
  await(prepared) thành công
  ghi version = 7
  countDown(forwarded)
          ↓
Consumer:
  await(forwarded) thành công
  đọc payload và version
```

Consumer không trực tiếp chờ prepared. Relay cũng không cần đọc payload rồi ghi lại để “chuyển dữ liệu”. Các mắt xích đồng bộ và thứ tự chương trình đã nối việc ghi payload tới lần đọc cuối.

### Chương trình đầy đủ

Lưu vào **TransitiveHappensBeforeDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class TransitiveHappensBeforeDemo {
    static final class Data {
        int payload;
        int version;
    }

    record Snapshot(int payload, int version) {
    }

    public static void main(String[] args) throws Exception {
        Data data = new Data();
        CountDownLatch prepared = new CountDownLatch(1);
        CountDownLatch forwarded = new CountDownLatch(1);
        ExecutorService executor =
                Executors.newFixedThreadPool(3);

        try {
            Future<?> producer = executor.submit(() -> {
                data.payload = 42;
                prepared.countDown();
            });

            Future<?> relay = executor.submit(() -> {
                prepared.await();
                data.version = 7;
                forwarded.countDown();
                return null;
            });

            Future<Snapshot> consumer = executor.submit(() -> {
                forwarded.await();
                return new Snapshot(data.payload, data.version);
            });

            producer.get();
            relay.get();
            Snapshot result = consumer.get();

            System.out.println("payload=" + result.payload());
            System.out.println("version=" + result.version());
            System.out.println("sum="
                    + (result.payload() + result.version()));
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 TransitiveHappensBeforeDemo.java
java TransitiveHappensBeforeDemo
```

Kết quả khi các tác vụ hoàn tất bình thường:

```text
payload=42
version=7
sum=49
```

payload và version là các trường int thường. Chúng không cần volatile trong ví dụ vì những lần ghi và đọc liên quan đã có đường happens-before phù hợp, và không có bên nào tiếp tục ghi cạnh tranh sau bước công bố tương ứng.

Future.get còn chuyển kết quả Snapshot từ consumer về main theo hợp đồng bộ nhớ của Future. Nó không thay thế những latch ở bên trong chuỗi producer → relay → consumer. [Hiệu ứng bộ nhớ của thư viện concurrent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html)

## 4. Chứng minh từng mắt xích

Đặt tên cho các hành động:

| Ký hiệu | Hành động |
| --- | --- |
| W | Producer ghi payload = 42 |
| P | Producer countDown(prepared) |
| R | Relay trở về thành công từ prepared.await() |
| F | Relay countDown(forwarded) |
| C | Consumer trở về thành công từ forwarded.await() |
| Q | Consumer đọc payload |

Ta có:

```text
W → P    theo thứ tự producer
P → R    theo hợp đồng prepared
R → F    theo thứ tự relay
F → C    theo hợp đồng forwarded
C → Q    theo thứ tự consumer

Suy ra W → Q nhờ tính bắc cầu.
```

Bảng dùng cách viết rút gọn các điểm đồng bộ để nhìn đường đi. Điều cần kiểm tra là hành động ghi nằm **trước** countDown, còn lần đọc nằm **sau** await thành công.

Tương tự, việc relay ghi version = 7 trước F có đường tới lần consumer đọc version. Không có phép ghi version khác sau đó, nên kết quả 7 được bảo đảm trong chương trình này.

Relay không đọc payload. Điều đó giúp tránh cách hiểu sai rằng mỗi luồng trung gian phải “chạm vào” từng trường để dữ liệu được truyền tiếp. Chính quan hệ giữa các hành động mới là cơ sở suy luận.

## 5. Chuỗi có thể ghép nhiều cơ chế khác nhau

Không cần toàn bộ đường đi dùng cùng một loại công cụ. Chẳng hạn:

```text
Main ghi input
  → start(workerA)
  → workerA ghi stage
  → Main join(workerA) hoàn tất
  → start(workerB)
  → workerB đọc stage, ghi output
  → Main join(workerB) hoàn tất
  → Main đọc output
```

Các hành động trước start được công bố cho luồng mới; hành động của một luồng đã kết thúc có quan hệ với bên join phát hiện sự kết thúc. Ghép thêm thứ tự ở main tạo được đường từ workerA tới workerB. [API Thread.join](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#join()), [JLS: start và join](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5)

### Chương trình start/join đầy đủ

Lưu thành **StartJoinChainDemo.java**:

```java
public class StartJoinChainDemo {
    static final class Data {
        int input;
        int stage;
        int output;
    }

    public static void main(String[] args)
            throws InterruptedException {
        Data data = new Data();
        data.input = 21;

        Thread first = new Thread(() -> {
            data.stage = data.input * 2;
        });

        first.start();
        first.join();

        Thread second = new Thread(() -> {
            data.output = data.stage * 2;
        });

        second.start();
        second.join();

        System.out.println("input=" + data.input);
        System.out.println("stage=" + data.stage);
        System.out.println("output=" + data.output);
    }
}
```

Chạy:

```shell
javac --release 17 -encoding UTF-8 StartJoinChainDemo.java
java StartJoinChainDemo
```

Kết quả:

```text
input=21
stage=42
output=84
```

Nếu main khởi động cả hai luồng ngay rồi mới join chúng ở cuối, không còn đường workerA hoàn tất → main → start(workerB) như chương trình trên. Việc main cuối cùng thấy cả hai đã xong không bảo đảm workerB đã đọc stage sau lần workerA ghi 42.

Đây là ví dụ tính bắc cầu có **chiều**. Không thể đảo một mũi tên chỉ vì nó nối cùng hai luồng.

## 6. Dùng queue để chuyển dữ liệu qua các giai đoạn

Một pipeline có thể tạo chuỗi:

```text
producer chuẩn bị đối tượng
  → put vào queue thứ nhất
  → relay take đúng đối tượng đó
  → relay xử lý
  → put vào queue thứ hai
  → consumer take đối tượng
  → consumer đọc dữ liệu
```

BlockingQueue quy định hành động trước khi đặt một phần tử vào queue có quan hệ happens-before với hành động sau khi luồng khác truy cập hoặc lấy phần tử tương ứng. Kết hợp hai lần chuyển với thứ tự của relay tạo đường công bố nhiều giai đoạn. [API BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

Cần gắn lập luận với **phần tử được chuyển tương ứng**. Không suy ra rằng chỉ vì hai luồng dùng cùng một queue ở đâu đó thì mọi hành động của chúng đều tự được sắp thứ tự.

Nếu producer tiếp tục sửa một đối tượng sau khi put, các sửa đổi đó không mặc nhiên nằm trước lần consumer đọc. Hãy chuyển quyền sở hữu hoặc dùng dữ liệu bất biến, hoặc thiết kế đồng bộ riêng cho việc sửa về sau.

## 7. Những nơi chuỗi suy luận bị đứt

### Không có cạnh liên luồng thật sự

Đổi latch thành hai biến boolean thường không tự giữ được hợp đồng. Chạy đúng theo một lần thử không tạo thêm quan hệ HB.

### Ghi dữ liệu sau điểm công bố

```java
prepared.countDown();
data.payload = 42;
```

Đây là đoạn cố ý đảo sai thứ tự so với chương trình đầu. Hợp đồng latch không đưa phép ghi payload ở sau countDown sang trước await của người nhận. Không được dùng tính bắc cầu để bù cho một cạnh không tồn tại.

### Dùng sai đối tượng đồng bộ

Mở khóa monitor X rồi luồng kia khóa monitor Y không tạo cạnh mở–khóa tương ứng. Tương tự, chờ một latch khác không nối với latch mà producer đã countDown.

### await chưa thành công

Một await có thời hạn trả false vì hết hạn không phải thông báo rằng dữ liệu đã sẵn sàng. Nếu bị ngắt và ném InterruptedException, cũng không được tiếp tục đọc như thể đường đồng bộ mong muốn đã hoàn tất.

Ví dụ trong bài dùng await không thời hạn, đồng thời main lấy Future để phát hiện lỗi tác vụ. Phần finally ngắt tác vụ còn lại khi main kết thúc xử lý lỗi. Với một hệ thống thực tế, cần thêm chính sách thời hạn/hủy phù hợp thay vì để một giai đoạn hỏng khiến các giai đoạn khác chờ vô hạn. [Hợp đồng await của CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

### Có các ghi cạnh tranh về sau

Nếu W có đường tới Q nhưng một luồng khác còn ghi cùng biến mà không theo giao thức, không thể dùng đường W → Q để khẳng định Q luôn đọc đúng giá trị từ W. Cần xét toàn bộ các truy cập và những ghi có thể chen vào, không chỉ một đường thuận lợi đã chọn.

## 8. Bắc cầu không biến nhiều bước thành nguyên tử

Giả sử hai luồng đều nhìn thấy đúng số vé hiện tại. Điều đó chưa ngăn cả hai cùng kiểm tra “còn vé” rồi trừ hai lần. HB giúp suy luận về khả năng quan sát và thứ tự liên quan; đơn vị cập nhật nghiệp vụ vẫn phải được bảo vệ bằng khóa chung hoặc thao tác atomic phù hợp.

Tương tự, các trường payload và version trong ví dụ có kết quả nhất quán vì quy trình chia giai đoạn và không có cập nhật cạnh tranh sau công bố. Nếu người ghi tiếp tục đổi cả hai trường trong lúc người đọc đọc, không thể coi mọi cặp giá trị là một ảnh chụp nguyên tử chỉ vì từng phần từng được công bố.

HB là một quan hệ thứ tự bộ phận. Hai hành động không có đường nối theo một chiều có thể vẫn chưa được sắp thứ tự với nhau. Không biến sơ đồ một số đường đi thành một thứ tự toàn cục giả tạo cho mọi hành động.

### Không dùng thời gian chờ làm bằng chứng

`Thread.sleep` không tạo đồng bộ bộ nhớ. Cho relay ngủ lâu hơn producer có thể đổi xác suất quan sát một kết quả, nhưng không tạo cạnh W → Q. Tương tự, log đúng thứ tự trên màn hình không thay cho lập luận dựa vào hợp đồng đồng bộ.

## 9. Cách lập luận trong mã thật

Một quy trình ngắn:

1. Chọn lần ghi và lần đọc cần chứng minh.
2. Ghi rõ chúng nằm ở những luồng/giai đoạn nào.
3. Vẽ các cạnh thứ tự trong từng luồng.
4. Thêm các cạnh liên luồng theo hợp đồng cụ thể.
5. Kiểm tra có đường đi có hướng từ ghi đến đọc.
6. Xem còn ghi cạnh tranh, thay đổi sau công bố hoặc dữ liệu chia sẻ khác không.
7. Chỉ đưa kết luận trong phạm vi đường đi thực sự chứng minh được.

Đây là cách tránh những lời giải thích mơ hồ như “dùng thư viện concurrent thì dữ liệu sẽ ổn”. Công cụ đúng phải được sử dụng tại đúng vị trí và với đúng thứ tự thao tác.

### Tự thực hành

1. Trong chương trình đầu, đổi relay thành không ghi version. Vì sao payload vẫn có thể được công bố qua relay dù relay không đọc nó?
2. Đưa phép ghi payload xuống sau prepared.countDown(). Chỉ ra chính xác cạnh nào không còn đúng.
3. Cho main start cả hai worker trong chương trình thứ hai trước khi join. Vì sao không được hứa output=84?
4. Thay một latch bằng biến boolean thường. Cần bổ sung điều gì mới có một cạnh đồng bộ hợp lệ?
5. Nếu producer sửa payload lần nữa sau khi đã countDown, kết luận về lần consumer đọc cần xem lại thế nào?
6. Vẽ chuỗi producer → queue → relay → Future → main và xác định từng hợp đồng giúp tạo đường HB.
