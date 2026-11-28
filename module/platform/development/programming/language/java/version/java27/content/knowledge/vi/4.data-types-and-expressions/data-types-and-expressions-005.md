# Toán tử số học, logic, bit và thứ tự ưu tiên trong Java

Trong Java 27, toán tử là ký hiệu kết hợp các toán hạng để tạo thành biểu thức. Biểu thức có thể tính ra một giá trị, tạo ra một giá trị boolean, hoặc thực hiện phép gán và thay đổi trạng thái. Hiểu rõ kiểu dữ liệu của toán hạng, cách Java chuyển kiểu, thứ tự ưu tiên và quy tắc đánh giá giúp tránh những lỗi khó nhận ra trong phép tính và điều kiện.

Bài học này thuộc chương **Kiểu dữ liệu và biểu thức** của module Java 27. Các quy tắc và ví dụ dưới đây sử dụng cú pháp Java hiện hành; không dựa vào hành vi của các phiên bản đã lỗi thời.

## 1. Các nhóm toán tử

Java có nhiều nhóm toán tử. Những nhóm chính liên quan đến phép tính và biểu thức điều kiện được tóm tắt dưới đây.

| Nhóm | Toán tử | Công dụng |
|---|---|---|
| Số học | `+`, `-`, `*`, `/`, `%` | Cộng, trừ, nhân, chia và lấy phần dư |
| Một ngôi | `+`, `-`, `++`, `--` | Giữ dấu, đổi dấu, tăng hoặc giảm một đơn vị |
| So sánh | `<`, `<=`, `>`, `>=`, `==`, `!=` | So sánh hai giá trị |
| Logic | `!`, `&&`, `||` | Phủ định, AND có đoản mạch và OR có đoản mạch |
| Bit | `~`, `&`, `|`, `^` | Đảo bit, AND, OR và XOR |
| Dịch bit | `<<`, `>>`, `>>>` | Dịch trái, dịch phải có giữ dấu và dịch phải điền bit 0 |
| Điều kiện | `?:` | Chọn một trong hai biểu thức theo điều kiện |
| Gán | `=`, `+=`, `-=`, `*=`, `/=`, `%=`, ... | Gán hoặc thực hiện phép toán rồi gán lại |

Một số ký hiệu có thể thuộc nhiều ngữ cảnh. Chẳng hạn, `+` vừa cộng số vừa nối chuỗi; `&`, `|` và `^` có thể thao tác trên bit của số nguyên hoặc kết hợp giá trị boolean.

## 2. Toán tử số học

### 2.1. Các phép toán cơ bản

Các toán tử số học nhị phân thường dùng là:

| Toán tử | Ý nghĩa | Ví dụ | Kết quả |
|---|---|---|---:|
| `+` | Cộng | `12 + 5` | `17` |
| `-` | Trừ | `12 - 5` | `7` |
| `*` | Nhân | `12 * 5` | `60` |
| `/` | Chia | `12 / 5` | `2` nếu là số nguyên |
| `%` | Phần dư | `12 % 5` | `2` |

Ví dụ:

```java
int quantity = 17;
int boxSize = 5;

int fullBoxes = quantity / boxSize;
int remaining = quantity % boxSize;

System.out.println(fullBoxes); // 3
System.out.println(remaining); // 2
```

### 2.2. Chia số nguyên và phép chia số thực

Khi cả hai toán hạng của phép chia là kiểu nguyên, Java thực hiện phép chia số nguyên và bỏ phần thập phân bằng cách làm tròn về 0:

```java
System.out.println(7 / 2);    // 3
System.out.println(-7 / 2);   // -3
System.out.println(7 / -2);   // -3
System.out.println(7.0 / 2);  // 3.5
```

Muốn giữ phần thập phân, ít nhất một toán hạng phải là kiểu dấu phẩy động, chẳng hạn `float` hoặc `double`. Việc ép kiểu cần diễn ra trước phép chia:

```java
int total = 7;
int count = 2;

double average = (double) total / count;
System.out.println(average); // 3.5
```

Nếu viết `(double) (total / count)`, phép chia số nguyên đã xảy ra trước khi chuyển kết quả sang `double`, nên kết quả vẫn là `3.0`.

Chia một số nguyên cho `0` gây `ArithmeticException`. Với số dấu phẩy động, phép chia cho `0.0` tạo ra giá trị vô cực hoặc `NaN` theo quy tắc số thực của Java:

```java
System.out.println(1.0 / 0.0); // Infinity
System.out.println(0.0 / 0.0); // NaN
```

### 2.3. Phép chia lấy phần dư

Toán tử `%` trả về phần dư của phép chia. Với toán hạng nguyên, dấu của phần dư cùng dấu với toán hạng bên trái:

```java
System.out.println(7 % 3);    // 1
System.out.println(-7 % 3);   // -1
System.out.println(7 % -3);   // 1
System.out.println(-7 % -3);  // -1
```

Do đó, `%` trong Java là phép remainder (phần dư), không phải lúc nào cũng cho kết quả modulo không âm. Nếu cần phần dư theo phép chia làm tròn xuống, có thể dùng `Math.floorMod(a, b)`; kết quả của phương thức này có dấu cùng với số chia.

### 2.4. Tràn số nguyên và độ chính xác số thực

Các kiểu nguyên `byte`, `short`, `char`, `int` và `long` có phạm vi biểu diễn cố định. Trong phép tính, `byte`, `short` và `char` thường được mở rộng thành `int`; vì vậy phép cộng, trừ hoặc nhân được thực hiện ở kiểu đã mở rộng. Khi phép toán trên `int` hoặc `long` vượt phạm vi của kiểu tính toán, kết quả tràn theo biểu diễn số nguyên của Java và thông thường không tự động ném ngoại lệ. Việc ép kết quả về `byte` hoặc `short` cũng có thể làm mất các bit cao.

```java
int maximum = Integer.MAX_VALUE;
int result = maximum + 1;

System.out.println(result); // -2147483648
```

Nếu ứng dụng cần phát hiện tràn, có thể dùng các phương thức như `Math.addExact`, `Math.subtractExact` và `Math.multiplyExact`. Các phương thức này ném `ArithmeticException` khi phép toán nguyên vượt phạm vi.

Các kiểu `float` và `double` biểu diễn số dấu phẩy động theo chuẩn IEEE 754. Nhiều số thập phân không thể biểu diễn chính xác bằng dạng nhị phân, vì vậy kết quả phép tính có thể có sai số làm tròn:

```java
double value = 0.1 + 0.2;
System.out.println(value); // thường hiển thị 0.30000000000000004
```

Khi so sánh kết quả tính toán dấu phẩy động, hãy cân nhắc một sai số cho phép (epsilon) phù hợp với bài toán thay vì mặc định rằng hai kết quả phải bằng nhau tuyệt đối.

### 2.5. Tăng, giảm và đổi dấu

Toán tử một ngôi `++` tăng biến lên 1; `--` giảm biến đi 1. Dạng tiền tố và hậu tố khác nhau ở giá trị của biểu thức:

```java
int number = 4;

int before = number++; // before = 4, number = 5
int after = ++number;  // number = 6, after = 6

System.out.println(before); // 4
System.out.println(after);  // 6
System.out.println(number); // 6
```

- `number++`: lấy giá trị hiện tại làm giá trị của biểu thức, sau đó tăng biến.
- `++number`: tăng biến trước, rồi dùng giá trị mới làm giá trị của biểu thức.
- `number--` và `--number` có quy tắc tương tự theo chiều giảm.

Toán tử một ngôi `+` giữ nguyên dấu; `-` đổi dấu:

```java
int temperature = 8;
System.out.println(+temperature); // 8
System.out.println(-temperature); // -8
```

Tránh ghép nhiều phép tăng/giảm trên cùng một biến trong một biểu thức phức tạp. Viết thành các câu lệnh riêng giúp thứ tự thay đổi trạng thái rõ ràng hơn.

### 2.6. Toán tử cộng với chuỗi

Khi một toán hạng của `+` là `String`, toán tử này thực hiện nối chuỗi. Biểu thức được nhóm theo thứ tự ưu tiên và tính kết hợp của toán tử:

```java
System.out.println(1 + 2 + "3"); // "33"
System.out.println("1" + 2 + 3); // "123"
System.out.println("Total: " + (1 + 2)); // "Total: 3"
```

Phép cộng số học được thực hiện trước khi nối chuỗi nếu các toán hạng số được nhóm trước. Khi cần tính toán trong một chuỗi thông báo, hãy dùng dấu ngoặc để thể hiện rõ ý định.

## 3. Chuyển kiểu số trong biểu thức

Trước nhiều phép toán số học, Java áp dụng *numeric promotion* (mở rộng kiểu số) để đưa các toán hạng về kiểu phù hợp. Điều này giải thích vì sao kết quả của phép tính trên `byte`, `short` hoặc `char` thường có kiểu `int`.

### 3.1. Unary numeric promotion

Trong ngữ cảnh số học một ngôi và một số ngữ cảnh khác, `byte`, `short` và `char` được mở rộng thành `int`. `int`, `long`, `float` và `double` giữ kiểu tương ứng.

```java
byte first = 10;
byte second = 20;

int sum = first + second; // kết quả có kiểu int
// byte total = first + second; // lỗi biên dịch
byte total = (byte) (first + second);
```

### 3.2. Binary numeric promotion

Với phép toán nhị phân trên các kiểu số, Java chọn kiểu chung theo thứ tự:

1. Nếu có toán hạng `double`, kết quả dùng `double`.
2. Nếu không có `double` nhưng có `float`, kết quả dùng `float`.
3. Nếu không có hai kiểu trên nhưng có `long`, kết quả dùng `long`.
4. Nếu không, các toán hạng được xử lý như `int`.

Ví dụ:

```java
byte small = 2;
int integer = 3;
long large = 4L;
float decimal = 1.5F;

var first = small + integer; // int
var second = integer + large; // long
var third = large + decimal; // float
```

Từ khóa `var` trong ví dụ suy luận kiểu biến cục bộ từ kiểu của biểu thức bên phải; nó không làm thay đổi quy tắc chuyển kiểu của toán tử.

### 3.3. Gán kết hợp với phép toán

Java cung cấp các toán tử gán kết hợp như `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `|=`, `^=`, `<<=`, `>>=` và `>>>=`.

```java
int score = 10;
score += 5; // tương đương về kết quả với score = score + 5
score *= 2; // score = 30
```

Gán kết hợp có quy tắc chuyển về kiểu của biến bên trái. Vì thế:

```java
byte count = 10;
count += 1;          // hợp lệ
// count = count + 1; // lỗi: count + 1 có kiểu int
```

Với biểu thức có vế trái phức tạp như phần tử mảng hoặc field, gán kết hợp cũng chỉ đánh giá vị trí đích một lần. Đây là điểm khác biệt cần lưu ý khi biểu thức có tác dụng phụ.

## 4. Toán tử so sánh

Toán tử so sánh tạo ra kết quả kiểu `boolean`, tức `true` hoặc `false`.

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `<` | Nhỏ hơn | `age < 18` |
| `<=` | Nhỏ hơn hoặc bằng | `score <= 100` |
| `>` | Lớn hơn | `temperature > 30` |
| `>=` | Lớn hơn hoặc bằng | `quantity >= 1` |
| `==` | Bằng | `left == right` |
| `!=` | Khác | `left != right` |

Bốn toán tử `<`, `<=`, `>`, `>=` dùng để so sánh các giá trị số nguyên hoặc dấu phẩy động. Chúng không dùng để so sánh thứ tự hai đối tượng `String`.

### 4.1. So sánh giá trị nguyên thủy và tham chiếu

Với kiểu nguyên thủy, `==` so sánh giá trị. Với kiểu tham chiếu, `==` kiểm tra hai tham chiếu có trỏ đến cùng một đối tượng hay không (hoặc cả hai cùng là `null`).

```java
int first = 10;
int second = 10;
System.out.println(first == second); // true

String name1 = new String("Java");
String name2 = new String("Java");

System.out.println(name1 == name2);      // false: hai đối tượng khác nhau
System.out.println(name1.equals(name2)); // true: nội dung bằng nhau
```

Khi cần so sánh nội dung chuỗi, dùng `equals` hoặc `equalsIgnoreCase` tùy yêu cầu. Nếu cần so sánh an toàn khi một giá trị có thể là `null`, có thể dùng `Objects.equals(a, b)`.

### 4.2. So sánh số dấu phẩy động

Các giá trị đặc biệt của `double` và `float` có quy tắc so sánh riêng:

- `NaN == NaN` là `false`.
- `NaN != NaN` là `true`.
- `+0.0 == -0.0` là `true`.

Vì vậy, để kiểm tra một giá trị có phải `NaN` hay không, dùng `Double.isNaN(value)` hoặc `Float.isNaN(value)`.

## 5. Toán tử logic

Các toán tử logic làm việc với giá trị boolean. Chúng thường được dùng để kết hợp nhiều điều kiện trong câu lệnh `if`, `while` hoặc biểu thức điều kiện khác.

| Toán tử | Tên | Kết quả |
|---|---|---|
| `!` | NOT | Đảo `true` thành `false` và ngược lại |
| `&&` | AND có đoản mạch | `true` khi cả hai điều kiện đúng |
| `||` | OR có đoản mạch | `true` khi ít nhất một điều kiện đúng |

### 5.1. Phủ định logic

```java
boolean isActive = true;
System.out.println(!isActive); // false
```

### 5.2. AND và OR có đoản mạch

`&&` chỉ đánh giá toán hạng bên phải nếu toán hạng bên trái là `true`. Nếu vế trái là `false`, toàn biểu thức chắc chắn là `false`, nên vế phải được bỏ qua.

`||` chỉ đánh giá toán hạng bên phải nếu toán hạng bên trái là `false`. Nếu vế trái là `true`, toàn biểu thức chắc chắn là `true`.

```java
String name = null;

if (name != null && !name.isBlank()) {
    System.out.println(name);
}
```

Trong ví dụ, `name.isBlank()` chỉ được gọi khi `name != null` là `true`. Đây là cách phổ biến để bảo vệ thao tác có thể gây lỗi nếu đối tượng là `null`.

Ví dụ khác:

```java
boolean hasAdminRole = true;
boolean accountLocked = false;

if (hasAdminRole || !accountLocked) {
    System.out.println("Access condition passed");
}
```

### 5.3. Kết hợp điều kiện và dấu ngoặc

Dùng dấu ngoặc khi điều kiện có nhiều nhóm để biểu đạt ý định rõ ràng:

```java
int age = 22;
boolean hasTicket = true;
boolean withGuardian = false;

boolean canEnter = age >= 18 && hasTicket
        || withGuardian && hasTicket;
```

Biểu thức trên tương đương:

```java
boolean canEnter = (age >= 18 && hasTicket)
        || (withGuardian && hasTicket);
```

Dù Java có quy tắc ưu tiên xác định, dấu ngoặc giúp người đọc nhìn thấy các nhóm điều kiện ngay lập tức.

## 6. Toán tử bit

Toán tử bit thao tác trực tiếp trên các bit của kiểu số nguyên. Java hỗ trợ các kiểu nguyên `byte`, `short`, `char`, `int` và `long`; trong biểu thức bit, các kiểu nhỏ hơn `int` thường được mở rộng thành `int` trước khi thực hiện phép toán. Riêng `&`, `|` và `^` cũng nhận hai toán hạng `boolean`; khi đó chúng kết hợp giá trị logic nhưng vẫn đánh giá cả hai toán hạng.

| Toán tử | Tên | Quy tắc trên từng bit |
|---|---|---|
| `~` | NOT bit | Đảo 0 thành 1 và 1 thành 0 |
| `&` | AND bit | Kết quả là 1 khi cả hai bit là 1 |
| `|` | OR bit | Kết quả là 1 khi ít nhất một bit là 1 |
| `^` | XOR bit | Kết quả là 1 khi hai bit khác nhau |

### 6.1. Biểu diễn nhị phân và ví dụ

Với `int`, Java dùng 32 bit; với `long`, Java dùng 64 bit. Ví dụ các phép toán trên hai số nguyên nhỏ:

```java
int a = 6; // 0110
int b = 3; // 0011

System.out.println(a & b); // 2: 0010
System.out.println(a | b); // 7: 0111
System.out.println(a ^ b); // 5: 0101
System.out.println(~a);    // -7
```

Toán tử `~` đảo toàn bộ bit của giá trị sau khi áp dụng unary numeric promotion. Do số nguyên Java là kiểu có dấu, kết quả thường không phải số dương. Ví dụ `~6` bằng `-7`.

### 6.2. Dùng bit mask

Bit mask cho phép lưu nhiều cờ boolean trong một biến số nguyên. Mỗi cờ sử dụng một bit riêng:

```java
final int READ    = 1 << 0; // 0001
final int WRITE   = 1 << 1; // 0010
final int EXECUTE = 1 << 2; // 0100

int permissions = READ | EXECUTE;

// Kiểm tra một cờ
boolean canRead = (permissions & READ) != 0;

// Bật cờ WRITE
permissions |= WRITE;

// Tắt cờ EXECUTE
permissions &= ~EXECUTE;

// Đảo trạng thái cờ READ
permissions ^= READ;
```

Các mẫu thường gặp:

| Mục đích | Biểu thức |
|---|---|
| Bật các bit trong mask | `value |= mask` |
| Tắt các bit trong mask | `value &= ~mask` |
| Đảo các bit trong mask | `value ^= mask` |
| Kiểm tra có ít nhất một bit trong mask | `(value & mask) != 0` |
| Kiểm tra tất cả bit trong mask đều bật | `(value & mask) == mask` |

Nếu làm việc với bit thứ 31 của `int` hoặc các vị trí cao của `long`, cần chọn đúng kiểu cho mask. Ví dụ, `1 << bitIndex` là phép dịch trên `int`; dùng `1L << bitIndex` khi cần mask kiểu `long`.

## 7. Toán tử dịch bit

Java có ba toán tử dịch bit:

| Toán tử | Tên | Cách hoạt động |
|---|---|---|
| `<<` | Dịch trái | Dịch các bit sang trái, điền 0 ở phía phải |
| `>>` | Dịch phải có dấu | Dịch sang phải và giữ bit dấu ở phía trái |
| `>>>` | Dịch phải không dấu | Dịch sang phải và điền 0 ở phía trái |

Ví dụ:

```java
int value = 8; // ...00001000

System.out.println(value << 1);  // 16
System.out.println(value >> 1);  // 4
System.out.println(value >>> 1); // 4

int negative = -8;
System.out.println(negative >> 1);  // -4
System.out.println(negative >>> 1); // 2147483644
```

Với số âm, `>>` giữ bit dấu nên kết quả vẫn âm trong ví dụ trên. `>>>` điền 0 ở phía trái, vì vậy kết quả có thể trở thành số dương lớn.

Toán hạng bên trái được áp dụng unary numeric promotion; kiểu kết quả là `int` hoặc `long` theo kiểu sau khi mở rộng của toán hạng trái. Số bit dịch được lấy từ các bit thấp của toán hạng phải:

- Với kết quả kiểu `int`, chỉ 5 bit thấp được dùng (giá trị dịch từ 0 đến 31).
- Với kết quả kiểu `long`, chỉ 6 bit thấp được dùng (giá trị dịch từ 0 đến 63).

Ví dụ:

```java
System.out.println(1 << 32);  // 1: khoảng dịch 32 được xem như 0 với int
System.out.println(1L << 64); // 1: khoảng dịch 64 được xem như 0 với long
```

Dịch trái không phải phép nhân số học an toàn trong mọi trường hợp: bit có thể bị đẩy ra ngoài phạm vi biểu diễn. Hãy kiểm tra giới hạn dữ liệu và chọn `int` hay `long` phù hợp.

## 8. Thứ tự ưu tiên của toán tử

Khi một biểu thức có nhiều toán tử, Java dùng thứ tự ưu tiên để xác định cách nhóm các toán hạng. Bảng dưới đây sắp xếp từ ưu tiên cao xuống thấp cho các nhóm thường gặp.

| Mức | Nhóm | Toán tử |
|---:|---|---|
| 1 | Hậu tố | `expr++`, `expr--` |
| 2 | Một ngôi, tiền tố, ép kiểu | `++expr`, `--expr`, `+`, `-`, `!`, `~`, `(type)` |
| 3 | Nhân, chia, phần dư | `*`, `/`, `%` |
| 4 | Cộng, trừ | `+`, `-` |
| 5 | Dịch bit | `<<`, `>>`, `>>>` |
| 6 | Quan hệ và kiểu | `<`, `<=`, `>`, `>=`, `instanceof` |
| 7 | Bằng, khác | `==`, `!=` |
| 8 | AND bit | `&` |
| 9 | XOR bit | `^` |
| 10 | OR bit | `|` |
| 11 | AND logic | `&&` |
| 12 | OR logic | `||` |
| 13 | Điều kiện ba ngôi | `?:` |
| 14 | Gán | `=`, `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `^=`, `|=`, `<<=`, `>>=`, `>>>=` |

Ví dụ:

```java
int result = 10 + 6 * 2;
```

Phép nhân có ưu tiên cao hơn phép cộng, nên biểu thức được nhóm như sau:

```java
int result = 10 + (6 * 2); // 22
```

Nếu muốn cộng trước, cần dùng dấu ngoặc:

```java
int result = (10 + 6) * 2; // 32
```

Một ví dụ khác:

```java
boolean result = 8 > 3 && 5 < 2 || true;
```

Do `>` và `<` có ưu tiên cao hơn `&&`, còn `&&` cao hơn `||`, biểu thức được nhóm như sau:

```java
boolean result = ((8 > 3) && (5 < 2)) || true;
```

Kết quả là `true`.

## 9. Tính kết hợp và thứ tự đánh giá

Thứ tự ưu tiên xác định toán tử nào được nhóm trước. Tính kết hợp xác định cách nhóm các toán tử cùng mức ưu tiên. Hai khái niệm này khác với thứ tự đánh giá toán hạng khi chương trình chạy.

### 9.1. Tính kết hợp trái và phải

Phần lớn toán tử nhị phân cùng mức ưu tiên kết hợp từ trái sang phải:

```java
int result = 20 - 5 - 3;
// được nhóm thành (20 - 5) - 3
// kết quả: 12
```

Toán tử gán kết hợp từ phải sang trái:

```java
int a;
int b;
int c;

a = b = c = 10;
// tương đương a = (b = (c = 10))
```

Toán tử điều kiện `?:` cũng kết hợp từ phải sang trái. Khi biểu thức điều kiện lồng nhau, nên dùng dấu ngoặc hoặc tách thành các biến trung gian để dễ đọc.

### 9.2. Thứ tự đánh giá toán hạng

Trong biểu thức Java, toán hạng được đánh giá từ trái sang phải. Tuy nhiên, `&&`, `||` và `?:` có quy tắc đoản mạch hoặc chỉ đánh giá nhánh được chọn:

- `left && right`: bỏ qua `right` nếu `left` là `false`.
- `left || right`: bỏ qua `right` nếu `left` là `true`.
- `condition ? first : second`: chỉ đánh giá `first` hoặc `second`, tùy kết quả của `condition`.

Các toán tử boolean `&`, `|` và `^` đánh giá cả hai toán hạng. Vì vậy, đừng thay `&&` bằng `&` hoặc `||` bằng `|` khi vế phải có thể gây lỗi hoặc có tác dụng phụ.

## 10. Những lỗi thường gặp và cách tránh

| Lỗi | Nguyên nhân | Cách viết rõ ràng |
|---|---|---|
| Kết quả phép chia thiếu phần thập phân | Cả hai toán hạng là số nguyên | Chuyển một toán hạng sang `double` trước khi chia |
| Gán tổng của hai `byte` vào `byte` | Phép cộng được mở rộng thành `int` | Ép kiểu có chủ đích hoặc dùng kiểu `int` |
| So sánh hai chuỗi bằng `==` | `==` so sánh danh tính đối tượng | Dùng `equals` hoặc `Objects.equals` |
| Gọi phương thức trên `null` trong điều kiện | Vế phải vẫn được đánh giá | Dùng `&&` để kiểm tra null trước |
| Nhầm `&` với `&&` | `&` không đoản mạch | Dùng `&&` cho điều kiện thông thường |
| Nhầm `>>` với `>>>` | Hai phép dịch phải xử lý bit dấu khác nhau | Chọn theo cách muốn điền bit ở phía trái |
| Sai nhóm biểu thức | Dựa vào suy đoán thứ tự ưu tiên | Dùng dấu ngoặc cho các nhóm quan trọng |
| Tràn số nguyên | Kết quả vượt phạm vi kiểu | Chọn kiểu rộng hơn hoặc dùng `Math.*Exact` |
| Dùng `1 << n` cho mask kiểu `long` | Hằng `1` có kiểu `int` | Dùng `1L << n` |

Một số lưu ý thêm:

- Java không có toán tử lũy thừa `**`; dùng `Math.pow(base, exponent)` cho phép tính dấu phẩy động hoặc các API số học phù hợp với miền giá trị.
- Java không hỗ trợ nạp chồng toán tử cho class do người dùng định nghĩa. Ví dụ, `BigInteger` cung cấp các phương thức như `add`, `multiply`, `and` thay vì cho phép dùng `+`, `*`, `&` trực tiếp với đối tượng `BigInteger`.
- Khi biểu thức dài, hãy ưu tiên biến trung gian có tên rõ nghĩa. Cách này giúp kiểm tra kiểu, giá trị và tác dụng phụ dễ hơn.

## 11. Bài tập thực hành

### Bài 1: Tính tiền và phần dư

Một cửa hàng có 53 sản phẩm, mỗi hộp chứa 8 sản phẩm. Viết chương trình tính số hộp đầy và số sản phẩm còn lại.

```java
int products = 53;
int capacity = 8;

int fullBoxes = products / capacity;
int remaining = products % capacity;

System.out.println("Full boxes: " + fullBoxes);
System.out.println("Remaining: " + remaining);
```

Kết quả mong đợi:

```text
Full boxes: 6
Remaining: 5
```

### Bài 2: Kiểm tra điều kiện truy cập

Một tài khoản được truy cập khi đã xác thực và (có vai trò quản trị hoặc tài nguyên đang công khai). Viết biểu thức boolean mô tả điều kiện này.

```java
boolean authenticated = true;
boolean admin = false;
boolean resourcePublic = true;

boolean canAccess = authenticated && (admin || resourcePublic);
System.out.println(canAccess); // true
```

### Bài 3: Quản lý cờ quyền bằng bit mask

Dùng ba cờ `READ`, `WRITE`, `EXECUTE`. Bật hai cờ `READ` và `WRITE`, kiểm tra `EXECUTE`, rồi tắt `WRITE`. Hãy giải thích giá trị của biến sau mỗi phép toán.

### Bài 4: Phân tích thứ tự ưu tiên

Không chạy chương trình ngay, hãy tự nhóm và dự đoán kết quả:

```java
int value = 4 + 12 / 3 * 2 - 1;
boolean accepted = value > 8 && value < 12 || false;
```

Sau đó thêm dấu ngoặc tường minh vào hai biểu thức và kiểm tra kết quả bằng Java.

## 12. Tóm tắt

Toán tử số học thực hiện các phép tính và tuân theo quy tắc mở rộng kiểu số; cần đặc biệt chú ý phép chia số nguyên, phần dư, tràn số và độ chính xác của `float`/ `double`. Toán tử so sánh tạo giá trị boolean; `==` trên kiểu tham chiếu kiểm tra danh tính đối tượng, còn so sánh nội dung chuỗi nên dùng `equals`.

Toán tử logic `&&` và `||` có đoản mạch, phù hợp để kết hợp điều kiện và bảo vệ thao tác ở vế phải. Toán tử bit và dịch bit thao tác trên biểu diễn nhị phân của số nguyên, thường dùng trong bit mask, cờ và xử lý dữ liệu mức thấp.

Thứ tự ưu tiên quyết định cách nhóm toán tử; tính kết hợp quyết định cách nhóm các toán tử cùng mức. Java đánh giá toán hạng từ trái sang phải, ngoại trừ phần được bỏ qua theo quy tắc đoản mạch hoặc nhánh điều kiện. Dùng dấu ngoặc và biến trung gian khi biểu thức phức tạp để mã nguồn dễ đọc, dễ kiểm tra và ít lỗi.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — Chapter 15: Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html)
- [Java Language Specification, Java SE 27 — §4.2 Primitive Types and Values](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.2)
- [Java Language Specification, Java SE 27 — §5.6 Numeric Contexts](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-5.html#jls-5.6)
- [Java SE 27 API — Class Math](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Math.html)
