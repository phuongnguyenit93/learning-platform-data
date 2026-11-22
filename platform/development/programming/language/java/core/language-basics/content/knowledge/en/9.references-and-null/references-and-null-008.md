# Nhận diện `NullPointerException` và đặt kiểm tra tại điểm phù hợp

> **Java core — language-basics / Tham chiếu và null**  
> **Môi trường:** JDK 17+; một tệp Java độc lập, không có dependency ngoài.  
> **Mục tiêu:** Nhận biết các thao tác có thể phát sinh `NullPointerException` (NPE), lần theo vị trí lỗi, chọn giữa **kiểm tra `null` / giá trị mặc định / từ chối đầu vào**, và đặt kiểm tra **trước thao tác cần đối tượng** thay vì bắt lỗi tràn lan.

## 1. NPE là gì và xảy ra ở đâu?

`null` là giá trị đặc biệt của **kiểu tham chiếu**, nghĩa là biến hiện không tham chiếu tới đối tượng nào. `NullPointerException` thường xảy ra khi chương trình thực hiện thao tác **đòi hỏi có đối tượng** nhưng tham chiếu liên quan đang bằng `null`.

Ví dụ:

~~~java
String text = null;
// int n = text.length(); // Nếu chạy: NullPointerException.
~~~

Các tình huống phổ biến:

| Thao tác | Ví dụ nguy hiểm | Tham chiếu có thể `null` |
| --- | --- | --- |
| Gọi instance method | `name.trim()` | `name` |
| Đọc/ghi instance field | `user.status` | `user` |
| Đọc `length` hay phần tử mảng | `items.length`, `items[0]` | **Mảng `items`**, nếu chưa có object mảng |
| Sử dụng **phần tử** mảng tham chiếu | `items[0].length()` | `items[0]`, ngay cả khi mảng có tồn tại |
| Tự unbox wrapper | `int n = boxed;` | `boxed` kiểu `Integer` |
| Duyệt bằng enhanced `for` trên mảng | `for (String s : items) { ... }` | `items` nếu là mảng `null` |

**Phân biệt lỗi:** `items[10]` trên mảng tồn tại nhưng thiếu phần tử gây `ArrayIndexOutOfBoundsException`, **không** phải NPE. `String` rỗng `""` là object hợp lệ, khác với tham chiếu `null`.

## 2. Xác định chính xác điểm lỗi trước khi thêm kiểm tra

Khi gặp NPE, đọc **stack trace**:

1. Tìm dòng `java.lang.NullPointerException` và frame đầu tiên thuộc mã của bạn (ví dụ `Service.java:42`).
2. Mở đúng dòng được chỉ tới; liệt kê từng tham chiếu có thể `null` trên dòng đó, nhất là chuỗi gọi như `order.getCustomer().getName()`.
3. Lần ngược nguồn tạo/nhận giá trị: tham số method, kết quả API, trường chưa khởi tạo, phần tử mảng, giá trị trả về từ repository, v.v.
4. Kiểm tra **hợp đồng dữ liệu**: `null` có phải một trạng thái hợp lệ hay là đầu vào không hợp lệ?

Java 17 có thể in **thông điệp NPE chi tiết** tùy cấu hình JVM, nhưng đừng hardcode toàn bộ stack trace hoặc thông điệp tự động vào testcase: tên biến và lời giải thích có thể phụ thuộc môi trường/biên dịch. Dùng **line number + nguyên nhân + hợp đồng** để quyết định cách sửa.

Ví dụ một lời gọi nhiều bước:

~~~java
// Nếu customer có thể null, kiểm tra tại đây trước khi gọi method:
// Customer customer = order.getCustomer();
// if (customer == null) { /* xử lý nhánh thiếu customer */ }
// String name = customer.getName();
~~~

Đừng tự động thêm `try { ... } catch (NullPointerException e) { }` để bỏ qua lỗi: cách đó có thể che lỗi lập trình và làm dữ liệu sau đó sai khó phát hiện.

## 3. Chọn cách xử lý theo ý nghĩa `null`

Có **ba chiến lược chính**, không thay thế lẫn nhau:

| Tình huống nghiệp vụ | Vị trí kiểm tra phù hợp | Cách giải quyết |
| --- | --- | --- |
| `null` **hợp lệ**, cần mặc định | Trước khi đọc dữ liệu tùy chọn | `if (x == null) return fallback;` |
| `null` **không hợp lệ** | Ngay ranh giới nhận dữ liệu, constructor hoặc public API | `Objects.requireNonNull(x, "x required")` |
| `null` hợp lệ nhưng chỉ được thao tác khi có object | Ngay trước thao tác dereference | `x != null && x.isReady()` |

Ví dụ gác điều kiện an toàn:

~~~java
String input = null;
boolean hasText = input != null && !input.isBlank();
System.out.println(hasText); // false, không gọi input.isBlank().
~~~

`&&` thực hiện **short-circuit**: khi vế trái false, Java không đánh giá vế phải. **Thứ tự là quan trọng**; đảo thành `!input.isBlank() && input != null` sẽ gây NPE nếu `input` là null. Toán tử boolean `&` **không short-circuit**, nên không phải cách thay thế tương đương khi cần bảo vệ việc gọi method.

Đối với so sánh với literal:

~~~java
String command = null;
System.out.println("START".equals(command)); // false, an toàn với null.
~~~

Có thể dùng `Objects.equals(a, b)` khi **cả hai** biến có thể `null`. Cần biết `Objects.equals(null, null)` cho **true**; nếu dữ liệu cùng vắng mặt không được xem là bằng nhau, phải đặt quy tắc riêng.

## 4. Java 17+ runnable: các tình huống NPE và cách xử lý

Tạo file **NullCheckDemo.java**:

~~~java
import java.util.Objects;

public final class NullCheckDemo {
    private static final class Account {
        private final String label;

        Account(String label) {
            this.label = Objects.requireNonNull(label, "label required");
        }

        String label() {
            return label;
        }
    }

    private static String displayLabel(Account account) {
        if (account == null) {
            return "Guest"; // Null là một trạng thái hợp lệ của API này.
        }
        return account.label();
    }

    private static int requiredLength(Account account) {
        Objects.requireNonNull(account, "account required");
        return account.label().length();
    }

    public static void main(String[] args) {
        Account valid = new Account("Linh");
        Account missing = null;

        System.out.println("valid=" + displayLabel(valid));
        System.out.println("fallback=" + displayLabel(missing));
        System.out.println("guard="
                + (missing != null && missing.label().length() > 0));
        System.out.println("literalEquals=" + "Linh".equals(null));
        System.out.println("bothNullEquals=" + Objects.equals(null, null));
        System.out.println("requiredLength=" + requiredLength(valid));

        try {
            requiredLength(missing);
        } catch (NullPointerException e) {
            System.out.println("requiredError=" + e.getMessage());
        }

        String receiver = null;
        try {
            receiver.length();
        } catch (NullPointerException e) {
            System.out.println("receiverNpe=true");
        }

        String[] words = {null, "ok"};
        try {
            System.out.println(words[0].length());
        } catch (NullPointerException e) {
            System.out.println("elementNpe=true");
        }

        Integer boxed = null;
        try {
            int number = boxed;
            System.out.println("number=" + number);
        } catch (NullPointerException e) {
            System.out.println("unboxingNpe=true");
        }

        try {
            new Account(null);
        } catch (NullPointerException e) {
            System.out.println("constructorError=" + e.getMessage());
        }

        System.out.println("safeLength="
                + (words[1] != null ? words[1].length() : 0));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file bằng Bash, PowerShell hoặc Command Prompt:

~~~bash
javac -encoding UTF-8 NullCheckDemo.java
java NullCheckDemo
~~~

**Expected output chính xác:**

~~~text
valid=Linh
fallback=Guest
guard=false
literalEquals=false
bothNullEquals=true
requiredLength=4
requiredError=account required
receiverNpe=true
elementNpe=true
unboxingNpe=true
constructorError=label required
safeLength=2
~~~

**Giải thích:**

- `displayLabel(null)` trả `"Guest"` vì API **cho phép** tài khoản vắng mặt; `requiredLength(null)` cố ý từ chối bằng thông báo `"account required"`.
- `missing != null && ...` dừng trước thao tác đọc `label()`. Literal `"Linh".equals(null)` trả false. `Objects.equals(null, null)` trả true theo hợp đồng của nó.
- `receiver.length()` gây NPE vì receiver null. Mảng `words` **không null**, nhưng phần tử `words[0]` null nên gọi `length()` vẫn gây NPE.
- Biến wrapper `Integer boxed` có thể null; tự chuyển sang `int` (*auto-unboxing*) gây NPE.
- Constructor `Account` kiểm tra giá trị `label` **ngay tại nơi thiết lập bất biến của object**, khiến một `Account` được tạo thành công luôn có `label` không null.
- Các khối `catch` dùng để minh họa một số lỗi một cách có kiểm soát; trong ứng dụng thật, hãy **sửa hợp đồng dữ liệu/kiểm tra đúng chỗ**, đừng nuốt NPE rồi tiếp tục như chưa có vấn đề.

## 5. Kiểm tra `null` ở đâu cho đúng?

**Nguyên tắc:** Đặt kiểm tra tại nơi **có đủ ngữ cảnh để quyết định cách xử lý**, và trước khi truy cập object. Không phải biến nào cũng cần lặp lại `if (x == null)` ở mọi dòng.

- **Ranh giới public API hoặc constructor:** Nếu giá trị bắt buộc, dùng `Objects.requireNonNull` để phát hiện sai đầu vào **sớm**, ghi rõ tên/thông điệp. Sau đó code nội bộ có thể dựa trên bất biến đã thiết lập.
- **Ranh giới nhập liệu hoặc nguồn có thể thiếu:** Nếu `null` là trạng thái hợp lệ, quyết định trả default, bỏ qua, yêu cầu người dùng bổ sung hoặc báo lỗi nghiệp vụ trước thao tác.
- **Trước chuỗi truy cập nhiều cấp:** Chia thành biến trung gian rồi kiểm tra đúng phần nào có thể null, thay vì gọi nối tiếp và chỉ bắt exception.
- **Từng phần tử collection/mảng:** Kiểm tra cả **container** và **element** nếu nguồn dữ liệu có thể chứa null.
- **Wrapper số:** Trước phép tính cần unbox `Integer`/`Long`/`Boolean`, xác nhận chúng không null hoặc có quy tắc default rõ ràng.

`Objects.requireNonNull(x, "...")` vẫn tạo ra **NPE**, nhưng đó là kiểm tra **chủ động ở ranh giới hợp đồng**, khác với lỗi vô tình dereference null sâu bên trong. Nếu public API cần loại exception khác (ví dụ `IllegalArgumentException` cho giá trị nhập không hợp lệ), hãy thiết kế có chủ đích và thống nhất thay vì đổi tùy tiện.

## 6. Những sai lầm thường gặp

| Sai lầm | Hậu quả / cách sửa |
| --- | --- |
| `name.equals("OK")` khi `name` có thể null | Có thể NPE; dùng `"OK".equals(name)` hoặc kiểm tra trước |
| `input.isBlank() && input != null` | Đảo thứ tự: gọi method trước khi guard |
| `input != null & input.isBlank()` | `&` đánh giá cả hai vế; dùng `&&` |
| Chỉ kiểm tra `array != null` rồi gọi `array[0].length()` | Phần tử `array[0]` vẫn có thể null |
| Tự unbox `Integer count = null` | NPE; định nghĩa fallback hoặc yêu cầu count khác null |
| Bắt và bỏ qua mọi `NullPointerException` | Che lỗi hợp đồng, kết quả về sau có thể sai |
| Mọi giá trị thiếu đều thay bằng `""` hoặc `0` | Có thể sai nghiệp vụ; chỉ dùng default nếu được định nghĩa |
| Gán `x = null` rồi tưởng object đã bị xóa | Chỉ biến x đổi tham chiếu; alias khác có thể còn trỏ object |

**Lưu ý:** `Optional` có thể thể hiện kết quả tùy chọn khi API phù hợp, nhưng không phải công cụ để bọc mọi field và không thay thế việc hiểu liệu `null` là dữ liệu hợp lệ hay lỗi. Tránh gọi `Optional.get()` mà không kiểm tra vì lại sinh lỗi khác.

## 7. Bài tập ngắn

**Bài 1.** Cho `String value = null;`. Dự đoán hành vi của `value.length()`, `"OK".equals(value)` và `value != null && value.length() > 0`. Chỉ ra lệnh nào gây NPE, lệnh nào an toàn.

**Bài 2.** Cho `String[] list = new String[2];`. Tại sao `list.length` hợp lệ nhưng `list[0].length()` gây NPE? Đặt guard ở đâu?

**Bài 3.** Viết hàm nhận `String requiredCode` bắt buộc khác null. Đặt `Objects.requireNonNull(requiredCode, "code required")` ngay đầu hàm, rồi dùng biến an toàn ở phần còn lại.

**Bài 4.** Một API trả `null` khi không tìm thấy tài khoản. Hãy chọn giữa (a) trả nhãn `"Guest"`, (b) thông báo “không tìm thấy”, (c) phát hiện lỗi đầu vào — và giải thích sự khác nhau về hợp đồng.

**Bài 5.** `Integer quantity = null; int total = quantity * 2;` gây lỗi vì sao? Viết hai cách xử lý có chủ đích: bắt buộc quantity hoặc dùng giá trị mặc định đã được nghiệp vụ đồng ý.

### Ghi nhớ

**NPE thường báo rằng code đã cố sử dụng một tham chiếu `null` như object.** Hãy đọc đúng stack trace để tìm thao tác lỗi; quyết định `null` có hợp lệ không, rồi **đặt kiểm tra tại ranh giới dữ liệu hoặc ngay trước dereference**. Dùng `&&` để guard, `Objects.requireNonNull` cho giá trị bắt buộc và so sánh an toàn khi cần. Tránh che giấu NPE bằng `catch` rỗng hay rải default không có ý nghĩa.
