# Tách các bước gọi dịch vụ và ghi dữ liệu khỏi phép biến đổi thuần

## 1. Bài toán: kết quả đúng chưa đủ nếu tác dụng phụ không kiểm soát được

Trong module **JAVA_STREAM_API**, chúng ta học cách xử lý dữ liệu khai báo bằng pipeline lazy với `filter`, `map`, `reduce`, `collect` và các collector. Khi phần tử chỉ là dữ liệu trong bộ nhớ, một pipeline như sau rất dễ hiểu:

```java
List<Long> amounts = orders.stream()
    .filter(Order::ready)
    .map(Order::amountCents)
    .toList();
```

Nhưng hãy tưởng tượng một yêu cầu khác:

> Đối với mỗi đơn hàng đủ điều kiện, gọi dịch vụ thanh toán, sau đó ghi biên nhận vào cơ sở dữ liệu. Nếu dịch vụ lỗi hoặc thao tác ghi thất bại, phải biết đã xử lý đến đâu và có thể thử lại mà không thu tiền hai lần.

Phiên bản tưởng như ngắn gọn:

```java
orders.parallelStream()
    .filter(Order::ready)
    .map(order -> gateway.charge(order))
    .forEach(receipt -> repository.save(receipt));
```

đã đặt **hai tác dụng phụ quan trọng** bên trong pipeline:

- `gateway.charge` có thể thực hiện giao dịch bên ngoài tiến trình.
- `repository.save` có thể ghi một bản ghi bền vững.

Một ngoại lệ xuất hiện sau khi gateway đã thu tiền **không chứng minh được giao dịch đã bị hoàn tác**. Việc thay `stream()` thành `parallelStream()` cũng có thể làm nhiều yêu cầu được gửi cùng lúc, làm thay đổi thứ tự thực thi và số giao dịch đang chạy khi phát hiện lỗi.

Trong chương **Ngoại lệ và tính an toàn**, chúng ta cần phân biệt:

1. **Biến đổi thuần**: tính ra dữ liệu mới từ dữ liệu đầu vào, không gọi dịch vụ hay ghi trạng thái ngoài.
2. **Ranh giới tác dụng phụ**: thao tác với HTTP, database, message broker, file, email hoặc các hệ thống khác.
3. **Hợp đồng thất bại**: đã thành công, chắc chắn thất bại hay kết quả **chưa xác định**.
4. **Chính sách retry và idempotency**: phát lại một yêu cầu mà không nhân đôi tác dụng không mong muốn.

Sau bài học, bạn có thể thiết kế một quy trình **lập kế hoạch bằng Stream API → kiểm tra → gọi dịch vụ có kiểm soát → ghi dữ liệu → trả báo cáo kết quả**, đồng thời chỉ rõ những bảo đảm hệ thống thật phải cung cấp ngoài Stream API.

Ví dụ chính dùng **Java 17+** và **JUnit 5**. Các ý tưởng về tính thuần, checked exception và Stream API có thể áp dụng từ Java 8, nhưng chương trình hoàn chỉnh dùng `record` và `Stream.toList()`.

## 2. Phân biệt phép biến đổi thuần, trạng thái cục bộ và tác dụng phụ

### 2.1. Phép biến đổi thuần là gì?

Một hàm được xem là **thuần** trong ngữ cảnh bài này nếu:

- Với cùng đầu vào, nó cho cùng đầu ra theo hợp đồng.
- Không làm thay đổi trạng thái có thể quan sát được bên ngoài lời gọi.
- Không đọc thời gian thực, gọi mạng, truy cập file hoặc phụ thuộc vào trạng thái thay đổi không được truyền vào.
- Không sửa đối tượng đầu vào mà phần khác của chương trình cũng đang sử dụng.

Ví dụ:

```java
record Price(long unitCents, long quantity) {}

static long lineTotal(Price price) {
    return Math.multiplyExact(
        price.unitCents(), price.quantity()
    );
}
```

Hàm nhận hai con số, tính một kết quả, không cần network hoặc database. `Math.multiplyExact` có thể ném `ArithmeticException` khi tràn số; **có thể ném lỗi không làm hàm mất tính thuần**, miễn lỗi được xác định bởi đầu vào và không gây side effect.

Phép biến đổi thuần có thể được sử dụng trong `map`:

```java
List<Long> totals = prices.stream()
    .map(MyCalculations::lineTotal)
    .toList();
```

### 2.2. Side effect là gì?

Side effect là sự thay đổi hoặc tương tác **ngoài giá trị trả về của hàm**:

| Hành động trong lambda | Thuần? | Nguy cơ |
| --- | --- | --- |
| `n -> n * 2` | Có | Chỉ cần xem tràn kiểu số nếu có |
| `order -> new Dto(order.id(), order.amount())` | Có nếu dữ liệu đầu vào ổn định | Cần tránh đưa mutable alias ra ngoài |
| `order -> Math.addExact(order.amount(), tax)` | Có nếu `tax` bất biến | Có thể ném ngoại lệ thuần |
| `order -> System.currentTimeMillis()` | Không | Kết quả phụ thuộc thời gian gọi |
| `order -> client.fetchPrice(order.sku())` | Không | I/O, timeout, trạng thái dịch vụ |
| `order -> database.insert(order)` | Không | Ghi bền vững, có thể thất bại giữa chừng |
| `order -> sharedList.add(order)` | Không | Mutable state ngoài, race trên stream song song |
| `order -> logger.info(order.id())` | Có side effect | Log có thể bị bỏ qua hoặc khác thứ tự mong đợi |
| `order -> counter.incrementAndGet()` | Không | Dù atomic, vẫn phụ thuộc số lần lambda được gọi |

**Không phải mọi mutation đều bị cấm.** Một collector có thể tạo `ArrayList` hoặc `HashMap` **cục bộ** để tích lũy kết quả rồi trả giá trị. Phép gom này có trạng thái triển khai nhưng không nhất thiết tạo side effect nghiệp vụ. Điều quan trọng là **quyền sở hữu trạng thái** và việc nó có bị chia sẻ/quan sát bên ngoài khi pipeline còn chạy hay không.

### 2.3. Đừng đồng nhất “không có I/O” với “thuần”

Một hàm dùng biến `static int counter` để tạo ID không có I/O, nhưng vẫn không thuần. Tương tự, một `map` sửa object đầu vào rồi trả nó tạo mutation mà caller có thể quan sát:

```java
// Phản ví dụ nếu OrderMutable được nơi khác chia sẻ:
// orders.stream()
//     .map(order -> {
//         order.setProcessed(true);
//         return order;
//     })
//     .toList();
```

Khi cần thêm trạng thái mới, ưu tiên tạo **record/DTO mới** từ trường nguồn thay vì sửa dữ liệu mà pipeline nhận vào.

## 3. Vì sao Stream API không phải công cụ điều phối giao dịch?

### 3.1. Pipeline lazy không bảo đảm lambda được chạy ngay khi khai báo

`filter`, `map` và `peek` là các **intermediate operations**. Chúng thường không thực thi cho tới khi một terminal operation bắt đầu:

```java
var pipeline = orders.stream()
    .map(order -> {
        System.out.println("Đang xử lý " + order.id());
        return order.id();
    });

// Chưa có terminal operation: không nên kỳ vọng đã xử lý đơn nào.
List<String> ids = pipeline.toList();
```

Điều này phù hợp cho biến đổi dữ liệu, nhưng không phải nơi diễn đạt yêu cầu “phải gửi email xác nhận ngay bây giờ” nếu chưa có một bước thực thi tường minh.

### 3.2. Short-circuit và tối ưu hóa có thể bỏ qua công việc

`limit`, `findFirst`, `anyMatch`, `noneMatch` và các cơ chế short-circuit khác có thể không xử lý mọi phần tử nguồn.

```java
// Sai nếu nghiệp vụ yêu cầu ghi mọi đơn vào audit store:
orders.stream()
    .peek(auditStore::save)
    .findFirst();
```

Khi chỉ cần phần tử đầu, các phần tử sau có thể không được duyệt. Hơn nữa, Stream implementation được phép lược bỏ một số lời gọi intermediate operation khi tối ưu hóa không làm đổi kết quả terminal; ví dụ `count()` trên nguồn có kích thước đã biết có thể không duyệt từng phần tử. `peek` không phải nơi phù hợp để gắn **hành động bắt buộc**.

### 3.3. Parallel stream không bảo đảm thứ tự thực thi side effect

`parallelStream().forEach(...)` không cam kết thứ tự gọi action theo encounter order. `forEachOrdered` giữ **thứ tự hành động** với nguồn ordered nhưng vẫn không cung cấp transaction, retry hoặc exactly-once.

```java
orders.parallelStream()
    .forEach(order -> gateway.charge(order));
// Không cam kết thứ tự giao dịch hay trạng thái các tác vụ khác khi một tác vụ lỗi.
```

Ngay cả khi chuyển thành:

```java
orders.parallelStream()
    .forEachOrdered(order -> gateway.charge(order));
```

thì Java vẫn không thể bảo đảm dịch vụ ngoài chỉ thu tiền một lần khi timeout hoặc khi tiến trình bị khởi động lại.

### 3.4. Ngoại lệ giữa pipeline không tự rollback side effect trước đó

```text
Đơn O1 -> gateway thu tiền -> ghi DB thành công
Đơn O2 -> gateway thu tiền -> ghi DB thất bại
Đơn O3 -> chưa xử lý
              │
              └── Ngoại lệ Java KHÔNG tự hoàn tác tiền O1/O2.
```

Một khối `try/catch` chỉ thay đổi luồng điều khiển **trong tiến trình**. Việc hoàn tác hoặc bù trừ giữa nhiều hệ thống là một bài toán giao dịch phân tán riêng.

## 4. Các phản mẫu phổ biến và giới hạn thực tế của `forEach`

### 4.1. Dùng `map` cho thao tác ghi

```java
// Không nên khi mục tiêu là điều phối nghiệp vụ:
var receipts = orders.stream()
    .map(gateway::charge)
    .map(repository::saveAndReturn)
    .toList();
```

Đoạn code khó diễn đạt rõ:

- Nếu `charge` thành công nhưng `saveAndReturn` lỗi, điều gì sẽ được trả?
- Có cần dừng ở đơn đầu thất bại hay xử lý các đơn khác?
- Nếu chạy lại pipeline, đơn nào có thể bị thu tiền hai lần?
- Ai ghi nhận các bước đã hoàn tất để phục hồi sau crash?

### 4.2. Dùng `peek` để ghi audit

```java
// Phản mẫu: side effect quan trọng nằm trong thao tác trung gian.
var ids = orders.stream()
    .peek(auditStore::record)
    .map(Order::id)
    .toList();
```

`peek` hữu ích để **quan sát/gỡ lỗi** trong một số trường hợp, nhưng số lần gọi và thời điểm gọi không nên trở thành hợp đồng ghi nhận dữ liệu bền vững.

### 4.3. `forEach` không phải API bị cấm tuyệt đối

`forEach` là terminal operation **được thiết kế để thực thi action**. Nó phù hợp cho các thao tác đơn giản có side effect đã được chấp nhận, ví dụ in dữ liệu minh họa:

```java
List.of("A", "B", "C").forEach(System.out::println);
```

Vấn đề không nằm ở chỗ “mọi `forEach` đều sai”, mà ở **bảo đảm nghiệp vụ mà action yêu cầu**. Nếu action ghi một giao dịch cần retry, exactly-once, audit, rollback và phân loại lỗi, một vòng lặp tường minh với các port dịch vụ/repository thường diễn đạt trách nhiệm tốt hơn.

## 5. Kiến trúc đề xuất: tách pha chuẩn bị và pha thực thi

```text
     List<Order> đầu vào đã ổn định
                 │
                 ▼
     VALIDATE (hợp đồng dữ liệu)
                 │
                 ▼
     PLAN / PURE TRANSFORMS
     filter, map, collect, kiểm tra duplicate,
     tính total với Math.addExact
                 │
                 ▼
       Plan không sửa được
       [ChargeCommand, ...]
                 │
                 ▼
      EXPLICIT EXECUTION LOOP
        ┌──────────────────────┐
        │ gateway.charge(cmd)  │
        │ receiptStore.save()  │
        └──────────────────────┘
                 │
        ┌────────┼──────────┐
        ▼        ▼          ▼
     RECORDED  CHARGE      RECORD
               UNKNOWN     FAILED
                 │
                 ▼
       ProcessReport gồm từng kết quả
```

**Pha chuẩn bị** có thể chạy nhiều lần trên cùng đầu vào mà không tạo giao dịch bên ngoài. **Pha thực thi** là nơi cấp quyền và kiểm soát các thao tác không thể đảo ngược; nó cần policy khi lỗi và idempotency.

| Pha | Có thể dùng Stream API? | Có side effect bên ngoài? | Bảo đảm mong muốn |
| --- | --- | --- | --- |
| Validate | Có hoặc vòng lặp tường minh | Không | Báo lỗi dữ liệu **trước** khi ghi |
| Prepare/Plan | Có, thường `filter/map/toList` | Không | Kết quả xác định, có thể kiểm thử |
| Authorize/Charge | Vòng lặp/service coordinator | **Có** | Gắn idempotency key, giới hạn concurrency |
| Save receipt | Repository/transaction API | **Có** | Trạng thái rõ, xử lý lỗi ghi |
| Summarize results | Có, trên kết quả đã ổn định | Không | Báo đủ thành công/thất bại/chưa rõ |

Việc tách pha **không tự tạo transaction giữa gateway và database**; nó làm vấn đề thất bại trở nên **nhìn thấy và có chỗ giải quyết**.

## 6. Thiết kế domain model và tính thuần

Mô hình đơn hàng trong ví dụ:

```java
record Order(
    String id,
    String customerId,
    long amountCents,
    boolean ready
) {}

record ChargeCommand(
    String orderId,
    String customerId,
    long amountCents,
    String idempotencyKey
) {}
```

Trong mã hoàn chỉnh, constructor sẽ validate chuỗi không trống và `amountCents > 0`. `ready` là **quy tắc nghiệp vụ**: chỉ những đơn sẵn sàng mới được đưa vào kế hoạch charge.

Không chọn idempotency key bằng `UUID.randomUUID()` mỗi khi chạy lại cùng đơn, vì retry tạo key mới có thể bị gateway xem là yêu cầu giao dịch mới. Trong ví dụ:

```java
String stableKey = "charge:v1:" + order.id();
```

Key được suy ra **ổn định** từ định danh giao dịch logic và phiên bản hành động. Đây chỉ là **quy ước minh họa**: hệ thống thật cần phân biệt tenant/merchant, loại hành động, phiên bản giao dịch, thời hạn giữ key và giới hạn namespace theo hợp đồng của nhà cung cấp.

### 6.1. Vì sao kiểm tra duplicate trước khi gọi dịch vụ?

Nếu hai bản ghi nguồn có cùng `orderId`, có thể là:

- Dữ liệu đầu vào bị lặp.
- Hai lệnh cho cùng một giao dịch logic.
- Một trường hợp hoàn toàn hợp lệ nhưng cần cách gộp riêng.

Trong bài này, **duplicate ID là lỗi**; toàn bộ input được kiểm tra trước khi thực thi. Nhờ vậy, không có tình huống đã thu tiền vài đơn rồi mới phát hiện duplicate ở cuối danh sách.

### 6.2. Trạng thái cục bộ trong `prepare` không phải side effect nghiệp vụ

Một `HashSet` cục bộ dùng để kiểm tra duplicate là trạng thái nội bộ của hàm. Nó không được trả ra hoặc chia sẻ với các thread khác; hàm vẫn có thể được xem là **thuần ở ranh giới công khai** nếu đầu vào ổn định và không sửa đầu vào.

Đừng đưa `HashSet` dùng chung vào `parallelStream().map(...)`. Phần validation có thể là vòng lặp tuần tự; vẫn bảo đảm luồng dữ liệu dễ hiểu và chính xác.

## 7. Chương trình Java 17 đầy đủ: chuẩn bị lệnh, rồi gọi gateway và lưu biên nhận

Lưu chương trình sau vào `SafeOrderProcessing.java`. Không cần framework ngoài JDK cho phần ví dụ chính; port dịch vụ/repository được mô phỏng bằng lớp in-memory.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class SafeOrderProcessing {

    private SafeOrderProcessing() {}

    public record Order(
        String id,
        String customerId,
        long amountCents,
        boolean ready
    ) {
        public Order {
            id = requireText(id, "id");
            customerId = requireText(customerId, "customerId");
            if (amountCents <= 0L) {
                throw new IllegalArgumentException(
                    "amountCents phải dương"
                );
            }
        }
    }

    public record ChargeCommand(
        String orderId,
        String customerId,
        long amountCents,
        String idempotencyKey
    ) {
        public ChargeCommand {
            orderId = requireText(orderId, "orderId");
            customerId = requireText(customerId, "customerId");
            idempotencyKey =
                requireText(idempotencyKey, "idempotencyKey");
            if (amountCents <= 0L) {
                throw new IllegalArgumentException(
                    "amountCents phải dương"
                );
            }
        }
    }

    public record Plan(
        List<ChargeCommand> commands,
        long plannedAmountCents
    ) {
        public Plan {
            commands = List.copyOf(commands);
        }
    }

    public record ChargeReceipt(
        String orderId, String receiptId
    ) {
        public ChargeReceipt {
            orderId = requireText(orderId, "orderId");
            receiptId = requireText(receiptId, "receiptId");
        }
    }

    public enum ExecutionStatus {
        RECORDED,
        CHARGE_UNCONFIRMED,
        RECEIPT_WRITE_FAILED
    }

    public record ExecutionResult(
        String orderId,
        ExecutionStatus status
    ) {}

    public record ProcessReport(List<ExecutionResult> results) {
        public ProcessReport {
            results = List.copyOf(results);
        }

        public long recordedCount() {
            return results.stream()
                .filter(r -> r.status() == ExecutionStatus.RECORDED)
                .count();
        }
    }

    public static class GatewayException extends Exception {
        public GatewayException(String message) {
            super(message);
        }
    }

    public static class StoreException extends Exception {
        public StoreException(String message) {
            super(message);
        }
    }

    @FunctionalInterface
    public interface ChargeGateway {
        ChargeReceipt charge(ChargeCommand command)
            throws GatewayException;
    }

    @FunctionalInterface
    public interface ReceiptStore {
        void save(ChargeReceipt receipt)
            throws StoreException;
    }

    private static String requireText(String text, String field) {
        Objects.requireNonNull(text, field);
        if (text.isBlank()) {
            throw new IllegalArgumentException(
                field + " không được rỗng"
            );
        }
        return text;
    }

    // Pha thuần: chỉ đọc dữ liệu, validate, chuẩn bị lệnh.
    public static Plan prepare(List<Order> input) {
        Objects.requireNonNull(input, "input");
        List<Order> snapshot = List.copyOf(input);

        Set<String> ids = new HashSet<>();
        for (Order order : snapshot) {
            if (!ids.add(order.id())) {
                throw new IllegalArgumentException(
                    "Duplicate order ID: " + order.id()
                );
            }
        }

        List<ChargeCommand> commands = snapshot.stream()
            .filter(Order::ready)
            .map(order -> new ChargeCommand(
                order.id(),
                order.customerId(),
                order.amountCents(),
                "charge:v1:" + order.id()
            ))
            .toList();

        long total = commands.stream()
            .mapToLong(ChargeCommand::amountCents)
            .reduce(0L, Math::addExact);

        return new Plan(commands, total);
    }

    // Ranh giới tác dụng phụ: có thứ tự, policy lỗi rõ ràng.
    public static ProcessReport execute(
        Plan plan,
        ChargeGateway gateway,
        ReceiptStore store
    ) {
        Objects.requireNonNull(plan, "plan");
        Objects.requireNonNull(gateway, "gateway");
        Objects.requireNonNull(store, "store");

        List<ExecutionResult> results = new ArrayList<>();

        for (ChargeCommand command : plan.commands()) {
            ChargeReceipt receipt;
            try {
                receipt = Objects.requireNonNull(
                    gateway.charge(command),
                    "Gateway không được trả receipt null"
                );
                if (!receipt.orderId().equals(command.orderId())) {
                    throw new IllegalStateException(
                        "Receipt không khớp order ID"
                    );
                }
            } catch (GatewayException ex) {
                // Timeout/network error: KHÔNG khẳng định chưa thu tiền.
                results.add(new ExecutionResult(
                    command.orderId(),
                    ExecutionStatus.CHARGE_UNCONFIRMED
                ));
                continue;
            }

            try {
                store.save(receipt);
                results.add(new ExecutionResult(
                    command.orderId(),
                    ExecutionStatus.RECORDED
                ));
            } catch (StoreException ex) {
                // Charge đã trả receipt, nhưng chưa ghi nhận bền vững.
                results.add(new ExecutionResult(
                    command.orderId(),
                    ExecutionStatus.RECEIPT_WRITE_FAILED
                ));
            }
        }

        return new ProcessReport(results);
    }

    // Chỉ để mô phỏng: không phải gateway thanh toán thật.
    public static final class FakeGateway
            implements ChargeGateway {
        private final Map<String, ChargeReceipt> byKey =
            new HashMap<>();

        @Override
        public ChargeReceipt charge(ChargeCommand command) {
            return byKey.computeIfAbsent(
                command.idempotencyKey(),
                unused -> new ChargeReceipt(
                    command.orderId(),
                    "R-" + command.orderId()
                )
            );
        }

        public int acceptedKeyCount() {
            return byKey.size();
        }
    }

    // Chỉ để mô phỏng: không thay thế database/transaction.
    public static final class FakeReceiptStore
            implements ReceiptStore {
        private final Map<String, ChargeReceipt> byOrder =
            new LinkedHashMap<>();

        @Override
        public void save(ChargeReceipt receipt) {
            byOrder.put(receipt.orderId(), receipt);
        }

        public int receiptCount() {
            return byOrder.size();
        }
    }

    public static void main(String[] args) {
        List<Order> input = List.of(
            new Order("O1", "C1", 1_000L, true),
            new Order("O2", "C2", 2_000L, false),
            new Order("O3", "C1", 4_000L, true)
        );

        Plan plan = prepare(input);
        System.out.println(plan.commands().size()); // 2
        System.out.println(plan.plannedAmountCents()); // 5000

        FakeGateway gateway = new FakeGateway();
        FakeReceiptStore store = new FakeReceiptStore();
        ProcessReport report = execute(plan, gateway, store);

        System.out.println(report.recordedCount()); // 2
        System.out.println(gateway.acceptedKeyCount()); // 2
        System.out.println(store.receiptCount()); // 2
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 SafeOrderProcessing.java
java SafeOrderProcessing
```

### 7.1. Hợp đồng của `prepare`

`prepare`:

- Không gọi gateway, không ghi database, không gửi email.
- Dùng `List.copyOf` chụp lại cấu trúc danh sách đầu vào và từ chối phần tử `null`.
- Kiểm tra mọi ID trùng **trước khi** lọc đơn sẵn sàng, nên ID trùng bị báo lỗi dù một đơn `ready == false`.
- Dùng `filter` và `map` để tạo các `ChargeCommand` chỉ từ dữ liệu đã hợp lệ.
- Sử dụng `Math.addExact` để phát hiện tổng số tiền tràn `long` trước khi bắt đầu tính phí.
- Trả `Plan` có danh sách lệnh không sửa được và các `record` bất biến ở mức trường primitive/String.

Điều kiện quan trọng: cấu trúc nguồn không bị sửa đồng thời **trong lúc tạo snapshot**. `List.copyOf` không tự biến việc sao chép từ một `ArrayList` đang bị thread khác sửa thành thao tác atomic.

### 7.2. Hợp đồng của `execute`

`execute`:

- Là một **vòng lặp tường minh** theo thứ tự các lệnh.
- Tách lỗi gateway khỏi lỗi ghi receipt.
- Gắn trạng thái `CHARGE_UNCONFIRMED` thay vì đoán gateway chắc chắn chưa thu tiền khi nhận lỗi giao tiếp.
- Gắn `RECEIPT_WRITE_FAILED` nếu gateway đã trả receipt nhưng store báo lỗi.
- Trả một kết quả cho từng command khi **các lỗi dự kiến** là `GatewayException` hoặc `StoreException`.

Đây là **chính sách continue-on-known-error** của ví dụ: lỗi dự kiến ở một đơn không tự động dừng các đơn sau. Những lỗi lập trình/hợp đồng như gateway trả `null` hoặc receipt sai order ID được ném ra để không che giấu vi phạm bất biến; trước khi triển khai sản xuất, nên có cơ chế ghi nhận bền vững các trạng thái trước khi có thể gặp lỗi không dự kiến.

### 7.3. Vì sao demo vẫn chưa phải “exactly once”?

`FakeGateway` chỉ giữ key trong `HashMap` **trong bộ nhớ**. Khi tiến trình khởi động lại, map biến mất. `FakeReceiptStore` cũng không bền vững. Chúng minh họa nơi gắn trách nhiệm chứ **không phải** implementation payment idempotency hoặc durability.

Một hệ thống thật phải có hợp đồng idempotency ở gateway, khóa duy nhất ở database, cách tra cứu trạng thái sau timeout, và có thể cần outbox/workflow trạng thái để phục hồi sau crash.

## 8. Tách trạng thái nghiệp vụ khỏi ngoại lệ kỹ thuật

Khi một service call thất bại, không nên gom mọi trường hợp vào một boolean `success == false`. Cần phân biệt điều gì **đã được xác nhận**, điều gì **chưa biết** và điều gì **có thể thử lại**.

| Trường hợp | Điều ta biết | Trạng thái hoặc xử lý thích hợp |
| --- | --- | --- |
| Gateway trả một receipt hợp lệ, repository lưu thành công | Đã có biên nhận và được ghi nhận | `RECORDED` |
| Gateway báo rõ “thẻ bị từ chối”, được xác nhận là **không charge** | Giao dịch không được chấp thuận | Một trạng thái nghiệp vụ `DECLINED` riêng |
| Gateway timeout sau khi gửi request | **Không biết** gateway đã charge hay chưa | `CHARGE_UNCONFIRMED`, cần tra cứu/reconcile |
| Gateway trả receipt, repository ném lỗi | Biết gateway đã trả kết quả charge; chưa lưu được | `RECEIPT_WRITE_FAILED`, cần phục hồi ghi |
| Database xác nhận ghi thất bại trước khi commit | Có thể biết không ghi thành công tùy hợp đồng DB | Xử lý theo transaction/result cụ thể |
| Mất kết nối đúng lúc commit DB | **Không được đoán** commit chưa xảy ra | Tra cứu trạng thái theo khóa duy nhất |
| Parser phát hiện dữ liệu đầu vào sai trước khi charge | Chưa gọi dịch vụ | Báo validation error |
| Process crash ngay sau charge, trước khi lưu | Có thể đã tạo tác dụng phụ nhưng chưa ghi trạng thái | Durable intent/outbox/reconciliation |

Code mẫu gộp các `GatewayException` thành `CHARGE_UNCONFIRMED` vì interface mô phỏng **không có loại lỗi decline đã xác nhận**. Trong sản phẩm thật, gateway adapter nên phân loại lỗi theo hợp đồng nhà cung cấp:

- **Declined chắc chắn:** trả `Declined(reasonCode)` hoặc một domain result tương đương.
- **Accepted chắc chắn:** trả receipt/id giao dịch.
- **Không rõ sau timeout/connection reset:** trả `UnknownOutcome`, không tự động charge lại bằng key khác.

Nếu API không đủ thông tin phân biệt, **chọn trạng thái bảo thủ** và bổ sung đường tra cứu/đối soát.

### 8.1. Tại sao không nên dùng `Optional.empty()` cho mọi lỗi?

`Optional.empty()` nói “không có giá trị”, nhưng không biểu diễn được:

1. Không có dữ liệu là bình thường.
2. Dịch vụ xác nhận không tìm thấy.
3. Dịch vụ timeout.
4. Dữ liệu phản hồi không hợp lệ.
5. Việc ghi kết quả thất bại.

Nếu mọi tình huống trên đều được đổi thành `Optional.empty()`, downstream có thể xem lỗi là dữ liệu rỗng và âm thầm tạo báo cáo thiếu. Hãy dùng **kiểu kết quả có trạng thái**, ngoại lệ phân loại, hoặc một báo cáo lỗi tường minh.

### 8.2. Thứ tự thao tác quyết định ý nghĩa thất bại

Với flow `charge → save receipt`, lỗi lưu dữ liệu xảy ra **sau** một tác dụng phụ bên ngoài. Không thể chỉ bắt `StoreException` rồi coi như đã rollback charge.

Nếu đổi thành `save "PENDING" → charge → save "CONFIRMED"`, hệ thống có cơ sở dữ liệu tốt hơn để phục hồi, nhưng vẫn còn khoảng trống giữa các hệ thống. Việc gọi gateway không thể tự tham gia vào một transaction database thông thường nếu gateway không cung cấp cơ chế đồng bộ giao dịch tương thích.

## 9. Checked exception trong lambda: đừng dùng wrapper để giấu lỗi

Các functional interface `Function<T,R>`, `Predicate<T>` và `Consumer<T>` của Stream API không khai `throws IOException` hoặc ngoại lệ checked tùy ý. Vì vậy:

```java
// Không biên dịch nếu client.lookup khai throws IOException:
// var values = ids.stream()
//     .map(id -> client.lookup(id))
//     .toList();
```

Có nhiều lựa chọn, mỗi lựa chọn phù hợp với một hợp đồng khác nhau.

### 9.1. Lựa chọn A — gọi dịch vụ tại một vòng lặp riêng

```java
List<String> ids = customers.stream()
    .filter(Customer::active)
    .map(Customer::id)
    .distinct()
    .toList();

List<CustomerProfile> profiles = new ArrayList<>();
for (String id : ids) {
    // Có chính sách retry/timeout/failure bên ngoài pipeline.
    profiles.add(client.lookup(id));
}
```

Đây là **đoạn minh họa bên trong một phương thức có tham số `customers` và `client` thích hợp**. Nếu `lookup` ném checked exception, phương thức bao quanh có thể `throws` hoặc `catch` phân loại lỗi tại đúng ranh giới.

Ưu điểm: dễ giới hạn số lời gọi, gắn correlation ID, dừng/tiếp tục rõ ràng và đóng các tài nguyên của request theo từng lần gọi.

### 9.2. Lựa chọn B — chuyển checked exception có chủ đích

Với thao tác **đọc nguồn I/O** khi thực sự cần pipeline, Java cung cấp `UncheckedIOException`:

```java
static String readTextUnchecked(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException ex) {
        throw new UncheckedIOException("Không đọc được: " + path, ex);
    }
}
```

Nếu gọi nó trong `map`, cần:

- Giữ **cause** của `IOException`.
- Không chuyển lỗi thành `null` hoặc `Stream.empty()` chỉ để pipeline tiếp tục.
- Bảo đảm không có side effect quan trọng đã thực hiện một phần trước lúc lỗi, hoặc có cơ chế khôi phục.
- Đóng tài nguyên ở owner phù hợp.

Chuyển checked sang unchecked **chỉ đổi cách truyền ngoại lệ**, không tạo rollback hoặc retry.

### 9.3. Lựa chọn C — trả kết quả có loại

Khi cần phân tích hàng loạt response nhưng **không ném** ở phần tử lỗi:

```java
sealed interface LookupOutcome
    permits LookupOk, LookupFailed {}

record LookupOk(String id, CustomerProfile profile)
    implements LookupOutcome {}

record LookupFailed(String id, String errorCode)
    implements LookupOutcome {}
```

Nếu dùng kiểu này, hãy có một pha gọi dịch vụ có kiểm soát để tạo `List<LookupOutcome>` rồi **dùng Stream thuần** để phân loại:

```java
Map<Boolean, List<LookupOutcome>> grouped = outcomes.stream()
    .collect(Collectors.partitioningBy(
        outcome -> outcome instanceof LookupOk
    ));
```

`partitioningBy` không tự gọi dịch vụ; nó chỉ phân chia **những kết quả đã tồn tại**. Đây là cách dùng Stream API ở nơi phù hợp.

## 10. Retry, idempotency và đối soát sau sự cố

### 10.1. Retry không làm một tác vụ trở thành an toàn nếu thiếu điều kiện

Giả sử mạng timeout sau khi gửi lệnh charge:

```text
Client                   Gateway
  │  charge(key=K)          │
  ├────────────────────────►│
  │                         │ xử lý thành công
  │  X mất phản hồi         │
  │                         │
  └── Timeout              │
```

Nếu client retry bằng **key mới** hoặc gateway không có hợp đồng idempotency, một lần charge thứ hai có thể xảy ra. `catch` rồi gọi lại không giải quyết được vấn đề này.

### 10.2. Idempotency key phải đại diện cho giao dịch logic

Trong ví dụ, `"charge:v1:" + order.id()` giữ nguyên khi retry cùng lệnh. Nhưng hệ thống thật cần xác định:

- Key có duy nhất trong phạm vi merchant/tenant và loại giao dịch không?
- Gateway giữ trạng thái key trong bao lâu?
- Nếu cùng key nhưng **payload khác amount**, gateway từ chối hay trả kết quả cũ?
- Khi timeout, có API tra cứu theo key hoặc transaction ID không?
- Khi key đã hết thời hạn lưu, ứng dụng còn muốn retry hay chuyển sang xử lý thủ công?

**Idempotency là hợp đồng của hệ thống nhận yêu cầu**, không phải thuộc tính tự nhiên của `Stream.distinct()` hay `Set`.

### 10.3. Retry nên nhắm đúng bước thất bại

| Trạng thái | Phục hồi nên làm gì? | Điều không nên làm |
| --- | --- | --- |
| Charge chưa rõ kết quả | Tra cứu key/transaction, reconcile trước khi retry | Gửi charge mới không xác minh |
| Charge đã có receipt, ghi DB lỗi | Thử ghi receipt **idempotent** | Thu tiền lại chỉ vì save lỗi |
| Business decline đã xác nhận | Ghi trạng thái decline, hỏi phương án thanh toán khác | Retry vô hạn cùng điều kiện |
| Dữ liệu input sai | Sửa dữ liệu/validation, tạo kế hoạch mới | Retry gateway khi command chưa hợp lệ |
| Lỗi tạm thời có chứng cứ có thể retry | Retry có giới hạn và backoff theo policy | Vòng lặp vô hạn không timeout |

### 10.4. Đừng đặt retry trong `map` mà không giới hạn số lần gọi

`map(order -> retry(() -> gateway.charge(order)))` khiến logic giao dịch khó quan sát, nhất là khi có `parallel`, `limit` hoặc một giai đoạn khác ném lỗi. Tốt hơn là cấp một **port/service coordinator** với deadline, giới hạn concurrency, status store và chính sách retry riêng.

Nếu chỉ có một lời gọi HTTP **read-only** và không cần phân loại lỗi phức tạp, `map(client::fetch)` đôi khi vẫn là lựa chọn thực dụng. Điều quan trọng là nó **không còn thuần** và phải được đánh giá với hợp đồng thời gian, thứ tự, lỗi và nguồn — không được giả vờ mọi mapper của Stream đều là biến đổi dữ liệu trong bộ nhớ.

## 11. Ghi dữ liệu an toàn: transaction, unique key và outbox

### 11.1. Transaction database chỉ bảo vệ những thao tác thuộc transaction đó

Nếu có nhiều lệnh SQL trên **cùng database** và cùng transaction, transaction có thể bảo đảm commit/rollback atomic theo mức cô lập và hợp đồng driver/database.

Ví dụ khái niệm:

```text
BEGIN TRANSACTION
    INSERT order_status(...)
    INSERT audit_event(...)
COMMIT
```

Nhưng một lời gọi HTTP tới payment gateway **không tự động nằm trong transaction** của database. Khi HTTP thành công mà database rollback, gateway không bị rollback theo.

### 11.2. Outbox cho trường hợp ghi DB rồi phát sự kiện

Khi cần đồng bộ “lưu trạng thái đơn hàng” và “phát sự kiện”, **transactional outbox** là một pattern hữu ích:

```text
Transaction trong cùng database:
    UPDATE orders SET status = 'READY'
    INSERT INTO outbox(event_id, payload, status='PENDING')
COMMIT
                   │
                   ▼
Worker riêng đọc outbox:
    gửi event tới broker
    đánh dấu published / retry
                   │
                   ▼
Consumer xử lý event theo event_id idempotent
```

Outbox giúp tránh khoảng trống “database đã commit nhưng ứng dụng crash trước khi publish”. Tuy nhiên, worker có thể gửi event thành công rồi crash trước khi đánh dấu đã publish; event có thể **được gửi lại**. Vì thế consumer vẫn cần **deduplication/idempotency** nếu mục tiêu là tác dụng phụ logic một lần.

### 11.3. Khi gọi gateway trước ghi DB, cần durable intent hoặc reconciliation

Với thanh toán, có thể lưu **ý định xử lý** (cùng idempotency key và dữ liệu đã xác thực) trước khi gửi gateway. Một worker thực thi có thể:

1. Lấy job có trạng thái `PENDING`.
2. Gọi gateway bằng key ổn định.
3. Ghi receipt/transaction ID khi nhận được xác nhận.
4. Chuyển trạng thái sang `RECORDED`, `DECLINED` hoặc `UNKNOWN`.
5. Đối soát job `UNKNOWN` trước khi thử lại.

Đây là **một thiết kế hệ thống**, không phải mã do `Collectors.toMap` hay `parallelStream` tạo ra. Chi tiết claim job, khóa lạc quan, deadline và thay đổi trạng thái phải phù hợp database/gateway cụ thể.

### 11.4. Nếu thao tác ghi có thể chạy lại, key lưu phải duy nhất

Ví dụ về bảng receipt:

```text
receipts(
    order_id UNIQUE,
    gateway_transaction_id UNIQUE,
    amount,
    recorded_at
)
```

Các unique constraints và một câu lệnh insert/upsert có hợp đồng rõ giúp giảm khả năng ghi trùng khi retry. Nhưng **upsert** vẫn phải kiểm tra rằng dữ liệu cũ khớp với giao dịch logic; không được ghi đè một receipt có số tiền khác mà không báo lỗi.

## 12. Chọn chính sách xử lý theo lô và ranh giới thành công

Có ít nhất ba lựa chọn khi gặp lỗi ở một phần tử:

| Chính sách | Hành vi | Khi nào phù hợp |
| --- | --- | --- |
| **Fail-fast** | Ngừng nhận thêm lệnh ở lỗi đầu tiên | Từng bước phải được kiểm duyệt; lỗi hiếm và không được bỏ qua |
| **Continue with results** | Tiếp tục xử lý các lệnh còn lại, ghi trạng thái từng lệnh | Batch độc lập, cần báo cáo đầy đủ tiến độ |
| **Durable job queue** | Lưu công việc và trạng thái, worker xử lý theo policy | Quy trình nhiều bước, cần phục hồi sau crash |

Ví dụ `execute` ở mục 7 chọn **continue with results** cho `GatewayException` và `StoreException`. Nó **không** xử lý mọi lỗi RuntimeException: nếu code vi phạm contract, quy trình có thể dừng bất ngờ. Trong production, cần có trạng thái từng job **được lưu bền vững trước thao tác ngoài** để phục hồi khi tiến trình chết.

### 12.1. Phân biệt ba loại “thành công”

1. **Pha chuẩn bị thành công:** `Plan` được tạo, dữ liệu và các invariant đã qua validation.
2. **Lời gọi gateway thành công:** hệ thống nhận được kết quả charge xác nhận.
3. **Toàn bộ workflow thành công:** receipt được ghi bền vững, audit/outbox cần thiết được hoàn tất và trạng thái có thể truy xuất sau crash.

Không gộp cả ba thành một trường `success = true` chỉ vì `collect(...)` không ném lỗi.

### 12.2. Partial success phải được công bố rõ

Nếu một batch có 100 lệnh:

```text
RECORDED             = 94
CHARGE_UNCONFIRMED   =  3
RECEIPT_WRITE_FAILED =  3
TOTAL                = 100
```

Đầu ra nên thể hiện đầy đủ cả ba trạng thái và các ID tương ứng. Không trả `List<Receipt>` gồm 94 receipt rồi nói “đã xử lý 100 đơn” nếu sáu lệnh còn lại chưa hoàn tất.

### 12.3. Kết quả rỗng không phải lỗi dịch vụ

Nếu sau `filter(Order::ready)` không có command, `Plan.commands()` rỗng có thể là trạng thái hợp lệ: **không có đơn đủ điều kiện**. Trái lại, nếu có command mà gateway timeout, không được biến thành `Plan` rỗng hoặc `ProcessReport` “không có việc” để tiếp tục.

Tách **rỗng theo nghiệp vụ** khỏi **thất bại kỹ thuật** là điều kiện cần cho báo cáo và retry.

## 13. Gọi dịch vụ trước phép biến đổi: mô hình enrichment có kiểm soát

Không phải lúc nào service call cũng nằm ở cuối. Nhiều bài toán phải tra cứu profile, giá hoặc tỷ giá trước khi biến đổi thành kết quả:

```text
Nguồn raw records
    │
    ├─ PURE: xác định request keys cần tra cứu
    ▼
List<LookupRequest> có thứ tự và không trùng
    │
    ├─ I/O BOUNDARY: gọi service, lưu kết quả/loại lỗi
    ▼
List<LookupOutcome> đã materialize
    │
    ├─ PURE: join response với bản ghi nguồn
    ▼
List<EnrichedRecord>
    │
    └─ I/O BOUNDARY: lưu/export kết quả theo transaction policy
```

### 13.1. Giai đoạn xác định request keys có thể thuần

```java
List<String> customerIds = orders.stream()
    .map(Order::customerId)
    .distinct()
    .toList();
```

Với `List` ordered, `distinct` giữ phần tử đầu tiên của mỗi ID theo encounter order. Đây là **giảm số yêu cầu tra cứu lặp** ở đầu vào; nó không phải bảo đảm service bên ngoài được gọi exactly-once nếu workflow retry/crash.

### 13.2. Giai đoạn gọi service nên trả outcome rõ ràng

```java
List<LookupOutcome> outcomes = new ArrayList<>();

for (String id : customerIds) {
    try {
        CustomerProfile profile = profileClient.lookup(id);
        outcomes.add(new LookupOk(id, profile));
    } catch (ProfileServiceException ex) {
        outcomes.add(
            new LookupFailed(id, ex.errorCode())
        );
    }
}
```

Đoạn này là **mẫu điều phối**, không phải chương trình độc lập: `profileClient`, `ProfileServiceException` và `CustomerProfile` được định nghĩa ở tầng tích hợp. Chủ ý là không che dấu request nào lỗi và chỉ chuyển **mã lỗi an toàn** sang kết quả công khai.

### 13.3. Giai đoạn join/transform lại có thể thuần

Sau khi tất cả kết quả đã ổn định, có thể xây map các profile thành công:

```java
Map<String, CustomerProfile> successfulProfiles =
    outcomes.stream()
        .filter(LookupOk.class::isInstance)
        .map(LookupOk.class::cast)
        .collect(Collectors.toMap(
            LookupOk::id,
            LookupOk::profile
        ));
```

`Collectors.toMap` **ném lỗi khi khóa trùng** theo hợp đồng overload hai mapper. Điều này giúp phát hiện service result bị lặp không dự kiến, thay vì âm thầm ghi đè.

Từ map này, một phép `map` thuần có thể ghép dữ liệu, nhưng phải xác định chính sách **profile thiếu**:

- Nếu mọi profile đều bắt buộc, báo lỗi và **không xuất bản** bản join thiếu.
- Nếu thiếu là trạng thái hợp lệ, dùng kiểu kết quả biểu diễn “không có profile”.
- Nếu được phép bỏ bản ghi, trả số lượng/ID đã bỏ thay vì tự `filter(Objects::nonNull)` rồi xem như hoàn chỉnh.

## 14. Nguồn tệp và việc đóng tài nguyên trước khi bước có side effect bắt đầu

Với nguồn I/O, việc đọc log/CSV có thể ném lỗi **khi mở** hoặc **trong lúc duyệt**. Đặt lời gọi dịch vụ trong `map` của `Files.lines` khiến vòng đời reader bị kéo dài trong lúc chờ network và tạo khả năng đã ghi một phần trước khi phát hiện dòng cuối sai.

### 14.1. Mẫu an toàn khi đầu vào vừa bộ nhớ

```java
Plan plan;
try (Stream<String> lines = Files.lines(
        path, StandardCharsets.UTF_8)) {
    List<Order> parsed = lines
        .map(OrderParser::parseStrict)
        .toList();
    plan = SafeOrderProcessing.prepare(parsed);
}

// Ở đây file đã đóng và toàn bộ input đã được validate.
ProcessReport report = SafeOrderProcessing.execute(
    plan, gateway, receiptStore
);
```

Đây là đoạn trong một phương thức có sẵn `path`, `gateway`, `receiptStore`, `OrderParser`. Các ý chính:

- Reader/file được đóng **trước khi** bắt đầu charge.
- Parsing/validation lỗi thì không có thao tác charge nào được chạy.
- Có thể tính tổng và phát hiện duplicate **trước** khi tạo side effect.
- Không tự chuyển `IOException` thành file rỗng.

### 14.2. Khi đầu vào không thể materialize toàn bộ

Với file hàng trăm GB, `toList()` sẽ dùng bộ nhớ theo số bản ghi. Có thể phải xử lý **từng chunk** hoặc dùng workflow hàng đợi:

```text
read 1 chunk → parse/validate chunk → persist intent → execute → checkpoint
read next chunk → ...
```

Khi đó, **không còn bảo đảm** “mọi dòng trong toàn file đã valid trước khi thực hiện giao dịch đầu tiên”. Phải công bố rõ chính sách partial progress và lưu checkpoint/dedup để có thể tiếp tục sau lỗi. Nếu yêu cầu all-or-nothing trên toàn file, cần thiết kế staging/validation trước execution hoặc công cụ giao dịch thích hợp.

### 14.3. `try-with-resources` không tự rollback ghi ngoài

`try-with-resources` bảo đảm đóng stream/reader đang sở hữu; nó **không hoàn tác** các dòng đã ghi vào database trước khi lỗi I/O đọc xuất hiện. Đừng nhầm tính đúng về tài nguyên với tính nguyên tử của một workflow.

## 15. Xử lý song song: giới hạn concurrency trước, không chuyển bừa sang `parallelStream`

Các lời gọi dịch vụ thường là blocking I/O. Chạy đồng thời **có thể** tăng throughput, nhưng kéo theo:

- Số kết nối đang mở, rate limit và quota của service.
- Thời gian timeout và cancellation.
- Số yêu cầu còn đang xử lý khi một yêu cầu lỗi.
- Thứ tự phản hồi khác với encounter order.
- Khả năng trùng tác dụng phụ khi retry hoặc crash.
- Trạng thái mutable trong các adapter có thể không thread-safe.

`parallelStream()` **không cung cấp sẵn** các hợp đồng rate limit, durable checkpoint, transaction hoặc idempotency.

### 15.1. `forEachOrdered` chỉ giải quyết một phần của bài toán

`forEachOrdered` duy trì encounter order của các action trên ordered stream, kể cả khi pipeline có chế độ parallel. Nhưng nó:

- Không tự biến HTTP request thành transactional.
- Không tự lưu tiến độ bền vững.
- Không bảo đảm một lỗi ở phần tử sau rollback tác dụng phụ trước đó.
- Không giúp phía service xác nhận một timeout có charge thành công hay chưa.

Khi thứ tự giao dịch quan trọng và số lượng vừa phải, **vòng lặp tuần tự tường minh** thường là lựa chọn đơn giản và dễ kiểm thử nhất.

### 15.2. Nếu cần concurrency thật sự, tạo một coordinator riêng

Thay vì `parallelStream().forEach(gateway::charge)`, một coordinator có thể dùng:

1. **Bounded concurrency:** giới hạn tối đa `k` request đồng thời.
2. **Per-request timeout:** không chờ vô hạn.
3. **Rate limiting:** giới hạn số request theo hợp đồng dịch vụ.
4. **Stable idempotency key:** retry cùng giao dịch logic không tạo key mới.
5. **Per-item result:** ghi trạng thái của từng lệnh.
6. **Durable checkpoint/reconciliation:** phục hồi sau crash.
7. **Cancellation semantics:** biết rõ việc ngừng chờ không có nghĩa server đã ngừng xử lý.

Các tính năng này thường được xây bằng `ExecutorService`, queue/job worker, cơ chế giới hạn concurrency hoặc framework tích hợp thích hợp. **Stream API có thể dùng để chuẩn bị danh sách lệnh và tổng hợp kết quả**, còn chính sách điều phối thuộc một thành phần riêng.

### 15.3. Không dùng stream song song để bảo đảm đúng N external calls

`limit(10)` giới hạn **số phần tử đầu ra** được yêu cầu, không phải một hợp đồng “chỉ có đúng 10 side effect từ những mapper chạy trước đó” trong mọi pipeline song song/được tối ưu. Một số tác vụ có thể đã bắt đầu trước khi downstream short-circuit.

Nếu nghiệp vụ yêu cầu đúng một số lượng lệnh, hãy tạo `List<ChargeCommand>` có kích thước đã validate, rồi đưa danh sách đó vào coordinator. Không dựa vào thứ tự thực thi lambda để định danh giao dịch.

## 16. Thứ tự đầu vào, thứ tự lưu và thứ tự hoàn tất

Ba loại thứ tự cần tách riêng:

| Loại thứ tự | Ví dụ | Có được Stream API bảo đảm? |
| --- | --- | --- |
| **Encounter order** | Đơn O1, O2, O3 từ một `List` | Có theo hợp đồng nguồn/pipeline ordered |
| **Thứ tự thực thi** | O2 gọi HTTP trước O1 khi xử lý song song | Không được cam kết bởi `parallel forEach` |
| **Thứ tự commit/response** | O3 commit DB trước O1 | Do service, transaction và coordinator quyết định |

Chương trình chính `execute` duyệt `plan.commands()` tuần tự, nên **thứ tự gọi gateway** theo danh sách plan trong một tiến trình bình thường. Nhưng không thể suy ra mọi hệ thống ngoài commit theo thứ tự ấy hoặc không có request từ tác nhân khác.

### 16.1. Thứ tự trong một báo cáo hiển thị

Nếu kết quả được thu từ nhiều worker song song, có thể lưu một `sequenceNumber` trong `ChargeCommand` hoặc `ExecutionResult`, rồi sắp kết quả theo số ấy **sau khi** thực thi:

```java
List<ExecutionResult> orderedResults = results.stream()
    .sorted(Comparator.comparingInt(ExecutionResult::sequenceNumber))
    .toList();
```

Đây là **đoạn minh họa cho một biến thể `ExecutionResult` có thêm `sequenceNumber`**, không phải lời gọi biên dịch với record hai trường ở chương trình chính. Việc sắp kết quả chỉ thay đổi **thứ tự báo cáo**, không thay đổi thứ tự các request đã đến gateway.

### 16.2. Dữ liệu lặp: `distinct` không phải kiểm soát ghi đúng một lần

`distinct` loại các phần tử trùng theo `equals` trong một **lần duyệt stream**. Nó không biết lần chạy trước của ứng dụng đã ghi những giao dịch nào; không thay thế idempotency key hoặc unique constraints.

Khi một batch được chạy lại sau crash, phải có một nguồn trạng thái bền vững để xác định lệnh nào đã hoàn thành, chưa hoàn thành hoặc chưa xác định.

## 17. Logging, metrics và bảo mật ở ranh giới tác dụng phụ

Log là một side effect, nhưng thường cần thiết để vận hành. Cách làm phù hợp không phải là “cấm logging”, mà là **đặt logging tại ranh giới được điều phối**:

```text
execute command
    │
    ├─ log request ID + operation type (không log token/PII)
    ├─ gọi gateway với timeout và idempotency key
    ├─ log status đã phân loại + latency
    ├─ ghi receipt
    └─ log bước lưu và cập nhật trạng thái
```

**Không dùng `peek` để viết audit bắt buộc**, vì một lời gọi terminal có thể short-circuit hoặc implementation có thể tối ưu bỏ một intermediate stage không ảnh hưởng kết quả.

### 17.1. Bộ số liệu vận hành nên tách biệt

| Metric | Đo điều gì? |
| --- | --- |
| `commands_planned` | Số lệnh đã được validate và lập kế hoạch |
| `gateway_confirmed` | Số lệnh gateway trả kết quả thành công đã xác nhận |
| `charge_unconfirmed` | Số lệnh không biết chắc kết quả sau lỗi |
| `receipt_recorded` | Số biên nhận đã được lưu |
| `receipt_write_failed` | Số lỗi lưu khi đã có receipt |
| `reconciliation_pending` | Số công việc cần đối soát |
| `retry_attempts` | Số lần thử lại, không phải số giao dịch mới |

Tổng số command cần được đối chiếu với các trạng thái cuối của batch. Đừng dùng số dòng log `"success"` hoặc số lần lambda mapper chạy để làm dữ liệu tài chính.

### 17.2. Không rò rỉ dữ liệu nhạy cảm khi báo lỗi

Một exception từ SDK có thể chứa URL, request body, token hoặc thông tin thanh toán. `ExecutionResult` trong ví dụ công khai **mã trạng thái**, không công khai `ex.getMessage()` thô. Nếu cần điều tra:

- Dùng correlation ID/trace ID được tạo theo chính sách hệ thống.
- Ghi cause vào một kênh có kiểm soát truy cập, có redaction.
- Không lưu toàn bộ dữ liệu thẻ hoặc khóa bí mật trong `Plan`/log.
- Tách thông báo kỹ thuật nội bộ khỏi thông báo trả ra API.

## 18. Kiểm thử JUnit 5: chứng minh tính thuần và ranh giới side effect

Các test dưới đây chạy trên JDK 17 và JUnit Jupiter, sử dụng lớp `SafeOrderProcessing` ở mục 7. Chúng kiểm tra **giá trị lập kế hoạch**, **số lời gọi trong mô phỏng**, **báo cáo trạng thái** và **khả năng dùng lại key**. Chúng không giả định fake gateway là một dịch vụ thanh toán bền vững.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class SafeOrderProcessingTest {

    private static List<SafeOrderProcessing.Order> sample() {
        return List.of(
            new SafeOrderProcessing.Order("O1", "C1", 100L, true),
            new SafeOrderProcessing.Order("O2", "C2", 200L, false),
            new SafeOrderProcessing.Order("O3", "C1", 300L, true)
        );
    }

    @Test
    void prepareIsDeterministicAndHasStableKeys() {
        var first = SafeOrderProcessing.prepare(sample());
        var second = SafeOrderProcessing.prepare(sample());

        assertEquals(first, second);
        assertEquals(2, first.commands().size());
        assertEquals(400L, first.plannedAmountCents());
        assertEquals(List.of("O1", "O3"),
            first.commands().stream()
                .map(SafeOrderProcessing.ChargeCommand::orderId)
                .toList());
        assertEquals("charge:v1:O1",
            first.commands().get(0).idempotencyKey());
    }

    @Test
    void duplicateIdsAreRejectedBeforeExternalCalls() {
        var duplicates = List.of(
            new SafeOrderProcessing.Order("O1", "C1", 100L, true),
            new SafeOrderProcessing.Order("O1", "C9", 999L, false)
        );

        assertThrows(IllegalArgumentException.class, () ->
            SafeOrderProcessing.prepare(duplicates)
        );
        // Không gọi execute: prepare chỉ tạo kế hoạch.
    }

    @Test
    void overflowIsRejectedDuringPurePreparation() {
        var tooLarge = List.of(
            new SafeOrderProcessing.Order(
                "O1", "C1", Long.MAX_VALUE, true
            ),
            new SafeOrderProcessing.Order("O2", "C2", 1L, true)
        );

        assertThrows(ArithmeticException.class, () ->
            SafeOrderProcessing.prepare(tooLarge)
        );
    }

    @Test
    void planDoesNotTrackLaterSourceListStructuralChanges() {
        ArrayList<SafeOrderProcessing.Order> input =
            new ArrayList<>(sample());
        var plan = SafeOrderProcessing.prepare(input);

        input.clear();
        assertEquals(2, plan.commands().size());
        assertThrows(UnsupportedOperationException.class, () ->
            plan.commands().clear()
        );
    }

    @Test
    void noReadyOrderMeansNoGatewayOrStoreCall() {
        var plan = SafeOrderProcessing.prepare(
            List.of(new SafeOrderProcessing.Order(
                "O1", "C1", 100L, false
            ))
        );
        AtomicInteger gatewayCalls = new AtomicInteger();
        AtomicInteger storeCalls = new AtomicInteger();

        var report = SafeOrderProcessing.execute(
            plan,
            cmd -> {
                gatewayCalls.incrementAndGet();
                return new SafeOrderProcessing.ChargeReceipt(
                    cmd.orderId(), "R1"
                );
            },
            receipt -> storeCalls.incrementAndGet()
        );

        assertTrue(report.results().isEmpty());
        assertEquals(0, gatewayCalls.get());
        assertEquals(0, storeCalls.get());
    }

    @Test
    void confirmedChargeIsRecorded() {
        AtomicInteger gatewayCalls = new AtomicInteger();
        AtomicInteger storeCalls = new AtomicInteger();
        var plan = SafeOrderProcessing.prepare(sample());

        var report = SafeOrderProcessing.execute(
            plan,
            cmd -> {
                gatewayCalls.incrementAndGet();
                return new SafeOrderProcessing.ChargeReceipt(
                    cmd.orderId(), "R-" + cmd.orderId()
                );
            },
            receipt -> {
                storeCalls.incrementAndGet();
            }
        );

        assertEquals(2, gatewayCalls.get());
        assertEquals(2, storeCalls.get());
        assertEquals(2L, report.recordedCount());
        assertEquals(
            SafeOrderProcessing.ExecutionStatus.RECORDED,
            report.results().get(0).status()
        );
    }

    @Test
    void gatewayTimeoutIsReportedAsUnconfirmedNotDeclined() {
        AtomicInteger storeCalls = new AtomicInteger();
        var plan = SafeOrderProcessing.prepare(
            List.of(sample().get(0))
        );

        var report = SafeOrderProcessing.execute(
            plan,
            cmd -> {
                throw new SafeOrderProcessing.GatewayException(
                    "Timeout giả lập"
                );
            },
            receipt -> storeCalls.incrementAndGet()
        );

        assertEquals(0, storeCalls.get());
        assertEquals(
            SafeOrderProcessing.ExecutionStatus.CHARGE_UNCONFIRMED,
            report.results().get(0).status()
        );
    }

    @Test
    void writeFailureDoesNotClaimChargeWasUndone() {
        var plan = SafeOrderProcessing.prepare(
            List.of(sample().get(0))
        );

        var report = SafeOrderProcessing.execute(
            plan,
            cmd -> new SafeOrderProcessing.ChargeReceipt(
                cmd.orderId(), "R1"
            ),
            receipt -> {
                throw new SafeOrderProcessing.StoreException(
                    "DB không sẵn sàng"
                );
            }
        );

        assertEquals(
            SafeOrderProcessing.ExecutionStatus.RECEIPT_WRITE_FAILED,
            report.results().get(0).status()
        );
        assertEquals(0L, report.recordedCount());
    }

    @Test
    void fakeGatewayDeduplicatesStableKeyAcrossTwoRuns() {
        var plan = SafeOrderProcessing.prepare(sample());
        var gateway = new SafeOrderProcessing.FakeGateway();
        var store = new SafeOrderProcessing.FakeReceiptStore();

        SafeOrderProcessing.execute(plan, gateway, store);
        SafeOrderProcessing.execute(plan, gateway, store);

        assertEquals(2, gateway.acceptedKeyCount());
        assertEquals(2, store.receiptCount());
        // Fake in-memory không chứng minh durability sau restart.
    }

    @Test
    void invalidOrderIsRejectedBeforePlan() {
        assertThrows(IllegalArgumentException.class, () ->
            new SafeOrderProcessing.Order(
                "O1", "C1", -1L, true
            )
        );
        assertThrows(IllegalArgumentException.class, () ->
            new SafeOrderProcessing.Order(
                "", "C1", 100L, true
            )
        );
        assertThrows(NullPointerException.class, () ->
            SafeOrderProcessing.prepare(null)
        );
    }
}
```

### 18.1. Test nào chứng minh điều gì?

| Test | Bảo đảm được kiểm chứng |
| --- | --- |
| `prepareIsDeterministicAndHasStableKeys` | Cùng input tạo plan tương đương |
| `duplicateIdsAreRejectedBeforeExternalCalls` | Input trùng bị chặn trong pha thuần |
| `overflowIsRejectedDuringPurePreparation` | Không charge với tổng tiền tràn miền số |
| `planDoesNotTrackLaterSourceListStructuralChanges` | Plan không phụ thuộc việc caller sửa cấu trúc nguồn sau prepare |
| `noReadyOrderMeansNoGatewayOrStoreCall` | Không có command thì không gọi external ports |
| `confirmedChargeIsRecorded` | Mỗi command mô phỏng đã gọi gateway và store |
| `gatewayTimeoutIsReportedAsUnconfirmedNotDeclined` | Timeout không bị diễn giải thành chắc chắn chưa charge |
| `writeFailureDoesNotClaimChargeWasUndone` | Lỗi lưu receipt có trạng thái riêng |
| `fakeGatewayDeduplicatesStableKeyAcrossTwoRuns` | Chứng minh **fake** giữ key trong cùng tiến trình, không hơn |

Trong thử nghiệm sản xuất, cần thêm **integration tests** đối với gateway sandbox, database thật và quy trình phục hồi sau restart. Unit test với fake chỉ chứng minh code điều phối nhận/đưa trạng thái đúng theo giao diện.

### 18.2. Không đưa thời gian ngủ ngẫu nhiên vào unit test tính đúng

Để mô phỏng timeout, gateway fake **ném `GatewayException`**. Unit test không cần `Thread.sleep` hoặc chờ một mạng thực, tránh test chập chờn. Những vấn đề concurrency, timeout thực, kết nối bị reset và crash giữa các bước nên được thử qua test tích hợp/chaos test có môi trường kiểm soát.

## 19. Các phản mẫu và sai lầm cần tránh

| Phản mẫu | Điều có thể sai | Cách thay thế |
| --- | --- | --- |
| Gọi `gateway.charge` trực tiếp trong `map` | Khó kiểm soát retry, timeout, số request và partial success | Tạo `ChargeCommand` bằng `map`, gọi gateway tại coordinator |
| Ghi DB bằng `peek` | Intermediate operation có thể không được thực hiện | Ghi qua service/repository ở bước tường minh |
| Coi `forEachOrdered` như transaction | Có thứ tự nhưng không atomic/rollback | Transaction/workflow state theo hệ thống |
| `parallelStream().forEach(repository::save)` với repository không thread-safe | Race, vượt connection limit | Điều phối concurrency rõ ràng |
| `catch (Exception ex) { return null; }` trong mapper | Nuốt lỗi dữ liệu, I/O và lỗi lập trình | Domain result hoặc exception phân loại |
| `catch (IOException ex) { return Stream.empty(); }` | File không đọc được trở thành dữ liệu rỗng | Báo nguồn thất bại, không giả thành công |
| Retry HTTP charge bằng `UUID.randomUUID()` mới | Một giao dịch logic có nhiều key | Stable idempotency key, tra cứu trạng thái |
| Gọi lại charge sau lỗi ghi receipt | Có thể nhân đôi giao dịch | Ghi lại receipt idempotent, không charge lại |
| Timeout được gán `DECLINED` | Có thể gateway đã charge thành công | Dùng trạng thái **chưa xác định**, đối soát |
| `distinct` rồi tin chỉ ghi mỗi đơn một lần vĩnh viễn | Không nhớ các lần chạy trước | Durable deduplication / unique constraints |
| Lưu raw exception message vào response | Có nguy cơ lộ token/PII | Mã lỗi an toàn + logging redacted |
| Một map mutable chung bị các lambda cập nhật | Non-interference và thread-safety bị vi phạm | Collector có ownership hoặc vòng lặp rõ |
| Chỉ test kết quả `toList()` | Không phát hiện số lần gateway bị gọi hoặc trạng thái sai | Fake ports + integration tests |
| Chạy side effects trước rồi mới validate hết batch | Đầu vào cuối lỗi khi đã charge một phần | Prepare/validate toàn bộ nếu dung lượng cho phép |
| Materialize hàng tỷ record vào `List` | Có thể hết bộ nhớ | Staging/chunk/checkpoint có hợp đồng partial progress |
| Cho rằng `Stream.close()` rollback mọi thao tác | Chỉ quản lý tài nguyên được gắn với stream | Thiết kế transaction/compensation riêng |

### 19.1. Vì sao `peek` vẫn có ích?

`peek` có thể dùng để quan sát giá trị ở một giai đoạn xử lý khi gỡ lỗi:

```java
List<String> normalized = names.stream()
    .map(String::strip)
    .peek(value -> System.out.println("DEBUG: " + value))
    .filter(value -> !value.isEmpty())
    .toList();
```

Nhưng đoạn này chỉ nên được hiểu là **log chẩn đoán tùy trường hợp**. Không xác lập một hợp đồng audit rằng mỗi input phải có đúng một bản ghi và tuyệt đối không phụ thuộc vào tối ưu hóa pipeline.

### 19.2. Kiểm thử mock “đã gọi hai lần” chưa đủ cho hệ thống phân tán

Một mock có thể đếm đúng hai lần gọi `gateway.charge` khi chạy bình thường; điều đó không chứng minh:

- Giao dịch được gửi đúng một lần khi process crash.
- Timeout xảy ra sau hay trước khi server ghi nhận.
- Gateway thực sự hỗ trợ idempotency key.
- Receipt được lưu bền vững ngay khi method `save` trả về.
- Hai worker không giành cùng một job ở môi trường production.

Những bảo đảm này phải được thiết kế và kiểm thử ở **ranh giới hệ thống**, không nằm trong đặc tính của Java Stream API.

## 20. Quy trình refactor một pipeline có I/O thành hai pha

Giả sử bạn nhận đoạn code cũ:

```java
var result = orders.stream()
    .filter(Order::ready)
    .map(order -> gateway.charge(order))
    .map(receipt -> repository.saveAndReturn(receipt))
    .toList();
```

Nó trộn cả biến đổi, gọi dịch vụ và lưu dữ liệu. Một lộ trình refactor theo thứ tự:

### Bước 1 — Liệt kê mọi side effect thực tế

Đừng chỉ nhìn tên `map`; mở định nghĩa hàm hoặc tài liệu port:

| Hàm | Đọc state bên ngoài? | Ghi state bên ngoài? | Lỗi có thể xảy ra? |
| --- | --- | --- | --- |
| `Order::ready` | Không nếu Order bất biến | Không | Chủ yếu lỗi dữ liệu |
| `orderToCommand` | Không | Không | Validation/overflow |
| `gateway.charge` | Có, trạng thái dịch vụ | Có, thanh toán | Timeout, decline, lỗi server |
| `repository.save` | Có, database | Có, ghi receipt | Conflict, timeout, lỗi DB |

Mục đích là xác định ranh giới **cần chính sách vận hành**, không chỉ thay cú pháp.

### Bước 2 — Dời các phép biến đổi thuần vào `prepare`

```java
Plan plan = prepare(orders);
```

Kiểm tra trước khi thực thi:

- `orderId` hợp lệ và duy nhất.
- `amountCents` thuộc miền dữ liệu được hỗ trợ.
- Chỉ những đơn `ready` được đưa vào command list.
- Tổng được tính bằng `Math.addExact` nếu không muốn tràn số âm thầm.
- Mỗi command có key ổn định.

### Bước 3 — Định nghĩa port thay vì gọi SDK trực tiếp trong mapper

```java
interface ChargeGateway {
    ChargeReceipt charge(ChargeCommand command)
        throws GatewayException;
}

interface ReceiptStore {
    void save(ChargeReceipt receipt)
        throws StoreException;
}
```

Nhờ các interface này, code điều phối có thể được kiểm thử bằng fake, còn adapter thực tế chịu trách nhiệm chuyển HTTP/SQL failures thành lỗi hoặc kết quả nghiệp vụ có cấu trúc.

### Bước 4 — Quyết định policy tại ranh giới

Ví dụ:

- Thấy lỗi gateway chưa xác định: ghi `CHARGE_UNCONFIRMED` và chuyển đối soát.
- Thấy lỗi database khi đã có receipt: ghi `RECEIPT_WRITE_FAILED` để thử ghi lại.
- Nếu cần dừng cả batch: **dừng** ở lỗi được phân loại và trả/bảo toàn trạng thái các lệnh đã xử lý, không coi batch tự động rollback.

### Bước 5 — Xuất bản `ProcessReport` và kiểm chứng tổng

```java
ProcessReport report = execute(plan, gateway, receiptStore);

long recorded = report.results().stream()
    .filter(r -> r.status() == ExecutionStatus.RECORDED)
    .count();

long uncertain = report.results().stream()
    .filter(r ->
        r.status() == ExecutionStatus.CHARGE_UNCONFIRMED)
    .count();
```

Các tên kiểu ở đoạn này là kiểu lồng trong `SafeOrderProcessing` (mục 7); nếu dùng mã ngoài class cần import tĩnh hoặc viết đầy đủ `SafeOrderProcessing.ProcessReport`, `SafeOrderProcessing.ExecutionStatus`.

Với chính sách continue-on-known-error và không có lỗi ngoài dự kiến, số kết quả bằng số command. Trong production, vẫn cần kiểm tra trạng thái bền vững để phát hiện các job dang dở sau crash.

### Bước 6 — Thêm integration tests trước khi tăng concurrency

Ưu tiên kiểm thử:

1. Timeout trước khi gateway xử lý.
2. Timeout **sau khi** gateway xử lý.
3. Ghi receipt thất bại sau xác nhận charge.
4. Worker restart giữa hai bước.
5. Retry cùng key, payload giống và payload khác.
6. Hai worker cùng nhận một job.
7. Kết quả truy vấn trạng thái phù hợp với báo cáo batch.

Chỉ khi semantics đã rõ mới thử tăng concurrency, benchmark hoặc thêm queue.

## 21. Bài tập thực hành

### Bài 1 — Phân loại hàm thuần và hàm side effect

Cho các hàm `normalizeName`, `calculateTax`, `LocalDate.now`, `db.insert`, `http.get`, `new Dto` và `sharedCounter.incrementAndGet`. Phân loại hàm nào có thể đặt vào `map` như phép biến đổi thuần, hàm nào cần tách ra. Giải thích khi một phương thức nhận dữ liệu immutable nhưng **gọi clock** thì vẫn không thuần.

### Bài 2 — Refactor một pipeline ghi database

Biến pipeline:

```java
orders.stream()
    .filter(Order::ready)
    .map(repository::save)
    .toList();
```

thành:

1. `Plan` chứa những `SaveCommand` thuần.
2. Vòng lặp gọi `repository.save`.
3. `ProcessReport` ghi nhận mỗi command thành công hay lỗi.

Quy định liệu batch **fail-fast** hay **continue**. Không được trả một danh sách “đã lưu” mà thiếu báo cáo các command thất bại.

### Bài 3 — Timeout không chứng minh thất bại nghiệp vụ

Mô tả chuỗi sự kiện:

```text
charge(K) được gửi → gateway charge thành công → response bị mất
```

Tại sao `catch (TimeoutException) { retry(newKey); }` nguy hiểm? Đề xuất quy tắc idempotency và API tra cứu giao dịch trước khi retry.

### Bài 4 — Hai lỗi ở hai điểm khác nhau

Trong chương trình `SafeOrderProcessing`, mô phỏng:

- Gateway ném `GatewayException` cho O1.
- Store ném `StoreException` cho O3.

Kết quả mỗi đơn là gì? Có đơn nào chắc chắn chưa bị charge? Viết JUnit test đối chiếu từng `ExecutionStatus` và số lời gọi store.

### Bài 5 — Đơn trùng ID và tổng tiền tràn

Thêm hai đơn cùng `id` nhưng khác `customerId`. Kiểm chứng `prepare` từ chối trước mọi lời gọi service. Tạo thêm hai đơn có tổng amount vượt `Long.MAX_VALUE`, kiểm chứng `Math.addExact` làm pha chuẩn bị thất bại và không trả `Plan`.

### Bài 6 — Enrichment trước biến đổi thuần

Từ danh sách đơn có nhiều `customerId` trùng nhau:

1. Dùng Stream tạo danh sách customer ID phân biệt.
2. Gọi dịch vụ tra cứu profile ở một bước tường minh.
3. Trả `LookupOk` / `LookupFailed` theo từng ID.
4. Ghép các kết quả thành báo cáo bằng các phép biến đổi thuần.

Nếu một profile thiếu hoặc service timeout, lựa chọn chính sách fail-fast hay best effort và giải thích ảnh hưởng tới số liệu.

### Bài 7 — Nguồn file rất lớn

Thiết kế pipeline nhập file CSV hàng trăm GB. Vì sao `readAllLines` hoặc `Files.lines(...).toList()` trước mọi giao dịch có thể không phù hợp? Đề xuất chunk size, validation, durable intent, checkpoint và dedup key. Nêu rõ sự khác biệt giữa “một chunk hoàn tất” và “toàn bộ file hoàn tất”.

### Bài 8 — Outbox và ghi nhận sự kiện

Một ứng dụng cần cập nhật `Order.status` trong database và publish sự kiện `OrderApproved`. Vẽ transaction outbox, worker publish và consumer idempotent. Chỉ ra khoảng trống có thể dẫn đến event được publish **hơn một lần**, và vì sao `Stream.distinct()` không giải quyết được.

### Bài 9 — Giới hạn concurrency

Giả sử gateway cho phép tối đa 5 request đồng thời và 100 request/phút. Lập kế hoạch cho một coordinator xử lý 1.000 lệnh:

- Giới hạn tác vụ cùng lúc.
- Cách áp dụng rate limit.
- Deadline cho mỗi request.
- Stable idempotency key.
- Lưu kết quả từng request.
- Đối soát những request chưa rõ trạng thái.

Giải thích vì sao chỉ gọi `orders.parallelStream()` không đáp ứng đủ những yêu cầu này.

### Bài 10 — Bất biến và điều kiện đầu vào

Chứng minh `List.copyOf` giúp `Plan` không phản ánh việc caller thêm/xóa phần tử trong list gốc **sau khi tạo snapshot**. Sau đó thay `Order` bằng một class mutable có getter `amountCents` có thể bị thay đổi từ thread khác; giải thích vì sao `List.copyOf` **không deep-copy** phần tử và tại sao cần value object hoặc defensive copy.

### Bài 11 — Hợp đồng chính xác của `peek`

Viết đoạn stream sử dụng `peek` để ghi log debug. Đặt các terminal operation khác nhau như `toList`, `count`, `findFirst` trên các stream mới. Giải thích vì sao số log không phải một phép đo đáng tin cho “số phần tử đã xử lý” hoặc số hành động audit đã được ghi nhận.

### Bài 12 — Định nghĩa “hoàn thành”

Một batch có 95 receipt đã lưu, 3 charge chưa rõ trạng thái và 2 receipt lưu thất bại. Thiết kế DTO trả về cho API và dashboard. Quy định:

- Có trả HTTP 200, 207 hay trạng thái workflow bất đồng bộ không? Phụ thuộc contract API.
- Các ID nào phải đối soát?
- Điều kiện nào để báo “batch hoàn tất và không còn công việc pending”?
- Khi truy vấn lại, làm sao không tạo thêm giao dịch charge ngoài ý muốn?

## 22. Checklist thiết kế trước khi đưa vào production

- [ ] Đã xác định rõ bước nào **thuần** và bước nào có side effect bên ngoài.
- [ ] Validation/duplicate kiểm tra **trước** side effect khi có thể.
- [ ] Command có định danh và idempotency key ổn định.
- [ ] Có hợp đồng cho charge được xác nhận, decline và outcome chưa rõ.
- [ ] Ngoại lệ được phân loại; không nuốt lỗi thành `null` hoặc kết quả rỗng.
- [ ] Không dựa vào `peek` hoặc số lần mapper chạy để đảm bảo audit.
- [ ] Không phụ thuộc vào `parallelStream` để tự cung cấp rate limit/transaction.
- [ ] Đã định nghĩa fail-fast hay continue-on-error cho từng batch.
- [ ] Có dữ liệu/tiến độ bền vững để phục hồi sau process crash.
- [ ] Có cách tra cứu/đối soát request timeout.
- [ ] Ghi receipt và các bước DB dùng transaction/unique constraints phù hợp.
- [ ] Có chiến lược compensation khi nghiệp vụ yêu cầu hoàn tác giữa các hệ thống.
- [ ] Không gọi lại charge chỉ vì bước lưu receipt lỗi.
- [ ] Nguồn I/O có owner và `try-with-resources`.
- [ ] Có giới hạn batch/chunk, timeout và concurrency phù hợp.
- [ ] Báo cáo kết quả đủ các trạng thái và số lệnh còn tồn đọng.
- [ ] Đầu ra không để lộ token, thông tin thẻ hoặc raw exception nhạy cảm.
- [ ] Có unit test với fake ports và integration test với hệ thống thật.
- [ ] Đã ghi rõ Stream API **không** cung cấp exactly-once hoặc distributed transaction.

## 23. Bảng quyết định và tổng kết

| Bài toán | Cách làm thường phù hợp |
| --- | --- |
| Biến đổi dữ liệu từ record immutable sang DTO | `map` thuần trong Stream |
| Lọc các phần tử theo quy tắc nghiệp vụ | `filter` với predicate thuần |
| Tính tổng, thống kê từ tập dữ liệu ổn định | `reduce`, `collect` hoặc collector thống kê |
| Phải validate cả batch trước khi gọi hệ thống ngoài | `prepare` thuần → `Plan` immutable → `execute` |
| Gọi API cho từng lệnh và lưu trạng thái | Service coordinator với bounded concurrency và per-item result |
| Timeout sau request có thể đã được xử lý | Trạng thái **UNCONFIRMED**, tra cứu/reconcile |
| Retry một lệnh có side effect | Stable idempotency key + hợp đồng của bên nhận |
| Ghi receipt sau charge thất bại | Thử ghi lại/đối soát, **không charge lại mặc định** |
| Cập nhật DB và phát event | Transactional outbox + consumer idempotent |
| Cần ghi vào cùng database atomically | DB transaction theo hợp đồng database |
| Cần xử lý nhiều file rất lớn | Chunk/staging/checkpoint, công bố partial progress |
| Nguồn file từ `Files.lines` | `try-with-resources` trước khi đi qua ranh giới tác dụng phụ |
| Một upstream có thể bị short-circuit | Không đặt ghi audit/charge bắt buộc vào `peek`/mapper |
| Muốn giữ thứ tự báo cáo | Mang sequence ID và sắp kết quả sau khi thu; không đồng nhất với commit order |
| Cần kết quả rỗng hợp lệ | Biểu diễn riêng với lỗi dịch vụ hoặc file |
| Muốn chứng minh đúng khi lỗi | Fake ports, status assertions, integration/failure tests |

### Kết luận

**Tách các bước gọi dịch vụ và ghi dữ liệu khỏi phép biến đổi thuần** là một nguyên tắc thiết kế giúp Java Stream API phát huy đúng vai trò: **mô tả dữ liệu cần xử lý**, không giả làm một bộ điều phối giao dịch. `filter`, `map`, `reduce` và `collect` rất mạnh khi dùng để tạo kế hoạch và tổng hợp kết quả; còn HTTP, database, queue và các tác dụng phụ cần ranh giới có chính sách lỗi, trạng thái, timeout, retry, idempotency và quan sát vận hành rõ ràng.

Một pipeline ngắn chưa chắc an toàn hơn một vòng lặp có tên và hợp đồng đúng. Hãy ưu tiên **kết quả xác định ở pha thuần**, **hành động được điều phối ở pha side effect**, và **trạng thái có thể phục hồi khi lỗi**. Khi đó, cả kiểm thử, triển khai song song lẫn vận hành sau sự cố đều dễ lý giải hơn, trong khi vẫn tận dụng tốt các phép biến đổi khai báo của **JAVA_STREAM_API**.
