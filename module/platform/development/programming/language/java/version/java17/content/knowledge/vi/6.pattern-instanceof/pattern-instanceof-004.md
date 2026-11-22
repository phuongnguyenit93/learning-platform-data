# Kết hợp `instanceof` với `&&` và quy tắc đánh giá ngắn mạch trong Java 17

Khi kiểm tra một đối tượng có thuộc một kiểu cụ thể hay không, Java 17 cho phép **khai báo biến ngay trong biểu thức `instanceof`**. Kết hợp cách viết này với toán tử `&&`, ta có thể kiểm tra kiểu, đọc thuộc tính và kiểm tra điều kiện bổ sung **trong cùng một biểu thức an toàn**.

Ví dụ tiêu biểu:

```java
Object value = "Java 17";

if (value instanceof String text && text.length() >= 5) {
    System.out.println(text.toUpperCase());
}
```

Điểm quan trọng nằm ở thứ tự đánh giá:

1. Java kiểm tra `value instanceof String text`.
2. Chỉ khi kiểm tra thành công, biến pattern `text` mới có giá trị kiểu `String` và vế phải `text.length() >= 5` mới được đánh giá.
3. Khối `if` chỉ chạy khi **cả hai điều kiện** là `true`.

Cơ chế này được gọi là **đánh giá ngắn mạch** (*short-circuit evaluation*), và nó liên kết trực tiếp với **phạm vi của biến pattern** (*flow scoping*).

> Trong Java 17, *pattern matching for `instanceof`* đã là tính năng chính thức (được hoàn thiện ở Java 16, JEP 394). Các ví dụ trong bài không cần bật preview feature.

## 1. Ôn lại: `instanceof` truyền thống và type pattern

Trước khi dùng type pattern, một cách viết quen thuộc là:

```java
static void printLength(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        System.out.println(text.length());
    }
}
```

Chúng ta thực hiện hai hành động: kiểm tra kiểu bằng `instanceof` và ép kiểu bằng `(String) value`.

Với type pattern trong Java 17:

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
```

Cú pháp:

```text
biểu_thức instanceof Kiểu tên_biến_pattern
                           └──────────────┘
                         chỉ được dùng khi đã khớp
```

Ở ví dụ `value instanceof String text`:

- `value` là biểu thức cần kiểm tra, thường có kiểu tĩnh là `Object` hoặc một kiểu cha/interface khác.
- `String` là **kiểu cần đối chiếu**.
- `text` là **biến pattern**, có kiểu tĩnh `String` nếu việc kiểm tra khớp.
- Không cần lặp lại ép kiểu `(String) value` trong nhánh đã kiểm tra thành công.

Nếu `value == null`, biểu thức `value instanceof String text` nhận `false`; Java không tạo một `String` hợp lệ cho `text` trong đường đi đó.

### Điều mà type pattern không làm

Type pattern **không thay đổi đối tượng gốc** và không biến mọi nhánh thành `String`. Biến `text` chỉ được dùng tại vị trí mà trình biên dịch chứng minh việc khớp pattern đã xảy ra.

```java
Object value = 123;

if (value instanceof String text) {
    System.out.println(text.length()); // Không chạy
}
```

Đối tượng `Integer` không khớp `String`. Chương trình không ném `ClassCastException` chỉ vì kiểm tra `instanceof` thất bại.

## 2. `&&` đánh giá ngắn mạch như thế nào?

Toán tử **conditional-and** `&&` nhận các toán hạng kiểu `boolean` (hoặc `Boolean` có thể được unbox) và đánh giá **từ trái sang phải**.

Với biểu thức:

```java
A && B
```

Quy tắc chạy là:

- Đánh giá `A` trước.
- Nếu `A` là `false`, **bỏ qua hoàn toàn `B`**, trả về `false`.
- Nếu `A` là `true`, tiếp tục đánh giá `B` và dùng kết quả của `B` làm kết quả chung.

Bảng chân trị:

| `A` | Có đánh giá `B`? | Nếu `B` là `false` | Nếu `B` là `true` |
|---|---|---|---|
| `false` | Không | Kết quả `false` | Kết quả `false` |
| `true` | Có | Kết quả `false` | Kết quả `true` |

Sơ đồ luồng:

```text
           Đánh giá A
               |
         +-----+-----+
         |           |
      A=false      A=true
         |           |
   Bỏ qua B     Đánh giá B
         |           |
     false        Kết quả B
```

Điều này rất hữu ích khi **vế phải chỉ an toàn hoặc chỉ có ý nghĩa sau khi điều kiện vế trái được đáp ứng**.

Ví dụ thường gặp, chưa dùng pattern:

```java
String name = null;

if (name != null && !name.isBlank()) {
    System.out.println(name);
}
```

Vì `name != null` là `false`, Java **không gọi** `name.isBlank()`, nên không gặp `NullPointerException` tại lời gọi đó.

Với type pattern, điều kiện `instanceof` còn làm được nhiều hơn: nó vừa kiểm tra kiểu, vừa cung cấp một biến có kiểu đúng cho phần còn lại.

## 3. Vì sao `instanceof ... && ...` sử dụng được biến pattern?

Đây là ví dụ then chốt:

```java
Object input = "Hello";

if (input instanceof String text && text.length() > 3) {
    System.out.println("Chuỗi đủ dài: " + text);
}
```

Có thể đọc bằng lời:

> Nếu `input` là một `String`, gọi nó là `text`; **và nếu** độ dài của `text` lớn hơn 3, thực hiện phần thân `if`.

Trình biên dịch cho phép sử dụng `text` ở vế phải vì `&&` bảo đảm vế đó chỉ chạy khi vế trái là `true`. Khi `input instanceof String text` là `true`, biến `text` đã **khớp pattern** và đã có giá trị.

Quy tắc này thuộc **flow scoping**:

- Biến pattern không đơn thuần có phạm vi cố định theo dấu ngoặc nhọn như một biến local thông thường.
- Phạm vi của nó phụ thuộc vào **những đường điều khiển mà tại đó pattern chắc chắn khớp**.
- Ở vế phải của `&&`, nếu vế trái là biểu thức đưa biến pattern vào phạm vi **khi true**, biến được phép sử dụng.

Bốn trường hợp của ví dụ:

| Giá trị `input` | `input instanceof String text` | Có chạy `text.length() > 3`? | Có vào `if`? |
|---|---|---|---|
| `null` | `false` | Không | Không |
| `100` (Integer) | `false` | Không | Không |
| `"Hi"` | `true` | Có; trả `false` | Không |
| `"Hello"` | `true` | Có; trả `true` | Có |

Tại dòng gọi `text.length()`, Java đã biết `text` là `String`. Vì vậy không cần ép kiểu và không có nguy cơ gọi `length()` trên một giá trị `null` do việc khớp type pattern này.

## 4. Đọc đúng thứ tự khi có nhiều `&&`

Toán tử `&&` có thể nối nhiều điều kiện:

```java
Object value = "Java 17";

if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 5
        && text.startsWith("Java")) {
    System.out.println("Hợp lệ: " + text);
}
```

Java đánh giá lần lượt:

1. `value instanceof String text`. Nếu không khớp, dừng.
2. `!text.isBlank()`. Nếu chuỗi chỉ chứa khoảng trắng, dừng.
3. `text.length() >= 5`. Nếu quá ngắn, dừng.
4. `text.startsWith("Java")`. Nếu không có tiền tố đúng, kết quả chung là `false`.
5. Khi tất cả đều `true`, thực hiện body của `if`.

Nhìn dưới dạng chuỗi bảo vệ:

```text
Có phải String?
    |
    +-- không -----------------> false
    |
    +-- có --> Không trống?
                   |
                   +-- không --> false
                   |
                   +-- có --> Đủ dài?
                                 |
                                 +-- không --> false
                                 |
                                 +-- có --> Đúng tiền tố?
                                             |
                                             +-- không --> false
                                             |
                                             +-- có --> vào if
```

Toán tử `&&` kết hợp từ trái sang phải; ngay cả khi dùng nhiều `&&`, các điều kiện vẫn được đánh giá theo đúng thứ tự viết ra.

**Thói quen tốt:** kiểm tra **kiểu hoặc điều kiện tiên quyết** trước, rồi đặt những thao tác cần điều kiện đó ở bên phải. Điều kiện rẻ, đơn giản và đủ để loại bỏ trường hợp sai thường được đặt sớm để tránh thực hiện xử lý tốn kém ở phía sau.

## 5. Tại sao đảo thứ tự sẽ không biên dịch?

Đây là lỗi:

```java
Object input = "Hello";

// LỖI: text chưa được khai báo tại vị trí đầu biểu thức.
// if (text.length() > 3 && input instanceof String text) {
//     System.out.println(text);
// }
```

`text` chỉ được giới thiệu ở **vế sau**; không thể sử dụng nó ở **vế trước** của `&&`. Java không “nhìn trước” sang vế phải để cấp biến cho vế trái.

Cách đúng:

```java
if (input instanceof String text && text.length() > 3) {
    System.out.println(text);
}
```

Một lỗi tương tự là gọi phương thức cụ thể của `String` trên biến kiểu `Object` trước khi kiểm tra kiểu:

```java
Object input = "Hello";

// LỖI biên dịch: Object không có length().
// if (input.length() > 3 && input instanceof String text) {}
```

Dù đối tượng thực tế là chuỗi, **kiểu tĩnh của `input` vẫn là `Object`**. Type pattern giúp cấp biến mới `text` với kiểu tĩnh `String` tại những vị trí hợp lệ.

## 6. Biến pattern được dùng ở đâu sau điều kiện?

Xét:

```java
Object value = "Java 17";

if (value instanceof String text && text.length() >= 4) {
    System.out.println(text.toUpperCase()); // Hợp lệ
} else {
    System.out.println("Không phải chuỗi đủ dài");
    // System.out.println(text); // LỖI
}

// System.out.println(text);     // LỖI trong trường hợp này
```

Tại body của nhánh `if`, cả biểu thức điều kiện đã là `true`, nên `text` chắc chắn được gán.

Tại nhánh `else`, điều kiện có thể sai vì:

- `value` không phải `String`; trong trường hợp này **không có** biến pattern đã khớp.
- `value` là `String` nhưng `text.length() >= 4` sai.

Vì vậy Java không cho phép tùy tiện dùng `text` trong `else`. Sau toàn bộ `if`, cũng không thể bảo đảm rằng quá trình khớp đã thành công.

### Không phải “biến chỉ tồn tại trong dấu ngoặc của `if`”

Phạm vi của pattern variable được quyết định bằng **luồng điều khiển**. Có trường hợp được phép dùng sau `if`, nếu nhánh không khớp **chắc chắn kết thúc luồng thực thi**:

```java
static int lengthOfString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected String");
    }

    // Đến đây chỉ có thể vì phép instanceof đã khớp.
    return text.length();
}
```

Với ví dụ này, `text` hợp lệ ở dòng `return`. Java đã chứng minh rằng nếu không khớp thì phương thức ném ngoại lệ và không tiếp tục tới dòng đó.

Phương pháp này gọi là **guard clause** và hữu ích khi muốn xử lý sớm dữ liệu không hợp lệ. Quy tắc không dựa trên việc “biến sống đến cuối hàm”, mà dựa trên việc **mọi đường có thể đến câu lệnh đó đều đã khớp pattern**.

## 7. Dùng `&&` với điều kiện ném ngoại lệ hoặc xử lý tốn kém

Đánh giá ngắn mạch có ích vì vế phải có thể gọi phương thức và gây tác dụng phụ.

```java
static boolean isAllowed(String text) {
    System.out.println("Đang kiểm tra nội dung...");
    return text.startsWith("APP-");
}

static void process(Object value) {
    if (value instanceof String text && isAllowed(text)) {
        System.out.println("Được chấp nhận");
    }
}
```

Ví dụ gọi:

```java
process(123);
process("APP-2026");
```

Chỉ lần gọi với chuỗi mới in:

```text
Đang kiểm tra nội dung...
Được chấp nhận
```

Lần gọi `process(123)` không chạy `isAllowed`. Điều này có nghĩa:

- Bớt việc không cần thiết.
- Không truy cập biến pattern khi kiểm tra kiểu thất bại.
- Tránh những ngoại lệ có thể phát sinh do gọi phương thức trên loại giá trị không phù hợp.

Tuy vậy, **`&&` không “nuốt” ngoại lệ**: nếu vế trái hoặc một vế đang được đánh giá ném exception, phép đánh giá kết thúc bất thường và ngoại lệ vẫn được truyền ra ngoài. Nó chỉ **bỏ qua các vế phía sau** khi gặp giá trị `false`.

Ngoài ra, nếu vế trái có kiểu `Boolean` và giá trị `null`, thao tác unboxing để đánh giá điều kiện vẫn có thể ném `NullPointerException`. Trong ví dụ `instanceof` ở đây, vế trái tạo ra giá trị nguyên thủy `boolean` nên không có vấn đề unboxing nullable ở chính phép kiểm tra kiểu.

## 8. Phân biệt `&&` với `&` trong biểu thức boolean

Khi hai toán hạng là boolean, `&&` và `&` có thể cho cùng **giá trị cuối** nhưng khác **cách đánh giá**:

| Toán tử | Có thể dùng cho boolean? | Khi vế trái `false` | Phù hợp để bảo vệ vế phải phụ thuộc pattern? |
|---|---|---|---|
| `&&` | Có | Bỏ qua vế phải | **Có** |
| `&` | Có | Vẫn đánh giá vế phải | **Không** |

Ví dụ không liên quan đến pattern để quan sát khác biệt:

```java
static boolean trace() {
    System.out.println("Vế phải được chạy");
    return true;
}

static void demo() {
    boolean a = false && trace();
    boolean b = false & trace();
}
```

Khi chạy `demo()`, chỉ biểu thức với `&` mới gọi `trace()` và in thông báo.

### Đặc biệt với biến pattern

Không thể thay `&&` thành `&` một cách máy móc:

```java
Object value = "Hello";

// HỢP LỆ
if (value instanceof String text && text.length() > 3) {
    System.out.println(text);
}

// LỖI: text không được đảm bảo nằm trong phạm vi ở vế phải của &.
// if (value instanceof String text & text.length() > 3) {}
```

**Tại sao?** Khi `&` nhận toán hạng boolean, vế phải vẫn được đánh giá ngay cả khi vế trái là `false`. Biến pattern lúc đó chưa chắc đã khớp, nên Java không cấp quyền sử dụng nó ở vế phải theo quy tắc của `&&`.

Để thấy hậu quả của việc thiếu short-circuit ở mã ép kiểu truyền thống:

```java
Object value = 42;

// true/false ở vế trái không chặn phép cast phía sau.
// boolean wrong = value instanceof String & ((String) value).length() > 0;
// Khi chạy: ClassCastException

boolean safe = value instanceof String
        && ((String) value).length() > 0; // false, không cast
```

Với Java 17, cách ngắn gọn và rõ nghĩa hơn là:

```java
boolean safe = value instanceof String text && text.length() > 0;
```

**Lưu ý:** `&` còn là toán tử xử lý bit với kiểu số nguyên; ở đây chúng ta chỉ so sánh `&` và `&&` khi chúng hoạt động trên toán hạng boolean.

## 9. Vì sao `||` không thay `&&` được?

`||` là **conditional-or**: vế phải chỉ được đánh giá nếu vế trái là `false`.

Khi viết:

```java
Object value = "Hello";

// LỖI biên dịch:
// if (value instanceof String text || text.length() > 3) {
//     System.out.println(text);
// }
```

vế phải `text.length() > 3` chỉ có thể chạy khi `value instanceof String text` **thất bại**. Chính lúc đó `text` không được khớp, nên không thể dùng.

So sánh:

| Biểu thức vế trái | Toán tử | Khi vế phải được chạy | Có chắc `text` đã khớp? |
|---|---|---|---|
| `value instanceof String text` | `&&` | Khi `instanceof` true | **Có** |
| `value instanceof String text` | `||` | Khi `instanceof` false | **Không** |
| `!(value instanceof String text)` | `||` | Khi phủ định false, tức `instanceof` true | **Có** |

Dòng cuối là một quy tắc thú vị trong Java 17: với **phủ định `!`**, hướng logic đảo lại.

### Trường hợp hợp lệ với `!` và `||`

Ví dụ một điều kiện dùng để **loại bỏ** đầu vào không phải chuỗi hoặc chuỗi rỗng:

```java
static String requireNonBlankString(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Expected nonblank String");
    }

    return text;
}
```

Giải thích từng bước:

1. Nếu `value` không phải chuỗi, `!(value instanceof String text)` là `true`; `||` dừng, **không gọi** `text.isBlank()`.
2. Nếu `value` là chuỗi, biểu thức phủ định là `false`; biến `text` đã khớp, nên vế phải `text.isBlank()` được phép dùng.
3. Nếu chuỗi rỗng hoặc chỉ có khoảng trắng, ném ngoại lệ.
4. Nếu phép kiểm tra hợp lệ, toàn bộ `if` là `false` và execution tiếp tục với `text` đã khớp.

Điều kiện này mang cùng ý nghĩa kiểm tra với việc chấp nhận theo dạng:

```java
if (value instanceof String text && !text.isBlank()) {
    // Đầu vào hợp lệ
}
```

Tuy nhiên, vị trí dùng `text` phải được xét theo **đường điều khiển** cụ thể; hai biểu thức không có cùng phạm vi biến ở mọi vị trí.

### Trường hợp phủ định sai với `&&`

```java
// LỖI: vế phải chạy khi instanceof KHÔNG khớp.
// if (!(value instanceof String text) && text.isBlank()) {}
```

Khi bỏ dấu `!`, phải xét lại ý nghĩa của `&&`/`||`. Không chỉ thay một từ khóa là đủ.

## 10. Dấu ngoặc và thứ tự ưu tiên toán tử

Java có quy tắc ưu tiên toán tử. Trong bài này, thứ tự cần nhớ là:

1. Dấu ngoặc `(...)` xác định nhóm cần đánh giá.
2. Phép so sánh kiểu `instanceof` có độ ưu tiên cao hơn `&&`.
3. `&&` có độ ưu tiên cao hơn `||`.

Ví dụ:

```java
if (value instanceof String text && text.length() > 3) {
    // ...
}
```

được hiểu như:

```java
if ((value instanceof String text) && (text.length() > 3)) {
    // ...
}
```

Có thể dùng ngoặc để thể hiện rõ mục đích khi cần.

Nếu trộn thêm `||` hoặc phủ định, nên viết dấu ngoặc chủ động để người đọc thấy **nhánh nào là điều kiện bảo vệ**:

```java
static boolean hasValidName(Object value) {
    return value instanceof String name
            && !name.isBlank()
            && name.length() <= 30;
}
```

Còn khi có điều kiện thay thế độc lập, có thể thiết kế rõ ràng thành các câu lệnh riêng:

```java
static boolean accepted(Object value, boolean allowMissing) {
    if (allowMissing && value == null) {
        return true;
    }

    return value instanceof String name && !name.isBlank();
}
```

Cách này tránh tạo một biểu thức phức tạp khiến người đọc phải suy ngược phạm vi của pattern variable qua nhiều `&&`, `||` và `!`.

## 11. Kết hợp nhiều pattern và nhiều điều kiện

Một biểu thức `&&` có thể chứa **nhiều phép kiểm tra kiểu khác nhau**, mỗi phép giới thiệu biến pattern riêng.

```java
static boolean sameText(Object left, Object right) {
    return left instanceof String first
            && right instanceof String second
            && !first.isBlank()
            && first.equalsIgnoreCase(second);
}
```

Tại `first.equalsIgnoreCase(second)`:

- `left instanceof String first` đã trả `true`.
- `right instanceof String second` đã trả `true`.
- `!first.isBlank()` đã trả `true`.

Do đó cả `first` và `second` đều nằm trong phạm vi và có kiểu tĩnh `String`. Không cần ép kiểu `left` hay `right`.

### Không khai báo hai biến pattern trùng tên trong cùng biểu thức

```java
// LỖI: hai pattern variable cùng tên s xung đột.
// if (left instanceof String s && right instanceof String s) {}
```

Chọn tên khác nhau:

```java
if (left instanceof String first && right instanceof String second) {
    System.out.println(first + " / " + second);
}
```

Java theo dõi từng biến pattern được tạo ở nhánh nào. Việc đặt cùng tên có thể gây xung đột ngay ở thời điểm biên dịch, dù ta dự kiến runtime sẽ đi theo một nhánh cụ thể.

### Tránh trùng tên với biến local hiện có

```java
String text = "existing";
Object value = "new";

// LỖI: pattern variable text trùng với local text đang trong scope.
// if (value instanceof String text && text.length() > 2) {}
```

Đặt tên mới cho pattern:

```java
if (value instanceof String matched && matched.length() > 2) {
    System.out.println(matched);
}
```

## 12. Ví dụ thực tế: kiểm tra đầu vào có cấu trúc

Giả sử một API nhận `Object` từ nhiều nguồn và chỉ chấp nhận mã yêu cầu ở dạng chuỗi bắt đầu bằng `"REQ-"`, dài ít nhất tám ký tự.

```java
static boolean isRequestCode(Object input) {
    return input instanceof String code
            && code.length() >= 8
            && code.startsWith("REQ-");
}
```

Các trường hợp:

| `input` | Kết quả | Lý do |
|---|---|---|
| `null` | `false` | Không khớp `String` |
| `12345` | `false` | Là số nguyên |
| `"REQ-"` | `false` | Ngắn hơn 8 ký tự |
| `"DOC-2026"` | `false` | Sai tiền tố |
| `"REQ-2026"` | `true` | Đúng kiểu, độ dài, tiền tố |

Đây là nơi nên dùng `&&`: **kiểm tra loại dữ liệu trước, kiểm tra nội dung sau**. Không cần lồng nhiều `if` và không lặp phép ép kiểu.

### Ví dụ với interface

Type pattern không giới hạn ở `String`. Có thể kiểm tra một interface như `CharSequence`:

```java
static boolean startsWithJava(Object input) {
    return input instanceof CharSequence text
            && text.length() >= 4
            && text.charAt(0) == 'J'
            && text.charAt(1) == 'a'
            && text.charAt(2) == 'v'
            && text.charAt(3) == 'a';
}
```

Với `String` hoặc `StringBuilder` chứa nội dung thích hợp, phép kiểm tra có thể thành công vì cả hai triển khai `CharSequence`. Khi dùng `text`, trình biên dịch chỉ bảo đảm các phương thức của **`CharSequence`**, chẳng hạn `length()` hoặc `charAt()`; muốn gọi phương thức riêng của `String` như `isBlank()`, cần type pattern `String` tương ứng.

### Ví dụ với một kiểu số

```java
static boolean positiveNumber(Object input) {
    return input instanceof Number number
            && number.doubleValue() > 0.0;
}
```

`Number` là class cha của các wrapper số như `Integer` và `Double`. Nếu đầu vào không phải `Number`, Java không gọi `doubleValue()`.

Cần nhớ rằng thao tác chuyển sang `double` có thể làm mất độ chính xác với một số loại số; ví dụ trên chỉ nhằm minh họa pattern và `&&`. Khi xử lý tiền tệ hoặc số nguyên lớn, chọn kiểu so sánh phù hợp với yêu cầu nghiệp vụ.

## 13. Ví dụ hoàn chỉnh chạy trên JDK 17

Tạo file `PatternAndDemo.java`:

```java
public class PatternAndDemo {
    static boolean startsWithJava(Object value) {
        return value instanceof String text
                && !text.isBlank()
                && text.length() >= 5
                && text.startsWith("Java");
    }

    static String describe(Object value) {
        if (value instanceof String text && text.length() > 0) {
            return "String(" + text.length() + "): " + text;
        }

        return "Không phải String không rỗng";
    }

    public static void main(String[] args) {
        Object[] samples = {
                null,
                123,
                "",
                "Hi",
                "Java",
                "Java 17"
        };

        for (Object sample : samples) {
            System.out.println(
                    String.valueOf(sample)
                            + " -> "
                            + startsWithJava(sample)
                            + " | "
                            + describe(sample)
            );
        }
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 PatternAndDemo.java
java PatternAndDemo
```

Kết quả dự kiến:

```text
null -> false | Không phải String không rỗng
123 -> false | Không phải String không rỗng
 -> false | Không phải String không rỗng
Hi -> false | String(2): Hi
Java -> false | String(4): Java
Java 17 -> true | String(7): Java 17
```

Hãy quan sát các đầu vào `null` và `123`. Mọi lệnh như `text.isBlank()`, `text.length()`, `text.startsWith(...)` đều bị bỏ qua khi phép `instanceof` sai. Với `"Hi"`, kiểm tra kiểu đúng nhưng điều kiện độ dài `>= 5` sai, nên lệnh `startsWith` ở cuối chuỗi `&&` của phương thức `startsWithJava` cũng không cần chạy.

## 14. Các sai lầm khi kết hợp pattern và short-circuit

### Sai lầm 1 — Dùng `||` thay `&&`

```java
// Sai: text không có phạm vi hợp lệ ở bên phải ||.
// if (input instanceof String text || text.length() > 3) {}
```

Sửa khi muốn cả hai điều kiện đúng:

```java
if (input instanceof String text && text.length() > 3) {
    System.out.println(text);
}
```

### Sai lầm 2 — Dùng `&` thay `&&`

```java
// Sai: & đánh giá cả hai toán hạng và không cấp flow scope như &&.
// if (input instanceof String text & text.length() > 3) {}
```

Sửa bằng `&&`.

### Sai lầm 3 — Kiểm tra thuộc tính trước khi kiểm tra kiểu

```java
// Sai: matched chưa được khai báo.
// if (matched.length() > 3 && input instanceof String matched) {}
```

Sửa bằng cách đặt `instanceof String matched` ở bên trái.

### Sai lầm 4 — Dùng pattern variable ngoài đường đi đã khớp

```java
if (input instanceof String text && text.length() > 3) {
    System.out.println(text); // Đúng
}

// Sai: không chắc input khớp kiểu.
// System.out.println(text);
```

Sửa bằng cách đặt lệnh cần `text` ở nhánh đã khớp hoặc sử dụng guard clause kết thúc sớm những đường không khớp.

### Sai lầm 5 — Tin rằng short-circuit kiểm tra mọi tính hợp lệ của dữ liệu

```java
Object input = "  ";

if (input instanceof String text && text.length() > 0) {
    System.out.println("Có nội dung"); // Vẫn chạy với chuỗi chỉ có khoảng trắng
}
```

`&&` chỉ quyết định thứ tự và điều kiện đánh giá; **nó không tự xác định dữ liệu nào được coi là hợp lệ**. Nếu yêu cầu chuỗi có ký tự khác khoảng trắng, dùng `!text.isBlank()`:

```java
if (input instanceof String text && !text.isBlank()) {
    System.out.println("Có nội dung thực sự");
}
```

### Sai lầm 6 — Giả định Java 17 cho pattern với mọi kiểu dữ liệu

Trong Java 17, *type pattern* của `instanceof` áp dụng cho **kiểu tham chiếu thích hợp**, không viết pattern cho giá trị nguyên thủy kiểu `int`:

```java
int number = 42;

// Sai trong Java 17.
// if (number instanceof int n) {}
```

Nếu một biến đã có kiểu `String`, việc kiểm tra nó bằng pattern `instanceof String text` cũng không mang lại phép kiểm tra kiểu hữu ích; trong Java 17, trường hợp biểu thức có kiểu tĩnh là subtype của kiểu pattern có thể bị từ chối ở thời điểm biên dịch. Pattern phù hợp nhất khi cần **kiểm tra và thu hẹp từ kiểu cha/interface xuống một kiểu cụ thể**.

## 15. Bài tập tự luyện và giải thích

### Bài 1 — Đánh giá những toán hạng nào?

Cho:

```java
Object value = 15;

if (value instanceof String text
        && text.length() > 2
        && text.startsWith("A")) {
    System.out.println("OK");
}
```

**Câu hỏi:** Có bao nhiêu phép kiểm tra thực sự được thực hiện?

**Giải thích:** Chỉ đánh giá `value instanceof String text`. Kết quả là `false`, nên cả `text.length()` và `text.startsWith("A")` đều bị bỏ qua. Khối `if` không chạy.

### Bài 2 — Sửa đoạn code sai phạm vi biến

Đoạn sai:

```java
// if (obj instanceof String text || text.isEmpty()) {
//     System.out.println("Empty");
// }
```

Nếu yêu cầu là **chỉ in thông báo khi obj là String rỗng**, hãy sửa:

```java
if (obj instanceof String text && text.isEmpty()) {
    System.out.println("Empty");
}
```

Nếu yêu cầu là **in thông báo khi obj không phải String hoặc là String rỗng**, dùng:

```java
if (!(obj instanceof String text) || text.isEmpty()) {
    System.out.println("Không phải chuỗi hoặc chuỗi rỗng");
}
```

Hai yêu cầu nghiệp vụ khác nhau nên biểu thức đúng cũng khác nhau.

### Bài 3 — Tại sao đoạn sau không biên dịch?

```java
Object left = "ABC";
Object right = "XYZ";

// Sai: hai pattern variable có cùng tên.
// if (left instanceof String s
//         && right instanceof String s
//         && s.length() > 2) {
//     System.out.println(s);
// }
```

**Giải thích:** Hai type pattern đều muốn khai báo `s` trong những phạm vi có thể chồng lấn. Dùng tên khác nhau như `first` và `second` để thể hiện hai đối tượng độc lập.

### Bài 4 — Chọn một guard clause phù hợp

Viết phương thức nhận `Object` và trả độ dài của chuỗi **không rỗng**, còn lại ném `IllegalArgumentException`.

Gợi ý với Java 17:

```java
static int lengthOfNonBlank(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Expected nonblank String");
    }

    return text.length();
}
```

Câu hỏi tự kiểm tra:

1. Nếu `input` là `null`, Java có gọi `text.isBlank()` không?
2. Nếu `input` là `42`, vì sao không xảy ra `ClassCastException`?
3. Nếu `input` là `"   "`, vì sao phương thức ném ngoại lệ?
4. Vì sao `text` hợp lệ ở dòng `return`?

**Đáp án:** (1) Không, `||` dừng ở vế trái `true`. (2) Không thực hiện ép kiểu cưỡng bức, phép `instanceof` trả `false`. (3) Type pattern khớp nhưng `isBlank()` trả `true`. (4) Mọi đường thực thi tới `return` đều đã vượt qua điều kiện kiểm tra kiểu và nội dung, vì nhánh không hợp lệ đã kết thúc bằng `throw`.

## 16. Ghi nhớ khi đọc hoặc viết `instanceof` kết hợp `&&`

Công thức thường dùng nhất:

```java
if (obj instanceof SomeType value
        && check1(value)
        && check2(value)) {
    use(value);
}
```

Hãy đọc như một chuỗi điều kiện bảo vệ:

- `obj instanceof SomeType value`: kiểm tra kiểu và ràng buộc biến pattern `value`.
- `&& check1(value)`: chỉ chạy khi pattern đã khớp.
- `&& check2(value)`: chỉ chạy khi mọi điều kiện trước đều đúng.
- Khối `if`: được thực thi khi tất cả đều đúng; `value` có phạm vi hợp lệ ở đây.

Khi đảo điều kiện bằng `!` hoặc thay `&&` bằng `||`, **hướng mà biến pattern chắc chắn khớp cũng thay đổi**. Đó là lý do cần hiểu cả hai phần: **đánh giá ngắn mạch lúc chạy** và **kiểm tra phạm vi biến lúc biên dịch**.

## Tài liệu tham khảo chính thức cho Java 17

- [JLS Java SE 17 — `15.20.2: toán tử `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2).
- [JLS Java SE 17 — `15.23: toán tử conditional-and `&&`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.23).
- [JLS Java SE 17 — `15.24: toán tử conditional-or `||`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.24).
- [JLS Java SE 17 — `6.3.1.1: scope của pattern variables với `&&`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1.1).
- [JLS Java SE 17 — `6.3.1.2–6.3.1.3: scope với `||` và `!`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1.2).
- [JLS Java SE 17 — `6.3.2: scope trong câu lệnh `if` và các câu lệnh khác](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.2).
- [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394).

