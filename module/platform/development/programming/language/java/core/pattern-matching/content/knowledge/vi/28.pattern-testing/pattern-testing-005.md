# Kiểm thử từng subtype của sealed hierarchy trong Java 21

## 1. Vì sao một sealed hierarchy vẫn cần kiểm thử?

`sealed class` hoặc `sealed interface` cho phép Java giới hạn những kiểu được phép kế thừa/triển khai. Điều này đặc biệt hữu ích khi kết hợp **pattern matching cho `switch`**: compiler có thể dựa vào cấu trúc hierarchy đóng kín để kiểm tra `switch expression` hoặc enhanced `switch statement` đã **exhaustive** hay chưa.

Tuy vậy, **exhaustive không đồng nghĩa với logic đúng**:

- Compiler có thể chứng minh rằng mỗi subtype được một `case` nào đó bao phủ, nhưng không biết kết quả nghiệp vụ phải là gì.
- Một subtype có thể có **nhiều nhánh `when`**, mỗi nhánh cần kiểm tra giá trị biên.
- Constructor của record có thể chứa **validation** và phải được kiểm tra riêng.
- `case null`, record component null hoặc dữ liệu không hợp lệ có hành vi riêng, không thể suy ra chỉ từ `permits`.
- Khi thêm một subtype hoặc thay đổi hierarchy, ta cần bảo vệ cả **khả năng biên dịch** lẫn **tập test runtime**.

Vì vậy, mục tiêu của bài là lập **ma trận kiểm thử từng subtype lá (*leaf subtype*)**, kiểm tra nhánh chính, guard, giá trị biên, invariant, null và cấu trúc `permits`. Bài cũng chỉ ra cơ chế để phát hiện khi xuất hiện subtype mới mà bộ test chưa cập nhật.

**Phiên bản:** `sealed` là tính năng chính thức từ Java 17 (JEP 409). Pattern matching cho `switch` (JEP 441) và record patterns (JEP 440) là tính năng chính thức từ **Java 21**. Chương trình đầy đủ trong bài dùng **JDK 21 trở lên**, với lệnh `javac --release 21`, không cần `--enable-preview`.

Sau bài học, bạn có thể:
1. Phân biệt **subtype trực tiếp** với **subtype lá** trong hierarchy nhiều cấp.
2. Thiết kế test cho từng biến thể và từng nhánh guard của một `switch`.
3. Dùng test bảng dữ liệu, test exception và test reflection của `getPermittedSubclasses()`.
4. Biết chính xác compiler bảo đảm được gì, và điều gì vẫn phải kiểm thử.
5. Bảo trì test khi thêm, xóa, đổi tên hoặc chuyển nhánh của subtype.

## 2. Ví dụ domain: một cây sealed hierarchy hai cấp

Giả sử hệ thống nhận các lệnh:

```text
Command (sealed interface)
├── OrderCommand (sealed interface)
│   ├── Submit(id, items)     (record)
│   └── Cancel(id)            (record)
└── SystemCommand (sealed interface)
    ├── Retry(job, attempt)   (record)
    └── Abort(job, code)      (record)
```

Các kiểu được khai báo như sau:

```java
// Khai báo minh họa, chương trình hoàn chỉnh ở phần 5.
sealed interface Command permits OrderCommand, SystemCommand {}

sealed interface OrderCommand extends Command
        permits Submit, Cancel {}

sealed interface SystemCommand extends Command
        permits Retry, Abort {}

record Submit(String id, int items) implements OrderCommand {}
record Cancel(String id) implements OrderCommand {}
record Retry(String job, int attempt) implements SystemCommand {}
record Abort(String job, int code) implements SystemCommand {}
```

Phân biệt hai cấp kiểm thử:

- **Cấp nhánh lớn:** `Command` cho phép trực tiếp `OrderCommand` và `SystemCommand`. Nếu một method phân loại theo nhánh cha, cần kiểm tra đại diện cả hai nhóm.
- **Cấp lá:** `Submit`, `Cancel`, `Retry`, `Abort` là các record `final`. Khi `switch` giải cấu trúc từng subtype, cần test **từng kiểu lá**, không chỉ test một `OrderCommand` và một `SystemCommand`.

`permits` của root liệt kê **subtype trực tiếp**, không tự liệt kê tất cả record lá ở các cấp sâu hơn. Vì vậy test chỉ hỏi `Command.class.getPermittedSubclasses()` sẽ thấy hai interface trung gian; muốn kiểm tra cả bốn lá, phải tiếp tục kiểm tra các nhánh trung gian hoặc duyệt đệ quy.

### Hai kiểu pattern trong cùng domain

Một phép phân loại cấp nhánh cha có thể dùng **type patterns**:

```java
static String group(Command command) {
    return switch (command) {
        case OrderCommand ignored -> "ORDER";
        case SystemCommand ignored -> "SYSTEM";
        case null -> "NONE";
    };
}
```

Trong khi đó, một phép xử lý chi tiết dùng **record patterns**:

```java
// Các case minh họa bên trong một switch expression.
case Submit(String id, int items) when items == 0 ->
    "SUBMIT_EMPTY:" + id;
case Submit(String id, int items) ->
    "SUBMIT:" + id + ":" + items;
```

Từ góc nhìn test, hai method có nhu cầu khác nhau: `group` cần kiểm tra các **nhóm cha**, còn `describe` cần kiểm tra **từng kiểu lá và điều kiện guard**.

## 3. Tách ba lớp bảo đảm: compiler, test runtime và test cấu trúc

### 3.1. Compiler kiểm tra type hierarchy và exhaustiveness

Với sealed hierarchy đóng kín, một `switch` đã có case phù hợp cho tất cả các lá có thể được compiler đánh giá là exhaustive. Nếu thêm một subtype lá và thiếu case tương ứng, `javac` có thể báo lỗi khi biên dịch lại.

Đây là kiểm tra **ở cấp kiểu**, không phải chứng minh rằng mỗi output hay mỗi nhánh nghiệp vụ đúng.

### 3.2. Runtime tests kiểm tra dữ liệu và kết quả

Test cần xác nhận:
- Đầu vào cụ thể thuộc subtype nào?
- Output của case tương ứng có đúng không?
- Guard ở ngưỡng đúng hay sai?
- Constructor có từ chối trạng thái không hợp lệ không?
- Selector null có được xử lý đúng theo contract không?

Compiler không biết rằng `Retry(job, 3)` phải được gắn nhãn `RETRY_ESCALATE` hay `Abort(job, 500)` phải là `ABORT_CRITICAL`: đây là quy tắc nghiệp vụ do test bảo vệ.

### 3.3. Reflection tests bảo vệ danh sách subtype mà ta kỳ vọng

API `Class::isSealed` và `Class::getPermittedSubclasses` giúp kiểm tra hierarchy trực tiếp ở runtime. Test có thể so sánh tập Class được permit với tập Class mong đợi.

Lợi ích:
- Thấy ngay khi một subtype được thêm hoặc chuyển nhánh mà test chưa cập nhật danh sách.
- Kiểm tra kiểu trung gian vẫn giữ `sealed` đúng thiết kế.
- Độc lập với việc một `switch` riêng có vô tình dùng `default` và che nhánh mới hay không.

**Giới hạn:** Reflection test không chứng minh từng guard đã được kiểm tra; danh sách subtype và test case phải được thiết kế bổ sung cho nhau.

## 4. Thiết kế test matrix trước khi code

Với handler trả về chuỗi, lập bảng kiểm thử như sau:

| Leaf subtype/đầu vào | Nhánh cần kiểm tra | Expected output |
| --- | --- | --- |
| `Submit("O1", 0)` | Guard `items == 0` | `SUBMIT_EMPTY:O1` |
| `Submit("O2", 2)` | Case `Submit` bình thường | `SUBMIT:O2:2` |
| `Cancel("O3")` | Case `Cancel` | `CANCEL:O3` |
| `Retry("J1", 2)` | Trước ngưỡng `attempt >= 3` | `RETRY:J1:2` |
| `Retry("J1", 3)` | Ngay tại ngưỡng guard | `RETRY_ESCALATE:J1` |
| `Abort("J2", 499)` | Trước ngưỡng `code >= 500` | `ABORT:J2:499` |
| `Abort("J2", 500)` | Ngay tại ngưỡng guard | `ABORT_CRITICAL:J2` |
| `null` | `case null` | `NULL` |

Bảng cho thấy **một test cho mỗi subtype chưa chắc đủ**: `Submit` có nhánh rỗng và không rỗng; `Retry` và `Abort` có ngưỡng guard. Cần ít nhất một test cho mỗi kết quả kỳ vọng, và kiểm tra ở hai phía của ranh giới.

**Đừng chỉ test ví dụ “đẹp”:** Đối với `attempt >= 3`, một test với `attempt = 10` chỉ chứng minh giá trị rất lớn được xử lý, còn lỗi dùng `> 3` thay cho `>= 3` có thể lọt. Cặp `2/3` trực tiếp bắt lỗi biên. Đối với mã lỗi `>= 500`, cặp `499/500` tương tự.

Ma trận tối thiểu còn cần các nhóm ngoài happy path:
- `null` ở selector `Command`.
- ID rỗng/blank/null; số item âm; số attempt âm nếu constructor cấm.
- Nhánh cha `OrderCommand` và `SystemCommand`.
- Tập subtype trực tiếp theo `permits` ở mỗi nút sealed.
- Khi thêm một leaf mới: cả compiler, reflection test và runtime test phải được cập nhật.

## 5. Chương trình Java 21 hoàn chỉnh: 17 phép kiểm thử

Bài dùng một test harness nhỏ từ Java SE, **không cần JUnit**. Mỗi test thành công in `PASS ...`; nếu khác expected, code ném `AssertionError` khiến chương trình không hoàn tất bình thường. Cách này giúp thử nhanh trong một file và có kết quả đáng tin ngay cả khi không bật cờ `-ea`.

Tạo file **`SealedSubtypeTestsDemo.java`**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class SealedSubtypeTestsDemo {
    sealed interface Command permits OrderCommand, SystemCommand {}
    sealed interface OrderCommand extends Command permits Submit, Cancel {}
    sealed interface SystemCommand extends Command permits Retry, Abort {}

    static void requireId(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("blank id");
        }
    }

    record Submit(String id, int items) implements OrderCommand {
        Submit {
            requireId(id);
            if (items < 0) {
                throw new IllegalArgumentException("negative items");
            }
        }
    }

    record Cancel(String id) implements OrderCommand {
        Cancel {
            requireId(id);
        }
    }

    record Retry(String job, int attempt) implements SystemCommand {
        Retry {
            requireId(job);
            if (attempt < 0) {
                throw new IllegalArgumentException("negative attempt");
            }
        }
    }

    record Abort(String job, int code) implements SystemCommand {
        Abort {
            requireId(job);
        }
    }

    static String describe(Command command) {
        return switch (command) {
            case Submit(String id, int items) when items == 0 ->
                "SUBMIT_EMPTY:" + id;

            case Submit(String id, int items) ->
                "SUBMIT:" + id + ":" + items;

            case Cancel(String id) ->
                "CANCEL:" + id;

            case Retry(String job, int attempt) when attempt >= 3 ->
                "RETRY_ESCALATE:" + job;

            case Retry(String job, int attempt) ->
                "RETRY:" + job + ":" + attempt;

            case Abort(String job, int code) when code >= 500 ->
                "ABORT_CRITICAL:" + job;

            case Abort(String job, int code) ->
                "ABORT:" + job + ":" + code;

            case null -> "NULL";
        };
    }

    static String group(Command command) {
        return switch (command) {
            case OrderCommand ignored -> "ORDER";
            case SystemCommand ignored -> "SYSTEM";
            case null -> "NONE";
        };
    }

    static int tests = 0;

    static void expect(String name, String expected, String actual) {
        tests++;
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                name + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println("PASS " + name);
    }

    static void expectIllegalArgument(String name, Runnable action) {
        tests++;
        try {
            action.run();
        } catch (IllegalArgumentException ex) {
            System.out.println("PASS " + name);
            return;
        }
        throw new AssertionError(
            name + ": expected IllegalArgumentException");
    }

    static void expectPermits(
            String name, Class<?> type, Set<Class<?>> expected) {
        tests++;
        if (!type.isSealed()) {
            throw new AssertionError(name + ": type must be sealed");
        }

        Set<Class<?>> actual =
            new HashSet<>(Arrays.asList(type.getPermittedSubclasses()));

        if (!expected.equals(actual)) {
            throw new AssertionError(
                name + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        expectPermits("root-permits", Command.class,
            Set.of(OrderCommand.class, SystemCommand.class));
        expectPermits("order-permits", OrderCommand.class,
            Set.of(Submit.class, Cancel.class));
        expectPermits("system-permits", SystemCommand.class,
            Set.of(Retry.class, Abort.class));

        expect("submit-empty", "SUBMIT_EMPTY:O1",
            describe(new Submit("O1", 0)));
        expect("submit-positive", "SUBMIT:O2:2",
            describe(new Submit("O2", 2)));
        expect("cancel", "CANCEL:O3",
            describe(new Cancel("O3")));
        expect("retry-before-boundary", "RETRY:J1:2",
            describe(new Retry("J1", 2)));
        expect("retry-at-boundary", "RETRY_ESCALATE:J1",
            describe(new Retry("J1", 3)));
        expect("abort-before-boundary", "ABORT:J2:499",
            describe(new Abort("J2", 499)));
        expect("abort-at-boundary", "ABORT_CRITICAL:J2",
            describe(new Abort("J2", 500)));

        expect("group-order", "ORDER", group(new Cancel("O4")));
        expect("group-system", "SYSTEM", group(new Retry("J3", 1)));
        expect("null-describe", "NULL", describe(null));
        expect("null-group", "NONE", group(null));

        expectIllegalArgument("invalid-id",
            () -> new Submit(" ", 1));
        expectIllegalArgument("invalid-items",
            () -> new Submit("O5", -1));
        expectIllegalArgument("invalid-attempt",
            () -> new Retry("J4", -1));

        System.out.println("TOTAL=" + tests);
    }
}
```

Biên dịch và chạy từ thư mục chứa file bằng **JDK 21 trở lên**:

```bash
javac --release 21 SealedSubtypeTestsDemo.java
java SealedSubtypeTestsDemo
```

Kết quả stdout chính xác:

```text
PASS root-permits
PASS order-permits
PASS system-permits
PASS submit-empty
PASS submit-positive
PASS cancel
PASS retry-before-boundary
PASS retry-at-boundary
PASS abort-before-boundary
PASS abort-at-boundary
PASS group-order
PASS group-system
PASS null-describe
PASS null-group
PASS invalid-id
PASS invalid-items
PASS invalid-attempt
TOTAL=17
```

Chương trình này vừa là một ví dụ đầy đủ, vừa là bộ kiểm tra nhỏ. Nó dùng `Objects.equals` để so output, bắt đúng `IllegalArgumentException` khi kỳ vọng validation thất bại, và dùng reflection để kiểm tra chính xác các nhánh được phép trong hierarchy. Không có dependency ngoài Java SE.

## 6. Giải thích các nhóm kiểm thử

### 6.1. Kiểm tra `permits` ở cả ba nút sealed

`expectPermits("root-permits", Command.class, ...)` bảo vệ cấu trúc trực tiếp của `Command`. Hai phép gọi tiếp theo bảo vệ cấu trúc trực tiếp của `OrderCommand` và `SystemCommand`.

Bên trong helper:

```java
if (!type.isSealed()) {
    throw new AssertionError(name + ": type must be sealed");
}
Set<Class<?>> actual =
    new HashSet<>(Arrays.asList(type.getPermittedSubclasses()));
```

`getPermittedSubclasses()` chỉ trả **các subtype trực tiếp** được phép, không phải danh sách đệ quy mọi lá. Dùng `Set` thay vì so thứ tự mảng giúp test tập kiểu mà không vô tình phụ thuộc vào thứ tự trình bày.

Phép so `expected.equals(actual)` kiểm tra **chính xác** tập được cho phép, không chỉ số lượng. Nếu thay `Cancel` bằng một subtype khác nhưng tổng số vẫn bằng hai, test vẫn phát hiện sự khác biệt.

**Giới hạn về chiến lược:** Test này cố ý yêu cầu cập nhật khi thiết kế hierarchy đổi. Một subtype mới không nhất thiết là bug; fail ở đây nhắc đội phát triển review các handler và bổ sung test. Không nên tự động “sửa” bằng cách lấy chính kết quả reflection làm expected, vì khi đó phép kiểm tra không còn phát hiện thay đổi.

### 6.2. Kiểm thử từng subtype lá

Trong ví dụ có bốn kiểu lá:

- `Submit`: hai test cho trường hợp `items == 0` và `items > 0`.
- `Cancel`: một test cho nhánh độc lập.
- `Retry`: hai test cho trước ngưỡng và tại ngưỡng `attempt >= 3`.
- `Abort`: hai test cho trước ngưỡng và tại ngưỡng `code >= 500`.

Điều này khác với việc chỉ test `group(new Submit(...))` và `group(new Retry(...))`: cách sau chỉ chứng minh hai **nhánh cha**, chưa chứng minh `Cancel` hay `Abort` được mô tả đúng.

### 6.3. Kiểm thử parent type patterns

`group` dùng `case OrderCommand ignored` và `case SystemCommand ignored`. Hai test `group-order` và `group-system` kiểm tra một đại diện cho mỗi nhánh lớn; `null-group` kiểm tra `case null`.

Với một hàm chỉ phân loại nhánh cha, hai test đại diện có thể đủ cho logic riêng của method. Nhưng nếu muốn bảo đảm **mọi leaf subtype** được route đúng, bổ sung test `group` với cả `Submit`, `Cancel`, `Retry`, `Abort`. Việc quyết định mức coverage tùy contract của method: không nên nhầm coverage cấp cha với coverage cấp lá.

### 6.4. Kiểm thử input không hợp lệ

Các record có constructor kiểm tra:
- ID không được null/rỗng/trắng.
- `Submit.items` không được âm.
- `Retry.attempt` không được âm.

`expectIllegalArgument` gọi một `Runnable` và yêu cầu **đúng kiểu** `IllegalArgumentException`. Nếu code không ném exception, helper sẽ ném `AssertionError`. Nếu ném kiểu khác, test cũng thất bại vì helper chỉ catch `IllegalArgumentException`.

Đây là cách kiểm tra **domain invariant** của từng subtype. Một hierarchy exhaustive không tự bảo đảm dữ liệu của record hợp lệ.

### 6.5. Kiểm thử null của selector

`describe(null)` và `group(null)` có hai test riêng. Hai method có `case null`, lần lượt trả `NULL` và `NONE`.

Đừng mặc định `default` bắt selector null. Nếu switch pattern cần cho phép null, hãy thiết kế `case null` hoặc kiểm tra ở boundary. Nếu contract yêu cầu không có null, dùng validation như `Objects.requireNonNull` và test exception tương ứng.

## 7. Exhaustiveness không thay thế kiểm tra từng nhánh when

Xét ba case liên tiếp:

```java
case Retry(String job, int attempt) when attempt >= 3 ->
    "RETRY_ESCALATE:" + job;
case Retry(String job, int attempt) ->
    "RETRY:" + job + ":" + attempt;
```

Compiler nhìn thấy case `Retry` **không guard** ở cuối nên có thể kết luận mọi `Retry` hợp lệ đều được bao phủ. Nhưng nó không chứng minh điều kiện `attempt >= 3` phản ánh đúng yêu cầu nghiệp vụ.

Vì vậy test phải kiểm tra ít nhất:
- **Ngay trước ngưỡng:** `attempt = 2`.
- **Ngay tại ngưỡng:** `attempt = 3`.
- **Sau ngưỡng:** có thể thêm `attempt = 4` để tăng niềm tin.
- **Dữ liệu không hợp lệ:** nếu âm bị cấm, test `attempt = -1` ngay tại constructor.

Tương tự, `Abort` có mốc `code >= 500`; `499` và `500` là cặp biên nên được ưu tiên. Nếu logic thật dùng nhiều khoảng mã lỗi, nên chia tương ứng từng nhánh `when`.

**Nguyên tắc:** Kiểm thử không chỉ theo số subtype; cần theo **các đường đi có ý nghĩa** bên trong mỗi subtype. Đếm một test cho mỗi class mà bỏ qua guard, validation và fallback sẽ tạo cảm giác bao phủ giả.

## 8. Khi thêm subtype: compiler và test cần phối hợp

Giả sử thêm một kiểu `Pause` thuộc `SystemCommand`:

```java
// Đoạn minh họa thay đổi hierarchy, không thêm độc lập
// vào file phần 5 nếu chưa cập nhật toàn bộ nơi liên quan.
sealed interface SystemCommand extends Command
        permits Retry, Abort, Pause {}

record Pause(String job) implements SystemCommand {}
```

Hệ quả cần xem xét:

1. `SystemCommand` phải cho phép trực tiếp `Pause` qua `permits`.
2. `group` vẫn có case `SystemCommand ignored` nên xử lý được `Pause` ở cấp nhánh cha mà không cần case riêng.
3. `describe` chỉ có case cho `Submit`, `Cancel`, `Retry`, `Abort`, vì vậy compiler có thể báo **switch expression không exhaustive** sau khi thêm leaf mới và biên dịch lại.
4. Test `system-permits` đang kỳ vọng tập `Retry`/`Abort`; khi có `Pause`, test sẽ thất bại cho tới khi expected được cập nhật.
5. Đội phát triển phải thêm test `describe(new Pause(...))` và các guard/invariant liên quan; chỉ thêm case để code biên dịch không bảo đảm behavior đã được test đúng.

Đây là quy trình hữu ích: **compile failure nhắc cập nhật handler**, còn **reflection test nhắc cập nhật ma trận test và review hierarchy**.

### Có nên thêm default để cho build qua?

Nếu mục tiêu là xử lý tường minh từng biến thể của một sealed hierarchy, không nên vội thêm:

```java
// Minh họa một fallback có thể che thiếu sót:
default -> "OTHER";
```

Một `default` rộng có thể làm switch vẫn exhaustive khi xuất hiện subtype mới, khiến compiler không còn nhắc nơi cần logic riêng. Tuy nhiên, `default` là lựa chọn hợp lệ nếu contract thực sự quy định mọi subtype còn lại phải xử lý giống nhau. Quyết định dựa trên yêu cầu, không dựa vào việc tránh diagnostic.

### Kiểm thử thay đổi ở module khác

Trong hệ thống multi-module, nếu subtype và consumer được build/deploy riêng, cần kiểm thử trên **tập artifact tương thích**. Một switch cũ đã biên dịch theo hierarchy trước đó có thể phát sinh lỗi ở runtime với thay đổi không tương thích (trong một số hoàn cảnh có thể có `MatchException`). CI nên biên dịch và chạy test các consumer với dependency version thực sự được triển khai, không chỉ source của một module cô lập.

## 9. Làm thế nào để đo coverage mà không hiểu sai?

**Line coverage** đo số dòng đã chạy; **branch coverage** đo nhánh điều khiển; nhưng không một con số duy nhất nào đồng nghĩa với “đã test hết domain”.

Với sealed hierarchy, cần xem ít nhất bốn lớp:

| Lớp coverage | Câu hỏi | Cách chứng minh |
| --- | --- | --- |
| **Type coverage** | Mọi leaf subtype đã có test? | Danh sách leaf/test case và kiểm tra `permits` |
| **Pattern-case coverage** | Mỗi case cần thiết được thực thi? | Test output cho từng record pattern và guard |
| **Boundary coverage** | Guard có test ở cả hai phía? | Các cặp `2/3`, `499/500`, số 0 |
| **Invariant/negative coverage** | Dữ liệu sai bị từ chối đúng? | Test constructor, exception, null và input biên |

Các công cụ như JaCoCo có thể đo line/branch coverage, nhưng bản báo cáo coverage không thay thế **ma trận subtype**. Ví dụ một test `Retry(100)` có thể chạy case escalate nhưng không chứng minh ranh giới 3 đúng. Tương tự, toàn bộ các dòng trong `group` được chạy không chứng minh tất cả leaf subtype có đúng behavior riêng.

**Mutation testing** có thể bổ sung giá trị: nếu đổi `>= 3` thành `> 3` mà test vẫn xanh, bộ test thiếu giá trị biên. Nếu bỏ case `Cancel` mà compiler đã báo non-exhaustive, đó là kiểm tra compile-time, không cần một runtime test để chứng minh lỗi cú pháp.

## 10. Mở rộng sang JUnit và parameterized tests

Đối với codebase thực tế, có thể đưa các case trong phần 5 sang **JUnit 5 (Jupiter)**; tuy nhiên JUnit là dependency ngoài JDK, nên các đoạn bên dưới là **minh họa test framework**, không phải chương trình độc lập. Cần khai báo dependency Jupiter và cấu hình Maven/Gradle/test runner phù hợp trong dự án.

Một test theo bảng dữ liệu có thể dùng `@ParameterizedTest` và `@MethodSource`:

```java
// Minh họa trong một test class đã import JUnit Jupiter.
// Không biên dịch riêng nếu thiếu dependency và type domain.
static java.util.stream.Stream<org.junit.jupiter.params.provider.Arguments>
describeCases() {
    return java.util.stream.Stream.of(
        org.junit.jupiter.params.provider.Arguments.of(
            new Submit("O1", 0), "SUBMIT_EMPTY:O1"),
        org.junit.jupiter.params.provider.Arguments.of(
            new Submit("O2", 2), "SUBMIT:O2:2"),
        org.junit.jupiter.params.provider.Arguments.of(
            new Cancel("O3"), "CANCEL:O3"),
        org.junit.jupiter.params.provider.Arguments.of(
            new Retry("J1", 2), "RETRY:J1:2"),
        org.junit.jupiter.params.provider.Arguments.of(
            new Retry("J1", 3), "RETRY_ESCALATE:J1"),
        org.junit.jupiter.params.provider.Arguments.of(
            new Abort("J2", 499), "ABORT:J2:499"),
        org.junit.jupiter.params.provider.Arguments.of(
            new Abort("J2", 500), "ABORT_CRITICAL:J2")
    );
}

@org.junit.jupiter.params.ParameterizedTest
@org.junit.jupiter.params.provider.MethodSource("describeCases")
void describeAllCases(Command input, String expected) {
    org.junit.jupiter.api.Assertions.assertEquals(
        expected, describe(input));
}
```

Tùy cấu trúc dự án, các type lồng trong `SealedSubtypeTestsDemo` phải được import bằng tên bao ngoài hoặc chuyển thành top-level types; ví dụ trên **giả định các type và `describe` đã ở trong phạm vi test**.

Lợi ích của test theo bảng:
- Dễ nhìn các subtype/guard nào đã có dữ liệu.
- Dễ bổ sung nhiều biến thể đầu vào.
- Tên test framework hiển thị trường hợp nào thất bại.
- Có thể tách data cases cho parser, mapping, formatter, domain service.

Nhưng đừng làm mất test `permits` và invariant khi chuyển sang framework. Tham số hóa chỉ là **cách tổ chức test cases**, không tự tạo coverage.

## 11. Null, record pattern lồng nhau và non-sealed: các góc khuất

### 11.1. Null của selector và null component khác nhau

`case null` xử lý **chính selector**. Nếu một record chứa nested record component, component null có thể làm record pattern lồng nhau **không khớp**, ngay cả khi record ngoài khác null. Ví dụ:

```java
// Chỉ minh họa, độc lập với Command của phần 5.
record Location(String city) {}
record UserEvent(Location location) {}

// event có kiểu Object:
boolean matched =
    event instanceof UserEvent(Location(String city));
```

Nếu `event` là `new UserEvent(null)` thì nested `Location(...)` không khớp; kết quả `matched` là `false`. Với một sealed hierarchy, switch được compiler cho là exhaustive dựa trên cấu trúc kiểu vẫn có thể gặp `MatchException` ở runtime nếu nested null khiến không có case nào phù hợp.

Đối với dữ liệu bắt buộc khác null, kiểm tra invariant ở constructor. Nếu null hợp lệ, tạo case/test riêng cho nó, chẳng hạn pattern component `var location` kèm guard `when location == null`, rồi mới tới nested patterns cụ thể.

### 11.2. Non-sealed mở tập biến thể

Một subtype trực tiếp của sealed type có thể là `non-sealed` để cho phép các lớp khác mở rộng. Trong trường hợp đó, tập các lớp lá không còn đóng kín: `getPermittedSubclasses()` trên root chỉ cho biết các nhánh trực tiếp được cho phép, **không** liệt kê mọi subtype có thể tồn tại bên dưới nhánh `non-sealed`.

Cách test phù hợp:
- Kiểm tra các implementation chính thức do dự án sở hữu.
- Có test cho **unknown/third-party implementation** nếu contract cho phép mở rộng.
- Nếu switch cần exhaustive, dùng type pattern bao phủ toàn bộ nhánh mở hoặc một fallback có chủ đích.
- Không tuyên bố test “mọi subtype trên thế giới” từ reflection ở root nếu hierarchy có phần mở.

### 11.3. Record không đồng nghĩa dữ liệu luôn hợp lệ

Record tự tạo constructor, accessor, `equals`, `hashCode` và `toString`, nhưng **không tự kiểm tra invariant nghiệp vụ**. Nếu component có kiểu tham chiếu, nó có thể null trừ khi constructor từ chối. Nếu component chứa đối tượng mutable, record không tự sao chép sâu.

Bộ test cho từng subtype nên dựa vào **contract thực tế**, không tự giả định mọi record đều immutable sâu hoặc non-null.

## 12. Quy trình kiểm thử trong dự án và CI

Một checklist thực tế:

1. **Liệt kê hierarchy:** Vẽ các nút sealed, final và non-sealed. Tách direct subtype khỏi leaf subtype.
2. **Định nghĩa contract của từng operation:** Method nào xử lý theo nhánh cha, method nào đọc dữ liệu lá và guard?
3. **Lập ma trận test:** Ít nhất một case cho mỗi leaf, thêm case cho từng guard và giá trị biên.
4. **Thêm invariant tests:** Record/class constructors phải xử lý dữ liệu sai theo đặc tả.
5. **Thêm null tests:** Selector và component null là hai tình huống khác nhau.
6. **Bảo vệ hierarchy:** Test `getPermittedSubclasses()` ở từng nút sealed quan trọng; so chính xác tập subtype dự kiến.
7. **Biên dịch toàn bộ consumer:** Để compiler kiểm tra những `switch` exhaustive khi có subtype mới.
8. **Chạy runtime tests và đo coverage:** Không dùng coverage % để thay thế ma trận nghiệp vụ.
9. **Review thay đổi API:** Khi hierarchy mới xuất hiện, cập nhật compile-time handlers, runtime fixtures, data mapper, serialization và test tương ứng.
10. **Kiểm thử build/deploy thực tế:** Đặc biệt khi các module được phát hành độc lập.

Ví dụ lệnh CI tối thiểu cho file standalone:

```bash
javac --release 21 -Xlint:all SealedSubtypeTestsDemo.java
java SealedSubtypeTestsDemo
```

Các kiểm thử dùng `AssertionError` nên **không cần `java -ea`**. Nếu một phép so sánh hoặc kiểm tra hierarchy thất bại, chương trình ném `AssertionError`, giúp job CI phát hiện test fail khi process thoát không thành công. Với JUnit, dùng runner/CI integration chính thức của dự án.

## 13. Lỗi thường gặp

| Lỗi | Vì sao không đủ | Cách khắc phục |
| --- | --- | --- |
| Chỉ test một đối tượng của mỗi nhánh cha | Có thể bỏ sót leaf sibling | Liệt kê từng leaf và tạo test riêng |
| Mỗi leaf chỉ có một happy path | Bỏ sót các guard và boundary | Test các ngưỡng và nhánh không guard |
| Tin rằng sealed + switch exhaustive tức là đúng nghiệp vụ | Compiler chỉ bảo đảm coverage kiểu | So expected output, exception và invariant |
| Chỉ kiểm tra `Command.getPermittedSubclasses()` | Chỉ thấy hai interface trực tiếp | Kiểm tra tiếp các nút sealed trung gian |
| Chỉ so số lượng subtype | Có thể thay một subtype mà số lượng không đổi | So chính xác tập Class mong đợi |
| Dùng `default` rộng để né lỗi compiler | Subtype mới không bị yêu cầu xử lý riêng | Chỉ dùng fallback khi contract cần |
| Quên `case null` hoặc null component | Có thể ném NPE/MatchException | Quy định null policy và test cụ thể |
| Test exception bằng `catch (Exception)` quá rộng | Lỗi ngoài dự kiến cũng khiến test xanh | Catch/assert đúng exception class |
| Dùng Java `assert` nhưng không bật `-ea` | Assertion có thể không chạy | Dùng JUnit assertions hoặc helper ném `AssertionError` |
| Dựa hoàn toàn vào coverage % | Có thể thiếu test biên | Ma trận subtype × guard × invariant |
| Thêm subtype nhưng không sửa test fixtures | Tập tests không phản ánh domain mới | Review `permits`, handler và mọi consumer |

## 14. Bài tập thực hành

**Bài tập 1 — Thêm test giá trị ngay sau ngưỡng.** Bổ sung `Retry("J1", 4)` và `Abort("J2", 501)`. Hai test này bắt được sai sót nào mà cặp `2/3` và `499/500` đã phát hiện, và tăng thêm độ tin cậy ở điểm nào?

**Bài tập 2 — Mở rộng subtype.** Thêm `record Pause(String job) implements SystemCommand`, cập nhật `permits`. Quan sát compile error của `describe`, cập nhật `expectPermits("system-permits", ...)` và thêm test cho `Pause`. So sánh với `group` — vì sao method phân loại nhánh cha không cần thay đổi?

**Bài tập 3 — Biến thể record mới có guard.** Thêm `Submit` có điều kiện mới như `items >= 100`, trả chuỗi `SUBMIT_BULK:<id>`. Đặt case có guard mới đúng thứ tự để không bị dominated. Viết test tại `99` và `100`, đồng thời xác minh case `items == 0` vẫn đúng.

**Bài tập 4 — Null trong record lồng nhau.** Tạo sealed hierarchy cho `UserEvent` có một record chứa `Location`. Cho phép hoặc cấm `location == null` một cách có chủ đích; thiết kế test để kiểm tra cả case nested record pattern và fallback khi null.

**Bài tập 5 — Thử mutation testing.** Sửa tạm `attempt >= 3` thành `attempt > 3`; chạy lại bộ test và ghi nhận case nào thất bại. Sau đó khôi phục code và thử sửa `code >= 500` thành `code > 500`.

## 15. Kết luận

Kiểm thử một **sealed hierarchy** không dừng ở việc compiler chấp nhận một `switch` exhaustive. Cần kiểm tra **mọi subtype lá**, các **guard và boundary**, **invariant**, **null**, và cấu trúc `permits` ở những nút sealed quan trọng.

Một chiến lược tốt kết hợp **compile-time exhaustiveness**, **reflection test bảo vệ tập subtype**, và **runtime tests với expected outputs rõ ràng**. Khi thêm kiểu mới, ba lớp này hỗ trợ phát hiện thiếu handler, thiếu test và sai logic nghiệp vụ — thay vì chỉ biết rằng code còn biên dịch được.

## Tài liệu tham khảo

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Sealed Classes and Interfaces: https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html
- Java SE 21 API — `Class.getPermittedSubclasses()`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()
- OpenJDK JEP 409 — Sealed Classes: https://openjdk.org/jeps/409
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
