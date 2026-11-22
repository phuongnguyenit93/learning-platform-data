# Chạy mã nguồn trực tiếp bằng `java` launcher (Java 11+)

## 1. Mục tiêu và ý nghĩa

Từ **Java 11**, lệnh `java` hỗ trợ **source-file mode** (chế độ chạy trực tiếp mã nguồn): đưa đường dẫn một tệp `.java` cho `java`, chương trình sẽ được **biên dịch trong bộ nhớ rồi chạy ngay** mà không cần tự thực hiện bước `javac` trước đó.

```bash
java QuickReport.java
```

Đây là khả năng của **Java launcher**, được giới thiệu bằng **JEP 330** và **vẫn được hỗ trợ trong các JDK hiện đại**. Nó phù hợp để thử API, minh họa bài học, làm công cụ dòng lệnh nhỏ và chạy thử một chương trình đơn giản. Chương trình vẫn là Java được biên dịch và thực thi trên JVM; đây **không phải** Java interpreter chạy từng dòng mã nguồn.

Cần phân biệt:

- `java QuickReport.java`: truyền **tệp nguồn**; launcher tự biên dịch và chạy theo source-file mode.
- `javac QuickReport.java` rồi `java QuickReport`: biên dịch thành các tệp `.class` trên đĩa trước, sau đó chạy lớp đã biên dịch.
- `java QuickReport`: truyền **tên lớp**, không truyền tên tệp nguồn; yêu cầu lớp đã được biên dịch và có thể tìm thấy trong classpath/module path.

Tính năng được giới thiệu cho **một tệp nguồn ở Java 11**; từ **JDK 22**, **JEP 458** mở rộng cơ chế này để có thể biên dịch những tệp nguồn phụ thuộc khác theo cấu trúc source tree. Khi học Java 11, hãy bắt đầu với một tệp độc lập như ví dụ bên dưới.

## 2. Điều kiện và cú pháp

Cần sử dụng **JDK 11 trở lên** có công cụ launcher và trình biên dịch đi kèm. Kiểm tra trong terminal:

```bash
java -version
javac -version
```

Hai lệnh giúp xác nhận JDK đang được sử dụng. Nếu hệ thống có nhiều JDK, kiểm tra đường dẫn `java`/`javac` trong `PATH` để tránh chạy nhầm phiên bản.

Cú pháp thông dụng:

```text
java [tùy_chọn_của_JVM/launcher] DuongDan/TenTep.java [tham_số_của_chương_trình]
```

Ví dụ:

```bash
java QuickReport.java Lan
java --source 11 QuickReport.java Lan
java -Xmx128m QuickReport.java Lan
```

- Tệp `.java` có sẵn, là đối số đầu tiên không thuộc tùy chọn của launcher thì `java` tự nhận ra **source-file mode**; không cần thêm `--source` trong trường hợp thông thường.
- `--source 11` yêu cầu biên dịch nguồn theo **ngôn ngữ và API Java 11** (khi JDK đang chạy còn hỗ trợ mức nguồn đó). Nó **không chuyển JVM hiện hành thành JVM 11** và không thay cho việc thử chương trình trên một JDK 11 thực tế.
- Tùy chọn của `java` như `-Xmx128m` hoặc `--source 11` đặt **trước** tên tệp; những giá trị **sau** tên tệp thuộc về `String[] args` của chương trình.
- Nếu tên tệp không kết thúc bằng `.java`, phải dùng `--source` để yêu cầu source-file mode; đây là trường hợp bổ sung, không cần cho bài học cơ bản.

## 3. Ví dụ hoàn chỉnh: chạy một tệp chứa nhiều lớp

Tạo tệp **`QuickReport.java`** với đúng nội dung sau (Java 11+):

```java
public class QuickReport {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "friend";
        System.out.println("Hello, " + name + "!");
        System.out.println("Sum: " + MathHelper.add(6, 7));
    }
}

class MathHelper {
    static int add(int a, int b) {
        return a + b;
    }
}
```

Mở terminal tại thư mục chứa tệp và chạy:

```bash
java QuickReport.java Lan
```

**Đầu ra chính xác:**

```text
Hello, Lan!
Sum: 13
```

Giải thích:

1. `java` nhận đường dẫn `QuickReport.java` nên biên dịch nguồn bằng cơ chế source-file mode.
2. `QuickReport` là **lớp top-level đầu tiên** trong tệp và có phương thức `public static void main(String[] args)`, nên đây là điểm vào của chương trình.
3. `Lan` đứng sau tên tệp, do đó `args[0]` bằng `"Lan"`. Khi không truyền tên, chương trình dùng giá trị mặc định `"friend"` và vẫn chạy bình thường.
4. `MathHelper` được khai báo **trong cùng tệp nguồn**, nên có thể được biên dịch và dùng trực tiếp, dù nó không phải lớp khởi chạy.
5. Launcher nạp và thực thi các lớp đã biên dịch. Trong lần chạy bằng source-file mode này, **không có `QuickReport.class` hoặc `MathHelper.class` mới được ghi vào thư mục làm việc**.

Cũng có thể yêu cầu mức nguồn Java 11 một cách tường minh:

```bash
java --source 11 QuickReport.java Lan
```

Lệnh trên cho **cùng đầu ra** vì ví dụ chỉ dùng cú pháp và API có trong Java 11.

> **Quy tắc quan trọng:** Nếu một tệp nguồn có nhiều lớp top-level, launcher chọn **lớp top-level đầu tiên trong tệp** để khởi chạy. Không được đặt lớp tiện ích không có `main` ở đầu tệp rồi mặc định nghĩ launcher sẽ tự tìm lớp có `main` ở dưới. Để rõ ràng, đặt lớp có `main` lên đầu.

## 4. Phân biệt với cách biên dịch và chạy truyền thống

Sau khi chạy thử trực tiếp, nếu cần sinh `.class` để lưu lại hoặc dùng trong quy trình build, biên dịch bằng `javac`:

```bash
javac --release 11 QuickReport.java
java QuickReport Lan
```

Đầu ra vẫn là:

```text
Hello, Lan!
Sum: 13
```

Với ví dụ này, `javac` tạo các tệp `QuickReport.class` và `MathHelper.class` (một tệp cho mỗi lớp top-level), và lệnh `java QuickReport Lan` chạy lại bytecode đã được tạo.

| Tiêu chí | `java QuickReport.java Lan` | `javac QuickReport.java` rồi `java QuickReport Lan` |
| --- | --- | --- |
| Đầu vào để chạy | Đường dẫn **tệp nguồn** | **Tên lớp** đã biên dịch |
| Biên dịch | Launcher thực hiện tự động trước khi chạy | Thực hiện tường minh bằng `javac` |
| Sinh tệp `.class` trong thư mục làm việc | Không, đối với mã nguồn biên dịch trong source-file mode | Có, theo đầu ra cấu hình của `javac` |
| Khi thích hợp | Chạy nhanh, thử mã, công cụ nhỏ | Dự án cần artifact, nhiều bước kiểm thử/build, quy trình phát hành |

Vì source-file mode vẫn cần biên dịch trước mỗi lần gọi, nó có thể tăng thời gian khởi động so với chạy bytecode đã biên dịch. Với ứng dụng lớn, phụ thuộc phức tạp hoặc quy trình release, nên dùng build tool như Gradle/Maven theo cấu trúc dự án thực tế.

## 5. Hiểu đúng cơ chế source-file mode

### 5.1. Chọn chế độ chạy

Khi lệnh nhận tệp nguồn `.java` tồn tại ở vị trí ứng dụng cần chạy, launcher chọn source-file mode. Nếu bỏ phần mở rộng:

```bash
java QuickReport Lan
```

thì launcher hiểu `QuickReport` là **tên lớp**, không phải tên `QuickReport.java`. Lệnh này sẽ không chạy thành công trong thư mục chỉ có mã nguồn và chưa có `.class` tương ứng.

### 5.2. Biên dịch trong bộ nhớ và xử lý lỗi

Launcher biên dịch mã nguồn trước, sau đó nạp lớp và chạy `main`. Nếu mã nguồn có lỗi cú pháp/kiểu, quá trình dừng với thông báo lỗi biên dịch và mã thoát khác 0; phương thức `main` chưa được gọi. Việc chạy bằng `java File.java` **không bỏ qua bước kiểm tra kiểu tĩnh** của Java.

Một tệp nguồn có thể chứa nhiều lớp top-level phụ trợ. Với Java 11–21, source-file mode **không tự tìm và biên dịch tệp nguồn `.java` khác chỉ vì tệp đó nằm cạnh tệp đang chạy**; để tương thích Java 11, hãy đặt các lớp phụ trợ nhỏ trong cùng tệp, hoặc dùng các lớp/thư viện đã biên dịch sẵn trên classpath.

**Cập nhật còn áp dụng hiện nay:** Từ **JDK 22**, khả năng **multi-file source programs** cho phép launcher tìm và biên dịch các tệp nguồn phụ thuộc trong một source tree với đường dẫn phù hợp package (JEP 458). Đây là **phần mở rộng**, không phải khả năng sẵn có của Java 11. Vì vậy, không nên áp dụng kết luận “launcher không hỗ trợ nhiều tệp nguồn” cho mọi phiên bản JDK hiện đại.

### 5.3. Điểm vào và tên lớp

Với mã tương thích Java 11, dùng điểm vào truyền thống:

```java
public static void main(String[] args)
```

Trong source-file mode, lớp top-level đầu tiên được xem là lớp khởi chạy. Việc chọn lớp **không dựa vào tên tệp**. Tuy quy tắc tên `public class` và tệp nguồn có thể được nới trong riêng trường hợp khởi chạy trực tiếp, vẫn nên đặt **tên tệp trùng tên lớp `public`** để mã rõ ràng và dùng được trong cách biên dịch truyền thống.

### 5.4. Tùy chọn JVM, tham số chương trình và classpath

Thứ tự đối số rất quan trọng:

```bash
# JVM nhận giới hạn bộ nhớ; chương trình nhận args[0] = "Lan".
java -Xmx128m QuickReport.java Lan

# Chuỗi "-Xmx128m" lúc này là đối số của chương trình, không phải tùy chọn JVM.
java QuickReport.java -Xmx128m
```

Nếu mã dùng các thư viện bên ngoài đã được biên dịch, có thể cấu hình classpath **trước** tên tệp nguồn, ví dụ:

```bash
java --class-path "lib/*" QuickReport.java Lan
```

`lib/*` là ví dụ quy ước chỉ các JAR trong thư mục `lib`, không cần thiết cho `QuickReport.java` vì ví dụ chỉ sử dụng Java chuẩn. Chỉ thêm classpath khi có phụ thuộc thực. Source-file mode không tự tải dependency từ Maven Central hay tự thực hiện thay việc quản lý phụ thuộc của Gradle/Maven.

## 6. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `java QuickReport.java` không được nhận diện như tệp nguồn | Đang dùng JDK trước Java 11 hoặc chạy nhầm `java` trên `PATH` | Kiểm tra `java -version`, chọn JDK 11+ |
| `Could not find or load main class QuickReport` | Dùng `java QuickReport` khi chưa biên dịch hoặc classpath không chứa `.class` | Đổi sang `java QuickReport.java` hoặc biên dịch bằng `javac` rồi chạy tên lớp |
| Lỗi “main method not found” | Lớp top-level đầu tiên không có điểm vào hợp lệ | Đặt lớp cần chạy lên đầu và khai báo `public static void main(String[] args)` để tương thích Java 11 |
| Không tìm thấy lớp định nghĩa trong tệp `Helper.java` bên cạnh | JDK 11–21 không tự biên dịch tệp nguồn phụ thuộc ở chế độ này | Ghép helper nhỏ vào cùng tệp hoặc biên dịch dependency trước; với JDK 22+ có thể dùng multi-file source mode khi đúng bố cục |
| Tìm thấy tệp `.java` nhưng lỗi cú pháp hoặc lỗi kiểu | Launcher vẫn phải biên dịch trước khi chạy | Sửa lỗi compiler nêu ở dòng tương ứng; thử `javac` nếu cần xem lỗi rõ hơn |
| Truyền `--source` hoặc `-Xmx` sau tên tệp | Đối số sau tên tệp được đưa vào `main(String[] args)` | Chuyển tùy chọn launcher lên trước tên tệp |
| Dùng `--source 11` nhưng không chạy được cú pháp/API mới hơn | Đang giới hạn mức biên dịch về Java 11 | Dùng cú pháp/API của Java 11 hoặc thay đổi mức nguồn theo yêu cầu và khả năng hỗ trợ của JDK |
| Không thấy `.class` xuất hiện sau `java File.java` | Đây là hành vi bình thường của source-file mode | Dùng `javac` nếu muốn sinh bytecode ra đĩa |

**Chú ý về môi trường:** Đối với JDK 11 trên các hệ điều hành có cấu hình mã hóa ký tự khác nhau, nguồn chứa ký tự ngoài ASCII có thể cần điều chỉnh encoding. Ví dụ ở trên dùng chuỗi ASCII để chạy nhất quán trên terminal Windows, macOS và Linux.

## 7. Áp dụng vào công việc học và phát triển

- **Học Java/kiểm tra API:** tạo một tệp với `main`, chạy `java File.java` và quan sát kết quả. Sửa nguồn rồi chạy lại ngay; không cần xóa `.class` vì source-file mode không tạo các tệp đó.
- **Công cụ dòng lệnh nhỏ:** nhận đối số qua `String[] args`, kiểm tra số tham số trước khi truy cập rồi xuất kết quả. Với mã cần phụ thuộc phức tạp, tổ chức nhiều gói, kiểm thử tự động và đóng gói, chuyển sang cấu trúc dự án có build tool.
- **Khi cần kiểm soát tương thích Java 11:** thử `java --source 11 File.java` với JDK hỗ trợ mức nguồn này và chạy xác nhận trên JDK 11 thật nếu mục tiêu vận hành là JDK 11. Tùy chọn `--source` kiểm soát biên dịch, không mô phỏng đầy đủ khác biệt runtime/JVM của JDK 11.
- **Khi đọc hướng dẫn mới:** nhận biết rằng Java 22+ đã có mở rộng multi-file source mode; ví dụ Java 11 trong bài này cố tình giữ mọi lớp cần thiết trong **một tệp** để nhất quán với chủ đề.

## 8. Tự kiểm tra

Từ tệp `QuickReport.java` ở mục 3, thử:

```bash
java QuickReport.java
java QuickReport.java Minh
```

Đầu ra tương ứng của lệnh thứ nhất:

```text
Hello, friend!
Sum: 13
```

Đầu ra của lệnh thứ hai:

```text
Hello, Minh!
Sum: 13
```

Câu hỏi: nếu đổi `java QuickReport.java Minh` thành `java QuickReport Minh` trong thư mục chỉ có tệp nguồn thì sao? **Trả lời:** khi không có `.class` khả dụng, launcher không tìm được lớp `QuickReport`; thêm `.java` để yêu cầu chạy tệp nguồn, hoặc dùng `javac` trước.

## 9. Ghi nhớ

**`java File.java [args]`** là lệnh khởi chạy mã nguồn trực tiếp được hỗ trợ từ Java 11 đến hiện nay: launcher biên dịch trong bộ nhớ, chọn lớp top-level đầu tiên làm điểm vào và truyền các đối số phía sau tên tệp vào `main`. Khi cần bytecode lưu ra đĩa, dùng `javac`. Khi dùng JDK 22+, lưu ý cơ chế đã được mở rộng để chạy chương trình từ nhiều tệp nguồn phụ thuộc.

**Tài liệu chính thức:** [JEP 330 — Launch Single-File Source-Code Programs](https://openjdk.org/jeps/330); [Oracle Java launcher — Using Source-File Mode](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#using-source-file-mode-to-launch-source-code-programs); [JEP 458 — Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458).