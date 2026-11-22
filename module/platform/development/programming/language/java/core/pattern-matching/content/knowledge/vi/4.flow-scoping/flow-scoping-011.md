# Quan hệ giữa reachability và definite matching trong Java

**Chủ đề:** Flow scoping của pattern variables, đặt trong bối cảnh phân tích luồng điều khiển của Java Language Specification (JLS). Các ví dụ dùng Java 17 trở lên và tập trung vào `instanceof`; các quy tắc tương ứng được trình bày theo JLS Java SE 21. Không cần bật preview.

Một câu hỏi thường gặp: **Tại sao sau một lệnh `if` có thể dùng biến khai báo trong `instanceof` ở chỗ này, nhưng ở chỗ khác Java lại báo biến không tồn tại?** Để trả lời chính xác, cần phân biệt ba khái niệm được trình biên dịch phân tích:

1. **Reachability:** câu lệnh có được xem là *có thể đi tới* theo quy tắc tĩnh của JLS không?
2. **Can complete normally:** câu lệnh có thể kết thúc và chuyển điều khiển tới câu lệnh ngay sau nó mà không kết thúc đột ngột bằng `return`, `throw` hoặc một cách chuyển điều khiển khác không?
3. **Definite matching:** tại một điểm của luồng điều khiển, trình biên dịch có biết chắc pattern đã khớp và **pattern variable** đã nhận giá trị không?

Đây là ba phân tích liên quan nhưng **không đồng nhất**. Một câu lệnh có thể *reachable* mà một biến pattern vẫn **không definitely matched** tại đó.

## 1. Reachability theo JLS `14.22

**Reachability** trả lời câu hỏi: *Có một đường đi hợp lệ về mặt cấu trúc từ đầu phương thức, constructor hoặc khối khởi tạo đến câu lệnh này hay không?*

JLS `14.22 định nghĩa các quy tắc tĩnh để xác định tính reachable. Một câu lệnh bị xem là **unreachable** gây lỗi biên dịch. Phân tích này chủ yếu dựa vào cấu trúc câu lệnh và khả năng kết thúc bình thường, không phải công cụ dự đoán mọi giá trị runtime.

Ví dụ **không biên dịch**:

```java
static void unreachableExample() {
    return;
    System.out.println("Không bao giờ tới đây"); // Unreachable statement
}
```

Dòng `println` đứng ngay sau `return` trong cùng khối. Không còn đường đi bình thường nào tới nó nên trình biên dịch báo lỗi.

### Reachability là phân tích bảo thủ, không phải mô phỏng runtime

So sánh hai đoạn **minh họa độc lập**:

```java
static void accepted() {
    if (false) {
        System.out.println("Never printed");
    }
}
```

Đoạn `if (false)` trên được Java chấp nhận; thân `if` không chạy trong thực tế nhưng quy tắc reachability của `if` vẫn coi nó reachable.

```java
// KHÔNG BIÊN DỊCH:
static void rejected() {
    while (false) {
        System.out.println("Unreachable");
    }
}
```

Với `while (false)`, JLS có quy tắc đặc biệt khiến thân vòng lặp bị xem là unreachable. Sự khác nhau này cho thấy không thể thay định nghĩa JLS bằng trực giác “câu nào thực tế sẽ chạy”.

## 2. “Can complete normally” nối reachability với flow scoping

Trong JLS `14.22, một câu lệnh **can complete normally** nếu xét theo các quy tắc của ngôn ngữ, nó có thể kết thúc để luồng điều khiển tiếp tục đến câu lệnh kế tiếp.

- Một lệnh `return` hoặc `throw` không hoàn thành bình thường: nó rời phương thức hoặc ném ngoại lệ.
- Một lệnh `break` hợp lệ chuyển điều khiển ra khỏi cấu trúc mà nó nhắm tới; việc có `break` **reachable** là yếu tố quan trọng trong quy tắc kết thúc vòng lặp và phạm vi pattern.
- Một câu lệnh `if` có thể hoàn thành bình thường nếu có đường đi hợp lệ đi qua cấu trúc `if` mà không kết thúc đột ngột.
- Với cấu trúc lặp, các quy tắc đặc biệt của `while`, `for` và `do` quyết định liệu có thể thoát vòng lặp bình thường hay không.

Ví dụ:

```java
static String check(Object obj) {
    if (!(obj instanceof String text)) {
        return "Không phải chuỗi";
    }
    return text.toUpperCase(); // Hợp lệ
}
```

Lý do `text` hợp lệ sau `if` **không phải** chỉ vì dòng `return text.toUpperCase()` reachable. Điều quyết định là **mọi đường đi còn tiếp tục sau `if` đều đã có phép khớp `String text` thành công**. Đường đi thất bại đã kết thúc bằng `return` nên không thể tới dòng cuối.

Nếu bỏ `return` trong nhánh thất bại:

```java
// KHÔNG BIÊN DỊCH:
static void broken(Object obj) {
    if (!(obj instanceof String text)) {
        System.out.println("Không phải chuỗi");
    }
    System.out.println(text.length()); // text không definitely matched
}
```

Dòng cuối **reachable**, nhưng có đường đi đến đó khi `obj` không phải `String`. Vì thế `text` không nằm trong phạm vi được chứng minh đã khớp. Thay một lệnh kết thúc luồng bằng một lệnh chỉ in thông báo làm thay đổi quy tắc flow scoping.

## 3. Definite matching theo JLS `6.3 là gì?

**Definite matching** là bảo đảm tĩnh rằng, ở vị trí định dùng một pattern variable, phép khớp tạo ra biến ấy chắc chắn đã thành công. Trong JLS, các quy tắc này chủ yếu mô tả việc một biến được **introduced by** một biểu thức **when true**, **when false**, hoặc bởi một câu lệnh; biến đó được **definitely matched** tại các vị trí thích hợp.

Phép kiểm tra đơn giản:

```java
obj instanceof String text
```

“Giới thiệu” biến `text` **when true**: nếu cả biểu thức đúng, `obj` đã khớp type pattern `String text` và `text` mang tham chiếu tương ứng. Nếu sai, không có bảo đảm về `text`.

Khi phủ định:

```java
!(obj instanceof String text)
```

Biến `text` được giới thiệu **when false**, bởi khi biểu thức phủ định sai thì phép `instanceof` bên trong phải đúng. Điều này giải thích vì sao `if (!(...)) return;` có thể đưa biến ra sử dụng sau `if`.

### Một bảng phân biệt ngắn

| Phân tích | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Reachability** (`14.22) | Có đường đi tới **câu lệnh** không? | Lệnh sau `return` không reachable. |
| **Can complete normally** (`14.22) | Câu lệnh có thể chuyển tiếp sang câu sau không? | Nhánh chỉ chứa `throw` không hoàn thành bình thường. |
| **Definite matching** (`6.3) | Pattern variable chắc chắn đã được khởi tạo vì phép khớp thành công chưa? | Sau `if (!(obj instanceof String s)) return;`, `s` được definitely matched. |
| **Definite assignment** (`16) | Biến cục bộ thông thường đã chắc chắn được gán giá trị trước khi đọc chưa? | `int n;` chỉ được dùng khi mọi đường đi hợp lệ đã gán `n`. |

**Definite matching và definite assignment không phải hai cách gọi cho cùng một phép kiểm tra.** Quy tắc về pattern variable và phạm vi của nó nằm ở `6.3; các quy tắc chắc chắn được gán cho biến cục bộ thông thường nằm ở `16.

## 4. Definite matching trong biểu thức điều kiện: `&&`, `||` và `!`

### 4.1. Với `&&`: đường đi đúng ở vế trái

```java
static boolean isLongString(Object obj) {
    return obj instanceof String text && text.length() >= 4;
}
```

Vế phải của `&&` chỉ được đánh giá nếu vế trái đúng. Tại thời điểm chạy `text.length()`, `String text` đã khớp, vì thế `text` **definitely matched** ở đó.

Ngược lại:

```java
// KHÔNG BIÊN DỊCH:
static boolean invalid(Object obj) {
    return obj instanceof String text || text.isBlank();
}
```

Vế phải của `||` được chạy khi vế trái **sai**, tức là đúng lúc `text` chưa chắc có giá trị. Lỗi này là lỗi về phạm vi/definite matching, không liên quan đến câu lệnh unreachable.

### 4.2. Với `!` và `||`: điều kiện phủ định có thể làm `||` hợp lệ

Dấu `!` đảo cách truyền thông tin **when true/when false**:

```java
static String usableText(Object obj) {
    if (!(obj instanceof String text) || text.isBlank()) {
        return "missing";
    }
    return "valid: " + text;
}
```

Đoạn này **hợp lệ**:

1. Vế phải `text.isBlank()` của `||` chỉ chạy khi `!(obj instanceof String text)` là **false**, tức `String text` đã khớp.
2. Khi toàn bộ điều kiện `if` là **true**, phương thức trả về `"missing"` và kết thúc.
3. Chỉ khi điều kiện `if` là **false** chương trình mới đi tới dòng cuối, và khi đó `text` chắc chắn đã khớp và không blank.

Đây là ví dụ trực tiếp cho việc definite matching phụ thuộc cả **giá trị logic của biểu thức** lẫn **khả năng hoàn thành bình thường** của câu lệnh chứa nó.

### 4.3. Biểu thức ba ngôi `?:`

```java
static String label(Object obj) {
    return obj instanceof String text ? text.toUpperCase() : "other";
}
```

`text` definitely matched trong nhánh giữa (nhánh **true**); không thể giả định nó đã khớp trong nhánh `"other"`. Dấu ngoặc quanh một biểu thức không phá vỡ thông tin matching, nhưng việc gán kết quả biểu thức vào một biến `boolean` khác không tự tạo một pattern scope mới.

## 5. Quan hệ trong `if`: nhánh có thể đi tới và nhánh chắc chắn đã khớp

### 5.1. Bên trong nhánh `then` của `instanceof`

```java
static void show(Object obj) {
    if (obj instanceof String text) {
        System.out.println(text.length()); // Hợp lệ
    } else {
        System.out.println("other");
        // text không có phạm vi ở đây.
    }
}
```

Nhánh `then` reachable và có điều kiện khớp đúng; `text` được definitely matched bên trong. Nhánh `else` cũng có thể reachable, nhưng không có bảo đảm khớp.

### 5.2. Sau `if` với đường đi thất bại kết thúc

```java
static int requireLength(Object obj) {
    if (!(obj instanceof String text)) {
        throw new IllegalArgumentException("Expected String");
    }
    return text.length(); // Hợp lệ
}
```

Theo `6.3.2.2`, biến được biểu thức `if` giới thiệu **when false** có thể được giới thiệu bởi chính câu lệnh `if` khi thân nhánh `then` **cannot complete normally**. Sau lệnh `if` này, mọi đường đi tiếp tục đều ứng với biểu thức phủ định sai, tức pattern đã khớp.

### 5.3. Sau `if / else` với đúng một nhánh có thể tiếp tục

```java
static String requireText(Object obj) {
    if (obj instanceof String text) {
        System.out.println("Matched");
    } else {
        throw new IllegalArgumentException("Expected String");
    }
    return text; // Hợp lệ
}
```

JLS `6.3.2.2` cho phép biến pattern từ nhánh điều kiện **true** được giới thiệu sau `if / else` khi nhánh `then` có thể hoàn thành bình thường, còn nhánh `else` thì không. Trường hợp đối xứng cũng tồn tại: biến được giới thiệu theo điều kiện **false** có thể xuất hiện sau `if / else` nếu nhánh `then` không hoàn thành bình thường, còn `else` thì có.

**Điểm cần nhớ:** Không phải chỉ cần viết `if (obj instanceof String text)` thì `text` luôn tồn tại sau câu `if`. Phải xét **mọi đường đi có thể đến điểm sử dụng**, đặc biệt là nhánh nào kết thúc bằng `return` hoặc `throw`.

## 6. Quan hệ trong `while` và `for`: vai trò của `break` reachable

### 6.1. `while` không có `break` thoát khỏi vòng lặp

```java
static String untilString(Object initial) {
    Object current = initial;
    while (!(current instanceof String text)) {
        current = "ready";
    }
    return text; // Hợp lệ: vòng lặp chỉ kết thúc bình thường khi pattern khớp.
}
```

Ở mỗi lần kiểm tra điều kiện, khi `current` không phải `String` thì điều kiện phủ định đúng và vòng lặp chạy. Nếu vòng lặp kết thúc bình thường bằng cách điều kiện trở thành **false**, `current instanceof String text` đã đúng, nên `text` được definitely matched sau vòng lặp.

JLS `6.3.2.3` sử dụng điều kiện rất cụ thể: biến pattern được giới thiệu **when false** bởi biểu thức điều kiện vòng lặp và **không có `break` reachable nhắm tới vòng lặp**. Trong ví dụ trên, thân vòng lặp gán `current = "ready"`, bảo đảm có trường hợp thoát và giúp ví dụ chạy hữu hạn.

### 6.2. Thêm một `break` reachable làm mất bảo đảm sau vòng lặp

```java
// KHÔNG BIÊN DỊCH:
static void brokenLoop(Object initial) {
    Object current = initial;
    while (!(current instanceof String text)) {
        if (current == null) {
            break; // Có thể thoát mà chưa khớp String text.
        }
        current = "ready";
    }
    System.out.println(text); // Không definitely matched.
}
```

`break` có thể đưa chương trình đến dòng cuối với `current == null`, nghĩa là `text` không có giá trị. Do đó, trình biên dịch không cho dùng `text` sau vòng lặp.

Điểm tinh tế: JLS xét liệu `break` **reachable theo quy tắc tĩnh** hay không. Nó không yêu cầu chứng minh từ dữ liệu runtime rằng nhánh `break` chắc chắn sẽ xảy ra. `break` nhắm đến vòng lặp khác hoặc nhãn khác phải được phân tích theo đích điều khiển thực sự của nó.

### 6.3. Với vòng `for` cơ bản

Các quy tắc `6.3.2.5` tương tự: biến được giới thiệu bởi điều kiện **when true** có thể được dùng trong thân vòng lặp và phần cập nhật; nếu muốn dùng biến **sau vòng lặp** từ điều kiện **when false**, còn phải đáp ứng quy tắc về `break` reachable nhắm tới vòng lặp đó.

```java
static String basicFor(Object initial) {
    Object current = initial;
    for (; !(current instanceof String text); current = "done") {
        // Thân rỗng, không có break.
    }
    return text; // Hợp lệ sau khi điều kiện phủ định trở thành false.
}
```

Với `do...while`, JLS cũng xét biến được giới thiệu **when false** bởi điều kiện, cùng quy tắc về `break` reachable. Tuy nhiên, thân `do` chạy trước khi điều kiện được đánh giá lần đầu; không được tùy tiện dùng biến được khai báo trong điều kiện ở thân vòng lặp.

## 7. Reachable chưa đủ: hai tình huống dễ nhầm

### Tình huống A: câu lệnh tới được nhưng pattern chưa chắc khớp

```java
// KHÔNG BIÊN DỊCH:
static void notDefinitelyMatched(Object obj) {
    if (obj instanceof String text) {
        System.out.println("String");
    }
    System.out.println(text.length());
}
```

Dòng cuối reachable trong cả hai trường hợp `obj` có hoặc không phải `String`. Chính vì có đường đi **không khớp** đến đó, `text` không definitely matched.

### Tình huống B: lưu kết quả `instanceof` vào `boolean` không giữ scope của biến

```java
// KHÔNG BIÊN DỊCH:
static void booleanAlias(Object obj) {
    boolean matches = obj instanceof String text;
    if (matches) {
        System.out.println(text.length());
    }
}
```

Lập luận runtime “`matches` đúng thì `text` đã khớp” nghe hợp lý, nhưng JLS không chuyển definite matching qua **biến `boolean` trung gian** theo cách này. Pattern variable `text` được giới thiệu bởi biểu thức `instanceof` tại vị trí tương ứng, không trở thành biến có phạm vi ở mọi vị trí chỉ nhờ lưu kết quả kiểm tra.

Cách đúng là giữ biểu thức `instanceof` tại điều kiện cho phép dùng biến:

```java
static void directCheck(Object obj) {
    if (obj instanceof String text) {
        System.out.println(text.length());
    }
}
```

## 8. Phân biệt definite matching với definite assignment (`16)

Một biến cục bộ bình thường phải được **definitely assigned** trước khi đọc:

```java
static int lengthOrZero(Object obj) {
    int result;

    if (obj instanceof String text) {
        result = text.length();
    } else {
        result = 0;
    }

    return result; // Hợp lệ: result được gán ở cả hai nhánh.
}
```

Tại `return result`, `result` definitely assigned vì cả hai nhánh đã gán nó. Nhưng `text` chỉ definitely matched bên trong nhánh `then`; không thể dùng `text` ở dòng trả về đó.

Tương tự, một đoạn không biên dịch nếu bỏ việc gán trong nhánh `else`:

```java
// KHÔNG BIÊN DỊCH:
static int incomplete(Object obj) {
    int result;
    if (obj instanceof String text) {
        result = text.length();
    }
    return result; // Variable result might not have been initialized.
}
```

**Definite assignment** bảo vệ việc đọc biến cục bộ chưa gán; **definite matching** quyết định phần nào của chương trình có thể tham chiếu biến khai báo từ pattern thành công. Cả hai đều phụ thuộc đường đi tĩnh nhưng được quy định ở các chương JLS khác nhau.

## 9. Chương trình hoàn chỉnh: đối chiếu các quy tắc

Tạo tệp **`ReachabilityMatchingDemo.java`** với mã dưới đây. Ví dụ chỉ dùng tính năng ổn định trong Java 17:

```java
public class ReachabilityMatchingDemo {
    static String describe(Object value) {
        // Nhánh không khớp kết thúc bằng return.
        if (!(value instanceof String text)) {
            return "not-string";
        }
        // Chỉ đường đi đã khớp có thể tới đây.
        return "String: " + text.toUpperCase();
    }

    static String guarded(Object value) {
        // && không phải cách duy nhất để dùng biến pattern an toàn.
        // Sau phủ định, vế phải || chỉ chạy khi String đã khớp.
        if (!(value instanceof String text) || text.isBlank()) {
            return "missing";
        }
        return "valid: " + text;
    }

    static String scanUntilString(Object initial) {
        Object current = initial;
        while (!(current instanceof String text)) {
            current = "ready"; // Không có break thoát vòng lặp.
        }
        return "loop: " + text;
    }

    static String ifElse(Object value) {
        if (value instanceof String text) {
            System.out.println("inside: " + text.length());
        } else {
            throw new IllegalArgumentException("need String");
        }
        return "after-if: " + text;
    }

    static int lengthOrZero(Object value) {
        int result;
        if (value instanceof String text) {
            result = text.length();
        } else {
            result = 0;
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(describe("java"));
        System.out.println(describe(42));
        System.out.println(guarded("ABC"));
        System.out.println(guarded("  "));
        System.out.println(guarded(2));
        System.out.println(scanUntilString(5));
        System.out.println(scanUntilString("ok"));
        System.out.println(ifElse("flow"));
        System.out.println(lengthOrZero("hello"));
        System.out.println(lengthOrZero(null));
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp với **JDK 17 trở lên**:

```bash
javac --release 17 -encoding UTF-8 ReachabilityMatchingDemo.java
java ReachabilityMatchingDemo
```

Kết quả:

```text
String: JAVA
not-string
valid: ABC
missing
missing
loop: ready
loop: ok
inside: 4
after-if: flow
5
0
```

**Đọc kết quả theo luồng điều khiển:**

1. `describe("java")` vượt qua nhánh `return` dành cho giá trị không khớp; `text` được dùng an toàn ở dòng sau.
2. `describe(42)` kết thúc ngay ở nhánh không khớp.
3. `guarded("ABC")` chứng minh phủ định và `||` cho phép kiểm tra `text.isBlank()`; chuỗi có nội dung đi tới dòng cuối.
4. `guarded("  ")` trả về `missing` vì `text` khớp nhưng blank; `guarded(2)` cũng trả về `missing` vì không khớp.
5. Hai lệnh gọi `scanUntilString` kết thúc khi điều kiện phủ định là `false`; không có `break` đưa ra ngoài với pattern chưa khớp.
6. `ifElse("flow")` đi qua nhánh `then` có thể hoàn thành bình thường; nhánh `else` chỉ ném ngoại lệ nên `text` có thể dùng sau câu `if`.
7. `lengthOrZero` minh họa rõ sự khác nhau: biến `result` definitely assigned ở cuối, còn `text` chỉ nằm trong nhánh khớp.

## 10. Cách suy luận cho một đoạn code bất kỳ

Khi thấy một pattern variable được dùng sau `if` hoặc vòng lặp, hãy kiểm tra theo thứ tự:

1. **Nơi khai báo:** pattern nào khai báo biến, chẳng hạn `obj instanceof String text`?
2. **Nhánh logic chắc chắn:** phép khớp được giới thiệu **when true** hay **when false**? Dấu `!`, `&&`, `||` hoặc `?:` có đổi điểm được phép sử dụng không?
3. **Luồng điều khiển:** để đi đến chỗ dùng biến, chương trình có thể đi qua đường mà pattern thất bại không?
4. **Hoàn thành bình thường:** nhánh thất bại có `return` hoặc `throw` và không thể tiếp tục không? Đối với `if / else`, nhánh nào còn đi tiếp?
5. **Vòng lặp:** có `break` reachable nào nhắm vào chính vòng lặp, cho phép thoát mà không cần điều kiện trở thành false không?
6. **Khả năng tới câu lệnh:** câu lệnh sử dụng biến có reachable không? Nếu không, đó là lỗi độc lập về unreachable statement; nếu có, vẫn cần kiểm tra definite matching.
7. **Biến thường:** nếu code sử dụng cả biến cục bộ thường như `result`, kiểm tra thêm quy tắc definite assignment.

Tự thử dự đoán trước khi biên dịch:

**Bài tập A.** Đoạn sau có hợp lệ không?

```java
static int testA(Object obj) {
    if (!(obj instanceof String s)) return -1;
    return s.length();
}
```

**Đáp án:** Có. Chỉ phép khớp thành công mới đi tới `s.length()`.

**Bài tập B.** Đoạn sau có hợp lệ không?

```java
// KHÔNG BIÊN DỊCH:
static int testB(Object obj) {
    if (obj instanceof String s) {
        System.out.println("yes");
    }
    return s.length();
}
```

**Đáp án:** Không. `return` reachable nhưng nhánh không khớp cũng tới được dòng đó; `s` không definitely matched.

**Bài tập C.** Vì sao chỉ thêm một `break` vào thân `while (!(obj instanceof String s))` có thể làm mất quyền dùng `s` sau vòng lặp?

**Đáp án:** Vì `break` reachable có thể đưa điều khiển ra khỏi vòng lặp trước khi biểu thức điều kiện trở thành `false`. Đến điểm sau vòng lặp không còn đảm bảo `instanceof String s` từng thành công.

**Bài tập D.** Nếu sửa `if (!(obj instanceof String s)) return;` thành `if (!(obj instanceof String s)) System.out.println("skip");` thì chuyện gì xảy ra?

**Đáp án:** Nhánh thất bại có thể hoàn thành bình thường. Sau `if`, `s` không còn được definite matching bảo đảm; sử dụng `s` ở đó gây lỗi biên dịch.

## 11. Các lỗi suy luận cần tránh

- **Đồng nhất “reachable” với “đã khớp”.** Reachability kiểm tra câu lệnh có đường đi đến; definite matching kiểm tra biến pattern có chắc đã gắn giá trị trên đường đi đó.
- **Cho rằng chỉ cần code “thực tế sẽ không chạy” là trình biên dịch cũng biết.** JLS dùng những quy tắc cấu trúc rõ ràng, không suy diễn tùy ý từ trạng thái runtime.
- **Bỏ quên khái niệm “can complete normally”.** Chính đặc tính này quyết định khả năng đưa biến pattern ra sau `if`/`if-else`.
- **Quên tác động của `break` reachable trong vòng lặp.** Một đường thoát bổ sung có thể khiến pattern không còn definitely matched ở điểm sau vòng lặp.
- **Nhầm `definite matching` với `definite assignment`.** Pattern variable và biến cục bộ thường tuân theo các quy tắc tương ứng ở `6.3` và `16`.
- **Tách điều kiện pattern thành biến `boolean` rồi mong còn truy cập pattern variable.** Phạm vi phải theo các dạng biểu thức/câu lệnh mà JLS quy định; không có cơ chế suy luận alias `boolean` tổng quát.
- **Dùng sai `&&`/`||`.** Xét nhánh logic nào khiến vế phải chạy; `a instanceof String s && s.length() > 0` hợp lệ, còn phiên bản `||` không phủ định thì không.

## Tài liệu đặc tả chính thức

- [JLS Java SE 21 `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): flow scoping, *introduced by*, *definitely matched* và quy tắc cho `if`/vòng lặp.
- [JLS Java SE 21 `14.22 — Unreachable Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.22): reachability và *can complete normally*.
- [JLS Java SE 21 `16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se21/html/jls-16.html): phân tích chắc chắn được gán cho biến cục bộ.
- [JLS Java SE 21 `15.20.2 — `instanceof`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): điều kiện khớp kiểu.
- [JLS Java SE 21 `14.9 — `if` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.9), [`14.12 — `while` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.12): quy tắc điều khiển được phân tích khi xác định definite matching.
