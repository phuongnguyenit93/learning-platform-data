# Java File truyền thống: mkdir(), mkdirs(), createNewFile(), renameTo() và delete()

## 1. Mục tiêu và bối cảnh

**java.io.File** là API Java truyền thống đại diện cho **đường dẫn trừu tượng** đến file hoặc thư mục trên hệ thống file. Một đối tượng File **không tự tạo file/thư mục trên ổ đĩa** chỉ vì bạn gọi constructor.

Ví dụ:

~~~java
File folder = new File("data/reports");
File report = new File(folder, "daily.txt");
~~~

Đây là **mảnh code minh họa**, cần import **java.io.File**. Sau hai lệnh trên, Java chỉ có hai đối tượng đại diện cho đường dẫn. Muốn thực sự tạo thư mục hoặc file, bạn phải gọi API như **mkdir()**, **mkdirs()**, **createNewFile()**.

Năm phương thức chính:

| Phương thức | Công dụng | Kiểu trả về | Điều quan trọng |
| --- | --- | --- | --- |
| **mkdir()** | Tạo **một** thư mục | boolean | Thư mục cha phải tồn tại |
| **mkdirs()** | Tạo thư mục đích **và các thư mục cha còn thiếu** | boolean | Trả false khi thư mục đích đã có; thất bại có thể để lại một số thư mục cha |
| **createNewFile()** | Tạo file rỗng **chỉ khi tên chưa tồn tại** | boolean, có thể ném IOException | Kiểm tra tồn tại và tạo mới là một thao tác nguyên tử theo hợp đồng API |
| **renameTo(File dest)** | Đổi tên hoặc di chuyển đường dẫn nguồn sang đích | boolean | Thành công phụ thuộc hệ thống file; không bảo đảm nguyên tử |
| **delete()** | Xóa một file hoặc **thư mục rỗng** | boolean | Không tự xóa đệ quy cây thư mục |

**Quy tắc lớn nhất:** Với các thao tác trả **boolean**, phải **kiểm tra kết quả**. Trả false không cung cấp chẩn đoán chi tiết “vì sao thất bại”. Khi viết ứng dụng mới cần thông báo lỗi chính xác, **java.nio.file.Files** và **Path** thường phù hợp hơn.

## 2. Mô hình đường dẫn của java.io.File

Đoạn code:

~~~java
File root = new File("workspace");
File child = new File(root, "images");
File image = new File(child, "logo.png");
~~~

biểu diễn quan hệ:

~~~text
workspace/
└── images/
    └── logo.png
~~~

**Nhưng các đường dẫn này chưa chắc tồn tại trên đĩa.** Đây chỉ là mô hình tên đường dẫn. **File** cũng không “mở file”, không giữ stream và không bảo đảm loại tài nguyên cuối cùng: một đường dẫn có thể chưa tồn tại, là thư mục, là file thường hoặc tài nguyên khác theo hệ thống file.

Các phép kiểm tra:

~~~java
boolean exists = image.exists();
boolean regularFile = image.isFile();
boolean directory = child.isDirectory();
File parent = image.getParentFile();
~~~

Đây là **mảnh code minh họa**. **exists()**, **isFile()**, **isDirectory()** quan sát trạng thái hệ thống file ở một thời điểm, có thể chịu ảnh hưởng quyền truy cập. Kết quả kiểm tra **không khóa trạng thái**: đối tượng khác có thể tạo, đổi tên hoặc xóa đường dẫn ngay sau khi chương trình kiểm tra.

Cách ghép **new File(parent, child)** giúp tránh tự nối chuỗi đường dẫn bằng dấu **/** hoặc **\\**. Đường dẫn tương đối được diễn giải theo thư mục làm việc của tiến trình; đường dẫn tuyệt đối chỉ rõ nơi đến, nhưng vẫn phụ thuộc môi trường. **File.separator** và **Path.resolve(...)** là cách biểu diễn đường dẫn tương thích đa hệ điều hành hơn việc hard-code dấu phân cách.

## 3. mkdir(): chỉ tạo đúng một cấp thư mục

Chữ ký:

~~~java
public boolean mkdir()
~~~

**mkdir()** yêu cầu hệ thống tạo thư mục đúng tại đường dẫn của File. Nó **không tự tạo các thư mục cha** còn thiếu.

Giả sử thư mục **project** đã tồn tại:

~~~text
project/
~~~

Gọi:

~~~java
File logs = new File("project/logs");
boolean created = logs.mkdir();
~~~

Nếu có quyền ghi và không có xung đột, thư mục **project/logs** được tạo và **created == true**. Ngược lại, nếu cố tạo trực tiếp **project/archive/2026** mà **project/archive** chưa có, **mkdir()** không tự tạo **archive**, nên thường trả false.

**Các lý do trả false** gồm: thư mục đã tồn tại, tên đã tồn tại nhưng là file, thư mục cha thiếu, không đủ quyền hoặc lỗi hệ thống file. Khi chỉ nhìn boolean, các nguyên nhân không được phân biệt chính xác.

**Điểm dễ nhầm:** Gọi **mkdir()** lần thứ hai trên thư mục vừa tạo thường trả **false**. False ở đây không chứng minh rằng thư mục đang bị lỗi: phương thức chỉ trả true khi **chính lần gọi đó đã tạo thành công**.

## 4. mkdirs(): tạo cả cây thư mục còn thiếu

Chữ ký:

~~~java
public boolean mkdirs()
~~~

**mkdirs()** tạo thư mục đích và các cấp thư mục cha còn thiếu nếu cần.

Ví dụ một thư mục gốc hợp lệ đã tồn tại:

~~~text
data/
~~~

Với:

~~~java
File output = new File("data/2026/october/reports");
boolean created = output.mkdirs();
~~~

nếu thành công, kết quả:

~~~text
data/
└── 2026/
    └── october/
        └── reports/
~~~

Lần gọi đầu **có thể trả true** khi thành công; lần tiếp theo trên cùng đường dẫn thường **trả false** vì đích đã tồn tại. Điều đó khác với một API kiểu “đảm bảo tồn tại”, vốn có thể được gọi nhiều lần mà không coi việc tồn tại là lỗi.

### 4.1. mkdir() so với mkdirs()

| Tình huống | mkdir() | mkdirs() |
| --- | --- | --- |
| Tạo **data/logs**, thư mục **data** đã có | Có thể thành công | Có thể thành công |
| Tạo **data/a/b**, **a** chưa có | Thường **false** | Có thể tạo cả **a** và **b** |
| Thư mục đích đã tồn tại | **false** | **false** |
| Một thư mục cha trùng tên file thường | Thất bại | Thất bại |
| Tạo một phần cây rồi có lỗi ở cấp sau | Không tự tạo các cấp cha | **Có thể đã tạo một số thư mục cha** trước khi thất bại |

Không được nghĩ rằng **mkdirs()** là giao dịch “được hết hoặc không tạo gì”. Tài liệu Java lưu ý nếu thao tác thất bại, **một số thư mục cha có thể đã được tạo**, dù thư mục đích không có.

### 4.2. Khi thư mục đã tồn tại thì nên xử lý thế nào?

Nếu mục tiêu nghiệp vụ là “thư mục phải tồn tại và đúng là một thư mục”, thay vì chỉ “lần gọi này tạo được thư mục”, có thể viết:

~~~java
File directory = new File("data/reports");
if (!directory.isDirectory()) {
    if (!directory.mkdirs() && !directory.isDirectory()) {
        throw new IllegalStateException(
                "Không thể chuẩn bị thư mục: " + directory);
    }
}
~~~

Đây là **mảnh mã minh họa**. Phép kiểm tra **isDirectory()** sau khi mkdirs thất bại giúp nhận diện trường hợp một tiến trình khác vừa tạo thư mục, nhưng vẫn **không loại bỏ hoàn toàn race condition** nếu tài nguyên có thể thay đổi đồng thời.

Với mã hiện đại, **Files.createDirectories(path)** là cách thích hợp hơn: tạo cha khi cần, có thể được gọi khi thư mục đích đã tồn tại và trả Path nếu hoàn tất, trong khi lỗi I/O thường được biểu diễn bằng **IOException** cụ thể.

## 5. createNewFile(): tạo file rỗng nếu chưa tồn tại

Chữ ký:

~~~java
public boolean createNewFile() throws IOException
~~~

**createNewFile()** tạo một **file rỗng** tại đường dẫn khi **chưa có mục file system với tên đó**.

- **true**: tạo mới thành công trong lần gọi này.
- **false**: đường dẫn đích đã tồn tại.
- **IOException**: có lỗi I/O như thư mục cha không có, không tạo được đối tượng file hoặc lỗi do hệ thống file; trường hợp cụ thể còn tùy môi trường.
- **SecurityException**: có thể xảy ra khi chính sách bảo mật của môi trường từ chối thao tác.

Ví dụ:

~~~java
File folder = new File("data");
if (!folder.isDirectory() && !folder.mkdirs()) {
    throw new IOException("Không tạo được thư mục data");
}

File report = new File(folder, "report.txt");
if (report.createNewFile()) {
    System.out.println("Đã tạo file rỗng");
} else {
    System.out.println("Tên file đã tồn tại");
}
~~~

Đây là **mảnh code minh họa**, cần import **java.io.File** và **java.io.IOException**, đồng thời nằm trong phương thức khai báo hoặc xử lý IOException. Khi file chưa có và tạo thành công, kích thước ban đầu là **0 byte**. **createNewFile() không tự ghi nội dung, không tạo thư mục cha và không mở OutputStream để người gọi ghi dữ liệu**.

### 5.1. Tính nguyên tử của tạo mới

Theo hợp đồng **createNewFile()**, việc **kiểm tra đường dẫn chưa tồn tại** và **tạo file mới** được thực hiện như **một thao tác nguyên tử** đối với các hoạt động hệ thống file có thể tác động đến đường dẫn.

Đây là lý do nên dùng:

~~~java
boolean created = file.createNewFile();
~~~

thay vì:

~~~java
if (!file.exists()) {
    file.createNewFile();
}
~~~

khi mục tiêu là **chỉ tạo mới một lần nếu chưa có**. Hai lần thao tác tách rời (exists rồi create) tạo ra khoảng thời gian để tiến trình khác can thiệp. Vẫn phải kiểm tra giá trị trả về của createNewFile. Đồng thời, **không dùng createNewFile như cơ chế file-lock đáng tin**; tài liệu Java khuyên dùng **FileLock** cho bài toán khóa file.

Nếu cần **mở ngay một luồng ghi và chỉ chấp nhận tạo file mới**, ứng dụng hiện đại có thể dùng **Files.newOutputStream(path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)**. Cách này đặt điều kiện tạo mới ở thao tác mở luồng thay vì tạo xong rồi mở lại, giúp tránh khoảng trống giữa hai hoạt động riêng.

## 6. renameTo(File dest): đổi tên hoặc chuyển vị trí nhưng phụ thuộc nền tảng

Chữ ký:

~~~java
public boolean renameTo(File dest)
~~~

**renameTo(dest)** yêu cầu đổi tên hoặc di chuyển đối tượng tại đường dẫn của nguồn sang đường dẫn đích.

Ví dụ:

~~~java
File source = new File("data/old.txt");
File destination = new File("data/new.txt");

boolean renamed = source.renameTo(destination);
if (!renamed) {
    System.err.println("Không đổi tên được; cần xử lý lỗi");
}
~~~

Đây là **mảnh code minh họa**, cần import **java.io.File** và dữ liệu nguồn phải tồn tại để rename có thể thành công.

### 6.1. Những điều KHÔNG được giả định

1. **Không bảo đảm luôn chuyển được giữa hai filesystem/ổ đĩa.** Chuyển trong cùng filesystem có thể thành công, trong khi chuyển qua vùng lưu trữ khác thất bại.
2. **Không bảo đảm thao tác luôn nguyên tử.** Ngữ nghĩa cụ thể phụ thuộc nền tảng và hệ thống file.
3. **Không bảo đảm ghi đè khi đường dẫn đích đã tồn tại.** Có hệ thống cho phép trong một số trường hợp, có hệ thống từ chối; không coi replace là hợp đồng chung.
4. **Không bảo đảm tự tạo thư mục cha của đích.** Phải chuẩn bị đường dẫn cha riêng.
5. **Không cập nhật chính đối tượng File nguồn.** File là đối tượng biểu diễn đường dẫn bất biến: **source** vẫn giữ tên cũ sau một lần rename thành công, còn **destination** giữ tên mới.
6. **Không tự ném IOException diễn giải mọi lỗi thất bại.** Đối với nhiều lỗi rename, phương thức chỉ trả **false**; SecurityException vẫn có thể xuất hiện do kiểm soát quyền.

Nếu renameTo trả true, có thể sử dụng đối tượng **destination** để thao tác với đường dẫn mới. Nếu trả false, **không tiếp tục như thể thao tác đã thành công**; cần kiểm tra trạng thái thực tế và xử lý theo hợp đồng của ứng dụng.

### 6.2. API thay thế: Files.move(...)

Nên cân nhắc **Files.move(sourcePath, destinationPath)** khi cần exception rõ nghĩa hơn:

~~~java
Path sourcePath = Path.of("data", "old.txt");
Path destinationPath = Path.of("data", "new.txt");

Files.move(sourcePath, destinationPath);
~~~

Đây là **mảnh minh họa**, cần import **java.nio.file.Files**, **java.nio.file.Path** và xử lý **IOException**. Mặc định, với đường dẫn đích đã tồn tại, Files.move thường báo lỗi; khi cần thay thế có thể chỉ định **StandardCopyOption.REPLACE_EXISTING** và chấp nhận chính sách thay thế rõ ràng.

Nếu nghiệp vụ yêu cầu đổi tên **nguyên tử**, có thể thử **StandardCopyOption.ATOMIC_MOVE**. Hệ thống file không hỗ trợ có thể ném **AtomicMoveNotSupportedException**; **không** được tự mặc định rằng một lần move không có ATOMIC_MOVE cũng nguyên tử. Thứ tự xử lý khi kết hợp option, tài nguyên đang mở và quy tắc ghi đè phụ thuộc hợp đồng cụ thể của Files.move và filesystem, vì vậy cần xác định rõ điều kiện trước khi triển khai.

## 7. delete(): xóa file hoặc thư mục rỗng, không xóa đệ quy

Chữ ký:

~~~java
public boolean delete()
~~~

**delete()** trả true **chỉ nếu thao tác xóa thành công**; trả false nếu không xóa được. Đường dẫn có thể trỏ đến:

- **File thường**: delete yêu cầu xóa file, tùy quyền và quy tắc của OS.
- **Thư mục rỗng**: có thể xóa.
- **Thư mục còn file/thư mục con**: **không được xóa bằng File.delete()**; trả false.
- **Đường dẫn không tồn tại**: thường trả false.

Ví dụ:

~~~java
File file = new File("data/report.txt");
if (!file.delete()) {
    System.err.println("Chưa xóa được: " + file);
}
~~~

Đây là **mảnh code minh họa**. Trả false không nói rõ do file không tồn tại, file còn mở trên một số hệ điều hành, thiếu quyền hay lý do khác. Các trường hợp làm việc với liên kết tượng trưng (**symbolic link**) cần chú ý ý nghĩa xóa đường dẫn/entry và không được suy diễn “xóa mục này” tức là xóa toàn bộ nội dung mà symlink trỏ đến.

**File.delete() không có chế độ recursive**. Muốn xóa cây thư mục, ứng dụng phải có quy trình duyệt và xóa có kiểm soát, thường theo thứ tự **con trước cha**; đây là thao tác nguy hiểm với dữ liệu người dùng nên cần giới hạn đường dẫn và tránh symlink escape.

### 7.1. So sánh với Files.delete và Files.deleteIfExists

~~~java
Files.delete(path);
~~~

- **Files.delete(path)** xóa đường dẫn, có thể ném **NoSuchFileException** nếu thiếu hoặc **DirectoryNotEmptyException** nếu thư mục không rỗng (khả năng báo lỗi cụ thể phụ thuộc hệ thống file).
- **Files.deleteIfExists(path)** trả **false** nếu không tồn tại; vẫn có thể ném **IOException** cho các lý do khác.
- Cả hai **không tự biến thành xóa đệ quy**.
- Cần xử lý đặc biệt khi dữ liệu quan trọng: không thử xóa hàng loạt chỉ vì một phương thức trả false.

### 7.2. deleteOnExit() không phải thay thế cho delete()

**File.deleteOnExit()** đăng ký yêu cầu xóa khi JVM kết thúc **bình thường**, không xóa ngay lúc gọi. Không được dựa vào nó để bảo đảm dọn sạch sau crash hay khi tiến trình bị kill; với ứng dụng chạy lâu, số lượng đăng ký cũng có thể tăng và không giải phóng như một cơ chế quản lý bộ nhớ thông thường. Với dữ liệu tạm quan trọng, nên dọn ngay trong **finally** hoặc try-with-resources thích hợp.

## 8. Ví dụ Java 17+ độc lập, tạo trong thư mục tạm an toàn

Để không xóa file thực tế của người học, chương trình dưới đây tạo **một thư mục tạm mới** rồi minh họa đủ năm phương thức. Tên thư mục tạm ngẫu nhiên nên **không in đường dẫn cụ thể**. Chương trình chỉ thao tác với tài nguyên tự tạo và có **finally** dọn dẹp nếu phát sinh lỗi.

Lưu thành **LegacyFileMethodsDemo.java**:

~~~java
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;

public class LegacyFileMethodsDemo {
    public static void main(String[] args) throws IOException {
        File root = Files.createTempDirectory("legacy-file-demo-").toFile();

        File single = new File(root, "single");
        File nested = new File(root, "a/b/c");
        File source = new File(single, "old.txt");
        File destination = new File(single, "new.txt");

        try {
            System.out.println("mkdir=" + single.mkdir());

            // Cha "a/b" chưa có: mkdir() chỉ tạo 1 cấp.
            System.out.println("nested.mkdir=" + nested.mkdir());
            System.out.println("nested.mkdirs=" + nested.mkdirs());
            System.out.println("nested.mkdirs again=" + nested.mkdirs());

            System.out.println("createNewFile=" + source.createNewFile());
            System.out.println("createNewFile again=" + source.createNewFile());

            boolean moved = source.renameTo(destination);
            if (!moved) {
                throw new IOException("renameTo thất bại trên filesystem này");
            }
            System.out.println("renameTo=" + moved);

            // Root còn con nên không được xóa bằng delete().
            System.out.println("root.delete nonempty=" + root.delete());

            System.out.println("destination.delete=" + destination.delete());
            System.out.println("single.delete=" + single.delete());
            System.out.println("nested.delete=" + nested.delete());
            System.out.println("b.delete=" + nested.getParentFile().delete());
            System.out.println("a.delete=" +
                    nested.getParentFile().getParentFile().delete());
            System.out.println("root.delete=" + root.delete());
        } finally {
            // Dọn tài nguyên tự tạo nếu lỗi khiến một số thư mục còn lại.
            if (root.exists()) {
                try (Stream<Path> paths = Files.walk(root.toPath())) {
                    for (Path path :
                            paths.sorted(Comparator.reverseOrder()).toList()) {
                        Files.deleteIfExists(path);
                    }
                }
            }
        }
    }
}
~~~

Lệnh:

~~~bash
javac LegacyFileMethodsDemo.java
java LegacyFileMethodsDemo
~~~

**Stdout trên một filesystem cục bộ bình thường**, khi quyền tạo/xóa hợp lệ và **renameTo** trong cùng thư mục thành công:

~~~text
mkdir=true
nested.mkdir=false
nested.mkdirs=true
nested.mkdirs again=false
createNewFile=true
createNewFile again=false
renameTo=true
root.delete nonempty=false
destination.delete=true
single.delete=true
nested.delete=true
b.delete=true
a.delete=true
root.delete=true
~~~

**Các giá trị trong stdout trên là kết quả dự kiến trong môi trường hợp lệ, không phải cam kết rằng mọi filesystem luôn cho cùng kết quả**: đặc biệt **renameTo** có thể thất bại; code chủ động báo IOException thay vì in “thành công” giả. Thư mục tạm được tạo độc nhất, nên không trùng với thư mục của lần chạy trước. Dọn dẹp trong **finally** dùng Files.walk với thứ tự đảo để xóa con trước cha, chỉ trong **root** của lần chạy; khi một path không thể xóa, chương trình vẫn có thể ném IOException khi cleanup. Đây là ví dụ kỹ thuật, không phải bộ xóa thư mục tùy ý do người dùng nhập.

Phân tích lần lượt:

1. **single.mkdir()** tạo thư mục một cấp dưới root → true.
2. **nested.mkdir()** thất bại vì **a/b** chưa có → false.
3. **nested.mkdirs()** tạo **a**, **b**, **c** → true. Gọi lại khi c đã tồn tại → false.
4. **source.createNewFile()** tạo file rỗng, lần thứ hai không tạo thêm → true rồi false.
5. **source.renameTo(destination)** đổi tên trong cùng thư mục; nếu true, file nằm ở đường dẫn destination.
6. **root.delete()** khi root chưa rỗng → false.
7. Xóa file và thư mục theo thứ tự từ trong ra ngoài → từng lời gọi trả true trong trường hợp thành công.

## 9. Khi trả false, nên chẩn đoán và xử lý thế nào?

Trước hết, không nên gộp tất cả false thành một loại lỗi. Dưới đây là **câu hỏi kiểm tra**, không phải phép suy luận chắc chắn vì trạng thái hệ thống file có thể thay đổi đồng thời.

| Lệnh trả false | Khả năng cần kiểm tra |
| --- | --- |
| **mkdir()** | Cha đã tồn tại? Đích đã tồn tại? Có quyền tạo thư mục? |
| **mkdirs()** | Đích là thư mục sẵn có? Một cấp cha lại là file? Có phần cây đã được tạo một phần? |
| **createNewFile()** | Theo hợp đồng: tên đích đã tồn tại; lỗi tạo file khác thường ném IOException |
| **renameTo()** | Đích đã tồn tại? Chuyển khác filesystem? Hạn chế nền tảng/quyền? |
| **delete()** | Mục tiêu còn tồn tại? Là thư mục không rỗng? Thiếu quyền? File bị khóa? |

**Không dùng exists() rồi kết luận chắc chắn về nguyên nhân thất bại**: giữa các lần gọi, một tiến trình khác có thể thay đổi trạng thái. Nếu cần thông tin chẩn đoán, chuyển sang API Files có ngoại lệ cụ thể sẽ hiệu quả hơn việc cố đoán từ boolean.

Với mỗi thao tác, ứng dụng cần xác định **hậu điều kiện mong muốn**:

- Nếu mục tiêu là **“thư mục phải tồn tại”**, xác minh **isDirectory()** (hoặc dùng Files.createDirectories).
- Nếu mục tiêu là **“phải tạo file mới, không đè cái cũ”**, dựa vào kết quả **createNewFile()** hoặc dùng chế độ **CREATE_NEW**.
- Nếu mục tiêu là **“đã di chuyển thành công”**, kiểm tra **renameTo() == true** rồi tiếp tục với **đường dẫn mới**; với yêu cầu chặt chẽ hơn, dùng Files.move.
- Nếu mục tiêu là **“đã xóa thành công”**, kiểm tra **delete() == true** hoặc dùng Files.delete và xử lý IOException.

## 10. java.io.File so với java.nio.file.Files: chọn API nào?

**java.io.File** vẫn rất thường gặp trong codebase cũ, thư viện lâu đời và API cần kiểu File. Tuy nhiên, với Java 17, **Path/Files** thường rõ ràng hơn về lỗi và tùy chọn.

| Tác vụ | File truyền thống | java.nio.file.Files |
| --- | --- | --- |
| Tạo **một** thư mục | **file.mkdir()** | **Files.createDirectory(path)** |
| Tạo thư mục với cha còn thiếu | **file.mkdirs()** | **Files.createDirectories(path)** |
| Tạo file rỗng chỉ khi chưa tồn tại | **file.createNewFile()** | **Files.createFile(path)** |
| Đổi tên/di chuyển | **source.renameTo(dest)** | **Files.move(source, dest, options...)** |
| Xóa file/thư mục rỗng | **file.delete()** | **Files.delete(path)** |
| Xóa nếu có, không báo lỗi khi thiếu | Kiểm tra giá trị boolean của delete, nhưng không phân biệt nguyên nhân | **Files.deleteIfExists(path)** |
| Chuyển biểu diễn | **file.toPath()** | **path.toFile()** (với Path thuộc filesystem hỗ trợ) |

Ví dụ minh họa cách làm hiện đại, giả định đã import **java.nio.file.*** và **java.io.IOException**:

~~~java
Path base = Path.of("data");
Files.createDirectories(base.resolve("reports"));

Path a = Files.createFile(base.resolve("reports").resolve("a.txt"));
Path b = base.resolve("reports").resolve("b.txt");

Files.move(a, b);          // Nếu không thành công sẽ báo IOException.
Files.delete(b);           // Nếu không xóa được sẽ báo IOException.
~~~

Đây là **mảnh code**, không phải chương trình tự chạy: nó giả định quyền truy cập phù hợp, thư mục làm việc chứa vị trí "data" và file đích **b.txt** chưa tồn tại. Chạy lại khi a.txt/b.txt có trạng thái khác có thể cho kết quả khác. Ví dụ nhằm minh họa API, không mô tả thao tác an toàn để áp dụng trên dữ liệu thật khi chưa xác nhận tên đích.

**Files.createDirectories(...)** phù hợp để chuẩn bị directory idempotent hơn: khi thư mục đích đã tồn tại đúng loại, lệnh thường hoàn tất mà không coi đó là thất bại. Nhưng **nếu có file thường chiếm tên thư mục**, việc tạo vẫn thất bại. Trên một số nền tảng, thao tác tạo cây có thể tạo được một phần trước khi lỗi; không tự coi đó là giao dịch.

## 11. An toàn dữ liệu và race condition

### 11.1. Tránh kiểm tra rồi thao tác như một giao dịch

Ví dụ không an toàn trước cạnh tranh:

~~~java
if (!file.exists()) {
    file.createNewFile();
}
~~~

Một tiến trình khác có thể tạo file ngay sau **exists()**. Khi cần tạo duy nhất, **createNewFile()** thực hiện kiểm tra và tạo cùng một thao tác; nếu đồng thời cần mở file để ghi, cân nhắc Files.newOutputStream với **CREATE_NEW**.

Tương tự, **isDirectory()** trước **mkdir()** hoặc **exists()** trước **delete()** chỉ là ảnh chụp trạng thái tại một thời điểm. Không thể lấy các phép kiểm tra này để tuyên bố đường dẫn “chắc chắn” không đổi trong ứng dụng nhiều tiến trình.

### 11.2. Không xóa/đổi tên dựa trên đường dẫn chưa xác thực

Với tên file lấy từ đầu vào người dùng, **đừng ghép trực tiếp chuỗi rồi xóa**, bởi các thành phần như **..**, đường dẫn tuyệt đối, symlink hoặc bất đồng giữa chuẩn hóa đường dẫn có thể làm thao tác ảnh hưởng đến nơi ngoài phạm vi dự định. Xác thực phạm vi truy cập ở tầng thích hợp, tránh xóa đệ quy tùy tiện; nếu cần thao tác an toàn trước race/symlink, cân nhắc API và thiết kế có cơ chế kiểm soát quyền thật sự.

Đối với file quan trọng, có thể ghi nội dung vào **file tạm trong cùng filesystem**, hoàn tất flush/đồng bộ khi cần rồi mới **Files.move(...)** theo hợp đồng thay thế phù hợp. **Không khẳng định mọi hệ thống đều hỗ trợ atomic move**; phải xử lý trường hợp không hỗ trợ.

### 11.3. Thư mục không rỗng và tài nguyên đang mở

Một số hệ điều hành hạn chế đổi tên hoặc xóa file đang được chương trình khác mở. Ngay cả khi API trả true, việc hiển thị trạng thái sau thao tác có thể chịu ảnh hưởng caching hoặc race từ bên ngoài. Để tránh mất dữ liệu, nên dùng **try-with-resources** cho I/O stream và kiểm tra kết quả các thao tác file.

**SecurityException** là ngoại lệ do cơ chế kiểm soát quyền trong những môi trường có SecurityManager/chính sách tương ứng, khác với **IOException**. API boolean không có nghĩa là không bao giờ phát sinh exception nào.

## 12. Lỗi thường gặp và cách tránh

1. **Tưởng new File(...) tự tạo file trên đĩa.** Constructor chỉ tạo đối tượng đường dẫn; phải gọi API tạo.
2. **Dùng mkdir() cho đường dẫn nhiều cấp có cha chưa tồn tại.** Dùng mkdirs() hoặc Files.createDirectories.
3. **Xem mkdirs() == false đồng nghĩa thư mục chắc chắn không tồn tại.** Nó thường false khi đích đã có; kiểm tra hậu điều kiện hoặc dùng Files.createDirectories.
4. **Tin mkdirs() thất bại thì không tạo ra gì.** Có thể đã tạo một phần cây, cần dọn hoặc khôi phục có kiểm soát.
5. **Gọi createNewFile() rồi cho rằng đã ghi dữ liệu.** File mới rỗng; ghi nội dung bằng OutputStream, Files.write... nếu cần.
6. **Viết exists() rồi createNewFile() như kiểm tra nguyên tử.** Kết quả exists có thể cũ; ưu tiên hợp đồng tạo mới nguyên tử.
7. **Không kiểm tra boolean từ renameTo().** Nó có thể false do filesystem hoặc đích tồn tại; không giả định rename luôn thành công.
8. **Sau renameTo thành công vẫn dùng File nguồn như thể đường dẫn đã tự đổi.** Đối tượng File nguồn vẫn giữ path cũ; dùng File dest.
9. **Dùng renameTo như cơ chế thay thế nguyên tử đa nền tảng.** Không được bảo đảm; cân nhắc Files.move với option tường minh.
10. **Thử file.delete() trên thư mục còn con.** Chỉ xóa được thư mục rỗng; delete không recursive.
11. **Tưởng File.delete() sẽ giải thích chi tiết lỗi.** Nó thường chỉ trả false; Files.delete có IOException hữu ích hơn.
12. **Xóa từ cha trước khi xóa con.** Muốn dọn cây tự tạo, phải xóa con trước cha, và phải giới hạn đúng phạm vi.
13. **Dùng deleteOnExit() thay cho dọn dẹp chắc chắn.** Nó không bảo đảm chạy khi JVM bị dừng bất thường.
14. **Hard-code dấu phân cách đường dẫn.** Dùng **new File(parent, child)** hoặc **Path.resolve**.
15. **Không cân nhắc chạy lại chương trình.** Lần thứ hai, file/thư mục có thể đã tồn tại; kết quả boolean thay đổi hợp lệ.
16. **Thử xóa hoặc đổi tên đường dẫn do người khác cung cấp mà chưa xác thực.** Có thể gây mất dữ liệu hoặc thao tác ra ngoài vùng cho phép.

## 13. Câu hỏi ôn tập

**Câu 1.** Có thư mục **data** nhưng chưa có **data/2026**. Lệnh nào phù hợp hơn để tạo **data/2026/reports** trong một lần?  
**Đáp:** **mkdirs()**; nó tạo cả cha còn thiếu. **mkdir()** không tự tạo data/2026.

**Câu 2.** Vì sao **mkdirs()** lần thứ hai thường trả false nhưng **Files.createDirectories()** có thể hoàn tất?  
**Đáp:** mkdirs trả true khi thực sự tạo thư mục đích cùng cha cần thiết trong lần gọi; Files.createDirectories cho phép đường dẫn đích đã tồn tại đúng loại mà không coi đó là lỗi.

**Câu 3.** **createNewFile()** trả false có nghĩa đã tạo được file nhưng không ghi dữ liệu?  
**Đáp:** Không. Theo hợp đồng, false nghĩa tên đích **đã tồn tại**. Khi vừa tạo mới thành công, kết quả là true và file ban đầu rỗng.

**Câu 4.** **renameTo()** có luôn đổi được tên file giữa hai ổ đĩa không?  
**Đáp:** Không. Nó phụ thuộc nền tảng và filesystem; phải kiểm tra boolean hoặc dùng Files.move để xử lý lỗi/tùy chọn rõ hơn.

**Câu 5.** Sau **source.renameTo(dest)** thành công, **source** có tự trỏ đến tên mới không?  
**Đáp:** Không. File đại diện cho đường dẫn bất biến; **source** vẫn mang đường dẫn cũ, còn **dest** là biểu diễn đích.

**Câu 6.** Có thư mục chứa file; gọi **directory.delete()** có xóa mọi thứ bên trong không?  
**Đáp:** Không. File.delete không recursive và chỉ có thể xóa thư mục rỗng.

**Câu 7.** Muốn biết lý do xóa thất bại, nên dùng API nào?  
**Đáp:** **Files.delete(path)** với IOException cụ thể, thay vì chỉ dựa trên giá trị boolean của File.delete.

**Câu 8.** Nếu cần tạo file chỉ khi chưa tồn tại **và mở ngay để ghi**, API nào đáng cân nhắc?  
**Đáp:** **Files.newOutputStream(path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)** để áp dụng điều kiện tạo mới ngay khi mở luồng.

## 14. Tổng kết

- **mkdir()**: tạo đúng **một** thư mục, không tự tạo cha.
- **mkdirs()**: tạo cả **các thư mục cha còn thiếu**, nhưng có thể để lại cây tạo dở khi lỗi.
- **createNewFile()**: **tạo file rỗng nếu chưa tồn tại**, trả false nếu tên đã có; việc kiểm tra và tạo là một thao tác nguyên tử.
- **renameTo(dest)**: yêu cầu đổi tên/di chuyển, **phụ thuộc nền tảng**, không bảo đảm nguyên tử hoặc ghi đè; đối tượng File nguồn không đổi đường dẫn.
- **delete()**: xóa **file hoặc thư mục rỗng**, không tự xóa đệ quy; trả false nếu không xóa được.

Trong code mới, **Path + Files** thường là lựa chọn nên ưu tiên khi cần xử lý lỗi đầy đủ, tùy chọn rõ ràng hoặc thao tác an toàn hơn. Dù dùng API nào, hãy kiểm tra hậu điều kiện, tránh xóa dữ liệu ngoài phạm vi và nhận thức rằng hệ thống file có thể thay đổi đồng thời.

### Tham khảo chính thức

- [Oracle Java SE 17 — java.io.File](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html): mkdir, mkdirs, createNewFile, renameTo, delete, deleteOnExit và kết quả boolean.
- [Oracle Java SE 17 — java.nio.file.Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): createDirectory, createDirectories, createFile, move, delete, deleteIfExists.
- [Oracle Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): CREATE_NEW và các tùy chọn mở file.
- [Oracle Java SE 17 — StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): REPLACE_EXISTING và ATOMIC_MOVE.
