# Lạm dụng `default` làm mất exhaustive check trong Java Pattern Matching

## Mục tiêu bài học

Trong nhóm **Lỗi thường gặp**, một lỗi thiết kế đáng chú ý là **thêm `default` vào mọi `switch` cho “chắc chắn”**. Với một tập biến thể đóng như `enum` hay `sealed interface`, cách làm này có thể khiến compiler **không còn buộc bạn xử lý tường minh biến thể mới** khi mã nguồn phát triển. Chương trình vẫn biên dịch, nhưng hành vi mới bị đưa vào một nhánh chung ít ý nghĩa, gây bỏ sót nghiệp vụ.

Bài học giúp bạn:
- Hiểu **exhaustiveness** của `switch` và giá trị của kiểm tra tại compile time.
- So sánh `switch` không có `default` với `switch` có `default` trên `enum` và `sealed hierarchy`.
- Chứng minh bằng `javac --release 21` rằng thêm một giá trị `enum` hoặc một permitted subtype sẽ khiến bản không có `default` yêu cầu cập nhật, trong khi bản dùng `default` vẫn qua bước biên dịch.
- Phân biệt `default` với `case null`, guard `when` và các trường hợp thực sự cần fallback.
- Chọn chiến lược bảo toàn tính đầy đủ của nhánh mà vẫn xử lý được đầu vào mở, lỗi và tương thích phiên bản.

**Phạm vi phiên bản:** ví dụ dùng **Java 21**. Pattern Matching for `switch` và Record Patterns chính thức trong Java 21 (JEP 441 và JEP 440). Với Java 17, pattern matching trong `switch` từng là tính năng preview; để chạy các ví dụ này, hãy dùng JDK 21 trở lên.

## 1. Exhaustive switch là gì?

Một `switch` được xem là **exhaustive** khi các case labels của nó đủ bao phủ mọi giá trị đầu vào mà quy tắc ngôn ngữ yêu cầu xử lý. Với `switch expression`, đây là điều kiện compile-time quan trọng: một biểu thức phải có khả năng sinh ra giá trị (hoặc ném exception) trên mọi đường đi phù hợp.

Xét:

```java
enum Phase { QUEUED, RUNNING, DONE }

static String phaseName(Phase phase) {
    return switch (phase) {
        case QUEUED -> "QUEUE";
        case RUNNING -> "RUN";
        case DONE -> "FINISH";
    };
}
```

Đây là **đoạn minh họa**, có thể đặt trong một lớp Java. Ba nhánh liệt kê đầy đủ ba hằng số của `Phase`, do đó `switch expression` đủ exhaustive **không cần `default`**.

Điểm hay của cách viết này không nằm ở việc bỏ được một dòng: nó thể hiện một cam kết kiểu dữ liệu.

> Nếu tập trạng thái `Phase` thay đổi, nơi phân loại trạng thái phải được xem xét lại.

Nếu sau này thêm `PAUSED`, khi biên dịch lại toàn bộ mã, `switch` trên không còn đủ các nhánh và `javac` báo lỗi. Đây là **tín hiệu cập nhật chính sách** ngay trong quá trình build, trước khi ứng dụng chạy.

Ngược lại:

```java
return switch (phase) {
    case QUEUED -> "QUEUE";
    case RUNNING -> "RUN";
    case DONE -> "FINISH";
    default -> "OTHER";
};
```

Nhánh `default` bao phủ phần còn lại của selector (trừ xử lý `null` đặc biệt sẽ bàn bên dưới). Khi thêm `PAUSED`, compiler không buộc sửa `switch`: chương trình tiếp tục chạy, trả `OTHER`. Đó có thể là chính sách đúng **nếu bạn thực sự muốn gộp mọi trạng thái tương lai**; nhưng thường là bug khi mỗi trạng thái cần xử lý riêng.

## 2. Vì sao `default` làm yếu tín hiệu của compiler?

Giả sử ứng dụng có công việc chạy qua các giai đoạn:

| Giai đoạn | Hành vi mong đợi |
|---|---|
| `QUEUED` | Hiển thị `QUEUE` |
| `RUNNING` | Hiển thị `RUN` |
| `DONE` | Hiển thị `FINISH` |
| `PAUSED` (thêm sau này) | **Cần quyết định mới**, ví dụ có hiển thị `PAUSE` hay không |

Ở thời điểm đầu, hai phiên bản `switch` — liệt kê đủ case và liệt kê đủ case cộng `default` — có thể cho kết quả giống hệt nhau trên ba giá trị hiện có. Điều đó **không có nghĩa chúng có cùng khả năng phát hiện thay đổi trong tương lai**.

| Khi thêm biến thể | Không có `default` | Có `default` |
|---|---|---|
| Thêm `enum Phase.PAUSED` | Compiler yêu cầu cập nhật các nhánh trong `switch expression` | `PAUSED` tự đi vào `default`; build vẫn qua |
| Thêm subtype vào một `sealed interface` | `switch expression` thiếu case cho subtype mới, compiler báo lỗi | Nhánh `default` có thể nhận subtype mới mà không cần thay logic |
| Thêm guard `when` quá hẹp | Cần đảm bảo có nhánh không guard hoặc nhánh khác bao phủ phần còn lại | `default` che khả năng thiếu đường đi của biến thể cũ |
| Input `null` | Không tự nhiên được xử lý nhờ các type patterns | **`default` cũng không tự xử lý `null`** |

Vì vậy, câu hỏi review không phải “`default` có hợp lệ không?” mà là:

**“Nếu ngày mai danh sách biến thể thay đổi, tôi muốn build bắt buộc tôi xem xét lại logic này hay muốn tự động xử lý bằng fallback?”**

Trong một mô hình domain đóng, câu trả lời thường là **muốn compiler nhắc cập nhật**.

## 3. Trường hợp `enum`: mặc định có thể che trạng thái mới

Ban đầu:

```java
enum Phase { QUEUED, RUNNING, DONE }

static String classify(Phase phase) {
    return switch (phase) {
        case QUEUED -> "QUEUE";
        case RUNNING -> "RUN";
        case DONE -> "FINISH";
    };
}
```

Khi thêm `PAUSED`:

```java
enum Phase { QUEUED, RUNNING, DONE, PAUSED }
```

Bản `classify` cũ **không biên dịch** khi build lại với `--release 21`, vì `switch expression` chưa cover `PAUSED`. Đây không phải bất tiện ngẫu nhiên: nó chỉ ra một chỗ mà yêu cầu nghiệp vụ cần được cập nhật.

Nếu đã viết:

```java
static String classify(Phase phase) {
    return switch (phase) {
        case QUEUED -> "QUEUE";
        case RUNNING -> "RUN";
        case DONE -> "FINISH";
        default -> "UNKNOWN_PHASE";
    };
}
```

bản đó vẫn biên dịch khi `Phase` xuất hiện `PAUSED`, nhưng kết quả sẽ là `UNKNOWN_PHASE`. Nơi khác có thể đã thêm xử lý pause đúng nghĩa, còn màn hình này âm thầm biến nó thành trạng thái “unknown”.

**Không có `default` không có nghĩa là runtime luôn được bảo đảm an toàn khi thay đổi class/jar mà không biên dịch lại.** Ưu thế chính ở đây là **compile-time exhaustiveness khi biên dịch mã phụ thuộc với định nghĩa kiểu mới**. Khi dùng nhiều binary/jar khác phiên bản, vẫn phải kiểm thử tương thích riêng.

## 4. Trường hợp `sealed interface`: để kiểu đóng hỗ trợ compiler

Một `sealed interface` giới hạn danh sách subtype trực tiếp được phép triển khai. Ví dụ:

```java
sealed interface Event permits Started, Stopped, Failed {}

record Started(String service) implements Event {}
record Stopped(String service) implements Event {}
record Failed(String service, int code) implements Event {}
```

Vì ba record trên là các permitted direct subtypes trong ví dụ, có thể viết:

```java
static String classify(Event event) {
    return switch (event) {
        case Started(var service) -> "STARTED:" + service;
        case Stopped(var service) -> "STOPPED:" + service;
        case Failed(var service, var code) -> "FAILED:" + code;
    };
}
```

**Đoạn minh họa trên không có `case null`:** với selector `null`, pattern switch sẽ ném `NullPointerException`, không phải tự rẽ sang một subtype. Nếu muốn xử lý null, thêm `case null` như chương trình độc lập ở phần 6.

Khi thêm một permitted subtype mới:

```java
record Retried(String service) implements Event {}
```

và cập nhật khai báo sealed thành `permits Started, Stopped, Failed, Retried`, compiler yêu cầu `switch expression` liệt kê đủ nhánh phù hợp (nếu không có nhánh bao phủ mới). Đây là một trong những lợi thế quan trọng khi kết hợp `sealed` với pattern matching.

Nhưng nếu mã ban đầu kết thúc bằng:

```java
default -> "UNRECOGNIZED_EVENT";
```

`Retried` sẽ được gộp vào `default` khi chạy. Có thể mất các hành động domain quan trọng như ghi trạng thái retry, hiển thị chi tiết hoặc phát metric chuyên biệt.

### Đóng nghĩa là có thể kiểm tra đầy đủ, không phải mọi pattern đều tự đầy đủ

Cần phân biệt:

- `sealed` đóng danh sách permitted subtypes, giúp compiler suy luận các biến thể.
- **Record pattern** phân rã component; một record pattern với guard `when` chỉ khớp phần thỏa điều kiện.
- **Một nhánh có guard** không thay thế một nhánh bao phủ mọi giá trị của subtype đó. Nếu có `case Started s when ...`, vẫn cần đường đi cho `Started` không thỏa guard, trừ khi nhánh khác đã bao phủ.
- `case Event event` là một **total type pattern cho các giá trị Event không null**, nhưng nó chỉ hợp lý khi mọi subtype thực sự có cùng xử lý. Nó cũng có thể che nhu cầu phân biệt subtype mới giống như `default`.

Sử dụng `sealed` có ích nhất khi tập biến thể là một phần của thiết kế domain và nơi xử lý **có trách nhiệm biết đầy đủ chúng**.

## 5. Ba loại “đầy đủ” không nên trộn lẫn

### 5.1. Bao phủ giá trị tại compile time

Compiler kiểm tra tập `case` theo **kiểu tĩnh của selector**, loại pattern, quan hệ subtype và tính exhaustive. Việc nó chấp nhận `default` chỉ nói rằng đã có đường đi bao phủ phần còn lại; nó không chứng minh mỗi biến thể được xử lý theo nghĩa nghiệp vụ.

### 5.2. Đáp ứng mọi hành vi nghiệp vụ

Một `default -> "OTHER"` có thể làm một `switch` exhaustive theo ngôn ngữ nhưng **không đầy đủ về mặt nghiệp vụ**. Khi domain có thêm biến thể, code không buộc tác giả quyết định cách xử lý riêng. Đây là **lỗi trọng tâm của việc lạm dụng default**.

### 5.3. Xử lý `null`

Với pattern matching `switch` trong Java 21, **`default` bình thường không bắt selector `null`**. Nếu selector có thể null và bạn muốn xử lý nó, dùng `case null` rõ ràng hoặc kiểm tra trước khi gọi `switch`.

Ví dụ:

```java
return switch (phase) {
    case null -> "PHASE_NULL";
    case QUEUED -> "QUEUE";
    case RUNNING -> "RUN";
    case DONE -> "FINISH";
};
```

Tập case này vừa thể hiện rõ chính sách của ba trạng thái `Phase`, vừa làm rõ chính sách khi selector null. Ngược lại, `default -> "OTHER"` đứng ở cuối một `switch` không có `case null` **không** ngăn được `NullPointerException` khi input null.

## 6. Chương trình Java 21: hai cách viết cho cùng trạng thái hiện tại

Tạo tệp **`ExhaustivenessDemo.java`**:

```java
import java.util.Objects;

public class ExhaustivenessDemo {
    sealed interface Event permits Started, Stopped, Failed {}
    record Started(String service) implements Event {}
    record Stopped(String service) implements Event {}
    record Failed(String service, int code) implements Event {}
    enum Phase { QUEUED, RUNNING, DONE }

    // Khong co default: compiler theo doi day du permitted subtypes.
    static String eventNoDefault(Event e) {
        return switch (e) {
            case null -> "EVENT_NULL";
            case Started(var service) -> "STARTED:" + service;
            case Stopped(var service) -> "STOPPED:" + service;
            case Failed(var service, var code) -> "FAILED:" + code;
        };
    }

    // Co default: neu sealed hierarchy mo rong, nhanh nay co the che sot.
    static String eventWithDefault(Event e) {
        return switch (e) {
            case null -> "EVENT_NULL";
            case Started(var service) -> "STARTED:" + service;
            case Stopped(var service) -> "STOPPED:" + service;
            case Failed(var service, var code) -> "FAILED:" + code;
            default -> "UNRECOGNIZED_EVENT";
        };
    }

    static String phaseNoDefault(Phase phase) {
        return switch (phase) {
            case null -> "PHASE_NULL";
            case QUEUED -> "QUEUE";
            case RUNNING -> "RUN";
            case DONE -> "FINISH";
        };
    }

    static String phaseWithDefault(Phase phase) {
        return switch (phase) {
            case null -> "PHASE_NULL";
            case QUEUED -> "QUEUE";
            case RUNNING -> "RUN";
            case DONE -> "FINISH";
            default -> "UNKNOWN_PHASE";
        };
    }

    static String defaultDoesNotCatchNull(Phase phase) {
        return switch (phase) {
            case QUEUED -> "QUEUE";
            default -> "OTHER";
        };
    }

    static void eventCheck(String title, Event event, String expected) {
        String strict = eventNoDefault(event);
        String broad = eventWithDefault(event);
        if (!Objects.equals(strict, expected) || !Objects.equals(broad, expected)) {
            throw new AssertionError("Mismatch " + title);
        }
        System.out.println(title + " -> " + strict);
    }

    static void phaseCheck(String title, Phase phase, String expected) {
        String strict = phaseNoDefault(phase);
        String broad = phaseWithDefault(phase);
        if (!Objects.equals(strict, expected) || !Objects.equals(broad, expected)) {
            throw new AssertionError("Mismatch " + title);
        }
        System.out.println(title + " -> " + strict);
    }

    public static void main(String[] args) {
        eventCheck("started", new Started("billing"), "STARTED:billing");
        eventCheck("stopped", new Stopped("billing"), "STOPPED:billing");
        eventCheck("failed", new Failed("billing", 503), "FAILED:503");
        eventCheck("null component", new Started(null), "STARTED:null");
        eventCheck("null event", null, "EVENT_NULL");

        phaseCheck("queued", Phase.QUEUED, "QUEUE");
        phaseCheck("running", Phase.RUNNING, "RUN");
        phaseCheck("done", Phase.DONE, "FINISH");
        phaseCheck("null phase", null, "PHASE_NULL");

        try {
            defaultDoesNotCatchNull(null);
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println("default without case null -> NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 ExhaustivenessDemo.java
java ExhaustivenessDemo
```

**Stdout chính xác đã được kiểm tra:**

```text
started -> STARTED:billing
stopped -> STOPPED:billing
failed -> FAILED:503
null component -> STARTED:null
null event -> EVENT_NULL
queued -> QUEUE
running -> RUN
done -> FINISH
null phase -> PHASE_NULL
default without case null -> NullPointerException
```

Trong chương trình:

1. Hai cách viết có `default` và không có `default` trả cùng kết quả cho **toàn bộ biến thể hiện hữu**; `eventCheck` và `phaseCheck` so cả hai với giá trị `expected` độc lập.
2. `Started(null)` vẫn khớp pattern `Started(var service)`: record `Started` tồn tại, còn component `service` kiểu tham chiếu có thể null. Kết quả `STARTED:null` đến từ phép nối chuỗi, không phải một exception.
3. `case null` xử lý được selector null khi được khai báo.
4. Hàm `defaultDoesNotCatchNull` cố ý không có `case null`, và runtime ném `NullPointerException` dù `default` tồn tại. `try/catch` xác nhận điều đó thay vì làm cả demo thất bại.

**Giới hạn của phép thử:** Hai implementation hiện tại cho cùng output không chứng minh chúng sẽ được cập nhật đúng khi tập biến thể thay đổi. Để quan sát khác biệt, cần kiểm thử cả quá trình **evolve type + recompile**, như phần tiếp theo.

## 7. Thực nghiệm compiler: thêm giá trị enum

Tạo riêng tệp **`EnumNoDefaultAfterChange.java`**, cố ý khai báo thêm `PAUSED` nhưng thiếu nhánh:

```java
public class EnumNoDefaultAfterChange {
    enum Phase { QUEUED, RUNNING, DONE, PAUSED }

    static String classify(Phase phase) {
        return switch (phase) {
            case QUEUED -> "QUEUE";
            case RUNNING -> "RUN";
            case DONE -> "FINISH";
        };
    }
}
```

Biên dịch:

```bash
javac --release 21 EnumNoDefaultAfterChange.java
```

**Kết quả mong đợi:** compiler **từ chối** vì `switch expression` không bao phủ mọi giá trị `Phase` sau khi thêm `PAUSED`. Không nên phụ thuộc vào nguyên văn thông báo lỗi vì cách trình bày có thể thay đổi giữa các bản `javac`.

Phiên bản thêm `default` sau đây lại biên dịch:

```java
public class EnumWithDefaultAfterChange {
    enum Phase { QUEUED, RUNNING, DONE, PAUSED }

    static String classify(Phase phase) {
        return switch (phase) {
            case QUEUED -> "QUEUE";
            case RUNNING -> "RUN";
            case DONE -> "FINISH";
            default -> "UNKNOWN_PHASE";
        };
    }

    public static void main(String[] args) {
        System.out.println("new enum value -> " + classify(Phase.PAUSED));
    }
}
```

Chạy:

```bash
javac --release 21 EnumWithDefaultAfterChange.java
java EnumWithDefaultAfterChange
```

**Stdout:**

```text
new enum value -> UNKNOWN_PHASE
```

Điểm cần hiểu: sự kiện **`PAUSED` là một trạng thái hợp lệ mới**, nhưng chương trình vô tình gộp nó với trạng thái “unknown”. Compiler không thể hỏi thêm bạn liệu `PAUSED` cần nhãn, thao tác hay quyền truy cập riêng, bởi `default` đã chặn tín hiệu thiếu case.

**Sửa đúng khi yêu cầu mới xuất hiện:** thêm nhánh `case PAUSED -> "PAUSE";` vào `switch` không có `default`; sửa test expected; biên dịch lại. Đó là công việc triển khai domain chứ không phải “sửa compiler cho chạy”.

## 8. Thực nghiệm compiler: thêm permitted subtype của sealed type

Tạo tệp **`SealedNoDefaultAfterChange.java`**:

```java
public class SealedNoDefaultAfterChange {
    sealed interface Event permits Started, Stopped, Failed {}
    record Started() implements Event {}
    record Stopped() implements Event {}
    record Failed() implements Event {}

    static String classify(Event value) {
        return switch (value) {
            case Started s -> "STARTED";
            case Stopped s -> "STOPPED";
        };
    }
}
```

Ở đây có ba subtype được phép nhưng `switch expression` chỉ xử lý hai subtype. Biên dịch:

```bash
javac --release 21 SealedNoDefaultAfterChange.java
```

**Kết quả:** `javac` từ chối do `switch expression` không bao phủ trường hợp `Failed` còn lại.

Phiên bản thêm `default`:

```java
public class SealedWithDefaultAfterChange {
    sealed interface Event permits Started, Stopped, Failed {}
    record Started() implements Event {}
    record Stopped() implements Event {}
    record Failed() implements Event {}

    static String classify(Event value) {
        return switch (value) {
            case Started s -> "STARTED";
            case Stopped s -> "STOPPED";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("new subtype -> " + classify(new Failed()));
    }
}
```

Chạy:

```bash
javac --release 21 SealedWithDefaultAfterChange.java
java SealedWithDefaultAfterChange
```

**Stdout:**

```text
new subtype -> OTHER
```

Đây là cùng một vấn đề với `enum`, chỉ khác kiểu domain là một phân cấp class/interface đóng. Khi phát triển sealed model, `switch` không có `default` là công cụ giúp người bảo trì thấy những nơi cần cập nhật theo biến thể mới.

Nếu thực sự có chính sách “mọi subtype còn lại đều xử lý chung”, nên diễn đạt **tường minh lý do** trong code review hoặc phương thức domain, không thêm `default` chỉ để né compiler.

## 9. `default` không phải kẻ xấu: khi nào nên dùng?

Một nhánh mặc định là hợp lý nếu **tập giá trị đầu vào được thiết kế mở** hoặc bạn có một chính sách fallback được định nghĩa rõ:

### 9.1. Selector là `Object` với nhiều kiểu ngoài domain

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case String s -> "text:" + s.length();
        case Number n -> "number:" + n;
        default -> "unsupported type";
    };
}
```

Đây là **phương thức minh họa**, không nằm trong chương trình của mục 6. Ở đây `Object` có vô số subtype; mục tiêu không phải xử lý exhaustive từng subtype. `default` có ngữ nghĩa hợp lệ: trả nhãn chung cho mọi kiểu khác.

### 9.2. Nghiệp vụ cố tình gom mọi trạng thái còn lại

Giả sử quy tắc chỉ cần phân biệt `DONE` với **mọi** trạng thái chưa xong; khi đó:

```java
boolean finished = switch (phase) {
    case DONE -> true;
    default -> false;
};
```

có thể là lựa chọn đúng **nếu yêu cầu thật sự định nghĩa trạng thái mới cũng mặc nhiên “chưa xong”**. Nhưng thường đơn giản và rõ hơn là:

```java
boolean finished = phase == Phase.DONE;
```

Biểu thức boolean sau còn tự xử lý `null` bằng `false` theo so sánh tham chiếu, còn `switch` phía trên (không có `case null`) có thể ném `NullPointerException` với `phase == null`. Vì vậy **đừng gọi chúng là tương đương nếu input nullable**.

### 9.3. Fallback là một phần của hợp đồng, không phải “che lỗi”

Trong hệ thống xử lý input từ bên ngoài, có thể có danh mục giá trị rộng hơn những kiểu/nhãn được ứng dụng hỗ trợ. Một fallback có tên như `UNSUPPORTED` hoặc ném exception được thiết kế có chủ đích là hợp lý.

Tuy nhiên, với domain **đóng và được ứng dụng sở hữu**, hãy cân nhắc để compiler làm việc thay mình. Nếu muốn unknown-type behavior, cũng nên nghĩ tới logging, metrics và kiểm thử để không âm thầm bỏ qua tình huống quan trọng.

### 9.4. Throw trong `default` vẫn che compile-time obligation

```java
default -> throw new IllegalStateException("Unexpected variant");
```

nhìn có vẻ “an toàn hơn” vì không âm thầm trả `OTHER`, nhưng **vẫn làm switch exhaustive ở compile time**. Khi thêm subtype/hằng số mới, compiler không bắt buộc bạn thêm case tường minh; lỗi chỉ nổi lên lúc đường đi runtime đó được chạy. Với sealed hierarchy hoặc enum mà bạn sở hữu, bỏ `default` thường phát hiện thiếu nhánh sớm hơn.

## 10. Guard `when` không tự bảo đảm exhaustiveness

Xét một `sealed interface` chỉ có subtype `Success` và `Failure`:

```java
sealed interface Result permits Success, Failure {}
record Success(int code) implements Result {}
record Failure(String reason) implements Result {}
```

Nếu chỉ có:

```java
case Success(var code) when code >= 200 -> "GOOD";
case Failure f -> "FAILED";
```

thì `Success` với `code < 200` chưa có nhánh xử lý. Đừng dùng `default -> "OTHER"` chỉ để tắt lỗi nếu còn cần quyết định riêng cho trường hợp đó.

Cách diễn đạt có ý nghĩa hơn:

```java
return switch (result) {
    case Success(var code) when code >= 200 -> "GOOD";
    case Success s -> "SUCCESS_OTHER";
    case Failure f -> "FAILED";
};
```

Đây là **các đoạn minh họa** dùng trong phương thức có `Result result` và không yêu cầu xử lý null. Thứ tự quan trọng: nhánh `Success` có guard đứng trước nhánh tổng quát. Nếu đảo lại, nhánh có guard bị bao phủ (*dominated*) và có thể lỗi compile time.

Không nên xem guard `when` là lời hứa rằng mọi giá trị `Success` đều thỏa nó. Compiler phải tính đến phần không thỏa guard trừ những trường hợp được ngôn ngữ xác định tường minh.

## 11. `switch expression` và `switch statement` có giống nhau không?

**Không hoàn toàn.** Những ví dụ chính ở trên đều là **`switch expression`**: `return switch (...) { ... };`. `switch expression` phải exhaustive.

Với `switch statement` kiểu truyền thống chỉ dùng constants của `enum`, Java đã từng cho phép viết thiếu case mà không cần `default`:

```java
switch (phase) {
    case DONE:
        System.out.println("Completed");
        break;
}
```

Vì đây chỉ là statement, khi `phase` là một hằng số khác `DONE`, chương trình có thể không thực thi nhánh nào. Điều này **không đảm bảo exhaustive checking giống switch expression**.

Trong Java 21, có thêm khái niệm **enhanced switch statement**, bao gồm các trường hợp sử dụng pattern hoặc selector kiểu khác với nhóm legacy switch. Enhanced switch statement có các yêu cầu exhaustiveness tương ứng. Vì vậy không nên phát biểu đơn giản “mọi switch không có default đều bị compiler bắt xử lý hết enum”.

**Khuyến nghị thực hành:** nếu một quyết định domain phải trả về một giá trị cho từng biến thể, dùng **switch expression** với các case tường minh là cách trực quan để nhận lợi ích kiểm tra exhaustiveness. Nếu đang refactor switch statement legacy, hiểu chính xác dạng switch trước khi dựa vào compiler.

## 12. Các giới hạn cần hiểu khi dựa vào exhaustive check

### 12.1. Compile time không thay thế kiểm thử runtime

Các class có thể được biên dịch riêng, thư viện có thể thay đổi mà binary phụ thuộc chưa được build lại. Một `switch` exhaustive khi compile với một tập biến thể không tự động chứng minh chạy an toàn với mọi tổ hợp phiên bản ở runtime. Khi cập nhật dependency/module, cần biên dịch lại và chạy regression tests.

### 12.2. Sealed type có generic và phân cấp phức tạp

Compiler xét **kiểu selector, các permitted subtypes và ràng buộc generic**, không đơn giản luôn đếm số class bằng tay. Một số parameterizations của sealed generic hierarchy khiến chỉ một phần permitted subtype thực sự khả dĩ. Hãy dựa vào `javac` và định nghĩa JLS thay vì áp dụng quy tắc đếm nhánh máy móc.

### 12.3. Null là một vấn đề riêng

`switch` có thể exhaustive đối với tất cả các giá trị khác null của enum/sealed type nhưng vẫn ném `NullPointerException` nếu selector null mà không có `case null`. Đừng “thêm default” rồi tưởng đã xử lý null.

### 12.4. Tên nhánh và thứ tự vẫn là trách nhiệm của người viết

Compiler có thể chứng minh đủ trường hợp, nhưng không chứng minh `case FAILED -> "OK"` là đúng nghiệp vụ. Exhaustiveness là một lớp bảo vệ, không phải thay thế test và code review.

## 13. Checklist code review: có nên cho phép default?

| Câu hỏi | Nếu câu trả lời là “có” |
|---|---|
| Selector là `enum` do team sở hữu? | Nên cân nhắc liệt kê đủ constants, bỏ `default` trong `switch expression` |
| Selector là `sealed interface/class`? | Nên liệt kê rõ những subtypes cần phân biệt |
| Thêm variant mới có cần quyết định nghiệp vụ? | **Đừng che sự kiện đó bằng `default` chung** |
| Có một fallback hợp đồng áp dụng với mọi giá trị tương lai? | `default` có thể hợp lý, nhưng cần giải thích/test |
| Selector có thể null? | Xác định cần `case null`, precondition non-null hay chấp nhận exception |
| Nhánh có guard `when`? | Đảm bảo giá trị **không thỏa guard** cũng được bao phủ đúng |
| Code là statement truyền thống hay switch expression? | Kiểm tra đúng yêu cầu exhaustiveness của dạng switch đó |
| Có nhiều jar/module phiên bản khác nhau? | Biên dịch lại và chạy integration/regression tests |
| `default` đang `throw`? | Nhớ rằng compiler vẫn không buộc thêm case mới; cân nhắc bỏ nó |
| Dữ liệu là tập kiểu mở (như `Object`)? | `default` thường chính đáng và có ý nghĩa |

### Quy trình refactor an toàn

1. Xác định **tập biến thể đóng hay mở** của selector.
2. Xác định hợp đồng nghiệp vụ: biến thể mới phải được xử lý riêng hay gộp chung?
3. Nếu đóng và cần xử lý riêng, **bỏ `default` trong `switch expression`** và liệt kê đầy đủ case.
4. Thêm `case null` nếu yêu cầu xử lý null theo một nhánh riêng.
5. Dùng `javac --release 21` xác nhận compiler chấp nhận bộ case hiện tại.
6. Viết regression tests cho từng enum constant/sealed subtype và các guard/boundary.
7. Thử thêm một variant mới trong nhánh thử nghiệm để xác nhận compiler buộc cập nhật nơi xử lý — đây là phép kiểm chứng thiết kế rất hiệu quả.
8. Chỉ giữ `default` nếu nó có **chính sách có tên và kiểm chứng được**, không phải để “xóa lỗi compiler”.

## 14. Câu hỏi tự kiểm tra

**1. Vì sao `default` là rủi ro trong `switch` trên enum có ba giá trị?**

Vì khi có giá trị thứ tư, chương trình có thể tiếp tục biên dịch và đưa giá trị mới vào nhánh chung, trong khi nghiệp vụ cần xem xét riêng.

**2. Bỏ `default` có luôn làm mọi `switch statement` thiếu case bị compiler từ chối không?**

Không. Cần phân biệt traditional switch statement với switch expression/enhanced switch statement; bài này dựa chủ yếu vào exhaustiveness của **switch expression**.

**3. Trong sealed hierarchy, `default -> throw ...` có giữ được khả năng buộc cập nhật khi thêm subtype mới không?**

Không. Nó có thể cho lỗi runtime khi gặp subtype mới, nhưng vẫn là nhánh bao phủ phần còn lại ở compile time.

**4. Nếu có `case Started s when s.service() != null`, compiler có coi đó là bao phủ mọi `Started` không?**

Không. Vẫn còn `Started` có service null cần nhánh phù hợp nếu muốn exhaustive.

**5. `default -> "OTHER"` có bắt null selector không?**

Không trong các pattern switch Java 21 minh họa ở bài. Muốn xử lý null theo hợp đồng, dùng `case null` hoặc kiểm tra trước.

**6. Khi nào `default` hữu ích?**

Khi đầu vào là tập kiểu mở, hoặc yêu cầu rõ ràng rằng **mọi** biến thể còn lại và tương lai đều đi qua cùng chính sách fallback.

**7. “Compiler chấp nhận” có đồng nghĩa “logic đúng” không?**

Không. Compiler bảo đảm các quy tắc kiểu và exhaustiveness theo ngôn ngữ, không kiểm tra ý nghĩa của nhãn kết quả hoặc tác dụng phụ của từng case.

## Kết luận

Với `enum` và `sealed` domain do bạn kiểm soát, **đừng thêm `default` theo thói quen**. Một `switch expression` liệt kê các biến thể tường minh cho phép compiler cảnh báo khi domain mở rộng, biến thay đổi kiểu dữ liệu thành yêu cầu xem lại code. `default` có chỗ đứng khi fallback thực sự là một phần của hợp đồng, nhất là với đầu vào mở; nhưng dùng nó để lấp chỗ trống sẽ làm mất một lợi ích lớn của pattern matching: **exhaustive check tại compile time**.

Luôn phân biệt **exhaustiveness của non-null variants**, **xử lý `null`**, và **đúng logic nghiệp vụ** — đó là ba câu hỏi khác nhau.

## Tài liệu tham khảo

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JLS Java SE 21 — Switch Statements §14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS Java SE 21 — Switch Expressions §15.28](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [JLS Java SE 21 — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
