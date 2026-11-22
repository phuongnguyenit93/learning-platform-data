# Tránh dùng `ordinal()` làm mã dữ liệu bền vững trong Java 17

## Mục tiêu học tập

Java `enum` giúp biểu diễn một tập hằng hữu hạn, có tên, an toàn kiểu. Mỗi hằng có một **vị trí khai báo** mà Java cung cấp qua `ordinal()`. Giá trị này rất tiện cho những cơ chế nội bộ dựa trên thứ tự, nhưng là **lựa chọn nguy hiểm để lưu cơ sở dữ liệu, gửi API, ghi log có hợp đồng dài hạn, mã hóa thông điệp hoặc trao đổi giữa nhiều phiên bản phần mềm**.

Sau bài này, bạn có thể:

- Giải thích chính xác `ordinal()` trả gì, vì sao giá trị có thể đổi dù tên hằng không đổi.
- Tái hiện lỗi dữ liệu: mã `1` hôm qua nghĩa là `PAID` nhưng phiên bản mới đọc thành `PENDING_REVIEW`.
- Phân biệt **danh tính enum constant**, **tên khai báo**, **thứ tự khai báo** và **mã nghiệp vụ bền vững**.
- Thiết kế mã `String`/`int` tường minh và bộ giải mã đáng tin: unique, null-aware, fail-fast, không phụ thuộc thứ tự.
- Hiểu trade-off giữa `name()`, `toString()`, `ordinal()` và explicit code.
- Đọc đúng rủi ro của `@Enumerated(EnumType.ORDINAL)` khi dùng JPA, cùng cách thay bằng converter/mapping được quản lý.
- Lập kế hoạch migration khi hệ thống **đã lỡ lưu ordinal**: cố định mapping phiên bản cũ, kiểm tra dữ liệu, chuyển đổi, triển khai an toàn, rollback và quan sát lỗi.
- Kiểm thử tính ổn định của mã qua reorder/add constants mà không vô tình viết một test phụ thuộc `ordinal()`.

Các chương trình minh họa sử dụng **Java 17**; mỗi tệp `.java` độc lập có `javac --release 17`, `java` và stdout xác định. Một số đoạn được ghi rõ là **snippet minh họa** hoặc **mã phiên bản trước/sau**: không ghép hai phiên bản có cùng tên class vào cùng một compilation unit.

## 1. `ordinal()` thực sự là gì?

Xét enum:

```java
enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
```

Mỗi enum constant có một vị trí **bắt đầu từ 0**, theo đúng thứ tự xuất hiện trong enum declaration:

| Hằng | `name()` | `ordinal()` |
| --- | --- | ---: |
| `NEW` | `"NEW"` | 0 |
| `PAID` | `"PAID"` | 1 |
| `SHIPPED` | `"SHIPPED"` | 2 |
| `CANCELLED` | `"CANCELLED"` | 3 |

`ordinal()` là final method do `java.lang.Enum` cung cấp. Ta **không tự đặt ordinal** trong constructor enum, cũng không override được nó.

Cú pháp:

```java
int position = OrderStatus.PAID.ordinal(); // 1
```

Đây là **vị trí khai báo**, không phải ID được domain xác nhận, không phải thứ tự thời gian, mức ưu tiên hay giá trị trong database. Hai enum constants khác nhau có ordinal khác nhau trong cùng enum class tại một phiên bản; điều đó **không bảo đảm** ordinal của một hằng giữ nguyên giữa các phiên bản source.

### Công dụng dự kiến của ordinal

Theo Java API, `ordinal()` được thiết kế chủ yếu cho những cấu trúc dữ liệu dựa trên enum như `EnumSet` và `EnumMap`. Các cấu trúc ấy hiểu thứ tự khai báo trong phạm vi enum hiện hành. Application code thường **không cần tự thao tác trực tiếp với ordinal** để lập trình nghiệp vụ.

**Quy tắc trọng tâm:** một thông tin được tính từ **thứ tự dòng source** không nên mặc nhiên trở thành **mã lưu trữ nhiều năm**.

## 2. Ví dụ runnable đầu tiên

Lưu **`OrdinalBasicsDemo.java`**:

```java
enum DeliveryStatus {
    CREATED, PAID, SENT
}

public class OrdinalBasicsDemo {
    public static void main(String[] args) {
        for (DeliveryStatus status : DeliveryStatus.values()) {
            System.out.println(status.name() + ":" + status.ordinal());
        }

        System.out.println(
                DeliveryStatus.PAID == DeliveryStatus.valueOf("PAID"));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 OrdinalBasicsDemo.java
java OrdinalBasicsDemo
```

**Stdout chính xác:**

```text
CREATED:0
PAID:1
SENT:2
true
```

Dòng cuối chỉ ra `valueOf("PAID")` trả lại chính **canonical enum constant**. Điều này liên quan đến danh tính hằng, **không** làm ordinal của hằng trở thành stable code.

## 3. Vì sao `ordinal()` không ổn định?

Hãy coi hai declaration sau là **hai phiên bản của cùng một enum**, không tồn tại cùng lúc:

**Phiên bản 1:**

```java
enum OrderStatus {
    NEW,
    PAID,
    SHIPPED
}
```

**Phiên bản 2:** thêm `PENDING_REVIEW` giữa NEW và PAID:

```java
enum OrderStatus {
    NEW,
    PENDING_REVIEW,
    PAID,
    SHIPPED
}
```

So sánh:

| Hằng | Ordinal v1 | Ordinal v2 |
| --- | ---: | ---: |
| `NEW` | 0 | 0 |
| `PENDING_REVIEW` | Không có | 1 |
| `PAID` | 1 | 2 |
| `SHIPPED` | 2 | 3 |

Nếu phiên bản 1 lưu `PAID` thành số `1` trong bảng `orders`, phiên bản 2 đọc `1` bằng cách tìm phần tử thứ 1 của `OrderStatus.values()` sẽ trả **PENDING_REVIEW**.

Không có exception nào bắt buộc xảy ra. Điều đáng sợ nhất là **dữ liệu có thể bị đọc sai một cách âm thầm**.

### Các thay đổi gây rủi ro

- Chèn hằng ở đầu/giữa enum.
- Sắp xếp lại constants theo alphabet để “đẹp source”.
- Gom nhóm constants theo quy tắc nghiệp vụ mới.
- Xóa hằng không dùng, làm dịch vị trí phía sau.
- Chuyển một enum thành một declaration khác với thứ tự thay đổi.
- Một service chạy version mới trong khi service khác vẫn dùng version cũ.

**Thêm hằng cuối** không làm dịch ordinal hiện tại trong bản source đó, nhưng vẫn không biến ordinal thành stable code: những thay đổi về thứ tự sau này vẫn có thể xảy ra và giao thức thường không bảo đảm mọi consumer nâng cấp đồng thời.

## 4. Thử nghiệm hai phiên bản với stdout

Lưu **`OrdinalVersion1Demo.java`**:

```java
enum OldStatus {
    NEW,
    PAID,
    SHIPPED
}

public class OrdinalVersion1Demo {
    public static void main(String[] args) {
        System.out.println(OldStatus.PAID.ordinal());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OrdinalVersion1Demo.java
java OrdinalVersion1Demo
```

Stdout:

```text
1
```

Lưu **`OrdinalVersion2Demo.java`** dưới một tên type riêng để hai ví dụ có thể tồn tại độc lập:

```java
enum NewStatus {
    NEW,
    PENDING_REVIEW,
    PAID,
    SHIPPED
}

public class OrdinalVersion2Demo {
    public static void main(String[] args) {
        System.out.println(NewStatus.PAID.ordinal());
        System.out.println(NewStatus.values()[1]);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OrdinalVersion2Demo.java
java OrdinalVersion2Demo
```

Stdout:

```text
2
PENDING_REVIEW
```

Trong production, type tên `OrderStatus` thường **không đổi**, nhưng version mã nguồn đổi. Việc dùng `OldStatus`/`NewStatus` ở hai file chỉ để minh họa kết quả cùng lúc mà không trùng tên.

## 5. “Dữ liệu bền vững” là những gì?

Một mã được xem là **persisted/external contract** nếu nó phải giữ ý nghĩa sau khi process hiện tại kết thúc hoặc qua nhiều bản triển khai.

Ví dụ:
- Column `status` trong MySQL/PostgreSQL hoặc file dữ liệu.
- Key/value trong Redis nếu dữ liệu sống qua deploy.
- Event payload Kafka/Pulsar đã gửi và có thể replay.
- JSON response/request của public API.
- Message gửi giữa các microservices khác version.
- Record trong audit log dùng để điều tra sau này.
- CSV export/import cho đối tác.
- Mã cấu hình tồn tại giữa các lần restart.
- Dữ liệu cache dài hạn cần đọc bằng phiên bản mới.

Trong những môi trường đó, dữ liệu cần có **ý nghĩa ổn định theo hợp đồng**, không theo vị trí ngẫu nhiên của một hằng trong source file.

Ngược lại, indexing ngắn hạn trong một thuật toán nội bộ có thể phụ thuộc declaration order nếu bạn kiểm soát đầy đủ lifecycle và **không xuất ordinal ra ranh giới persistence/protocol**.

## 6. Failure mode khi lưu ordinal vào database

Hình dung bảng:

```text
orders
+----+--------+
| id | status |
+----+--------+
| 10 |   1    |
| 11 |   2    |
+----+--------+
```

Với enum v1 `NEW, PAID, SHIPPED`, ứng dụng hiểu:

```text
id=10 → PAID
id=11 → SHIPPED
```

Sau khi một developer chèn `PENDING_REVIEW` vào giữa, cùng hai số ấy được đọc là:

```text
id=10 → PENDING_REVIEW   (sai ý nghĩa)
id=11 → PAID             (sai ý nghĩa)
```

Lỗi có thể tiếp tục lan:
1. UI hiển thị trạng thái sai.
2. Authorization/transition logic đi sai nhánh.
3. Batch job xử lý lại dữ liệu theo nhãn mới.
4. Hệ thống ghi đè kết quả sai trở lại database.
5. Audit logs ghi những sự kiện khó phục hồi.

**Điểm nguy hiểm:** nếu mọi ordinal vẫn nằm trong phạm vi 0..N-1 của enum mới, code lookup có thể không ném exception nào.

### Không phải chỉ là lỗi trình bày

Với trạng thái `PAID` bị đọc thành `PENDING_REVIEW`, hệ thống thanh toán có thể từ chối giao hàng, tính phí lại hoặc kích hoạt workflow không đúng. Đây là lỗi **toàn vẹn dữ liệu (data integrity)**.

## 7. Anti-pattern thường thấy

```java
// Sai khi persisted status là business ID ổn định:
int valueForDatabase = status.ordinal();
```

Và lúc đọc:

```java
// Nguy hiểm: chỉ hợp nghĩa nếu schema dữ liệu và thứ tự enum
// thực sự thuộc cùng một phiên bản, và vẫn không nên dùng lâu dài.
OrderStatus loaded = OrderStatus.values()[savedNumber];
```

Nhược điểm của `values()[savedNumber]`:
- Nếu số âm hoặc quá phạm vi: `ArrayIndexOutOfBoundsException`.
- Nếu số hợp lệ nhưng bản enum reorder: **giải mã thành hằng sai**.
- Không có thông tin version của schema.
- Không có khả năng phát hiện rằng `1` vốn từng biểu diễn hằng cũ khác.
- Tên hằng, nội dung field hoặc contract mới không giúp khôi phục đúng ý nghĩa.

**Đừng “khắc phục” bằng cách catch exception rồi chọn hằng mặc định**. Trường hợp sai âm thầm vẫn không exception, và defaulting có thể xóa dấu vết lỗi dữ liệu.

## 8. Runnable: tái hiện silent misinterpretation

Lưu **`OrdinalDataCorruptionDemo.java`**:

```java
enum OriginalStatus {
    NEW, PAID, SHIPPED
}

enum ModifiedStatus {
    NEW, PENDING_REVIEW, PAID, SHIPPED
}

public class OrdinalDataCorruptionDemo {
    public static void main(String[] args) {
        int stored = OriginalStatus.PAID.ordinal();

        OriginalStatus original = OriginalStatus.values()[stored];
        ModifiedStatus modified = ModifiedStatus.values()[stored];

        System.out.println("stored=" + stored);
        System.out.println("original=" + original);
        System.out.println("modified=" + modified);
        System.out.println(original.name().equals(modified.name()));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OrdinalDataCorruptionDemo.java
java OrdinalDataCorruptionDemo
```

Stdout:

```text
stored=1
original=PAID
modified=PENDING_REVIEW
false
```

Mã số nguyên `1` không mang đủ thông tin để nói “đây là PAID”. **Nó chỉ có ý nghĩa khi ghép với một version declaration cụ thể**.

## 9. Lỗi tương tự trong API và sự kiện

Ví dụ một event:

```text
{ "orderId": 10, "status": 1 }
```

Producer cũ dùng `OrderStatus.PAID.ordinal()==1`. Consumer mới hiểu `1` là PENDING_REVIEW. Dù producer và consumer cùng dùng Java, không có guarantee tự đồng bộ thứ tự enum giữa hai binary versions.

Nếu consumer là Python, Go, JavaScript hoặc một đối tác ngoài công ty, họ thậm chí không nhìn thấy Java source declaration. Numeric code `1` cần được định nghĩa **trong protocol specification**, không ngầm phụ thuộc `ordinal()`.

### Rolling deployment làm vấn đề phức tạp hơn

Trong blue/green hoặc rolling update, các phiên bản có thể cùng hoạt động:
- Service A v1 ghi số 1 với nghĩa PAID.
- Service B v2 đọc số 1 với nghĩa PENDING_REVIEW.
- Service B v2 ghi số 2 với nghĩa PAID.
- Service A v1 đọc số 2 với nghĩa SHIPPED.

Chỉ một lần reorder có thể tạo **incompatibility hai chiều**. Vì thế migration phải xét cả khả năng tồn tại nhiều version đồng thời, không chỉ một lần restart.

## 10. Bốn khái niệm dễ lẫn

| Khái niệm | Ví dụ | Có bền vững khi reorder hằng? |
| --- | --- | --- |
| Identity object của hằng | `OrderStatus.PAID` | Cùng hằng được tham chiếu trong runtime tương ứng |
| `name()` | `"PAID"` | **Có** nếu giữ nguyên tên; rename làm đổi |
| `ordinal()` | `1` | **Không** nếu thêm/reorder hằng trước PAID |
| Mã explicit | `"P"` hoặc `200` | **Có thể có**, khi được quản lý ổn định như hợp đồng |

**Explicit code không tự động bất biến.** Nó chỉ bền vững nếu team đưa vào quy tắc: không tái sử dụng mã, không sửa ngầm, migration có chủ đích và kiểm thử contract.

### `toString()` không phải chìa khóa mặc định

`toString()` của enum có thể override cho UI hoặc logging. Nếu dùng làm persisted key, sau này thay câu chữ/locale có thể phá dữ liệu.

Sử dụng rõ:
- `name()` khi contract cam kết theo tên constant source.
- `code()` khi contract có mã riêng.
- `label(locale)` cho hiển thị đa ngôn ngữ.
- `ordinal()` chỉ cho thứ tự nội bộ hợp lý.

## 11. Giải pháp ưu tiên: mã `String` tường minh

```java
enum OrderStatus {
    NEW("N"),
    PENDING_REVIEW("R"),
    PAID("P"),
    SHIPPED("S");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Mỗi hằng có một mã cố định:
- NEW → N.
- PENDING_REVIEW → R.
- PAID → P.
- SHIPPED → S.

Bây giờ đổi thứ tự các hằng **không làm đổi field `code`**, nếu bạn giữ nguyên argument đi cùng từng hằng.

Đây là tách biệt quan trọng giữa **declaration order** và **external representation**.

### Vì sao String thường tiện?

- Dễ đọc bằng mắt trong database, logs, JSON.
- Có thể ngắn và ổn định, ví dụ `"P"`.
- Không bị hiểu nhầm là offset/mảng.
- Có thể mở rộng namespace với prefixes khi cần.

Nhưng String không bắt buộc. `int` explicit cũng ổn nếu protocol có numeric codes có ý nghĩa, không phải ordinal.

## 12. Runnable: stable String code

Lưu **`ExplicitStringCodeDemo.java`**:

```java
enum OrderStatus {
    NEW("N"),
    PENDING_REVIEW("R"),
    PAID("P"),
    SHIPPED("S");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}

public class ExplicitStringCodeDemo {
    public static void main(String[] args) {
        OrderStatus status = OrderStatus.PAID;

        System.out.println(status.code());
        System.out.println(status.ordinal());
        System.out.println(status.name());
        System.out.println(status == OrderStatus.PAID);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ExplicitStringCodeDemo.java
java ExplicitStringCodeDemo
```

Stdout:

```text
P
2
PAID
true
```

`P` là mã external contract do ta tự thiết kế. `2` chỉ là ordinal trong version source hiện tại. Nếu reorder `PAID` lên đầu, `ordinal()` đổi thành 0, còn `code()` vẫn P.

## 13. Mã `int` tường minh cũng là giải pháp

Không phải dùng số nguyên là sai. Sai là **dùng số nguyên lấy từ `ordinal()` mà không có contract ổn định**.

Ví dụ:

```java
enum PaymentStatus {
    PENDING(100),
    PAID(200),
    FAILED(900);

    private final int code;

    PaymentStatus(int code) {
        this.code = code;
    }

    public int code() {
        return code;
    }
}
```

Đây là các mã **100/200/900** được chọn rõ và document. Ta có thể thêm trạng thái `REFUNDED(300)` vào bất kỳ vị trí nào mà không làm đổi các mã cũ.

### Quy tắc dành cho mã số

- Có namespace và định nghĩa rõ.
- Unique trong tập hằng.
- Không dùng lại mã cũ cho nghĩa mới sau khi ngừng sử dụng.
- Không suy mã bằng `ordinal()+1`.
- Có strategy cho unknown code.
- Không phụ thuộc sorting/reordering enum.
- Có test đảm bảo backward compatibility.

## 14. Runnable: stable numeric codes

Lưu **`ExplicitNumericCodeDemo.java`**:

```java
enum PaymentStatus {
    PENDING(100),
    PAID(200),
    FAILED(900);

    private final int code;

    PaymentStatus(int code) {
        this.code = code;
    }

    int code() {
        return code;
    }
}

public class ExplicitNumericCodeDemo {
    public static void main(String[] args) {
        for (PaymentStatus status : PaymentStatus.values()) {
            System.out.println(status.name()
                    + ":code=" + status.code()
                    + ",ordinal=" + status.ordinal());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ExplicitNumericCodeDemo.java
java ExplicitNumericCodeDemo
```

Stdout:

```text
PENDING:code=100,ordinal=0
PAID:code=200,ordinal=1
FAILED:code=900,ordinal=2
```

Điểm mấu chốt là **`code` không được tạo từ `ordinal`**. Dù hiện tại số thứ tự ngẫu nhiên liên quan tới thứ tự khai báo, contract chỉ nằm trong các mã explicit.

## 15. Thiết kế decoder: không đọc `values()[number]`

Khi database/API trả `"P"`, cần ánh xạ về `OrderStatus.PAID`.

Một cách đơn giản cho enum nhỏ:

```java
static OrderStatus fromCode(String code) {
    for (OrderStatus status : values()) {
        if (status.code.equals(code)) {
            return status;
        }
    }
    throw new IllegalArgumentException("Unknown code: " + code);
}
```

Lợi ích:
- Tìm theo mã explicit, không phải ordinal.
- Đổi thứ tự enum không ảnh hưởng.
- Unknown code được phát hiện thay vì sai âm thầm.
- Chi phí O(n), thường đủ cho enum nhỏ và tần suất thấp.

### Đừng dùng `toString()` hoặc `name()` như decoder ngầm

`Enum.valueOf(Type.class, input)` tìm theo **constant name**, không theo `code`. Nếu `PAID` có mã `"P"` thì `valueOf("P")` **không** chọn PAID.

Hãy đặt tên method `fromCode` rõ, không giả định Java tự hiểu custom fields.

## 16. Runnable: decoder tuyến tính và unknown code

Lưu **`EnumDecoderDemo.java`**:

```java
enum OrderState {
    NEW("N"),
    PAID("P"),
    SHIPPED("S");

    private final String code;

    OrderState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static OrderState fromCode(String code) {
        for (OrderState candidate : values()) {
            if (candidate.code.equals(code)) {
                return candidate;
            }
        }
        throw new IllegalArgumentException("unknown code");
    }
}

public class EnumDecoderDemo {
    public static void main(String[] args) {
        OrderState state = OrderState.fromCode("P");

        System.out.println(state);
        System.out.println(state == OrderState.PAID);
        System.out.println(state.code());

        try {
            OrderState.fromCode("X");
        } catch (IllegalArgumentException error) {
            System.out.println("UNKNOWN");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumDecoderDemo.java
java EnumDecoderDemo
```

Stdout:

```text
PAID
true
P
UNKNOWN
```

`fromCode` trả **canonical enum object**, không một bản sao. Việc ánh xạ từ `"P"` sang PAID vẫn đúng nếu developer đổi thứ tự khai báo.

## 17. Khi nào dùng lookup map?

Với enum lớn hoặc decoding rất thường xuyên, có thể tạo `Map<String,EnumType>` một lần:

```java
private static final Map<String, OrderStatus> BY_CODE = ...;
```

Map lookup thường O(1) trung bình, nhưng lợi ích chính ở đây không chỉ hiệu năng:
- Kiểm tra duplicate mã ngay khi initialize class.
- Tập trung mapping logic.
- Dễ định nghĩa unknown-code policy.
- Có thể expose method `fromCode` mà không expose map mutable.

**Không xây map trong enum constructor bằng cách chạm tới một static map của chính enum vừa được khởi tạo.** Các enum constants được xây trước static fields thông thường, và có các hạn chế Java với tham chiếu tới static fields chưa được khởi tạo trong enum constructor. Đặt logic dựng map sau khi mọi constants đã sẵn sàng, ví dụ trong static initializer hoặc static field initialization phù hợp.

### Map nên immutable sau khi tạo

Nếu mapping là contract của enum:
- Xây local mutable map để kiểm tra uniqueness.
- Publish immutable `Map.copyOf` hoặc `Collections.unmodifiableMap`.
- Không expose map cho caller có thể `put` phá invariant.
- Tránh null trong mã và trùng mã.

## 18. Runnable: decoder bằng immutable map, phát hiện mã trùng

Lưu **`EnumCodeMapDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

enum ReviewStatus {
    NEW("N"),
    APPROVED("A"),
    REJECTED("R");

    private final String code;

    ReviewStatus(String code) {
        this.code = Objects.requireNonNull(code);
    }

    String code() {
        return code;
    }

    private static final Map<String, ReviewStatus> BY_CODE;

    static {
        Map<String, ReviewStatus> map = new HashMap<>();

        for (ReviewStatus status : values()) {
            ReviewStatus previous = map.putIfAbsent(
                    status.code, status);
            if (previous != null) {
                throw new IllegalStateException(
                        "duplicate enum code");
            }
        }

        BY_CODE = Map.copyOf(map);
    }

    static ReviewStatus fromCode(String code) {
        ReviewStatus result = BY_CODE.get(code);
        if (result == null) {
            throw new IllegalArgumentException(
                    "unknown enum code");
        }
        return result;
    }
}

public class EnumCodeMapDemo {
    public static void main(String[] args) {
        ReviewStatus status = ReviewStatus.fromCode("A");

        System.out.println(status);
        System.out.println(status.code());
        System.out.println(status == ReviewStatus.APPROVED);

        try {
            ReviewStatus.fromCode("Z");
        } catch (IllegalArgumentException error) {
            System.out.println("unknown");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumCodeMapDemo.java
java EnumCodeMapDemo
```

Stdout:

```text
APPROVED
A
true
unknown
```

**Quan trọng:** `BY_CODE` được dựng trong `static` block **sau danh sách hằng**. Nó dùng `values()` khi constants đã được khởi tạo. `putIfAbsent` bắt lỗi duplicate ngay lúc khởi tạo enum type, tránh việc “giá trị cuối ghi đè giá trị trước” âm thầm.

**Policy cho null:** `Map.copyOf` không cho key/value null; constructor ngăn null code. `BY_CODE.get(null)` đối với immutable map này có thể ném `NullPointerException`, nên decoder production cần kiểm tra null tường minh trước lookup nếu muốn một loại lỗi thống nhất.

## 19. Decoder rõ ràng với null và input không hợp lệ

Đầu vào ngoài hệ thống có thể chứa:
- `null`;
- Chuỗi rỗng;
- Chuỗi có space thừa;
- Khác hoa/thường;
- Code không còn được hỗ trợ;
- Code của tương lai mà phiên bản hiện tại chưa biết.

Không có một chính sách duy nhất cho mọi domain:
- **Fail fast** với `IllegalArgumentException` khi trạng thái tác động tiền hoặc authorization.
- Trả `Optional<Status>` nếu unknown là tình huống được mong đợi.
- Trả một object kết quả biểu diễn `Unknown(rawCode)` nếu cần bảo toàn dữ liệu chưa biết để chuyển tiếp.
- Normalize input chỉ khi protocol định nghĩa normalization (đừng tự `trim()`/uppercase khiến các codes khác nhau bị đánh đồng).

### Bẫy default về NEW

`return Status.NEW;` cho mọi unknown code có thể là lỗi nghiêm trọng: một trạng thái PAID từ tương lai bị đọc thành NEW, dẫn tới xử lý lại hoặc hủy luồng. Default chỉ hợp lệ khi semantics của hệ thống thật sự định nghĩa điều đó và được kiểm thử.

## 20. Runnable: parse an toàn với Optional

Lưu **`EnumOptionalDecoderDemo.java`**:

```java
import java.util.Optional;

enum Channel {
    EMAIL("e"),
    SMS("s");

    private final String code;

    Channel(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static Optional<Channel> tryFromCode(String input) {
        if (input == null) {
            return Optional.empty();
        }

        for (Channel channel : values()) {
            if (channel.code.equals(input)) {
                return Optional.of(channel);
            }
        }
        return Optional.empty();
    }
}

public class EnumOptionalDecoderDemo {
    public static void main(String[] args) {
        System.out.println(Channel.tryFromCode("e").orElseThrow());
        System.out.println(Channel.tryFromCode("S").isPresent());
        System.out.println(Channel.tryFromCode(null).isEmpty());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumOptionalDecoderDemo.java
java EnumOptionalDecoderDemo
```

Stdout:

```text
EMAIL
false
true
```

Ở đây mã phân biệt hoa/thường: `"s"` hợp lệ, `"S"` unknown. Đó là lựa chọn protocol chủ ý.

## 21. `name()` tốt hơn `ordinal()` trong trường hợp nào?

Ví dụ:

```java
enum OrderStatus {
    NEW, PAID, SHIPPED
}
```

Lưu `OrderStatus.PAID.name()` sẽ ghi `"PAID"`. Khi thêm `PENDING_REVIEW` trước PAID:
- `name()` vẫn là `"PAID"` nếu không rename hằng.
- `OrderStatus.valueOf("PAID")` vẫn trả đúng PAID.
- Ordinal của PAID thay đổi.

Như vậy **lưu tên hằng thường an toàn hơn lưu ordinal** trước các thay đổi thứ tự.

Nhưng có caveat:
- Rename PAID → SETTLED làm dữ liệu `"PAID"` cũ không còn được `valueOf` nhận.
- Xóa hằng làm historical rows cần migration.
- Tên source trở thành public data contract, hạn chế quyền refactor tên.

Nếu code là internal và rename hiếm, name-based mapping có thể đủ. Nếu API/database có vòng đời độc lập, explicit stable code cho bạn một tầng abstraction chắc hơn.

## 22. `name()` và `toString()` khác nhau

`Enum.name()` là final, trả tên declaration chính xác. `toString()` mặc định cũng trả tên, nhưng có thể override:

```java
enum Status {
    PAID;

    @Override
    public String toString() {
        return "Đã thanh toán";
    }
}
```

`Status.PAID.name()` là `"PAID"`; `Status.PAID.toString()` là `"Đã thanh toán"`.

**Không sử dụng text giao diện làm ID bền vững**. Locale, wording, A/B experiments và thay đổi dịch thuật có thể khiến text khác trong khi ý nghĩa domain không đổi.

Nên tách:
- `code`: stable persistence/wire code.
- `name`: Java declaration identifier.
- `label`: UI translation.

## 23. Runnable: label thay đổi không ảnh hưởng code

Lưu **`EnumLabelVsCodeDemo.java`**:

```java
enum TicketStatus {
    OPEN("O", "Đang mở"),
    CLOSED("C", "Đã đóng");

    private final String code;
    private final String label;

    TicketStatus(String code, String label) {
        this.code = code;
        this.label = label;
    }

    String code() {
        return code;
    }

    String label() {
        return label;
    }
}

public class EnumLabelVsCodeDemo {
    public static void main(String[] args) {
        TicketStatus status = TicketStatus.CLOSED;

        System.out.println(status.name());
        System.out.println(status.code());
        System.out.println(status.label());
        System.out.println(status.ordinal());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumLabelVsCodeDemo.java
java EnumLabelVsCodeDemo
```

Stdout:

```text
CLOSED
C
Đã đóng
1
```

Bạn có thể sửa label thành một bản dịch khác mà không cần sửa `"C"`, miễn code mapping được cam kết ổn định.

## 24. JPA `EnumType.ORDINAL`: hiểu đúng rủi ro

Nếu dự án dùng Jakarta Persistence/JPA, một entity field enum có thể được ánh xạ kiểu ordinal hoặc string tùy annotation/provider/version.

Ví dụ **snippet phụ thuộc JPA library**, không phải Java SE 17 thuần:

```java
@Enumerated(EnumType.ORDINAL)
private OrderStatus status;
```

Ý nghĩa thường thấy của `EnumType.ORDINAL` là ánh xạ enum theo số thứ tự. Nếu source enum reorder, dữ liệu trong cột có thể được giải mã sai.

**Cảnh báo:** tùy JPA namespace/version, có thể là `javax.persistence` hoặc `jakarta.persistence`; đoạn trên không tự biên dịch chỉ với JDK nếu chưa có JPA dependency và entity context.

### `EnumType.STRING` có an toàn tuyệt đối?

Snippet:

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;
```

Nó thường ánh xạ theo enum name, tránh vấn đề reorder nhưng vẫn phụ thuộc **tên constant**. Rename/delete constant cần migration.

Các thiết lập mặc định và chi tiết schema/provider có thể khác theo JPA specification và phiên bản; đừng dựa vào default không kiểm soát. Hãy xác minh mapping được sử dụng trong dự án thật.

### Khi cần stable business code

Dùng một converter/mapper do ứng dụng kiểm soát: `OrderStatus.code()` khi ghi và `OrderStatus.fromCode(...)` khi đọc. Cơ chế thực hiện có thể là JPA `AttributeConverter` hoặc mapper ở persistence layer, tùy thiết kế/provider.

**Không nên đồng thời dùng `@Enumerated` và custom converter cho cùng field** mà không hiểu quy tắc precedence/hạn chế của provider và specification. Chọn một mapping strategy rõ và test integration.

## 25. Database schema nên lưu mã nào?

Có hai lựa chọn phổ biến:

**String code:**

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status_code VARCHAR(16) NOT NULL
);
```

**Numeric explicit code:**

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status_code INTEGER NOT NULL
);
```

Hai đoạn là **DDL minh họa**, không chứa vendor-specific constraints/migration. Ứng dụng ghi `"P"` hoặc `200` theo explicit enum code, không ghi `ordinal()`.

Các câu hỏi schema:
- Nullable hay not null?
- Có CHECK/foreign key/reference table constraint không?
- Mã cũ có cần vẫn được nhận trong historical data không?
- Độ dài cột có đủ cho mã tương lai?
- Có index/unique constraints cần điều chỉnh?
- Có application versions cũ cùng đọc cột không?
- Có cần lưu schema version để replay dữ liệu nhiều năm?

Đừng coi việc đổi kiểu từ SMALLINT sang VARCHAR như một thay đổi chỉ về Java source. Nó là **data migration** và cần lập kế hoạch.

## 26. Migration: hệ thống đã lưu ordinal thì làm gì?

Nếu `orders.status` hiện chứa `0,1,2`, việc thay ngay code thành explicit `fromCode` mà không chuyển dữ liệu sẽ gây lỗi hoặc đọc sai.

Quy trình có chủ đích:

1. **Đóng băng bản mapping đã dùng để ghi dữ liệu**: tìm đúng source/binary version của enum khi dữ liệu được tạo.
2. **Liệt kê các versions lịch sử**, thời gian deploy và khả năng có nhiều mappings khác nhau.
3. **Đo phân bố giá trị**: những ordinals nào có trong database, tỷ lệ null, số ngoài phạm vi.
4. **Xác định tính đơn nghĩa** của mỗi giá trị trong từng giai đoạn; nếu một số từng có hai ý nghĩa và không có version/timestamp, việc khôi phục có thể không chắc chắn.
5. **Chọn stable code** và document mapping chính thức.
6. **Tạo cột mới hoặc giai đoạn chuyển đổi có kiểm soát** để tránh nhầm cũ/mới.
7. **Backfill bằng mapping cố định của phiên bản cũ**, không bằng enum current `values()[n]`.
8. **Đối chiếu số lượng, checksums và mẫu nghiệp vụ** trước khi chuyển reader.
9. **Đảm bảo compatibility trong rolling deploy**: dual-read/dual-write nếu cần và có thiết kế chặt.
10. **Chuyển reader/writer sang stable code**, sau đó gỡ ordinal theo kế hoạch.
11. **Quan sát unknown/missing code**, rollback, audit trails, dữ liệu mới phát sinh.
12. **Xóa đường ghi ordinal và đặt guard/test** để lỗi không quay lại.

Quan trọng nhất là **bước 1**. Nếu bạn lấy enum source mới để giải mã số cũ thì migration có thể tự tạo ra dữ liệu sai vĩnh viễn.

## 27. Lập mapping legacy theo declaration lịch sử, không theo current enum

Giả sử lịch sử có:

```text
V1 historical ordinal:
0 = NEW
1 = PAID
2 = SHIPPED
```

Phiên bản mới có thêm PENDING_REVIEW. Khi migration, định nghĩa rõ bản mapping cũ:

```java
static OrderStatus fromLegacyV1Ordinal(int saved) {
    return switch (saved) {
        case 0 -> OrderStatus.NEW;
        case 1 -> OrderStatus.PAID;
        case 2 -> OrderStatus.SHIPPED;
        default -> throw new IllegalArgumentException(
                "Unknown legacy ordinal: " + saved);
    };
}
```

**Không** viết `OrderStatus.values()[saved]` ở đây, vì current enum declaration đã thay đổi.

### Nếu nhiều lịch sử source version?

Định nghĩa migration logic theo dữ liệu version/source-era tương ứng:

```java
switch (record.schemaVersion()) {
    case 1 -> decodeV1(record.ordinal());
    case 2 -> decodeV2(record.ordinal());
    default -> throw new IllegalArgumentException();
}
```

Đây là snippet thiết kế: `record` cần một model có schemaVersion/ordinal. Không tự bịa version nếu database hiện không có trường tương ứng. Nếu dữ liệu đã trộn và không thể biết record được ghi bởi version nào, có thể cần forensic evidence, manual reconciliation và xử lý không chắc chắn, không được tuyên bố mapping hoàn hảo.

## 28. Runnable: migration từ ordinal cũ sang code mới

Lưu **`LegacyOrdinalMigrationDemo.java`**:

```java
enum CurrentState {
    NEW("N"),
    PENDING_REVIEW("R"),
    PAID("P"),
    SHIPPED("S");

    private final String code;

    CurrentState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static CurrentState fromLegacyV1(int oldOrdinal) {
        return switch (oldOrdinal) {
            case 0 -> NEW;
            case 1 -> PAID;
            case 2 -> SHIPPED;
            default -> throw new IllegalArgumentException(
                    "unknown old ordinal");
        };
    }
}

public class LegacyOrdinalMigrationDemo {
    public static void main(String[] args) {
        int[] oldDatabaseValues = {0, 1, 2};

        for (int old : oldDatabaseValues) {
            CurrentState state = CurrentState.fromLegacyV1(old);
            System.out.println(old + " -> " + state.code());
        }

        System.out.println(CurrentState.PAID.ordinal());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LegacyOrdinalMigrationDemo.java
java LegacyOrdinalMigrationDemo
```

Stdout:

```text
0 -> N
1 -> P
2 -> S
2
```

Dòng cuối chứng minh PAID hiện có ordinal **2**, nhưng legacy ordinal **1** vẫn được migration thành PAID theo **historical mapping** chứ không phải current position.

## 29. SQL migration phải dựa vào tài liệu schema cũ

Ví dụ **ý tưởng backfill có điều kiện**:

```sql
UPDATE orders
SET status_code = CASE legacy_status
    WHEN 0 THEN 'N'
    WHEN 1 THEN 'P'
    WHEN 2 THEN 'S'
    ELSE NULL
END;
```

Đây chỉ là **SQL minh họa**, không phải script production chạy nguyên xi:
- Column names thực tế có thể khác.
- Việc `ELSE NULL` chỉ giúp minh họa unknown value; trong migration thật cần báo lỗi/kiểm toán chứ không biến unknown thành null im lặng.
- Có thể cần transaction batching, locks, online schema changes và replication planning.
- Với versions hỗn hợp, một mapping cho mọi rows có thể sai.
- Sau backfill phải đối chiếu counts và samples theo business rules.

### Trước khi chạy migration

Nên có:
- Backup/snapshot khôi phục được.
- Dry run trên dữ liệu đại diện.
- Report số rows theo từng legacy ordinal.
- Query phát hiện invalid/unknown ordinals.
- Kế hoạch rollback và write compatibility.
- Cửa sổ bảo trì hoặc phased rollout được kiểm chứng.
- Owners chịu trách nhiệm sign-off integrity checks.

“Đổi annotation từ ORDINAL sang STRING” **không** tự chuyển những con số tồn tại sang đúng enum names.

## 30. Dữ liệu lịch sử có thể không cứu hoàn toàn

Giả sử:
- v1: `0 NEW, 1 PAID, 2 SHIPPED`;
- v2: `0 NEW, 1 PENDING_REVIEW, 2 PAID, 3 SHIPPED`;
- database đã chứa nhiều records được ghi bởi cả hai;
- record không có schema version, deployment timestamp đáng tin hay audit state.

Giá trị `1` có thể nghĩa là:
- PAID nếu ghi từ v1;
- PENDING_REVIEW nếu ghi từ v2.

Không có phép toán Java nào khôi phục chắc chắn ý nghĩa từ **một số 1 đơn lẻ**. Bài toán đã mất thông tin tại thời điểm ghi dữ liệu.

Phải:
- Thu thập logs, events, timestamps, version metadata nếu có.
- Kiểm tra quy tắc nghiệp vụ ràng buộc mỗi record.
- Xác định nhóm không thể suy ra và xử lý riêng.
- Báo cáo rõ sự không chắc chắn, không giả vờ tất cả rows đã được sửa chính xác.

Đây là lý do phòng tránh ordinal persistence **rẻ hơn rất nhiều** so với sửa sai hậu quả.

## 31. Migration trong rolling deployment

Nếu không thể dừng toàn bộ hệ thống cùng lúc:

**Giai đoạn mở rộng schema:** thêm `status_code` nhưng vẫn giữ cột legacy ordinal. Deploy readers mới có thể đọc stable code khi có, fallback historical mapping khi không có.

**Giai đoạn dual-write:** writer mới ghi cả hai cột **chỉ khi dual-write được thiết kế an toàn**, legacy code không thể biểu diễn mọi trạng thái mới; tránh ghi ordinal cho constant mới mà consumer cũ hiểu sai.

**Backfill và xác minh:** chuyển những rows cũ theo mapping version đúng; phát hiện rows unsupported/ambiguous.

**Giai đoạn chuyển đổi:** chuyển mọi readers và writers sang code mới. Theo dõi tỉ lệ fallback, unknown code và consistency.

**Giai đoạn thu gọn:** ngừng legacy writes, bỏ fallback khi dữ liệu đã được xác minh, sau đó xóa cột ordinal theo release phù hợp.

### Điểm kiểm soát quan trọng

Nếu code v2 có hằng mới không tồn tại trong v1, legacy consumers có thể không hiểu trạng thái đó dù dual-write. Bạn có thể cần version gating, feature flag hoặc trì hoãn phát hành giá trị mới cho tới khi mọi consumers đã nâng cấp.

Dual-write không phải magic solution cho incompatibility.

## 32. Bộ quy tắc quản lý mã explicit

Để mã thực sự bền vững:

1. Mỗi code có một ý nghĩa duy nhất trong namespace định nghĩa.
2. Code của một trạng thái đang tồn tại **không đổi do reorder**.
3. Không tái sử dụng code của trạng thái đã retire cho nghĩa khác.
4. Thêm hằng mới phải cấp code mới, không sinh từ ordinal.
5. Rename Java identifier không đổi code nếu business semantics giữ nguyên.
6. Giữ aliases cho dữ liệu cũ chỉ khi semantics còn tương đương và được document.
7. Có policy cho unknown code từ phiên bản tương lai.
8. Có tests bảo vệ code mapping và uniqueness.
9. Public API contract/documentation nói rõ code values.
10. Migration được làm bằng mapping lịch sử xác minh, không current indexes.

Nếu numeric codes còn có ý nghĩa nghiệp vụ (ví dụ HTTP 200, 404), đặt code theo specification tương ứng, không theo vị trí enum.

## 33. Test hợp đồng thay vì test implementation detail

Một unit test yếu:

```java
assertEquals(1, Status.PAID.ordinal());
```

Nó chỉ khóa thứ tự khai báo. Nếu reorder là thay đổi nội bộ hợp lệ, test sẽ cản trở refactor mà **không bảo vệ contract external**.

Một test tốt hơn:

```java
assertEquals("P", Status.PAID.code());
assertSame(Status.PAID, Status.fromCode("P"));
```

Nếu muốn chắc chắn không duplicate:
- Tập code từ `values()` vào `Set`.
- Assert kích thước Set bằng `values().length`.
- Với mã persistence public, assert tất cả known contract pairs bằng values cụ thể.

### Nguyên tắc

**Kiểm thử thứ mà khách hàng/database nhìn thấy, không khóa vị trí source nếu vị trí không thuộc contract.**

## 34. Runnable: kiểm thử contract không phụ thuộc ordinal

Lưu **`StableCodeContractTestDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

enum ShipmentStatus {
    CREATED("C"),
    IN_TRANSIT("T"),
    DELIVERED("D");

    private final String code;

    ShipmentStatus(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static ShipmentStatus fromCode(String code) {
        for (ShipmentStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException("unknown code");
    }
}

public class StableCodeContractTestDemo {
    public static void main(String[] args) {
        require(ShipmentStatus.CREATED.code().equals("C"));
        require(ShipmentStatus.IN_TRANSIT.code().equals("T"));
        require(ShipmentStatus.DELIVERED.code().equals("D"));

        Set<String> codes = new HashSet<>();

        for (ShipmentStatus status : ShipmentStatus.values()) {
            require(codes.add(status.code()));
            require(ShipmentStatus.fromCode(status.code()) == status);
        }

        System.out.println("CONTRACT_OK");
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("contract failed");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 StableCodeContractTestDemo.java
java StableCodeContractTestDemo
```

Stdout:

```text
CONTRACT_OK
```

Bạn có thể reorder `ShipmentStatus` mà vẫn pass test khi những code fields không đổi. Đây là kiểm thử **tính độc lập với declaration order**.

## 35. Test chống regression từ `ordinal()`

Ngoài unit tests, có thể thực hiện:
- Code search tìm `.ordinal()` trong persistence DTO mapper/API serializer.
- Static analysis rule tùy tổ chức cho việc `ordinal()` chảy qua boundary methods.
- Integration tests kiểm tra database raw values đúng các code đã công bố.
- Contract tests producer/consumer khác version.
- Schema tests với dữ liệu legacy và unknown values.
- Snapshot golden JSON/CSV theo stable code, không theo ordinal.
- Test migration từ bản mapping lịch sử bằng fixtures chính xác.

**Không cần cấm tuyệt đối mọi lần dùng `ordinal()`**. Có những đoạn algorithm internal legitimate; cần kiểm soát vị trí **nó trở thành external persistent representation**.

## 36. Khi nào `ordinal()` vẫn phù hợp?

Một số tình huống nội bộ:

- Dựa trên thứ tự enum để biểu diễn một internal array trong **cùng một phiên bản, cùng lifecycle**, nếu thiết kế thật sự cần thứ tự đó.
- Xử lý natural order của enum khi thứ tự khai báo được hiểu là thứ tự tự nhiên.
- Khảo sát/debugging: in name/ordinal để hiểu enum declaration.
- Các cấu trúc chuyên dụng JDK như `EnumSet`/`EnumMap` đã quản lý chi tiết nội bộ.

Ví dụ internal index:

```java
int index = current.ordinal();
```

Nếu dùng index để truy cập một array **được dựng từ đúng cùng enum declaration hiện tại**, code có thể đúng trong một runtime. Nhưng vẫn cần review:
- Array có độ dài/ordering tương ứng không?
- Có nguy cơ code này được reuse cho persisted data không?
- Có dễ thay bằng `EnumMap` để giảm coupling không?
- Có thread safety/visibility issues không?

Nói cách khác, **ordinal không “bị cấm trong Java”**; nó chỉ **không phải mã dữ liệu bền vững**.

## 37. Vì sao `EnumMap` tốt hơn array tự index bằng ordinal?

Giả sử:

```java
String[] labels = {"new", "paid", "shipped"};
String label = labels[status.ordinal()];
```

Nếu thêm hằng giữa NEW và PAID mà quên chỉnh mảng, `labels[status.ordinal()]` có thể trả label sai.

Dùng `EnumMap<OrderStatus,String>`:

```java
EnumMap<OrderStatus, String> labels =
        new EnumMap<>(OrderStatus.class);
labels.put(OrderStatus.NEW, "new");
labels.put(OrderStatus.PAID, "paid");
labels.put(OrderStatus.SHIPPED, "shipped");
```

Map gắn values với **enum constants làm keys**, không với raw array offsets do application quản lý. Nếu thêm hằng mới, bạn vẫn cần quyết định label cho nó; code đọc map có thể phát hiện missing key và xử lý rõ.

Đây là ví dụ **snippet**; để chạy, thêm `import java.util.EnumMap;` và định nghĩa enum.

## 38. Runnable: dùng EnumMap thay array ordinal

Lưu **`EnumMapInsteadOfOrdinalDemo.java`**:

```java
import java.util.EnumMap;

enum OrderStage {
    NEW, PENDING_REVIEW, PAID, SHIPPED
}

public class EnumMapInsteadOfOrdinalDemo {
    public static void main(String[] args) {
        EnumMap<OrderStage, String> labels =
                new EnumMap<>(OrderStage.class);

        labels.put(OrderStage.NEW, "new");
        labels.put(OrderStage.PENDING_REVIEW, "review");
        labels.put(OrderStage.PAID, "paid");
        labels.put(OrderStage.SHIPPED, "shipped");

        System.out.println(labels.get(OrderStage.PAID));
        System.out.println(labels.get(OrderStage.PENDING_REVIEW));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumMapInsteadOfOrdinalDemo.java
java EnumMapInsteadOfOrdinalDemo
```

Stdout:

```text
paid
review
```

`EnumMap` chuyên cho enum keys và tự xử lý representation nội bộ. Code ứng dụng không buộc label vào số thứ tự thô.

## 39. Enum natural order vẫn dựa vào declaration order

`Enum.compareTo` sắp xếp constants theo thứ tự ordinal. `EnumSet` và `EnumMap` cũng duyệt keys theo natural declaration order.

Nếu thứ tự UI/priority là một **business contract**, thêm `rank` explicit:

```java
enum Priority {
    LOW(10),
    MEDIUM(20),
    HIGH(30);

    private final int rank;

    Priority(int rank) {
        this.rank = rank;
    }

    int rank() {
        return rank;
    }
}
```

Sắp xếp bằng `Comparator.comparingInt(Priority::rank)` khi bạn muốn thứ tự dựa trên field rank. Có thể giữ gap (10,20,30) để chèn cấp mới mà không cần thay code các mức cũ, nhưng đừng nhầm rank với ID nếu hai vai trò cần contract riêng.

### Thứ tự không đồng nghĩa identity

`Priority.HIGH` là một canonical enum constant. Field `rank=30` mô tả relative ordering. `ordinal()` mô tả vị trí source. Ba ý nghĩa khác nhau.

## 40. Runnable: thứ tự explicit không phụ thuộc khai báo

Lưu **`EnumExplicitRankDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

enum Priority {
    HIGH(30),
    LOW(10),
    MEDIUM(20);

    private final int rank;

    Priority(int rank) {
        this.rank = rank;
    }

    int rank() {
        return rank;
    }
}

public class EnumExplicitRankDemo {
    public static void main(String[] args) {
        List<Priority> priorities =
                new ArrayList<>(List.of(Priority.values()));

        priorities.sort(Comparator.comparingInt(
                Priority::rank));

        for (Priority p : priorities) {
            System.out.println(p.name() + ":" + p.rank());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumExplicitRankDemo.java
java EnumExplicitRankDemo
```

Stdout:

```text
LOW:10
MEDIUM:20
HIGH:30
```

Declaration order là HIGH, LOW, MEDIUM; thứ tự theo rank là LOW, MEDIUM, HIGH. Nếu dùng ordinal để đại diện rank, hai ý nghĩa sẽ bị trộn.

## 41. Dữ liệu từ phiên bản tương lai: forward compatibility

Giả sử một service v2 thêm `REFUNDED("F")`. Service v1 đọc code `"F"` nhưng enum của v1 chưa có hằng REFUNDED.

Đây là vấn đề khác với ordinal:
- Với stable code, v1 nhận ra rõ ràng `"F"` là **unknown code**.
- Với ordinal, v1 có thể bị lỗi out-of-range hoặc ánh xạ sai thành hằng hiện có.
- Stable code giúp **fail rõ**, nhưng không tự dạy phiên bản cũ xử lý business semantics mới.

Các chiến lược forward compatibility:
- Unknown-as-error cho workflows nghiêm ngặt.
- Preserve raw code ở integration/event forwarding layer.
- Version hóa message schema.
- Feature gating để không xuất giá trị mới trước khi consumers sẵn sàng.
- Dùng sealed result type như `Known(Status) / Unknown(String rawCode)` ở boundary nếu cần bảo toàn unknown.

Không tùy tiện thêm `UNKNOWN` enum constant rồi map mọi code lạ về nó nếu hệ thống cần giữ mã gốc để retry/replay.

## 42. Đồng bộ mã giữa nhiều ngôn ngữ

Một Java service có:

```java
PAID("P")
```

Một service Go/TypeScript có thể có constant tương ứng `"P"`. Các hệ thống phối hợp theo **protocol field `"P"`**, không theo mỗi bên chọn thứ tự khai báo.

Định nghĩa codes trong:
- API specification.
- Schema registry/IDL khi phù hợp.
- Shared contract tests.
- Tài liệu migration/deprecation.
- Mã generated hoặc constants được sinh từ source contract nếu hệ thống hỗ trợ.

**Không bắt nhiều ngôn ngữ cam kết cùng một ordinal Java**. Mỗi ngôn ngữ có enum semantics khác nhau, và việc reorder source file Java không phải protocol versioning mechanism.

## 43. Tính tương thích khi rename hằng

Giả sử business muốn đổi tên Java constant `PAID` thành `SETTLED`, nhưng external code vẫn cần `"P"`.

```java
enum Status {
    SETTLED("P");
    // ...
}
```

Nếu code mapping không đổi, dữ liệu cũ `"P"` vẫn giải mã đúng về hằng mới. Đây là lợi ích rõ của **stable explicit code** so với lưu `name()`.

Tuy nhiên còn các compatibility surfaces khác:
- Java source code cũ tham chiếu `Status.PAID` sẽ phải sửa.
- Dữ liệu cũ lưu enum names với `name()` hoặc Java native enum serialization có thể bị ảnh hưởng.
- Audit logs/metrics dùng `name()` có thể cần mapping.
- External clients gọi trực tiếp tên hằng nếu công bố Java API cần migration.

Stable code bảo vệ **biên persistence/wire đã chọn dùng code**, không bảo đảm tự động tương thích mọi API khác.

## 44. Không tái sử dụng mã của trạng thái đã xóa

Một quy tắc rất quan trọng cho longevity:

Nếu `CANCELLED("C")` bị retire, **đừng gán `"C"` cho một trạng thái khác như `CHARGEBACK`** vì historical rows/events mang `"C"` vẫn còn nghĩa CANCELLED.

Thay thế có thể:
- Giữ hằng deprecated nếu domain vẫn phải đọc dữ liệu cũ.
- Đặt mapping legacy `"C"` sang một đại diện historical record có ý nghĩa rõ.
- Dùng bảng chuyển đổi mã cũ, có migration.
- Dành mã mới cho trạng thái mới.
- Version hóa API/schema nếu semantics thay đổi căn bản.

**Thay code dưới cùng một chuỗi là một breaking data-contract change**, dù `ordinal()` không còn xuất hiện.

## 45. Logging và audit: tên nào nên ghi?

Một audit record nên chứa:
- Event type ổn định.
- Stable status code.
- Context (entity ID, timestamp, actor).
- Schema version nếu cần replay.
- Human-readable label như thông tin bổ sung, không phải sole identifier.

Ví dụ thông điệp minh họa:

```text
order_id=10 status_code=P status_label=Paid schema_version=2
```

Không chỉ ghi `status_ordinal=1` vì người đọc tương lai không biết source enum nào đã sinh nó.

Nếu log được giữ rất ngắn hạn, ordinal vẫn có thể gây rắc rối khi incident investigation kéo qua deployments. Stable code thường rẻ hơn trong dài hạn.

## 46. Khi nào một explicit code vẫn không đủ?

Một code có thể ổn định nhưng **ngữ nghĩa thay đổi**. Ví dụ `"P"` hôm qua nghĩa “đã thanh toán đầy đủ”, hôm nay nghĩa “đã đặt cọc”. Giữ cùng code có thể làm dữ liệu tương thích về cú pháp nhưng **không tương thích về business semantics**.

Cần thêm:
- Versioning hoặc trạng thái mới với mã mới.
- Migration có quy tắc nghiệp vụ.
- Validation và contract tests.
- Documentation thời điểm ý nghĩa thay đổi.
- Kiểm soát quyền sở hữu thay đổi schema.

**Stable syntax không tự bảo đảm stable meaning.** Tránh `ordinal()` chỉ là lớp phòng vệ đầu tiên.

## 47. Khác biệt với Java native enum serialization

Java native object serialization có cơ chế riêng cho enum constants: về cơ bản resolve theo enum type/name, không lưu `ordinal()` như một public persistence representation cho hằng theo cách nhiều developer tự làm.

Điều này có hai hệ quả:
- Java native enum deserialization không nên được mô tả là `values()[ordinal]` đơn giản.
- Rename/remove enum constant có thể vẫn gây compatibility issue do dữ liệu name/type cũ.

Các thư viện JSON, ORM, Protobuf hay serializer khác **có mapping policy riêng**. Đừng suy rằng vì native Java enum serialization dựa vào name nên mọi framework cũng vậy.

### Ví dụ sai lầm phổ biến

Nói “Java đã serialize enum được nên lưu `ordinal()` vào DB cũng sẽ an toàn” là sai: bạn đang tự chọn một representation khác với cơ chế serialization chuẩn.

## 48. Checklist review một đoạn persistence code

Khi thấy enum field được ghi vào database hoặc message:

1. Field wire/database đang là number hay String?
2. Number đó đến từ **explicit code** hay từ `ordinal()`?
3. Nếu source enum reorder, raw stored value có giữ nghĩa không?
4. Nếu thêm hằng mới, reader cũ phản ứng thế nào?
5. Nếu rename hằng, raw stored value có bị thay đổi không?
6. Mapping được document ở đâu và có owner không?
7. Có validation uniqueness không?
8. Unknown/null/empty code có policy rõ không?
9. Có long-lived historical records dùng old mappings không?
10. Có integration tests đọc dữ liệu cũ bằng version mới không?
11. Có rolling deployment với mixed versions không?
12. Có audit/observability cho unknown codes không?
13. Có DB constraint/DDL migration cần cập nhật không?
14. Có chỗ nào vô tình dùng `values()[id]` không?
15. Có chỗ nào dùng `toString()` làm ID không?
16. JPA mapping đang là ORDINAL, STRING hay converter?
17. Nếu dùng `EnumType.STRING`, rename/delete được quản lý thế nào?
18. Nếu dùng explicit code, đã không tái sử dụng mã cũ cho nghĩa mới chưa?
19. Có đường rollback an toàn khi reader/writer chuyển cột không?
20. Có tests phát hiện double meanings của historical ordinal không?

## 49. Bài tập 1 — Thêm hằng vào giữa

Cho:

```java
enum Status {
    NEW, PAID, SHIPPED
}
```

DB lưu `PAID.ordinal()`. Sau khi sửa declaration thành `NEW, REVIEW, PAID, SHIPPED`, số cũ `1` giải mã bằng `values()[1]` thành gì?

**Đáp án:** `REVIEW`, không phải PAID. Đây là silent data corruption nếu hệ thống không nhận diện mismatch.

## 50. Bài tập 2 — Reorder nhưng tên giữ nguyên

`enum Color { RED, GREEN, BLUE }` được đổi thành `BLUE, RED, GREEN`. `Color.RED.name()` đổi không? `ordinal()` đổi không?

**Đáp án:** `name()` vẫn `"RED"`; `ordinal()` đổi từ 0 sang 1.

## 51. Bài tập 3 — Mã numeric có luôn xấu?

`enum Status { NEW(100), PAID(200) }` với constructor field `code`. Lưu `status.code()` vào DB có cùng vấn đề với ordinal không?

**Đáp án:** Không, nếu `100`/`200` được định nghĩa và giữ ổn định như hợp đồng riêng. Số nguyên không phải vấn đề; **nguồn gốc từ vị trí khai báo** mới là vấn đề.

## 52. Bài tập 4 — Dùng `name()`

Lưu `status.name()` rồi reorder constants. DB có sai nghĩa không?

**Đáp án:** Không vì reorder không đổi tên. Tuy nhiên rename/delete constants vẫn cần migration/compatibility strategy.

## 53. Bài tập 5 — Dùng `toString()`

Enum override `toString()` để trả nhãn tiếng Việt. Có nên lưu kết quả vào DB làm trạng thái canonical không?

**Đáp án:** Thường không; nhãn UI có thể đổi theo ngôn ngữ và wording. Tách stable code khỏi display label.

## 54. Bài tập 6 — Unknown ordinal nằm trong phạm vi

DB có số 1; enum mới có 4 constants. `values()[1]` chạy không lỗi. Có thể kết luận dữ liệu đúng không?

**Đáp án:** Không. Số hợp lệ theo chỉ số vẫn có thể có ý nghĩa khác ở version cũ.

## 55. Bài tập 7 — Unknown ordinal ngoài phạm vi

Một old record có số 9, enum hiện có 4 constants. `values()[9]` làm gì?

**Đáp án:** `ArrayIndexOutOfBoundsException`. Catch exception không giải quyết trường hợp số hợp lệ nhưng mapping sai.

## 56. Bài tập 8 — Legacy mapping

V1: `0 NEW, 1 PAID, 2 SHIPPED`. V2: `0 NEW, 1 REVIEW, 2 PAID, 3 SHIPPED`. Khi backfill record có legacy ordinal 2, stable code nào?

**Đáp án:** Mã của `SHIPPED` theo mapping V1, chẳng hạn `"S"`, không phải mã PAID của V2.

## 57. Bài tập 9 — Mixed versions

V1 và V2 cùng ghi raw ordinal 1 nhưng biểu diễn hai trạng thái khác nhau; không có schema version.

**Đáp án:** Không thể luôn suy ra đúng hằng từ số 1 duy nhất. Cần bổ sung dữ liệu lịch sử/audit để phân loại, hoặc xử lý records không thể kết luận.

## 58. Bài tập 10 — Mã trùng

`NEW("N")` và `NOTIFIED("N")` cùng code `N`. Decoder nào nguy hiểm?

**Đáp án:** Decoder lấy hằng đầu tiên/tùy thứ tự và bỏ qua trùng; mapping phụ thuộc thứ tự hoặc bị ghi đè. Cần validate unique codes và fail-fast khi duplicate.

## 59. Bài tập 11 — Map static được tạo lúc nào?

Có nên viết enum constructor `Registry(String code) { BY_CODE.put(code,this); }` khi `BY_CODE` là static mutable map field khai báo sau constants?

**Đáp án:** Không nên và có các compile-time initialization restrictions liên quan tham chiếu static nonconstant fields của enum trong constructor. Tạo map trong static block sau constants, khi `values()` sẵn sàng.

## 60. Bài tập 12 — JPA ORDINAL

Một field dùng `@Enumerated(EnumType.ORDINAL)`. Developer chèn hằng giữa enum list nhưng không migration DB.

**Đáp án:** Có nguy cơ dữ liệu cũ bị đọc sai. Cần xem raw stored values, historical mapping và migration/mapper được quản lý.

## 61. Bài tập 13 — JPA STRING

Đổi mapping sang `EnumType.STRING` có tự chuyển integers cũ thành đúng names không?

**Đáp án:** Không. Cần data migration và kiểm chứng; annotation đổi representation của code chứ không tự khôi phục ý nghĩa historical ordinals.

## 62. Bài tập 14 — Thêm constant cuối

Thêm `REFUNDED` vào cuối enum có phá ordinal của các hằng cũ không?

**Đáp án:** Không dịch các ordinals cũ ngay trong thay đổi đó. Nhưng consumer cũ chưa chắc xử lý được hằng mới và nguy cơ reorder tương lai vẫn tồn tại; không dùng lý do này để thiết kế ordinal persistence dài hạn.

## 63. Bài tập 15 — Idempotent migration

Backfill chạy lại lần hai có thể làm gì sai nếu lấy dữ liệu từ cột đã chuyển thay vì legacy field?

**Đáp án:** Có thể đọc nhầm code mới thành ordinal hoặc ghi lại dựa trên mapping sai. Migration phải có source/target columns và điều kiện version/idempotency rõ; test rerun và rollback.

## 64. Bài tập 16 — Name vs code sau rename

Java constant đổi tên `PAID` → `SETTLED` nhưng mã external vẫn `"P"`. Dữ liệu dùng code có còn giải mã hợp lệ không?

**Đáp án:** Có thể có, nếu decoder mới ánh xạ `"P"` đến SETTLED và ngữ nghĩa giữ nguyên. Dữ liệu lưu `name() == "PAID"` cần xử lý riêng.

## 65. Bài tập 17 — Dữ liệu nhiều ngôn ngữ

Một Go service và Java service dùng cùng protocol status. Có nên truyền `ordinal` Java?

**Đáp án:** Không. Công bố explicit stable code trong schema chung; mỗi ngôn ngữ có implementation/mapping riêng và contract tests.

## 66. Bài tập 18 — Default unknown về NEW

Decoder nhận code `"F"` chưa biết rồi trả `Status.NEW`. Có an toàn?

**Đáp án:** Thường không với nghiệp vụ nhạy cảm: unknown và NEW là hai ngữ nghĩa khác nhau. Trả lỗi hoặc biểu diễn Unknown chứa raw code theo requirement.

## 67. Bài tập 19 — EnumSet

`EnumSet` duyệt constants theo thứ tự nào? Có nên persist vị trí khi iterator duyệt không?

**Đáp án:** Natural declaration order. Không persist vị trí như ID; Set có thể biểu diễn các constants trực tiếp, hoặc mỗi constant xuất code ổn định khi lưu.

## 68. Bài tập 20 — Trạng thái bị loại bỏ

Một trạng thái cũ có code `"C"` không còn dùng. Có thể tái sử dụng C cho trạng thái mới không?

**Đáp án:** Không nên nếu historical events/records vẫn còn. Reuse sẽ làm dữ liệu cũ mang nghĩa mới. Dùng code mới và migration/alias được quản lý.

## 69. Bài tập 21 — Test nào tốt hơn?

A. `assertEquals(1, Status.PAID.ordinal())`.  
B. `assertEquals("P", Status.PAID.code())` và `assertSame(Status.PAID, Status.fromCode("P"))`.

**Đáp án:** B bảo vệ persistence contract. A chỉ bảo vệ thứ tự declaration và làm test phụ thuộc chi tiết có thể refactor.

## 70. Bài tập 22 — Stable code nhưng semantics đổi

Code `"P"` trước nghĩa “paid in full”, sau nghĩa “partially paid”. Có còn tương thích dữ liệu hoàn toàn không?

**Đáp án:** Không. Mã vẫn giống nhưng business semantics thay đổi; cần version/mã mới hoặc migration có chủ đích.

## 71. Bài tập 23 — Gắn rank explicit

Enum khai báo HIGH, LOW, MEDIUM nhưng field `rank` là 30, 10, 20. Nên dùng gì để sort theo priority?

**Đáp án:** `Comparator.comparingInt(Status::rank)` (với enum type phù hợp), không `ordinal()`. Rank có thể khác vị trí source.

## 72. Bài tập 24 — Null code

`fromCode(null)` nên làm gì?

**Đáp án:** Phụ thuộc API: fail với exception rõ hoặc trả Optional.empty. Không âm thầm map thành một trạng thái hợp lệ nếu null không có nghĩa như vậy; document contract.

## 73. Bài tập 25 — Serializer

Java native enum serialization dùng cơ chế đặc biệt theo type/name. Điều đó có chứng minh lưu `ordinal()` vào JSON/DB an toàn không?

**Đáp án:** Không. Native serialization và custom persistence mappings khác nhau. Mỗi boundary cần quy định representation riêng.

## 74. Bài tập 26 — Identity của hằng

`Status.PAID == Status.valueOf("PAID")` có true không?

**Đáp án:** True khi Status có hằng PAID, vì `valueOf` trả canonical enum constant. Identity semantics không nói gì về sự ổn định của ordinal.

## 75. Bài tập 27 — Có nên hardcode historical ordinals trong migration?

`switch (oldOrdinal) { case 1 -> PAID; ... }` là “vi phạm lời khuyên không dùng ordinal” không?

**Đáp án:** Không nếu được **cô lập trong migration từ một schema lịch sử đã được xác minh**, không được dùng làm write representation mới. Đây là cách đọc có kiểm soát dữ liệu ordinal cũ.

## 76. Bài tập 28 — Cho phép reorder sau khi đã dùng stable code?

Nếu tất cả external mapping thực sự dùng explicit stable code, reorder có thể an toàn hoàn toàn không?

**Đáp án:** Chưa chắc: `values()`, `ordinal()`, `compareTo`, `EnumSet`/`EnumMap` iteration và UI source-order code vẫn có thể đổi. Stable code bảo vệ boundary được thiết kế, không phủ mọi behavior.

## 77. Bài tập 29 — Đơn vị kiểm chứng migration

Migration chuyển 0→N, 1→P, 2→S. Có nên chỉ kiểm tra số rows không?

**Đáp án:** Không. Cần row-level sampling/business invariants, phân bố theo trạng thái, unknown counts, unique constraints, dual-write consistency và rollback plan.

## 78. Bài tập 30 — Quyết định cuối

Ứng dụng có một enum được lưu trong DB, gửi qua Kafka và dùng trong public API. Chọn `ordinal()`, `name()` hay explicit code?

**Đáp án:** Thường ưu tiên **explicit stable code** có specification, decoder, uniqueness validation, migration policy và compatibility tests. `name()` có thể dùng khi tên source được cam kết ổn định; `ordinal()` không nên làm long-lived contract.

## 79. Checklist tránh ordinal persistence

- [ ] Không ghi `enum.ordinal()` trực tiếp vào DB/API/event/config nếu giá trị cần bền vững.
- [ ] Không đọc dữ liệu lịch sử bằng `EnumType.values()[saved]` khi declaration từng đổi.
- [ ] Có tài liệu exact historical ordinal mappings nếu hệ thống cũ đã dùng ordinal.
- [ ] Stable String/int code được khai báo riêng, không suy từ index/ordinal.
- [ ] Mỗi code unique, không null theo contract.
- [ ] Có tests phát hiện duplicate codes.
- [ ] Có tests giữ nguyên mapping code ↔ constant qua reorder.
- [ ] Có policy cho rename/delete/retire constants.
- [ ] Không tái sử dụng code cũ cho nghĩa mới.
- [ ] Không dùng UI `toString()` làm mã persistence.
- [ ] Nếu lưu `name()`, đã quản lý rủi ro rename.
- [ ] Nếu JPA, xác định mapping `ORDINAL`/`STRING`/converter đang thực sự áp dụng.
- [ ] Không đổi JPA annotation mà bỏ qua migration dữ liệu hiện có.
- [ ] Có migration theo **lịch sử version đúng**, không theo enum current values.
- [ ] Có thống kê invalid/mixed-era values trước migration.
- [ ] Có chiến lược xử lý những ordinal lịch sử không thể giải mã chắc chắn.
- [ ] Có kế hoạch rolling deploy/dual-read/dual-write thực tế.
- [ ] Có rollback và data integrity verification.
- [ ] API schema/public docs liệt kê codes và semantics.
- [ ] Unknown code được phát hiện và xử lý đúng contract.
- [ ] Không default unknown về một trạng thái nghiệp vụ bình thường không có căn cứ.
- [ ] Có automated contract tests producer/consumer.
- [ ] Có quan sát lỗi decode trong production.
- [ ] Có phân biệt code, name, label, rank và ordinal.
- [ ] Có xét tác động reorder tới sorting/`values()`/`EnumSet`/`EnumMap`.
- [ ] Không đưa code sinh từ `ordinal()+1` hoặc phép toán ordinal khác.
- [ ] Map lookup được dựng sau khi enum constants đã sẵn sàng.
- [ ] Nếu shared enum contract với ngôn ngữ khác, mọi bên dùng cùng stable code.
- [ ] Khi semantics đổi, có version hoặc mã mới phù hợp.
- [ ] Bản viết có thử reorder/add constant và xác nhận persisted code không đổi.

## 80. Tổng kết

`ordinal()` là **vị trí zero-based của một enum constant trong source declaration hiện tại**. Nó không phải mã nghiệp vụ ổn định, dù Java bảo đảm identity của từng hằng. Chèn, xóa hoặc sắp xếp lại constants có thể đổi ordinals và làm cơ sở dữ liệu, message/API payload cũ bị hiểu sai.

**Để dữ liệu sống qua nhiều phiên bản phần mềm:**
1. Khai báo **explicit String/int code** cho từng hằng.
2. Viết `code()` và `fromCode(...)` độc lập với declaration order.
3. Validate code uniqueness, xử lý null/unknown rõ.
4. Quản lý mã như **external contract**: không tùy tiện đổi/tái sử dụng.
5. Nếu đã lưu ordinal, migration dựa vào **historical mapping đúng**, không dựa vào enum source mới.
6. Kiểm thử database/API compatibility khi thêm/rename/reorder constants.

Nói ngắn gọn: **`ordinal()` trả một con số về vị trí của hằng, không phải lời hứa về ý nghĩa của con số đó ở bản phát hành tương lai.** Hãy tách hai vai trò ấy trước khi đưa enum ra khỏi bộ nhớ của một phiên chạy.

## Tham khảo Java 17

- Java SE 17 `java.lang.Enum.ordinal()` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html#ordinal()
- Java SE 17 JLS `8.9 — Enum Classes`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9
- Java SE 17 `EnumSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html
- Java SE 17 `EnumMap`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html
