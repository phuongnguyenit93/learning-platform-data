# Phạm vi học: các tính năng trong Java 22 còn hữu ích với Java hiện đại

Java 22 là một bản phát hành tính năng của Java. Một số nội dung được hoàn thiện ngay trong Java 22, còn nhiều nội dung mới chỉ ở giai đoạn preview hoặc incubator rồi tiếp tục thay đổi ở các bản phát hành sau. Vì vậy, khi học Java 22 ở thời điểm hiện tại, cần phân biệt **phiên bản xuất hiện trong Java 22** với **phiên bản mà tính năng trở thành ổn định**.

Bài này lấy JDK 27, bản phát hành GA mới nhất tại thời điểm biên soạn, làm mốc kiểm tra trạng thái. Nội dung tập trung vào những tính năng Java 22 vẫn có giá trị trong Java hiện đại; các tính năng đã bị rút khỏi lộ trình được loại khỏi phạm vi học.

## 1. Bản đồ tính năng còn hữu ích

| Tính năng trong Java 22 | JEP trong Java 22 | Trạng thái ổn định hoặc mới nhất đến JDK 27 | Phạm vi sử dụng |
| --- | --- | --- | --- |
| Unnamed Variables & Patterns | JEP 456 | Final từ Java 22 | Viết pattern matching và xử lý biến không cần dùng gọn hơn |
| Foreign Function & Memory API | JEP 454 | Final từ Java 22 | Gọi thư viện native và quản lý bộ nhớ ngoài heap |
| Launch Multi-File Source-Code Programs | JEP 458 | Final từ Java 22 | Chạy chương trình Java nhiều file nguồn trực tiếp bằng launcher |
| G1 Region Pinning | JEP 423 | Final từ Java 22 | Cải thiện hành vi GC khi JNI đang giữ vùng nhớ quan trọng |
| Class-File API | JEP 457 | Preview ở Java 22, final ở Java 24 qua JEP 484 | Đọc, tạo và biến đổi bytecode/class file |
| Stream Gatherers | JEP 461 | Preview ở Java 22, final ở Java 24 qua JEP 485 | Tạo phép biến đổi trung gian tùy chỉnh cho Stream |
| Scoped Values | JEP 464 | Preview lần hai ở Java 22, final ở Java 25 qua JEP 506 | Truyền dữ liệu ngữ cảnh bất biến qua chuỗi lời gọi và luồng |
| Flexible Constructor Bodies | JEP 447 | Preview ở Java 22, final ở Java 25 qua JEP 513 | Kiểm tra hoặc chuẩn hóa tham số trước lời gọi constructor cha |
| Compact Source Files & Instance Main Methods | JEP 463 | Preview lần hai ở Java 22, final ở Java 25 qua JEP 512 | Viết chương trình nhỏ mà không cần khai báo lớp tường minh |
| Structured Concurrency | JEP 462 | Preview lần hai ở Java 22; vẫn là preview ở JDK 27 qua JEP 533 | Quản lý nhóm tác vụ đồng thời theo một phạm vi vòng đời |
| Vector API | JEP 460 | Incubator lần thứ bảy ở Java 22; vẫn incubator ở JDK 27 qua JEP 537 | Tính toán SIMD cho workload cần hiệu năng cao |

Các trạng thái có ý nghĩa khác nhau:

- **Final**: API hoặc cú pháp đã ổn định trong phiên bản được nêu; có thể dùng mà không bật preview.
- **Preview**: tính năng đang được thử nghiệm ở cấp ngôn ngữ hoặc API. Khi dùng phải bật `--enable-preview` lúc biên dịch và chạy đúng phiên bản JDK; thiết kế có thể còn thay đổi.
- **Incubator**: API thử nghiệm được phát hành trong module riêng. API có thể thay đổi đáng kể hoặc bị loại bỏ; không nên xem là nền tảng ổn định cho ứng dụng production.

## 2. Những tính năng đã ổn định

### 2.1. Unnamed Variables & Patterns — JEP 456

Java 22 cho phép dùng dấu gạch dưới `_` để biểu thị một biến hoặc thành phần pattern có chủ ý không sử dụng. Trước đây, lập trình viên thường phải đặt một tên tạm như `ignored`, `unused` hoặc `unusedValue`, dù giá trị đó không tham gia xử lý.

Ví dụ với record pattern:

```java
record Point(int x, int y) {}

static void printX(Object value) {
    if (value instanceof Point(int x, _)) {
        System.out.println(x);
    }
}
```

Chương trình chỉ cần tọa độ `x`, nên thành phần `y` được biểu diễn bằng `_`. Có thể dùng unnamed variable trong những ngữ cảnh phù hợp khác, chẳng hạn biến trong `catch` hoặc resource trong `try-with-resources` mà chương trình không cần tham chiếu đến.

Giá trị thực tế của tính năng này là làm rõ ý định: một giá trị bị bỏ qua có chủ đích, thay vì một biến được khai báo rồi quên sử dụng. Tính năng đã final từ Java 22, vì vậy không cần bật preview.

### 2.2. Foreign Function & Memory API — JEP 454

Foreign Function & Memory API (FFM) cung cấp API chuẩn trong package `java.lang.foreign` để Java tương tác với mã native và vùng nhớ nằm ngoài heap do JVM quản lý. API này hỗ trợ hai nhu cầu chính:

- Gọi hàm trong thư viện native thông qua linker và method handle.
- Truy cập bộ nhớ native thông qua `MemorySegment`, layout và arena có phạm vi vòng đời rõ ràng.

Ví dụ cấp phát và truy cập một vùng nhớ native chứa số nguyên:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class OffHeapExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cell = arena.allocate(ValueLayout.JAVA_INT);
            cell.set(ValueLayout.JAVA_INT, 0, 42);

            int value = cell.get(ValueLayout.JAVA_INT, 0);
            System.out.println(value);
        }
    }
}
```

Khi `arena` được đóng, vùng nhớ do arena quản lý hết hiệu lực. Cách tổ chức này giúp giới hạn thời gian sử dụng bộ nhớ native và giảm nguy cơ truy cập vùng nhớ đã giải phóng. Để gọi hàm C, chương trình dùng `Linker`, `SymbolLookup` và `MethodHandle` để mô tả lời gọi phù hợp với ABI của nền tảng.

FFM hữu ích khi tích hợp thư viện native, tận dụng thư viện hệ thống, làm việc với thiết bị hoặc xử lý dữ liệu ngoài heap. Đây không phải lý do để chuyển mọi ứng dụng sang native code: chỉ dùng khi có yêu cầu tích hợp hoặc hiệu năng cụ thể, kiểm soát chính xác layout, quyền truy cập và vòng đời bộ nhớ. Những lời gọi native có thể cần cấu hình quyền native access theo JDK và module đang chạy.

FFM đã final từ Java 22. Đây là một trong những API nền tảng đáng học nhất của bản phát hành này nếu công việc có liên quan đến native interop.

### 2.3. Launch Multi-File Source-Code Programs — JEP 458

Java launcher đã có chế độ chạy trực tiếp một file nguồn từ các phiên bản trước. Java 22 mở rộng khả năng đó để chương trình có thể gồm nhiều file nguồn. Nhờ vậy, một chương trình nhỏ có thể được tách thành lớp chính và các lớp hỗ trợ mà vẫn chạy trực tiếp bằng launcher.

Ví dụ, `Main.java` sử dụng lớp `Helper` được khai báo trong `Helper.java`:

```java
// Main.java
public class Main {
    public static void main(String[] args) {
        System.out.println(Helper.message());
    }
}
```

```java
// Helper.java
class Helper {
    static String message() {
        return "Hello from another source file";
    }
}
```

Có thể khởi chạy chế độ source-file bằng lệnh:

```bash
java Main.java
```

Launcher có thể tự tìm, biên dịch và nạp các file nguồn phụ mà chương trình tham chiếu đến. Với lớp có package, vị trí file nguồn phải khớp cấu trúc package; thư viện đã đóng gói vẫn cần được đưa vào class path phù hợp. Tính năng này tiện cho ví dụ học tập, script nội bộ, thử nghiệm và tiện ích nhỏ. Với ứng dụng có dependency, module, quy trình build hoặc đóng gói phức tạp, vẫn nên dùng công cụ build như Maven hoặc Gradle.

### 2.4. Stream Gatherers — JEP 461, final ở Java 24

Stream Gatherers mở rộng Stream API bằng phép biến đổi trung gian có thể tự định nghĩa. Các phép trung gian quen thuộc như `map`, `filter` và `flatMap` đã đáp ứng nhiều tình huống, nhưng không thuận tiện cho mọi phép biến đổi theo nhóm hoặc cần giữ trạng thái giữa các phần tử.

Java 22 giới thiệu Gatherers ở trạng thái preview; API được hoàn thiện và final trong Java 24 qua JEP 485. Ví dụ dùng gatherer có sẵn để gom các phần tử thành cửa sổ cố định:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

public class GathererExample {
    public static void main(String[] args) {
        List<List<Integer>> windows = IntStream.rangeClosed(1, 7)
                .boxed()
                .gather(Gatherers.windowFixed(3))
                .toList();

        System.out.println(windows);
        // [[1, 2, 3], [4, 5, 6], [7]]
    }
}
```

Các gatherer dựng sẵn còn hỗ trợ những phép xử lý như cửa sổ trượt, tích lũy và ánh xạ có giới hạn đồng thời. Khi cần quy tắc riêng, có thể tạo `Gatherer` tùy chỉnh để đóng gói trạng thái và cách phát kết quả vào một bước trung gian có thể tái sử dụng.

Gatherers phù hợp với xử lý luồng dữ liệu, gom nhóm theo cửa sổ, tính toán tích lũy hoặc biến đổi tuần tự có trạng thái. Khi dùng trên JDK 24 trở lên, đây là API ổn định; mã cần chạy trên JDK 22 phải xem lại trạng thái preview của phiên bản đó.

### 2.5. Class-File API — JEP 457, final ở Java 24

Class-File API cung cấp API chuẩn trong package `java.lang.classfile` để đọc, tạo và biến đổi file `.class` theo định dạng của JVM. Java 22 đưa API này vào preview; JEP 484 hoàn thiện nó trong Java 24.

Ví dụ bắt đầu phân tích byte array của một class file:

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;

ClassModel model = ClassFile.of().parse(classBytes);
```

`ClassModel` biểu diễn cấu trúc class đã phân tích. Từ mô hình này, công cụ có thể duyệt metadata, method, field và attribute; API cũng cung cấp khả năng dựng mới hoặc biến đổi class file.

Đây là kiến thức chuyên sâu dành cho người xây dựng compiler, bytecode transformer, agent, công cụ phân tích, instrumentation hoặc framework. Ứng dụng nghiệp vụ thông thường hiếm khi cần thao tác trực tiếp với bytecode. Khi cần, API chuẩn của JDK giúp giảm phụ thuộc vào các API nội bộ không được cam kết ổn định.

### 2.6. Scoped Values — JEP 464, final ở Java 25

Scoped Values cho phép chia sẻ dữ liệu ngữ cảnh bất biến trong một phạm vi thực thi. Chúng đặc biệt hữu ích khi một request đi qua nhiều tầng gọi hàm và các tầng cần truy cập cùng một thông tin như request ID, thông tin người dùng hoặc cấu hình theo request.

Java 22 đưa Scoped Values vào preview lần thứ hai; tính năng trở thành API ổn định trong Java 25 qua JEP 506.

```java
public class RequestContext {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    static void handle(String requestId) {
        ScopedValue.where(REQUEST_ID, requestId).run(
                RequestContext::process
        );
    }

    static void process() {
        System.out.println("requestId=" + REQUEST_ID.get());
    }
}
```

Giá trị được gắn trong phạm vi `run`; khi xử lý kết thúc, binding đó không còn hiệu lực bên ngoài phạm vi. Scoped Values phù hợp với dữ liệu ngữ cảnh chỉ đọc và có vòng đời rõ ràng. Nếu cần một giá trị thay đổi độc lập theo thread, `ThreadLocal` vẫn có trường hợp sử dụng riêng; không nên thay thế máy móc mọi `ThreadLocal` bằng Scoped Values.

Scoped Values cũng có ý nghĩa trong ứng dụng dùng virtual threads và Structured Concurrency, vì dữ liệu ngữ cảnh có thể được truyền theo quy tắc của phạm vi tác vụ thay vì phải quản lý thủ công nhiều bản sao thread-local.

### 2.7. Flexible Constructor Bodies — JEP 447, final ở Java 25

Trước tính năng này, lời gọi tường minh `super(...)` hoặc `this(...)` phải đứng đầu constructor. Điều đó gây khó khăn khi lớp con cần kiểm tra hoặc chuẩn hóa tham số trước khi chuyển chúng cho constructor của lớp cha.

Flexible Constructor Bodies cho phép đặt một phần câu lệnh an toàn trước lời gọi constructor. Phần này có thể dùng tham số, biến cục bộ và phương thức static, nhưng không được truy cập đối tượng đang được khởi tạo qua `this` hoặc `super`.

```java
import java.util.Objects;

class User {
    User(String email) {}
}

class PremiumUser extends User {
    PremiumUser(String email) {
        String normalized = Objects.requireNonNull(email).trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("email must not be blank");
        }

        super(normalized);
    }
}
```

Việc kiểm tra xảy ra trước khi constructor của lớp cha chạy. Điều này hữu ích khi cần bảo đảm bất biến dữ liệu ngay từ đầu quá trình khởi tạo, nhất là khi constructor cha có thể gọi phương thức được override ở lớp con.

Tính năng được preview lần đầu trong Java 22 và final trong Java 25 qua JEP 513. Khi đọc tài liệu Java 22, hãy nhận biết đây là bản preview; khi viết mã ổn định hiện nay, dùng quy tắc final của Java 25 trở lên.

### 2.8. Compact Source Files & Instance Main Methods — JEP 463, final ở Java 25

Java 22 tiếp tục preview khả năng viết chương trình mà không cần khai báo lớp bao quanh và không bắt buộc phương thức `main` phải là `static`. Tính năng này được hoàn thiện trong Java 25 với tên Compact Source Files and Instance Main Methods, theo JEP 512.

Ví dụ một file nguồn tối giản:

```java
void main() {
    System.out.println("Hello, modern Java");
}
```

Có thể chạy file bằng source-file launcher:

```bash
java Hello.java
```

Mục tiêu chính là giảm phần cú pháp ban đầu để người học tập trung vào biến, điều kiện, vòng lặp, phương thức và cách giải quyết bài toán. Khi chương trình lớn dần, có thể chuyển sang cấu trúc lớp và package thông thường. Tính năng này bổ trợ cho việc dạy học và viết tiện ích nhỏ; nó không làm cho mô hình lớp của Java biến mất.

## 3. Những nội dung vẫn đang thử nghiệm

Hai API dưới đây vẫn tiếp tục phát triển ở các bản Java mới. Chúng đáng tìm hiểu về mặt ý tưởng và thử nghiệm có kiểm soát, nhưng trạng thái hiện tại cần được ghi nhớ khi quyết định đưa vào sản phẩm.

### 3.1. Structured Concurrency — JEP 462, preview ở Java 27

Structured Concurrency tổ chức một nhóm tác vụ đồng thời thành một đơn vị có vòng đời rõ ràng. Thay vì tạo nhiều tác vụ độc lập rồi tự quản lý việc chờ, hủy và xử lý lỗi ở nhiều nơi, chương trình tạo một phạm vi tác vụ; phạm vi đó điều phối việc hoàn thành và xử lý các tác vụ con.

Ví dụ thực tế là một request cần lấy thông tin sản phẩm, tồn kho và phí vận chuyển đồng thời. Nếu một tác vụ thất bại hoặc request bị hủy, mô hình structured concurrency giúp việc hủy và thu hồi các tác vụ còn lại có quy tắc rõ ràng hơn, giảm nguy cơ tác vụ chạy sót sau khi request kết thúc.

Trong Java 22, tính năng ở preview lần thứ hai. Đến JDK 27, JEP 533 tiếp tục ở preview lần thứ bảy; vì vậy API vẫn có thể thay đổi và cần `--enable-preview` khi biên dịch, chạy. Nên học nguyên tắc về cấu trúc vòng đời, hủy tác vụ và lan truyền lỗi trước; chỉ thử API trên đúng phiên bản JDK mục tiêu và tránh phụ thuộc vào nó trong thư viện hoặc ứng dụng production cần tương thích lâu dài.

### 3.2. Vector API — JEP 460, incubator ở Java 27

Vector API biểu diễn phép tính trên nhiều phần tử cùng lúc. JVM có thể ánh xạ các phép tính vector sang lệnh SIMD phù hợp với CPU, giúp tăng thông lượng cho một số workload so với cách xử lý từng phần tử bằng phép toán scalar.

API này có thể hữu ích trong xử lý ảnh, âm thanh, dữ liệu số, mô phỏng khoa học, phân tích dữ liệu hoặc một số tác vụ inference. Hiệu quả phụ thuộc dữ liệu, CPU, cách tổ chức vòng lặp và khả năng vector hóa; không thể mặc định rằng thay vòng lặp bằng Vector API sẽ luôn nhanh hơn.

Java 22 chứa lần incubator thứ bảy. Đến Java 27, Vector API vẫn ở incubator lần thứ mười hai qua JEP 537 và nằm trong module `jdk.incubator.vector`. Khi thử nghiệm cần thêm module, ví dụ:

```bash
javac --add-modules jdk.incubator.vector VectorExample.java
java --add-modules jdk.incubator.vector VectorExample
```

Chỉ nên đầu tư vào API này khi đã đo hiệu năng và xác định workload có lợi từ SIMD. Do API vẫn incubator, không nên coi chữ ký hiện tại là cam kết tương thích lâu dài.

## 4. Cải tiến runtime: G1 Region Pinning — JEP 423

G1 Region Pinning là cải tiến của garbage collector G1 trong Java 22. Trước đây, khi JNI giữ một vùng nhớ trong critical section, JVM có thể phải hạn chế hoặc tạm dừng một số hoạt động thu gom để tránh di chuyển vùng nhớ đang được native code sử dụng. Region pinning cho phép G1 ghim region liên quan và tiếp tục thu gom các region khác, qua đó giảm độ trễ trong những tình huống JNI critical.

Đây là cải tiến bên trong JVM, không phải API mà lập trình viên cần gọi trực tiếp. Ứng dụng thường nhận lợi ích khi chạy trên JDK có hỗ trợ G1 Region Pinning và sử dụng các đường JNI liên quan. Khi phát triển tích hợp native mới, nên đánh giá FFM trước; Region Pinning vẫn là kiến thức hữu ích để hiểu hành vi GC của ứng dụng còn sử dụng JNI.

## 5. Nội dung không đưa vào lộ trình

**String Templates — JEP 459** từng xuất hiện ở Java 22 dưới dạng preview lần thứ hai. Sau phản hồi trong quá trình preview, thiết kế này bị rút khỏi JDK 23 và không tiếp tục trong hình thức đó. Vì vậy, không nên học nó như một tính năng Java hiện đại đã được chấp nhận hoặc viết mã phụ thuộc vào cú pháp preview này.

Việc loại String Templates giúp phân biệt một ý tưởng từng được thử nghiệm với một tính năng còn được duy trì. Nếu cần nội suy chuỗi trong mã hiện tại, hãy dùng các API và cú pháp ổn định đang có trong phiên bản JDK của dự án.

## 6. Thứ tự học đề xuất

| Mức ưu tiên | Nội dung | Lý do |
| --- | --- | --- |
| 1 | Unnamed Variables & Patterns | Dễ áp dụng trong mã Java hằng ngày, cú pháp đã final từ Java 22 |
| 2 | Stream Gatherers | Mở rộng cách xử lý Stream; API final từ Java 24 |
| 3 | Scoped Values | Hữu ích cho dữ liệu ngữ cảnh, đặc biệt trong ứng dụng dùng virtual threads; final từ Java 25 |
| 4 | Flexible Constructor Bodies | Làm constructor rõ ràng hơn khi cần xác thực dữ liệu; final từ Java 25 |
| 5 | Compact Source Files & Instance Main Methods và source-file launcher | Hữu ích cho học tập, ví dụ và tiện ích nhỏ; tính năng compact source final từ Java 25 |
| 6 | Foreign Function & Memory API | Học khi có nhu cầu tích hợp native hoặc quản lý bộ nhớ ngoài heap |
| 7 | Class-File API | Học khi làm compiler, framework, bytecode tool hoặc instrumentation |
| 8 | G1 Region Pinning | Hiểu khi phân tích GC và ứng dụng có JNI |
| 9 | Structured Concurrency và Vector API | Tìm hiểu chuyên sâu; cần theo dõi trạng thái preview/incubator và đo kiểm trước khi áp dụng |

## 7. Chọn JDK theo trạng thái tính năng

Không phải tất cả ví dụ trong bài đều chạy ổn định trên Java 22. Nếu dự án cần dùng các tính năng đã final, hãy chọn phiên bản JDK tối thiểu tương ứng:

| Mốc phiên bản | Tính năng và trạng thái |
| --- | --- |
| Java 22 | Unnamed Variables & Patterns, FFM API, Multi-File Source-Code Launcher, G1 Region Pinning |
| Java 24 | Stream Gatherers, Class-File API |
| Java 25 | Scoped Values, Flexible Constructor Bodies, Compact Source Files & Instance Main Methods |
| Java 27 | Structured Concurrency vẫn preview; Vector API vẫn incubator, không phải API final |

Khi một tính năng còn preview, cần bật preview cả lúc biên dịch và chạy, đồng thời dùng đúng phiên bản JDK:

```bash
javac --enable-preview --release 27 Main.java
java --enable-preview Main
```

Với incubator module như Vector API, dùng `--add-modules` theo hướng dẫn của module thay vì coi đó là preview language feature. Không trộn hai cơ chế này.

## 8. Tài liệu tham khảo

- [Java 22 Language Changes](https://docs.oracle.com/en/java/javase/22/language/java-language-changes.html)
- [Significant Changes in JDK 22](https://docs.oracle.com/en/java/javase/22/migrate/significant-changes-jdk-release.html)
- [Foreign Function and Memory API trong Java 22](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html)
- [Java Language Changes by Release — Java 25](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html)
- [Significant Changes in JDK 25](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [JEP 423 — Region Pinning for G1](https://openjdk.org/jeps/423)
- [JEP 447 — Statements before super(...)](https://openjdk.org/jeps/447)
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [JEP 456 — Unnamed Variables & Patterns](https://openjdk.org/jeps/456)
- [JEP 457 — Class-File API (Preview in Java 22)](https://openjdk.org/jeps/457)
- [JEP 458 — Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458)
- [JEP 459 — String Templates (Withdrawn)](https://openjdk.org/jeps/459)
- [JEP 460 — Vector API (Seventh Incubator)](https://openjdk.org/jeps/460)
- [JEP 461 — Stream Gatherers (Preview in Java 22)](https://openjdk.org/jeps/461)
- [JEP 462 — Structured Concurrency (Second Preview)](https://openjdk.org/jeps/462)
- [JEP 463 — Implicitly Declared Classes and Instance Main Methods (Second Preview)](https://openjdk.org/jeps/463)
- [JEP 464 — Scoped Values (Second Preview)](https://openjdk.org/jeps/464)
- [JEP 484 — Class-File API](https://openjdk.org/jeps/484)
- [JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485)
- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506)
- [JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512)
- [JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513)
- [JEP 533 — Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533)
- [JEP 537 — Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537)
