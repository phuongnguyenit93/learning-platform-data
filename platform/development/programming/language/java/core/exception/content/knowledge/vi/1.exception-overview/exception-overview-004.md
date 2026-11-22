# Các thành phần trong luồng ngoại lệ Java: nơi phát sinh, nơi gọi và nơi xử lý

Khi một thao tác trong Java thất bại, hiểu được **ngoại lệ bắt đầu ở đâu, đi qua những phương thức nào và được xử lý ở đâu** giúp bạn đọc stack trace, chọn chỗ đặt `try-catch` và thiết kế trách nhiệm giữa các lớp. Ba vai trò cốt lõi là:

1. **Nơi phát sinh (throw site / origin):** câu lệnh hoặc thao tác tại đó ngoại lệ được ném vào luồng thực thi.
2. **Nơi gọi (call site / caller):** câu lệnh đang gọi phương thức xảy ra lỗi; có thể là một hoặc nhiều tầng gọi lồng nhau.
3. **Nơi xử lý (handler):** khối `catch` phù hợp gần nhất theo thứ tự tìm kiếm của JVM trên chuỗi lời gọi đang hoạt động; khối này quyết định phục hồi, chuyển đổi lỗi hoặc kết thúc yêu cầu.

Điều quan trọng: **nơi phát sinh và nơi xử lý không nhất thiết nằm trong cùng một phương thức**. Một phương thức có thể chỉ chuyển ngoại lệ lên tầng trên mà không có `catch`.

## 1. Ba vai trò nhìn qua sơ đồ

Xét lời gọi `main() → processRequest() → parseQuantity()`. Khi `parseQuantity()` gặp chuỗi không thể chuyển thành số, ngoại lệ có thể lan ngược qua những lời gọi chưa kết thúc:

```text
main()                     ← nơi xử lý: catch trong main
  └── processRequest()     ← nơi gọi parseQuantity; có thể chuyển tiếp
        └── parseQuantity()← nơi phát sinh ngoại lệ
              throw
              ↓
        không có catch phù hợp
              ↓
  ngoại lệ truyền ngược lên main()
              ↓
      catch phù hợp → xử lý
```

Đây là một chuỗi lời gọi **động tại thời điểm lỗi xảy ra**, không phải quan hệ kế thừa hay đơn thuần là thứ tự các phương thức được khai báo trong tệp. Hai phương thức cùng gọi `parseQuantity()` có thể đưa ngoại lệ đến hai handler khác nhau.

| Thành phần | Việc đang làm | Ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- | --- |
| Nơi phát sinh | Phát hiện điều kiện lỗi và ném ngoại lệ | `throw new IllegalArgumentException(...)` | Vì sao thao tác không thể tiếp tục? |
| Nơi gọi | Gọi hàm có khả năng ném lỗi; nhận kết quả hoặc bị gián đoạn | `int n = parseQuantity(text);` | Có nên xử lý ở đây hay để cấp trên xử lý? |
| Nơi xử lý | Bắt kiểu ngoại lệ tương thích rồi đưa ra hành động | `catch (IllegalArgumentException ex) { ... }` | Có thể sửa đầu vào, thử lại, phản hồi người dùng hay chuyển lỗi? |

Một phương thức có thể **đồng thời đảm nhiệm nhiều vai trò**: nó gọi phương thức khác, bắt ngoại lệ vừa nhận và ném một ngoại lệ mới để bổ sung ngữ cảnh. Phân chia ba vai trò nhằm đọc luồng thực thi cho rõ, không buộc chương trình luôn có ba lớp riêng biệt.

## 2. Nơi phát sinh: ngoại lệ được tạo và ném như thế nào?

### Chủ động ném bằng `throw`

Khi phát hiện điều kiện vi phạm hợp đồng, mã có thể chủ động tạo và ném một đối tượng ngoại lệ:

```java
static int requirePositive(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException("Số phải lớn hơn 0");
    }
    return value;
}
```

Đây là **đoạn phương thức minh họa**, cần đặt trong một lớp Java để biên dịch độc lập. Khi `value <= 0`, câu lệnh `throw` làm đường thực thi bình thường dừng tại đó; `return value` không chạy. Kiểu `IllegalArgumentException` cho biết đối số không thỏa tiền điều kiện, còn thông điệp nêu nguyên nhân cụ thể.

Phân biệt hai thao tác:

- `new IllegalArgumentException(...)` **tạo** đối tượng ngoại lệ.
- `throw exception` **ném** đối tượng đó vào cơ chế xử lý ngoại lệ.

Hai thao tác thường nằm cùng một dòng, nhưng về ý nghĩa không giống nhau. Khi ném lại một đối tượng đã bắt bằng `throw ex;`, ta không tạo ngoại lệ mới.

### Ngoại lệ do thao tác/API phát sinh

Không phải ngoại lệ nào cũng xuất hiện sau một câu lệnh `throw` do bạn trực tiếp viết:

- `Integer.parseInt("abc")` ném `NumberFormatException` vì chuỗi không biểu diễn một số nguyên hợp lệ.
- Phép chia số nguyên `10 / 0` ném `ArithmeticException`; phép chia số thực có quy tắc IEEE 754 khác, không nên suy diễn y hệt.
- Truy cập phần tử mảng ở chỉ số ngoài phạm vi ném `ArrayIndexOutOfBoundsException`.
- Gọi phương thức trên tham chiếu `null` có thể ném `NullPointerException`.
- Đọc một tệp có thể ném `IOException` theo hợp đồng API.

Với các lỗi được phát hiện bởi JVM hoặc mã thư viện, nơi phát sinh là **điểm thao tác thực sự ném ngoại lệ**. Nơi gọi API là chỗ người viết ứng dụng có thể quan sát ngoại lệ được truyền ra; nó không nhất thiết là nơi sâu nhất đã phát hiện lỗi trong thư viện.

### Khi nào coi một tình huống là lỗi?

Không tìm thấy phần tử trong một phép tìm kiếm được thiết kế cho phép “không có kết quả” có thể biểu diễn bằng `Optional.empty()` hoặc danh sách rỗng. Ngược lại, phương thức có hợp đồng “bắt buộc có cấu hình” nhưng không thể đọc tệp sẽ cần báo lỗi rõ. Trước khi `throw`, hãy xác định **đó thực sự là vi phạm hợp đồng hay chỉ là một kết quả dự kiến**.

## 3. Nơi gọi: điểm chuyển giao kết quả hoặc ngoại lệ

Ví dụ:

```java
int quantity = parseQuantity(input);
System.out.println("Số lượng: " + quantity);
```

Câu lệnh đầu là **call site**. Nếu `parseQuantity(input)` trả về bình thường, biến `quantity` nhận giá trị và câu in chạy. Nếu lời gọi ném ngoại lệ chưa được xử lý ngay bên trong phương thức đó:

1. Phép gọi không hoàn tất bình thường, nên phép gán cho `quantity` không hoàn tất.
2. Dòng `println` phía sau không chạy trên đường thực thi đó.
3. JVM tìm `catch` tương thích bao quanh điểm gọi; nếu không có, tiếp tục tìm ở phương thức đã gọi phương thức hiện tại.
4. Quá trình tiếp tục qua các lời gọi đang hoạt động cho đến khi tìm được handler, hoặc ngoại lệ trở thành *uncaught*.

**Call site không cần chứa `try-catch`**. Tùy tầng ứng dụng, để ngoại lệ đi lên thường hợp lý hơn là bắt chỉ để in một dòng rồi bỏ qua.

### `throws` và `throw` không thay thế nhau

```java
static String readConfig() throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.txt"));
}
```

Đây là đoạn phương thức minh họa; hành vi cụ thể phụ thuộc sự tồn tại/quyền truy cập tệp.

- `throws IOException` trên khai báo phương thức nói rằng lời gọi **có thể để ngoại lệ checked này đi ra ngoài**. Bản thân khai báo không tạo hoặc ném ngoại lệ.
- `throw new IOException(...)` bên trong thân hàm là một câu lệnh **ném ngoại lệ thực sự**.
- Người gọi `readConfig()` phải bắt `IOException` hoặc tiếp tục khai báo `throws IOException` (trừ các trường hợp ngôn ngữ cho phép đặc biệt). Không có yêu cầu tương tự khi lan truyền đa số ngoại lệ unchecked như `IllegalArgumentException`.

Cách đọc chữ ký: `throws` mô tả một phần hợp đồng kiểm tra tại thời điểm biên dịch; `throw` ảnh hưởng luồng thực thi tại thời điểm chạy.

## 4. Nơi xử lý: `try-catch` phù hợp gần nhất

Cú pháp điển hình:

```java
try {
    // Gọi đoạn mã có thể phát sinh ngoại lệ.
} catch (NumberFormatException ex) {
    // Xử lý lỗi chuyển đổi số.
} catch (IllegalArgumentException ex) {
    // Xử lý lỗi tham số khác.
} finally {
    // Dọn dẹp hoặc ghi nhận kết thúc thao tác.
}
```

Đoạn mã này chỉ minh họa cấu trúc, không phải tệp chạy độc lập.

- `try` xác định đoạn mã được theo dõi để bắt ngoại lệ.
- `catch (Type ex)` được chọn khi loại đối tượng ngoại lệ **cùng loại hoặc là lớp con** của `Type`. Một ngoại lệ được xử lý bởi **khối `catch` khớp đầu tiên theo thứ tự mã nguồn tại vùng `try` đang được xét**.
- Khi có nhiều `catch`, hãy đặt loại **cụ thể trước loại tổng quát**. `NumberFormatException` kế thừa `IllegalArgumentException`; đổi thứ tự hai khối trong ví dụ sẽ khiến khối riêng trở thành không thể tới được và trình biên dịch báo lỗi.
- `finally` thường chạy khi rời `try`/`catch` dù thành công, có lỗi hay `return`. Nó dùng cho các việc kết thúc cần thiết; với tài nguyên `AutoCloseable` nên ưu tiên `try-with-resources`.

Nói “handler gần nhất” là nói tới **vùng xử lý còn hoạt động trên đường gọi hiện tại**, không phải khối `catch` xuất hiện gần nhất về số dòng trong tệp. JVM trước hết xét các handler có hiệu lực tại điểm đang ném, rồi khi không phù hợp mới truyền ra người gọi.

Nếu `catch` xử lý xong và **không ném lại**, ngoại lệ đó dừng lan truyền; thực thi tiếp tục sau cấu trúc `try-catch-finally` (nếu luồng còn được tiếp tục). Nếu `catch` ném lại hoặc ném ngoại lệ khác, quá trình tìm handler mới lại diễn ra.

## 5. Ví dụ Java 17+ hoàn chỉnh: quan sát từng tầng A → B → C

Lưu mã dưới tên **`ExceptionFlowDemo.java`**:

```java
public class ExceptionFlowDemo {

    // C: nơi phát sinh; có thể ném trực tiếp hoặc qua API parseInt.
    static int parseQuantity(String input) {
        System.out.println("C: bắt đầu kiểm tra");
        int number = Integer.parseInt(input);

        if (number <= 0) {
            throw new IllegalArgumentException("số lượng phải > 0");
        }

        System.out.println("C: trả kết quả");
        return number;
    }

    // B: nơi gọi C, không tự bắt hoặc thay đổi ngoại lệ.
    static int prepareOrder(String input) {
        System.out.println("B: gọi C");
        int quantity = parseQuantity(input);
        System.out.println("B: đã nhận số lượng");
        return quantity;
    }

    // A: nơi gọi B đồng thời là nơi xử lý lỗi.
    static void handleRequest(String input) {
        System.out.println("A: nhận yêu cầu " + input);
        try {
            int quantity = prepareOrder(input);
            System.out.println("A: tạo đơn với " + quantity + " sản phẩm");
        } catch (NumberFormatException ex) {
            System.out.println("A: lỗi định dạng số");
        } catch (IllegalArgumentException ex) {
            System.out.println("A: " + ex.getMessage());
        } finally {
            System.out.println("A: kết thúc yêu cầu");
        }
    }

    public static void main(String[] args) {
        handleRequest("3");
        System.out.println("---");
        handleRequest("0");
        System.out.println("---");
        handleRequest("abc");
    }
}
```

Lệnh chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 ExceptionFlowDemo.java
java ExceptionFlowDemo
```

**Stdout chính xác:**

```text
A: nhận yêu cầu 3
B: gọi C
C: bắt đầu kiểm tra
C: trả kết quả
B: đã nhận số lượng
A: tạo đơn với 3 sản phẩm
A: kết thúc yêu cầu
---
A: nhận yêu cầu 0
B: gọi C
C: bắt đầu kiểm tra
A: số lượng phải > 0
A: kết thúc yêu cầu
---
A: nhận yêu cầu abc
B: gọi C
C: bắt đầu kiểm tra
A: lỗi định dạng số
A: kết thúc yêu cầu
```

### Phân tích ba đường chạy

**Yêu cầu `"3"` — thành công:** `main` gọi A; A gọi B; B gọi C; C trả `3`. Luồng kết thúc bình thường theo thứ tự ngược C → B → A. Vì không có ngoại lệ, không `catch` nào chạy; `finally` của A vẫn chạy.

**Yêu cầu `"0"` — C chủ động ném:** `Integer.parseInt("0")` chuyển đổi thành công, nhưng `number <= 0` vi phạm quy tắc nghiệp vụ. `throw new IllegalArgumentException(...)` ở C làm dòng `"C: trả kết quả"` bị bỏ qua. B cũng không in `"B: đã nhận số lượng"`, vì lời gọi C không trả kết quả. A có `catch (IllegalArgumentException)` nên nhận lỗi, in thông điệp, rồi chạy `finally`.

**Yêu cầu `"abc"` — API ném lỗi:** ngoại lệ `NumberFormatException` phát sinh trong `Integer.parseInt` được gọi tại C, trước khi chạy câu `if`. B không có handler nên nó lan về A. Vì `NumberFormatException` phù hợp với khối `catch` cụ thể đầu tiên, A in `"A: lỗi định dạng số"`. Chương trình không phát sinh stack trace trên stderr vì ngoại lệ đã được bắt và không bị ném lại.

Từ ví dụ thấy rằng **nơi phát sinh nắm nguyên nhân kỹ thuật/nghiệp vụ**, **nơi gọi quyết định có can thiệp ở tầng hiện tại không**, và **nơi xử lý quyết định hành động đối với yêu cầu đang thực hiện**. Các vai trò không đòi hỏi mỗi tầng đều bắt cùng một lỗi.

## 6. Cơ chế lan truyền và tháo ngăn xếp lời gọi

Khi một ngoại lệ không được xử lý trong phương thức hiện tại, JVM rời khỏi phương thức đó theo đường hoàn tất bất thường và tìm handler phù hợp ở phương thức gọi nó. Đây là **exception propagation**; quá trình rời các khung gọi còn hoạt động thường được gọi là **stack unwinding**.

Giả sử:

```text
main()  →  A()  →  B()  →  C()
                         |
                         throw X
             ← X ← X ← X |
```

Nếu C và B không có `catch` phù hợp, nhưng A có, thì A xử lý X. Sau đó A có thể tiếp tục từ **sau khối `try-catch`**, chứ không “quay lại đúng câu lệnh đang dở” ở B hoặc C. Các câu lệnh phía sau lời gọi thất bại trong B/C đã bị bỏ qua.

### `finally` và dọn dẹp trong lúc lan truyền

Các khối `finally` trên đường rời ngăn xếp sẽ được chạy theo quy tắc Java. Nếu B có `try-finally` bao quanh lời gọi C, khối `finally` của B sẽ chạy trước khi ngoại lệ đi lên handler của A.

```java
static void middle() {
    try {
        fail();
    } finally {
        System.out.println("B: dọn dẹp");
    }
}

static void fail() {
    throw new IllegalStateException("thất bại tại C");
}
```

Đây là các phương thức minh họa, không phải chương trình độc lập. Nếu người gọi A bắt `IllegalStateException`, thứ tự là: lỗi tại C → in dòng dọn dẹp của B → handler tại A. `finally` **không mặc nhiên nuốt lỗi**; ngoại lệ tiếp tục lan truyền sau dọn dẹp. Tuy nhiên, nếu chính `finally` ném một ngoại lệ mới hoặc dùng `return`, nó có thể làm thay đổi/khuất nguyên nhân ban đầu; vì vậy tránh thay thế luồng lỗi trong `finally`.

Không thể bảo đảm mọi `finally` chạy trong các tình huống kết thúc JVM bất thường (ví dụ `Runtime.halt`, tiến trình bị buộc dừng). Với đối tượng tài nguyên, `try-with-resources` thường an toàn và dễ đọc hơn.

### Nếu hoàn toàn không có handler?

Ngoại lệ *uncaught* thoát đến điểm trên cùng của một thread được xử lý bởi cơ chế uncaught-exception handler của thread (thường in tên ngoại lệ và stack trace ra stderr trong cấu hình mặc định), và thread đó kết thúc. Một lỗi uncaught trong một thread **không mặc nhiên đồng nghĩa toàn bộ tiến trình Java dừng ngay**: các thread khác vẫn có thể hoạt động. Vì vậy đừng dựa vào uncaught exception như cách trả lỗi nghiệp vụ cho người dùng.

## 7. Checked exception: nơi gọi phải chọn bắt hay khai báo

Một số ngoại lệ, ví dụ `IOException`, là **checked exceptions**. Khi gọi phương thức có thể ném chúng, trình biên dịch yêu cầu người gọi xử lý hoặc tiếp tục khai báo `throws`. Điều đó giúp người viết API thể hiện sớm tình huống cần xem xét, nhưng không có nghĩa mọi `catch` đều đưa ra cách phục hồi phù hợp.

Chương trình độc lập sau chứng minh tầng giữa chỉ chuyển tiếp lỗi. Lưu thành **`CheckedExceptionFlowDemo.java`**:

```java
import java.io.IOException;

public class CheckedExceptionFlowDemo {

    // C: cố tình mô phỏng sự cố I/O để ví dụ không phụ thuộc hệ thống tệp.
    static String readConfig() throws IOException {
        System.out.println("C: đọc cấu hình");
        throw new IOException("không đọc được cấu hình");
    }

    // B: caller của C; không bắt, nhưng phải khai báo throws IOException.
    static String prepareConfig() throws IOException {
        System.out.println("B: gọi C");
        return readConfig();
    }

    // A: caller của B và handler của IOException.
    public static void main(String[] args) {
        try {
            System.out.println("A: gọi B");
            String config = prepareConfig();
            System.out.println("A: đã đọc " + config);
        } catch (IOException ex) {
            System.out.println("A: xử lý " + ex.getMessage());
        }
        System.out.println("A: tiếp tục");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CheckedExceptionFlowDemo.java
java CheckedExceptionFlowDemo
```

Stdout:

```text
A: gọi B
B: gọi C
C: đọc cấu hình
A: xử lý không đọc được cấu hình
A: tiếp tục
```

Lưu ý:

- C **ném thực tế** bằng `throw new IOException`.
- B **gọi C và lan truyền** bằng khai báo `throws IOException`, không tạo thêm lỗi; lệnh `return readConfig()` không hoàn thành vì C đã ném.
- A **bắt và xử lý** ở một ranh giới có thể quyết định phản hồi, sau đó chương trình tiếp tục.
- Nếu bỏ `throws IOException` ở B nhưng vẫn giữ lời gọi không có `try-catch`, mã sẽ không biên dịch. Ngược lại, các `RuntimeException` không bị bắt buộc khai báo theo cách này.

## 8. Nếu tầng giữa cần bổ sung ngữ cảnh thì làm gì?

Đôi khi B biết thêm một thông tin hữu ích mà C không có: tên thao tác, mã yêu cầu hay loại dữ liệu đang xử lý. B có thể bắt ngoại lệ từ C và ném **ngoại lệ khác kèm nguyên nhân gốc**:

```java
static int parseAmount(String raw) {
    try {
        return Integer.parseInt(raw);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
                "Không đọc được số lượng đơn hàng từ chuỗi: " + raw,
                cause);
    }
}
```

Đây là phương thức minh họa, cần đặt trong lớp Java. Trong trường hợp này:

1. `Integer.parseInt` là điểm ném `NumberFormatException` ban đầu.
2. `parseAmount` vừa là caller vừa có handler của lỗi gốc.
3. `throw new IllegalArgumentException(..., cause)` tạo **một ngoại lệ mới** để caller bên ngoài xử lý; `cause` giữ liên kết tới sự cố gốc. Handler bên ngoài có thể gọi `ex.getCause()` để chẩn đoán.

Chỉ nên **wrap** khi ngữ cảnh/hợp đồng ở tầng mới thực sự cần một loại lỗi khác. Nếu không, để ngoại lệ gốc lan lên giúp code ngắn và tránh làm rối nguyên nhân. Tránh tự động bắt rồi ném `new RuntimeException("Lỗi")` mà không giữ `cause`.

Về stack trace, một đối tượng ngoại lệ thông thường có stack trace được ghi khi khởi tạo (hoặc khi gọi `fillInStackTrace()`), vì vậy dòng đầu thường phản ánh nơi đối tượng được tạo, trong khi ngoại lệ đã bị ném lại bằng `throw ex` có thể vẫn giữ trace gốc. Trace của ngoại lệ bọc mới phản ánh điểm tạo wrapper; chuỗi `Caused by` chỉ ra nguyên nhân phía dưới. Không nên suy luận rằng dòng đầu stack trace luôn là mọi địa điểm mà đối tượng từng được ném.

## 9. Chọn nơi xử lý theo trách nhiệm của tầng

Một hệ thống Java thường gồm nhiều tầng. Ví dụ: controller nhận yêu cầu, service thực hiện quy tắc, repository truy cập dữ liệu. Đây là những **vai trò kiến trúc minh họa**, không phải ràng buộc rằng Java bắt buộc dùng framework hay đúng ba tầng.

| Tầng / điểm gọi | Thông thường nên làm | Ví dụ |
| --- | --- | --- |
| Đoạn mã phát hiện lỗi | Phát hiện và ném kiểu ngoại lệ diễn đạt đúng thất bại | Tham số sai quy tắc → `IllegalArgumentException` |
| Tầng giữa | Chỉ xử lý nếu có cách phục hồi, chuyển đổi có ngữ cảnh hoặc cần giải phóng tài nguyên | Retry kết nối theo chính sách, bọc nguyên nhân để giữ bối cảnh |
| Ranh giới giao tiếp | Chuyển lỗi thành phản hồi phù hợp với caller/người dùng; ghi log nơi được phân công | Giao diện báo nhập sai; API chuyển lỗi thành mã HTTP thích hợp |
| Biên của thread hoặc tác vụ nền | Đưa lỗi vào cơ chế báo cáo tác vụ, giám sát hoặc chính sách retry | `Future.get()` có thể báo `ExecutionException` chứa nguyên nhân của lỗi trong tác vụ |

“Bắt càng sớm càng tốt” không phải quy tắc đúng. Bắt ngay tại nơi phát sinh rồi trả `null` có thể khiến tầng ngoài tưởng rằng kết quả hợp lệ nhưng trống. Ngược lại, cứ để ngoại lệ đi lên vô hạn mà không có ranh giới xử lý cũng khiến người gọi không nhận được phản hồi có ý nghĩa.

Một `catch` được coi là **xử lý** chỉ khi nó có hành động có chủ đích: khôi phục trạng thái, yêu cầu nhập lại, chuyển thành thông báo phù hợp, quyết định thất bại tác vụ, hoặc chuyển lỗi sang hợp đồng tầng ngoài. `catch` rỗng thường chỉ che giấu lỗi.

## 10. Các lỗi tư duy và lỗi lập trình hay gặp

### Nhầm nơi tạo lỗi với nơi phát hiện hoặc nơi xử lý

Khi stack trace có nhiều phương thức, một khung trên cùng có thể nằm trong thư viện Java vì thư viện đã phát hiện dữ liệu không hợp lệ; dòng gọi trong mã ứng dụng giúp xác định **bạn đã cung cấp đầu vào nào**. Đừng vội quy trách nhiệm cho phương thức đang có `catch`: nó có thể chỉ là nơi nhận được sự cố.

### Nghĩ `throws` tự động bắt hoặc ném ngoại lệ

Khai báo `throws IOException` chỉ cho phép/biểu đạt sự lan truyền checked exception, không tạo `catch` và không đảm bảo phương thức luôn ném ngoại lệ. Chỉ khi code thực sự ném ngoại lệ thì đường đi bất thường mới xảy ra.

### Xếp `catch` lớp cha trước lớp con

`catch (Exception ex)` đứng trước `catch (NumberFormatException ex)` làm khối `catch` phía sau không thể tới được trong cùng cấu trúc `try`. Java sẽ báo lỗi biên dịch. Đặt lỗi cụ thể trước, lỗi tổng quát sau nếu thật sự cần.

### Bắt mọi lỗi rồi tiếp tục như thành công

```java
try {
    process();
} catch (Exception ex) {
    // Bỏ qua tất cả.
}
sendSuccess();
```

Đây là đoạn minh họa, không phải chương trình độc lập. Nếu `process()` thất bại mà chương trình vẫn gọi `sendSuccess()`, caller bị đánh lừa. Chỉ tiếp tục thành công khi có cách **phục hồi được xác định rõ và đã thành công**.

### Đặt `catch` sai phạm vi

Nếu `try` chỉ bao quanh câu lệnh không có khả năng ném lỗi cần bắt, còn lời gọi có rủi ro lại nằm ngoài `try`, handler đó không bảo vệ được lời gọi. Hãy đặt `try` bao quanh đúng hoạt động đang cần xử lý và giữ vùng này đủ nhỏ để xác định chính xác nguồn lỗi.

### Quên thao tác dọn dẹp trong lúc lan truyền

Nếu luồng hoặc kết nối đã được mở trước khi một lời gọi ném ngoại lệ, các câu lệnh `close()` thông thường nằm sau lời gọi có thể bị bỏ qua. Dùng `try-with-resources` cho đối tượng `AutoCloseable` để tự động đóng khi thoát khối; cơ chế này còn có quy tắc bảo lưu **suppressed exceptions** nếu vừa lỗi khi xử lý vừa lỗi khi đóng.

### Ném ngoại lệ mới nhưng mất nguyên nhân

`catch (IOException ex) { throw new IllegalStateException("Không đọc được"); }` che khuất đối tượng `IOException` khỏi quan hệ `cause`. Thay bằng `new IllegalStateException("Không đọc được", ex)` nếu chính sách tầng hiện tại cần chuyển sang unchecked exception.

### Hiểu sai sau khi `catch` xong

Xử lý xong lỗi trong A **không có nghĩa** JVM quay về chạy tiếp dòng ngay sau điểm `throw` ở C. Các lời gọi thất bại đã kết thúc bất thường. Nếu muốn thử lại, mã xử lý phải **chủ động gọi lại thao tác** sau khi đã đảm bảo điều kiện retry và giới hạn số lần phù hợp.

## 11. Checklist đọc và thiết kế luồng ngoại lệ

Khi gặp một lỗi trong mã Java, lần lượt xác định:

1. **Lỗi bắt đầu ở đâu?** Tìm `throw` trực tiếp hoặc lời gọi Java/API phát sinh ngoại lệ. Kiểm tra kiểu, thông điệp, nguyên nhân gốc và đầu vào liên quan.
2. **Ai đang gọi ai?** Xem ngăn xếp lời gọi/stack trace và những phương thức đã gọi nhau. Tại mỗi caller, câu lệnh sau lời gọi thất bại sẽ bị bỏ qua, trừ khi một cấu trúc xử lý trong cùng phương thức đưa luồng quay về vị trí hợp lệ.
3. **Handler hiệu lực nằm ở đâu?** Xét `try` bao quanh điểm ném và các khung caller, rồi tìm `catch` có kiểu tương thích. Kiểm tra thứ tự khối `catch`, các `finally` và tác động của `try-with-resources`.
4. **Handler có thực sự giải quyết được lỗi?** Nếu không, có thể để ngoại lệ lan lên hoặc chuyển lỗi có chủ đích và giữ `cause`. Không biến thất bại thành dữ liệu trông có vẻ hợp lệ.
5. **Hợp đồng được phản ánh đúng chưa?** Với checked exception, khai báo `throws`/`catch` cho đúng; với lỗi nghiệp vụ, chọn kiểu ngoại lệ hoặc kiểu kết quả tường minh phù hợp. Tại ranh giới ứng dụng, chuyển lỗi thành phản hồi hữu ích.

**Ghi nhớ chuỗi vai trò:** nơi phát sinh cho biết **điều gì đã hỏng**, nơi gọi xác định **đường ngoại lệ đi qua**, nơi xử lý quyết định **hệ thống sẽ làm gì với thất bại đó**. Hiểu được ba vai trò này giúp đặt `throw`, `throws`, `try`, `catch` và `finally` đúng vị trí, đồng thời không làm mất thông tin chẩn đoán.