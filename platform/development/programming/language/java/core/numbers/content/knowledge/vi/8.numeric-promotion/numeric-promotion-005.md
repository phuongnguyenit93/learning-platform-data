# Compound assignment và phép thu hẹp ngầm định trong Java

**Compound assignment** (phép gán kết hợp) là toán tử vừa thực hiện phép tính, vừa gán kết quả lại cho biến ở vế trái, như `+=`, `-=`, `*=`. Điểm dễ gây nhầm là **phép gán kết hợp có thể tự động thu hẹp kiểu của kết quả về kiểu biến nhận**, ngay cả khi phép gán thông thường với biểu thức tương đương sẽ **không biên dịch**.

```java
byte count = 10;
count += 1;          // Hợp lệ: phép cộng ở kiểu int, thu hẹp về byte.
// count = count + 1; // LỖI biên dịch: count + 1 có kiểu int.
```

Đây là mảnh mã có thể đặt trong một phương thức Java. Quy tắc hợp lệ của `count += 1` **không có nghĩa phép toán luôn an toàn, không tràn hay không mất dữ liệu**. Muốn sử dụng đúng, cần hiểu cách Java nâng kiểu biểu thức trước khi chuyển kết quả trở lại kiểu của vế trái.

## 1. Định nghĩa và các toán tử gán kết hợp

Ở phép gán thường `x = expression`, Java kiểm tra kết quả biểu thức có thể chuyển sang kiểu của `x` bằng **assignment conversion** hay không. Ở phép gán kết hợp, Java cho phép phép toán và chuyển kết quả về kiểu của biến nhận như một phần của ngữ nghĩa toán tử.

| Nhóm | Các toán tử | Ví dụ |
| --- | --- | --- |
| Số học | `+=`, `-=`, `*=`, `/=`, `%=` | `x += 5`, `x *= 2` |
| Bitwise | `&=`, `\|=`, `^=` | `mask &= 0xFF`, `flags ^= 0b10` |
| Dịch bit | `<<=`, `>>=`, `>>>=` | `bits <<= 1`, `bits >>>= 2` |

Các toán tử `&=`, `|=`, `^=` cũng hỗ trợ toán hạng kiểu `boolean` theo quy tắc boolean, chẳng hạn `boolean ok = true; ok &= false;`. Java **không có** toán tử `&&=` hoặc `||=`. Riêng `String +=` là trường hợp phép **nối chuỗi**, không theo quy tắc thu hẹp kiểu số.

## 2. Quy tắc gần tương đương của Java: phép toán rồi ép về kiểu vế trái

Theo ngữ nghĩa Java, đối với phép gán kết hợp hợp lệ:

```text
E1 op= E2
```

gần tương đương với:

```text
E1 = (T) (E1 op E2)
```

trong đó `T` là **kiểu của `E1`**. Khác biệt quan trọng là **biểu thức vế trái `E1` chỉ được đánh giá một lần** trong toán tử gán kết hợp. Công thức chỉ là mô hình để hiểu kiểu và kết quả; **không nên thay máy móc** mọi `op=` bằng đoạn mã trên nếu vế trái có tác dụng phụ.

Với các giá trị nguyên, luồng chuyển kiểu thường diễn ra như sau:

1. Đánh giá vị trí/vế trái và lưu giá trị ban đầu.
2. Đánh giá biểu thức vế phải.
3. Thực hiện phép toán theo **binary numeric promotion** hoặc quy tắc kiểu riêng của toán tử. `byte`, `short`, `char` khi tham gia cộng/trừ/nhân thường được nâng lên `int`; nếu có `long`, `float`, `double`, kiểu phép toán có thể rộng hơn.
4. Chuyển kết quả về **kiểu vế trái** bằng phép chuyển phù hợp, bao gồm thu hẹp số nguyên/float khi cần.
5. Lưu giá trị đã chuyển trở lại biến, phần tử mảng hoặc trường.

Ví dụ `byte b = 10; b += 20;` tính `int` 30 rồi thu hẹp thành `byte` 30. Với `byte b = 127; b += 1;`, giá trị tính toán `int` là 128 nhưng chuyển xuống `byte` cho **-128**.

## 3. Vì sao `byte += int` hợp lệ nhưng `byte = byte + int` có thể không?

Đối với toán tử cộng nhị phân, cả hai toán hạng `byte` và `short` thường được **nâng lên `int`**. Vì vậy `b + 1` có kiểu `int`, bất kể `b` được khai báo là `byte`.

```java
byte b = 10;
int result = b + 1; // Hợp lệ: int 11.
// b = b + 1;        // LỖI: không được tự chuyển int động sang byte.
b += 1;             // Hợp lệ: kết quả phép cộng tự thu hẹp thành byte.
```

Ở dòng gán thường, trình biên dịch không thể đảm bảo một biểu thức `int` động luôn nằm trong -128..127. Gán kết hợp là một quy tắc riêng **có phép thu hẹp ngầm định**, chứ không làm `b + 1` đổi kiểu thành `byte`.

Cần phân biệt với **thu hẹp biểu thức hằng số lúc gán**:

```java
byte a = 1 + 2;    // Hợp lệ: biểu thức hằng int có giá trị 3 trong phạm vi byte.
byte b = 10;
// byte c = b + 1; // LỖI: b + 1 không phải biểu thức hằng compile-time.
b += 1;            // Hợp lệ theo quy tắc compound assignment.
```

Do đó, việc `byte a = 1 + 2` được cho phép **không chứng minh** phép gán thường `b = b + 1` là hợp lệ. Đó là **hai ngoại lệ khác nhau** trong hệ thống kiểu của Java.

## 4. Mất dữ liệu và quay vòng khi thu hẹp sang `byte`, `short`, `char`

Khi chuyển một giá trị nguyên sang kiểu nguyên **hẹp hơn**, Java bỏ các bit cao vượt độ rộng đích và diễn giải phần còn lại theo kiểu đích:

| Trường hợp | Kết quả phép tính trước khi thu hẹp | Kết quả lưu |
| --- | ---: | --- |
| `byte b = 127; b += 1;` | `int` 128 | `byte` -128 |
| `short s = 32767; s += 1;` | `int` 32768 | `short` -32768 |
| `byte b = 100; b *= 2;` | `int` 200 | `byte` -56 |
| `byte b = 1; b += 200L;` | `long` 201 | `byte` -55 |
| `char c = 'A'; c += 1;` | `int` 66 | `char` 'B' |
| `char c = Character.MAX_VALUE; c += 1;` | `int` 65536 | `char` có mã 0 |

`byte` có 8 bit có dấu (-128..127), `short` có 16 bit có dấu, còn `char` là 16 bit **không dấu** (0..65535), biểu diễn một **đơn vị mã UTF-16**. Vì vậy `char` không trở thành số âm khi vượt 65535: sau khi mất các bit cao, nó quay về code unit `0`.

Đối với các toán tử thường dùng, việc thực hiện phép toán trước rồi chuyển hẹp là điều khiến `+=`, `*=`, `-=` có thể làm mất dữ liệu mà không báo lỗi. **Compiler chấp nhận cú pháp** không đồng nghĩa với **kết quả toán học được bảo toàn**.

Ví dụ, dùng `byte` để đếm số lượng và tăng liên tục bằng `+=` sẽ quay vòng sau 127; đây thường là lỗi nghiệp vụ. Chọn `int` hoặc `long` khi cần phạm vi rộng hơn, hoặc chủ động kiểm tra biên.

## 5. Vế phải rộng hơn vẫn có thể được chấp nhận

Java không yêu cầu vế phải của phép gán kết hợp phải có kiểu nhỏ hơn hoặc bằng vế trái. Chẳng hạn:

```java
byte small = 1;
small += 200L;     // Hợp lệ: tính bằng long, sau đó thu hẹp về byte (-55).

int n = 7;
n += 2.9;          // Hợp lệ: tính bằng double 9.9, chuyển về int 9.

long length = 4L;
length += 0.9d;    // Hợp lệ: double 4.9, chuyển về long 4.
```

Ngược lại, phép gán thường không cho phép tự chuyển một giá trị `double` hoặc `long` động thành `int`, `byte` hoặc `long` hẹp hơn một cách tùy ý.

Với chuyển `double`/`float` sang số nguyên, Java **không làm tròn đến số nguyên gần nhất**. Phần thập phân bị loại bỏ theo hướng về 0 khi giá trị hữu hạn nằm trong phạm vi. Với giá trị ngoài phạm vi đích trung gian hoặc `NaN`, còn có các quy tắc chuyển float-to-integer riêng (như bão hòa về cực trị hoặc `NaN` thành 0); nếu đang cần tính số lượng chính xác, **không nên dựa vào `+=` để âm thầm ép số thực về số nguyên**.

Ví dụ `n += 2.9` cho `9`, khác với làm tròn `7 + 2.9 = 9.9` lên 10. Nếu muốn làm tròn, hãy áp dụng quy tắc nghiệp vụ tường minh trước khi gán, chẳng hạn dùng `Math.round` khi phù hợp.

## 6. Phép tính tràn trước khi chuyển hẹp vẫn có thể xảy ra

Phép gán kết hợp có **hai nguồn mất dữ liệu khác nhau**:

- **Phép toán ban đầu có thể đã tràn trong kiểu thực thi**, chẳng hạn phép cộng `int` hoặc `long`.
- **Kết quả hợp lệ của phép toán có thể bị thu hẹp** khi lưu vào biến nhỏ hơn.

```java
int max = Integer.MAX_VALUE;
max += 1;        // -2147483648: phép cộng int quay vòng.

byte b = 100;
b *= 2;          // -56: phép nhân int được 200, thu hẹp thành byte.

long total = 2_000_000_000L;
total += 1_000_000_000; // 3000000000: phép cộng diễn ra ở long.
```

Ở trường hợp `max += 1`, kiểu vế trái là `int`, phép cộng cũng là `int`; giá trị đã quay vòng ở phép toán. Ở `b *= 2`, phép nhân `int` được đúng 200, **sau đó** giá trị bị thay đổi khi chuyển sang `byte`. Hai tình huống có cùng kết quả “ngoài mong đợi” nhưng nguyên nhân khác nhau.

Nếu bắt buộc không được tràn, `Math.addExact`, `Math.multiplyExact`, `Math.toIntExact` hỗ trợ kiểm tra phạm vi cho `int`/`long`. Không có hàm `Math.toByteExact` trong Java 17; với `byte`, có thể tính ở `int` bằng `Math.addExact` rồi kiểm tra `Byte.MIN_VALUE <= result <= Byte.MAX_VALUE` trước khi ép.

```java
byte b = 120;
int computed = Math.addExact((int) b, 10);
if (computed < Byte.MIN_VALUE || computed > Byte.MAX_VALUE) {
    throw new ArithmeticException("byte out of range");
}
b = (byte) computed;
```

Đây là mảnh mã trong phương thức. Thay `b += 10` bằng hướng tiếp cận này khi cần **từ chối dữ liệu ngoài phạm vi**, chứ không phải quấn vòng tự động.

## 7. Vế trái được đánh giá đúng một lần: khác biệt không chỉ là ép kiểu

Hãy xét phép gán kết hợp với truy cập mảng và toán tử tăng hậu tố:

```java
int[] values = {10, 20};
int i = 0;
values[i++] += i;
// values[0] == 11, i == 1, values[1] == 20.
```

Java đánh giá `values[i++]` để tìm phần tử vế trái **một lần**: đọc chỉ số cũ 0 và làm `i` thành 1; sau đó đánh giá vế phải `i` là 1. Giá trị cũ của `values[0]` là 10, nên kết quả 11 được lưu trở lại **đúng phần tử 0**.

Không được viết lại thành:

```java
// KHÔNG tương đương khi vế trái có tác dụng phụ:
values[i++] = (int) (values[i++] + i);
```

Trong biểu thức viết lại, `i++` có thể bị đánh giá **hai lần**, gây thay đổi chỉ số và cả phần tử được cập nhật. Quy tắc vế trái đánh giá một lần áp dụng cả trường đối tượng, truy cập mảng, biểu thức có lời gọi phương thức và những phép tính tạo ra địa chỉ/vị trí lưu.

Ví dụ riêng:

```java
int[] arr = {10};
arr[locate()] += 2; // locate() chỉ được gọi một lần.
```

Ở đây giả sử `locate()` là một phương thức trả 0 và tăng bộ đếm mỗi lần được gọi. Chương trình hoàn chỉnh bên dưới có minh họa runnable cho trường hợp này.

## 8. Phép tăng `++` và giảm `--` cũng đáng lưu ý

Dù cú pháp khác `+=`/`-=`, `++` và `--` trên biến kiểu `byte`, `short`, `char` cũng có thể cập nhật biến về đúng kiểu nhỏ mà không cần ghi ép kiểu rõ ràng:

```java
byte b = 127;
b++;            // b == -128.

char c = 'A';
c++;            // c == 'B'.
```

Tuy nhiên `b++` và `++b` **khác nhau ở giá trị mà biểu thức trả về** (trước tăng hoặc sau tăng). Chúng không phải cú pháp hoán đổi vô điều kiện với `b += 1`, nhất là khi giá trị của toàn biểu thức được sử dụng. Khi cần hiểu ngữ nghĩa kiểu, hãy phân biệt **phép cập nhật biến**, **giá trị trả về của biểu thức** và **thời điểm tác dụng phụ xảy ra**.

## 9. Chương trình Java 17+ biên dịch và chạy độc lập

Lưu tệp **`CompoundAssignmentDemo.java`**:

```java
public class CompoundAssignmentDemo {
    static int evaluations = 0;

    static int locate() {
        evaluations++;
        return 0;
    }

    public static void main(String[] args) {
        byte b = 127;
        b += 1;
        System.out.println("byteWrap=" + b);

        short s = 32_767;
        s += 1;
        System.out.println("shortWrap=" + s);

        char letter = 'A';
        letter += 1;
        System.out.println("nextChar=" + letter);

        char maxChar = Character.MAX_VALUE;
        maxChar += 1;
        System.out.println("charWrapCode=" + (int) maxChar);

        byte product = 100;
        product *= 2;
        System.out.println("byteProduct=" + product);

        byte mixed = 1;
        mixed += 200L;
        System.out.println("byteWithLong=" + mixed);

        int truncated = 7;
        truncated += 2.9;
        System.out.println("doubleToInt=" + truncated);

        long longValue = 4L;
        longValue += 0.9d;
        System.out.println("doubleToLong=" + longValue);

        int bitMask = 0b1010;
        bitMask &= 0b1100;
        System.out.println("bitAnd=" + bitMask);

        String label = "A";
        label += 5;
        System.out.println("stringPlus=" + label);

        Integer boxed = 127;
        boxed += 1;
        System.out.println("boxed=" + boxed);

        int[] values = {10, 20};
        int i = 0;
        values[i++] += i;
        System.out.println("sideEffect=" + values[0] + "," + i + "," + values[1]);

        int[] once = {10};
        once[locate()] += 2;
        System.out.println("lhsOnce=" + once[0] + "," + evaluations);

        int nearMax = Integer.MAX_VALUE;
        nearMax += 1;
        System.out.println("intOverflow=" + nearMax);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 CompoundAssignmentDemo.java
java CompoundAssignmentDemo
```

Kết quả stdout chính xác:

```text
byteWrap=-128
shortWrap=-32768
nextChar=B
charWrapCode=0
byteProduct=-56
byteWithLong=-55
doubleToInt=9
doubleToLong=4
bitAnd=8
stringPlus=A5
boxed=128
sideEffect=11,1,20
lhsOnce=12,1
intOverflow=-2147483648
```

Trong đó:

- `byteWrap`, `shortWrap`, `byteProduct`, `byteWithLong` cho thấy kết quả bị thu hẹp về kiểu đích và có thể quay vòng.
- `nextChar` và `charWrapCode` minh họa `char` là kiểu nguyên không dấu 16 bit, không tự “mở rộng” khi dùng `+=`.
- `doubleToInt`, `doubleToLong` cho thấy gán kết hợp có thể thu hẹp từ số thực về số nguyên và bỏ phần thập phân.
- `bitAnd` là gán kết hợp cho phép toán bitwise; `stringPlus` minh họa ngoại lệ nối chuỗi.
- `boxed` cho thấy wrapper `Integer` cũng có thể dùng `+=` thông qua unboxing/boxing; đó **không phải** phép toán nguyên tử trên một đối tượng số bất biến.
- `sideEffect`, `lhsOnce` chứng minh vế trái của phép gán kết hợp chỉ được đánh giá một lần.
- `intOverflow` cho thấy `int` có thể tràn khi dùng `+=` như khi cộng thông thường.

## 10. Các toán tử bitwise và shift có thu hẹp ngầm định

Quy tắc gán kết hợp không chỉ áp dụng cho cộng/trừ/nhân. Ví dụ:

```java
byte bits = 0b0000_1111;
bits <<= 1;        // Giá trị được dịch ở kiểu int rồi thu hẹp về byte.
bits &= 0b0001_1110; // Mask tiếp tục cập nhật byte.

int mask = 0b1010;
mask &= 0b1100;    // 0b1000, tức 8.
```

Với `byte` hoặc `short`, phép dịch bit thường sử dụng `int` sau khi nâng kiểu toán hạng trái; kết quả mới được chuyển về kiểu biến ban đầu. Đừng nhầm việc `bits <<= 1` biên dịch với việc bit bị đẩy ra ngoài độ rộng nhỏ sẽ được lưu lại.

Trong các phép dịch, `>>` là dịch phải giữ dấu, `>>>` là dịch phải điền 0; khi kết quả được thu hẹp xuống `byte`, `short` hoặc `char`, các bit cao lại có thể bị loại bỏ. Khi viết mã mask/bit protocol, cần kiểm tra chính xác **kiểu toán hạng sau promotion** và độ rộng muốn giữ.

Các toán tử boolean `&=`, `|=`, `^=` làm việc với giá trị logic, **không có câu chuyện thu hẹp kiểu số**. Và cũng không có `boolean += ...` trong Java.

## 11. Wrapper types, `null`, biến `final` và đa luồng

**Wrapper:** `Integer`, `Byte`, `Short`, `Long`, `Character` là các lớp đóng gói giá trị nguyên thủy. Với kiểu wrapper thích hợp, `+=` có thể **unbox**, thực hiện phép số học, rồi **box** kết quả:

```java
Integer score = 127;
score += 1; // score mang giá trị 128 dưới dạng Integer mới hoặc boxed value.
```

Nếu wrapper bằng `null`, phép tính cần unbox sẽ ném `NullPointerException` tại thời điểm chạy. Không coi `Integer count; count += 1;` là cách tăng an toàn nếu giá trị chưa được khởi tạo hợp lệ. Wrapper bất biến; phép `+=` là cập nhật **biến tham chiếu**, không sửa đối tượng cũ.

**`final`:** gán kết hợp sửa biến nhận, nên không thể dùng cho biến `final` sau khi đã được gán:

```java
final int limit = 10;
// limit += 1; // LỖI biên dịch: không thể gán lại biến final.
```

**Đa luồng:** `counter += 1` gồm đọc giá trị cũ, tính, rồi ghi lại; thao tác này **không nguyên tử chỉ vì dùng một toán tử**. Ngay cả biến `volatile int counter` cũng không làm `counter += 1` tự trở thành atomic read-modify-write. Nếu nhiều luồng cùng cập nhật bộ đếm, cân nhắc `AtomicInteger.incrementAndGet()`, `AtomicLong.addAndGet(...)` hoặc đồng bộ hóa phù hợp, tùy yêu cầu nhất quán.

## 12. Phân biệt gán kết hợp, gán thường và cast tường minh

| Cách viết | Với `byte b = 10` | Kết quả |
| --- | --- | --- |
| `b += 1;` | Hợp lệ | Tính `int` 11, thu hẹp thành `byte` 11 |
| `b = b + 1;` | Không hợp lệ | Biểu thức `b + 1` có kiểu `int`, cần chuyển hẹp |
| `b = (byte) (b + 1);` | Hợp lệ | Diễn đạt tường minh phép chuyển hẹp, giá trị 11 |
| `b += 200;` | Hợp lệ | Tính `int` 210, thu hẹp `byte` thành -46 |
| `b = (byte) 210;` | Hợp lệ (có cast) | Giá trị `byte` -46 |
| `int n = b + 1;` | Hợp lệ | Giá trị ở `int`, không bị thu hẹp về `byte` |

Sự giống nhau giữa `b += 1` và `b = (byte) (b + 1)` ở đây chỉ áp dụng khi **vế trái là biến đơn giản không có tác dụng phụ**. Đối với `a[i++]`, lời gọi phương thức, truy cập trường hoặc biểu thức phức tạp, không được quên nguyên tắc **đánh giá vế trái đúng một lần**.

## 13. Lỗi thường gặp và cách sửa

| Lỗi/nhầm lẫn | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Cho rằng `b += 1` giữ kết quả ở `int` | Bỏ qua chuyển hẹp implicit ở bước lưu | Xác định kiểu của biến vế trái |
| `byte b = 127; b += 1;` bất ngờ âm | Thu hẹp mẫu bit 128 về `byte` | Dùng `int` hoặc kiểm tra phạm vi trước |
| `short s = 32767; s += 1;` thành âm | Vượt biên `short` | Dùng `int` khi đếm vượt 32767 |
| `int x = 7; x += 2.9;` thành 9 | `double` bị chuyển sang `int`, bỏ phần lẻ | Làm tròn/chuyển kiểu có chủ đích |
| `byte b = 1; b += 200L;` thành -55 | `long` bị thu hẹp về `byte` | Chọn biến đủ rộng, không dựa vào cast ngầm |
| Đổi `a[i++] += 1` thành `a[i++] = a[i++] + 1` | Đánh giá vế trái nhiều lần | Giữ `+=` hoặc lưu index vào biến tạm |
| Nghĩ `Integer x += 1` là atomic | Unbox, toán học, box, cập nhật tham chiếu | Dùng API đồng bộ/atomic phù hợp |
| Dùng `+=` lên `final` | Toán tử sửa giá trị vế trái | Không dùng phép gán sau khi final đã gán |
| Nhầm `String +=` với số học | Với `String`, `+=` nối văn bản | Phân biệt ngữ cảnh kiểu |
| Cho rằng `+=` tự phát hiện overflow | Số nguyên Java thông thường có thể quay vòng | Dùng `Math.*Exact` và kiểm tra phạm vi đích |

## 14. Câu hỏi tự kiểm tra

1. **Vì sao `byte b = 5; b += 1;` hợp lệ, nhưng `b = b + 1;` không hợp lệ?** Vì `b + 1` có kiểu `int`; compound assignment có phép thu hẹp ngầm định về `byte`, còn gán thường không tự thu hẹp một biểu thức động như vậy.
2. **`byte b = 127; b += 1;` cho kết quả nào?** `-128`, do `int` 128 thu hẹp còn 8 bit có dấu.
3. **`short s = 32767; s += 1;` bằng gì?** `-32768`.
4. **`int n = 7; n += 2.9;` bằng gì?** `9`, do kết quả số thực 9.9 được chuyển về `int`, bỏ phần thập phân.
5. **`char c = 'A'; c += 1;` cho ký tự nào?** `'B'` (mã UTF-16 66).
6. **`int[] a = {10,20}; int i = 0; a[i++] += i;` cho mảng nào?** `a[0] == 11`, `a[1] == 20`, `i == 1`; vế trái `a[i++]` được đánh giá một lần.
7. **Có thể dùng `+=` để cộng an toàn không tràn không?** Không mặc định. Dùng kiểu đủ rộng, `Math.addExact`, và kiểm tra dải đích nếu cần thu hẹp.
8. **`String s = "A"; s += 5;` có thực hiện cộng số không?** Không, kết quả chuỗi là `"A5"`.
9. **`volatile int count; count += 1;` có nguyên tử với nhiều luồng không?** Không; cần đồng bộ hóa hoặc kiểu atomic nếu yêu cầu.

**Ghi nhớ:** `E1 op= E2` thực hiện phép toán theo quy tắc promotion, **chuyển kết quả về kiểu của vế trái**, và **chỉ đánh giá vế trái một lần**. Chính sự thu hẹp ngầm định này làm các câu lệnh `byte += int` hoặc `int += double` biên dịch được, nhưng cũng có thể âm thầm gây tràn, cắt bit hoặc mất phần thập phân. Viết ngắn không thay thế việc kiểm tra đúng kiểu và đúng phạm vi dữ liệu.
