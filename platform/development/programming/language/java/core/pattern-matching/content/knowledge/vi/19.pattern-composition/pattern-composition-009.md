# Tách predicate phức tạp thành phương thức khi kết hợp patterns (Java 21)

## Mục tiêu

Trong chủ đề **Kết hợp patterns**, biểu thức `instanceof` hoặc nhánh `switch` có thể cùng lúc chứa type pattern, nested record pattern, toán tử `&&`/`||` và guard `when`. Khi phần điều kiện boolean kéo dài, việc tách thành phương thức có tên rõ nghĩa giúp người đọc hiểu **điều kiện nghiệp vụ** mà không phải giải mã từng phép so sánh.

Sau bài này, bạn có thể:
- Phân biệt **kiểm tra cấu trúc** bằng pattern với **predicate nghiệp vụ** bằng boolean.
- Tách guard phức tạp thành các phương thức nhỏ mà không đổi kết quả.
- Truyền đúng pattern variables vào helper từ `when` hoặc vế phải `&&`.
- Bảo toàn thứ tự đánh giá, short-circuit, ưu tiên `&&`/`||`, xử lý `null` và thứ tự các nhánh `switch`.
- Chọn giữa tách **riêng guard** và đóng gói **cả điều kiện domain** vào một phương thức.

**Yêu cầu:** Java 21 trở lên. Record Patterns (JEP 440) và Pattern Matching for `switch` (JEP 441) đều là tính năng chính thức từ Java 21, không cần `--enable-preview`.

## 1. Bài toán: pattern rõ ràng nhưng guard quá dài

Giả sử có hai record:

```java
record Reporter(String email, boolean verified, String team) {}
record Ticket(String id, Reporter reporter, int impact, boolean serviceDown) {}
```

Hệ thống ví dụ áp dụng **quy tắc giả định để học**, không phải tiêu chuẩn vận hành: một ticket được đưa vào luồng `ESCALATE` khi đồng thời thỏa mãn:

1. Dịch vụ đang gián đoạn (`serviceDown == true`).
2. Mức tác động từ 3 đến 5, gồm cả hai biên.
3. Người báo cáo đã được xác minh.
4. Email không `null`, kết thúc bằng `@company.test`.
5. Nhóm hỗ trợ là `SRE` **hoặc** `OPS`.

Nếu reporter thiếu hoặc bất kỳ điều kiện nào sai, một `Ticket` vẫn được phân loại `NORMAL`. Selector `null` hoặc không phải `Ticket` được phân loại `NOT_TICKET`.

Nhánh `switch` ban đầu thường trông như sau:

```java
case Ticket(var id, Reporter(var email, var verified, var team),
            var impact, var down)
        when down && impact >= 3 && impact <= 5
             && verified && email != null
             && email.endsWith("@company.test")
             && ("SRE".equals(team) || "OPS".equals(team))
        -> "ESCALATE:" + id;
```

Đây là **nhánh của một `switch`**, không phải chương trình độc lập. Pattern thể hiện quan hệ `Ticket → Reporter`, nhưng guard buộc caller biết chi tiết về mức tác động, miền email và danh sách nhóm. Nếu quy tắc lặp lại trong nhiều nhánh/service, thay đổi chính sách có thể khiến các nơi lệch nhau.

**Mục tiêu refactor:** giữ pattern để nhận diện kiểu, lấy dữ liệu, nhưng chuyển ý nghĩa nghiệp vụ sang phương thức có tên:

```java
case Ticket(var id, Reporter(var email, var verified, var team),
            var impact, var down)
        when meetsEscalationRule(down, impact, verified, email, team)
        -> "ESCALATE:" + id;
```

Cách này giữ được biến `id` cho câu trả lời và chuyển độ phức tạp từ guard sang một helper có thể kiểm thử riêng.

## 2. Phân biệt pattern và predicate

| Thành phần | Nhiệm vụ | Ví dụ |
|---|---|---|
| Type pattern | Nhận diện kiểu và bind biến | `case Ticket ticket` |
| Record pattern | Kiểm tra record và phân rã component | `Ticket(var id, ...)` |
| Nested record pattern | Yêu cầu nested record tồn tại để phân rã | `Reporter(var email, ...)` |
| Guard `when` | Kiểm tra bổ sung sau khi pattern đã khớp | `when impact >= 3 && verified` |
| Helper boolean | Đặt tên cho điều kiện logic/nghiệp vụ | `meetsEscalationRule(...)` |

**Ranh giới quan trọng:** `Reporter(...)` là record pattern, nên không khớp nếu `Ticket.reporter() == null`. Tuy nhiên `Reporter(var email, ...)` có thể bind `email == null` vì component lá kiểu tham chiếu được phép null. Tách predicate không được làm mất hai hành vi này.

Một phương thức `boolean` chỉ trả về đúng/sai. Nó không tạo pattern variables cho caller, không tự thay đổi loại record được `switch` khớp và không đóng vai trò một record pattern mới.

## 3. Tách guard theo những câu hỏi có tên

Tách quy tắc thành ba phương thức:

```java
static boolean isWorkEmail(String email) {
    return email != null && email.endsWith("@company.test");
}

static boolean isResponseTeam(String team) {
    return "SRE".equals(team) || "OPS".equals(team);
}

static boolean meetsEscalationRule(boolean down, int impact,
        boolean verified, String email, String team) {
    return down && impact >= 3 && impact <= 5
            && verified && isWorkEmail(email)
            && isResponseTeam(team);
}
```

Đây là **đoạn minh họa**, toàn bộ mã chạy được đặt trong mục 5.

- `meetsEscalationRule` diễn tả quyết định chuyển mức xử lý.
- `isWorkEmail` giữ kiểm tra `null` trước khi gọi `endsWith`.
- `isResponseTeam` gom hai lựa chọn SRE/OPS bằng `||`, tránh lỗi đặt dấu ngoặc ở caller.
- Các helper đều **thuần túy**: không thay đổi trạng thái, không I/O, không đọc giờ hiện tại, nên dễ kiểm thử và ít gây thay đổi ngoài ý muốn.

Không phải mọi phép so sánh đều cần một helper. Một điều kiện đơn giản, chỉ xuất hiện một lần và không có ý nghĩa riêng có thể giữ trực tiếp; nên tách những nhóm điều kiện làm cho tên phương thức dễ hiểu hơn cả biểu thức.

## 4. Các bước refactor an toàn

### Bước 1 — Chốt hành vi trước khi sửa

Cần ghi nhận các kết quả:

| Input | Kết quả |
|---|---|
| Selector `null` hoặc sai kiểu | `NOT_TICKET` |
| Ticket thiếu reporter | `NORMAL:<id>` |
| Có Reporter nhưng guard sai | `NORMAL:<id>` |
| Reporter tồn tại và mọi điều kiện đúng | `ESCALATE:<id>` |

Danh sách này giúp kiểm thử sự tương đương của bản trước và sau; đừng sửa chính sách trong cùng đợt refactor.

### Bước 2 — Giữ pattern, chỉ thay guard

Giữ nguyên `Ticket(var id, Reporter(...), ...)` và nhánh fallback. Chuyển phần sau `when` thành `meetsEscalationRule(down, impact, verified, email, team)`. Đây là bước nhỏ, tránh đổi đồng thời cấu trúc và nghiệp vụ.

### Bước 3 — Giữ nhóm ngoặc và ưu tiên toán tử

Điều kiện đúng:

```java
down && verified && ("SRE".equals(team) || "OPS".equals(team))
```

Nếu lỡ viết:

```java
down && verified && "SRE".equals(team) || "OPS".equals(team)
```

thì do `&&` có ưu tiên cao hơn `||`, biểu thức tương đương:

```java
(down && verified && "SRE".equals(team)) || "OPS".equals(team)
```

Khi `team == "OPS"`, điều kiện sai có thể thành đúng dù `down == false` hoặc `verified == false`. Helper `isResponseTeam` làm rõ nhóm OR và giảm cơ hội thay đổi ý nghĩa.

### Bước 4 — Giữ short-circuit và null contract

`&&` đánh giá từ trái sang phải và ngừng khi gặp `false`:

```java
email != null && email.endsWith("@company.test")
```

Điều kiện này an toàn; còn `email.endsWith("@company.test") && email != null` có thể ném `NullPointerException`. Không chuyển một phép gọi có side effect hoặc có thể ném exception sang vị trí mới mà không kiểm tra tác động đến thứ tự đánh giá. Tương tự, `"SRE".equals(team)` an toàn với null nhưng `team.equals("SRE")` thì không.

### Bước 5 — So sánh kết quả thực tế

Kiểm tra các giá trị biên 3/5, ngoài biên 2/6, email null, team null, reporter null, root null, kiểu khác và trường hợp đủ điều kiện của cả SRE và OPS. Đừng chỉ kiểm tra một đường đi thành công.

## 5. Ví dụ Java 21 đầy đủ và kiểm tra hồi quy

Tạo tệp **`PatternPredicateExtractionDemo.java`**:

```java
public class PatternPredicateExtractionDemo {
    record Reporter(String email, boolean verified, String team) {}
    record Ticket(String id, Reporter reporter, int impact, boolean serviceDown) {}

    // BEFORE: nested record pattern và nhiều điều kiện trong guard.
    static String before(Object input) {
        return switch (input) {
            case null -> "NOT_TICKET";
            case Ticket(var id, Reporter(var email, var verified, var team),
                        var impact, var down)
                    when down && impact >= 3 && impact <= 5
                         && verified && email != null
                         && email.endsWith("@company.test")
                         && ("SRE".equals(team) || "OPS".equals(team))
                    -> "ESCALATE:" + id;
            case Ticket(var id, var reporter, var impact, var down) -> "NORMAL:" + id;
            default -> "NOT_TICKET";
        };
    }

    // Điều kiện có tên, null-safe.
    static boolean isWorkEmail(String email) {
        return email != null && email.endsWith("@company.test");
    }

    static boolean isResponseTeam(String team) {
        return "SRE".equals(team) || "OPS".equals(team);
    }

    static boolean meetsEscalationRule(boolean down, int impact,
            boolean verified, String email, String team) {
        return down && impact >= 3 && impact <= 5
                && verified && isWorkEmail(email)
                && isResponseTeam(team);
    }

    // AFTER: pattern cũ, guard gọi predicate có tên.
    static String after(Object input) {
        return switch (input) {
            case null -> "NOT_TICKET";
            case Ticket(var id, Reporter(var email, var verified, var team),
                        var impact, var down)
                    when meetsEscalationRule(down, impact, verified, email, team)
                    -> "ESCALATE:" + id;
            case Ticket(var id, var reporter, var impact, var down) -> "NORMAL:" + id;
            default -> "NOT_TICKET";
        };
    }

    // Mức refactor thứ hai: helper nhận domain type.
    static boolean isEscalatable(Ticket ticket) {
        if (ticket == null || ticket.reporter() == null) {
            return false;
        }
        Reporter reporter = ticket.reporter();
        return meetsEscalationRule(ticket.serviceDown(), ticket.impact(),
                reporter.verified(), reporter.email(), reporter.team());
    }

    static String byDomainPredicate(Object input) {
        return switch (input) {
            case null -> "NOT_TICKET";
            case Ticket ticket when isEscalatable(ticket) -> "ESCALATE:" + ticket.id();
            case Ticket ticket -> "NORMAL:" + ticket.id();
            default -> "NOT_TICKET";
        };
    }

    // instanceof kết hợp &&: helper chỉ gọi sau khi pattern khớp.
    static boolean predicateOnly(Object input) {
        return input instanceof Ticket(
                var id, Reporter(var email, var verified, var team),
                var impact, var down)
                && meetsEscalationRule(down, impact, verified, email, team);
    }

    static void check(String label, Object input) {
        String initial = before(input);
        String extracted = after(input);
        String domain = byDomainPredicate(input);
        boolean predicate = predicateOnly(input);
        if (!initial.equals(extracted)
                || !initial.equals(domain)
                || predicate != initial.startsWith("ESCALATE:")) {
            throw new AssertionError(label + ": " + initial + "/"
                    + extracted + "/" + domain + "/" + predicate);
        }
        System.out.println(label + " -> " + extracted);
    }

    public static void main(String[] args) {
        check("null root", null);
        check("wrong type", "text");
        check("SRE qualifies", new Ticket("T01",
                new Reporter("a@company.test", true, "SRE"), 3, true));
        check("OPS qualifies", new Ticket("T02",
                new Reporter("b@company.test", true, "OPS"), 5, true));
        check("not down", new Ticket("T03",
                new Reporter("a@company.test", true, "SRE"), 4, false));
        check("low impact", new Ticket("T04",
                new Reporter("a@company.test", true, "SRE"), 2, true));
        check("too high impact", new Ticket("T05",
                new Reporter("a@company.test", true, "SRE"), 6, true));
        check("unverified", new Ticket("T06",
                new Reporter("a@company.test", false, "SRE"), 4, true));
        check("null email", new Ticket("T07",
                new Reporter(null, true, "OPS"), 4, true));
        check("other email", new Ticket("T08",
                new Reporter("a@elsewhere.test", true, "OPS"), 4, true));
        check("other team", new Ticket("T09",
                new Reporter("a@company.test", true, "DEV"), 4, true));
        check("null team", new Ticket("T10",
                new Reporter("a@company.test", true, null), 4, true));
        check("missing reporter", new Ticket("T11", null, 4, true));
        check("null id", new Ticket(null,
                new Reporter("a@company.test", true, "SRE"), 4, true));
    }
}
```

Biên dịch và chạy bằng JDK 21+:

```bash
javac --release 21 PatternPredicateExtractionDemo.java
java PatternPredicateExtractionDemo
```

**Stdout đã xác minh bằng Java:**

```text
null root -> NOT_TICKET
wrong type -> NOT_TICKET
SRE qualifies -> ESCALATE:T01
OPS qualifies -> ESCALATE:T02
not down -> NORMAL:T03
low impact -> NORMAL:T04
too high impact -> NORMAL:T05
unverified -> NORMAL:T06
null email -> NORMAL:T07
other email -> NORMAL:T08
other team -> NORMAL:T09
null team -> NORMAL:T10
missing reporter -> NORMAL:T11
null id -> ESCALATE:null
```

Mỗi lời gọi `check(...)` so sánh **bốn kết quả**: chuỗi trước refactor, sau refactor, khi đóng gói theo domain type, và boolean từ `instanceof` kết hợp `&&`. Có sai lệch thì ném `AssertionError`. Các trường hợp trên chạy thành công với `javac --release 21`; đây là bằng chứng cho các input mẫu, còn test production cần bao phủ thêm invariant của domain.

Tình huống `null id` cố ý giữ hành vi cũ: `var id` trong record pattern có thể bind null, nên `"ESCALATE:" + id` cho ra `ESCALATE:null`. Nếu domain yêu cầu ID bắt buộc, hãy validate riêng thay vì âm thầm sửa quy tắc khi đang refactor.

## 6. Scope của pattern variables khi tách phương thức

Trong một nhánh `switch`, biến `email` chỉ được sử dụng sau khi pattern chứa nó khớp:

```java
case Ticket(var id, Reporter(var email, var verified, var team),
            var impact, var down)
        when meetsEscalationRule(down, impact, verified, email, team)
        -> "ESCALATE:" + id;
```

Trong `instanceof` kết hợp `&&`, compiler biết các biến đã được bind ở vế trái trước khi gọi helper ở vế phải:

```java
static boolean predicateOnly(Object input) {
    return input instanceof Ticket(
            var id, Reporter(var email, var verified, var team),
            var impact, var down)
            && meetsEscalationRule(down, impact, verified, email, team);
}
```

Nhờ short-circuit, `meetsEscalationRule` không được gọi nếu selector không phải `Ticket` hoặc `Reporter` là null. Đây là **đoạn trùng với phương thức trong chương trình đã chạy**, không cần cast thủ công.

**Không thể mang pattern variables ra khỏi boolean helper:**

```java
boolean escalated = predicateOnly(input);
// Biến 'email' và 'id' khai báo trong predicateOnly()
// không có scope tại caller này.
```

Nếu caller cần `id`/`email` để hiển thị hoặc xử lý, nên giữ pattern trong caller và chỉ tách guard. Hoặc bind một `Ticket ticket` ở caller, gọi `isEscalatable(ticket)` rồi lấy `ticket.id()`. Khi thực sự cần trả nhiều giá trị sau validation, hãy dùng kiểu kết quả có cấu trúc (record hoặc `Optional<Result>`), thay vì trông đợi biến pattern tồn tại ngoài scope của nó.

**Cú pháp:** `when` thuộc guard của `case` trong `switch`, không dùng trực tiếp sau `instanceof`. Với `instanceof` dùng `&& predicate(...)`.

## 7. Hai cấp độ refactor và cách chọn

### Cấp A — Giữ nested pattern, chỉ tách guard

```java
case Ticket(var id, Reporter(var email, var verified, var team),
            var impact, var down)
        when meetsEscalationRule(down, impact, verified, email, team)
        -> "ESCALATE:" + id;
```

Cách này phù hợp khi nhánh `switch` vẫn cần các biến đã phân rã, muốn thể hiện cấu trúc input và guard là phần gây khó đọc nhất. Việc đổi nhỏ giúp dễ đối chiếu tính tương đương.

### Cấp B — Chuyển sang predicate nhận kiểu domain

```java
case Ticket ticket when isEscalatable(ticket)
        -> "ESCALATE:" + ticket.id();
```

Cách này phù hợp khi nhiều caller cùng hỏi “ticket này có cần escalated không?”. Caller không cần biết `Reporter` chứa email hay team. Phương thức `isEscalatable(Ticket)` phải kiểm tra null của reporter, vì nested record pattern ban đầu loại trừ reporter null.

Trong hệ thống lớn, có thể đưa predicate vào `Ticket` hoặc một policy/domain service tùy nơi sở hữu quy tắc. Nếu phụ thuộc cấu hình thay đổi, thời gian, cơ sở dữ liệu hay network, hãy cung cấp dependency/policy rõ ràng, không giấu I/O trong predicate của một `switch`.

Không nên đặt mọi helper vào `Utils` chung chỉ vì có thể tái sử dụng; tên và vị trí cần phản ánh domain.

## 8. Những ngữ nghĩa phải giữ nguyên

### 8.1. Root null và nested null

- `case null` bắt selector null. `default` không mặc nhiên là cách xử lý selector null trong pattern `switch`; thiếu nhánh xử lý có thể gây `NullPointerException`.
- `case Ticket(var id, Reporter(...), ...)` không khớp khi `reporter == null`. Nhánh `case Ticket(var id, var reporter, ...)` rộng hơn sẽ xử lý và trả `NORMAL`.
- `case Ticket ticket when isEscalatable(ticket)` khớp kiểu Ticket trước, rồi helper phải kiểm tra `ticket.reporter() == null` để giữ kết quả như nested pattern cũ.
- Bên trong một `Reporter` khác null, `email == null` hoặc `team == null` vẫn có thể xuất hiện: helper dùng `email != null` và `"SRE".equals(team)` để an toàn.

### 8.2. Thứ tự các nhánh switch

```java
case Ticket ticket when isEscalatable(ticket) -> "ESCALATE";
case Ticket ticket -> "NORMAL";
```

Nhánh có guard phải đứng trước nhánh `Ticket ticket` không guard. Nếu đảo lại, nhánh rộng che nhánh hẹp (**dominated case label**), Java báo lỗi biên dịch. Với các guard độc lập có thể đồng thời đúng, thứ tự các `case` còn quyết định kết quả; đừng đổi thứ tự mà chưa kiểm chứng.

### 8.3. Giới hạn số và phép OR

Nếu ban đầu có `impact >= 3 && impact <= 5`, helper phải giữ cả hai biên. Chuyển thành `impact < 5` sẽ đổi quyết định với impact 5. Thay nhóm `SRE || OPS` thành `SRE && OPS` sẽ khiến ticket không thể đáp ứng nếu team chỉ có một mã. Những thay đổi đó thuộc chính sách nghiệp vụ, không phải refactor.

### 8.4. Side effects và thứ tự gọi

Một biểu thức `&&`/`||` chỉ đánh giá phần cần thiết. Thêm log, truy vấn dịch vụ, tăng bộ đếm, đọc giờ hệ thống hoặc ném exception từ helper có thể làm chương trình hành xử khác dù boolean trong trường hợp thông thường giống nhau. Với dữ liệu và predicate phức tạp, nên ưu tiên helper thuần túy và ghi rõ các dependency bên ngoài.

### 8.5. Dễ đọc không đồng nghĩa với nhiều phương thức nhất

Nếu guard chỉ có `when impact >= 3`, việc tạo `isImpactAtLeastThree(...)` có thể làm code dài hơn. Nếu nó chứa nhiều nhóm điều kiện, được lặp lại, hoặc biểu đạt chính sách có tên miền riêng, việc tách thường có giá trị cao hơn. Tách theo ý nghĩa và ranh giới trách nhiệm.

## 9. Checklist áp dụng trên codebase

| Kiểm tra | Cần bảo đảm |
|---|---|
| Cấu trúc pattern | Giữ đúng kiểu record, thứ tự component, nested null-match |
| Scope | Mọi pattern variable chỉ được dùng nơi Java biết pattern khớp |
| Guard | Helper nhận đúng biến đã bind, trả kết quả cùng nghĩa |
| Toán tử | Giữ nhóm ngoặc, ưu tiên `&&`/`||`, short-circuit |
| Null | Root, nested record và component lá cho kết quả tương đương |
| Biên | Giữ `>=`, `<=` và tập giá trị đúng |
| Switch | Giữ nhánh có guard trước nhánh tổng quát, xử lý `case null` |
| Side effect | Không thêm tác dụng phụ/exception ngoài hợp đồng cũ |
| Kiểm thử | So sánh bản trước/sau với input thành công, thất bại và biên |

Ở dự án thực tế có thể dùng JUnit parameterized tests để truyền nhiều cấu hình ticket và kiểm tra output. Không cần test mọi helper chỉ để phản chiếu implementation; ưu tiên trường hợp biên và những thay đổi logic có thể quan sát được.

## 10. Lỗi phổ biến và cách sửa

- **Helper tên mơ hồ như `checkEverything`:** khó hiểu hơn biểu thức cũ. Hãy chọn tên gắn với nghiệp vụ, ví dụ `meetsEscalationRule`.
- **Viết `input instanceof Ticket(...) when ...`:** không hợp lệ. Dùng `instanceof Pattern && predicate(...)`.
- **Bỏ dấu ngoặc quanh điều kiện OR:** có thể khiến nhánh OPS bỏ qua các điều kiện down/verified.
- **Dùng biến pattern sau khi boolean method trả về:** các biến đó chỉ tồn tại trong scope của method, không được xuất ra.
- **Đổi thứ tự kiểm tra null và gọi phương thức:** có thể tạo `NullPointerException` mà code cũ không có.
- **Đặt `case Ticket ticket` trước nhánh có guard:** làm nhánh cụ thể bị dominated.
- **Bỏ fallback `NORMAL`:** ticket có kiểu hợp lệ nhưng không đủ điều kiện sẽ bị xử lý khác.
- **Cho rằng record pattern đảm bảo mọi component khác null:** record ở mỗi tầng phải tồn tại, nhưng các component tham chiếu vẫn có thể null.
- **Dời điều kiện có tác dụng phụ tùy tiện:** thay đổi số lần hoặc thứ tự đánh giá; nên giữ predicate thuần túy.
- **Gộp thay đổi chính sách với refactor:** khó biết lệch kết quả do bug hay yêu cầu mới; nên tách thành lần sửa riêng.

## 11. Câu hỏi tự kiểm tra

1. `Reporter` bằng `null` thì nhánh `Ticket(..., Reporter(...), ...)` có khớp không? **Không.** Nested record pattern loại trường hợp này trước guard.
2. `email == null` nhưng reporter khác null thì pattern có khớp không? **Có thể khớp.** `var email` nhận null; helper email sẽ trả `false`.
3. Vì sao `isResponseTeam` trả về `"SRE".equals(team) || "OPS".equals(team)`? **Vì đây là một nhóm OR thống nhất**, được dùng cùng với các điều kiện AND ở cấp cao hơn.
4. `predicateOnly(input)` trả `true` có cho caller sử dụng biến `id` bên trong không? **Không.** Trả boolean không chuyển scope của pattern variable.
5. Làm thế nào thêm predicate vào `instanceof`? **Dùng `&&`** phía sau pattern: `input instanceof Ticket(...) && meetsEscalationRule(...)`.
6. Vì sao `case Ticket ticket when isEscalatable(ticket)` phải trước `case Ticket ticket`? **Nhánh không guard bao phủ nhánh có guard** nếu đặt trước.
7. Nếu helper đổi `impact <= 5` thành `impact < 5` thì có còn là refactor bảo toàn hành vi không? **Không.** Ticket impact 5 bị đổi từ ESCALATE sang NORMAL.

## Ghi nhớ

**Pattern nhận diện và phân rã cấu trúc; predicate có tên biểu đạt điều kiện nghiệp vụ.** Khi kết hợp nested patterns và nhiều toán tử, có thể tách guard thành helper boolean, sau đó cân nhắc đưa quyết định về domain method nếu nhiều caller cần dùng. Để refactor an toàn trong Java 21, phải giữ scope biến, short-circuit, nhóm `&&`/`||`, xử lý null, thứ tự nhánh `switch` và kiểm tra đầu ra của các trường hợp biên.

## Tài liệu chính thức

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [JLS SE 21 — §15.23 Conditional-And Operator &&](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.23)
- [JLS SE 21 — §15.24 Conditional-Or Operator ||](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.24)
