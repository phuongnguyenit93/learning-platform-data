# Dominance giữa các pattern trong Java 21

## 1. Dominance là gì, vì sao switch có thể không biên dịch?

**Pattern dominance** (quan hệ bao phủ/che khuất giữa các pattern) là quy tắc quan trọng của **pattern matching for switch** trong Java 21. Một nhãn `case` phía sau bị *dominated* nếu một nhãn `case` phía trước đã bao phủ toàn bộ giá trị mà nhãn phía sau có thể nhận, theo những quy tắc mà trình biên dịch được phép xác định.

Ví dụ:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
Object input = "Java";

switch (input) {
    case CharSequence sequence -> System.out.println("text-like");
    case String text -> System.out.println("string"); // Dominated!
    default -> System.out.println("other");
}
```

Vì `String` triển khai `CharSequence`, mọi `String` đều khớp `CharSequence sequence`. Nhánh `String text` đứng sau không thể được chọn: compiler báo lỗi **dominated case label**.

Sửa bằng cách đưa pattern **hẹp hơn** trước:

```java
switch (input) {
    case String text -> System.out.println("string");
    case CharSequence sequence -> System.out.println("text-like");
    default -> System.out.println("other");
}
```

**Điểm mấu chốt:** dominance được xét trên **những giá trị mà pattern có thể khớp**, không dựa vào cách đặt tên biến. Đổi `sequence` thành `s` không giải quyết được lỗi; phải thay đổi thứ tự hoặc phạm vi bao phủ của các nhánh.

Trong Java 21, type patterns, record patterns và pattern matching for `switch` đều là tính năng **chính thức**, không cần bật `--enable-preview`.

## 2. Đặt dominance vào đúng bối cảnh

Một `switch` pattern thường có nhiều loại nhãn:

```java
return switch (input) {
    case null -> "missing";
    case String s when s.isBlank() -> "blank";
    case String s -> "string";
    case Number n -> "number";
    default -> "other";
};
```

Phân biệt rõ:

- `String s`, `Number n`: **type patterns**.
- `String s when s.isBlank()`: **guarded case pattern**; guard được đánh giá **sau khi** type pattern khớp.
- `case null`: nhãn riêng cho giá trị `null`.
- `default`: nhãn fallback, không phải một type pattern.
- `s`, `n`: các **pattern variables**; tên không ảnh hưởng tới quan hệ kiểu giữa các pattern.

Dominance chủ yếu là **ràng buộc hợp lệ khi biên dịch**: nếu compiler chứng minh được một nhãn đứng sau bị một nhãn đứng trước che hoàn toàn theo quy tắc JLS, switch sẽ bị từ chối. Nhưng **không phải mọi sự chồng lấn đều là lỗi biên dịch**. Hai nhánh có thể cùng nhận một số giá trị mà không nhánh nào bao phủ *toàn bộ* nhánh còn lại; lúc ấy **thứ tự case** quyết định hành vi cho phần giao nhau.

### Bốn câu hỏi khi review

1. Pattern nào xuất hiện **trước**?
2. Những giá trị nào match pattern đứng **sau**?
3. Pattern trước có match **mọi** giá trị đó hay không, theo JLS?
4. Có guard không? Guard có khiến nhãn trước được xem là **guarded** thay vì unguarded không?

Nếu đáp án cho câu 3 là có và nhãn trước là pattern **unguarded**, nhãn sau thường bị dominated. Ngoài pattern-vs-pattern, JLS còn có quy tắc riêng cho **hằng số**, **default** và **null/default**.

## 3. Type pattern cha–con: đặt subtype trước supertype

Ví dụ phân cấp:

```text
Object
  |
  +-- CharSequence
  |      |
  |      +-- String
  |      +-- StringBuilder
  |
  +-- Number
         |
         +-- Integer
         +-- Double
```

Đối với type patterns, một type pattern có kiểu đủ rộng có thể dominate một type pattern có kiểu hẹp hơn. Ví dụ:

| Case đứng trước | Case đứng sau | Kết quả |
| --- | --- | --- |
| `case Object object` | `case String text` | **Sai**: `Object` bao phủ `String` |
| `case CharSequence chars` | `case String text` | **Sai**: `String` là `CharSequence` |
| `case Number number` | `case Integer integer` | **Sai**: `Integer` là `Number` |
| `case String text` | `case CharSequence chars` | **Hợp lệ**: subtype trước supertype |
| `case Integer integer` | `case Number number` | **Hợp lệ**: subtype trước supertype |
| `case String text` | `case Integer integer` | **Không có dominance giữa hai kiểu này** |

Mẫu nên dùng:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "String";
        case CharSequence chars -> "other CharSequence";
        case Integer integer -> "Integer";
        case Number number -> "other Number";
        default -> "other";
    };
}
```

Ở đây `String` đứng trước `CharSequence`, và `Integer` đứng trước `Number`. Nếu có `case Object object` làm nhánh cuối, nó có thể bao phủ các đối tượng khác; lúc đó không được đặt thêm một `default` phía sau vì một **unconditional type pattern** có thể làm `default` bị dominated.

### 3.1. Dựa vào kiểu, không dựa vào tên biến

```java
case Number payment -> ...
case Integer invoice -> ... // Dominated
```

Dù `payment` và `invoice` gợi ý hai khái niệm khác nhau, quan hệ bao phủ là quan hệ **`Integer` <: `Number`**. Nếu hai vai trò nghiệp vụ thật sự khác nhau, hãy biểu diễn bằng **các kiểu domain riêng**, không hy vọng tên biến cục bộ khiến pattern phân biệt được chúng.

### 3.2. Interface cũng tham gia dominance

Không chỉ class inheritance:

```java
case java.util.Collection<?> values -> "collection";
case java.util.List<?> list -> "list"; // Dominated
```

`List` kế thừa `Collection`; vì vậy đặt `List` phía trước `Collection` nếu cần xử lý riêng danh sách. Các đối số `?` là wildcard generic; chúng không giúp phân biệt hai loại danh sách theo kiểu phần tử ở runtime.

## 4. Type pattern và record pattern: kiểu tổng quát có thể che việc giải cấu trúc

Record pattern dùng để kiểm tra record và các component của nó:

```java
record Parcel(Object item) {}
```

Một type pattern khớp mọi `Parcel` có thể che record pattern của cùng record nếu đứng trước:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
return switch (value) {
    case Parcel parcel -> "any parcel";
    case Parcel(String text) -> "parcel text: " + text; // Dominated
    default -> "other";
};
```

Mọi giá trị match `Parcel(String text)` đều là một `Parcel` và đã match `Parcel parcel`. Compiler không cần biết `text` là gì để kết luận.

**Sửa:** đặt nhánh record pattern có điều kiện cấu trúc cụ thể trước, nhánh type pattern chung phía sau:

```java
return switch (value) {
    case Parcel(String text) -> "parcel text: " + text;
    case Parcel parcel -> "other parcel";
    default -> "other";
};
```

Nhánh `Parcel(String text)` chỉ khớp `Parcel` có component `item` khớp `String`. Nhánh `Parcel parcel` còn lại nhận các `Parcel` khác.

### 4.1. Record pattern không đồng nhất với type pattern

- `Parcel parcel` kiểm tra **kiểu record** và liên kết toàn bộ đối tượng.
- `Parcel(String text)` còn kiểm tra **component** và liên kết `text`.
- `Parcel(Object item)` cũng là **record pattern**: nó giải cấu trúc `item`, dù component pattern có kiểu rất rộng.

Đừng kết luận mọi record pattern `Parcel(...)` tự nhiên đều tương đương `Parcel parcel`. Mức độ bao phủ còn phụ thuộc **kiểu và từng component pattern**.

## 5. Dominance giữa hai record patterns: so từng component

Với:

```java
record Pair(Object left, Object right) {}
```

Một record pattern có các component patterns rộng hơn có thể dominate record pattern khác **cùng record class**:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
return switch (value) {
    case Pair(Object left, Object right) -> "general pair";
    case Pair(String left, String right) -> "two strings"; // Dominated
    default -> "other";
};
```

Record `Pair(Object, Object)` có thể khớp mọi `Pair` và hai component `Object` đủ rộng để bao phủ `String` ở từng vị trí. Nhánh sau bị che.

Sửa:

```java
return switch (value) {
    case Pair(String left, String right) -> "two strings";
    case Pair(Object left, Object right) -> "general pair";
    default -> "other";
};
```

### 5.1. Quy tắc chính xác hơn cho record patterns

Theo JLS 21 §14.30.3, hai record patterns có quan hệ dominance khi chúng chỉ cùng một **record class** và mỗi component pattern của record đứng trước dominate component pattern ở **vị trí tương ứng** của record đứng sau.

Ví dụ:

```java
case Pair(Object left, String right) -> ...
case Pair(String left, String right) -> ... // Dominated
```

Vì component thứ nhất `Object` bao phủ `String` và component thứ hai `String` bao phủ cùng kiểu `String`.

Ngược lại, hai pattern sau không có một chiều bao phủ toàn bộ:

```java
case Pair(String left, Object right) -> "left is text";
case Pair(Object left, String right) -> "right is text";
```

Với `Pair("A", "B")`, **cả hai** pattern có thể match, nhưng pattern thứ nhất không bao phủ mọi giá trị của pattern thứ hai (ví dụ `Pair(42, "B")`), và pattern thứ hai không bao phủ mọi giá trị của pattern thứ nhất (ví dụ `Pair("A", 42)`). Vì vậy không phải lỗi dominance; **nhánh đứng trước được chọn** khi cả hai cùng match.

Đây là lý do bạn không nên suy luận “hai case chồng lấn thì compiler chắc chắn từ chối”. Dominance yêu cầu một quan hệ bao phủ cụ thể, không chỉ có **giao nhau**.

### 5.2. Lưu ý về null trong record component

Một chi tiết của Java 21 dễ bị bỏ qua: **type pattern lồng trực tiếp vào record pattern có thể match `null`** nếu type pattern đó là *unconditional* đối với kiểu khai báo của component.

Với `record Pair(Object left, Object right)`, các component patterns `Object left` và `Object right` có thể nhận cả component `null`. Vì vậy `Pair(Object left, Object right)` có thể match một đối tượng `new Pair(null, null)`, dù bản thân **record pattern không match selector `null`**.

Trái lại, `Pair(String left, Object right)` không match một `Pair` có `left = null`, bởi component có kiểu khai báo `Object` và pattern `String left` không unconditional cho `Object`.

Đây là quy tắc JLS 21; không áp dụng máy móc trực giác “mọi `String` pattern đều từ chối `null`” từ `instanceof` ở top-level vào record component patterns.

## 6. Guarded và unguarded patterns: compiler suy luận đến đâu?

Trong nhãn:

```java
case Integer number when number > 0 -> "positive";
```

`Integer number` là pattern; `number > 0` là **guard**. JLS phân biệt:

- **Unguarded:** không có `when`, hoặc guard là biểu thức hằng có giá trị `true`.
- **Guarded:** có `when` với điều kiện không thuộc trường hợp trên.

Một pattern **unguarded** đứng trước có thể dominate pattern đứng sau. Một pattern **guarded thông thường** đứng trước **không được coi là bao phủ mọi giá trị** của pattern cùng kiểu không guard ở phía sau.

Ví dụ hợp lệ:

```java
static String sign(Integer value) {
    return switch (value) {
        case null -> "null";
        case Integer number when number > 0 -> "positive";
        case Integer number -> "zero or negative";
    };
}
```

Mặc dù hai case đều có `Integer number`, nhánh đầu chỉ áp dụng khi guard đúng; nhánh sau là **fallback cho cùng subtype**.

### 6.1. Ngược thứ tự thì lỗi

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
return switch (value) {
    case Integer number -> "integer";
    case Integer number when number > 0 -> "positive"; // Dominated
};
```

Nhánh `Integer` không guard bao phủ tất cả số nguyên `Integer`, nên nhánh có guard phía sau không bao giờ được chọn.

### 6.2. `when true` là trường hợp đặc biệt

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
return switch (value) {
    case Integer number when true -> "any integer";
    case Integer number -> "fallback"; // Dominated
};
```

Trong Java 21, `when true` là **constant-expression true** và được coi là unguarded. Nếu chỉ muốn nhánh tổng quát, nên **bỏ hẳn `when true`** cho rõ nghĩa.

Ngược lại, `when false` là **compile-time error** đối với một guard có giá trị hằng `false`; không dùng nó để tạm tắt nhánh.

### 6.3. Guard tùy ý không được compiler chứng minh quan hệ số học đầy đủ

Xét:

```java
case Integer number when number > 0 -> "positive";
case Integer number when number > 10 -> "large positive";
case Integer number -> "other";
```

Hai nhánh đầu **chồng lấn** ở các giá trị lớn hơn 10. Nhưng compiler không chứng minh `number > 0` luôn đúng khi `number > 10` để coi nhánh thứ hai là dominated theo cách nó xử lý pattern unguarded. Code có thể biên dịch, song nhánh `large positive` sẽ không được chọn cho số lớn hơn 10 vì nhánh đầu đã xử lý chúng.

**Sửa theo ý định nghiệp vụ:**

```java
case Integer number when number > 10 -> "large positive";
case Integer number when number > 0 -> "positive";
case Integer number -> "other";
```

Đừng coi việc “không bị compiler báo dominance” là bằng chứng thứ tự guard đúng. Luôn test ngưỡng và trường hợp chồng lấn.

## 7. Constant case và pattern: đặt hằng số trước type pattern chung

Trong một `switch` trên `Integer`, hằng `42` cần được xử lý **trước** type pattern không guard `Integer`:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
return switch (number) {
    case Integer n -> "some integer";
    case 42 -> "the answer"; // Dominated
};
```

Một type pattern `Integer n` unguarded bao phủ giá trị `42`. Sửa:

```java
static String classifyInteger(Integer number) {
    return switch (number) {
        case null -> "missing";
        case 42 -> "the answer";
        case Integer n when n > 0 -> "positive";
        case Integer n -> "nonpositive";
    };
}
```

Thứ tự có thể đọc như một luật ưu tiên:

1. Giá trị đặc biệt `42`.
2. Nhóm số nguyên dương khác.
3. Các số nguyên còn lại.

### 7.1. Một guarded pattern đứng trước hằng số không nhất thiết bị báo dominance

```java
return switch (number) {
    case Integer n when n > 0 -> "positive";
    case 42 -> "the answer";
    case Integer n -> "other";
};
```

Đoạn trên có thể **biên dịch**, nhưng `42` đã match nhánh `n > 0`, nên **không đến** nhãn `case 42` khi chạy. Để giá trị đặc biệt được xử lý, hãy đặt `case 42` **trước guard**.

**Heuristic khi kết hợp các loại nhãn:** hằng số đặc biệt → pattern có guard → pattern rộng không guard → fallback. Đây là quy ước đọc mã thực tế, không phải quy tắc mọi hằng số luôn phải đứng đầu bất kể kiểu hay nghiệp vụ.

## 8. Default, total patterns và trường hợp bao phủ toàn bộ selector

Với selector có kiểu tĩnh `Object`, type pattern `Object other` là pattern rộng nhất cho các đối tượng không-null:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "string";
        case Number number -> "number";
        case Object other -> "other";
    };
}
```

Không cần `default`. Thêm `default` phía sau một **unconditional pattern cho kiểu selector** có thể dẫn đến lỗi compile-time vì nhánh fallback bị dominated.

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
return switch (value) {
    case Object other -> "any non-null object";
    default -> "fallback"; // Dominated
};
```

Trong Java 21, compiler có các quy tắc riêng cho nhãn `default`, bao gồm việc không được đặt `default` trước `case pattern` hoặc `case null`; nên để `default` cuối cùng khi cần sử dụng.

### 8.1. `null` không giống default

- **Top-level type pattern** như `case Object other` không khớp selector `null`.
- `case null` được dùng để khớp `null`.
- `default` thông thường không thay thế việc xử lý `null` một cách tường minh trong pattern `switch`.

Do vậy, một switch muốn nhận cả `null` và mọi đối tượng khác có thể dùng:

```java
return switch (value) {
    case null -> "missing";
    case Object other -> "non-null";
};
```

Nếu mục đích là từ chối `null`, có thể dùng `Objects.requireNonNull(value)` trước khi switch.

### 8.2. `case null, default` là nhãn đặc biệt

Java 21 cho phép nhãn kết hợp `case null, default` trong ngữ cảnh thích hợp:

```java
return switch (value) {
    case String text -> "text";
    case null, default -> "other or missing";
};
```

Khi sử dụng, nhãn kết hợp này phải nằm **cuối** switch block. Đó không phải hai type patterns và không phải mẹo để vượt quy tắc dominance. Nếu nghiệp vụ cần phân biệt `null` với kiểu không được hỗ trợ, giữ hai nhánh riêng sẽ dễ đọc hơn.

## 9. Dominance khác exhaustiveness như thế nào?

Hai cơ chế thường xuất hiện gần nhau nhưng trả lời **hai câu hỏi khác nhau**.

| Khái niệm | Câu hỏi | Hậu quả khi sai |
| --- | --- | --- |
| **Dominance** | “Có nhánh sau nào bị nhánh trước bao phủ hoàn toàn không?” | Nhánh bị dominated → **compile-time error** |
| **Exhaustiveness** | “Các nhánh có bao phủ tất cả giá trị cần xét cho switch này không?” | Switch cần exhaustive mà thiếu trường hợp → **compile-time error** |
| **Guard order** | “Hai nhánh có thể cùng match một số giá trị; nhánh nào được chọn?” | Có thể **biên dịch nhưng sai kết quả** |
| **Flow scoping** | “Biến pattern có được dùng tại đây khi match thành công không?” | Dùng biến ngoài scope → **compile-time error** |

Ví dụ một sealed domain:

```java
sealed interface Result permits Success, Failure {}
record Success(String value) implements Result {}
record Failure(String reason) implements Result {}
```

Switch exhaustive:

```java
static String render(Result result) {
    return switch (result) {
        case Success(var value) -> "OK:" + value;
        case Failure(var reason) -> "FAIL:" + reason;
    };
}
```

Hai subtype được bao phủ. Không cần `default`. Nếu business logic thêm subtype mới rồi biên dịch lại, compiler có thể yêu cầu thêm case phù hợp.

Tuy nhiên, một switch chỉ có guarded `Success` sẽ không tự động exhaustive:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH: thiếu Success khi guard false
return switch (result) {
    case Success(var value) when value != null -> "OK";
    case Failure(var reason) -> "FAIL";
};
```

Đây là lỗi **thiếu bao phủ**, không phải dominance. Cách sửa là thêm một nhánh `Success` không guard (hoặc chính sách fallback đúng). Đừng thêm `default -> ""` chỉ để compiler im lặng nếu mong muốn xử lý từng biến thể domain rõ ràng.

## 10. Generic types, erasure và khả năng phân biệt pattern

Trong Java generics, thông tin type argument không luôn có ở runtime. Với nguồn có kiểu tĩnh `Object`, **reifiable types** như `List<?>` có thể dùng trong type pattern:

```java
return switch (value) {
    case java.util.List<?> list -> "list";
    case java.util.Collection<?> collection -> "collection";
    default -> "other";
};
```

Đây là thứ tự phù hợp: `List` là subtype của `Collection`. Đảo hai nhánh khiến `case List<?> list` bị dominated.

Không thể phân biệt mọi giá trị dựa vào generic type arguments cụ thể như `List<String>` và `List<Integer>` khi nguồn chỉ là `Object`:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH từ nguồn Object:
case java.util.List<String> strings -> "strings";
case java.util.List<Integer> ints -> "integers";
```

Đây trước hết là vấn đề **khả năng áp dụng pattern/checked cast** do type erasure, không phải phương pháp giải quyết dominance. Hãy match `List<?> list` rồi kiểm tra từng phần tử hoặc thiết kế record wrappers có kiểu runtime phân biệt được.

Theo JLS, một số phép kiểm tra generic cụ thể hợp lệ nếu **kiểu tĩnh của selector** đã mang đủ thông tin để chuyển kiểu checked. Nhưng không nên dùng type arguments như cách phân biệt hai collection tùy ý từ `Object`.

## 11. Khi compiler không báo dominance nhưng code vẫn có nhánh vô dụng

Một số cặp pattern **chồng lấn mà không bao phủ nhau**. Ví dụ:

```java
record Pair(Object left, Object right) {}
```

```java
return switch (value) {
    case Pair(String left, Object right) -> "string on left";
    case Pair(Object left, String right) -> "string on right";
    case Pair(Object left, Object right) -> "general pair";
    default -> "not a pair";
};
```

Với `Pair("A", "B")`, hai nhánh đầu đều match. Vì nhánh **left** đứng trước, nó được chọn. Đây **không** phải compile-time dominance: mỗi nhánh có những giá trị của riêng mình mà nhánh kia không bao phủ.

Trong thiết kế hệ thống, bạn phải quyết định rõ khi dữ liệu thỏa cả hai điều kiện:

- Ưu tiên xét trái?
- Ưu tiên xét phải?
- Có cần một case riêng `Pair(String left, String right)` ở đầu?
- Hay nên chuyển logic vào một phương thức phân loại có tên rõ?

Ví dụ thêm nhánh cụ thể nhất:

```java
case Pair(String left, String right) -> "both strings";
case Pair(String left, Object right) -> "left string";
case Pair(Object left, String right) -> "right string";
case Pair(Object left, Object right) -> "other pair";
```

Cách này làm rõ hành vi cho giao nhau của hai trường hợp, tránh phụ thuộc ngầm vào vị trí. Dùng unit test cho `Pair("A","B")`, `Pair("A",42)`, `Pair(42,"B")`, và `Pair(42,7)`.

## 12. Chương trình Java 21 hoàn chỉnh: type, record, guard, constant

Lưu thành tệp **`PatternDominanceDemo.java`**. Đây là chương trình **chạy được với Java 21 chính thức**, không dùng preview. Các ví dụ cố ý lỗi biên dịch ở mục khác **không thuộc tệp** này.

```java
public class PatternDominanceDemo {
    record Parcel(Object item) {}

    sealed interface Notice permits EmailNotice, SmsNotice {}
    record EmailNotice(String address) implements Notice {}
    record SmsNotice(String number) implements Notice {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "null selector";

            case String text when text.isBlank() -> "blank text";
            case String text -> "text:" + text;

            case Integer number when number > 0 ->
                "positive:" + number;
            case Integer number -> "integer:" + number;

            case Parcel(String text) when text.isEmpty() ->
                "empty payload";
            case Parcel(String text) -> "payload text:" + text;
            case Parcel(Object item) -> "payload other:" + item;

            case Object other ->
                "other:" + other.getClass().getSimpleName();
        };
    }

    static String numberClass(Integer number) {
        return switch (number) {
            case null -> "no number";
            case 42 -> "answer";
            case Integer value when value > 0 -> "positive";
            case Integer value -> "zero or negative";
        };
    }

    static String notice(Notice value) {
        return switch (value) {
            case null -> "no notice";
            case EmailNotice(String address)
                    when address != null && address.isBlank() ->
                "blank email";
            case EmailNotice(String address) ->
                "email:" + address;
            case SmsNotice(String number) -> "sms:" + number;
        };
    }

    static void check(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected [" + expected + "] but got [" + actual + "]");
        }
    }

    public static void main(String[] args) {
        Object[] examples = {
            " ", "java", 5, -1,
            new Parcel(""), new Parcel("hi"),
            new Parcel(12), new Parcel(null),
            3.5, null
        };

        for (Object example : examples) {
            System.out.println(describe(example));
        }

        System.out.println(numberClass(42));
        System.out.println(numberClass(7));
        System.out.println(numberClass(0));

        System.out.println(notice(new EmailNotice("  ")));
        System.out.println(notice(new EmailNotice("a@b.com")));
        System.out.println(notice(new SmsNotice("090")));
        System.out.println(notice(null));

        check("empty payload", describe(new Parcel("")));
        check("payload other:null", describe(new Parcel(null)));
        check("answer", numberClass(42));
        check("positive", numberClass(7));
        check("zero or negative", numberClass(0));
        check("blank email", notice(new EmailNotice("  ")));
        check("email:null", notice(new EmailNotice(null)));
        System.out.println("checks passed");
    }
}
```

Biên dịch và chạy bằng **JDK 21**:

```bash
javac --release 21 PatternDominanceDemo.java
java PatternDominanceDemo
```

Stdout chính xác theo các giá trị trong chương trình:

```text
blank text
text:java
positive:5
integer:-1
empty payload
payload text:hi
payload other:12
payload other:null
other:Double
null selector
answer
positive
zero or negative
blank email
email:a@b.com
sms:090
no notice
checks passed
```

**Điều gì được minh họa?**

1. `String` có guard `isBlank()` đứng trước `String` tổng quát.
2. `Integer` có guard `number > 0` đứng trước `Integer` tổng quát.
3. `Parcel(String text)` đứng trước `Parcel(Object item)`: component `String` cụ thể hơn `Object`.
4. `Parcel(null)` được xử lý bởi `Parcel(Object item)` vì pattern component `Object item` là null-matching khi component có kiểu khai báo `Object`.
5. `Object other` được đặt **cuối** để nhận các đối tượng không-null còn lại; `case null` xử lý selector null riêng.
6. `case 42` đứng trước `case Integer value`, tránh bị nhánh kiểu bao phủ.
7. `Notice` là sealed hierarchy gồm hai record; switch không cần `default` và mỗi record có nhánh cơ sở.
8. `EmailNotice(String address)` với component khai báo `String` có thể nhận `null`; guard kiểm tra `address != null` trước khi gọi `isBlank()` nên không ném lỗi.
9. Các kiểm tra trong `check` xác minh ranh giới quan trọng mà không cần `-ea` hoặc thư viện bên ngoài.

## 13. Ba nhóm lỗi compiler dễ nhầm với dominance

### 13.1. Pattern không áp dụng được cho kiểu selector

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
Object input = java.util.List.of("A");
if (input instanceof java.util.List<String> strings) {
    // ...
}
```

Đây là lỗi **khả năng kiểm tra generic type** từ nguồn `Object`, không phải lỗi một `case` che nhánh khác.

### 13.2. Switch không exhaustive

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH: thiếu khi guard false
return switch (value) {
    case String text when text.length() > 2 -> "long text";
};
```

Khi selector là một kiểu mở như `Object`, switch expression trên còn thiếu rất nhiều giá trị; ngay cả selector `String` cũng có thể không đạt guard. Đây là lỗi **exhaustiveness**, không phải dominance. Có thể sửa bằng nhánh `String text` không guard và `default` khi kiểu selector yêu cầu fallback.

### 13.3. Biến pattern ngoài scope

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
switch (value) {
    case String text -> System.out.println(text);
    default -> {}
}
System.out.println(text); // text không ở scope này
```

Đây là lỗi **flow scoping**. Pattern variable chỉ thuộc nhánh phù hợp; nó không tồn tại sau switch. Một switch expression có thể trả về biến kết quả dùng chung:

```java
String summary = switch (value) {
    case String text -> "string:" + text;
    default -> "other";
};
System.out.println(summary);
```

Đừng sửa lỗi scope bằng cách đổi thứ tự case; các vấn đề khác nhau cần cách sửa khác nhau.

## 14. Quy trình kiểm tra dominance trong code review

Khi thấy `switch` có nhiều pattern, hãy thực hiện:

1. **Ghi rõ kiểu tĩnh selector.** `Object`, `Number`, `Integer` hay sealed domain? Kiểu này ảnh hưởng pattern applicability và exhaustiveness.
2. **Tìm case tổng quát.** `Object`, interface cha, `Number`, `Collection<?>`, type pattern của record.
3. **Đặt case cụ thể trước.** Ví dụ `String` trước `CharSequence`, `Integer` trước `Number`, record pattern cụ thể trước type pattern của record.
4. **Kiểm tra record component theo từng vị trí.** Nếu mọi component pattern của nhánh trước đều bao phủ component tương ứng của nhánh sau, nhánh sau có thể bị dominated.
5. **Tách guard và pattern.** Với nhánh guarded, đánh giá mức độ chồng lấn và thứ tự ưu tiên; đừng mong compiler giải quyết các biểu thức boolean phức tạp.
6. **Đặt hằng số đặc biệt trước pattern kiểu không guard.** Ví dụ `case 42` trước `case Integer n`.
7. **Xác định chính sách null và fallback.** `case null`, `default` hoặc type pattern unconditional cho selector không được dùng tùy tiện, chồng chéo.
8. **Phân biệt lỗi dominance với lỗi khác.** Đọc chẩn đoán `dominated`, `not exhaustive`, `not applicable` hoặc lỗi tên biến cho đúng.
9. **Viết test cho phần giao nhau.** Hai pattern chồng lấn mà không dominate nhau vẫn có thể phụ thuộc vào thứ tự case ở runtime.
10. **Tái biên dịch với đúng Java 21.** Sử dụng `javac --release 21` để tránh lấy cú pháp preview hoặc thay đổi của Java phiên bản mới làm chuẩn của bài.

### Gợi ý thứ tự dễ đọc

Với cùng selector hỗ trợ nhiều dạng, một thứ tự thuận tiện thường là:

1. `case null` (nếu `null` cần nhánh riêng).
2. Các **hằng số đặc biệt** tương thích kiểu selector.
3. Các **pattern hẹp hơn** hoặc cấu trúc record cụ thể.
4. Các **guarded case** cần ưu tiên theo luật nghiệp vụ.
5. Các **unguarded type/record patterns** rộng hơn.
6. `default` hoặc một unconditional pattern tổng quát **nếu cần**, không giữ cả hai làm fallback trùng lặp.

Đây là **nguyên tắc tổ chức**, không phải một luật ngữ pháp rằng mọi nhóm phải xuất hiện trong mọi switch. Với cặp điều kiện có quan hệ đặc biệt, phải đặt case theo **mức độ bao phủ thực tế** và thứ tự nghiệp vụ, thay vì máy móc áp dụng thứ tự nhóm.

## 15. Bài tập tự đánh giá và đáp án

### Bài 1 — Thứ tự Number/Integer

```java
// Đây là mảnh switch:
case Number n -> "number";
case Integer i -> "integer";
```

**Hỏi:** có biên dịch không?

**Đáp án:** Không khi cùng một switch phù hợp về kiểu; `Number` bao phủ `Integer`. Đưa `Integer` trước `Number`.

### Bài 2 — Hai guarded patterns

```java
case Integer n when n >= 0 -> "nonnegative";
case Integer n when n >= 10 -> "at least ten";
case Integer n -> "negative";
```

**Hỏi:** lỗi dominance hay lỗi logic?

**Đáp án:** Hai guard không được compiler chứng minh quan hệ số học tùy ý để từ chối như một unguarded dominance. Đoạn có thể biên dịch nhưng nhánh `at least ten` không được chọn với các giá trị của nó vì `n >= 0` đã xử lý trước. Đảo hai guarded case; giữ case tổng quát cuối.

### Bài 3 — Record pattern vs type pattern

```java
record Parcel(Object item) {}

case Parcel parcel -> "parcel";
case Parcel(String text) -> "text parcel";
```

**Hỏi:** vấn đề gì?

**Đáp án:** Type pattern `Parcel parcel` bao phủ mọi `Parcel` có component chuỗi. Record pattern sau bị dominated. Đặt `Parcel(String text)` trước.

### Bài 4 — Hai record patterns chỉ chồng lấn

```java
record Pair(Object a, Object b) {}

case Pair(String a, Object b) -> "left";
case Pair(Object a, String b) -> "right";
```

**Hỏi:** có dominance hoàn toàn không, `Pair("a", "b")` đi đâu?

**Đáp án:** Không có chiều dominance hoàn toàn, vì mỗi pattern có các giá trị mà pattern kia không match. `Pair("a", "b")` match cả hai nên nhánh **left** đứng trước được chọn. Nếu cần xử lý riêng cả hai chuỗi, thêm `Pair(String a, String b)` lên đầu.

### Bài 5 — Hằng số đứng sau type pattern

```java
case Integer n -> "integer";
case 42 -> "answer";
```

**Đáp án:** `case 42` bị dominated. Đưa hằng 42 lên trước, sau đó mới pattern `Integer`.

### Bài 6 — `when true` và `when false`

**Hỏi:** `when true` có giúp tránh dominance không? `when false` có phải cách tạm vô hiệu hóa một nhánh?

**Đáp án:** Không. `when true` là **unguarded** theo đặc tả và có thể dominate các case sau. Guard là constant expression `false` bị từ chối khi biên dịch. Hãy xóa nhánh không cần dùng hoặc thiết kế điều kiện hợp lệ.

### Bài 7 — Default có bắt null không?

```java
return switch (value) {
    case String s -> "text";
    default -> "other";
};
```

**Đáp án:** Không được suy ra `default` là chính sách nhận `null`. Với pattern switch Java 21, `null` không khớp type pattern thông thường và có thể gây `NullPointerException` khi không có nhãn `case null`. Nếu `null` là đầu vào dự kiến, thêm `case null` hoặc dùng `case null, default` theo chính sách.

### Bài 8 — Type pattern Object và default

```java
case Object obj -> "object";
default -> "fallback";
```

**Đáp án:** Với selector `Object` trong Java 21, `Object obj` là unconditional pattern cho kiểu selector; `default` phía sau bị dominated. Chọn một cơ chế bao phủ còn lại cho phù hợp, xử lý `null` riêng nếu cần.

## 16. Checklist khi sửa lỗi “dominated case label”

- [ ] Đã xác định **kiểu tĩnh của selector** và những pattern applicable?
- [ ] Có supertype pattern nào đứng trước subtype pattern không?
- [ ] Có type pattern của record đứng trước record pattern chi tiết không?
- [ ] Với hai record patterns, đã kiểm tra dominance **theo từng component**?
- [ ] Hai pattern chồng lấn nhưng không dominate nhau đã có **ưu tiên nghiệp vụ** rõ?
- [ ] Nhánh có guard được đặt trước nhánh unguarded tổng quát của cùng kiểu?
- [ ] Không coi mọi guarded pattern là thông tin compiler có thể suy luận để loại nhánh khác?
- [ ] Không dùng `when true` để né dominance hoặc `when false` để tắt nhánh?
- [ ] Hằng số đặc biệt đứng trước pattern kiểu tổng quát nếu cần xử lý riêng?
- [ ] `case null`, `default` hoặc `case null, default` có vai trò rõ ràng?
- [ ] Không đặt một unconditional pattern cho selector cùng `default` gây chồng lặp?
- [ ] Không nhầm dominance với exhaustive switch, generic applicability hoặc flow scope?
- [ ] Đã test nhánh chồng lấn và mốc biên sau khi đổi thứ tự?

## 17. Tài liệu chính thức

- [Java Language Specification 21 §14.11.1 — Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): quy tắc nhãn `case` dominated, guard, hằng số, `default` và `null`.
- [Java Language Specification 21 §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3): định nghĩa *unconditional* và dominance giữa type/record patterns.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): ví dụ thứ tự type, guard và constant case.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): thiết kế pattern matching for switch chính thức trong Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): cách các record pattern được giải cấu trúc và kiểm tra.
