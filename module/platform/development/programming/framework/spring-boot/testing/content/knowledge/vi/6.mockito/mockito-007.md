# doReturn, doThrow và giới hạn khi làm việc với spy

Khi kiểm thử Java bằng Mockito, `mock` và `spy` không có cùng cách hoạt động. Với mock thông thường, một phương thức chưa stub thường không chạy logic thật; với spy, các phương thức chưa stub **thực thi logic thật**. Vì vậy, dòng trông quen thuộc như `when(spy.someMethod()).thenReturn(value)` có thể gọi phương thức thật ngay **trong lúc chuẩn bị test**, trước khi đến bước thực hiện hành vi cần kiểm tra. Nếu phương thức đó đọc file, truy vấn database, thay đổi trạng thái hoặc ném ngoại lệ, test có thể hỏng ngay trong pha Arrange.

Mockito cung cấp họ API `doReturn(...)`, `doThrow(...)`, `doAnswer(...)`, `doNothing()` và `doCallRealMethod()`. Đối với spy, đặc biệt là `doReturn` và `doThrow`, các API này giúp cấu hình hành vi mà **không chạy phương thức đang được stub tại thời điểm thiết lập**. Tuy nhiên, spy là một dạng *partial mock*: phần lớn code còn lại vẫn là thật, nên nó không tự đảm bảo test an toàn, ổn định hoặc phản ánh đúng nghiệp vụ.

**Sau bài này, bạn có thể:** giải thích mock khác spy; chọn đúng giữa `when(...).thenReturn(...)` và `doReturn(...).when(...)`; sử dụng `doThrow` cho phương thức `void` và phương thức trả giá trị; hiểu rủi ro trạng thái, side effect, AOP proxy, private/final method; xác định khi nào nên thay spy bằng dependency injection; viết JUnit 5 test có thể chạy với Java 17+ và Spring Boot.

## 1. Mock, spy và partial mocking

| Đặc điểm | `mock(MyClass.class)` | `spy(new MyClass(...))` |
|---|---|---|
| Phương thức chưa stub | Thường dùng default answer của mock: `null`, `false`, số 0, collection rỗng tùy loại trả về/cấu hình Mockito | Mặc định gọi phương thức **thật** |
| Constructor và trạng thái | Mock thông thường không mặc định thực thi constructor của đối tượng thực | Với `spy(instance)`, bạn cung cấp đối tượng đã khởi tạo; Mockito tạo spy từ trạng thái đó |
| Thiết lập `when(target.method())` | Thường chỉ gọi phương thức giả để ghi nhận lời gọi stubbing | **Có thể chạy phương thức thật** trên spy |
| `doReturn(value).when(target).method()` | Stub không gọi logic thật | Stub không gọi logic thật |
| Tác dụng phụ ngoài ý muốn | Chủ yếu đến từ custom answer hoặc logic test | Có thể đến từ bất kỳ phương thức thật chưa stub |
| Dùng khi | Cần giả lập dependency ngoài phạm vi kiểm tra | Cần giữ phần lớn hành vi thật, chỉ thay một phần có lý do |
| Rủi ro thiết kế | Mock quá nhiều làm test chỉ chứng minh thiết lập giả | Test phụ thuộc cấu trúc nội bộ, trạng thái và side effect của lớp thật |

**Spy không phải bản sao của mock đã “trả dữ liệu thật”.** Spy chứa logic của đối tượng, mặc định gọi method thật; stubbing chỉ thay thế những lời gọi đã được xác định. Không thể suy ra rằng tạo spy sẽ tự tách hết I/O, database, thread, transaction hoặc call tới dependency khác.

Ví dụ ngắn:

```java
import java.util.ArrayList;
import java.util.List;

import static org.mockito.Mockito.spy;

List<String> observedList = spy(new ArrayList<>());
observedList.add("A");                  // Gọi ArrayList.add thật
String value = observedList.get(0);     // Gọi ArrayList.get thật
// value bằng "A"
```

Đây là **đoạn minh họa**, không phải một file Java độc lập có `main` hay `@Test`. Nó cho thấy spy vẫn thực thi logic của `ArrayList`. Các ví dụ đầy đủ, có tên file và class, xuất hiện ở phần 4–7.

## 2. Vì sao `when(spy.method()).thenReturn(...)` có thể nguy hiểm?

Với cú pháp:

```java
when(spy.method()).thenReturn(result);
```

Java phải đánh giá biểu thức `spy.method()` để truyền kết quả cho `when(...)`. Vì `spy` mặc định dùng phương thức thật, **method có thể chạy ngay khi bạn đang stub**, trước khi Mockito thiết lập kết quả `thenReturn`.

Hãy xét danh sách rỗng:

```java
List<String> spyList = spy(new ArrayList<>());

// PHẢN VÍ DỤ: ArrayList.get(0) chạy thật trên list rỗng.
when(spyList.get(0)).thenReturn("A");
```

Dòng thiết lập này ném `IndexOutOfBoundsException` do `get(0)` thật chạy khi danh sách chưa có phần tử. Không có một test nghiệp vụ nào cần chạy để tạo lỗi; lỗi nảy sinh ngay ở Arrange.

Đổi sang **doReturn**:

```java
List<String> spyList = spy(new ArrayList<>());

doReturn("A").when(spyList).get(0);

assertEquals("A", spyList.get(0));
```

Ở đây `doReturn("A")` tạo một cấu hình stubbing; lời gọi `get(0)` sau `when(spyList)` được Mockito nhận diện để xác định method phải stub, không chạy `ArrayList.get` thật trong pha thiết lập. Khi test gọi `get(0)`, Mockito trả giá trị đã stub.

**Điểm cần phân biệt:** `doReturn` chỉ tránh chạy **method được stub trong lúc stubbing**. Những method khác trên spy vẫn chạy thật và có thể tạo side effect. Nó không làm đối tượng thành một mock thông thường.

## 3. `doReturn(...).when(spy).method(...)`: cơ chế và cách đọc

Mẫu cơ bản:

```java
doReturn(expectedValue).when(spyObject).method(arguments);
```

Hiểu theo thứ tự:

1. `doReturn(expectedValue)` khai báo giá trị mong muốn cho một lời gọi được stub.
2. `when(spyObject)` chỉ định đối tượng Mockito quản lý.
3. `method(arguments)` xác định method và argument của lời gọi phải stub; **không thực thi logic thật** tại bước cấu hình.
4. Khi code trong bước Act gọi đúng method và argument, Mockito trả `expectedValue`.
5. Các lời gọi chưa được stub tiếp tục dùng real method của spy theo default answer.

Một trường hợp khác có giá trị: method trên spy đã từng được stub để ném ngoại lệ. Nếu dùng `when(spy.method()).thenReturn(newValue)` để sửa stub, lời gọi method trong `when` có thể kích hoạt exception từ stub cũ. `doReturn(newValue).when(spy).method()` cho phép thay cấu hình mà không kích hoạt lời gọi trong setup.

**Với mock thuần**, `when(mock.method()).thenReturn(value)` thường rõ ràng và kiểm tra kiểu trả về qua chữ ký generic tốt hơn. `doReturn(Object)` nhận giá trị kiểu rộng, nên một lỗi kiểu như:

```java
// PHẢN VÍ DỤ: increase() trả int, không thể hợp lệ trả String.
// Dòng này có thể qua bước kiểm tra kiểu Java ở lời gọi doReturn,
// nhưng Mockito phát hiện kiểu không tương thích khi gắn stub.
doReturn("wrong type").when(spyCounter).increase();
```

chỉ xuất hiện ở **runtime** khi Mockito thiết lập stub. Vì vậy `doReturn` là lựa chọn có chủ đích cho spy và tình huống cần tránh chạy method thật, chứ không phải lý do thay mọi `when(...).thenReturn(...)` trong toàn bộ test.

## 4. Ví dụ đầy đủ: thấy rõ tác dụng phụ xảy ra lúc stubbing

Ví dụ dưới đây không cần Spring context, chỉ Java 17+, JUnit Jupiter, Mockito. Ta tạo một bộ đếm: gọi `increase()` thật làm trạng thái tăng; `value()` trả trạng thái, `reset()` đặt lại về 0.

**`src/main/java/com/example/testing/Counter.java`**

```java
package com.example.testing;

public class Counter {
    private int value;

    public int increase() {
        value++;
        return value;
    }

    public int value() {
        return value;
    }

    public void reset() {
        value = 0;
    }
}
```

**`src/test/java/com/example/testing/CounterSpyTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.when;

class CounterSpyTest {

    @Test
    void whenOnSpyRunsRealMethodDuringStubbing() {
        Counter observed = spy(new Counter());

        when(observed.increase()).thenReturn(42);

        assertEquals(1, observed.value(),
                "Real increase() đã chạy trong lúc stubbing");
        assertEquals(42, observed.increase(),
                "Lần gọi sau dùng kết quả đã stub");
        assertEquals(1, observed.value(),
                "Stub không tăng trạng thái khi được gọi");
    }

    @Test
    void doReturnAvoidsRealCallDuringStubbing() {
        Counter observed = spy(new Counter());

        doReturn(42).when(observed).increase();

        assertEquals(0, observed.value(),
                "Chưa tăng trong lúc stubbing");
        assertEquals(42, observed.increase());
        assertEquals(0, observed.value(),
                "Lần gọi đã stub không chạy real increase()");
    }
}
```

Cả hai test được thiết kế để **pass**, nhưng cho thấy khác biệt chính xác:

| Thời điểm | `when(spy.increase()).thenReturn(42)` | `doReturn(42).when(spy).increase()` |
|---|---:|---:|
| Trạng thái ngay sau tạo spy | 0 | 0 |
| Trạng thái sau cấu hình stub | **1** (vì method thật chạy) | **0** |
| Giá trị khi gọi `increase()` sau đó | 42 | 42 |
| Trạng thái sau lời gọi đã stub | 1 | 0 |

Nếu `increase()` thay bằng method gửi email hoặc ghi bản ghi database, side effect có thể đã xảy ra **trước khi Act của test bắt đầu**. Đó là lý do Mockito khuyên xem xét họ `doReturn`/`doThrow` khi stub spy.

**Lưu ý về scope:** ví dụ gọi `observed.value()` thật và không stub method này. Với đối tượng trạng thái phức tạp, chỉ nên assert các tác động nghiệp vụ cần bảo vệ, không tạo thói quen ràng buộc private state nếu đó không phải contract.

## 5. `doThrow(...).when(spy).voidMethod()`: giả lập lỗi từ phương thức void

Một phương thức `void` không có giá trị để truyền cho `when(...)` kiểu thông thường. Vì vậy cú pháp sau là **sai ở mức Java**:

```java
// PHẢN VÍ DỤ — KHÔNG BIÊN DỊCH: reset() có kiểu void.
when(counter.reset()).thenThrow(new IllegalStateException());
```

Mẫu đúng:

```java
doThrow(new IllegalStateException("reset blocked"))
        .when(counterSpy).reset();
```

Stubbing không chạy `reset()` thật. Chỉ khi code gọi `counterSpy.reset()` sau đó, Mockito ném `IllegalStateException` đã cấu hình.

Đặt file test tiếp theo cùng package (sử dụng `Counter.java` của mục 4):

**`src/test/java/com/example/testing/CounterFailureTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.spy;

class CounterFailureTest {

    @Test
    void doThrowForVoidMethodDoesNotResetDuringSetup() {
        Counter observed = spy(new Counter());
        observed.increase();

        doThrow(new IllegalStateException("reset blocked"))
                .when(observed).reset();

        assertEquals(1, observed.value(),
                "Thiết lập stub không gọi reset thật");

        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                observed::reset);

        assertEquals("reset blocked", failure.getMessage());
        assertEquals(1, observed.value(),
                "Phương thức reset thật không chạy khi stub ném lỗi");
    }

    @Test
    void doThrowAlsoWorksForMethodWithReturnValue() {
        Counter observed = spy(new Counter());

        doThrow(new IllegalStateException("counter offline"))
                .when(observed).increase();

        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                observed::increase);

        assertEquals("counter offline", failure.getMessage());
        assertEquals(0, observed.value());
    }
}
```

Hai điểm học tập:

- Với `reset()` kiểu `void`, `doThrow` là cách phổ biến và rõ ràng để thay hành vi thực bằng exception.
- `doThrow` **không giới hạn cho void**. Với `increase()` có `int` trả về, nó vẫn có thể tạo lỗi mà không chạy tăng bộ đếm thật trong pha thiết lập.

Nếu method trả giá trị trên một **mock thuần**, `when(mock.read()).thenThrow(error)` thường dễ đọc hơn. Với **spy**, cân nhắc `doThrow(error).when(spy).read()` nếu không được phép để logic thật chạy trong lúc setup.

## 6. `doThrow` với checked và unchecked exception

### 6.1. Unchecked exception

`IllegalStateException`, `IllegalArgumentException` hoặc các subclass của `RuntimeException` không buộc chữ ký method khai báo `throws`. Các ví dụ `CounterFailureTest` dùng unchecked exception như vậy.

### 6.2. Checked exception

Mockito kiểm tra tính hợp lệ của **checked exception** theo chữ ký của method. Ví dụ một cổng đọc dữ liệu khai báo `throws IOException`, có thể stub để ném `IOException`:

```java
package com.example.testing;

import java.io.IOException;

public interface TextStore {
    String read(String path) throws IOException;
}
```

**`src/test/java/com/example/testing/TextStoreTest.java`**

```java
package com.example.testing;

import java.io.IOException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

class TextStoreTest {

    @Test
    void returnsConfiguredCheckedException() throws Exception {
        TextStore store = mock(TextStore.class);

        doThrow(new IOException("storage unavailable"))
                .when(store).read("welcome.txt");

        IOException thrown = assertThrows(IOException.class,
                () -> store.read("welcome.txt"));

        assertEquals("storage unavailable", thrown.getMessage());
    }
}
```

Ví dụ dùng **mock của dependency** vì mục tiêu chỉ là điều khiển lỗi I/O. Nếu thật sự cần spy một implementation có method `read(...) throws IOException`, cú pháp `doThrow(...).when(spy).read(...)` vẫn theo cùng quy tắc.

Không cố cấu hình `IOException` trên một method **không khai báo** IOException hoặc supertype được phép: Mockito có thể báo checked exception không hợp lệ. Khi gặp lỗi đó, hãy kiểm tra chữ ký thật của phương thức; đừng thay bằng exception khác một cách tùy tiện nếu muốn test đúng contract.

Hai overload thường gặp:

```java
doThrow(new IllegalStateException("failed")).when(spy).reset();
doThrow(IllegalStateException.class).when(spy).reset();
```

Overload nhận **instance** thích hợp khi muốn kiểm tra thông điệp hoặc dữ liệu exception. Overload nhận **class** cho Mockito tạo exception theo kiểu đã nêu khi method được gọi; không nên dựa vào một stack trace/message tự sinh cụ thể.

## 7. Stub liên tiếp: thay đổi kết quả theo lần gọi

Có tình huống dependency lỗi sau một lần thành công hoặc trả dữ liệu theo chuỗi. Họ `doReturn`/`doThrow` cho phép khai báo các hành vi nối tiếp:

```java
Counter observed = spy(new Counter());

doReturn(10)
        .doReturn(20)
        .when(observed).increase();

assertEquals(10, observed.increase());
assertEquals(20, observed.increase());
assertEquals(20, observed.increase());
assertEquals(0, observed.value());
```

Đây là **đoạn mã minh họa nằm trong `@Test`**, sử dụng `Counter`, `assertEquals`, `doReturn` và `spy` từ các ví dụ trước; không phải chương trình Java độc lập. Mockito dùng hành vi cuối cùng cho những lời gọi tiếp theo khi danh sách kết quả đã hết.

Có thể kết hợp:

```java
Counter observed = spy(new Counter());

doReturn(10)
        .doThrow(new IllegalStateException("no more values"))
        .when(observed).increase();

assertEquals(10, observed.increase());
assertThrows(IllegalStateException.class, observed::increase);
```

Các chuỗi stub hữu ích khi **thứ tự kết quả từ dependency là một phần kịch bản cần kiểm tra** (ví dụ API thành công một lần, sau đó thất bại). Đừng dùng để mô phỏng quá nhiều nhánh nghiệp vụ trên chính service đang được kiểm tra: nếu test phải nạp cả một kịch bản giả quá phức tạp, đó có thể là dấu hiệu tách dependency chưa tốt.

## 8. Spy có trạng thái: vì sao object gốc và spy có thể khác nhau?

Một điểm rất dễ nhầm trong `Mockito.spy(realInstance)`: với cách tạo spy từ object instance thông thường, Mockito **không mặc định ủy quyền từng lời gọi ngược về đúng object gốc**. Mockito tạo spy dựa trên trạng thái hiện có của instance. Nếu sau đó bạn giữ biến tham chiếu tới object gốc và tiếp tục thay đổi nó, đừng kỳ vọng spy tự nhìn thấy các thay đổi đó; và khi gọi method thật trên spy, đừng kỳ vọng object gốc tự được cập nhật.

Ví dụ với class `Counter` ở mục 4:

```java
Counter original = new Counter();
Counter observed = spy(original);

original.increase();
original.increase();

assertEquals(2, original.value());
assertEquals(0, observed.value());

observed.increase();

assertEquals(1, observed.value());
assertEquals(2, original.value());
```

Đây là **đoạn mã trong test**, không phải class độc lập. Kết quả cho thấy hai reference có trạng thái bộ đếm riêng.

**Giới hạn cần hiểu:** trạng thái có thể chứa tham chiếu đến object mutable, file handle hoặc dependency khác. Việc Mockito tạo spy từ object không đồng nghĩa thực hiện **deep copy** toàn bộ object graph. Nếu object gốc và spy cùng giữ tham chiếu tới một collaborator mutable, tác dụng phụ trên collaborator vẫn có thể được chia sẻ. Do đó không dùng spy như một cơ chế cách ly trạng thái hay giao dịch.

Nếu người kiểm thử cố đọc `original.value()` sau khi gọi `observed.increase()` và chờ tăng, họ đang quan sát sai đối tượng. Hãy chủ động xác định test gọi **spy hay real instance**, và phân biệt sự khác biệt do stubbing với sự khác biệt do object state.

## 9. Ví dụ thực tế: thay một thao tác I/O trong lớp legacy, giữ logic render thật

Spy có giá trị nhất ở tình huống **lớp legacy chưa tách được dependency bên ngoài**. Giả sử một class vừa đọc template từ file, vừa thay tên khách hàng. Ta muốn kiểm tra logic render nhưng không muốn test phụ thuộc filesystem.

**`src/main/java/com/example/testing/LegacyReportGenerator.java`**

```java
package com.example.testing;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class LegacyReportGenerator {

    public String loadTemplate(String filename) {
        try {
            return Files.readString(
                    Path.of(filename), StandardCharsets.UTF_8);
        } catch (IOException cause) {
            throw new UncheckedIOException(cause);
        }
    }

    public String render(String filename, String customer) {
        String template = loadTemplate(filename);
        return template.replace("{customer}", customer);
    }
}
```

**`src/test/java/com/example/testing/LegacyReportGeneratorTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.spy;

class LegacyReportGeneratorTest {

    @Test
    void rendersCustomerWithoutOpeningFile() {
        LegacyReportGenerator observed =
                spy(new LegacyReportGenerator());

        doReturn("Hello, {customer}!")
                .when(observed).loadTemplate("welcome.txt");

        String result = observed.render("welcome.txt", "Mai");

        assertEquals("Hello, Mai!", result);
    }
}
```

**Cơ chế:**

1. `render(...)` **không được stub**, nên chạy code thật của `LegacyReportGenerator`.
2. `render` gọi `loadTemplate("welcome.txt")` trên chính object spy; lời gọi virtual phù hợp được Mockito chặn và trả template giả.
3. `loadTemplate` thật không mở file trong bài test này.
4. `String.replace` thật chạy và cho ra kết quả nghiệp vụ cần assert.

Nếu test viết:

```java
// PHẢN VÍ DỤ: có thể mở file thật ngay lúc stubbing.
when(observed.loadTemplate("welcome.txt"))
        .thenReturn("Hello, {customer}!");
```

method `loadTemplate` có thể truy cập file thật hoặc ném `UncheckedIOException` trong Arrange. Đây là **tình huống điển hình dùng `doReturn`**.

Điều kiện để kỹ thuật này áp dụng đáng tin: method seam `loadTemplate` phải là method Mockito có thể intercept; không dùng private method như một điểm stub. Việc self-invocation của method virtual trên spy thường đi qua cơ chế intercept của Mockito, nhưng nếu mã dùng helper private, static, native hoặc một kiểu gọi bị mock maker hạn chế, kỳ vọng “chỉ stub helper” có thể không đạt. Khi đó hướng bền vững là tách I/O thành collaborator rõ ràng.

## 10. Thiết kế tốt hơn cho code mới: tách collaborator và mock dependency

Giải pháp `spy(LegacyReportGenerator)` có thể hữu ích khi cần kiểm thử code chưa refactor được, nhưng **không nên trở thành mẫu thiết kế mặc định cho code mới**. Nếu một lớp cùng thực hiện business logic và đọc filesystem, tách I/O qua interface giúp test không cần partial mock.

**`src/main/java/com/example/testing/TemplateSource.java`**

```java
package com.example.testing;

public interface TemplateSource {
    String read(String filename);
}
```

**`src/main/java/com/example/testing/ReportService.java`**

```java
package com.example.testing;

public final class ReportService {
    private final TemplateSource source;

    public ReportService(TemplateSource source) {
        this.source = source;
    }

    public String render(String filename, String customer) {
        return source.read(filename)
                .replace("{customer}", customer);
    }
}
```

**`src/test/java/com/example/testing/ReportServiceTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ReportServiceTest {

    @Test
    void rendersCustomerUsingTemplatePort() {
        TemplateSource source = mock(TemplateSource.class);
        when(source.read("welcome.txt"))
                .thenReturn("Hello, {customer}!");

        ReportService service = new ReportService(source);

        assertEquals("Hello, Mai!",
                service.render("welcome.txt", "Mai"));
    }
}
```

Đây là unit test thuần với **logic thật** trong `ReportService`, **I/O ở dependency bị mock**. Ta không cần biết nội bộ `ReportService` có gọi private helper nào hay không; test bảo vệ đầu ra mà client của service nhận được. Nếu cần kiểm chứng adapter đọc file thật, viết một test riêng cho implementation của `TemplateSource` bằng fixture kiểm soát được.

Trong Spring Boot, dependency injection phù hợp tự nhiên với hướng này:

- Biến `TemplateSource` thành một bean/adapter thực tế trong ứng dụng.
- Service nhận `TemplateSource` qua constructor injection.
- Unit test tạo service bằng `new ReportService(mockSource)`; không phải khởi động `ApplicationContext` để kiểm tra thay chuỗi.
- Integration test chỉ khởi động context khi cần kiểm tra Spring wiring, cấu hình bean, I/O hoặc transaction thật.

**Quy tắc thực dụng:** nếu test phải liên tục dùng `doReturn` để chặn nhiều method **của chính lớp đang được test**, hãy xem có dependency hoặc trách nhiệm nào nên được tách khỏi lớp đó.

## 11. Khi nào nên dùng `@Spy` và MockitoExtension?

Với unit test, Mockito có annotation `@Spy` để khai báo spy trên một field, thường đi kèm `MockitoExtension` của JUnit Jupiter để xử lý annotation. Đây vẫn là spy Mockito của một đối tượng Java, **không mặc nhiên là Spring bean**.

Ví dụ dựa trên `Counter.java`:

**`src/test/java/com/example/testing/AnnotatedCounterSpyTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doReturn;

@ExtendWith(MockitoExtension.class)
class AnnotatedCounterSpyTest {

    @Spy
    private Counter observed = new Counter();

    @Test
    void annotationCreatesAUsableSpy() {
        doReturn(7).when(observed).increase();

        assertEquals(7, observed.increase());
        assertEquals(0, observed.value());
    }
}
```

Nếu muốn tạo spy trực tiếp bằng `spy(new Counter())` như các mục trước, bạn **không cần** `@ExtendWith(MockitoExtension.class)` chỉ để Mockito.spy hoạt động.

Những vấn đề dễ gặp với annotation:

- Chỉ viết `@Spy` nhưng không có cách khởi tạo annotation (MockitoExtension, MockitoAnnotations.openMocks hoặc runner/cơ chế tương đương) sẽ không có bảo đảm field đã được spy.
- Dùng `@Spy` trên field tự quản lý **không tự thay bean** mà ứng dụng Spring đang inject vào các lớp khác.
- Dùng `@InjectMocks` với spy có thể dẫn tới đối tượng/constructor được khởi tạo theo cách không mong đợi; minh bạch hơn khi tạo dependency và hệ thống cần test bằng constructor.
- Spy vẫn chạy method thật khi không stub; extension không biến nó thành mock thuần.

## 12. Spy với Spring Boot context: bean thật, AOP proxy và phiên bản annotation

Đôi khi cần kiểm tra một bean trong `ApplicationContext` vì hành vi liên quan đến cấu hình Spring, bean wiring hoặc AOP. Khi đó spy plain Java và spy bean của Spring Test là hai khái niệm phải phân biệt.

**Ở các nhánh Spring Boot 3.3**, test hỗ trợ `@SpyBean` từ package `org.springframework.boot.test.mock.mockito` để thay/wrap bean trong test context theo cơ chế của Boot. **Từ Spring Framework 6.2** có `@MockitoSpyBean` trong `org.springframework.test.context.bean.override.mockito`; các phiên bản Spring Boot mới tương ứng có cơ chế mới này. Không nhập cả hai annotation vào cùng một class rồi giả định chúng giống nhau trên mọi phiên bản.

Ví dụ cú pháp **chỉ mang tính định hướng cho dự án Spring Boot 3.3**, cần có context và bean thật để chạy:

```java
// Cấu hình test theo Spring Boot 3.3; đây không phải file độc lập.
@SpringBootTest
class OrderServiceContextTest {

    @SpyBean
    OrderService orderService;

    @Test
    void usesRealBeanUnlessStubbed() {
        // doReturn(...).when(orderService).someMethod(...);
        // Act qua bean thật được context cung cấp, rồi assert hành vi.
    }
}
```

Cần import `@SpringBootTest`, `@SpyBean`, `@Test` và khai báo `OrderService` thật theo module. Không đặt ví dụ này vào project nếu bean đó không tồn tại. Với Spring Framework 6.2+ dùng `@MockitoSpyBean`, hãy đọc tài liệu đúng phiên bản thay vì sao chép máy móc cú pháp cũ.

**Lưu ý đặc biệt với Spring AOP:**

- Bean có `@Transactional`, `@Cacheable`, `@Async` hoặc advice khác có thể đi qua **proxy của Spring**, không phải chỉ một object Mockito đơn lẻ.
- Khi spy bean, lời gọi đi qua proxy/advice có thể khác với lời gọi method trực tiếp trên spy; setup stub nhầm ranh giới có thể kích hoạt advice hoặc không kiểm tra được hành vi bạn nghĩ mình đang kiểm tra.
- Với `@MockitoSpyBean`, Spring TestContext có cơ chế wrap bean; nếu có AOP proxy, proxy có thể vẫn bao quanh target spy. Tính chính xác của stubbing và verification phụ thuộc bean/proxy/advice và phiên bản Spring; cần kiểm tra tài liệu tương ứng.
- **Self-invocation** trong Spring AOP (một method cùng instance gọi method khác cùng instance) thường **không đi qua proxy Spring**. Đó là vấn đề khác với interception của Mockito spy. Không dùng việc Mockito chặn một lời gọi self-call trong unit test để kết luận transaction/caching aspect sẽ áp dụng khi production self-invoke.
- Một test chỉ kiểm chứng logic thuần không nên khởi động Spring context và spy bean chỉ để gọi vài method Java.

Nếu mục tiêu là xác minh transaction, cache, security, retry hay HTTP thực sự hoạt động qua proxy, hãy viết **integration test kiểm tra kết quả quan sát được** và gọi qua boundary thật. Không đặt mọi assertion vào số lần gọi method trên spy.

## 13. Giới hạn của spy: những điều `doReturn`/`doThrow` không giải quyết

### 13.1. Chỉ method được stub mới được thay thế

Sau:

```java
doReturn("fake").when(observed).loadTemplate("welcome.txt");
```

các method khác như `render(...)` vẫn chạy thật, và `loadTemplate("other.txt")` cũng có thể chạy thật nếu argument không khớp. Khi thật sự muốn mọi filename trả một template giả, có thể dùng matcher:

```java
doReturn("Hello, {customer}!")
        .when(observed).loadTemplate(anyString());
```

Đoạn trên cần static import `org.mockito.ArgumentMatchers.anyString` và dùng trong ngữ cảnh test. `anyString()` dành cho argument kiểu String không null trong các phiên bản Mockito hiện đại; nếu method nhận `null` hợp lệ, cần matcher tương ứng (`isNull`, `nullable`) thay vì nghĩ rằng `anyString` luôn khớp cả null.

**Cảnh báo:** match quá rộng có thể che lỗi: nếu production gọi sai tên template, stub toàn bộ filename vẫn cho test xanh. Ưu tiên argument cụ thể khi đường dẫn hoặc key là một phần hợp đồng.

### 13.2. Không biến mọi lời gọi thành an toàn

Một spy của service có thể có dependency chưa được khởi tạo:

```java
// PHẢN VÍ DỤ: nếu real getInvoice() cần repository,
// spy(new InvoiceService(null)) vẫn có thể NPE khi gọi method thật.
InvoiceService observed = spy(new InvoiceService(null));
```

Đây là đoạn minh họa, `InvoiceService` không được định nghĩa trong các file có thể chạy của bài. `doReturn` có thể tránh một lời gọi nguy hiểm khi setup, nhưng **những đường chạy không stub vẫn gặp dependency null**. Thay bằng constructor injection với mock/fake của dependency thích hợp hoặc khởi tạo đối tượng hợp lệ.

### 13.3. Private, static, final và mock maker

- Method `private` không phải điểm stubbing/verification thông thường qua Mockito spy. Nên kiểm tra hành vi public hoặc tách trách nhiệm thật sự cần giả lập.
- Method `static` là lời gọi gắn với class; việc tạo spy của instance **không tự stub static method**. Mockito có API static mocking riêng (`mockStatic`) với phạm vi `MockedStatic`, nhưng chỉ nên dùng khi cần và phải đóng scope đúng cách.
- Với method/class `final`, **khả năng mock phụ thuộc phiên bản Mockito và mock maker**. Mockito 5 với inline mock maker thường hỗ trợ nhiều trường hợp final, trong khi cấu hình/phiên bản khác có thể không. Tránh quy tắc lỗi thời “Mockito tuyệt đối không mock được final”, cũng đừng giả định mọi API native/JVM đều có thể intercept an toàn.
- Constructor và phương thức native/special có giới hạn khác; spy không phải công cụ thay mọi loại side effect.

### 13.4. Spy không cô lập database, thread hay tài nguyên ngoài

Nếu một phương thức thật trên spy mở socket, tạo transaction, phát event hoặc đổi singleton state, việc spy object **không chặn những tác dụng phụ đó**. `doReturn` chỉ ngăn đúng method đã stub chạy trong lúc stubbing và khi invocation khớp. Để kiểm thử ổn định, dùng mock/fake ở boundary, database test chuyên dụng, Testcontainers hoặc môi trường kiểm soát được tùy mục tiêu.

### 13.5. Mocking quá nhiều nội bộ khiến test giá trị thấp

Ví dụ kiểm thử service nhưng stub `calculateDiscount()`, `validate()`, `mapResult()` rồi assert `process()` trả giá trị mong đợi. Những method quan trọng đã bị thay, nên test có thể chỉ chứng minh các stub được nối với nhau. Một refactor đổi tên helper có thể phá test dù behavior đúng. Hãy giữ logic nghiệp vụ chính chạy thật, chỉ giả lập dependency ngoài phạm vi.

### 13.6. Trạng thái và concurrency

Một spy có method thật phụ thuộc mutable state hoặc dùng chung giữa nhiều test dễ gặp rò rỉ trạng thái, đặc biệt nếu test chạy song song. Không nên chia sẻ một spy mutable giữa các phương thức test khi không cần. Mockito stubbing/verification có thể bị nhiễu nếu nhiều thread sửa chung mock/spy cùng lúc; tránh concurrent stubbing trên cùng object, kiểm tra side effect ở boundary xác định được.

## 14. Các API liên quan: `doNothing`, `doAnswer`, `doCallRealMethod`

Ngoài `doReturn` và `doThrow`, họ “do...” có những lựa chọn khác:

| API | Dùng khi | Lưu ý |
|---|---|---|
| `doNothing().when(mock).voidMethod()` | Muốn bỏ qua một void method | Với mock thuần, void method mặc định thường đã không làm gì; `doNothing` có thể thừa |
| `doNothing().when(spy).voidMethod()` | Muốn ngăn side effect của void method thật | Là stub có chủ đích; không dùng để che mọi tác dụng phụ nghiệp vụ |
| `doAnswer(answer).when(target).method(...)` | Cần logic phản hồi theo argument hoặc ghi nhận thông tin | Giữ answer đơn giản, tránh dựng một “hệ thống giả” khó đọc |
| `doCallRealMethod().when(mock).method(...)` | Cần gọi method thật cho một lời gọi trên mock nếu hợp lệ | Object mock có thể thiếu trạng thái do constructor không chạy |
| `doCallRealMethod().when(spy).method(...)` | Muốn bỏ stubbing cho method cụ thể và gọi real implementation | Vẫn có side effect thật; không phải cách reset toàn bộ spy |

Ví dụ dùng `doNothing` với `Counter`:

```java
Counter observed = spy(new Counter());
observed.increase();

doNothing().when(observed).reset();

observed.reset();
assertEquals(1, observed.value()); // Không reset vì đã stub void method
```

Đây là đoạn minh họa trong test sử dụng static imports `doNothing`, `spy`, `assertEquals`. Với `Counter` thật, không stub thì `reset()` đưa `value` về 0.

**Câu hỏi kiểm thử:** mình muốn chứng minh điều gì khi bỏ qua `reset`? Nếu mục tiêu nghiệp vụ là chứng minh reset hoạt động, việc `doNothing` sẽ làm mất logic cần kiểm tra. Nếu mục tiêu là test một bước khác mà reset chỉ là side effect không liên quan trong một hệ thống legacy, stub này có thể phù hợp tạm thời.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `IndexOutOfBoundsException` ngay tại `when(spy.get(0))` | Gọi `get(0)` thật trên list rỗng ở Arrange | `doReturn("A").when(spy).get(0)` hoặc test với list có dữ liệu |
| Repository/file/network bị gọi khi “chỉ đang stub” | `when(spy.method())` chạy method thật | Dùng `doReturn`/`doThrow` đúng method, hoặc mock dependency ngoài phạm vi |
| Exception từ stub cũ khi đổi stub | `when(spy.method())` kích hoạt stub đang ném lỗi | Dùng họ `doReturn/doThrow` để thay cấu hình |
| Không compile với `when(spy.voidMethod())` | `void` không thể là argument giá trị của `when` | Dùng `doThrow`/`doNothing`/`doAnswer` với void |
| Mockito báo kiểu trả về không tương thích | `doReturn(Object)` có thể làm mất kiểm tra generic ở Java compile time | Kiểm tra kiểu thật của method; với mock thuần ưu tiên `when().thenReturn()` khi có thể |
| Mockito từ chối checked exception | Exception không phù hợp với `throws` method | Chọn exception đúng contract và chữ ký; không tùy tiện thay bằng lỗi khác |
| Test đọc object gốc nhưng spy đã thay state | `spy(real)` không mặc định ủy quyền toàn bộ lên cùng instance | Dùng nhất quán spy; xem collaborator tham chiếu có bị chia sẻ không |
| Stub argument cụ thể không có hiệu lực | Lời gọi runtime dùng argument khác | Kiểm tra đúng input; dùng matcher có chủ đích, tránh quá rộng |
| `@Spy` field null/không phải Mockito spy | Chưa kích hoạt MockitoExtension/MockitoAnnotations | Khởi tạo annotation đúng cách hoặc dùng `spy(new ...)` |
| Stub trên Spring bean không hoạt động như mong đợi | Nhầm spy thuần với bean proxy/annotation theo phiên bản | Kiểm tra Spring context, proxy, bean override và AOP advice |
| `verify` method private/static/final hành xử bất ngờ | Giới hạn method/mocking engine hoặc đang verify sai object | Kiểm tra loại method, Mockito version/mock maker, và behavior thực cần bảo vệ |
| Test đỏ sau refactor dù API vẫn đúng | Test phụ thuộc helper/call count nội bộ | Đưa assertion ra kết quả, lỗi hoặc side effect công khai |

Đừng “chữa” một bài test bằng cách stub thêm mọi method chỉ để test xanh. Nếu một test liên tục đòi mở rộng spy, rất có thể trách nhiệm của class chưa được tách rõ hoặc test đang kiểm tra implementation thay vì requirement.

## 16. Khi nào dùng spy, khi nào tránh?

Dùng các câu hỏi sau để quyết định:

1. **Có thật sự cần chạy phần lớn method thật của đối tượng không?** Nếu không, mock dependency riêng thường đủ.
2. **Method cần thay có phải I/O hoặc collaborator bên ngoài có thể tách bằng interface không?** Nếu có thể, ưu tiên constructor injection để code dễ test và dễ bảo trì.
3. **Đối tượng có trạng thái phức tạp hay side effect khi khởi tạo/gọi method thật không?** Nếu có, spy làm test khó dự đoán.
4. **Test đang bảo vệ hành vi nghiệp vụ hay chỉ `verify` chuỗi call nội bộ?** Hãy ưu tiên giá trị trả về, exception, dữ liệu lưu và tác dụng phụ được quy định.
5. **Có cần Spring proxy/transaction/async/cache thật để xác minh hành vi không?** Nếu có, sử dụng test context/integration và assert boundary thay vì spy plain Java.
6. **Spy có giúp chuyển tiếp an toàn khi refactor legacy không?** Nếu có, ghi nhận seam tạm và kế hoạch tách collaborator khi có điều kiện.

**Phù hợp:** kiểm tra một phép render thật trong lớp legacy nhưng chặn đúng method đọc file; theo dõi một cổng public có ý nghĩa, hoặc tạm thay một đường đi đắt khi đang chuyển thiết kế cũ.

**Thường không phù hợp:** spy chính service nghiệp vụ rồi stub hết validation/tính toán; spy mọi Spring bean vì muốn “giống production”; spy object thực có side effect khó kiểm soát; spy để verify private/helper đã gọi đúng số lần trong khi response cuối cùng mới là contract.

## 17. Chạy ví dụ với JUnit Jupiter, Mockito và Spring Boot

Trong project Spring Boot 3.x/Java 17+ dùng Gradle và quản lý phiên bản dependency qua Spring Boot plugin/BOM, có thể dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` trong Spring Boot 3.x cung cấp JUnit Jupiter và Mockito, gồm `MockitoExtension` qua tích hợp test. Các ví dụ unit ở mục 4–11 có thể dùng `testImplementation 'org.springframework.boot:spring-boot-starter-test'` và không bắt buộc khởi chạy Spring. Nếu module đã khai báo starter/dependency tương ứng thì không thêm lặp.

**Thư mục và lệnh chạy:**

```text
src/main/java/com/example/testing/
    Counter.java
    LegacyReportGenerator.java
    TemplateSource.java
    ReportService.java
    TextStore.java
src/test/java/com/example/testing/
    CounterSpyTest.java
    CounterFailureTest.java
    TextStoreTest.java
    LegacyReportGeneratorTest.java
    ReportServiceTest.java
    AnnotatedCounterSpyTest.java
```

```bash
./gradlew test --tests com.example.testing.CounterSpyTest --tests com.example.testing.CounterFailureTest --tests com.example.testing.TextStoreTest --tests com.example.testing.LegacyReportGeneratorTest --tests com.example.testing.ReportServiceTest --tests com.example.testing.AnnotatedCounterSpyTest
```

Trên Windows PowerShell, dùng `.\gradlew.bat`; với multi-project Gradle, chỉ rõ task module, ví dụ `:your-module:test` khi module đó thực sự tồn tại. Các class được tách vào file đúng tên, đúng package, Java 17+ chạy được với các dependency đã nói.

**Kết quả kỳ vọng:** tất cả phương thức test hoàn thành mà không có assertion failure; Gradle in `BUILD SUCCESSFUL` trong môi trường đã cấu hình đúng. Test JUnit trong ví dụ không có stdout nghiệp vụ cố định. Đây là kết quả **dự kiến theo mã ví dụ**, không phải khẳng định đã chạy test trên workspace cụ thể. Các đoạn **PHẢN VÍ DỤ** và **minh họa chưa độc lập** không phải file bổ sung trong danh sách chạy.

Xem báo cáo tại `build/reports/tests/test/index.html` hoặc `build/test-results/test/` trong build directory của module. Nếu gặp lỗi stubbing, xem stack trace ở thời điểm Arrange để biết method thật có chạy trước Act hay không.

## 18. Bài tập thực hành

### Bài tập A — tìm lỗi trước bước Act

Đọc đoạn sau:

```java
List<String> observed = spy(new ArrayList<>());
when(observed.get(0)).thenReturn("first");
assertEquals("first", observed.get(0));
```

1. Lệnh nào chạy logic thật khi đang stub?
2. Exception nào có khả năng xảy ra và vì sao?
3. Sửa bằng `doReturn` và giải thích vì sao assertion sau đó pass.

**Đáp án định hướng:** `observed.get(0)` trong `when(...)` chạy thật trên list rỗng và ném `IndexOutOfBoundsException`. Dùng `doReturn("first").when(observed).get(0)` để bỏ qua lời gọi thật khi setup.

### Bài tập B — kiểm chứng trạng thái tại stubbing

Với class `Counter` của bài, viết hai test: một dùng `when(spy.increase()).thenReturn(10)`, một dùng `doReturn(10).when(spy).increase()`. Sau pha stubbing, assert trạng thái lần lượt là **1** và **0**. Sau đó gọi `increase` và quan sát cả hai trả **10** mà không tăng counter thêm.

### Bài tập C — lỗi của phương thức void

Dùng spy của `Counter`, tăng bộ đếm lên 1, sau đó cấu hình `doThrow(new IllegalStateException("blocked")).when(spy).reset()`. Kiểm tra:

- Pha stubbing không gọi reset thật.
- Khi gọi `reset`, test bắt được `IllegalStateException` bằng `assertThrows`.
- Giá trị counter vẫn bằng 1 sau exception.

Giải thích vì sao `when(spy.reset()).thenThrow(...)` không biên dịch.

### Bài tập D — nhận diện giải pháp thiết kế tốt hơn

Lớp `InvoiceService` vừa truy vấn database, vừa tính thuế, vừa gửi email, và test dùng spy để stub cả ba helper. Đề xuất ranh giới dependency (repository, tax policy, email port). Nêu phần logic nào cần chạy thật trong unit test, phần nào có thể mock, và khi nào cần integration test với database thật.

### Bài tập E — Spring AOP và spy

Một bean `@Transactional` có hai public method; method A gọi method B bằng `this.methodB()`. Một spy unit test intercept được call đến B. Có thể từ đó kết luận advice transaction của Spring được áp dụng cho B ở production không?

**Đáp án định hướng:** Không. Mockito interception và lời gọi qua Spring AOP proxy là hai cơ chế khác nhau; self-invocation trong Spring AOP thường bypass proxy. Phải thiết kế integration test qua boundary thực nếu muốn khẳng định hành vi transaction.

## 19. Checklist trước khi chấp nhận một spy test

- [ ] Tôi nêu được lý do thật sự cần **spy** thay cho mock dependency hoặc object thật.
- [ ] Tôi hiểu method chưa stub sẽ chạy thật và có thể tạo side effect.
- [ ] Với spy, tôi dùng `doReturn`/`doThrow` khi không được phép gọi method thật trong Arrange.
- [ ] Với `void`, tôi không cố đưa lời gọi vào `when(voidMethod())`.
- [ ] Loại exception được stub phù hợp với chữ ký method, nhất là checked exception.
- [ ] Tôi không nhầm spy với object gốc; trạng thái và collaborator được kiểm soát.
- [ ] Stub có argument đúng và không quá rộng đến mức che hành vi sai.
- [ ] Tôi không cố stub private method hoặc giả định mọi final/static/native method đều giống nhau trên mọi mock maker.
- [ ] Tôi không coi Mockito spy là phương tiện thay thế Spring proxy/transaction/async behavior.
- [ ] Tôi chạy **logic thật đang cần kiểm tra**; mock/stub chỉ áp dụng ở boundary có lý do.
- [ ] Assertion xác nhận kết quả, lỗi hoặc side effect thuộc contract, thay vì chỉ số lần gọi helper.
- [ ] Test ổn định khi refactor nội bộ không đổi hành vi; kiểm thử tích hợp vẫn bảo vệ ranh giới thực cần thiết.

**Ghi nhớ:** `doReturn` và `doThrow` giúp cấu hình spy **mà không vô tình chạy method thật ở bước stubbing**. Chúng không loại bỏ những giới hạn của partial mock: state, I/O, AOP proxy, khả năng intercept và nguy cơ test bám cách triển khai. Với mã mới, ưu tiên tách dependency và kiểm thử hành vi thông qua hợp đồng rõ ràng; dùng spy có chủ đích, thường là để kiểm tra hoặc chuyển tiếp an toàn với code legacy.

### Tài liệu đối chiếu

- Mockito 5 Javadoc: https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html — mục *Spying on real objects*, *doReturn/doThrow family*.
- Spring Framework TestContext: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html — `@MockitoSpyBean` và hành vi bean override/AOP.
- Spring Boot 3.3 Javadoc: https://docs.spring.io/spring-boot/docs/3.3.0/api/org/springframework/boot/test/mock/mockito/SpyBean.html — annotation `@SpyBean` dùng trong nhánh Boot 3.3.
