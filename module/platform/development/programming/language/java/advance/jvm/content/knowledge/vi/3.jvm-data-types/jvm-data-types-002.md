# Kiểu int dùng cho nhiều phép toán trên byte, short, char và boolean

## 1. Mục tiêu bài học

Java có các kiểu nguyên thủy **byte**, **short**, **char**, **boolean** và **int**. Chúng khác nhau về giá trị hợp lệ, quy tắc kiểu trong mã nguồn và chữ ký phương thức. Tuy vậy, trong tập lệnh của Java Virtual Machine (JVM), phần lớn thao tác với bốn kiểu đầu được thực hiện thông qua **kiểu tính toán (computational type) int**.

Sau khi học, bạn có thể:

- Giải thích vì sao bytecode dùng các lệnh như **iload**, **istore**, **iadd**, **ifeq** và **ireturn** cho giá trị xuất phát từ **byte**, **short**, **char**, đôi khi cả **boolean**.
- Phân biệt **kiểu Java ở mã nguồn**, **kiểu khai báo/lưu trữ trong class file** và **kiểu tính toán trên operand stack**.
- Phân biệt **mở rộng dấu (sign extension)** của **byte/short** với **mở rộng bằng số 0 (zero extension)** của **char/boolean**.
- Hiểu numeric promotion, ép kiểu thu hẹp bằng **i2b/i2s/i2c**, và lý do một biểu thức cộng hai biến **byte** cho kết quả kiểu **int**.
- Giải thích tại sao dùng **int** để biểu diễn giá trị boolean trong JVM không cho phép cộng hoặc ép kiểu giữa **boolean** và **int** trong Java.
- Kiểm tra bytecode bằng **javap** và dự đoán chính xác kết quả của chương trình Java 17+.

Bài học bàn về mô hình được **đặc tả JVM** định nghĩa; không suy ra rằng JVM bắt buộc dùng bốn byte bộ nhớ vật lý cho từng biến boolean/byte/short/char khi chạy.

## 2. Hai tầng kiểu dữ liệu phải được phân biệt

**Tầng 1 — Ngôn ngữ Java (source-level types):**

| Kiểu | Miền giá trị | Đặc điểm |
| --- | --- | --- |
| **byte** | -128 đến 127 | Số nguyên có dấu 8 bit |
| **short** | -32768 đến 32767 | Số nguyên có dấu 16 bit |
| **char** | 0 đến 65535 | Đơn vị mã UTF-16 không dấu 16 bit; một **char** không nhất thiết là một ký tự Unicode hoàn chỉnh |
| **boolean** | **false**, **true** | Giá trị logic, không phải kiểu số trong Java |
| **int** | -2147483648 đến 2147483647 | Số nguyên có dấu 32 bit |

Ở tầng Java, những kiểu này **không hoán đổi tùy ý**. Chẳng hạn, phép cộng giữa hai biến **byte** cần dùng quy tắc numeric promotion; còn **boolean** không được chuyển thành số chỉ vì JVM có thể dùng một giá trị tính toán kiểu **int** để xử lý nó.

**Tầng 2 — Tập lệnh và frame của JVM:**

Một frame khi gọi phương thức có **bảng biến cục bộ (local variables)** và **ngăn xếp toán hạng (operand stack)**. JVM định nghĩa tập lệnh có chủ đích: hỗ trợ trực tiếp những nhóm toán hạng tính toán chính, thay vì tạo một phiên bản phép cộng hay load/store cho mọi kiểu nguồn.

Theo bảng ánh xạ kiểu tính toán trong JVM:

| Kiểu thực tế (actual type) | Kiểu tính toán (computational type) trên JVM | Category |
| --- | --- | --- |
| **boolean** | **int** | 1 |
| **byte** | **int** | 1 |
| **short** | **int** | 1 |
| **char** | **int** | 1 |
| **int** | **int** | 1 |
| **long** | **long** | 2 |
| **float** | **float** | 1 |
| **double** | **double** | 2 |

**Category 1** dùng một đơn vị slot trong mô hình JVM cho các lệnh xử lý operand stack; **long/double** thuộc **category 2**. Đây là khái niệm của máy ảo và bộ xác minh, **không phải** cam kết mỗi giá trị category 1 luôn chiếm bốn byte RAM trong một object hay thanh ghi máy thật.

Sơ đồ ý tưởng:

~~~text
Java source:
    byte a, b;
    byte c = (byte) (a + b);
               |
               v
      javac kiểm tra kiểu Java
               |
               v
JVM operand stack:
    iload a     -> một giá trị tính toán kiểu int
    iload b     -> một giá trị tính toán kiểu int
    iadd        -> kết quả kiểu int
    i2b         -> thu hẹp thành byte và sign-extend lại thành int
    istore c    -> lưu giá trị tính toán vào local slot
~~~

Khi mã truy cập **field**, mảng hoặc truyền/nhận phương thức, mô tả kiểu thật vẫn tồn tại; không có nghĩa tất cả mọi nơi đã đổi tên thành **int**.

## 3. Vì sao JVM dùng các lệnh int cho nhiều kiểu?

Mỗi opcode JVM có độ dài mã lệnh cơ bản là một byte. Nếu tất cả phép cộng, trừ, nhân, load, store, so sánh, trả về... đều cần opcode riêng cho từng kiểu nguyên thủy, tập lệnh sẽ phình to. JVM dùng tập lệnh không hoàn toàn đối xứng giữa các kiểu, và compiler thêm chuyển đổi ở điểm cần giữ nguyên ngữ nghĩa Java.

Ví dụ các lệnh thường gặp:

| Công việc | Lệnh xử lý qua **int** | Ý nghĩa |
| --- | --- | --- |
| Đưa local variable lên stack | **iload**, **iload_0**...**iload_3** | Đọc giá trị tính toán kiểu **int** từ slot |
| Ghi local variable từ stack | **istore**, **istore_0**...**istore_3** | Ghi giá trị tính toán **int** vào slot |
| Cộng, trừ, nhân | **iadd**, **isub**, **imul** | Toán học **int** |
| Chia, phần dư | **idiv**, **irem** | Toán học **int**; chia cho 0 gây **ArithmeticException** |
| AND, OR, XOR trên bit | **iand**, **ior**, **ixor** | Xử lý toán hạng tính toán **int** |
| Dịch bit | **ishl**, **ishr**, **iushr** | Phép dịch trên **int** |
| Nhánh | **ifeq**, **ifne**, **if_icmpeq**... | Kiểm tra giá trị **int**, đôi khi xuất phát từ boolean |
| Trả về | **ireturn** | Dùng cho phương thức khai báo trả **boolean**, **byte**, **short**, **char** hoặc **int** |
| Thu hẹp về kiểu nhỏ | **i2b**, **i2s**, **i2c** | Chuyển kết quả **int** thành giá trị mang ngữ nghĩa byte/short/char |

Không có lệnh **badd**, **sadd**, **cadd** hay **zadd** để cộng trực tiếp những kiểu đó. Không có **i2z** để biến một số thành boolean. Đây là dấu hiệu rõ của sự khác biệt giữa mô hình tính toán JVM và hệ thống kiểu Java.

Khi xem bytecode với **javap -c**, chữ **i** trong **iadd** hay **iload** chỉ **kiểu tính toán của instruction**, không chứng minh biến khai báo ở mã nguồn nhất thiết là **int**.

## 4. Mở rộng dấu và mở rộng bằng số 0

Khi một giá trị nhỏ được đưa lên operand stack, nó thường ở dạng computational **int**, nhưng phải giữ đúng ý nghĩa dấu:

- **byte** có dấu 8 bit và **short** có dấu 16 bit: dùng **sign extension**, sao chép bit dấu khi mở rộng lên 32 bit.
- **char** không dấu 16 bit: dùng **zero extension**, thêm các bit 0 ở phía cao.
- **boolean**: giá trị logic được biểu diễn qua computational **int**; compiler Java sử dụng cách mã hóa **false = 0**, **true = 1** và mô hình mở rộng bằng 0. Không được suy ra giá trị boolean là một số trong ngôn ngữ Java.

Ví dụ biểu diễn bit:

~~~text
byte -1:
    11111111             (8 bit)
          |
          v sign extension
    11111111 11111111 11111111 11111111   -> int -1

short -1:
    11111111 11111111    (16 bit)
          |
          v sign extension
    11111111 11111111 11111111 11111111   -> int -1

char '\uFFFF':
    11111111 11111111    (16 bit)
          |
          v zero extension
    00000000 00000000 11111111 11111111   -> int 65535
~~~

Điều này giải thích vì sao cùng mẫu bit thấp **FFFF**, **short** diễn giải là **-1** còn **char** diễn giải là **65535**. Phép toán bằng opcode **int** chỉ đúng khi giá trị đưa vào đã được mở rộng phù hợp.

### 4.1. Lệnh đọc mảng thể hiện rõ sự khác biệt

Mảng vẫn giữ kiểu phần tử; JVM có lệnh nạp phần tử riêng:

| Loại mảng | Lệnh nạp | Giá trị được đẩy lên operand stack |
| --- | --- | --- |
| **byte[]** | **baload** | Giá trị kiểu tính toán **int**, sign-extend từ byte |
| **short[]** | **saload** | Giá trị kiểu tính toán **int**, sign-extend từ short |
| **char[]** | **caload** | Giá trị kiểu tính toán **int**, zero-extend từ char |
| **boolean[]** | **baload** | Giá trị logic dạng computational **int**; JVM tái sử dụng lệnh này cho boolean array |
| **int[]** | **iaload** | Giá trị **int** |

Khi ghi về mảng, các lệnh tương ứng gồm **bastore** (byte/boolean), **sastore**, **castore** và **iastore**. Việc chia sẻ opcode **baload/bastore** không làm **boolean[]** và **byte[]** trở thành cùng một kiểu; Java vẫn kiểm tra kiểu tại compile time và runtime.

**Không suy diễn cấu trúc bộ nhớ:** JVM specification cho phép những chi tiết triển khai về biểu diễn của boolean; bảng opcode không chứng minh rằng boolean field hoặc phần tử mảng boolean bắt buộc chiếm một byte hay một int vật lý trên mọi JVM.

## 5. Numeric promotion: tại sao byte + byte lại ra int?

Quy tắc của **ngôn ngữ Java** gọi là **binary numeric promotion**: với nhiều toán tử số học như **+**, **-**, **\***, **/**, **%**, những toán hạng nhỏ hơn **int** (byte, short, char) được nâng lên ít nhất **int** trước khi thực hiện phép toán.

Ví dụ:

~~~java
// Mã minh họa bên trong một phương thức:
byte a = 10;
byte b = 20;

int sum = a + b;             // Hợp lệ: biểu thức a + b có kiểu int
byte narrow = (byte) (a + b); // Hợp lệ: ép kết quả về byte
~~~

Dòng dưới **không biên dịch**:

~~~java
byte a = 10;
byte b = 20;
byte invalid = a + b; // Compile-time error: int không tự thu hẹp về byte
~~~

Compiler không dựa vào việc hai giá trị tình cờ nhỏ để chấp nhận phép gán này, bởi **a** và **b** là biến và giá trị runtime có thể vượt giới hạn kiểu **byte**. JVM dùng **iadd** cho phép cộng; kiểm tra kiểu nguồn được thực hiện từ trước bởi **javac**.

Tương tự:

~~~java
short s = 300;
char c = 'A';

int x = s + 1; // 301
int y = c + 1; // 66, vì 'A' có giá trị mã UTF-16 là 65
~~~

**short + short**, **char + char**, **byte + char** cũng tạo **int** trong những trường hợp chỉ dùng các toán hạng nhỏ này. Nếu có **long**, **float** hoặc **double**, quy tắc promotion tiếp tục theo thứ tự tương ứng; không nên nói mọi phép số học trong JVM đều thành **int**.

Các toán tử **+** hoặc **-** một ngôi, **~**, và toán tử dịch bit cũng có quy tắc promotion riêng. Ví dụ **~(byte) 0** cho kết quả kiểu **int** với giá trị **-1**; **(byte) 1 << 8** có kiểu **int** với giá trị **256**.

### 5.1. Ngoại lệ có kiểm soát: hằng biểu thức

Java cho phép gán một số **biểu thức hằng có kiểu int** cho **byte/short/char** nếu giá trị được biết lúc biên dịch và nằm trong phạm vi đích.

~~~java
byte a = 10 + 20;       // Hợp lệ: hằng int 30 vừa byte
short s = 1000 + 2000;  // Hợp lệ: hằng int 3000 vừa short
char c = 65;            // Hợp lệ: hằng int 65 vừa char
final int code = 66;
char letter = code;     // Hợp lệ: code là constant variable kiểu int, giá trị vừa char
~~~

Ngược lại:

~~~java
byte tooLarge = 120 + 10; // Compile-time error: hằng 130 vượt giới hạn byte
int runtimeValue = 30;
byte cannotAssign = runtimeValue; // Compile-time error: biến int không được tự thu hẹp
~~~

Đây là quy tắc **gán hằng** của Java, không mâu thuẫn với việc phép cộng tạo biểu thức kiểu **int**. Đừng hiểu sai rằng javac luôn tự ép kiểu mọi biểu thức **int** về **byte** khi kết quả có vẻ nhỏ.

### 5.2. Phép gán kết hợp và ++ có thu hẹp ngầm

So sánh hai đoạn:

~~~java
byte b = 127;
// b = b + 1; // Không biên dịch: b + 1 là int
b += 1;       // Hợp lệ: gán kết hợp có bước thu hẹp về byte
~~~

**b += 1** có hiệu ứng giá trị giống **b = (byte) (b + 1)** khi vế trái là biến đơn giản, và vế trái của gán kết hợp chỉ được đánh giá một lần. Sau đó **b** có giá trị **-128** vì kết quả **128** bị thu hẹp về số có dấu 8 bit.

Với toán tử **b++** hoặc **b--**, Java cũng bảo đảm kết quả cuối được lưu về đúng kiểu biến; chúng không bắt người viết mã thêm cast tường minh.

**Lưu ý:** Quy tắc gán kết hợp và **++/--** dành cho các kiểu số; **boolean++**, **boolean += 1** hoặc **boolean + boolean** đều không hợp lệ trong Java.

## 6. Thu hẹp kết quả int: i2b, i2s, i2c

Khi tính toán qua **int** và cần trả kết quả về kiểu nhỏ, compiler có thể sinh các lệnh chuyển đổi:

| Lệnh | Hành vi khái quát | Ví dụ đầu vào **int** | Kết quả theo ngữ nghĩa kiểu đích |
| --- | --- | --- | --- |
| **i2b** | Giữ 8 bit thấp rồi diễn giải là byte có dấu; giá trị tính toán trên stack được sign-extend lại thành int | 130 | -126 |
| **i2s** | Giữ 16 bit thấp rồi diễn giải là short có dấu; sign-extend lại thành int | 32768 | -32768 |
| **i2c** | Giữ 16 bit thấp và diễn giải là char không dấu; zero-extend lại thành int | -1 | 65535 |

Vì vậy, **i2b** không phải lệnh biến operand stack thành “stack chứa ô byte 8 bit”. Operand stack tiếp tục làm việc với computational **int**, nhưng giá trị đã được chuẩn hóa theo kiểu nhỏ.

Ví dụ:

~~~text
130 ở dạng int
    |
    v i2b
8 bit thấp: 10000010
    |
    v diễn giải byte có dấu rồi sign-extend
-126 (một giá trị tính toán int)

-1 ở dạng int
    |
    v i2c
16 bit thấp: 11111111 11111111
    |
    v zero-extend
65535 (một giá trị tính toán int)
~~~

Khi không có yêu cầu thu hẹp từ **int** trở lại kiểu nhỏ, compiler không nhất thiết chèn **i2b/i2s/i2c** vào từng biểu thức. Cũng không phải cứ một biểu thức Java xuất hiện cast là bản bytecode của mọi compiler bắt buộc có một instruction chuyển đổi riêng; tối ưu hằng biểu thức có thể xảy ra ngay khi biên dịch.

## 7. Boolean là trường hợp đặc biệt quan trọng

JVM không có một bộ opcode đầy đủ riêng cho **boolean**. Trong mã do Java compiler tạo, **boolean** thường đi qua **int** để dùng lệnh nạp, lưu, kiểm tra nhánh hoặc trả về.

Ví dụ mã nguồn:

~~~java
// Mã minh họa bên trong một phương thức:
boolean ready = true;
boolean active = false;
boolean allowed = ready && active;
~~~

Compiler có thể dùng các lệnh nhánh trên computational **int** như **ifeq/ifne** để hiện thực **&&** theo kiểu đoản mạch (short circuit). Với **&**, **|**, **^** áp dụng cho hai toán hạng **boolean**, phép toán logic không đoản mạch vẫn hợp lệ; các lệnh như **iand/ior/ixor** có thể được dùng khi compiler tạo mã thích hợp.

**Cần phân biệt hai phát biểu:**

1. **Đúng ở tầng JVM:** các giá trị logic có thể được xử lý bằng computational **int**; đối với mã Java hợp lệ, giá trị boolean thông thường được mã hóa bằng 0 hoặc 1.
2. **Sai ở tầng Java:** boolean là số nguyên và có thể cộng, nhân, so sánh lớn hơn hoặc ép sang int. Java không cho phép **boolean value = 1**, **int x = true**, **(int) true**, **true + false** hay **true < false**.

**boolean** không tham gia binary numeric promotion của ngôn ngữ Java. Quy tắc mở rộng số của **byte/short/char** và cách JVM biểu diễn boolean ở runtime là **hai cơ chế khác nhau**.

Ngoài ra:

- **boolean** được phép dùng **!**, **&&**, **||**, **&**, **|**, **^**, **==**, **!=** và điều kiện của **if/while**.
- **&&/||** luôn giữ ngữ nghĩa đoản mạch trong Java. Việc JVM dùng nhánh **int** không cho phép bỏ qua quy tắc này.
- Một phương thức khai báo trả về **boolean** thường dùng **ireturn** như các kiểu nhỏ khác, nhưng chữ ký vẫn đánh dấu nó bằng descriptor **Z**, không phải **I**.
- JVM có **boolean[]** như một loại mảng riêng; thao tác truy cập phần tử chia sẻ instruction với **byte[]** nhưng không đồng nghĩa với phép chuyển kiểu giữa hai mảng.
- **boolean** là kiểu logic với hai giá trị theo Java; hành vi của bytecode tùy ý tự tạo và mã vi phạm các quy ước compiler không được dùng làm lý do suy ngược một phép chuyển đổi boolean ↔ int ở Java source.

## 8. Ví dụ Java 17+ chạy được và output chính xác

Tạo tệp **IntComputationalTypeDemo.java**:

~~~java
public class IntComputationalTypeDemo {
    static byte addBytes(byte a, byte b) {
        return (byte) (a + b);
    }

    static short addShorts(short a, short b) {
        return (short) (a + b);
    }

    static char nextChar(char value) {
        return (char) (value + 1);
    }

    static boolean both(boolean left, boolean right) {
        return left && right;
    }

    static int doubleByte(byte value) {
        return value * 2;
    }

    public static void main(String[] args) {
        byte first = 120;
        byte second = 10;

        System.out.println("sumAsInt=" + (first + second));
        System.out.println("sumAsByte=" + addBytes(first, second));

        short maxShort = 32767;
        System.out.println("shortWrap=" + addShorts(maxShort, (short) 1));

        System.out.println("nextChar=" + nextChar('A'));
        System.out.println("charPlusOneAsInt=" + ('A' + 1));

        System.out.println("both=" + both(true, false));
        System.out.println("doubleByte=" + doubleByte((byte) -2));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 IntComputationalTypeDemo.java
java IntComputationalTypeDemo
~~~

**Stdout:**

~~~text
sumAsInt=130
sumAsByte=-126
shortWrap=-32768
nextChar=B
charPlusOneAsInt=66
both=false
doubleByte=-4
~~~

Phân tích từng trường hợp:

1. **first + second** thực hiện phép cộng kiểu **int**: 120 + 10 = **130**.
2. **addBytes** cũng cộng qua **int**, nhưng cast kết quả về **byte** giữ 8 bit thấp. Giá trị 130 trở thành **-126** khi diễn giải dưới dạng byte có dấu.
3. **32767 + 1** tính ra **32768** dưới dạng **int**; ép về **short** cho **-32768**.
4. **'A' + 1** có kiểu **int**, tương đương 65 + 1 = **66**. Trong **nextChar**, cast đưa kết quả về **char**, và **System.out.println** nhận giá trị **char** nên in ký tự **B**.
5. **both(true, false)** trả **false** đúng theo phép logic Java; không có phép cộng boolean.
6. **doubleByte((byte) -2)** mở rộng giá trị byte **-2** thành computational **int**, nhân 2 được **-4**, và trả về **int** mà không cần thu hẹp.

Ví dụ dùng các phép toán cố định, không phụ thuộc múi giờ, locale hoặc filesystem. **Stdout** ở trên là kết quả của chương trình, không phải toàn bộ output của trình biên dịch hay công cụ bytecode.

## 9. Kiểm chứng với javap: lời giải thích được thấy trong bytecode

Sau khi biên dịch, chạy:

~~~bash
javap -c -p IntComputationalTypeDemo
javap -s -p IntComputationalTypeDemo
~~~

Lệnh **javap -c** giải mã instructions, còn **javap -s** hiện method descriptors. Hai lệnh này dùng cho quan sát cấu trúc, không thay thế việc chạy chương trình để xác minh output.

### 9.1. Theo dấu addBytes

Với **javac** thông dụng, thân bytecode của phương thức **addBytes(byte, byte)** có dạng:

~~~text
iload_0
iload_1
iadd
i2b
ireturn
~~~

Có thể có tiền tố offset như **0:**, **1:** hoặc chi tiết hiển thị khác; dãy mnemonic này mới là điểm cần quan sát.

Giải thích:

- **iload_0** đưa tham số **a** từ local slot 0 lên stack dưới dạng computational **int**.
- **iload_1** làm tương tự với tham số **b**.
- **iadd** tiêu thụ hai toán hạng **int** và đẩy tổng **int** lên stack.
- **i2b** thu hẹp tổng theo quy tắc byte và đưa kết quả đã sign-extend trở lại dạng computational **int**.
- **ireturn** trả giá trị cho phương thức khai báo kiểu **byte**.

Với chương trình mẫu, compiler không thể thay toàn bộ phương thức thành một hằng cố định bởi tham số thay đổi theo lần gọi. Việc có **iadd** và **i2b** cho thấy tường minh hai giai đoạn tính toán và thu hẹp.

### 9.2. Theo dấu short, char và boolean

Trong **addShorts(short, short)**, chú ý các lệnh **iadd**, **i2s**, **ireturn**. Trong **nextChar(char)**, chú ý **iadd**, **i2c**, **ireturn**. Trong **doubleByte(byte)**, chú ý **imul** và **ireturn**; kiểu trả về là **int** nên không cần chuyển về **byte**.

Ở **both(boolean, boolean)**, compiler có thể tổ chức nhánh **ifeq** hoặc cách kiểm tra tương đương để giữ ngữ nghĩa **&&**: nếu **left** là false thì bỏ qua đánh giá **right** ở cấp ngôn ngữ. Với hai biến tham số thuần như ví dụ, output không cho thấy khác biệt về side effect; quy tắc đoản mạch vẫn phải được bảo toàn khi toán hạng là biểu thức có side effect.

### 9.3. Chữ ký vẫn giữ nguyên kiểu Java

**javap -s -p** sẽ cho các descriptors của phương thức ví dụ:

| Phương thức | Descriptor JVM | Diễn giải |
| --- | --- | --- |
| **addBytes(byte, byte)** | **(BB)B** | Hai byte vào, một byte ra |
| **addShorts(short, short)** | **(SS)S** | Hai short vào, một short ra |
| **nextChar(char)** | **(C)C** | Một char vào, một char ra |
| **both(boolean, boolean)** | **(ZZ)Z** | Hai boolean vào, một boolean ra |
| **doubleByte(byte)** | **(B)I** | Một byte vào, một int ra |

Những ký hiệu descriptor chính là **B** (byte), **S** (short), **C** (char), **Z** (boolean), **I** (int). Sự tồn tại của **(BB)B** cạnh các instruction **iadd/ireturn** là bằng chứng rõ: **tính toán qua int không xóa danh tính kiểu của phương thức**.

Khi xem **LocalVariableTable** trong một class có thông tin debug, bạn cũng có thể thấy descriptor khai báo của các biến. Tuy nhiên bảng debug này có thể không tồn tại; **javap -c** không cần thông tin debug để hiện instructions.

## 10. Ví dụ mảng: byte/short mở rộng dấu, char mở rộng bằng số 0

Tạo một chương trình độc lập **ArrayLoadDemo.java**:

~~~java
public class ArrayLoadDemo {
    public static void main(String[] args) {
        byte[] bytes = {(byte) 0xFF};
        short[] shorts = {(short) 0xFFFF};
        char[] chars = {(char) 0xFFFF};
        boolean[] flags = {true};

        int fromByte = bytes[0];
        int fromShort = shorts[0];
        int fromChar = chars[0];

        System.out.println("byte=" + fromByte);
        System.out.println("short=" + fromShort);
        System.out.println("char=" + fromChar);
        System.out.println("boolean=" + flags[0]);
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 ArrayLoadDemo.java
java ArrayLoadDemo
~~~

**Stdout:**

~~~text
byte=-1
short=-1
char=65535
boolean=true
~~~

Các số **0xFF** và **0xFFFF** là literal số nguyên dạng hexadecimal. Cast giúp khởi tạo đúng các mảng đích:

- **(byte) 0xFF** trở thành **-1**; **baload** đọc và sign-extend lên int.
- **(short) 0xFFFF** trở thành **-1**; **saload** đọc và sign-extend.
- **(char) 0xFFFF** biểu diễn **65535**; **caload** đọc và zero-extend.
- **flags[0]** có kiểu Java **boolean**; khi in, Java hiển thị chữ **true**, không hiển thị số 1, mặc dù bytecode có thể dùng computational int để xử lý logic.

Dùng **javap -c ArrayLoadDemo** để tìm các lệnh **baload**, **saload**, **caload**. Nếu nhìn thấy **baload** cho boolean array, hãy nhớ opcode đó được JVM định nghĩa dùng được cho cả byte array và boolean array, không phải chứng cứ hai mảng có cùng kiểu ở Java.

## 11. Các lỗi phổ biến và cách giải thích theo đúng tầng

### Lỗi 1: “Đã dùng iadd thì byte biến thành int hoàn toàn”

Không đúng. Biểu thức cộng trong Java được nâng kiểu thành **int**, nhưng khai báo **byte** của tham số, field, array hay kiểu trả về vẫn có ý nghĩa. Compiler phải chèn chuyển đổi ở điểm gán/trả về kiểu nhỏ khi cần. Class file lưu descriptor tương ứng và JVM bảo vệ các ràng buộc kiểu.

### Lỗi 2: “JVM lưu mọi byte/char/boolean thành bốn byte”

Không thể kết luận từ instruction set. **int** là kiểu tính toán trên operand stack; field, mảng, object layout và tối ưu JIT là chuyện khác. Ví dụ boolean array, object field padding hoặc thanh ghi CPU do triển khai JVM quyết định trong giới hạn đặc tả. Cần dùng công cụ đo và tài liệu JVM cụ thể nếu quan tâm kích thước bộ nhớ thực.

### Lỗi 3: “byte + byte có kiểu byte, vì cả hai toán hạng nhỏ”

Sai đối với biểu thức Java dùng các biến **byte**: phép cộng có kiểu **int**. Chỉ có trường hợp gán hằng trong phạm vi hoặc phép cast/gán kết hợp phù hợp mới đưa kết quả trở lại **byte** mà không báo lỗi compile.

### Lỗi 4: “boolean là số 0 hoặc 1 nên có thể cộng”

Không hợp lệ ở mã nguồn Java. Boolean có hệ thống toán tử riêng; việc sử dụng computational int để hiện thực điều kiện là chi tiết JVM. Không có chuyển đổi Java hợp lệ **boolean ↔ int** bằng cast thông thường.

### Lỗi 5: “char có dấu giống short”

Sai. **char** là đơn vị mã UTF-16 **không dấu**; **short** là số có dấu. Cùng 16 bit thấp **FFFF**, cast về **char** cho 65535 trong biểu thức số, còn cast về **short** cho -1.

### Lỗi 6: “i2b chỉ lấy 8 bit rồi để nguyên số dương”

Không đúng khi bit cao nhất trong 8 bit còn lại là 1. Kết quả byte có dấu sẽ được **sign-extend** khi trở lại computational int, ví dụ 130 → -126.

### Lỗi 7: “Mọi phép toán với kiểu nhỏ luôn phải có i2b/i2s/i2c”

Không bắt buộc. Chỉ khi cần bảo toàn ngữ nghĩa kiểu đích hoặc mã compiler lựa chọn; phép toán cho kết quả **int** có thể dừng ở **iadd**. Hằng biểu thức còn có thể được tính tại compile time.

### Lỗi 8: “Chỉ cần đọc mã nguồn là biết chính xác mọi opcode javac sinh ra”

Cần kiểm tra class file thực. Compiler, phiên bản JDK và tối ưu có thể thay đổi trình tự bytecode tương đương. **javap** là công cụ đọc bằng chứng, còn JVM specification giải thích ngữ nghĩa instruction.

## 12. Bài tập dự đoán và tự kiểm tra

**Bài 1.** Tại sao đoạn này lỗi compile?

~~~java
byte x = 100;
byte y = 20;
byte z = x + y;
~~~

**Đáp án:** **x + y** có kiểu **int**, không được tự động gán về **byte** dù lần chạy cụ thể có thể ra 120. Sửa thành **int z = x + y;**, hoặc cast tường minh nếu chủ động chấp nhận thu hẹp.

**Bài 2.** Kết quả của đoạn này là gì?

~~~java
short s = 32767;
s++;
System.out.println(s);
~~~

**Đáp án:** **-32768**. Phép tăng dùng ngữ nghĩa số học, sau đó lưu lại kết quả theo phạm vi **short**, dẫn đến vòng về giá trị âm nhỏ nhất.

**Bài 3.** Biểu thức **(char) -1** mang giá trị số nào khi tham gia một phép toán kiểu int?

**Đáp án:** **65535**. **i2c** giữ 16 bit thấp và zero-extend. Nếu in giá trị này bằng **println(char)** có thể hiển thị ký tự không dễ quan sát; dùng ép sang **int** khi muốn xem trị số.

**Bài 4.** Có thể viết **int n = true + false;** nếu JVM dùng int cho boolean không?

**Đáp án:** Không. Java source không xem boolean là toán hạng số và không có phép cộng boolean.

**Bài 5.** Vì sao **javap** có **iload** với phương thức nhận **byte** nhưng **javap -s** vẫn báo **(BB)B**?

**Đáp án:** **iload** biểu thị computational type của instruction trong frame; **B** trong method descriptor biểu thị kiểu thật ở ranh giới phương thức. Hai thông tin thuộc hai tầng khác nhau và nhất quán với nhau.

**Bài 6.** Với **byte a = 120; byte b = 10;**, kết quả của **a + b** và **(byte) (a + b)** lần lượt là gì?

**Đáp án:** **130** kiểu **int** và **-126** kiểu **byte**. Nhớ rằng việc cast không làm phép cộng ban đầu đổi thành opcode cộng byte.

## 13. Khi nào cần hiểu chi tiết này?

Kiến thức này hữu ích khi:

- **Đọc bytecode**: không nhầm **iload/iadd/ireturn** là biến Java ban đầu có kiểu **int**.
- **Điều tra kết quả tràn số**: phân biệt bước cộng **int** với bước thu hẹp về **byte/short**.
- **Hiểu chương trình xử lý ký tự**: không nhầm **char** không dấu với **short** có dấu hay với một Unicode code point hoàn chỉnh.
- **Phân tích điều kiện**: hiểu tại sao mã xử lý **boolean** có các nhánh trên computational int nhưng vẫn phải tuân thủ logic Java.
- **Viết công cụ bytecode, compiler, instrumentation**: phải tuân theo descriptor, stack typing, chuyển đổi và các ràng buộc verifier, thay vì chỉ nhìn chữ **i** trong opcode.
- **Đánh giá hiệu năng/bộ nhớ**: tránh suy diễn layout object hoặc số byte RAM từ mô hình instruction của JVM; đo lường trên runtime cụ thể.

### Tài liệu đặc tả để đối chiếu

- Java Virtual Machine Specification, Java SE 17, chương **2.11.1 — Types and the Java Virtual Machine**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.1
- Java Virtual Machine Specification, Java SE 17, chương **2.11.4 — Type Conversion Instructions**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.4
- Java Language Specification, Java SE 17, chương **5 — Conversions and Contexts**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html
- Java Language Specification, Java SE 17, chương **15 — Expressions**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html

**Ghi nhớ cốt lõi:** Trong JVM, **byte**, **short**, **char** và **boolean** thường dùng **int** như **kiểu tính toán** trên operand stack và trong các lệnh load/store, so sánh, trả về. **byte/short** mở rộng dấu, **char/boolean** được xử lý với biểu diễn không dấu khi đưa lên stack; chuyển về các kiểu số nhỏ dùng **i2b/i2s/i2c** theo nhu cầu. Nhưng **Java vẫn duy trì kiểu nguồn riêng**: phép cộng byte/short/char theo numeric promotion cho kết quả **int**, còn **boolean tuyệt đối không trở thành kiểu số** chỉ vì cách hiện thực bytecode.
