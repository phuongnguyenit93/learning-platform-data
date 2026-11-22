# Xử lý enum chưa biết ở default trong Java

## 1. “Enum chưa biết” thật sự là trường hợp nào?

Khi viết `switch` trên một kiểu `enum`, người học thường dùng `case` cho những trạng thái được hệ thống xử lý trực tiếp và `default` cho trạng thái chưa có nhánh riêng. Điều này có vẻ đơn giản, nhưng câu “enum chưa biết” có ít nhất **ba ý nghĩa khác nhau**:

1. **Giá trị là một enum constant hợp lệ nhưng chưa được liệt kê trong `case`.** Ví dụ `Status.ON_HOLD` đã được khai báo trong enum nhưng `switch` chỉ có `NEW`, `RUNNING` và `DONE`. Với `default` tường minh, `ON_HOLD` sẽ đi vào `default`.
2. **Tên constant mới được thêm vào phiên bản thư viện/enum về sau.** Một bản mã đã biên dịch với danh sách cũ có thể gặp constant được bổ sung ở runtime. `default` tường minh có thể cung cấp hành vi dự phòng, nhưng đồng thời làm giảm khả năng compiler buộc tác giả rà soát mọi trạng thái mới khi biên dịch lại.
3. **Dữ liệu bên ngoài là chuỗi không tồn tại trong enum.** Ví dụ API trả `"FUTURE"` nhưng enum Java chỉ có `NEW, RUNNING, DONE, ON_HOLD`. `Enum.valueOf(Status.class, "FUTURE")` ném `IllegalArgumentException`. **Không có đối tượng `Status` tương ứng để đưa vào `switch`, vì vậy `default` của switch không thể tự bắt lỗi parse này.**

Ngoài ra, `null` cũng **không phải một enum constant** và cần được xử lý theo quy tắc riêng; `default` không phải cách thay thế tự động cho `null`.

Bài này tập trung vào **thiết kế `default` khi xử lý enum**, đồng thời giải thích cách phân biệt “constant chưa có case”, “chuỗi không parse được” và “null”. Mục đích là vừa viết mã đúng cú pháp, vừa tránh che giấu trạng thái nghiệp vụ mới.

### Sơ đồ quyết định

```text
Dữ liệu đầu vào
   |
   +-- Đã là Status? -- Có --> status == null?
   |                                |
   |                          Có --> xử lý null
   |                          Không
   |                                |
   |                                v
   |                         switch(status)
   |                           |-- khớp case --> xử lý riêng
   |                           +-- không khớp --> default (nếu có)
   |
   +-- Là chuỗi từ API?
           |
           +-- null/rỗng --> xử lý thiếu dữ liệu
           |
           +-- parse được bằng valueOf --> Status --> switch
           |
           +-- parse thất bại --> xử lý chuỗi không hợp lệ
```

Sơ đồ là mô tả luồng xử lý, không phải cú pháp Java.

## 2. Cơ chế enum và case label

Giả sử trạng thái xử lý đơn hàng:

```java
enum Status {
    NEW,
    RUNNING,
    DONE,
    ON_HOLD
}
```

`Status` là một lớp enum Java; mỗi tên trong thân enum đại diện cho một **enum constant**. Các constant có danh tính cố định theo tên khai báo. Với selector có kiểu `Status`, nhãn case có thể viết bằng tên constant đơn giản:

```java
static String display(Status status) {
    return switch (status) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
        default -> "unhandled:" + status.name();
    };
}
```

Đây là **phương thức minh họa** cần đặt trong một lớp có thể truy cập enum `Status`. `case NEW`, `case RUNNING`, `case DONE` khớp các constant tương ứng. `ON_HOLD` không khớp ba case ấy, nên khi gọi `display(Status.ON_HOLD)`, kết quả là `"unhandled:ON_HOLD"`.

Điểm cốt lõi: `default` không tạo một enum constant “unknown” mới; nó chỉ là **nhánh dự phòng** khi quá trình chọn nhãn case không có nhãn cụ thể khớp giá trị không-null đã cho.

### Default có thay thế được danh sách constant không?

Không. Giả sử người viết thực sự muốn xử lý `ON_HOLD` như trạng thái tạm dừng, việc trả `"unhandled:ON_HOLD"` chỉ là một *fallback*. Nó không chứa hành vi “tạm dừng đơn hàng” chuyên biệt. Tách hai chuyện:

- **Hợp lệ về cú pháp:** `default` giúp `switch expression` có nhánh dự phòng.
- **Đúng về nghiệp vụ:** `default` phải trả một kết quả an toàn hoặc từ chối rõ ràng; không nên âm thầm giả làm một trạng thái được xử lý đầy đủ.

Đặt `default` ở cuối thường giúp người đọc nhận ra chính sách xử lý phần còn lại. Khi dùng nhánh `->`, các case không tự rơi xuyên sang case tiếp theo.

## 3. Khi nào switch expression bắt buộc có default?

`switch expression` phải **exhaustive**: mọi giá trị hợp lệ của selector đều cần một nhánh tạo kết quả hoặc ném ngoại lệ. Với một enum, Java có thể chứng minh tính đầy đủ khi **tất cả enum constants hiện biết đều có case**, vì tập tên constant là hữu hạn tại thời điểm biên dịch.

### Trường hợp A — Chưa liệt kê hết constant: cần fallback

Với `Status` có bốn constants, ba case sau không bao quát `ON_HOLD`:

```java
// CỐ Ý SAI về tính đầy đủ của switch expression Java 17+:
static String incomplete(Status status) {
    return switch (status) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
    };
}
```

Compiler báo biểu thức `switch` không bao quát hết các giá trị. Có hai cách sửa hợp lệ: thêm `case ON_HOLD` với hành vi riêng, hoặc thêm `default` với một hành vi dự phòng có chủ đích.

### Trường hợp B — Đủ toàn bộ constant: không bắt buộc default

```java
static String exhaustive(Status status) {
    return switch (status) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
        case ON_HOLD -> "on hold";
    };
}
```

Đây là phương thức minh họa. Java chấp nhận `switch expression` không có `default` vì nó bao gồm bốn enum constants hiện có. Ưu điểm:

- Khi enum được bổ sung constant mới và mã `switch` được **biên dịch lại** với định nghĩa enum mới, compiler có thể báo thiếu case, nhắc lập trình viên quyết định ý nghĩa nghiệp vụ.
- Mọi constant hiện tại có cách xử lý riêng, dễ kiểm thử theo từng case.

Điểm đánh đổi: nếu runtime dùng một enum đã được mở rộng nhưng bản mã chứa `switch` **chưa được biên dịch lại**, có thể có một constant không được nhãn nào xử lý. Theo quy tắc `switch expression` trong **Java 21**, tình huống không có nhãn áp dụng cho giá trị không-null sẽ ném `MatchException`. Không nên dựa vào một “default ẩn” để tự động trả giá trị nghiệp vụ. Với các phiên bản Java khác, chi tiết lỗi khi thay đổi enum không đồng bộ có thể khác; bài này căn cứ Java 21.

### Trường hợp C — Đủ tất cả case và vẫn viết default

```java
static String defensive(Status status) {
    return switch (status) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
        case ON_HOLD -> "on hold";
        default -> "unrecognized";
    };
}
```

Mã này hợp lệ. `default` hiện không được chọn cho bốn giá trị đã khai báo, nhưng là nhánh dự phòng nếu môi trường nhị phân mang đến một constant mới chưa có case.

**Đánh đổi:** Sau này, nếu thêm `CANCELLED` và biên dịch lại, compiler không buộc bổ sung `case CANCELLED` bởi `default` đã bao quát. Vì thế, với hành vi phải được xem xét khi thêm enum constant, **không có `default` thường có ích hơn**.

## 4. Ví dụ chạy đầy đủ Java 17: default và chuỗi ngoài enum

Tạo file `EnumDefault17.java`:

```java
import java.util.Locale;

public class EnumDefault17 {

    enum Status {
        NEW,
        RUNNING,
        DONE,
        ON_HOLD
    }

    static String display(Status status) {
        if (status == null) {
            return "missing";
        }

        return switch (status) {
            case NEW -> "new";
            case RUNNING -> "running";
            case DONE -> "done";
            default -> "unhandled:" + status.name();
        };
    }

    static String fromWire(String token) {
        if (token == null || token.isBlank()) {
            return "missing-token";
        }

        try {
            Status parsed =
                    Status.valueOf(token.strip().toUpperCase(Locale.ROOT));
            return display(parsed);
        } catch (IllegalArgumentException badToken) {
            return "invalid-token:" + token;
        }
    }

    public static void main(String[] args) {
        System.out.println(display(Status.NEW));
        System.out.println(display(Status.ON_HOLD));
        System.out.println(display(null));
        System.out.println(fromWire(" done "));
        System.out.println(fromWire("FUTURE"));
        System.out.println(fromWire(null));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 EnumDefault17.java
java EnumDefault17
```

Kết quả chính xác:

```text
new
unhandled:ON_HOLD
missing
done
invalid-token:FUTURE
missing-token
```

**Đọc kết quả thật kỹ:**

1. `Status.NEW` khớp case cụ thể và cho `new`.
2. `Status.ON_HOLD` **là enum constant hợp lệ**, nhưng chưa có case cụ thể nên đi vào `default`, trả `unhandled:ON_HOLD`.
3. `null` được xử lý **trước khi switch** bằng tiền kiểm, trả `missing`.
4. Chuỗi `" done "` được `strip()`, chuyển sang chữ hoa với `Locale.ROOT` rồi parse thành `Status.DONE`. Sau đó case `DONE` cho kết quả `done`.
5. Chuỗi `"FUTURE"` **không phải tên constant** trong `Status`. `valueOf` ném `IllegalArgumentException`; `catch` trả `invalid-token:FUTURE`. `switch` không chạy, nên `default` cũng không chạy.
6. `null` từ nguồn chuỗi được coi là thiếu token và trả `missing-token`, không phải lỗi parse hoặc enum chưa có case.

`Locale.ROOT` giúp chuẩn hóa cách viết không phụ thuộc locale người dùng; việc chuyển chữ thường sang hoa chỉ là **chính sách parse của ví dụ**, không phải hành vi mặc định của `Enum.valueOf`. Mặc định, `valueOf` yêu cầu **tên khớp chính xác** và có phân biệt chữ hoa/chữ thường.

**Lưu ý thực tế:** Ví dụ trả lại token thô trong thông điệp lỗi để thấy đường đi. Trong dịch vụ thật, tránh đưa nguyên văn dữ liệu không tin cậy vào log hoặc thông báo mà không giới hạn độ dài, làm sạch hoặc cấu trúc hóa theo quy ước của hệ thống.

## 5. Default không bắt được lỗi Enum.valueOf

Đây là lỗi thiết kế rất phổ biến:

```java
// SAI nếu kỳ vọng default bắt được chuỗi "UNKNOWN":
static String parseWrong(String raw) {
    Status status = Status.valueOf(raw);
    return switch (status) {
        case NEW -> "new";
        default -> "fallback";
    };
}
```

Đoạn này là **phương thức minh họa**. Với `parseWrong("UNKNOWN")` và `Status` không có constant tên `UNKNOWN`, lời gọi `valueOf` ném `IllegalArgumentException` **trước** khi chạy `switch`. Với `parseWrong(null)`, lời gọi `valueOf` ném `NullPointerException` nếu không được tiền kiểm.

Giải pháp là xác định rõ **hai ranh giới**:

- **Ranh giới bên ngoài → enum:** dữ liệu từ JSON, database, query parameter, Kafka message... có thể chứa tên lạ, sai chữ hoa/thường, khoảng trắng hoặc null. Parse và xử lý lỗi dữ liệu **tại đây**.
- **Ranh giới enum → hành vi:** sau khi parse thành một constant hợp lệ, `switch` xử lý các constant đã biết, và `default` xử lý constant chưa được liệt kê trong các case.

Một lựa chọn API sạch hơn là cho tầng parse trả kết quả có cấu trúc, ví dụ một kiểu kết quả gồm `Parsed(Status)` và `Invalid(raw)`, thay vì gộp lỗi parse với một enum constant dự phòng.

### Không dùng valueOf để “tự tạo constant mới”

Enum Java có tập constants được khai báo trong mã/bytecode enum. `valueOf` chỉ **tra cứu** constant đã tồn tại; nó không tạo constant khi gặp chuỗi mới. Không thể dùng `default` để tự thêm biến thể mới vào enum.

Nếu yêu cầu nghiệp vụ cần lưu trữ hoặc hiển thị mã trạng thái từ đối tác chưa được phần mềm hiện tại hiểu, hãy **giữ lại chuỗi gốc** trong một kiểu dữ liệu kết quả hoặc trường riêng, thay vì kỳ vọng enum có thể chứa giá trị tùy ý.

## 6. Enum.UNKNOWN là constant bình thường, không phải default

Một thiết kế đôi khi khai báo:

```java
enum Status {
    NEW,
    RUNNING,
    DONE,
    UNKNOWN
}
```

Ở đây `UNKNOWN` **là một enum constant thật**. Vì vậy:

```java
static String explain(Status status) {
    return switch (status) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
        case UNKNOWN -> "explicitly unknown";
    };
}
```

`case UNKNOWN` khác về ý nghĩa với `default`:

| Tình huống | `case UNKNOWN` | `default` |
| --- | --- | --- |
| Selector là constant `Status.UNKNOWN` | Khớp | Chỉ tới default nếu không có case cụ thể khớp |
| Selector là `Status.NEW` | Không | Có thể tới default nếu NEW không có case |
| Chuỗi ngoài enum `"FUTURE"` gặp `valueOf` | Không, vì parse chưa tạo Status | Không, vì switch chưa chạy |
| Enum bổ sung `PAUSED` | Không | Có thể nhận nếu mã switch có default tường minh và chưa có case PAUSED |

Nếu muốn mọi tên chuỗi không nhận diện được đều biến thành `Status.UNKNOWN`, phải **viết chính sách parse riêng** để thực hiện ánh xạ đó. Khi làm thế, cân nhắc việc **mất tên chuỗi gốc**, gây khó chẩn đoán hoặc làm mất khả năng xử lý khi phiên bản sau hỗ trợ trạng thái mới.

Ví dụ một hàm parse với fallback thành `UNKNOWN` là quyết định **của ứng dụng**, không phải quy tắc mặc định của Java:

```java
static Status parseWithUnknown(String raw) {
    if (raw == null || raw.isBlank()) {
        return Status.UNKNOWN;
    }

    try {
        return Status.valueOf(raw.strip().toUpperCase(java.util.Locale.ROOT));
    } catch (IllegalArgumentException ignored) {
        return Status.UNKNOWN;
    }
}
```

Đây là **phương thức minh họa** giả định `Status` có constant `UNKNOWN`. Khi cần phân biệt `null`, chuỗi rỗng, tên lạ, nên dùng kiểu kết quả phong phú hơn thay vì gom hết thành `UNKNOWN`.

## 7. Java 21: case null tường minh, default cho enum còn lại

Trong Java 17, một selector enum bằng `null` sẽ gây `NullPointerException` trong `switch` nếu không có tiền kiểm. `default` không ngăn việc này. Java 21 bổ sung khả năng viết `case null` trong switch trên kiểu tham chiếu, gồm enum.

Tạo file `EnumDefault21.java`:

```java
public class EnumDefault21 {

    enum State {
        READY,
        RUNNING,
        FINISHED,
        WAITING
    }

    static String render(State state) {
        return switch (state) {
            case null -> "missing";
            case READY -> "ready";
            case RUNNING -> "running";
            case FINISHED -> "finished";
            default -> "unmapped:" + state.name();
        };
    }

    static String describe(Object value) {
        return switch (value) {
            case null -> "input-null";
            case State state -> render(state);
            case String raw -> "raw:" + raw;
            default -> "unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe(State.READY));
        System.out.println(describe(State.WAITING));
        System.out.println(describe("FUTURE"));
        System.out.println(describe(42));
    }
}
```

Biên dịch/chạy bằng JDK 21 trở lên:

```bash
javac -encoding UTF-8 --release 21 EnumDefault21.java
java EnumDefault21
```

Kết quả chính xác:

```text
input-null
ready
unmapped:WAITING
raw:FUTURE
unsupported
```

### Hai lớp switch có vai trò khác nhau

- `describe(Object value)` dùng **type pattern** `case State state` để nhận đúng đối tượng enum và `case String raw` để nhận chuỗi. Vì selector là `Object`, `default` của **switch ngoài** xử lý đối tượng kiểu khác, ví dụ `Integer`.
- `render(State state)` dùng các **enum constant case** `READY`, `RUNNING`, `FINISHED`. `State.WAITING` không nằm trong các case cụ thể nên được **default của switch trong** xử lý.
- `describe("FUTURE")` không gọi `Enum.valueOf`, vì chương trình này minh họa phân loại kiểu đầu vào. Nó trả `raw:FUTURE`, không có nghĩa chuỗi đã biến thành `State`.
- `case null` của switch ngoài phân biệt đầu vào `null` với `default`; trong `render` còn có `case null` phòng khi phương thức được gọi trực tiếp với null.

Ví dụ cho thấy **default của switch trên Object và default của switch trên enum có trách nhiệm khác nhau**. Đừng gom “loại Java không hỗ trợ”, “enum constant chưa xử lý”, “chuỗi bên ngoài sai tên” và “null” vào cùng một giá trị lỗi nếu nghiệp vụ cần phân biệt.

### Có thể gộp case null, default không?

Java 21 hỗ trợ `case null, default -> ...` khi thật sự muốn gộp hai trường hợp. Tuy nhiên, với chủ đề này, thường **không nên** gộp, vì `null` có thể nghĩa là thiếu dữ liệu còn `default` của enum là constant hợp lệ chưa được xử lý. Sự phân biệt đó rất hữu ích trong kiểm thử và chẩn đoán.

## 8. Java 17: switch statement có thể âm thầm bỏ qua constant chưa có case

Không phải mọi `switch` có cùng yêu cầu đầy đủ. Ví dụ `switch statement` truyền thống trên enum:

```java
enum State { NEW, DONE, ON_HOLD }

static void printState(State state) {
    switch (state) {
        case NEW -> System.out.println("new");
        case DONE -> System.out.println("done");
    }
}
```

Đây là **mảnh mã minh họa**. Nếu gọi `printState(State.ON_HOLD)`, không có nhánh áp dụng, nên phương thức hoàn thành **mà không in gì**. Trong Java 21, một switch statement theo kiểu truyền thống (không dùng pattern/null label) vẫn có thể không exhaustive để giữ tương thích nguồn.

Điều này khác với `switch expression`, nơi phải có kết quả cho mọi đầu vào hợp lệ. Đây cũng khác với *enhanced switch statement* Java 21 có pattern hoặc nhãn `null`, vì loại enhanced switch statement chịu quy tắc exhaustiveness.

Khi viết switch statement trên enum có tác vụ quan trọng, nên chọn một trong hai hướng rõ ràng:

```java
switch (state) {
    case NEW -> startNew();
    case DONE -> finish();
    default -> handleUnhandled(state);
}
```

Đây là **mảnh mã minh họa**: ba phương thức `startNew`, `finish` và `handleUnhandled` phải được định nghĩa. Nếu thiếu `default`, không nên giả định rằng Java sẽ báo compile-time error cho mọi constant chưa liệt kê trong switch statement truyền thống.

Với ngữ cảnh tính toán một kết quả, `switch expression` thường giúp tránh tình trạng quên gán giá trị do thiếu nhánh.

## 9. Chọn chính sách cho default: fallback, fail-fast hay fail-closed?

`default` không bắt buộc phải trả một chuỗi `"UNKNOWN"`. Nó là nơi thể hiện **hợp đồng** khi gặp enum constant chưa có nhánh riêng.

### 9.1. Fallback hiển thị: an toàn với dữ liệu có thể mở rộng

Giả sử một ứng dụng chỉ cần hiển thị nhãn cho trạng thái và có thể chấp nhận tên raw của constant:

```java
static String label(Status status) {
    if (status == null) return "No status";
    return switch (status) {
        case NEW -> "New";
        case RUNNING -> "In progress";
        case DONE -> "Completed";
        default -> "Other (" + status.name() + ")";
    };
}
```

Đây là **phương thức minh họa** với enum `Status` ở phần trước. Lợi ích: giao diện không bị gián đoạn khi có constant mới. Hạn chế: người dùng có thể thấy một nhãn chung chưa dịch hoặc chưa đúng nghiệp vụ. Đối với hệ thống có logging/metrics, có thể ghi nhận constant mới để lên kế hoạch bổ sung case.

### 9.2. Fail-fast: trạng thái chưa định nghĩa hành vi là lỗi

Trong nghiệp vụ tài chính, kiểm soát truy cập hoặc trạng thái máy, việc im lặng trả thành công giả có thể nguy hiểm. Có thể viết:

```java
static String transition(Status status) {
    java.util.Objects.requireNonNull(status, "status");

    return switch (status) {
        case NEW -> "start";
        case RUNNING -> "continue";
        case DONE -> "stop";
        default -> throw new IllegalStateException(
                "Unhandled status: " + status.name());
    };
}
```

Đây là **phương thức minh họa**. Với `ON_HOLD`, exception được ném có chủ đích. Cách này biến constant chưa xử lý thành tín hiệu lỗi rõ, tránh giả vờ áp dụng một chuyển trạng thái không phù hợp.

Tuy nhiên, khi `default` có mặt, **sau khi thêm enum constant mới và biên dịch lại**, compiler không còn bắt buộc thêm case mới. Nếu mục tiêu là phát hiện chính xác tất cả biến thể trong quá trình biên dịch, hãy cân nhắc **bỏ default và liệt kê hết constant**, đồng thời kiểm thử việc cập nhật enum.

### 9.3. Fail-closed: mặc định từ chối trong phân quyền

Nếu enum biểu diễn vai trò:

```java
enum Role { ADMIN, USER, GUEST, UNKNOWN }

static boolean mayDelete(Role role) {
    if (role == null) {
        return false;
    }

    return switch (role) {
        case ADMIN -> true;
        case USER, GUEST -> false;
        default -> false;
    };
}
```

Đây là **mảnh code minh họa**. Constant `UNKNOWN` rơi vào `default` và trả `false`. Một vai trò được bổ sung sau này cũng không được tự động cấp quyền xóa nếu chưa có case cho phép. Đây là nguyên tắc **fail-closed**: không cho quyền chỉ vì nhánh mới hoặc chưa nhận diện.

Thiết kế thực tế vẫn cần logging/audit thích hợp và bộ kiểm thử, vì default từ chối không thay thế toàn bộ mô hình phân quyền. Thận trọng nếu chọn default trả `true` cho bất kỳ quyền nhạy cảm nào.

### 9.4. Log và đo lường constant chưa hỗ trợ

Khi `default` mang vai trò fallback, nên có cách quan sát:

```java
default -> {
    System.err.println("Unhandled state: " + status.name());
    yield "Other";
}
```

Đây là **mảnh nhánh Java 17+** trong `switch expression`; nếu dùng block nhiều lệnh thì `yield` trả kết quả cho expression. Trong hệ thống thật, thường dùng logger/metrics có giới hạn tần suất và không dùng dữ liệu không tin cậy làm nhãn metric có cardinality vô hạn.

Đừng biến một fallback quan sát được thành lỗi bị nuốt mà không ai phát hiện, nhất là khi trạng thái mới cần thay đổi quy trình xử lý.

## 10. Khi enum được mở rộng: những lựa chọn đánh đổi

Giả sử thư viện ban đầu có:

```java
enum Approval { REQUESTED, APPROVED }
```

Mã ứng dụng dùng `switch expression` với hai case, không có `default`:

```java
static String caption(Approval approval) {
    return switch (approval) {
        case REQUESTED -> "pending";
        case APPROVED -> "approved";
    };
}
```

Ở thời điểm biên dịch, đây là biểu thức exhaustive và hợp lệ. Về sau, thư viện thêm `REJECTED`. Hai tình huống cần phân biệt:

**Tình huống 1 — Biên dịch lại ứng dụng với enum mới.** Compiler có thể báo expression không exhaustive và yêu cầu quyết định cách xử lý `REJECTED`. Đây là **ưu điểm của việc không có default**: thay đổi mô hình buộc thay đổi code tương ứng.

**Tình huống 2 — Thay thư viện enum tại runtime nhưng giữ nguyên lớp ứng dụng đã biên dịch.** Nếu đối tượng `Approval.REJECTED` tới `caption` mà các nhãn cũ không áp dụng, Java 21 có thể ném `MatchException` theo quy tắc switch expression. Vì thế, quy trình nâng cấp thư viện nên **build lại và kiểm thử các module phụ thuộc**. Không coi binary compatibility của việc thêm enum constant là bằng chứng mọi đường đi xử lý đều có ý nghĩa.

Nếu biểu thức có `default -> "other"` từ đầu, nó có thể nhận `REJECTED` và tiếp tục. Cách này tăng tính chịu lỗi khi gặp biến thể mới, nhưng compiler không ép bổ sung case tường minh sau khi enum được mở rộng.

### Quy tắc chọn nhanh

| Mục đích | Default nên làm gì? | Đánh đổi |
| --- | --- | --- |
| Hiển thị không quan trọng, muốn tiếp tục hoạt động | Trả nhãn an toàn và ghi nhận constant mới | Có thể thiếu hành vi/ngôn ngữ chuyên biệt |
| State machine, nghiệp vụ quan trọng | `throw` có chủ đích hoặc xử lý lỗi nghiệp vụ | Có thể gián đoạn, nhưng tránh cập nhật trạng thái sai |
| Phân quyền | Từ chối mặc định (`false`/deny) | Cần audit để phân biệt lỗi cấu hình và vai trò mới |
| Muốn compiler bắt buộc xử lý khi enum thêm constant | Liệt kê đủ case, **không có default** | Cần biên dịch lại khi enum thay đổi; bản nhị phân cũ có thể lỗi nếu gặp constant mới |
| Dữ liệu chuỗi từ hệ thống ngoài | Parse riêng, trả kết quả lỗi hoặc giữ raw token | Không phải nhiệm vụ của switch default |

Không có lựa chọn mặc định đúng cho mọi dự án. Hãy viết **rõ hợp đồng** và kiểm tra ca bổ sung constant trong cả code review lẫn bộ kiểm thử.

## 11. Quan hệ với pattern matching trong Java 21

Enum có thể xuất hiện trong Java 21 theo hai cách khác nhau:

**Cách A — Selector là chính kiểu enum:** dùng các **constant labels** như `case NEW`, `case DONE`. Không cần type pattern để kiểm tra kiểu của chính selector đã là `Status`.

**Cách B — Selector là một kiểu rộng hơn như `Object`:** có thể dùng **type pattern** `case Status status` để ràng buộc đối tượng enum, rồi gọi một `switch` enum chuyên trách:

```java
static String process(Object input) {
    return switch (input) {
        case null -> "missing";
        case Status status -> display(status);
        case String raw -> "unparsed token: " + raw;
        default -> "wrong data type";
    };
}
```

Đây là phương thức minh họa **Java 21**, giả định đã định nghĩa `Status` và `display(Status)`. `case Status status` không tự phân loại từng constant; nó chỉ nhận đối tượng thuộc kiểu `Status`, sau đó `display` mới phân nhánh bằng các enum constants. Hai mức default có ý nghĩa riêng: “kiểu Java không hỗ trợ” và “constant chưa có cách xử lý riêng”.

Nếu muốn dùng `when` để lọc một tập con, có thể viết:

```java
case Status status when status == Status.ON_HOLD -> "on hold";
case Status status -> display(status);
```

Đây là các **nhãn trong switch(Object input)**, cần đặt nhánh guard trước nhánh `Status` tổng quát; nếu đảo ngược sẽ gặp lỗi **dominance**. Với selector đã là `Status`, dùng `case ON_HOLD` thường đơn giản hơn.

**Không nhầm lẫn:** `default` không phải type pattern, không khai báo biến và không mang giá trị enum chưa biết. Tên biến `status` của case pattern chỉ tồn tại trong guard/thân nhánh phù hợp.

## 12. Những lỗi thường gặp khi dùng default với enum

| Lỗi / giả định | Hậu quả | Cách sửa |
| --- | --- | --- |
| `default` sẽ bắt `valueOf("FUTURE")` | Lỗi parse xảy ra trước switch | Bắt `IllegalArgumentException` ở tầng parse |
| `default` tự nhận `null` | Với Java 17, switch enum null ném NPE; Java 21 cần `case null`/tiền kiểm | Tách null rõ ràng |
| Constant `UNKNOWN` là alias của default | `UNKNOWN` chỉ là một constant bình thường | Viết `case UNKNOWN` hoặc chính sách parse có chủ đích |
| Default luôn trả “success” | Có thể coi trạng thái chưa xử lý là thành công | Trả fallback an toàn, deny hoặc throw |
| Dùng `ordinal()` để suy ra tên/ID ổn định | Thêm hoặc đổi thứ tự constant làm thay đổi ordinal | Dùng tên hoặc mã nghiệp vụ tường minh |
| Dùng `toString()` như khóa parse mặc định | Enum có thể override `toString()` | Dùng `name()` cho tên khai báo hoặc ánh xạ wire code riêng |
| Muốn compiler phát hiện enum constant mới nhưng có default tổng quát | Biểu thức vẫn exhaustive, không nhắc xử lý riêng | Cân nhắc liệt kê đủ constant và bỏ default |
| Không có default trong switch statement truyền thống | Constant thiếu case có thể làm statement không thực hiện gì | Thêm xử lý dự phòng có chủ đích hoặc chuyển sang expression |
| Dùng `catch (Exception)` quanh toàn bộ logic | Che cả lỗi chương trình khác, khó chẩn đoán | Chỉ bắt lỗi parse dự kiến và ở đúng ranh giới |
| Log raw token không kiểm soát | Dễ spam, chứa ký tự điều khiển hoặc thông tin nhạy cảm | Giới hạn, làm sạch hoặc dùng log có cấu trúc |
| Dùng switch expression nhưng một nhánh block không `yield` | Lỗi biên dịch do thiếu giá trị | Dùng `yield` hoặc `throw` |
| Gộp enum constant mới với lỗi đầu vào chuỗi | Không phân biệt tiến hóa mô hình và dữ liệu sai | Kết quả có mã lỗi/kiểu kết quả riêng |

### Vì sao không so sánh ordinal?

Ví dụ:

```java
// Không nên dùng ordinal cho protocol / lưu trữ:
int code = Status.ON_HOLD.ordinal();
```

`ordinal()` trả vị trí khai báo (bắt đầu từ 0), không phải mã nghiệp vụ ổn định. Thêm constant vào giữa enum hoặc sắp xếp lại các tên có thể thay đổi số đó, khiến dữ liệu lưu cũ bị hiểu nhầm. Khi giao tiếp ngoài hệ thống, dùng một trường mã tường minh và bộ parse riêng nếu cần tương thích tiến hóa.

## 13. Kiểm thử default theo đúng tình huống

Với `EnumDefault17` ở phần 4, kiểm thử các trường hợp:

| Đầu vào | Nhánh hoặc giai đoạn | Kết quả |
| --- | --- | --- |
| `Status.NEW` | `case NEW` | `new` |
| `Status.RUNNING` | `case RUNNING` | `running` |
| `Status.DONE` | `case DONE` | `done` |
| `Status.ON_HOLD` | `default` (constant hợp lệ chưa có case) | `unhandled:ON_HOLD` |
| `null` truyền vào `display` | Tiền kiểm trước switch | `missing` |
| `" done "` truyền vào `fromWire` | Parse thành DONE, sau đó case | `done` |
| `"FUTURE"` truyền vào `fromWire` | `valueOf` ném IAE, catch | `invalid-token:FUTURE` |
| `null` truyền vào `fromWire` | Tiền kiểm token | `missing-token` |

Với `EnumDefault21`, cần bổ sung:

| Đầu vào | Đường đi | Kết quả |
| --- | --- | --- |
| `describe(null)` | `case null` của switch ngoài | `input-null` |
| `describe(State.READY)` | Type pattern State, rồi `case READY` | `ready` |
| `describe(State.WAITING)` | Type pattern State, rồi default enum | `unmapped:WAITING` |
| `describe("FUTURE")` | Type pattern String, không parse | `raw:FUTURE` |
| `describe(42)` | Default của switch(Object) | `unsupported` |

Ngoài đầu ra của hàm, kiểm thử **chính sách hành vi**:

1. Nếu fallback là fail-fast, xác nhận exception và thông điệp đúng với trạng thái chưa hỗ trợ.
2. Nếu fallback là fail-closed, xác nhận constant mới/không nhận diện được **không được cấp quyền**.
3. Nếu muốn compiler buộc xử lý mọi constant, thêm constant tạm thời, biên dịch lại và kiểm tra chỗ thiếu case.
4. Nếu ứng dụng nạp enum từ mô-đun khác, thực hiện build/test tích hợp khi cập nhật enum hoặc phiên bản thư viện.
5. Với parse dữ liệu ngoài, kiểm tra tên lạ, chuỗi rỗng, khoảng trắng, sai chữ hoa, null, tên hợp lệ và dữ liệu quá dài.

Không coi “có `default`, không ném lỗi” là bằng chứng QA đủ. **Đúng kết quả nghiệp vụ** mới quyết định fallback có phù hợp hay không.

## 14. Bài tập thực hành

**Bài 1 — Constant chưa xử lý:** Khai báo `enum Shipping { CREATED, PACKING, SHIPPED, RETURNED }`. Dùng `switch expression` xử lý ba trạng thái đầu, còn `RETURNED` vào `default` trả `"unhandled:RETURNED"`. Kiểm tra kết quả bằng cách chạy.

**Bài 2 — Tách parse khỏi switch:** Cho chuỗi `"delayed"` không có trong `Shipping`. Viết `parseShipping(String)` trả kết quả phân biệt `missing input` và `invalid token`. Giải thích vì sao default trong switch không thể bắt lỗi parse.

**Bài 3 — Exhaustiveness:** Viết `switch expression` đủ bốn `case` cho `Shipping`, không dùng `default`. Sau đó thêm `CANCELLED` vào enum, biên dịch lại và xử lý lỗi thiếu nhánh.

**Bài 4 — Chính sách nghiêm ngặt:** Với enum `PaymentState { NEW, PAID, FAILED, REFUNDED }`, chỉ xử lý `NEW`, `PAID`, `FAILED` theo chuyển trạng thái. Dùng `default -> throw new IllegalStateException(...)` cho `REFUNDED` khi chức năng chưa hỗ trợ. Viết unit test xác nhận không trả thành công giả.

**Bài 5 — Fail-closed:** Dùng enum vai trò `ADMIN, USER, GUEST, UNKNOWN`. Chỉ `ADMIN` được phép thao tác xóa. Viết `switch expression` với `default -> false`, thử `UNKNOWN` và null. Sau đó thêm `AUDITOR` và kiểm tra rằng nó không được cấp quyền ngoài ý muốn.

**Bài 6 — Java 21 và null:** Viết lại `display(Status)` bằng `case null -> ...`, không tiền kiểm riêng. Giải thích sự khác nhau giữa `case null` và `default` khi enum có thêm constant.

**Bài 7 — Pattern switch(Object):** Viết `switch (Object input)` có `case Status state`, `case String raw`, `case null` và `default`. Chỉ ra default nào bắt constant chưa liệt kê trong enum, default nào bắt kiểu đối tượng không hỗ trợ, và nhánh nào xử lý chuỗi từ API.

**Bài 8 — Tương thích phiên bản:** Giả sử module A chứa enum và module B chứa `switch`. Mô tả việc cần làm khi cập nhật module A từ ba constants lên bốn constants, so sánh chiến lược có default và không default khi biên dịch lại module B.

### Câu hỏi tự đánh giá

- Tại sao `default` không thể nhận một chuỗi `"NOT_IN_ENUM"` khi `valueOf` đã thất bại?
- `case UNKNOWN` khác `default` như thế nào nếu enum có constant `UNKNOWN`?
- Khi nào switch expression trên enum có thể bỏ `default`?
- Vì sao việc luôn có default có thể **che** yêu cầu thêm case khi enum tiến hóa?
- Nếu enum được nâng cấp mà mã switch chưa biên dịch lại, điều gì có thể xảy ra khi xuất hiện constant mới?
- `null` có đi vào default trong Java 17 và Java 21 hay không?
- Vì sao legacy enum switch statement không có default có thể không làm gì, trong khi switch expression yêu cầu đầy đủ?
- Khi nào fallback nên trả nhãn chung, khi nào cần throw hoặc từ chối?
- Nếu security role mới xuất hiện, quyền mặc định nào an toàn?
- Bạn sẽ kiểm thử những dữ liệu nào để phân biệt lỗi parse, constant chưa có case và null?

Hoàn thành bài khi bạn **phân loại đúng các ý nghĩa “không biết”**, biết chọn chính sách `default` phù hợp, xử lý chuỗi ngoại vi ở tầng parse, nhận ra ảnh hưởng của enum evolution và dùng `switch expression`/`switch statement` đúng phiên bản Java.

## 15. Nguồn chính thức

- [Java Language Specification SE 21 — `14.11 Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): enum case labels, tính đầy đủ của enhanced switch statement, chọn nhánh và xử lý `null`.
- [Java Language Specification SE 21 — `15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): exhaustiveness của switch expression, nhánh trả giá trị, và `MatchException` khi không có nhãn áp dụng.
- [Oracle Java SE 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html): hướng dẫn switch expression và xử lý enum cases.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): `->`, `yield`, tính đầy đủ của switch expression.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): `case null`, type pattern và quy tắc switch được mở rộng trong Java 21.
- [Java SE 21 API — Enum.valueOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String)): tra cứu constant theo tên và lỗi khi không tồn tại.

**Ghi nhớ:** `default` là **nhánh dự phòng cho giá trị đã lọt vào switch**, không phải bộ giải mã dữ liệu bên ngoài. Một fallback tốt phải diễn đạt rõ hành vi với constant chưa có case: **hiển thị an toàn, từ chối hoặc báo lỗi có chủ đích**. Khi enum thuộc hợp đồng nghiệp vụ đóng và mọi constant cần xử lý riêng, cân nhắc liệt kê đầy đủ các case mà **không đặt default**, để compiler giúp phát hiện thay đổi.
