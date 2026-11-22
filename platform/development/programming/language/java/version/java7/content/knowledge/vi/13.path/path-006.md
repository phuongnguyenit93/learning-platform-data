# `Path` trong Java: Tạo đường dẫn tương đối bằng `relativize`

## 1. Mục tiêu: tạo đường dẫn từ một vị trí gốc đến một vị trí đích

Trong ứng dụng Java, không phải lúc nào ta cũng muốn lưu hoặc hiển thị **đường dẫn tuyệt đối**. Khi tạo liên kết giữa các tệp trong cùng một dự án, đóng gói nội dung, hiển thị vị trí tài nguyên hoặc di chuyển thư mục, ta thường cần biết:

> **Đang đứng tại đường dẫn `base`, cần đi tương đối như thế nào để tới `target`?**

`java.nio.file.Path` cung cấp phương thức:

```java
Path relative = base.relativize(target);
```

Kết quả `relative` là một **`Path` tương đối**, có thể kết hợp với `base` qua `resolve`. Ví dụ trên một cây thư mục:

```text
workspace/
├── docs/
└── assets/
    └── images/
        └── logo.png

base:    workspace/docs
target:  workspace/assets/images/logo.png
relative từ base đến target: ../assets/images/logo.png
```

Cú pháp Java 17+:

```java
import java.nio.file.Path;

Path base = Path.of("workspace", "docs");
Path target = Path.of("workspace", "assets", "images", "logo.png");

Path relative = base.relativize(target);
System.out.println(relative);
```

Trên Linux/macOS, ví dụ in `../assets/images/logo.png`. Trên Windows, dấu phân cách có thể là dấu gạch chéo ngược: `..\assets\images\logo.png`. **Ý nghĩa các thành phần giống nhau**, còn cách hiển thị phụ thuộc provider/hệ điều hành.

**Điểm cốt lõi:** Gọi **`base.relativize(target)`**, không gọi ngược. Phương thức có từ Java 7 và vẫn là API chuẩn trong Java hiện đại. `Path.of(...)` là factory được hỗ trợ từ Java 11; bài này chọn Java 17+ cho ví dụ chạy độc lập.

## 2. Hiểu đúng công thức `base.relativize(target)`

### 2.1. `relativize` là thao tác ngược ý nghĩa với `resolve`

Hai phương thức cần đi thành cặp:

- `base.relativize(target)`: tìm một đường tương đối mô tả cách đi **từ base đến target**.
- `base.resolve(relative)`: ghép đường tương đối trở lại base để tạo một đường dẫn đến đích.

Với các đường dẫn phù hợp, đã chuẩn hóa và cùng hệ thống tệp:

```java
Path base = Path.of("workspace", "docs");
Path target = Path.of("workspace", "assets", "images", "logo.png");

Path relative = base.relativize(target);
Path reconstructed = base.resolve(relative).normalize();

boolean same = reconstructed.equals(target.normalize());
System.out.println(same); // true
```

Đây là **đoạn minh họa bên trong một phương thức**, có `import java.nio.file.Path;`.

**Đọc `resolve` cho đúng:** `base.resolve(relative)` xem `base` là **đường dẫn thư mục để ghép thêm** một đường dẫn con hoặc đường tương đối. Nếu `base` thực ra trỏ đến **một tệp**, cần xác định rằng điểm xuất phát hợp lý thường là **thư mục chứa tệp**, tức `base.getParent()`, chứ không phải chính path đến tệp ấy.

### 2.2. Tại sao kết quả có `..`?

Mỗi thành phần `..` là một bước đi lên **một cấp** trong cấu trúc tên đường dẫn:

```text
base = workspace/docs
             └── đi lên 1 cấp → workspace

target = workspace/assets/images/logo.png
                  └── từ workspace đi xuống assets/images/logo.png

kết quả = ../assets/images/logo.png
```

`..` không mặc định là dấu hiệu nguy hiểm, lỗi hay sai cú pháp. Nó là một thành phần đường dẫn tương đối hợp lệ, đặc biệt khi hai tài nguyên là **anh em** trong cây thư mục. Tuy nhiên, khi đường dẫn đến từ người dùng không tin cậy, `..` cần được xử lý theo chính sách bảo mật vì nó có thể cho phép truy cập ra ngoài thư mục dự kiến.

### 2.3. `relativize` trả về `Path`, không phải chuỗi URL

`Path` biểu diễn tên đường dẫn trong **một file system/provider**. Nó không phải `URI`, không phải URL HTTP và không tự thêm chuẩn phân tách `/` cho mọi hệ điều hành.

```java
Path relative = base.relativize(target);
String display = relative.toString();
```

Nếu cần gửi đường dẫn qua giao thức ngoài hoặc lưu trong định dạng dùng quy tắc riêng, hãy xác định hợp đồng serialization tương ứng. **Đừng ép mọi `Path` thành chuỗi bằng `replace("\\", "/")` rồi coi đó là chuyển đổi phổ quát đúng cho mọi filesystem**. Trong chương trình thử ở cuối bài chỉ dùng phép thay dấu phân cách để **chuẩn hóa đầu ra hiển thị** của ví dụ học tập, không dùng để thực hiện truy cập file.

## 3. Những trường hợp cơ bản phải nắm

### 3.1. Đích nằm ngay bên dưới thư mục gốc

```java
Path base = Path.of("project", "docs");
Path target = Path.of("project", "docs", "java", "guide.md");

Path relative = base.relativize(target);
// java/guide.md  (theo cách hiển thị kiểu Unix)
```

Hai đường dẫn có prefix chung `project/docs`. Phần còn lại sau prefix là `java/guide.md`, **không cần `..`**.

### 3.2. Đích là tệp/thư mục ở nhánh anh em

```java
Path base = Path.of("project", "docs");
Path target = Path.of("project", "images", "logo.svg");

Path relative = base.relativize(target);
// ../images/logo.svg
```

Đi lên từ `docs` đến `project`, rồi đi xuống `images/logo.svg`.

### 3.3. Đích là thư mục cha

```java
Path base = Path.of("project", "docs", "java");
Path parent = Path.of("project");

Path relative = base.relativize(parent);
// ../..
```

Đi lên hai cấp từ `project/docs/java` để về `project`.

### 3.4. Hai đường dẫn bằng nhau

```java
Path base = Path.of("project", "docs");
Path same = base.relativize(base);

System.out.println(same.toString().isEmpty()); // true
```

Theo API Java, hai `Path` bằng nhau cho kết quả là **empty path**, không phải chuỗi `"."` được thêm sẵn.

Khi hiển thị cho người dùng, bạn **có thể tùy chọn** hiển thị `"."` thay cho chuỗi rỗng để nói “vị trí hiện tại”. Nhưng phải phân biệt **cách hiển thị do ứng dụng chọn** với giá trị trả về thật từ `relativize`.

### 3.5. Đích nằm ở nhiều nhánh khác nhau

```java
Path base = Path.of("root", "a", "b");
Path target = Path.of("root", "c", "d", "file.txt");

// Kết quả có ý nghĩa: ../../c/d/file.txt
```

Hãy tìm **phần chung theo các thành phần tên**, không theo tiền tố ký tự. `root/a` và `root/archive` là các thư mục khác nhau, dù chuỗi `"root/a"` là tiền tố của `"root/archive"`.

**Bảng suy luận nhanh** (dấu phân cách `/` chỉ dùng để minh họa):

| `base` | `target` | `base.relativize(target)` |
| --- | --- | --- |
| `a/b` | `a/b/c.txt` | `c.txt` |
| `a/b` | `a/c.txt` | `../c.txt` |
| `a/b/c` | `a` | `../..` |
| `a/b` | `a/b` | empty path |
| `a/b` | `a/b/c/d` | `c/d` |
| `a/b` | `a/d/e` | `../d/e` |

Các ví dụ giả sử hai path có cùng provider và cùng kiểu tương đối, không chứa thành phần `..` chưa được chuẩn hóa.

## 4. Điểm xuất phát phải phù hợp: thư mục hay đường dẫn tệp?

Một trong những lỗi khó nhận ra nhất là gọi `relativize` từ **đường dẫn đến một tệp**, rồi sử dụng kết quả như thể “tương đối với thư mục chứa tệp”.

Giả sử:

```text
workspace/
├── docs/
│   └── guide.md
└── assets/
    └── logo.svg
```

Ta muốn tạo đường dẫn từ **vị trí của `guide.md`** tới `logo.svg` để nhúng vào Markdown. Thông thường liên kết trong tài liệu được giải thích theo **thư mục chứa `guide.md`**, không xem `guide.md` là một thư mục.

**Cách đúng:**

```java
Path document = Path.of("workspace", "docs", "guide.md");
Path image = Path.of("workspace", "assets", "logo.svg");

Path relativeLink = document.getParent().relativize(image);
// ../assets/logo.svg
```

Nếu viết:

```java
Path wrongBase = document.relativize(image);
// ../../assets/logo.svg
```

thì phép tính vẫn là một **phép biến đổi path hợp lệ** ở mức tên, nhưng nó tính từ `workspace/docs/guide.md` như thể path đó là một **vị trí có thể làm base để đi xuống**. Kết quả không phù hợp để dùng như liên kết tương đối từ nội dung `guide.md`.

**Quy tắc:** Nếu một API yêu cầu đường dẫn “relative to the directory containing a file”, hãy dùng `file.getParent()`. Nếu path tệp chỉ có một tên, chẳng hạn `Path.of("guide.md")`, `getParent()` có thể trả `null`. Khi đó cần chủ động xác định thư mục làm việc/gốc dự án hoặc dùng `toAbsolutePath().getParent()` theo yêu cầu ứng dụng; không gọi `relativize` trên `null`.

`Path.resolveSibling(...)` cũng hữu ích khi muốn thay tên tệp ở cùng thư mục:

```java
Path renamed = document.resolveSibling("new-guide.md");
// workspace/docs/new-guide.md
```

Nhưng **`resolveSibling` không thay thế `relativize`** khi muốn tính đường tương đối đến một tài nguyên ở nhánh khác.

## 5. `normalize()` trước khi tính đường tương đối

### 5.1. Vì sao `.` và `..` trong đầu vào dễ gây bất ngờ?

`Path.normalize()` tạo một `Path` mới bằng cách bỏ những thành phần tên dư thừa theo ngữ nghĩa từ vựng (*lexical*). Ví dụ:

```java
Path raw = Path.of("workspace", "docs", ".", "..",
                   "assets", "logo.svg");

Path normalized = raw.normalize();
// workspace/assets/logo.svg
```

Chúng ta muốn tính đường đi từ `workspace/docs` đến đích `workspace/assets/logo.svg`. Với path đầu vào đã chuẩn hóa:

```java
Path base = Path.of("workspace", "docs").normalize();
Path target = raw.normalize();

Path relative = base.relativize(target);
// ../assets/logo.svg
```

Việc chuẩn hóa giúp kết quả dễ đọc và phép kiểm tra round-trip dễ hiểu. Đặc biệt khi input được ghép từ nhiều bước `resolve`, nên loại bỏ các thành phần `.`, `folder/..` không cần thiết **nếu việc chuẩn hóa từ vựng phù hợp với ngữ nghĩa ứng dụng**.

### 5.2. `normalize()` không truy cập hệ thống tệp

`normalize()` không cần một file hay thư mục thật tồn tại. Nó xử lý **cấu trúc tên đường dẫn**.

**Nhưng có cảnh báo quan trọng về symlink:** Nếu thành phần `folder` thực tế là symbolic link, việc rút gọn `folder/..` bằng xử lý từ vựng **có thể thay đổi file thực tế được trỏ tới** so với việc lần lượt đi qua symlink ở runtime. Java API nêu rõ trường hợp này.

Vì vậy:

- Với path dùng để tính liên kết nội bộ theo cấu trúc tên và không cần xét symlink, `normalize` thường hợp lý.
- Với path đại diện **tài nguyên thật có symlink**, không được khẳng định `normalize` có nghĩa “đã giải quyết symlink”.
- Với nhu cầu **đường dẫn vật lý thực** của một tệp/thư mục tồn tại, dùng `toRealPath(...)` theo hợp đồng và xử lý `IOException`. Phương thức đó có thể kiểm tra sự tồn tại và giải quyết liên kết theo tùy chọn; khác bản chất với `normalize`.

### 5.3. Chuẩn hóa không tự quyết định đường dẫn nào đáng tin

`normalize()` có thể loại bỏ `..`, nhưng **không bảo đảm** path sau chuẩn hóa ở trong thư mục mà chương trình cho phép.

```java
Path root = Path.of("workspace").toAbsolutePath().normalize();
Path outside = root.resolve(Path.of("..", "secret.txt")).normalize();

System.out.println(outside.startsWith(root)); // false trong ví dụ
```

Đây là kiểm tra **lexical containment** đơn giản, không phải cơ chế sandbox hoàn chỉnh. Symlink, race condition và quyền truy cập cần được giải quyết riêng (xem mục 11).

## 6. Hai `Path` phải tương thích về absolute/relative và filesystem

### 6.1. Trộn một path tương đối với một path tuyệt đối

Đây là lỗi thường gặp:

```java
Path base = Path.of("workspace", "docs");          // relative
Path target = Path.of("workspace", "assets");       // relative
Path absoluteTarget = target.toAbsolutePath();     // absolute

// base.relativize(absoluteTarget); // IllegalArgumentException
```

Theo Java API, **không thể tạo relative path nếu một bên có root còn bên kia không có root**. Với default filesystem, phép trộn relative/absolute như trên làm `relativize` ném `IllegalArgumentException`.

**Cách xử lý:** lựa chọn nhất quán một trong hai phương án:

```java
// Cách A: cả hai đều relative
Path linkA = base.normalize().relativize(target.normalize());

// Cách B: cả hai đều absolute
Path linkB = base.toAbsolutePath().normalize()
        .relativize(target.toAbsolutePath().normalize());
```

Với dữ liệu lấy từ những tầng khác nhau, không tự động `toAbsolutePath()` một bên rồi quên bên kia. Hai đường dẫn tương đối được chuyển sang tuyệt đối sẽ dùng thư mục làm việc của process theo quy tắc provider; đó phải là **cùng điểm gốc hợp lý** cho ứng dụng.

### 6.2. Cùng absolute không luôn có nghĩa có thể relativize

Hai đường dẫn tuyệt đối có thể nằm ở **hai root không tương thích**. Ví dụ trên Windows, một path thuộc ổ `C:\` và path khác thuộc ổ `D:\` thường **không thể** tìm relative path dùng `..` từ ổ này sang ổ kia. UNC shares và các filesystem providers khác cũng có quy tắc riêng.

Trong Java, khả năng relativize giữa hai absolute paths có root được tài liệu quy định là **phụ thuộc implementation**; do đó không viết thuật toán “cứ hai absolute path thì chắc chắn relativize được”.

```java
static Path tryRelative(Path base, Path target) {
    try {
        return base.relativize(target);
    } catch (IllegalArgumentException ex) {
        // Chính sách thực tế có thể trả về thông báo lỗi,
        // trả target tuyệt đối hoặc dùng URI tùy hợp đồng.
        throw new IllegalArgumentException(
                "Paths are not relativizable in this filesystem", ex);
    }
}
```

Đây là **phương thức minh họa** trong lớp có import `java.nio.file.Path`. Nếu định dạng đích **bắt buộc** là relative path, cần thông báo lỗi hoặc đổi nơi đặt file, chứ không đơn giản lưu đường dẫn tuyệt đối thay thế.

### 6.3. Không trộn `Path` của các filesystem providers

`Path` có thể đến từ filesystem mặc định, file system ZIP/JAR, hoặc custom provider. Hai đối tượng có cùng tên thư mục dạng text chưa chắc cùng **filesystem**.

Ví dụ ứng dụng có thể mở một ZIP filesystem:

```java
// Path thuộc ZIP filesystem không nhất thiết tương thích
// với Path.of(...) thuộc default filesystem.
```

Trước khi relativize những path từ nhiều nguồn, cần chắc chắn chúng thuộc cùng filesystem/provider và phép tính được phép. Không thay `Path` bằng string nối tay để lách sự không tương thích: khi đó bạn chỉ tạo ra **chuỗi**, không chứng minh được nó chỉ đúng đến một file trong filesystem đích.

### 6.4. `Path.of(...)` và cách ghi dấu phân cách

`Path.of("workspace", "docs", "guide.md")` để provider tạo đường dẫn theo dấu phân cách hệ thống. Cách này dễ đọc và tránh phải tự gõ `/` hoặc `\`.

`Path.of(...)` có từ Java 11, nhưng **`Path.relativize(...)` đã có từ Java 7** và vẫn được hỗ trợ. Trong code Java 17+, dùng `Path.of` là cách trình bày hiện đại, không phải chuyển ngược sang API đã lỗi thời.

## 7. Đường dẫn tương đối không kiểm tra file tồn tại

`Path.relativize` là **phép tính tên đường dẫn**. Nó không:

- Mở tệp.
- Kiểm tra thư mục/tệp có tồn tại.
- Kiểm tra quyền đọc/ghi.
- Kiểm tra xem một thành phần có phải symbolic link hay không.
- Thực hiện copy hoặc di chuyển file.
- Tự phát hiện root được phép của ứng dụng.

```java
Path base = Path.of("__folder_not_created_123__");
Path target = base.resolve("missing.txt");

Path relative = base.relativize(target);
System.out.println(relative); // missing.txt
```

Đoạn code hợp lệ **ngay cả khi thư mục và tệp không tồn tại**. Do đó không dùng `relativize` như một phương thức kiểm tra file.

Muốn làm việc với file thật, `java.nio.file.Files` có các thao tác như `Files.exists`, `Files.readString`, `Files.copy`, `Files.move`, v.v. Hãy dùng chúng theo từng yêu cầu, cân nhắc race condition khi kiểm tra tồn tại rồi thao tác ở bước sau.

### 7.1. Kết quả có `..` không phải thao tác filesystem

`base.relativize(target)` có thể trả `../images/pic.png`. Nó **chỉ trả một đối tượng `Path`**; không di chuyển, không xóa, không đọc bất kỳ tệp nào. Những tác động lên dữ liệu chỉ xuất hiện khi caller thực sự đem path này đi dùng trong các API I/O hoặc truyền sang hệ thống khác.

Đây là lý do `relativize` thích hợp để tạo **đường dẫn liên kết** hoặc một phần metadata mà không cần đọc toàn bộ cây tệp.

## 8. Chương trình Java 17+ đầy đủ, kết quả không lệ thuộc dấu phân cách OS

Chương trình bên dưới kiểm tra:

1. Đường tương đối từ `workspace/docs` tới `workspace/assets/images/logo.png`.
2. Lời gọi `resolve + normalize` khôi phục đúng đường dẫn đích.
3. Đường đến tệp con, đường trùng nhau và đường chứa `.`/`..`.
4. Sự khác nhau giữa tính từ **thư mục chứa file** và tính từ **path tới file**.
5. Dạng tuyệt đối/tuyệt đối phù hợp, và lỗi khi trộn absolute với relative.
6. Kiểm tra lexical `startsWith(root)` và việc `relativize` không cần file tồn tại.
7. Những assertion khiến chương trình thất bại nếu kết quả quan trọng không đúng.

Tệp **`PathRelativizeDemo.java`**:

```java
import java.nio.file.Path;

public final class PathRelativizeDemo {

    // Chỉ phục vụ in kết quả portable; KHÔNG dùng để thao tác file.
    static String portable(Path path) {
        return path.toString().replace('\\', '/');
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Path base = Path.of("workspace", "docs");
        Path target = Path.of(
                "workspace", "assets", "images", "logo.png");

        Path relative = base.relativize(target);

        System.out.println("base=" + portable(base));
        System.out.println("target=" + portable(target));
        System.out.println("relative=" + portable(relative));
        System.out.println("resolved="
                + portable(base.resolve(relative).normalize()));
        System.out.println("roundTrip="
                + base.resolve(relative).normalize()
                    .equals(target.normalize()));

        System.out.println("nested=" + portable(
                base.relativize(Path.of(
                        "workspace", "docs", "java", "guide.md"))));

        System.out.println("sameEmpty="
                + base.relativize(base).toString().isEmpty());

        Path raw = Path.of("workspace", "docs", ".", "..",
                "assets", "logo.svg");
        System.out.println("normalizedTarget="
                + portable(raw.normalize()));
        System.out.println("normalizedRelative="
                + portable(base.normalize().relativize(raw.normalize())));

        Path file = Path.of("workspace", "docs", "guide.md");
        Path image = Path.of("workspace", "assets", "logo.svg");

        System.out.println("fromFileParent=" + portable(
                file.getParent().relativize(image)));
        System.out.println("fileAsBase=" + portable(
                file.relativize(image)));

        Path absoluteBase = base.toAbsolutePath().normalize();
        Path absoluteTarget = target.toAbsolutePath().normalize();

        System.out.println("absoluteRelative="
                + portable(absoluteBase.relativize(absoluteTarget)));

        boolean rejected = false;

        try {
            base.relativize(target.toAbsolutePath());
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("mixedKindsRejected=" + rejected);

        Path sandbox = Path.of("workspace")
                .toAbsolutePath().normalize();
        Path inside = sandbox.resolve(
                Path.of("assets", "logo.svg")).normalize();
        Path outside = sandbox.resolve(
                Path.of("..", "secret.txt")).normalize();

        System.out.println("insideRoot="
                + inside.startsWith(sandbox));
        System.out.println("outsideRoot="
                + outside.startsWith(sandbox));

        System.out.println("noExistenceCheck=" + portable(
                Path.of("__no_such_root_123__").relativize(
                    Path.of("__no_such_root_123__", "x.txt"))));

        check(portable(relative).equals(
                "../assets/images/logo.png"), "relative");
        check(base.resolve(relative).normalize()
                .equals(target.normalize()), "round trip");
        check(rejected && !outside.startsWith(sandbox), "guards");

        System.out.println("checks=PASS");
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 PathRelativizeDemo.java
java PathRelativizeDemo
```

**Stdout chính xác của chương trình:**

```text
base=workspace/docs
target=workspace/assets/images/logo.png
relative=../assets/images/logo.png
resolved=workspace/assets/images/logo.png
roundTrip=true
nested=java/guide.md
sameEmpty=true
normalizedTarget=workspace/assets/logo.svg
normalizedRelative=../assets/logo.svg
fromFileParent=../assets/logo.svg
fileAsBase=../../assets/logo.svg
absoluteRelative=../assets/images/logo.png
mixedKindsRejected=true
insideRoot=true
outsideRoot=false
noExistenceCheck=x.txt
checks=PASS
```

### 8.1. Giải thích đầu ra quan trọng

- `relative=../assets/images/logo.png`: đi lên một cấp rồi xuống nhánh `assets/images`.
- `resolved=workspace/assets/images/logo.png` và `roundTrip=true`: tổ hợp `resolve/normalize` khôi phục đúng tên đường dẫn đích trong ví dụ.
- `nested=java/guide.md`: đích nằm trực tiếp dưới base nên không có `..`.
- `sameEmpty=true`: hai path bằng nhau cho empty path.
- `normalizedTarget` và `normalizedRelative`: loại bỏ `.` và cặp `docs/..` trước khi tạo kết quả.
- `fromFileParent=../assets/logo.svg`: link tính từ thư mục chứa file; `fileAsBase=../../assets/logo.svg` thể hiện vì sao dùng chính path tới file làm base có thể cho kết quả không mong muốn.
- `absoluteRelative=../assets/images/logo.png`: khi cả hai path được chuyển sang absolute cùng root, các thành phần tương đối vẫn giống trường hợp này.
- `mixedKindsRejected=true`: Java từ chối một relative path và một absolute path không tương thích.
- `insideRoot=true`, `outsideRoot=false`: kiểm tra containment **lexical** bằng `Path.startsWith`; đây không phải bảo đảm an toàn trước symlink.
- `noExistenceCheck=x.txt`: relativize dựa trên path expressions, không yêu cầu tệp thật.
- `checks=PASS`: các assertion chính đều thành công.

Lớp `portable` chỉ phục vụ **in demo dễ đọc** trên cả Windows và Unix. Trong code ứng dụng, hãy giữ nguyên đối tượng `Path` khi gọi `Files`, `resolve`, `relativize` và các API khác; tránh chuyển qua string nếu không có lý do hoặc hợp đồng rõ ràng.

## 9. Phân biệt `relativize`, `resolve`, `normalize` và `toRealPath`

| API | Câu hỏi mà API giải quyết | Có truy cập filesystem? |
| --- | --- | --- |
| `base.relativize(target)` | Từ base cần đi đường tương đối nào đến target? | Không cần |
| `base.resolve(child)` | Ghép một đường dẫn khác vào base ra sao? | Không cần |
| `path.normalize()` | Loại các thành phần `.`/`..` dư theo cấu trúc tên ra sao? | Không |
| `path.toAbsolutePath()` | Biểu diễn path thành dạng tuyệt đối theo provider/môi trường? | Không phải thao tác xác thực file; quy trình xác định có thể phụ thuộc môi trường |
| `path.toRealPath()` | Tên đường dẫn thật của file/thư mục đã tồn tại là gì? | **Có**, có thể ném `IOException` |
| `Files.isSameFile(a,b)` | Hai path trỏ tới cùng một file thật không? | Có thể truy cập filesystem, có thể ném `IOException` |

Sự khác nhau này quyết định **khi nào nên dùng API nào**.

### 9.1. `relativize` không đảm bảo hai path trỏ tới cùng một file thực

Một `Path` có thể chỉ chứa tên, chưa có đối tượng vật lý. Kể cả khi hai path đều đang tồn tại, symlink có thể khiến một path có `..` sau `resolve` dẫn tới nơi khác dự kiến. Tài liệu `Path.relativize` **nêu rõ khả năng ánh xạ tới cùng file khi có symlink phụ thuộc implementation**.

Nếu nghiệp vụ yêu cầu xác nhận **cùng file thật**, nên xem `Files.isSameFile` hoặc `toRealPath` phù hợp theo điều kiện tồn tại và quyền truy cập. Đừng suy ra tương đương vật lý chỉ từ việc chuỗi `Path` sau `normalize` nhìn giống nhau.

### 9.2. `normalize` không tự nhận diện symbolic link

Ví dụ trên một filesystem có symlink:

```text
real/
  photos/
  reports/

alias -> real/photos  (symlink, minh họa)
```

Một đường dẫn chứa `alias/..` có thể có ý nghĩa khác với phép loại bỏ từ vựng `alias/..`, tùy cách hệ điều hành/provider duyệt symlink. Vì vậy, **kết quả lexical ngắn hơn không đồng nghĩa đã xác minh đường đi vật lý**.

Nếu tồn tại symlink, hãy xác định rõ yêu cầu: tạo một **đường liên kết tương đối theo tên** hay tìm **đường từ tài nguyên thực này đến tài nguyên thực khác**.

### 9.3. Đường dẫn đến file và URI dùng cho web khác nhau

`Path.relativize` là API của `java.nio.file.Path`, không đồng nghĩa `java.net.URI.relativize`. URI có cú pháp scheme, authority và escape riêng. Với link HTML/Markdown muốn có `/`, thành phần URL cần được mã hóa đúng theo URI/URL contract, không nên coi `Path.toString()` là một URL di động qua hệ điều hành.

## 10. Ứng dụng thực tế: lưu đường dẫn liên kết trong dự án

Giả sử hệ thống tạo tài liệu:

```text
site/
├── docs/
│   ├── intro.md
│   └── advanced/
│       └── setup.md
└── media/
    └── diagrams/
        └── architecture.png
```

Tài liệu `intro.md` cần tham chiếu ảnh:

```java
Path page = Path.of("site", "docs", "intro.md");
Path picture = Path.of(
        "site", "media", "diagrams", "architecture.png");

Path relative = page.getParent().relativize(picture);
// ../media/diagrams/architecture.png
```

Trong ngữ cảnh Markdown link, đường dẫn thường được trình bày theo ký tự phân cách `/`. Nhưng việc **chuyển `Path` thành đường URL tương đối** cần quan tâm encode ký tự đặc biệt và quy tắc của target format. Ví dụ này mô tả cách tính **các thành phần tên** trước; không tuyên bố mọi string `Path.toString()` đều là URL hợp lệ.

### 10.1. Lưu path trong cấu hình và đóng gói dự án

Nếu muốn cấu hình được di chuyển cùng một thư mục, có thể lưu path tương đối **đối với một root do ứng dụng quy định**:

```java
Path projectRoot = Path.of("site");
Path target = Path.of(
        "site", "media", "diagrams", "architecture.png");

Path stored = projectRoot.relativize(target);
// media/diagrams/architecture.png
```

Sau này, tại môi trường khác:

```java
Path newRoot = Path.of("copied-site");
Path restored = newRoot.resolve(stored).normalize();
// copied-site/media/diagrams/architecture.png
```

Điều này hữu ích khi **đồng bộ cấu trúc tương đối** giữa các môi trường. Tuy nhiên, nếu cấu hình thực tế chứa đường dẫn tới ổ ngoài, root khác hoặc filesystem provider khác, không được giả định relative path luôn tạo được.

**Quy ước quan trọng:** Luôn lưu cả **ý nghĩa của base** (“tương đối với project root”, “tương đối với file chứa liên kết”…) trong tài liệu hợp đồng. Một chuỗi `../media/architecture.png` không có nghĩa đầy đủ nếu không biết tính từ đâu.

### 10.2. Hiển thị đường dẫn gọn hơn cho log/CLI

Khi một tệp nằm trong project root, log có thể hiển thị đường dẫn tương đối thay vì đường dẫn máy cục bộ dài:

```java
Path root = Path.of("site").toAbsolutePath().normalize();
Path output = root.resolve("docs/intro.md").normalize();

if (output.startsWith(root)) {
    System.out.println(root.relativize(output));
}
```

Đây là **minh họa trong phương thức**. `startsWith(Path)` là so sánh các **thành phần Path**, không đơn thuần là `String.startsWith`. `root.relativize(output)` tạo tên ngắn hơn và tránh ghi toàn bộ đường dẫn local vào log khi không cần.

Tuy nhiên, nếu file chứa symlink hoặc input đến từ nguồn không đáng tin cậy, kiểm tra trên chỉ mang nghĩa **lexical**; không nên dùng một mình như bảo đảm truy cập file an toàn.

### 10.3. Tạo liên kết giữa các file sau khi di chuyển cây thư mục

Khi cả base và target cùng nằm dưới một thư mục cha được di chuyển nguyên vẹn, relative path giữa chúng thường vẫn giữ cấu trúc logic. Nhưng nếu chỉ di chuyển một nhánh hoặc thay đổi tên thư mục, có thể phải tính lại relative path. Điều này là lý do **lưu đường tương đối có ích cho dự án di động**, chứ không phải mọi relative path tự động bất biến trước mọi thay đổi cấu trúc.

## 11. Bảo mật: `relativize` không phải công cụ chống path traversal

Việc tạo đường tương đối và việc **giới hạn quyền truy cập tệp** là hai bài toán khác nhau.

Giả sử ứng dụng cho người dùng tải tệp từ root `uploads`. Một đầu vào như `../private/secret.txt` có thể đi ra ngoài root nếu ứng dụng ghép vào rồi truy cập mà không kiểm soát. `relativize` **có thể trả ra `..` hợp lệ theo ngữ nghĩa**, vì nó không được thiết kế như validator bảo mật.

### 11.1. Kiểm tra prefix ở mức `Path`, không phải string

Với dữ liệu tin cậy và nhu cầu kiểm tra **lexical**, cách chuẩn bị ban đầu:

```java
Path root = Path.of("uploads")
        .toAbsolutePath().normalize();

Path candidate = root.resolve(userSuppliedPath).normalize();

if (!candidate.startsWith(root)) {
    throw new SecurityException("Path escapes allowed root");
}
```

Đây là **đoạn minh họa**; `userSuppliedPath` có kiểu `Path` và phải được xử lý/giới hạn theo hợp đồng trước khi thực hiện I/O. `startsWith(Path)` phân biệt các **thành phần** đường dẫn; `String.startsWith` có thể nhầm `/data/app` với `/data/app-backup`.

Cần quyết định thêm liệu có **cho phép path tuyệt đối** đến từ người dùng hay không: theo `Path.resolve`, nếu đối số đã absolute thì kết quả có thể chính là đối số ấy, chứ không được ghép trong root. Kiểm tra đầu vào `isAbsolute()` và containment cần phù hợp chính sách.

### 11.2. Kiểm tra lexical không chặn được mọi symlink escape

Nếu `uploads/link` là symbolic link dẫn tới thư mục bên ngoài, một path có tên `uploads/link/file.txt` vẫn bắt đầu bằng root ở mức lexical nhưng thực tế có thể truy cập ngoài root.

Với những đường dẫn **đã tồn tại**, có thể dùng `toRealPath()` cho root và path dự kiến để kiểm tra đường thực sau khi giải quyết symlink, đồng thời xử lý `IOException`. Nhưng điều này **vẫn không tự loại bỏ mọi race condition**: file/symlink có thể bị thay đổi giữa lúc kiểm tra và lúc mở.

Khi phải xử lý đường dẫn không tin cậy trong môi trường có khả năng bị thay đổi đồng thời, cần thiết kế mở file an toàn theo provider, quyền hệ điều hành và cơ chế thao tác tương ứng (ví dụ `SecureDirectoryStream` trên filesystem hỗ trợ), thay vì xem `normalize`/`relativize` là một sandbox.

### 11.3. Không cấm mọi `..` nếu ứng dụng cần liên kết hợp lệ

Đối với một hệ thống sinh Markdown, `../images/logo.svg` là đường tương đối đúng. Cấm toàn bộ `..` có thể làm hỏng chức năng tạo liên kết.

Đối với một endpoint phục vụ tệp **chỉ trong uploads**, `..` lại cần kiểm soát theo root và đường thực. **Cùng một ký hiệu, nhưng chính sách khác nhau theo mục đích sử dụng.**

## 12. Phân biệt lỗi theo tình huống

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Kết quả có `..` | Hai đường dẫn thuộc nhánh khác nhau | Bình thường; kiểm tra xem base có đúng không |
| Kết quả có quá nhiều `..` | Dùng path tới file làm base thay vì thư mục chứa file | `file.getParent().relativize(target)` |
| `IllegalArgumentException` | Trộn absolute/relative, root/provider không tương thích | Chuẩn hóa loại path và kiểm tra filesystem |
| `relativize` thành công nhưng file không tồn tại | Đây là phép toán tên, không làm I/O | Dùng `Files` nếu cần xác minh file thật |
| `base.resolve(relative)` không bằng target thô | Có `.`/`..` hoặc path chưa normalized | So sánh các Path đã `normalize` khi phù hợp |
| Kết quả in dấu `\` trên Windows | File-system separator khác Unix | Giữ Path; chỉ chuẩn hóa hiển thị nếu cần |
| Kết quả empty path | Hai path bằng nhau | Trình bày `"."` ở UI nếu muốn |
| Dùng `String.startsWith` để kiểm tra root | So theo ký tự chứ không phải thành phần Path | Dùng `Path.startsWith(Path)` |
| Tài nguyên thực khác khi có symlink | `normalize`/`relativize` xử lý tên theo provider | Kiểm tra đường thực/ownership khi cần |
| Tưởng `Path.relativize` trả URL dùng ngay | Path và URI có contract khác nhau | Chuyển đổi cho định dạng đích rõ ràng |
| Lưu relative path nhưng không lưu base contract | Sau này không biết resolve từ đâu | Định nghĩa base cố định trong cấu hình |
| Trộn path của ZIP filesystem với default filesystem | Khác provider/root | Xử lý theo cùng provider hoặc định dạng khác |

## 13. Phương pháp kiểm thử `relativize` chính xác

Một bộ test tốt nên kiểm tra **kết quả và quan hệ round-trip**, thay vì so chuỗi theo một hệ điều hành duy nhất.

### 13.1. Test với các vị trí trong cây thư mục

Tạo các path **ảo trong bộ nhớ**, không cần tạo file vật lý:

```java
Path base = Path.of("a", "b");
Path child = Path.of("a", "b", "c.txt");
Path sibling = Path.of("a", "d.txt");

assert base.relativize(child).equals(Path.of("c.txt"));
assert base.relativize(sibling)
        .equals(Path.of("..", "d.txt"));
```

Đây là **đoạn minh họa**, không phải chương trình độc lập; keyword `assert` của Java cần chạy JVM với `-ea` để assertions được kiểm tra. Trong unit test thực tế, dùng assertions của JUnit hoặc một hàm `check` chủ động ném `AssertionError` như ở chương trình mục 8.

Kiểm tra bằng `Path.of("..", "d.txt")` thay vì chuỗi `"../d.txt"` thường tránh được khác biệt separator giữa Windows và Linux.

### 13.2. Test cùng path, parent/child, sibling và path đã normalize

Nên bao phủ:

- `base == target` → empty path.
- Target là con trực tiếp của base → tên con.
- Target là con nhiều cấp → đường đi xuống nhiều cấp.
- Target ở nhánh khác → có `..`.
- Target là thư mục cha → một hoặc nhiều `..`.
- Base được cho dưới dạng path tới file → xác minh có dùng `getParent()`.
- Target có `.`, `..` → làm rõ hợp đồng có normalize trước không.
- Cả hai là absolute → hoạt động trong root tương thích.
- Một absolute, một relative → kiểm tra lỗi.
- Path khác root/provider → kiểm tra chính sách fallback theo môi trường được hỗ trợ.

**Đừng hard-code root như `C:\` trong test cần chạy trên Linux**, và không giả định dấu phân cách của `Path.toString()` luôn là `/`.

### 13.3. Test không đồng nghĩa với kiểm tra symlink

Unit test với `Path.of` chứng minh tính toán tên đường dẫn. Nếu ứng dụng có yêu cầu theo symlink, cần thêm **integration test** trên filesystem thật với những symlink/permission do môi trường test kiểm soát và skip/điều chỉnh khi provider không hỗ trợ symlink. Không nên tạo symlink tùy ý bên ngoài thư mục thử nghiệm hoặc yêu cầu quyền quản trị không cần thiết.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Với `base = a/b` và `target = a/c.txt`, `base.relativize(target)` cho gì?  
**Đáp án:** `../c.txt`: lên từ `b` về `a` rồi tới `c.txt`.

**Câu 2.** `target.relativize(base)` có tương đương `base.relativize(target)` không?  
**Đáp án:** Không. Đảo thứ tự thay đổi điểm xuất phát và đích, nên có thể tạo một path hoàn toàn khác.

**Câu 3.** Một tệp Markdown ở `docs/guide.md` muốn nhúng ảnh `images/logo.svg` ở nhánh anh em, nên dùng base nào?  
**Đáp án:** Thư mục chứa tài liệu, ví dụ `Path.of("docs","guide.md").getParent()`, so với đường dẫn ảnh theo cùng gốc. Không nên coi tệp `guide.md` là một thư mục để resolve từ đó.

**Câu 4.** Hai path bằng nhau thì `relativize` trả `"."` hay chuỗi rỗng?  
**Đáp án:** Theo Java API, trả **empty path**. Ứng dụng có thể hiển thị `"."` nếu muốn, nhưng đó là cách trình bày tự chọn.

**Câu 5.** Tại sao `relativeBase.relativize(absoluteTarget)` có thể ném lỗi?  
**Đáp án:** Vì một bên không có root còn bên kia có root. Java không thể tạo relative path hợp lệ theo quy tắc này.

**Câu 6.** `normalize()` có bảo đảm đường dẫn không vượt ra ngoài root hoặc không qua symlink không?  
**Đáp án:** Không. Nó là phép biến đổi tên theo cấu trúc, không kiểm tra đường thực hoặc quyền truy cập.

**Câu 7.** `Path.relativize` có kiểm tra target tồn tại không?  
**Đáp án:** Không. Nó không làm I/O và có thể tạo relative path cho tên file chưa tồn tại.

**Câu 8.** Muốn kiểm tra liên kết được tính đúng, có thể dùng công thức nào?  
**Đáp án:** Với các path tương thích, có thể kiểm tra `base.resolve(base.relativize(target)).normalize().equals(target.normalize())`, đồng thời hiểu giới hạn lexical và symlink.

**Câu 9.** Trên Windows, kết quả `..\assets\logo.png` là sai vì không có dấu `/`?  
**Đáp án:** Không. `Path.toString()` dùng cách biểu diễn theo provider. Khi thao tác filesystem, giữ đối tượng `Path` thay vì so chuỗi raw.

**Câu 10.** Có thể dùng `relativize` làm cơ chế duy nhất chặn path traversal không?  
**Đáp án:** Không. Nó có thể sinh `..` hợp lệ và không nhận diện symlink, race condition hoặc quyền truy cập. Bảo mật cần kiểm tra root và đường thực/hợp đồng hệ điều hành theo tình huống.

## 15. Checklist áp dụng vào dự án

- [ ] Xác định rõ `base` là **thư mục** hay path tới tệp.
- [ ] Gọi `base.relativize(target)` đúng thứ tự.
- [ ] Dùng đối tượng `Path` thay vì tự tính số dấu `../` bằng string.
- [ ] Hai đường dẫn cùng kiểu relative/absolute và provider có thể relativize.
- [ ] Chỉ dùng `normalize()` khi hợp với yêu cầu lexical và đã xét symlink.
- [ ] Kiểm tra tính đúng bằng `base.resolve(relative).normalize()` khi phù hợp.
- [ ] Với link từ tệp, dùng `getParent()` và xử lý khả năng `null`.
- [ ] Tài liệu hóa root mà các đường dẫn tương đối dựa vào.
- [ ] Không coi `relativize` là phép kiểm tra file tồn tại.
- [ ] Không dùng `relativize` để thay thế kiểm soát truy cập, symlink hoặc path traversal.
- [ ] Test đủ child/sibling/parent/same, mixed absolute-relative và normalize.
- [ ] Chỉ chuyển kết quả `Path` thành URL/chuỗi khi định dạng đích và dấu phân cách đã được quy định.
- [ ] Tránh test phụ thuộc ổ đĩa Windows, separator hay thư mục làm việc cụ thể.

## 16. Kết luận và tài liệu chính thức

**`Path.relativize(target)` tạo đường dẫn tương đối từ một `Path` gốc đến một `Path` đích.** Nó kết hợp tự nhiên với `resolve`, cho phép mô tả liên kết giữa các tài nguyên mà không gắn cứng vị trí tuyệt đối của chúng.

Ba điều quyết định chất lượng triển khai:

1. **Đúng điểm xuất phát:** từ một thư mục hay từ thư mục chứa tệp, không nhầm với chính tệp.
2. **Đúng loại đường dẫn:** relative và absolute phải tương thích; root và provider phải cho phép relativize. Chuẩn hóa từ vựng khi phù hợp.
3. **Đúng ranh giới tin cậy:** tương đối hóa tên đường dẫn không đồng nghĩa kiểm tra file tồn tại, giải quyết symlink hoặc cấp quyền truy cập.

### Tài liệu Oracle còn hiệu lực

- [Java SE 17 API — `java.nio.file.Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `relativize`, `resolve`, `normalize`, `getParent`, `toAbsolutePath`, `toRealPath` và quy tắc root/provider.
- [Java SE 17 API — `java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): API thực hiện I/O, `isSameFile`, `exists` và xử lý tài nguyên thực.
- [Java SE 17 API — `java.nio.file.SecureDirectoryStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): cơ chế thao tác theo directory stream có khả năng giảm một số race condition trên filesystem hỗ trợ.
- [Java SE 17 API — `java.nio.file.Path.of`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#of(java.lang.String,java.lang.String...)): tạo các đường dẫn theo provider trên Java 17+.