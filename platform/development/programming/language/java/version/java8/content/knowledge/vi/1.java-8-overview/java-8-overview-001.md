# Những năng lực Java 8 tiếp tục dùng trong Java hiện đại

Java 8 mang đến những nền tảng đã định hình cách viết Java hiện đại: lambda và functional interface, Stream, Optional, API thời gian `java.time`, `CompletableFuture`, phương thức mặc định trong interface và các thao tác hữu ích trên collection. Chúng vẫn được dùng trong những ứng dụng Java chạy trên JDK hiện đại. Bài này tập trung vào **năng lực còn giá trị, cách vận dụng và những lỗi cần tránh**. Ví dụ chạy với JDK 17 trở lên; các API minh họa chính đều có từ Java 8, trừ khi ghi rõ.

## 1. Bản đồ kiến thức cần nắm

| Năng lực | Vì sao còn quan trọng | Dùng ở đâu |
| --- | --- | --- |
| Lambda, method reference, functional interface | Biểu diễn hành vi thành đối số, viết quy tắc lọc và biến đổi rõ ràng | `Comparator`, callback, `Predicate`, `Function` |
| Stream API, collectors | Lọc, chuyển đổi, nhóm, tổng hợp dữ liệu theo pipeline | Dữ liệu bộ nhớ, báo cáo, kết quả truy vấn |
| `Optional<T>` | Diễn đạt khả năng không có kết quả trong API | Hàm tra cứu, `findFirst`, `max` |
| `java.time` | Phân biệt ngày lịch, thời điểm, múi giờ và khoảng thời gian | Lịch hẹn, thời hạn, log, API |
| `CompletableFuture` | Ghép các bước bất đồng bộ và xử lý lỗi | Dịch vụ gọi API bất đồng bộ, tác vụ I/O |
| Interface `default`/`static` | Phát triển hợp đồng thư viện với hành vi mặc định | Thiết kế interface, tương thích API |
| `Map`/`Collection` methods | Thao tác tập dữ liệu đúng mục đích, ít mã thủ công | `computeIfAbsent`, `merge`, `removeIf` |

Đây không phải danh sách cú pháp cần học thuộc. Hãy hiểu **hợp đồng hoạt động, điều kiện sử dụng, chi phí và cách xử lý trường hợp bất thường** của từng API. Một vòng lặp thông thường vẫn là lựa chọn tốt khi pipeline khiến logic khó đọc.

## 2. Lambda, functional interface và method reference

*Functional interface* là interface có một phương thức trừu tượng; annotation `@FunctionalInterface` giúp trình biên dịch kiểm tra hợp đồng này. Lambda cung cấp phần triển khai của phương thức đó ngay tại chỗ. Biến cục bộ được lambda bắt giữ phải là `final` hoặc *effectively final*, tức không bị gán lại sau khi khởi tạo.

Các kiểu quan trọng trong `java.util.function`:

- `Predicate<T>` nhận `T` và trả `boolean`; dùng `and`, `or`, `negate` để ghép điều kiện.
- `Function<T,R>` chuyển `T` thành `R`; dùng `andThen`/`compose` để kết hợp phép biến đổi.
- `Consumer<T>` nhận dữ liệu và thực hiện thao tác không trả giá trị; `Supplier<T>` cung cấp giá trị.
- `UnaryOperator<T>`, `BinaryOperator<T>` và các biến thể nguyên thủy (`IntPredicate`, `ToIntFunction`, ...) biểu đạt hợp đồng cụ thể, có thể tránh boxing không cần thiết.

```java
Predicate<String> present = s -> s != null && !s.isEmpty();
Function<String, String> normalize = String::trim;
Comparator<String> order =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
```

Đây là **đoạn minh họa**, cần import `java.util.Comparator` và `java.util.function.*` trong chương trình. `String::trim` là *method reference*: truyền lời gọi phương thức có chữ ký phù hợp thay cho lambda `s -> s.trim()`. Method reference phù hợp khi nó làm ý định sáng rõ; lambda có thể tốt hơn nếu cần diễn đạt một biểu thức hoặc điều kiện.

**Lỗi thường gặp:** cố gộp nhiều hành vi và tác dụng phụ vào một lambda; ghi vào biến hoặc collection dùng chung trong Stream; lạm dụng lambda nhiều dòng khiến người đọc khó theo dõi. Tách logic nghiệp vụ phức tạp thành phương thức có tên và dùng method reference khi phù hợp.

## 3. Stream API và Collectors

Một Stream là luồng phần tử để thực hiện các phép toán tổng hợp, không phải collection lưu trữ. Pipeline có **nguồn → thao tác trung gian → thao tác kết thúc**.

- Trung gian: `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`. Phần lớn thao tác này *lazy*: chỉ hoạt động khi có terminal operation.
- Kết thúc: `collect`, `reduce`, `count`, `findFirst`, `anyMatch`, `max`. Sau một thao tác kết thúc, **không dùng lại cùng Stream**.
- `Collectors.groupingBy` nhóm theo khóa; `mapping` biến đổi phần tử trong nhóm; `counting`, `summingInt` tổng hợp; `joining` nối chuỗi.
- `IntStream`, `LongStream`, `DoubleStream` dùng cho dữ liệu số để giảm boxing và cung cấp các phép tổng hợp như `sum`/`average`.

Ví dụ ý tưởng: từ danh sách đơn hàng, dùng `filter` giữ những đơn thỏa mức tiền, sau đó `groupingBy` và `summingInt` tính tổng theo khách. Đọc từ trái sang phải là thấy mục đích xử lý dữ liệu.

**Hợp đồng của kết quả:** `collect(Collectors.toList())` có trong Java 8 nhưng không cam kết kiểu danh sách hoặc quyền sửa đổi. Nếu bắt buộc có danh sách mutable, chọn `collect(Collectors.toCollection(ArrayList::new))`. `Stream.toList()` chỉ có từ Java 16 và trả về danh sách không thể sửa đổi: hữu ích trên JDK hiện đại nhưng không phải phương thức Java 8.

**Đừng tự động song song hóa.** `parallelStream()` có chi phí điều phối, đặc biệt bất lợi với dữ liệu nhỏ, pipeline chứa I/O hoặc thao tác trên trạng thái chia sẻ. Chỉ dùng khi chức năng an toàn, phép tổng hợp phù hợp và benchmark chứng minh có lợi. `forEach` không phải cách tốt để lắp ghép kết quả bằng cách sửa một container bên ngoài; ưu tiên collector/reduction hoặc một vòng lặp rõ ràng.

## 4. Optional: biểu diễn khả năng thiếu kết quả

`Optional<T>` giúp API trả về một giá trị **có thể vắng mặt** mà người gọi phải cân nhắc. Đặc biệt thích hợp cho hàm tra cứu một phần tử, như kết quả `stream.findFirst()`, `min()` hoặc `max()`.

- `Optional.of(value)` yêu cầu giá trị khác `null`; `ofNullable(value)` biến `null` thành `Optional.empty()`.
- `map` áp dụng phép biến đổi khi có giá trị; `flatMap` dùng cho hàm trả `Optional` để không sinh `Optional<Optional<T>>`.
- `orElse(defaultValue)` đánh giá biểu thức mặc định ngay khi gọi; `orElseGet(supplier)` chỉ tính giá trị dự phòng khi Optional rỗng.
- `orElseThrow(...)` phù hợp khi thiếu dữ liệu phải trở thành lỗi có thông điệp rõ. `ifPresent` dùng cho thao tác nhỏ nếu có kết quả.

```java
Optional<String> name = Optional.ofNullable(null);
String display = name.map(String::trim).orElseGet(() -> "Khách");
System.out.println(display); // Khách
```

Đây là **đoạn minh họa**, cần import `java.util.Optional`. Tránh gọi `get()` khi chưa xác nhận có giá trị, tránh dùng `Optional` cho mọi field hay tham số một cách máy móc. Nếu một phương thức trả nhiều kết quả, collection rỗng thường phù hợp hơn `Optional<List<T>>`. Không coi Optional là một cơ chế giải quyết mọi vấn đề `null`; hợp đồng API vẫn phải rõ ràng.

## 5. java.time: đúng loại thời gian, đúng múi giờ

Các kiểu ngày giờ cốt lõi của `java.time` bất biến và có ngữ nghĩa riêng:

| Ý nghĩa | Kiểu |
| --- | --- |
| Ngày lịch không có giờ hoặc múi giờ | `LocalDate` |
| Giờ trong ngày không kèm ngày | `LocalTime` |
| Ngày và giờ địa phương chưa gắn múi giờ | `LocalDateTime` |
| Một thời điểm trên timeline (UTC) | `Instant` |
| Ngày giờ trong vùng có quy tắc múi giờ | `ZonedDateTime` với `ZoneId` |
| Khoảng thời gian theo giây/phút/giờ; hoặc theo ngày/tháng/năm | `Duration`; `Period` |

`LocalDateTime` chưa đủ thông tin để chỉ ra một thời điểm toàn cầu: cần zone/offset và quy tắc chuyển đổi. `ZoneId.of("Asia/Ho_Chi_Minh")` biểu diễn một khu vực có quy tắc thời gian; một offset cố định `+07:00` chỉ cho biết độ lệch. Dùng `DateTimeFormatter` để định dạng/parse và xác định rõ múi giờ tại biên API hoặc khi lưu trữ.

```java
Instant event = Instant.parse("2026-11-05T12:00:00Z");
ZonedDateTime local = event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
System.out.println(local.format(DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm")));
// 05/11/2026 19:00
```

Đây là **đoạn minh họa**, cần `import java.time.*;` và `import java.time.format.DateTimeFormatter;`. Khi tính hạn theo ngày, dùng `LocalDate.plusDays` hoặc `Period` theo ngày lịch; khi đo khoảng thời gian tuyệt đối, dùng `Instant`/`Duration`. Tránh tự đổi thời điểm bằng cách cộng số giờ cố định khi hệ thống cần xử lý vùng có DST.

## 6. CompletableFuture và phối hợp bất đồng bộ

`CompletableFuture<T>` đại diện cho kết quả có thể hoàn tất sau, hoặc thất bại. Nó giúp tổ chức các phép toán phụ thuộc nhau:

- `supplyAsync` tạo kết quả từ tác vụ bất đồng bộ; `runAsync` thực hiện tác vụ không trả kết quả.
- `thenApply` biến đổi một kết quả; `thenCompose` nối hàm trả `CompletionStage` để làm phẳng các bước bất đồng bộ.
- `thenCombine` ghép hai kết quả độc lập; `allOf` báo khi một nhóm hoàn tất, còn việc lấy giá trị từng future là bước riêng.
- `exceptionally` cung cấp fallback khi lỗi; `handle` xem xét cả thành công và lỗi. Không dùng fallback để che khuất lỗi nghiêm trọng.
- `join()` chờ kết quả và có thể block luồng gọi; cần quản lý executor, timeout, tài nguyên, hủy tác vụ và chính sách xử lý lỗi ở ranh giới phù hợp.

Ví dụ chương trình độc lập:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class AsyncExample {
    public static void main(String[] args) {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<String> result =
                    CompletableFuture.supplyAsync(() -> "java", executor)
                            .thenApply(String::toUpperCase)
                            .exceptionally(error -> "ERROR");
            System.out.println(result.join());
        } finally {
            executor.shutdown();
        }
    }
}
```

Lưu thành `AsyncExample.java`; chạy `javac AsyncExample.java` rồi `java AsyncExample`. Kết quả:

```text
JAVA
```

Trong hệ thống thật, kích thước executor và chiến lược timeout phải phù hợp tính chất tác vụ. `CompletableFuture` vẫn hữu ích khi cần **ghép luồng kết quả**, kể cả ở dự án có thêm virtual threads: mô hình lập trình blocking có thread riêng và mô hình composition bất đồng bộ có ưu nhược điểm khác nhau.

## 7. Phương thức default trong interface và thao tác collection

`default` method cho phép interface có một triển khai mặc định; nó hỗ trợ tiến hóa API và tái sử dụng hành vi nhỏ, rõ nghĩa. `static` method trong interface là tiện ích gắn với hợp đồng đó. Nếu một lớp có hai phương thức `default` xung đột cùng chữ ký từ các interface, lớp phải tự override để giải quyết.

```java
interface Named {
    String name();

    default String label() {
        return "Name: " + name();
    }

    static boolean validName(String value) {
        return value != null && !value.isEmpty();
    }
}
```

Đoạn trên là định nghĩa interface, không phải chương trình độc lập. Dùng `default` để mở rộng một hợp đồng có ý nghĩa; tránh đưa business logic lớn hay trạng thái mutable vào phương thức mặc định.

Các thao tác `Map`/`Collection` vẫn hữu ích hàng ngày:

- `getOrDefault(key, fallback)` lấy dự phòng khi không có ánh xạ phù hợp.
- `computeIfAbsent(key, mapper)` tính/đặt giá trị khi chưa có, thường dùng trong cache hay gom nhóm.
- `merge(key, value, combiner)` kết hợp giá trị đã có, ví dụ đếm tần suất.
- `removeIf(predicate)` xóa phần tử thỏa điều kiện; `List.replaceAll(operator)` biến đổi tại chỗ; `Map.forEach` duyệt cặp khóa–giá trị.

Lưu ý mutability và đồng thời: không phải collection nào cũng cho sửa; `HashMap` không mặc nhiên an toàn cho nhiều luồng cùng ghi. Khi truy cập đồng thời, cân nhắc đồng bộ hóa hoặc `ConcurrentHashMap` và hiểu tính nguyên tử từng phương thức. Tránh để callback của `computeIfAbsent` tự sửa chính map mà nó đang thao tác.

## 8. Ví dụ tổng hợp: từ collection đến báo cáo

Bài toán: lọc các đơn hàng từ 80 trở lên, tính tổng theo khách, tìm khách của đơn hàng lớn nhất và tính ngày hẹn sau bảy ngày. Ví dụ chỉ sử dụng các API có từ Java 8, chạy trực tiếp trên JDK 17+.

Tạo tệp `Java8Foundations.java`:

```java
import java.time.LocalDate;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class Java8Foundations {
    static final class Order {
        private final String customer;
        private final int amount;

        Order(String customer, int amount) {
            this.customer = customer;
            this.amount = amount;
        }

        String getCustomer() { return customer; }
        int getAmount() { return amount; }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("An", 120),
                new Order("Binh", 50),
                new Order("An", 80)
        );

        Map<String, Integer> totals = orders.stream()
                .filter(order -> order.getAmount() >= 80)
                .collect(Collectors.groupingBy(
                        Order::getCustomer,
                        TreeMap::new,
                        Collectors.summingInt(Order::getAmount)
                ));

        Optional<Order> biggest = orders.stream()
                .max(Comparator.comparingInt(Order::getAmount));

        System.out.println(totals);
        System.out.println(biggest.map(Order::getCustomer).orElse("Không có"));
        System.out.println(LocalDate.of(2026, 11, 5).plusDays(7));
    }
}
```

Biên dịch và chạy:

```bash
javac Java8Foundations.java
java Java8Foundations
```

Kết quả chuẩn:

```text
{An=200}
An
2026-11-12
```

Hai đơn của An có giá trị 120 và 80, nên tổng là 200; đơn của Binh bằng 50 không đạt bộ lọc. `TreeMap` bảo đảm thứ tự khóa khi in kết quả; `max` chọn đơn 120, `Optional.map` lấy tên khách; `LocalDate.plusDays(7)` tính theo ngày lịch. Mọi dữ liệu đầu vào cố định nên stdout không phụ thuộc giờ hệ thống.

## 9. Checklist áp dụng vào Java hiện đại

**Thứ tự ưu tiên học:** lambda và functional interface → Stream và collectors → Optional → `java.time` và múi giờ → `CompletableFuture` → default methods và các thao tác collection. Mỗi bước nên đi cùng bài tập nhỏ và đánh giá tính dễ đọc của code.

Khi viết hoặc review, tự hỏi:

1. Lambda đang biểu đạt một hành vi rõ ràng hay giấu tác dụng phụ và trạng thái dùng chung?
2. Stream đã có terminal operation đúng, không được sử dụng hai lần, và kết quả có đúng tính mutable cần thiết?
3. Có tránh `parallelStream` theo cảm tính, chỉ dùng sau khi đánh giá tính đúng và benchmark không?
4. Optional có nằm ở nơi kết quả thực sự có thể thiếu, được xử lý an toàn và không ép gọi `get()` không?
5. Dữ liệu ngày giờ đã phân biệt rõ `LocalDate`, `LocalDateTime`, `Instant` và `ZoneId` chưa?
6. Future có executor, xử lý lỗi, timeout và điểm chờ rõ ràng không?
7. Các thao tác `Map`/`Collection` có an toàn đối với concurrency và tính mutable của dữ liệu không?

Các tính năng Java mới bổ sung thêm cách giải quyết vấn đề, nhưng nền tảng Java 8 kể trên vẫn giúp đọc hiểu và thiết kế mã ứng dụng hiện đại. Hãy ưu tiên API đúng ngữ nghĩa, khả năng bảo trì và kiểm chứng bằng thử nghiệm thực tế.

### Tài liệu API chính thức

- [Stream, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Optional, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html)
- [java.time, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/package-summary.html)
- [CompletableFuture, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [java.util.function, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/package-summary.html)
