# Không phụ thuộc nguyên văn thông báo NullPointerException làm hợp đồng kiểm thử

## 1. Vấn đề: thông báo tốt để chẩn đoán không đồng nghĩa với API ổn định

Khi một chương trình Java truy cập phương thức hoặc field qua tham chiếu `null`, máy ảo có thể phát sinh `NullPointerException` (NPE). Các bản Java hiện đại thường cung cấp **Helpful NullPointerExceptions**: thay vì chỉ nói xảy ra NPE, thông báo có thể gợi ý thao tác nào thất bại và biểu thức nào đã trả `null`.

Ví dụ:

~~~java
String result = customer.name().trim();
~~~

Nếu `customer` là một đối tượng hợp lệ nhưng `customer.name()` trả `null`, JVM có thể tạo thông báo mô tả rằng không thể gọi `String.trim()` vì giá trị trả về của `name()` là `null`. Thông báo giúp người phát triển tìm nguyên nhân nhanh hơn, nhưng **không được coi chính nguyên văn câu chữ do JVM tạo ra là hợp đồng kiểm thử hoặc hợp đồng API của ứng dụng**.

Điểm mấu chốt:

- **Hợp đồng hành vi** có thể là: ném `NullPointerException` khi dữ liệu đầu vào không đáp ứng điều kiện; không ghi dữ liệu; trả kết quả đúng trên đường thành công.
- **Thông tin chẩn đoán** là mô tả được JVM/Java runtime tạo để hỗ trợ kỹ sư đọc lỗi: chi tiết của nó có thể thay đổi theo JDK, JVM, cách biên dịch hoặc cấu hình.
- Nếu ứng dụng cần báo lỗi cho máy khác đọc, dùng **mã lỗi, kiểu ngoại lệ hoặc kiểu kết quả do chính ứng dụng quy định**; không lấy câu tiếng Anh trong NPE làm định dạng giao tiếp.

Bài này tập trung vào kiểm thử đáng tin cậy khi ứng dụng có NPE. Không chủ trương bỏ qua NPE hay bắt NPE để che lỗi lập trình; mục tiêu là **chọn assertion đúng mức độ ổn định của hợp đồng**.

## 2. Java 14 đã cải thiện chẩn đoán NPE như thế nào?

JEP 358 — *Helpful NullPointerExceptions* xuất hiện trong **JDK 14**. Khi JVM tự phát sinh một NPE tại thao tác dereference, tính năng có thể dùng thông tin bytecode để mô tả thao tác thất bại và nguồn của tham chiếu `null`.

Về lịch sử cấu hình:

- **JDK 14 (HotSpot):** có thể bật bằng `-XX:+ShowCodeDetailsInExceptionMessages`; mặc định tính năng bị tắt.
- **JDK 15 trở đi (HotSpot):** giá trị mặc định của cờ được đổi thành bật. Các bản JDK hiện đại vẫn hỗ trợ chẩn đoán dạng này.
- Có thể tắt trên HotSpot bằng `-XX:-ShowCodeDetailsInExceptionMessages`, nhưng đây là **cờ triển khai JVM**, không phải một API Java SE mà mọi máy ảo đều phải hỗ trợ giống nhau.

Tính năng chủ yếu liên quan đến **NPE do JVM sinh ra** khi xảy ra một thao tác không hợp lệ với `null`. Ví dụ:

~~~java
static int readLength(String value) {
    return value.length();  // NPE do dereference nếu value == null
}
~~~

Khác với:

~~~java
throw new NullPointerException("customer is required");
~~~

Ví dụ thứ hai là **chủ động tạo ngoại lệ với thông báo do ứng dụng viết**. Máy ảo không cần suy luận một biểu thức null để hình thành câu chữ này. Tương tự, `Objects.requireNonNull(value, "customer is required")` sử dụng thông điệp do người gọi chỉ định nếu giá trị `null`.

Hữu ích cho việc chẩn đoán không có nghĩa là chắc chắn luôn có thông điệp. Tài liệu `NullPointerException.getMessage()` của Java SE 17/26 nêu rằng nếu không có thông điệp tường minh từ constructor thì kết quả là **thông điệp đặc thù triển khai hoặc `null`**. Một số thông tin nội bộ dùng để tạo thông điệp có thể không còn, chẳng hạn khi ngoại lệ được deserialize.

Vì vậy, code kiểm thử không nên mặc định:

~~~java
String message = exception.getMessage();
int n = message.length(); // Có thể NPE tiếp nếu message == null
~~~

Đây là đoạn mã minh họa **không an toàn**, không có phương thức `main` độc lập. Hãy coi `getMessage()` là dữ liệu chẩn đoán có thể thiếu, chứ không phải một trường bắt buộc luôn mang chuỗi do JVM tạo ra.

## 3. Vì sao khẳng định nguyên văn thông báo khiến test giòn?

Giả sử một bài test mong đợi thông báo NPE đúng một câu kiểu:

~~~java
// Minh họa cách kiểm thử không nên dùng cho thông báo NPE do JVM sinh.
assertEquals("Cannot invoke ... because ... is null",
             exception.getMessage());
~~~

Đoạn này là ví dụ trong môi trường JUnit, **không phải đoạn Java chạy độc lập**. Nó có các vấn đề sau:

| Nguồn thay đổi | Vì sao nguyên văn thông báo dễ khác? |
| --- | --- |
| Cờ `ShowCodeDetailsInExceptionMessages` | Bật có thể hiện thông báo dài; tắt có thể cho `null` |
| Phiên bản JDK hoặc JVM | Thông báo được mô tả ở mức *implementation-specific*, không có yêu cầu cố định từng chữ |
| Khác cách biên dịch và thông tin debug | Tên local variable, biểu thức hay dạng mô tả có thể khác khi không có đủ metadata |
| Refactor mã nguồn | Đổi tên method, chuyển logic qua helper, đổi biểu thức truy cập có thể đổi câu chẩn đoán |
| Obfuscation, instrumentation, thư viện | Bytecode được biến đổi có thể khiến nội dung mô tả khác mã nguồn ban đầu |
| Nguồn gốc NPE | NPE do VM tạo, NPE do `new NullPointerException()` hoặc NPE có thông điệp tường minh không nhất thiết giống nhau |
| Môi trường chạy | VM khác nhau và cấu hình logging/exception handling khác nhau có thể tạo khác biệt |

Ngoài ra, **stack trace không phải hợp đồng nguyên văn**: tên file, số dòng, định dạng khi in stack trace và đường dẫn call có thể đổi khi refactor, nâng cấp compiler hoặc thay môi trường. Test không nên đòi một chuỗi log dài trùng từng ký tự để chứng minh hành vi nghiệp vụ.

Một lỗi tương tự là:

~~~java
// Minh họa test giòn: vừa phụ thuộc wording, vừa có nguy cơ NPE.
assertTrue(exception.getMessage().contains("because"));
~~~

Khi `getMessage() == null`, chính test lại ném NPE, làm thông tin lỗi bị nhiễu. **Ngay cả khi có kiểm tra `message != null`**, việc ép phải chứa từ `"because"` vẫn không trở thành hợp đồng bảo đảm của Java SE.

Các ví dụ kiểm tra thông báo nói trên chỉ minh họa lỗi thiết kế test; chúng **không phải ví dụ được khuyến nghị dùng**.

## 4. Chương trình Java 17+: chứng minh thông báo phụ thuộc cấu hình JVM

Tạo file **`NpeMessageVariabilityDemo.java`**:

~~~java
import java.util.Objects;

public class NpeMessageVariabilityDemo {
    static final class Customer {
        String name() {
            return null;
        }
    }

    static String readName(Customer customer) {
        return customer.name().trim();
    }

    static void run() {
        try {
            readName(new Customer());
            throw new AssertionError("Expected NPE");
        } catch (NullPointerException ex) {
            System.out.println("vmNpeType="
                    + ex.getClass().getSimpleName());
            System.out.println("vmMessagePresent="
                    + (ex.getMessage() != null));
        }

        try {
            Objects.requireNonNull(null, "customer is required");
            throw new AssertionError("Expected NPE");
        } catch (NullPointerException ex) {
            System.out.println("explicitNpeType="
                    + ex.getClass().getSimpleName());
            System.out.println("explicitMessage=" + ex.getMessage());
        }

        NullPointerException bare = new NullPointerException();
        System.out.println("bareMessageIsNull="
                + (bare.getMessage() == null));
    }

    public static void main(String[] args) {
        run();
    }
}
~~~

Biên dịch với JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 NpeMessageVariabilityDemo.java
~~~

Chạy với hai cấu hình của HotSpot:

~~~bash
java -XX:+ShowCodeDetailsInExceptionMessages NpeMessageVariabilityDemo
java -XX:-ShowCodeDetailsInExceptionMessages NpeMessageVariabilityDemo
~~~

**Kết quả khi bật chi tiết (đã kiểm tra trên môi trường Java 17):**

~~~text
vmNpeType=NullPointerException
vmMessagePresent=true
explicitNpeType=NullPointerException
explicitMessage=customer is required
bareMessageIsNull=true
~~~

**Kết quả khi tắt chi tiết (đã kiểm tra trên cùng môi trường Java 17):**

~~~text
vmNpeType=NullPointerException
vmMessagePresent=false
explicitNpeType=NullPointerException
explicitMessage=customer is required
bareMessageIsNull=true
~~~

Cần hiểu kết quả đúng mức:

1. `vmNpeType` không đổi: vẫn là `NullPointerException`.
2. `vmMessagePresent` **khác** giữa hai cấu hình: khi bật, JVM cụ thể có thể tạo thông báo chẩn đoán; khi tắt, NPE đó không có thông báo. **Đây là kết quả kiểm thử trên JVM được dùng**, không phải lời hứa rằng mọi JVM sẽ có đúng boolean đó trong mọi điều kiện.
3. NPE do `Objects.requireNonNull(null, "customer is required")` có thông điệp **do lập trình viên chỉ định**, nên in `customer is required` trong cả hai lần chạy.
4. Đối tượng `new NullPointerException()` trong phép thử có `getMessage() == null`; một lần nữa, không dùng riêng kết quả này để khẳng định mọi cách tạo NPE trên mọi triển khai đều phải có message null.
5. Những phần có thể kiểm thử ổn định là **loại ngoại lệ và hành vi**, không phải nội dung `getMessage()` do VM suy ra.

Nếu máy ảo của bạn không nhận cờ `-XX:...`, hãy xem tài liệu JVM của chính môi trường chạy; **không** sửa test để dựa vào một cờ triển khai mà dự án không kiểm soát.

## 5. Test bền vững nên kiểm tra gì?

Thay vì hỏi “JVM đã dùng đúng những chữ nào?”, một test hành vi nên trả lời **yêu cầu nghiệp vụ nào được bảo đảm**. Thông thường ưu tiên:

1. **Đúng loại ngoại lệ:** hàm có ném `NullPointerException` hoặc loại ngoại lệ do API quy định hay không? Nếu đặc tả cho phép subtype, dùng assertion chấp nhận subtype; nếu yêu cầu đúng class, kiểm tra chính xác class.
2. **Đúng thời điểm và đúng thao tác:** thu gọn lambda hoặc khối lệnh đang được kiểm tra để ngoại lệ không bị phát sinh tình cờ ở bước setup/test assertion.
3. **Trạng thái sau lỗi:** một thao tác ghi dữ liệu, gửi thông báo, thay đổi collection có bị bỏ qua khi đầu vào không hợp lệ hay không?
4. **Đường thành công:** với đầu vào hợp lệ, hàm có trả đúng giá trị hay tạo đúng thay đổi như mong đợi không?
5. **Mã lỗi có cấu trúc:** nếu ứng dụng xuất API lỗi cho hệ thống khác, kiểm tra mã lỗi ổn định do ứng dụng định nghĩa, không parse thông điệp NPE.
6. **Nguyên nhân lỗi khi có hợp đồng:** nếu code chủ động bọc ngoại lệ, có thể kiểm tra `getCause()` hoặc chuỗi cause theo hợp đồng được công bố. Không ép stack trace hay wording JVM phải khớp.

Bảng lựa chọn assertion:

| Mục đích | Nên kiểm tra | Tránh ràng buộc |
| --- | --- | --- |
| Method truy cập null phải ném NPE | Kiểu `NullPointerException` | Câu `"Cannot invoke ..."` chính xác |
| Xử lý thất bại không gửi event | Event list/counter không đổi | Nội dung mọi dòng log được tạo |
| Xử lý thành công | Giá trị trả về / state / event | Tên biến trong message lỗi |
| API lỗi có mã ổn định | `errorCode == "NAME_REQUIRED"` | Trích `"NAME_REQUIRED"` từ câu NPE do JVM suy ra |
| Lỗi có cause nghiệp vụ | Loại cause và dữ liệu cause có hợp đồng | Số dòng trong stack trace |
| Kiểm tra thông điệp do chính mình kiểm soát | Exact message **chỉ nếu được quy định rõ là contract** | Dựa vào message của JVM như contract |

**Lưu ý về false positive:** test kiểu `assertThrows(NullPointerException.class, () -> { setup(); mutate(); verify(); })` có thể pass vì một NPE **không liên quan** xảy ra ngay trong `setup()`. Hãy thực thi setup bên ngoài và đặt **chính thao tác phải ném lỗi** trong lambda.

## 6. Chương trình Java 17+ kiểm thử hành vi mà không đọc message JVM

Tạo file **`NpeBehaviorContractDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NpeBehaviorContractDemo {
    record Customer(String name) {}

    static class InputException extends RuntimeException {
        private final String code;

        InputException(String code, String message) {
            super(message);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    static void publish(Customer customer, List<String> events) {
        String label = customer.name().strip();
        events.add("sent=" + label);
    }

    static String normalizeRequiredName(String name) {
        if (name == null) {
            throw new InputException("NAME_REQUIRED", "Name is required");
        }
        return name.strip();
    }

    @FunctionalInterface
    interface Action {
        void run();
    }

    static <T extends Throwable> T expectExact(
            Class<T> expectedType, Action action) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (actual.getClass() != expectedType) {
                throw new AssertionError("Wrong exception type", actual);
            }
            return expectedType.cast(actual);
        }
        throw new AssertionError("Expected exception was not thrown");
    }

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        NullPointerException failure = expectExact(
                NullPointerException.class,
                () -> publish(new Customer(null), events));

        System.out.println("implicitType="
                + failure.getClass().getSimpleName());
        System.out.println("eventsAfterFailure=" + events.size());

        publish(new Customer("  Ana  "), events);
        if (!events.equals(List.of("sent=Ana"))) {
            throw new AssertionError("Incorrect event");
        }
        System.out.println("successEvent=" + events.get(0));

        InputException invalid = expectExact(
                InputException.class,
                () -> normalizeRequiredName(null));
        System.out.println("domainType="
                + invalid.getClass().getSimpleName());
        System.out.println("domainCode=" + invalid.code());
        System.out.println("normalValue="
                + normalizeRequiredName("  Linh "));
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -encoding UTF-8 NpeBehaviorContractDemo.java
~~~

Chạy với hai cấu hình:

~~~bash
java -XX:+ShowCodeDetailsInExceptionMessages NpeBehaviorContractDemo
java -XX:-ShowCodeDetailsInExceptionMessages NpeBehaviorContractDemo
~~~

**Cả hai lần chạy đều cho cùng stdout sau (đã kiểm thử):**

~~~text
implicitType=NullPointerException
eventsAfterFailure=0
successEvent=sent=Ana
domainType=InputException
domainCode=NAME_REQUIRED
normalValue=Linh
~~~

Giải thích:

- `publish(new Customer(null), events)` truy cập `customer.name().strip()`. Vì `name()` trả `null`, một NPE phát sinh **trước khi** thêm sự kiện; test kiểm tra đúng loại NPE và `events.size() == 0`.
- Với `Customer("  Ana  ")`, `strip()` tạo `"Ana"` và event được thêm một lần; test kiểm tra chính xác `List.of("sent=Ana")`.
- `normalizeRequiredName(null)` có hợp đồng lỗi riêng: `InputException` với mã máy đọc được `NAME_REQUIRED`. Test kiểm tra mã đó, không phân tích văn bản tiếng Anh của NPE do JVM sinh ra.
- `expectExact(...)` là helper **chỉ phục vụ ví dụ độc lập này**, không thay thế một thư viện test như JUnit trong ứng dụng lớn. Nó kiểm tra loại ngoại lệ chính xác; nếu code throw một exception khác hoặc không throw, nó báo `AssertionError`.
- Không chỗ nào phải lấy `failure.getMessage()` để quyết định pass/fail. Bởi vậy thay đổi cấu hình helpful NPE **không làm thay đổi kết quả test**.

Thiết kế trên còn cho thấy: khi một API thật sự cần hợp đồng xử lý input rõ ràng, chủ động xác định lỗi tại ranh giới nghiệp vụ có thể phù hợp hơn việc để NPE phát sinh sâu trong chuỗi gọi. Tuy nhiên, việc dùng NPE hay domain exception phải tuân theo **hợp đồng API được lựa chọn**, không phải cứ mọi NPE đều phải bọc thành exception khác.

## 7. Viết cùng nguyên tắc bằng JUnit Jupiter

Trong dự án đã thiết lập **JUnit Jupiter** qua build tool, có thể dùng `assertThrows`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class NpeContractJupiterTest {
    @Test
    void rejectsNullNameWithoutPublishing() {
        List<String> events = new ArrayList<>();

        assertThrows(NullPointerException.class,
                () -> NpeBehaviorContractDemo.publish(
                        new NpeBehaviorContractDemo.Customer(null), events));

        assertTrue(events.isEmpty());
    }

    @Test
    void publishesNormalizedName() {
        List<String> events = new ArrayList<>();

        NpeBehaviorContractDemo.publish(
                new NpeBehaviorContractDemo.Customer("  Ana  "), events);

        assertEquals(List.of("sent=Ana"), events);
    }

    @Test
    void domainErrorHasStableCode() {
        var error = assertThrows(
                NpeBehaviorContractDemo.InputException.class,
                () -> NpeBehaviorContractDemo.normalizeRequiredName(null));

        assertEquals("NAME_REQUIRED", error.code());
    }
}
~~~

**Lưu ý về khả năng chạy:** đây là **mã test dùng dependency JUnit Jupiter**, không thể biên dịch bằng mỗi `javac --release 17` nếu classpath không có JUnit. Test cũng giả định file `NpeBehaviorContractDemo.java` từ phần 6 ở cùng package mặc định; trong dự án thật hãy tổ chức package/import tương ứng. Do đó mã này là ví dụ tích hợp JUnit, **không phải một chương trình chạy độc lập đã kiểm chứng bằng javac thuần**.

Các lưu ý:

- `assertThrows(ExpectedType.class, executable)` xác nhận ngoại lệ thuộc loại đã chỉ định **hoặc subtype**. Nếu hợp đồng đòi đúng class, các phiên bản JUnit Jupiter hiện đại có `assertThrowsExactly(...)`; chỉ dùng khi dự án hỗ trợ API đó.
- Ưu tiên tập trung mỗi `executable` vào thao tác cần kiểm thử, tránh để lỗi ngoài ý muốn trong setup làm test pass giả.
- Kiểm tra dữ liệu và side effects bằng các assertions phù hợp sau khi bắt ngoại lệ.
- Không viết `assertEquals("Cannot invoke ...", error.getMessage())` nếu chuỗi đó do JVM tự sinh.

**Khi nào được assert message?** Nếu ứng dụng **chủ động đặt thông điệp và công bố nó là một phần hợp đồng cần giữ ổn định**, việc kiểm tra message có thể hợp lệ. Ví dụ exception có message do code ứng dụng tạo, hoặc message hiển thị được quy định rõ. Dù vậy, cho giao tiếp giữa các hệ thống, **mã lỗi có cấu trúc** thường phù hợp hơn so với việc buộc bên nhận parse câu chữ. Đừng trộn hai mức này với thông báo chẩn đoán tự sinh của JVM.

## 8. Test không ổn định: ví dụ trước và sau

### Cách dễ hỏng

~~~java
// Minh họa trong một bài test JUnit đã có biến "failure".
assertEquals(
        "Cannot invoke \"String.trim()\" because ...",
        failure.getMessage());
~~~

Trong một môi trường, thông báo có thể chứa phần diễn giải mà người viết test dự đoán; ở môi trường khác, `failure.getMessage()` có thể bằng `null`. Test fail dù hành vi thật sự của method vẫn chính xác.

Đổi thành:

~~~java
// Kiểm tra hợp đồng: loại ngoại lệ, không dựa vào câu chữ.
assertThrows(NullPointerException.class,
        () -> service.perform(inputWithNull));
~~~

Đây là **mã minh họa**: `service`, `perform` và `inputWithNull` giả định là đối tượng/method của ứng dụng. Khi dùng thật, kết hợp kiểm tra trạng thái sau lỗi và đường thành công theo yêu cầu nghiệp vụ, ví dụ `assertEquals(0, repository.countPending())` nếu hành vi này được hợp đồng đảm bảo.

### Các thông tin chẩn đoán vẫn có ích

Không phụ thuộc nguyên văn thông báo trong assertion **không đồng nghĩa bỏ qua nó khi debug**. Khi cần điều tra lỗi, có thể xem:

- Loại exception.
- `getMessage()` nếu có; sử dụng như dữ liệu gợi ý, không đặt expectation cố định theo từng chữ.
- `getStackTrace()` để tìm vùng code xảy ra lỗi; số dòng là dữ liệu điều tra, không phải interface bền vững.
- `getCause()` để truy nguyên ngoại lệ gốc khi application code bọc exception.
- Context do ứng dụng log riêng: request/correlation ID, operation, validation state được phép ghi log.

**Bảo mật:** Helpful NPE có thể làm lộ tên field/method hoặc cấu trúc nội bộ. Không nên trả thẳng thông báo NPE/stack trace chi tiết cho người dùng cuối hay API client trong production. Có thể ghi log trong hệ thống phù hợp chính sách bảo mật, rồi trả **mã lỗi ứng dụng** và thông điệp an toàn cho client.

## 9. Vì sao thông báo tường minh cũng cần phân định hợp đồng?

Xét:

~~~java
String safe = java.util.Objects.requireNonNull(
        customerName, "customerName is required");
~~~

Nếu `customerName == null`, `Objects.requireNonNull` ném `NullPointerException` với thông điệp được người viết code cung cấp. Khác với helpful NPE do VM tổng hợp, câu `"customerName is required"` thuộc **quyền kiểm soát của ứng dụng**. Tuy nhiên:

1. **Không tự động suy ra đó là hợp đồng công khai:** trong một utility nội bộ, câu chữ có thể được chỉnh cho dễ hiểu mà không làm thay đổi chức năng. Test chỉ nên ghim exact message nếu có yêu cầu rõ.
2. **Nếu public API thực sự quy định message:** có thể assert exact message, nhưng cần giữ tính tương thích khi đổi thông điệp.
3. **Nếu caller cần phân loại lỗi:** ưu tiên kiểu exception, mã `enum`/`String code` hoặc kiểu kết quả thay vì so khớp substring tiếng Anh.
4. **Nếu quốc tế hóa thông điệp:** câu chữ có thể phụ thuộc locale, vì thế test phải tách rõ **hợp đồng mã lỗi** khỏi **message dành cho con người**.
5. **Nếu nguyên nhân là bug trong code:** đừng thay bằng một chuỗi lỗi “đẹp” để che việc dereference null ngoài dự kiến; kiểm tra input và invariant ở ranh giới phù hợp.

Với các thư viện Java chuẩn, chỉ dựa vào thông điệp khi **tài liệu API thực sự bảo đảm nội dung**, không phải vì bạn vừa quan sát một chuỗi cụ thể ở máy phát triển.

## 10. Checklist bảo vệ test khi nâng cấp JDK

Trước khi chốt test liên quan đến null:

- **Nguồn NPE là gì?** VM tự phát sinh khi dereference hay ứng dụng chủ động throw? Hai nguồn này có cách tạo message khác nhau.
- **Hợp đồng nào thật sự cần giữ?** Loại ngoại lệ, giá trị kết quả, side effect, mã lỗi và cause có thường quan trọng hơn câu chữ không?
- **Test có vô tình assert phần chẩn đoán không?** Tìm `getMessage()`, `toString()`, `printStackTrace()`, `contains("because")` hoặc snapshot log được dùng làm pass/fail.
- **Message có thể là `null` không?** `NullPointerException.getMessage()` theo Javadoc có thể trả `null`. Không dùng `.contains(...)` khi chưa kiểm tra; và dù đã null-check, cũng không biến lời chẩn đoán thành contract.
- **Đã thu hẹp đoạn đang được `assertThrows` kiểm tra chưa?** Nếu nhiều lệnh cùng có thể ném NPE, một lỗi sai vị trí vẫn khiến test “xanh”.
- **Đã kiểm tra hành vi khi thất bại và khi thành công chưa?** Ví dụ không gửi event khi input sai, nhưng có gửi event với input đúng.
- **Cần thông báo lỗi cho máy đọc?** Hãy định nghĩa error code cụ thể, tránh parse từ thông báo JVM.
- **Bản JDK/JVM thay đổi thì test có còn đúng không?** Kiểm thử dưới hai cấu hình helpful NPE nếu môi trường HotSpot hỗ trợ cờ; kết quả nghiệp vụ cần giống nhau.
- **Có nguy cơ rò thông tin trong log/API?** Không phát tán trực tiếp stack trace hoặc helpful NPE detail cho bên ngoài khi không được phép.
- **Có yêu cầu exact message do ứng dụng tự quy định không?** Nếu có, kiểm thử thông điệp **do mình sở hữu**, và ghi rõ đó là hợp đồng của ứng dụng chứ không phải bảo đảm chung của JVM.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Hai bản JDK tạo thông báo NPE khác nhau, nhưng đều ném `NullPointerException` đúng khi input null. Test assert nguyên văn message có thể fail. Điều đó có nhất thiết là lỗi nghiệp vụ không?  
**Trả lời:** Không. Nếu message do JVM tự tạo và không nằm trong hợp đồng, khác biệt wording không chứng minh chức năng sai.

**Câu 2.** Có được viết `exception.getMessage().contains("because")` làm assertion mặc định không?  
**Trả lời:** Không nên. `getMessage()` có thể `null` và câu chữ là chi tiết triển khai.

**Câu 3.** Helpful NPE xuất hiện ở JDK nào? Mặc định bật từ khi nào trên HotSpot?  
**Trả lời:** JEP 358 xuất hiện ở **JDK 14** và có cờ bật; mặc định được bật trên HotSpot từ **JDK 15**.

**Câu 4.** Nếu API cần trả mã lỗi ổn định cho client, nên trích `"Cannot invoke ..."` để xác định mã lỗi không?  
**Trả lời:** Không. Hãy ánh xạ bằng quy tắc ứng dụng và mã lỗi do ứng dụng quy định, ví dụ `NAME_REQUIRED`.

**Câu 5.** `Objects.requireNonNull(value, "value required")` tạo NPE có message tường minh. Có thể assert exact không?  
**Trả lời:** Có thể nếu **message thuộc hợp đồng được chính ứng dụng công bố**. Không nên ghim câu chữ chỉ vì nó hiện trong log.

**Câu 6.** Vì sao test có `assertThrows(NPE.class, () -> { setup(); execute(); })` dễ sai?  
**Trả lời:** NPE từ `setup()` cũng có thể làm test pass; nên chuẩn bị điều kiện bên ngoài và cô lập `execute()`.

**Câu 7.** Nếu tắt `ShowCodeDetailsInExceptionMessages` mà test hành vi vẫn pass, điều đó chứng minh gì?  
**Trả lời:** Test không cần lời chẩn đoán có hay không để xác nhận loại ngoại lệ và các hậu điều kiện đã quy định.

## Tài liệu chính thức

- **OpenJDK JEP 358 — Helpful NullPointerExceptions** (JDK 14; thông báo chi tiết do JVM tổng hợp từ bytecode): https://openjdk.org/jeps/358
- **Oracle Java SE 17 API — NullPointerException.getMessage()** (thông điệp đặc thù triển khai hoặc `null` nếu không có message tường minh): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NullPointerException.html#getMessage()
- **Oracle Java SE 26 API — NullPointerException** (xác nhận quy tắc vẫn áp dụng trong các phiên bản hiện đại): https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NullPointerException.html
- **Oracle JDK 15 Release Notes** (thay đổi giá trị mặc định của `ShowCodeDetailsInExceptionMessages` thành bật): https://www.oracle.com/java/technologies/javase/15-relnote-issues.html
- **Oracle Java SE 17 API — Objects.requireNonNull** (đầu vào null và message do người dùng quy định): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)
- **JUnit Jupiter User Guide — Assertions** (kiểm tra exception và trạng thái, không phụ thuộc vào nguyên văn chẩn đoán): https://docs.junit.org/current/user-guide/#writing-tests-assertions