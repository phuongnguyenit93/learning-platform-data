# Java 7 — Quan hệ giữa cải tiến ngôn ngữ, thư viện chuẩn và JVM

## 1. Bức tranh tổng thể

Một phiên bản Java có thể cải tiến **ngôn ngữ**, **thư viện chuẩn** và **JVM** cùng lúc, nhưng ba phần này giải quyết ba loại vấn đề khác nhau. Hiểu ranh giới giữa chúng giúp đọc đúng một tính năng, chọn API phù hợp và chẩn đoán lỗi tương thích khi biên dịch hoặc chạy ứng dụng.

Bài này lấy các thay đổi gắn với Java 7 vẫn còn hữu ích trên JDK hiện đại để minh họa. Java 7 là bối cảnh xuất hiện tính năng, **không phải khuyến nghị sử dụng JDK 7 làm môi trường triển khai**. Các ví dụ chạy bằng JDK 17 trở lên; các dự án thực tế nên chọn bản JDK còn được hỗ trợ theo chính sách của mình.

| Lớp | Phụ trách điều gì? | Ví dụ liên quan Java 7 còn áp dụng |
| --- | --- | --- |
| **Ngôn ngữ Java** | Cú pháp, quy tắc kiểu, ngữ nghĩa của mã nguồn; trình biên dịch `javac` chuyển nguồn thành bytecode. | `switch` trên `String`, try-with-resources, diamond `<>`, multi-catch. |
| **Thư viện chuẩn Java SE** | Các lớp, interface và phương thức để chương trình gọi; API được trình biên dịch kiểm tra và được runtime cung cấp. | `AutoCloseable`, `Path`, `Files`, `ForkJoinPool`, `MethodHandle`. |
| **JVM** | Nạp/xác minh lớp, liên kết, thực thi bytecode (thông dịch và có thể JIT), quản lý bộ nhớ và tương tác với hệ thống. | Lệnh bytecode `invokedynamic` và cơ chế liên kết động; định dạng class file tương ứng. |

Luồng thực thi thường là:

```text
Tệp .java
   │  cú pháp và kiểm tra kiểu của ngôn ngữ + tra cứu API tại lúc biên dịch
   ▼
javac
   │  sinh .class chứa bytecode và tham chiếu đến class/method/field
   ▼
JVM nạp, xác minh, liên kết và thực thi bytecode
   │  khi gặp lời gọi thư viện: tìm implementation trong runtime
   ▼
Thư viện Java SE / nhà cung cấp hệ thống tệp / dịch vụ hệ điều hành
```

**Quy tắc quan trọng:** một tính năng nhìn từ mã nguồn có thể liên quan **nhiều lớp**, nhưng không phải mọi cú pháp mới hoặc API mới đều đòi một lệnh JVM mới. Ngược lại, JVM có thể bổ sung nền tảng để các phiên bản ngôn ngữ hoặc thư viện về sau sử dụng.

## 2. Cải tiến ngôn ngữ: thay đổi cách viết và cách biên dịch

### 2.1. `switch` trên `String`

```java
String mode = "read";

switch (mode) {
    case "read":
        System.out.println("Read mode");
        break;
    case "write":
        System.out.println("Write mode");
        break;
    default:
        System.out.println("Unknown mode");
}
```

- **Ngôn ngữ:** `switch` chấp nhận `String` và chọn nhánh theo giá trị chuỗi.
- **Thư viện:** trình biên dịch có thể dùng `String.hashCode()` và `String.equals()` để phân nhánh, kể cả khi có va chạm hash.
- **JVM:** vẫn thực thi bytecode thông thường như gọi phương thức và rẽ nhánh; **không có lệnh JVM riêng mang tên “string switch”**.
- Với cú pháp `switch` cổ điển này, biến `mode == null` làm phát sinh `NullPointerException`; nên xác định rõ cách xử lý `null`. Những dạng `switch` mới hơn có thêm khả năng riêng, không nên suy luận rằng mọi dạng đều có cùng quy tắc.

Điểm học được: **cú pháp được mở rộng không có nghĩa JVM cần thay đổi**; nhiều cải tiến được `javac` diễn dịch thành bytecode có sẵn.

### 2.2. Diamond `<>` và suy luận kiểu

```java
java.util.Map<String, Integer> counts = new java.util.HashMap<>();
counts.put("ok", 1);
System.out.println(counts.get("ok"));
```

`javac` suy ra đối số kiểu ở vế phải từ ngữ cảnh, giảm lặp khi viết generics. Việc này thuộc **kiểm tra kiểu lúc biên dịch**; không tạo cơ chế generic mới ở JVM. Do **type erasure**, đa số thông tin tham số kiểu không trở thành kiểu đối tượng riêng ở runtime. `<>` vẫn được sử dụng rộng rãi trong Java hiện đại.

### 2.3. Multi-catch và các cải tiến cú pháp khác

```java
try {
    // Thao tác có thể phát sinh IOException hoặc SecurityException
} catch (java.io.IOException | SecurityException e) {
    System.err.println(e.getMessage());
}
```

Multi-catch giúp gom cùng một cách xử lý cho nhiều kiểu ngoại lệ không có quan hệ kế thừa trực tiếp với nhau; biến ngoại lệ của multi-catch không được gán lại. Compiler sinh các mục xử lý ngoại lệ phù hợp trong class file; không cần “câu lệnh bắt nhiều ngoại lệ” mới trong JVM.

Các literal nhị phân (`0b1010`) và dấu gạch dưới trong literal số (`1_000_000`) cũng là ví dụ cú pháp vẫn hợp lệ: compiler hiểu và chuyển thành giá trị số bình thường, JVM không phải biết mã nguồn ban đầu đã dùng ký hiệu nào.

## 3. Tính năng phối hợp ngôn ngữ và thư viện: try-with-resources

Đây là trường hợp tiêu biểu cho sự kết hợp nhiều lớp:

1. **Ngôn ngữ:** `try (resource) { ... }` quy định tài nguyên được đóng khi rời khối, kể cả khi có ngoại lệ. Nhiều tài nguyên được đóng theo thứ tự ngược với thứ tự khai báo.
2. **Thư viện chuẩn:** kiểu tài nguyên phải triển khai `AutoCloseable` (hoặc `Closeable`, vốn mở rộng `AutoCloseable`). Phương thức `close()` định nghĩa hành động đóng.
3. **JVM:** chạy bytecode mà compiler sinh ra để gọi `close()` và xử lý ngoại lệ. **Không tồn tại opcode “try-with-resources”**.

```java
try (java.io.BufferedReader reader =
         new java.io.BufferedReader(new java.io.StringReader("A\nB"))) {
    System.out.println(reader.readLine());
    System.out.println(reader.readLine());
}
```

Với đoạn này, output là hai dòng `A` và `B`. `BufferedReader` đóng tự động sau khối `try`; không cần `finally` viết tay cho việc đóng reader.

**Ngoại lệ bị che khuất:** nếu phần thân `try` ném ngoại lệ và `close()` cũng ném ngoại lệ, ngoại lệ ở phần thân vẫn là ngoại lệ chính; ngoại lệ từ `close()` có thể lấy qua `Throwable.getSuppressed()`. Đây là lợi ích thực tế của cơ chế được hỗ trợ đồng thời bởi cú pháp và API ngoại lệ. Tuy nhiên, “đóng” phụ thuộc cách implementation của `AutoCloseable.close()` hoạt động; không mặc định có nghĩa là đã commit giao dịch hay giải phóng mọi tài nguyên ngoài hệ thống.

**Khi áp dụng:** ưu tiên try-with-resources cho stream, reader, writer, JDBC connection/statement/result set và các đối tượng có lifecycle phù hợp. Đừng giữ resource đang đóng để tiếp tục sử dụng ngoài phạm vi `try`.

## 4. Thư viện chuẩn có thể tiến hóa mà không cần cú pháp hoặc opcode mới

### 4.1. NIO.2: `Path` và `Files`

API `java.nio.file` cung cấp cách biểu diễn đường dẫn và thao tác tệp hiện vẫn hữu dụng:

- `Path` là một đối tượng đường dẫn do `FileSystem` cung cấp; không đơn giản chỉ là `String`.
- `Files` có phương thức tạo, đọc, ghi, sao chép, di chuyển, xóa tệp; có thể thao tác với metadata và duyệt cây thư mục bằng các API tương ứng.
- `FileSystemProvider` kết nối các thao tác trừu tượng với hệ thống tệp thực tế. Việc đọc/ghi cuối cùng dựa vào implementation và OS, không phải một opcode bytecode mới cho từng thao tác.

Không cần cú pháp Java mới để gọi `Files.readAllLines(path, charset)` hoặc `Files.newBufferedReader(path, charset)`. Compiler chỉ kiểm tra chữ ký API và tạo lời gọi phương thức; runtime tìm implementation tương ứng. Vì thế khi đánh giá một API, hãy phân biệt **nó có mặt ở JDK đích hay không** với **JVM có hỗ trợ bytecode hay không**.

### 4.2. `ForkJoinPool` và xử lý song song

`ForkJoinPool` là ví dụ cải tiến thư viện tương tác với khả năng thực thi đa luồng sẵn có của JVM. Nó quản lý các task và có kỹ thuật **work-stealing** để phân phối công việc. Bản thân việc bổ sung lớp này không tạo cú pháp ngôn ngữ mới và không đòi opcode “fork/join”.

Hãy dùng khi có công việc tính toán có thể tách thành tác vụ con phù hợp; cân nhắc đặc tính blocking, kích thước task, quản lý pool và tải thực tế. Nó **không làm mọi bài toán chạy nhanh hơn** chỉ vì số luồng tăng. Trong ứng dụng hiện đại, chọn giữa `ExecutorService`, `CompletableFuture`, `ForkJoinPool` hoặc cơ chế concurrency khác dựa trên kiểu công việc, thay vì mặc định chọn API xuất hiện trong Java 7.

## 5. JVM có thể mở đường cho tính năng ra đời sau: `invokedynamic`

Java 7 bổ sung opcode `invokedynamic` và hỗ trợ liên kết động liên quan đến `java.lang.invoke`, trong đó có `MethodHandle`, `CallSite` và bootstrap method. Đây là **thay đổi ở JVM/class file**: cách liên kết một call site có thể được quyết định bởi cơ chế bootstrap thay vì chỉ biểu diễn như lời gọi thông thường đến một phương thức xác định tĩnh.

Một ứng dụng hiện đại rất gần gũi là cách `javac` thường biên dịch biểu thức lambda, dù **lambda là tính năng ngôn ngữ được bổ sung sau Java 7**.

```java
public class LambdaLinkageDemo {
    public static void main(String[] args) {
        Runnable task = () -> System.out.println("Hello from Runnable");
        task.run();
    }
}
```

Lưu mã trên thành `LambdaLinkageDemo.java`, dùng JDK 17+:

```bash
javac --release 17 LambdaLinkageDemo.java
java LambdaLinkageDemo
javap -c -p LambdaLinkageDemo
```

Lệnh `java` in ra:

```text
Hello from Runnable
```

Trong bytecode `main` do `javac` thông thường sinh ra, `javap` cho thấy lời gọi `invokedynamic` để tạo `Runnable` từ lambda (cùng các cấu trúc phụ trợ khác). Kiểu chính xác của mã máy/JIT được tạo khi chạy là chi tiết implementation, không phải phần bảo đảm của mã nguồn Java.

Phân biệt ba ý:

- `invokedynamic` là **cơ chế bytecode/JVM**, không đồng nghĩa với từ khóa Java.
- `java.lang.invoke` là **API thư viện** để mô tả và thao tác với lời gọi/liên kết; code ứng dụng thông thường không buộc phải tự thao tác `CallSite`.
- Lambda là **cú pháp/ngữ nghĩa ở tầng ngôn ngữ**; compiler và runtime cùng triển khai ý nghĩa đó trên nền JVM phù hợp.

Điểm mấu chốt: **hạ tầng JVM có thể được bổ sung ở một phiên bản, rồi được các tính năng ngôn ngữ ở phiên bản sau tận dụng**. Không nên đồng nhất phiên bản xuất hiện của ba lớp.

## 6. Ví dụ hoàn chỉnh chạy trên JDK hiện đại

Ví dụ sau kết hợp hai cải tiến cú pháp có từ Java 7 (`switch` trên `String` và try-with-resources) với API NIO.2 (`Path`/`Files`). Nó vẫn là kiểu code hữu ích ngày nay.

Tạo tệp `Java7LayersDemo.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class Java7LayersDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("java7-layers-", ".txt");
        try {
            Files.write(path, Arrays.asList("language", "library"),
                    StandardCharsets.UTF_8);

            try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                String first = reader.readLine();

                switch (first) {
                    case "language":
                        System.out.println("language: String switch");
                        break;
                    default:
                        System.out.println("unexpected");
                }

                System.out.println("library: " + reader.readLine());
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn (ví dụ máy đang có JDK 17, 21 hoặc bản được hỗ trợ khác):

```bash
javac --release 17 Java7LayersDemo.java
java Java7LayersDemo
```

Khi thư mục tạm của hệ điều hành cho phép tạo tệp, stdout chính xác là:

```text
language: String switch
library: library
```

**Phân tích từng lớp:**

1. **Ngôn ngữ:** `switch (first)` chọn nhánh trên `String`; `try (BufferedReader ...)` tự động đóng reader khi rời scope. `javac` chịu trách nhiệm dịch các cấu trúc này.
2. **Thư viện:** `Files.createTempFile`, `Files.write`, `Files.newBufferedReader`, `Files.deleteIfExists` và `StandardCharsets.UTF_8` là API chuẩn. `BufferedReader` triển khai giao ước đóng tài nguyên.
3. **JVM:** nạp và chạy các lời gọi/nhánh/handler trong bytecode, dùng implementation của thư viện và hệ thống tệp. Không có opcode đặc biệt cho `Path` hay auto-close.
4. **Vòng đời tài nguyên:** reader được đóng trước khi cố gắng xóa tệp ở `finally`. Dọn tệp tạm được thực hiện dù có ngoại lệ trong phần xử lý chính; trường hợp thao tác xóa cũng lỗi thì `IOException` có thể được ném tiếp.

Mã ví dụ có thể dùng cú pháp được giới thiệu trong Java 7, nhưng khi biên dịch với `--release 17`, class file nhắm tới **Java 17**; không vì cú pháp cũ mà class file tự trở thành “Java 7 bytecode”.

## 7. Tương thích: ba loại yêu cầu phải kiểm tra riêng

“Dùng tính năng Java” có ít nhất ba câu hỏi độc lập:

| Câu hỏi | Kiểm tra | Lỗi điển hình nếu không đáp ứng |
| --- | --- | --- |
| **Nguồn có hợp ngữ pháp/luật kiểu không?** | Mức `--release` và cú pháp mà compiler cho phép. | Lỗi biên dịch ở cú pháp hoặc kiểm tra kiểu. |
| **API có tồn tại tại thời điểm biên dịch/chạy không?** | Class, method, module và dependency trong Java SE/JAR đích. | Lỗi biên dịch “cannot find symbol”; ở runtime có thể là `NoClassDefFoundError` hoặc `NoSuchMethodError` nếu môi trường khác bản build. |
| **JVM có đọc được class file và opcode không?** | Phiên bản class file và các tính năng JVM đích. | `UnsupportedClassVersionError` khi class file đòi runtime mới hơn. |

Thông tin thực dụng:

- `javac --release 17 Example.java` yêu cầu compiler sử dụng mức ngôn ngữ, class file và **API chuẩn theo Java 17**. Nó hữu ích hơn việc chỉ chọn `--source` hoặc `--target` khi cần tránh vô tình gọi API mới hơn môi trường đích.
- Java 7 dùng **class file major version 51**; Java 17 dùng **61**. Đây là dữ kiện giúp đọc lỗi version, **không phải lý do để tiếp tục dùng runtime Java 7**.
- JVM mới thường đọc được class file cũ, nhưng chương trình vẫn có thể lỗi vì API hoặc dependency không tương thích, module, cấu hình, hành vi môi trường hay thay đổi bảo mật. Phải test trên runtime thật.
- Class file được biên dịch cho runtime mới không chạy trên JVM cũ chỉ nhờ source có cú pháp cũ.
- Một API thư viện không tự tạo ra cú pháp mới; một từ khóa mới không tự đảm bảo API có trên mọi JDK; một opcode mới không tự làm cho mã nguồn dùng được trên compiler cũ.

Có thể xem class file sau khi biên dịch:

```bash
javap -verbose Java7LayersDemo
```

Tìm dòng `major version`. Với lệnh `javac --release 17` ở trên, giá trị phải là `61`. Dùng `javap -c -p` khi cần xem lệnh bytecode để phân biệt thao tác được compiler “dịch xuống” với lời gọi API.

## 8. Cách áp dụng khi nghiên cứu một thay đổi Java

Khi đọc về một cải tiến, hãy đi lần lượt:

1. **Hỏi nó thuộc lớp nào.** Ví dụ `try-with-resources` trước hết là cú pháp; `Files` là API; `invokedynamic` là bytecode/JVM.
2. **Chỉ ra phụ thuộc giữa các lớp.** Try-with-resources cần giao ước `AutoCloseable`; `Files` cần implementation/runtime; lambda có thể được compiler triển khai bằng `invokedynamic`.
3. **Kiểm tra yêu cầu phiên bản cho từng lớp.** Compiler có hiểu syntax không, JDK đích có API không, JVM có chạy class file không?
4. **Biên dịch và kiểm thử trên JDK mục tiêu còn được hỗ trợ.** Dùng `--release` phù hợp và kiểm tra thư viện phụ thuộc, thay vì giả định “nếu compile được thì chạy ở đâu cũng được”.
5. **Ưu tiên cách dùng đang phù hợp.** Giữ các cơ chế hữu ích (try-with-resources, NIO.2, generics, APIs hiện đại), tránh mang theo cấu hình/toolchain chỉ vì chúng từng xuất hiện cùng Java 7.

### Những nhầm lẫn thường gặp

- **“Java có thêm `switch(String)` nên JVM phải có opcode mới.”** Sai: `javac` có thể dịch sang các lời gọi và nhánh bytecode sẵn có.
- **“`AutoCloseable` tự đóng tài nguyên dù không dùng `try`.”** Sai: đối tượng cần được đóng theo vòng đời thích hợp; try-with-resources là một cơ chế đảm bảo compiler sinh lời gọi đóng.
- **“Thêm `Path`/`Files` là nâng cấp JVM.”** Sai: đây chủ yếu là lớp thư viện; JVM thực thi lời gọi, việc truy cập tệp do provider/runtime và hệ thống bên dưới xử lý.
- **“`invokedynamic` đồng nghĩa Java 7 đã có lambda.”** Sai: hỗ trợ JVM đến trước, cú pháp lambda đến sau.
- **“Cùng source Java 7 thì class file tự tương thích với JVM 7.”** Sai: phải xét compiler, `--release`, bytecode, API và dependency.
- **“Cứ dùng API/cấu hình Java 7 là chuẩn cho dự án hiện tại.”** Sai: lấy **cơ chế còn hữu ích** từ giai đoạn đó, nhưng build, triển khai và bảo trì trên JDK được hỗ trợ.

## 9. Tự kiểm tra hiểu biết

**Tình huống A:** Code dùng `try-with-resources` với một lớp tự viết. Cần bổ sung gì? — Lớp triển khai `AutoCloseable` và `close()` có ý nghĩa rõ ràng; compiler sẽ xử lý việc đóng theo cú pháp `try`.

**Tình huống B:** Dùng `Files.readAllLines(...)` nhưng không xuất hiện từ khóa mới. Đó là cải tiến lớp nào? — Chủ yếu là **thư viện chuẩn**; lời gọi vẫn được biên dịch thành bytecode gọi phương thức.

**Tình huống C:** Một đoạn lambda có opcode `invokedynamic`. Điều đó chứng minh lambda là cú pháp Java 7? — **Không**. Nó cho thấy compiler dùng cơ chế liên kết động của JVM vốn đã có nền tảng từ Java 7.

**Tình huống D:** Chương trình build với `--release 17`, runtime Java cũ báo `UnsupportedClassVersionError`. Có phải lỗi `Path`? — Chưa thể kết luận về API; đầu tiên hãy đối chiếu **major version class file** với JVM đang chạy.

**Ghi nhớ:** Ngôn ngữ quy định **cách diễn đạt**; thư viện chuẩn cung cấp **khả năng để gọi**; JVM cung cấp **môi trường thực thi bytecode**. Một cải tiến thành công khi các lớp cần thiết khớp nhau về tính năng và phiên bản.