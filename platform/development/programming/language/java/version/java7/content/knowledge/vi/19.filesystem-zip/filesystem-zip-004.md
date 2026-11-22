# Truy cập ZIP hoặc JAR như một cây đường dẫn với Java NIO

## 1. Mở đầu: một file chứa cả một cây file

Thông thường, một tập tin `.zip` hoặc `.jar` chỉ xuất hiện là **một file** trên ổ đĩa. Nhưng nội dung của nó có thể tổ chức thành các thư mục và tệp:

~~~text
bundle.zip
├── readme.txt
├── docs/
│   └── notes.txt
└── src/
    └── Main.java
~~~

Java NIO.2 cung cấp ZIP File System Provider để coi archive đó như một **FileSystem** độc lập. Sau khi mở bằng `FileSystems.newFileSystem`, ta có thể dùng các API quen thuộc như `Path`, `Files.walk`, `Files.readString`, `Files.copy`, `Files.writeString` và `Files.delete` để thao tác với từng entry **mà không cần giải nén toàn bộ ZIP ra thư mục tạm**.

Ví dụ ý tưởng:

~~~java
try (FileSystem zipfs =
             FileSystems.newFileSystem(zipPath, Map.of())) {
    Path root = zipfs.getPath("/");
    Path file = root.resolve("docs/notes.txt");

    if (Files.isRegularFile(file)) {
        String content =
                Files.readString(file, StandardCharsets.UTF_8);
    }
}
~~~

Đây là đoạn **trong một phương thức**, với `zipPath` là `Path` của file archive bên ngoài; cần import `java.nio.file.*`, `java.nio.charset.StandardCharsets` và `java.util.Map`. Nó không phải class chạy độc lập. Archive phải tồn tại và provider cần hỗ trợ định dạng. `FileSystem` là tài nguyên cần được đóng trong try-with-resources.

### Mục tiêu bài học

- Phân biệt **Path của file ZIP/JAR trên máy** và **Path của entry bên trong ZIP/JAR**.
- Mở một archive sẵn có, tạo archive mới khi cần và lấy root `/` của ZIP filesystem.
- Duyệt toàn cây entry với `Files.walk`; liệt kê một thư mục với `Files.list` hoặc `DirectoryStream`.
- Đọc/ghi text bằng charset rõ ràng; sao chép binary giữa filesystem thường và ZIP filesystem.
- Mở JAR bằng URI có scheme `jar:`, xem `META-INF/MANIFEST.MF` và phân biệt với `JarFile`.
- Thực hiện move/delete entry, xử lý resource lifetime và lỗi khi dùng Path sau khi đóng FileSystem.
- Hiểu cấu hình `create`, `encoding`, `compressionMethod`, `releaseVersion` và điểm khác nhau giữa JDK 17 với tài liệu Java SE 26 về `accessMode`.
- Nhận biết giới hạn provider, tên entry có `.`/`..`, rủi ro ZIP Slip/ZIP bomb, JAR signatures và việc dùng `toFile()` sai.
- Tự chạy các chương trình Java 17+ để đối chiếu stdout chính xác.

**Phiên bản:** ZIP filesystem provider được giới thiệu từ **JDK 7**, vẫn có trong JDK hiện đại. Từ Java 9, implementation của JDK được đóng gói trong module `jdk.zipfs`. Các ví dụ **độc lập** trong bài dùng Java 17+, đã được biên dịch bằng `javac -encoding UTF-8 --release 17` và chạy với JDK 17 trên Windows. Những thuộc tính chỉ được xác nhận trong tài liệu Java SE 26 sẽ được phân biệt rõ, không giả định chúng hoạt động như nhau trên JDK 17.

## 2. Mô hình FileSystemProvider, FileSystem và Path

Tưởng tượng:

~~~text
Default FileSystem (scheme "file")
└── C:\work\bundle.zip         <- một FILE trên ổ đĩa
                 |
                 | FileSystems.newFileSystem(...)
                 v
ZIP FileSystem (scheme "jar")
└── /                           <- root bên trong ZIP
    ├── readme.txt
    ├── docs/
    │   └── notes.txt
    └── src/
        └── Main.java
~~~

Hai cách truy cập này khác nhau:

~~~java
Path archive = Path.of("bundle.zip");
Path inner = zipfs.getPath("/docs/notes.txt");
~~~

- `archive` thuộc default filesystem và trỏ tới **file ZIP đã nén**.
- `inner` thuộc ZIP filesystem, trỏ tới **entry notes.txt bên trong** archive.
- `Files.readAllBytes(archive)` đọc bytes của **cả ZIP container**.
- `Files.readString(inner, UTF_8)` đọc nội dung text của **một entry đã chọn**.
- `inner.toFile()` **không** tạo được một `java.io.File` hợp lệ của entry ZIP, vì entry không phải file đơn lẻ trên default filesystem.
- `Path.of("/docs/notes.txt")` trỏ tới **default filesystem**, không phải entry trong ZIP dù chuỗi đường dẫn có thể trông giống nhau.

Bên trong ZIP, API `FileSystem.getPath(String, String...)` được gọi qua `zipfs.getPath(...)`; root thường là `zipfs.getPath("/")`. Các thao tác `Files` nhận Path và chuyển hành vi đến provider tương ứng.

### 2.1. Vì sao scheme là `jar` dù file đuôi `.zip`?

Javadoc hiện hành của module `jdk.zipfs` xác định **URI scheme `jar`** là scheme của ZIP FileSystem Provider. Nó xử lý archive ZIP **và** JAR vì JAR là một định dạng đóng gói dựa trên ZIP.

Đừng hiểu `jar:` là lệnh buộc Java chạy JAR. Nó là cách định danh một filesystem provider. Còn việc chạy một executable JAR, đọc manifest và kiểm tra chữ ký là những bài toán khác.

Nguồn: [Oracle Java SE 26 — jdk.zipfs](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.zipfs/module-summary.html).

## 3. Các cách mở và tạo ZIP/JAR

### 3.1. Mở archive có sẵn bằng Path

~~~java
Path zipFile = Path.of("report.zip");

try (FileSystem fs =
             FileSystems.newFileSystem(zipFile, Map.of())) {
    Path root = fs.getPath("/");
    // Duyệt và đọc entry bên trong archive.
}
~~~

Đây là đoạn minh họa trong phương thức. `Map.of()` là môi trường cấu hình rỗng, dùng được trong ví dụ Java 17. Không cần `create=true` khi muốn từ chối archive chưa tồn tại.

### 3.2. Tạo ZIP mới nếu file chưa có

~~~java
try (FileSystem fs = FileSystems.newFileSystem(
        zipFile, Map.of("create", "true"))) {
    Files.createDirectories(fs.getPath("/docs"));
    Files.writeString(
            fs.getPath("/docs/readme.txt"),
            "Xin chào ZIP", StandardCharsets.UTF_8);
}
~~~

Thuộc tính `create=true` của ZipFS **tạo archive nếu file không tồn tại**. Nó không có nghĩa tự xóa archive đã tồn tại, cũng không tự tạo tất cả thư mục cha của **file ZIP bên ngoài**. Một cách an toàn khi định tạo archive riêng là chọn tên file mới trong thư mục do ứng dụng quản lý và xử lý các lỗi I/O/trùng tên.

### 3.3. Mở theo URI có scheme `jar:`

~~~java
URI uri = URI.create("jar:" + zipFile.toUri());

try (FileSystem fs =
             FileSystems.newFileSystem(uri, Map.of())) {
    Path root = fs.getPath("/");
}
~~~

Đây là đoạn minh họa; import `java.net.URI`. Cách dùng `zipFile.toUri()` giúp chuyển path OS sang file URI đã được escape phù hợp hơn so với tự ghép chuỗi `jar:file:/...` từ path Windows có dấu cách/ký tự đặc biệt.

**Bẫy thường gặp:** Nếu đã có một FileSystem được mở và quản lý theo một URI, việc tạo instance trùng định danh có thể dẫn tới `FileSystemAlreadyExistsException`. Không tùy tiện mở/đóng một archive trong nhiều thành phần cùng lúc mà thiếu owner rõ ràng.

## 4. Ví dụ 1 — Tạo ZIP, duyệt cây và mở lại

Tạo file `ZipCreateDemo.java`:

~~~java
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.stream.*;

public class ZipCreateDemo {
    public static void main(String[] args) throws Exception {
        Path folder =
                Files.createTempDirectory("zip-create-");
        Path archive = folder.resolve("sample.zip");

        try {
            try (FileSystem fs = FileSystems.newFileSystem(
                    archive, Map.of("create", "true"))) {
                Path docs = fs.getPath("/docs");
                Files.createDirectories(docs);

                Files.writeString(
                        docs.resolve("notes.txt"),
                        "xin chao", StandardCharsets.UTF_8);
                Files.writeString(
                        fs.getPath("/readme.txt"),
                        "README", StandardCharsets.UTF_8);

                List<String> entries;
                try (Stream<Path> s = Files.walk(fs.getPath("/"))) {
                    entries = s.map(Path::toString)
                            .sorted()
                            .collect(Collectors.toList());
                }

                System.out.println("entries=" +
                        String.join(",", entries));
                System.out.println("fsScheme=" +
                        fs.provider().getScheme());
            }

            System.out.println("archiveExists=" +
                    Files.isRegularFile(archive));

            try (FileSystem fs =
                         FileSystems.newFileSystem(
                                 archive, Map.of())) {
                System.out.println("reopenedText=" +
                        Files.readString(
                                fs.getPath("/docs/notes.txt"),
                                StandardCharsets.UTF_8));
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

Chạy trong thư mục có mã nguồn:

~~~bash
javac -encoding UTF-8 --release 17 ZipCreateDemo.java
java ZipCreateDemo
~~~

Stdout đã kiểm chứng:

~~~text
entries=/,/docs,/docs/notes.txt,/readme.txt
fsScheme=jar
archiveExists=true
reopenedText=xin chao
~~~

**Phân tích:**

1. File ZIP ban đầu chưa tồn tại, môi trường `create=true` làm provider tạo archive.
2. `fs.getPath("/docs")` là directory **trong archive**, không phải thư mục ngoài ổ đĩa.
3. `Files.createDirectories` tạo path thư mục ZIP trước khi ghi nội dung.
4. `Files.walk(fs.getPath("/"))` đi từ root và có thể trả file/directory entry. `sorted()` giúp output ổn định.
5. `Stream<Path>` được đóng bằng try-with-resources **trước** khi đóng `FileSystem`.
6. Khi `FileSystem` đóng, ZIP vẫn tồn tại trên ổ đĩa; lần mở lại đọc được text.
7. `finally` dọn file archive thử nghiệm sau khi mọi resource đã đóng.

**Kết luận:** ZIP được xem như một **cây Path có root riêng**, có thể mở/đóng và lưu nội dung qua API NIO.

## 5. Duyệt cây và lọc entry: walk, list, DirectoryStream

| API | Phạm vi | Lưu ý |
| --- | --- | --- |
| `Files.walk(root)` | Đệ quy toàn cây từ root | Trả `Stream<Path>` cần close |
| `Files.walk(root, maxDepth)` | Đệ quy đến độ sâu giới hạn | Không tự loại directory |
| `Files.list(dir)` | Các entry trực tiếp trong dir | Trả `Stream<Path>` cần close |
| `Files.newDirectoryStream(dir)` | Các entry trực tiếp | Trả `DirectoryStream<Path>` cần close |
| `Files.newDirectoryStream(dir,"*.txt")` | Một cấp, lọc bằng glob | Glob lọc **tên entry**, không tự đệ quy |

Dùng `Files.isRegularFile(path)` khi muốn chỉ file thường, không lấy directory. Nếu metadata không xác định được vì I/O, phương thức boolean có thể false; khi cần phân loại lỗi, dùng `Files.readAttributes`.

Khi cần sắp xếp tên đầu ra, dùng `Stream.sorted()` hoặc `Collections.sort`. Không dựa vào thứ tự directory iteration do provider trả.

### 5.1. Tạo và xử lý Path trong ZIP

~~~java
Path root = fs.getPath("/");
Path folder = root.resolve("assets");
Path entry = folder.resolve("image.png");
~~~

Các Path trên đều thuộc cùng `fs`. Nếu lấy tên cuối:

~~~java
String name = entry.getFileName().toString();
~~~

sẽ được `image.png`; nhưng đừng dùng **chỉ filename** làm khóa duy nhất toàn cây. `/assets/image.png` và `/backup/image.png` có thể cùng tên nhưng khác entry.

## 6. Ví dụ 2 — Duyệt file nhiều cấp và lọc glob một thư mục

Tạo file `ZipWalkDemo.java`:

~~~java
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.stream.*;

public class ZipWalkDemo {
    public static void main(String[] args) throws Exception {
        Path folder =
                Files.createTempDirectory("zip-walk-");
        Path archive = folder.resolve("tree.zip");

        try {
            try (FileSystem fs = FileSystems.newFileSystem(
                    archive, Map.of("create", "true"))) {
                Files.createDirectories(fs.getPath("/assets"));
                Files.createDirectories(fs.getPath("/src"));
                Files.writeString(
                        fs.getPath("/assets/a.txt"),
                        "aa", StandardCharsets.UTF_8);
                Files.writeString(
                        fs.getPath("/assets/b.json"), "{}");
                Files.writeString(
                        fs.getPath("/src/Main.java"), "class Main {}");
            }

            try (FileSystem fs = FileSystems.newFileSystem(
                    archive, Map.of())) {
                List<String> files;

                try (Stream<Path> stream =
                             Files.walk(fs.getPath("/"))) {
                    files = stream
                            .filter(Files::isRegularFile)
                            .map(Path::toString)
                            .sorted()
                            .collect(Collectors.toList());
                }

                List<String> names = new ArrayList<>();
                try (DirectoryStream<Path> ds =
                             Files.newDirectoryStream(
                                     fs.getPath("/assets"),
                                     "*.txt")) {
                    for (Path path : ds) {
                        names.add(path.getFileName().toString());
                    }
                }
                Collections.sort(names);

                System.out.println("files=" +
                        String.join(",", files));
                System.out.println("txt=" +
                        String.join(",", names));
                System.out.println("rootIsDir=" +
                        Files.isDirectory(fs.getPath("/")));
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ZipWalkDemo.java
java ZipWalkDemo
~~~

Stdout:

~~~text
files=/assets/a.txt,/assets/b.json,/src/Main.java
txt=a.txt
rootIsDir=true
~~~

**Giải thích:** `Files.walk("/")` đi qua `assets` và `src`, rồi chỉ giữ regular files. `newDirectoryStream("/assets","*.txt")` chỉ xét các entry **trực tiếp** dưới `assets`. Root `/` là directory trong archive, nên `Files.isDirectory` trả true. Cả Stream và DirectoryStream được đóng trước khi FileSystem đóng.

## 7. Copy file giữa default filesystem và ZIP filesystem

Bạn có thể dùng `Files.copy` trực tiếp giữa hai providers:

~~~java
Path source = Path.of("source.bin");
Path destInZip = fs.getPath("/payloads/source.bin");

Files.createDirectories(destInZip.getParent());
Files.copy(source, destInZip);
~~~

Đây là đoạn minh họa. Nếu destination đã tồn tại, `Files.copy` có thể ném `FileAlreadyExistsException`; muốn ghi đè có chủ ý mới dùng `StandardCopyOption.REPLACE_EXISTING`. Không dùng `destInZip.toFile()`.

Khi xuất từ ZIP ra thư mục OS:

~~~java
Path sourceInZip = fs.getPath("/payloads/source.bin");
Path destLocal = Path.of("restored.bin");

Files.copy(sourceInZip, destLocal);
~~~

Ưu điểm của `Files.copy` là xử lý bytes mà không phải tải toàn bộ file vào RAM. Điều này quan trọng với file binary (ảnh, PDF, `.class`, dữ liệu nén) hoặc entry lớn. Nếu chỉ cần text, dùng `Files.readString`/`writeString` với charset rõ ràng.

### 7.1. Ví dụ 3 — Sao chép binary vào ZIP rồi lấy lại

Tạo `ZipCopyDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;

public class ZipCopyDemo {
    public static void main(String[] args) throws Exception {
        Path folder =
                Files.createTempDirectory("zip-copy-");
        Path archive = folder.resolve("bytes.zip");
        Path source = folder.resolve("source.bin");
        Path out = folder.resolve("copied.bin");

        byte[] expected = new byte[]{
                0, 1, 2, 3, 127, -1
        };

        try {
            Files.write(source, expected);

            try (FileSystem fs = FileSystems.newFileSystem(
                    archive, Map.of("create", "true"))) {
                Files.createDirectories(fs.getPath("/data"));
                Files.copy(
                        source,
                        fs.getPath("/data/payload.bin"));
            }

            try (FileSystem fs = FileSystems.newFileSystem(
                    archive, Map.of())) {
                Files.copy(
                        fs.getPath("/data/payload.bin"), out);
            }

            System.out.println("sameBytes=" +
                    Arrays.equals(
                            expected, Files.readAllBytes(out)));
            System.out.println("sourceStillExists=" +
                    Files.isRegularFile(source));
        } finally {
            Files.deleteIfExists(out);
            Files.deleteIfExists(source);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ZipCopyDemo.java
java ZipCopyDemo
~~~

Stdout:

~~~text
sameBytes=true
sourceStillExists=true
~~~

Sau khi close và reopen archive, bytes đọc ra vẫn bằng dữ liệu gốc. Đọc `Files.readAllBytes` ở đây chỉ để **assertion cho fixture 6 byte**. Trong sản phẩm với file lớn, không nạp toàn bộ bytes nếu có thể dùng streaming/copy.

## 8. JAR cũng là archive dạng cây: META-INF và manifest

Một JAR có thể chứa:

~~~text
application.jar
├── META-INF/
│   └── MANIFEST.MF
├── config/
│   └── app.properties
└── com/
    └── example/
        └── App.class
~~~

ZIP FileSystem nhìn được những entry này như `Path`. Nhưng JAR cũng có semantics riêng:

- `META-INF/MANIFEST.MF` chứa manifest; `JarFile.getManifest()` trả dữ liệu metadata có cấu trúc.
- Một JAR có thể có chữ ký; **sửa entry có thể làm chữ ký/digest không hợp lệ**.
- Một JAR có thể là *multi-release JAR*, chứa các đường dẫn `META-INF/versions/<N>/...`. Cần chính sách version khi muốn tìm “nội dung có hiệu lực” ở runtime.
- Có manifest **không tự nghĩa là JAR chạy được bằng `java -jar`**; muốn chạy cần ứng dụng/classes và thuộc tính phù hợp.

### 8.1. Ví dụ 4 — Mở JAR bằng URI scheme jar và đọc manifest

Tạo `JarTreeDemo.java`:

~~~java
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.net.URI;
import java.util.*;
import java.util.jar.*;
import java.util.stream.*;

public class JarTreeDemo {
    public static void main(String[] args) throws Exception {
        Path folder =
                Files.createTempDirectory("jar-tree-");
        Path jar = folder.resolve("module.jar");

        try {
            URI jarUri = URI.create("jar:" + jar.toUri());

            try (FileSystem fs =
                         FileSystems.newFileSystem(
                                 jarUri, Map.of("create", "true"))) {
                Files.createDirectories(
                        fs.getPath("/META-INF"));
                Files.writeString(
                        fs.getPath("/META-INF/MANIFEST.MF"),
                        "Manifest-Version: 1.0\n\n",
                        StandardCharsets.UTF_8);
                Files.createDirectories(
                        fs.getPath("/config"));
                Files.writeString(
                        fs.getPath("/config/app.properties"),
                        "enabled=true\n", StandardCharsets.UTF_8);
            }

            try (FileSystem fs =
                         FileSystems.newFileSystem(
                                 jarUri, Map.of())) {
                List<String> entries;

                try (Stream<Path> s =
                             Files.walk(fs.getPath("/"))) {
                    entries = s.filter(Files::isRegularFile)
                            .map(Path::toString)
                            .sorted()
                            .collect(Collectors.toList());
                }

                System.out.println("entries=" +
                        String.join(",", entries));
                System.out.println("property=" +
                        Files.readString(
                                fs.getPath("/config/app.properties"),
                                StandardCharsets.UTF_8).trim());
            }

            try (JarFile jf = new JarFile(jar.toFile())) {
                System.out.println("manifestVersion=" +
                        jf.getManifest()
                                .getMainAttributes()
                                .getValue("Manifest-Version"));
            }
        } finally {
            Files.deleteIfExists(jar);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 JarTreeDemo.java
java JarTreeDemo
~~~

Stdout:

~~~text
entries=/META-INF/MANIFEST.MF,/config/app.properties
property=enabled=true
manifestVersion=1.0
~~~

Ở ví dụ, ZipFS cung cấp cây path và `JarFile` đọc metadata manifest. File mẫu **không phải executable JAR** vì không chứa Main-Class/chương trình. JAR đang được chạy/deployed hoặc đã ký thường nên được **rebuild từ build pipeline**, không sửa tại chỗ qua ZipFS.

## 9. Chỉnh sửa ZIP bằng Files.move, delete và writeString

Các thao tác `Files` trên ZIP Path có semantics filesystem phù hợp với provider:

~~~java
Path oldEntry = fs.getPath("/docs/old.txt");
Path newEntry = fs.getPath("/docs/new.txt");

Files.move(oldEntry, newEntry);
Files.delete(fs.getPath("/docs/outdated.txt"));
Files.writeString(fs.getPath("/docs/current.txt"), "new data");
~~~

Đây là đoạn minh họa trong một phương thức. Việc chỉnh sửa archive có thể tốn I/O khi provider phải ghi lại ZIP; không coi một ZIP FS là cơ sở dữ liệu với transaction isolation/rollback đầy đủ.

### 9.1. Ví dụ 5 — Đổi tên và xóa entry rồi mở lại

Tạo `ZipMoveDeleteDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;

public class ZipMoveDeleteDemo {
    public static void main(String[] args) throws Exception {
        Path folder =
                Files.createTempDirectory("zip-move-");
        Path archive = folder.resolve("edit.zip");

        try {
            try (FileSystem fs = FileSystems.newFileSystem(
                    archive, Map.of("create", "true"))) {
                Files.createDirectories(
                        fs.getPath("/docs"));
                Files.writeString(
                        fs.getPath("/docs/old.txt"), "data");
                Files.writeString(
                        fs.getPath("/docs/trash.txt"), "remove");

                Files.move(
                        fs.getPath("/docs/old.txt"),
                        fs.getPath("/docs/new.txt"));
                Files.delete(
                        fs.getPath("/docs/trash.txt"));
            }

            try (FileSystem fs = FileSystems.newFileSystem(
                    archive, Map.of())) {
                System.out.println("newExists=" +
                        Files.exists(
                                fs.getPath("/docs/new.txt")));
                System.out.println("oldExists=" +
                        Files.exists(
                                fs.getPath("/docs/old.txt")));
                System.out.println("trashExists=" +
                        Files.exists(
                                fs.getPath("/docs/trash.txt")));
                System.out.println("newText=" +
                        Files.readString(
                                fs.getPath("/docs/new.txt")));
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ZipMoveDeleteDemo.java
java ZipMoveDeleteDemo
~~~

Stdout:

~~~text
newExists=true
oldExists=false
trashExists=false
newText=data
~~~

Như vậy, sau khi zipfs được đóng rồi mở lại, tên mới đã lưu và các entry cũ đã biến mất. Việc thay đổi **JAR đã ký** không có cùng ý nghĩa với việc đơn giản đổi tên một file trong directory: signature có thể cần tạo lại.

## 10. Đóng FileSystem và Stream đúng lúc

`FileSystem` là `AutoCloseable`. Các Path của ZIP gắn với FileSystem cụ thể ấy. Sau `close()`, Path Java vẫn là đối tượng nhưng nhiều hoạt động I/O sẽ thất bại vì backing FileSystem đã đóng.

Mẫu đúng:

~~~java
try (FileSystem fs =
             FileSystems.newFileSystem(archive, Map.of())) {
    try (Stream<Path> entries =
                 Files.walk(fs.getPath("/"))) {
        entries.filter(Files::isRegularFile)
                .forEach(path -> {
                    // Đọc/kiểm tra entry khi fs còn mở.
                });
    }
}
~~~

Đây là đoạn minh họa. **Đóng Stream trước, FileSystem sau**. Stream từ `Files.walk/list/find` có thể giữ resource và lazy traversal; không dùng nó sau khi filesystem đóng.

### 10.1. Ví dụ 6 — Đọc ZIP Path sau khi đóng bị từ chối

Tạo `ZipClosedDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;

public class ZipClosedDemo {
    public static void main(String[] args) throws Exception {
        Path folder =
                Files.createTempDirectory("zip-close-");
        Path archive = folder.resolve("closed.zip");

        try {
            Path entry;

            FileSystem fs = FileSystems.newFileSystem(
                    archive, Map.of("create", "true"));
            try {
                entry = fs.getPath("/data.txt");
                Files.writeString(entry, "ok");
                System.out.println("beforeClose=" +
                        Files.readString(entry));
            } finally {
                fs.close();
            }

            boolean closed = false;
            try {
                Files.readString(entry);
            } catch (ClosedFileSystemException ex) {
                closed = true;
            }

            System.out.println("readAfterCloseRejected=" +
                    closed);
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ZipClosedDemo.java
java ZipClosedDemo
~~~

Stdout:

~~~text
beforeClose=ok
readAfterCloseRejected=true
~~~

Khi muốn xử lý các entry bất đồng bộ, cần xác định rõ ai sở hữu FileSystem và khi nào được close. Đừng truyền Path ZIP sang một thread có thể chạy sau khi owner đã đóng archive; hoặc lưu Path từ filesystem đã đóng để tái sử dụng về sau.

## 11. ZIP Path không phải java.io.File

Một entry ZIP như `/folder/hello.txt` **không phải file trên ổ đĩa có path đó**. `Path.toFile()` của ZIP provider có thể ném `UnsupportedOperationException`.

### 11.1. Ví dụ 7 — Kiểm tra provider và toFile

Tạo `ZipProviderPathsDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;

public class ZipProviderPathsDemo {
    public static void main(String[] args) throws Exception {
        Path folder =
                Files.createTempDirectory("zip-provider-");
        Path archive = folder.resolve("provider.zip");

        try {
            try (FileSystem fs = FileSystems.newFileSystem(
                    archive, Map.of("create", "true"))) {
                Path inside =
                        fs.getPath("/folder/hello.txt");
                Files.createDirectories(inside.getParent());
                Files.writeString(inside, "Hi");

                System.out.println("jarScheme=" +
                        fs.provider().getScheme());
                System.out.println("insideAbsolute=" +
                        inside.isAbsolute());
                System.out.println("differentFileSystems=" +
                        (inside.getFileSystem()
                                != archive.getFileSystem()));
                System.out.println("name=" +
                        inside.getFileName());
                System.out.println("exists=" +
                        Files.exists(inside));

                boolean notLocalFile = false;
                try {
                    inside.toFile();
                } catch (UnsupportedOperationException e) {
                    notLocalFile = true;
                }

                System.out.println("toFileUnsupported=" +
                        notLocalFile);
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ZipProviderPathsDemo.java
java ZipProviderPathsDemo
~~~

Stdout:

~~~text
jarScheme=jar
insideAbsolute=true
differentFileSystems=true
name=hello.txt
exists=true
toFileUnsupported=true
~~~

Một Path bên trong ZIP có thể là *absolute* so với **ZIP root** `/` nhưng không phải absolute path của hệ điều hành. Nếu thư viện chỉ nhận `java.io.File`, hãy sao chép entry ra file tạm an toàn và quản lý lifetime/cleanup; không tự ghép `zipFile + "/" + entry` thành OS path.

## 12. Charset tên entry khác với charset nội dung file

Trong cấu hình `jdk.zipfs`:

- `encoding` mô tả cách xử lý **tên entry** của ZIP/JAR. Tài liệu SE 26 ghi mặc định UTF-8.
- Nội dung text **vẫn phải dùng charset riêng** như `StandardCharsets.UTF_8` khi đọc/ghi.
- `compressionMethod` lựa chọn cách lưu entry: `DEFLATED` (mặc định) hoặc `STORED` (không nén) trong provider hiện hành.
- File binary nên được copy/stream theo byte, không biến thành String bằng charset ngẫu nhiên.

### 12.1. Ví dụ 8 — Unicode filename và compression STORED

Tạo `ZipEncodingCompressionDemo.java`:

~~~java
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.*;

public class ZipEncodingCompressionDemo {
    public static void main(String[] args) throws Exception {
        Path folder =
                Files.createTempDirectory("zip-utf8-");
        Path archive = folder.resolve("unicode.zip");

        try {
            try (FileSystem fs = FileSystems.newFileSystem(
                    archive,
                    Map.of(
                            "create", "true",
                            "compressionMethod", "STORED"))) {
                Files.createDirectories(
                        fs.getPath("/tài liệu"));
                Files.writeString(
                        fs.getPath("/tài liệu/chào.txt"),
                        "Xin chào", StandardCharsets.UTF_8);
            }

            try (FileSystem fs = FileSystems.newFileSystem(
                    archive, Map.of())) {
                System.out.println("readUnicode=" +
                        Files.readString(
                                fs.getPath("/tài liệu/chào.txt"),
                                StandardCharsets.UTF_8));
            }

            try (ZipFile zip = new ZipFile(
                    archive.toFile(), StandardCharsets.UTF_8)) {
                ZipEntry entry =
                        zip.getEntry("tài liệu/chào.txt");

                System.out.println("entryFound=" +
                        (entry != null));
                System.out.println("storedNotDeflated=" +
                        (entry != null
                                && entry.getMethod()
                                        == ZipEntry.STORED));
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ZipEncodingCompressionDemo.java
java ZipEncodingCompressionDemo
~~~

Stdout:

~~~text
readUnicode=Xin chào
entryFound=true
storedNotDeflated=true
~~~

Lưu ý: `STORED` nghĩa là entry không nén bằng DEFLATE, **không** nghĩa là entry được mã hóa hoặc an toàn. Thông thường để mặc định DEFLATED nếu cần giảm kích thước archive. Phải dùng charset đúng cho file text và tránh giả định mọi file bên trong ZIP đều là UTF-8.

## 13. Cấu hình ZipFS theo phiên bản JDK

Nguồn hiện hành [Oracle SE 26 — jdk.zipfs properties](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.zipfs/module-summary.html):

| Property | Mục đích | Chú ý |
| --- | --- | --- |
| `create` | Tạo archive nếu chưa có | String `"true"` hoặc Boolean true |
| `encoding` | Charset **tên entry** | Mặc định UTF-8 |
| `compressionMethod` | `STORED` / `DEFLATED` | Phương thức khi ghi entry |
| `releaseVersion` | Chọn version view của multi-release JAR | Không đặt = unversioned theo docs |
| `enablePosixFileAttributes` | Tùy chọn bật POSIX view | Không đồng nghĩa thực thi quyền như filesystem OS |
| `accessMode` | Java SE 26 mô tả readOnly/readWrite | **Không thể mặc định áp dụng y hệt trên JDK 17** |

### 13.1. Cẩn thận với `accessMode=readOnly`

Trong tài liệu Java SE 26, provider có option `accessMode` với giá trị `"readOnly"` hoặc `"readWrite"`. Tuy nhiên, kiểm thử trực tiếp trên **JDK 17** cho thấy:

~~~java
FileSystems.newFileSystem(
        archive, Map.of("accessMode", "readOnly"))
~~~

**không** làm `fs.isReadOnly()` thành true và thao tác ghi vẫn thành công trong môi trường đó. Đây là đoạn minh họa cú pháp, **không phải ví dụ đảm bảo mở read-only ở JDK17**.

Nếu sản phẩm có yêu cầu chỉ đọc:

1. Đọc đúng tài liệu ZipFS của **JDK/provider đang chạy**.
2. Kiểm tra `fs.isReadOnly()`, không coi key env được truyền là biện pháp bảo mật.
3. Dùng quyền truy cập file archive của OS cùng thiết kế logic không ghi.
4. Không sửa JAR triển khai hoặc JAR đã ký theo cách tùy tiện.
5. Kiểm thử hành vi read-only trên runtime mục tiêu, không suy luận từ Javadoc của một version khác.

### 13.2. Multi-release JAR

Một multi-release JAR có thể chứa `META-INF/versions/9/`, `META-INF/versions/17/`... Javadoc ZipFS hiện hành mô tả `releaseVersion` dùng để chọn version-specific entry view; mặc định **unversioned**. Nếu mục tiêu là xem cấu trúc vật lý, phân biệt nó với mục tiêu đọc “tài nguyên hiệu lực tại runtime X”. `JarFile` và classloader có thể áp dụng semantics riêng.

### 13.3. POSIX attributes trong ZIP không phải security control

Javadoc SE 26 có ZIP attribute view `zip:permissions` và tùy chọn POSIX view. Tuy nhiên, **ZIP filesystem không enforce access permissions được lưu trong entry** theo cách OS kiểm soát file ngoài archive. Không dùng thuộc tính permission trong ZIP làm cơ chế phân quyền/ACL cho ứng dụng.

## 14. ZIP Slip và archive độc hại

Một archive không tin cậy có thể chứa tên entry có ý định thoát khỏi thư mục extraction:

~~~text
../outside.txt
../../secrets.txt
docs/../../../private.txt
/absolute/path.txt
~~~

Nếu một extractor lấy tên entry và ghi trực tiếp xuống ổ đĩa mà không kiểm tra, dữ liệu có thể bị ghi **ngoài root được cho phép**. Đây là rủi ro **ZIP Slip**. Một archive cũng có thể có **ZIP bomb**: dung lượng nén rất nhỏ nhưng giải nén rất lớn, quá nhiều entry, hoặc payload gây tiêu tốn CPU/RAM.

Javadoc `jdk.zipfs` Java SE 26 có một giới hạn quan trọng: **không hỗ trợ mở ZIP chứa entry với các name elements `.` hoặc `..`**. Điều đó giúp tránh một lớp path nguy hiểm khi duyệt bằng ZipFS, nhưng **không** tạo bảo đảm đầy đủ trước dữ liệu không tin cậy, symlink, archive bomb hay logic extraction tự viết.

### 14.1. Ví dụ 9 — ZipFS từ chối entry có ../

Ví dụ này **chỉ tạo ZIP thử không an toàn trong thư mục tạm và thử mở bằng ZipFS**. Nó **không giải nén** dữ liệu ra ổ đĩa.

Tạo `ZipUnsafeEntryDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;
import java.io.*;
import java.util.zip.*;

public class ZipUnsafeEntryDemo {
    public static void main(String[] args) throws Exception {
        Path folder =
                Files.createTempDirectory("zip-unsafe-");
        Path archive = folder.resolve("bad.zip");

        try {
            try (ZipOutputStream out =
                         new ZipOutputStream(
                                 Files.newOutputStream(archive))) {
                out.putNextEntry(
                        new ZipEntry("../outside.txt"));
                out.write(
                        "malicious".getBytes(
                                java.nio.charset.StandardCharsets.UTF_8));
                out.closeEntry();
            }

            boolean rejected = false;
            try (FileSystem fs =
                         FileSystems.newFileSystem(
                                 archive, Map.of())) {
                System.out.println("unexpectedlyOpened=" +
                        fs.isOpen());
            } catch (IOException
                     | IllegalArgumentException ex) {
                rejected = true;
            }

            System.out.println("zipfsRejectsDotDot=" +
                    rejected);
            System.out.println("outsideNotCreated=" +
                    Files.notExists(
                            folder.resolve("outside.txt")));
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ZipUnsafeEntryDemo.java
java ZipUnsafeEntryDemo
~~~

Stdout đã kiểm chứng trên JDK17 kiểm thử:

~~~text
zipfsRejectsDotDot=true
outsideNotCreated=true
~~~

**Giải thích:**

- `ZipOutputStream` có thể ghi tên entry `../outside.txt` trong file ZIP thử.
- `FileSystems.newFileSystem(archive,Map.of())` của ZipFS từ chối archive này trên provider đã kiểm thử.
- `outsideNotCreated=true` vì chương trình **chỉ thử mở**, không extract một entry nào.
- Đừng coi việc ZipFS từ chối một archive là kết quả “thư mục không có file”. Đó là trường hợp đầu vào không hợp lệ.
- Đừng suy ra mọi ZIP provider, hệ điều hành hoặc phiên bản có cùng thông báo lỗi. Nên xử lý dựa trên ngoại lệ/contract thay vì so nguyên văn message.

### 14.2. Khi thật sự phải giải nén ZIP từ người dùng

Một extractor cần chính sách riêng:

1. Chỉ tạo file dưới extraction root do ứng dụng kiểm soát.
2. Kiểm tra tên entry: từ chối absolute names, traversal `..`, path separator bất thường, ký tự cấm và loại entry không được phép theo nghiệp vụ.
3. Với từng candidate path, ghép với root bằng `Path.resolve`, `normalize` và kiểm tra containment theo Path semantics. Nhưng lexical containment **không đủ** khi attacker có thể thay symlink.
4. Kiểm soát symlink/no-follow và quyền filesystem; cân nhắc API mạnh hơn nếu môi trường có người khác sửa entry đồng thời (TOCTOU).
5. Giới hạn **số entry, kích thước từng entry sau giải nén, tổng bytes giải nén, tỷ lệ nén, độ sâu, CPU/thời gian**.
6. Không cho ghi đè file nhạy cảm theo mặc định; xử lý collision, filename normalization và loại file theo policy.
7. Quét/kiểm tra nội dung nếu nghiệp vụ yêu cầu, và có cơ chế publish chỉ sau khi validate thành công.

Nếu phải xử lý ZIP mà ZipFS từ chối, các API `ZipInputStream` hoặc `ZipFile` hỗ trợ đọc từng `ZipEntry` để kiểm tra; **không** dùng chúng để bỏ qua validation và extract trực tiếp.

## 15. Sai lầm phổ biến

| Ngộ nhận/lỗi | Điều đúng |
| --- | --- |
| `Path.of("/inside")` là ZIP Path | Chỉ `fs.getPath("/inside")` thuộc ZIP FileSystem |
| File ZIP và entry ZIP là cùng filesystem | File ZIP ở default FS; entry ở ZIP FS |
| `zipEntry.toFile()` luôn dùng được | ZIP Path có thể ném `UnsupportedOperationException` |
| `Files.walk` chỉ liệt kê một cấp | Nó duyệt cây; dùng `Files.list` hoặc DirectoryStream cho một cấp |
| `newDirectoryStream("*.txt")` tự đệ quy | Không, chỉ entry trực tiếp |
| Không cần đóng Stream và FileSystem | Cần try-with-resources và đóng đúng thứ tự |
| ZIP Path vẫn đọc được sau fs.close | Có thể `ClosedFileSystemException` |
| `create=true` luôn tạo ZIP rỗng và xóa bản cũ | Chỉ tạo nếu chưa tồn tại theo provider |
| Chỉ cần "jar:" cho executable JAR | Scheme `jar` là định danh provider, không chạy chương trình |
| JAR có manifest là JAR chạy được | Cần classes/Main-Class hoặc launcher phù hợp |
| Sửa signed JAR không ảnh hưởng signature | Có thể khiến chữ ký/digest không hợp lệ |
| `encoding` tự sửa charset nội dung text | Nó dành cho tên entry; file contents có charset riêng |
| `compressionMethod=STORED` là encrypt | Chỉ là lưu không nén, không mã hóa |
| ZipFS read-only env SE26 chắc chạy trên JDK17 | Kiểm thử JDK17 trong bài cho thấy option có thể bị bỏ qua |
| Các ZIP entry có permission POSIX được enforce như trên OS | ZIP provider không enforce như vậy |
| ZIP mở thành công là an toàn | Vẫn cần giới hạn kích thước và kiểm tra nội dung |
| Có thể extract tên `../x` trực tiếp | Đây là ZIP Slip; phải chặn path traversal |
| ZIP nhỏ nghĩa bytes giải nén nhỏ | ZIP bomb có thể có tỷ lệ nén cực cao |
| Đổi tên entry trong JAR giống đổi tên file không phụ thuộc gì | Có thể ảnh hưởng manifest, resource paths, chữ ký |
| Archive bị hỏng có thể coi là tree rỗng | Phải báo lỗi, không giấu dữ liệu không đọc được |

## 16. Quy tắc quản lý tài nguyên và hiệu năng

- Luôn dùng `try (FileSystem fs=...)`, trừ khi có owner lifecycle dài hạn được thiết kế rõ.
- Với `Files.walk/list/find`, đóng `Stream<Path>` trước khi đóng `FileSystem`.
- Với `Files.newDirectoryStream`, đóng `DirectoryStream<Path>`.
- Không giữ Path ZIP lâu hơn tuổi thọ filesystem cần dùng.
- Không `collect(toList())` hàng triệu entry nếu chỉ cần xử lý tuần tự.
- Không dùng `Files.readAllBytes` cho file khổng lồ nếu có thể stream/copy.
- Khi cần mở cùng archive từ nhiều nơi, quản lý quyền sở hữu và tránh tạo FileSystem trùng URI không cần thiết.
- Nếu archive đang được một tiến trình khác ghi/sửa, không coi view của ZipFS là snapshot transactional.
- Với thao tác ghi nhiều entry, kiểm thử chi phí lưu/close archive, quota ổ đĩa và chiến lược rollback.
- Với ứng dụng chỉ cần xem manifest/class/resource một số mục, cân nhắc `JarFile`/`ZipFile` để tránh mở filesystem không cần thiết.
- Khi build ứng dụng với `jlink` custom image, kiểm tra module `jdk.zipfs` có mặt. Thiếu provider có thể dẫn tới `ProviderNotFoundException`.
- Đừng chỉ bắt `IOException` ở Files.walk mà quên lỗi phát sinh trong lazy Stream processing; nếu cần, xử lý exception có cause phù hợp và đóng resource.

## 17. Bảng chọn API theo mục đích

| Nhu cầu | API phù hợp | Vì sao |
| --- | --- | --- |
| Xem ZIP/JAR như directory tree | `FileSystems.newFileSystem` + `Path` + `Files.walk` | Mô hình NIO |
| Duyệt file cùng directory trong ZIP | `Files.list`/`DirectoryStream` | Chỉ một cấp |
| Lọc glob `*.xml` ngay trong một folder ZIP | `Files.newDirectoryStream(folder,"*.xml")` | Lọc theo tên |
| Đọc một vài named ZIP entries | `ZipFile` | API theo entry |
| Đọc manifest JAR | `JarFile.getManifest` | API metadata JAR |
| Đọc luồng ZIP tuần tự | `ZipInputStream` | Xử lý theo stream |
| Tạo ZIP từ luồng bytes | `ZipOutputStream` | Điều khiển entry trong stream |
| Chép file local vào ZIP | `Files.copy(local,zipEntry)` | Giữ bytes giữa providers |
| Cập nhật ZIP qua path | `Files.write/move/delete` trên ZipFS | Tiện dùng API thống nhất |
| Build ứng dụng JAR triển khai | Build tool hoặc `jar` CLI | Quản lý manifest, dependencies, signatures |
| Extract archive không đáng tin | API ZIP + validation/path containment/quotas | Bảo mật toàn bộ quy trình |

## 18. Checklist áp dụng

1. Đã phân biệt file ZIP bên ngoài và Path entry bên trong?
2. Có chắc FileSystem provider hỗ trợ ZIP/JAR trong runtime image?
3. Mở archive sẵn có bằng env rỗng và chỉ dùng `create=true` khi được phép tạo?
4. Dùng `zipfs.getPath("/")` làm root cây?
5. Không tái tạo ZIP Path bằng default `Path.of`?
6. Dùng `Files.walk` khi cần đệ quy và `Files.list`/DirectoryStream khi chỉ một cấp?
7. Có lọc file thường, xử lý path trùng tên ở nhiều directory?
8. Có đóng Stream, DirectoryStream và FileSystem đúng thứ tự?
9. Có tránh đọc Path sau khi FileSystem đóng?
10. Có copy entry sang OS trước khi đưa tới thư viện yêu cầu `java.io.File`?
11. Có chọn charset nội dung text rõ ràng, phân biệt với encoding của tên entry?
12. Có kiểm tra `compressionMethod` và những property provider chỉ hỗ trợ ở phiên bản phù hợp?
13. Không tin `accessMode=readOnly` chỉ vì đã truyền env trên JDK17?
14. Nếu là JAR, đã xử lý manifest, multi-release entries và signature theo mục tiêu?
15. Có hạn chế quyền sửa archive production và signed JAR?
16. Có test ZIP/JAR sau close-reopen để đảm bảo kết quả?
17. Có test trên OS/JDK và FileSystem provider mà sản phẩm thực sự hỗ trợ?
18. Có xử lý ZIP không hợp lệ, thiếu provider, permission, duplicate, read-only?
19. Có chặn ZIP Slip/path traversal nếu extract?
20. Có giới hạn decompressed bytes, số entry và memory/CPU đối với ZIP không tin cậy?

## 19. Câu hỏi tự kiểm tra

**1.** File `archive.zip` trên ổ đĩa và entry `/docs/a.txt` trong ZIP có cùng FileSystem không?  
**Đáp án:** Không.

**2.** Mở một ZIP có sẵn bằng API nào?  
**Đáp án:** `FileSystems.newFileSystem(zipPath, Map.of())` nếu provider hỗ trợ.

**3.** Tạo ZIP mới khi chưa tồn tại bằng env gì?  
**Đáp án:** `Map.of("create","true")`.

**4.** Root trong ZIP có dạng gì?  
**Đáp án:** `fs.getPath("/")`.

**5.** Path trong ZIP có dùng `toFile()` được không?  
**Đáp án:** Không như default FS; có thể `UnsupportedOperationException`.

**6.** `Files.walk(root)` so với `Files.list(root)` khác gì?  
**Đáp án:** walk đệ quy, list chỉ một cấp.

**7.** Dùng `Files.copy(local,zipEntry)` được không?  
**Đáp án:** Được, nếu provider/permissions cho phép và parent/destination hợp lệ.

**8.** Sau `FileSystem.close()` có thể dùng Path ZIP để đọc lại không?  
**Đáp án:** Không; có thể ClosedFileSystemException.

**9.** Tại sao JAR có scheme `jar:`?  
**Đáp án:** Đó là định danh của ZIP FileSystem Provider.

**10.** `JarFile` giúp gì ngoài ZipFS?  
**Đáp án:** Semantics JAR entries và manifest/version-specific handling.

**11.** Property `encoding` của ZipFS mô tả điều gì?  
**Đáp án:** Encoding của **tên entry**, không tự decode nội dung text.

**12.** `STORED` có phải mã hóa dữ liệu không?  
**Đáp án:** Không; nó là cách lưu không nén.

**13.** Property `accessMode=readOnly` theo SE26 có chắc chặn ghi ở JDK17 không?  
**Đáp án:** Không. Phải kiểm tra provider/version và `fs.isReadOnly()`.

**14.** Chỉnh sửa JAR đã ký có thể gây điều gì?  
**Đáp án:** Hỏng tính hợp lệ của chữ ký/digest.

**15.** ZipFS Java SE26 có hỗ trợ ZIP chứa entry `../evil.txt` không?  
**Đáp án:** Javadoc nói không hỗ trợ entry có name elements `.` hoặc `..`; JDK17 kiểm thử cũng từ chối.

**16.** ZIP nhỏ có chắc an toàn khi giải nén?  
**Đáp án:** Không; cần chống ZIP bomb bằng giới hạn.

**17.** Khi nào nên dùng `ZipFile` thay ZipFS?  
**Đáp án:** Khi chỉ cần truy cập vài entry cụ thể, không cần mô hình tree Path.

**18.** Tại sao cần đóng cả Files.walk Stream?  
**Đáp án:** Stream có thể giữ tài nguyên traversal và lazy access.

## 20. Nguồn chính thức

- [Oracle Java SE 26 — Module jdk.zipfs](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.zipfs/module-summary.html): ZIP/JAR FileSystem Provider, URI jar, env properties, giới hạn entry tên "." hoặc "..".
- [Oracle Java SE 26 — FileSystems](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileSystems.html): overload `newFileSystem`, provider discovery và lỗi mở.
- [Oracle Java SE 26 — FileSystem](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileSystem.html): `getPath`, `provider`, `isReadOnly`, `close`.
- [Oracle Java SE 26 — Path](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html): path/provider semantics và `toFile`.
- [Oracle Java SE 26 — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): `walk`, `list`, `copy`, `move`, `readString`, `writeString`.
- [Oracle Java SE 26 — DirectoryStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/DirectoryStream.html): iterable entry một cấp và cần close.
- [Oracle Java SE 26 — ZipFile](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/zip/ZipFile.html): đọc ZIP entries.
- [Oracle Java SE 26 — ZipEntry](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/zip/ZipEntry.html): metadata entry, STORED/DEFLATED.
- [Oracle Java SE 26 — ZipInputStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/zip/ZipInputStream.html): đọc archive theo luồng.
- [Oracle Java SE 26 — ZipOutputStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/zip/ZipOutputStream.html): tạo archive qua stream.
- [Oracle Java SE 26 — JarFile](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/JarFile.html): đọc manifest/JAR metadata.
- [Oracle Java SE 26 — Manifest](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/Manifest.html): cấu trúc manifest.
- [Oracle Java SE 26 — ClosedFileSystemException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/ClosedFileSystemException.html): I/O sau close.
- [Oracle Java SE 26 — ProviderNotFoundException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/ProviderNotFoundException.html): runtime thiếu provider.
- [Oracle Java SE 8 — Zip File System Provider Guide](https://docs.oracle.com/javase/8/docs/technotes/guides/io/fsp/zipfilesystemprovider.html): xác nhận ZIP provider có từ Java 7; dùng làm mốc lịch sử, còn hành vi hiện tại đối chiếu SE 26.

**Kết luận:** ZIP/JAR là **một file** ngoài ổ đĩa nhưng có thể mở thành **một cây Path trong FileSystem riêng**. Mở bằng `FileSystems.newFileSystem`, lấy root `fs.getPath("/")`, dùng `Files.walk` và `Files.copy` đúng provider, rồi **đóng Stream và FileSystem**. Không nhầm ZipFS Path với OS Path, không tin các option mới trên JDK cũ và không xử lý archive không đáng tin mà thiếu kiểm soát kích thước/đường dẫn.