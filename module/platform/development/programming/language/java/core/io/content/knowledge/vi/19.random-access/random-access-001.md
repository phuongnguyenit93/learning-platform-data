# RandomAccessFile và các chế độ `r`, `rw`, `rws`, `rwd`

## 1. Bài toán: đọc và sửa một vị trí bất kỳ trong tệp

Khi xử lý một tệp văn bản theo dòng, ta thường đọc tuần tự từ đầu tới cuối. Nhưng đôi khi ứng dụng cần **đọc bản ghi thứ 500**, **sửa đúng 4 byte ở giữa tệp**, hoặc **ghi nối tiếp sau byte cuối** mà không đọc lại toàn bộ nội dung. Đó là **truy cập ngẫu nhiên (random access)**.

Java cung cấp lớp **`java.io.RandomAccessFile`** để đọc/ghi theo **vị trí byte** trên một tệp:

- Có một **file pointer** (con trỏ vị trí), khởi đầu ở offset `0` khi mở tệp.
- `seek(offset)` đặt con trỏ đến offset mong muốn.
- Thao tác `read...` lấy byte bắt đầu tại con trỏ; `write...` ghi byte tại con trỏ. Sau thao tác, con trỏ tiến theo số byte đã đọc/ghi.
- `length()` trả về kích thước tệp **tính bằng byte**, khác với số ký tự hoặc số bản ghi.
- Chế độ mở (`"r"`, `"rw"`, `"rws"`, `"rwd"`) xác định quyền ghi và yêu cầu đồng bộ xuống thiết bị lưu trữ.

`RandomAccessFile` triển khai `DataInput`, `DataOutput` và `Closeable`; nó **không** là lớp con của `InputStream` hay `OutputStream`. Do có thể di chuyển con trỏ cả về trước lẫn về sau, nó phù hợp với tệp nhị phân, định dạng bản ghi có kích thước cố định, cập nhật header hoặc chỉ mục byte.

Sơ đồ tệp gồm ba số nguyên `int` (Java ghi mỗi `int` thành **4 byte**, byte có trọng số lớn trước):

~~~text
Offset byte       0             4             8            12 = length
                  |  int = 10   |  int = 20   |  int = 30  |
                  ^ bắt đầu       ^ seek(4)     ^ seek(8)   ^ EOF
~~~

Gọi `seek(4)` rồi `writeInt(99)` sẽ thay **chỉ bốn byte thứ 4 đến 7**. Tệp vẫn dài 12 byte; hai số khác giữ nguyên.

## 2. Bốn chế độ mở tệp

Cú pháp:

~~~java
// Path có thể được chuyển thành File khi dùng default file system:
try (RandomAccessFile raf = new RandomAccessFile(path.toFile(), "rw")) {
    // Đọc/ghi tại các byte offset mong muốn
}
~~~

Đây là đoạn minh họa đặt trong ngữ cảnh đã khai báo `Path path` và các import cần thiết. Một chương trình chạy đầy đủ nằm ở mục 5.

| Mode | Đọc | Ghi | Nếu tệp chưa tồn tại | Đảm bảo đồng bộ khi cập nhật |
|---|---|---|---|---|
| `"r"` | Có | Không | Mở thất bại (`FileNotFoundException`) | Không thực hiện ghi |
| `"rw"` | Có | Có | Cố tạo tệp mới | Không yêu cầu mỗi lần cập nhật phải đồng bộ xuống thiết bị |
| `"rws"` | Có | Có | Cố tạo tệp mới | Đồng bộ **nội dung và metadata** cho mỗi cập nhật |
| `"rwd"` | Có | Có | Cố tạo tệp mới | Đồng bộ **nội dung** cho mỗi cập nhật; metadata không có cùng yêu cầu |

Những điểm phải nhớ:

- `"r"` là **read-only**. Nếu gọi `writeInt`, `writeBytes`, `write` hoặc phương thức ghi khác trên đối tượng này, Java ném **`IOException`**.
- `"rw"` là **read/write**, **không có nghĩa** ghi nối cuối tệp (append). Trừ khi tự gọi `seek(length())`, chương trình ghi tại **con trỏ hiện tại**; lúc mới mở là offset 0 nên có thể **ghi đè phần đầu tệp**.
- `"rws"` và `"rwd"` đều là read/write giống `"rw"`, có thêm yêu cầu lưu bền vững ở mỗi cập nhật.
- Chỉ bốn chuỗi trên hợp lệ. Chẳng hạn `"w"`, `"a"`, `"rb"`, `"rw+"` hoặc `"R"` sẽ dẫn tới **`IllegalArgumentException`**.
- Việc mở tệp vẫn có thể thất bại vì không đủ quyền, không thể tạo tệp, thiếu thư mục cha, tệp đang bị hệ điều hành hạn chế truy cập hoặc lỗi I/O. `"rw"` không tự tạo toàn bộ thư mục cha.
- `RandomAccessFile` **không tự động truncate** tệp đang tồn tại khi mở bằng `"rw"`; muốn xóa nội dung cũ phải chủ động `setLength(0)`.

### 2.1. `rws`: đồng bộ dữ liệu **và metadata**

`"rws"` yêu cầu mọi cập nhật nội dung hoặc metadata được ghi **đồng bộ** xuống thiết bị lưu trữ cơ sở. Metadata liên quan đến tệp có thể bao gồm độ dài tệp và thời điểm sửa đổi; chi tiết phụ thuộc hệ thống tệp.

~~~java
try (RandomAccessFile raf = new RandomAccessFile(file, "rws")) {
    raf.seek(0);
    raf.writeInt(42); // Yêu cầu đồng bộ nội dung và metadata liên quan.
}
~~~

Đây là đoạn minh họa với `File file` đã hợp lệ. Mode này có ý nghĩa khi cần độ bền của cả thông tin quản lý tệp lẫn dữ liệu, ví dụ cập nhật khiến tệp dài thêm. Trên một số hệ thống tệp, đồng bộ metadata có thêm chi phí I/O.

### 2.2. `rwd`: đồng bộ dữ liệu, có thể rẻ hơn

`"rwd"` yêu cầu mỗi cập nhật **nội dung** được ghi đồng bộ; Java không yêu cầu đồng bộ cả metadata như `"rws"`.

~~~java
try (RandomAccessFile raf = new RandomAccessFile(file, "rwd")) {
    raf.seek(0);
    raf.writeInt(42); // Yêu cầu đồng bộ dữ liệu tệp.
}
~~~

Nếu thường xuyên ghi đè một vùng byte **đã tồn tại**, `"rwd"` có thể hợp lý vì không cần cùng mức đồng bộ metadata. Tuy nhiên không thể khẳng định `"rwd"` sẽ nhanh hơn `"rws"` trên mọi thiết bị; kết quả phụ thuộc OS, bộ nhớ đệm, file system và kiểu cập nhật.

**Rất quan trọng:** `rwd` chỉ đảm bảo đồng bộ dữ liệu theo hợp đồng API. Với một thao tác **mở rộng tệp**, metadata như kích thước cũng có thể quan trọng để sau sự cố còn truy cập được dữ liệu mới. Đừng tự suy ra “dữ liệu đã đồng bộ” đồng nghĩa toàn bộ cấu trúc tệp đã được lưu bền vững như `rws`.

### 2.3. Độ bền không đồng nghĩa tính nguyên tử hay giao dịch

Theo đặc tả Java 17, với **thiết bị lưu trữ cục bộ**, khi một phương thức trên `RandomAccessFile` dùng `"rws"` hoặc `"rwd"` trả về thành công, các thay đổi thuộc phạm vi yêu cầu đồng bộ của phương thức đó đã được ghi xuống thiết bị. Đối với **thiết bị không phải local** (ví dụ một số hệ thống tệp mạng), API **không đưa ra bảo đảm tương tự**.

Dù dùng mode nào:

- Một chuỗi nhiều lời gọi `seek`, `writeInt`, `writeLong` **không biến thành một transaction nguyên tử**. Sự cố giữa chừng vẫn có thể để lại bản ghi chỉ cập nhật một phần.
- Đồng bộ thành công không thay thế cơ chế **lock**, journal, checksum, bản sao dự phòng hoặc protocol khôi phục nếu dữ liệu quan trọng.
- Đồng bộ có thể làm chậm ứng dụng vì tăng I/O ghi. Cân bằng độ bền và hiệu năng theo yêu cầu thực tế, đo trên môi trường mục tiêu.
- `"rw"` thiếu yêu cầu đồng bộ **trên từng lần ghi**; điều đó không có nghĩa dữ liệu chắc chắn chỉ nằm trong RAM hay chắc chắn mất sau sự cố.

### 2.4. So sánh với `FileChannel.force`

Với `"rw"`, một ứng dụng có thể **ghi nhiều lần rồi yêu cầu flush/force tại một thời điểm**:

~~~java
try (RandomAccessFile raf = new RandomAccessFile(file, "rw")) {
    raf.seek(0);
    raf.writeInt(10);
    raf.writeInt(20);
    raf.getChannel().force(true); // Yêu cầu đẩy content + metadata xuống thiết bị.
}
~~~

- `raf.getChannel().force(true)` gần với yêu cầu đồng bộ **content và metadata**.
- `raf.getChannel().force(false)` gần với yêu cầu đồng bộ **content**.
- `"rws"` và `"rwd"` áp dụng yêu cầu ấy **cho từng I/O/cập nhật**, thay vì chờ lời gọi `force` có chủ đích. Đặc tả lưu ý các mode đồng bộ có thể hoạt động hiệu quả hơn so với việc tự `force` sau mỗi thao tác; điều này không xác định cách nào nhanh nhất khi gom nhiều thao tác.
- `force` cũng chịu giới hạn bảo đảm khi tệp không nằm trên thiết bị cục bộ. Mở tệp chỉ đọc không biến `force` thành thao tác ghi.

Xem đặc tả chính thức của `RandomAccessFile` và `FileChannel.force(boolean)` ở cuối bài.

## 3. Con trỏ byte: `seek`, `getFilePointer`, `length`, `setLength`

### 3.1. `seek(offset)` chỉ thay đổi vị trí; không tự ghi

~~~java
raf.seek(12L);                           // Đặt byte offset của lần I/O kế tiếp.
long position = raf.getFilePointer();   // 12
long size = raf.length();                // Kích thước thực của tệp.
~~~

Nếu gọi `seek(1000)` khi file chỉ dài 20 byte, **chưa có byte nào được thêm vào**. Chỉ khi thực sự **ghi** sau vị trí đó thì tệp mới có thể mở rộng. Phần byte nằm giữa dữ liệu cũ và vùng mới không nên được ứng dụng dựa vào nếu chưa tự định nghĩa/khởi tạo định dạng dữ liệu.

- Offset tính bằng **byte**, bắt đầu từ `0`; không phải thứ tự ký tự, dòng hoặc bản ghi.
- `seek(-1)` không hợp lệ, ném `IOException`.
- `read()` ở cuối tệp trả về **`-1`**; `readInt()`, `readLong()`, `readFully(...)` khi không còn đủ byte cần thiết ném **`EOFException`**.
- `read(byte[])` có thể đọc **ít byte hơn số lượng mong muốn**. Nếu cần đúng N byte hoặc báo lỗi EOF, dùng `readFully(buffer)`.

### 3.2. Đọc/ghi kiểu nguyên thủy và thứ tự byte

`RandomAccessFile` hỗ trợ `readInt`, `readLong`, `readBoolean`, `readDouble`... và `writeInt`, `writeLong`, `writeBoolean`, `writeDouble`...

~~~java
raf.seek(0);
raf.writeInt(0x01020304);  // Ghi đúng bốn byte: 01 02 03 04.
raf.seek(0);
int number = raf.readInt(); // 0x01020304.
~~~

Các phương thức `DataInput`/`DataOutput` đa byte sử dụng **big-endian**. Kích thước điển hình: `byte` = 1, `short` = 2, `int` = 4, `long` = 8 byte. Không coi `writeInt(1000)` là ghi chuỗi văn bản `"1000"` vào tệp.

**Chuỗi ký tự:** `writeUTF` ghi độ dài (2 byte) kèm nội dung theo **modified UTF-8** của giao thức `DataOutput`, nên phải đọc lại bằng `readUTF` theo đúng định dạng; đây không phải raw UTF-8 để tiện mở bằng text editor. Dữ liệu mã hóa trong một lần `writeUTF` bị giới hạn bởi độ dài được biểu diễn trong **2 byte không dấu** (tối đa 65.535 byte modified UTF-8). `writeChars` ghi từng UTF-16 code unit thành 2 byte, còn `writeBytes` bỏ phần cao của mỗi `char`; không nên dùng hai cách này để tùy tiện ghi tiếng Việt/Unicode vào tệp văn bản. Với định dạng văn bản UTF-8 chuẩn, hãy chủ động chuyển chuỗi bằng `StandardCharsets.UTF_8`, lưu độ dài hoặc dùng giao thức framing nhất quán khi đọc.

### 3.3. `setLength(newLength)`: cắt ngắn/mở rộng tệp

`setLength(0)` dùng để làm tệp rỗng; `setLength(8)` giữ đúng 8 byte đầu khi tệp đang dài hơn 8. Nếu tăng độ dài, **nội dung các byte mới chưa được đặc tả**, nên không coi đó là vùng giá trị đã được khởi tạo theo ý ứng dụng.

Khi `setLength(newLength)` trả về, con trỏ được **giới hạn không vượt quá `newLength`**; nếu con trỏ cũ lớn hơn độ dài mới thì con trỏ về đúng vị trí cuối mới. `setLength` yêu cầu mở tệp ở chế độ cho phép ghi và có thể ném `IOException` khi hệ thống tệp không thực hiện được.

### 3.4. Đọc, cập nhật, nối thêm: đừng nhầm với append mode

~~~java
raf.seek(0);            // Ghi đè từ đầu.
raf.writeInt(10);

raf.seek(4);            // Cập nhật một vùng ở offset 4.
raf.writeInt(20);

raf.seek(raf.length()); // Tự đưa con trỏ tới EOF để append.
raf.writeInt(30);
~~~

Đoạn này là minh họa trong một đối tượng `raf` đang mở cho ghi. **Không tồn tại một mode `"a"` hợp lệ** cho `RandomAccessFile`. Việc `seek(length())` rồi `write...` cũng **không tự là append nguyên tử** khi nhiều luồng hoặc tiến trình đồng thời sử dụng cùng tệp.

## 4. Quy tắc chọn chế độ theo nhu cầu

| Tình huống | Lựa chọn thường phù hợp | Vì sao |
|---|---|---|
| Kiểm tra header, đọc bản ghi tại offset đã biết | `"r"` | Chặn thao tác ghi nhầm qua instance |
| Tạo/cập nhật tệp thực hành, nội dung có thể tạo lại | `"rw"` | Đọc/ghi linh hoạt, chi phí đồng bộ từng lần thấp |
| Ghi đè vùng dữ liệu đã tồn tại; cần yêu cầu đồng bộ dữ liệu từng lần | `"rwd"` | Bảo đảm đồng bộ content khi có thiết bị local |
| Tạo bản ghi làm tăng kích thước/đổi metadata; cần yêu cầu đồng bộ chặt hơn | `"rws"` | Đồng bộ cả content và metadata |
| Nhiều thay đổi cần ghi theo từng đợt | `"rw"` + `getChannel().force(...)` | Tự chọn thời điểm yêu cầu đồng bộ, và cần thiết kế quy trình lỗi/crash riêng |

**Không có chế độ tốt nhất cho mọi bài toán.** Chọn theo yêu cầu độ bền, mô hình lỗi, đặc tính thiết bị và khả năng khôi phục. Nếu chỉ muốn đọc/ghi tuần tự văn bản, `Files.newBufferedReader`, `Files.newBufferedWriter` hoặc API stream có thể trực quan hơn.

## 5. Chương trình Java 17+ chạy được: ghi đè, append, truncate và mở `r`

Lưu chính xác tệp **`RandomAccessFileModesDemo.java`**:

~~~java
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;

public class RandomAccessFileModesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("raf-modes-demo-", ".bin");

        try {
            try (RandomAccessFile raf =
                         new RandomAccessFile(file.toFile(), "rw")) {
                raf.writeInt(10); // Offset 0..3
                raf.writeInt(20); // Offset 4..7
                System.out.println("initial: length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());

                raf.seek(4);
                raf.writeInt(99); // Thay giá trị int thứ hai, không đổi độ dài.
                System.out.println("update: length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());

                raf.seek(0);
                System.out.println("values: " + raf.readInt()
                        + ", " + raf.readInt());

                raf.seek(raf.length()); // Chuyển con trỏ đến EOF.
                raf.writeByte(7);       // Thêm 1 byte.
                System.out.println("append: length=" + raf.length());

                raf.setLength(8);       // Cắt bỏ byte vừa append.
                System.out.println("truncate: length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());
            }

            try (RandomAccessFile reader =
                         new RandomAccessFile(file.toFile(), "r")) {
                System.out.println("read-only: " + reader.readInt()
                        + ", " + reader.readInt());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp nguồn:

~~~bash
javac RandomAccessFileModesDemo.java
java RandomAccessFileModesDemo
~~~

**Stdout dự kiến khi tất cả I/O thành công:**

~~~text
initial: length=8, pointer=8
update: length=8, pointer=8
values: 10, 99
append: length=9
truncate: length=8, pointer=8
read-only: 10, 99
~~~

Diễn giải:

1. Hai lần `writeInt` ghi 8 byte; con trỏ kết thúc ở offset 8.
2. `seek(4)` đưa con trỏ về đầu số nguyên thứ hai; `writeInt(99)` ghi đè 4 byte, vẫn dài 8.
3. `seek(0)` và hai lần `readInt` khôi phục các số `10`, `99`.
4. `seek(length())` chọn offset 8; `writeByte(7)` thêm đúng một byte, tổng độ dài 9.
5. `setLength(8)` cắt một byte; con trỏ vừa ở offset 9 nay bị giới hạn về 8.
6. Đóng instance `"rw"` rồi mở `"r"` vẫn đọc được hai số; `"r"` không cho phép ghi.

`try-with-resources` bảo đảm `close()` được gọi khi thoát khối, kể cả khi có exception. Việc dùng tệp tạm riêng tránh ghi đè dữ liệu của người dùng. Nếu xảy ra lỗi I/O, chương trình có thể không in đủ những dòng trên và sẽ báo ngoại lệ; đây là hành vi cần được xử lý trong ứng dụng thật.

## 6. Dùng offset cho bản ghi kích thước cố định

Giả sử tệp lưu mỗi bản ghi:

~~~text
Record 0: [id: int (4 byte)] [balanceCents: long (8 byte)] = 12 byte
Record 1: [id: int (4 byte)] [balanceCents: long (8 byte)] = 12 byte
Record 2: [id: int (4 byte)] [balanceCents: long (8 byte)] = 12 byte
...
~~~

Byte offset của bản ghi `i` (**đếm từ 0**) là `i * 12`. Muốn đọc và sửa số dư bản ghi thứ ba (`i=2`), bắt đầu tại offset 24; trường `balanceCents` nằm ở offset 28.

Đoạn minh họa có thể đưa vào một class tiện ích; giả định file dùng đúng cấu trúc nhị phân nói trên:

~~~java
private static final int RECORD_SIZE =
        Integer.BYTES + Long.BYTES; // 12

static long readBalance(RandomAccessFile raf, long index)
        throws IOException {
    if (index < 0) {
        throw new IllegalArgumentException("index must be >= 0");
    }
    long offset = Math.multiplyExact(index, RECORD_SIZE);
    if (offset > raf.length() - RECORD_SIZE) {
        throw new java.io.EOFException("record does not exist");
    }
    raf.seek(offset + Integer.BYTES);
    return raf.readLong();
}

static void updateBalance(RandomAccessFile raf, long index, long cents)
        throws IOException {
    if (index < 0) {
        throw new IllegalArgumentException("index must be >= 0");
    }
    long offset = Math.multiplyExact(index, RECORD_SIZE);
    if (offset > raf.length() - RECORD_SIZE) {
        throw new java.io.EOFException("record does not exist");
    }
    raf.seek(offset + Integer.BYTES);
    raf.writeLong(cents);
}
~~~

**Lưu ý để dùng đúng:**

- Kiểm tra chỉ số âm; dùng `Math.multiplyExact` để tránh **tràn số** khi tính byte offset.
- Kiểm tra phạm vi trước khi update để không vô tình mở rộng tệp ở offset sai. Bản ghi được đánh số từ 0.
- `updateBalance` yêu cầu file mở ở `"rw"`, `"rwd"` hoặc `"rws"`; đối tượng chỉ đọc `"r"` sẽ không ghi được.
- Cần định nghĩa thống nhất layout (thứ tự trường, số byte, endianness, version), tránh dùng `String.length()` để tính offset chuỗi UTF-8 có độ dài biến thiên.
- Việc ghi `long` 8 byte **không phải một giao dịch** với các trường còn lại; cân nhắc checksum, log hoặc chiến lược cập nhật khi dữ liệu quan trọng.
- Đoạn trên không cung cấp khóa đồng thời; nếu nhiều tác nhân cập nhật cùng bản ghi, cần bổ sung đồng bộ phù hợp.

Nếu bản ghi có kích thước không cố định (ví dụ chuỗi UTF-8 dài ngắn khác nhau), `i * RECORD_SIZE` không dùng được; cần **index offset** hoặc định dạng có trường độ dài rõ ràng.

## 7. Đồng thời, `FileChannel`, khóa và rủi ro vận hành

### 7.1. Con trỏ là trạng thái chung trong cùng đối tượng

Trong một instance `RandomAccessFile`, thao tác `seek` rồi `read`/`write` là **một chuỗi hành động**, không phải thao tác nguyên tử ở cấp ứng dụng. Ví dụ:

~~~text
Thread A: seek(100)
Thread B: seek(200)
Thread A: writeInt(42)  // Có thể ghi từ offset 200 nếu không phối hợp.
~~~

Tránh dùng cùng một instance ở nhiều luồng mà không có kiểm soát truy cập. Với nhiều tiến trình, chỉ `synchronized` của một JVM không thể bảo vệ tiến trình khác. Có thể xem xét `FileChannel.lock()`/`tryLock()`, nhưng phải hiểu phạm vi lock, hỗ trợ và quy tắc OS; file lock **không phải** một giao dịch và một số hệ thống chỉ áp dụng theo cơ chế advisory.

### 7.2. `RandomAccessFile.getChannel()` chia sẻ vị trí

`getChannel()` trả về một `FileChannel` gắn với cùng tệp. **`channel.position()` và `raf.getFilePointer()` là cùng vị trí logic**: di chuyển một bên làm thay đổi vị trí bên kia. Thay đổi kích thước tệp qua bên nào cũng ảnh hưởng đến bên còn lại.

Vì vậy, nếu trộn `raf.seek(...)` và `channel.position(...)` trong một đoạn xử lý, phải có quy tắc kiểm soát con trỏ rõ ràng. Đóng `RandomAccessFile` cũng đóng channel liên kết; ngược lại, đóng channel của nó cũng khiến stream tương ứng bị đóng.

### 7.3. Quy tắc lỗi và bảo vệ dữ liệu

- Dùng `try-with-resources` để đóng handle; không giữ tệp mở vô hạn.
- Bắt `EOFException` riêng khi đọc record không đủ byte; phân biệt với `IOException` do quyền, thiết bị hoặc tệp hỏng.
- Dùng đường dẫn tin cậy và kiểm tra quyền trước khi cho người dùng chọn file để ghi. Mở `"rw"` trên tệp đang có dữ liệu có thể ghi đè ngay từ offset 0.
- Đừng dựa vào `"rws"`/`"rwd"` để tự xử lý **race condition**, ghi trùng, bản ghi dang dở, file format corruption hoặc ghi nhiều bước cần rollback.
- Nếu cần append đồng thời giữa nhiều luồng/tiến trình, thiết kế lock/protocol rõ ràng hoặc chọn API có bảo đảm append phù hợp thay vì tự coi `seek(length())` + `write` là nguyên tử.

## 8. Các nhầm lẫn phổ biến và cách sửa

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`RandomAccessFile` chỉ dùng để đọc ngẫu nhiên” | Nó có thể **đọc và ghi** nếu mở `rw/rws/rwd`. |
| “`rw` nghĩa là read/write và luôn append” | `rw` là quyền truy cập; vị trí ghi do **file pointer** quyết định. |
| “Mở `rw` sẽ xóa tệp cũ” | Không tự truncate; chỉ `setLength(0)` hoặc thao tác ghi theo offset mới thay đổi dữ liệu. |
| “`seek(1000)` làm tệp dài 1000 byte” | `seek` chỉ di chuyển pointer; tệp mở rộng khi ghi (hoặc gọi `setLength`). |
| “`rwd` đồng bộ cả file metadata” | `rwd` yêu cầu đồng bộ **content**; `rws` yêu cầu **content + metadata**. |
| “`rws` khiến nhiều lần ghi thành transaction” | Không có bảo đảm transaction/atomicity cho chuỗi lời gọi. |
| “`readInt` đọc số nguyên ở dạng chữ số ASCII” | `readInt` đọc **4 byte binary big-endian**. |
| “`read(byte[])` luôn trả về đủ buffer” | Có thể đọc thiếu; dùng `readFully` khi yêu cầu đúng kích thước. |
| “`writeUTF` ghi raw UTF-8 theo mọi chuẩn” | Đó là **modified UTF-8 có prefix 2 byte**, cần đọc bằng `readUTF` tương ứng. |
| “Lấy channel có con trỏ độc lập” | Channel và `RandomAccessFile` **chia sẻ vị trí**. |
| “`rwd/rws` đồng nghĩa dữ liệu trên network FS luôn an toàn sau crash” | Bảo đảm ghi xuống thiết bị được đặc tả cho **local storage**; remote FS không có bảo đảm tương tự. |

## 9. Tự kiểm tra

1. Mở tệp 100 byte bằng `"rw"`, gọi `seek(20)` rồi `writeInt(123)`. Kích thước mới? **100 byte** (ghi đè các byte 20–23); con trỏ ở **24**.
2. Mở tệp mới bằng `"rw"` rồi `writeLong(5L)`. Kích thước? **8 byte**, con trỏ ở **8**.
3. File đang dài 8 byte. Gọi `seek(100)` mà chưa ghi. `length()`? **8**, còn `getFilePointer()` là **100**.
4. Mở file chỉ với `"r"` rồi gọi `writeByte(1)`. Điều gì xảy ra? **`IOException`**.
5. Ở chế độ nào Java yêu cầu đồng bộ cả nội dung và metadata khi cập nhật? **`"rws"`**.
6. `"rwd"` khác `"rw"` chủ yếu ở đâu? **`"rwd"` yêu cầu đồng bộ nội dung trên từng cập nhật**, còn `"rw"` không yêu cầu như vậy.
7. Nếu sau một loạt lời gọi `write...` trong `"rw"` muốn yêu cầu đồng bộ content và metadata trước khi tiếp tục, dùng gì? **`raf.getChannel().force(true)`**.
8. Hai luồng dùng cùng một `RandomAccessFile`, mỗi luồng `seek` rồi `write`. Có tự an toàn không? **Không**; phải phối hợp để giữ tính đúng đắn của con trỏ và vùng ghi.

## 10. Tài liệu chính thức

- [Java SE 17 — RandomAccessFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/RandomAccessFile.html): bốn mode, `seek`, `setLength`, `getFilePointer`, `read`/`write`.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `force(boolean)`, `position`, file lock và các giới hạn đồng bộ.
- [Java SE 17 — DataInput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInput.html) và [DataOutput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutput.html): bố cục binary, big-endian, `readFully`, modified UTF-8.
