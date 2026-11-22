# Java 7 — Files: Tùy chọn tạo mới, ghi thêm, cắt nội dung và ghi đồng bộ

## 1. Vì sao tùy chọn mở file quan trọng?

Với `java.nio.file.Files`, cùng một tên file nhưng các lệnh ghi có thể dẫn tới **những hành vi rất khác nhau**:

- Chỉ tạo mới khi file **chưa tồn tại**, tuyệt đối không ghi đè: `CREATE_NEW`.
- Tạo file nếu thiếu nhưng vẫn mở file đã tồn tại: `CREATE`.
- Ghi tiếp vào **cuối file**: `APPEND`.
- Xóa nội dung cũ ngay khi mở để ghi: `TRUNCATE_EXISTING`.
- Cho phép ghi byte: `WRITE`.
- Yêu cầu ghi cập nhật xuống thiết bị lưu trữ theo hợp đồng đồng bộ: `SYNC` hoặc `DSYNC`.

Các lựa chọn này được biểu diễn bằng enum **`java.nio.file.StandardOpenOption`**, triển khai giao diện `OpenOption`. Chúng có từ Java 7 và **vẫn là API hiện hành** trên JDK 17+. Biết rõ từng lựa chọn giúp tránh ba nhóm lỗi nghiêm trọng: **ghi đè hoặc cắt mất dữ liệu**, **ghi thêm sai chỗ**, và **đánh đồng “đã gọi write” với dữ liệu đã bền vững trên thiết bị lưu trữ**.

Bài này tập trung vào **cách sử dụng tùy chọn khi tạo/mở/ghi file** qua `Files` và `FileChannel`. Không sử dụng API file cũ đã bị thay thế nếu thư viện NIO.2 có cách diễn đạt rõ hơn. Ví dụ chạy với **Java 17+**; những phương thức như `Files.writeString` xuất hiện từ Java 11, trong khi nhóm `StandardOpenOption` đã có từ Java 7.

## 2. Các lựa chọn StandardOpenOption và ý nghĩa chính xác

| Tùy chọn | Tác động khi mở file | Cần chú ý |
| --- | --- | --- |
| `READ` | Mở để đọc | Không mặc định cho phép ghi |
| `WRITE` | Mở để ghi | **Không tự cắt ngắn** file cũ |
| `CREATE` | Tạo nếu chưa tồn tại; nếu đã tồn tại thì mở tiếp | **Không** đồng nghĩa “fail if exists” |
| `CREATE_NEW` | Chỉ tạo file mới; thất bại nếu tên đã tồn tại | Kiểm tra tồn tại + tạo được thực hiện **atomically** theo hợp đồng |
| `APPEND` | Mỗi lần ghi nhằm tới cuối file | Không hứa toàn bộ nhiều lần ghi là một giao dịch nguyên tử |
| `TRUNCATE_EXISTING` | Nếu file tồn tại và mở với quyền `WRITE`, rút chiều dài file về **0 byte** | Dữ liệu cũ có thể mất trước khi ghi nội dung mới thành công |
| `SYNC` | Yêu cầu đồng bộ cập nhật **nội dung và metadata** tới thiết bị lưu trữ | Chi phí I/O cao; không thay thế giao dịch hoặc atomic rename |
| `DSYNC` | Yêu cầu đồng bộ cập nhật **nội dung** tới thiết bị lưu trữ | Không đưa ra cùng cam kết metadata như `SYNC` |
| `DELETE_ON_CLOSE` | Cố gắng xóa file khi đóng channel/stream | Best effort và có giới hạn bảo mật/portable |
| `SPARSE` | Gợi ý tạo sparse file khi phù hợp | Provider có thể bỏ qua; không phải trọng tâm của thao tác ghi văn bản |

`StandardOpenOption` có từ Java 7 và vẫn hợp lệ trên Java 17+. Các option được truyền bằng varargs vào một số phương thức của `Files`, ví dụ:

```java
Files.writeString(path, text, StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND);
```

Đây là **snippet đặt trong phương thức** có `Path path`, `String text`, import `java.nio.file.Files`, `java.nio.charset.StandardCharsets`, `java.nio.file.StandardOpenOption` và xử lý `IOException`. Tùy chọn được kết hợp theo đúng hợp đồng của **phương thức đang gọi**, không phải mọi bộ option đều hợp lệ cho mọi API hay mọi provider.

**Nguyên tắc:** Option nêu một **yêu cầu khi mở file**, không phải lời khẳng định file chắc chắn tồn tại, tiến trình có quyền ghi, thao tác sẽ thành công, hay mọi file system đều hỗ trợ tính năng đó.

## 3. API nào nhận các tùy chọn này?

### 3.1. Files.writeString: ghi văn bản với charset

```java
Files.writeString(path, "Xin chào", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE);
```

Đây là snippet trong phương thức. `writeString(Path, CharSequence, Charset, OpenOption...)` có từ Java 11, phù hợp Java 17+. Nó encode text theo charset được chọn, ghi vào file và đóng tài nguyên liên quan khi hoàn tất hoặc khi lỗi.

**Không tự thêm ký tự xuống dòng:** nếu dữ liệu phải có newline, hãy đưa `"\n"` hoặc cấu trúc line ending mong muốn vào chuỗi. Một lời gọi `writeString` không tương đương một “log record” được đảm bảo nguyên tử.

### 3.2. Files.write: ghi byte[] và các dòng văn bản

```java
byte[] bytes = "HELLO".getBytes(StandardCharsets.UTF_8);
Files.write(path, bytes,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
```

Snippet trong phương thức. `Files.write(Path, byte[], OpenOption...)` có từ Java 7. Nó phù hợp khi đã có payload bytes, không phải String. Nếu ghi text, hãy xác định charset rõ ràng tại bước chuyển String → bytes.

Overload `Files.write(path, Iterable<? extends CharSequence> lines, charset, options...)` ghi nhiều dòng và thêm **line separator của nền tảng** theo hợp đồng của API. Điều đó khác với `Files.writeString`, vốn giữ nguyên các ký tự trong `CharSequence` và không tự thêm newline.

### 3.3. Files.newBufferedWriter: tạo writer cho file lớn

```java
try (var writer = Files.newBufferedWriter(path,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND,
        StandardOpenOption.WRITE)) {
    writer.write("event=ready");
    writer.newLine();
}
```

Đây là snippet Java 17+ với `Path path` và xử lý `IOException`. `newBufferedWriter` có từ Java 7; `var` có từ Java 10. Với tệp nhiều dòng hoặc ghi theo streaming, writer giúp tránh phải tạo sẵn một String cực lớn. **Try-with-resources** đóng writer cả khi có ngoại lệ; các lỗi ghi có thể được báo ở `write`, `flush` hoặc `close`.

### 3.4. Files.newOutputStream và newByteChannel

```java
try (var out = Files.newOutputStream(path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND)) {
    out.write(new byte[] {65, 66, 67});
}
```

Snippet trong phương thức; ghi các byte ASCII “ABC” vào cuối file. `newOutputStream` mở byte stream; `newByteChannel` mở seekable byte channel, có thể đọc/ghi và truy cập vị trí. Chúng cũng nhận `OpenOption` nhưng có **quy tắc kết hợp và mặc định riêng**.

### 3.5. FileChannel.open và FileChannel.force

```java
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    ByteBuffer buffer = StandardCharsets.UTF_8.encode("record");
    while (buffer.hasRemaining()) {
        channel.write(buffer);
    }
    channel.force(true);
}
```

Đây là snippet trong phương thức có import `java.nio.channels.FileChannel` và `java.nio.ByteBuffer`, cần xử lý `IOException`. `SYNC` yêu cầu đồng bộ các cập nhật khi ghi; `force(true)` là **lệnh yêu cầu đẩy dữ liệu + metadata** một cách tường minh. Trong ví dụ trên, `force(true)` minh họa API và có thể **dư thừa** khi channel đã mở với `SYNC`; không cần gọi ở mỗi vòng lặp trong ứng dụng thật.

**Phân biệt:** `StandardOpenOption.SYNC/DSYNC` là **chính sách của channel khi mở**, còn `FileChannel.force(boolean)` là **thao tác chủ động** yêu cầu đồng bộ các cập nhật. Một writer được buffer có thể còn dữ liệu trong bộ nhớ JVM: phải hoàn tất/flush buffer hoặc đóng writer để các byte thực sự được gửi xuống channel trước khi kỳ vọng các cơ chế sync của channel có hiệu lực.

## 4. Mặc định của các API ghi: điều rất dễ gây mất dữ liệu

Các overload không truyền tùy chọn có hành vi cụ thể. Trên Java 17:

| Phương thức không truyền OpenOption | Hành vi mặc định khi mở để ghi |
| --- | --- |
| `Files.write(path, byte[])` | `CREATE + TRUNCATE_EXISTING + WRITE` |
| `Files.writeString(path, text, charset)` | `CREATE + TRUNCATE_EXISTING + WRITE` |
| `Files.writeString(path, text)` | UTF-8 và `CREATE + TRUNCATE_EXISTING + WRITE` |
| `Files.newBufferedWriter(path, charset)` | `CREATE + TRUNCATE_EXISTING + WRITE` |
| `Files.newBufferedWriter(path)` | UTF-8 và `CREATE + TRUNCATE_EXISTING + WRITE` |
| `Files.newOutputStream(path)` | `CREATE + TRUNCATE_EXISTING + WRITE` |
| `Files.newByteChannel(path)` không có option | Mặc định `READ`, **không** phải ghi |
| `FileChannel.open(path)` không có option | Mặc định `READ`, **không** phải ghi |

Điểm đặc biệt: **`Files.writeString(path, "abc")` có thể làm mất toàn bộ nội dung file cũ** vì mặc định truncate trước khi ghi. Đừng xem “không truyền option” là cách giữ nội dung an toàn.

Nếu **đã truyền các option**, không tự suy rằng API sẽ bổ sung toàn bộ bộ mặc định nói trên. Ví dụ khi dùng `Files.writeString(path, text, UTF_8, WRITE)`, bạn đang yêu cầu mở để ghi **mà không yêu cầu `CREATE` hoặc `TRUNCATE_EXISTING`**; với file đã có, việc ghi bắt đầu từ đầu nhưng byte cũ phía sau có thể còn.

**Thiết kế dễ đọc:** luôn viết đủ các option quan trọng ở đoạn code có rủi ro dữ liệu, ngay cả khi provider có thể suy ra một option từ option khác.

## 5. CREATE_NEW: tạo lần đầu và tuyệt đối không thay file có sẵn

### 5.1. Hợp đồng

`StandardOpenOption.CREATE_NEW` yêu cầu:

1. Tạo file nếu tại thời điểm mở **chưa có entry** với tên đó.
2. Nếu đã tồn tại, **không mở để ghi đè**: thao tác thất bại, thường là `FileAlreadyExistsException`.
3. Việc **kiểm tra tồn tại và tạo file** là **atomic** so với các thao tác file system khác theo hợp đồng, tránh lỗi kiểm tra-đến-khi-tạo (*check-then-act race*) ở bước tạo.

Ví dụ:

```java
Files.writeString(file, "first version",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
```

Đây là snippet trong phương thức có `Path file` và xử lý `IOException`. Thao tác thành công khi file chưa tồn tại. Nếu file đã có, đừng coi việc bắt ngoại lệ rồi thử lại với `TRUNCATE_EXISTING` là một “fallback an toàn”: cách đó **hủy đúng cam kết không ghi đè**.

### 5.2. Vì sao không nên dùng Files.exists trước CREATE?

Ví dụ **có nguy cơ race**:

```java
if (Files.notExists(file)) {
    Files.writeString(file, data, StandardCharsets.UTF_8);
}
```

Đây là snippet minh họa không an toàn: giữa `notExists` và `writeString`, tiến trình khác có thể tạo file. Vì `writeString` không options **mặc định truncate**, lời gọi thứ hai có thể ghi đè nội dung file mới do tiến trình khác tạo.

Cách sửa là **đưa chính điều kiện “chưa tồn tại” vào lệnh mở**:

```java
try {
    Files.writeString(file, data, StandardCharsets.UTF_8,
            StandardOpenOption.CREATE_NEW,
            StandardOpenOption.WRITE);
} catch (FileAlreadyExistsException ex) {
    // Xử lý nghiệp vụ: file đã tồn tại, không ghi đè.
}
```

Cần import `FileAlreadyExistsException` và xử lý các `IOException` khác. Trong thực tế, nếu file đã tồn tại dưới dạng **symbolic link**, `CREATE_NEW` cũng không được dùng để lặng lẽ ghi đè link đó. Tuy vậy, `CREATE_NEW` **không tự làm mọi bước I/O về sau trở nên nguyên tử hay chống được mọi rủi ro symlink/race ở parent directory**.

### 5.3. CREATE_NEW khác Files.createFile

`Files.createFile(path)` cũng tạo file mới với bước kiểm tra+tạo atomic, thất bại nếu đã có; nhưng **chỉ tạo file rỗng**. Nếu muốn tạo file rồi ghi nội dung, tách `createFile` và `writeString` thành hai lệnh có thể tạo khoảng trống cho một writer khác can thiệp. Khi muốn **tạo và ghi qua một lần mở**, `Files.writeString(..., CREATE_NEW, WRITE)` hoặc `FileChannel.open(..., CREATE_NEW, WRITE)` diễn đạt đúng mục tiêu hơn.

Không nhầm `CREATE_NEW` với tên file “unique” do code tự sinh. Nếu tên dự đoán được hoặc chia sẻ, vẫn cần kiểm tra quyền thư mục, symlink ở các thành phần cha và phối hợp cạnh tranh ghi.

## 6. CREATE: mở nếu có, tạo nếu chưa có

`CREATE` **không yêu cầu file phải mới**. Nếu file chưa tồn tại thì tạo; nếu đã tồn tại thì mở file cũ theo các option còn lại.

Ví dụ muốn bổ sung log:

```java
Files.writeString(log, "event=login\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND);
```

Đây là snippet trong phương thức. Nếu `log` chưa tồn tại thì tạo; nếu đã có thì **append**, không truncate. Vì có `APPEND` nên dữ liệu được viết tới cuối file (với những giới hạn đồng thời đã mô tả ở phần 8).

Ngược lại:

```java
Files.writeString(log, "event=login\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING);
```

Vẫn tạo khi thiếu, nhưng **xóa nội dung cũ khi đã tồn tại** trước khi ghi text mới. Cả hai ví dụ dùng `CREATE`, khác nhau ở `APPEND` và `TRUNCATE_EXISTING`. Vì vậy câu “dùng CREATE để không bị mất dữ liệu” là **sai**.

**`CREATE + CREATE_NEW`:** theo đặc tả, khi cả hai có mặt thì `CREATE` bị bỏ qua, `CREATE_NEW` quyết định. Tuy nhiên không nên viết cả hai nếu không cần, vì mục đích khó đọc hơn.

## 7. TRUNCATE_EXISTING: cắt file xuống 0 byte khi mở ghi

`TRUNCATE_EXISTING` yêu cầu một file có sẵn được mở với `WRITE` thì **chiều dài của file bị đặt về 0 byte**, rồi các thao tác ghi tiếp theo bắt đầu từ file rỗng.

Ví dụ file đang chứa `"abcdef"`:

```java
Files.writeString(file, "xy", StandardCharsets.UTF_8,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING);
// Nội dung mới: "xy"
```

Đây là snippet trong phương thức; `file` **phải đã tồn tại** vì không có `CREATE`. Nếu file không tồn tại, bạn có thể gặp `NoSuchFileException` thay vì được tạo mới.

Nếu bỏ `TRUNCATE_EXISTING`:

```java
Files.writeString(file, "xy", StandardCharsets.UTF_8,
        StandardOpenOption.WRITE);
// Khi đang có "abcdef", kết quả có thể là "xycdef".
```

Với file thông thường và vị trí ghi ban đầu bằng 0, chỉ hai byte đầu được thay; phần byte cũ phía sau **không tự bị cắt**. Đây là lỗi rất nguy hiểm khi ứng dụng muốn “ghi đè toàn bộ cấu hình” nhưng lại dùng `WRITE` đơn thuần.

### 7.1. TRUNCATE_EXISTING không được dùng để bảo đảm rollback

Nếu thao tác mở đã truncate file, nhưng quá trình encode/ghi sau đó ném `IOException`, **nội dung cũ có thể đã mất**, và file có thể rỗng hoặc mới ghi được một phần. Javadoc không cam kết ghi trọn file như một giao dịch. Muốn tránh làm lộ file cấu hình dở dang, hãy thiết kế ghi file tạm rồi thay thế file đích bằng cơ chế phù hợp thay vì ghi truncate trực tiếp vào dữ liệu quan trọng.

### 7.2. TRUNCATE_EXISTING bị bỏ qua nếu chỉ mở READ

Theo `StandardOpenOption`, tùy chọn `TRUNCATE_EXISTING` **không có tác dụng** nếu file chỉ được mở để đọc. Nhưng điều này **không** có nghĩa mọi API đọc đều cho phép truyền `TRUNCATE_EXISTING`: còn phải xét các tổ hợp option được từng phương thức hỗ trợ.

## 8. APPEND: ghi thêm ở cuối file chứ không ghép nội dung trong bộ nhớ

### 8.1. Trường hợp sử dụng

`APPEND` phù hợp với log tuần tự, báo cáo tăng dần hoặc một file text mà nghiệp vụ muốn **giữ mọi nội dung trước**.

```java
try (var writer = Files.newBufferedWriter(log,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND)) {
    writer.write("event=created");
    writer.newLine();
}
```

Snippet trong phương thức, `log` là Path, xử lý IOException. Writer được mở để ghi và trỏ hoạt động write về phía cuối file. Khi gọi `writer.newLine()`, mã thêm **ký tự xuống dòng theo nền tảng**. Nếu định dạng cần newline `\n` nhất quán trên Windows/Linux, hãy ghi `"\n"` tường minh theo schema.

### 8.2. APPEND có tự tạo file không?

Đừng đồng nhất `APPEND` với `CREATE`. Với API `Files.writeString` trong bài, **chủ động kết hợp `CREATE + WRITE + APPEND`** khi muốn tự tạo file nếu chưa có. Nếu chỉ mở để append mà file không có và không yêu cầu tạo, có thể nhận `NoSuchFileException`.

### 8.3. APPEND không phải giao dịch nguyên tử cho cả bản ghi

Theo Javadoc, việc chuyển vị trí ghi về EOF và ghi bytes có được thực hiện như một thao tác nguyên tử hay không **phụ thuộc file system**. Nếu hai tiến trình hoặc nhiều thread cùng ghi, có thể xuất hiện thứ tự không như mong đợi hoặc việc đan xen nội dung, đặc biệt khi một dòng log được chia thành nhiều thao tác write.

Không giả định:

- Một lần `Files.writeString` là một transaction đối với mọi provider/OS.
- Một câu `writer.write(...)` và câu `writer.newLine()` luôn tạo một bản ghi liền khối trong môi trường nhiều writers.
- `APPEND` thay thế hoàn toàn lock, queue hoặc hệ thống log chuyên dụng.
- `APPEND + SYNC` làm cho thao tác append đồng thời trở thành atomic ở mức logic.

Với logging ứng dụng, thường dùng một logging framework có chính sách thread safety, rotation và flush rõ ràng thay vì để nhiều tiến trình tự append vào một file chung không phối hợp.

### 8.4. Không kết hợp APPEND với TRUNCATE_EXISTING hoặc READ

Với các API mở channel theo hợp đồng Java NIO, `APPEND` **không được dùng cùng `READ` hoặc `TRUNCATE_EXISTING`**. Chúng có ý định mâu thuẫn: “mỗi write ở cuối” so với “cắt về 0” hoặc mở để đọc. Đừng dựa vào cách provider “bỏ qua một option” để khiến tổ hợp trái nghĩa hoạt động.

Nếu muốn thay thế file, chọn `TRUNCATE_EXISTING + WRITE`; nếu muốn giữ nội dung cũ và bổ sung, chọn `APPEND + WRITE`.

## 9. SYNC, DSYNC và ghi bền vững: định nghĩa đúng, không hứa quá mức

Hai open option này thường bị hiểu nhầm là đồng nghĩa với “đã an toàn tuyệt đối khi mất điện”:

- `SYNC`: yêu cầu **mỗi cập nhật nội dung hoặc metadata** của file được ghi đồng bộ tới thiết bị lưu trữ nền theo hợp đồng.
- `DSYNC`: yêu cầu **mỗi cập nhật nội dung** của file được ghi đồng bộ, phạm vi hẹp hơn metadata.
- `FileChannel.force(true)`: yêu cầu đẩy cập nhật **nội dung và metadata** tới thiết bị.
- `FileChannel.force(false)`: chỉ yêu cầu nội dung, không bắt buộc mọi metadata.

Các yêu cầu đồng bộ **không** đồng nghĩa với:

1. Ghi cả một file lớn một cách **nguyên tử** (all-or-nothing). File có thể thay đổi nhiều lần.
2. Có thể **rollback** khi xảy ra lỗi sau lần truncate đầu tiên.
3. Đảm bảo tất cả lần ghi đồng thời được **sắp thứ tự** và không giao nhau.
4. Đảm bảo một thao tác **rename** đã bền vững sau crash chỉ vì dữ liệu file được sync; metadata của **thư mục chứa directory entry** là chủ đề riêng, phụ thuộc OS/file system.
5. Bảo đảm tuyệt đối trước mọi hỏng hóc phần cứng, bộ nhớ đệm thiết bị, remote filesystem, network hoặc lỗi OS.
6. Thay thế transaction DB, journaling, backup và kiểm tra tính toàn vẹn nghiệp vụ.

### 9.1. Khi dùng SYNC và DSYNC

```java
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    ByteBuffer bytes = StandardCharsets.UTF_8.encode("important");
    while (bytes.hasRemaining()) {
        channel.write(bytes);
    }
}
```

Đây là snippet Java 17+ trong phương thức, có import `FileChannel`, `ByteBuffer` và xử lý `IOException`. `SYNC` được truyền ngay khi mở channel. Có thể dùng `DSYNC` thay `SYNC` nếu yêu cầu chỉ tập trung vào cập nhật nội dung theo hợp đồng. Một số provider/file system có thể không hỗ trợ option; lúc đó cần xử lý lỗi hoặc thay đổi thiết kế, **không âm thầm bỏ SYNC** trong hệ thống có yêu cầu durability.

### 9.2. FileChannel.force để đồng bộ theo mốc

Nếu đang ghi nhiều đợt và không cần yêu cầu đồng bộ ở **mỗi** lần write, một phương án là:

```java
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    ByteBuffer data = StandardCharsets.UTF_8.encode("payload");
    while (data.hasRemaining()) {
        channel.write(data);
    }
    channel.force(true);
}
```

Đây là snippet minh họa. `force(true)` được gọi sau khi tất cả byte đã được chuyển qua channel. Điều này có thể giảm số lần đồng bộ so với mở channel bằng `SYNC` trong một luồng ghi nhiều lần, nhưng phải đánh giá yêu cầu mất dữ liệu tối đa khi crash **giữa các lần force**.

Theo Javadoc `FileChannel.force`, bảo đảm mạnh khi file nằm trên **thiết bị lưu trữ cục bộ**; với file không nằm trên local device, API không đưa ra bảo đảm tương tự. Phạm vi đồng bộ được bảo đảm cho những thay đổi thực hiện qua **các phương thức của chính FileChannel**. Nếu còn dữ liệu trong `BufferedWriter` hay mapped buffer thì phải flush/force theo đúng cơ chế tương ứng. `MappedByteBuffer.force()` phục vụ thay đổi được thực hiện qua mapped buffer.

### 9.3. Chi phí đồng bộ

`SYNC/DSYNC` có thể làm giảm throughput do chờ I/O lưu trữ. Với log tốc độ cao hoặc batch lớn, nên benchmark yêu cầu thực tế: đồng bộ từng record hay đồng bộ theo lô, mức mất dữ liệu chấp nhận được, độ trễ tối đa và khả năng khôi phục. Không bật SYNC mặc định ở mọi file để “an toàn hơn” mà không hiểu chi phí và mục tiêu.

## 10. Chương trình Java 17+ đầy đủ: bốn cách mở và file có SYNC

Tạo file **`FilesOpenOptionsDemo.java`**. Chương trình chỉ tạo file trong **thư mục tạm ngẫu nhiên**, in ra kết quả có thể tái hiện, sau đó xóa file/thư mục của chính nó. Không ghi vào file dự án.

```java
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FilesOpenOptionsDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("files-open-options-");
        Path text = directory.resolve("events.txt");
        Path durable = directory.resolve("durable.dat");

        try {
            Files.writeString(text, "first\n", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            System.out.println("created = " + Files.exists(text));

            try {
                Files.writeString(text, "ignored", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("create again = FileAlreadyExistsException");
            }

            Files.writeString(text, "second\n", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.WRITE,
                    StandardOpenOption.APPEND);
            System.out.println("appended = " +
                    Files.readString(text, StandardCharsets.UTF_8)
                            .replace("\n", "|"));

            Files.writeString(text, "short", StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE, StandardOpenOption.TRUNCATE_EXISTING);
            System.out.println("truncated = " +
                    Files.readString(text, StandardCharsets.UTF_8));

            Files.writeString(text, "+", StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE);
            System.out.println("overwrite without truncate = " +
                    Files.readString(text, StandardCharsets.UTF_8));

            try (FileChannel channel = FileChannel.open(durable,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.SYNC)) {
                ByteBuffer data = StandardCharsets.UTF_8.encode("SYNC");
                while (data.hasRemaining()) {
                    channel.write(data);
                }
                channel.force(true);
            }
            System.out.println("synced bytes = " + Files.size(durable));
            System.out.println("synced content = " +
                    Files.readString(durable, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(durable);
            Files.deleteIfExists(text);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 FilesOpenOptionsDemo.java
java FilesOpenOptionsDemo
```

**Stdout chính xác trên filesystem mặc định hỗ trợ `SYNC`, như môi trường JDK 24 đã kiểm thử:**

```text
created = true
create again = FileAlreadyExistsException
appended = first|second|
truncated = short
overwrite without truncate = +hort
synced bytes = 4
synced content = SYNC
```

Từng dòng có ý nghĩa:

1. `created = true`: mở với `CREATE_NEW + WRITE` tạo file `events.txt` mới.
2. `create again = FileAlreadyExistsException`: thử tạo lại đúng tên từ chối ghi đè; nội dung `"ignored"` không được ghi.
3. `appended = first|second|`: dữ liệu `"second\n"` được thêm ở cuối `"first\n"`, không thay bản ghi đầu. Dấu `|` chỉ là cách thay newline khi hiển thị để stdout cố định.
4. `truncated = short`: mở `WRITE + TRUNCATE_EXISTING` cắt file trước rồi ghi đúng `"short"`.
5. `overwrite without truncate = +hort`: ghi một byte `"+"` từ vị trí đầu mà **không truncate**; bốn byte `"hort"` cũ vẫn còn.
6. `synced bytes = 4`: file riêng `durable.dat` được mở với `SYNC` và nhận byte UTF-8 của `"SYNC"`.
7. `synced content = SYNC`: đọc file đồng bộ đã đóng đúng nội dung. Kết quả này **xác nhận behavior trong demo**, không phải một phép kiểm tra thực nghiệm bảo đảm sống sót qua mọi kiểu crash.

Lưu ý:

- `CREATE_NEW` có thể thất bại bằng ngoại lệ ghi file đã tồn tại; chương trình bắt đúng lỗi đó để demo tiếp tục. Trong ứng dụng cần xử lý các `IOException` khác theo chính sách.
- `FileChannel.write(ByteBuffer)` có thể chỉ ghi **một phần** số byte trong buffer; vì vậy code lặp `while (data.hasRemaining())` thay vì tin rằng một lần `write` sẽ ghi hết mọi byte.
- `try-with-resources` đóng channel. `finally` xóa các file do demo tạo; nếu không có quyền ghi thư mục temp hoặc provider không hỗ trợ SYNC, chương trình có thể ném lỗi thay vì in đủ các dòng.
- `channel.force(true)` trong kịch bản đã dùng `SYNC` nhằm trình bày cả hai API; thực tế có thể không cần gọi riêng nếu chính sách đã yêu cầu sync mỗi update.

## 11. Công thức lựa chọn option theo từng nhu cầu

### 11.1. Ghi file chỉ một lần, không được ghi đè

```java
Files.writeString(target, content, StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
```

Dùng cho file export mới, snapshot có tên cố định nhưng không được overwrite hoặc checkpoint mới. Nếu file đã có, **fail có chủ đích** và để tầng nghiệp vụ quyết định đổi tên hay dừng; không chuyển thành TRUNCATE một cách vô điều kiện.

### 11.2. Tạo nếu thiếu, ghi thêm vào cuối

```java
Files.writeString(target, "new event\n", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND);
```

Dùng khi muốn duy trì lịch sử text/log. Đừng quên newline theo schema. Không giả định append nhiều writers là atomic.

### 11.3. Thay toàn bộ nội dung file đã tồn tại

```java
Files.writeString(target, content, StandardCharsets.UTF_8,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING);
```

Chỉ phù hợp nếu file **phải tồn tại** và nghiệp vụ **chấp nhận nội dung cũ bị xóa khi mở**. Nếu cần tạo khi thiếu, bổ sung `CREATE`. Với file cấu hình quan trọng, phương pháp này có thể để lại file rỗng/dở dang nếu write lỗi; cân nhắc ghi file tạm và thay thế có kiểm soát.

### 11.4. Ghi vài byte vào đầu mà giữ phần dư cũ

```java
Files.write(target, new byte[] {65}, StandardOpenOption.WRITE);
```

Khi file cũ chứa bytes `"ABCDE"`, thao tác này thường cho `"A" + "BCDE"` (vẫn là “ABCDE”). Nếu thay byte 0 bằng `'X'`, kết quả “XBCDE”. Đây là **ghi đè một phần từ vị trí ban đầu**, không phải append hay truncate. Chỉ dùng nếu thực sự có hợp đồng binary về vị trí byte; không dùng để “thay nội dung toàn file”.

### 11.5. Yêu cầu đồng bộ từng cập nhật

```java
try (FileChannel channel = FileChannel.open(target,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    // Ghi ByteBuffer qua channel, kiểm tra write/close/errors.
}
```

Snippet minh họa về cấu hình channel; không có payload nên không phải chương trình hoàn chỉnh. Nếu chỉ cần dữ liệu đồng bộ theo mốc, dùng `FileChannel.force(...)` sau những lô ghi đã hoàn tất. Chọn theo yêu cầu crash recovery thật, không phải chọn bừa dựa vào tên option.

## 12. Ghi thay thế an toàn hơn: file tạm, đồng bộ và move

Một cách thiết kế thường phù hợp hơn **truncate trực tiếp file quan trọng**:

1. Tạo file tạm **trong cùng thư mục/file store mục tiêu** và không bị trùng tên; `Files.createTempFile(parent, prefix, suffix)` tạo file mới.
2. Ghi đầy đủ nội dung vào file tạm. Kiểm tra lỗi encode, write, flush/close, dung lượng và quyền.
3. Nếu yêu cầu durability, đồng bộ dữ liệu file tạm qua channel/force theo chính sách.
4. Dùng `Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE, ...)` **nếu provider hỗ trợ atomic move và semantics đích phù hợp**. Nếu không hỗ trợ, API có thể ném `AtomicMoveNotSupportedException`; ứng dụng phải chọn chính sách fallback, thay vì giả định mọi nơi đều atomic.
5. Với yêu cầu **crash consistency** nghiêm ngặt, xem xét việc đồng bộ cả metadata của thư mục và hành vi rename/file store theo nền tảng, cũng như backup/rollback. Java API chuẩn không cung cấp một công thức bảo đảm tuyệt đối cho mọi provider.
6. Nếu có lỗi và file tạm còn tồn tại, dọn file tạm khi an toàn; không xóa dữ liệu cũ chưa được xác nhận thay thế.

**Chú ý:** `ATOMIC_MOVE` là `StandardCopyOption` của **Files.move**, **không phải** `StandardOpenOption` truyền vào `Files.writeString`. Ngay cả khi move được hỗ trợ, quy tắc thay một target đã tồn tại khi dùng atomic move cần xem hợp đồng provider; không mặc định `REPLACE_EXISTING` luôn được áp dụng giống trên mọi hệ thống.

Giải pháp này giảm khả năng người đọc thấy **file đích bị truncate dở dang**, nhưng chưa đủ để thiết kế một transactional storage system trước mọi crash, volume hoặc yêu cầu pháp lý. Đừng gọi nó là “100% atomic và durable” nếu chưa kiểm tra điều kiện của hạ tầng đích.

## 13. Concurrent writers, race và dữ liệu nghiệp vụ

### 13.1. CREATE_NEW ngăn trùng tên, không ngăn mọi cạnh tranh

Hai tiến trình cùng cố `CREATE_NEW` trên một tên có thể nhận **một thành công, một thất bại** theo hợp đồng atomic create; điều đó hữu ích cho single-writer reservation. Nhưng sau khi tạo, còn có thể có thay đổi từ process khác nếu quyền cho phép. Nếu dùng việc tạo file như lock, phải thiết kế **vòng đời, dọn lock sau crash, quyền sở hữu và race**; không coi CREATE_NEW là distributed lock hoàn chỉnh.

### 13.2. APPEND và bản ghi nhiều dòng

Một log record có thể được chia thành nhiều lời gọi `write` do buffering và giới hạn buffer. Trong môi trường nhiều writers, dữ liệu có thể bị chèn xen hoặc đổi thứ tự. Sử dụng logger có cơ chế tuần tự hóa, queue, file locks khi phù hợp hoặc một nơi lưu sự kiện chuyên dụng nếu cần guarantee ở mức record.

### 13.3. TRUNCATE và consumer đọc đồng thời

Một consumer có thể mở file ngay sau khi writer truncate nhưng trước khi ghi xong; khi đó consumer quan sát file rỗng hoặc mới một phần. Đây là lý do file config/report được sử dụng đồng thời thường không nên được cập nhật bằng **truncate in place** khi cần reader luôn thấy một phiên bản hoàn chỉnh.

### 13.4. Đừng dùng Files.exists làm “quyết định cuối cùng”

`Files.exists(path)`/`Files.notExists(path)` chỉ trả trạng thái tại thời điểm kiểm tra, có thể stale ngay lập tức. Với tạo mới không được ghi đè, giao việc bảo vệ vào `CREATE_NEW`. Với ghi đè, cần chính sách explicit và quyền truy cập phù hợp.

## 14. Lỗi và ngoại lệ cần xử lý

Những trường hợp cần dự tính:

| Tình huống | Biểu hiện có thể gặp | Đối sách |
| --- | --- | --- |
| `CREATE_NEW` khi file đã tồn tại | `FileAlreadyExistsException` (trường hợp cụ thể) | Đừng ghi đè; báo tên trùng hoặc đổi tên theo policy |
| Ghi file chưa có mà không `CREATE` | `NoSuchFileException` | Nếu được phép tạo, thêm `CREATE` hoặc `CREATE_NEW` |
| Thư mục cha chưa tồn tại | `NoSuchFileException`/`IOException` | Tạo parent có chủ đích với `Files.createDirectories` và kiểm tra quyền |
| Không có quyền ghi | `AccessDeniedException` hoặc `IOException` | Kiểm tra permission/ACL, không suppress |
| Tổ hợp option mâu thuẫn | `IllegalArgumentException` hoặc lỗi tương ứng | Sửa tổ hợp, tránh APPEND + TRUNCATE |
| Provider không hỗ trợ option | `UnsupportedOperationException` hoặc `IOException` | Chọn provider/thiết kế phù hợp |
| Hết dung lượng/lỗi I/O giữa chừng | `IOException` | Có thể file đã truncate/ghi một phần; cần recovery |
| Encoding sai hoặc dữ liệu không thể encode | Lỗi mã hóa/ghi hoặc thay thế tùy API | Chọn UTF-8, kiểm tra charset/encoder và hợp đồng dữ liệu |
| SYNC/DSYNC chậm hoặc không hỗ trợ | Latency cao hoặc không mở được | Benchmark, chọn durability policy, kiểm tra platform |
| Reader cần file nguyên vẹn khi writer cập nhật | Quan sát file dở dang | Thiết kế file tạm + publish/move phù hợp |

`FileAlreadyExistsException` và `NoSuchFileException` là các nhánh cụ thể của `IOException`. Hãy bắt lỗi cụ thể nếu nghiệp vụ có thể xử lý; những lỗi I/O khác nên được truyền lên/ghi nhận với đủ ngữ cảnh để tránh giấu mất nguyên nhân. Không khẳng định mọi provider luôn trả đúng cùng một subclass; tài liệu có những ngoại lệ được nêu là **optional specific exception**.

**Không suy rằng exception nghĩa là “không có byte nào được thay đổi”.** Đối với ghi file đã tồn tại, lỗi có thể xảy ra **sau** khi đã truncate hoặc sau khi ghi một phần. Thiết kế retry cần biết file đang ở trạng thái nào.

## 15. Định dạng text và ký tự xuống dòng khi append

Khi ghi log hoặc file text, các lựa chọn mở file **không tự xử lý charset**. Hãy chỉ định charset phù hợp:

```java
Files.writeString(log, "Chào\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND,
        StandardOpenOption.WRITE);
```

Snippet trong phương thức. Nếu file đã chứa text được encode bằng một charset khác, append UTF-8 có thể làm file chứa **nhiều encoding trộn lẫn**, rất khó đọc đúng. Vì vậy dữ liệu append phải tuân theo **charset và line-ending đã quy định cho toàn file**.

- `Files.writeString` **giữ nguyên** newline đã có trong chuỗi; nó không tự thêm `\n`.
- `BufferedWriter.newLine()` dùng line separator do hệ thống cung cấp.
- `Files.write(path, Iterable<CharSequence>, charset, options...)` ghi từng dòng kèm line separator của nền tảng.
- Nếu định dạng giao thức quy định CRLF hoặc LF, ghi theo giao thức, không tùy tiện dùng mặc định hệ điều hành.

UTF-8 là lựa chọn phổ biến cho file mới, nhưng nếu đang tiếp tục một file do hệ thống khác tạo, phải tuân theo **charset gốc** thay vì tự đổi encoding ở giữa file.

## 16. Các tình huống không nên dùng trực tiếp kiểu ghi này

### 16.1. Database thay vì file config cần transaction

Nếu cập nhật nhiều bản ghi liên quan và cần commit/rollback, các open option không tạo transaction. Cân nhắc database hoặc cơ chế journal/application log đúng nghĩa thay vì tự ghép một loạt `writeString` vào file và gọi đó là giao dịch.

### 16.2. Mỗi yêu cầu HTTP dùng Files.writeString trực tiếp trên cùng log

Với nhiều request song song, tự mở file rồi append từ từng thread có thể tạo bottleneck và race. Hãy dùng logger hoặc pipeline ghi có thứ tự được kiểm soát và policy rotation, backpressure, durability phù hợp.

### 16.3. Ghi cập nhật nhỏ vào file cực lớn

`TRUNCATE_EXISTING` sẽ phá toàn bộ dữ liệu cũ. Nếu chỉ cần cập nhật một record trong file nhị phân có layout rõ, có thể dùng `FileChannel.position(...)`/write theo offset, hoặc thiết kế lưu trữ phù hợp. Không coi `Files.write(..., WRITE)` là “sửa một record” nếu chưa có schema byte/offset.

### 16.4. File lưu trên network share/object storage

Các bảo đảm của `SYNC`, `force` và các phép rename có thể khác thiết bị cục bộ. Javadoc `FileChannel.force` không đưa ra cùng guarantee khi file nằm ngoài local storage. Với object storage, cần API/contract của provider tương ứng, không mặc định NIO.2 trên file system ảo có semantics y hệt local disk.

## 17. Những ngộ nhận và lỗi thường gặp

**1 — “CREATE là tạo mới và báo lỗi nếu đã tồn tại.”** Sai. `CREATE` mở file có sẵn; `CREATE_NEW` mới yêu cầu chưa tồn tại.

**2 — “CREATE_NEW cũng ghi đè file nếu tôi đã xóa file bằng Files.exists trước.”** Sai về chủ ý API; nó từ chối tên đã tồn tại tại lúc mở. Đừng kiểm tra tồn tại rồi chuyển sang write không bảo vệ.

**3 — “WRITE đồng nghĩa ghi đè toàn bộ nội dung.”** Sai. Chỉ cho phép ghi; nếu không truncate, phần byte cũ phía sau nội dung mới có thể còn.

**4 — “Files.writeString không option sẽ append.”** Sai. Mặc định thường là `CREATE + TRUNCATE_EXISTING + WRITE`.

**5 — “APPEND tự tạo file ở mọi API mà không cần CREATE.”** Không nên giả định. Nếu yêu cầu tạo khi thiếu, truyền `CREATE` tường minh.

**6 — “APPEND là atomic transaction cho một dòng log.”** Sai. Atomicity của thao tác vị trí-đến-EOF và write phụ thuộc file system; nhiều lần write không tự thành một giao dịch.

**7 — “APPEND + TRUNCATE_EXISTING làm vừa xóa cũ vừa ghi ở cuối nên rất tiện.”** Tổ hợp mâu thuẫn; không dùng với các API NIO channel theo hợp đồng.

**8 — “TRUNCATE_EXISTING xảy ra sau khi write thành công.”** Sai. Nó áp dụng lúc mở file để ghi; nếu write lỗi, dữ liệu cũ có thể đã mất.

**9 — “Không cần xử lý IOException vì Files.writeString luôn ghi hết hoặc không ghi gì.”** Sai. I/O có thể dở dang; cần xử lý recovery.

**10 — “SYNC nghĩa là một file write hoàn toàn atomic.”** Sai. Đồng bộ cập nhật tới lưu trữ và atomicity là hai khái niệm khác nhau.

**11 — “DSYNC và SYNC giống hệt nhau.”** Không. SYNC bao gồm metadata; DSYNC tập trung vào content theo hợp đồng.

**12 — “FileChannel.force(true) sau SYNC luôn tăng an toàn.”** Không chắc. Nó có thể dư thừa; quan trọng là dữ liệu đã được viết qua channel và policy durability rõ ràng.

**13 — “Đóng BufferedWriter là đã bảo đảm không bao giờ mất dữ liệu khi mất điện.”** Sai. Close/flush không phải bảo đảm crash durability trên mọi filesystem.

**14 — “SYNC cũng làm metadata của thư mục chứa file mới bền vững ở mọi OS.”** Không được mặc định. Durability của directory entry/rename là vấn đề riêng.

**15 — “Files.createFile rồi Files.writeString mặc định là một thao tác nguyên tử.”** Sai. Đó là **hai thao tác**; lần ghi sau có thể truncate hoặc can thiệp bởi writer khác.

**16 — “Nếu bật -Werror hoặc dùng try-with-resources thì file đã có transaction.”** Không. Compiler flags và TWR không tạo database transaction; TWR chủ yếu quản lý vòng đời/đóng tài nguyên.

**17 — “Nếu Files.exists trả false thì tôi chắc chắn được tạo file mới.”** Không; trạng thái có thể thay đổi. Dùng `CREATE_NEW` để bảo vệ điều kiện ở bước tạo.

**18 — “Ghi vào file nằm trên ZIP/network provider chắc hỗ trợ SYNC.”** Không được mặc định; kiểm tra provider hoặc xử lý unsupported option.

## 18. Checklist code review trước khi ghi file

1. **Mục tiêu:** tạo mới duy nhất, append, overwrite có truncate, cập nhật một phần hay durable write?
2. **Bộ option:** có `CREATE_NEW` thay vì `CREATE` khi tuyệt đối không được ghi đè?
3. **Trạng thái thiếu file:** nếu file chưa có, method có được phép tạo không? Nếu có cần `CREATE`?
4. **Nguy cơ truncate:** có chủ ý xóa toàn bộ nội dung cũ không, hay đang dùng overload mặc định vô tình?
5. **Overwrite một phần:** nếu không truncate, phần byte cũ phía sau có tạo lỗi dữ liệu không?
6. **APPEND:** đã có `WRITE` và, nếu được phép tạo, `CREATE`? Có tránh READ/TRUNCATE tổ hợp không?
7. **Đồng thời:** nhiều writer có thể cùng ghi không? Có cần phối hợp, logger, queue hoặc lock không?
8. **Durability:** cần `SYNC`, `DSYNC` hay `force` theo lô? Đã hiểu giới hạn local/network và metadata chưa?
9. **Atomicity:** có đang nhầm “sync” với “all-or-nothing”? Với file quan trọng, cần temp+move hoặc giải pháp dữ liệu khác?
10. **Encoding:** file text dùng charset nào? Các lần append có cùng encoding và newline convention không?
11. **Error handling:** đã xử lý FileAlreadyExistsException, NoSuchFileException, AccessDeniedException, IOException và unsupported options chưa?
12. **Rollback/retry:** nếu viết một phần rồi lỗi, quy trình xử lý trạng thái file là gì?
13. **Symlink/path input:** đường dẫn có đến từ user input không? Đã kiểm tra root, tên hợp lệ, quyền thư mục và race?
14. **Resource lifecycle:** stream/writer/channel có được đóng bằng try-with-resources không?
15. **Test:** có test file thiếu, file có sẵn, file có nội dung dài hơn payload mới, append nhiều lần và create-new conflict không?
16. **Platform:** hoạt động trên Windows/Linux/macOS, filesystem provider, network share và JDK target của hệ thống thật?
17. **Performance:** nếu SYNC tạo quá nhiều I/O, đã benchmark throughput/latency theo workload chưa?
18. **Audit:** nếu hành động ghi đè dữ liệu quan trọng, có ghi lại lý do, nguồn và kết quả an toàn mà không lộ nội dung nhạy cảm không?

## 19. Câu hỏi tự kiểm tra

**1.** `CREATE` khác `CREATE_NEW` như thế nào? — `CREATE` tạo nếu thiếu nhưng mở file nếu đã có; `CREATE_NEW` yêu cầu chưa tồn tại và thất bại nếu đã có.

**2.** `Files.writeString(path, "x")` khi file đã chứa “hello” làm gì? — Theo mặc định, mở với `CREATE + TRUNCATE_EXISTING + WRITE` và ghi “x”, nên nội dung cũ bị cắt.

**3.** File chứa “hello”, gọi `Files.writeString(file, "X", UTF_8, WRITE)` có thể ra gì? — **“Xello”**; WRITE không tự truncate phần byte dư.

**4.** File chưa tồn tại, chỉ dùng `WRITE + TRUNCATE_EXISTING` có tự tạo không? — Không; thiếu CREATE/CREATE_NEW nên có thể gặp `NoSuchFileException`.

**5.** Muốn append văn bản và tạo file nếu thiếu? — `CREATE + WRITE + APPEND`, kèm charset tường minh.

**6.** APPEND có bảo đảm mọi dòng do hai tiến trình ghi không bị đan xen không? — Không; phải xét provider và số thao tác write, đồng thời có thể cần cơ chế phối hợp.

**7.** Vì sao `Files.notExists(file)` rồi write không an toàn cho yêu cầu “chỉ tạo mới”? — Vì giữa kiểm tra và ghi có race; dùng `CREATE_NEW` để gắn điều kiện vào thao tác mở.

**8.** `TRUNCATE_EXISTING` có xảy ra sau khi ghi xong không? — Không; nó có hiệu lực khi mở file để ghi, có thể làm mất dữ liệu cũ trước khi ghi thành công.

**9.** `SYNC` khác `DSYNC`? — SYNC yêu cầu đồng bộ nội dung **và metadata**; DSYNC yêu cầu nội dung.

**10.** `FileChannel.force(true)` dùng để làm gì? — Yêu cầu đồng bộ cập nhật file đã ghi qua channel, gồm nội dung và metadata trong phạm vi hợp đồng.

**11.** Có nên gọi `force(true)` sau mọi `channel.write` nếu channel đã mở bằng SYNC không? — Có thể dư thừa và tốn I/O; quyết định dựa vào durability policy.

**12.** Nếu ghi qua `BufferedWriter`, nên nghĩ gì trước khi kỳ vọng dữ liệu bền vững? — Dữ liệu có thể đang nằm trong buffer; cần flush/close và cơ chế sync tương ứng với channel/filesystem.

**13.** SYNC có làm một lần ghi file lớn thành giao dịch atomic không? — Không. Atomicity và durability khác nhau.

**14.** Muốn tránh reader thấy file cấu hình dở dang, nên cân nhắc gì? — Ghi file tạm hoàn chỉnh rồi publish/move với tính nguyên tử được kiểm tra, cùng chính sách lỗi/crash.

**15.** `ATOMIC_MOVE` thuộc enum nào? — `StandardCopyOption` dùng với `Files.move`, **không** phải `StandardOpenOption`.

**16.** Nếu `Files.writeString` báo IOException, có chắc file cũ còn nguyên? — Không. Có thể đã truncate hoặc ghi một phần.

**17.** Tại sao code ghi file cần test bằng byte thay vì chỉ nhìn text? — Vì charset, newline và partial overwrite có thể tạo sự khác biệt mà cách hiển thị không phản ánh hết.

**18.** Khi nào nên không dùng SYNC? — Khi yêu cầu độ trễ/throughput và mức mất dữ liệu chấp nhận được phù hợp cơ chế sync theo lô hoặc storage khác; quyết định dựa trên rủi ro và benchmark.

## Tài liệu chính thức còn áp dụng

- [Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): định nghĩa `CREATE`, `CREATE_NEW`, `APPEND`, `TRUNCATE_EXISTING`, `SYNC` và `DSYNC`.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `writeString`, `write`, `newOutputStream`, `newByteChannel`, `newBufferedWriter`, `createFile` và hành vi mặc định.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `open`, `write`, `force(boolean)`, `position` và `truncate`.
- [Java SE 17 — StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): `ATOMIC_MOVE` và `REPLACE_EXISTING` khi di chuyển file.
- [Java SE 17 — Charset/StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): charset rõ ràng khi chuyển văn bản thành byte.
- [Java SE 17 — Filesystem Provider API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html): các chi tiết và tùy chọn có thể khác theo provider.

**Ghi nhớ:** Với NIO.2, **`CREATE_NEW` bảo vệ việc tạo file mới không ghi đè**, **`CREATE` cho phép mở file đã có**, **`APPEND` ghi vào cuối**, **`TRUNCATE_EXISTING` xóa nội dung cũ khi mở để ghi**, còn **`WRITE` chỉ cấp quyền ghi chứ không tự truncate**. **`SYNC/DSYNC` và `FileChannel.force` nói về đồng bộ dữ liệu với lưu trữ, không tạo giao dịch all-or-nothing**. Hãy chọn option theo hợp đồng dữ liệu, ghi rõ charset, phối hợp nhiều writers khi cần và kiểm thử trên file system đích.