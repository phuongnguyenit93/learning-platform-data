# Từ lệnh `java` đến tiến trình JVM và điểm vào chương trình

## 1. Bức tranh tổng thể

Khi mở terminal và nhập `java demo.LifecycleApp`, ta không “gọi thẳng phương thức `main`” như gọi một phương thức bình thường từ mã nguồn. Lệnh này khởi động **một chương trình thực thi của hệ điều hành**, thiết lập một **tiến trình** chứa môi trường **JVM**, rồi JVM tìm, nạp, liên kết, khởi tạo lớp đầu vào và gọi `main`.

Vòng đời điển hình của ứng dụng Java chạy qua command line:

```text
Người dùng / script / IDE
          |
          | gõ hoặc chạy lệnh java [JVM options] MainClass [app args]
          v
Shell tìm chương trình java theo PATH (hoặc đường dẫn tuyệt đối)
          |
          v
Hệ điều hành khởi tạo tiến trình (process, có PID, không gian địa chỉ ...)
          |
          v
Java launcher phân tích tùy chọn và cấu hình runtime
          |
          v
Khởi động JVM trong tiến trình
          |
          v
Xác định lớp / JAR / module / tệp nguồn đầu vào
          |
          v
Nạp → liên kết → khởi tạo lớp chính
          |
          v
Gọi public static void main(String[] args)
          |
          v
Ứng dụng chạy: lời gọi phương thức, đối tượng, luồng, I/O ...
          |
          v
Điều kiện kết thúc JVM / yêu cầu thoát
          |
          v
Shutdown hooks (khi cơ chế shutdown thông thường được thực hiện)
          |
          v
JVM kết thúc, tiến trình trả mã thoát cho hệ điều hành
```

Đây là **luồng khái niệm**, không phải danh sách mọi hàm native nội bộ. Thứ tự, tên thành phần và cơ chế tạo JVM cụ thể có thể khác theo hệ điều hành, nhà cung cấp JVM và cách nhúng runtime. Trong trường hợp **khởi chạy một ứng dụng bằng lệnh `java` thông thường**, mô hình trên giúp lý giải phần lớn hành vi quan sát được.

Bài học tập trung vào ranh giới **lệnh shell → tiến trình hệ điều hành → Java launcher → JVM → lớp đầu vào → phương thức `main` → kết thúc tiến trình**.

## 2. Phân biệt bốn thực thể dễ bị nhầm lẫn

| Thực thể | Nó là gì? | Điều cần nhớ |
| --- | --- | --- |
| **Shell** | Chương trình nhận lệnh, chẳng hạn PowerShell, CMD, Bash | Phân tách cú pháp lệnh và yêu cầu hệ điều hành chạy một chương trình |
| **`java` launcher** | Chương trình thực thi đi cùng bản phân phối Java | Đọc tùy chọn, xác định kiểu khởi chạy và bắt đầu JVM |
| **Tiến trình (process)** | Đơn vị thực thi do hệ điều hành quản lý, có PID và tài nguyên riêng | Chứa mã native của launcher, JVM và mã ứng dụng đang chạy |
| **JVM** | Máy ảo thực thi bytecode và cung cấp cơ chế runtime | Nạp lớp, thực thi mã Java, quản lý nhiều hoạt động runtime |
| **`main`** | Phương thức đầu vào chuẩn của một ứng dụng Java kiểu class-launch | Là điểm vào **logic ứng dụng**, không phải điểm bắt đầu toàn bộ tiến trình hệ điều hành |

Ví dụ, hai cửa sổ terminal cùng chạy `java -cp out demo.LifecycleApp` sẽ **thông thường tạo hai tiến trình Java độc lập**, có PID và vùng nhớ khác nhau. Các trường `static` không tự động được chia sẻ qua hai tiến trình; “cùng tên lớp” không có nghĩa “cùng JVM”.

Một JVM có thể chạy **nhiều luồng (thread)** trong một tiến trình. Luồng chia sẻ nhiều tài nguyên của tiến trình, còn các tiến trình Java riêng biệt không chia sẻ heap theo cách thông thường. Đừng đồng nhất PID với thread ID hoặc cho rằng mỗi thread tạo ra một JVM mới.

## 3. Điều gì xảy ra ngay sau khi nhập lệnh `java`?

### 3.1. Shell tìm đúng chương trình `java`

Trong terminal, tên `java` thường được giải quyết theo cơ chế tìm chương trình của shell và hệ điều hành, thường liên quan đến biến môi trường `PATH`. Nếu chỉ định đường dẫn tuyệt đối đến `java` của một JDK cụ thể, ta tránh được nhiều nhầm lẫn do có nhiều JDK cùng cài đặt.

Các lệnh chẩn đoán:

```powershell
java -version
javac -version
where.exe java
Get-Command java
```

Đối với Bash hoặc shell tương tự:

```bash
java -version
javac -version
command -v java
```

`java -version` chỉ in thông tin runtime rồi thoát; nó **không yêu cầu** một lớp ứng dụng có `main`. `javac` là công cụ biên dịch mã nguồn. Hai lệnh có thể trỏ đến các bản cài đặt khác nhau nếu cấu hình `PATH` không nhất quán.

Khi tìm thấy launcher, shell yêu cầu hệ điều hành chạy nó. Trên các hệ thống phổ biến, hệ điều hành cấp cho tiến trình một định danh PID, không gian địa chỉ và các tài nguyên cần thiết. Cách shell đợi lệnh hoàn thành, chạy nền hoặc chuyển hướng đầu vào/đầu ra phụ thuộc vào shell; JVM không tự quyết định toàn bộ hành vi đó.

### 3.2. Launcher hiểu hai loại đối số khác nhau

Cú pháp class-launch cơ bản:

```text
java [tùy chọn của launcher/JVM] <tên lớp chính> [đối số của ứng dụng...]
```

Ví dụ:

```bash
java -Xmx256m -Dapp.mode=demo -cp out demo.LifecycleApp alpha "two words"
```

Ở đây:

- `java`: khởi chạy ứng dụng Java.
- `-Xmx256m`: tùy chọn đặt mức heap tối đa của JVM (ví dụ thuộc nhóm tùy chọn JVM, không phải tham số của `main`).
- `-Dapp.mode=demo`: thuộc tính hệ thống Java, có thể đọc qua `System.getProperty("app.mode")`.
- `-cp out`: dùng thư mục `out` làm đường dẫn tìm class thông thường.
- `demo.LifecycleApp`: tên **đầy đủ** (*fully qualified class name*) của lớp đầu vào, không phải tên tệp `.java` hoặc `.class`.
- `alpha` và `"two words"`: được shell truyền thành hai đối số của ứng dụng; launcher chuyển chúng vào mảng `String[] args` của `main`.

**Vị trí đối số rất quan trọng.**

```bash
java -Xmx256m -cp out demo.LifecycleApp alpha
```

Trong lệnh trên, `-Xmx256m` được launcher/JVM xử lý. Ngược lại:

```bash
java -cp out demo.LifecycleApp -Xmx256m
```

Ở lệnh sau, chuỗi `"-Xmx256m"` đứng **sau tên lớp chính**, vì vậy nó là **đối số ứng dụng**, không phải yêu cầu đặt heap. Tùy chọn JVM phải được đặt ở phần tùy chọn trước tên chương trình theo cú pháp tương ứng.

Cú pháp dấu nháy và việc tách chuỗi thành token xảy ra ở phía shell; Java nhận những chuỗi đã được chuyển tới launcher, không tự tách lại nội dung của dấu nháy như shell.

### 3.3. Launcher khởi tạo JVM và tìm chương trình cần chạy

Launcher chuẩn bị cấu hình runtime và khởi động JVM phù hợp. JVM sử dụng class loader và các cơ chế runtime để tìm định nghĩa lớp, liên kết lớp và thực thi mã. Đặc tả JVM mô tả ý nghĩa các bước; không nên suy diễn rằng mọi bản JVM luôn có một thứ tự chi tiết giống hệt nhau trong nội bộ.

Trong trường hợp chạy class thông thường:

```text
java -cp out demo.LifecycleApp
                    |
                    v
Classpath = out
                    |
                    v
Tìm out/demo/LifecycleApp.class
                    |
                    v
Nạp, liên kết, khởi tạo demo.LifecycleApp
                    |
                    v
Gọi demo.LifecycleApp.main(String[])
```

Đường dẫn tệp nêu trên là cách hình dung với thư mục lớp đã biên dịch. Trên Windows dấu phân cách thư mục có thể được hiển thị bằng `\`; class loader cũng có thể tìm class từ JAR hoặc nguồn lớp khác tùy cấu hình.

## 4. JVM chuẩn bị lớp chính trước khi gọi `main`

Theo mô hình của Java, khởi động một ứng dụng kiểu class-launch dẫn đến các bước quan trọng sau.

### Bước 1: Loading — nạp lớp

JVM cần định nghĩa lớp đầu vào ở dạng class file/bytecode hợp lệ. Class loader tìm và tạo biểu diễn runtime của lớp. Nếu lớp không nằm trên classpath/module path thích hợp hoặc tên đầy đủ bị sai, ứng dụng có thể dừng **trước khi vào `main`**.

Ví dụ: với `package demo;` và tên lớp `LifecycleApp`, launcher phải tìm `demo.LifecycleApp`. Gõ `java -cp out LifecycleApp` sẽ không tương đương.

### Bước 2: Linking — liên kết lớp

Liên kết gồm các hoạt động như:

1. **Verification:** xác minh tính hợp lệ của các cấu trúc class file và một số ràng buộc kiểu/bytecode.
2. **Preparation:** chuẩn bị vùng lưu trữ của các trường `static` và các giá trị mặc định theo đặc tả, trước khi mã khởi tạo tĩnh của ứng dụng được thực hiện.
3. **Resolution:** giải quyết tham chiếu ký hiệu như thông tin lớp/phương thức/trường thành thực thể runtime khi cần; một số resolution có thể được trì hoãn.

Không được kết luận rằng **mọi lớp phụ thuộc** sẽ được tải, giải quyết và khởi tạo ngay trước `main`. Có những công việc xảy ra khi chương trình bắt đầu sử dụng chúng.

### Bước 3: Initialization — khởi tạo lớp chính

Trước khi `main` được gọi, lớp khai báo phương thức đó phải được khởi tạo thành công. Điều này liên quan đến việc khởi tạo các lớp cha cần thiết, chạy bộ khởi tạo trường `static` và khối `static { ... }` theo quy tắc của ngôn ngữ.

Ví dụ:

```java
public class InitBeforeMain {
    static {
        System.out.println("static initializer");
    }

    public static void main(String[] args) {
        System.out.println("main method");
    }
}
```

Biên dịch và chạy:

```bash
javac InitBeforeMain.java
java InitBeforeMain
```

**Stdout chính xác khi chạy bình thường:**

```text
static initializer
main method
```

Điều này chứng minh: **`main` không phải câu lệnh Java đầu tiên có thể được thực thi trong chương trình**. Bộ khởi tạo tĩnh của lớp chính có thể chạy trước. Nếu khởi tạo thất bại, `main` có thể chưa được gọi.

### Bước 4: Invoke main — gọi phương thức đầu vào

Với mô hình class-launch chuẩn tương thích Java 17, phương thức đầu vào có chữ ký:

```java
public static void main(String[] args)
```

Hoặc cú pháp varargs tương đương về kiểu tham số:

```java
public static void main(String... args)
```

Ý nghĩa:

- `public`: phương thức có khả năng được gọi từ ngoài lớp theo hợp đồng điểm vào chuẩn.
- `static`: launcher không cần tự tạo một đối tượng của lớp ứng dụng để gọi phương thức.
- `void`: phương thức không trả một giá trị kết quả trực tiếp theo kiểu `int` để làm exit code.
- `String[] args`: chứa các đối số chương trình mà launcher chuyển tới sau tên lớp/JAR/module/tệp nguồn, không gồm các tùy chọn JVM đã xử lý.

Tên biến `args` **không bắt buộc**; có thể viết `String[] parameters`. Phương thức `main` cũng có thể gọi các phương thức khác hoặc khởi tạo framework, rồi ứng dụng mới thực sự bắt đầu xử lý yêu cầu.

## 5. Thí nghiệm hoàn chỉnh Java 17+: quan sát lifecycle, tham số và PID

Tạo cấu trúc thư mục sau:

```text
jvm-launch-demo/
└── src/
    └── demo/
        └── LifecycleApp.java
```

Nội dung **`src/demo/LifecycleApp.java`**:

```java
package demo;

import java.util.Arrays;

public final class LifecycleApp {
    static {
        System.out.println("1. class initialized");
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("2. main entered");
        System.out.println("3. arguments: " + Arrays.toString(args));

        if (Arrays.asList(args).contains("--inspect")) {
            System.out.println("PID: " + ProcessHandle.current().pid());
            Thread.sleep(20_000);
        }

        System.out.println("4. main returning");
    }
}
```

Mở terminal ở thư mục **`jvm-launch-demo`** và chạy:

```bash
javac -d out src/demo/LifecycleApp.java
java -cp out demo.LifecycleApp alpha "two words"
```

**Stdout chính xác của lần chạy trên:**

```text
1. class initialized
2. main entered
3. arguments: [alpha, two words]
4. main returning
```

Giải thích từng điểm:

1. `javac -d out ...` biên dịch mã nguồn và tạo `out/demo/LifecycleApp.class`. `-d out` định vị thư mục gốc của cấu trúc package trong output.
2. `java -cp out demo.LifecycleApp ...` bắt đầu một **tiến trình Java mới**; `-cp out` chỉ ra nơi tìm lớp.
3. Trước khi `main` được gọi, JVM khởi tạo lớp nên dòng `1. class initialized` xuất hiện trước.
4. Launcher truyền hai tham số vào mảng `args`. Vì đã đặt dấu nháy quanh `"two words"`, đó là một tham số duy nhất gồm khoảng trắng.
5. Sau dòng `4. main returning`, phương thức `main` kết thúc bình thường. Nếu không còn luồng non-daemon nào giữ JVM hoạt động, quá trình shutdown bắt đầu.

Đổi đối số:

```bash
java -cp out demo.LifecycleApp
```

Khi đó dòng `3` là:

```text
3. arguments: []
```

**Quan sát PID và tiến trình đang sống:** chạy:

```bash
java -cp out demo.LifecycleApp --inspect
```

Lần này chương trình sẽ in thêm một dòng dạng `PID: <số thay đổi theo lần chạy>` rồi tạm ngủ khoảng 20 giây. **Không có một giá trị PID cố định** để đưa vào expected stdout, vì hệ điều hành cấp phát PID ở mỗi lần chạy.

Trong lúc tiến trình còn sống, có thể quan sát nó bằng Task Manager/Process Explorer trên Windows hoặc các công cụ quản lý tiến trình tương ứng trên Linux/macOS. Khi có JDK, thử lệnh:

```bash
jps -l
```

Công cụ `jps` có thể hiển thị tiến trình JVM đang chạy; trên một số môi trường/container hoặc với quyền truy cập hạn chế, nó không liệt kê được mọi tiến trình. Tìm tiến trình trước khi khoảng ngủ kết thúc. Có thể dùng `jcmd <PID> VM.command_line` khi `jcmd` có sẵn và đủ quyền; thay `<PID>` bằng giá trị in thực tế. Không nhập nguyên ký tự `<`/`>` trong lệnh shell.

**Quan sát quan hệ tiến trình:** chạy ứng dụng hai lần, mỗi lần với `--inspect`, từ hai terminal. Thông thường chúng in hai PID khác nhau. Mỗi lần class `LifecycleApp` được khởi tạo trong JVM riêng, nên khối `static` sẽ chạy trong mỗi tiến trình. Không tồn tại một bộ biến `static` chung tự động nối hai lần chạy.

## 6. Bốn cách chỉ định điểm vào cho Java launcher

Bốn chế độ khác nhau ở **cách tìm điểm vào và dependencies**, không thay đổi nguyên tắc thực thi bytecode, điều kiện kết thúc JVM hoặc ý nghĩa `main`.

| Chế độ | Câu lệnh minh họa | Cơ chế chọn lớp ban đầu |
| --- | --- | --- |
| **Class** | `java -cp out demo.LifecycleApp alpha` | Binary class name nằm trên classpath |
| **JAR** | `java -jar lifecycle-app.jar alpha` | `Main-Class` trong JAR manifest |
| **Named module** | `java --module-path mods -m com.example.app/com.example.app.Main alpha` | Resolve module và main class, cần module thực |
| **Source-file** | `java src/demo/LifecycleApp.java alpha` | Launcher Java 11+ biên dịch file nguồn rồi chạy class kết quả |

Với mã `LifecycleApp.java` đã biên dịch trong mục 5, có thể thử trực tiếp JAR mode:

~~~bash
jar --create --file lifecycle-app.jar --main-class demo.LifecycleApp -C out .
java -jar lifecycle-app.jar alpha "two words"
~~~

Các dòng output nghiệp vụ của `LifecycleApp` giống khi chạy class mode với cùng `args`. Với `-jar`, không được mặc định `-cp` cung cấp dependencies theo cùng cách class mode; hãy xem manifest và packaging. Module mode cần descriptor `module-info.java`, `--module-path` và artifact module phù hợp; ví dụ bảng không phải project module hoàn chỉnh. Source-file mode vẫn biên dịch class trong bộ nhớ, **không** phải JVM đọc trực tiếp cú pháp Java source.

Trên classpath có nhiều mục, Windows dùng dấu phân cách `;` và Linux/macOS dùng `:`. Bài chuyên đề về bốn chế độ launch phân tích sâu cơ chế này; ở bài tổng quan, điều cốt lõi là launcher có thể chọn điểm vào khác nhau **trước khi** chuyển quyền điều khiển cho cùng logic `main`.

## 7. `main` trả về chưa chắc tiến trình JVM đã kết thúc

Nhiều người thấy `main` là “điểm vào” rồi tưởng rằng **hễ `main` return thì JVM tắt ngay**. Điều này sai khi vẫn còn các **non-daemon thread** đang chạy.

Các điều kiện shutdown quan trọng theo API Java:

- JVM bắt đầu shutdown khi **không còn luồng non-daemon đang sống** (xét theo điều kiện của runtime), ngay cả khi trước đó `main` đã return.
- Lời gọi `System.exit(status)` yêu cầu runtime bắt đầu tiến trình shutdown với mã trạng thái.
- Một số sự kiện từ bên ngoài, ví dụ tín hiệu ngắt phù hợp, có thể khiến runtime bắt đầu shutdown; các cách cưỡng bức chấm dứt tiến trình không bảo đảm cùng hành vi.

Ví dụ **`BackgroundWorker.java`**:

```java
public class BackgroundWorker {
    public static void main(String[] args) {
        Thread worker = new Thread(() -> {
            try {
                Thread.sleep(1_000);
                System.out.println("worker finished");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "background-worker");

        worker.start(); // non-daemon theo mặc định khi được tạo từ main thread chuẩn
        System.out.println("main is finishing");
    }
}
```

Chạy:

```bash
javac BackgroundWorker.java
java BackgroundWorker
```

Trong lần chạy thông thường, hai dòng được in:

```text
main is finishing
worker finished
```

Dòng từ luồng worker thường xuất hiện sau khoảng một giây; thời điểm thực tế do hệ điều hành và scheduler quyết định. Điểm quan trọng là tiến trình **đợi luồng non-daemon** hoàn tất. Trên lý thuyết thời điểm các luồng được lập lịch có thể thay đổi; đừng dùng thứ tự log không có đồng bộ hóa làm chứng cứ tuyệt đối cho mọi lịch chạy.

Nếu `worker.setDaemon(true)` được gọi **trước** `worker.start()`, luồng đó không còn tự giữ JVM sống. Khi tất cả non-daemon thread đã kết thúc, daemon thread có thể bị dừng trong quá trình JVM kết thúc, kể cả khi nó chưa in dòng nào. Đừng dùng daemon thread cho tác vụ cần bảo đảm hoàn thành và lưu kết quả.

**Còn framework thì sao?** Một chương trình Spring Boot có thể khởi động server, thread pool và những thành phần duy trì vòng đời ứng dụng. Phương thức `main` thường gọi `SpringApplication.run(...)`; chuyện tiến trình tiếp tục sống phụ thuộc các luồng và cơ chế của ứng dụng/framework, không phải “`main` đang lặp vô hạn”.

## 8. Khi nào tiến trình thoát? Return, exit và dừng cưỡng bức

| Đường kết thúc | Điều kiện | Cleanup / kết quả |
| --- | --- | --- |
| **Tự nhiên** | `main` và non-daemon threads còn lại kết thúc | JVM bắt đầu shutdown, chạy registered hooks |
| **`System.exit(status)`** | Ứng dụng yêu cầu toàn JVM shutdown | Chạy hooks theo sequence; không tự đợi mọi worker hoặc unwind mọi `finally` |
| **`Runtime.halt(status)`** | Cưỡng bức dừng VM ngay | Bỏ qua hoặc cắt ngang hooks; nguy cơ mất dữ liệu |
| **Uncaught Java exception** | Thread mang lỗi chết trước | Không tự đồng nghĩa toàn JVM crash; các non-daemon khác có thể chạy tiếp |
| **OS kill / native fatal crash** | Process bị dừng ngoài đường Java thường | Không được bảo đảm hooks, logs hoặc cleanup |

Theo quy ước, `0` là exit status thành công, nonzero thường biểu thị lỗi, nhưng exit code không tự nói nguyên nhân dừng. Kiểu `void` của `main` Java 17 truyền thống không tự trả exit status; có thể gọi `System.exit(2)` khi cần một mã trạng thái, song nên đóng tài nguyên quan trọng **trước** lời gọi đó.

Đăng ký hook trong lúc JVM đang hoạt động bằng `Runtime.getRuntime().addShutdownHook(new Thread(...))`. Các hooks chạy đồng thời, không có thứ tự cố định; một hook đợi vô hạn có thể khiến shutdown treo. Khi bị `SIGKILL`, `Runtime.halt` hoặc mất điện, không được trông chờ hooks chạy. Dùng resource scopes, transactions và recovery thay vì coi hook là nơi duy nhất bảo vệ dữ liệu.

Như vậy **trả về từ main**, **một thread kết thúc**, **JVM shutdown có trình tự** và **tiến trình bị cưỡng bức dừng** là bốn sự kiện khác nhau. Những bài riêng trong chương đi sâu vào daemon/executor lifecycle, shutdown hooks và lỗi/exit-status.

## 9. Các lỗi thường gặp trước và sau `main`

| Biểu hiện | Thời điểm / nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `java` không được nhận diện | Shell chưa tìm thấy launcher | Kiểm tra JDK, `PATH`, đường dẫn tuyệt đối |
| `Could not find or load main class` | Sai tên lớp đầy đủ hoặc sai classpath | Kiểm tra `package`, `-cp` và vị trí `.class` |
| `Main method not found` | Không có điểm vào đúng hợp đồng của phiên bản launcher | Kiểm tra chữ ký `public static void main(String[] args)` |
| `UnsupportedClassVersionError` | Class file biên dịch cho phiên bản mới hơn JVM đang chạy | Kiểm tra `java -version` và cấu hình biên dịch như `--release` |
| `NoClassDefFoundError` | Class phụ thuộc không khả dụng khi runtime cần sử dụng | Kiểm tra classpath/module path và dependency runtime |
| `ExceptionInInitializerError` | Lỗi không được xử lý trong khởi tạo tĩnh | Đọc nguyên nhân gốc từ stack trace và mã `static` |
| `No main manifest attribute` | JAR không chỉ định main class | Kiểm tra manifest, lệnh tạo JAR, hoặc dùng class mode |
| Chương trình đã in “main done” nhưng vẫn chạy | Còn non-daemon thread, server, executor, hook… | Xem thread dump/log, quản lý vòng đời thread và tài nguyên |
| JVM dừng quá sớm, worker chưa xong | Task chạy trên daemon thread hoặc bị cưỡng bức kết thúc | Đồng bộ tác vụ, đóng executor có kiểm soát, xem exit code |

Một lỗi phát sinh **trước `main`** thường thuộc các bước tìm lớp, liên kết, khởi tạo lớp, cấu hình hoặc kiểm tra điểm vào. Một lỗi **sau `main`** có thể do nghiệp vụ, luồng, tác vụ nền, I/O hoặc shutdown. Phân loại đúng thời điểm giúp tìm nguyên nhân nhanh hơn.

## 10. Kỹ thuật kiểm tra thực tế

**Kiểm tra Java nào đã chạy:** dùng `java -version` và cách tra đường dẫn lệnh của shell (PowerShell `Get-Command java` hoặc Bash `command -v java`). Không mặc định `JAVA_HOME` luôn quyết định chính xác launcher khi `PATH` chứa nhiều JDK.

**Xác minh class và JAR:** với ví dụ đã biên dịch, kiểm tra thư mục `out/demo/LifecycleApp.class`. Có thể dùng `jar --list --file lifecycle-app.jar` để xem các mục trong JAR và `jar --describe-module --file ...` khi đang điều tra artifact dạng module phù hợp. Cần kiểm tra manifest nếu `java -jar` không tìm ra main class.

**Quan sát tiến trình hiện tại:** `ProcessHandle.current().pid()` trong Java 17+ trả PID của tiến trình hiện tại. Cùng với `jps`/`jcmd` (khi môi trường cho phép), điều này giúp phân biệt một tiến trình Java chưa thoát với một lần chạy khác vừa khởi động lại.

**Chẩn đoán JVM không thoát:** kiểm tra thread đang sống và trạng thái daemon/non-daemon bằng thread dump hoặc debugger; tìm thread pool/executor không được đóng, server listener vẫn hoạt động hoặc shutdown hook đang treo. Đừng sửa bằng cách gọi `System.exit(0)` một cách máy móc vì có thể bỏ qua quy trình hoàn tất công việc đang chạy.

**Xem lệnh mà JVM nhận:** với JDK có hỗ trợ và có quyền phù hợp, lệnh `jcmd <PID> VM.command_line` hữu ích để đối chiếu JVM options với tham số khởi động; `jcmd <PID> Thread.print` có thể hỗ trợ kiểm tra thread. Đây là công cụ chẩn đoán gắn với triển khai/JDK, nên khả năng hỗ trợ có thể khác nhau.

**Khi chọn phiên bản Java:** nếu cần chạy trên runtime Java 17, có thể dùng JDK biên dịch hỗ trợ tùy chọn `--release 17`:

```bash
javac --release 17 -d out src/demo/LifecycleApp.java
```

Tùy chọn này đặt mức ngôn ngữ, class file và bề mặt Java SE API đích trong phạm vi compiler hỗ trợ; vẫn phải kiểm tra các thư viện bên thứ ba, môi trường hệ điều hành và cấu hình runtime riêng.

## 11. Tự kiểm tra

**Câu 1.** Trong lệnh `java -Xmx256m -cp out demo.LifecycleApp hello`, tham số của `main` là gì?

**Đáp án:** `args` gồm một chuỗi `"hello"`. Các tùy chọn `-Xmx256m` và `-cp out` thuộc launcher/runtime.

**Câu 2.** Vì sao chương trình có thể in nội dung từ khối `static` trước câu lệnh đầu tiên trong `main`?

**Đáp án:** JVM khởi tạo lớp chính, thực thi các bộ khởi tạo tĩnh cần thiết trước khi gọi `main`.

**Câu 3.** Hai terminal chạy cùng một class; liệu chúng cùng chia sẻ một biến `static int counter`?

**Đáp án:** Thông thường không. Hai lần khởi chạy `java` tạo hai tiến trình/JVM với vùng nhớ độc lập.

**Câu 4.** `main` đã return nhưng tiến trình vẫn xuất hiện trong Task Manager. Có chắc JVM bị treo không?

**Đáp án:** Không. Một thread non-daemon, server, executor hoặc shutdown hook có thể vẫn đang hoạt động. Phải quan sát thread và vòng đời ứng dụng trước khi kết luận.

**Câu 5.** Vì sao `java -jar app.jar` khác `java -cp app.jar demo.Main`?

**Đáp án:** `-jar` lấy lớp đầu vào từ `Main-Class` của manifest; class mode dùng tên lớp chính trên dòng lệnh và classpath. Quy tắc classpath khi dùng `-jar` cũng khác với class mode.

**Câu 6.** Nếu tệp `.class` đã được biên dịch, máy đích nhất thiết phải có `javac` không?

**Đáp án:** Không. Nó cần một môi trường runtime/JVM tương thích để chạy class và các dependency cần thiết; `javac` chỉ cần cho bước biên dịch.

## 12. Tổng kết bằng một chuỗi trách nhiệm

```text
Shell              : chọn và gọi chương trình java
Hệ điều hành       : tạo/quản lý tiến trình, PID, tài nguyên
Java launcher      : diễn giải options, chọn class/JAR/module/source
JVM                : chuẩn bị runtime, nạp/liên kết/khởi tạo lớp, thực thi bytecode
main(String[])     : điểm vào logic của ứng dụng; nhận application args
Các thread ứng dụng: quyết định công việc tiếp tục chạy sau main hay không
Shutdown           : điều kiện kết thúc, hooks, mã thoát của tiến trình
```

Nắm ranh giới này giúp giải thích **vì sao class không tìm thấy, vì sao khối `static` chạy trước `main`, vì sao `main` return mà JVM còn sống, vì sao PID thay đổi qua mỗi lần chạy, và vì sao `java -jar` khác `java -cp`**. Đây là nền tảng để học sâu hơn về class loading, memory areas, thread lifecycle, JIT và chẩn đoán JVM.

### Tài liệu chính thức tham khảo

- [The `java` Command — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): chế độ khởi chạy class/JAR/module/source và cú pháp đối số.
- [Java Language Specification `12: Execution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html): nạp, liên kết, khởi tạo lớp và lời gọi `main`.
- [`java.lang.Runtime` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html): shutdown sequence, hooks, exit và halt.
- [`java.lang.Thread` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): thread và quan hệ với điều kiện JVM shutdown.
