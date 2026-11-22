# Unboxing tham chiếu `null` gây `NullPointerException` trong Java

> **Java core — language-basics / Lớp bao nguyên thủy**  
> **Yêu cầu:** Java 17+, một chương trình Java chạy độc lập, không cần thư viện ngoài.  
> **Mục tiêu:** Nhận diện vị trí Java tự **unbox** wrapper về primitive, giải thích vì sao wrapper bằng `null` phát sinh `NullPointerException` (NPE), và chọn cách kiểm tra hoặc quy định dữ liệu đầu vào trước khi tính toán.

## 1. Unboxing là gì và vì sao `null` gây lỗi?

Các lớp bao nguyên thủy (*wrapper classes*) như `Integer`, `Long`, `Double`, `Boolean` và `Character` là **kiểu tham chiếu**. Chúng có thể nhận `null`; các kiểu nguyên thủy tương ứng như `int`, `long`, `double`, `boolean` và `char` thì không.

**Unboxing** là chuyển một giá trị wrapper thành primitive tương ứng, thường được compiler thực hiện tự động:

~~~java
Integer wrapped = 12;
int value = wrapped; // Tự động unboxing: tương đương lấy intValue().
~~~

Nếu tham chiếu wrapper bằng `null`, không có object nào để lấy giá trị primitive:

~~~java
Integer missing = null;
// int value = missing; // Chạy đến đây sẽ ném NullPointerException.
~~~

Java có thể tự sinh thao tác gần tương đương `missing.intValue()`. Vì `missing == null` nên việc gọi phương thức để lấy giá trị primitive gây **NPE**.

**Quan trọng:** Bản thân câu lệnh `Integer missing = null;` **không** gây NPE. Lỗi xảy ra tại **điểm sử dụng cần primitive**. Wrapper và primitive có hợp đồng dữ liệu khác nhau: wrapper có thể biểu diễn “thiếu giá trị”, primitive thì không.

## 2. Những chỗ Java có thể unbox ngầm

| Ngữ cảnh | Ví dụ có thể gây NPE | Lý do |
| --- | --- | --- |
| Gán wrapper sang primitive | `Integer x = null; int n = x;` | Cần `int` nên unbox `Integer` |
| Phép toán số học | `Integer x = null; int sum = x + 1;` | `+` cần toán hạng số nguyên thủy |
| So sánh với primitive | `Integer x = null; boolean ok = x == 0;` | So sánh số dẫn tới unbox `x` |
| Điều kiện Boolean | `Boolean flag = null; if (flag) { ... }` | `if` cần `boolean` |
| Phép logic Boolean | `Boolean flag = null; boolean ok = flag && true;` | Vế trái phải được unbox |
| Tăng/giảm wrapper | `Integer x = null; x++;` | Phải đọc giá trị số trước khi tăng |
| Biểu thức ba ngôi | `Integer x = null; int n = true ? x : 10;` | Nhánh được chọn cần giá trị `int` |

**Ngược lại:** `x == null` **không unbox `x`** vì đang so sánh một tham chiếu với `null`. Nó là cách kiểm tra `null` hợp lệ. So sánh hai biến `Integer` bằng `==` có thể chỉ so identity tham chiếu; đừng dùng phép so ấy để suy ra hai **giá trị** wrapper bằng nhau.

### Hai tình huống dễ gây nhầm

~~~java
Integer count = null;
boolean missing = (count == null); // true: không unbox.
// boolean zero = (count == 0);    // NPE: cần unbox để so với int 0.
~~~

~~~java
Boolean approved = null;
// if (approved) { ... } // NPE: điều kiện if yêu cầu boolean.
boolean safeApproved = Boolean.TRUE.equals(approved); // false.
~~~

`Boolean.TRUE.equals(approved)` an toàn khi đối số là `null`. Cách này có nghĩa nghiệp vụ: **chỉ đúng khi giá trị tường minh là true**, còn `false` và `null` đều xử lý như false. Nếu thiếu dữ liệu phải báo lỗi, **không** nên âm thầm đổi `null` thành false.

## 3. Ví dụ Java 17+ hoàn chỉnh, chạy được

Tạo tệp **UnboxingNullDemo.java** với toàn bộ nội dung sau:

~~~java
import java.util.Objects;

public final class UnboxingNullDemo {
    private static int requiredQuantity(Integer quantity) {
        return Objects.requireNonNull(quantity, "quantity is required");
    }

    private static int quantityOrZero(Integer quantity) {
        return quantity != null ? quantity : 0;
    }

    private static boolean isEnabled(Boolean flag) {
        return Boolean.TRUE.equals(flag);
    }

    public static void main(String[] args) {
        Integer present = 7;
        Integer missing = null;
        Boolean missingFlag = null;

        System.out.println("present=" + requiredQuantity(present));
        System.out.println("nullReference=" + (missing == null));
        System.out.println("safeDefault=" + quantityOrZero(missing));
        System.out.println("safeBoolean=" + isEnabled(missingFlag));
        System.out.println("safeGuard="
                + (missing != null && missing > 0));
        System.out.println("bothNullEqual=" + Objects.equals(missing, null));

        try {
            int number = missing;
            System.out.println("number=" + number);
        } catch (NullPointerException ex) {
            System.out.println("assignmentNpe=true");
        }

        try {
            int total = missing + 1;
            System.out.println("total=" + total);
        } catch (NullPointerException ex) {
            System.out.println("arithmeticNpe=true");
        }

        try {
            boolean isZero = missing == 0;
            System.out.println("isZero=" + isZero);
        } catch (NullPointerException ex) {
            System.out.println("comparisonNpe=true");
        }

        try {
            if (missingFlag) {
                System.out.println("enabled");
            }
        } catch (NullPointerException ex) {
            System.out.println("booleanNpe=true");
        }

        try {
            int chosen = true ? missing : 10;
            System.out.println("chosen=" + chosen);
        } catch (NullPointerException ex) {
            System.out.println("ternaryNpe=true");
        }

        try {
            requiredQuantity(missing);
        } catch (NullPointerException ex) {
            System.out.println("requiredError=" + ex.getMessage());
        }

        Integer[] values = {3, null, 5};
        int sum = 0;
        for (Integer element : values) {
            if (element != null) {
                sum += element;
            }
        }
        System.out.println("nonNullSum=" + sum);
    }
}
~~~

Biên dịch/chạy từ thư mục chứa tệp (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 UnboxingNullDemo.java
java UnboxingNullDemo
~~~

**Expected output chính xác:**

~~~text
present=7
nullReference=true
safeDefault=0
safeBoolean=false
safeGuard=false
bothNullEqual=true
assignmentNpe=true
arithmeticNpe=true
comparisonNpe=true
booleanNpe=true
ternaryNpe=true
requiredError=quantity is required
nonNullSum=8
~~~

Giải thích kết quả:

1. `requiredQuantity(present)` nhận `Integer(7)` hợp lệ, trả primitive 7. `missing == null` chỉ kiểm tra tham chiếu nên không gây lỗi.
2. `quantityOrZero(null)` chọn số 0 theo hợp đồng hàm. `Boolean.TRUE.equals(null)` trả false. Biểu thức `missing != null && missing > 0` dừng tại vế trái false nên không unbox.
3. Gán sang `int`, cộng với 1, so với `int 0` và dùng `Boolean` trong `if` đều cần unboxing của một tham chiếu `null`: cả bốn khối bắt NPE tương ứng.
4. `true ? missing : 10` chọn nhánh `missing`, nhưng kiểu biểu thức kết quả cần `int`, nên unboxing xảy ra và gây NPE. Dấu `?:` **không tự động bảo vệ khỏi null**.
5. `Objects.requireNonNull(missing, "quantity is required")` ném NPE **có chủ đích tại ranh giới hàm**, với thông điệp ổn định `quantity is required`.
6. Mảng `Integer[]` chứa một phần tử `null`. Guard từng phần tử trước phép `sum += element` giúp chỉ cộng các giá trị có mặt: `3 + 5 = 8`.

Các khối `catch` ở đây **chỉ để minh họa từng nguồn NPE và in kết quả dễ kiểm chứng**. Trong ứng dụng thật, hãy kiểm tra đầu vào và xử lý đúng nghiệp vụ **trước khi unbox**, thay vì dùng `try/catch NullPointerException` như luồng điều khiển bình thường.

## 4. Đặt kiểm tra ở đâu cho đúng?

Đầu tiên cần quyết định `null` có phải trạng thái hợp lệ không.

| Hợp đồng nghiệp vụ | Cách xử lý | Lưu ý |
| --- | --- | --- |
| Giá trị **bắt buộc** | `Objects.requireNonNull(x, "x required")` | Phát hiện sớm, lỗi rõ tại ranh giới API |
| Giá trị tùy chọn, có default hợp lệ | `x != null ? x : defaultValue` | Chỉ dùng default khi nghiệp vụ cho phép |
| Cờ chỉ đúng khi tường minh true | `Boolean.TRUE.equals(flag)` | `null` được xem như không bật |
| Cần bỏ qua giá trị thiếu trong danh sách | `if (element != null) sum += element;` | Kiểm tra **từng phần tử**, không chỉ array/list |
| `null` biểu thị trạng thái chưa nhập | Giữ wrapper hoặc trả lỗi nghiệp vụ | Không tự biến thành 0/false khi điều đó sai nghĩa |

Nếu dữ liệu buộc phải có mặt, cách sau rõ ràng:

~~~java
static int requireScore(Integer score) {
    return Objects.requireNonNull(score, "score must not be null");
}
~~~

Hàm từ chối `null` **trước khi** chuyển sang `int`. Nếu yêu cầu đầu vào của một API là primitive và không có lý do biểu diễn thiếu dữ liệu, bạn có thể khai báo tham số `int` ngay từ đầu; tuy vậy, **người gọi vẫn có thể gây NPE** ở chỗ chuyển `Integer null` thành `int` trước lời gọi.

## 5. Guard an toàn và bẫy short-circuit

~~~java
Integer quantity = null;

boolean positive = quantity != null && quantity > 0; // false, an toàn.
// boolean wrongOrder = quantity > 0 && quantity != null; // NPE.
// boolean wrongOperator = quantity != null & quantity > 0; // NPE.
~~~

`&&` và `||` có **short-circuit**. Với `a && b`, vế phải **không chạy** khi vế trái false. Toán tử boolean `&`, trái lại, đánh giá cả hai vế nên có thể unbox một wrapper null dù điều kiện trước đã false.

Với biểu thức ba ngôi, cần xác định **kiểu của toàn biểu thức**, không chỉ nhìn từng nhánh:

~~~java
Integer nullable = null;
int safe = nullable == null ? 10 : nullable; // 10.
~~~

Ở đây kiểm tra `nullable == null` chọn nhánh `10`, tránh unboxing null. Nếu chọn nhánh `nullable`, nó chỉ được unbox khi đã không null.

**Chú ý:** `Objects.equals(a, b)` là cách so sánh wrapper chịu được `null`. Nhưng `Objects.equals(null, null)` trả **true**; chỉ dùng nếu quy tắc đó hợp nghiệp vụ.

## 6. Nhận diện NPE qua stack trace và kiểu dữ liệu

Khi nhìn một NPE thực tế:

1. Tìm frame đầu tiên thuộc mã của bạn và **dòng** phát sinh lỗi.
2. Xác định biến nào có kiểu **wrapper** như `Integer`/`Boolean`, thay vì primitive.
3. Kiểm tra biểu thức có **ngữ cảnh đòi primitive**: toán tử `+`, `-`, `*`, `/`, so sánh với literal số, `if (Boolean)`, phép gán sang primitive hoặc `?:`.
4. Lần về nơi wrapper được gán `null`: dữ liệu DB nullable, DTO, kết quả tìm kiếm, phần tử collection hoặc giá trị chưa khởi tạo.
5. Quyết định một trong hai hợp đồng: **từ chối null sớm** hoặc **xử lý null hợp lệ theo quy tắc**. Bổ sung testcase cho cả trường hợp giá trị hợp lệ và `null`.

**Không nhầm lỗi khác:** `Integer.parseInt("abc")` ném `NumberFormatException`, không phải NPE do unboxing. Còn `Integer.parseInt(null)` cũng cần được xem xét theo tài liệu API riêng, không suy diễn mọi lỗi liên quan `null` đều là NPE tự động.

## 7. Bài tập tự kiểm tra

**Bài 1.** Cho `Integer x = null;`. Dự đoán `x == null`, `x == 0` và `int y = x;`. Giải thích cụ thể thao tác nào buộc unbox.

**Bài 2.** Cho `Boolean approved = null;`. Viết một cách kiểm tra an toàn khi nghiệp vụ xem `null` như false, và một cách từ chối `null` khi trạng thái phê duyệt là bắt buộc.

**Bài 3.** Cho `Integer[] data = {2, null, 4};`. Viết hàm tính tổng, bỏ qua phần tử null một cách có chủ đích. Nêu kết quả mong đợi.

**Bài 4.** Vì sao `Integer a = null; int chosen = true ? a : 5;` gây NPE? Sửa thành biểu thức ba ngôi có guard.

**Bài 5.** Một API nhận `Integer quantity` nhưng không chấp nhận giá trị thiếu. Viết hàm kiểm tra ngay đầu vào, thông báo lỗi cụ thể, sau đó thực hiện tính toán chỉ với giá trị hợp lệ.

### Ghi nhớ

**`null` có thể tồn tại trong wrapper nhưng không thể biến thành một giá trị primitive.** NPE do unboxing thường xuất hiện ngay tại **gán, phép toán, so sánh, điều kiện hoặc biểu thức ba ngôi** cần primitive. Phát hiện bằng cách đọc kiểu dữ liệu và ngữ cảnh toán tử; phòng tránh bằng **hợp đồng null rõ ràng**, guard đúng thứ tự, `Objects.requireNonNull` cho dữ liệu bắt buộc hoặc default có chủ đích khi dữ liệu được phép thiếu.
