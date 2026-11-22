# Không có phép cast trực tiếp giữa kiểu số và boolean trong Java

## 1. Vấn đề cần hiểu

Khi học **chuyển kiểu (type conversion)** trong Java Core — Numbers, ta thường thấy `int` đổi sang `long`, `double` đổi sang `float`, hoặc `char` tham gia phép tính số. Nhưng Java có một ranh giới rõ ràng: **`boolean` không thuộc nhóm kiểu số và không có phép cast trực tiếp hợp lệ giữa `boolean` và các kiểu số nguyên thủy**.

Cụ thể, những ý tưởng quen thuộc trong một số ngôn ngữ khác **không hợp lệ trong Java**:

```java
// CÁC DÒNG SAU CỐ Ý SAI, KHÔNG BIÊN DỊCH:
boolean a = (boolean) 1;
boolean b = (boolean) 0;
int c = (int) true;
double d = (double) false;
boolean e = 42;
int f = true;
```

`0` không tự động là `false` và `1` không tự động là `true` trong ngôn ngữ Java. Nếu dữ liệu số mã hóa ý nghĩa đúng/sai, **chính chương trình phải định nghĩa cách chuyển ý nghĩa đó** bằng phép so sánh, toán tử điều kiện, xác thực hoặc một phương thức có tên.

Sau bài này, bạn sẽ:

- Phân biệt các kiểu số `byte`, `short`, `char`, `int`, `long`, `float`, `double` với `boolean`.
- Hiểu tại sao phép gán, cast, toán tử điều kiện và lời gọi phương thức cần kiểu `boolean` thực sự.
- Chuyển **ý nghĩa** “có/không”, “bật/tắt” từ dữ liệu số sang `boolean` bằng quy tắc rõ ràng.
- Mã hóa `boolean` thành `0/1` theo hợp đồng giao tiếp, không nhầm với cast.
- Xử lý các trường hợp biên của số thực, `NaN`, `Infinity`, chuỗi `"true"`/`"1"` và bitmask.
- Đọc đúng lỗi biên dịch, tránh cast lòng vòng qua wrapper hoặc `Object`.

Các ví dụ đầy đủ dùng **Java 17+**.

## 2. Hệ kiểu primitive: số và boolean là hai nhóm riêng

Java có tám kiểu primitive:

| Nhóm | Kiểu | Ghi chú |
| --- | --- | --- |
| Số nguyên | `byte`, `short`, `int`, `long` | Giá trị số nguyên có dấu |
| Liên quan số nguyên/UTF-16 | `char` | Đơn vị mã UTF-16 16 bit không dấu, có thể tham gia một số phép số học |
| Số thực | `float`, `double` | Số chấm động nhị phân |
| Logic | `boolean` | Chỉ có hai giá trị ngôn ngữ: `true` và `false` |

Trong các **numeric conversion**, Java cho phép nhiều chuyển đổi giữa các kiểu số với nhau, chẳng hạn `int → long`, `int → double`, `double → int` hoặc `char → int`, có thể là chuyển rộng hoặc chuyển hẹp tùy loại.

Nhưng `boolean` không là kiểu số, không có quy tắc `numeric promotion` như `int`, và không tham gia các **widening/narrowing primitive numeric conversions**. Theo đặc tả ngôn ngữ, không có cast primitive trực tiếp hợp lệ từ kiểu số sang `boolean` hay ngược lại.

Điều này vẫn đúng cho cả:

- `byte`, `short`, `int`, `long`;
- `char`, dù giá trị của nó có thể đọc được dưới dạng số nguyên;
- `float`, `double`;
- Các literal số như `0`, `1`, `0.0`, `1.0F`;
- Các giá trị âm và dương: Java không có cú pháp cho phép dùng `-1` làm `true` như một điều kiện.

Cần nhớ rằng **giá trị 0/1 dùng để mã hóa boolean trong dữ liệu** là một thỏa thuận ứng dụng, khác với **quy tắc chuyển kiểu của ngôn ngữ Java**.

## 3. Tại sao `(boolean) 1` không hoạt động?

Hãy xét:

```java
int count = 1;
// boolean hasItems = (boolean) count; // LỖI BIÊN DỊCH
```

Khi trình biên dịch gặp `(boolean) count`, nó kiểm tra có phép chuyển kiểu được JLS cho phép giữa kiểu `int` và kiểu đích `boolean` hay không. **Không có** phép chuyển đổi đó, nên mã không hợp lệ. Đây là lỗi **thời điểm biên dịch**, không phải “chạy thử mới ra `false` hay `true`”.

Tương tự:

```java
boolean enabled = true;
// int n = (int) enabled; // LỖI BIÊN DỊCH
```

Việc thêm nhiều dấu ngoặc không thay đổi quy tắc:

```java
// boolean a = ((boolean) (1));     // vẫn sai
// int b = ((int) (false));         // vẫn sai
```

Không có hậu tố literal hoặc tùy chọn `javac` thông thường nào khiến `boolean` trở thành kiểu số. Java chủ ý yêu cầu điều kiện logic rõ ràng, thay vì âm thầm suy luận “khác 0 là đúng”.

### 3.1. So sánh với cast số hợp lệ

```java
int quantity = 5;
long larger = (long) quantity;  // hợp lệ: int -> long
double exactHere = (double) quantity; // hợp lệ: int -> double

double estimate = 5.9;
int truncated = (int) estimate; // hợp lệ nhưng có mất phần thập phân: 5
```

Tính **hợp lệ** của phép cast và việc nó **giữ chính xác dữ liệu** là hai câu hỏi khác nhau. Với `boolean` và kiểu số, câu hỏi đầu đã thất bại: ngôn ngữ không định nghĩa cast primitive giữa chúng.

## 4. Điều kiện trong `if`, `while`, `for` và toán tử logic yêu cầu boolean

Một lỗi chuyển từ các ngôn ngữ cho phép “truthy/falsy” sang Java là viết:

```java
int count = 3;
// if (count) { ... } // LỖI BIÊN DỊCH
```

Trong Java, biểu thức điều kiện của `if`, `while`, `do ... while` và phần điều kiện của `for` thường phải là `boolean` hoặc `Boolean` có thể unbox thành `boolean`. Một `int` riêng lẻ không đủ. Tương tự, toán tử `!` và `&&`/`||` áp dụng cho giá trị logic; `!count` và `count && true` không hợp lệ.

Cách viết đúng phụ thuộc **ý nghĩa nghiệp vụ**:

```java
int count = 3;

if (count > 0) {
    System.out.println("Có phần tử");
}

if (count != 0) {
    System.out.println("Khác không");
}
```

Hai điều kiện này không đồng nghĩa khi `count` âm:

- `count > 0`: chỉ nhận số dương.
- `count != 0`: nhận cả số âm và số dương.
- `count == 1`: chỉ nhận đúng mã `1`.
- `count >= minimum`: thể hiện điều kiện ngưỡng.

**Không tự chọn `!= 0` chỉ để làm trình biên dịch hết báo lỗi.** Hãy chọn phép so sánh diễn đạt đúng dữ liệu đang biểu thị.

### 4.1. Bảng diễn giải 0/1 thường gặp

| Dữ liệu số | Ý định nghiệp vụ | Biểu thức Java |
| --- | --- | --- |
| Bộ đếm `count` | “Có ít nhất một phần tử” | `count > 0` |
| Mã giao thức quy ước 0/1 | “Đúng khi đúng bằng 1” | `code == 1` |
| Trạng thái quy ước mọi số khác 0 là bật | “Bật khi khác 0” | `state != 0` |
| Một bit trong `flags` | “Bit được chọn đang bật” | `(flags & MASK) != 0` |
| Giá trị đo `v` | “Lớn hơn ngưỡng” | `v > threshold` |
| Tập bit phải có đầy đủ | “Tất cả bit trong mask đều bật” | `(flags & MASK) == MASK` |

Đây là **những quy tắc quy ước khác nhau**, không phải các kiểu cast tương đương.

## 5. Cách chuyển ý nghĩa kiểu số sang boolean bằng phép so sánh

Nếu dữ liệu là số đếm, biểu thức `count > 0` trả về `boolean`:

```java
int count = 3;
boolean hasItems = count > 0; // true
```

Nếu dữ liệu là cờ mã hóa bằng `0` hoặc `1`:

```java
int activeCode = 1;
boolean active = activeCode == 1; // true
```

Nếu hợp đồng chấp nhận mọi số khác 0:

```java
int status = -2;
boolean nonzero = status != 0; // true
```

**Sự khác biệt:** ba biến `hasItems`, `active`, `nonzero` có cùng kiểu `boolean`, nhưng chúng được tạo từ **ba điều kiện rõ ràng**.

### 5.1. Đặc biệt với số thực

Với `double`/`float`, không nên tùy tiện dùng `value != 0.0` làm điều kiện “giá trị số hợp lệ” hoặc “có số”:

- `0.0 == -0.0` là `true`; hai giá trị này khác bit dấu nhưng cùng so sánh bằng về mặt `==`.
- `Double.NaN != 0.0` là `true`, nhưng `NaN` **không phải** một độ lớn đo được.
- `Double.POSITIVE_INFINITY != 0.0` là `true`; giá trị vô cực cũng thường không hợp lệ cho phép đo hữu hạn.
- Giá trị rất nhỏ nhưng khác `0.0` vẫn khiến `value != 0.0` thành `true`; yêu cầu nghiệp vụ “đủ lớn để đáng kể” có thể cần ngưỡng.

Ví dụ nếu chỉ muốn giá trị dương **hữu hạn**:

```java
double reading = 2.5;
boolean validPositive = Double.isFinite(reading) && reading > 0.0;
```

Nếu cần “khác 0 và hữu hạn”, viết `Double.isFinite(reading) && reading != 0.0`. Nếu cần so sánh số thực với độ chênh lệch chấp nhận được, chọn tolerance theo bài toán và lưu ý overflow/underflow trong công thức so sánh. Không có một epsilon duy nhất đúng cho mọi dữ liệu.

## 6. Cách mã hóa boolean thành số: dùng toán tử điều kiện

Để xuất `boolean` thành mã nguyên, hãy nêu rõ quy ước bằng **toán tử điều kiện ba ngôi `?:`**:

```java
boolean enabled = true;
int encoded = enabled ? 1 : 0;  // 1
```

Mẫu này đọc là: nếu `enabled` đúng, trả `1`; ngược lại trả `0`. Với mã dài hơn hoặc dùng chung ở nhiều nơi, viết một phương thức đặt tên rõ ràng:

```java
static int toZeroOne(boolean value) {
    return value ? 1 : 0;
}
```

Đây là **một mảnh phương thức** cần đặt trong class để gọi, không phải chương trình độc lập.

Có thể chọn mã khác:

```java
boolean allowed = false;
int protocolCode = allowed ? 100 : 400; // 400
```

Không có quy định chung rằng boolean phải ánh xạ sang `0/1`, `-1/0` hay bất kỳ cặp giá trị nào. Điều này do hợp đồng trao đổi dữ liệu quyết định.

### 6.1. Ternary không phải primitive cast

Biểu thức `enabled ? 1 : 0` trả một giá trị số dựa trên điều kiện boolean; nó **không chuyển kiểu `boolean` thành `int`**.

Ngược lại, `code == 1` trả boolean bằng so sánh số; nó **không chuyển kiểu `int` sang `boolean`**.

Nhận diện đúng thao tác giúp kiểm tra dễ hơn: nếu hệ thống đổi quy ước từ mã `1` sang mã `100`, ta sửa quy tắc mapping mà không thay đổi các quy tắc type conversion của Java.

## 7. Mã 0/1 phải được xác thực nếu input bên ngoài có thể sai

Nếu giao thức tuyên bố chỉ có `0` và `1`, dùng `code != 0` sẽ **âm thầm chấp nhận** `2`, `-1` hoặc `999` là true. Điều đó có thể che giấu dữ liệu lỗi.

Cách tốt hơn là định nghĩa phương thức chỉ nhận hai mã hợp lệ:

```java
static boolean fromZeroOne(int code) {
    if (code == 0) {
        return false;
    }
    if (code == 1) {
        return true;
    }
    throw new IllegalArgumentException("Expected 0 or 1: " + code);
}
```

Nếu một API phải cho phép mọi số khác 0 có nghĩa là true, hãy viết và tài liệu hóa rõ `code != 0`. Hai chính sách không nên bị trộn lẫn.

### Ví dụ hoàn chỉnh: mapping có kiểm tra

Lưu tệp **`NumericBooleanMapping.java`**:

```java
public class NumericBooleanMapping {
    static boolean fromZeroOne(int code) {
        if (code == 0) return false;
        if (code == 1) return true;
        throw new IllegalArgumentException("Expected 0 or 1: " + code);
    }

    static int toZeroOne(boolean value) {
        return value ? 1 : 0;
    }

    public static void main(String[] args) {
        System.out.println(fromZeroOne(0));
        System.out.println(fromZeroOne(1));
        System.out.println(toZeroOne(true));
        System.out.println(toZeroOne(false));

        try {
            fromZeroOne(2);
        } catch (IllegalArgumentException e) {
            System.out.println(e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac --release 17 NumericBooleanMapping.java
java NumericBooleanMapping
```

Stdout chính xác:

```text
false
true
1
0
Expected 0 or 1: 2
```

Lợi ích của phương thức này là **giữ hợp đồng dữ liệu ở một nơi**, phân biệt lỗi input khỏi mã hợp lệ và tránh sao chép các phép so sánh khác nhau khắp chương trình.

## 8. Wrapper `Boolean` và `Number` cũng không phải cầu nối cast

Các wrapper như `Integer`, `Long`, `Double` là đối tượng đại diện các giá trị số và kế thừa `Number`. `Boolean` đại diện giá trị logic; nó **không kế thừa `Number`**.

Ví dụ hợp lệ:

```java
Integer boxedInt = Integer.valueOf(1);
Boolean boxedFlag = Boolean.TRUE;

int number = boxedInt.intValue();
boolean flag = boxedFlag.booleanValue();
```

Nhưng không có cách cast trực tiếp `Integer` thành `Boolean` để nhận “1 = true”, hoặc cast `Boolean` thành `Integer` để nhận “true = 1”.

Đừng dùng ép kiểu gián tiếp qua `Object` để “né” lỗi trình biên dịch. Ví dụ nếu một tham chiếu `Object` đang chứa `Integer`, cast nó thành `Boolean` sẽ dẫn đến lỗi kiểu lúc chạy (`ClassCastException`), thay vì tự động chuyển giá trị số thành logic. Việc boxing/unboxing không sáng tạo quy tắc numeric-to-boolean.

### 8.1. Unboxing đúng nghĩa là gì?

`Boolean enabled = Boolean.TRUE;` có thể unbox thành `boolean` trong ngữ cảnh cần primitive boolean. Đó là **`Boolean → boolean`**, không phải `int → boolean`.

Cần đề phòng `null`:

```java
Boolean optional = null;
// if (optional) { } // chạy sẽ ném NullPointerException khi unbox
boolean safelyTrue = Boolean.TRUE.equals(optional); // false
```

Nếu dữ liệu có ba trạng thái “true”, “false”, “chưa biết”, đừng vội ép mọi trường hợp vào số `0/1` rồi làm mất trạng thái null. Nên chọn mô hình dữ liệu thể hiện rõ đủ trạng thái.

## 9. Parse chuỗi: `Boolean.parseBoolean` không hiểu chuỗi "1" là true

Đây là một nhầm lẫn phổ biến khi chuyển từ biểu diễn số trong file, JSON hoặc form nhập:

```java
System.out.println(Boolean.parseBoolean("true"));  // true
System.out.println(Boolean.parseBoolean("TrUe"));  // true
System.out.println(Boolean.parseBoolean("1"));     // false
System.out.println(Boolean.parseBoolean("0"));     // false
System.out.println(Boolean.parseBoolean(" TRUE ")); // false
```

`Boolean.parseBoolean(String)` trả `true` **chỉ khi** chuỗi khác null và bằng `"true"` theo so sánh không phân biệt hoa/thường. Các chuỗi khác trả `false`. Nó không parse `"1"` thành true, và không tự trim khoảng trắng.

Nếu dữ liệu đầu vào quy ước `"0"`/`"1"`, có thể parse sang số rồi chuyển bằng chính sách:

```java
String raw = "1";
int code = Integer.parseInt(raw);
boolean active = code == 1; // chỉ đúng khi hợp đồng cho phép các giá trị khác
```

Nếu hợp đồng chỉ nhận `0/1`, hãy gọi `fromZeroOne(code)` ở mục trên để **báo lỗi** khi nhận `2`. `Integer.parseInt` có thể ném `NumberFormatException` nếu dữ liệu không phải số nguyên hợp lệ, vì vậy API nhận dữ liệu bên ngoài cần xử lý trường hợp này theo yêu cầu.

Với một trường boolean thực sự trong JSON, nhiều thư viện mapping sẽ dùng giá trị JSON `true`/`false`. Nếu bên ngoài gửi `0/1`, bạn đang xử lý một **quy ước schema** và phải kiểm tra chính sách mapping của thư viện; Java primitive cast không tự xử lý việc ấy.

## 10. Bitmask: giá trị bitwise là số, điều kiện được tạo bằng so sánh

Các toán tử `&`, `|`, `^` và `~` cũng xuất hiện ở chủ đề Numbers. Với toán hạng kiểu `int`, `&` trả về **`int`**, không phải `boolean`.

Ví dụ:

```java
int flags = 0b0101;
int mask = 0b0100;

// boolean invalid = flags & mask; // LỖI: int không thể gán sang boolean
boolean hasFlag = (flags & mask) != 0; // true
```

Đọc logic đúng:

1. `flags & mask` tạo một **giá trị nguyên** chứa các bit chung.
2. `!= 0` **so sánh** giá trị đó với số 0 và tạo ra `boolean`.
3. Biến `hasFlag` nhận kết quả của phép so sánh.

Nếu mask có nhiều bit và cần tất cả đều bật, dùng `(flags & mask) == mask`. Đừng nhầm kiểm tra “ít nhất một bit” với kiểm tra “mọi bit”.

### 10.1. `&` và `|` cũng hoạt động trên boolean

Java có hai nhóm overload ngữ nghĩa của `&`, `|` và `^`:

- Với **hai toán hạng nguyên**, chúng thao tác từng bit và cho giá trị số nguyên.
- Với **hai toán hạng boolean**, chúng thực hiện AND/OR/XOR logic và cho `boolean`.

`&&` và `||` chỉ dành cho logic và có khả năng short circuit; `&`/`|` trên boolean vẫn đánh giá cả hai toán hạng.

Ví dụ hợp lệ:

```java
boolean a = true;
boolean b = false;
boolean x = a & b; // false
boolean y = a | b; // true
boolean z = a ^ b; // true
```

Ngược lại, `int bits = 1 & 2;` cho `0`; `boolean test = 1 & 2;` không hợp lệ do vế phải là `int`. Việc cùng dùng ký hiệu `&` không tạo một cast tự động giữa hai loại kết quả.

## 11. Ví dụ Java hoàn chỉnh: số tạo điều kiện, điều kiện tạo mã số

Lưu tệp **`NumericBooleanConditions.java`**:

```java
public class NumericBooleanConditions {
    public static void main(String[] args) {
        int count = 3;
        double measurement = 0.0;

        boolean hasItems = count != 0;
        boolean isPositive = count > 0;
        boolean hasNonzeroMeasurement = measurement != 0.0;

        System.out.println(hasItems);
        System.out.println(isPositive);
        System.out.println(hasNonzeroMeasurement);

        System.out.println(hasItems ? 1 : 0);
        System.out.println(false ? 1 : 0);

        System.out.println(Double.NaN != 0.0);
        System.out.println(Double.isFinite(Double.NaN));

        int flags = 0b0101;
        System.out.println((flags & 0b0100) != 0);
        System.out.println((flags & 0b0010) != 0);
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac --release 17 NumericBooleanConditions.java
java NumericBooleanConditions
```

**Stdout chính xác:**

```text
true
true
false
1
0
true
false
true
false
```

Giải thích:

- `count != 0` và `count > 0` đều đúng cho `3` nhưng không cùng hợp đồng ở mọi giá trị.
- `measurement != 0.0` sai cho `0.0`.
- Toán tử `?:` mã hóa `boolean` thành `int` theo quy ước `true ↦ 1` và `false ↦ 0`.
- `Double.NaN != 0.0` đúng vì so sánh không bằng với NaN luôn đúng (trừ các chi tiết riêng của một số phương thức so sánh đối tượng); `Double.isFinite(Double.NaN)` trả false.
- Bitmask `0101 & 0100` khác 0, còn `0101 & 0010` bằng 0.

Đây là ví dụ cho thấy **rõ ràng từng bước chuyển ý nghĩa**, hoàn toàn không dùng cast trực tiếp giữa kiểu số và boolean.

## 12. Lỗi biên dịch thường gặp và cách sửa

Các đoạn trong bảng là mã **cố ý không hợp lệ**. Mọi cách sửa cần được đánh giá theo yêu cầu thực, vì khác ý nghĩa sẽ cho kết quả khác.

| Mã sai | Lý do | Cách sửa có chủ đích |
| --- | --- | --- |
| `boolean b = (boolean) 1;` | Không có numeric-to-boolean cast | `boolean b = (1 == 1);` hoặc `true` nếu là hằng |
| `int n = (int) true;` | Không có boolean-to-numeric cast | `int n = true ? 1 : 0;` |
| `if (count) { ... }` | `int` không là điều kiện boolean | `if (count > 0) { ... }` nếu “có phần tử” |
| `while (n) { ... }` | `n` không là `boolean` | `while (n != 0) { ... }` nếu dữ liệu xác nhận |
| `boolean x = 1 & 2;` | `1 & 2` có kiểu `int` | `boolean x = (1 & 2) != 0;` |
| `boolean a = !1;` | `!` cần boolean | `boolean a = !(1 != 0);` nếu thực sự muốn phủ định “khác 0” |
| `boolean b = "1";` | Chuỗi không là boolean | Parse/mapping theo schema, không cast |
| `Boolean b = Integer.valueOf(1);` | Wrapper khác kiểu | `Boolean b = Integer.valueOf(1) == 1;` nếu chỉ nhận mã 1 |

Khi IDE hoặc `javac` báo `incompatible types` hoặc `bad operand types`, hãy nhìn vào **kiểu của từng biểu thức**, không chỉ kiểu biến đích. Gắn thêm `(boolean)` hoặc `(int)` sẽ không sửa được lỗi chuyển giữa hai họ kiểu này.

### 12.1. Điều gì xảy ra nếu ép kiểu một `Object`?

Giả sử một giá trị tại runtime được lưu dưới dạng `Integer`. Ép tham chiếu `Object` thành `Boolean` (khi biểu thức được chấp nhận bởi cơ chế reference casting) không chuyển số `1` thành `true`; kiểu object thực tế vẫn là `Integer` và cast sai có thể gây `ClassCastException`. Đây là **reference cast khác với primitive value conversion**. Tốt nhất định nghĩa phương thức mapping tường minh ở biên nhận dữ liệu.

## 13. Câu hỏi tự luyện có đáp án

**Bài 1 — Phân loại mã hợp lệ.** Mã nào biên dịch: `boolean a = 0;`, `boolean b = 0 == 0;`, `int c = true ? 1 : 0;` và `int d = (int) false;`?

Đáp án: `b` và `c` hợp lệ; `a` và `d` sai vì Java không chuyển primitive số ↔ boolean.

**Bài 2 — Chọn điều kiện đúng.** Với `int count = -1;`, `count != 0` và `count > 0` trả gì?

Đáp án: `true` và `false`. Nếu count là số lượng hợp lệ phải không âm, cần xử lý giá trị âm như một lỗi hoặc xác định thêm hợp đồng.

**Bài 3 — Kiểm tra 0/1 nghiêm ngặt.** Một API chỉ chấp nhận mã `0` và `1`. Vì sao `code != 0` không đủ? Hãy viết hàm nhận 0/1 và báo lỗi nếu nhận 2.

Đáp án: `2 != 0` cũng true, dù 2 không phải mã hợp lệ. Dùng `fromZeroOne` ở mục 7, ném `IllegalArgumentException` cho các giá trị khác.

**Bài 4 — Đổi boolean sang số.** Với `boolean permitted = false;`, làm sao xuất `0`?

Đáp án: `int code = permitted ? 1 : 0;`. Đây là biểu thức chọn giá trị số, không phải cast.

**Bài 5 — NaN.** Với `double value = Double.NaN;`, `value != 0.0` và `Double.isFinite(value)` bằng gì?

Đáp án: `true` và `false`. Vì vậy không dùng riêng `!= 0` để kết luận “số đo hợp lệ”.

**Bài 6 — Wrapper.** Tại sao `Boolean.parseBoolean("1")` trả false? Nó có phải chuyển từ số nguyên 1 sang boolean không?

Đáp án: phương thức chỉ nhận chuỗi tương đương `"true"` (không phân biệt hoa/thường), và `"1"` không thỏa. Đây là **parsing chuỗi**, không phải numeric cast.

**Bài 7 — Bitmask.** Với `flags = 0b0101` và `mask = 0b0100`, biểu thức `flags & mask` có kiểu gì? Viết điều kiện boolean kiểm tra cờ.

Đáp án: `int`, giá trị `4`. `boolean enabled = (flags & mask) != 0;` trả true.

**Bài 8 — Toán tử logic.** Có thể viết `1 && 1` trong Java không? Làm sao diễn đạt ý “hai số đều khác 0”?

Đáp án: không; `&&` yêu cầu boolean. Viết `(a != 0) && (b != 0)` với hai biến số `a`/`b`.

**Bài 9 — Nullability.** Điều gì xảy ra khi unbox `Boolean b = null;` vào biến `boolean`?

Đáp án: xảy ra `NullPointerException` ở runtime. Nếu null có ý nghĩa “chưa có dữ liệu”, phải xử lý riêng; ví dụ kiểm tra `Boolean.TRUE.equals(b)` khi chỉ cần nhận đúng `true`.

## 14. Checklist khi xử lý Numbers và chuyển kiểu

- [ ] Tôi biết `boolean` là primitive logic riêng, không thuộc các numeric primitive.
- [ ] Tôi không dùng `(boolean) number`, `(int) boolean` hay gán `0/1` trực tiếp cho `boolean`.
- [ ] Tôi phân biệt numeric conversion với điều kiện logic và mapping nghiệp vụ.
- [ ] Tôi dùng `count > 0`, `code == 1` hoặc `code != 0` có lý do rõ, thay vì tự coi mọi số có “truthiness”.
- [ ] Tôi kiểm tra miền input trước khi chuyển mã giao tiếp, không âm thầm chấp nhận mã lỗi.
- [ ] Tôi biết toán tử `?:` có thể chọn `1/0` để mã hóa boolean theo hợp đồng.
- [ ] Tôi không nhầm `Boolean.parseBoolean("1")` với phép chuyển số sang boolean.
- [ ] Tôi xét đúng các trường hợp `0.0`, `-0.0`, `NaN` và vô cực nếu điều kiện lấy từ số thực.
- [ ] Tôi biết `flags & mask` có kiểu số, và `(flags & mask) != 0` mới là boolean.
- [ ] Tôi không coi `Boolean` là `Number` hoặc dùng reference cast như một phép chuyển nội dung.
- [ ] Tôi đã chạy ví dụ, thử input ngoài miền và tự giải thích được lỗi biên dịch.

## 15. Tài liệu chuẩn để đối chiếu

- [JLS 17 §4.2 — Primitive Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2): phân biệt numeric primitive và `boolean`.
- [JLS 17 §5.1.2 — Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.2): chuyển rộng primitive, không chuyển sang `boolean`.
- [JLS 17 §5.1.3 — Narrowing Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.3): chuyển hẹp giữa các kiểu primitive được phép.
- [JLS 17 §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): những chuyển đổi mà casting context cho phép.
- [JLS 17 §14.9 — The `if` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.9): điều kiện phải có kiểu boolean/Boolean.
- [JLS 17 §15.22 — Bitwise and Logical Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.22): cùng ký hiệu `&`/`|`/`^` nhưng toán hạng số và boolean có hợp đồng khác nhau.
- [Java SE 17 Boolean API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Boolean.html): `parseBoolean`, `valueOf` và wrapper boolean.

Hãy luôn diễn đạt rõ **dữ liệu số đang có ý nghĩa gì** trước khi đưa nó vào điều kiện. Java không có cast trực tiếp giữa số và `boolean`, vì vậy phép so sánh, phương thức mapping và xác thực input là nơi phải thể hiện quy tắc mà chương trình thực sự mong muốn.