# Kiểm tra dữ liệu và xử lý lỗi trong hàm khởi tạo Java

**Constructor (hàm khởi tạo)** là nơi thiết lập trạng thái ban đầu của một object. Trong nhiều class, đây cũng là ranh giới tốt nhất để từ chối những dữ liệu không thể tạo nên một object hợp lệ: tên rỗng, số lượng âm, khoảng thời gian đảo ngược hoặc một tham chiếu bắt buộc nhưng bằng `null`.

Ví dụ, nếu một tài khoản luôn phải có chủ sở hữu và số dư ban đầu không âm, constructor không nên âm thầm nhận `new Account("", -100)` rồi chờ các phương thức khác phát hiện lỗi. Mục tiêu là **khi lời gọi `new` hoàn tất bình thường, object đã thỏa những điều kiện bất biến (invariant) mà class cam kết**.

Tuy nhiên, “kiểm tra dữ liệu trong constructor” không có nghĩa là đặt mọi quy tắc nghiệp vụ và mọi hoạt động I/O vào đó. Bài này phân biệt:

- **Tiền điều kiện của tham số**: dữ liệu đầu vào cần có dạng gì?
- **Invariant của object**: trạng thái nào phải đúng sau khi tạo và sau mỗi hành vi cập nhật?
- **Chuẩn hóa (normalization)**: có nên bỏ khoảng trắng, đổi đơn vị, tạo bản sao dữ liệu mutable?
- **Thất bại khi khởi tạo**: exception ảnh hưởng thế nào đến `new`, phép gán và các side effect đã xảy ra?
- **Hợp đồng lỗi**: nên dùng `IllegalArgumentException`, `NullPointerException`, checked exception hay kiểu lỗi khác?
- **Kiểm thử**: chứng minh constructor nhận dữ liệu hợp lệ và từ chối dữ liệu sai theo cách dự đoán được.

Các chương trình đầy đủ bên dưới dùng Java 17+ và có stdout dự kiến để đối chiếu.

## 1. Constructor là ranh giới tạo trạng thái hợp lệ

Xét class chưa bảo vệ dữ liệu:

~~~java
class Account {
    String owner;
    long balanceCents;

    Account(String owner, long balanceCents) {
        this.owner = owner;
        this.balanceCents = balanceCents;
    }
}
~~~

Đây là **class minh họa**, không phải chương trình độc lập. Những lời gọi sau đều được constructor này chấp nhận:

~~~java
new Account(null, -500);
new Account("   ", 0);
~~~

Nếu thiết kế yêu cầu tên chủ tài khoản có nội dung và số dư không âm, cả hai object đều **không hợp lệ theo nghiệp vụ**, dù trình biên dịch không báo lỗi.

Một phiên bản được kiểm tra:

~~~java
class Account {
    private final String owner;
    private long balanceCents;

    Account(String owner, long balanceCents) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner is required");
        }
        if (balanceCents < 0) {
            throw new IllegalArgumentException("balance must be >= 0");
        }

        this.owner = owner.strip();
        this.balanceCents = balanceCents;
    }
}
~~~

Các quy tắc được áp dụng trước khi constructor kết thúc:

1. `owner` không được `null`.
2. `owner` không được rỗng hoặc chỉ gồm khoảng trắng theo `String.isBlank()`.
3. `balanceCents` không âm.
4. `owner.strip()` bỏ khoảng trắng Unicode ở hai đầu theo định nghĩa của API, tạo giá trị lưu thống nhất.

**Invariant** không phải một phép kiểm tra chỉ có hiệu lực lúc khởi tạo. Nếu object có phương thức `withdraw`, `deposit` hay `rename`, các phương thức cập nhật cũng phải giữ invariant. Constructor chỉ đặt **nền tảng trạng thái ban đầu**.

### Constructor không phải phương thức thông thường

Một constructor:

~~~java
Account(String owner, long balanceCents) {
    // ...
}
~~~

có **tên trùng class** và **không khai báo kiểu trả về**, kể cả `void`. Khi `new Account(...)` hoàn tất bình thường, **biểu thức `new`** cho ra tham chiếu đến object mới; constructor không `return` một object.

Constructor có thể ném exception:

~~~java
throw new IllegalArgumentException("balance must be >= 0");
~~~

Khi exception thoát khỏi quá trình khởi tạo, lời gọi `new` **không hoàn tất bình thường**, vì vậy phép gán bên ngoài dựa vào kết quả của `new` có thể không được thực hiện.

## 2. Những loại điều kiện nên kiểm tra

Trước khi code, hãy viết ra **điều kiện hợp lệ** của object. Mỗi điều kiện nên có lý do nghiệp vụ hoặc lý do bảo vệ API rõ ràng.

| Loại kiểm tra | Ví dụ | Lưu ý |
| --- | --- | --- |
| Bắt buộc khác `null` | `name`, `address`, `configuration` | Chọn rõ chính sách với null |
| Chuỗi có nội dung | `!name.isBlank()` | Chuỗi `""` và chuỗi chỉ có khoảng trắng không như chuỗi thông thường |
| Phạm vi số | `quantity > 0`, `age >= 0` | Xét cả cực trị và tràn số |
| Tập giá trị cố định | `Status`, `DeliveryMode` | Dùng enum khi phù hợp, vẫn xử lý null |
| Quan hệ giữa các trường | `start <= end` | Không chỉ validate riêng từng tham số |
| Collection hợp lệ | Không null, không rỗng, phần tử đúng điều kiện | Định nghĩa có cho phép null element không |
| Định dạng/chuẩn hóa | Mã sản phẩm, mã vùng, tên hiển thị | Không nhầm heuristic đơn giản với quy tắc chuẩn hoàn chỉnh |
| Tính nhất quán với phụ thuộc | Cấu hình dùng cùng đơn vị, cùng domain | Có thể cần factory/service thay vì constructor |
| Giá trị mặc định | Ghi chú để trống, giới hạn hợp lý | Tránh default khiến object sai ý nghĩa |

Ví dụ `age` nằm trong `0..150` chỉ là **quy tắc của một bài toán cụ thể**, không phải giới hạn cố định của Java hay mọi ứng dụng. Đừng đưa giới hạn tùy tiện vào một kiểu được dùng rộng rãi nếu nghiệp vụ không yêu cầu.

### Phân biệt bắt buộc, tùy chọn và trạng thái thiếu

Giả sử một `Person` có `displayName` bắt buộc và `nickname` tùy chọn. Có ít nhất ba chính sách khả thi đối với nickname:

- Chấp nhận `null` như “chưa có biệt danh” và lưu nguyên `null`.
- Chấp nhận `null` nhưng **chuẩn hóa thành chuỗi rỗng**.
- Từ chối null, buộc caller cung cấp một giá trị riêng biểu diễn sự vắng mặt.

Không có cách duy nhất đúng cho mọi API. Quan trọng là chọn **một hợp đồng nhất quán** và không khiến người gọi phải đoán. Với dữ liệu bắt buộc, từ chối sớm thường giảm lỗi xa nguồn gốc.

## 3. Ví dụ hoàn chỉnh: kiểm tra constructor và giữ invariant sau khi tạo

Lưu thành **`ConstructorValidationDemo.java`**:

~~~java
public class ConstructorValidationDemo {
    static final class Account {
        private final String owner;
        private long balanceCents;

        Account(String owner, long initialBalanceCents) {
            if (owner == null) {
                throw new IllegalArgumentException("owner must not be null");
            }

            String normalizedOwner = owner.strip();
            if (normalizedOwner.isEmpty()) {
                throw new IllegalArgumentException("owner must not be blank");
            }
            if (initialBalanceCents < 0) {
                throw new IllegalArgumentException("initial balance must be >= 0");
            }

            this.owner = normalizedOwner;
            this.balanceCents = initialBalanceCents;
        }

        void deposit(long amountCents) {
            if (amountCents <= 0) {
                throw new IllegalArgumentException("deposit must be positive");
            }

            balanceCents = Math.addExact(balanceCents, amountCents);
        }

        String summary() {
            return owner + ": " + balanceCents + " cents";
        }
    }

    public static void main(String[] args) {
        Account account = new Account("  Mai  ", 12_000);
        account.deposit(5_500);
        System.out.println(account.summary());

        try {
            new Account(null, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected name: " + ex.getMessage());
        }

        try {
            new Account("An", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected balance: " + ex.getMessage());
        }

        try {
            account.deposit(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected deposit: " + ex.getMessage());
        }

        System.out.println("Still: " + account.summary());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ConstructorValidationDemo.java
java ConstructorValidationDemo
~~~

Stdout:

~~~text
Mai: 17500 cents
Rejected name: owner must not be null
Rejected balance: initial balance must be >= 0
Rejected deposit: deposit must be positive
Still: Mai: 17500 cents
~~~

Giải thích:

1. `new Account("  Mai  ", 12_000)` thành công; constructor chuẩn hóa `"  Mai  "` thành `"Mai"`.
2. `deposit(5_500)` hợp lệ, cộng số dư thành `17_500`.
3. `new Account(null, 0)` ném `IllegalArgumentException` với thông điệp chỉ rõ trường sai.
4. `new Account("An", -1)` bị từ chối bởi điều kiện số dư.
5. `deposit(0)` bị từ chối **trước khi** cập nhật field; số dư giữ nguyên.
6. `Math.addExact` ném `ArithmeticException` nếu phép cộng `long` tràn, thay vì cho kết quả tràn bất ngờ.

Một object đã tạo hợp lệ có thể vẫn trở nên sai nếu những method cập nhật bỏ qua kiểm tra. Vì vậy hãy định nghĩa invariant rồi xem constructor **và mọi hành vi thay đổi state** có cùng duy trì nó hay không.

**Đơn vị tiền:** Ví dụ dùng `long balanceCents` và gọi là `cents`. Đây chỉ là mô hình biểu diễn số tiền dưới dạng đơn vị nguyên nhỏ nhất. Hệ thống thực phải xác định loại tiền, độ chia nhỏ và quy tắc làm tròn; không tùy tiện dùng `double` cho kế toán chính xác.

## 4. Chọn exception phù hợp với nguyên nhân

Không có một exception duy nhất bắt buộc dùng cho mọi constructor. Những lựa chọn thông dụng:

| Exception | Khi nào phù hợp | Ví dụ |
| --- | --- | --- |
| `IllegalArgumentException` | Argument không đáp ứng hợp đồng constructor | Số lượng âm, mã rỗng, khoảng ngày đảo ngược |
| `NullPointerException` | Đầu vào buộc không được null theo hợp đồng API | `Objects.requireNonNull(name, "name")` |
| `NumberFormatException` | Không chuyển được chuỗi thành số đúng định dạng | `Integer.parseInt("abc")` |
| `ArithmeticException` | Phép toán không hợp lệ về số học | `Math.addExact` phát hiện tràn |
| Checked exception như `IOException` | Constructor thật sự làm thao tác có thể phát sinh lỗi I/O | Mở/đọc một nguồn dữ liệu |
| `IllegalStateException` | Thao tác không hợp lệ vì **trạng thái hiện tại**, thường là method hơn là argument constructor | Dịch vụ đã đóng không thể tiếp tục chạy |

`NumberFormatException` là subclass của `IllegalArgumentException`. `NullPointerException` và `IllegalArgumentException` đều là unchecked exceptions thuộc hệ `RuntimeException`. Chúng không yêu cầu phải khai báo `throws` theo quy tắc checked exception.

### `IllegalArgumentException` hay `NullPointerException` khi argument null?

Hai kiểu chính sách đều tồn tại:

~~~java
if (name == null) {
    throw new IllegalArgumentException("name is required");
}
~~~

hoặc:

~~~java
this.name = java.util.Objects.requireNonNull(name, "name");
~~~

`Objects.requireNonNull` ném `NullPointerException` nếu `name` null. Chọn một chính sách nhất quán với API; nếu API công khai có tài liệu xác định loại exception, hãy kiểm thử đúng hợp đồng đó. **Không mặc định rằng Java yêu cầu mọi null parameter phải ném một loại exception cố định.**

Các đoạn trên là **mảnh mã minh họa**, cần đặt trong constructor phù hợp; `this.name` yêu cầu class có field tương ứng.

### Thông điệp lỗi nên cụ thể

Thông điệp tốt nói rõ tham số và điều kiện, ví dụ:

- `"quantity must be positive"`;
- `"start must not be after end"`;
- `"owner must not be blank"`.

Thông điệp quá chung như `"invalid"` khó giúp xác định nguồn sai khi một constructor có nhiều tham số. Tuy nhiên không nên đưa mật khẩu, access token, dữ liệu nhạy cảm hoặc toàn bộ nội dung người dùng nhập vào exception message và log.

## 5. Kiểm tra null, chuỗi rỗng và chuẩn hóa

Chuỗi có những trạng thái khác nhau:

| Giá trị | `value == null` | `value.isEmpty()` nếu không null | `value.isBlank()` nếu không null |
| --- | --- | --- | --- |
| `null` | true | Không được gọi | Không được gọi |
| `""` | false | true | true |
| `"   "` | false | false | true |
| `" Mai "` | false | false | false |
| `"Mai"` | false | false | false |

**Quan trọng:** Không gọi `name.isBlank()` **trước khi** xử lý khả năng `name == null`, vì gọi method trên null sẽ gây `NullPointerException`.

`String.strip()` bỏ ký tự khoảng trắng hai đầu theo `Character.isWhitespace`, khác với `String.trim()` ở phạm vi ký tự được xử lý. `isBlank()` cũng dựa trên khái niệm khoảng trắng Unicode của Java. Chúng hữu ích cho tên thông thường, nhưng không phải giải pháp chuẩn hóa Unicode toàn diện cho mọi dữ liệu.

Một helper kiểm tra và chuẩn hóa có thể viết:

~~~java
static String normalizeName(String name) {
    if (name == null) {
        throw new IllegalArgumentException("name is required");
    }

    String normalized = name.strip();
    if (normalized.isEmpty()) {
        throw new IllegalArgumentException("name must not be blank");
    }

    return normalized;
}
~~~

Đây là **method minh họa**. Có thể gọi trong constructor:

~~~java
this.name = normalizeName(name);
~~~

Nếu nhiều class cùng cần một chính sách tên giống nhau, có thể đặt validation ở một value object chuyên biệt hoặc utility có hợp đồng rõ. Nhưng tránh tạo helper tổng quát rồi vô tình dùng chung quy tắc cho những tên có nhu cầu khác nhau, như tên đăng nhập, tên người, tên file và mã định danh.

### Chuẩn hóa phải có lý do nghiệp vụ

Một số trường **không nên tự động strip hoặc chuyển chữ hoa/thường**, ví dụ mật khẩu, mã phân biệt khoảng trắng, dữ liệu chữ ký số hay chuỗi được dùng làm khóa có tính chính xác từng byte. Nếu constructor thay đổi nội dung đầu vào, hãy ghi rõ quy tắc để người gọi không bất ngờ.

## 6. Kiểm tra nhiều tham số liên quan nhau

Một số object chỉ hợp lệ khi các tham số **có quan hệ đúng**, dù từng tham số xét riêng đều hợp lệ.

Lưu file **`DateRangeValidationDemo.java`**:

~~~java
import java.time.LocalDate;
import java.util.Objects;

public class DateRangeValidationDemo {
    static final class DateRange {
        private final LocalDate start;
        private final LocalDate end;

        DateRange(LocalDate start, LocalDate end) {
            this.start = Objects.requireNonNull(start, "start");
            this.end = Objects.requireNonNull(end, "end");

            if (end.isBefore(start)) {
                throw new IllegalArgumentException("end must be >= start");
            }
        }

        long daysInclusive() {
            return java.time.temporal.ChronoUnit.DAYS
                    .between(start, end) + 1;
        }
    }

    public static void main(String[] args) {
        DateRange range = new DateRange(
                LocalDate.of(2026, 3, 10),
                LocalDate.of(2026, 3, 12));

        System.out.println("Days: " + range.daysInclusive());

        try {
            new DateRange(
                    LocalDate.of(2026, 3, 12),
                    LocalDate.of(2026, 3, 10));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DateRangeValidationDemo.java
java DateRangeValidationDemo
~~~

Stdout:

~~~text
Days: 3
Rejected: end must be >= start
~~~

Mặc dù `start` và `end` đều là `LocalDate` hợp lệ, constructor vẫn từ chối khi `end` nằm trước `start`. Ví dụ quy định khoảng **bao gồm cả hai đầu** nên `daysInclusive()` cộng thêm 1. Một hệ thống khác có thể dùng khoảng nửa mở `[start, end)`; khi đó điều kiện và cách đếm ngày cần điều chỉnh theo hợp đồng.

**Điểm thiết kế:** Kiểu `DateRange` gom hai tham số có quan hệ bất biến. Các method dùng `DateRange` có thể tin tưởng rằng object hoàn tất thành công không chứa ngày kết thúc đứng trước ngày bắt đầu, miễn class không cung cấp đường sửa state làm hỏng điều kiện đó.

### Kiểm tra trước khi gán field hay sau khi gán?

Trong `DateRange`, hai field được gán rồi điều kiện quan hệ được kiểm tra. Nếu constructor ném exception, object không được trả về bình thường cho caller. Cách viết này hợp lệ khi **không công bố `this` trong constructor** và không có side effect ngoài việc thiết lập fields. Tuy nhiên, kiểm tra toàn bộ dữ liệu bằng biến cục bộ **trước khi gán field** thường giúp code dễ hiểu và giảm nguy cơ để trạng thái trung gian quan sát được nếu class phức tạp.

Không có quy tắc Java bắt buộc mọi phép validate phải xảy ra trước mọi phép gán. Yêu cầu quan trọng là object được công bố sau khi constructor thành công phải hợp lệ và không làm rò rỉ instance chưa hoàn tất.

## 7. Constructor thất bại: phép gán bên ngoài có diễn ra không?

Một exception được ném từ constructor và không được xử lý trong chuỗi khởi tạo khiến **biểu thức `new` kết thúc bất thường**. Bên gọi không nhận được reference do biểu thức này trả về bình thường.

Lưu **`ConstructionFailureDemo.java`**:

~~~java
public class ConstructionFailureDemo {
    static final class User {
        private final String name;

        User(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("invalid name");
            }
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        User current = new User("Original");

        try {
            current = new User(" ");
            System.out.println("assignment completed");
        } catch (IllegalArgumentException ex) {
            System.out.println("constructor failed");
        }

        System.out.println("current=" + current.name());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructionFailureDemo.java
java ConstructionFailureDemo
~~~

Stdout:

~~~text
constructor failed
current=Original
~~~

Giải thích:

1. `current` đã trỏ đến một User hợp lệ có tên `Original`.
2. Ở vế phải `new User(" ")`, constructor phát hiện tên chỉ có khoảng trắng và ném `IllegalArgumentException`.
3. Vì vế phải không hoàn tất bình thường, phép gán `current = ...` không diễn ra.
4. `current` vẫn trỏ đến object cũ, không trở thành null và cũng không chuyển tới instance tạo thất bại.
5. Dòng `assignment completed` không được thực thi.

Đừng kết luận rằng Java luôn “rollback” mọi thứ khi constructor thất bại. **Việc không hoàn tất phép gán reference khác hẳn việc hoàn tác những side effect đã xảy ra**.

### Có thể đã có object đang trong quá trình khởi tạo

JVM có thể đã cấp phát không gian và chạy một phần initializer hoặc constructor trước khi exception xuất hiện. Trong trường hợp thông thường, caller không nhận được reference từ biểu thức `new` thất bại. Nhưng nếu constructor **làm rò rỉ `this`** ra một static collection, callback hoặc thread, mã khác có thể giữ một tham chiếu đến object chưa khởi tạo hoàn tất. Đây là lý do rất quan trọng để không công bố `this` quá sớm.

## 8. Side effect trong constructor không tự được hoàn tác

Constructor có thể sửa static field, ghi log, thêm dữ liệu vào registry hoặc gọi một dịch vụ. Nếu sau đó ném exception, các side effect đã xảy ra **không tự biến mất**.

Lưu **`ConstructorSideEffectDemo.java`**:

~~~java
public class ConstructorSideEffectDemo {
    static final class Registration {
        private static int attempts;
        private static int successful;

        private final String code;

        Registration(String code) {
            attempts++;

            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code is required");
            }

            this.code = code;
            successful++;
        }

        static int attempts() {
            return attempts;
        }

        static int successful() {
            return successful;
        }

        String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        Registration ok = new Registration("A1");

        try {
            new Registration("");
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected invalid code");
        }

        System.out.println("Valid code: " + ok.code());
        System.out.println("Attempts: " + Registration.attempts());
        System.out.println("Successful: " + Registration.successful());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorSideEffectDemo.java
java ConstructorSideEffectDemo
~~~

Stdout:

~~~text
Rejected invalid code
Valid code: A1
Attempts: 2
Successful: 1
~~~

`attempts` tăng ở đầu constructor nên đếm cả lần khởi tạo thất bại. `successful` chỉ tăng sau khi dữ liệu đã được kiểm tra và field bắt buộc được gán. Cả hai static field thuộc class runtime, không thuộc riêng từng instance. Ví dụ chạy tuần tự; `++` ở static field không tự thread-safe.

**Bài học:** Nếu muốn đếm số object **được tạo thành công**, đừng tăng counter trước khi quá trình validation có thể thất bại. Với constructor phức tạp còn nhiều bước sau đó có thể ném exception, việc tăng ở cuối cũng cần cân nhắc chính xác định nghĩa “thành công”, đặc biệt với side effect bên ngoài.

### Không nên thực hiện giao dịch ngoài trong constructor nếu tránh được

Mở kết nối, ghi cơ sở dữ liệu, gửi email hoặc cập nhật trạng thái toàn hệ thống ngay trong constructor khiến cơ chế lỗi khó quản lý:

- Dữ liệu có thể bị ghi một phần trước khi constructor ném exception.
- Caller không nhận object nhưng thao tác ngoài đã xảy ra.
- Việc retry `new` có thể gây ghi lặp.
- Việc kiểm thử constructor trở nên phụ thuộc môi trường.

Với tác vụ I/O hoặc giao dịch, thường nên tạo object cấu hình hợp lệ trước, rồi thực hiện hành vi có tên rõ và chiến lược lỗi/rollback riêng. Không có quy tắc cấm tuyệt đối constructor làm I/O, nhưng cần cân nhắc ownership, cleanup và hợp đồng exception.

## 9. Xử lý ngoại lệ ở bên trong hay bên ngoài constructor?

Có hai mức quyết định:

### Bên trong constructor: phát hiện và từ chối dữ liệu sai

~~~java
if (quantity <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
~~~

Đây là mẫu đơn giản và hiệu quả: object không bị tạo thành công với `quantity` vi phạm điều kiện.

### Bên ngoài constructor: quyết định chính sách khôi phục

~~~java
try {
    Order order = new Order(quantity);
    save(order);
} catch (IllegalArgumentException ex) {
    System.out.println("Please correct the input");
}
~~~

Đây là **đoạn minh họa**, giả định `Order` và `save` được định nghĩa phù hợp. Lớp điều phối hoặc tầng giao diện có thể yêu cầu nhập lại, hiển thị thông điệp thân thiện hoặc từ chối request. Constructor **không nên tự quyết định cách hiển thị thông báo GUI/HTTP** nếu class chỉ mô tả domain object.

### Không nuốt exception rồi giữ object không hợp lệ

Mẫu lỗi:

~~~java
class UnsafeItem {
    private int quantity;

    UnsafeItem(int quantity) {
        if (quantity <= 0) {
            System.out.println("Warning: invalid quantity");
        }
        this.quantity = quantity;
    }
}
~~~

Đoạn class này cho phép tạo `new UnsafeItem(-3)` dù in cảnh báo. Nếu invariant yêu cầu số lượng dương, log không phải một phương thức xử lý lỗi đủ để bảo vệ tính đúng đắn.

Chỉ “sửa” dữ liệu lỗi bằng default khi **hợp đồng nêu rõ** rằng dữ liệu đó được phép chuẩn hóa. Chẳng hạn giá trị `null` của một ghi chú tùy chọn có thể trở thành chuỗi rỗng; một mã định danh bắt buộc null không nên bị biến thành một mã ngẫu nhiên âm thầm.

## 10. Constructor chaining: validate ở đâu khi có nhiều overload?

Khi class có nhiều constructor, dễ xuất hiện lỗi **mỗi overload kiểm tra một kiểu**, dẫn tới các object cùng class nhưng điều kiện hợp lệ không nhất quán.

Trong Java 17, một constructor gọi constructor khác bằng `this(...)` phải đặt lời gọi đó ở vị trí **câu lệnh đầu tiên** của constructor. Vì vậy không thể viết vài câu lệnh validation rồi mới gọi `this(...)` trong cùng constructor theo cú pháp Java 17 thông thường.

Một thiết kế rõ ràng là ủy quyền mọi overload về một constructor chính:

Lưu file **`ConstructorChainingValidationDemo.java`**:

~~~java
public class ConstructorChainingValidationDemo {
    static final class Ticket {
        private final String code;
        private final int quantity;

        Ticket(String code) {
            this(code, 1);
        }

        Ticket(String code, int quantity) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code is required");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }

            this.code = code;
            this.quantity = quantity;
        }

        String summary() {
            return code + " x" + quantity;
        }
    }

    public static void main(String[] args) {
        System.out.println(new Ticket("VIP").summary());
        System.out.println(new Ticket("STD", 3).summary());

        try {
            new Ticket("BAD", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorChainingValidationDemo.java
java ConstructorChainingValidationDemo
~~~

Stdout:

~~~text
VIP x1
STD x3
Rejected: quantity must be positive
~~~

`Ticket(String)` gọi `this(code, 1)`, không tạo thêm Ticket object. Constructor hai tham số là nơi có **quy tắc validation chung**. Nhờ đó, cả hai đường khởi tạo đều áp dụng cùng invariant.

### Khi cần kiểm tra trước lời gọi `this(...)`

Bạn có thể truyền **kết quả của một helper method** làm đối số của lời gọi constructor khác:

~~~java
Ticket(String code) {
    this(requireCode(code), 1);
}

private static String requireCode(String code) {
    if (code == null || code.isBlank()) {
        throw new IllegalArgumentException("code is required");
    }
    return code;
}
~~~

Các đoạn trên là **mảnh mã thiết kế thay thế**, không ghép thêm constructor cùng chữ ký vào file demo đã có. Helper `requireCode` được đánh giá như một biểu thức đối số trước khi constructor đích tiếp tục được gọi; nếu helper ném exception, quá trình `new` không hoàn tất. Chỉ làm vậy khi cần thiết; đặt invariant ở constructor đích vẫn thường dễ đọc hơn.

### Validation ở superclass

Nếu class con extends class cha, Java 17 thường yêu cầu `super(...)` ở vị trí đầu constructor khi được viết tường minh. Ví dụ:

~~~java
class BaseConfig {
    BaseConfig(int port) {
        if (port <= 0 || port > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
    }
}

class ServerConfig extends BaseConfig {
    ServerConfig(int port, String host) {
        super(port);
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("host is required");
        }
    }
}
~~~

Đây là hai class minh họa. Constructor superclass có trách nhiệm kiểm tra `port`; constructor subclass kiểm tra `host`. Nếu `super(port)` ném exception thì các câu lệnh còn lại của constructor subclass không chạy. Không thể dùng một khối `try` thông thường đặt **bao quanh** lời gọi `super(...)` trong body constructor của Java 17; caller bên ngoài có thể bắt lỗi từ `new ServerConfig(...)`.

Mọi class trong chuỗi kế thừa nên tự duy trì invariant của phần trạng thái do nó quản lý. Tránh viết subclass phá vỡ các giả định mà superclass tạo ra.

## 11. Bảo vệ đầu vào mutable: constructor cần defensive copy khi nào?

Đối số là object mutable hoặc collection có thể bị **caller sửa sau khi constructor kết thúc**. Nếu constructor chỉ lưu nguyên tham chiếu, invariant ban đầu có thể bị phá vỡ mà không đi qua method của class.

Xét code dễ bị alias:

~~~java
class Team {
    private final java.util.List<String> members;

    Team(java.util.List<String> members) {
        this.members = members;
    }

    java.util.List<String> members() {
        return members;
    }
}
~~~

Nếu caller truyền một `ArrayList`, sau đó thêm/xóa phần tử trong list cũ, `Team` quan sát cùng thay đổi. Method `members()` cũng để lộ list nội bộ cho caller sửa. Field `final` chỉ ngăn gán tham chiếu khác cho `members`, **không làm ArrayList bất biến**.

### Ví dụ hoàn chỉnh với `List.copyOf`

Lưu file **`DefensiveCopyConstructorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class DefensiveCopyConstructorDemo {
    static final class Team {
        private final List<String> members;

        Team(List<String> members) {
            Objects.requireNonNull(members, "members");

            List<String> copy = List.copyOf(members);

            if (copy.isEmpty()) {
                throw new IllegalArgumentException("members must not be empty");
            }

            for (String member : copy) {
                if (member.isBlank()) {
                    throw new IllegalArgumentException("member must not be blank");
                }
            }

            this.members = copy;
        }

        List<String> members() {
            return members;
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("Mai");
        source.add("An");

        Team team = new Team(source);

        source.add("Binh");
        System.out.println("Source: " + source);
        System.out.println("Team: " + team.members());

        try {
            team.members().add("Lan");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Cannot modify team members");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefensiveCopyConstructorDemo.java
java DefensiveCopyConstructorDemo
~~~

Stdout:

~~~text
Source: [Mai, An, Binh]
Team: [Mai, An]
Cannot modify team members
~~~

Trong constructor:

1. `Objects.requireNonNull` từ chối list reference null.
2. `List.copyOf(members)` tạo hoặc sử dụng một danh sách không thể sửa qua API mutation thông thường, không chia sẻ cấu trúc mutable của `ArrayList` nguồn. Nó cũng **từ chối phần tử null**.
3. List rỗng hoặc tên thành viên chỉ có khoảng trắng bị từ chối.
4. Field `members` được gán sau khi dữ liệu đã qua kiểm tra.
5. Caller không thể sửa list đã lưu bằng cách sửa `source` hay gọi `team.members().add(...)`.

**Giới hạn:** `List.copyOf` không tạo deep copy của các phần tử. Với `List<Person>` nếu từng `Person` mutable, caller vẫn có thể thay đổi trạng thái của một `Person` chung. Ví dụ dùng `String`, là immutable, nên tránh vấn đề đó. Trong bài toán khác, hãy định nghĩa rõ mức độ bất biến cần có.

### Nếu truyền mảng

Mảng trong Java luôn mutable. Với mảng primitive `int[]`, constructor có thể dùng `values.clone()` để sao chép phần tử. Nếu accessor trả lại mảng, thường cần sao chép lần nữa để tránh lộ tham chiếu nội bộ.

~~~java
class Scores {
    private final int[] values;

    Scores(int[] values) {
        if (values == null) {
            throw new IllegalArgumentException("values required");
        }
        this.values = values.clone();
    }

    int[] values() {
        return values.clone();
    }
}
~~~

Đoạn class minh họa. Với mảng của reference type, `clone()` sao chép **các tham chiếu phần tử** chứ không tạo deep copy của object phần tử.

## 12. Record cũng phải bảo vệ invariant khi có constructor

Từ Java 16, `record` giúp biểu diễn các giá trị có thành phần cố định. Record có thể khai báo **compact constructor** để validate tham số trước khi giá trị được gán vào các component fields của record.

Lưu file **`ValidatedRecordDemo.java`**:

~~~java
public class ValidatedRecordDemo {
    record Product(String code, int quantity) {
        Product {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code is required");
            }
            if (quantity < 0) {
                throw new IllegalArgumentException("quantity must be >= 0");
            }

            code = code.strip();
        }
    }

    public static void main(String[] args) {
        Product product = new Product("  P01  ", 3);

        System.out.println(product.code());
        System.out.println(product.quantity());

        try {
            new Product(" ", 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected invalid product");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ValidatedRecordDemo.java
java ValidatedRecordDemo
~~~

Stdout:

~~~text
P01
3
Rejected invalid product
~~~

Trong compact constructor, các tên `code` và `quantity` là tham số tương ứng với record components. Sau khi thân compact constructor hoàn tất bình thường, compiler sắp xếp việc khởi tạo các component fields theo quy tắc record. Gán `code = code.strip()` trong compact constructor làm **giá trị sau chuẩn hóa** được dùng để khởi tạo field.

**Không suy luận rằng record luôn immutable sâu:** các component reference tới mảng hoặc collection mutable cần cơ chế copy phù hợp nếu muốn bảo vệ toàn bộ trạng thái quan sát được.

## 13. Exception checked và constructor làm I/O

Thông thường các constructor của **value object/domain object** chỉ nên validate dữ liệu trong bộ nhớ. Tuy nhiên một constructor tạo tài nguyên có thể cần I/O và có khả năng ném checked exception.

Ví dụ khai báo:

~~~java
class FileReaderResource {
    private final java.io.BufferedReader reader;

    FileReaderResource(java.nio.file.Path path)
            throws java.io.IOException {
        java.util.Objects.requireNonNull(path, "path");
        this.reader = java.nio.file.Files.newBufferedReader(path);
    }
}
~~~

Đây là **class minh họa**, không có `main` và chưa có phương thức đóng tài nguyên nên **chưa đủ** để sử dụng trong ứng dụng thật. `Files.newBufferedReader` có thể ném `IOException`; vì vậy constructor khai báo `throws IOException` và caller cần xử lý hoặc khai báo lan truyền checked exception này.

Trong thiết kế sản xuất:

- Nếu class sở hữu reader/file/socket, cần một chiến lược đóng tài nguyên, thường triển khai `AutoCloseable`.
- Nếu constructor mở nhiều tài nguyên rồi bước sau thất bại, những tài nguyên đã mở trước có thể cần đóng trong xử lý lỗi.
- Với một hoạt động tạo tài nguyên có nhiều bước, factory có tên rõ hoặc `try-with-resources` ở tầng sử dụng có thể làm vòng đời dễ kiểm soát hơn.
- Không dùng GC như một cách đóng file hoặc connection đúng thời điểm.

### Preserve nguyên nhân gốc

Khi bắt exception mức thấp và chuyển thành exception ý nghĩa hơn, nên giữ **cause** nếu muốn người gọi chẩn đoán:

~~~java
throw new IllegalStateException("Cannot initialize resource", cause);
~~~

Đây là mảnh minh họa trong một `catch` có biến `cause` kiểu `Throwable` phù hợp. Không nên bắt mọi exception rồi chỉ ném `new IllegalArgumentException("invalid")` làm mất stack/cause nếu nguyên nhân thật là I/O, quyền truy cập hoặc trạng thái hệ thống.

## 14. Constructor không tự rollback và không nên rò rỉ `this`

Trong khi constructor đang chạy, `this` đã có thể được dùng ở các ngữ cảnh instance hợp lệ. Nếu truyền `this` ra ngoài trước khi object khởi tạo xong, mã khác có thể giữ tham chiếu đến object đang ở trạng thái trung gian.

Ví dụ thiết kế rủi ro:

~~~java
class Registry {
    static Object last;
}

class LeakyObject {
    private final String id;

    LeakyObject(String id) {
        Registry.last = this; // Công bố reference quá sớm.
        if (id == null) {
            throw new IllegalArgumentException("id required");
        }
        this.id = id;
    }
}
~~~

Đây là **hai class minh họa**, không phải chương trình độc lập. Nếu constructor ném exception sau khi `Registry.last = this`, biến static `Registry.last` đã giữ một tham chiếu đến object **chưa khởi tạo hoàn tất**. Trong Java Memory Model, xuất bản `this` quá sớm còn có thể gây vấn đề visibility giữa các thread.

Các nguyên tắc thực hành:

- Validate dữ liệu quan trọng và xây dựng trạng thái trước khi công bố object.
- Không thêm `this` vào static registry trong constructor nếu không kiểm soát rõ vòng đời và lỗi.
- Không mở thread trong constructor rồi để thread chạy code phụ thuộc các field chưa khởi tạo.
- Tránh gọi phương thức **có thể bị override** từ constructor của superclass: subclass có thể chưa chạy các field initializer.
- Nếu cần đăng ký listener/callback, cân nhắc làm ở bước riêng **sau khi tạo object thành công**.

**Final field không phải phép màu:** `private final String id` hữu ích để tránh gán lại field, nhưng không thể sửa mọi vấn đề nếu object bị công bố không an toàn trong quá trình khởi tạo.

## 15. Đừng gọi method override được từ constructor

Vấn đề không chỉ là validation: khi superclass constructor gọi một instance method có thể override, Java vẫn dùng dynamic dispatch và có thể gọi phiên bản subclass **trước khi field subclass được khởi tạo xong**.

Lưu file **`ConstructorOverridePitfallDemo.java`**:

~~~java
public class ConstructorOverridePitfallDemo {
    static class Base {
        Base() {
            System.out.println("Base constructor");
            describe();
        }

        void describe() {
            System.out.println("Base describe");
        }
    }

    static final class Child extends Base {
        private String id = "ready";

        Child() {
            System.out.println("Child constructor");
        }

        @Override
        void describe() {
            System.out.println("Child id=" + id);
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        child.describe();
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorOverridePitfallDemo.java
java ConstructorOverridePitfallDemo
~~~

Stdout:

~~~text
Base constructor
Child id=null
Child constructor
Child id=ready
~~~

Superclass constructor gọi `describe()`. Vì object runtime thuộc `Child`, Java gọi `Child.describe()` ngay lúc đó. Nhưng initializer `id = "ready"` của Child chưa chạy; field vẫn ở giá trị mặc định `null`. Khi tạo xong, lời gọi từ `main` mới in `ready`.

Nếu method bị override thực hiện validation dựa trên field subclass, nó có thể **kết luận sai hoặc ném exception** trong giai đoạn object chưa sẵn sàng. Tránh cấu trúc này; chỉ chạy những helper an toàn, không override được từ constructor khi cần thiết.

## 16. Validation không nên phụ thuộc trạng thái toàn hệ thống nếu có thể tránh

Constructor cần đảm bảo invariant nội tại, ví dụ `quantity > 0`. Nhưng một số điều kiện thay đổi theo thời gian:

- Mã người dùng còn tồn tại trong cơ sở dữ liệu hay không?
- Tên tài khoản đã được sử dụng chưa?
- Tồn kho còn đủ tại thời điểm đặt hàng?
- Token thanh toán còn hợp lệ không?
- Một dịch vụ bên ngoài đang khả dụng không?

Những điều này thường thuộc **quy trình tạo/đăng ký**, transaction hoặc domain service, không phải thuộc tính chỉ từ tham số. Ví dụ `new OrderRequest(productId, quantity)` có thể đảm bảo dữ liệu có cấu trúc và số lượng dương, nhưng không thể đảm bảo tồn kho còn đủ trong tương lai.

Một cách phân lớp:

~~~text
Dữ liệu người dùng
       |
       v
Validate/normalize dữ liệu cấu trúc
       |
       v
new OrderRequest(...)  -> request hợp lệ nội tại
       |
       v
OrderService kiểm tra tồn kho, quyền, giao dịch
       |
       v
Lưu đơn và thực hiện hậu xử lý theo chính sách
~~~

Đây là sơ đồ thiết kế, không khẳng định mọi ứng dụng phải dùng service theo đúng tên đó. Đặt kiểm tra đúng tầng giúp constructor **dễ dự đoán, dễ kiểm thử, ít side effect và không chứa giao dịch kéo dài**.

## 17. Kiểm thử constructor: ca hợp lệ, ca biên và ca không hợp lệ

Một constructor đáng tin cần được kiểm chứng ở cả ba loại đường đi:

1. **Happy path:** input hợp lệ tạo object có field đúng.
2. **Boundary path:** giá trị sát ngưỡng, như 0 nếu được phép, 1 nếu số lượng phải dương, chuỗi có khoảng trắng hai đầu.
3. **Failure path:** null, chuỗi blank, số âm, thứ tự ngày đảo ngược, collection rỗng hoặc phần tử sai.
4. **Aliasing path:** caller sửa mảng/list cũ sau khi tạo object; object có giữ invariant không?
5. **No side effect path:** khi validation thất bại, không gây thay đổi bên ngoài trái hợp đồng.
6. **Consistency path:** mọi constructor overload và factory đi tới cùng trạng thái hợp lệ.

### Bộ kiểm tra Java không cần thư viện ngoài

Lưu file **`ConstructorTestDemo.java`**:

~~~java
public class ConstructorTestDemo {
    static final class Range {
        private final int start;
        private final int end;

        Range(int start, int end) {
            if (end < start) {
                throw new IllegalArgumentException("end must be >= start");
            }
            this.start = start;
            this.end = end;
        }

        int length() {
            return Math.subtractExact(end, start);
        }
    }

    static void assertEquals(int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "expected=" + expected + ", actual=" + actual);
        }
    }

    static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid input rejected");
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        assertEquals(5, new Range(3, 8).length());
        assertEquals(0, new Range(4, 4).length());

        expectInvalid(() -> new Range(8, 3));

        System.out.println("All constructor checks passed");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorTestDemo.java
java ConstructorTestDemo
~~~

Stdout:

~~~text
invalid input rejected
All constructor checks passed
~~~

Điểm cần hiểu:

- `Range(3, 8)` hợp lệ, có độ dài 5.
- `Range(4, 4)` hợp lệ, độ dài 0 vì hợp đồng cho phép hai đầu bằng nhau.
- `Range(8, 3)` bị từ chối; helper `expectInvalid` xác nhận đúng loại exception.
- Nếu constructor không ném exception như dự kiến, helper ném `AssertionError` để báo bài kiểm tra thất bại.
- Trong `expectInvalid`, chỉ `IllegalArgumentException` được xem là kết quả từ chối hợp lệ; nếu ném một exception khác, nó không bị âm thầm coi là pass.

Đây là cách kiểm tra thủ công đủ để học cơ chế. Trong dự án thật, JUnit có `assertThrows` và các công cụ tổ chức nhiều test case rõ ràng hơn.

### Đừng test chỉ bằng cách “code chạy không lỗi”

Nếu `new Account("Mai", 100)` chạy được, ta mới biết **một ca hợp lệ** hoạt động. Chưa biết constructor có từ chối `null`, blank hoặc số âm. Test đủ phải cố tình truyền **dữ liệu sai** và kiểm tra trạng thái không hợp lệ không lọt qua ranh giới tạo object.

## 18. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Constructor chấp nhận mọi dữ liệu | Object có state bất hợp lệ | Định nghĩa invariant, từ chối đầu vào sai |
| Chỉ in cảnh báo thay vì ném exception | Caller vẫn nhận object không hợp lệ | Ném exception khi vi phạm điều kiện bắt buộc |
| Gọi `name.isBlank()` mà chưa xét null | Có thể ném `NullPointerException` ngoài ý định | Kiểm tra null trước, hoặc dùng `Objects.requireNonNull` có chủ đích |
| Dùng giá trị mặc định của Java như state hợp lệ | `null`, 0, false có thể trái nghiệp vụ | Khởi tạo tường minh và kiểm tra |
| Cho mọi null thành default | Che dữ liệu sai, khó debug | Tách bắt buộc và tùy chọn |
| Validate từng tham số mà bỏ quan hệ giữa chúng | Ngày kết thúc trước ngày bắt đầu vẫn lọt qua | Kiểm tra invariant liên trường |
| Constructor overload validate khác nhau | Cùng class nhưng có đường tạo object sai | Ủy quyền đến constructor chính |
| Lưu thẳng tham chiếu mutable đầu vào | Caller có thể phá invariant sau constructor | Defensive copy và hợp đồng ownership |
| Trả thẳng mảng/list mutable nội bộ | Caller sửa state mà không qua method | Trả bản sao hoặc unmodifiable view phù hợp |
| Nuốt exception rồi tiếp tục khởi tạo | Không thể tin object khi tạo thành công | Để exception lan ra hoặc khôi phục theo hợp đồng rõ |
| Ghi dữ liệu ngoài rồi mới validate | Constructor thất bại nhưng side effect vẫn tồn tại | Validate sớm, tách giao dịch khỏi constructor |
| Công bố `this` trước khi xong | Mã khác thấy object chưa khởi tạo xong | Chỉ publish sau thành công |
| Gọi overridable method trong superclass constructor | Có thể đọc field subclass ở giá trị mặc định | Tránh dynamic dispatch trong giai đoạn khởi tạo |
| Xóa thông tin cause khi bọc exception | Khó chẩn đoán lỗi gốc | Giữ cause nếu tạo exception mới |
| Dùng checked exception tùy tiện cho mọi input sai | Caller bị ép xử lý không cần thiết | Dùng exception theo hợp đồng và ý nghĩa lỗi |
| Chỉ test ca hợp lệ | Không phát hiện input sai được chấp nhận | Test invalid/boundary/aliasing |

## 19. Bài tập áp dụng

### Bài 1 — Sửa constructor chưa an toàn

Cho class:

~~~java
class Product {
    String code;
    int quantity;

    Product(String code, int quantity) {
        this.code = code;
        this.quantity = quantity;
    }
}
~~~

Hãy sửa để:

- `code` bắt buộc khác null, sau `strip()` không rỗng.
- `quantity` phải lớn hơn 0.
- Các field là `private`, có `final` nếu không cần thay đổi.
- `new Product(" P01 ", 2)` lưu code chuẩn hóa `P01`.
- `new Product("", 2)`, `new Product(null, 2)` và `new Product("P01", 0)` bị từ chối đúng loại exception theo hợp đồng bạn chọn.

### Bài 2 — Tách kiểm tra khỏi I/O

Một constructor vừa nhận email, ghi bản ghi vào database và gửi thư xác nhận. Đặt câu hỏi: Nếu email sai, việc ghi database đã xảy ra chưa? Nếu gửi thư thất bại, object đã có được trả về chưa? Đề xuất cách tạo `RegistrationRequest` hợp lệ trong bộ nhớ rồi để một service thực hiện giao dịch bên ngoài, có chiến lược rollback/retry phù hợp.

### Bài 3 — Kiểm tra khoảng thời gian

Viết `TimeWindow(LocalTime start, LocalTime end)` với chính sách cho phép hay không cho phép khoảng chạy qua nửa đêm. Nếu không cho phép, kiểm tra `end` không đứng trước `start`. Nếu cho phép, phải định nghĩa rõ liệu end của ngày kế tiếp được hiểu như thế nào — chỉ so sánh `LocalTime` có thể không đủ. Đây là bài tập chọn **đúng invariant nghiệp vụ**, không chỉ thêm `if`.

### Bài 4 — Defensive copy của mảng

Viết `ExamScores(int[] scores)`:

- Không cho `scores == null`.
- Không cho mảng rỗng nếu nghiệp vụ yêu cầu ít nhất một điểm.
- Mỗi điểm phải nằm trong khoảng `0..100`.
- Constructor tạo bản sao mảng.
- Accessor không trả trực tiếp mảng nội bộ.

Thử sửa mảng nguồn và mảng từ accessor, rồi giải thích vì sao state của object không đổi.

### Bài 5 — Constructor chaining

Tạo `Ticket(String code)` và `Ticket(String code, int quantity)` sao cho mọi đường đều validate `code` và `quantity`. Dự đoán chuyện gì xảy ra nếu overload một tham số chỉ gán field riêng mà bỏ kiểm tra. Đặt quy tắc tập trung ở constructor chính và kiểm thử cả hai overload.

### Bài 6 — Đường thất bại và tham chiếu cũ

Tạo một object `Account current` hợp lệ, sau đó thử `current = new Account(" ", 10)` trong `try-catch`. Hãy chứng minh `current` vẫn trỏ object ban đầu khi constructor mới ném exception. Phân biệt **không hoàn tất phép gán** với **rollback toàn bộ side effect**.

## 20. Checklist cuối bài

- [ ] Tôi giải thích được vì sao object hoàn tất tạo thành công nên thỏa invariant của class.
- [ ] Tôi phân biệt kiểm tra `null`, chuỗi rỗng, chuỗi blank và chuẩn hóa.
- [ ] Tôi biết khi nào nên ném `IllegalArgumentException` hoặc dùng `Objects.requireNonNull`.
- [ ] Tôi biết điều kiện của từng tham số chưa đủ nếu các tham số có quan hệ với nhau.
- [ ] Tôi hiểu constructor thất bại khiến biểu thức `new` không trả reference bình thường cho caller.
- [ ] Tôi biết phép gán của caller không xảy ra nếu vế phải `new` ném exception.
- [ ] Tôi không giả định side effect đã thực hiện được rollback tự động.
- [ ] Tôi tránh công bố `this` khi object chưa được khởi tạo xong.
- [ ] Tôi tránh gọi method có thể override trong constructor khi nó có thể đọc state subclass chưa sẵn sàng.
- [ ] Tôi biết truyền mảng/list mutable vào constructor có thể làm rò rỉ quyền sửa state và biết dùng defensive copy.
- [ ] Tôi áp dụng validation nhất quán qua các constructor overload và `this(...)`.
- [ ] Tôi phân biệt invariant nội tại với kiểm tra trạng thái hệ thống thay đổi theo thời gian.
- [ ] Tôi biết kiểm tra cả ca hợp lệ, biên, lỗi và aliasing.
- [ ] Tôi tự biên dịch/chạy các ví dụ Java 17+ và giải thích output dựa trên state, exception và thời điểm khởi tạo.

**Kết luận:** Constructor là điểm thiết lập một object hợp lệ, không phải chỗ “nuốt” dữ liệu sai hoặc thực hiện mọi tác vụ ngoại vi. Hãy **xác định invariant → validate đầu vào → chuẩn hóa/copy khi cần → gán trạng thái → hoàn tất khởi tạo**. Nếu điều kiện không đạt, báo lỗi rõ ràng để `new` không cung cấp một object không hợp lệ theo đường thành công. Cùng với các phương thức cập nhật giữ invariant, cách này giúp class dễ sử dụng, dễ kiểm thử và ít phát sinh trạng thái khó chẩn đoán.
