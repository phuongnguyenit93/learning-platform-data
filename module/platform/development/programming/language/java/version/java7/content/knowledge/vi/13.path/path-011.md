# Kiểm tra đường dẫn nằm trong thư mục được phép bằng `Path` (Java 7+)

> **Chủ đề:** Kiểm tra một đường dẫn có thuộc phạm vi thư mục được phép hay không khi ứng dụng nhận tên tệp/thư mục từ bên ngoài. Trọng tâm là dùng `java.nio.file.Path` thay cho phép so sánh tiền tố chuỗi; hiểu vai trò của `toAbsolutePath()`, `normalize()` và `startsWith(Path)` đối với cấu trúc đường dẫn; kiểm chứng symlink bằng `toRealPath()` đối với đối tượng đã tồn tại; và nhận biết giới hạn của cách “kiểm tra xong rồi mở tệp” trước các thay đổi filesystem đồng thời (*TOCTOU*). Các API NIO.2 cốt lõi có từ Java 7 và **vẫn phù hợp trên Java 17+**.

## 1. Bài toán: cho phép trong vùng A, từ chối đường dẫn ra ngoài vùng A

Giả sử ứng dụng chỉ cho phép đọc tài liệu trong một thư mục do hệ thống quản lý:

```text
allowed/
  reports/
    jan.txt
    feb.txt
  images/
    icon.png

outside/
  secret.txt
```

Đây là **sơ đồ cấu trúc thư mục**, không phải lệnh tạo file. Nếu một request yêu cầu `reports/jan.txt`, hệ thống có thể chấp nhận. Nếu request yêu cầu `../outside/secret.txt`, chính sách cần **từ chối**, dù ứng dụng vẫn có quyền filesystem để đọc tệp đó.

Mục tiêu kiểm soát được gọi là **path containment**: một đường dẫn được chấp nhận chỉ khi nằm trong vùng đường dẫn/tài nguyên được cho phép theo một **chính sách xác định**.

Nhưng “nằm trong” có ít nhất hai nghĩa cần phân biệt:

1. **Containment theo cú pháp (*lexical*):** sau khi tạo một `Path` tuyệt đối và rút gọn các đoạn `.`/`..`, các name elements của candidate bắt đầu bằng những name elements của base.
2. **Containment của đối tượng filesystem thật (*physical/real*):** khi đã phân giải các symbolic links và thực thể filesystem, đối tượng đích thật sự nằm dưới phạm vi được phép.

Hai nghĩa này **không luôn tương đương**. Một đường dẫn trông như `allowed/link/secret.txt` có thể đi qua symbolic link `link` trỏ tới `outside`. Nó vượt qua phép kiểm tra lexical nhưng **không** vượt qua kiểm tra real path nếu kiểm tra đúng đường dẫn đã tồn tại.

**Giới hạn quan trọng:** ngay cả việc kiểm tra real path trước rồi mới gọi `Files.readString` hoặc `Files.newOutputStream` **không mặc nhiên loại bỏ race condition** nếu kẻ khác có quyền thay đổi thư mục/symlink giữa hai thao tác. Đừng trình bày một phép `startsWith` hay `toRealPath` duy nhất như một giải pháp sandbox tuyệt đối.

## 2. Phân biệt `Path` với chuỗi ký tự đường dẫn

`Path` đại diện cho một đường dẫn theo **quy tắc của file-system provider**. Nó có thành phần root và các **name elements**. Java có thể kiểm tra mối quan hệ cấu trúc bằng các method chuẩn:

```java
Path base = Path.of("safe").toAbsolutePath().normalize();
Path candidate = base.resolve("docs").resolve("report.txt").normalize();

boolean inside = candidate.startsWith(base);
```

Đây là snippet với import `java.nio.file.Path`. Với provider mặc định thông thường, `inside` là `true`. Không cần biết dấu phân cách trên máy là `/` hay `\`; `Path.startsWith(Path)` so sánh **các thành phần đường dẫn**, không đơn giản là `String.startsWith`.

Từ Java 7 có thể sử dụng `java.nio.file.Paths.get(...)` để tạo Path. `Path.of(...)` là cách viết được bổ sung từ Java 11; dùng trong các chương trình Java 17+ ở bài này. Điều kiện containment và cách đọc cấu trúc Path vẫn là kiến thức còn hiệu lực.

### 2.1. Vì sao `String.startsWith` dễ sai?

So sánh theo chuỗi:

```java
String base = ".../safe";
String candidate = ".../safe-backup/report.txt";
boolean allowed = candidate.startsWith(base); // Có thể true dù nằm ngoài.
```

Đây là snippet minh họa **lỗi thiết kế**, không phải kiểm tra bảo mật. `safe-backup` chỉ có tiền tố ký tự giống `safe`; nó **không phải con** của thư mục `safe`.

Sửa bằng so sánh `Path` sau khi đã chuyển chúng về cùng ngữ cảnh/kiểu đường dẫn phù hợp:

```java
Path base = Path.of("safe").toAbsolutePath().normalize();
Path sibling = base.resolveSibling(base.getFileName() + "-backup")
                   .resolve("report.txt");

boolean allowed = sibling.startsWith(base); // false.
```

Các name elements của `sibling` chứa `safe-backup` tại vị trí tương ứng, không phải `safe`. `Path.startsWith` tính mối quan hệ theo **ranh giới component**, ngăn lỗi nhầm tiền tố chuỗi.

**Không nhầm:** `Path.startsWith(String other)` (nếu gọi overload String trên Path) cũng chuyển đối số thành một Path và so sánh theo ngữ nghĩa `Path`. Sai lầm chính là **`candidate.toString().startsWith(base.toString())`**.

### 2.2. Bốn toán tử không có cùng nhiệm vụ

| API | Ý nghĩa | Có truy cập filesystem không? |
| --- | --- | --- |
| `base.resolve(relative)` | Ghép đường dẫn theo quy tắc provider | Không |
| `path.toAbsolutePath()` | Đưa Path về biểu diễn absolute | Không cần xác minh file tồn tại |
| `path.normalize()` | Rút gọn các đoạn `.` và `..` về cú pháp | Không |
| `path.startsWith(base)` | So sánh prefix theo root/name elements | Không |
| `path.toRealPath()` | Lấy đường dẫn thật của đối tượng đã tồn tại, theo quy tắc giải symlink | Có |

Chọn đúng tầng kiểm tra theo hành động sắp thực hiện. Nếu cần xác minh một Path thuộc một thư mục theo **cú pháp**, bốn method đầu có vai trò chính. Nếu cần bảo vệ một hành động với **file đã tồn tại** và có symlink, `toRealPath` là thành phần bổ sung quan trọng.

## 3. Đầu vào tuyệt đối, tương đối và dấu `..`

Một ứng dụng thường yêu cầu khách hàng gửi **đường dẫn tương đối** như `reports/jan.txt` chứ không phải full path từ hệ điều hành.

Các ví dụ cần phân biệt:

| Giá trị do caller đưa vào | Ý nghĩa và chính sách minh họa |
| --- | --- |
| `reports/jan.txt` | Một đường dẫn tương đối có thể nằm trong vùng được phép |
| `reports/../ok.txt` | Sau lexical normalize, vẫn nằm trong base; có thể chấp nhận nếu chính sách cho phép |
| `../secret.txt` | Có ý định đi ra thư mục cha; phải từ chối khi normalized target nằm ngoài |
| `a/../../secret.txt` | Dù ban đầu có tên `a` bên trong, normalize có thể đi ra ngoài |
| `.` | Trỏ tới base; có thể từ chối nếu API chỉ cho phép một **file bên trong**, không cho phép chính thư mục root |
| Đường dẫn absolute | Có thể chỉ tới ngoài vùng cho phép; chính sách minh họa **từ chối ngay** |

**Luật quan trọng:** trước khi đánh giá containment, cần nêu rõ **loại input được phép**. Nếu API nói chỉ chấp nhận *relative path*, nên từ chối input absolute ngay. Không dựa vào việc `resolve` sẽ luôn “nhét” một absolute path vào base, bởi quy tắc `resolve` có thể ưu tiên đường dẫn tuyệt đối đầu vào.

### 3.1. Normalize sau khi ghép

Một chuỗi thao tác thường dùng:

```java
Path base = trustedRoot.toAbsolutePath().normalize();
Path requested = Path.of(userSuppliedText);
Path candidate = base.resolve(requested).normalize();
```

Đây là snippet: `trustedRoot` là Path đã được cấu hình đáng tin cậy và `userSuppliedText` là chuỗi cần validate. Trước `resolve`, hãy xác nhận `requested` **không absolute** theo chính sách. Sau `resolve`, normalize để phần `..` được rút gọn trong biểu diễn Path.

**Không chỉ normalize chuỗi input rồi so sánh text:** thao tác này phải xét cả **base Path** và **candidate Path** sau khi ghép theo provider. Khi root/base có dạng tương đối, đường dẫn của hai phía phải được đưa về ngữ cảnh nhất quán trước khi so sánh.

### 3.2. Có nên cấm mọi thành phần `..`?

Một chính sách bảo thủ có thể **cấm mọi thành phần `..`** ngay từ đầu nếu ứng dụng không có lý do nghiệp vụ cho chúng. Tuy vậy đây là **quyết định chính sách**, không phải yêu cầu bắt buộc của Java.

Ví dụ `reports/../ok.txt` sau normalize vẫn là `ok.txt` trong base; nếu API cho phép đường dẫn có đoạn tham chiếu cha rồi rút gọn, lexical containment có thể chấp nhận. Nếu quy ước đầu vào chỉ cho phép tên đơn giản hoặc “không có đường dẫn ngược”, cứ từ chối `..` ở mức parsing/validation.

Đừng nhầm “đã từ chối `..`” với “đã bảo vệ hoàn toàn”: symbolic links, absolute input và race condition vẫn cần chính sách riêng.

## 4. Chương trình hoàn chỉnh: kiểm tra lexical containment

Đây là **kiểm tra cấu trúc**, hữu ích khi root và nội dung thư mục là phần đáng tin cậy hoặc khi bạn mới muốn lọc các request có thể thoát ra theo `..`. Nó **không** tự xác nhận tài nguyên trên đĩa có tồn tại và **không tự chống symlink escape**.

Lưu thành `LexicalContainmentDemo.java`:

```java
import java.nio.file.Path;
import java.util.Objects;

public class LexicalContainmentDemo {
    static Path checked(Path base, Path supplied) {
        Objects.requireNonNull(base, "base required");
        Objects.requireNonNull(supplied, "supplied required");
        if (!base.isAbsolute()) {
            throw new IllegalArgumentException("base must be absolute");
        }
        if (supplied.isAbsolute()) {
            throw new IllegalArgumentException("absolute input forbidden");
        }
        Path target = base.resolve(supplied).normalize();
        if (!target.startsWith(base) || target.equals(base)) {
            throw new IllegalArgumentException("outside permitted directory");
        }
        return target;
    }

    static void attempt(String label, Path base, Path supplied) {
        try {
            Path target = checked(base, supplied);
            String relative = base.relativize(target).toString().replace('\\', '/');
            System.out.println(label + "=ACCEPT:" + relative);
        } catch (IllegalArgumentException error) {
            System.out.println(label + "=REJECT");
        }
    }

    public static void main(String[] args) {
        Path base = Path.of("sandbox").toAbsolutePath().normalize();

        attempt("nested", base, Path.of("reports", "2026.txt"));
        attempt("escape", base, Path.of("..", "secret.txt"));
        attempt("doubleEscape", base, Path.of("a", "..", "..", "secret.txt"));
        attempt("withinAfterNormalize", base, Path.of("a", "..", "ok.txt"));
        attempt("rootOnly", base, Path.of("."));
        attempt("absoluteInput", base, base.resolve("escape.txt"));
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac -encoding UTF-8 --release 17 LexicalContainmentDemo.java
java LexicalContainmentDemo
```

Stdout chính xác đã kiểm chứng (ví dụ chuẩn hóa dấu phân cách **chỉ khi hiển thị**):

```text
nested=ACCEPT:reports/2026.txt
escape=REJECT
doubleEscape=REJECT
withinAfterNormalize=ACCEPT:ok.txt
rootOnly=REJECT
absoluteInput=REJECT
```

### 4.1. Phân tích từng tình huống

- `nested` là `reports/2026.txt`: sau `base.resolve(...)` và `normalize()`, candidate vẫn bắt đầu bằng base và không trùng base nên được chấp nhận.
- `escape` là `../secret.txt`: normalize làm candidate đi lên trên base, nên `candidate.startsWith(base)` là false; từ chối.
- `doubleEscape` có `a/../../secret.txt`: dù có một tên thư mục con ban đầu, đường dẫn đã normalize đi ra ngoài; từ chối.
- `withinAfterNormalize` có `a/../ok.txt`: kết quả là `ok.txt` trong base; chính sách demo cho phép.
- `rootOnly` có `.`: ứng với chính base. `Path.startsWith(base)` sẽ true, nhưng demo **cấm dùng base như đích cuối** bằng `target.equals(base)` vì API này được thiết kế cho tệp **bên trong** vùng.
- `absoluteInput` truyền một absolute Path; ứng dụng từ chối **trước** bước resolve.

Đường dẫn được in ra theo dạng tương đối để không lộ hoặc phụ thuộc thư mục làm việc thực tế. `replace('\\','/')` chỉ phục vụ **hiển thị stdout**, không làm thay nhiệm vụ kiểm tra hay chuyển Path cho filesystem.

### 4.2. Tiền điều kiện của hàm minh họa

`checked` yêu cầu base đã là absolute. Trong code thực tế, hãy chuẩn hóa **base** từ một cấu hình đáng tin cậy và kiểm soát vòng đời của nó. Nếu base đã chứa các đoạn `..` nhưng chưa normalize, so sánh lexical có thể làm kết quả khó hiểu.

Ví dụ thường tạo base một lần:

```java
Path base = configuredRoot.toAbsolutePath().normalize();
```

Đây là snippet, `configuredRoot` phải đến từ cấu hình đáng tin và được validate. **Không** lấy `configuredRoot` trực tiếp từ cùng đầu vào chưa tin cậy mà bạn đang cố kiểm soát. Nếu caller có thể chọn cả root, mọi containment check trở nên vô nghĩa về quyền truy cập.

Nếu API cho phép chọn **chính thư mục base**, bỏ điều kiện `target.equals(base)` một cách có chủ đích; đừng coi root bắt buộc được phép hay cấm cho mọi bài toán.

## 5. Chương trình kiểm chứng bẫy tiền tố chuỗi

Lưu thành `PrefixBoundaryDemo.java`:

```java
import java.nio.file.Path;

public class PrefixBoundaryDemo {
    public static void main(String[] args) {
        Path base = Path.of("safe").toAbsolutePath().normalize();
        Path sibling = base.resolveSibling(base.getFileName() + "-backup")
                .resolve("report.txt");
        Path child = base.resolve("docs").resolve("report.txt");

        System.out.println("stringPrefix=" +
                sibling.toString().startsWith(base.toString()));
        System.out.println("segmentPrefix=" + sibling.startsWith(base));
        System.out.println("childPrefix=" + child.startsWith(base));
        System.out.println("rootIsInsideWhenAllowed=" + base.startsWith(base));
        System.out.println("lexicalParentContained=" +
                base.resolve("docs").resolve("..").resolve("ok.txt")
                        .normalize().startsWith(base));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PrefixBoundaryDemo.java
java PrefixBoundaryDemo
```

Stdout đã xác minh:

```text
stringPrefix=true
segmentPrefix=false
childPrefix=true
rootIsInsideWhenAllowed=true
lexicalParentContained=true
```

**Tại sao đây là phép thử quan trọng?**

- Base kết thúc bằng một name element `safe`.
- Sibling có name element `safe-backup`, là **tên khác**, dù chuỗi ký tự bắt đầu bằng `safe`.
- `String.startsWith` trả true → kiểm tra **sai** sẽ chấp nhận ngoài phạm vi.
- `Path.startsWith(Path)` trả false → so sánh **theo ranh giới tên**, không nhầm hai thư mục.
- `base.startsWith(base)` trả true: **prefix theo Path thường bao gồm chính base**, nên muốn chỉ cho phép con thật sự thì thêm chính sách khác biệt với root.

Không cần tự chèn dấu `/` ở cuối tên base để “sửa” `String.startsWith`. Làm vậy vẫn phụ thuộc separator/provider và dễ phát sinh tình huống cạnh. Dùng thẳng `Path`.

## 6. `Path.startsWith` là kiểm tra name elements, không phải chứng nhận quyền

Các thuộc tính của `startsWith(Path other)`:

- Xem root và từng **name element** theo semantics của file-system provider.
- Không tự resolve symlink.
- Không tự đi đọc tệp hoặc kiểm tra quyền filesystem.
- Không tự normalize toàn bộ chuỗi mà bạn đưa vào trước đó; hãy gọi `normalize()` có chủ đích nếu đó là mô hình muốn áp dụng.
- Nếu hai Path không tương thích về filesystem/provider/root, phép so sánh có thể không cho kết quả “trong phạm vi” dù chuỗi hiển thị giống nhau.

### 6.1. Tại sao phải so sánh Path cùng ngữ cảnh?

Nếu một Path là tương đối, một Path là tuyệt đối, câu hỏi “bắt đầu bằng” có thể không có ý nghĩa containment như mong muốn. Vì thế hãy dùng một base tin cậy và tạo candidate **từ base đó**. Với đối tượng đã tồn tại, thường nên so sánh hai `toRealPath()` để làm rõ symlink và canonical names.

Trên hệ điều hành có filesystem case-insensitive, cách Path/provider xử lý ký tự hoa/thường có thể khác môi trường case-sensitive. Đừng tự chuẩn hóa case bằng cách `toLowerCase()` trên chuỗi đường dẫn như một giải pháp đa nền tảng; dùng provider-aware operations và kiểm thử trên hệ thống thực tế.

### 6.2. `normalize()` không xác minh file tồn tại

`Path.of("folder","..","secret.txt").normalize()` có thể thành `secret.txt` ngay cả khi `folder` chưa tồn tại. Đây là **lexical transformation**, không phải truy vấn thư mục.

Nếu mục tiêu là chỉ kiểm tra *tên đường dẫn cho phép*, điều đó hữu ích. Nếu mục tiêu là truy cập một file đã tồn tại theo đúng đối tượng thực, phải xem các bước tiếp theo.

### 6.3. Tập tên có ký tự ngăn cách

Nếu API nhận tên file đơn (không cho phép nhiều cấp thư mục), nên validate theo hợp đồng riêng: path phải có **đúng một name element hợp lệ**, không phải absolute/root-only, không là `"."` hoặc `".."`, và không chứa cú pháp điều hướng bị cấm.

Một ứng dụng chỉ chấp nhận `avatar.png` thường không cần mở rộng bề mặt tấn công bằng việc cho phép `folder/subfolder/avatar.png`. Nếu cần subdirectory, mới dùng containment tương ứng. **Thu hẹp chức năng đầu vào** thường dễ đánh giá quyền hơn là cố chấp nhận mọi biến thể path.

## 7. Đối tượng đã tồn tại: dùng `toRealPath()` để phát hiện symlink

`toRealPath()` trả đường dẫn thật của một file/directory **đã tồn tại**; theo mặc định, nó **giải symbolic links** đến đích cuối cùng (theo chính sách provider).

Ví dụ:

```java
Path realBase = allowedDirectory.toRealPath();
Path realTarget = requestedFile.toRealPath();

if (!realTarget.startsWith(realBase)) {
    throw new SecurityException("outside allowed directory");
}
```

Đây là **snippet trong method khai báo hoặc xử lý `IOException`**, với `allowedDirectory`/`requestedFile` đã có. Nó là **kiểm tra tại thời điểm thực thi**, không phải chứng minh một file handle sẽ luôn trỏ cùng đối tượng nếu có thay đổi đồng thời ở filesystem.

### 7.1. Cần bảo đảm cả base là thư mục đáng tin

Dùng `toRealPath()` với cả root và target giúp so sánh hai Path cùng biểu diễn thực tế. Tuy nhiên root phải được kiểm soát từ cấu hình và chính sách hệ thống; nếu root là symlink do bên không tin cậy thay được, việc giải root một lần không tự biến nó thành điểm neo bất biến.

Nên có:
- Thư mục được phép do ứng dụng/quản trị tạo và kiểm soát.
- Quyền filesystem hạn chế người không tin cậy thay đổi cấu trúc thư mục, liên kết hoặc parent.
- Root thực (`realBase`) được xác định trước phiên truy cập và quản lý trong phạm vi hợp lý.
- Phương án đặc biệt khi một đối tượng vẫn có thể bị đổi giữa lúc check và lúc open.

### 7.2. Nếu file chưa tồn tại thì `toRealPath()` làm gì?

`requestedFile.toRealPath()` thường ném `IOException`/`NoSuchFileException` khi file không tồn tại. Vì thế không dùng code kiểm tra cho **file đã tồn tại** để kiểm soát trực tiếp **file mới sắp tạo**. Với create-new cần kiểm tra parent hiện hữu và thực hiện thao tác tạo file theo chính sách khác, sẽ được minh họa ở phần 10.

## 8. Ví dụ runnable: kiểm tra file hiện hữu

Lưu thành `ExistingFileContainmentDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class ExistingFileContainmentDemo {
    static Path checkExisting(Path allowedDirectory, Path requested)
            throws IOException {
        Path realBase = allowedDirectory.toRealPath();
        Path realRequested = requested.toRealPath();
        if (!realRequested.startsWith(realBase) || realRequested.equals(realBase)) {
            throw new SecurityException("outside allowed directory");
        }
        return realRequested;
    }

    public static void main(String[] args) throws IOException {
        Path base = Files.createTempDirectory("allowed-");
        Path sub = base.resolve("reports");
        Path file = sub.resolve("note.txt");
        Path outside = Files.createTempFile("outside-", ".txt");
        try {
            Files.createDirectory(sub);
            Files.writeString(file, "hello", StandardCharsets.UTF_8);

            Path checked = checkExisting(base, file);
            System.out.println("inside=" +
                    checked.startsWith(base.toRealPath()));
            System.out.println("filename=" + checked.getFileName());
            System.out.println("text=" + Files.readString(checked, StandardCharsets.UTF_8));

            try {
                checkExisting(base, outside);
                throw new AssertionError("Outside file was accepted");
            } catch (SecurityException expected) {
                System.out.println("outside=REJECT");
            }

            try {
                checkExisting(base, sub.resolve("missing.txt"));
                throw new AssertionError("Missing file was accepted");
            } catch (NoSuchFileException expected) {
                System.out.println("missing=REJECT");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(base);
            Files.deleteIfExists(outside);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ExistingFileContainmentDemo.java
java ExistingFileContainmentDemo
```

Stdout trên môi trường cho phép tạo file tạm:

```text
inside=true
filename=note.txt
text=hello
outside=REJECT
missing=REJECT
```

**Giải thích từng đường đi:**

1. `Files.createTempDirectory` tạo một base thật; `Files.createDirectory` tạo thư mục con thật.
2. `Files.writeString` (có từ Java 11) tạo nội dung `hello`.
3. `checkExisting` phân giải `realBase` và `realRequested`. File trong `reports` có real path bắt đầu bằng base nên được chấp nhận.
4. Một file tạm **ngoài base** bị từ chối vì `realRequested.startsWith(realBase) == false`. Không dựa vào tên tiền tố tình cờ giống nhau.
5. Một file không tồn tại bị báo `NoSuchFileException`, tức không thể được xác nhận là file hiện hữu trong chính sách đang dùng.
6. `finally` chỉ xóa những file/thư mục tạm mà chương trình tự tạo. Không dùng đoạn cleanup như thao tác xóa dữ liệu thật của người dùng.

**Quan trọng:** ví dụ có bước `checkExisting` rồi bước `Files.readString(checked)` riêng biệt. Trong mô hình có đối thủ đủ quyền sửa filesystem giữa hai bước, đây **chưa phải bảo đảm race-free**. Tên `checkExisting` có ý nghĩa kiểm tra tại thời điểm gọi; không cam kết một open sau đó sẽ tham chiếu cùng inode/object.

### 8.1. Khi nào trả về `Path` đã real-resolved?

Trả real Path giúp caller sử dụng biểu diễn đối tượng đã được kiểm tra, giảm nguy cơ vô tình quay lại một đường dẫn lexical qua symlink ban đầu. Tuy nhiên thực thể filesystem có thể thay đổi sau khi hàm trả về, nên **trả Path không khóa object**. Nếu yêu cầu an toàn cao, phải kiểm soát quyền sửa thư mục và dùng chiến lược thao tác dựa trên handle.

### 8.2. Không dùng `Files.exists` như bước “chứng nhận an toàn”

Mô hình:

```java
if (Files.exists(candidate)) {
    Files.readString(candidate);
}
```

Đây là **snippet thiếu cơ chế xử lý rủi ro và lỗi**. `exists` không chứng minh candidate thuộc base, không bảo vệ symlink escape, và file có thể bị xóa/thay thế giữa check và read. Cách tốt hơn là mở tệp theo chính sách đã xác định và xử lý `IOException`/quyền truy cập theo hợp đồng. Đừng dùng `Files.exists` thay `toRealPath`/`Path.startsWith`.

## 9. Bẫy symlink: đường dẫn nhìn nằm trong nhưng đích nằm ngoài

Ví dụ:

```text
base/
  shortcut -> /some/outside/directory
  shortcut/secret.txt

outside/
  secret.txt
```

Đây là sơ đồ **minh họa symbolic link**, không phải cú pháp chạy được trên mọi hệ điều hành. Nếu `shortcut` là symlink tới một thư mục bên ngoài, thì đường dẫn `base/shortcut/secret.txt`:

- **Lexical containment:** true, vì các name elements bắt đầu bằng base.
- **Real containment:** false, vì hệ thống giải liên kết đến thư mục ngoài.

### 9.1. Chương trình có kiểm thử tùy khả năng tạo symbolic link

Lưu thành `SymlinkEscapeDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class SymlinkEscapeDemo {
    public static void main(String[] args) throws IOException {
        Path base = Files.createTempDirectory("allowed-");
        Path outside = Files.createTempDirectory("outside-");
        Path secret = outside.resolve("secret.txt");
        Path link = base.resolve("shortcut");
        try {
            Files.writeString(secret, "secret", StandardCharsets.UTF_8);
            try {
                Files.createSymbolicLink(link, outside);
            } catch (UnsupportedOperationException | IOException | SecurityException noLink) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            Path candidate = link.resolve("secret.txt");
            boolean lexical = candidate.normalize().startsWith(base.normalize());
            boolean physical = candidate.toRealPath().startsWith(base.toRealPath());

            System.out.println("lexicalInside=" + lexical);
            System.out.println("realInside=" + physical);
            if (!lexical || physical) {
                throw new AssertionError("Unexpected symbolic-link containment");
            }
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(secret);
            Files.deleteIfExists(base);
            Files.deleteIfExists(outside);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 SymlinkEscapeDemo.java
java SymlinkEscapeDemo
```

**Kết quả trên máy cho phép tạo symlink**:

```text
lexicalInside=true
realInside=false
```

**Kết quả trên môi trường từ chối hoặc không hỗ trợ tạo symlink** (như môi trường Windows kiểm thử không có quyền cần thiết):

```text
symlinkTest=SKIPPED
```

Hai nhánh là có chủ đích; đây là test phụ thuộc **capability và quyền của OS**. Nếu symlink được tạo, assertion bắt buộc xác nhận lexical là true trong khi physical là false. Nếu không thể tạo, chương trình ghi rõ `SKIPPED` chứ không giả vờ đã chứng minh tình huống đó. Cần chạy test trên môi trường CI có khả năng symlink nếu đây là yêu cầu bảo mật quan trọng.

### 9.2. Có nên chỉ dùng `LinkOption.NOFOLLOW_LINKS`?

`LinkOption.NOFOLLOW_LINKS` kiểm soát việc đi theo symbolic links ở các API có hỗ trợ option này. Nhưng không thể đơn giản thêm option vào một nơi và kết luận **toàn bộ đường dẫn gồm mọi thư mục cha** đều không thể chứa symlink. Ngữ nghĩa no-follow khác nhau theo method và provider. Nếu cần traversal an toàn, phải thiết kế rõ **mỗi thành phần** được giải quyết ra sao, quyền thư mục nào được tin tưởng và file handle được mở khi nào.

**Lưu ý kỹ thuật:** `toRealPath(LinkOption.NOFOLLOW_LINKS)` không phải giải pháp thay thế cho `toRealPath()` khi mục tiêu là xác định **đích thực theo các symlink**. Nó chủ đích thay đổi quy tắc follow link. Lựa chọn nào đúng tùy chính sách: *cấm symlink*, *cho phép symlink nếu đích vẫn trong vùng* hay *theo semantics của provider*.

## 10. File chưa tồn tại: kiểm tra parent thực và tạo không ghi đè

Một hệ thống upload cần tạo file **mới**; đích chưa tồn tại nên `toRealPath()` trên chính file mới không dùng được như ở phần 8.

Chiến lược **giảm rủi ro cho thư mục do ứng dụng kiểm soát**:

1. Root được lấy từ cấu hình đáng tin và đã tồn tại.
2. Chỉ nhận relative path theo policy; không nhận absolute input.
3. Tạo candidate bằng `base.resolve(relative).normalize()`.
4. Yêu cầu lexical candidate nằm trong base; cấm candidate bằng chính base nếu đích phải là file.
5. Xác định `candidate.getParent()` và gọi `parent.toRealPath()` nếu parent đã tồn tại.
6. Chỉ chấp nhận khi **real parent** vẫn nằm trong real base.
7. Tạo file bằng một thao tác yêu cầu **tên đích chưa tồn tại**, ví dụ `StandardOpenOption.CREATE_NEW`.
8. Giữ quyền sửa thư mục thuộc ứng dụng; nếu adversary có thể đổi parent giữa bước 6 và bước 7, **vẫn có TOCTOU**.

**Bước 8 không phải tiểu tiết.** Hai lần kiểm tra riêng biệt có thể đúng ở từng thời điểm nhưng một attacker có quyền thay directory entry trước khi mở file. Với hệ thống chịu đầu vào thù địch hoặc nhiều tenant, dùng cơ chế thao tác dựa trên directory handle khi provider hỗ trợ và bảo vệ filesystem permissions.

### 10.1. Chương trình đầy đủ: create-new có kiểm tra vị trí

Lưu thành `NewFileContainmentDemo.java`:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class NewFileContainmentDemo {
    static Path destination(Path root, Path relative) throws IOException {
        if (relative.isAbsolute()) {
            throw new IllegalArgumentException("absolute forbidden");
        }
        Path base = root.toRealPath();
        Path candidate = base.resolve(relative).normalize();
        if (!candidate.startsWith(base) || candidate.equals(base)) {
            throw new IllegalArgumentException("outside allowed directory");
        }
        Path parent = candidate.getParent();
        Path realParent = parent.toRealPath();
        if (!realParent.startsWith(base)) {
            throw new IllegalArgumentException("parent follows link outside");
        }
        return realParent.resolve(candidate.getFileName());
    }

    public static void main(String[] args) throws IOException {
        Path base = Files.createTempDirectory("uploads-");
        Path folder = base.resolve("incoming");
        Path file = folder.resolve("note.txt");
        try {
            Files.createDirectory(folder);
            Path checked = destination(base, Path.of("incoming", "note.txt"));
            try (OutputStream output = Files.newOutputStream(
                    checked, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
                output.write("ok".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("created=" + Files.isRegularFile(file));
            System.out.println("content=" + Files.readString(file, StandardCharsets.UTF_8));

            try {
                destination(base, Path.of("..", "outside.txt"));
                throw new AssertionError("Escape was accepted");
            } catch (IllegalArgumentException expected) {
                System.out.println("escape=REJECT");
            }

            try (OutputStream ignored = Files.newOutputStream(
                    checked, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
                throw new AssertionError("Existing file was overwritten");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("overwrite=REJECT");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(base);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 NewFileContainmentDemo.java
java NewFileContainmentDemo
```

Stdout đã xác minh:

```text
created=true
content=ok
escape=REJECT
overwrite=REJECT
```

**Điều chương trình xác minh:**

- `destination(...)` kiểm tra lexical, sau đó dùng `toRealPath()` của parent đã tồn tại.
- Một tên file nằm trong thư mục con được phép có thể được tạo.
- `Path.of("..","outside.txt")` bị từ chối trước khi có file nào được tạo bên ngoài.
- `Files.newOutputStream(..., CREATE_NEW, WRITE)` từ chối ghi đè một file đã tồn tại, bao gồm tình huống tên đích đã được chiếm; trên provider tuân thủ hợp đồng, `CREATE_NEW` có phép kiểm tra sự tồn tại và tạo tên mới **atomic**.
- Những thao tác này được thực hiện trong thư mục tạm do chương trình sở hữu, rồi dọn sạch.

**Không khẳng định quá mức:** `CREATE_NEW` ngăn ghi đè **tại tên cuối** theo hợp đồng open/create, nhưng **không tự cố định toàn bộ các thư mục cha** nếu chúng bị kẻ khác thay đổi đồng thời. Tham số `root` cũng phải thuộc phạm vi đã được xác minh và không được lấy từ cùng đầu vào untrusted.

### 10.2. Vì sao không dùng `Files.newOutputStream(path)` mặc định?

Khi không truyền open options, API có thể tạo file mới **hoặc truncate file đã tồn tại**. Nếu việc ghi là upload phải **không ghi đè**, đây là rủi ro không cần thiết.

`CREATE_NEW` thể hiện chính sách rõ: chỉ tạo khi chưa tồn tại. Nếu sản phẩm **cần** ghi đè, phải có quyền rõ ràng, kiểm tra tính toàn vẹn và quy trình thay thế file an toàn riêng; đừng ngầm coi mọi tên file do người dùng cung cấp đều có quyền overwrite.

### 10.3. Parent không tồn tại thì sao?

`parent.toRealPath()` sẽ thất bại khi thư mục parent chưa tồn tại. Đó là chủ ý của ví dụ: yêu cầu thư mục cấp cha đã được ứng dụng tạo và kiểm soát. Nếu hệ thống cho phép tạo cả cây thư mục con, hãy thiết kế một quy trình tạo từng đoạn tên với kiểm tra quyền và symlink/handle thích hợp.

Không thể chỉ thêm `Files.createDirectories(untrustedPath)` trước khi validate rồi coi kết quả an toàn: bạn có thể đã tạo thư mục ở ngoài root trước khi phát hiện lỗi.

## 11. TOCTOU: kiểm tra đúng tại thời điểm A chưa bảo đảm thao tác đúng tại thời điểm B

**TOCTOU** là viết tắt của *time of check to time of use*. Có thể xảy ra khi:

```text
T1: Ứng dụng kiểm tra /allowed/reports/file.txt => nằm trong base
T2: Tác nhân khác đổi /allowed/reports thành symlink trỏ ra ngoài
T3: Ứng dụng mở lại tên /allowed/reports/file.txt
T4: Tên ở thời điểm T3 có thể dẫn đến file khác so với T1
```

Đây là sơ đồ rủi ro; khả năng xảy ra phụ thuộc **quyền sửa thư mục/symlink**, filesystem và cách chương trình mở file.

### 11.1. Những gì `toRealPath()` giải quyết và chưa giải quyết

`toRealPath` giải symbolic links và các thành phần để xác định một **real path tại thời điểm gọi**. Nó rất hữu ích để phát hiện symlink đã tồn tại trỏ ngoài phạm vi. Nhưng khi một thao tác tiếp theo mở file **qua tên**, filesystem có thể thay đổi giữa hai thời điểm.

Tương tự, gọi `Files.exists` rồi `Files.newInputStream` không loại bỏ race. Bản chất rủi ro không nằm ở một method cụ thể mà ở **chuỗi check-then-use không atomic**.

### 11.2. Cách giảm thiểu theo mô hình đe dọa

- **Ưu tiên thư mục do ứng dụng quản lý:** người dùng bình thường không được phép sửa cấu trúc directory entries và symlinks của thư mục root/parent.
- **Dùng các operation mang tính atomic khi có:** ví dụ `CREATE_NEW` để ngăn file name tồn tại/overwrite tại thao tác create.
- **Dùng directory-handle-relative operations** khi bảo mật yêu cầu: Java NIO.2 cung cấp `SecureDirectoryStream` trên provider hỗ trợ.
- **Không mở lại path không kiểm soát:** khi đã có một file handle phù hợp, làm việc trên handle đã mở thay vì liên tục kiểm tra tên rồi mở lại mà không có kiểm soát.
- **Giới hạn quyền của process:** dù code sai, tài khoản chạy ứng dụng không nên có quyền đọc/ghi những khu vực hệ thống không thuộc trách nhiệm của nó.
- **Kiểm thử với attacker model thực tế:** một môi trường user có thể chỉ gửi request nhưng không sửa filesystem khác đáng kể với môi trường user có quyền tạo symlink trong vùng upload.

**Không có một câu lệnh `normalize().startsWith(...)` nào thay thế được tất cả các lớp bảo vệ trên.**

## 12. `SecureDirectoryStream`: dành cho truy cập nhạy cảm với race

`java.nio.file.SecureDirectoryStream` đã có từ Java 7, triển khai các thao tác tương đối với **thư mục đang mở** thay vì chỉ tên Path có thể thay đổi. Javadoc mô tả nó dành cho những ứng dụng cần duyệt/hoạt động trên directory theo cách giảm race condition.

Các thao tác tiêu biểu gồm mở stream của thư mục con, lấy channel, đọc attributes và xóa/move entries bằng tên tương đối với directory handle.

**Hai giới hạn phải biết:**

1. `SecureDirectoryStream` chỉ khả dụng nếu **file-system provider/OS hỗ trợ**. Khi gọi `Files.newDirectoryStream(dir)`, đối tượng trả về **không được bảo đảm** luôn implements `SecureDirectoryStream`.
2. Vẫn phải thiết kế **từng bước duyệt tên**, quy tắc symlink/no-follow và quyền truy cập. Nếu truyền một đường dẫn nhiều cấp chứa liên kết không kiểm soát mà không xét semantics, bạn không tự động có một sandbox an toàn.

Một snippet chỉ để phát hiện khả năng hỗ trợ:

```java
try (java.nio.file.DirectoryStream<Path> opened =
         java.nio.file.Files.newDirectoryStream(base)) {
    if (opened instanceof java.nio.file.SecureDirectoryStream) {
        // Có thể thiết kế thao tác directory-handle-relative.
    } else {
        // Không có capability: dùng phương án phù hợp hoặc từ chối.
    }
}
```

Đây là **snippet trong method có import Path, base tồn tại và handle IOException**, không phải một quy trình an toàn hoàn chỉnh. `SecureDirectoryStream` triển khai `AutoCloseable` qua `DirectoryStream` nên cần đóng bằng `try-with-resources`.

Khi nhà cung cấp không hỗ trợ, hãy chọn một trong các hành động **theo mô hình đe dọa**: kiểm soát quyền thư mục tốt hơn, dùng một khu vực staging cách ly, hoặc từ chối chức năng đòi hỏi bảo đảm race-free. Đừng tự báo “an toàn tương đương” chỉ vì đã thêm `Files.isSymbolicLink`.

## 13. `NOFOLLOW_LINKS`, symlink và hard links

Một số người nghĩ:

```java
boolean linked = Files.isSymbolicLink(path);
if (!linked) {
    // Chắc chắn an toàn?
}
```

Đây là **mẫu kiểm tra không đủ**. Có ít nhất hai vấn đề:

- Một symlink có thể nằm ở **thư mục cha**, không phải leaf `path`.
- Giữa bước kiểm tra và bước sử dụng, một entry có thể bị thay thế nếu tác nhân khác có quyền sửa filesystem.

`LinkOption.NOFOLLOW_LINKS` có ích khi làm việc với API cho phép lựa chọn follow link; tuy nhiên không nên suy rộng rằng nó có thể “khóa” toàn bộ path đã normalize. Cần xem tài liệu method cụ thể, hỗ trợ OS/provider và trạng thái quyền của thư mục.

**Hard link** cũng nhắc rằng quan hệ “đường dẫn nằm dưới base” không luôn đồng nghĩa “dữ liệu này có nguồn gốc và quyền sở hữu độc quyền của base”. Trên những filesystem hỗ trợ hard links, cùng nội dung/inode có thể có nhiều tên trong các vị trí khác nhau theo quyền hệ thống. Chính sách quyền dữ liệu cần xét thực tế nguồn tài nguyên, không chỉ hình dáng của tên.

**Quyền filesystem vẫn là lớp bảo vệ cuối quan trọng:** chương trình xử lý tài nguyên chỉ nên chạy với quyền cần thiết. Đừng cấp quyền truy cập toàn ổ đĩa rồi kỳ vọng một phép phân tích Path duy nhất thay thế quyền OS.

## 14. Khi dữ liệu đầu vào đến từ URL, HTTP upload hoặc ZIP entry

`Path.of(raw)` phân tích một **chuỗi path filesystem**, không tự biết các quy ước escaping của URL/HTTP hoặc định dạng archive.

Nếu input đến từ một URL:
- HTTP layer thường đã thực hiện một số xử lý/decoding theo hợp đồng.
- `%2e%2e` là một chuỗi dấu phần trăm và chữ số nếu đưa thẳng vào `Path.of`; nó **không tự biến thành `..`** trong Path.
- Nhưng nếu một tầng khác decode lại, cùng dữ liệu có thể thay đổi ý nghĩa. Phải xác định **chuỗi path cuối cùng được sử dụng thực sự** và validate ở đúng ranh giới, tránh việc kiểm tra một chuỗi nhưng mở tệp bằng một chuỗi khác.

Nếu input là tên ZIP entry hoặc tên file upload:
- Đừng tin rằng tên do client cung cấp đã nằm trong vùng được phép.
- Một entry có thể có tên chứa dấu phân cách, `..` hoặc đường dẫn absolute.
- Nếu chương trình trích xuất vào một root, cần kiểm tra từng entry theo cấu trúc Path, xử lý đúng định dạng archive và kiểm soát symlink/parent.
- Không tự động suy ra một URL path và một filesystem Path có cùng quy tắc dấu phân cách trên mọi nền tảng.

Điểm cốt lõi là **validate sau bước parsing/canonicalization phù hợp và trước khi thực hiện operation**, trên chính dạng dữ liệu mà operation sử dụng.

## 15. Giới hạn phạm vi: “đường dẫn hợp lệ” chưa chắc “được phép đọc/ghi”

Giả sử một tệp nằm bên trong `allowed/users/alice/private.txt`. Một request của Bob có thể vượt qua containment check vì vẫn dưới root. Điều đó **không có nghĩa Bob có quyền truy cập tài liệu của Alice**.

Containment chỉ trả lời một điều kiện về **vị trí theo path**, còn authorization có thể cần:
- Quyền theo user/tenant/session.
- ID tài liệu do server cấp, không phụ thuộc trực tiếp tên file do client chọn.
- Các quyền đọc, tạo, cập nhật, xóa riêng nhau.
- Metadata sở hữu file, nhãn phân loại, trạng thái lưu trữ.
- Quy tắc không truy cập nội dung nội bộ hoặc thư mục staging chỉ dành cho hệ thống.

Một cách giảm rủi ro là **không nhận raw filesystem path từ client** khi ứng dụng chỉ cần một document ID. Server có thể ánh xạ ID đã kiểm tra quyền sang đường dẫn do server kiểm soát. Nếu ứng dụng thật sự phải nhận subpath (ví dụ file manager), kiểm soát containment vẫn cần nhưng phải đi kèm authorization đầy đủ.

## 16. Thiết kế một API kiểm tra có hợp đồng rõ ràng

Trước khi viết hàm, trả lời những câu hỏi sau:

1. **Input là gì?** Một tên file đơn, relative path nhiều cấp, absolute path hay URI?
2. **Root lấy từ đâu?** Cấu hình tin cậy cố định, tenant-specific directory do server chọn, hay người dùng gửi?
3. **Tài nguyên đã tồn tại chưa?** Đọc/đổi tên file có sẵn khác với tạo upload mới.
4. **Cho phép symlink không?** Nếu có, chỉ cho phép link mà **đích thật** vẫn dưới base, hay cấm mọi link?
5. **Có cần cho phép đúng root không?** Một file API thường không; một API liệt kê thư mục có thể có.
6. **Có cho phép `..` được normalize nhưng vẫn trong base không?** Đó là chính sách đầu vào.
7. **Có tác nhân khác sửa filesystem đồng thời không?** Quyết định liệu lexical/real-path precheck là đủ hay cần handle-relative ops.
8. **Operation thực tế là gì?** `READ`, `CREATE_NEW`, `WRITE`, `DELETE` hay `LIST` có ràng buộc riêng.
9. **Lỗi được xử lý ra sao?** Malformed path, outside root, not found, permission denied và I/O error cần được phân biệt khi thích hợp.
10. **Có dữ liệu nhạy cảm trong đường dẫn không?** Không gửi full server path/stack trace trong error response công khai.

Mẫu tên API nên phản ánh **mức bảo đảm**. Ví dụ `checkLexicalRelativePath(...)` nói rõ chỉ kiểm tra cấu trúc; `findRealExistingPathUnder(...)` nói rõ đối tượng phải tồn tại; `createNewFileUnderManagedRoot(...)` nên triển khai policy tạo file rõ ràng, không chỉ trả về một `Path` “đã check”.

**Tránh những cái tên gây hiểu nhầm như `isSafePath(...)` khi hàm chỉ gọi `normalize().startsWith(...)`**; nó khiến người dùng API tưởng mọi vấn đề symlink/TOCTOU/authorization đã được giải quyết.

## 17. Bảng chọn phương pháp theo tình huống

| Tình huống | Kiểm tra nền tảng | Lớp bảo vệ bổ sung |
| --- | --- | --- |
| UI muốn hiển thị một relative path dưới root | `resolve`, `normalize`, `startsWith(Path)` | Validate tên và format hiển thị |
| App chỉ đọc file từ thư mục do chính nó kiểm soát, không ai khác sửa được | Lexical containment rồi open theo policy | File permissions, xử lý IOException |
| App đọc file đã tồn tại và có thể có symlinks | `toRealPath` của base/target rồi so sánh `startsWith(Path)` | Cấm/kiểm soát symlinks, TOCTOU mitigation |
| App tạo một file upload mới | Check relative/lexical + real parent đã tồn tại | `CREATE_NEW`, managed root, không cho ghi đè, tránh race ở parent |
| App cần duyệt/thao tác nhạy cảm với rename/symlink race | Directory-handle-relative API | `SecureDirectoryStream` nếu provider hỗ trợ, chính sách fallback |
| App nhận tên ZIP entry | Resolve vào root và kiểm tra từng entry | Kiểm tra archive semantics, link entries và loại thao tác |
| App xử lý nhiều user/tenant | Containment theo tenant root | Authorization per user/document, isolation/permissions |
| App nhận đường dẫn absolute từ người dùng | Thường từ chối nếu API chỉ cần relative | Nếu thật sự cho phép, xác định policy root và kiểm tra real path |
| App chỉ nhận tên file một cấp | Kiểm tra không absolute và chỉ một name element hợp lệ | Deny traversal/dot/empty, không tạo nested subdir |
| App cần tạo file khi parent chưa tồn tại | Quy trình tạo từng cấp theo policy | Không `createDirectories` trên untrusted path trước khi xác minh |

## 18. Các lỗi thường gặp và cách sửa

| Sai lầm | Tác hại | Cách sửa |
| --- | --- | --- |
| `candidate.toString().startsWith(base.toString())` | Nhận nhầm `safe-backup` là con của `safe` | `Path.startsWith(Path)` |
| Chỉ tìm chuỗi `"../"` trong input | Bỏ sót nhiều cách biểu diễn/path parsing | Dùng `Path`, normalize, policy rõ |
| Ghép `base + "/" + userInput` | Phụ thuộc OS/provider và không kiểm soát absolute path | `Path.resolve` + validate input |
| Không từ chối absolute input khi chỉ cho phép relative | Candidate có thể trỏ nơi khác | Check `isAbsolute()` trước resolve |
| So sánh relative Path với absolute base | Dễ sai ngữ cảnh | Dùng absolute/real paths tương thích |
| Không normalize trước so sánh lexical | `..` có thể thay đổi vị trí logic | `resolve(...).normalize()` |
| Coi lexical containment đủ chống symlink | Link trỏ ra ngoài được bỏ qua | Dùng `toRealPath` khi cần file thật |
| Dùng `toRealPath` cho file chưa tạo | Thường báo file không tồn tại | Xác minh parent hiện hữu, tạo theo policy |
| Coi `toRealPath` precheck là race-free | Path có thể thay sau check | Hạn chế quyền thay đổi directory/handle-relative ops |
| Nghĩ `NOFOLLOW_LINKS` tự xử lý mọi ancestor | Có thể vẫn follow symlinks ở parent | Kiểm soát từng thành phần và API semantics |
| `Files.exists` rồi mở mà không xử lý lỗi | TOCTOU và không chứng nhận containment | Mở theo policy và bắt IOException |
| `Files.newOutputStream(path)` mặc định cho upload mới | Có thể truncate file cũ | `CREATE_NEW` khi không cho phép overwrite |
| Cho rằng `CREATE_NEW` bảo vệ mọi thư mục cha | Chỉ atomic ở tên cuối trong thao tác create | Kiểm soát parent/permissions |
| Tin tên file client là tên server thật | Khách hàng có thể gửi traversal hoặc tên xung đột | Dùng ID do server cấp và kiểm tra quyền |
| Dùng `Path.of` mà code target Java 7 | `Path.of` chỉ có từ Java 11 | Java 7 dùng `Paths.get` |
| Log nguyên full path server ra response | Lộ cấu trúc máy và dữ liệu | Dùng error code phù hợp, log nội bộ tối thiểu |
| Đưa logic kiểm tra vào một helper tên “safe” rồi bỏ authorization | Vẫn truy cập nhầm dữ liệu user khác | Kiểm tra quyền ở tầng nghiệp vụ |

## 19. Kịch bản kiểm thử nên có

Một test suite path-containment cần có cả **đường được phép** và **đường phải bị từ chối**:

1. Relative path một tên, ví dụ `report.txt`.
2. Relative path nhiều cấp, ví dụ `reports/2026.txt`.
3. Path có `.` hoặc `a/../ok.txt` nhưng normalized target vẫn bên trong.
4. `../outside.txt` thoát một cấp.
5. `a/../../outside.txt` thoát nhiều cấp.
6. Absolute path đầu vào khi policy chỉ cho phép relative.
7. Candidate bằng chính base (`"."`) khi operation chỉ cho phép file con.
8. Sibling có tiền tố tên tương tự như `safe-backup` để bắt String prefix bug.
9. File đã tồn tại trong root: toRealPath và đọc thành công.
10. File thật đã tồn tại ngoài root: bị từ chối.
11. File không tồn tại: lỗi rõ, không báo “đã xác minh tồn tại”.
12. Symlink từ trong base trỏ ra ngoài: kiểm tra lexical và physical **khác nhau**.
13. Tạo file mới có parent thật trong base.
14. Tạo file mới với parent symlink trỏ ngoài base: từ chối nếu policy yêu cầu.
15. Tên file đã tồn tại: `CREATE_NEW` từ chối ghi đè.
16. File-system provider không hỗ trợ symlink hoặc secure directory operations: xử lý capability rõ ràng.
17. Đường dẫn từ URL/ZIP sau bước decode/parse: validate chính chuỗi cuối cùng dùng để mở.
18. Permission denied, file bị đổi hoặc bị xóa khi thao tác: kiểm soát lỗi I/O.
19. Nhiều user/tenant: một Path đúng dưới root nhưng user không có quyền vẫn phải bị từ chối.
20. Các thay đổi đồng thời đối với thư mục không đáng tin: thử nghiệm trên môi trường có quyền và công cụ kiểm tra race phù hợp.

### 19.1. Test không nên phụ thuộc tên thư mục tạm ngẫu nhiên

Các chương trình ở bài in **kết quả boolean, tên file đơn và trạng thái**. Chúng không hard-code một full path từ `Files.createTempDirectory`, vì đường dẫn này có suffix ngẫu nhiên và phụ thuộc hệ điều hành. Nhờ vậy stdout của phần lớn ví dụ ổn định hơn.

### 19.2. Test với symlink là một capability-dependent test

Nếu không thể tạo symlink trong môi trường hiện tại, đừng báo rằng test “đã PASS chống symlink”. Phải ghi rõ `SKIPPED` và thực hiện test trên môi trường có hỗ trợ khi rủi ro này nằm trong yêu cầu bảo mật. Đó là khác biệt giữa “chương trình chạy thành công” và “đã chứng minh một tính chất cụ thể”.

### 19.3. Kiểm thử quyền và thời gian sống

Bên cạnh test Path thuần túy, hãy tạo bài kiểm thử tích hợp trong thư mục do test sở hữu. Một test có thể kiểm tra việc cấp/thu hồi quyền, nhưng không nên âm thầm thay đổi quyền của thư mục thật trong máy người dùng. Bài tập quan trọng hơn là xác nhận **mọi trường hợp reject xảy ra trước thao tác đọc/ghi ngoài vùng**.

## 20. Bài tập thực hành có đáp án

**Câu 1.** Vì sao `String.startsWith` không đủ để kiểm tra directory containment?  
**Đáp án:** Nó so ký tự, không có ranh giới name element. `safe-backup` có tiền tố `safe` nhưng là thư mục khác. Dùng `Path.startsWith(Path)`.

**Câu 2.** Sau `base.resolve(Path.of("..","secret.txt")).normalize()`, candidate có luôn ở trong base không?  
**Đáp án:** Không. Normalize có thể đưa nó lên thư mục cha bên ngoài base; cần kiểm tra `startsWith(base)` sau đó.

**Câu 3.** Nếu API chỉ cho phép relative path, bước nào cần làm trước `resolve`?  
**Đáp án:** Từ chối `supplied.isAbsolute()`, sau đó mới ghép vào base và normalize theo policy.

**Câu 4.** `candidate.startsWith(base)` true khi `candidate.equals(base)` đúng hay sai?  
**Đáp án:** Đúng. Nếu API chỉ cho phép file **bên trong**, cần tự từ chối candidate bằng base.

**Câu 5.** `normalize()` có mở file hay kiểm tra symlink không?  
**Đáp án:** Không. Nó là phép rút gọn lexical, không truy vấn filesystem.

**Câu 6.** Vì sao cần `toRealPath()` khi có symlink?  
**Đáp án:** Để xem đường dẫn thực của file/directory đã tồn tại sau khi giải symbolic links theo policy, từ đó phát hiện link trỏ ngoài base.

**Câu 7.** `toRealPath()` có dùng được trực tiếp cho một file mới chưa tạo không?  
**Đáp án:** Thường không; file chưa tồn tại gây lỗi. Kiểm tra parent thật đã tồn tại và tạo file bằng operation thích hợp.

**Câu 8.** Vì sao check real path rồi open theo tên vẫn có rủi ro?  
**Đáp án:** Đường dẫn/symlink có thể bị thay giữa kiểm tra và open nếu tác nhân khác có quyền sửa; đó là TOCTOU.

**Câu 9.** `CREATE_NEW` bảo đảm điều gì?  
**Đáp án:** Từ chối tạo tại tên cuối nếu đối tượng đó đã tồn tại, với bước kiểm tra tên và tạo mới atomic theo hợp đồng. Nó **không** tự cố định toàn bộ các thư mục cha.

**Câu 10.** Có thể dựa hoàn toàn vào `Files.exists` để xác nhận file an toàn không?  
**Đáp án:** Không. Nó không kiểm tra containment/authorization và không loại bỏ race.

**Câu 11.** Nếu tạo symlink bị từ chối trong test, có nên ghi “symlink-safe PASS” không?  
**Đáp án:** Không. Ghi `SKIPPED` và kiểm thử trên môi trường hỗ trợ khi cần chứng minh.

**Câu 12.** `SecureDirectoryStream` có luôn sẵn trong mọi JDK/OS không?  
**Đáp án:** Không. Nó là API Java, nhưng capability phụ thuộc file-system provider/OS; phải kiểm tra trước khi dùng.

**Câu 13.** Nếu một Path nằm dưới base nhưng thuộc dữ liệu người dùng khác, có nên cho đọc không?  
**Đáp án:** Không chỉ dựa vào containment. Cần kiểm tra authorization theo user/tenant/tài liệu.

**Câu 14.** Tại sao không gửi nguyên full real path cho client khi bị từ chối?  
**Đáp án:** Có thể lộ cấu trúc máy hoặc vị trí dữ liệu nhạy cảm. Trả thông báo/error code phù hợp; log thông tin chi tiết có kiểm soát.

**Câu 15.** Trong Java 7, có `Path.of(...)` chưa?  
**Đáp án:** Chưa. Dùng `java.nio.file.Paths.get(...)`. `Path.of(...)` từ Java 11, còn các API path containment cốt lõi vẫn áp dụng.

**Câu 16.** Chỉ từ chối chuỗi chứa `".."` có đủ không?  
**Đáp án:** Không. Phải xác định parsing/decoding thực tế, absolute path, symlinks, quyền filesystem và race conditions.

### Thực hành A — Kiểm tra lexical

Chạy `LexicalContainmentDemo`; thêm `Path.of("reports","..","images","icon.png")` và xem nó có được chấp nhận theo policy của demo không. Thử đổi điều kiện để cấm **mọi** thành phần `..` và giải thích sự khác biệt giữa policy và quy tắc Java.

### Thực hành B — Prefix trap

Chạy `PrefixBoundaryDemo`; đổi `safe-backup` thành `safe-logs` và kiểm tra tại sao `String.startsWith` vẫn sai nhưng `Path.startsWith` trả false.

### Thực hành C — File thực

Chạy `ExistingFileContainmentDemo`, thêm một file ở thư mục con thứ hai của root và một file ở thư mục sibling. Đảm bảo hàm chỉ chấp nhận đúng file trong root.

### Thực hành D — Symlink

Chạy `SymlinkEscapeDemo` trên một môi trường hỗ trợ symbolic links, kiểm tra `lexicalInside=true`/`realInside=false`. Nếu test bị skip, ghi rõ hạn chế môi trường thay vì đoán.

### Thực hành E — Create new

Chạy `NewFileContainmentDemo`, kiểm tra `CREATE_NEW` ngăn ghi đè. Sau đó thử dùng một parent không tồn tại: phải nhận lỗi từ việc lấy real path parent, không tạo cả cây ngoài vùng.

### Thực hành F — Chính sách cho phép root

Sửa `checked(...)` để cho phép candidate bằng base trong API liệt kê thư mục, nhưng vẫn cấm trong API đọc một file con. Viết hai test để thể hiện sự khác biệt của **hợp đồng nghiệp vụ**.

### Thực hành G — Quyền truy cập

Tạo hai tenant directories riêng; viết phương thức chỉ nhận document ID và ánh xạ ID sang relative file name do server chọn. Thử yêu cầu tài liệu khác tenant và bảo đảm **authorization** được kiểm tra, kể cả khi Path vẫn nằm dưới root chung.

### Thực hành H — Threat model

Viết ngắn một bảng gồm “người gửi request có quyền tạo symlink?”, “có quyền đổi parent folder?”, “có thể tạo file cùng tên?”, “ứng dụng chạy với quyền OS nào?”; từ đó xác định khi nào lexical check chỉ là bộ lọc đầu vào và khi nào cần thao tác directory-handle-relative.

## 21. Tài liệu chính thức

- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `normalize`, `startsWith`, `toAbsolutePath` và `toRealPath`.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `newInputStream`, `newOutputStream`, `newByteChannel`, kiểm tra/cấp phát tài nguyên filesystem.
- [Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW` và các điều kiện mở file.
- [Java SE 17 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác relative-to-directory handle cho ứng dụng nhạy cảm với race.
- [Java SE 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): lựa chọn `NOFOLLOW_LINKS` ở API tương thích.
- [Java SE 17 — FileSystem](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): các quy tắc đường dẫn theo provider.
- [Java SE 17 — Paths](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Paths.html): tạo `Path` kiểu Java 7.
- [Java SE 17 — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): mô hình báo lỗi khi đối tượng filesystem không hiện hữu hoặc không thể truy cập.

**Tóm tắt cốt lõi:** Kiểm tra đường dẫn trong thư mục được phép phải dùng **`Path` theo ranh giới name elements**, không dùng tiền tố `String`. Với đầu vào tương đối, thực hiện `resolve` + `normalize` + `startsWith(Path)` để kiểm tra **lexical containment**. Với file có thật và symlinks, `toRealPath()` bổ sung kiểm tra **real containment**. Khi mở/tạo/xóa file thật, phải xét **quyền filesystem, symlink, TOCTOU, các option atomic như `CREATE_NEW` và authorization theo người dùng**. Một phép kiểm tra đúng ở tầng đường dẫn là cần thiết, nhưng chỉ trở thành hệ thống an toàn khi gắn với đúng mô hình đe dọa và thao tác I/O.
