# Bản đồ tính năng Java 21 đã hoàn thiện và dùng không cần bật Preview

Java 21 (JDK 21) bổ sung một nhóm tính năng đã được hoàn thiện và có thể dùng trực tiếp trong chương trình Java SE 21. Bản đồ này tập trung vào sáu hạng mục chính: hai tính năng ngôn ngữ, ba API thư viện và một cải tiến bộ thu gom rác. Các ví dụ bên dưới không yêu cầu `--enable-preview`.

Phạm vi được giới hạn ở những tính năng đã final trong Java 21. Các mục được phát hành dưới trạng thái Preview hoặc Incubator không được xem là tính năng hoàn thiện trong bài này. Một thay đổi vận hành liên quan đến nạp Java agent được trình bày riêng vì nó ảnh hưởng đến việc chạy và giám sát ứng dụng.

## 1. Bản đồ tổng quan

| Nhóm | Tính năng | JEP | Giá trị chính |
|---|---|---:|---|
| Ngôn ngữ | Record Patterns | 440 | Tách dữ liệu từ record ngay trong điều kiện kiểm tra kiểu |
| Ngôn ngữ | Pattern Matching for `switch` | 441 | Rẽ nhánh theo kiểu và mẫu dữ liệu, hỗ trợ kiểm tra đầy đủ các nhánh |
| Đồng thời | Virtual Threads | 444 | Xử lý nhiều tác vụ chờ I/O với chi phí mỗi luồng thấp |
| Collections | Sequenced Collections | 431 | API thống nhất cho phần tử đầu, cuối và thứ tự đảo ngược |
| Bảo mật | Key Encapsulation Mechanism API | 452 | Trao đổi khóa bí mật dùng mật mã khóa công khai |
| Hiệu năng JVM | Generational ZGC | 439 | Thu gom đối tượng trẻ và đối tượng sống lâu theo hai thế hệ |

## 2. Record Patterns — JEP 440

Record pattern cho phép kiểm tra một giá trị có thuộc kiểu record hay không và lấy các component của record ngay trong cùng biểu thức. Có thể lồng nhiều record pattern để đi sâu vào cấu trúc dữ liệu.

Ví dụ, một yêu cầu có thông tin khách hàng và địa chỉ:

```java
record Address(String city) {}
record Customer(String name, Address address) {}

static void printCity(Object value) {
    if (value instanceof Customer(String name, Address(String city))) {
        System.out.println(name + " lives in " + city);
    }
}
```

Khi `value` khớp với `Customer`, Java tự gọi các accessor của record và gán giá trị component vào `name` và `city`. Đoạn mã không cần ép kiểu `Customer`, gọi `address()` rồi gọi tiếp `city()`.

Record pattern hữu ích khi xử lý DTO, kết quả truy vấn, sự kiện hoặc cấu trúc dữ liệu bất biến. Có thể kết hợp nó với pattern matching for `switch` để biểu diễn việc phân loại và tách dữ liệu trong cùng một cấu trúc.

## 3. Pattern Matching for switch — JEP 441

Java 21 hoàn thiện việc mở rộng `switch` để các nhãn `case` có thể dùng pattern. Nhờ đó, `switch` có thể phân nhánh theo kiểu dữ liệu, kết hợp record pattern và dùng mệnh đề `when` để đặt điều kiện bổ sung.

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case String text when text.isBlank() -> "empty text";
        case String text -> "text: " + text;
        case Integer number -> "integer: " + number;
        default -> "other";
    };
}
```

Điểm cần nhớ:

- `case String text` vừa kiểm tra kiểu vừa tạo biến `text` có kiểu `String` trong nhánh tương ứng.
- `when` là guard: nhánh chỉ khớp khi pattern đúng và biểu thức điều kiện trả về `true`.
- `case null` xử lý tường minh giá trị `null`. Nếu không có nhãn `case null`, `switch` trên giá trị `null` vẫn ném `NullPointerException`.
- Các nhánh phải được sắp xếp để pattern tổng quát không che khuất pattern cụ thể phía sau. Với hierarchy `sealed` hoặc enum, compiler có thể kiểm tra tính đầy đủ của các nhánh.

Khi `switch` trả về giá trị, dùng switch expression giúp tránh biến tạm và giảm nguy cơ bỏ sót trường hợp. Với record pattern, có thể phân tích trực tiếp cấu trúc của từng loại dữ liệu:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

static double area(Shape shape) {
    return switch (shape) {
        case Circle(var radius) -> Math.PI * radius * radius;
        case Rectangle(var width, var height) -> width * height;
    };
}
```

`Shape` là sealed interface với danh sách kiểu con được khai báo rõ ràng, vì vậy `switch` có thể bao phủ mọi kiểu con mà không cần `default`.

## 4. Virtual Threads — JEP 444

Virtual thread là luồng do Java runtime quản lý. Khi một virtual thread chờ một thao tác I/O có khả năng block, runtime thường có thể tạm dừng virtual thread đó và dùng lại platform thread làm carrier cho một virtual thread khác. Nhờ vậy, ứng dụng có thể duy trì nhiều tác vụ đồng thời mà không cần tạo một OS thread cho mỗi tác vụ.

Ví dụ dùng một virtual thread cho mỗi tác vụ:

```java
import java.util.concurrent.Executors;

static void loadDashboard() throws Exception {
    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
        var profile = executor.submit(() -> loadProfile(42));
        var orders = executor.submit(() -> loadOrders(42));

        System.out.println(profile.get());
        System.out.println(orders.get());
    }
}
```

`newVirtualThreadPerTaskExecutor()` tạo một virtual thread cho mỗi tác vụ được gửi vào executor. `try` with resources đóng executor và chờ các tác vụ đã gửi hoàn tất. Đây là cách phù hợp khi các tác vụ chủ yếu chờ database, HTTP hoặc I/O khác.

Các nguyên tắc sử dụng:

- Dùng virtual thread cho nhiều tác vụ đồng thời có thời gian chờ I/O đáng kể, đặc biệt với mô hình thread-per-request.
- Virtual thread không làm phép tính CPU chạy nhanh hơn. Với tác vụ CPU-bound, số lõi CPU vẫn là giới hạn chính.
- Không tạo pool để tái sử dụng virtual thread. Hãy tạo virtual thread theo từng tác vụ; nếu cần giới hạn số lời gọi đến dịch vụ ngoài, dùng semaphore hoặc giới hạn sẵn có của connection pool.
- Tránh dùng `ThreadLocal` để cache đối tượng đắt đỏ dùng lại giữa nhiều tác vụ: mỗi tác vụ có virtual thread riêng nên cách cache này có thể làm tăng số đối tượng và bộ nhớ.
- Trong JDK 21, virtual thread có thể bị pin vào carrier khi thực hiện thao tác blocking bên trong `synchronized` hoặc native method. Nếu ứng dụng không đạt mức đồng thời mong muốn, cần đo và kiểm tra các đoạn code này.

Virtual thread giúp tăng khả năng mở rộng và thông lượng của ứng dụng I/O-bound; không nên hiểu nó là cơ chế giảm độ trễ của từng tác vụ hoặc thay thế giới hạn tài nguyên bên ngoài.

## 5. Sequenced Collections — JEP 431

Java 21 thêm ba interface vào Collections Framework:

- `SequencedCollection<E>`: collection có thứ tự duyệt xác định.
- `SequencedSet<E>`: set có thứ tự duyệt xác định.
- `SequencedMap<K, V>`: map có thứ tự duyệt xác định.

Các interface này cung cấp cách thao tác thống nhất ở hai đầu của collection. Với `SequencedCollection`, những phương thức chính là `addFirst`, `addLast`, `getFirst`, `getLast`, `removeFirst`, `removeLast` và `reversed`.

```java
import java.util.ArrayList;
import java.util.List;

static void showSequence() {
    var names = new ArrayList<>(List.of("An", "Binh"));

    names.addFirst("Chi");
    names.addLast("Dung");

    System.out.println(names.getFirst());
    System.out.println(names.getLast());

    for (String name : names.reversed()) {
        System.out.println(name);
    }
}
```

`reversed()` trả về view có thứ tự ngược của collection. Với implementation hỗ trợ cập nhật, thao tác qua view sẽ được phản ánh vào collection gốc. Đây là view, không phải một bản sao độc lập.

`SequencedMap` bổ sung các thao tác tương ứng như `firstEntry`, `lastEntry`, `pollFirstEntry`, `pollLastEntry`, `putFirst`, `putLast` và `reversed`. Ví dụ:

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

static void showMapOrder() {
    SequencedMap<String, Integer> scores = new LinkedHashMap<>();
    scores.putLast("An", 10);
    scores.putLast("Binh", 9);

    System.out.println(scores.firstEntry());
    System.out.println(scores.reversed());
}
```

Các thao tác thêm hoặc xóa ở hai đầu là optional operation. Collection bất biến hoặc implementation không hỗ trợ thay đổi có thể ném `UnsupportedOperationException`; hãy kiểm tra khả năng sửa đổi của collection đang dùng.

## 6. Key Encapsulation Mechanism API — JEP 452

Key Encapsulation Mechanism (KEM) là kỹ thuật dùng khóa công khai để hai bên cùng thiết lập một khóa bí mật đối xứng. Bên gửi dùng public key của bên nhận để tạo secret key và một encapsulation message. Bên nhận dùng private key tương ứng cùng message đó để khôi phục cùng secret key.

Java 21 cung cấp API `javax.crypto.KEM`. Ví dụ dưới đây dùng thuật toán `DHKEM` với cặp khóa `X25519` để minh họa quá trình đóng gói và giải đóng gói khóa:

```java
import java.security.KeyPairGenerator;
import java.util.Arrays;
import javax.crypto.KEM;

static void exchangeSecret() throws Exception {
    var keyPairGenerator = KeyPairGenerator.getInstance("X25519");
    var receiverKeys = keyPairGenerator.generateKeyPair();

    // Sender: tạo shared secret và gửi encapsulation message.
    var senderKem = KEM.getInstance("DHKEM");
    var encapsulated = senderKem.newEncapsulator(receiverKeys.getPublic())
            .encapsulate();
    var senderSecret = encapsulated.key();

    // Receiver: dùng private key để khôi phục shared secret.
    var receiverKem = KEM.getInstance("DHKEM");
    var receiverSecret = receiverKem.newDecapsulator(receiverKeys.getPrivate())
            .decapsulate(encapsulated.encapsulation());

    System.out.println(Arrays.equals(
            senderSecret.getEncoded(), receiverSecret.getEncoded()));
}
```

Trong ví dụ, hai bên nhận được cùng một secret key. Ứng dụng thực tế cần xác thực public key và tích hợp KEM vào một giao thức bảo mật được thiết kế, kiểm thử phù hợp. KEM không tự cung cấp toàn bộ giao thức xác thực, quản lý khóa hay mã hóa dữ liệu; không tự xây dựng thuật toán mật mã từ các primitive riêng lẻ.

## 7. Generational ZGC — JEP 439

Generational ZGC mở rộng Z Garbage Collector bằng cách quản lý heap thành hai thế hệ: young generation cho đối tượng mới tạo và old generation cho đối tượng đã sống lâu hơn. Vì phần lớn đối tượng thường có vòng đời ngắn, ZGC có thể thu gom young generation thường xuyên hơn và xử lý old generation theo nhịp phù hợp.

Trong JDK 21, có thể bật Generational ZGC bằng các tùy chọn:

```bash
java -XX:+UseZGC -XX:+ZGenerational -Xms4g -Xmx4g -jar service.jar
```

ZGC hướng đến ứng dụng cần thời gian tạm dừng GC rất thấp. Đổi lại, mức tiêu thụ CPU và thông lượng tổng thể phụ thuộc workload. Hãy so sánh với collector hiện tại bằng tải đại diện, GC log, độ trễ p95/p99, CPU và bộ nhớ trước khi chọn cho production.

Tùy chọn `-XX:+ZGenerational` trong ví dụ là cấu hình của JDK 21. Không sao chép nguyên cấu hình này sang JDK khác mà chưa kiểm tra tài liệu của đúng phiên bản, vì mặc định và tùy chọn ZGC đã thay đổi ở các bản JDK mới hơn.

## 8. Lưu ý vận hành: nạp Java agent động — JEP 451

JDK 21 phát cảnh báo khi một Java agent được nạp động vào JVM đang chạy, chẳng hạn qua cơ chế attach của công cụ giám sát hoặc chẩn đoán. Thay đổi này chuẩn bị cho việc siết quyền nạp agent động ở các bản JDK tương lai.

Agent được nạp ngay lúc khởi động bằng tùy chọn `-javaagent` không tạo ra cảnh báo này. Khi nâng ứng dụng lên JDK 21, hãy kiểm tra APM, profiler, công cụ kiểm thử và công cụ chẩn đoán có attach agent vào tiến trình đang chạy hay không; cập nhật cách cấu hình theo hướng dẫn của nhà cung cấp.

JEP 451 là thay đổi về hành vi và cảnh báo của JVM, không phải một API Preview. Nó được ghi riêng để người vận hành nhận biết ảnh hưởng khi triển khai Java 21.

## 9. Dùng các tính năng này mà không bật Preview

Với các tính năng trong bản đồ này, có thể biên dịch và chạy bằng Java 21 mà không thêm `--enable-preview`. Ví dụ:

```bash
javac --release 21 -d out src/Main.java
java -cp out Main
```

Kiểm tra phiên bản compiler và runtime bằng `javac -version` và `java -version`. Nếu dự án dùng Maven hoặc Gradle, cấu hình toolchain/compiler release về 21 để mã nguồn và API mục tiêu nhất quán. Không thêm `--enable-preview` cho các tính năng đã final được liệt kê ở trên.

| Nhu cầu | Tính năng nên xem xét |
|---|---|
| Phân loại dữ liệu theo kiểu và tách component record | Record Patterns, Pattern Matching for `switch` |
| Xử lý đồng thời nhiều request chờ I/O | Virtual Threads |
| Thao tác phần tử đầu/cuối hoặc duyệt ngược collection | Sequenced Collections |
| Thiết lập khóa đối xứng bằng mật mã khóa công khai | KEM API |
| Giảm thời gian tạm dừng GC cho workload phù hợp | Generational ZGC |
| Điều tra cảnh báo agent được attach vào JVM đang chạy | JEP 451 và cấu hình công cụ giám sát |

## 10. Tài liệu tham khảo

- [Oracle — Java Language Changes for Java SE 21](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Oracle — Virtual Threads in Java SE 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle — Creating Sequenced Collections, Sets, and Maps](https://docs.oracle.com/en/java/javase/21/core/creating-sequenced-collections-sets-and-maps.html)
- [Java SE 21 API — SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html)
- [Java SE 21 API — KEM](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [Oracle — Z Garbage Collector in JDK 21](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html)
- [Oracle — Significant Changes in JDK 21](https://docs.oracle.com/en/java/javase/21/migrate/significant-changes-jdk-release.html)
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
- [JEP 439 — Generational ZGC](https://openjdk.org/jeps/439)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451)
- [JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452)
