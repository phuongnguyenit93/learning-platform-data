# Unboxing trong gán, phép toán và lời gọi phương thức trong Java

**Unboxing** là phép chuyển một giá trị từ **wrapper object** sang **kiểu nguyên thủy (primitive)** tương ứng. Ví dụ, Java có thể chuyển `Integer` thành `int`, `Long` thành `long` và `Double` thành `double` một cách ngầm định khi ngữ cảnh yêu cầu giá trị primitive.

```java
Integer boxed = 12; // Integer object
int number = boxed; // unboxing: Integer -> int

Integer a = 7, b = 5;
int sum = a + b;    // unboxing cả a và b, sau đó cộng int

static int twice(int x) {
    return x * 2;
}
// twice(boxed) gọi được: Integer -> int trước khi truyền đối số.
```

*Chú ý:* `twice` ở trên là **phương thức minh họa cần đặt trong class**. Bài sẽ có chương trình hoàn chỉnh chạy được ở phần sau.

Unboxing không phải phép biến đổi vô hại với mọi đầu vào: **unbox một wrapper có giá trị `null` sẽ ném `NullPointerException` khi thực hiện**. Và unboxing không làm thay đổi các quy tắc như nâng kiểu số học, overflow, phép chia nguyên hoặc chọn phương thức overload.

## 1. Primitive khác wrapper như thế nào?

Java có các cặp primitive và wrapper:

| Primitive | Wrapper | Phương thức lấy primitive điển hình |
| --- | --- | --- |
| `boolean` | `Boolean` | `booleanValue()` |
| `byte` | `Byte` | `byteValue()` |
| `short` | `Short` | `shortValue()` |
| `char` | `Character` | `charValue()` |
| `int` | `Integer` | `intValue()` |
| `long` | `Long` | `longValue()` |
| `float` | `Float` | `floatValue()` |
| `double` | `Double` | `doubleValue()` |

- **Primitive** chứa giá trị thuộc kiểu đó, ví dụ `int` có giá trị số nguyên 32 bit.
- **Wrapper** là kiểu tham chiếu, ví dụ `Integer` là đối tượng chứa giá trị `int`. Một biến tham chiếu wrapper có thể là `null`.
- **Boxing** là chiều ngược lại: `int → Integer`, thường xảy ra khi gán primitive vào biến wrapper hoặc đưa vào collection.
- **Unboxing** là chiều `Integer → int`, được chèn tự động khi Java cần một primitive.

```java
int primitive = 10;
Integer boxed = primitive; // boxing

int again = boxed;         // unboxing
```

Không nên đồng nhất **đối tượng** wrapper và **giá trị primitive**. Unboxing đọc giá trị primitive từ wrapper; nếu wrapper không tham chiếu đến một đối tượng nào (`null`), không có giá trị để đọc.

## 2. Unboxing trong phép gán (assignment)

Một kiểu dùng phổ biến là **gán wrapper cho biến primitive tương ứng**:

```java
Integer boxedInt = 42;
int primitiveInt = boxedInt;  // Integer -> int

Double boxedDouble = 3.5;
double primitiveDouble = boxedDouble; // Double -> double

Boolean enabled = Boolean.TRUE;
boolean flag = enabled; // Boolean -> boolean
```

Đây là các **assignment contexts** nơi Java có thể thực hiện unboxing conversion. Kết quả sau unboxing phải tuân theo các quy tắc kiểu của biến đích.

### Unboxing rồi widening primitive

Java còn cho phép **unboxing rồi mở rộng primitive**, ví dụ `Integer → int → long`:

```java
Integer boxed = 12;
long wider = boxed;    // Integer -> int -> long, giá trị 12L

Byte small = 10;
int number = small;    // Byte -> byte -> int
double real = boxed;   // Integer -> int -> double
```

Tuy nhiên, không suy luận rằng Java tự thực hiện mọi chuỗi chuyển kiểu:

```java
Integer source = 12;
// Long invalid = source; // Lỗi biên dịch: không có Integer -> int -> long -> Long tự động

long widened = source;  // Hợp lệ: unboxing rồi widening primitive
Long target = (long) source; // Hợp lệ: cast sang long, sau đó boxing thành Long
```

Chuyển `Integer` sang `Long` không phải một phép unboxing trực tiếp. Nếu cần `Long`, hãy chuyển sang `long` một cách rõ ràng rồi boxing.

### Unboxing `null` khi gán

```java
Integer count = null;
// int value = count; // Biên dịch được nhưng NPE khi thực hiện
```

Trình biên dịch không từ chối chỉ vì một wrapper **có thể** null. Nhưng khi chạy tới phép gán primitive, quá trình lấy `intValue()` trên tham chiếu null dẫn đến `NullPointerException`.

Với giá trị có thể thiếu, nên kiểm tra và xử lý rõ theo hợp đồng dữ liệu:

```java
Integer count = null;
int safe = count == null ? 0 : count;  // Chỉ dùng 0 nếu nghiệp vụ quy định
```

Biểu thức điều kiện này không đánh giá nhánh `count` khi điều kiện `count == null` đúng, nên tránh unboxing ở trường hợp null. **Không tự thay null bằng 0** nếu 0 cũng là dữ liệu có ý nghĩa khác; có thể chọn từ chối, báo lỗi hoặc giữ kiểu wrapper đến khi cần.

## 3. Unboxing trong toán tử số học

Các toán tử số học `+`, `-`, `*`, `/`, `%` hoạt động trên các giá trị primitive số học. Khi toán hạng là wrapper kiểu số, Java có thể **unbox rồi áp dụng numeric promotion**:

```java
Integer a = 7;
Integer b = 5;

int sum = a + b;          // 12
int difference = a - b;   // 2
int product = a * b;      // 35
int quotient = a / b;     // 1, phép chia nguyên
int remainder = a % b;    // 2
```

`a` và `b` vẫn là các biến `Integer`; chỉ giá trị của chúng được chuyển thành `int` trong **biểu thức mới**. Kết quả `a + b` có kiểu `int`, **không phải `Integer` chỉ vì toán hạng được khai báo là `Integer`**.

### Wrapper nhỏ hơn `int` vẫn chịu numeric promotion

```java
Byte first = 10, second = 20;
int sum = first + second; // Byte -> byte rồi nâng lên int
```

Các toán hạng `byte` và `short` thường được nâng ít nhất thành `int` trong phép toán nhị nguyên. Nếu một toán hạng là `Long` và bên kia là `Integer`, sau unboxing phép toán sẽ dùng `long`:

```java
Integer i = 2;
Long l = 3L;
long total = i + l; // int + long -> long
```

Không có nghĩa wrapper tự được mở rộng về object wrapper khác; việc nâng kiểu xảy ra trong **biểu thức primitive**.

### Unboxing không bảo vệ khỏi overflow hoặc mất phần lẻ

```java
Integer a = 50_000;
Integer b = 50_000;

int wrong = a * b;          // -1794967296: nhân int đã tràn
long alsoWrong = a * b;     // Mở rộng kết quả int đã tràn
long correct = (long) a * b; // 2500000000: unbox a, cast long trước phép nhân

Integer seven = 7;
Integer three = 3;
int q = seven / three;       // 2, chia nguyên cắt phần phân số
double real = (double) seven / three; // Khoảng 2.3333333333333335
```

Kết quả phụ thuộc **kiểu primitive sau unboxing và chuyển kiểu**, không phụ thuộc vào việc ta viết wrapper hay primitive ở khai báo ban đầu. Nếu cần phát hiện overflow thay vì nhận giá trị tràn `int`/`long`, cân nhắc `Math.multiplyExact` hoặc `Math.addExact` với overload và kiểu đối số phù hợp.

## 4. Toán tử tăng giảm, gán rút gọn và boxing trở lại

Các lệnh như `++`, `--`, `+=` có thể đưa wrapper qua chu trình **unbox → tính toán → boxing lại**:

```java
Integer count = 5;
count++;     // lấy int 5, cộng 1, tạo giá trị Integer 6 để gán lại
count += 2;  // lấy int 6, cộng 2, boxing trở lại thành Integer 8
```

Vì wrapper là reference type, câu lệnh không làm thay đổi trực tiếp nội dung của một đối tượng `Integer` bất biến (*immutable*). Nó **gán lại tham chiếu biến** tới giá trị wrapper sau boxing.

```java
Integer counter = Integer.MAX_VALUE;
counter++; // Integer.MIN_VALUE do phép cộng int bị tràn
```

Unboxing rồi boxing lại **không tạo kiểm tra tràn số**. Nếu `counter` là null, `counter++` và `counter += 1` đều cần unbox để tính và gây `NullPointerException`.

Ngoài ra, `count += 0.5` không làm `Integer` biến thành `Double`: compound assignment có các chuyển kiểu tương ứng về loại primitive của `count` trước khi boxing lại. Đừng dùng `+=` để “tự nâng kiểu” một wrapper.

## 5. Unboxing khi so sánh: `==` cần xét kiểu hai bên

Trường hợp này thường gây lỗi nhiều hơn các phép cộng vì `==` có thể là **so sánh tham chiếu** hoặc **so sánh giá trị primitive** tùy kiểu toán hạng:

```java
Integer left = Integer.valueOf(1000);
Integer right = Integer.valueOf(1000);

boolean references = (left == right); // So sánh tham chiếu; đừng dùng để so giá trị
boolean values = left.equals(right);  // So sánh giá trị wrapper: true

int primitive = 1000;
boolean mixed = (left == primitive);   // Unbox left, so sánh int: true
```

**Hai tham chiếu `Integer` trong `left == right` không tự unbox** chỉ vì cùng là wrapper. Khi một bên là primitive số và bên kia là wrapper số, Java áp dụng các quy tắc số học và có thể unbox wrapper để so sánh.

Cũng vì vậy:

```java
Integer missing = null;
boolean absent = (missing == null); // true: kiểm tra tham chiếu, an toàn
// boolean isZero = (missing == 0);  // Biên dịch, nhưng NPE khi so sánh
```

Các toán tử quan hệ `<`, `<=`, `>`, `>=` trên wrapper số cần so sánh giá trị số học, nên sẽ thực hiện unboxing:

```java
Integer low = 3, high = 7;
boolean ordered = low < high; // true, unbox cả hai
```

Với `null`, quan hệ thứ tự này gây NPE tại runtime. Viết `missing != null && missing > 0` để **short-circuit** bảo vệ phép unboxing ở vế phải. Không dùng `missing > 0 && missing != null` vì vế trái đã unbox trước.

## 6. Unboxing khi gọi phương thức (method invocation)

Java có thể chuyển wrapper thành primitive để phù hợp kiểu tham số:

```java
static int twice(int value) {
    return value * 2;
}

// Trong phương thức khác:
Integer number = 12;
int answer = twice(number); // Integer -> int; kết quả 24
```

Phương thức `twice` yêu cầu `int`, do đó Java unbox `number` khi đánh giá đối số. Nếu `number == null`, lời gọi không thể cung cấp giá trị `int`, và quá trình chuẩn bị đối số ném NPE **trước khi thân phương thức `twice` được chạy**.

Unboxing có thể kết hợp với **widening primitive** cho tham số rộng hơn:

```java
static void acceptLong(long value) {
    System.out.println(value);
}

// Integer boxed = 12;
// acceptLong(boxed); // Integer -> int -> long
```

Đây là mảnh mã minh họa, không phải chương trình độc lập. Sự tương thích kiểu được kiểm tra lúc biên dịch, còn việc đọc giá trị wrapper có thể gây NPE ở runtime.

### Overload resolution: không phải cứ có overload primitive là Java unbox

Nếu nhiều phương thức cùng tên, Java chọn overload theo **các giai đoạn áp dụng được của method invocation**: trước hết các lời gọi không cần boxing/unboxing (strict invocation), sau đó mới xét các chuyển đổi rộng hơn, rồi varargs.

Ví dụ:

```java
static String choose(int value)  { return "int"; }
static String choose(long value) { return "long"; }

Integer boxed = 12;
// choose(boxed) -> "int": cần unbox; overload int cụ thể hơn long
```

Nhưng với các overload:

```java
static String route(long value)     { return "long"; }
static String route(Integer value)  { return "Integer"; }

Integer boxed = 12;
// route(boxed) -> "Integer": truyền tham chiếu không cần unbox
// route(7)     -> "long": widening int -> long được xét trước boxing int -> Integer
```

Và có một tình huống tinh tế:

```java
static String view(Object value) { return "Object"; }
static String view(int value)    { return "int"; }

Integer boxed = 12;
// view(boxed) -> "Object": Integer -> Object là widening reference
//                nên được chọn ở giai đoạn strict trước khi xét unboxing int
```

**Vì vậy không thể khẳng định “overload nhận primitive luôn được ưu tiên” hoặc “Java luôn unbox khi có thể”.** Phải xem tập overload cùng giai đoạn chuyển đổi áp dụng được. Khi đọc code khó, dùng kiểu tham số tường minh, tránh overload quá nhiều giữa primitive/wrapper nếu chúng dẫn tới ngữ nghĩa khác nhau.

### Null cũng phụ thuộc overload nào được chọn

```java
Integer missing = null;

// route(missing) có thể gọi overload route(Integer) mà không unbox.
// twice(missing) bắt buộc unbox vì tham số là int -> NPE.
```

Một tham chiếu null **không tự gây NPE khi được truyền**. NPE xuất hiện khi biểu thức hoặc tham số thực sự đòi primitive và phải unbox null.

## 7. Thứ tự đánh giá và thời điểm NPE

Java không “kiểm tra wrapper null từ xa” khi biên dịch. Nó đánh giá biểu thức và chỉ unbox khi cần giá trị primitive:

| Ngữ cảnh | Có cần unbox không? | Nếu wrapper null |
| --- | --- | --- |
| `int n = boxed;` | Có | NPE |
| `long n = boxed;` với `boxed` là `Integer` | Có, rồi widening | NPE |
| `int x = boxed + 1;` | Có | NPE |
| `boxed > 0` | Có | NPE |
| `boxed == 0` | Có | NPE |
| `boxed == null` | Không, so sánh tham chiếu | Không NPE vì phép so sánh này |
| `boxed == anotherBoxed` với hai `Integer` | Không, so sánh tham chiếu | Không NPE chỉ vì một bên null |
| Gọi `twice(boxed)` với `twice(int)` | Có | NPE khi chuẩn bị đối số |
| Gọi `route(boxed)` khi chọn `route(Integer)` | Không | Có thể truyền null bình thường |
| `boxed++` / `boxed += 1` | Có và boxing lại | NPE |

Một trường hợp nữa là biểu thức điều kiện có một nhánh primitive:

```java
Integer maybe = null;
boolean useBoxed = false;
int value = useBoxed ? maybe : 0; // 0, không đánh giá nhánh maybe
```

Nếu `useBoxed` là `true`, nhánh `maybe` phải cung cấp giá trị `int` và sẽ NPE khi null. Trình biên dịch xác định kiểu biểu thức theo cả hai nhánh, nhưng **chỉ nhánh được chọn được đánh giá tại runtime**.

Trong lời gọi nhiều đối số, các biểu thức đối số được đánh giá theo thứ tự của Java; nếu unboxing một đối số ném NPE, thân phương thức không chạy. Đây là lý do chỉ đặt `Objects.requireNonNull` bên trong một phương thức nhận `int` **không thể bảo vệ** trước NPE do unboxing ở phía caller; tham số `int` đã phải được tạo trước khi vào phương thức.

## 8. Java 17+: ví dụ hoàn chỉnh đã kiểm chứng

Lưu vào tệp `UnboxingContextsDemo.java`:

```java
public class UnboxingContextsDemo {
    static String choose(int value) { return "int"; }
    static String choose(long value) { return "long"; }

    static String route(long value) { return "long"; }
    static String route(Integer value) { return "Integer"; }

    static String view(Object value) { return "Object"; }
    static String view(int value) { return "int"; }

    static int twice(int value) { return value * 2; }

    public static void main(String[] args) {
        Integer boxed = 12;
        int assigned = boxed;
        long widened = boxed;
        System.out.println("assignment: " + assigned + ", long: " + widened);

        Integer a = 7, b = 5;
        System.out.println("sum: " + (a + b) + ", product: " + (a * b));
        System.out.println("comparison: " + (a > b));

        System.out.println("choose(boxed): " + choose(boxed));
        System.out.println("route(boxed): " + route(boxed));
        System.out.println("route(7): " + route(7));
        System.out.println("view(boxed): " + view(boxed));
        System.out.println("twice(boxed): " + twice(boxed));

        Integer counter = Integer.MAX_VALUE;
        counter++;
        System.out.println("counter after ++: " + counter);

        Integer absent = null;
        System.out.println("absent == null: " + (absent == null));
        System.out.println("route(absent): " + route(absent));

        try {
            int x = absent;
        } catch (NullPointerException ex) {
            System.out.println("assignment null: NPE");
        }
        try {
            int x = absent + 1;
        } catch (NullPointerException ex) {
            System.out.println("arithmetic null: NPE");
        }
        try {
            boolean x = absent == 0;
        } catch (NullPointerException ex) {
            System.out.println("comparison null: NPE");
        }
        try {
            twice(absent);
        } catch (NullPointerException ex) {
            System.out.println("invocation null: NPE");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac UnboxingContextsDemo.java
java UnboxingContextsDemo
```

Stdout:

```text
assignment: 12, long: 12
sum: 12, product: 35
comparison: true
choose(boxed): int
route(boxed): Integer
route(7): long
view(boxed): Object
twice(boxed): 24
counter after ++: -2147483648
absent == null: true
route(absent): Integer
assignment null: NPE
arithmetic null: NPE
comparison null: NPE
invocation null: NPE
```

**Đọc kết quả:**

- Gán `Integer` cho `int` hoặc `long` minh họa **unboxing**, và với `long` có bước mở rộng sau unboxing.
- Phép `a + b`, `a * b`, `a > b` buộc lấy các giá trị `int` để tính.
- `choose`, `route` và `view` chứng minh lựa chọn overload **không chỉ dựa vào “primitive hay wrapper”**, mà theo giai đoạn chuyển đổi phù hợp.
- `counter++` dùng `int` ở bên trong nên vẫn tràn và boxing lại.
- `absent == null` cùng `route(absent)` không yêu cầu unboxing; bốn tình huống cuối bắt buộc unboxing và gây NPE được bắt riêng.

## 9. Unboxing trong collection và generic

Generics Java dùng reference type cho type argument, nên `List<int>` không hợp lệ; thường dùng `List<Integer>`. Khi thêm một `int`, Java boxing; khi lấy ra để tính với `int`, Java unboxing:

```java
java.util.List<Integer> scores = new java.util.ArrayList<>();
scores.add(10);    // int -> Integer (boxing)
scores.add(20);

int sum = 0;
for (Integer score : scores) {
    sum += score;   // Integer -> int (unboxing)
}
```

Nếu collection chứa `null`, vòng lặp `sum += score` có thể ném NPE. Điều này không xảy ra chỉ vì `scores.add(null)` được gọi; lỗi xảy ra khi dữ liệu `null` **được dùng trong primitive context**.

Với `Map<String, Integer>`, `map.get(key)` có thể trả `null` nếu không có key (hoặc nếu key được gán null). Đoạn `int n = map.get(key);` dễ phát sinh NPE. Tùy nghiệp vụ, có thể kiểm tra `containsKey`, dùng `getOrDefault` với default phù hợp, hoặc tiếp tục giữ `Integer` để biểu diễn giá trị không có.

**Lưu ý hiệu năng:** boxing/unboxing có thể tạo hoặc truy cập wrapper và tăng chi phí trong những vòng lặp lớn hoặc cấu trúc dữ liệu nhiều phần tử. Nhưng đừng tối ưu bằng cách bỏ mọi wrapper nếu cần nullable/generic. Khi lưu số lượng lớn dữ liệu chỉ cần primitive, mảng `int[]` hoặc `double[]` là lựa chọn cần cân nhắc.

## 10. `var` và wrapper: kiểu có thể nhìn không rõ

`var` suy luận kiểu từ biểu thức khởi tạo, không dựa vào cách dùng sau đó:

```java
var wrapper = Integer.valueOf(5); // Integer
var primitive = wrapper + 1;       // int vì unboxing rồi phép cộng int
var another = wrapper;             // Integer, giữ kiểu tĩnh của expression
```

Vì thế `var` không tự né NPE: `var x = wrapper + 1` vẫn phải unbox `wrapper` khi đánh giá initializer. Nếu `wrapper` null, phép cộng ném NPE **trước khi `x` nhận được giá trị**.

Đừng nhầm phương thức trả `Integer` với phương thức trả `int` chỉ vì khi chạy chúng đều in cùng chữ số. Trong những đoạn xử lý nhiều overload/generic, có thể viết kiểu tường minh để người đọc biết **giá trị có thể null** hay không.

## 11. Cách tránh lỗi unboxing và viết API rõ nghĩa

### Xác định có cho phép thiếu dữ liệu hay không

Nếu `null` có nghĩa là “chưa biết”, “không có” hoặc “chưa nhập”, dùng wrapper ở lớp dữ liệu có thể là hợp lý. Nhưng khi chuyển sang phép toán, cần quyết định:

- **Từ chối dữ liệu thiếu:** ví dụ `Objects.requireNonNull(value, "value")`, rồi thực hiện phép toán. NPE khi ấy được kiểm soát có thông điệp rõ ràng.
- **Dùng giá trị mặc định:** chỉ khi nghiệp vụ định nghĩa default, như số lượng thiếu được tính 0.
- **Giữ trạng thái không có giá trị:** không unbox cho đến khi nhánh xử lý phù hợp hoặc dùng mô hình kiểu dữ liệu diễn đạt sự thiếu vắng.

```java
Integer maybe = null;

if (maybe != null && maybe > 0) {
    System.out.println("Positive");
}
```

Toán tử `&&` đánh giá ngắn mạch: khi `maybe != null` là false, vế phải **không thực hiện**, nên không unbox null.

### Thiết kế method signature giảm bất ngờ

Nếu một hàm luôn yêu cầu số nguyên hợp lệ và không cho phép thiếu, một tham số `int` cho thấy rõ hợp đồng ấy. Nhưng lời gọi truyền `Integer` vẫn có thể NPE do unboxing ở phía caller; nên xác thực dữ liệu trước khi gọi.

Nếu phương thức thực sự cho phép null, dùng `Integer` và xử lý null **trong phương thức**. Khi dùng overload giữa `int`, `long`, `Integer` và `Object`, nên kiểm tra resolution với các trường hợp primitive, wrapper và null; nếu ý nghĩa khác nhau quá nhiều, cân nhắc tên hàm khác nhau hoặc cast tường minh để tránh khó đọc.

### Không dùng `==` giữa hai wrapper để so nội dung số

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

// a == b: so sánh identity, không nên dùng kiểm tra bằng số.
boolean equalValues = a.equals(b); // true
```

Chọn `Objects.equals(a, b)` nếu cả hai có thể null và muốn null bằng null; hoặc unbox sau khi xác minh không null để dùng `==` primitive. Với `Float`/`Double`, `equals` có ngữ nghĩa NaN và signed zero khác phép `==` primitive, nên cần xác định quy tắc mong muốn.

### Ưu tiên chuyển đổi tường minh nếu miền quan trọng

Nếu `Integer` tham gia phép nhân có nguy cơ vượt 32 bit, unbox rồi nâng một toán hạng sang `long` **trước phép nhân**, chẳng hạn `(long) a * b`; khi cần kiểm tra overflow, dùng `Math.multiplyExact` với overload `long` phù hợp. Không cho rằng boxing/unboxing có cơ chế tự phát hiện lỗi tràn.

## 12. Các nhầm lẫn thường gặp

1. **“Wrapper chỉ là primitive có thể null, Java luôn unbox ngay khi tạo.”** Sai: unboxing xảy ra khi ngữ cảnh yêu cầu giá trị primitive, không phải ngay khi tham chiếu wrapper xuất hiện.
2. **“`Integer a = null; int b = a;` không biên dịch.”** Sai: có thể biên dịch, nhưng unboxing `null` gây NPE khi chạy.
3. **“`Integer + Integer` luôn tạo `Integer` mới.”** Sai: toán tử số học unbox toán hạng, áp dụng numeric promotion; kết quả có kiểu primitive, trừ khi được boxing sau đó ở ngữ cảnh gán/return phù hợp.
4. **“`Integer * Integer` an toàn khỏi overflow.”** Sai: sau unboxing vẫn là phép nhân `int` nếu hai bên là `Integer`.
5. **“`Integer a = null; a == null` ném NPE.”** Sai: đây là so sánh tham chiếu an toàn; `a == 0` mới cần unbox.
6. **“`a == b` với hai `Integer` luôn so giá trị số.”** Sai: thường là so tham chiếu, không tự unbox hai bên.
7. **“Overload nhận primitive luôn thắng overload nhận wrapper.”** Sai: overload `route(Integer)` được chọn với đối số `Integer` phù hợp mà không cần unboxing.
8. **“Overload primitive luôn thắng `Object` nếu đối số là `Integer`.”** Sai: widening reference sang `Object` có thể được xét ở giai đoạn strict trước khi unboxing.
9. **“Một tham chiếu `null` truyền vào bất kỳ phương thức nào cũng gây NPE.”** Sai: chỉ khi chuẩn bị đối số/thân phương thức cần dùng primitive hoặc có dereference không an toàn.
10. **“`counter++` trên `Integer` thay đổi object hiện có.”** Sai: wrapper bất biến; phép toán unbox và boxing rồi gán lại biến.
11. **“`Long target = integerWrapper` hợp lệ vì `long x = integerWrapper` hợp lệ.”** Sai: `Integer → int → long` có thể đi vào primitive `long`, nhưng không tự nối thêm boxing sang `Long` trong assignment đó.
12. **“`List<Integer>` đảm bảo không có `null` nên lấy ra gán `int` luôn an toàn.”** Sai: list có thể chứa null; unboxing ở phép gán/tính sẽ ném NPE.

## 13. Tự kiểm tra

**1. `Integer x = 8; int y = x;` xảy ra gì?** → Unboxing `Integer → int` khi gán, `y` bằng 8.

**2. `Integer x = 8; long y = x;` có hợp lệ không?** → Có: unbox `int` rồi widen thành `long`.

**3. `Integer a = 5, b = 6;` kiểu của `a + b` là gì?** → `int`, không phải `Integer`.

**4. `Integer n = null;` biểu thức nào an toàn hơn để kiểm tra null: `n == null` hay `n == 0`?** → `n == null`; biểu thức còn lại cần unbox và gây NPE.

**5. Nếu có cả `route(long)` và `route(Integer)`, `route(7)` gọi phiên bản nào?** → `route(long)` vì widening primitive `int → long` được xét trước boxing `int → Integer`. Còn `route(Integer.valueOf(7))` chọn `route(Integer)`.

**6. Nếu `view(Object)` và `view(int)` cùng tồn tại, truyền `Integer` chọn overload nào?** → `view(Object)` qua widening reference ở giai đoạn strict trước khi xét unboxing.

**7. `Integer counter = Integer.MAX_VALUE; counter++;` cho gì?** → `Integer.MIN_VALUE` do phép cộng primitive `int` tràn, rồi boxing lại.

**8. Trong `int v = map.get(key);` với `Map<String,Integer>`, rủi ro nào cần kiểm tra?** → `get` có thể trả null, unboxing lúc gán `int` gây NPE.

**Ghi nhớ:** Unboxing là **đưa wrapper về primitive khi ngữ cảnh cần giá trị**, thường thấy ở **gán**, **toán tử số học/so sánh** và **đối số phương thức**. Java có thể kết hợp unboxing với widening primitive và boxing lại sau một phép toán, nhưng **không tự chuyển mọi wrapper sang wrapper khác**. Kiểu của biểu thức, overload được chọn và nguy cơ `NullPointerException` phải được xét theo **ngữ cảnh cụ thể**, không dựa trên việc hai biến in ra cùng một con số.
