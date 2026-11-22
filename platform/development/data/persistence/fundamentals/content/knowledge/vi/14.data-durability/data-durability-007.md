# Ghi chỉ thêm, ghi đè và nguy cơ bản ghi dở dang

Một ứng dụng có thể xử lý lệnh ghi thành công ở tầng Java nhưng vẫn mất dữ liệu hoặc đọc được nội dung không hoàn chỉnh sau khi máy bị mất điện. Nguyên nhân không chỉ nằm ở câu lệnh ghi đúng hay sai: hệ điều hành có bộ đệm, thiết bị lưu trữ có đơn vị ghi riêng, hệ thống tệp có cơ chế cập nhật metadata, còn ứng dụng có thể chết ngay giữa quá trình ghi một bản ghi.

Trong chương **Độ bền dữ liệu** của **DATA_PERSISTENCE_FUNDAMENTALS**, cần phân biệt hai chiến lược cơ bản:

- **Ghi chỉ thêm (append-only):** đặt dữ liệu mới ở cuối một chuỗi bản ghi; dữ liệu cũ giữ nguyên cho đến khi một quy trình dọn dẹp hoặc tái tổ chức thay thế chúng.
- **Ghi đè tại chỗ (in-place overwrite):** cập nhật các byte hoặc trang dữ liệu ở vị trí đã tồn tại.

Mỗi chiến lược có lợi thế và rủi ro khác nhau. **Append-only không tự bảo đảm một bản ghi được ghi trọn vẹn, bền vững hay có thể khôi phục.** Ngược lại, **ghi đè không đồng nghĩa với thiếu an toàn**: nhiều hệ quản trị cơ sở dữ liệu bảo vệ việc ghi trang dữ liệu bằng write-ahead log (WAL), checksum, copy-on-write hoặc cơ chế phục hồi khác.

Bài này giải thích vì sao bản ghi có thể bị *ghi dở* (*torn/partial record*), cách phát hiện phần dữ liệu chưa hoàn tất, cách chọn mốc khôi phục và cách Java phối hợp với lớp lưu trữ để xác nhận kết quả ghi.

## 1. Hai cách cập nhật một trạng thái

Giả sử hệ thống lưu số dư của tài khoản 42, ban đầu là 1.000, sau một giao dịch hợp lệ tăng thành 1.250. Có ít nhất hai cách biểu diễn:

**Ghi đè tại chỗ** thay giá trị cũ trong một vùng lưu trữ:

```text
Trước:  [account=42 | balance=1000 | ...]
                     |
                     v
Sau:    [account=42 | balance=1250 | ...]
         (cùng vị trí lưu trữ)
```

**Ghi chỉ thêm** bổ sung một bản ghi mô tả trạng thái hoặc sự kiện mới:

```text
[account=42 | balance=1000]
[account=42 | balance=1250]  <- bản ghi mới ở cuối

Hoặc nhật ký sự kiện:
[account=42 | credit=250 | eventId=abc]
```

Ở mô hình thứ hai, khi khôi phục trạng thái cần có quy tắc xác định bản ghi nào là hợp lệ và thứ tự áp dụng. Nếu lưu sự kiện cộng/trừ tiền, cần tránh áp dụng lại cùng một sự kiện hai lần. Nếu lưu các snapshot trạng thái, cần có số phiên bản hoặc thứ tự ghi để biết giá trị mới nhất.

| Khía cạnh | Ghi chỉ thêm | Ghi đè tại chỗ |
| --- | --- | --- |
| Thao tác chính | Thêm đoạn dữ liệu mới vào cuối log hoặc segment | Sửa trang/byte đã tồn tại |
| Dữ liệu cũ | Thường còn để phục hồi/audit cho đến khi dọn dẹp | Có thể bị thay thế, cần log hoặc bản sao để khôi phục |
| Khi ghi bị ngắt | Có thể còn **đuôi bản ghi chưa hoàn chỉnh** | Có thể còn **trang cũ, trang mới hoặc nội dung trộn** |
| Đọc trạng thái mới nhất | Có thể phải dựng lại chỉ mục, đọc snapshot hoặc compact | Thường thuận tiện khi đọc trực tiếp theo vị trí/khóa |
| Chi phí | Log lớn dần, cần retention/compaction/checkpoint | Có thể phát sinh ghi ngẫu nhiên, copy page, phân mảnh và chi phí phục hồi |
| Khả năng an toàn | Cần framing, xác thực, đồng bộ, phục hồi | Cần giao thức cập nhật nguyên tử hoặc bảo vệ bằng WAL/COW |

Sự khác biệt này là về **cách tổ chức ghi dữ liệu**, không phải về mức độ bảo đảm cuối cùng. Thiết kế đúng phải trả lời được: mất điện ở bất kỳ bước nào thì hệ thống sẽ nhìn thấy trạng thái nào?

## 2. Bản ghi dở dang là gì?

Một bản ghi logic có thể dài hàng trăm hoặc hàng nghìn byte. Tuy nhiên, một lần gọi `write` không nhất thiết tương ứng với **một thao tác bền vững và nguyên tử** trên thiết bị lưu trữ. Quá trình ghi có thể bị gián đoạn do tiến trình dừng đột ngột, bộ nhớ/thiết bị gặp sự cố, lỗi I/O hoặc máy mất nguồn.

Giả sử định dạng bản ghi có ba thành phần: độ dài, payload và checksum.

```text
Bản ghi dự kiến:
  [ length = 100 ][ payload = 100 byte ][ checksum = 4 byte ]

Sau sự cố:
  [ length = 100 ][ payload = 37 byte ] ... EOF

Hoặc:
  [ length = 100 ][ payload bị lỗi một số byte ][ checksum ]
```

Các trường hợp cần phân biệt:

1. **Partial write:** chỉ một phần số byte mà ứng dụng muốn ghi đã được chuyển qua một lời gọi I/O. API thường trả về số byte thật sự ghi; chương trình phải kiểm tra và lặp cho đến khi ghi hết hoặc gặp lỗi.
2. **Torn record:** sau sự cố, phần dữ liệu của một bản ghi logic có thể không đồng nhất, chẳng hạn một số phần là trạng thái mới còn phần khác là cũ, hoặc checksum không khớp. Một bản ghi logic thường lớn hơn đơn vị ghi nguyên tử mà thiết bị/hệ thống tệp thực sự cung cấp.
3. **Torn page:** một trang dữ liệu DB gồm nhiều khối/sector không được cập nhật đồng bộ; sau crash, trang có thể chứa các phần từ hai lần ghi khác nhau.
4. **Lost but acknowledged write:** nếu ứng dụng xác nhận thành công ngay sau khi dữ liệu vào bộ đệm, crash có thể làm mất dữ liệu chưa được buộc xuống tầng lưu trữ có khả năng giữ bền vững.
5. **Corruption:** dữ liệu có đủ byte nhưng nội dung bị hỏng; độ dài và việc đọc tới EOF không đủ chứng minh nội dung hợp lệ.

**Đơn vị ghi nguyên tử không đồng nghĩa với kích thước bản ghi của ứng dụng.** Cũng không thể mặc định một lời gọi `write()`, một lệnh `UPDATE`, một sector hoặc một trang 4 KiB/8 KiB là nguyên tử trên mọi file system, thiết bị và cấu hình. Một DB có thể cung cấp atomicity ở mức transaction nhờ cơ chế bảo vệ riêng, kể cả khi các thao tác ghi vật lý không nguyên tử.

## 3. Append-only: giữ tiền tố hợp lệ, nhưng phải xử lý đuôi dở dang

Giả sử file gồm ba bản ghi hợp lệ và tiến trình ngừng khi đang thêm bản ghi thứ tư:

```text
Offset 0
  |
  v
  +---------+---------+---------+--------------------+
  | R1 OK   | R2 OK   | R3 OK   | R4 chưa đủ byte   |
  +---------+---------+---------+--------------------+
                               ^
                               tiền tố hợp lệ kết thúc tại đây
```

Nếu mỗi bản ghi có định dạng tự mô tả, bộ đọc có thể kiểm tra từng bản ghi tuần tự rồi xác định vị trí **kết thúc của tiền tố hợp lệ**. Trong một mô hình log đơn giản chỉ có một writer, chỉ append và không cho ghi xen kẽ, một bản ghi chưa hoàn chỉnh ở cuối file có thể được coi là phần chưa được commit vào log. Khi khởi động lại, ứng dụng có thể bỏ phần đuôi chưa hoàn chỉnh rồi tiếp tục append.

Tuy nhiên, phải cẩn trọng:

- Một lỗi checksum ở **giữa** file có thể là hỏng dữ liệu đã từng hợp lệ, chứ không phải bản ghi cuối chưa ghi hết. Không được tự động bỏ qua một số byte rồi nối tiếp như thể không có gì xảy ra.
- Nếu có **nhiều writer** append đồng thời mà không có giao thức đồng bộ, các byte từ hai bản ghi có thể xen kẽ hoặc thứ tự logic không được bảo đảm như kỳ vọng.
- Nếu file chứa bản ghi đã ghi đủ byte nhưng **chưa được đồng bộ bền vững**, crash có thể làm mất hoặc làm hỏng cả phần đuôi; chỉ kiểm tra EOF không đủ xác nhận mốc commit.
- Sau khi phát hiện một đuôi chưa hoàn chỉnh, **phải sửa/truncate về vị trí hợp lệ** dưới quyền sở hữu độc quyền trước lần append tiếp theo. Nếu cứ nối thêm ngay phía sau đuôi hỏng, scanner tuần tự sẽ không thể đi tiếp đến bản ghi mới một cách đáng tin cậy.

Append-only hỗ trợ một chiến lược phục hồi rõ ràng là **valid prefix recovery**, nhưng không thể dựa trên giả định "mọi thứ đã append chắc chắn an toàn".

## 4. Thiết kế định dạng bản ghi có thể kiểm tra

Nếu tự viết một file log, không nên chỉ nối chuỗi văn bản mà không định nghĩa ranh giới và cách nhận biết lỗi. Một khung bản ghi (*framed record*) tối thiểu có thể chứa:

```text
  4 byte        4 byte         4 byte          N byte         4 byte
+----------+-------------+---------------+----------------+------------+
| MAGIC    | VERSION     | PAYLOAD_LEN   | PAYLOAD        | CRC32C     |
+----------+-------------+---------------+----------------+------------+
         \______________________________________________/
                      dữ liệu đưa vào checksum
```

Ý nghĩa:

- **MAGIC:** dấu hiệu nhận diện đúng định dạng, giúp phát hiện phần đầu không như mong đợi; không phải cơ chế mã hóa hay bằng chứng tính xác thực.
- **VERSION:** hỗ trợ thay đổi schema/dạng ghi trong tương lai; bộ đọc cần kiểm tra phiên bản được hỗ trợ.
- **PAYLOAD_LEN:** cho biết phải đọc bao nhiêu byte. Bắt buộc giới hạn kích thước tối đa trước khi cấp phát bộ nhớ; không tin một giá trị độ dài bất thường.
- **PAYLOAD:** nội dung bản ghi, ví dụ một sự kiện có mã định danh, loại và dữ liệu cần thiết.
- **CRC32C:** phát hiện nhiều lỗi byte ngẫu nhiên trong phần header và payload; **không** chống giả mạo có chủ đích. Nếu log cần chống sửa đổi độc hại, dùng MAC/chữ ký hoặc biện pháp bảo mật tương ứng.

Việc tính checksum trên cả header quan trọng vì một độ dài bị sai có thể làm bộ đọc mất vị trí ranh giới. Với log hoạt động thực tế còn có thể cần **sequence number/LSN**, transaction ID, loại bản ghi, giới hạn thời gian sống, cờ commit và phiên bản schema. Một bản ghi được cấu trúc tốt vẫn cần giao thức xác định **bản ghi nào được phép coi là đã commit**.

### Thuật toán đọc phục hồi đơn giản

Với file log do **một writer** sở hữu, không bị sửa giữa chừng và có khung định dạng trên, thuật toán minh họa:

```text
lastValidOffset = 0
while chưa đến EOF:
    đọc MAGIC, VERSION, PAYLOAD_LEN
    nếu EOF giữa header:
        báo "đuôi chưa hoàn chỉnh", dừng tại lastValidOffset
    nếu magic/version không hợp lệ hoặc length vượt giới hạn:
        báo "log có dấu hiệu hỏng", không tự ý bỏ qua byte
    đọc PAYLOAD_LEN byte và CRC32C
    nếu EOF giữa payload/checksum:
        báo "đuôi chưa hoàn chỉnh", dừng tại lastValidOffset
    nếu checksum sai:
        báo "bản ghi lỗi", điều tra/khôi phục từ bản sao hoặc backup
    xử lý bản ghi hợp lệ theo đúng thứ tự
    lastValidOffset = vị trí ngay sau bản ghi

sau khi chấp nhận trạng thái khôi phục và có độc quyền file:
    chỉ truncate phần đuôi thiếu byte rõ ràng đến lastValidOffset
    đồng bộ thay đổi metadata nếu giao thức yêu cầu
    mở quyền append trở lại
```

Đây là **khung tư duy**, chưa phải recovery protocol đầy đủ cho một DB. Chẳng hạn, nếu chỉ một bản ghi cuối có checksum sai nhưng chiều dài đầy đủ, không thể biết chỉ từ checksum rằng lỗi là do crash hay dữ liệu cũ bị hỏng. Cần chính sách rõ ràng: dừng dịch vụ và đối soát, phục hồi từ bản sao, hoặc dùng thông tin commit/checkpoint bổ sung. Không âm thầm xem mọi lỗi checksum là "tail có thể xóa".

## 5. Java FileChannel: ghi đủ byte và yêu cầu đồng bộ

Ví dụ dưới đây viết một bản ghi vào **file log minh họa** với khung `MAGIC + VERSION + LENGTH + PAYLOAD + CRC32C`. Dùng Java 17+, giới hạn payload và `FileChannel.force(true)` để yêu cầu hệ điều hành đồng bộ dữ liệu/metadata của file. Ví dụ giả định **một tiến trình sở hữu file log**, các bên ghi đều sử dụng cùng cơ chế khóa và quá trình khôi phục đuôi lỗi đã chạy xong trước khi append.

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.zip.CRC32C;

public final class FramedEventLog {
    private static final int MAGIC = 0x45565431; // "EVT1"
    private static final int VERSION = 1;
    private static final int HEADER_BYTES = 3 * Integer.BYTES;
    private static final int CHECKSUM_BYTES = Integer.BYTES;
    private static final int MAX_PAYLOAD_BYTES = 1024 * 1024;

    private FramedEventLog() {}

    public static void append(Path path, byte[] payload) throws IOException {
        if (payload == null || payload.length > MAX_PAYLOAD_BYTES) {
            throw new IllegalArgumentException("Payload không hợp lệ");
        }

        ByteBuffer frame = ByteBuffer.allocate(
                HEADER_BYTES + payload.length + CHECKSUM_BYTES);
        frame.putInt(MAGIC);
        frame.putInt(VERSION);
        frame.putInt(payload.length);
        frame.put(payload);

        CRC32C crc = new CRC32C();
        crc.update(frame.array(), 0, HEADER_BYTES + payload.length);
        frame.putInt((int) crc.getValue());
        frame.flip();

        try (FileChannel channel = FileChannel.open(
                    path, StandardOpenOption.CREATE, StandardOpenOption.WRITE);
             FileLock ignored = channel.lock()) {
            // Điều kiện tiên quyết: startup đã đọc/khôi phục log
            // và đã xử lý mọi đuôi chưa hoàn chỉnh.
            channel.position(channel.size());
            while (frame.hasRemaining()) {
                int written = channel.write(frame);
                if (written <= 0) {
                    throw new IOException("Không thể tiếp tục ghi bản ghi");
                }
            }
            // Yêu cầu đẩy dữ liệu và metadata của file xuống storage.
            channel.force(true);
        }
    }
}
```

Giải thích những dòng dễ bị hiểu sai:

1. **`while (frame.hasRemaining())`:** một lệnh `FileChannel.write` có thể ghi ít byte hơn yêu cầu. Lặp đến khi ghi đủ là điều kiện cần để hoàn tất bản ghi ở tầng API.
2. **`FileLock`:** nhằm giới hạn các writer cùng tuân thủ cơ chế khóa khi dùng chung file. Khả năng bảo vệ tùy hệ điều hành và file system; không được giả định nó bảo vệ trước các writer không hợp tác, hoặc rằng locking trên ổ mạng luôn giống ổ cục bộ.
3. **`channel.position(channel.size())`:** chọn cuối file **trong khi đang giữ khóa**. Nếu có tiến trình không tuân thủ khóa, nó vẫn có thể phá hỏng quy tắc ghi nối tiếp. Đừng nhầm thao tác này với giao thức append đồng thời an toàn cho nhiều writer.
4. **`force(true)`:** yêu cầu đồng bộ dữ liệu và metadata của **file** theo khả năng của hệ điều hành/thiết bị. Nó không biến một loạt byte thành một thao tác nguyên tử; cũng không bảo đảm trường hợp firmware, bộ đệm phần cứng không an toàn hoặc môi trường lưu trữ không thực hiện đúng cam kết.
5. **Lỗi giữa chừng:** nếu `write` hoặc `force` ném `IOException`, file có thể đã tăng kích thước hoặc chứa bản ghi dở. Phía gọi **không được xác nhận bản ghi đã bền vững**, và lần mở lại phải qua kiểm tra/khôi phục trước khi append tiếp.

Nếu file vừa được **tạo mới**, tính bền vững của mục tên file trong thư mục có thể còn yêu cầu đồng bộ thư mục chứa file, tùy file system và hệ điều hành. Java không cung cấp một cách đồng bộ thư mục bảo đảm hoạt động trên mọi nền tảng; hệ thống có yêu cầu độ bền nghiêm ngặt cần xác nhận hành vi trên nền tảng triển khai thực tế.

Ví dụ trên tập trung vào **đường ghi**. Một ứng dụng dùng log thật phải xây dựng đường đọc, recovery, quản lý đồng thời, versioning, commit marker/transaction boundary, bảo vệ khỏi quá trình ghi trùng, và cách dọn/compact dữ liệu. Nếu đang dùng PostgreSQL, MySQL hay một DB có transaction, hãy ưu tiên dùng đúng giao thức commit do DB cung cấp thay vì cố thay thế chúng bằng một file append tự viết.

## 6. Đồng bộ xuống ổ lưu trữ và mốc xác nhận thành công

Có ít nhất bốn mốc khác nhau khi ứng dụng gọi ghi:

```text
Ứng dụng tạo bản ghi
   |
   +-- (1) Đưa dữ liệu vào bộ đệm của ứng dụng
   |
   +-- (2) Lời gọi write trả về: byte đã được hệ điều hành chấp nhận
   |
   +-- (3) fsync/FileChannel.force hoặc giao thức DB xác nhận đồng bộ
   |
   +-- (4) Ứng dụng trả "thành công" cho bên gọi
```

Tùy yêu cầu độ bền, điểm **(4)** nên gắn với một tiêu chí rõ ràng như "commit đã được DB xác nhận theo cấu hình durability yêu cầu", hoặc "record trong log đã qua bước đồng bộ theo giao thức". Chỉ đến bước (2) chưa thể suy ra dữ liệu chịu được mất nguồn.

| Thời điểm máy gặp sự cố | Điều không được suy đoán |
| --- | --- |
| Trước khi gọi ghi | Không có lý do để tin bản ghi đã xuất hiện. |
| Sau khi `write` trả về, trước khi đồng bộ | Không thể bảo đảm bản ghi còn sau mất điện, dù có thể vẫn còn nhờ hệ thống lưu trữ. |
| Trong lúc `force` hoặc DB commit đang chạy | Kết quả có thể **không rõ** với ứng dụng; cần phục hồi/đối soát trước khi retry có tác động nghiệp vụ. |
| Sau khi đồng bộ/commit thành công theo cấu hình | Có cơ sở dựa trên cam kết của tầng lưu trữ, nhưng vẫn phải xét lỗi phần cứng, phạm vi đồng bộ, replication và cấu hình cụ thể. |

**Atomicity** và **durability** là hai thuộc tính khác nhau. Atomicity nói về việc một nhóm thay đổi logic xuất hiện đầy đủ hay không có gì sau phục hồi; durability nói về việc thay đổi đã commit có còn sau sự cố được mô hình bảo đảm hay không. Một bản ghi được `force` thành công vẫn có thể yêu cầu giao thức phát hiện torn record nếu lỗi xuất hiện trong các lần ghi khác hoặc trường hợp thiết bị không bảo đảm nguyên tử.

### Group commit và độ trễ

Đồng bộ từng bản ghi có thể tăng latency và làm giảm throughput. Nhiều hệ thống gom các lần commit để dùng chung một lần flush bền vững (*group commit*). Chiến lược này cần ghi rõ **bản ghi nào đã được xác nhận** sau mỗi lần đồng bộ. Nếu trả kết quả thành công trước khi nhóm được flush, ứng dụng đã chấp nhận một cửa sổ mất dữ liệu. Sự đánh đổi phải được đo và thống nhất với yêu cầu nghiệp vụ.

## 7. Ghi đè tại chỗ: an toàn nhờ giao thức phục hồi

Ghi đè trực tiếp một cấu trúc dữ liệu lớn có rủi ro là crash xảy ra sau khi một số byte được thay nhưng trước khi tất cả phần liên quan được ghi xong:

```text
Trang ban đầu:    [ Header cũ | Data cũ | Checksum cũ ]
Trang muốn ghi:   [ Header mới | Data mới | Checksum mới ]
Crash giữa chừng: [ Header mới | Data cũ | Checksum cũ ]
```

Nếu không có checksum hoặc nhật ký thay đổi, ứng dụng có thể đọc trạng thái bị trộn mà không nhận ra. Nếu ghi đè bản duy nhất và không có bản cũ, dữ liệu có thể không thể khôi phục đầy đủ.

Hai họ giải pháp phổ biến:

**A. Write-ahead logging (WAL)**

1. Ghi một bản ghi log mô tả thay đổi hoặc thông tin cần để redo/undo.
2. Bảo đảm các bản ghi log cần thiết được đồng bộ theo quy tắc write-ahead **trước khi** trang dữ liệu liên quan được flush.
3. Khi xác nhận commit, hệ quản trị bảo đảm thông tin commit/log cần thiết đã bền vững theo chính sách cấu hình.
4. Sau crash, recovery dùng log và metadata liên quan để xác định thay đổi nào cần phát lại hoặc hoàn tác. Cách làm cụ thể khác nhau giữa các engine.

```text
Transaction ghi dữ liệu
      |
      +--> WAL record --đồng bộ--> log bền vững
      |                             |
      +--> data page có thể flush <-+
      |
      +--> commit record / commit protocol
                                  |
                     Crash -> recovery từ WAL + page
```

WAL **không đồng nghĩa với việc toàn bộ dữ liệu nghiệp vụ được lưu append-only mãi mãi**. DB vẫn có thể ghi đè các trang dữ liệu, trong khi log hỗ trợ phục hồi các thao tác chưa được phản ánh đầy đủ vào trang.

**B. Copy-on-write (COW), shadow paging hoặc ghi file mới rồi thay thế**

Thay vì sửa bản cũ ngay, hệ thống ghi một phiên bản mới, kiểm tra/đồng bộ nó, rồi cập nhật một tham chiếu hoặc metadata để trỏ đến phiên bản mới. Với file cấu hình nhỏ, mẫu thường gặp là:

```text
1. Ghi state.tmp trong cùng file system.
2. Flush và đồng bộ state.tmp.
3. Đổi tên/thay thế state.tmp -> state.dat bằng thao tác
   được nền tảng hỗ trợ theo cách nguyên tử về khả năng quan sát.
4. Đồng bộ thư mục nếu cần và được hỗ trợ cho tính bền vững
   của việc đổi tên.
```

Đây là **một giao thức cần kiểm chứng**, không chỉ là gọi `Files.move(..., ATOMIC_MOVE)` rồi coi dữ liệu đã chống mất điện. Atomic rename thường bảo vệ việc người đọc thấy tên file cũ hay tên file mới; tính bền vững sau crash của file mới và directory entry là vấn đề riêng. Các file system, OS và cách thay thế file đang tồn tại có thể có giới hạn khác nhau.

| Kỹ thuật | Giảm rủi ro nào? | Giới hạn chính |
| --- | --- | --- |
| Framed append + checksum | Phát hiện record thiếu byte/hỏng; giữ được tiền tố hợp lệ trong mô hình phù hợp | Không thay cho commit protocol và đồng bộ; log có thể phình to |
| WAL | Cho phép phục hồi trạng thái transaction khi data page chưa đồng bộ hoặc bị ghi dở, tùy thiết kế engine | Phải tuân thủ thứ tự log/page, commit và recovery; cấu hình có thể giảm durability |
| COW/shadow paging | Giữ bản cũ trong lúc viết bản mới; thay đổi tham chiếu theo giao thức | Tăng ghi và metadata; cần quản lý crash ở bước chuyển tham chiếu |
| Doublewrite buffer | Hỗ trợ phục hồi trang dữ liệu bị torn bằng bản sao trang an toàn hơn | Cần engine quản lý chính xác thứ tự ghi và phục hồi |
| Backup và replication | Khôi phục khi hỏng thiết bị, xóa nhầm hoặc lỗi diện rộng theo phạm vi giải pháp | Không tự bảo đảm commit riêng lẻ là nguyên tử; replica có thể sao chép lỗi và backup có RPO |

## 8. Giao dịch Java: đừng nhầm commit DB với ghi một file

Khi code Java dùng JDBC để cập nhật nhiều bảng trong một giao dịch, nên giao cho DB thực hiện atomicity/durability theo mức cấu hình đã chọn:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class BalanceRepository {
    public void transfer(Connection connection, long fromId, long toId,
                         BigDecimal amount) throws SQLException {
        // Phương thức này được tầng gọi quản lý transaction.
        try (PreparedStatement debit = connection.prepareStatement("""
                UPDATE accounts
                SET balance = balance - ?
                WHERE account_id = ? AND balance >= ?
                """);
             PreparedStatement credit = connection.prepareStatement("""
                UPDATE accounts
                SET balance = balance + ?
                WHERE account_id = ?
                """)) {
            debit.setBigDecimal(1, amount);
            debit.setLong(2, fromId);
            debit.setBigDecimal(3, amount);
            if (debit.executeUpdate() != 1) {
                throw new SQLException("Không thể trừ số dư nguồn");
            }

            credit.setBigDecimal(1, amount);
            credit.setLong(2, toId);
            if (credit.executeUpdate() != 1) {
                throw new SQLException("Không thể cộng số dư đích");
            }
        }
    }
}
```

Tầng service phải mở transaction trước khi gọi `transfer`, thực hiện `commit` sau khi tất cả bước thành công, và `rollback` khi thất bại. Hàm repository trên **không tự xác nhận commit**; nó cũng giả định tầng gọi đã kiểm tra `amount > 0`, `fromId != toId` và quyền thực hiện giao dịch. Một hệ thống chuyển tiền thật cần thêm khóa nghiệp vụ duy nhất, idempotency và sổ cái để xử lý yêu cầu lặp hoặc kết quả commit không rõ ràng.

Nếu transaction commit thành công nhưng ứng dụng gặp lỗi kết nối trước khi nhận phản hồi, không thể đơn giản dựa vào ngoại lệ để kết luận "chưa ghi" rồi thực hiện lại lệnh chuyển tiền. Với các thao tác tài chính, cần tra cứu trạng thái theo một mã yêu cầu duy nhất hoặc dùng phương án idempotent đã thiết kế.

Tương tự, thêm một dòng vào file log riêng **không tự động trở thành một phần của giao dịch JDBC**. Ví dụ:

```text
1. UPDATE bảng đơn hàng trong DB
2. Append "ORDER_PAID" vào file log riêng
3. COMMIT transaction DB
```

Nếu crash sau bước 2 nhưng trước bước 3, file log có thể chứa sự kiện `ORDER_PAID` dù DB đã rollback. Nếu đảo thứ tự, crash sau commit DB nhưng trước khi append có thể làm thiếu sự kiện. Với yêu cầu đồng bộ dữ liệu DB và sự kiện bên ngoài, cân nhắc **transactional outbox** hoặc giao thức phối hợp phù hợp. Chỉ gọi `force()` trên file và `commit()` trên DB riêng rẽ không tạo thành một giao dịch phân tán nguyên tử.

## 9. Tình huống mất điện và cách quyết định phục hồi

Xét một log thanh toán có các bản ghi `P1`, `P2` đã xác nhận và ứng dụng đang thêm `P3`. Một quy trình phục hồi đáng tin cậy cần trả lời:

| Trạng thái quan sát sau restart | Hành động phù hợp | Điều tránh làm |
| --- | --- | --- |
| Hai bản ghi đầu hợp lệ, EOF giữa header của `P3` | Nhận diện phần đuôi thiếu byte, đối chiếu mốc xác nhận rồi xử lý tail theo giao thức | Không coi `P3` đã bền vững chỉ vì header có vài byte |
| Header `P3` hợp lệ nhưng payload thiếu byte | Dừng ở tiền tố hợp lệ; nếu chính sách cho phép, truncate dưới khóa độc quyền | Không nối bản ghi mới sau payload dang dở |
| Payload và checksum `P3` đầy đủ, checksum hợp lệ | Đối chiếu commit marker/LSN và chính sách xác nhận để quyết định áp dụng | Không suy từ checksum rằng transaction nghiệp vụ đã commit |
| Checksum `P2` sai trong vùng đã từng xác nhận | Báo hỏng dữ liệu; phục hồi từ bản sao/backup hoặc cơ chế sửa lỗi được thiết kế | Không im lặng bỏ `P2` rồi tiếp tục như không có lỗi |
| DB commit chưa trả kết quả vì mạng đứt | Đối soát bằng khóa idempotency/trạng thái DB trước khi retry | Không kết luận transaction đã rollback hoặc commit chỉ từ timeout |

Ở mức vận hành, cần đặt câu hỏi **RPO** (được chấp nhận mất tối đa bao nhiêu dữ liệu khi có sự cố), **RTO** (cần phục hồi trong bao lâu), cách sao lưu, số bản sao độc lập và cách kiểm tra backup bằng thao tác restore. Một write durable trên một ổ đĩa vẫn không bảo vệ trước cháy máy chủ, mất toàn bộ vùng lưu trữ hoặc xóa nhầm có thể lan sang replica.

## 10. Bài tập thực hành

### Bài tập 1: phân biệt append và overwrite

Một ứng dụng có hai phiên bản file:

```text
A. App ghi đè 8 KiB dữ liệu cũ ở cùng vị trí.
B. App append một record mới dài 8 KiB vào cuối log.
```

Máy mất điện giữa chừng. Hãy giải thích vì sao **cả A và B đều cần cơ chế phát hiện lỗi**, nhưng B thường có cơ hội giữ một tiền tố record hợp lệ dễ xác định hơn. Cần thêm thông tin gì để biết phần dữ liệu nào đã được xác nhận? 

**Gợi ý:** xem byte đã ghi, ranh giới record, checksum, quy tắc flush, mốc commit và liệu có nhiều writer không.

### Bài tập 2: tìm lỗ hổng của đoạn ghi Java

```java
channel.write(buffer);
return true;
```

**Câu hỏi:** thiếu những điều kiện gì nếu `true` có nghĩa bản ghi đã được lưu bền vững?

**Đáp án:** phải lặp cho đến khi buffer hết dữ liệu; định nghĩa framing/kiểm tra checksum và recovery; đồng bộ bằng cơ chế phù hợp; bảo đảm writer không xen kẽ; xác định mốc xác nhận và xử lý `IOException`/kết quả không rõ. `write` trả về không phải bảo đảm dữ liệu vẫn còn sau mất nguồn.

### Bài tập 3: khôi phục một log

```text
[R1: hợp lệ][R2: hợp lệ][R3: chỉ ghi được nửa payload] EOF
```

**Câu hỏi:** scanner nên dừng ở đâu? Điều gì phải xảy ra **trước lần append tiếp theo**? Nếu checksum của `R2` sai thì còn được tự truncate từ `R2` trở đi không?

**Đáp án:** với giả định log một writer chỉ append, scanner dừng tại offset kết thúc `R2`. Khi đã xác minh chính sách phục hồi và có khóa độc quyền, loại bỏ đuôi dang dở rồi mới append. Nếu `R2` hỏng checksum trong dữ liệu đã xác nhận, phải coi đó là lỗi toàn vẹn dữ liệu, điều tra/restore; không tự xóa tùy tiện một phần lịch sử.

### Bài tập 4: kiểm tra giao thức ghi file mới

Bạn đang cập nhật file cấu hình quan trọng bằng cách ghi `settings.tmp` rồi gọi `Files.move(tmp, target, ATOMIC_MOVE)`.

**Câu hỏi:** điều gì chưa đủ để cam kết chịu được mất điện?

**Đáp án:** phải xem dữ liệu file tạm đã được đồng bộ hay chưa; thao tác đổi tên/thay thế có được hỗ trợ và nguyên tử trên đúng file system hay không; metadata của thư mục có cần đồng bộ để tên mới bền vững không; và cách phục hồi nếu gặp lỗi ở từng bước.

### Checklist thiết kế độ bền dữ liệu

- Có xác định rõ **bản ghi logic**, giới hạn kích thước, phiên bản định dạng, checksum và cách xử lý record thiếu byte không?
- Có phân biệt **ghi đủ byte**, **đồng bộ xuống storage** và **commit nghiệp vụ** không? Điểm nào ứng dụng được phép trả thành công?
- Sau crash, có thuật toán tìm tiền tố hợp lệ và quy tắc xử lý corruption giữa log khác đuôi chưa hoàn chỉnh không?
- Mọi writer có tuân thủ cùng một cơ chế khóa/thứ tự và thực hiện recovery trước khi nối tiếp log không?
- Nếu cập nhật tại chỗ, có WAL/COW/doublewrite/backup hoặc giao thức phục hồi tương ứng không?
- Nếu vừa ghi DB vừa gọi hệ thống khác, đã thiết kế chống trạng thái lệch và retry trùng chưa?
- Đã thử mô phỏng lỗi ở **trước ghi, giữa ghi, trước đồng bộ, trong commit và sau commit**, đồng thời kiểm tra restore từ backup chưa?

**Kết luận:** Ghi chỉ thêm thuận lợi cho việc giữ lịch sử và tìm tiền tố bản ghi hợp lệ, còn ghi đè giúp cập nhật trạng thái trực tiếp nhưng cần bảo vệ dữ liệu cũ khi crash. Không có phương án nào tự giải quyết **bản ghi dở dang, xác nhận commit và độ bền dữ liệu**. Điều quyết định tính đúng đắn là một giao thức nhất quán giữa **định dạng ghi, kiểm tra lỗi, thứ tự đồng bộ, khôi phục và cách ứng dụng xử lý kết quả không rõ ràng**.
