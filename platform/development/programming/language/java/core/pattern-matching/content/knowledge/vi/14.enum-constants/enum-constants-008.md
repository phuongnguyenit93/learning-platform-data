# Kiểm thử toàn bộ enum domain trong Java

**Chủ đề:** Java Core Pattern Matching → Enum và constant  
**Phiên bản thực hành:** Java 21. Các quy tắc `switch` expression trên enum đã có từ trước Java 21; chương trình trong bài dùng `case null` theo cú pháp `switch` Java 21, nên biên dịch bằng JDK 21 trở lên.

## 1. “Kiểm thử toàn bộ enum domain” nghĩa là gì?

Một `enum` định nghĩa một **tập hữu hạn các hằng số có tên**, ví dụ:

```java
enum TaskState {
    NEW, RUNNING, DONE, FAILED
}
```

*Enum domain* của `TaskState` là tập tất cả giá trị enum hợp lệ: `NEW`, `RUNNING`, `DONE`, `FAILED`. Mục tiêu kiểm thử toàn bộ domain không chỉ là “chạy được một vài trạng thái”, mà là bảo đảm **mỗi hằng hiện có đều được đưa qua logic cần kiểm tra** và **kết quả của từng hằng được so với yêu cầu độc lập**.

Ví dụ, một phương thức chuyển trạng thái thành nhãn hiển thị có thể vô tình hoán đổi nhãn `DONE` và `FAILED`. Nếu chỉ kiểm tra hàm có trả chuỗi khác `null`, test sẽ không phát hiện sai sót. Test tốt phải biết rõ `DONE` phải được biểu diễn là `SUCCESS`, còn `FAILED` là `ERROR`.

Cần phân biệt ba câu hỏi:

1. **Coverage của domain:** mọi hằng của enum đã xuất hiện trong input test chưa?
2. **Correctness của mapping:** đầu ra cho từng hằng có đúng như đặc tả không?
3. **Bảo trì khi enum thay đổi:** khi thêm hằng mới, compiler hoặc test có bắt người phát triển cập nhật hành vi tương ứng không?

Ba câu hỏi này bổ sung cho nhau; một vòng lặp qua `values()` chỉ trực tiếp giải quyết câu hỏi đầu tiên.

## 2. `switch` expression trên enum và tính exhaustive

Với selector có kiểu tĩnh là `TaskState`, các nhãn hằng enum được viết bằng tên hằng không cần tiền tố kiểu:

```java
static String label(TaskState state) {
    return switch (state) {
        case NEW -> "QUEUED";
        case RUNNING -> "IN_PROGRESS";
        case DONE -> "SUCCESS";
        case FAILED -> "ERROR";
    };
}
```

Đây là **phương thức minh họa**; nó cần đặt bên trong một class cùng khai báo `TaskState`. Khi compiler biết enum có đúng bốn hằng trên, `switch` expression bao phủ đủ bốn trường hợp không null nên **không cần `default`**.

Nếu bỏ `case FAILED` mà vẫn không có `default`, compiler báo thiếu tính đầy đủ (*exhaustiveness*):

```java
// KHÔNG BIÊN DỊCH khi enum có NEW, RUNNING, DONE, FAILED:
return switch (state) {
    case NEW -> "QUEUED";
    case RUNNING -> "IN_PROGRESS";
    case DONE -> "SUCCESS";
    // FAILED chưa có nhánh và không có default.
};
```

Thông báo biên dịch tương ứng trong JDK hiện đại có nội dung kiểu: `the switch expression does not cover all possible input values`.

**Đặc điểm hữu ích:** Nếu sau này thêm `CANCELLED` vào `TaskState` và biên dịch lại phương thức không có `default`, compiler sẽ yêu cầu xử lý trạng thái mới. Đây là một lớp kiểm tra **tĩnh**, nhưng chưa thay thế được unit test về giá trị trả về.

### Khi nào dùng `default`?

```java
static String labelWithFallback(TaskState state) {
    return switch (state) {
        case NEW -> "QUEUED";
        case RUNNING -> "IN_PROGRESS";
        default -> "OTHER";
    };
}
```

Ví dụ này biên dịch vì `default` bao phủ `DONE` và `FAILED` còn lại. Nhưng nó cũng làm hai trạng thái khác nhau nhận chung `OTHER` — có thể sai yêu cầu. Nếu thêm `CANCELLED`, trạng thái mới cũng có thể đi vào `default` mà không buộc compiler yêu cầu một case cụ thể. Chỉ dùng `default` khi nghiệp vụ **thực sự định nghĩa** một nhánh dự phòng chung.

## 3. Các công cụ để liệt kê và đối chiếu domain

Java cung cấp một số API hữu ích:

| Công cụ | Ý nghĩa | Dùng khi nào |
| --- | --- | --- |
| `TaskState.values()` | Mảng mới chứa toàn bộ enum constants theo thứ tự khai báo | Lặp mọi trạng thái để chạy test |
| `EnumSet.allOf(TaskState.class)` | Tập gồm toàn bộ constants của enum | So sánh miền đầy đủ với bảng kỳ vọng |
| `EnumMap<TaskState, Decision>` | Map với khóa là enum, hiệu quả và rõ ràng | Lưu oracle: kết quả kỳ vọng riêng cho từng trạng thái |
| `TaskState.valueOf(name)` | Phân giải tên enum chính xác về constant | Kiểm tra chuyển đổi từ chuỗi, dữ liệu lưu trữ |
| `state.name()` | Tên khai báo chính xác của constant | Tạo tên test, đối chiếu round-trip |
| `state.ordinal()` | Vị trí khai báo, bắt đầu từ 0 | Thường **không** nên làm định danh nghiệp vụ |

Ví dụ:

```java
for (TaskState state : TaskState.values()) {
    System.out.println(state.name());
}
```

Đầu ra là bốn tên `NEW`, `RUNNING`, `DONE`, `FAILED` theo đúng thứ tự khai báo. Vòng lặp này **đảm bảo đã đi qua từng enum constant**, nhưng chưa chứng minh logic gắn với các constant là đúng.

`EnumSet.allOf(TaskState.class)` không phải danh sách expectation độc lập: nó cũng suy ra domain từ chính enum. Vì thế việc chỉ so sánh `values()` với `EnumSet.allOf()` có thể xác nhận hai cách liệt kê thống nhất, nhưng **không** tự phát hiện một mapping bị sai.

## 4. Test oracle độc lập: cấu trúc quan trọng nhất

*Oracle* là một nguồn kết quả kỳ vọng được xác định **không phụ thuộc vào cách tính của hàm đang test**. Với ví dụ trạng thái, hãy viết bảng yêu cầu trước:

| TaskState | Nhãn kỳ vọng | Terminal? |
| --- | --- | --- |
| `NEW` | `QUEUED` | `false` |
| `RUNNING` | `IN_PROGRESS` | `false` |
| `DONE` | `SUCCESS` | `true` |
| `FAILED` | `ERROR` | `true` |

Một `record Decision(String label, boolean terminal)` cho phép kiểm tra cả nhãn và trạng thái kết thúc. Bảng expectation sẽ được mã hóa bằng `EnumMap` trong chương trình đầy đủ.

Điều kiện cần kiểm tra:

```java
EnumSet<TaskState> allStates = EnumSet.allOf(TaskState.class);
EnumMap<TaskState, Decision> expected = new EnumMap<>(TaskState.class);

// expected được điền tường minh theo bảng yêu cầu, không gọi hàm decide().
if (!expected.keySet().equals(allStates)) {
    throw new AssertionError("Bảng kỳ vọng thiếu enum constant");
}
```

Đoạn trên là **mã minh họa chưa độc lập**: `Decision` và `expected` cần được định nghĩa/điền dữ liệu; chương trình đầy đủ ở mục 6 sẽ thực hiện.

Điều kiện tập khóa bằng toàn bộ domain có hai chiều: không thiếu trạng thái nào và cũng không dựa vào một danh sách hard-code số lượng hằng không cần thiết. Khi thêm hằng mới, phải cập nhật oracle.

**Lưu ý:** Nếu đã có `switch` expression không `default` và thiếu nhánh khi enum thay đổi, mã sẽ bị compiler chặn trước khi test chạy. Đây là điều tốt. Nếu `switch` có fallback `default`, kiểm tra đầy đủ oracle vẫn có cơ hội phát hiện trạng thái mới chưa được gán expectation.

## 5. Quy trình kiểm thử toàn bộ domain

Một test đúng trọng tâm có thể theo 5 bước:

1. **Xác định hợp đồng đầu ra độc lập**, ghi mapping và các cờ/ngữ nghĩa liên quan cho từng enum constant.
2. **Tạo oracle** như `EnumMap` hoặc bảng test data khai báo rõ từng hằng.
3. **Xác nhận oracle bao phủ domain** bằng `EnumSet.allOf()` so với `expected.keySet()`. Không chỉ so sánh kích thước: hai tập khác nhau vẫn có thể có số lượng phần tử bằng nhau.
4. **Duyệt `values()`**, gọi hàm đang kiểm tra cho từng giá trị và so sánh đầy đủ kết quả thực tế với expectation. Dùng assertion thực sự phát sinh lỗi khi sai.
5. **Kiểm thử trường hợp ngoài domain enum** một cách riêng biệt: selector bằng `null`, chuỗi tên không hợp lệ hoặc đầu vào kiểu khác, tùy hợp đồng API.

Với mapping như `TaskState -> Decision`, nên thêm kiểm tra `valueOf(state.name()) == state` nếu mã có điểm giao tiếp lưu trữ/đọc tên enum. Đây là kiểm tra round-trip của API enum, **không chứng minh mapping nghiệp vụ** nên không được dùng làm oracle thay thế.

### Tại sao không chỉ dùng `assert`?

Java có từ khóa `assert`, nhưng assertion thường **bị vô hiệu hóa mặc định** nếu chạy mà không có `-ea`. Trong self-test bằng Java SE, hãy dùng điều kiện và `throw new AssertionError(...)`, hoặc dùng thư viện test như JUnit 5. Khi đã dùng JUnit, các assertion của JUnit hoạt động không phụ thuộc cờ `-ea`.

## 6. Chương trình Java 21 chạy được: test tất cả hằng enum

Tạo tệp **`EnumDomainCoverageDemo.java`**:

```java
public class EnumDomainCoverageDemo {
    enum TaskState { NEW, RUNNING, DONE, FAILED }

    record Decision(String label, boolean terminal) {}

    static Decision decide(TaskState state) {
        return switch (state) {
            case null -> new Decision("NO_STATE", false);
            case NEW -> new Decision("QUEUED", false);
            case RUNNING -> new Decision("IN_PROGRESS", false);
            case DONE -> new Decision("SUCCESS", true);
            case FAILED -> new Decision("ERROR", true);
        };
    }

    static void equal(String label, Object expected, Object actual) {
        if (!java.util.Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        java.util.EnumMap<TaskState, Decision> expected =
                new java.util.EnumMap<>(TaskState.class);

        // Oracle lập độc lập với hàm decide().
        expected.put(TaskState.NEW, new Decision("QUEUED", false));
        expected.put(TaskState.RUNNING,
                new Decision("IN_PROGRESS", false));
        expected.put(TaskState.DONE, new Decision("SUCCESS", true));
        expected.put(TaskState.FAILED, new Decision("ERROR", true));

        java.util.EnumSet<TaskState> domain =
                java.util.EnumSet.allOf(TaskState.class);

        equal("expected domain", domain,
                java.util.EnumSet.copyOf(expected.keySet()));

        int checked = 0;
        for (TaskState state : TaskState.values()) {
            Decision actual = decide(state);

            equal(state.name(), expected.get(state), actual);
            equal("valueOf:" + state.name(),
                    state, TaskState.valueOf(state.name()));

            System.out.println(state.name() + "=" + actual.label()
                    + ",terminal=" + actual.terminal());
            checked++;
        }

        equal("count", domain.size(), checked);

        Decision nullResult = decide(null);
        equal("null", new Decision("NO_STATE", false), nullResult);

        System.out.println("null=" + nullResult.label()
                + ",terminal=" + nullResult.terminal());
        System.out.println("COVERED=" + checked);
        System.out.println("ALL_ENUM_CASES_PASSED");
    }
}
```

Biên dịch và chạy với JDK 21+:

```bash
javac --release 21 EnumDomainCoverageDemo.java
java EnumDomainCoverageDemo
```

**Standard output chính xác:**

```text
NEW=QUEUED,terminal=false
RUNNING=IN_PROGRESS,terminal=false
DONE=SUCCESS,terminal=true
FAILED=ERROR,terminal=true
null=NO_STATE,terminal=false
COVERED=4
ALL_ENUM_CASES_PASSED
```

### Giải thích chương trình

- `TaskState.values()` sinh toàn bộ bốn hằng hiện tại; mỗi hằng được chạy qua `decide(state)`.
- `expected` là `EnumMap` được xây dựng từ bảng yêu cầu. Việc tính expected không gọi `decide` để tránh một test tự xác nhận chính logic sai của nó.
- `EnumSet.allOf(TaskState.class)` là domain hiện tại. `EnumSet.copyOf(expected.keySet())` biến khóa oracle thành một `EnumSet`, rồi kiểm tra **hai tập giá trị bằng nhau**. Vì bảng hiện tại không rỗng, phép `copyOf` là hợp lệ.
- `Decision` là record, nên `equals` do compiler sinh so sánh cả `label` và `terminal`. Nếu `DONE` trả `SUCCESS` nhưng `terminal=false`, test vẫn thất bại.
- `TaskState.valueOf(state.name())` xác nhận round-trip tên enum của từng constant.
- `checked` đếm số constant thực sự được duyệt, đối chiếu với kích thước domain.
- `decide(null)` được kiểm tra **ngoài vòng lặp** vì `null` không phải một enum constant và không có trong `values()`.
- Dòng `ALL_ENUM_CASES_PASSED` chỉ in sau khi tất cả các phép kiểm tra không ném `AssertionError`.

Trong đoạn này, nếu đổi nhãn ở một nhánh mà không cập nhật đặc tả/oracle, test sẽ báo sai giá trị. Nếu thêm một enum constant nhưng quên cập nhật `switch` không có `default`, compiler chặn ngay từ bước biên dịch. Khi đã cập nhật `switch` nhưng quên bổ sung oracle, test miền kỳ vọng sẽ phát hiện thiếu constant.

## 7. `null` không nằm trong enum domain

`null` có thể là giá trị của một **biến tham chiếu** khai báo kiểu enum, nhưng `null` **không phải một hằng được định nghĩa bởi enum**. Vì thế:

```java
TaskState state = null;
```

là khai báo hợp lệ, nhưng `state` không xuất hiện trong `TaskState.values()` và không thuộc `EnumSet.allOf(TaskState.class)`.

Trong Java 21, có thể xử lý riêng selector `null` bằng:

```java
case null -> new Decision("NO_STATE", false);
```

**Không được giả định `default` bắt `null`.** Trong `switch` Java 21, nếu selector null mà không có xử lý null thích hợp, kết quả thông thường là `NullPointerException`, kể cả khi có `default` đứng riêng.

Có hai chính sách hợp lệ:

- **Chấp nhận null** và trả một kết quả nghiệp vụ tường minh như `NO_STATE`. Khi đó unit test cần `decide(null)`.
- **Từ chối null**, chẳng hạn dùng `java.util.Objects.requireNonNull(state)` trước `switch` hoặc `case null -> throw new IllegalArgumentException(...)`. Test phải xác nhận đúng loại ngoại lệ.

Đừng tăng “số lượng trạng thái” của enum lên 1 để đếm null. Đây là ca test input bổ sung, không phải một phần của enum domain.

## 8. Kiểm thử khi thêm, đổi tên hoặc bỏ một enum constant

Giả sử phiên bản tiếp theo bổ sung `CANCELLED`:

```java
enum TaskState {
    NEW, RUNNING, DONE, FAILED, CANCELLED
}
```

Nếu `decide` vẫn giữ bốn `case` cũ và **không có `default`**, compiler báo `switch` expression chưa exhaustive khi biên dịch lại. Đây là lợi ích quan trọng của việc liệt kê đầy đủ các enum constant.

Sau khi bổ sung:

```java
case CANCELLED -> new Decision("CANCELLED", true);
```

thì mã phân loại có thể biên dịch, nhưng bảng `expected` trong test vẫn chỉ có bốn khóa. So sánh `expected.keySet()` với `EnumSet.allOf(TaskState.class)` phát hiện oracle chưa được cập nhật. Khi bổ sung expectation tương ứng, test cũng sẽ chạy cho `CANCELLED` vì `values()` tự bao gồm hằng mới.

Cần để ý các trường hợp khác:

- **Đổi tên `DONE` thành `COMPLETED`**: phải cập nhật các nhánh, dữ liệu lưu trữ dạng tên, hợp đồng API và test. `valueOf("DONE")` không tự hiểu tên mới.
- **Bỏ `FAILED`**: compiler sẽ báo nếu mã còn tham chiếu constant đã bị xóa; bảng oracle cũng phải được sửa.
- **Đổi thứ tự hằng số**: `values()` có thứ tự khai báo mới và `ordinal()` thay đổi. Không dùng ordinal làm khóa lưu trữ bền vững hoặc mã nghiệp vụ.
- **Thêm `default` vô điều kiện**: không còn bắt buộc cập nhật case cụ thể khi enum phát triển; lúc này kiểm tra domain-oracle độc lập càng quan trọng.

**Cảnh báo về binary không đồng bộ:** đảm bảo exhaustiveness tại thời điểm biên dịch không bảo đảm mọi binary biên dịch từ phiên bản enum cũ vẫn xử lý được một constant mới từ dependency thay đổi mà chưa được biên dịch lại. Các dự án đa module nên build lại module phụ thuộc và chạy test sau khi thay đổi domain enum.

## 9. Cách dùng `@EnumSource` trong JUnit 5

Trong dự án dùng JUnit Jupiter, `@EnumSource` hỗ trợ chạy một test theo từng constant. Đây là **ví dụ test riêng, cần JUnit 5 với module `junit-jupiter-params` trên test classpath**; không phải một phần của chương trình Java SE ở mục 6.

Tạo `EnumDomainCoverageTest.java` trong cùng package với `EnumDomainCoverageDemo`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

class EnumDomainCoverageTest {
    @ParameterizedTest
    @EnumSource(EnumDomainCoverageDemo.TaskState.class)
    void everyConstantHasExpectedDecision(
            EnumDomainCoverageDemo.TaskState state) {

        var expected = Map.of(
            EnumDomainCoverageDemo.TaskState.NEW,
                new EnumDomainCoverageDemo.Decision("QUEUED", false),
            EnumDomainCoverageDemo.TaskState.RUNNING,
                new EnumDomainCoverageDemo.Decision("IN_PROGRESS", false),
            EnumDomainCoverageDemo.TaskState.DONE,
                new EnumDomainCoverageDemo.Decision("SUCCESS", true),
            EnumDomainCoverageDemo.TaskState.FAILED,
                new EnumDomainCoverageDemo.Decision("ERROR", true)
        );

        assertEquals(expected.get(state),
                EnumDomainCoverageDemo.decide(state));
    }

    @Test
    void nullHasItsOwnPolicy() {
        assertEquals(
            new EnumDomainCoverageDemo.Decision("NO_STATE", false),
            EnumDomainCoverageDemo.decide(null)
        );
    }
}
```

`@EnumSource` cung cấp tất cả constants hiện tại mặc định, nên khi có thêm enum constant, test sẽ nhận thêm lượt chạy. Map kỳ vọng viết độc lập với `decide`; nếu chưa bổ sung expectation cho constant mới, `expected.get(state)` trả null và phép `assertEquals` sẽ không khớp với `Decision` thực tế.

**Giới hạn:** `@EnumSource` mặc định không cung cấp null. Hãy dùng một `@Test` riêng như trên, hoặc cấu hình nguồn dữ liệu bổ sung nếu muốn bao phủ cả null. Không coi một test `assertNotNull(decide(state))` là đủ vì nó không xác nhận ý nghĩa nghiệp vụ.

### Test data nên gắn với đặc tả, không sao chép implementation

Nếu viết expected bằng một `switch` thứ hai có cùng mapping được sao chép từ implementation, hai vị trí có thể cùng mang một lỗi. Khi có thể, dùng bảng acceptance criteria, yêu cầu sản phẩm, ví dụ có tên hoặc mẫu input-output đã thống nhất để xây dựng oracle.

`EnumMap` thích hợp trong self-test, còn `Map.of` trong ví dụ JUnit giúp bảng ngắn gọn. Cả hai cần cập nhật khi enum domain biến đổi.

## 10. Enum constants và type pattern trong `switch` là hai việc khác nhau

Trong một `switch` mà selector có kiểu **`TaskState`**, có thể dùng:

```java
case NEW -> ...
case RUNNING -> ...
case DONE -> ...
case FAILED -> ...
```

Các nhãn này phân biệt **những hằng enum cụ thể**.

Nếu selector có kiểu tĩnh **`Object`**, Java 21 có thể dùng một **type pattern** để nhận nhóm đối tượng thuộc enum trước:

```java
static String inspect(Object input) {
    return switch (input) {
        case null -> "NULL";
        case TaskState state -> decide(state).label();
        default -> "NOT_TASK_STATE";
    };
}
```

Đây là **phương thức minh họa** đặt bên trong class có `TaskState` và `decide`. Nhánh `case TaskState state` chỉ chứng minh input là một `TaskState` non-null. Nó **không tự kiểm thử đủ bốn constant**; muốn phân biệt từng trạng thái, `decide(state)` vẫn cần đầy đủ case hoặc bảng mapping thích hợp.

Điều này nối chủ đề **enum và constant** với **pattern matching**: type pattern nhận biết một loại dữ liệu, còn enum constant labels phân biệt các giá trị nằm bên trong loại đó. Đừng nhầm một test “đã đi qua case TaskState” với việc “đã test toàn bộ domain của TaskState”.

## 11. Những trường hợp cần thêm test ngoài enum domain

Ngoài việc chạy tất cả constants, ứng dụng có thể nhận dữ liệu bên ngoài và chuyển thành enum. Khi đó nên kiểm thử cả **biên giao tiếp**:

### Chuyển đổi từ chuỗi

```java
TaskState parsed = TaskState.valueOf("DONE"); // DONE
```

`Enum.valueOf` dùng tên khai báo **chính xác**, có phân biệt chữ hoa/chữ thường; `"done"` không hợp lệ nếu không có xử lý chuẩn hóa riêng. Tên không tồn tại thường gây `IllegalArgumentException`, còn đối số chuỗi `null` gây `NullPointerException`. Đây là hành vi phải test nếu API nhận dữ liệu chuỗi không đáng tin cậy.

Nếu muốn chấp nhận `"done"`, hãy quyết định rõ quy tắc chuẩn hóa, chẳng hạn `toUpperCase(Locale.ROOT)`, và test khoảng trắng đầu/cuối cùng trường hợp không hợp lệ. Không suy ra `name()` hoặc `toString()` luôn là định dạng API ổn định về lâu dài nếu enum có thể bị đổi tên.

### Lưu trữ dữ liệu

Không dựa vào `ordinal()` để mã hóa trạng thái trong database hoặc giao thức mạng: thêm hoặc sắp xếp lại enum constants làm ordinal đổi. Nếu phải lưu, hãy dùng mã nghiệp vụ rõ, có chính sách tương thích và kiểm thử round-trip cho mã đó.

### Mapping hai chiều

Khi vừa có `TaskState -> String` vừa có `String -> TaskState`, hãy kiểm tra cả chiều mã hóa, giải mã và các giá trị không hợp lệ. Một chiều thành công không bảo đảm chiều kia đã hoàn toàn tương thích, đặc biệt với fallback/alias/tên lịch sử.

## 12. Ma trận kiểm thử và chiến lược coverage

| Mục kiểm tra | Input đại diện | Kỳ vọng | Loại bảo đảm |
| --- | --- | --- | --- |
| Mỗi constant có mapping | `NEW`, `RUNNING`, `DONE`, `FAILED` | Đúng `Decision` từng trạng thái | Unit test runtime |
| Oracle đủ domain | Tập khóa expected so với `EnumSet.allOf` | Hai tập bằng nhau | Test cấu hình/đặc tả |
| Vòng lặp không sót | `TaskState.values()` | Số ca chạy bằng kích thước domain | Kiểm soát độ bao phủ |
| `null` theo hợp đồng | `decide(null)` | `NO_STATE` | Unit test ngoại lệ miền enum |
| Round-trip tên | `valueOf(state.name())` | Cùng constant | API enum runtime |
| Tên lạ | `valueOf("UNKNOWN")` | `IllegalArgumentException` | Test đầu vào không hợp lệ |
| Thêm constant và thiếu case | Thêm `CANCELLED`, chưa cập nhật switch | Lỗi compile nếu không default | Exhaustiveness tĩnh |
| Mapping sai dù đủ case | Hoán đổi kết quả `DONE` và `FAILED` | Test oracle phát hiện | Unit test ngữ nghĩa |
| Sử dụng fallback | Một constant bị đưa vào `default` | Chỉ hợp lệ nếu đúng đặc tả | Review + test |
| Đầu vào kiểu `Object` | `TaskState` và đối tượng khác kiểu | Đúng type pattern/fallback | Integration unit test |

**Không đồng nhất các khái niệm coverage:** mã hóa một `switch` exhaustive cho enum đảm bảo đầy đủ **về mặt case selection** ở compile time, nhưng không chứng minh branch trả dữ liệu đúng, không kiểm tra hợp đồng null hoặc khả năng tích hợp với đầu vào từ hệ thống khác.

## 13. Lỗi thường gặp

| Sai lầm | Vì sao không đủ/sai | Hướng khắc phục |
| --- | --- | --- |
| Chỉ test `TaskState.NEW` | Không chạy các enum constant khác | Duyệt `values()` hoặc `@EnumSource` |
| Lặp `values()` rồi chỉ `assertNotNull` | Không biết ánh xạ có đúng không | So sánh mỗi constant với oracle độc lập |
| Expected tính bằng chính `decide(state)` | Test tự chứng minh điều nó đang kiểm tra | Viết expectation từ đặc tả |
| Chỉ so sánh `expected.size()` với số constant | Hai tập bằng số lượng nhưng khác thành viên vẫn lọt | So sánh tập khóa với `EnumSet.allOf` |
| Quên `case null` nhưng cho rằng `default` sẽ nhận null | Có thể ném `NullPointerException` | Test null riêng và chọn chính sách rõ ràng |
| Cứ thêm `default` để compiler hết lỗi | Có thể che hằng mới bị quên | Cân nhắc exhaustive switch không default |
| Chỉ dựa vào exhaustive compile | Không phát hiện mapping nhầm nhãn | Unit test kết quả cụ thể |
| Dùng `ordinal()` trong dữ liệu bền vững | Giá trị đổi khi sắp xếp enum | Dùng mã nghiệp vụ ổn định |
| Cho rằng `@EnumSource` có `null` | Null không phải enum constant | Viết test null riêng |
| Không cấu hình `junit-jupiter-params` | Test `@ParameterizedTest`/`@EnumSource` không chạy đúng | Thêm dependency/config JUnit Jupiter |
| Dùng `assert` mà không bật `-ea` | Self-test có thể âm thầm không kiểm tra | Dùng `AssertionError` tường minh hoặc JUnit |
| Quên build lại module phụ thuộc khi enum đổi | Mã client có thể không đồng bộ với enum mới | Rebuild và chạy test toàn bộ module liên quan |
| Đổi tên enum constant mà không xử lý dữ liệu cũ | `valueOf` không phân giải tên đã bỏ | Chính sách migration/alias và test tương thích |
| Nghĩ `case TaskState state` bao phủ việc test mọi constant | Type pattern chỉ phân biệt loại `TaskState` với các loại khác | Bổ sung test từng constant và các nhánh mapping |

## 14. Bài tập thực hành

1. Tạo `enum OrderStatus { CREATED, PAID, SHIPPED, DELIVERED, CANCELLED }`. Viết `switch` expression trả về nhãn hiển thị cho từng hằng **không có default**. Tạo bảng oracle riêng, dùng `values()` để test toàn bộ domain.
2. Với `OrderStatus`, viết thêm `isTerminal()` trả `boolean`: `DELIVERED` và `CANCELLED` phải là terminal, các trạng thái khác không phải. Test cả nhãn và cờ terminal thay vì chỉ một giá trị.
3. Thêm `RETURNED` vào enum, giữ nguyên `switch` cũ không default và biên dịch. Ghi lại lỗi exhaustiveness; bổ sung case mới.
4. Sau khi sửa `switch`, cố tình quên thêm `RETURNED` vào oracle. Chạy kiểm tra tập khóa để chứng minh domain test phát hiện thiếu expectation.
5. Đổi mapping `PAID` sang nhãn của `SHIPPED` mà vẫn giữ đủ case. Quan sát compiler vẫn chấp nhận nhưng unit test báo sai giá trị.
6. Viết `switch` có `default -> "UNKNOWN"` và so sánh lợi/hại với bản không default khi enum được thêm constant.
7. Viết test riêng cho `null`: trường hợp API chấp nhận null và trường hợp API chủ động ném lỗi. Chỉ chọn một chính sách cho mã sản xuất.
8. Dùng `@EnumSource(OrderStatus.class)` trong JUnit Jupiter để tự sinh các lượt test, rồi dùng expectation độc lập so sánh.
9. Tạo một hàm parser nhận tên trạng thái từ request. Test tên hợp lệ, khác chữ hoa/chữ thường, chuỗi rỗng, tên lạ và null; nêu chính sách khi trạng thái được đổi tên.
10. Đổi thứ tự khai báo enum, so sánh `values()` và `ordinal()`. Giải thích vì sao test business logic nên dựa trên hằng và mã ổn định, không dựa vào vị trí enum.
11. Viết `switch(Object input)` với `case OrderStatus status`; chứng minh nhánh này nhận đúng loại nhưng không tự thay thế test cho mọi enum constant.
12. Chạy `EnumDomainCoverageDemo`, đối chiếu toàn bộ 7 dòng stdout và sửa một expectation có chủ đích để thấy `AssertionError` làm test thất bại.

**Đạt bài học khi:** thiết kế được test chạy tất cả enum constants, có oracle độc lập, xác nhận tập kỳ vọng bằng enum domain, hiểu tác dụng của exhaustive `switch` không default, và test riêng `null`/dữ liệu đầu vào ngoài domain.

**Tài liệu tham khảo:**

- [Java SE 21 API — `Enum`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html).
- [Java SE 21 API — `EnumSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/EnumSet.html).
- [Java SE 21 API — `EnumMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/EnumMap.html).
- [Java Language Specification 21 — Enum Classes (§8.9)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9).
- [JLS 21 — Switch Expressions (§15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [JUnit 5 — Parameterized Tests (`@EnumSource`)](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests-sources-EnumSource).
