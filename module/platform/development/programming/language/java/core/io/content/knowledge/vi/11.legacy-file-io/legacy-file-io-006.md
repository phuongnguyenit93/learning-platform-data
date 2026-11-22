# `list()`, `listFiles()`, `FileFilter` và `FilenameFilter`

## Mục tiêu bài học

Trong Java I/O truyền thống, lớp `java.io.File` biểu diễn **đường dẫn** tới file hoặc thư mục, không phải nội dung file hay một file descriptor đang mở. Để liệt kê các phần tử **trực tiếp** trong một thư mục, lớp này cung cấp hai họ phương thức: `list(...)` trả **tên** dạng `String`, còn `listFiles(...)` trả các đối tượng `File`. Hai giao diện `FilenameFilter` và `FileFilter` giúp chọn những phần tử được đưa vào kết quả.

Sau bài này, bạn có thể:

- Phân biệt các overload `list()`, `list(FilenameFilter)`, `listFiles()`, `listFiles(FilenameFilter)` và `listFiles(FileFilter)`.
- Viết lambda/implementation cho `FilenameFilter.accept(File dir, String name)` và `FileFilter.accept(File pathname)` đúng tham số.
- Biết khi nào cần **tên đơn giản**, khi nào cần **đường dẫn đầy đủ theo đối tượng `File`**, và cách kết hợp parent với child.
- Xử lý kết quả `null` của `list`/`listFiles`, sắp xếp khi cần, giới hạn ở một cấp thư mục, và các tình huống permission/race condition.
- Viết Java 17+ dùng thư mục tạm để kiểm chứng bộ lọc một cách độc lập với thư mục máy cá nhân.
- Biết lúc nào nên chuyển sang `java.nio.file.Files.list`, `DirectoryStream`, `Files.walk` hoặc `Files.walkFileTree` trong mã mới.

## 1. Nền tảng: `java.io.File` đại diện đường dẫn

```java
File directory = new File("data");
File child = new File(directory, "report.txt");
```

Đây là **đoạn minh họa**, cần `import java.io.File;`. Tạo `new File(...)` **không** tạo file/thư mục vật lý, không kiểm tra chắc chắn nó tồn tại và không tự mở luồng dữ liệu. `File` chỉ lưu cách biểu diễn đường dẫn để các phương thức I/O sử dụng.

Các phép kiểm tra thường dùng:

| Phương thức | Ý nghĩa cần nhớ |
|---|---|
| `exists()` | Kiểm tra đường dẫn hiện đang tồn tại theo khả năng quan sát của runtime |
| `isDirectory()` | Kiểm tra đường dẫn hiện tham chiếu tới thư mục |
| `isFile()` | Kiểm tra đường dẫn hiện tham chiếu tới file thông thường |
| `getName()` | Thành phần tên cuối cùng của đường dẫn, không gồm parent |
| `getPath()` | Chuỗi đường dẫn được `File` biểu diễn |
| `getAbsolutePath()` | Dạng đường dẫn tuyệt đối theo cách runtime phân giải |
| `getCanonicalPath()` | Dạng đường dẫn chuẩn hóa theo quy tắc của filesystem; có thể ném `IOException` |
| `toPath()` | Chuyển sang `java.nio.file.Path`, thuận tiện khi dùng NIO.2 |

**Lưu ý:** Kết quả `exists()`, `isFile()` hay `isDirectory()` chỉ mô tả trạng thái tại thời điểm kiểm tra. Ngay sau đó, file có thể bị đổi tên, xóa hoặc thay bởi một process khác; vì vậy không dùng chuỗi “kiểm tra rồi thao tác” làm cơ chế khóa hoặc bảo mật tuyệt đối.

Một đường dẫn tới directory là đối tượng `File`; liệt kê directory mới là hành động I/O thực sự. Các phương thức `list` và `listFiles` chỉ liệt kê **con trực tiếp**, không tự duyệt các thư mục con.

## 2. Bản đồ API `list` và `listFiles`

| Phương thức | Kiểu trả về | Bộ lọc | Nội dung kết quả |
|---|---|---|---|
| `dir.list()` | `String[]` hoặc `null` | Không | Tên các mục trực tiếp trong thư mục |
| `dir.list(FilenameFilter filter)` | `String[]` hoặc `null` | `accept(File dir, String name)` | Tên các mục được filter chấp nhận |
| `dir.listFiles()` | `File[]` hoặc `null` | Không | Các đối tượng `File` cho các mục trực tiếp |
| `dir.listFiles(FilenameFilter filter)` | `File[]` hoặc `null` | Filter theo parent và tên | Các đối tượng `File` tương ứng mục được chấp nhận |
| `dir.listFiles(FileFilter filter)` | `File[]` hoặc `null` | `accept(File pathname)` | Các đối tượng `File` được filter chấp nhận |

Ví dụ thư mục tưởng tượng:

```text
data/
├── README.md
├── notes.txt
├── photo.png
└── images/
    └── icon.png
```

Nếu `File dir = new File("data")`:

- `dir.list()` cho mảng tên trực tiếp: `README.md`, `notes.txt`, `photo.png`, `images` (thứ tự **không được bảo đảm**).
- `dir.listFiles()` cho các `File` tương ứng với `data/README.md`, `data/notes.txt`, `data/photo.png`, `data/images` (biểu diễn đường dẫn phụ thuộc hệ điều hành).
- **Không** có `icon.png` trong kết quả của hai lời gọi trên, vì nó ở cấp sâu hơn.
- `list` có thể trả tên của **cả file lẫn thư mục**; tên chứa phần mở rộng không tự chứng minh đó là file thông thường.
- Mảng kết quả có thể rỗng, nhưng mảng rỗng **khác `null`**.

Các phương thức không bảo đảm thứ tự sắp xếp. Nếu trình bày kết quả cho người dùng, so sánh trong unit test hoặc cần thứ tự xử lý xác định, hãy **sắp xếp một cách tường minh**.

## 3. `list()`: lấy tên `String[]`

```java
File dir = new File("data");
String[] names = dir.list();

if (names == null) {
    System.err.println("Cannot list directory");
} else {
    Arrays.sort(names);
    for (String name : names) {
        System.out.println(name);
    }
}
```

Đây là **đoạn minh họa**, cần `import java.io.File;`, `import java.util.Arrays;`, và một thư mục `data` tồn tại để nhận dữ liệu thực tế.

Những điểm quan trọng:

1. `list()` trả về **tên** từng entry, **không phải** đường dẫn đầy đủ.
2. Nếu cần mở một mục, phải kết hợp tên với directory: `new File(dir, name)` hoặc `dir.toPath().resolve(name)`.
3. Nếu thư mục trống, kết quả thông thường là `new String[0]`, không phải `null`.
4. Nếu đường dẫn **không trỏ tới directory** hoặc xảy ra lỗi I/O khi liệt kê, `list()` có thể trả `null`. Ngoài ra, API có thể ném `SecurityException` khi kiểm tra quyền theo môi trường/security manager có liên quan; đừng mặc định mọi lỗi chỉ thể hiện qua `null`.
5. Giá trị do `list()` trả về chỉ là một **snapshot kết quả liệt kê tại lần gọi đó**; filesystem có thể thay đổi ngay sau đó.

Khi chỉ cần hiển thị tên, lọc phần mở rộng hoặc điền danh sách tên, `String[]` rất tiện. Khi cần kiểm tra `isFile()`, `length()`, `lastModified()` hoặc thao tác file, `File[]` thường giúp code rõ hơn.

## 4. `listFiles()`: lấy các đối tượng `File[]`

```java
File[] children = dir.listFiles();

if (children == null) {
    System.err.println("Cannot list directory");
} else {
    Arrays.sort(children, Comparator.comparing(File::getName));
    for (File child : children) {
        System.out.println(
            child.getName() + " / isFile=" + child.isFile()
        );
    }
}
```

Đây là **đoạn minh họa** với `dir` kiểu `File`; cần import `java.io.File`, `java.util.Arrays`, `java.util.Comparator`.

Mỗi phần tử của `File[]` biểu diễn đường dẫn đến một mục **trong directory**. Đối tượng `File` không tự bảo đảm mục đó vẫn tồn tại khi bạn gọi `isFile()`; kết quả kiểm tra được hệ điều hành cung cấp tại lúc gọi.

**Không nhầm `File[]` với các file đã mở.** Lấy mảng `File` không có nghĩa Java đang giữ `InputStream` hay file descriptor của từng mục, và không có `close()` cho các đối tượng `File` đơn thuần.

### Những lựa chọn thường gặp

- Muốn nhận **tên** rồi tự xử lý: `list()`.
- Muốn kiểm tra loại entry hoặc metadata: `listFiles()`.
- Muốn trả cả parent/name để callback quyết định: `FilenameFilter`.
- Muốn callback nhận thẳng object pathname: `FileFilter`.

Ví dụ `listFiles()` trên một file thông thường thay vì directory cũng có thể trả `null`, không phải một mảng chứa chính file đó.

## 5. `FilenameFilter`: nhận `dir` và `name`

Giao diện `java.io.FilenameFilter` là **functional interface** với một phương thức trừu tượng:

```java
boolean accept(File dir, String name);
```

Đây là **chữ ký minh họa**, không phải một hàm top-level để biên dịch độc lập.

- `dir`: directory đang được liệt kê.
- `name`: tên **đơn giản** của entry nằm ngay trong directory đó.
- Trả `true`: chấp nhận entry vào kết quả.
- Trả `false`: loại entry khỏi kết quả.

Ví dụ chỉ lấy tên có đuôi `.txt`:

```java
FilenameFilter onlyTxt =
    (parent, name) -> name.endsWith(".txt");

String[] txtNames = dir.list(onlyTxt);
File[] txtEntries = dir.listFiles(onlyTxt);
```

Đây là **đoạn minh họa**, cần import `java.io.File` và `java.io.FilenameFilter`; `dir` là directory `File`.

Hai lời gọi cùng điều kiện chấp nhận nhưng khác kiểu trả về: `String[]` và `File[]`.

Nếu cần kiểm tra loại đối tượng dù đang dùng `FilenameFilter`:

```java
FilenameFilter onlyTxtFiles = (parent, name) -> {
    File candidate = new File(parent, name);
    return candidate.isFile() && name.endsWith(".txt");
};
```

**Đúng:** Kết hợp directory và name bằng `new File(parent, name)`. **Sai:** `new File(name)` nếu kỳ vọng kiểm tra một đường dẫn trong `parent`: đường dẫn tương đối có thể bị phân giải theo working directory của JVM, dẫn tới kiểm tra nhầm chỗ.

### Phân biệt phần mở rộng và file thực

`name.endsWith(".txt")` chỉ xét **chuỗi tên**, vì vậy **một thư mục có tên `backup.txt` vẫn có thể được chấp nhận**. Nếu nghiệp vụ yêu cầu *file thông thường* có phần mở rộng `.txt`, cần kết hợp kiểm tra `isFile()` và tên.

### Phân biệt hoa/thường

`name.endsWith(".txt")` không chọn `README.TXT`. Nếu chính sách cho phép tên không phân biệt hoa/thường:

```java
FilenameFilter caseInsensitiveTxt =
    (parent, name) ->
        name.toLowerCase(Locale.ROOT).endsWith(".txt");
```

Đây là **đoạn minh họa**, cần `import java.util.Locale;`. `Locale.ROOT` giúp tránh phụ thuộc vào locale người dùng với quy tắc so sánh tên kiểu kỹ thuật. Tuy nhiên, đó vẫn chỉ là **chính sách lọc của ứng dụng**: không đồng nghĩa filesystem trên mọi nền tảng đều không phân biệt hoa/thường, và với Unicode có những trường hợp case mapping không thể xử lý đầy đủ chỉ bằng một lần `toLowerCase`.

## 6. `FileFilter`: nhận đường dẫn `File`

Giao diện `java.io.FileFilter` cũng là **functional interface**:

```java
boolean accept(File pathname);
```

Đây là **chữ ký minh họa**, không phải chương trình độc lập.

Khác `FilenameFilter`, callback nhận luôn object `File` đại diện entry; rất tiện để kiểm tra **file thông thường**, **directory**, **kích thước**, **thời gian sửa đổi**, hoặc điều kiện liên quan đường dẫn.

```java
FileFilter onlyRegularFiles = File::isFile;
FileFilter directoriesOnly = File::isDirectory;
FileFilter nonEmptyLogs = file ->
    file.isFile()
        && file.getName().endsWith(".log")
        && file.length() > 0L;

File[] regular = dir.listFiles(onlyRegularFiles);
File[] folders = dir.listFiles(directoriesOnly);
File[] logs = dir.listFiles(nonEmptyLogs);
```

Đây là **đoạn minh họa**, cần `java.io.File` và `java.io.FileFilter`, với `dir` trỏ thư mục. Nên kiểm tra `null` sau mỗi lời gọi trước khi lặp kết quả.

**Khác biệt phương thức:** `FileFilter` được dùng với `listFiles(FileFilter)`, **không có overload `list(FileFilter)`**. Nếu chỉ muốn nhận mảng tên nhưng điều kiện cần kiểm tra loại file, dùng `list(FilenameFilter)` và dựng `File` từ `parent/name`, hoặc dùng `listFiles(FileFilter)` rồi ánh xạ `File::getName`.

### Nếu callback tốn kém?

Một `FileFilter` gọi `isFile()` hoặc `length()` có thể phát sinh thêm lượt truy vấn metadata tới filesystem cho từng entry. Trong directory rất lớn hoặc storage từ xa, điều đó có thể tốn thời gian. Nếu chỉ cần lọc theo tên, `FilenameFilter` đơn giản thường đủ và tránh truy vấn metadata không cần thiết.

Đừng dựa vào số lượng hoặc thứ tự callback `accept` như một hợp đồng ổn định để thực hiện side effect (ghi/xóa/đổi tên file). Filter nên **không có side effect**, quyết định nhanh và nhất quán từ thông tin cần thiết.

## 7. So sánh `FilenameFilter` và `FileFilter`

| Tiêu chí | `FilenameFilter` | `FileFilter` |
|---|---|---|
| Phương thức | `accept(File dir, String name)` | `accept(File pathname)` |
| Đối số trực tiếp | Parent directory + tên con | `File` đại diện đường dẫn con |
| `list(FilenameFilter)` | Có | Không có `list(FileFilter)` |
| `listFiles(...)` | Có | Có |
| Phù hợp | Lọc tên, pattern, đuôi file | Lọc theo loại file, thuộc tính và đường dẫn |
| Lọc `isFile()` | Tự dựng `new File(dir, name)` | Gọi trên `pathname` |
| Lambda hai tham số | `(dir, name) -> ...` | Không |
| Lambda một tham số | Không | `file -> ...` |

Ví dụ đối chiếu cùng một điều kiện, chọn file `.csv` thông thường:

```java
FilenameFilter a = (parent, name) ->
    name.endsWith(".csv")
        && new File(parent, name).isFile();

FileFilter b = pathname ->
    pathname.isFile()
        && pathname.getName().endsWith(".csv");

File[] usingA = dir.listFiles(a);
File[] usingB = dir.listFiles(b);
```

Đây là **đoạn minh họa**, cần import `File`, `FileFilter`, `FilenameFilter`. Cả hai diễn đạt cùng ý định trong trường hợp filesystem không thay đổi và điều kiện kiểm tra tương đương. Chúng không bảo đảm kết quả như nhau nếu directory thay đổi **giữa hai lần gọi**.

### Hai overload `listFiles` có thể gây nhầm

Có hai overload cùng tên: `listFiles(FilenameFilter)` và `listFiles(FileFilter)`. Với lambda, số tham số thường giúp compiler xác định:

```java
dir.listFiles((parent, name) -> name.endsWith(".txt"));
dir.listFiles(file -> file.isFile());
```

Đây là **đoạn minh họa**; lambda hai tham số tương ứng `FilenameFilter`, lambda một tham số tương ứng `FileFilter`.

**Đặc biệt:** Lời gọi `dir.listFiles(null)` có thể **mơ hồ khi biên dịch** vì cả hai overload đều nhận kiểu tham chiếu và không có overload nào cụ thể hơn. Nếu thật sự muốn không lọc, hãy dùng `dir.listFiles()` thay vì truyền `null`.

## 8. Ví dụ Java 17 hoàn chỉnh: năm phương thức liệt kê và sắp xếp

Chương trình tự tạo directory tạm với ba file và một thư mục con. Toàn bộ output được sắp xếp nên không phụ thuộc vào thứ tự liệt kê của filesystem.

Lưu **`FileListingDemo.java`**:

```java
import java.io.File;
import java.io.FileFilter;
import java.io.FilenameFilter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Comparator;

public class FileListingDemo {
    private static String sorted(String[] names) {
        if (names == null) {
            return "<null>";
        }
        Arrays.sort(names);
        return Arrays.toString(names);
    }

    private static String sorted(File[] files) {
        if (files == null) {
            return "<null>";
        }
        Arrays.sort(files, Comparator.comparing(File::getName));
        String[] names = Arrays.stream(files)
            .map(File::getName)
            .toArray(String[]::new);
        return Arrays.toString(names);
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("file-list-");

        try {
            Files.writeString(
                root.resolve("notes.txt"),
                "note",
                StandardCharsets.UTF_8
            );
            Files.writeString(
                root.resolve("photo.png"),
                "not a real image",
                StandardCharsets.UTF_8
            );
            Files.writeString(
                root.resolve("readme.md"),
                "readme",
                StandardCharsets.UTF_8
            );
            Files.createDirectory(root.resolve("sub"));

            File directory = root.toFile();
            FilenameFilter txt = (parent, name) ->
                name.endsWith(".txt");
            FilenameFilter markdown = (parent, name) ->
                name.endsWith(".md");
            FileFilter regular = File::isFile;
            FileFilter folders = File::isDirectory;

            System.out.println(
                "list(): " + sorted(directory.list()));
            System.out.println(
                "listFiles(): " + sorted(directory.listFiles()));
            System.out.println(
                "list(txt): " + sorted(directory.list(txt)));
            System.out.println(
                "listFiles(markdown): " +
                    sorted(directory.listFiles(markdown)));
            System.out.println(
                "listFiles(regular): " +
                    sorted(directory.listFiles(regular)));
            System.out.println(
                "listFiles(folders): " +
                    sorted(directory.listFiles(folders)));

            File missing = root.resolve("absent").toFile();
            System.out.println(
                "missing list() is null: " +
                    (missing.list() == null));
        } finally {
            Files.deleteIfExists(root.resolve("notes.txt"));
            Files.deleteIfExists(root.resolve("photo.png"));
            Files.deleteIfExists(root.resolve("readme.md"));
            Files.deleteIfExists(root.resolve("sub"));
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac FileListingDemo.java
java FileListingDemo
```

Stdout khi thao tác filesystem thành công và không có process khác sửa thư mục tạm:

```text
list(): [notes.txt, photo.png, readme.md, sub]
listFiles(): [notes.txt, photo.png, readme.md, sub]
list(txt): [notes.txt]
listFiles(markdown): [readme.md]
listFiles(regular): [notes.txt, photo.png, readme.md]
listFiles(folders): [sub]
missing list() is null: true
```

Giải thích:

1. `list()` và `listFiles()` nhận bốn **con trực tiếp**.
2. `list(txt)` chỉ trả `String[]` chứa `notes.txt`.
3. `listFiles(markdown)` trả `File[]` chỉ chứa `readme.md`.
4. `listFiles(regular)` loại thư mục `sub`; `listFiles(folders)` chỉ chọn `sub`.
5. Đường dẫn `absent` không tồn tại, vì vậy `missing.list() == null`.
6. Helper `sorted(...)` sắp xếp kết quả trước khi in; **không được khẳng định** bản thân API luôn trả đúng thứ tự trên.

Ví dụ dùng `Files.createTempDirectory` và `Files.writeString` để dựng fixture; phần giải thích chính vẫn là các API **truyền thống** của `java.io.File`. `Files.writeString` có trong Java 11+, phù hợp yêu cầu Java 17. File giả `photo.png` chỉ minh họa rằng **đuôi tên không chứng minh định dạng nội dung**.

Phần `finally` xóa các mục theo tên cố định. Nếu việc tạo một file bị lỗi trước khi vào phần liệt kê, `deleteIfExists` giúp dọn những mục đã tạo; lỗi cleanup có thể ném `IOException`. Trong code production, cần cơ chế dọn dẹp file tạm giữ nguyên nguyên nhân lỗi gốc khi điều đó quan trọng. Không dùng mã xóa tự động trên directory chứa dữ liệu của người dùng.

## 9. Ví dụ Java 17: cùng đuôi tên nhưng khác loại entry

Đôi khi dùng mỗi `name.endsWith(".csv")` là chưa đủ. Chương trình sau tạo hai file có đuôi `.csv` và một **thư mục** cũng có đuôi `.csv`, sau đó so sánh lọc theo tên với lọc theo metadata.

Lưu **`FileFilterVsFilenameFilterDemo.java`**:

```java
import java.io.File;
import java.io.FileFilter;
import java.io.FilenameFilter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class FileFilterVsFilenameFilterDemo {
    private static String names(File[] files) {
        if (files == null) {
            return "<null>";
        }
        String[] values = Arrays.stream(files)
            .map(File::getName)
            .sorted()
            .toArray(String[]::new);
        return Arrays.toString(values);
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("filter-demo-");

        try {
            Files.writeString(root.resolve("empty.csv"), "");
            Files.writeString(root.resolve("filled.csv"), "id\n1\n");
            Files.createDirectory(root.resolve("archive.csv"));

            File directory = root.toFile();

            FilenameFilter bySuffix =
                (parent, name) -> name.endsWith(".csv");

            FileFilter realCsvFiles = file ->
                file.isFile()
                    && file.getName().endsWith(".csv");

            FileFilter nonEmptyCsvFiles = file ->
                file.isFile()
                    && file.getName().endsWith(".csv")
                    && file.length() > 0;

            System.out.println("suffix: " +
                names(directory.listFiles(bySuffix)));
            System.out.println("regular: " +
                names(directory.listFiles(realCsvFiles)));
            System.out.println("nonempty: " +
                names(directory.listFiles(nonEmptyCsvFiles)));
        } finally {
            Files.deleteIfExists(root.resolve("empty.csv"));
            Files.deleteIfExists(root.resolve("filled.csv"));
            Files.deleteIfExists(root.resolve("archive.csv"));
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac FileFilterVsFilenameFilterDemo.java
java FileFilterVsFilenameFilterDemo
```

Stdout khi tạo/đọc directory thành công:

```text
suffix: [archive.csv, empty.csv, filled.csv]
regular: [empty.csv, filled.csv]
nonempty: [filled.csv]
```

Giải thích từng bộ lọc:

- `bySuffix` chỉ xét **tên**, nên cả thư mục `archive.csv` được nhận.
- `realCsvFiles` yêu cầu `isFile()`, nên loại directory.
- `nonEmptyCsvFiles` còn yêu cầu `length() > 0`; vì `filled.csv` chứa `id\n1\n`, chỉ nó được chọn.

`File.length()` có ý nghĩa với file thông thường nhưng không thể thay thế một quy trình xác minh nội dung file. Nếu file thay đổi giữa lúc lọc và lúc mở, kích thước hoặc loại entry có thể khác; `isFile()` và `length()` là **các truy vấn trạng thái tức thời**, không tạo giao dịch nguyên tử.

### Lọc tên không đồng nghĩa lọc nội dung

Một file tên `report.csv` vẫn có thể chứa dữ liệu nhị phân sai định dạng CSV. Nếu ứng dụng phải xử lý CSV thực sự, sau bước liệt kê cần mở và parse nội dung bằng bộ parser phù hợp, kiểm tra charset, schema, escaping và xử lý lỗi.

## 10. Trả về `null`, mảng rỗng và lỗi quyền truy cập

Điểm dễ sai nhất của họ `list` là **không phải lúc nào kết quả cũng là một mảng hợp lệ**.

| Trường hợp | Kỳ vọng hợp lý |
|---|---|
| Directory tồn tại, truy cập được, không có entry | `String[0]` hoặc `File[0]` |
| Directory tồn tại, có n entry và liệt kê thành công | Mảng n phần tử (hoặc ít hơn khi filter) |
| Đường dẫn không tồn tại | `null` |
| Đường dẫn trỏ tới file, không phải directory | `null` |
| Lỗi I/O khi liệt kê | Có thể trả `null` |
| Vi phạm kiểm tra quyền bảo mật theo runtime | Có thể ném `SecurityException` |
| Permission hoặc filesystem thay đổi bất ngờ | Không thể coi `null` hay kết quả cũ là chẩn đoán duy nhất |

**`null` không nói chính xác nguyên nhân.** Đừng biến `null` thành “directory rỗng”. Ví dụ sai:

```java
for (File f : dir.listFiles()) {
    System.out.println(f.getName());
}
```

Đây là **phản ví dụ**: nếu `listFiles()` trả `null`, vòng for-each sẽ ném `NullPointerException`.

Một cách bảo vệ tối thiểu:

```java
File[] entries = dir.listFiles();
if (entries == null) {
    throw new IllegalStateException(
        "Cannot list directory: " + dir);
}
for (File entry : entries) {
    System.out.println(entry.getName());
}
```

Đây là **đoạn minh họa**, biến `dir` là `File`. Việc ném `IllegalStateException` phù hợp cho ví dụ đơn giản nhưng không tái tạo nguyên nhân `IOException` vốn không được API `listFiles()` cung cấp trực tiếp. Nếu xử lý lỗi chi tiết là yêu cầu quan trọng, cân nhắc API NIO.2 như `Files.newDirectoryStream()` hoặc `Files.list()`, vốn có cách báo lỗi rõ hơn.

### Có nên gọi `isDirectory()` trước?

Bạn có thể làm:

```java
if (!dir.isDirectory()) {
    System.err.println("Not a readable directory: " + dir);
    return;
}
File[] entries = dir.listFiles();
if (entries == null) {
    System.err.println("Listing failed: " + dir);
    return;
}
```

Đây là **mã minh họa bên trong một phương thức trả về `void`**; nếu đặt trong mã khác cần điều chỉnh `return`. Tuy nhiên, việc `isDirectory()` trả `true` **không đảm bảo** `listFiles()` thành công; filesystem có thể thay đổi và quyền truy cập có thể khác. Vẫn bắt buộc xử lý `null` sau khi gọi.

## 11. Thứ tự phần tử và cách sắp xếp

JDK **không quy định thứ tự** trả về của `list` hoặc `listFiles`. Không xây dựng logic dựa trên giả định “theo thứ tự tạo”, “theo thứ tự tên” hay “theo độ mới”.

Sắp xếp tên:

```java
String[] names = dir.list();
if (names != null) {
    Arrays.sort(names);
}
```

Sắp xếp `File[]` theo tên:

```java
File[] files = dir.listFiles();
if (files != null) {
    Arrays.sort(files, Comparator.comparing(File::getName));
}
```

Đây là **các đoạn minh họa**, cần import `Arrays`, `Comparator`, `File`.

- `Arrays.sort(names)` so sánh chuỗi Unicode theo quy tắc `String.compareTo`; không đồng nghĩa xếp chữ cái theo văn hóa của người Việt.
- Nếu cần thứ tự phù hợp ngôn ngữ/locale, cân nhắc `Collator` với locale được khai báo rõ.
- Nếu chỉ cần thứ tự ổn định trong test, comparator theo tên là đủ khi các tên không trùng trong một directory.
- Sort mảng lớn cần thêm bộ nhớ/thời gian; với listing hàng triệu entry, nên cân nhắc pipeline streaming/giới hạn đầu vào.

Không so sánh kết quả thực tế của `listFiles()` với expected array theo **vị trí** nếu chưa sort cả hai.

## 12. Không tự đệ quy: muốn duyệt thư mục con phải chủ động

Với cấu trúc:

```text
root/
├── top.txt
└── child/
    └── nested.txt
```

`new File("root").listFiles()` chỉ cho `top.txt` và directory `child`; nó **không** cho `nested.txt`.

Một ví dụ đệ quy khái niệm:

```java
static void visit(File directory) {
    File[] children = directory.listFiles();
    if (children == null) {
        return; // Cần chính sách báo lỗi phù hợp ứng dụng.
    }
    for (File child : children) {
        if (child.isDirectory()) {
            visit(child);
        } else if (child.isFile()) {
            System.out.println(child.getPath());
        }
    }
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Nó cố tình đơn giản, **không thích hợp để dùng nguyên xi trên cây không tin cậy**, vì:

- Symlink tới directory có thể dẫn đến vòng lặp hoặc đi ra ngoài root nếu implementation đi theo liên kết và ứng dụng không kiểm soát.
- Cây sâu có thể gây `StackOverflowError`.
- Directory có thể thay đổi trong lúc duyệt; `listFiles()` có thể trả `null` mà ví dụ lặng lẽ bỏ qua.
- Liệt kê hàng triệu phần tử tạo mảng lớn.
- Quyền truy cập, filesystem từ xa, device node hoặc đường dẫn đặc biệt có thể yêu cầu chính sách riêng.

Với mã sản phẩm cần duyệt sâu, hãy xem `Files.walkFileTree` cùng `FileVisitor`, giới hạn độ sâu, chính sách `FOLLOW_LINKS`, xử lý lỗi và kiểm soát vòng lặp. Nếu chỉ duyệt một cấp, không cần recursion.

## 13. Vấn đề bảo mật: symlink, race condition và dữ liệu người dùng

Các phương thức `File.isFile()`, `isDirectory()` và `listFiles()` quan sát trạng thái **có thể thay đổi**. Nếu ứng dụng quét directory mà người dùng không tin cậy có thể sửa, đừng kết luận một pathname luôn chỉ đến cùng một object qua các bước:

```text
T1: listFiles() thấy "upload.txt"
T2: isFile() trả true
T3: process khác thay "upload.txt" thành liên kết/đích khác
T4: ứng dụng mở và xử lý đường dẫn đó
```

Đây là ví dụ **TOCTOU** (*time of check to time of use*). Kiểm tra tại T2 không khóa object cho thao tác T4.

Điểm phòng tránh ở mức thiết kế:

1. Không tin tên file từ nguồn không kiểm soát; kiểm tra ràng buộc đường dẫn theo hệ thống của bạn.
2. Không dựa duy nhất vào `getCanonicalPath()`, `isFile()` hoặc `startsWith` string để giải quyết mọi cuộc đua symlink. Việc check và open vẫn có thể là hai bước khác nhau.
3. Dùng API và cờ mở theo chính sách mong muốn: NIO.2 có `LinkOption.NOFOLLOW_LINKS` cho những thao tác thích hợp và `SecureDirectoryStream` trên provider có hỗ trợ; không giả định nó có sẵn ở mọi filesystem.
4. Giới hạn root được phép truy cập, quyền OS, depth, số entry, thời gian và tài nguyên xử lý.
5. Khi ứng dụng chỉ phân tích dữ liệu thông thường trong directory do chính nó tạo và kiểm soát, các filter đơn giản thường đủ; không cần phức tạp hóa nếu threat model không yêu cầu.

**FileFilter không phải cơ chế bảo mật.** Nó là callback quyết định một entry xuất hiện trong kết quả listing; nó không ngăn process khác thay directory và không bảo vệ thao tác mở file sau đó.

## 14. `java.io.File` truyền thống so với NIO.2

Các API từ Java 7 trong `java.nio.file` có thể giúp xử lý lỗi và duyệt directory linh hoạt hơn. Bài này tập trung vào `File`, nhưng cần biết hướng di chuyển khi viết mã mới.

| Nhu cầu | `java.io.File` | NIO.2 thường dùng |
|---|---|---|
| Liệt kê con trực tiếp | `File.listFiles()` | `Files.list(Path)` |
| Liệt kê con theo filter | `listFiles(FileFilter)`, `listFiles(FilenameFilter)` | `Files.newDirectoryStream(Path, filter)` |
| Chỉ khớp glob tên | `FilenameFilter` viết điều kiện | `Files.newDirectoryStream(dir, "*.txt")` |
| Duyệt cây thư mục | Tự recursion | `Files.walk` / `Files.walkFileTree` |
| Có thể nhận `IOException` rõ hơn | `listFiles()` có thể trả `null` | `Files.list`/`DirectoryStream` báo lỗi bằng exception |
| Quản lý vòng đời listing | Mảng không phải resource cần close | Stream/directory stream cần `close()` |
| Tính năng filesystem hiện đại | API hạn chế | `Path`, `Files`, attributes, link options |

**`Files.list(Path)` trả `Stream<Path>` cần đóng**; đừng bỏ quên try-with-resources. Stream liệt kê cũng không tự bảo đảm thứ tự; nếu cần output theo tên, sort tường minh. Trong lúc duyệt, lỗi I/O xảy ra muộn có thể xuất hiện qua `UncheckedIOException`.

`DirectoryStream<Path>` thường phù hợp khi muốn duyệt entry theo lô mà không tạo toàn bộ `File[]` cùng lúc. Tuy nhiên nó không tự sort, không tự recursion, cần close, và vẫn có các vấn đề trạng thái filesystem thay đổi.

### Ví dụ Java 17: so sánh `listFiles` và `Files.list`

Lưu **`FileAndNioListingDemo.java`**:

```java
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FileAndNioListingDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("nio-list-");

        try {
            Files.writeString(root.resolve("b.txt"), "b");
            Files.writeString(root.resolve("a.txt"), "a");

            File[] oldApi = root.toFile().listFiles();
            if (oldApi == null) {
                throw new IOException("Legacy listing failed");
            }
            String legacy = Arrays.stream(oldApi)
                .map(File::getName)
                .sorted()
                .collect(Collectors.joining(", "));

            String modern;
            try (Stream<Path> entries = Files.list(root)) {
                modern = entries
                    .map(path -> path.getFileName().toString())
                    .sorted()
                    .collect(Collectors.joining(", "));
            }

            System.out.println("File: " + legacy);
            System.out.println("NIO: " + modern);
        } finally {
            Files.deleteIfExists(root.resolve("a.txt"));
            Files.deleteIfExists(root.resolve("b.txt"));
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac FileAndNioListingDemo.java
java FileAndNioListingDemo
```

Stdout khi thao tác file thành công:

```text
File: a.txt, b.txt
NIO: a.txt, b.txt
```

Điều chứng minh: hai API có thể liệt kê cùng các **entry trực tiếp**. Khác biệt ở **kiểu trả về và cơ chế vòng đời**: `File[]` là mảng đã nhận về, còn `Files.list` tạo `Stream<Path>` cần được đóng để giải phóng resource. Không dùng ví dụ này để kết luận NIO tự sort; hai nhánh đều gọi `sorted()`.

## 15. Khi nào dùng `list(FilenameFilter)` và khi nào `listFiles(FileFilter)`?

### Trường hợp A — chọn tên cấu hình

Yêu cầu: “Liệt kê các file có tên `config-*.properties` để hiển thị”. Nếu chỉ cần tên và quy tắc tên, `list(FilenameFilter)` ngắn gọn:

```java
String[] configs = dir.list((parent, name) ->
    name.startsWith("config-") && name.endsWith(".properties")
);
```

Đây là **đoạn minh họa**. Nếu chỉ chọn file thông thường, thêm `new File(parent, name).isFile()`; nếu cần pattern phức tạp, cân nhắc glob từ NIO.2.

### Trường hợp B — chọn file log lớn hơn 1 MiB

Yêu cầu: “Chỉ các file thông thường `.log` có kích thước lớn hơn 1 MiB”.

```java
FileFilter largeLogs = file ->
    file.isFile()
        && file.getName().endsWith(".log")
        && file.length() > 1024L * 1024L;

File[] result = dir.listFiles(largeLogs);
```

Đây là **đoạn minh họa**; `dir` là `File`, cần import `File` và `FileFilter`. `FileFilter` đọc được `File.length()` trực tiếp, nhưng kết quả vẫn là trạng thái nhất thời; không thay thế kiểm tra trong quá trình mở/đọc file thật.

### Trường hợp C — chỉ liệt kê thư mục con

```java
File[] directories = dir.listFiles(File::isDirectory);
```

Đây là **đoạn minh họa**. Java suy ra `FileFilter` từ method reference một tham số. Cần kiểm tra `null` như mọi lời gọi `listFiles`.

### Trường hợp D — chỉ muốn đuôi `.txt` và kết quả là `File[]`

```java
File[] texts = dir.listFiles(
    (parent, name) -> name.endsWith(".txt")
);
```

Đây là **đoạn minh họa**; lambda hai tham số chọn `FilenameFilter`, nhưng kiểu trả về vẫn là `File[]`. Đừng lầm rằng “dùng FilenameFilter thì bắt buộc nhận String[]”: **phương thức bạn gọi** quyết định kiểu trả về.

## 16. Lỗi phổ biến và cách khắc phục

1. **Không kiểm tra `null` trước khi lặp.** `list()`/`listFiles()` có thể thất bại; phân biệt `null` với mảng rỗng.
2. **Tưởng `list()` trả đường dẫn đầy đủ.** Nó trả tên con; khi mở cần `new File(parent, name)`.
3. **Dùng `new File(name)` trong `FilenameFilter` để kiểm tra entry.** Việc này có thể kiểm tra sai working directory; dùng `new File(dir, name)`.
4. **Tưởng tên `.txt` chắc chắn là file.** Directory cũng có thể tên `archive.txt`; kiểm tra loại khi cần.
5. **Tưởng `FileFilter` và `FilenameFilter` hoán đổi được ở mọi overload.** Không có `list(FileFilter)`; hai `listFiles` overload nhận kiểu callback khác.
6. **Tưởng kết quả đã sort.** API không bảo đảm; sort kết quả với comparator rõ ràng.
7. **Tưởng `listFiles()` đệ quy.** Chỉ con trực tiếp; muốn đệ quy phải thiết kế traversal.
8. **Tin `isDirectory()` trước listing là đủ.** Directory có thể biến mất hoặc quyền truy cập thay đổi; vẫn phải xử lý kết quả.
9. **Bỏ qua trường hợp quyền truy cập hạn chế.** Legacy API đôi khi chỉ trả `null`, không cung cấp nguyên nhân chi tiết; dùng NIO.2 khi cần báo lỗi cụ thể.
10. **Lọc dựa trên tên mà tin nội dung/định dạng cũng đúng.** Đuôi file không chứng minh dữ liệu hợp lệ; kiểm tra nội dung khi xử lý.
11. **Đưa side effect vào `accept()`.** Filter nên là hàm kiểm tra, tránh xóa/di chuyển các entry trong khi đang liệt kê.
12. **Dùng recursion đơn giản trên cây có symlink không kiểm soát.** Có thể gặp vòng lặp, vượt root hoặc tràn stack; cân nhắc NIO.2 với chính sách liên kết.
13. **Bỏ qua TOCTOU.** Kết quả `listFiles()` không đảm bảo file vẫn tồn tại hoặc không bị thay ở lúc mở.
14. **Đọc toàn bộ directory cực lớn vào `File[]` mà không cân nhắc bộ nhớ.** Khi quy mô lớn, `DirectoryStream` và streaming traversal có thể tốt hơn.
15. **Quên đóng `Files.list`/directory stream.** Khác với mảng `File[]`, những API này giữ tài nguyên cần được đóng qua TWR.
16. **Tự coi so sánh tên với `equalsIgnoreCase` là cùng semantics filesystem.** Mỗi filesystem có quy tắc so sánh đường dẫn/case/Unicode riêng; cần chính sách ứng dụng rõ ràng.
17. **Hiểu sai `FileFilter` là bộ lọc bảo mật.** Nó chỉ chọn kết quả liệt kê, không khóa quyền truy cập và không chống sửa entry đồng thời.

## 17. Bài tập tự kiểm tra

**Câu 1.** Khác biệt giữa `File.list()` và `File.listFiles()`?

**Đáp án:** `list()` trả `String[]` tên entry; `listFiles()` trả `File[]` đại diện đường dẫn entry. Cả hai chỉ con trực tiếp và có thể trả `null`.

**Câu 2.** `FilenameFilter.accept(File dir, String name)` nhận `name` là đường dẫn đầy đủ hay tên con?

**Đáp án:** Tên con. Nếu cần truy vấn file, tạo `new File(dir, name)`.

**Câu 3.** Muốn lọc các **file** `.csv` nhưng loại directory cũng mang tên `.csv`, viết thế nào?

**Đáp án:** Dùng `FileFilter file -> file.isFile() && file.getName().endsWith(".csv")`, hoặc `FilenameFilter` kết hợp `new File(dir, name).isFile()`.

**Câu 4.** `listFiles((parent, name) -> ...)` trả `String[]` hay `File[]`?

**Đáp án:** `File[]`. Lambda hai tham số chọn overload `FilenameFilter`; tên phương thức `listFiles` quyết định kiểu trả về.

**Câu 5.** `listFiles()` trả `null` có nghĩa thư mục rỗng?

**Đáp án:** Không. Directory rỗng thường trả mảng độ dài 0; `null` có thể báo không phải directory hoặc lỗi I/O. Cần báo lỗi thay vì giả định rỗng.

**Câu 6.** API có bảo đảm file được trả theo tên alphabet không?

**Đáp án:** Không. Phải tự sort nếu cần thứ tự xác định.

**Câu 7.** `File.listFiles()` có tự lấy các file ở mọi directory cấp dưới không?

**Đáp án:** Không. Nó chỉ liệt kê entry trực tiếp; phải chủ động duyệt cây hoặc dùng NIO.2 traversal.

**Câu 8.** Vì sao kiểm tra `file.isFile()` rồi `Files.readString(file.toPath())` vẫn có rủi ro?

**Đáp án:** File có thể bị thay/xóa giữa lúc kiểm tra và lúc đọc (TOCTOU). Kết quả filter không khóa identity hoặc trạng thái file.

**Câu 9.** Nếu cần duyệt directory rất lớn và thông tin lỗi rõ ràng hơn, nên xem API nào?

**Đáp án:** `Files.newDirectoryStream(Path)` hoặc `Files.list(Path)`; dùng try-with-resources để đóng. Nếu duyệt nhiều cấp, `Files.walk` hoặc `Files.walkFileTree` theo yêu cầu.

**Câu 10.** Khi nào chỉ lọc theo tên là đủ, khi nào nên kiểm tra metadata?

**Đáp án:** Nếu bài toán chỉ hiển thị/chọn tên theo mẫu, `FilenameFilter` đơn giản thường đủ. Khi yêu cầu file thông thường, directory, kích thước hoặc thuộc tính, `FileFilter` phù hợp hơn; nhớ rằng metadata vẫn có thể đổi khi thao tác thật.

## Tổng kết

- `list()` và `list(FilenameFilter)` trả **`String[]` tên con**.
- `listFiles()`, `listFiles(FilenameFilter)`, `listFiles(FileFilter)` trả **`File[]` đường dẫn con**.
- `FilenameFilter` nhận **`(dir, name)`**; `FileFilter` nhận **`File pathname`**.
- Cả hai họ API chỉ liệt kê **một cấp**, **không bảo đảm thứ tự**, có thể trả **`null`**, và không ngăn filesystem thay đổi trong lúc xử lý.
- Khi cần sắp xếp, kiểm tra loại mục, duyệt sâu, chống TOCTOU hoặc xử lý lỗi tốt hơn, chọn API/phương án phù hợp, thường là `Path` và NIO.2 cho mã mới.

Nắm được sự khác biệt giữa **tên**, **đường dẫn**, **loại entry** và **kết quả liệt kê** sẽ giúp bạn sử dụng lớp `java.io.File` truyền thống đúng và tránh những lỗi I/O khó phát hiện.
