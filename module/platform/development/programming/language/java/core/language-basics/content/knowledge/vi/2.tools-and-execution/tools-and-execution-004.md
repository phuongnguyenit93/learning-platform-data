# Thư mục làm việc, thư mục đầu ra và classpath trong Java

> **Module:** Java core — language-basics  
> **Chủ đề:** Công cụ và thực thi  
> **Mục tiêu:** Phân biệt thư mục làm việc của tiến trình, thư mục chứa kết quả biên dịch và classpath. Tự biên dịch/chạy một project Java có `package`, nhiều tệp `.java`, tệp dữ liệu và classpath resource; giải thích vì sao JVM tìm được class nhưng chương trình không tìm được file, hoặc ngược lại.

## 1. Ba loại đường dẫn cần phân biệt

Một chương trình Java có thể vừa nạp bytecode `.class`, vừa đọc file trên ổ đĩa. Đó là **hai cơ chế tìm kiếm khác nhau**, thêm một cơ chế thứ ba khi compiler tạo kết quả:

| Khái niệm | Tác dụng | Ví dụ |
| --- | --- | --- |
| **Working directory** (thư mục làm việc, CWD) | Nơi các đường dẫn file **tương đối** được giải quyết khi tiến trình chạy | `Path.of("data", "customer.txt")` đọc từ thư mục `data` dưới CWD |
| **Output directory** (thư mục đầu ra biên dịch) | Nơi `javac -d` ghi các file `.class` theo cây package | `javac -d out ...` ghi `out/demo/app/Main.class` |
| **Classpath** (đường tìm lớp/tài nguyên) | Danh sách các thư mục hoặc JAR dùng để tìm class và resource trên classpath | `java -cp 'out:resources' demo.app.Main` trên Linux/macOS |

Dùng `javac -d out` **không** làm chương trình tự chạy từ `out`, cũng **không** tự thêm `out` vào classpath của một lệnh `java` khác. Dùng `java -cp ...` **không** chuyển working directory sang bất kỳ thư mục nào được liệt kê.

~~~mermaid
flowchart TD
    A["src/main/java: mã nguồn"] --> B["javac -d out"]
    B --> C["out: bytecode .class"]
    C --> D["Classpath: out + resources"]
    R["resources: file bên trong classpath"] --> D
    D --> J["JVM: nạp class, resource"]
    W["Working directory: path-lab"] --> F["data/customer.txt: file tương đối"]
    J --> F
    J --> O["Kết quả chạy"]
~~~

**Mẹo nhớ:** `-d` trả lời “compiler **ghi** ở đâu?”, `-cp` trả lời “JVM/compiler **tìm class** ở đâu?”, còn CWD trả lời “đường dẫn file **tương đối** bắt đầu ở đâu?”.

## 2. Project mẫu và cây thư mục

Ta tạo thư mục `path-lab` chứa mã Java 11+ không dùng dependency ngoài:

~~~text
path-lab/
├── src/
│   └── main/
│       └── java/
│           └── demo/
│               ├── app/
│               │   └── Main.java
│               └── lib/
│                   └── GreetingFormatter.java
├── data/
│   └── customer.txt
└── resources/
    └── messages/
        └── greeting.txt
~~~

Khi biên dịch, chương trình sẽ tạo thêm thư mục `out`. Cây `src/main/java` là một **quy ước tổ chức**; từ khóa `package` trong mỗi tệp mới quyết định tên đầy đủ của class và cách Java sắp xếp output theo `-d`.

Hai tệp văn bản cần tạo trước:

**`data/customer.txt`**

~~~text
Lan
~~~

**`resources/messages/greeting.txt`**

~~~text
Xin chào
~~~

Lưu với UTF-8. Chúng cùng là file văn bản nhưng **cách chương trình tìm chúng khác nhau**: `customer.txt` dựa trên working directory, còn `greeting.txt` sẽ được tìm qua classpath.

## 3. Viết mã Java cho project

### 3.1. GreetingFormatter.java

Tệp `src/main/java/demo/lib/GreetingFormatter.java`:

~~~java
package demo.lib;

public final class GreetingFormatter {
    private GreetingFormatter() { }

    public static String format(String greeting, String customer) {
        if (greeting == null || greeting.isBlank()
                || customer == null || customer.isBlank()) {
            throw new IllegalArgumentException("Missing text");
        }
        return greeting + ", " + customer + "!";
    }
}
~~~

Lớp có tên đầy đủ `demo.lib.GreetingFormatter`. `package demo.lib;` không phải một phần của đường dẫn Java command; JVM sẽ dùng tên package để tìm file class bên dưới mỗi **classpath root**.

### 3.2. Main.java

Tệp `src/main/java/demo/app/Main.java`:

~~~java
package demo.app;

import demo.lib.GreetingFormatter;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Main {
    private static String readGreeting() throws IOException {
        try (InputStream in =
                Main.class.getResourceAsStream("/messages/greeting.txt")) {
            if (in == null) {
                throw new IllegalStateException(
                        "Missing classpath resource: /messages/greeting.txt");
            }
            return new String(
                    in.readAllBytes(), StandardCharsets.UTF_8).strip();
        }
    }

    public static void main(String[] args) throws IOException {
        Path workingDir = Path.of("").toAbsolutePath().normalize();
        System.out.println("Working directory: " + workingDir);

        // File ngoài: tương đối theo working directory.
        Path customerFile = Path.of("data", "customer.txt");
        String customer = Files.readString(
                customerFile, StandardCharsets.UTF_8).strip();

        // Resource: tìm theo classpath, không theo CWD.
        String greeting = readGreeting();
        System.out.println("Customer file: "
                + customerFile.toAbsolutePath().normalize());
        System.out.println(GreetingFormatter.format(greeting, customer));
    }
}
~~~

Đọc kỹ sự khác nhau:

- `Files.readString(Path.of("data", "customer.txt"), UTF_8)` mở file tương đối với working directory. Nếu chưa có file, Java có thể ném `NoSuchFileException`.
- `Main.class.getResourceAsStream("/messages/greeting.txt")` tìm resource từ **gốc đường tìm resource** cho class này. Ở ví dụ **classpath truyền thống**, đó là entry `resources` hoặc resource đã đóng gói trong JAR. Khi không tìm được, API trả `null` và chương trình chủ động ném `IllegalStateException`.
- `import demo.lib.GreetingFormatter;` có nghĩa chương trình sử dụng một class khác; class này phải sẵn có khi biên dịch và khi runtime nạp nó.

Tệp `Main.java` dùng `Path.of`, `Files.readString`, `String.strip` và `InputStream.readAllBytes` nên yêu cầu **Java 11 trở lên**. Đây là một project **console** giản lược để quan sát đường dẫn, không phải cấu hình Maven/Gradle hoàn chỉnh.

## 4. Biên dịch và chạy bằng Bash trên macOS/Linux

Từ **thư mục cha** của `path-lab`:

~~~bash
cd path-lab
mkdir -p out

javac -encoding UTF-8 -d out \
  src/main/java/demo/lib/GreetingFormatter.java \
  src/main/java/demo/app/Main.java

java -cp 'out:resources' demo.app.Main
~~~

`mkdir -p out` tạo thư mục gốc cho output. Khi dùng `javac -d out`, hãy tạo sẵn `out`; compiler sẽ tạo thư mục package con trong đó. Sau khi biên dịch thành công, bạn sẽ có:

~~~text
out/
└── demo/
    ├── app/
    │   └── Main.class
    └── lib/
        └── GreetingFormatter.class
~~~

`-cp 'out:resources'` cung cấp **hai** classpath entries: `out` để tìm hai class và `resources` để tìm `messages/greeting.txt`. **Dấu hai chấm** là dấu phân tách classpath trên macOS/Linux.

Kết quả ví dụ:

~~~text
Working directory: <đường dẫn tuyệt đối tới path-lab>
Customer file: <đường dẫn tuyệt đối tới path-lab/data/customer.txt>
Xin chào, Lan!
~~~

Hai đường dẫn phụ thuộc vị trí thật trên máy; dòng cuối phải là `Xin chào, Lan!`.

**Không chạy `java Main`** khi class có `package demo.app;`. Tên lớp dùng để chạy là `demo.app.Main`, không có đuôi `.java` hoặc `.class`.

## 5. Biên dịch và chạy trên Windows PowerShell

Từ thư mục cha của `path-lab`:

~~~powershell
Set-Location path-lab
New-Item -ItemType Directory -Force -Path out | Out-Null
javac -encoding UTF-8 -d out src/main/java/demo/lib/GreetingFormatter.java src/main/java/demo/app/Main.java
java -cp 'out;resources' demo.app.Main
~~~

Điểm khác biệt: **Windows dùng dấu chấm phẩy** để phân tách các entry classpath, vì vậy `out;resources`, không phải `out:resources`. Trong PowerShell, đặt toàn bộ chuỗi classpath trong dấu nháy đơn để shell truyền nó nguyên vẹn thành **một đối số**.

Bạn có thể dùng dấu gạch chéo xuôi trong đường dẫn truyền cho các công cụ Java trên Windows như ví dụ, hoặc dùng dạng đường dẫn Windows tương ứng. Tránh nhầm dấu **phân tách path trong hệ điều hành** với dấu **phân tách nhiều phần tử của classpath**.

Nếu thư mục có khoảng trắng như `C:\Java Projects\path-lab`, cần quote đường dẫn nguồn/đích chứa khoảng trắng. Ví dụ `java -cp 'C:\Java Projects\path-lab\out;C:\Java Projects\path-lab\resources' demo.app.Main` là classpath Windows gồm hai entry; khi dùng đường dẫn tuyệt đối, working directory **vẫn không tự thay đổi**.

## 6. Thử nghiệm: lỗi nằm ở classpath hay working directory?

### Trường hợp A: class có đủ, nhưng thiếu resource

Từ đúng thư mục `path-lab`, chạy:

~~~bash
java -cp out demo.app.Main
~~~

- Java nạp `Main.class` và `GreetingFormatter.class` trong `out` thành công.
- File `data/customer.txt` vẫn đọc được vì working directory đúng.
- Nhưng `messages/greeting.txt` không có trong `out`, nên `getResourceAsStream` trả `null` và chương trình báo thiếu classpath resource.

**Cách sửa:** thêm `resources` vào `-cp`, hoặc đóng gói resource vào JAR đúng đường dẫn. Không nên chỉ đổi CWD với hy vọng JVM tự tìm classpath resource.

### Trường hợp B: có resource nhưng thiếu class

~~~bash
java -cp resources demo.app.Main
~~~

JVM chỉ tìm trong `resources`, không thấy `demo/app/Main.class`. Chương trình thất bại ở bước **nạp main class**, chưa chạy logic đọc file. Thêm `out` vào classpath để JVM tìm được class.

### Trường hợp C: classpath đúng nhưng CWD sai

Giả sử bạn đứng ở thư mục **cha** của `path-lab`. Nếu đưa classpath hợp lệ từ đó, ví dụ macOS/Linux:

~~~bash
java -cp 'path-lab/out:path-lab/resources' demo.app.Main
~~~

JVM có thể tìm được class và resource. Nhưng `Path.of("data", "customer.txt")` lúc này trỏ tới `data/customer.txt` **bên dưới thư mục cha**, không phải `path-lab/data/customer.txt`. Chương trình sẽ báo thiếu file nếu file ấy không tồn tại ở vị trí đang tìm.

Có hai hướng giải quyết hợp lý: **chạy từ working directory đúng** hoặc **truyền đường dẫn file cấu hình rõ ràng** (tuyệt đối hay tương đối, được xử lý theo hợp đồng). Không nên viết cứng đường dẫn tuyệt đối tới máy của một lập trình viên vào mã nguồn dùng chung.

## 7. Classpath root và cấu trúc package

Lớp trong ví dụ khai báo:

~~~java
package demo.app;

public final class Main {
    public static void main(String[] args) { }
}
~~~

Khi output đặt tại `out`, bytecode nằm ở `out/demo/app/Main.class`. Vì vậy:

| Lệnh | Đánh giá | Lý do |
| --- | --- | --- |
| `java -cp out demo.app.Main` | Tìm được main class | Classpath root là `out`, Java tự ánh xạ `demo.app.Main` thành `demo/app/Main.class` |
| `java -cp out/demo/app Main` | Sai cho lớp ví dụ | `Main` không nằm ở default package; trong bytecode tên lớp vẫn là `demo.app.Main` |
| `java -cp resources demo.app.Main` | Thiếu classpath cho code | `resources` không chứa bytecode của main class |

Tên **package** do khai báo `package` quyết định, không do thư mục hiện tại của terminal tự sinh ra. Nên đặt file nguồn theo cây package vì nó giúp code và build tool dễ hiểu; `javac -d` đặt output theo đúng tên package.

## 8. `javac -cp` khác `java -cp` thế nào?

Cùng là tùy chọn thiết lập đường tìm class, nhưng **thời điểm** khác:

- `javac -cp ...` cho **compiler** biết nơi tìm những class đã biên dịch hoặc JAR cần để giải quyết import/type.
- `java -cp ...` cho **runtime** biết nơi tìm main class, các class phụ thuộc và các resource trên classpath.

Trong ví dụ ban đầu, ta đưa **cả hai tệp nguồn** cho `javac` cùng một lần nên compiler có thể biên dịch chúng cùng nhau. Nếu biên dịch từng file riêng:

~~~bash
# Thực hiện từ path-lab, sau khi out đã tồn tại.
javac -encoding UTF-8 -d out src/main/java/demo/lib/GreetingFormatter.java
javac -encoding UTF-8 -cp out -d out src/main/java/demo/app/Main.java
~~~

Lượt biên dịch thứ hai cần thấy `GreetingFormatter.class` trong `out`. Nhưng sau khi build, lệnh chạy vẫn cần **`out` và `resources`** để chương trình hoạt động đúng.

Nếu có thư viện ngoài `lib/helper.jar`, trong project thực tế, compiler và runtime có thể cần thêm JAR đó trên classpath:

~~~bash
# Minh họa cú pháp trên macOS/Linux; thay tên nguồn và lớp cho dự án thật.
javac -cp 'lib/helper.jar' -d out YourFile.java
java -cp 'out:resources:lib/helper.jar' your.package.Main
~~~

Trên Windows, dùng `;` thay cho `:` khi phân tách nhiều phần tử classpath. Dòng này **không phải lệnh chạy project mẫu** vì project mẫu không có `lib/helper.jar` hay `YourFile.java`.

Khi chỉ định `-cp` tường minh, đừng mặc định Java sẽ tự thêm `out`, `resources`, mọi JAR đang có hay thư mục hiện tại. `CLASSPATH` là biến môi trường tùy chọn, nhưng cấu hình bằng `-cp` thường rõ hơn cho từng lệnh.

## 9. Đóng gói class và resource vào JAR

Sau khi biên dịch, hãy tạo JAR có entry point và resource:

**Bash (macOS/Linux):**

~~~bash
jar --create --file demo.jar \
  --main-class demo.app.Main \
  -C out . -C resources .
java -jar demo.jar
~~~

**PowerShell (Windows):**

~~~powershell
jar --create --file demo.jar --main-class demo.app.Main -C out . -C resources .
java -jar demo.jar
~~~

Tùy chọn `-C out .` đưa các file class nằm trong `out` vào gốc JAR, giữ cây package. Tùy chọn `-C resources .` đưa `messages/greeting.txt` vào đúng đường dẫn ở bên trong JAR. `--main-class demo.app.Main` ghi thông tin main class vào manifest của JAR.

Khi chạy `java -jar`, JVM dùng main class từ manifest. **Đừng giả định** `-cp` đặt cạnh `-jar` sẽ tự thêm mọi thư viện ngoài vào đường tìm class; với ứng dụng nhiều dependency cần đóng gói hoặc khai báo chúng theo cách phù hợp.

**Điểm mấu chốt:** `data/customer.txt` **vẫn là file bên ngoài**. Lệnh `java -jar demo.jar` từ `path-lab` vẫn đọc được file đó; chạy JAR từ một working directory khác có thể không đọc được, dù class và greeting resource đã nằm trong JAR.

## 10. Bảng chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| `javac -d out` không thể ghi class | `out` chưa tồn tại hoặc không có quyền ghi | Tạo `out` trước, kiểm tra quyền |
| `Could not find or load main class` | `-cp` thiếu output root hoặc tên package sai | Kiểm tra `out/demo/app/Main.class` và chạy `demo.app.Main` |
| `NoClassDefFoundError` | Thiếu class phụ thuộc lúc chạy, hoặc lỗi nạp/khởi tạo khác | Xem classpath, dependency và phần `Caused by` |
| `package demo.lib does not exist` khi compile | Compiler không thấy mã hay class của thư viện nội bộ | Biên dịch cả hai nguồn hoặc thêm `-cp out` ở lượt sau |
| `NoSuchFileException: data/customer.txt` | Sai working directory hoặc chưa có file | Xem CWD và đường dẫn thực tế, không chỉ classpath |
| `Missing classpath resource` | Thiếu `resources` trên classpath/JAR, sai tên resource | Kiểm tra root classpath và `messages/greeting.txt` |
| Chạy được trong IDE nhưng lỗi trên terminal | IDE đặt working directory, output hoặc classpath khác | Kiểm tra Run Configuration rồi so sánh ba giá trị |
| `UnsupportedClassVersionError` | Bytecode build cho Java mới hơn runtime hỗ trợ | Kiểm tra JDK build, runtime và target phù hợp |

**Phân biệt lỗi ở ba tầng:** `javac` không tìm được type là lỗi **biên dịch**; `java` không tìm được main class là lỗi **nạp chương trình**; `Files.readString` không mở được file là lỗi **I/O lúc chạy**. Ba lỗi này cần ba hướng kiểm tra khác nhau.

### Trường hợp biên đáng lưu ý

- **Có khoảng trắng trong đường dẫn:** quote classpath và đối số đường dẫn. Trên Bash, dấu `;` có ý nghĩa đặc biệt đối với shell.
- **Phân biệt hoa/thường:** các hệ điều hành có thể có quy tắc phân biệt chữ khác nhau; tên `Main.class`, package, resource phải chính xác.
- **Đường dẫn tương đối trong IDE:** IDE có thể mặc định working directory là project root, module root hoặc thư mục cấu hình khác. Không mặc định giống terminal.
- **Thư mục runtime khác với thư mục JDK:** `JAVA_HOME`, `java.home`, CWD và classpath là các khái niệm độc lập.
- **Classpath khác module path:** bài này dùng classpath và project **không có `module-info.java`**. Ứng dụng theo Java Platform Module System có quy tắc nạp/module path riêng.

## 11. Quy trình kiểm tra nhanh khi project không chạy

1. **Xem CWD:** Bash dùng `pwd`, PowerShell dùng `Get-Location`. Khi chạy Java, chương trình có thể in `Path.of("").toAbsolutePath()` để hỗ trợ chẩn đoán.
2. **Xem nơi xuất bytecode:** file `.class` có dưới thư mục đã truyền cho `-d` không, và cây package có đúng không?
3. **Xem runtime classpath:** entry đầu tiên chứa gốc package của main class không? Đã thêm resource/JAR cần thiết chưa?
4. **Kiểm tra file dữ liệu:** `data/customer.txt` có tồn tại **tương đối với CWD** không?
5. **Đọc nguyên thông báo lỗi:** lỗi biên dịch, lỗi load class hay lỗi mở file là ba tầng khác nhau.
6. **Thay một yếu tố mỗi lượt:** không đổi cả classpath, CWD và package đồng thời rồi đoán nguyên nhân.

## 12. Bài tập có đáp án định hướng

**Bài 1 — Class có đủ nhưng resource thiếu.** Dự đoán điều gì xảy ra khi chạy `java -cp out demo.app.Main` từ `path-lab`.

*Gợi ý:* Nạp được các file `.class` và đọc được `data/customer.txt`, nhưng thiếu `resources` để tìm `/messages/greeting.txt`.

**Bài 2 — Classpath đúng nhưng file không thấy.** Chạy từ thư mục cha với `-cp 'path-lab/out:path-lab/resources'` trên macOS/Linux. Tại sao `Files.readString` có thể thất bại?

*Gợi ý:* CWD là thư mục cha; đường dẫn tương đối sẽ trỏ tới `data` dưới thư mục cha, không phải dưới `path-lab`.

**Bài 3 — Thử compile hai lượt.** Biên dịch `GreetingFormatter.java` trước, sau đó `Main.java`. Lượt hai cần thêm tùy chọn nào để compiler tìm class đã tạo?

*Gợi ý:* Dùng `javac -cp out -d out ...`.

**Bài 4 — Đóng gói JAR.** Tạo `demo.jar` chứa hai class và `messages/greeting.txt`. Chạy từ project root và từ một thư mục khác. Phần nào đã nằm trong JAR, phần nào vẫn phụ thuộc CWD?

**Bài 5 — Cải thiện thiết kế.** Cho chương trình nhận đường dẫn `customer.txt` qua `args[0]` thay vì cố định `data/customer.txt`. Kiểm tra trường hợp thiếu đối số, file không tồn tại và đường dẫn tương đối. Thảo luận khi nào nên dùng đường dẫn tuyệt đối.

### Tự đánh giá

Bạn hiểu bài khi tự trả lời được: `javac -d` tạo `.class` ở đâu; `java -cp` tìm `demo.app.Main` và resource từ đâu; `Path.of("data","customer.txt")` phụ thuộc thư mục nào; tại sao Java package cần tên FQCN khi chạy; và vì sao đóng gói JAR **không tự biến file bên ngoài thành resource bên trong JAR**.
