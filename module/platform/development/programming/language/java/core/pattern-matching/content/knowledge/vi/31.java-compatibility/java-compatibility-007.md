# Biên dịch với \`--release\` phù hợp khi dùng Java Pattern Matching

## 1. Vấn đề: JDK cài trên máy không phải phiên bản Java mà ứng dụng hỗ trợ

Giả sử máy phát triển dùng JDK 24 nhưng ứng dụng phải chạy trên Java 17. Người lập trình viết:

```java
record Address(String city) {}
record Shipment(String id, Address destination) {}

static String describe(Object value) {
    return switch (value) {
        case Shipment(var id, Address(var city))
                when city != null -> "ship:" + id + ":" + city;
        default -> "other";
    };
}
```

Đây là **đoạn minh họa không độc lập**: phải đặt các khai báo trong một lớp hợp lệ. Nó sử dụng **record pattern**, **pattern matching for switch** và guard `when`, những tính năng chính thức từ Java 21. Mã này có thể được JDK 24 chấp nhận khi biên dịch cho Java 21+, nhưng **không phù hợp với hợp đồng Java 17**.

Sai lầm phổ biến là chạy `javac Shipment.java` bằng JDK mới, thấy compiler không báo lỗi rồi kết luận file `.class` sẽ dùng được trên Java 17. Nếu không chỉ rõ release, compiler thường mặc định theo phiên bản JDK đang chạy, nên có thể tạo bytecode mới hơn và cho phép API/ngữ pháp chưa có ở nền tảng đích.

Công cụ chuẩn để thể hiện **phiên bản Java SE mà mã nguồn phải tương thích** là:

```bash
javac --release 17 -encoding UTF-8 Release17Demo.java
```

Lệnh này không phải cách “cài Java 17” lên máy hay một công tắc chuyển JVM đang chạy; nó yêu cầu **compiler hiện tại** biên dịch mã theo bộ quy tắc của Java SE 17 và đối chiếu API nền tảng tương ứng.

**Mục tiêu của bài:** chọn `--release` dựa trên runtime tối thiểu thực tế; nhận biết tính năng pattern matching nào được phép ở Java 17/21; kiểm tra API mới; phân biệt lỗi biên dịch với lỗi runtime; và đưa cấu hình release vào build/CI để tránh mã chạy được trên máy tác giả nhưng lỗi khi triển khai.

## 2. \`javac --release N\` kiểm soát đồng thời ba thứ

Tài liệu `javac` mô tả `--release N` gồm ba khía cạnh:

| Khía cạnh | Với `--release 17` | Ví dụ bị từ chối |
| --- | --- | --- |
| **Ngữ pháp và quy tắc ngôn ngữ** (*source*) | Chỉ nhận cú pháp và quy tắc Java 17 cho nguồn được biên dịch | `case Shipment(var id, Address(var city))`, guard `when` theo bản Java 21 |
| **Phiên bản class file** (*target*) | Sinh class file phù hợp Java 17, major version **61** | Không xuất class file Java 21 (major **65**) từ mã đích 17 |
| **API Java SE/JDK đã xuất bản của release đích** (*platform API*) | Chỉ cho dùng các API được hỗ trợ trong Java 17 | `List.getFirst()`, được bổ sung từ Java 21 |

Tóm tắt:

```text
                javac của JDK hiện tại
                          │
                    --release 17
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
        Source 17     Class file 17   Java API 17
             │            │            │
             └────────────┴────────────┘
                          │
                 Mã của dự án phù hợp
                   hợp đồng Java 17
```

**Chú ý:** `--release` áp dụng cho mã nguồn được biên dịch và API nền tảng mà compiler nhìn thấy. Nó **không tự hạ phiên bản bytecode của JAR phụ thuộc**, không thay đổi runtime thực tế trên server và không bảo đảm mọi thư viện bên thứ ba tương thích Java 17.

Nói cách khác, `--release` là **hàng rào tương thích ở bước biên dịch**, cần kết hợp test trên runtime đích và kiểm tra dependencies.

## 3. Chọn đúng mốc Java cho từng tính năng pattern matching

Các khả năng Java không ra mắt cùng lúc. Vì vậy không nên thấy chữ “pattern” rồi mặc định chỉ cần một phiên bản bất kỳ.

| Tính năng | Phiên bản chính thức | Ví dụ | Biên dịch với `--release 17` | Biên dịch với `--release 21` |
| --- | --- | --- | --- | --- |
| `instanceof` type pattern | **Java 16** (JEP 394) | `obj instanceof String text` | Có | Có |
| Record class | **Java 16** (JEP 395) | `record Point(int x, int y) {}` | Có | Có |
| Sealed classes/interfaces | **Java 17** (JEP 409) | `sealed interface Event permits A, B` | Có | Có |
| Switch expression (giá trị) | **Java 14** (JEP 361) | `return switch (state) { ... };` | Có, nếu chỉ dùng case hợp lệ của 17 | Có |
| Record pattern (phân rã) | **Java 21** (JEP 440) | `obj instanceof Point(var x, var y)` | Không | Có |
| Pattern matching for `switch` | **Java 21** (JEP 441) | `case String text -> ...` | Không ở dạng chính thức | Có |
| Guard `when` trong pattern switch | **Java 21** (JEP 441) | `case String s when s.isBlank() -> ...` | Không | Có |
| `case null` trong enhanced `switch` | **Java 21** (JEP 441) | `case null -> "missing"` | Không ở dạng chính thức | Có |
| `SequencedCollection` / `List.getFirst()` | **Java 21** | `List.of("a").getFirst()` | Không | Có |

**Hai điểm phân biệt quan trọng:**

1. **Record class không đồng nghĩa record pattern.** Java 17 đã định nghĩa được `record Person(String name) {}`, nhưng chưa dùng được `case Person(var name)` hoặc `instanceof Person(var name)` dưới tính năng chính thức.
2. **Switch expression không đồng nghĩa pattern switch.** Java 17 đã có `return switch (enumValue) { case A -> ...; ... };`, nhưng `case String text` bên trong một switch trên `Object` không phải cú pháp chính thức được dùng chỉ với `--release 17`.

Trong Java 17, pattern matching for switch tồn tại ở dạng **preview** (JEP 406); record patterns chưa là tính năng chính thức. Điều này **không có nghĩa** lấy JDK 24 hay JDK 21 rồi thêm `--enable-preview --release 17` sẽ tái tạo được bộ tính năng preview Java 17. Chi tiết ở mục 8.

## 4. Ví dụ hoàn chỉnh tương thích Java 17

Ví dụ sau tận dụng type pattern `instanceof`, `record`, `sealed` và switch expression trên enum — tất cả đều là tính năng chính thức trước hoặc tại Java 17. Không dùng record pattern hoặc pattern switch.

Lưu nguyên văn vào **`Release17Demo.java`**:

```java
public class Release17Demo {
    enum Stage { NEW, DONE }

    sealed interface Event permits Created, Cancelled {}

    record Created(String eventId) implements Event {}
    record Cancelled(String eventId, String reason) implements Event {}

    static String describe(Object event) {
        if (event instanceof Created created) {
            return "created:" + created.eventId();
        }
        if (event instanceof Cancelled cancelled) {
            return "cancelled:" + cancelled.eventId();
        }
        return "other";
    }

    static String stageName(Stage stage) {
        return switch (stage) {
            case NEW -> "new";
            case DONE -> "done";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Created("E-17")));
        System.out.println(describe(new Cancelled("E-18", "duplicate")));
        System.out.println(describe(null));
        System.out.println(stageName(Stage.DONE));
    }
}
```

Biên dịch bằng JDK có hỗ trợ target Java 17 (chẳng hạn JDK 17 hoặc một JDK mới hơn có hỗ trợ `--release 17`):

```bash
javac --release 17 -encoding UTF-8 Release17Demo.java
java Release17Demo
```

**Đầu ra chính xác:**

```text
created:E-17
cancelled:E-18
other
done
```

### Vì sao ví dụ tương thích 17?

- `Created` và `Cancelled` là record classes — tính năng chính thức từ Java 16.
- `sealed interface Event permits ...` và việc triển khai các record con — hỗ trợ chính thức trong Java 17.
- `if (event instanceof Created created)` là type pattern cho `instanceof` — hỗ trợ chính thức từ Java 16.
- `return switch (stage) { case NEW -> ...; ... };` là switch expression dùng **enum constants** thông thường — đã chính thức từ Java 14.
- Mã không đòi hỏi `record deconstruction` hoặc `case Type var` trong switch.

Với `describe(null)`, cả hai phép `instanceof` trả `false` nên kết quả là `"other"`. Đây là hành vi của chuỗi `if`; không nên tự ý chuyển sang pattern switch mà bỏ qua chính sách null.

**Kiểm tra kỹ thuật:** đoạn mã đã được thực thi với bộ compiler chạy ở chế độ `--release 17` (qua JShell), cho đúng bốn dòng trên. Để chứng minh chạy được trên runtime Java 17 thực, còn cần chạy `java` của **JDK/JRE 17**, không chỉ chạy class file 17 bằng JVM mới hơn.

## 5. Ví dụ hoàn chỉnh cần Java 21: record patterns và pattern switch

Khi dự án **đã nâng runtime tối thiểu lên Java 21**, có thể dùng cú pháp gọn hơn để xử lý cấu trúc dữ liệu.

Lưu vào **`Release21Demo.java`**:

```java
import java.util.List;

public class Release21Demo {
    record Address(String city) {}
    record Shipment(String shipmentId, Address destination) {}

    static String route(Object request) {
        return switch (request) {
            case null -> "missing";

            case Shipment(var shipmentId, Address(var city))
                    when city != null && !city.isBlank() ->
                    "ship:" + shipmentId + ":" + city.strip();

            case Shipment(var shipmentId, var destination) ->
                    "invalid:" + shipmentId;

            default -> "unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(route(null));
        System.out.println(route(
                new Shipment("S-1", new Address(" Ha Noi "))));
        System.out.println(route(new Shipment("S-2", null)));
        System.out.println(route(
                new Shipment("S-3", new Address("  "))));
        System.out.println(route(42));

        System.out.println(
                "first:" + List.of("alpha", "beta").getFirst());
    }
}
```

Biên dịch:

```bash
javac --release 21 -encoding UTF-8 Release21Demo.java
java Release21Demo
```

**Đầu ra chính xác:**

```text
missing
ship:S-1:Ha Noi
invalid:S-2
invalid:S-3
unsupported
first:alpha
```

### Trong ví dụ có hai lý do độc lập đòi Java 21

**Lý do ngôn ngữ:**
- `Shipment(var shipmentId, Address(var city))` là record pattern lồng.
- `case ... when ...` là guard trong pattern switch.
- `case null` xử lý selector null.
- `case Shipment(var shipmentId, var destination)` sau nhánh có guard xử lý các trường hợp thiếu địa chỉ.

**Lý do API:** `List.getFirst()` thuộc API nền tảng từ Java 21, thông qua việc các collection có thứ tự hỗ trợ API sequenced collections. Ngay cả khi thay toàn bộ switch bằng `if` cũ, lời gọi `getFirst()` vẫn không tồn tại trong API Java 17.

Như vậy, khi muốn “hạ” ví dụ xuống Java 17, cần xem **cả cú pháp lẫn API**. Chỉ thay case pattern bằng `instanceof` chưa đủ nếu còn dùng phương thức của thư viện chuẩn được thêm ở Java 21.

Ví dụ cũng cho thấy null ở hai tầng khác nhau: `route(null)` đi `case null`, còn `route(new Shipment("S-2", null))` là một `Shipment` không null, không khớp mẫu `Address(...)` bên trong và đi tới case `Shipment` rộng hơn.

**Kiểm tra kỹ thuật:** chương trình đã được thực thi với compiler ở chế độ `--release 21`, có đủ sáu dòng đầu ra như trên.

## 6. Hạ release để kiểm tra tính tương thích: lỗi nào là đúng?

Hãy thử biên dịch `Release21Demo.java` bằng:

```bash
javac --release 17 -encoding UTF-8 Release21Demo.java
```

**Kết quả mong đợi: biên dịch thất bại**. Mã dùng những cấu trúc vượt khỏi tập ngôn ngữ Java 17; compiler có thể báo lỗi ở `case Shipment(...)`, record pattern hoặc guard `when`. Nội dung, thứ tự và câu chữ diagnostics có thể khác theo phiên bản `javac`.

Một đoạn tối giản cố ý không biên dịch dưới `--release 17`:

```java
class Java21PatternUnder17 {
    record Address(String city) {}
    record Shipment(String id, Address address) {}

    static String label(Object value) {
        return switch (value) {
            case Shipment(var id, Address(var city)) -> "ship:" + city;
            default -> "other";
        };
    }
}
```

Với compiler JDK 24 chạy ở chế độ source 17, kiểm tra cho thấy những diagnostics như:

```text
patterns in switch statements are not supported in -source 17
deconstruction patterns are not supported in -source 17
```

Đó là **tín hiệu hữu ích**: build đang từ chối cú pháp vượt hợp đồng Java 17 thay vì âm thầm phát hành bytecode không phù hợp.

Nếu muốn duy trì Java 17, hãy **viết lại** logic bằng `instanceof` type patterns, truy cập record qua accessor và chuỗi `if/else`. Nếu muốn dùng pattern switch và record patterns, hãy thống nhất nâng **runtime tối thiểu, build configuration, dependencies và CI** lên Java 21, rồi chọn `--release 21`.

Không được “sửa lỗi” bằng cách tắt kiểm tra release hoặc biên dịch không chỉ định release chỉ để build xanh.

## 7. Lỗi API: mã nhìn như Java 17 nhưng vẫn dùng API Java 21

Xét đoạn chỉ dùng cú pháp class và method thông thường:

```java
import java.util.List;

class Java21ApiUnder17 {
    static String first() {
        return List.of("alpha", "beta").getFirst();
    }
}
```

Lệnh:

```bash
javac --release 17 -encoding UTF-8 Java21ApiUnder17.java
```

phải báo lỗi vì `java.util.List` của Java 17 chưa có phương thức `getFirst()`. Thông báo có thể tương tự:

```text
cannot find symbol
symbol: method getFirst()
```

Nếu viết lại cho Java 17:

```java
import java.util.List;

class Api17Compatible {
    static String first() {
        List<String> names = List.of("alpha", "beta");
        return names.get(0);
    }
}
```

`List.of(...)` đã có từ Java 9 và `List.get(int)` tồn tại từ lâu, nên đoạn này dùng được dưới `--release 17`. Trong thực tế, cần xử lý `List` rỗng theo hợp đồng riêng: `get(0)` và `getFirst()` đều có thể ném ngoại lệ nếu không có phần tử, và đây không phải phép chuyển đổi bảo toàn tất cả semantics của mọi implementation `List` trong mọi điều kiện.

**Lưu ý cho pattern matching:** nhiều lỗi “hạ phiên bản” bị gán nhầm cho `case` hoặc `instanceof`. Một chương trình có thể đã loại toàn bộ pattern mới mà vẫn thất bại do gọi API mới. Hãy đọc lỗi compiler và phân biệt **unsupported language feature** với **symbol/method unavailable in platform API**.

## 8. Vì sao \`-source 17 -target 17\` chưa thay thế hoàn toàn \`--release 17\`?

Hai lựa chọn này không đồng nghĩa.

```bash
javac -source 17 -target 17 SomeClass.java
```

- `-source 17` chọn quy tắc nguồn Java 17.
- `-target 17` chọn định dạng class file phù hợp Java 17.
- Khi dùng hai cờ đó trên một JDK mới hơn, compiler **không tự động giới hạn API Java SE** về đúng bản Java 17; nó có thể nhìn thấy API của JDK đang dùng nếu không cấu hình thêm platform classes tương ứng.

Đối chứng (đã kiểm tra với JDK 24):

| Mã chứa `List.of("alpha", "beta").getFirst()` | Với JDK mới hơn | Ý nghĩa |
| --- | --- | --- |
| `javac --release 17 ...` | **Bị từ chối** | API 17 không có `getFirst()` |
| `javac -source 17 -target 17 ...` | **Có thể biên dịch** | Cú pháp và định dạng class 17, nhưng API bị “lọt” từ JDK compiler |
| `javac --release 21 ...` | **Biên dịch** | API `getFirst()` được phép ở Java 21 |

Nếu chạy class từ trường hợp giữa trên Java 17, lời gọi `List.getFirst()` có thể dẫn tới `NoSuchMethodError` khi runtime không có phương thức được tham chiếu. Đây là một lỗi rất khó phát hiện nếu chỉ thử trên JDK mới tại máy phát triển.

Đối với mục tiêu đơn giản “biên dịch tương thích Java 17/21”, **ưu tiên `--release`**. Các cấu hình `-source/-target` với platform classes riêng có thể cần trong kịch bản đặc biệt, nhưng là bài toán công cụ phức tạp hơn và dễ sai cấu hình.

Một lệnh **không hợp lệ**:

```bash
javac --release 17 -source 17 Release17Demo.java
```

`--release` không được dùng cùng `--source` hay `--target`. Chọn **một cơ chế**, thường là `--release`, để tránh cấu hình mâu thuẫn.

## 9. Các tính năng preview và giới hạn của \`--enable-preview\`

Đây là nguồn gây nhầm lẫn trong các bài Pattern Matching.

**Java 17** từng có *pattern matching for switch* ở dạng preview, chưa phải cú pháp chính thức. **Java 21** hoàn thiện tính năng này (JEP 441), cùng record patterns (JEP 440). Có khác biệt ngữ nghĩa và cú pháp giữa các phiên bản preview và bản final.

Nếu đang chạy `javac` của JDK 24, lệnh:

```bash
javac --release 17 --enable-preview MyClass.java
```

không cho phép “bật lại preview Java 17”. Java compiler chỉ hỗ trợ **preview features của chính phiên bản compiler đang chạy** khi dùng `--enable-preview`, không hồi sinh bộ preview của một release cũ. Compiler có thể báo thông điệp như:

```text
invalid source release 17 with --enable-preview
(preview language features are only supported for release 24)
```

Đây là ví dụ thông báo ghi nhận ở môi trường JDK 24; số release trong diagnostic sẽ tùy compiler.

Nếu thật sự cần nghiên cứu preview Java 17, phải dùng toolchain **JDK 17** và cấu hình compile/runtime preview của **chính Java 17**; nhưng không nên đưa mã preview cũ vào bài toán cần đảm bảo tương thích lâu dài. Với dự án mới muốn dùng pattern switch/record patterns ổn định, lựa chọn rõ ràng hơn là **Java 21+ với `--release 21`**, không cần `--enable-preview` cho hai tính năng này.

**Điểm nhớ:** `--release` chọn **mức tương thích được hỗ trợ**. Nó không phải công tắc bật mọi cú pháp có thể đã từng xuất hiện trong các JEP preview lịch sử.

## 10. Kiểm tra toolchain và class file trước khi kết luận build đúng

### 10.1. Xem JDK nào thực sự được gọi

```bash
java -version
javac -version
javac --help
```

Đối chiếu:
- `java` chạy ứng dụng bằng JVM nào?
- `javac` biên dịch bằng compiler nào?
- Compiler hiện tại hỗ trợ `--release` cho những version nào?

`javac` chỉ hỗ trợ release hiện tại và **một số release cũ**; không có bảo đảm mọi JDK đều hỗ trợ tùy ý mọi số version. Ví dụ, `javac` của Java 17 không thể tự biên dịch cho Java 21 chỉ bằng `--release 21`. Khi cần target Java 21, phải có một compiler đủ mới và có hỗ trợ release 21.

Ở môi trường có nhiều JDK, `java` và `javac` trên `PATH` có thể khác nhau. CI cũng có thể dùng JDK khác terminal cá nhân. Kiểm tra cả trình biên dịch mà build tool thực sự chọn.

### 10.2. Kiểm tra version của bytecode

Sau khi compile ra file class thực tế, dùng:

```bash
javap -verbose Release17Demo | grep "major version"
```

Trên Windows PowerShell, có thể thay bằng:

```powershell
javap -verbose Release17Demo | Select-String "major version"
```

Các giá trị thường gặp:

| Java target | Class-file major version |
| --- | --- |
| 17 | **61** |
| 21 | **65** |
| 24 | **68** |

Công thức thường dùng cho class-file versions của các release hiện đại là `major = release + 44`. Đây là phép kiểm tra nhanh **định dạng bytecode**, không kiểm tra việc dependency hoặc API bên thứ ba có tương thích hay không.

Khi file class 21 (major 65) được nạp bởi Java 17 (hỗ trợ đến major 61), runtime thường ném **`UnsupportedClassVersionError`**. Đó là dấu hiệu rất khác với lỗi `cannot find symbol` khi biên dịch hoặc `NoSuchMethodError` lúc gọi API không tồn tại.

## 11. Build theo Maven: cấu hình release một nơi

Ví dụ dự án cần Java 17, với Maven Compiler Plugin được cấu hình sử dụng thuộc tính release:

```xml
<project>
    <!-- Các phần groupId/artifactId/version của dự án được khai báo riêng. -->
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
```

Đây là **đoạn minh họa phần cấu hình**, không phải `pom.xml` hoàn chỉnh; hãy đặt khối `properties` đúng trong POM hợp lệ, phù hợp phiên bản Maven/compiler-plugin của dự án.

Nếu baseline chuyển thành Java 21:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Các lệnh tham khảo:

```bash
mvn --version
mvn clean test
```

`mvn --version` cho biết runtime Java mà Maven đang dùng. Tuy nhiên, dự án có thể cấu hình Maven Toolchains để compiler được chọn từ một JDK khác; cần kiểm tra POM/toolchain thật thay vì chỉ nhìn Java của process Maven.

Quan trọng: đặt release 17 trong POM **không đồng nghĩa test đã chạy trên Java 17**. Một pipeline dùng JDK 21 để build `--release 17` rồi chạy toàn bộ unit tests trên JDK 21 vẫn chưa chứng minh chương trình chạy đúng dưới JDK 17. Nên có job kiểm thử bằng JVM 17 thực tế nếu đó là môi trường tối thiểu được hỗ trợ.

## 12. Build theo Gradle: tách compiler JDK khỏi release đích

Ví dụ Gradle Groovy DSL cho phép dùng compiler toolchain Java 21 nhưng yêu cầu mã sản phẩm tương thích Java 17:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
```

Đây là phần cấu hình minh họa của `build.gradle` cho dự án Java; không phải `build.gradle.kts` (Kotlin DSL). Cần dùng phiên bản Gradle và JDK toolchain được hỗ trợ theo tài liệu của dự án.

- `java.toolchain.languageVersion = 21` chọn compiler/JDK phù hợp cho tác vụ Java.
- `options.release = 17` yêu cầu compiler sinh mã theo ngôn ngữ, bytecode và API Java 17.
- Hai thiết lập này nói về **hai câu hỏi khác nhau**: “dùng compiler nào?” và “sản phẩm hỗ trợ Java nào?”.

Nếu mục tiêu sản phẩm là Java 21, đổi `options.release = 21` và kiểm thử với runtime Java 21. Nếu dự án có source sets/modules khác nhau (chẳng hạn một module Java 17, một module Java 21), phải cấu hình release theo đúng module, không đặt mặc định toàn dự án rồi giả định mọi artifact giống nhau.

Lệnh tham khảo:

```bash
./gradlew --version
./gradlew clean test
```

Trong Windows PowerShell có thể dùng `.\gradlew.bat --version` và `.\gradlew.bat clean test`. Giống Maven, đừng quên test JVM có thể khác compiler JVM.

## 13. Quy trình lựa chọn \`--release\` cho từng dự án

### Bước 1 — Xác định baseline thật

Hỏi: **phiên bản Java thấp nhất mà artifact phải chạy được là gì?**

- Nếu dịch vụ triển khai trên Java 17 và chưa được nâng cấp: target Java **17**.
- Nếu toàn bộ runtime đã là Java 21 trở lên và các phụ thuộc hỗ trợ: có thể target **21**.
- Nếu một thư viện phải phục vụ cả ứng dụng Java 17 và Java 21: phần API chung của thư viện thường nên **được biên dịch cho Java 17**, trừ khi có chiến lược phân phối đa phiên bản rõ ràng.

Không chọn release theo “JDK trên laptop mới nhất” hoặc theo cú pháp muốn dùng. Chọn theo **hợp đồng triển khai và hỗ trợ**.

### Bước 2 — Lập bảng các tính năng đang dùng

Ví dụ một module có:
- `record` và `sealed`: tương thích 17.
- `obj instanceof Type variable`: tương thích 17.
- `switch (obj) { case Type x -> ... }`: cần 21 nếu muốn bản chính thức.
- `record Type(var x, var y)`: cần 21.
- `List.getFirst()`: API 21.

Nếu chỉ một tính năng cần 21, không thể công bố cả module đó tương thích 17 bằng cách chỉ thay class-file target. Phải viết lại tính năng hoặc nâng baseline.

### Bước 3 — Dùng compiler hỗ trợ target

Chạy `javac -version` và `javac --help`. Chọn phiên bản JDK đủ mới để hỗ trợ release đích; compiler cũ hơn release đích không thể biết cú pháp/API tương lai.

### Bước 4 — Biên dịch với release cố định

```bash
javac --release 17 -encoding UTF-8 -d out17 Release17Demo.java
```

Hoặc:

```bash
javac --release 21 -encoding UTF-8 -d out21 Release21Demo.java
```

Hai lệnh trên tạo thư mục output nếu cần và ghi file class khi **người học tự chạy trong môi trường của họ**; tên file phải khớp public class trong từng ví dụ. Việc đặt output riêng giúp tránh dùng nhầm file class cũ biên dịch bằng release khác.

### Bước 5 — Chạy trên JVM tối thiểu

Để xác minh target 17, dùng `java` **thật sự của Java 17**, không chỉ JDK mới hơn:

```bash
java -cp out17 Release17Demo
```

Để xác minh target 21, chạy bằng Java 21:

```bash
java -cp out21 Release21Demo
```

Việc chạy chương trình trên Java 24 không chứng minh nó sẽ chạy đúng trên Java 17, dù major version của class file đã được hạ.

### Bước 6 — Lặp lại trong CI

CI nên thể hiện ít nhất hai mục tiêu độc lập:

1. **Build/compile gate:** mã không dùng cú pháp và API vượt baseline; ví dụ `--release 17`.
2. **Runtime gate:** chạy tests/integration trên JVM tối thiểu 17, đồng thời có thể test thêm JVM mới hơn nếu dự án cam kết hỗ trợ.

Nếu không được phép dùng các artifact Java 21 trong module target17, một lệnh `javac --release 17` sẽ chặn trực tiếp chúng trước khi release.

## 14. Các lỗi thường gặp và cách nhận diện

| Triệu chứng | Nguyên nhân khả dĩ | Cần kiểm tra |
| --- | --- | --- |
| `patterns in switch ... not supported in -source 17` | Dùng pattern switch Java 21 dưới release 17 | Tính năng ngôn ngữ và baseline |
| `deconstruction patterns ... not supported in -source 17` | Record pattern chưa hỗ trợ ở Java 17 final | Thay bằng accessor/type pattern hoặc nâng release |
| `cannot find symbol: getFirst()` | API `List.getFirst()` không có ở Java 17 | Phiên bản API và `--release` |
| `invalid target release: 21` hoặc `release version 21 not supported` | Compiler quá cũ để target 21 | `javac -version`, `javac --help` |
| `UnsupportedClassVersionError` | Runtime quá cũ cho class-file version | Major version của class/dependency và `java -version` |
| `NoSuchMethodError` khi gọi API | Mã tham chiếu method không hiện hữu trong runtime hoặc khác phiên bản | Dùng `--release`, kiểm tra classpath và thư viện |
| `invalid source release 17 with --enable-preview` | Muốn dùng preview cũ qua compiler mới | Dùng baseline ổn định hoặc đúng toolchain preview tương ứng |
| `--release cannot be used with --source/--target` | Trộn hai cơ chế chọn release | Chỉ dùng một cơ chế |
| Chạy được trên máy tác giả, fail trên CI | JDK/Gradle/Maven toolchain hoặc dependencies khác | In versions và chạy test trên target JVM |
| Code Java 17 vẫn fail compile ở target17 | Đang dùng API mới hay syntax Java 21 ẩn trong module | Phân biệt lỗi language với lỗi API |

**Đọc thông báo cụ thể quan trọng hơn đoán.** Các dạng message phụ thuộc phiên bản `javac`. Đừng xem một câu chữ lỗi cụ thể là giao diện được bảo đảm bất biến giữa mọi JDK.

## 15. Những giới hạn của \`--release\`: cần test thật dù biên dịch PASS

`--release 17` là một hàng rào mạnh nhưng không phải lời hứa rằng **mọi thứ** sẽ chạy được trên máy chỉ có Java 17.

### 15.1. Phụ thuộc bên thứ ba

Nếu module target17 phụ thuộc một JAR được biên dịch bằng Java21 (class major65), riêng việc compile mã của bạn với `--release17` không tự chuyển class trong JAR ấy thành major61. Compiler có thể báo lỗi đọc class version khi sử dụng dependency; nếu dependency chỉ được nạp ở runtime, có thể gặp lỗi khi chạy. Phải kiểm tra compatibility và class version của dependencies.

### 15.2. API không kiểm tra tĩnh

Reflection như `Class.forName(...)`, `Method.invoke(...)`, tải class theo tên chuỗi, mã sinh động hoặc service loader có thể phụ thuộc API không được compiler kiểm tra tại vị trí lời gọi. Test trên runtime tối thiểu vẫn cần thiết.

### 15.3. Annotation processors và code generation

Processor hoặc plugin build có thể chạy trên JDK của compiler và sinh ra mã chứa API/cú pháp mới. Cần áp dụng release cho mọi bước compile thực sự và kiểm tra output của generator thay vì giả định chỉ một cờ ở một module đủ bảo vệ toàn dự án.

### 15.4. Native libraries, OS, runtime flags và cấu hình

Tương thích class file/API không đảm bảo native library, biến môi trường, module access, TLS, charset, hệ điều hành hoặc cấu hình JVM giống nhau. CI/integration test trên môi trường đích là phần cần thiết của hợp đồng triển khai.

### 15.5. Binary compatibility khi cập nhật thư viện

`NoSuchMethodError` cũng có thể phát sinh khi phiên bản thư viện chạy khác thư viện dùng lúc compile, ngay cả khi tất cả class đều thuộc cùng Java release. Đừng kết luận mọi `NoSuchMethodError` đều do sai `--release`.

### 15.6. Multi-release JAR và modules

Các dự án cố ý phát hành nhiều biến thể class cho nhiều JDK có thể dùng multi-release JAR hoặc cấu hình module phức tạp. Đây là thiết kế phân phối riêng, cần test từng biến thể; không nên ngộ nhận một lời gọi `javac --release 17` sẽ tự tạo artifact đa phiên bản.

## 16. Checklist review trước khi merge hoặc phát hành

- [ ] Có tài liệu nêu **minimum supported Java runtime** không?
- [ ] `--release` có tương ứng runtime tối thiểu hay không?
- [ ] JDK compiler đang dùng **có hỗ trợ** release ấy không?
- [ ] Pattern matching trong mã có yêu cầu Java 21 không? Type pattern `instanceof` khác record pattern và pattern switch.
- [ ] API nền tảng có được giới hạn đúng version không? Có dùng `List.getFirst()` hay API mới tương tự?
- [ ] Không trộn `--release` với `-source`/`-target` trong cùng tác vụ compile?
- [ ] Không dùng preview cũ bằng cách bật `--enable-preview` trên JDK mới?
- [ ] Mã nguồn dùng `UTF-8` nhất quán nếu chứa dấu tiếng Việt?
- [ ] Đã kiểm tra class-file major version đúng target chưa?
- [ ] Dependencies có build cho Java tương thích hay không?
- [ ] Đã chạy unit/integration tests bằng **JVM tối thiểu thật** chưa?
- [ ] Build của IDE, Maven, Gradle và CI có cùng mục tiêu release không?
- [ ] Có tách output directories để tránh file class cũ từ release khác không?
- [ ] Nếu nâng baseline 17 lên 21, đã cập nhật cả compiler, runtime, Docker image, CI và tài liệu phát hành chưa?

Một baseline có thể thay đổi theo thời gian, nhưng **mọi nơi liên quan phải thay đổi đồng bộ**. Hãy xem nâng `--release` là quyết định sản phẩm/hạ tầng chứ không phải cách nhanh để bỏ qua lỗi compiler.

## 17. Bài tập tự luyện có đáp án

**Bài 1 — Chọn release.** Dịch vụ dùng JDK 24 để build, môi trường production còn Java 17. Dự án dùng type pattern `instanceof` và `record`, không có cú pháp Java 21. Nên dùng release nào?

**Đáp án:** `--release 17`. JDK24 có thể compile cho Java17 nếu hỗ trợ target này; vẫn cần chạy tests trên JVM17 thật.

**Bài 2 — Record pattern.** Tại sao `if (candidate instanceof Point(var x, var y))` bị từ chối dưới `--release 17` dù `record Point(int x, int y) {}` biên dịch được?

**Đáp án:** record class chính thức từ Java16, nhưng **record pattern phân rã** là tính năng chính thức từ Java21. Muốn tương thích17, dùng type pattern `instanceof Point point` rồi gọi `point.x()`, `point.y()`.

**Bài 3 — Hai lỗi độc lập.** Đoạn code có `case String s when s.isBlank()` và `List.of("a").getFirst()`. Dưới `--release 17` có thể chỉ sửa case mà build được không?

**Đáp án:** không. Guarded pattern switch cần Java21; `List.getFirst()` cũng là API21. Phải thay cả cú pháp và API hoặc nâng baseline lên Java21.

**Bài 4 — Source/target.** Vì sao dùng `-source 17 -target 17` trên JDK24 vẫn có thể compile lời gọi `List.getFirst()`, trong khi `--release 17` không?

**Đáp án:** source/target giới hạn cú pháp và định dạng class, không tự buộc API nền tảng về bản Java17. `--release` giới hạn cả ba mặt.

**Bài 5 — Class file.** Major version 65 là target Java nào? Java17 có load class đó được không?

**Đáp án:** Java21. Runtime Java17 thường ném `UnsupportedClassVersionError` khi cố nạp class major65.

**Bài 6 — Preview.** Khi chạy javac24, bật `--enable-preview --release 17` có hợp lệ để dùng các preview patterns của Java17 không?

**Đáp án:** không. Preview chỉ được bật cho release của compiler hiện tại, không phát lại preview lịch sử. Muốn tính năng final hãy dùng Java21+ và `--release21`.

**Bài 7 — Maven/Gradle.** Dự án dùng JDK21 compiler nhưng cần hỗ trợ Java17 runtime. Có cần đổi compiler về JDK17 mới dùng được `--release17` không?

**Đáp án:** không nhất thiết. Compiler JDK21 có thể target17. Nhưng phải **kiểm tra dependencies** và chạy tests trên JVM17 thật; toolchain compiler và runtime đích là hai vấn đề khác nhau.

**Bài 8 — Library dependency.** Code của bạn đã build với `--release17` nhưng dependency có một class major65. Có bảo đảm production Java17 hoạt động không?

**Đáp án:** không. `--release` không biến bytecode dependency thành bản Java17. Cần chọn dependency tương thích hoặc điều chỉnh baseline.

**Bài 9 — Runtime.** Bạn compile với `--release17` rồi test chỉ trên JDK24; có được coi như đã xác nhận chạy đúng trên JDK17 không?

**Đáp án:** chưa. Hãy chạy artifact bằng JVM17 thật trong CI/test deployment để phát hiện khác biệt runtime, dependencies, reflection và cấu hình.

**Bài 10 — Nâng phiên bản.** Khi team quyết định chuyển từ Java17 sang Java21 để dùng record patterns, những gì phải thay ngoài cờ compile?

**Đáp án:** runtime production, build JDK hỗ trợ21, cấu hình Maven/Gradle, image/container, dependencies, toolchain CI và bộ test tương thích. Chỉ nâng `--release` trên máy phát triển là chưa đủ.

## 18. Ghi nhớ

- **`javac --release N` chọn cùng lúc ngôn ngữ, class-file target và API Java SE/JDK của release N**.
- Với **Java17**, có thể dùng `instanceof` type pattern, record classes, sealed hierarchy và switch expression với case thường, nhưng **không** dùng record patterns/pattern switch Java21 final.
- Với **Java21**, có thể dùng record patterns, pattern matching for switch, guard `when` và các API mới như `List.getFirst()`.
- **`-source/-target` không thay thế an toàn cho `--release`** khi cần giới hạn API của một JDK cũ.
- **Preview features gắn với phiên bản compiler**, không thể dùng compiler mới để “bật lại” preview lịch sử của Java17.
- **Compiler JDK khác runtime tối thiểu**; build pass trên JDK mới chưa chứng minh chạy được trên runtime cũ.
- **`--release` không tự đảm bảo tương thích dependencies, reflection, cấu hình và môi trường**; luôn kiểm thử trên JVM tối thiểu thật.
- Chốt release theo hợp đồng hỗ trợ của dự án và duy trì đồng nhất trong IDE, Maven/Gradle và CI.

**Tham khảo chính thức:**
- [Oracle JDK 21 — The javac Command, option --release](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Oracle Java 21 — Java Language Changes Summary](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-summary.html)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
