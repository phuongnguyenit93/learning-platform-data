# Kiểu của phép tăng giảm khác phép cộng rồi gán trong Java

Trong Java, ba cách viết tưởng như tương đương dưới đây **không giống nhau về quy tắc kiểu**:

```java
byte b = 10;
b++;        // Hợp lệ.
b += 1;     // Hợp lệ.
// b = b + 1; // Lỗi biên dịch: b + 1 có kiểu int, không tự gán vào byte.
```

Cả ba đều có ý định tăng giá trị lên 1, nhưng Java áp dụng **binary numeric promotion** cho phép cộng thông thường, trong khi phép tăng `++` và phép gán kết hợp `+=` có **quy tắc chuyển đổi ngược vào kiểu biến**. Nắm được sự khác biệt này giúp giải thích lỗi `possible lossy conversion from int to byte`, tránh mất dữ liệu do thu hẹp kiểu ngầm và hiểu đúng giá trị của biểu thức tiền tố/hậu tố.

Bài học thuộc nhóm **Nâng kiểu biểu thức** của **Java core – numbers**, tập trung vào kiểu của phép tăng/giảm `++`/`--` so với phép cộng rồi gán, cũng như các hệ quả với `byte`, `short`, `char`, `int`, `long` và wrapper.

## 1. Nhìn nhanh: phép tính và phép gán là hai giai đoạn

Xét:

```java
byte b = 10;
int sum = b + 1;    // 11, phép cộng có kiểu int.
```

Dù `b` lưu một `byte` và giá trị 11 nằm trong miền `byte`, **biểu thức `b + 1` có kiểu `int`**. Lý do là quy tắc *binary numeric promotion* của toán tử `+`: với các kiểu `byte`, `short`, `char`, toán hạng thường được nâng thành `int` để thực hiện phép tính.

Do đó:

```java
byte b = 10;
// b = b + 1; // Không biên dịch: biểu thức int không được tự thu hẹp về byte.
b = (byte) (b + 1); // Hợp lệ, có cast tường minh.
```

Trong khi đó:

```java
byte b = 10;
b++;     // Hợp lệ, cập nhật byte.
++b;     // Hợp lệ, cập nhật byte.
b += 1;  // Hợp lệ, cập nhật byte.
```

Bảng tóm tắt:

| Cú pháp | Kiểu phép toán trung gian | Kiểu của biểu thức | Ghi giá trị về biến kiểu hẹp? |
| --- | --- | --- | --- |
| `b + 1` với `b` là `byte` | `int` | `int` | Chưa gán |
| `b = b + 1` | `int` | Biểu thức phép gán có kiểu `byte` **nếu hợp lệ** | Không biên dịch nếu không cast |
| `b = (byte)(b + 1)` | `int`, sau đó ép về `byte` | `byte` | Có, cast tường minh |
| `b += 1` | Tính tổng theo quy tắc số học rồi chuyển về `byte` | `byte` | Có, chuyển kiểu ngầm theo compound assignment |
| `b++` | Tăng giá trị và chuyển về kiểu của biến | `byte` | Có, hậu tố trả **giá trị cũ** |
| `++b` | Tăng giá trị và chuyển về kiểu của biến | `byte` | Có, tiền tố trả **giá trị mới** |

Ghi chú về bảng: phép `b = b + 1` là mã không hợp lệ với biến `byte` thông thường; ô “kiểu của biểu thức phép gán nếu hợp lệ” chỉ mô tả quy tắc chung của toán tử gán, không có nghĩa Java cho phép phép gán ấy. Cũng cần phân biệt **kiểu của biểu thức `++b`** là `byte` với **kiểu số học trung gian** có thể được nâng lên trước khi chuyển trở lại `byte`.

## 2. Vì sao `byte + 1` có kiểu int?

Java định nghĩa nhóm phép toán số học nhị phân gồm `+`, `-`, `*`, `/`, `%`. Khi chúng áp dụng lên các toán hạng nguyên thủy, Java thực hiện *binary numeric promotion*:

1. Nếu một toán hạng là `double`, phép toán theo `double`.
2. Nếu không, nhưng có một toán hạng là `float`, phép toán theo `float`.
3. Nếu không, nhưng có một toán hạng là `long`, phép toán theo `long`.
4. Nếu không, phép toán theo **`int`**, kể cả khi cả hai toán hạng ban đầu là `byte`, `short` hoặc `char`.

Ví dụ:

```java
byte a = 10;
byte b = 20;
int sum = a + b;       // Hợp lệ.
// byte wrong = a + b; // Không biên dịch.

short s = 1;
int nextShort = s + 1; // Kiểu biểu thức: int.

char ch = 'A';
int nextCode = ch + 1; // 66, kiểu int.

long l = 5L;
long nextLong = l + 1; // Kiểu long do có một toán hạng long.
```

Lỗi `byte wrong = a + b` là lỗi **kiểu tĩnh tại lúc biên dịch**. Không có một phép “thử cộng trước rồi xem kết quả có vừa byte không” đối với biểu thức có biến thông thường. Ngay cả khi tại thời điểm chạy `a=10` và `b=20`, biểu thức vẫn được Java định kiểu là `int`.

### Ngoại lệ cần biết: hằng số compile-time

Không được phát biểu quá rộng rằng “không thể gán bất kỳ biểu thức cộng có kiểu int nào cho byte”. Java có quy tắc **thu hẹp hằng số khi khởi tạo hoặc gán**, nếu biểu thức là *constant expression* và giá trị nằm trong miền kiểu đích:

```java
byte a = 10 + 20; // Hợp lệ: hằng số 30, vừa byte.

final byte x = 10;
byte y = x + 20;  // Hợp lệ: x là constant variable, tổng 30 là constant expression.
```

Nhưng:

```java
byte a = 10;
// a = a + 20;    // Không biên dịch: a không phải constant variable.
```

Nếu một hằng số nằm ngoài miền, vẫn bị từ chối:

```java
// byte invalid = 100 + 100; // Không biên dịch: 200 vượt Byte.MAX_VALUE.
```

Quy tắc hằng số này khác với phép cập nhật giá trị của **một biến có thể thay đổi**. `final byte x` không thể dùng `x++` hoặc `x += 1`.

## 3. Cơ chế của ++ và --: tăng giảm và lưu ngược kiểu biến

Hai toán tử `++` và `--` tác động trực tiếp lên **biến** có kiểu số hợp lệ. Chúng cập nhật giá trị biến thêm hoặc bớt 1, thực hiện chuyển đổi cần thiết để lưu trở lại đúng kiểu biến.

```java
byte b = 10;
b++; // b = 11, vẫn là byte.

short s = 10;
--s; // s = 9, vẫn là short.

char c = 'A';
++c; // c là 'B', vẫn là char.
```

Với các kiểu nhỏ như `byte`, `short` và `char`, phép tính trung gian được nâng kiểu theo quy tắc số học phù hợp, rồi giá trị được chuyển về kiểu của biến. Đây là nguyên nhân `b++` hợp lệ dù `b = b + 1` không hợp lệ.

**Kiểu của cả biểu thức tiền tố và hậu tố là kiểu của biến**. Vì vậy, nếu `b` có kiểu `byte`, thì `++b` và `b++` có kiểu `byte`. Khi biểu thức ấy tiếp tục tham gia một phép toán nhị phân khác, nó **lại có thể được nâng lên `int`** ở bước tiếp theo.

Ví dụ:

```java
byte b = 10;
byte afterIncrement = ++b; // Hợp lệ: ++b có kiểu byte.
int computed = b++ + 1;    // Phép cộng ngoài cùng có kiểu int.
// byte other = b++ + 1;   // Không biên dịch nếu không cast.
```

Ở đây, cú pháp `++` không “tắt mọi quy tắc nâng kiểu”. Nó chỉ có quy tắc **riêng cho biểu thức tăng/giảm và phép cập nhật biến**.

### Biến nào có thể được tăng hoặc giảm?

Toán hạng của `++`/`--` phải là một biến kiểu số có thể ghi được. Không thể áp dụng cho literal, kết quả phép cộng, biến `final`, hoặc `boolean`:

```java
int i = 10;
i++; // Hợp lệ.

// 10++;      // Sai: literal không phải biến.
// (i + 1)++; // Sai: kết quả cộng không phải biến.
// boolean flag = false; flag++; // Sai: boolean không phải kiểu số.

final int fixed = 5;
// fixed++;   // Sai: không được cập nhật biến final.
```

Một phần tử mảng, field của object hoặc biến cục bộ có thể dùng `++` nếu thỏa điều kiện là biến có thể gán và kiểu phù hợp.

## 4. Tiền tố và hậu tố khác giá trị biểu thức, không khác kiểu biến

Cả `++x` và `x++` đều làm biến `x` tăng 1. Điểm khác nhau là **giá trị biểu thức**:

- `++x` (*prefix*) cập nhật trước rồi cho giá trị mới.
- `x++` (*postfix*) cho giá trị cũ, sau đó biến vẫn được cập nhật.
- Với `x` kiểu `byte`, **cả hai biểu thức có kiểu `byte`**, không phải `int` chỉ vì đang thực hiện cộng thêm 1.

```java
byte a = 10;
byte oldValue = a++; // oldValue = 10, a = 11.

byte b = 10;
byte newValue = ++b; // newValue = 11, b = 11.
```

Hậu tố **không có nghĩa phép tăng bị hoãn đến dòng tiếp theo**: sau khi biểu thức hậu tố đã được đánh giá, biến đã được cập nhật. Chỉ có **giá trị biểu thức được trả ra** là giá trị cũ.

Ví dụ:

```java
int n = 5;
int result = n++ + 10;
// result = 15 vì n++ tạo giá trị 5.
// Sau biểu thức, n = 6.
```

Ngược lại:

```java
int n = 5;
int result = ++n + 10;
// result = 16; n = 6.
```

Trong ứng dụng thực tế, tránh viết biểu thức lồng nhiều `++`/`--` khi không cần: nó làm người đọc khó theo dõi thứ tự đánh giá dù Java quy định thứ tự cụ thể. Một câu lệnh tăng riêng thường rõ ràng hơn.

## 5. Phép gán kết hợp += khác phép cộng rồi gán

Cú pháp:

```java
byte b = 10;
b += 1;
```

có thể hiểu gần với:

```java
b = (byte) (b + 1);
```

Quy tắc chung: biểu thức `E1 op= E2` tương đương về ý nghĩa kiểu với `E1 = (T)((E1) op (E2))`, trong đó `T` là kiểu của `E1`. **Khác biệt quan trọng:** toán hạng trái `E1` chỉ được đánh giá **một lần** trong phép gán kết hợp. Quy tắc này áp dụng cho nhiều toán tử gán kết hợp, không riêng `+=`.

Với `byte`:

```java
byte b = 10;
b += 1;     // Hợp lệ: 11.
b = (byte) (b + 1); // Hợp lệ: 12.
// b = b + 1;       // Không biên dịch.
```

Đối với giá trị và biến đơn giản, `b++` và `b += 1` thường cùng tăng 1 và lưu về kiểu `byte`. Nhưng khi đặt bên trong biểu thức khác, **`b++` trả giá trị cũ**, còn **`b += 1` trả giá trị đã cập nhật**, tương tự `++b` ở khía cạnh này:

```java
int x = 5;
int fromPostfix = x++; // fromPostfix=5, x=6

int y = 5;
int fromCompound = (y += 1); // fromCompound=6, y=6

int z = 5;
int fromPrefix = ++z; // fromPrefix=6, z=6
```

### Compound assignment có thể thu hẹp kiểu ngầm

```java
byte b = 1;
b += 1000; // Hợp lệ về cú pháp, nhưng mất thông tin: kết quả -23.
```

Ở đây `1 + 1000 = 1001`; khi chuyển về `byte` 8 bit, giữ 8 bit thấp: `1001 mod 256 = 233`; diễn giải có dấu của byte là `233 - 256 = -23`. Không có `ArithmeticException` tự động.

Điểm nguy hiểm là **compiler chấp nhận cú pháp, không bảo đảm kết quả nằm trong miền nghiệp vụ**. Ngay cả các phép gán kết hợp với kiểu toán hạng phải mở rộng hơn như `b += 1L` cũng có thể làm phép tính rồi thu hẹp về `byte`. Hãy dùng kiểu đủ rộng và kiểm tra biên nếu không được mất thông tin.

## 6. Tràn kiểu nhỏ với ++ và --

Vì kết quả cuối phải lưu lại vào kiểu biến, việc tăng giảm tại ranh giới có thể **quay vòng**:

```java
byte b = Byte.MAX_VALUE;  // 127
b++;                      // -128

short s = Short.MIN_VALUE; // -32768
s--;                      // 32767

char c = Character.MAX_VALUE; // '\uFFFF'
c++;                          // '\u0000'
```

Với `char`, cần nhớ đây là **đơn vị mã UTF-16 16 bit không dấu** trong Java, có phạm vi `0..65535`. Có thể tăng/giảm `char` theo số học nhưng **không nên sử dụng cách đó như một phương pháp duyệt Unicode code point**: ký tự ngoài BMP dùng surrogate pair, và tăng từng `char` không tương đương tăng từng ký tự Unicode hoàn chỉnh.

Một biểu thức như:

```java
byte b = 127;
int sum = b + 1; // 128, không tràn ở phép cộng int.
b++;             // b trở thành -128 sau khi chuyển về byte.
```

cho thấy rõ sự khác biệt giữa **giá trị int từ phép cộng** và **giá trị đã gán lại vào byte**.

Khi giá trị 128 có ý nghĩa hợp lệ trong bài toán, hãy **đổi kiểu lưu trữ sang `int`** thay vì cố tăng biến `byte`.

## 7. Với int và long: khác biệt cú pháp vẫn tồn tại, nhưng kiểu cộng thường đủ lớn hơn

Với `int`:

```java
int n = 10;
n = n + 1; // Hợp lệ, vế phải kiểu int.
n += 1;    // Hợp lệ.
n++;       // Hợp lệ.
++n;       // Hợp lệ.
```

Với `long`, dùng `long` trong biểu thức số học có `long`:

```java
long n = 10L;
n = n + 1; // Hợp lệ: long + int được nâng thành long.
n += 1;
n++;
```

Nhưng **`int`/`long` vẫn có thể tràn**:

```java
int n = Integer.MAX_VALUE;
n++; // Integer.MIN_VALUE, không tự ném exception.
```

Sự khác biệt kiểu dễ thấy nhất với `byte`, `short`, `char` vì kết quả `+` là `int`. Với `int` hoặc `long`, cả ba cách cập nhật thường cùng hợp lệ, nhưng cách nhận **giá trị cũ/mới** và cách kiểm tra tràn vẫn khác nhau.

Nếu cần phát hiện tràn `int` hoặc `long` thay vì cho phép quay vòng, sử dụng các phương thức checked:

```java
int next = Math.incrementExact(n); // Ném ArithmeticException nếu n == Integer.MAX_VALUE.
int previous = Math.decrementExact(n); // Kiểm tra tràn khi giảm.
```

Phải **gán lại** kết quả nếu muốn cập nhật biến: `n = Math.incrementExact(n)`. Khác `n++`, lời gọi `Math.incrementExact(n)` riêng lẻ không sửa `n`.

## 8. Có thể dùng Math.incrementExact cho byte hay short không?

`Math.incrementExact` có overload cho `int` và `long`, không có overload trả `byte` hoặc `short`. Nếu gọi:

```java
byte b = 127;
int result = Math.incrementExact(b); // Trả 128, KHÔNG ném exception.
```

Java nâng `b` lên `int` trước khi gọi phương thức. Giá trị 128 **vẫn nằm trong miền `int`**, nên `Math.incrementExact` không coi đây là tràn. Nó không biết bạn định gán lại kết quả vào `byte`.

Muốn tăng `byte` **có kiểm tra đúng miền byte**, có thể viết:

```java
static byte incrementByteExact(byte value) {
    int next = Math.incrementExact((int) value);
    if (next > Byte.MAX_VALUE) {
        throw new ArithmeticException("byte overflow");
    }
    return (byte) next;
}
```

Nếu là phép giảm, cần kiểm tra `next < Byte.MIN_VALUE` và cân nhắc sử dụng `Math.decrementExact`. Với `short`, thay miền kiểm tra bằng `Short.MIN_VALUE`/`Short.MAX_VALUE`. Với `char`, kiểm tra trong `0..Character.MAX_VALUE`.

Thực tế, nhiều bài toán nên lưu số lượng tăng giảm bằng `int` ngay từ đầu. Sử dụng `byte`/`short` cho bộ đếm chỉ vì giá trị lúc đầu nhỏ thường làm code khó hiểu và dễ phát sinh lỗi thu hẹp kiểu.

## 9. Wrapper: ++ với Byte, Short, Integer có thể unbox/box

Java cho phép tăng/giảm biến kiểu wrapper số như `Byte`, `Short`, `Integer` hoặc `Long`:

```java
Byte boxed = 10;
boxed++; // Unbox, cộng 1, chuyển kiểu/box lại; boxed giữ giá trị 11.
```

Wrapper là kiểu đối tượng có thể `null`. Khi toán tử cần lấy giá trị số bên trong, Java phải **unbox**. Do đó:

```java
Integer count = null;
// count++; // Ném NullPointerException khi chạy vì unbox null.
```

Không nhầm lẫn lỗi này với lỗi biên số học. `Integer` wrapper không tự biến `++` thành phép tăng checked, và `Byte` wrapper vẫn có thể quay vòng:

```java
Byte b = Byte.MAX_VALUE;
b++; // b là -128 sau khi box lại.
```

Với collection/DTO có wrapper nullable, hãy xác định cách xử lý `null` trước khi tăng và không dùng `++` mù quáng. Nếu giá trị bắt buộc luôn có, primitive thường thể hiện rõ hợp đồng hơn.

## 10. Thứ tự đánh giá và side effect: không lặp tính toán khi thay bằng phép gán

Với biến đơn giản, `b += 1` gần với `b = (byte)(b + 1)`. Nhưng khi vế trái là một biểu thức có side effect, thay thế máy móc có thể khiến nó bị đánh giá **hai lần**:

```java
int[] values = {10, 20, 30};
int i = 0;
values[i++] += 1; // Chỉ tăng i một lần; values[0] thành 11.
```

Nếu đổi một cách ngây thơ thành:

```java
int[] values = {10, 20, 30};
int i = 0;
values[i++] = values[i++] + 1;
```

thì hai lần `i++` làm chỉ số được đánh giá khác nhau: giá trị ở phía đọc có thể đến từ phần tử kế tiếp. Không còn tương đương.

Chính vì vậy, trong đặc tả Java, phép gán kết hợp được mô tả bằng công thức tương đương **kèm điều kiện vế trái chỉ được đánh giá một lần**. Nếu cần refactor một biểu thức phức tạp, hãy tách vế trái hoặc lưu chỉ số/đối tượng vào biến cục bộ rõ ràng.

Ví dụ dễ đọc:

```java
int[] values = {10, 20, 30};
int index = 0;
values[index] += 1;
index++;
```

`++` với phần tử mảng hay field cũng đánh giá địa chỉ/biến đích theo quy tắc ngôn ngữ; không nên tùy tiện thay thế bằng biểu thức có nhiều lần đánh giá cùng một vế trái.

## 11. Chương trình Java 17+ chạy độc lập

Lưu thành **`IncrementTypeDemo.java`**:

```java
public class IncrementTypeDemo {
    static byte incrementByteExact(byte value) {
        int next = Math.incrementExact((int) value);
        if (next > Byte.MAX_VALUE) {
            throw new ArithmeticException("byte overflow");
        }
        return (byte) next;
    }

    public static void main(String[] args) {
        byte b = 10;
        int added = b + 1;
        System.out.println("addition-int=" + added);

        byte post = b++;
        System.out.println("post-old=" + post);
        System.out.println("post-current=" + b);

        byte pre = ++b;
        System.out.println("pre-new=" + pre);
        System.out.println("pre-current=" + b);

        b += 1;
        System.out.println("compound=" + b);

        byte overflow = Byte.MAX_VALUE;
        overflow++;
        System.out.println("byte-overflow=" + overflow);

        short s = Short.MIN_VALUE;
        s--;
        System.out.println("short-underflow=" + s);

        char ch = Character.MAX_VALUE;
        ch++;
        System.out.println("char-wrap-code=" + (int) ch);

        byte x = 1;
        x += 1000;
        System.out.println("compound-narrowing=" + x);

        int n = 5;
        int postfixResult = n++;
        int prefixResult = ++n;
        System.out.println("int-postfix=" + postfixResult);
        System.out.println("int-prefix=" + prefixResult);
        System.out.println("int-current=" + n);

        byte max = Byte.MAX_VALUE;
        System.out.println("int-exact-result=" +
                Math.incrementExact((int) max));
        try {
            incrementByteExact(max);
        } catch (ArithmeticException ex) {
            System.out.println("byte-exact=overflow");
        }

        Byte boxed = Byte.MAX_VALUE;
        boxed++;
        System.out.println("boxed-byte-wrap=" + boxed);
    }
}
```

Biên dịch/chạy bằng JDK 17 hoặc mới hơn:

```bash
javac IncrementTypeDemo.java
java IncrementTypeDemo
```

Stdout chính xác:

```text
addition-int=11
post-old=10
post-current=11
pre-new=12
pre-current=12
compound=13
byte-overflow=-128
short-underflow=32767
char-wrap-code=0
compound-narrowing=-23
int-postfix=5
int-prefix=7
int-current=7
int-exact-result=128
byte-exact=overflow
boxed-byte-wrap=-128
```

**Phân tích quan trọng:**

- `b + 1` tạo biểu thức `int`, nhưng `b++`, `++b`, `b += 1` cập nhật được `byte`.
- `b++` trả 10 rồi cập nhật thành 11; `++b` cập nhật từ 11 lên 12 và trả 12.
- Tăng `Byte.MAX_VALUE` trở thành `Byte.MIN_VALUE`, giảm `Short.MIN_VALUE` thành `Short.MAX_VALUE`; tăng `Character.MAX_VALUE` quay về 0.
- `x += 1000` được phép nhưng chuyển kết quả về `byte` nên trả -23.
- `Math.incrementExact((int) Byte.MAX_VALUE)` trả 128 vì vẫn vừa `int`. Hàm `incrementByteExact` kiểm tra giới hạn `byte` mới thực sự phát hiện lỗi.
- `Byte` wrapper cũng quay vòng và box lại giá trị mới.

## 12. Lỗi thường gặp và cách tránh

| Lỗi/nhầm lẫn | Vì sao xảy ra? | Cách xử lý |
| --- | --- | --- |
| `byte b = 1; b = b + 1;` không biên dịch | `b + 1` là `int`; gán `int → byte` không tự động | Dùng `b++`, `b += 1`, cast có chủ ý, hoặc đổi sang `int` |
| Tưởng `b++` có kiểu `int` | Nhầm kiểu phép tính trung gian với kiểu của biểu thức `++` | `b++` và `++b` có kiểu của biến, ở đây là `byte` |
| Tưởng `b += 1` có kiểm tra tràn | `+=` có chuyển về kiểu đích, có thể mất bit | Kiểm tra miền hoặc dùng kiểu rộng hơn |
| Dùng `Math.incrementExact(b)` để kiểm tra overflow byte | `b` được nâng lên `int`; phép tính 127+1 vẫn vừa int | Kiểm tra riêng miền byte trước khi cast |
| Dùng `x++` khi cần giá trị mới trong biểu thức | Hậu tố trả giá trị cũ | Dùng `++x` hoặc tách câu lệnh tăng và câu lệnh đọc |
| Dùng `++x` khi cần giá trị trước cập nhật | Tiền tố trả giá trị mới | Dùng `x++` hoặc tách biến cũ |
| Refactor `array[i++] += 1` thành `array[i++] = array[i++] + 1` | Vế trái bị đánh giá nhiều lần | Dùng `+=` hoặc lưu chỉ số trước khi cập nhật |
| Tăng một `Byte`/`Integer` có thể null | Unboxing `null` | Kiểm tra null/hợp đồng dữ liệu |
| Viết bộ đếm bằng `byte` chỉ vì giá trị ban đầu nhỏ | Sớm tràn và khó hiểu khi cộng/gán | Thường chọn `int` cho bộ đếm |
| Coi quy tắc constant expression áp dụng cho mọi biến | Chỉ hằng số compile-time phù hợp miền mới được thu hẹp ngầm đặc biệt | Phân biệt literal/`final` constant và biến cập nhật runtime |

## 13. Bài tập tự kiểm tra

**Bài 1 — Dự đoán lỗi biên dịch.** Xác định dòng nào hợp lệ, lý do và kiểu biểu thức:

```java
byte b = 5;
int a = b + 1;
// byte c = b + 1;
byte d = ++b;
byte e = b++;
b += 1;
b = (byte) (b + 1);
```

Giải thích vì sao `b + 1` là `int`, còn `++b`/`b++` là `byte`.

**Bài 2 — Giá trị cũ và mới.** Dự đoán `a`, `b`, `x`:

```java
int x = 10;
int a = x++;
int b = ++x;
```

Đáp án: `a=10`, `b=12`, `x=12`.

**Bài 3 — Tràn sau phép tăng.** Cho `byte b = 127`, tính kết quả của `b++` và `b += 1`. Vì sao không ném ngoại lệ? Viết phiên bản có kiểm tra để fail fast.

**Bài 4 — Kiểu nhỏ và hằng số.** Tại sao `byte b = 1 + 2;` hợp lệ trong khi `byte b = 1; b = b + 2;` không hợp lệ? Hãy thử `final byte x = 5; byte y = x + 1;` và `final byte x = 120; byte y = x + 20;`.

**Bài 5 — char và Unicode.** Giải thích `char c = Character.MAX_VALUE; c++;`. Vì sao không nên dùng tăng `char` để duyệt mọi ký tự Unicode ngoài BMP?

**Bài 6 — Đánh giá vế trái một lần.** So sánh side effect của `array[i++] += 1` với `array[i++] = array[i++] + 1`. Hãy biến đổi code để giữ semantics mà vẫn dễ đọc.

**Bài 7 — Wrapper nullable.** Với `Integer n = null;`, dự đoán `n++`. Thiết kế validation để phân biệt “chưa nhập” và “đang bằng 0”.

**Bài 8 — Kiểm tra byte.** Viết `decrementByteExact(byte value)` phát hiện `Byte.MIN_VALUE`; kiểm thử `-127`, `-128`, `0`, `127`. Đảm bảo ngoại lệ chỉ xảy ra khi phép giảm không vừa byte.

## 14. Ghi nhớ

- **`byte`/`short`/`char` cộng với số nguyên thông thường được nâng lên `int`**. Vì vậy `b = b + 1` với `byte b` thường không biên dịch.
- **`++b`, `b++`, `b += 1` có thể cập nhật biến kiểu hẹp** nhờ quy tắc chuyển kết quả về kiểu biến.
- **Kiểu biểu thức `++b` và `b++` là kiểu của biến**, dù bước tính toán trung gian có thể được nâng kiểu.
- **Hậu tố trả giá trị cũ, tiền tố trả giá trị mới**; cả hai đều cập nhật biến khi được đánh giá.
- **Compound assignment có chuyển kiểu ngầm và chỉ đánh giá vế trái một lần**. Vì vậy nó không phải luôn tương đương với cách viết vế trái hai lần.
- **Hợp lệ về kiểu không có nghĩa an toàn trước tràn**: `byte`, `short`, `char`, `int`, `long` đều có giới hạn. `Math.incrementExact` chỉ kiểm tra miền của overload `int`/`long` được chọn, không tự kiểm tra miền byte.
- Khi bài toán cần giữ kết quả số học thật sự, **dùng kiểu đủ rộng và kiểm tra biên trước khi thu hẹp**; khi yêu cầu là cập nhật biến kiểu nhỏ, hãy nêu rõ chính sách xử lý overflow.

Sự khác biệt nằm ở **quy tắc của từng toán tử và kiểu của biểu thức**: phép cộng bình thường áp dụng nâng kiểu số học, còn tăng/giảm và gán kết hợp có quy tắc riêng cho cập nhật biến. Nắm rõ hai bước “tính theo kiểu nào” và “lưu về kiểu nào” là cách phân tích chính xác mọi ví dụ thuộc nhóm này.
