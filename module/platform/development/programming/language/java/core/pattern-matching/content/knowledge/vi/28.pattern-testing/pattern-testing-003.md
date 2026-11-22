# Kiểm thử null trong instanceof (Java 21)

## Mục tiêu và phạm vi

Trong chủ đề **Kiểm thử** của Java Core Pattern Matching, một nguồn lỗi rất phổ biến là đoán sai hành vi của `instanceof` khi gặp `null`. Khi refactor từ kiểm tra kiểu truyền thống sang type pattern hoặc record pattern, cần kiểm tra **`null` ở selector**, **`null` ở record lồng nhau** và **`null` ở component lá** bằng các tình huống độc lập.

Bài này hướng dẫn:

- Giải thích vì sao `obj instanceof SomeType` và `obj instanceof SomeType x` trả `false` khi **`obj == null`**.
- Thiết kế bảng test gồm `null`, đúng kiểu, sai kiểu, chuỗi rỗng/trắng, nested record thiếu và component lá null.
- Phân biệt `instanceof Account(...)` (record ở root) với pattern chứa `Profile(...)` bên trong, và với `var profile` bind trực tiếp.
- Kiểm tra **flow scoping** của pattern variable và short-circuit của `&&` để tránh `NullPointerException`.
- Viết một chương trình Java 21 độc lập có assertions, expected results và stdout cố định để xác nhận hành vi.

**Phiên bản:** Java 21. Type pattern cho `instanceof` đã chính thức từ Java 16 (JEP 394); record patterns chính thức trong Java 21 (JEP 440). Chương trình dùng `javac --release 21` và không yêu cầu `--enable-preview`.

## 1. Quy tắc nền: null ở vế trái của instanceof

Xét:

```java
Object value = null;
boolean ordinary = value instanceof String;
boolean pattern = value instanceof String text;
```

Cả `ordinary` và `pattern` đều bằng **`false`**. `instanceof` không cố cast `null` sang `String`, và biến `text` **không được bind** nếu pattern không khớp.

Điều này vẫn đúng với kiểu rất rộng:

```java
Object value = null;
boolean result = value instanceof Object present; // false
```

Vì `null` không phải một thể hiện object, dù mọi object không null đều là một `Object`. Muốn phân biệt trường hợp thiếu dữ liệu, hãy kiểm tra `value == null` riêng.

Để không hiểu nhầm, hãy tách hai câu hỏi:

| Câu hỏi | Cách kiểm tra | Với `value == null` |
|---|---|---|
| “Có phải null không?” | `value == null` | `true` |
| “Có phải String không null không?” | `value instanceof String s` | `false` |
| “Có phải Object không null không?” | `value instanceof Object o` | `false` |
| “Không phải String?” | `!(value instanceof String s)` | `true` |

**Cẩn thận với phủ định:** `!(value instanceof String s)` đúng khi value null, nhưng cũng đúng với mọi giá trị sai kiểu. Nếu cần phân biệt lý do, hãy viết các nhánh tường minh: null / sai kiểu / đúng kiểu.

## 2. Type pattern khớp kiểu nhưng không thay hợp đồng null

Ví dụ:

```java
static String message(Object input) {
    if (input instanceof String text) {
        return "length=" + text.length();
    }
    return "not a string";
}
```

Đây là một phương thức minh họa độc lập. Với `null`, nó trả `not a string`, không ném `NullPointerException`, vì chỉ gọi `text.length()` khi pattern khớp.

Cách refactor truyền thống:

```java
// Trước:
if (input instanceof String) {
    String text = (String) input;
    return text.length();
}

// Sau:
if (input instanceof String text) {
    return text.length();
}
```

Cả hai xử lý input null giống nhau: nhánh không chạy. Vì thế test của bản refactor phải chứa **case null**, chứ không chỉ case đúng kiểu.

**Không suy luận ngược:** việc nhánh `if` an toàn không có nghĩa bất kỳ thao tác nào trên biến `input` đều an toàn. Ví dụ `input.toString()` trước `instanceof` vẫn có thể ném lỗi khi input null.

## 3. Khi có record pattern: ba vị trí null khác nhau

Giả sử có các record:

```java
record Profile(String nickname) {}
record Account(String id, Profile profile) {}
```

Xét pattern:

```java
value instanceof Account(String id, Profile(String nickname))
```

Ở Java 21, các tình huống sau cần phân biệt:

### 3.1. Root null

Nếu `value == null` thì toàn bộ `Account(...)` không khớp. `instanceof` trả `false`.

### 3.2. Nested record null

Nếu `value = new Account("A2", null)`, record `Account` tồn tại nhưng component `profile` bằng null. Nested **record pattern** `Profile(String nickname)` **không** khớp `null`. Cả pattern sâu thất bại; `instanceof` trả `false`.

### 3.3. Component lá null

Nếu `value = new Account("A3", new Profile(null))`, nested record `Profile` **tồn tại**. Component `nickname` được khai báo kiểu `String` và pattern con `String nickname` là **unconditional đối với kiểu component đó**, nên trong record deconstruction nó có thể bind `null`. Pattern sâu vì vậy **khớp thành công**.

Tương tự, với `new Account(null, new Profile("An"))`, component `id` được bind null mà không làm thất bại record pattern.

Điểm dễ nhầm là câu “type patterns không khớp null” ở cấp `obj instanceof String s` **không** được áp dụng máy móc cho **type pattern trực tiếp ở component của record pattern**. Cơ chế null-matching của nested component được JLS Java 21 mô tả riêng cho record patterns và các unconditional patterns.

### 3.4. Dừng deconstruction ở var pattern

Nếu không cần phân rã profile, có thể viết:

```java
value instanceof Account(var id, var profile)
```

Pattern này khớp một `Account` khác null **dù `profile == null`**: `var profile` trực tiếp trong component bind cả null. Sau đó code có thể kiểm tra `profile == null`. Nó không tương đương với `Profile(var nickname)` vì cái sau yêu cầu bản thân record Profile tồn tại.

| Input | `Account(String id, Profile(String nick))` | `Account(var id, var profile)` |
|---|---|---|
| `null` | `false` | `false` |
| `"text"` | `false` | `false` |
| `new Account("A1", new Profile("Lan"))` | `true` | `true` |
| `new Account("A2", null)` | **`false`** | **`true`** |
| `new Account("A3", new Profile(null))` | **`true`** | `true` |
| `new Account(null, new Profile("An"))` | **`true`** | `true` |
| `new Account(null, null)` | `false` | `true` |

Bảng này là trọng tâm kiểm thử: **root null, nested record null và leaf null** không có cùng semantics.

## 4. Kiểm thử short-circuit với &&

Câu lệnh:

```java
return value instanceof Account(var id, Profile(var nickname))
        && nickname != null
        && !nickname.isBlank();
```

được đánh giá từ trái sang phải. Khi `value` không phải `Account` hoặc `profile == null`, vế trái `instanceof` trả false; các toán hạng tiếp theo **không chạy**. Khi nickname null, toán hạng `nickname != null` trả false; `nickname.isBlank()` không được gọi.

Vì vậy biểu thức có ba trường hợp:

- Account và Profile tồn tại, nickname có ký tự không phải whitespace → `true`.
- Account/Profile thiếu hoặc nickname null/rỗng/trắng → `false`.
- Value root null hoặc sai kiểu → `false`.

Hãy cố ý thêm test với `new Profile(null)` và `new Profile("  ")`. Chỉ test nickname `"Lan"` sẽ không thể phát hiện một lỗi như bỏ `nickname != null` trước `nickname.isBlank()`.

**Phản ví dụ nguy hiểm:**

```java
// Không an toàn nếu nickname có thể null:
return value instanceof Account(var id, Profile(var nickname))
        && !nickname.isBlank();
```

Đoạn này có thể ném `NullPointerException` dù pattern deconstruction thành công, bởi nickname là **component lá tham chiếu** và được phép null.

Thứ tự cũng quan trọng:

```java
// Sai thứ tự nếu nickname có thể null:
nickname.isBlank() || nickname == null

// An toàn để kiểm tra "không có nickname" hoặc "nickname trắng":
nickname == null || nickname.isBlank()
```

Vế phải của `||` chỉ chạy khi vế trái false. Kiểm thử cần kiểm tra cả **giá trị trả về lẫn việc không ném exception**.

## 5. Flow scoping khi phủ định instanceof

Một mẫu hợp lệ để xử lý sai kiểu/null sớm:

```java
static String scopedId(Object value) {
    if (!(value instanceof Account account)) {
        return "NOT_ACCOUNT";
    }
    return "ACCOUNT:" + account.id();
}
```

Java biết rằng để vượt qua `if` mà không `return`, pattern `Account account` phải đã khớp. Vì vậy biến `account` tồn tại ở câu lệnh `return` sau đó. Với root null, phủ định đúng và phương thức trả `NOT_ACCOUNT`; không gọi `account.id()`.

Đừng nhầm với mã không hợp lệ:

```java
if (value instanceof Account account) {
    System.out.println(account.id());
}
// Không được giả định 'account' luôn có scope tại đây:
// có thể nhánh instanceof đã không khớp.
```

Các đoạn minh họa trên giả định `Account` đã được khai báo. Mục 6 có toàn bộ phương thức chạy được trong một lớp.

## 6. Chương trình Java 21 hoàn chỉnh có kiểm thử tự động

Tạo tệp **`NullInstanceofTestDemo.java`**. Không dùng thư viện ngoài; mỗi dòng `test(...)` chứa **expected results** và sẽ ném `AssertionError` nếu hành vi thực tế khác kỳ vọng.

```java
import java.util.Objects;

public class NullInstanceofTestDemo {
    record Profile(String nickname) {}
    record Account(String id, Profile profile) {}

    static String classify(Object value) {
        if (value instanceof Account(String id, Profile(String nickname))) {
            return "DEEP:" + id + "/" + nickname;
        }
        if (value instanceof Account(var id, var profile)) {
            return "SHALLOW:" + id + "/profile-null=" + (profile == null);
        }
        return "OTHER";
    }

    static boolean nonBlankNickname(Object value) {
        return value instanceof Account(var id, Profile(var nickname))
                && nickname != null
                && !nickname.isBlank();
    }

    static boolean isProfileMissing(Object value) {
        return value instanceof Account(var id, var profile)
                && profile == null;
    }

    static String scopedId(Object value) {
        if (!(value instanceof Account account)) {
            return "NOT_ACCOUNT";
        }
        return "ACCOUNT:" + account.id();
    }

    static String stringLength(Object value) {
        return value instanceof String text && !text.isBlank()
                ? "LEN:" + text.length() : "NO_TEXT";
    }

    static void test(String label, Object value, String expectedClassify,
                     boolean expectedNonBlank, boolean expectedMissing,
                     String expectedId, String expectedText) {
        String actualClassify = classify(value);
        boolean actualNonBlank = nonBlankNickname(value);
        boolean actualMissing = isProfileMissing(value);
        String actualId = scopedId(value);
        String actualText = stringLength(value);
        if (!Objects.equals(expectedClassify, actualClassify)
                || expectedNonBlank != actualNonBlank
                || expectedMissing != actualMissing
                || !Objects.equals(expectedId, actualId)
                || !Objects.equals(expectedText, actualText)) {
            throw new AssertionError(label + " => "
                    + actualClassify + "/" + actualNonBlank + "/"
                    + actualMissing + "/" + actualId + "/" + actualText);
        }
        System.out.println(label + " => " + actualClassify
                + ", nonBlank=" + actualNonBlank
                + ", missing=" + actualMissing
                + ", id=" + actualId
                + ", text=" + actualText);
    }

    public static void main(String[] args) {
        test("root null", null, "OTHER", false, false, "NOT_ACCOUNT", "NO_TEXT");
        test("other type", Integer.valueOf(7), "OTHER", false, false,
                "NOT_ACCOUNT", "NO_TEXT");
        test("text", "Hi", "OTHER", false, false, "NOT_ACCOUNT", "LEN:2");
        test("blank text", "  ", "OTHER", false, false, "NOT_ACCOUNT", "NO_TEXT");
        test("full", new Account("A1", new Profile("Lan")),
                "DEEP:A1/Lan", true, false, "ACCOUNT:A1", "NO_TEXT");
        test("profile null", new Account("A2", null),
                "SHALLOW:A2/profile-null=true", false, true, "ACCOUNT:A2", "NO_TEXT");
        test("nickname null", new Account("A3", new Profile(null)),
                "DEEP:A3/null", false, false, "ACCOUNT:A3", "NO_TEXT");
        test("nickname blank", new Account("A4", new Profile("  ")),
                "DEEP:A4/  ", false, false, "ACCOUNT:A4", "NO_TEXT");
        test("id null", new Account(null, new Profile("An")),
                "DEEP:null/An", true, false, "ACCOUNT:null", "NO_TEXT");
        test("both null", new Account(null, null),
                "SHALLOW:null/profile-null=true", false, true, "ACCOUNT:null", "NO_TEXT");

        Object ref = null;
        if (ref instanceof Object present) {
            throw new AssertionError("null instanceof Object must be false");
        }
        System.out.println("null instanceof Object -> false");
    }
}
```

Biên dịch và chạy trên JDK 21 trở lên:

```bash
javac --release 21 NullInstanceofTestDemo.java
java NullInstanceofTestDemo
```

**Stdout đã kiểm chứng trực tiếp:**

```text
root null => OTHER, nonBlank=false, missing=false, id=NOT_ACCOUNT, text=NO_TEXT
other type => OTHER, nonBlank=false, missing=false, id=NOT_ACCOUNT, text=NO_TEXT
text => OTHER, nonBlank=false, missing=false, id=NOT_ACCOUNT, text=LEN:2
blank text => OTHER, nonBlank=false, missing=false, id=NOT_ACCOUNT, text=NO_TEXT
full => DEEP:A1/Lan, nonBlank=true, missing=false, id=ACCOUNT:A1, text=NO_TEXT
profile null => SHALLOW:A2/profile-null=true, nonBlank=false, missing=true, id=ACCOUNT:A2, text=NO_TEXT
nickname null => DEEP:A3/null, nonBlank=false, missing=false, id=ACCOUNT:A3, text=NO_TEXT
nickname blank => DEEP:A4/  , nonBlank=false, missing=false, id=ACCOUNT:A4, text=NO_TEXT
id null => DEEP:null/An, nonBlank=true, missing=false, id=ACCOUNT:null, text=NO_TEXT
both null => SHALLOW:null/profile-null=true, nonBlank=false, missing=true, id=ACCOUNT:null, text=NO_TEXT
null instanceof Object -> false
```

**Đọc kết quả:**

- `root null`: cả type/record patterns đều không khớp. Không có pattern variable ở root được bind.
- `other type`: `Integer` không phải Account/String; kết quả tương tự root null nhưng **lý do khác nhau**.
- `text` và `blank text`: cùng là String, nên type pattern khớp; biểu thức có `!text.isBlank()` tiếp tục phân loại nội dung.
- `full`: Account và Profile tồn tại, nickname không rỗng/trắng → deep match và predicate đúng.
- `profile null`: nested `Profile(...)` không khớp; pattern `Account(var id, var profile)` vẫn khớp, bind `profile == null`.
- `nickname null`: deep pattern vẫn khớp vì đó là component lá, nhưng `nonBlankNickname` trả false và không ném NPE.
- `nickname blank`: hai khoảng trắng được giữ trong chuỗi; deep match đúng, `isBlank()` làm predicate sai.
- `id null`: component id null không ngăn record pattern khớp. Chuỗi `DEEP:null/An` là hệ quả của nối chuỗi Java, không phải quy tắc xác thực ID.
- `both null`: root Account tồn tại; shallow match thành công, profile là null. Deep match không thành công.
- `null instanceof Object`: một phép khẳng định độc lập đảm bảo root null không bị nhận sai thành đối tượng.

Không phải mọi kết quả `false` đều là một lỗi; test phải xác minh **hợp đồng phân loại**, không cố gắng làm tất cả nhánh trả true.

## 7. Chọn test cases có khả năng phát hiện lỗi

Một bộ test tối thiểu có giá trị nên bao gồm:

| Nhóm | Input ví dụ | Lỗi được phát hiện |
|---|---|---|
| **Root null** | `null` | Tưởng rằng instanceof khớp null hoặc dereference trước check |
| **Sai kiểu** | `Integer.valueOf(7)` | Xử lý null và sai kiểu bằng cùng nhánh khi đáng lẽ cần phân biệt |
| **Đúng kiểu cơ bản** | `"Hi"` | Sai type pattern hoặc flow scope |
| **String blank** | `"  "` | Chỉ test kiểu mà bỏ qua guard nội dung |
| **Nested record null** | `new Account("A2", null)` | Nhầm nested record pattern với `var` component |
| **Leaf null** | `new Account("A3", new Profile(null))` | Tưởng toàn bộ record pattern thất bại khi leaf null; bỏ null guard |
| **ID null** | `new Account(null, new Profile("An"))` | Tưởng mỗi component của record đều non-null |
| **Root khác null, toàn bộ hợp lệ** | `new Account("A1", new Profile("Lan"))` | Pattern/guard không nhận case thành công |
| **Null kết hợp** | `new Account(null, null)` | Thiếu nhánh fallback với dữ liệu lồng nhau bị thiếu |

Tùy domain, hãy thêm input với subtype, record lồng nhiều tầng, collection rỗng, Unicode whitespace hoặc dữ liệu malformed. Nhưng **đừng tự suy ra mọi component record đều không null** trừ khi constructor hoặc boundary validation đã bảo đảm điều đó.

## 8. Kiểm tra ngoại lệ chứ không chỉ boolean

Một cách viết sai có thể trả đúng với input bình thường nhưng ném exception khi gặp null. Ví dụ:

```java
// Nguy hiểm khi value là Account chứa Profile(null):
if (value instanceof Account(var id, Profile(var nickname))
        && nickname.isBlank()) {
    System.out.println("Blank");
}
```

Trong Java 21, `Profile(var nickname)` có thể khớp với nickname null. Lỗi nằm ở lời gọi `nickname.isBlank()`, không phải bản thân `instanceof`. Để sửa:

```java
if (value instanceof Account(var id, Profile(var nickname))
        && nickname != null && nickname.isBlank()) {
    System.out.println("Blank (khác null)");
}
```

Hoặc nếu nghiệp vụ coi null và blank đều là “thiếu nickname”:

```java
if (value instanceof Account(var id, Profile(var nickname))
        && (nickname == null || nickname.isBlank())) {
    System.out.println("Missing nickname");
}
```

Ba đoạn này là **minh họa để chèn vào một method** nơi `value` đã được khai báo; không phải file Java độc lập. Các dấu ngoặc ở điều kiện `||` giữ rõ ý nghĩa.

Khi viết JUnit, nên dùng cả assertion về return value và `assertDoesNotThrow(...)` ở những biên mà null có thể xuất hiện. Với chương trình self-test của mục 6, chỉ cần một NPE phát sinh cũng khiến chương trình dừng và không thể in đủ 11 dòng, nên test phát hiện được rủi ro này.

## 9. Mẫu test JUnit 5 khi làm việc trong dự án

Chương trình ở mục 6 không phụ thuộc framework. Nếu dự án có JUnit Jupiter 5, bạn có thể viết một lớp test riêng để báo lỗi theo từng case:

```java
// Snippet minh họa, dùng khi dự án đã có JUnit 5 và đã
// truy cập được lớp NullInstanceofTestDemo.
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class NullInstanceofTests {
    @Test
    void nullRootDoesNotMatch() {
        assertEquals("OTHER", NullInstanceofTestDemo.classify(null));
        assertFalse(NullInstanceofTestDemo.nonBlankNickname(null));
        assertEquals("NOT_ACCOUNT", NullInstanceofTestDemo.scopedId(null));
    }

    @Test
    void nullNestedProfileFallsBack() {
        var account = new NullInstanceofTestDemo.Account("A2", null);
        assertEquals("SHALLOW:A2/profile-null=true",
                NullInstanceofTestDemo.classify(account));
        assertTrue(NullInstanceofTestDemo.isProfileMissing(account));
    }

    @Test
    void nullLeafIsSafeForGuard() {
        var account = new NullInstanceofTestDemo.Account(
                "A3", new NullInstanceofTestDemo.Profile(null));
        assertEquals("DEEP:A3/null", NullInstanceofTestDemo.classify(account));
        assertDoesNotThrow(() ->
                NullInstanceofTestDemo.nonBlankNickname(account));
        assertFalse(NullInstanceofTestDemo.nonBlankNickname(account));
    }
}
```

**Lưu ý:** đây là **test snippet cần đặt trong cùng package với lớp ví dụ** và cấu hình dependency JUnit 5 thích hợp; không thể biên dịch chỉ bằng `javac --release 21` nếu thiếu JUnit. Chương trình mục 6 mới là ví dụ độc lập đã được thực thi và đối chiếu stdout.

Trong hệ thống thật, có thể chuyển dữ liệu test thành parameterized tests, nhưng đừng gom tất cả case null thành một assertion duy nhất. Mỗi mức null (root/nested/leaf) cần tên test và expected behavior riêng để khi thất bại dễ truy tìm nguyên nhân.

## 10. Những lỗi thường gặp khi kiểm thử null với pattern matching

### 10.1. Chỉ test Object không null

Test duy nhất với `"abc"` không thể phát hiện việc bỏ nhánh null hoặc gọi `toString()` trước kiểm tra. Thêm một test root null độc lập.

### 10.2. Cho rằng `instanceof String s` “chấp nhận null”

Không đúng cho selector ở root. `null instanceof String` và `value instanceof String s` khi value null đều trả false.

### 10.3. Cho rằng mọi null bên trong record đều khiến pattern thất bại

Sai: component lá kiểu tham chiếu có thể được bind null nếu pattern con unconditional với kiểu component. Điều làm record pattern lồng nhau thất bại là **bản thân nested record** bằng null.

### 10.4. Không test `var profile` và `Profile(...)` riêng

Hai cách viết không đồng nghĩa khi profile null. Test `Account("A2", null)` phải thể hiện deep không khớp và shallow khớp.

### 10.5. Đặt dereference ở trước null check

`nickname.isBlank() && nickname != null` có thể ném lỗi. Dùng `nickname != null && !nickname.isBlank()` hoặc logic `nickname == null || nickname.isBlank()` tùy yêu cầu.

### 10.6. Hiểu sai flow scoping

Pattern variable chỉ dùng được khi compiler có thể chứng minh pattern đã khớp. Tránh sử dụng biến ngoài nhánh không bảo đảm match. Test compile được là một điều kiện cần, nhưng còn phải test runtime null.

### 10.7. Chỉ kiểm tra output mà bỏ exception contract

Nếu bản trước trả `false` với null còn bản sau ném NPE, đó là thay đổi hành vi. Test phải làm lỗi nổi lên, không nuốt exception tùy tiện.

### 10.8. Dùng `switch default` để suy ra quy tắc của instanceof

`switch` có cú pháp `case null` riêng và những quy tắc exhaustive/dominance khác. `instanceof` không có `default`; với selector null, nó trả false. Đừng gom hai cơ chế này làm một khi viết expected behavior.

### 10.9. Chỉ test một tầng null

Một test `value == null` không đủ chứng minh rằng `new Account("A", null)` và `new Account("A", new Profile(null))` được xử lý đúng. Kiểm thử từng tầng của cấu trúc dữ liệu.

## 11. Quy trình kiểm thử trước và sau refactor

Khi chuyển legacy cast sang record patterns hoặc type patterns:

1. **Xác định hợp đồng cũ:** có chấp nhận root null không? Khi nested field thiếu thì trả về gì? Có phân biệt sai kiểu và thiếu dữ liệu không?
2. **Lập bảng input:** root null, sai kiểu, đúng kiểu, nested record null, leaf null, chuỗi trống/trắng và dữ liệu đầy đủ.
3. **Thêm expected results độc lập:** không chỉ viết `assertEquals(before(input), after(input))`, vì hai phiên bản có thể cùng sai.
4. **Kiểm tra type pattern:** null root luôn làm `instanceof` trả false; không được dựa vào pattern variable khi match thất bại.
5. **Kiểm tra record patterns:** nested record null không khớp; direct `var`/unconditional component pattern có thể bind null.
6. **Kiểm tra short-circuit:** đặt null guard trước method call; tránh NPE khi component lá null.
7. **Chạy `javac --release 21`:** bắt lỗi cú pháp/scope/typing của patterns đúng theo phiên bản mục tiêu.
8. **Chạy test và đọc đủ stdout:** có AssertionError hoặc exception thì không đánh dấu pass.
9. **Review output và exception contract:** xác nhận không mất nhánh fallback sau refactor.
10. **Bổ sung test tích hợp khi cần:** nhất là khi constructor/accessor record có validation, dùng dữ liệu từ nhiều module hoặc nullable fields từ API ngoài.

Đừng tách việc kiểm thử null thành “một lần test ở controller”: nơi nhận đầu vào, nơi deconstruct và nơi gọi hàm của component có thể có các giả định null khác nhau.

## 12. Bài tự kiểm tra

Dùng:

```java
record Box(String value) {}
record Envelope(Box box) {}
```

Giả sử selector có kiểu `Object`. Hãy dự đoán kết quả:

| Selector | Pattern | Kết quả |
|---|---|---|
| `null` | `Envelope(Box(var s))` | `false` |
| `new Envelope(null)` | `Envelope(Box(var s))` | `false` |
| `new Envelope(null)` | `Envelope(var box)` | **`true`**, box được bind null |
| `new Envelope(new Box(null))` | `Envelope(Box(var s))` | **`true`**, s được bind null |
| `new Envelope(new Box(""))` | `Envelope(Box(var s))` | **`true`**, s là chuỗi rỗng |
| `"hello"` | `Envelope(var box)` | `false` |

Các pattern fragments trên đặt trong biểu thức `selector instanceof ...`. Không thể dùng tên biến `s` sau một `if` nếu compiler không bảo đảm pattern khớp.

**Câu hỏi:**

1. Vì sao `value instanceof Object obj` trả false khi value null? **Vì null không phải instance object.**
2. Khi nested `Box` bằng null, `Box(var s)` có được phân rã không? **Không.**
3. Khi `Box` khác null nhưng `Box.value() == null`, `var s` có nhận null không? **Có.**
4. Nếu `s == null`, có được gọi `s.isBlank()` chỉ vì record pattern đã khớp không? **Không; phải guard.**
5. Điều kiện nào bảo đảm không gọi `isBlank()` với null? **`s != null && !s.isBlank()`**.
6. Vì sao phải test null root **và** null nested? **Vì chúng tác động đến các tầng pattern khác nhau và dễ bị refactor xử lý lệch.**

## Kết luận

Để kiểm thử `null` trong `instanceof` một cách chính xác, phải biết **null nằm ở đâu**. **Root selector null** khiến `instanceof` trả false. **Nested record null** làm nested record pattern không khớp. Nhưng **component lá null** có thể vẫn được bind bởi pattern unconditional tương ứng bên trong record pattern; lúc đó guard phải bảo vệ mọi dereference.

Một bộ test tốt cho Java 21 không chỉ kiểm tra case đúng kiểu. Nó phân biệt root/nested/leaf null, sai kiểu, short-circuit và biến pattern có scope hợp lệ, xác nhận cả **giá trị trả về lẫn việc không xuất hiện exception ngoài hợp đồng**. Chương trình self-test với expected results độc lập giúp biến các quy tắc này thành hành vi có thể kiểm chứng.

## Tài liệu tham khảo

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java Language Specification SE 21 — §15.20.2 The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [Java Language Specification SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java SE 21 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
