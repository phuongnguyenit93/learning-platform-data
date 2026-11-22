# Socket appender trong Java logging: gửi log qua mạng

## 1. Socket appender là gì?

**Socket appender** là thành phần xuất log qua kết nối mạng tới một máy hoặc dịch vụ đang lắng nghe, thay vì chỉ in ra console hay ghi trực tiếp vào tệp cục bộ. Nó thường xuất hiện trong kiến trúc logging tập trung: ứng dụng phát sinh sự kiện, appender chuyển dữ liệu qua TCP/UDP/TLS, rồi một collector nhận, phân tích, lưu giữ và cho phép tìm kiếm.

Trong **Apache Log4j 2 (Log4j2)**, plugin cấu hình có tên **`Socket`** và được triển khai bằng `SocketAppender`. Đây là chủ đề thuộc nhóm **Appender và handler**: trách nhiệm chính là **đưa các bản ghi đã được hệ thống logging chấp nhận tới một đích mạng**.

```text
Mã Java
  LOG.info("event=order_created order_id={}", orderId)
                        |
                        v
                 Logger / LogEvent
                        |
                 Level và Filter
                        |
                        v
                 SocketAppender
                        |
               Layout -> bytes
                        |
                 TCP / UDP / TLS
                        |
                        v
                Network collector
                        |
              Parse / route / buffer
                        |
                        v
                Log storage / search
```

Ba khái niệm cần tách rõ:

- **Logger**: API mà mã nguồn gọi để phát sự kiện, với tên logger và mức `INFO`, `WARN`, `ERROR`...
- **Layout**: quyết định bản ghi được **biểu diễn ra byte/text/JSON** theo định dạng gì. Ví dụ `PatternLayout` và `JsonTemplateLayout`.
- **SocketAppender**: quyết định **host, port, giao thức và cách chuyển dữ liệu** đến máy nhận.

**SocketAppender không phải một socket server.** Ứng dụng dùng appender thường là bên **chủ động kết nối/gửi**; đích nhận phải tồn tại, mở đúng cổng, hiểu đúng cách đóng khung bản ghi và xử lý đúng định dạng.

Không nên gọi tất cả các cơ chế gửi log mạng là “SocketAppender” của Log4j2. Chẳng hạn `java.util.logging` (JUL) có `SocketHandler` và Logback có một họ socket appender riêng; API, định dạng mặc định và hành vi lỗi của chúng không hoàn toàn giống nhau.

## 2. So sánh socket appender với console và file

| Đích / thành phần | Đầu ra gần ứng dụng | Thường dùng khi | Rủi ro chính |
| --- | --- | --- | --- |
| Console Appender | `stdout` hoặc `stderr` | CLI, ứng dụng container, môi trường đã có agent thu log console | Bản ghi không được lưu lâu nếu runtime/collector không thu thập |
| File / RollingFile Appender | Tệp cục bộ hoặc volume | Máy chủ cần bản ghi tại chỗ, agent theo dõi file | Dung lượng đĩa, rotation, quyền file, tệp bị mất khi môi trường tạm thời bị xóa |
| SocketAppender | Host và port qua mạng | Collector có giao thức tương thích, cần gửi log từ nhiều ứng dụng | Collector hoặc mạng lỗi; backpressure; mất log hoặc không rõ trạng thái nhận |
| HTTP / Kafka Appender hoặc pipeline chuyên dụng | Dịch vụ nhận qua giao thức tương ứng | Cần khả năng vận chuyển, cấu trúc dữ liệu hay xác nhận phù hợp | Phụ thuộc giao thức, cấu hình, retry, hàng đợi và chi phí |

**Không phải gửi socket luôn tốt hơn ghi console.** Trong một cụm container đã tự động thu thập stdout/stderr, cách đơn giản và dễ vận hành có thể là ứng dụng ghi console rồi để agent/daemon của hạ tầng gửi đi. SocketAppender có ích khi **bộ nhận và giao thức đã rõ** hoặc khi kiến trúc yêu cầu ứng dụng gửi trực tiếp; cách này cũng làm ứng dụng phụ thuộc nhiều hơn vào tình trạng mạng/collector.

Điều quan trọng khi chọn appender là xác định **đích gần nhất** và **nơi lưu trữ cuối**. Nhìn thấy log trên dashboard không chứng minh ứng dụng gửi trực tiếp qua socket; nó có thể in console và được một agent chuyển tiếp.

## 3. TCP, UDP và TLS khác nhau thế nào?

Log4j2 SocketAppender hỗ trợ các kiểu truyền phổ biến là `TCP`, `UDP` và `SSL` (gửi trên kết nối được bảo vệ bằng TLS). Tài liệu Apache nêu rõ rằng cả TCP/TLS đều **ghi vào luồng byte và không chờ thông điệp xác nhận từ dịch vụ đích**.

| Giao thức | Đặc tính | Điều cần cân nhắc |
| --- | --- | --- |
| **TCP** | Kết nối, luồng byte có thứ tự trong phạm vi một kết nối | Không tự phân ranh giới từng LogEvent; có thể chậm hoặc lỗi khi đầu nhận/mạng gặp sự cố |
| **UDP** | Gửi datagram không cần thiết lập kết nối dài hạn | Có thể mất, lặp, đảo thứ tự hoặc vượt giới hạn gói; không có bảo đảm ứng dụng đích nhận |
| **SSL/TLS** | Bảo vệ kênh truyền, thường là TCP với TLS | Cần truststore/chứng chỉ/cấu hình xác minh; **mã hóa không đồng nghĩa giao nhận bền vững** |

### TCP không tự biết “một sự kiện log là một thông điệp”

Với TCP, collector đọc **một luồng byte**. Hai lời gọi `LOG.info` không mặc nhiên tương ứng hai lần `read` ở server. TCP có thể gộp hoặc chia các lần gửi ở cấp transport.

Để receiver biết ranh giới, hai bên phải thống nhất **framing**:

- Một sự kiện trên **một dòng**, kết thúc bằng `\n` và nội dung cần escape xuống dòng.
- Dùng **length prefix**: gói có độ dài trước dữ liệu.
- Dùng một giao thức định nghĩa sẵn như **syslog có framing thích hợp**, **GELF** với dấu phân cách phù hợp, hoặc một giao thức riêng do cả hai đầu hỗ trợ.

Ví dụ bài học phía dưới chọn **PatternLayout một dòng + newline `%n`**. Receiver dùng `BufferedReader.readLine()`. Đây là một **hợp đồng ứng dụng ở trên TCP**, không phải đặc tính có sẵn của TCP.

### TCP bảo đảm được gì và không được gì?

TCP giúp truyền luồng byte có thứ tự trong một kết nối đang hoạt động, nhưng lời gọi ghi thành công **không chứng minh collector đã ghi bền vào kho lưu trữ**. Khi server đóng socket đột ngột, một số lần ghi có thể chưa bị phát hiện lỗi ngay, rồi bản ghi bị mất khi lỗi socket xuất hiện sau đó.

Vì thế **SocketAppender không tự cung cấp giao nhận exactly-once hay at-least-once đến kho lưu trữ**. Muốn cam kết chặt hơn cần thiết kế có acknowledgment, lưu đệm bền vững, retry có định danh, xử lý trùng và hệ thống nhận phù hợp. Mã hóa TLS cũng không cung cấp những bảo đảm đó.

## 4. Cấu hình SocketAppender cơ bản trong Log4j2

Một cấu hình XML tối giản để gửi log text qua TCP:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Socket name="REMOTE"
                host="127.0.0.1"
                port="5514"
                protocol="TCP"
                connectTimeoutMillis="3000"
                immediateFlush="true"
                ignoreExceptions="false">
            <PatternLayout charset="UTF-8"
                    pattern="%p %m%n"/>
        </Socket>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="REMOTE"/>
        </Root>
    </Loggers>
</Configuration>
```

Đây là **file `log4j2.xml` hoàn chỉnh của ví dụ cục bộ**, và nó giả định một server TCP đang lắng nghe tại địa chỉ **127.0.0.1:5514**. Không thay `127.0.0.1` bằng một địa chỉ tùy ý khi chưa có collector tương thích.

Giải thích từng phần:

| Thuộc tính / thành phần | Vai trò |
| --- | --- |
| `name="REMOTE"` | Tên appender để `AppenderRef` tham chiếu |
| `host="127.0.0.1"` | Máy nhận log; loopback của chính máy đang chạy ví dụ |
| `port="5514"` | Cổng TCP của receiver; cả hai đầu phải dùng cùng giá trị |
| `protocol="TCP"` | Giao thức mạng |
| `connectTimeoutMillis="3000"` | Giới hạn chờ thiết lập kết nối ở ví dụ; không phải timeout xác nhận lưu trữ log |
| `immediateFlush="true"` | Flush buffer nội bộ sau từng sự kiện; **không có nghĩa collector đã persist** |
| `ignoreExceptions="false"` | Cho phép lỗi appender lan tới bên gọi logging khi lỗi được phát hiện ở giai đoạn ghi; không bảo đảm mọi mất log đều được phát hiện |
| `PatternLayout` | Chuyển LogEvent thành văn bản UTF-8 |
| `pattern="%p %m%n"` | In level, một dấu cách, message và dấu xuống dòng |
| `Root level="INFO"` | Cho các sự kiện từ `INFO` trở lên qua bộ lọc mức thông thường |
| `AppenderRef ref="REMOTE"` | Gắn SocketAppender vào root logger |

Cấu hình level và Appender là hai trách nhiệm độc lập. Một sự kiện `DEBUG` có thể bị lọc trước khi SocketAppender được gọi nếu root level là `INFO`. Sửa network host hoặc pattern không khiến level `DEBUG` tự xuất hiện.

**Điểm cần nhớ:** `ignoreExceptions="false"` chỉ làm **lỗi appender mà Log4j phát hiện** có khả năng ảnh hưởng lời gọi logging. Nó không biến appender thành một hàng đợi có xác nhận nhận thành công. Trong production phải đánh giá kỹ nguy cơ sự cố logging ảnh hưởng đường xử lý nghiệp vụ.

## 5. Ví dụ Java 17+ đầy đủ: bộ nhận TCP và ứng dụng gửi log

Ví dụ sử dụng **hai tiến trình** trong cùng một máy: một receiver thuần JDK lắng nghe TCP, và một ứng dụng Java dùng Log4j2 SocketAppender gửi hai sự kiện. Cách này giúp quan sát chính xác đường đi dữ liệu.

Ứng dụng sender **không tự tạo ServerSocket**. Receiver **không sử dụng Log4j2**; nó chỉ nhận hai dòng UTF-8 theo giao thức đã thống nhất.

Cấu trúc:

```text
socket-logging-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── logging/
        │           ├── SocketLogReceiver.java
        │           └── SocketLogSender.java
        └── resources/
            └── log4j2.xml
```

### 5.1. File Maven `pom.xml`

Hai artifact `log4j-api` và `log4j-core` được cố định ở **2.26.1** để ví dụ tái lập, không có nghĩa đây luôn là phiên bản mới nhất. Dự án thực phải tuân thủ chính sách cập nhật và kiểm tra thông báo bảo mật trước khi triển khai.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example.logging</groupId>
    <artifactId>socket-logging-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-api</artifactId>
            <version>2.26.1</version>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.26.1</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `log4j2.xml` đặt ở `src/main/resources/log4j2.xml`, **giữ nguyên cấu hình XML đầy đủ trong phần 4**.

### 5.2. Receiver: `SocketLogReceiver.java`

Receiver chỉ dùng `ServerSocket` và `BufferedReader` của JDK. Nó in thông báo sẵn sàng, chờ một kết nối đến đúng cổng, sau đó đọc **hai dòng** được gửi bởi SocketAppender.

```java
package example.logging;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public final class SocketLogReceiver {
    private SocketLogReceiver() {
    }

    public static void main(String[] args) throws IOException {
        InetAddress loopback =
                InetAddress.getByName("127.0.0.1");

        try (ServerSocket server =
                     new ServerSocket(5514, 1, loopback)) {
            System.out.println("READY 127.0.0.1:5514");

            try (Socket socket = server.accept();
                 BufferedReader reader = new BufferedReader(
                         new InputStreamReader(
                                 socket.getInputStream(),
                                 StandardCharsets.UTF_8))) {
                socket.setSoTimeout(15_000);

                for (int i = 0; i < 2; i++) {
                    String line = reader.readLine();
                    if (line == null) {
                        throw new IOException(
                                "Socket closed before 2 events");
                    }
                    System.out.println("RECEIVED " + line);
                }
            }
        }
    }
}
```

Đặc điểm quan trọng:

- Receiver bind vào **127.0.0.1**, không mở một cổng TCP ra tất cả giao diện mạng của máy.
- Nó chờ **một** client bằng `accept()`; nếu không chạy sender, chương trình tiếp tục chờ, không phải đã bị treo vì logging.
- `readLine()` cần bản ghi kết thúc bằng newline; ở sender, `%n` tạo ranh giới đó.
- `setSoTimeout(15_000)` đặt thời gian chờ đọc sau khi kết nối đã được thiết lập; nó **không** là timeout cho `accept()`.
- Vòng lặp đọc đúng hai dòng để kết quả minh họa dễ xác nhận. Đây **không phải collector production**: không hỗ trợ nhiều client, lưu trữ, xác nhận ở tầng ứng dụng, tự khôi phục hay xác thực mạng.

### 5.3. Sender: `SocketLogSender.java`

```java
package example.logging;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class SocketLogSender {
    private static final Logger LOG =
            LogManager.getLogger(SocketLogSender.class);

    private SocketLogSender() {
    }

    public static void main(String[] args) {
        LOG.info("event=order_created order_id={}", "ORD-101");
        LOG.warn("event=payment_retry order_id={} attempt={}",
                "ORD-101", 2);

        LogManager.shutdown();
    }
}
```

Cả hai lời gọi tạo LogEvent; SocketAppender dùng PatternLayout của file XML để biến chúng thành văn bản rồi gửi qua TCP. `LogManager.shutdown()` đóng hệ thống logging của tiến trình ví dụ theo cơ chế hỗ trợ và có thể flush tài nguyên liên quan. **Shutdown/flush không tạo acknowledgment từ collector**, nên vẫn không có bảo đảm bản ghi đã lưu bền.

Ứng dụng sender chỉ gọi API Log4j2. Nó không chủ động dùng `Socket` của JDK, không viết `OutputStream` và không chọn dấu newline trong code; đó là trách nhiệm cấu hình appender/layout.

### 5.4. Biên dịch và chạy trên hai terminal

Trong thư mục chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn -q -DskipTests package
mvn -q org.apache.maven.plugins:maven-dependency-plugin:3.7.1:copy-dependencies -DoutputDirectory=target/dependency
```

Maven có thể cần truy cập kho dependency đã được cấu hình. Phải có hai tiến trình riêng, không chạy receiver và sender nối tiếp trong **một terminal duy nhất** khi receiver còn đang chờ.

**Terminal A – khởi động receiver trước, Linux/macOS:**

```bash
java -cp "target/classes:target/dependency/*" example.logging.SocketLogReceiver
```

**Terminal B – khi A đã in READY, chạy sender:**

```bash
java -cp "target/classes:target/dependency/*" example.logging.SocketLogSender
```

Trên Windows, dùng dấu `;` làm ký tự phân tách classpath:

```powershell
# Terminal A:
java -cp "target\classes;target\dependency\*" example.logging.SocketLogReceiver

# Terminal B, sau khi A in READY:
java -cp "target\classes;target\dependency\*" example.logging.SocketLogSender
```

Đầu ra **stdout chính xác của receiver** trong điều kiện port 5514 còn trống, cả hai tiến trình sử dụng đúng cấu hình và kết nối thành công:

```text
READY 127.0.0.1:5514
RECEIVED INFO event=order_created order_id=ORD-101
RECEIVED WARN event=payment_retry order_id=ORD-101 attempt=2
```

Đầu ra **stdout của sender:** không có dòng nào. Bản ghi của sender được gửi đến **SocketAppender**, không có ConsoleAppender trong file XML mẫu. Không có thông điệp lỗi ứng dụng trên stderr khi cấu hình và mạng hoạt động bình thường; chẩn đoán bất thường từ JVM, Maven hoặc Log4j không phải là một phần của đầu ra chuẩn ở trên.

### 5.5. Phân tích kết quả

| Quan sát | Giải thích |
| --- | --- |
| Receiver in `READY` trước | ServerSocket đã bind và bắt đầu chờ kết nối |
| Sender ghi `INFO`, `WARN` nhưng không in console | Cấu hình gắn root logger với `REMOTE` SocketAppender, không gắn ConsoleAppender |
| Receiver thấy `RECEIVED INFO ...` | `%p` đưa level vào dòng, `%m` đưa message sau thay tham số |
| Hai dòng có thứ tự `INFO` rồi `WARN` | Hai lời gọi tuần tự trên một tiến trình/kết nối TCP hoạt động thành công |
| `%n` tạo ranh giới | `BufferedReader.readLine()` có thể tách hai sự kiện từ stream |
| Receiver dừng sau hai dòng | Vòng lặp của demo chỉ đọc hai dòng, không phải do TCP tự biết phải dừng sau hai LogEvent |

Nếu cổng `5514` đang được tiến trình khác sử dụng, receiver sẽ không bind được và phải chọn cổng khác **đồng thời sửa đúng cùng số trong cả receiver và `log4j2.xml`**. Nếu sender chạy trước khi receiver sẵn sàng, kết nối có thể thất bại; đừng kỳ vọng appender tự giữ hai sự kiện và chuyển lại đầy đủ sau khi server được mở.

Ví dụ minh họa **cơ chế gửi trực tiếp**, không kiểm thử TLS, retry, phân tán nhiều máy hay độ bền lưu trữ.

## 6. Các thuộc tính cấu hình ảnh hưởng lỗi và độ trễ

Trong tài liệu Log4j2, SocketAppender có các thuộc tính như `host`, `port`, `protocol`, `connectTimeoutMillis`, `bufferedIo`, `bufferSize`, `immediateFlush`, `immediateFail` và `ignoreExceptions`. Một số phiên bản còn có `reconnectDelayMillis` và các tùy chọn socket khác; phải kiểm tra **phiên bản plugin thực tế** vì bảng tài liệu/thuộc tính có thể thay đổi theo nhánh bản phát hành.

| Thuộc tính | Ý nghĩa vận hành | Điều không nên suy diễn |
| --- | --- | --- |
| `host` | Địa chỉ server nhận | Không bảo đảm hostname có thể resolve hoặc có kết nối |
| `port` | Cổng lắng nghe | Cùng số port không đồng nghĩa cùng giao thức dữ liệu |
| `protocol` | `TCP`, `UDP` hoặc `SSL`/TLS | Không quyết định Layout hoặc schema |
| `connectTimeoutMillis` | Giới hạn thời gian thiết lập kết nối | Không xác nhận server đã lưu bản ghi |
| `bufferedIo` / `bufferSize` | Bộ đệm bên trong appender/manager | Không phải hàng đợi bền vững vô hạn |
| `immediateFlush` | Có flush buffer sau từng sự kiện hay không | Flush không phải xác nhận ứng dụng nhận |
| `immediateFail` | Khi socket không sẵn sàng, có ưu tiên thất bại ngay thay vì chờ cơ chế reconnect | Không chứng minh log đã được lưu |
| `ignoreExceptions` | Có che lỗi appender khỏi bên gọi khi lỗi được phát hiện không | `true` không có nghĩa không xảy ra lỗi; `false` không bảo đảm phát hiện mọi mất log |
| `reconnectDelayMillis` | Khoảng thời gian giữa các lần thử kết nối lại, khi phiên bản hỗ trợ | Reconnect không tự phát lại những sự kiện đã mất |

Trong ví dụ sử dụng `ignoreExceptions="false"` để lỗi write **có thể lộ ra** khi phát hiện. Trong môi trường production, phải xác định chính sách mong muốn: có để sự cố quan sát ảnh hưởng request không? Có cần fallback sang file/console không? Có giám sát bộ thu và số log bị rơi không?

**Không tự khẳng định “gửi TCP là mất log bằng 0”**. Ngay cả khi appender write trả về bình thường, nó không có thỏa thuận để server gửi xác nhận đã ghi bền một LogEvent. Khi server đóng kết nối, lỗi có thể đến muộn.

## 7. TCP framing: ranh giới của từng bản ghi

TCP là **byte stream**, không có khái niệm từng “dòng log” ở tầng mạng. Nếu Layout tạo:

```text
INFO event=order_created order_id=ORD-101
WARN event=payment_retry order_id=ORD-101 attempt=2
```

và thêm `%n`, receiver có thể tách hai dòng bằng `readLine`. Nếu bỏ `%n`, phần cuối dòng đầu có thể nối với đầu dòng thứ hai và không được tách đúng.

Các lỗi thường gặp:

- **Message chứa newline:** một LogEvent có thể thành nhiều dòng, làm collector đếm nhầm. Với log text, cân nhắc converter escape CR/LF như `%enc{%m}{CRLF}` và vẫn giữ `%n` ở cuối.
- **Gửi JSON nhiều dòng:** nếu receiver giả định mỗi dòng là một JSON event, JSON “pretty-printed” nhiều dòng làm parser sai. Thường chọn một JSON object trên một dòng hoặc framing được hai bên thống nhất.
- **Binary payload:** không dùng `BufferedReader.readLine()` nếu layout gửi dữ liệu nhị phân hoặc dùng dấu phân cách khác.
- **GELF qua TCP:** định dạng GELF có yêu cầu framing riêng, thường dùng dấu phân cách NUL khi chọn cách gửi TCP thích hợp; phải cấu hình `GelfLayout`/collector khớp nhau.
- **Syslog qua TCP/TLS:** tùy collector, cần RFC 5424 và framing tương thích với giao thức nhận; không phải cứ gửi `%p %m%n` vào cổng syslog là được chấp nhận.

Với stream transport, **đọc một lần không bằng một LogEvent**: server cần bộ giải mã framing tích lũy byte và tách thông điệp. Receiver ở phần 5 đã chọn cách đơn giản nhất là newline-delimited UTF-8, chỉ hợp lệ với layout tạo dòng phù hợp.

## 8. Dùng JSON thay text với SocketAppender

Trong hệ thống log tập trung, JSON có các trường độc lập thường dễ phân tích hơn dòng văn bản tự ghép. Log4j2 hỗ trợ **JsonTemplateLayout**, nhưng cần thêm artifact `log4j-layout-template-json` tương thích cùng phiên bản.

Dependency Maven bổ sung:

```xml
<dependency>
    <groupId>org.apache.logging.log4j</groupId>
    <artifactId>log4j-layout-template-json</artifactId>
    <version>2.26.1</version>
    <scope>runtime</scope>
</dependency>
```

Đoạn này cần đặt **trong khối `<dependencies>`** của `pom.xml`, không phải một POM hoàn chỉnh.

Snippet Appender gửi JSON qua TCP:

```xml
<Socket name="REMOTE_JSON"
        host="collector.example.internal"
        port="5514"
        protocol="TCP">
    <JsonTemplateLayout/>
</Socket>
```

Đây là **mẫu cấu hình cho môi trường giả định có collector JSON tương thích**, không phải thay thế tự động hoạt động cho receiver ở phần 5. Receiver demo in text nhưng không parse JSON. Muốn dùng collector thực, cần xác nhận:

1. Đầu nhận yêu cầu **JSON lines**, length-prefixed frame hay cách đóng khung khác?
2. Template mặc định đã có các trường `level`, `message`, `logger`, timestamp và exception theo schema nào?
3. `ThreadContext`, mã tương quan, dữ liệu nghiệp vụ và stack trace có được giữ thành **trường riêng** không?
4. Khi ghi exception có nhiều dòng, dữ liệu JSON đã escape đúng chưa?
5. Có cần ánh xạ `event`, `reason_code`, `service`, `environment` vào schema riêng của công ty không?

Một bản JSON minh họa, **không phải output chính xác của JsonTemplateLayout mặc định**:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "event": "order_created",
  "order_id": "ORD-101",
  "correlation_id": "req-7"
}
```

Không coi chuỗi `event=order_created order_id=ORD-101` trong message là hai trường JSON độc lập nếu template chỉ xuất `message` dạng chuỗi. Muốn có thuộc tính thật cần đưa chúng vào LogEvent/context và template bằng cơ chế phù hợp.

## 9. UDP: khi nào dùng và giới hạn gì?

Với `protocol="UDP"`, SocketAppender gửi dữ liệu dưới dạng datagram. Một cấu hình minh họa:

```xml
<Socket name="REMOTE_UDP"
        host="collector.example.internal"
        port="5514"
        protocol="UDP">
    <PatternLayout charset="UTF-8" pattern="%p %m%n"/>
</Socket>
```

Đây là snippet cần gắn AppenderRef ở logger/root, và chỉ có ý nghĩa nếu đầu nhận thật sự lắng nghe **UDP** cùng cổng, hiểu đúng encoding/layout.

UDP có các đặc điểm:

- Không cần duy trì kết nối TCP với server.
- Một datagram có ranh giới gói ở tầng UDP, khác với TCP stream.
- Không có bảo đảm gói tới đích, chỉ tới một lần hoặc đúng thứ tự.
- Gói lớn dễ gặp phân mảnh IP và có nguy cơ bị loại; cần tính kích thước sự kiện.
- Lỗi gửi không chứng minh receiver đã nhận; không có ứng dụng acknowledgment mặc định.
- Không tự mã hóa dữ liệu truyền; tránh gửi dữ liệu nhạy cảm trên mạng không tin cậy.

UDP phù hợp khi bộ nhận và tổ chức **chấp nhận mất một phần sự kiện** để đổi lấy sự đơn giản/độ trễ, với chính sách quan sát và bảo mật rõ. Không chọn UDP cho audit trail hoặc dữ liệu bắt buộc không mất chỉ vì cấu hình ngắn.

## 10. TLS: bảo mật đường truyền không phải bảo đảm lưu trữ

TCP không mã hóa thông điệp. Khi gửi qua hạ tầng không hoàn toàn tin cậy, log có thể chứa tên dịch vụ, mã định danh, lỗi kỹ thuật và metadata quan trọng. Trong Log4j2, SocketAppender có thể dùng **TLS** qua `protocol="SSL"` và cấu hình `Ssl`.

Minh họa cách cấu hình cho một collector **đã được triển khai TLS và xác nhận hostname**:

```xml
<Socket name="REMOTE_TLS"
        host="collector.example.internal"
        port="5515"
        protocol="SSL">
    <PatternLayout charset="UTF-8"
            pattern="%p %m%n"/>
    <Ssl verifyHostName="true">
        <TrustStore location="conf/log-collector-truststore.p12"
                    passwordEnvironmentVariable="LOG_TRUSTSTORE_PASSWORD"/>
    </Ssl>
</Socket>
```

Đây là **snippet**, không phải chương trình chạy ngay: cần tạo truststore, cấu hình biến môi trường, có TLS server đúng hostname/cổng và đăng ký AppenderRef. Không đặt mật khẩu thật trong tài liệu hay commit file cấu hình có secret.

Những điểm quan trọng:

1. **TLS mã hóa đường truyền** và có thể xác thực server dựa trên chứng chỉ/truststore khi cấu hình đúng.
2. **Xác minh hostname** giúp tránh kết nối tới endpoint có chứng chỉ không tương ứng. Không nên vô hiệu hóa chỉ để làm ví dụ “chạy được” trên production.
3. Khi dùng địa chỉ IP thay vì tên DNS, việc xác minh hostname/chứng chỉ có giới hạn và cần thiết kế chứng chỉ phù hợp; dùng tên DNS được chứng thực.
4. Nếu collector yêu cầu **mutual TLS**, phía ứng dụng còn cần client certificate/private key qua keystore và chính sách quản lý secret.
5. **TLS không phải ack của hệ thống lưu trữ**. Kênh an toàn vẫn có thể đứt, collector có thể đầy hoặc mất dữ liệu sau khi nhận.
6. Không dùng cổng **6514** chỉ vì đó là cổng syslog-over-TLS phổ biến nếu collector ở cổng ấy yêu cầu **RFC5424/framing đặc thù** mà Layout của bạn chưa cung cấp.

Trong production, tham số TLS, cipher suite, truststore/keystore và vòng đời chứng chỉ cần khớp với bảo mật của nền tảng đang dùng.

## 11. Xử lý khi collector không sẵn sàng

Điểm yếu quan trọng của socket logging là **đường mạng và đầu nhận nằm ngoài kiểm soát trực tiếp của ứng dụng**. Một vài tình huống:

| Tình huống | Hệ quả có thể xảy ra | Điều cần kiểm tra |
| --- | --- | --- |
| Hostname không phân giải được | Không tạo được kết nối | DNS, địa chỉ, network policy |
| Sai cổng hoặc không có listener | Connection refused hoặc timeout | Host/port, firewall, readiness của collector |
| Collector đóng socket sau khi nhận một phần | Một số bản ghi có thể mất trước khi bên gửi phát hiện | Kết nối, lỗi appender, metrics của collector |
| Server nhận TCP nhưng parser sai | Bytes đến mà không xuất hiện trong dashboard | Layout, charset, newline, framing, schema |
| Mạng chậm hoặc bộ thu nghẽn | Tăng thời gian write hoặc tích lũy buffer/queue | Timeout, throughput, backpressure |
| TLS handshake thất bại | Không thể lập kênh an toàn | Chứng chỉ, truststore, hostname, protocol |
| Gửi UDP quá nhiều | Mất hoặc đảo thứ tự datagram | Kích thước gói, lưu lượng, giới hạn kernel/collector |
| Ứng dụng dừng đột ngột | Buffer chưa flush có thể mất | Shutdown, queue, phương án lưu bền |

### `ignoreExceptions` và `immediateFail`

Với Log4j2, `ignoreExceptions` mặc định thường là `true`: những lỗi appender được phát hiện có thể được ghi vào **Status Logger** thay vì ném tới code nghiệp vụ. Nếu đặt `false`, lỗi có thể lan ra từ lời gọi logging, làm thay đổi hành vi phương thức đang xử lý một request.

`immediateFail` liên quan cách xử lý khi socket không sẵn sàng, còn `reconnectDelayMillis` ở các phiên bản hỗ trợ chỉ là cơ chế thử kết nối lại. **Không có cái nào tự cung cấp bộ đệm bền vững để phát lại tất cả các sự kiện cũ.**

Đừng tạo logic:

```java
// Cách hiểu sai: log gửi thành công = giao dịch đã được ghi bền.
LOG.info("payment captured id={}", paymentId);
markPaymentAsCommitted();
```

Đây là đoạn **minh họa không độc lập**. Trạng thái thanh toán phải được xác nhận qua hệ thống giao dịch, không phụ thuộc bản ghi logging đã gửi được hay chưa. Nếu không gửi được log, ứng dụng vẫn phải tuân thủ hợp đồng nghiệp vụ của chính nó.

### Flush, buffering và hiệu năng

`bufferedIo`/`bufferSize` giúp quản lý byte buffer bên trong appender. `immediateFlush="true"` khiến appender yêu cầu flush thường xuyên hơn, giúp sự kiện không nằm lâu ở buffer phía gửi nhưng có thể tăng chi phí I/O. **Flush không đồng nghĩa server đã ghi file hay index bản ghi.**

Ghi socket trực tiếp cũng có thể chịu chi phí kết nối, định dạng và backpressure. Tại lưu lượng cao, nên đánh giá phương án **AsyncAppender**, hàng đợi/buffer có giới hạn, collector agent hoặc đường truyền chuyên dụng. Async có thể giảm độ trễ đường gọi nghiệp vụ trong một số tình huống nhưng thêm rủi ro mất sự kiện chưa được flush khi tiến trình dừng đột ngột.

## 12. Failover, retry và độ tin cậy thực tế

Khi collector không sẵn sàng, có thể cần một **đích dự phòng** như file hoặc console. Log4j2 có **FailoverAppender** để chỉ định appender chính và dự phòng theo lỗi được phát hiện. Nhưng failover không phải giao thức xác nhận lưu trữ và không bảo đảm thu hồi tất cả bản ghi đã gửi trước khi lỗi lộ ra.

Một ý tưởng kiến trúc:

```text
                  LogEvent
                     |
                     v
               FailoverAppender
                   /        \
                  v          v
        Primary Socket     Fallback File
             |                  |
             v                  v
        Remote collector     Local disk/agent
```

Để failover hoạt động, **thông số báo lỗi của appender chính** và cấu hình FailoverAppender phải tương thích; các bản Log4j2 thường yêu cầu appender chính **không nuốt lỗi** (`ignoreExceptions="false"`). Nếu appender chính đã bỏ qua mọi lỗi thì lớp failover có thể không nhận được tín hiệu để chuyển.

Đoạn cấu hình **minh họa hình dạng**:

```xml
<Appenders>
    <Socket name="REMOTE"
            host="collector.example.internal"
            port="5514"
            protocol="TCP"
            ignoreExceptions="false">
        <PatternLayout pattern="%p %m%n"/>
    </Socket>

    <RollingFile name="LOCAL"
                 fileName="logs/fallback.log"
                 filePattern="logs/fallback-%i.log.gz">
        <PatternLayout pattern="%p %m%n"/>
        <Policies>
            <SizeBasedTriggeringPolicy size="10 MB"/>
        </Policies>
        <DefaultRolloverStrategy max="5"/>
    </RollingFile>

    <Failover name="SAFE_ROUTE" primary="REMOTE">
        <Failovers>
            <AppenderRef ref="LOCAL"/>
        </Failovers>
    </Failover>
</Appenders>
```

Đây **không phải file `log4j2.xml` hoàn chỉnh**: cần thêm `<Configuration>`, `<Loggers>` và `<AppenderRef ref="SAFE_ROUTE"/>`. Trước khi triển khai, xác minh cú pháp với phiên bản Log4j2, quyền thư mục file, rotation và agent đọc fallback.

Đánh đổi:

- **Failover** giúp có đường dự phòng khi lỗi được phát hiện.
- **Retry/reconnect** có thể nối lại đường truyền sau sự cố nhưng **không tự phát lại mọi log đã mất**.
- **Async queue** hấp thụ những đợt tăng tải có giới hạn, nhưng có thể đầy hoặc mất khi process crash.
- **Buffer bền vững** chỉ hữu ích nếu thiết kế thực sự có cơ chế lưu đĩa/đảm bảo nhận; SocketAppender đơn lẻ không tự có.
- **Ack, deduplication và idempotency** thường cần nếu hệ thống yêu cầu giao nhận mạnh hơn.

Log không nên là nguồn duy nhất cho thông tin giao dịch/kiểm toán bắt buộc bảo toàn. Với dữ liệu có yêu cầu không mất, nên dùng cơ chế audit/event store/transactional outbox phù hợp bên cạnh logging quan sát.

## 13. So sánh `SocketAppender`, JUL `SocketHandler` và Logback

Trong hệ sinh thái Java, có nhiều cách ghi log qua network socket. Chúng có mục đích tương đồng nhưng **không hoán đổi cấu hình**:

| Hệ thống | Thành phần | Đặc điểm cần nhớ |
| --- | --- | --- |
| **Log4j2** | `org.apache.logging.log4j.core.appender.SocketAppender` | Appender cho TCP/UDP/TLS, cấu hình `<Socket>` trong `log4j2.xml`, Layout theo nhu cầu |
| **JUL – java.util.logging** | `java.util.logging.SocketHandler` | Handler gửi log qua **TCP**, mặc định dùng `XMLFormatter`; có thể thay Formatter |
| **Logback** | `ch.qos.logback.classic.net.SocketAppender` và các biến thể khác | Có giao thức/encoder/cơ chế truyền riêng theo implementation; không giả định receiver văn bản của Log4j2 đọc trực tiếp được |
| **SLF4J API** | `Logger` và `LoggerFactory` | Chỉ là facade ghi log; backend/provider mới quyết định có appender socket hay không |

Ví dụ JUL có thể tạo handler bằng:

```java
java.util.logging.SocketHandler handler =
        new java.util.logging.SocketHandler("127.0.0.1", 5514);
handler.setEncoding("UTF-8");
```

Đây là **mã minh họa không chạy độc lập**: còn cần mở receiver, gắn handler vào JUL logger, chọn mức và formatter thích hợp, rồi đóng handler theo vòng đời.

Với JUL, `SocketHandler` **mặc định dùng XMLFormatter**, không phải PatternLayout của Log4j2. Do đó đừng lấy receiver `readLine()` trong ví dụ Log4j2 để khẳng định nó sẽ đọc “hai dòng text y hệt” từ JUL SocketHandler mặc định.

Cũng không nhầm **SLF4J API** với Log4j2 SocketAppender: code gọi `org.slf4j.Logger` chỉ có thể đi vào Log4j2 Core nếu runtime có provider/adapter thích hợp và không có bridge vòng lặp.

## 14. Thiết kế log nghiệp vụ và metadata khi gửi qua socket

Một appender gửi nhanh đến collector không làm thông điệp nghiệp vụ trở nên tự hiểu. Đầu ra vẫn cần:

- **Tên sự kiện ổn định** như `order_created`, `payment_retry_scheduled` và `invoice_generation_failed`.
- **Mức log đúng**: `INFO` cho sự kiện bình thường, `WARN` cho suy giảm, `ERROR` cho lỗi nghiêm trọng ngoài dự kiến.
- **Mã tương quan** như `correlation_id`/`trace_id` để tìm request xuyên dịch vụ.
- **Tên service và environment** để phân biệt nhiều tiến trình cùng gửi đến collector.
- **Mã lý do và outcome** thuộc tập giá trị kiểm soát, thay vì chỉ ghi văn bản lỗi tự do.
- **Thời gian có múi giờ**, thường UTC, để tra cứu và đối chiếu trong hệ thống phân tán.
- **Danh tính instance** khi cần phân biệt nhiều replica.

Với Log4j2, `ThreadContext` có thể gắn mã tương quan. Một đoạn minh họa bên trong lớp Java:

```java
ThreadContext.put("correlation_id", requestId);
try {
    LOG.info("event=order_received order_id={}", orderId);
} finally {
    ThreadContext.remove("correlation_id");
}
```

Nếu muốn PatternLayout in mã đó, thêm converter `%X{correlation_id}`. Với JsonTemplateLayout, dùng resolver/template được cấu hình tương ứng. Đừng dựa vào việc chỉ gọi `ThreadContext.put` mà khẳng định collector đã có trường riêng.

Dữ liệu từ user có thể chứa xuống dòng, ký tự điều khiển và payload quá lớn. Khi dùng định dạng một dòng, hãy escape hợp lý và giới hạn giá trị. **Không gửi secret qua log**, kể cả kênh TLS; collector và kho lưu trữ vẫn có quyền đọc được nội dung sau khi giải mã.

## 15. Triển khai an toàn trong mạng thật

Bài học dùng `127.0.0.1` và TCP không mã hóa để đơn giản hóa quá trình quan sát trên cùng một máy. Đây **không phải cấu hình production cho dữ liệu nhạy cảm**.

Một checklist trước khi triển khai:

1. **Xác định collector cụ thể**: nó chấp nhận TCP text lines, TLS syslog, GELF, JSON lines, HTTP hay một giao thức khác?
2. **Chọn framing và Layout**: `%n`, delimiter NUL, length prefix hoặc format chuẩn tương ứng. Hai đầu cần dùng cùng hợp đồng.
3. **Bảo mật truyền tải**: TLS với xác thực server, truststore, hostname verification và client credential nếu cần.
4. **Thu hẹp quyền kết nối**: chỉ cho ứng dụng gửi đến cổng collector được phép; không mở listener công khai không xác thực.
5. **Giới hạn dữ liệu**: không log bí mật hoặc dữ liệu nhạy cảm, escape message và context.
6. **Định nghĩa hành vi khi mất kết nối**: timeout, retry, fallback, chính sách khi queue đầy và cách theo dõi mất log.
7. **Đo throughput và kích thước bản ghi**: tránh biến logging thành nút thắt của đường xử lý request.
8. **Giám sát từ đầu tới cuối**: kiểm tra log được phát, collector nhận, parse thành công và được lập chỉ mục đúng thời điểm.
9. **Có thời hạn lưu trữ**: cấu hình retention, phân quyền, xóa và chi phí tại kho cuối.
10. **Đối chiếu metric và nghiệp vụ**: số dòng log không mặc nhiên tương ứng số giao dịch thành công hoặc thất bại.

Nếu đang chạy trong Kubernetes/container, cân nhắc chiến lược thu stdout/stderr qua node agent trước khi chọn gửi socket trực tiếp. Điều này giảm coupling với collector trong một số hạ tầng, nhưng vẫn cần cấu hình và giám sát pipeline để bảo đảm log không biến mất sau khi container bị xóa.

## 16. Các bài kiểm tra có giá trị

### Kiểm tra đường gửi bình thường

Trong ví dụ phần 5: mở receiver, xác nhận `READY`, chạy sender, quan sát đúng hai dòng `RECEIVED`. Đây là phép thử **framing + đường TCP + PatternLayout**, không phải thử độ bền log khi crash.

### Kiểm tra lỗi khi receiver chưa chạy

Dừng receiver rồi chạy sender. Với `ignoreExceptions="false"`, lỗi khi appender kết nối/ghi **có thể được phát hiện và báo**; không nên kết luận trước rằng mọi môi trường đều ném cùng một exception hay in cùng stack trace. Đánh giá thông điệp từ **Status Logger** và kết quả thật của Log4j.

Không “sửa” ví dụ bằng cách bịa một giá trị stdout cố định cho ca lỗi: chẩn đoán phụ thuộc thời điểm khởi tạo, hệ điều hành, network và tình trạng socket.

### Kiểm tra parser

Nếu thay PatternLayout thành JSON, xác nhận collector nhận **một event theo framing mong muốn**, parse được và giữ các trường đã thống nhất. Đặc biệt kiểm tra message chứa dấu nháy kép, ký tự tiếng Việt và newline.

### Kiểm tra sự cố sau khi đã kết nối

Giết receiver khi sender đang gửi liên tục. Theo dõi khi nào sender phát hiện lỗi, có retry/reconnect không, có bản ghi mất hoặc trùng không và ứng dụng có bị ảnh hưởng không. TCP write có thể tiếp tục trông thành công trong một khoảng ngắn sau khi peer mất, vì thế **không lấy kết quả một lần gọi log làm xác nhận cuối**.

### Kiểm tra throughput

Gửi nhiều LogEvent có size gần thực tế, theo dõi CPU, memory, thời gian ghi, backlog/queue và số bản ghi collector đã ingest. Nếu cần cam kết mất log bằng 0, phải xây thêm một giao thức hoặc pipeline có xác nhận và lưu đệm bền vững; không dựa vào thông số `immediateFlush` đơn lẻ.

## 17. Những lỗi phổ biến cần tránh

**1. Chạy appender mà không có socket server.** Host/port phải trỏ đúng một dịch vụ đang lắng nghe; SocketAppender không mở listener để chờ người khác đến đọc.

**2. Sai transport.** Sender TCP vào receiver UDP hoặc ngược lại sẽ không trao đổi được dữ liệu dù port là cùng một con số.

**3. Sai framing.** TCP nhận byte stream; thiếu newline/delimiter hoặc dùng JSON nhiều dòng khiến parser ghép/tách sai sự kiện.

**4. Gửi text vào cổng collector đòi syslog/GELF.** Trùng cổng không có nghĩa trùng giao thức. Layout phải khớp chuẩn nhận.

**5. Coi TLS là bảo đảm giao nhận.** TLS bảo vệ kênh truyền khi cấu hình đúng, không xác nhận bản ghi đã persist.

**6. Coi reconnect là replay bền vững.** SocketAppender không tự lưu tất cả sự kiện không gửi được để phát lại sau.

**7. Dùng `ignoreExceptions="false"` mà không hiểu hệ quả.** Một lỗi logging được phát hiện có thể làm lời gọi nghiệp vụ bị exception. Cần chính sách rõ ràng.

**8. Dùng `ignoreExceptions="true"` rồi tưởng không có sự cố.** Lỗi có thể bị ghi nội bộ và không đi tới code nghiệp vụ; cần giám sát Status Logger/pipeline.

**9. Không có giới hạn timeout hoặc kế hoạch nghẽn mạng.** Logging trực tiếp có thể ảnh hưởng thời gian xử lý khi đầu nhận không khỏe.

**10. Gửi thông điệp nhiều dòng chưa escape.** Một LogEvent có thể bị hiển thị thành nhiều dòng hoặc giả mạo sự kiện khác.

**11. Gửi token/password qua socket vì “nội bộ”.** Dữ liệu vẫn có thể bị đọc ở collector hoặc lộ nếu không có TLS/phân quyền; thiết kế không ghi secret.

**12. Cho rằng mọi SocketAppender đều tương thích.** JUL SocketHandler, Logback và Log4j2 có những lựa chọn format/protocol khác nhau.

**13. Không dọn ThreadContext.** Worker thread được tái sử dụng có thể mang mã request cũ vào bản ghi sau.

**14. Gắn đồng thời Console, File và Socket không kiểm tra collector.** Nếu collector đọc nhiều nguồn, có thể ingest cùng một sự kiện nhiều lần.

**15. Dùng log làm bằng chứng giao dịch.** Việc ghi `payment_completed` lên socket không xác nhận trạng thái tài chính đã commit.

## 18. Câu hỏi tự kiểm tra

1. **SocketAppender là client hay server?** Thông thường nó là bên kết nối/gửi; cần có bộ nhận lắng nghe ở host và port đã cấu hình.
2. **SocketAppender khác Layout ra sao?** Appender chọn đích và cách truyền; Layout quyết định biểu diễn LogEvent.
3. **TCP có một lần gửi ứng với một lần read phía server không?** Không. TCP là byte stream; cần framing để tách sự kiện.
4. **Vì sao PatternLayout của demo chứa `%n`?** Tạo dấu xuống dòng để receiver dùng `readLine()` tách hai LogEvent.
5. **Gửi log TCP thành công có chứng minh collector đã lưu bền không?** Không. SocketAppender không nhận acknowledgment về việc lưu trữ.
6. **UDP khác TCP ở rủi ro nào?** Datagram có thể mất, đảo thứ tự, bị phân mảnh hoặc không được nhận, không có kết nối với đảm bảo thứ tự của TCP.
7. **Dùng `protocol="SSL"` đã đủ an toàn chưa?** Còn cần truststore/chứng chỉ hợp lệ, xác minh hostname, chính sách mTLS nếu cần và tránh ghi dữ liệu nhạy cảm.
8. **`ignoreExceptions="false"` có bảo đảm không mất log không?** Không. Nó chỉ khiến lỗi appender được phát hiện có thể truyền tới caller.
9. **`immediateFlush="true"` có đồng nghĩa receiver đã ghi file không?** Không, chỉ flush ở phía gửi theo cơ chế appender.
10. **Nếu sender gửi text `%p %m%n` vào collector chỉ nhận GELF, lỗi ở đâu?** Sai định dạng/framing giữa Layout và receiver, không nhất thiết là lỗi socket.
11. **Vì sao cần kiểm tra cả collector lẫn dashboard?** Bytes có thể đến collector nhưng parser lỗi hoặc chưa được index.
12. **Có thể dùng JsonTemplateLayout với SocketAppender không?** Có, khi có dependency, template và collector tương thích.
13. **JUL SocketHandler mặc định có cho dòng text giống Log4j2 PatternLayout không?** Không; mặc định JUL dùng XMLFormatter.
14. **Nếu collector ngừng, reconnect có tự gửi lại toàn bộ các sự kiện bị mất không?** Không được bảo đảm; cần cơ chế bền vững/ack riêng nếu có yêu cầu.
15. **Khi LogEvent đi cả console và socket, có phải hai nghiệp vụ không?** Không, có thể chỉ là hai bản xuất của cùng một sự kiện.
16. **Tại sao phải dọn ThreadContext?** Tránh để mã yêu cầu của request trước xuất hiện trong request sau khi thread được tái sử dụng.

## 19. Tài liệu tham khảo

- Apache Log4j 2 – Network Appenders / Socket Appender: https://logging.apache.org/log4j/2.x/manual/appenders/network.html
- Apache Log4j 2 – Appenders (buffer, Failover, async): https://logging.apache.org/log4j/2.x/manual/appenders.html
- Apache Log4j 2 – Pattern Layout: https://logging.apache.org/log4j/2.x/manual/pattern-layout.html
- Apache Log4j 2 – JSON Template Layout: https://logging.apache.org/log4j/2.x/manual/json-template-layout.html
- Apache Log4j 2 – Plugin reference (Socket attributes): https://logging.apache.org/log4j/2.x/plugin-reference.html
- Oracle Java – `java.util.logging.SocketHandler`: https://docs.oracle.com/en/java/javase/25/docs/api/java.logging/java/util/logging/SocketHandler.html

**Ghi nhớ:** SocketAppender chuyển **LogEvent đã định dạng** đến một host/port qua TCP, UDP hoặc TLS. Chọn đúng **giao thức + framing + Layout** với collector; hiểu rõ giới hạn **không có xác nhận đã lưu bền**, cấu hình timeout/lỗi/fallback theo yêu cầu vận hành, và giữ dữ liệu log an toàn. Để quan sát hệ thống đáng tin cậy, phải kiểm chứng toàn bộ đường đi từ mã Java đến collector và kho lưu trữ, thay vì chỉ dựa vào việc lời gọi `LOG.info` đã chạy.
