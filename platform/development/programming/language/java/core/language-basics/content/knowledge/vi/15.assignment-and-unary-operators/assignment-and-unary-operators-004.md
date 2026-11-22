# Chuyển kiểu ngầm định trong phép gán kết hợp — Java 17+

## 1. Bài toán: vì sao `b += 10` được mà `b = b + 10` không được?

Trong Java, các toán tử gán kết hợp (*compound assignment*) như `+=`, `-=`, `*=`, `/=` vừa tính toán vừa cập nhật biến ở vế trái. Với kiểu số nguyên nhỏ, chúng thực hiện **chuyển đổi về kiểu đích một cách ngầm định**, kể cả khi phép tính trung gian được nâng lên kiểu lớn hơn.

~~~java
byte b = 120;
b += 10; // Biên dịch được
System.out.println(b); // -126
~~~

Trong khi đó:

~~~java
byte b = 120;
// b = b + 10; // Lỗi compile: byte + int tạo int, không tự gán vào byte
~~~

**Vì sao `-126`?** Java nâng `b` thành `int`, tính `120 + 10 = 130`, rồi thu hẹp về `byte` 8 bit. Giá trị 130 vượt `Byte.MAX_VALUE` (127) nên kết quả lưu thành -126. Compiler **không** tự từ chối mất dữ liệu ở phép `+=` này.

Bài học cốt lõi: **cú pháp gán kết hợp có quy tắc chuyển kiểu khác phép gán `=` thông thường**. Dùng ngắn hơn không có nghĩa an toàn hơn.

## 2. Công thức ngữ nghĩa của phép gán kết hợp

Với một biến số nguyên thủy `x` có kiểu `T`, có thể hình dung:

~~~java
x op= y;
~~~

gần tương đương:

~~~java
x = (T) (x op y);
~~~

**Ngoại lệ quan trọng:** vế trái của `op=` **chỉ được đánh giá một lần**; thay máy móc bằng biểu thức dài `x = (T)(x op y)` có thể thay đổi side effect nếu `x` là field hoặc phần tử mảng truy cập qua biểu thức.

Với toán hạng số học nguyên thủy, thứ tự ý nghĩa cơ bản là:

1. Xác định nơi chứa giá trị ở vế trái, lấy giá trị hiện tại.
2. Đánh giá toán hạng phải theo quy tắc thứ tự của Java.
3. Thực hiện phép toán `op` với **numeric promotion** khi cần.
4. Chuyển kết quả về **kiểu của vế trái**, kể cả narrowing.
5. Gán lại giá trị đã chuyển; biểu thức gán kết hợp cho giá trị sau cập nhật.

~~~mermaid
flowchart TD
    A["byte b = 120"] --> B["b += 10"]
    B --> C["Nâng byte thành int"]
    C --> D["120 + 10 = 130, kiểu int"]
    D --> E["Thu hẹp int về byte"]
    E --> F["b trở thành -126"]
~~~

Công thức trên minh họa tốt cho **kiểu nguyên thủy số**. Với `String +=`, toán tử bitwise boolean hoặc wrapper, có thêm quy tắc nối chuỗi, unboxing/boxing hoặc phép toán tương ứng; không diễn giải chúng như một phép cast số duy nhất.

## 3. So sánh gán thường và gán kết hợp

| Cú pháp | Hành vi | Ví dụ |
|---|---|---|
| `x = y` | Vế phải phải tương thích qua *assignment conversion* | `int x = 3;` |
| `x += y` | Cộng/nối rồi cập nhật; với primitive số có narrowing ngầm về kiểu đích | `byte b = 120; b += 10;` |
| `x -= y` | Trừ rồi cập nhật, có thể narrowing | `short s = 5; s -= 2;` |
| `x *= y` | Nhân rồi cập nhật, có thể overflow/narrowing | `int n = 5; n *= 3;` |
| `x /= y` | Chia rồi cập nhật; với số nguyên vẫn cắt thương về 0 | `int n = 7; n /= 2;` |
| `x %= y` | Lấy dư rồi cập nhật | `int n = 7; n %= 2;` |
| `x <<= y`, `>>=`, `>>>=` | Dịch bit rồi gán | `int bits = 1; bits <<= 2;` |
| `x &= y`, `^=`, `|=` | Phép bitwise hoặc boolean phù hợp kiểu | `int mask = 7; mask &= 3;` |

**Không** có toán tử `&&=` hoặc `||=` trong Java. Với boolean, `&=` và `|=` **không áp dụng short-circuit như `&&`/`||`**; vế phải vẫn được đánh giá.

## 4. Binary numeric promotion và narrowing tự động

Một phép cộng giữa `byte` và `int` thông thường tạo **`int`**:

~~~java
byte b = 100;
int promoted = b + 1;
System.out.println(promoted); // 101
~~~

Nhưng:

~~~java
byte b = 100;
b += 1;           // Hợp lệ, kết quả lưu vào byte
// b = b + 1;     // Lỗi compile: int không tự thu hẹp về byte
b = (byte) (b + 1); // Hợp lệ, ép kiểu tường minh
~~~

| Vế trái | Phép tính trung gian | Kiểu lưu sau `op=` |
|---|---|---|
| `byte` | Thường nâng lên `int` hoặc rộng hơn | `byte` |
| `short` | Thường nâng lên `int` hoặc rộng hơn | `short` |
| `char` | Thường nâng lên `int` hoặc rộng hơn | `char` |
| `int` | `int`, `long`, `float` hoặc `double` tùy toán hạng | `int` |
| `long` | `long`, `float` hoặc `double` tùy toán hạng | `long` |
| `float` | `float` hoặc `double` | `float` |
| `double` | `double` | `double` |

Ví dụ thu hẹp từ `long` ngay trong phép `+=`:

~~~java
byte n = 1;
n += 255L; // int/long arithmetic, sau đó về byte
System.out.println(n); // 0: 1 + 255 = 256, byte chỉ giữ 8 bit thấp
~~~

Còn phép gán thường:

~~~java
byte n = 1;
// n = n + 255L; // Lỗi compile: kết quả long không tự gán vào byte
~~~

**Cảnh báo:** trình biên dịch cho phép nhiều compound assignment làm mất dữ liệu **dù vế phải không phải hằng và không vừa miền**. Đừng coi khả năng compile là chứng nhận an toàn số học.

## 5. Ví dụ `short`, `char`, `int`, `long`

### `short` bị tràn

~~~java
short s = 32767;
s += 1;
System.out.println(s); // -32768
~~~

Phép cộng có kết quả `int` 32768, thu hẹp về `short` 16 bit có dấu thành -32768.

### `char` tăng mã UTF-16

~~~java
char letter = 'A';
letter += 1;
System.out.println(letter); // B
~~~

`char + int` được tính qua `int`, sau đó gán trở lại `char`. Vì `char` là một UTF-16 code unit (0..65535), nó không phải kiểu biểu diễn mọi ký tự Unicode độc lập, nhất là các ký tự cần surrogate pair.

### `int` thu hẹp kết quả `double`

~~~java
int count = 5;
count += 2.9;
System.out.println(count); // 7
~~~

Phép cộng tạo `double` 7.9, sau đó chuyển về `int` theo quy tắc thu hẹp số thực: **cắt phần lẻ về 0** đối với giá trị hữu hạn trong miền.

Đoạn tương đương về ý nghĩa số với vế trái đơn giản:

~~~java
count = (int) (count + 2.9);
~~~

Không thể thay bằng `count = count + 2.9;` vì `double` không tự gán vào `int`.

### `long` nhận phép cộng với `double`

~~~java
long total = 10L;
total += 2.9;
System.out.println(total); // 12
~~~

Kiểu kết quả cuối vẫn là `long`; phần lẻ bị loại khi thu hẹp từ `double`.

**Nguyên tắc nghiệp vụ:** nếu độ chính xác của số thực có ý nghĩa, việc tự động cắt phần lẻ trong `+=` có thể là bug. Tốt hơn hãy chuyển đổi tường minh kèm kiểm tra hoặc giữ loại dữ liệu đáp ứng yêu cầu.

## 6. Overflow và mất dữ liệu không phát sinh exception mặc định

~~~java
int count = Integer.MAX_VALUE;
count += 1;
System.out.println(count); // -2147483648
~~~

Với `int`, kết quả tràn được tính theo quy tắc số học integer của Java; **không tự ném ngoại lệ overflow**.

Nếu phải phát hiện tràn:

~~~java
int count = Integer.MAX_VALUE;
try {
    count = Math.addExact(count, 1);
} catch (ArithmeticException ex) {
    System.out.println("overflow detected");
}
~~~

**Expected output:**

~~~text
overflow detected
~~~

`Math.addExact` phát hiện tràn `int`/`long` phù hợp overload. Đừng dùng `+=` với giả định nó sẽ tự ngăn overflow hoặc mất thông tin.

Một trường hợp khác là thu hẹp từ `double` sang `int`: nếu giá trị quá lớn, Java có quy tắc bão hòa theo miền số nguyên khi narrowing floating-to-integral (và các quy tắc với NaN). **Không tự coi kết quả ép kiểu này là một phép validate miền.**

## 7. Giới hạn của quy tắc narrowing

Phần **cộng, trừ, nhân, chia, lấy dư, nối `String`** và hành vi vế trái chỉ đánh giá một lần đã được trình bày cùng các ví dụ có thể chạy trong bài “Phép gán kết hợp `+=`, `-=`, `*=`, `/=` và `%=`”. Ở đây ta phân tích thêm **kiểu đích** và những giá trị biên mà bước chuyển đổi âm thầm tạo ra.

| Biểu thức | Phép toán trung gian | Giá trị cuối sau gán |
|---|---|---|
| `byte b = 1; b += 255L;` | `long` 256 | `byte` 0 |
| `int n = 5; n += 2.9;` | `double` 7.9 | `int` 7 |
| `long n = 10L; n += 2.9;` | `double` 12.9 | `long` 12 |
| `short s = 32767; s += 1;` | `int` 32768 | `short` -32768 |

Điểm chung của bốn trường hợp là **kiểu tính toán trung gian không nhất thiết trùng kiểu lưu trữ**. Biến sau phép gán vẫn giữ kiểu đã khai báo, nhưng giá trị có thể thay đổi vì narrowing.

## 8. Trường hợp đặc biệt khi thu hẹp `double` thành `int`

Java có quy tắc cụ thể cho NaN và infinity khi chuyển `double` sang `int`: NaN thành `0`; infinity dương bị chặn tại `Integer.MAX_VALUE`; infinity âm tại `Integer.MIN_VALUE`. Điều này cũng xuất hiện trong compound assignment:

~~~java
int a = 5;
a += Double.NaN;               // a = 0

int b = 0;
b += Double.POSITIVE_INFINITY; // b = 2147483647

int c = 0;
c += Double.NEGATIVE_INFINITY; // c = -2147483648
~~~

Không nhầm việc **chặn giá trị khi narrowing** với kiểm tra hợp lệ nghiệp vụ. Nếu không chấp nhận NaN, infinity hay mất phần thập phân, cần kiểm tra bằng `Double.isFinite` và kiểm tra miền trước khi chuyển.

## 9. Bitwise, boolean và `String` nằm ngoài công thức cast số giản lược

`<<=`, `>>=` và `>>>=` dùng quy tắc dịch bit của Java; `int` chỉ dùng 5 bit thấp của lượng dịch và `long` dùng 6 bit thấp. `&=`, `|=`, `^=` có thể là phép bitwise hoặc boolean tùy kiểu; trên boolean, `&` và `|` **không short-circuit**. `String +=` dùng nối chuỗi chứ không dùng cast số.

~~~java
int bit = 1;
bit <<= 33; // 2, vì lượng dịch được lấy modulo 32

boolean active = false;
active |= true; // true

String label = "item=";
label += 7; // "item=7"
~~~

Các phép này giúp xác định **ranh giới áp dụng** của giải thích “tính số rồi cast về `T`”, không phải là những phép chuyển kiểu số tương tự byte/short.

## 10. Đừng bỏ qua vị trí chứa giá trị ở vế trái

`numbers[index++] += 5` đánh giá vị trí phần tử một lần, lưu giá trị cũ, tính với `5` và gán trở lại phần tử đã chọn. Không được khai triển thành `numbers[index++] = numbers[index++] + 5`: cách viết sau tăng chỉ số **hai lần**. Đây là khác biệt độc lập với narrowing; khi kiểm tra một phép gán kết hợp, cần xem **cả kiểu kết quả lẫn số lần đánh giá vế trái**.

## 11. Wrapper và auto-unboxing/boxing

Với lớp bao như `Integer`, gán kết hợp có thể thực hiện **unboxing → phép tính → boxing**:

~~~java
Integer boxed = 10;
boxed += 5;
System.out.println(boxed); // 15
~~~

Không nên coi việc này là cập nhật giá trị bên trong một object `Integer`; wrapper là immutable. Biến `boxed` được gán lại một giá trị tham chiếu wrapper đại diện cho số mới.

Nếu wrapper là null, phép tính cần unbox sẽ ném `NullPointerException`:

~~~java
Integer boxed = null;
try {
    boxed += 1;
} catch (NullPointerException ex) {
    System.out.println("null unboxing");
}
~~~

**Expected output:**

~~~text
null unboxing
~~~

So với primitive, wrapper cho phép null và được dùng trong generic; `+=` không xóa đi rủi ro null. Kiểm tra dữ liệu trước khi thực hiện phép toán hoặc sử dụng primitive khi trạng thái nullable không cần thiết.

## 12. Biểu thức gán kết hợp cũng trả giá trị

~~~java
int count = 2;
int result = (count += 3) * 4; // count=5, result=20
~~~

`count += 3` có kiểu của biến đích và cung cấp giá trị sau cập nhật. Khi không cần giá trị trung gian, nên viết `count += 3; int result = count * 4;` để giảm side effect bên trong biểu thức.

## 13. `final` không cho phép phép gán kết hợp

~~~java
final int fixed = 3;
// fixed += 1; // Lỗi compile: vẫn là gán lại biến final
~~~

Không có ngoại lệ dành riêng cho `op=`: dù được phép narrowing ngầm, toán tử vẫn phải tuân thủ khả năng gán của biến đích.

## 14. Chương trình Java 17 — kiểm tra chuyển đổi kiểu và giá trị biên

Lưu thành `CompoundAssignmentConversionDemo.java` và chạy với JDK 17+:

~~~java
public final class CompoundAssignmentConversionDemo {
    public static void main(String[] args) {
        byte b = 120;
        b += 10;
        System.out.println("byte=" + b);

        short s = Short.MAX_VALUE;
        s += 1;
        System.out.println("short=" + s);

        int mixed = 5;
        mixed += 2.9;
        System.out.println("intFromDouble=" + mixed);

        long wide = 10L;
        wide += 2.9;
        System.out.println("longFromDouble=" + wide);

        int nan = 5;
        nan += Double.NaN;
        System.out.println("nan=" + nan);

        int positiveInfinity = 0;
        positiveInfinity += Double.POSITIVE_INFINITY;
        System.out.println("positiveInfinity=" + positiveInfinity);

        Integer boxed = 10;
        boxed += 5;
        System.out.println("boxed=" + boxed);

        Integer missing = null;
        try {
            missing += 1;
        } catch (NullPointerException ex) {
            System.out.println("nullWrapper=NullPointerException");
        }

        int[] numbers = {10};
        int index = 0;
        numbers[index++] += 5;
        System.out.println("array=" + numbers[0] + ",index=" + index);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CompoundAssignmentConversionDemo.java
java CompoundAssignmentConversionDemo
~~~

**Expected stdout:**

~~~text
byte=-126
short=-32768
intFromDouble=7
longFromDouble=12
nan=0
positiveInfinity=2147483647
boxed=15
nullWrapper=NullPointerException
array=15,index=1
~~~

Các dòng `nan` và `positiveInfinity` cho thấy narrowing không tự báo lỗi; `boxed` và `nullWrapper` cho thấy wrapper cần unboxing/boxing; dòng `array` xác nhận phép gán kết hợp chỉ đánh giá vị trí phần tử một lần.

## 15. Sai lầm dễ gây mất dữ liệu

| Suy đoán sai | Cách kiểm chứng |
|---|---|
| “`b += 10` luôn giống `b = b + 10`.” | Kiểm tra numeric promotion và cast ngầm; `byte` có thể compile ở `+=` nhưng không ở `= b + ...`. |
| “Compile được nghĩa là không mất dữ liệu.” | Thử biên `byte`, `short` và `int += double`; kiểm tra miền/precision trước. |
| “NaN và infinity sẽ gây ngoại lệ khi cộng vào `int`.” | Narrowing `double` sang `int` theo các giá trị định nghĩa của Java, không mặc định ném lỗi. |
| “`Integer` luôn xử lý như `int`.” | `Integer` nullable, việc unbox null có thể ném `NullPointerException`. |
| “Có thể sao chép biểu thức vế trái khi thay `op=`.” | Với mảng/field chứa lời gọi hoặc `index++`, số lần đánh giá thay đổi. |
| “`+=` là thao tác nguyên tử giữa nhiều thread.” | Đọc–tính–ghi không tự đồng bộ; cần cơ chế đồng bộ/atomic tương ứng. |

## 16. Bài tập phân tích kiểu và miền

1. Với `byte x = 127; x += 1;`, dự đoán `x`. **Đáp án:** -128 sau narrowing từ `int` 128.
2. Với `int n = 10; n += -2.8;`, dự đoán `n`. **Đáp án:** 7; phép cộng trung gian cho `double` 7.2 rồi cắt phần lẻ.
3. Với `int n = 8; n += Double.NaN;`, dự đoán `n`. **Đáp án:** 0 do quy tắc narrowing từ NaN sang `int`.
4. Với `Integer n = null; n += 1;`, điều gì xảy ra? **Đáp án:** `NullPointerException` khi unboxing trước phép cộng.
5. Với `int[] a = {5}; int i = 0; a[i++] += 2;`, giá trị cuối là gì? **Đáp án:** `a[0] == 7`, `i == 1`; vị trí được đánh giá một lần.

## 17. Checklist và kết luận

- [ ] Biết phân biệt kiểu **tính toán trung gian** với kiểu **đích** của compound assignment.
- [ ] Có thể giải thích byte/short overflow và cắt phần lẻ khi `int += double`.
- [ ] Nắm quy tắc Java với NaN, infinity và giá trị ngoài miền khi narrowing từ số thực sang số nguyên.
- [ ] Biết wrapper nullable có thể gây NPE khi unbox.
- [ ] Không thay máy móc `op=` bằng hai lần đánh giá vế trái.
- [ ] Chạy ví dụ và đối chiếu kết quả, kiểm tra miền và precision nếu bài toán cần dữ liệu chính xác.

**Kết luận:** Compound assignment thuận tiện nhưng cho phép **chuyển kiểu hẹp ngầm**, có thể mất bit, phần thập phân hoặc nhận giá trị chặn ở miền số nguyên mà không báo lỗi. Hãy xác định kiểu trung gian, kiểu đích và điều kiện hợp lệ của dữ liệu trước khi chọn `op=`.
