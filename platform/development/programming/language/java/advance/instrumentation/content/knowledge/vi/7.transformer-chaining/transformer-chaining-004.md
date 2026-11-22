# Thứ tự đăng ký bên trong từng nhóm `ClassFileTransformer`

Một Java agent có thể đăng ký nhiều `ClassFileTransformer`. Khi JVM xử lý một lớp, các transformer hợp lệ được chạy theo **chuỗi**: mỗi bước nhận `classfileBuffer` do bước trước để lại. Vì vậy thứ tự không chỉ quyết định thứ tự log, mà còn có thể quyết định bytecode cuối cùng.

Tuy nhiên quy tắc thực tế **không** phải “transformer nào được gọi `addTransformer` trước thì luôn chạy trước tất cả transformer khác”. Java instrumentation chia transformer thành các **nhóm có thứ tự ưu tiên cố định**. **Bên trong mỗi nhóm, thứ tự chính là thứ tự đăng ký**. Bài học thuộc phần **Chuỗi biến đổi**, tập trung vào ý nghĩa của cụm “bên trong từng nhóm”, cách kiểm chứng trên Java 17+, và những bẫy khi nhóm bị xen kẽ trong lúc đăng ký.

## 1. Hai tầng thứ tự: nhóm trước, thời điểm đăng ký sau

Theo hợp đồng `java.lang.instrument.ClassFileTransformer`, khi một lớp được nạp mới hoặc redefine, các bước biến đổi được áp dụng theo thứ tự:

| Thứ tự nhóm | Nhóm | Nguồn đăng ký |
|---|---|---|
| 1 | Transformer **không hỗ trợ retransform** viết bằng Java | `Instrumentation.addTransformer(t)` hoặc `addTransformer(t, false)` |
| 2 | Transformer **không hỗ trợ retransform** ở tầng native | JVMTI `ClassFileLoadHook` |
| 3 | Transformer **có hỗ trợ retransform** viết bằng Java | `Instrumentation.addTransformer(t, true)` |
| 4 | Transformer **có hỗ trợ retransform** ở tầng native | JVMTI `ClassFileLoadHook` với capability phù hợp |

Các nhóm này tạo thành thứ tự **cố định** trong pipeline. Ngay cả khi bạn đăng ký một transformer Java thuộc nhóm 3 trước một transformer Java thuộc nhóm 1, thì **nhóm 1 vẫn chạy trước nhóm 3** khi JVM định nghĩa một lớp mới.

Sau khi JVM chọn nhóm, nó xử lý các transformer **theo thứ tự chúng được đăng ký trong chính nhóm đó**:

```text
Nhóm 1 (Java, không retransform): N1 -> N2 -> N3
                                |
Nhóm 2 (native, không retransform): ... (nếu có)
                                |
Nhóm 3 (Java, có retransform): R1 -> R2 -> R3
                                |
Nhóm 4 (native, có retransform): ... (nếu có)
                                |
                                v
                  Class file được JVM kiểm tra và áp dụng
```

Trong hai nhóm Java, `N` và `R` là ký hiệu minh họa:

- `N`: *retransformation incapable*, đăng ký với `false`.
- `R`: *retransformation capable*, đăng ký với `true`.
- Con số phía sau (`N1`, `N2`, `R1`, `R2`) biểu diễn **thứ tự tương đối trong nhóm**, không phải thứ tự gọi `addTransformer` trên toàn hệ thống.

Đừng nhầm **retransformation capable** với “đã thực hiện retransform”. Đây là đặc tính của **lần đăng ký transformer**, cho biết callback có được chạy lại khi `retransformClasses` xảy ra hay không. Cả hai nhóm Java vẫn có thể được gọi khi lớp được nạp mới hoặc redefine.

## 2. Một ví dụ đăng ký xen kẽ nhưng thực thi theo nhóm

Giả sử agent đăng ký bốn transformer theo thứ tự thời gian:

```java
inst.addTransformer(r1, true);   // Lần đăng ký 1: nhóm R
inst.addTransformer(n1, false);  // Lần đăng ký 2: nhóm N
inst.addTransformer(r2, true);   // Lần đăng ký 3: nhóm R
inst.addTransformer(n2, false);  // Lần đăng ký 4: nhóm N
```

Đây là **đoạn minh họa trong `premain`**, ở đó `inst` là `Instrumentation`, còn `r1`, `n1`, `r2`, `n2` là các instance implement `ClassFileTransformer`. Chưa phải chương trình Java độc lập.

Lịch sử đăng ký toàn cục:

```text
R1 -> N1 -> R2 -> N2
```

Thứ tự callback khi JVM load mới một lớp:

```text
N1 -> N2 -> R1 -> R2
```

**Vì sao?** JVM gom các bước theo nhóm trước. Trong nhóm không hỗ trợ retransform, `N1` được đăng ký trước `N2` nên `N1` chạy trước `N2`. Trong nhóm có hỗ trợ retransform, `R1` được đăng ký trước `R2` nên `R1` chạy trước `R2`. Nhóm N hoàn tất trước nhóm R, bất kể các lệnh đăng ký của hai nhóm bị xen kẽ như thế nào.

| Lần đăng ký | Transformer | Thuộc nhóm | Vị trí khi nạp mới (không có native transformer) |
|---|---|---|---|
| 1 | `R1` | R (có retransform) | 3 |
| 2 | `N1` | N (không retransform) | 1 |
| 3 | `R2` | R (có retransform) | 4 |
| 4 | `N2` | N (không retransform) | 2 |

Đây là bảng **hai nhóm Java**, dùng để chứng minh thứ tự trong mỗi nhóm; không hàm ý native transformers không tồn tại trong ứng dụng thực tế. Khi có JVMTI native transformers, hai nhóm native được xen vào đúng vị trí 2 và 4 như mục 1.

### Thay đổi đăng ký trong cùng một nhóm có ảnh hưởng gì?

Giữ thứ tự nhóm cố định nhưng đổi vị trí đăng ký của `N1` và `N2`:

```java
inst.addTransformer(r1, true);
inst.addTransformer(n2, false);
inst.addTransformer(r2, true);
inst.addTransformer(n1, false);
```

Khi load mới, thứ tự trở thành:

```text
N2 -> N1 -> R1 -> R2
```

Tương tự, nếu đăng ký `R2` trước `R1`, thì trong nhóm R sẽ thành `R2 -> R1`. Đó là nội dung cốt lõi của **“thứ tự đăng ký bên trong từng nhóm”**: sắp xếp nhóm không xóa bỏ tính tuần tự của các lần đăng ký **trong cùng nhóm**.

### Đổi cách xen kẽ khác nhóm không nhất thiết đổi pipeline

Hai lịch sử:

```text
A: add(R1,true), add(N1,false), add(R2,true), add(N2,false)
B: add(N1,false), add(N2,false), add(R1,true), add(R2,true)
```

đều dẫn tới cùng thứ tự trong pipeline Java:

```text
N1 -> N2 -> R1 -> R2
```

vì thứ tự **tương đối trong N** và **tương đối trong R** đều giống nhau.

## 3. Vì sao thứ tự trong nhóm quan trọng đối với bytecode?

`ClassFileTransformer.transform(...)` nhận một `byte[]` class file. Transformer có thể:

- Trả `null`: không thay đổi bytes ở bước này.
- Trả `byte[]` mới hợp lệ: JVM dùng bytes mới như đầu vào cho bước tiếp theo.

Mô hình khái niệm (không phải code Java thực thi):

```text
B0 = class file gốc
B1 = N1(B0)                  // Hoặc giữ B0 nếu N1 trả null
B2 = N2(B1)                  // Hoặc giữ B1 nếu N2 trả null
B3 = native_incapable(B2)    // Nếu có
B4 = R1(B3)
B5 = R2(B4)
B6 = native_capable(B5)      // Nếu có
JVM kiểm tra và định nghĩa từ bytes cuối cùng
```

Biến đổi **thường không giao hoán**: `N2(N1(B0))` không nhất thiết cho cùng kết quả với `N1(N2(B0))`.

Ví dụ về một ý tưởng thực tế:

- Transformer `A` chèn một lời gọi logging ở đầu method.
- Transformer `B` tìm instruction đầu tiên rồi chèn một đoạn kiểm tra ngay trước instruction đó.
- Nếu `B` chạy trước, nó xem instruction đầu tiên **trong bản gốc**.
- Nếu `A` chạy trước, `B` có thể xem instruction logging mới là instruction đầu tiên.

Vì vậy thứ tự đăng ký trong cùng nhóm có thể làm thay đổi **vị trí instrumentation**, kết quả runtime và xung đột giữa các thư viện. Để minh họa logic này một cách an toàn, có thể dùng ví dụ giả lập trên chuỗi:

```text
A: thêm tiền tố "log:"
B: biến tiền tố hiện có thành chữ in hoa

B(A("work")) = "LOG:work"
A(B("work")) = "log:work"
```

Đây chỉ là **mô hình cho phép toán tuần tự**, không phải thao tác hợp lệ trên class file bytes. Với bytecode thật, phải dùng công cụ hiểu định dạng class file, như ASM hoặc Byte Buddy, và trả mảng bytes mới hợp lệ. Không tự sửa tùy tiện các ký tự trong `.class`.

### `return null` có làm đứt chuỗi không?

Không. Nếu `N1` trả `null`, JVM vẫn tiếp tục gọi `N2` với bytes chưa bị thay bởi `N1`. `null` nghĩa là **không có biến đổi tại bước này**, không có nghĩa “dừng cả pipeline”.

Nếu một callback ném exception chưa bắt, Javadoc cũng quy định các transformer tiếp theo vẫn có thể được gọi và JVM tiếp tục nỗ lực định nghĩa/cập nhật lớp. Do đó không dùng `return null` hoặc `throw` như cơ chế để chặn các transformer khác.

## 4. Ví dụ Java 17+ có thể chạy: chứng minh thứ tự thực tế

Ví dụ tạo một **startup Java agent** và một ứng dụng nhỏ. Agent đăng ký `R1`, `N1`, `R2`, `N2` đúng thứ tự xen kẽ ở mục 2, rồi kích hoạt quá trình load một lớp tên `demo.Probe`.

Sau đó agent chủ động yêu cầu `retransformClasses` để chứng minh thêm:

- Khi **load mới**, cả N và R đều nhận callback, theo thứ tự `N1, N2, R1, R2`.
- Khi **retransform**, N **không được gọi lại**; JVM tự tái áp dụng kết quả trước đó của nhóm N, rồi gọi `R1, R2` trong thứ tự đăng ký của nhóm R.

Ta chỉ log và `return null`; vì thế ví dụ kiểm tra **thứ tự callback** mà không cần dependency ASM hoặc phải sửa bytecode.

### 4.1. Cấu trúc thư mục

```text
order-demo/
├── src/demo/
│   ├── OrderAgent.java
│   ├── Probe.java
│   └── App.java
└── agent.mf
```

### 4.2. Lớp đích `src/demo/Probe.java`

```java
package demo;

public final class Probe {
    public String value() {
        return "base";
    }
}
```

`Probe` đơn giản vì nhiệm vụ chính là nhìn thấy thứ tự đi qua các transformer. Không có `static` initializer để gây ra log phụ không liên quan.

### 4.3. Ứng dụng `src/demo/App.java`

```java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("[app] value=" + new Probe().value());
    }
}
```

Khi không sử dụng agent, ứng dụng in:

```text
[app] value=base
```

### 4.4. Agent và transformer `src/demo/OrderAgent.java`

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class OrderAgent {
    private OrderAgent() {
    }

    public static void premain(String agentArgs, Instrumentation inst)
            throws Exception {

        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException(
                    "This demo requires retransformation support");
        }

        // Cố tình đăng ký xen kẽ hai nhóm.
        inst.addTransformer(new TraceTransformer("R1"), true);
        inst.addTransformer(new TraceTransformer("N1"), false);
        inst.addTransformer(new TraceTransformer("R2"), true);
        inst.addTransformer(new TraceTransformer("N2"), false);

        System.out.println("[agent] registered R1,N1,R2,N2");

        // Class.forName dùng tên chuỗi, tránh tham chiếu trực tiếp
        // tới Probe.class trước khi transformer được đăng ký.
        Class<?> probe = Class.forName(
                "demo.Probe",
                false,
                ClassLoader.getSystemClassLoader());

        System.out.println("[agent] load completed");

        if (!inst.isModifiableClass(probe)) {
            throw new IllegalStateException(
                    "demo.Probe cannot be retransformed");
        }

        System.out.println("[agent] retransform requested");
        inst.retransformClasses(probe);
        System.out.println("[agent] retransform completed");
    }
}

// Class phụ không public vẫn có thể đặt chung file nguồn.
final class TraceTransformer implements ClassFileTransformer {
    private final String label;

    TraceTransformer(String label) {
        this.label = label;
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if ("demo/Probe".equals(className)) {
            String phase = classBeingRedefined == null
                    ? "load"
                    : "retransform";
            System.out.println("[" + label + "] " + phase);
        }

        // Không sửa bytes: ta đang quan sát thứ tự gọi callback.
        return null;
    }
}
```

**Giải thích code theo hợp đồng:**

1. `premain` chạy trước `App.main`, nên có thể đăng ký transformer trước khi `demo.Probe` được load.
2. `isRetransformClassesSupported()` là kiểm tra khả năng runtime. Điều kiện này yêu cầu cả JVM và manifest phù hợp, không phụ thuộc chỉ vào việc code có gọi `true`.
3. Bốn `TraceTransformer` khác instance, mỗi instance mang một `label`, được đăng ký theo lịch sử `R1, N1, R2, N2`.
4. `Class.forName("demo.Probe", false, ...)` yêu cầu nạp lớp sau khi đã đăng ký; `false` tránh yêu cầu khởi tạo class nếu không cần. Trong ví dụ này, class loader của ứng dụng có thể tìm `demo.Probe` từ classpath `out`.
5. Callback lọc chính xác tên nội bộ `"demo/Probe"`, tránh in log cho nhiều lớp JDK khác được nạp trong quá trình startup.
6. `classBeingRedefined == null` biểu thị nạp mới; trong ví dụ này, giá trị khác null xuất hiện ở lần **retransform** mà agent chủ động yêu cầu. Ở hệ thống tổng quát, non-null cũng có thể là redefine, nên không được dùng điều kiện đó để phân biệt hai cơ chế nếu không biết ngữ cảnh.
7. Tất cả transformer `return null`, vì vậy `Probe.value()` vẫn trả `"base"`.
8. `premain` chỉ kết thúc sau khi load và retransform hoàn tất; lúc đó JVM mới chạy `App.main`.

Đoạn này cố ý **không viết transformer native**. Với Java `Instrumentation.addTransformer`, ta quan sát trực tiếp **hai nhóm Java**; hai nhóm JVMTI native có cùng quy tắc thứ tự theo tài liệu nhưng sử dụng API/native tooling khác.

### 4.5. Manifest `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.OrderAgent
Can-Retransform-Classes: true

```

- `Premain-Class` chọn `demo.OrderAgent`.
- `Can-Retransform-Classes: true` khai báo nhu cầu dùng retransform; nếu thiếu hoặc đặt `false`, `isRetransformClassesSupported()` có thể trả `false` và `addTransformer(t, true)` sẽ bị từ chối.
- Ví dụ dùng startup agent để không cần thiết lập dynamic attach; mục đích là chứng minh thứ tự transformer.

Đặt một dòng trống ở cuối manifest như ví dụ để kết thúc main section.

### 4.6. Biên dịch và đóng JAR

Mở terminal trong thư mục `order-demo`, với **JDK 17+**:

```bash
mkdir out

javac --release 17 -encoding UTF-8 -d out src/demo/OrderAgent.java src/demo/Probe.java src/demo/App.java

jar --create --file order-agent.jar --manifest agent.mf -C out demo/OrderAgent.class -C out demo/TraceTransformer.class
```

Các lệnh có thể chạy trong Bash, PowerShell hoặc cmd; `mkdir out` chỉ cần một lần ở thư mục mới.

Lệnh `javac` tạo hai file class từ source `OrderAgent.java`: `demo/OrderAgent.class` và `demo/TraceTransformer.class`. Cả hai phải nằm trong agent JAR, nếu không có thể gặp lỗi thiếu class khi `premain` tạo transformer. `Probe.class` và `App.class` nằm trên classpath `out` của ứng dụng, không cần đóng vào agent JAR.

Kiểm tra archive:

```bash
jar --list --file order-agent.jar
```

Bạn phải nhìn thấy `META-INF/MANIFEST.MF`, `demo/OrderAgent.class` và `demo/TraceTransformer.class`.

### 4.7. Chạy và đọc stdout

Không có agent:

```bash
java -cp out demo.App
```

Stdout:

```text
[app] value=base
```

Có agent:

```bash
java -javaagent:order-agent.jar -cp out demo.App
```

**Stdout dự kiến khi JVM hỗ trợ retransform, không có transformer native khác can thiệp và việc nạp/cập nhật thành công:**

```text
[agent] registered R1,N1,R2,N2
[N1] load
[N2] load
[R1] load
[R2] load
[agent] load completed
[agent] retransform requested
[R1] retransform
[R2] retransform
[agent] retransform completed
[app] value=base
```

Đọc các dòng theo từng giai đoạn:

- **Dòng đăng ký:** `R1,N1,R2,N2` phản ánh đúng thứ tự gọi `addTransformer`.
- **Bốn dòng `load`:** `N1,N2,R1,R2` là thứ tự thực tế JVM áp dụng, cho thấy nhóm N đi trước nhóm R bất kể được đăng ký xen kẽ.
- **Hai dòng `retransform`:** chỉ `R1,R2` được gọi lại. Thứ tự giữa chúng vẫn như lúc đăng ký.
- **Dòng ứng dụng:** `base` cho thấy transformer không sửa bytecode vì tất cả đều trả `null`.

Nếu JVM không hỗ trợ retransform hoặc `Probe` không thể sửa, ví dụ chủ động báo lỗi thay vì in kết quả “hoàn tất” gây hiểu nhầm. Đây là điều kiện runtime đã được kiểm tra trong code, không phải một kết quả stdout thay thế tự đoán.

### 4.8. Thử thay thứ tự đăng ký trong cùng nhóm

Trong `OrderAgent.premain`, đổi hai lệnh N:

```java
inst.addTransformer(new TraceTransformer("R1"), true);
inst.addTransformer(new TraceTransformer("N2"), false);
inst.addTransformer(new TraceTransformer("R2"), true);
inst.addTransformer(new TraceTransformer("N1"), false);
```

Đây là **phần code thay thế cho bốn lệnh đăng ký** trong file đầy đủ, không phải một chương trình riêng. Sau khi biên dịch và đóng JAR lại, các dòng callback khi load dự kiến sẽ là:

```text
[N2] load
[N1] load
[R1] load
[R2] load
```

Nếu đổi hai lệnh R thay vì hai lệnh N, phần của nhóm R sẽ đổi vị trí tương ứng. Đây là phép thử trực tiếp của quy tắc **“trong cùng nhóm, gọi theo thứ tự đăng ký”**.

Lưu ý: không cần đổi `className`, manifest hoặc JDK để thực hiện phép thử; thay đổi duy nhất ảnh hưởng đến chuỗi callback là thứ tự các lần đăng ký.

## 5. Khi `retransformClasses`: thứ tự vẫn còn, nhưng nhóm không capable không chạy lại

Điểm cần phân biệt rõ: **thứ tự pipeline** và **số lần callback được gọi** không phải cùng một khái niệm.

Với quá trình retransform, JVM làm việc theo hợp đồng:

1. Bắt đầu từ bytes định nghĩa thích hợp của class (không nhất thiết từng byte giống file gốc trên đĩa do JVM có thể biểu diễn lại constant pool).
2. **Tái áp dụng kết quả trước đó** của transformer không có khả năng retransform, theo cùng thứ tự nhóm, **không gọi lại** callback của chúng.
3. Gọi callback của transformer đã đăng ký với `canRetransform=true` theo thứ tự trong nhóm.
4. Kiểm tra và cài đặt định nghĩa class mới nếu hợp lệ.

Hình minh họa cho trường hợp chỉ có Java transformers:

```text
Lúc load mới:
  B0 -> N1() -> N2() -> R1() -> R2() -> bytes được định nghĩa

Lúc retransform:
  B0' -> [kết quả N1 đã lưu] -> [kết quả N2 đã lưu]
      -> R1() -> R2() -> bytes mới được kiểm tra và áp dụng
         ^         ^
       callback  callback

  N1 và N2 KHÔNG nhận callback lại trong giai đoạn này.
```

Dấu `B0'` nhấn mạnh bytes bắt đầu khi retransform có thể không giống hệt layout của classfile ban đầu; điều quan trọng là các kết quả của nhóm không capable được dùng lại theo hợp đồng.

**Vì sao quan trọng?** Nếu `N1` đã chèn bytecode trong lần load đầu tiên, lần retransform không tự xóa hiệu ứng của nó chỉ vì `N1` không được gọi lại. JVM có cơ chế tái áp dụng biến đổi cũ. Không nên suy từ log chỉ có `R1,R2` rằng bytes của N đã “biến mất”.

Với redefine, callback của các nhóm phù hợp vẫn có thể chạy. Với retransform, chỉ nhóm capable chạy callback lại. Thứ tự trong từng nhóm vẫn theo thứ tự đăng ký ở cả hai tình huống.

Trong code thực, chỉ dùng `inst.addTransformer(t, true)` khi `inst.isRetransformClassesSupported()` là `true`; cần manifest `Can-Retransform-Classes: true` và JVM hỗ trợ capability. Ngoài ra kiểm tra `inst.isModifiableClass(clazz)` trước khi yêu cầu cập nhật class cụ thể.

## 6. Nhóm native và JVMTI nằm ở đâu?

Java instrumentation có thể cùng tồn tại với công cụ JVM Tool Interface (JVMTI) viết bằng native code. Ở tầng native, `ClassFileLoadHook` cho phép nhận sự kiện liên quan đến class bytes.

Thứ tự đầy đủ của cả bốn nhóm là:

```text
Java N group   ->  Native N group  ->  Java R group  ->  Native R group
  N1,N2,...          JNI/JVMTI          R1,R2,...          JNI/JVMTI
```

Trong **mỗi nhóm native**, callback vẫn theo thứ tự các transformer native được đăng ký theo cơ chế của chúng. Đây là thứ tự do Javadoc `ClassFileTransformer` quy định; người viết Java agent thuần **không** dùng `Instrumentation.addTransformer` để đăng ký một JVMTI `ClassFileLoadHook` native.

Hai điều nên tránh khẳng định:

- “Toàn bộ transformer Java luôn chạy xong trước native.” **Sai:** nhóm native không capable nằm giữa hai nhóm Java.
- “Đăng ký native sau tất cả Java transformer nghĩa là chắc chắn nó chạy cuối.” **Sai:** vị trí được quyết định bởi **nhóm**, rồi mới đến thứ tự đăng ký trong nhóm.

Ví dụ JVM có Java `N1,N2,R1,R2` và thêm JVMTI native `JN` (không capable), `JR` (capable) thì thứ tự theo nhóm là:

```text
N1 -> N2 -> JN -> R1 -> R2 -> JR
```

Đây là **ví dụ lý thuyết**, không phải kết quả của chương trình Java ở mục 4 (chương trình đó không cài JVMTI native agent). Để kiểm chứng thực nghiệm native order, phải có một JVMTI agent và môi trường native thích hợp, ngoài phạm vi ví dụ Java thuần.

## 7. Các quy tắc vẫn đúng khi thay transformer

### 7.1. `addTransformer` không hoán đổi các bước có sẵn

`Instrumentation.addTransformer(t, canRetransform)` đăng ký một transformer cho các sự kiện tương lai phù hợp. Nó không tự gọi lại callback cho lớp đã nạp, không tự retransform, không sắp xếp lại transformers trong nhóm khác theo thứ tự đăng ký toàn cục.

Đăng ký **muộn hơn** không cho phép một transformer nhóm N chạy sau transformer nhóm R đã đăng ký sớm. Nhóm vẫn được ưu tiên theo quy định.

### 7.2. `removeTransformer` tác động đến đăng ký tương lai

```java
boolean removed = inst.removeTransformer(transformer);
```

Đây là **đoạn method minh họa**, trong đó `inst` và `transformer` là các biến đã có. API trả `true` nếu tìm được một đăng ký tương ứng và gỡ nó. Nếu **cùng một instance** đã bị đăng ký nhiều lần, API gỡ lần đăng ký phù hợp **mới nhất**; vì vậy nhà phát triển được khuyến nghị **không đăng ký trùng instance**.

Do class loading đa luồng, callback đã bắt đầu hoặc đang được lên lịch vẫn có thể xảy ra sau khi bạn gọi `removeTransformer`; đừng dùng lời gọi này như rào chắn đồng bộ tuyệt đối. Nếu định nghĩa lại pipeline sau khi gỡ và đăng ký mới, cần tính lại thứ tự cho các sự kiện **về sau**, không suy đoán rằng lớp đã nạp sẽ tự được biến đổi ngay lập tức.

### 7.3. Một instance được đăng ký hai lần không phải hai transformer “độc lập”

Dù API có thể cho phép đăng ký lại cùng một đối tượng nhiều lần, điều đó dễ dẫn tới:

- Log trùng, callback nhiều lần không mong muốn.
- Khó xác định đăng ký nào thuộc nhóm nào.
- Gỡ bằng `removeTransformer` không nhất thiết loại bỏ mọi lần đăng ký.
- Các phép sửa bytecode không idempotent bị áp dụng lặp.

Tạo các instance rõ ràng, giữ reference khi cần gỡ, và quản lý chính xác vòng đời đăng ký.

### 7.4. “Đúng thứ tự” không có nghĩa “đúng mọi kết quả”

Những điều vẫn có thể làm phép biến đổi thất bại dù thứ tự hoàn toàn đúng:

- Một transformer trả class bytes không hợp lệ, làm JVM báo lỗi verify/format.
- Transformer phía sau dựa vào cấu trúc mà transformer trước đã thay đổi.
- Filter theo tên lớp sai (`"demo.Probe"` thay vì tên nội bộ `"demo/Probe"`).
- Biến đổi class không hợp lệ trong retransform/redefine.
- Code instrument phụ thuộc vào chính những lớp nó đang cố instrument, tạo recursion hoặc lỗi nạp class.
- Một callback sử dụng trạng thái chia sẻ không đồng bộ giữa các thread nạp lớp.

Lọc đúng class/module/loader, kiểm tra dữ liệu đầu vào, tránh mutate `classfileBuffer`, và kiểm thử nhiều agent cùng lúc để phát hiện xung đột.

## 8. Thứ tự callback có thể liên quan tới concurrency

Một JVM có thể nạp **nhiều lớp trên nhiều thread**. Quy tắc “bên trong từng nhóm theo thứ tự đăng ký” áp dụng **cho chuỗi biến đổi của một sự kiện định nghĩa/cập nhật lớp**, không có nghĩa mọi dòng log của tất cả lớp trên toàn JVM phải sắp thành một dãy tuần tự duy nhất.

Ví dụ nếu hai lớp `A` và `B` cùng load, bạn có thể thấy output xen kẽ giữa sự kiện A và sự kiện B, trong khi **đối với từng lớp**, các bước transformer vẫn tuân thứ tự.

Do vậy khi chẩn đoán pipeline thực tế nên ghi đủ:

- Tên nội bộ lớp (`className`).
- Tham chiếu hoặc danh tính `ClassLoader`.
- Danh tính `Module` (nếu cần).
- Tên/ID transformer.
- Thread/pha (`load`, `redefine`, `retransform`) khi có bằng chứng xác định pha.
- Mã hash/fingerprint của mảng bytes đầu vào/đầu ra nếu cần truy vết biến đổi.

Đừng dựa vào một file log đa luồng chưa có correlation ID để kết luận quy tắc nhóm của JVM bị vi phạm.

## 9. Những nhầm lẫn điển hình

| Nhầm lẫn | Điều đúng |
|---|---|
| “Đăng ký R1 trước N1 thì R1 chạy trước” | **Sai:** N luôn thuộc nhóm ưu tiên trước R ở chuỗi Java |
| “Trong cùng nhóm JVM gọi không theo thứ tự nào” | **Sai:** gọi theo **thứ tự đăng ký** |
| “Có hai nhóm Java nên các native transformers đều ở cuối” | **Sai:** native N ở giữa Java N và Java R |
| “Khi retransform, các N transformers chạy lại” | **Sai:** kết quả N trước đó được **tái áp dụng** không cần callback |
| “Không thấy N log lần retransform nghĩa là hiệu ứng N bị bỏ” | **Sai:** kết quả cũ vẫn được dùng |
| “`return null` dừng mọi transformer sau đó” | **Sai:** giữ nguyên bytes ở bước hiện tại và tiếp tục |
| “Thứ tự log xen kẽ giữa nhiều lớp chứng minh lỗi pipeline” | **Sai:** phải đối chiếu trên **từng sự kiện lớp** |
| “Chỉ cần đổi thứ tự đăng ký là sửa được class đã load” | **Sai:** việc cập nhật class hiện hữu là thao tác khác, chịu giới hạn của JVM |
| “Mọi transformer đều có quyền retransform” | **Sai:** khả năng phụ thuộc cách đăng ký và JVM/manifest |
| “N1/N2 trong nhóm N có thể bỏ qua thứ tự đăng ký” | **Sai:** thứ tự của chúng ảnh hưởng bytes truyền cho nhau |

## 10. Bài tập suy luận theo thứ tự

### Câu 1. Đăng ký xen kẽ hai nhóm

Agent gọi:

```java
inst.addTransformer(r2, true);
inst.addTransformer(n2, false);
inst.addTransformer(r1, true);
inst.addTransformer(n1, false);
```

**Thứ tự load mới theo hai nhóm Java?**

Đáp án: `N2 -> N1 -> R2 -> R1`. Nhóm N trước nhóm R; trong từng nhóm giữ nguyên thứ tự các lần đăng ký.

### Câu 2. Đổi vị trí hai lệnh cùng nhóm

Đổi `addTransformer(n2, false)` và `addTransformer(n1, false)` trong lịch sử trên nhưng không đổi hai lệnh R. Điều gì xảy ra?

Đáp án: `N1 -> N2 -> R2 -> R1`. Chỉ thứ tự **trong nhóm N** đổi.

### Câu 3. Có native JVMTI ở giữa

Các Java transformer chạy theo thứ tự nhóm `N1,N2,R1,R2`. Có thêm native `JN` không capable và native `JR` capable. Thứ tự tổng là gì?

Đáp án: `N1 -> N2 -> JN -> R1 -> R2 -> JR`.

### Câu 4. Retransform

Với ví dụ mục 4, vì sao chỉ in `R1`, `R2` khi retransform?

Đáp án: `N1,N2` đăng ký `false` nên không nhận lại callback; kết quả biến đổi cũ được JVM tái áp dụng trước khi gọi nhóm R.

### Câu 5. Hai transformer tạo bytes mới

Một transformer nhóm N thêm instruction trước method, transformer thứ hai trong cùng nhóm chèn instruction khác dựa vào instruction đầu hiện có. Đổi thứ tự N có thể làm kết quả khác không?

Đáp án: Có. Bước sau nhận bytes sau biến đổi của bước trước, nên thao tác có thể **không giao hoán**. Phải thử cả chuỗi và kiểm tra bytecode hợp lệ.

### Câu 6. Cả hai đều trả `null`

Nếu N1, N2, R1, R2 đều trả `null`, có thể kết luận JVM bỏ qua nhóm nào không?

Đáp án: Không. Chúng vẫn nhận callback khi load mới và giữ bytes đầu vào ở mỗi bước; `null` chỉ nói rằng không có mảng bytes thay thế tại bước đó.

### Câu 7. Thêm R3 sau N2

Thêm `inst.addTransformer(r3, true)` sau bốn lệnh đăng ký ban đầu `R1,N1,R2,N2`. Thứ tự load mới trở thành gì?

Đáp án: `N1 -> N2 -> R1 -> R2 -> R3`. `R3` là cuối **nhóm R**.

### Câu 8. Đổi thứ tự nạp lớp khác nhau

Hai lớp khác nhau cùng được load trên hai thread; log hiển thị callback của chúng xen kẽ. Có được kết luận rằng thứ tự trong một nhóm bị phá vỡ không?

Đáp án: Không. Cần nhóm log theo từng class loading event rồi kiểm tra thứ tự **bên trong sự kiện đó**.

## 11. Ghi nhớ để áp dụng

**Hai tầng quy tắc là điều cốt lõi:**

1. JVM đặt các transformer vào bốn **nhóm cố định** theo khả năng retransform và Java/native.
2. **Trong mỗi nhóm**, transformer được gọi **theo thứ tự đăng ký**.
3. Mỗi transformer nhận kết quả bytes của bước trước; `return null` giữ nguyên bytes, không dừng chuỗi.
4. Khi retransform, các transformer **không capable** không được gọi lại; kết quả trước đó được tái áp dụng, rồi các transformer **capable** chạy lại theo thứ tự trong nhóm.
5. Với nhiều class load đồng thời, đánh giá thứ tự **theo sự kiện của một lớp**, không từ log toàn cục đã xen thread.

Trong ví dụ Java thuần, lệnh đăng ký `R1,N1,R2,N2` phải được hiểu thành chuỗi callback load **`N1,N2,R1,R2`**. Đây là cách kiểm tra chính xác nội dung “thứ tự đăng ký bên trong từng nhóm”.

## Tài liệu tham khảo

- Oracle Java 17 — [`ClassFileTransformer`: transformation order và chaining](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).
- Oracle Java 17 — [`Instrumentation`: addTransformer, removeTransformer, retransformClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- OpenJDK — [Java Instrumentation Package Specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html).
- OpenJDK — [JVM TI Specification: `ClassFileLoadHook`](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html).
