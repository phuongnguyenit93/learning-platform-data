# Những cải tiến từ Java 14 còn được sử dụng trong Java hiện đại

Java 14 (phát hành tháng 3/2020) là một mốc quan trọng trong quá trình hiện đại hóa Java. Một số tính năng trở thành chính thức ngay ở Java 14; một số khác mới ở giai đoạn *preview* hoặc *incubator*, rồi được hoàn thiện trong các phiên bản sau. Bài này chỉ trình bày **cách dùng và API còn có giá trị trong Java hiện đại**, không hướng dẫn sử dụng các API thử nghiệm cũ, thành phần đã bị loại bỏ hoặc cờ JVM đã lỗi thời.

**Môi trường thực hành:** Dùng JDK 17 trở lên cho các ví dụ về ngôn ngữ, chẩn đoán, JFR và `jpackage`; riêng ví dụ Foreign Function & Memory (FFM) dùng JDK 22 trở lên. Kiểm tra bằng `java -version` và `javac -version`. Cú pháp ổn định được dùng trực tiếp, không cần `--enable-preview`.

## 1. Bản đồ các cải tiến còn hữu ích

| Cải tiến | Mốc tại Java 14 | Trạng thái/cách sử dụng hiện đại | Giá trị thực tế |
| --- | --- | --- | --- |
| Switch expressions — JEP 361 | Trở thành tính năng chính thức (đã preview ở 12/13) | Dùng trực tiếp từ Java 14 | Trả về giá trị từ `switch`, ít lỗi `fall-through` |
| Records — JEP 359 → 395 | Preview lần đầu ở Java 14 | Chính thức từ Java 16 | Kiểu dữ liệu gọn cho DTO, kết quả và value object |
| Pattern matching for `instanceof` — JEP 305 → 394 | Preview lần đầu ở Java 14 | Chính thức từ Java 16 | Kiểm tra kiểu và tạo biến cùng một biểu thức |
| Text blocks — JEP 368 → 378 | Preview lần hai ở Java 14 (xuất hiện từ 13) | Chính thức từ Java 15 | Viết SQL, JSON và văn bản nhiều dòng dễ đọc |
| Helpful NullPointerExceptions — JEP 358 | Bổ sung chẩn đoán `null` tại Java 14 | Các JDK hiện đại bật mặc định trong cấu hình thông thường | Xác định cụ thể tham chiếu nào là `null` |
| JFR Event Streaming — JEP 349 | API tiêu thụ sự kiện JFR theo luồng xuất hiện ở Java 14 | `jdk.jfr.consumer.RecordingStream` vẫn được hỗ trợ | Theo dõi JVM đang chạy, phân tích hiệu năng |
| `jpackage` — JEP 343 → 392 | Công cụ ở giai đoạn incubator trong Java 14 | Công cụ chính thức từ Java 16 | Tạo application image/installer có kèm Java runtime |
| G1 NUMA awareness — JEP 345 | Nâng cấp cách cấp phát bộ nhớ trên máy NUMA | Tối ưu JVM còn hữu ích trong môi trường phù hợp | Có thể cải thiện locality, cần benchmark |
| ZGC trên macOS/Windows — JEP 364/365 | Mở rộng nền tảng hỗ trợ ZGC | ZGC tiếp tục được phát triển và hỗ trợ trên các nền tảng phù hợp | Lựa chọn GC khi đặc biệt quan tâm độ trễ |
| NVM mapped byte buffers — JEP 352 | Thêm chế độ ánh xạ bộ nhớ không mất dữ liệu khi mất điện | `jdk.nio.mapmode.ExtendedMapMode` vẫn có trong JDK hiện đại | Trường hợp chuyên biệt có phần cứng/bộ nhớ NVM |
| Foreign-Memory Access — JEP 370 → 454 | Khởi đầu là API incubator ở Java 14 | Được thiết kế lại, chính thức thành FFM API từ Java 22 | Làm việc với bộ nhớ ngoài heap và mã native |

Điểm cần nhớ: **“có ở Java 14” không đồng nghĩa với “đã chính thức ở Java 14”**. Ví dụ, mã `record` và pattern `instanceof` trong bài chạy bằng cú pháp chính thức của Java 16+, trong khi text block dùng cú pháp chính thức của Java 15+.

## 2. Switch expressions: viết logic phân nhánh có kết quả

Trước đây, lập trình viên thường khai báo biến, gán trong từng nhánh `case` rồi phải nhớ `break`. Từ Java 14, `switch` có thể là một **biểu thức trả về giá trị**. Dạng `case ... ->` không tự động chạy xuyên sang nhánh kế tiếp; nhánh có nhiều lệnh dùng khối `{ ... }` và `yield` để trả về kết quả.

**Tệp `SwitchDemo.java` (Java 17+):**

```java
public class SwitchDemo {
    static String delivery(int days) {
        return switch (days) {
            case 0 -> "Hỏa tốc";
            case 1, 2 -> "Nhanh";
            default -> {
                if (days < 0) {
                    yield "Không hợp lệ";
                }
                yield "Tiêu chuẩn";
            }
        };
    }

    public static void main(String[] args) {
        System.out.println(delivery(2));
        System.out.println(delivery(4));
        System.out.println(delivery(-1));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SwitchDemo.java
java SwitchDemo
```

Kết quả:

```text
Nhanh
Tiêu chuẩn
Không hợp lệ
```

**Cơ chế và quy tắc:**

- `return switch (...) { ... };` nhận giá trị của nhánh được chọn; `yield` kết thúc nhánh biểu thức và trả về giá trị, còn `return` sẽ thoát khỏi phương thức.
- Các nhánh dạng mũi tên không có `fall-through`. Dạng `case X:` truyền thống vẫn tồn tại nhưng cần chú ý `break`; không trộn hai dạng nhãn trong cùng một khối `switch`.
- Một `switch` **biểu thức** phải bao phủ mọi giá trị có thể có, thường bằng `default`. Với enum, khi đã liệt kê đầy đủ các hằng có thể không cần `default`.
- Java 14 không giới thiệu pattern matching trong `switch`. Các khả năng như `case null` hoặc type patterns trong `switch` thuộc các phiên bản mới hơn; đừng gộp chúng vào lịch sử của JEP 361.

**Khi nên dùng:** ánh xạ trạng thái sang nhãn, chọn quy tắc, chuyển mã loại sang giá trị. Với xử lý quá dài hoặc có nhiều tác dụng phụ, tách logic thành phương thức riêng sẽ dễ đọc hơn.

## 3. Records: khai báo kiểu dữ liệu mang giá trị

`record` được thử nghiệm lần đầu ở Java 14 và trở thành tính năng chuẩn ở **Java 16**. Nó tạo một lớp có các thành phần dữ liệu (*record components*), constructor, accessor, `equals`, `hashCode` và `toString` phù hợp cho mục đích biểu diễn dữ liệu. Accessor mang tên thành phần, chẳng hạn `sku()`, không phải mặc định là `getSku()`.

**Tệp `RecordDemo.java` (Java 17+):**

```java
record Product(String sku, int quantity) {
    Product {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("Quantity must be nonnegative");
        }
    }
}

public class RecordDemo {
    public static void main(String[] args) {
        Product p = new Product("P-01", 3);
        System.out.println(p.sku());
        System.out.println(p.quantity());
        System.out.println(p);
        System.out.println(p.equals(new Product("P-01", 3)));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 RecordDemo.java
java RecordDemo
```

Kết quả:

```text
P-01
3
Product[sku=P-01, quantity=3]
true
```

Trong *compact canonical constructor* `Product { ... }`, ta kiểm tra dữ liệu đầu vào; trình biên dịch đảm nhiệm việc gán các thành phần sau phần thân constructor. Record có thể có phương thức và thực thi interface; bản thân kiểu record là `final` và không thể kế thừa từ lớp tùy ý.

**Giới hạn quan trọng: “shallowly immutable”, không phải bất biến sâu.** Các trường thành phần là `private final`, nhưng nếu một thành phần trỏ tới `List` hoặc mảng có thể sửa, đối tượng được trỏ tới vẫn có thể thay đổi. Nếu cần bất biến sâu, tạo bản sao phòng vệ, ví dụ `List.copyOf(items)`, và cân nhắc các phần tử bên trong. Record thích hợp cho DTO, dữ liệu trả về, khóa có ngữ nghĩa giá trị; không tự động thay thế mọi entity có vòng đời và trạng thái thay đổi.

## 4. Pattern matching for instanceof: kiểm tra kiểu và dùng biến an toàn

Java 14 giới thiệu dạng `instanceof` có *type pattern* ở preview; từ **Java 16** có thể dùng chính thức. Nó gộp phép kiểm tra kiểu và phép ép kiểu, tránh đoạn mã lặp `if (o instanceof String) { String s = (String) o; ... }`.

**Tệp `PatternDemo.java` (Java 17+):**

```java
public class PatternDemo {
    static String readable(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return text.trim();
        }
        return "không hợp lệ";
    }

    public static void main(String[] args) {
        System.out.println(readable("  Java  "));
        System.out.println(readable(123));
        System.out.println(readable(null));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PatternDemo.java
java PatternDemo
```

Kết quả:

```text
Java
không hợp lệ
không hợp lệ
```

Biến `text` chỉ có hiệu lực ở vị trí mà trình biên dịch đã chứng minh phép kiểm tra kiểu thành công (*flow scoping*). Dùng `&&` như trên là hợp lệ vì toán hạng bên phải chỉ được xét khi biểu thức bên trái đúng. Không thể tùy tiện thay bằng `||` rồi tham chiếu `text` ở vế phải. `null instanceof String` luôn là `false`, nên ví dụ không ném `NullPointerException`.

**Khi nên dùng:** kiểm tra dữ liệu từ API tổng quát, phân loại object hoặc xử lý polymorphism đơn giản. Với hệ phân cấp kiểu phức tạp, cân nhắc thiết kế interface/sealed class và những khả năng pattern matching của Java mới hơn, thay vì xếp nhiều `if` khó bảo trì.

## 5. Text blocks: chuỗi nhiều dòng vẫn giữ được tính dễ đọc

Text blocks xuất hiện ở preview Java 13, được cải tiến trong preview Java 14 và chính thức ở **Java 15**. Ba dấu nháy kép `"""` tạo literal nhiều dòng; nội dung bắt đầu ở dòng sau dấu mở. Trình biên dịch xử lý phần thụt lề chung để mã nguồn có thể căn lề đẹp mà chuỗi kết quả vẫn đúng.

**Tệp `TextBlockDemo.java` (Java 17+):**

```java
public class TextBlockDemo {
    public static void main(String[] args) {
        String sql = """
                SELECT id, name
                FROM users
                WHERE active = true
                """;
        System.out.print(sql);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TextBlockDemo.java
java TextBlockDemo
```

Kết quả (có ký tự xuống dòng sau dòng cuối):

```text
SELECT id, name
FROM users
WHERE active = true
```

Text block hữu ích cho truy vấn SQL tĩnh, JSON mẫu, HTML và thông báo nhiều dòng. Nó **không** tự động escape dữ liệu đầu vào hoặc ngăn SQL injection: với tham số từ người dùng, vẫn dùng `PreparedStatement` và placeholder `?`. Chú ý khoảng trắng đầu/cuối và ký tự xuống dòng cuối; nếu so sánh chuỗi hoặc ký dữ liệu, hãy xác minh chính xác giá trị thu được. Từ phiên bản chính thức, có thể dùng các escape như `\s` để thể hiện dấu cách một cách tường minh khi thật sự cần.

## 6. Helpful NullPointerExceptions: chẩn đoán đúng mắt xích null

JEP 358 bổ sung từ Java 14 khả năng phân tích bytecode khi JVM tự ném `NullPointerException`, nhằm mô tả rõ thao tác thất bại và tham chiếu nào đang là `null`. Tùy chọn `-XX:+ShowCodeDetailsInExceptionMessages` được bật mặc định trong các JDK hiện đại thông thường (Java 14 lúc ra mắt chưa bật mặc định).

**Tệp `NullDemo.java` (Java 17+):**

```java
public class NullDemo {
    static class Address {
        String city;
    }

    static class Customer {
        Address address;
    }

    public static void main(String[] args) {
        Customer customer = new Customer();
        System.out.println(customer.address.city.length());
    }
}
```

```bash
javac -g -encoding UTF-8 NullDemo.java
java NullDemo
```

Chương trình cố ý kết thúc bằng `NullPointerException` vì `customer.address` chưa được gán. Thông báo của JVM hiện đại thường chỉ ra không thể truy cập `city` do `address` là `null`. **Không coi chuỗi stack trace cụ thể là output cố định**: tên biến hiển thị và vị trí dòng phụ thuộc bytecode, thông tin debug và bản JDK.

Lưu ý:

- Chỉ hỗ trợ diễn giải những trường hợp JVM có đủ thông tin để phân tích; một `new NullPointerException("...")` do ứng dụng tự tạo không được JVM tự viết lại thành mô tả chuỗi dereference.
- Tính năng giúp tìm nguyên nhân, **không thay thế** kiểm tra hợp lệ, `Objects.requireNonNull`, thiết kế API rõ ràng hoặc xử lý lỗi đúng chỗ.
- Khi ghi log, xem xét liệu thông báo lỗi và stack trace có chứa chi tiết nội bộ không nên xuất hiện ở phản hồi gửi người dùng cuối.

## 7. JFR Event Streaming: giám sát ứng dụng đang chạy

JDK Flight Recorder (JFR) có từ trước Java 14, nhưng **JEP 349 tại Java 14** bổ sung khả năng tiêu thụ sự kiện theo luồng qua `jdk.jfr.consumer`. `RecordingStream` có thể bật những loại sự kiện mong muốn, đăng ký callback và chạy bất đồng bộ; dữ liệu hữu ích cho quan sát GC, CPU, phân bổ bộ nhớ và hành vi thực tế của JVM.

**Tệp `JfrStreamDemo.java` (Java 17+):**

```java
import java.time.Duration;
import jdk.jfr.consumer.RecordingStream;

public class JfrStreamDemo {
    public static void main(String[] args) throws InterruptedException {
        try (RecordingStream stream = new RecordingStream()) {
            stream.enable("jdk.CPULoad")
                  .withPeriod(Duration.ofSeconds(1));
            stream.onEvent("jdk.CPULoad", event -> {
                double userCpu = event.getFloat("jvmUser") * 100.0;
                System.out.printf("JVM user CPU: %.1f%%%n", userCpu);
            });

            stream.startAsync();
            Thread.sleep(3_500);
        }
    }
}
```

```bash
javac JfrStreamDemo.java
java JfrStreamDemo
```

Có thể xuất hiện một hoặc nhiều dòng như `JVM user CPU: 0.5%`, nhưng **số lượng sự kiện và phần trăm CPU không cố định**; chúng phụ thuộc môi trường chạy. `try`-with-resources đóng luồng khi kết thúc. Trong ứng dụng thực, xác định loại sự kiện, tần suất, ngưỡng, chi phí thu thập và cách dừng luồng; tránh bật toàn bộ sự kiện với cấu hình quá nặng trong production.

**Phân biệt:** JFR lưu/truyền sự kiện hiệu năng; nó không phải hệ thống logging nghiệp vụ hay công cụ thay thế toàn bộ metrics/tracing. Một `RecordingStream` có thể bổ sung chẩn đoán cho hệ giám sát hiện có.

## 8. jpackage: đóng gói ứng dụng Java để phân phối

`jpackage` lần đầu có trong JDK 14 dưới dạng công cụ incubator và trở thành công cụ chuẩn từ **JDK 16**. Nó tạo **application image** đi cùng Java runtime cần thiết; trên nền tảng phù hợp, có thể tạo installer như `msi`/`exe`, `dmg`/`pkg` hoặc `deb`/`rpm`.

Ví dụ app nhỏ; **tệp `HelloApp.java`**:

```java
public class HelloApp {
    public static void main(String[] args) {
        System.out.println("Hello from jpackage!");
    }
}
```

Dùng JDK 17+ có `jpackage`:

```bash
javac HelloApp.java
mkdir app-input
jar --create --file app-input/hello.jar --main-class HelloApp HelloApp.class
java -jar app-input/hello.jar
jpackage --type app-image --name HelloApp --input app-input --main-jar hello.jar --main-class HelloApp --dest dist
```

Lệnh `java -jar` in chính xác:

```text
Hello from jpackage!
```

Lệnh `jpackage` tạo thư mục application image bên trong `dist`; vị trí và tên launcher phụ thuộc hệ điều hành. Chạy launcher trong image để kiểm tra ứng dụng đã được đóng gói. Có thể dùng `jpackage --help` để xem kiểu gói hỗ trợ tại máy hiện tại.

**Giới hạn khi triển khai:** phải xây gói trên hệ điều hành mục tiêu (không có cơ chế cross-build tùy ý giữa Windows/macOS/Linux); installer thường cần công cụ native và quy trình ký gói phù hợp. Image có kèm runtime nên kích thước khác với JAR đơn thuần. Đây là lựa chọn tốt cho desktop/CLI cần phân phối độc lập, không bắt buộc cho mọi dịch vụ backend.

## 9. Các nâng cấp JVM và bộ nhớ dành cho tình huống chuyên biệt

### 9.1. G1 GC hiểu kiến trúc NUMA (JEP 345)

Trên máy có nhiều node **Non-Uniform Memory Access (NUMA)**, chi phí truy cập bộ nhớ phụ thuộc vị trí CPU và vùng RAM. Từ Java 14, G1 cải thiện cách phân bố/cấp phát đối tượng để tăng *memory locality*. Tùy chọn `-XX:+UseNUMA` kích hoạt heuristic liên quan trên bản JDK/hệ điều hành hỗ trợ.

Ứng dụng thực tế: máy chủ nhiều socket/NUMA chạy workload đủ lớn, có kết quả benchmark về thông lượng hoặc độ trễ. Không nên bật cờ chỉ vì bài viết đề cập nó: trên laptop, container nhỏ hay hệ không có NUMA, lợi ích có thể không đáng kể. So sánh theo cùng tải, quan sát GC logs, throughput và percentile latency.

### 9.2. ZGC được mở rộng nền tảng (JEP 364/365)

Java 14 đưa ZGC sang macOS và Windows ở trạng thái thử nghiệm lúc đó. Trong các JDK hiện đại, ZGC tiếp tục là lựa chọn thu gom rác hướng tới độ trễ thấp. Giá trị còn lại là **khả năng cân nhắc ZGC trên nhiều hệ điều hành**, song tính năng, mặc định và cờ cấu hình đã phát triển qua nhiều phiên bản. Kiểm tra tài liệu đúng **phiên bản JDK đang dùng**, tải thực tế và hỗ trợ của nhà phân phối; không tái dùng nguyên xi các cờ “experimental” thời Java 14.

### 9.3. Ánh xạ bộ nhớ không mất dữ liệu qua NVM (JEP 352)

JDK 14 bổ sung `jdk.nio.mapmode.ExtendedMapMode.READ_ONLY_SYNC` và `READ_WRITE_SYNC` để `FileChannel.map` có thể làm việc với vùng nhớ *non-volatile* trên hệ hỗ trợ. API này vẫn xuất hiện trong tài liệu JDK hiện đại, nhưng **phụ thuộc phần cứng, hệ thống tệp và hệ điều hành**. Ví dụ sau chỉ là **đoạn tích hợp**, giả sử có `FileChannel channel` phù hợp và file ánh xạ đủ lớn:

```java
import java.nio.MappedByteBuffer;
import jdk.nio.mapmode.ExtendedMapMode;

// Trong một phương thức đã mở channel với quyền đọc/ghi:
MappedByteBuffer buffer =
        channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, length);
buffer.putInt(0, 42);
buffer.force();
```

Không áp dụng đoạn này như mẹo tăng tốc phổ quát. `READ_WRITE_SYNC` có thể ném `UnsupportedOperationException` khi môi trường không hỗ trợ; việc đảm bảo dữ liệu bền vững vẫn đòi hỏi hiểu giới hạn phần cứng và giao thức ghi. Với I/O thông thường, ưu tiên `Files`, `FileChannel` hoặc công nghệ lưu trữ phù hợp nhu cầu.

### 9.4. Từ Foreign-Memory Access incubator đến FFM API chính thức

Java 14 có JEP 370, một API incubator thử nghiệm để truy cập bộ nhớ ngoài Java heap. **API thời Java 14 không còn là cách viết nên học**: chuỗi thử nghiệm sau đó được thiết kế lại và culminate ở **Foreign Function & Memory (FFM) API — JEP 454, chính thức từ Java 22**, thuộc package `java.lang.foreign`.

**Tệp `MemoryDemo.java` (yêu cầu JDK 22+):**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class MemoryDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment memory = arena.allocate(ValueLayout.JAVA_INT);
            memory.set(ValueLayout.JAVA_INT, 0, 2026);
            System.out.println(memory.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
```

```bash
javac MemoryDemo.java
java MemoryDemo
```

Kết quả:

```text
2026
```

`Arena` quản lý vòng đời của vùng nhớ và `MemorySegment` cung cấp truy cập có kiểm soát. Đây là tính năng hữu ích khi tương tác thư viện native, làm việc với bộ nhớ off-heap hoặc xử lý dữ liệu nhị phân hiệu năng cao. Mã trên chỉ cấp phát/đọc ghi vùng nhớ native; **không gọi hàm C** và không cần các thiết lập quyền truy cập native bổ sung chỉ để thực hiện ví dụ này. Khi tích hợp native linker thực sự, áp dụng quy tắc bảo mật và cấu hình của JDK hiện tại.

## 10. Chọn đúng tính năng trong dự án

| Nhu cầu | Ưu tiên |
| --- | --- |
| Hàm ánh xạ trạng thái/enum sang một giá trị | `switch` expression |
| DTO, kết quả tìm kiếm, command/query object đơn giản | `record` với validation và phòng vệ dữ liệu mutable |
| Xử lý object chưa biết kiểu | Pattern `instanceof` + kiểm tra hợp lệ |
| Chuỗi SQL/JSON/HTML mẫu nhiều dòng | Text block; SQL có dữ liệu ngoài vẫn parameterized |
| Xác định nguồn `NullPointerException` | Chẩn đoán JVM + stack trace; sửa invariant/validation |
| Điều tra CPU, GC, latency trong JVM | JFR streaming và công cụ quan sát phù hợp |
| Phân phối app desktop/CLI cho người không cài JDK | `jpackage` |
| Tối ưu trên máy NUMA hoặc yêu cầu GC latency đặc thù | Benchmark G1/NUMA, cân nhắc ZGC |
| Phần cứng NVM hoặc truy cập bộ nhớ/native hiệu năng cao | `ExtendedMapMode` hoặc FFM theo đúng nhu cầu và nền tảng |

### Lỗi phổ biến cần tránh

1. **Nhầm preview với tính năng chuẩn:** record và `instanceof` patterns chỉ ổn định ở Java 16; text block ở Java 15. Hãy biên dịch bằng JDK tương ứng, đừng dựa vào cú pháp preview Java 14.
2. **Viết `switch` thiếu nhánh:** `switch` expression phải bao phủ giá trị hợp lệ; khối có nhiều câu lệnh dùng `yield`, không dùng `break value` từ cú pháp thử nghiệm cũ.
3. **Tin record bất biến sâu:** record không đóng băng đối tượng/list nằm trong thành phần. Tạo bản sao khi dữ liệu cần bất biến.
4. **Cho rằng text block tự làm SQL an toàn:** văn bản nhiều dòng chỉ là chuỗi; câu lệnh có input phải parameterized.
5. **Phụ thuộc output tuyệt đối của JVM diagnostics/JFR:** chi tiết NPE và sự kiện runtime phụ thuộc bytecode, JDK và tải; chỉ kiểm chứng những phần thật sự ổn định.
6. **Đem API incubator cũ vào code mới:** không dùng `jdk.incubator.foreign` hoặc cấu hình `jpackage` kiểu incubator Java 14 trong dự án hiện đại; chọn `java.lang.foreign` (Java 22+) và `jpackage` chính thức.
7. **Bật tuning GC/bộ nhớ thiếu bằng chứng:** NUMA, ZGC, NVM cần điều kiện môi trường và phép đo. Không biến tối ưu chuyên biệt thành mặc định toàn dự án.
8. **Chạy Java 14 làm runtime lâu dài:** Java 14 là bản phát hành ngắn hạn đã hết vòng đời hỗ trợ thông thường; hãy dùng JDK còn được cập nhật bảo mật và cấu hình được xác nhận cho ứng dụng.

## 11. Bài tập tự kiểm tra

1. Viết `switch` expression chuyển `enum OrderStatus { NEW, PAID, SHIPPED }` sang thông báo, không dùng `break`. Thử thêm hằng enum để đánh giá tác động lên tính bao phủ các nhánh.
2. Tạo `record Coordinate(int x, int y)` và kiểm tra tính bằng nhau của hai instance. Sau đó thử một record chứa `List<String>` để nhận ra khác biệt giữa bất biến nông và bất biến sâu.
3. Tạo phương thức nhận `Object`; chỉ gọi `length()` nếu đó là `String` không rỗng, bằng pattern `instanceof` và `&&`.
4. Chuyển chuỗi SQL nhiều dòng nối bằng `+` thành text block, dùng `PreparedStatement` để truyền tham số tên người dùng.
5. Chạy `JfrStreamDemo` trên hai máy/tải khác nhau và giải thích vì sao số dòng/số phần trăm CPU không giống nhau.
6. Dùng `jpackage --type app-image` đóng gói `HelloApp`, xác nhận launcher chạy được không cần gọi lệnh `java` riêng. (Nâng cao, JDK 22+: thay đổi giá trị ghi vào `MemorySegment` rồi thử truy cập sau khi `Arena` đóng để hiểu vòng đời bộ nhớ.)

## 12. Tài liệu chính thức để đối chiếu

- Oracle, **Java Language Changes by Release** — lịch sử chuẩn hóa `switch`, record, `instanceof` và text blocks: https://docs.oracle.com/en/java/javase/24/language/java-language-changes-release.html
- Oracle, **Significant Changes in JDK 14** — JFR streaming, Helpful NPE, G1 NUMA, NVM, preview/incubator: https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-14.html
- Oracle, **Significant Changes in JDK 16** — record, pattern `instanceof` và `jpackage` chính thức: https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-16.html
- Oracle, **The java Command** — tùy chọn `ShowCodeDetailsInExceptionMessages` trên JDK hiện đại: https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- Oracle, **RecordingStream API** — luồng sự kiện JFR: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
- Oracle, **The jpackage Command** — công cụ đóng gói hiện đại: https://docs.oracle.com/en/java/javase/27/docs/specs/man/jpackage.html
- Oracle, **ExtendedMapMode API** — các chế độ map NVM có từ Java 14: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html
- OpenJDK JEP: `361` (switch), `358` (Helpful NPE), `349` (JFR streaming), `359/395` (records), `305/394` (instanceof), `368/378` (text blocks), `343/392` (jpackage), `345` (G1 NUMA), `352` (NVM), `370/454` (FFM). Danh mục: https://openjdk.org/jeps/0

**Nguyên tắc áp dụng:** học tính năng theo phiên bản **chính thức hiện tại**, dùng nó khi giải quyết vấn đề cụ thể, và kiểm tra tương thích bằng compiler, test và tài liệu của JDK thực sự triển khai.