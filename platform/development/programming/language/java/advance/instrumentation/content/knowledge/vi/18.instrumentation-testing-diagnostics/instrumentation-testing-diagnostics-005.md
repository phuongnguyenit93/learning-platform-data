# Bảo toàn kết quả, ngoại lệ, trạng thái và số lần gọi phương thức ứng dụng

**Ngữ cảnh:** Java Advance → instrumentation → **Kiểm thử và chẩn đoán**.

Instrumentation đưa mã phụ trợ như tracing, metrics, audit hoặc profiling vào quá trình thực thi ứng dụng. Nó chỉ đáng tin cậy khi **không làm thay đổi hành vi nghiệp vụ mà công cụ được giao quan sát**. Kiểm thử chỉ xác nhận “chương trình vẫn chạy” là chưa đủ: một transformer có thể vô tình **gọi method hai lần**, đổi giá trị trả về, **bọc/thay ngoại lệ**, ghi thêm dữ liệu hoặc làm mất ngữ cảnh đồng thời trong khi vẫn vượt qua smoke test đơn giản.

Mục tiêu bài này là kiểm chứng, trên **cùng một bộ input và điều kiện kiểm thử có thể tái lập**, rằng phiên bản gốc (*baseline*) và phiên bản được instrument (*instrumented*) bảo toàn:

1. **Kết quả** — giá trị trả về, kiểu trả về, reference identity khi thuộc hợp đồng, và các tính chất đặc biệt của dữ liệu.
2. **Ngoại lệ** — có ném hay không, kiểu, message/cause/suppressed theo hợp đồng, **chính object Throwable** khi đường đi chỉ có nhiệm vụ quan sát, và không nuốt/chuyển loại lỗi.
3. **Trạng thái** — field/state mutation, collections, static state, counters, DB/cache/IO effects và invariants sau chạy.
4. **Số lần gọi phương thức ứng dụng** — mỗi lần gọi nghiệp vụ thật phải tương ứng **một lần thực thi**, không bị transformer/wrapper gọi lại để “xem kết quả”, không có bản ghi span duplicate vì chèn hook hai lần.

Bài có **lab hoàn chỉnh Java 17+ với Java agent dùng ASM**, hai lệnh chạy riêng (baseline và instrumented), assertion và stdout dự kiến, cùng ma trận kiểm thử cho return/exception/recursion/concurrency/async. Không cần quyền dynamic attach; agent dùng `-javaagent` khi JVM khởi động.

> **Giới hạn quan trọng:** “Bảo toàn” ở đây là **các bất biến nghiệp vụ có thể quan sát theo tiêu chí kiểm thử**. Một agent thực tế vẫn tiêu thụ CPU/bộ nhớ, có thể ảnh hưởng timing, JIT, stack traces hay scheduling. Không hứa **tương đương toàn bộ hệ thống cho mọi input** chỉ từ vài test cases. Mọi thay đổi của telemetry tự thân là **side effect đã chủ đích**, cần phân biệt nó với side effects nghiệp vụ bị thay đổi.

## 1. Định nghĩa chính xác điều gì phải bằng nhau

Gọi:

- `P` là chương trình gốc.
- `T(P)` là chương trình sau instrumentation.
- `x` là input được cung cấp.
- `E` là điều kiện môi trường/cấu hình đã kiểm soát.
- `B(P,x,E)` là kết quả quan sát nghiệp vụ, **không tính telemetry nội bộ**.

Mục tiêu kiểm thử là:

```text
B(P, x, E) == B(T(P), x, E)
```

Đây là **mô hình kiểm thử**, không phải đòi hỏi bytes hoặc thời gian thực thi của hai chương trình giống nhau. Có thể phân rã:

```text
BusinessObservation =
  {
    normalResult,
    thrownOutcome,
    businessStateAfter,
    externallyVisibleEffects,
    applicationMethodInvocationCounts
  }
```

Đối với mỗi phép gọi đồng bộ, một bên phải trả giá trị bình thường hoặc ném ngoại lệ; **không thể cùng lúc trả bình thường và ném ra cho caller**. Hai bản chạy phải có cùng lựa chọn theo hợp đồng đã định.

### 1.1. Quy tắc so sánh phù hợp từng loại

| Đối tượng cần so | Thế nào là “không đổi”? | Lỗi dễ bỏ lọt |
| --- | --- | --- |
| `int`, `long`, `boolean` và primitive khác | Cùng giá trị | Probe vô tình thay hoặc mất operand trên stack |
| `float`, `double` | Theo tiêu chí hợp đồng; xét `NaN`, `-0.0`, bit patterns khi cần | `==` không nhận diện mọi khác biệt bit-level |
| `String` / DTO immutable | Nội dung tương đương; identity nếu API cam kết | Wrapper tạo chuỗi mới và caller dựa vào `==` |
| Reference return | Giữ **cùng reference object** khi contract yêu cầu, không copy | Tạo list/object thay vì trả bản gốc |
| `void` | Không đổi nghiệp vụ và side effects | “Không có return” không có nghĩa không có lỗi |
| Ngoại lệ | Kiểu, message, cause/suppressed, identity theo contract | `catch(Exception e) { throw new RuntimeException(e); }` |
| State | Fields, collections, object graph/static state, versioning | Hook thêm một mutation hoặc bỏ mutation |
| External effect | Cùng DB writes/HTTP calls/messages/files theo contract | Agent dùng “retry” thực thi nghiệp vụ hai lần |
| Count ứng dụng | Cùng số lần **method body được chạy** | Hook đo bằng cách gọi lại method |
| Event đo lường | Số event phải khớp policy quan sát, **không phải** business call | Entry 1 lần nhưng hai exit events, span trùng |

Không phải mọi hệ thống yêu cầu so **từng byte** của serialized data hoặc **từng dòng stack trace**. Xác định **acceptance criteria trước khi đo**, tránh vừa chạy xong mới quyết định bỏ qua những khác biệt bất tiện.

### 1.2. Ba loại “số lần gọi” khác nhau

Một invocation của `Service.process` có thể dẫn đến nhiều lần gọi tới helper methods; mỗi lần instrument còn chạy thêm `Probe.onEntry`. Vì vậy cần tách:

```text
N_app(m)   = số lần thân phương thức nghiệp vụ m thực thi
N_probe(m) = số lần hook quan sát m được kích hoạt
N_span(m)  = số span/event logical được ghi nhận cho m
```

Với **entry-only instrumentation** trong lab:

```text
N_app(m) baseline == N_app(m) instrumented
N_probe(m) baseline == 0
N_probe(m) instrumented == N_app(m) instrumented
```

Với full tracing, thường muốn **một logical span cho mỗi invocation**, có **một start và một terminal outcome** (normal/error). Nhưng không tự đồng nhất “hai events START/END” với “hai business invocations”.

## 2. Vì sao instrumentation dễ phá invariants?

### 2.1. Gọi lại method để đo kết quả

Một wrapper nguy hiểm:

```java
// Anti-pattern, không phải source hoàn chỉnh.
Object first = target.call();
logger.info("result=" + target.call()); // GỌI LẦN HAI!
return first;
```

Nếu `target.call()` chuyển tiền, ghi DB, gửi email hoặc tăng counter, nó đã chạy hai lần. Logger không được **tự gọi lại business method** chỉ để lấy giá trị hiển thị. Hãy lưu **kết quả của một invocation**, sau đó chỉ đọc reference mà không gọi lại target.

Bản hợp lý ở mức Java wrapper:

```java
// Fragment: target và các loại được khai báo ở chương trình khác.
Object result = target.call();
try {
    safeRecord(result);
} catch (RuntimeException telemetryFailure) {
    // Chỉ theo chính sách fail-open của TELEMETRY.
}
return result;
```

Tuy nhiên cách viết cũng cần xem `safeRecord` có làm thay đổi `result`/object graph không; một logger dùng `result.toString()` có thể thực thi code ứng dụng, làm phát sinh side effects hoặc ném exception. “Ghi log không làm đổi behavior” chỉ đúng nếu logger/probe được thiết kế **có giới hạn**.

### 2.2. Bọc hoặc nuốt ngoại lệ

Một anti-pattern khác:

```java
// Anti-pattern: đổi loại và identity throwable của nghiệp vụ.
try {
    return service.doWork();
} catch (Exception original) {
    throw new IllegalStateException("instrumentation failed", original);
}
```

Cách này đổi exception type/message/identity trên đường caller nhìn thấy; code bắt `IOException` hay `IllegalArgumentException` có thể hành xử khác.

Khi cần quan sát lỗi, thường phải **ghi nhận mà không biến đổi throwable** và **ném lại chính object cũ**. Trong mô hình Java đồng bộ, dùng `catch` rồi `throw original;` với kiểu checked đúng, hoặc dùng `finally` chỉ cho cleanup. Nhưng **không** đặt telemetry call có thể throw vào `finally` rồi mặc nhiên tin rằng original throwable được bảo toàn: lỗi từ `finally` có thể **ghi đè outcome**.

### 2.3. Hook chạy hai lần ở cùng một method

Ví dụ:

```text
Thời điểm load:  instrument BankAccount.deposit lần 1
Thời điểm retransform:  transformer chèn thêm cùng hook lần 2
Kết quả: một business invocation -> hai Probe.onEntry
```

Đây là **tình huống có thể xảy ra ở pipeline thiếu idempotency**, không phải mặc định mọi retransform luôn nhân đôi hook. `ClassFileTransformer` có quy tắc khác nhau giữa transformers có/không hỗ trợ retransformation. Luôn kiểm tra *stage*, output bytes và mã hook thật sự đã có. Tránh dùng constant pool index hoặc offset byte ngẫu nhiên làm marker.

### 2.4. Probe đổi state hoặc lock ordering

Một helper đo lường vô tình viết lên `ThreadLocal` không cleanup, thay MDC của caller, giữ lock không đúng thứ tự, gọi application service trong logging hoặc kích hoạt callback đệ quy có thể:

- Làm dirty context của request tiếp theo trên thread pool.
- Gây deadlock hoặc contention khác biệt.
- Gây thêm network call/DB write.
- Đổi static cache, transaction scope hoặc permission context.
- Tạo recursion/`StackOverflowError` trong tracer.

**Nguyên tắc thiết kế:** đo lường phải được cô lập logic khỏi ứng dụng, giới hạn tài nguyên, không gọi lại method mục tiêu và không điều chỉnh dữ liệu đầu vào/đầu ra nghiệp vụ.

## 3. Hợp đồng `ClassFileTransformer` liên quan tới tính đúng đắn

JDK 17 định nghĩa:

```java
// Fragment API, không phải chương trình độc lập.
byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
        throws IllegalClassFormatException;
```

Có cả overload **sáu tham số có `Module`** trên JDK 9+; việc override phiên bản năm tham số vẫn hợp lệ. Đối với một transformer:

- **Không sửa trực tiếp `classfileBuffer`** do JVM cung cấp.
- Không cần transform thì **`return null`**.
- Cần transform thì trả **mảng `byte[]` mới** chứa class file hợp lệ.
- Nhiều transformers có thể được **chaining**; output trước là input sau.
- JVM vẫn có thể tiếp tục load với bytes chưa đổi nếu transformer throw exception; đó **không phải một cơ chế fail-fast đáng tin** để đảm bảo agent đã instrument. Cần kiểm chứng hiệu lực thật sự và báo error rõ.
- Khi redefine/retransform, output phải thỏa **schema restrictions**, stack frames, bytecode verifier và mọi điều kiện của VM.
- `className` dùng **internal name** dạng `demo/BankAccount`, không phải tên Java source dạng `demo.BankAccount`.

**Lưu ý quyền kiểm thử:** với mỗi method cần đo, hãy kiểm tra class loader, method descriptor và số callback. Một tên method overload không đủ để nhận diện duy nhất một phương thức.

## 4. Thiết kế thí nghiệm so sánh hai JVM độc lập

Chúng ta sẽ giữ nguyên **source ứng dụng** và chạy **hai process Java**:

```text
Run A (baseline)
  java -cp app-and-agent.jar demo.App
       │
       ▼
  BankAccount methods nguyên bản
       │
       ▼
  Assert result / exception / state / application counts
  Probe counts = 0

Run B (instrumented)
  java -DexpectTrace=true -javaagent:app-and-agent.jar \
       -cp app-and-agent.jar demo.App
       │
       ▼
  Agent premain -> ClassFileTransformer -> ASM chèn onEntry
       │
       ▼
  Cùng BankAccount business methods
       │
       ▼
  Assert result / exception / state / application counts
  Probe counts = actual business counts
```

Hai process riêng giúp tránh static counters, JIT state, class loading và side effects từ run trước làm nhiễu run sau. Dữ liệu đầu vào giống hệt trong mã, không dùng thời gian thực/random/database ngoài để quyết định kết quả.

**Điểm then chốt:** chương trình baseline và instrumented in các dòng **BUSINESS, EXCEPTIONS, IDENTITY, STATE, CALLS** như nhau. Chỉ dòng **PROBE** khác **theo chủ ý**. Nếu một trong các bất biến nghiệp vụ lệch, **không** coi test đạt chỉ vì vẫn in được `RESULT=PASS` từ code khác.

### 4.1. Ca kiểm thử của lab

| Method | Input/kịch bản | Dấu hiệu cần bảo toàn | Số lượt |
| --- | --- | --- | --- |
| `deposit(int)` | `20` và `-1` | Trả 120; một lỗi argument; số lần thực thi = 2 | 2 |
| `withdraw(int)` | `30` và `200` | Trả 90; một lỗi insufficient funds; số lần = 2 | 2 |
| `raise(RuntimeException)` | Truyền một `marker` cụ thể | Ném lại **cùng object marker**, không đổi suppressed | 1 |
| `recursive(int)` | `3` | Trả 6; gọi cho `3,2,1,0`, đếm đúng 4 | 4 |
| `tick()` | Hai threads, mỗi thread 100 lần | State tăng đúng 200; đồng bộ bằng `synchronized` | 200 |

Đây là **số lượt thực thi thân phương thức**, **không** phải tổng số Java method calls của toàn ứng dụng (lệnh getter, `Future.get`, `System.out.println`... cũng là phương thức nhưng nằm ngoài phạm vi instrument).

## 5. Lab Java 17+: mã nguồn, agent, build và assertions

### 5.1. Cấu trúc dự án

```text
transparency-lab/
├── pom.xml
└── src/main/java/demo/
    ├── BankAccount.java
    ├── Probe.java
    ├── TraceAgent.java
    └── App.java
```

Cần **JDK 17+**, Maven 3.x và quyền tải Maven dependencies (hoặc repository/cache nội bộ đã có). Maven sẽ sinh **một JAR được shade gồm mã ứng dụng, agent và ASM**. Ta dùng cùng artifact ở cả hai lần chạy; khác biệt duy nhất là có/không có `-javaagent`.

### 5.2. `pom.xml` — Maven 17 và ASM

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>transparency-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.7.1</version>
    </dependency>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm-commons</artifactId>
      <version>9.7.1</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.6.0</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <manifestEntries>
                    <Premain-Class>demo.TraceAgent</Premain-Class>
                  </manifestEntries>
                </transformer>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
```

`maven-shade-plugin` đóng gói cả `asm` và `asm-commons` vào JAR để JVM có thể load transformer trong `premain`. Nếu dùng JAR thường chỉ có các classes dự án mà bỏ dependencies ASM, startup agent có thể ném `NoClassDefFoundError: org/objectweb/asm/...` trước khi ứng dụng bắt đầu. Manifest `Premain-Class` là bắt buộc khi dùng `-javaagent`. Bài lab không cần `Can-Retransform-Classes` vì transformer đăng ký ở **load time**, không có lệnh retransform.

### 5.3. `src/main/java/demo/BankAccount.java` — nghiệp vụ có trạng thái

```java
package demo;

public final class BankAccount {
    private int balance;
    private int depositCalls;
    private int withdrawCalls;
    private int raiseCalls;
    private int recursiveCalls;
    private int ticks;

    public BankAccount(int initialBalance) {
        this.balance = initialBalance;
    }

    public int deposit(int amount) {
        depositCalls++;
        if (amount <= 0) {
            throw new IllegalArgumentException(
                    "amount must be positive");
        }
        balance += amount;
        return balance;
    }

    public int withdraw(int amount) {
        withdrawCalls++;
        if (amount <= 0) {
            throw new IllegalArgumentException(
                    "amount must be positive");
        }
        if (amount > balance) {
            throw new IllegalStateException(
                    "insufficient funds");
        }
        balance -= amount;
        return balance;
    }

    public void raise(RuntimeException marker) {
        raiseCalls++;
        throw marker;
    }

    public int recursive(int n) {
        recursiveCalls++;
        if (n <= 0) {
            return 0;
        }
        return n + recursive(n - 1);
    }

    public synchronized void tick() {
        ticks++;
    }

    public int balance() {
        return balance;
    }

    public int depositCalls() {
        return depositCalls;
    }

    public int withdrawCalls() {
        return withdrawCalls;
    }

    public int raiseCalls() {
        return raiseCalls;
    }

    public int recursiveCalls() {
        return recursiveCalls;
    }

    public synchronized int ticks() {
        return ticks;
    }
}
```

Đây là **class ứng dụng không có mã instrumentation**. Trong test, các counters `depositCalls`/`withdrawCalls`/`raiseCalls`/`recursiveCalls` là một phần **state nghiệp vụ của bài lab**, được tăng bên trong mỗi method và được dùng làm “nguồn sự thật” về số lần thân phương thức đã chạy.

- `deposit(20)` trên balance 100 trả 120.
- `withdraw(30)` trả 90.
- `deposit(-1)` ném `IllegalArgumentException` **sau khi ghi nhận một lượt gọi**, nhưng không đổi balance.
- `withdraw(200)` ném `IllegalStateException`, không đổi balance.
- `raise(marker)` ném **đúng object** được truyền vào, không tạo wrapper.
- `recursive(3)` gọi bốn lần (3,2,1,0) và trả `3+2+1+0=6`.
- `tick` là `synchronized`, nên hai threads có thể tăng đúng 200 lần nếu mỗi thread gọi 100 lần và chờ chúng kết thúc.

Độ dài/cấu trúc của class không quan trọng bằng việc có **return bình thường, exception, object identity, state, recursion và concurrency** trong cùng một kịch bản.

### 5.4. `src/main/java/demo/Probe.java` — state riêng của agent

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public final class Probe {
    private static final AtomicInteger DEPOSIT = new AtomicInteger();
    private static final AtomicInteger WITHDRAW = new AtomicInteger();
    private static final AtomicInteger RAISE = new AtomicInteger();
    private static final AtomicInteger RECURSIVE = new AtomicInteger();
    private static final AtomicInteger TICK = new AtomicInteger();

    private Probe() {}

    public static void onEntry(String name) {
        switch (name) {
            case "deposit" -> DEPOSIT.incrementAndGet();
            case "withdraw" -> WITHDRAW.incrementAndGet();
            case "raise" -> RAISE.incrementAndGet();
            case "recursive" -> RECURSIVE.incrementAndGet();
            case "tick" -> TICK.incrementAndGet();
            default -> {
                // Ngoài phạm vi mẫu: bỏ qua.
            }
        }
    }

    public static int count(String name) {
        return switch (name) {
            case "deposit" -> DEPOSIT.get();
            case "withdraw" -> WITHDRAW.get();
            case "raise" -> RAISE.get();
            case "recursive" -> RECURSIVE.get();
            case "tick" -> TICK.get();
            default -> 0;
        };
    }
}
```

`Probe` **không gọi lại bất kỳ phương thức nào của `BankAccount`**. Nó chỉ tăng các `AtomicInteger` độc lập; vì vậy logging không trực tiếp thay field `balance`, `ticks` hoặc counters nghiệp vụ. `AtomicInteger` quan trọng khi nhiều threads gọi `tick` đồng thời: dùng `int++` thông thường trong probe có thể mất updates và báo sai số lượt.

Trong sản phẩm thật, ngay cả `AtomicInteger.incrementAndGet()` cũng có chi phí và lý thuyết có thể bị ảnh hưởng bởi lỗi hệ thống nghiêm trọng như `OutOfMemoryError` khi một helper class lần đầu load. **Không có telemetry helper Java nào tuyệt đối không gây tác động**. Hãy đánh giá fail-open, initialization sớm, giới hạn overhead và loại trừ helper classes khỏi instrumentation.

### 5.5. `src/main/java/demo/TraceAgent.java` — ASM transformer chỉ chèn entry hook

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.commons.AdviceAdapter;

public final class TraceAgent {
    private TraceAgent() {}

    public static void premain(
            String arguments, Instrumentation instrumentation) {
        instrumentation.addTransformer(new AccountTransformer());
    }

    private static final class AccountTransformer
            implements ClassFileTransformer {

        private static boolean watched(
                String name, String descriptor) {
            return switch (name) {
                case "deposit", "withdraw", "recursive" ->
                        "(I)I".equals(descriptor);
                case "raise" ->
                        "(Ljava/lang/RuntimeException;)V"
                                .equals(descriptor);
                case "tick" -> "()V".equals(descriptor);
                default -> false;
            };
        }

        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer)
                throws IllegalClassFormatException {

            if (!"demo/BankAccount".equals(className)) {
                return null;
            }

            try {
                ClassReader reader = new ClassReader(classfileBuffer);
                ClassWriter writer = new ClassWriter(
                        reader, ClassWriter.COMPUTE_MAXS);

                ClassVisitor visitor =
                        new ClassVisitor(Opcodes.ASM9, writer) {
                    @Override
                    public MethodVisitor visitMethod(
                            int access,
                            String name,
                            String descriptor,
                            String signature,
                            String[] exceptions) {

                        MethodVisitor original = super.visitMethod(
                                access, name, descriptor,
                                signature, exceptions);

                        if (original == null
                                || (access & (Opcodes.ACC_ABSTRACT
                                    | Opcodes.ACC_NATIVE)) != 0
                                || !watched(name, descriptor)) {
                            return original;
                        }

                        return new AdviceAdapter(
                                Opcodes.ASM9, original, access,
                                name, descriptor) {
                            @Override
                            protected void onMethodEnter() {
                                visitLdcInsn(name);
                                visitMethodInsn(
                                        Opcodes.INVOKESTATIC,
                                        "demo/Probe",
                                        "onEntry",
                                        "(Ljava/lang/String;)V",
                                        false);
                            }
                        };
                    }
                };

                reader.accept(visitor, 0);
                return writer.toByteArray();
            } catch (RuntimeException failure) {
                IllegalClassFormatException error =
                        new IllegalClassFormatException(
                            "Cannot transform demo/BankAccount");
                error.initCause(failure);
                throw error;
            }
        }
    }
}
```

**Phân tích đường bytecode:**

1. Transformer chỉ chọn **`demo/BankAccount`** ở load time, không đụng đến JDK classes, `Probe`, `TraceAgent` hoặc class logger. Filter dựa vào internal name có dấu `/`.
2. `watched` chọn **đúng name + descriptor** của năm nghiệp vụ. Constructors, getters, overload khác không bị instrument.
3. `ClassReader` đọc input mà **không ghi vào `classfileBuffer`**. `ClassWriter` sinh **mảng byte mới**.
4. `AdviceAdapter.onMethodEnter` chèn hai instructions ở đầu mỗi method đã chọn: nạp tên method bằng `LDC` và gọi `Probe.onEntry(name)` đúng một lần khi method thực sự bắt đầu chạy.
5. Hook không đọc arguments, không sửa local variables, không đọc/ghi return operand và **không catch/wrap exception**. Luồng original instructions của nghiệp vụ được giữ nguyên.
6. `ClassWriter.COMPUTE_MAXS` tính lại max operand stack/local requirements phù hợp với việc chèn `LDC` rồi `INVOKESTATIC`. Ví dụ không thêm branches/handlers hay biến đổi control flow nên không cần tự tạo stack-map frames mới. **Không suy mở rộng** điều này cho mọi kiểu instrumentation; các biến đổi phức tạp cần thiết kế frame computation và verifier riêng.
7. Với Java 17, override `transform` **năm tham số** được overload sáu tham số mặc định của interface gọi chuyển tiếp, phù hợp Javadoc.
8. Nếu transform fail, JVM có thể tiếp tục nạp class không đổi (theo hợp đồng transformer). Vì vậy **test instrumented phải assert probe counts**; không được coi có `-javaagent` trong command line là bằng chứng rằng bytecode mới thực sự được áp dụng.

**Vì sao lab chỉ chèn entry?** Đây là mức tối thiểu đủ đo số lần thực thi thân phương thức và kiểm tra preservation cho **normal return lẫn thrown exception**. Nó cố tình tránh triển khai “exit hook” chưa được xử lý đầy đủ để không đánh tráo một ca `ATHROW` explicit với tất cả lỗi có thể thoát ra khỏi method.

### 5.6. `src/main/java/demo/App.java` — differential assertions

```java
package demo;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class App {
    private App() {}

    @FunctionalInterface
    private interface Attempt {
        void run();
    }

    private static Throwable capture(Attempt action) {
        try {
            action.run();
        } catch (Throwable thrown) {
            return thrown;
        }
        throw new AssertionError("Expected an exception");
    }

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError("Invariant failed: " + label);
        }
    }

    public static void main(String[] args) throws Exception {
        BankAccount account = new BankAccount(100);

        int deposited = account.deposit(20);
        int withdrawn = account.withdraw(30);

        Throwable invalid = capture(() -> {
            account.deposit(-1);
        });
        Throwable insufficient = capture(() -> {
            account.withdraw(200);
        });

        RuntimeException marker =
                new IllegalArgumentException("marker");
        Throwable caughtMarker = capture(() -> {
            account.raise(marker);
        });

        int recursive = account.recursive(3);

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Runnable job = () -> {
                for (int i = 0; i < 100; i++) {
                    account.tick();
                }
            };

            Future<?> first = executor.submit(job);
            Future<?> second = executor.submit(job);
            first.get();
            second.get();
        } finally {
            executor.shutdownNow();
        }

        check(deposited == 120, "deposit result");
        check(withdrawn == 90, "withdraw result");
        check(recursive == 6, "recursive result");
        check(account.balance() == 90, "balance");
        check(account.ticks() == 200, "ticks");

        check(invalid.getClass() == IllegalArgumentException.class
                && "amount must be positive".equals(
                        invalid.getMessage()),
                "invalid exception");
        check(insufficient.getClass() == IllegalStateException.class
                && "insufficient funds".equals(
                        insufficient.getMessage()),
                "insufficient exception");
        check(caughtMarker == marker, "Throwable identity");
        check(caughtMarker.getSuppressed().length == 0,
                "no suppressed errors");

        check(account.depositCalls() == 2, "deposit calls");
        check(account.withdrawCalls() == 2, "withdraw calls");
        check(account.raiseCalls() == 1, "raise calls");
        check(account.recursiveCalls() == 4, "recursive calls");

        boolean expectTrace = Boolean.getBoolean("expectTrace");
        int scale = expectTrace ? 1 : 0;
        check(Probe.count("deposit") == 2 * scale,
                "probe deposit");
        check(Probe.count("withdraw") == 2 * scale,
                "probe withdraw");
        check(Probe.count("raise") == scale, "probe raise");
        check(Probe.count("recursive") == 4 * scale,
                "probe recursive");
        check(Probe.count("tick") == 200 * scale,
                "probe tick");

        System.out.println("BUSINESS=deposit:" + deposited
                + ",withdraw:" + withdrawn
                + ",recursive:" + recursive
                + ",balance:" + account.balance());
        System.out.println("EXCEPTIONS="
                + invalid.getClass().getSimpleName() + ":"
                + invalid.getMessage() + "|"
                + insufficient.getClass().getSimpleName() + ":"
                + insufficient.getMessage());
        System.out.println("IDENTITY="
                + (caughtMarker == marker)
                + ",suppressed="
                + caughtMarker.getSuppressed().length);
        System.out.println("STATE=balance:" + account.balance()
                + ",ticks:" + account.ticks());
        System.out.println("CALLS=deposit:"
                + account.depositCalls()
                + ",withdraw:" + account.withdrawCalls()
                + ",raise:" + account.raiseCalls()
                + ",recursive:" + account.recursiveCalls()
                + ",tick:" + account.ticks());
        System.out.println("PROBE=deposit:"
                + Probe.count("deposit")
                + ",withdraw:" + Probe.count("withdraw")
                + ",raise:" + Probe.count("raise")
                + ",recursive:" + Probe.count("recursive")
                + ",tick:" + Probe.count("tick"));
        System.out.println("RESULT=PASS");
    }
}
```

Chương trình **không dùng JUnit**, nhưng mỗi invariant đều được assert bằng `check(...)`. Nếu một giá trị sai, nó ném `AssertionError`, JVM trả exit code khác 0 và **không in `RESULT=PASS`**. Đây là cách làm một thí nghiệm độc lập không cần test dependencies. Trong dự án thật, chuyển assertions vào unit/integration tests có hệ thống.

`Boolean.getBoolean("expectTrace")` đọc Java system property. **Baseline** mặc định `false`, nên probe counts phải bằng 0. **Agent run** dùng `-DexpectTrace=true`, buộc probe counts khớp số business invocations. Nếu transformer không cài hook, test agent run sẽ **fail** thay vì báo sai là đã instrument thành công.

Không làm test **phụ thuộc thứ tự hai threads**: `Future.get()` chờ cả hai hoàn tất, và `tick()` là `synchronized`. Những con số in ra đều xác định, dù scheduler khác nhau.

## 6. Chạy hai phiên bản và đọc stdout

### 6.1. Build một lần

Tại thư mục `transparency-lab`:

```bash
mvn -q -DskipTests package
```

Sau thành công, artifact tiêu chuẩn của cấu hình Maven này là:

```text
target/transparency-lab-1.0.0.jar
```

JAR này chứa cả source ứng dụng và `TraceAgent`, ASM runtime dependencies cùng manifest `Premain-Class: demo.TraceAgent`. Cần Maven 3.x, JDK 17+ và repository có `asm`/`asm-commons` 9.7.1, compiler/shade plugins. Bài không giả định lệnh build đã chạy độc lập trong tài liệu; stdout dưới đây là **kết quả kỳ vọng từ source được trình bày**.

### 6.2. Baseline (không agent)

```bash
java -cp target/transparency-lab-1.0.0.jar demo.App
```

Stdout của ứng dụng:

```text
BUSINESS=deposit:120,withdraw:90,recursive:6,balance:90
EXCEPTIONS=IllegalArgumentException:amount must be positive|IllegalStateException:insufficient funds
IDENTITY=true,suppressed=0
STATE=balance:90,ticks:200
CALLS=deposit:2,withdraw:2,raise:1,recursive:4,tick:200
PROBE=deposit:0,withdraw:0,raise:0,recursive:0,tick:0
RESULT=PASS
```

### 6.3. Instrumented (startup agent)

```bash
java -DexpectTrace=true \
    -javaagent:target/transparency-lab-1.0.0.jar \
    -cp target/transparency-lab-1.0.0.jar demo.App
```

Trên Windows PowerShell, viết thành một dòng:

```powershell
java -DexpectTrace=true -javaagent:target/transparency-lab-1.0.0.jar -cp target/transparency-lab-1.0.0.jar demo.App
```

Stdout ứng dụng dự kiến:

```text
BUSINESS=deposit:120,withdraw:90,recursive:6,balance:90
EXCEPTIONS=IllegalArgumentException:amount must be positive|IllegalStateException:insufficient funds
IDENTITY=true,suppressed=0
STATE=balance:90,ticks:200
CALLS=deposit:2,withdraw:2,raise:1,recursive:4,tick:200
PROBE=deposit:2,withdraw:2,raise:1,recursive:4,tick:200
RESULT=PASS
```

**Đọc kết quả:**

- `BUSINESS` giống nhau: các giá trị trả về đúng.
- `EXCEPTIONS` giống nhau: lỗi invalid amount và insufficient funds không đổi loại/message.
- `IDENTITY=true` ở **cả hai lần chạy**: method `raise` thực sự ném lại **marker object được truyền trong cùng process**; không phải hai JVM dùng cùng object reference.
- `STATE` giống nhau: balance=90, tổng ticks=200.
- `CALLS` giống nhau: không phát sinh **business invocation** thứ hai chỉ do instrumentation.
- `PROBE` có chủ ý **khác**: baseline không có hooks; agent có đúng một `onEntry` cho mỗi invocation, cả invalid/exceptional paths và recursion.
- `RESULT=PASS` chỉ xuất hiện khi tất cả checks chạy xong.

Đây là thí nghiệm đơn giản nhưng giàu tín hiệu hơn việc chỉ thấy log “agent loaded”.

### 6.4. Kiểm chứng bytecode và verifier

Có thể bổ sung xác minh trên JVM mục tiêu:

```bash
java -Xverify:all -DexpectTrace=true \
    -javaagent:target/transparency-lab-1.0.0.jar \
    -cp target/transparency-lab-1.0.0.jar demo.App
```

`-Xverify:all` yêu cầu VM xác minh class bytecode mạnh hơn; nếu transformed class có stack frame/operand stack lỗi, test có thể thất bại sớm. **Verifier pass không bảo đảm semantic equivalence**; vẫn phải chạy assertions ở trên.

Nếu muốn dump **output class-file bytes thật** từ transformer để xem bằng `javap -c -v`, hãy thêm một cơ chế snapshot riêng trong môi trường thử nghiệm. `javap` trực tiếp trên `target/transparency-lab-1.0.0.jar` **chỉ thấy class file trên disk**, không tự thấy những instructions agent đã chèn vào runtime. Không dùng bytecode hash của JAR như bằng chứng instrumentation đã hoặc chưa chạy.

## 7. Vì sao phương pháp differential test này có giá trị?

Ta cố ý tránh viết hai bản business code để so: **chỉ một `BankAccount`** được compile, rồi khởi chạy cùng class bytes bằng hai command lines. Java agent thay class khi load ở run B; vì thế mọi khác biệt nghiệp vụ có thể liên quan đến instrumentation hoặc những biến số môi trường chưa kiểm soát.

Các test kiểm tra **hai phía**:

1. **Business correctness baseline:** nhận đúng giá trị, exceptions và state theo hợp đồng.
2. **Non-regression under instrumentation:** tất cả invariants được lặp lại khi có agent.
3. **Effectiveness of instrumentation:** probe counts chính xác, tránh test “agent không chạy nên không phá ứng dụng” vẫn báo PASS.

Một số đặc tính được thiết kế riêng:

- Có ít nhất hai lỗi được ném **từ trong method**.
- Một lỗi `raise` có **Throwable identity** để bắt việc wrapper tạo ngoại lệ mới.
- Có **recursive call graph**: instrumentation phải chèn một entry cho **mỗi invocation**, không phải một entry cho toàn cây đệ quy.
- Có **multi-threaded synchronized method**: tránh kết luận “đã instrument đúng” chỉ vì kết quả test tuần tự.
- Có **method counters ứng dụng** độc lập với `Probe` counters: nhờ đó phát hiện một công cụ đếm sai hoặc business method bị gọi thêm.

**Điểm cần trung thực:** bài lab dùng inputs nhỏ và state trong memory; chưa chứng minh bảo toàn external DB/HTTP effects hay correctness với mọi exception class, JIT optimization, JVM vendor và tải thực tế. Đó là lý do cần các cấp kiểm thử tiếp theo.

## 8. Bảo toàn return values qua mọi opcode

Một transformer can thiệp ở method exit phải hiểu JVM có nhiều lệnh trả về:

| Return dạng source | Opcode phổ biến | Stack trước khi return |
| --- | --- | --- |
| `void` | `RETURN` | Không có return value |
| `int`, `boolean`, `byte`, `char`, `short` | `IRETURN` | Một category-1 value |
| `float` | `FRETURN` | Một category-1 value |
| `long` | `LRETURN` | Một category-2 value |
| `double` | `DRETURN` | Một category-2 value |
| Object/array reference | `ARETURN` | Một reference |
| Ném ngoại lệ | `ATHROW` | Một reference tới throwable |

Nếu muốn ghi log return value, hook **không được tiêu thụ operand rồi quên đặt lại**. Với ASM, `dup` áp dụng cho category-1; `dup2` phù hợp category-2. Hoặc dùng `AdviceAdapter.newLocal(Type)` và save/load đúng kiểu, kết hợp tính lại stack frames/locals khi cần. Không dùng `DUP` cho `long`/`double`.

Một ý tưởng pseudocode:

```text
Method returns int:
   [ ... original computation ... ]
   push(result)
   DUP                 // giữ một bản cho original IRETURN
   INVOKESTATIC Probe.recordInt(I)V
   IRETURN

Original return value vẫn còn trên operand stack.
```

Đây chỉ là **hình minh họa stack**, không phải phương thức hoàn chỉnh có đủ frames. Probe `recordInt` phải không can thiệp kết quả và chịu trách nhiệm xử lý lỗi telemetry. Nếu nó throw, original return sẽ bị thay thành lỗi. Vì vậy **giữ giá trị trên stack là điều kiện cần nhưng chưa đủ** để bảo toàn semantics.

### 8.1. Đặc biệt với object references và mutable results

Nếu method trả `List<Order>`, việc log bằng `list.toString()` có thể chạy code do ứng dụng tự định nghĩa, thay đổi state hoặc throw. Nếu instrumenter tạo bản sao list, caller có thể không còn cùng reference và các updates tiếp theo không đi vào object gốc.

Các test nên kiểm tra:

- `assertSame(referenceBefore, returnedReference)` khi identity là contract.
- Giá trị và thứ tự elements khi cần.
- Không có mutation hoặc iteration side effects gây `ConcurrentModificationException`.
- `null` vẫn là `null`; hook không “giúp đỡ” thay bằng empty object.
- Đối với `double`, kiểm tra `Double.doubleToRawLongBits(...)` khi phải bảo toàn `-0.0`/NaN payload, hoặc dùng comparator domain-specific nếu API chỉ cam kết tương đương số học.

**Không so `Double.NaN == Double.NaN`** để kết luận hai outputs khác nhau: `NaN != NaN` theo IEEE-754, trong khi ứng dụng có thể coi cả hai là cùng loại kết quả hợp lệ.

## 9. Bảo toàn ngoại lệ, cả lỗi explicit và implicit

### 9.1. “Loại ngoại lệ giống nhau” chưa chắc đủ

Cùng `IllegalArgumentException` nhưng khác `message`, `cause`, `suppressed` hoặc identity có thể làm caller xử lý khác:

```java
// Anti-pattern: thay đổi identity và stack trace của lỗi gốc.
catch (RuntimeException original) {
    throw new RuntimeException(original.getMessage(), original);
}
```

Nếu caller dựa vào `e == marker`, đoạn trên phá contract. Khi chỉ đo lường, **đừng tạo một exception mới để thay kết quả nghiệp vụ**. Kiểm tra `Throwable.getClass()`, `getMessage()`, `getCause()`, `getSuppressed()` và identity khi có ý nghĩa.

### 9.2. Lỗi explicit `ATHROW` khác lỗi implicit từ callee

Với ASM `AdviceAdapter.onMethodExit(int opcode)`, callback được gọi ngay trước **return/throw instructions** mà visitor nhìn thấy, gồm `ATHROW` explicit. Nhưng một method cũng có thể **kết thúc bất thường vì một instruction/callee ném lỗi mà trong bytecode hiện tại không có lệnh `ATHROW` explicit** tại vị trí đó.

Ví dụ:

```java
// Fragment: externalService và Request có trong chương trình thực.
public void send(Request request) {
    externalService.send(request); // callee có thể throw!
}
```

Nếu callee throw, chương trình **không chạy `RETURN` ở cuối method** và không nhất thiết đi qua `ATHROW` explicit của method `send`. Chỉ dùng `onMethodExit(ATHROW)` để đếm “mọi exception exits” là **thiếu**.

Muốn phát terminal event đầy đủ, cần một catch-all handler bao quanh phạm vi method thích hợp, record error, rồi **ném lại chính Throwable**, đồng thời tránh đếm đôi những `ATHROW` đã quan sát:

```text
method body (đúng phạm vi try)
  normal return -> record exactly one normal exit; return original value
  explicit/implicit throw -> catch-all handler:
      record exactly one error exit
      throw the SAME throwable
```

Đây là **pseudocode control flow**, không phải ASM code hoàn chỉnh. Với constructors phải đặc biệt lưu ý trạng thái `uninitialized this` trước `super(...)`/`this(...)`; không tự áp dụng một catch-all không được verifier chấp nhận. Exception tables, handler ordering, stack-map frames và các original try/catch/finally semantics cần được giữ hợp lệ.

### 9.3. Telemetry failure có thể che mất business exception

Ví dụ:

```java
// Anti-pattern: nếu logError throw, caller không thấy original.
try {
    return operation();
} catch (Throwable original) {
    logger.logError(original); // có thể throw
    throw original;
}
```

Một mô hình fail-open có thể thử bắt **lỗi của telemetry** riêng, đảm bảo không biến nó thành replacement của original. Tuy nhiên việc “catch tất cả `Throwable`” cũng có giới hạn: với `ThreadDeath`, `OutOfMemoryError`, `StackOverflowError` hoặc JVM termination, không có đảm bảo an toàn tuyệt đối. Thiết kế telemetry path đủ nhỏ, tránh allocations/locks đắt đỏ, có queue/budget/sampling và policy rõ cho những lỗi nghiêm trọng.

**Phân biệt** business exception và instrumentation exception trong tests; nếu tracer lỗi nhưng business đã trả đúng, telemetry status có thể là degraded chứ không được lặng lẽ tuyên bố đã đo đủ.

## 10. Bảo toàn state sau thực thi

State cần so không chỉ là một `int balance`. Với ứng dụng thật, mở rộng bao gồm:

| State/effect | Cách kiểm chứng | Nguy cơ instrumentation |
| --- | --- | --- |
| Object fields | Snapshot business DTO/state hoặc deep diff hợp lý | Probe đổi object/collection |
| Static caches | Cùng keys/values/version counters | Hook khởi tạo/ghi cache khác |
| ThreadLocal/MDC | Trước-sau trong cùng thread và worker thread pool | Không cleanup trong `finally` |
| Transaction state | Commit/rollback và số lần persistence | Probe gọi lại DAO hoặc làm rollback sai |
| External requests | Stub/mock server đếm HTTP/gRPC calls | Double invocation, retries ngoài policy |
| Messages | In-memory broker/test topic đếm publish | Duplicate send hoặc thay correlation ID |
| Files | So bytes/metadata và số lần ghi có ý nghĩa | Logging nhầm vào đường nghiệp vụ |
| Locks/monitor ownership | Test concurrency, liveness, lock ordering | Hook nắm lock khác gây deadlock |
| Async task graph | Count submitted/completed tasks | Tạo thêm task hoặc mất context |
| Metrics/tracing | Kiểm tra riêng với app business state | Telemetry mất/nhân đôi event |

Chỉ lấy `toString()` hoặc JSON serialization của một object chưa chắc vô tác dụng: custom getters, lazy-loading ORM, serializer hooks và iteration có thể thay đổi state. Dùng test doubles/recorders **độc lập với instrumentation** để thu external effects.

### 10.1. Snapshot business state đúng cách

Với các đối tượng có field mutable, xác định projection chỉ bao gồm **dữ liệu nghiệp vụ** cần bảo toàn:

```text
Before:
   account.id, balance, version, pendingWrites
After:
   account.id, balance, version, pendingWrites

Telemetry:
   span count, timing, log buffer -> kiểm tra riêng
```

Nếu log/tracer thêm một field vào app object chỉ để giữ span id, đó có thể là **schema mutation** không được phép với redefinition/retransformation. Nên dùng scoped context hoặc side table phù hợp, nhưng vẫn phải kiểm soát memory leaks và class loader lifetimes.

### 10.2. Đặc biệt với transaction và retries

Một cơ chế retry nghiệp vụ **được thiết kế sẵn** có thể hợp lệ, nhưng instrumentation **không được tự thêm retry** chỉ để “lấy lại kết quả” hoặc khi thấy telemetry failure. Khi test, phân biệt:

- **Request attempts** ở client.
- **Invocation count** của method được instrument.
- **DB transaction count**.
- **Committed side effects**.

Một request có thể gọi business method hai lần do retry policy hợp lệ; không được tự áp đặt “mỗi request đúng một invocation” nếu hợp đồng vốn cho phép retries. Kiểm thử nên dùng expected count theo kịch bản, không theo suy đoán.

## 11. Số lần gọi: recursion, concurrency, overload và dispatch

### 11.1. Đệ quy

Với `recursive(3)`:

```text
recursive(3)
  recursive(2)
    recursive(1)
      recursive(0)
```

Đây là **bốn method invocations**, không phải một. Nếu business counter là 4 mà probe báo 1 thì hook có thể chỉ bọc outermost call. Nếu probe báo 8 thì transformer có thể chèn hook hai lần hoặc có một layer wrapper khác cùng đo. Cần xác định metric đang đếm **method entry**, **root request** hay **logical transaction** trước khi báo bug.

### 11.2. Đa luồng

Hai threads cùng gọi `tick` không có thứ tự tuyến tính cố định theo JVM scheduler. Điều phải bảo toàn là:

```text
100 calls của Thread A + 100 calls của Thread B
= 200 business method entries
= 200 probe entries khi agent bật
= 200 state increments trong bài lab synchronized
```

Đừng viết test so thứ tự log `A, B, A, B...` trừ khi đã dùng synchronization buộc thứ tự. Dùng `CountDownLatch`/`Future.get` để chờ hoàn tất rồi so **số lượng/invariants**, và cho test có timeout trong CI để phát hiện deadlock.

### 11.3. Overloads, bridge và synthetic methods

Phương thức có cùng name nhưng khác descriptor là **method khác**:

```text
save(I)V
save(Ljava/lang/String;)V
```

Nếu tracker chỉ dựa vào `methodName`, nó có thể trộn counts của hai overloads. Với generic overrides, compiler có thể sinh **bridge methods**; một lời gọi source có thể đi qua bridge rồi method implementation, vì thế **hai bytecode method entries** có thể tương ứng **một logical operation**.

Quy tắc:

- Định danh bytecode method bằng **owner internal class + name + descriptor**, thêm defining loader identity khi cần.
- Xác định policy có instrument `ACC_BRIDGE`/`ACC_SYNTHETIC` không.
- Đếm **logical business operations** theo service boundary phù hợp, không máy móc cộng mọi bytecode helper call.
- Có tests overloads/default methods/inheritance và dynamic dispatch.

### 11.4. Reentrant logging và chính hook tự bị instrument

Nếu `Probe.onEntry` cũng bị chọn bởi transformer, có thể xảy ra:

```text
BankAccount.deposit
  -> Probe.onEntry
      -> Probe.onEntry
          -> Probe.onEntry
             ... StackOverflowError
```

Một transformer đúng cần tránh instrument chính helper packages, logging framework hot paths, bootstrap classes không cần thiết hoặc phải có **reentrancy guard** dựa trên `ThreadLocal` được cleanup đúng. Bài lab filter duy nhất `demo/BankAccount` nên không gặp chuỗi này.

## 12. Bảo toàn try/finally và context đa luồng

Một tracing context thường có thao tác `push`/`pop` span:

```java
// Fragment mô hình; SpanScope không thuộc JDK chuẩn.
SpanScope scope = traceContext.openScope();
try {
    return businessWork();
} finally {
    scope.close();
}
```

Code này có thể cần thiết nhưng chưa đủ: nếu `openScope` hoặc `close` ném lỗi, outcome nghiệp vụ có thể thay đổi. Khi dùng `ThreadLocal`, phải cleanup trong cả normal và exceptional paths, không để span của request trước chảy sang request sau trên thread pool.

Trong `CompletableFuture`, Reactor, virtual threads hoặc callback frameworks, một logical operation có thể chạy qua **nhiều execution contexts**. “Một Java method entry” khác “một request span”. Tracing phải truyền context có kiểm soát qua scheduling boundary; không chỉ giả định `ThreadLocal` tồn tại khi callback chạy ở thread khác.

Một test tốt cho thread pool:

```text
Task A: đặt correlation id = X, gọi business, cleanup
Task B: không đặt correlation id
Expected: Task B KHÔNG nhìn thấy X
```

Điều này là **test plan**, không phải stdout của lab chính. Sử dụng `try/finally` cleanup và assert trong cùng executor thread khi test để bắt leaks.

## 13. Kiểm thử async: exception không nhất thiết ném ngay tại caller

Synchronous method:

```java
Result result = service.call(); // value hoặc throw ngay tại call site
```

Asynchronous method:

```java
CompletableFuture<Result> future = service.callAsync();
```

Method `callAsync()` có thể **trả future bình thường**, sau đó future hoàn thành exceptionally. Nếu agent đổi `CompletionStage`/`Future` object, gọi `join()` thay caller, thêm callback mutate state hoặc wrap exception sai, caller có thể thấy outcome khác.

Ma trận kiểm thử async:

- Future/Publisher reference identity có cần giữ không?
- Completion value có tương đương không?
- Exceptional completion chứa **cause gốc** nào, có bị wrap thêm ngoài contract không?
- Cancellation, timeout, interrupts có được giữ nguyên không?
- Callback có chạy một lần, đúng executor/context, và có bị gọi thêm?
- Số lần business method **tạo future** và số lần **completion callback** cần đếm **riêng**.

Không so sánh máy móc `CompletionException` với exception ném đồng bộ: `join()` thường wrap exceptional completion trong `CompletionException` theo API. Chọn assert theo **tầng caller thực sự sử dụng**.

## 14. Quy trình kiểm thử thực tế theo nhiều tầng

### Tầng 1 — Hợp đồng một method

Với mỗi target:

- Normal return, null, empty, boundary, large values.
- Lỗi expected theo business rules.
- `Error` và unchecked exception nếu liên quan.
- Reference identity/aliasing theo hợp đồng.
- State mutations và application call count.
- Với return primitive đặc biệt: NaN/negative zero/long/double categories.

### Tầng 2 — Bytecode correctness

Sau transform:

- Class file parse được.
- Class/method descriptors không vô tình thay.
- `StackMapTable`, max stack/max locals, exception tables hợp lệ.
- Branch offsets/control flow và handlers đúng.
- Constructors/`<clinit>`, synchronized methods, native/abstract methods không bị instrument sai.
- Output version tương thích JVM đích.
- `-Xverify:all` và tests trên VM thực tế.

### Tầng 3 — Differential runs

Chạy baseline và agent **trong hai JVM riêng** với:

- Cùng JDK/vendor/version.
- Cùng classpath/module-path và app artifact.
- Cùng input fixtures và timezone/locale khi có ảnh hưởng.
- Fake clock/random/HTTP/database trong kịch bản determinism.
- Cùng concurrency workload nhưng so invariants, không so thứ tự scheduler tùy ý.
- Exit status, stdout business projection, test fixtures/external effects.

### Tầng 4 — Agent pipeline

Kiểm tra một agent và nhiều agents:

- Agent thêm trước/sau transformer khác.
- Mỗi transformer chỉ xử lý đúng targets.
- Load time, retransform, redefine nếu được yêu cầu.
- Không chèn hooks kép sau retransform lặp.
- Class loader khác nhau, module access, bootstrap visibility.
- Hooks không gây recursive class loading và không giữ `Class<?>`/loader vô hạn.

### Tầng 5 — Regression/soak tests

Với traffic thực tế/giả lập:

- So throughput, p95/p99 latency và GC overhead.
- Tìm deadlocks, hung threads, thread pool saturation.
- Xác minh telemetry backpressure không làm business fail.
- Kiểm tra memory leaks, queue growth, dropped telemetry và error sampling.
- Chạy nhiều phút/giờ với tải/đầu vào đa dạng.
- Có rollback/tắt agent nếu instrumentation gây sai outcome.

Không gộp tất cả vào một bài unit test; các loại bug xuất hiện ở những tầng khác nhau.

## 15. Chẩn đoán khi baseline và agent khác nhau

| Dấu hiệu | Khả năng | Hướng xử lý |
| --- | --- | --- |
| Return value khác | Sai xử lý operand `IRETURN`/`ARETURN`/`LRETURN`, helper mutate return | Kiểm tra stack/local saves, identity và code paths |
| Business counter gấp đôi | Wrapper thực thi target hai lần, retry do instrumentation | Tách request retry hợp lệ khỏi hook-induced invocation |
| Probe counter gấp đôi nhưng business không đổi | Chèn hook hai lần, đo cả bridge/wrapper hoặc hai agents | Dump transformed bytes, xác định method descriptors và transformer ordering |
| Probe = 0 khi agent run | Transformer không chạy/không match target hoặc fail silently | Assert hiệu lực, kiểm tra manifest, loader, class name |
| Exception type/message đổi | Catch/wrap hoặc logging callback throw | Bảo toàn Throwable gốc; tách telemetry errors |
| `Throwable` identity khác | Agent tạo new exception | Rethrow same throwable, không wrap khi contract cần identity |
| Có thêm suppressed errors | `try-with-resources`/scope close hoặc helper thêm suppressed | Kiểm tra lifecycle telemetry và exception policy |
| Lost exception events | Chỉ dùng `onMethodExit(ATHROW)` | Thêm catch-all đúng phạm vi, không double counting |
| State khác | Helper chạm fields, gọi lại getter có side effect, async task trùng | Mock external effects, assert snapshots |
| `VerifyError` | Stack map frames/handler offsets/sai operand stack | ASM checks/`-Xverify:all`/load JVM đích |
| `ClassFormatError` | Output classfile sai | Kiểm tra reader/writer, không sửa input tại chỗ |
| `NoClassDefFoundError: demo/Probe` | Helper không visible cho defining loader của target | Đảm bảo class-loader/module strategy, không chỉ thử system loader |
| Deadlock khi agent bật | Probe giữ locks/log sync/reentrant class loading | Giới hạn callback, loại trừ logger/agent classes |
| Đếm thiếu dưới concurrency | Counter thường, race hoặc sampling | AtomicLong/LongAdder, synchronization; phân biệt sampled metrics |
| Context còn ở request sau | `ThreadLocal` không cleanup | `try/finally`, kiểm tra reuse executor thread |
| Async completion khác | Agent intercept future và thay cancellation/cause | So returned stage semantics và exceptional completion |
| Chạy JUnit pass nhưng production fail | Test thiếu third-party agents, modules, classloader, JDK matrix | Integration tests cùng startup path |
| Stack trace khác dù lỗi giống | Code offsets/frames thay do instrumentation | Định nghĩa stack trace fidelity theo hợp đồng, không nhầm với exception outcome |
| Agent overhead cao | Quá nhiều probes/logging/string formatting | Sampling, aggregation, instrumentation scope |
| Kết quả khác do input nondeterministic | Time/random/network/scheduling/DB state khác giữa runs | Dùng fixtures và so invariants đúng loại |

## 16. Checklist QA cuối bài

- [ ] Đã định nghĩa **business observation** và tách telemetry state khỏi nghiệp vụ.
- [ ] Mỗi target có test giá trị trả về, void path, expected errors, state và application invocation count.
- [ ] Không gọi lại method chỉ để ghi log, lấy result hoặc đo duration.
- [ ] Giữ cùng returned reference nếu API yêu cầu identity.
- [ ] Không thay kiểu/message/cause/suppressed/identity của throwable trái contract.
- [ ] Không để telemetry failure trong `finally` che mất return/exception gốc.
- [ ] Đo invocation count theo name+descriptor/loader, không chỉ theo source method name.
- [ ] Test recursion, overloads/bridge/synthetic, synchronized và concurrent calls.
- [ ] Test implicit exception exits, không nhầm `ATHROW` explicit với mọi exceptional paths.
- [ ] Trả `null` khi transformer không thay class; nếu có transform, trả bytes mới, không mutate input `classfileBuffer`.
- [ ] Verify class output; tính đúng stack/frames/handlers/constructor rules.
- [ ] Dùng hai JVM riêng và cùng business fixtures để chạy baseline vs instrumented.
- [ ] Kiểm tra agent thực sự kích hoạt hook, không pass giả khi transformer silently fails.
- [ ] Test classloader/module/helper visibility, không instrument recursive logging helpers.
- [ ] Test context cleanup trên pool threads và async exceptional completions.
- [ ] Phân biệt sampled/dropped telemetry với count application method thật.
- [ ] Kiểm tra external effects, DB writes/messages/HTTP calls bằng test doubles hoặc sandbox.
- [ ] Với retransform/redefine, đảm bảo idempotency và không chèn duplicate hooks.
- [ ] Có performance/soak tests, backpressure policy và khả năng rollback agent.

## 17. Câu hỏi tự kiểm tra

1. **Instrumentation ghi log kết quả bằng cách gọi `service.doWork()` hai lần. Có bảo toàn app call count?**  
   Không. Log đã khiến business method chạy thêm một lần và có thể gây thêm side effects.

2. **Probe ghi hai events (START và END) cho một method invocation. Có nghĩa business method chạy hai lần?**  
   Không. Event count và application invocation count là hai đại lượng khác nhau.

3. **Vì sao baseline và agent chạy ở hai JVM riêng thay vì nối tiếp trong cùng process?**  
   Tránh static state, class loading, agent redefinition/JIT và counters của run đầu gây nhiễu run sau.

4. **Agent run có tất cả business outputs đúng nhưng Probe đếm 0. Test instrumentation đạt chưa?**  
   Chưa. Có thể transformer không chạy, trong khi business code nguyên bản vẫn hoạt động; cần assert hook effectiveness.

5. **`deposit(-1)` ném lỗi nhưng business invocation count có tăng không?**  
   Có trong ví dụ vì method body đã bắt đầu và tăng counter trước validation; nó vẫn là một invocation.

6. **`recursive(3)` có mấy invocation của `recursive`?**  
   Bốn: n=3,2,1,0. Probe entry-only đúng phải thấy bốn lần.

7. **Hai threads mỗi thread tăng 100 lần mà probe báo 190, business state 200. Lỗi có thể ở đâu?**  
   Có thể probe dùng counter không atomic, sampling/dropped events hoặc telemetry race; cần điều tra độc lập với business state.

8. **`catch (RuntimeException e) { throw new IllegalStateException(e); }` có giữ Throwable identity không?**  
   Không. Nó tạo object khác và đổi loại exception.

9. **Vì sao `finally { logger.close(); }` có thể đổi outcome của app?**  
   Nếu `close()` throw, nó có thể che return/exception gốc.

10. **`onMethodExit(ATHROW)` có thấy mọi lỗi do callee ném mà không được catch không?**  
    Không. Lỗi có thể thoát qua control flow mà method hiện tại không thực thi `ATHROW` explicit.

11. **Tại sao `DUP` không đủ cho return `long`/`double`?**  
    Đây là category-2 values cần xử lý two-slot đúng (`DUP2` hoặc local var phù hợp).

12. **Nếu một method trả reference mới trong bản instrumented với nội dung bằng object gốc, có luôn tương đương?**  
    Không nếu caller quan tâm object identity, aliasing hoặc mutation.

13. **`Arrays.equals(before, after)` trên class file bytes có chứng minh business equivalence không?**  
    Không. Bytecode khác bytes có thể cùng behavior, nhưng cũng có thể phá semantics; cần kiểm thử phù hợp.

14. **Vì sao số Java method entries của chương trình có agent chắc chắn cao hơn baseline?**  
    Vì hook gọi thêm helper methods. Điều cần giữ là **application business method invocation count**, không phải tổng mọi helper calls.

15. **Agent bắt mọi throwable rồi ghi log; có nên nuốt `OutOfMemoryError` để “không phá app” không?**  
    Không có giải pháp đảm bảo an toàn tuyệt đối ở lỗi tài nguyên nghiêm trọng. Thiết kế telemetry nhẹ và có chính sách rõ về fail-open/degraded operation.

16. **Làm sao kiểm tra không duplicate hooks khi retransform?**  
    Chụp đúng input/output, nhận diện hook theo symbolic instructions, retransform nhiều lần, so probe count với business count.

17. **Một async method trả `CompletableFuture` thành công rồi future thất bại sau đó. Nên ghi terminal outcome lúc nào?**  
    Theo contract của operation: thường phải theo dõi future completion riêng, không nhầm synchronous return với async success.

18. **Verifier pass có đủ để khẳng định instrumentation bảo toàn state/exception?**  
    Không. Verifier kiểm tra bytecode hợp lệ; không chứng minh business equivalence.

19. **Vì sao không luôn so toàn bộ stack trace từng ký tự?**  
    Instrumentation có thể đổi line/offset/frame layout; cần xác định liệu stack-trace fidelity là yêu cầu thực sự hay chỉ outcome exception type/message/cause.

20. **Điều kiện nào mới đủ để tuyên bố test lab PASS?**  
    Business results, exception contract, state/call counts và hiệu lực của probes đều pass theo mode đã chạy. Không được báo PASS nếu thiếu agent hook hoặc sai business invariants.

## 18. Tài liệu chính thức và công cụ

1. Oracle JDK 17 — **`java.lang.instrument.ClassFileTransformer`**: callback, transformer chaining, `classfileBuffer` immutable, `return null` hoặc bytes mới: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
2. Oracle JDK 17 — **`java.lang.instrument` package**: `-javaagent`, `Premain-Class`/`premain`, agent startup và module visibility: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
3. Oracle JDK 17 — **`Instrumentation`**: retransform/redefine, modifiability và thứ tự transformers: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
4. ASM — **`AdviceAdapter`**: `onMethodEnter` và `onMethodExit`; explicit return/`ATHROW`, constructor semantics: https://asm.ow2.io/javadoc/org/objectweb/asm/commons/AdviceAdapter.html
5. ASM — official documentation và release history: https://asm.ow2.io/
6. Maven Central — **`asm-commons 9.7.1`**: https://central.sonatype.com/artifact/org.ow2.asm/asm-commons/9.7.1
7. Oracle JDK 17 — **`Throwable`**: cause, suppressed exceptions và stack traces: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html
8. Oracle JDK 17 — **`AtomicInteger`**: thread-safe counters: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
9. Oracle JDK 17 — **`Future.get`**, memory-consistency/cancellation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
10. JVM Specification 17 — **Chapter 6**, return opcodes, `athrow` và method invocation instructions: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html

**Kết luận:** Instrumentation đúng không chỉ “ghi được telemetry”: nó phải **giữ nguyên giá trị và identity khi hợp đồng yêu cầu, không thay loại/đối tượng ngoại lệ, không thêm state mutation nghiệp vụ, không gọi lại methods ngoài logic vốn có**. Hãy chạy cùng kịch bản baseline và agent trong **hai JVM độc lập**, kiểm tra cả business assertions và hiệu lực probe, rồi mở rộng sang concurrency, async, multiple agents, bytecode verifier và production-like tests.
