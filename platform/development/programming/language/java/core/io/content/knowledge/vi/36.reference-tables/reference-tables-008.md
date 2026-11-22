# Tra cứu Javadoc, Serialization Specification và khả năng của provider trong Java I/O

## 1. Mục tiêu và cách chọn nguồn tài liệu

Khi sử dụng Java I/O, câu hỏi quan trọng không chỉ là “gọi phương thức nào?” mà còn là “Java bảo đảm hành vi nào, hành vi nào tùy hệ điều hành hoặc provider, và lỗi có thể xảy ra ở đâu?”. Ba nguồn thông tin giải quyết ba lớp câu hỏi khác nhau:

| Nguồn | Trả lời điều gì? | Ví dụ câu hỏi |
| --- | --- | --- |
| **Javadoc của Java SE** | Chữ ký API, ngữ nghĩa, tham số, giá trị trả về, ngoại lệ, bảo đảm và giới hạn của từng lớp/phương thức. | `Files.move` có bảo đảm atomic không? `InputStream.read` trả về gì khi hết dữ liệu? |
| **Java Object Serialization Specification** | Quy tắc chuẩn của cơ chế tuần tự hóa đối tượng: đồ thị đối tượng, trạng thái được lưu, định dạng luồng, phục hồi, tương thích phiên bản, hook và bảo mật. | `transient` được xử lý thế nào? Khi đổi trường hoặc `serialVersionUID` thì việc đọc dữ liệu cũ ra sao? |
| **Tài liệu và khả năng của provider đang chạy** | Những gì một triển khai thực tế hỗ trợ, như file attribute view, symbolic link, atomic move, ZIP filesystem hoặc tùy chọn mở tệp. | Provider của `Path` này có hỗ trợ POSIX permissions không? |

**Nguyên tắc:** Javadoc và specification là hợp đồng để lập luận; phát hiện capability tại runtime giúp chọn nhánh xử lý phù hợp. Một tính năng “optional” trong Javadoc không trở thành tính năng luôn có chỉ vì hoạt động trên máy phát triển.

Cần chốt **phiên bản JDK mục tiêu** (ví dụ Java 17 hoặc 21) trước khi tra cứu. Chọn đúng tài liệu Java SE cho phiên bản đó; API mới hơn có thể chưa tồn tại ở JDK đang chạy. Bài này minh họa bằng Java 17+ và liên kết tài liệu Java SE 21 để tra cứu.

## 2. Đọc Javadoc hiệu quả

### 2.1. Xác định đúng lớp, package, module và overload

Bắt đầu từ lớp sở hữu thao tác:

- Byte stream: `java.io.InputStream`, `OutputStream`, `BufferedInputStream`, `DataInputStream`.
- Character stream và charset: `Reader`, `Writer`, `InputStreamReader`, `OutputStreamWriter`, `java.nio.charset.Charset`.
- Filesystem/NIO.2: `java.nio.file.Path`, `Paths`, `Files`, `FileSystem`, `FileStore`, `FileSystems`.
- Object serialization: `Serializable`, `Externalizable`, `ObjectOutputStream`, `ObjectInputStream`, `ObjectStreamClass`.

Mỗi trang Javadoc chỉ rõ **module**, **package**, `Since`, thông tin kế thừa và các overload. `Files.copy(Path, Path, CopyOption...)` có hợp đồng khác `Files.copy(InputStream, Path, CopyOption...)`; không kết luận theo tên phương thức đơn thuần.

### 2.2. Đọc phần mô tả theo thứ tự

1. Đọc mô tả cấp lớp trước: tài nguyên, thread-safety, đặc điểm hoặc điều kiện của implementor.
2. Chọn đúng signature/overload: kiểu tham số, varargs, generic, return type và `throws`.
3. Đọc toàn bộ mô tả chi tiết: mặc định khi không truyền option, chính sách xử lý symbolic link, trạng thái khi thao tác thất bại.
4. Đọc `Parameters`, `Returns`, `Throws`, `Implementation Requirements/Notes`, `API Note` và `See Also` nếu có.
5. Ghi ra: **điều được bảo đảm**, **điều tùy triển khai**, **thao tác optional**, **ngoại lệ cần xử lý**, và **cách đóng tài nguyên**.

Ví dụ ở `InputStream.read()`: kết quả là một `int` biểu diễn byte hợp lệ từ 0 đến 255, hoặc `-1` khi kết thúc luồng; không ép ngay về `byte` trước khi kiểm tra `-1`. Một lời gọi `read(byte[])` cũng không có nghĩa là luôn lấp đầy cả mảng; phải xem số byte thực đọc được.

Ví dụ ở `Files.newOutputStream(path)`: nếu không chỉ định option, mặc định tương đương `CREATE`, `TRUNCATE_EXISTING` và `WRITE`. Vì thế “mở để ghi” có thể xóa nội dung cũ. Nếu cần không ghi đè, tra `CREATE_NEW` và xử lý `FileAlreadyExistsException`; không chọn option bằng suy đoán.

### 2.3. “Có API” khác “mọi triển khai đều hỗ trợ”

Trong Javadoc, các cụm như “optional operation”, “implementation specific”, “if supported” và “not specified” là một phần quan trọng của hợp đồng.

- `Files.move(source, target, ATOMIC_MOVE)`: yêu cầu di chuyển nguyên tử. Nếu không thể đáp ứng, `AtomicMoveNotSupportedException` có thể được ném; không nên âm thầm coi di chuyển thông thường cũng atomic. Khi có `ATOMIC_MOVE`, cách xử lý mục tiêu đã tồn tại là tùy triển khai và các option khác bị bỏ qua.
- `Files.copy(..., COPY_ATTRIBUTES)`: các thuộc tính nào được sao chép phụ thuộc filesystem/provider; thời gian sửa đổi cuối cùng là thuộc tính tối thiểu được cố gắng sao chép nếu cả hai bên hỗ trợ, và có thể mất độ chính xác.
- `Files.createSymbolicLink` và `FileSystem.newWatchService` là những chức năng có thể không được hỗ trợ.
- `Files.getFileAttributeView(path, SomeView.class)` có thể trả về `null` khi view không khả dụng; các thao tác đọc thuộc tính tương ứng cũng có thể ném `UnsupportedOperationException`.

Cũng cần phân biệt kết quả kiểm tra: `Files.exists(path) == false` **không khẳng định** rằng tệp chắc chắn không tồn tại; API có thể không xác định được do lỗi quyền truy cập hoặc I/O. Tương tự `Files.notExists(path) == false` không tự chứng minh tệp tồn tại.

## 3. Tra cứu đúng Java Object Serialization Specification

Object serialization trong Java là cơ chế chuyển **đồ thị đối tượng** thành luồng để ghi/trao đổi và phục hồi theo quy tắc riêng. Nó không đồng nghĩa với đọc/ghi byte thông thường bằng `Files` hoặc với JSON. Những quy tắc không thể suy ra đầy đủ từ một phương thức `ObjectOutputStream.writeObject` được đặc tả trong **Java Object Serialization Specification**.

### 3.1. Bản đồ những phần thường cần đọc

| Câu hỏi | Phần cần mở trong Serialization Specification |
| --- | --- |
| Trường nào được lưu, object graph, reference chia sẻ và chu trình? | Chương 1 — System Architecture, đặc biệt 1.2–1.7 và 1.14 |
| `Serializable` khác `Externalizable` thế nào? | Mục 1.10–1.11, 2.4 và 3.6 |
| Tự điều chỉnh ghi/đọc đối tượng bằng `writeObject`/`readObject`? | Chương 2–3, đặc biệt 2.3 và 3.4 |
| `serialVersionUID`, mô tả lớp, serial form? | Chương 4, đặc biệt 4.3 và 4.6 |
| Đổi tên/xóa/thêm trường, đổi kiểu, tương thích dữ liệu đã lưu? | Chương 5 — Versioning of Serializable Objects |
| Dữ liệu nhị phân của stream và phiên bản giao thức? | Chương 6 — Object Serialization Stream Protocol |
| Bề mặt tấn công và lỗi deserialization? | Phụ lục A/B và Javadoc `ObjectInputFilter` |

Nên đọc đồng thời Javadoc của `Serializable`, `ObjectInputStream`, `ObjectOutputStream` và phần specification có liên quan. Specification quy định cơ chế; Javadoc cung cấp cách gọi API cùng exception cụ thể.

### 3.2. Các quy tắc cốt lõi cần nắm

- Một lớp khai báo `implements Serializable` để tham gia cơ chế serialization mặc định. Marker interface này **không có phương thức** cần implement.
- Mặc định, các trường instance đủ điều kiện được đưa vào serial form; `static` không biểu diễn trạng thái riêng từng instance và `transient` không được lưu theo cơ chế mặc định. Giá trị của trường `transient` sau phục hồi là giá trị mặc định của kiểu, trừ khi có logic khôi phục khác.
- Một trường tham chiếu đến đối tượng không serializable có thể khiến quá trình ghi ném `NotSerializableException` nếu đối tượng đó thực sự được duyệt trong đồ thị serialization.
- `ObjectOutputStream` ghi mô tả lớp và dữ liệu đối tượng; `ObjectInputStream` đọc theo protocol, tái dựng reference chia sẻ/chu trình. Không giả định constructor của lớp `Serializable` được gọi như tạo đối tượng mới; constructor không tham số có thể truy cập của lớp cha đầu tiên **không Serializable** được gọi khi phục hồi.
- Khai báo `private static final long serialVersionUID = ...L;` cho lớp serializable thông thường giúp kiểm soát bộ định danh phiên bản. UID khác nhau có thể gây `InvalidClassException`; **UID giống nhau không chứng minh mọi thay đổi trong lớp đều tương thích**. Phải xem quy tắc tiến hóa lớp ở Chương 5.
- `private writeObject(ObjectOutputStream)`/`private readObject(ObjectInputStream)`, `writeReplace`/`readResolve`, `serialPersistentFields` và `Externalizable` thay đổi giao thức/serial form; cần đọc chính xác điều kiện khai báo và thứ tự xử lý trong đặc tả. `Externalizable` chịu trách nhiệm ghi/đọc dữ liệu của chính nó và cần constructor `public` không tham số cho việc phục hồi.
- Enum có quy tắc serialization riêng; record serializable cũng có quy tắc riêng. Không suy diễn mọi hook của lớp thông thường sang enum/record.
- Java serialization không phải định dạng trao đổi tổng quát lý tưởng cho API lâu dài. Nếu cần hợp đồng đa ngôn ngữ hoặc schema tiến hóa độc lập, hãy cân nhắc một định dạng được xác định cho mục đích đó.

### 3.3. Ví dụ Java 17+ có thể biên dịch: `transient` và serial form

Lưu mã sau vào tệp `SerializationProbe.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

public class SerializationProbe {
    private static final class Profile implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String name;
        private transient String sessionToken;

        private Profile(String name, String sessionToken) {
            this.name = name;
            this.sessionToken = sessionToken;
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] saved;

        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(new Profile("Lan", "temporary-token"));
            out.flush();
            saved = bytes.toByteArray();
        }

        try (ObjectInputStream in =
                     new ObjectInputStream(new ByteArrayInputStream(saved))) {
            Profile restored = (Profile) in.readObject();
            System.out.println(restored.name);
            System.out.println(restored.sessionToken == null);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SerializationProbe.java
java SerializationProbe
```

Kết quả:

```text
Lan
true
```

`name` được lưu; `sessionToken` bị đánh dấu `transient` nên giá trị khôi phục bằng `null`. Ví dụ dùng mảng byte do chính chương trình tạo ra, **không đọc stream không tin cậy**. `@Serial` giúp trình biên dịch kiểm tra một số khai báo phục vụ serialization, nhưng không thay đổi yêu cầu bảo mật hay làm dữ liệu tương thích tự động.

### 3.4. Bảo mật khi deserialization

Đừng dùng `ObjectInputStream.readObject()` với dữ liệu do bên không tin cậy kiểm soát chỉ vì đã có `serialVersionUID`, `transient` hoặc kiểm tra kiểu sau khi đọc. Quá trình dựng đồ thị đối tượng diễn ra trước khi ép kiểu và có thể kích hoạt logic của các lớp trên classpath.

Nếu bắt buộc dùng Java native serialization cho một nguồn dữ liệu được kiểm soát, hãy áp dụng chính sách cho phép kiểu rõ ràng và giới hạn kích thước/độ sâu/độ phức tạp bằng `ObjectInputFilter` (bao gồm filter cho từng stream), đồng thời xác thực nguồn và quản lý phiên bản. Javadoc cảnh báo rằng deserialization dữ liệu không tin cậy là nguy hiểm ngay cả khi có filtering; ưu tiên tránh cơ chế này ở ranh giới không tin cậy.

## 4. Provider trong Java NIO.2: ai thực hiện thao tác trên `Path`?

Một `Path` thuộc về **một `FileSystem` cụ thể**; `FileSystem` đó do một `FileSystemProvider` cung cấp. Lớp tiện ích `Files` thường ủy nhiệm hoạt động cho provider tương ứng của `Path`. Vì vậy cùng một lời gọi `Files` có thể có giới hạn khác nhau trên filesystem mặc định, ZIP filesystem hoặc một implementation bên thứ ba.

Quan hệ tra cứu:

```text
Path ──getFileSystem()──> FileSystem ──provider()──> FileSystemProvider
  │                         │                              │
  └── Files.* thao tác ──────┴── triển khai thao tác <─────┘
```

Provider mặc định thường có scheme `file`. Provider khác có scheme riêng (ví dụ `jar` cho ZIP/JAR filesystem khi module/provider tương ứng có sẵn). Sự hiện diện của một provider phải được kiểm chứng trên JVM đang chạy, không thể suy ra chỉ từ extension `.zip` hoặc từ sự hiện diện của một lớp API.

### 4.1. API kiểm tra khả năng ở từng cấp

- `FileSystemProvider.installedProviders()`: liệt kê các provider được cài đặt mà API tìm thấy; `provider.getScheme()` xác định URI scheme.
- `path.getFileSystem().provider()`: biết provider thực sự sở hữu `Path`; `FileSystems.getDefault()` chỉ đại diện filesystem mặc định.
- `fileSystem.supportedFileAttributeViews()`: tập tên các view mà **filesystem** hỗ trợ, ví dụ `basic`, `posix`, `dos`, `acl`, `user` (tập thực tế tùy provider).
- `Files.getFileStore(path).supportsFileAttributeView(...)`: kiểm tra view tại **file store** chứa đường dẫn; chuẩn `basic` luôn được hỗ trợ. Kết quả trên một số lưu trữ không cục bộ vẫn có thể không chính xác hoàn toàn.
- `Files.getFileAttributeView(path, PosixFileAttributeView.class)`: trả về đối tượng view nếu có, hoặc `null` nếu không hỗ trợ kiểu view đó.
- Các chức năng optional khác (atomic move, symbolic/hard link, file locking, watch service, option riêng của provider) phải được tra trong **Javadoc của thao tác tương ứng** và kiểm tra bằng thao tác thật có xử lý ngoại lệ. Không có một hàm `isEverythingSupported()` tổng quát.

Lưu ý: **tên view hỗ trợ không nói lên quyền thực hiện thao tác**. Dù hệ thống hỗ trợ POSIX view, việc thay đổi permission vẫn có thể thất bại do quyền người dùng hoặc trạng thái read-only. Hơn nữa, `FileStore` chứa `Path` cụ thể có thể khác capability tổng quát của `FileSystem`.

### 4.2. Ví dụ Java 17+ chạy được: tìm provider và file attribute view

Lưu `ProviderProbe.java`:

```java
import java.nio.file.FileStore;
import java.nio.file.FileSystem;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;
import java.nio.file.spi.FileSystemProvider;

public class ProviderProbe {
    public static void main(String[] args) throws Exception {
        Path path = Path.of(".").toAbsolutePath().normalize();
        FileSystem fs = path.getFileSystem();
        FileStore store = Files.getFileStore(path);

        System.out.println("Provider của Path: "
                + fs.provider().getScheme());
        System.out.println("Attribute views của FileSystem: "
                + fs.supportedFileAttributeViews());
        System.out.println("FileStore hỗ trợ POSIX: "
                + store.supportsFileAttributeView(PosixFileAttributeView.class));
        System.out.println("POSIX view tại Path khả dụng: "
                + (Files.getFileAttributeView(
                        path, PosixFileAttributeView.class) != null));

        System.out.println("Các provider được cài đặt:");
        for (FileSystemProvider provider : FileSystemProvider.installedProviders()) {
            System.out.println("  " + provider.getScheme());
        }
    }
}
```

Chạy:

```bash
javac ProviderProbe.java
java ProviderProbe
```

Kết quả sẽ **khác nhau giữa Windows, Linux, macOS, filesystem và JDK**. Với đường dẫn thuộc filesystem mặc định, scheme thường là `file`; view `posix` thường có trên hệ thống POSIX nhưng không nên giả định luôn có. Danh sách có thể có provider `jar` khi ZIP filesystem provider sẵn có. Không lấy đầu ra của một máy làm bảo đảm di động cho mọi máy.

### 4.3. Quyết định theo capability và dự phòng có chủ đích

Giả sử muốn di chuyển một tệp kết quả sang vị trí đích:

```java
import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class MoveExample {
    public static void moveWithFallback(Path source, Path target)
            throws IOException {
        try {
            Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }
}
```

Đây là **đoạn minh họa phương thức**, không phải chương trình độc lập có `main`. Nhánh fallback chấp nhận ngữ nghĩa **không atomic**; dùng nó **chỉ khi nghiệp vụ cho phép**. Nếu cần công bố tệp mà độc giả tuyệt đối không được thấy trạng thái trung gian, không thể coi fallback này là tương đương. Khi `ATOMIC_MOVE` được yêu cầu, xử lý đích đã tồn tại có thể khác nhau theo implementation, nên phải thiết kế riêng quy tắc ghi đè. `IOException` khác vẫn cần được đưa lên hoặc xử lý; không bắt mọi lỗi rồi đoán “provider không hỗ trợ”.

Với permission POSIX, có thể chọn nhánh chỉ khi `Files.getFileAttributeView(path, PosixFileAttributeView.class) != null`, rồi vẫn xử lý `IOException` hoặc lỗi quyền khi thực thi. Nếu cần chức năng bắt buộc mà provider không hỗ trợ, giải pháp đúng có thể là **từ chối thao tác và thông báo rõ giới hạn**, thay vì mô phỏng sai bảo đảm.

### 4.4. Khi nào cần đọc tài liệu riêng của provider?

Hãy đọc tài liệu triển khai khi ứng dụng sử dụng ZIP/JAR filesystem, filesystem từ thư viện, filesystem mạng/cloud, hoặc open option và metadata mở rộng. Cần xác minh:

1. URI scheme và cách khởi tạo `FileSystem` (qua `FileSystems.newFileSystem`, map cấu hình, lifecycle `close()`).
2. Quy tắc đường dẫn, phân biệt chữ hoa/thường, separator, quyền truy cập và trạng thái read-only.
3. File attribute views, symbolic link/hard link, atomic move, watch service và đặc điểm nhất quán.
4. Giới hạn kích thước, thao tác đa luồng, xử lý lỗi, thời gian chặn I/O và hành vi khi đóng tài nguyên.

Javadoc chuẩn mô tả giao diện chung; không tự gán tính năng của provider mặc định cho `Path` thuộc provider khác. Khi có nhiều nguồn `Path`, phải truy xuất provider **từ từng `Path`** trước khi quyết định.

## 5. Phân loại lỗi đúng khi tra cứu

| Hiện tượng hoặc exception | Điểm cần kiểm chứng | Hướng xử lý |
| --- | --- | --- |
| `NotSerializableException` | Thành phần nào trong object graph không đáp ứng quy tắc serialization? | Xem kiểu trường và đường tham chiếu; thiết kế DTO/serial form phù hợp. |
| `InvalidClassException` | UID, mô tả lớp và thay đổi serial form có tương thích Chương 5 không? | Quản lý phiên bản, migration hoặc format riêng; không sửa UID tùy tiện để “qua lỗi”. |
| `StreamCorruptedException` | Luồng có đúng object stream protocol không, có bị cắt/hỏng không? | Xác minh nguồn, framing và cách ghi; không coi file thường là object stream. |
| `ProviderNotFoundException` | Provider cho scheme/file type có được cài đặt và discover không? | Kiểm tra `FileSystemProvider.installedProviders()`, classpath/module và cách mở. |
| `UnsupportedOperationException` | API/option/view có được đánh dấu optional hoặc không được hỗ trợ không? | Đọc đúng overload và capability, thay thế hợp lệ hoặc báo không hỗ trợ. |
| `AtomicMoveNotSupportedException` | `ATOMIC_MOVE` có được filesystem/store đích hỗ trợ không? | Chỉ fallback khi chấp nhận mất tính atomic. |
| `AccessDeniedException` / `IOException` | Quyền, path thực tế, thiết bị, kết nối, store hoặc giới hạn implementation? | Ghi lại ngữ cảnh an toàn, xử lý lỗi I/O cụ thể; không nhầm mọi `IOException` thành thiếu capability. |

Khi cần phân biệt lỗi, ưu tiên ngoại lệ được Javadoc tuyên bố; đừng phân tích chuỗi thông báo lỗi theo từng hệ điều hành để quyết định nhánh logic.

## 6. Quy trình tra cứu từ câu hỏi tới quyết định kỹ thuật

**Tình huống A — “Đọc file Unicode đúng trên mọi máy”:**

1. Xác định bài toán là text: tìm `Files.newBufferedReader(Path, Charset)` hoặc `Files.readString(Path, Charset)`.
2. Đọc Javadoc để biết charset, ngoại lệ và cách đóng reader; truyền rõ `StandardCharsets.UTF_8` thay vì ngầm dựa vào default charset ở code cũ.
3. Nếu cần streaming file lớn, ưu tiên `BufferedReader` hoặc stream và `try-with-resources`; đừng dùng `readAllBytes` chỉ vì code ngắn hơn.
4. Phân biệt lỗi encoding với lỗi do provider, permission và path.

**Tình huống B — “Lưu đối tượng rồi đọc lại sau khi deploy bản mới”:**

1. Tra Javadoc `Serializable`, `ObjectOutputStream`, `ObjectInputStream` để xác định API.
2. Đọc Serialization Specification Chương 4–5 và serial form của từng lớp để đánh giá thay đổi.
3. Xác định dữ liệu đầu vào có đáng tin không; nếu không, tránh Java deserialization. Nếu thật sự cần, thiết kế lọc lớp và giới hạn tài nguyên.
4. Tạo test tương thích thực sự: ghi dữ liệu bằng phiên bản cũ, đọc bằng phiên bản mới (và chiều ngược lại nếu sản phẩm cần). Test một vòng serialize–deserialize trong cùng phiên bản không kiểm chứng tương thích nâng cấp.

**Tình huống C — “Copy/move tệp qua ổ đĩa, ZIP hoặc filesystem mạng”:**

1. Tra Javadoc `Files.copy`/`Files.move` và option cần dùng; đặc biệt atomic, replacement, link và attributes.
2. Từ mỗi `Path` tìm `FileSystem`/provider, dùng `FileStore` và attribute views để xác định những khả năng có thể kiểm tra trước.
3. Thử hành vi bắt buộc trong môi trường đích, xử lý các exception đặc thù và xác nhận tính toàn vẹn sau thao tác.
4. Không coi “chạy được trên máy mình” là chứng cứ provider khác cũng làm giống hệt.

Một ghi chép tra cứu hữu ích cho mỗi quyết định gồm: **JDK/version → lớp & overload → bảo đảm Javadoc → câu trong specification (nếu có) → provider/capability → trường hợp lỗi → kết quả thử nghiệm trên môi trường đích**. Cách này giúp reviewer lần lại lập luận mà không phải đoán nguồn.

## 7. Lỗi học tập thường gặp và cách tự kiểm tra

- **Chỉ xem tên phương thức:** bỏ qua `Throws`, tùy chọn mặc định và ngữ nghĩa partial read/write. Cách sửa: đọc mô tả của đúng overload tới hết.
- **Nhầm Javadoc với Serialization Specification:** tin rằng tất cả quy tắc tương thích có ở `writeObject`. Cách sửa: đối chiếu Chương 4–5 specification.
- **Cho rằng `Serializable` tự bảo đảm an toàn, tương thích:** đây là hai vấn đề riêng. Cách sửa: đánh giá object graph, serial form/versioning và ranh giới tin cậy.
- **Coi `serialVersionUID` là phiên bản schema hoàn chỉnh:** UID chỉ tham gia kiểm tra tương thích, không thay thế kiểm tra thay đổi trường/hook.
- **Cho rằng Linux/Windows và mọi `Path` giống nhau:** xem capability ở `FileSystem`/`FileStore`/provider thực tế.
- **Coi `supportsFileAttributeView("posix")` là chắc chắn có quyền `setPermissions`:** khả năng API không phải quyền thực hiện thao tác.
- **Coi atomic move và fallback là tương đương:** fallback thay đổi bảo đảm khi xảy ra lỗi hoặc có độc giả đồng thời.
- **Chỉ đọc ví dụ blog trên JDK khác:** cách sửa là mở đúng Javadoc/specification của phiên bản mục tiêu, rồi dùng ví dụ để kiểm chứng.

Tự kiểm tra: (1) giải thích vì sao `read(byte[])` phải xử lý số byte đã đọc; (2) nêu vì sao cùng `serialVersionUID` vẫn có thể mất tương thích; (3) phân biệt `FileSystem.supportedFileAttributeViews()`, `FileStore.supportsFileAttributeView(...)` và `Files.getFileAttributeView(...)`; (4) giải thích khi nào được phép fallback từ `ATOMIC_MOVE`.

## 8. Nguồn chính thức để tiếp tục tra cứu

- [Java SE 21 API Javadoc — tổng quan](https://docs.oracle.com/en/java/javase/21/docs/api/index.html)
- [`Files` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [`FileSystem` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystem.html)
- [`FileStore` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileStore.html)
- [`FileSystems` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html)
- [`FileSystemProvider` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html)
- [`Serializable` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html)
- [`ObjectInputFilter` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Java Object Serialization Specification — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/)

Nếu hệ thống chạy Java 17, hãy mở cây tài liệu `/en/java/javase/17/...` cho chính các lớp và specification tương ứng. Không thay đổi kết luận hợp đồng API dựa trên bài viết mô tả một JDK khác.
