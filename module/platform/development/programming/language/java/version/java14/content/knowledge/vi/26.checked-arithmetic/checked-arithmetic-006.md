# Quan hệ giữa số học kiểm tra tràn trong StrictMath và các phép toán tương ứng trong Math

## 1. Mục tiêu và ngữ cảnh Java 14

Java có hai lớp tiện ích số học quen thuộc trong package `java.lang`: **`Math`** và **`StrictMath`**. Cả hai cung cấp những phương thức tính toán số nguyên có **kiểm tra tràn (*exact arithmetic*)**, chẳng hạn `addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact`, `negateExact` và `toIntExact`.

Với một phép toán số nguyên có thể biểu diễn được trong kiểu đích, các phương thức `...Exact` tương ứng của `Math` và `StrictMath` **trả cùng kết quả**. Nếu phép tính toán học nằm ngoài miền giá trị của kiểu đích, **cả hai ném `ArithmeticException`** thay vì lặng lẽ cho kết quả bị cuộn vòng như toán tử `+`, `-`, `*` hay toán tử đổi dấu `-x` thông thường.

Bài này trả lời câu hỏi trực tiếp **“Quan hệ với các phép toán tương ứng trong Math”** trong chủ đề **“Số học kiểm tra tràn”**:

- Những phương thức `StrictMath` nào có bản tương ứng trong `Math`?
- **Kết quả, kiểu dữ liệu, điều kiện ném exception** có khác nhau không?
- Vì sao Java 14 đáng chú ý: `StrictMath.incrementExact`, `decrementExact` và `negateExact` xuất hiện ở phiên bản nào, và có phải `Math` mới có chúng từ Java 14 không?
- Vì sao `Math`/`StrictMath` kiểm tra tràn khác toán tử số nguyên thông thường?
- Làm thế nào chọn đúng overload `int` hoặc `long`, tránh tràn **trước khi** widening?
- Phân biệt `multiplyExact` với `multiplyFull`, `multiplyHigh`, và phân biệt phép chia thông thường với những phép chia kiểm tra tràn mới hơn.
- Khi nào dùng `Math`, khi nào dùng `StrictMath`, và khi nào cần `BigInteger`/`BigDecimal` thay vì fixed-width integers?

### Tính hiện hành

Các API nêu trong bài vẫn được hỗ trợ trên JDK hiện đại. Chương trình chính được **biên dịch bằng `javac --release 17`**, chạy được trên **Java 17+**. Các phương thức `divideExact`/`floorDivExact`/`ceilDivExact` bổ sung từ **Java 18** được giải thích trong phần riêng và có ví dụ chạy với **JDK 21+**; không trộn các method đó vào chương trình yêu cầu tương thích Java 17.

**Lưu ý lịch sử có ích, không dùng legacy:** Tài liệu Oracle xác nhận `StrictMath.incrementExact`, `StrictMath.decrementExact` và `StrictMath.negateExact` được đưa vào **Java 14**, trong khi **`Math` đã có những phương thức tương ứng từ Java 8**. Đây là mối liên hệ quan trọng của bài trong module Java 14. Các phương thức hiện còn áp dụng và không yêu cầu cờ preview.

## 2. Nền tảng: số nguyên Java có miền giá trị hữu hạn

Kiểu nguyên thủy `int` là số nguyên có dấu **32 bit**; `long` là số nguyên có dấu **64 bit**:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: |
| `int` | `-2_147_483_648` (`Integer.MIN_VALUE`) | `2_147_483_647` (`Integer.MAX_VALUE`) |
| `long` | `-9_223_372_036_854_775_808L` (`Long.MIN_VALUE`) | `9_223_372_036_854_775_807L` (`Long.MAX_VALUE`) |

Khi tính `int`/`long` bằng toán tử `+`, `-`, `*` hoặc đổi dấu `-x`, **tràn số nguyên không tự ném exception**; kết quả tuân theo biểu diễn hai bù với độ rộng tương ứng.

~~~java
int max = Integer.MAX_VALUE;
System.out.println(max + 1);           // -2147483648
System.out.println(50_000 * 50_000);    // -1794967296
System.out.println(-Integer.MIN_VALUE); // -2147483648
~~~

Ba dòng này là **đoạn minh họa cần đặt trong method**. Chúng không “tự mở rộng” sang kiểu `long` dù kết quả toán học của phép tính vượt khỏi `int`. Khi dùng:

~~~java
int max = Integer.MAX_VALUE;
// int checked = Math.addExact(max, 1); // ArithmeticException.
// int checked2 = StrictMath.addExact(max, 1); // ArithmeticException.
~~~

thay vì nhận một giá trị âm sai ngữ nghĩa, ứng dụng có thể **phát hiện tràn tại đúng phép tính**.

### 2.1. Vì sao cần “Exact”?

“Exact” trong các phương thức số nguyên kiểm tra tràn có nghĩa: **nếu kết quả toán học biểu diễn chính xác được trong kiểu trả về thì trả kết quả; nếu không, báo lỗi**. Đây **không** phải lời hứa tính toán với số có độ lớn vô hạn hay về độ chính xác của số thực dấu phẩy động.

Ví dụ:

- `Math.addExact(40, 2)` → `42`.
- `Math.addExact(Integer.MAX_VALUE, 1)` → `ArithmeticException`.
- `Math.multiplyExact(50_000, 50_000)` (hai `int`) → `ArithmeticException` vì tích `2_500_000_000` vượt `int`.
- `Math.multiplyExact(50_000L, 50_000)` → `2_500_000_000L` vì phép nhân được chọn trên kiểu trả về `long`.

## 3. Quan hệ nền tảng giữa Math và StrictMath

### 3.1. Cùng hợp đồng số học nguyên, khác tên lớp gọi

Trong nhóm **exact integer operations**, `Math.xxxExact(...)` và `StrictMath.xxxExact(...)` có **cùng định nghĩa phép toán** và **cùng ranh giới tràn** cho overload tương ứng.

~~~java
int a = Math.addExact(12, 30);        // 42
int b = StrictMath.addExact(12, 30);  // 42

// Cả hai ném ArithmeticException nếu vượt int:
// Math.addExact(Integer.MAX_VALUE, 1);
// StrictMath.addExact(Integer.MAX_VALUE, 1);
~~~

Đây là **snippet**, không phải một chương trình độc lập. “Cùng hành vi” ở đây là **kiểu giá trị trả về hoặc việc báo tràn bằng loại exception**, không có nghĩa:
- Chuỗi `getMessage()` của exception phải giống hệt trên mọi JVM.
- Hai lời gọi nhất thiết sử dụng **một mã máy/implementation nội bộ**.
- Hiệu suất chắc chắn bằng nhau ở mọi phiên bản, CPU và môi trường JIT.
- Các phương thức số thực của `Math` và `StrictMath` đều có đặc tả bit-level giống nhau trong mọi tình huống.

### 3.2. Sự khác biệt lịch sử của StrictMath không đổi quy tắc tràn số nguyên

`StrictMath` được biết đến nhờ các yêu cầu nhất quán đặc biệt cho **một số phép toán floating-point** (ví dụ hàm lượng giác, logarit). Sự khác nhau đó **không cho phép hiểu** rằng `Math.addExact` “ít chính xác” hơn `StrictMath.addExact` đối với số nguyên.

Đối với `int` và `long`:
- Miền giá trị là xác định.
- Kết quả của exact operation là duy nhất nếu nằm trong miền.
- Cùng phép toán và cùng kiểu đích ⇒ cùng kết quả hoặc cùng `ArithmeticException`.

**Không cần chuyển toàn bộ `Math.*Exact` sang `StrictMath.*Exact` chỉ để “bảo đảm chống tràn tốt hơn”.** Cả hai cung cấp kiểm tra tràn đúng hợp đồng.

### 3.3. Tính di động của các API

Hai lớp thuộc `java.lang`, module `java.base`; không cần import khi dùng tên đầy đủ `Math` hoặc `StrictMath`. Chúng là **static utility methods**; bạn gọi trực tiếp từ class, không tạo instance.

~~~java
long total = Math.addExact(10L, 20L);
long totalStrict = StrictMath.addExact(10L, 20L);
~~~

Các phương thức này dùng được trong mã ứng dụng thông thường; trên các bản Java hiện đại không cần preview hoặc thư viện bên thứ ba.

## 4. Bảng đối chiếu các phương thức Exact trong Math và StrictMath

Bảng tập trung vào **Java 17+**, những method đang được sử dụng. Khi có khác biệt lịch sử của `StrictMath`, bảng ghi rõ.

| Phép toán | `Math` | `StrictMath` | Hành vi khi tràn |
| --- | --- | --- | --- |
| Cộng | `Math.addExact(x, y)` | `StrictMath.addExact(x, y)` | Ném `ArithmeticException` |
| Trừ | `Math.subtractExact(x, y)` | `StrictMath.subtractExact(x, y)` | Ném `ArithmeticException` |
| Nhân | `Math.multiplyExact(x, y)` | `StrictMath.multiplyExact(x, y)` | Ném `ArithmeticException` |
| Tăng 1 | `Math.incrementExact(x)` | `StrictMath.incrementExact(x)` | Ném nếu `x` đã ở MAX |
| Giảm 1 | `Math.decrementExact(x)` | `StrictMath.decrementExact(x)` | Ném nếu `x` đã ở MIN |
| Đổi dấu | `Math.negateExact(x)` | `StrictMath.negateExact(x)` | Ném nếu `x` bằng MIN |
| Chuyển `long` sang `int` | `Math.toIntExact(value)` | `StrictMath.toIntExact(value)` | Ném nếu vượt miền `int` |
| Giá trị tuyệt đối nguyên | `Math.absExact(x)` | `StrictMath.absExact(x)` | Ném nếu `x` bằng MIN |

Ngoại trừ `toIntExact` có chữ ký `(long) → int`, các phép toán trong bảng có những overload thích hợp cho `int` và `long`. `multiplyExact` còn có overload `(long, int) → long` (từ Java 9).

### 4.1. Những mốc phiên bản quan trọng

| Nhóm API | `Math` | `StrictMath` | Ý nghĩa đối với bài Java 14 |
| --- | --- | --- | --- |
| `addExact`, `subtractExact`, `multiplyExact(int,int)/(long,long)` | Java 8 | Java 8 | Đã tồn tại trước Java 14 và còn dùng tốt |
| `multiplyExact(long,int)` | Java 9 | Java 9 | Bổ sung lựa chọn kiểu kết quả `long` |
| `incrementExact`, `decrementExact`, `negateExact` | Java 8 | **Java 14** | Java 14 bổ sung các method tương ứng ở `StrictMath` |
| `toIntExact` | Java 8 | Java 8 | Kiểm tra chuyển hẹp kiểu |
| `absExact(int/long)` | **Java 15** | **Java 15** | Phương thức hiện hành nhưng **không có trong Java 14** |
| `divideExact`, `floorDivExact`, `ceilDivExact` | **Java 18** | **Java 18** | Phương thức hiện hành, phải build bằng JDK đủ mới |

**Đây là bảng phiên bản API**, không phải lời khuyên dùng lại phương pháp cũ. Nếu dự án đặt `--release 17`, `absExact` dùng được nhưng nhóm exact division Java 18 **không** biên dịch được. Với ứng dụng yêu cầu Java 14 nguyên bản, `StrictMath.incrementExact`/`decrementExact`/`negateExact` đã có, nhưng `absExact` chưa có.

## 5. Phép cộng: `addExact` tương đương giữa hai lớp

Phép cộng:

~~~java
int x = 20, y = 22;
int fromMath = Math.addExact(x, y);             // 42
int fromStrict = StrictMath.addExact(x, y);     // 42
~~~

**Quan hệ:** `Math.addExact(int,int)` và `StrictMath.addExact(int,int)` cùng trả tổng toán học nếu vừa `int`; nếu tràn thì cùng ném `ArithmeticException`. Đối với `long`, dùng overload `(long,long)`.

Trường hợp biên:

~~~java
int x = Integer.MAX_VALUE;
int unchecked = x + 1; // -2147483648

// Hai câu lệnh dưới đều gây ArithmeticException:
// Math.addExact(x, 1);
// StrictMath.addExact(x, 1);
~~~

Nếu mục tiêu nghiệp vụ là một tổng **không được phép bị cuộn vòng**, chọn một trong hai phương thức `addExact`. Nếu mục tiêu là arithmetic modulo có chủ đích (ví dụ một số thuật toán băm), toán tử thường có thể đúng hơn; phải nêu rõ mục đích thay vì coi mọi wraparound là bug.

## 6. Phép trừ: `subtractExact` và biên dưới của kiểu nguyên

~~~java
int remainA = Math.subtractExact(40, 2);       // 38
int remainB = StrictMath.subtractExact(40, 2); // 38
~~~

Trường hợp nguy hiểm:

~~~java
int x = Integer.MIN_VALUE;
int unchecked = x - 1; // 2147483647

// Ném ArithmeticException:
// Math.subtractExact(x, 1);
// StrictMath.subtractExact(x, 1);
~~~

**Quan hệ:** Hai bản `subtractExact` phát hiện tràn tương đương. `-` trong source thông thường không có cơ chế kiểm tra tràn, trong khi `subtractExact` có.

Một nhầm lẫn liên quan: `Math.abs(x)` (không có chữ Exact) **không tự xử lý tràn** khi `x` là `Integer.MIN_VALUE` hoặc `Long.MIN_VALUE`. Có thể dùng `absExact` từ Java 15 trở đi nếu cần phát hiện ranh giới đó.

## 7. Phép nhân: `multiplyExact` và bẫy chọn overload

### 7.1. Nhân hai `int`

~~~java
int a = 9, b = 7;
int p1 = Math.multiplyExact(a, b);             // 63
int p2 = StrictMath.multiplyExact(a, b);       // 63
~~~

Khi tích vượt `int`:

~~~java
int a = 50_000, b = 50_000;
int wrapped = a * b; // -1794967296

// Ném ArithmeticException:
// Math.multiplyExact(a, b);
// StrictMath.multiplyExact(a, b);
~~~

### 7.2. Lỗi phổ biến: gán vào `long` không cứu được tràn đã xảy ra

~~~java
int a = 50_000;
int b = 50_000;

long wrong = a * b;           // -1794967296L: tràn int trước khi gán.
long correct = (long) a * b;  // 2500000000L: nhân ở long.
long exact = Math.multiplyExact((long) a, b); // 2500000000L.
~~~

**Nguyên tắc:** Kiểu của toán hạng quyết định phép toán ở giai đoạn tính. Sau khi phép nhân `int * int` đã tràn, gán vào `long` chỉ mở rộng **giá trị sai**.

Với `Math.multiplyExact(long,int)` hoặc `StrictMath.multiplyExact(long,int)`, kiểu trả về là `long`. Hai phương thức đó ném exception **nếu tích vượt `long`**, không phải vì nó vượt `int`.

### 7.3. Nên cast chỗ nào?

~~~java
int quantity = 50_000;
int unitPrice = 50_000;

long cents = Math.multiplyExact((long) quantity, unitPrice);
~~~

Điều này đảm bảo **độ rộng 64-bit trước phép nhân**. Nếu giá trị `long` vẫn có thể vượt biên do đầu vào cực lớn, `multiplyExact(long,int)` báo tràn. Đối với bài toán tài chính có phân số, tỷ giá hoặc quy tắc làm tròn, `BigDecimal` với scale/rounding policy thường phù hợp hơn `double`; kiểm tra tràn số nguyên chỉ là **một phần của chính sách dữ liệu**.

## 8. Tăng, giảm và đổi dấu: ba phép Java 14 bổ sung vào StrictMath

Đây là phần đặc biệt quan trọng khi học module Java 14.

### 8.1. `incrementExact`

~~~java
int nextMath = Math.incrementExact(41);           // 42
int nextStrict = StrictMath.incrementExact(41);   // 42
~~~

Hai phương thức đều **ném `ArithmeticException` khi đầu vào bằng `Integer.MAX_VALUE`** (hoặc `Long.MAX_VALUE` cho overload `long`).

Đối chiếu toán tử thường:

~~~java
int x = Integer.MAX_VALUE;
int wrapped = ++x; // -2147483648, không ném ArithmeticException.
~~~

Nếu biến là một sequence number **không được lặp lại sau MAX**, `incrementExact` giúp phát hiện cần đổi kiểu/thiết kế thay vì âm thầm đưa ID về số âm.

### 8.2. `decrementExact`

~~~java
int nextMath = Math.decrementExact(42);           // 41
int nextStrict = StrictMath.decrementExact(42);   // 41
~~~

Ném khi đầu vào `Integer.MIN_VALUE` hoặc `Long.MIN_VALUE` tương ứng. Phép `--x` thông thường lại wraparound.

### 8.3. `negateExact`

~~~java
int negatedMath = Math.negateExact(-42);          // 42
int negatedStrict = StrictMath.negateExact(-42);  // 42
~~~

Tại sao đổi dấu `MIN_VALUE` gây tràn?

`int` có miền `[-2^31, 2^31 - 1]`. Giá trị dương `2^31` **không biểu diễn được bằng `int`**. Vì thế:

~~~java
int min = Integer.MIN_VALUE;
int wrapped = -min; // -2147483648, vẫn âm.

// Hai phương thức đều ném ArithmeticException:
// Math.negateExact(min);
// StrictMath.negateExact(min);
~~~

**Quan hệ Java 14:** `Math.incrementExact`/`decrementExact`/`negateExact` có từ Java 8; các **bản tương ứng trong `StrictMath` được thêm từ Java 14**. Không nên nói “Java 14 phát minh số học kiểm tra tràn cho Math” — điều đó sai về lịch sử API.

## 9. Chuyển kiểu kiểm tra tràn: `toIntExact` và ép kiểu thường

### 9.1. Cast `(int)` có thể làm mất bit

~~~java
long value = (long) Integer.MAX_VALUE + 1L;
int narrowed = (int) value; // -2147483648.
~~~

Phép cast từ `long` xuống `int` giữ các bit thấp theo quy tắc chuyển kiểu Java, không kiểm tra phạm vi. Nếu chuyển một số lượng lớn trong domain mà `int` không chứa nổi, bạn có thể nhận giá trị sai nhưng hợp lệ về cú pháp.

### 9.2. `toIntExact` báo lỗi

~~~java
long safeValue = 42L;
int a = Math.toIntExact(safeValue);        // 42
int b = StrictMath.toIntExact(safeValue);  // 42
~~~

Với `long value = (long) Integer.MAX_VALUE + 1L`, cả hai đều ném `ArithmeticException`.

**Quan hệ:** Hai phương thức cùng kiểu `(long) → int`, cùng điều kiện thành công/thất bại. Chúng **không** kiểm tra phép toán `long` diễn ra trước đó. Nếu giá trị `value` đã bị tràn ở một phép toán `long` trước khi chuyển, `toIntExact` không thể khôi phục giá trị toán học ban đầu.

### 9.3. Ranh giới của phép tính còn quan trọng hơn ranh giới chuyển kiểu

~~~java
long x = Long.MAX_VALUE;
long bad = x + 1L;      // Long.MIN_VALUE, đã tràn trước.
int narrowed = (int) bad; // 0, không báo tràn của phép cộng.
~~~

Nếu muốn kiểm tra **phép cộng** ở miền `long`, hãy dùng:

~~~java
long x = Long.MAX_VALUE;
// long safe = Math.addExact(x, 1L); // ArithmeticException tại phép cộng.
~~~

Sau đó, nếu cần chuyển kết quả `long` sang `int`, mới dùng `toIntExact`. **Không có một lời gọi `toIntExact` cuối cùng thay thế được mọi kiểm tra tràn ở các bước trước**.

## 10. Giá trị tuyệt đối: `abs` vs `absExact` (Java 15+)

Trên các JDK hiện đại có hai họ method:

~~~java
Math.abs(intValue)
Math.absExact(intValue)

StrictMath.abs(intValue)
StrictMath.absExact(intValue)
~~~

Với input bình thường, `abs` và `absExact` đều cho cùng kết quả. Nhưng tại `Integer.MIN_VALUE` hoặc `Long.MIN_VALUE`:
- `Math.abs(MIN_VALUE)` và `StrictMath.abs(MIN_VALUE)` trả lại chính **giá trị âm MIN_VALUE**, do không có số dương tương ứng trong kiểu.
- `Math.absExact(MIN_VALUE)` và `StrictMath.absExact(MIN_VALUE)` ném **`ArithmeticException`**.

Ví dụ:

~~~java
int min = Integer.MIN_VALUE;
System.out.println(Math.abs(min)); // -2147483648.

// Ném ArithmeticException trên Java 15+:
// Math.absExact(min);
// StrictMath.absExact(min);
~~~

**Mốc phiên bản:** `absExact` được bổ sung từ **Java 15**, nên **không** dùng nó trong chương trình yêu cầu biên dịch đúng Java 14. Bài học khuyến nghị API này vì nó **vẫn đang được hỗ trợ**, đồng thời ghi rõ ranh giới lịch sử để tránh lỗi compilation.

## 11. Nhân có mở rộng kết quả: `multiplyFull` và `multiplyHigh` không giống `multiplyExact`

Không phải mọi method có chữ “multiply” trong `Math`/`StrictMath` đều **kiểm tra tràn rồi ném exception**.

### 11.1. `multiplyFull(int,int) → long`

~~~java
long fullA = Math.multiplyFull(50_000, 50_000);       // 2500000000L
long fullB = StrictMath.multiplyFull(50_000, 50_000); // 2500000000L
~~~

Tích của hai `int` có dấu **luôn có thể biểu diễn hoàn chỉnh trong `long`**, vì miền tích 32-bit×32-bit nằm trong 64-bit. Vì vậy `multiplyFull` trả **tích toán học đầy đủ dưới dạng `long`**; nó không cần ném exception kiểm tra tràn `int`.

So sánh ba trường hợp:

| Biểu thức | Kiểu kết quả | Ví dụ `50_000 × 50_000` |
| --- | --- | --- |
| `a * b` với hai `int` | `int` | `-1794967296` do tràn |
| `Math.multiplyExact(a, b)` với hai `int` | `int` | Ném `ArithmeticException` |
| `Math.multiplyFull(a, b)` | `long` | `2500000000`, không mất kết quả |
| `Math.multiplyExact((long) a, b)` | `long` | `2500000000`, báo lỗi nếu về sau có tràn long |

Cả `Math.multiplyFull` lẫn `StrictMath.multiplyFull` có mặt từ Java 9 và còn được hỗ trợ. Đây là giải pháp rõ nghĩa khi muốn nhân hai `int` và **trả kết quả rộng hơn**, thay vì yêu cầu kết quả vẫn phải vừa `int`.

### 11.2. `multiplyHigh(long,long) → long`

`Math.multiplyHigh(x, y)` và `StrictMath.multiplyHigh(x, y)` trả về **64 bit cao** của tích có dấu 128-bit từ hai `long`. Chúng **không trả cả tích 128-bit**, cũng **không báo tràn như `multiplyExact(long,long)`**.

Ví dụ kiểm chứng:

~~~java
long highA = Math.multiplyHigh(Long.MIN_VALUE, -1L);       // 0.
long highB = StrictMath.multiplyHigh(Long.MIN_VALUE, -1L); // 0.
~~~

Tại sao `0`? Tích toán học `(-2^63) × (-1) = 2^63`, nằm trong 128-bit có phần 64-bit cao bằng 0, còn phần thấp chứa bit dấu. Nếu gọi `multiplyExact(Long.MIN_VALUE, -1L)`, cả Math và StrictMath lại ném `ArithmeticException` vì kết quả `2^63` vượt `long` có dấu.

**Kết luận:** `multiplyFull` và `multiplyHigh` là các công cụ **mở rộng/khai thác bit của tích**, không thay thế nhau hoặc tự động mang cùng chính sách báo tràn với `multiplyExact`.

## 12. Phép chia: toán tử `/`, `floorDiv` và nhóm kiểm tra tràn Java 18+

### 12.1. Phép chia nguyên thông thường

Toán tử `/` trên hai số nguyên chia theo hướng **cắt phần thập phân về 0** (truncation):

~~~java
System.out.println(-7 / 3); // -2
~~~

Trường hợp đặc biệt:

~~~java
int min = Integer.MIN_VALUE;
System.out.println(min / -1); // -2147483648, overflow nhưng không ném.
~~~

Chia cho `0` bằng toán tử `/` trên số nguyên vẫn **ném `ArithmeticException`**; việc không tự bắt tràn **không** có nghĩa toán tử này luôn bỏ qua mọi lỗi.

### 12.2. `floorDiv` không phải `divideExact`

~~~java
System.out.println(Math.floorDiv(-7, 3));       // -3.
System.out.println(StrictMath.floorDiv(-7, 3)); // -3.
~~~

`floorDiv` làm tròn thương đại số theo hướng **âm vô cùng**, khác kết quả `-2` của toán tử `-7 / 3`. Cả `Math.floorDiv` và `StrictMath.floorDiv` có cùng semantics và có overload phù hợp `int`/`long`.

**Cạm bẫy:** `floorDiv(Integer.MIN_VALUE, -1)` trên phiên bản hiện hành không tự kiểm tra tràn theo cách của `divideExact`; trường hợp đặc biệt trả lại `Integer.MIN_VALUE`. Đừng dùng `floorDiv` như một “phép chia đã kiểm tra mọi trường hợp tràn”.

### 12.3. Java 18 bổ sung các phiên bản `...Exact` cho phép chia

Trên **Java 18 trở lên**, cả `Math` và `StrictMath` có:

| Mục tiêu | `Math` | `StrictMath` |
| --- | --- | --- |
| Chia nguyên, truncation, báo tràn | `Math.divideExact(x, y)` | `StrictMath.divideExact(x, y)` |
| Chia hướng âm vô cùng, báo tràn | `Math.floorDivExact(x, y)` | `StrictMath.floorDivExact(x, y)` |
| Chia hướng dương vô cùng, báo tràn | `Math.ceilDivExact(x, y)` | `StrictMath.ceilDivExact(x, y)` |

Cả ba nhóm **ném `ArithmeticException`** nếu mẫu số 0 hoặc gặp overflow `MIN_VALUE / -1`. Giá trị trả về với đầu vào bình thường theo quy tắc rounding của nhóm method:

~~~java
// Chỉ có trên Java 18+:
int trunc = Math.divideExact(-7, 3);   // -2
int floor = Math.floorDivExact(-7, 3); // -3
int ceil = Math.ceilDivExact(-7, 3);   // -2
~~~

`floorDiv` và `floorMod`, `ceilDiv` và `ceilMod` còn có quy tắc ghép thương/số dư. Chúng hữu ích khi chia số âm hoặc xử lý chỉ số/bucket. **Không tự đồng nhất** “floor” hay “ceil” với “exact”; suffix `Exact` trong nhóm phương thức chia này báo rằng **tràn `MIN/-1` bị chặn**, trong khi rounding mode do tên method xác định.

**Ranh giới biên dịch:** Nếu dùng `javac --release 17`, các lời gọi `divideExact`/`floorDivExact`/`ceilDivExact` **không được nhận diện**, dù bạn chạy trình biên dịch JDK 24. Hãy dùng `--release 21` (hoặc một release hỗ trợ từ 18) cho ví dụ riêng ở phần 15.

## 13. Ví dụ Java 17+ hoàn chỉnh: Math và StrictMath có cùng hành vi

Ví dụ kiểm chứng:
- Các method `...Exact` khi phép tính **hợp lệ**.
- Các method `...Exact` khi phép tính **tràn**.
- Sự khác biệt với toán tử thường, widening và `multiplyFull`.
- Ranh giới của `floorDiv` và `abs`.
- Quan hệ `multiplyHigh` giữa `Math` và `StrictMath`.

Để stdout nhất quán, chương trình chuyển **`ArithmeticException` thành chuỗi tên exception** chỉ trong phần **demo/test**, không khuyến nghị bắt và bỏ qua exception trong logic ứng dụng.

**Lưu tệp `MathStrictMathExactDemo.java`:**

~~~java
import java.util.function.IntSupplier;
import java.util.function.LongSupplier;

public final class MathStrictMathExactDemo {
    static String intResult(IntSupplier op) {
        try {
            return Integer.toString(op.getAsInt());
        } catch (ArithmeticException ex) {
            return "ArithmeticException";
        }
    }

    static String longResult(LongSupplier op) {
        try {
            return Long.toString(op.getAsLong());
        } catch (ArithmeticException ex) {
            return "ArithmeticException";
        }
    }

    static void pair(String label, IntSupplier mathOp, IntSupplier strictOp) {
        String m = intResult(mathOp);
        String s = intResult(strictOp);
        System.out.println(label + ": Math=" + m
                + ", StrictMath=" + s + ", same=" + m.equals(s));
    }

    public static void main(String[] args) {
        pair("add", () -> Math.addExact(40, 2),
                () -> StrictMath.addExact(40, 2));
        pair("add overflow", () -> Math.addExact(Integer.MAX_VALUE, 1),
                () -> StrictMath.addExact(Integer.MAX_VALUE, 1));
        pair("subtract", () -> Math.subtractExact(40, 2),
                () -> StrictMath.subtractExact(40, 2));
        pair("subtract overflow", () -> Math.subtractExact(Integer.MIN_VALUE, 1),
                () -> StrictMath.subtractExact(Integer.MIN_VALUE, 1));
        pair("multiply", () -> Math.multiplyExact(9, 7),
                () -> StrictMath.multiplyExact(9, 7));
        pair("multiply overflow", () -> Math.multiplyExact(50_000, 50_000),
                () -> StrictMath.multiplyExact(50_000, 50_000));
        pair("increment overflow", () -> Math.incrementExact(Integer.MAX_VALUE),
                () -> StrictMath.incrementExact(Integer.MAX_VALUE));
        pair("decrement overflow", () -> Math.decrementExact(Integer.MIN_VALUE),
                () -> StrictMath.decrementExact(Integer.MIN_VALUE));
        pair("negate overflow", () -> Math.negateExact(Integer.MIN_VALUE),
                () -> StrictMath.negateExact(Integer.MIN_VALUE));
        pair("toIntExact overflow",
                () -> Math.toIntExact((long) Integer.MAX_VALUE + 1L),
                () -> StrictMath.toIntExact((long) Integer.MAX_VALUE + 1L));
        pair("absExact overflow", () -> Math.absExact(Integer.MIN_VALUE),
                () -> StrictMath.absExact(Integer.MIN_VALUE));

        int max = Integer.MAX_VALUE;
        System.out.println("unchecked add=" + (max + 1));
        System.out.println("unchecked multiply=" + (50_000 * 50_000));
        System.out.println("widened multiply=" + (50_000L * 50_000));
        System.out.println("Math.multiplyFull=" + Math.multiplyFull(50_000, 50_000));
        System.out.println("StrictMath.multiplyFull="
                + StrictMath.multiplyFull(50_000, 50_000));
        System.out.println("Math.multiplyExact(long,int)="
                + longResult(() -> Math.multiplyExact(50_000L, 50_000)));
        System.out.println("unchecked division=" + (Integer.MIN_VALUE / -1));
        System.out.println("truncating -7/3=" + (-7 / 3));
        System.out.println("Math.floorDiv(-7,3)=" + Math.floorDiv(-7, 3));
        System.out.println("StrictMath.floorDiv(-7,3)="
                + StrictMath.floorDiv(-7, 3));
        System.out.println("Math.abs(MIN)=" + Math.abs(Integer.MIN_VALUE));
        System.out.println("Math.multiplyHigh(MIN,-1)="
                + Math.multiplyHigh(Long.MIN_VALUE, -1L));
        System.out.println("StrictMath.multiplyHigh(MIN,-1)="
                + StrictMath.multiplyHigh(Long.MIN_VALUE, -1L));
    }
}
~~~

### 13.1. Biên dịch/chạy

~~~bash
javac -encoding UTF-8 --release 17 MathStrictMathExactDemo.java
java MathStrictMathExactDemo
~~~

### 13.2. Stdout chính xác đã kiểm chứng

Chương trình đã được **biên dịch với `--release 17` và chạy trên OpenJDK hiện đại**, cho output sau:

~~~text
add: Math=42, StrictMath=42, same=true
add overflow: Math=ArithmeticException, StrictMath=ArithmeticException, same=true
subtract: Math=38, StrictMath=38, same=true
subtract overflow: Math=ArithmeticException, StrictMath=ArithmeticException, same=true
multiply: Math=63, StrictMath=63, same=true
multiply overflow: Math=ArithmeticException, StrictMath=ArithmeticException, same=true
increment overflow: Math=ArithmeticException, StrictMath=ArithmeticException, same=true
decrement overflow: Math=ArithmeticException, StrictMath=ArithmeticException, same=true
negate overflow: Math=ArithmeticException, StrictMath=ArithmeticException, same=true
toIntExact overflow: Math=ArithmeticException, StrictMath=ArithmeticException, same=true
absExact overflow: Math=ArithmeticException, StrictMath=ArithmeticException, same=true
unchecked add=-2147483648
unchecked multiply=-1794967296
widened multiply=2500000000
Math.multiplyFull=2500000000
StrictMath.multiplyFull=2500000000
Math.multiplyExact(long,int)=2500000000
unchecked division=-2147483648
truncating -7/3=-2
Math.floorDiv(-7,3)=-3
StrictMath.floorDiv(-7,3)=-3
Math.abs(MIN)=-2147483648
Math.multiplyHigh(MIN,-1)=0
StrictMath.multiplyHigh(MIN,-1)=0
~~~

### 13.3. Ý nghĩa các nhóm output

**Các dòng `same=true`:** Trong mọi trường hợp được demo, cả Math và StrictMath trả **cùng số** hoặc cùng báo **ArithmeticException**. Bài học không so chuỗi message của exception, vì đó không phải hợp đồng nên phụ thuộc implementation.

**`unchecked add/multiply`:** Toán tử `+` và `*` trên `int` có thể tràn thành số âm dù kết quả toán học là dương.

**`widened multiply`:** Cho một toán hạng thành `long` **trước khi** nhân giúp kết quả nằm trong miền rộng hơn.

**`multiplyFull`:** Khi hai toán hạng đều là `int`, `multiplyFull` trả tích đầy đủ ở `long`; không yêu cầu kết quả phải vừa `int` như `multiplyExact(int,int)`.

**`unchecked division`:** `Integer.MIN_VALUE / -1` tràn nhưng không ném; một ngoại lệ đặc biệt của phép chia nguyên cần hiểu trước khi chọn Java 18+ `divideExact`.

**`floorDiv`:** Phép chia `-7/3` cho `-3` thay vì `-2`; khác biệt do **quy tắc làm tròn**, không phải do việc kiểm tra tràn.

**`Math.abs(MIN)`:** Giá trị tuyệt đối thông thường của `Integer.MIN_VALUE` vẫn âm; `absExact` ngăn tình huống đó bằng `ArithmeticException`.

**`multiplyHigh`:** Trả high bits của tích 128-bit, không phải một bản thay thế `multiplyExact`.

## 14. Chọn đúng phép toán dựa trên hợp đồng nghiệp vụ

### 14.1. Khi nào dùng `Math.*Exact` hoặc `StrictMath.*Exact`?

**Nên dùng** nếu một phép số nguyên vượt giới hạn kiểu đích phải được **phát hiện**:
- Tính số tiền ở đơn vị nguyên nhỏ nhất (cents, đồng) theo quy tắc không cho tràn.
- Tăng counter/sequence number không cho wraparound.
- Tính tổng byte count, số lượng, index/offset có ràng buộc.
- Chuyển `long` xuống `int` trước khi truyền cho API dùng kích thước `int`.

**Lưu ý:** Exception báo tràn vẫn cần được xử lý có ý nghĩa — ví dụ reject input, trả lỗi validation, đổi kiểu lưu trữ — chứ không nên bắt rồi tự thay bằng số 0.

### 14.2. Khi nào toán tử thường lại phù hợp?

Một số thuật toán cố ý dùng arithmetic modulo 2^32 hoặc 2^64, chẳng hạn một số hàm băm hoặc thuật toán bit-level. Khi đó `+`/`*` với wraparound có thể là một phần của thiết kế.

**Tuy nhiên:** dùng wraparound phải là **quyết định được tài liệu hóa**, không phải hệ quả không biết của tràn.

### 14.3. Khi nào dùng `BigInteger`?

Nếu số nguyên có thể vượt cả `long` mà ứng dụng vẫn phải tiếp tục tính một kết quả toán học chính xác:

~~~java
import java.math.BigInteger;

BigInteger a = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger b = a.add(BigInteger.ONE); // 9223372036854775808
~~~

Đây là **snippet**, cần đặt trong class/method thích hợp. `BigInteger` có độ chính xác nguyên lớn tùy bộ nhớ/tài nguyên, thay vì giới hạn ở 64 bit và ném `ArithmeticException` tại biên `long`. Nhưng `BigInteger` **không thay thế** validation về kích thước đầu vào, tài nguyên, số vòng lặp hoặc giới hạn nghiệp vụ.

### 14.4. Khi nào dùng `BigDecimal`?

Dữ liệu tài chính có phần thập phân có thể cần **`BigDecimal`**, quản lý scale, precision và rounding. `Math.addExact` xử lý **kiểu nguyên fixed-width**, không giải quyết vấn đề sai số floating-point `double` hoặc quy định làm tròn tiền tệ.

Ví dụ: lưu số tiền nguyên nhỏ nhất dưới dạng `long` và dùng `Math.addExact` có thể đúng cho nhiều hệ thống; nếu cần tỷ giá/phần lẻ, dùng decimal policy phù hợp.

## 15. Ví dụ riêng cho nhóm phép chia mới hơn (Java 18+, chạy với JDK 21+)

**Không ghép đoạn này vào chương trình Java 17 của phần 13** nếu build yêu cầu `--release 17`.

Lưu tệp **`MathDivExact21Demo.java`**:

~~~java
public final class MathDivExact21Demo {
    public static void main(String[] args) {
        System.out.println("divideExact=" + Math.divideExact(10, 2));
        System.out.println("StrictMath.divideExact="
                + StrictMath.divideExact(10, 2));
        System.out.println("floorDivExact(-7,3)="
                + Math.floorDivExact(-7, 3));
        System.out.println("ceilDivExact(-7,3)="
                + Math.ceilDivExact(-7, 3));
        System.out.println("StrictMath.floorDivExact(-7,3)="
                + StrictMath.floorDivExact(-7, 3));
        System.out.println("StrictMath.ceilDivExact(-7,3)="
                + StrictMath.ceilDivExact(-7, 3));

        try {
            Math.divideExact(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException ex) {
            System.out.println("Math.divideExact(MIN,-1)=ArithmeticException");
        }
        try {
            StrictMath.divideExact(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException ex) {
            System.out.println(
                    "StrictMath.divideExact(MIN,-1)=ArithmeticException");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 --release 21 MathDivExact21Demo.java
java MathDivExact21Demo
~~~

**Stdout chính xác đã kiểm chứng bằng `--release 21` trên JDK đủ mới:**

~~~text
divideExact=5
StrictMath.divideExact=5
floorDivExact(-7,3)=-3
ceilDivExact(-7,3)=-2
StrictMath.floorDivExact(-7,3)=-3
StrictMath.ceilDivExact(-7,3)=-2
Math.divideExact(MIN,-1)=ArithmeticException
StrictMath.divideExact(MIN,-1)=ArithmeticException
~~~

**Lưu ý:** Mốc API là **Java 18**, không phải Java 21. Dùng `--release 21` chỉ là cách kiểm chứng trên một phiên bản LTS hiện đại có API đó. `ArithmeticException` ở ví dụ được chủ động bắt để chương trình tiếp tục in các trường hợp khác.

## 16. Bẫy khi so sánh các phương thức tương ứng

| Hiểu sai | Thực tế | Cách tránh |
| --- | --- | --- |
| `StrictMath.addExact` phát hiện tràn tốt hơn `Math.addExact` | Hai method tương ứng cùng semantics cho số nguyên | Chọn một lớp nhất quán với coding style |
| Đổi mọi `Math` sang `StrictMath` sẽ sửa tràn | Nếu vẫn dùng toán tử `+`/`*` thì không có kiểm tra tràn | Dùng đúng `...Exact` tại điểm tính |
| Java 14 mới có `Math.incrementExact` | `Math.incrementExact` có từ Java 8; `StrictMath.incrementExact` từ Java 14 | Kiểm tra mục `Since` của từng class |
| `Math.abs` luôn trả số không âm | `Math.abs(Integer.MIN_VALUE)` vẫn âm | Dùng `absExact` khi JDK ≥15 |
| `long result = a * b` với hai int chắc chắn không tràn | Phép nhân `int` có thể tràn **trước khi gán** | Cast trước hoặc dùng `multiplyFull` |
| `multiplyFull` chỉ là `multiplyExact` khác tên | `multiplyFull(int,int)` trả toàn tích `long` | Chọn theo kiểu kết quả mong muốn |
| `multiplyHigh` trả tích `long` “an toàn” | Nó chỉ trả **64 bit cao** của tích 128-bit | Chọn `multiplyExact`/`BigInteger` theo yêu cầu |
| `toIntExact` kiểm tra mọi phép toán tạo ra số đó | Nó chỉ kiểm tra giá trị `long` tại lúc chuyển xuống `int` | Kiểm tra từng phép cộng/nhân nếu cần |
| `floorDiv` luôn phát hiện tràn | Trường hợp `MIN/-1` có thể trả MIN | Java 18+ dùng `floorDivExact` nếu muốn báo |
| `divideExact` tồn tại trong Java 17 | API này từ Java 18 | Chỉ dùng khi release target phù hợp |
| `ArithmeticException` có nghĩa là một checked exception | Đây là **unchecked exception** kế thừa `RuntimeException` | Không cần `throws` bắt buộc, nhưng cần xử lý ở ranh giới nghiệp vụ |
| Exception message luôn là `integer overflow` | Chuỗi message không phải hợp đồng ổn định | Kiểm tra loại lỗi và điều kiện, không parse message |
| `Math` và `StrictMath` đều là nơi đặt phép toán dấu phẩy động **exact** | Floating-point dùng precision/rounding và có thể sinh infinity/NaN | Phân biệt integer checked arithmetic với FP |
| `+` trên `long` không tràn | `long` cũng hữu hạn | Dùng `addExact(long,long)` hoặc `BigInteger` |
| Dùng `Math.addExact` sẽ tự động tránh lỗi do unboxing null | `Integer` null khi unboxing vẫn có thể ném NPE | Validate null trước, rồi chọn overload |

## 17. Ngữ nghĩa của exception và cách xử lý

### 17.1. Không cần `try/catch` ở mọi phép tính

~~~java
static long total(long current, long delta) {
    return Math.addExact(current, delta);
}
~~~

Đây là **method minh họa**. Khi tràn, `ArithmeticException` có thể được truyền lên caller để tầng API xác định cách báo lỗi. Nếu một dịch vụ có quy định phải trả lỗi validation vì giá trị vượt phạm vi, hãy xử lý ở đúng boundary (ví dụ HTTP handler hoặc message processor).

### 17.2. Đừng bắt exception rồi dùng số sai

~~~java
// KHÔNG nên:
static int badTotal(int a, int b) {
    try {
        return Math.addExact(a, b);
    } catch (ArithmeticException ex) {
        return a + b; // Lại lấy số đã tràn; mất ý nghĩa kiểm tra.
    }
}
~~~

Phần này là **ví dụ phản diện**, không phải lời khuyên. Nó che lỗi bằng kết quả không hợp đồng.

### 17.3. Một chính sách thay thế hợp lệ phải được thiết kế trước

Nếu ứng dụng chủ động yêu cầu **saturating arithmetic** (giữ ở MIN/MAX khi vượt), đó là một **hợp đồng khác** với `addExact`. Java không có nghĩa vụ biến `addExact` thành saturating arithmetic. Có thể tự viết phương thức có kiểm tra và chọn giới hạn, nhưng phải thử cả hai dấu, `MIN/MAX` và thứ tự đánh giá.

Một ứng dụng cần số lớn chính xác thường nên dùng `BigInteger` thay vì lạm dụng saturating khi ý nghĩa nghiệp vụ không cho phép cắt ngưỡng.

### 17.4. Kiểm tra null và kiểu wrapper

~~~java
Integer quantity = null;
// int next = Math.incrementExact(quantity); // NPE khi unboxing null.
~~~

Lỗi này **không phải `ArithmeticException` do tràn**. Ngay cả khi `Math` và `StrictMath` có cùng hợp đồng kiểm tra tràn, null wrapper vẫn phải được xử lý theo hợp đồng dữ liệu đầu vào.

## 18. Bài tập có đáp án

### Bài 1 — Hai lời gọi cùng hợp đồng không?

~~~java
int a = Math.subtractExact(100, 40);
int b = StrictMath.subtractExact(100, 40);
~~~

**Đáp án:** `a == b == 60`. Với các giá trị `int` hợp lệ, hai phương thức tương ứng trả cùng kết quả; với phép trừ tràn, cả hai ném `ArithmeticException`.

### Bài 2 — Mốc lịch sử Java 14

**Hỏi:** Có phải `Math.negateExact` chỉ xuất hiện từ Java 14?

**Đáp án:** **Không**. `Math.negateExact` có từ **Java 8**, trong khi `StrictMath.negateExact` được thêm từ **Java 14**. Chữ `Exact` trong cả hai tiếp tục có cùng ý nghĩa kiểm tra tràn, không phải tính năng bị thay thế/legacy.

### Bài 3 — Vì sao phép nhân này sai?

~~~java
int a = 50_000;
int b = 50_000;
long amount = a * b;
~~~

**Đáp án:** `a * b` được tính ở `int` và **tràn trước khi gán**, khiến `amount == -1794967296L`. Có thể dùng `Math.multiplyFull(a,b)` hoặc `Math.multiplyExact((long)a,b)` để nhận `2500000000L`.

### Bài 4 — `MIN_VALUE` và dấu trừ

~~~java
int min = Integer.MIN_VALUE;
System.out.println(-min);
~~~

**Đáp án:** In `-2147483648` do overflow wraparound. `Math.negateExact(min)` và `StrictMath.negateExact(min)` đều ném `ArithmeticException`.

### Bài 5 — Hợp đồng `abs`

**Hỏi:** `Math.abs(Integer.MIN_VALUE)` và `Math.absExact(Integer.MIN_VALUE)` khác nhau thế nào?

**Đáp án:** `Math.abs` trả giá trị âm `Integer.MIN_VALUE`; `Math.absExact` ném `ArithmeticException`. `absExact` có từ Java 15 trở đi.

### Bài 6 — Quy tắc chuyển kiểu

~~~java
long n = 2_147_483_648L;
int x = (int) n;
~~~

**Đáp án:** `x == -2147483648`. `Math.toIntExact(n)` và `StrictMath.toIntExact(n)` đều ném `ArithmeticException` để tránh mất dữ liệu.

### Bài 7 — Ba phép chia

Với `x = -7`, `y = 3`, hãy nêu kết quả:
- `x / y`.
- `Math.floorDiv(x,y)`.
- `Math.ceilDivExact(x,y)` (JDK 18+).

**Đáp án:** Theo thứ tự: **-2, -3, -2**. Hai phép sau có khác biệt về hướng làm tròn; chữ `Exact` trong `ceilDivExact` còn giúp báo overflow.

### Bài 8 — Chọn checked arithmetic hay kết quả rộng

Bạn muốn nhân hai `int` mà cho phép tích lớn hơn `Integer.MAX_VALUE`, **nhưng kết quả phải là số nguyên chính xác**.

**Đáp án:** Chọn `Math.multiplyFull(int,int)` trả `long` hoặc chuyển một toán hạng sang `long` trước khi nhân. Không dùng `Math.multiplyExact(int,int)` nếu việc vượt `int` là kết quả hoàn toàn hợp lệ trong domain.

### Bài 9 — Khái quát kết quả giống nhau

**Hỏi:** Hai cặp `Math.*Exact` và `StrictMath.*Exact` cho cùng số/exception trên tất cả trường hợp thử có chứng minh JVM dùng cùng implementation không?

**Đáp án:** **Không**. Nó xác nhận **semantics quan sát được** trong phạm vi thử nghiệm; implementation, JIT intrinsic và tối ưu hóa nội bộ có thể khác và không phải hợp đồng mà ứng dụng được phép giả định.

### Bài 10 — Kết hợp nhiều phép kiểm tra

Tính `total = base + count * unit` với tất cả đầu vào `long`; không được tràn ở bất cứ bước nào.

**Đáp án tham khảo:**

~~~java
static long total(long base, long count, long unit) {
    long product = Math.multiplyExact(count, unit);
    return Math.addExact(base, product);
}
~~~

Nếu tích tràn `long`, lỗi phát sinh ngay ở `multiplyExact`. Nếu tích hợp lệ nhưng tổng tràn, `addExact` ném `ArithmeticException`. Nếu sản phẩm cần hỗ trợ giá trị lớn hơn nữa, nên tính bằng `BigInteger` rồi validate miền kết quả theo hợp đồng.

## 19. Checklist khi chọn Math hoặc StrictMath cho exact arithmetic

- [ ] Biết **kiểu của từng toán hạng** (`int`, `long`) và kiểu kết quả mong muốn.
- [ ] Chỉ định đúng overload, **widen trước khi tính** nếu kết quả cần `long`.
- [ ] Dùng `Math/StrictMath.*Exact` khi **tràn phải được phát hiện**.
- [ ] Không nhầm toán tử thường với checked arithmetic.
- [ ] Biết `Math` và `StrictMath` có **hành vi kiểm tra tràn tương đương** cho method tương ứng.
- [ ] Hiểu điểm Java 14: `StrictMath.incrementExact`/`decrementExact`/`negateExact` được thêm sau các bản `Math` tương ứng.
- [ ] Chú ý `absExact` có từ Java 15 và exact division có từ Java 18.
- [ ] Phân biệt `multiplyFull`/`multiplyHigh` với `multiplyExact`.
- [ ] Phân biệt `floorDiv`/`ceilDiv` với `floorDivExact`/`ceilDivExact`.
- [ ] Không dùng `toIntExact` để “sửa” tràn đã xảy ra ở bước cộng/nhân trước đó.
- [ ] Kiểm tra `null` nếu số được truyền dưới dạng wrapper `Integer`/`Long`.
- [ ] Khi cần độ lớn vượt `long`, cân nhắc `BigInteger`; khi có phần thập phân chính xác, cân nhắc `BigDecimal`.
- [ ] Test **MAX/MIN, 0, -1, giá trị gần biên và các operand khác kiểu**.
- [ ] Không parse chuỗi message của `ArithmeticException` làm logic nghiệp vụ.
- [ ] Kiểm chứng `--release` trước khi dùng API mới hơn target JDK.

## 20. Tóm tắt trọng tâm

1. **`StrictMath.*Exact` và `Math.*Exact` tương ứng có cùng semantics kiểm tra tràn trên số nguyên**: trả kết quả chính xác trong kiểu đích, ném `ArithmeticException` khi vượt miền biểu diễn.
2. **Điểm liên quan Java 14** là các phương thức `StrictMath.incrementExact`, `StrictMath.decrementExact`, `StrictMath.negateExact` được thêm vào `StrictMath`, trong khi `Math` đã có bản tương ứng từ Java 8.
3. **Không có lợi ích chống tràn bổ sung** chỉ vì chọn tên `StrictMath` thay `Math` cho các exact integer methods.
4. Toán tử số nguyên `+`, `-`, `*` và unary `-` **wraparound** khi tràn; `...Exact` giúp phát hiện thay vì tiếp tục với kết quả sai.
5. **Widen trước khi tính:** `(long) a * b`, `Math.multiplyExact((long)a,b)` hoặc `Math.multiplyFull(a,b)` khi tích `int*int` cần được giữ chính xác ở `long`.
6. `toIntExact` kiểm tra **chuyển hẹp `long → int`**, không sửa được phép tính đã tràn trước đó.
7. `absExact` (Java 15+) và `divideExact`/`floorDivExact`/`ceilDivExact` (Java 18+) vẫn là API hợp lệ hiện nay, nhưng phải ghi rõ version target.
8. **Sự tương đương về kết quả và exception không phải bảo đảm cùng implementation, cùng tốc độ hoặc cùng exception message.** Chọn API theo hợp đồng, khả năng đọc hiểu và yêu cầu của dự án.

**Tài liệu chính thức còn áp dụng:**
- [Oracle Java SE 17 — StrictMath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): phương thức exact, `Since` và liên kết “See Also” tới bản `Math` tương ứng.
- [Oracle Java SE 17 — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact`, `negateExact`, `toIntExact`, `absExact`, `multiplyFull` và `multiplyHigh`.
- [Oracle Java SE 21 — StrictMath](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StrictMath.html): những method mới hơn cho exact division và điều kiện tràn.
- [Oracle Java SE 21 — Math](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html): `divideExact`, `floorDivExact`, `ceilDivExact` và các method tương ứng.
- [Java SE 17 JLS — `4.2.1 Integral Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.1): miền của `int`/`long`.
- [Java SE 17 JLS — `15.17.2 Division Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2): phép chia nguyên, chia 0 và trường hợp `MIN/-1`.
- [Java SE 17 JLS — `15.18.2 Additive Operators for Numeric Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18.2): quy tắc tràn số nguyên cho toán tử cộng/trừ.
