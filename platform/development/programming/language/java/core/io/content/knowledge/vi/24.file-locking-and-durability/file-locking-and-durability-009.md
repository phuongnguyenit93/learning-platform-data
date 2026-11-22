# Tính nguyên tử của đổi tên khác độ bền sau sự cố nguồn điện

## 1. Vấn đề: “đổi tên thành công” không đồng nghĩa “đã lưu bền”

Trong Java NIO.2, một ứng dụng thường cập nhật tệp cấu hình hoặc trạng thái bằng mẫu **ghi tệp tạm rồi đổi tên**:

```text
Trước:      config.json = dữ liệu cũ
Chuẩn bị:   .config-123.tmp = dữ liệu mới
Công bố:    đổi tên .config-123.tmp thành config.json
Sau:        ứng dụng khác mở config.json sẽ thấy dữ liệu mới
```

Mẫu này giảm khả năng người đọc nhìn thấy tệp đích **đang được ghi dở**. Nhưng câu hỏi “người đọc có thấy bản cập nhật nguyên vẹn khi hệ thống đang chạy?” khác căn bản với “sau khi máy mất điện và khởi động lại, cập nhật có còn tồn tại?”.

Có ít nhất ba thuộc tính cần phân biệt:

1. **Atomicity của đổi tên (rename atomicity):** đối với thao tác tệp được hỗ trợ, việc di chuyển/đổi tên là một thao tác nguyên tử trong namespace của file system. Người quan sát không thấy trạng thái thay đổi tên *nửa chừng* do chính thao tác đó.
2. **Durability (độ bền):** byte và metadata cần thiết đã được đẩy xuống lưu trữ theo hợp đồng, để có thể khôi phục sau crash hoặc mất nguồn.
3. **Consistency của ứng dụng:** dữ liệu được công bố là một phiên bản hoàn chỉnh, hợp lệ về schema/checksum; các file liên quan nhau tuân theo bất biến. Atomic rename không tự kiểm tra nội dung và không tạo transaction nhiều file.

**Kết luận trung tâm:** `Files.move(source, target, StandardCopyOption.ATOMIC_MOVE)` có thể cung cấp **atomic rename** khi provider hỗ trợ; bản thân nó **không phải một lệnh fsync**, cũng không tự tạo lời hứa rằng phiên bản mới sống sót qua sự cố nguồn điện.

Mục tiêu bài: hiểu `ATOMIC_MOVE` và giới hạn với `REPLACE_EXISTING`, phân biệt `FileChannel.force(...)` với ghi bền thư mục, thiết kế chuỗi “write → sync file → rename → sync directory” theo nền tảng, đọc đúng kết quả demo và tránh các giả định về crash consistency.

## 2. Ba thời điểm phải mô hình hóa riêng

Giả sử `state.dat` đang có nội dung `OLD` và chương trình muốn thay bằng `NEW`.

```text
T0: target = OLD
             │
             ▼
T1: tạo tệp tạm, ghi NEW (có thể còn trong cache)
             │
             ▼
T2: đồng bộ dữ liệu tệp tạm (nếu yêu cầu độ bền)
             │
             ▼
T3: atomic rename tệp tạm → target
             │
             ▼
T4: đồng bộ thư mục/metadata namespace (nếu nền tảng hỗ trợ)
             │
             ▼
T5: hoàn thành chính sách cập nhật bền của ứng dụng
```

Câu hỏi ở **T3**: khi rename hoàn tất, thao tác quan sát đường dẫn target được công bố như thế nào?  
Câu hỏi ở **T5**: nếu xảy ra crash ngay sau khi API trả về, nền tảng có cung cấp đủ bảo đảm để khôi phục tên tệp trỏ tới dữ liệu hợp lệ không?

Chúng là hai bài toán khác nhau. Việc thay tên có thể được nhìn thấy ngay trong namespace đang chạy, trong khi thay đổi của entry thư mục hoặc byte file vẫn cần được đồng bộ để có độ bền sau crash. Ngược lại, việc flush dữ liệu file tạm **trước** rename không tự đảm bảo tên cuối đã được lưu bền.

### 2.1. Phân biệt sự cố ứng dụng và sự cố mất nguồn

- **Process crash**: tiến trình Java dừng, nhưng OS vẫn chạy. Dữ liệu đang ở page cache có thể tiếp tục được OS ghi xuống đĩa.
- **OS crash/kernel panic**: hệ điều hành dừng bất thường; page cache chưa được ghi có thể mất.
- **Power loss**: mất điện đột ngột; ngoài page cache còn cần xét bộ đệm thiết bị, firmware, controller, hệ thống tệp, journal và các cam kết thực tế của ổ lưu trữ.

Đừng dùng thử nghiệm `kill -9` một tiến trình rồi đọc lại file làm bằng chứng rằng chương trình đã an toàn trước *mất điện*. Đó là kiểu lỗi khác với shutdown đột ngột của OS hoặc nguồn điện.

## 3. `Files.move` và `StandardCopyOption.ATOMIC_MOVE`

Java NIO.2 cung cấp:

```java
Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
```

Trong đó `source` và `target` là `Path` đã xác định; ví dụ minh họa phải nằm trong method xử lý `IOException` và import `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.file.StandardCopyOption`.

Theo Java SE 21:

- `ATOMIC_MOVE` yêu cầu move diễn ra như **một thao tác nguyên tử của file system**.
- Nếu không hỗ trợ thao tác nguyên tử cho cặp source/target, API ném `AtomicMoveNotSupportedException`; một nguyên nhân điển hình là phải di chuyển giữa các `FileStore` khác nhau hoặc provider khác.
- Khi có `ATOMIC_MOVE`, **mọi option khác đều bị bỏ qua**. Không được suy ra rằng `ATOMIC_MOVE` cộng `REPLACE_EXISTING` sẽ luôn thay thế tệp đích đã tồn tại.
- **Nếu target đã tồn tại**, việc atomic move có thay thế target hay ném `IOException` là **implementation-specific**. Hãy xác minh contract/provider/môi trường chạy nếu muốn dùng để cập nhật đè một tệp hiện hữu.
- Khi không chỉ định `ATOMIC_MOVE`, `Files.move` không cam kết luôn có tính nguyên tử; nếu move cần copy/delete, trạng thái khi lỗi có thể phức tạp và tệp đích có thể không hoàn chỉnh.

**Quan trọng:** `Files.move` trả về thành công không đồng nghĩa Java đã gọi/hoàn thành fsync cho file và các directory entry liên quan. `ATOMIC_MOVE` là yêu cầu *atomicity*, không phải option *durability*.

### 3.1. `REPLACE_EXISTING` không thay thế `ATOMIC_MOVE`

```java
Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
```

`REPLACE_EXISTING` chỉ yêu cầu thay thế target hiện hữu trong phạm vi contract và ngoại lệ tương ứng. Nó **không tự cam kết** atomic rename. Với hai option:

```java
Files.move(source, target,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
```

`ATOMIC_MOVE` khiến các option còn lại bị bỏ qua theo API. Không mô tả câu lệnh này như “bảo đảm overwrite nguyên tử trên mọi OS”. Khi target đã tồn tại, chính sách replace và các giới hạn liên quan phải được xác nhận cho file system cụ thể.

### 3.2. Vì sao nên đặt tệp tạm cạnh đích?

`Files.createTempFile(target.getParent(), ...)` tạo tệp tạm trong **cùng thư mục** chứa đích. Điều đó giúp tránh tình huống tệp tạm mặc định nằm ở ổ đĩa khác, khiến atomic rename không thực hiện được.

Tuy nhiên, “cùng thư mục” **không phải bằng chứng tuyệt đối** provider hỗ trợ `ATOMIC_MOVE`. Quyền truy cập, loại file system, mount, trạng thái target và hành vi provider vẫn quyết định thành công. Dùng đúng API và xử lý `AtomicMoveNotSupportedException`.

## 4. Atomicity bảo đảm điều gì cho người đọc đang chạy?

Giả sử rename là nguyên tử và file system thực hiện thao tác thành công. Người đọc mở đường dẫn target **trước** rename có thể đã giữ handle tới phiên bản cũ, trong khi người đọc mở **sau** rename có thể lấy phiên bản mới, tùy semantics của OS/provider và ứng dụng.

Điểm được bảo vệ là **bước thay đổi tên** không bị triển khai thành một chuỗi thao tác có trạng thái rename một nửa. Nhưng:

- Nó không bảo đảm tất cả người đọc đang giữ file handle cũ đều lập tức nhìn nội dung mới.
- Nó không ngăn chương trình khác sửa trực tiếp file đích hoặc file tạm cùng lúc.
- Nó không chuyển những lần ghi vào **cùng một file đang mở** thành nguyên tử; hãy ghi đủ dữ liệu vào file tạm trước khi publish.
- Nó không bảo đảm tính nguyên tử nếu một bản cập nhật bao gồm nhiều file hoặc nhiều đường dẫn riêng lẻ.
- Nó không làm dữ liệu hợp lệ về JSON, checksum hoặc quy tắc nghiệp vụ.
- Nó không tự nói gì về tính bền vững sau mất điện.

**So sánh:** ghi đè trực tiếp file đích `TRUNCATE_EXISTING` rồi viết từng chunk có thể để người đọc gặp tệp rỗng/thiếu byte. Ghi đầy đủ vào file tạm, sau đó dùng atomic move được hỗ trợ, giúp tránh vấn đề *công bố nội dung dang dở* đối với các quan sát đường dẫn trong điều kiện phù hợp.

## 5. `FileChannel.force(boolean)` và độ bền nội dung tệp

Java cung cấp cách yêu cầu flush dữ liệu tệp xuống thiết bị:

```java
try (FileChannel channel = FileChannel.open(
        temp,
        StandardOpenOption.WRITE)) {

    // Sau khi ghi byte bằng channel...
    channel.force(true);
}
```

Đây là đoạn minh họa với `temp` là `Path` hợp lệ; import `FileChannel` và `StandardOpenOption`, method xử lý `IOException`. Giá trị `true` yêu cầu flush **nội dung cùng metadata** liên quan của tệp trong phạm vi contract; `false` chỉ yêu cầu nội dung, không nhất thiết metadata.

Các điều kiện và giới hạn quan trọng trong Java SE:

- Khi file nằm trên **thiết bị lưu trữ cục bộ**, `force(...)` có bảo đảm về những thay đổi liên quan đến file theo hợp đồng `FileChannel`.
- Với file trên thiết bị **không cục bộ** như một số network filesystem, Java **không đưa ra cùng bảo đảm**.
- Java `FileChannel.force` chỉ bảo đảm cho những thay đổi đã được thực hiện qua phương thức của channel và các đường dẫn liên quan mà API quy định. Không mặc định nó flush mọi thứ do code khác/provider khác vừa viết.
- Nếu tệp được sửa qua `MappedByteBuffer`, `channel.force(...)` có thể **không** flush đầy đủ thay đổi qua mapping; cần `mapped.force()` theo contract của buffer.
- `force(true)` có thể cần thao tác I/O tốn chi phí. Dùng có chủ đích ở điểm commit, không phải mặc định sau mỗi byte nếu không cần.
- Thành công của `force(true)` **đối với tệp** chưa đồng nghĩa entry tên `target` sau thao tác rename đã bền trên ổ lưu trữ.

### 5.1. Lỗi phổ biến: gọi `force` sau khi rename nhưng không phân biệt phạm vi

Giả sử ghi đầy đủ vào `temp`, gọi `channel.force(true)` rồi rename. Tại thời điểm `force`, Java yêu cầu đồng bộ **tệp temp**; **rename xảy ra sau đó** làm thay đổi directory entry. Vì thế bước `force` trước rename không thể “đồng bộ trước” một namespace change vẫn chưa xảy ra.

Ngay cả khi mở lại `target` và `force(true)`, hợp đồng của `FileChannel.force` nói về thay đổi của **file do channel quản lý**; nó **không cung cấp API đồng bộ portable cho directory entry đã đổi tên**. Không coi `FileChannel.force(true)` trên file cuối là đủ để bảo đảm parent directory đã được lưu bền.

## 6. Parent directory cũng chứa metadata cần được ghi bền

Trong hệ thống tệp, sự liên kết giữa **tên** `state.dat` và đối tượng file nằm trong metadata của thư mục. Khi rename, directory entry thay đổi.

Trên Linux/POSIX, manual `fsync(2)` nói rõ: gọi `fsync` trên **file** không nhất thiết đồng bộ entry của **directory chứa file**; để có bảo đảm ghi entry tương ứng, cần `fsync` trên file descriptor của thư mục.

Vì vậy một quy trình cập nhật mạnh trên hệ thống có hỗ trợ phù hợp thường có dạng:

```text
1. Tạo file tạm trong cùng directory với target.
2. Ghi toàn bộ dữ liệu mới vào file tạm.
3. fsync/force tệp tạm để ghi bền nội dung (+ metadata cần thiết).
4. Atomic rename file tạm thành tên target.
5. fsync thư mục cha để ghi bền thay đổi tên trong namespace.
6. Chỉ sau đó mới xác nhận cập nhật bền theo chính sách của nền tảng.
```

Đây là **quy trình mức hệ điều hành**, không phải lời hứa rằng Java `Files.move` đã tự làm cả bước 3 và bước 5. Nếu rename đi qua **hai thư mục khác nhau**, chính sách durability có thể cần sync cả hai thư mục nguồn và đích. Ví dụ tạm cùng thư mục làm quy trình dễ kiểm soát hơn.

### 6.1. Có thể mở directory bằng `FileChannel` rồi `force(true)` cho mọi OS không?

**Không có bảo đảm portable như vậy từ Java SE 17/21.** Việc mở directory như một `FileChannel` phụ thuộc OS, provider và quyền. `FileChannel.force` cũng không phải một API Java được định nghĩa chung để sync mọi thay đổi directory entry do `Files.move` thực hiện.

Ví dụ bạn có thể gặp trong mã riêng cho Linux:

```java
// Minh họa tùy nền tảng; không phải giải pháp Java portable.
try (FileChannel dir = FileChannel.open(
        directory, StandardOpenOption.READ)) {
    dir.force(true);
}
```

Đoạn trên **không** được dùng để tuyên bố “bảo đảm đồng bộ rename trên Windows/macOS/Linux với Java NIO.2”. Một hệ thống có yêu cầu mất điện nghiêm ngặt nên dùng adapter nền tảng/OS đã kiểm chứng cho thao tác fsync directory, hoặc giao thức lưu trữ/engine cung cấp hợp đồng durability thích hợp; đồng thời kiểm thử trên thiết bị, file system và cấu hình triển khai thực tế.

### 6.2. Journaled filesystem cũng không miễn trừ bài toán

Một journal có thể giúp phục hồi metadata sau crash, nhưng chính sách journaling khác nhau: thứ tự data/metadata, chế độ mount, flush cache thiết bị, barrier, snapshot, network server và crash-recovery semantics có thể khác nhau.

Không thể suy diễn “hệ thống tệp có journaling” ⇒ mọi `Files.move(ATOMIC_MOVE)` đã bền sau mất điện. Khi thiết kế dữ liệu quan trọng, cần đọc contract của platform/file system, kể cả khả năng thiết bị báo flush thành công mà không thực sự lưu bền như kỳ vọng.

## 7. Ví dụ Java 17+ chạy được: ghi tệp tạm, force, yêu cầu rename nguyên tử

Ví dụ này chứng minh các thao tác Java NIO được hỗ trợ và nêu **ranh giới bảo đảm**. Để tránh phụ thuộc vào hành vi replace target đã tồn tại (implementation-specific), chương trình tạo **đường dẫn target chưa có** trong một thư mục tạm riêng.

**Tệp:** `AtomicRenameDemo.java`

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;

public class AtomicRenameDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("atomic-rename-");
        Path target = directory.resolve("state.txt");
        Path staging = null;

        try {
            staging = Files.createTempFile(directory, ".state-", ".tmp");

            byte[] payload = "READY".getBytes(StandardCharsets.UTF_8);
            try (FileChannel channel = FileChannel.open(
                    staging, StandardOpenOption.WRITE)) {

                ByteBuffer buffer = ByteBuffer.wrap(payload);
                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }

                channel.force(true); // Flush nội dung và metadata tệp staging.
            }

            System.out.println("before move exists: "
                    + Files.exists(target));

            try {
                Files.move(staging, target,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException ex) {
                System.out.println("atomic move: unsupported");
                return; // Không âm thầm thay bằng move thường.
            }

            System.out.println("after move: "
                    + Files.readString(target, StandardCharsets.UTF_8));
            System.out.println("staging exists: "
                    + Files.exists(staging));

            // Đây mới là demo atomic move + force(file).
            // Java SE không bảo đảm parent-directory fsync portable.
        } finally {
            // Chỉ dọn những file do demo tạo.
            if (staging != null) {
                Files.deleteIfExists(staging);
            }
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp nguồn:

```bash
javac AtomicRenameDemo.java
java AtomicRenameDemo
```

**Stdout dự kiến khi filesystem hỗ trợ `ATOMIC_MOVE`:**

```text
before move exists: false
after move: READY
staging exists: false
```

**Nếu provider không hỗ trợ atomic move**, output đi theo nhánh khác:

```text
before move exists: false
atomic move: unsupported
```

Diễn giải:

1. `createTempDirectory` tạo một thư mục riêng, `createTempFile(directory, ...)` đặt staging file **cùng thư mục** với target.
2. Dữ liệu `READY` được encode UTF-8 rồi ghi với vòng lặp `while (buffer.hasRemaining())` vì một lần `channel.write` không được bảo đảm ghi hết.
3. `channel.force(true)` được gọi khi channel vẫn mở, sau khi byte đã được ghi bằng chính channel đó.
4. `Files.move(..., ATOMIC_MOVE)` yêu cầu thao tác rename nguyên tử. Nếu không thể, ví dụ báo `unsupported` và **không hạ cấp lặng lẽ**.
5. Ở nhánh thành công, target chứa toàn bộ chuỗi `READY` và staging path không tồn tại.
6. Cuối chương trình dọn file tạm. Việc demo mở/đọc file thành công chứng minh nội dung hiện nhìn thấy, **không chứng minh** directory entry đã được sync bền qua mất điện.

**Lưu ý:** ngay cả với filesystem hỗ trợ `ATOMIC_MOVE`, I/O vẫn có thể thất bại bởi lý do khác (quyền, hết dung lượng, lỗi thiết bị, lỗi xóa file tạm...). Chương trình sẽ để `IOException` được báo ra ngoài, không hứa một stdout cố định cho mọi lỗi môi trường.

### 7.1. Vì sao demo không gọi `Files.move(..., REPLACE_EXISTING)` khi `ATOMIC_MOVE` thất bại?

Vì yêu cầu của ví dụ là **không công bố bản cập nhật bằng một thao tác không đảm bảo atomicity**. Nếu fallback sang move thông thường, lời hứa “người đọc chỉ thấy một bản đầy đủ” không còn được bảo đảm bởi `ATOMIC_MOVE`.

Trong ứng dụng thật, bạn có thể cho phép một fallback kém mạnh hơn, nhưng đó phải là **quyết định nghiệp vụ rõ ràng**, có thông báo trạng thái, hành vi lỗi và quy trình recovery; không thể dùng cùng nhãn “atomic commit”.

## 8. Khi cập nhật đè target đã tồn tại: điểm phức tạp cần xử lý

Tình huống “lần ghi đầu” (target chưa có) đơn giản hơn tình huống “thay phiên bản đang dùng”. Muốn thay `settings.json` hiện hữu bằng bản mới:

```text
T0: target = phiên bản A
T1: staging = phiên bản B hợp lệ
T2: sync staging
T3: atomic rename staging → target (nếu platform hỗ trợ overwrite)
T4: sync parent directory theo platform
```

**Không nên giả định** `Files.move(staging, target, ATOMIC_MOVE, REPLACE_EXISTING)` luôn thay A bằng B. Vì khi có `ATOMIC_MOVE`, option còn lại bị bỏ qua; khi target có sẵn, **replace hay fail là implementation-specific**.

Một thiết kế production cần:

- Xác định rõ OS, filesystem, provider và khả năng atomic replace trên target hiện hữu.
- Xác nhận quyền, chính sách symlink, hard link và race với tiến trình khác.
- Viết tệp tạm hoàn chỉnh và kiểm tra nội dung trước khi công bố.
- Kiểm tra kết quả `force` và rename, không báo “committed/durable” nếu bước bắt buộc chưa hoàn thành.
- Đảm bảo recovery sau crash có thể phân biệt bản hợp lệ, bản cũ, file tạm hoặc trạng thái thiếu.
- Với yêu cầu durability mạnh, triển khai sync directory phù hợp nền tảng.

**Nguyên tắc nhất quán:** atomic rename một target **không** làm một nhóm file (ví dụ `config.json` và `index.json`) cùng đổi trong một transaction. Khi phải công bố nhiều file nhất quán, có thể cân nhắc ghi các file bất biến theo phiên bản, sau đó atomic update **một file manifest/pointer** duy nhất, kết hợp chính sách durability/recovery phù hợp.

## 9. Bảng “đã làm gì?” và “được bảo đảm gì?”

| Thao tác | Cải thiện tính chất gì? | Không tự bảo đảm điều gì? |
|---|---|---|
| `Files.write(...)` vào target | Ghi nội dung file | Không atomic publish, không chắc durable |
| Ghi file tạm hoàn chỉnh | Có phiên bản B riêng để kiểm tra | Chưa công bố target; chưa chắc durable |
| `channel.force(false)` | Flush nội dung theo `FileChannel` | Không nhất thiết flush metadata; không sync entry rename |
| `channel.force(true)` | Flush nội dung và metadata file theo contract | Không tự sync directory entry của rename sau đó |
| `Files.move(temp,target,ATOMIC_MOVE)` | Yêu cầu atomic namespace move khi hỗ trợ | Không tự fsync file/directory, không luôn replace được target có sẵn |
| `Files.move(temp,target,REPLACE_EXISTING)` | Yêu cầu thay target khi hỗ trợ | Không cam kết atomicity nếu thiếu `ATOMIC_MOVE` |
| Native `fsync(parentDir)` đúng platform | Có thể làm durable cập nhật directory entry theo contract OS | Không chữa payload chưa sync hoặc mọi lỗi phần cứng |
| `FileLock` | Điều phối một số truy cập concurrent theo semantics file lock | Không phải atomic rename, không phải cơ chế durable |
| `close()` channel | Giải phóng tài nguyên, có thể flush các layer liên quan theo contract của chúng | Không tương đương một lời gọi `force(true)` chắc chắn trong mọi trường hợp |

### 9.1. Tại sao `close()` không thể thay thế chính sách fsync?

Đóng một Writer/OutputStream có thể đẩy buffer trong process đến kênh I/O, nhưng Java không tuyên bố mọi `close` tương đương `FileChannel.force(true)` về độ bền dữ liệu và metadata. Cần gọi API sync đúng cách khi durability là yêu cầu. Ngay cả sau đó vẫn phải xử lý directory entry nếu nghiệp vụ cần bảo đảm rename bền qua mất nguồn.

### 9.2. `StandardOpenOption.SYNC` và `DSYNC`

Khi mở file để ghi, Java hỗ trợ:

- `SYNC`: yêu cầu mỗi cập nhật nội dung **hoặc metadata** được ghi đồng bộ tới thiết bị nền.
- `DSYNC`: yêu cầu cập nhật **nội dung** được ghi đồng bộ tới thiết bị nền; metadata không nhất thiết đi theo, trừ khi cần để truy xuất dữ liệu.

Đây là **option lúc mở file**, không phải option của `Files.move`:

```java
try (FileChannel ch = FileChannel.open(
        staging,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    // Ghi nội dung theo chính sách SYNC.
}
```

Ví dụ minh họa với `staging` đã tồn tại; các option phụ thuộc provider, chi phí đồng bộ có thể cao. `SYNC` hoặc `DSYNC` **không tự sync directory entry của rename xảy ra sau đó**. Với network filesystem, durability cuối cùng vẫn cần tuân theo contract của hệ thống bên dưới.

## 10. Kết quả sau crash: không được suy ra duy nhất từ một lời gọi API

Ta cần phân tích theo thời điểm xảy ra lỗi và giả định về OS/file system.

| Thời điểm sự cố | Trong lúc chạy đã quan sát gì? | Điều cần lưu ý khi phục hồi |
|---|---|---|
| Trước khi ghi đủ staging | Target cũ chưa công bố bản mới | Staging có thể thiếu dữ liệu; chỉ chấp nhận file có validation |
| Sau ghi staging, chưa sync file | Có thể đọc được staging B | Byte B có thể chưa durable |
| Sau sync staging, trước rename | Staging B được yêu cầu ghi bền | B chưa phải tên target; cần recovery cleanup/resume |
| Sau atomic rename, trước sync directory | Target B có thể đã nhìn thấy ngay | Không được mặc định directory entry B bền sau mất nguồn |
| Sau sync file + rename + sync directory đúng hợp đồng | Đã thực hiện các bước commit bền theo nền tảng | Vẫn phải tuân theo giới hạn thiết bị/OS và phục hồi dữ liệu ứng dụng |

Bảng này là **mô hình phân tích rủi ro**, không phải dự đoán tất định rằng “sau power loss luôn chỉ có A hoặc B” trên mọi file system. Java SE không quy định crash-recovery semantics cho từng thiết bị/provider. Không khẳng định chắc chắn target cũ hay mới sẽ tồn tại khi thiếu các bước sync cần thiết.

### 10.1. Một tên đích có đồng nghĩa một transaction không?

Nếu file mới chứa nhiều bản ghi, atomic rename chỉ đổi **con trỏ tên** từ phiên bản cũ sang phiên bản mới tại một thời điểm quan sát trong filesystem. Chính sách hợp lệ của file vẫn cần checksum, version, độ dài, schema và kiểm tra cấu trúc. Nếu ứng dụng còn cập nhật database, message queue hoặc nhiều file, rename không bảo đảm atomicity xuyên các tài nguyên đó.

Ví dụ: ghi `state.json` rồi gửi message “phiên bản 2 đã sẵn sàng” trước khi bảo đảm độ bền. Sau mất điện, message có thể đã đến consumer trong khi namespace file chưa bền, tạo sự bất nhất. Cần thiết kế đúng thứ tự commit và recovery.

## 11. Kiểm tra và xử lý lỗi trong ứng dụng thật

### 11.1. Không nuốt `AtomicMoveNotSupportedException`

```java
try {
    Files.move(staging, target,
            StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException ex) {
    // Chính sách: trả về lỗi rõ ràng, hoặc
    // thực hiện fallback với bảo đảm yếu hơn được mô tả riêng.
    throw ex;
}
```

Đây là đoạn minh họa trong method xử lý `IOException`. Không được chuyển thành `Files.move(..., REPLACE_EXISTING)` rồi tiếp tục log “atomic update succeeded”. Nếu sản phẩm chọn fallback, nên có tín hiệu phân biệt cả trong log/metrics và tài liệu API.

### 11.2. Cẩn thận về cleanup khi có lỗi

Nếu việc ghi staging thất bại, có thể còn file chưa hoàn chỉnh. Nếu rename chưa được thực hiện, dọn staging theo chính sách và giữ target cũ. Nếu rename đã thành công, không được giả định staging vẫn ở đường dẫn cũ. Ví dụ dùng:

```java
Path staging = Files.createTempFile(parent, ".update-", ".tmp");
try {
    // Ghi đủ bytes, force, validation, atomic rename ...
} finally {
    Files.deleteIfExists(staging);
}
```

Đây là đoạn mã minh họa trong method xử lý `IOException`. `finally` chạy khi process vẫn có cơ hội thực thi Java, không chạy nếu máy mất điện. Cleanup phải an toàn đối với file do chương trình tạo và không xóa target sau khi đã publish.

### 11.3. Kiểm tra failure mode mà không phá dữ liệu thật

- Unit test với thư mục tạm có thể xác minh nhánh rename thành công, quyền, xử lý exception, nội dung cuối và cleanup.
- Integration test trên filesystem thực có thể kiểm tra khả năng atomic move và hành vi replace target hiện hữu.
- Kiểm thử concurrent reader có thể tìm lỗi giao thức publish, nhưng **không chứng minh** độ bền sau mất điện.
- Crash/power-loss test cần môi trường thử riêng, cơ chế khôi phục và phép đo thực tế. Không cắt nguồn máy production để suy diễn.
- Nếu provider không hỗ trợ atomic move hoặc directory sync đáng tin, hệ thống phải hạ mức bảo đảm đã công bố hoặc chọn thiết kế lưu trữ khác.

## 12. Lỗi phổ biến

1. **“`ATOMIC_MOVE` nghĩa là dữ liệu đã durable.”** Sai: atomicity của namespace và durability của lưu trữ là hai thuộc tính riêng.
2. **“`FileChannel.force(true)` trước rename đủ để lưu tên cuối.”** Sai: rename cập nhật entry directory **sau** force file.
3. **“Đóng file tự động tương đương fsync file và fsync directory.”** Không có bảo đảm portable từ `close`.
4. **“`ATOMIC_MOVE + REPLACE_EXISTING` luôn overwrite nguyên tử.”** Java quy định các option khác bị bỏ qua; target đã tồn tại xử lý theo implementation.
5. **“Cùng một thư mục chắc chắn có atomic rename.”** Chỉ tăng khả năng tương thích; provider vẫn có thể từ chối.
6. **“Move không có `ATOMIC_MOVE` cũng chắc chắn là atomic trên mọi OS.”** Không được contract cam kết.
7. **“Nếu `Files.move` trả thành công, chắc chắn power-loss recovery giữ bản mới.”** Chưa đủ; cần các bước sync đúng phạm vi và contract nền tảng.
8. **“fsync file = fsync parent directory.”** Trên Linux, hai việc khác nhau; entry của thư mục cần sync riêng để có bảo đảm thích hợp.
9. **“`FileChannel.open(dir).force(true)` là directory fsync portable.”** Java SE không cung cấp hợp đồng chung như vậy.
10. **“Mọi thiết bị đều tôn trọng đúng flush.”** Độ bền thực phụ thuộc OS, firmware, controller, filesystem và thiết bị.
11. **“Rename giữ transaction cho nhiều file.”** Một thao tác rename không tạo commit nguyên tử cho một tập file hoặc database.
12. **“Kill process rồi thấy file đúng là đã kiểm chứng mất điện.”** Process crash không tương đương OS crash hoặc power loss.
13. **“File tạm để ở `java.io.tmpdir` vẫn atomic move sang đích.”** Temp mặc định có thể nằm trên file store khác.
14. **“Ghi xong một lần `channel.write` là đủ.”** NIO write có thể chỉ ghi một phần; phải lặp cho hết `ByteBuffer`.
15. **“Dùng `FileLock` thay sync.”** Lock liên quan phối hợp truy cập, không tự tạo độ bền.
16. **“Staging B đọc được” nghĩa là “B đã durable”.** Byte có thể chỉ ở page cache.
17. **“Journaling bảo đảm ứng dụng không bao giờ thấy file hỏng.”** Phụ thuộc mode filesystem và chính sách ghi nội dung, chưa kể dữ liệu ứng dụng.
18. **“Không cần recovery vì đã dùng atomic rename.”** Vẫn phải kiểm tra version/checksum và xử lý temp/file cũ theo chính sách.
19. **“Dùng `force(false)` luôn đủ metadata cần thiết.”** False không bắt buộc flush mọi metadata; xem nhu cầu thực.
20. **“Không có lỗi I/O tức đã đạt mức đảm bảo cao nhất.”** API chỉ cam kết trong phạm vi cụ thể; phần không được quy định phải được đánh giá riêng.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `Files.move(temp,target,ATOMIC_MOVE)` thành công. Điều đó có bảo đảm target mới còn sau mất điện không?  
**Đáp án:** Không. Nó yêu cầu atomic namespace move, không tự bảo đảm nội dung file và directory entry đã được ghi bền.

**Câu 2.** Nếu target tồn tại, `ATOMIC_MOVE` có bắt buộc thay thế nó không?  
**Đáp án:** Không. Hợp đồng Java để implementation quyết định replace hoặc thất bại; option khác như `REPLACE_EXISTING` bị bỏ qua khi có `ATOMIC_MOVE`.

**Câu 3.** Vì sao ghi temp trong cùng directory hữu ích?  
**Đáp án:** Tránh một nguyên nhân move không atomic: source và target ở các file store khác nhau. Nhưng vẫn phải kiểm tra provider hỗ trợ.

**Câu 4.** `FileChannel.force(true)` trên temp trước rename làm được gì?  
**Đáp án:** Trong điều kiện contract về lưu trữ cục bộ và cách ghi qua channel, yêu cầu flush nội dung cùng metadata file. Nó chưa sync đổi tên diễn ra sau đó.

**Câu 5.** Trên Linux, vì sao cần xem xét `fsync` parent directory sau rename?  
**Đáp án:** Vì `fsync` trên file không mặc định lưu bền entry tên trong thư mục; rename sửa namespace metadata của thư mục.

**Câu 6.** Java SE 17/21 có API directory fsync portable bảo đảm mọi OS không?  
**Đáp án:** Không có lời hứa như vậy từ `Files.move` hay `FileChannel.force`; cần đánh giá giải pháp nền tảng riêng nếu yêu cầu mức bảo đảm đó.

**Câu 7.** Nếu `ATOMIC_MOVE` không hỗ trợ thì gọi `REPLACE_EXISTING` và báo thành công “atomic update” được không?  
**Không.** Đây là chế độ có bảo đảm thấp hơn; nếu fallback phải công bố lại contract.

**Câu 8.** Dùng `channel.force(true)` sau khi sửa qua `MappedByteBuffer` có đủ chắc chắn không?  
**Đáp án:** `FileChannel.force` có thể không flush sửa đổi qua mapped buffer; xem `MappedByteBuffer.force()`.

**Câu 9.** Làm sao phân biệt kiểm thử process crash với kiểm thử power loss?  
**Đáp án:** Process crash để OS tiếp tục chạy và ghi cache; power loss ngắt cả khả năng tiếp tục flush, nên kết luận khác nhau.

**Câu 10.** Khi cần cập nhật đồng thời nhiều file cùng một phiên bản, atomic rename từng file có tạo một transaction không?  
**Không.** Cần giao thức riêng như snapshot bất biến + manifest/pointer commit, hoặc dùng storage engine có transaction/durability đã được xác minh.

## 14. Ghi nhớ và tài liệu chính thức

**Một câu cần nhớ:** *Đổi tên nguyên tử là thuộc tính của thao tác công bố tên; ghi bền là thuộc tính của dữ liệu/metadata sau crash. Muốn cả hai, phải thiết kế cả chuỗi ghi file, đồng bộ file, atomic rename và đồng bộ directory theo contract nền tảng.*

Tài liệu tham khảo:

- Java SE 21 — `Files.move`, `ATOMIC_MOVE` và `REPLACE_EXISTING`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html
- Java SE 21 — `StandardCopyOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html
- Java SE 21 — `FileChannel.force(boolean)`, `SYNC` và `DSYNC`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 21 — `StandardOpenOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html
- Linux man-pages — `fsync(2)`, đặc biệt ghi chú về đồng bộ thư mục chứa file: https://man7.org/linux/man-pages/man2/fsync.2.html
