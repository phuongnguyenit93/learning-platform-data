# Phân biệt tính năng chính thức, preview và mô-đun incubator

Java 22 giới thiệu nhiều thay đổi có mức độ trưởng thành khác nhau. Một số tính năng đã trở thành phần ổn định của Java ngay trong JDK 22; một số khác chỉ được phát hành để lấy phản hồi qua cơ chế *preview* hoặc *incubator*. Trạng thái ở thời điểm ra mắt không nhất thiết là trạng thái hiện tại: nhiều tính năng preview của Java 22 đã được hoàn thiện trong các JDK sau đó.

Bài này phân biệt ba trạng thái trên, phân loại các JEP của Java 22 và theo dõi vòng đời của chúng đến JDK 27 (tháng 11 năm 2026). Mục tiêu là giúp chọn đúng API và cú pháp còn được hỗ trợ trong Java hiện đại, đồng thời nhận ra những thử nghiệm đã bị rút lại.

## 1. JEP và trạng thái phát hành có ý nghĩa gì?

JEP (*JDK Enhancement Proposal*) là mã đề xuất dùng để mô tả, thảo luận và theo dõi một thay đổi trong JDK. Số JEP không tự cho biết tính năng đã ổn định hay chưa. Cần đọc trạng thái phát hành đi kèm tên JEP:

| Trạng thái | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| Chính thức (*permanent/final*) | Tính năng đã được hoàn thiện và đưa vào nền tảng Java hoặc JDK như một phần ổn định. | Có thể sử dụng trong ứng dụng thông thường theo tài liệu của phiên bản JDK đang chạy. |
| Preview | Bản xem trước của cú pháp ngôn ngữ, API hoặc tính năng VM. Thiết kế có thể thay đổi hoặc bị rút lại sau khi nhận phản hồi. | Chỉ thử nghiệm khi đã bật preview; không xem hợp đồng API là ổn định giữa các phiên bản JDK. |
| Incubator | API thử nghiệm được cung cấp qua một mô-đun incubator riêng. API có thể thay đổi hoặc bị loại bỏ khi nhóm phát triển tiếp tục hoàn thiện thiết kế. | Phải chủ động thêm mô-đun vào ứng dụng; chỉ phụ thuộc khi chấp nhận được thay đổi giữa các bản JDK. |

Preview và incubator đều phục vụ thử nghiệm, nhưng cơ chế phát hành khác nhau. Preview có thể áp dụng cho cú pháp Java hoặc API; incubator thường cung cấp API trong mô-đun riêng để người dùng thử nghiệm thiết kế thư viện.

## 2. Cách bật và nhận biết Preview, Incubator

### Preview

Để biên dịch và chạy mã dùng preview feature của JDK 22, bật preview ở cả hai bước:

```bash
javac --release 22 --enable-preview Example.java
java --enable-preview Example
```

Preview gắn với một phiên bản JDK cụ thể. Mã biên dịch bằng preview của JDK 22 cần được chạy trên JDK 22 có bật preview. Khi tính năng tiếp tục thay đổi ở JDK 23, 24 hoặc phiên bản khác, cần đọc tài liệu của phiên bản đó và biên dịch lại bằng đúng JDK tương ứng. Không nên lấy class file dùng preview của JDK 22 rồi kỳ vọng chạy được trên JDK 27.

Ví dụ, nếu đang thử một preview feature hiện tại của JDK 27, dùng compiler và runtime JDK 27:

```bash
javac --release 27 --enable-preview Example.java
java --enable-preview Example
```

Khi một preview feature được hoàn thiện, mã nguồn thường có thể dùng phiên bản chính thức mà không cần `--enable-preview`. Tuy nhiên, cần kiểm tra thay đổi cú pháp hoặc API giữa bản preview cuối cùng và bản chính thức.

### Incubator

API incubator thường nằm trong một mô-đun có tên bắt đầu bằng `jdk.incubator`. Ví dụ, Vector API thuộc mô-đun `jdk.incubator.vector`. Với JDK 27, cần thêm mô-đun khi biên dịch và chạy:

```bash
javac --add-modules jdk.incubator.vector VectorDemo.java
java --add-modules jdk.incubator.vector VectorDemo
```

`--add-modules` giải quyết việc đưa mô-đun incubator vào đồ thị mô-đun của ứng dụng. Nó không thay thế `--enable-preview`; hai cờ phục vụ hai cơ chế khác nhau. API incubator có thể thay đổi giữa các bản JDK, vì vậy cần kiểm tra tài liệu của đúng phiên bản đang dùng.

## 3. Phân loại các JEP được đưa vào Java 22

Java 22 có 12 JEP nổi bật trong bộ tính năng phát hành. Bảng dưới đây ghi trạng thái lúc Java 22 ra mắt và tình trạng tiếp nối đến JDK 27.

| JEP | Tính năng trong Java 22 | Trạng thái ở Java 22 | Tình trạng đến JDK 27 |
| --- | --- | --- | --- |
| [423](https://openjdk.org/jeps/423) | Region Pinning for G1 | Chính thức; cải tiến runtime/GC | Vẫn là tối ưu hóa của G1, không phải API Java mới. |
| [447](https://openjdk.org/jeps/447) | Statements before `super(...)` | Preview | Đã chính thức hóa thành Flexible Constructor Bodies trong JDK 25 (JEP 513). |
| [454](https://openjdk.org/jeps/454) | Foreign Function & Memory API | Chính thức | API chuẩn từ Java 22 và tiếp tục được duy trì. |
| [456](https://openjdk.org/jeps/456) | Unnamed Variables & Patterns | Chính thức | Tính năng ngôn ngữ chính thức từ Java 22. |
| [457](https://openjdk.org/jeps/457) | Class-File API | Preview | Đã chính thức hóa trong JDK 24 (JEP 484). |
| [458](https://openjdk.org/jeps/458) | Launch Multi-File Source-Code Programs | Chính thức | Chế độ chạy chương trình từ nhiều file nguồn vẫn được hỗ trợ. |
| [459](https://openjdk.org/jeps/459) | String Templates (Second Preview) | Preview | Đã bị rút lại sau Java 22; không phải tính năng chuẩn trong các JDK hiện đại. |
| [460](https://openjdk.org/jeps/460) | Vector API (Seventh Incubator) | Incubator | Vẫn là incubator ở JDK 27, lần thứ 12 (JEP 537). |
| [461](https://openjdk.org/jeps/461) | Stream Gatherers | Preview | Đã chính thức hóa trong JDK 24 (JEP 485). |
| [462](https://openjdk.org/jeps/462) | Structured Concurrency (Second Preview) | Preview | Vẫn là preview ở JDK 27, lần thứ 7 (JEP 533). |
| [463](https://openjdk.org/jeps/463) | Implicitly Declared Classes and Instance Main Methods (Second Preview) | Preview | Đã chính thức hóa trong JDK 25 với tên Compact Source Files and Instance Main Methods (JEP 512). |
| [464](https://openjdk.org/jeps/464) | Scoped Values (Second Preview) | Preview | Đã chính thức hóa trong JDK 25 (JEP 506). |

Có bốn JEP được phát hành ở trạng thái chính thức ngay trong Java 22: JEP 423, 454, 456 và 458. Bảy JEP ở trạng thái preview và một JEP ở trạng thái incubator. Trong nhóm preview, phần lớn đã được hoàn thiện sau Java 22; Structured Concurrency vẫn đang thử nghiệm, còn String Templates đã bị rút lại.

## 4. Những tính năng Java 22 đã trở thành chính thức và còn hữu ích

### Foreign Function & Memory API — JEP 454

FFM API cho phép Java gọi hàm native và truy cập vùng nhớ bên ngoài JVM thông qua package `java.lang.foreign`. API này cung cấp cách tích hợp thư viện C mà không cần tự viết lớp JNI cho từng lời gọi. Đây là API chính thức ngay từ Java 22.

Các thành phần thường gặp gồm `Linker`, `SymbolLookup`, `FunctionDescriptor`, `MemorySegment` và `Arena`. Khi làm việc với API này, cần mô tả đúng ABI và chữ ký C, đồng thời quản lý chính xác vòng đời của vùng nhớ native.

### Unnamed Variables & Patterns — JEP 456

Ký tự `_` biểu thị một biến hoặc thành phần pattern được cố ý bỏ qua vì chương trình không cần sử dụng giá trị đó. Điều này giúp thể hiện rõ ý định và tránh đặt tên cho biến không dùng đến.

```java
try {
    readFile();
} catch (java.io.IOException _) {
    // Chỉ cần xử lý lỗi, không cần tham chiếu đối tượng exception.
    reportFailure();
}
```

Đây là tính năng ngôn ngữ chính thức từ Java 22, không cần bật preview. Không thể dùng `_` như tên biến thông thường để đọc giá trị.

### Launch Multi-File Source-Code Programs — JEP 458

Trình khởi chạy Java có thể chạy chương trình ở chế độ source-file với nhiều file mã nguồn. Điều này hữu ích cho script hoặc công cụ nhỏ cần tách một phần triển khai sang file khác mà không yêu cầu người dùng tự gọi `javac` trước.

```bash
java Main.java
```

Trong chế độ source-file, `Main.java` có thể tham chiếu các lớp nguồn khác được tìm thấy theo source path. Tính năng này thuộc trình khởi chạy JDK, không phải cú pháp mới trong thân chương trình Java.

### Region Pinning for G1 — JEP 423

Đây là cải tiến của Garbage-First Garbage Collector (G1). Region pinning giúp G1 xử lý các vùng nhớ bị ghim trong JNI critical regions mà không phải tạm dừng toàn bộ hoạt động thu gom rác theo cách cũ, qua đó giảm độ trễ trong trường hợp liên quan.

JEP này không thêm API hoặc cú pháp Java để lập trình viên gọi trực tiếp. Nó hữu ích khi tìm hiểu hiệu năng G1 và tương tác giữa garbage collector với mã JNI. Đây là cải tiến runtime; không nên nhầm nó với FFM API ở JEP 454.

## 5. Preview của Java 22 đã được hoàn thiện

Các tính năng dưới đây xuất hiện dưới dạng preview trong Java 22 nhưng đã có phiên bản chính thức ở JDK mới hơn. Khi viết mã mới, hãy dùng API hoặc cú pháp chính thức của JDK mục tiêu thay vì sao chép ví dụ preview cũ.

### Stream Gatherers — JEP 461, chính thức từ JDK 24

Stream Gatherers mở rộng Stream API bằng các phép biến đổi trung gian do lập trình viên định nghĩa hoặc sử dụng từ thư viện. Tính năng này hữu ích khi pipeline cần gom nhóm, tạo cửa sổ dữ liệu hoặc thực hiện một phép biến đổi không thuận tiện với các intermediate operation có sẵn.

Ví dụ với gatherer có sẵn để gom các phần tử thành cửa sổ cố định:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class WindowExample {
    public static void main(String[] args) {
        List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5, 6)
                .gather(Gatherers.windowFixed(3))
                .toList();

        System.out.println(windows);
    }
}
```

Kết quả gồm các cửa sổ `[1, 2, 3]` và `[4, 5, 6]`. `Gatherers` và `Stream.gather(...)` là API chuẩn từ JDK 24; không cần `--enable-preview` khi dùng phiên bản chính thức.

### Class-File API — JEP 457, chính thức từ JDK 24

Class-File API cung cấp API chuẩn để đọc, tạo và biến đổi Java class file theo định dạng class file của JVM. API này hữu ích cho công cụ phân tích bytecode, framework, thư viện sinh mã, công cụ kiểm tra và xử lý class file.

Trong Java 22, API còn ở preview. Từ JDK 24, API chính thức được đưa vào package `java.lang.classfile` theo JEP 484. Khi phát triển công cụ bytecode trên JDK hiện đại, ưu tiên API chuẩn này và tài liệu đúng phiên bản thay vì phụ thuộc vào API preview Java 22 hoặc tự xử lý định dạng class file bằng các giả định cũ.

### Flexible Constructor Bodies — JEP 447, chính thức từ JDK 25

JEP 447 ban đầu cho phép đặt một số câu lệnh trước lời gọi `super(...)` trong constructor. Sau các vòng preview, tính năng được hoàn thiện với tên Flexible Constructor Bodies ở JDK 25 (JEP 513).

Các câu lệnh mở đầu constructor có thể kiểm tra tham số hoặc thực hiện phép tính an toàn trước khi gọi constructor của lớp cha. Chúng không được tùy ý truy cập đối tượng đang được khởi tạo; các giới hạn này giúp tránh việc mã của lớp cha gọi phương thức ghi đè và quan sát trạng thái chưa khởi tạo của lớp con.

```java
class Account extends BaseAccount {
    Account(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id không được để trống");
        }
        super(id);
    }
}
```

Ví dụ minh họa việc xác thực tham số trước khi gọi constructor lớp cha. Đây là cú pháp chính thức từ JDK 25; mã Java 22 cần bật preview mới có thể thử cú pháp tương ứng.

### Compact Source Files and Instance Main Methods — JEP 463, chính thức từ JDK 25

JEP 463 tiếp tục phát triển ý tưởng viết chương trình Java nhỏ với ít cấu trúc khai báo hơn. Tính năng được hoàn thiện trong JDK 25 với tên Compact Source Files and Instance Main Methods (JEP 512).

Một file nguồn đơn giản có thể bỏ khai báo lớp bao ngoài và dùng instance `main`:

```java
void main() {
    IO.println("Hello, Java!");
}
```

Tính năng này hữu ích cho ví dụ học tập, script và chương trình dòng lệnh nhỏ. Ứng dụng lớn vẫn có thể dùng lớp, package, module và cấu trúc thông thường. Đây là lựa chọn cú pháp bổ sung, không thay thế cách khai báo `public static void main(String[] args)` quen thuộc.

### Scoped Values — JEP 464, chính thức từ JDK 25

Scoped Values cung cấp cách chia sẻ dữ liệu bất biến trong phạm vi một luồng thực thi và các tác vụ con. Chúng đặc biệt hữu ích khi truyền ngữ cảnh như người dùng hiện tại hoặc thông tin yêu cầu qua nhiều lời gọi phương thức, nhất là trong ứng dụng dùng virtual threads.

```java
import java.lang.ScopedValue;

public class RequestContext {
    private static final ScopedValue<String> CURRENT_USER =
            ScopedValue.newInstance();

    static void handleRequest() {
        ScopedValue.where(CURRENT_USER, "alice").run(() -> service());
    }

    static void service() {
        System.out.println(CURRENT_USER.get());
    }
}
```

Scoped Values ở trạng thái preview trong Java 22 và trở thành API chính thức trong JDK 25 (JEP 506). Với mã mới trên JDK 25 trở lên, có thể cân nhắc Scoped Values cho dữ liệu ngữ cảnh bất biến theo phạm vi; `ThreadLocal` vẫn có trường hợp sử dụng riêng và không cần thay thế máy móc.

## 6. Những thử nghiệm vẫn chưa ổn định hoặc đã bị rút lại

### Structured Concurrency — JEP 462

Structured Concurrency tổ chức một nhóm tác vụ chạy đồng thời thành một đơn vị công việc có phạm vi rõ ràng. Cách tiếp cận này giúp phối hợp kết quả, xử lý lỗi và hủy tác vụ liên quan một cách nhất quán.

Tính năng ở preview lần thứ hai trong Java 22 và vẫn ở preview lần thứ bảy trong JDK 27 (JEP 533). API đã trải qua nhiều thay đổi qua các vòng preview. Có thể nghiên cứu ý tưởng và thử nghiệm bằng đúng JDK tương ứng, nhưng không nên coi mã preview Java 22 là API hiện hành hoặc đặt phụ thuộc sản phẩm dài hạn vào hợp đồng chưa ổn định.

### Vector API — JEP 460

Vector API biểu diễn phép tính trên nhiều phần tử cùng lúc để JVM có thể ánh xạ phép tính sang chỉ thị vector phù hợp của CPU. Nó hướng đến các tác vụ tính toán như xử lý số học, ảnh, âm thanh hoặc một số workload khoa học.

API này ở incubator lần thứ bảy trong Java 22 và vẫn là incubator lần thứ mười hai trong JDK 27 (JEP 537). Mô-đun vẫn mang tên `jdk.incubator.vector`. Chỉ nên thử nghiệm hoặc sử dụng trong phạm vi chấp nhận được việc cập nhật mã khi API thay đổi; không xem đây là API chuẩn ổn định của Java SE.

### String Templates — JEP 459

String Templates xuất hiện dưới dạng preview lần thứ hai trong Java 22. Sau phản hồi và thảo luận về thiết kế, nhóm phát triển đã rút lại tính năng trước khi đưa vào JDK 23. Vì vậy, cú pháp preview của String Templates không phải một phần của Java hiện đại và không nên dùng trong mã nguồn mới.

Đây là ví dụ rõ ràng cho lý do cần phân biệt preview với tính năng chính thức: một tính năng preview có thể được hoàn thiện, tiếp tục thử nghiệm nhiều lần hoặc bị rút lại.

## 7. Lộ trình học và lựa chọn khi phát triển ứng dụng

Khi học các thay đổi xuất phát từ Java 22, nên ưu tiên những nội dung đã có API hoặc cú pháp chính thức trong JDK hiện đại:

1. **Học và sử dụng trực tiếp:** FFM API, Unnamed Variables & Patterns và Launch Multi-File Source-Code Programs. Đây là các tính năng chính thức từ Java 22.
2. **Học theo phiên bản đã hoàn thiện:** Stream Gatherers và Class-File API từ JDK 24; Flexible Constructor Bodies, Scoped Values và Compact Source Files and Instance Main Methods từ JDK 25.
3. **Theo dõi khi có nhu cầu chuyên biệt:** Structured Concurrency vẫn preview và Vector API vẫn incubator trong JDK 27. Chỉ thử nghiệm với đúng phiên bản JDK, kiểm tra lại API trước mỗi lần nâng cấp.
4. **Không đưa vào mã mới:** String Templates của JEP 459 đã bị rút lại. Region Pinning là tối ưu hóa nội bộ của G1, nên chỉ cần hiểu tác động runtime khi làm việc với GC/JNI, không tìm cách gọi nó như một API.

Khi chọn JDK cho dự án, hãy căn cứ vào phiên bản mà môi trường triển khai hỗ trợ và trạng thái chính thức của API trong phiên bản đó. Một tính năng từng xuất hiện trong Java 22 không có nghĩa là nó vẫn đang preview hoặc incubator; ngược lại, một API từng được giới thiệu lâu năm vẫn có thể chưa trở thành chính thức.

## 8. Tài liệu tham khảo

- [JDK 22 Release Notes](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html) — danh sách tính năng và trạng thái khi Java 22 phát hành.
- [Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html) — lịch sử preview và các tính năng ngôn ngữ đã trở thành chính thức hoặc bị rút lại.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — trạng thái hiện tại của Structured Concurrency và Vector API.
- [JEP Index](https://openjdk.org/jeps/0) — tra cứu đề xuất và tiến trình của từng JEP.

Trạng thái trong bài được đối chiếu đến JDK 27, bản phát hành tháng 9 năm 2026 và bản cập nhật 27.0.1.1 tháng 11 năm 2026. Khi đọc bài ở thời điểm sau đó, hãy kiểm tra lại release notes của JDK đang dùng, đặc biệt với các tính năng preview và incubator.
