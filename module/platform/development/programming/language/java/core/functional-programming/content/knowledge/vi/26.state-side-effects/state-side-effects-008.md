# Tách việc biến đổi dữ liệu khỏi gửi thông báo, ghi tệp hoặc cập nhật hệ thống

## 1. Vấn đề: biến đổi dữ liệu và tác dụng phụ là hai trách nhiệm khác nhau

Trong lập trình hàm (*functional programming*) với Java, một nguyên tắc thiết kế quan trọng là **tách phần tính toán giá trị mới khỏi những hành động làm thay đổi thế giới bên ngoài**. Đây là khác biệt giữa:

- **Biến đổi dữ liệu:** chuẩn hóa đầu vào, xác thực, lọc, tính toán, nhóm, sắp xếp, tạo báo cáo hoặc tạo một yêu cầu cập nhật chưa được thực thi.
- **Tác dụng phụ (*side effect*):** gửi email/SMS, ghi tệp, cập nhật database, gọi API, ghi message vào broker, sửa biến toàn cục, in console, hoặc thay đổi trạng thái object dùng chung.

Ví dụ một danh sách đơn hàng cần tính tổng và gửi xác nhận:

```java
// Chỉ tính dữ liệu, chưa gửi email:
List<Receipt> receipts = orders.stream()
        .map(OrderService::calculateReceipt)
        .toList();

// Thực hiện hành động ở ranh giới I/O:
for (Receipt receipt : receipts) {
    notifier.send(receipt); // Có side effect.
}
```

Đây là **mã minh họa**: `OrderService`, `Receipt`, `orders` và `notifier` là các kiểu/biến ứng dụng phải tự định nghĩa. Điểm cần hiểu là phép tính `calculateReceipt` không tự gửi email; việc gửi diễn ra **sau khi đã có kết quả cần gửi**.

Trái lại, cách viết sau trộn trách nhiệm:

```java
// Không khuyến khích trộn I/O vào mapper:
List<Receipt> receipts = orders.stream()
        .map(order -> {
            Receipt receipt = calculateReceipt(order);
            database.save(receipt);
            mailClient.send(receipt.email());
            return receipt;
        })
        .toList();
```

Đoạn trên cũng chỉ là minh họa. Nó khiến một thao tác được đặt tên như “ánh xạ dữ liệu” âm thầm tác động lên database và hệ thống email. Điều này làm unit test khó hơn, việc retry nguy hiểm hơn, thứ tự side effect kém rõ ràng hơn và gây vấn đề khi chuyển sang `parallelStream()` hoặc tái sử dụng mapper.

**Mục tiêu bài học:** thiết kế pipeline theo hướng **tính toán → tạo kế hoạch/giá trị → thực thi side effect có kiểm soát**, đồng thời hiểu rõ giới hạn của cách tách này: nó giúp tổ chức code và test tốt hơn, nhưng **không tự biến nhiều tác vụ I/O thành một giao dịch nguyên tử**.

## 2. Thế nào là hàm thuần và tại sao hữu ích?

Một hàm thường được gọi là **hàm thuần (*pure function*)** nếu:

1. Với cùng đầu vào và cùng các điều kiện mà nó được xác định, hàm trả cùng kết quả.
2. Nó không có side effect có thể quan sát được bên ngoài việc trả kết quả (không ghi file, không gọi hệ thống ngoài, không sửa trạng thái chia sẻ).

Ví dụ:

```java
static long lineTotal(int quantity, long unitPriceCents) {
    return Math.multiplyExact(quantity, unitPriceCents);
}
```

`lineTotal(2, 150)` trả `300`. Hàm không cập nhật database hay thay đổi đối tượng truyền vào. `Math.multiplyExact` có thể ném `ArithmeticException` nếu phép nhân overflow, nhưng **việc có thể ném exception không tự đồng nghĩa hàm có side effect**.

Ngược lại:

```java
static void sendReceipt(Receipt receipt, MailClient mailClient) {
    mailClient.send(receipt.email(), receipt.totalCents());
}
```

Đoạn này minh họa một phương thức gây side effect; kiểu `Receipt` và `MailClient` là kiểu do ứng dụng định nghĩa. Kết quả thực tế phụ thuộc dịch vụ email, mạng, quyền truy cập và trạng thái hệ thống. Khi gọi lại, có thể gửi thêm một thông báo.

### Lợi ích của việc tách

| Khía cạnh | Tính toán thuần | Thực thi side effect |
| --- | --- | --- |
| Dễ kiểm tra bằng input/output | Thường rất dễ | Cần fake/mock, test tích hợp hoặc sandbox |
| Lặp lại thao tác | Thường không làm thay đổi hệ thống | Có thể gây hành động lặp |
| Phụ thuộc thời gian/mạng/file | Không nên phụ thuộc | Thường có |
| Khả năng song song hóa | Dễ hơn khi không chia sẻ mutable state | Phải xem xét đồng thời, idempotency, thứ tự |
| Xử lý thất bại | Lỗi tính toán và validation | Lỗi I/O, timeout, partial success |
| Kết quả mong muốn | Object/record/collection mới | Thay đổi trạng thái hoặc gửi thông tin ra ngoài |

Tách hai nhóm trách nhiệm giúp hiểu chính xác **đoạn nào quyết định dữ liệu cần làm gì**, **đoạn nào chịu trách nhiệm thật sự làm**.

## 3. Thiết kế theo ba giai đoạn: chuẩn bị, lập kế hoạch, thực thi

Một cách tổ chức rõ ràng:

```text
ĐẦU VÀO
   |
   v
[1. Kiểm tra và chuẩn hóa]
   |       lỗi dữ liệu? -> báo lỗi rõ ràng
   v
[2. Biến đổi + tạo kế hoạch bất biến]
   |       PreparedOrder / Message / ReportRow / Plan
   v
========== RANH GIỚI SIDE EFFECT ==========
   |
   v
[3. Ghi file / cập nhật hệ thống / gửi thông báo]
   |       lỗi I/O? -> retry, log, bù trừ, outbox...
   v
Trạng thái thực thi / kết quả gửi
```

**Giai đoạn 1 — Kiểm tra và chuẩn hóa.** Chuyển đổi DTO, kiểm tra số lượng/đơn giá/email, xác minh thuộc tính bắt buộc. Nếu dữ liệu không hợp lệ, nên phát hiện **trước** khi tạo những tác dụng phụ khó hoàn tác.

**Giai đoạn 2 — Tạo kế hoạch.** Tính tổng đơn, tạo bản ghi báo cáo, xác định địa chỉ người nhận và nội dung cần gửi. Đầu ra là **dữ liệu mô tả công việc**, không phải kết quả gửi thành công. Với Java 17, `record` và `List.copyOf` rất thuận lợi để tạo các giá trị khó bị sửa ngoài ý muốn.

**Giai đoạn 3 — Thực thi.** Một lớp/giao diện riêng kiểm soát file, repository, email, message broker hoặc HTTP. Đây là nơi định nghĩa transaction, retry, idempotency, timeout và chiến lược xử lý lỗi.

Tên gọi có thể là `prepare`/`plan`/`execute`, `calculate`/`persist`/`notify`, hoặc tổ chức theo *functional core, imperative shell*. Không bắt buộc có đúng ba class; điều quan trọng là **ranh giới trách nhiệm rõ ràng**.

## 4. Vì sao không nên đặt `sendEmail` hoặc `writeFile` trong `map`?

`Stream.map` được thiết kế để biến mỗi phần tử thành một giá trị mới:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
```

Lý tưởng, mapper diễn đạt một phép tính:

```java
List<String> normalized = emails.stream()
        .map(String::trim)
        .map(s -> s.toLowerCase(java.util.Locale.ROOT))
        .toList();
```

Trong khi đó:

```java
List<String> risky = emails.stream()
        .map(email -> {
            notificationService.send(email);
            return email;
        })
        .toList();
```

là đoạn minh họa giả định có `emails` và `notificationService`, và trộn thao tác gửi với phép biến đổi. Có các nguy cơ:

- **Lười thực thi (*laziness*):** tạo pipeline chưa chạy mapper; side effect xảy ra khi terminal operation tiêu thụ dữ liệu.
- **Short-circuit:** khi dùng `findFirst`, `limit` hoặc các terminal short-circuit, không phải mọi phần tử đều cần được duyệt, nên không được dựa vào mapper để gửi đúng một lần cho tất cả.
- **Tối ưu hóa:** Stream API có quyền tối ưu một số trường hợp; những tác dụng phụ không phải điều kiện bắt buộc của phép toán dữ liệu có thể không xảy ra như cách ta tưởng.
- **Song song:** `parallelStream` có thể khiến mapper chạy trên các thread khác nhau; thứ tự gửi không còn là thứ tự danh sách.
- **Retry:** tính lại pipeline có thể lặp lại lời gọi gửi/ghi ngoài mong muốn.

**Phép tính trả dữ liệu** đặt trong `map`/`filter`/`reduce`; **thực thi I/O** đặt ở một điểm điều phối riêng, có thể là vòng lặp hoặc một adapter dịch vụ được gọi chủ động.

### `peek` có phải nơi thay thế để ghi log/gửi email?

`peek` là intermediate operation chủ yếu hữu ích khi quan sát/debug. Nó **không phù hợp làm nơi bắt buộc thực hiện audit, gửi email hoặc ghi database**. Số lần action của `peek` được gọi có thể phụ thuộc cách tiêu thụ stream và tối ưu của pipeline.

Ví dụ:

```java
long count = List.of("A", "B", "C").stream()
        .peek(System.out::println)
        .count();
```

Không được khẳng định ba dòng A, B, C **bắt buộc** được in trong mọi triển khai: với nguồn có kích thước biết trước, `count()` có thể lấy số lượng mà không cần thực hiện pipeline intermediate. Đây là lý do `peek` không phải cơ chế phát thông báo đáng tin cậy.

## 5. Ví dụ Java 17 hoàn chỉnh: lập kế hoạch đơn hàng rồi thực thi

Ví dụ sau cố ý **tách hai phần**:

1. Phần tính toán thuần: từ `Order` tính `PreparedOrder` và các dòng CSV.
2. Phần I/O: ghi một tệp CSV thực vào tệp tạm; mô phỏng cập nhật hệ thống và gửi thông báo bằng bộ thực thi test có log sự kiện.

Chương trình mô phỏng lỗi gửi email ở đơn A02, cho thấy **những tác dụng phụ trước lỗi vẫn tồn tại**. Sau đó chạy lại để minh họa cơ chế tránh lặp trong phạm vi tiến trình của bản demo. Đây không phải bản triển khai gửi email/database thật.

Tạo tệp **`SeparateEffectsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;

public class SeparateEffectsDemo {
    record Line(String sku, int quantity, int unitCents) {}

    record Order(String id, String email, List<Line> lines) {
        Order {
            lines = List.copyOf(lines);
        }
    }

    record PreparedOrder(String id, String email, long totalCents) {}

    record Plan(List<PreparedOrder> items, List<String> csvLines) {
        Plan {
            items = List.copyOf(items);
            csvLines = List.copyOf(csvLines);
        }
    }

    // Pure: kiểm tra dữ liệu và tính tổng. Không ghi I/O.
    static PreparedOrder prepare(Order order) {
        long total = order.lines().stream()
                .mapToLong(line -> {
                    if (line.quantity() <= 0 || line.unitCents() < 0) {
                        throw new IllegalArgumentException("invalid line");
                    }
                    return Math.multiplyExact(
                            (long) line.quantity(), line.unitCents());
                })
                .reduce(0L, Math::addExact);

        return new PreparedOrder(order.id(), order.email(), total);
    }

    // Pure: lập kế hoạch từ dữ liệu, không gửi/ghi gì.
    static Plan buildPlan(List<Order> orders) {
        List<PreparedOrder> prepared = orders.stream()
                .map(SeparateEffectsDemo::prepare)
                .toList();

        List<String> csv = Stream.concat(
                Stream.of("orderId,totalCents"),
                prepared.stream()
                        .map(p -> p.id() + "," + p.totalCents()))
                .toList();

        return new Plan(prepared, csv);
    }

    // Lớp thực thi side effect chỉ dành cho ví dụ.
    static final class DemoEffects {
        private final Path report;
        private final List<String> events = new ArrayList<>();
        private final Set<String> updated = new HashSet<>();
        private final Set<String> mailed = new HashSet<>();
        boolean failMailA02 = true;

        DemoEffects(Path report) {
            this.report = report;
        }

        void writeReport(Plan plan) throws IOException {
            Files.writeString(
                    report,
                    String.join("\n", plan.csvLines()) + "\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);
            events.add("FILE written");
        }

        void updateSystem(PreparedOrder item) {
            // Fake repository: không gọi database thật.
            if (updated.add(item.id())) {
                events.add("DB " + item.id());
            } else {
                events.add("DB skip " + item.id());
            }
        }

        void sendNotification(PreparedOrder item) {
            // Fake mail service: giả lập lỗi tại A02.
            if (item.id().equals("A02") && failMailA02) {
                events.add("MAIL failed A02");
                throw new IllegalStateException("mail offline");
            }
            if (mailed.add(item.id())) {
                events.add("MAIL " + item.id());
            } else {
                events.add("MAIL skip " + item.id());
            }
        }

        void execute(Plan plan) throws IOException {
            writeReport(plan);
            for (PreparedOrder item : plan.items()) {
                updateSystem(item);
                sendNotification(item);
            }
        }

        List<String> events() {
            return List.copyOf(events);
        }
    }

    public static void main(String[] args) throws IOException {
        List<Order> orders = List.of(
                new Order("A01", "lan@example.test", List.of(
                        new Line("BOOK", 2, 150),
                        new Line("PEN", 1, 50))),
                new Order("A02", "minh@example.test", List.of(
                        new Line("BAG", 1, 800)))
        );

        Plan plan = buildPlan(orders);
        List<String> totals = plan.items().stream()
                .map(p -> p.id() + "=" + p.totalCents())
                .toList();

        System.out.println("Prepared: " + totals);
        System.out.println("CSV rows planned: " + plan.csvLines().size());

        // File tạm chỉ được tạo ở ranh giới side effect.
        Path report = Files.createTempFile("orders-demo-", ".csv");
        try {
            DemoEffects effects = new DemoEffects(report);
            System.out.println("Before execute: " + effects.events());

            try {
                effects.execute(plan);
            } catch (IllegalStateException ex) {
                System.out.println("First error: " + ex.getMessage());
            }

            System.out.println("Events after failure: " + effects.events());
            System.out.println("File rows: "
                    + Files.readAllLines(report, StandardCharsets.UTF_8));

            // Khôi phục mail giả lập rồi thực thi lại kế hoạch.
            effects.failMailA02 = false;
            effects.execute(plan);
            System.out.println("Events after retry: " + effects.events());
        } finally {
            Files.deleteIfExists(report);
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac --release 17 SeparateEffectsDemo.java
java SeparateEffectsDemo
```

**Stdout dự kiến:**

```text
Prepared: [A01=350, A02=800]
CSV rows planned: 3
Before execute: []
First error: mail offline
Events after failure: [FILE written, DB A01, MAIL A01, DB A02, MAIL failed A02]
File rows: [orderId,totalCents, A01,350, A02,800]
Events after retry: [FILE written, DB A01, MAIL A01, DB A02, MAIL failed A02, FILE written, DB skip A01, MAIL skip A01, DB skip A02, MAIL A02]
```

### Giải thích chi tiết ví dụ

**Bước tính toán.** `prepare` duyệt các `Line` và tính `quantity * unitCents` bằng `Math.multiplyExact`, sau đó cộng bằng `Math.addExact`. A01 có 2 × 150 + 1 × 50 = **350** cent; A02 có 1 × 800 = **800** cent. Nếu có số lượng không dương hoặc đơn giá âm, `IllegalArgumentException` xuất hiện trước khi tạo bản kế hoạch thành công. Việc kiểm tra chỉ có ý nghĩa khi có quy tắc nghiệp vụ tương ứng; ví dụ này chấp nhận đơn giá 0 để minh họa một mặt hàng miễn phí.

**Bước lập kế hoạch.** `buildPlan` tạo hai `PreparedOrder` và ba dòng CSV gồm một dòng header. Cả `Order` lẫn `Plan` sao chép danh sách trong constructor, nên cấu trúc danh sách không bị sửa qua tham chiếu bên ngoài. Đây là kế hoạch **dữ liệu**, chưa gọi repository hoặc mail service.

**Bước ghi file.** `DemoEffects.execute` gọi `writeReport`. Đoạn `Files.writeString` ghi UTF-8 vào tệp tạm có sẵn và thay nội dung cũ bằng các dòng CSV, với newline cố định `\n`. `Files.readAllLines` ở cuối dùng để chứng minh tệp thật đã được ghi; tên file tạm không được in nên stdout độc lập với đường dẫn của máy. Khối `finally` xóa tệp tạm sau demo.

**Bước cập nhật và thông báo.** `updateSystem`, `sendNotification` chỉ **mô phỏng** database và mail bằng `Set`/`List` trong bộ nhớ. Chúng không truy cập hệ thống thật. Sau khi A01 thành công, A02 được đánh dấu DB đã cập nhật nhưng mail giả lập lỗi, nên chuỗi dừng. Log chứng minh side effect đã xảy ra không tự bị rollback.

**Retry có tránh lặp trong demo.** Khi bật lại khả năng gửi cho A02 và chạy `execute` lần nữa, việc ghi tệp lặp nhưng có cùng nội dung; các `Set` lưu ID đã cập nhật hoặc đã gửi giúp bỏ qua lần thứ hai cho những phần đã thành công. Do đó A01 không bị “gửi lại” trong log, còn A02 được gửi lần đầu sau lỗi.

**Giới hạn mô phỏng:** bộ `Set` chỉ tồn tại trong một instance Java và **không đủ để bảo đảm idempotency của hệ thống thật**. Nếu ứng dụng restart, có nhiều instance hoặc một yêu cầu gửi thành công nhưng client bị timeout trước khi nhận kết quả, cần cơ chế bền vững như idempotency key, unique constraint, outbox, trạng thái gửi và deduplication theo hợp đồng dịch vụ.

Chương trình không dựa vào thứ tự iteration của `HashSet`; thứ tự sự kiện được lưu bằng `ArrayList` tuần tự và đầu ra luôn duyệt `List.of` của đầu vào. Tệp CSV chỉ có mã đơn và tổng số cent số nguyên, nên không cần xử lý quoting phức tạp. Trong ứng dụng có dấu phẩy, xuống dòng, quote trong trường CSV hoặc mã không đáng tin, cần dùng escaping/CSV library đúng tiêu chuẩn.

## 6. Vì sao ghi tệp, gửi email hoặc cập nhật DB phải có một “điểm vào” rõ ràng?

Phương thức điều phối rõ nghĩa hơn:

```java
Plan plan = buildPlan(orders);
effects.execute(plan);
```

Nó giúp phân biệt:

- `buildPlan` có thể chạy trong unit test mà không cần file system/database/email.
- `execute` có thể kiểm thử riêng bằng fake effects hoặc test tích hợp.
- Người đọc biết chính xác **lúc nào bắt đầu có side effect**.
- Việc kiểm tra quyền truy cập, retry, transaction và audit tập trung ở tầng I/O.
- Có thể hiển thị *preview* hoặc *dry run* từ Plan trước khi thực thi thật.

Nếu viết `map(order -> { mail.send(...); db.save(...); return ...; })`, người đọc phải xem kỹ từng mapper để biết I/O diễn ra ở đâu. Điều này làm khó việc đánh giá một pipeline có an toàn để chạy song song, dừng sớm hoặc chạy lại hay không.

### Mô hình “functional core, imperative shell”

Đây là cách gọi phổ biến của cách tách:

```text
+---------------------------------------------------+
| FUNCTIONAL CORE                                    |
| validate -> normalize -> calculate -> build Plan  |
| trả giá trị mới, không chạm database/email/file    |
+---------------------------------------------------+
                      |
                      v
+---------------------------------------------------+
| IMPERATIVE SHELL                                   |
| load inputs -> call core -> persist -> notify     |
| xử lý I/O, giao dịch, retry, monitoring, timeout  |
+---------------------------------------------------+
```

Không cần hiểu core là một framework khác. Nó có thể chỉ là vài `static` method, record và service Java thông thường. Mục tiêu là **giảm số vị trí trong chương trình có thể làm thay đổi hệ thống**.

## 7. Đừng nhầm bất biến danh sách với tính thuần của pipeline

`Stream.toList()` trên Java 16+ trả về một danh sách không cho sửa cấu trúc. Nhưng việc trả unmodifiable list **không biến một mapper có side effect thành hàm thuần**:

```java
List<Receipt> result = orders.stream()
        .map(order -> {
            notification.send(order);
            return calculateReceipt(order);
        })
        .toList();
```

Đoạn mã minh họa vẫn gửi thông báo trong `map`, bất kể list kết quả có thể sửa hay không.

Ngược lại, một danh sách mutable được tạo ra **cục bộ trong hàm** rồi trả về bản bất biến có thể là một triển khai thuần, miễn việc tính toán không thay đổi trạng thái bên ngoài. “Không mutate gì cả” không phải điều kiện duy nhất; điều quan trọng là **không có tác dụng phụ có thể quan sát được vượt quá giá trị trả về**, và giữ đầu vào ổn định.

### `record` và `List.copyOf` chỉ bảo vệ một phần

`record` giúp biểu đạt dữ liệu theo giá trị và có field `final`, nhưng một record chứa tham chiếu tới object mutable vẫn có thể quan sát thay đổi trong object ấy. `List.copyOf` sao chép **cấu trúc list** và không cho sửa cấu trúc, nhưng không tự deep-copy mọi phần tử.

Trong ví dụ đầy đủ, `Order` chứa `Line` là record chỉ có `String`/`int`, `PreparedOrder` cũng là record chứa `String`/`long`; với dữ liệu như vậy, thiết kế có tính bất biến thực tế tốt hơn. Nếu trường nào là `Date` mutable, `ArrayList` hoặc object mutable khác, cần bổ sung defensive copy và chính sách ownership.

## 8. Có nên dùng `forEach` để gửi thông báo không?

`forEach` là terminal operation nhận `Consumer`:

```java
plan.items().stream()
        .forEach(item -> notifier.send(item));
```

Đây là đoạn minh họa. Nó **có thể phù hợp** khi ranh giới side effect đã rõ và bạn chủ động muốn gọi một action trên từng item. Nhưng phải hiểu:

- `Stream.forEach` là terminal, không trả dữ liệu kết quả.
- Nếu dùng `parallelStream().forEach`, thứ tự gửi không được bảo đảm và các hành động có thể chạy đồng thời.
- Nếu action ném exception, pipeline truyền lỗi ra; với pipeline song song, các action khác có thể đã chạy.
- `forEach` không cung cấp transaction/retry/idempotency hay quản lý timeout.
- Nếu cần dừng ngay khi một bước lỗi, xác định rõ chương trình đang chạy **tuần tự**.

Vòng `for` trong `DemoEffects.execute` phù hợp vì người đọc thấy rõ thứ tự nghiệp vụ `ghi báo cáo → cập nhật A01 → gửi A01 → cập nhật A02 → gửi A02`. Không có quy tắc bắt buộc phải thay mọi vòng lặp bằng Stream. **Functional programming không có nghĩa là cấm `for` hay `try/catch`.**

### `forEachOrdered` có giải quyết mọi vấn đề thứ tự không?

`forEachOrdered` đảm bảo action theo encounter order nếu nguồn ordered, kể cả ở parallel stream, nhưng **không biến các thao tác bên ngoài thành transaction**, không tự chống gửi trùng và không buộc tất cả phép tính upstream chạy tuần tự. Nếu nhiều sự kiện nghiệp vụ có phụ thuộc nhau, một vòng lặp tuần tự đơn giản có thể dễ kiểm toán hơn.

## 9. Tránh dùng `peek` để làm audit bắt buộc

Một phản ví dụ:

```java
long total = orders.stream()
        .peek(order -> audit.log("Processing " + order.id()))
        .mapToLong(Order::amount)
        .sum();
```

Đoạn minh họa giả định có `orders`, `audit` và `Order::amount`. `peek` thường tiện để debug nhưng không phải nơi thích hợp để đặt audit bắt buộc. Tính lazy, short-circuit, các tối ưu pipeline và parallel processing làm giả định “một record thì có đúng một side effect” không đáng tin nếu nghiệp vụ coi audit là bắt buộc.

Nếu audit là yêu cầu quan trọng, hãy cho nó một **hành động riêng trong shell**, đi cùng transaction hoặc cơ chế ghi sự kiện đáng tin cậy tùy hệ thống. Ví dụ tạo `AuditEvent` như **dữ liệu** trong Plan, sau đó tầng I/O ghi nó theo hợp đồng.

## 10. Tách cả dữ liệu thông báo khỏi thao tác gửi

Một cách mở rộng kế hoạch:

```java
record EmailCommand(String id, String address, String subject, String body) {}

List<EmailCommand> messages = prepared.stream()
        .map(item -> new EmailCommand(
                item.id(),
                item.email(),
                "Receipt " + item.id(),
                "Total: " + item.totalCents() + " cents"))
        .toList();
```

`prepared` là `List<PreparedOrder>` minh họa. Đây là một phép biến đổi tạo **lệnh gửi ở dạng dữ liệu**, không phải lệnh đã được gửi. Tầng điều phối có thể ghi lệnh vào outbox, gửi qua notifier, áp dụng chính sách retry hoặc chọn kênh khác.

Có hai trạng thái phải phân biệt:

- `EmailCommand` đã **được tạo trong bộ nhớ**.
- Email đã **được hệ thống ngoài chấp nhận hoặc gửi thành công** theo contract của nhà cung cấp.

Chúng không tương đương. Một kế hoạch tạo thành công không nói lên email đã đến inbox; ngay cả HTTP 200 từ dịch vụ gửi cũng chưa chắc đồng nghĩa người nhận đã đọc thư.

### Lợi ích của “data as commands”

Khi “cần gửi email nào” được biểu diễn thành object:

1. Có thể hiển thị/dry-run mà không gửi thật.
2. Có thể unit test chủ đề, địa chỉ, nội dung từ input.
3. Có thể lưu outbox một cách có cấu trúc.
4. Có thể phát hiện trùng theo business key trước khi gọi dịch vụ.
5. Có thể thêm retry metadata mà không phải chạy lại toàn bộ bước tính toán.

Tuy nhiên các object command này thường có thông tin cá nhân; log, lưu trữ và truyền đi phải phù hợp với quyền truy cập, chính sách riêng tư và khả năng kiểm toán của ứng dụng.

## 11. Xử lý lỗi tính toán khác lỗi thực thi I/O

### Lỗi ở bước chuẩn bị

Ví dụ giá trị số lượng âm hoặc overflow:

```java
static long total(int quantity, int cents) {
    if (quantity <= 0 || cents < 0) {
        throw new IllegalArgumentException("invalid input");
    }
    return Math.multiplyExact((long) quantity, cents);
}
```

Lỗi có thể được phát hiện trước khi ghi file, cập nhật hệ thống hay gửi thông báo. Với input không hợp lệ, nên trả lỗi validation rõ ràng. Nếu cần kiểm tra **tất cả** bản ghi để trả danh sách lỗi, có thể biểu diễn lỗi thành Result thay vì fail-fast ngay bản ghi đầu tiên.

### Lỗi ở bước thực thi

`Files.writeString` có thể ném checked `IOException`. Email/API thường có thể lỗi timeout hoặc trả trạng thái không thành công. Ghi database có thể lỗi constraint/connection/transaction.

Một phương thức thực thi nên khai báo hoặc chuyển đổi ngoại lệ theo một hợp đồng có ý nghĩa, ví dụ:

```java
void execute(Plan plan) throws IOException {
    writeReport(plan);
    for (PreparedOrder item : plan.items()) {
        updateSystem(item);
        sendNotification(item);
    }
}
```

Đây là đoạn minh họa đúng theo các kiểu trong chương trình đầy đủ. Nếu `writeReport` ném `IOException`, các bước update/mail chưa được gọi trong lần thực thi đó. Nhưng bản thân thao tác ghi tệp **có thể đã ghi một phần** rồi mới ném; không mặc định mọi thất bại I/O xảy ra trước khi có side effect. Nếu một bước update/mail thất bại, những bước trước đó cũng có thể đã tồn tại.

### Đừng “nuốt” lỗi chỉ để pipeline tiếp tục

```java
// Không nên nuốt mọi lỗi vô điều kiện:
try {
    mail.send(message);
} catch (RuntimeException ex) {
    // bỏ qua
}
```

Đây là đoạn minh họa. Việc bỏ lỗi có thể hợp lý đối với một log phụ trợ *best effort* trong một bối cảnh được quy định, nhưng rất nguy hiểm nếu yêu cầu nghiệp vụ coi gửi/cập nhật là bắt buộc. Hãy định nghĩa rõ tình huống nào được phép bỏ qua, tình huống nào cần retry, tình huống nào phải báo thất bại.

## 12. Partial failure: tách trách nhiệm không tự bảo đảm atomicity

Giả sử bạn cần ba side effect:

```text
1. Cập nhật trạng thái đơn hàng trong database
2. Ghi báo cáo ra tệp
3. Gửi email xác nhận
```

Các bước này thường nằm ở **ba hệ thống khác nhau**. Một giao dịch database không tự rollback email đã gửi hoặc tệp đã ghi.

| Bước lỗi | Điều có thể đã xảy ra |
| --- | --- |
| Trước khi update DB | Chưa có update, nhưng bước chuẩn bị đã chạy |
| Trong lúc update DB | Có thể rollback hoặc partial result tùy transaction |
| Sau khi update DB, trước khi ghi file | DB đã thay đổi, file/email chưa thực hiện |
| Trong lúc ghi file | File có thể đã ghi một phần, DB có thể đã thay đổi |
| Sau khi ghi file, lúc gửi email | DB/file tồn tại, email chưa chắc thành công |
| Email thành công nhưng mất response | Không rõ caller đã quan sát thành công hay chưa |

Muốn có bảo đảm mạnh, cần thiết kế thêm **transaction, outbox, saga/compensation hoặc idempotency**, tùy kiến trúc. Đừng giả định chỉ dùng `Stream.toList()` hoặc “hàm thuần” là đã giải quyết bài toán phân tán.

### Transaction trong một hệ thống khác với nhiều hệ thống

Một transaction database có thể đảm bảo các thao tác **trong phạm vi transaction đó** commit hoặc rollback cùng nhau. File system và email API bên ngoài **không tự tham gia** transaction này. Vì vậy, đặt `mailClient.send` trong method `@Transactional` của một service không khiến email có thể rollback khi database rollback.

Khi cần phát sự kiện sau khi cập nhật DB một cách đáng tin, **transactional outbox** là một mô hình phổ biến:

1. Trong cùng transaction DB, cập nhật dữ liệu nghiệp vụ và thêm một bản ghi outbox.
2. Commit transaction.
3. Một worker khác đọc outbox, gửi thông điệp ra broker/email, và ghi trạng thái đã xử lý.
4. Dùng idempotency/deduplication để hạn chế tác hại của việc gửi lại.

Outbox cho phép tránh tình huống DB commit rồi tiến trình chết trước khi kịp lưu ý định gửi, nhưng **không tự biến delivery thành exactly-once thực sự trên mọi hệ thống**. Cần hiểu contract của broker/consumer và thiết kế khả năng xử lý trùng.

## 13. Idempotency: vì sao đặc biệt quan trọng khi retry?

Một hành động là **idempotent** theo nghĩa thực tế nếu lặp lại cùng một yêu cầu nhiều lần cho **cùng một kết quả trạng thái nghiệp vụ** như làm một lần, với cùng khóa định danh và điều kiện hợp đồng. Ví dụ đặt trạng thái đơn hàng thành “CONFIRMED” thường dễ thiết kế idempotent hơn hành động “tăng số lượt xác nhận thêm 1”.

Nguy cơ của retry:

```java
for (Order order : orders) {
    chargePayment(order);
    sendEmail(order);
}
```

Đây là đoạn minh họa, không định nghĩa `chargePayment` và `sendEmail`. Nếu đã trừ tiền nhưng gửi email lỗi, chạy lại toàn bộ vòng có thể **trừ tiền hai lần**. Việc tách phần tính toán thành Plan giúp thấy rõ các bước cần retry, nhưng tầng I/O vẫn phải có chính sách idempotency.

Một số kỹ thuật:

- Gán **idempotency key** ổn định cho mỗi hành động nghiệp vụ (`orderId + operationType + version`), không tạo khóa mới ngẫu nhiên ở mỗi lần retry.
- Dùng **unique constraint** hoặc trạng thái transaction bền vững để từ chối cập nhật trùng.
- Lưu trạng thái **pending/sent/failed** có kiểm soát để biết bước nào có thể tiếp tục.
- Với hệ thống ngoài, dùng idempotency API nếu nhà cung cấp hỗ trợ.
- Với báo cáo tệp, cân nhắc ghi tệp tạm rồi **atomic move** nếu file system hỗ trợ và yêu cầu xuất bản nguyên khối; kiểm tra lỗi/đường dẫn và khả năng chạy lại.

Trong `SeparateEffectsDemo`, hai `Set` chỉ chứng minh ý tưởng “đã thực hiện thì bỏ qua lần sau” trong **một lần chạy**, không thay cho lưu bền vững và xử lý đồng thời của hệ thống thật.

## 14. Ghi tệp: dữ liệu CSV trước, thao tác I/O sau

Việc tạo nội dung báo cáo có thể là một phép biến đổi thuần:

```java
List<String> rows = prepared.stream()
        .map(p -> p.id() + "," + p.totalCents())
        .toList();
```

Nhưng việc ghi các dòng đó ra file là side effect:

```java
Files.writeString(
        path,
        String.join("\n", rows) + "\n",
        StandardCharsets.UTF_8);
```

Các đoạn này là minh họa, cần khai báo `prepared`, `path` và import thích hợp. Nhờ tách rời:

- Có thể unit test định dạng CSV mà không động đến file system.
- Có thể kiểm tra preview và xác nhận dữ liệu trước ghi.
- Có thể thay CSV bằng JSON mà không đổi tầng ghi file.
- Có thể chọn chính sách ghi đè, append hoặc đổi tên file ở tầng I/O.
- Có thể thử lỗi quyền truy cập, hết dung lượng hoặc thiếu thư mục ở test tích hợp.

**Tránh ghi vào file từ `Stream.map` rồi trả lại phần tử**: cách ấy vừa làm pipeline khó kiểm thử, vừa có rủi ro tài nguyên và khó kiểm soát ghi từng phần. Nếu cần hiệu năng streaming đối với file rất lớn không thể giữ hết trong RAM, vẫn có thể tách “hàm tạo bản ghi” khỏi “hàm ghi”, rồi dùng một vòng xử lý có quản lý `BufferedWriter`/`try-with-resources` rõ ràng. Tách trách nhiệm **không buộc phải materialize mọi dữ liệu vào một List khổng lồ**.

### Tệp lớn: ranh giới thuần vẫn tồn tại trong quá trình streaming

```java
try (BufferedWriter writer = Files.newBufferedWriter(path, UTF_8)) {
    for (Order order : orders) {
        PreparedOrder prepared = prepare(order); // Tính dữ liệu.
        writer.write(renderCsv(prepared));        // I/O.
        writer.newLine();
    }
}
```

Đây là **ví dụ thành phần** cần có `orders`, `prepare`, `renderCsv`, `path` cùng import, không phải chương trình độc lập. Dù vòng lặp xử lý theo dòng, hai trách nhiệm vẫn là hai phương thức tách biệt. Cần xác định xử lý lỗi và tính nguyên tử tệp riêng.

## 15. Gửi thông báo: chuẩn bị thông điệp trước khi dispatch

Không nên trộn format message với transport:

```java
// Không nên gộp cả tạo message và transport trong mapper:
orders.stream().map(order -> {
    String body = formatReceipt(order);
    mailClient.send(order.email(), body);
    return body;
});
```

Đoạn này còn **không có terminal operation**: chỉ dựng pipeline nên hành động gửi có thể chưa diễn ra. Điều đó dễ tạo bug vì người đọc nhầm đã gửi.

Cách tách:

```java
List<EmailCommand> commands = orders.stream()
        .map(this::buildEmailCommand)
        .toList();

for (EmailCommand command : commands) {
    mailClient.send(command);
}
```

Hai đoạn là mã minh họa với các tên kiểu/biến do ứng dụng định nghĩa. Bước đầu quyết định *gửi gì/cho ai*; bước sau quyết định *gửi bằng gì, thử lại hay báo lỗi ra sao*. Việc tách còn giúp thay mail service mà không động đến quy tắc tính tiền.

## 16. Cập nhật hệ thống: tạo ý định cập nhật và áp dụng riêng

Ví dụ từ trạng thái mới tính được:

```java
record UpdateCommand(String orderId, String newStatus) {}

List<UpdateCommand> updates = orders.stream()
        .filter(this::eligibleForConfirmation)
        .map(order -> new UpdateCommand(order.id(), "CONFIRMED"))
        .toList();
```

`eligibleForConfirmation` và `Order` là code miền nghiệp vụ minh họa. `updates` chỉ là **dữ liệu**, chưa cập nhật DB.

Bước side effect:

```java
for (UpdateCommand update : updates) {
    repository.apply(update);
}
```

Tầng repository chịu trách nhiệm transaction, optimistic locking, unique constraint, audit và lỗi kết nối. Nếu có nhiều cập nhật phải commit cùng nhau, cân nhắc batch transaction **trong một ranh giới DB rõ ràng**, thay vì hy vọng vòng lặp mặc định nguyên tử.

Nếu bản thân việc tính status phụ thuộc dữ liệu thay đổi đồng thời trong database, không thể giả định Plan đã tính từ đầu luôn còn hợp lệ khi thực thi. Có thể cần **version**, **compare-and-set**, optimistic locking hoặc transaction kiểm tra lại điều kiện trước khi commit.

## 17. Kiểm thử: chia thành unit test thuần và integration test cho I/O

### Kiểm thử hàm biến đổi

`prepare` và `buildPlan` có thể kiểm tra bằng cách so sánh dữ liệu:

```java
Plan plan = buildPlan(input);

assertEquals(2, plan.items().size());
assertEquals(350L, plan.items().get(0).totalCents());
assertEquals("orderId,totalCents", plan.csvLines().get(0));
```

Đây là **mã kiểm thử minh họa**, `assertEquals` cần JUnit hoặc thư viện assert tương ứng, `input` cần dữ liệu test và các kiểu như ở chương trình. Test thuần không cần mock email/database/file.

### Kiểm thử tầng thực thi bằng fake

Thay một email service thật bằng fake ghi các lời gọi:

```java
interface Notifier {
    void send(String address, String body);
}

final class RecordingNotifier implements Notifier {
    final List<String> sent = new ArrayList<>();
    @Override
    public void send(String address, String body) {
        sent.add(address + ":" + body);
    }
}
```

Đây là đoạn **định nghĩa kiểu** trong test hoặc file Java phù hợp, cần import `List`/`ArrayList`. Tầng thực thi gọi `Notifier` qua dependency injection hoặc constructor. Unit test có thể xác minh “gửi cho đúng người, một lần trong kịch bản đã cho” mà không gửi thư thật.

### Integration test

Với tầng I/O, nên kiểm thử thêm:

- File được tạo tại path được phép, nội dung đúng encoding/format, được đóng tài nguyên và có chính sách ghi đè/append.
- DB commit/rollback theo yêu cầu, các trường hợp optimistic lock và unique constraint.
- Email/broker trả lỗi timeout hoặc 429/5xx, cách retry/backoff và giới hạn số lần.
- Điều gì xảy ra nếu tiến trình dừng **sau khi DB commit nhưng trước khi gửi**.
- Idempotency khi một request bị gửi lại hoặc hai worker thực thi đồng thời.
- Quản lý thông tin nhạy cảm: dữ liệu khách hàng không bị log tùy tiện.

Không nên để test thông thường gửi email thật hoặc cập nhật DB sản xuất.

## 18. Đọc đúng vai trò của `Function` và `Consumer`

`Function<T,R>` biểu diễn một thao tác nhận T trả R; `Consumer<T>` nhận T trả `void`. Điều này gợi ý:

```java
Function<Order, PreparedOrder> transform =
        SeparateEffectsDemo::prepare;

Consumer<PreparedOrder> deliver =
        item -> notifier.send(item);
```

Đây là đoạn minh họa với `notifier` có sẵn trong scope. `transform` thích hợp để diễn đạt phép tính, `deliver` thường diễn đạt side effect. Tuy nhiên:

**Chỉ vì một lambda có kiểu `Function` không có nghĩa nó thuần.** Bạn vẫn có thể viết một Function sửa biến chung hoặc gửi email rồi trả kết quả. Ngược lại, một `Consumer` có thể không có side effect quan sát được (ví dụ thân rỗng). Tính thuần là thuộc tính **hành vi thực tế**, không do tên interface đảm bảo.

### `andThen` và thứ tự side effect

`Consumer.andThen` ghép hai hành động:

```java
Consumer<PreparedOrder> save = repository::save;
Consumer<PreparedOrder> notify = notifier::send;

Consumer<PreparedOrder> workflow = save.andThen(notify);
```

Đoạn này giả định `repository`/`notifier` với chữ ký tương ứng. Nếu `save.accept` ném exception, `notify.accept` không chạy. Nếu `save` thành công rồi `notify` ném, phần lưu trước đó **không tự rollback**. `andThen` thuận tiện cho thứ tự thao tác nhưng không thay thế một tầng điều phối có transaction/idempotency/compensation.

## 19. Parallel stream và các hành động không an toàn

Một pipeline biến đổi không có trạng thái chia sẻ thường dễ chạy song song hơn:

```java
List<PreparedOrder> prepared = orders.parallelStream()
        .map(SeparateEffectsDemo::prepare)
        .toList();
```

Với nguồn ordered như `List`, `toList()` giữ encounter order. Nhưng Java không cam kết mapper chạy theo thứ tự đó hoặc trên cùng thread. Hàm `prepare` không cập nhật trạng thái dùng chung, giúp giảm nguy cơ race.

Ngược lại:

```java
orders.parallelStream()
        .forEach(order -> mailClient.send(order.email()));
```

là một thao tác I/O song song có thể xảy ra đồng thời, không bảo đảm thứ tự gửi. Ngoài thread safety của mail client, còn phải xét rate limit, giới hạn kết nối, retry, idempotency và thời gian xử lý. **Không mặc định dùng parallel stream cho I/O**; cân nhắc executor, queue, batch worker hoặc asynchronous API được thiết kế riêng với backpressure và giám sát.

Nếu cần một thứ tự giao dịch cố định, dùng tầng điều phối rõ ràng; `forEachOrdered` chỉ ràng buộc thứ tự action theo encounter order, không biến các tác động bên ngoài thành giao dịch chung.

## 20. Tình huống cần quyết định thiết kế

| Tình huống | Thiết kế nên cân nhắc |
| --- | --- |
| Chỉ lọc, chuẩn hóa tên khách hàng | `map`/`filter` thuần và `toList` |
| Tạo CSV nhưng chưa cần ghi tệp | Trả các dòng/bản ghi report như dữ liệu |
| Ghi file lớn theo dòng | Hàm render thuần + vòng I/O có `try-with-resources` |
| Tính nội dung email | Trả `EmailCommand`, không gửi ở mapper |
| Email phải được gửi sau khi DB commit | DB transaction + outbox/dispatcher phù hợp |
| Cập nhật DB và gọi REST API | Điều phối side effect, timeout, idempotency, error handling |
| Cần xem trước thay đổi | Tính `Plan` rồi hiển thị preview/dry-run |
| Một bản ghi dữ liệu sai | Validation trước side effect hoặc Result chứa lỗi |
| Gửi thất bại giữa chừng | Lưu trạng thái, retry có chọn lọc, không gọi lại hành động đã commit tùy tiện |
| Nhiều worker xử lý song song | Idempotency key, concurrency control và giới hạn tải |

Cách chọn cụ thể còn phụ thuộc yêu cầu nhất quán, khối lượng dữ liệu, loại nguồn/đích và khả năng chấp nhận gửi lặp.

## 21. Những lỗi phổ biến

**Lỗi 1 — Gửi thông báo trong `map` hoặc `filter`.** Pipeline dữ liệu bị gắn với I/O; khi đổi terminal hoặc parallel hóa có thể làm hành vi thay đổi. Hãy tạo command/plan trước và gửi ở ranh giới riêng.

**Lỗi 2 — Dùng `peek` làm audit bắt buộc.** `peek` không có hợp đồng luôn được chạy cho mọi phần tử nếu terminal không yêu cầu. Audit phải có cơ chế đảm bảo phù hợp.

**Lỗi 3 — Nghĩ `toList` chạy pipeline là đã “lưu đơn”.** `toList` thu thập **giá trị trong bộ nhớ**, không tự ghi DB hay gửi email.

**Lỗi 4 — Nghĩ tách hàm thuần thì rollback tự động.** Việc tách nâng cao khả năng kiểm thử nhưng các side effect đã thực hiện vẫn có thể tồn tại khi bước sau lỗi.

**Lỗi 5 — Retry cả kế hoạch mà không có idempotency.** Có thể gửi trùng, trừ tiền hai lần hoặc append nội dung file trùng.

**Lỗi 6 — Tạo bản kế hoạch rồi ngầm cho rằng mọi điều kiện không đổi tới lúc commit.** Dữ liệu ngoài có thể thay đổi; dùng version/transaction/validation khi thực thi nếu cần.

**Lỗi 7 — Dùng shared `ArrayList` để thu thập từ `parallelStream().forEach`.** Có nguy cơ race; dùng collector hoặc `toList` cho kết quả dữ liệu.

**Lỗi 8 — Giấu lỗi I/O trong lambda bằng `catch (Exception ignored)`.** Tầng gọi không biết có thất bại, gây trạng thái không nhất quán. Cần hợp đồng lỗi rõ.

**Lỗi 9 — Cho rằng record/list unmodifiable làm toàn bộ object graph immutable.** Object mutable lồng bên trong vẫn có thể đổi; xem xét defensive copy và ownership.

**Lỗi 10 — Đưa tệp/email/database thật vào unit test tính toán.** Test chậm, không ổn định, rủi ro làm thay đổi dữ liệu bên ngoài. Dùng fake cho orchestration và test tích hợp riêng.

**Lỗi 11 — Dùng transaction database để suy ra email cũng được rollback.** Giao dịch không tự kéo theo hệ thống ngoài; dùng outbox/compensation khi cần.

**Lỗi 12 — Xem thành công khi gọi mail API là đã được người nhận đọc.** Cần phân biệt mức độ xác nhận delivery theo contract dịch vụ.

**Lỗi 13 — Đồng thời hóa I/O mà chưa tính giới hạn tải.** Có thể vượt rate limit, hết connection hoặc tạo hàng đợi retry lớn; thiết kế concurrency và backpressure rõ.

**Lỗi 14 — Thu thập hàng triệu đối tượng chỉ để ghi tuần tự tệp lớn.** Không nhất thiết materialize toàn bộ dataset: tách mapper thuần và writer có tài nguyên rõ ràng vẫn có thể xử lý theo dòng.

## 22. Bài tập thực hành

1. Viết hàm `static String normalizeEmail(String email)` chỉ trim/lowercase bằng `Locale.ROOT`. Giải thích tại sao nó có thể kiểm thử mà không cần mail service.
2. Từ `List<Order>`, tạo `List<PreparedOrder>` bằng `map`, tính tổng bằng `Math.addExact` và không ghi hệ thống nào. Kiểm tra đầu ra với đơn A01/A02 ở `SeparateEffectsDemo`.
3. Thiết kế `record EmailCommand(String orderId,String email,String body)`. Dùng `map` tạo danh sách command rồi viết một vòng dispatch ở tầng riêng.
4. Chuyển đoạn `orders.stream().map(order -> { repository.save(order); return order.id(); }).toList()` thành hai phần: tính ID thuần và lưu qua service riêng. Nêu ích lợi và rủi ro của thứ tự thực thi.
5. Dùng fake `Notifier` ghi nhận các lần gọi, test rằng A01 có đúng một yêu cầu gửi trong kịch bản thành công.
6. Giả lập việc gửi A02 thất bại sau khi A01 đã được cập nhật. Ghi lại trạng thái còn lại và giải thích vì sao không được gọi lại mọi bước vô điều kiện.
7. Thêm một `ReportRow` record và hàm `toCsvRow(PreparedOrder)` thuần. Viết unit test kiểm tra chuỗi có đúng mã và tổng tiền, không đụng filesystem.
8. Ghi báo cáo vào file tạm bằng `try/finally` hoặc `try-with-resources`, đọc lại và xóa sau test. Kiểm tra trường hợp file không thể ghi và chính sách lỗi.
9. Thiết kế một `UpdateCommand(orderId,status,version)` để kiểm tra optimistic locking ở tầng repository. Tại sao validation lúc lập Plan chưa đủ?
10. So sánh chạy `orders.parallelStream().map(this::prepare).toList()` với `orders.parallelStream().forEach(mailClient::send)`. Pipeline nào thường dễ bảo đảm thread-safe hơn và vì sao?
11. Tạo một pipeline chỉ dùng `peek` để ghi audit rồi gọi `count()`. Giải thích vì sao audit có thể không được phát như kỳ vọng.
12. Viết phác thảo transactional outbox: trong một transaction, cập nhật đơn và ghi `OutboxEvent`; worker khác gửi email. Nêu cách chống gửi trùng khi worker crash sau gửi.
13. Với dữ liệu quá lớn để giữ toàn bộ trong RAM, thiết kế cách sử dụng hàm `renderCsv` thuần cùng `BufferedWriter` ở tầng I/O.
14. Lập danh sách các side effect của một chức năng gửi hóa đơn: email, tệp, DB, metrics, logs, message broker; xác định hành động nào bắt buộc, hành động nào best effort và thứ tự cần thiết.

## 23. Checklist trước khi đưa vào dự án

- Có phân biệt rõ **giá trị cần tạo** với **hành động cần thực thi** không?
- Có mapper hoặc predicate nào lén gọi file, database, email, HTTP API hay sửa state ngoài không?
- Dữ liệu đầu vào đã validate đủ trước những side effect khó hoàn tác chưa?
- Có thể unit test phần tính toán chỉ qua input/output không?
- Có `Plan`, `EmailCommand`, `UpdateCommand` hoặc cấu trúc tương đương để preview trước khi gửi không?
- Có định nghĩa rõ vị trí bắt đầu và thứ tự các side effect trong shell không?
- Khi lỗi xảy ra giữa chuỗi, những bước nào đã có hiệu lực và có thể retry bước nào?
- Với DB/file/email nhiều hệ thống, đã xử lý **partial failure** thay vì ngầm giả định một transaction chung chưa?
- Các thao tác lặp lại đã có idempotency key và cơ chế lưu bền vững phù hợp chưa?
- Nếu dùng parallel, các mapper có tránh shared mutable state và tầng I/O có giới hạn concurrency không?
- Các tài nguyên I/O đã được đóng đúng; file có chính sách ghi đè/append và đồng bộ hợp lý chưa?
- Có phân biệt **test tính toán**, **test orchestration với fake**, và **integration test hệ thống ngoài** không?

**Kết luận:** Hãy dùng `map`/`filter`/`reduce` để **tính dữ liệu và tạo kế hoạch**, rồi dùng một tầng điều phối có tên gọi, hợp đồng lỗi và trách nhiệm rõ để **ghi tệp, gửi thông báo hoặc cập nhật hệ thống**. Cách tách này giữ phần lớn logic nghiệp vụ dễ hiểu, dễ kiểm thử và dễ tái sử dụng, đồng thời phơi bày những vấn đề I/O thực tế — idempotency, transaction, concurrency và partial failure — ở đúng nơi cần giải quyết.
