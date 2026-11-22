# Giới hạn sử dụng biến mẫu với toán tử `||` trong Java

> **Phạm vi:** Bài thuộc **Java 14 → Phạm vi biến mẫu** nhưng áp dụng quy tắc **Java hiện hành**. Pattern matching cho `instanceof` từng được giới thiệu thử nghiệm quanh Java 14 và trở thành tính năng chuẩn từ **Java 16** (JEP 394). Các ví dụ dùng Java **17+**, không cần `--enable-preview`. Bài tập trung đúng vào **toán tử OR ngắn mạch `||`**, cách compiler xác định **phạm vi (scope)** của biến mẫu và sự khác biệt với `&&`.

## 1. Mục tiêu

Sau bài học, bạn cần:

1. Giải thích vì sao `value instanceof String s || s.isBlank()` **không biên dịch**, dù `s` được khai báo trong toán hạng trái.
2. Hiểu khi nào `s` được xem là **definitely matched** tại toán hạng phải của `||`.
3. Viết đúng mẫu có phủ định: `!(value instanceof String s) || s.isBlank()`.
4. Xác định có được dùng biến mẫu trong **nhánh `if`/`else`** và ở **các câu lệnh sau một guard clause** hay không.
5. Phân biệt `||` với `&&`, `!` và `|` để không dùng biến trước khi việc khớp mẫu được chứng minh.
6. Nhận diện lỗi khi khai báo cùng tên biến mẫu trong hai nhánh OR, và chọn cách thay thế đúng.
7. Kiểm chứng mọi kết luận bằng các ví dụ Java 17+ có lệnh biên dịch và stdout xác định.

## 2. Biến mẫu `instanceof` chỉ tồn tại khi compiler chứng minh khớp

Trong Java hiện hành, biểu thức:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length());
}
```

không chỉ kiểm tra kiểu. Nếu phép kiểm tra thành công, một **pattern variable** tên `text`, kiểu `String`, được khởi tạo từ `value`. Nhưng **phạm vi của biến mẫu không đơn giản kéo dài từ điểm khai báo đến hết block** như nhiều biến cục bộ thông thường.

JLS `6.3` dùng phân tích luồng (**flow scoping**) để xác định chính xác ở vị trí nào biến đã được khớp và được phép sử dụng. Khái niệm quan trọng là:

- **Introduced when true:** Một biểu thức bảo đảm biến mẫu được khớp nếu kết quả của biểu thức là `true`.
- **Introduced when false:** Một biểu thức bảo đảm biến mẫu được khớp nếu kết quả của biểu thức là `false`.
- **Definitely matched tại vị trí dùng:** Mọi đường điều khiển thực sự đi tới vị trí đó đều đã khớp và khởi tạo biến mẫu.

Với `value instanceof String text`, biến `text` được **introduced when true**, vì chỉ khi kết quả `true` ta mới biết `value` là một `String` và đã gán biến `text`.

Khi `value` không phải `String` hoặc là `null`, `instanceof` trả `false` và **không có giá trị `text` đã được khớp**. Java vì thế không cho dùng `text` ở nơi có thể được đi tới bằng nhánh kiểm tra thất bại.

**Đây là kiểm tra kiểu và phạm vi tại compile time.** Compiler không dựa vào việc bạn «biết chắc» dữ liệu test đang là chuỗi để bỏ qua những đường chạy còn lại.

## 3. Bản chất của `||`: Vế phải chỉ chạy khi vế trái `false`

Toán tử conditional OR `a || b` được đánh giá từ trái sang phải và **ngắn mạch**:

| Giá trị của `a` | Có đánh giá `b`? | Kết quả của `a || b` |
| --- | --- | --- |
| `true` | **Không** | `true` |
| `false` | **Có** | Bằng kết quả của `b` |

Vì vậy, khi compiler xét một biến mẫu có được dùng tại `b` không, câu hỏi đúng là:

**Nếu `a` là `false` và chương trình phải đánh giá `b`, biến mẫu đã được khớp chắc chắn chưa?**

JLS **`6.3.1.2 — Conditional-Or Operator `||`** quy định:

> Biến mẫu được biểu thức bên trái đưa vào **khi false** thì được xem là đã khớp tại biểu thức bên phải.

Đồng thời, toàn bộ `a || b` có thể đưa một biến mẫu vào **khi false**, nếu một trong hai toán hạng đưa biến đó vào khi false. Không có quy tắc tổng quát đưa biến vào **khi true** cho một biểu thức OR, vì kết quả `true` có thể đến từ hai đường đánh giá khác nhau.

Đây là điểm khác biệt quan trọng so với toán tử `&&`, nơi toán hạng phải chỉ chạy khi toán hạng trái `true`.

## 4. Trường hợp SAI phổ biến: `instanceof` dương bên trái `||`

Xét đoạn code bên trong một phương thức:

```java
// CỐ Ý SAI: không biên dịch.
if (value instanceof String text || text.isBlank()) {
    System.out.println("accepted");
}
```

Phân tích từng đường chạy:

1. Nếu `value instanceof String text` là `true`, Java **không đánh giá vế phải**, nên `text.isBlank()` không được gọi.
2. Nếu biểu thức `instanceof` là `false`, Java **phải đánh giá vế phải**.
3. Nhưng lúc đó `text` **chưa được khớp và khởi tạo**, vì `value` không phải chuỗi hoặc là `null`.
4. Do đó tên `text` **không nằm trong phạm vi hợp lệ** của vế phải; compiler báo lỗi, thường là không thể giải quyết ký hiệu `text`.

Không được sửa bằng `(value instanceof String text) || text.isBlank()`: **ngoặc đơn không đổi** nhánh điều kiện đưa chương trình vào vế phải. Việc chuyển sang `|` (OR không ngắn mạch) cũng không giải quyết phạm vi và còn làm mất lợi ích ngắn mạch.

### 4.1. Vì sao `||` không cứu được bằng cách «chạy trước rồi dùng»?

Một số người đọc mã từ trái sang phải và nghĩ rằng cứ đặt `instanceof String text` trước thì phần bên phải có thể dùng `text`. Điều đó sai vì tên biến mẫu không được quyết định chỉ bằng thứ tự xuất hiện trong source.

Cần hỏi **vế phải chạy lúc nào**, không phải **vế trái được viết ở đâu**. Với `||`, vế phải chạy khi vế trái **false**. Với `instanceof` dương, false chính là trường hợp **không khớp mẫu**.

### 4.2. Nếu chỉ muốn kết hợp hai kiểm tra độc lập

Giả sử bạn chỉ muốn cho phép một chuỗi **hoặc** một flag độc lập:

```java
static boolean allowed(Object value, boolean force) {
    return value instanceof String || force;
}
```

Đây là đoạn phương thức minh họa, không có `main` riêng. Cú pháp `instanceof String` thông thường trả boolean mà không khai báo biến mẫu. Khi không cần dùng giá trị chuỗi đã match, không cần tạo tên `text`.

Nếu cần xử lý giá trị chuỗi, hãy đặt logic dùng `text` vào nhánh mà compiler đã chứng minh match, chẳng hạn `if (value instanceof String text) { ... }` hoặc `&&`.

## 5. Trường hợp ĐÚNG: phủ định mẫu trước toán tử `||`

Mẫu thường dùng trong validation là:

```java
if (!(value instanceof String text) || text.isBlank()) {
    return "invalid";
}
return text.strip();
```

Đây là các câu lệnh trong **phương thức trả về `String`**. Cấu trúc hợp lệ với Java 17+.

Giải thích:

- `value instanceof String text` là `true` khi `value` khớp `String`.
- Dấu `!` đảo giá trị, nên `!(value instanceof String text)` là **false khi mẫu đã khớp**.
- Vế phải `text.isBlank()` của OR chỉ chạy nếu vế trái **false**.
- Vì vậy, ở vế phải, compiler **biết chắc** `text` đã khớp và có kiểu `String`.
- Nếu `value` không phải chuỗi, vế trái `true`, OR ngắn mạch nên không gọi `text.isBlank()`.

Có thể hình dung như sau:

```text
                  value instanceof String text
                         /          \
                  không khớp         khớp
                       |                |
            !(...) là true       !(...) là false
                       |                |
            OR ngắn mạch         chạy text.isBlank()
            không dùng text      text chắc chắn là String
```

### 5.1. Bảng ví dụ với dữ liệu đầu vào

| `value` | `value instanceof String text` | `!(...)` | Có chạy `text.isBlank()` không? | Điều kiện OR |
| --- | --- | --- | --- | --- |
| `"Java"` | `true` | `false` | Có, trả `false` | `false` |
| `"   "` | `true` | `false` | Có, trả `true` | `true` |
| `42` | `false` | `true` | Không | `true` |
| `null` | `false` | `true` | Không | `true` |

`String.isBlank()` là API ổn định từ Java 11, nên ví dụ Java 17+ dùng được. Điều kiện này vừa kiểm tra kiểu vừa tránh dùng chuỗi trắng khi dữ liệu không hợp lệ.

**Cần phân biệt:** Vế phải được phép dùng `text` vì **vế trái false chứng minh match**, chứ không phải vì biến mẫu «tồn tại sẵn từ trước» hay vì Java tự ép `value` thành `String` dù kiểm tra thất bại.

## 6. Vì sao `&&` lại cho phép cách viết ngược?

Toán tử conditional AND `a && b` chỉ đánh giá `b` khi `a` là **true**:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
```

Ở đây, vế trái `value instanceof String text` **true** là bằng chứng mẫu đã khớp, nên `text` an toàn ở toán hạng phải. Nếu vế trái false, `&&` ngắn mạch, hoàn toàn không gọi `text.isBlank()`.

Hai công thức phổ biến có cùng mục tiêu kiểm tra «phải là String và không rỗng trắng» nhưng dùng trong các luồng khác nhau:

| Mục đích | Biểu thức | Khi nào xử lý dữ liệu đã khớp? |
| --- | --- | --- |
| Đi tiếp khi hợp lệ | `value instanceof String text && !text.isBlank()` | Nhánh `true` của `if`. |
| Trả lỗi ngay khi không hợp lệ | `!(value instanceof String text) || text.isBlank()` | Sau guard clause kết thúc khi điều kiện `true`. |

Theo luật De Morgan, phủ định của `A && B` là `!A || !B`. Ở đây đặt `A = value instanceof String text` và `B = !text.isBlank()`. Phủ định `!A || !B` trở thành `!(value instanceof String text) || text.isBlank()`.

**Lưu ý về tên biến mẫu:** Dù hai điều kiện tương đương về giá trị boolean, vị trí mà `text` được phép sử dụng ở **then/else/đoạn mã sau `if`** còn phụ thuộc flow scoping và việc các nhánh có thể kết thúc bình thường hay không.

## 7. Phạm vi của biến trong các nhánh `if` và `else`

### 7.1. Khi OR trả `true`: không chắc mẫu đã khớp

```java
// CỐ Ý SAI ở dòng dùng text.
if (value instanceof String text || allowFallback) {
    System.out.println(text.length()); // LỖI biên dịch
}
```

Giả sử `allowFallback` là một biến boolean. Điều kiện OR có thể đúng vì:

- `value` là `String`: `text` đã match; hoặc
- `value` không phải `String` nhưng `allowFallback` là `true`: `text` **chưa match**.

Vì thế không thể dùng `text` trong nhánh `then` như một giá trị luôn tồn tại. Bản thân điều kiện `if (value instanceof String text || allowFallback)` có thể hợp lệ nếu **không sử dụng `text` ở nơi ngoài scope**; lỗi xuất hiện khi bạn cố dùng biến ở nhánh không được bảo đảm.

**Cách sửa khi cần phân luồng theo dữ liệu:**

```java
if (value instanceof String text) {
    System.out.println("string=" + text);
} else if (allowFallback) {
    System.out.println("fallback");
}
```

Ở nhánh đầu, `text` chắc chắn có giá trị. Nhánh sau không dùng `text`.

### 7.2. Khi OR ở mục 5 trả `false`: mẫu chắc chắn đã khớp

Xét:

```java
if (!(value instanceof String text) || text.isBlank()) {
    System.out.println("invalid");
} else {
    System.out.println("valid=" + text.strip());
}
```

Nhánh `else` chỉ chạy khi **toàn bộ OR là false**. Lúc đó:

1. `!(value instanceof String text)` phải là false → `instanceof` đã thành công.
2. `text.isBlank()` cũng false → chuỗi không chỉ chứa khoảng trắng.
3. `text` vì vậy được compiler xem là definitely matched trong `else`.

**Không khẳng định biến mẫu cũng có sẵn ở nhánh `then`.** Nhánh `then` có thể chạy khi mẫu không match; nếu truy cập `text` ở đó, lỗi biên dịch.

### 7.3. Ra khỏi một guard clause kết thúc bằng `return` hoặc `throw`

Mẫu thực tế rất hữu ích:

```java
static String normalize(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "invalid";
    }

    return text.strip();
}
```

Tại `return text.strip()` ở phía dưới:

- Muốn tới được câu lệnh này, chương trình phải **không** vào nhánh `if`.
- Điều kiện OR phải là **false**, nên `value instanceof String text` đã khớp.
- Nhánh `if` kết thúc bằng `return`, không thể đi xuyên từ nhánh lỗi xuống đoạn phía dưới.
- Theo JLS `6.3.2.2`, biến mẫu `text` được đưa vào scope ở các statement theo sau trong trường hợp này.

Tương tự với `throw new IllegalArgumentException(...)` trong nhánh lỗi. Nhưng nếu chỉ in log mà **không return/throw**, đường chạy từ nhánh lỗi vẫn đi tiếp; compiler không thể bảo đảm `text` đã khớp ở đoạn sau.

```java
// CỐ Ý SAI: nhánh if có thể hoàn thành bình thường.
if (!(value instanceof String text) || text.isBlank()) {
    System.out.println("invalid");
}
System.out.println(text.length()); // LỖI: text không chắc được match
```

## 8. Quy tắc khái quát «when true» và «when false»

Để hiểu các biểu thức Boolean phức tạp hơn, hãy ghi nhớ đúng các quy tắc trong JLS `6.3.1`:

| Cấu trúc | Điều kiện để dùng pattern variable ở vế phải | Điều có thể được bảo đảm cho toàn biểu thức |
| --- | --- | --- |
| `obj instanceof String s` | Đây là khai báo mẫu, chưa phải toán tử nhị phân | Giới thiệu `s` **when true**. |
| `!(obj instanceof String s)` | Dấu `!` đảo kết quả kiểm tra | Giới thiệu `s` **when false**. |
| `a && b` | Biến được giới thiệu từ `a` **when true** mới nằm trong scope ở `b` | Có thể giới thiệu biến **when true**; không có bảo đảm chung **when false**. |
| `a || b` | Biến được giới thiệu từ `a` **when false** mới nằm trong scope ở `b` | Có thể giới thiệu biến **when false**; không có bảo đảm chung **when true**. |
| `(a)` | Ngoặc đơn không đổi giá trị | Giữ cách giới thiệu biến khi true/false như `a`. |

**Mẹo phân tích:** Với `||`, hãy xét **vế trái false**. Với `&&`, hãy xét **vế trái true**. Với `!`, hãy **đảo true/false**. Sau đó mới xét `if`, `else` hoặc guard clause.

Từ khóa **introduced** ở đây là thuật ngữ phân tích phạm vi trong JLS, không có nghĩa chương trình tạo ra một biến mới ở mỗi lần gọi biểu thức. Biến mẫu chỉ được khởi tạo khi phép so khớp thực sự thành công.

### 8.1. Vế phải của OR có thể kiểm tra tiếp với biến vừa khớp

Ví dụ hợp lệ:

```java
static boolean invalid(Object value) {
    return !(value instanceof String text) || text.length() < 3;
}
```

Ở vế phải, `text` hợp lệ vì điều kiện đầu tiên false chứng minh `value` là `String`. Kết quả hàm có ý nghĩa:

- `true` nếu đầu vào **không phải chuỗi**; hoặc
- `true` nếu đầu vào là chuỗi **dài dưới 3**; còn lại `false`.

**Quan trọng:** Hàm có thể trả `true` do vế trái khi không khớp, nên không được suy ra biến `text` đã match chỉ vì kết quả `invalid(value)` là `true`. Trạng thái biến mẫu thuộc **ngữ cảnh biểu thức nơi nó khai báo**, không được chuyển qua ranh giới gọi phương thức như một biến local của caller.

## 9. Chương trình Java hoàn chỉnh và stdout chính xác

Lưu dưới tên **`PatternOrDemo.java`**:

```java
public class PatternOrDemo {
    static String normalize(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "INVALID";
        }
        return "VALID:" + text.strip();
    }

    static boolean notStringOrLong(Object value) {
        return !(value instanceof String text) || text.length() > 4;
    }

    static String positiveCheck(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "TEXT:" + text.strip();
        }
        return "OTHER";
    }

    static String withFallback(Object value, boolean fallback) {
        if (value instanceof String text || fallback) {
            // Không dùng text: fallback cũng có thể làm điều kiện true.
            return "ACCEPT";
        }
        return "REJECT";
    }

    static String withElse(Object value) {
        if (!(value instanceof String text) || text.length() < 3) {
            return "SHORT_OR_NOT_STRING";
        } else {
            return "LONG:" + text;
        }
    }

    public static void main(String[] args) {
        System.out.println("normalize-1=" + normalize(" Java "));
        System.out.println("normalize-2=" + normalize("   "));
        System.out.println("normalize-3=" + normalize(42));
        System.out.println("normalize-4=" + normalize(null));

        System.out.println("or-long-1=" + notStringOrLong("hello"));
        System.out.println("or-long-2=" + notStringOrLong("hi"));
        System.out.println("or-long-3=" + notStringOrLong(99));

        System.out.println("and-1=" + positiveCheck(" Java "));
        System.out.println("and-2=" + positiveCheck("   "));

        System.out.println("fallback-1=" + withFallback(42, true));
        System.out.println("fallback-2=" + withFallback(42, false));

        System.out.println("else-1=" + withElse("abcd"));
        System.out.println("else-2=" + withElse("ab"));
        System.out.println("else-3=" + withElse(42));
    }
}
```

Với JDK 17+ hỗ trợ `--release 17`, biên dịch và chạy:

```bash
javac --release 17 PatternOrDemo.java
java PatternOrDemo
```

**Stdout chính xác:**

```text
normalize-1=VALID:Java
normalize-2=INVALID
normalize-3=INVALID
normalize-4=INVALID
or-long-1=true
or-long-2=false
or-long-3=true
and-1=TEXT:Java
and-2=OTHER
fallback-1=ACCEPT
fallback-2=REJECT
else-1=LONG:abcd
else-2=SHORT_OR_NOT_STRING
else-3=SHORT_OR_NOT_STRING
```

**Giải thích từng nhóm kết quả:**

1. **`normalize`:** Với `" Java "`, `instanceof` thành công, vế phải của OR được phép gọi `text.isBlank()`; vì không blank nên nhánh lỗi không chạy, và `text.strip()` hợp lệ sau guard clause. Với `"   "`, nhánh phải trả `true`, nên `INVALID`. Với số nguyên hoặc `null`, vế trái phủ định `true` nên vế phải không được gọi, tránh truy cập biến chưa match.
2. **`notStringOrLong`:** Chuỗi `"hello"` có độ dài 5 nên trả true; `"hi"` dài 2 nên false. `99` không phải chuỗi nên trả true nhờ vế trái, không có thao tác trên `text`.
3. **`positiveCheck`:** `&&` đánh giá `text.isBlank()` chỉ khi `instanceof` true. Chuỗi trắng không đi vào nhánh hợp lệ.
4. **`withFallback`:** OR có thể được kích hoạt bởi boolean `fallback`, nên method không cố dùng biến `text` trong thân `if`.
5. **`withElse`:** Nhánh `else` chỉ có thể chạy nếu OR false; kết quả chứng minh đối tượng đã match `String` và có chiều dài ít nhất 3.

**Kiểm tra version:** Cú pháp `instanceof String text` chính thức từ Java 16; `String.isBlank()` và `String.strip()` là API Java 11+. Java 17 đủ khả năng biên dịch chương trình ở trên mà không bật preview. Không dùng compiler Java 14 preview làm ví dụ production hiện hành.

## 10. Đặt hai biến mẫu ở hai vế OR: vì sao không thể dùng như một biến chung?

### 10.1. Hai vế cùng khai báo **cùng tên** biến mẫu

```java
// CỐ Ý SAI (minh họa đặt trong một phương thức):
if ((first instanceof String text) ||
    (second instanceof String text)) {
    System.out.println("text");
}
```

Giả sử `first` và `second` có kiểu `Object`. JLS `6.3.1.2` có quy tắc chống **hai khai báo pattern variable trùng tên** được giới thiệu bởi các toán hạng OR trong trường hợp có thể gây mơ hồ. Khi toàn bộ OR trả true, một trong hai vế có thể là nguồn khớp mẫu; compiler không cho phép hai khai báo cùng tên `text` tạo ra một biến có danh tính mơ hồ.

**Không sửa bằng cách chỉ thêm ngoặc đơn:** Hai khai báo vẫn thuộc hai nhánh OR. Khi cần chọn dữ liệu từ nhiều nguồn, hãy viết các nhánh riêng, trả sớm hoặc chuyển kết quả thành một kiểu dữ liệu chung.

### 10.2. Hai vế khai báo tên khác nhau có tự cho dùng trong thân `if` không?

```java
// Các khai báo mẫu khác tên; bản thân điều kiện có thể hợp lệ.
if (value instanceof String s || value instanceof Integer n) {
    System.out.println("Supported type");
    // Không thể mặc định dùng s hay n ở đây:
    // nhánh còn lại có thể đã làm OR true.
}
```

Ngay cả khi điều kiện true, compiler **không bảo đảm cả `s` và `n` đã match**. Nếu cần dùng giá trị sau kiểm tra, hãy chuyển sang các nhánh độc lập:

```java
static String format(Object value) {
    if (value instanceof String s) {
        return "text:" + s;
    }
    if (value instanceof Integer n) {
        return "number:" + n;
    }
    return "other";
}
```

Đây là đoạn phương thức hợp lệ của Java 17+, có thể được đặt trong một class. Mỗi pattern variable có phạm vi rõ ràng ở nhánh đã khớp.

### 10.3. Một tên được khai báo ở chỗ khác thì sao?

Pattern variable không được tự do shadow một biến cục bộ đang nằm trong scope của nó. Ví dụ:

```java
// CỐ Ý SAI:
String text = "old";
if (value instanceof String text) {
    System.out.println(text);
}
```

Hai khai báo `text` mâu thuẫn trong phạm vi. Đổi tên pattern variable hoặc dùng tên đã khai báo theo một cách khác, thay vì dựa vào `||`/`&&` để «tái sử dụng» tên.

## 11. Các giới hạn liên quan dễ bị nhầm với quy tắc `||`

### 11.1. Đừng thay `||` bằng `|` để lách compiler

Java có cả `||` và `|` áp dụng với operand boolean:

- `||` **short-circuit**: vế phải chỉ chạy khi trái false.
- `|` boolean **đánh giá cả hai vế**.

`|` không cung cấp cơ sở flow scoping kiểu conditional OR để đảm bảo pattern variable được khớp ở vế phải. Mã như `!(value instanceof String s) | s.isBlank()` không phải giải pháp an toàn và không hợp lệ theo phạm vi pattern variable.

Nếu vế phải có thể gây ngoại lệ hoặc tốn tài nguyên, cơ chế ngắn mạch còn ảnh hưởng trực tiếp tới hành vi runtime; không chỉ là khác biệt về style.

### 11.2. Ngoặc đơn chỉ đổi nhóm, không đổi quy tắc matching

Hai dạng:

```java
!(value instanceof String s) || s.isBlank()
(!(value instanceof String s)) || s.isBlank()
```

là các biểu thức minh họa **nằm trong một ngữ cảnh Java hợp lệ**. Chúng có cùng ý nghĩa. Việc đặt thêm ngoặc quanh một biểu thức không thay đổi đặc tính **introduced when false** hay **introduced when true** của pattern variable theo JLS `6.3.1.7`.

Tuy nhiên **đặt lại nhóm các toán tử khác nhau** có thể thay đổi thứ tự/đường đánh giá. Luôn ưu tiên dấu ngoặc rõ ràng khi dùng `!` với `instanceof` và boolean operators, nhất là trong điều kiện validation.

### 11.3. `null` không match một type pattern `instanceof String s`

Với `value == null`, `value instanceof String s` là false. Vì thế:

```java
if (!(value instanceof String s) || s.isBlank()) {
    return "invalid";
}
```

trong một phương thức trả `String`, sẽ đi vào nhánh lỗi mà **không đánh giá `s.isBlank()`**. Trường hợp này an toàn đối với input null nhờ `instanceof` và tính ngắn mạch; không phải vì biến mẫu có giá trị `null`.

Một khi `instanceof String s` thành công, `s` tham chiếu tới một đối tượng `String`, không phải `null`. Nhưng các method do người dùng gọi từ đó vẫn có thể ném ngoại lệ khác, nên giới hạn an toàn chỉ nằm trong điều kiện kiểm tra này.

### 11.4. Biểu thức boolean gán vào biến không làm biến mẫu «lọt» ra ngoài

```java
// CỐ Ý SAI tại dòng cuối:
boolean invalid = !(value instanceof String s) || s.isBlank();
System.out.println(s.length());
```

Vế phải của phép OR trong dòng đầu có thể dùng `s` hợp lệ, nhưng việc lưu kết quả boolean trong `invalid` không bảo đảm `s` match ở câu lệnh sau. Muốn dùng dữ liệu đã match, khai thác trực tiếp flow scope trong `if`, `else` hoặc guard clause như các ví dụ trước.

### 11.5. Phân biệt scope với giá trị runtime

Mệnh đề `"biến s không nằm trong scope"` là kết luận **compile time**. Nó khác với các tình huống runtime như:

- Chuỗi có rỗng trắng hay không (`isBlank()`).
- Một hàm có ném ngoại lệ hay không.
- Toán hạng phải của OR có thực sự được chạy trong một lượt cụ thể không.

Không chữa lỗi scope bằng `try/catch` hoặc kiểm tra null thêm ở phía sau; compiler phải chứng minh biến tồn tại đúng phạm vi **trước khi** chương trình chạy.

## 12. Cách đọc và sửa lỗi compiler theo từng bước

Khi gặp lỗi tại một tên biến mẫu trong điều kiện chứa `||`, hãy lần lượt:

1. **Tìm nơi khai báo pattern variable**, ví dụ `obj instanceof String s`. Có đúng tên và đúng kiểu không?
2. **Xác định dấu phủ định `!`** và dấu ngoặc: biểu thức bên trái đưa `s` vào **when true** hay **when false**?
3. **Xác định toán tử ngắn mạch**: Với `||`, vế phải chạy khi trái **false**. Với `&&`, vế phải chạy khi trái **true**.
4. **Xét đường đi đến chỗ dùng biến**: Có trường hợp nào tới đó mà `instanceof` không match không? Nếu có, biến không hợp lệ ở đó.
5. **Kiểm tra kết quả của toàn biểu thức**: Sau `a || b`, nhánh true thường không cho bảo đảm pattern variable; nhánh false có thể cho bảo đảm theo JLS.
6. **Xét control flow của `if`**: Guard clause có `return`/`throw` nên nhánh lỗi không đi tiếp hay chỉ in log rồi tiếp tục?
7. **Rà soát tên khai báo trùng nhau**: Hai pattern cùng tên trên các nhánh OR không tạo một biến chung.
8. **Biên dịch bằng release chuẩn hiện hành**, chẳng hạn `javac --release 17`, rồi test với input String hợp lệ, String blank, kiểu khác và `null`.

### 12.1. Bảng lỗi và cách sửa

| Mã hoặc ý định | Vấn đề | Cách sửa |
| --- | --- | --- |
| `obj instanceof String s || s.isBlank()` | Khi trái false, `s` chưa match; RHS không dùng được. | `!(obj instanceof String s) || s.isBlank()` cho luồng reject, hoặc dùng `&&` cho luồng accept. |
| `if (obj instanceof String s || allow) use(s);` | OR có thể true bởi `allow` mà không match. | Tách `if (obj instanceof String s)` và nhánh fallback. |
| `if (!(obj instanceof String s) || s.isBlank()) log(); use(s);` | Nhánh lỗi vẫn đi tiếp; không đảm bảo `s` sau `if`. | Nhánh lỗi phải `return`/`throw`, hoặc dùng `else` để truy cập `s`. |
| `(x instanceof String s) || (y instanceof String s)` | Khai báo cùng tên ở hai nhánh OR gây mơ hồ. | Tách nhánh, dùng tên riêng và xử lý từng match. |
| `!(obj instanceof String s) | s.isBlank()` | `|` không short-circuit và không tạo scope đúng cho RHS. | Dùng `||` khi cần ngắn mạch và flow typing. |
| `boolean bad = !(obj instanceof String s) || s.isBlank(); use(s);` | Không thể suy luận kết quả match sau phép gán boolean. | Sử dụng `s` tại vị trí compiler chứng minh đã match. |
| Java 14 preview examples trong code production mới | Chế độ preview cũ không phải baseline ổn định. | Dùng cú pháp chuẩn Java 16+ và compiler/runtime còn hỗ trợ. |

## 13. Bài tập tự kiểm tra

### Bài 1 — Dòng nào không biên dịch?

```java
// Các biểu thức độc lập trong một phương thức có biến Object obj.
boolean a = obj instanceof String s && s.length() > 2;
boolean b = !(obj instanceof String t) || t.length() < 3;
boolean c = obj instanceof String u || u.length() > 2;
```

**Đáp án:** `a` và `b` hợp lệ; `c` sai vì `u` ở RHS của `||` chỉ được đánh giá nếu `instanceof` false, tức chưa match. Với `a`, RHS chạy khi match; với `b`, RHS chạy khi phép phủ định false, nghĩa là match.

### Bài 2 — Phủ định làm thay đổi điều gì?

```java
if (!(obj instanceof String s) || s.isBlank()) {
    return;
}
System.out.println(s.strip());
```

Đoạn này nằm trong phương thức có kiểu trả về `void`. **Đáp án:** Hợp lệ. Khi tới `println`, nhánh lỗi đã thoát; điều kiện OR false chứng minh `obj` đã match String và `s` không blank. Compiler cho `s` nằm trong scope sau `if`.

### Bài 3 — Phân tích đường đi của `null`

```java
boolean invalid = !(obj instanceof String s) || s.length() == 0;
```

**Đáp án:** Nếu `obj` là `null`, `instanceof` false, vế phủ định true; `||` không chạy `s.length()` và `invalid == true`. Không có lỗi dereference ở nhánh đó.

### Bài 4 — Có được dùng biến mẫu trong nhánh then không?

```java
boolean override = true;
if (obj instanceof String s || override) {
    System.out.println(s);
}
```

**Đáp án:** Không. Điều kiện có thể true vì `override` mà `obj` không match String. Compiler không coi `s` definitely matched ở nhánh then. Sửa bằng hai nhánh riêng.

### Bài 5 — Đặt biến mẫu ở vế phải OR

```java
boolean forced = false;
if (forced || obj instanceof String s) {
    // Có thể dùng s trong nhánh này không?
}
```

**Đáp án:** Không thể mặc định dùng `s` trong nhánh then. Nếu `forced` true, toán hạng phải không đánh giá, mẫu không match. Điều kiện OR vẫn hợp lệ nếu nhánh then không yêu cầu `s`.

### Bài 6 — Vì sao không nên dùng cùng tên trong cả hai nhánh?

```java
// CỐ Ý SAI:
if (a instanceof String s || b instanceof String s) {
    System.out.println("match");
}
```

**Đáp án:** Hai pattern declarations trùng tên ở các nhánh OR, dẫn tới trường hợp không phân biệt được declaration nào sinh ra một biến `s` khi điều kiện true. JLS `6.3.1.2` có điều kiện cấm; dùng hai nhánh `if` riêng nếu cần xử lý dữ liệu.

### Bài 7 — Dự đoán stdout của guard clause

```java
static String check(Object value) {
    if (!(value instanceof String s) || s.length() < 3) {
        return "NO";
    }
    return "YES:" + s.length();
}
```

**Đáp án:** `check("hi")` trả `NO`; `check("Java")` trả `YES:4`; `check(10)` trả `NO`. Luồng sau guard clause chỉ có thể đến khi mẫu đã match.

## 14. Nguồn chính thức còn hiệu lực

1. [JLS Java SE 25 — `6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3): định nghĩa flow scoping, introduced when true/false.
2. [JLS `6.3.1.2 Conditional-Or Operator `||`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3.1.2): quy tắc pattern variable ở RHS OR, khi toàn biểu thức false và các trường hợp khai báo tên trùng.
3. [JLS `6.3.1.1 Conditional-And Operator `&&`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3.1.1): so sánh luồng match ở RHS của AND.
4. [JLS `6.3.1.3 Logical Complement `!`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3.1.3): đảo introduced when true/false.
5. [JLS `6.3.1.5 Pattern Match Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3.1.5): `instanceof` giới thiệu pattern variable khi true.
6. [JLS `6.3.2.2 `if` Statements](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3.2.2): scope trong then/else và sau guard clause.
7. [JLS `15.24 Conditional-Or Operator](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.24): ngữ nghĩa short-circuit của `||`.
8. [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): mốc tính năng trở thành chuẩn ở Java 16.
9. [Java SE 25 Javadoc — `String.isBlank`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#isBlank()): API được dùng trong ví dụ và trạng thái ổn định.

**Ghi nhớ:** Với `a || b`, **chỉ khi a false mới chạy b**. Bởi thế, biến mẫu dùng trong `b` phải được chứng minh đã khớp ở tình huống `a false`. `obj instanceof String s` giới thiệu `s` khi **true** nên `|| s...` là sai; `!(obj instanceof String s)` giới thiệu `s` khi **false** nên `|| s...` là đúng. Khi dùng biến sau toàn bộ `if`, vẫn phải kiểm tra **đường điều khiển** để biết mọi trường hợp không khớp đã bị loại bỏ hay chưa.