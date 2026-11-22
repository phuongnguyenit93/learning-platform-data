# Điều kiện phải có kiểu `boolean` hoặc `Boolean` được unboxing — Java 17+

## 1. Quy tắc quan trọng nhất

Trong Java, biểu thức đặt trong dấu ngoặc của `if` phải có kiểu **`boolean`** hoặc **`java.lang.Boolean`** có thể được *unboxing* thành `boolean`. Không thể dùng trực tiếp số, chuỗi hoặc tham chiếu đối tượng làm điều kiện chỉ vì chúng “có giá trị”.

~~~java
boolean ready = true;

if (ready) {
    System.out.println("ready");
}
~~~

**Expected stdout:**

~~~text
ready
~~~

Với `Boolean`, Java tự gọi chuyển đổi unboxing để lấy `boolean` khi cần:

~~~java
Boolean enabled = Boolean.TRUE;

if (enabled) {
    System.out.println("enabled");
}
~~~

**Expected stdout:**

~~~text
enabled
~~~

**Cảnh báo:** nếu `enabled == null`, unboxing gây `NullPointerException`. Vì vậy cần phân biệt:

- **`boolean` nguyên thủy:** chỉ có `true` hoặc `false`, không thể null.
- **`Boolean` lớp bao:** có thể mang `Boolean.TRUE`, `Boolean.FALSE` hoặc `null`; phải quy định cách xử lý null.

Bài này tập trung vào kiểu của điều kiện `if`, không mở rộng sang hệ thống rẽ nhánh hoặc vòng lặp nói chung.

## 2. Cú pháp `if` và kiểm tra kiểu tại compile time

Cú pháp cơ bản:

~~~java
if (condition) {
    // Chạy nếu condition có giá trị true
} else {
    // Chạy nếu condition có giá trị false
}
~~~

Compiler phải xác nhận `condition` có kiểu boolean/Boolean thích hợp **trước khi chạy**. Kết quả cụ thể true hay false chỉ quyết định nhánh được thực thi.

| Biểu thức trong `if (...)` | Hợp lệ? | Vì sao? |
|---|---|---|
| `true` | Có | Literal `boolean` |
| `ready` với `boolean ready` | Có | Biến `boolean` |
| `enabled` với `Boolean enabled` | Có | `Boolean` được unboxing |
| `score >= 60` | Có | Phép so sánh trả `boolean` |
| `value != 0` | Có | Phép so sánh trả `boolean` |
| `text != null` | Có | Phép so sánh tham chiếu với null trả `boolean` |
| `score` với `int score` | **Không** | `int` không phải điều kiện boolean |
| `text` với `String text` | **Không** | Java không coi String rỗng/không rỗng là truthy/falsy |
| `object` với `Object object` | **Không** | Java không coi object khác null là true |
| `boxedNumber` với `Integer boxedNumber` | **Không** | Unboxing `Integer` ra `int`, vẫn không phải boolean |

Ví dụ bị lỗi compile (giữ nguyên ở dạng comment để code ví dụ vẫn chạy):

~~~java
int count = 3;
// if (count) { } // SAI: int cannot be converted to boolean

String title = "Java";
// if (title) { } // SAI: String cannot be converted to boolean

Object object = Boolean.TRUE;
// if (object) { } // SAI: kiểu tĩnh Object, không phải Boolean
~~~

Ngay cả khi một biến `Object` **đang trỏ tới object `Boolean.TRUE`**, compiler nhìn thấy kiểu tĩnh `Object` trong `if (object)`. Muốn dùng, phải kiểm tra/chuyển kiểu phù hợp thay vì giả định Java tự đoán kiểu object ở runtime.

## 3. Chuyển ý nghĩa nghiệp vụ thành biểu thức boolean

Nếu đầu vào là số, hãy viết **phép so sánh tường minh**:

~~~java
int count = 3;

if (count > 0) {
    System.out.println("positive");
}

if (count != 0) {
    System.out.println("nonzero");
}
~~~

**Expected stdout:**

~~~text
positive
nonzero
~~~

Tương tự, với `String`:

~~~java
String title = "Java";
boolean valid = title != null && !title.isBlank();

if (valid) {
    System.out.println("valid title");
}
~~~

Ở đây `title != null`, `!title.isBlank()` và `valid` đều trả hoặc chứa giá trị **boolean**; `title` tự nó không phải điều kiện hợp lệ.

### Các biểu thức thường cho kết quả boolean

| Biểu thức | Kiểu kết quả |
|---|---|
| `a == b`, `a != b` | `boolean` |
| `x < y`, `x >= y` | `boolean` |
| `!active` | `boolean` |
| `hasAccess && isActive` | `boolean` |
| `isAdmin \|\| hasPermission` | `boolean` |
| `name == null` | `boolean` |
| `Boolean.TRUE.equals(flag)` | `boolean` |

**Đừng dùng giá trị số 0/1 thay `false`/`true`**: Java không thực hiện chuyển kiểu số → boolean ngầm định.

## 4. `Boolean` trong `if`: Java thực hiện unboxing

~~~java
Boolean boxedTrue = Boolean.TRUE;
Boolean boxedFalse = Boolean.FALSE;

if (boxedTrue) {
    System.out.println("true branch");
}

if (boxedFalse) {
    System.out.println("unexpected");
} else {
    System.out.println("false branch");
}
~~~

**Expected stdout:**

~~~text
true branch
false branch
~~~

Về ý nghĩa, `if (boxedTrue)` cần chuyển giá trị `Boolean` thành `boolean` để quyết định nhánh. Trường hợp này là **unboxing conversion**, không phải so sánh địa chỉ tham chiếu.

`Boolean` thường xuất hiện trong dữ liệu cho phép null, các collection/generic hoặc API trả kết quả ba trạng thái. Unboxing tiện lợi khi giá trị chắc chắn **khác null**, nhưng có thể gây lỗi runtime nếu dữ liệu thiếu.

## 5. `Boolean null`: hợp lệ khi biên dịch, lỗi khi chạy

~~~java
Boolean flag = null;

try {
    if (flag) {
        System.out.println("never printed");
    }
} catch (NullPointerException ex) {
    System.out.println("null Boolean -> NullPointerException");
}
~~~

**Expected stdout:**

~~~text
null Boolean -> NullPointerException
~~~

Mã **biên dịch hợp lệ** vì biến có kiểu tĩnh `Boolean`. Tuy nhiên, ở runtime, Java cần unbox giá trị null và ném `NullPointerException` **trước khi chọn nhánh**.

Lỗi không phải do `if` không chấp nhận `Boolean`; lỗi là do giá trị wrapper không thể unbox khi bằng null.

**Phân biệt hai loại lỗi:**

- `if (123)`: lỗi **compile time** vì điều kiện có kiểu `int`.
- `Boolean flag = null; if (flag)`: compile được, nhưng lỗi **runtime** khi unboxing.

## 6. Các cách kiểm tra `Boolean` nullable an toàn

Giả sử yêu cầu: **chỉ khi giá trị đúng là true mới cho phép**.

**Cách 1 — Guard với `&&`:**

~~~java
Boolean enabled = null;
boolean allowed = enabled != null && enabled;
System.out.println(allowed); // false
~~~

`&&` bỏ qua toán hạng phải khi `enabled != null` là false. Do đó, `enabled` không bị unbox lúc null.

**Cách 2 — Dùng `Boolean.TRUE.equals`:**

~~~java
Boolean enabled = null;
boolean allowed = Boolean.TRUE.equals(enabled);
System.out.println(allowed); // false
~~~

Lời gọi trên object hằng `Boolean.TRUE` không unbox `enabled`, và an toàn với null.

**Cách 3 — Phân biệt đủ ba trạng thái:**

~~~java
static String describe(Boolean flag) {
    if (flag == null) {
        return "UNKNOWN";
    }
    return flag ? "ON" : "OFF";
}
~~~

| Giá trị `Boolean` | `Boolean.TRUE.equals(flag)` | `describe(flag)` |
|---|---|---|
| `Boolean.TRUE` | true | `ON` |
| `Boolean.FALSE` | false | `OFF` |
| `null` | false | `UNKNOWN` |

**Quan trọng:** Nếu null mang ý nghĩa **chưa biết/chưa xác nhận**, không nên tự động coi null là false mà không có quyết định nghiệp vụ. `Boolean.TRUE.equals(flag)` phù hợp với quy tắc “chỉ true mới đạt”, nhưng cố ý không phân biệt false và null trong kết quả boolean.

## 7. `flag == true` không phải null guard

~~~java
Boolean flag = null;

// if (flag == true) { }
// Khi chạy: NullPointerException do phải unbox flag.
~~~

So sánh với primitive `true` có thể khiến `Boolean` phải unbox, nên vẫn nguy hiểm khi flag null.

**Nên dùng:**

~~~java
if (Boolean.TRUE.equals(flag)) {
    // Chỉ chạy khi flag khác null và có giá trị true
}
~~~

Hoặc:

~~~java
if (flag != null && flag) {
    // Kiểm tra null trước khi unbox
}
~~~

**Không lẫn hai ý nghĩa:**

- `flag == null`: kiểm tra tham chiếu null, an toàn.
- `flag == true`: kiểm tra giá trị logic bằng true, có thể unbox và gây NPE.
- `Boolean.TRUE.equals(flag)`: so **giá trị object** an toàn với null.

Để kiểm tra đúng false (không phải null):

~~~java
boolean explicitlyFalse = Boolean.FALSE.equals(flag);
~~~

Với `flag == null`, cả `Boolean.TRUE.equals(flag)` và `Boolean.FALSE.equals(flag)` đều false.

## 8. `&&` và `||`: đặt guard trước phép dùng giá trị

Java đánh giá các toán hạng của `&&` và `||` từ trái sang phải, có cơ chế **ngắn mạch**.

~~~java
Boolean approved = null;

boolean allowed = approved != null && approved;
boolean deniedOrUnknown = approved == null || !approved;

System.out.println(allowed);         // false
System.out.println(deniedOrUnknown); // true
~~~

- `approved != null && approved`: nếu approved null, bỏ qua vế phải, an toàn.
- `approved == null || !approved`: nếu approved null, bỏ qua vế phải, an toàn.
- `approved != null & approved`: toán tử `&` boolean **không ngắn mạch**, phải đánh giá vế phải và có thể NPE.
- `approved == null | !approved`: `|` cũng **không ngắn mạch**, có thể NPE.

Ví dụ `Boolean` trong **vế phải**:

~~~java
Boolean missing = null;

System.out.println(false && missing); // false, không unbox missing
System.out.println(true || missing);  // true, không unbox missing
~~~

Nhưng nếu **buộc phải đánh giá** nhánh chứa null, unboxing vẫn ném NPE:

~~~java
// boolean bad = true && missing; // NPE khi chạy
// boolean bad = false || missing; // NPE khi chạy
~~~

**Điều kiện bảo vệ phải được đặt trước thao tác nguy hiểm.** Chỉ xuất hiện toán tử `&&` ở đâu đó không đủ tạo an toàn nếu tham chiếu đã bị sử dụng khi chưa kiểm tra.

## 9. Phân biệt `=` với `==` trong điều kiện boolean

Một lỗi logic nguy hiểm:

~~~java
boolean granted = false;

if (granted = true) {
    System.out.println("entered");
}

System.out.println(granted);
~~~

**Expected stdout:**

~~~text
entered
true
~~~

`granted = true` là **biểu thức gán** có kiểu và giá trị `boolean`. Nó biên dịch hợp lệ, đặt `granted` thành true rồi khiến nhánh `if` chạy.

Nếu ý định chỉ là **kiểm tra**, hãy viết:

~~~java
if (granted) {
    // Kiểm tra true, không gán
}
~~~

Với số nguyên, `if (number = 1)` lại **không biên dịch** vì biểu thức gán có kiểu `int`, không phải boolean. Đây là lý do lỗi `if (booleanVariable = true)` đặc biệt dễ lọt qua compile time.

**Khuyến nghị:** tránh gán trạng thái bên trong điều kiện `if` trừ khi có lý do rất rõ; tách phép gán thành câu lệnh riêng.

## 10. Chuỗi `"true"` và `"false"` không phải kiểu boolean

~~~java
String input = "true";
// if (input) { } // SAI: String không phải boolean/Boolean
~~~

Nếu dữ liệu đến từ văn bản, cần **phân tích giá trị** trước:

~~~java
boolean enabled = Boolean.parseBoolean(input);
if (enabled) {
    System.out.println("parsed true");
}
~~~

**Expected stdout:**

~~~text
parsed true
~~~

`Boolean.parseBoolean(String)` trả true **chỉ nếu chuỗi bằng `"true"` không phân biệt chữ hoa/thường**; các giá trị khác (kể cả null) trả false. Do đó:

~~~java
System.out.println(Boolean.parseBoolean("yes")); // false
~~~

Nếu API phải **từ chối văn bản không hợp lệ** thay vì âm thầm coi là false, tự định nghĩa parser nghiêm ngặt:

~~~java
static boolean parseStrictBoolean(String value) {
    if ("true".equalsIgnoreCase(value)) {
        return true;
    }
    if ("false".equalsIgnoreCase(value)) {
        return false;
    }
    throw new IllegalArgumentException("invalid boolean text");
}
~~~

Parser trên phân biệt `"true"`, `"false"` với `"yes"`, `"1"` hay null. Chính sách trim khoảng trắng hoặc chấp nhận các từ khác phải được định nghĩa theo yêu cầu input cụ thể.

## 11. Ví dụ Java 17 hoàn chỉnh, chạy được bằng CLI

Tạo đúng file **`IfBooleanConditionDemo.java`**:

~~~java
public final class IfBooleanConditionDemo {
    private IfBooleanConditionDemo() {}

    static boolean inScoreRange(int score) {
        return score >= 0 && score <= 100;
    }

    static String describe(Boolean flag) {
        if (flag == null) {
            return "UNKNOWN";
        }
        return flag ? "ON" : "OFF";
    }

    static boolean parseStrictBoolean(String value) {
        if ("true".equalsIgnoreCase(value)) {
            return true;
        }
        if ("false".equalsIgnoreCase(value)) {
            return false;
        }
        throw new IllegalArgumentException("invalid boolean text");
    }

    public static void main(String[] args) {
        boolean active = true;
        if (active) {
            System.out.println("primitive true=entered");
        }
        if (!active) {
            System.out.println("not active=entered");
        } else {
            System.out.println("primitive else=entered");
        }

        int score = 75;
        if (inScoreRange(score)) {
            System.out.println("score in range=true");
        }
        int count = 3;
        if (count > 0) {
            System.out.println("numeric comparison=true");
        }

        Boolean enabled = Boolean.TRUE;
        if (enabled) {
            System.out.println("boxed true=entered");
        }

        Boolean disabled = Boolean.FALSE;
        if (disabled) {
            System.out.println("boxed false=entered");
        } else {
            System.out.println("boxed false=else");
        }

        Boolean missing = null;
        try {
            if (missing) {
                System.out.println("never printed");
            }
        } catch (NullPointerException ex) {
            System.out.println("null condition=NullPointerException");
        }

        System.out.println("safe &&="
                + (missing != null && missing));
        System.out.println("safe true equals="
                + Boolean.TRUE.equals(missing));
        System.out.println("safe false equals="
                + Boolean.FALSE.equals(missing));
        System.out.println("null state=" + describe(missing));
        System.out.println("true state=" + describe(Boolean.TRUE));
        System.out.println("false state=" + describe(Boolean.FALSE));

        try {
            boolean result = missing == true;
            System.out.println(result);
        } catch (NullPointerException ex) {
            System.out.println("null == true=NullPointerException");
        }

        try {
            boolean result = missing != null & missing;
            System.out.println(result);
        } catch (NullPointerException ex) {
            System.out.println("eager guard=NullPointerException");
        }

        System.out.println("skip &&=" + (false && missing));
        System.out.println("skip ||=" + (true || missing));

        try {
            boolean result = true && missing;
            System.out.println(result);
        } catch (NullPointerException ex) {
            System.out.println("evaluated null=NullPointerException");
        }

        boolean granted = false;
        if (granted = true) {
            System.out.println("assignment in if=entered");
        }
        System.out.println("granted after assignment=" + granted);

        String input = "TrUe";
        if (parseStrictBoolean(input)) {
            System.out.println("strict parsed=true");
        }
        System.out.println("strict false="
                + parseStrictBoolean("FALSE"));
        System.out.println("lenient yes="
                + Boolean.parseBoolean("yes"));

        try {
            parseStrictBoolean("yes");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid input=" + ex.getMessage());
        }
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; terminal đang ở thư mục chứa file. Chương trình chỉ dùng thư viện tiêu chuẩn JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IfBooleanConditionDemo.java
java -cp . IfBooleanConditionDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IfBooleanConditionDemo.java
java -cp . IfBooleanConditionDemo
~~~

### Exact expected stdout

~~~text
primitive true=entered
primitive else=entered
score in range=true
numeric comparison=true
boxed true=entered
boxed false=else
null condition=NullPointerException
safe &&=false
safe true equals=false
safe false equals=false
null state=UNKNOWN
true state=ON
false state=OFF
null == true=NullPointerException
eager guard=NullPointerException
skip &&=false
skip ||=true
evaluated null=NullPointerException
assignment in if=entered
granted after assignment=true
strict parsed=true
strict false=false
lenient yes=false
invalid input=invalid boolean text
~~~

### Các điểm cần tự kiểm tra

1. `boolean` primitive chạy theo true/false như mong đợi; số nguyên chỉ được dùng thông qua phép so sánh `count > 0`.
2. `Boolean.TRUE` và `Boolean.FALSE` được unbox để điều khiển `if`.
3. `if (missing)` biên dịch nhưng ném NPE khi runtime unbox null.
4. `missing != null && missing` và `Boolean.TRUE.equals(missing)` cho false **mà không ném lỗi**.
5. `describe(missing)` giữ riêng trạng thái UNKNOWN, không nhập nhằng với false.
6. `missing == true` và `missing != null & missing` ném NPE vì vẫn yêu cầu unboxing null.
7. `false && missing` và `true || missing` bỏ qua vế phải, không unbox; ngược lại `true && missing` phải đánh giá vế phải nên NPE.
8. `if (granted = true)` cho thấy lỗi gán thay vì kiểm tra có thể compile và thay đổi trạng thái.
9. Parser nghiêm ngặt chấp nhận chữ hoa/thường của `true`/`false`, từ chối `"yes"`; `Boolean.parseBoolean("yes")` lặng lẽ cho false.

## 12. Lỗi phổ biến và cách tránh

| Sai lầm | Hệ quả | Cách phù hợp |
|---|---|---|
| `if (1)` | Lỗi compile: int không phải boolean | `if (number != 0)` nếu muốn kiểm tra khác 0 |
| `if (text)` | Lỗi compile: String không phải boolean | `text != null && !text.isBlank()` |
| `if (object)` với Object trỏ Boolean.TRUE | Kiểu tĩnh Object không hợp lệ | Dùng Boolean có kiểu rõ hoặc kiểm tra/chuyển kiểu |
| `if (nullableFlag)` khi null | Runtime NPE do unboxing | Guard hoặc `Boolean.TRUE.equals` |
| `if (nullableFlag == true)` là null-safe | Vẫn cần unboxing | `Boolean.TRUE.equals(nullableFlag)` |
| `flag != null & flag` | `&` đánh giá cả vế phải | `flag != null && flag` |
| `flag == null \| !flag` | `\|` đánh giá cả vế phải | `flag == null \|\| !flag` |
| Coi `null` là `false` mà không xét nghiệp vụ | Mất thông tin “chưa biết” | Giữ trạng thái UNKNOWN nếu cần |
| `if (flag = true)` khi định kiểm tra | Gán true rồi nhánh chạy | `if (flag)` |
| Dùng `Boolean.parseBoolean("yes")` như parser bắt lỗi | Trả false thay vì báo input không hợp lệ | Validate văn bản tường minh |
| Đổi `Boolean` thành `boolean` khi dữ liệu nullable | Mất trạng thái null hoặc NPE trong quá trình unbox | Xác định hợp đồng dữ liệu trước khi đổi |

## 13. Bài tập có đáp án

### Bài A — tại sao `if (number)` sai?

~~~java
int number = 5;
// if (number) { System.out.println("yes"); }
~~~

**Đáp án:** `number` có kiểu `int`, Java không cho chuyển `int → boolean` ngầm định. Nếu muốn kiểm tra dương, viết `if (number > 0)`; nếu muốn khác 0, viết `if (number != 0)`.

### Bài B — unboxing null

~~~java
Boolean accepted = null;
// if (accepted) { System.out.println("accepted"); }
~~~

**Đáp án:** Nếu thực thi câu `if`, chương trình ném `NullPointerException`. Có thể thay bằng:

~~~java
if (Boolean.TRUE.equals(accepted)) {
    System.out.println("accepted");
}
~~~

Không in gì và không ném NPE.

### Bài C — ba trạng thái

Yêu cầu `Boolean` nhận true, false hoặc null, tương ứng in `ON`, `OFF`, `UNKNOWN`.

**Đáp án:**

~~~java
static String state(Boolean flag) {
    if (flag == null) return "UNKNOWN";
    return flag ? "ON" : "OFF";
}
~~~

Phải kiểm tra null **trước khi** cho `Boolean` tham gia `?:` với hai nhánh logic có thể dùng unboxing.

### Bài D — ngắn mạch khác toán tử `&`

~~~java
Boolean flag = null;
System.out.println(flag != null && flag);
// System.out.println(flag != null & flag);
~~~

**Đáp án:** dòng đầu in `false`, không NPE. Dòng comment nếu thực thi sẽ ném NPE do `&` không short-circuit.

### Bài E — gán hay so sánh?

~~~java
boolean ready = false;
if (ready = true) {
    System.out.println("inside");
}
System.out.println(ready);
~~~

**Đáp án:**

~~~text
inside
true
~~~

Đây là phép gán `ready = true` hợp lệ về kiểu, nhưng thường sai ý định. Dùng `if (ready)` để kiểm tra biến.

### Bài F — xử lý văn bản đầu vào

Có input `"TRUE"`, `"FALSE"`, `"yes"`. Chỉ hai giá trị đầu được coi hợp lệ, không phân biệt hoa/thường.

**Đáp án:** dùng `parseStrictBoolean` ở chương trình đầy đủ, trả true cho TRUE, false cho FALSE và ném `IllegalArgumentException` với yes. Không dùng riêng `Boolean.parseBoolean` nếu cần phân biệt false hợp lệ với văn bản không hợp lệ.

## 14. Checklist và kết luận

- [ ] Biết điều kiện `if` phải có kiểu `boolean` hoặc `Boolean` được unboxing.
- [ ] Hiểu Java **không có implicit truthiness** cho số, String hay object.
- [ ] Biết phép so sánh trả boolean, ví dụ `count > 0`, `text != null`.
- [ ] Biết `if (Boolean.TRUE)` hợp lệ, nhưng `if ((Boolean) null)` có thể ném NPE.
- [ ] Phân biệt lỗi kiểu tại compile time và lỗi unboxing null tại runtime.
- [ ] Dùng `Boolean.TRUE.equals(flag)` cho chính sách “chỉ true”, hoặc `flag != null && flag`.
- [ ] Không coi null bằng false nếu nghiệp vụ cần đủ ba trạng thái.
- [ ] Biết `flag == true` có thể unbox null; `flag == null` là kiểm tra null an toàn.
- [ ] Biết `&&`/`||` ngắn mạch; `&`/`|` boolean không ngắn mạch.
- [ ] Không dùng nhầm `if (flag = true)` thành phép kiểm tra.
- [ ] Kiểm tra định dạng String trước khi chuyển thành boolean nếu cần từ chối input sai.
- [ ] Chạy `IfBooleanConditionDemo.java` bằng Java 17+ và đối chiếu exact stdout.

**Kết luận:** Java bắt buộc biểu thức điều kiện của `if` mang kiểu `boolean` hoặc `Boolean`. Với `Boolean`, compiler cho phép **unboxing**, nhưng runtime sẽ ném `NullPointerException` nếu giá trị là null. Viết điều kiện rõ nghĩa, guard null trước khi unbox và chọn chính sách xử lý ba trạng thái có chủ đích sẽ giúp nhánh `if` đúng kiểu, đúng logic và dễ bảo trì.