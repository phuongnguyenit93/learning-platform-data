# JDK, JVM, bytecode và tiến trình Java khi chạy ứng dụng

Khi chạy một ứng dụng Spring Boot bằng `java -jar app.jar`, hệ điều hành khởi tạo một **tiến trình Java**. Bên trong tiến trình đó, **JVM** nạp các lớp đã biên dịch, thực thi mã của ứng dụng, quản lý bộ nhớ và các luồng. Trước đó, **JDK** cung cấp những công cụ cần thiết để biên dịch mã nguồn Java thành **bytecode** và đóng gói ứng dụng.

Hiểu ranh giới giữa các khái niệm này giúp trả lời những câu hỏi thực tế: Vì sao mã chạy được trên máy lập trình nhưng lỗi khi triển khai? Vì sao có JDK mà ứng dụng vẫn dùng sai phiên bản Java? Vì sao tăng `-Xmx` không đồng nghĩa với giới hạn toàn bộ RAM của tiến trình? Vì sao hai ứng dụng Spring Boot chạy cùng một máy lại có PID, cổng và bộ nhớ riêng?

## 1. Phân biệt JDK, JVM, bytecode và tiến trình Java

| Khái niệm | Vai trò | Ví dụ khi làm việc với Spring Boot |
|---|---|---|
| **JDK** (*Java Development Kit*) | Bộ công cụ phát triển Java, gồm trình biên dịch, công cụ phân tích và môi trường cần thiết để chạy Java. | Dùng `javac`, `jar`, `jcmd` và chạy Gradle/Maven để build ứng dụng. |
| **JVM** (*Java Virtual Machine*) | Máy ảo thực thi mã Java đã biên dịch: nạp lớp, xác minh bytecode, thực thi, biên dịch JIT và quản lý bộ nhớ. | JVM thực thi `main()` và toàn bộ mã Spring Boot. |
| **Bytecode** | Tập lệnh trung gian chứa trong các tệp `.class`, độc lập tương đối với hệ điều hành và CPU. | Các lớp của ứng dụng nằm trong JAR dưới dạng `.class`. |
| **Java launcher** (`java`) | Chương trình khởi chạy JVM và xác định điểm vào ứng dụng. | Lệnh `java -jar app.jar` bắt đầu quá trình chạy. |
| **Tiến trình Java** | Một tiến trình do hệ điều hành quản lý, có PID, vùng địa chỉ bộ nhớ, các luồng và tài nguyên riêng. | Một instance Spring Boot đang chạy thường tương ứng với một tiến trình Java. |
| **JAR** (*Java Archive*) | Tệp đóng gói các lớp, tài nguyên và metadata; không phải JVM hoặc tiến trình. | Spring Boot executable JAR chứa lớp ứng dụng, thư viện phụ thuộc và launcher. |

Trong các bản Java hiện đại, nhà phát triển thường cài **JDK** để vừa build vừa chạy. Khái niệm **JRE** (*Java Runtime Environment*) mô tả môi trường chạy Java, nhưng không nên mặc định rằng mọi bản phân phối Java hiện nay đều cung cấp một gói JRE độc lập như trước. Có thể tạo runtime tối giản bằng `jlink` cho một số kiểu ứng dụng.

Một cách ghi nhớ theo trách nhiệm:

- **JDK giúp tạo ra chương trình**: mã nguồn, biên dịch, đóng gói, kiểm tra và chẩn đoán.
- **Bytecode là sản phẩm biên dịch**: được lưu trong `.class`, không tự chạy như một tiến trình.
- **JVM thực thi chương trình**: biến bytecode thành các hoạt động trên máy thực.
- **Hệ điều hành quản lý tiến trình**: cấp PID, lập lịch các luồng, quản lý tài nguyên và cho phép kết thúc ứng dụng.

## 2. Từ mã nguồn `.java` đến bytecode `.class`

Giả sử có tệp `HelloJava.java`:

```java
public class HelloJava {
    public static void main(String[] args) {
        String name = "Spring Boot";
        System.out.println("Hello, " + name);
    }
}
```

Dùng các lệnh sau tại thư mục chứa tệp; ví dụ sử dụng một JDK đã cài và cấu hình đường dẫn:

```bash
javac -d out HelloJava.java
java -cp out HelloJava
javap -classpath out -c HelloJava
```

Các bước diễn ra như sau:

1. `javac` kiểm tra cú pháp, kiểu dữ liệu và các tham chiếu có thể kiểm tra ở thời điểm biên dịch; sau đó sinh `out/HelloJava.class`.
2. `java -cp out HelloJava` khởi tạo JVM với `out` trên *classpath*, tìm lớp `HelloJava` và gọi phương thức `main(String[] args)`.
3. `javap -c` hiển thị những lệnh bytecode trong `.class` để quan sát kết quả biên dịch. Tùy phiên bản JDK và biểu thức, bytecode cụ thể có thể khác nhau.

Ví dụ, các chỉ thị như `getstatic`, `ldc`, `invokevirtual` và `return` biểu diễn thao tác lấy trường tĩnh, nạp hằng, gọi phương thức và trở về từ phương thức. Chúng **không phải mã máy x86/ARM trực tiếp**. JVM sẽ diễn giải hoặc biên dịch chúng thành mã máy phù hợp với môi trường đang chạy.

Sơ đồ tổng quát:

```text
HelloJava.java
     │  javac (công cụ trong JDK)
     ▼
HelloJava.class  ── bytecode + metadata lớp
     │  java launcher khởi tạo JVM
     ▼
Class loading → verification/linking → initialization khi cần
     │
     ▼
Interpreter / JIT → thực thi trên CPU
     │
     ▼
Tiến trình Java: PID, bộ nhớ, các thread, tài nguyên OS
```

Điểm quan trọng: **biên dịch thành công không đảm bảo chạy thành công**. Thư viện có thể thiếu ở runtime, cấu hình hoặc cổng mạng có thể sai, phiên bản JVM có thể không tương thích, hay ứng dụng có thể ném exception trong lúc khởi tạo.

## 3. JVM nạp và thực thi chương trình như thế nào?

Một mô hình khái quát của JVM gồm những thành phần sau.

### Class loading, linking và initialization

**Class loader** tìm và nạp thông tin của lớp từ classpath, module path hoặc cơ chế nạp tùy biến. Trong quá trình liên kết (*linking*), JVM xác minh cấu trúc bytecode, chuẩn bị các trường tĩnh và phân giải các tham chiếu khi thích hợp. **Initialization** thực thi logic khởi tạo tĩnh của lớp khi lớp được khởi tạo theo quy tắc của Java.

Các lớp thường được tải theo nhu cầu; JVM không bắt buộc phải đọc toàn bộ `.class` trong mọi JAR ngay khi tiến trình bắt đầu. Vì vậy, lỗi thiếu lớp đôi khi chỉ xuất hiện khi đường chạy tương ứng được sử dụng.

Với Spring Boot executable JAR, **Spring Boot loader** hỗ trợ tìm lớp ứng dụng và các dependency đóng gói bên trong JAR. Cơ chế này giải thích vì sao một JAR Spring Boot có thể chạy với `java -jar` dù chứa các thư viện ở vị trí không giống classpath JAR thông thường.

### Interpreter và JIT compiler

JVM có thể thực thi bytecode bằng bộ thông dịch (*interpreter*) và dùng trình biên dịch **JIT** (*Just-In-Time*) để chuyển những đoạn mã phù hợp thành mã máy trong lúc ứng dụng đang chạy. JVM có thể tối ưu dựa trên thông tin quan sát được và điều chỉnh tối ưu hóa khi giả định không còn đúng.

Nhờ đó, câu “Java phải biên dịch hai lần” chỉ là cách nói giản lược: lần đầu `javac` tạo bytecode trước khi chạy; lúc runtime, JVM **có thể** biên dịch một phần mã thành mã máy. Không phải mọi lệnh bytecode đều bắt buộc được JIT biên dịch.

### Garbage collector (GC)

Đối tượng Java thông thường được cấp phát trên **heap** do JVM quản lý. GC tìm và thu hồi vùng nhớ của các đối tượng không còn reachable theo cơ chế của bộ thu gom đang dùng. GC không tự đóng mọi kết nối, file handle hoặc tài nguyên bên ngoài JVM; những tài nguyên đó vẫn cần quản lý vòng đời thích hợp, chẳng hạn `try-with-resources`.

## 4. Bộ nhớ của một tiến trình Java

Khi ứng dụng báo lỗi hết bộ nhớ, cần phân biệt **heap** với toàn bộ bộ nhớ mà tiến trình đang sử dụng.

| Vùng/nguồn sử dụng bộ nhớ | Dùng để làm gì? | Ghi chú |
|---|---|---|
| **Heap** | Chứa phần lớn đối tượng Java được cấp phát động. | `-Xms` và `-Xmx` ảnh hưởng đến kích thước heap. |
| **Java stack của thread** | Chứa frame của lời gọi phương thức, biến cục bộ và dữ liệu thực thi của từng luồng. | Mỗi thread có stack riêng; không phải nơi chứa toàn bộ đối tượng mà biến cục bộ tham chiếu đến. |
| **Metaspace** | Chứa nhiều loại metadata về lớp được JVM nạp. | Nằm ngoài Java heap trong HotSpot hiện đại. |
| **Code cache** | Chứa mã máy được JIT biên dịch và thông tin liên quan. | Có giới hạn và cơ chế quản lý riêng. |
| **Native/direct memory và tài nguyên runtime** | Dùng cho JVM, native library, direct buffer, GC/JIT và hoạt động hệ thống. | Có thể làm tổng RAM tiến trình lớn hơn `-Xmx`. |

Ví dụ:

```bash
java -Xms256m -Xmx512m -jar app.jar
```

Ở đây, `-Xms256m` đặt dung lượng heap khởi tạo và `-Xmx512m` đặt dung lượng heap tối đa. **Không được suy ra tiến trình chỉ dùng tối đa 512 MB RAM**: stacks, metaspace, direct buffers và các bộ phận khác vẫn tiêu thụ bộ nhớ ngoài heap. Việc hệ điều hành hiển thị RAM theo RSS, working set hoặc virtual memory cũng có ý nghĩa khác nhau.

Các thuật ngữ nên phân biệt thêm:

- **Stack overflow** (`StackOverflowError`): thường liên quan stack của một thread bị dùng hết, ví dụ đệ quy quá sâu.
- **Java heap space** (`OutOfMemoryError`): JVM không cấp phát được đối tượng trên heap trong giới hạn/điều kiện hiện tại.
- **Native memory pressure**: tiến trình hoặc container có thể thiếu RAM dù Java heap chưa chạm `-Xmx`.

Không thể xác định chính xác nguyên nhân chỉ từ một con số RAM; cần xem thông báo lỗi, giới hạn JVM/container và số liệu tương ứng.

## 5. Tiến trình Java, thread và vòng đời ứng dụng

**Process** là đơn vị cô lập tài nguyên ở mức hệ điều hành. Mỗi lần khởi chạy một ứng dụng bằng lệnh `java ...`, thông thường sẽ tạo ra một tiến trình hệ điều hành mới chứa một JVM. **Thread** là một luồng thực thi bên trong tiến trình đó; nhiều thread cùng chia sẻ heap của JVM nhưng có stack riêng.

Một ứng dụng Spring Boot chạy web có thể có các luồng xử lý request, luồng nền của JVM, luồng scheduler, luồng cho tác vụ bất đồng bộ và các luồng của connection pool. **Một HTTP request không đồng nghĩa với việc tạo một tiến trình Java mới.** Thread và cách xử lý request phụ thuộc vào web stack và cấu hình cụ thể.

Ví dụ cùng máy chạy hai instance:

```bash
java -jar app.jar --server.port=8081
java -jar app.jar --server.port=8082
```

Hai lệnh chạy đồng thời tạo **hai tiến trình**, với PID và heap riêng. Chúng không chia sẻ trực tiếp đối tượng trong heap. Nếu hai instance cùng cố bind một cổng và cùng địa chỉ lắng nghe, một instance thường gặp lỗi do cổng đã được sử dụng.

Vòng đời thường gặp của một ứng dụng web Spring Boot:

1. Hệ điều hành tạo tiến trình và Java launcher khởi tạo JVM.
2. JVM nạp điểm vào của executable JAR; launcher của Spring Boot chuyển điều khiển đến lớp ứng dụng.
3. Phương thức `main()` gọi `SpringApplication.run(...)`.
4. Spring khởi tạo `ApplicationContext`, cấu hình bean và, với ứng dụng web, khởi động web server phù hợp.
5. Các thread tiếp tục phục vụ request và tác vụ nền. `main()` kết thúc **không nhất thiết** khiến tiến trình web dừng ngay.
6. Khi nhận tín hiệu dừng hoặc yêu cầu shutdown phù hợp, ứng dụng/JVM thực hiện logic kết thúc được cấu hình, giải phóng tài nguyên rồi tiến trình thoát.

**PID** giúp phân biệt các instance. **Exit code** là kết quả mà tiến trình trả về cho hệ điều hành khi thoát: giá trị `0` thường biểu thị kết thúc bình thường; giá trị khác `0` thường biểu thị lỗi, nhưng ý nghĩa cụ thể do chương trình hoặc cơ chế khởi chạy quyết định.

## 6. Phiên bản JDK lúc build và phiên bản JVM lúc chạy

Kiểm tra bộ công cụ hiện tại:

```bash
java -version
javac -version
```

`java -version` hiển thị **runtime được lệnh `java` hiện tại sử dụng**; `javac -version` hiển thị trình biên dịch. Hai lệnh có thể trỏ đến hai bản cài đặt khác nhau nếu `PATH`, `JAVA_HOME` hoặc cấu hình IDE/build tool không đồng nhất.

Đặc biệt, `JAVA_HOME` chỉ ra một vị trí JDK theo cấu hình của nhiều công cụ, còn lệnh `java` được shell tìm bằng `PATH`. Không nên chỉ nhìn `JAVA_HOME` rồi kết luận `java -jar` chắc chắn dùng JDK đó.

Mỗi class file có **class file version**. Ví dụ thường gặp:

| Java target | Class file major version |
|---|---:|
| Java 17 | 61 |
| Java 21 | 65 |

Một lớp được biên dịch cho Java 21 thông thường không chạy trên JVM 17 và có thể gây `UnsupportedClassVersionError`. Khi muốn build trên JDK mới nhưng hỗ trợ bản Java cũ, có thể dùng:

```bash
javac --release 17 -d out HelloJava.java
```

Tùy chọn `--release 17` yêu cầu trình biên dịch tạo mã tương thích với API và ngôn ngữ của Java 17; nó không làm các dependency được biên dịch cho Java mới hơn trở nên tương thích. Với Spring Boot, cần kiểm tra thêm phiên bản tối thiểu do **phiên bản Spring Boot và các thư viện đang dùng** yêu cầu. Gradle Java toolchain hoặc Maven compiler configuration cũng có thể chọn phiên bản Java khác với shell/IDE.

## 7. Java khởi chạy Spring Boot cụ thể ra sao?

Một điểm vào Spring Boot điển hình:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Mã này chỉ khai báo và gọi điểm bắt đầu ứng dụng. JVM **không tự hiểu annotation `@SpringBootApplication`** để dựng bean: đó là công việc của các thư viện Spring trong quá trình khởi tạo `ApplicationContext`.

Với dự án sử dụng plugin Spring Boot và Gradle wrapper, một đường chạy phổ biến là:

```bash
./gradlew bootJar
java -jar build/libs/<ten-file-jar-duoc-build>.jar
```

Trên Windows PowerShell, lệnh wrapper tương ứng thường là `./gradlew.bat bootJar`. Tên JAR thực tế do cấu hình build quyết định. Một executable JAR Spring Boot phổ biến có cấu trúc:

```text
app.jar
├── META-INF/MANIFEST.MF     # Metadata, gồm entrypoint cho launcher
├── BOOT-INF/classes/        # .class và resources của ứng dụng
├── BOOT-INF/lib/            # JAR của dependency
└── org/springframework/boot/loader/...  # Lớp launcher
```

Tùy phiên bản và kiểu đóng gói, chi tiết có thể khác. Có thể kiểm tra bằng `jar tf app.jar` và `unzip -p app.jar META-INF/MANIFEST.MF` (nếu có công cụ `unzip`). Manifest của executable JAR giúp Java launcher tìm điểm vào; Spring Boot loader sau đó nạp ứng dụng cùng thư viện lồng bên trong. Vì vậy, **`java -jar` trên executable Spring Boot JAR không giống chạy trực tiếp một `.class` bằng `java -cp`**.

Các cách chạy phổ biến có điểm chung là đều thực thi Java trên JVM, nhưng khác cách cấu hình classpath, tham số và tiến trình phụ trợ:

| Cách chạy | Ý nghĩa thực tế |
|---|---|
| **Run `main()` trong IDE** | IDE dựng classpath, chọn JDK/runtime rồi khởi động ứng dụng để phát triển, debug. |
| **`./gradlew bootRun`** | Gradle dùng cấu hình dự án để chạy ứng dụng; bản thân Gradle cũng có quá trình/daemon Java liên quan. |
| **`java -jar app.jar`** | Chạy gói executable JAR đã build; phù hợp khi triển khai artifact. |

Không nên suy luận rằng một JVM lỗi chỉ vì ứng dụng chạy được bằng `bootRun` nhưng lỗi với JAR. Trước hết phải đối chiếu artifact, runtime Java, tham số cấu hình, biến môi trường, working directory và dependency thực sự được đóng gói.

## 8. JVM options khác gì tham số của Spring Boot?

Vị trí của tham số trong lệnh có ý nghĩa:

```bash
java -Xms256m -Xmx512m -Dspring.profiles.active=dev -jar app.jar --server.port=8081
```

| Thành phần | Ai xử lý chủ yếu? | Ý nghĩa |
|---|---|---|
| `-Xms256m` | JVM | Heap khởi tạo. |
| `-Xmx512m` | JVM | Giới hạn heap tối đa. |
| `-Dspring.profiles.active=dev` | Java launcher/JVM thiết lập system property; Spring đọc property | Kích hoạt profile `dev`. |
| `-jar app.jar` | Java launcher | Chỉ định executable JAR cần chạy. |
| `--server.port=8081` | Ứng dụng Spring Boot | Cấu hình cổng HTTP, nếu có web server và property được áp dụng. |

Các **JVM options** như `-Xmx` và Java system properties như `-D...` phải đặt ở vị trí Java launcher xử lý được, thường là **trước** `-jar`. Các application arguments dạng `--...` thường đặt **sau** đường dẫn JAR để truyền cho ứng dụng. Spring Boot còn có thể nhận cấu hình từ file, biến môi trường và những property source khác; giá trị cuối cùng phụ thuộc thứ tự ưu tiên cấu hình của Spring.

Ví dụ, `java -jar app.jar -Xmx512m` không thiết lập giới hạn heap 512 MB; `-Xmx512m` lúc đó được chuyển vào vùng đối số ứng dụng, và có thể bị ứng dụng bỏ qua hoặc xử lý khác.

## 9. Quan sát tiến trình đang chạy

Các công cụ trong JDK hữu ích khi cần xác định phiên bản JVM, điểm vào hoặc hiện trạng của một tiến trình Java:

```bash
jps -l
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> GC.heap_info
jcmd <PID> Thread.print
```

`<PID>` là mã tiến trình thực tế thay vào, không gõ nguyên dấu ngoặc nhọn. `jps` và `jcmd` cần có trong JDK trên máy; khả năng attach còn phụ thuộc hệ điều hành, quyền người dùng, bản JVM và cách cấu hình tiến trình. Tên hiển thị trong `jps` có thể là launcher hoặc class chính, không nhất thiết giống tên project.

Các lệnh hệ điều hành cũng giúp định vị PID:

```bash
# Linux/macOS
ps -ef | grep java

# Windows PowerShell
Get-Process java
```

Khi chẩn đoán, nên ghép bằng chứng theo cùng một **PID**: command line, phiên bản Java thực tế, cổng mạng, log, trạng thái thread và thông tin heap. Tránh gộp log của hai instance thành lỗi của một tiến trình.

## 10. Những lỗi thường gặp và ranh giới cần kiểm tra

| Triệu chứng | Lớp vấn đề cần kiểm tra trước | Hướng xác minh |
|---|---|---|
| `javac` không tìm thấy | Thiếu JDK hoặc cấu hình `PATH`. | Kiểm tra `javac -version`, vị trí cài JDK. |
| `java` dùng sai phiên bản | Runtime/launcher trong `PATH` hoặc cấu hình IDE, Gradle, service khác nhau. | Kiểm tra `java -version` trong **đúng môi trường** khởi chạy. |
| `UnsupportedClassVersionError` | Bytecode được biên dịch cho JVM mới hơn runtime. | Đối chiếu Java target, JDK build và JVM chạy. |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Class loading hoặc dependency/runtime classpath; cũng có thể liên quan lỗi khởi tạo lớp. | Xem stack trace đầy đủ, lớp nào thiếu, cách đóng gói JAR. |
| `no main manifest attribute` | JAR không khai báo main entrypoint như lệnh `java -jar` yêu cầu. | Kiểm tra manifest, task build có tạo executable JAR hay không. |
| Port already in use / `BindException` | Tranh chấp cổng hoặc địa chỉ bind ở mức OS. | Xác định PID đang lắng nghe cổng, cấu hình `server.port`. |
| `OutOfMemoryError: Java heap space` | Không cấp phát được thêm trên heap; nguyên nhân có thể do workload, kích thước heap hoặc giữ tham chiếu quá lâu. | Xem heap/GC metrics, log và mô hình sử dụng bộ nhớ trước khi điều chỉnh `-Xmx`. |
| Tiến trình bị hệ điều hành/container dừng đột ngột | Giới hạn tài nguyên hoặc hành vi môi trường chạy, có thể không xuất hiện Java exception. | Kiểm tra exit status, log container/OS, memory limit và signal. |

`Exception` từ Spring khi khởi tạo bean có thể khiến ứng dụng không lên được, dù JDK, bytecode và JVM hoàn toàn hợp lệ. Cần đọc nguyên nhân sâu nhất trong stack trace thay vì quy mọi lỗi startup về “lỗi Java”.

## 11. Bài tập quan sát thực tế

**Bài tập 1 — Nhìn thấy bytecode.** Tạo `HelloJava.java` ở phần 2, chạy `javac -d out HelloJava.java`, rồi so sánh nội dung file mã nguồn với kết quả `javap -classpath out -c HelloJava`. Xác định đoạn bytecode tương ứng với lệnh in ra console và phương thức `main`.

**Bài tập 2 — Phân biệt thời điểm build và chạy.** Chạy `java -version` và `javac -version`. Nếu sử dụng hai JDK khác nhau, xác định shell đang trỏ lệnh nào đến đâu trước khi biên dịch tiếp. Thử `javac --release 17` trên JDK hỗ trợ tùy chọn này; kiểm tra class file bằng `javap -verbose` và tìm `major version`.

**Bài tập 3 — Quan sát hai instance Spring Boot.** Với một executable JAR web có sẵn, chạy hai instance bằng `--server.port=8081` và `--server.port=8082` trong hai terminal. Dùng `jps -l` hoặc công cụ OS để tìm **hai PID**, quan sát command line tương ứng và thử dùng cùng một cổng để hiểu lỗi bind. Sau khi thực hành, dừng cả hai tiến trình bằng cơ chế dừng bình thường của môi trường chạy.

**Bài tập 4 — Phân biệt heap và process memory.** Chạy ứng dụng với `-Xmx512m`, dùng `jcmd <PID> GC.heap_info` và quan sát thông số bộ nhớ của tiến trình trong công cụ OS. Giải thích vì sao các số đo không nhất thiết bằng nhau.

## 12. Những nguyên tắc cần giữ khi học Spring Boot

1. **Spring Boot vẫn là ứng dụng Java.** Cần một runtime phù hợp để thực thi các lớp `.class`; framework Spring cung cấp tầng khởi tạo ứng dụng, dependency injection và web/server integration.
2. **Build và runtime là hai thời điểm riêng.** Kiểm tra JDK/toolchain lúc biên dịch cùng Java runtime thực tế lúc chạy.
3. **JAR là artifact, JVM là runtime, process là thực thể hệ điều hành.** Không dùng ba từ thay thế cho nhau.
4. **Một tiến trình có nhiều thread và nhiều vùng bộ nhớ.** Tăng heap không tự giải quyết mọi lỗi tài nguyên hay hiệu năng.
5. **Dùng PID để gắn bằng chứng với đúng instance.** Cấu hình, log, cổng, heap và lỗi đều cần được đối chiếu trong cùng môi trường chạy.

Khi nắm được đường đi `source → bytecode → JVM → tiến trình → Spring ApplicationContext`, người học có thể giải thích những sự cố startup và triển khai Spring Boot dựa trên thành phần thực sự chịu trách nhiệm, thay vì thử thay đổi cấu hình một cách ngẫu nhiên.
