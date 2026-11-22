# MethodHandle trong Java: CallSite và vai trò của invokedynamic

## 1. Tại sao Java cần CallSite và invokedynamic?

Trong mã Java quen thuộc, compiler thường biết loại lời gọi method và tạo bytecode phù hợp như `invokevirtual`, `invokestatic`, `invokeinterface` hoặc `invokespecial`. Tuy nhiên, các runtime cần cơ chế **liên kết (link) hành vi của một điểm gọi khi chương trình thực thi**: ví dụ compiler của ngôn ngữ động trên JVM, biểu thức lambda, method reference, hoặc cách thực hiện tối ưu phép nối chuỗi.

Từ **Java 7**, JVM có lệnh bytecode `invokedynamic` và package `java.lang.invoke`, gồm `MethodHandle`, `MethodType` và `CallSite`. Tính năng **vẫn được sử dụng trong Java 17+**, không phải API đã legacy. Những tính năng hiện đại xây trên cơ chế đó bao gồm:
- **Lambda expressions/method references** được Java 8 giới thiệu, thường link qua `LambdaMetafactory`.
- **Nối chuỗi `+`** trong bytecode do Java 9+ `javac` phát sinh, thường link qua `StringConcatFactory`.
- Runtime của các ngôn ngữ và framework có thể dùng custom bootstrap methods để quản lý điểm gọi động.

Bài **“CallSite và vai trò của invokedynamic”** thuộc chủ đề **“MethodHandle”**. Cần phân biệt ba đối tượng:

1. **`MethodHandle`** — một tham chiếu có kiểu đến hành vi có thể gọi được; giống một “function pointer” được JVM quản lý, nhưng có type và access checks của Java.
2. **`CallSite`** — vật chứa một `MethodHandle` đích (*target*) của một điểm gọi động. Đích có thể cố định hoặc thay đổi tùy subclass.
3. **`invokedynamic`** — lệnh JVM mà lúc link sẽ nhận một `CallSite` từ *bootstrap method* rồi thực thi theo target của site đó.

**Câu chốt:** `MethodHandle` mô tả **gọi gì**, `CallSite` mô tả **điểm gọi hiện liên kết tới handle nào**, còn `invokedynamic` là **bytecode sử dụng liên kết động do bootstrap thiết lập**.

## 2. Các khối xây dựng trong `java.lang.invoke`

### 2.1. `MethodType`: chữ ký chính xác của điểm gọi

Một `MethodType` mô tả return type và các parameter types:

```java
MethodType type =
        MethodType.methodType(String.class, String.class);
```

`type` trên là `(String)String`: nhận một `String` và trả một `String`. Trong Java source có generic parameters, nhưng `MethodType` mang kiểu JVM thực sự sau erasure, gồm primitives và reference classes, không phải mô tả đầy đủ generic signatures.

Ví dụ:
- `MethodType.methodType(void.class)` là `()void`.
- `MethodType.methodType(int.class, int.class, int.class)` là `(int,int)int`.
- `MethodType.methodType(String.class, String.class)` là `(String)String`.

### 2.2. `MethodHandles.Lookup`: bối cảnh quyền truy cập

`MethodHandles.lookup()` tạo `Lookup` gắn với vị trí caller, dùng để tìm `MethodHandle` theo các quy tắc access control/module boundaries của Java. Ví dụ:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle target = lookup.findStatic(
        SomeClass.class,
        "work",
        MethodType.methodType(String.class, String.class));
```

Đây là **snippet minh họa**, `SomeClass.work(String)` phải thật sự tồn tại và caller phải có quyền tìm. Nếu sai tên, sai chữ ký hoặc không được phép truy cập, `findStatic` có thể ném `NoSuchMethodException` hoặc `IllegalAccessException`.

**Không coi MethodHandle là phương pháp hợp lệ để tự động vượt quyền `private` hoặc rào cản module.** Một bootstrap method cũng nhận `Lookup` đúng context do JVM cung cấp.

### 2.3. `MethodHandle`: đối tượng có thể gọi

`MethodHandle.invokeExact(...)` dùng chữ ký **tại call site của chính lời gọi Java**, phải khớp chính xác type của handle. Một call site Java có thể phải cast kết quả để compiler tạo descriptor đúng.

```java
String output = (String) target.invokeExact("Ada");
```

Đây là snippet trong method khai báo `throws Throwable` hoặc xử lý lỗi. Nếu expected descriptor tại call site Java không tương thích, có thể gặp `WrongMethodTypeException`. `invoke(...)` có khả năng type adaptation hơn `invokeExact`, nhưng không biến mọi conversion thành hợp lệ.

### 2.4. `CallSite`: vật chứa target

`java.lang.invoke.CallSite` là lớp trừu tượng. Ba subclass chuẩn trong Java 17:
- `ConstantCallSite` — target **cố định**.
- `MutableCallSite` — target thay đổi như một field thông thường; có `syncAll(...)` cho công bố cập nhật.
- `VolatileCallSite` — target thay đổi với **volatile memory semantics**.

Một `CallSite` có `type()`, `getTarget()`, `setTarget(...)` (theo subclass), và `dynamicInvoker()`. Điểm gọi động có thể gắn với một lệnh `invokedynamic` **hoặc tồn tại độc lập** dưới dạng object Java (*free-floating CallSite*).

## 3. Sơ đồ vai trò: Bootstrap Method → CallSite → MethodHandle

```text
Java source / other-language compiler
                |
                | compiles
                v
       Class file (bytecode)
                |
                +-- invokedynamic name + descriptor
                |
                +-- BootstrapMethods attribute
                       |
                       | JVM resolves/linkage
                       v
                Bootstrap method
                (Lookup, String, MethodType, ...)
                       |
                       | returns a CallSite
                       v
                    CallSite
                     | type: (String)String
                     | target: MethodHandle
                     v
                   MethodHandle
                       |
                       | invoke with runtime operands
                       v
                   Java behavior
```

Khác biệt với lời gọi tĩnh: bytecode `invokedynamic` **không cố định sẵn method đích giống một lệnh `invokestatic` thông thường**. Khi liên kết, JVM nhờ bootstrap method tạo đối tượng CallSite đúng chữ ký. Sau đó những lần thực thi điểm gọi sử dụng target do CallSite cung cấp.

Nếu CallSite là `ConstantCallSite`, đích cố định; nếu là `MutableCallSite` hoặc `VolatileCallSite`, runtime có thể đổi target nhưng **không được đổi method type của điểm gọi**.

### 3.1. Hai tầng thời điểm

**Linkage phase:** JVM resolve symbolic reference của điểm gọi, chuẩn bị bootstrap arguments và lấy CallSite. Không phải mỗi lần gọi method lại chạy bootstrap.

**Invocation phase:** các operands runtime được truyền tới target MethodHandle. Lời gọi có thể xảy ra nhiều lần sau khi linkage hoàn tất.

**Lưu ý tinh tế:** khi có các threads cùng race để resolve một symbolic reference, JVMS cho phép liên quan đến việc bootstrap được gọi nhiều hơn một lần trong quá trình tranh chấp, nhưng **kết quả resolution được dùng để link chỉ là một kết quả hợp lệ theo quy tắc JVM**. Do đó không xây logic nghiệp vụ đòi hỏi bootstrap “chính xác chỉ có một side effect” trong mọi tình huống cạnh tranh. Kịch bản thông thường chạy lại cùng điểm gọi không re-run bootstrap.

### 3.2. Linkage không phải reflection mỗi lần gọi

Tại mỗi invocation, JVM không bắt buộc thực hiện một lượt `Class.getMethod()` hoặc reflection lookup đầy đủ. Bootstrap đã tạo target có kiểu, JVM có thể tối ưu hóa chuỗi lời gọi. Chi tiết JIT/inlining thay đổi theo runtime và phiên bản; **không khẳng định mọi invokedynamic đều nhanh hơn lời gọi bình thường**.

## 4. Contract của `CallSite`

Một CallSite giữ target:

```java
CallSite site = new ConstantCallSite(target);
MethodType signature = site.type();
MethodHandle current = site.getTarget();
MethodHandle dynamic = site.dynamicInvoker();
```

Đây là snippet yêu cầu `target` đã được tạo và không null.

### 4.1. `type()` không thay đổi khi relink

CallSite type được xác định khi tạo; `setTarget(newTarget)` trên mutable/volatile site đòi **`newTarget.type().equals(site.type())`**. Sai type có thể ném `WrongMethodTypeException`.

Ví dụ site có type `(String)String` không thể chuyển target thành `(int)int` bằng một `setTarget` đơn thuần. Nếu ý định chuyển đổi loại tham số, cần một `MethodHandle` được **thích ứng có kiểm tra** (ví dụ `asType` nếu hợp lệ), để target cuối vẫn mang chữ ký chính xác.

### 4.2. `getTarget()` và `dynamicInvoker()` không giống nhau

- `getTarget()` lấy một `MethodHandle` là **target tại thời điểm đọc** (và theo memory semantics của subclass).
- `dynamicInvoker()` tạo hoặc trả handle **chuyển tiếp lời gọi đến target hiện tại của site**.

Với `ConstantCallSite`, vì target không đổi, `dynamicInvoker()` có thể trả thẳng target vĩnh viễn. Với mutable/volatile site, handle dynamic invoker **theo target đang được liên kết**, nên nó khác với một reference chụp trước bằng `getTarget`.

### 4.3. Không nhầm CallSite với một biến function tùy ý

Một `CallSite` mang **chữ ký method cố định**, có quy tắc liên kết và được JVM sử dụng bởi `invokedynamic`. Nó không phải `Object` có thể lưu một giá trị bất kỳ rồi gọi với mọi kiểu. Điều đó quan trọng cho:
- Bootstrap type checks.
- Khả năng tối ưu hóa của JVM.
- Quy tắc thay thế target khi đổi hành vi.
- Các lỗi `WrongMethodTypeException` khi signature sai.

## 5. `ConstantCallSite`: liên kết cố định

`ConstantCallSite` giữ target vĩnh viễn:

```java
MethodHandle hello = lookup.findStatic(
        Demo.class, "hello",
        MethodType.methodType(String.class, String.class));
ConstantCallSite site = new ConstantCallSite(hello);
String result =
        (String) site.dynamicInvoker().invokeExact("Ada");
```

Đây là snippet mô tả, `Demo.hello` và biến `lookup` phải tồn tại. Chương trình hoàn chỉnh bên dưới dùng class `CallSiteIndyDemo`.

**Đặc trưng:**
- `getTarget()` không chuyển qua handle khác sau khi tạo.
- `setTarget(...)` **luôn ném `UnsupportedOperationException`**.
- `dynamicInvoker()` trả target cố định (xem Javadoc).
- Phù hợp cho bootstrap khi một điểm gọi có thể liên kết một lần rồi giữ target lâu dài.

Cần phân biệt **target reference không thay đổi** với **hành vi bên trong target luôn trả cùng kết quả**. Một method được target tham chiếu vẫn có thể đọc tham số, state hoặc nguồn dữ liệu biến thiên. `ConstantCallSite` không biến logic target thành hàm toán học thuần.

### 5.1. Vì sao không sửa target?

Vì JVM có thể khai thác thông tin rằng liên kết là bất biến. Nếu cần thay target theo runtime, phải chọn subclass cho phép relink thay vì cố thay bằng reflection/unsafe.

### 5.2. Khi nào thích hợp?

- Bootstrap lambda factory tạo CallSite cố định.
- String concat factory liên kết một kiểu biểu thức.
- Method dispatch mà rule không đổi cho điểm gọi đó.
- Custom language runtime với liên kết ổn định.

Không phải mọi lambda trong Java tạo class theo một cơ chế triển khai cứng nhắc; đặc tả cho phép nhiều phương thức tạo function object. Điều quan trọng là *contract* của CallSite và chức năng của bootstrap.

## 6. `MutableCallSite`: thay target mà giữ chữ ký

Khởi tạo:

```java
MutableCallSite site = new MutableCallSite(handleA);
MethodHandle invoker = site.dynamicInvoker();

// Lúc đầu: invoker chuyển lời gọi tới handleA.
site.setTarget(handleB);
MutableCallSite.syncAll(new MutableCallSite[]{site});

// Sau synchronization: những lời gọi phù hợp sẽ dùng target mới.
```

Đây là snippet, `handleA` và `handleB` phải có cùng `MethodType`. Việc `setTarget` không phải thao tác đổi signature.

### 6.1. Tại sao lưu `dynamicInvoker` khác với lưu `getTarget`?

Nếu bạn giữ `MethodHandle saved = site.getTarget()` rồi đổi site sang target mới, `saved` **vẫn là handle cũ**. Nhưng handle từ `site.dynamicInvoker()` luôn gọi theo target được site quản lý.

```text
site.target = HELLO
saved  = site.getTarget()      -> HELLO
dynamic = site.dynamicInvoker -> delegates to site.target

site.setTarget(GOODBYE)
MutableCallSite.syncAll(...)

saved.invokeExact(...)          -> HELLO
dynamic.invokeExact(...)        -> GOODBYE
```

Đây là thay đổi **liên kết của CallSite**, không phải thay nội dung `MethodHandle` đã được lưu trước đó.

### 6.2. `MutableCallSite` có volatile semantics không?

**Không.** `getTarget()/setTarget()` hoạt động như đọc/ghi một field thông thường. Nếu thread A `setTarget` và thread B gọi site, **không có synchronization phù hợp**, thread B có thể tiếp tục thấy target cũ mà không có giới hạn thời gian rõ ràng.

Java SE 17 cung cấp `MutableCallSite.syncAll(MutableCallSite[] sites)` để buộc các readers bỏ những target đã cache theo quy tắc của API.

### 6.3. Cách dùng `syncAll`

```java
site.setTarget(newTarget);
MutableCallSite.syncAll(new MutableCallSite[]{site});
```

Sau `syncAll`, các readers tương lai nhận được cập nhật mục tiêu theo contract. Tuy nhiên:
- Lời gọi đã bắt đầu trên old target **không bị tua ngược**.
- Giữa `setTarget` và `syncAll`, một thread **có thể đã thấy target mới** trong khi thread khác chưa.
- `syncAll` **không tạo transaction nguyên tử** khi thay nhiều CallSites; nó buộc công bố chứ không bảo đảm toàn bộ điểm gọi đổi cùng một khoảnh khắc.
- Nên phối hợp `setTarget`/`syncAll` bằng mutual exclusion thích hợp để tránh các writers cạnh tranh.
- `syncAll` có thể tốn chi phí và nên dùng tiết kiệm; nếu có thể, gom nhiều cập nhật thay vì sync liên tục.

### 6.4. `MutableCallSite(MethodType)` tạo đích ban đầu đặc biệt

```java
MutableCallSite blank = new MutableCallSite(
        MethodType.methodType(String.class, String.class));
```

Constructor với type chưa có method thực; initial target là một handle **ném `IllegalStateException` khi gọi**. Trước khi dùng CallSite (hoặc trả từ bootstrap) thường phải `setTarget(...)` tới một MethodHandle đúng type. Không coi một site mới có MethodType là đã “link thành công” chỉ vì constructor trả về.

## 7. `VolatileCallSite`: relink với volatile visibility

`VolatileCallSite` có API gần giống `MutableCallSite`, nhưng việc đọc/ghi target có **memory semantics như field `volatile`**:

```java
VolatileCallSite site = new VolatileCallSite(handleA);
MethodHandle invoker = site.dynamicInvoker();
site.setTarget(handleB); // volatile write đối với target
```

Khi thread khác đọc target/dynamic invoker, các cập nhật được quan sát theo volatile semantics; **không cần `VolatileCallSite.syncAll`**, và class này không cung cấp method `syncAll`.

### 7.1. Trade-off

| Tiêu chí | MutableCallSite | VolatileCallSite |
| --- | --- | --- |
| target có thể đổi | Có | Có |
| Memory semantics | Field thông thường | Field volatile |
| Công bố giữa threads | Cần sync thích hợp; `syncAll` khi cần | Target reads/writes có volatile semantics |
| API syncAll | Có | Không |
| Cost/optimization | Có thể tiết kiệm cho relink hiếm | Có thể chịu chi phí volatile access |
| Nên dùng khi | Cập nhật ít, batch relink có kiểm soát | Cập nhật cần các readers thấy nhanh, thường xuyên |

Không đoán hiệu năng chỉ từ tên class. Benchmark thực tế và đặc điểm workload quyết định. `VolatileCallSite` không tự khiến **toàn bộ dữ liệu mutable mà target truy cập** trở thành thread-safe; nó chỉ mô tả tính đồng bộ của target và các happens-before tương ứng.

### 7.2. Volatile không làm lời gọi đang chạy thay code giữa chừng

Nếu một thread đã vào old target, thay CallSite target ở thread khác **không hủy/restart** lời gọi đang chạy. Những invocation tiếp theo dùng target theo memory semantics được bảo đảm, không phải một cơ chế hot-swap transaction cho toàn bộ logic chương trình.

## 8. Bảng so sánh ba CallSite

| API / quy tắc | ConstantCallSite | MutableCallSite | VolatileCallSite |
| --- | --- | --- | --- |
| Target ban đầu từ MethodHandle | Có | Có | Có |
| Có constructor nhận MethodType | Protected-special hook | Có, target ném IllegalStateException khi chưa set | Có, target ném IllegalStateException khi chưa set |
| `type()` cố định | Có | Có | Có |
| `getTarget()` | Target cố định | Đọc như ordinary field | Đọc như volatile field |
| `setTarget(newTarget)` | Luôn UnsupportedOperationException | Có, type phải khớp | Có, type phải khớp |
| `dynamicInvoker()` | Có, cố định | Theo current target | Theo current target |
| `syncAll` | Không | Có | Không cần / không có |
| Target đổi làm MethodType đổi? | Không | Không | Không |
| Phù hợp cho | Liên kết cố định | Relink có batch synchronization | Liên kết cần cross-thread visibility chặt |
| Thread khác tự thấy update ngay? | Không có update | Không bảo đảm nếu thiếu synchronization | Theo volatile semantics |

**Tất cả thuộc `java.lang.invoke`, tồn tại trong Java 7 và vẫn được hỗ trợ trong Java 17+.** Không xếp chúng vào API đã lỗi thời.

## 9. invokedynamic thực sự làm gì khi JVM link điểm gọi?

### 9.1. Trong class file có gì?

Một `invokedynamic` instruction tham chiếu đến một entry **`CONSTANT_InvokeDynamic_info`** trong constant pool. Entry đó chứa:
- `bootstrap_method_attr_index` trỏ vào `BootstrapMethods` attribute.
- `name_and_type_index` xác định **tên** và **method descriptor** của điểm gọi.

Bootstrap method có thể nhận:
1. `MethodHandles.Lookup` trong context của điểm gọi.
2. `String` tên symbolic.
3. `MethodType` mô tả chữ ký của điểm gọi.
4. Các **static bootstrap arguments** bổ sung được compiler đưa vào constant pool nếu bootstrap cần.

Bootstrap trả **`CallSite`** có method type phù hợp với điểm gọi. JVM liên kết điểm gọi với CallSite đó và thực thi theo target; target không nhất thiết được quyết định tại thời điểm compile.

### 9.2. Tách static bootstrap arguments với runtime operands

```text
Static linkage data (class file):
    name, descriptor, bootstrap handle, optional constants
                       |
                       v
                  Bootstrap method
                       |
                       v
                    CallSite

Runtime operands (khi invokedynamic chạy):
    args for target.invoke(...)
                       |
                       v
             target MethodHandle
```

Đừng nhầm arguments để **xây CallSite** với arguments truyền vào **target mỗi lần gọi**. Ví dụ lambda capture có operands động để tạo function object; static args mô tả functional interface và implementation method.

### 9.3. Mismatch và lỗi linkage

Các vấn đề thường gặp:
- Bootstrap không trả đúng một CallSite.
- CallSite target type khác descriptor mà `invokedynamic` yêu cầu.
- Bootstrap không truy cập được method cần link.
- Bootstrap ném exception hoặc tự khởi tạo sai.
- Target bị set sang MethodType không tương thích.

Trong JVM linkage, lỗi bootstrap có thể biểu hiện bằng **`BootstrapMethodError`**. Các lời gọi `MethodHandle.invokeExact`/`CallSite.setTarget` cũng có thể gặp `WrongMethodTypeException` khi chữ ký không phù hợp; nơi và loại exception phụ thuộc bước đang lỗi. Không “fix” các lỗi type bằng ép cast vô căn cứ.

### 9.4. Không viết trực tiếp `invokedynamic` bằng cú pháp Java thông thường

Không có statement Java source kiểu `invokedynamic x()` để bạn tự gọi như một method. Compiler/JVM bytecode sử dụng instruction này. Nếu muốn **tạo điểm gọi invokedynamic tùy biến**, thường cần compiler, class-file generator hoặc bytecode library phù hợp và được kiểm thử rõ. Không thêm thư viện chỉ để hiểu nguyên lý; `CallSite.dynamicInvoker()` có thể mô phỏng semantics chuyển tiếp ở Java code.

## 10. Bootstrap method tự viết: hiểu chính xác vai trò

Một bootstrap method đơn giản có thể mang dạng:

```java
static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String name,
        MethodType type) throws ReflectiveOperationException {

    if (!"hello".equals(name)) {
        throw new IllegalArgumentException("unknown name");
    }

    MethodHandle target = caller.findStatic(
            Demo.class, "hello",
            MethodType.methodType(String.class, String.class));

    return new ConstantCallSite(target.asType(type));
}
```

Đây là **snippet minh họa**, `Demo.hello` phải tồn tại và caller phải được phép truy cập. Việc `asType(type)` được dùng nhằm làm target có signature khớp type; nếu adaptation không hợp lệ sẽ có lỗi.

Khi JVM xử lý một `invokedynamic` thực, nó cung cấp ba arguments đầu (và bootstrap static args tùy call site), rồi dùng CallSite trả về để link. **Gọi `bootstrap(...)` trực tiếp từ Java chỉ thử logic bootstrap**; không sinh ra một instruction `invokedynamic` mới.

### 10.1. Tác dụng của `Lookup caller`

Bootstrap có thể tìm member theo quyền truy cập của caller. Nó không có quyền tùy ý vượt module encapsulation. Không đưa một `Lookup` nhạy cảm cho code chưa tin cậy mà không đánh giá phạm vi quyền.

### 10.2. Điều gì phải được kiểm trước khi return?

- `name` và metadata liên kết được hiểu đúng.
- `type` là chữ ký point of call và target có đúng signature.
- MethodHandle không null.
- Quyền truy cập hợp lệ.
- Static arguments được validate, tránh tạo method handles đến hành vi ngoài ý định.
- Side effects tối thiểu, tránh phụ thuộc call-count của bootstrap.
- Nếu cache bootstrap results, có lifecycle và classloader considerations phù hợp.

### 10.3. Khi nào không cần viết bootstrap thủ công?

Đa số Java application code **không cần** tự tạo CallSite. Viết lambda, method reference, chuỗi nối hay dùng standard libraries đã khiến compiler/runtime sử dụng cơ chế cần thiết. Custom bootstrap chỉ cần cho language runtime, bytecode tooling hoặc các hệ thống dynamic dispatch có requirements rõ.

## 11. Lambda expression: một ứng dụng thật của invokedynamic

Với Java 8+:

```java
Function<String, String> upper =
        text -> text.toUpperCase(Locale.ROOT);

String result = upper.apply("abc"); // ABC
```

Đây là snippet cần import `java.util.Locale` và `java.util.function.Function`.

Compiler Java thường biểu diễn lambda bằng một **`invokedynamic`** được link bởi `LambdaMetafactory.metafactory` (hoặc `altMetafactory`). Mục tiêu ở đây là **tạo một object thực thi functional interface**; nó khác với việc gọi `Function.apply` sau đó.

Ba giai đoạn quan trọng:
1. **Linkage:** metafactory chuẩn bị CallSite để tạo function object.
2. **Capture:** thực thi invokedynamic để tạo/nhận function object, lấy các giá trị captured variables nếu có.
3. **Invocation:** gọi abstract method của functional interface trên object; code implementation đã chọn được thực thi.

Không mặc định mỗi lambda expression sẽ sinh một anonymous inner class tĩnh theo bytecode cũ. Runtime có quyền tối ưu hóa hoặc tái sử dụng function objects theo contract; đừng so sánh `==` giữa hai lambdas làm logic nghiệp vụ.

## 12. String concat: một ứng dụng phổ biến trong Java hiện đại

Ví dụ:

```java
String name = "Mia";
int number = 7;
String text = name + "#" + number; // Mia#7
```

Trên **JDK 17 với javac mặc định**, expression nối chuỗi với operands không phải hằng số được compiler biên dịch theo cơ chế `invokedynamic`, thường tham chiếu bootstrap `StringConcatFactory.makeConcatWithConstants`.

Điều này cho phép runtime chọn/điều chỉnh chiến lược thực thi phép nối chuỗi thay vì compiler phải luôn phát sinh một chuỗi `new StringBuilder`/`append` cứng nhắc trong bytecode.

**Giới hạn cần nói rõ:**
- Đây là một lựa chọn của **javac/JDK** đối với code phù hợp; không cam kết mọi compiler/version luôn phát bytecode y hệt.
- Câu nối toàn hằng số có thể được compiler **constant-fold** và không tạo `invokedynamic`.
- Việc compiler dùng StringConcatFactory không làm `+` trở thành lời gọi bảo mật hoặc thay đổi semantics của String concatenation trong Java source.

Dùng `javap -c -v` để kiểm chứng **class file thật** đang chạy.

## 13. Ví dụ Java 17+ độc lập: cả ba CallSite, bootstrap thủ công, lambda và concat

Chương trình **`CallSiteIndyDemo.java`** không cần thư viện ngoài JDK. Nó minh họa:

1. `ConstantCallSite` giữ target `hello`; `setTarget` bị từ chối.
2. `MutableCallSite` được đổi target `hello → goodbye`, sau đó gọi `syncAll`; `dynamicInvoker` thấy target mới nhưng `getTarget` đã lưu trước vẫn gọi old target.
3. Thay target bằng MethodHandle `(int)int` bị từ chối khi site cần `(String)String`.
4. `MutableCallSite(MethodType)` chưa set target sẽ ném `IllegalStateException` khi gọi, sau setTarget chạy đúng.
5. `VolatileCallSite` target được đổi ở main thread và được một worker nhận thông qua dynamic invoker; test dùng `CountDownLatch` để phối hợp thời gian.
6. Gọi `manualBootstrap` thủ công tạo `ConstantCallSite` và dùng `dynamicInvoker`. **Đây không phải lệnh invokedynamic**.
7. Java lambda và string concat thật trong source; `javap -c -v` trên class file xác nhận có `invokedynamic` cùng bootstrap của LambdaMetafactory và StringConcatFactory.

### 13.1. File `CallSiteIndyDemo.java` đầy đủ

```java
import java.lang.invoke.*;
import java.util.Locale;
import java.util.concurrent.*;
import java.util.function.Function;

public final class CallSiteIndyDemo {
    static void check(boolean yes, String message) {
        if (!yes) throw new AssertionError(message);
    }

    public static String hello(String name) {
        return "hello:" + name;
    }

    public static String goodbye(String name) {
        return "goodbye:" + name;
    }

    public static int twice(int n) {
        return n * 2;
    }

    static CallSite manualBootstrap(MethodHandles.Lookup lookup,
                                    String name, MethodType type)
            throws ReflectiveOperationException {
        if (!"hello".equals(name)) {
            throw new IllegalArgumentException("unsupported name");
        }
        MethodHandle target = lookup.findStatic(
                CallSiteIndyDemo.class,
                "hello",
                MethodType.methodType(String.class, String.class));
        return new ConstantCallSite(target.asType(type));
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(String.class, String.class);
        MethodHandle hello = lookup.findStatic(
                CallSiteIndyDemo.class, "hello", type);
        MethodHandle goodbye = lookup.findStatic(
                CallSiteIndyDemo.class, "goodbye", type);
        MethodHandle intTarget = lookup.findStatic(
                CallSiteIndyDemo.class, "twice",
                MethodType.methodType(int.class, int.class));

        ConstantCallSite constant = new ConstantCallSite(hello);
        check(constant.type().equals(type), "constant type");
        String fixed = (String) constant.dynamicInvoker().invokeExact("Ada");
        check("hello:Ada".equals(fixed), "constant invocation");
        System.out.println("constant.value=" + fixed);
        boolean immutable = false;
        try {
            constant.setTarget(goodbye);
        } catch (UnsupportedOperationException expected) {
            immutable = true;
        }
        check(immutable, "constant target can change");
        System.out.println("constant.relinkRejected=" + immutable);

        MutableCallSite mutable = new MutableCallSite(hello);
        MethodHandle dynamic = mutable.dynamicInvoker();
        MethodHandle oldSnapshot = mutable.getTarget();
        String before = (String) dynamic.invokeExact("Ada");
        check("hello:Ada".equals(before), "mutable before");
        mutable.setTarget(goodbye);
        MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        String after = (String) dynamic.invokeExact("Ada");
        String cached = (String) oldSnapshot.invokeExact("Ada");
        check("goodbye:Ada".equals(after), "mutable current target");
        check("hello:Ada".equals(cached), "snapshot handle must remain old");
        System.out.println("mutable.before=" + before);
        System.out.println("mutable.after=" + after);
        System.out.println("mutable.savedOldTarget=" + cached);

        boolean wrongType = false;
        try {
            mutable.setTarget(intTarget);
        } catch (WrongMethodTypeException expected) {
            wrongType = true;
        }
        check(wrongType, "target type changed");
        System.out.println("mutable.wrongTypeRejected=" + wrongType);

        MutableCallSite blank = new MutableCallSite(type);
        boolean blankFails = false;
        try {
            String ignored = (String) blank.dynamicInvoker().invokeExact("Ada");
        } catch (IllegalStateException expected) {
            blankFails = true;
        }
        check(blankFails, "blank call site should throw");
        blank.setTarget(hello);
        String initialized = (String) blank.dynamicInvoker().invokeExact("Ada");
        check("hello:Ada".equals(initialized), "blank init");
        System.out.println("mutable.uninitializedThrows=" + blankFails);
        System.out.println("mutable.initialized=" + initialized);

        VolatileCallSite volatileSite = new VolatileCallSite(hello);
        String volatileBefore = (String) volatileSite.dynamicInvoker()
                .invokeExact("Ada");
        check("hello:Ada".equals(volatileBefore), "volatile initial");
        CountDownLatch go = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();
        String otherThread;
        try {
            Future<String> future = executor.submit(() -> {
                if (!go.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("worker timed out");
                }
                try {
                    return (String) volatileSite.dynamicInvoker()
                            .invokeExact("Ada");
                } catch (Throwable cause) {
                    throw new RuntimeException(cause);
                }
            });
            volatileSite.setTarget(goodbye);
            go.countDown();
            otherThread = future.get(5, TimeUnit.SECONDS);
        } finally {
            go.countDown();
            executor.shutdownNow();
            check(executor.awaitTermination(5, TimeUnit.SECONDS),
                    "worker not terminated");
        }
        check("goodbye:Ada".equals(otherThread), "volatile update");
        System.out.println("volatile.before=" + volatileBefore);
        System.out.println("volatile.otherThreadAfterUpdate=" + otherThread);

        CallSite constructed = manualBootstrap(lookup, "hello", type);
        String direct = (String) constructed.dynamicInvoker().invokeExact("Bao");
        check("hello:Bao".equals(direct), "bootstrap result");
        System.out.println("bootstrap.manualCallSite=" + direct);
        System.out.println("bootstrap.type=" + constructed.type());

        Function<String, String> lambda =
                text -> text.toUpperCase(Locale.ROOT);
        check("ABC".equals(lambda.apply("abc")), "lambda");
        System.out.println("lambda.output=" + lambda.apply("abc"));
        String name = "Mia";
        int number = 7;
        String concat = name + "#" + number;
        check("Mia#7".equals(concat), "concat");
        System.out.println("concat.output=" + concat);
        System.out.println("checks=PASS");
    }
}
```

### 13.2. Lệnh biên dịch, chạy và xem bytecode

```bash
javac -encoding UTF-8 CallSiteIndyDemo.java
java CallSiteIndyDemo
javap -c -v CallSiteIndyDemo
```

Các lệnh này **đã được chạy thành công** với JDK 17+. `javap -c -v` in thông tin constant pool, code và `BootstrapMethods`. Output đầy đủ của `javap` rất dài, thay đổi theo compiler; không ghi cứng từng constant-pool index hoặc bytecode offset.

### 13.3. Stdout chính xác của `java CallSiteIndyDemo` đã kiểm chứng

```text
constant.value=hello:Ada
constant.relinkRejected=true
mutable.before=hello:Ada
mutable.after=goodbye:Ada
mutable.savedOldTarget=hello:Ada
mutable.wrongTypeRejected=true
mutable.uninitializedThrows=true
mutable.initialized=hello:Ada
volatile.before=hello:Ada
volatile.otherThreadAfterUpdate=goodbye:Ada
bootstrap.manualCallSite=hello:Bao
bootstrap.type=(String)String
lambda.output=ABC
concat.output=Mia#7
checks=PASS
```

Chương trình chạy **exit code 0** và in `checks=PASS`. Đây là dữ liệu test thực tế trên JDK trong môi trường chạy bài, không phải stdout phỏng đoán.

### 13.4. Đọc kết quả của `ConstantCallSite`

`constant.value=hello:Ada` vì target ban đầu trỏ tới `hello(String)`. Khi gọi `constant.setTarget(goodbye)`, API ném `UnsupportedOperationException`, nên in `constant.relinkRejected=true`. Điều này minh họa **liên kết cố định ở level CallSite**, không ngăn method target đọc tham số bất kỳ.

### 13.5. Đọc kết quả của `MutableCallSite`

`mutable.before=hello:Ada` và `mutable.after=goodbye:Ada` cho thấy **cùng dynamic invoker** đã chuyển từ target cũ sang target mới. `mutable.savedOldTarget=hello:Ada` minh họa một `MethodHandle` đã lưu từ `getTarget()` **không tự đổi** theo CallSite.

`mutable.wrongTypeRejected=true` là kết quả từ việc thử chuyển sang handle kiểu `(int)int`. `mutable.uninitializedThrows=true` chứng minh constructor nhận MethodType ban đầu tạo target ném lỗi nếu chưa khởi tạo.

### 13.6. Đọc kết quả của `VolatileCallSite`

Worker thread chờ một latch rồi gọi `volatileSite.dynamicInvoker()` sau khi main đã `setTarget(goodbye)`. Kết quả `volatile.otherThreadAfterUpdate=goodbye:Ada`.

**Không được khẳng định test này riêng rẽ chứng minh chính xác hiệu ứng volatile:** bài test cũng sử dụng `CountDownLatch` để tạo thứ tự chạy và memory visibility. **Bảo đảm volatile đến từ Javadoc và Java Memory Model**, còn chương trình xác minh API và một tình huống thread coordination hợp lệ.

### 13.7. Đọc kết quả `bootstrap.manualCallSite`

`manualBootstrap(...)` tạo một `ConstantCallSite` rồi Java code gọi `constructed.dynamicInvoker()`, trả `hello:Bao`. Dòng này minh họa bootstrap **trả một CallSite đúng type**. **Đây không phải một instruction JVM `invokedynamic` tự viết**.

### 13.8. Tại sao `lambda.output` và `concat.output` xuất hiện?

Hai tính năng của ngôn ngữ Java được compiler JDK 17 sử dụng để tạo bytecode gọi động. Kết quả:
- `lambda.output=ABC`.
- `concat.output=Mia#7`.

Không suy từ hai kết quả stdout rằng bytecode chắc chắn chứa `invokedynamic`; cần **`javap`** kiểm chứng class file. Việc kiểm tra `javap` dưới đây chính là bằng chứng đó.

## 14. Dùng `javap -c -v` để thấy invokedynamic thật

Sau khi biên dịch:

```bash
javap -c -v CallSiteIndyDemo
```

Hãy tìm:
- Dòng opcode **`invokedynamic`** trong phần `Code`.
- `InvokeDynamic` entries trong constant pool.
- `BootstrapMethods` attribute.
- Một bootstrap method handle tên **`LambdaMetafactory.metafactory`** cho lambda.
- Một bootstrap method handle tên **`StringConcatFactory.makeConcatWithConstants`** cho phép nối chuỗi.

Môi trường kiểm thử đã xác nhận:

```text
javap.invokedynamicPresent=true
javap.lambdaBootstrapPresent=true
javap.stringConcatBootstrapPresent=true
```

Ba dòng này là **tóm tắt boolean do lệnh PowerShell kiểm tra output `javap`**, không phải output gốc của `javap` và không phải phần stdout của chương trình Java. Kết quả dựa trên class file được biên dịch trong môi trường thử nghiệm. Constant-pool indices, tên synthetic methods và số lượng opcode có thể đổi giữa compiler/JDK versions.

### 14.1. Vì sao Java demo có MethodHandle mà vẫn phải xem bytecode?

Lời gọi:

```java
String x = (String) someHandle.invokeExact("Ada");
```

không giống một instruction `invokedynamic` do mình tự viết. `invokeExact` là method *signature-polymorphic* đặc biệt, và bytecode callsite có semantics riêng; **chỉ thao tác với đối tượng `MethodHandle`/`CallSite` ở Java source không tự chèn opcode invokedynamic**.

Trong class demo, bằng chứng `invokedynamic` đến từ những phép xây **lambda** và **string concatenation** mà compiler biến đổi. Phân biệt này giúp không nhầm một mô phỏng runtime linkage với việc đã tạo custom indy bytecode.

### 14.2. Vì sao số lượng opcode không là tiêu chí QA?

Việc Java source có nhiều phép `String + ...` trong các câu `System.out.println` cũng có thể tạo thêm invokedynamic string concatenation. Đếm opcode/indices không phải một phần cố định của ngôn ngữ Java. QA nên kiểm tra **có sự xuất hiện của instruction và bootstrap phù hợp**, không assert số lượng 38 hay một offset cụ thể qua mọi phiên bản JDK.

## 15. Những lỗi loại và lỗi liên kết thường gặp

### 15.1. `WrongMethodTypeException` lúc relink

`MutableCallSite` có type cố định, ví dụ `(String)String`. Chuyển target thành `(int)int` ném `WrongMethodTypeException`:

```java
try {
    mutable.setTarget(intTarget); // intTarget: (int)int
} catch (WrongMethodTypeException expected) {
    // Target không cùng MethodType.
}
```

Đây là snippet, các biến được tạo trong chương trình chính. Cần dùng MethodHandle có `type()` đúng, hoặc dùng adaptation hợp lệ như `asType` để target mới mang chữ ký site đòi hỏi.

### 15.2. `invokeExact` và expected return type

`invokeExact` có cơ chế match descriptor mạnh. Trong Java, biểu thức:

```java
String result = (String) invoker.invokeExact("Ada");
```

mang expected return `String`. Gọi dưới dạng `Object` hoặc không capture return như cùng một chữ ký có thể tạo một descriptor khác và dẫn đến `WrongMethodTypeException`. Không sửa bằng việc truyền `null` hoặc ép cast vô tội vạ.

### 15.3. `NoSuchMethodException` / `IllegalAccessException`

`Lookup.findStatic/findVirtual` đòi tên, type, access quyền hợp lệ. Xem:
- Static vs instance method handle type.
- Primitive vs wrapper types.
- Quy tắc `private/protected/package/public`.
- Java module exports/opens và caller lookup privileges.
- Khả năng nhìn thấy declaring class từ module/classloader.

### 15.4. `BootstrapMethodError`

Khi JVM không link được một `invokedynamic` vì bootstrap thất bại hoặc trả CallSite sai, lỗi có thể xuất hiện dưới dạng `BootstrapMethodError`. Trong code generator/bytecode tooling, kiểm tra `BootstrapMethods` attribute, constant pool descriptors, static args và bootstrap signature, thay vì chỉ nhìn stack trace ở target.

### 15.5. `IllegalStateException` với blank CallSite

`MutableCallSite(MethodType)` hoặc `VolatileCallSite(MethodType)` ban đầu chứa một target ném `IllegalStateException`. Hãy `setTarget` tới handle hợp lệ **trước khi điểm gọi được thực thi**.

### 15.6. Không lẫn các lỗi với vấn đề classloader

Trong hệ thống plugins/dynamic loaders, các class có cùng tên nhưng do hai classloaders khác nhau định nghĩa vẫn là **hai types khác nhau**. Một `MethodType` mang `Class<?>` identity thật, không chỉ chuỗi tên class; lookup/linkage cần đúng loader/module context.

## 16. Concurrency: thay target và quan sát giữa threads

### 16.1. MutableCallSite không bảo đảm nhìn thấy cập nhật nếu thiếu synchronization

Không đúng:

```java
// Thread A:
mutable.setTarget(newTarget);

// Thread B:
while (true) {
    mutable.dynamicInvoker().invokeExact(...);
    // Không có synchronization; không bảo đảm nhanh thấy target mới.
}
```

Đây là **pseudocode phản ví dụ**, không phải chương trình Java biên dịch nguyên xi. Với Java Memory Model, `MutableCallSite` target là ordinary field; thread B có thể tiếp tục dùng cached target. Thực tế có thể nhìn thấy update sớm, nhưng không có guarantee dùng được để xây giao thức dừng/đổi rule.

### 16.2. Khi cần công bố cập nhật qua MutableCallSite

Dùng:

```java
mutable.setTarget(newTarget);
MutableCallSite.syncAll(new MutableCallSite[]{mutable});
```

Phối hợp các writers theo cùng protocol/mutual exclusion; không gọi `syncAll` trong hot loop trên mọi request nếu không có lý do. `syncAll` không hủy old in-flight call, không là transaction nguyên tử qua nhiều sites.

### 16.3. Khi dùng VolatileCallSite

`VolatileCallSite.setTarget` có hiệu ứng volatile write, `getTarget` tương ứng volatile read. Nếu cập nhật đích thường xuyên hoặc yêu cầu readers kịp nhận target mới, đây là lựa chọn có memory semantics mạnh hơn. Tuy nhiên thay target không đồng bộ mọi side effect của target method bên trong; shared state khác vẫn phải tuân thủ JMM.

### 16.4. Bất biến nhiều CallSites

Giả sử dispatcher có hai call sites cần thay đồng bộ vì một business rule gồm hai phần. Gọi `setTarget` trên site A rồi B không bảo đảm một reader luôn thấy “cả A mới + B mới”. `MutableCallSite.syncAll` cũng không trở thành multi-object atomic transaction. Nếu invariant yêu cầu cả hai thay đồng thời, thiết kế một immutable dispatch table/snapshot và chuyển atomic reference ở một vị trí, hoặc một khóa/giao thức version phù hợp.

## 17. CallSite giúp gì cho runtime, và không giúp gì?

### 17.1. Mục đích đáng dùng

- **Ngôn ngữ động trên JVM:** compiler/runtime có thể chọn target theo kiểu runtime và tối ưu hóa dispatch.
- **Biểu thức lambda/method references:** metafactory liên kết factory của function object.
- **String concatenation trong Java 9+:** bootstrap chuẩn bị đường nối chuỗi phù hợp với call descriptor.
- **Framework/code generator có dynamic linkage:** nếu đã có compiler/bytecode tooling và có yêu cầu hiệu năng/thay đổi target rõ.

### 17.2. Nó không tự làm

- Không cho phép bypass security/module checks.
- Không đảm bảo runtime tự cập nhật target theo từng request nếu code không thiết kế lại target.
- Không biến một `MethodHandle` có signature sai thành tương thích.
- Không làm mọi target method thread-safe.
- Không cung cấp durability/transaction/business rollback khi relink.
- Không bắt buộc mỗi lần gọi chạy lại bootstrap method.
- Không bảo đảm luôn nhanh hơn trực tiếp `invokevirtual`/`invokestatic`; JVM có thể tối ưu hóa tùy tình huống.

### 17.3. Lựa chọn thay thế cho ứng dụng thường ngày

Nếu chỉ cần inject một hành vi và chuyển logic đơn giản, **functional interfaces**, strategy objects, ordinary polymorphism hoặc `Map<Key,Handler>` thường dễ hiểu và dễ debug hơn. Không nên đưa `CallSite` vào mọi service chỉ vì nó “động”.

## 18. Những nhầm lẫn hay gặp

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| “CallSite là MethodHandle.” | CallSite **chứa** target MethodHandle, có type và lifecycle linkage |
| “invokedynamic gọi bootstrap mỗi lần.” | Bootstrap dùng để link; execution sau dùng CallSite target |
| “Chỉ tạo new CallSite trong Java là đã phát opcode invokedynamic.” | Free-floating CallSite không tự tạo bytecode instruction |
| “getTarget và dynamicInvoker luôn là một.” | Saved getTarget có thể giữ target cũ; dynamicInvoker theo current target |
| “ConstantCallSite target có thể set bằng reflection.” | API không cho đổi, `setTarget` UnsupportedOperationException |
| “MutableCallSite.setTarget làm các threads thấy ngay.” | Không có volatile guarantee; dùng `syncAll` hoặc sync khác |
| “MutableCallSite.syncAll hủy mọi old calls.” | Những lời gọi đã bắt đầu trên old target vẫn có thể hoàn tất |
| “syncAll đổi nhiều sites atomically.” | Không, không phải multi-site transaction |
| “VolatileCallSite tự thread-safe hóa target method.” | Nó chỉ đồng bộ target reference theo volatile semantics |
| “Relink được target sang mọi chữ ký.” | Site `type()` không đổi; mismatch dẫn đến WrongMethodTypeException |
| “Blank MutableCallSite(MethodType) có sẵn method hữu ích.” | Initial target ném IllegalStateException |
| “invokeExact tự ép mọi kiểu.” | InvokeExact đòi descriptor khớp chính xác |
| “Lambda là Java 7.” | invokedynamic/CallSite từ Java 7, lambda Java 8 |
| “StringConcatFactory có từ Java 7.” | String concat factory được đưa vào về sau, được JDK 17 sử dụng |
| “Có stdout đúng thì đã chứng minh bytecode dùng indy.” | Cần kiểm tra `javap`/class file |
| “Custom bootstrap luôn chỉ chạy đúng một lần dưới mọi race.” | Resolution có quy tắc cạnh tranh; tránh side effects dựa call count |
| “Java source có keyword invokedynamic.” | Nó là JVM bytecode instruction, không phải Java statement |
| “MethodHandles có thể vượt quyền module tùy ý.” | Lookup và module access controls vẫn áp dụng |
| “Mọi JDK biên dịch concat giống nhau.” | Bytecode strategy có thể thay đổi theo compiler/release |

## 19. Kiểm thử và QA

### 19.1. Test contract của từng CallSite

| Test | Kỳ vọng |
| --- | --- |
| ConstantCallSite target String→String | `dynamicInvoker.invokeExact` trả kết quả của target cố định |
| ConstantCallSite.setTarget | UnsupportedOperationException |
| MutableCallSite trước relink | Target ban đầu |
| MutableCallSite sau setTarget + syncAll | Dynamic invoker gọi target mới |
| Saved handle từ getTarget trước relink | Vẫn gọi method cũ |
| Thay target khác type | WrongMethodTypeException |
| MutableCallSite(MethodType) trước setTarget | IllegalStateException khi invoke |
| MutableCallSite sau setTarget đúng type | Gọi thành công |
| VolatileCallSite setTarget | Target mới đọc theo volatile semantics |
| Manual bootstrap | Trả CallSite đúng MethodType |
| Java lambda | Function object hoạt động đúng |
| String concat | Java source semantics đúng |
| `javap -c -v` | Có `invokedynamic`, `BootstrapMethods`, LambdaMetafactory và StringConcatFactory |
| Bootstrap fail | Lỗi linkage được xử lý theo JVM/JDK contract |
| Multi-thread target updates | Sử dụng syncAll/volatile hoặc protocol khác |
| Multi-site rule changes | Không dựa vào atomicity mặc định |

### 19.2. Dùng JDK tool đúng mục tiêu

- `javac -encoding UTF-8 ...` kiểm tra cú pháp/tên class/type.
- `java ...` kiểm tra hành vi observable của demo.
- `javap -c -v ...` xem bytecode, constant pool, bootstrap method references.
- Xem thêm `javap -p` nếu muốn nhìn synthetic implementation methods trong class.
- Dùng `-Xlog` hoặc JVM diagnostic flags chỉ khi thực sự cần; không dựa vào flags nội bộ/không ổn định của một runtime làm hướng dẫn cốt lõi cho module Java 17+.

### 19.3. Không dùng benchmark làm proof về semantics

JIT compilation, inlining, call-site relinking và CPU/cache effects có thể thay đổi hiệu năng mạnh giữa các phiên bản. Một microbenchmark tự viết bằng `System.nanoTime` không chứng minh `ConstantCallSite` luôn nhanh hơn `VolatileCallSite`. Nếu cần đo, dùng công cụ benchmark phù hợp và quan sát workload thật, không chuyển kết quả một máy thành bảo đảm API.

### 19.4. Test đồng thời nên có deadline

Đừng viết `while(!seenUpdate){}` để xác minh visibility. Trong demo, `CountDownLatch` và `Future.get(timeout)` kiểm soát lúc worker chạy và kết thúc; `ExecutorService.shutdownNow` cùng `awaitTermination` dọn threads. Một test mãi không kết thúc làm CI treo và không chứng minh được JMM contract.

## 20. FAQ

**1. `CallSite` là gì?**  
Là object chứa target `MethodHandle` của một điểm gọi động và có method type cố định.

**2. `invokedynamic` là gì?**  
Là JVM bytecode instruction liên kết hành vi điểm gọi bằng bootstrap method trả `CallSite`.

**3. Có thể tạo `CallSite` mà không có `invokedynamic` không?**  
Có. Đó là free-floating CallSite; gọi qua `dynamicInvoker` từ Java.

**4. Mọi lần invokedynamic có gọi bootstrap không?**  
Không. Bootstrap phục vụ linkage, các lần gọi sau sử dụng site đã được link.

**5. `ConstantCallSite` có đổi target được không?**  
Không. `setTarget` luôn UnsupportedOperationException.

**6. `MutableCallSite` có đổi target được không?**  
Có nếu MethodType khớp; để công bố đáng tin cho threads khác dùng `syncAll`/synchronization phù hợp.

**7. `VolatileCallSite` khác gì?**  
Target có volatile memory semantics, phù hợp khi cần các threads thấy cập nhật trực tiếp.

**8. Vì sao `type()` bất biến?**  
Vì chữ ký invokedynamic/site được cố định ở linkage; target phải tương thích với method descriptor.

**9. `dynamicInvoker()` khác `getTarget()` thế nào?**  
Dynamic invoker chuyển tới target hiện tại; một MethodHandle đã lưu từ getTarget có thể tiếp tục gọi target cũ.

**10. MethodHandle có giống Java reflection không?**  
Cùng có thể tham chiếu method nhưng API, kiểu gọi, access checks và tối ưu hóa khác nhau; không đồng nhất chúng.

**11. Có thể dùng `invokeExact` mà không xử lý Throwable không?**  
Không thể bỏ qua checked Throwable của MethodHandle invocation trong code được compile, trừ khi method khai báo/handling thích hợp.

**12. Lambda có dùng invokedynamic không?**  
Compiler Java hiện đại thông thường sử dụng LambdaMetafactory và invokedynamic cho lambda/method reference; xác minh bằng javap.

**13. String concat có dùng invokedynamic không?**  
Trong JDK 17 `javac` thường có, thông qua StringConcatFactory; phép nối toàn hằng số có thể bị constant-fold.

**14. Bootstrap method có bắt buộc nhận ba parameters đầu không?**  
Mô hình phổ biến dùng Lookup, String, MethodType cùng static args bổ sung tùy CallSite; JVM bootstrap linkage có quy tắc về signature/adaptation.

**15. Tại sao `BootstrapMethodError` xuất hiện?**  
Khi JVM linkage qua bootstrap không thành công theo contract, ví dụ bootstrap ném lỗi hoặc trả kết quả không hợp lệ.

**16. `syncAll` có làm update atomically qua nhiều CallSites không?**  
Không. Nó phục vụ công bố target values chứ không là transaction đa site.

**17. Có nên dùng CallSite cho ứng dụng CRUD thông thường không?**  
Thường không cần. Dùng methods, interfaces và ordinary dispatch trước, chỉ chọn dynamic linkage nếu có nhu cầu rõ.

**18. Các API này có lỗi thời trong Java 17+ không?**  
Không. `java.lang.invoke`, CallSite và invokedynamic vẫn là hạ tầng quan trọng của JVM hiện đại.

## 21. Checklist thiết kế và code review

- [ ] Đã phân biệt `MethodHandle`, `MethodType`, `CallSite` và `invokedynamic`.
- [ ] CallSite target có signature chính xác với site `type()`.
- [ ] `Lookup` được tạo ở đúng context và không vi phạm access controls.
- [ ] Nếu target không đổi, xem `ConstantCallSite`.
- [ ] Nếu target đổi hiếm và có sync control, xem `MutableCallSite` và `syncAll`.
- [ ] Nếu cần volatile visibility, xem `VolatileCallSite`.
- [ ] Không giả định `MutableCallSite.setTarget` tự khiến mọi thread thấy cập nhật.
- [ ] Không dùng `syncAll` như atomic transaction đa site.
- [ ] Không tưởng in-flight calls tự dừng khi thay target.
- [ ] Không lưu `getTarget()` rồi mong handle cũ đổi theo site.
- [ ] Nếu dùng `invokeExact`, xác minh kiểu argument và return của call site Java.
- [ ] Với `MutableCallSite(MethodType)`, set target trước khi invoke.
- [ ] Validate bootstrap name/type/static args và kiểm tra null.
- [ ] Không dựa vào số lần bootstrap chạy cho external side effects.
- [ ] Không đưa `Lookup` có quyền quá rộng cho code không tin cậy.
- [ ] Phân biệt manual bootstrap invocation và JVM dynamic linkage.
- [ ] Nếu claim Java bytecode chứa indy, có `javap -c -v` evidence.
- [ ] Không assert constant pool indexes hoặc số lượng invokedynamic cố định giữa compilers.
- [ ] Kiểm tra runtime/driver không liên quan; demo dùng JDK 17+ thuần.
- [ ] Tests có deadlines, không busy-spin không kiểm soát.
- [ ] Đối với performance, đo thực tế thay vì suy từ tên class.
- [ ] Chỉ dùng kiến thức/API còn hiệu lực cho Java 17+.

## 22. Tổng kết và tài liệu chính thức Java 17

**Tóm tắt một câu:** `invokedynamic` là instruction cho phép JVM liên kết động một điểm gọi qua **bootstrap method**, kết quả là **`CallSite` giữ target `MethodHandle`** có chữ ký cố định.

Những điểm thực hành:
- `ConstantCallSite`: target cố định, không thể relink.
- `MutableCallSite`: target đổi được; `syncAll` giúp công bố tới readers khác theo contract.
- `VolatileCallSite`: target đổi được với volatile semantics.
- `getTarget` là snapshot handle; `dynamicInvoker` chuyển tiếp theo target hiện tại.
- Java 17 `javac` dùng invokedynamic cho lambda/method reference và nhiều biểu thức nối chuỗi.
- Người học có thể tự tạo CallSite để hiểu API, nhưng **chưa đồng nghĩa phát sinh một custom invokedynamic instruction**.
- Type checks, access control, thread visibility và lifecycle vẫn quan trọng khi xây runtime có dynamic dispatch.

### Tài liệu chính thức

- [Oracle Java SE 17 — `CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html): khái niệm, target, dynamic invoker, abstract contract.
- [`ConstantCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html): immutable target và UnsupportedOperationException.
- [`MutableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html): relink, ordinary field memory semantics, `syncAll`.
- [`VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): volatile target reads/writes.
- [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invoke`/`invokeExact` và signature-polymorphic behavior.
- [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): method descriptors.
- [`MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): quyền truy cập và factory các handles.
- [`LambdaMetafactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html): bootstrap lambda và method references.
- [`StringConcatFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html): bootstrap phép nối chuỗi.
- [Oracle Java SE 17 — JVM Support for Non-Java Languages](https://docs.oracle.com/en/java/javase/17/vm/support-non-java-languages.html): giải thích invokedynamic, bootstrap linking và CallSite.
- [JVMS Java SE 17 `5.4.3.6 — Dynamically-Computed Call Site](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6): resolution và linkage rules.
- [JVMS Java SE 17 `6.5 — invokedynamic](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic): instruction semantics.
