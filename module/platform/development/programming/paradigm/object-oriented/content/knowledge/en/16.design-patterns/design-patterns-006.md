# Decorator and Adding Behavior in Java

> **Topic:** OOP → Design Patterns → **Decorator Pattern**.  
> **Objective:** Understand how to extend an object's behavior by *wrapping* another object with the same contract, compose several decorators, control execution order, and recognize cases where the pattern is inappropriate.

## 1. The Problem: Adding Behavior Without Modifying Every Implementation

Suppose an application has a notification-sending component:

~~~java
interface MessageChannel {
    void send(Message message);
}
~~~

Initially, a **ConsoleChannel** prints notifications to the console for testing. Later, new requirements appear:

- Add an **[APP]** prefix to the content before sending.
- Reject content exceeding a length limit.
- Count calls that successfully complete the sending chain.
- Later, introduce **EmailChannel**, **SmsChannel**, or third-party provider adapters.

A hasty solution adds prefixing, length validation, counting, and logging logic to every notification class. This duplicates logic; each shared-rule change then affects multiple implementations. Another approach creates subclasses such as **LoggedEmailChannel**, **CheckedEmailChannel**, **CheckedLoggedEmailChannel**, and so on. The inheritance combinations become hard to maintain, especially when behaviors must be enabled or disabled flexibly.

**Decorator** addresses this through **composition**: an object implements the same interface as the wrapped object, holds a reference to it, and adds behavior before or after delegating the call.

~~~mermaid
flowchart LR
    Client["Client"] --> Count["CountingDecorator"]
    Count --> Prefix["PrefixDecorator"]
    Prefix --> Limit["LengthLimitDecorator"]
    Limit --> Core["ConsoleChannel"]
    Core --> Output["Đầu ra console"]
~~~

The diagram shows the call path **from outermost to innermost**. As calls return, outer decorators may perform further work after inner components finish.

**Core idea:** callers can use the entire chain through the same **MessageChannel** interface without knowing how many wrappers it contains.

## 2. Decorator Structure

| Role | In the notification example | Responsibility |
| --- | --- | --- |
| **Component** | **MessageChannel** | Defines the shared contract used by clients |
| **Concrete Component** | **ConsoleChannel** | Provides the original behavior: receiving and outputting notifications |
| **Decorator** | **ChannelDecorator** | Holds a reference to another **MessageChannel** while implementing the same contract |
| **Concrete Decorator** | **PrefixDecorator** | Transforms the content before sending |
| **Concrete Decorator** | **LengthLimitDecorator** | Validates a constraint before forwarding |
| **Concrete Decorator** | **CountingDecorator** | Tracks calls that return successfully |
| **Client** | **main** or business service | Assembles wrapper chains and invokes the shared interface |

Each wrapper can invoke its delegate **before**, **after**, or **around** the added behavior. It may also refuse to forward a call when a documented constraint is violated. However, changes to contract preconditions/postconditions must be explicitly designed and described; matching an interface syntactically does not guarantee safe substitutability among wrappers.

### Class Diagram

~~~mermaid
classDiagram
    class MessageChannel {
        <<interface>>
        +send(message) void
    }
    class ConsoleChannel {
        +send(message) void
    }
    class ChannelDecorator {
        <<abstract>>
        #next: MessageChannel
    }
    class PrefixDecorator {
        -prefix: String
        +send(message) void
    }
    class LengthLimitDecorator {
        -maxCodePoints: int
        +send(message) void
    }
    class CountingDecorator {
        -accepted: AtomicInteger
        +send(message) void
        +acceptedCalls() int
    }
    MessageChannel <|.. ConsoleChannel
    MessageChannel <|.. ChannelDecorator
    ChannelDecorator o--> MessageChannel : delegates
    ChannelDecorator <|-- PrefixDecorator
    ChannelDecorator <|-- LengthLimitDecorator
    ChannelDecorator <|-- CountingDecorator
~~~

An intermediate **ChannelDecorator** base class is optional for a single small wrapper; each decorator may directly implement **MessageChannel** and accept a **MessageChannel** in its constructor. The intermediate abstract class helps only when it reduces genuine duplication, such as shared non-null delegate validation.

## 3. Standalone Java 17 Example

Create **DecoratorDemo.java**. The example uses a **Message record** for immutable message values, **AtomicInteger** to count calls through a wrapper, and **String.codePointCount** to enforce a Unicode code-point limit rather than simply counting UTF-16 code units using **String.length()**.

~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class DecoratorDemo {

    public record Message(String recipient, String body) {
        public Message {
            if (recipient == null || recipient.isBlank()) {
                throw new IllegalArgumentException(
                        "Người nhận không được rỗng");
            }
            if (body == null || body.isBlank()) {
                throw new IllegalArgumentException(
                        "Nội dung không được rỗng");
            }
        }
    }

    public interface MessageChannel {
        void send(Message message);
    }

    // Thành phần gốc: chỉ giả lập gửi bằng console.
    public static final class ConsoleChannel implements MessageChannel {
        @Override
        public void send(Message message) {
            Objects.requireNonNull(message, "message");
            System.out.println(
                    "SEND " + message.recipient()
                    + ": " + message.body());
        }
    }

    // Lớp nền tùy chọn: giữ delegate của chuỗi decorator.
    public static abstract class ChannelDecorator
            implements MessageChannel {

        protected final MessageChannel next;

        protected ChannelDecorator(MessageChannel next) {
            this.next = Objects.requireNonNull(next, "next");
        }
    }

    // Thêm tiền tố nhưng không sửa đối tượng Message ban đầu.
    public static final class PrefixDecorator extends ChannelDecorator {
        private final String prefix;

        public PrefixDecorator(MessageChannel next, String prefix) {
            super(next);
            this.prefix = Objects.requireNonNull(prefix, "prefix");
        }

        @Override
        public void send(Message message) {
            Objects.requireNonNull(message, "message");
            next.send(new Message(
                    message.recipient(),
                    prefix + message.body()
            ));
        }
    }

    // Kiểm tra độ dài của thông điệp tại vị trí đặt decorator.
    public static final class LengthLimitDecorator
            extends ChannelDecorator {

        private final int maxCodePoints;

        public LengthLimitDecorator(
                MessageChannel next, int maxCodePoints) {
            super(next);
            if (maxCodePoints <= 0) {
                throw new IllegalArgumentException(
                        "Giới hạn phải lớn hơn 0");
            }
            this.maxCodePoints = maxCodePoints;
        }

        @Override
        public void send(Message message) {
            Objects.requireNonNull(message, "message");
            String body = message.body();
            int length = body.codePointCount(0, body.length());

            if (length > maxCodePoints) {
                throw new IllegalArgumentException(
                        "Thông điệp vượt quá "
                        + maxCodePoints + " Unicode code points");
            }
            next.send(message);
        }
    }

    // Chỉ đếm các lời gọi delegate trở về bình thường.
    public static final class CountingDecorator
            extends ChannelDecorator {

        private final AtomicInteger accepted = new AtomicInteger();

        public CountingDecorator(MessageChannel next) {
            super(next);
        }

        @Override
        public void send(Message message) {
            next.send(message);
            accepted.incrementAndGet();
        }

        public int acceptedCalls() {
            return accepted.get();
        }
    }

    public static void main(String[] args) {
        CountingDecorator channel = new CountingDecorator(
                new PrefixDecorator(
                        new LengthLimitDecorator(
                                new ConsoleChannel(), 80),
                        "[APP] "
                )
        );

        channel.send(new Message(
                "user-01", "Hóa đơn đã phát hành"));

        System.out.println(
                "Số lần xử lý không ném lỗi: "
                        + channel.acceptedCalls());
    }
}
~~~

Run in a terminal with JDK 17 or later:

~~~bash
javac DecoratorDemo.java
java DecoratorDemo
~~~

Output:

~~~text
SEND user-01: [APP] Hóa đơn đã phát hành
Số lần xử lý không ném lỗi: 1
~~~

In this example, **ConsoleChannel** only simulates sending by printing to the console. A normal return **does not guarantee** that a recipient actually received an email/SMS. Therefore the counter is called **acceptedCalls**, not **deliveredMessages**. In a real integration, define accepted, submitted-to-provider, and successfully delivered states according to the provider's contract.

**Call sequence:**

1. The client invokes **CountingDecorator.send(message)**.
2. **CountingDecorator** forwards the call to **PrefixDecorator**.
3. **PrefixDecorator** creates a new **Message** with the prefix and forwards it.
4. **LengthLimitDecorator** measures the content length **after the prefix is added**; if it exceeds the limit, it throws **IllegalArgumentException** without invoking the underlying component.
5. **ConsoleChannel** prints the message.
6. If the chain returns normally, **CountingDecorator** increments its counter; if an inner layer throws, the counter remains unchanged.

**Extensibility:** replace **ConsoleChannel** with another **MessageChannel** implementation while reusing the wrappers. Wrappers need not understand HTTP/SMTP libraries or destination devices.

## 4. Wrapping Order Determines Behavior

One of the most error-prone aspects of Decorator is **ordering**. Consider two assemblies:

~~~java
// A: thêm tiền tố trước, sau đó kiểm tra nội dung cuối cùng.
MessageChannel pipelineA =
        new DecoratorDemo.PrefixDecorator(
                new DecoratorDemo.LengthLimitDecorator(
                        new DecoratorDemo.ConsoleChannel(), 12),
                "[A] ");

// B: kiểm tra nội dung gốc trước, rồi mới thêm tiền tố.
MessageChannel pipelineB =
        new DecoratorDemo.LengthLimitDecorator(
                new DecoratorDemo.PrefixDecorator(
                        new DecoratorDemo.ConsoleChannel(), "[A] "),
                12);
~~~

With a body containing **10** ASCII characters, the **[A]** prefix plus a space takes **4** code points:

- **pipelineA:** checks 14 code points and **rejects** the message because the limit is 12.
- **pipelineB:** checks 10 code points and **accepts** the message; the underlying component receives 14 characters.

Both chains are valid Java, but only **pipelineA** ensures that the final output does not exceed 12 code points. If the external service limits **UTF-8 bytes**, counting code points is **still insufficient**: measure the encoded bytes with the required charset. Real systems must specify whether limits concern bytes, code points, UTF-16 code units, or displayed characters.

Ordering matters similarly for compression/encryption, caching/authorization, and retries/logging:

| Wrapping chain | Possible effect | Decision required |
| --- | --- | --- |
| Prefix → length validation | Checks the fully transformed text | Is the limit measured before or after transformation? |
| Cache → authorization | A cache serving data before authorization can leak information | Authenticate/authorize each request correctly, and partition caches by suitable context |
| Logging → retry | An outer logging wrapper may see only one overall call | Log one request or every attempt? |
| Retry → logging | The inner logging wrapper may run on every attempt | Is retrying the operation allowed without duplicate side effects? |
| Compression → encryption | Usually compresses before encrypting | The receiver must decrypt and then decompress using matching formats |

The table illustrates structural consequences. In production, safety also depends on the contract, data, persistence, failures, and security policy of each decorator. **Do not add retries to side-effectful operations merely by wrapping them in another class**; sending messages, charging payments, and writing data require idempotency keys or appropriate duplicate-prevention mechanisms. A timeout may occur after the recipient has already processed the request.

## 5. Testing Individual Decorators and Their Chain

One advantage of interface-based design is the ability to replace the underlying component with a small **fake** that records behavior. The JUnit 5 example below goes in **DecoratorDemoTest.java**, in the same package as the sample source.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class DecoratorDemoTest {

    static final class RecordingChannel
            implements DecoratorDemo.MessageChannel {
        DecoratorDemo.Message lastMessage;
        int calls;

        @Override
        public void send(DecoratorDemo.Message message) {
            lastMessage = message;
            calls++;
        }
    }

    @Test
    void tienToDuocThemMaKhongThayDoiMessageGoc() {
        RecordingChannel fake = new RecordingChannel();
        var channel = new DecoratorDemo.PrefixDecorator(fake, "[APP] ");
        var original =
                new DecoratorDemo.Message("u01", "Xin chào");

        channel.send(original);

        assertEquals("[APP] Xin chào", fake.lastMessage.body());
        assertEquals("Xin chào", original.body());
        assertEquals(1, fake.calls);
    }

    @Test
    void chuoiChanDuocNoiDungQuaDaiSauKhiThemTienTo() {
        RecordingChannel fake = new RecordingChannel();

        var channel = new DecoratorDemo.PrefixDecorator(
                new DecoratorDemo.LengthLimitDecorator(fake, 8),
                "[A] ");

        assertThrows(IllegalArgumentException.class, () ->
                channel.send(
                        new DecoratorDemo.Message("u01", "12345")));
        // "[A] " dài 4, cộng "12345" dài 5 = 9 > 8.
        assertEquals(0, fake.calls);
    }

    @Test
    void boDemChiTangKhiDelegateTroVeBinhThuong() {
        RecordingChannel fake = new RecordingChannel();
        var counted = new DecoratorDemo.CountingDecorator(
                new DecoratorDemo.LengthLimitDecorator(fake, 5));

        counted.send(
                new DecoratorDemo.Message("u01", "Hello"));
        assertThrows(IllegalArgumentException.class, () ->
                counted.send(
                        new DecoratorDemo.Message("u01", "123456")));

        assertEquals(1, counted.acceptedCalls());
        assertEquals(1, fake.calls);
    }
}
~~~

These tests need no network or SMTP/SMS server. They verify exactly what each wrapper promises: forwarding, transformation, blocking delegation, and the condition for incrementing the counter. JUnit Jupiter must be on the project's classpath to run the test file; standalone **DecoratorDemo.java** does not require JUnit.

Add integration tests when connecting to a real provider to check encoding, payload limits, retry policies, and delivery-state mapping. Fake-based tests cannot prove that the real provider always behaves according to the fake's assumptions.

## 6. How Does Decorator Differ from Other Extension Techniques?

| Technique | How it works | When to consider it |
| --- | --- | --- |
| **Decorator** | An object with the **same interface** wraps another object and adds composable behavior | Add logging, metrics, validation, buffering, compression, transformation, etc. per instance |
| **Inheritance** | A subclass changes/extends the behavior of a base class | A genuine subtype relationship is stable and has few independent combinations |
| **Proxy** | May share the interface and delegate, but primarily **controls access** to another object (lazy loading, remote access, access control, etc.) | Clients need a representative object or controlled access |
| **Adapter** | Converts an incompatible **contract/interface** into the contract expected by clients | Integrate a library, legacy API, or provider with another interface |
| **Strategy** | Encapsulates **alternative** algorithms and selects an appropriate one | Several ways exist to perform the same task |
| **Chain of Responsibility** | Passes requests along handlers, each typically choosing to handle or forward | Several processing steps have their own stop/forward conditions |
| **AOP** | Declares cross-cutting advice at framework-supported join points | Apply shared policies to many beans/methods without manually wrapping them |

**Proxy and Decorator have similar structures**, so classify them by design intent and actual responsibility rather than diagrams alone. **Strategy** selects *one implementation approach*; Decorator adds *behavioral layers* around the selected implementation. They can be combined.

In Spring, **@Transactional**, some interceptors, and proxies provide mechanisms for cross-cutting concerns, but that does not mean every Decorator use case should move to AOP. For per-instance customization or explicit assembly order, plain Java Decorators are easier to read and test. Conversely, a policy applied uniformly across hundreds of endpoints may fit filters/interceptors/AOP, depending on interception points. Spring proxy-based AOP also has subtleties: for example, internal calls from one method to another on the same object generally bypass the proxy.

## 7. Familiar Decorator Examples in the JDK

A clear example is **java.io.InputStream**:

~~~java
import java.io.BufferedInputStream;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;

class InputExample {
    static int firstByte(String path) throws IOException {
        try (InputStream in = new BufferedInputStream(
                new FileInputStream(path))) {
            return in.read();
        }
    }
}
~~~

**FileInputStream** reads bytes from a file; **BufferedInputStream** wraps an **InputStream** to add buffering during reads. Clients continue invoking **read()** through the **InputStream** contract. When **try-with-resources** closes the wrapper, that wrapper closes the inner stream according to its contract.

Two lessons follow: (1) clients need no changes when a wrapper is added; (2) wrappers can manage resources/lifecycles, so understand closing, flushing, and composition order instead of assuming decorators are entirely independent.

A related example is **Collections.unmodifiableList(list)**, which creates a view that cannot be modified through that view, but **does not create a copy**: changes to the original list may still appear in the view. For an independent snapshot, consider **List.copyOf(list)** and the immutability of its elements. This illustrates a wrapper that extends/restricts behavior without necessarily copying data.

## 8. Designing Safe Decorators for Production

### 8.1. Preserve the Component Contract

A wrapper must preserve the meaning of **send**, error-handling rules, and invariants expected by clients. For example:

- A decorator should not silently drop a message while reporting success if the contract promises delegation or an explicit error.
- When adding content limits, define them as part of the pipeline's public policy; clients should know when validation errors occur.
- For asynchronous results (**CompletableFuture**), do not immediately measure/count a future's creation; decide whether to measure scheduling, successful future completion, or provider-confirmed delivery.
- If a wrapper owns resources that must be closed, make the lifecycle explicit (for example, **AutoCloseable**) and avoid double closing or leaks.

### 8.2. Decide How to Handle Exceptions

Decorators execute **before** and **after** delegates, so exception timing matters. In the **CountingDecorator** above, the counter increases after a normal return; it does not report real-world delivery.

For timing, **finally** is often appropriate if failed requests should also be measured:

~~~java
@Override
public void send(Message message) {
    long start = System.nanoTime();
    try {
        next.send(message);
    } finally {
        long elapsedNanos = System.nanoTime() - start;
        recordDuration(elapsedNanos); // Phương thức đo lường do ứng dụng định nghĩa.
    }
}
~~~

The snippet only illustrates **the body of a timing decorator**; standalone compilation also requires a class declaring **next**, the **send** contract, and **recordDuration**. Do not use **finally** to silently turn failure into success; exceptions must still propagate or be converted according to the defined contract. Also prevent metric-recording exceptions from masking primary failures.

### 8.3. Consider State, Concurrency, and Scope

In the example, **PrefixDecorator** and **LengthLimitDecorator** hold **final** configuration and do not mutate their state. **CountingDecorator** uses **AtomicInteger**, so incrementing and reading the counter are individually safe under concurrent updates; that **does not make the entire chain thread-safe**. Safety also depends on **next**, the data passed through, external resources, and any other mutation.

When caching by user, ensure keys contain sufficient authorization context and suitable expiration. When logging, do not log personal information, tokens, or sensitive data by default. When retrying, require duplicate-execution protection. When rate-limiting, distinguish per-instance, per-user, per-tenant, and system-wide limits.

### 8.4. Avoid Turning Assembly into a Maze

A very long chain, implicit configuration ordering, or wrappers with non-obvious side effects can be harder to debug than the original solution. Instead:

1. Name each decorator by its **specific behavior**, such as **LengthLimitDecorator**, rather than a vague name like **EnhancedChannel**.
2. Centralize assembly in the **composition root** or a clearly named factory, especially for shared chains.
3. Document outer-to-inner order and the reasons for it; write integration tests for risky interactions.
4. Avoid a single wrapper that logs, caches, retries, and transforms content when those responsibilities vary independently.
5. When behavior applies everywhere without variation, consider a shared service, interceptor, or the implementation itself instead of excessive wrappers.

## 9. When Should You Choose Decorator, and When Should You Avoid It?

**Consider Decorator when** behaviors must be enabled, disabled, or composed around individual objects, multiple implementations share extra logic, changing the original implementation is impossible or undesirable, and one contract can represent the pipeline.

**Avoid applying it mechanically when** a simple call or helper function is enough, behavior never needs composition, or multiple wrappers obscure the contract. A rule mandatory for all objects may belong at the domain boundary rather than depending on clients to remember a wrapper. Do not use Decorator merely to avoid refactoring a class with tangled responsibilities.

Decorator's dynamic flexibility is useful, but must be balanced against **KISS** (*Keep It Simple*) and **composition over inheritance**: composition improves flexibility but does not eliminate the cost of controlling complexity.

## 10. Practical Exercise

Build a document-reading system with this contract:

~~~java
interface DocumentReader {
    String read(String documentId);
}
~~~

An **InMemoryDocumentReader** reads from a **Map<String, String>**. Implement three independent decorators:

- **TrimmingReader** removes leading/trailing whitespace from returned content.
- **CachingReader** caches content by document ID after the first read. Define TTL/invalidation if the data can change; for the exercise, assume the source data is immutable.
- **CountingReader** counts calls to **read()** on the wrapper. Clarify whether this counts requests or accesses to the actual source.

Assemble two pipelines:

~~~text
Counting → Caching → Trimming → InMemory
Counting → Trimming → Caching → InMemory
~~~

Read the same document ID twice and compare: how often was the source called, what content was cached, and does moving the cache change behavior if trimming rules change? Use a fake reader for testing rather than depending on files or networks.

**Success criteria:**

- All decorators implement the same **DocumentReader** interface.
- Adding trim/cache/count does not modify **InMemoryDocumentReader**.
- Each wrapper has one clearly named responsibility; pipeline order is intentional.
- Tests verify final results, delegate call counts, and behavior when the source throws an exception.
- Do not share cached sensitive data between users when keys or access policies do not distinguish users.

**Remember:** Decorator extends behavior **by wrapping another object with the same contract**. Its practical value is composing behaviors without proliferating subclasses or changing core code; its practical challenges are preserving the contract, managing order, and clarifying errors/state at each wrapper layer.
