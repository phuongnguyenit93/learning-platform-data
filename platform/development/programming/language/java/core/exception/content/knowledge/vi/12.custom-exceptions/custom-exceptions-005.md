# Thuộc tính ngữ cảnh có kiểu và tránh dữ liệu dư thừa trong ngoại lệ tùy chỉnh Java

> **Phạm vi:** Java Core → Exception → Ngoại lệ tùy chỉnh. Một custom exception tốt không chỉ mang `message` và `stack trace`. Khi caller cần **xử lý khác nhau theo mã lỗi, định danh tài nguyên, tên trường hoặc trạng thái tác vụ**, exception có thể cung cấp **thuộc tính ngữ cảnh có kiểu rõ ràng**. Tuy nhiên thêm mọi dữ liệu vào exception không tự làm API tốt hơn: các trường trùng lặp, có thể tính từ trường khác, dễ sai lệch hoặc chứa dữ liệu nhạy cảm sẽ khiến việc xử lý và bảo trì khó khăn.

## 1. Vấn đề cần giải quyết

Hãy hình dung một dịch vụ đặt hàng từ chối yêu cầu vì số lượng đặt vượt số lượng tồn. Cách ném đơn giản:

```java
throw new IllegalArgumentException(
        "Đơn ORD-21 đặt 8 sản phẩm, chỉ còn 3");
```

Chuỗi này có thể đủ để **con người đọc log**, nhưng nếu UI cần biết chính xác nên hiện nút “giảm số lượng”, caller phải tách text hoặc suy đoán. Đó là một hợp đồng dễ vỡ: thay ngôn ngữ, dấu câu hay cách diễn đạt là code phân tích message có thể hỏng.

Một ngoại lệ tùy chỉnh có ngữ cảnh có kiểu giúp tách hai mục đích:

- **Thông tin máy có thể sử dụng ổn định:** `ErrorCode.INSUFFICIENT_STOCK`, `orderId`, `requestedQuantity`, `availableQuantity`.
- **Thông tin phục vụ con người:** `getMessage()` mô tả điều đã xảy ra. Message có thể thay đổi cách viết theo yêu cầu logging mà không ảnh hưởng code quyết định hành vi.

Nhưng cũng không nên lưu lặp `requestedQuantity` trong exception, trong một `Map` riêng, trong một chuỗi `details` và thêm một bản sao của toàn bộ `Order`. Một nguồn dữ liệu đáng tin sẽ giúp giảm nguy cơ các bản sao mâu thuẫn.

**Mục tiêu:** lưu **vừa đủ, có ý nghĩa, có kiểu rõ ràng, bất biến ở mức phù hợp, an toàn để chuyển qua tầng xử lý và không giữ dư dữ liệu**.

## 2. “Thuộc tính ngữ cảnh có kiểu” nghĩa là gì?

Một custom exception có thể định nghĩa các trường mang ngữ nghĩa riêng:

```java
final class InvalidQuantityException extends IllegalArgumentException {
    private final String orderId;
    private final int requestedQuantity;
    private final int availableQuantity;

    InvalidQuantityException(String orderId,
                             int requestedQuantity,
                             int availableQuantity) {
        super("Số lượng đặt vượt số lượng tồn");
        this.orderId = orderId;
        this.requestedQuantity = requestedQuantity;
        this.availableQuantity = availableQuantity;
    }

    String orderId() {
        return orderId;
    }

    int requestedQuantity() {
        return requestedQuantity;
    }

    int availableQuantity() {
        return availableQuantity;
    }
}
```

Đây là một **khai báo lớp hợp lệ nhưng chưa phải chương trình có `main`**. Caller nhận `InvalidQuantityException` có thể đọc trực tiếp:

```java
// Ví dụ trong một handler tương thích:
System.out.println(e.orderId());
System.out.println(e.requestedQuantity());
System.out.println(e.availableQuantity());
```

Thay vì:

```java
// Phản ví dụ: không nên parse thông điệp để đưa ra quyết định.
String message = e.getMessage();
// Tìm "ORD-" rồi tách số lượng bằng substring/regex.
```

Thuộc tính được gọi là **có kiểu** vì chúng dùng `int` cho số lượng, `String` với ngữ nghĩa rõ (hoặc kiểu ID chuyên biệt nếu cần), `enum` cho mã lỗi, `Instant` cho thời điểm, `URI` cho tài nguyên, hay một `record` để gói thông tin có liên quan. Không phải tất cả đều nên có trong cùng một exception.

### 2.1. Thế nào là ngữ cảnh hữu ích?

Một trường hữu ích khi ít nhất một trong các mục tiêu sau cần đến nó:

1. **Caller chọn cách xử lý:** mã lỗi hoặc phân loại nghiệp vụ.
2. **Chẩn đoán:** ID tác vụ/tài nguyên giúp kết hợp với log mà không đưa vào dữ liệu nhạy cảm.
3. **Phản hồi người dùng:** tên trường và giới hạn hợp lệ để hiển thị hướng dẫn sửa.
4. **Quan sát hệ thống:** mã subsystem hoặc request ID để liên kết sự kiện.
5. **Khôi phục an toàn:** thông tin được phép dùng để chọn nguồn thay thế, retry có điều kiện hoặc yêu cầu đầu vào mới.

Đừng thêm trường chỉ vì “có sẵn ở thời điểm ném”. Ngoại lệ nên lưu **ngữ cảnh tối thiểu cần cho hợp đồng xử lý lỗi**.

## 3. So sánh ba cấp độ biểu diễn

| Cách thiết kế | Ví dụ | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| Chỉ `message` | `throw new IllegalArgumentException("...");` | Ngắn gọn, đủ cho lỗi ít cần xử lý đặc biệt | Không cung cấp trường typed cho caller |
| `Map<String,Object>` tùy ý | `Map.of("orderId", id, "qty", 8)` | Dễ mở rộng, phù hợp telemetry không có schema cố định | Key sai chính tả, sai kiểu runtime, khó khám phá, dễ lộ dữ liệu |
| Trường có kiểu / `record` / `enum` | `ErrorCode`, `OrderContext` | Compile-time type checking, API rõ, IDE hỗ trợ, dễ viết test | Thêm lớp/API; cần cân nhắc thay đổi schema và tính tương thích |

**Không có quy tắc** mọi exception phải có `record` hay `enum`. Nếu tầng gọi chỉ cần nhận biết “tham số không hợp lệ”, `IllegalArgumentException` với message tốt có thể đủ. Dùng custom exception khi có **hợp đồng xử lý đặc thù thực sự**.

## 4. Chọn cây kế thừa cho custom exception

Mọi exception Java đều thuộc hệ `Throwable`:

```text
Throwable
├── Exception
│   ├── IOException
│   └── RuntimeException
│       ├── IllegalArgumentException
│       └── IllegalStateException
└── Error
```

Nếu đây là vi phạm hợp đồng của caller (như số lượng âm hoặc không đủ tồn kho theo API cụ thể), một subclass của `IllegalArgumentException` hoặc `RuntimeException` có thể hợp lý. Nếu caller **được kỳ vọng xử lý có kiểm tra compile-time** (ví dụ thất bại một thao tác có thể phục hồi theo hợp đồng), subclass của `Exception` checked có thể hữu ích.

Ví dụ định nghĩa **checked exception**:

```java
final class ImportFailedException extends Exception {
    ImportFailedException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Ví dụ **unchecked exception**:

```java
final class InvalidRequestException extends IllegalArgumentException {
    InvalidRequestException(String message) {
        super(message);
    }
}
```

Đây là các lớp minh họa, không có `main`. Việc ngoại lệ checked/unchecked **không quyết định** liệu các thuộc tính ngữ cảnh nên có kiểu hay không. Hai việc phải xem riêng: hợp đồng xử lý lỗi và dữ liệu lỗi cần mang theo.

### 4.1. Đừng tạo `Error` cho lỗi nghiệp vụ

`Error` dành cho nhánh lỗi mà ứng dụng thông thường không nên xem như sự cố nghiệp vụ có thể phục hồi. Một lớp `InvalidOrderError extends Error` chỉ để mang `orderId` thường làm sai ý nghĩa, đồng thời bỏ qua những handler `catch(Exception)` thông thường. Nếu cần thông báo vi phạm hợp đồng hay sự cố nghiệp vụ, dùng kiểu exception phù hợp.

## 5. Java 17 — thiết kế mã lỗi, context `record` và ngoại lệ chuyên biệt

Ví dụ hoàn chỉnh sau có:

- `enum ErrorCode` thay chuỗi mã lỗi tự do.
- `record OrderContext` gom các thuộc tính **cùng thuộc một tình huống**.
- `InsufficientStockException` kế thừa `IllegalArgumentException`, giữ code và context typed.
- Handler chọn hành động bằng `code()`, không parse `getMessage()`.

Tạo tệp **`TypedOrderExceptionDemo.java`**:

```java
import java.util.Objects;

public class TypedOrderExceptionDemo {
    enum ErrorCode {
        INSUFFICIENT_STOCK,
        INVALID_QUANTITY
    }

    record OrderContext(String orderId,
                        int requestedQuantity,
                        int availableQuantity) {
        OrderContext {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("Thiếu orderId");
            }
            if (requestedQuantity < 0 || availableQuantity < 0) {
                throw new IllegalArgumentException(
                        "Số lượng không được âm");
            }
        }
    }

    static final class InsufficientStockException
            extends IllegalArgumentException {
        private final ErrorCode code;
        private final OrderContext context;

        InsufficientStockException(OrderContext context) {
            super("Số lượng đặt vượt số lượng tồn");
            this.code = ErrorCode.INSUFFICIENT_STOCK;
            this.context = Objects.requireNonNull(context);
        }

        ErrorCode code() {
            return code;
        }

        OrderContext context() {
            return context;
        }
    }

    static void reserve(OrderContext context) {
        if (context.requestedQuantity() >
                context.availableQuantity()) {
            throw new InsufficientStockException(context);
        }
        System.out.println("OK: " + context.orderId());
    }

    public static void main(String[] args) {
        OrderContext normal = new OrderContext("ORD-1", 2, 5);
        OrderContext shortage = new OrderContext("ORD-2", 7, 3);

        reserve(normal);

        try {
            reserve(shortage);
        } catch (InsufficientStockException e) {
            System.out.println("Code: " + e.code());
            System.out.println("Order: " + e.context().orderId());
            System.out.println("Requested: "
                    + e.context().requestedQuantity());
            System.out.println("Available: "
                    + e.context().availableQuantity());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 TypedOrderExceptionDemo.java
java TypedOrderExceptionDemo
```

**Stdout chính xác:**

```text
OK: ORD-1
Code: INSUFFICIENT_STOCK
Order: ORD-2
Requested: 7
Available: 3
Message: Số lượng đặt vượt số lượng tồn
```

**Điểm học được:**

1. Caller biết lỗi thiếu hàng qua **loại exception** hoặc `ErrorCode.INSUFFICIENT_STOCK`, không phụ thuộc text tiếng Việt.
2. `OrderContext` chỉ chứa thông tin của tình huống đặt hàng. Các trường số lượng là `int`, không phải text cần parse lại.
3. `code` được đặt cố định trong subclass này; nếu chỉ duy nhất một loại lỗi có thể phát sinh, thêm cả subclass chuyên biệt **và** mã cố định có thể dư. Phần sau giải thích cách chọn một nguồn sự thật.
4. `record` tự cung cấp accessor, `equals`, `hashCode` và `toString` dựa trên các component. **Không nên log `toString` mặc định của record nếu nó có dữ liệu nhạy cảm.**
5. Điều kiện bất biến trong constructor record giúp tránh tạo một `OrderContext` có số lượng âm. Đây là validation cho **dữ liệu ngữ cảnh**, không thay thế toàn bộ validation đầu vào của nghiệp vụ.
6. `InsufficientStockException` lưu một tham chiếu `OrderContext` thay vì lưu thêm ba bản sao riêng của `orderId`, `requestedQuantity`, `availableQuantity`.

### 5.1. Nếu đã có subtype chuyên biệt, có cần thêm `ErrorCode`?

Không phải lúc nào cũng cần. Với handler:

```java
catch (InsufficientStockException e) {
    // Loại Java đã đủ để phân biệt lỗi thiếu hàng.
}
```

việc lưu thêm `code = INSUFFICIENT_STOCK` có thể **lặp lại cùng một sự thật**. Tuy nhiên mã lỗi vẫn hữu ích nếu API cần trả mã ổn định cho client, ghi metric thống nhất giữa nhiều loại exception, hoặc mapping sang hệ thống ngoài.

Hãy quyết định:

- Nếu toàn bộ hệ thống thuần Java và subtype đủ rõ: có thể chỉ giữ **kiểu exception** cùng context.
- Nếu mã lỗi là một phần giao thức/telemetry: giữ một mã ổn định; cân nhắc **derive code từ subtype** thay vì lưu bản sao có thể không đồng bộ.
- Nếu một loại exception bao phủ nhiều tình huống: `enum` `code` có thể là dữ liệu thực sự cần thiết.
- Nếu mã lỗi được lưu song song với subtype, thiết kế constructor tránh nhận một mã bất kỳ trái với subtype.

### 5.2. Không truyền code tùy ý vào subclass có ý nghĩa cố định

Một thiết kế dễ tạo mâu thuẫn:

```java
// Phản ví dụ thiết kế, không phải chương trình đầy đủ.
new InsufficientStockException(
        ErrorCode.INVALID_QUANTITY, context);
```

Nếu cho phép constructor như vậy, kiểu Java nói “không đủ tồn” nhưng code lại nói “số lượng không hợp lệ”. Nên **suy ra mã cố định từ loại exception**, hoặc đổi thiết kế sang một exception chung với code được kiểm soát, thay vì tạo hai trường hợp đồng trái nhau.

## 6. Quy tắc “một nguồn sự thật” cho ngữ cảnh

Dữ liệu dư thừa có nhiều dạng, không chỉ là hai trường có tên giống nhau.

| Dữ liệu | Dạng dư thừa | Thiết kế thường tốt hơn |
| --- | --- | --- |
| `orderId` trong context và trường riêng cùng object | Hai nơi giữ cùng ID | Một `OrderContext.orderId()` |
| `amount` và `amountText` | Text có thể suy từ số | Lưu số, format khi hiển thị |
| `status` và `isFailure` | Boolean suy từ trạng thái | Chỉ lưu status có kiểu |
| `errorCode` và `errorName` | Tên có thể suy từ enum | Chỉ lưu `ErrorCode`, lấy `name()` khi cần |
| `cause` và `originalException` | Hai tham chiếu đến cùng lỗi gốc | Dùng `getCause()` nếu đó là quan hệ nguyên nhân |
| `message` và `description` cùng copy | Hai chuỗi mô tả cùng ý nghĩa | Thông điệp phục vụ người đọc; ngữ cảnh riêng dùng typed fields |
| `timestamp` và `ageMillis` | `ageMillis` thay đổi theo thời gian | Lưu thời điểm cần thiết, tính tuổi ở thời điểm đọc |
| `userProfile` đầy đủ và `userId` | Giữ quá nhiều dữ liệu, rủi ro PII | Chỉ ID an toàn hoặc request ID |
| `Map<String,Object>` và các getter có kiểu cùng dữ liệu | Hai schema phải đồng bộ | Chọn typed API là nguồn chính; tạo map chỉ khi cần xuất |
| `Throwable` được lưu trong một field riêng và truyền vào `super(message, cause)` | Hai tham chiếu giống cause | Lấy `getCause()`, không giữ bản sao |

**Không cấm message đề cập lại số lượng để người đọc hiểu.** “Tránh dư thừa” chủ yếu nói đến **trạng thái nguồn dữ liệu** và các bản sao có thể lệch nhau. Message thường là **biểu diễn** của dữ liệu hoặc phần mô tả tự nhiên; quan trọng là **không parse ngược message để ra quyết định**.

### 6.1. Chỉ lưu số liệu nền, tính giá trị dẫn xuất khi cần

Ví dụ có `requestedQuantity` và `availableQuantity`:

```java
int shortage = Math.max(
        0, context.requestedQuantity()
                - context.availableQuantity());
```

Nếu `shortage` chỉ là phép tính xác định từ hai trường kia, không cần trường thứ ba `shortage` trong exception. Lưu cả ba tạo rủi ro một constructor hoặc refactor tính sai.

**Ngoại lệ có chủ đích:** đôi khi cần lưu “snapshot” của giá trị dẫn xuất do quy tắc tính phụ thuộc tỷ giá, thời điểm, phiên bản thuật toán hoặc trạng thái ngoài. Khi đó giá trị không thực sự suy lại được từ hai input hiện có và có thể đáng lưu, nhưng phải mô tả ý nghĩa snapshot.

### 6.2. Đừng lưu cả object domain lớn chỉ để lấy ID

Không nên:

```java
// Ví dụ phản thiết kế; Order là đối tượng nghiệp vụ lớn.
class FailedOrderException extends RuntimeException {
    private final Order entireOrder;
}
```

Đây không phải một lớp hoàn chỉnh. Giữ `entireOrder` trong Throwable có thể vô tình kéo theo dữ liệu lớn, trạng thái mutable, liên kết đến session/connection, hoặc dữ liệu nhạy cảm. Exception có thể tồn tại lâu hơn thao tác gây lỗi do log queue, retry framework hoặc storage.

Thay bằng **định danh tối thiểu** và một số trường có ý nghĩa phục hồi/chẩn đoán:

```java
private final String orderId;
private final ErrorCode code;
```

Những trường này phải có ngữ nghĩa rõ. Với ID có nhiều loại dễ nhầm, có thể dùng value object typed hơn là `String` chung.

## 7. Giá trị bất biến: `final` là cần nhưng chưa đủ

Đối tượng exception bản thân **không hoàn toàn bất biến**, vì `Throwable` có các API như `addSuppressed` và `setStackTrace`. Tuy vậy, **các trường ngữ cảnh tùy chỉnh** nên được giữ ổn định sau khi exception được tạo để caller, logger và nhiều thread không quan sát các giá trị khác nhau.

Điều cần kiểm tra:

- Dùng `private final` cho trường context.
- Kiểm tra `null` và invariants ở constructor.
- Không cung cấp setter thay đổi error code hoặc ID sau khi lỗi đã xảy ra.
- Nếu context chứa `List`/`Set`/`Map`, tạo defensive copy bất biến thích hợp.
- Với các object mutable lồng bên trong collection, copy collection **chưa phải deep copy**. Ưu tiên component immutable hoặc snapshot các trường cần thiết.
- Không lưu các resource đang mở hoặc object domain có vòng đời dài/ngắn không kiểm soát.
- Hạn chế đưa exception object có mutable context qua nhiều thread nếu không có hợp đồng concurrency rõ.

### 7.1. Java 17 — record với `List.copyOf` để giữ snapshot

Tạo tệp **`ImmutableContextDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ImmutableContextDemo {
    record BatchContext(String batchId, List<String> itemIds) {
        BatchContext {
            Objects.requireNonNull(batchId, "batchId");
            itemIds = List.copyOf(
                    Objects.requireNonNull(itemIds, "itemIds"));
        }
    }

    static final class BatchFailedException
            extends RuntimeException {
        private final BatchContext context;

        BatchFailedException(BatchContext context) {
            super("Lô xử lý thất bại");
            this.context = Objects.requireNonNull(context);
        }

        BatchContext context() {
            return context;
        }
    }

    public static void main(String[] args) {
        List<String> original = new ArrayList<>(
                List.of("A", "B"));

        BatchContext snapshot =
                new BatchContext("B-1", original);
        BatchFailedException e =
                new BatchFailedException(snapshot);

        original.add("C");

        System.out.println("Gốc: " + original.size());
        System.out.println("Snapshot: "
                + e.context().itemIds().size());
        System.out.println("Items: "
                + String.join(",", e.context().itemIds()));

        try {
            e.context().itemIds().add("D");
        } catch (UnsupportedOperationException ignored) {
            System.out.println("Không thể sửa snapshot");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ImmutableContextDemo.java
java ImmutableContextDemo
```

Stdout:

```text
Gốc: 3
Snapshot: 2
Items: A,B
Không thể sửa snapshot
```

**Vì sao có ý nghĩa?**

1. `original` là danh sách mutable do bên ngoài giữ.
2. `List.copyOf` tạo một danh sách không sửa được, với các phần tử `String` vốn immutable.
3. Sửa `original` sau khi tạo exception không làm thay đổi context bên trong.
4. Getter `context().itemIds()` không cho caller thêm phần tử.
5. Nếu danh sách chứa những object mutable khác `String`, `List.copyOf` chỉ bảo vệ cấu trúc danh sách, **không biến các phần tử mutable thành immutable**.

Lưu ý: `List.copyOf` từ chối phần tử `null`. Nếu `null` có ý nghĩa trong mô hình ngữ cảnh, cần hợp đồng khác, nhưng thông thường danh sách ID không nên chứa `null`.

## 8. Dùng `enum` hay `record` cho mã lỗi và các trường ngữ cảnh?

Một `enum` tốt cho tập giá trị đóng, có danh sách hữu hạn và ý nghĩa ổn định:

```java
enum ValidationCode {
    MISSING_FIELD,
    INVALID_FORMAT,
    OUT_OF_RANGE
}
```

Một `record` phù hợp để mô tả nhóm dữ liệu bất biến ở mức tham chiếu và có hành vi value-based:

```java
record FieldIssue(String field, ValidationCode code,
                  int min, int max) {
}
```

Đây là ví dụ kiểu khai báo, không có `main`. Hãy xét liệu mọi trường đều có ý nghĩa cho **mọi giá trị code**. Nếu `MISSING_FIELD` không liên quan đến `min`/`max`, một record chứa cả bốn trường có thể tạo trạng thái khó hiểu.

Các cách đơn giản hơn:

- Chia thành loại context riêng cho từng nhóm lỗi nếu schema thực sự khác nhau.
- Dùng một `ErrorCode` và field ID, chỉ thêm giới hạn khi loại lỗi thực sự cần.
- Dùng sealed hierarchy hoặc subtype chuyên biệt khi hợp đồng đủ phức tạp; không bắt buộc cho mọi hệ thống.
- Tránh “mega context” với hàng chục trường `null` và flags khó nhất quán.

### 8.1. Trường bắt buộc và optional

Một thuộc tính bắt buộc nên được xác nhận ngay ở constructor. Ví dụ:

```java
this.orderId = Objects.requireNonNull(orderId, "orderId");
```

Với giá trị tùy chọn, phải có chính sách rõ: `null` có thể là hợp đồng hợp lệ trong phạm vi nội bộ, hoặc sử dụng cách biểu diễn có nghĩa riêng. Không thêm `Optional` field theo thói quen mà không cân nhắc serialization, API và cách dùng.

### 8.2. Không coi mọi chuỗi `String` là “mất type safety”

`orderId` dưới dạng `String` đôi khi là lựa chọn hợp lý khi API hiện tại giao tiếp bằng chuỗi. Type safety là mức độ phù hợp với hợp đồng, không phải số lượng wrapper class. Nếu thường xuyên nhầm `userId` và `orderId` đều là `String`, một typed ID như `record OrderId(String value)` có thể giảm nhầm lẫn đáng kể.

## 9. Không nhân bản cause và suppressed vào các trường riêng

`Throwable` đã có:

```java
Throwable getCause()
Throwable[] getSuppressed()
StackTraceElement[] getStackTrace()
String getMessage()
```

Vì vậy custom exception thông thường **không cần** thêm:

```java
// Thiết kế dư thừa, KHÔNG khuyến nghị:
private final Throwable originalException;
private final String originalMessage;
private final StackTraceElement[] originalStack;
```

Nếu `originalException` chính là cause, truyền nó cho `super(message, cause)` và đọc lại qua `getCause()`. Lưu thêm `originalMessage` và mảng stack làm tăng bộ nhớ, phức tạp vòng đời và có thể giữ bản chụp không cần thiết.

Tương tự, nếu try-with-resources đã gắn các lỗi đóng qua `addSuppressed`, không cần thêm `List<Throwable> cleanupErrors` song song, trừ khi đó là cấu trúc nghiệp vụ khác với ý nghĩa độc lập.

### 9.1. `message` không thay thế context typed

Không thể nói ngược rằng vì `getMessage()` đã chứa `orderId` nên mọi trường typed là dư. Message có mục đích hỗ trợ người đọc và có thể thay đổi theo ngôn ngữ. Nếu caller cần order ID để truy cứu hoặc API phải trả mã lỗi, typed context mới là **dữ liệu hợp đồng**.

Một thiết kế nhất quán có thể:

- Lưu `orderId` và `ErrorCode` ở các trường typed.
- Dùng một message ngắn, ví dụ “Không đủ tồn kho”.
- Khi log, kết hợp các getter để hiển thị có cấu trúc.
- Khi trả API, map code/context sang response được kiểm soát.
- Không tách `getMessage()` để lấy lại order ID.

### 9.2. Ranh giới giữa cause và context

`cause` trả lời “Throwable nào đã dẫn đến exception này?”. `context` trả lời “trường hợp/định danh/tham số nào liên quan?”. Một `IOException` nên là cause nếu nó thực sự gây ra failure. Không nên đưa `IOException` vào `Map<String,Object>` của context để thay cause chain.

## 10. Java 17 — checked exception có context typed và giữ cause

Tạo tệp **`PaymentProcessingDemo.java`**:

```java
import java.io.IOException;
import java.util.Objects;

public class PaymentProcessingDemo {
    enum FailureCode {
        PROVIDER_UNAVAILABLE,
        INVALID_RESPONSE
    }

    record PaymentContext(String transactionId, String providerCode) {
        PaymentContext {
            Objects.requireNonNull(transactionId, "transactionId");
            Objects.requireNonNull(providerCode, "providerCode");
        }
    }

    static final class PaymentProcessingException extends Exception {
        private final FailureCode failureCode;
        private final PaymentContext context;

        PaymentProcessingException(FailureCode failureCode,
                                   PaymentContext context,
                                   Throwable cause) {
            super("Không thể xử lý thanh toán", cause);
            this.failureCode =
                    Objects.requireNonNull(failureCode);
            this.context = Objects.requireNonNull(context);
        }

        FailureCode failureCode() {
            return failureCode;
        }

        PaymentContext context() {
            return context;
        }
    }

    static void invokeProvider() throws IOException {
        throw new IOException("Kết nối thất bại");
    }

    static void charge(PaymentContext context)
            throws PaymentProcessingException {
        try {
            invokeProvider();
        } catch (IOException e) {
            throw new PaymentProcessingException(
                    FailureCode.PROVIDER_UNAVAILABLE,
                    context, e);
        }
    }

    public static void main(String[] args) {
        PaymentContext context =
                new PaymentContext("TX-17", "PROVIDER-A");
        try {
            charge(context);
        } catch (PaymentProcessingException e) {
            System.out.println("Code: " + e.failureCode());
            System.out.println("Transaction: "
                    + e.context().transactionId());
            System.out.println("Provider: "
                    + e.context().providerCode());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PaymentProcessingDemo.java
java PaymentProcessingDemo
```

Stdout:

```text
Code: PROVIDER_UNAVAILABLE
Transaction: TX-17
Provider: PROVIDER-A
Cause: IOException
Message: Không thể xử lý thanh toán
```

**Diễn giải:**

- `PaymentProcessingException extends Exception` là **checked exception**, nên `charge` khai báo `throws PaymentProcessingException`.
- `FailureCode` cho phép caller chọn chính sách theo một giá trị ổn định, không dùng `getMessage().contains("thanh toán")`.
- `PaymentContext` chứa transaction ID và mã nhà cung cấp cần cho điều tra. Không giữ object thanh toán đầy đủ hoặc số thẻ.
- `IOException` gốc được truyền vào `super(message, cause)`. Nó **không** được lưu lặp trong field `originalIOException`.
- `getCause()` cung cấp đường chẩn đoán lỗi tầng I/O.
- Mã ví dụ không thực hiện thanh toán thực: chỉ minh họa thiết kế hợp đồng lỗi và đầu ra có thể tái tạo.

### 10.1. Vì sao không dùng `String failureCode`?

Có thể dùng chuỗi nếu mã lỗi phải khớp với giao thức ngoài và tập giá trị thay đổi động. Nhưng trong một module Java có tập mã cố định, `enum` giúp compiler và IDE nhận biết lựa chọn; giảm lỗi chính tả và giúp logic `switch` rõ ràng.

Khi ánh xạ ra HTTP/JSON, **đừng tự động lấy `enum.ordinal()` làm mã lỗi ổn định**: thứ tự enum có thể thay đổi. Dùng tên hoặc một trường mã giao thức được kiểm soát nếu API công khai yêu cầu tương thích dài hạn.

## 11. Chọn context dựa trên người xử lý lỗi

Cùng một failure có thể được quan sát ở các tầng khác nhau:

| Người đọc exception | Dữ liệu thường cần | Không nên tự nhét vào exception |
| --- | --- | --- |
| Caller Java | Loại exception, error code, định danh, field lỗi | Bản sao toàn bộ request |
| UI/Form validation | Tên trường, mã validation, giới hạn cần thiết | Stack trace, SQL, token |
| Dịch vụ điều phối | ID tác vụ, giai đoạn, thông tin retry phù hợp | `Connection`, `InputStream` đang mở |
| Hệ thống logging | Request/correlation ID, code, cause, stack | Password hoặc khóa bí mật |
| Client API bên ngoài | Mã lỗi công khai và thông điệp an toàn | Tên class nội bộ, đường file, cause chain thô |
| Hệ thống metric | Code hữu hạn/cardinality thấp | orderId, userId hoặc mã transaction làm nhãn metric cao-cardinality |

**Tối thiểu hóa ngữ cảnh không đồng nghĩa bỏ thông tin cần thiết**. Ví dụ một request ID an toàn có thể giúp liên kết log, nhưng không nhất thiết lưu nó trong mọi exception nếu logging context (MDC hoặc tracing context) đã có và lifecycle được quản lý đúng.

### 11.1. Không đẩy mọi ngữ cảnh vào exception

Nếu một thông tin chỉ dùng để log ở một tầng mà không cần đi theo exception, có thể truyền qua logging context/tracing phù hợp. Ngược lại, nếu caller thực sự cần biết field gây lỗi để xử lý, đặt field typed trong exception có thể rõ ràng hơn phụ thuộc một cơ chế log side-channel.

Câu hỏi thực dụng là **ai chịu trách nhiệm sử dụng thông tin, trong bao lâu và ở đâu**.

## 12. Dữ liệu nhạy cảm, dữ liệu lớn và bảo mật

Ngoại lệ có thể bị log tự động, hiển thị trong crash report, gửi tới hệ thống giám sát hoặc giữ lại trong queue; các thuộc tính của nó có thể bị truy cập qua debug/reflection/serialization tùy môi trường.

Tránh đưa vào context:

- Password, access token, refresh token, session cookie hoặc khóa bí mật.
- Số thẻ thanh toán đầy đủ, dữ liệu xác thực, toàn bộ hồ sơ người dùng.
- Body request chưa được lọc, JSON chứa thông tin cá nhân hoặc header `Authorization`.
- Stream/connection và đối tượng có vòng đời ngoài ý định của exception.
- Collection cực lớn hoặc object graph có thể khiến memory retention tăng.
- Các giá trị mà caller không có quyền truy cập.

Thay vào đó, chọn **ID tham chiếu không nhạy cảm**, mã lỗi, tên trường cho phép công khai và những giá trị đã được kiểm soát. Ngay cả ID cũng có thể là dữ liệu cần bảo vệ theo ngữ cảnh hệ thống; không có danh sách “luôn an toàn” cho mọi ứng dụng.

### 12.1. Java 17 — typed context nhưng không giữ giá trị bí mật

Tạo tệp **`SafeValidationContextDemo.java`**:

```java
import java.util.Objects;

public class SafeValidationContextDemo {
    enum Field {
        API_TOKEN,
        EMAIL,
        AMOUNT
    }

    enum ValidationCode {
        MISSING,
        INVALID
    }

    static final class SafeValidationException
            extends IllegalArgumentException {
        private final Field field;
        private final ValidationCode code;
        private final String requestId;

        SafeValidationException(Field field,
                                ValidationCode code,
                                String requestId) {
            super("Dữ liệu đầu vào không hợp lệ");
            this.field = Objects.requireNonNull(field);
            this.code = Objects.requireNonNull(code);
            this.requestId =
                    Objects.requireNonNull(requestId);
        }

        Field field() {
            return field;
        }

        ValidationCode code() {
            return code;
        }

        String requestId() {
            return requestId;
        }
    }

    static void checkToken(String token, String requestId) {
        if (token == null || token.isBlank()) {
            throw new SafeValidationException(
                    Field.API_TOKEN,
                    ValidationCode.MISSING,
                    requestId);
        }
    }

    public static void main(String[] args) {
        try {
            checkToken("", "REQ-42");
        } catch (SafeValidationException e) {
            System.out.println("Field: " + e.field());
            System.out.println("Code: " + e.code());
            System.out.println("Request: " + e.requestId());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SafeValidationContextDemo.java
java SafeValidationContextDemo
```

Stdout:

```text
Field: API_TOKEN
Code: MISSING
Request: REQ-42
Message: Dữ liệu đầu vào không hợp lệ
```

**Tại sao an toàn hơn?** Exception chỉ chứa tên trường và mã lỗi, không mang token đầu vào. Điều đó không thay cho các biện pháp bảo vệ còn lại, nhưng giảm rủi ro vô tình log chính giá trị bí mật trong `toString()`, message hoặc object context.

Cũng không nên gọi `getMessage()` với một chuỗi được tạo từ toàn bộ token: nhiều framework log message mặc định.

### 12.2. Đừng serialize nguyên trạng exception cho client

Một response API nên là một DTO được chọn lọc, ví dụ `{code, field, requestId, safeMessage}`. Không trả thẳng exception, stack trace, cause, suppressed và toàn bộ custom fields. Khác biệt này vừa liên quan bảo mật vừa giúp hợp đồng API độc lập với implementation Java.

## 13. Thông điệp người đọc và mã cho máy

`getMessage()` là văn bản; không bảo đảm không đổi giữa phiên bản, ngôn ngữ, cấu hình hoặc mức chi tiết. `errorCode` typed dùng khi machine logic cần chính sách ổn định.

Ví dụ handler hợp lý:

```java
switch (e.code()) {
    case INSUFFICIENT_STOCK ->
            System.out.println("Đề xuất giảm số lượng");
    case INVALID_QUANTITY ->
            System.out.println("Yêu cầu số lượng hợp lệ");
}
```

Đây là mảnh code minh họa cần biến `e` có accessor `code()` trả `ErrorCode`. Mục tiêu là **không phân nhánh theo substring message**.

Nếu ứng dụng đa ngôn ngữ, thường lưu code/field và map sang thông điệp theo locale tại **tầng hiển thị**, thay vì đặt một chuỗi đã địa phương hóa làm nguồn sự thật duy nhất trong exception.

### 13.1. Lỗi về thứ tự ưu tiên

Nếu handler phân loại theo subtype, đôi khi **không cần mã lỗi**. Nếu handler phân loại theo mã lỗi, đôi khi **không cần subclass cho từng mã**. Không nhất thiết nên tạo hai hệ phân loại song song rồi cố đồng bộ tất cả mapping.

Hãy chọn một thiết kế mạch lạc và cung cấp adapter/mapping khi cần giao tiếp với tầng ngoài, thay vì lưu đồng thời nhiều bản sao trong mọi Throwable.

## 14. Bảo toàn quan hệ `cause` và `suppressed`

Khi một lỗi tầng thấp gây ra lỗi tầng cao:

```java
try {
    callExternalService();
} catch (java.io.IOException e) {
    throw new ServiceOperationException(
            "Không thể gọi dịch vụ", context, e);
}
```

Đây là đoạn minh họa, giả định `ServiceOperationException` có constructor đúng. Thuộc tính `context` mô tả tác vụ (ví dụ ID và pha), `cause` là exception đã phát sinh. Hai thứ **không thay thế nhau**.

Trong try-with-resources, lỗi đóng tài nguyên có thể được gắn dưới dạng **suppressed exception** vào primary. Không nên tự nhân bản chúng thành `List<Throwable> closeFailures` trong custom exception nếu dữ liệu `getSuppressed()` đã đủ.

### 14.1. Java 17 — context và cause là hai trách nhiệm riêng

Tạo tệp **`ContextWithCauseDemo.java`**:

```java
import java.io.IOException;
import java.util.Objects;

public class ContextWithCauseDemo {
    record TaskContext(String taskId, String phase) {
        TaskContext {
            Objects.requireNonNull(taskId);
            Objects.requireNonNull(phase);
        }
    }

    static final class TaskFailedException
            extends RuntimeException {
        private final TaskContext context;

        TaskFailedException(TaskContext context, Throwable cause) {
            super("Tác vụ thất bại", cause);
            this.context = Objects.requireNonNull(context);
        }

        TaskContext context() {
            return context;
        }
    }

    public static void main(String[] args) {
        IOException original =
                new IOException("Nguồn dữ liệu mất kết nối");
        TaskFailedException error = new TaskFailedException(
                new TaskContext("JOB-9", "READ"),
                original);

        System.out.println("Task: " + error.context().taskId());
        System.out.println("Phase: " + error.context().phase());
        System.out.println("Message: " + error.getMessage());
        System.out.println("Cause: "
                + error.getCause().getClass().getSimpleName());
        System.out.println("Suppressed: "
                + error.getSuppressed().length);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ContextWithCauseDemo.java
java ContextWithCauseDemo
```

Stdout:

```text
Task: JOB-9
Phase: READ
Message: Tác vụ thất bại
Cause: IOException
Suppressed: 0
```

Exception giữ `TaskContext` cho mục đích nhận diện tác vụ, còn `IOException` nằm trong `getCause()`. Không cần trường thứ hai `private IOException originalIOException`. Vì chương trình không có lỗi phụ từ đóng/dọn, suppressed count bằng `0`.

## 15. Những quy tắc constructor quan trọng

Constructor của subclass `Throwable` nên thiết lập đúng state ngay từ đầu:

```java
public final class DataImportException extends Exception {
    private final String importId;
    private final FailureCode code;

    public DataImportException(String importId,
                               FailureCode code,
                               Throwable cause) {
        super("Nhập dữ liệu thất bại", cause);
        this.importId =
                java.util.Objects.requireNonNull(importId);
        this.code =
                java.util.Objects.requireNonNull(code);
    }

    public String importId() {
        return importId;
    }

    public FailureCode code() {
        return code;
    }
}
```

Đây là **mẫu lớp**, giả sử `FailureCode` đã được định nghĩa và tệp/lớp được đặt đúng quy tắc Java. Không phải chương trình standalone.

Đảm bảo:

- Lời gọi `super(message, cause)` được đặt đúng theo quy tắc constructor Java.
- Trường bắt buộc được validate; dùng `Objects.requireNonNull` khi cần.
- Không lưu bản sao `cause`; gọi `getCause()` khi cần.
- Không mở file, gọi mạng hay thao tác lớn trong constructor exception; exception nên nhẹ, dễ tạo khi đường lỗi xảy ra.
- Không gọi method có thể override từ constructor nếu nó phụ thuộc field subclass chưa khởi tạo xong.
- Cân nhắc constructor overload nếu caller có cả trường hợp có/không có cause; đừng tạo overload vô nghĩa không ai sử dụng.
- Thông điệp ngắn, không chứa dữ liệu cần bảo vệ.

### 15.1. Nếu gọi `super` rồi validate field mới thì sao?

Một số validation có thể ném `NullPointerException` hoặc `IllegalArgumentException` trong constructor trước khi exception dự định được tạo xong. Điều đó hợp lệ về mặt Java nhưng caller sẽ thấy lỗi xây dựng exception, không phải exception mong muốn. Cần xác định **ngữ cảnh nào luôn có sẵn** ở đường lỗi và thiết kế constructor để các giá trị bắt buộc thực sự có thể cung cấp.

Không làm “context required” giả nếu thực tế nhiều đường lỗi không có ID. Có thể tách loại exception hoặc dùng hợp đồng nullable được ghi rõ khi phù hợp.

## 16. Lựa chọn lưu snapshot thay vì tham chiếu đến trạng thái đang thay đổi

Giả sử một `Order` có trạng thái mutable, được giữ làm field:

```java
// Anti-pattern khi caller có thể tiếp tục sửa order.
private final Order order;
```

Dù field là `final`, **đối tượng `order` vẫn có thể thay đổi** sau khi exception được tạo. Khi log ở thời điểm muộn hơn, dữ liệu hiện tại không còn phản ánh trạng thái khi lỗi xảy ra.

Thay bằng dữ liệu snapshot:

```java
record QuantitySnapshot(String orderId,
                        int requested,
                        int availableAtFailure) {
}
```

Một `record` chứa `String` và `int` như trên là value context đơn giản và ổn định. Tên `availableAtFailure` giúp người đọc hiểu giá trị là **snapshot tại thời điểm xảy ra lỗi**, không phải lượng tồn hiện hành.

Đây là khác biệt quan trọng:

- “Available quantity” hiện tại thuộc domain store và có thể thay đổi.
- “Available at failure” là quan sát trong một lần xử lý.
- Nếu caller muốn lấy lượng tồn **mới nhất**, nó phải gọi nguồn dữ liệu phù hợp, không coi exception chứa state live.

### 16.1. Snapshot không tự là deep copy

Record có `List<OrderLine>` mà `OrderLine` mutable có thể vẫn thay đổi qua tham chiếu. `List.copyOf` chỉ bảo vệ cấu trúc danh sách, không sao chép toàn bộ object con. Tùy mức rủi ro, chọn component immutable, chuyển thành các ID/giá trị primitive, hoặc viết logic sao chép sâu có mục đích.

## 17. Logging và serialization: hệ quả của việc thêm field

Java `Throwable` triển khai `Serializable`, nhưng điều đó **không** có nghĩa mọi custom field tự động phù hợp để serialize qua Java serialization. Nếu class exception có field trỏ đến object không serializable, việc serialize có thể thất bại. Trong Java hiện đại, không nên chọn Java native serialization làm giao thức public API chỉ vì `Exception` có sẵn `Serializable`.

Nếu dự án thực sự phải serialize exception qua một biên giới Java nội bộ:

- Các kiểu field cần tương thích với yêu cầu serialization, hoặc có chiến lược ánh xạ.
- Cân nhắc `serialVersionUID`, tương thích thay đổi class và rủi ro version skew.
- Không lưu object chứa credential/resource trong exception serialized.
- Không phụ thuộc vào khả năng sửa field ngữ cảnh không tương thích giữa các phiên bản.
- Nên cân nhắc chuyển lỗi thành **DTO có schema ổn định** cho HTTP, event, message queue thay vì serialize Throwable trực tiếp.

`record` được Java hỗ trợ serialization theo quy tắc riêng nếu components serializable; record **không tự biến mọi component thành serializable**. Nếu serialization là yêu cầu, cần đánh giá/test cấu trúc thực tế.

### 17.1. Dữ liệu có kiểu không nhất thiết “an toàn cho metric”

Một `ErrorCode` là nhãn metric tốt vì có số lượng giá trị giới hạn. Một `orderId`, `transactionId` hoặc email có thể tạo số lượng nhãn cực lớn (*high cardinality*). Dù các trường này có kiểu rõ, vẫn không nên dùng trực tiếp chúng làm nhãn metric. Đưa ID vào log/tracing theo chính sách phù hợp, còn metric thường nên dùng code/subsystem cố định.

## 18. Kiểm thử hợp đồng của custom exception

Một test tốt không chỉ hỏi “đã ném exception chưa?”. Với custom exception có context typed, nên kiểm tra:

1. **Đúng loại exception** ở đường lỗi.
2. **Đúng code** nếu code là một phần hợp đồng.
3. **Đúng context fields** với input.
4. **Invariants** của constructor/record.
5. **Cause** được giữ khi bọc ngoại lệ thấp hơn.
6. **Immutability** của context nếu input có collection mutable.
7. **Không chứa dữ liệu nhạy cảm** trong message/context được log hoặc response.
8. **Đường thành công** không ném ngoại lệ không cần thiết.

Với JUnit 5, ví dụ test ý tưởng:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class TypedOrderExceptionDemoTest {
    @Test
    void shortageProvidesTypedDetails() {
        var context = new TypedOrderExceptionDemo.OrderContext(
                "ORD-5", 9, 2);

        var error = assertThrows(
                TypedOrderExceptionDemo.InsufficientStockException.class,
                () -> TypedOrderExceptionDemo.reserve(context));

        assertEquals(
                TypedOrderExceptionDemo.ErrorCode.INSUFFICIENT_STOCK,
                error.code());
        assertEquals("ORD-5", error.context().orderId());
        assertEquals(9, error.context().requestedQuantity());
        assertEquals(2, error.context().availableQuantity());
    }
}
```

**Đây là file test minh họa, không phải một tệp `javac` độc lập:** cần JUnit Jupiter trên classpath và đặt file test cùng default package hoặc điều chỉnh visibility/package phù hợp. Mã tập trung kiểm tra **dữ liệu có cấu trúc**, không parse text của message.

### 18.1. Không test ngữ cảnh dựa trên `toString()` mặc định

`record.toString()` và `Throwable.toString()` dành cho hiển thị, không phải schema ổn định để phần mềm parse. Test getter/field type thay vì yêu cầu một cách định dạng string không liên quan đến hợp đồng API.

### 18.2. Test tránh dư thừa dữ liệu

Kiểm tra một context mutable bị thay đổi sau khi ném exception: các getter trong exception có giữ snapshot đúng không? Nếu code có hai field biểu diễn cùng một giá trị, có thể test tính nhất quán — nhưng tốt hơn là loại bỏ field dư ngay từ thiết kế, không phải thêm test để duy trì hai bản sao mãi mãi.

## 19. Chọn giữa custom exception và kết quả lỗi có cấu trúc

Không phải mọi validation failure đều nên ném exception. Nếu người dùng nhập form thường xuyên có nhiều field sai, một kiểu kết quả:

```java
record ValidationIssue(String field, String code) {}
record ValidationResult(
        boolean valid,
        java.util.List<ValidationIssue> issues) {}
```

có thể phù hợp hơn dùng `Throwable` cho từng lỗi dự kiến. Đây là **định nghĩa kiểu minh họa**, không có chương trình `main`. Khi có nhiều lỗi đồng thời, một tập `ValidationIssue` thường diễn đạt dữ liệu trực tiếp hơn danh sách suppressed exceptions (vốn phục vụ quan hệ lỗi phụ).

Quyết định theo semantics:

- **Exception:** không thể hoàn thành thao tác đúng hợp đồng, cần unwinding hoặc caller xử lý đường thất bại.
- **Result/validation errors:** thất bại dự kiến như một phần luồng giao tiếp bình thường, có thể tổng hợp nhiều vấn đề và trả về mà không ném.

Nếu dùng custom exception, giữ ngữ cảnh trong nó có ý nghĩa rõ ràng; không chuyển mọi kết quả nghiệp vụ thành exception chỉ vì có thể tạo typed fields.

## 20. Các lỗi phổ biến và cách sửa

| Lỗi thiết kế | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Parse `getMessage()` để lấy order ID/code | Text thay đổi không theo hợp đồng máy | Cung cấp getter typed |
| `Map<String,Object>` cho toàn bộ context | Key/kiểu sai chỉ lộ khi chạy | Dùng field/record/enum khi schema đã biết |
| Giữ đồng thời `quantity` và `quantityText` | Dễ lệch khi format hay update | Chỉ lưu quantity, format ở presentation |
| Giữ toàn bộ entity domain mutable | Log muộn thấy state khác, rò rỉ dữ liệu | Lưu snapshot tối thiểu |
| `private final List<T>` nhưng không copy | Caller vẫn có thể sửa list | `List.copyOf`; kiểm tra mutable elements |
| Dùng `record` và nghĩ tự deep immutable | Component có thể trỏ đến object mutable | Chọn component immutable/snapshot |
| Lưu thêm `originalException` cạnh `cause` | Trùng dữ liệu Throwable đã có | `super(message, cause)` + `getCause()` |
| Lưu `errorCode` tùy ý trong subtype có ý nghĩa cố định | Type và code có thể mâu thuẫn | Derive code, giới hạn constructor |
| Đưa password/token vào message | Có thể bị log tự động | Chỉ lưu field/code và ID an toàn |
| Dùng ID người dùng làm metric label | High cardinality và rủi ro riêng tư | Metric theo code hữu hạn, ID trong log được kiểm soát |
| Trả Throwable nguyên trạng qua HTTP | Rò rỉ stack, cause, field nội bộ | Map sang DTO đã lọc |
| Thêm hàng chục getter “phòng khi cần” | API phình to, versioning khó | Chỉ trường có use case thực tế |
| Dùng `Error` cho lỗi domain | Sai ngữ nghĩa và handler thường gặp | `Exception`/`RuntimeException` thích hợp |
| Bắt custom exception rồi trả “OK” | Che thất bại, làm sai trạng thái | Phục hồi thật hoặc báo failure |
| Tắt cause để giảm độ dài log | Mất đường truy nguyên | Giữ cause; chỉnh policy logger nếu cần |
| Dùng suppressed như danh sách tất cả validation issues | Sai ngữ nghĩa quan hệ Throwable | Dùng result có danh sách issue |
| Dùng native serialization làm public error protocol | Ràng buộc implementation và nguy cơ dữ liệu | Dùng DTO/versioned schema |
| Xem thuộc tính context là state live | Snapshot đã cũ sau khi ném | Tên field “atFailure” và đọc store khi cần giá trị mới |

## 21. Bài tập vận dụng

### Bài 1 — Tìm dữ liệu dư thừa

Một exception có `orderId`, `order`, `orderIdText` và `context.getOrderId()`. Hãy chọn một nơi làm nguồn sự thật. Giải thích vì sao giữ nguyên object `order` có thể làm state thay đổi và dữ liệu bí mật bị giữ lại.

### Bài 2 — Mã lỗi hay subtype?

Thiết kế `InsufficientStockException` với `ErrorCode.INSUFFICIENT_STOCK`. Nêu một trường hợp mà code thật sự hữu ích (mapping sang API/metric) và một trường hợp subtype Java đã đủ. Nếu giữ cả hai, constructor phải ngăn loại và code trái nhau ra sao?

### Bài 3 — Snapshot collection

Chạy `ImmutableContextDemo`, thử bỏ `List.copyOf` khỏi compact constructor. Sau khi `original.add("C")`, `context.itemIds().size()` sẽ thay đổi như thế nào? Tại sao `private final BatchContext context` không đủ bảo đảm snapshot nếu record giữ tham chiếu tới danh sách mutable?

### Bài 4 — Cause hay field riêng?

Trong `PaymentProcessingDemo`, thử thêm `private final IOException original;` cùng tham chiếu được đưa vào `super(message, e)`. Nó có tạo thêm khả năng xử lý nào không? **Không**, nếu caller đã có `getCause()` và không cần hợp đồng typed đặc biệt khác; nên loại bản sao.

### Bài 5 — Bảo mật

Thay ví dụ `SafeValidationContextDemo` để input là một token giả rất dài. Kiểm tra rằng stdout và các getter vẫn **không** xuất token. Nêu các nơi khác có thể vô tình log raw input và cách kiểm soát.

### Bài 6 — Enum và giao thức bên ngoài

Giả sử API trả JSON code `"STOCK_LOW"`, còn enum Java tên `INSUFFICIENT_STOCK`. Thiết kế mapper explicit thay vì phụ thuộc `ordinal()` hoặc ngầm coi `enum.name()` là hợp đồng bất biến. Test mapping theo từng mã công khai.

### Bài 7 — Nhiều lỗi validation

Một form có đồng thời 3 trường sai. Bạn sẽ tạo 3 suppressed exceptions hay một `ValidationResult` chứa 3 `ValidationIssue`? Giải thích tại sao kết quả cấu trúc thường diễn đạt validation dự kiến rõ hơn suppressed errors.

### Bài 8 — Dữ liệu có thể suy ra

Một context lưu `requested=7`, `availableAtFailure=3`, `shortage=4`. Nếu shortage luôn là `max(0, requested-available)`, hãy bỏ trường dư và tính khi cần. Nếu nghiệp vụ có quy tắc làm tròn hoặc tỷ giá theo thời điểm, lúc nào giá trị derived snapshot lại đáng giữ?

### Bài 9 — Kiểm thử hợp đồng

Viết JUnit test xác nhận `PaymentProcessingException` là checked, có code/context đúng và `getCause()` là `IOException` gốc. Không assert chuỗi `getMessage()` nếu message không phải hợp đồng máy ổn định.

### Bài 10 — Thiết kế giới hạn sử dụng

Một exception đang lưu danh sách 100.000 item IDs. Đây là thông tin có thật nhưng có nên đưa hết vào Throwable không? Hãy đề xuất một batch ID, số lượng, vài chỉ số lỗi hoặc một vị trí lưu báo cáo riêng, để exception không giữ dữ liệu quá lớn.

## 22. Checklist thiết kế exception có ngữ cảnh

- [ ] Custom exception có thật sự cần thiết ngoài các exception chuẩn hoặc kiểu result không?
- [ ] Chọn đúng checked/unchecked theo hợp đồng của caller chưa?
- [ ] Có xác định rõ ai sử dụng mỗi field context không?
- [ ] Field có kiểu phù hợp (`enum`, số, ID typed, `record`) thay vì parse message chưa?
- [ ] Các trường có trạng thái nhất quán và được validate trong constructor chưa?
- [ ] Những giá trị có thể tính lại đã được **derive thay vì lưu lặp** chưa?
- [ ] Có tránh lưu `cause`/stack/suppressed lần thứ hai khi `Throwable` đã cung cấp API chưa?
- [ ] Nếu subtype và code cùng biểu đạt một loại lỗi, chúng có được bảo đảm nhất quán không?
- [ ] Có tránh lưu object domain lớn, mutable, collection thừa hoặc resource đang mở chưa?
- [ ] Những collection context cần snapshot đã được defensive copy chưa?
- [ ] Đã biết `final` không khiến toàn bộ object graph bất biến chưa?
- [ ] Message có phục vụ con người và không bị code phân tích để ra quyết định chưa?
- [ ] Có loại trừ token, password, body/header nhạy cảm khỏi message/context chưa?
- [ ] Logger/API response có chính sách riêng và không serialize raw Throwable ra ngoài chưa?
- [ ] ID có được dùng đúng trong logging/tracing thay vì metric label high-cardinality chưa?
- [ ] Những field thêm vào exception có ý nghĩa về versioning/serialization nếu hệ thống dùng chúng chưa?
- [ ] Test có kiểm tra type/code/context/cause, snapshot và đường lỗi không?
- [ ] Khi error xảy ra, caller có cách xử lý hoặc báo thất bại đúng hợp đồng chưa?

**Kết luận:** Hãy thiết kế custom exception như một **báo cáo thất bại có cấu trúc nhỏ gọn**. Giữ những trường typed thật sự hữu ích cho caller, dùng `enum`/`record` khi tăng sự rõ ràng, kiểm soát snapshot và quyền riêng tư, **không nhân bản dữ liệu đã có** trong `Throwable` hoặc trường khác. `message` giúp con người hiểu; `code` và context giúp phần mềm xử lý; `cause` giữ đường nguyên nhân. Cân bằng ba nhóm thông tin này làm exception dễ đọc, dễ kiểm thử và ổn định hơn khi ứng dụng lớn lên.