# `assert` để kiểm tra giả định nội bộ và bật bằng `-ea` (Java 17+)

## 1. `assert` là gì?

`assert` là câu lệnh Java dùng để kiểm tra một **giả định mà lập trình viên tin phải luôn đúng** nếu chương trình hoạt động đúng. Nó đặc biệt hữu ích để phát hiện vi phạm bất biến (*invariant*), hậu điều kiện của thuật toán hoặc trạng thái nội bộ không thể xảy ra theo thiết kế.

Nếu kiểm tra được **bật** và điều kiện sai, Java ném `java.lang.AssertionError`. Nếu điều kiện đúng, chương trình đi tiếp. Với phần lớn ứng dụng Java thông thường, assertions **mặc định tắt khi chạy**, vì vậy câu lệnh `assert` bị bỏ qua trừ khi bật bằng tùy chọn JVM như `-ea` (*enable assertions*).

Ví dụ ý tưởng:

```java
assert index >= 0 : "negative internal index: " + index;
```

Câu trên phù hợp nếu `index` là giá trị **nội bộ** được suy ra từ thuật toán vốn phải không âm. Nó **không phù hợp** làm lớp kiểm tra đầu vào duy nhất cho tham số `index` do người dùng gửi đến, vì khi assertions tắt thì phép kiểm tra không chạy.

**Phân biệt:** `assert` là câu lệnh thuộc ngôn ngữ Java, không phải phương thức `assertEquals` của JUnit và cũng không phải `throw new IllegalArgumentException(...)`. Các phương thức assertion trong framework kiểm thử hoạt động theo cơ chế riêng của framework.

## 2. Cú pháp và cơ chế đánh giá

Java có hai dạng cú pháp:

```java
assert booleanExpression;
assert booleanExpression : detailExpression;
```

- `booleanExpression` phải cho kết quả kiểu `boolean` hoặc `Boolean` (có thể được unbox). Chẳng hạn `assert count >= 0;` hợp lệ, còn `assert count;` sai nếu `count` là `int`.
- `detailExpression` là biểu thức trả về một giá trị (không được là lời gọi phương thức có kiểu kết quả `void`); giá trị đó giúp xây dựng thông tin của `AssertionError`. Không có nghĩa là câu lệnh `println` luôn được thực thi.
- Khi assertions **được bật**: Java đánh giá điều kiện; nếu `false`, nó đánh giá thêm biểu thức sau `:` (nếu có) rồi ném `AssertionError` với thông tin tương ứng.
- Khi assertions **tắt**: cả điều kiện lẫn biểu thức thông tin đều **không được đánh giá**. Do đó không nên đặt tác dụng phụ (*side effect*) trong assertion.
- Nếu điều kiện là `Boolean` có giá trị `null`, việc unbox trong lúc assertion được đánh giá có thể phát sinh `NullPointerException`. Tránh dùng một giá trị nullable làm điều kiện trực tiếp.

Trong Java 17, `assert` là từ khóa, không thể dùng để đặt tên phương thức hoặc biến. Câu lệnh được kiểm tra cú pháp và kiểu **khi biên dịch** kể cả khi assertions sẽ bị tắt ở lúc chạy.

Ví dụ khi assertion được bật:

```java
int count = 2;
assert count >= 0;                        // đúng: tiếp tục
assert count % 2 != 0 : "count is even"; // sai: ném AssertionError với thông điệp
```

Đây là **đoạn minh họa**, không phải tệp chương trình độc lập; ví dụ chạy hoàn chỉnh ở phần tiếp theo.

## 3. Ví dụ đầy đủ: nhìn thấy khác biệt khi có và không có `-ea`

Tạo tệp **`AssertDemo.java`**:

```java
public class AssertDemo {
    private static int halfEven(int number) {
        assert number % 2 == 0 : "even input required: " + number;
        return number / 2;
    }

    public static void main(String[] args) {
        System.out.println("enabled=" + AssertDemo.class.desiredAssertionStatus());
        System.out.println("half(8)=" + halfEven(8));

        try {
            System.out.println("half(5)=" + halfEven(5));
        } catch (AssertionError error) {
            System.out.println("caught=" + error.getClass().getSimpleName());
            System.out.println("detail=" + error.getMessage());
        }
    }
}
```

Từ thư mục chứa tệp (JDK 17+; chạy được trên PowerShell, CMD, bash), tạo thư mục `out` nếu chưa có, rồi biên dịch:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out AssertDemo.java
```

### Chạy bình thường: assertions tắt

```sh
java -cp out AssertDemo
```

**Stdout chính xác** khi không có cấu hình bật assertion bổ sung:

```text
enabled=false
half(8)=4
half(5)=2
```

`halfEven(5)` trả `2` do phép chia số nguyên, vì dòng `assert` không được thực thi. Ví dụ cố tình dùng số lẻ để chỉ ra lý do **không được lấy assert làm kiểm tra dữ liệu bắt buộc**.

### Chạy với `-ea`: assertions bật

```sh
java -ea -cp out AssertDemo
```

**Stdout chính xác:**

```text
enabled=true
half(8)=4
caught=AssertionError
detail=even input required: 5
```

Lần gọi với `8` thỏa điều kiện và trả `4`. Lần gọi với `5` ném `AssertionError` nên phần `System.out.println("half(5)=" + ...)` không in dòng giá trị. Khối `catch (AssertionError)` ở đây chỉ dùng **để biểu diễn kết quả cố định cho người học**; trong ứng dụng thật, assertion thất bại thường báo một lỗi lập trình cần được sửa, không nên bị bắt để giả vờ tiếp tục bình thường.

`AssertDemo.class.desiredAssertionStatus()` báo cấu hình mong muốn cho lớp; trong ví dụ chạy bằng launcher Java chuẩn, nó khớp với trạng thái assertions thực tế. Trong chương trình có class loader tự điều chỉnh assertion status, không nên xem phương thức này là cơ chế kiểm tra lỗi nghiệp vụ.

**Chú ý lệnh:** `-ea` là tùy chọn của **`java` lúc chạy**, không phải tùy chọn của `javac`. Không cần biên dịch lại giữa hai lần chạy; một file `.class` có thể cho hai hành vi vì thiết lập JVM khác nhau.

## 4. Bật/tắt assertions theo lớp và package

Các tùy chọn thường dùng với `java`:

| Tùy chọn | Tác dụng |
| --- | --- |
| `-ea` hoặc `-enableassertions` | Bật assertions cho các lớp ứng dụng thông thường theo phạm vi mặc định của JVM |
| `-da` hoặc `-disableassertions` | Tắt assertions cho các lớp theo phạm vi tương ứng |
| `-ea:lesson.AssertDemo` | Bật cho một lớp có tên đầy đủ `lesson.AssertDemo` |
| `-ea:lesson...` | Bật cho package `lesson` và các package con của nó |
| `-da:lesson.Legacy` | Tắt cho một lớp cụ thể |
| `-esa` hoặc `-enablesystemassertions` | Bật assertions trong các lớp hệ thống; thường không cần cho chương trình mới học |

Tên lớp và package trong tham số phải khớp **tên đầy đủ thực tế**. Ví dụ `AssertDemo` ở phần 3 thuộc unnamed package, vì vậy bật riêng bằng `-ea:AssertDemo` thay vì `-ea:lesson.AssertDemo`.

Các tùy chọn enable/disable có thể được phối hợp để cấu hình theo class/package; khi làm vậy, hãy dùng quy tắc của Java launcher và kiểm tra trên chính chương trình được khởi chạy. Tùy chọn đặt **trước tên lớp chứa `main`** hoặc trước `-jar` nếu chạy JAR:

```sh
java -ea -cp out AssertDemo
java -ea:AssertDemo -cp out AssertDemo
java -da -cp out AssertDemo
```

Các lệnh trên dùng tệp `AssertDemo.class` đã biên dịch ở phần 3. Đừng viết `java -cp out AssertDemo -ea` rồi cho rằng `-ea` được JVM xử lý: tại vị trí sau tên lớp, nó chỉ là đối số truyền cho `main(String[] args)`.

### Ví dụ package riêng

Tạo **`src/lesson/InvariantDemo.java`**:

```java
package lesson;

import java.util.Arrays;

public class InvariantDemo {
    private static boolean isSorted(int[] values) {
        for (int i = 1; i < values.length; i++) {
            if (values[i - 1] > values[i]) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        int[] values = {3, 1, 2};
        Arrays.sort(values);
        assert isSorted(values) : "sorting postcondition failed";

        System.out.println("enabled=" + InvariantDemo.class.desiredAssertionStatus());
        System.out.println("sorted=" + Arrays.toString(values));
    }
}
```

Biên dịch và chạy:

```sh
javac -encoding UTF-8 --release 17 -d out src/lesson/InvariantDemo.java
java -cp out lesson.InvariantDemo
java -ea:lesson.InvariantDemo -cp out lesson.InvariantDemo
```

**Stdout của lần chạy đầu (không bật assertions):**

```text
enabled=false
sorted=[1, 2, 3]
```

**Stdout của lần chạy thứ hai (bật cho đúng lớp):**

```text
enabled=true
sorted=[1, 2, 3]
```

Ví dụ này thể hiện vị trí phù hợp của `assert`: kiểm tra **hậu điều kiện nội bộ** sau khi sắp xếp. Không cần dùng assertion để quyết định có sắp xếp hay không, vì thuật toán vẫn phải chạy đúng khi assertions tắt.

## 5. Không đặt tác dụng phụ trong assertion

Đoạn code sau biên dịch hợp lệ nhưng **là kiểu viết cần tránh**:

```java
assert ++counter > 0;
```

Nếu assertions tắt, `counter` không tăng; nếu bật, `counter` tăng. Chương trình có thể thay đổi trạng thái chỉ do thêm `-ea`.

Để thấy sự khác biệt, tạo tệp **`SideEffectDemo.java`**:

```java
public class SideEffectDemo {
    public static void main(String[] args) {
        int counter = 0;
        assert ++counter == 1 : "unexpected counter";
        System.out.println("counter=" + counter);
    }
}
```

```sh
javac -encoding UTF-8 --release 17 -d out SideEffectDemo.java
java -cp out SideEffectDemo
java -ea -cp out SideEffectDemo
```

Hai lần chạy có output lần lượt:

Không có `-ea`:

```text
counter=0
```

Có `-ea`:

```text
counter=1
```

**Cách viết đúng:** thực hiện các phép cập nhật quan trọng ngoài `assert`, rồi chỉ kiểm tra một biểu thức **không làm thay đổi trạng thái**:

```java
counter++;
assert counter == 1 : "unexpected counter";
```

Đoạn sửa là minh họa tại phạm vi có biến `counter`. Ngay cả trong biểu thức `detailExpression` sau dấu `:`, cũng không nên đặt thao tác ghi file, cập nhật dữ liệu hoặc hàm có tác dụng phụ: biểu thức đó chỉ được đánh giá khi assertions bật **và điều kiện sai**.

## 6. Khi nào dùng `assert`, khi nào dùng `if` và `throw`?

| Mục đích | Cách làm |
| --- | --- |
| Bảo vệ tiền điều kiện của **public API**, tham số truyền từ caller có thể sai | `if` + `throw new IllegalArgumentException(...)` hoặc `Objects.requireNonNull(...)` |
| Kiểm tra dữ liệu ngoài: request, file, DB, CLI, network | Kiểm tra luôn chạy, có xử lý lỗi rõ ràng; không dùng `assert` thay thế |
| Kiểm tra bất biến nội bộ vốn phải đúng nếu code không có bug | `assert condition : detail;` |
| Kiểm tra hậu điều kiện của thuật toán nội bộ để tìm bug trong lúc phát triển | `assert postcondition;` |
| Kiểm tra kết quả bằng JUnit trong automated tests | Dùng assertion của JUnit/test framework theo hợp đồng kiểm thử |

**Minh họa phân biệt** (các phương thức dưới đây cần đặt trong một class thích hợp; không phải tệp chạy độc lập):

```java
// Input bên ngoài: kiểm tra phải hoạt động khi assertions tắt.
public static int positive(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException("value must be positive");
    }
    return value;
}

// Giá trị suy ra bên trong thuật toán: bảo vệ giả định lập trình.
private static int internalHalf(int provenEven) {
    assert provenEven % 2 == 0 : "algorithm produced an odd value";
    return provenEven / 2;
}
```

Nếu `provenEven` thực tế do người dùng đưa vào mà chưa kiểm tra, assertion không đủ bảo vệ hợp đồng. Vấn đề là **nguồn gốc và ý nghĩa của dữ liệu**, không chỉ mức truy cập `private`/ `public` của phương thức.

Dùng `assert false : "unreachable state";` để đánh dấu nhánh logic đáng lẽ không thể tới được là một kỹ thuật debug. Nhưng khi assertions tắt, câu lệnh đó không làm gì; vì vậy **không dùng `assert false` thay `throw`** trong trường hợp ứng dụng phải từ chối trạng thái đó ở mọi môi trường.

## 7. `AssertionError` không phải ngoại lệ nghiệp vụ thông thường

`AssertionError` kế thừa `Error`, và `Error` kế thừa `Throwable`. Nó **không** kế thừa `Exception`. Do đó:

```java
try {
    assert false : "broken assumption";
} catch (Exception ex) {
    System.out.println("not caught");
}
```

Đoạn minh họa trên không bắt được `AssertionError` khi bật assertions, vì `catch (Exception)` không nhận `Error`. Khi assertions tắt, câu lệnh `assert` bị bỏ qua và phần `catch` không chạy. Đây không phải ví dụ chương trình đầy đủ; dùng phần 3 để xem bản chạy có bắt `AssertionError` nhằm minh họa.

Không nên dùng `catch (Throwable)` hoặc `catch (AssertionError)` rộng khắp để biến lỗi lập trình thành kết quả mặc định. Nếu xuất hiện `AssertionError`, điều cần làm thường là điều tra assumption bị phá vỡ, input dẫn tới trạng thái đó và đường đi của thuật toán.

Thông báo/stack trace nếu `AssertionError` không được bắt sẽ do JVM in ra luồng lỗi chuẩn (*stderr*); nội dung stack trace chứa tên tệp/số dòng và có thể thay đổi. Vì vậy ví dụ chính bắt lỗi có chủ đích để người học nhìn thấy **stdout chính xác**, không phụ thuộc vào chi tiết stack trace.

## 8. Sai lầm phổ biến

1. **Quên `-ea`:** thấy chương trình không báo gì rồi tin assertion đã chạy. Hãy kiểm tra dòng lệnh JVM hoặc cấu hình Run/Debug trong IDE.
2. **Dùng `assert` thay validation:** khi triển khai với assertions tắt, input không hợp lệ có thể đi qua; phải dùng `if`/`throw` hoặc API validation phù hợp.
3. **Có tác dụng phụ trong biểu thức:** cập nhật biến, xóa file, gọi API tạo thay đổi có thể chỉ xảy ra trong một chế độ JVM.
4. **Nhầm `-ea` là tham số biên dịch:** `javac` vẫn phân tích và biên dịch câu lệnh; `java -ea` quyết định việc kiểm tra lúc chạy.
5. **Đặt `-ea` sau tên main class:** launcher chuyển nó cho `main` như tham số chương trình.
6. **Dùng `assert` để báo lỗi có thể dự kiến:** file không tồn tại, JSON không hợp lệ, người dùng nhập sai là tình huống vận hành thông thường, không nhất thiết biểu thị bug nội bộ.
7. **Lẫn với kiểm thử JUnit:** lời gọi `Assertions.assertEquals` là API của thư viện, không cần bật `-ea` để thực hiện logic kiểm thử của JUnit.
8. **Giả định mọi Java class đều bật chỉ nhờ `-ea`:** cấu hình có phạm vi class/package, class loader và nhóm system classes; kiểm tra lớp nào thực sự chịu tác dụng khi dùng cấu hình chọn lọc.

## 9. Checklist thực hành

Trước khi thêm một assertion, tự hỏi:

- Điều kiện này có **luôn đúng nếu thuật toán không có lỗi** hay đây là dữ liệu ngoài có thể sai hợp lệ?
- Biểu thức kiểm tra và biểu thức message có **không gây tác dụng phụ** không?
- Khi `-ea` tắt, chương trình có vẫn giữ nguyên hành vi cần thiết không?
- Nếu điều kiện sai, message có cho biết giá trị/biến quan trọng để tìm bug không?
- Khi chạy local/test, tôi đã bật assertions cho lớp hoặc package cần kiểm tra chưa?
- Sau khi sửa bug, chương trình đã chạy thử ở cả chế độ **có** và **không có `-ea`** chưa?

### Tự kiểm tra

**1. `assert value > 0;` có chạy mặc định trong hầu hết ứng dụng Java không?** Không. Cần bật assertion bằng `java -ea ...` hoặc cấu hình tương đương.

**2. Khi assertion sai và được bật, Java ném gì?** `AssertionError`, thuộc nhánh `Error`, không phải `Exception`.

**3. `assert condition : detail;` có luôn đánh giá `detail` không?** Không. Chỉ đánh giá khi assertion được bật và điều kiện sai.

**4. Có thể dùng `assert` làm kiểm tra bắt buộc cho số tiền nhập vào không?** Không. Dùng validation luôn thực thi và ném loại exception phù hợp hoặc trả kết quả lỗi theo hợp đồng API.

**5. Có cần đổi lệnh `javac` hoặc biên dịch lại để bật assertions không?** Không. Chỉ cần chạy chương trình bằng `java -ea ...` và bảo đảm lớp cần kiểm tra được bật.

**Ghi nhớ:** `assert` là công cụ phát hiện **vi phạm giả định nội bộ**; `-ea` bật việc kiểm tra ở **thời điểm chạy**. Chương trình phải giữ được hành vi đúng ngay cả khi assertion bị tắt.
