# Các bổ sung `incrementExact` của `StrictMath` — số học kiểm tra tràn

> **Ngữ cảnh:** Java 14 → **Số học kiểm tra tràn** → **Các bổ sung `incrementExact` của `StrictMath`**. Kể từ **Java 14**, `java.lang.StrictMath` có hai overload `incrementExact(int)` và `incrementExact(long)`. Chúng cộng chính xác **1** vào một số nguyên có dấu, nhưng **ném `ArithmeticException` nếu phép cộng vượt phạm vi của chính kiểu trả về**. Các overload này vẫn tồn tại trong Java hiện đại (ví dụ JDK 17/21/25) và **không phải preview/legacy API**. Bài ưu tiên JDK 17+ để học và sử dụng; không cần cài lại JDK 14 đã cũ.

## 1. Mục tiêu học tập

Sau bài này, bạn cần có khả năng:

1. Mô tả đúng chữ ký, kiểu tham số, kiểu trả về và điều kiện ném lỗi của hai overload `StrictMath.incrementExact`.
2. Giải thích tại sao `int + 1`, `long + 1` và `++` **không tự động báo lỗi tràn số nguyên**, còn `incrementExact` thì có.
3. Kiểm tra ranh giới `Integer.MAX_VALUE` và `Long.MAX_VALUE`; phân biệt chúng với `MIN_VALUE`.
4. So sánh `StrictMath.incrementExact` với `Math.incrementExact` (đã có từ Java 8) mà không gán khác biệt giả về thuật toán hay độ chính xác.
5. Hiểu lựa chọn overload theo kiểu đối số, **numeric promotion**, widening và nguy cơ ép kiểu hẹp sau khi đã kiểm tra tràn.
6. Biết chọn `int`, `long`, `BigInteger` hoặc nghiệp vụ modulo/saturating phù hợp với miền dữ liệu.
7. Áp dụng vào bộ đếm, phiên bản/sequence number và phép biến đổi dữ liệu cần **fail-fast**; giữ trạng thái không đổi nếu kiểm tra tràn thất bại.
8. Phân biệt **kiểm tra tràn** với **atomic update/thread safety** khi nhiều luồng cùng tăng counter.
9. Viết test biên và test xác định stdout trên Java 17+, không so khớp văn bản lỗi của JVM.
10. Nhận diện các lỗi phổ biến: bỏ qua exception, tăng sau khi đã thu hẹp kiểu, nhầm `Math` với `StrictMath`, dùng exact arithmetic sai cho counter cố tình quay vòng.

## 2. Vì sao tràn số nguyên nguy hiểm?

Hai kiểu số nguyên có dấu `int` và `long` của Java có giới hạn cố định:

| Kiểu | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| `int` | 32 | `-2_147_483_648` | `2_147_483_647` |
| `long` | 64 | `-9_223_372_036_854_775_808L` | `9_223_372_036_854_775_807L` |

Theo Java Language Specification, số nguyên primitive sử dụng cách biểu diễn **two's complement**. Khi phép cộng/chia số nguyên không cho phép biểu diễn kết quả đúng trong kiểu đích (ví dụ `Integer.MAX_VALUE + 1`), toán tử cộng thông thường **không tự ném ArithmeticException vì overflow**. Giá trị có thể **wrap around**, dẫn đến một số âm bất ngờ.

Ví dụ ý tưởng:

~~~java
int max = Integer.MAX_VALUE;
int wrapped = max + 1;   // -2147483648, KHÔNG tự báo lỗi
~~~

Đây là **mảnh mã**, không phải chương trình đầy đủ.

Hậu quả thực tế có thể nghiêm trọng nếu `wrapped` bị dùng làm:

- Số thứ tự tăng dần, counter hạn ngạch hoặc ID chỉ được dương.
- Kích thước dữ liệu/buffer, vị trí index hoặc offset.
- Kiểm tra giới hạn tài nguyên hoặc lượng tiền ở dạng đơn vị nguyên.
- Một phép tính tạo phiên bản mới của object/bản ghi.
- Điều kiện kiểm tra `value >= 0` sau khi tăng, nếu chương trình đã mất tính đơn điệu.

**Lưu ý:** phép chia số nguyên có những trường hợp lỗi riêng, và tính toán với dấu phẩy động có quy tắc khác; bài này **chỉ xét tăng một đơn vị cho `int`/`long`**.

## 3. API chính xác của `StrictMath.incrementExact`

Hai overload được thêm từ Java 14:

~~~java
public static int incrementExact(int a)
public static long incrementExact(long a)
~~~

Chúng thuộc `java.lang.StrictMath`, không cần import vì `java.lang` được Java import ngầm. Cách dùng trực tiếp:

~~~java
int nextInt = StrictMath.incrementExact(41);
long nextLong = StrictMath.incrementExact(41L);
~~~

Đây là **mảnh code** đặt bên trong một phương thức.

Hợp đồng API:

| Đối số | Khi nào thành công? | Kết quả thành công | Khi nào ném lỗi? |
| --- | --- | --- | --- |
| `int a` | `a < Integer.MAX_VALUE` | `a + 1` dưới dạng `int` | **Chỉ khi `a == Integer.MAX_VALUE`** |
| `long a` | `a < Long.MAX_VALUE` | `a + 1L` dưới dạng `long` | **Chỉ khi `a == Long.MAX_VALUE`** |

Khi tràn, API ném **`java.lang.ArithmeticException`**. Không có giá trị trả về từ lần gọi thất bại. Không cần bật `-ea` và không cần cờ JVM riêng; kiểm tra này là **hợp đồng runtime của phương thức**, không phải `assert`.

### Biên dễ nhầm

- `StrictMath.incrementExact(Integer.MIN_VALUE)` **hợp lệ** và trả `Integer.MIN_VALUE + 1`.
- `StrictMath.incrementExact(-1)` trả `0`.
- `StrictMath.incrementExact(0)` trả `1`.
- `StrictMath.incrementExact(Integer.MAX_VALUE - 1)` trả đúng `Integer.MAX_VALUE`.
- Chỉ `StrictMath.incrementExact(Integer.MAX_VALUE)` mới tràn với overload `int`.
- Quy tắc tương tự cho `long`: chỉ `Long.MAX_VALUE` làm overload `long` ném `ArithmeticException`.

**Không nhầm tăng với giảm:** `decrementExact` sẽ tràn khi đối số là **MIN_VALUE**, còn `incrementExact` chỉ tràn ở **MAX_VALUE**.

### Không phải phiên bản dành cho dấu phẩy động

Không có overload `incrementExact(double)` hoặc `incrementExact(float)`. Phương thức này **không** hỗ trợ các giá trị `NaN`, `Infinity`, rounding mode, `BigDecimal` hoặc IEEE-754. Tên lớp `StrictMath` không làm thay đổi bản chất **số học nguyên chính xác** của hai overload.

## 4. Vì sao đây là “bổ sung của Java 14”?

Theo Javadoc chính thức:

| API | Có từ Java | Ghi chú |
| --- | --- | --- |
| `Math.incrementExact(int)` | **Java 8** | Tăng `int`, ném lỗi khi tràn. |
| `Math.incrementExact(long)` | **Java 8** | Tăng `long`, ném lỗi khi tràn. |
| `StrictMath.incrementExact(int)` | **Java 14** | Bổ sung API tương ứng cho `StrictMath`. |
| `StrictMath.incrementExact(long)` | **Java 14** | Bổ sung API tương ứng cho `StrictMath`. |
| `StrictMath.decrementExact(int/long)` | **Java 14** | Giảm chính xác một đơn vị; overload liên quan, không phải nội dung chính. |
| `StrictMath.negateExact(int/long)` | **Java 14** | Đổi dấu chính xác; overload liên quan, không phải nội dung chính. |

Điểm cần ghi nhớ: **Java 14 không phải thời điểm Java lần đầu có `incrementExact`**. `Math.incrementExact` đã xuất hiện ở Java 8; điều mới trong bài là **thêm hai overload tương đương vào `StrictMath`**.

### `StrictMath` khác `Math` ở đây thế nào?

Một số hàm dấu phẩy động của `StrictMath` có yêu cầu đặc biệt về tính nhất quán thuật toán/khả năng tái lập. Nhưng **đối với phép cộng nguyên chính xác `incrementExact`**, cả `Math.incrementExact` lẫn `StrictMath.incrementExact` có **cùng hợp đồng kết quả và overflow**. Không có “độ chính xác cao hơn” khi gọi phiên bản `StrictMath` cho `int`/`long`.

Đặc tả yêu cầu:

~~~java
StrictMath.incrementExact(10) == Math.incrementExact(10)
~~~

trên mọi đối số không gây overflow. Khi đối số là giới hạn `MAX_VALUE`, cả hai đều phải ném `ArithmeticException`. Không nên dựa vào **nội dung message exception** trùng nhau hoặc tốc độ của hai API luôn khác nhau; đó không phải phần cần có trong contract nghiệp vụ.

### Tương thích mã nguồn với Java cũ

~~~bash
javac --release 17 ExactIncrementBasicsDemo.java
java ExactIncrementBasicsDemo
~~~

Có thể dùng overload `StrictMath` vì target 17 **mới hơn 14**. Nếu một dự án thực sự phải biên dịch với `--release 11`, `StrictMath.incrementExact` chưa có trong API mục tiêu; hãy sử dụng `Math.incrementExact` nếu cần tương thích Java 8+.

**Không dùng reflection, bản sao phương thức hoặc cờ preview** để “mang” `StrictMath.incrementExact` về một JDK runtime cũ. Chọn API theo **minimum Java version của sản phẩm**.

## 5. Ví dụ độc lập 1 — Giá trị bình thường và giới hạn

Tạo tệp **`ExactIncrementBasicsDemo.java`**:

~~~java
public class ExactIncrementBasicsDemo {
    public static void main(String[] args) {
        System.out.println("int 41 -> " +
                StrictMath.incrementExact(41));
        System.out.println("int -1 -> " +
                StrictMath.incrementExact(-1));
        System.out.println("int max-1 -> " +
                StrictMath.incrementExact(Integer.MAX_VALUE - 1));

        System.out.println("long 41 -> " +
                StrictMath.incrementExact(41L));
        System.out.println("long max-1 -> " +
                StrictMath.incrementExact(Long.MAX_VALUE - 1));

        try {
            StrictMath.incrementExact(Integer.MAX_VALUE);
        } catch (ArithmeticException expected) {
            System.out.println("int overflow detected");
        }

        try {
            StrictMath.incrementExact(Long.MAX_VALUE);
        } catch (ArithmeticException expected) {
            System.out.println("long overflow detected");
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac --release 17 ExactIncrementBasicsDemo.java
java ExactIncrementBasicsDemo
~~~

**Stdout chính xác:**

~~~text
int 41 -> 42
int -1 -> 0
int max-1 -> 2147483647
long 41 -> 42
long max-1 -> 9223372036854775807
int overflow detected
long overflow detected
~~~

Giải thích:

1. `41` là literal `int`; Java chọn overload `incrementExact(int)`.
2. `41L` là literal `long`; Java chọn overload `incrementExact(long)`.
3. `MAX_VALUE - 1` vẫn tăng được thành `MAX_VALUE`; **lần tăng kế tiếp** mới tràn.
4. Khi kiểm tra tràn thất bại, exception được bắt rồi in chuỗi ổn định do chương trình kiểm soát.
5. Demo **không so khớp nguyên văn `ArithmeticException.getMessage()`**, vì message là chi tiết triển khai không nên làm golden output.

**Đừng bỏ catch trong ứng dụng thật chỉ để in “overflow” rồi tiếp tục như chưa có lỗi.** Mỗi miền nghiệp vụ cần chính sách rõ: từ chối operation, dùng kiểu rộng hơn, hoặc thông báo sequence hết phạm vi.

## 6. So sánh với `++`, `+1` và `+=1`

Các cách sau đều tăng một đơn vị nhưng **khác hợp đồng khi tràn**:

| Cách viết | Có tự phát hiện overflow? | Ví dụ từ `Integer.MAX_VALUE` |
| --- | --- | --- |
| `value++` | Không | Wrap về `Integer.MIN_VALUE` |
| `++value` | Không | Wrap về `Integer.MIN_VALUE` |
| `value += 1` | Không | Wrap về `Integer.MIN_VALUE` |
| `value = value + 1` | Không | Wrap về `Integer.MIN_VALUE` |
| `StrictMath.incrementExact(value)` | **Có** | Ném `ArithmeticException` |
| `Math.incrementExact(value)` | **Có** | Ném `ArithmeticException` |
| `Math.addExact(value, 1)` | **Có** | Ném `ArithmeticException` |

Ngoài khác biệt overflow, prefix/postfix `++` có khác biệt về **giá trị của biểu thức** trong code phức hợp. `incrementExact` trả về **giá trị mới** nhưng **không tự thay đổi biến đầu vào**; phải gán kết quả nếu muốn cập nhật.

Ví dụ:

~~~java
int current = 10;
int next = StrictMath.incrementExact(current);
// current vẫn là 10; next là 11
~~~

Đây là mảnh code; không nên kỳ vọng phương thức tự sửa `current`.

### Ví dụ độc lập 2 — Tràn vòng và lỗi tường minh

Tạo tệp **`WrapVersusExactDemo.java`**:

~~~java
public class WrapVersusExactDemo {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;

        System.out.println("plain=" + (max + 1));

        try {
            StrictMath.incrementExact(max);
        } catch (ArithmeticException expected) {
            System.out.println("checked=overflow");
        }

        long castAfter = (long) (max + 1);
        long castBefore = ((long) max) + 1;

        System.out.println("after-cast=" + castAfter);
        System.out.println("before-cast=" + castBefore);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 WrapVersusExactDemo.java
java WrapVersusExactDemo
~~~

**Stdout chính xác:**

~~~text
plain=-2147483648
checked=overflow
after-cast=-2147483648
before-cast=2147483648
~~~

Giải thích:

- `max + 1` thực hiện phép cộng **`int`**, overflow trước khi có bước nào khác.
- `(long) (max + 1)` chỉ **widen giá trị đã overflow**, không sửa được lỗi.
- `((long) max) + 1` chuyển thành `long` **trước phép cộng**, đủ chỗ cho kết quả `2147483648`.
- `StrictMath.incrementExact(max)` giữ kiểu `int`, vì thế **ném lỗi** chứ không tự nâng kiểu trả về lên `long`.

**Nguyên tắc:** chọn kiểu đủ lớn trước khi tính toán; nếu vẫn bị giới hạn kiểu cố định, dùng exact arithmetic để phát hiện tràn.

## 7. Overload resolution và numeric promotion

`StrictMath.incrementExact` có đúng hai overload `int` và `long`, vì vậy lựa chọn phụ thuộc kiểu biểu thức ở thời điểm gọi:

| Biểu thức | Kiểu đối số | Overload được gọi | Kiểu trả về |
| --- | --- | --- | --- |
| `StrictMath.incrementExact(5)` | `int` | `incrementExact(int)` | `int` |
| `StrictMath.incrementExact(5L)` | `long` | `incrementExact(long)` | `long` |
| `StrictMath.incrementExact((long) 5)` | `long` | `incrementExact(long)` | `long` |
| `StrictMath.incrementExact(Integer.MAX_VALUE)` | `int` | `incrementExact(int)` | Ném lỗi |
| `StrictMath.incrementExact((long) Integer.MAX_VALUE)` | `long` | `incrementExact(long)` | `long` (2147483648) |
| `byte b = 127; StrictMath.incrementExact(b)` | `byte` được widen thành `int` | `incrementExact(int)` | `int` (128) |
| `short s = 32767; StrictMath.incrementExact(s)` | `short` được widen thành `int` | `incrementExact(int)` | `int` (32768) |

Những đoạn dùng `byte b` và `short s` là **mảnh lệnh trong phương thức**, không phải file Java độc lập.

### Cảnh báo ép kiểu sau exact arithmetic

~~~java
byte b = Byte.MAX_VALUE;
int correct = StrictMath.incrementExact(b);      // 128
byte wrong = (byte) StrictMath.incrementExact(b); // -128 vì narrowing!
~~~

`StrictMath.incrementExact(b)` **không tràn `int`**. Nhưng phép ép `(byte)` sau đó **thu hẹp kiểu và wrap**, không ném exception. Do đó kiểm tra tràn phải áp dụng cho **kiểu đích nghiệp vụ**, không chỉ kiểu trung gian.

Với phép chuyển `long` sang `int`, có thể dùng `Math.toIntExact(longValue)` hoặc `StrictMath.toIntExact(longValue)` (đều hiện còn áp dụng) để phát hiện giá trị không biểu diễn được dưới dạng `int`. Với `byte`/`short`, phải kiểm tra phạm vi thủ công hoặc dùng giải pháp phù hợp miền dữ liệu.

### Boxing và `null`

~~~java
Integer wrapped = null;
// StrictMath.incrementExact(wrapped) sẽ lỗi khi unbox null.
~~~

Đây là mảnh code cố ý minh họa rủi ro: nếu truyền wrapper `Integer` chứa `null` thì lỗi xảy ra ở bước **unboxing**, không phải overflow. `incrementExact` không thay thế kiểm tra dữ liệu đầu vào có hợp lệ/không null.

## 8. Khi nào dùng `StrictMath.incrementExact` trong ứng dụng?

Những trường hợp phù hợp:

- **Sequence/counter có miền hữu hạn**: giá trị cần tăng đều và tràn là lỗi nghiêm trọng.
- **Tính điểm bắt đầu hoặc giới hạn** của một đoạn dữ liệu, với điều kiện kiểu đủ rộng.
- **Thay `value++` ở vùng nhạy lỗi**: đảm bảo không lặng lẽ chuyển từ số dương lớn nhất sang số âm.
- **Validation trong batch transformations**: muốn phát hiện một phần tử không tăng được trước khi commit toàn bộ dữ liệu mới.
- **Tạo version number**: nếu phiên bản đã ở MAX, nghiệp vụ cần từ chối thay vì dùng version âm.

Nhưng `incrementExact` **không tự**:

- Đảm bảo giá trị luôn dương hoặc nằm trong một **giới hạn domain** nhỏ hơn `MAX_VALUE`.
- Bảo đảm không trùng ID giữa **nhiều tiến trình, node hoặc database transactions**.
- Bảo đảm atomicity giữa nhiều threads.
- Tự rollback database transaction hoặc I/O đã xảy ra trước exception.
- Tự chuyển sang `long`/`BigInteger` khi `int` bị tràn.
- Cung cấp chính sách “saturate at MAX” hay “wrap modulo N”.

**Ví dụ nghiệp vụ:** nếu counter là số lượng ghế còn tối đa 100, giá trị 100 tăng thành 101 hoàn toàn hợp lệ theo `StrictMath.incrementExact(int)` vì nó **không tràn `int`**. Bạn vẫn phải có `if (value >= 100) throw ...` nếu 100 là giới hạn nghiệp vụ.

## 9. Ví dụ độc lập 3 — Bộ đếm từ chối tràn và giữ trạng thái

Tạo tệp **`CheckedSequenceDemo.java`**:

~~~java
public class CheckedSequenceDemo {
    static final class Sequence {
        private int current;

        Sequence(int initial) {
            this.current = initial;
        }

        synchronized int next() {
            int candidate = StrictMath.incrementExact(current);
            current = candidate;
            return current;
        }

        synchronized int current() {
            return current;
        }
    }

    public static void main(String[] args) {
        Sequence ids = new Sequence(Integer.MAX_VALUE - 1);

        System.out.println("next=" + ids.next());

        try {
            ids.next();
        } catch (ArithmeticException expected) {
            System.out.println("sequence exhausted");
        }

        System.out.println("current=" + ids.current());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 CheckedSequenceDemo.java
java CheckedSequenceDemo
~~~

**Stdout chính xác:**

~~~text
next=2147483647
sequence exhausted
current=2147483647
~~~

Cơ chế:

1. `current` khởi đầu ở `Integer.MAX_VALUE - 1`.
2. `StrictMath.incrementExact(current)` thành công, gán `MAX_VALUE` vào `candidate`, sau đó mới cập nhật state.
3. Lần gọi tiếp theo với `current == MAX_VALUE` ném `ArithmeticException` **trước câu gán `current = candidate`**.
4. State vẫn là `MAX_VALUE`, không wrap thành số âm.
5. Hai phương thức `synchronized` bảo đảm tính nhất quán trong **một JVM instance** khi nhiều luồng gọi cùng object.

**Giới hạn:** dù có `synchronized`, đây **không phải** bộ phát ID phân tán. Nếu hai ứng dụng cùng tạo sequence từ một giá trị thì vẫn có nguy cơ trùng. Trong hệ thống nhiều tiến trình, sử dụng transaction/database sequence hoặc cơ chế cấp phát ID phù hợp.

**Đừng dùng exception làm bộ điều khiển vòng lặp bình thường** nếu chương trình có thể kiểm tra trước tình trạng hết ID và chuyển trạng thái nghiệp vụ rõ ràng. Nhưng khi thao tác thực sự yêu cầu **fail-fast** vì overflow, exception là đúng hợp đồng API.

## 10. Kiểm tra tràn **khác** thread safety

Cách viết sau không bảo đảm cập nhật an toàn nếu nhiều threads đồng thời thao tác:

~~~java
int current = 10;
current = StrictMath.incrementExact(current);
~~~

Đây là mảnh code. Nếu `current` là shared field không đồng bộ, hai threads có thể cùng đọc 10, cùng tính 11 rồi cùng ghi 11: xảy ra **lost update** dù không có overflow.

Hai bài toán khác nhau:

| Thuộc tính | `StrictMath.incrementExact` | Atomic update / synchronization |
| --- | --- | --- |
| Kiểm tra overflow của phép tăng `int`/`long` | **Có** | Không mặc nhiên |
| Tránh lost updates khi nhiều threads cùng ghi | **Không** | Có khi dùng đúng |
| Giữ trạng thái không đổi nếu overflow | Có thể thiết kế gán sau khi tính thành công | Cần thiết kế cẩn thận |
| Bảo đảm sequence duy nhất giữa nhiều JVM | Không | Không chỉ nhờ `AtomicInteger` |
| Có thể xử lý atomic update kiểu kiểm tra tràn | Có, khi kết hợp hàm thuần với CAS/lock | Có, với `updateAndGet` hoặc `synchronized` |

### `AtomicInteger.incrementAndGet()` cũng không kiểm tra overflow

`AtomicInteger.incrementAndGet()` là phép tăng **atomic**, nhưng không có hợp đồng báo `ArithmeticException` khi `int` tràn. Từ `Integer.MAX_VALUE` nó có thể wrap theo kiểu `int`.

Để có **atomic + exact**, có thể sử dụng `AtomicInteger.updateAndGet(StrictMath::incrementExact)`. Overload method reference sẽ được Java chọn phù hợp với `IntUnaryOperator`.

### Ví dụ độc lập 4 — Counter atomic có kiểm tra tràn

Tạo tệp **`AtomicExactCounterDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicExactCounterDemo {
    public static void main(String[] args) {
        AtomicInteger counter =
                new AtomicInteger(Integer.MAX_VALUE - 1);

        int updated =
                counter.updateAndGet(StrictMath::incrementExact);
        System.out.println("next=" + updated);

        try {
            counter.updateAndGet(StrictMath::incrementExact);
        } catch (ArithmeticException expected) {
            System.out.println("overflow detected");
        }

        System.out.println("current=" + counter.get());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 AtomicExactCounterDemo.java
java AtomicExactCounterDemo
~~~

**Stdout chính xác:**

~~~text
next=2147483647
overflow detected
current=2147483647
~~~

Giải thích:

- `AtomicInteger.updateAndGet(IntUnaryOperator)` cập nhật giá trị bằng cơ chế atomic compare-and-set.
- `StrictMath::incrementExact` là hàm thuần `int → int` nên phù hợp cho callback cập nhật.
- Khi input đã là `MAX_VALUE`, hàm cập nhật ném `ArithmeticException` và không tạo giá trị mới để commit.
- Theo Javadoc, hàm truyền vào `updateAndGet` **có thể được gọi lại** nếu CAS thất bại do contention. Vì vậy không ghi log, gửi email hoặc thay state bên ngoài **bên trong lambda cập nhật**.
- `AtomicInteger.updateAndGet(StrictMath::incrementExact)` an toàn cho counter **nội bộ một JVM**; không thay thế giao dịch phân tán.

Với giá trị `long`, có thể dùng `AtomicLong.updateAndGet(StrictMath::incrementExact)`, nhờ overload `long` và `LongUnaryOperator`. Kiểm tra overflow vẫn xảy ra ở `Long.MAX_VALUE`.

## 11. Ví dụ độc lập 5 — Biến đổi batch không ghi dở khi tràn

Một trường hợp thực tế: muốn tăng mỗi phần tử trong một dãy, **không muốn thay đổi dãy gốc nếu bất kỳ phần tử nào tràn**.

Tạo tệp **`BatchExactIncrementDemo.java`**:

~~~java
import java.util.Arrays;

public class BatchExactIncrementDemo {
    static int[] incrementCopy(int[] source) {
        int[] result = new int[source.length];

        for (int i = 0; i < source.length; i++) {
            result[i] = StrictMath.incrementExact(source[i]);
        }
        return result;
    }

    public static void main(String[] args) {
        int[] normal = {-1, 0, 9};
        int[] next = incrementCopy(normal);
        System.out.println(Arrays.toString(next));

        int[] boundary = {1, Integer.MAX_VALUE};
        try {
            incrementCopy(boundary);
        } catch (ArithmeticException expected) {
            System.out.println("batch rejected");
        }

        System.out.println(Arrays.toString(boundary));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 BatchExactIncrementDemo.java
java BatchExactIncrementDemo
~~~

**Stdout chính xác:**

~~~text
[0, 1, 10]
batch rejected
[1, 2147483647]
~~~

Lý do:

- `incrementCopy` tạo **mảng mới**, không sửa `source`.
- Nếu phần tử thứ hai là `Integer.MAX_VALUE`, exception xảy ra; **không có mảng kết quả nào được trả về**.
- Mảng `boundary` vẫn giữ nguyên vì chưa hề sửa nó.
- Đây là **atomicity ở mức kết quả của hàm thuần/immutable style**, **không phải** đảm bảo transaction với một database hoặc shared mutable state khác.

**Phương án sai nếu yêu cầu all-or-nothing:**

~~~java
for (int i = 0; i < values.length; i++) {
    values[i] = StrictMath.incrementExact(values[i]);
}
~~~

Đây là **mảnh code**: phần tử trước có thể đã bị thay đổi, rồi phần tử sau ném lỗi; dãy trở nên **cập nhật dở**. Nếu toàn bộ batch phải commit hoặc rollback cùng nhau, tính trên bản sao rồi publish một lần ở ranh giới có đồng bộ/giao dịch phù hợp.

## 12. Nếu `int` hết chỗ: widen trước, kiểm tra chuyển kiểu sau

`StrictMath.incrementExact(int)` không tự nâng kết quả lên `long`. Cần chọn kiểu rộng hơn **trước** khi thực hiện arithmetic.

Ví dụ:

~~~java
long next = StrictMath.incrementExact(
        (long) Integer.MAX_VALUE);
// next == 2147483648L
~~~

Đây là mảnh code. Nếu về sau vẫn cần lưu vào `int`, phải kiểm tra chuyển đổi thay vì cast làm mất dữ liệu.

### Ví dụ độc lập 6 — `long`, `toIntExact` và `BigInteger`

Tạo tệp **`WidenAndBigIntegerDemo.java`**:

~~~java
import java.math.BigInteger;

public class WidenAndBigIntegerDemo {
    public static void main(String[] args) {
        long outsideInt =
                StrictMath.incrementExact((long) Integer.MAX_VALUE);
        System.out.println("long=" + outsideInt);

        try {
            Math.toIntExact(outsideInt);
        } catch (ArithmeticException expected) {
            System.out.println("int conversion overflow");
        }

        BigInteger beyondLong =
                BigInteger.valueOf(Long.MAX_VALUE)
                          .add(BigInteger.ONE);
        System.out.println("big=" + beyondLong);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 WidenAndBigIntegerDemo.java
java WidenAndBigIntegerDemo
~~~

**Stdout chính xác:**

~~~text
long=2147483648
int conversion overflow
big=9223372036854775808
~~~

Giải thích:

- `(long) Integer.MAX_VALUE` chuyển giá trị thành `long` **trước** khi tăng; kết quả có thể biểu diễn bằng `long`.
- `Math.toIntExact(outsideInt)` từ chối chuyển giá trị vượt `Integer.MAX_VALUE` về `int`.
- `BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE)` biểu diễn số lớn hơn phạm vi `long`.
- `BigInteger` là kiểu số nguyên có độ chính xác tùy ý trong giới hạn tài nguyên/hợp đồng implementation; không phải overload của `StrictMath.incrementExact`. Nó có chi phí cấp phát và xử lý phù hợp với độ lớn dữ liệu.

**Không phải lúc nào chuyển sang `BigInteger` cũng đúng.** Nếu giá trị đang dùng làm index trong array hoặc trường database `INTEGER`, bạn vẫn phải thiết kế chính sách miền dữ liệu và schema; mở rộng số học trong JVM không tự mở rộng khả năng lưu của hệ thống khác.

## 13. Nếu cần modulo hoặc saturating thì sao?

`incrementExact` được thiết kế theo chính sách **fail on overflow**. Một số bài toán lại cần **wrap có chủ đích**, hoặc **giữ ở giới hạn tối đa**.

### 13.1. Chính sách wrap có chủ đích

Với ring buffer sức chứa `capacity > 0` và chỉ số đã được kiểm tra nằm trong `0..capacity-1`, một cách rõ ràng để tăng:

~~~java
int next = (index == capacity - 1) ? 0 : index + 1;
~~~

Đây là **mảnh code**, giả định `capacity > 0` và `0 <= index < capacity`. Điều kiện chuyển vòng **được định nghĩa theo domain**, không vô tình để overflow của `int` quyết định. Nó là logic **modulo capacity**, **không phải** trường hợp nên gọi `StrictMath.incrementExact(index)` rồi bắt exception như một tín hiệu vòng lặp bình thường.

### 13.2. Chính sách saturating

Nếu counter không được vượt một giới hạn domain `limit`, ứng dụng có thể định nghĩa:

~~~java
int next = (current >= limit) ? limit
        : StrictMath.incrementExact(current);
~~~

Đây là **mảnh code**, cần kiểm tra invariant `current <= limit` và `limit` phù hợp với `int`. Nếu mục tiêu là dừng ở `MAX_VALUE`, nhánh điều kiện tránh exception bằng quy tắc business được khai báo rõ.

### 13.3. Chính sách fail-fast

Nếu tăng từ `MAX_VALUE` là **lỗi dữ liệu hoặc vi phạm tính đơn điệu**, dùng `incrementExact` và cho phép error đi tới boundary xử lý phù hợp. Đừng “sửa” overflow bằng cách âm thầm reset về 0, vì như vậy có thể trùng ID hoặc phá điều kiện sort/order.

| Yêu cầu nghiệp vụ | Công cụ phù hợp |
| --- | --- |
| Tràn là lỗi nghiêm trọng | `StrictMath.incrementExact` / `Math.incrementExact` |
| Tăng bất kỳ delta chứ không phải 1 | `Math.addExact(x, delta)` hoặc `StrictMath.addExact` |
| Chuyển `long` sang `int` có kiểm tra | `Math.toIntExact` / `StrictMath.toIntExact` |
| Giá trị vượt `long` hợp lệ | `BigInteger.add(BigInteger.ONE)` |
| Quay vòng trong miền `0..capacity-1` | Logic modulo/domain rõ ràng |
| Dừng ở giới hạn nghiệp vụ | Explicit saturating/domain rule |
| Nhiều threads update cùng giá trị | `synchronized`/CAS/`AtomicInteger.updateAndGet` kết hợp exact |
| Nhiều JVM/database cần ID duy nhất | Database sequence/transaction/ID service |

## 14. Xử lý `ArithmeticException` đúng cách

`ArithmeticException` là **unchecked exception** (con của `RuntimeException`). API `StrictMath.incrementExact` ném exception khi overflow; caller không cần khai báo `throws` trong method signature.

Một pattern phù hợp ở biên service:

~~~java
public static int nextVersion(int current) {
    if (current < 0) {
        throw new IllegalArgumentException(
                "version must be non-negative");
    }

    try {
        return StrictMath.incrementExact(current);
    } catch (ArithmeticException e) {
        throw new IllegalStateException(
                "version number exhausted", e);
    }
}
~~~

Đây là **mảnh phương thức**, không phải chương trình độc lập. Mục tiêu minh họa việc:

1. Kiểm tra **business invariant** (`current >= 0`) tách khỏi kiểm tra overflow.
2. Dùng `StrictMath.incrementExact` cho lỗi vượt phạm vi `int`.
3. Chuyển lỗi kỹ thuật thành lỗi miền nghiệp vụ có thông điệp và **giữ cause** để debug.
4. Không swallow exception rồi trả một số mặc định có thể bị hiểu thành version hợp lệ.

**Không nên catch `ArithmeticException` quá rộng** bao quanh một đoạn xử lý phức tạp nếu bên trong còn có phép chia cho 0 hoặc các exact arithmetic khác; dễ gán nhầm nguyên nhân. Khoanh phạm vi `try` đúng phép tăng cần kiểm tra.

### Vì sao không cần bắt mỗi lần?

Trong nhiều ứng dụng, để exception đi lên tới transaction boundary là đúng lựa chọn; một lớp cao hơn sẽ rollback thao tác và ghi lỗi. Chỉ catch ở nơi có **chính sách xử lý hữu ích**, ví dụ từ chối yêu cầu tạo ID mới. Không phải bài toán nào cũng cần in lỗi ra stdout.

### Vì sao không so `getMessage()`?

Javadoc đảm bảo **kiểu ngoại lệ** `ArithmeticException` khi overflow, không yêu cầu mọi bản JVM có message giống hệt. Kiểm thử nên assert loại exception và state; với demo stdout, in chuỗi do chính bạn kiểm soát.

## 15. Kiểm tra đồng nhất với `Math.incrementExact`

Vì `Math` và `StrictMath` có **cùng hợp đồng** cho phép tăng nguyên chính xác, một bài test đơn giản có thể so cả hai trên tập các input đại diện.

Tạo tệp **`MathStrictMathParityDemo.java`**:

~~~java
public class MathStrictMathParityDemo {
    public static void main(String[] args) {
        int[] values = {
            Integer.MIN_VALUE, -1, 0, 1,
            Integer.MAX_VALUE - 1
        };

        boolean equal = true;
        for (int value : values) {
            equal &= (Math.incrementExact(value)
                    == StrictMath.incrementExact(value));
        }

        boolean mathFailed = false;
        boolean strictFailed = false;

        try {
            Math.incrementExact(Integer.MAX_VALUE);
        } catch (ArithmeticException expected) {
            mathFailed = true;
        }

        try {
            StrictMath.incrementExact(Integer.MAX_VALUE);
        } catch (ArithmeticException expected) {
            strictFailed = true;
        }

        System.out.println("equal=" + equal);
        System.out.println("overflow=" +
                (mathFailed && strictFailed));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 MathStrictMathParityDemo.java
java MathStrictMathParityDemo
~~~

**Stdout chính xác:**

~~~text
equal=true
overflow=true
~~~

Bài này kiểm tra vài boundary, **không phải chứng minh hình thức cho tất cả 2³² giá trị `int`**. Nhưng contract của Javadoc cho biết hai phương thức phải cho cùng kết quả hợp lệ và cùng loại exception overflow.

**Không cần dùng `StrictMath` chỉ vì “StrictMath chính xác hơn Math” cho `incrementExact`**; chọn nhất quán với style/API tối thiểu của dự án. Nếu sản phẩm hỗ trợ Java 8–13, `Math.incrementExact` là phương án tương thích; nếu Java 14+ và đã dùng `StrictMath` thì overload mới hoàn toàn hợp lệ.

## 16. Bảng kiểm thử biên đầy đủ

Với mỗi overload `int` và `long`, test không chỉ “giá trị thường” mà phải kiểm tra chính xác **điểm tràn**:

| Tình huống | Input | Kỳ vọng |
| --- | --- | --- |
| Tăng 0 | `0` | `1` |
| Tăng số dương | `41` | `42` |
| Tăng số âm | `-1` | `0` |
| Tăng `int` từ MIN | `Integer.MIN_VALUE` | `Integer.MIN_VALUE + 1` |
| Tăng `int` sát MAX | `Integer.MAX_VALUE - 1` | `Integer.MAX_VALUE` |
| Tăng `int` tại MAX | `Integer.MAX_VALUE` | **`ArithmeticException`** |
| Tăng `long` từ MIN | `Long.MIN_VALUE` | `Long.MIN_VALUE + 1L` |
| Tăng `long` sát MAX | `Long.MAX_VALUE - 1L` | `Long.MAX_VALUE` |
| Tăng `long` tại MAX | `Long.MAX_VALUE` | **`ArithmeticException`** |
| Math vs StrictMath | Các input hợp lệ | Kết quả bằng nhau |
| Math vs StrictMath tại MAX | Cả hai kiểu | Cùng ném `ArithmeticException` |
| Byte argument | `byte 127` | `int 128` vì widening |
| Narrowing sau exact | `(byte) incrementExact((byte)127)` | `-128` vì cast; **không có overflow exception ở bước int** |

### Mẫu kiểm thử thuần Java không cần thư viện

Nếu không dùng JUnit/TestNG, có thể viết helper assert:

~~~java
static void expectIntOverflow(int value) {
    try {
        StrictMath.incrementExact(value);
        throw new AssertionError("Expected ArithmeticException");
    } catch (ArithmeticException expected) {
        // PASS: đúng loại exception.
    }
}
~~~

Đây là **mảnh phương thức**; cần đặt trong một class. Không bỏ qua trường hợp `MAX_VALUE - 1` vẫn hợp lệ, vì lỗi off-by-one ở ranh giới thường nguy hiểm hơn input bình thường.

### Nếu dùng JUnit 5 hiện hành

Một unit test ngắn có thể là:

~~~java
assertEquals(Integer.MAX_VALUE,
        StrictMath.incrementExact(Integer.MAX_VALUE - 1));

assertThrows(ArithmeticException.class,
        () -> StrictMath.incrementExact(Integer.MAX_VALUE));
~~~

Đây là **mảnh test**, yêu cầu JUnit Jupiter và import `assertEquals`/`assertThrows` tương ứng. Không phải ví dụ độc lập chỉ bằng `javac`, vì JUnit là dependency riêng.

## 17. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Cho rằng `StrictMath.incrementExact` có từ Java 8 | Hai overload `StrictMath` được thêm từ **Java 14** | Nếu target Java 8–13, dùng `Math.incrementExact`. |
| Cho rằng Java 14 mới có exact increment nói chung | `Math.incrementExact` đã có từ Java 8 | Phân biệt lớp và mốc `Since`. |
| Coi `value++` sẽ ném lỗi ở MAX | Primitive `int`/`long` wrap on overflow | Dùng exact arithmetic khi cần fail-fast. |
| Cho rằng tăng `MIN_VALUE` gây overflow | Tăng từ MIN là hợp lệ | Overflow tại **MAX_VALUE** đối với increment. |
| Cho rằng `StrictMath` luôn chính xác hơn `Math` cho `int` | Hai API có cùng hợp đồng tăng nguyên | Chọn API phù hợp minimum Java target. |
| Truyền `Integer.MAX_VALUE` nhưng kỳ vọng overload `long` | Literal/biến kiểu `int` chọn int overload | Widen **trước khi gọi**: `(long) value`. |
| Ép `(long)(intMax + 1)` | Overflow xảy ra trước cast | `((long) intMax) + 1` hoặc gọi overload `long`. |
| Ép `(byte) StrictMath.incrementExact(byteValue)` | Kiểm tra ở `int`, narrowing vẫn mất dữ liệu | Kiểm tra giới hạn của **kiểu đích**. |
| Dùng `incrementExact` để kiểm tra hạn mức 100 | Phương thức chỉ kiểm tra tràn primitive | Thêm domain validation `<= 100`. |
| Dùng `incrementExact` cho counter chia sẻ mà không khóa | Exact không đồng nghĩa atomic | `synchronized` hoặc `AtomicInteger.updateAndGet`. |
| Dùng `AtomicInteger.incrementAndGet` và tưởng có overflow check | Atomic increment vẫn có thể wrap | `updateAndGet(StrictMath::incrementExact)`. |
| Có side effect trong `updateAndGet` lambda | CAS có thể retry lambda nhiều lần | Update function phải **side-effect-free**. |
| Tăng mảng tại chỗ rồi exception ở cuối | Mảng có thể bị cập nhật dở | Tính copy trước, publish khi hoàn tất. |
| Catch overflow rồi trả 0 | Có thể tạo ID/version trùng | Từ chối thao tác hoặc chọn kiểu/schema phù hợp. |
| Dùng `BigInteger` nhưng DB chỉ lưu `int` | Miền lưu trữ vẫn bị giới hạn | Cập nhật schema/chính sách đồng bộ. |
| Bắt `ArithmeticException` quanh đoạn quá rộng | Có thể bắt nhầm chia 0 hoặc exact khác | Catch sát phép tăng hoặc chuyên biệt domain error. |
| Kiểm tra nguyên văn exception message | Message không phải hợp đồng nghiệp vụ | Kiểm tra type/state. |
| Dùng exact cho ring buffer cần quay vòng | Exact ném lỗi ở MAX, không triển khai modulo | Viết logic modulo có kiểm tra phạm vi. |

## 18. Lưu ý về hiệu năng và thiết kế

`incrementExact` là phép toán đơn giản, không cần cấu hình VM hay phép toán dấu phẩy động. Tuy nhiên nó có chi phí kiểm tra overflow và có thể chịu ảnh hưởng JIT/CPU; **không khẳng định `StrictMath` luôn nhanh hơn hoặc chậm hơn `Math`** nếu chưa đo trên đúng JDK/workload.

Khi chọn API:

- Nếu overflow là **bug nghiêm trọng**, độ rõ ràng và fail-fast thường quan trọng hơn tối ưu vi mô.
- Nếu counter có thể đạt giới hạn, cần thiết kế **cách xử lý trạng thái hết phạm vi**; chỉ chọn `long` không loại bỏ vấn đề vĩnh viễn.
- Nếu bài toán đòi **quay vòng hợp lệ**, logic modulo là chính sách của domain, không phải phép tràn bị bỏ qua.
- Nếu ứng dụng có **concurrency**, bổ sung synchronization hoặc CAS; exact arithmetic không biến gán thành atomic.
- Nếu giá trị sẽ được **lưu vào hệ thống khác**, xác minh schema/range trước khi publish.
- Nếu input không tin cậy, kiểm tra parsing, null, dấu âm, giới hạn miền dữ liệu tách biệt với overflow.
- Nếu cần số lớn hơn `long`, `BigInteger` có thể phù hợp nhưng cần xét memory, serialization, database và throughput.

**Không dùng `strictfp` hoặc các khái niệm rounding dấu phẩy động để “bật chế độ exact increment”**. `StrictMath.incrementExact` đã xác định rõ hành vi trên `int`/`long`, không cần modifier đặc biệt.

## 19. Bài tập luyện tập có đáp án định hướng

### Bài 1 — Tìm điều kiện ném lỗi

Đoạn nào ném `ArithmeticException`?

~~~java
StrictMath.incrementExact(Integer.MIN_VALUE);
StrictMath.incrementExact(Integer.MAX_VALUE - 1);
StrictMath.incrementExact(Integer.MAX_VALUE);
~~~

**Đáp án:** chỉ dòng cuối. MIN tăng lên MIN+1 hợp lệ, MAX−1 tăng thành MAX hợp lệ.

### Bài 2 — Chọn overload đúng

~~~java
int x = Integer.MAX_VALUE;
long a = StrictMath.incrementExact((long) x);
~~~

Giá trị `a` là bao nhiêu? **Đáp án:** `2147483648L`. Nếu bỏ `(long)`, overload `int` ném exception.

### Bài 3 — Tràn trước hay sau cast?

~~~java
long a = (long) (Integer.MAX_VALUE + 1);
long b = ((long) Integer.MAX_VALUE) + 1;
~~~

**Đáp án:** `a == -2147483648L` vì `int` overflow trước khi cast; `b == 2147483648L` vì phép tính thực hiện trên `long`.

### Bài 4 — Điểm vào của Java 14

Dự án dùng Java 11 và muốn tăng `int` có kiểm tra tràn. Có gọi `StrictMath.incrementExact` được không?

**Đáp án:** không theo API Java 11; dùng `Math.incrementExact` đã có từ Java 8. Khi nâng minimum version lên Java 14+, overload `StrictMath` trở thành lựa chọn hợp lệ.

### Bài 5 — Counter concurrent

Một thread gọi `counter.incrementAndGet()`, thread khác cũng gọi trên `AtomicInteger` đã bằng `Integer.MAX_VALUE`. Liệu API có tự ném overflow không?

**Đáp án:** không. Đây là atomic increment nhưng có thể wrap. Nếu yêu cầu exact, dùng `counter.updateAndGet(StrictMath::incrementExact)` với hàm cập nhật thuần hoặc khóa và exact check.

### Bài 6 — Miền nghiệp vụ 0..100

Một biến `count=100`, gọi `StrictMath.incrementExact(count)` có bị lỗi không?

**Đáp án:** không, kết quả `101` vẫn là `int` hợp lệ. Phải có domain check riêng nếu tối đa nghiệp vụ là 100.

### Bài 7 — Biến đổi dãy

Muốn tăng mỗi phần tử của mảng nhưng dừng toàn bộ khi có `Integer.MAX_VALUE`, không sửa các giá trị trước đó. Bạn chọn in-place hay copy?

**Đáp án:** tính trên **mảng mới** hoặc transaction staging trước, chỉ publish khi toàn bộ thành công; code in-place có thể ghi dở.

### Bài 8 — So sánh hai lớp

Có cần đổi mọi `Math.incrementExact` sang `StrictMath.incrementExact` vì “StrictMath chính xác hơn” không?

**Đáp án:** không. Cả hai có cùng semantics cho exact integer increment, khác chủ yếu ở thời điểm API có mặt và style; với Java 8–13 còn cần `Math`.

### Bài 9 — Sử dụng BigInteger

Giá trị hiện là `Long.MAX_VALUE`, doanh nghiệp muốn tăng tiếp mà không wrap/throw ở `long`. Cách nào phù hợp?

**Đáp án:** chuyển domain sang `BigInteger`, ví dụ `BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE)` và xem xét lại toàn bộ schema/API/serialization.

## 20. Lệnh chạy toàn bộ ví dụ Java 17

Mỗi class `public` phải nằm trong file Java trùng tên. Các lệnh chạy từ thư mục chứa những file đã được tạo ở phần trên:

~~~bash
javac --release 17 ExactIncrementBasicsDemo.java
java ExactIncrementBasicsDemo

javac --release 17 WrapVersusExactDemo.java
java WrapVersusExactDemo

javac --release 17 CheckedSequenceDemo.java
java CheckedSequenceDemo

javac --release 17 AtomicExactCounterDemo.java
java AtomicExactCounterDemo

javac --release 17 BatchExactIncrementDemo.java
java BatchExactIncrementDemo

javac --release 17 WidenAndBigIntegerDemo.java
java WidenAndBigIntegerDemo

javac --release 17 MathStrictMathParityDemo.java
java MathStrictMathParityDemo
~~~

Các ví dụ dùng `java.lang.StrictMath` nên không cần import `StrictMath`. Dòng stdout trong từng ví dụ là kết quả xác định nếu chạy thành công. Không cần dependency ngoài JDK, không cần preview flags.

### Tóm tắt giá trị kiểm tra

| Chương trình | Tín hiệu thành công |
| --- | --- |
| `ExactIncrementBasicsDemo` | Giá trị tăng thường/ranh giới đúng; hai lỗi MAX được bắt. |
| `WrapVersusExactDemo` | Phân biệt rõ phép cộng `int` tràn và cast trước phép tính. |
| `CheckedSequenceDemo` | Khi hết phạm vi, state vẫn giữ `Integer.MAX_VALUE`. |
| `AtomicExactCounterDemo` | Atomic update tăng tới MAX; lần sau ném lỗi và state không wrap. |
| `BatchExactIncrementDemo` | Tăng mảng mới khi thành công; mảng gốc không đổi khi fail. |
| `WidenAndBigIntegerDemo` | Widen `int → long`, kiểm tra narrow về int và tính số vượt long. |
| `MathStrictMathParityDemo` | Hai API cho cùng kết quả hợp lệ và cùng phát hiện overflow. |

## 21. Checklist trước khi dùng trong dự án thật

- [ ] Minimum supported Java version là **14+** nếu dùng `StrictMath.incrementExact`?
- [ ] Nếu cần Java 8–13, đã chọn `Math.incrementExact`?
- [ ] Phép tính đúng là **tăng 1**, không phải cộng một delta khác?
- [ ] Kiểu dữ liệu thật là `int` hay `long`, và overload được chọn như mong muốn?
- [ ] Đã kiểm tra **MAX_VALUE** là điểm overflow duy nhất cho increment?
- [ ] Đã phân biệt overload với phép cast/narrowing sau đó?
- [ ] Đã có domain validation cho giới hạn nhỏ hơn MAX?
- [ ] Overflow được xử lý bằng chính sách rõ (reject/retry với kiểu rộng hơn/stop), không trả 0 tùy tiện?
- [ ] State chỉ được commit **sau khi** phép tính thành công?
- [ ] Nếu nhiều threads, có synchronization/CAS, không dùng phép gán thường?
- [ ] Nếu dùng `updateAndGet`, update function side-effect-free?
- [ ] Nếu nhiều ứng dụng/database cùng cấp ID, có cơ chế uniqueness phân tán?
- [ ] Test đủ `MIN_VALUE`, `-1`, `0`, `MAX_VALUE-1`, `MAX_VALUE` cho hai overload?
- [ ] Test kiểm tra exception type và state, không dựa vào message JVM?
- [ ] Có lệnh build/run và tài liệu API chính thức khớp JDK mục tiêu?

## 22. Tài liệu chính thức và còn áp dụng

1. [Oracle Java SE 25 — `StrictMath` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StrictMath.html): `incrementExact(int)` và `incrementExact(long)`, `Since: 14`, `ArithmeticException` ở MAX; các overload liên quan.
2. [Oracle Java SE 14 — `StrictMath` API](https://docs.oracle.com/en/java/javase/14/docs/api/java.base/java/lang/StrictMath.html): kiểm tra mốc **Java 14** của các phương thức được bổ sung.
3. [Oracle Java SE 25 — `Math` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html): `incrementExact`, `addExact` và `toIntExact`, gồm so sánh hợp đồng với `StrictMath`.
4. [Oracle Java SE 14 — `Math` API](https://docs.oracle.com/en/java/javase/14/docs/api/java.base/java/lang/Math.html): `Math.incrementExact` đã có từ **1.8 (Java 8)**.
5. [Java Language Specification SE 25 — Integer operations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.2.2): phạm vi `int`/`long`, kết quả số nguyên cố định và overflow.
6. [Oracle Java SE 25 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): `updateAndGet` atomic, function có thể được gọi lại do contention; `incrementAndGet` không kiểm tra overflow.
7. [Oracle Java SE 25 — `AtomicLong`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): atomic update tương tự cho `long`.
8. [Oracle Java SE 25 — `BigInteger`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigInteger.html): số nguyên có độ chính xác tùy ý theo API hiện hành; dùng khi miền giá trị vượt `long`.

**Ghi nhớ:** `StrictMath.incrementExact(int/long)` **được bổ sung từ Java 14** và vẫn dùng tốt trên JDK hiện đại. Nó **trả đúng `a + 1` nếu biểu diễn được trong cùng kiểu**, và **ném `ArithmeticException` duy nhất khi đầu vào là `MAX_VALUE` của kiểu đó**. Đừng nhầm với phép `++` wrap, đừng tin rằng `StrictMath` chính xác hơn `Math` cho số nguyên, và đừng nghĩ một phép kiểm tra tràn tự làm cho việc cập nhật state trở nên atomic.