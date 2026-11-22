# Mockito: when–thenReturn, thenThrow và mô phỏng nhiều lần gọi

## 1. Mục tiêu bài học và ngữ cảnh Spring Boot

Trong kiểm thử Java/Spring Boot, **Mockito** giúp mô phỏng hành vi của một dependency để test phần logic mà không cần truy cập database, HTTP service, queue hoặc file system thật. Hai nhóm thao tác cần phân biệt:

- **Stubbing (cấu hình phản hồi):** chỉ định mock phải làm gì khi nhận một lời gọi phù hợp, chẳng hạn `when(repository.findName("A")).thenReturn("Lan")`.
- **Verification (xác minh tương tác):** kiểm tra mã đang test thực sự đã gọi mock bao nhiêu lần, với đối số nào và (khi quan trọng) theo thứ tự nào, ví dụ `verify(repository, times(2)).findName("A")`.

`when(...).thenReturn(...)` cho kết quả bình thường; `when(...).thenThrow(...)` mô phỏng lỗi. **Consecutive stubbing** cho phép nhiều lần gọi **cùng một phương thức và cùng điều kiện khớp đối số** trả về các kết quả khác nhau theo thứ tự: thất bại trước, thành công sau; hết dữ liệu; hoặc một chuỗi trạng thái.

Bài học áp dụng cho các tình huống phổ biến:

1. Repository/mock trả một giá trị cố định.
2. Remote client gặp lỗi tạm thời, lần gọi lại thành công.
3. Một dependency trả các giá trị khác nhau ở lần 1, 2, 3 và sau đó.
4. Service dừng retry sau số lần tối đa; cần kiểm chứng số lời gọi thật.
5. Phương thức `void` ném lỗi; checked exception; spy gọi phương thức thật trong lúc setup.
6. Mock dựa vào đối số hoặc trạng thái khi chuỗi cố định không đủ.
7. Phân biệt mocked unit test với kiểm thử thật về HTTP timeout, retry policy và tính nhất quán.

**Nguyên tắc:** Stub thể hiện dữ liệu/điều kiện ban đầu; assertion thể hiện kết quả của code; verification thể hiện tương tác quan trọng. Stub đúng nhưng code không hề gọi dependency **không chứng minh nghiệp vụ đúng**.

## 2. API cơ bản: when, thenReturn, thenThrow

Mockito thường dùng các static methods sau:

| API | Ý nghĩa | Mẫu |
| --- | --- | --- |
| `mock(Type.class)` | Tạo mock của type | `Client client = mock(Client.class);` |
| `when(mock.call(args))` | Bắt đầu định nghĩa hành vi của một lời gọi **có giá trị trả về** | `when(client.read("A"))` |
| `thenReturn(value)` | Trả về giá trị | `when(client.read("A")).thenReturn("ok");` |
| `thenThrow(exception)` | Ném exception đã chỉ định | `when(client.read("A")).thenThrow(new IllegalStateException());` |
| `thenThrow(ExceptionType.class)` | Mockito tạo ngoại lệ thuộc loại được chỉ định khi gọi | `when(client.read("A")).thenThrow(IllegalStateException.class);` |
| `thenAnswer(answer)` | Tính phản hồi động theo invocation | `when(client.read(anyString())).thenAnswer(inv -> ...);` |
| `doThrow(...).when(mock).voidMethod()` | Mô phỏng lỗi với phương thức trả về `void` | `doThrow(new IllegalStateException()).when(client).reset();` |
| `verify(mock, times(n)).call(args)` | Xác minh đúng `n` lời gọi phù hợp | `verify(client, times(2)).read("A");` |
| `InOrder` | Xác minh thứ tự tương tác nếu thứ tự thuộc hợp đồng | `InOrder order = inOrder(client);` |

### Một phản hồi cố định

```java
Client client = mock(Client.class);
when(client.read("A")).thenReturn("READY");

String result = client.read("A");  // "READY"
String again = client.read("A");   // "READY"

verify(client, times(2)).read("A");
```

Đây là **trích đoạn**: `Client` và `read` là giao diện minh họa, chưa phải Java class độc lập; ví dụ chạy được hoàn chỉnh ở phần 7.

Ở regular mock, `when(client.read("A"))` **không thực hiện I/O thật**; Mockito nhận diện invocation và lưu behavior. Nếu chưa stub một method, mock thường trả giá trị mặc định theo type (ví dụ `null` cho một tham chiếu thông thường, `false` cho `boolean`, `0` cho `int`; một số kiểu được Mockito hỗ trợ trả đối tượng rỗng). Đừng phụ thuộc vào default thay cho việc stub rõ ràng một hợp đồng quan trọng.

### Mô phỏng exception

```java
when(client.read("A"))
    .thenThrow(new IllegalStateException("Remote unavailable"));

assertThrows(IllegalStateException.class, () -> client.read("A"));
```

`thenThrow` phù hợp khi method **có giá trị trả về**. Trong stub của regular mock, lỗi sẽ được ném khi **method thực sự được gọi**, không phải ngay khi khai báo `thenThrow`. Nếu code không chạm vào dependency, sẽ không có exception. Điều kiện này giúp test logic xử lý lỗi của service thay vì test trực tiếp mock.

## 3. Mô phỏng các lần gọi liên tiếp bằng thenReturn

Có hai cú pháp chính, **tương đương về ý nghĩa**:

```java
when(client.read("A")).thenReturn("one", "two", "three");
```

```java
when(client.read("A"))
    .thenReturn("one")
    .thenReturn("two")
    .thenReturn("three");
```

Hành vi:

| Lần gọi `client.read("A")` | Giá trị |
| --- | --- |
| 1 | `"one"` |
| 2 | `"two"` |
| 3 | `"three"` |
| 4 | `"three"` |
| 5, 6, ... | `"three"` |

**Quy tắc cực quan trọng:** sau khi các kết quả được liệt kê đã dùng hết, **hành vi cuối cùng được lặp cho các lần gọi tiếp theo**. Mockito không mặc định trả `null` hoặc báo hết chuỗi. Tương tự, nếu kết thúc bằng `thenThrow`, các lời gọi kế tiếp tiếp tục ném lỗi cuối cùng.

### Hệ quả với test

- Để biết service có thực sự gọi ba lần, phải `verify(client, times(3)).read("A")`.
- Dùng `thenReturn("one","two")` **không** có nghĩa dependency chỉ được phép gọi hai lần.
- Trong bài test kiểm tra retry, đôi khi chỉ muốn “lỗi lần đầu, thành công lần hai”; verification phải chứng minh service **dừng** sau thành công.
- Sequence thuộc **mock + method + điều kiện khớp đối số**: `read("A")` và `read("B")` có thể có hai stub độc lập.

### Không nhầm với khai báo lại một stub

```java
when(client.read("A")).thenReturn("one");
when(client.read("A")).thenReturn("two");
```

Trường hợp này là **hai lần khai báo stub cùng lời gọi**, thường kết quả của lời gọi sau được ưu tiên, không có “one rồi two”. Muốn tuần tự, gọi `thenReturn("one","two")` hoặc nối `thenReturn` trên **cùng** một `OngoingStubbing`.

Cần lưu ý thêm: nếu stub đầu tiên ném exception, việc cố gắng viết `when(client.read("A")).thenReturn("new")` ở lần khai báo thứ hai có thể khiến exception được kích hoạt ngay khi setup lại. Dùng `doReturn("new").when(client).read("A")` nếu thật sự cần thay stub đã ném exception, nhưng cách tốt hơn là tạo mock mới cho test mới thay vì ghi đè hành vi phức tạp.

## 4. Phối hợp thenThrow và thenReturn để kiểm tra retry

Giả sử remote catalog đôi khi bị gián đoạn: lần đầu ném `TemporaryFailure`, lần thứ hai trả dữ liệu. Stub đúng:

```java
when(client.read("SKU-1"))
    .thenThrow(new TemporaryFailure("timeout"))
    .thenReturn("Giá sản phẩm: 100");

String result = service.loadWithRetry("SKU-1", 3);

assertEquals("Giá sản phẩm: 100", result);
verify(client, times(2)).read("SKU-1");
```

Đây là trích đoạn dùng `service` và `TemporaryFailure` được định nghĩa ở phần 7. Nếu `loadWithRetry` chỉ retry đúng loại lỗi tạm thời rồi dừng khi thành công, lần 1 thất bại, lần 2 thành công. Mặc dù cấu hình cho phép các lần tiếp theo vẫn trả cùng giá trị thành công, code **không nên gọi lần thứ ba**.

Các chuỗi phổ biến:

| Kịch bản | Stub | Kỳ vọng tương tác |
| --- | --- | --- |
| Thành công ngay | `thenReturn("ok")` | Gọi 1 lần |
| Lỗi tạm thời rồi thành công | `thenThrow(new TemporaryFailure()).thenReturn("ok")` | Gọi 2 lần |
| Hai lỗi rồi thành công | `thenThrow(e1).thenThrow(e2).thenReturn("ok")` | Gọi 3 lần nếu retry budget cho phép |
| Cả ba lần đều lỗi | `thenThrow(new TemporaryFailure("down"))` | Service ném lỗi sau 3 lần, verify `times(3)` |
| Thành công rồi lỗi ở lần kế | `thenReturn("ok").thenThrow(e)` | Chỉ thể hiện lỗi nếu service thực sự gọi thêm |
| Hai giá trị rồi cố định | `thenReturn("A","B")` | Các lần từ thứ 2 đều là `"B"` |
| Chuỗi exception | `thenThrow(e1, e2)` | Lần 1 ném `e1`; từ lần 2 ném `e2` nếu không có behavior khác |

Nếu **ngân sách retry** là “tối đa ba lần gọi”, cần thống nhất nó là **3 attempts tổng cộng** hay “1 lần đầu + 3 retries” (= 4 attempts). Đây là chi tiết hợp đồng mà test phải ghi rõ. Trong ví dụ phần 7, tham số `maxAttempts=3` có nghĩa là **tối đa 3 lời gọi tổng cộng**.

### Exception cuối cùng có thể tiếp tục lặp

```java
when(client.read("A"))
    .thenReturn("first")
    .thenThrow(new IllegalStateException("outage"));
```

- Lần 1: trả `first`.
- Lần 2: ném `IllegalStateException`.
- Lần 3 trở đi: tiếp tục ném exception theo hành vi cuối.
- Nếu muốn mô phỏng “lỗi hai lần, sau đó thành công”, thứ tự phải là `thenThrow(e1).thenThrow(e2).thenReturn("ok")`.

Không lấy “đã cấu hình 3 kết quả” làm bằng chứng rằng service gọi 3 lần. `verify` và kết quả trả về mới là bằng chứng.

## 5. Checked exception, unchecked exception và điều kiện ném lỗi

Java phân biệt:

- **Unchecked exception**: `RuntimeException` và các lớp con; thường có thể mô phỏng với `thenThrow` mà không cần method khai báo `throws`.
- **Checked exception**: ví dụ `IOException`; Mockito yêu cầu loại checked exception **phù hợp với khai báo `throws` của method được stub**, nếu không sẽ báo lỗi cấu hình stub. Chạy kiểm tra compiler/Mockito theo chữ ký thật.

Ví dụ hợp lệ:

```java
interface FileGateway {
    String download(String path) throws java.io.IOException;
}
```

```java
FileGateway gateway = mock(FileGateway.class);

when(gateway.download("report.txt"))
    .thenThrow(new java.io.IOException("Network failed"))
    .thenReturn("OK");
```

Trong ngữ cảnh Java, method test chứa lời gọi `when(gateway.download(...))` cần khai báo `throws IOException` hoặc xử lý checked exception vì biểu thức Java vẫn có chữ ký `throws`. Một test hoàn chỉnh xuất hiện ở phần 7.

Ví dụ **sai hợp đồng**:

```java
interface SimpleGateway {
    String ping(); // Không khai báo throws IOException.
}
// Mockito không cho stub ping() ném IOException checked không được khai báo:
// when(mock.ping()).thenThrow(new IOException("x"));
```

Trường hợp này không phải “HTTP simulation thành công”, mà là lỗi định nghĩa test. Trong adapter thực tế có thể cần ném unchecked wrapper như `RemoteServiceUnavailableException` hoặc cấu hình đúng phương thức `throws IOException`.

Với `thenThrow(SomeException.class)`, Mockito tạo exception thuộc class đó lúc được gọi; với instance `thenThrow(new SomeException("message"))`, test có thể assert message ổn định hơn. Không nên assert toàn bộ stack trace từ exception được mock; chi tiết stack trace phụ thuộc cách tạo exception/JVM.

## 6. Phương thức void: doThrow, doNothing và chuỗi hành vi

`when(mock.voidMethod())` **không biên dịch**, vì `void` không phải giá trị truyền được vào `when(T)`. Dùng họ API `do...when(...)`:

```java
Notifier notifier = mock(Notifier.class);
doThrow(new IllegalStateException("service stopped"))
    .when(notifier).send("message");

assertThrows(IllegalStateException.class,
    () -> notifier.send("message"));
```

`Notifier` là interface minh họa: test runnable ở phần 7 có phương thức `evict`.

Với regular mock, `void` mặc định thường **không làm gì**, nên `doNothing()` một mình thường không cần. Nó hữu ích khi cần xâu chuỗi hành vi:

```java
doThrow(new IllegalStateException("busy"))
    .doNothing()
    .when(notifier).send("message");
```

Khi gọi `send("message")`:

- Lần 1: ném `IllegalStateException`.
- Lần 2: không làm gì.
- Từ lần 3: tiếp tục hành vi cuối (`doNothing`) trong cùng stub.
- Có thể ghép các phương thức `doThrow`/`doNothing`/`doAnswer` trên cùng một `Stubber` nếu cần kịch bản nhiều bước.

**Cảnh báo:** `doThrow` không “bỏ qua” quy tắc checked exception. Nếu dùng `doThrow(new IOException())` cho method `void send()` không khai báo `throws IOException`, Mockito sẽ từ chối checked exception không hợp lệ. Với `void` khai báo `throws IOException`, mới có thể stub bằng `doThrow(new IOException(...))`.

## 7. Bài thực hành hoàn chỉnh: JUnit Jupiter + Mockito + Java 17

Ví dụ này kiểm thử mock và một service retry nhỏ, **không cần database, network hoặc khởi động Spring context**. Dùng Spring Boot 3.5.0 làm phiên bản mẫu để Spring Boot BOM quản lý Mockito/JUnit. Trong dự án thực tế, giữ Spring Boot version hiện có và chỉ thêm `spring-boot-starter-test` ở test scope; không sao chép số version một cách máy móc.

### 7.1. Cấu trúc

```text
mockito-sequence-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── MockitoSequenceTest.java
```

### 7.2. Tệp pom.xml hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>mockito-sequence-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 7.3. Tệp src/test/java/example/MockitoSequenceTest.java

```java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class MockitoSequenceTest {

    interface RemoteCatalog {
        String read(String key);
        void evict(String key);
        String download(String path) throws IOException;
    }

    static final class TemporaryFailure extends RuntimeException {
        TemporaryFailure(String message) {
            super(message);
        }
    }

    static final class CatalogService {
        private final RemoteCatalog remote;

        CatalogService(RemoteCatalog remote) {
            this.remote = remote;
        }

        // maxAttempts là tổng số lần gọi, bao gồm lần đầu.
        String loadWithRetry(String key, int maxAttempts) {
            if (maxAttempts < 1) {
                throw new IllegalArgumentException("maxAttempts must be >= 1");
            }

            for (int attempt = 1; attempt <= maxAttempts; attempt++) {
                try {
                    return remote.read(key);
                } catch (TemporaryFailure ex) {
                    if (attempt == maxAttempts) {
                        throw ex;
                    }
                }
            }

            throw new IllegalStateException("unreachable");
        }
    }

    @Test
    void oneStubReturnsSameResultOnEachCall() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        when(remote.read("A")).thenReturn("READY");

        assertEquals("READY", remote.read("A"));
        assertEquals("READY", remote.read("A"));

        verify(remote, times(2)).read("A");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void thenReturnSequenceRepeatsTheLastValue() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        when(remote.read("A")).thenReturn("one", "two", "three");

        assertEquals("one", remote.read("A"));
        assertEquals("two", remote.read("A"));
        assertEquals("three", remote.read("A"));
        assertEquals("three", remote.read("A"));

        verify(remote, times(4)).read("A");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void transientFailureThenSuccessNeedsExactlyTwoCalls() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        when(remote.read("SKU-1"))
                .thenThrow(new TemporaryFailure("temporary outage"))
                .thenReturn("DATA");

        CatalogService service = new CatalogService(remote);

        assertEquals("DATA", service.loadWithRetry("SKU-1", 3));
        verify(remote, times(2)).read("SKU-1");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void persistentTransientFailureStopsAfterThreeAttempts() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        when(remote.read("SKU-2"))
                .thenThrow(new TemporaryFailure("still down"));

        CatalogService service = new CatalogService(remote);

        TemporaryFailure ex = assertThrows(TemporaryFailure.class,
                () -> service.loadWithRetry("SKU-2", 3));
        assertEquals("still down", ex.getMessage());
        verify(remote, times(3)).read("SKU-2");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void voidMethodCanThrowAndThenDoNothing() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        doThrow(new IllegalStateException("busy"))
                .doNothing()
                .when(remote).evict("SKU-3");

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> remote.evict("SKU-3"));
        assertEquals("busy", ex.getMessage());

        remote.evict("SKU-3");
        remote.evict("SKU-3");

        verify(remote, times(3)).evict("SKU-3");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void checkedIOExceptionCanBeStubbedWhenDeclared() throws IOException {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        when(remote.download("report.txt"))
                .thenThrow(new IOException("network"))
                .thenReturn("REPORT");

        IOException ex = assertThrows(IOException.class,
                () -> remote.download("report.txt"));
        assertEquals("network", ex.getMessage());
        assertEquals("REPORT", remote.download("report.txt"));

        verify(remote, times(2)).download("report.txt");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void thenAnswerCanUseAnInvocationCounter() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        AtomicInteger count = new AtomicInteger();

        when(remote.read("SKU-4")).thenAnswer(invocation -> {
            int attempt = count.incrementAndGet();
            if (attempt == 1) {
                throw new TemporaryFailure("first call failed");
            }
            return "DATA-" + attempt;
        });

        CatalogService service = new CatalogService(remote);

        assertEquals("DATA-2", service.loadWithRetry("SKU-4", 3));
        assertEquals(2, count.get());
        verify(remote, times(2)).read("SKU-4");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void differentArgumentsHaveIndependentStubs() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        when(remote.read("A")).thenReturn("A1", "A2");
        when(remote.read("B")).thenReturn("B1", "B2");

        assertEquals("A1", remote.read("A"));
        assertEquals("B1", remote.read("B"));
        assertEquals("A2", remote.read("A"));
        assertEquals("B2", remote.read("B"));

        verify(remote, times(2)).read("A");
        verify(remote, times(2)).read("B");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void doReturnAvoidsInvokingRealMethodOnSpyDuringSetup() {
        List<String> listSpy = spy(new ArrayList<>());
        doReturn("virtual").when(listSpy).get(0);

        assertEquals("virtual", listSpy.get(0));
        verify(listSpy).get(0);
        verifyNoMoreInteractions(listSpy);
    }
}
```

### 7.4. Chạy test và kết quả dự kiến

Ở thư mục có `pom.xml`:

```bash
mvn test
```

Hoặc chỉ chạy class này:

```bash
mvn test -Dtest=MockitoSequenceTest
```

**Kỳ vọng:** 9 test methods `@Test` đều PASS; không có `System.out.println`, nên không có stdout ứng dụng cố định. Maven Surefire sẽ tổng hợp số test và kết quả trong `target/surefire-reports`. Những ví dụ ở trên đã xác định rõ thứ tự stubbing và số lần gọi; kết quả cụ thể của Maven phụ thuộc phiên bản plugin và cấu hình logging.

Các tình huống được bao phủ:

| Test method | Stub | Assertion chính | Verification |
| --- | --- | --- | --- |
| `oneStubReturnsSameResultOnEachCall` | Một `thenReturn` | Cả hai lần đều `READY` | `times(2)` |
| `thenReturnSequenceRepeatsTheLastValue` | `one,two,three` | Lần 4 vẫn `three` | `times(4)` |
| `transientFailureThenSuccessNeedsExactlyTwoCalls` | Lỗi rồi dữ liệu | Retry service trả `DATA` | `times(2)` |
| `persistentTransientFailureStopsAfterThreeAttempts` | Lỗi luôn | Service ném lỗi sau lần 3 | `times(3)` |
| `voidMethodCanThrowAndThenDoNothing` | `doThrow` rồi `doNothing` | Chỉ lần đầu ném | `times(3)` |
| `checkedIOExceptionCanBeStubbedWhenDeclared` | `IOException` rồi chuỗi | Lỗi rồi `REPORT` | `times(2)` |
| `thenAnswerCanUseAnInvocationCounter` | Đếm lời gọi động | `DATA-2` | `times(2)` |
| `differentArgumentsHaveIndependentStubs` | Hai key, hai sequence | A1/B1/A2/B2 | Mỗi key 2 lần |
| `doReturnAvoidsInvokingRealMethodOnSpyDuringSetup` | Stub spy không gọi phương thức thật khi setup | Trả `virtual` từ list rỗng | `get(0)` 1 lần |

Bài demo đặt helper classes bên trong test để chạy độc lập. Trong ứng dụng thực, chuyển `CatalogService` và `RemoteCatalog` sang `src/main/java`, import vào test và để mock chỉ mô phỏng boundary. Không đưa Mockito vào production classpath nếu không có yêu cầu đặc biệt.

## 8. when(...).thenReturn và doReturn(...).when khác nhau ở đâu?

Với mock thông thường, ưu tiên `when(...).thenReturn(...)` vì dễ đọc, có kiểm tra kiểu trả về ở compile time. Tuy nhiên với **spy** (một object bọc/copy để giữ một phần behavior thật), lời gọi trong `when(spy.realMethod())` có thể **thực thi phương thức thật ngay lúc cấu hình**.

Ví dụ:

```java
List<String> spyList = spy(new ArrayList<>());

// KHÔNG AN TOÀN: list trống, spyList.get(0) có thể ném lỗi ngay lúc stub.
// when(spyList.get(0)).thenReturn("virtual");

// AN TOÀN: không gọi get(0) thật trong lúc setup.
doReturn("virtual").when(spyList).get(0);
assertEquals("virtual", spyList.get(0));
```

**Spy có side effect** (gọi DB, ghi file, tăng counter...) khiến `when(spy.call())` rất nguy hiểm. Nếu cần partial mocking, cân nhắc `doReturn` / `doThrow` / `doAnswer`; nhưng đa số test có thể thiết kế gọn hơn bằng inject dependency vào service và mock dependency, không spy chính class nghiệp vụ.

`doReturn` nhận `Object` nên không được trình biên dịch kiểm tra type chặt như `thenReturn`; lỗi type có thể xuất hiện lúc chạy. Chỉ dùng nó khi mang lại lợi ích thực sự.

Mockito cũng hỗ trợ sequential stubbing ở dạng `doReturn("one","two").when(mock).getValue()`; nó hữu ích với spies hoặc khi ghi đè một stub đã ném exception. Với regular mock, dạng `when(...).thenReturn("one","two")` thường rõ ràng hơn.

## 9. Matchers, nhiều đối số và phạm vi của một chuỗi

Stub khớp theo **method + matcher/đối số**. Khi không khớp, mock dùng behavior mặc định hoặc một stub khác phù hợp. Xem ví dụ:

```java
when(client.read("A")).thenReturn("A1", "A2");
when(client.read("B")).thenReturn("B1", "B2");

client.read("A"); // A1
client.read("B"); // B1
client.read("A"); // A2
client.read("B"); // B2
```

Hai chuỗi không tiêu thụ trạng thái của nhau trong tình huống stub độc lập như trên.

### Khi dùng matchers cho nhiều tham số

Giả sử mock có `String find(String tenant, int version)`:

```java
when(mock.find(eq("tenant-1"), anyInt()))
    .thenReturn("v1", "v2");
```

Đây là **trích đoạn**, cần static imports `org.mockito.ArgumentMatchers.eq` và `anyInt`. Nếu dùng matcher cho một tham số, các tham số còn lại trong cùng invocation cũng cần matcher (`eq(...)` cho giá trị cố định), chẳng hạn:

```java
// SAI: trộn matcher anyInt() và literal "tenant-1".
// when(mock.find("tenant-1", anyInt())).thenReturn("x");

// ĐÚNG:
when(mock.find(eq("tenant-1"), anyInt())).thenReturn("x");
```

`anyString()` của Mockito hiện đại thường khớp chuỗi **khác null**, nên nếu muốn mô phỏng input `null`, phải dùng `isNull()` hoặc matcher phù hợp; không suy diễn rằng every matcher khớp mọi giá trị. Sequence ở matcher rộng như `anyString()` có thể bị tiêu thụ bởi các key khác nhau cùng khớp matcher; nếu mỗi key cần sequence độc lập, stub riêng theo key hoặc dùng `thenAnswer` giữ trạng thái theo key.

### Stub chồng lấn

Các stub có thể chồng lấn:

```java
when(client.read(anyString())).thenReturn("generic");
when(client.read("A")).thenReturn("specific");
```

Với một regular mock trong ví dụ này, stub đặc thù khai báo sau được ưu tiên cho `"A"`; các key khác dùng stub chung. Nhưng nếu có nhiều stub rộng/hẹp chồng lấn hoặc override một stub đã ném lỗi, thứ tự khai báo có thể làm test khó hiểu. Hạn chế overlap và xác định rõ điều kiện từng stub.

### Verification theo số lần và thứ tự

`verify(mock, times(3)).call()` xác nhận số lời gọi, **không** tự chứng minh lời gọi diễn ra đúng thứ tự so với các phương thức khác. Khi thứ tự là requirement, dùng `InOrder`:

```java
InOrder order = inOrder(mock);
order.verify(mock).begin();
order.verify(mock).commit();
```

Đây là trích đoạn minh họa; `mock` phải có hai method `begin` và `commit`, static import `inOrder` hoặc gọi `Mockito.inOrder`, và code đang test phải gọi cả hai. `InOrder` không bắt buộc nếu chỉ cần đếm số lần gọi cùng một method. Không assert thứ tự không thuộc hợp đồng: test dễ trở nên brittle khi refactor implementation.

Một cách đọc các mode:

| Verification | Điều kiện |
| --- | --- |
| `verify(mock).read("A")` | Đúng 1 lần mặc định |
| `verify(mock, times(2)).read("A")` | Chính xác 2 lần |
| `verify(mock, never()).read("A")` | Không có lần gọi phù hợp |
| `verify(mock, atLeastOnce()).read("A")` | Ít nhất 1 lần |
| `verifyNoInteractions(mock)` | Mock không có tương tác được ghi nhận |
| `verifyNoMoreInteractions(mock)` | Không còn tương tác chưa được verify |

Không nhầm `verifyNoMoreInteractions` với test business correctness: nó kiểm tra chi tiết tương tác và có thể cần bỏ nếu các tương tác bổ sung hợp lệ được thêm sau này.

## 10. Mô phỏng động bằng thenAnswer khi một dãy cố định không đủ

`thenReturn` phù hợp nếu danh sách kết quả **biết trước** và ngắn. Với dữ liệu phụ thuộc tham số, số lần retry hoặc một trạng thái trong bộ giả lập, dùng `thenAnswer`:

```java
AtomicInteger counter = new AtomicInteger();

when(client.read(anyString())).thenAnswer(invocation -> {
    String key = invocation.getArgument(0, String.class);
    int n = counter.incrementAndGet();
    if (n == 1) {
        throw new TemporaryFailure("temporary");
    }
    return key + "-value-" + n;
});
```

Đây là trích đoạn sử dụng `TemporaryFailure` minh họa, static imports `anyString`/`when` và `AtomicInteger`. Sau lần 1 ném lỗi, lần 2 trả chuỗi có key và số `2`. Tuy nhiên **counter là toàn cục cho mock**, nên nếu gọi key khác, số đếm vẫn tăng. Nếu cần đếm riêng từng key, lưu counter trong `Map<String, Integer>` hoặc tạo fake class có state được kiểm soát.

Dùng `thenAnswer` thận trọng vì nó có thể chuyển nhiều logic vào mock; nếu fake trở thành một hệ thống con phức tạp, test khó hiểu và dễ lặp lại bug của production. Đối với retry có clock/backoff, ưu tiên inject clock/scheduler/fake sleeper hoặc công cụ kiểm soát thời gian để tránh `Thread.sleep` dài và test flakiness.

Mockito có API `Answer<T>`; lambda nhận `InvocationOnMock`, có thể xem `getArgument(index, Type.class)`. Đừng đọc các đối số không tồn tại hoặc ép kiểu sai; test sẽ báo lỗi mock setup thay vì nghiệp vụ.

## 11. Dùng @Mock, @InjectMocks và Spring Boot đúng tầng

### Unit test với MockitoExtension

Trong dự án Spring Boot có `spring-boot-starter-test`, Mockito cung cấp `@Mock` và `@InjectMocks` cho unit tests, thường kết hợp với `@ExtendWith(MockitoExtension.class)`:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CatalogServiceUnitTest {
    @Mock
    RemoteCatalog remote;

    @InjectMocks
    CatalogService service;

    @Test
    void retriesOneTransientFailure() {
        when(remote.read("A"))
            .thenThrow(new TemporaryFailure("timeout"))
            .thenReturn("READY");

        assertEquals("READY", service.loadWithRetry("A", 3));
        verify(remote, times(2)).read("A");
    }
}
```

Đây là **trích đoạn cần các class `RemoteCatalog`, `CatalogService`, `TemporaryFailure` cùng các static imports** từ phần trước; không phải test độc lập. `@InjectMocks` cố gắng inject mocks bằng constructor/setter/field trong phạm vi khả năng; thiết kế ưu tiên **constructor injection** để dependency hiển nhiên. `MockitoExtension` có thể bật kiểm tra strict stubs mặc định: những stubs không bao giờ được sử dụng thường bị xem là dấu hiệu test thiết kế sai. Không thêm `lenient()` bừa bãi để che cảnh báo; nếu phải làm, lý giải cụ thể.

### Trong Spring ApplicationContext: mock khác nhau

- `@Mock` tạo Mockito mock **ngoài** Spring context nếu chỉ dùng MockitoExtension.
- `@MockitoBean` (`org.springframework.test.context.bean.override.mockito.MockitoBean`) thay/đăng ký bean trong Spring test context với Spring Framework 6.2+/Spring Boot 3.4+; Boot 4 dùng annotation này.
- `@MockBean` của Spring Boot cũ đã deprecated trong Boot 3.4/3.5 và không nên dựa vào khi migrate Boot 4.
- `@WebMvcTest` dùng test slice MVC, còn `@SpringBootTest` mở Spring context rộng hơn. Chọn đúng mức; không cần tạo toàn bộ Spring context cho bài test chỉ kiểm tra retry loop.

Với Spring Boot 4, có các starter test theo công nghệ như `spring-boot-starter-webmvc-test` ngoài starter test chung; dùng theo đúng dòng version. Tuy vậy, **cú pháp Mockito `when/thenReturn/thenThrow` vẫn cùng ý tưởng** dù cấu hình test bean của Spring Boot thay đổi.

### Gradle Kotlin DSL

Trong project đã áp dụng plugin Spring Boot và quản lý version phụ thuộc:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
```

Khi dùng Maven, scope `test` như POM phần 7. Nếu dự án dùng dependency management của Boot, tránh tự ghép version Mockito/JUnit khác major không kiểm tra.

## 12. Phân biệt mô phỏng retry trong unit test và retry thật

Một mock sequence kiểm tra **code gọi dependency và xử lý kết quả**. Nó **không chứng minh**:

- HTTP client thật có cấu hình connect/read timeout đúng.
- Retry policy thật có backoff, jitter hoặc timeout budget đúng.
- Spring Retry/Resilience4j proxy, circuit breaker hay annotation `@Retryable` thực sự được áp dụng.
- Transaction DB rollback/commit chính xác sau lỗi.
- Idempotency của POST/ghi dữ liệu khi retry.
- Logging/metrics/tracing đúng trong môi trường triển khai.

Ví dụ unit test từ phần 7 mô phỏng một vòng lặp retry **tự viết**. Nếu ứng dụng dùng `@Retryable` qua Spring proxy, gọi trực tiếp `new Service(...)` có thể **bỏ qua proxy**, dẫn đến test không xác nhận retry thật. Khi đó cần integration/slice test có Spring context phù hợp hoặc test riêng cấu hình proxy; mock dependency ở biên ngoài rồi verify số lần gọi trong bean được proxy. Đừng thêm `@SpringBootTest` chỉ để khắc phục một unit test thiếu logic cần test.

**Cần kiểm tra hành vi thất bại cố định:** khi `thenThrow` luôn ném, service phải dừng ở attempt cuối. **Cần kiểm tra hành vi hồi phục:** khi lỗi rồi thành công, service dừng ngay sau thành công. **Cần kiểm tra lỗi không retry:** với loại exception vĩnh viễn (`IllegalArgumentException`/validation/business denial), hệ thống thường phải ném ngay, không retry vô hạn. Các loại lỗi retry được hay không phụ thuộc hợp đồng ứng dụng.

Nếu retry một thao tác có tác dụng phụ (thanh toán, giữ hàng, gửi message), timeout **không chứng minh thao tác trước thất bại**: phụ thuộc có thể đã xử lý nhưng response mất. Cần đặc tả idempotency key, deduplication hoặc compensation; chỉ mock `thenThrow(...).thenReturn(...)` không thể bảo đảm an toàn với side effect thật.

## 13. Những lỗi thường gặp và cách sửa

| Lỗi hoặc hiểu lầm | Tác hại | Cách làm đúng |
| --- | --- | --- |
| Viết hai lệnh `when(...).thenReturn` và tưởng là hai lần gọi liên tiếp | Stub sau thường ghi đè stub trước | Gộp `thenReturn("A","B")` hoặc nối trên cùng ongoing stubbing |
| Nghĩ sequence tự kết thúc sau kết quả cuối | Test bỏ qua trường hợp service gọi quá nhiều | Assert `times(n)`, nhớ behavior cuối lặp lại |
| Chỉ assert giá trị trả về mà không verify số lời gọi retry | Không bắt được lời gọi dư/thừa | `verify(mock, times(expected)).call(...)` |
| `when(mock.voidMethod())` | Java không biên dịch | `doThrow(...).when(mock).voidMethod()` |
| `thenThrow(new IOException())` khi method không khai báo throws | Mockito từ chối checked exception | Dùng exception phù hợp với chữ ký hoặc unchecked wrapper |
| `when(spy.method())` gây side effect hoặc ném lỗi khi setup | Test fail trước khi gọi code cần test | `doReturn`/`doThrow` cho spy |
| Dùng matcher cho một tham số và literal cho tham số khác | Mockito ném InvalidUseOfMatchersException | Dùng matcher cho mọi tham số, `eq(...)` cho literal |
| `anyString()` nhưng kỳ vọng khớp `null` | Stub không được sử dụng | Dùng `isNull()`/`nullable(String.class)` tùy hợp đồng |
| Stub riêng từng key nhưng lời gọi dùng key khác | Nhận default (có thể `null`), lỗi khó hiểu | Xác minh tham số thật và stub đúng chữ ký |
| Stubbing không dùng bị StrictStubs báo | Dấu hiệu setup thừa hoặc đường code không chạy | Sửa test và chỉ stub tương tác sẽ xảy ra |
| `reset(mock)` ở giữa test để chạy nhiều giai đoạn | Mất history và stubs, test khó kiểm tra | Dùng test riêng, mock mới hoặc setup lại fixture rõ ràng |
| Dùng `Thread.sleep` dài để test retry | Test chậm và flake | Inject clock/scheduler/fake sleeper và assert số attempts |
| Dùng mock để kết luận HTTP timeout thật hoạt động | Không có network/client thật | Viết test adapter với WireMock/MockWebServer hoặc integration phù hợp |
| Dùng `times(3)` nhưng không kiểm tra kết quả/exception | Có thể gọi đúng 3 lần nhưng behavior vẫn sai | Kết hợp status/value/exception assertion |
| Lạm dụng `verifyNoMoreInteractions` vào mọi test | Khóa chặt implementation detail | Chỉ verify những tương tác quan trọng với contract |

### Checklist trước khi chốt test

- [ ] Stub khớp đúng method và đúng đối số?
- [ ] Với chuỗi nhiều lần gọi, đã ghi rõ thứ tự và biết behavior cuối cùng lặp?
- [ ] Đã xác định `maxAttempts` gồm hay không gồm lần gọi đầu?
- [ ] Thành công sau retry được assert và số lời gọi đúng?
- [ ] Lỗi liên tục bị dừng đúng giới hạn?
- [ ] Lỗi không retry bị ném ngay khi cần?
- [ ] Method `void` dùng `doThrow`/`doNothing` đúng API?
- [ ] Checked exception hợp lệ với `throws`?
- [ ] Spy không vô ý gọi phương thức thật trong lúc stubbing?
- [ ] Không trộn matcher và literal trong một invocation?
- [ ] Không có network/DB thật trong unit test?
- [ ] Khi behavior phụ thuộc Spring proxy, đã có test thích hợp qua context?
- [ ] Test có kiểm chứng điều kiện nghiệp vụ và các tương tác quan trọng, không chỉ một trong hai?

## 14. Tài liệu gốc

- [Mockito API — Mockito, ví dụ when/thenReturn/thenThrow/consecutive calls](https://javadoc.io/static/org.mockito/mockito-core/5.24.0/org.mockito/org/mockito/Mockito.html)
- [Mockito API — OngoingStubbing](https://javadoc.io/static/org.mockito/mockito-core/5.24.0/org.mockito/org/mockito/stubbing/OngoingStubbing.html)
- [Mockito API — Stubber cho doThrow/doNothing](https://javadoc.io/static/org.mockito/mockito-core/5.24.0/org.mockito/org/mockito/stubbing/Stubber.html)
- [Mockito API — VerificationMode](https://javadoc.io/static/org.mockito/mockito-core/5.24.0/org.mockito/org/mockito/verification/VerificationMode.html)
- [Spring Boot — Test Scope Dependencies](https://docs.spring.io/spring-boot/reference/testing/test-scope-dependencies.html)

**Ghi nhớ:** `when(...).thenReturn/thenThrow` định nghĩa **những gì mock trả/ném**; chaining định nghĩa **diễn biến qua nhiều lần gọi**; `verify(..., times(n))` xác nhận **code thực sự gọi bao nhiêu lần**. Kết hợp cả kết quả nghiệp vụ, exception, lần gọi và giới hạn retry sẽ tạo test có khả năng phát hiện lỗi thay vì chỉ chứng minh mock đã được cấu hình.
