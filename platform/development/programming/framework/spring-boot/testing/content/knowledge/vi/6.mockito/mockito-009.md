# Mock phương thức void, final hoặc static theo khả năng phiên bản

## 1. Mục tiêu và bản chất của vấn đề

Trong unit test Java/Spring Boot, Mockito thường thay một dependency bằng **mock** để kiểm soát phản hồi và kiểm tra tương tác. Các phương thức `void`, `final` và `static` cần cách xử lý khác nhau:

- **`void`:** không có giá trị trả về, vì vậy không thể dùng cú pháp `when(mock.method()).thenReturn(...)`. Ta có thể kiểm tra đã gọi hay chưa bằng `verify(...)`, hoặc thiết lập hành vi với họ `doNothing()`, `doThrow(...)`, `doAnswer(...)` và `doCallRealMethod()`.
- **`final`:** phương thức/lớp bị hạn chế kế thừa hoặc override. Khả năng mock phụ thuộc **mock maker** và phiên bản Mockito. Trên JVM thông thường, Mockito 5 dùng inline mock maker theo mặc định và hỗ trợ nhiều trường hợp `final`.
- **`static`:** phương thức thuộc về lớp, không gắn với một mock instance. Mockito từ **3.4.0** có `mockStatic(...)` khi dùng inline mock maker. Kết quả trả về là `MockedStatic<T>` với scope phải được đóng, thông thường bằng `try-with-resources`.

**Điểm cốt lõi:** trước khi áp dụng một đoạn code, phải biết phiên bản Mockito đang thực thi, mock maker được chọn, JVM và test runner. “Mockito có API này” không bảo đảm môi trường cụ thể cho phép sử dụng. Đồng thời, mock được tạo ra để kiểm tra **đơn vị đang được thử**, không phải để xóa đi mọi hành vi thật cần được chứng minh.

### 1.1. Khi nào cần mock, khi nào nên gọi thật?

Ví dụ service gửi thông báo đơn hàng qua một cổng gửi bên ngoài:

- Luật quyết định có được gửi hay không là **logic cần thử thật**.
- Cổng gửi email/HTTP/queue tạo side effect là **ranh giới phù hợp để mock**.
- Mã định danh tạo bởi utility static có thể cần kiểm soát trong một unit test đặc biệt, nhưng có thể thiết kế lại thành interface/instance method nếu nó là dependency quan trọng hoặc được dùng lặp lại ở nhiều test.

Dù `void`, `final` và `static` đã mock được, việc mock không tự động làm test đúng. Cần đảm bảo test còn kiểm tra kết quả hoặc tương tác quan trọng, tránh setup quá cụ thể khiến test chỉ “diễn lại” stub.

## 2. Ma trận phiên bản và giới hạn cần nhớ

| Khả năng | Các mốc phiên bản quan trọng | Điều kiện / giới hạn |
|---|---|---|
| Mock interface, class thông thường; `verify` | Có từ các thế hệ Mockito cũ | Cần dependency Mockito và test runtime phù hợp |
| Stub `void` bằng `doThrow/doNothing/doAnswer` | API Mockito lâu đời | Không dùng `when(voidCall).thenReturn(...)` vì Java không có giá trị từ lời gọi `void` |
| Mock lớp/phương thức `final` | Hỗ trợ qua inline mock maker ở các dòng Mockito 2.x–4.x; **mặc định trong Mockito 5.x** | Mockito trước 5 cần bật inline phù hợp; một số cấu hình/kiểu method vẫn bị giới hạn |
| Mock phương thức `static` | `mockStatic` có từ **Mockito 3.4.0** | Cần inline mock maker, scope `MockedStatic` và môi trường instrumentation tương thích |
| Mockito 5.x | Inline mock maker mặc định trên JVM; yêu cầu **Java 11+** cho chính Mockito | Java 17+ phù hợp về baseline, nhưng môi trường JVM/agent và dependency vẫn phải tương thích |
| Java 21+ và JVM siết attach agent | Inline instrumentation có thể phát cảnh báo/không attach được tùy runtime | Làm theo hướng dẫn `-javaagent` chính thức nếu cần, không chỉ bỏ qua cảnh báo |

**Đừng suy luận từ tên dependency một mình.** Cùng có `mockito-core`, một dự án có thể dùng Mockito 4 với subclass mock maker, dự án khác dùng Mockito 5 inline. Nếu project chứa file `mockito-extensions/org.mockito.plugins.MockMaker` chọn `mock-maker-subclass`, `final` và `static` vẫn có thể không mock được dù Mockito là 5.x.

Với Mockito 3.x/4.x, cơ chế inline có thể được kích hoạt bằng cấu hình extension trên test classpath:

**File `src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker` (một dòng nội dung):**

```text
mock-maker-inline
```

Ở các dòng cũ, artifact `mockito-inline` cũng từng cung cấp cấu hình inline sẵn. **Không tự thêm `mockito-inline` phiên bản cũ vào Mockito 5**, vì Mockito 5 đã dùng inline làm mặc định và artifact đó không phải cách thiết lập cần thiết cho dự án hiện đại. Dùng một bộ dependency Mockito được quản lý nhất quán, tránh các version chồng chéo giữa `mockito-core`, `mockito-junit-jupiter`, Byte Buddy và framework.

### 2.1. Hạn chế vẫn tồn tại, kể cả khi có inline mock maker

- Mocking inline cần instrumentation/Byte Buddy và JVM tương thích; trên JDK mới hoặc runtime bị giới hạn attach, quá trình khởi tạo mock maker có thể thất bại.
- Không mặc định mock được **native method**, một số method thuộc `java.*`, các lớp/hàm gắn với JVM intrinsic, hoặc các đối tượng có classloader đặc biệt.
- `mockStatic` **mock lời gọi phương thức tĩnh**, không biến field `static final` thành field có thể stub qua `when(...)`. Hằng số compile-time có thể đã được inlined bởi Java compiler.
- Mocking phương thức `private` hay constructor `new` không phải cùng thao tác với mock `final` hoặc `static`. Mockito có API khác cho construction mocking ở các phiên bản hỗ trợ, nhưng không nên coi chúng là lựa chọn mặc định cho mọi test.
- Không nên mock rộng rãi các API lõi như `System` hoặc `Thread`. Mockito có các giới hạn để bảo vệ cơ chế thực thi; thường có giải pháp tốt hơn bằng wrapper hoặc injection.

**Nguyên tắc quyết định:** nếu phải mock static liên tục để kiểm thử luồng chính, hãy cân nhắc tách dependency thành một đối tượng truyền qua constructor. Static mocking phù hợp hơn khi làm việc với legacy API hoặc một điểm tích hợp không dễ thay đổi.

## 3. Cấu hình Mockito trong dự án Spring Boot

Với dự án Spring Boot thông dụng, `spring-boot-starter-test` đưa Mockito, JUnit Jupiter và nhiều thư viện test vào test scope. Chọn phiên bản Mockito theo dependency management/BOM của dự án; khi bài thực hành cần mock `final`/`static`, xác nhận phiên bản thực tế đủ mới và inline được bật.

**Gradle Groovy DSL — phần liên quan của `build.gradle`:**

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven — phần dependency của `pom.xml`:**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Các đoạn trên **không phải build file hoàn chỉnh**: dự án cần khai báo Spring Boot plugin/parent hoặc cơ chế quản lý version, repositories và Java toolchain phù hợp. Unit test ví dụ bên dưới dùng `mock(...)` trực tiếp, nên không bắt buộc thêm `@ExtendWith(MockitoExtension.class)`. Nếu muốn dùng `@Mock` hoặc `@InjectMocks`, có thể dùng Mockito extension với JUnit Jupiter trong cấu hình thích hợp.

Kiểm tra version thực tế khi cần điều tra:

**Gradle Wrapper:**

```bash
./gradlew dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency byte-buddy --configuration testRuntimeClasspath
```

**Maven Wrapper:**

```bash
./mvnw dependency:tree -Dincludes=org.mockito
```

Các lệnh phù hợp với dự án có Wrapper và dependency plugin/task được cấu hình. Trong multi-module project, chạy ở đúng module hoặc chỉ rõ project/module; dependencyInsight không thể hiện mọi cấu hình nếu bạn chọn sai module.

**Phân biệt Spring và Mockito:** tạo `mock(SomeType.class)` chỉ tạo object cục bộ; Spring `ApplicationContext` không tự thay bean bằng object đó. Với Spring test cần override bean, các phiên bản Spring Framework hỗ trợ có `@MockitoBean`/`@MockitoSpyBean`; Spring Boot cũ dùng `@MockBean`/`@SpyBean` (các annotation này bị đánh dấu deprecated từ Spring Boot 3.4). Lựa chọn theo phiên bản Spring thực tế, không dùng `@MockitoBean` trong project mà framework chưa có. Bài ví dụ sẽ tập trung **unit test thuần Java** để nhìn rõ hành vi Mockito.

## 4. Kiến thức cơ bản về Mockito stubbing và verification

Trước khi đi vào ba kiểu method, phân biệt hai câu hỏi:

- **Stubbing — “nếu dependency được gọi, nó sẽ làm gì?”** Dùng `when(...).thenReturn(...)` cho phương thức trả về giá trị; dùng họ `do...` cho `void` hoặc tình huống cần tránh gọi method thật trên spy.
- **Verification — “dependency có được gọi đúng cách không?”** Dùng `verify(mock).method(...)`, `verify(mock, times(n))`, `never()`, `verifyNoInteractions(...)`, `ArgumentCaptor`… Verification không tự thay thế assertion về dữ liệu đầu ra hoặc trạng thái nghiệp vụ.

Ví dụ trên một mock trả về giá trị:

```java
when(policy.accepts("buyer@example.org")).thenReturn(true);
org.junit.jupiter.api.Assertions.assertTrue(policy.accepts("buyer@example.org"));
verify(policy).accepts("buyer@example.org");
```

Đây là **đoạn minh họa** trong test có sẵn đối tượng `policy` là mock phù hợp. Với phương thức `void`, câu lệnh `when(channel.send(...))` không thể biên dịch vì lời gọi đó có kiểu `void`.

### 4.1. Matcher và đối số cụ thể

Mockito dùng matcher như `anyString()`, `eq("...")`, `argThat(...)` để lựa chọn call cần stub/verify. Khi đã dùng matcher cho một đối số trong cùng lần gọi, thông thường phải dùng matcher cho **mọi** đối số của lời gọi đó:

**Đúng:**

```java
doThrow(new IllegalStateException("offline"))
        .when(channel)
        .send(eq("buyer@example.org"), anyString());
```

**Sai cách phối hợp matcher:**

```java
doThrow(new IllegalStateException("offline"))
        .when(channel)
        .send("buyer@example.org", anyString());
```

Ở đoạn sai, đối số đầu là literal, đối số sau là matcher; Mockito thường ném `InvalidUseOfMatchersException`. Cách sửa là `eq("buyer@example.org")` hoặc dùng cả hai đối số literal theo đúng mục tiêu.

Một matcher rộng như `anyString()` chấp nhận các String phù hợp, và không thay thế được kiểm tra payload cụ thể khi payload là hợp đồng. Khi kết quả phụ thuộc argument, stub cần đúng điều kiện để không “ăn nhầm” lời gọi.

## 5. Mock phương thức `void`

### 5.1. Mặc định trên mock: không làm gì, nhưng vẫn có thể verify

Với mock thuần Mockito có default answer thông thường, lời gọi đến phương thức `void` chưa stub sẽ **không thực thi side effect thật**. Ví dụ:

```java
Channel channel = mock(Channel.class);
channel.send("buyer@example.org", "hello");
verify(channel).send("buyer@example.org", "hello");
```

Đây là **đoạn minh họa**, giả định đã khai báo interface `Channel` với phương thức `void send(String, String)`. `verify` xác nhận invocation; không có email hay message thật được gửi từ mock đó. Không cần viết `doNothing()` trước mọi lời gọi `void` chỉ để tái hiện hành vi mặc định.

### 5.2. `doNothing()`: hữu ích trên spy hoặc khi thiết lập chuỗi hành vi

```java
doNothing().when(channel).send(anyString(), anyString());
```

Hàm này chỉ thực sự có ích khi:

1. Bạn đang dùng **spy** lên đối tượng thật và muốn vô hiệu hóa một side effect cụ thể trong test.
2. Bạn muốn cấu hình những lần gọi tiếp theo khác nhau, ví dụ lần đầu thành công, lần sau ném lỗi: `doNothing().doThrow(error).when(channel).send(...)`.

Nếu `channel` là mock thuần chưa stub, câu trên hầu như không làm test mạnh hơn. Hãy ưu tiên verification chính xác hoặc kiểm tra kết quả nghiệp vụ.

### 5.3. `doThrow(...)`: mô phỏng side effect thất bại

```java
doThrow(new IllegalStateException("gateway offline"))
        .when(channel)
        .send(eq("buyer@example.org"), anyString());
```

Khi dependency được gọi với bộ đối số khớp, Mockito ném exception đã cấu hình. Đây là cách để thử service **truyền lỗi, xử lý lỗi hoặc retry** theo hợp đồng. Phân biệt:

- `doThrow(new IOException(...))` với checked exception chỉ hợp lệ khi method signature cho phép loại checked exception đó; nếu không Mockito có thể báo cấu hình exception không hợp lệ.
- `doThrow(IllegalStateException.class)` yêu cầu Mockito tạo instance theo cơ chế hỗ trợ; nếu cần kiểm tra **message hoặc identity** của exception, truyền một instance được tạo rõ ràng như ví dụ.
- Với một method `void`, không thể viết `when(channel.send(...)).thenThrow(...)` vì `send(...)` không trả về giá trị.

### 5.4. `doAnswer(...)`: quan sát đối số hoặc mô phỏng hành vi có điều kiện

```java
List<String> sent = new ArrayList<>();

doAnswer(invocation -> {
    String to = invocation.getArgument(0, String.class);
    String body = invocation.getArgument(1, String.class);
    sent.add(to + ": " + body);
    return null;
}).when(channel).send(anyString(), anyString());
```

**Lưu ý:** đây là đoạn trong test có import Java Collection và Mockito; `Answer` của method `void` thường trả `null`. Nó không cần trả một “void value” giả vì Java không có giá trị đó. `doAnswer` hữu ích khi cần phản hồi dựa vào tham số hoặc tạo in-memory fake; nhưng không nên tự viết `Answer` phức tạp cho điều kiện chỉ cần `verify`/`ArgumentCaptor`.

### 5.5. `doCallRealMethod()` và rủi ro side effect thật

`doCallRealMethod().when(spy).someVoidMethod()` chỉ định lời gọi thực thi method thật. Với spy, đây có thể là hành vi mặc định; dùng khi cần thiết lập rõ một chuỗi stub. Với **mock của class**, gọi real method có thể chạy trên object không được khởi tạo trạng thái như constructor thật, dẫn đến NPE hoặc side effect khó kiểm soát. Hãy cân nhắc dùng **instance thật** cho logic cần thử hoặc spy được khởi tạo hợp lệ.

**Không lạm dụng spy:** spy thường gọi method thật trừ khi đã stub. Nếu method thực hiện gửi email, ghi DB, xóa file hoặc phát event, sơ suất trong stubbing có thể kích hoạt hành vi thật ngay trong test.

## 6. Ví dụ hoàn chỉnh Java 17+ — đối tượng sản phẩm

Ví dụ sau minh họa đủ ba nhóm `void`, `final`, `static` với một service đơn giản. Chúng ta không khởi động Spring ApplicationContext vì mục tiêu là học hành vi của Mockito.

Tạo file **`src/main/java/com/example/testing/mockito/ShipmentService.java`**:

```java
package com.example.testing.mockito;

import java.util.Objects;

public final class ShipmentService {

    public interface Channel {
        void send(String destination, String payload);
    }

    public static final class AddressPolicy {
        // final class và final method để kiểm tra Mockito inline.
        public final boolean accepts(String address) {
            return address != null && address.contains("@");
        }
    }

    public static final class TraceIds {
        private TraceIds() {}

        public static String forOrder(String orderId) {
            return "trace-" + orderId;
        }
    }

    private final Channel channel;
    private final AddressPolicy policy;

    public ShipmentService(Channel channel, AddressPolicy policy) {
        this.channel = Objects.requireNonNull(channel, "channel");
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    public void dispatch(String orderId, String destination) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        if (!policy.accepts(destination)) {
            throw new IllegalArgumentException(
                    "destination rejected");
        }

        String payload = "order=" + orderId
                + ";trace=" + TraceIds.forOrder(orderId);
        channel.send(destination, payload);
    }
}
```

Các vai trò:

- `Channel.send(...)` trả `void`, tượng trưng cho dependency có side effect; có thể mock mà không gửi thật.
- `AddressPolicy` là **final class** và `accepts` là **final method**; Mockito 5 inline có thể tạo mock để buộc nhánh từ chối. Điều kiện chứa `@` chỉ là ví dụ để dễ hiểu, **không phải bộ xác thực địa chỉ email dùng trong sản xuất**.
- `TraceIds.forOrder(...)` là **static method**; ta sẽ can thiệp trong phạm vi một test rồi trả về hành vi thật.
- `ShipmentService.dispatch(...)` chính là hành vi cần thử. Code giữ cả logic điều kiện và thao tác gọi dependency để ta phân biệt **assert exception** và **verify interaction**.

## 7. Ví dụ hoàn chỉnh Java 17+ — JUnit Jupiter + Mockito

Tạo file **`src/test/java/com/example/testing/mockito/ShipmentServiceTest.java`**:

```java
package com.example.testing.mockito;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.MockedStatic;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

class ShipmentServiceTest {

    private static final String ADDRESS = "buyer@example.org";

    private ShipmentService.Channel newChannel() {
        return mock(ShipmentService.Channel.class);
    }

    private ShipmentService newService(
            ShipmentService.Channel channel) {
        return new ShipmentService(
                channel, new ShipmentService.AddressPolicy());
    }

    @Test
    void verifiesVoidInvocationWithExactArguments() {
        var channel = newChannel();
        var service = newService(channel);

        service.dispatch("R-01", ADDRESS);

        verify(channel).send(
                ADDRESS, "order=R-01;trace=trace-R-01");
        verifyNoMoreInteractions(channel);
    }

    @Test
    void canExplicitlyStubVoidToDoNothing() {
        var channel = newChannel();
        var service = newService(channel);

        doNothing().when(channel)
                .send(eq(ADDRESS), anyString());

        service.dispatch("R-02", ADDRESS);

        verify(channel).send(
                ADDRESS, "order=R-02;trace=trace-R-02");
    }

    @Test
    void doThrowSimulatesFailureOfVoidDependency() {
        var channel = newChannel();
        var service = newService(channel);

        doThrow(new IllegalStateException("gateway offline"))
                .when(channel)
                .send(eq(ADDRESS), anyString());

        assertThatThrownBy(
                () -> service.dispatch("R-03", ADDRESS))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("gateway offline");

        verify(channel).send(
                ADDRESS, "order=R-03;trace=trace-R-03");
    }

    @Test
    void voidCanHaveDifferentBehaviorsAcrossCalls() {
        var channel = newChannel();
        var service = newService(channel);

        doNothing()
                .doThrow(new IllegalStateException(
                        "second attempt blocked"))
                .when(channel)
                .send(anyString(), anyString());

        service.dispatch("R-04", ADDRESS);

        assertThatThrownBy(
                () -> service.dispatch("R-04", ADDRESS))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("second attempt blocked");

        verify(channel, times(2)).send(
                ADDRESS, "order=R-04;trace=trace-R-04");
    }

    @Test
    void doAnswerCanRecordVoidArguments() {
        var channel = newChannel();
        var service = newService(channel);
        List<String> events = new ArrayList<>();

        doAnswer(invocation -> {
            String destination =
                    invocation.getArgument(0, String.class);
            String payload =
                    invocation.getArgument(1, String.class);
            events.add(destination + " <- " + payload);
            return null;
        }).when(channel).send(anyString(), anyString());

        service.dispatch("R-05", ADDRESS);

        assertThat(events).containsExactly(
                "buyer@example.org <- order=R-05;trace=trace-R-05");
    }

    @Test
    void canStubFinalClassAndFinalMethodWithInlineMockMaker() {
        var channel = newChannel();
        var policy = mock(ShipmentService.AddressPolicy.class);
        when(policy.accepts(ADDRESS)).thenReturn(false);
        var service = new ShipmentService(channel, policy);

        assertThatThrownBy(
                () -> service.dispatch("R-06", ADDRESS))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("destination rejected");

        verify(policy).accepts(ADDRESS);
        verifyNoInteractions(channel);
    }

    @Test
    void staticMockIsRestrictedToTryWithResourcesScope() {
        var channel = newChannel();
        var service = newService(channel);

        assertThat(ShipmentService.TraceIds.forOrder("R-07"))
                .isEqualTo("trace-R-07");

        try (MockedStatic<ShipmentService.TraceIds> traces =
                     mockStatic(ShipmentService.TraceIds.class)) {

            traces.when(() ->
                    ShipmentService.TraceIds.forOrder("R-07"))
                    .thenReturn("fixed-07");

            service.dispatch("R-07", ADDRESS);

            verify(channel).send(
                    ADDRESS, "order=R-07;trace=fixed-07");
            traces.verify(() ->
                    ShipmentService.TraceIds.forOrder("R-07"));
        }

        assertThat(ShipmentService.TraceIds.forOrder("R-07"))
                .isEqualTo("trace-R-07");
    }

    @Test
    void invalidDestinationNeverCallsVoidDependency() {
        var channel = newChannel();
        var service = newService(channel);

        assertThatThrownBy(
                () -> service.dispatch("R-08", "invalid"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("destination rejected");

        verifyNoInteractions(channel);
    }

    @Test
    void capturesVoidPayloadForFurtherAssertions() {
        var channel = newChannel();
        var service = newService(channel);
        ArgumentCaptor<String> payload =
                ArgumentCaptor.forClass(String.class);

        service.dispatch("R-09", ADDRESS);

        verify(channel).send(eq(ADDRESS), payload.capture());
        assertThat(payload.getValue())
                .startsWith("order=R-09;")
                .contains("trace-R-09");
    }

    @Test
    void doNothingOnSpyPreventsRealVoidSideEffect() {
        var counter = spy(new SideEffectCounter());

        doNothing().when(counter).increment();
        counter.increment();

        assertThat(counter.count()).isZero();
        verify(counter).increment();
    }

    static class SideEffectCounter {
        private int calls;

        void increment() {
            calls++;
        }

        int count() {
            return calls;
        }
    }
}
```

Đoạn code trên có **10 phương thức test**. Các test tự tạo mock riêng trong mỗi phương thức, không dùng static mock vượt ra ngoài `try-with-resources` và không cần Spring context. Đặt hai file đúng tên/package, dùng Java 17+ và Mockito 5.x với inline mock maker trên JVM tương thích; khi đó kỳ vọng **cả 10 test pass**. Không có stdout do ứng dụng chủ động in ra; định dạng log số test và trạng thái phụ thuộc JUnit/Gradle/Maven.

**Chạy bằng Gradle Wrapper** từ root/module thích hợp:

```bash
./gradlew test --tests "com.example.testing.mockito.ShipmentServiceTest"
```

**Chạy bằng Maven Wrapper** với Surefire đã hỗ trợ JUnit Jupiter:

```bash
./mvnw -Dtest=ShipmentServiceTest test
```

Trên Windows PowerShell, dùng `.\gradlew.bat test --tests "com.example.testing.mockito.ShipmentServiceTest"` hoặc `.\mvnw.cmd "-Dtest=ShipmentServiceTest" test`. Trong multi-module project, phải chọn đúng task/goal của module chứa lớp test. Nếu bản Mockito dự án **chưa dùng inline** hoặc runtime không hỗ trợ instrumentation, hai test dùng final/static cần cấu hình thích hợp; không nên kết luận toàn bộ ví dụ sai vì chỉ môi trường đó không đáp ứng điều kiện của API.

### 7.1. Vì sao từng test đáng tin?

- `verifiesVoidInvocationWithExactArguments`: không stub `void` vì mock mặc định không làm gì. `verify` xác minh chính xác destination và payload.
- `canExplicitlyStubVoidToDoNothing`: minh họa cú pháp, nhưng chủ động nêu rằng `doNothing` trên mock thuần thường thừa.
- `doThrowSimulatesFailureOfVoidDependency`: kiểm tra nhánh service đi qua dependency khi transport lỗi, bao gồm exception type/message và xác nhận lời gọi.
- `voidCanHaveDifferentBehaviorsAcrossCalls`: lần đầu không lỗi, lần sau lỗi; `times(2)` xác minh có đúng hai lần gọi.
- `doAnswerCanRecordVoidArguments`: mô phỏng side effect trong bộ nhớ, cho phép assert payload đã truyền.
- `canStubFinalClassAndFinalMethodWithInlineMockMaker`: chứng minh Mockito mock được một class `final` chứa method `final` khi inline hỗ trợ.
- `staticMockIsRestrictedToTryWithResourcesScope`: trong scope static trả giá trị cố định; sau scope method thật trả lại giá trị gốc.
- `invalidDestinationNeverCallsVoidDependency`: kiểm tra **không có side effect** khi service từ chối đầu vào.
- `capturesVoidPayloadForFurtherAssertions`: trích argument từ invocation thay vì ép khớp string toàn bộ khi chỉ một số phần của payload là hợp đồng.
- `doNothingOnSpyPreventsRealVoidSideEffect`: spy đã tạo từ object thật nhưng riêng `increment` được vô hiệu hóa, nên `count()` vẫn bằng 0.

## 8. Mock `final`: đúng version và đúng mục tiêu

### 8.1. Vì sao trước đây final khó mock?

Mock maker kiểu **subclass** thường tạo một lớp con để override phương thức. Java không cho subclass một `final class` và không cho override `final method`. Vì vậy trong cơ chế này, lệnh `mock(FinalType.class)` hoặc stub `finalMethod()` có thể bị từ chối hay không hoạt động.

**Inline mock maker** can thiệp bytecode của lớp theo cơ chế instrumentation và không chỉ dựa vào subclass, nên có khả năng thay hành vi của nhiều final method/class. Mockito 5 bật inline mặc định trên JVM thông thường; Mockito 2.x–4.x thường phải opt in. Đây là thay đổi về **cơ chế mock maker**, không phải tính năng riêng của JUnit hoặc Spring Boot.

### 8.2. Ví dụ final class + final method

Từ class `ShipmentService.AddressPolicy` ở phần 6:

```java
var policy = mock(ShipmentService.AddressPolicy.class);
when(policy.accepts("buyer@example.org")).thenReturn(false);

assertThat(policy.accepts("buyer@example.org")).isFalse();
verify(policy).accepts("buyer@example.org");
```

Đây là đoạn trích dùng trong test có imports phù hợp. Method `accepts` là final, nhưng Mockito 5 inline hỗ trợ stub. Với subclass mock maker, test có thể không tạo được mock hoặc method final không được intercept như mong đợi.

### 8.3. Một số trường hợp không nên mock final

- **Record/value object không có side effect:** thường chỉ cần tạo instance thật, không mock. Mock data object dễ khiến test chỉ xác minh setup do chính mình dựng.
- **Class xử lý thuật toán thuần:** nên gọi thật để test kiểm tra logic thật, không mock kết quả mà lẽ ra cần chứng minh.
- **Bean hay class final khó kiểm soát vì thiết kế phụ thuộc:** nếu có quyền sửa thiết kế, tạo interface/adaptor có thể làm test ổn định hơn mock trực tiếp lớp final.
- **Final method gọi phụ thuộc ngoài:** nếu class là thư viện không thể sửa, inline mock có thể là lựa chọn thực tế, nhưng giới hạn mock chỉ ở vùng cần thiết.

Phân biệt `final` trên **biến tham chiếu** với `final class/method`. `final SomeService service` chỉ cấm gán lại biến; không quyết định việc Mockito có tạo mock cho kiểu `SomeService` hay không.

## 9. Mock `static`: scope, thread và kiểm soát tác động

### 9.1. Cú pháp chuẩn

```java
try (MockedStatic<ShipmentService.TraceIds> traces =
             mockStatic(ShipmentService.TraceIds.class)) {

    traces.when(() ->
            ShipmentService.TraceIds.forOrder("R-07"))
            .thenReturn("fixed-07");

    assertThat(ShipmentService.TraceIds.forOrder("R-07"))
            .isEqualTo("fixed-07");

    traces.verify(() ->
            ShipmentService.TraceIds.forOrder("R-07"));
}
```

**`MockedStatic<T>` là một controller có scope, không phải mock instance thông thường.**

- `mockStatic(MyUtility.class)` kích hoạt khả năng intercept static method của lớp cho thread gọi.
- `traces.when(() -> MyUtility.staticMethod(...))` cấu hình hành vi trong scope.
- `traces.verify(() -> MyUtility.staticMethod(...))` xác nhận lời gọi static phù hợp trong scope.
- Khi thoát `try-with-resources`, `close()` được thực hiện kể cả khi assertion thất bại, giúp tránh rò rỉ static mock sang test sau.

Để kiểm tra môi trường test không bị rò rỉ mock, test minh họa so sánh hành vi method thật **trước và sau** scope. Đó là bằng chứng rõ hơn việc chỉ thấy test trong scope pass.

### 9.2. Thread-local không có nghĩa là áp dụng lên mọi thread

Mockito `MockedStatic` có phạm vi **thread đã tạo static mock**. Nếu production code giao việc sang `CompletableFuture.supplyAsync(...)`, ExecutorService hoặc một thread khác, lời gọi static ở thread mới có thể **không bị intercept** bởi mock ở test thread.

Vì vậy:

- Không dựa vào một static mock để kiểm soát mọi lời gọi trong luồng bất đồng bộ nếu không thể đảm bảo chúng chạy cùng thread.
- Không chia sẻ object `MockedStatic` để thao tác từ nhiều thread; tài liệu API nêu việc đó không an toàn.
- Ưu tiên truyền dependency instance cho scheduler/async logic cần kiểm thử riêng.
- Luôn đóng static scope bằng `try-with-resources`, không giữ nó ở trạng thái mở qua nhiều phương thức test.

**Ví dụ phản mẫu:** mở static mock trong `@BeforeAll` rồi không đóng cho đến khi toàn suite kết thúc. Điều này có thể làm test khác vô tình nhận phản hồi đã mock, nhất là khi cùng thread chạy nhiều test. Mỗi test chỉ nên mở scope đúng thời gian cần thiết.

### 9.3. Method chưa stub khi static mock đang hoạt động

Một static mock được tạo với default answer thông thường **không tự chuyển mọi lời gọi sang method thật**. Các lời gọi chưa stub có thể nhận default value (như `null` với reference type, 0 với số, false với boolean) tùy kiểu. Vì vậy **mock toàn bộ static class** có nguy cơ làm những method khác trong cùng lớp trả dữ liệu giả ngoài dự tính.

Nếu cần dùng một số method thật, Mockito có cấu hình default answer như `CALLS_REAL_METHODS` trong các phiên bản hỗ trợ. Nhưng điều đó có thể thực thi logic thật (kể cả khi thiết lập stub), nên phải kiểm tra side effect và chỉ dùng khi có lý do. Thường tốt hơn là đặt static mock scope nhỏ hoặc đổi thiết kế để thay đúng dependency cần kiểm soát.

### 9.4. Static mock và overload/argument matcher

Trong lambda `traces.when(() -> TraceIds.forOrder("R-07"))`, method call được ghi nhận để stub. Với overload và matcher, hãy bảo đảm chọn đúng chữ ký và đúng đối số. Nếu code gọi `forOrder("R-08")` nhưng bạn chỉ stub `"R-07"`, stub đó không khớp; giá trị mặc định có thể dẫn đến lỗi ở vị trí tưởng như không liên quan.

Không viết một chuỗi “gọi static khi thì trả A, khi thì trả B” mà không hiểu production sẽ gọi mấy lần, ở thread nào. Trong trường hợp static thực hiện thời gian/ngẫu nhiên, **Clock**, supplier hoặc interface injection thường rõ ràng hơn mocking `Instant.now()`/`UUID.randomUUID()`.

## 10. Spy và `doCallRealMethod()`: cần hiểu thực thi thật

### 10.1. Mock và spy khác nhau ở đâu?

- **Mock:** không thực thi method thật theo mặc định (trừ cấu hình đặc biệt); các method không stub trả default value.
- **Spy:** bọc một object được khởi tạo thật; các method thường gọi logic thật khi chưa stub. Vì vậy spy thích hợp cho kiểm tra một phần hành vi nhưng dễ gây side effect ngoài dự kiến.

Ví dụ `SideEffectCounter` trong test hoàn chỉnh:

```java
var counter = spy(new SideEffectCounter());
doNothing().when(counter).increment();

counter.increment();
assertThat(counter.count()).isZero();
```

Không có `doNothing`, `increment()` sẽ tăng counter do đây là spy. Đoạn trên chứng minh cách cô lập **một method void** khỏi side effect trong khi các method khác vẫn dùng hành vi thật.

### 10.2. Vì sao dùng họ `do...` khi stubbing spy?

Với một method **có giá trị trả về**, biểu thức `when(spy.read()).thenReturn(value)` phải **đánh giá `spy.read()` trước** để truyền kết quả vào `when`; như vậy method thật có thể chạy lúc stubbing. Để tránh thực thi thật, dùng `doReturn(value).when(spy).read()` khi phù hợp.

Với `void`, cách stubbing cũng phải thuộc họ `do...` vì `when(spy.voidMethod())` không hợp lệ về cú pháp Java. Cảnh giác `doCallRealMethod()` vì nó cho phép side effect thật xảy ra ở lời gọi sau; không dùng chỉ để làm test có vẻ “đầy đủ”.

### 10.3. Spy trên bean Spring

Trong các phiên bản Spring hỗ trợ `@MockitoSpyBean`, annotation này wrap Spring bean bằng spy trong test context; các version cũ có `@SpyBean`. Đây là chuyện **quản lý bean trong Spring**, khác với `spy(new SomeClass())` tạo object cục bộ. Vì spy có thể gọi method thật, các transaction, cache, AOP proxy và tác động ngoài cần được xét cẩn thận. Không thêm spy vào context nếu chỉ muốn chứng minh một điều kiện thuần Java.

## 11. Verification mạnh, vừa đủ và có ý nghĩa

### 11.1. `verify(...)` với `void`

Cách phổ biến nhất khi test “service gọi gateway hay không”:

```java
verify(channel).send("buyer@example.org", "payload");
verify(channel, times(2)).send(anyString(), anyString());
verify(channel, never()).send(eq("blocked@example.org"), anyString());
verifyNoInteractions(channel);
```

**Các dòng là những ví dụ lựa chọn độc lập**, không phải bốn assertion cùng áp dụng lên một mock đã được gọi. `verifyNoInteractions(channel)` chỉ đúng nếu mock chưa được tương tác; `never()` xác nhận không có lời gọi khớp điều kiện, chứ không đảm bảo không có lời gọi khác.

Nên kiểm tra tương tác khi tương tác là **hợp đồng nghiệp vụ** (ví dụ không gửi thông báo khi người dùng bị từ chối, chỉ ghi log một lần, gửi đúng payload). Không cần `verifyNoMoreInteractions` trên mọi mock nếu khiến test quá nhạy với các lời gọi không liên quan.

### 11.2. `ArgumentCaptor` khi payload quan trọng

```java
ArgumentCaptor<String> payload =
        ArgumentCaptor.forClass(String.class);

verify(channel).send(eq("buyer@example.org"), payload.capture());
assertThat(payload.getValue()).contains("trace-R-09");
```

Đây là đoạn trong test đã chạy một lời gọi `channel.send(...)`. Captor có ích khi cần assert **thuộc tính của argument**, đặc biệt với object DTO hoặc message lớn. Không dùng captor để tạo stub tùy tiện khi một matcher đơn giản đã đủ: `ArgumentCaptor` hữu ích nhất ở bước **verification**.

### 11.3. Khi cần kiểm tra thứ tự

Nếu yêu cầu nghiệp vụ là ghi audit **trước** khi gửi gateway, có thể dùng `InOrder` với các mock liên quan. Nhưng không ràng buộc thứ tự khi hành vi cho phép chạy bất đồng bộ, khi thứ tự không thuộc hợp đồng hoặc khi các call không ảnh hưởng nhau. Verify quá chi tiết implementation làm test khó bảo trì dù kết quả nghiệp vụ vẫn đúng.

## 12. Các lỗi thường gặp theo dấu hiệu

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Java không compile tại `when(channel.send(...))` | `send` trả `void` | Dùng `doThrow/doAnswer/doNothing` hoặc chỉ `verify` |
| `Cannot mock/spy class ... final class` | Mock maker subclass hoặc version không hỗ trợ inline | Xác minh Mockito version và mock maker; nâng cấp/bật inline phù hợp |
| `mockStatic(...)` không tìm thấy | Mockito quá cũ (trước 3.4) hoặc import/dependency sai | Kiểm tra version, classpath và API của phiên bản |
| `mockStatic(...)` báo unsupported by mock maker | Đang dùng `SUBCLASS`/proxy maker thay vì inline | Dùng inline trên JVM tương thích; tránh cấu hình mock maker xung đột |
| `MockitoInitializationException`/Byte Buddy agent lỗi | Instrumentation/JVM/agent bị giới hạn | Xem root cause, JDK/test runner; cấu hình javaagent theo tài liệu Mockito |
| Test static xanh khi chạy lẻ, đỏ khi chạy suite | Scope không đóng, reuse cùng thread, static dependency bị mock ngoài ý muốn | Dùng `try-with-resources` cho từng test và giảm static mocking |
| Static stub không tác động đến code async | Lời gọi chuyển sang thread khác | Injection/adaptor hoặc thiết kế test theo thread thực |
| Spy gửi email/ghi file thật trong setup | Method thật chạy khi stubbing hoặc khi chưa stub | Dùng họ `do...`, giảm spy, mock dependency sát ranh giới |
| `InvalidUseOfMatchersException` | Trộn literal và matcher hoặc dùng matcher sai vị trí | Dùng `eq(...)` cho argument literal khi các argument khác dùng matcher |
| `UnnecessaryStubbingException` | Stub không được code under test sử dụng trong strict mode | Xóa stub thừa; kiểm tra đường code; tránh `lenient` tràn lan |
| `Wanted but not invoked` | Production không gọi mock đó; SUT dùng instance khác hoặc nhánh khác | Kiểm tra injection và input; không tăng `times` tùy tiện |
| Nhiều lời gọi bị bắt bởi `anyString()` quá rộng | Matcher không phản ánh nghiệp vụ | Dùng argument cụ thể, `eq` hoặc captor/assert cho payload |
| Thử mock `static final SOME_CONSTANT` | Đây là field, không phải static method | Truyền cấu hình qua constructor/config thay vì stub constant |

### 12.1. Lỗi thường xuất hiện khi chuyển sang JDK mới

Trong Mockito 5, inline mocking có thể sử dụng Java instrumentation. Trên **Java 21 trở lên**, quá trình tự attach agent có thể phát cảnh báo hoặc thất bại trong môi trường giới hạn; JDK có chính sách mới về dynamic agent loading. Tài liệu Mockito hướng dẫn cách gắn `mockito-core` bằng `-javaagent` cho JVM test. Đừng copy nguyên JVM argument từ một dự án khác vì đường dẫn jar và cách Gradle/Maven fork test JVM phải khớp build của bạn.

Nếu test trả lỗi “Could not initialize inline Byte Buddy mock maker”, trước hết đọc **cause cuối cùng có ý nghĩa**: JDK chưa hỗ trợ, attach bị cấm, thư viện Byte Buddy không tương thích, hoặc cấu hình mock maker xung đột. Cách xử lý có thể là dùng dependency được quản lý hợp lệ hoặc explicit javaagent theo tài liệu, không đơn giản tắt assertion.

### 12.2. Các hiểu lầm cần tránh

1. **“Void không mock được.”** Sai. Mockito mock void mặc định không làm gì; có thể verify hoặc dùng `do...`.
2. **“Final lúc nào cũng không mock được.”** Sai trong Mockito 5 inline trên JVM phù hợp, nhưng đúng có thể xảy ra với mock maker subclass/cấu hình cũ.
3. **“Mock static xong không cần đóng.”** Sai. `MockedStatic` phải được đóng để tránh ảnh hưởng test khác.
4. **“Static mock can thiệp mọi thread.”** Sai; scope là thread-local theo API.
5. **“Đã verify lời gọi là logic nghiệp vụ đúng.”** Chưa đủ; cần assert kết quả/ngữ nghĩa phù hợp. Một lời gọi sai định dạng nhưng vẫn “được gọi” có thể làm test xanh giả.
6. **“@MockitoBean và mock() giống nhau hoàn toàn.”** Không; annotation thuộc cơ chế override bean Spring, còn `mock()` tạo object thuần.
7. **“Một khi thư viện hỗ trợ, phải mock.”** Không; mục tiêu kiểm thử quyết định đâu là đối tượng thực, đâu là dependency cần cô lập.

## 13. Lựa chọn kỹ thuật dựa trên thiết kế hệ thống

| Tình huống | Lựa chọn thường hợp lý | Lý do |
|---|---|---|
| Service gọi cổng gửi email/queue `void` | Mock cổng qua interface, `verify`/`doThrow` | Tách side effect khỏi logic |
| Cần test xử lý lỗi từ gateway | `doThrow(error).when(mock).voidMethod(...)` | Ép chính xác nhánh lỗi |
| Cần thu thập payload được gửi | `ArgumentCaptor` hoặc `doAnswer` | Quan sát dữ liệu, không gửi thật |
| Legacy SDK có final class không sửa được | Mockito inline nếu version/JVM hỗ trợ | Có thể cô lập SDK mà không sửa source |
| Value object/DTO final | Tạo object thật | Kiểm tra dữ liệu thật, tránh mock thừa |
| Static utility legacy chỉ gọi trong một luồng | `mockStatic` với try-with-resources ngắn | Kiểm soát một điểm khó tiêm phụ thuộc |
| Static liên quan thời gian/ngẫu nhiên hoặc async | `Clock`/`Supplier`/interface injection | Tách dependency, ổn định qua thread và version |
| Test Spring bean đã có trong context | `@MockitoBean` hoặc cơ chế theo phiên bản | Thay bean trong đúng TestContext |
| Cần kiểm tra phối hợp bean/transaction thật | Test tích hợp với bean thật | Mock tất cả sẽ bỏ lỡ lỗi cấu hình/phối hợp |

Một thiết kế tốt thường hạn chế chỗ phải mock static/final phức tạp, nhưng không nên ép refactor lớn chỉ để một unit test có thể chạy. Cân nhắc chi phí thay đổi và mức độ kiểm thử thật cần thiết.

## 14. Bài tập thực hành và đáp án tham khảo

### Bài tập 1. Làm cho cổng `void` ném exception

Trong test, `channel.send(...)` phải ném `IllegalStateException("temporary failure")` bất kể destination/payload hợp lệ. Stub ra sao?

**Đáp án:**

```java
doThrow(new IllegalStateException("temporary failure"))
        .when(channel)
        .send(anyString(), anyString());
```

Sau đó gọi service và assert type/message của exception. Kiểm tra xem service dự kiến propagate hay handle lỗi trước khi chọn expected. Nếu service **có retry**, cần kiểm tra tổng số lần gọi trong hợp đồng thay vì chỉ mong một lần.

### Bài tập 2. Đảm bảo không gọi gửi thật khi đầu vào bị từ chối

Cho service `dispatch("R-11", "invalid")`. Nếu service phải từ chối địa chỉ, làm sao biết dependency side effect không bị gọi?

**Đáp án:**

```java
assertThatThrownBy(() ->
        service.dispatch("R-11", "invalid"))
        .isInstanceOf(IllegalArgumentException.class);

verifyNoInteractions(channel);
```

Giả định `service` đã được tạo với mock `channel` và AddressPolicy thật. Test kiểm tra cả lỗi đầu vào lẫn việc **không gọi gateway**.

### Bài tập 3. Kiểm chứng hành vi static được hoàn nguyên

**Đáp án:**

```java
assertThat(ShipmentService.TraceIds.forOrder("R-12"))
        .isEqualTo("trace-R-12");

try (MockedStatic<ShipmentService.TraceIds> traces =
             mockStatic(ShipmentService.TraceIds.class)) {
    traces.when(() ->
            ShipmentService.TraceIds.forOrder("R-12"))
            .thenReturn("fixed");

    assertThat(ShipmentService.TraceIds.forOrder("R-12"))
            .isEqualTo("fixed");
}

assertThat(ShipmentService.TraceIds.forOrder("R-12"))
        .isEqualTo("trace-R-12");
```

Quan sát: sau khi scope kết thúc, logic static thật trở lại. Đây là hành vi rất quan trọng cho tính độc lập của test.

### Bài tập 4. Phân biệt vấn đề version

Một dự án đang dùng Mockito 4.x mặc định với subclass mock maker. Lời gọi `mockStatic(TraceIds.class)` báo không hỗ trợ static mocks. Bạn có thể làm gì?

**Đáp án gợi ý:** xác minh dependency resolution và cấu hình mock maker; với Mockito 4 dùng inline mock maker nếu tương thích runtime (ví dụ cấu hình extension hoặc artifact phù hợp dòng version đó). Khi nâng lên Mockito 5, kiểm tra baseline Java 11+, các constraint về agent và dependency management. Không cần viết lại business logic chỉ vì một method `void`, và không cho rằng thay JUnit annotation sẽ kích hoạt static mocking.

## 15. Checklist trước khi chốt test dùng void/final/static

- [ ] Đã biết **version Mockito** và **mock maker** chạy thật trong test runtime.
- [ ] JDK, Byte Buddy/instrumentation và cách chạy Gradle/Maven/IDE tương thích.
- [ ] Với `void`, dùng `verify` nếu chỉ cần biết lời gọi; không stub thừa.
- [ ] Nếu cần ép lỗi `void`, dùng `doThrow` với exception hợp lệ theo method signature.
- [ ] `doAnswer` trả `null` cho `void` và không tự tạo side effect nguy hiểm.
- [ ] Với spy, đã hiểu method thật có thể chạy; dùng họ `do...` khi cần tránh tác động.
- [ ] Với `final`, không nhầm final variable với final class/method.
- [ ] Với `static`, `MockedStatic` nằm trong `try-with-resources` và được đóng sau test.
- [ ] Không giả định static mock hoạt động ở worker thread khác.
- [ ] Không thử stub field `static final` như một static method.
- [ ] Matcher được dùng nhất quán trong một lời gọi; verification/captor kiểm tra đủ đối số nghiệp vụ.
- [ ] Test còn assert hành vi thực của SUT; không mock mất thứ cần kiểm tra.
- [ ] Không có test phụ thuộc state/rò rỉ static mock của test khác.
- [ ] Test chạy được cả riêng lẻ lẫn full suite theo task/goal chính thức, và failure message chỉ rõ nguyên nhân.
- [ ] Nếu cần override Spring bean, chọn đúng annotation theo version Spring.

## 16. Kết luận

**`void` là vấn đề cú pháp stubbing; `final` và `static` là vấn đề cơ chế mock maker, phiên bản và JVM.** Mockito có công cụ thích hợp cho cả ba: `verify/doThrow/doAnswer/doNothing`, inline mocking và `MockedStatic`. Dùng chúng khi chúng giúp kiểm thử hành vi của một đơn vị rõ ràng, trong phạm vi ngắn và với assertion kiểm chứng được.

Với Spring Boot, hãy ưu tiên ranh giới phụ thuộc có thể injection để tránh side effect thật; sử dụng final/static mocking cho trường hợp có ích về chi phí hoặc mã legacy, và luôn kiểm tra test suite chạy ổn định trên JVM/CI thực tế.

## Tài liệu tham khảo

- [Mockito — tài liệu API của lớp Mockito](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html): void stubbing, final/inline mock maker, static mocking, version notes và Java agent.
- [Mockito — MockedStatic API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/MockedStatic.html): phạm vi thread-local, đóng resource, stubbing và verification.
- [Mockito — README chính thức](https://github.com/mockito/mockito/blob/main/README.md): Mockito 5, inline mock maker mặc định và Java baseline.
- [Spring Boot — Test Scope Dependencies](https://docs.spring.io/spring-boot/reference/testing/test-scope-dependencies.html): Mockito trong `spring-boot-starter-test`.
- [Spring Framework — @MockitoBean và @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): override Spring bean trong test context.
- [OpenJDK JEP 451](https://openjdk.org/jeps/451): thay đổi cảnh báo/chính sách dynamic loading của agent trên JDK mới.
