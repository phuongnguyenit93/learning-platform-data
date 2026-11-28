# Các tính năng ổn định từ Java 16 còn hữu ích trong Java hiện đại

> **Chương:** Định hướng Java 16  
> **Phạm vi:** Những cải tiến được đưa vào hoặc trở thành tính năng chính thức ở Java 16, vẫn có giá trị khi viết ứng dụng trên các JDK hiện đại. Bài học ưu tiên API và cách sử dụng ổn định; những tính năng chỉ ở giai đoạn thử nghiệm trong Java 16 được phân biệt rõ.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `record` và pattern matching cho `instanceof` giúp mã Java rõ ràng hơn.
2. Chọn đúng giữa `Stream.toList()`, các collector và `Stream.mapMulti()` theo yêu cầu đầu ra.
3. Hiểu vai trò của `jpackage` khi phát hành ứng dụng và mối liên hệ với `jlink`.
4. Nhận biết tác động của việc đóng gói mạnh các API nội bộ JDK, cùng một số cải tiến JVM đáng chú ý.
5. Phân biệt các tính năng đã ổn định ở Java 16 với những tính năng khi ấy chỉ là *preview* hoặc *incubator*.

## 1. Vị trí của Java 16 trong hệ sinh thái Java hiện đại

Java 16 được phát hành vào tháng 3/2021 và **không phải phiên bản hỗ trợ dài hạn (LTS)**. Khi bắt đầu dự án mới, nên chọn một JDK còn được nhà cung cấp hỗ trợ theo chính sách của tổ chức, chẳng hạn Java 21 hoặc Java 25, rồi tận dụng các tính năng ổn định đã xuất hiện từ Java 16. Không cần chạy ứng dụng trên Java 16 chỉ để dùng các tính năng trong bài.

Các thay đổi có ích nhất có thể chia thành ba nhóm:

| Nhóm | Cải tiến | Ý nghĩa thực tế |
| --- | --- | --- |
| Mô hình dữ liệu | **Records** — JEP 395 | Khai báo các đối tượng dữ liệu ngắn gọn, có ngữ nghĩa giá trị |
| Cú pháp kiểm tra kiểu | **Pattern Matching for `instanceof`** — JEP 394 | Kết hợp kiểm tra kiểu với khai báo biến đã ép kiểu |
| Xử lý dữ liệu | **`Stream.toList()` và `Stream.mapMulti()`** | Thu kết quả và biến đổi luồng theo cách rõ ràng hơn |
| Phát hành phần mềm | **`jpackage`** — JEP 392 | Tạo gói ứng dụng có thể phân phối trên từng hệ điều hành |
| Tích hợp hệ thống | **Unix-Domain Socket Channels** — JEP 380 | Giao tiếp tiến trình trên cùng máy qua socket cục bộ, khi nền tảng hỗ trợ |
| Nền tảng JDK/JVM | **Đóng gói mạnh nội bộ JDK** — JEP 396; **Elastic Metaspace** — JEP 387; cải tiến **ZGC** — JEP 376 | Tăng tính bền vững của phụ thuộc, cải thiện việc quản lý bộ nhớ và tạm dừng GC trong một số tải |

Các tính năng ở trên có mức độ ứng dụng khác nhau. Với ứng dụng nghiệp vụ thông thường, hãy học `record`, `instanceof`, `Stream` và nguyên tắc tránh API nội bộ JDK trước.

## 2. `record`: mô hình hóa dữ liệu bằng ít mã hơn

### 2.1. Vấn đề mà `record` giải quyết

Một lớp chỉ dùng để mang dữ liệu thường cần constructor, các trường `private final`, accessor, `equals()`, `hashCode()` và `toString()`. Viết tay nhiều mã lặp lại vừa tốn công vừa dễ bỏ sót một thành phần khi thay đổi mô hình.

Java 16 hoàn thiện **records** (JEP 395). Khai báo:

```java
record CustomerId(String value) {}
```

trình biên dịch tự tạo constructor chuẩn, các trường tương ứng với thành phần khai báo, accessor `value()`, `equals()`, `hashCode()` và `toString()`. Hai record cùng kiểu có các thành phần bằng nhau sẽ bằng nhau theo `equals()`.

> `record` phù hợp với **dữ liệu có cấu trúc và ngữ nghĩa giá trị**: DTO, kết quả truy vấn, lệnh, sự kiện, đối tượng truyền giữa các tầng. Nó không mặc nhiên phù hợp với mọi entity có vòng đời, danh tính hoặc yêu cầu proxy của framework.

### 2.2. Constructor gọn, kiểm tra dữ liệu và phương thức tính toán

Ví dụ sau là một chương trình đầy đủ, có thể lưu thành `Demo.java` và chạy bằng JDK 16 trở lên:

```java
import java.math.BigDecimal;
import java.util.Objects;

public class Demo {
    record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
        OrderLine {
            sku = Objects.requireNonNull(sku, "sku").strip();
            unitPrice = Objects.requireNonNull(unitPrice, "unitPrice");

            if (sku.isEmpty() || quantity <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
        }

        BigDecimal subtotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static void main(String[] args) {
        OrderLine line = new OrderLine("  BOOK-01  ", 2, new BigDecimal("19.50"));
        System.out.println(line.sku());       // BOOK-01
        System.out.println(line.quantity());  // 2
        System.out.println(line.subtotal());  // 39.00
    }
}
```

Điểm cần hiểu:

- `OrderLine { ... }` là **compact canonical constructor**: chỗ phù hợp để kiểm tra hoặc chuẩn hóa tham số; trình biên dịch thực hiện việc gán các tham số thành phần vào trường sau phần thân constructor.
- Accessor của record có dạng `line.sku()`, **không phải** `line.getSku()`.
- Có thể khai báo phương thức nghiệp vụ, phương thức static, triển khai interface và thêm xác thực. Record không thể kế thừa một lớp tùy ý hoặc có thêm trường instance ngoài các thành phần record.
- Các trường thành phần là `final`, nhưng **record chỉ bất biến ở mức nông** (*shallowly immutable*). Nếu một thành phần trỏ đến `List` hoặc đối tượng có thể thay đổi, dữ liệu bên trong vẫn có thể bị sửa.

Khi cần bảo vệ thành phần dạng tập hợp, tạo bản sao phòng vệ:

```java
import java.util.List;
import java.util.Objects;

record Invoice(String id, List<String> items) {
    Invoice {
        Objects.requireNonNull(id, "id");
        items = List.copyOf(Objects.requireNonNull(items, "items"));
    }
}
```

`List.copyOf()` tạo danh sách không cho phép sửa qua API của danh sách; nếu phần tử là đối tượng có thể thay đổi thì vẫn phải xem xét tính bất biến của từng phần tử. Không nên hiểu `record` là giải pháp tự động bảo đảm an toàn đa luồng.

### 2.3. Khi nào nên và không nên dùng record?

| Dùng tốt | Cần cân nhắc lớp thông thường |
| --- | --- |
| DTO từ REST API, dữ liệu báo cáo, cấu hình bất biến | Đối tượng cần thay đổi trạng thái qua nhiều bước |
| Kết quả của một thao tác: `Result(code, message)` | Entity ORM cần constructor không tham số, proxy hoặc cơ chế quản lý riêng |
| Khóa tổng hợp, sự kiện, dữ liệu truyền giữa các tầng | Kiểu dữ liệu cần kế thừa từ một lớp cụ thể |

## 3. Pattern matching cho `instanceof`: kiểm tra kiểu và dùng biến an toàn

Trước đây, sau khi kiểm tra bằng `instanceof`, lập trình viên thường phải ép kiểu lại:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Từ Java 16, **pattern matching for `instanceof`** là tính năng chính thức (JEP 394):

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Biến `text` chỉ tồn tại trong phạm vi mà trình biên dịch xác định phép kiểm tra đã thành công (*flow scoping*). Điều này giúp hạn chế ép kiểu lặp lại và tránh dùng biến khi chưa biết kiểu.

### 3.1. Kết hợp với điều kiện và trả về sớm

```java
public class PatternDemo {
    static void showCode(Object value) {
        if (!(value instanceof String code)) {
            System.out.println("Expected a string");
            return;
        }

        // code chắc chắn là String ở đây.
        if (!code.isBlank()) {
            System.out.println(code.strip());
        }
    }

    static boolean isValidName(Object value) {
        return value instanceof String name && !name.isBlank();
    }
}
```

Lưu ý:

- Khi `value == null`, phép `instanceof String name` trả về `false`.
- Với toán tử `&&`, điều kiện bên phải được xét khi điều kiện kiểm tra kiểu đã thành công, nên có thể dùng biến pattern.
- Không giả định biến pattern tồn tại ở mọi nhánh, đặc biệt khi kết hợp `||` hoặc khi luồng điều khiển không bảo đảm phép kiểm tra thành công.
- Tính năng đang nói đến là pattern matching cho **`instanceof`**. Pattern matching cho `switch` có lộ trình chuẩn hóa riêng ở các bản Java về sau; không gọi đó là tính năng ổn định của Java 16.

### 3.2. Tình huống phù hợp

Chọn `instanceof` pattern khi cần xử lý đầu vào từ API kiểu `Object`, hệ thống plugin, dữ liệu hỗn hợp hoặc phân nhánh theo một vài kiểu rõ ràng. Nếu phải xếp nhiều kiểm tra kiểu dài và liên tục, hãy xem lại thiết kế: đôi khi đa hình qua interface hay một mô hình dữ liệu phân loại tốt hơn.

## 4. Hai bổ sung thực tế cho Stream API

### 4.1. `Stream.toList()`: tạo danh sách kết quả dễ đọc

Java 16 bổ sung phương thức kết thúc `Stream.toList()`:

```java
import java.util.List;
import java.util.ArrayList;

public class StreamToListDemo {
    public static void main(String[] args) {
        List<String> names = List.of("an", "binh", "chi")
                .stream()
                .map(String::toUpperCase)
                .toList();

        System.out.println(names); // [AN, BINH, CHI]

        // names.add("DUNG"); // UnsupportedOperationException
        List<String> editable = new ArrayList<>(names);
        editable.add("DUNG");
    }
}
```

**Quy tắc quan trọng:** danh sách do `Stream.toList()` trả về là **không thể sửa thông qua các thao tác thêm/xóa/thay thế**. Đừng viết mã dựa trên một kiểu triển khai `List` cụ thể hoặc giả định danh sách đó có thể sửa được.

| Cách tạo danh sách | Bảo đảm về khả năng sửa | Ghi chú |
| --- | --- | --- |
| `stream.toList()` (Java 16+) | **Không thể sửa** | Ngắn gọn khi chỉ cần kết quả để đọc |
| `stream.collect(Collectors.toList())` | **Không có bảo đảm** về khả năng sửa hay kiểu cụ thể | Không nên dựa vào hiện tượng triển khai thường trả về `ArrayList` |
| `stream.collect(Collectors.toUnmodifiableList())` | **Không thể sửa** | Từ chối phần tử `null` |
| `new ArrayList<>(stream.toList())` | **Có thể sửa** | Nêu rõ ý định cần một bản sao để cập nhật |

Không nhầm `toList()` với `List.of(...)` hoặc `List.copyOf(...)`: các API có hợp đồng riêng về việc xử lý `null` và sao chép dữ liệu. Khi thiết kế luồng, tốt nhất nên xác định rõ đầu vào có thể chứa `null` hay không.

### 4.2. `Stream.mapMulti()`: ánh xạ mỗi phần tử thành 0, 1 hoặc nhiều phần tử

`mapMulti()` cũng có từ Java 16. Nó hữu ích khi với mỗi đầu vào, ta muốn phát ra một số lượng phần tử đầu ra không cố định mà không cần tạo một `Stream` trung gian cho từng đầu vào.

```java
import java.util.List;

public class MapMultiDemo {
    record Order(String code, List<Integer> itemIds) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", List.of(10, -1, 20)),
                new Order("B", List.of(30))
        );

        List<Integer> validIds = orders.stream()
                .<Integer>mapMulti((order, downstream) -> {
                    for (int id : order.itemIds()) {
                        if (id > 0) {
                            downstream.accept(id);
                        }
                    }
                })
                .toList();

        System.out.println(validIds); // [10, 20, 30]
    }
}
```

Ở đây, mỗi `Order` có thể tạo ra nhiều ID hợp lệ; `downstream.accept(...)` phát từng ID vào luồng kết quả. Cú pháp `<Integer>mapMulti` giúp trình biên dịch suy luận kiểu đầu ra rõ ràng trong trường hợp cần thiết.

So sánh cách chọn:

- Dùng `map(...)` khi **một** đầu vào luôn tạo **một** đầu ra.
- Dùng `filter(...)` khi chỉ muốn giữ/bỏ từng phần tử.
- Dùng `flatMap(...)` khi đã có hoặc muốn biểu diễn kết quả từng đầu vào dưới dạng `Stream`.
- Dùng `mapMulti(...)` khi logic tạo **0 đến nhiều** phần tử thông qua callback; có thể tránh tạo nhiều stream nhỏ, nhưng đừng mặc định nó luôn nhanh hơn `flatMap` trong mọi trường hợp.

## 5. `jpackage`: đóng gói ứng dụng để bàn để phát hành

`jpackage` được chuẩn hóa ở Java 16 (JEP 392). Công cụ này giúp đóng gói ứng dụng Java thành **application image** hoặc gói cài đặt phù hợp hệ điều hành, kèm runtime cần thiết để người dùng không phải tự cấu hình một JDK riêng.

Giả sử bạn đã xây dựng `dist/salesdesk.jar` chứa lớp chạy chính `com.example.Main`. Từ máy có JDK hỗ trợ `jpackage`, dùng:

```bash
jpackage --type app-image --name SalesDesk --input dist --main-jar salesdesk.jar --main-class com.example.Main --dest build
```

Lệnh này tạo một thư mục ứng dụng cho **hệ điều hành đang chạy**. Khi cần trình cài đặt, chọn định dạng được nền tảng và công cụ đóng gói trên máy build hỗ trợ, chẳng hạn `msi` trên Windows, `dmg`/`pkg` trên macOS hoặc `deb`/`rpm` trên Linux. Một số định dạng yêu cầu công cụ hệ điều hành, thiết lập ký mã hoặc thành phần build bổ sung.

**Không xem `jpackage` là công cụ build đa nền tảng từ một máy duy nhất.** Để phát hành cho Windows, macOS và Linux, thường cần quy trình build/test trên từng nền tảng đích.

### `jlink` hỗ trợ `jpackage` như thế nào?

`jlink` đã có **từ Java 9**, không phải tính năng mới của Java 16. Công cụ này tạo runtime tùy biến từ các module JDK. `jpackage` có thể đóng gói ứng dụng cùng runtime; khi cần chủ động xây dựng runtime, có thể kết hợp cả hai:

```bash
jlink --add-modules java.base,java.logging --output build/runtime --strip-debug --no-header-files --no-man-pages
```

Danh sách module trên **chỉ là ví dụ**, không tự động đủ cho mọi ứng dụng. Hãy phân tích phụ thuộc với `jdeps`, kiểm tra phần dùng reflection, provider, native library và chạy thử ứng dụng bằng runtime tùy biến. Thiếu module có thể chỉ bộc lộ lỗi khi chạy một chức năng ít dùng.

**Ứng dụng phù hợp:** công cụ nội bộ có giao diện đồ họa, trình cài đặt cho nhân viên, phần mềm desktop cần trải nghiệm cài đặt nhất quán. Đối với dịch vụ chạy trong container hay trên server, `jpackage` thường không phải bước đóng gói chính; cơ chế build ảnh/container và quản lý runtime phù hợp hơn.

## 6. JDK ngày càng đóng gói chặt API nội bộ

JEP 396 thay đổi mặc định của Java 16 theo hướng **đóng gói mạnh các thành phần nội bộ của JDK**, qua đó hạn chế việc thư viện hoặc ứng dụng tự truy cập vào lớp và thành viên không nằm trong API công khai. Java 17 tiếp tục siết chặt theo JEP 403.

Ví dụ lỗi thường gặp khi nâng JDK là một thư viện cũ cố dùng reflection để mở thành viên không được công khai trong `java.base`; chương trình có thể gặp `InaccessibleObjectException`. Đây thường là dấu hiệu **phụ thuộc vào cơ chế nội bộ** chứ không phải lỗi cú pháp `record` hay `Stream`.

Cách xử lý bền vững:

1. Nâng thư viện lên bản tương thích với JDK mục tiêu; ưu tiên API chuẩn của Java.
2. Quét phần phụ thuộc tĩnh bằng `jdeps --jdk-internals <file-jar>` để phát hiện một số tham chiếu vào API nội bộ JDK.
3. Chạy bài kiểm tra tích hợp vì phân tích tĩnh không phát hiện được mọi truy cập bằng reflection.
4. Chỉ khi đang chuyển đổi tạm thời mới cân nhắc tùy chọn mở gói có phạm vi hẹp như `--add-opens`, với kế hoạch loại bỏ phụ thuộc đó.

Không dựa vào `--illegal-access` để xử lý lâu dài: đây là cơ chế chuyển tiếp cũ và không còn là giải pháp hữu hiệu trên các JDK hiện đại.

## 7. Những cải tiến nền tảng còn đáng biết

### 7.1. Elastic Metaspace (JEP 387)

Metaspace lưu metadata của các lớp được JVM nạp. Từ Java 16, việc cấp phát và hoàn trả bộ nhớ của Metaspace được cải tiến theo hướng **hoàn trả bộ nhớ đã cam kết hiệu quả hơn khi phù hợp**, hữu ích cho dịch vụ thường xuyên tải/gỡ lớp, ứng dụng dùng nhiều class loader hoặc môi trường cần kiểm soát bộ nhớ.

Đây là cải tiến **ở cấp JVM**: ứng dụng thường không phải đổi mã để sử dụng. Lượng bộ nhớ thực tế còn phụ thuộc khối lượng tải lớp, cấu hình và khả năng thu hồi class loader; không nên hứa hẹn mức giảm bộ nhớ cố định.

### 7.2. ZGC xử lý ngăn xếp luồng đồng thời (JEP 376)

Java 16 tiếp tục cải thiện ZGC bằng cách chuyển thêm công việc xử lý ngăn xếp luồng sang pha đồng thời, giúp giảm phần việc phải làm trong một số điểm dừng của ứng dụng. Đây là **một bước trong quá trình phát triển ZGC**, không đồng nghĩa mọi dịch vụ phải chuyển sang ZGC hoặc mọi lần GC đều không có độ trễ.

Khi chọn collector trên JDK hiện đại, đo thời gian tạm dừng, thông lượng và mức sử dụng bộ nhớ theo tải thực. Không sao chép nguyên các cờ tuning hoặc giả định hiệu năng của Java 16 sang JDK mới mà không kiểm tra lại.

### 7.3. Unix-domain sockets (JEP 380)

Java 16 cung cấp API chuẩn cho kênh socket trên cùng máy qua `StandardProtocolFamily.UNIX` và `UnixDomainSocketAddress`. Nó phù hợp với giao tiếp giữa các tiến trình cục bộ khi môi trường chạy hỗ trợ kiểu socket này.

```java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

public class LocalSocketClient {
    public static void main(String[] args) throws Exception {
        var address = UnixDomainSocketAddress.of(Path.of("/tmp/app.sock"));
        try (var channel = SocketChannel.open(StandardProtocolFamily.UNIX)) {
            channel.connect(address); // Cần có server đang lắng nghe tại địa chỉ.
            // Đọc/ghi dữ liệu qua channel.
        }
    }
}
```

Đường dẫn, quyền truy cập và mức hỗ trợ phụ thuộc hệ điều hành; ví dụ `/tmp/app.sock` phù hợp với môi trường Unix-like và chỉ chạy thành công khi server tồn tại. API này không phải lựa chọn thay thế mặc định cho HTTP hoặc TCP giữa các máy khác nhau.

## 8. Đừng nhầm tính năng chính thức với tính năng thử nghiệm của Java 16

Java 16 cũng chứa một số công nghệ khi đó **chưa phải API hoặc cú pháp ổn định**. Chúng có thể đã thay đổi, được chuẩn hóa ở phiên bản khác hoặc bị thay thế; vì vậy không học cú pháp thử nghiệm của Java 16 như cách viết nên áp dụng hiện nay.

| Chủ đề từng xuất hiện ở Java 16 | Trạng thái khi ở Java 16 | Cách học thực tế |
| --- | --- | --- |
| `record` | **Chính thức** | Học và dùng ngay với JDK hiện đại |
| Pattern matching cho `instanceof` | **Chính thức** | Học và dùng ngay |
| Sealed classes | **Preview lần 2** | Nếu cần, học cú pháp **chính thức từ Java 17** trở đi |
| Vector API | **Incubator** | Tra API và trạng thái của **JDK đích**, không bê nguyên ví dụ incubator từ Java 16 |
| Foreign-Memory Access / Foreign Linker API | **Incubator** | Học Foreign Function & Memory API chính thức ở **Java 22+** khi có nhu cầu truy cập native |

Thêm một điểm dễ nhầm: **pattern matching cho `switch` không phải tính năng chính thức của Java 16**. Nếu bài toán cần `switch` nâng cao, hãy học phiên bản chuẩn hóa ở các JDK mới hơn theo đúng mức tương thích mục tiêu.

## 9. Ví dụ kết hợp: nhận dữ liệu, lọc và tạo kết quả chỉ đọc

Đoạn mã sau phối hợp ba cải tiến chính trong một tác vụ: nhận danh sách có nhiều kiểu dữ liệu, giữ các dòng hàng hợp lệ và tạo một danh sách kết quả:

```java
import java.util.List;

public class ModernJava16Features {
    record Line(String sku, int quantity) {}

    static List<Line> validLines(List<?> rawValues) {
        return rawValues.stream()
                .<Line>mapMulti((value, downstream) -> {
                    if (value instanceof Line line && line.quantity() > 0) {
                        downstream.accept(line);
                    }
                })
                .toList();
    }

    public static void main(String[] args) {
        List<?> input = List.of(
                new Line("A", 2), "not a line",
                new Line("B", 0), new Line("C", 5)
        );

        List<Line> result = validLines(input);
        System.out.println(result);
        // [Line[sku=A, quantity=2], Line[sku=C, quantity=5]]
    }
}
```

**Phân tích:** `Line` biểu diễn dữ liệu có cấu trúc; `instanceof Line line` kiểm tra kiểu và gán biến; `mapMulti` chỉ phát ra phần tử thỏa điều kiện; `toList()` trả danh sách kết quả không thể sửa. Trong ứng dụng thực tế, dữ liệu đầu vào có kiểu rõ ràng thường tốt hơn `List<?>`; ở đây kiểu hỗn hợp chỉ nhằm minh họa pattern matching.

## 10. Quy tắc chọn công cụ khi làm dự án

| Nhu cầu | Công cụ nên xem xét | Điều cần nhớ |
| --- | --- | --- |
| Biểu diễn bản ghi dữ liệu nhỏ, ít thay đổi | `record` | Bất biến nông; sao chép phòng vệ với thành phần mutable |
| Kiểm tra và dùng một giá trị theo kiểu runtime | `instanceof` pattern | Chú ý phạm vi biến và xử lý `null` |
| Thu kết quả stream để đọc | `Stream.toList()` | Không sửa danh sách kết quả |
| Một đầu vào sinh nhiều đầu ra | `mapMulti()` hoặc `flatMap()` | Chọn cách diễn đạt rõ ràng; đo hiệu năng khi cần |
| Phát hành ứng dụng desktop | `jpackage` | Build đúng hệ điều hành đích, test runtime đi kèm |
| Chuyển ứng dụng cũ sang JDK mới | API chuẩn + nâng thư viện + `jdeps` | Loại dần phụ thuộc vào API nội bộ |
| Tối ưu bộ nhớ hoặc GC | Theo dõi bằng công cụ đo | Không kết luận chỉ từ tên JEP hoặc tham số cũ |

### Bài tập tự luyện

1. **Record:** Tạo `record Product(String code, int stock)`. Dùng compact constructor để từ chối `code` rỗng và `stock < 0`. Thử so sánh hai instance có cùng giá trị bằng `equals()`.
2. **Pattern matching:** Viết hàm `describe(Object input)`: với `String` không rỗng thì trả độ dài; với `Integer` không âm thì trả giá trị; trường hợp khác trả thông báo dữ liệu không hợp lệ. Không dùng ép kiểu thủ công.
3. **Stream:** Từ `List<List<Integer>>`, tạo danh sách các số dương bằng `mapMulti` và `toList()`. Thử gọi `add` trên kết quả và giải thích lỗi; sau đó tạo một `ArrayList` có thể sửa.
4. **Vận hành:** Chọn một ứng dụng cũ, kiểm tra thư viện có tham chiếu API nội bộ JDK không, rồi nêu phương án nâng thư viện hoặc thay API. Nếu là ứng dụng desktop, mô tả lệnh `jpackage` cho hệ điều hành triển khai.

### Câu hỏi tự kiểm tra

- Vì sao `record` có trường `final` mà vẫn chưa chắc bất biến sâu?
- Vì sao `stream.collect(Collectors.toList())` không phải lựa chọn đáng tin nếu mã yêu cầu chắc chắn một danh sách có thể sửa?
- Trong ví dụ `value instanceof String s && !s.isBlank()`, điều gì đảm bảo `s` dùng được ở vế phải?
- `jlink` và `jpackage` khác nhau ở bước nào của quá trình phân phối ứng dụng?
- Khi một thư viện phản chiếu vào thành viên nội bộ JDK và lỗi trên JDK mới, hướng xử lý dài hạn là gì?

## Tài liệu đối chiếu chính thức

- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java SE 16 — Stream API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html) (các phương thức `toList()` và `mapMulti()`)
- [JEP 392 — Packaging Tool](https://openjdk.org/jeps/392)
- [JEP 380 — Unix-Domain Socket Channels](https://openjdk.org/jeps/380)
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396) và [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [JEP 387 — Elastic Metaspace](https://openjdk.org/jeps/387) và [JEP 376 — ZGC: Concurrent Thread-Stack Processing](https://openjdk.org/jeps/376)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409) và [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454), để đối chiếu các chủ đề đã được chuẩn hóa sau Java 16.

**Ghi nhớ:** Giá trị lâu dài của Java 16 nằm ở mô hình dữ liệu bằng `record`, mã kiểm tra kiểu dễ đọc, các tiện ích Stream, công cụ đóng gói ứng dụng và hướng chuyển sang API JDK công khai. Hãy sử dụng chúng trên **JDK hiện đại được hỗ trợ**, thay vì phụ thuộc vào những tính năng thử nghiệm hoặc cách mở quyền nội bộ đã lỗi thời.
