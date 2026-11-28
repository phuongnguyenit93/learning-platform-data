# Xử lý lỗi điểm vào chương trình và tương thích với launcher, IDE, công cụ đóng gói

## 1. Mục tiêu và tình huống thực tế

Khi học Java 25, ta có thể viết một chương trình chỉ bằng vài dòng trong tệp nguồn gọn (**compact source file**), dùng một phương thức **instance main** mà không cần khai báo lớp tường minh. Chương trình chạy được khi gọi **java Hello.java**, nhưng có thể không xuất hiện nút Run trong IDE cũ, bị công cụ đóng gói báo không tìm thấy main class hoặc thất bại khi chạy JAR trên một JDK thấp hơn.

Bài **Xử lý lỗi điểm vào chương trình và tương thích với launcher, IDE, công cụ đóng gói**, thuộc chương **Hàm main** của **JAVA_VERSION_JAVA25**, hướng dẫn tìm đúng nguồn lỗi thay vì thay đổi cú pháp main một cách tùy tiện. Kiến thức áp dụng cho các chương trình nguồn gọn, ứng dụng dòng lệnh, bài thực hành Java 25 và dự án đóng gói để phân phối.

Sau bài này, bạn có thể:

1. Phân biệt **lỗi biên dịch**, **lỗi chọn entry point**, **lỗi khởi tạo instance**, **lỗi classpath/module path**, **lỗi JAR manifest** và **lỗi do ứng dụng ném ra sau khi chạy main**.
2. Áp dụng đúng quy tắc chọn main trong Java 25, gồm **static/instance**, **có hoặc không có String[]**, phương thức truy cập được và constructor phù hợp.
3. Chạy compact source file bằng launcher, sau đó chuyển sang lớp tường minh để IDE, Maven/Gradle và công cụ đóng gói có một định danh entry point ổn định.
4. Tách logic trả mã trạng thái khỏi điểm vào main để kiểm thử và xử lý lỗi dòng lệnh nhất quán.
5. Chẩn đoán vấn đề tương thích khi đưa chương trình vào JAR, jpackage, CI hoặc runtime image.

**Phạm vi phiên bản:** Java 25 là dòng LTS; **JEP 512 – Compact Source Files and Instance Main Methods** đã được hoàn thiện trong Java 25. Không cần **--enable-preview** để dùng riêng hai khả năng này. Tránh sao chép nguyên các ví dụ preview của Java 21–24: trong Java 25, lớp **java.lang.IO** tồn tại và lời gọi in ra console cần viết **IO.println(...)** (hoặc System.out.println), không mặc định dùng hàm **println(...)** độc lập như một số bản preview cũ.

## 2. Java 25 có những kiểu main nào?

Trong Java 25, launcher có thể gọi phương thức main đáp ứng một trong hai hình dạng: **void main(String[] args)** hoặc **void main()**. Phương thức có thể là **static** hoặc **instance**, với quyền truy cập **public**, **protected** hoặc **package-private**; **private main** không phải candidate được launcher chọn. Dấu **String... args** có cùng dạng tham số mảng như **String[] args**.

| Khai báo trong một lớp có thể khởi chạy | Có là launchable main trong Java 25? | Ghi chú |
| --- | --- | --- |
| **public static void main(String[] args)** | Có | Hình thức phổ biến; rất phù hợp với công cụ đóng gói và hệ sinh thái. |
| **static void main(String[] args)** | Có | Không bắt buộc public trong Java 25. |
| **void main(String[] args)** | Có | Instance main; cần tạo instance của lớp trước khi gọi. |
| **public static void main()** | Có | Không nhận tham số dòng lệnh. |
| **void main()** | Có | Instance main không tham số, phù hợp compact source file. |
| **protected void main()** | Có, với constructor phù hợp | Java 25 cho phép protected. |
| **private static void main(String[] args)** | Không | Private không được launcher coi là candidate. |
| **int main(String[] args)** | Không | Phải trả về **void**, không trả số nguyên làm exit code. |
| **void main(String arg)** | Không | Một String đơn lẻ không phải String[]. |
| **void main(String[] args, int n)** | Không | Có hai tham số nên sai hình dạng. |

**Quy tắc ưu tiên:** nếu có một candidate **main(String[])**, launcher chọn nó trước **main()**, bất kể một trong hai là static hay instance. Nếu không có candidate với mảng String, launcher mới chọn candidate không tham số. Không nên suy luận rằng static sẽ được ưu tiên hơn instance.

Ví dụ lưu thành **PickMain.java**:

~~~java
class PickMain {
    static void main() {
        System.out.println("KHONG CHON");
    }

    void main(String[] args) {
        System.out.println("CHON: " + String.join(",", args));
    }
}
~~~

Chạy bằng JDK 25:

~~~bash
java PickMain.java A B
~~~

Kết quả:

~~~text
CHON: A,B
~~~

**Vì sao?** Candidate có tham số **String[]** được chọn trước, dù nó là instance main, còn static main không tham số bị bỏ qua. Một class không thể đồng thời khai báo **static** và **instance** main có *cùng chữ ký* vì Java không phân biệt method overload chỉ bằng static.

### 2.1. Instance main cần constructor có thể dùng được

Launcher phải tạo một instance để gọi instance main. Với lớp tường minh, cần constructor **không tham số** và **không private** (public/protected/package-private) theo quy tắc Java 25. Một constructor chỉ nhận tham số hoặc constructor không tham số nhưng private có thể khiến việc launch thất bại, ngay cả khi code biên dịch được.

~~~java
class NeedsConstructor {
    private NeedsConstructor() {} // Không phù hợp cho instance main.

    void main() {
        System.out.println("Khong the launch theo quy tac Java 25");
    }
}
~~~

**Sửa:** sử dụng constructor không tham số có quyền truy cập thích hợp hoặc chuyển entry point sang static main nếu không cần trạng thái instance. Đừng biến mọi constructor thành public không cần thiết; chỉ cần thiết kế điểm vào rõ ràng.

Compact source file có lớp **được khai báo ngầm** với default constructor, nên ví dụ đơn giản **void main()** không gặp vấn đề trên. Khi chuyển từ nguồn gọn sang lớp tường minh có constructor tùy chỉnh, phải kiểm tra lại điều kiện này.

## 3. Chạy compact source file bằng launcher Java 25

Lưu **Hello.java**:

~~~java
void main(String[] args) {
    String who = args.length == 0 ? "world" : args[0];
    IO.println("Hello, " + who + "!");
}
~~~

Chạy:

~~~bash
java --version
java Hello.java
java Hello.java Lan
~~~

Kết quả của hai lệnh cuối:

~~~text
Hello, world!
Hello, Lan!
~~~

Đây là **source-file mode**: launcher biên dịch nguồn rồi chạy trực tiếp, không cần thao tác tạo JAR hoặc gọi **javac** trước. Java 25 có thể dùng **IO.println** nhờ lớp **java.lang.IO**, và compact source file tự có phạm vi import các kiểu public từ các package mà module **java.base** export. Khi cần, vẫn có thể dùng **System.out.println**.

**Không cần --enable-preview** cho compact source file/instance main đã finalized trong Java 25. Nếu tài liệu cũ đề nghị **java --enable-preview --source 22 Hello.java** cho tính năng này, đó là ví dụ gắn với giai đoạn preview cũ, không phù hợp làm hướng dẫn Java 25 hiện hành.

### 3.1. Phân biệt các cách gọi launcher

| Lệnh | Điều launcher xử lý | Cần chuẩn bị |
| --- | --- | --- |
| **java Hello.java** | Source-file mode, compile và launch tệp nguồn. | Có **Hello.java**, JDK 25. |
| **javac Hello.java** | Biên dịch ra class file. | JDK 25 và nguồn hợp lệ. |
| **java Hello** | Class launch mode, tải class tên Hello từ classpath. | Class file và tên class phù hợp; với compact file, tên biên dịch là chi tiết triển khai. |
| **java -cp out demo.Main** | Class launch mode theo tên fully qualified class. | Đã compile **demo.Main** vào **out**. |
| **java -jar app.jar** | JAR launch mode, đọc **Main-Class** từ manifest. | JAR chứa main class, manifest và dependencies. |
| **java -m demo.app/demo.Main** | Named-module launch mode. | Module descriptor và module path phù hợp. |

Với compact file **Hello.java**, compiler JDK 25 có thể sinh **Hello.class** khi gọi **javac Hello.java** và sau đó **java Hello** hoạt động. Tuy nhiên, **tên lớp khai báo ngầm là chi tiết do compiler chọn** và không thể tham chiếu trực tiếp từ mã Java nguồn. Vì vậy, **không nên xây quy trình đóng gói lâu dài dựa trên tên class ngầm**; hãy chuyển sang lớp tường minh trước khi cần một entry point ổn định cho manifest, plugin, IDE hoặc công cụ khác.

### 3.2. Source mode khi có nhiều class

Khi tệp nguồn chứa nhiều **top-level class tường minh**, source-file mode chọn **top-level class xuất hiện đầu tiên trong tệp** để launch. Nó không tự dò tìm mọi class cho đến khi gặp main hợp lệ.

Ví dụ lưu **TwoClasses.java**:

~~~java
class Helper {
    static String message() {
        return "hello";
    }
}

class Application {
    static void main() {
        System.out.println(Helper.message());
    }
}
~~~

Gọi **java TwoClasses.java** có thể báo không tìm thấy main của **Helper**, vì Helper là lớp top-level đầu tiên. **Sửa:** đưa lớp Application có launchable main lên trước hoặc tách thành các tệp nguồn/lớp rõ ràng, rồi compile và chạy theo tên class.

**Lưu ý:** đây là quy tắc lựa chọn *lớp* của source-file mode; nó khác quy tắc ưu tiên lựa chọn *phương thức main* trong một lớp.

## 4. Tạo lớp entry point tường minh khi chương trình lớn dần

Compact source file rất phù hợp bài học, thí nghiệm và công cụ nhỏ. Khi chương trình có **package**, nhiều lớp, unit test, dependency, installer hoặc cần plugin chỉ định main class, chuyển sang lớp tường minh sẽ giúp build lặp lại và giảm phụ thuộc vào hành vi nhận diện của từng IDE.

Ví dụ:

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        String who = args.length == 0 ? "world" : args[0];
        System.out.println("Hello, " + who + "!");
    }
}
~~~

Giả sử lưu ở **src/demo/Main.java**, có thể compile/run từ thư mục dự án:

~~~bash
javac --release 25 -d out src/demo/Main.java
java -cp out demo.Main Lan
~~~

Ở đây:

- **demo.Main** là tên lớp đầy đủ gồm package và class, không phải **src/demo/Main.java**.
- **--release 25** yêu cầu compiler dùng cú pháp, API nền tảng và bytecode Java 25.
- **-d out** đưa **demo/Main.class** vào đúng cấu trúc package; **-cp out** cho class launcher biết root classpath.
- Java runtime cần đủ mới để đọc class file Java 25 (major **69**).

**Hình thức public static void main(String[] args) không lỗi thời.** Nó vẫn là lựa chọn thực tiễn cho ứng dụng phân phối rộng, đặc biệt khi IDE cũ, plugin hoặc integration code dùng phép nhận diện main truyền thống. Java 25 *mở rộng* các hình thức hợp lệ, không bắt buộc chuyển mọi ứng dụng hiện có sang instance main.

### 4.1. Không nhầm chương trình nguồn gọn với package được đặt tên

Trong Java 25, compact source file khai báo **lớp ngầm** thuộc **unnamed package** và **unnamed module**. Khi một ứng dụng cần package có tên, module-info, API được các lớp khác gọi hoặc artifact đóng gói ổn định, chuyển sang class declaration tường minh. Đừng chỉ thêm **package demo;** trước một tập method top-level rồi kỳ vọng compact source file vẫn hợp lệ theo cùng cơ chế.

## 5. Lỗi điểm vào khác lỗi bên trong ứng dụng

Không phải lỗi nào xuất hiện ngay lúc chạy cũng là lỗi **main method**. Phân tầng theo tiến trình:

~~~mermaid
flowchart TD
    A["java launcher nhận lệnh"] --> B{"Nguồn / class / JAR / module có tìm thấy?"}
    B -->|Không| E1["Lỗi đường dẫn, classpath, module path, manifest"]
    B -->|Có| C{"Bytecode và main hợp lệ?"}
    C -->|Không| E2["Lỗi JDK, signature, constructor, lựa chọn class"]
    C -->|Có| D["Tạo instance nếu cần; gọi main"]
    D --> F{"Logic xử lý hoàn tất?"}
    F -->|Không| E3["Lỗi tham số, I/O, dependency, khởi tạo, exception"]
    F -->|Có| G["Exit 0 / hoàn thành"]
~~~

**Phân loại đầu tiên cần ghi trong báo cáo sự cố:** compiler có báo lỗi trước khi chạy không? Launcher có nêu class/method không hợp lệ không? Hay main đã bắt đầu và chính code ứng dụng ném exception?

| Triệu chứng | Tầng lỗi | Nguyên nhân thường gặp |
| --- | --- | --- |
| **cannot find symbol: IO** | Biên dịch | Compiler không phải JDK 25 hoặc cấu hình release cũ. |
| **class, interface, enum, or record expected** ở phương thức top-level | Biên dịch | Biên dịch nguồn gọn bằng release/IDE cũ không hỗ trợ compact source file. |
| **Main method not found** | Launch | Chỉ có private main, main sai chữ ký, hoặc source mode chọn nhầm lớp. |
| Không tạo được instance của main class | Launch | Instance main nhưng không có constructor không tham số phù hợp. |
| **Could not find or load main class** | Class loading | Dùng sai fully qualified class name, classpath hoặc output directory. |
| **NoClassDefFoundError** | Class loading/linking | Thiếu dependency hoặc cấu trúc package/classpath không khớp. |
| **UnsupportedClassVersionError** | Runtime compatibility | Bytecode build bằng Java 25 nhưng runtime quá cũ. |
| **no main manifest attribute** | JAR packaging | Không đặt **Main-Class** trong manifest. |
| **Unable to access jarfile** | JAR launch | Đường dẫn/file JAR không tồn tại hoặc không đọc được. |
| Stack trace sau khi in **Starting...** | Application | main đã được gọi; lỗi nằm trong logic, dependency hoặc khởi tạo tiếp theo. |

Với lỗi main, hãy trích **lệnh chạy đầy đủ**, **stderr**, **exit status**, **JDK thực thi** và tên class/JAR. Chỉ xem đoạn code main thường chưa đủ để tìm nguyên nhân.

## 6. Thiết kế CLI xử lý lỗi và exit status rõ ràng

Java main vẫn trả **void**, kể cả trong Java 25. Muốn trả kết quả cho shell, không viết **int main()**. Thay vào đó, có thể tổ chức ứng dụng thành:

1. **main** làm adapter của launcher, gọi hàm nghiệp vụ.
2. **run** hoặc **execute** trả về một mã kết quả có thể kiểm thử.
3. **main** chỉ gọi **System.exit(code)** khi thực sự cần chuyển mã lỗi cho process ngoài cùng.

Ví dụ lớp tường minh **src/demo/CountMain.java**:

~~~java
package demo;

public final class CountMain {
    public static void main(String[] args) {
        int exitCode = new CountMain().run(args);
        if (exitCode != 0) {
            System.exit(exitCode);
        }
    }

    int run(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java demo.CountMain <non-negative-number>");
            return 2; // Ví dụ: lỗi cách dùng CLI.
        }
        try {
            int count = Integer.parseInt(args[0]);
            if (count < 0) {
                System.err.println("Number must be non-negative");
                return 2;
            }
            System.out.println("count=" + count);
            return 0;
        } catch (NumberFormatException ex) {
            System.err.println("Not an integer: " + args[0]);
            return 2;
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 25 -d out src/demo/CountMain.java
java -cp out demo.CountMain 3
java -cp out demo.CountMain invalid
~~~

Kết quả nghiệp vụ thành công in **count=3** và process kết thúc với mã **0**. Khi tham số sai, chương trình in thông báo lên **stderr** rồi kết thúc với mã **2** do code ví dụ chủ động chọn. **0** thường là thành công, còn **non-zero** báo thất bại; cần quy ước số mã lỗi nhất quán giữa ứng dụng và shell script.

### 6.1. Đừng System.exit trong code khó kiểm thử

Lỗi phổ biến là gọi **System.exit(...)** sâu bên trong service, khiến unit test hoặc IDE Run dừng toàn bộ JVM. Tốt hơn hãy trả kết quả/throw exception từ logic, rồi đổi thành exit code tại boundary của ứng dụng CLI.

Ví dụ JUnit test chỉ kiểm tra **run**:

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CountMainTest {
    @Test
    void returnsUsageErrorForBadInput() {
        assertEquals(2, new CountMain().run(new String[] {"oops"}));
    }

    @Test
    void returnsSuccessForValidInput() {
        assertEquals(0, new CountMain().run(new String[] {"3"}));
    }
}
~~~

Test này không yêu cầu chặn **System.exit** hoặc dựng thêm process. Muốn kiểm tra **exit status thực** của launcher, viết integration test khởi chạy một JVM con (**ProcessBuilder**) và so exit status, stdout, stderr; không chỉ gọi trực tiếp main trong cùng JVM.

### 6.2. Exception ở main không phải lỗi chọn main

Nếu launcher tìm thấy main rồi code ném exception chưa xử lý, JVM sẽ báo stack trace và process thường kết thúc không thành công. Xử lý exception tại biên CLI khi có thể cung cấp thông báo hữu ích; để exception bất ngờ hiển thị stack trace trong môi trường phát triển nhưng tránh lộ secrets/thông tin nhạy cảm ở môi trường phân phối.

Không dùng **catch (Throwable)** để nuốt mọi lỗi hệ thống. Phân biệt lỗi nhập liệu, I/O, cấu hình và lỗi lập trình. Trong ứng dụng server/framework, tránh chủ động gọi **System.exit** trong service hoặc listener.

## 7. Truyền tham số dòng lệnh đúng vị trí

Tham số truyền cho main nằm **sau** tên lớp, tệp nguồn hoặc tên JAR; JVM options thường đứng **trước** entry point.

~~~bash
java -Xmx256m Hello.java Lan
java -Xmx256m -cp out demo.Main Lan
java -Xmx256m -jar dist/demo.jar Lan
~~~

Ở dòng đầu, launcher chọn source mode vì **Hello.java** là tệp nguồn; **Lan** được truyền vào **args[0]** nếu main dùng **String[]**. Nếu main là **void main()**, nó không nhận mảng args; lời gọi vẫn có thể chạy nhưng không có cách truy cập các đối số qua tham số main.

**Sai vị trí:** viết **java Hello.java -Xmx256m** sẽ khiến **-Xmx256m** là một argument của chương trình, không phải thiết lập memory của JVM. Với **java -jar**, các phần tử sau tên JAR cũng là application arguments; tùy tiện đặt **-cp** ở sau JAR không bổ sung dependency như bạn nghĩ.

**Khuyến nghị:** tạo parser/validation rõ ràng cho CLI có nhiều options và test với bộ args thực tế. Đừng lấy String args bằng cách ghép thành một chuỗi shell rồi parse lại thủ công, vì dễ lỗi ký tự trắng và escaping.

## 8. IDE: nhận diện entry point và cấu hình JDK

IDE hiện đại có thể chạy main với nhiều dạng hợp lệ trong Java 25, nhưng **khả năng nhận diện nút Run do phiên bản IDE/plugin quyết định**. Ngay cả khi JDK 25 launcher chạy tốt trên terminal, IDE hoặc build plugin cũ có thể chỉ tìm **public static void main(String[])** bằng quy tắc cổ điển.

### 8.1. IntelliJ IDEA, Eclipse và VS Code

Kiểm tra theo thứ tự:

1. IDE, Java language server/JDT và plugin được **cập nhật tới phiên bản hỗ trợ Java 25**.
2. **Project SDK**, **compiler language level/release** hoặc Gradle/Maven toolchain được đặt đúng **25**.
3. **Run/Debug Configuration** sử dụng JDK 25, đúng **main class** nếu chạy class mode, hoặc đúng **source file** nếu chạy source mode.
4. Với compact source file, thử **java Hello.java** trong terminal tích hợp IDE để xác nhận compiler/launcher; sau đó mới chẩn đoán việc IDE không hiện nút Run.
5. Nếu công cụ chạy ứng dụng chưa hỗ trợ main dạng mới, dùng **lớp entry point tường minh** và **public static void main(String[] args)** ở boundary để giữ tương thích, trong khi mã nghiệp vụ vẫn dùng các API Java 25.

| Môi trường | Chỗ dễ lệch | Cách tìm |
| --- | --- | --- |
| **IntelliJ IDEA** | Project SDK khác Run JRE/Gradle JVM. | Project Structure, Gradle JVM, Run Configuration và terminal tích hợp. |
| **Eclipse JDT** | Compiler compliance/JRE khác Java 25, plugin Java cũ. | Installed JREs, Java Compiler, Run Configurations. |
| **VS Code Java** | Language server runtime khác debug runtime hoặc terminal. | Java: Configure Java Runtime, Java extension và launch config. |
| **Maven/Gradle import** | IDE phát hiện main theo bytecode hoặc cấu hình plugin cũ. | Chạy từ wrapper trước, kiểm tra output và run task của IDE. |

Đừng đổi source code hàng loạt vì một biểu tượng Run chưa hiện. Trước hết kiểm tra hỗ trợ Java 25 trong IDE; nếu mục tiêu là **artifact phân phối**, class entry point tường minh vẫn là quyết định ổn định.

### 8.2. Nhận diện lỗi do JDK khác

Trong chính chương trình có thể in:

~~~java
System.out.println(Runtime.version());
System.out.println(System.getProperty("java.home"));
~~~

Nếu terminal chạy bằng Java 25 còn IDE chạy Java 21, compact source file có thể không được biên dịch hoặc class file 69 không được nạp. Đây là lỗi **môi trường/JDK**, không phải lỗi chọn main theo Java 25.

## 9. Đóng gói JAR: Main-Class là tên lớp, không phải đường dẫn nguồn

Để chạy bằng **java -jar**, JAR cần manifest với **Main-Class** chỉ định **fully qualified name** của class được launcher khởi chạy. Khi giao cho người dùng, đừng buộc họ biết vị trí tệp **Hello.java** trong source tree.

Ví dụ sử dụng lớp tường minh **demo.Main** ở mục 4. Chạy trong Bash/Zsh:

~~~bash
mkdir -p out dist
javac --release 25 -d out src/demo/Main.java
jar --create --file dist/demo.jar --main-class demo.Main -C out .
jar --describe-module --file dist/demo.jar
java -jar dist/demo.jar Lan
~~~

**Lưu ý về ví dụ:** lệnh **jar --describe-module** có thể mô tả JAR như **automatic module** nếu không có module-info; nó không phải bước bắt buộc để chạy JAR ở classpath. Có thể bỏ lệnh này nếu mục tiêu chỉ là xác minh manifest và chạy. Để xem manifest:

~~~bash
unzip -p dist/demo.jar META-INF/MANIFEST.MF
~~~

**unzip** là tiện ích thường có trên Linux/macOS, có thể thiếu trên Windows. Trên Windows, dùng công cụ ZIP phù hợp để kiểm tra **META-INF/MANIFEST.MF**. Manifest cần có một dòng tương tự:

~~~text
Main-Class: demo.Main
~~~

Với PowerShell, thay bước tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force out, dist | Out-Null
~~~

Phần còn lại dùng **javac**, **jar** và **java** từ JDK 25 có thể thực thi trong PowerShell.

**Java 25 launcher có giao thức main mới**, nhưng **plugin hoặc trình phát hiện main class bên ngoài JDK** có thể vẫn nhận diện main theo chữ ký cũ. Vì vậy khi phát hành JAR bằng Maven/Gradle, khuyến nghị giữ lớp **public static void main(String[] args)** tường minh để cải thiện tương thích rộng. Đó là lựa chọn thiết kế, không phải tuyên bố rằng Java 25 cấm instance main trong JAR.

### 9.1. Những lỗi manifest thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| **no main manifest attribute** | JAR không có Main-Class. | Cấu hình jar plugin/manifest hoặc **jar --main-class**. |
| **Could not find or load main class** | Giá trị Main-Class sai tên package hoặc class không có trong JAR. | Kiểm tra đường dẫn **demo/Main.class** và manifest. |
| **NoClassDefFoundError** khi main bắt đầu | Dependency runtime không có trên classpath/module path. | Đóng gói dependency phù hợp, kiểm tra Class-Path hoặc dùng distribution build hợp lệ. |
| **UnsupportedClassVersionError** | JAR biên dịch release 25 nhưng runtime thấp hơn. | Dùng Java 25 runtime hoặc build cho target thấp hơn nếu code hỗ trợ. |

**Một JAR có manifest không tự động là fat/uber JAR.** Ví dụ **jar --create** chỉ đóng gói các class trong **out**; nếu ứng dụng cần thư viện bên ngoài, phải phân phối dependency qua classpath, plugin tạo executable distribution hoặc cơ chế đóng gói của framework. Với Spring Boot, executable Boot JAR có cấu trúc launcher/manifest riêng; dùng plugin Boot tương thích thay vì tự chép một Main-Class tùy ý.

## 10. jpackage: tạo launcher ứng dụng từ JAR/module

**jpackage** của JDK 25 tạo application image hoặc native installer theo hệ điều hành. Nó không trực tiếp nhận tệp compact source file như một entry point ổn định: bạn cần một **main JAR** hoặc **named module**, rồi chỉ định class/module để launch.

Sau khi có **dist/demo.jar**:

~~~bash
jpackage --type app-image \
  --name DemoMain \
  --input dist \
  --main-jar demo.jar \
  --main-class demo.Main \
  --dest package-out
~~~

Ví dụ dùng cú pháp nối dòng Bash; trên Windows PowerShell có thể viết một dòng:

~~~powershell
jpackage --type app-image --name DemoMain --input dist --main-jar demo.jar --main-class demo.Main --dest package-out
~~~

Lựa chọn **--type app-image** tạo ứng dụng và runtime image, hữu ích để thử launcher trước khi tạo installer. **jpackage** hỗ trợ các loại package khác nhau tùy OS; muốn tạo gói cài đặt native có thể cần công cụ hệ điều hành bổ sung. Khi ứng dụng có dependency ngoài hoặc module dependencies, cần cung cấp đầy đủ trong input/module path và kiểm tra output thực.

**Không nhầm option:** **--main-class** là tên lớp, không phải chữ ký main hoặc đường dẫn .java. **--main-jar** trỏ tới JAR trong **--input**. Khi dùng **--module**, công cụ nhận **module[/main-class]** trên module path; không chỉ định đồng thời hai chế độ **--main-jar** và **--module**.

### 10.1. Smoke test bắt buộc sau packaging

1. Chạy **java -jar dist/demo.jar Lan** trước khi tạo application image.
2. Chạy executable được tạo trong **package-out** (đường dẫn phụ thuộc OS) với tham số **Lan**.
3. Kiểm tra stdout/stderr và exit status; xác nhận output khớp bản JAR.
4. Xác nhận image chứa Java runtime tương thích class file Java 25.
5. Nếu đóng gói trên các OS khác nhau, tạo và thử image trên **mỗi OS đích**; không giả định package Windows chạy trên Linux.

Đối với command-line app, kiểm tra việc wrapper có hiển thị stdout/stderr như mong đợi trên hệ điều hành đó. Một ứng dụng đóng gói thành GUI launcher có thể không hiển thị console dù logic main đã chạy.

## 11. Maven và Gradle: cấu hình entry point tường minh

### 11.1. Gradle application plugin

Ví dụ **build.gradle.kts**:

~~~kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

application {
    mainClass = "demo.Main"
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(25)
}
~~~

Gradle Application plugin tạo nhiệm vụ **run** và distribution với entry point **demo.Main**. Kiểm tra toolchain, plugin và Gradle wrapper đều hỗ trợ Java 25. Với Gradle Java 25, dùng bản Gradle tương thích theo **Gradle Compatibility Matrix**; đừng chỉ đặt Java 25 nhưng vẫn giữ Gradle/plugin quá cũ.

Các lệnh kiểm thử trong dự án tương ứng:

~~~bash
./gradlew --version
./gradlew run --args="Lan"
./gradlew installDist
~~~

**mainClass** phải trỏ tới class được compile trong source set phù hợp; nếu chỉ có tệp compact source file và plugin không nhận diện entry point, chuyển sang explicit class là cách chắc chắn hơn khi cần phát hành distribution.

### 11.2. Maven JAR manifest

Với dự án Maven có compiler configuration Java 25, có thể khai báo **maven-jar-plugin**:

~~~xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <configuration>
                <archive>
                    <manifest>
                        <mainClass>demo.Main</mainClass>
                    </manifest>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **trích đoạn bổ sung vào POM hiện có**, không phải POM hoàn chỉnh. Nên dùng phiên bản plugin được parent/BOM hoặc tổ chức quản lý. **maven.compiler.release=25** kiểm soát target API/bytecode; **mainClass** kiểm soát manifest. Hai thiết lập giải quyết hai việc khác nhau.

Nếu chương trình phụ thuộc các thư viện khác, Maven JAR plugin không tự gói toàn bộ thư viện vào một JAR. Hãy dùng giải pháp packaging/distribution phù hợp hoặc plugin application/framework của dự án. Để build có thể tái lập, ghi versions của compiler, jar plugin và JDK, đừng dựa vào mặc định của máy.

## 12. CI và runtime: tránh “works on my machine”

Trong pipeline, hãy kiểm tra thực tế:

~~~bash
java --version
javac --version
java Hello.java Lan
javac --release 25 -d out src/demo/Main.java
java -cp out demo.Main Lan
java -jar dist/demo.jar Lan
~~~

Với lệnh cuối cần tạo **dist/demo.jar** ở bước đóng gói trước đó. Nếu CI thiếu tệp này, lỗi đường dẫn JAR không phải do main. Một pipeline Java 25 nên có **JDK 25**, toolchain/release 25, kiểm thử, build artifact, sau đó chạy smoke test **artifact thực tế** trên JVM tương thích.

| Kiểm tra | Cách xác minh | Mục tiêu |
| --- | --- | --- |
| JDK CLI | java/javac --version | Java 25 thực sự được chọn. |
| Compact source | java Hello.java Lan | JEP 512 đã được hỗ trợ, không cần preview. |
| Explicit class | java -cp out demo.Main Lan | Tên package, classpath và main hợp lệ. |
| JAR | java -jar dist/demo.jar Lan | Manifest và class/dependencies đủ. |
| jpackage | Chạy binary trong app image | Native launcher có entry point đúng. |
| IDE | Chạy cùng class/source bằng Run Config | Cấu hình IDE dùng Java 25. |
| Runtime compatibility | In Runtime.version() từ process | JVM vận hành hỗ trợ class file 69. |
| Exit status | Test input hợp lệ và không hợp lệ | 0 cho thành công, nonzero theo quy ước. |

Không nên chỉ kiểm tra **javac** đã biên dịch thành công. Packaging và launcher có thể lỗi ở **manifest**, **module path**, **classpath** hoặc **JVM đích** sau đó.

## 13. Quy trình triage một lỗi entry point

Khi gặp sự cố, xử lý tuần tự:

1. **Chép lại lệnh chạy chính xác**: source-file mode, class mode, **-jar** hay **-m**? Đối số JVM và args đứng đúng phía chưa?
2. **Xác minh JDK chạy thực**: **java --version**, **javac --version**, **java.home** của IDE/CI/runtime. Java 25 cần JDK/VM tương thích, không phải chỉ thiết lập compiler.
3. **Kiểm tra lớp đầu vào**: compact source file hay class tường minh? Nếu source có nhiều top-level class, lớp đầu tiên là lớp nào?
4. **Kiểm tra main candidate**: **void**; tham số **String[]** hoặc không tham số; quyền truy cập không private; nếu instance thì có constructor không tham số không private.
5. **Kiểm tra vị trí class**: package/classpath đúng chưa? **demo.Main** phải tương ứng với **demo/Main.class** tại classpath root.
6. **Kiểm tra artifact**: JAR manifest **Main-Class**, class/dependencies; module-info và module path khi dùng **-m**.
7. **Kiểm tra lỗi ứng dụng**: nếu main đã chạy, phân biệt thiếu tham số, input sai, exception/I-O hoặc khởi tạo dependency.
8. **Tái hiện không qua IDE**: chạy thẳng **java** cùng JDK/args để phân biệt lỗi IDE/plugin với lỗi launcher.
9. **Tái hiện từ artifact**: smoke test JAR/app image bằng JVM/runtime thực dùng ở CI/deploy.

### Mẫu thông tin nên lưu khi báo lỗi

~~~text
JDK: <java --version>
OS/architecture: <OS, CPU>
Launch mode: source | class | jar | module | jpackage
Command: <exact command, without secrets>
Selected class/main: <fully-qualified class and signature>
Compiler release: <25 or other>
Artifact: <source file, classes, jar, app image>
Expected: <stdout/stderr, exit code>
Actual: <stderr/stack trace, exit code>
Reproduction: <minimal source and steps>
~~~

Đừng đưa token, password hoặc dữ liệu nhạy cảm trong command line/trace/report. Nếu lỗi phụ thuộc phiên bản IDE/build plugin, ghi rõ **version đã cài**, không chỉ ghi “mới nhất”.

## 14. Bài tập thực hành

**Bài 1 – nhận diện main:** Tạo một class có **static main()** và **instance main(String[])** như **PickMain**. Trên JDK 25, dự đoán phương thức được chọn rồi chạy để xác minh.

**Bài 2 – lỗi constructor:** Tạo class có **void main()** nhưng constructor không tham số **private**; quan sát lỗi launcher. Sửa quyền truy cập constructor rồi chạy lại.

**Bài 3 – lỗi source-file mode:** Tạo tệp chứa hai top-level class, main chỉ nằm ở class thứ hai. Chạy trực tiếp source, sau đó đưa class có main lên đầu hoặc compile/run theo tên class.

**Bài 4 – bảo toàn thông số lỗi:** Viết ứng dụng CLI nhận một số nguyên không âm, trả **0** khi hợp lệ, **2** khi sai input. Unit test hàm **run** mà không kết thúc JVM test; smoke test process ngoài để kiểm tra mã lỗi.

**Bài 5 – chuyển nguồn gọn thành artifact:** Bắt đầu bằng **void main()** trong compact source file; chuyển sang **demo.Main** tường minh, compile với **--release 25**, tạo JAR có **Main-Class** và chạy bằng **java -jar**.

**Bài 6 – tương thích IDE/build:** Dùng cùng project trên JDK 25 CLI và trong IDE. Nếu IDE không hiện Run cho compact source file, ghi version IDE, JDK, chế độ chạy; thử bản class tường minh và xác minh.

**Bài 7 – jpackage:** Tạo application image từ JAR đã smoke test, chạy launcher thực và so tham số/exit status. Ghi OS, kiến trúc và JVM/runtime image đích.

### Tự kiểm tra

1. Trong Java 25, vì sao **void main()** hợp lệ, và khi nào launcher phải tạo instance?
2. Nếu có **static void main()** và **void main(String[])**, phương thức nào được chọn?
3. Vì sao **private static void main(String[])** không phải entry point hợp lệ?
4. Khi **java TwoClasses.java** chọn sai class, khác gì lỗi chọn overload main?
5. Vì sao compact source file chạy bằng **java Hello.java** nhưng không nên phụ thuộc tên lớp ngầm khi đóng gói JAR?
6. **--release 25** giải quyết điều gì, và **Main-Class** trong manifest giải quyết điều gì?
7. Một JAR có Main-Class đúng vẫn có thể báo **NoClassDefFoundError** vì nguyên nhân nào?
8. Vì sao unit test không nên gọi trực tiếp main chứa **System.exit**?
9. Khi nút Run IDE thất bại nhưng terminal Java 25 chạy được, những lớp cấu hình nào cần kiểm tra?
10. Tại sao không cần **--enable-preview** cho compact source file và instance main trong Java 25?

## 15. Nguồn tham khảo hiện hành

- **JEP 512 – Compact Source Files and Instance Main Methods (final trong Java 25):** https://openjdk.org/jeps/512
- **Oracle Java 25 Language Updates – Compact Source Files and Instance main Methods:** https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html
- **Java 25 Language Changes by Release:** https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html
- **Java Language Specification, Java SE 25 – quy tắc chọn main:** https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html
- **Java 25 java launcher:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **JAR File Specification, manifest Main-Class:** https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html
- **Java 25 jpackage – Basic Packaging:** https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html
- **Gradle Application Plugin:** https://docs.gradle.org/current/userguide/application_plugin.html

**Lưu ý đọc tài liệu:** một số đoạn mô tả ngắn của manual/IDE cũ vẫn viết main chỉ có thể là **public static void main(String[])**. Quy tắc Java 25 cho phép nhiều dạng hơn; khi có khác biệt, đối chiếu **JEP 512**, **Java 25 Language Updates** và JLS của đúng phiên bản. Ngược lại, khi muốn tối đa hóa tương thích với công cụ đóng gói bên thứ ba, tiếp tục dùng entry point tường minh và chữ ký static truyền thống là hợp lý, không phải sử dụng kiến thức legacy.

**Kết quả cần nộp:** bộ ví dụ chạy nguồn gọn và lớp tường minh; bảng lỗi entry point kèm cách tái hiện; CLI trả exit status có kiểm thử; JAR có manifest đúng; application image từ jpackage; bảng xác minh launcher/IDE/CI/runtime. Đầu ra này cho phép ứng dụng Java 25 tận dụng khả năng main hiện đại nhưng vẫn chạy và đóng gói có thể dự đoán trong môi trường thực tế.
