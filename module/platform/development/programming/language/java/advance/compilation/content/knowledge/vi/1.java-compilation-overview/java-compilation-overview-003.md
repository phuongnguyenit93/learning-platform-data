# Vai trò của JDK, javac, JVM và JIT

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **JDK** (bộ công cụ phát triển), **`javac`** (trình biên dịch mã nguồn), **JVM** (máy ảo thực thi bytecode) và **JIT** (bộ biên dịch tối ưu trong lúc chạy).
- Theo dõi một chương trình từ tệp `.java`, qua `.class`, đến lúc thực thi và, khi phù hợp, sinh mã máy.
- Tự biên dịch, chạy, kiểm tra bytecode và quan sát việc JVM biên dịch nóng bằng công cụ trong JDK.
- Giải thích vì sao “biên dịch thành công” khác “chạy được”, và vì sao JIT không phải bước bắt buộc cho từng phương thức.

## 1. Bức tranh tổng thể

Một quy trình Java thông dụng có dạng:

```text
Lập trình viên
    |
    | viết PipelineDemo.java (source code)
    v
JDK: javac ── kiểm tra cú pháp, kiểu và ngữ nghĩa ──> PipelineDemo.class
                                                     (JVM bytecode)
                                                            |
                                                            | java -cp out PipelineDemo
                                                            v
                                              JVM nạp, liên kết, khởi tạo lớp
                                                            |
                                                            v
                                                 Thực thi bytecode
                                             (thông dịch và/hoặc JIT)
                                                            |
                                      +---------------------+---------------------+
                                      |                                           |
                             Interpreter                                JIT biên dịch
                             bytecode                                    phần mã nóng
                                      |                                           |
                                      +---------------------+---------------------+
                                                            |
                                                            v
                                                   CPU thực thi mã máy
```

Sơ đồ trên minh họa **JDK dùng để phát triển và cung cấp công cụ khởi chạy**, còn **JVM thực hiện công việc chạy chương trình**. `javac` thường chạy trước thời điểm khởi động ứng dụng; JIT, nếu JVM triển khai và kích hoạt, hoạt động trong lúc chương trình đang chạy. Một phương thức có thể được thông dịch trước rồi được JIT biên dịch; cũng có phương thức không bao giờ đủ “nóng” để JIT lựa chọn.

| Thành phần | Vai trò cốt lõi | Đầu vào / đầu ra điển hình | Khi nào tham gia |
| --- | --- | --- | --- |
| **JDK** (Java Development Kit) | Bộ phân phối công cụ phát triển Java, gồm compiler, launcher, các công cụ chẩn đoán và runtime | `javac`, `java`, `jar`, `javap`, `jshell`… | Khi phát triển, đóng gói, kiểm tra và cả khi dùng runtime đi kèm để chạy |
| **`javac`** | Biên dịch mã nguồn Java thành bytecode với kiểm tra theo ngôn ngữ Java | `.java` → `.class` | Thường trước khi chạy; cũng có thể được gọi gián tiếp bởi build tool/IDE |
| **JVM** (Java Virtual Machine) | Nạp, xác minh và thực thi class file theo mô hình JVM; quản lý các dịch vụ runtime | Class files/bytecode → hành vi thực thi | Trong suốt vòng đời tiến trình Java |
| **JIT** (Just-In-Time compiler) | Biên dịch các phần bytecode được chọn thành mã máy để tối ưu hiệu năng khi chạy | Bytecode + thông tin runtime → mã máy của kiến trúc CPU hiện tại | Trong quá trình JVM chạy, tùy phiên bản/cấu hình/tải thực tế |

**Không đồng nhất khái niệm với sản phẩm.** JVM là một đặc tả/mô hình thực thi; HotSpot là một triển khai JVM phổ biến trong OpenJDK. Các chi tiết như C1, C2, bộ đếm ngưỡng hay cờ `-XX` là đặc trưng của một số bản HotSpot, không phải cam kết của mọi JVM.

## 2. JDK: môi trường và bộ công cụ

JDK cung cấp những thứ cần thiết để **xây dựng** chương trình Java. Những công cụ thường gặp:

- `javac`: biên dịch tệp Java thành class file.
- `java`: launcher khởi chạy một ứng dụng và tạo JVM để thực thi.
- `jar`: tạo/đọc gói JAR, vốn là một định dạng lưu trữ nhiều tài nguyên và class file.
- `javap`: xem thông tin lớp, chữ ký thành viên và chỉ thị bytecode.
- `javadoc`: tạo tài liệu API từ mã nguồn và chú thích tài liệu.
- `jshell`: môi trường thử nhanh biểu thức/đoạn mã Java.
- `jcmd`, `jstack`, `jmap`, `jfr`: công cụ hỗ trợ quan sát hoặc chẩn đoán trên những JDK có cung cấp.

Bản JDK hiện đại thường chứa một **runtime để chạy ứng dụng**, bao gồm một JVM. Trong lịch sử từng có phân phối “JRE” riêng; từ Java 9 và mô hình module, cách đóng gói runtime thay đổi, nên không nên mặc định máy nào cũng có bộ cài JRE tách biệt. Có thể tạo runtime tùy biến bằng `jlink` khi thích hợp.

Kiểm tra môi trường:

```bash
java -version
javac -version
```

Hai lệnh trên có thể dùng hai bản cài khác nhau nếu `PATH` cấu hình không nhất quán. Hãy kiểm tra đường dẫn `java`/`javac` và `JAVA_HOME` (nếu dự án dùng biến này) để biết build tool/IDE đang sử dụng JDK nào. `JAVA_HOME` là quy ước cấu hình của nhiều công cụ, **không phải** một yêu cầu của đặc tả ngôn ngữ Java.

Lưu ý sự khác biệt:

- Có lệnh `java` nhưng không có `javac`: môi trường có thể chỉ cung cấp runtime hoặc `PATH` trỏ không đúng JDK.
- Cài JDK mới không tự động khiến mọi dự án dùng phiên bản mới: IDE, Gradle, Maven và terminal có thể lựa chọn toolchain riêng.
- Tên “JDK 21” nói về bản phân phối công cụ; “Java 21” cũng có thể nói đến mức ngôn ngữ, thư viện chuẩn hoặc phiên bản runtime. Cần xác định đang đề cập tới phần nào.

## 3. `javac`: chuyển source thành class file

Ví dụ Java 17+ hoàn chỉnh sau dùng toán học đơn giản để có kết quả kiểm chứng được.

Tạo file **`PipelineDemo.java`**:

```java
public class PipelineDemo {
    static int square(int value) {
        return value * value;
    }

    public static void main(String[] args) {
        int total = 0;
        for (int i = 1; i <= 5; i++) {
            total += square(i);
        }
        System.out.println("Tong binh phuong = " + total);
    }
}
```

Từ thư mục chứa file, thực hiện:

```bash
javac -d out PipelineDemo.java
java -cp out PipelineDemo
```

Đầu ra chuẩn chính xác:

```text
Tong binh phuong = 55
```

Giải thích:

1. `javac -d out PipelineDemo.java` phân tích mã nguồn, kiểm tra và sinh `out/PipelineDemo.class`. Tùy hệ điều hành, ký tự phân cách đường dẫn có thể khác.
2. `java -cp out PipelineDemo` yêu cầu launcher đưa `out` vào classpath và tìm lớp có tên nhị phân `PipelineDemo` chứa điểm vào `public static void main(String[] args)`.
3. Vòng lặp cộng `1² + 2² + 3² + 4² + 5² = 55`. Đây là kết quả logic của chương trình, không phụ thuộc phương thức được JIT biên dịch hay thông dịch.
4. Sau khi chạy, class file vẫn là bytecode. `java` khởi động JVM để xử lý nó; bước `javac` trước đó **không sinh trực tiếp** một tệp thực thi native cho CPU.

`javac` làm gì ở mức khái niệm?

- **Phân tích từ vựng và cú pháp:** nhận biết token, câu lệnh, biểu thức, khai báo và cấu trúc chương trình.
- **Phân giải tên và kiểm tra kiểu/ngữ nghĩa:** kiểm tra ví dụ biến/phương thức có tồn tại, kiểu có tương thích, lời gọi có hợp lệ, quy tắc truy cập, ngoại lệ được kiểm tra…
- **Xử lý annotation khi có cấu hình thích hợp:** annotation processor có thể tạo thêm source hoặc tài nguyên. Annotation thông thường không đồng nghĩa với việc `javac` tự phát sinh bất kỳ hành vi runtime nào.
- **Sinh class file:** tạo constant pool, thông tin lớp/phương thức/field và chỉ thị bytecode, cùng metadata cần thiết.

Bytecode là bộ chỉ thị cho JVM, ví dụ nạp một giá trị, gọi phương thức, cộng hai số hoặc trả về. Nó **không phải** mã máy x86-64/ARM64. Đây là một lý do Java có thể phân phối class/JAR chung tới nhiều hệ điều hành/CPU, miễn là phía đích có JVM và các phụ thuộc tương thích.

### 3.1 Xem kết quả `javac`

```bash
javap -c -p -classpath out PipelineDemo
javap -verbose -classpath out PipelineDemo
```

`javap -c` hiển thị các chỉ thị bytecode của phương thức có code. Bạn có thể thấy các chỉ thị như `iload`, `imul`, `iadd`, `invokestatic`, `invokevirtual`; chỉ thị thực tế và offset phụ thuộc cách trình biên dịch tạo class file. `javap -verbose` còn hiển thị metadata, constant pool và phiên bản định dạng class file. Đây là công cụ **đọc/giải mã class file**, không phải trình biên dịch JIT.

Ví dụ, class file dùng mức Java 17 có `major version: 61`; Java 21 có `major version: 65`. Đó là phiên bản **định dạng class file**, không phải số phiên bản của CPU hoặc JIT.

### 3.2 Phiên bản ngôn ngữ và khả năng chạy trên runtime khác

Với JDK 21, có thể tạo class file dùng API, quy tắc ngôn ngữ và mức bytecode tương thích Java 17:

```bash
javac --release 17 -d out PipelineDemo.java
java -cp out PipelineDemo
```

Lệnh `--release 17` khi dùng `javac` phù hợp sẽ giới hạn mức ngôn ngữ, API Java platform và class-file target tới bản 17. Nó có ý nghĩa mạnh hơn việc chỉ đặt `-source` và `-target` mà không giới hạn API chuẩn. Các thư viện bên thứ ba và môi trường triển khai vẫn cần được kiểm tra riêng.

Biên dịch bằng JDK 21 **mặc định** không đảm bảo chạy được trên JVM 17: class file target mặc định theo JDK có thể mới hơn. Khi JVM đích gặp major version cao hơn mức hỗ trợ, có thể xảy ra `UnsupportedClassVersionError`.

### 3.3 Biên dịch khác thực thi

`javac` có thể phát hiện lỗi cú pháp, lỗi kiểu, thiếu symbol có thể xác định khi compile. Nó **không thể đảm bảo** chương trình không bao giờ chia cho 0, không có `NullPointerException`, không lỗi cấu hình mạng/tệp hoặc đạt hiệu năng tốt. Ví dụ:

```java
public class RuntimeFailure {
    public static void main(String[] args) {
        int denominator = Integer.parseInt(args[0]);
        System.out.println(10 / denominator);
    }
}
```

```bash
javac -d out RuntimeFailure.java
java -cp out RuntimeFailure 0
```

Biên dịch hợp lệ nhưng khi chạy với đối số `0`, phép chia số nguyên gây `ArithmeticException: / by zero`. Dòng báo lỗi đầy đủ/stack trace có thể khác theo phiên bản JVM. Nếu chạy không có đối số, chương trình có thể ném `ArrayIndexOutOfBoundsException` trước khi tính phép chia.

## 4. JVM: từ class file đến hành vi chạy

JVM thực thi ngữ nghĩa bytecode theo đặc tả. Với một tiến trình Java thông thường, có thể phân chia các trách nhiệm sau.

### 4.1 Nạp, liên kết và khởi tạo lớp

- **Loading:** class loader tìm và định nghĩa lớp từ classpath, module path hoặc nguồn hợp lệ khác. Class loader còn quyết định một phần danh tính lớp: cùng tên nhị phân nhưng được định nghĩa bởi các class loader khác nhau không mặc nhiên là cùng một lớp.
- **Linking:** bao gồm **verification** (kiểm tra tính hợp lệ/an toàn của bytecode theo các quy tắc JVM), **preparation** (chuẩn bị các trường `static` với giá trị mặc định) và **resolution** (phân giải tham chiếu ký hiệu; có phần được phép trì hoãn).
- **Initialization:** thực thi các bộ khởi tạo biến `static` và khối `static` theo quy tắc JVM vào thời điểm lớp được khởi tạo. Việc **nạp** lớp không đồng nghĩa mọi đoạn khởi tạo `static` đã chạy.

Đây là mô hình khái niệm; triển khai có thể thực hiện một số thao tác theo thứ tự/lúc khác nhau miễn tuân thủ ngữ nghĩa quy định. JVM không nhất thiết tải toàn bộ lớp của ứng dụng ngay khi tiến trình khởi động.

### 4.2 Mô hình bộ nhớ và dịch vụ runtime

Một số vùng dữ liệu runtime quan trọng:

| Thành phần | Tác dụng |
| --- | --- |
| **Heap** | Chứa các object và array được cấp phát theo mô hình JVM; nơi garbage collector thường quản lý vòng đời bộ nhớ. |
| **JVM stack của mỗi thread** | Chứa frame cho lời gọi phương thức, bao gồm local variables và operand stack ở mức máy ảo. |
| **PC register của mỗi thread** | Theo dõi vị trí chỉ thị JVM của phương thức đang thực thi (với giới hạn/chi tiết khác cho native method). |
| **Method area** | Khu vực logic chứa cấu trúc theo lớp; HotSpot thường dùng Metaspace để quản lý phần lớn metadata lớp. |
| **Native method stack / native memory** | Phục vụ mã native và các cấu trúc ngoài heap; chi tiết tùy implementation. |

Các dịch vụ JVM thường gồm thực thi bytecode, quản lý thread, cấp phát object, xử lý exception, đồng bộ hóa và hỗ trợ garbage collection. **JVM, Java standard library và hệ điều hành không phải một thứ**: JVM cung cấp mô hình thực thi; thư viện Java cung cấp API như `String`, `Files`, `Socket`; hệ điều hành cung cấp các tài nguyên hệ thống thực tế.

Garbage collection thường chạy tự động theo các thuật toán của runtime, nhưng **không đảm bảo** thời điểm một object được thu gom hay khi nào tài nguyên ngoài heap như file/socket được đóng. Dùng `try-with-resources` cho những tài nguyên cần đóng có kiểm soát.

### 4.3 Interpreter: chạy bytecode mà chưa cần JIT

JVM có thể thực hiện bytecode qua bộ thông dịch. Khi ứng dụng mới bắt đầu, nhiều đoạn mã chưa có dữ liệu sử dụng đủ để JIT quyết định cách tối ưu. Thông dịch có lợi ở chỗ khởi chạy nhanh hơn với một số đoạn mã và tránh phải biên dịch native những phần hiếm khi được gọi.

Các JVM có thể dùng nhiều kỹ thuật thực thi khác nhau: interpreter, JIT, thậm chí mô hình AOT trong một số sản phẩm/runtime. Vì thế không nên nói **mọi bytecode đều bắt buộc đi qua interpreter trước khi chạy** hoặc “mọi JVM đều có JIT”.

## 5. JIT: biên dịch và tối ưu khi đang chạy

JIT nhận bytecode cùng thông tin quan sát được khi chương trình chạy (profile), sau đó sinh **mã máy native** cho các đoạn được lựa chọn. Mã máy đó được thực thi trực tiếp trên CPU của máy đang chạy JVM. JIT nằm trong cơ chế thực thi runtime; bạn thường **không phải gọi JIT từ code Java**.

Một mô hình đơn giản:

```text
Bytecode bắt đầu thực thi
       |
       v
JVM ghi nhận mức sử dụng/hành vi runtime (khi được hỗ trợ)
       |
       +--> Ít được dùng: tiếp tục theo đường thực thi hiện tại
       |
       +--> Được chọn để biên dịch: JIT tối ưu, sinh mã máy
                                             |
                                             v
                                    Chạy mã native đã sinh
                                             |
                         Giả định tối ưu không còn đúng?
                                             |
                                             v
                                 Deoptimization / thực thi lại
                                 theo đường phù hợp với ngữ nghĩa
```

Các yếu tố đáng hiểu:

- **Hot code:** phương thức hoặc vòng lặp được gọi/lặp nhiều, đủ để JVM thấy lợi ích biên dịch. Không tồn tại một ngưỡng duy nhất, ổn định cho mọi phiên bản và mọi cấu hình.
- **Profiling:** JVM có thể thu thập kiểu object thực tế, tần suất nhánh, điểm gọi hàm… để tối ưu theo hành vi quan sát.
- **Inlining:** chèn logic của phương thức được gọi vào call site khi có lợi, giảm chi phí lời gọi và mở ra cơ hội tối ưu tiếp.
- **Các tối ưu khác:** loại bỏ tính toán dư thừa, loại bỏ code không thể tới, phân tích escape/scalar replacement ở những điều kiện phù hợp; không được giả định mọi tối ưu luôn xảy ra.
- **Deoptimization:** nếu giả định được dùng cho mã đã tối ưu không còn phù hợp, JVM có thể quay về dạng thực thi khác, bảo toàn ngữ nghĩa Java.
- **Warm-up:** kết quả benchmark của những lượt chạy đầu có thể khác sau khi profile/JIT ổn định. JIT cũng tiêu thụ CPU và bộ nhớ cho quá trình compile, nên không phải miễn phí.

### 5.1 Tiered compilation ở HotSpot

Trong những cấu hình HotSpot thường gặp, **tiered compilation** kết hợp interpreter với các mức biên dịch để cân bằng tốc độ khởi động, chi phí profiling và hiệu năng dài hạn. Hai compiler thường được nhắc đến là **C1** (client compiler) và **C2** (server compiler). C1 có thể tạo mã nhanh và thu thập profiling; C2 dành nhiều công sức hơn cho tối ưu ở các mức thích hợp.

Đây là mô tả triển khai HotSpot, **không phải thuật ngữ được đặc tả JVM bắt buộc**. Các chế độ, mức biên dịch, compiler và thuật toán có thể thay đổi theo bản JDK, cờ cấu hình, phần cứng và JVM vendor.

### 5.2 Quan sát JIT, không đoán từ một lần chạy

Tạo file **`JitDemo.java`**:

```java
public class JitDemo {
    static long work(int count) {
        long sum = 0;
        for (int i = 0; i < count; i++) {
            sum += i % 7;
        }
        return sum;
    }

    public static void main(String[] args) {
        long result = 0;
        for (int round = 0; round < 10_000; round++) {
            result += work(1_000);
        }
        System.out.println("Result = " + result);
    }
}
```

```bash
javac -d out JitDemo.java
java -cp out JitDemo
```

Đầu ra chuẩn khi chạy bình thường:

```text
Result = 29970000
```

Mỗi lần `work(1000)` cho tổng `2997`; gọi 10.000 lần được `29.970.000`. Các thuật toán tối ưu runtime không được phép thay đổi kết quả quan sát được theo ngữ nghĩa của ví dụ.

Với **HotSpot** hỗ trợ những tùy chọn tương ứng, thử:

```bash
java -Xint -cp out JitDemo
java -XX:+PrintCompilation -cp out JitDemo
```

- `-Xint` yêu cầu chạy ở chế độ interpreter-only trên HotSpot. Đây là cách so sánh đường thực thi, **không phải benchmark chuẩn** về hiệu năng Java.
- `-XX:+PrintCompilation` yêu cầu in thông tin các phương thức được runtime biên dịch. Bạn có thể thấy tên `JitDemo::work`, nhưng điều đó **không được bảo đảm** trong mọi lần chạy/cấu hình; log còn chứa hoạt động nội bộ của JDK/JVM, thứ tự và thời gian không cố định.
- Khi bật `PrintCompilation`, stdout có thêm nhiều dòng chẩn đoán ngoài dòng `Result = 29970000`; không dùng cả log làm đầu ra cố định để kiểm thử.
- Các cờ `-XX` mang tính triển khai, có thể không tồn tại hoặc thay đổi trên JVM khác. Hãy xem trợ giúp/tài liệu của bản runtime đang dùng.

Muốn đo throughput/latency thực, hãy dùng workload đại diện và phương pháp đo có kiểm soát (ví dụ harness **JMH**), quan tâm warm-up, số fork, GC, CPU, biến động môi trường và tránh để optimizer loại bỏ công việc không được quan sát. **Không suy ra “JIT nhanh gấp N lần” chỉ từ hai lệnh chạy đơn lẻ.**

## 6. Mối quan hệ giữa compile-time, load-time và run-time

Ba mốc thời gian giải thích nhiều lỗi thực tế:

| Giai đoạn | Công cụ/cơ chế tiêu biểu | Vấn đề điển hình |
| --- | --- | --- |
| **Compile-time** | `javac`, annotation processor, dependency compiler classpath | Sai cú pháp; sai kiểu; thiếu dependency lúc biên dịch; API không có dưới `--release` đã chọn |
| **Load/link/initialize-time** | Class loader, verifier, linker, class initializer của JVM | Class thiếu lúc chạy; class version không được hỗ trợ; lỗi xác minh; khởi tạo `static` thất bại |
| **Run-time** | JVM interpreter/JIT, GC, thư viện, OS | Dữ liệu đầu vào sai; exception; timeout; lỗi I/O; memory pressure; hiệu năng thay đổi |

**Classpath tại compile và runtime có thể khác nhau.** Biên dịch thành công khi tìm thấy một thư viện không có nghĩa khi chạy JVM cũng tìm thấy nó. Với ứng dụng có package, layout thư mục và tên lớp chính phải phù hợp tên nhị phân của class. Ví dụ `com.example.Main` cần được gọi bằng tên đầy đủ nếu lớp khai báo trong package `com.example`.

**Kiểu lỗi phải đọc theo nguyên nhân.** `ClassNotFoundException` là checked exception có thể xuất hiện từ một số API nạp lớp động; `NoClassDefFoundError` thường phát sinh khi JVM cần định nghĩa lớp đã từng hiện diện lúc biên dịch nhưng không thể tìm/khởi tạo phù hợp lúc chạy. Chúng không phải hai cách viết thay thế hoàn toàn.

**Tương thích chạy không chỉ là major version.** Runtime cần đủ class/library/native dependencies, quyền hệ điều hành, cấu hình, module access và môi trường hỗ trợ. Một `.class` tương thích về phiên bản vẫn có thể lỗi runtime vì điều kiện khác.

## 7. Các tình huống thường gặp

### “Tại sao có JDK rồi vẫn gặp `java: command not found` hoặc `javac is not recognized`?”

JDK có thể đã được cài nhưng đường dẫn tới thư mục `bin` chưa nằm trong `PATH` của shell hiện tại; shell/IDE cũng có thể chưa cập nhật môi trường. Kiểm tra phiên bản và đường dẫn thực tế của `java`, `javac`, `JAVA_HOME` rồi cấu hình nhất quán. Lỗi này thuộc cấu hình môi trường, chưa nói gì về tính đúng của source code.

### “`javac` chạy xong nhưng `java PipelineDemo` báo không tìm thấy lớp?”

Trong ví dụ đã dùng `-d out`, nên class file ở `out`. Runtime cần `java -cp out PipelineDemo`. Không truyền tên file `PipelineDemo.class` cho launcher trong chế độ chạy theo class name. Tên package, classpath/module path và tên lớp chính cũng phải chính xác.

### “Mỗi lần chạy có phải compile lại bằng `javac`?”

Không. Nếu đã có class/JAR phù hợp, JVM có thể chạy những artifact ấy. Tuy nhiên JIT thường phải tạo lại mã máy cho **tiến trình JVM mới**; mã native được JIT sinh không mặc nhiên thay thế `.class` trên đĩa. JVM/JDK có các kỹ thuật lưu chia sẻ/cải thiện startup khác, nhưng không nên đánh đồng với việc biến mã nguồn thành một tệp native cố định.

### “JIT có chạy trước `main` không?”

JIT là hoạt động runtime. JVM và các thư viện có thể thực thi, khởi tạo hoặc biên dịch một số mã trước khi thân `main` của ứng dụng bắt đầu; vì vậy câu “JIT chỉ chạy sau dòng đầu của `main`” quá đơn giản. Nhưng bước `javac` biên dịch file trong workflow trên vẫn là bước độc lập trước khi khởi động tiến trình Java.

### “Có `java Hello.java` thì `javac` không còn cần thiết?”

Từ Java 11 có **source-file mode** cho launcher, ví dụ `java PipelineDemo.java` với source phù hợp. Launcher có thể biên dịch source ở bộ nhớ rồi chạy trong JVM. Điều đó không biến JVM thành trình đọc trực tiếp từng câu lệnh Java source, cũng không biến JIT thành trình biên dịch source Java. Chế độ này tiện cho chương trình nhỏ; với project có nhiều file, package, dependency và build tái lập, pipeline build tách bước vẫn thường rõ ràng hơn.

### “Java luôn chậm hơn native vì phải thông dịch?”

Không thể kết luận tổng quát. JIT có thể tối ưu theo dữ liệu runtime; hiệu năng còn phụ thuộc thuật toán, cấp phát, GC, I/O, warm-up, cấu hình và phần cứng. Có workload Java rất tốt, có workload bị giới hạn bởi startup, bộ nhớ hoặc mô hình thực thi. Muốn kết luận, cần đo workload thực tế.

### “JIT biến bytecode thành native rồi có bỏ qua luật Java không?”

Không. Các tối ưu phải giữ hành vi quan sát được theo ngữ nghĩa Java, kể cả quy tắc xử lý exception, đồng bộ và memory model. JIT có thể đổi thứ tự/thay cách tính khi hợp lệ, nhưng không được tùy tiện đổi kết quả hay làm chương trình vi phạm ràng buộc ngữ nghĩa.

## 8. Checklist tự thực hành

1. Chạy `java -version` và `javac -version`; xác định phiên bản và JDK thực tế được terminal dùng.
2. Tạo `PipelineDemo.java`, biên dịch bằng `javac -d out ...`, chạy bằng `java -cp out PipelineDemo` và xác minh dòng `Tong binh phuong = 55`.
3. Dùng `javap -c -p -classpath out PipelineDemo`, nhận diện chỉ thị gọi `square` và phép nhân; phân biệt nó với source Java và mã máy.
4. Nếu có JDK 21, biên dịch lại bằng `--release 17` rồi kiểm tra major version của class file; giải thích vì sao runtime cũ hơn có thể từ chối class file mới.
5. Chạy `JitDemo` bình thường rồi thử `-Xint` và `-XX:+PrintCompilation` trên HotSpot; xem sự khác nhau giữa **đường thực thi/log chẩn đoán** và **giá trị kết quả**.

## 9. Tự kiểm tra kiến thức

**Câu 1.** `javac` có tạo mã máy x86-64 để CPU chạy trực tiếp từ file `.class` không?

**Đáp án:** Không. `javac` thông thường tạo bytecode theo định dạng class file; JVM/runtime tiếp tục chịu trách nhiệm thực thi, có thể dùng interpreter hoặc JIT.

**Câu 2.** Vì sao source đã compile được vẫn có thể gặp `NoClassDefFoundError` khi chạy?

**Đáp án:** Dependency/classpath hoặc điều kiện nạp/khởi tạo lớp ở runtime có thể khác compile-time; class file hợp lệ không bảo đảm đủ dependency khi khởi chạy.

**Câu 3.** Tại sao một phương thức trong chương trình rất ngắn có thể không được JIT biên dịch?

**Đáp án:** JVM có thể thấy chi phí biên dịch không xứng với lợi ích hoặc không đủ thông tin/profile; nhiều runtime có thể thực thi phương thức bằng interpreter.

**Câu 4.** Khi nào dùng `javap` và khi nào dùng `-XX:+PrintCompilation`?

**Đáp án:** `javap` phân tích class file/bytecode tĩnh. `PrintCompilation` là cờ chẩn đoán HotSpot cho biết hoạt động biên dịch native của runtime, có log biến động theo lần chạy và cấu hình.

**Câu 5.** Câu “JDK = javac = JVM = JIT” sai ở đâu?

**Đáp án:** JDK là bộ công cụ/phân phối; `javac` là compiler chuyển source sang bytecode; JVM là mô hình/môi trường thực thi bytecode; JIT là cơ chế tối ưu runtime có thể nằm trong một JVM cụ thể.

## Kết luận

Nhớ đúng chuỗi trách nhiệm: **JDK cung cấp công cụ → `javac` tạo bytecode → JVM nạp và thực thi → JIT có thể tối ưu những phần được chọn thành mã máy khi đang chạy**. Điểm phân biệt quyết định là **biên dịch source thành bytecode xảy ra tại compile-time**, còn **JIT biên dịch bytecode thành mã máy xảy ra tại runtime**. Hiểu ranh giới này giúp bạn cấu hình JDK, đọc lỗi build/runtime và đánh giá hiệu năng Java một cách chính xác.