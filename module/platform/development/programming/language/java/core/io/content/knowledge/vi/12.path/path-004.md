# `Path.relativize()` và điều kiện tương thích trong Java NIO.2

## 1. Mục tiêu và khái niệm cốt lõi

Trong Java NIO.2, `java.nio.file.Path` biểu diễn một đường dẫn trong hệ thống tệp. `Path.relativize(Path other)` tạo một **đường dẫn tương đối từ vị trí mà Path hiện tại biểu diễn tới Path đích**. Nó trả về một đối tượng `Path` mới; không mở, tạo, di chuyển, kiểm tra nội dung hay thay đổi tệp trên đĩa.

Ví dụ, giả sử trong dự án có hai vị trí:

```text
workspace/
├── module/                 ← đường dẫn gốc (base)
└── assets/
    └── logo.png            ← đường dẫn đích (target)
```

Từ `workspace/module` tới `workspace/assets/logo.png`, đường đi tương đối là:

```text
../assets/logo.png
```

Ở đây `..` có nghĩa là đi lên một thành phần của đường dẫn; sau đó đi xuống `assets/logo.png`. `Path.relativize` dùng các thành phần `Path` và quy tắc của filesystem/provider, **không phải phép cắt chuỗi theo dấu `/`**.

Bài học giúp bạn:

- Hiểu kết quả của `base.relativize(target)` và chiều tính đường dẫn (đổi vị trí hai đối số sẽ đổi kết quả).
- Nắm các **điều kiện tương thích**: đường dẫn cùng loại tương đối/tuyệt đối, root phù hợp, provider/filesystem tương thích.
- Dùng `normalize()`, `toAbsolutePath()` và `resolve()` đúng vai trò để tính và đối chiếu đường dẫn.
- Phân biệt thao tác **thuần cú pháp** với đường dẫn thật trên filesystem, symbolic link và `toRealPath()`.
- Xử lý `IllegalArgumentException`/`ProviderMismatchException` thay vì tự sửa chuỗi hoặc giả định thao tác luôn thành công.
- Áp dụng vào xây dựng đường dẫn tương đối cho cấu hình, liên kết giữa thư mục, cấu trúc dự án và đường dẫn file nhưng không dùng nó thay cơ chế bảo mật.

**Ghi nhớ ngay từ đầu:** Trong `base.relativize(target)`, đối tượng gọi là **base**, đối số là **target**. Đây không phải lệnh biến `target` thành absolute, cũng không phải lệnh tạo file trên đĩa.

## 2. Cú pháp và cơ chế tính đường dẫn

Khai báo:

```java
Path relative = base.relativize(target);
```

Kết quả thường là đường dẫn **không có root**, gồm các thành phần `..` để đi lên từ base và các tên còn lại để đi xuống tới target.

Hình dung các bước cho đường dẫn tương thích:

1. Xét các thành phần chung ở đầu của base và target.
2. Với mỗi thành phần còn lại ở **base**, thêm một `..` vào kết quả.
3. Sau đó thêm các thành phần còn lại ở **target**.
4. Trả về một `Path` tương đối dùng dấu phân cách phù hợp với provider.

Ví dụ về thành phần (dùng dấu `/` để minh họa):

| Base | Target | Kết quả tương đối minh họa |
| --- | --- | --- |
| `project` | `project/src/Main.java` | `src/Main.java` |
| `project/src` | `project/test/Test.java` | `../test/Test.java` |
| `a/b/c` | `a/b/c` | Đường dẫn rỗng (empty path) |
| `a/b/c` | `a/b` | `..` |
| `a/b/c` | `a/x.txt` | `../../x.txt` |
| `docs` | `images/logo.png` | `../images/logo.png` |

Bảng giả định cả hai đối số **cùng provider, cùng loại relative** và các thành phần đã ở dạng thích hợp. Java thực hiện theo quy tắc của `Path` provider nên khi xuất chuỗi trên Windows có thể thấy `\` thay cho `/`.

### 2.1. Cùng đường dẫn thì sao?

Nếu `base` và `target` biểu diễn cùng một đường dẫn theo phép so sánh thích hợp, `base.relativize(target)` tạo một **empty path**, thường có chuỗi `""`. Không phải `null`, và không nên giả định `Path.getNameCount() == 0` ở tất cả provider cho empty path. Cần phân biệt:

- `Path.of("")`: một đối tượng Path hợp lệ biểu diễn chuỗi đường dẫn rỗng.
- `null`: không phải Path; truyền vào `relativize` sẽ không phải thao tác hợp lệ.
- `"."`: thành phần thư mục hiện tại trong cú pháp đường dẫn; `Path.of(".")` không nhất thiết bằng `Path.of("")` khi chưa normalize.

### 2.2. `relativize` là phép toán một chiều

Không được nhầm:

```java
Path a = Path.of("project", "src");
Path b = Path.of("project", "test", "Test.java");

Path fromSrcToTest = a.relativize(b); // ../test/Test.java
Path fromTestToSrc = b.relativize(a); // ../..
```

Hai kết quả khác nhau vì base đã đổi. Trong ví dụ thứ hai, base là **đường dẫn biểu diễn chính file `Test.java`**, không phải thư mục cha `test`. Nếu muốn đi **từ thư mục chứa file** thay vì từ đường dẫn file, hãy dùng `b.getParent().relativize(a)`; lúc đó kết quả chỉ cần đi lên một cấp (`..`).

Đây là điểm quan trọng: `relativize` chỉ tính toán từ **Path thành phần**, không tự biết đường dẫn trỏ tới tệp hay thư mục và không tự “bỏ tên file cuối”.

## 3. Điều kiện tương thích quan trọng nhất

### 3.1. Cả hai cùng relative hoặc cả hai cùng absolute

Một cặp tương thích thông thường:

```java
Path base = Path.of("project", "src");
Path target = Path.of("project", "docs", "guide.md");
Path result = base.relativize(target); // ../docs/guide.md
```

Cả hai đều **relative** theo cùng filesystem. Ngược lại:

```java
Path base = Path.of("project", "src");   // relative
Path target = base.toAbsolutePath();      // absolute

// Không hợp lệ: base.relativize(target) ném IllegalArgumentException
```

Theo hợp đồng `Path.relativize`, khi một đường dẫn absolute còn đường kia relative, phương thức ném **`IllegalArgumentException`**. Java không tự đoán root cho một phía trong phép tính này.

Cách chuẩn bị hai đối số khi ngữ cảnh thực sự cho phép:

```java
Path relativeBase = Path.of("project", "src");
Path relativeTarget = Path.of("project", "docs", "guide.md");

Path absoluteBase = relativeBase.toAbsolutePath().normalize();
Path absoluteTarget = relativeTarget.toAbsolutePath().normalize();

Path route = absoluteBase.relativize(absoluteTarget);
```

**Chú ý:** hai `toAbsolutePath()` đều lấy ngữ cảnh thư mục làm việc của tiến trình; việc chuyển đổi phải phản ánh cùng một hệ quy chiếu thực tế. Chuyển mọi thứ thành absolute **không tự giải quyết** vấn đề root khác nhau hoặc provider khác nhau.

### 3.2. Root phải tương thích

Với đường dẫn absolute, cả hai thường cần có **root có thể relativize cùng nhau**. Trên Linux/Unix, ví dụ `/home/a` và `/var/data` đều có root `/` nên provider mặc định thường tính đường dẫn từ nơi này tới nơi kia.

Trên Windows, một đường dẫn absolute ở ổ `C:\` và một đường dẫn ở `D:\` là hai root khác nhau; thường không thể biểu diễn đích chỉ bằng các bước `..` tương đối từ base. Kết quả có thể là `IllegalArgumentException`. Đường dẫn UNC (network shares) cũng có đặc điểm root riêng.

Ví dụ mô tả, **không phải mã chạy portable**:

```text
Base:    C:\projects\app
Target:  D:\archive\image.png
Result:  không có đường dẫn tương đối phù hợp theo cơ chế relativize thông thường
```

Không nên xây logic bằng cách bắt exception rồi xóa ký tự ổ đĩa bằng `substring`; như vậy sẽ đánh mất ý nghĩa root và tạo đường dẫn sai. Nếu không thể relativize, hãy giữ absolute path hoặc từ chối tác vụ theo hợp đồng ứng dụng.

### 3.3. Provider và filesystem phải tương thích

`Path` không nhất thiết đại diện cho filesystem mặc định trên ổ đĩa. Java có thể dùng những **FileSystemProvider** khác nhau, ví dụ default filesystem, ZIP filesystem hay một provider của thư viện bên ngoài.

Một `Path` đến từ default filesystem và một `Path` đến từ ZIP filesystem **không thể được coi là hai nhánh trong cùng một cây path** chỉ vì `toString()` của chúng giống nhau.

Trong trường hợp provider không tương thích, `relativize` có thể ném **`ProviderMismatchException`** (một lớp con của `IllegalArgumentException`), hoặc có điều kiện tương thích khác theo provider. Không được trộn đối tượng `Path` khác provider rồi hy vọng `normalize()` hoặc `toAbsolutePath()` biến chúng thành cùng filesystem.

### 3.4. Bảng quyết định nhanh

| Base | Target | Khả năng |
| --- | --- | --- |
| Relative A | Relative B trên cùng provider | Thường relativize được |
| Absolute A | Absolute B cùng root/provider phù hợp | Thường relativize được |
| Relative A | Absolute B | **Không tương thích**, ném `IllegalArgumentException` |
| Absolute A | Relative B | **Không tương thích**, ném `IllegalArgumentException` |
| Absolute C: | Absolute D: trên Windows | Root không tương thích; thường không relativize được |
| Default filesystem | ZIP filesystem | Provider/filesystem khác; không giả định có thể relativize |
| Cùng pathname | Cùng pathname | Empty path |
| Hai Path có `.`, `..` chưa normalize | Cùng loại/root | Có thể tính nhưng kết quả có thể khó hiểu; nên xác định chiến lược normalize |

Không có một phép “ép sang relative” áp dụng cho mọi cặp `Path`. Cần xác định **hệ quy chiếu**: cùng filesystem, cùng root, cùng semantics về đường dẫn.

## 4. Ví dụ Java 17+ hoàn chỉnh, chạy đa nền tảng

Ví dụ dưới đây tránh in chuỗi có dấu phân cách phụ thuộc hệ điều hành. Thay vào đó, in số thành phần, kiểm tra ký tự `..` và chứng minh quan hệ `resolve`/`normalize`. Chương trình **không cần tạo file thật**.

Lưu thành **`PathRelativizeDemo.java`**:

```java
import java.nio.file.Path;

public class PathRelativizeDemo {
    public static void main(String[] args) {
        Path base = Path.of("workspace", "module");
        Path target = Path.of("workspace", "assets", "logo.png");

        Path route = base.relativize(target);

        System.out.println("Base relative: " + !base.isAbsolute());
        System.out.println("Target relative: " + !target.isAbsolute());
        System.out.println("Route relative: " + !route.isAbsolute());
        System.out.println("Route parts: " + route.getNameCount());
        System.out.println("Starts with ..: "
                + route.getName(0).toString().equals(".."));
        System.out.println("Reconstructed: "
                + base.resolve(route).normalize()
                          .equals(target.normalize()));

        Path same = base.relativize(base);
        System.out.println("Same gives empty: "
                + same.toString().isEmpty());

        try {
            base.relativize(target.toAbsolutePath());
            System.out.println("Mixed types accepted");
        } catch (IllegalArgumentException error) {
            System.out.println("Mixed types rejected");
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 PathRelativizeDemo.java
java PathRelativizeDemo
```

**Stdout trong môi trường filesystem mặc định thông thường:**

```text
Base relative: true
Target relative: true
Route relative: true
Route parts: 3
Starts with ..: true
Reconstructed: true
Same gives empty: true
Mixed types rejected
```

**Giải thích theo thứ tự:**

1. `Path.of("workspace", "module")` và `Path.of("workspace", "assets", "logo.png")` đều relative.
2. Hai đường dẫn có thành phần chung `workspace`. Từ `module` đi lên bằng `..` rồi đi xuống `assets/logo.png`, vì vậy route có ba thành phần.
3. `route.getName(0)` là `".."`. Kiểm thử dựa trên **thành phần Path**, không dựa trên dấu phân cách `/` hay `\`.
4. `base.resolve(route).normalize()` tạo lại đường dẫn lexical tương đương `target.normalize()` trong ví dụ.
5. Khi gọi `base.relativize(base)`, kết quả biểu diễn đường dẫn rỗng.
6. Khi gọi `base.relativize(target.toAbsolutePath())`, một bên relative còn bên kia absolute; nhánh bắt `IllegalArgumentException` được thực thi.

Ví dụ không chứng minh file `logo.png` tồn tại. `Path.relativize` và `normalize()` trong tình huống này chỉ thao tác trên thành phần tên. Nếu không có `workspace` trên ổ đĩa, mọi dòng stdout về cú pháp vẫn có ý nghĩa như trên.

### 4.1. Tránh dùng chuỗi separator cố định trong kiểm thử

Trên Unix, `route.toString()` thường trông như `../assets/logo.png`, còn trên Windows là `..\assets\logo.png`. Nếu muốn bài kiểm thử chạy cả hai nền tảng, có thể so sánh với `Path.of("..", "assets", "logo.png")`:

```java
// Minh họa bổ sung (đặt sau khi route được tạo):
boolean equivalent =
        route.equals(Path.of("..", "assets", "logo.png"));
System.out.println(equivalent);
```

Đây là **đoạn minh họa**; cần biến `route` thuộc ví dụ chạy đầy đủ. Kết quả là `true` theo provider mặc định khi đầu vào đúng như trên.

## 5. `normalize()` và thời điểm nên áp dụng

### 5.1. Chuẩn hóa cú pháp trước khi tính

`Path.normalize()` loại bỏ các thành phần dư thừa như `.` và các cặp tên/`..` khi có thể. Phương thức này **không truy cập filesystem** và không yêu cầu file tồn tại.

Ví dụ:

```java
Path base = Path.of("root", "docs", "..", "src");
Path target = Path.of("root", "assets", ".", "icon.svg");

Path normalizedBase = base.normalize();     // root/src
Path normalizedTarget = target.normalize(); // root/assets/icon.svg

Path route = normalizedBase.relativize(normalizedTarget);
// ../assets/icon.svg (hiển thị theo separator của nền tảng)
```

Những dòng trên là minh họa cho cú pháp API, không phải class hoàn chỉnh. Trong tình huống cấu trúc dự án và đường dẫn thuần lexical, chiến lược **normalize hai phía rồi relativize** giúp kết quả dễ hiểu và dự đoán hơn.

Cần áp dụng **cùng chiến lược** cho cả base và target. Nếu một bên được normalize còn bên kia chứa thành phần `..` thừa, kết quả có thể khiến người đọc hiểu sai.

### 5.2. Không được nhầm `normalize` với canonical/real path

`normalize()` chỉ sửa đường dẫn về mặt cú pháp, không hỏi filesystem xem thành phần `link` có phải symbolic link không.

Ví dụ khái niệm (giả sử `link` là symbolic link trỏ tới một vị trí khác):

```text
/data/link/../report.txt
```

`normalize()` có thể rút gọn thành `/data/report.txt`, nhưng khi OS thực sự đi qua `link` là symlink, semantics của `..` có thể khác. Vì thế quy tắc “bỏ một tên rồi một `..`” **không phải chứng minh** đường dẫn cũ và mới trỏ tới cùng file vật lý.

- `Path.normalize()`: xử lý cú pháp; không yêu cầu tồn tại.
- `Path.toAbsolutePath()`: tạo absolute path; không phải bước giải quyết symlink.
- `Path.toRealPath()`: thực hiện thao tác filesystem để lấy đường dẫn thực, mặc định yêu cầu tồn tại và giải quyết symbolic link, có thể ném `IOException`.
- `File.getCanonicalPath()`: API truyền thống với semantics canonical pathname; không đồng nhất hoàn toàn với `toRealPath()`, nhất là với path chưa tồn tại.

**Lựa chọn:** Nếu mục tiêu là tạo tên đường dẫn relative cho tệp nguồn/dự án, hãy xem xét normalize. Nếu phải xác định đường dẫn thực của **file đang tồn tại**, cân nhắc `toRealPath()` và xử lý lỗi/tính thay đổi đồng thời.

## 6. `resolve()` và `relativize()`: quan hệ hai chiều

### 6.1. `resolve` làm gì?

`base.resolve(other)` ghép `other` vào `base` khi `other` là relative. Nếu `other` là absolute, theo hợp đồng `Path.resolve` của provider mặc định, kết quả thường là chính `other`; với provider khác, chi tiết có thể phụ thuộc triển khai. Không được dựa vào `resolve` để âm thầm xác nhận rằng `other` an toàn hoặc nằm trong base.

Ví dụ thuần lexical:

```java
Path base = Path.of("app", "src");
Path other = Path.of("..", "assets", "logo.png");
Path combined = base.resolve(other).normalize();
// app/assets/logo.png
```

`resolve` **không đọc/ghi file**, và việc ghép đường dẫn không tự tạo thư mục.

### 6.2. Kiểm tra quan hệ reconstruction

Với hai đường dẫn tương thích và đã normalize, có thể kiểm tra:

```java
Path relative = base.relativize(target);
Path reconstructed = base.resolve(relative).normalize();
boolean matches = reconstructed.equals(target.normalize());
```

Trong tình huống chuẩn của ví dụ, `matches` là `true`. Đây là công cụ hữu ích để phát hiện bug **đổi chiều** hoặc xử lý `..` không đúng.

Nhưng đây là phép đồng nhất **đường dẫn lexical**. Nó không chứng minh file đã tồn tại, kiểm tra quyền, đối chiếu inode/file identity hoặc ngăn symlink thay đổi. Với ngữ cảnh có root phức tạp, path chưa normalize và provider khác nhau, cần kiểm tra hợp đồng provider thay vì suy diễn từ một công thức cho mọi trường hợp.

### 6.3. `relativize` không phải `resolve` với dấu âm

Không nên coi `relativize` là “phép trừ đường dẫn” dựa trên `String.replace`. Đường dẫn có hệ thống root, separator, filesystem provider và có thể có thành phần đặc biệt. `Path.relativize` tính theo cấu trúc Path, còn phép cắt chuỗi bỏ mất các thông tin đó.

## 7. Relative và absolute: quy trình chọn dùng an toàn, dễ bảo trì

Trong một ứng dụng, trước khi gọi `relativize` hãy xác định **ngữ cảnh gốc của cả hai đường dẫn**:

1. Nếu cả hai là relative và được hiểu từ **cùng working directory/anchor**, có thể normalize rồi relativize.
2. Nếu cả hai là absolute, kiểm tra chúng thuộc root/provider tương thích và relativize theo hệ tọa độ đó.
3. Nếu một absolute, một relative, **đừng tự đoán**. Xác định xem relative thật sự được hiểu từ working directory, từ một root dự án hay từ thư mục cha cụ thể, rồi convert *có chủ đích*.
4. Nếu không thể xác định cùng hệ quy chiếu, xử lý bằng thông báo lỗi, giữ absolute path hoặc thay đổi dữ liệu đầu vào.
5. Nếu Path thuộc provider đặc biệt (ZIP, filesystem ảo), bảo đảm cả hai cùng provider/filesystem thích hợp thay vì đổi qua `toString()` để ghép thủ công.

### 7.1. Trường hợp cần cố định root ứng dụng

Giả sử cấu hình của dự án dùng các đường dẫn tương đối dưới root xác định, hãy resolve cả hai **từ cùng root**:

```java
// Minh họa; projectRoot là Path absolute do ứng dụng cung cấp.
Path base = projectRoot.resolve("src").normalize();
Path target = projectRoot.resolve("assets/logo.png").normalize();
Path relative = base.relativize(target);
```

Ví dụ này **không phải chương trình độc lập** vì chưa khai báo `projectRoot`. Trong ứng dụng thật, `projectRoot` nên được xác định rõ từ cấu hình/đường dẫn tin cậy. Nếu `projectRoot` chỉ là relative, cần thống nhất việc chuyển thành absolute trước khi ghép.

### 7.2. Không suy luận working directory từ vị trí file nguồn

Một lỗi thường gặp: chương trình dùng `Path.of("src")` rồi giả định đó là thư mục `src` trong repository. Khi chạy bằng IDE, service, script hoặc container, working directory có thể khác. `toAbsolutePath()` chỉ giải quyết theo ngữ cảnh tiến trình, không biết module nào được lập trình viên “muốn dùng”.

Nếu ứng dụng cần đường dẫn độc lập với working directory, hãy dùng cấu hình absolute hoặc xác định root rõ ràng tại thời điểm khởi tạo ứng dụng.

## 8. Root và filesystem provider trong hệ thống thực tế

### 8.1. FileSystem mặc định

`Path.of(...)` thường tạo đường dẫn thuộc default provider của hệ điều hành hiện tại. Trên hệ Unix, absolute paths hay bắt đầu từ `/`. Trên Windows, có thể có root của ổ đĩa hoặc UNC.

Với hai đường dẫn absolute cùng root, phép tính tương đối có ý nghĩa. Với hai ổ đĩa không cùng root, có thể không tồn tại một relative path thuần `..` nối giữa chúng.

Khi kiểm tra khả năng tương thích, có thể xem:

```java
// Minh họa với các Path đã tồn tại trong mã.
boolean sameFileSystem = base.getFileSystem()
        .equals(target.getFileSystem());
boolean sameKind = base.isAbsolute() == target.isAbsolute();
```

Hai boolean này là **chỉ báo ban đầu**, không thay thế hợp đồng `relativize`. Ví dụ, trên Windows cùng FileSystem mặc định vẫn có thể có hai drive root khác nhau. Khi thực sự tính, gọi `relativize` và xử lý `IllegalArgumentException` nếu đầu vào không tương thích.

### 8.2. Provider riêng như ZIP filesystem

Một Path bên trong ZIP filesystem do provider quản lý không được xem là con của một directory Path mặc định chỉ vì tên hai path cùng chứa `/docs`. Provider có thể xác định cú pháp root, cách so sánh và cách relativize khác nhau.

Không nên dùng `Path.of(zipPath.toString())` để “ép” path ZIP sang default filesystem rồi coi nó vẫn tham chiếu tới cùng file. Cách đó chỉ tạo **một Path mới có chuỗi giống hoặc tương tự**, không tự giữ ngữ nghĩa filesystem ban đầu.

Nếu ứng dụng cần sao chép dữ liệu giữa hai provider, hãy dùng API mở/đọc/ghi trên từng provider và xác định đích riêng, không yêu cầu `relativize` nối hai cây filesystem khác nhau.

### 8.3. Xử lý ngoại lệ chính xác

Hợp đồng `relativize` có thể ném:

- `IllegalArgumentException` khi hai path không thể relativize, ví dụ absolute/relative trộn hoặc root không tương thích.
- `ProviderMismatchException` khi các Path do provider không phù hợp quản lý; đây là kiểu con của `IllegalArgumentException` trong Java.
- `NullPointerException` nếu truyền `null` vào phương thức.

Lưu ý `Path.relativize` không khai báo `throws IOException` vì nó chủ yếu thao tác cấu trúc Path, khác với `toRealPath()` có thể truy cập filesystem.

Nếu cần thông báo riêng cho provider mismatch, bắt `ProviderMismatchException` **trước** `IllegalArgumentException` trong nhiều nhánh catch; không bắt ngược thứ tự khi lớp con đã bị catch bởi lớp cha.

Không nên viết `catch (Exception ignored)` rồi trả một chuỗi “relative” giả để che việc hai hệ quy chiếu không tương thích.

## 9. Sai lầm thường gặp và cách sửa

### 9.1. Đổi chiều giữa base và target

Sai mục tiêu: muốn đường từ `src` đến `tests` nhưng lại gọi `tests.relativize(src)`. Hãy đọc câu “**từ object gọi phương thức đến đối số**”. Trong code, đặt tên rõ `from`/`to`:

```java
Path from = Path.of("project", "src");
Path to = Path.of("project", "tests");
Path navigation = from.relativize(to); // ../tests
```

### 9.2. Dùng một absolute và một relative

Không thể gọi thành công theo hợp đồng mặc định. Trước khi convert, phải biết relative được neo ở đâu. `toAbsolutePath()` chỉ là một cách dựa trên working directory; không phải lựa chọn đúng cho mọi dữ liệu.

### 9.3. Suy luận kết quả không phụ thuộc nền tảng

Chuỗi `relative.toString()` có thể dùng `/` hoặc `\`. Hãy so sánh `Path`/tên thành phần, không hard-code separator trong test đa hệ điều hành.

### 9.4. Quên xử lý `..` trong chính input

Với đường dẫn có `. / ..`, kết quả có thể khó đọc hoặc không phù hợp với dự kiến. Khi mục tiêu là phép tính lexical, cân nhắc `normalize()` trước phép tính. Không dùng normalize làm bằng chứng path trỏ cùng file nếu có symlink.

### 9.5. Coi relative path là bảo đảm file tồn tại

`relativize` không gọi `Files.exists()`, không tạo file và không mở handle. Đường dẫn đích có thể không có thật. Khi dùng kết quả để đọc file, vẫn phải xử lý `IOException`.

### 9.6. So sánh path bằng chuỗi tiền tố

Nếu ứng dụng muốn kiểm tra xem một file nằm dưới một thư mục, gọi `string.startsWith("/data")` không tương đương với kiểm tra thành phần path vì `/database` cũng có tiền tố `/data`. Sau khi chọn cùng filesystem và normalize phù hợp, `candidate.startsWith(root)` trên **Path** là kiểm tra lexical về thành phần, nhưng chưa xử lý symlink hoặc các thay đổi trên đĩa.

### 9.7. Nhầm `relativize` là công cụ bảo mật

Một chương trình có thể tạo một relative path trỏ **ra ngoài** root thông qua `..`. Kết quả tương đối không đồng nghĩa “được phép truy cập”. Với đường dẫn người dùng nhập, cần giới hạn các thành phần cho phép, root tin cậy, quyền truy cập, symlink policy và biện pháp chống thay đổi filesystem đồng thời.

### 9.8. Xử lý tất cả đường dẫn như cùng provider

Hai `Path` trông giống nhau khi in ra có thể thuộc hai filesystem khác nhau. So sánh `getFileSystem()`/provider khi cần và thiết kế rõ nơi dữ liệu được lưu trữ.

## 10. Symlink, `toRealPath()` và vấn đề bảo mật

### 10.1. Lexical route không đồng nghĩa route vật lý

Giả sử `/project/assets` là symlink đến `/mnt/shared-assets`. `Path.of("/project/src").relativize(Path.of("/project/assets/logo.png"))` tính toán bằng các thành phần `Path`, không mở symlink để hỏi file đích thực ở đâu.

Nếu cần tương quan giữa **hai file thực sự đang tồn tại**, có thể lấy real paths:

```java
// Minh họa: base và target là Path tới các tài nguyên đang tồn tại.
Path realBase = base.toRealPath();
Path realTarget = target.toRealPath();
Path navigation = realBase.relativize(realTarget);
```

Cách này yêu cầu file/dir tồn tại và cùng provider/root có thể relativize, có thể ném `IOException`. Đường dẫn sau khi giải quyết symlink có thể nằm ngoài cây thư mục ban đầu. `toRealPath()` còn có tùy chọn `LinkOption.NOFOLLOW_LINKS` nếu yêu cầu là *không theo* liên kết; hãy lựa chọn theo threat model, không dùng như nghi thức mặc định.

### 10.2. Kiểm tra rồi mới dùng có thể gặp TOCTOU

Nếu tiến trình khác có quyền thay đổi symlink/directory sau khi bạn kiểm tra, đường dẫn thực có thể đổi trước lúc đọc file (time-of-check-to-time-of-use). Vì vậy, kể cả `toRealPath()` và `relativize` sau đó **không tự khóa** đối tượng file.

Với yêu cầu bảo mật cao, hãy dùng API mở tài nguyên bằng cơ chế quản lý directory/file handle phù hợp với provider, phân quyền filesystem, và cân nhắc `SecureDirectoryStream` khi được hỗ trợ. Đừng cố dùng một phép tính chuỗi/Path thuần lexical để chứng minh không thể có race.

## 11. Checklist chọn và sử dụng đúng

| Câu hỏi | Cách quyết định |
| --- | --- |
| Muốn đường đi từ A đến B? | `A.relativize(B)` |
| Hai Path khác loại absolute/relative? | Xác định anchor rồi chuyển cả hai về hệ tọa độ chung; nếu không, báo lỗi |
| Hai absolute path khác root? | Đừng giả định có relative route; xử lý `IllegalArgumentException` |
| Hai Path khác provider? | Không ép chuỗi để trộn; xử lý theo từng filesystem |
| Đường dẫn có `.`/`..`? | Xem xét normalize **cả hai** nếu mục tiêu là cú pháp |
| Cần ghép base và relative route? | `base.resolve(route)`; normalize nếu cần |
| Cần xác minh kết quả trong test? | So sánh `Path` thành phần hoặc `resolve(...).normalize()` với target normalized |
| Cần kiểm tra sự tồn tại/tài nguyên thật? | Dùng `Files`/`toRealPath()`; xử lý `IOException` |
| Cần ngăn truy cập ra ngoài root? | Thiết kế kiểm soát containment + symlink + race, không dựa đơn lẻ vào `relativize` |
| Chạy đa nền tảng? | Tránh kỳ vọng chuỗi `/` hay `\` cố định |

## 12. Bài tập tự đánh giá

1. **Cơ bản:** tính `Path.of("a", "b").relativize(Path.of("a", "c", "d.txt"))` và trình bày các thành phần kết quả.
2. **Đổi chiều:** tính đường ngược lại. Vì sao số bước `..` khác khi base là path tới một file?
3. **Tương thích:** giải thích vì sao `Path.of("docs").relativize(Path.of("docs").toAbsolutePath())` ném `IllegalArgumentException`.
4. **Đồng nhất:** gọi `p.relativize(p)`, in `toString()`, nhận xét về empty path.
5. **Normalize:** với `base = "a/b/../src"`, `target = "a/docs/./intro.md"`, normalize cả hai và relativize; kiểm tra `base.normalize().resolve(route).normalize()`.
6. **Windows roots:** vì sao `C:\work` và `D:\backup` thường không thể relativize? Vì sao xử lý bằng substring ổ đĩa là sai?
7. **Provider:** nêu vấn đề khi trộn Path từ ZIP filesystem với Path từ default filesystem.
8. **Symlink:** so sánh ý nghĩa của `normalize()` và `toRealPath()` khi một thư mục trung gian là symbolic link.
9. **Thực hành:** viết hàm trả về `Optional<Path>` cho một cặp Path tương thích, còn cặp không tương thích trả `Optional.empty()` hoặc báo lỗi có ngữ cảnh. Chỉ bắt lỗi liên quan; không âm thầm đổi root.
10. **Thiết kế an toàn:** người dùng đưa tên file cần tải xuống; giải thích tại sao `relativize` không phải bước xác thực được phép truy cập vào root thư mục.

## 13. Tóm tắt kiến thức

- **`base.relativize(target)`** tạo một đường dẫn tương đối **từ base đến target**.
- **Tính tương thích là bắt buộc:** cả hai relative hoặc cả hai absolute; absolute paths cần root thích hợp và cả hai Path phải thuộc môi trường filesystem/provider tương thích.
- **`normalize()`** giúp đơn giản hóa cú pháp, **`toAbsolutePath()`** định vị từ ngữ cảnh làm việc, **`resolve()`** ghép relative path và **`toRealPath()`** yêu cầu tra cứu filesystem khi cần đường dẫn thực.
- `relativize` **không mở tệp, không bảo đảm file tồn tại, không truy cập symlink để xác minh**, không tự làm công cụ path security.
- Để tránh lỗi, hãy xác định **chiều from → to**, thống nhất hệ quy chiếu, viết test đối chiếu bằng `Path` và xử lý rõ ràng các trường hợp không tương thích.

**Quy tắc thực hành:** Chọn hai `Path` cùng hệ tọa độ, xác định cần tính toán lexical hay cần tương quan với tài nguyên thật, rồi mới dùng `relativize`. Không thay thế việc kiểm tra và bảo vệ filesystem bằng một phép biến đổi đường dẫn.