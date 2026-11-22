# Decorator và bổ sung hành vi trong Java

> **Chủ đề:** OOP → Mẫu thiết kế → **Decorator Pattern**.  
> **Mục tiêu:** hiểu cách mở rộng hành vi đối tượng bằng cách bọc (*wrap*) đối tượng khác cùng hợp đồng, phối hợp nhiều decorator, kiểm soát thứ tự thực thi và nhận biết tình huống không nên áp dụng.

## 1. Bài toán: thêm hành vi mà không sửa mọi implementation

Giả sử ứng dụng có một thành phần gửi thông báo:

~~~java
interface MessageChannel {
    void send(Message message);
}
~~~

Ban đầu, một **ConsoleChannel** ghi thông báo ra console để thử nghiệm. Sau đó xuất hiện yêu cầu:

- Thêm tiền tố **[APP]** vào nội dung trước khi gửi.
- Chặn nội dung dài quá giới hạn.
- Đếm số lời gọi xử lý thành công qua chuỗi gửi.
- Sau này có thể có **EmailChannel**, **SmsChannel** hay adapter cho nhà cung cấp thứ ba.

Một cách làm vội là bổ sung logic tiền tố, kiểm tra độ dài, đếm và ghi log vào mọi lớp gửi thông báo. Cách này lặp logic; mỗi thay đổi quy định chung lại kéo theo nhiều implementation. Cách khác là tạo các lớp con kiểu **LoggedEmailChannel**, **CheckedEmailChannel**, **CheckedLoggedEmailChannel**… Số tổ hợp kế thừa sẽ khó quản lý, đặc biệt khi hành vi phải bật/tắt linh hoạt.

**Decorator** giải quyết tình huống này bằng **composition**: một đối tượng triển khai cùng interface với đối tượng được bọc, giữ tham chiếu đến đối tượng đó, rồi thêm hành vi trước hoặc sau khi ủy quyền lời gọi.

~~~mermaid
flowchart LR
    Client["Client"] --> Count["CountingDecorator"]
    Count --> Prefix["PrefixDecorator"]
    Prefix --> Limit["LengthLimitDecorator"]
    Limit --> Core["ConsoleChannel"]
    Core --> Output["Đầu ra console"]
~~~

Đường đi trong sơ đồ là thứ tự gọi **từ ngoài vào trong**. Khi lời gọi quay ra, các decorator bên ngoài có thể thực hiện thêm hành vi sau khi lớp bên trong hoàn tất.

**Ý chính:** người gọi có thể sử dụng toàn bộ chuỗi qua cùng một interface **MessageChannel** mà không cần biết chính xác nó đang được bọc bởi bao nhiêu lớp.

## 2. Cấu trúc của Decorator

| Vai trò | Trong ví dụ thông báo | Trách nhiệm |
| --- | --- | --- |
| **Component** | **MessageChannel** | Định nghĩa hợp đồng chung mà client sử dụng |
| **Concrete Component** | **ConsoleChannel** | Cung cấp hành vi gốc: nhận và xuất thông báo |
| **Decorator** | **ChannelDecorator** | Giữ tham chiếu đến một **MessageChannel** khác và tiếp tục triển khai hợp đồng |
| **Concrete Decorator** | **PrefixDecorator** | Biến đổi nội dung trước khi gửi |
| **Concrete Decorator** | **LengthLimitDecorator** | Kiểm tra điều kiện trước khi chuyển tiếp |
| **Concrete Decorator** | **CountingDecorator** | Theo dõi số lời gọi trở về thành công |
| **Client** | **main** hoặc service nghiệp vụ | Lắp chuỗi wrapper và gọi giao diện chung |

Mỗi lớp bọc có quyền gọi delegate **trước**, **sau** hoặc **xung quanh** phần hành vi bổ sung. Nó cũng có thể từ chối chuyển tiếp khi một ràng buộc công khai bị vi phạm. Tuy nhiên, thay đổi tiền điều kiện/hậu điều kiện của hợp đồng cần được thiết kế và mô tả rõ; chỉ cần cùng interface về mặt cú pháp chưa đảm bảo mọi wrapper thay thế an toàn cho nhau.

### Sơ đồ lớp

~~~mermaid
classDiagram
    class MessageChannel {
        <<interface>>
        +send(message) void
    }
    class ConsoleChannel {
        +send(message) void
    }
    class ChannelDecorator {
        <<abstract>>
        #next: MessageChannel
    }
    class PrefixDecorator {
        -prefix: String
        +send(message) void
    }
    class LengthLimitDecorator {
        -maxCodePoints: int
        +send(message) void
    }
    class CountingDecorator {
        -accepted: AtomicInteger
        +send(message) void
        +acceptedCalls() int
    }
    MessageChannel <|.. ConsoleChannel
    MessageChannel <|.. ChannelDecorator
    ChannelDecorator o--> MessageChannel : delegates
    ChannelDecorator <|-- PrefixDecorator
    ChannelDecorator <|-- LengthLimitDecorator
    ChannelDecorator <|-- CountingDecorator
~~~

Không cần bắt buộc có lớp **ChannelDecorator** trung gian nếu chỉ có một wrapper nhỏ; mỗi decorator hoàn toàn có thể trực tiếp implements **MessageChannel** và nhận một **MessageChannel** trong constructor. Lớp trừu tượng trung gian chỉ có ích khi thực sự giảm lặp, chẳng hạn cùng logic kiểm tra delegate khác null.

## 3. Ví dụ Java 17 chạy độc lập

Tạo file **DecoratorDemo.java**. Ví dụ dùng **record Message** để thông điệp có giá trị bất biến, **AtomicInteger** để đếm lời gọi qua một wrapper, và **String.codePointCount** để giới hạn theo Unicode code point thay vì chỉ theo số đơn vị UTF-16 của **String.length()**.

~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class DecoratorDemo {

    public record Message(String recipient, String body) {
        public Message {
            if (recipient == null || recipient.isBlank()) {
                throw new IllegalArgumentException(
                        "Người nhận không được rỗng");
            }
            if (body == null || body.isBlank()) {
                throw new IllegalArgumentException(
                        "Nội dung không được rỗng");
            }
        }
    }

    public interface MessageChannel {
        void send(Message message);
    }

    // Thành phần gốc: chỉ giả lập gửi bằng console.
    public static final class ConsoleChannel implements MessageChannel {
        @Override
        public void send(Message message) {
            Objects.requireNonNull(message, "message");
            System.out.println(
                    "SEND " + message.recipient()
                    + ": " + message.body());
        }
    }

    // Lớp nền tùy chọn: giữ delegate của chuỗi decorator.
    public static abstract class ChannelDecorator
            implements MessageChannel {

        protected final MessageChannel next;

        protected ChannelDecorator(MessageChannel next) {
            this.next = Objects.requireNonNull(next, "next");
        }
    }

    // Thêm tiền tố nhưng không sửa đối tượng Message ban đầu.
    public static final class PrefixDecorator extends ChannelDecorator {
        private final String prefix;

        public PrefixDecorator(MessageChannel next, String prefix) {
            super(next);
            this.prefix = Objects.requireNonNull(prefix, "prefix");
        }

        @Override
        public void send(Message message) {
            Objects.requireNonNull(message, "message");
            next.send(new Message(
                    message.recipient(),
                    prefix + message.body()
            ));
        }
    }

    // Kiểm tra độ dài của thông điệp tại vị trí đặt decorator.
    public static final class LengthLimitDecorator
            extends ChannelDecorator {

        private final int maxCodePoints;

        public LengthLimitDecorator(
                MessageChannel next, int maxCodePoints) {
            super(next);
            if (maxCodePoints <= 0) {
                throw new IllegalArgumentException(
                        "Giới hạn phải lớn hơn 0");
            }
            this.maxCodePoints = maxCodePoints;
        }

        @Override
        public void send(Message message) {
            Objects.requireNonNull(message, "message");
            String body = message.body();
            int length = body.codePointCount(0, body.length());

            if (length > maxCodePoints) {
                throw new IllegalArgumentException(
                        "Thông điệp vượt quá "
                        + maxCodePoints + " Unicode code points");
            }
            next.send(message);
        }
    }

    // Chỉ đếm các lời gọi delegate trở về bình thường.
    public static final class CountingDecorator
            extends ChannelDecorator {

        private final AtomicInteger accepted = new AtomicInteger();

        public CountingDecorator(MessageChannel next) {
            super(next);
        }

        @Override
        public void send(Message message) {
            next.send(message);
            accepted.incrementAndGet();
        }

        public int acceptedCalls() {
            return accepted.get();
        }
    }

    public static void main(String[] args) {
        CountingDecorator channel = new CountingDecorator(
                new PrefixDecorator(
                        new LengthLimitDecorator(
                                new ConsoleChannel(), 80),
                        "[APP] "
                )
        );

        channel.send(new Message(
                "user-01", "Hóa đơn đã phát hành"));

        System.out.println(
                "Số lần xử lý không ném lỗi: "
                        + channel.acceptedCalls());
    }
}
~~~

Chạy trong terminal với JDK 17 trở lên:

~~~bash
javac DecoratorDemo.java
java DecoratorDemo
~~~

Kết quả:

~~~text
SEND user-01: [APP] Hóa đơn đã phát hành
Số lần xử lý không ném lỗi: 1
~~~

Trong ví dụ này, **ConsoleChannel** chỉ mô phỏng gửi thông báo bằng cách in ra màn hình. Một lời gọi trả về bình thường **không tương đương** bảo đảm người nhận thực sự nhận được email/SMS. Vì vậy, bộ đếm được đặt tên **acceptedCalls**, không phải **deliveredMessages**. Khi tích hợp hệ thống thật, cần định nghĩa trạng thái đã tiếp nhận, đã gửi tới nhà cung cấp và đã giao thành công theo hợp đồng của nhà cung cấp.

**Diễn biến lời gọi:**

1. Client gọi **CountingDecorator.send(message)**.
2. **CountingDecorator** chuyển lời gọi vào **PrefixDecorator**.
3. **PrefixDecorator** tạo một **Message** mới có tiền tố và gửi tiếp.
4. **LengthLimitDecorator** đo độ dài của nội dung **sau khi thêm tiền tố**; vượt giới hạn thì ném **IllegalArgumentException** và không gọi thành phần gốc.
5. **ConsoleChannel** in thông điệp.
6. Nếu chuỗi trở về bình thường, **CountingDecorator** tăng bộ đếm; nếu lớp trong ném exception, bộ đếm không tăng.

**Tính mở rộng:** muốn đổi cách gửi, thay **ConsoleChannel** bằng implementation **MessageChannel** khác mà vẫn có thể tái sử dụng các wrapper. Các wrapper không cần biết chi tiết thư viện HTTP, SMTP hay thiết bị đích.

## 4. Thứ tự bọc quyết định hành vi

Một trong những yếu tố dễ gây lỗi nhất của Decorator là **thứ tự**. Xét hai cách lắp:

~~~java
// A: thêm tiền tố trước, sau đó kiểm tra nội dung cuối cùng.
MessageChannel pipelineA =
        new DecoratorDemo.PrefixDecorator(
                new DecoratorDemo.LengthLimitDecorator(
                        new DecoratorDemo.ConsoleChannel(), 12),
                "[A] ");

// B: kiểm tra nội dung gốc trước, rồi mới thêm tiền tố.
MessageChannel pipelineB =
        new DecoratorDemo.LengthLimitDecorator(
                new DecoratorDemo.PrefixDecorator(
                        new DecoratorDemo.ConsoleChannel(), "[A] "),
                12);
~~~

Với nội dung gồm **10** ký tự ASCII, tiền tố **[A]** kèm dấu cách dài **4** code points:

- **pipelineA:** kiểm tra 14 code points, **từ chối** vì vượt 12.
- **pipelineB:** kiểm tra 10 code points, **chấp nhận**; thành phần gốc nhận văn bản dài 14.

Cả hai chuỗi đều đúng cú pháp Java, nhưng chỉ **pipelineA** bảo đảm thông điệp đầu ra không vượt 12 code points. Nếu dịch vụ ngoài giới hạn **số byte UTF-8**, số code point cũng **chưa đủ**: phải đo byte sau khi encode theo charset yêu cầu. Thực tế cần quy định rõ giới hạn đang nói tới byte, code point, UTF-16 code unit hay ký tự hiển thị.

Thứ tự quan trọng tương tự với nén/mã hóa, cache/phân quyền, retry/logging:

| Chuỗi bọc | Tác động có thể xảy ra | Cần quyết định |
| --- | --- | --- |
| Tiền tố → kiểm tra độ dài | Kiểm tra văn bản hoàn chỉnh | Giới hạn đo trước hay sau biến đổi? |
| Cache → phân quyền | Nếu cache phục vụ trước bước phân quyền, có thể làm lộ dữ liệu | Phải xác thực/phân quyền đúng cho mỗi request và tách cache theo ngữ cảnh phù hợp |
| Logging → retry | Wrapper log ngoài có thể chỉ thấy một lần gọi tổng thể | Muốn log một request hay từng lần thử? |
| Retry → logging | Wrapper logging bên trong có thể chạy mỗi lần thử | Có được phép gọi lại thao tác và trùng side effect không? |
| Nén → mã hóa | Thường nén dữ liệu trước khi mã hóa | Bên nhận phải giải mã rồi giải nén cùng định dạng |

Bảng mô tả ảnh hưởng về mặt cấu trúc. Với hệ thống thật, tính an toàn còn tùy contract, dữ liệu, cơ chế lưu trữ, lỗi và chính sách bảo mật của từng decorator. **Không thêm retry cho thao tác có side effect chỉ bằng việc bọc một lớp**; lệnh gửi tin, thanh toán hoặc ghi dữ liệu cần idempotency key hoặc cơ chế chống lặp phù hợp. Timeout có thể xảy ra sau khi bên nhận đã xử lý yêu cầu.

## 5. Kiểm thử từng decorator và cả chuỗi

Một lợi thế của thiết kế theo interface là dễ thay thành phần gốc bằng một **fake** nhỏ để quan sát hành vi. Ví dụ JUnit 5 dưới đây đặt trong **DecoratorDemoTest.java**, cùng package với mã nguồn mẫu.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class DecoratorDemoTest {

    static final class RecordingChannel
            implements DecoratorDemo.MessageChannel {
        DecoratorDemo.Message lastMessage;
        int calls;

        @Override
        public void send(DecoratorDemo.Message message) {
            lastMessage = message;
            calls++;
        }
    }

    @Test
    void tienToDuocThemMaKhongThayDoiMessageGoc() {
        RecordingChannel fake = new RecordingChannel();
        var channel = new DecoratorDemo.PrefixDecorator(fake, "[APP] ");
        var original =
                new DecoratorDemo.Message("u01", "Xin chào");

        channel.send(original);

        assertEquals("[APP] Xin chào", fake.lastMessage.body());
        assertEquals("Xin chào", original.body());
        assertEquals(1, fake.calls);
    }

    @Test
    void chuoiChanDuocNoiDungQuaDaiSauKhiThemTienTo() {
        RecordingChannel fake = new RecordingChannel();

        var channel = new DecoratorDemo.PrefixDecorator(
                new DecoratorDemo.LengthLimitDecorator(fake, 8),
                "[A] ");

        assertThrows(IllegalArgumentException.class, () ->
                channel.send(
                        new DecoratorDemo.Message("u01", "12345")));
        // "[A] " dài 4, cộng "12345" dài 5 = 9 > 8.
        assertEquals(0, fake.calls);
    }

    @Test
    void boDemChiTangKhiDelegateTroVeBinhThuong() {
        RecordingChannel fake = new RecordingChannel();
        var counted = new DecoratorDemo.CountingDecorator(
                new DecoratorDemo.LengthLimitDecorator(fake, 5));

        counted.send(
                new DecoratorDemo.Message("u01", "Hello"));
        assertThrows(IllegalArgumentException.class, () ->
                counted.send(
                        new DecoratorDemo.Message("u01", "123456")));

        assertEquals(1, counted.acceptedCalls());
        assertEquals(1, fake.calls);
    }
}
~~~

Các test trên không cần mạng hay máy chủ SMTP/SMS. Chúng kiểm tra chính xác điều wrapper hứa thực hiện: chuyển tiếp, biến đổi, ngăn chuyển tiếp và điều kiện tăng bộ đếm. JUnit Jupiter cần có trong classpath của dự án để chạy file test; **DecoratorDemo.java** độc lập không yêu cầu JUnit.

Nên bổ sung test tích hợp khi kết nối provider thật để kiểm tra encoding, giới hạn payload, policy retry và ánh xạ trạng thái giao hàng. Kiểm thử fake không thể chứng minh nhà cung cấp thật luôn hành xử theo giả định của fake.

## 6. Decorator khác gì các cách mở rộng quen thuộc?

| Kỹ thuật | Cách hoạt động | Nên cân nhắc khi |
| --- | --- | --- |
| **Decorator** | Một đối tượng **cùng interface** bọc đối tượng khác và thêm hành vi có thể ghép lớp | Bổ sung logging, metrics, validation, buffering, compression, transformation... cho từng instance |
| **Kế thừa** | Subclass thay đổi/mở rộng hành vi của base class | Quan hệ subtype thực sự ổn định, ít tổ hợp độc lập |
| **Proxy** | Cũng có thể cùng interface và ủy quyền, nhưng trọng tâm là **kiểm soát truy cập** tới đối tượng khác (lazy loading, remote access, access control...) | Client cần đối tượng đại diện/kiểm soát truy cập |
| **Adapter** | Chuyển đổi **hợp đồng/interface** không tương thích sang hợp đồng client mong đợi | Tích hợp thư viện, API cũ hoặc provider có giao diện khác |
| **Strategy** | Đóng gói các thuật toán **thay thế** và chọn thuật toán phù hợp | Có nhiều cách thực hiện cùng một nhiệm vụ |
| **Chain of Responsibility** | Chuyển request qua chuỗi handler, thường mỗi handler chọn xử lý hoặc tiếp tục | Có nhiều bước xử lý với điều kiện dừng/chuyển tiếp riêng |
| **AOP** | Khai báo cross-cutting advice tại các join point được framework hỗ trợ | Muốn áp quy tắc chung trên nhiều bean/method mà không bọc bằng tay |

**Proxy và Decorator có cấu trúc giống nhau**, nên phải xem ý định thiết kế và trách nhiệm thực tế chứ không phân loại chỉ bằng sơ đồ. **Strategy** chọn *một cách thực hiện*; Decorator thêm các *lớp hành vi* xung quanh cách thực hiện được chọn. Hai mẫu có thể kết hợp.

Trong Spring, **@Transactional**, một số interceptor và proxy là cơ chế giải quyết các vấn đề cắt ngang, nhưng không đồng nghĩa mọi use case Decorator phải chuyển sang AOP. Với wrapper cần tùy biến theo từng instance hoặc có thứ tự rõ ở nơi lắp ráp, Decorator thuần Java dễ đọc và test hơn. Ngược lại, áp một policy thống nhất cho hàng trăm endpoint có thể phù hợp với filter/interceptor/AOP, tùy điểm chặn. Spring proxy AOP cũng có chi tiết cần lưu ý, chẳng hạn lời gọi nội bộ từ một phương thức tới phương thức khác của cùng object thường không đi qua proxy khi dùng proxy-based interception.

## 7. Ví dụ Decorator quen thuộc trong JDK

Một ví dụ rõ ràng là **java.io.InputStream**:

~~~java
import java.io.BufferedInputStream;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;

class InputExample {
    static int firstByte(String path) throws IOException {
        try (InputStream in = new BufferedInputStream(
                new FileInputStream(path))) {
            return in.read();
        }
    }
}
~~~

**FileInputStream** đọc byte từ file; **BufferedInputStream** bọc một **InputStream** để bổ sung buffering trong quá trình đọc. Client tiếp tục gọi **read()** qua hợp đồng **InputStream**. Khi **try-with-resources** đóng wrapper, wrapper này thực hiện việc đóng luồng bên trong theo hợp đồng của nó.

Từ ví dụ này cần rút ra hai điểm: (1) client không cần sửa chỉ vì một lớp bọc được thêm vào; (2) wrapper có thể quản lý tài nguyên/lifecycle, nên cần hiểu rõ trách nhiệm đóng, flush và thứ tự kết hợp thay vì coi các decorator hoàn toàn độc lập.

Một ví dụ liên quan là **Collections.unmodifiableList(list)** tạo view không cho sửa qua view đó, nhưng **không tạo bản sao**: thay đổi trên list gốc vẫn có thể phản ánh qua view. Nếu muốn snapshot không sửa qua reference gốc, hãy cân nhắc **List.copyOf(list)** cùng với tính bất biến của các phần tử. Đây là ví dụ điển hình cho việc wrapper bổ sung/giới hạn hành vi mà không nhất thiết copy dữ liệu.

## 8. Thiết kế Decorator an toàn khi đưa vào dự án

### 8.1. Giữ đúng hợp đồng Component

Wrapper cần giữ ý nghĩa của **send**, quy tắc xử lý lỗi và các bất biến mà client trông đợi. Chẳng hạn:

- Một decorator không nên tự ý bỏ thông điệp rồi báo đã gửi nếu hợp đồng hứa thông báo sẽ được chuyển tới delegate hoặc trả lỗi rõ ràng.
- Khi thêm giới hạn nội dung, hãy định nghĩa đó là một phần chính sách công khai của pipeline; client cần biết tình huống nào phát sinh validation error.
- Nếu có kết quả bất đồng bộ (**CompletableFuture**), đừng chỉ đo/đếm ngay khi nhận được future; phải xác định muốn đo việc xếp lịch, việc future hoàn tất thành công hay việc provider xác nhận đã giao.
- Nếu wrapper thêm tài nguyên cần đóng, nên biểu diễn lifecycle rõ ràng (chẳng hạn **AutoCloseable**) và tránh double-close, rò rỉ tài nguyên.

### 8.2. Quyết định trách nhiệm khi gặp exception

Decorator chạy **trước** và **sau** delegate nên thời điểm phát sinh exception rất quan trọng. Trong **CountingDecorator** ở trên, bộ đếm tăng sau khi delegate trả về bình thường; nó không nói lên kết quả giao hàng ngoài đời.

Với đo thời gian, **finally** thường phù hợp nếu muốn đo cả request thất bại:

~~~java
@Override
public void send(Message message) {
    long start = System.nanoTime();
    try {
        next.send(message);
    } finally {
        long elapsedNanos = System.nanoTime() - start;
        recordDuration(elapsedNanos); // Phương thức đo lường do ứng dụng định nghĩa.
    }
}
~~~

Đoạn trên chỉ minh họa **phần thân của một decorator đo thời gian**; để biên dịch độc lập cần khai báo lớp có **next**, hợp đồng **send** và phương thức **recordDuration**. Không dùng **finally** để ngầm biến thất bại thành thành công; exception vẫn cần được truyền hoặc chuyển đổi theo hợp đồng đã định nghĩa. Cũng cần hạn chế exception từ việc ghi metric làm che khuất exception chính.

### 8.3. Cân nhắc trạng thái, đồng thời và phạm vi sử dụng

**PrefixDecorator** và **LengthLimitDecorator** trong ví dụ giữ cấu hình **final** và không tự thay đổi trạng thái. **CountingDecorator** dùng **AtomicInteger** nên riêng phép tăng và đọc bộ đếm được bảo vệ trước cập nhật đồng thời; điều đó **không khiến cả chuỗi thread-safe**. Tính an toàn còn phụ thuộc vào **next**, dữ liệu truyền qua, cách dùng tài nguyên ngoài và có hay không mutation khác.

Nếu cache theo người dùng, bảo đảm key chứa đủ ngữ cảnh phân quyền và thời hạn phù hợp. Nếu logging, không ghi nội dung chứa thông tin cá nhân, token hoặc dữ liệu nhạy cảm theo mặc định. Nếu retry, yêu cầu khả năng chống thực hiện trùng. Nếu giới hạn tốc độ, phân biệt rate-limit theo instance, người dùng, tenant hay toàn hệ thống.

### 8.4. Đừng để lắp ráp trở thành mê cung

Một chuỗi quá dài, nhiều thứ tự cấu hình ngầm hoặc wrapper có tác dụng phụ không hiển nhiên có thể khó debug hơn giải pháp ban đầu. Nên:

1. Đặt tên từng decorator theo **hành vi cụ thể**, như **LengthLimitDecorator**, không đặt tên mơ hồ kiểu **EnhancedChannel**.
2. Tập trung lắp ráp ở **composition root** hoặc một factory có tên rõ, đặc biệt khi chain được sử dụng chung.
3. Ghi nhận thứ tự từ ngoài vào trong cùng lý do; viết test integration cho những tương tác có rủi ro.
4. Tránh wrapper vừa logging, vừa cache, vừa retry, vừa đổi nội dung nếu các trách nhiệm biến thiên độc lập.
5. Khi một hành vi dùng ở mọi nơi và không có biến thể, cân nhắc đưa vào service chung, interceptor hoặc chính implementation thay vì tạo quá nhiều lớp bọc.

## 9. Khi nào nên và không nên chọn Decorator?

**Cân nhắc Decorator khi** cần bật/tắt hoặc ghép các hành vi quanh từng đối tượng, nhiều implementation phải chia sẻ logic bổ sung, sửa implementation gốc không khả thi hoặc không phù hợp, và cùng một hợp đồng có thể biểu diễn pipeline.

**Tránh dùng máy móc khi** chỉ cần một phép gọi đơn giản, một helper function là đủ, không có nhu cầu kết hợp hành vi, hoặc nhiều wrapper làm hợp đồng khó hiểu. Một quy tắc bắt buộc đối với mọi đối tượng có thể cần đặt ở ranh giới domain thay vì cho phép client vô tình quên bọc. Không dùng Decorator chỉ để né việc refactor một lớp đang có trách nhiệm lẫn lộn.

Khả năng thay đổi động của Decorator mang lại lợi ích nhưng cũng cần cân đối với **KISS** (*Keep It Simple*) và nguyên tắc **composition over inheritance**: composition giúp linh hoạt, chứ không miễn trừ chi phí kiểm soát độ phức tạp.

## 10. Bài tập thực hành

Xây dựng hệ thống đọc tài liệu với hợp đồng:

~~~java
interface DocumentReader {
    String read(String documentId);
}
~~~

Có một **InMemoryDocumentReader** đọc từ **Map<String, String>**. Hãy viết ba decorator độc lập:

- **TrimmingReader** xóa khoảng trắng đầu/cuối của nội dung trả về.
- **CachingReader** lưu nội dung theo document ID sau lần đọc đầu tiên. Xác định rõ TTL/invalidation nếu dữ liệu có thể thay đổi; với bài tập, giả định dữ liệu gốc bất biến.
- **CountingReader** đếm số lần gọi **read()** tới wrapper. Nêu rõ đếm request hay đếm lần truy cập vào nguồn thật.

Lắp hai pipeline:

~~~text
Counting → Caching → Trimming → InMemory
Counting → Trimming → Caching → InMemory
~~~

Gọi cùng document ID hai lần và so sánh: nguồn gốc được gọi mấy lần; nội dung nào được cache; nếu thay đổi quy tắc trimming thì vị trí cache làm thay đổi hành vi hay không? Tạo fake reader để kiểm thử thay vì phụ thuộc file hoặc mạng.

**Tiêu chí đạt:**

- Các decorator đều triển khai cùng interface **DocumentReader**.
- Không sửa **InMemoryDocumentReader** khi bổ sung trim/cache/count.
- Mỗi wrapper có một trách nhiệm được đặt tên rõ ràng; thứ tự pipeline có chủ đích.
- Test chứng minh kết quả cuối, số lần delegate được gọi và hành vi khi nguồn ném exception.
- Không dùng cache chia sẻ dữ liệu nhạy cảm xuyên người dùng khi key hoặc chính sách truy cập không phân biệt người sử dụng.

**Ghi nhớ:** Decorator mở rộng hành vi **bằng cách bọc đối tượng cùng hợp đồng**. Giá trị thực tế là có thể phối hợp các hành vi mà không cần tạo hàng loạt lớp con hoặc sửa mã lõi; thách thức thực tế là giữ đúng hợp đồng, quản lý thứ tự và làm rõ lỗi/trạng thái ở từng lớp bọc.