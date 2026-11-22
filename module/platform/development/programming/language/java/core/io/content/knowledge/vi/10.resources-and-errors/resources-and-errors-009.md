# Đọc hoặc ghi dở dang khi có ngoại lệ trong Java I/O

## 1. “Đã đọc/ghi một phần” nghĩa là gì?

Một thao tác I/O thường trải qua nhiều bước: lấy byte từ nguồn, đi qua các buffer hoặc bộ mã hóa, rồi tới tệp, socket hoặc thiết bị. Nếu một bước gặp lỗi, dữ liệu có thể đã được **tiêu thụ hoặc gửi đi một phần** trước khi phương thức báo ngoại lệ.

Ví dụ:

- Đọc bản ghi dự kiến 100 byte, nhận 40 byte rồi kết nối gặp lỗi.
- Ghi 5 byte vào một luồng, ba byte đầu đến đích rồi byte thứ tư gây `IOException`.
- Ghi văn bản vào `BufferedWriter` chưa báo lỗi, nhưng `flush()` hoặc `close()` mới phát hiện đích đã hỏng.
- Tạo một tệp đầu ra rồi ứng dụng lỗi giữa chừng, khiến tệp có nội dung nhưng **chưa hoàn chỉnh**.

**Nguyên tắc:** `IOException` không tự động hoàn tác mọi byte đã đọc hoặc ghi. “Phương thức ném ngoại lệ” **không có nghĩa** “chưa có byte nào thay đổi”. Ngược lại, một lệnh `write()` trả về bình thường cũng không nhất thiết chứng minh dữ liệu đã được lưu bền vững hay phía nhận đã xử lý.

Vì vậy phải tách ba trạng thái:

| Trạng thái | Điều đã biết | Điều chưa được bảo đảm |
| --- | --- | --- |
| Đọc thành công một phần | Một lượng dữ liệu đã được đưa lên ứng dụng | Chưa chắc có đủ bản ghi/thông điệp |
| Ghi đã trả về | API đã chấp nhận thao tác theo hợp đồng tầng đó | Chưa chắc đã flush, lưu bền vững hoặc nhận được ACK |
| Ngoại lệ I/O | Thao tác không hoàn thành theo cách đã yêu cầu | Chưa chắc mọi tác động trước đó đã bị đảo ngược |

Đây là vấn đề **tính toàn vẹn dữ liệu và quản lý lỗi**, không chỉ là việc thêm một `catch`.

## 2. Đọc theo khối: trả ít byte không phải lúc nào cũng là lỗi

Một lời gọi `InputStream.read(byte[])` hoặc `read(byte[], offset, length)` có thể trả về **ít byte hơn số byte được yêu cầu**, ngay cả khi chưa hết nguồn. Chẳng hạn gọi đọc 1.024 byte nhưng nhận kết quả `37` là tình huống hợp lệ: 37 byte đầu mảng vừa được điền, các byte còn lại không thuộc dữ liệu mới đọc.

- Kết quả **dương**: số byte thực tế vừa đọc.
- Kết quả **`-1`**: EOF, nguồn báo hết dữ liệu.
- Có **`IOException`**: lỗi I/O. Không được đồng nhất lỗi này với EOF.
- Với yêu cầu độ dài **0**, kết quả có thể là `0`; không thể coi mọi `0` là EOF.

Mẫu đọc đến EOF, xử lý đúng số byte nhận được:

```java
byte[] block = new byte[4096];
int count;

while ((count = input.read(block)) != -1) {
    consume(block, 0, count);
}
```

Đây là **đoạn mã minh họa**: `input` là `InputStream` đã mở; `consume` là hàm của ứng dụng và có thể ném lỗi; cần quản lý nguồn bằng `try-with-resources` ở cấp thích hợp.

Nếu chỉ cần một bản ghi độ dài cố định, **đọc đến EOF** lại có thể là cách sai. Phải biết số byte kỳ vọng và lặp cho đủ (hoặc dùng `DataInputStream.readFully(...)`). Đọc ít byte vì chưa sẵn sàng khác với một bản ghi **bị cắt cụt**.

**Lưu ý về lỗi giữa một lần đọc khối:** Hợp đồng `InputStream` gốc cho phép một số cách cài đặt `read(byte[], off, len)` trả số byte đã nhận nếu xảy ra ngoại lệ **sau byte đầu tiên** trong cùng lần gọi; cũng có lớp đọc ném ngoại lệ trực tiếp. Do đó không giả định rằng ngoại lệ luôn xuất hiện ở vị trí chính xác byte lỗi nếu dùng đọc theo khối. Với dữ liệu quan trọng, quản lý ranh giới bản ghi và kiểm chứng độ dài của cả thông điệp.

## 3. Ví dụ Java 17+: nguồn đọc lỗi sau ba byte

Tạo file **`PartialReadDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.StringJoiner;

public class PartialReadDemo {
    static class FailingInputStream extends InputStream {
        private final byte[] data = {10, 20, 30, 40};
        private int position;

        @Override
        public int read() throws IOException {
            if (position == 3) {
                throw new IOException("simulated connection loss");
            }
            if (position >= data.length) {
                return -1;
            }
            return data[position++] & 0xFF;
        }
    }

    public static void main(String[] args) {
        StringJoiner received = new StringJoiner(" ");

        try (InputStream input = new FailingInputStream()) {
            int value;
            while ((value = input.read()) != -1) {
                received.add(Integer.toString(value));
            }
        } catch (IOException ex) {
            System.out.println("Lỗi đọc: " + ex.getMessage());
        }

        System.out.println("Đã nhận: " + received);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 PartialReadDemo.java
java PartialReadDemo
```

Đầu ra:

```text
Lỗi đọc: simulated connection loss
Đã nhận: 10 20 30
```

Luồng cho phép đọc ba byte đầu; lần đọc thứ tư ném `IOException`. Không có `-1`: chương trình **chưa thấy EOF hợp lệ**. Ba byte đã được ứng dụng tiếp nhận vẫn tồn tại trong `StringJoiner`; Java không tự rút lại chúng.

Nếu dữ liệu là một bản ghi gồm bốn byte thì không được âm thầm coi `10 20 30` là bản ghi hợp lệ. Cần thông báo bản ghi thiếu, hủy kết quả xử lý chưa commit hoặc đợi quy trình phục hồi theo giao thức.

## 4. Ghi dở dang: lỗi không có nghĩa là đích vẫn nguyên vẹn

`OutputStream.write(int)` ghi một byte hoặc ném `IOException`. Khi ứng dụng ghi **nhiều byte**, những byte đầu có thể đã được ghi trước khi sự cố xuất hiện. Hợp đồng của `OutputStream` không cung cấp rollback.

Ví dụ độc lập **`PartialWriteDemo.java`** tạo đích mô phỏng chỉ chấp nhận ba byte:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.HexFormat;

public class PartialWriteDemo {
    static class LimitedOutputStream extends OutputStream {
        private final ByteArrayOutputStream destination;
        private final int limit;
        private int written;

        LimitedOutputStream(ByteArrayOutputStream destination, int limit) {
            this.destination = destination;
            this.limit = limit;
        }

        @Override
        public void write(int value) throws IOException {
            if (written >= limit) {
                throw new IOException("simulated disk failure");
            }
            destination.write(value);
            written++;
        }
    }

    public static void main(String[] args) {
        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        try (OutputStream output = new LimitedOutputStream(destination, 3)) {
            output.write(new byte[]{1, 2, 3, 4, 5});
        } catch (IOException ex) {
            System.out.println("Lỗi ghi: " + ex.getMessage());
        }

        System.out.println("Byte còn lại: "
                + HexFormat.of().formatHex(destination.toByteArray()));
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 PartialWriteDemo.java
java PartialWriteDemo
```

Kết quả:

```text
Lỗi ghi: simulated disk failure
Byte còn lại: 010203
```

Trong ví dụ, `OutputStream.write(byte[])` kế thừa từ `OutputStream` gọi `write(int)` lần lượt; sau byte thứ ba, byte thứ tư gây lỗi. **Ba byte `01 02 03` vẫn còn trong đích**. Đây là mô phỏng để thấy một thao tác “ghi mảng” không đồng nghĩa với transaction ghi cả mảng hoặc không ghi gì.

Các triển khai chuyên biệt có thể có cách ghi theo khối khác. Không suy từ ví dụ rằng mọi `write(byte[])` luôn thực hiện từng byte, hoặc ngoại lệ luôn cho biết chính xác số byte đã ghi. Với tệp hoặc socket thật, trạng thái phía đích có thể chỉ xác định được qua kiểm chứng hoặc giao thức xác nhận.

## 5. Buffer khiến thời điểm phát hiện lỗi bị trễ

`BufferedOutputStream` và `BufferedWriter` có thể giữ dữ liệu trong RAM. Khi gọi `write(...)`, dữ liệu được đưa vào **buffer** trước; lỗi ở đích bên dưới đôi khi chỉ xuất hiện khi:

- Buffer đầy và tự đẩy xuống.
- Chương trình gọi `flush()`.
- Chương trình gọi `close()`, thường có bước đẩy dữ liệu còn lại xuống trước khi đóng.

Ví dụ độc lập **`BufferedFailureDemo.java`**:

```java
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.HexFormat;

public class BufferedFailureDemo {
    static class LimitedOutputStream extends OutputStream {
        private final ByteArrayOutputStream destination;
        private int written;

        LimitedOutputStream(ByteArrayOutputStream destination) {
            this.destination = destination;
        }

        @Override
        public void write(int value) throws IOException {
            if (written == 3) {
                throw new IOException("simulated device failure");
            }
            destination.write(value);
            written++;
        }
    }

    public static void main(String[] args) {
        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        try (BufferedOutputStream output = new BufferedOutputStream(
                new LimitedOutputStream(destination), 8)) {
            output.write(new byte[]{1, 2, 3, 4, 5});
            System.out.println("write() chưa báo lỗi");
            output.flush();
        } catch (IOException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }

        System.out.println("Byte đã xuống đích: "
                + HexFormat.of().formatHex(destination.toByteArray()));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BufferedFailureDemo.java
java BufferedFailureDemo
```

Đầu ra:

```text
write() chưa báo lỗi
Lỗi: simulated device failure
Byte đã xuống đích: 010203
```

Vì buffer có sức chứa 8 byte và ứng dụng mới ghi 5 byte, `write()` hoàn tất mà chưa gọi luồng dưới. `flush()` bắt đầu chuyển byte tới `LimitedOutputStream` và gặp lỗi sau 3 byte.

**Hệ quả:** Thành công của `BufferedWriter.write(...)` hay `BufferedOutputStream.write(...)` có thể mới chỉ là thành công **ghi vào bộ đệm**. Phải xử lý ngoại lệ ở cả `flush()` và `close()`. `flush()` cũng không đồng nghĩa dữ liệu đã được đồng bộ an toàn xuống thiết bị lưu trữ hoặc phía nhận đã xử lý: đây là các cam kết khác nhau ở những tầng khác nhau.

Nếu lỗi xảy ra lúc flush, buffer có thể vẫn giữ dữ liệu chưa được chuyển, hoặc lớp dưới đã chấp nhận một phần. Gọi lại cùng `write(...)` mù quáng dễ tạo **dữ liệu lặp**.

## 6. Bản ghi có cấu trúc: đủ byte mới được coi là hoàn chỉnh

Xét định dạng nhị phân:

```text
[int payloadLength: 4 byte][payload: đúng payloadLength byte]
```

Phía đọc phải có chính xác bốn byte cho `int`, sau đó có chính xác `payloadLength` byte cho payload. Cả hai bước có thể thất bại dở dang.

`DataInputStream` hỗ trợ:

- `readInt()`: cần đủ bốn byte để tạo `int`, nếu nguồn hết sớm sẽ ném `EOFException`.
- `readFully(byte[])`: cố đọc đủ độ dài mảng, nếu EOF trước khi đủ sẽ ném `EOFException`. **Mảng có thể đã được ghi một phần trước khi có ngoại lệ**.
- `read(byte[])`: có thể trả ít byte hơn số yêu cầu, nên không dùng một lần gọi thay cho `readFully`.

Ví dụ **`TruncatedRecordDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.EOFException;
import java.io.IOException;
import java.util.HexFormat;

public class TruncatedRecordDemo {
    public static void main(String[] args) throws IOException {
        byte[] truncated = {0, 0, 0, 3, 0x41, 0x42};

        try (DataInputStream input = new DataInputStream(
                new ByteArrayInputStream(truncated))) {
            int length = input.readInt();
            if (length < 0 || length > 1024) {
                throw new IOException("Invalid payload length");
            }

            byte[] payload = new byte[length];
            try {
                input.readFully(payload);
                System.out.println("Bản ghi hoàn chỉnh");
            } catch (EOFException ex) {
                System.out.println("Thiếu byte của payload");
                System.out.println("Không commit: "
                        + HexFormat.of().formatHex(payload));
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 TruncatedRecordDemo.java
java TruncatedRecordDemo
```

Đầu ra:

```text
Thiếu byte của payload
Không commit: 414200
```

Payload yêu cầu 3 byte nhưng trong luồng chỉ còn `41 42`. `readFully` đã ghi hai byte vào mảng trước khi gặp EOF; phần tử thứ ba giữ giá trị mặc định `00`. **Không được dùng mảng `41 42 00` làm dữ liệu thật**: byte `00` ở đây là mặc định bộ nhớ chứ không phải byte thứ ba từ nguồn.

Điểm quan trọng: `readFully` giúp phát hiện bản ghi chưa đủ, nhưng **không hoàn tác** những thay đổi đã có trong mảng đích. Chỉ công bố bản ghi sang phần còn lại của ứng dụng **sau khi** kiểm tra xong độ dài và tính hợp lệ.

## 7. Phân biệt EOF, IOException và dữ liệu sai nhưng đọc không báo lỗi

| Tình huống | Ý nghĩa | Hành động phù hợp |
| --- | --- | --- |
| `read() == -1` | Nguồn báo đã hết byte | Kiểm tra EOF có được schema cho phép ở vị trí này không |
| `EOFException` | Phương thức cần thêm byte cho một giá trị/bản ghi nhưng không còn | Coi là dữ liệu cắt cụt trừ khi giao thức định nghĩa khác |
| `IOException` | Trục trặc I/O, ví dụ thiết bị hoặc socket lỗi | Giữ nguyên bối cảnh lỗi; xác định phần dữ liệu đã xử lý và chính sách phục hồi |
| Đủ số byte nhưng checksum sai | Dữ liệu đã đến nhưng không đạt kiểm tra toàn vẹn | Bác bỏ bản ghi, không công bố dữ liệu |
| Đủ byte nhưng trường sai thứ tự | Parser diễn giải sai, có thể không ném ngoại lệ | Kiểm tra schema, version, kiểu và offset |

Không viết:

```java
try {
    parseRecord(input);
} catch (IOException ex) {
    // bỏ qua và tiếp tục dùng kết quả đã parse một nửa
}
```

Đây là **mã minh họa một anti-pattern**. Nếu bộ phân tích đã cập nhật đối tượng nghiệp vụ trước khi đọc đủ bản ghi, việc bỏ qua ngoại lệ có thể để lại trạng thái không nhất quán.

Cách tốt hơn là đọc vào **biến cục bộ/đối tượng tạm**, xác thực hết các trường và checksum (nếu có), rồi mới thêm vào danh sách hoặc thay đổi trạng thái chính thức. Không công bố một phần bản ghi khi chưa đạt điều kiện hoàn chỉnh.

## 8. Ghi tệp an toàn hơn: tệp tạm rồi công bố

Ghi trực tiếp vào đường dẫn đích có thể khiến người đọc nhìn thấy **tệp mới chỉ ghi một phần** nếu chương trình hoặc thiết bị lỗi. Với trường hợp cần thay thế trọn vẹn nội dung tệp, cách thường dùng là:

1. Tạo **tệp tạm trong cùng thư mục/hệ thống tệp** với đích.
2. Ghi **toàn bộ** nội dung mới vào tệp tạm.
3. Hoàn tất writer và kiểm tra dữ liệu nếu cần.
4. Chuyển tên (rename/move) tệp tạm thành tên đích khi dữ liệu đã sẵn sàng.
5. Nếu có lỗi trước bước công bố, xóa tệp tạm; giữ tệp đích cũ nếu vẫn có thể.

Đoạn minh họa Java 17+:

```java
Path target = Path.of("result.txt").toAbsolutePath();
Path directory = target.getParent();
Path temporary = Files.createTempFile(directory, ".result-", ".tmp");

try {
    Files.writeString(temporary, text, StandardCharsets.UTF_8);
    // Khi định dạng yêu cầu, kiểm tra nội dung tệp temporary tại đây.
    Files.move(temporary, target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} finally {
    Files.deleteIfExists(temporary);
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Cần import `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.file.StandardCopyOption`, `java.nio.charset.StandardCharsets`; khai báo `String text`, xử lý `IOException` và quyết định chính sách ghi đè theo nghiệp vụ. Đừng chạy với đường dẫn dữ liệu quan trọng khi chưa kiểm tra quyền sở hữu và nhu cầu thay thế.

**Giới hạn phải hiểu:**

- `ATOMIC_MOVE` **có thể không được filesystem hỗ trợ**, khi đó có thể nhận `AtomicMoveNotSupportedException`. Không âm thầm bỏ cờ atomic rồi tuyên bố dữ liệu vẫn được công bố nguyên khối.
- Khi `ATOMIC_MOVE` đi cùng các option khác, chi tiết thay thế đích tồn tại có thể phụ thuộc filesystem/provider. Cần kiểm tra hợp đồng và thử nghiệm trên môi trường triển khai.
- Atomic rename liên quan đến **tính nhìn thấy nguyên khối của tên tệp**, không tự bảo đảm **durability khi mất điện**. Khi yêu cầu độ bền dữ liệu chặt chẽ, cần cơ chế sync/force và quản lý thư mục phù hợp với hệ điều hành/filesystem.
- Nếu ứng dụng viết nhiều tệp hoặc đồng thời thay đổi database, rename **không tạo transaction xuyên nhiều tài nguyên**.
- Khi move lỗi hoặc có tác nhân ghi đồng thời, phải bảo đảm cách xử lý không xóa nhầm tệp người khác và không ghi đè phiên bản mới.

Với tệp nhỏ và không yêu cầu tính nguyên khối, `Files.writeString(...)` trực tiếp có thể đủ. Nhưng khi yêu cầu “hoặc tệp cũ nguyên vẹn, hoặc tệp mới hoàn chỉnh”, nên thiết kế đường commit rõ ràng thay vì chỉ dựa vào `try-with-resources`.

## 9. `try-with-resources` và lỗi trong `close()`

`try-with-resources` giúp đóng tài nguyên ngay cả khi mã bên trong ném ngoại lệ. Tuy nhiên:

- Đóng tài nguyên **không rollback** byte đã ghi.
- `close()` tự nó có thể ném `IOException`, đặc biệt khi đẩy buffer đang chờ xuống tầng dưới.
- Nếu khối `try` đang có một ngoại lệ chính và `close()` cũng lỗi, Java giữ ngoại lệ của khối làm **primary exception**, còn lỗi đóng thường nằm trong `getSuppressed()`.
- Không nên ghi đè hoặc bỏ mất primary exception vì chỉ quan tâm lỗi close.

Ví dụ độc lập **`SuppressedCloseDemo.java`**:

```java
import java.io.IOException;

public class SuppressedCloseDemo {
    static class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("write failed");
        } catch (IOException ex) {
            System.out.println("Primary: " + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("Suppressed: "
                        + suppressed.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac SuppressedCloseDemo.java
java SuppressedCloseDemo
```

Đầu ra:

```text
Primary: write failed
Suppressed: close failed
```

Khi gỡ lỗi thực tế, lưu cả primary exception và suppressed exceptions trong log phù hợp. Đừng ghi log trùng lặp hoặc vô tình làm lộ dữ liệu nhạy cảm, token hoặc toàn bộ payload khách hàng.

## 10. Retry và nguy cơ nhân đôi dữ liệu

Khi ghi sang socket, database gateway hoặc dịch vụ từ xa, không phải lúc nào phía gửi cũng biết **đã gửi/nhận thành công bao nhiêu byte** sau lỗi:

```text
Client                       Server
  | ---- message bytes ---->  |
  | ---- message bytes --X    |  lỗi kết nối ở phía client
  |                            |
  |  Server có thể đã nhận/    |
  |  xử lý một phần hoặc đủ.   |
```

Gửi lại toàn bộ request mà không có cơ chế chống trùng có thể tạo hai giao dịch. Ngược lại, chỉ gửi phần còn thiếu mà không biết chính xác offset đã được xác nhận cũng có thể làm hỏng stream.

Các cách tiếp cận tùy giao thức:

- **Framing**: có tiền tố độ dài, message ID, version và checksum/hash để nhận biết ranh giới và tính hợp lệ.
- **Idempotency key**: phía nhận ghi nhận ID duy nhất và không thực thi cùng một tác vụ hai lần nếu nhận lại request. Khả năng chống trùng phải được triển khai phía nhận.
- **ACK theo thông điệp**: chỉ coi request hoàn tất khi nhận được phản hồi theo giao thức; một ACK cũng có thể bị mất, nên vẫn cần cơ chế chống trùng.
- **Resume với offset đã xác nhận**: chỉ thực hiện khi giao thức hỗ trợ vị trí byte, checksum và trạng thái phiên rõ ràng; không tự đoán offset từ số byte client đã đưa cho `write()`.
- **Retry có giới hạn**: thời gian chờ, backoff và quy tắc lỗi được phép retry. Một exception không đủ để xác định thao tác trước có an toàn để lặp lại không.

Với việc chuyển file lớn, có thể ghi ra một tên tạm ở server, kiểm tra độ dài và checksum rồi mới công bố; không cho phía khác đọc tài liệu đang nhận dở.

## 11. Khi dùng `Reader`, `Writer` và charset

Dữ liệu ký tự cũng có thể dở dang:

- `Reader.read(char[])` trả số `char` thực đọc. Nó không bảo đảm lấp đầy mảng.
- `BufferedReader.readLine()` có thể trả một dòng cuối không có newline nếu **EOF hợp lệ** xảy ra sau nội dung dòng. Nhưng nếu nguồn gặp `IOException` giữa dòng, không được tự coi đó là một record hoàn chỉnh.
- `OutputStreamWriter` chuyển `char` sang byte theo charset. Một ký tự Unicode có thể tạo nhiều byte UTF-8, nên đứt luồng có thể để lại **chuỗi byte UTF-8 không hoàn chỉnh**.
- `BufferedWriter` có thể giữ ký tự chưa gửi xuống bộ mã hóa. Lỗi ở `close()` hoặc `flush()` có thể để lại đích chưa hoàn chỉnh.
- Với `CharsetDecoder` cấu hình `CodingErrorAction.REPORT`, chuỗi byte không hợp lệ có thể gây lỗi mã hóa/giải mã được báo rõ, thay vì âm thầm chèn ký tự thay thế.

Một dữ liệu text là một **tài liệu hoặc bản ghi có cấu trúc**, không chỉ là tập hợp các ký tự. Ví dụ CSV có thể đang ở giữa chuỗi có dấu ngoặc kép; JSON có thể thiếu dấu đóng ngoặc. Bản thân việc đọc được `String` chưa chứng minh tài liệu hợp lệ. Hãy parse và chỉ công bố dữ liệu khi cú pháp và kiểm tra nghiệp vụ đã hoàn tất.

Với nguồn mạng, dòng cuối chưa có newline có thể vẫn là nội dung hợp lệ nếu protocol dùng EOF để đánh dấu kết thúc; nhưng nếu luồng bị lỗi giữa dòng, không thể khẳng định đó là EOF chuẩn. Ranh giới hợp lệ phải do **giao thức** định nghĩa.

## 12. Theo dõi tiến độ và phục hồi có kiểm soát

Khi ghi/đọc khối lớn, theo dõi số byte xử lý **đã được xác nhận ở tầng thích hợp**, ví dụ:

```java
long totalRead = 0;
byte[] buffer = new byte[8192];
int count;

while ((count = input.read(buffer)) != -1) {
    process(buffer, 0, count);
    totalRead += count;
}
```

Đây là **đoạn minh họa**, cần `input` và `process` hợp lệ. `totalRead` chỉ cho biết **byte ứng dụng đã xử lý sau `process` thành công**, không tự chứng minh dữ liệu đã được commit ở nơi khác. Nếu `process` ném lỗi sau khi xử lý một phần block, biến đếm có thể chưa phản ánh đúng mọi tác động đã diễn ra. Thiết kế cập nhật offset và commit phải bám vào ngữ nghĩa thao tác thực tế.

Khi có ngoại lệ, nên thu thập đủ ngữ cảnh để gỡ lỗi:

1. Tên thao tác: đọc header, đọc payload, flush output, close, rename...
2. Bản ghi/chunk số mấy, offset kỳ vọng, số byte xác nhận đã xử lý.
3. Độ dài và checksum mong đợi, kết quả kiểm tra thực tế.
4. Nguyên nhân ngoại lệ và suppressed exception nếu có.
5. Có thể tiếp tục trên cùng stream hay phải mở lại phiên mới.
6. Kết quả đang là **tạm thời**, đã **commit**, hay **không xác định**.

Không nhất thiết log nội dung byte thô hoặc toàn bộ file, nhất là khi dữ liệu có thông tin riêng tư. Thông thường metadata kỹ thuật và mã lỗi đã đủ hỗ trợ chẩn đoán.

## 13. Sai lầm phổ biến và hướng khắc phục

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| `catch (IOException)` rồi coi như EOF | Dùng dữ liệu thiếu thành bản ghi hợp lệ | Phân biệt kết thúc đúng schema với thất bại |
| Tin `read(byte[])` luôn lấp đầy mảng | Byte cũ/byte mặc định lẫn vào kết quả | Dùng số byte trả về hoặc `readFully` |
| Bắt `EOFException` và vẫn dùng mảng đang đọc | Mảng có thể đã bị sửa một phần | Chỉ công bố payload sau khi hoàn tất |
| Tin `write(byte[])` ném lỗi nghĩa là 0 byte đã ghi | File/socket có thể đã đổi một phần | Xem kết quả là không xác định; kiểm chứng hoặc thiết kế commit |
| Bỏ qua lỗi `flush()`/`close()` | Dữ liệu bị kẹt hoặc mất ở buffer | Xử lý lỗi ở tất cả ranh giới hoàn tất |
| Retry `write` toàn bộ ngay sau lỗi | Có thể nhân đôi bản ghi | Dùng message ID, ACK, idempotency hoặc resume có xác nhận |
| Ghi thẳng vào file đích quan trọng | File mới có thể bị cắt cụt | Ghi tạm rồi công bố theo điều kiện filesystem |
| Coi atomic rename là đồng nghĩa fsync | Mất điện vẫn có thể ảnh hưởng độ bền | Phân biệt atomic visibility với durability |
| Bỏ qua chiều dài khai báo | Cấp phát quá lớn hoặc chấp nhận bản ghi thiếu | Xác thực độ dài và byte thực đọc |
| Parser cập nhật đối tượng thật từng field | Ngoại lệ để lại trạng thái nửa chừng | Parse vào trạng thái tạm và commit khi hợp lệ |
| Mất primary exception vì lỗi `close` | Chẩn đoán sai nguyên nhân | Dùng `try-with-resources` và đọc suppressed exception |
| Đếm số byte “đã viết” bằng số lần gọi `write` | Không biết chính xác phía đích đã nhận bao nhiêu | Dựa trên xác nhận của giao thức/đích |

## 14. Checklist và bài tự luyện

**Trước khi đọc:**

- [ ] Xác định chính xác độ dài, delimiter, EOF marker hoặc quy tắc framing.
- [ ] Dự kiến và xử lý trường hợp `read(...)` trả ít hơn yêu cầu.
- [ ] Không công bố dữ liệu cho nghiệp vụ khi chưa đọc đủ và validate.
- [ ] Phân biệt EOF hợp lệ với `IOException` và EOF giữa bản ghi.
- [ ] Giới hạn độ dài/record count để tránh cấp phát không kiểm soát.

**Trước khi ghi:**

- [ ] Xác định dữ liệu có cần “all-or-nothing” ở mức file/message hay không.
- [ ] Không giả định một `write(...)` là transaction.
- [ ] Hoàn tất writer, kiểm tra `flush`, `close` và mọi ngoại lệ.
- [ ] Có cơ chế commit (temp file/rename) hoặc ACK theo giao thức nếu cần.
- [ ] Xây chiến lược retry tránh trùng và tránh mất dữ liệu.
- [ ] Phân biệt “byte đã được API nhận”, “đã đến phía bên kia”, “đã ghi bền vững” và “đã được xử lý”.

**Bài tự luyện 1 — nguồn bị cắt:** Với định dạng `[int length=5][5 byte payload]` nhưng nguồn chỉ chứa 3 byte payload, dùng `DataInputStream.readFully` và kiểm chứng `EOFException`. Giải thích vì sao mảng 5 byte có thể chứa ba byte thật và hai byte mặc định.

**Bài tự luyện 2 — đích bị lỗi:** Tạo `OutputStream` ném `IOException` sau `N` byte. Ghi dữ liệu qua `BufferedOutputStream`, thử các kích thước buffer khác nhau và dự đoán lỗi xuất hiện ở `write`, `flush` hay `close`. Không gọi lại `write` mù quáng sau khi lỗi.

**Bài tự luyện 3 — cập nhật file:** Thiết kế việc xuất một báo cáo lớn sao cho người đọc khác không nhìn thấy bản báo cáo dở dang. Mô tả rõ tệp tạm, thời điểm kiểm tra, cách công bố, chính sách khi `ATOMIC_MOVE` không hỗ trợ và yêu cầu durability có hay không.

**Ghi nhớ:** I/O là quá trình có thể **thành công một phần**. Java báo lỗi qua ngoại lệ nhưng không tự hoàn tác các tác động trước đó. Muốn an toàn, phải xác định ranh giới bản ghi, kiểm tra đủ byte, tách kết quả tạm khỏi dữ liệu đã commit, xử lý lỗi buffer/close, và thiết kế phục hồi hoặc retry theo giao thức.