# Không dùng `assert` thay kiểm tra đầu vào công khai trong Java

Trong Java, `assert` là công cụ chẩn đoán những giả định mà chương trình **đáng lẽ luôn bảo đảm đúng bằng logic nội bộ**. Nó **không phải** cơ chế kiểm tra dữ liệu người dùng, tham số của phương thức `public`, constructor công khai hoặc dữ liệu từ file, mạng và cơ sở dữ liệu. Lý do quan trọng nhất: **assertion có thể bị vô hiệu hóa khi chạy**, khiến toàn bộ câu lệnh `assert` không có tác dụng và **không đánh giá cả biểu thức điều kiện lẫn thông báo**.

Ví dụ không đúng:

~~~java
public void setAge(int age) {
    assert age >= 0 : "age must be non-negative";
    this.age = age;
}
~~~

Đây là đoạn **minh họa trong một lớp có trường `age`**. Nếu chương trình chạy không bật assertions, giá trị âm vẫn có thể được gán vào trường. Nếu bật assertions, lỗi phát sinh là `AssertionError` thuộc nhánh `Error`, thay vì ngoại lệ tham số không hợp lệ thông thường mà người gọi API có thể dự kiến.

Cách phù hợp cho một public API:

~~~java
public void setAge(int age) {
    if (age < 0) {
        throw new IllegalArgumentException("age must be non-negative");
    }
    this.age = age;
}
~~~

Kiểm tra bằng `if` **luôn thực thi** khi phương thức được gọi, bất kể trạng thái bật/tắt assertions. Đây là cơ sở của hợp đồng API: đầu vào sai phải được từ chối một cách nhất quán ở mọi môi trường triển khai.

Bài học này trình bày quy tắc của JLS §14.10, cách chạy `-ea`/`-da`, phân biệt `AssertionError` và `IllegalArgumentException`/`NullPointerException`, cách kiểm tra public constructor, record, collection index, phương thức sửa trạng thái; khi nào `assert` vẫn hữu ích cho **internal invariant**; vì sao không đặt side effect trong assertions; và các ví dụ Java 17+ có stdout rõ ràng.

## 1. `assert` trong Java thực sự làm gì?

Java có hai dạng:

~~~java
assert condition;
assert condition : detailExpression;
~~~

Đây là hai **mẫu cú pháp minh họa**, với `condition` là biểu thức kiểu `boolean` hoặc `Boolean` và `detailExpression` là biểu thức phù hợp làm detail message.

Theo JLS §14.10:

1. Nếu assertion **bị tắt**, toàn bộ câu lệnh hoàn tất bình thường; **không đánh giá** điều kiện hoặc biểu thức sau dấu hai chấm.
2. Nếu assertion **được bật**, Java đánh giá điều kiện.
3. Nếu điều kiện trả `true`, câu lệnh hoàn tất bình thường; biểu thức detail sau dấu hai chấm **không được đánh giá**.
4. Nếu điều kiện trả `false`, Java đánh giá detail expression nếu có, tạo một đối tượng `AssertionError` rồi ném nó.
5. Nếu chính việc đánh giá điều kiện hoặc detail expression ném lỗi, câu lệnh có thể kết thúc bằng lỗi đó trước khi tạo `AssertionError` theo đường thông thường.

Vì thế, `assert` là một **khẳng định có thể tắt bằng cấu hình chạy**, không phải một điều kiện `if` bắt buộc.

| Cấu trúc | Khi điều kiện đúng | Khi điều kiện sai | Có thể bị JVM bỏ qua theo assertion status? |
| --- | --- | --- | --- |
| `assert x > 0;` | Tiếp tục | `AssertionError` nếu được bật | **Có** |
| `if (x <= 0) throw new IllegalArgumentException(...);` | Tiếp tục | `IllegalArgumentException` | **Không** |
| `Objects.requireNonNull(value);` | Trả lại chính tham chiếu khác `null` | `NullPointerException` | **Không** |
| `Objects.checkIndex(index, length);` | Trả chỉ số hợp lệ | `IndexOutOfBoundsException` | **Không** |

Một `assert` được biên dịch hợp lệ không đồng nghĩa nó được thực thi trong bản chạy thực tế. Ngược lại, một điều kiện `if` hoặc lời gọi `Objects.requireNonNull` là mã thực thi bình thường, không phụ thuộc vào cờ bật assertion.

## 2. Bật và tắt assertions bằng `java -ea` và `java -da`

Trong JVM thông thường, assertions của các lớp ứng dụng mặc định **không được bật**, trừ khi có cấu hình từ launcher, class loader hoặc API liên quan. Các lệnh quen thuộc:

~~~bash
javac -encoding UTF-8 MyProgram.java
java -da MyProgram
java -ea MyProgram
~~~

Ý nghĩa:

- `-ea` hoặc `-enableassertions`: bật assertions theo phạm vi được chỉ định; dạng không có hậu tố dùng làm mặc định cho các lớp ứng dụng được áp dụng.
- `-da` hoặc `-disableassertions`: tắt assertions trong phạm vi tương ứng.
- JVM có thể cấu hình **theo lớp hoặc package**, không nhất thiết mọi lớp đều có cùng trạng thái. Ngoài cờ launcher, class loader có các API thiết lập trạng thái mong muốn cho những lớp sẽ được khởi tạo.
- Cấu hình khẳng định thường được quyết định khi lớp được khởi tạo. Không thiết kế logic nghiệp vụ dựa trên việc thay đổi bật/tắt assertions giữa hai lời gọi của cùng một lớp.

**Cờ JVM phải đặt trước tên class**: `java -ea MyProgram`, không phải `java MyProgram -ea`. Trong lệnh thứ hai, `-ea` chỉ là phần tử của `String[] args` dành cho chương trình, không phải tùy chọn JVM.

Khi kiểm thử, chạy cả hai chế độ giúp phát hiện lỗi kiểu “có bật assertions thì từ chối dữ liệu, còn tắt thì âm thầm chấp nhận”. Tuy nhiên, test nên nhấn mạnh **cùng một hợp đồng đầu vào cho cả hai chế độ**, không coi `-ea` là một yêu cầu bắt buộc ở production để tránh lỗi.

## 3. Ví dụ 1: mã sai cho phép dữ liệu không hợp lệ khi assertions tắt

Lưu thành `BadPublicAssertDemo.java`:

~~~java
public class BadPublicAssertDemo {
    static String acceptAmount(int amount) {
        assert amount > 0 : "amount must be positive";
        return "accepted:" + amount;
    }

    public static void main(String[] args) {
        try {
            System.out.println(acceptAmount(-4));
        } catch (AssertionError ex) {
            System.out.println("error=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy hai lần:

~~~bash
javac -encoding UTF-8 BadPublicAssertDemo.java
java -da BadPublicAssertDemo
java -ea BadPublicAssertDemo
~~~

Đầu ra của **lần chạy `-da`**:

~~~text
accepted:-4
~~~

Đầu ra của **lần chạy `-ea`**:

~~~text
error=AssertionError
~~~

Cùng mã nguồn và cùng tham số `-4` nhưng hai kết quả khác nhau:

1. Khi tắt assertion, kiểm tra bị bỏ qua và chương trình tạo kết quả **accepted:-4**, vi phạm tiền điều kiện dự kiến.
2. Khi bật assertion, điều kiện sai tạo `AssertionError`. Chương trình cố ý bắt loại này để minh họa đầu ra, **không khuyến nghị bắt AssertionError để xử lý nhập liệu thông thường**.
3. Nếu `acceptAmount` là API công khai, người gọi không nên phải biết chương trình của họ đang bật `-ea` hay không để dự đoán API có từ chối giá trị âm.

Đây là lý do không dùng `assert` cho tham số của `public` method hoặc public constructor, đặc biệt khi đầu vào đến từ một người gọi, module, thư viện hoặc dịch vụ khác.

## 4. Phải kiểm tra public precondition bằng luồng thực thi bắt buộc

Một public method có **tiền điều kiện** (*precondition*): ví dụ `quantity > 0`, `name != null`, `index >= 0`. Tiền điều kiện là phần của hợp đồng mà người gọi được biết. Nếu vi phạm, method phải đáp ứng chính sách đã công bố, chẳng hạn ném `IllegalArgumentException`.

Cách viết:

~~~java
public static int calculateCharge(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity must be positive");
    }
    return quantity * 10;
}
~~~

Đây là phương thức minh họa đặt trong một lớp Java; số học chỉ nhằm cho thấy điều kiện. Nếu sản phẩm `quantity * 10` có thể overflow trong ứng dụng thực tế, cần kiểm tra thêm, ví dụ `Math.multiplyExact`.

**Điều kiện không phụ thuộc `-ea`** và được thực thi trước khi method trả kết quả. Có thể dùng helper để tái sử dụng, nhưng helper phải là mã bình thường, không giấu trong assert expression.

### Ví dụ 2: public guard ổn định ở mọi chế độ

Lưu thành `PublicGuardDemo.java`:

~~~java
import java.util.Objects;

public class PublicGuardDemo {
    static String register(String name, int age) {
        Objects.requireNonNull(name, "name");

        if (name.isBlank()) {
            throw new IllegalArgumentException("name blank");
        }
        if (age < 0 || age > 150) {
            throw new IllegalArgumentException("age out of range");
        }
        return "registered:" + name + ":" + age;
    }

    static void show(String name, int age) {
        try {
            System.out.println(register(name, age));
        } catch (RuntimeException ex) {
            System.out.println("error="
                    + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        show("Ada", 36);
        show("", 36);
        show("Ada", -1);
        show(null, 20);
    }
}
~~~

~~~bash
javac -encoding UTF-8 PublicGuardDemo.java
java -da PublicGuardDemo
java -ea PublicGuardDemo
~~~

**Cả hai lần chạy đều in cùng một kết quả**:

~~~text
registered:Ada:36
error=IllegalArgumentException:name blank
error=IllegalArgumentException:age out of range
error=NullPointerException:name
~~~

Ở đây:

- `Objects.requireNonNull(name, "name")` dùng để báo **tham chiếu bắt buộc không được null**.
- `name.isBlank()` kiểm tra yêu cầu chuỗi không rỗng/không chỉ chứa whitespace; việc đó khác với kiểm tra null.
- `age` được kiểm tra theo miền nghiệp vụ.
- `RuntimeException` được bắt trong **demo để in tên loại lỗi**, không phải khuyến nghị catch rộng cho một service thật.
- Dù assertions được bật hay tắt, kết quả validation không thay đổi vì mã bảo vệ là luồng điều khiển thông thường.

Đây là dạng hành vi ổn định mà một public API cần cung cấp.

## 5. `AssertionError` không phải `IllegalArgumentException`

Cả hai đều là hậu duệ của `Throwable`, nhưng thuộc **nhánh khác nhau**:

~~~text
Throwable
 ├── Error
 │    └── AssertionError
 └── Exception
      └── RuntimeException
           ├── IllegalArgumentException
           ├── IllegalStateException
           ├── NullPointerException
           └── IndexOutOfBoundsException
~~~

Ý nghĩa sử dụng:

| Loại | Ngữ cảnh thích hợp |
| --- | --- |
| `AssertionError` | Giả định nội bộ bị phá vỡ, thường phản ánh bug và cần sửa code |
| `IllegalArgumentException` | Người gọi truyền một giá trị tham số không hợp lệ |
| `NullPointerException` | Tham chiếu không được phép null; `Objects.requireNonNull` hỗ trợ rõ ràng |
| `IllegalStateException` | Đối tượng ở trạng thái không cho phép thực hiện thao tác |
| `IndexOutOfBoundsException` | Chỉ số hoặc khoảng chỉ số không hợp lệ |
| Custom domain exception | Khi API cần lỗi có ý nghĩa riêng, mã lỗi/thuộc tính hoặc chính sách checked/unchecked rõ |

**AssertionError thuộc Error**, không phải Exception. Vì vậy `catch (Exception ex)` không bắt `AssertionError`. Có thể viết `catch (Throwable ex)` hoặc `catch (AssertionError ex)`, nhưng bắt rộng như vậy để che lỗi khẳng định trong vận hành thường sai mục tiêu: cần sửa bug nội bộ hơn là giả vờ đầu vào đã được xử lý.

Không nên ném `AssertionError` bằng tay khi phát hiện lỗi người dùng. Nếu người dùng nhập số lượng âm, đó là dữ liệu vi phạm hợp đồng, không nhất thiết là một lỗi trong implementation của chương trình.

## 6. Cảnh báo: `assert` có thể bị bỏ qua cả biểu thức có side effect

Theo JLS §14.10, một assertion bị vô hiệu hóa **không đánh giá** biểu thức điều kiện. Nếu expression gọi phương thức có side effect, trạng thái chương trình có thể khác nhau giữa hai chế độ chạy.

### Ví dụ 3: side effect bị mất khi assertions tắt

Lưu thành `AssertSideEffectDemo.java`:

~~~java
public class AssertSideEffectDemo {
    static int calls = 0;

    static boolean incrementAndReportTrue() {
        calls++;
        return true;
    }

    public static void main(String[] args) {
        assert incrementAndReportTrue();
        System.out.println("calls=" + calls);
    }
}
~~~

~~~bash
javac -encoding UTF-8 AssertSideEffectDemo.java
java -da AssertSideEffectDemo
java -ea AssertSideEffectDemo
~~~

Đầu ra với `-da`:

~~~text
calls=0
~~~

Đầu ra với `-ea`:

~~~text
calls=1
~~~

Không có `AssertionError` ở cả hai trường hợp vì phương thức trả `true`, nhưng trạng thái `calls` khác nhau. Việc đặt thao tác ghi log, gán biến, đọc file hoặc gọi API có tác dụng phụ vào điều kiện `assert` có thể làm môi trường test và production đi theo hai đường điều khiển khác nhau.

**Nguyên tắc:** điều kiện của `assert` và biểu thức sau dấu hai chấm nên **không gây side effect có ý nghĩa với chương trình**. Nếu một thao tác cần chạy, hãy thực hiện nó bằng câu lệnh bình thường trước, rồi dùng `assert` để kiểm tra giả định trên kết quả.

Ví dụ đúng hơn:

~~~java
int updated = updateState();
assert updated >= 0 : "internal invariant";
~~~

Đây là đoạn minh họa trong một method có `updateState()` phù hợp. `updateState()` luôn chạy; câu `assert` chỉ quan sát kết quả đã có. Tuy nhiên, nếu `updated >= 0` là điều kiện bắt buộc cho dữ liệu công khai thì vẫn phải dùng kiểm tra không tắt được, không chỉ assert.

## 7. Biểu thức thông báo sau dấu hai chấm cũng có điều kiện thực thi

Dạng `assert condition : detailExpression;` không đánh giá detailExpression trong mọi lần:

- Assertions **tắt**: cả hai biểu thức đều không được đánh giá.
- Assertions **bật và condition đúng**: chỉ đánh giá condition; không đánh giá detailExpression.
- Assertions **bật và condition sai**: đánh giá cả hai, rồi thông thường tạo `AssertionError` với detail message.

Điều này hữu ích khi message chẩn đoán tốn chi phí tạo: thông tin chi tiết chỉ được tính khi invariant sai. Nhưng detail expression vẫn nên an toàn, không thay đổi state hoặc làm lỗi thêm rối rắm.

### Ví dụ 4: đánh giá detail lazily

Lưu thành `LazyAssertDetailDemo.java`:

~~~java
public class LazyAssertDetailDemo {
    static int descriptions = 0;

    static String describe(int value) {
        descriptions++;
        return "internal value=" + value;
    }

    public static void main(String[] args) {
        int x = -2;

        try {
            assert x >= 0 : describe(x);
            System.out.println("accepted=" + x);
        } catch (AssertionError ex) {
            System.out.println("error=" + ex.getMessage());
        }

        System.out.println("descriptions=" + descriptions);
    }
}
~~~

~~~bash
javac -encoding UTF-8 LazyAssertDetailDemo.java
java -da LazyAssertDetailDemo
java -ea LazyAssertDetailDemo
~~~

Kết quả khi `-da`:

~~~text
accepted=-2
descriptions=0
~~~

Kết quả khi `-ea`:

~~~text
error=internal value=-2
descriptions=1
~~~

Ví dụ có tăng bộ đếm chỉ để **quan sát chính xác việc đánh giá**. Trong mã production, tránh thiết kế `describe` gây thay đổi state; đó nên là chức năng chỉ tạo mô tả an toàn cho điều kiện chẩn đoán.

Đừng dùng biểu thức sau dấu hai chấm để sửa dữ liệu, đặt giao dịch, giải phóng tài nguyên hoặc phát tín hiệu nghiệp vụ. Mọi thao tác bắt buộc phải chạy độc lập với trạng thái bật/tắt assertions.

## 8. Public constructor cũng là ranh giới đầu vào

Constructor có thể nhận đầu vào không tin cậy từ module khác. Nếu chỉ viết:

~~~java
public Account(String id) {
    assert id != null;
    this.id = id;
}
~~~

Đây là đoạn minh họa trong lớp `Account` có trường `id`. Khi assertions tắt, đối tượng vẫn có thể được tạo với `id == null`, để rồi nhiều phương thức khác gặp NullPointerException muộn tại vị trí khó chẩn đoán.

Cách an toàn là kiểm tra ngay lúc khởi tạo:

~~~java
public Account(String id) {
    this.id = java.util.Objects.requireNonNull(id, "id");
}
~~~

Nếu còn điều kiện như không rỗng, không có dấu cách, hoặc ID phải đúng dạng thì thêm kiểm tra bằng `if`. Bảo đảm constructor **không trả một đối tượng ở trạng thái không hợp lệ** theo hợp đồng.

### Ví dụ 5: validation trong constructor

Lưu thành `ConstructorGuardDemo.java`:

~~~java
import java.util.Objects;

public class ConstructorGuardDemo {
    static final class Account {
        private final String id;

        Account(String id) {
            Objects.requireNonNull(id, "id");
            if (id.isBlank()) {
                throw new IllegalArgumentException("id blank");
            }
            this.id = id;
        }

        String id() {
            return id;
        }
    }

    public static void main(String[] args) {
        System.out.println("ok=" + new Account("U-7").id());

        try {
            new Account(null);
        } catch (NullPointerException ex) {
            System.out.println("null=" + ex.getClass().getSimpleName());
        }

        try {
            new Account("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("blank=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorGuardDemo.java
java -da ConstructorGuardDemo
java -ea ConstructorGuardDemo
~~~

Kết quả **giống nhau ở cả hai chế độ**:

~~~text
ok=U-7
null=NullPointerException
blank=IllegalArgumentException
~~~

Constructor từ chối input không phù hợp ngay nơi tạo đối tượng, thay vì chấp nhận một object không đạt invariant rồi để lỗi phát sinh về sau. Đây là khác biệt giữa **giữ invariant bằng validation bắt buộc** và chỉ **khẳng định rằng invariant đã đúng**.

Khi kế thừa, constructor Java 17 yêu cầu lời gọi explicit `super(...)` hoặc `this(...)` đặt đầu constructor theo quy tắc ngôn ngữ. Nếu cần xác thực tham số trước khi truyền vào constructor lớp cha, có thể dùng biểu thức helper trong tham số của `super(...)`, ví dụ `super(Objects.requireNonNull(value, "value"))`, thay vì cố đặt lệnh `if` trước một `super(...)` explicit trong Java 17.

## 9. Record và immutable object cũng phải kiểm tra trước khi lưu

Java 17 hỗ trợ `record` để mang dữ liệu bất biến ở mức các component. Nhưng từ khóa record **không tự xác thực** `null`, số âm, chuỗi rỗng hoặc giá trị vượt miền. Cần kiểm tra trong constructor khi hợp đồng yêu cầu.

### Ví dụ 6: compact constructor của record

Lưu thành `RecordGuardDemo.java`:

~~~java
import java.util.Objects;

public class RecordGuardDemo {
    record OrderLine(String sku, int quantity) {
        OrderLine {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank()) {
                throw new IllegalArgumentException("sku blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
        }
    }

    public static void main(String[] args) {
        OrderLine valid = new OrderLine("SKU-1", 3);
        System.out.println("valid="
                + valid.sku() + ":" + valid.quantity());

        try {
            new OrderLine("SKU-2", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("quantity="
                    + ex.getClass().getSimpleName());
        }

        try {
            new OrderLine(null, 2);
        } catch (NullPointerException ex) {
            System.out.println("sku="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 RecordGuardDemo.java
java -da RecordGuardDemo
java -ea RecordGuardDemo
~~~

Kết quả cả hai chế độ:

~~~text
valid=SKU-1:3
quantity=IllegalArgumentException
sku=NullPointerException
~~~

Compact constructor kiểm tra tham số trước khi record lưu component. Không phải vì dữ liệu bất biến mà validation có thể bỏ qua; một giá trị không hợp lệ nếu được lưu sẽ **khó sửa sau khi đối tượng được tạo**.

Nếu record mang collection có thể thay đổi, còn cần cân nhắc defensive copy (ví dụ `List.copyOf`) và chính sách phần tử null; `assert` cũng không thay được những bước bảo vệ dữ liệu này.

## 10. Chọn ngoại lệ cho từng loại điều kiện công khai

Không phải mọi lỗi đầu vào đều nên ném một ngoại lệ giống nhau. Chọn theo **hợp đồng** của API và hoàn cảnh sử dụng:

| Điều kiện | Loại thường phù hợp | Ví dụ |
| --- | --- | --- |
| Tham số số học không đúng miền | `IllegalArgumentException` | amount <= 0 |
| Tham số tham chiếu bắt buộc không null | `NullPointerException` qua `Objects.requireNonNull` | customerId == null |
| Chỉ số ngoài kích thước danh sách | `IndexOutOfBoundsException` | index < 0 hoặc index >= size |
| Thao tác ở trạng thái đối tượng không cho phép | `IllegalStateException` | gọi mutate sau khi close |
| Văn bản số không thể chuyển sang int | `NumberFormatException` | parseInt("foo") |
| Đầu vào dạng ngày không parse được | `DateTimeParseException` | LocalDate.parse("bad") |
| Dữ liệu có lỗi nghiệp vụ cần phản hồi theo field/code | Custom exception hoặc validation result | INVALID_QUANTITY |
| Giả định nội bộ bị phá vỡ dù input public đã được kiểm tra | `AssertionError` khi assertion được bật | postcondition đáng lẽ luôn đúng |

Bảng này là **quy ước thiết kế thường dùng**, không phải danh sách duy nhất có thể áp dụng. Một API có thể chọn custom exception hoặc một kiểu `Result<T>` có thông tin lỗi. Quan trọng nhất: hành vi khi đầu vào công khai không hợp lệ phải **được thực thi nhất quán**, có ý nghĩa cho bên gọi và được tài liệu hóa.

Không tự động dùng `AssertionError` chỉ vì một điều kiện “không nên xảy ra”. Nếu điều kiện do **caller có thể gây ra bằng tham số công khai**, hãy dùng validation. Nếu điều kiện biểu diễn **lỗi của implementation** mà logic nội bộ đã cam kết ngăn, assertion có thể là công cụ chẩn đoán bổ trợ.

## 11. Kiểm tra collection index: không dùng `assert index >= 0`

Với public method truy cập danh sách, chỉ kiểm tra `index >= 0` là chưa đủ: chỉ số còn phải nhỏ hơn kích thước. Nếu dùng `assert`, khi assertion tắt có thể truy cập chỉ số sai rồi nhận lỗi sâu hơn hoặc thậm chí thực thi logic không mong đợi trước khi lỗi xuất hiện.

JDK cung cấp các helper:

- `Objects.checkIndex(index, length)` xác thực chỉ số đơn.
- `Objects.checkFromToIndex(from, to, length)` xác thực phạm vi dạng [from, to).
- `Objects.checkFromIndexSize(from, size, length)` xác thực phạm vi theo điểm đầu và độ dài.

Các API này ném `IndexOutOfBoundsException` khi tham số sai; không phụ thuộc `-ea`.

### Ví dụ 7: helper kiểm tra chỉ số

Lưu thành `IndexGuardDemo.java`:

~~~java
import java.util.List;
import java.util.Objects;

public class IndexGuardDemo {
    static String read(List<String> items, int index) {
        Objects.requireNonNull(items, "items");
        int checked = Objects.checkIndex(index, items.size());
        return items.get(checked);
    }

    public static void main(String[] args) {
        List<String> data = List.of("A", "B");

        System.out.println("ok=" + read(data, 1));

        try {
            read(data, 2);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("index="
                    + ex.getClass().getSimpleName());
        }

        try {
            read(null, 0);
        } catch (NullPointerException ex) {
            System.out.println("list="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 IndexGuardDemo.java
java -da IndexGuardDemo
java -ea IndexGuardDemo
~~~

Kết quả cả hai chế độ:

~~~text
ok=B
index=IndexOutOfBoundsException
list=NullPointerException
~~~

Lợi ích của validation gần ranh giới: caller nhận lỗi của **điều kiện hợp đồng sai**, thay vì chờ một thao tác sâu hơn vô tình ném lỗi có ít ngữ cảnh hơn.

## 12. Invalid input khác invalid state

Một phương thức có thể có cả **tiền điều kiện tham số** và **tiền điều kiện trạng thái đối tượng**. Cả hai phải được kiểm tra bằng code thực thi bình thường nếu vi phạm có thể phát sinh trong những tình huống dự kiến của API.

Ví dụ một tài khoản:

- `withdraw(amount)` với `amount <= 0`: tham số sai → `IllegalArgumentException`.
- Tài khoản đã đóng: đối tượng không ở trạng thái cho phép rút tiền → `IllegalStateException`.
- Sau khi kiểm tra và cập nhật, `balance >= 0` có thể là một **invariant nội bộ** để dùng thêm `assert` trong debug. Nhưng logic cần **bảo đảm** invariant ngay cả khi assertions tắt.

### Ví dụ 8: validation và invariant bổ trợ

Lưu thành `StateContractDemo.java`:

~~~java
public class StateContractDemo {
    static final class Account {
        private int balance;
        private boolean closed;

        Account(int initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException(
                        "initial balance negative");
            }
            balance = initialBalance;
        }

        void withdraw(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException(
                        "amount must be positive");
            }
            if (closed) {
                throw new IllegalStateException("account closed");
            }
            if (amount > balance) {
                throw new IllegalStateException("insufficient balance");
            }

            balance -= amount;
            assert balance >= 0 : "internal negative balance";
        }

        void close() {
            closed = true;
        }

        int balance() {
            return balance;
        }
    }

    public static void main(String[] args) {
        Account account = new Account(10);
        account.withdraw(4);
        System.out.println("balance=" + account.balance());

        try {
            account.withdraw(-2);
        } catch (IllegalArgumentException ex) {
            System.out.println("argument="
                    + ex.getClass().getSimpleName());
        }

        account.close();
        try {
            account.withdraw(1);
        } catch (IllegalStateException ex) {
            System.out.println("state="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("final=" + account.balance());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StateContractDemo.java
java -da StateContractDemo
java -ea StateContractDemo
~~~

Kết quả giống nhau ở cả hai chế độ:

~~~text
balance=6
argument=IllegalArgumentException
state=IllegalStateException
final=6
~~~

Ở đây, `assert balance >= 0` chỉ là **dấu hiệu chẩn đoán bổ sung** sau khi thuật toán đã kiểm tra amount và số dư để tránh giá trị âm. Dù tắt assertion, object vẫn không thể bị rút âm thông qua các đường API hợp lệ của ví dụ. Điều đó đúng với vai trò kiểm tra invariant nội bộ: **không dùng assert làm lớp bảo vệ duy nhất**.

Lưu ý trong hệ thống đa luồng, cần xem xét đồng bộ/trạng thái giao dịch nếu nhiều thread cùng sửa balance. Một `assert` không tự tạo atomicity hay thread safety.

## 13. Vị trí thích hợp của `assert`: invariant do code nội bộ kiểm soát

Một assertion phù hợp thường diễn đạt điều mà **implementation đã bảo đảm** chứ không đòi hỏi caller phải bảo đảm. Ví dụ, sau một thuật toán sắp xếp hoặc một nhánh xử lý enum nội bộ, ta có thể khẳng định một thuộc tính không thể sai nếu code không có bug.

Mẫu trong một phương thức:

~~~java
Result result = algorithm(validatedInput);
assert result != null : "algorithm violated its postcondition";
return result;
~~~

Đây là **mã minh họa không độc lập**: giả định `Result`, `algorithm` và `validatedInput` được định nghĩa. Nếu result != null là điều kiện không thể thiếu cho hành vi đúng, logic sản xuất vẫn phải có cách xử lý hoặc thiết kế để không tạo trạng thái không hợp lệ khi assertion bị tắt.

Các điểm có thể phù hợp cho assertion trong nội bộ:

- Kiểm tra một quan hệ toán học mà thuật toán luôn phải duy trì.
- Kiểm tra một trạng thái nhánh private không thể xảy ra nếu switch/dispatch đã xử lý toàn bộ trường hợp.
- Kiểm tra tính nhất quán của cấu trúc dữ liệu sau thao tác mà public API đã xác thực.
- Gắn thông báo debug có ngữ cảnh khi một invariant được vi phạm.

**Nhưng “private” không tự động làm mọi precondition thành invariant.** Một private method nếu nhận chuỗi thô từ network hoặc dữ liệu chưa được validate cũng không nên dựa vào `assert` cho điều kiện bắt buộc. Tiêu chí là **ai bảo đảm điều kiện và liệu nó có thể bị vi phạm bởi đầu vào hợp lệ của hệ thống**.

## 14. Đừng lấy `assert` làm điều kiện trước khi có side effect nguy hiểm

Một pattern rủi ro:

~~~java
public void transfer(int amount) {
    assert amount > 0;
    debit(amount);
    credit(amount);
}
~~~

Đây là ví dụ minh họa không độc lập, giả định `debit` và `credit` tồn tại. Nếu asserts bị tắt, mã có thể tiến hành thao tác bất hợp lệ trước khi phát hiện vấn đề hoặc có thể gây lỗi ở một bước giữa chừng. Đối với tiền, tồn kho, quyền truy cập hoặc tài nguyên, việc **kiểm tra đầu vào trước side effects** là một phần thiết yếu của thiết kế.

Mẫu đúng hơn:

~~~java
public void transfer(int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException(
                "amount must be positive");
    }
    debit(amount);
    credit(amount);
}
~~~

Hai đoạn chỉ để so sánh validation; một thao tác chuyển tiền thật cần thêm các yêu cầu như kiểm tra quyền truy cập, số dư, tính nguyên tử/transaction và xử lý lỗi hệ thống. `if` ở đây là điều kiện cần, không khẳng định code minh họa là implementation tài chính đầy đủ.

Nếu nhận dữ liệu từ request, hãy parse và validate ở **ranh giới tin cậy** trước khi thực hiện tác dụng phụ. Assertions dùng cho debug ở các bước nội bộ không thể thay các rào chắn này.

## 15. Lỗi parse nhập liệu không nên được “kiểm tra bằng assert”

Một số giá trị đến từ chuỗi: số lượng trong URL, ID, ngày từ CSV. Ví dụ:

~~~java
int amount = Integer.parseInt(rawAmount);
assert amount > 0;
~~~

Đây là đoạn minh họa. Có hai loại lỗi khác nhau:

1. Nếu rawAmount không thể biểu diễn một số int, `Integer.parseInt` ném **NumberFormatException**.
2. Nếu rawAmount parse được nhưng giá trị không dương, `assert` có thể **không chạy**, khiến dữ liệu vượt qua tiền điều kiện.

Cách tốt hơn là biểu diễn cả hai bước rõ ràng:

### Ví dụ 9: parse và validation với cause

Lưu thành `InputBoundaryDemo.java`:

~~~java
import java.util.Objects;

public class InputBoundaryDemo {
    static int parseQuantity(String raw) {
        Objects.requireNonNull(raw, "quantity");

        final int quantity;
        try {
            quantity = Integer.parseInt(raw);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "quantity must be an integer", ex);
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        return quantity;
    }

    static void show(String raw) {
        try {
            System.out.println("quantity=" + parseQuantity(raw));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
            System.out.println("causeIsNFE="
                    + (ex.getCause() instanceof NumberFormatException));
        }
    }

    public static void main(String[] args) {
        show("3");
        show("abc");
        show("-5");
    }
}
~~~

~~~bash
javac -encoding UTF-8 InputBoundaryDemo.java
java -da InputBoundaryDemo
java -ea InputBoundaryDemo
~~~

Kết quả cả hai chế độ:

~~~text
quantity=3
invalid=quantity must be an integer
causeIsNFE=true
invalid=quantity must be positive
causeIsNFE=false
~~~

`InputBoundaryDemo` **không dựa vào assert**; dữ liệu rỗng/sai có thể được phân loại rõ. Với lỗi parse, wrapper chứa nguyên đối tượng `NumberFormatException` làm cause; với số âm, lỗi nghiệp vụ độc lập không cần cause giả.

Lưu ý: phương thức `show` không thử `null` vì đoạn demo này chỉ bắt `IllegalArgumentException`, còn `parseQuantity(null)` dùng `Objects.requireNonNull` và ném `NullPointerException`. Nếu API muốn chuyển mọi dữ liệu không hợp lệ thành một error response chung, hãy tạo tầng mapping rõ ràng chứ không mặc định `IllegalArgumentException` luôn bao trùm NPE.

## 16. Cách viết kiểm thử cho hợp đồng public API

Một unit test có thể dùng thư viện kiểm thử để kiểm tra rằng public method luôn ném một loại lỗi đã định khi được gọi với dữ liệu sai. Đó khác với việc đặt `assert` trong implementation. Với Java không cần framework, có thể viết một helper đơn giản để chứng minh hợp đồng.

### Ví dụ 10: kiểm tra ngoại lệ ở cả `-da` và `-ea`

Lưu thành `GuardContractTestDemo.java`:

~~~java
public class GuardContractTestDemo {
    static int requirePositive(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("value not positive");
        }
        return value;
    }

    static boolean rejects(int value) {
        try {
            requirePositive(value);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    public static void main(String[] args) {
        System.out.println("positive=" + requirePositive(5));
        System.out.println("rejectZero=" + rejects(0));
        System.out.println("rejectNegative=" + rejects(-1));

        if (!rejects(0) || !rejects(-1)) {
            throw new AssertionError("broken public contract");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 GuardContractTestDemo.java
java -da GuardContractTestDemo
java -ea GuardContractTestDemo
~~~

Kết quả giống nhau:

~~~text
positive=5
rejectZero=true
rejectNegative=true
~~~

**Trong test**, câu lệnh `throw new AssertionError(...)` được viết tường minh bằng luồng thực thi bình thường, khác với từ khóa `assert` có thể bị bỏ qua. Nhiều framework unit test cũng dùng AssertionError để báo test fail; đó là vai trò của **kiểm thử**, không phải lý do dùng `assert` cho public preconditions trong code ứng dụng.

Khi dùng JUnit, có thể áp dụng `assertThrows(IllegalArgumentException.class, ...)` để chỉ rõ loại ngoại lệ mong đợi. Không nên chỉ viết `assert condition;` trong test rồi quên bật `-ea` nếu chính test dựa vào từ khóa assert của Java; các assertion methods của framework là API khác với từ khóa `assert` của ngôn ngữ.

## 17. `Objects.requireNonNull`, `checkIndex` và helper riêng: chọn cho đúng

Các helper trong `java.util.Objects` thường tiện cho tham số công khai:

~~~java
String validName =
        java.util.Objects.requireNonNull(name, "name");
int validIndex =
        java.util.Objects.checkIndex(index, count);
~~~

Đây là đoạn mã minh họa trong phương thức nơi `name`, `index` và `count` đã được định nghĩa. Hai thao tác luôn chạy, dù assertions bị tắt.

Phân biệt:

- `requireNonNull` chỉ kiểm tra null; nó **không tự kiểm tra** chuỗi rỗng, whitespace, pattern hoặc business rule.
- `checkIndex` kiểm tra miền chỉ số [0, length), không thay cho kiểm tra quyền truy cập hay ý nghĩa phần tử.
- Helper riêng như `requirePositive` nên ném lỗi có nghĩa và giữ việc xác thực **không thể bị tắt**.
- Với một giá trị từ người dùng, hệ thống có thể muốn trả **ValidationResult** thay vì exception vì đầu vào sai là tình huống thường xuyên; đó là lựa chọn thiết kế API, nhưng không dùng `assert` để thay thế.

Ví dụ helper có thể tái sử dụng:

~~~java
static int requirePositive(int value, String parameter) {
    if (value <= 0) {
        throw new IllegalArgumentException(
                parameter + " must be positive");
    }
    return value;
}
~~~

Đây là phương thức hợp lệ khi đặt trong lớp. Có thể sử dụng trong constructor hoặc method để giảm trùng code. Tránh đưa dữ liệu nhạy cảm vào thông báo exception; tên tham số và quy tắc thường đủ.

## 18. Những trường hợp không nên chỉ dùng `assert`

| Ngữ cảnh | Vì sao assert không phù hợp? | Hướng thay thế |
| --- | --- | --- |
| Public method nhận số lượng âm | Khi `-da`, dữ liệu sai được tiếp nhận | `if` + IllegalArgumentException |
| Constructor nhận null | Object có thể được tạo không hợp lệ | Objects.requireNonNull |
| Record có giá trị component sai | Bất biến không được kiểm soát | Compact constructor validation |
| REST API nhận ngày sai | Dữ liệu người dùng có thể sai bình thường | Parse + map lỗi validation |
| File CSV chứa dòng hỏng | Lỗi nhập liệu dự kiến | Trả lỗi theo dòng, exception/result phù hợp |
| Collection truy cập index | Sai index là sai hợp đồng | Objects.checkIndex hoặc API checked |
| Giao dịch có input vượt giới hạn | Không được phép thay đổi state khi input sai | Validate trước side effect |
| Trạng thái đối tượng closed | Thao tác không được phép theo API | IllegalStateException |
| Quy tắc quyền truy cập | Bảo vệ bắt buộc trong mọi chế độ | Kiểm tra authorization không thể tắt |
| Kiểm tra null để tránh dereference sâu | Khi tắt assert sẽ NPE muộn | Objects.requireNonNull |
| Assert gọi hàm thay đổi state | Bật/tắt đổi hành vi chương trình | Tách thao tác thành câu lệnh bình thường |
| Quy trình phục hồi lỗi dự kiến | AssertionError thuộc Error, không phải contract thông thường | Exception/domain error hoặc result type |

**Phân biệt mức độ “không nên”:** JLS không cấm cú pháp `assert x > 0` ngay đầu public method, nhưng cách đó **không bảo đảm hợp đồng** nếu assertions tắt. Vì vậy đây là **anti-pattern thiết kế**, không phải lỗi syntax Java.

## 19. Khi nào vẫn nên dùng `assert` trong code production?

Assertions có thể xuất hiện trong code production để hỗ trợ chẩn đoán một invariant nội bộ khi được bật có chủ đích. Ví dụ trong một thuật toán mà đầu vào đã được public API kiểm tra và mọi đường điều khiển đều bảo đảm một tính chất:

~~~java
int result = carefullyComputedValue();
assert result >= 0 : "internal algorithm invariant";
return result;
~~~

Đây là đoạn minh họa, giả định `carefullyComputedValue()` tồn tại và logic chương trình đã bảo đảm kết quả không âm. Khi assertions tắt, thuật toán vẫn phải có nghĩa và giữ được hợp đồng quan trọng.

Những nơi cần cân nhắc kỹ:

- **Security check:** tuyệt đối không thay bằng assert, vì bật/tắt làm khác mức bảo vệ.
- **Input validation:** không dùng assert vì caller được phép truyền dữ liệu sai và cần phản hồi ổn định.
- **Resource management:** không đặt close/commit/rollback trong assert expression.
- **Concurrency:** assert không cung cấp khóa, visibility, atomicity hay synchronization.
- **Debug-only invariant:** có thể dùng assert để phát hiện vi phạm giả định mà implementation vốn phải bảo đảm.
- **Expensive invariant check:** có thể dùng assert nếu điều kiện không gây side effect, việc chạy thêm chỉ nhằm debug, và không có hậu quả bắt buộc khi bị tắt.

Một lỗi invariant phát hiện bởi `AssertionError` thường cần điều tra và sửa logic, không phải trả thông điệp “tham số không hợp lệ” cho người dùng cuối.

## 20. Những nhầm lẫn thường gặp về bật/tắt assertions

**Nhầm lẫn 1 — “Java tự bật assert khi debug trong IDE.”**  
Không có bảo đảm như vậy. IDE/test runner có thể tự thêm `-ea` hoặc không. Hãy kiểm tra cấu hình JVM thật. Một chương trình được biên dịch bằng `javac` không tự làm assertions bật.

**Nhầm lẫn 2 — “Chạy `java MyProgram -ea` sẽ bật assert.”**  
Không. Tùy chọn JVM nằm trước tên main class: dùng `java -ea MyProgram`.

**Nhầm lẫn 3 — “Assert chỉ tắt phần `throw`, còn điều kiện vẫn chạy.”**  
Sai. Khi assert tắt, các biểu thức trong assert **không được đánh giá**.

**Nhầm lẫn 4 — “Chạy `-ea` ở dev thì production cũng được bảo vệ.”**  
Sai. Một môi trường khác có thể tắt assertion, đặc biệt khi thay đổi launcher/configuration.

**Nhầm lẫn 5 — “Một `catch(Exception)` xử lý được AssertionError.”**  
Sai. AssertionError thuộc `Error`, không nằm trong cây Exception.

**Nhầm lẫn 6 — “Mọi thứ `assert` kiểm tra đều là dữ liệu công khai.”**  
Không. Assert phù hợp nhất khi kiểm tra một invariant **được implementation kiểm soát**, tức sai lệch cho thấy bug thay vì dữ liệu người dùng nhập sai.

**Nhầm lẫn 7 — “Objects.requireNonNull kiểm tra mọi dạng String sai.”**  
Không. Chuỗi `""` vẫn khác null; cần kiểm tra thêm isBlank, định dạng và miền.

**Nhầm lẫn 8 — “JUnit assertEquals giống Java keyword assert.”**  
Không. Framework assertion là phương thức thư viện, không được JVM bỏ qua bằng cờ `-da` như câu lệnh assert của ngôn ngữ.

**Nhầm lẫn 9 — “Chỉ cần `assert balance >= 0` sau phép trừ là đủ.”**  
Không. Khi assert tắt, điều kiện không được kiểm tra. Phải có logic bình thường ngăn rút quá số dư trước khi cập nhật.

**Nhầm lẫn 10 — “Assert luôn gây AssertionError khi expression lỗi.”**  
Không hẳn. Khi điều kiện hoặc biểu thức detail tự ném một ngoại lệ/lỗi trong lúc đánh giá, câu lệnh có thể kết thúc bằng lỗi đó; JLS mô tả rõ hành vi này.

## 21. Quy trình review một public method hoặc constructor

Hãy rà soát theo thứ tự:

1. **Đầu vào từ đâu?** Caller ngoài module, HTTP, file, CLI, cấu hình hay một bước nội bộ đã kiểm tra?
2. **Tham số nào bắt buộc?** Null, rỗng, range, index, format, enum, capacity có điều kiện rõ ràng không?
3. **Có dùng `assert` làm hàng rào duy nhất không?** Nếu có, cần thay bằng `if`, Objects helper hoặc validation result.
4. **Mã có side effect trước khi kiểm tra không?** Hãy validate trước khi ghi DB, gửi message, thay đổi state hoặc phân bổ tài nguyên đắt đỏ.
5. **Ngoại lệ có đúng ý nghĩa không?** NullPointerException, IllegalArgumentException, IndexOutOfBoundsException, IllegalStateException hay custom domain failure?
6. **Thông điệp có an toàn không?** Không lộ token, password, dữ liệu nhạy cảm hoặc toàn bộ input lớn.
7. **Constructor có thể tạo object không hợp lệ không?** Kiểm tra trước khi lưu component/field.
8. **Invariant được bảo đảm ở đâu?** Validation và thuật toán phải bảo đảm; assert chỉ bổ sung chẩn đoán.
9. **Có biểu thức side effect trong assert không?** Nếu có, tách khỏi assert thành statement luôn chạy.
10. **Kiểm thử hai chế độ?** Chạy với `java -da` và `java -ea` để bảo đảm public contract không thay đổi.
11. **Kiểm thử đường lỗi?** Kiểm tra đúng loại exception, message hoặc mã lỗi, trạng thái sau khi từ chối.
12. **Ghi tài liệu API:** mô tả miền tham số và kiểu lỗi thay vì dựa vào việc người gọi đọc code assert.

Checklist này đặc biệt hữu ích khi di chuyển code từ script/debug utility sang thư viện công khai: những giả định chỉ đúng với dữ liệu test cần chuyển thành kiểm tra hợp đồng trước khi chịu đầu vào thực tế.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không dùng `assert amount > 0` làm kiểm tra duy nhất trong public method?  
Vì assertion có thể bị tắt và khi đó `amount > 0` không được đánh giá; input sai vẫn có thể đi tiếp.

**Câu 2.** Chạy `java -ea Program` khác `java -da Program` thế nào?  
Cờ đầu cho phép assertions thuộc phạm vi áp dụng, cờ sau vô hiệu hóa chúng; các validation viết bằng `if`/Objects vẫn chạy như nhau.

**Câu 3.** Khi `assert false : "bad";` được bật, lỗi thường là gì?  
**AssertionError**, thuộc nhánh Error.

**Câu 4.** `catch(Exception ex)` có bắt được AssertionError không?  
**Không**, vì AssertionError không kế thừa Exception.

**Câu 5.** Nếu `assert checkAndModify();` có side effect, khi `-da` side effect xảy ra không?  
**Không**, biểu thức điều kiện không được gọi.

**Câu 6.** Một constructor nhận null ở tham số bắt buộc nên xử lý bằng gì?  
Có thể dùng **Objects.requireNonNull**, ném NullPointerException theo hợp đồng rõ ràng.

**Câu 7.** Số lượng âm do caller truyền có phải invariant nội bộ bị phá vỡ không?  
Thông thường **không**; đó là tham số sai hợp đồng công khai, nên phản hồi qua validation.

**Câu 8.** Khi đối tượng đã đóng mà caller gọi mutate, loại ngoại lệ thường phù hợp là gì?  
**IllegalStateException** theo thiết kế API thường dùng.

**Câu 9.** Có nên dùng `assert index >= 0` để đảm bảo truy cập danh sách hợp lệ không?  
**Không**. Cần kiểm tra cả giới hạn trên bằng code bắt buộc, ví dụ Objects.checkIndex.

**Câu 10.** Có thể dùng assert để kiểm tra invariant nội bộ sau khi validation đầy đủ không?  
**Có thể**, miễn khi assertions tắt ứng dụng vẫn giữ hợp đồng và điều kiện không có side effect.

**Câu 11.** Một compact constructor của record có tự từ chối số lượng 0 không?  
**Không tự động**. Phải kiểm tra bằng `if` nếu đó là precondition.

**Câu 12.** Tại sao nên chạy test với cả `-ea` và `-da`?  
Để phát hiện code sai phụ thuộc vào việc assertions được bật; public API phải giữ hành vi validation nhất quán.

**Câu 13.** `assert condition : detailExpression` có luôn đánh giá detailExpression không?  
**Không**. Chỉ đánh giá khi assertion bật và điều kiện sai (trừ khi điều kiện kết thúc đột ngột).

**Câu 14.** Từ khóa `assert` và phương thức `assertThrows` trong test framework có phải giống nhau không?  
**Không**. `assertThrows` là phương thức kiểm thử; từ khóa assert có thể bị JVM vô hiệu hóa.

## Tài liệu tham khảo chuẩn

- [JLS Java SE 21 — §14.10: The assert Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.10) — quy tắc bật/tắt, đánh giá biểu thức, AssertionError và khuyến cáo không dùng assertions cho public argument checking.
- [Oracle — Programming With Assertions](https://docs.oracle.com/javase/8/docs/technotes/guides/language/assert.html) — lựa chọn đúng/sai khi sử dụng assert và side effects.
- [Java SE 21 — java.lang.AssertionError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AssertionError.html).
- [Java SE 21 — java.util.Objects: requireNonNull, checkIndex](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html).
- [Java SE 21 — IllegalArgumentException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/IllegalArgumentException.html).
- [Java SE 21 — IllegalStateException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/IllegalStateException.html).
- [Java SE 21 — IndexOutOfBoundsException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/IndexOutOfBoundsException.html).
- [Java launcher — enableassertions / disableassertions](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).

**Ghi nhớ:** `assert` dành cho giả định nội bộ mà chương trình **đã bảo đảm đúng**, giúp phát hiện bug khi bật chẩn đoán. **Public method, constructor, record, API nhận dữ liệu bên ngoài và các thao tác có side effect phải xác thực tiền điều kiện bằng code luôn chạy**, bất kể `-ea`/`-da`. Hãy chọn ngoại lệ hợp đồng có ý nghĩa, giữ cause khi chuyển đổi lỗi, viết test cho dữ liệu sai và không để tính đúng đắn hay bảo mật phụ thuộc vào trạng thái assertions.
