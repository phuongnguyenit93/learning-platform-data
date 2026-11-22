# Không dùng `assert` thay kiểm tra dữ liệu đầu vào bắt buộc — Java 17+

## 1. Quy tắc cốt lõi: `assert` không phải validation

Trong Java, **assertion** là một phép kiểm tra giả định nội bộ dành cho quá trình phát triển và chẩn đoán. Cú pháp `assert` có thể bị **tắt khi chương trình chạy**. Vì thế, **không dùng `assert` để thay những kiểm tra dữ liệu đầu vào bắt buộc** của phương thức, constructor, API công khai hay hệ thống nghiệp vụ.

~~~java
// SAI: điều kiện có thể không được kiểm tra khi assertions bị tắt.
static void registerAgeWrong(int age) {
    assert age >= 0 : "age must not be negative";
    // Tiếp tục xử lý age ngay cả khi age âm nếu assertion bị tắt.
}
~~~

~~~java
// ĐÚNG: kiểm tra bắt buộc chạy độc lập với tùy chọn -ea/-da.
static void registerAge(int age) {
    if (age < 0) {
        throw new IllegalArgumentException("age must not be negative");
    }
    // Chỉ xử lý sau khi age hợp lệ.
}
~~~

**Câu hỏi quyết định:** điều kiện này có phải luôn được kiểm tra trong ứng dụng thật, kể cả khi không bật assertions? Nếu **có**, phải dùng kiểm tra chạy bình thường (`if`, validation API, `Objects.requireNonNull`, v.v.) chứ **không chỉ dùng `assert`**.

## 2. Hợp đồng API phải hoạt động khi assertions tắt

Với `-da`, JVM bỏ qua điều kiện và thông điệp trong câu lệnh `assert`, nên không thể dựa vào assertion để chặn dữ liệu sai. Cờ `-ea` hoặc `-da` thuộc lệnh **`java` lúc chạy**, đặt trước tên lớp `main`; chúng không làm thay đổi nghĩa vụ validation của ứng dụng.

Ví dụ ở các phần dưới cho thấy `IllegalArgumentException` và `Objects.requireNonNull` hoạt động giống nhau ở cả hai chế độ. Phần cú pháp, cấu hình assertions theo lớp/package và tác dụng phụ của biểu thức `assert` đã được giải thích trong bài trước.

## 3. Vì sao kiểm tra dữ liệu bên ngoài phải là bắt buộc?

Dữ liệu đầu vào có thể đến từ đối số phương thức công khai, constructor, người dùng, file, mạng hoặc các hệ thống tích hợp. Những dữ liệu này **không phải giả định nội bộ** mà cần có **hợp đồng hợp lệ** được thực thi mọi lần.

Ví dụ sai:

~~~java
static int calculateDiscountWrong(int percent) {
    assert percent >= 0 && percent <= 100;
    return 100 - percent;
}
~~~

Ở chế độ assertions tắt, `calculateDiscountWrong(150)` vẫn chạy và trả `-50`. Đây là lỗi nghiệp vụ ngay cả khi phép toán vẫn biên dịch, không phải dấu hiệu chương trình đúng.

Bản đúng:

~~~java
static int calculateDiscount(int percent) {
    if (percent < 0 || percent > 100) {
        throw new IllegalArgumentException("percent must be 0..100");
    }
    return 100 - percent;
}
~~~

Dù JVM bật hay tắt assertions:

- `calculateDiscount(20)` trả `80`.
- `calculateDiscount(150)` ném `IllegalArgumentException`.
- Đầu vào xấu **không được phép lọt qua kiểm tra**.

Validation cũng quan trọng với những ràng buộc không biểu diễn bằng một số: chuỗi không rỗng, ngày đúng miền, tệp được phép, trạng thái tài khoản, số lượng vật phẩm không âm, mã định danh hợp lệ, giới hạn tài nguyên.

## 4. Chọn ngoại lệ phù hợp khi validation thất bại

| Tình huống | Cách xử lý Java thường phù hợp |
|---|---|
| Đối số số học ngoài miền hợp lệ | `IllegalArgumentException` |
| Tham chiếu đối số bắt buộc khác null | `Objects.requireNonNull(value, "message")` hoặc `NullPointerException` có chủ đích |
| Đối số chuỗi rỗng/blank | Kiểm tra và ném `IllegalArgumentException` |
| Giá trị chuỗi không phân tích được thành số | Xử lý/để lan truyền `NumberFormatException` theo hợp đồng |
| Thao tác không thể làm trong trạng thái hiện tại | `IllegalStateException` |
| API trả checked exception, như đọc file | Catch hoặc declare `throws` theo hợp đồng API |
| Giả định chỉ có thể sai khi có bug **nội bộ** | Có thể dùng `assert` để phát hiện lỗi trong lúc phát triển, không thay validation |

~~~java
static String normalizeUser(String username) {
    java.util.Objects.requireNonNull(username, "username is required");
    if (username.isBlank()) {
        throw new IllegalArgumentException("username must not be blank");
    }
    return username.strip();
}
~~~

- `normalizeUser(null)` → ném `NullPointerException` với thông điệp `username is required`.
- `normalizeUser("   ")` → ném `IllegalArgumentException` với thông điệp `username must not be blank`.
- `normalizeUser(" Lan ")` → trả `"Lan"`.

Cả ba hành vi **không phụ thuộc** vào `-ea`. Dùng đúng loại ngoại lệ còn giúp caller biết ranh giới nào cần kiểm tra dữ liệu, ranh giới nào xử lý trạng thái và ranh giới nào báo lỗi cho người dùng.

## 5. Assertion hợp lý cho bất biến nội bộ

Một **bất biến (invariant)** là điều thuật toán phải duy trì khi dữ liệu đầu vào và các bước đã được xử lý đúng. Assertion có thể hỗ trợ phát hiện vi phạm bất biến nội bộ trong quá trình phát triển:

~~~java
static int roundDownToEven(int value) {
    if (value < 0) {
        throw new IllegalArgumentException("value must not be negative");
    }

    int even = 2 * (value / 2);
    assert even >= 0 : "even must not be negative";
    assert even % 2 == 0 : "even must be divisible by two";
    assert even <= value : "even must not exceed original";
    return even;
}
~~~

Phân biệt hai nhóm kiểm tra:

1. `if (value < 0)` là **validation bắt buộc** vì `value` là đối số do caller cung cấp.
2. Những `assert` còn lại kiểm tra **kết quả nội bộ** do code tạo ra sau validation, để phát hiện khi giả định của lập trình viên bị vi phạm trong phát triển.

Nếu `assert` bị tắt, giá trị trả về vẫn đúng theo logic đã được thiết kế. Ngược lại, nếu bỏ `if` thì kết quả với đầu vào âm có thể không đúng hợp đồng, dù các assertions được bật ở máy phát triển.

Nếu tính đúng đắn hoặc an toàn của ứng dụng đòi hỏi kiểm tra một bất biến ở **production**, hãy dùng kiểm tra **luôn chạy** thay vì trông chờ `assert` được bật.

## 6. Tác dụng phụ không được nằm trong một kiểm tra có thể tắt

~~~java
int processed = 0;
// Không dùng: assert ++processed == 1;
processed++;              // Thao tác nghiệp vụ luôn chạy.
assert processed == 1;   // Chỉ kiểm tra trạng thái nội bộ.
~~~

`assert operation();` sẽ bỏ qua **cả lời gọi `operation()`** khi assertions tắt. Không được đưa ghi file, kiểm tra quyền, thay dữ liệu hoặc trừ tiền chỉ vào biểu thức assertion. Biểu thức sau dấu `:` cũng chỉ được đánh giá khi assertion bật **và sai**, nên không được dùng để tạo tác dụng phụ bắt buộc.

## 7. Từ chối input khác với báo lỗi giả định nội bộ

`AssertionError` kế thừa `Error`, **không** kế thừa `Exception`; `catch (Exception)` không bắt nó. Thất bại assertion thường chỉ ra bug về bất biến thuật toán, không phải dữ liệu mà người dùng được phép nhập sai.

Với null hoặc phạm vi dữ liệu, dùng `Objects.requireNonNull`, `IllegalArgumentException` hoặc `IllegalStateException` theo ý nghĩa hợp đồng; mọi kiểm tra ấy phải làm việc dưới cả `-da` lẫn `-ea`. Bài runnable tiếp theo cố ý bắt `AssertionError` **chỉ để minh họa stdout ổn định**, không phải chính sách xử lý `Error` trong hệ thống thật.


## 8. Chương trình Java 17+ hoàn chỉnh và hai chế độ chạy

Lưu đúng tên file **`AssertVsValidationDemo.java`**:

~~~java
import java.util.Objects;

public final class AssertVsValidationDemo {
    private AssertVsValidationDemo() {}

    static String normalizeUser(String username) {
        Objects.requireNonNull(username, "username is required");
        if (username.isBlank()) {
            throw new IllegalArgumentException("username must not be blank");
        }
        return username.strip();
    }

    static int requirePercent(int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("percent must be 0..100");
        }
        return percent;
    }

    static int roundDownToEven(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("value must not be negative");
        }
        int even = 2 * (value / 2);
        assert even >= 0 : "even must not be negative";
        assert even % 2 == 0 : "even must be divisible by two";
        assert even <= value : "even must not exceed original";
        return even;
    }

    static final class Wallet {
        private int balance;

        Wallet(int openingBalance) {
            if (openingBalance < 0) {
                throw new IllegalArgumentException("opening balance negative");
            }
            this.balance = openingBalance;
        }

        void withdraw(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            if (amount > balance) {
                throw new IllegalStateException("insufficient funds");
            }
            balance -= amount;
            assert balance >= 0 : "internal balance invariant broken";
        }

        int getBalance() {
            return balance;
        }
    }

    // CỐ Ý CÓ BUG: chỉ dùng để so sánh -da với -ea, không dùng thực tế.
    private static int buggyInternalCalculation() {
        int computed = -1;
        assert computed >= 0 : "internal computed negative";
        return computed;
    }

    public static void main(String[] args) {
        System.out.println("assertions enabled="
                + AssertVsValidationDemo.class.desiredAssertionStatus());

        System.out.println("user=" + normalizeUser(" Lan "));
        System.out.println("percent=" + requirePercent(80));

        Wallet wallet = new Wallet(100);
        wallet.withdraw(30);
        System.out.println("balance=" + wallet.getBalance());
        System.out.println("even=" + roundDownToEven(7));

        try {
            normalizeUser(null);
        } catch (NullPointerException ex) {
            System.out.println("null user=" + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
        }

        try {
            normalizeUser("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("blank user=" + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
        }

        try {
            requirePercent(150);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid percent="
                    + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }

        try {
            wallet.withdraw(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid withdraw="
                    + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }

        try {
            wallet.withdraw(100);
        } catch (IllegalStateException ex) {
            System.out.println("insufficient="
                    + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }

        System.out.println("balance after rejection=" + wallet.getBalance());

        // Khối bắt AssertionError CHỈ dành cho bài học minh họa.
        try {
            System.out.println("buggy internal="
                    + buggyInternalCalculation());
        } catch (AssertionError ex) {
            System.out.println("internal assertion=" + ex.getMessage());
        }

        System.out.println("finished=true");
    }
}
~~~

**Biên dịch một lần** bằng JDK 17+, không cần Maven/Gradle, thư viện ngoài hay preview features.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 AssertVsValidationDemo.java
java -da -cp . AssertVsValidationDemo
java -ea -cp . AssertVsValidationDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\AssertVsValidationDemo.java
java -da -cp . AssertVsValidationDemo
java -ea -cp . AssertVsValidationDemo
~~~

### Exact stdout với `-da` (assertions tắt)

~~~text
assertions enabled=false
user=Lan
percent=80
balance=70
even=6
null user=NullPointerException:username is required
blank user=IllegalArgumentException:username must not be blank
invalid percent=IllegalArgumentException:percent must be 0..100
invalid withdraw=IllegalArgumentException:amount must be positive
insufficient=IllegalStateException:insufficient funds
balance after rejection=70
buggy internal=-1
finished=true
~~~

### Exact stdout với `-ea` (assertions bật)

~~~text
assertions enabled=true
user=Lan
percent=80
balance=70
even=6
null user=NullPointerException:username is required
blank user=IllegalArgumentException:username must not be blank
invalid percent=IllegalArgumentException:percent must be 0..100
invalid withdraw=IllegalArgumentException:amount must be positive
insufficient=IllegalStateException:insufficient funds
balance after rejection=70
internal assertion=internal computed negative
finished=true
~~~

**Phân tích kết quả:**

1. Dòng `assertions enabled=...` cho biết trạng thái assertion của **chính lớp demo**.
2. Người dùng và phần trăm hợp lệ chạy bình thường. Sau khi rút 30 từ ví có 100, số dư là 70.
3. Đầu vào `null`, chuỗi chỉ có khoảng trắng, phần trăm `150`, lệnh rút `0` và lệnh rút vượt số dư **đều bị từ chối y hệt** ở cả hai chế độ.
4. `roundDownToEven(7)` trả 6; các `assert` nội bộ đều đúng khi bật.
5. `buggyInternalCalculation()` có lỗi giả định có chủ đích. Với `-da`, câu lệnh `assert` không kiểm tra gì nên trả `-1`; với `-ea`, nó ném `AssertionError` và nhánh demo in thông điệp.
6. **Bài học quan trọng:** validation bắt buộc không đổi theo `-da/-ea`; chỉ kiểm tra assertion chẩn đoán nội bộ phụ thuộc vào cờ này.

## 9. Viết kiểm thử đúng cho API

Nếu một phương thức tuyên bố chỉ chấp nhận `percent` trong `0..100`, hãy kiểm thử cả dữ liệu hợp lệ lẫn dữ liệu sai **ngay cả khi assertions đang bị tắt**.

Ví dụ ý tưởng kiểm thử, không phụ thuộc framework:

~~~java
int accepted = requirePercent(50);     // Phải là 50.
try {
    requirePercent(150);
    throw new IllegalStateException("expected validation to reject input");
} catch (IllegalArgumentException expected) {
    // Giá trị sai đã bị từ chối đúng hợp đồng.
}
~~~

Chú ý đây là **mã minh họa** dùng phương thức `requirePercent` của mục 8; kiểm thử thực tế cần đặt trong lớp kiểm thử/phạm vi truy cập hợp lệ và dùng assertions của framework hoặc cơ chế test thích hợp. Khi kiểm thử exception, không chỉ dựa vào ngôn ngữ `assert` bị vô hiệu trong runtime.

Với JUnit, các phương thức kiểm thử như `assertThrows` của thư viện test không tương đương câu lệnh ngôn ngữ `assert`. Chúng chạy theo cơ chế thư viện kiểm thử, không biến thành câu lệnh `assert` bị bỏ qua theo `-da`.

**Test hai chế độ:** cùng một bộ validation phải đạt khi chạy `-da` và `-ea`. Tùy chính sách, dùng `-ea` trong quá trình phát triển/test để sớm phát hiện bug nội bộ, nhưng tính đúng của API không được phụ thuộc vào việc người triển khai bật cờ ấy.

## 10. Khi nào có thể dùng `assert`?

Những chỗ thường hợp lý (chỉ cho các giả định **nội bộ** không bị ảnh hưởng bởi dữ liệu không tin cậy chưa qua kiểm tra):

- Kiểm tra kết quả trung gian sau một phép biến đổi mà thuật toán bảo đảm bất biến.
- Đánh dấu nhánh nội bộ được thiết kế là không thể tới theo các điều kiện đã được chứng minh.
- Xác minh điều kiện hậu trạng thái khi code xử lý đã hoàn tất và tính đúng vẫn được đảm bảo độc lập với assertion.
- Hỗ trợ phát hiện lỗi lập trình khi chạy môi trường phát triển/test có bật `-ea`.

Ngược lại, **không dùng `assert`** làm phương thức duy nhất để:

- Kiểm tra input của public method, REST handler, constructor, CLI argument.
- Kiểm tra null/blank/giới hạn dữ liệu cần đảm bảo trong sản phẩm.
- Phân quyền truy cập, xác thực và bảo đảm an toàn giao dịch.
- Kiểm tra trạng thái bắt buộc (ví dụ đủ số dư để rút tiền).
- Thực hiện công việc có tác dụng phụ, gọi API, sửa object hoặc cấp quyền.

Đừng cố “giải quyết” một kiểm tra nghiệp vụ thiếu bằng cách bắt người dùng chạy ứng dụng với `-ea`. **Chính mã validation phải luôn thực thi**.

## 11. Các lỗi thường gặp

| Sai lầm | Rủi ro | Cách sửa |
|---|---|---|
| `assert age >= 0;` là điều kiện đầu vào duy nhất | Dữ liệu âm lọt qua nếu assertions tắt | `if (age < 0) throw new IllegalArgumentException(...)` |
| `assert username != null;` trong API công khai | Caller null không bị từ chối ngay khi tắt | `Objects.requireNonNull(username, ...)` |
| Cho rằng `-ea` luôn bật trong production | JVM có thể chạy mặc định không bật | Validation không phụ thuộc cờ assertion |
| `assert ++counter > 0;` | Khi tắt, `counter` không tăng | Tách thao tác bắt buộc ra khỏi assertion |
| `assert authorize(user);` | Khi tắt, việc kiểm tra quyền bị bỏ qua | Gọi logic phân quyền bắt buộc và xử lý kết quả bằng điều kiện thường |
| Bắt `Exception` rồi mong xử lý `AssertionError` | `AssertionError` không kế thừa `Exception` | Sửa bug nội bộ; không dùng Error như validation |
| Viết `assert condition : logAndReturn();` | Detail cũng không chạy khi tắt/điều kiện đúng | Không dựa vào tác dụng phụ trong assert |
| Dùng assert để báo “hết tiền” | Đó là trạng thái nghiệp vụ dự kiến | Kiểm tra và báo `IllegalStateException`/kết quả hợp đồng |
| Viết test validation chỉ chạy khi `-ea` | Không chứng minh an toàn khi tắt | Chạy kiểm thử với `-da` và `-ea` |
| Bắt lỗi validation bằng `catch (AssertionError)` | Biến lỗi input thành Error ngoài hợp đồng | Ném ngoại lệ đầu vào có loại/thông điệp rõ |
| Nghĩ `assert` được chạy ở compile time | Assertion statement được kiểm tra cú pháp khi compile, điều kiện được đánh giá khi chạy nếu bật | Phân biệt compiler check với runtime assertion |
| Dùng một `assert` cho mọi vấn đề bất thường | Không rõ loại lỗi và không bảo đảm kiểm tra | Phân loại input, state, internal invariant và dùng cơ chế phù hợp |

## 12. Bài tập có đáp án

**A — Nhận diện lỗi thiết kế.** Có phương thức:

~~~java
static double divide(double a, double b) {
    assert b != 0;
    return a / b;
}
~~~

Nếu hợp đồng yêu cầu **từ chối mẫu số 0** mọi lúc, đoạn trên có đủ không?

**Đáp án:** Không. Khi assertions tắt, với số thực `double`, phép chia cho 0 có thể tạo `Infinity` hoặc `NaN` thay vì bị từ chối. Thêm:

~~~java
if (b == 0.0) {
    throw new IllegalArgumentException("divisor must not be zero");
}
~~~

**B — Bật/tắt assertion.** Lệnh nào bật assertion của lớp ví dụ?

**Đáp án:** `java -ea -cp . AssertVsValidationDemo`. Để tắt rõ ràng: `java -da -cp . AssertVsValidationDemo`.

**C — Vì sao `assert ++count > 0;` nguy hiểm?**

**Đáp án:** Khi `-da`, biểu thức điều kiện không được đánh giá, nên `count` **không tăng**. Không đưa cập nhật dữ liệu bắt buộc vào assertion.

**D — Loại lỗi.** `AssertionError` nằm dưới `Exception` hay `Error`?

**Đáp án:** Dưới `Error`; `catch (Exception)` không bắt `AssertionError`.

**E — Phân loại điều kiện.** `user != null` của một API công khai và `computed >= 0` sau thuật toán đã xác minh giá trị đầu vào: điều kiện nào phải là validation?

**Đáp án:** `user != null` là **validation bắt buộc**; `computed >= 0` có thể là assertion nội bộ nếu đó là bất biến được đảm bảo theo thuật toán và việc bỏ qua assert không làm sai hành vi production.

**F — So sánh hai lần chạy.** `requirePercent(150)` sẽ thế nào dưới `-da` và `-ea`?

**Đáp án:** Cả hai đều ném `IllegalArgumentException`. Chỉ `buggyInternalCalculation()` biểu lộ sự khác biệt do câu lệnh assertion.

## 13. Checklist và kết luận

- [ ] Hiểu `assert` kiểm tra giả định nội bộ, có thể bị tắt khi chạy.
- [ ] Biết `assert condition;` và `assert condition : detail;`.
- [ ] Biết `-ea` bật, `-da` tắt assertion của ứng dụng theo cấu hình JVM.
- [ ] Không dùng `assert` thay validation dữ liệu đầu vào bắt buộc.
- [ ] Dùng `if`, `throw IllegalArgumentException` và `Objects.requireNonNull` phù hợp hợp đồng.
- [ ] Dùng `IllegalStateException` cho thao tác sai trạng thái khi phù hợp.
- [ ] Biết `AssertionError` là nhánh `Error`, không phải ngoại lệ đầu vào thông thường.
- [ ] Không đưa tác dụng phụ, phân quyền hoặc thay đổi dữ liệu vào biểu thức assertion.
- [ ] Nhận diện khác nhau giữa internal invariant và ràng buộc của input bên ngoài.
- [ ] Kiểm thử validation ngay cả khi `-da`.
- [ ] Chạy `AssertVsValidationDemo.java` trên JDK 17+ với cả `-da` và `-ea`, đối chiếu hai stdout.

**Kết luận:** `assert` giúp tìm **lỗi giả định nội bộ** khi được bật, nhưng **không bảo đảm được thực thi trong mọi lần chạy**. Bất kỳ điều kiện đầu vào hay quy tắc nghiệp vụ nào bắt buộc phải được kiểm tra đều cần **validation luôn chạy**, ném ngoại lệ hoặc trả kết quả theo hợp đồng API; tuyệt đối không chỉ dựa vào `assert`.