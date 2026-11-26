# Các tính năng chính thức của Java 22: FFM, biến không tên, chạy nguồn nhiều tệp và G1 region pinning

Java 22 bổ sung nhiều cải tiến cho ngôn ngữ, thư viện, công cụ chạy chương trình và máy ảo. Bài học này tập trung vào bốn tính năng đã trở thành chính thức trong Java 22 và vẫn có ích khi phát triển với JDK hiện đại:

- **Foreign Function & Memory API (FFM)** – kết nối Java với hàm native và vùng nhớ ngoài heap.
- **Unnamed Variables & Patterns** – bỏ tên biến hoặc thành phần pattern không được sử dụng.
- **Launch Multi-File Source-Code Programs** – chạy chương trình gồm nhiều file `.java` trực tiếp bằng lệnh `java`.
- **Region Pinning for G1** – cho phép G1 tiếp tục thu gom rác khi mã native đang giữ tham chiếu cần được cố định.

Đây đều là tính năng chính thức, không cần bật preview. Các ví dụ hướng đến API ổn định từ Java 22 trở đi; khi triển khai ứng dụng, hãy dùng một JDK còn được nhà cung cấp hỗ trợ.

## 1. Bản đồ bốn tính năng

| JEP | Tính năng | Phạm vi | Giá trị trong Java hiện đại |
|---|---|---|---|
| [454](https://openjdk.org/jeps/454) | Foreign Function & Memory API | Thư viện và native interop | Dùng `java.lang.foreign` để gọi hàm native và thao tác vùng nhớ ngoài heap có kiểm soát vòng đời. |
| [456](https://openjdk.org/jeps/456) | Unnamed Variables & Patterns | Ngôn ngữ Java | Làm rõ ý định bỏ qua dữ liệu không cần dùng trong vòng lặp, lambda, `catch` và record pattern. |
| [458](https://openjdk.org/jeps/458) | Launch Multi-File Source-Code Programs | Java launcher | Chạy chương trình nhiều file nguồn trực tiếp khi học, thử nghiệm hoặc viết tiện ích nhỏ. |
| [423](https://openjdk.org/jeps/423) | Region Pinning for G1 | Garbage collector | Giảm thời gian G1 phải chờ khi JNI giữ con trỏ tới dữ liệu Java trong critical region. |

Các tính năng phục vụ những nhu cầu khác nhau. FFM và unnamed variables/patterns tác động trực tiếp đến cách viết mã. Multi-file source launch giúp rút ngắn vòng lặp thử nghiệm. Region pinning là cải tiến bên trong JVM; ứng dụng thường không cần thay đổi mã để nhận lợi ích này.

## 2. Foreign Function & Memory API – JEP 454

### Khi nào cần FFM?

Ứng dụng Java đôi khi cần gọi thư viện C/C++, dùng thư viện hệ điều hành, trao đổi dữ liệu với thiết bị hoặc đọc vùng nhớ do mã native quản lý. Trước đây, JNI là một cơ chế phổ biến cho việc này, nhưng nó đòi hỏi phần mã native và quy trình tích hợp riêng.

FFM cung cấp API Java để thực hiện hai nhóm công việc:

- **Foreign function**: gọi hàm nằm ngoài JVM (*downcall*) hoặc cho phép mã native gọi ngược vào Java (*upcall*).
- **Foreign memory**: đọc và ghi vùng nhớ ngoài heap, chẳng hạn bộ đệm do thư viện native cấp phát hoặc dữ liệu ánh xạ từ file.

FFM được chuẩn hóa trong JDK 22 qua JEP 454. API chính thức nằm trong package `java.lang.foreign`. Với các dự án hiện đại, hãy học API này thay vì những API FFM thử nghiệm cũ thuộc module `jdk.incubator.foreign`.

### Các khái niệm chính

| Thành phần | Vai trò |
|---|---|
| `MemorySegment` | Đại diện cho một vùng nhớ liên tục, có thể nằm trong heap hoặc ngoài heap. |
| `Arena` | Quản lý vòng đời vùng nhớ được cấp phát. Khi arena đóng, các segment gắn với arena đó không còn được truy cập. |
| `MemoryLayout` / `ValueLayout` | Mô tả cấu trúc, kích thước và kiểu dữ liệu tại các vị trí trong vùng nhớ. |
| `Linker` | Tạo liên kết giữa Java và hàm native theo calling convention của nền tảng. |
| `SymbolLookup` | Tìm địa chỉ của hàm native trong các thư viện đã nạp hoặc trong lookup mặc định. |
| `FunctionDescriptor` | Mô tả kiểu trả về và các tham số của hàm native. |

`Arena` giúp xác định rõ thời điểm giải phóng vùng nhớ. `MemorySegment` cung cấp các thao tác có kiểm tra phạm vi và vòng đời, nhờ vậy mã Java có thể quản lý bộ nhớ native có cấu trúc hơn. Tuy nhiên, gọi native code vẫn là một ranh giới tin cậy: khai báo sai chữ ký hàm hoặc truyền địa chỉ không hợp lệ vẫn có thể làm hỏng tiến trình.

### Ví dụ: gọi hàm `strlen` của C

Ví dụ sau gọi hàm `strlen` trong thư viện C tiêu chuẩn để lấy độ dài chuỗi UTF-8 đã cấp phát ngoài heap. Chữ ký `size_t` dùng `JAVA_LONG` trong ví dụ Linux/x64 này; kiểu layout cần khớp ABI của nền tảng thực tế.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public class FfmDemo {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        SymbolLookup standardLibrary = linker.defaultLookup();

        MethodHandle strlen = linker.downcallHandle(
            standardLibrary.find("strlen").orElseThrow(),
            FunctionDescriptor.of(
                ValueLayout.JAVA_LONG,
                ValueLayout.ADDRESS
            )
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cString = arena.allocateFrom("Hello");
            long length = (long) strlen.invokeExact(cString);
            System.out.println(length); // 5
        }
    }
}
```

Các bước chính:

1. Lấy `Linker` của nền tảng và tìm symbol `strlen`.
2. Mô tả hàm C bằng `FunctionDescriptor`: trả về số nguyên 64-bit trong ví dụ này và nhận một địa chỉ.
3. Tạo `MethodHandle` bằng `downcallHandle`.
4. Mở `Arena`, cấp phát chuỗi C có ký tự kết thúc null, gọi hàm native rồi đóng arena.

Khi chạy ứng dụng trên classpath, các thao tác như tạo downcall handle là restricted operations và cần cấp quyền native access. Ví dụ có thể chạy trên JDK hiện đại bằng:

```bash
java --enable-native-access=ALL-UNNAMED FfmDemo.java
```

Với ứng dụng dạng module, chỉ định tên module cần quyền native access thay vì cấp cho toàn bộ classpath. Hãy chỉ cấp quyền cho module thực sự cần gọi native code. Trên JDK 24 trở đi, native access không được bật sẽ phát cảnh báo theo mặc định khi thực hiện restricted operation; chính sách này được thiết kế để siết chặt hơn trong các bản JDK tương lai.

FFM phù hợp khi cần tích hợp thư viện native hoặc quản lý vùng nhớ ngoài heap. Nó không tự động chuyển mọi thư viện JNI sang FFM và cũng không làm cho mọi thao tác native trở nên an toàn tuyệt đối. Cần hiểu ABI, quyền sở hữu bộ nhớ, vòng đời segment và hợp đồng của thư viện được gọi.

## 3. Unnamed Variables & Patterns – JEP 456

### Bỏ tên khi giá trị không được sử dụng

Trong một số đoạn mã, Java yêu cầu khai báo biến vì cấu trúc cú pháp cần một biến, nhưng logic không cần đọc giá trị đó. Trước Java 22, lập trình viên thường đặt tên như `ignored`, `unused` hoặc `ignoredException`. Những tên này vẫn tạo ra một biến có thể được tham chiếu dù chương trình không cần đến nó.

Java 22 cho phép dùng dấu gạch dưới `_` làm tên biến không định danh (*unnamed variable*) hoặc pattern không định danh (*unnamed pattern*). Vì `_` là từ khóa dành riêng, không thể dùng nó làm tên biến thông thường rồi đọc giá trị.

Ví dụ, vòng lặp chỉ cần đếm số phần tử:

```java
int[] orderIds = {34, 45, 23, 27, 15};
int total = 0;

for (int _ : orderIds) {
    total++;
}

System.out.println(total); // 5
```

Biến vòng lặp được khai báo nhưng không có tên để sử dụng trong thân vòng lặp. Ý định bỏ qua từng giá trị được thể hiện trực tiếp trong mã.

Unnamed variables cũng hữu ích trong `catch`, lambda và try-with-resources:

```java
try {
    int number = Integer.parseInt(input);
    System.out.println(number);
} catch (NumberFormatException _) {
    System.out.println("Input is not a number");
}

java.util.function.Consumer<String> task = _ -> System.out.println("Task started");
task.accept("unused input");

try (var _ = new java.io.FileReader("input.txt")) {
    System.out.println("Resource opened");
}
```

Trong ví dụ lambda, tham số đầu vào không cần thiết cho thân lambda. Trong try-with-resources, tài nguyên vẫn được đóng tự động khi thoát khối lệnh dù không cần tham chiếu tới biến tài nguyên. Đoạn try-with-resources là một mảnh mã trong phương thức có khai báo xử lý `IOException`.

### Bỏ qua thành phần của record pattern

Unnamed pattern giúp khớp một thành phần của record mà không tạo biến cho thành phần đó. Ví dụ sau chỉ cần tọa độ của `Point`, không cần màu của `ColoredPoint`:

```java
class PatternDemo {
    record Point(int x, int y) {}
    record ColoredPoint(Point point, String color) {}

    static int xCoordinate(Object value) {
        if (value instanceof ColoredPoint(Point point, _)) {
            return point.x();
        }
        return -1;
    }
}
```

Pattern `ColoredPoint(Point point, _)` yêu cầu đối tượng khớp với record `ColoredPoint`, đồng thời khớp thành phần `point`. Thành phần `color` vẫn được kiểm tra theo cấu trúc record nhưng không tạo biến để sử dụng. Cách viết này làm rõ rằng màu sắc không tham gia vào phép tính.

Unnamed pattern cũng có thể dùng trong `switch` khi chỉ cần phân biệt kiểu mà không cần giá trị:

```java
sealed interface Employee permits Salaried, Freelancer {}
record Salaried(String name, long salary) implements Employee {}
record Freelancer(String name) implements Employee {}

class EmployeeDemo {
    static String category(Employee employee) {
        return switch (employee) {
            case Salaried salaried -> "Salaried: " + salaried.name();
            case Freelancer _ -> "Freelancer";
        };
    }
}
```

### Khi nào nên dùng

- Dùng `_` khi biến được khai báo chỉ vì cú pháp yêu cầu và giá trị của nó không cần thiết.
- Dùng unnamed pattern khi cần khớp cấu trúc hoặc kiểu của dữ liệu nhưng không cần giữ một thành phần để xử lý tiếp.
- Giữ tên có ý nghĩa cho mọi giá trị sẽ được đọc, truyền tiếp hoặc dùng trong điều kiện. `_` không phải cách viết tắt cho một biến mà sau đó vẫn cần truy cập.

Tính năng này đã là một phần chính thức của ngôn ngữ từ Java 22, vì vậy không cần `--enable-preview`.

## 4. Launch Multi-File Source-Code Programs – JEP 458

### Chạy nhiều file nguồn trực tiếp

Java đã hỗ trợ chạy một file nguồn trực tiếp bằng `java` từ JDK 11. JEP 458 mở rộng chế độ đó trong JDK 22 để launcher có thể tìm, biên dịch và nạp các file nguồn khác mà file chính phụ thuộc vào.

Giả sử thư mục có cấu trúc:

```text
demo/
├── Main.java
└── greeting/
    └── Greeter.java
```

File `greeting/Greeter.java`:

```java
package greeting;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

File `Main.java`:

```java
import greeting.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Greeter().greet("Java 22"));
    }
}
```

Chạy tại thư mục `demo`:

```bash
java Main.java
```

Launcher nhận ra `Main.java` là file nguồn, biên dịch file chính cùng những file nguồn cần thiết mà nó tham chiếu, rồi chạy chương trình. Các file phụ phải nằm đúng đường dẫn tương ứng với package để launcher tìm được chúng.

Nếu chương trình dùng thư viện bên ngoài, hãy cung cấp JAR qua classpath:

```bash
java --class-path "lib/*" Main.java
```

### Giới hạn và trường hợp sử dụng

Chế độ chạy nguồn nhiều file phù hợp để học Java, tạo ví dụ có nhiều lớp, thử API hoặc viết tiện ích nội bộ nhỏ. Nó giúp người học chia lớp ra nhiều file mà chưa cần thiết lập bước biên dịch thủ công.

Đây vẫn là source-file mode của launcher. Với ứng dụng cần quản lý dependency, kiểm thử, đóng gói, xử lý annotation processor, cấu hình nhiều source set hoặc phát hành artifact, hãy tiếp tục dùng quy trình build phù hợp như Maven hoặc Gradle. Tính năng này không tự tìm và tải thư viện bên thứ ba; classpath hoặc module path vẫn phải được cấu hình.

## 5. Region Pinning for G1 – JEP 423

### Vì sao cần pinning?

Garbage collector có thể di chuyển đối tượng trong heap để gom vùng nhớ trống. Tuy nhiên, khi mã native đang giữ con trỏ trực tiếp tới một mảng Java trong JNI critical region, JVM phải bảo đảm đối tượng được trỏ tới không bị di chuyển cho đến khi con trỏ được trả lại.

JNI cung cấp các cặp hàm như `GetPrimitiveArrayCritical()` và `ReleasePrimitiveArrayCritical()` để lấy và giải phóng quyền truy cập này. Đoạn mã giữa hai lời gọi là critical region; mã native phải tuân thủ các giới hạn nghiêm ngặt và kết thúc vùng này sớm.

Trước khi G1 hỗ trợ region pinning, việc giữ con trỏ trong critical region có thể buộc G1 trì hoãn hoạt động thu gom rác. JEP 423 cho phép G1 tiếp tục thu gom các vùng khác trong heap trong khi vẫn giữ những đối tượng cần thiết ở vị trí ổn định.

### Cách hoạt động và ảnh hưởng

G1 chia heap thành nhiều region. Khi JNI cần giữ một đối tượng không được di chuyển, G1 pin region chứa đối tượng đó. Trong lúc thu gom rác, G1 có thể tiếp tục xử lý các vùng phù hợp khác; vùng có đối tượng bị pin sẽ không được di chuyển theo cách làm mất hiệu lực con trỏ native.

Điều này giúp giảm thời gian chờ và độ trễ trong ứng dụng có sử dụng JNI critical regions. Một số hệ quả cần hiểu:

- Đây là thay đổi bên trong G1, không phải API Java mà ứng dụng phải gọi.
- Tính năng chỉ liên quan đến G1; không nên suy rộng hành vi này sang mọi garbage collector.
- Đối tượng đang bị pin không thể được di chuyển trong lần thu gom tương ứng. Nhật ký GC hiện đại vẫn có thể ghi nhận `Evacuation Failure: Pinned`; vùng đó có thể được xem xét thu gom lại ở chu kỳ sau.
- Mã JNI vẫn phải giải phóng con trỏ đúng cách và không được giữ critical region lâu. Region pinning không loại bỏ các ràng buộc của JNI.

Nếu đang phân tích độ trễ của ứng dụng dùng G1 và native code, có thể bật log GC để quan sát các sự kiện evacuation:

```bash
java -Xlog:gc -jar application.jar
```

Không cần thêm cờ để bật region pinning. Khi JVM sử dụng G1, cơ chế này được áp dụng tự động cho những tình huống pinning phù hợp.

## 6. Chọn tính năng phù hợp với công việc

| Nhu cầu | Tính năng nên tìm hiểu | Lý do |
|---|---|---|
| Gọi thư viện C/C++, truy cập vùng nhớ native | FFM | Cung cấp API Java chính thức cho foreign functions và foreign memory. |
| Viết vòng lặp, lambda hoặc pattern có dữ liệu không dùng | Unnamed Variables & Patterns | Giảm biến giả như `ignored` và thể hiện rõ phần dữ liệu bị bỏ qua. |
| Chia ví dụ thành nhiều file nhưng muốn chạy nhanh | Multi-File Source-Code Launch | Launcher tự biên dịch các file nguồn phụ theo cấu trúc package. |
| Phân tích độ trễ GC của ứng dụng dùng JNI với G1 | Region Pinning for G1 | Giải thích cách G1 xử lý đối tượng phải đứng yên trong critical region. |

Hai tính năng ngôn ngữ và FFM là kiến thức có thể áp dụng trực tiếp trong mã nguồn. Multi-file launch là công cụ hỗ trợ quá trình phát triển. Region pinning quan trọng khi phân tích tương tác giữa JVM và native code; phần lớn ứng dụng Java thuần không cần cấu hình hay gọi trực tiếp tính năng này.

## 7. Tính tương thích và cách học trong JDK hiện đại

| Tính năng | Phiên bản đầu tiên | Cần bật preview? | Ghi chú khi dùng hiện nay |
|---|---:|---|---|
| FFM API | Java 22 | Không | Dùng package `java.lang.foreign`; cấp native access cho module gọi restricted methods. |
| Unnamed Variables & Patterns | Java 22 | Không | `_` là từ khóa dành riêng cho khai báo không định danh và unnamed pattern. |
| Multi-File Source-Code Launch | Java 22 | Không | Dùng `java Main.java`; bảo đảm file nguồn phụ khớp cấu trúc package. |
| G1 Region Pinning | Java 22 | Không | Cơ chế tự động của G1 khi xử lý JNI critical regions. |

Khi đọc tài liệu Java 22, cần phân biệt các tính năng chính thức trong bài với những đề xuất khác từng xuất hiện ở dạng preview hoặc incubator trong cùng bản phát hành. Bốn nội dung ở đây đã có trạng thái chính thức từ Java 22 và tiếp tục được tài liệu JDK hiện đại mô tả. Đối với dự án mới, hãy dùng phiên bản JDK còn được hỗ trợ và kiểm tra tài liệu đúng phiên bản đó, nhất là khi tích hợp native code hoặc phụ thuộc vào hành vi của garbage collector.

## Tài liệu tham khảo

- [JEP 454 – Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [JEP 456 – Unnamed Variables & Patterns](https://openjdk.org/jeps/456)
- [JEP 458 – Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458)
- [JEP 423 – Region Pinning for G1](https://openjdk.org/jeps/423)
- [Foreign Function and Memory API – Java SE 25](https://docs.oracle.com/en/java/javase/25/core/foreign-function-and-memory-api.html)
- [Restricted Methods and Native Access – Java SE 25](https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html)
- [Unnamed Variables and Patterns – Java SE 22](https://docs.oracle.com/en/java/javase/22/language/unnamed-variables-and-patterns.html)
- [Launching Multi-File Source-Code Programs – dev.java](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/)
- [G1 Garbage Collector – Java SE 25](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html)
