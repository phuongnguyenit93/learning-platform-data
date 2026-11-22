# Ảnh hưởng của hậu tố L, F, D và phép ép kiểu khi dùng `var` (Java 10+)

## 1. Vì sao hậu tố literal và ép kiểu lại quan trọng với `var`?

Từ Java 10, `var` cho phép **suy luận kiểu biến cục bộ** từ **kiểu tĩnh của biểu thức khởi tạo**. Trình biên dịch xác định kiểu **ngay lúc biên dịch**; nó không suy luận lại dựa trên lệnh gán tiếp theo và không khiến Java trở thành ngôn ngữ kiểu động.

Ví dụ:

```java
var a = 10;      // int
var b = 10L;     // long
var c = 10F;     // float
var d = 10D;     // double
```

Cả bốn biến đều khởi tạo bằng số có cùng giá trị toán học là 10, nhưng **kiểu tĩnh khác nhau**. Hậu tố viết ngay sau literal tham gia xác định kiểu của **chính literal**, và `var` nhận kiểu của biểu thức khởi tạo đó.

Cũng tương tự, **phép ép kiểu tường minh (*cast*)** có thể thay đổi kiểu của biểu thức trước khi `var` suy luận:

```java
var x = 10;          // int
var y = (long) 10;   // long
var z = (byte) 10;   // byte
```

Mục tiêu của bài là phân biệt chính xác **kiểu literal**, **kiểu của biểu thức sau phép toán/ép kiểu**, **kiểu biến do `var` suy luận**, và **giá trị kết quả**. Bốn khái niệm này liên quan nhưng không phải lúc nào cũng giống nhau.

## 2. Quy tắc của hậu tố `L`, `F`, `D`

### 2.1. `L` hoặc `l`: literal số nguyên kiểu `long`

```java
var count = 100;       // int
var largeCount = 100L; // long
var alsoLong = 100l;   // long, nhưng không nên viết l thường
```

- Literal số nguyên thập phân **không có hậu tố** thông thường mang kiểu `int`; nếu giá trị nằm ngoài phạm vi `int` thì thường phải dùng `L` để tạo literal kiểu `long`.
- Hậu tố `L` cũng áp dụng cho literal số nguyên ở hệ 16 (`0xFFL`), hệ 2 (`0b1010L`) hoặc hệ 8 (`077L`).
- **Nên dùng chữ `L` viết hoa** vì chữ `l` thường dễ nhầm với chữ số `1`.
- `L` biểu diễn kiểu `long`, **không có nghĩa** phép toán sau đó tự tránh tràn số. `long` cũng có giới hạn giá trị.

Ví dụ số nguyên lớn:

```java
// var big = 3_000_000_000; // Sai: literal thập phân không hậu tố vượt phạm vi int
var big = 3_000_000_000L;   // long, hợp lệ
```

Dấu gạch dưới trong literal chỉ giúp dễ đọc; nó không tự làm literal trở thành `long`.

### 2.2. `F` hoặc `f`: literal dấu phẩy động kiểu `float`

```java
var rate = 1.5;    // double, vì không có F
var rateF = 1.5F;  // float
var ratef = 1.5f;  // float
var scientific = 1e3F; // float, giá trị 1000.0
```

- Literal dấu phẩy động không có hậu tố có kiểu **`double`** (ví dụ `0.5`, `1.5`, `1e3`).
- Thêm `F` hoặc `f` biến nó thành literal **`float`**; `var` theo đó suy ra `float` nếu biểu thức chỉ gồm literal đó.
- `float` dùng độ chính xác thấp hơn `double`, nên không phải mọi số thập phân đều có biểu diễn nhị phân chính xác. **Không coi hậu tố `F` là phép làm tròn theo số chữ số thập phân**; nó chọn định dạng số dấu phẩy động.
- Nếu một phép toán cần độ chính xác của `double`, hãy chọn `double`; `F` chỉ hợp lý khi muốn `float` một cách có chủ đích (ví dụ API dùng `float` hoặc yêu cầu bộ nhớ/định dạng dữ liệu cụ thể).

### 2.3. `D` hoặc `d`: literal dấu phẩy động kiểu `double`

```java
var a = 2.5;     // double
var b = 2.5D;    // double
var c = 2.5d;    // double
var d = 2D;      // double; không bắt buộc có dấu chấm
```

`D` không bắt buộc khi literal dấu phẩy động đã có kiểu mặc định `double`, nhưng có thể hữu ích để **nhấn mạnh chủ ý** hoặc phân biệt với literal nguyên `2`. `2D` là `double`, còn `2L` là `long` và `2` là `int`.

**Không thể gắn `L` vào một literal có phần thập phân**: `1.5L` không hợp lệ. Hãy dùng `1.5F` hoặc `1.5D` tùy kiểu dấu phẩy động cần dùng.

### 2.4. Bảng tổng hợp

| Khởi tạo | Kiểu `var` suy ra | Lý do |
| --- | --- | --- |
| `var x = 42;` | `int` | Literal nguyên mặc định |
| `var x = 42L;` | `long` | Hậu tố `L` |
| `var x = 42F;` | `float` | Hậu tố `F` |
| `var x = 42D;` | `double` | Hậu tố `D` |
| `var x = 0.25;` | `double` | Literal dấu phẩy động mặc định |
| `var x = 0.25F;` | `float` | Literal dấu phẩy động có `F` |
| `var x = 1e2;` | `double` | Dạng lũy thừa không hậu tố |
| `var x = 0b1010L;` | `long` | Literal nhị phân có `L` |

Các dòng trong bảng là **khai báo độc lập** để giải thích kiểu; không đặt nhiều biến cùng tên `x` vào một khối mã duy nhất.

## 3. Phép ép kiểu thay đổi kiểu mà `var` nhìn thấy

Cú pháp ép kiểu tường minh là `(TenKieu) bieuThuc`. Trong khai báo `var`, trình biên dịch xem **kiểu của toàn biểu thức sau phép ép**, không chỉ kiểu của literal ban đầu.

```java
var a = (long) 7;       // long
var b = (float) 7;      // float
var c = (double) 7;     // double
var d = (int) 7.9;      // int, giá trị 7
var e = (short) 100;    // short
var f = (byte) 100;     // byte
```

Đối với biến `d`, phép chuyển từ `double` sang `int` là **narrowing primitive conversion**: với giá trị hữu hạn, trong phạm vi bình thường như `7.9`, phần lẻ bị bỏ **về phía 0**. Vì vậy `(int) 7.9` cho `7` và `(int) (-7.9)` cho `-7`, không phải làm tròn tới số nguyên gần nhất.

Ép kiểu thu hẹp còn có thể **mất dữ liệu hoặc đổi giá trị**:

```java
var small = (byte) 130; // byte, giá trị -126
```

Vì `byte` có miền giá trị từ `-128` đến `127`, chuyển `130` từ `int` sang `byte` chỉ giữ 8 bit thấp nên kết quả là `-126`. `var` chỉ suy ra kiểu `byte`, **không ngăn mất dữ liệu do ép kiểu**. Với dữ liệu đầu vào không được kiểm soát, cần kiểm tra phạm vi trước khi ép.

Nếu cần chuyển đổi nguyên chính xác và phải phát hiện tràn khi thu hẹp từ `long` sang `int`, có thể dùng API hiện hành `Math.toIntExact(long)`; phương thức này ném `ArithmeticException` khi giá trị vượt phạm vi `int`. Đây là lựa chọn an toàn hơn việc ép kiểu âm thầm cắt bớt bit trong những trường hợp đòi hỏi bảo toàn giá trị.

### Suy luận từ `(float)` khác với hậu tố `F` thế nào?

```java
var f1 = 2.5F;        // float: literal được khai báo trực tiếp là float
var f2 = (float) 2.5; // float: literal là double, rồi ép thành float
```

Cả hai biến đều có kiểu `float`. Tuy nhiên, với giá trị khó biểu diễn chính xác, hai cách có thể liên quan đến việc chuyển đổi/làm tròn số. Khi viết hằng số `float` thông thường, `2.5F` rõ ràng và ngắn hơn; khi chuyển giá trị đang có kiểu `double` sang `float`, dùng phép ép kiểu và hiểu rủi ro mất độ chính xác.

## 4. `var` suy ra kiểu của **toàn biểu thức**, không phải literal đầu tiên

Nếu vế phải chứa phép toán, thứ quyết định kiểu của `var` là **kiểu kết quả của biểu thức** sau các quy tắc *numeric promotion* (nâng kiểu số), không chỉ hậu tố của một toán hạng.

### 4.1. Nâng kiểu số trong phép toán nhị phân

Với những phép toán số học nhị phân thông dụng như `+`, `-`, `*`, `/`, Java thực hiện nâng kiểu số theo thứ tự ưu tiên về cơ bản:

1. Có toán hạng `double` → kết quả là `double`.
2. Nếu không có `double` nhưng có `float` → kết quả là `float`.
3. Nếu không có hai kiểu trên nhưng có `long` → kết quả là `long`.
4. Nếu không, các toán hạng nguyên nhỏ như `byte`, `short`, `char` được nâng lên `int` → kết quả là `int`.

Ví dụ:

| Biểu thức khởi tạo | Kiểu được suy ra | Điểm cần chú ý |
| --- | --- | --- |
| `var sum = 1 + 2L;` | `long` | `int + long` cho `long` |
| `var sum = 1L + 2F;` | `float` | Có `float` nên `long` được chuyển khi tính; có thể mất độ chính xác |
| `var sum = 1F + 2D;` | `double` | Có `double` |
| `var sum = (byte) 1 + (byte) 2;` | `int` | Hai `byte` đều được nâng lên `int` trước phép `+` |
| `var sum = 2L + 3;` | `long` | Toán hạng `int` được chuyển thành `long` |

Đây là lý do **`var sum = (byte) 1 + (byte) 2` không tạo biến `byte`**, mặc dù cả hai toán hạng đều đã được ép thành `byte`. Nếu cần biến `byte`, phải ép **toàn bộ kết quả**:

```java
var result = (byte) ((byte) 1 + (byte) 2); // byte, giá trị 3
```

Chỉ dùng phép ép như vậy khi đã chắc chắn kết quả nằm trong miền của kiểu đích hoặc chấp nhận hành vi thu hẹp.

### 4.2. Hậu tố và phép chia nguyên: hai tình huống khác nhau

```java
var a = 7 / 2;          // int, giá trị 3
var b = 7F / 2;         // float, giá trị 3.5
var c = 7D / 2;         // double, giá trị 3.5
var d = (double) 7 / 2; // double, giá trị 3.5
var e = (double) (7 / 2); // double, giá trị 3.0
```

Giải thích:

- `7 / 2` chia hai số nguyên, nên dùng **chia số nguyên**, loại phần dư và cho `int 3`.
- `7F / 2`: có toán hạng `float`, nên phép chia dấu phẩy động cho `float 3.5`.
- `7D / 2`: có toán hạng `double`, nên cho `double 3.5`.
- `(double) 7 / 2`: ép toán hạng trái trước khi chia, nên nhận `double 3.5`.
- `(double) (7 / 2)`: **chia số nguyên xong** mới ép `int 3` thành `double 3.0`. Phép ép không thể khôi phục phần lẻ đã mất.

Vì vậy, nếu cần kết quả chia thập phân, phải đảm bảo **ít nhất một toán hạng là `float` hoặc `double` trước khi phép chia diễn ra**.

### 4.3. Kiểu `var` cố định sau khi suy luận

```java
var size = 1;    // int
// size = 2L;    // Lỗi biên dịch: long không gán ngầm vào int

var total = 1L;  // long
total = 2;       // Hợp lệ: chuyển int -> long

var ratio = 1F;  // float
// ratio = 2D;   // Lỗi: double không gán ngầm vào float

var precise = 1D; // double
precise = 2F;     // Hợp lệ: chuyển float -> double
```

Chú ý: Java có một số quy tắc riêng cho **hằng số nguyên tại thời gian biên dịch** khi gán vào `byte`/`short`/`char` nếu giá trị nằm trong phạm vi. Điều đó **không thay đổi kiểu `var` đã suy ra**. Ví dụ `var b = (byte) 10;` vẫn là `byte` kể cả khi `b = 11;` hợp lệ vì `11` là hằng số `int` vừa phạm vi.

## 5. Quy tắc đặt hậu tố và những lỗi thường gặp

### 5.1. Nhầm kiểu `int` với `long`

```java
// var millis = 3_000_000_000; // Không hợp lệ như literal int thập phân
var millis = 3_000_000_000L;   // long
```

Ngay cả khi số còn trong phạm vi `int`, bạn vẫn cần `L` nếu kiểu **mong muốn** là `long`:

```java
var attempts = 3;   // int
var capacity = 3L;  // long
```

### 5.2. Nhầm mặc định `double` với `float`

```java
var speed = 1.25;     // double
var speedF = 1.25F;   // float
```

Không có cơ chế nào để `var speed = 1.25;` tự hiểu rằng bạn muốn `float` theo tên biến hoặc các nơi sử dụng sau đó.

### 5.3. Dùng `L` cho số thập phân hoặc thiếu hậu tố khi phải có `float`

```java
// var wrong = 1.5L;        // Sai: hậu tố L không dùng cho literal có dấu chấm
var goodFloat = 1.5F;       // float
var goodDouble = 1.5D;     // double
```

Nếu cần biểu diễn số nguyên lớn, dùng literal nguyên có `L`, ví dụ `1_500_000_000L`.

### 5.4. Tưởng ép kiểu ở cuối sẽ sửa được phép tính ở trước

```java
var wrongAverage = (double) (5 / 2); // 2.0
var correctAverage = (double) 5 / 2; // 2.5
```

Thứ tự thực hiện của các phép toán là yếu tố quan trọng. Phép ép kiểu sau phép chia nguyên chỉ thay đổi **kiểu biểu diễn của kết quả đã bị cắt phần lẻ**.

### 5.5. Nhầm phép ép kiểu với tính an toàn của dữ liệu

```java
var value = (byte) 130; // byte, -126
```

Chương trình biên dịch được nhưng giá trị đã đổi. Không nên ép kiểu chỉ để khiến phép gán biên dịch, đặc biệt với giá trị nhận từ người dùng, dữ liệu ngoài hệ thống hoặc phép tính có thể vượt phạm vi kiểu đích.

### 5.6. Dùng `F` khi không cần độ chính xác `float`

`float` có độ chính xác hữu hạn thấp hơn `double`; nhiều giá trị như `0.1F` không biểu diễn chính xác dưới dạng nhị phân. Với tính toán tiền tệ cần chính xác theo thập phân, **không nên mặc định dùng `float` hoặc `double`**; thường cần `BigDecimal` với quy tắc làm tròn được xác định rõ. Đối với literal thập phân truyền vào `BigDecimal`, ưu tiên **chuỗi** như `new BigDecimal("0.10")` thay vì dựng từ `double` nếu muốn giữ chính xác giá trị thập phân. Đây là lưu ý khi chọn kiểu số cho bài toán; không phải một quy tắc riêng của `var`.

## 6. Ví dụ Java 17+ hoàn chỉnh và kết quả chính xác

Lưu mã dưới đây vào file **`VarNumberDemo.java`**:

```java
public class VarNumberDemo {
    public static void main(String[] args) {
        var amount = 10L;                    // long
        var factor = 1.5F;                   // float
        var precise = 1.5D;                  // double
        var implicitDouble = 1.5;            // double

        var noSuffix = 7 / 2;                // int
        var floatResult = 7F / 2;            // float
        var castBefore = (double) 7 / 2;     // double
        var castAfter = (double) (7 / 2);    // double

        var narrowed = (byte) 130;           // byte
        var intPromoted = (byte) 100 + (byte) 20; // int
        var mixed = 2 + 3L;                  // long

        System.out.println("amount=" + amount);
        System.out.println("factor=" + factor);
        System.out.println("precise=" + precise);
        System.out.println("implicitDouble=" + implicitDouble);
        System.out.println("noSuffix=" + noSuffix);
        System.out.println("floatResult=" + floatResult);
        System.out.println("castBefore=" + castBefore);
        System.out.println("castAfter=" + castAfter);
        System.out.println("narrowed=" + narrowed);
        System.out.println("intPromoted=" + intPromoted);
        System.out.println("mixed=" + mixed);
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac -encoding UTF-8 VarNumberDemo.java
java VarNumberDemo
```

Kết quả:

```text
amount=10
factor=1.5
precise=1.5
implicitDouble=1.5
noSuffix=3
floatResult=3.5
castBefore=3.5
castAfter=3.0
narrowed=-126
intPromoted=120
mixed=5
```

Đọc từng nhóm kết quả:

1. `amount` được suy ra `long` nhờ `L`; `factor` là `float` nhờ `F`; `precise` và `implicitDouble` đều là `double`.
2. `noSuffix` là phép chia nguyên: `7 / 2` cho `3`. Các biến `floatResult` và `castBefore` chia kiểu dấu phẩy động nên cho `3.5`, còn `castAfter` ép sau phép chia nên cho `3.0`.
3. `narrowed` có kiểu `byte` với giá trị `-126` vì thu hẹp `130`; `intPromoted` có kiểu `int` do quy tắc nâng kiểu số học với `byte + byte`.
4. `mixed` là `long` vì `int + long` cho `long`.

Đoạn này dùng cú pháp Java ổn định từ Java 10 trở đi và API chuẩn, không cần tính năng preview.

## 7. Hướng dẫn chọn cách viết dễ hiểu

- **Muốn `int`:** dùng literal nguyên bình thường như `var count = 0;`.
- **Muốn `long`:** dùng hậu tố rõ ràng `L`, ví dụ `var timeoutMillis = 5_000L;`; tránh `l` thường.
- **Muốn `float`:** dùng `F` khi API/bài toán thật sự cần `float`, ví dụ `var gain = 0.5F;`.
- **Muốn `double`:** literal thập phân không hậu tố đã cho `double`; `D` giúp nhấn mạnh, ví dụ `var ratio = 0.5D;`.
- **Muốn ép sang kiểu khác:** đặt phép ép đúng chỗ trong biểu thức, chẳng hạn `var average = (double) total / count;`, đồng thời kiểm tra rủi ro mất giá trị.
- **Khi kiểu và ý định dễ bị hiểu nhầm:** có thể dùng khai báo tường minh `long timeout = 5_000;` hoặc `double ratio = 0.5;`. `var` là lựa chọn về cách diễn đạt, không phải bắt buộc.

Cần nhớ rằng **hậu tố chọn kiểu literal**, **toán tử có thể nâng kiểu biểu thức**, **cast đổi kiểu của biểu thức tại vị trí đặt cast**, còn **`var` lấy kiểu cuối cùng của biểu thức khởi tạo**. Hiểu đúng trình tự đó giúp tránh lỗi kiểu dữ liệu và sai lệch giá trị.

## 8. Bài tập tự kiểm tra

**Câu 1.** Kiểu của các biến sau là gì?

```java
var a = 5;
var b = 5L;
var c = 5F;
var d = 5D;
```

**Đáp án:** Lần lượt `int`, `long`, `float` và `double`.

**Câu 2.** `var a = 9 / 4;` khác `var b = 9D / 4;` ở điểm nào?

**Đáp án:** `a` có kiểu `int` và giá trị `2` do chia nguyên; `b` có kiểu `double` và giá trị `2.25` vì có toán hạng `double`.

**Câu 3.** `var value = (short) 20 + 1;` suy ra `short` hay `int`?

**Đáp án:** `int`. Toán hạng `short` được nâng lên `int` khi thực hiện phép `+`. Nếu muốn kiểu `short` sau phép cộng, phải ép toàn bộ kết quả và cân nhắc mất dữ liệu.

**Câu 4.** Có thể sửa lỗi chia nguyên bằng cách viết `var average = (double) (9 / 4);` không?

**Đáp án:** Không. `9 / 4` đã cho `int 2`, sau đó cast thành `double 2.0`. Viết `(double) 9 / 4` hoặc `9D / 4` để được `2.25`.

**Câu 5.** Vì sao `var result = (byte) 130;` có thể biên dịch nhưng không có giá trị `130`?

**Đáp án:** Cast sang `byte` là thu hẹp kiểu, chỉ giữ các bit thấp nên `130` thành `-126`. `var` suy ra đúng kiểu `byte` của kết quả đã ép, không tự kiểm tra giá trị có bị thay đổi không.

## 9. Tóm tắt kiến thức cần nhớ

1. `var` suy ra **kiểu tĩnh của toàn biểu thức khởi tạo** ở thời điểm biên dịch; kiểu đó cố định.
2. `L` → literal số nguyên `long`; `F` → literal dấu phẩy động `float`; `D` → literal `double`. Literal số nguyên thông thường là `int` và literal dấu phẩy động mặc định là `double`.
3. Phép ép `(type) expression` có thể đổi kiểu mà `var` suy ra và có thể gây mất dữ liệu.
4. Phép toán số học áp dụng quy tắc nâng kiểu; `byte + byte` tạo `int`, `int + long` tạo `long`, `float + double` tạo `double`.
5. **Ép kiểu trước hay sau phép chia** quyết định có bị mất phần thập phân do chia nguyên hay không.
6. Ưu tiên biểu thức rõ kiểu, đặt hậu tố/cast có chủ đích và kiểm tra phạm vi dữ liệu trước khi thu hẹp.

## Tài liệu tham khảo chính thức

- OpenJDK JEP 286 — Local-Variable Type Inference (Java 10): https://openjdk.org/jeps/286
- Java Language Specification — Integer Literals (`3.10.1): https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.1
- Java Language Specification — Floating-Point Literals (`3.10.2): https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.2
- Java Language Specification — Numeric Promotions (`5.6), Casting Contexts (`5.5): https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html
- Dev.java — Using the Var Type Identifier: https://dev.java/learn/language-basics/using-var/
