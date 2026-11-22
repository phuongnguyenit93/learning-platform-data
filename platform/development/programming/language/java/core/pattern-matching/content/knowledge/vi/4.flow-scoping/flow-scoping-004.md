# Phạm vi biến với toán tử `||` trong Java Pattern Matching

## 1. Vấn đề: tại sao `instanceof` có biến pattern nhưng `||` vẫn có thể gây lỗi?

Từ Java 16, `instanceof` có thể nhận một **type pattern**, ví dụ `value instanceof String text`. Khi phép kiểm tra thành công, nó tạo biến `text` có kiểu `String` để dùng ở những vị trí mà trình biên dịch biết chắc phép khớp đã thành công.

Tuy nhiên, biến này **không có phạm vi giống một biến cục bộ thông thường khai báo trước câu lệnh `if`**. Phạm vi của nó phụ thuộc vào đường đi của chương trình (*flow scoping*). Toán tử OR ngắn mạch `||` là trường hợp dễ nhầm vì điều kiện tổng thể có thể đúng dù mẫu không khớp.

Xét đoạn **không biên dịch**:

```java
// ĐOẠN SAI — không dùng làm ví dụ chạy:
// Object value = "Java";
// boolean fallback = true;
// if (value instanceof String text || fallback) {
//     System.out.println(text.length()); // Lỗi: text có thể chưa khớp.
// }
```

Nếu `value` là số nguyên còn `fallback` là `true`, cả điều kiện `if` vẫn đúng, nhưng `value instanceof String text` đã thất bại. Java không thể cho phép dùng `text` vì không có giá trị `String` nào được ràng buộc.

**Câu hỏi cốt lõi:** Tại vị trí sử dụng biến pattern, **mọi đường đi tới đó** có bảo đảm mẫu đã khớp hay không? Chỉ khi câu trả lời là “có”, biến pattern mới hợp lệ tại vị trí đó.

Bài này tập trung vào cách `||` ảnh hưởng đến phạm vi biến pattern từ `instanceof`, đặc biệt là cách kết hợp **phủ định `!`**, **điều kiện loại trừ sớm** và **truy cập biến sau `if`**. Các ví dụ chạy được trên **Java 17 trở lên**, không cần bật tính năng preview.

## 2. Hai quy tắc nền tảng: OR ngắn mạch và flow scoping

### 2.1. `||` đánh giá từ trái sang phải

Với biểu thức:

```java
left || right
```

Java làm như sau:

1. Tính `left`.
2. Nếu `left == true`, **không tính `right`**; cả biểu thức là `true`.
3. Nếu `left == false`, mới tính `right` để quyết định kết quả.

Bảng chân trị:

| `left` | `right` có được đánh giá? | Kết quả `left || right` |
| --- | --- | --- |
| `true` | Không | `true` |
| `false` | Có, kết quả `true` | `true` |
| `false` | Có, kết quả `false` | `false` |

Hệ quả quan trọng: nếu **cả biểu thức `left || right` là `false`**, ta chắc chắn **cả hai vế đều đã cho kết quả `false`**. Còn nếu cả biểu thức là `true`, ta không thể kết luận riêng vế nào đã đúng.

### 2.2. Biến pattern chỉ dùng khi “đã khớp chắc chắn”

Ví dụ cơ bản:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length()); // Hợp lệ: text đã khớp.
}
```

`value instanceof String text` trả về `true` khi giá trị runtime là `String`; lúc đó `text` tham chiếu đến chính đối tượng `String` đã kiểm tra. Nếu giá trị không phải `String` hoặc là `null`, kết quả là `false` và không thể dùng `text` ở đường đi không khớp.

Đối với biểu thức phức tạp, Java xét **biến được giới thiệu khi biểu thức đúng hay sai** (*introduced when true/false*) để xác định phạm vi. Phép phủ định `!` đảo hướng đó: nếu `!(value instanceof String text)` là `false`, ta biết phép `instanceof` bên trong là `true` và `text` đã khớp.

Quy tắc này giải thích vì sao cùng toán tử `||` có đoạn sai và đoạn đúng.

## 3. Trường hợp sai: pattern dương ở vế trái của `||`

Xem ví dụ:

```java
// KHÔNG HỢP LỆ:
// if (value instanceof String text || text.isBlank()) {
//     System.out.println("OK");
// }
```

Vế phải `text.isBlank()` chỉ được đánh giá khi vế trái `value instanceof String text` là **`false`**. Chính khi đó biến `text` **chưa khớp**, nên trình biên dịch từ chối truy cập `text` ở vế phải.

Đây là điểm ngược với `&&`:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip()); // Hợp lệ.
}
```

Với `&&`, vế phải chỉ chạy khi phép `instanceof` là `true`, nên `text` đã khớp và có thể gọi `isBlank()`.

### Cũng không được dùng biến trong thân `if` nếu OR có đường đi thay thế

Ngay cả khi vế phải **không hề nhắc đến** biến pattern, phép `||` vẫn khiến biến không được bảo đảm trong nhánh `if`:

```java
// KHÔNG HỢP LỆ:
// if (value instanceof String text || useDefault) {
//     System.out.println(text.length());
// }
```

Có hai cách để nhánh `if` được chạy: giá trị là `String`, **hoặc** `useDefault` là `true`. Ở cách thứ hai, pattern có thể đã thất bại; Java không cho phép truy cập `text`.

Cần phân biệt:

- `||` là phép OR về **giá trị boolean**.
- Việc **có biến pattern để dùng** là điều kiện mạnh hơn: phải chứng minh mẫu đã khớp trên mọi đường đi đến chỗ sử dụng.

Một điều kiện trả về `true` chưa đủ để chứng minh rằng một type pattern cụ thể đã khớp.

## 4. Trường hợp đúng: phủ định pattern trước `||`

Bây giờ đổi điều kiện sang hướng **phát hiện dữ liệu không hợp lệ**:

```java
if (!(value instanceof String text) || text.isBlank()) {
    System.out.println("Không phải chuỗi hợp lệ");
}
```

**Đoạn này hợp lệ trong Java 17.** Lý do:

1. Nếu `value` không phải `String` (kể cả `null`), `value instanceof String text` là `false`, nên `!(...)` là `true`. Java **bỏ qua** vế phải `text.isBlank()`; không truy cập biến chưa khớp.
2. Nếu `value` là `String`, `instanceof` khớp và tạo biến `text`; phủ định `!(...)` là `false`. Java cần tính vế phải, và lúc này `text` **đã chắc chắn khớp**, nên `text.isBlank()` hợp lệ.

Có thể đọc điều kiện theo tiếng Việt:

> “Nếu đầu vào **không phải chuỗi**, hoặc **đúng là chuỗi nhưng chỉ có khoảng trắng**, hãy xử lý lỗi.”

Dấu `!` là điểm then chốt. Nó biến điều kiện ở vế trái thành phép kiểm tra **phủ định**, để **vế trái sai** đồng nghĩa với **pattern đã khớp**.

### Bảng theo dõi một số đầu vào

Với biểu thức `!(value instanceof String text) || text.isBlank()`:

| `value` | `instanceof String` | `!(...)` | Có chạy `text.isBlank()`? | Kết quả toàn biểu thức |
| --- | --- | --- | --- | --- |
| `"Java"` | `true` | `false` | Có, `false` | `false` |
| `"   "` | `true` | `false` | Có, `true` | `true` |
| `42` | `false` | `true` | Không | `true` |
| `null` | `false` | `true` | Không | `true` |

Đây còn là một **cách tránh lỗi truy cập `null`**: khi `value == null`, vế phải không được chạy. Trong Java, riêng phép `null instanceof String text` trả về `false`, không ném `NullPointerException`.

### So sánh hai cách viết tương đương về ý nghĩa

**Cách 1 — giữ trường hợp hợp lệ:**

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
```

**Cách 2 — loại trường hợp không hợp lệ:**

```java
if (!(value instanceof String text) || text.isBlank()) {
    System.out.println("Giá trị không hợp lệ");
} else {
    System.out.println(text.strip());
}
```

Trong cách 2, nhánh `else` chỉ chạy nếu toàn bộ điều kiện OR là **`false`**. Khi đó:
- `!(value instanceof String text)` là `false`, nên pattern đã khớp.
- `text.isBlank()` là `false`, nên chuỗi không phải chuỗi trắng.

Vì vậy biến `text` dùng được trong nhánh `else`. Hai đoạn trên thể hiện cùng phép nhận diện dữ liệu hợp lệ; điểm khác là cách tổ chức nhánh xử lý.

## 5. Guard clause: dùng biến pattern sau phép `||`

Một ứng dụng rất hữu ích của `||` là **điều kiện loại trừ sớm** (*guard clause*). Ta xử lý lỗi trước, `return` hoặc `throw`, rồi tiếp tục với đường đi đã được bảo đảm hợp lệ:

```java
static String normalize(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "INVALID";
    }

    return text.strip(); // HỢP LỆ: text chắc chắn đã khớp.
}
```

Tại sao `text` còn dùng được **sau** câu lệnh `if`?

- Nếu điều kiện OR là `true`, hàm đã `return`, nên không còn đường đi đến `text.strip()`.
- Muốn đi đến `text.strip()`, điều kiện OR **phải là `false`**.
- Điều kiện OR `false` bắt buộc `!(value instanceof String text)` là `false`; tức pattern đã khớp và `text` có kiểu `String`.

Đây là một ví dụ điển hình cho khái niệm *flow scoping*: phạm vi không chỉ phụ thuộc vào cặp ngoặc nhọn của `if`, mà còn phụ thuộc nhánh nào **có thể tiếp tục thực thi**.

### Nếu nhánh `if` không thoát sớm thì sao?

Đoạn sau **không hợp lệ**:

```java
// KHÔNG BIÊN DỊCH:
// if (!(value instanceof String text) || text.isBlank()) {
//     System.out.println("Input không hợp lệ");
// }
// System.out.println(text.strip()); // Có thể đi tới đây sau nhánh lỗi.
```

Do nhánh lỗi chỉ in thông báo rồi đi tiếp, chương trình vẫn có đường đi tới `text.strip()` khi `value` không khớp `String`. Không thể coi `text` là đã khớp.

**Sửa bằng `return` hoặc `throw`:**

```java
static String requireText(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Expected non-blank String");
    }
    return text.strip();
}
```

Một giải pháp khác là đặt logic dùng `text` trong nhánh `else` đã được bảo đảm, như ở phần trước.

## 6. Khi cần kiểm tra hai pattern: điều kiện OR phủ định

Trong thực tế, có thể cần bảo đảm **hai đầu vào đồng thời** có đúng kiểu trước khi xử lý. Với guard clause, ta viết `||` để từ chối nếu **một trong hai** sai kiểu:

```java
static String describePair(Object first, Object second) {
    if (!(first instanceof String name)
            || !(second instanceof Integer count)) {
        return "INVALID_PAIR";
    }

    return name.strip() + " x " + count;
}
```

Đoạn trên **hợp lệ** trong Java 17:

1. Nếu `first` không phải `String`, vế trái là `true`, vế phải không được tính, phương thức trả về `"INVALID_PAIR"`.
2. Nếu `first` là `String`, biến `name` đã khớp. Vế phải kiểm tra `second`.
3. Nếu `second` không phải `Integer`, phương thức trả về lỗi.
4. Chỉ khi **cả hai** đối tượng đúng kiểu, toàn bộ điều kiện OR mới là `false`, nên nhánh lỗi không chạy. Sau `if`, cả `name` và `count` đã khớp.

Lưu ý quan trọng: trong thân nhánh `if` xử lý lỗi, không được tùy tiện dùng `name` hoặc `count`. Nhánh đó có thể được chọn vì **bất kỳ** phép kiểm tra nào thất bại.

### So sánh với điều kiện `&&` theo hướng tích cực

Hai kiểu viết dưới đây có cùng mục tiêu kiểm tra:

```java
if (first instanceof String name
        && second instanceof Integer count) {
    System.out.println(name + ": " + count);
}
```

Và:

```java
if (!(first instanceof String name)
        || !(second instanceof Integer count)) {
    return;
}
System.out.println(name + ": " + count);
```

Đoạn thứ hai phải được đặt **trong thân một phương thức trả về `void`**, vì nó dùng `return;`. Đó là đoạn minh họa, không phải một chương trình độc lập.

Có thể hiểu hai điều kiện bằng luật De Morgan:

```text
A && B             : cả A và B đều đúng
!(A && B)          : ít nhất một điều kiện sai
!A || !B           : tương đương với !(A && B)
```

Với biến pattern, ngoài tương đương logic, bạn còn phải xét **nhánh nào đảm bảo mẫu đã khớp** và câu lệnh có **thoát sớm** hay không.

## 7. Ví dụ Java 17 hoàn chỉnh: OR, phủ định và phạm vi biến

Tạo tệp **`OrFlowScopingDemo.java`**:

```java
public class OrFlowScopingDemo {

    static String normalize(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "INVALID";
        }
        return "OK:" + text.strip();
    }

    static String pair(Object first, Object second) {
        if (!(first instanceof String name)
                || !(second instanceof Integer count)) {
            return "INVALID_PAIR";
        }
        return name.strip() + " x " + count;
    }

    static boolean invalidText(Object value) {
        return !(value instanceof String text) || text.isBlank();
    }

    static String classify(Object value) {
        if (value instanceof String text) {
            return "TEXT:" + text;
        }
        if (value instanceof Integer number) {
            return "INT:" + number;
        }
        return "OTHER";
    }

    public static void main(String[] args) {
        System.out.println(normalize("  Java  "));
        System.out.println(normalize("   "));
        System.out.println(normalize(5));
        System.out.println(normalize(null));

        System.out.println(pair("  An  ", 3));
        System.out.println(pair("  An  ", "3"));

        System.out.println(invalidText("x"));
        System.out.println(invalidText(""));
        System.out.println(invalidText(null));

        System.out.println(classify("ok"));
        System.out.println(classify(12));
        System.out.println(classify(null));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 OrFlowScopingDemo.java
java OrFlowScopingDemo
```

Kết quả:

```text
OK:Java
INVALID
INVALID
INVALID
An x 3
INVALID_PAIR
false
true
true
TEXT:ok
INT:12
OTHER
```

**Giải thích từng phương thức:**

- `normalize`: viết điều kiện lỗi bằng `!(... instanceof String text) || text.isBlank()`. Khi không lỗi, `text` dùng được sau `if` vì nhánh lỗi đã `return`.
- `pair`: kết hợp hai phép thử phủ định bằng `||`. Muốn vượt qua guard clause, cả `name` lẫn `count` đều phải khớp.
- `invalidText`: dùng biểu thức OR trực tiếp làm kết quả boolean. Biến `text` chỉ cần cho vế phải, và ở đó luôn chắc chắn đã khớp.
- `classify`: hai kiểu cần xử lý khác nhau được tách thành hai `if` riêng để mỗi biến pattern có phạm vi rõ ràng. Không cố gộp các pattern dương bằng `||` rồi sử dụng một biến trong cùng nhánh.

Đặc biệt, `normalize(null)` trả về `"INVALID"` an toàn: `null instanceof String text` là `false`, phủ định thành `true`, nên Java bỏ qua `text.isBlank()`.

## 8. Những lỗi phổ biến liên quan đến `||`

### Lỗi 1: hiểu “điều kiện OR đúng” thành “pattern đã khớp”

```java
// KHÔNG HỢP LỆ:
// if (value instanceof String text || allowUnknown) {
//     System.out.println(text.toUpperCase());
// }
```

Khi `allowUnknown` đúng, chương trình có thể vào `if` ngay cả khi `value` không phải chuỗi. **Cách sửa:** tách nhánh dùng `text` khỏi nhánh dùng giá trị dự phòng:

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
} else if (allowUnknown) {
    System.out.println("UNKNOWN");
}
```

Đoạn sửa giả sử `value` và `allowUnknown` đã được khai báo phù hợp trong phạm vi chứa `if`.

### Lỗi 2: quên phủ định `!` khi muốn loại dữ liệu sai kiểu

```java
// KHÔNG BIÊN DỊCH:
// if (value instanceof String text || text.isBlank()) {
//     return "INVALID";
// }
```

**Cách sửa:**

```java
if (!(value instanceof String text) || text.isBlank()) {
    return "INVALID";
}
```

Đoạn sửa cần nằm trong phương thức có kiểu trả về `String`. Phủ định làm cho việc đi tới vế phải đồng nghĩa với pattern đã khớp.

### Lỗi 3: dùng biến sau `if` khi nhánh lỗi vẫn đi tiếp

```java
// KHÔNG HỢP LỆ:
// if (!(value instanceof String text) || text.isBlank()) {
//     System.out.println("INVALID");
// }
// System.out.println(text.length());
```

**Cách sửa:** dùng `return`, `throw`, hoặc đặt câu lệnh dùng `text` trong nhánh `else` tương ứng.

### Lỗi 4: nghĩ `||` luôn không thể đi cùng biến pattern

Nhận định này **sai**: có thể dùng biến pattern trong vế phải nếu điều kiện vế trái **sai** đã chứng minh pattern khớp. Ví dụ hợp lệ:

```java
if (!(value instanceof String text) || text.length() == 0) {
    System.out.println("Không có chuỗi hợp lệ");
}
```

`text.length()` chỉ chạy sau khi giá trị đã khớp `String`. Tên biến pattern không quyết định tính hợp lệ; **hướng đúng/sai của phép khớp và thứ tự đánh giá** mới quyết định.

### Lỗi 5: quên tính ngắn mạch khi gọi phương thức

`||` không đánh giá vế phải khi vế trái đúng. Điều này giúp tránh gọi phương thức trên biến chưa khớp trong mẫu phủ định. Nhưng nếu vế phải chứa hàm có tác dụng phụ (ghi trạng thái, gửi yêu cầu, tăng bộ đếm), hàm đó có thể bị **bỏ qua**. Chỉ đặt tác dụng phụ trong điều kiện khi bạn thật sự cần hành vi đó.

## 9. Quy tắc kiểm tra nhanh khi đọc một điều kiện phức tạp

Hãy tự hỏi theo thứ tự:

1. Pattern là `value instanceof T variable` hay đã bị phủ định thành `!(value instanceof T variable)`?
2. Nếu `||` cần đánh giá vế phải, **vế trái chắc chắn đang là `false`**. Điều đó bảo đảm biến pattern khớp hay không?
3. Nếu đang ở nhánh `if` của toàn bộ OR, có đường nào khiến OR đúng **mà pattern không khớp** không?
4. Nếu dùng biến sau `if`, các nhánh lỗi có thoát bằng `return`, `throw` hay không?
5. Nếu có nhiều type pattern, liệu tại nơi dùng từng biến, **tất cả điều kiện tương ứng đã khớp** hay chưa?

Bảng đối chiếu:

| Cách viết | Dùng biến pattern ở đâu? | Kết luận |
| --- | --- | --- |
| `x instanceof String s && !s.isBlank()` | Vế phải và nhánh `if` khi biểu thức đúng | Hợp lệ |
| `x instanceof String s || s.isBlank()` | Vế phải cố dùng `s` | Lỗi biên dịch |
| `x instanceof String s || fallback` | Không bảo đảm `s` trong nhánh `if` | Không dùng `s` tại đó |
| `!(x instanceof String s) || s.isBlank()` | Vế phải | Hợp lệ |
| `if (!(x instanceof String s) || s.isBlank()) return; ... s ...` | Sau `if` trong phương thức `void` khi điều kiện lỗi đã thoát | Hợp lệ |
| `if (!(x instanceof String s) || s.isBlank()) { ... } else { ... s ... }` | Nhánh `else` | Hợp lệ |
| `if (!(x instanceof String s) || s.isBlank()) { log(); } ... s ...` | Sau `if` trong khi nhánh lỗi còn đi tiếp | Lỗi biên dịch |

Các dấu `...` trong bảng là ký hiệu mô tả cấu trúc luồng điều khiển, không phải mã Java để sao chép nguyên xi.

## 10. Bài tập và đáp án

### Bài 1: đoạn nào biên dịch?

Giả sử `Object value` đã được khai báo:

**A.**

```java
if (value instanceof String s || s.length() > 2) {
    System.out.println("A");
}
```

**B.**

```java
if (!(value instanceof String s) || s.length() < 3) {
    System.out.println("B");
}
```

**C.**

```java
if (value instanceof String s && s.length() > 2) {
    System.out.println(s);
}
```

**Đáp án:** A không biên dịch vì vế phải được đánh giá khi type pattern `s` thất bại. B biên dịch vì vế phải chỉ chạy nếu phép `instanceof` bên trong đã khớp. C biên dịch vì vế phải của `&&` chỉ chạy khi type pattern đã khớp.

### Bài 2: dự đoán kết quả hàm

```java
static String check(Object value) {
    if (!(value instanceof String s) || s.isBlank()) {
        return "BAD";
    }
    return "GOOD:" + s.strip();
}
```

- `check(" Hi ")` → `"GOOD:Hi"`
- `check("   ")` → `"BAD"`
- `check(10)` → `"BAD"`
- `check(null)` → `"BAD"`

Giải thích được cả **khi nào vế phải được thực thi** và **vì sao `s` dùng được sau `if`** mới là hiểu đầy đủ vấn đề.

### Bài 3: sửa code để vừa kiểm tra kiểu vừa tránh lỗi

Đoạn ban đầu không biên dịch:

```java
// KHÔNG BIÊN DỊCH:
// if (obj instanceof String name || obj instanceof Integer number) {
//     System.out.println(name + " / " + number);
// }
```

Ở một thời điểm, `obj` không được bảo đảm đồng thời là cả `String` và `Integer`. Thay vì cố dùng `name` và `number` trong một nhánh, hãy xử lý từng khả năng:

```java
if (obj instanceof String name) {
    System.out.println("Name: " + name);
} else if (obj instanceof Integer number) {
    System.out.println("Number: " + number);
} else {
    System.out.println("Other");
}
```

Đoạn sửa chỉ yêu cầu `Object obj` có sẵn trong phạm vi. Mỗi biến pattern được dùng ở nhánh mà phép kiểm tra tương ứng đã khớp.

## 11. Kết luận vận dụng

Toán tử `||` **không tự làm mất** tính năng pattern matching. Nó chỉ buộc ta xét đúng luồng điều khiển:

- Với `value instanceof String s || ...`, vế phải được xét khi phép khớp `String` **thất bại**, nên không được dùng `s` ở vế phải; nhánh đúng của cả phép OR cũng không bảo đảm `s` đã khớp.
- Với `!(value instanceof String s) || s.isBlank()`, vế phải chỉ được xét khi phép khớp `String` **thành công**, nên `s` hợp lệ ở đó.
- Nếu điều kiện OR phủ định dùng để loại trừ sớm bằng `return` hoặc `throw`, phần mã chạy tiếp có thể dùng `s` vì mọi đường đi còn lại đều đã chứng minh mẫu khớp.

**Nguyên tắc ghi nhớ:** Với `||`, muốn dùng biến pattern ở vế phải, hãy hỏi: “Khi vế trái **sai**, biến này đã chắc chắn được ràng buộc chưa?” Muốn dùng biến sau câu lệnh `if`, hãy kiểm tra mọi đường đi chưa thoát khỏi phương thức. Đó là cốt lõi của **flow scoping** trong bài toán này.

## Tài liệu tham khảo

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java SE 17 Language Specification, §6.3 — Scope of Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3)
- [Java SE 17 Language Specification, §15.23–15.24 — Conditional-AND and Conditional-OR Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.24)
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
