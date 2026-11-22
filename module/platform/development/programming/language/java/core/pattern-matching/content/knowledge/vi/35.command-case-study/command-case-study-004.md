# Xử lý command không hợp lệ với Java Pattern Matching

## 1. Bối cảnh: command không hợp lệ không chỉ có một loại lỗi

Trong một ứng dụng nhận lệnh (*command*) từ CLI, HTTP API, message queue hoặc một service khác, người dùng có thể gửi dữ liệu sai theo nhiều cách. Chẳng hạn, một hệ thống quản lý tài khoản nội bộ hỗ trợ:

- `CREATE|carol|Carol|30`: tạo tài khoản `carol`, tên `Carol`, số dư điểm khởi tạo `30`.
- `TRANSFER|alice|bob|40`: chuyển `40` điểm từ `alice` sang `bob`.
- `RENAME|bob|Bobby`: thay tên hiển thị của tài khoản `bob`.

Các đầu vào sau đây **không cùng một lỗi**:

| Đầu vào / tình huống | Nhóm lỗi | Giải thích |
| --- | --- | --- |
| Chuỗi `null` hoặc blank | Dữ liệu đầu vào thiếu | Chưa có command để giải mã |
| `TRANSFER|alice|bob` | Cú pháp/arity sai | Thiếu đối số số lượng |
| `TRANSFER|alice|bob|abc` | Định dạng trường sai | Không chuyển `abc` thành `long` |
| `DEPOSIT|alice|5` | Command không hỗ trợ | Verb không nằm trong bộ lệnh đã biết |
| `TRANSFER|alice|bob|0` | Tham số không hợp lệ | Giao dịch yêu cầu số lượng dương |
| `TRANSFER|alice|alice|10` | Quy tắc domain bị vi phạm | Không được chuyển cho cùng tài khoản |
| `TRANSFER|alice|missing|10` | Không tìm thấy tài nguyên | Tài khoản đích không tồn tại |
| `TRANSFER|alice|bob|1000` | Xung đột với trạng thái hiện tại | Tài khoản nguồn không đủ điểm |
| `CREATE|alice|Another|10` | Xung đột | ID tài khoản đã tồn tại |
| Chuyển điểm sang số dư `Long.MAX_VALUE` | Lỗi giới hạn số | Phép cộng sẽ tràn `long` nếu không kiểm tra |

**Mục tiêu** không phải đơn giản “bắt mọi exception rồi trả error”. Hãy **phân loại lỗi ở đúng tầng**, cung cấp phản hồi ổn định, giữ dữ liệu không bị chỉnh sửa khi lệnh bị từ chối, và tiếp tục xử lý được các command hợp lệ.

Từ Java 21, **pattern matching for `switch`** (JEP 441) giúp dispatcher phân loại các biến thể command có kiểu cụ thể. Khi kết hợp `sealed interface`, `record` và `when`, ta có một bảng điều phối dễ đọc, được compiler kiểm tra tính exhaustive. Tuy nhiên pattern matching **không tự validate nghiệp vụ** và cũng **không thay thế transaction, authorization hay error handling**.

## 2. Pipeline xử lý chuẩn: phân tách bốn giai đoạn

Một pipeline hợp lý:

```text
Untrusted input (CLI / HTTP / message)
    |
    v
[1] Parse: xác định verb, số trường, kiểu dữ liệu
    |    Lỗi: BAD_REQUEST hoặc UNKNOWN_COMMAND
    v
[2] Typed Command: Create / Transfer / Rename
    |
    v
[3] Validate + authorize + kiểm tra trạng thái domain
    |    Lỗi: INVALID_ARGUMENT / NOT_FOUND / CONFLICT /
    |         lỗi quyền truy cập (ở hệ thống thực tế)
    v
[4] Execute trong phạm vi an toàn
    |    Thành công: OK
    |    Lỗi hạ tầng: xử lý riêng theo hợp đồng
    v
Reply (mã kết quả + thông điệp phù hợp)
```

**Tại sao cần tách?**

- Parser chỉ biết **cấu trúc đầu vào**: tên verb, số đối số, cú pháp số nguyên. Nó không nên tự sửa số dư tài khoản.
- Dispatcher chỉ quyết định **loại command nào cần handler nào**. Nó không nên chứa hàng loạt thao tác cập nhật database trong `when`.
- Handler biết **bất biến nghiệp vụ**: tài khoản có tồn tại không, số điểm có dương không, có đủ số dư không.
- Phản hồi có mã lỗi ổn định để CLI/API/client xử lý nhất quán.

Với JSON/HTTP thật, parser sẽ là JSON parser + schema validation, **không nên dùng `String.split` để đọc JSON**. Bài sử dụng một protocol văn bản tối giản chỉ để nhìn thấy mọi tầng trong một chương trình Java độc lập.

## 3. Biểu diễn tập command bằng sealed interface và record

Một mô hình đơn giản:

```java
sealed interface Command
        permits Create, Transfer, Rename, Unknown, Malformed {}

record Create(String id, String name, long opening)
        implements Command {}

record Transfer(String from, String to, long credits)
        implements Command {}

record Rename(String id, String name)
        implements Command {}

record Unknown(String verb) implements Command {}
record Malformed(String reason) implements Command {}
```

Ý nghĩa các biến thể:

| Biến thể | Vai trò |
| --- | --- |
| `Create` | Command đã parse được: tạo account mới |
| `Transfer` | Command đã parse được: chuyển một lượng điểm |
| `Rename` | Command đã parse được: đổi tên hiển thị |
| `Unknown` | Có verb nhưng verb không được ứng dụng hỗ trợ |
| `Malformed` | Thiếu verb, sai số đối số hoặc sai định dạng số |

Ở đây, `Unknown` và `Malformed` là **biến thể của command nội bộ** để đường điều phối luôn biểu đạt được lỗi đầu vào. Đây là một **lựa chọn thiết kế**, không phải Java bắt buộc. Một hệ thống lớn có thể dùng `ParseResult` dạng `Success(Command)`/`Failure(ParseError)` để tránh đưa lỗi parser vào domain hierarchy.

Các record `Create`, `Transfer`, `Rename` là **data carriers**. Trong ví dụ chúng cho phép chứa cả giá trị sai nghiệp vụ (ví dụ `credits=0`, `name=""`) để handler minh họa validation. Ở một mô hình domain khác, constructor/factory có thể từ chối giá trị sai ngay lập tức. Khi lựa chọn, cần giữ **đường phản hồi lỗi có cấu trúc** cho client; đừng để một constructor exception không được xử lý xuyên qua HTTP/service boundary.

`sealed interface` được chuẩn hóa từ **Java 17 (JEP 409)**, record từ **Java 16 (JEP 395)**, còn record patterns và pattern switch theo cú pháp hiện hành đều chuẩn từ **Java 21 (JEP 440/441)**.

## 4. Phân biệt lỗi parser và lỗi nghiệp vụ

### 4.1. Parser phải giữ được trường rỗng

Với giao thức minh họa phân tách bởi dấu `|`:

```java
String[] parts = raw.split("\\|", -1);
```

- `"TRANSFER|alice|bob|10"` tạo bốn trường.
- `"RENAME|bob|"` phải tạo **ba** trường, trong đó tên mới rỗng.
- `-1` bảo đảm **không bỏ các trường rỗng cuối chuỗi**; nếu bỏ, lỗi thiếu trường và trường rỗng có thể bị đánh đồng.
- `\\|` trong Java string literal tạo regex tương ứng **dấu `|` literal**, thay vì toán tử alternation của regex.

Cách xử lý command verb:

```java
String verb = parts[0].strip()
        .toUpperCase(java.util.Locale.ROOT);
```

`Locale.ROOT` giúp chuẩn hóa verb ổn định, không phụ thuộc locale mặc định của máy. Ví dụ chuẩn hóa `create` thành `CREATE` là **quy tắc parser được chọn có chủ đích**. Trong protocol phân biệt chữ hoa/thường, không được tự chuẩn hóa nếu chưa có hợp đồng cho phép.

Giới hạn demo: **không có cơ chế escape dấu `|`** trong dữ liệu tên. Nếu muốn cho phép tên chứa `|`, cần thiết kế quoting/escaping hoặc dùng định dạng có parser chuẩn (JSON/Protobuf...). Không lấy bản demo làm một protocol production hoàn chỉnh.

### 4.2. Parser chỉ bắt những exception dự đoán được

Chuyển chuỗi sang kiểu `long`:

```java
try {
    long credits = Long.parseLong(rawCredits);
    return new Transfer(from, to, credits);
} catch (NumberFormatException ex) {
    return new Malformed("invalid number");
}
```

Đây là cách chuyển **lỗi định dạng dữ liệu ngoài** thành một kết quả có kiểm soát. Nó cũng từ chối chuỗi số nằm ngoài miền `long`, ví dụ một số nguyên có quá nhiều chữ số.

**Không nên**:

```java
// Anti-pattern minh họa:
// try {
//     return executeEverything();
// } catch (RuntimeException ex) {
//     return "INVALID_COMMAND";
// }
```

Bắt `RuntimeException` bừa bãi sẽ che `NullPointerException` do bug lập trình, `IllegalStateException` của service, lỗi database và các exception bất ngờ khác. Một lỗi hệ thống **không phải** mặc nhiên là command không hợp lệ. Nên chuyển lỗi đầu vào dự đoán được sang mã cụ thể, còn lỗi không mong đợi phải được báo cáo/giám sát và xử lý theo hợp đồng của hệ thống.

### 4.3. Unknown command khác malformed command

`DEPOSIT|alice|5` có cấu trúc trông giống command hợp lệ nhưng verb `DEPOSIT` chưa được hỗ trợ. Trả `UNKNOWN_COMMAND:DEPOSIT` là chính xác hơn `BAD_REQUEST:invalid number` hoặc `NullPointerException`.

Còn `TRANSFER|alice|bob` là **verb hợp lệ nhưng sai arity**, nên trả `BAD_REQUEST:TRANSFER needs 3 arguments`.

Trong API công khai, có thể không muốn trả nguyên verb do người dùng gửi nếu nó chứa dữ liệu nhạy cảm hoặc độc hại. Demo chỉ dùng verb đã chuẩn hóa. Với hệ thống thật, nên giới hạn độ dài đầu vào, kiểm tra charset, phân loại lỗi và tránh phản chiếu raw payload vào response/log.

## 5. Dispatcher dùng record patterns và guard `when`

Khi parser trả về một `Command`, Java 21 có thể phân phối:

```java
return switch (command) {
    case Create(var id, var name, var opening) ->
            create(state, id, name, opening);

    case Transfer(var from, var to, var credits)
            when credits <= 0 ->
            reply("INVALID_ARGUMENT", "credits must be positive");

    case Transfer(var from, var to, var credits) ->
            transfer(state, from, to, credits);

    case Rename(var id, var name) ->
            rename(state, id, name);

    case Unknown(var verb) ->
            reply("UNKNOWN_COMMAND", verb);

    case Malformed(var reason) ->
            reply("BAD_REQUEST", reason);

    case null ->
            reply("BAD_REQUEST", "null command");
};
```

Đoạn trên là **một phần phương thức**, cần các record/handler/biến `state` được định nghĩa như trong chương trình hoàn chỉnh ở mục 7.

Điểm cần hiểu:

1. `case Create(var id, var name, var opening)` là **record pattern**, lấy ba component theo đúng thứ tự khai báo.
2. `case Transfer(...) when credits <= 0` là **guarded record pattern**. Guard chỉ đánh giá khi record pattern đã khớp.
3. Nhánh `Transfer` không guard phải ở **sau** nhánh có guard; nếu đặt nhánh tổng quát trước, nó bao phủ nhánh cụ thể và compiler có thể báo dominated case.
4. Guard `credits <= 0` không gọi database, không ghi log và không thay trạng thái. Nó chỉ phát biểu một điều kiện nghiệp vụ đơn giản.
5. `case Unknown(...)` và `case Malformed(...)` thể hiện hai kiểu lỗi có thể dự đoán.
6. `case null` xử lý **command object được truyền trực tiếp là null**. Đây là tình huống khác với chuỗi raw null mà parser chuyển thành `Malformed`.
7. Không có `default` vì `Command` là sealed hierarchy với năm biến thể đã được bao phủ; **compiler giúp nhắc cập nhật** nếu thêm một kiểu command mới.

**Điều quan trọng:** Pattern matching giải quyết **phân phối theo kiểu và cấu trúc**, không xác nhận `id` tồn tại, `name` hợp lệ hay `credits` có thể chuyển an toàn. Các kiểm tra đó thuộc handler.

### Null ở selector và null ở component

`case null` chỉ giải quyết `command == null`. Với `new Rename("bob", null)`, selector `Rename` tồn tại nhưng component `name` là null; record pattern `Rename(var id,var name)` vẫn binding component null và handler phải kiểm tra `validName(name)`. Đừng trông chờ `case null` bắt được mọi null bên trong record.

Nếu dùng **nested record pattern** để bóc một component record có thể null, cần thiết kế fallback riêng; một exhaustive pattern switch vẫn có thể gặp `MatchException` nếu không có nhãn khớp ở runtime. Chương trình chính cố ý dùng record patterns nông và validate nullable data trong handler.

## 6. Những bất biến phải kiểm tra trước khi thay đổi trạng thái

### 6.1. Create

Trước khi tạo account:

- `id` hợp lệ theo chính sách của demo: chữ thường ASCII từ `a` đến `z` ở đầu, tiếp theo là chữ thường hoặc chữ số.
- `name` khác null/blank, tối đa 40 UTF-16 code units trong cách đo `String.length()` của ví dụ.
- `opening >= 0`; không cho phép số dư âm ngay lúc tạo.
- `id` chưa tồn tại; nếu trùng, trả `CONFLICT`.

**Chỉ sau khi mọi kiểm tra qua** mới gọi `state.accounts.put(...)`.

### 6.2. Transfer

Trước khi chuyển điểm:

- `credits > 0` (được kiểm tra trong guard).
- Hai account ID hợp lệ và **khác nhau**.
- Cả account nguồn và đích đều tồn tại.
- Số dư nguồn đủ điểm.
- Số dư đích + điểm chuyển không tràn `long`.

Dùng `Math.addExact(target.credits, credits)` trước khi trừ điểm nguồn. Nếu phép cộng tràn, bắt `ArithmeticException` **ngay tại phép toán dự kiến có thể tràn** và trả lỗi nghiệp vụ thích hợp. Trong demo, account đích chứa `Long.MAX_VALUE` sẽ không nhận thêm một điểm.

Việc kiểm tra **trước khi đột biến** giúp lệnh bị từ chối không gây trạng thái nửa vời trong **ví dụ chạy một luồng, trong bộ nhớ**. Tuy nhiên đây **không phải bảo đảm giao dịch nguyên tử trong hệ thống thật**: nếu có concurrency, database hoặc service bên ngoài, cần transaction, locking/optimistic versioning và thiết kế idempotency phù hợp.

### 6.3. Rename

Trước khi đổi tên:

- `id` hợp lệ, `name` không blank.
- Account tồn tại.
- Chỉ sau đó cập nhật `account.name`.

Khi `RENAME|bob|` có phần tên rỗng, parser vẫn tạo `Rename("bob", "")` và handler trả `INVALID_ARGUMENT:bad name`. Đây là ví dụ rõ về **đúng cú pháp** (đủ ba trường) nhưng **sai hợp đồng**.

## 7. Chương trình Java 21 hoàn chỉnh, chạy độc lập

Chương trình thực thi một luồng với dữ liệu trong memory, phục vụ minh họa pipeline parser → dispatcher → handler. Nó **không phải hệ thống quản lý tiền thật**: dùng “credits” nguyên `long`, không có database, xác thực, phân quyền, giao dịch phân tán hoặc khả năng cạnh tranh. Để làm việc với tiền, phải có mô hình đơn vị, precision, authorization, audit và transactional consistency phù hợp.

Lưu file **`InvalidCommandDemo.java`**:

```java
public class InvalidCommandDemo {
    sealed interface Command
            permits Create, Transfer, Rename, Unknown, Malformed {}

    record Create(String id, String name, long opening)
            implements Command {}

    record Transfer(String from, String to, long credits)
            implements Command {}

    record Rename(String id, String name) implements Command {}
    record Unknown(String verb) implements Command {}
    record Malformed(String reason) implements Command {}

    record Reply(String code, String detail) {
        @Override
        public String toString() {
            return code + ":" + detail;
        }
    }

    static final class Account {
        String name;
        long credits;

        Account(String name, long credits) {
            this.name = name;
            this.credits = credits;
        }
    }

    static final class State {
        final java.util.Map<String, Account> accounts =
                new java.util.LinkedHashMap<>();

        State() {
            accounts.put("alice", new Account("Alice", 100));
            accounts.put("bob", new Account("Bob", 20));
        }
    }

    static Command parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return new Malformed("empty input");
        }

        String[] parts = raw.split("\\|", -1);
        String verb = parts[0].strip()
                .toUpperCase(java.util.Locale.ROOT);

        if (verb.isEmpty()) {
            return new Malformed("missing verb");
        }

        return switch (verb) {
            case "CREATE" -> {
                if (parts.length != 4) {
                    yield new Malformed(
                            "CREATE needs 3 arguments");
                }
                try {
                    yield new Create(
                            parts[1].strip(),
                            parts[2].strip(),
                            Long.parseLong(parts[3].strip()));
                } catch (NumberFormatException ex) {
                    yield new Malformed("invalid number");
                }
            }

            case "TRANSFER" -> {
                if (parts.length != 4) {
                    yield new Malformed(
                            "TRANSFER needs 3 arguments");
                }
                try {
                    yield new Transfer(
                            parts[1].strip(),
                            parts[2].strip(),
                            Long.parseLong(parts[3].strip()));
                } catch (NumberFormatException ex) {
                    yield new Malformed("invalid number");
                }
            }

            case "RENAME" ->
                    parts.length == 3
                            ? new Rename(
                                    parts[1].strip(),
                                    parts[2].strip())
                            : new Malformed(
                                    "RENAME needs 2 arguments");

            default -> new Unknown(verb);
        };
    }

    static Reply reply(String code, String detail) {
        return new Reply(code, detail);
    }

    static boolean validId(String id) {
        return id != null && id.matches("[a-z][a-z0-9]*");
    }

    static boolean validName(String name) {
        return name != null
                && !name.isBlank()
                && name.length() <= 40;
    }

    static Reply dispatch(State state, Command command) {
        java.util.Objects.requireNonNull(state, "state");

        return switch (command) {
            case Create(var id, var name, var opening) ->
                    create(state, id, name, opening);

            case Transfer(var from, var to, var credits)
                    when credits <= 0 ->
                    reply(
                            "INVALID_ARGUMENT",
                            "credits must be positive");

            case Transfer(var from, var to, var credits) ->
                    transfer(state, from, to, credits);

            case Rename(var id, var name) ->
                    rename(state, id, name);

            case Unknown(var verb) ->
                    reply("UNKNOWN_COMMAND", verb);

            case Malformed(var reason) ->
                    reply("BAD_REQUEST", reason);

            case null ->
                    reply("BAD_REQUEST", "null command");
        };
    }

    static Reply create(
            State state, String id, String name, long opening) {
        if (!validId(id)) {
            return reply("INVALID_ARGUMENT", "bad id");
        }
        if (!validName(name)) {
            return reply("INVALID_ARGUMENT", "bad name");
        }
        if (opening < 0) {
            return reply(
                    "INVALID_ARGUMENT",
                    "opening must be nonnegative");
        }
        if (state.accounts.containsKey(id)) {
            return reply("CONFLICT", "account exists");
        }

        state.accounts.put(id, new Account(name, opening));
        return reply("OK", "created " + id);
    }

    static Reply transfer(
            State state, String from, String to, long credits) {
        if (!validId(from) || !validId(to)) {
            return reply("INVALID_ARGUMENT", "bad id");
        }
        if (from.equals(to)) {
            return reply(
                    "INVALID_ARGUMENT",
                    "accounts must differ");
        }

        Account source = state.accounts.get(from);
        Account target = state.accounts.get(to);

        if (source == null || target == null) {
            return reply("NOT_FOUND", "account missing");
        }
        if (source.credits < credits) {
            return reply("CONFLICT", "insufficient balance");
        }

        long newTarget;
        try {
            newTarget = Math.addExact(target.credits, credits);
        } catch (ArithmeticException ex) {
            return reply("CONFLICT", "balance overflow");
        }

        source.credits -= credits;
        target.credits = newTarget;

        return reply("OK", "transferred " + credits);
    }

    static Reply rename(State state, String id, String name) {
        if (!validId(id)) {
            return reply("INVALID_ARGUMENT", "bad id");
        }
        if (!validName(name)) {
            return reply("INVALID_ARGUMENT", "bad name");
        }

        Account target = state.accounts.get(id);
        if (target == null) {
            return reply("NOT_FOUND", "account missing");
        }

        target.name = name;
        return reply("OK", "renamed " + id);
    }

    static java.util.Map<String, String> snapshot(State state) {
        java.util.Map<String, String> copy =
                new java.util.LinkedHashMap<>();

        state.accounts.forEach((id, account) ->
                copy.put(
                        id,
                        account.name + "/" + account.credits));

        return copy;
    }

    static void check(
            State state,
            String label,
            String raw,
            String expected) {
        var before = snapshot(state);
        Reply result = dispatch(state, parse(raw));

        if (!result.toString().equals(expected)) {
            throw new AssertionError(
                    label + ": expected " + expected
                            + ", got " + result);
        }

        if (!result.code().equals("OK")
                && !before.equals(snapshot(state))) {
            throw new AssertionError(
                    label + ": rejected command changed state");
        }

        System.out.println(label + " => " + result);
    }

    public static void main(String[] args) {
        State state = new State();

        check(state, "null-text", null,
                "BAD_REQUEST:empty input");
        check(state, "blank", " ",
                "BAD_REQUEST:empty input");
        check(state, "no-verb", "|alice",
                "BAD_REQUEST:missing verb");
        check(state, "unknown", "DEPOSIT|alice|4",
                "UNKNOWN_COMMAND:DEPOSIT");
        check(state, "arity", "TRANSFER|alice|bob",
                "BAD_REQUEST:TRANSFER needs 3 arguments");
        check(state, "number", "TRANSFER|alice|bob|foo",
                "BAD_REQUEST:invalid number");
        check(state, "zero", "TRANSFER|alice|bob|0",
                "INVALID_ARGUMENT:credits must be positive");
        check(state, "negative", "TRANSFER|alice|bob|-5",
                "INVALID_ARGUMENT:credits must be positive");
        check(state, "same", "TRANSFER|alice|alice|10",
                "INVALID_ARGUMENT:accounts must differ");
        check(state, "not-found", "TRANSFER|alice|nobody|1",
                "NOT_FOUND:account missing");
        check(state, "insufficient",
                "TRANSFER|alice|bob|1000",
                "CONFLICT:insufficient balance");
        check(state, "blank-name", "CREATE|carol| |10",
                "INVALID_ARGUMENT:bad name");
        check(state, "duplicate",
                "CREATE|alice|Another|10",
                "CONFLICT:account exists");

        check(state, "create", "CREATE|carol|Carol|30",
                "OK:created carol");
        check(state, "transfer",
                "TRANSFER|alice|bob|40",
                "OK:transferred 40");
        check(state, "rename", "RENAME|bob|Bobby",
                "OK:renamed bob");

        check(state, "rename-bad", "RENAME|bob|",
                "INVALID_ARGUMENT:bad name");
        check(state, "rename-missing",
                "RENAME|ghost|Ghost",
                "NOT_FOUND:account missing");
        check(state, "huge-create",
                "CREATE|huge|Huge|9223372036854775807",
                "OK:created huge");
        check(state, "overflow",
                "TRANSFER|alice|huge|1",
                "CONFLICT:balance overflow");

        Reply directNull = dispatch(state, null);
        if (!directNull.toString()
                .equals("BAD_REQUEST:null command")) {
            throw new AssertionError("null command");
        }

        System.out.println("direct-null => " + directNull);
        System.out.println("final=" + snapshot(state));
    }
}
```

Biên dịch và chạy trên **JDK 21+**, không cần bật preview:

```bash
javac --release 21 InvalidCommandDemo.java
java InvalidCommandDemo
```

**Stdout chính xác:**

```text
null-text => BAD_REQUEST:empty input
blank => BAD_REQUEST:empty input
no-verb => BAD_REQUEST:missing verb
unknown => UNKNOWN_COMMAND:DEPOSIT
arity => BAD_REQUEST:TRANSFER needs 3 arguments
number => BAD_REQUEST:invalid number
zero => INVALID_ARGUMENT:credits must be positive
negative => INVALID_ARGUMENT:credits must be positive
same => INVALID_ARGUMENT:accounts must differ
not-found => NOT_FOUND:account missing
insufficient => CONFLICT:insufficient balance
blank-name => INVALID_ARGUMENT:bad name
duplicate => CONFLICT:account exists
create => OK:created carol
transfer => OK:transferred 40
rename => OK:renamed bob
rename-bad => INVALID_ARGUMENT:bad name
rename-missing => NOT_FOUND:account missing
huge-create => OK:created huge
overflow => CONFLICT:balance overflow
direct-null => BAD_REQUEST:null command
final={alice=Alice/60, bob=Bobby/60, carol=Carol/30, huge=Huge/9223372036854775807}
```

Chương trình được kiểm tra với **JDK 24 JShell**, dùng cú pháp Java 21 và cho đúng 22 dòng stdout. Các method `check` tự đối chiếu `Reply` với giá trị mong đợi, đồng thời so sánh snapshot trạng thái trước/sau nếu command **không** trả `OK`. Nếu test bị lệch, chương trình ném `AssertionError` thay vì in một dòng kết quả thành công giả.

Các số dư cuối chứng minh: ban đầu `alice=100` và `bob=20`; chuyển 40 điểm hợp lệ tạo `alice=60`, `bob=60`; lệnh đổi tên hợp lệ tạo `Bobby`; lệnh chuyển 1 điểm đến account đã có `Long.MAX_VALUE` bị từ chối nên `huge` giữ nguyên.

## 8. Phân tích chi tiết các đường lỗi trong chương trình

### 8.1. Chuỗi null/blank so với command object null

`parse(null)` trả `Malformed("empty input")` vì parser đã nhận và phân loại chuỗi raw thiếu nội dung. Trái lại `dispatch(state, null)` nhận trực tiếp **reference command null**, chọn `case null` và trả `BAD_REQUEST:null command`.

Hai lệnh cuối cùng đều không thành công, nhưng chúng đi qua **hai đường khác nhau**. Phân biệt này có ích khi gỡ lỗi tầng giao tiếp và tầng xử lý typed command.

### 8.2. Sai arity và sai định dạng số

`TRANSFER|alice|bob` bị từ chối **trước** khi cố đọc `parts[3]`. Điều này ngăn `ArrayIndexOutOfBoundsException` do parser lập trình thiếu kiểm tra.

`TRANSFER|alice|bob|foo` có đúng số đối số nhưng giá trị thứ tư không phải `long`; `NumberFormatException` được chuyển có chủ đích thành `Malformed("invalid number")`.

Một input như `TRANSFER|alice|bob|999999999999999999999999999999` cũng phát sinh lỗi định dạng do vượt giới hạn `long`.

### 8.3. Guard khi credits không dương

`case Transfer(...) when credits <= 0` xử lý 0 và số âm trước khi gọi handler chuyển khoản. Không cần cấp quyền hay truy vấn account để biết số lượng điểm không dương đã vi phạm hợp đồng.

Trong một domain khác, thứ tự trả lỗi có thể được thiết kế khác vì lý do bảo mật hoặc API contract. Ví dụ không nên để một người dùng chưa được xác thực khai thác các thông báo lỗi để suy ra tài khoản nào tồn tại. **Chương trình demo chưa có xác thực/phân quyền**; trong production, authentication và authorization phải được thiết kế tại boundary thích hợp trước khi tiết lộ thông tin nhạy cảm.

### 8.4. Không tìm thấy account và không đủ số dư

`TRANSFER|alice|nobody|1` có cấu trúc và số lượng hợp lệ, nhưng account đích không tồn tại. Trả `NOT_FOUND` khác với `INVALID_ARGUMENT`.

`TRANSFER|alice|bob|1000` có account hợp lệ nhưng `alice` chỉ có 100 điểm. Trả `CONFLICT:insufficient balance`, không sửa số dư. Cách phân loại `CONFLICT` là **quy ước của demo**; với API thực, phải xác định mã lỗi nghiệp vụ và HTTP status tương ứng theo hợp đồng riêng.

### 8.5. Tràn số khi cộng số dư đích

Câu lệnh:

```java
long newTarget;
try {
    newTarget = Math.addExact(target.credits, credits);
} catch (ArithmeticException ex) {
    return reply("CONFLICT", "balance overflow");
}
```

tính số dư đích **trước khi thay đổi** nguồn. `Math.addExact` kiểm tra tràn số nguyên có dấu, thay vì để `long` âm vòng (*wrap-around*). Trong test, `huge` có `Long.MAX_VALUE`; cộng 1 tạo `ArithmeticException`, được chuyển thành một phản hồi có kiểm soát. Sau đó cả số dư nguồn và đích giữ nguyên.

Cách này tốt cho mô hình số nguyên đơn giản. Với điểm thưởng có cạnh tranh, hoặc tiền thật, phải có kiểm tra tổng số dư, chính sách giới hạn, transaction và độ chính xác đơn vị rõ ràng; **không tự mặc định đây là hệ thống tài chính an toàn**.

## 9. Tính exhaustive: vì sao không cần default?

Bộ command được định nghĩa:

```java
sealed interface Command
        permits Create, Transfer, Rename, Unknown, Malformed {}
```

Dispatcher xử lý mọi biến thể cùng `case null`. Với **`switch` expression trên `Command`**, Java 21 có thể kiểm tra bộ case là exhaustive. Nếu thêm `record Suspend(String id) implements Command` và cập nhật `permits`, code `dispatch` sẽ cần xét `Suspend` khi biên dịch lại nếu không có pattern tổng quát che tất cả.

Đây là cơ chế hữu ích chống quên command mới. Đừng thêm `default -> reply("UNKNOWN_COMMAND", "...")` vào mọi sealed switch chỉ để tránh compiler báo thiếu case: làm vậy có thể che một **biến thể đã khai báo nhưng chưa được implement**.

**UnknownCommand không phải là default.** `Unknown` ở đây là **một record có kiểu cụ thể**, được parser tạo khi gặp verb chưa hỗ trợ. Vì vậy:

- `Unknown("DEPOSIT")` xử lý được một raw verb mới chưa đăng ký.
- `Suspend` là **một subtype Java mới của Command**, cần được thiết kế và thêm handler.
- `null` là selector rỗng, có nhãn riêng.

Nếu domain hỗ trợ plugin bên ngoài tự định nghĩa subtype `Command`, `sealed` có thể không phù hợp; khi đó registry/visitor hoặc một interface mở có thể cần fallback. Đây là **quyết định kiến trúc**, không phải hạn chế của record pattern.

### MatchException khác kết quả BAD_REQUEST

Một `switch` exhaustive có thể ném `MatchException` khi class hierarchy thay đổi sau khi client compile hoặc một nested pattern không khớp ở runtime dù compiler cho là exhaustive. Đó **không phải** phản hồi `BAD_REQUEST` bình thường. Cần kiểm tra môi trường build, phiên bản thư viện và tính đầy đủ của pattern, thay vì catch `MatchException` rồi âm thầm coi như input sai.

Trong chương trình, dispatcher không dùng nested record patterns trên component có thể null, và record `Malformed`/`Unknown` cho lỗi dự kiến; vì thế các lỗi đầu vào thông thường được trả thành `Reply`, không cần dựa vào exception để điều phối.

## 10. Error model: trả mã ổn định, không phát tán chi tiết nội bộ

`Reply(String code, String detail)` của demo đủ để minh họa, nhưng một API thực tế nên dùng kiểu dữ liệu có hợp đồng rõ:

```java
// Minh họa thiết kế, không phải phần thay thế trực tiếp của demo.
enum ErrorCode {
    BAD_REQUEST,
    UNKNOWN_COMMAND,
    INVALID_ARGUMENT,
    NOT_FOUND,
    CONFLICT,
    FORBIDDEN,
    INTERNAL_ERROR
}

record ApiError(
        ErrorCode code,
        String message,
        String correlationId) {}
```

**Nguyên tắc:**

- **Code** ổn định, máy có thể đọc, không phụ thuộc ngôn ngữ hiển thị.
- **Message** đủ rõ cho người gọi, nhưng không chứa stack trace, SQL query, token hoặc thông tin tài khoản nhạy cảm.
- **Correlation ID** giúp liên kết response với server logs/tracing mà không phơi bày nội bộ.
- **Unexpected exception** được log/quan sát an toàn và trả lỗi hệ thống phù hợp, không gộp vào `INVALID_ARGUMENT`.
- Có thể bổ sung danh sách vi phạm theo field (`field`, `reason`) cho form/JSON, tránh parse thông điệp tự do.
- Mã lỗi của domain **không nhất thiết tương ứng 1:1** với HTTP status code; mapping HTTP phải được thiết kế ở adapter API.

Ví dụ mapping API thường gặp **chỉ để tham khảo**: malformed payload → HTTP 400; không được phép → 403; không tìm thấy tài nguyên → 404; conflict → 409. Với endpoint thực tế còn có 401 (authentication), 422 (validation) hoặc lựa chọn không tiết lộ sự tồn tại của tài nguyên. Không copy bảng mapping này vào production mà không xem lại policy và khả năng tương thích client.

### Có nên dùng enum cho mã lỗi?

Có, nếu hệ thống muốn compiler kiểm tra các mã hợp lệ. `Reply` dùng string để giữ ví dụ ngắn; `enum ErrorCode` hoặc sealed result types giúp loại bỏ typo. Một biến thể khác:

```java
sealed interface Outcome permits Success, Failure {}
record Success(String message) implements Outcome {}
record Failure(ErrorCode code, String message)
        implements Outcome {}
```

Có thể `switch` tiếp trên `Outcome` để chuyển sang HTTP/gRPC/CLI response. Tuy nhiên không nên tạo quá nhiều hierarchy nếu một `record Reply` nhỏ đã đủ cho yêu cầu.

## 11. Tác động phụ, transaction và race condition

Kiểm tra đầu vào đúng **không tự bảo đảm thao tác cập nhật đúng dưới concurrency**.

Trong demo:

```java
if (source.credits < credits) {
    return reply("CONFLICT", "insufficient balance");
}
long newTarget = Math.addExact(target.credits, credits);
source.credits -= credits;
target.credits = newTarget;
```

Bốn bước trên không có transaction/lock. Nếu hai thread đồng thời đọc cùng `source.credits`, cả hai có thể thấy đủ số dư rồi cùng trừ, gây **lost update** hoặc vi phạm invariant. Trong hệ thống có database:

- Dùng **transaction** cho các thay đổi cần nguyên tử.
- Áp dụng optimistic locking (version column) hoặc locking phù hợp.
- Kiểm tra số dư trên trạng thái được bảo vệ và cập nhật có điều kiện.
- Có **idempotency key** cho command có thể bị gửi lại do retry; đặc biệt với chuyển điểm/tiền.
- Không gửi event/email/notification trước khi transaction commit một cách không kiểm soát. Cân nhắc transactional outbox nếu cần đảm bảo nhất quán giữa DB và message broker.
- Phân biệt lỗi **không hợp lệ không nên retry** với lỗi **tạm thời có thể retry** theo chính sách.

Các yêu cầu này nằm ngoài khả năng của một `switch` pattern. Pattern matching chỉ làm đường định tuyến rõ hơn, không “hô biến” việc cập nhật tài khoản thành atomic.

## 12. Authorization, input limits và an toàn dữ liệu

Một command đúng kiểu và hợp lệ về payload **có thể vẫn không được phép thực thi**.

Ví dụ `RENAME|bob|Bobby` hoàn toàn hợp lệ về cú pháp, nhưng caller có thể không sở hữu account `bob`. Trong service thật, cần kiểm tra quyền trước khi thay đổi dữ liệu.

Các điểm cần triển khai:

1. **Authentication:** caller là ai? Có token/session hợp lệ không?
2. **Authorization:** caller được phép tạo, chuyển, đổi tên account nào?
3. **Input limits:** số byte/ký tự tối đa của raw payload, số trường, độ dài ID/name để tránh tiêu tốn tài nguyên.
4. **Canonicalization:** nếu chuẩn hóa chữ hoa/thường/Unicode/whitespace, phải đồng bộ giữa validation, storage và uniqueness check.
5. **Sensitive data:** không log raw payload chứa credential/PII; chỉ ghi metadata cần thiết.
6. **Rate limits và quotas:** ngăn spam command kể cả command bị từ chối.
7. **Replay/duplicate:** các command có side effect cần ID để phát hiện gửi lại nếu giao thức có retry.
8. **Validation ở boundary:** JSON deserialization có thể tạo null, enum lạ hoặc trường thiếu, bất kể compiler nhìn thấy sealed model.

Không nhầm kiểm tra `validId` bằng regex với authorization. Regex xác định **hình dạng ID**, không xác định quyền trên ID đó.

## 13. Kiểm thử command không hợp lệ theo ma trận

Một bộ test tốt không chỉ kiểm tra “happy path”. Nên chia:

| Lớp kiểm thử | Ví dụ | Invariant |
| --- | --- | --- |
| Parse | Raw null, blank, thiếu verb | Có mã `BAD_REQUEST`, không exception ngoài dự kiến |
| Arity | Thiếu hoặc thừa đối số | Không truy cập mảng ngoài giới hạn |
| Numeric | `foo`, số vượt giới hạn `long` | Parser trả lỗi định dạng |
| Unknown verb | `DEPOSIT` chưa được hỗ trợ | Trả `UNKNOWN_COMMAND`, không coi là Create/Transfer |
| Boundary | `credits=0`, `-1`, `1` | Ranh giới dương được áp dụng đúng |
| Domain state | Account trùng, account thiếu, không đủ số dư | Mã lỗi phân biệt rõ |
| Numeric overflow | Cộng vào `Long.MAX_VALUE` | Không wrap-around, không thay đổi số dư |
| Component null | `new Rename("bob", null)` | Handler trả `INVALID_ARGUMENT` an toàn |
| Selector null | `dispatch(state, null)` | `case null` xử lý đúng |
| Side effects | Command thất bại | Snapshot trước/sau không đổi |
| Success | Create, Transfer, Rename | Chỉ thay những account/field cần thiết |
| Extensibility | Thêm subtype command | Compiler/test nhắc cập nhật dispatcher |

Với test có side effect thực, nên dùng **fake repository hoặc database transaction rollback**; không chạy lệnh thử chuyển tiền thật hai lần để so sánh. Unit test của parser nên độc lập với handler, và integration test phải bao gồm điều kiện đồng thời/retry nếu hệ thống hỗ trợ.

### Một số property hữu ích

- **Không thay trạng thái khi bị từ chối:** với mọi command trả code khác `OK`, state phải bằng state ban đầu (trong các tình huống đã xác định).
- **Bảo toàn tổng điểm:** với một Transfer thành công giữa hai tài khoản khác nhau, tổng điểm của hai account phải không đổi (nếu không có phí và phép toán không tràn).
- **Idempotency của parser:** parse một raw command xác định phải cho kết quả cấu trúc tương đương khi không có thời gian/random tác động.
- **Không ném ngoại lệ ngoài dự kiến:** trên miền input raw được hỗ trợ/không hợp lệ đã dự kiến, parser trả command/error thay vì truy cập mảng sai hoặc làm rơi NumberFormatException.
- **Không thay dữ liệu khi xử lý Unknown/Malformed:** mọi command kiểu `Unknown`/`Malformed` đều không được cập nhật repository.
- **Exhaustiveness:** thêm subtype mới của `Command` phải kéo theo cập nhật dispatcher và test.

**Cẩn thận:** “mọi lỗi đều không throw” là property quá rộng. Bug/hạ tầng bất ngờ có thể cần exception hoặc cơ chế failure ở tầng cao; không được nuốt để làm test xanh.

## 14. Các lỗi thường gặp và cách tránh

1. **Dùng một `default` duy nhất cho mọi command:** che thiếu handler khi thêm subtype mới của sealed interface.
2. **Đánh đồng unknown verb với malformed payload:** client không biết phải sửa cú pháp hay đổi loại lệnh.
3. **Bắt `RuntimeException` rồi trả `INVALID_COMMAND`:** che lỗi lập trình/hạ tầng thành lỗi người dùng.
4. **Đưa ghi database hoặc gửi event vào `when`:** guard có thể chạy nhưng nhánh không được chọn; side effect vẫn tồn tại.
5. **Đặt nhánh `Transfer` không guard trước nhánh `when credits <= 0`:** gây domination hoặc mất kiểm tra chuyên biệt.
6. **Tin rằng `case null` bắt null trong mọi record component:** selector null và component null là hai tầng khác nhau.
7. **Dùng `String.split("\\|")` mà quên `-1`:** mất trường rỗng cuối, phân loại lỗi sai.
8. **Dùng `Long.parseLong` mà không catch đúng lỗi:** đầu vào không hợp lệ trở thành exception ngoài API contract.
9. **Cập nhật số dư nguồn trước rồi mới kiểm tra overflow ở đích:** có thể để lại trạng thái không nhất quán khi bị từ chối.
10. **Cho rằng validation trước mutation đủ cho concurrency:** nhiều thread vẫn có thể cùng đọc trạng thái cũ; cần transaction/locking.
11. **Trộn validId với authorization:** ID đúng regex không đồng nghĩa caller có quyền thao tác.
12. **Log raw command hoặc exception details ra client:** có thể rò rỉ dữ liệu và chi tiết nội bộ.
13. **Không đặt giới hạn độ dài input:** một parser đơn giản vẫn có thể tiêu thụ tài nguyên quá mức khi nhận payload khổng lồ.
14. **Cho rằng record constructor tự validate:** record không có invariant trừ khi tác giả định nghĩa.
15. **Dùng `long` cho tiền thật mà không định nghĩa đơn vị/precision/overflow:** mô hình không đủ cho ứng dụng tài chính.
16. **Trả `NOT_FOUND` cho mọi lỗi:** thiếu thông tin để client phân biệt validation, conflict và tài nguyên thiếu.
17. **Dùng `toString()` của record làm giao thức dữ liệu:** output record có thể thay đổi theo schema, không phải wire format ổn định.
18. **Dùng pattern matching để thay toàn bộ kiến trúc xử lý lỗi:** pattern là công cụ phân phối, không phải transaction manager hay security boundary.

## 15. Checklist trước khi merge

- [ ] Phân biệt rõ parser error, unknown command, invalid arguments, domain conflict, not found và system failure.
- [ ] Bộ kiểu `Command` là sealed có chủ đích, bao phủ đầy đủ các biến thể hiện tại?
- [ ] Record patterns và `when` chỉ làm matching/điều kiện rõ ràng, không giấu side effect?
- [ ] `case null` giải quyết selector null, còn component null được validate trong handler?
- [ ] Parser kiểm tra số trường **trước** khi truy cập mảng và dùng `split(..., -1)` nếu cần giữ trường rỗng?
- [ ] Chuyển đổi kiểu số bắt `NumberFormatException` đúng tầng và có thông điệp lỗi ổn định?
- [ ] Có giới hạn input, chính sách chuẩn hóa, schema và encoding phù hợp?
- [ ] Handler validate đầy đủ trước mutation, kiểm tra phép toán tràn số, và phân biệt business conflict?
- [ ] Hệ thống thực có authentication, authorization, transaction, locking và idempotency khi cần?
- [ ] Test kiểm tra không thay trạng thái đối với lệnh bị từ chối?
- [ ] Test bao phủ các giá trị biên, unknown verb, malformed arguments, component null và command null?
- [ ] Error response không tiết lộ stack trace/secret và có correlation ID khi cần?
- [ ] Khi thêm command subtype, đã cập nhật dispatcher, parser, quyền truy cập, schema và test?

**Kết luận:** Xử lý command không hợp lệ bắt đầu bằng **phân loại lỗi đúng tầng**. Java 21 `sealed` + `record` + `switch` pattern giúp dispatcher dễ đọc và exhaustive; `when` chỉ phù hợp cho các guard đơn giản, thuần túy. Parser phải biến dữ liệu sai cú pháp thành kết quả dự đoán được, handler xác nhận các quy tắc domain **trước khi làm side effect**, còn concurrency/security/transaction là trách nhiệm riêng. Nhờ vậy command không hợp lệ được từ chối có kiểm soát mà không phá trạng thái hoặc che giấu lỗi hệ thống.

### Tài liệu tham khảo

- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 409 — Sealed Classes: https://openjdk.org/jeps/409
- OpenJDK JEP 395 — Records: https://openjdk.org/jeps/395
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java 21 API — `Long.parseLong`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html#parseLong(java.lang.String)
- Oracle Java 21 API — `Math.addExact`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#addExact(long,long)
