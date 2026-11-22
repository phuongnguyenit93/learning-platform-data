# 11.5 Vòng đời từ điểm gọi chưa liên kết tới `CallSite` đã được chọn

Một chỉ thị bytecode `invokedynamic` không được gắn sẵn với một method đích cố định như cách ta thường hình dung về `invokestatic` hay `invokevirtual`. Nó khởi đầu ở trạng thái **chưa liên kết (*unlinked*)**. Trước lần thực thi đầu tiên, JVM phải giải quyết thông tin ký hiệu của điểm gọi, gọi một **bootstrap method (BSM)** và lựa chọn một đối tượng `java.lang.invoke.CallSite` hợp lệ. Sau khi chọn, chỉ thị ấy được **gắn với chính `CallSite` đó**; các lần thực thi tiếp theo dùng target do `CallSite` cung cấp.

Đây là mô hình nền tảng của Java runtime động: lambda, method reference, nối chuỗi và các trình biên dịch ngôn ngữ động có thể để JVM quyết định cơ chế thực thi tại thời điểm **linkage**.

**Điểm phải phân biệt ngay:**

- **Liên kết (*link*)**: chọn **`CallSite`** nào được gắn với một chỉ thị `invokedynamic` cụ thể. Với mỗi chỉ thị, việc chuyển từ *unlinked* sang *linked* chỉ xảy ra một lần nếu thành công.
- **Dispatch (*invoke*)**: mỗi lần chạy chỉ thị đã link, lấy hành vi từ **target `MethodHandle`** của `CallSite` và gọi nó với các đối số runtime.
- **Relink target**: `MutableCallSite`/`VolatileCallSite` có thể **đổi target** mà **không chạy lại bootstrap và không chọn `CallSite` mới** cho chỉ thị ấy.

Bài dùng chuẩn **Java 17** và theo thuật ngữ của Java Virtual Machine Specification (JVMS). Những đoạn minh họa gắn nhãn giả mã không phải cú pháp Java có thể viết trực tiếp bằng `javac`.

## 1. Trước khi liên kết: class file đã biết những gì?

Khi biên dịch, class file có thể chứa một chỉ thị `invokedynamic` với một **chỉ số vào constant pool**. Entry `CONSTANT_InvokeDynamic_info` mô tả điểm gọi bằng:

1. **`bootstrap_method_attr_index`**: chọn một entry trong thuộc tính class-level `BootstrapMethods`. Entry này chỉ tới *bootstrap method handle* và danh sách **static arguments** (nếu có).
2. **`name_and_type_index`**: trỏ tới `CONSTANT_NameAndType_info`, chứa **tên của điểm gọi** và **method descriptor**: danh sách kiểu tham số cùng kiểu trả về.

Ví dụ dạng **sơ đồ**, không phải bytecode thực tế với chỉ số cố định:

~~~text
Method bytecode:
    invokedynamic #17, 0

Constant pool:
    #17 = InvokeDynamic #0 : applyAsInt:()Ljava/util/function/IntUnaryOperator;

BootstrapMethods:
    0: REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
       arguments: ... (method type, implementation handle, ...)

Ý nghĩa ở điểm gọi trên:
  name       = applyAsInt
  descriptor = ()IntUnaryOperator
  BSM        = LambdaMetafactory.metafactory
  static args = thông tin đã ghi trong class file
~~~

Số `#17`, số bootstrap entry và tên method sinh tự động **chỉ là ví dụ trình bày**; `javac` có thể tạo index khác. Lệnh `javap -v -p` sẽ cho thấy số index thực tế trên máy.

**Quan trọng:** Mô tả `()IntUnaryOperator` ở ví dụ lambda là **kiểu của chính điểm gọi tạo ra đối tượng function**: không có tham số và trả về `IntUnaryOperator`. Nó **khác** chữ ký của phương thức trừu tượng bên trong interface, chẳng hạn `applyAsInt(int) -> int`. Khi đọc disassembly, đừng nhầm kiểu của *call site factory* với kiểu SAM được bootstrap cấu hình.

Ở trạng thái unlinked, JVM có metadata để thực hiện linkage nhưng **chưa có `CallSite` được lựa chọn cho chỉ thị**; nó chưa có target cuối cùng để thực thi điểm gọi ấy.

## 2. Hai loại đối số: static bootstrap argument và runtime argument

Một lỗi tư duy phổ biến là cho rằng bootstrap phải nhận **dữ liệu nghiệp vụ của mỗi lần gọi**. Thực tế có hai luồng tách biệt:

| Loại dữ liệu | Nguồn | Khi nào sử dụng? | Dùng vào việc gì? |
| --- | --- | --- | --- |
| **Metadata linkage** | Lookup của caller, tên điểm gọi, `MethodType` và các static args trong class file | Trong quá trình link | BSM dùng để **chọn/thiết kế target** |
| **Đối số runtime** | Operand stack trước mỗi chỉ thị `invokedynamic` | **Mỗi lần** chạy chỉ thị sau khi link | Được chuyển cho **target của `CallSite`** |

Chữ ký bootstrap phổ biến ở Java:

~~~java
static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String invokedName,
        MethodType invokedType,
        Object... staticArguments) throws Throwable {
    // Lựa chọn và trả về CallSite có type() == invokedType.
}
~~~

Đây là **chữ ký minh họa**, chưa phải method đầy đủ. Với một BSM có 0 static argument, có thể bỏ tham số `Object...`; với những static argument đã biết kiểu, có thể dùng chữ ký tường minh.

Giải thích bốn loại thông tin:

- `caller` là `MethodHandles.Lookup` cho **class chứa điểm gọi**; cung cấp ngữ cảnh truy cập để bootstrap tìm method/field hợp lệ. Nó không có nghĩa “class của đối số runtime đầu tiên”.
- `invokedName` là **tên tượng trưng** mà compiler/generator gán cho điểm gọi. Nó không bắt buộc là tên một method Java đang tồn tại trên class đích.
- `invokedType` là kiểu **đầy đủ** của điểm gọi, bao gồm **tham số và kiểu trả về**. Target cuối cùng phải có kiểu tương đương chính xác về ngữ nghĩa.
- `staticArguments` là metadata do class file khai báo, chẳng hạn `MethodType`, `MethodHandle` và chuỗi hoặc hằng số khác, **không phải** dữ liệu mới từ caller ở mỗi lần chạy.

Theo JVMS, JVM chuẩn bị mảng logic `[caller, invokedName, invokedType, staticArg0, ...]`, rồi gọi bootstrap handle theo ngữ nghĩa của `MethodHandle.invokeWithArguments`. Do đó các kiểu tham số của BSM có thể linh hoạt hơn chữ ký gợi ý trên; không nhất thiết compiler phải tìm đúng một method Java với chữ ký `(Lookup,String,MethodType,Object[])CallSite`.

**Phân biệt `CONSTANT_Dynamic`:** dynamic constant cũng có bootstrap nhưng để **tính giá trị của một hằng**. Với `invokedynamic`, bootstrap phải cung cấp một **`CallSite`**. Trong trường hợp constant bootstrap, tham số thứ ba là `Class<?>` đại diện kiểu trường, không phải `MethodType` của điểm gọi.

## 3. Sơ đồ vòng đời một chỉ thị `invokedynamic`

~~~text
[Class file chứa invokedynamic + symbolic reference]
                         │
                         ▼
                [UNLINKED CALL SITE]
                         │
             chuẩn bị cho lần thực thi đầu
                         │
                         ▼
        [Resolve BSM handle + call-site MethodType
                    + static args]
                         │
                         ▼
             [Invoke bootstrap method]
                         │
              trả về một đối tượng
                         ▼
        [Validate: non-null CallSite,
           CallSite.type() == descriptor?]
                 │                 │
              Hợp lệ           Không hợp lệ
                 │                 │
                 ▼                 ▼
        [JVM chọn 1 CallSite]  [Linkage failure]
                 │             (ví dụ BME)
                 ▼
      [Bind CallSite vào CHỈ THỊ này]
                 │
                 ▼
      [Đọc current target MethodHandle]
                 │
                 ▼
        [Gọi target với runtime args]
                 │
                 ▼
     [Các lần sau: bỏ qua bootstrap,
      dùng CallSite đã gắn và target
       hiện hành của nó]
~~~

Đây là mô hình logic theo đặc tả, **không phải** lời hứa về một chuỗi lệnh máy cố định. JVM có thể tối ưu, inline hoặc lưu trạng thái link bằng cơ chế nội bộ khác, miễn giữ đúng hành vi quan sát được.

### Giai đoạn A — resolve metadata

JVM giải quyết bootstrap `MethodHandle`, kiểu call site từ method descriptor và các static argument. Việc resolve có thể kéo theo việc load class, kiểm tra quyền truy cập, resolve method type/method handle hoặc khởi tạo class cần thiết để gọi bootstrap.

Thứ tự xử lý static args do class file xác định. Nếu một tham chiếu method/type không resolve được, quá trình liên kết có thể thất bại **trước** khi method body của BSM thực sự chạy.

### Giai đoạn B — chạy bootstrap

BSM nhận các thông tin **tĩnh** và tạo ra một `CallSite`. BSM thường làm việc như:

1. Dùng `caller.findStatic`/`findVirtual` hay các API của `MethodHandles` để lấy target ban đầu.
2. Nếu cần, ghép adapter bằng `asType`, `bindTo`, `filterArguments`, `guardWithTest` hoặc các combinator khác.
3. Trả một loại `CallSite` phù hợp: `ConstantCallSite`, `MutableCallSite` hoặc `VolatileCallSite`.

BSM **có thể chạy mã tùy ý** và có thể có tác dụng phụ; không nên giả định nó tự động tinh khiết hoặc miễn phí. Tuy nhiên không được đặt logic nghiệp vụ cần thực hiện *mỗi lần call* vào BSM, vì sau linkage bình thường BSM không được gọi lại cho chỉ thị ấy.

### Giai đoạn C — xác thực và chọn `CallSite`

Một kết quả được chấp nhận chỉ khi:

- Không phải `null`.
- Là một thể hiện của `java.lang.invoke.CallSite` (hoặc lớp con).
- `CallSite.type()` **bằng method descriptor của điểm gọi** theo ngữ nghĩa kiểu JVM. Nói cách khác, target có đúng danh sách tham số và kiểu trả về. Không có “tự thích nghi” kiểu tùy tiện *sau khi* chọn site.

Nếu bootstrap trả `null`, trả đối tượng không phải `CallSite`, hoặc trả site có kiểu khác descriptor, linkage thất bại, thông thường với `BootstrapMethodError`. Một method `(String)String` không thể làm target cho điểm gọi `(int)int` chỉ vì tên giống nhau.

### Giai đoạn D — binding và thực thi

JVM liên kết **chỉ thị `invokedynamic` cụ thể** với `CallSite` được chọn. Sau đó, các đối số runtime theo call-site descriptor được chuyển tới **target `MethodHandle`** như một lời gọi kiểu `invokeExact`.

Nếu target là một chuỗi adapter dài, nó có thể thực hiện nhiều phép biến đổi trước hoặc sau method đích; những bước đó là **hành vi target**, không phải JVM chạy BSM lại.

**Một ranh giới quan trọng:** target ban đầu có thể chọn thay đổi được; **đối tượng `CallSite` được gắn với chỉ thị** thì không bị thay mới bởi chính chỉ thị sau khi đã liên kết thành công.

## 4. “Bootstrap chỉ gọi một lần” cần hiểu chính xác

Câu rút gọn “BSM chỉ chạy một lần” hữu ích trong ví dụ đơn luồng, nhưng **không phải** bảo đảm tổng số lần gọi BSM trên toàn bộ chương trình luôn đúng bằng một.

### 4.1. Linkage thuộc về một **vị trí chỉ thị**

Hai chỉ thị `invokedynamic` trong cùng class có thể trỏ tới **cùng một entry constant pool**; vẫn phải giải quyết linkage cho **từng chỉ thị**. Nếu BSM tự trả cùng một đối tượng `CallSite` cho hai vị trí, chúng có thể chia sẻ đối tượng đó; **JVM không mặc định gộp hai vị trí thành một lần liên kết**.

Hệ quả:

- Một method chứa một chỉ thị `invokedynamic` có thể được gọi nhiều lần; sau lần liên kết thành công, chỉ thị ấy **không được liên kết lại** chỉ vì method chạy thêm lần nữa.
- Hai vị trí gọi riêng có thể dẫn tới **hai quá trình liên kết riêng**, ngay cả khi BSM giống nhau.
- Hai class có bytecode tương tự nhưng được nạp bởi class loader khác nhau có state liên kết riêng. Không suy số lần liên kết từ **số class lambda được sinh** hoặc **số object function được tạo**.

### 4.2. Nhiều thread cạnh tranh ở lần chạy đầu

Theo JVMS Java 17, khi nhiều thread cùng thử đi vào một chỉ thị chưa liên kết:

- Bootstrap **có thể** được gọi **đồng thời nhiều lần** cho cùng một điểm gọi.
- JVM chọn **một** kết quả hợp lệ để **cài đặt và công bố** cho mọi thread.
- Các kết quả BSM còn lại được phép hoàn thành nhưng **không được chọn** làm binding cuối cùng.

Vì vậy, BSM có side effect (tăng counter, ghi log, mở resource, đăng ký handler) cần được thiết kế **an toàn khi cạnh tranh**, và không nên xem “đếm số lần BSM chạy” là phép đo chắc chắn cho “bao nhiêu CallSite đã được cài đặt”.

Sơ đồ:

~~~text
Thread T1 ─┐
           ├──> BSM(...) --> CallSite A ──┐
Thread T2 ─┘                              ├── JVM chọn đúng 1 binding
               BSM(...) --> CallSite B ──┘

Sau đó: mọi lần thực thi chỉ thị dùng CallSite đã chọn,
không chạy lại BSM để "bốc thăm" lần nữa.
~~~

### 4.3. Cache cả thành công lẫn thất bại

Với **một chỉ thị cụ thể**, sau liên kết thành công, các lần resolve tiếp theo trả về **cùng đối tượng đã gắn** mà không gọi lại BSM.

Nếu quá trình resolve của chỉ thị ấy **thất bại**, những lần thử lại bởi **chính chỉ thị ấy** tiếp tục thất bại với **cùng lỗi resolution**; bootstrap không được chạy lại như một cơ chế retry tự động. Chỉ thị `invokedynamic` **khác** (dù trỏ tới cùng constant pool entry) vẫn có thể được resolve độc lập.

Không nên dùng `invokedynamic` như một “retry loop” cho bootstrap ném lỗi do cấu hình hoặc kết nối tạm thời. Nếu cần thay đổi chiến lược sau khi đã liên kết, thiết kế target thích hợp bên trong `MutableCallSite`/`VolatileCallSite`, hoặc chủ động làm logic retry ở tầng nghiệp vụ.

## 5. Site đã chọn không đồng nghĩa target luôn bất biến

`CallSite` giữ một target `MethodHandle`, và ba biến thể Java 17 có quy tắc khác nhau:

| Biến thể | Sau liên kết có đổi target không? | Tác dụng |
| --- | --- | --- |
| `ConstantCallSite` | **Không** | Target cố định; phù hợp đường gọi ổn định, tối ưu hiệu quả |
| `MutableCallSite` | **Có** qua `setTarget` | Target có semantics như field thường; muốn các thread khác quan sát cập nhật nhất quán, dùng cơ chế đồng bộ thích hợp như `MutableCallSite.syncAll` |
| `VolatileCallSite` | **Có** qua `setTarget` | Target có semantics của biến `volatile`; thread khác thấy thay đổi theo quy tắc volatile, có thể phát sinh chi phí đồng bộ cao hơn |

Các loại site trên có `type()` cố định sau khi tạo. Nếu đổi target từ `(int)int` sang `(String)String`, `setTarget` ném `WrongMethodTypeException`; muốn thay một logic khác, phải đưa vào **`MethodHandle` cùng kiểu**, chẳng hạn sau khi tự tạo adapter tương thích.

`CallSite.dynamicInvoker()` trả một handle giúp **gọi target hiện hành của site**, có hành vi tương đương một điểm gọi đã gắn với site đó. Với site mutable/volatile, handle này quan sát việc thay target theo semantics tương ứng. **Nhưng gọi `dynamicInvoker()` trực tiếp trong Java không tạo ra một chỉ thị `invokedynamic` mới và không kích hoạt bootstrap**.

Phân biệt rõ hai khái niệm:

~~~text
Binding:
    invokedynamic instruction ──> chosen CallSite  [không đổi]

Dispatch:
    chosen CallSite ──> current MethodHandle target [có thể đổi]
                                │
                                ▼
                             thực thi
~~~

Do đó “liên kết lại target” là một cách nói về **thay target bên trong một site đã gắn**, không phải “JVM quay lại trạng thái unlinked và chạy lại BSM”.

## 6. Ví dụ đầy đủ Java 17: có `invokedynamic` thật và site có thể đổi target

Để có ví dụ **chạy được chỉ bằng Java source**, ta dùng một lambda: `javac` trên Java 17 phát sinh `invokedynamic` để xây đối tượng triển khai functional interface. Sau đó ta **tạo `CallSite` thủ công** để quan sát trạng thái target. Hai phần được **phân tách có chủ đích**:

- **Phần lambda:** có `invokedynamic` thật trong bytecode, do compiler tạo; BSM là `LambdaMetafactory.metafactory` trong cấu hình thông thường.
- **Phần `CallSite` tạo thủ công:** minh họa target cố định và có thể thay, **không** phải JVM liên kết một chỉ thị `invokedynamic` mới. Các lời gọi thông qua `dynamicInvoker()` là `MethodHandle` invocation thông thường.

Tạo file **`IndyLifecycleDemo.java`**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.VolatileCallSite;
import java.lang.invoke.WrongMethodTypeException;
import java.util.function.IntUnaryOperator;

public final class IndyLifecycleDemo {
    static IntUnaryOperator factory() {
        return x -> x + 1;
    }

    static int plusTen(int x) { return x + 10; }
    static int timesTen(int x) { return x * 10; }

    public static void main(String[] args) throws Throwable {
        IntUnaryOperator a = factory();
        IntUnaryOperator b = factory();
        System.out.println("lambda a(3): " + a.applyAsInt(3));
        System.out.println("lambda b(5): " + b.applyAsInt(5));

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(int.class, int.class);
        MethodHandle first = lookup.findStatic(IndyLifecycleDemo.class, "plusTen", type);
        MethodHandle second = lookup.findStatic(IndyLifecycleDemo.class, "timesTen", type);

        CallSite constant = new ConstantCallSite(first);
        System.out.println("constant site type: " + constant.type());
        System.out.println("constant invoker(2): " + (int) constant.dynamicInvoker().invokeExact(2));

        MutableCallSite mutable = new MutableCallSite(first);
        MethodHandle dynamic = mutable.dynamicInvoker();
        System.out.println("mutable before(2): " + (int) dynamic.invokeExact(2));
        mutable.setTarget(second);
        MutableCallSite.syncAll(new MutableCallSite[] { mutable });
        System.out.println("mutable after(2): " + (int) dynamic.invokeExact(2));

        VolatileCallSite volatileSite = new VolatileCallSite(first);
        MethodHandle volatileInvoker = volatileSite.dynamicInvoker();
        System.out.println("volatile before(2): " + (int) volatileInvoker.invokeExact(2));
        volatileSite.setTarget(second);
        System.out.println("volatile after(2): " + (int) volatileInvoker.invokeExact(2));

        try {
            mutable.setTarget(MethodHandles.constant(String.class, "wrong"));
        } catch (WrongMethodTypeException expected) {
            System.out.println("bad target type: " + expected.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 IndyLifecycleDemo.java
java IndyLifecycleDemo
~~~

**Stdout chính xác:**

~~~text
lambda a(3): 4
lambda b(5): 6
constant site type: (int)int
constant invoker(2): 12
mutable before(2): 12
mutable after(2): 20
volatile before(2): 12
volatile after(2): 20
bad target type: WrongMethodTypeException
~~~

Ý nghĩa từng phần:

1. `factory()` có **một vị trí `invokedynamic`** để sản xuất `IntUnaryOperator`. Ta gọi `factory` hai lần nhưng không kết luận rằng BSM chạy hai lần; quá trình link thuộc về **vị trí bytecode**, không thuộc về mỗi object `IntUnaryOperator`.
2. `ConstantCallSite(first)` giữ target `plusTen(int)` cố định, nên `2 → 12`. Đoạn này không nằm trong bootstrap thực của lambda.
3. `MutableCallSite(first)` ban đầu thực thi `plusTen`. Sau `setTarget(second)` và `syncAll`, chính handle `dynamic` đã lấy trước đó thực thi `timesTen`, nên `2 → 20`. **Site không đổi**, chỉ target đổi.
4. `VolatileCallSite` cho phép thay target với ngữ nghĩa bộ nhớ `volatile` mà không gọi `syncAll`.
5. Một target có kiểu `()String` do `MethodHandles.constant(String.class, "wrong")` tạo ra không phù hợp với site kiểu `(int)int`. `WrongMethodTypeException` được ném **ngay khi gọi `setTarget`**.

Tại đây, **không có BSM custom** được trình diễn để tránh làm người học nhầm `new ConstantCallSite(...)` với hành động JVM resolve một chỉ thị. Để hiểu BSM thật được compiler chọn, dùng `javap` ở bước kế.

## 7. Dùng `javap` nhìn phần *unlinked descriptor* và bootstrap metadata

Sau khi biên dịch, chạy:

~~~bash
javap -c -p IndyLifecycleDemo
javap -v -p IndyLifecycleDemo
~~~

Ở output của `javap -c -p`, tìm method `factory`. Với `javac --release 17`, phương thức có cấu trúc sau (lược số index, không coi đây là stdout bytecode hoàn chỉnh):

~~~text
static java.util.function.IntUnaryOperator factory();
  Code:
     0: invokedynamic ... // applyAsInt:()Ljava/util/function/IntUnaryOperator;
     5: areturn
~~~

Tại `javap -v -p`, kiểm tra hai phần riêng:

1. **`Constant pool`** có entry `InvokeDynamic` cho điểm gọi `applyAsInt:()Ljava/util/function/IntUnaryOperator;`.
2. **`BootstrapMethods`** cho biết BSM tham chiếu tới `java/lang/invoke/LambdaMetafactory.metafactory` và các static args của lambda (SAM method type, implementation method handle, instantiated method type).

Cùng class có thể xuất hiện nhiều `InvokeDynamic` khác do Java 17 còn dùng `StringConcatFactory.makeConcatWithConstants` cho biểu thức nối chuỗi trong `println`. **Không** lấy tổng số entry `InvokeDynamic` trong class để suy ra “bao nhiêu lần bootstrap của lambda đã được gọi”.

Mẫu đường đọc:

~~~text
Nguồn Java:
    return x -> x + 1;

javap -c:
    invokedynamic ... applyAsInt:()IntUnaryOperator

javap -v:
    BootstrapMethods[N] = LambdaMetafactory.metafactory(...)
    static args         = kiểu SAM, implementation method, kiểu SAM hiện thực

Runtime:
    JVM resolve vị trí invokedynamic và chọn CallSite khi cần
    target của site tạo/gắn function object thích hợp
    function.applyAsInt(x) mới thực thi phép +1
~~~

Một điểm tinh tế: phép `applyAsInt(3)` trên object trong ví dụ thường là `invokeinterface`, **không phải** một lần thực thi lại chính chỉ thị `invokedynamic` tạo object. `invokedynamic` của `factory` phục vụ **quá trình xây function instance**, còn gọi SAM trên instance là một lời gọi method khác. Điều đó lý giải vì sao phải phân biệt *bootstrap*, *factory target* và *lambda body*.

Lệnh `javap` chỉ phân tích class file; bản thân `javap` **không thực thi BSM** và **không cho biết BSM đã chạy bao nhiêu lần ở runtime**. Nó cho biết metadata để JVM có thể link điểm gọi.

## 8. Mẫu bootstrap do bạn tự viết (chỉ minh họa hợp đồng)

Nếu tự tạo bytecode `invokedynamic` bằng bytecode generator, bạn có thể tham chiếu tới một BSM có kiểu phổ biến sau:

~~~java
static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String name,
        MethodType siteType,
        int factor) throws ReflectiveOperationException {

    MethodHandle raw = caller.findStatic(
            Example.class,
            "multiply",
            MethodType.methodType(int.class, int.class, int.class));

    MethodHandle bound = MethodHandles.insertArguments(raw, 1, factor);
    return new ConstantCallSite(bound.asType(siteType));
}

static int multiply(int value, int factor) {
    return value * factor;
}
~~~

Đây là **đoạn mô phỏng API, không phải một chương trình Java độc lập**: `Example.class` tượng trưng cho class chứa method; muốn JVM tự gọi bootstrap cần có **class file thực sự chứa `CONSTANT_InvokeDynamic_info` và entry `BootstrapMethods` trỏ tới bootstrap này**. Chỉ khai báo method `bootstrap` trong source Java **không tự tạo `invokedynamic` gọi method đó**.

Giả sử bytecode mô tả một điểm gọi có `siteType = (int)int` và static argument `factor = 3`: BSM lấy handle `multiply(int,int)int`, gắn cố định `factor` vào đối số thứ hai để được handle `(int)int`, rồi trả `ConstantCallSite`. Khi điểm gọi chạy với `4`, target trả `12`.

Điều cần kiểm tra trong bản thật:

- `caller.findStatic` phải có quyền truy cập vào method đích; `Lookup` phụ thuộc class chứa điểm gọi. Trong BSM mẫu, `Example.class` cần xác định đúng đối tượng class.
- `bound.type()` phải tương thích để `asType(siteType)` hợp lệ; kết quả cuối phải **trùng chính xác kiểu** của điểm gọi.
- Số/loại static args phải thích nghi được với chữ ký bootstrap mà class file tham chiếu.
- Trả `ConstantCallSite` cố định khác với trả `MutableCallSite` cho phép thay target sau này.

Chú ý: `name` trong ví dụ không được dùng để định tuyến; trong bootstrap thực, nó có thể được dùng để quyết định target, nhưng không có quy định rằng `name` bắt buộc trùng tên `multiply`.

## 9. Lỗi xảy ra ở đâu trong vòng đời?

| Thời điểm | Triệu chứng / exception | Cần kiểm tra |
| --- | --- | --- |
| Resolve bootstrap method handle hoặc các static args | `LinkageError`, lỗi resolve class/method/access tùy tình huống | `BootstrapMethods`, class loader, module/package access, method handle kind, descriptor |
| BSM thực thi và ném exception **không phải subclass của `Error`** | `BootstrapMethodError` có nguyên nhân là exception gốc | Body BSM, quyền `Lookup`, thiếu target, logic tính adapter |
| BSM thực thi và ném một `Error` | `Error` ấy có thể truyền ra trực tiếp theo JVMS | Không mặc định mọi lỗi đều bị bọc trong `BootstrapMethodError` |
| BSM trả `null`, không trả `CallSite`, hoặc kiểu site sai descriptor | `BootstrapMethodError` | `CallSite.type()` so với call-site descriptor trong class file |
| Link đã thành công nhưng **target** khi được gọi ném exception | Exception do target/adapter phát sinh theo hợp đồng của nó | Mã nghiệp vụ, kiểu dữ liệu runtime, lỗi logic; không tự gán là thất bại bootstrap |
| `MutableCallSite.setTarget` với handle sai kiểu | `WrongMethodTypeException` tại `setTarget` | Type cố định của site so với `newTarget.type()` |
| Tạo site trống bằng `new MutableCallSite(MethodType)` rồi gọi trước khi đặt target hợp lệ | `IllegalStateException` từ target mặc định | Khởi tạo target có ích trước khi công bố site |

**Phân biệt lỗi link và lỗi target:** Khi **chính chỉ thị `invokedynamic`** đã link thành công, JVM bảo đảm target không `null` và có kiểu đúng descriptor; vì thế phần *dispatch* do chỉ thị tự thực hiện không sinh `WrongMethodTypeException` chỉ vì lệch descriptor đã được JVM kiểm tra. Tuy vậy **mã target** có thể tự ném `WrongMethodTypeException`, `NullPointerException` hoặc bất kỳ exception hợp lệ nào. Đừng bỏ qua stack trace.

Với lỗi resolution đã ghi nhận cho **cùng chỉ thị**, việc gọi lại chỉ thị không thử lại BSM. Muốn thay hành vi sau khi link thành công, cập nhật target của site phù hợp thay vì giả định lỗi link sẽ tự phục hồi.

## 10. Phân biệt mức “cố định” trong hệ thống động

| Thành phần | Cố định ở đâu? | Có thể thay đổi gì sau đó? |
| --- | --- | --- |
| `invokedynamic` trong class file | Vị trí bytecode và metadata (name, descriptor, BSM ref, static args) | Không thay trực tiếp class file đang chạy bằng `setTarget` |
| `CallSite` được JVM chọn cho chỉ thị | **Binding** cho vị trí chỉ thị sau linkage | Chỉ thị không tự chọn site khác |
| `CallSite.type()` | Kiểu tham số + trả về | **Không** đổi đối với chính site |
| Target `MethodHandle` của `ConstantCallSite` | Target | **Không** đổi |
| Target của `MutableCallSite` | Kiểu target | Có thể đổi sang method handle **cùng kiểu**; cần quan tâm visibility giữa thread |
| Target của `VolatileCallSite` | Kiểu target | Có thể đổi sang handle cùng kiểu, theo semantics volatile |
| Dữ liệu truyền khi dispatch | Giá trị runtime trên operand stack | Mỗi lần gọi có thể khác nhau |

Chẳng hạn tại một điểm gọi đã link `MutableCallSite` loại `(Object)Object`, target đầu có thể kiểm tra kiểu input và dùng đường chậm; sau khi quan sát dữ liệu, runtime có thể `setTarget` sang chuỗi `guardWithTest` đã tối ưu, miễn kiểu tổng thể vẫn `(Object)Object`. Đó là một kỹ thuật triển khai runtime động, **không cần làm BSM chạy lại**.

Đừng nhầm “JIT biên dịch lại/inline lại machine code” với “JVM resolution lại `invokedynamic`”. Đây là những cơ chế khác cấp độ, và chi tiết tối ưu hóa không phải hợp đồng public API.

## 11. Checklist khi đọc lỗi hoặc phân tích hiệu năng

1. **Chỉ định đúng vị trí bytecode**: class/method nào, chỉ thị `invokedynamic` nào? Đừng chỉ tìm tên bootstrap chung.
2. **Đọc `javap -v -p`**: `CONSTANT_InvokeDynamic_info`, name/type, entry `BootstrapMethods` và static args. Ghi rõ **call-site descriptor**, không nhầm với kiểu của method target bên trong.
3. **Xác định BSM thực sự nhận gì**: `Lookup`, tên, `MethodType`, các static args đã resolve. Kiểm tra class loader và quyền truy cập cần thiết.
4. **So kiểu trước khi trả kết quả**: `CallSite.type()` phải trùng descriptor; đặt target có ích trước khi trả site, nhất là với site được khởi tạo chỉ bằng `MethodType`.
5. **Phân biệt một lần link và nhiều lần dispatch**: một phương thức Java chạy 100 lần không có nghĩa BSM của một chỉ thị chạy 100 lần.
6. **Có concurrency hay không?** Bootstrap có thể được chạy cạnh tranh; tránh side effects phụ thuộc “chạy đúng một lần vật lý”.
7. **Có thay target không?** Với `MutableCallSite`, dùng `syncAll` hoặc quan hệ đồng bộ phù hợp; với `VolatileCallSite`, cân nhắc cost của volatile.
8. **Phân loại exception**: error resolve/BSM/validation khác với exception của target lúc thực thi. Khi đã thất bại link, không mong lần gọi kế là một retry.
9. **Tránh đoán tên generated class**: lambda implementation và tối ưu hóa target là chi tiết JVM; ưu tiên kiểm tra descriptor, handle type và API được bảo đảm.
10. **Tách các mức quan sát**: `javap` xem metadata tĩnh; log BSM (nếu bạn kiểm soát nó) đo bootstrap execution; telemetry của target đo invocation. Một nguồn quan sát không tự suy ra nguồn kia.

## 12. Câu hỏi tự kiểm tra

**1.** Một method chứa một `invokedynamic`; method được gọi 1.000 lần trên một thread. BSM có bắt buộc chạy 1.000 lần không?  
**Đáp:** Không. Sau khi vị trí ấy link thành công, các lần tiếp theo dùng site đã chọn. Trong một tiến trình đơn luồng bình thường, BSM chỉ cần chạy lúc link lần đầu.

**2.** Hai chỉ thị `invokedynamic` cùng tham chiếu một constant-pool entry. Chỉ thị thứ nhất đã link, chỉ thị thứ hai đã link chưa?  
**Đáp:** Chưa chắc. Theo JVMS, resolution của điểm gọi động được gắn **theo từng chỉ thị**, không tự động áp dụng cho chỉ thị còn lại.

**3.** Hai thread chạy vào một vị trí unlinked đồng thời. Có thể thấy BSM được gọi hai lần nhưng chỉ một site được chọn không?  
**Đáp:** Có. JVM được quyền chạy bootstrap cạnh tranh, sau đó chọn một kết quả và bỏ qua kết quả còn lại.

**4.** BSM trả `new ConstantCallSite(MethodHandles.constant(String.class,"x"))`, trong khi descriptor của điểm gọi là `(int)int`. Liên kết được không?  
**Đáp:** Không. Site có type `()String`, không trùng `(int)int`; validation thất bại với `BootstrapMethodError`.

**5.** Một `invokedynamic` đã gắn với `MutableCallSite`. Bạn thay `target` qua `setTarget` và `syncAll`. BSM có chạy lại không?  
**Đáp:** Không. Binding tới `CallSite` vẫn giữ nguyên; chỉ target trong site thay đổi.

**6.** Với `factory()` ở phần 6, lời gọi `a.applyAsInt(3)` có nhất thiết chạy lại `invokedynamic` để tạo lambda không?  
**Đáp:** Không. `factory()` đã tạo ra object function qua điểm gọi động; `applyAsInt` là lời gọi method trên object đó.

**7.** Một bootstrap thất bại khi link và sau đó hạ tầng đã được sửa. Cùng điểm gọi có tự gọi lại bootstrap lần nữa không?  
**Đáp:** Không. Kết quả thất bại khi resolve được lưu cho chính chỉ thị ấy. Không dựa vào “retry bootstrap” để hồi phục.

## Tài liệu Java 17 chính thức

- [JVMS 17 `5.4.3: Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3)
- [JVMS 17 `5.4.3.6: Dynamically-Computed Constant and Call Site Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
- [JVMS 17 `6.5: `invokedynamic` instruction](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic)
- [Java SE 17 `java.lang.invoke` package: call-site linkage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/package-summary.html)
- [Java SE 17 `CallSite`, `ConstantCallSite`, `MutableCallSite` và `VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [Java SE 17 `MutableCallSite.syncAll`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html)