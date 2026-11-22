# Phép chia exact và các API bổ sung theo phiên bản JDK

Java có các phép chia số nguyên `/` và `Math.floorDiv` từ lâu. Tuy nhiên, phép chia nguyên thông thường có một trường hợp tràn đặc biệt: `Integer.MIN_VALUE / -1` trả về chính `Integer.MIN_VALUE` thay vì báo lỗi. Từ **JDK 18**, lớp `Math` bổ sung `divideExact`, `floorDivExact`, `ceilDivExact` để phát hiện trường hợp tràn này. Cùng phiên bản đó có thêm `ceilDiv` và `ceilMod` phục vụ phép chia làm tròn lên.

Chữ **exact** ở đây có nghĩa là **phép chia không được âm thầm trả một thương đã tràn miền biểu diễn**, chứ **không có nghĩa hai số phải chia hết cho nhau**. Phân biệt điều này là trọng tâm khi chọn API và khi triển khai trên JDK 17 hoặc phiên bản mới hơn.

## 1. Tại sao phép chia nguyên cần kiểm tra tràn?

Các kiểu nguyên Java dùng dấu và có cận hữu hạn:

- `int`: `-2_147_483_648` đến `2_147_483_647`.
- `long`: `-9_223_372_036_854_775_808L` đến `9_223_372_036_854_775_807L`.

Miền âm có thêm một giá trị về độ lớn so với miền dương. Giá trị toán học của `-Integer.MIN_VALUE` là 2.147.483.648, vượt `int`. Vì vậy, trường hợp `Integer.MIN_VALUE / -1` có thương toán học nằm ngoài miền `int`. Tương tự với `Long.MIN_VALUE / -1L`.

```java
int min = Integer.MIN_VALUE;
System.out.println(min / -1); // -2147483648: kết quả đã tràn.
System.out.println(min % -1); // 0.
```

**Java không ném exception trong trường hợp tràn phép chia này.** Đó là hành vi được quy định cho toán tử `/`. Ngược lại, chia số nguyên cho **0** luôn ném `ArithmeticException`.

### Khác với tràn của cộng và nhân

Phép cộng/nhân cũng có thể tràn, nhưng nhiều tổ hợp giá trị có thể tạo overflow. Với phép chia nguyên có dấu, số chia khác 0, **trường hợp tràn thương duy nhất** là:

| Kiểu | Số bị chia | Số chia | Thương toán học | Thương thường của Java |
| --- | --- | --- | --- | --- |
| `int` | `Integer.MIN_VALUE` | `-1` | 2.147.483.648 | `Integer.MIN_VALUE` |
| `long` | `Long.MIN_VALUE` | `-1L` | 9.223.372.036.854.775.808 | `Long.MIN_VALUE` |

Mọi phép chia nguyên khác, với số chia khác 0, có thương được cắt phần lẻ theo hướng về 0 và vừa miền của cùng kiểu. Dù vậy, thương vẫn **bị bỏ phần dư**, vì phép chia nguyên không lưu số thập phân.

## 2. Phiên bản JDK quyết định API nào có thể sử dụng

Khi phát triển thư viện dùng chung, có hai yếu tố độc lập: JDK đang chạy và **API được phép dùng theo phiên bản mục tiêu**. Mã được biên dịch bằng JDK mới vẫn có thể không tương thích Java 17 nếu gọi phương thức chỉ xuất hiện từ JDK 18.

| API / nhóm API trong `Math` | Phiên bản bắt đầu | Ý nghĩa |
| --- | --- | --- |
| `addExact`, `subtractExact`, `multiplyExact` (overload `int,int` và `long,long`), `incrementExact`, `decrementExact`, `negateExact`, `toIntExact` | Java 8 | Kiểm tra overflow cho cộng/trừ/nhân/tăng/giảm/đổi dấu/chuyển `long` sang `int` |
| `floorDiv` và `floorMod` (các overload ban đầu) | Java 8 | Chia lấy thương làm tròn xuống, phần dư có dấu theo số chia |
| `multiplyFull(int,int)`, `multiplyHigh(long,long)`, `multiplyExact(long,int)` | Java 9 | Một số khả năng nhân và quan sát kết quả lớn hơn |
| `absExact(int)`, `absExact(long)` | Java 15 | Lấy trị tuyệt đối, ném exception khi gặp giá trị nhỏ nhất |
| **`divideExact(int,int)`, `divideExact(long,long)`** | **Java 18** | Chia theo quy tắc cắt về 0 và ném exception nếu thương tràn |
| **`floorDivExact(int,int)`, `floorDivExact(long,long)`** | **Java 18** | Chia làm tròn xuống, có kiểm tra tràn thương |
| **`ceilDivExact(int,int)`, `ceilDivExact(long,long)`** | **Java 18** | Chia làm tròn lên, có kiểm tra tràn thương |
| `ceilDiv`, `ceilMod` | Java 18 | Thương làm tròn lên và phần dư đi kèm; bản thường không kiểm tra tràn `MIN_VALUE / -1` |
| `unsignedMultiplyHigh(long,long)` | Java 18 | Lấy 64 bit cao của tích 128 bit theo nghĩa không dấu |

Bảng này nêu những API có ý nghĩa với chủ đề số học nguyên; nó không nhằm liệt kê toàn bộ phương thức của `Math`.

**Quy tắc tương thích:**

- Trên **Java 17**, `Math.divideExact`, `Math.floorDivExact`, `Math.ceilDivExact`, `Math.ceilDiv` và `Math.ceilMod` **chưa có**. Gọi chúng khi biên dịch `--release 17` sẽ báo lỗi không tìm thấy phương thức.
- Trên **Java 18+**, có thể dùng các phương thức mới, miễn môi trường biên dịch và runtime thực tế đáp ứng phiên bản đó.
- Với **Java 17**, có thể kiểm tra trường hợp tràn trước `/` hoặc `Math.floorDiv` bằng một hàm nhỏ (xem phần 6).
- Java 17 **đã có `Math.absExact`**, `Math.addExact`, `Math.multiplyExact` và `Math.toIntExact`. Không nên nhầm thời điểm xuất hiện của cả họ `Exact` là cùng một phiên bản.

Dùng lệnh sau để kiểm tra toolchain:

```bash
java -version
javac -version
javac --release 17 YourFile.java
```

`--release 17` giới hạn ngôn ngữ và API công khai ở Java 17, nên đây là phép thử phù hợp cho mã thư viện có yêu cầu tương thích Java 17. Nếu chạy ứng dụng Java 18+ API trên runtime cũ hơn, có thể gặp lỗi liên kết `NoSuchMethodError` (hoặc lỗi phiên bản class file, tùy cách biên dịch); không chỉ quan tâm mã có chạy được trên máy phát triển.

## 3. `Math.divideExact`: vẫn là phép chia lấy thương làm tròn về 0

Từ Java 18:

```java
System.out.println(Math.divideExact(7, 3));  // 2.
System.out.println(Math.divideExact(-7, 3)); // -2.
System.out.println(Math.divideExact(7, -3)); // -2.
```

Với các toán hạng bình thường, `divideExact(x,y)` cho cùng giá trị như `x / y`, tức **truncation toward zero**. Nếu phép chia có dư, cả hai đều trả thương nguyên đã cắt, **không ném exception chỉ vì có dư**.

Ví dụ `Math.divideExact(7, 3) == 2`, chứ không có lỗi “7 không chia hết cho 3”.

### Trường hợp exception

`Math.divideExact` ném `ArithmeticException` khi:

1. Số chia bằng **0**.
2. Thương bị **overflow**, tức cặp `MIN_VALUE` và `-1` của cùng kiểu.

```java
// Java 18+:
Math.divideExact(Integer.MIN_VALUE, -1); // ArithmeticException.
Math.divideExact(Long.MIN_VALUE, -1L);   // ArithmeticException.
Math.divideExact(9, 0);                  // ArithmeticException.
```

Lưu ý `Math.divideExact` **không** ném `ArithmeticException` cho `Math.divideExact(7,3)`. Không dựa vào tên phương thức để thay thế một kiểm tra **chia hết**.

### Muốn bắt buộc chia hết không có phần dư?

Một chính sách riêng có thể gồm **hai điều kiện**: thương không tràn **và** phần dư bằng 0.

```java
// Hàm minh họa Java 18+ (đặt bên trong một lớp):
static int divideWithoutRemainder(int dividend, int divisor) {
    int quotient = Math.divideExact(dividend, divisor);
    if (dividend % divisor != 0) {
        throw new ArithmeticException("Division has remainder");
    }
    return quotient;
}
```

Ví dụ `divideWithoutRemainder(12,4)` bằng 3; `divideWithoutRemainder(7,3)` ném exception do có dư; `divideWithoutRemainder(Integer.MIN_VALUE,-1)` ném exception do tràn. `Math.divideExact` đã kiểm tra số chia 0 trước phép `%`, nên không có phép modulo với 0.

Nếu bài toán chấp nhận kết quả dạng **phân số**, phải thay đổi mô hình dữ liệu (chẳng hạn giữ tử/mẫu nguyên với quy tắc chuẩn hóa riêng hoặc dùng số thập phân với chính sách làm tròn), không mong `divideExact` tạo ra 2,333… dưới dạng `int`.

## 4. Ba kiểu lấy thương: truncate, floor và ceiling

Các kiểu làm tròn thương tạo ra kết quả khác nhau khi phép chia có số dư:

| Phép toán | Quy tắc thương | Ví dụ `-7 / 3` | Ví dụ `7 / 3` |
| --- | --- | ---: | ---: |
| `x / y` hoặc `Math.divideExact(x,y)` | Cắt phần lẻ **về 0** | −2 | 2 |
| `Math.floorDiv(x,y)` hoặc `Math.floorDivExact(x,y)` | Làm tròn **xuống âm vô cùng** | −3 | 2 |
| `Math.ceilDiv(x,y)` hoặc `Math.ceilDivExact(x,y)` | Làm tròn **lên dương vô cùng** | −2 | 3 |

Các phương thức `Exact` trong bảng đều có từ **Java 18**; `floorDiv` có từ trước, còn `ceilDiv` cũng được bổ sung ở Java 18.

Các định nghĩa toán học, khi kết quả biểu diễn được:

- `trunc(x/y)`: lấy phần nguyên hướng về 0.
- `floor(x/y)`: số nguyên lớn nhất không vượt thương toán học.
- `ceil(x/y)`: số nguyên nhỏ nhất không nhỏ hơn thương toán học.

Ví dụ có dấu âm:

```java
// Java 18+:
System.out.println(Math.divideExact(-7, 3));   // -2.
System.out.println(Math.floorDivExact(-7, 3)); // -3.
System.out.println(Math.ceilDivExact(-7, 3));  // -2.

System.out.println(Math.divideExact(7, 3));   // 2.
System.out.println(Math.floorDivExact(7, 3)); // 2.
System.out.println(Math.ceilDivExact(7, 3));  // 3.
```

**Làm tròn thương và kiểm tra tràn là hai quyết định riêng.** `floorDiv` giải quyết hướng làm tròn, còn `floorDivExact` vừa dùng cùng hướng làm tròn vừa báo lỗi overflow. `ceilDiv` và `ceilDivExact` tương tự.

### Cặp phần dư phù hợp với từng kiểu thương

Để giữ quan hệ `x = quotient * y + remainder` theo số học:

| Hướng làm tròn | Thương | Phần dư đi kèm |
| --- | --- | --- |
| Truncate | `/` hoặc `divideExact` | `%` |
| Floor | `floorDiv` hoặc `floorDivExact` | `floorMod` |
| Ceiling | `ceilDiv` hoặc `ceilDivExact` | `ceilMod` |

Với `x=-7` và `y=3`:

- Truncate: thương −2, dư −1; vì `-7 = -2 * 3 + (-1)`.
- Floor: thương −3, dư 2; vì `-7 = -3 * 3 + 2`.
- Ceiling: thương −2, dư −1; cùng kết quả truncate ở trường hợp này.

Với `x=7` và `y=3`:

- Truncate: thương 2, dư 1.
- Floor: thương 2, dư 1.
- Ceiling: thương 3, dư −2; vì `7 = 3 * 3 + (-2)`.

`floorMod` có phần dư cùng dấu với **số chia** hoặc bằng 0; `ceilMod` có phần dư trái dấu với **số chia** hoặc bằng 0. Khi thực sự cần phần dư không âm, dùng `floorMod(x, m)` với **`m > 0`**. `ceilMod` không thay thế `floorMod` cho index vòng chuẩn.

**Ngoại lệ về miền biểu diễn:** nếu `x = MIN_VALUE` và `y = -1`, các phương thức không `Exact` có thể trả thương overflow. Các đẳng thức ở trên nên được hiểu theo toán học hoặc kiểm tra trong miền số phù hợp; tránh suy luận kết quả toán học chính xác từ một phép tính đã tràn.

## 5. Những phương thức Exact *không* cùng ngữ nghĩa

Chữ `Exact` trong `Math` thường chỉ nghĩa “phát hiện kết quả nguyên **vượt miền kiểu trả về**”, mỗi phương thức kiểm tra một phép toán tương ứng:

| Phương thức | Ví dụ thành công | Khi nào báo lỗi |
| --- | --- | --- |
| `Math.addExact(a,b)` | `addExact(2,3) == 5` | Tổng vượt `int`/`long` |
| `Math.subtractExact(a,b)` | `subtractExact(5,3) == 2` | Hiệu vượt miền |
| `Math.multiplyExact(a,b)` | `multiplyExact(3,4) == 12` | Tích vượt miền |
| `Math.negateExact(a)` | `negateExact(-7) == 7` | `a == MIN_VALUE` |
| `Math.absExact(a)` | `absExact(-7) == 7` | `a == MIN_VALUE` |
| `Math.incrementExact(a)` / `decrementExact(a)` | Tăng/giảm 1 | Chạm cận khi tăng/giảm |
| `Math.toIntExact(value)` | `toIntExact(42L) == 42` | Giá trị `long` không vừa `int` |
| `Math.divideExact(x,y)` | `divideExact(7,3) == 2` | Chia 0 hoặc **tràn thương** |
| `Math.floorDivExact(x,y)` | `floorDivExact(-7,3) == -3` | Chia 0 hoặc **tràn thương** |
| `Math.ceilDivExact(x,y)` | `ceilDivExact(7,3) == 3` | Chia 0 hoặc **tràn thương** |

Một số phương thức không `Exact` vẫn có thể lưu kết quả toán học chính xác trong kiểu **rộng hơn**. Chẳng hạn `Math.multiplyFull(int,int)` trả về tích của hai `int` trong `long`, vì tích của hai `int` luôn vừa `long`. `Math.multiplyHigh(long,long)` chỉ cung cấp 64 bit cao của tích rộng 128 bit, **không phải** toàn bộ tích dưới dạng một `long` chính xác.

Lưu ý `Math.abs(Integer.MIN_VALUE)` vẫn trả `Integer.MIN_VALUE`; `Math.absExact(Integer.MIN_VALUE)` mới phát hiện overflow. `Math.toIntExact` không kiểm tra số âm hay index ngoài mảng: nó chỉ kiểm tra miền `int`, không phải hợp lệ nghiệp vụ.

## 6. Java 17: xây dựng phép chia kiểm tra overflow khi chưa có `divideExact`

Nếu module đang dùng Java 17, đừng gọi phương thức Java 18 bằng cách “import thêm”. `Math` thuộc `java.base` của JDK và không thể chỉ bổ sung phiên bản API đó bằng một import.

Để có **hành vi kiểm tra tương đương** của `divideExact(int,int)` trên Java 17, xử lý cặp gây tràn trước toán tử `/`:

```java
// Đặt bên trong một class trong Java 17+:
static int divideChecked(int x, int y) {
    if (y == 0) {
        throw new ArithmeticException("/ by zero");
    }
    if (x == Integer.MIN_VALUE && y == -1) {
        throw new ArithmeticException("integer overflow");
    }
    return x / y;
}
```

Bản cho `long`:

```java
static long divideChecked(long x, long y) {
    if (y == 0L) {
        throw new ArithmeticException("/ by zero");
    }
    if (x == Long.MIN_VALUE && y == -1L) {
        throw new ArithmeticException("long overflow");
    }
    return x / y;
}
```

Các hàm trên có thể ném `ArithmeticException` như các phương thức Java 18, nhưng **nội dung message là do hàm tự đặt ra**, không phải cam kết về thông báo exception của JDK. Khi viết test nghiệp vụ, kiểm tra **loại lỗi/điều kiện**, không phụ thuộc một chuỗi thông báo bất biến.

### Java 17: kiểm tra thương floor thay vì truncate

Có thể kiểm tra tràn rồi gọi `Math.floorDiv`:

```java
static int floorDivChecked(int x, int y) {
    if (y == 0) {
        throw new ArithmeticException("/ by zero");
    }
    if (x == Integer.MIN_VALUE && y == -1) {
        throw new ArithmeticException("integer overflow");
    }
    return Math.floorDiv(x, y);
}
```

`Math.floorDiv` đã có trong Java 17; sau khi loại trừ trường hợp tràn, kết quả phù hợp ngữ nghĩa `floorDivExact` của Java 18.

Nếu yêu cầu **ceil division** trên Java 17, phải triển khai cẩn thận với cả dấu âm, không áp dụng bừa công thức `(a+b-1)/b` vì công thức này có thể tràn và sai với số âm.

Một cách tương thích với Java 17, dựa vào thương và số dư của phép chia thường, là:

```java
static int ceilDivChecked(int x, int y) {
    int quotient = divideChecked(x, y);
    int remainder = x % y;
    if (remainder != 0 && ((x ^ y) >= 0)) {
        return quotient + 1;
    }
    return quotient;
}
```

Trong phép toán trên `int`, điều kiện `(x ^ y) >= 0` kiểm tra hai số có **cùng dấu** (bit dấu của XOR là 0). Khi thương dương có phần dư, ceil cần cộng một; với thương âm, kết quả truncate đã là ceil. Cặp gây overflow đã được `divideChecked` loại trừ; `quotient + 1` ở nhánh này không vượt miền `int`. Đây là hàm minh họa một cách triển khai kiểm tra tràn, không phải API tiêu chuẩn Java 17.

Với mã mới yêu cầu Java 18+, dùng `Math.ceilDivExact` trực tiếp sẽ dễ đọc và dễ bảo trì hơn.

## 7. Ví dụ chạy độc lập trên Java 18+

Lưu chương trình dưới tên `ExactDivisionDemo18.java`:

```java
public class ExactDivisionDemo18 {
    public static void main(String[] args) {
        System.out.println("7 / 3 = " + (7 / 3));
        System.out.println("Math.divideExact(7,3) = "
                + Math.divideExact(7, 3));
        System.out.println("Math.divideExact(-7,3) = "
                + Math.divideExact(-7, 3));

        System.out.println("Math.floorDivExact(-7,3) = "
                + Math.floorDivExact(-7, 3));
        System.out.println("Math.ceilDivExact(7,3) = "
                + Math.ceilDivExact(7, 3));
        System.out.println("Math.ceilDivExact(-7,3) = "
                + Math.ceilDivExact(-7, 3));

        System.out.println("Math.floorMod(-7,3) = "
                + Math.floorMod(-7, 3));
        System.out.println("Math.ceilMod(7,3) = "
                + Math.ceilMod(7, 3));

        System.out.println("Long division = "
                + Math.divideExact(9_000_000_000L, 3L));

        try {
            Math.divideExact(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException ex) {
            System.out.println("MIN_VALUE / -1: ArithmeticException");
        }

        try {
            Math.floorDivExact(1, 0);
        } catch (ArithmeticException ex) {
            System.out.println("Division by zero: ArithmeticException");
        }

        System.out.println("7 divisible by 3? " + (7 % 3 == 0));
        System.out.println("12 divisible by 4? " + (12 % 4 == 0));
    }
}
```

Chạy với JDK 18 hoặc mới hơn:

```bash
javac --release 18 ExactDivisionDemo18.java
java ExactDivisionDemo18
```

Stdout:

```text
7 / 3 = 2
Math.divideExact(7,3) = 2
Math.divideExact(-7,3) = -2
Math.floorDivExact(-7,3) = -3
Math.ceilDivExact(7,3) = 3
Math.ceilDivExact(-7,3) = -2
Math.floorMod(-7,3) = 2
Math.ceilMod(7,3) = -2
Long division = 3000000000
MIN_VALUE / -1: ArithmeticException
Division by zero: ArithmeticException
7 divisible by 3? false
12 divisible by 4? true
```

Hai dòng cuối nhấn mạnh rằng `Math.divideExact(7,3)` vẫn bằng 2 và **không bảo đảm phép chia hết**; chỉ kiểm tra `7 % 3 == 0` mới nói được rằng hai số chia hết trong miền số nguyên.

### Ví dụ chạy riêng trên Java 17

Lưu `ExactDivisionDemo17.java`:

```java
public class ExactDivisionDemo17 {
    static int divideChecked(int x, int y) {
        if (y == 0) throw new ArithmeticException("/ by zero");
        if (x == Integer.MIN_VALUE && y == -1) {
            throw new ArithmeticException("integer overflow");
        }
        return x / y;
    }

    static int floorDivChecked(int x, int y) {
        if (y == 0) throw new ArithmeticException("/ by zero");
        if (x == Integer.MIN_VALUE && y == -1) {
            throw new ArithmeticException("integer overflow");
        }
        return Math.floorDiv(x, y);
    }

    public static void main(String[] args) {
        System.out.println("Checked quotient: " + divideChecked(-7, 3));
        System.out.println("Checked floor: " + floorDivChecked(-7, 3));
        try {
            divideChecked(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException ex) {
            System.out.println("Overflow detected");
        }
    }
}
```

```bash
javac --release 17 ExactDivisionDemo17.java
java ExactDivisionDemo17
```

Stdout:

```text
Checked quotient: -2
Checked floor: -3
Overflow detected
```

Đây là **hai tệp/chương trình độc lập** với hai mức yêu cầu JDK khác nhau. Nếu thực sự phải chạy trên Java 17, chọn ví dụ Java 17 và không gọi `divideExact`/`ceilDivExact`.

## 8. Kiểm thử biên và chọn API đúng trong thực tế

Một bộ test tối thiểu cho phép chia nguyên có kiểm tra overflow nên bao gồm:

| Đầu vào | Kết quả mong đợi của `divideExact` (Java 18+) | Điều cần xác thực |
| --- | --- | --- |
| `(7,3)` | 2 | Có dư nhưng **không** ném exception |
| `(-7,3)` | −2 | Làm tròn về 0 |
| `(7,-3)` | −2 | Làm tròn về 0 |
| `(-7,-3)` | 2 | Hai số cùng dấu |
| `(Integer.MIN_VALUE,-1)` | `ArithmeticException` | Overflow `int` |
| `(Long.MIN_VALUE,-1L)` | `ArithmeticException` | Overflow `long` |
| `(1,0)` | `ArithmeticException` | Chia cho 0 |
| `(0,3)` | 0 | Zero dividend |
| `(Integer.MIN_VALUE,1)` | `Integer.MIN_VALUE` | Giá trị nằm trong miền |

Với `floorDivExact` và `ceilDivExact`, bổ sung các test chia số âm còn dư: `(-7,3)` tương ứng −3/−2, và `(7,3)` tương ứng 2/3; kiểm tra cả số chia âm. Trên JDK 17, chạy cùng bộ trường hợp cho các hàm `divideChecked`, `floorDivChecked` hoặc `ceilDivChecked` tự xây dựng, và test việc biên dịch với `--release 17`.

### Đâu là “exact” mà nghiệp vụ thực sự cần?

Có ít nhất ba nhu cầu cần phân biệt:

1. **Không cho phép overflow:** dùng `Math.divideExact`, `floorDivExact` hoặc `ceilDivExact` từ Java 18+, hoặc kiểm tra trước khi chia trên Java 17.
2. **Không cho phép phần dư:** ngoài việc kiểm tra overflow, phải kiểm tra `x % y == 0`. Không có nghĩa vụ chia hết được suy ra chỉ từ tên `divideExact`.
3. **Cần kết quả toán học lớn hơn `long` hoặc phân số/thập phân chính xác:** dùng cấu trúc số lớn hoặc biểu diễn hợp đồng phù hợp, ví dụ `BigInteger` cho số nguyên lớn và `BigDecimal` cho giá trị thập phân với chính sách chia/làm tròn. `BigDecimal.divide` với yêu cầu exact có thể ném `ArithmeticException` khi khai triển thập phân không kết thúc; đây **là ngữ nghĩa khác** `Math.divideExact`.

Nếu dữ liệu không tin cậy đến từ bên ngoài, xử lý `ArithmeticException` ở ranh giới phù hợp và quyết định rõ lỗi nào nên báo ra ngoài. Không nên bắt toàn bộ exception rồi trả về 0, vì 0 là một kết quả hợp lệ của phép chia và có thể che giấu dữ liệu sai.

### Những lỗi hay gặp

- **Nhầm `divideExact` với “chia không dư”.** `divideExact(7,3)` trả 2, không ném lỗi.
- **Dùng API Java 18 trong dự án bắt buộc Java 17.** Kiểm tra với `javac --release 17`, không chỉ với JDK cài trên máy.
- **Dùng `Math.floorDiv` để kỳ vọng tự phát hiện overflow.** `floorDiv(MIN_VALUE,-1)` vẫn có thể trả giá trị tràn; Java 18+ có `floorDivExact`.
- **Dùng `Math.ceilDiv` và nghĩ rằng đó là checked division.** `ceilDiv` xử lý hướng làm tròn; `ceilDivExact` thêm kiểm tra overflow.
- **Đổi sang `double` rồi lấy `Math.floor` hoặc `Math.ceil` khi tính trên `long` rất lớn.** Chuyển `long` sang `double` có thể mất chính xác; ưu tiên API số nguyên.
- **Giả sử `Math.abs` có kiểm tra overflow.** `Math.abs(Integer.MIN_VALUE)` vẫn âm; `Math.absExact` từ Java 15 mới phát hiện.
- **Dùng công thức `(a+b-1)/b` để tính ceil division cho mọi đầu vào.** Công thức có thể tràn, và không xử lý chính xác nhiều trường hợp số âm.
- **Nhầm overload với kiểu trả về.** Khi dùng `int`/`long`, xem chữ ký phương thức thực tế; không tự động ép hẹp một kết quả `long` sang `int`.
- **So sánh thông báo lỗi exception như một giao thức.** Hãy xác nhận loại lỗi và ngữ nghĩa, vì message không phải là hợp đồng cố định của mọi JDK.

## 9. Tự kiểm tra

1. Tại sao `Integer.MIN_VALUE / -1` không ném exception nhưng `Math.divideExact(Integer.MIN_VALUE,-1)` lại ném? Java phiên bản nào bổ sung phương thức thứ hai?
2. `Math.divideExact(10,3)` có ném `ArithmeticException` không? Nếu muốn bắt buộc 10 chia hết cho 3, điều kiện nào còn thiếu?
3. Với `x=-7, y=3`, phân biệt thương của `/`, `floorDivExact` và `ceilDivExact`.
4. Vì sao `Math.ceilDiv(7,3)` bằng 3 nhưng `Math.ceilMod(7,3)` bằng −2? Kiểm tra quan hệ giữa thương và phần dư.
5. Đang phát triển thư viện chạy trên Java 17, vì sao dùng JDK 24 để build không mặc nhiên cho phép gọi `Math.divideExact` trong artifact tương thích Java 17?
6. Viết hàm kiểm tra chia nguyên Java 17 cho trường hợp `Long.MIN_VALUE/-1L` và trường hợp divisor 0.
7. Khi nào nên dùng `Math.toIntExact`, `Math.absExact` hoặc `Math.multiplyExact` thay vì `Math.divideExact`?

## 10. Tham khảo JDK API chính thức

- [Math — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): các overload có sẵn trước Java 18, gồm `floorDiv`, `floorMod`, `absExact`, `addExact`, `multiplyExact` và `toIntExact`.
- [Math — Java SE 18](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/Math.html): `Since: 18` của `divideExact`, `floorDivExact`, `ceilDivExact`, `ceilDiv`, `ceilMod`.
- [Java Language Specification `15.17.2 — Division Operator /](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2): quy tắc phép chia số nguyên và trường hợp overflow.

**Ghi nhớ:** **Java 18+** có `divideExact`/`floorDivExact`/`ceilDivExact` để **báo lỗi khi thương số nguyên tràn**. “Exact” không có nghĩa kết quả không có phần dư. **Java 17** vẫn triển khai được chính sách kiểm tra bằng cách bắt cặp `MIN_VALUE/-1` trước `/` hoặc `floorDiv`, và phải xác định rõ yêu cầu làm tròn, chia hết, xử lý chia 0 cũng như phiên bản JDK mục tiêu.