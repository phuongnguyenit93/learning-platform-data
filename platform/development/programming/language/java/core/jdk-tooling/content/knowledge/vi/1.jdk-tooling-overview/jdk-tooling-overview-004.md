# JDK và JVM

Trong hệ sinh thái Java, **JDK** và **JVM** là hai thành phần có vai trò khác nhau nhưng phối hợp chặt chẽ. JDK cung cấp công cụ để phát triển, biên dịch, đóng gói và chạy ứng dụng Java. JVM là máy ảo thực thi bytecode trong các tệp class. Hiểu rõ ranh giới giữa hai thành phần giúp bạn chọn đúng công cụ, đọc lỗi môi trường và hiểu cách chương trình Java đi từ mã nguồn đến khi chạy.

## 1. Bức tranh tổng thể

Khi viết một chương trình Java, bạn thường làm việc với ba khái niệm:

- **JDK (Java Development Kit):** bộ công cụ dành cho nhà phát triển. JDK có trình biên dịch, trình khởi chạy, thư viện nền tảng và nhiều tiện ích phục vụ phát triển, gỡ lỗi, đóng gói hoặc phân tích ứng dụng.
- **JVM (Java Virtual Machine):** máy ảo thực thi Java bytecode. JVM nạp các lớp, kiểm tra bytecode, quản lý bộ nhớ và thực thi mã.
- **JRE (Java Runtime Environment):** tên gọi cho môi trường cần thiết để chạy ứng dụng Java, thường được mô tả bằng JVM cộng với thư viện và các thành phần runtime hỗ trợ. Đây là khái niệm hữu ích để hiểu kiến trúc, dù cách phân phối JRE độc lập đã thay đổi ở các phiên bản Java hiện đại.

Một cách nhớ nhanh: **JDK phục vụ quá trình phát triển; JVM thực thi bytecode; JRE mô tả môi trường chạy ứng dụng.** Khi cài một JDK đầy đủ, bạn thường đã có cả công cụ biên dịch lẫn môi trường để chạy chương trình.

## 2. JDK là gì?

JDK là bộ công cụ và thành phần nền tảng để xây dựng ứng dụng Java. Một bản phân phối JDK thường có:

1. **Java compiler — javac:** chuyển mã nguồn `.java` thành bytecode trong tệp `.class`.
2. **Java launcher — java:** khởi chạy lớp, JAR hoặc module; launcher khởi tạo JVM phù hợp để thực thi chương trình.
3. **Java platform APIs:** các thư viện chuẩn như collections, I/O, networking, concurrency, date/time và nhiều API khác.
4. **Công cụ đóng gói và tài liệu:** ví dụ `jar` để làm việc với JAR, `javadoc` để tạo tài liệu API.
5. **Công cụ phát triển và chẩn đoán:** ví dụ `jshell`, `jdb`, `jcmd`, `jstack`, `jmap` và `jfr` trong các bản phân phối hỗ trợ.

JDK là một bộ công cụ, không phải chỉ là trình biên dịch. Bạn có thể dùng cùng một cài đặt JDK để biên dịch mã nguồn, chạy ứng dụng, tạo JAR, tạo tài liệu và điều tra một số vấn đề runtime.

### Một số công cụ thường gặp

| Công cụ | Công dụng |
|---|---|
| `javac` | Biên dịch mã nguồn Java thành bytecode |
| `java` | Chạy lớp, JAR hoặc module Java |
| `jar` | Tạo, xem và cập nhật tệp JAR |
| `javadoc` | Sinh tài liệu từ comment Javadoc |
| `jshell` | Thử biểu thức và đoạn mã Java tương tác |
| `jdb` | Gỡ lỗi chương trình Java |
| `jcmd` | Gửi lệnh chẩn đoán đến tiến trình JVM |
| `jstack` | Lấy thread dump để xem trạng thái các luồng |
| `jmap` | Thu thập thông tin liên quan đến heap |
| `jfr` | Làm việc với bản ghi Java Flight Recorder |

Danh sách công cụ cụ thể có thể khác nhau giữa các nhà cung cấp và phiên bản JDK. Khi cần dùng một tiện ích, hãy kiểm tra thư mục `bin` của JDK đang cài và tài liệu tương ứng với phiên bản đó.

## 3. JVM là gì?

JVM là một máy tính trừu tượng được đặc tả để thực thi bytecode trong định dạng class file. Đặc tả JVM quy định cách class file được nạp, kiểm tra và thực thi, cũng như các vùng dữ liệu runtime mà chương trình có thể sử dụng.

JVM không đồng nghĩa với ngôn ngữ Java. Một số ngôn ngữ khác có thể biên dịch sang Java bytecode và chạy trên JVM, miễn là bytecode và thư viện cần thiết tương thích với môi trường đó.

Cần phân biệt **đặc tả JVM** và **một bản triển khai JVM**:

- Đặc tả mô tả hành vi mà một JVM tương thích phải cung cấp.
- Bản triển khai là phần mềm thực tế chạy trên hệ điều hành và phần cứng.
- HotSpot là một triển khai JVM phổ biến. Ngoài ra còn có những triển khai khác, với lựa chọn tối ưu hóa và vận hành riêng.

Đặc tả không bắt buộc mọi JVM phải dùng cùng một thuật toán garbage collection, cùng cách bố trí bộ nhớ hay cùng chiến lược JIT. Vì vậy, chi tiết quan sát được trong một triển khai cụ thể không phải lúc nào cũng là quy tắc chung của mọi JVM.

## 4. JVM thực thi chương trình như thế nào?

Một chương trình Java thông thường đi qua chuỗi bước sau:

1. **Viết mã nguồn:** nhà phát triển tạo tệp `.java`.
2. **Biên dịch:** `javac` kiểm tra mã nguồn và tạo bytecode trong tệp `.class`.
3. **Khởi chạy:** lệnh `java` tìm lớp hoặc JAR cần chạy và khởi tạo JVM.
4. **Nạp lớp:** class loader tìm và nạp các định nghĩa lớp cần thiết.
5. **Kiểm tra và liên kết:** JVM kiểm tra tính hợp lệ của class file, chuẩn bị dữ liệu lớp và giải quyết các tham chiếu khi cần.
6. **Khởi tạo lớp:** các initializer và khối static được thực thi theo quy tắc khởi tạo lớp.
7. **Thực thi:** execution engine diễn giải bytecode và có thể biên dịch những phần chạy thường xuyên thành mã máy.
8. **Quản lý runtime:** JVM cấp phát bộ nhớ, phối hợp các luồng và thu hồi những đối tượng không còn được tham chiếu theo chính sách garbage collection.

Bytecode không phải mã máy dành riêng cho một CPU. JVM tương thích trên từng nền tảng chịu trách nhiệm thực thi bytecode trên nền tảng đó. Đây là nền tảng của tính di động Java, nhưng ứng dụng vẫn có thể phụ thuộc hệ điều hành hoặc kiến trúc nếu sử dụng native library, đường dẫn hệ thống hay hành vi đặc thù của nền tảng.

## 5. Các thành phần chính trong JVM

### 5.1. Class loader

Class loader chịu trách nhiệm tìm và nạp class vào JVM. Các class loader tích hợp phổ biến trong Java hiện đại gồm:

- **Bootstrap Class Loader:** nạp các lớp nền tảng cốt lõi.
- **Platform Class Loader:** nạp các lớp nền tảng thuộc những module phù hợp.
- **Application Class Loader:** nạp lớp ứng dụng từ classpath hoặc module path theo cấu hình.

Cơ chế delegation (ủy quyền) thường khiến class loader hỏi loader cha trước khi tự tìm lớp. Cơ chế này giúp tránh việc ứng dụng vô tình thay thế các lớp nền tảng. Ứng dụng có thể định nghĩa custom class loader cho các nhu cầu như plugin hoặc nạp lớp động; cách hoạt động cụ thể phụ thuộc vào thiết kế loader.

### 5.2. Linking và initialization

Sau khi class được nạp, JVM thực hiện các bước liên quan đến liên kết:

- **Verification:** kiểm tra cấu trúc class file và các ràng buộc an toàn của bytecode.
- **Preparation:** tạo các cấu trúc cần thiết cho lớp và chuẩn bị vùng lưu trữ cho biến static với giá trị mặc định.
- **Resolution:** chuyển các symbolic reference thành tham chiếu có thể sử dụng trực tiếp. Việc này có thể diễn ra theo cách eager hoặc lazy tùy trường hợp.

Initialization thực thi các bộ khởi tạo static và phép gán static tương ứng. Khởi tạo lớp diễn ra theo quy tắc của JVM, thường được kích hoạt bởi lần sử dụng chủ động đầu tiên của lớp. Vì vậy, thời điểm nạp lớp và thời điểm khởi tạo lớp không nhất thiết trùng nhau.

### 5.3. Runtime data areas — các vùng dữ liệu khi chạy

JVM định nghĩa các vùng dữ liệu runtime với phạm vi chia sẻ khác nhau:

| Vùng dữ liệu | Phạm vi | Vai trò |
|---|---|---|
| Heap | Chia sẻ giữa các luồng | Lưu trữ đối tượng và mảng được cấp phát khi chạy; garbage collector quản lý việc thu hồi |
| Java Virtual Machine Stack | Mỗi luồng có stack riêng | Lưu stack frame cho các lần gọi phương thức |
| PC Register | Mỗi luồng có một PC riêng | Theo dõi vị trí bytecode đang được thực thi trong luồng |
| Native Method Stack | Gắn với luồng | Hỗ trợ thực thi native method |
| Method Area | Chia sẻ giữa các luồng | Lưu cấu trúc lớp, metadata, mã phương thức và runtime constant pool theo mô hình JVM |

Mỗi lần gọi phương thức, JVM tạo một **stack frame** cho lời gọi đó. Frame chứa thông tin như local variables, operand stack và dữ liệu phục vụ liên kết động hoặc kết thúc phương thức. Khi phương thức kết thúc, frame tương ứng được loại khỏi stack.

Heap là nơi các đối tượng thường được cấp phát. Nhiều luồng có thể cùng truy cập một đối tượng trên heap, vì vậy chương trình cần dùng các cơ chế đồng bộ phù hợp khi có truy cập đồng thời và thay đổi trạng thái dùng chung.

**Method Area** là khái niệm trong đặc tả JVM. Cách triển khai nội bộ phụ thuộc JVM. Chẳng hạn, HotSpot dùng **Metaspace** để lưu metadata lớp trong native memory từ Java 8; Metaspace không phải tên vùng bộ nhớ bắt buộc trong đặc tả JVM.

### 5.4. Execution engine

Execution engine chịu trách nhiệm thực thi bytecode. Hai cơ chế quan trọng là:

- **Interpreter:** đọc và thực thi bytecode từng lệnh. Cơ chế này giúp chương trình bắt đầu chạy mà không cần biên dịch toàn bộ mã thành mã máy trước.
- **JIT compiler (Just-In-Time compiler):** theo dõi những đoạn mã được thực thi thường xuyên và biên dịch chúng thành mã máy để cải thiện hiệu năng. JVM có thể áp dụng tối ưu hóa dựa trên hành vi runtime và điều chỉnh khi giả định tối ưu hóa không còn đúng.

Vì có JIT, thời gian chạy của một chương trình có thể thay đổi giữa giai đoạn khởi động và giai đoạn đã chạy ổn định. Một phép đo hiệu năng đáng tin cậy cần tính đến warm-up, dữ liệu đầu vào và môi trường thực thi.

### 5.5. Garbage collector

Garbage collector (GC) tự động thu hồi bộ nhớ của những đối tượng không còn có thể được chương trình truy cập thông qua các đường tham chiếu hợp lệ. Điều này giảm nhu cầu giải phóng bộ nhớ thủ công, nhưng không có nghĩa là ứng dụng không thể gặp vấn đề bộ nhớ.

Một số điểm cần nhớ:

- Đối tượng còn được tham chiếu có thể tiếp tục sống dù ứng dụng không còn cần về mặt nghiệp vụ.
- Giữ tham chiếu lâu hơn cần thiết có thể làm tăng bộ nhớ sử dụng và dẫn đến memory leak ở cấp độ logic.
- GC có thể tạm dừng một số luồng ứng dụng tùy collector và tình huống.
- Gọi `System.gc()` chỉ là yêu cầu JVM xem xét việc chạy GC; chương trình không được bảo đảm rằng GC sẽ chạy ngay.

Tên collector, cách chia heap và các cờ cấu hình là chi tiết phụ thuộc triển khai và phiên bản. Khi phân tích hiệu năng, hãy xem tài liệu của JDK đang chạy và đo bằng công cụ phù hợp thay vì giả định mọi JVM có cùng hành vi.

### 5.6. Native interface

JVM có thể tương tác với mã native thông qua cơ chế như Java Native Interface (JNI). Đây là cách ứng dụng Java gọi thư viện được viết bằng ngôn ngữ native hoặc tích hợp với thành phần của hệ điều hành. Native code hữu ích trong một số tình huống, nhưng có thể làm giảm tính di động và đưa thêm rủi ro về quản lý bộ nhớ, tương thích ABI hoặc lỗi tiến trình.

## 6. Ví dụ: biên dịch và chạy một chương trình Java

Tạo tệp **Main.java** với nội dung:

~~~java
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from JDK");
    }
}
~~~

Mở terminal tại thư mục chứa tệp và kiểm tra phiên bản công cụ:

~~~text
java --version
javac --version
~~~

Biên dịch mã nguồn:

~~~text
javac Main.java
~~~

Nếu biên dịch thành công, thư mục hiện tại có thêm tệp **Main.class** chứa bytecode. Chạy lớp bằng Java launcher:

~~~text
java Main
~~~

Kết quả stdout:

~~~text
Hello from JDK
~~~

Ở đây:

- `javac Main.java` là bước biên dịch do JDK cung cấp.
- `Main.class` chứa bytecode, chưa phải mã máy dành riêng cho CPU.
- `java Main` gọi Java launcher, launcher khởi tạo JVM và yêu cầu thực thi lớp `Main`.
- Tên lớp khi chạy không có phần mở rộng `.class`.

### Biên dịch vào thư mục riêng

Với dự án nhỏ, nên tách mã nguồn và bytecode đầu ra. Tạo thư mục `out` nếu chưa có, sau đó chạy:

~~~text
javac -d out Main.java
java -cp out Main
~~~

Tùy chọn `-d out` chỉ định nơi lưu class file. Tùy chọn `-cp out` (hoặc `-classpath out`) cho JVM biết nơi tìm lớp khi chạy. Với chương trình có package, đường dẫn thư mục đầu ra phải phản ánh cấu trúc package; hãy chạy lớp bằng tên đầy đủ, ví dụ `com.example.Main`.

### Biên dịch cho một phiên bản Java mục tiêu

Nếu đang dùng JDK mới hơn nhưng muốn tạo bytecode và giới hạn API theo Java 17, có thể dùng:

~~~text
javac --release 17 -d out Main.java
~~~

Tùy chọn `--release` yêu cầu compiler biên dịch theo phiên bản nền tảng được chỉ định, gồm mức ngôn ngữ, định dạng class file và tập API công khai tương ứng. Nó hữu ích hơn việc chỉ đặt một cờ target bytecode, vì mã biên dịch cũng được kiểm tra với API của phiên bản mục tiêu.

### Chạy trực tiếp một tệp nguồn

Từ Java 11, Java launcher hỗ trợ source-file mode:

~~~text
java Main.java
~~~

Lệnh này cho phép chạy một tệp nguồn đơn giản mà không cần gọi `javac` thủ công trước. Với quy trình build của dự án, việc biên dịch rõ ràng bằng `javac` hoặc build tool vẫn giúp kiểm soát đầu ra và classpath tốt hơn.

## 7. Phân biệt JDK, JRE và JVM

| Khái niệm | Trả lời câu hỏi | Thành phần / vai trò |
|---|---|---|
| JDK | Cần gì để phát triển ứng dụng Java? | Compiler, launcher, runtime, thư viện nền tảng và công cụ phát triển |
| JRE | Cần gì để chạy ứng dụng Java? | Khái niệm môi trường runtime gồm JVM, thư viện và thành phần hỗ trợ |
| JVM | Ai thực thi bytecode? | Máy ảo nạp, kiểm tra và thực thi class file; quản lý runtime |

Trong mô hình lịch sử thường dùng để giải thích, JRE bao gồm JVM và các thư viện runtime, còn JDK bao gồm môi trường runtime cùng công cụ phát triển. Mô hình này vẫn hữu ích để hiểu vai trò, nhưng không nên dùng nó để suy ra cách mọi nhà cung cấp đóng gói phần mềm hiện nay.

Từ Java 9, nền tảng được tổ chức theo module. Nhiều nhà cung cấp không còn phát hành bộ cài JRE độc lập theo kiểu cũ cho mọi phiên bản. Một JDK đầy đủ vẫn là lựa chọn thuận tiện cho máy phát triển. Khi chỉ cần runtime tối giản để triển khai, có thể xem xét runtime image tùy chỉnh bằng công cụ `jlink`, nếu quy trình và ứng dụng phù hợp.

## 8. Cài đặt và kiểm tra môi trường JDK

Sau khi cài JDK, hãy kiểm tra cả compiler và launcher:

~~~text
java --version
javac --version
~~~

Hai lệnh cần trỏ đến bộ cài phù hợp với dự án. Nếu `java` chạy được nhưng `javac` không được nhận diện, có thể máy chỉ có runtime hoặc biến PATH chưa trỏ đến thư mục `bin` của JDK.

Các khái niệm môi trường thường gặp:

- **JAVA_HOME:** thường trỏ đến thư mục gốc của JDK, ví dụ `C:\Program Files\Java\jdk-17` trên Windows hoặc một đường dẫn JDK tương ứng trên macOS/Linux. Không đặt `JAVA_HOME` trỏ trực tiếp vào thư mục `bin`.
- **PATH:** nên có thư mục `bin` của JDK để gọi `java`, `javac` và các công cụ liên quan từ terminal.
- **PATH và JAVA_HOME có thể không đồng bộ:** terminal có thể tìm thấy một bản Java khác với bản mà IDE hoặc build tool đang sử dụng.

Trên Windows, dùng `where.exe java` và `where.exe javac` để xem các executable được tìm thấy. Trên macOS/Linux, có thể dùng `which -a java` và `which -a javac`. Sau khi thay đổi biến môi trường, hãy mở terminal mới để kiểm tra lại.

## 9. Lỗi thường gặp và cách xử lý

### `javac` không được nhận diện

**Nguyên nhân thường gặp:** chưa cài JDK hoặc PATH chưa chứa thư mục `bin` của JDK.

**Cách xử lý:** kiểm tra thư mục cài đặt JDK, đặt JAVA_HOME về thư mục gốc và bổ sung `%JAVA_HOME%\bin` trên Windows hoặc `$JAVA_HOME/bin` trên macOS/Linux vào PATH. Mở terminal mới rồi chạy `javac --version`.

### `java` và `javac` có phiên bản khác nhau

**Nguyên nhân thường gặp:** PATH chứa nhiều bản Java hoặc IDE/build tool dùng JDK riêng.

**Cách xử lý:** kiểm tra đường dẫn thực tế của cả hai lệnh, sau đó thống nhất JDK được dùng trong terminal, IDE và công cụ build. Đừng chỉ dựa vào kết quả của một lệnh phiên bản.

### `Could not find or load main class`

**Nguyên nhân thường gặp:** classpath không chứa thư mục hoặc JAR có lớp cần chạy; tên lớp đầy đủ không khớp package; hoặc lệnh chạy dùng sai tên lớp.

**Cách xử lý:** xác nhận thư mục đầu ra, package và classpath. Nếu đã biên dịch vào `out`, thử `java -cp out Main` với lớp không có package, hoặc dùng tên đầy đủ như `java -cp out com.example.Main`.

### `UnsupportedClassVersionError`

**Nguyên nhân thường gặp:** class file được biên dịch bởi phiên bản Java mới hơn phiên bản JVM đang chạy.

**Cách xử lý:** nâng phiên bản runtime để tương thích hoặc biên dịch lại với `javac --release` theo phiên bản Java mục tiêu mà môi trường triển khai hỗ trợ.

### Chạy được trên máy phát triển nhưng lỗi trên máy triển khai

**Nguyên nhân có thể có:** khác phiên bản JDK/JVM, thiếu module hoặc dependency, classpath khác, hệ điều hành/kiến trúc khác, hay thiếu native library.

**Cách xử lý:** ghi rõ phiên bản Java mục tiêu, quản lý dependency và cấu hình build nhất quán, đồng thời kiểm tra runtime thực tế của môi trường triển khai. Với ứng dụng dùng native code, kiểm tra thêm thư viện và kiến trúc hệ điều hành.

## 10. Cách ghi nhớ khi làm việc với Java

- Khi cần **biên dịch** mã nguồn `.java`, dùng `javac` thuộc JDK.
- Khi cần **khởi chạy** lớp hoặc JAR, dùng `java`; launcher sẽ khởi tạo JVM.
- Khi cần hiểu **bytecode được thực thi và quản lý ra sao**, tìm hiểu JVM, class loader, runtime data areas, execution engine và GC.
- Khi gặp lỗi phiên bản, kiểm tra cả compiler lẫn runtime. Phiên bản JDK dùng để build và phiên bản JVM dùng để chạy cần tương thích với class file và API mà ứng dụng yêu cầu.
- Khi triển khai, xác định rõ ứng dụng cần một JDK đầy đủ hay chỉ cần runtime phù hợp.

JDK cung cấp bộ công cụ phát triển và môi trường chạy; JVM thực thi bytecode theo đặc tả của nền tảng Java. Nắm được hai vai trò này giúp bạn hiểu đúng quy trình từ mã nguồn đến chương trình đang chạy, cũng như khoanh vùng lỗi khi biên dịch hoặc vận hành ứng dụng.