# Java 7 — Thuộc tính tệp: Thuộc tính mở rộng do người dùng định nghĩa

## 1. Thuộc tính mở rộng là gì và tại sao cần?

Một tệp trên hệ thống thường có **nội dung** và **metadata**. Nội dung có thể là văn bản, hình ảnh, dữ liệu nhị phân. Metadata cơ bản gồm kích thước, thời điểm sửa đổi và loại tệp. Nhưng có lúc ứng dụng muốn gắn thêm một cặp thông tin như:

- Nhãn nguồn nhập dữ liệu: `source=partner-a`.
- Trạng thái đã xử lý: `processed=true`.
- Phiên bản schema của tệp: `schema-version=2`.
- Ghi chú loại nội dung do ứng dụng xác định: `content-type=application/json`.

Nếu filesystem/provider hỗ trợ, một số dữ liệu như vậy có thể lưu thành **user-defined file attributes** (thuộc tính mở rộng do ứng dụng/người dùng định nghĩa), thường còn gọi là *extended attributes* hoặc *xattrs*.

Trong Java, API tương ứng là:

```java
java.nio.file.attribute.UserDefinedFileAttributeView
```

Đây là **tên interface**, không phải một câu lệnh Java độc lập. Interface này được đưa vào NIO.2 từ **Java 7**, tiếp tục có trong Java 17+ và vẫn là cơ chế chuẩn để truy cập một nhóm metadata mở rộng khi provider hỗ trợ.

Về bản chất, mỗi tệp có thể có **những cặp tên/giá trị**:

```text
File: report.csv
    Nội dung:        các byte CSV
    Basic metadata:  size, modified time, file type, ...
    User attributes: "app.stage"       -> [các byte UTF-8 của "validated"]
                     "app.schema"      -> [các byte UTF-8 của "v2"]
                     "app.checksum"    -> [các byte nhị phân]
```

**Quan trọng:** Cặp tên/giá trị trên chỉ là ví dụ minh họa. Không phải mọi FileSystem lưu user-defined attributes, không phải mọi tên đều hợp lệ và không có bảo đảm metadata này sẽ tồn tại sau khi sao chép, tải xuống, giải nén hoặc chuyển tệp sang filesystem khác.

Bài này tập trung vào cách **kiểm tra hỗ trợ, ghi, đọc, liệt kê, thay thế và xóa** những thuộc tính đó trong Java 17+, hiểu `ByteBuffer` và xử lý các giới hạn thực tế. Không nhầm với `BasicFileAttributes`, ACL hoặc POSIX permissions.

## 2. Khái niệm và mô hình dữ liệu

### 2.1. UserDefinedFileAttributeView là một attribute view tùy chọn

Các view thường gặp trong `java.nio.file.attribute`:

| Loại view | Vai trò | Có bắt buộc hỗ trợ không? |
| --- | --- | --- |
| `BasicFileAttributeView` | Kích thước, thời điểm, loại tệp | **Có** — mọi NIO FileSystem hỗ trợ basic |
| `PosixFileAttributeView` | Quyền owner/group/others, owner, group | Không |
| `DosFileAttributeView` | Các cờ hidden, readonly, system, archive | Không |
| `AclFileAttributeView` | ACL access-control entries | Không |
| `UserDefinedFileAttributeView` | Các cặp tên/giá trị do ứng dụng định nghĩa | **Không** |

Không nên suy đoán dựa trên tên OS: một máy Linux có thể mount một volume không hỗ trợ user attributes; một máy Windows có thể có provider hỗ trợ; ZIP provider hoặc remote filesystem có khả năng khác. Ngay trên cùng máy, những `FileStore` khác nhau có thể khác nhau.

### 2.2. Tên là String, giá trị là byte

Interface sử dụng:

- **Tên thuộc tính:** `String`, ví dụ `"app.note"` hoặc `"demo.note"`.
- **Giá trị thuộc tính:** dãy **byte** được đưa qua `ByteBuffer`; không có charset tự động và không phải một đối tượng Java được serialize tự động.
- **Phạm vi:** metadata gắn với một đối tượng file trong một filesystem/provider cụ thể.
- **Ý nghĩa:** do ứng dụng quy định; filesystem thường không diễn giải nội dung payload.

Ví dụ app lưu “Chào Java”:

```java
ByteBuffer bytes = StandardCharsets.UTF_8.encode("Chào Java");
view.write("app.note", bytes);
```

Đây là **snippet trong phương thức** có một biến `UserDefinedFileAttributeView view` không null, import `java.nio.ByteBuffer` và `java.nio.charset.StandardCharsets`, xử lý `IOException`. Nó mã hóa String thành byte UTF-8 rồi chuyển cho provider.

Nếu lưu số, JSON hoặc dữ liệu binary, **ứng dụng tự định nghĩa encoding/schema**. Không được tự xem mọi user attribute là văn bản có thể giải mã bằng UTF-8.

### 2.3. Không biến metadata thành cơ sở dữ liệu nghiệp vụ

Extended attributes phù hợp với metadata nhỏ gắn chặt với file trong một môi trường được kiểm soát. Chúng **không thay thế** database, permission/ACL, cơ chế transaction hoặc storage bền vững có thể đồng bộ giữa nhiều máy.

Đặc biệt không dùng user-defined attributes như nơi duy nhất chứa dữ liệu kinh doanh quan trọng, bí mật truy cập hoặc trạng thái buộc phải tồn tại sau khi copy/export, nếu chưa có cam kết cụ thể của toàn bộ hệ thống lưu trữ/backup.

## 3. Các phương thức của UserDefinedFileAttributeView

Trong Java SE 17, các phương thức chính:

| Phương thức | Ý nghĩa |
| --- | --- |
| `name()` | Trả tên của view, cố định là `"user"` |
| `list()` | Danh sách tên các user-defined attributes đang có |
| `size(String name)` | Kích thước **giá trị** của attribute theo byte, kiểu `int` |
| `read(String name, ByteBuffer dst)` | Đọc toàn bộ giá trị của attribute vào buffer đích |
| `write(String name, ByteBuffer src)` | Tạo hoặc **thay thế giá trị** attribute bằng các byte trong source buffer |
| `delete(String name)` | Xóa riêng attribute theo tên, **không xóa tệp** |

Các phương thức `list`, `size`, `read`, `write`, `delete` có thể ném `IOException`. Provider có thể giới hạn chiều dài tên, số attribute hoặc kích thước của mỗi giá trị.

Những chữ ký tiêu biểu:

```java
List<String> list() throws IOException;
int size(String name) throws IOException;
int read(String name, ByteBuffer dst) throws IOException;
int write(String name, ByteBuffer src) throws IOException;
void delete(String name) throws IOException;
```

Đây là **trích dẫn chữ ký rút gọn để học**, không phải những hàm cần tự định nghĩa trong chương trình. Một `UserDefinedFileAttributeView` là **giao diện tới metadata thực của file**; không phải một Map trong bộ nhớ. Các lời gọi có thể tương tác với file system và chịu tác động của quyền truy cập, symlink và tiến trình khác.

### 3.1. list() và size()

`view.list()` trả danh sách tên thuộc tính. Theo Javadoc, danh sách trả về là **unmodifiable**, và không có cam kết thứ tự cụ thể. Nếu cần in theo alphabet, sao chép thành `ArrayList` rồi sort.

`view.size(name)` trả **số byte**, không phải số ký tự hoặc UTF-16 code units. Nếu giá trị “Chào Java” dùng UTF-8, số byte có thể khác độ dài String vì chữ có dấu được mã hóa bằng nhiều byte.

Không nên dùng `size()` như một phương tiện lập tức chứng minh dữ liệu sẽ không thay đổi: tiến trình khác có thể sửa attribute giữa `size` và `read`.

### 3.2. write() là tạo hoặc thay thế

Khi gọi `view.write(name, buffer)`:

- Nếu tên chưa tồn tại, API tạo attribute mới nếu provider cho phép.
- Nếu tên đã tồn tại, giá trị **bị thay thế** bằng các byte mới; không phải append vào giá trị cũ.
- Hàm trả số byte đã chuyển, đồng thời cập nhật `ByteBuffer.position()`.
- Javadoc không bảo đảm một bước kiểm tra-tồn tại rồi tạo attribute mới là atomic với mọi hoạt động khác trên filesystem.

**Không xem `write` là transaction** hoặc cơ chế so-sánh-và-đổi (*compare-and-swap*) giữa nhiều tiến trình.

### 3.3. read() đọc toàn bộ giá trị vào buffer

`view.read(name, dst)` không tự cấp phát đủ vùng nhớ. Buffer phải có **`remaining()` đủ lớn** để nhận **toàn bộ** giá trị. Nếu không đủ, API ném `IOException` theo hợp đồng.

Cần dùng đúng ba bước:

1. Tạo buffer có capacity phù hợp.
2. Gọi `read`; vị trí buffer tăng theo số byte đã đọc.
3. Gọi `flip()` trước khi giải mã/đọc lại dữ liệu vừa ghi vào buffer.

### 3.4. delete() chỉ xóa metadata được chọn

`view.delete("app.note")` xóa **thuộc tính** theo tên, không xóa file hay nội dung file. Nếu thuộc tính đó không tồn tại, API có thể ném `IOException`; không ngầm giả định lệnh xóa luôn idempotent.

Với workflow xóa theo danh sách, không tự xóa mọi attribute mà ứng dụng không sở hữu — có thể có metadata thuộc về phần mềm khác.

## 4. Kiểm tra hỗ trợ trước khi truy cập

Trước khi ghi một user attribute, nên có bước **feature detection**, nhất là với ứng dụng đa nền tảng.

### 4.1. Cấp FileSystem: tên view `user`

```java
Path file = Path.of("data", "report.csv");
boolean fileSystemOffersUser = file.getFileSystem()
        .supportedFileAttributeViews().contains("user");
```

Đây là snippet trong phương thức với `Path file`. `supportedFileAttributeViews()` trả tập tên các view mà `FileSystem` công bố hỗ trợ. Sự có mặt của `"user"` là **tín hiệu cấp filesystem**, không phải bảo đảm rằng mọi mount/volume bên dưới đều có cùng khả năng.

### 4.2. Cấp FileStore: có hỗ trợ cho nơi chứa file không?

```java
FileStore store = Files.getFileStore(file);

boolean storeOffersUser =
        store.supportsFileAttributeView(UserDefinedFileAttributeView.class);
```

Đây là snippet trong phương thức có imports `Files`, `FileStore`, `UserDefinedFileAttributeView` và xử lý `IOException`. File được giả định **đã tồn tại**. Nếu file không tồn tại hoặc không truy cập được, lấy FileStore có thể lỗi.

Overload tương đương trong trường hợp dùng tên view:

```java
boolean supportedByName = store.supportsFileAttributeView("user");
```

Đây là snippet có biến `FileStore store`. Provider có thể công bố khả năng khác nhau trên các FileStore. Javadoc cũng lưu ý default provider **không bảo đảm kết quả hoàn toàn chính xác** với một số file store **không phải local storage**. Vì vậy vẫn phải xử lý lỗi ở lúc đọc/ghi thật.

### 4.3. Cấp Path: lấy typed view có null hay không?

```java
UserDefinedFileAttributeView view = Files.getFileAttributeView(
        file,
        UserDefinedFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);

if (view == null) {
    System.out.println("User attributes are unsupported here");
}
```

Đây là snippet trong phương thức với import `java.nio.file.LinkOption`, `Files` và `UserDefinedFileAttributeView`. Khi view type không khả dụng, `Files.getFileAttributeView` trả `null`. Không gọi `view.list()` hay `view.write()` khi nó chưa được kiểm tra.

### 4.4. Có bắt buộc phải gọi cả ba tầng?

Không. Ba tầng có giá trị để **giải thích và chẩn đoán** khả năng, nhưng nếu một chương trình chỉ cần kiểm tra view trên Path cụ thể, có thể gọi `Files.getFileAttributeView(...)` rồi xử lý `null`. Khi quyết định hỗ trợ nghiệp vụ phụ thuộc file store, kiểm tra thêm `store.supportsFileAttributeView(...)`.

Đừng biến ba phép thăm dò thành câu khẳng định “mọi thao tác sau đó chắc chắn thành công”. **Capability khác authorization và khác I/O success**. Ngay cả khi supported, file có thể bị xóa, provider mất kết nối hoặc người dùng không được phép sửa metadata.

## 5. Java 17+: chương trình đầy đủ có kiểm tra và dọn file

Chương trình sau tạo **tệp tạm riêng** rồi thử các thao tác quan trọng: kiểm tra view, ghi UTF-8, `size`, `read`, `list`, dynamic access, thay thế, xóa. Nó không chỉnh sửa file thật của người dùng.

Tạo tệp **`UserAttributesDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.UserDefinedFileAttributeView;
import java.util.Arrays;

public class UserAttributesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("user-attributes-demo-", ".txt");
        try {
            boolean fsOffersUser = file.getFileSystem()
                    .supportedFileAttributeViews().contains("user");
            FileStore store = Files.getFileStore(file);
            boolean storeOffersUser = store.supportsFileAttributeView(
                    UserDefinedFileAttributeView.class);
            UserDefinedFileAttributeView view = Files.getFileAttributeView(
                    file, UserDefinedFileAttributeView.class,
                    LinkOption.NOFOLLOW_LINKS);

            boolean supported = fsOffersUser && storeOffersUser && view != null;
            System.out.println("user view available = " + supported);
            if (!supported) {
                System.out.println("user metadata demo = skipped");
                return;
            }

            String name = "demo.note";
            String message = "Chào Java";
            ByteBuffer source = StandardCharsets.UTF_8.encode(message);
            int bytesExpected = source.remaining();
            int written = view.write(name, source);
            System.out.println("written equals expected = " +
                    (written == bytesExpected));
            System.out.println("source buffer consumed = " +
                    !source.hasRemaining());

            int size = view.size(name);
            ByteBuffer destination = ByteBuffer.allocate(size);
            int read = view.read(name, destination);
            destination.flip();
            String restored = StandardCharsets.UTF_8.decode(destination).toString();
            System.out.println("size matches read = " + (size == read));
            System.out.println("decoded equals original = " +
                    message.equals(restored));
            System.out.println("listed = " + view.list().contains(name));

            byte[] raw = (byte[]) Files.getAttribute(file, "user:" + name);
            System.out.println("dynamic bytes match = " +
                    Arrays.equals(raw, message.getBytes(StandardCharsets.UTF_8)));

            view.write(name, StandardCharsets.UTF_8.encode("updated"));
            System.out.println("replaced length = " + view.size(name));
            view.delete(name);
            System.out.println("deleted = " + !view.list().contains(name));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac --release 17 UserAttributesDemo.java
java UserAttributesDemo
```

**Stdout thực tế khi chạy trên máy Windows có user-defined attribute view (đã kiểm thử JDK 24):**

```text
user view available = true
written equals expected = true
source buffer consumed = true
size matches read = true
decoded equals original = true
listed = true
dynamic bytes match = true
replaced length = 7
deleted = true
```

**Nếu FileSystem hoặc FileStore không hỗ trợ user view, hoặc typed view bằng null**, nhánh đầu tiên sẽ in:

```text
user view available = false
user metadata demo = skipped
```

Vì file system tùy nền tảng, **không khẳng định mọi máy đều in chín dòng đầu**. Khi API báo có hỗ trợ nhưng quá trình I/O thực thất bại (chẳng hạn không có quyền hoặc provider lỗi), chương trình có thể ném `IOException`; nó không giả vờ “thành công” hay tự đổi thành nhánh unsupported.

### 5.1. Vì sao code chạy được với Java 17?

- `UserDefinedFileAttributeView`, `Files.getFileAttributeView` và `Files.getAttribute` có từ NIO.2/Java 7.
- `Path` và `FileStore` vẫn là API chính thức của Java 17+.
- Factory `Files.createTempFile` có từ Java 7.
- `StandardCharsets.UTF_8` có từ Java 7, được dùng rõ ràng.
- Code không phụ thuộc `Path.of` nên vẫn biên dịch dưới `--release 17` như công bố.

### 5.2. Tại sao cần `finally`?

Ví dụ tạo một file tạm để học; `finally` gọi `Files.deleteIfExists(file)` cả khi gặp lỗi. Thao tác này cũng có thể thất bại nếu file bị khóa hoặc provider có lỗi I/O. Trong ứng dụng thật, cần chính sách cleanup phù hợp và không dùng code demo để xóa dữ liệu do người dùng sở hữu.

### 5.3. Vì sao danh sách attribute không được in nguyên?

`view.list()` có thể trả những tên khác nhau tùy provider, nên chương trình chỉ kiểm tra `contains(name)` để có output ổn định. Khi triển khai công cụ liệt kê metadata, bạn có thể in tên nhưng nên cân nhắc khả năng tên/giá trị chứa thông tin nội bộ hoặc nhạy cảm.

## 6. Hiểu ByteBuffer: position, limit, remaining, flip

Phần dễ nhầm nhất không phải `write` mà là vòng đời của `ByteBuffer`.

### 6.1. Khi ghi

```java
String text = "Xin chào";
ByteBuffer source = StandardCharsets.UTF_8.encode(text);

int expected = source.remaining();
int written = view.write("app.note", source);

System.out.println(written == expected);
```

Đây là **snippet trong phương thức** với biến `UserDefinedFileAttributeView view` đã kiểm tra và xử lý `IOException`. Buffer có dãy byte UTF-8 từ `position` đến `limit`. `view.write` lấy những byte còn lại, cập nhật `position` theo số byte chuyển và trả số byte đã ghi.

**Không tính số byte bằng `text.length()`.** Trong Java, `String.length()` đo số UTF-16 code units; chuỗi có tiếng Việt hoặc emoji thường có số byte UTF-8 khác.

### 6.2. Khi đọc

```java
int size = view.size("app.note");

ByteBuffer destination = ByteBuffer.allocate(size);
int transferred = view.read("app.note", destination);
destination.flip();

String result = StandardCharsets.UTF_8.decode(destination).toString();
```

Đây là snippet trong phương thức có `view` hợp lệ; cần xử lý `IOException`. `size` là số byte, `ByteBuffer.allocate(size)` tạo vùng nhớ, `read` ghi bytes và tăng `position`, rồi `flip` đưa buffer về chế độ đọc.

Nếu quên `flip()`, giải mã có thể nhìn thấy số byte còn lại bằng 0 và cho chuỗi rỗng hoặc kết quả sai. Đừng dùng `buffer.array()` mà không xét `position`/`limit` và việc buffer có backing array hay không.

### 6.3. Không nhầm with InputStream/OutputStream

Các giá trị user-defined attributes được đọc/ghi bằng **ByteBuffer**, không tự động cung cấp `InputStream` / `OutputStream` để stream một attribute khổng lồ như file content. Interface cũng không dành cho giá trị có kích thước lớn hơn `Integer.MAX_VALUE`, và thực tế nhiều filesystem áp giới hạn thấp hơn rất nhiều.

Nếu dữ liệu cần hàng megabyte, giao dịch hoặc streaming, nên lưu thành file/DB/object storage có schema rõ ràng thay vì cố nhét vào một extended attribute.

## 7. UTF-8 và dữ liệu nhị phân: encoding do ứng dụng quyết định

Javadoc gọi giá trị user-defined attribute là **opaque content**: provider không biết nó là tiếng Việt, JSON, checksum hay binary. Vì vậy chương trình phải chọn cách encode/decode nhất quán.

### 7.1. Văn bản

```java
String value = "Đã kiểm tra";
view.write("app.status", StandardCharsets.UTF_8.encode(value));
```

Đây là snippet trong phương thức có view, import `StandardCharsets` và xử lý IOException. Đầu đọc cũng phải biết nó là UTF-8. Không dùng charset mặc định của môi trường một cách ngầm định khi metadata được trao đổi giữa các máy hoặc được đọc bởi nhiều chương trình.

### 7.2. Số hoặc cấu trúc phức tạp

Một lựa chọn đơn giản là lưu số theo quy ước decimal UTF-8:

```java
int version = 2;
view.write("app.schema-version",
        StandardCharsets.UTF_8.encode(Integer.toString(version)));
```

Đây là snippet minh họa. Khi đọc, ứng dụng kiểm tra chuỗi và parse với xử lý lỗi, ví dụ `Integer.parseInt(text)` có thể ném `NumberFormatException` nếu metadata bị hỏng.

Đối với JSON, hãy dùng thư viện serializer/validator thay vì tự nối JSON khi giá trị chứa dữ liệu tùy ý. Với dữ liệu nhị phân, dùng `ByteBuffer.wrap(bytes)` và kiểm tra kích thước/format; không ép mọi payload vào String.

### 7.3. Giải mã UTF-8 nghiêm ngặt khi cần

`StandardCharsets.UTF_8.decode(buffer)` dùng hành vi decoder tiện lợi; nếu dữ liệu bị lỗi byte, nó có thể thay thế ký tự không hợp lệ. Khi metadata bắt buộc đúng UTF-8, dùng decoder với `CodingErrorAction.REPORT`:

```java
String strictText = StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(buffer)
        .toString();
```

Đây là snippet trong phương thức có import `java.nio.charset.CodingErrorAction`, `StandardCharsets`, biến `ByteBuffer buffer` đang ở chế độ đọc, và xử lý `CharacterCodingException`. Không tự coi dữ liệu trong extended attribute là đáng tin chỉ vì được gắn vào file.

## 8. Đọc/ghi động bằng Files.getAttribute và Files.setAttribute

Nếu không cần cầm một typed view instance, Java NIO.2 cũng hỗ trợ cú pháp **`view-name:attribute-name`**.

Ví dụ:

```java
byte[] original = "ready".getBytes(StandardCharsets.UTF_8);

Files.setAttribute(file, "user:app.state", original);

byte[] restored = (byte[]) Files.getAttribute(
        file, "user:app.state");

System.out.println(Arrays.equals(original, restored));
```

Đây là snippet Java trong phương thức có `Path file`, import `Files`, `StandardCharsets`, `Arrays` và xử lý IOException. API trả `byte[]` khi đọc một user-defined attribute qua `Files.getAttribute`, đúng theo Javadoc của `UserDefinedFileAttributeView`.

**Cú pháp cần phân biệt:**

- Tên *view* là `"user"`.
- Tên *attribute* ở đây là `"app.state"`.
- Toàn bộ chuỗi dynamic là `"user:app.state"`.

Không dùng `"basic:app.state"` hoặc `"posix:app.state"` rồi mong provider tự tìm user metadata. Đồng thời tên trong Java API và tên trong công cụ OS-native có thể khác cách trình bày/namespace; không tự nối thêm tiền tố OS khi chưa xác nhận hợp đồng provider.

### 8.1. ByteBuffer và byte[] khi setAttribute

`Files.setAttribute(path, "user:name", value)` cho user view có thể nhận `byte[]` hoặc `ByteBuffer` theo hợp đồng API. Typed view dùng `view.write(name, ByteBuffer)`. Đừng gửi String trực tiếp vào `setAttribute` rồi mặc định Java sẽ encode tự động.

### 8.2. Khi nào chọn typed view, khi nào chọn dynamic string?

**Typed view** phù hợp với code nghiệp vụ có thao tác list/size/read/write/delete nhiều lần, muốn IDE/compiler hỗ trợ. **Dynamic access** phù hợp với công cụ tổng quát thao tác một attribute theo tên. Cả hai đều cần kiểm tra hỗ trợ, xử lý lỗi I/O và xem xét namespace/tên hợp lệ.

Dynamic API không có nghĩa metadata trở thành portable. Nó chỉ là cách gọi khác của cùng cơ chế provider.

## 9. Giới hạn kích thước, tên và lỗi thiếu buffer

### 9.1. Không cấp phát buffer vô hạn theo metadata

Một cách đọc thường gặp là:

```java
int size = view.size(name);
ByteBuffer buffer = ByteBuffer.allocate(size);
view.read(name, buffer);
buffer.flip();
```

Đây là snippet trong phương thức có `view` và `String name`. Nó hoạt động cho trường hợp dữ liệu nhỏ, ổn định nhưng **chưa đủ cho đầu vào không tin cậy**. Nếu attribute có kích thước lớn, `allocate(size)` có thể dùng quá nhiều bộ nhớ. Javadoc còn có `ArithmeticException` nếu kích thước vượt `Integer.MAX_VALUE`.

Cần đặt giới hạn phù hợp với nghiệp vụ, chẳng hạn **4 KiB** cho một nhãn metadata nhỏ:

```java
static byte[] readSmallAttribute(
        UserDefinedFileAttributeView view, String name)
        throws IOException {
    final int maxBytes = 4096;
    int size = view.size(name);
    if (size > maxBytes) {
        throw new IOException("Attribute exceeds application limit");
    }

    ByteBuffer buffer = ByteBuffer.allocate(size);
    int count = view.read(name, buffer);
    buffer.flip();

    byte[] bytes = new byte[count];
    buffer.get(bytes);
    return bytes;
}
```

Đây là phương thức minh họa, cần import `UserDefinedFileAttributeView`, `ByteBuffer` và `IOException`. `4096` là **giới hạn do ví dụ đặt ra**, không phải kích thước tối đa chuẩn của NIO. Provider có thể giới hạn thấp hơn hoặc cao hơn.

### 9.2. Race giữa size và read

Trong môi trường có nhiều tiến trình, giá trị của `name` có thể thay đổi sau `view.size(name)` nhưng trước `view.read(name, dst)`. Nếu attribute tăng kích thước, buffer không đủ; `read` có thể ném `IOException`. Nếu giá trị giảm, số byte thực đọc có thể nhỏ hơn size ban đầu.

Điều này có nghĩa:

- Không dựa vào `size` làm “khóa” giá trị.
- Kiểm tra số byte thực đọc mà `read` trả về.
- Có chính sách retry **có giới hạn** khi nghiệp vụ cho phép và lỗi được xác định rõ.
- Nếu cần snapshot hoặc compare-and-swap, thiết kế một giao thức đồng bộ/storage khác; không tự suy ra tính nguyên tử từ hai lời gọi `size/read`.

### 9.3. Nếu buffer quá nhỏ

Theo Javadoc, `view.read` **phải thất bại** nếu số byte còn lại của destination buffer không đủ chứa toàn bộ giá trị. Nó có thể ném `IOException` thay vì “đọc một phần tùy ý rồi trả số byte”.

Điều đó khác với API stream/file channel, vốn thường cho phép xử lý từng chunk. User-defined attributes không dành cho streaming dữ liệu lớn.

### 9.4. Giới hạn tên và độ dài là provider-specific

Tên thuộc tính có thể chịu quy tắc giới hạn ký tự, độ dài, namespace, cấm một số ký tự hoặc chính sách ACL. Giá trị có thể chịu giới hạn số bytes. Không thể giả định `name` dài 1000 ký tự hoặc payload 10 MB chạy trên mọi filesystem.

Hãy giữ tên **ngắn, ổn định, có prefix ứng dụng để tránh va chạm**, chẳng hạn `"myapp.stage"`. Prefix ở đây là quy ước nghiệp vụ trong tên Java; không tự giả định mọi OS dùng tiền tố `user.` theo cùng cách.

## 10. Đặt tên và version hóa schema cho metadata

Không có một schema chung mà Java áp đặt cho user-defined attributes. Nếu ứng dụng dùng lâu dài, hãy quy định:

1. **Namespace của ứng dụng:** ví dụ `"myapp.source"`, `"myapp.version"`.
2. **Kiểu giá trị:** UTF-8 text, số decimal, JSON hoặc bytes nhị phân.
3. **Version:** khi cấu trúc thay đổi, có tên mới hoặc trường version để reader biết cách parse.
4. **Ý nghĩa khi không có attribute:** phải khác với giá trị rỗng nếu nghiệp vụ cần phân biệt.
5. **Giới hạn kích thước:** bảo vệ memory và khả năng copy sang filesystem khác.
6. **Ownership:** ứng dụng nào được phép ghi/xóa thuộc tính; không chạm vào namespace của chương trình khác.
7. **Mức độ quan trọng:** metadata chỉ là cache/tối ưu hóa hay là dữ liệu nguồn chính cần lưu ở nơi khác.

Một kiểu thiết kế ví dụ:

```text
myapp.schema       = "2"              (UTF-8 decimal)
myapp.processed    = "true"           (UTF-8 text)
myapp.source       = "upload-service" (UTF-8 text)
myapp.payload-hash = [binary bytes]   (định dạng do app quy định)
```

**Không** dựa vào thứ tự `view.list()` để suy luận quan hệ giữa các thuộc tính. Cần đọc theo **tên** và kiểm tra schema từng giá trị.

### 10.1. Khi attribute không tồn tại

Có ít nhất ba trạng thái cần phân biệt:

- **Không hỗ trợ user view** trên filesystem/file store.
- **Có hỗ trợ, nhưng tên attribute chưa tồn tại.**
- **Attribute tồn tại nhưng giá trị rỗng** (0 byte), nếu provider cho phép.

Đừng gộp các trường hợp vào một giá trị `null` rồi tự cho rằng ý nghĩa giống nhau. Nếu `size`, `read` hoặc `delete` được gọi với tên chưa tồn tại, `IOException` có thể là kết quả đúng theo đặc tả.

## 11. Copy, move, backup và đồng bộ: metadata không tự đi theo tệp

Vì user-defined attributes phụ thuộc provider, việc **sao chép nội dung file** không tự hứa mọi thuộc tính mở rộng sẽ đi theo file đích.

### 11.1. Files.copy và COPY_ATTRIBUTES

`Files.copy(source, target, StandardCopyOption.COPY_ATTRIBUTES)` yêu cầu sao chép những thuộc tính file được hỗ trợ theo hợp đồng. Một số thuộc tính ngoài basic có thể được sao chép tùy implementation; không có bảo đảm chung rằng **mọi user-defined attributes** đều được giữ nguyên giữa các provider/volume.

```java
Files.copy(source, destination,
        StandardCopyOption.COPY_ATTRIBUTES);
```

Đây là snippet trong phương thức có `Path source`, `Path destination`, import `Files`, `StandardCopyOption` và xử lý `IOException`. Không dùng bản này như một “bản sao metadata đầy đủ chắc chắn”. Hãy kiểm tra sau copy trên filesystem đích.

### 11.2. Các thao tác thường làm mất extended attributes

Các thao tác truyền file qua HTTP, object storage, email attachment, ZIP, chương trình đồng bộ hoặc copy sang volume khác **có thể chỉ chuyển nội dung byte và một phần metadata chuẩn**. Thuộc tính mở rộng có thể bị mất, đổi namespace hoặc không được đối tác hỗ trợ.

Vì vậy nếu một thuộc tính là **yêu cầu bắt buộc**, cần:

- Kiểm tra đường đi dữ liệu từ nguồn đến đích có lưu thuộc tính đó không.
- Test đọc lại thuộc tính trên hệ thống đích sau copy/move/restore.
- Có phương án metadata **sidecar** (file JSON bên cạnh), manifest hoặc database.
- Không biến user-defined attribute thành **bằng chứng bảo mật không thể giả mạo**.

### 11.3. Chuyển giữa các filesystem

Một `Path` trong ZIP provider hoặc remote filesystem có thể không hỗ trợ `UserDefinedFileAttributeView`. Nếu source có `user` nhưng destination không có, không thể yêu cầu destination tự lưu tên/giá trị tương tự. Với dữ liệu quan trọng, **di chuyển phải có chính sách fallback hoặc từ chối thao tác**; không âm thầm bỏ metadata mà nghiệp vụ đòi hỏi.

## 12. Symbolic link và thuộc tính của file nào?

Mặc định, nhiều phương thức attribute của NIO **theo symbolic link** đến tệp đích. Nếu muốn thao tác metadata của **chính link entry**, dùng `LinkOption.NOFOLLOW_LINKS` khi lấy view:

```java
UserDefinedFileAttributeView linkView = Files.getFileAttributeView(
        linkPath,
        UserDefinedFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);
```

Đây là snippet trong phương thức có `Path linkPath`, import `Files` và `LinkOption`. Nếu filesystem không hỗ trợ user attributes trên symbolic link, view có thể không dùng được hoặc thao tác sau đó thất bại. Không giả định `NOFOLLOW_LINKS` tạo được metadata trên symlink ở mọi provider.

**Lưu ý bảo mật:** Một tiến trình khác có thể thay link hoặc file giữa bước kiểm tra và bước ghi attribute. Điều đó là một dạng *time-of-check/time-of-use* (TOCTOU) race. `NOFOLLOW_LINKS` quy định chính sách theo link cho **lời gọi được cung cấp option**, không tự khóa tên file hoặc bảo đảm mọi bước kế tiếp truy cập cùng đối tượng.

Nếu ứng dụng dùng user attributes để gắn thông tin nhạy cảm, cần kiểm soát quyền đường dẫn, directory handle, symlink policy, owner của file và quy trình đồng thời ở mức hệ thống.

## 13. Bảo mật, quyền truy cập và tính tin cậy

### 13.1. “Có view” không nghĩa “được quyền dùng”

`FileStore.supportsFileAttributeView(...) == true` hoặc `view != null` chỉ là **khả năng kỹ thuật**. Việc gọi `list`, `read`, `write` hoặc `delete` vẫn có thể thất bại do:

- ACL hoặc permission của file/parent directory.
- File store read-only.
- File bị xóa, thay thế hoặc chuyển volume.
- Provider/network mất kết nối.
- Giới hạn kích thước/tên thuộc tính.
- Thao tác bị giới hạn bởi chính sách của hệ thống hoặc runtime.

Luôn xử lý `IOException` và các ngoại lệ đầu vào/programming error theo đúng ý nghĩa, không dùng `catch (Exception ignored)` để biến mọi lỗi thành “không có thuộc tính”.

### 13.2. Không lưu bí mật ở extended attribute nếu không có threat model

Metadata mở rộng **không phải kho bí mật**. Khả năng đọc của người dùng/chương trình khác, backup, việc copy, hay công cụ hệ điều hành đều tùy filesystem. Không coi giá trị `"approved=true"` là một authorization token bất khả giả mạo; một actor có quyền sửa xattr có thể thay đổi nó.

Nếu cần lưu secret, credentials hay token, hãy dùng storage và key management được thiết kế cho mục đích đó với chính sách bảo mật phù hợp.

### 13.3. Không thực hiện thay đổi tùy ý lên file người dùng

Ví dụ demo chỉ sửa thuộc tính của file tạm do chương trình tạo. Trên file thật, có thể có thuộc tính của phần mềm khác. Đừng lặp qua `view.list()` rồi xóa tất cả để “dọn metadata” nếu không chứng minh được ownership của từng tên.

Một ứng dụng chỉ nên thao tác các tên nằm trong schema/namespace của chính nó và xử lý rõ chuyện tên được tạo bởi actor khác.

## 14. Concurrency và tính nguyên tử của extended attributes

### 14.1. Thay thế giá trị và cạnh tranh writer

Giả sử hai tiến trình cùng chạy:

```java
view.write("myapp.state", StandardCharsets.UTF_8.encode("A"));
view.write("myapp.state", StandardCharsets.UTF_8.encode("B"));
```

Đây là hai lời gọi minh họa. Kết quả cuối phụ thuộc thứ tự thực tế, và API không cung cấp phiên bản, điều kiện “chỉ ghi nếu giá trị đang bằng X”, hay giao dịch kết hợp nhiều tên thuộc tính.

Nếu cần trạng thái chuyển tiếp có kiểm soát hoặc *exactly-once processing*, hãy dùng cơ chế lưu trữ hỗ trợ concurrency control hoặc giao thức khóa/ownership đáng tin cậy.

### 14.2. list(), size(), read() không tạo snapshot

Một vòng duyệt:

```java
for (String name : view.list()) {
    int size = view.size(name);
    // Giá trị có thể bị xóa/thay đổi trước khi read(name,...).
}
```

Đây là snippet minh họa trong phương thức có view. Vì `list`, `size` và `read` là những lời gọi riêng, chúng không hứa một snapshot atomic của metadata. Hãy xử lý trường hợp giá trị biến mất hoặc thay đổi giữa các bước.

### 14.3. Ghi nhiều thuộc tính không phải transaction

Một chương trình ghi `myapp.state` và `myapp.timestamp` ở hai lệnh riêng có thể để lại trạng thái không đồng bộ nếu lệnh thứ hai lỗi. Đừng thiết kế tính nhất quán nghiệp vụ quan trọng dựa vào giả định “hai lời gọi write sẽ commit cùng lúc”.

Nếu metadata có nhiều trường cần nhất quán, cân nhắc encode một cấu trúc được version hóa thành một attribute nhỏ; nhưng **việc ghi một attribute vẫn phụ thuộc provider** và không thay thế transaction/crash durability theo hợp đồng tổng quát.

## 15. Hiệu năng, số lượng và kích thước thuộc tính

- `view.size`, `view.list` và `view.read` có thể phát sinh I/O hoặc truy cập metadata, đặc biệt trên remote filesystem.
- Tên và giá trị có giới hạn theo provider; không hard-code một mức tối đa cho mọi file system.
- Lưu nhiều thuộc tính cho hàng triệu file có thể làm tăng chi phí backup/sync hoặc làm phức tạp quản lý schema.
- `view.list()` có thể trả danh sách lớn; nếu chỉ cần một tên, hãy truy cập trực tiếp và bắt lỗi phù hợp thay vì liệt kê tất cả chỉ để tìm.
- Không dùng extended attribute như blob store cho nội dung file lớn.
- Nếu app phải hoạt động khi provider không hỗ trợ, thiết kế fallback ngay từ đầu, thay vì để lỗi xuất hiện ở production.

### 15.1. Quy tắc đặt giới hạn ứng dụng

Với một nhãn text đơn, giới hạn 512 hoặc 4096 byte có thể phù hợp; con số là **quy tắc của ứng dụng**, không phải API. Nên kiểm tra:

- Payload được encode thành bao nhiêu **byte**.
- Định dạng có hợp lệ, đúng version và độ dài tối đa không.
- Khi đọc, có phân biệt attribute không tồn tại với dữ liệu rỗng không.
- Có chống việc allocate buffer theo giá trị size bất thường không.
- Có kế hoạch cho attribute bị thay đổi giữa size/read không.

## 16. Phân biệt user-defined attributes với các cách lưu metadata khác

| Cách lưu | Điểm mạnh | Hạn chế chính |
| --- | --- | --- |
| User-defined file attributes | Gắn metadata nhỏ trực tiếp với đối tượng file khi provider hỗ trợ | Không portable tuyệt đối, thiếu transaction, giới hạn size và khả năng backup/copy |
| Basic/Posix/Dos/ACL attributes | Semantics chuẩn theo nhóm metadata của filesystem | Chỉ có các trường được định nghĩa, nhiều view tùy chọn |
| File JSON sidecar | Dễ xuất, đồng bộ, review và giữ schema | Phải quản lý quan hệ giữa file chính và file bên cạnh |
| Database | Có thể quản lý version, index, query, transaction/concurrency | Cần cơ sở hạ tầng và liên kết với file |
| Manifest trong archive | Có thể giữ metadata khi đóng gói nhiều file | Cần định dạng và quy trình cập nhật riêng |
| Metadata của object-storage API | Theo hợp đồng của storage provider | Không thể giả định giống NIO filesystem xattrs |

**Gợi ý lựa chọn:** Nếu metadata chỉ tối ưu hóa cho một chương trình chạy trên file system được kiểm soát, user-defined attributes có thể hợp lý. Nếu metadata phải sống qua tải lên, gửi qua mạng, đồng bộ đa nền tảng hoặc lưu trữ lâu dài, một schema portable bên ngoài hoặc trong nội dung file thường đáng tin hơn.

## 17. Các lỗi thường gặp

**Lỗi 1 — Giả định user-defined attributes có trên mọi filesystem.** Sai. Đây là view tùy chọn.

**Lỗi 2 — Chỉ dựa vào tên OS để suy capability.** Sai. Hỗ trợ tùy provider và FileStore.

**Lỗi 3 — Không kiểm tra null của Files.getFileAttributeView.** Có thể gây NullPointerException khi view không có.

**Lỗi 4 — Nghĩ giá trị là String.** API nhận/đưa **byte** bằng ByteBuffer; charset/schema do ứng dụng quản lý.

**Lỗi 5 — Lấy text.length() làm kích thước buffer.** Sai với Unicode; dùng số byte thực của payload.

**Lỗi 6 — Đọc vào ByteBuffer nhưng quên flip().** Dẫn đến giải mã dữ liệu không đúng hoặc trống.

**Lỗi 7 — ByteBuffer thiếu remaining và hy vọng read đọc một phần.** Không; read attribute yêu cầu đủ dung lượng và có thể ném IOException.

**Lỗi 8 — Dùng ByteBuffer.array() mà không xét position/limit.** Có thể lấy byte ngoài phạm vi hoặc buffer không có backing array.

**Lỗi 9 — Không giới hạn size trước khi cấp phát RAM.** Dữ liệu không tin cậy có thể tạo rủi ro bộ nhớ.

**Lỗi 10 — Nghĩ write(name, src) sẽ append.** Không. Attribute cũ bị thay thế bằng giá trị mới.

**Lỗi 11 — Nghĩ delete(name) xóa nội dung file.** Không. Nó xóa riêng attribute theo tên.

**Lỗi 12 — Tự đoán tên attribute trên OS từ tên Java.** Quy tắc namespace/encoding có thể khác giữa provider và công cụ native.

**Lỗi 13 — Tự tin metadata được copy sang mọi máy.** Không có bảo đảm chung; cần test/cơ chế fallback.

**Lỗi 14 — Dùng user attributes làm kho bí mật hoặc authorization token.** Không có cam kết bảo mật mặc định như vậy.

**Lỗi 15 — Coi view có sẵn nghĩa là có quyền sửa.** Permission/ACL/readonly có thể chặn.

**Lỗi 16 — Coi size + read là một snapshot atomic.** Không. Giá trị có thể đổi giữa hai lời gọi.

**Lỗi 17 — Coi nhiều write attributes là transaction.** Không có bảo đảm all-or-nothing.

**Lỗi 18 — Gắn metadata lên symlink nhưng quên xác định theo link hay không.** Dùng NOFOLLOW_LINKS có chủ đích khi provider hỗ trợ.

**Lỗi 19 — Dùng dynamic "user:name" với String value mà không encode.** Typed API yêu cầu ByteBuffer; dynamic user value là byte[] hoặc ByteBuffer.

**Lỗi 20 — Nuốt IOException và coi mọi lỗi là unsupported.** Phải phân biệt thiếu view, thiếu tên, permission và lỗi I/O.

## 18. Checklist code review

- [ ] Metadata thật sự nhỏ và cần gắn với file thay vì nằm trong DB/sidecar?
- [ ] Có kiểm tra `FileSystem.supportedFileAttributeViews()` hoặc view-level support phù hợp?
- [ ] Nếu cần xác định khả năng của volume, có xét `FileStore.supportsFileAttributeView(UserDefinedFileAttributeView.class)`?
- [ ] Có xử lý `Files.getFileAttributeView(...) == null` trước khi gọi method?
- [ ] Giá trị do app quy định **encoding/schema/version** rõ ràng chưa?
- [ ] Số byte encode/decoded được kiểm tra, không nhầm với độ dài String?
- [ ] Có dùng `ByteBuffer.remaining()` và `flip()` đúng lúc?
- [ ] Có giới hạn tối đa byte trước khi `ByteBuffer.allocate(size)`?
- [ ] Có xử lý trường hợp attribute bị đổi/xóa giữa `list/size/read`?
- [ ] Có phân biệt attribute không tồn tại và giá trị rỗng?
- [ ] Có kiểm tra số byte thực ghi/đọc khi nghiệp vụ cần toàn vẹn?
- [ ] Có tránh overwrite/xóa attribute của ứng dụng khác?
- [ ] Có biết `write` thay thế toàn giá trị, không phải append?
- [ ] Có xử lý `IOException` của mọi thao tác, thay vì chỉ kiểm tra support?
- [ ] Nếu cần đọc một String nghiêm ngặt, có dùng UTF-8 decoder với REPORT khi cần?
- [ ] Có chính sách symlink/NOFOLLOW_LINKS và rủi ro TOCTOU?
- [ ] Có test trên filesystem/provider thực tế, bao gồm remote và ZIP nếu dùng?
- [ ] Có test copy/backup/restore xem user metadata còn hay mất?
- [ ] Nếu thuộc tính là bắt buộc, có fail closed hoặc fallback thiết kế trước?
- [ ] Có tránh lưu bí mật hoặc trạng thái transaction quan trọng trong metadata tùy chọn?

## 19. Câu hỏi tự kiểm tra

**1.** UserDefinedFileAttributeView dùng để làm gì? — Đọc/ghi các cặp **tên String / giá trị byte** gắn với file khi provider hỗ trợ.

**2.** Tên của attribute view này là gì? — `"user"`.

**3.** View này có bắt buộc trên mọi filesystem không? — **Không**.

**4.** Kiểm tra support theo FileStore bằng lệnh nào? — `store.supportsFileAttributeView(UserDefinedFileAttributeView.class)` hoặc overload tên `"user"`.

**5.** `Files.getFileAttributeView(path, UserDefinedFileAttributeView.class)` trả gì nếu không hỗ trợ? — **null**.

**6.** `view.list()` trả gì? — Danh sách tên attribute, không phải giá trị; danh sách unmodifiable.

**7.** `view.size(name)` đo bằng đơn vị nào? — **Byte**, kiểu int.

**8.** `view.read(name, dst)` có được đọc một phần nếu buffer quá nhỏ? — Không; có thể ném **IOException** do thiếu buffer.

**9.** Tại sao phải gọi `flip()` trước decode? — Vì `read` đã tăng position; `flip` chuyển sang đọc các byte vừa nhận.

**10.** `view.write(name, src)` khi name đã tồn tại thì sao? — **Thay thế giá trị** attribute, không append.

**11.** `view.delete(name)` có xóa file không? — Không, chỉ xóa attribute.

**12.** Làm sao ghi “Xin chào” đúng charset? — Encode UTF-8 thành ByteBuffer, sau đó ghi; khi đọc decode bằng UTF-8.

**13.** Khi dùng Files.getAttribute dynamic, tên định dạng thế nào? — `"user:attribute-name"`, giá trị trả về là `byte[]`.

**14.** `Files.setAttribute(path, "user:note", "text")` có tự encode String không? — Không nên dùng kiểu đó; user attribute yêu cầu byte[] hoặc ByteBuffer.

**15.** Vì sao không tin rằng user attribute luôn đi theo Files.copy? — Việc copy metadata ngoài basic tùy khả năng/provider/options, không có bảo đảm chung trên mọi đích.

**16.** Một FileSystem báo có user view có đủ để khẳng định mọi FileStore hỗ trợ không? — Không, FileStore có thể khác nhau.

**17.** Nếu view tồn tại, có chắc gọi write không lỗi không? — Không; quyền, kích thước, provider và trạng thái filesystem vẫn ảnh hưởng.

**18.** Dùng metadata này để lưu mật khẩu có an toàn mặc định không? — Không, nó không thay thế secrets storage.

**19.** `NOFOLLOW_LINKS` giải quyết hoàn toàn symlink race không? — Không, nó chỉ áp chính sách theo link cho thao tác tương ứng khi hỗ trợ.

**20.** Khi nào nên chọn sidecar/DB thay vì user attribute? — Khi cần tính portable, search/query, transactions, backup hoặc dữ liệu phải sống qua sao chép đa hệ thống.

## Tài liệu chính thức còn áp dụng

- [Java SE 17 — UserDefinedFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/UserDefinedFileAttributeView.html): quy tắc tên/giá trị byte, `list`, `size`, `read`, `write`, `delete` và giới hạn.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `getFileAttributeView`, `getAttribute`, `setAttribute`, `copy` và `getFileStore`.
- [Java SE 17 — FileSystem](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): `supportedFileAttributeViews()` và quan hệ giữa filesystem/file store.
- [Java SE 17 — FileStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html): `supportsFileAttributeView`, đặc biệt với file store local/remote.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `remaining` và `flip`.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): quy tắc encode/decode UTF-8.
- [Java SE 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): xử lý symbolic links.
- [Oracle Core Libraries — User-Defined File Attributes File NIO Example](https://docs.oracle.com/en/java/javase/17/core/java-core-libraries-developer-guide.pdf): ví dụ chính thức về liệt kê, đọc, ghi và xóa user metadata.

**Ghi nhớ:** `UserDefinedFileAttributeView` giúp lưu metadata nhỏ dưới dạng **String name + byte value** khi filesystem hỗ trợ. Trước khi sử dụng cần **kiểm tra provider/FileStore/view**, sau đó dùng `write/read/size/list/delete` với `ByteBuffer` đúng cách và charset rõ ràng. Không giả định metadata portable qua copy/backup, không coi capability là quyền truy cập, không dùng xattrs thay thế database hay secrets storage, và luôn xử lý lỗi I/O cùng các rủi ro thay đổi file đồng thời.