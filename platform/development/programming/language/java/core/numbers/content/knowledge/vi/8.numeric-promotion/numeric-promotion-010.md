# `var` suy luận kiểu từ initializer, không từ cách dùng về sau

Khi viết `var x = expression;` trong Java, trình biên dịch xác định **kiểu tĩnh của biến `x` tại thời điểm khai báo** từ kiểu của **biểu thức khởi tạo (initializer)**. Kiểu này được cố định cho toàn bộ phạm vi biến. Java **không** theo dõi các lệnh gán, lời gọi phương thức hay cách sử dụng về sau để suy ra một kiểu rộng hơn.

```java
var count = 10;   // Kiểu tĩnh của count: int
count = 20;       // Hợp lệ: int → int
// count = 20L;   // Lỗi biên dịch: long không tự thu hẹp về int

var total = 10L;  // Kiểu tĩnh của total: long ngay từ đầu
total = 20L;      // Hợp lệ
```

`var` là **suy luận kiểu cục bộ lúc biên dịch**, không phải biến “tự đổi kiểu” hay kiểu dữ liệu động. Điều này đặc biệt quan trọng với **literal số**, **nâng kiểu toán hạng**, **phép chia nguyên** và **tràn số**, bởi Java quyết định loại phép tính từ **kiểu của biểu thức** chứ không phải từ ý định mà người viết sẽ thể hiện sau đó.

## 1. Cơ chế: initializer quyết định kiểu tĩnh

Xét khai báo:

```java
var result = 1 + 2L;
```

Trình biên dịch xử lý theo thứ tự hợp lý sau:

1. Phân tích initializer `1 + 2L`. Literal `1` có kiểu `int`; literal `2L` có kiểu `long`.
2. Áp dụng **binary numeric promotion**: `int + long` cho biểu thức có kiểu `long`.
3. Suy luận `result` có kiểu tĩnh `long`, tương đương khai báo tường minh `long result = 1 + 2L;`.
4. Với mọi câu lệnh tiếp theo, `result` được kiểm tra như một biến `long`. Java không suy luận lại kiểu khi bạn gán hay dùng nó.

Có thể hình dung:

```text
initializer → xác định kiểu biểu thức → suy luận kiểu tĩnh của biến
                                                    ↓
                                          kiểm tra mọi cách dùng sau đó
```

Quá trình này diễn ra **lúc biên dịch**, trước khi chương trình thực thi. Ví dụ, `var x = 10;` vẫn là `int` kể cả sau đó có câu lệnh `x += 1`, `System.out.println(x)`, truyền `x` cho một phương thức nhận `long`, hoặc cộng `x` với một `long` để tạo giá trị mới.

**Quan trọng:** `var` chỉ thay phần **khai báo kiểu viết bằng tay**. Những quy tắc Java vốn áp dụng cho `int`, `long`, `double`, boxing/unboxing và chuyển kiểu vẫn áp dụng y hệt.

## 2. Các initializer số tạo ra kiểu nào?

| Khai báo | Kiểu được suy luận | Lý do |
| --- | --- | --- |
| `var a = 1;` | `int` | Literal nguyên thập phân không hậu tố `L` thuộc `int` khi vừa miền |
| `var b = 1L;` | `long` | Hậu tố `L` xác định literal `long` |
| `var c = 1.0;` | `double` | Literal dấu phẩy động không hậu tố mặc định là `double` |
| `var d = 1.0f;` | `float` | Hậu tố `f` hoặc `F` |
| `var e = (byte) 1;` | `byte` | Kiểu biểu thức sau ép kiểu là `byte` |
| `var f = (short) 1;` | `short` | Kiểu biểu thức sau ép kiểu là `short` |
| `var g = 1 + 2L;` | `long` | Nâng kiểu trong biểu thức |
| `var h = 1 + 2.0;` | `double` | Phép toán với `double` |
| `var i = 5 / 2;` | `int` | Chia số nguyên cho thương nguyên |
| `var j = 5.0 / 2;` | `double` | Có toán hạng `double` |
| `var k = true ? 1 : 2L;` | `long` | Biểu thức điều kiện áp dụng quy tắc kiểu của `?:` |
| `var m = Integer.valueOf(7);` | `Integer` | Kiểu trả về khai báo của phương thức là wrapper `Integer` |

Bảng trên cho thấy **không có “kiểu mặc định của `var`”**: kiểu phụ thuộc initializer cụ thể.

### Literal lớn và hậu tố `L`

```java
var small = 2_000_000_000;       // int
var big = 3_000_000_000L;        // long
// var invalid = 3_000_000_000; // Không biên dịch: literal decimal vượt int
```

`var` không tự tìm một kiểu đủ lớn cho literal thập phân vượt miền `int` nếu thiếu `L`. Với mục đích giữ `long`, cần viết initializer có kiểu `long` ngay từ đầu (ví dụ `3_000_000_000L`), tương tự như khai báo tường minh.

### Kiểu của biểu thức điều kiện đã được xác định trước khi chọn nhánh

```java
var value = true ? 1 : 2L;  // Kiểu long, dù nhánh được chọn cho giá trị là 1
```

Java xác định kiểu của biểu thức `?:` theo kiểu của **cả hai nhánh** và các quy tắc ngôn ngữ; không chờ chạy để suy luận từ nhánh được chọn. Chỉ nhìn vào giá trị runtime `1` không đủ kết luận biến thuộc `int`.

## 3. “Dùng sau này” không làm thay đổi kiểu đã suy luận

```java
var number = 10; // int

long wider = number;       // Hợp lệ: widening từ int sang long
long sum = number + 10L;   // Hợp lệ: biểu thức mới có kiểu long

// number = 10L;           // Lỗi: không có implicit narrowing long → int
// number = 3.14;          // Lỗi: không có implicit narrowing double → int
```

Trong `long wider = number;`, Java chỉ **mở rộng giá trị lúc gán**; kiểu gốc của `number` vẫn là `int`. Trong `number + 10L`, một biểu thức **mới** có kiểu `long` do nâng kiểu toán hạng. Biến `number` không bị đổi kiểu.

Nếu dữ liệu thực sự có thể lớn hơn miền `int`, hãy khai báo đúng từ đầu:

```java
var counter = 0L;   // long, có thể tăng đến miền long
counter += 3_000_000_000L;
```

Trình biên dịch còn kiểm tra **từng lần gán** theo kiểu đã suy luận. Nó không phân tích “tất cả các giá trị tương lai” rồi chọn kiểu phù hợp nhất.

### Tính tương đương với khai báo tường minh

Hai đoạn sau có cùng kiểu biến, cùng phép toán và cùng quy tắc chuyển kiểu:

```java
var a = 7;        // int a = 7;
var b = 3L;       // long b = 3L;
var c = a + b;    // long c = a + b;
```

Suy luận kiểu không phụ thuộc vào tên biến `a`/`b`/`c` hay sự kỳ vọng về loại giá trị của lập trình viên.

## 4. `var` không thay đổi numeric promotion

Trong Java, với nhiều toán tử số học như `+`, `-`, `*`, `/`, `%`, hai toán hạng nguyên nhỏ hơn `int` sẽ được nâng ít nhất lên `int`; nếu có `long` thì biểu thức nguyên là `long`; nếu có `float`/`double` thì áp dụng các quy tắc nâng kiểu dấu phẩy động.

```java
byte first = 10;
byte second = 20;

var sum = first + second;  // int, không phải byte
var product = first * second; // int
var diff = first - second; // int
```

Sự có mặt của `var` ở biến nhận **không ngăn numeric promotion**. Chính biểu thức `first + second` có kiểu `int`.

### Phép chia nguyên vẫn loại phần thập phân

```java
var ratio = 5 / 2;          // int, giá trị 2
var ratioLong = 5L / 2;     // long, giá trị 2L
var ratioDouble = 5.0 / 2;  // double, giá trị 2.5
```

Nếu muốn giá trị có phần lẻ, phải làm cho **ít nhất một toán hạng** thuộc kiểu số thực **trước phép chia**. Viết `var ratio = 5 / 2;` không khiến Java tự chọn `double` vì kết quả toán học chứa `.5`.

Tương tự, `var decimal = (double) (5 / 2);` suy luận `double` nhưng giá trị vẫn là `2.0` vì phần lẻ đã mất trong phép chia `int` xảy ra trước cast. Để nhận `2.5`, viết `(double) 5 / 2` hoặc `5.0 / 2`.

### Phép nhân `int` vẫn có thể tràn trước khi suy luận

```java
var x = 50_000;        // int
var y = 50_000;        // int

var wrong = x * y;       // int, -1794967296 vì vượt int
var correct = (long) x * y; // long, 2500000000
```

Java nhân `int * int` theo 32 bit, kết quả có thể tràn; `var wrong` chỉ nhận **kiểu `int` và giá trị đã tính**. `var` không tự kiểm tra overflow và không tự nâng kiểu vì kết quả cần nhiều bit hơn. Muốn phép nhân dùng `long`, ép **một toán hạng** trước phép nhân, dùng literal `long` sớm, hoặc API như `Math.multiplyFull(int,int)` khi phù hợp.

Ngược lại, `var late = (long) (x * y);` suy luận `long`, **nhưng giá trị là tích `int` đã tràn rồi mới cast**. Cần tách biệt hai câu hỏi: “biến có kiểu nào?” và “biểu thức khởi tạo đã tính đúng chưa?”.

## 5. Gán rút gọn không làm `var` đổi kiểu

Các phép gán rút gọn như `+=`, `-=`, `*=`, `/=` giữ kiểu biến đích và bao gồm chuyển đổi cần thiết theo quy tắc compound assignment. Vì vậy:

```java
var value = 10;    // int
value += 0.5;      // Hợp lệ, nhưng value vẫn là int và có giá trị 10
// value = value + 0.5; // Không biên dịch: biểu thức bên phải là double
```

Câu lệnh `value += 0.5` hoạt động tương đương theo giá trị với `value = (int) (value + 0.5)` (ngoại trừ biểu thức bên trái chỉ được đánh giá một lần). Phần `.5` bị cắt khi chuyển lại thành `int`. Suy luận kiểu từ initializer **không chạy lại** ở phép gán rút gọn.

Trường hợp tương tự:

```java
var count = 127; // int, không bị hạn chế như byte
count++;         // int

var tiny = (byte) 127; // byte
tiny++;                // byte, có thể tràn thành -128
```

Nếu muốn chuyển dần sang số thực hoặc kiểu rộng hơn theo yêu cầu mới, hãy tạo biến có kiểu phù hợp và giá trị khởi tạo hợp lệ, thay vì trông đợi biến `var` cũ “nở rộng kiểu”.

## 6. Inference nhìn vào kiểu tĩnh của phương thức và constructor

### Giá trị trả về của phương thức

```java
var rounded = Math.round(3.5);   // long: Math.round(double) trả long
var smaller = Math.round(3.5f);  // int: Math.round(float) trả int
var wrapper = Integer.valueOf(7); // Integer (wrapper), không phải primitive int
```

`var` suy luận từ **kiểu trả về được khai báo của lời gọi**, xét overload và generic inference nếu có. Nó không dựa vào “giá trị trông như số nguyên nhỏ” tại runtime. `var wrapper = Integer.valueOf(7)` mang kiểu `Integer` nên có thể tham gia boxing/unboxing khi dùng trong biểu thức số học; vẫn là một kiểu tĩnh xác định.

### Constructor và toán tử diamond (`<>`)

```java
var names = new java.util.ArrayList<String>();
names.add("Java");
// names.add(42);  // Không biên dịch: ArrayList<String>

var flexible = new java.util.ArrayList<>();
flexible.add("Java");
flexible.add(42); // Hợp lệ: ở đây suy luận ArrayList<Object>
```

Với `var flexible = new ArrayList<>()`, không có kiểu đích tường minh như `List<String>` để ràng buộc tham số generic. Trong trường hợp này type argument suy luận thành `Object`; việc thêm phần tử sau đó **không làm suy luận lại thành `String` hoặc `Integer`**.

Nếu muốn API hoặc collection có kiểu phần tử cụ thể, hãy truyền type argument trong initializer như `new ArrayList<String>()` hoặc khai báo kiểu đích rõ ràng.

Không nên xem `var` như cơ chế kiểu động kiểu JavaScript. Nó tuân theo **static type checking** của Java và kiểu không biến đổi theo runtime.

## 7. `var` dùng được ở đâu, và yêu cầu initializer nào?

`var` được hỗ trợ để suy luận kiểu **biến cục bộ** từ Java 10 (ví dụ trong phương thức, vòng lặp `for`, enhanced `for` và một số tài nguyên trong try-with-resources). Java 11 hỗ trợ `var` cho tham số lambda khi tuân theo quy tắc khai báo lambda thích hợp. `var` **không dùng thay kiểu** cho field, tham số phương thức thông thường hoặc kiểu trả về phương thức.

Ví dụ hợp lệ:

```java
var counter = 0;
for (var i = 0; i < 3; i++) {
    counter += i;
}

var numbers = new int[] {1, 2, 3};
for (var n : numbers) {
    System.out.println(n);
}
```

Các ví dụ sau được **comment lại vì chúng không biên dịch**, dùng để chỉ rõ giới hạn:

```java
// var missing;           // Sai: không có initializer
// var nullOnly = null;   // Sai: không thể suy luận kiểu từ null
// var array = {1, 2};    // Sai: array initializer trần không có target type
// var f = x -> x + 1;    // Sai: lambda không có target functional interface
// var pair1 = 1, pair2 = 2; // Sai: var không khai báo nhiều biến một lần

// class Demo {
//     var field = 1;      // Sai: không dùng var khai báo field
//     var get() { ... }   // Sai: không dùng var làm kiểu trả về
// }
```

Cách thay thế:

```java
var array = new int[] {1, 2};
java.util.function.IntUnaryOperator f = x -> x + 1;
// Hoặc: var f = (java.util.function.IntUnaryOperator) (x -> x + 1);
```

Lambda và method reference cần **target functional interface** để biết kiểu tham số/kết quả; chỉ một initializer lambda “trần” không cung cấp đủ target type cho khai báo `var`. Với `null`, nếu thực sự cần khởi tạo một reference null, dùng kiểu tường minh (`String s = null;`) thay vì `var s = null;`.

**Chú ý:** ví dụ trong mục này là các **mảnh mã ngữ cảnh**, không phải các file Java độc lập. Chương trình hoàn chỉnh để chạy được đặt ngay dưới.

## 8. Ví dụ chạy Java 17+: kiểu từ initializer và kết quả số học

Tạo tệp `VarInferenceDemo.java`:

```java
public class VarInferenceDemo {
    public static void main(String[] args) {
        var count = 1;          // int
        count += 2;
        System.out.println("count: " + count);

        var countLong = 1L;     // long
        countLong = 3_000_000_000L;
        System.out.println("countLong: " + countLong);

        var sum = count + countLong;  // long: int + long
        System.out.println("int + long: " + sum);

        var ratio = 5 / 2;           // int
        var realRatio = 5.0 / 2;     // double
        System.out.println("ratios: " + ratio + ", " + realRatio);

        var first = 50_000;         // int
        var second = 50_000;        // int
        var bad = first * second;   // int overflow
        var good = (long) first * second; // long
        System.out.println("products: " + bad + ", " + good);

        var conditional = true ? 1 : 2L; // long
        System.out.println("conditional: " + conditional);

        var list = new java.util.ArrayList<String>();
        list.add("Java");
        System.out.println("list: " + list);

        var words = new java.util.ArrayList<>(); // ArrayList<Object>
        words.add("text");
        words.add(42);
        System.out.println("diamond: " + words);

        var numbers = new int[] {1, 2};
        System.out.println("array length: " + numbers.length);

        var width = 10;           // int
        width += 0.5;             // int, vẫn là 10
        System.out.println("compound +=: " + width);
    }
}
```

Biên dịch và chạy:

```bash
javac VarInferenceDemo.java
java VarInferenceDemo
```

Stdout:

```text
count: 3
countLong: 3000000000
int + long: 3000000003
ratios: 2, 2.5
products: -1794967296, 2500000000
conditional: 1
list: [Java]
diamond: [text, 42]
array length: 2
compound +=: 10
```

**Điểm cần đọc trong output:**

1. `count` tiếp tục là `int` sau lệnh `+=`; `countLong` là `long` vì initializer `1L`.
2. `sum` là `long` do `int + long`, mặc dù biến `count` gốc vẫn là `int`.
3. `ratio` mang kiểu `int` nên phần `0.5` bị loại bỏ ở phép `5 / 2`. `realRatio` có kiểu `double` nên nhận `2.5`.
4. `bad` chứa kết quả nhân `int` bị tràn; `good` tính theo `long` vì cast nằm **trước phép nhân**.
5. `conditional` được suy luận kiểu `long` từ biểu thức có nhánh `2L` ngay khi biên dịch, kể cả lúc chương trình in `1`.
6. `list` và `words` có kiểu generic đã xác định khi khai báo; việc thêm phần tử sau đó không khiến Java suy luận lại tham số kiểu.
7. `width += 0.5` vẫn gán kết quả về `int`, vì compound assignment không sửa kiểu biến.

## 9. Khi nào nên dùng `var` và khi nào nên viết rõ kiểu?

`var` có ích khi initializer khiến kiểu rất dễ nhận ra:

```java
var total = 0L;
var ratio = (double) numerator / denominator;
var names = new java.util.ArrayList<String>();
```

Ví dụ thứ hai là mảnh mã trong phương thức: `numerator` và `denominator` cần được khai báo trước. Cast `(double)` giúp thể hiện ý định chia số thực ngay trong initializer, tránh suy luận nhầm ý định của `var`.

Khai báo kiểu tường minh thường rõ hơn khi **miền số và độ chính xác quan trọng**, ví dụ:

```java
long transactionCount = 0L;
double probability = 0.0;
int maxRetries = 3;
```

Không phải vì `var` kém an toàn; hai cách vẫn chịu cùng quy tắc của trình biên dịch. Kiểu tường minh giúp người đọc nhận ngay hợp đồng dữ liệu, nhất là nếu initializer là biểu thức khó đọc hoặc lời gọi generic/overload phức tạp.

Một số nguyên tắc thực hành:

- **Định hình kiểu ngay ở initializer.** Muốn `long`, dùng `0L` hoặc biểu thức `long`; muốn chia số thực, dùng literal/ép kiểu số thực trước phép chia.
- **Đánh giá kiểu trung gian**, đặc biệt với `int * int`, `int / int` và các chuỗi phép toán.
- **Giữ initializer rõ ràng**, tránh tin vào giá trị thực tế khi runtime để đoán kiểu.
- **Chọn đúng kiểu collection ngay khi tạo**, vì `var` kết hợp diamond `<>` có thể suy luận `Object` nếu không có đủ ràng buộc.
- **Dùng tên biến thể hiện đơn vị/nghĩa**, như `timeoutMillis`, `priceCents`, `ratio`; kiểu tĩnh và tên rõ nghĩa phối hợp giúp tránh sai sót.

## 10. Những nhầm lẫn thường gặp

1. **“`var` là kiểu động, biến có thể đổi thành `long` khi được gán số lớn.”** Sai: `var x = 1` cố định `x` là `int` lúc biên dịch.
2. **“Java nhìn lệnh gán sau để suy luận kiểu `var`.”** Sai: chỉ initializer tại khai báo quyết định kiểu suy luận.
3. **“`var` tự tránh tràn `int` vì không khai báo kiểu.”** Sai: biểu thức `int * int` vẫn tính theo `int`.
4. **“`var r = 5 / 2` sẽ thành `double` vì 2.5 là kết quả toán học.”** Sai: `5 / 2` là `int` và giá trị 2.
5. **“`var v = (long) (a * b)` chắc chắn giữ tích.”** Sai: phép nhân `int` có thể đã tràn trước cast.
6. **“Sau `x += 0.5`, biến `x` đổi sang `double`.”** Sai: compound assignment chuyển kết quả về kiểu tĩnh `x`, có thể mất phần lẻ.
7. **“`var list = new ArrayList<>()` tự suy luận `String` vì lần đầu thêm chuỗi.”** Sai: type argument không được tái suy luận từ lời gọi `add` về sau.
8. **“`var x = null` hợp lệ vì Java có thể chọn `Object`.”** Sai: null initializer trần không cung cấp kiểu suy luận phù hợp.
9. **“`var f = x -> x + 1` có thể suy ra functional interface từ thân lambda.”** Sai: lambda cần target type.
10. **“`var` thay được mọi khai báo kiểu trong class.”** Sai: `var` có phạm vi áp dụng theo quy tắc ngôn ngữ, chủ yếu khai báo cục bộ có initializer và một số vị trí được hỗ trợ cụ thể.
11. **“Có `var` thì `long a = 1 + 2L` và `var a = 1 + 2L` là hai kiểu khác nhau.”** Sai: trong ví dụ này cả hai biến đều có kiểu `long`.
12. **“Giá trị `conditional` in ra 1 nên chắc chắn kiểu của nó là `int`.”** Sai: `true ? 1 : 2L` có kiểu `long` do quy tắc biểu thức điều kiện.

## 11. Tự kiểm tra

- `var n = 100; n = 100L;` có biên dịch không? **Không**: `n` là `int` từ initializer `100`, không thể gán `long` trực tiếp.
- `var n = 100L; n = 200;` có biên dịch không? **Có**: giá trị `int` 200 được mở rộng thành `long` khi gán.
- `var x = 7 / 2;` có kiểu và giá trị gì? **`int` và 3**, vì chia nguyên cắt phần lẻ về 0.
- `var y = 7.0 / 2;` có kiểu và giá trị gì? **`double` và 3.5**.
- `var p = 50_000 * 50_000;` có kiểu gì? **`int`**, có thể đã tràn trước khi lưu. Muốn `long` đúng giá trị, viết `var p = 50_000L * 50_000;`.
- `var z = true ? 1 : 2L;` có kiểu gì? **`long`**, do Java xét kiểu cả biểu thức điều kiện.
- `var words = new ArrayList<>();` có đổi thành `ArrayList<String>` sau khi gọi `words.add("hi")` không? **Không**.
- Khi bắt buộc có giới hạn kiểu `long` để tránh vượt miền `int`, việc đặt chữ `L` vào initializer có ý nghĩa gì? **Nó xác định kiểu literal và có thể thay đổi kiểu toàn bộ biểu thức trước khi phép toán diễn ra**.

**Ghi nhớ:** `var` để **trình biên dịch viết giúp kiểu biến**, và kiểu ấy được xác định **một lần duy nhất từ initializer**. `var` không xem trước cách dùng ở các dòng sau và không sửa các quy tắc numeric promotion, overflow, division hay assignment của Java. Hãy đặt kiểu mong muốn vào **initializer/kiểu toán hạng trước phép tính**, rồi kiểm tra đúng miền giá trị.
