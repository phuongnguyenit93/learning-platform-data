# ZIP FileSystem trong Java: Tùy chọn tạo mới và bảng mã tên mục

## 1. Bài toán: tạo ZIP mới và giữ đúng tên tệp tiếng Việt

Giả sử một ứng dụng xuất báo cáo thành file `reports.zip` với các mục bên trong:

```text
reports.zip
└── docs/
    ├── đề-cương.txt
    └── tổng-hợp.csv
```

Chương trình cần giải quyết **hai việc khác nhau**:

1. Nếu `reports.zip` **chưa có**, làm sao yêu cầu ZIP filesystem provider **tạo một archive ZIP mới** thay vì báo lỗi?
2. Khi ghi và đọc lại những mục có tên tiếng Việt như `đề-cương.txt`, làm sao bảo đảm Java giải mã **tên mục trong ZIP** bằng bảng mã phù hợp?

Trong Java NIO.2, có thể xem một tệp ZIP hoặc JAR là một **`FileSystem`** và thao tác từng entry bằng `Path`, `Files.createDirectories`, `Files.writeString`, `Files.copy` và các API tương tự.

Hai tùy chọn môi trường quan trọng của ZIP filesystem provider là:

- **`create`**: cho phép **tạo tệp archive ZIP/JAR bên ngoài** nếu chưa tồn tại.
- **`encoding`**: chỉ ra **bảng mã dùng cho tên các entry** trong ZIP/JAR.

Cả hai là tùy chọn **khi mở/tạo ZIP filesystem**, không phải tùy chọn để giải mã **nội dung** tệp văn bản bên trong ZIP.

**Mấu chốt:** `create=true` không có nghĩa “tạo mới mọi entry” hoặc “xóa ZIP cũ rồi tạo lại”; `encoding=UTF-8` không có nghĩa “nội dung của mọi file bên trong được đọc bằng UTF-8 tự động”.

ZIP filesystem provider đã có từ JDK 7 và hiện vẫn được hỗ trợ. Trên JDK 9+ implementation chuẩn được cung cấp bởi module **`jdk.zipfs`**; với các runtime image tự tùy biến, cần bảo đảm module/provider này hiện diện. Ví dụ đầy đủ trong bài sử dụng Java 17+ và đã được biên dịch, chạy thực tế.

## 2. ZIP như một `FileSystem` chứ không chỉ là một luồng byte

Một archive ZIP trên hệ thống tệp vật lý là **một file**:

```text
C:/data/reports.zip        <- Path của archive trên host
```

Khi mở ZIP filesystem, nội dung của nó trở thành một cây `Path` **thuộc một provider khác**:

```text
/docs/đề-cương.txt         <- Path của entry bên trong ZIP FileSystem
/docs/tổng-hợp.csv
```

Cùng là kiểu `Path`, nhưng **không cùng file system**.

| Khái niệm | Giá trị ví dụ | Công dụng |
| --- | --- | --- |
| Archive host path | `Path.of("output", "reports.zip")` | Xác định file ZIP trên ổ đĩa |
| ZIP FileSystem | `FileSystems.newFileSystem(uri, env)` | Mở/cấp quyền thao tác như filesystem |
| ZIP entry path | `zip.getPath("/docs/đề-cương.txt")` | Xác định mục ở **bên trong** archive |
| Entry data | Nội dung chuỗi, ảnh, binary, JSON... | Đọc/ghi bằng API `Files` phù hợp |
| Entry name charset | `encoding=UTF-8` | Chuyển tên các mục qua byte encoding của ZIP |

Không tạo entry bằng `archive.resolve("docs/đề-cương.txt")`: cách đó tạo một tên đường dẫn **bên ngoài archive** theo host file system, chứ không phải path trong ZIP. Hãy tạo entry path bằng **`zip.getPath(...)`** sau khi mở `FileSystem`.

Đường dẫn mục bên trong ZIP thường bắt đầu bằng `/` và dùng `/` làm dấu phân cách theo ZIP filesystem. Không thay bằng `\\` chỉ vì ứng dụng đang chạy trên Windows.

### 2.1. Những việc ZIP filesystem xử lý giúp bạn

Provider có thể cho phép tạo directory, ghi file, đọc file và liệt kê entry bằng bộ API NIO.2 quen thuộc. Ví dụ:

```java
Path directory = zip.getPath("/docs");
Files.createDirectories(directory);

Path entry = directory.resolve("đề-cương.txt");
Files.writeString(entry, "Nội dung",
        java.nio.charset.StandardCharsets.UTF_8);
```

Đây là **đoạn minh họa** trong phương thức có `zip` là ZIP `FileSystem` đang mở và xử lý `IOException`; `Files.writeString` là API có từ **Java 11**. Trong thực tế, cần quyết định có cho phép ghi đè entry hay không, chứ không mặc định dùng cách ghi không option cho file đã tồn tại.

### 2.2. Vì sao không chỉ dùng `java.util.zip.ZipOutputStream`?

`ZipOutputStream` thích hợp khi bạn muốn ghi các `ZipEntry` tuần tự vào một luồng và kiểm soát dạng stream. ZIP filesystem phù hợp khi muốn dùng **mô hình đường dẫn** để đọc, thêm, sửa, xóa, hoặc duyệt entry bằng `Files`.

Không có một API thắng trong mọi trường hợp. Với một luồng xuất ZIP tuyến tính, `ZipOutputStream` có thể đơn giản và hiệu quả hơn. Với ứng dụng có nhiều thao tác ngẫu nhiên theo tên entry, ZIP filesystem thường dễ diễn đạt. Cả hai vẫn là API Java hiện hành; mục tiêu bài này là hai **environment options của ZIP filesystem**.

## 3. Cách mở ZIP filesystem bằng URI

Khi dùng môi trường `env`, cách phổ biến, tương thích ý tưởng từ Java 7, là xây dựng **URI có scheme `jar`** từ đường dẫn ZIP:

```java
import java.net.URI;
import java.nio.file.Path;

Path archive = Path.of("reports.zip").toAbsolutePath();
URI uri = URI.create("jar:" + archive.toUri());
```

Đoạn này nằm trong một phương thức. Ví dụ `archive.toUri()` tạo URI dạng `file:///...`, sau đó tiền tố `jar:` tạo URI để ZIP filesystem provider nhận diện:

```text
jar:file:///C:/data/reports.zip
jar:file:///home/user/data/reports.zip
```

Đây chỉ là **ví dụ dạng URI**; không hardcode drive letter hoặc OS path vào code đa nền tảng.

Không đưa một chuỗi đường dẫn có dấu cách/Unicode trực tiếp vào `URI.create("jar:file:" + rawPath)` khi chưa xử lý escape/encoding. Hãy dùng `Path.toUri()` để tạo file URI hợp lệ trước khi thêm `jar:`.

### 3.1. Tạo mới hoặc mở archive

```java
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.util.Map;

Map<String, String> env =
        Map.of("create", "true", "encoding", "UTF-8");

try (FileSystem zip = FileSystems.newFileSystem(uri, env)) {
    // Làm việc với zip.getPath(...) ở đây.
}
```

Đây là đoạn minh họa có biến `uri` kiểu `URI` và phương thức xử lý `IOException`. `Map.of` có từ Java 9; code Java 7 cần một `HashMap<String, String>` tương đương. `FileSystems.newFileSystem(URI, Map)` và ZIP filesystem provider đã có từ Java 7.

**Đừng nhầm `URI` trỏ tới archive với `Path` trỏ tới entry:** thứ nhất để mở file system, thứ hai được tạo **sau khi** có `zip`.

## 4. Tùy chọn `create`: tạo archive khi chưa tồn tại

Tùy chọn `create` trả lời câu hỏi:

> Khi mở ZIP filesystem trên một tệp archive **chưa có**, provider có được phép tạo tệp ZIP/JAR mới không?

Theo tài liệu `jdk.zipfs`, mặc định của `create` là **`false`**.

| Giá trị `create` | Archive chưa tồn tại | Archive đã tồn tại và hợp lệ |
| --- | --- | --- |
| Không truyền (mặc định `false`) | Thao tác mở thất bại, thường `NoSuchFileException` | Mở archive để làm việc theo chính sách provider |
| `"false"` | Không tự tạo archive mới | Mở archive đang có |
| `"true"` | Cho phép provider tạo archive ZIP/JAR mới | Mở archive đang có; **không mặc định xóa nội dung** |

Trên Java hiện đại, `create` có thể nhận **`String` hoặc `Boolean`** tùy hợp đồng module ZIPFS. Dùng `"true"`/`"false"` trong `Map<String,String>` là lựa chọn rõ ràng và phù hợp với tài liệu qua nhiều phiên bản JDK.

### 4.1. Tạo mới

```java
Map<String, String> env = Map.of("create", "true");

try (FileSystem zip = FileSystems.newFileSystem(uri, env)) {
    Files.createDirectories(zip.getPath("/docs"));
}
```

Đây là đoạn minh họa trong phương thức có `uri` hợp lệ và xử lý `IOException`. Khi `reports.zip` chưa tồn tại, provider tạo archive; khi archive đã tồn tại và hợp lệ, nó được mở thay vì bị xóa làm lại.

**Không dùng `create=true` như một chính sách ghi đè tệp ZIP cũ.** Nếu ứng dụng đòi “archive mới, tuyệt đối không phá dữ liệu cũ”, phải thiết kế kiểm soát tên/ownership và hành vi khi tệp archive đã tồn tại. Có thể chọn một đường dẫn đầu ra mới, hoặc một quy trình tạo file tạm và công bố kết quả theo hợp đồng. `create=true` **không tương đương** với ngữ nghĩa “fail if archive already exists”.

### 4.2. Chỉ mở ZIP đã có

```java
Map<String, String> env =
        Map.of("create", "false", "encoding", "UTF-8");

try (FileSystem zip = FileSystems.newFileSystem(uri, env)) {
    Path entry = zip.getPath("/docs/đề-cương.txt");
    // Đọc nếu entry tồn tại.
}
```

Nếu archive chưa có, trên provider chuẩn có thể gặp `NoSuchFileException`. Một archive có tồn tại nhưng **không phải file ZIP hợp lệ** cũng không tự biến thành ZIP mới khi `create=true`; provider có thể từ chối với lỗi định dạng/`IOException`.

### 4.3. `create` không tạo sẵn thư mục hoặc entry bên trong

Lệnh:

```java
FileSystems.newFileSystem(uri, Map.of("create", "true"));
```

**chỉ mở/tạo file system ZIP**, không tự sinh `/docs/đề-cương.txt`. Nếu cần directory/entry, phải tạo bằng API riêng:

```java
Files.createDirectories(zip.getPath("/docs"));

Files.writeString(zip.getPath("/docs/đề-cương.txt"),
        "Xin chào",
        java.nio.charset.StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.CREATE_NEW);
```

Hai đoạn trên là ví dụ nằm trong ngữ cảnh `zip` đang mở và phương thức xử lý `IOException`. `CREATE_NEW` ở đây là **tùy chọn tạo entry bên trong ZIP**, không phải property môi trường `create`.

## 5. Phân biệt hai khái niệm “tạo mới”

Đây là lỗi hiểu nhầm phổ biến nhất của bài.

| Mục tiêu | Cách điều khiển | Phạm vi tác động |
| --- | --- | --- |
| Tạo **tệp archive .zip** nếu nó chưa tồn tại | Environment property `"create" = "true"` khi gọi `newFileSystem` | File ZIP/JAR bên ngoài |
| Tạo **directory bên trong ZIP** | `Files.createDirectory` hoặc `Files.createDirectories` trên ZIP `Path` | Entry directory |
| Tạo **file entry mới, không ghi đè** | `Files.writeString(..., CREATE_NEW)` hoặc `Files.newOutputStream(..., CREATE_NEW)` | Entry file |
| Tạo file nếu thiếu, có thể mở file sẵn có | `StandardOpenOption.CREATE` cùng ngữ nghĩa ghi mong muốn | Entry file |
| Ghi đè nội dung file entry sẵn có | API ghi với tùy chọn truncate/replace phù hợp | Nội dung một entry |
| Copy một file từ host vào ZIP | `Files.copy(hostPath, zipEntry)` với tùy chọn phù hợp | Entry được copy |

### 5.1. `StandardOpenOption.CREATE_NEW` khi không được phép ghi đè

```java
Path entry = zip.getPath("/docs/đề-cương.txt");

Files.writeString(entry, "Nội dung đầu tiên",
        java.nio.charset.StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.CREATE_NEW);
```

Nếu entry đã tồn tại, ZIP filesystem provider chuẩn thường ném **`FileAlreadyExistsException`**. Chương trình hoàn chỉnh ở mục 12 đã kiểm thử tình huống này trên JDK 17.

Điều quan trọng là **nêu rõ chính sách không ghi đè**. Đừng gọi một API ghi không có option rồi cho rằng nó giống `CREATE_NEW`: đối với `Files.writeString`, không truyền open option thì theo hợp đồng ghi mặc định nó có thể tạo file nếu thiếu và **truncate file sẵn có**.

### 5.2. `CREATE` không giống `CREATE_NEW`

- `CREATE`: tạo file nếu chưa tồn tại; khi đã tồn tại, không tự thất bại chỉ vì có file. Hành vi ghi thêm/truncate phụ thuộc các option và API đi kèm.
- `CREATE_NEW`: yêu cầu tạo entry mới và thất bại nếu entry đã tồn tại theo hợp đồng tạo mới.
- `TRUNCATE_EXISTING`: khi mở để ghi và file đã có, yêu cầu cắt dữ liệu hiện có về độ dài 0 theo hợp đồng tương ứng.
- `APPEND`: ghi nối thêm trong những provider/mode hỗ trợ; không được suy rằng ZIP filesystem provider bắt buộc hỗ trợ mọi tổ hợp option giống file system vật lý.

Một số cặp option có thể không hợp lệ hoặc không được provider hỗ trợ. Với ZIP archive quan trọng, **không viết code phụ thuộc vào tổ hợp option chưa thử**; hãy kiểm thử đúng JDK/provider và thiết kế khôi phục nếu lỗi khi đóng.

### 5.3. Có cần kiểm tra `Files.exists` trước khi tạo entry?

Không nên làm:

```java
if (!Files.exists(entry)) {
    Files.writeString(entry, content,
            java.nio.charset.StandardCharsets.UTF_8);
}
```

và nghĩ hoàn toàn không thể ghi đè. Entry có thể thay đổi giữa phép kiểm tra và phép ghi (*time-of-check/time-of-use*). Nếu mục tiêu là **không ghi đè**, dùng `CREATE_NEW` trên chính thao tác tạo.

Đoạn trên là ví dụ **không nên áp dụng nguyên trạng** nếu cần chống ghi đè; cần biến `entry`, `content` và xử lý `IOException` trong phương thức.

### 5.4. “ZIP hiện có” khác “ZIPFS đang được mở”

Khi dùng `FileSystems.newFileSystem(URI, env)` với một archive **đang được mount bằng cùng URI** trong process, có thể nhận **`FileSystemAlreadyExistsException`**. Đừng mặc định có thể mở vô hạn những ZIP filesystem trùng URI mà không quản lý vòng đời.

Nếu cần chia sẻ cùng một ZIP filesystem giữa nhiều component, phải có chính sách **owner, thời gian sống và đồng bộ**, không cho từng component tự mở/đóng cùng một archive một cách tùy tiện. `FileSystems.getFileSystem(uri)` có thể lấy tham chiếu tới một file system đã được tạo, nhưng nó không tự chuyển ownership hoặc làm file system đã đóng sống lại.

## 6. Tùy chọn `encoding`: bảng mã của **tên entry**

Theo tài liệu ZIP filesystem provider, property `encoding` mặc định là **`UTF-8`** và nhận một chuỗi tên bảng mã.

```java
Map<String, String> env = Map.of(
        "create", "true",
        "encoding", "UTF-8");
```

Trong ngữ cảnh ZIP filesystem, `encoding` điều khiển cách provider biểu diễn/giải mã **tên các entry** khi làm việc với ZIP/JAR.

Ví dụ các tên:

```text
/docs/đề-cương.txt
/docs/tổng-hợp.csv
/images/ảnh-đại-diện.png
```

đều chứa ký tự ngoài ASCII. Một ZIP mới nên dùng **UTF-8** để tên mục có thể biểu diễn tiếng Việt và các ký tự Unicode thông dụng một cách nhất quán.

### 6.1. Vì sao phải quan tâm tới bảng mã tên mục?

Định dạng ZIP lưu tên entry ở dạng byte trong cấu trúc archive. Khi đọc các byte thành một tên để đưa vào `Path`, provider phải dùng bảng mã phù hợp. Khi tạo entry mới, provider cũng cần chuyển tên Java thành byte theo chính sách encoding.

Nếu các hệ thống đọc/ghi tên bằng bảng mã khác nhau, có thể xảy ra:

- Một số tên entry biến thành ký tự lạ hoặc bị sai dấu.
- Một archive không mở/không đọc được tên entry do byte không hợp lệ với charset được chọn.
- Một entry có thể không được tìm thấy bằng tên mong đợi vì cách giải mã tên khác nhau.
- Nếu chương trình copy/migrate một archive, những tên chứa Unicode có thể hỏng dù **nội dung file** vẫn đúng byte.

Đừng tự suy bảng mã từ tên ngôn ngữ của hệ điều hành, từ `Locale.getDefault()` hay từ `Charset.defaultCharset()`. Khi ZIP được tạo bởi phần mềm do bạn kiểm soát, **thống nhất UTF-8**; khi tương tác archive cũ không dùng UTF-8, cấu hình theo thông tin định dạng/nguồn tạo đáng tin.

### 6.2. `UTF-8` là lựa chọn mặc định hiện đại

Nếu không chỉ định `encoding`, provider `jdk.zipfs` chuẩn dùng UTF-8 cho tên entry. Vì vậy:

```java
Map<String, String> env = Map.of("create", "true");
```

và

```java
Map<String, String> env =
        Map.of("create", "true", "encoding", "UTF-8");
```

có cùng ý định với **bảng mã mặc định** của tên entry ở provider chuẩn hiện đại. Viết rõ `encoding=UTF-8` có thể giúp người đọc hợp đồng tích hợp nhận biết chính sách xử lý tên; bỏ đi cũng hợp lệ khi ứng dụng chủ động dựa vào mặc định được tài liệu bảo đảm.

### 6.3. Khi nào cần encoding khác?

Nếu phải đọc một ZIP được tạo từ hệ thống cũ có tên entry lưu bằng bảng mã khác, chương trình **có thể** cần khai báo tên charset tương ứng, chẳng hạn `Cp437` trong một môi trường hỗ trợ charset đó.

```java
Map<String, String> env =
        Map.of("create", "false", "encoding", "Cp437");
```

**Đây là nhánh tương thích dữ liệu lịch sử, không phải đề xuất tạo ZIP mới với Cp437.** Trong các hệ thống Java mới, ưu tiên tạo archive UTF-8 và chuyển đổi dữ liệu cũ theo quy trình có kiểm chứng nếu cần.

Việc chọn đúng charset phải dựa vào nguồn tạo ZIP và dữ liệu thực. Không nên “thử mọi charset và chọn kết quả trông có vẻ đúng” để sửa tên entry quan trọng, vì có thể gây map nhầm tên hoặc ghi trở lại archive bằng bảng mã không phù hợp.

### 6.4. Không phải mọi bảng mã hỗ trợ mọi ký tự

UTF-8 biểu diễn được tên Unicode thông dụng; một charset đơn byte có thể không biểu diễn được ký tự tiếng Việt hoặc emoji. Nếu cố lưu tên không thể mã hóa bằng charset đã chọn, provider có thể thất bại. Đừng mặc định charset khác UTF-8 luôn hỗ trợ mọi ký tự trong `String` Java.

Tên charset phải tồn tại trong runtime. Một custom runtime image tối giản có thể không chứa các extended charsets hoặc module/provider cần thiết. Nếu lựa chọn bảng mã là đầu vào cấu hình, cần kiểm tra và báo lỗi rõ khi không hỗ trợ.

## 7. Bảng mã **tên entry** không phải bảng mã **nội dung file**

Ví dụ một file trong ZIP:

```text
ZIP entry path:  /docs/đề-cương.txt
ZIP entry name:  "đề-cương.txt"
File content:    "Xin chào ☕"
```

Tại đây có **hai lớp chuyển đổi hoàn toàn khác**:

| Cấp | Chuyển đổi | Ai điều khiển? |
| --- | --- | --- |
| ZIP entry name | Các byte tên mục ↔ tên `Path`/`String` | `encoding` của ZIP filesystem |
| File content (text) | Các byte nội dung ↔ chuỗi ký tự | `Charset` trong `Files.writeString/readString` hoặc các API đọc/ghi text |
| File content (binary) | Các byte giữ nguyên | `Files.write`/`newInputStream`/`newOutputStream`; không có “text charset” mặc định cho binary |

Hai ví dụ:

```java
Map<String, String> env =
        Map.of("create", "true", "encoding", "UTF-8");

try (FileSystem zip = FileSystems.newFileSystem(uri, env)) {
    Path text = zip.getPath("/đề-cương.txt");
    Files.writeString(text, "Xin chào ☕",
            java.nio.charset.StandardCharsets.UTF_8);
}
```

```java
Map<String, String> env =
        Map.of("create", "true", "encoding", "UTF-8");

try (FileSystem zip = FileSystems.newFileSystem(uri, env)) {
    Path text = zip.getPath("/đề-cương.txt");
    Files.writeString(text, "Xin chào ☕",
            java.nio.charset.StandardCharsets.UTF_16);
}
```

Đây là **hai ví dụ độc lập với nhau**, mỗi ví dụ giả định archive được mở trên một URI phù hợp và method có xử lý `IOException`. Tên entry ở cả hai được xử lý theo **UTF-8**, nhưng nội dung tệp có encoding khác nhau. Đoạn thứ hai **không** phải khuyến nghị dùng UTF-16 cho văn bản; nó chỉ chứng minh hai loại encoding độc lập. Khi đọc nội dung, phải dùng **đúng charset** ứng với nội dung đã ghi.

### 7.1. Thay `encoding` không tự chuyển mã văn bản bên trong ZIP

Nếu một entry chứa nội dung được ghi bằng UTF-16, việc mở ZIP filesystem bằng `encoding=UTF-8` không chuyển file nội dung sang UTF-8. Gọi `Files.readString(path, UTF_8)` lên byte UTF-16 có thể cho dữ liệu sai hoặc lỗi giải mã.

Muốn chuyển encoding nội dung, cần **đọc bằng charset gốc và ghi lại bằng charset đích** theo nghiệp vụ, không đơn thuần đổi thuộc tính môi trường khi mở ZIP.

### 7.2. Tên file có dấu và nội dung ASCII

Một entry có tên `tổng-hợp.txt` nhưng chỉ chứa chữ ASCII vẫn cần encoding đúng cho **tên**; nội dung ASCII không làm tên trở thành ASCII. Ngược lại, tên entry `notes.txt` có thể chứa nội dung tiếng Việt UTF-8. Bảng mã tên và bảng mã dữ liệu phải được coi là hai hợp đồng riêng.

### 7.3. Bảng mã ZIP và `Charset.defaultCharset()`

Không dựa vào charset mặc định của OS/JVM để giải thích tên entry khi provider đã có property `encoding`. Trong code xử lý văn bản quan trọng, hãy nêu charset tường minh khi gọi API file content:

```java
String content =
        Files.readString(zip.getPath("/docs/đề-cương.txt"),
                java.nio.charset.StandardCharsets.UTF_8);
```

Đây là đoạn minh họa bên trong một ZIP filesystem đang mở, có xử lý `IOException`; `Files.readString` từ Java 11. Nó chỉ định **charset nội dung**, không thay đổi tên entry hay chính sách giải mã tên của ZIP filesystem.

## 8. Mở ZIP và đóng đúng vòng đời

ZIP filesystem là một tài nguyên cần đóng:

```java
try (FileSystem zip = FileSystems.newFileSystem(uri, env)) {
    Path entry = zip.getPath("/docs/report.txt");
    // Tạo/đọc/ghi entry ở đây.
}
```

`FileSystem` triển khai `AutoCloseable/Closeable`; `try-with-resources` đảm bảo gọi `close()` khi ra khỏi khối, kể cả khi có exception trong thân khối.

### 8.1. Vì sao `close` quan trọng khi ghi ZIP?

Provider có thể cần cập nhật cấu trúc và hoàn tất archive khi đóng ZIP filesystem. Vì vậy **không coi ghi entry thành công bên trong khối là bảo đảm archive bên ngoài đã hoàn tất bền vững trước khi close**.

Nên kiểm tra/tải archive sau khi khối `try-with-resources` đã hoàn tất thành công. Bản thân `close()` cũng có thể ném `IOException`; nếu bỏ qua lỗi đóng, ứng dụng có nguy cơ báo rằng ZIP đã tạo thành công trong khi chưa thể chắc chắn kết quả.

### 8.2. Không tiếp tục dùng `Path` của ZIPFS đã đóng

```java
Path inside;
try (FileSystem zip = FileSystems.newFileSystem(uri, env)) {
    inside = zip.getPath("/docs/report.txt");
}

// Không tiếp tục Files.writeString(inside, ...) sau khi ZIP FileSystem đóng.
```

Đây là ví dụ cố ý nhấn mạnh lỗi vòng đời. `inside` vẫn là một object `Path`, nhưng provider/file system gắn với nó đã đóng. Thao tác I/O có thể gặp `ClosedFileSystemException`.

Không giữ một ZIP entry `Path` làm tài nguyên I/O sử dụng xuyên nhiều thread sau khi owner đã đóng `FileSystem`.

### 8.3. Không xóa archive khi còn mở

Với ứng dụng cần tạo lại archive mới, đừng xóa hoặc thay thế tệp ZIP host trong khi ZIP filesystem đang mở. Hành vi giữa các OS có thể khác; có thể gặp lỗi file lock, mất dữ liệu hoặc trạng thái mâu thuẫn.

Chọn một owner và quy trình tạo: tạo trong thư mục tạm/đích, ghi các entry, đóng thành công, xác minh rồi công bố file theo hợp đồng. Nếu muốn đảm bảo không ghi đè output cũ, xử lý rõ trường hợp tên archive đã tồn tại.

### 8.4. Một URI ZIP đã mở

Cố mở hai lần cùng một `jar:` URI mà không đóng filesystem cũ có thể dẫn đến `FileSystemAlreadyExistsException`. Nếu component khác cần truy cập, có thể chia sẻ `FileSystem` theo một chính sách quản lý ownership rõ ràng, hoặc dùng API tra cứu filesystem đã mở khi phù hợp. Đừng để một component tự đóng file system mà component khác còn cần dùng.

## 9. File tên Unicode, normalization và ứng dụng đa nền tảng

`encoding=UTF-8` giải quyết việc **mã hóa tên entry**, nhưng không tự giải quyết mọi khác biệt về tên:

- Unicode có thể có nhiều cách biểu diễn dấu bằng code point (ví dụ ký tự dựng sẵn hoặc dạng tổ hợp). Hai chuỗi hiển thị tương tự vẫn có thể khác sequence Unicode.
- Một số OS/file system có quy tắc phân biệt chữ hoa/chữ thường khác nhau; đừng mặc định cách so tên của ZIP entry giống toàn bộ OS.
- Tên file có thể chứa ký tự đặc biệt, dấu cách, hoặc các byte không hợp lệ với charset bạn cố dùng.
- Không xem một tên entry đã giải mã được là bằng chứng nó đáng tin hay an toàn để dùng trong mọi vị trí.

**Gợi ý khi xuất ZIP mới:** dùng tên entry ổn định, chuẩn hóa Unicode theo yêu cầu nghiệp vụ nếu cần, tránh đặt tên chỉ khác nhau ở chữ hoa/thường cho các tích hợp nhạy cảm, và thống nhất UTF-8.

Nếu tên entry được người dùng nhập, xác thực theo chính sách ứng dụng, không nối chuỗi không tin cậy vào path host hoặc archive mà không kiểm tra. Encoding đúng **không phải security validation**.

## 10. Giao tiếp với `Files.copy` và dữ liệu nhị phân

Khi ZIP filesystem đang mở, có thể dùng các API `Files` để chuyển byte giữa host và ZIP entry:

```java
Path source = Path.of("images", "photo.png");
Path entry = zip.getPath("/images/photo.png");

Files.createDirectories(entry.getParent());
Files.copy(source, entry);
```

Đây là đoạn minh họa trong phương thức có biến `zip` là ZIP `FileSystem` đang mở và xử lý `IOException`. Nếu entry đã có, `Files.copy` thường thất bại trừ khi có tùy chọn thay thế phù hợp.

**Điểm quan trọng:** sao chép bytes không đồng nghĩa chuyển mã tên entry hoặc chuyển mã nội dung ảnh. ZIPFS xử lý tên entry theo `encoding`; việc copy dữ liệu nhị phân giữ nội dung theo byte và chịu hợp đồng `Files.copy`.

### 10.1. Đọc một entry ra host

```java
Path archiveEntry = zip.getPath("/docs/report.txt");
Path output = Path.of("exports", "report.txt");

Files.createDirectories(output.getParent());
Files.copy(archiveEntry, output);
```

Đây là đoạn minh họa trên dữ liệu **đáng tin**, không phải quy trình giải nén archive từ người dùng bất kỳ. Với archive không tin cậy, kiểm soát đường dẫn đích để tránh traversal/ghi đè; không lấy tên entry rồi dùng trực tiếp như đường dẫn tuyệt đối trên host.

### 10.2. Không nhầm `encoding` với nén dữ liệu

ZIP lưu byte của nội dung có thể theo phương pháp nén phù hợp. `encoding` chỉ điều khiển charset **tên entry**, không phải kiểu nén, mức nén, checksum hay encryption. Không thay property encoding với hy vọng ZIP nhỏ hơn hoặc giải nén nhanh hơn.

## 11. Lỗi thường gặp và cách phản ứng

| Tình huống | Biểu hiện có thể gặp | Hướng xử lý |
| --- | --- | --- |
| `create=false` và archive chưa có | `NoSuchFileException` trên provider chuẩn | Báo archive thiếu hoặc chọn chế độ tạo mới theo hợp đồng |
| `create=true` nhưng không có quyền tạo file host | `AccessDeniedException`/`IOException` khác | Kiểm tra quyền và thư mục đích; không tự nâng quyền |
| Archive hiện có nhưng không hợp lệ | `ZipException`/`IOException` khi mở | Không ghi đè file gốc âm thầm; báo lỗi định dạng |
| Provider `jar` không có trong runtime image | `ProviderNotFoundException` hoặc lỗi provider phù hợp | Bổ sung module `jdk.zipfs` hoặc dùng giải pháp được triển khai |
| Cùng `jar:` URI đã mở bằng `newFileSystem` | `FileSystemAlreadyExistsException` | Quản lý owner/lifecycle hoặc dùng filesystem đã mở |
| Entry đã tồn tại khi dùng `CREATE_NEW` | `FileAlreadyExistsException` | Đổi tên hoặc từ chối trùng, không xóa cũ vô điều kiện |
| Tên entry không biểu diễn được bằng charset | Lỗi encoding/`IOException` hoặc lỗi theo provider | Chọn UTF-8 cho ZIP mới, điều tra nguồn archive cũ |
| Sai encoding khi đọc archive cũ | Tên sai dấu hoặc archive bị từ chối | Xác minh charset từ nguồn tạo, không đoán bừa |
| `FileSystem` đã đóng | `ClosedFileSystemException` khi dùng entry path | Giới hạn dùng ZIP path trong thời gian mở |
| `close()` thất bại | `IOException` khi hoàn tất filesystem | Không coi archive đã hoàn tất thành công |
| ZIP có entry độc hại khi trích xuất | Nguy cơ traversal/ghi đè, ZIP bomb | Validate paths, quota byte/số entry, kiểm soát resource |
| Dùng `Files.writeString` nhưng quên charset | Ngữ nghĩa nội dung không rõ cho tích hợp | Nêu charset nội dung, thường `UTF-8` |

**Không phân loại lỗi chỉ dựa vào chuỗi `exception.getMessage()`.** Các message từ provider có thể phụ thuộc JDK, OS và ngôn ngữ. Ưu tiên lớp exception, ngữ cảnh thao tác và kiểm tra trực tiếp đầu vào/đầu ra.

### 11.1. `create=true` không phải giấy phép ghi đè

Một lỗi định dạng trong ZIP đang có **không phải** chỉ thị xóa archive rồi tạo mới. Archive hiện có có thể chứa dữ liệu người dùng hoặc sản phẩm của tiến trình khác. Nếu cần thay archive, thiết kế một quy trình xuất mới, ghi sang file tạm, xác minh, rồi thay thế theo nghiệp vụ được cho phép.

### 11.2. Bảng mã sai không có nghĩa content cũng sai

Nếu tên mục bị lỗi ký tự nhưng nội dung nhị phân vẫn đọc được, đừng vô điều kiện chuyển mã lại nội dung file. Cần xác định **lớp bị sai**: entry name bytes, metadata của archive, hay content bytes. Đối với nội dung text, xác định charset riêng của từng định dạng.

### 11.3. Với archive bên ngoài cần kiểm soát quy mô

Tệp ZIP nhỏ có thể chứa nhiều dữ liệu giải nén hoặc hàng nghìn entry. Khi đọc từ nguồn không tin cậy, đặt giới hạn số lượng entry, dung lượng đã giải nén, kích thước file, thời gian và tổng byte, đồng thời chặn đường dẫn trích xuất vượt root. `encoding` và `create` **không thay thế những biện pháp bảo vệ đó**.

## 12. Chương trình Java 17+ hoàn chỉnh đã kiểm thử

Chương trình minh họa ba mục tiêu:

1. **Không tạo archive** khi `create=false`: file `absent.zip` chưa tồn tại dẫn đến `NoSuchFileException`.
2. **Tạo ZIP bằng UTF-8**: thêm entry tên tiếng Việt `/docs/đề-cương.txt`, dùng `CREATE_NEW` ngăn ghi đè, đóng archive rồi mở lại để xác minh tên Unicode và nội dung UTF-8.
3. **Tương thích bảng mã tên mục cũ có chủ đích**: tạo một ZIP fixture thử nghiệm với tên `café.txt` (biểu diễn được trong `Cp437`), đọc lại tên bằng `Cp437`, nhưng **nội dung text vẫn ghi/đọc bằng UTF-8**. Phần này chỉ phục vụ kiểm thử tính độc lập của hai loại encoding; khi tạo archive mới phục vụ sản phẩm, **ưu tiên UTF-8**, không khuyến nghị chọn Cp437.

Toàn bộ file test được tạo dưới thư mục tạm và dọn sau khi chạy. Không sửa/xóa ZIP thật của người dùng.

### 12.1. Mã chạy đầy đủ: `ZipCreateEncodingDemo.java`

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Map;

public final class ZipCreateEncodingDemo {
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    private static URI zipUri(Path archive) {
        return URI.create("jar:" + archive.toUri());
    }

    public static void main(String[] args) throws IOException {
        Path work = Files.createTempDirectory("zip-encoding-demo-");
        Path modern = work.resolve("modern.zip");
        Path historical = work.resolve("historical.zip");
        Path absent = work.resolve("absent.zip");

        try {
            try {
                FileSystems.newFileSystem(zipUri(absent),
                        Map.of("create", "false", "encoding", "UTF-8")).close();
                throw new AssertionError("missing ZIP must not be created");
            } catch (NoSuchFileException expected) {
                System.out.println("create=false missing = NoSuchFileException");
            }

            try (FileSystem zip = FileSystems.newFileSystem(
                    zipUri(modern),
                    Map.of("create", "true", "encoding", "UTF-8"))) {
                Path docs = zip.getPath("/docs");
                Files.createDirectory(docs);
                Path note = docs.resolve("đề-cương.txt");
                Files.writeString(note, "Xin chào ☕\n",
                        StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);

                System.out.println("ZIP entry created = " + Files.exists(note));

                try {
                    Files.writeString(note, "overwrite forbidden",
                            StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
                    throw new AssertionError("duplicate entry must fail");
                } catch (FileAlreadyExistsException expected) {
                    System.out.println(
                            "CREATE_NEW duplicate = FileAlreadyExistsException");
                }
            }

            check(Files.size(modern) > 0, "ZIP archive bytes");
            System.out.println("ZIP archive exists = " + Files.exists(modern));

            try (FileSystem zip = FileSystems.newFileSystem(
                    zipUri(modern),
                    Map.of("create", "false", "encoding", "UTF-8"))) {
                String name = zip.getPath("/docs/đề-cương.txt")
                        .getFileName().toString();
                String content = Files.readString(
                        zip.getPath("/docs/đề-cương.txt"),
                        StandardCharsets.UTF_8);

                check(name.equals("đề-cương.txt"), "Unicode name round-trip");
                check(content.equals("Xin chào ☕\n"), "UTF-8 payload round-trip");

                System.out.println("UTF-8 name = " + name);
                System.out.println("UTF-8 content = " + content.strip());
            }

            try (FileSystem zip = FileSystems.newFileSystem(
                    zipUri(historical),
                    Map.of("create", "true", "encoding", "Cp437"))) {
                Files.writeString(zip.getPath("/café.txt"), "Nội dung UTF-8",
                        StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
            }

            try (FileSystem zip = FileSystems.newFileSystem(
                    zipUri(historical),
                    Map.of("create", "false", "encoding", "Cp437"))) {
                String content = Files.readString(
                        zip.getPath("/café.txt"), StandardCharsets.UTF_8);
                check(content.equals("Nội dung UTF-8"),
                        "payload independent of name charset");
                System.out.println("Cp437 name = "
                        + zip.getPath("/café.txt").getFileName());
                System.out.println("Cp437 content = " + content);
            }
        } finally {
            Files.deleteIfExists(modern);
            Files.deleteIfExists(historical);
            Files.deleteIfExists(absent);
            Files.deleteIfExists(work);
        }
        System.out.println("cleanup = done");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 ZipCreateEncodingDemo.java
java ZipCreateEncodingDemo
```

**Stdout chính xác đã kiểm chứng trên JDK 17 có `jdk.zipfs` và charset `Cp437`:**

```text
create=false missing = NoSuchFileException
ZIP entry created = true
CREATE_NEW duplicate = FileAlreadyExistsException
ZIP archive exists = true
UTF-8 name = đề-cương.txt
UTF-8 content = Xin chào ☕
Cp437 name = café.txt
Cp437 content = Nội dung UTF-8
cleanup = done
```

### 12.2. Vì sao `create=false` không tạo archive?

Tệp `absent.zip` chưa có và map môi trường yêu cầu `create=false`. Provider ZIPFS từ chối mở và ném `NoSuchFileException` trong môi trường kiểm thử. Đây là khác biệt giữa **mở ZIP đã có** và **tạo archive mới khi thiếu**.

Không có lệnh nào tạo `absent.zip`; biến được dùng chỉ như tên của trường hợp lỗi.

### 12.3. Vì sao có `CREATE_NEW` khi tạo entry?

`create=true` đảm bảo archive host được tạo nếu còn thiếu. Nó **không kiểm soát** xem `/docs/đề-cương.txt` đã có hay chưa. `StandardOpenOption.CREATE_NEW` kiểm soát **riêng entry**: lệnh thứ hai cố tạo trùng tên thất bại bằng `FileAlreadyExistsException`, không ghi đè nội dung ban đầu.

Việc mở lại archive và đọc được “Xin chào ☕” xác nhận dữ liệu nội dung đã được giữ nguyên sau lần tạo trùng bị từ chối.

### 12.4. Vì sao đóng rồi mở lại?

ZIPFS có vòng đời ghi/đóng. Bằng cách kết thúc khối `try-with-resources` rồi mở ZIP mới bằng `create=false`, chương trình chứng minh archive trên host là tệp ZIP thực sự có thể mở lại, chứa entry với tên Unicode và nội dung được ghi đúng.

Nếu chỉ đọc ngay trong một filesystem đang mở, chưa chứng minh rằng archive đã hoàn tất và có thể đọc lại sau close.

### 12.5. Vì sao ví dụ dùng cả `Cp437`?

`Cp437` trong ví dụ là **fixture thử nghiệm tương thích tên mục của dữ liệu lịch sử**, không phải hướng dẫn chọn bảng mã này cho ZIP xuất ra của phần mềm mới. Tên `café.txt` có ký tự `é` phù hợp với charset đó. Chương trình đọc lại bằng đúng tên charset đã dùng khi tạo fixture.

Điều then chốt: nội dung `"Nội dung UTF-8"` vẫn được ghi và đọc bằng `StandardCharsets.UTF_8`, cho thấy tên mục và content có thể sử dụng **hai charset độc lập**.

Không suy từ ví dụ rằng tất cả archive ZIP cũ đều dùng Cp437. Một archive thực tế có thể dùng Unicode hoặc bảng mã khác; phải dựa vào nguồn/định dạng và kiểm chứng metadata, không đoán.

### 12.6. Giới hạn môi trường của test

- JDK/runtime image cần có ZIP filesystem provider (`jdk.zipfs` trên JDK 9+).
- Phải có quyền tạo/đọc/ghi/xóa file trong thư mục tạm.
- Charset `Cp437` phải được runtime hỗ trợ.
- File system không được thay đổi các tên thử nghiệm bởi một tác nhân ngoài.
- Nếu provider khác hoặc file system gặp lỗi, test có thể ném exception thay vì in đủ dòng; đó là giới hạn runtime/I/O, không phải một điều kiện mà `create/encoding` luôn tự sửa được.

Khối `finally` chỉ xóa tệp do chương trình tạo trong thư mục tạm; chương trình không dọn toàn bộ thư mục người dùng theo một tên đầu vào ngẫu nhiên.

## 13. Kiểm thử có mục tiêu và tiêu chí thành công

Một bộ test thực tế nên chia theo **tác vụ** thay vì chỉ kiểm tra “đã gọi API”:

| Ca kiểm thử | Chuẩn bị | Xác minh |
| --- | --- | --- |
| Archive thiếu, `create=false` | Đường dẫn chưa có file ZIP | Không có archive mới được tạo; thao tác mở thất bại |
| Archive thiếu, `create=true` | Đường dẫn mới, thư mục cha cho phép ghi | Tạo được ZIP, có thể đóng/mở lại |
| ZIP đã có hợp lệ, `create=true` | Tạo archive trước | Không tự xóa toàn bộ entry cũ |
| Entry chưa có + `CREATE_NEW` | ZIP đang mở, parent entry đã tồn tại | Tạo entry thành công |
| Entry đã có + `CREATE_NEW` | Tạo entry trước | Không ghi đè nội dung cũ; nhận lỗi phù hợp |
| Tên entry tiếng Việt | Dùng `encoding=UTF-8` | Tên Unicode đọc lại đúng sau khi close/reopen |
| Nội dung UTF-8 | Ghi/đọc cùng `StandardCharsets.UTF_8` | So khớp content hoặc so byte chính xác |
| Archive lịch sử có charset được xác minh | Fixture test theo charset tương ứng | Tên entry giải mã đúng, content giải mã riêng |
| Archive hỏng | File không phải ZIP hợp lệ | Thất bại có kiểm soát, không xóa file gốc |
| ZIPFS không được cung cấp | Runtime image không có provider | Thông báo rõ điều kiện, không crash âm thầm |
| Cùng URI đang mở | Đăng ký ZIP filesystem trước | Xử lý việc mount trùng/lifecycle đúng |
| Close sau khi ghi | Tạo entry rồi đóng | Archive có thể mở lại; xử lý lỗi close |

### 13.1. Không kiểm thử charset bằng cách chỉ đọc tên ASCII

Tên `hello.txt` có các byte ASCII, nên nhiều charset đều giải mã giống nhau. Nếu bài kiểm thử muốn chứng minh dùng UTF-8 cho tên, cần một tên chứa ký tự **ngoài ASCII**, như `đề-cương.txt`, sau đó close/reopen và so sánh chính xác tên.

### 13.2. So sánh sau khi đóng để tránh “chỉ đúng trong bộ nhớ”

Khi kiểm thử tạo ZIP, hãy đóng `FileSystem` và mở lại archive để xác nhận kết quả đã được lưu và có thể đọc bởi một lần mount mới. Kiểm tra `Files.size(archive) > 0` có thể hữu ích như dấu hiệu file có byte, nhưng **không đủ** để chứng minh toàn bộ ZIP/entry hợp lệ; phải thật sự đọc tên và nội dung.

### 13.3. Tránh test phụ thuộc thông điệp lỗi OS

Với `NoSuchFileException` hoặc `FileAlreadyExistsException`, ưu tiên xác minh **loại ngoại lệ** và trạng thái tệp, không so sánh `getMessage()` với chuỗi tiếng Anh cụ thể. Provider có thể thay đổi message theo hệ điều hành/JDK.

### 13.4. Không cần kiểm tra mọi charset trên một archive duy nhất

Nếu muốn hỗ trợ archive cũ, nên có fixture biết rõ tên charset và tên entry mong đợi, test riêng. Việc thử nhiều charset trên một archive không có thông tin nguồn rồi xem tên nào “có vẻ đúng” có thể dẫn tới dữ liệu sai, trùng tên hoặc ghi lại hỏng.

## 14. Những lỗi và nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `create=true` sẽ luôn tạo một ZIP mới, xóa ZIP cũ | Khi archive đã tồn tại hợp lệ, nó có thể được mở | Không coi là chế độ replace; có chính sách output riêng |
| `create=true` làm `/docs/file.txt` tự xuất hiện | Chỉ tạo archive host nếu thiếu | Tạo entry bằng `Files` trên `zip.getPath` |
| `CREATE_NEW` của entry có cùng nghĩa với env `create` | Hai lớp tùy chọn độc lập | Phân biệt tạo archive vs tạo entry |
| `encoding=UTF-8` chuyển mã nội dung mọi file text | Điều khiển tên entry | Truyền charset riêng cho `readString/writeString` |
| Java chạy trên Windows thì ZIP name phải dùng code page của Windows | ZIPFS có chính sách encoding riêng, mặc định UTF-8 | Dùng UTF-8 với archive mới |
| Chọn `Charset.defaultCharset()` cho ZIP tên Unicode | Mặc định JVM/OS không quyết định chuẩn ZIP đang dùng | Nêu encoding có chủ đích |
| Chọn Cp437 cho mọi ZIP lịch sử | Không phải archive cũ nào cũng dùng Cp437 | Dựa vào nguồn và metadata đáng tin |
| UTF-8 bị lỗi nên chuyển sang charset khác tùy ý | Có thể khiến tên sai lệch hơn | Chẩn đoán encoding từ nguồn tạo |
| ZIP entry `Path` có thể dùng sau khi `zip.close()` | FileSystem đã đóng | Giới hạn vòng đời dùng entry path |
| `Files.exists(archive)` bảo đảm là ZIP hợp lệ | Chỉ xác định trạng thái tồn tại tại một thời điểm | Thử mở ZIP và xử lý lỗi |
| Tệp ZIP hiện có không hợp lệ sẽ được tạo lại với `create=true` | Không tự sửa archive hỏng | Báo lỗi, không phá file cũ |
| `FileSystems.newFileSystem` trùng URI không có rủi ro | Có thể gặp `FileSystemAlreadyExistsException` | Quản lý mount và ownership |
| Không cần đóng ZIPFS sau khi ghi entry | Archive có thể chưa được hoàn tất | `try-with-resources`, xử lý lỗi close |
| `Path.of("reports.zip").resolve(...)` là entry path | Đó là host path | Dùng `zip.getPath("/")` và `resolve` |
| Dùng backslash làm dấu phân cách entry trên Windows | ZIPFS dùng quy tắc path riêng | Dùng `/` qua API ZIPFS |
| `Files.copy` tự chuyển mã dữ liệu text | Chủ yếu copy byte theo hợp đồng | Xử lý charset text riêng nếu cần |
| Tên entry đã giải mã đúng đồng nghĩa an toàn để extract | Có thể chứa tên độc hại/traversal | Validate host destination, quota và ownership |
| Chỉ thấy `size > 0` là ZIP đã đúng | Có thể vẫn không mở/đọc được | Reopen và kiểm chứng entry |
| Muốn xóa file output cũ thì cứ gọi `delete` trước khi mở ZIP | Có thể phá dữ liệu hợp lệ | Thiết kế overwrite/rollback có kiểm soát |
| Coi ZIPFS là filesystem dùng chung cho mọi thread không cần đồng bộ | Có thể gặp cập nhật cạnh tranh/lifecycle | Xác định owner, quản lý concurrency |

## 15. Bài tập thực hành kèm đáp án

### Bài 1 — Hai kiểu tạo mới

Một ứng dụng tạo `result.zip` rồi thêm `report.txt` vào archive. Tùy chọn nào điều khiển tạo archive, và tùy chọn nào giúp tránh ghi đè `report.txt`?

**Đáp án:** Environment property `"create"="true"` cho ZIP filesystem; `StandardOpenOption.CREATE_NEW` trên `Files.writeString`/`newOutputStream` cho entry. Hai tùy chọn có phạm vi khác nhau.

### Bài 2 — Mặc định của `create`

Nếu không truyền `create` và tệp archive chưa tồn tại, ZIPFS có tự tạo file không?

**Đáp án:** Không. Mặc định là `false`; provider chuẩn có thể ném `NoSuchFileException` khi mở archive thiếu.

### Bài 3 — Mở lại ZIP đã có

Có một ZIP hợp lệ đang chứa `docs/report.txt`. Mở bằng `create=true` có tự xóa entry đó không?

**Đáp án:** Không vì `create=true` chỉ cho phép tạo archive khi chưa tồn tại, không phải một lệnh xóa/làm mới archive đã có.

### Bài 4 — Tên mục tiếng Việt

Muốn tạo `/docs/đề-cương.txt` và đọc đúng dấu sau khi đóng/mở ZIP trên Java hiện đại, nên chọn `encoding` nào?

**Đáp án:** `UTF-8`, cũng là mặc định của ZIPFS chuẩn. Dùng cùng chính sách tạo/đọc tên và xác minh sau khi reopen.

### Bài 5 — Bảng mã tên vs bảng mã nội dung

Một ZIP dùng `encoding=UTF-8`, nhưng file `/notes.txt` bên trong chứa byte văn bản UTF-16. Có thể mặc định `Files.readString(path, UTF_8)` cho kết quả đúng không?

**Đáp án:** Không. `encoding` xử lý tên entry, còn byte nội dung phải đọc bằng charset tương ứng, ví dụ UTF-16 nếu đúng là encoding của file nội dung.

### Bài 6 — Tên ASCII có đủ để test encoding?

Một test tạo tên `a.txt` và đọc lại thấy đúng dưới `encoding=UTF-8`. Nó có chứng minh ZIP giữ được tên tiếng Việt không?

**Đáp án:** Chưa. ASCII được nhiều charset giải mã giống nhau. Nên có fixture tên chứa ký tự ngoài ASCII như `đề-cương.txt` để xác minh việc round-trip.

### Bài 7 — ZIP từ ứng dụng cũ

Bạn có archive do một hệ thống cũ tạo, tên entry sai dấu khi đọc mặc định. Có nên tự chuyển toàn bộ nội dung từ UTF-8 sang Cp437 không?

**Đáp án:** Không. Cần xác định charset của **entry names** từ nguồn, chọn property `encoding` phù hợp nếu cần, còn nội dung mỗi file phải xử lý riêng. Không dùng đoán mò charset để tự viết lại archive.

### Bài 8 — File ZIP không hợp lệ

`reports.zip` tồn tại nhưng chứa byte ngẫu nhiên không phải định dạng ZIP. Gọi `newFileSystem(uri, Map.of("create","true"))` có buộc tạo ZIP mới và ghi đè file cũ không?

**Đáp án:** Không. `create=true` không phải chế độ “sửa ZIP hỏng” hay “xóa rồi tạo lại”. Provider có thể báo lỗi định dạng; ứng dụng cần xử lý mà không phá dữ liệu gốc.

### Bài 9 — Entry trùng tên

Trong ZIPFS, `Files.writeString(path, text, UTF_8, CREATE_NEW)` được gọi với entry đã có. Kết quả mong đợi trên provider chuẩn?

**Đáp án:** `FileAlreadyExistsException`. Lệnh không được âm thầm ghi đè entry theo chính sách `CREATE_NEW`.

### Bài 10 — ZIPFS đã đóng

Bạn lưu `Path entry = zip.getPath("/notes.txt")` rồi đóng `zip`. Có thể dùng `Files.writeString(entry,...)` ngay sau đó không?

**Đáp án:** Không. Entry `Path` gắn với file system đã đóng, thao tác có thể ném `ClosedFileSystemException`. Muốn dùng lại, mở filesystem mới và lấy `Path` trong scope mới.

### Bài 11 — Dùng host Path làm entry?

`Path archive = Path.of("a.zip"); Path entry = archive.resolve("inside.txt");` có làm `inside.txt` nằm trong ZIP không?

**Đáp án:** Không. `archive.resolve` chỉ tạo đường dẫn host kiểu `a.zip/inside.txt`. Phải mở ZIPFS và lấy `zip.getPath("/inside.txt")`.

### Bài 12 — Khi nào dùng `Map.of`?

`FileSystems.newFileSystem(uri, Map.of("create","true"))` là ví dụ Java 7 thuần túy không cần chỉnh sửa không?

**Đáp án:** Phương thức ZIPFS và property `create` có từ Java 7, nhưng `Map.of` chỉ có từ Java 9. Với source Java 7 dùng `HashMap<String,String>`; trên JDK 17 dùng `Map.of` như trong ví dụ hoàn chỉnh.

### Bài 13 — Lỗi file system đã mở

Bạn có `FileSystem` cùng một `jar:` URI đang mở và gọi `newFileSystem(uri,env)` lần nữa. Điều gì cần tính tới?

**Đáp án:** Có thể gặp `FileSystemAlreadyExistsException`. Quản lý lifecycle của file system đã mở, đóng khi owner thật sự xong hoặc chia sẻ tham chiếu theo chính sách.

### Bài 14 — Kiểm tra archive sau khi tạo

Vì sao không chỉ dùng `Files.exists(archive)` mà cần mở lại và đọc entry sau khi close?

**Đáp án:** Sự tồn tại không xác nhận cấu trúc ZIP, encoding tên hay byte nội dung đúng. Reopen + so sánh tên Unicode và nội dung giúp kiểm chứng kết quả thực.

### Bài 15 — Bảo vệ khi giải nén

Tại sao tên entry đã decode đúng UTF-8 vẫn có thể gây rủi ro nếu lấy thẳng nó làm đường dẫn host?

**Đáp án:** Encoding đúng không phải kiểm tra an toàn. Tên có thể mang traversal, dấu phân cách hoặc thành phần không được phép. Khi extract phải kiểm tra thư mục đích, chuẩn hóa/giới hạn root, chống thay đổi symbolic link và đặt quota để tránh ghi đè hoặc quá tải.

### Bài 16 — ZIPFS không có trong runtime tùy biến

Một ứng dụng chạy trên custom Java runtime không tìm thấy provider `jar`. Đổi `encoding` từ UTF-8 sang charset khác có sửa lỗi được không?

**Đáp án:** Không. Vấn đề là **provider/module** không hiện diện hoặc không được tải, không phải bảng mã tên. Cần bảo đảm runtime có `jdk.zipfs` hoặc thay đổi cách triển khai đọc ZIP.

## 16. Checklist áp dụng vào hệ thống thực

- [ ] Phân biệt **ZIP host file** với **entry Path** bên trong `FileSystem`.
- [ ] Xây dựng `jar:` URI từ `archive.toUri()` thay vì nối raw OS path chưa escape.
- [ ] Chỉ dùng env `create=true` khi thực sự muốn provider tạo archive **nếu thiếu**.
- [ ] Không coi `create=true` là lệnh truncate/xóa archive cũ.
- [ ] Dùng `CREATE_NEW` cho entry khi muốn từ chối trùng tên, không dựa vào check-then-write.
- [ ] Dùng UTF-8 làm chính sách tên entry cho ZIP mới; hiểu mặc định UTF-8 của `jdk.zipfs`.
- [ ] Nếu buộc đọc ZIP cũ với charset khác, có bằng chứng charset nguồn và test fixture phù hợp.
- [ ] Phân biệt `encoding` của ZIPFS với `Charset` để đọc/ghi nội dung text.
- [ ] Không áp dụng charset text cho nội dung nhị phân hoặc tự chuyển mã dữ liệu không rõ định dạng.
- [ ] Tạo directory/entry bằng `zip.getPath(...)` và API `Files` trên ZIP filesystem.
- [ ] Quản lý vòng đời `FileSystem` bằng `try-with-resources` và xử lý lỗi khi đóng.
- [ ] Sau khi đóng, không tiếp tục sử dụng `Path` entry gắn với filesystem cũ.
- [ ] Xử lý lỗi archive thiếu, archive hỏng, entry trùng, provider thiếu và mount trùng bằng exception phù hợp.
- [ ] Không dựa vào thông điệp `getMessage()` của OS/provider để phân loại lỗi.
- [ ] Nếu archive quan trọng, ghi ra file tạm/có kiểm chứng và không phá dữ liệu cũ khi thất bại.
- [ ] Với archive không tin cậy, validate đường dẫn khi extract, quota entry/byte và chính sách resource.
- [ ] Test tên Unicode sau khi **close rồi reopen**, không chỉ tên ASCII.
- [ ] Test nội dung text bằng charset tường minh và kiểm chứng byte/chuỗi đúng.
- [ ] Đảm bảo runtime có ZIP filesystem provider; trên Java 9+ thường là module `jdk.zipfs`.
- [ ] Ghi rõ API từ Java 7 nhưng ví dụ đầy đủ dùng `Map.of`/`Files.writeString`/`Path.of` và `strip` từ Java 9/11+, biên dịch với JDK 17.

## 17. Nguồn tham khảo API chính thức

- [Oracle JDK 17 — jdk.zipfs module](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html): ZIP filesystem provider, ý nghĩa và mặc định của các property `create`, `encoding`.
- [Oracle Java 8 — ZIP File System Properties](https://docs.oracle.com/javase/8/docs/technotes/guides/io/fsp/zipfilesystemproviderprops.html): cách mô tả property ZIPFS từ các thế hệ JDK trước, vẫn hỗ trợ việc hiểu hai tùy chọn cốt lõi.
- [Java SE 17 — FileSystems](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html): factory để tạo/mở file system.
- [Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): ngữ nghĩa `CREATE_NEW` và các open option cho entry.

## 18. Kết luận

Trong Java NIO.2, ZIP filesystem biến một archive ZIP/JAR thành một `FileSystem` có các entry thao tác bằng `Path`. **`create`** là property quyết định có **tạo file archive** khi nó chưa tồn tại; mặc định **`false`**. **`encoding`** quyết định cách biểu diễn/giải mã **tên mục ZIP**, mặc định **`UTF-8`** trên ZIP filesystem provider chuẩn. Hai property này không kiểm soát việc tạo **entry** hay bảng mã **nội dung** của từng tệp.

Khi tạo ZIP mới, ưu tiên **UTF-8**, kiểm soát trùng entry với `CREATE_NEW` khi cần, dùng `zip.getPath` cho tên mục, đóng filesystem bằng `try-with-resources` và xác minh bằng cách **mở lại archive**. Khi phải hỗ trợ ZIP cũ, chỉ chọn charset khác theo thông tin đáng tin và không đồng nhất tên file với payload. Kết hợp chính sách không ghi đè, quản lý vòng đời, kiểm thử Unicode, xử lý exception và kiểm soát archive không tin cậy sẽ giúp chương trình ZIP hiện đại ít mất dữ liệu và khả chuyển hơn.