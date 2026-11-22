# So sánh `enum switch` với `Map` tra cứu trong Java

## 1. Hai cách chuyển một enum thành kết quả

Khi một biến có kiểu `enum`, ta thường phải chuyển trạng thái của nó thành nhãn hiển thị, mã phản hồi, quyền truy cập hoặc hành động. Hai lựa chọn rất phổ biến là:

- **`switch` trên enum:** mô tả trực tiếp logic theo từng hằng số enum trong cấu trúc điều khiển.
- **`Map<Enum, Value>`:** tách thông tin ánh xạ thành dữ liệu gồm khóa enum và giá trị tương ứng; với khóa enum, nên cân nhắc `EnumMap`.

Ví dụ giản lược, giả sử đã có `enum TaskState { NEW, RUNNING, DONE, FAILED }`.

**Dùng `switch` expression:**

```java
static String labelBySwitch(TaskState state) {
    return switch (state) {
        case NEW -> "New";
        case RUNNING -> "Running";
        case DONE -> "Done";
        case FAILED -> "Failed";
    };
}
```

**Dùng `EnumMap`:**

```java
EnumMap<TaskState, String> labels = new EnumMap<>(TaskState.class);
labels.put(TaskState.NEW, "New");
labels.put(TaskState.RUNNING, "Running");
labels.put(TaskState.DONE, "Done");
labels.put(TaskState.FAILED, "Failed");

String label = labels.get(TaskState.DONE); // "Done"
```

Các đoạn trên là **mã minh họa trong ngữ cảnh đã định nghĩa `TaskState`**; chương trình chạy độc lập có ở mục 7.

Nếu giá trị đầu vào là `DONE`, cả hai cách đều trả `"Done"`. Tuy nhiên, chúng khác đáng kể về **kiểm tra đủ trường hợp, xử lý khóa thiếu, khả năng thay đổi bảng ánh xạ và độ rõ của logic**.

### Có phải `case NEW` là một type pattern không?

**Không.** Trong `switch (state)` với selector kiểu `TaskState`, `case NEW` là một **nhãn hằng enum**; nó không khai báo pattern variable như `case String text` hoặc `case Point(int x, int y)`. Bài này thuộc mạch học Java Core Pattern Matching vì khi thiết kế `switch` hiện đại, bạn cần phân biệt **constant labels** với **type/record patterns** và hiểu cách compiler kiểm tra tính đầy đủ.

Từ Java 14, `switch` expression đã là tính năng chính thức. Mã Java 21 trong bài dùng dạng `case ... -> ...` phổ biến; không cần bật preview.

## 2. Khác biệt quan trọng nhất: kiểm tra đầy đủ lúc biên dịch

### `switch` expression có kiểm tra exhaustiveness

Với enum:

```java
enum TaskState {
    NEW, RUNNING, DONE, FAILED
}
```

Nếu biểu thức `switch` liệt kê đủ bốn hằng, compiler biết giá trị enum **khác `null`** nào cũng có case tương ứng:

```java
return switch (state) {
    case NEW -> "New";
    case RUNNING -> "Running";
    case DONE -> "Done";
    case FAILED -> "Failed";
};
```

Bây giờ giả sử bạn thêm hằng `CANCELLED` vào `TaskState` rồi **biên dịch lại** chương trình nhưng chưa sửa `switch`. Biểu thức trên sẽ gây lỗi biên dịch do thiếu nhánh `CANCELLED`.

Đây là ưu điểm lớn khi trạng thái enum có ý nghĩa nghiệp vụ bắt buộc phải xử lý riêng: **compiler giúp phát hiện đường đi chưa được viết mã**.

Nếu thêm:

```java
default -> "Other";
```

thì `switch` expression sẽ không còn báo thiếu `CANCELLED` chỉ vì thay đổi enum, vì `default` đã nhận các hằng còn lại. `default` không sai, nhưng nó làm giảm khả năng compiler buộc người lập trình xem lại hành vi khi thêm trạng thái mới.

**Phân biệt statement và expression:** một **traditional `switch` statement** có thể không exhaustive, trong khi **`switch` expression** yêu cầu exhaustive. Vì vậy lời khuyên “enum switch luôn bắt mọi trạng thái” là quá chung; lợi ích compiler nói trên rõ ràng nhất với **switch expression không `default`**.

### `EnumMap` không tự phát hiện khóa thiếu lúc biên dịch

Một `EnumMap<TaskState, String>` có thể chỉ chứa:

```java
EnumMap<TaskState, String> labels = new EnumMap<>(TaskState.class);
labels.put(TaskState.NEW, "New");
labels.put(TaskState.DONE, "Done");
```

Mã trên **hợp lệ** dù `RUNNING` và `FAILED` không được ánh xạ. Gọi `labels.get(TaskState.FAILED)` trả về `null`, chứ compiler không báo bạn quên `FAILED`.

Nếu sau này thêm `CANCELLED`, compiler cũng **không yêu cầu** bạn phải cập nhật `EnumMap`. Một `Map` là **cấu trúc dữ liệu**, không phải cấu trúc điều khiển có quy tắc exhaustiveness như `switch` expression.

Để đạt mức bảo vệ tương tự, cần **tự kiểm tra đủ khóa** lúc khởi tạo hoặc trong test. Ví dụ dùng `EnumSet.allOf(TaskState.class)` để lấy toàn bộ hằng rồi trừ đi `keySet()` của map.

## 3. `EnumMap` khác gì `HashMap` khi khóa là enum?

Nếu các khóa đều là một loại enum, `EnumMap<K extends Enum<K>, V>` được thiết kế riêng cho tình huống này:

| Khía cạnh | `EnumMap<TaskState, V>` | `HashMap<TaskState, V>` |
| --- | --- | --- |
| Kiểu khóa | Khóa thuộc một loại enum cụ thể | Nhận mọi kiểu khóa phù hợp với tham số `K` |
| Tổ chức dữ liệu | Cấu trúc chuyên biệt, gắn với các hằng enum | Hash table |
| Thứ tự duyệt khóa | Theo **thứ tự khai báo của enum** | Không bảo đảm một thứ tự duyệt |
| Sử dụng bộ nhớ | Thường gọn với tập khóa enum hữu hạn | Có chi phí cấu trúc hash |
| Truy cập khóa | Được thiết kế để tra cứu hiệu quả, thường thời gian hằng số | Thường thời gian hằng số trung bình |
| Khóa `null` | Không cho phép thêm bằng `put(null, ...)` | Cho phép một khóa `null` |
| Giá trị `null` | Cho phép lưu giá trị `null` | Cho phép lưu giá trị `null` |

`EnumMap` có thể được khởi tạo ngay cả khi chưa có phần tử:

```java
EnumMap<TaskState, String> labels =
        new EnumMap<>(TaskState.class);
```

Truyền `TaskState.class` xác định loại enum của khóa. Khi dùng constructor nhận `Map`, loại khóa phải suy ra được; khởi tạo từ một map rỗng không có đủ thông tin kiểu có thể gây lỗi tùy constructor và dữ liệu. Cách rõ ràng nhất là truyền enum class.

**Không nên kết luận “`EnumMap` luôn nhanh hơn `switch`”.** `switch` có thể được compiler/JVM tối ưu theo nhiều cách; `EnumMap` cũng tra cứu hiệu quả. Hiệu năng còn tùy JDK, độ lớn tập trạng thái, cách sử dụng, tối ưu JIT và tính chất xử lý. Khi tốc độ thực sự quan trọng, nên benchmark đúng luồng ứng dụng thay vì dựa vào một khẩu hiệu.

## 4. Khi nào nên chọn `switch`, khi nào chọn `EnumMap`?

| Tình huống | Thường ưu tiên | Vì sao |
| --- | --- | --- |
| Mỗi trạng thái có **logic khác nhau** | `switch` | Dễ đọc đường điều khiển, có thể dùng block và `yield` |
| Phải nhận biết **mọi enum hằng khi build** | `switch` expression, không `default` | Compiler báo thiếu case khi thêm hằng và biên dịch lại |
| Enum chỉ được ánh xạ sang **giá trị dữ liệu đơn giản** | `EnumMap` | Bảng dữ liệu rõ ràng, giảm lặp boilerplate ở nhiều nơi |
| Cần thêm/bớt/thay đổi ánh xạ **lúc chạy** | `EnumMap` có kiểm soát | Có thể cập nhật các giá trị ứng với enum đã định nghĩa |
| Chỉ một số trạng thái có ánh xạ | `EnumMap` | Bản đồ **không đầy đủ có chủ đích** có thể diễn đạt một tập con |
| Cần nhiều handler được tra cứu theo trạng thái | `EnumMap<State, Function<...>>` | Tách dữ liệu dispatch khỏi implementation |
| Không muốn bỏ sót giá trị khi thêm enum constant | `switch` hoặc `EnumMap` có validator/test | Không nên dùng `getOrDefault` để âm thầm che lỗi thiếu |
| Mục tiêu tối ưu hiệu năng | Đo bằng benchmark | Không có đáp án tuyệt đối theo cú pháp |

Đây là **gợi ý thiết kế**, không phải các quy tắc ngôn ngữ bắt buộc. Ví dụ nếu mỗi enum hằng chỉ trả một nhãn, một `switch` vẫn có thể rất rõ ràng; với nhiều mapping khác nhau, `EnumMap` có thể dễ bảo trì hơn.

## 5. Giá trị thiếu, fallback và `null`

### Thiếu khóa trong map

```java
EnumMap<TaskState, String> labels =
        new EnumMap<>(TaskState.class);
labels.put(TaskState.NEW, "New");

String a = labels.get(TaskState.DONE); // null
String b = labels.getOrDefault(TaskState.DONE, "UNKNOWN");
// b = "UNKNOWN"
```

`getOrDefault` chỉ dùng giá trị dự phòng nếu **không có mapping cho khóa**. Nếu map có **mapping tồn tại nhưng giá trị là `null`**, `getOrDefault` vẫn trả `null`. Đây là khác biệt quan trọng vì `EnumMap` cho phép lưu giá trị `null`.

Có thể phân biệt bằng:

```java
if (labels.containsKey(TaskState.DONE)) {
    // Có mapping (giá trị có thể là null).
} else {
    // Hoàn toàn chưa có mapping.
}
```

Nếu tất cả trạng thái phải có nhãn khác `null`, hãy **kiểm tra đủ khóa và không nhận giá trị `null`** trong khâu dựng bảng hoặc khi đọc. Không nên mặc định rằng `get() == null` luôn chỉ có một nguyên nhân.

### Selector `null` trong `switch`

Trong Java 21, có thể xử lý rõ `null`:

```java
return switch (state) {
    case null -> "No state";
    case NEW -> "New";
    case RUNNING -> "Running";
    case DONE -> "Done";
    case FAILED -> "Failed";
};
```

Nếu bỏ `case null`, một `switch` trên enum với selector bằng `null` thường ném `NullPointerException`; một `default` thông thường không phải lựa chọn thay thế tương đương `case null`.

### Khóa `null` trong `EnumMap`

`EnumMap.put(null, "x")` ném `NullPointerException`: không thể thêm một phần tử với khóa `null`. Với `get(null)`, map không tìm thấy khóa enum hợp lệ và trả `null`. Do đó nếu muốn hàm tra cứu và hàm switch đều trả `"No state"` cho đầu vào rỗng, bạn cần kiểm tra `state == null` **trước** thao tác `get`.

Hai API có hành vi khác nhau và việc xử lý thống nhất là quyết định của chương trình, không phải điều mặc định từ enum.

## 6. Chặn thiếu trạng thái bằng `EnumSet` và bảng không sửa đổi

Nếu map phải ánh xạ **mọi** trạng thái, nên dựng và kiểm tra bảng ở một nơi:

```java
static Map<TaskState, String> buildLabels() {
    EnumMap<TaskState, String> result =
            new EnumMap<>(TaskState.class);

    result.put(TaskState.NEW, "New");
    result.put(TaskState.RUNNING, "Running");
    result.put(TaskState.DONE, "Done");
    result.put(TaskState.FAILED, "Failed");

    EnumSet<TaskState> missing = EnumSet.allOf(TaskState.class);
    missing.removeAll(result.keySet());

    if (!missing.isEmpty()) {
        throw new IllegalStateException("Missing states: " + missing);
    }
    return Collections.unmodifiableMap(result);
}
```

Đây là **phương thức minh họa**, cần các import `Map`, `EnumMap`, `EnumSet` và `Collections`. Bản đầy đủ sẽ nằm trong chương trình ở mục 7.

Cơ chế kiểm tra:

1. `EnumSet.allOf(TaskState.class)` tạo tập gồm **tất cả enum constants hiện có**.
2. `removeAll(result.keySet())` bỏ đi các hằng đã được ánh xạ.
3. Nếu vẫn còn phần tử, chính là những trạng thái **thiếu khóa**.
4. `Collections.unmodifiableMap(result)` trả một view không cho phép sửa qua biến map được công khai. Trong ví dụ, `result` là biến cục bộ không thoát ra ngoài qua tham chiếu có thể thay đổi, nên view này phù hợp với mục tiêu chỉ đọc.

Đây là **kiểm tra lúc runtime**, thường diễn ra khi khởi tạo class, **không phải exhaustiveness do compiler tự chứng minh**. Nếu thêm enum constant mà quên map, chương trình có thể ném lỗi khi khởi tạo thay vì âm thầm xuất nhãn `null`.

**Kiểm tra giá trị:** bộ kiểm tra khóa chưa đủ nếu cho phép `null` làm giá trị. Trong bảng thực tế, nên kiểm tra từng mapping bằng `Objects.requireNonNull(...)` hoặc dùng chính sách không chấp nhận giá trị rỗng. Chương trình hoàn chỉnh dùng các chuỗi cố định không `null`.

Với mapping dài và có khả năng thay đổi, viết một unit test so sánh `EnumSet.allOf(...)` với `map.keySet()` cũng hữu ích. Đừng chỉ test vài hằng quen thuộc.

## 7. Chương trình Java 21 hoàn chỉnh: cùng kết quả qua hai cách

Tạo tệp **`EnumSwitchVsLookup.java`**:

```java
import java.util.Collections;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;

public class EnumSwitchVsLookup {
    enum TaskState { NEW, RUNNING, DONE, FAILED }

    static String labelBySwitch(TaskState state) {
        return switch (state) {
            case null -> "No state";
            case NEW -> "New";
            case RUNNING -> "Running";
            case DONE -> "Done";
            case FAILED -> "Failed";
        };
    }

    private static Map<TaskState, String> buildLabels() {
        EnumMap<TaskState, String> result =
                new EnumMap<>(TaskState.class);

        result.put(TaskState.NEW, "New");
        result.put(TaskState.RUNNING, "Running");
        result.put(TaskState.DONE, "Done");
        result.put(TaskState.FAILED, "Failed");

        EnumSet<TaskState> missing =
                EnumSet.allOf(TaskState.class);
        missing.removeAll(result.keySet());

        if (!missing.isEmpty()) {
            throw new IllegalStateException("Missing states: " + missing);
        }

        return Collections.unmodifiableMap(result);
    }

    private static final Map<TaskState, String> LABELS = buildLabels();

    static String labelByMap(TaskState state) {
        if (state == null) {
            return "No state";
        }
        String label = LABELS.get(state);
        if (label == null) {
            throw new IllegalStateException("No label for " + state);
        }
        return label;
    }

    public static void main(String[] args) {
        for (TaskState state : TaskState.values()) {
            System.out.println(state + " -> switch="
                    + labelBySwitch(state)
                    + ", map=" + labelByMap(state));
        }

        System.out.println("null -> switch="
                + labelBySwitch(null)
                + ", map=" + labelByMap(null));

        EnumMap<TaskState, String> incomplete =
                new EnumMap<>(TaskState.class);
        incomplete.put(TaskState.NEW, "New");

        System.out.println("missing DONE = "
                + incomplete.get(TaskState.DONE));

        System.out.println("default DONE = "
                + incomplete.getOrDefault(TaskState.DONE, "UNKNOWN"));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên** với mức nguồn Java 21:

```bash
javac --release 21 EnumSwitchVsLookup.java
java EnumSwitchVsLookup
```

**Stdout chính xác:**

```text
NEW -> switch=New, map=New
RUNNING -> switch=Running, map=Running
DONE -> switch=Done, map=Done
FAILED -> switch=Failed, map=Failed
null -> switch=No state, map=No state
missing DONE = null
default DONE = UNKNOWN
```

Diễn giải:

- Bốn lần lặp `TaskState.values()` lần lượt duyệt enum constants theo thứ tự khai báo; kết quả của hai cách trùng nhau với bảng đầy đủ.
- `labelBySwitch(null)` đi vào `case null`; `labelByMap(null)` có guard đầu phương thức. Cả hai trả `No state`.
- `incomplete` chỉ có khóa `NEW`. `get(DONE)` trả `null` mà không báo compile error.
- `getOrDefault(DONE, "UNKNOWN")` trả giá trị dự phòng vì khóa `DONE` chưa có trong `incomplete`.
- `buildLabels()` có bước kiểm tra enum đầy đủ và trả view không sửa đổi, nên bảng chính `LABELS` không bị chỉnh qua những đoạn code sử dụng biến này.

Đoạn chương trình cho thấy hai cách hoàn toàn có thể cho **cùng kết quả chức năng**, nhưng đảm bảo của compiler và cách phát hiện lỗi thiếu mapping không giống nhau.

## 8. Nếu ánh xạ thành hành động thay vì chuỗi thì sao?

Không phải mọi trạng thái chỉ cần trả nhãn. Có tình huống bạn muốn chọn một **hàm xử lý** theo enum.

Với `switch`, viết trực tiếp logic:

```java
enum Operation { DOUBLE, TRIPLE, NEGATE }

static int calculate(Operation op, int input) {
    return switch (op) {
        case DOUBLE -> input * 2;
        case TRIPLE -> input * 3;
        case NEGATE -> -input;
    };
}
```

Đây là **đoạn minh họa trong một lớp**.

Với map, có thể đưa các hàm vào `EnumMap`:

```java
EnumMap<Operation, java.util.function.IntUnaryOperator> handlers =
        new EnumMap<>(Operation.class);

handlers.put(Operation.DOUBLE, n -> n * 2);
handlers.put(Operation.TRIPLE, n -> n * 3);
handlers.put(Operation.NEGATE, n -> -n);

int result = handlers.get(Operation.TRIPLE).applyAsInt(4);
// result = 12
```

Ưu điểm của map handler: có thể cấu hình/đổi chiến lược thực thi bằng dữ liệu lưu trong map, tách phần dispatch khỏi phần hành động. Tuy nhiên:

- Cần bảo đảm có handler cho trạng thái cần xử lý; nếu `get(op)` trả `null` mà vẫn gọi `applyAsInt`, sẽ ném `NullPointerException`.
- Nên kiểm tra kiểu/hợp đồng của handler và vấn đề thread-safety khi thay đổi map dùng chung.
- Nếu tập thao tác cố định và logic ngắn, `switch` thường rõ ràng và có bảo vệ exhaustiveness.
- Nếu một trạng thái cần hành động phức tạp, có thể tách phương thức xử lý riêng; không cần dùng map handler chỉ để tránh vài dòng `switch`.

**Đừng nhầm giá trị trong map với pattern variable.** `EnumMap<Operation, IntUnaryOperator>` là bảng tra cứu hàm. Nó không mang flow scoping của `case String text`, cũng không tự trở thành `switch` exhaustive.

## 9. Tính đọc được và bảo trì khi enum thay đổi

Một quyết định nên dựa trên **điều gì cần trở thành lỗi khi thay đổi enum**.

### Khi một trạng thái mới bắt buộc phải được xử lý

Giả sử bổ sung `CANCELLED` vào `TaskState`. Với `switch` expression không `default`, khi bạn biên dịch lại mã theo enum mới, compiler báo thiếu case và buộc bạn chọn một nhãn/logic thích hợp.

Nếu dùng `EnumMap`, có hai lựa chọn có chủ đích:

- **Map đầy đủ:** validator dùng `EnumSet.allOf(TaskState.class)` và báo lỗi khởi tạo nếu thiếu `CANCELLED`.
- **Map một phần:** chấp nhận thiếu khóa, nhưng caller phải xử lý kết quả `null` hoặc fallback một cách minh bạch.

Nếu thiếu trường hợp là lỗi nghiêm trọng, `getOrDefault(..., "Other")` có thể che vấn đề và khiến trạng thái mới hiển thị sai. Không nên dùng fallback chỉ vì muốn chương trình “luôn trả chuỗi”.

### Khi mapping là cấu hình thay đổi tại runtime

Map linh hoạt hơn: bạn có thể chọn bản dịch nhãn theo locale, bật/tắt vài hành động theo tính năng, hoặc xây dựng một map khác từ cấu hình đã kiểm tra hợp lệ. Tuy nhiên **tập enum constants vẫn được quyết định lúc biên dịch**; việc đổi nội dung map lúc chạy **không tạo ra hằng enum mới**.

Nếu cần nhiều bản dịch độc lập, có thể dùng một `EnumMap` cho mỗi ngôn ngữ và kiểm tra đủ khóa của từng bảng. Trường hợp đơn giản có thể phù hợp hơn với `ResourceBundle` hoặc hệ thống i18n của ứng dụng. Quan trọng là tránh tạo mapping thiếu âm thầm.

### Một lựa chọn thứ ba: hành vi nằm trong chính enum

Java cũng cho phép định nghĩa dữ liệu hoặc phương thức trong enum. Ví dụ:

```java
enum StateWithLabel {
    NEW("New"), RUNNING("Running"), DONE("Done");

    private final String label;

    StateWithLabel(String label) {
        this.label = label;
    }

    String label() {
        return label;
    }
}
```

Đây là **một kiểu enum minh họa độc lập**. Khi mỗi constant luôn gắn cố định với một nhãn hoặc một thuộc tính của trạng thái, cách này có thể gọn hơn cả `switch` lẫn map. Nhưng nếu ánh xạ thuộc lớp hiển thị, ngôn ngữ hoặc cấu hình riêng của hệ thống, đẩy nó vào domain enum có thể làm giảm khả năng tách mối quan tâm.

Bài này so sánh chủ yếu `switch` với map, nhưng lựa chọn enum property đáng cân nhắc để không phải duy trì bảng bên ngoài cho những thuộc tính thật sự thuộc bản thân từng hằng.

## 10. Tốc độ, bộ nhớ và độ an toàn: tránh kết luận tuyệt đối

**Về hiệu năng:**

- `switch` trên enum là cấu trúc điều khiển được compiler/JVM triển khai theo cách tối ưu tương ứng; không cần lookup qua một đối tượng `Map` do bạn tự tạo.
- `EnumMap` được thiết kế cho khóa enum và thường rất hiệu quả cả về bộ nhớ lẫn tra cứu.
- Thời gian thực tế còn phụ thuộc JIT, hot path, các hành động của nhánh, layout dữ liệu, cấp phát và tối ưu runtime. Một mapping chỉ chạy lúc khởi tạo UI thường không đáng đánh đổi tính rõ ràng để tiết kiệm vài nanosecond.

**Về an toàn thay đổi:**

- `switch` expression không `default` giúp phát hiện enum constant bị thiếu khi **biên dịch lại**. Nó không phải cơ chế kiểm tra cấu hình runtime.
- Map chỉ an toàn tương đương trong yêu cầu bao phủ nếu bạn **có validator/test** và xử lý giá trị thiếu hoặc `null`.
- `Collections.unmodifiableMap` chặn sửa qua view được chia sẻ, nhưng không làm mọi cấu trúc dữ liệu mà nó có thể wrap trở thành bất biến sâu; nếu còn tham chiếu tới map gốc ở nơi khác, dữ liệu gốc vẫn có thể bị thay đổi. Ví dụ chính giữ map gốc là biến cục bộ không bị rò rỉ.

**Về tính dễ hiểu:**

- Với 3–5 case có điều kiện khác nhau, `switch` thường dễ đọc hơn một map chứa lambda phức tạp.
- Với hàng chục ánh xạ dữ liệu thuần, `EnumMap` hoặc cách cấu hình có thể dễ quản lý hơn chuỗi `case` dài.
- Đừng dùng `EnumMap` để giấu đi logic có side effect khó kiểm soát; cũng đừng biến mọi ánh xạ dữ liệu thành một `switch` rối rắm.

## 11. Lỗi thường gặp và cách tránh

| Lỗi / nhầm lẫn | Vì sao sai hoặc rủi ro | Cách xử lý |
| --- | --- | --- |
| Tưởng `EnumMap` tự exhaustive | Map có thể thiếu khóa mà vẫn biên dịch | Dùng `EnumSet.allOf(...)`, validator và unit test |
| Tưởng mọi `switch` trên enum đều exhaustive | Traditional switch statement có thể thiếu nhánh | Dùng switch expression khi muốn compiler kiểm tra |
| Thêm `default` để “chắc ăn” | Có thể che trạng thái enum mới chưa được cân nhắc | Bỏ `default` khi từng hằng phải có chính sách riêng |
| Dùng `getOrDefault` để giấu thiếu mapping | Dữ liệu mới có thể mang nhãn sai mà không báo lỗi | Tách rõ “thiếu là lỗi” với “thiếu được phép” |
| Tưởng `getOrDefault` thay thế giá trị `null` | Nếu khóa có mapping đến `null`, nó vẫn trả `null` | Phân biệt `containsKey` và giá trị thực tế |
| Dùng `EnumMap.put(null, ...)` | Khóa `null` không được chấp nhận | Kiểm tra null trước khi thêm |
| Gọi handler khi map chưa có khóa | `handlers.get(op)` có thể trả `null` | Validate key set và fail fast có thông điệp |
| Chọn `HashMap` do thói quen | Bỏ qua lợi ích chuyên biệt của `EnumMap` | Cân nhắc `EnumMap<>(EnumType.class)` |
| Khẳng định giải pháp nào “nhanh hơn” | JDK và workload khác nhau | Benchmark trên môi trường thực tế |
| Nhầm enum case constant với type pattern | `case DONE` không khai báo biến kiểu | Phân biệt hằng enum với `case SomeType x` |

## 12. Checklist thiết kế và tự kiểm tra

Khi cần chuyển trạng thái enum thành dữ liệu/hành động, hãy tự trả lời:

1. **Tất cả enum constants đều phải được xử lý chứ?** Nếu có, ưu tiên `switch` expression không `default`, hoặc map có xác minh đủ khóa.
2. **Mỗi trạng thái có logic hay chỉ có giá trị dữ liệu?** Logic khác nhau thường hợp với `switch`; dữ liệu bảng thường hợp với `EnumMap`.
3. **Thiếu mapping là lỗi hay fallback hợp lệ?** Đây là quyết định nghiệp vụ, không để `getOrDefault` quyết định thay.
4. **Giá trị `null` có thể xuất hiện không?** Xử lý rõ selector `null`, khóa `null` và giá trị map `null`.
5. **Mapping có thể thay đổi tại runtime không?** Nếu có, map/cấu hình có thể linh hoạt hơn, nhưng vẫn cần ràng buộc kiểu và test.
6. **Nếu thêm enum constant, muốn compiler hay runtime bắt lỗi?** Cân nhắc lợi thế của switch expression ở compile time.
7. **Có cần so sánh hiệu năng không?** Chỉ benchmark khi thực sự nằm trên hot path và kết quả có thể ảnh hưởng quyết định.

### Câu hỏi 1

Với `enum State { A, B, C }`, mã sau có biên dịch không?

```java
static int code(State state) {
    return switch (state) {
        case A -> 1;
        case B -> 2;
    };
}
```

**Đáp án:** Không. `switch` expression thiếu `C` và không có `default`. Trình biên dịch từ chối vì chưa exhaustive.

### Câu hỏi 2

Nếu thay bằng:

```java
EnumMap<State, Integer> codes = new EnumMap<>(State.class);
codes.put(State.A, 1);
codes.put(State.B, 2);
```

Map có biên dịch không? `codes.get(State.C)` trả gì?

**Đáp án:** Có. Map thiếu `C` vẫn hợp lệ; `get(C)` trả `null` khi không có mapping. Muốn thiếu khóa trở thành lỗi, phải tự kiểm tra/validate.

### Câu hỏi 3

Nếu thêm `CANCELLED` vào enum có `switch` expression đã đầy đủ trước đó nhưng có `default -> "Other"` thì compiler có buộc thêm nhánh riêng cho `CANCELLED` không?

**Đáp án:** Không. `default` đã được xem là đường xử lý cho giá trị còn lại. Điều này có thể đúng ý định hoặc làm bỏ sót yêu cầu nghiệp vụ, tùy trường hợp.

### Câu hỏi 4

Muốn nhận `String` nhãn cho tất cả trạng thái, nhưng tên nhãn tùy ngôn ngữ, và mỗi bản dịch có thể thay đổi theo cấu hình. Chọn gì?

**Đáp án:** Một `EnumMap<TaskState, String>` theo từng locale hoặc một hệ thống i18n phù hợp sẽ thuận tiện hơn `switch` hard-code cho mỗi ngôn ngữ. Nhưng vẫn phải kiểm tra đủ hằng và không chấp nhận ánh xạ rỗng nếu nhãn là bắt buộc.

**Ghi nhớ:** **`switch` expression là logic được compiler kiểm tra độ bao phủ; `EnumMap` là bảng dữ liệu linh hoạt cần kiểm tra độ đầy đủ riêng.** Hai cách không đối lập tuyệt đối. Chọn theo đặc điểm mapping, yêu cầu phát hiện lỗi khi enum thay đổi, chính sách fallback và khả năng bảo trì.

## Tài liệu tham khảo

- [Java Language Specification 21 — §15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [Java Language Specification 21 — §14.11 Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java SE 21 API — `EnumMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/EnumMap.html).
- [Java SE 21 API — `EnumSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/EnumSet.html).
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).