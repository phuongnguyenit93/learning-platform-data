# 11.3 Hợp đồng bootstrap method với `Lookup`, tên, `MethodType` và đối số tĩnh

## 1. Từ `invokedynamic` tới bootstrap method: cần liên kết điều gì?

Trong bytecode Java, `invokedynamic` là một lệnh gọi có **điểm liên kết động** (*dynamic call site*). Khác với `invokestatic` hay `invokevirtual`, bản thân lệnh này không chứa một `Methodref` trỏ thẳng tới method Java sẽ thực hiện cho mọi lần gọi. Thay vào đó, class file chứa **mô tả call site** và **bootstrap method specifier**. Khi JVM phân giải (*resolve/link*) call site, nó gọi một **bootstrap method (BSM)** để lấy về một đối tượng `java.lang.invoke.CallSite`. `CallSite` mang `MethodHandle` tới target thực thi.

Hợp đồng thường gặp của BSM cho `invokedynamic`:

~~~java
public static CallSite bootstrap(
    MethodHandles.Lookup caller,
    String name,
    MethodType invokedType,
    /* 0 hoặc nhiều đối số tĩnh */
) throws Throwable
~~~

Đây là **khuôn chữ ký minh họa**, không phải một khai báo Java có thể biên dịch nguyên xi vì phần comment thay cho danh sách tham số. Ba đầu vào chuẩn là:

1. `MethodHandles.Lookup caller`: **ngữ cảnh quyền truy cập của class chứa lệnh `invokedynamic`**.
2. `String name`: **tên không đủ điều kiện** (*unqualified name*) được gắn trên chính call site.
3. `MethodType invokedType`: **chữ ký chính xác của lệnh `invokedynamic`**, gồm parameter types và return type.
4. **Static arguments bổ sung, nếu có**: metadata được ghi trong `BootstrapMethods` của class file và lấy từ constant pool, ví dụ `String`, `int`, `Class`, `MethodType`, `MethodHandle` hoặc dynamic constants hợp lệ.

BSM phải cung cấp một `CallSite` **khác null** với `CallSite.type()` **khớp chính xác** method descriptor của `invokedynamic`. Nó được phép tìm method, chọn implementation, ràng buộc argument bằng `insertArguments` hoặc thích nghi method handle bằng `asType` *trước khi* tạo `CallSite`. Sau khi liên kết thành công, các lần chạy tiếp theo của điểm gọi sử dụng **target của CallSite**, không đi qua code bootstrap như một lệnh gọi thông thường mỗi lần.

**Cảnh báo quan trọng:** “BSM chỉ chạy đúng một lần trong mọi hoàn cảnh” là diễn đạt quá mạnh. Khi nhiều thread cùng phân giải một symbolic reference, JVMS cho phép **nhiều lần thực thi BSM đồng thời**, rồi JVM chọn một kết quả để cài đặt cho site và bỏ các kết quả khác. Sau khi liên kết thành công, việc thực thi `invokedynamic` không bootstrap lại cho mỗi invocation. Vì vậy BSM cần tránh side effect không an toàn khi cạnh tranh.

### Vì sao phải hiểu hợp đồng này?

- Khi dùng lambda/method reference, `javac` thường phát sinh `invokedynamic` và `LambdaMetafactory.metafactory` làm BSM.
- Khi nối chuỗi bằng cú pháp `+`, `javac` hiện đại thường dùng `StringConcatFactory.makeConcatWithConstants` với một **recipe** làm static argument.
- Compiler cho ngôn ngữ chạy trên JVM và framework tạo bytecode có thể dùng BSM riêng để lựa chọn hoặc tạo target.
- Khi gặp `BootstrapMethodError` lúc chạy, cần biết lỗi xảy ra ở **giai đoạn liên kết** chứ không mặc định ở logic target method.

## 2. Sơ đồ luồng liên kết một call site

~~~text
Class file
  |
  +-- CONSTANT_InvokeDynamic
  |     tên: decorate
  |     descriptor: (Ljava/lang/String;)Ljava/lang/String;
  |     chỉ số bootstrap specifier: 0
  |
  +-- BootstrapMethods[0]
        MethodHandle REF_invokeStatic -> DecorateBootstrap.bootstrap
        static arg #1 -> "Hi-"
        static arg #2 -> int 2
                             |
                             v
                    JVM phân giải site
                             |
                             v
        bootstrap(callerLookup, "decorate",
                  MethodType(String)->String,
                  "Hi-", 2)
                             |
                             v
             BSM trả CallSite có type
                  (String)String
                             |
                             v
           JVM cài liên kết cho site
                             |
                             v
   invokedynamic chạy target nhận "Ada"
           -> "Hi-Hi-Ada"
~~~

Có **hai thời điểm khác nhau**:

- **Linkage time**: JVM phân giải BSM và static arguments, cấp `Lookup`/name/type, gọi BSM, kiểm tra `CallSite`.
- **Invocation time**: mỗi lần bytecode `invokedynamic` được chạy, nó truyền **dynamic arguments từ operand stack** tới target. Những giá trị như `"Ada"` hay `"Bob"` trong ví dụ không phải static bootstrap arguments.

JVM có thể thực hiện resolution sớm hoặc khi site lần đầu cần thực thi, theo các quy tắc liên kết của JVM. Đừng dùng thời điểm chính xác của println trong BSM làm hợp đồng về lịch scheduling của mọi JVM.

## 3. Hợp đồng từng tham số BSM

| Tham số BSM | Nguồn do JVM cung cấp | Ý nghĩa và sai lầm thường gặp |
| --- | --- | --- |
| `Lookup caller` | Ngữ cảnh class **chứa lệnh `invokedynamic`** | Không mặc định là class **định nghĩa BSM**; không được phép truy cập tùy ý mọi class |
| `String name` | `NameAndType` của `CONSTANT_InvokeDynamic` | Là tên **site**, không nhất thiết là tên method cuối cùng trên target |
| `MethodType invokedType` | Method descriptor của `CONSTANT_InvokeDynamic` | Mô tả **call site** (tham số lấy từ operand stack và return đưa về stack), không nhất thiết là chữ ký của method được Java source tham chiếu |
| Static arg 1…N | Các constant-pool entries trong `BootstrapMethods` | Metadata **cố định tại linkage**, thứ tự đúng theo class file, không phải các argument runtime |
| Kết quả `CallSite` | Giá trị trả của BSM | Phải khác null, có target type đúng; target có thể là method handle đã được biến đổi/thích nghi |

### 3.1. `MethodHandles.Lookup`: quyền của *caller*, không phải quyền “toàn năng”

Giả sử bytecode `invokedynamic` nằm trong class `example.GeneratedCaller`, nhưng BSM được định nghĩa ở `example.BootstrapLibrary`. `caller.lookupClass()` phản ánh **`GeneratedCaller`**, không phải `BootstrapLibrary`.

Lookup được JVM cấp để BSM có thể tạo method handles với quyền truy cập tương ứng ngữ cảnh của **lớp chứa site**. Điều này hữu ích khi BSM cần tìm private method/member mà code được biên dịch có quyền dùng. Tuy nhiên mọi lời gọi `findStatic`, `findVirtual`, `findSpecial`, `privateLookupIn` vẫn tuân theo access mode, module và các quy tắc bảo vệ của `Lookup`.

Một BSM không nên bỏ mặc `caller` rồi tùy tiện dùng `MethodHandles.lookup()` trong class thư viện khi target cần truy cập thành phần của class gọi. `lookup()` trong thư viện phản ánh **quyền của thư viện**, có thể khác quyền của caller. Ngược lại, không được dùng `caller` như một cơ chế vượt qua Java module encapsulation.

### 3.2. `String name`: tên của *site*, không phải tên target bắt buộc

Trong lambda, `invokedynamic` có thể mang tên `apply`, `get`, `run`... ứng với functional interface. Target của `CallSite` thường là một **factory tạo function object**, chứ không phải method `apply` được gọi trực tiếp tại thời điểm tạo lambda.

Trong ví dụ BSM tự viết ở phần 6, tên site là `decorate` để dễ đọc. BSM hoàn toàn có thể chọn một method tên `render` hoặc `dispatch`, miễn target type và ngữ nghĩa phù hợp. Không có hợp đồng chung buộc `caller.findStatic(..., name, type)` phải thành công chỉ vì site mang `name` đó.

Nên validate `name` nếu thư viện BSM chỉ hỗ trợ một tập operation cụ thể; dùng name để chọn implementation là quyết định của BSM, không phải magic resolution mặc định của JVM.

### 3.3. `MethodType invokedType`: đặc biệt phải xét **return type**

Ví dụ descriptor JVM:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

tương ứng với:

~~~java
MethodType.methodType(String.class, String.class)
~~~

và hiển thị bởi `toString()`:

~~~text
(String)String
~~~

Đây là type của **call site**: một `String` đi vào, một `String` đi ra. Nếu target handle ban đầu mang `(String,int,String)String`, BSM có thể bind hai tham số đầu rồi nhận `(String)String`. Nếu dùng `target.asType(invokedType)`, conversion phải hợp lệ; một `CallSite` cuối vẫn phải có đúng type yêu cầu.

**Không nhầm `invokedType` với chữ ký của BSM.** BSM có thể nhận `(Lookup,String,MethodType,String,int)CallSite` nhưng site được liên kết lại có `(String)String`. Hai kiểu dùng cho **hai lời gọi khác nhau**: gọi BSM lúc linkage và gọi target lúc invocation.

### 3.4. Đối số tĩnh (*static bootstrap arguments*)

“Static” ở đây nghĩa là **metadata cố định gắn với site trong class file**, không có nghĩa “biến Java `static`”. Chúng **không** phải các tham số runtime nằm trong dấu ngoặc của source expression/target invocation.

Theo JVMS 17, mỗi static argument trong `BootstrapMethods` trỏ tới một **constant-pool entry có thể load**, ví dụ:

- `CONSTANT_String`: một `String` như `"Hi-"`.
- `CONSTANT_Integer/Float/Long/Double`: numeric constants; khi BSM được gọi qua method handle, giá trị được biểu diễn dưới dạng wrapper thích hợp, rồi có thể unbox để khớp tham số primitive.
- `CONSTANT_Class`: một đối tượng `Class<?>`.
- `CONSTANT_MethodType`: một `MethodType` đã được phân giải.
- `CONSTANT_MethodHandle`: một method handle đã được phân giải.
- `CONSTANT_Dynamic`: một dynamic constant mà quá trình phân giải có thể tạo giá trị bổ sung; nó mang **bootstrap contract riêng**, không tự đồng nhất với BSM của `invokedynamic`.

Static arguments xuất hiện **sau ba implicit arguments**, theo **đúng thứ tự đã ghi**. JVM không tự phân tích giá trị của chúng để lựa một overload BSM theo business rules. Bootstrap method handle được gọi với danh sách `caller, name, type, staticArg1, ...` bằng ngữ nghĩa **như thể `MethodHandle.invokeWithArguments(...)`**. Vì vậy chữ ký BSM thường khai báo đúng ba kiểu chuẩn và các static args tương ứng; theo đặc tả, kiểu tham số handle có thể khác khi converter của `invokeWithArguments` cho phép, và một varargs collector có thể gom các đối số cuối.

**Không nói cứng rằng BSM nhất thiết phải có đúng chữ ký Java `(Lookup,String,MethodType,...)CallSite`.** Đây là giao diện **quy ước và đáng dùng nhất**, nhưng JVM thực sự yêu cầu bootstrap method handle *có thể nhận* những đối số mà nó cung cấp và trả kết quả hợp lệ. `CONSTANT_Dynamic` (condy) có một số ràng buộc riêng; không áp đặt quy tắc condy lên invokedynamic.

## 4. Dấu vết trong class file: `InvokeDynamic` và `BootstrapMethods`

Một `invokedynamic` instruction sử dụng một constant-pool entry kiểu `CONSTANT_InvokeDynamic`. Entry này gắn:

- **bootstrap method attribute index**: trỏ vào bảng trong `BootstrapMethods` của class.
- **name-and-type index**: chỉ ra **tên site và method descriptor**.

`BootstrapMethods` ở cấp class trỏ tới:

- `bootstrap_method_ref` là `CONSTANT_MethodHandle` xác định BSM sẽ gọi.
- `num_bootstrap_arguments` và danh sách các `bootstrap_arguments` tương ứng (có thể không có static args).

Đây là một mối quan hệ **hai bảng**: `CONSTANT_InvokeDynamic` dùng chỉ số vào `BootstrapMethods`; entry trong `BootstrapMethods` dẫn tới method handle BSM và danh sách static args. Không nhầm một `Methodref` thông thường với toàn bộ thông tin để liên kết call site.

Trong một listing `javap -v`, thường thấy cấu trúc tương tự:

~~~text
#18 = InvokeDynamic  #0:#17
#17 = NameAndType    #16:#6
#15 = MethodHandle   6:#14   // REF_invokeStatic ...
BootstrapMethods:
  0: #15 REF_invokeStatic ...
    Method arguments:
      #20 ...
      #21 ...
~~~

**Các số `#18`/`#17` ở đây chỉ dùng trong ví dụ class tự sinh ở phần 6.** Đối với class khác hoặc khi compiler/JDK thay đổi, constant-pool indices và cách trình bày `javap` có thể khác. Điều cần nhận biết là quan hệ `InvokeDynamic → bootstrap index → MethodHandle + static arguments`.

## 5. Ví dụ thật với Java source: `LambdaMetafactory` và các static arguments

Khi viết lambda hoặc method reference trong Java, compiler của JDK thường dùng `invokedynamic` cho việc xây function object. Đây là ví dụ **có invokedynamic thật** mà không cần tạo bytecode bằng tay.

Tạo **`LambdaIndyDemo.java`**:

~~~java
import java.util.Locale;
import java.util.function.UnaryOperator;

public class LambdaIndyDemo {
    static String upper(String value) {
        return value.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        UnaryOperator<String> op = LambdaIndyDemo::upper;
        System.out.println(op.apply("java"));
    }
}
~~~

Biên dịch/chạy/kiểm tra:

~~~sh
javac --release 17 LambdaIndyDemo.java
java LambdaIndyDemo
javap -v -p LambdaIndyDemo
~~~

**Stdout của lệnh `java LambdaIndyDemo`:**

~~~text
JAVA
~~~

Trong output `javap`, tìm các thành phần (bỏ qua số `#...` vì có thể khác):

~~~text
InvokeDynamic ... apply:()Ljava/util/function/UnaryOperator;
BootstrapMethods:
  ... REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
    Method arguments:
      (Ljava/lang/Object;)Ljava/lang/Object;
      REF_invokeStatic LambdaIndyDemo.upper:(Ljava/lang/String;)Ljava/lang/String;
      (Ljava/lang/String;)Ljava/lang/String;
~~~

Phân tích ba implicit inputs:

- **`caller`**: Lookup cho class chứa instruction — `LambdaIndyDemo`.
- **`name`**: `apply`, tên phương thức của functional interface ở ngữ cảnh này.
- **`invokedType`**: `()UnaryOperator`. Đây là **kiểu của factory call site tạo lambda object**, không phải `(String)String`.

Ba **static arguments** của BSM `LambdaMetafactory.metafactory` trong ví dụ:

1. `samMethodType`: kiểu JVM của abstract method trong functional interface, thường có erasure `(Object)Object`.
2. `implMethod`: `MethodHandle` chỉ tới implementation `LambdaIndyDemo.upper(String)String`.
3. `instantiatedMethodType`: method type ở mức type specialization `(String)String`.

**Điều khác biệt phải nắm:** khi chương trình sau đó gọi `op.apply("java")`, đó là lời gọi interface trên object vừa tạo; không phải lần bootstrap mới của instruction tạo lambda. `CallSite` từ metafactory đóng vai trò **factory**, còn lambda object thực hiện hành vi được ủy quyền qua implementation method handle.

Không cố đoán hình dạng class implementation của lambda (ẩn hay không, được tái sử dụng hay không) dựa vào kết quả riêng một JVM. Hợp đồng ở đây là linkage và hành vi của functional interface, không phải identity/representation của object được tạo.

## 6. Ví dụ custom bootstrap có **invokedynamic thật** và hai đối số tĩnh

Java source thông thường **không có cú pháp trực tiếp** để viết một instruction `invokedynamic` tùy ý với BSM tự chọn. Để minh họa **chính xác cả bốn nhóm thông tin mà JVM truyền**, ví dụ này dùng **API chuẩn Java 17 `java.io.DataOutputStream`** tạo một class file nhỏ mang lệnh `invokedynamic`. Nó không yêu cầu thư viện ASM, JDK-internal APIs hay plugin bên ngoài.

Bộ ví dụ có ba file source độc lập trong cùng thư mục:

~~~text
DecorateBootstrap.java   - bootstrap và target method
IndyClassWriter.java     - ghi IndyGenerated.class theo định dạng JVM
IndyRunner.java          - nạp class được sinh và gọi 2 lần
~~~

### 6.1. Bootstrap method nhận đầy đủ `Lookup`, `name`, `MethodType` và static args

Lưu **`DecorateBootstrap.java`**:

~~~java
import java.lang.invoke.*;

public class DecorateBootstrap {
    public static int linkCount;

    public static CallSite bootstrap(
            MethodHandles.Lookup caller,
            String name,
            MethodType type,
            String prefix,
            int repeat) throws Throwable {
        linkCount++;
        System.out.println("link=" + caller.lookupClass().getSimpleName()
                + "|" + name + "|" + type + "|" + prefix + "|" + repeat);

        MethodHandle impl = caller.findStatic(
                DecorateBootstrap.class, "decorate",
                MethodType.methodType(String.class,
                        String.class, int.class, String.class));

        MethodHandle bound = MethodHandles.insertArguments(
                impl, 0, prefix, repeat).asType(type);
        return new ConstantCallSite(bound);
    }

    public static String decorate(
            String prefix, int repeat, String input) {
        return prefix.repeat(repeat) + input;
    }
}
~~~

`decorate` là target method `(String,int,String)String`. BSM nhận `prefix` và `repeat` ở linkage time, rồi:

1. `caller.findStatic(...)` tra cứu target theo quyền của class chứa site. Target trong ví dụ là `public static` để làm rõ access.
2. `insertArguments(impl,0,prefix,repeat)` cố định hai tham số đầu. Handle còn lại có kiểu `(String)String`.
3. `asType(type)` bảo đảm khả năng thích nghi tới đúng type yêu cầu của site (ở ví dụ đã đúng).
4. `new ConstantCallSite(bound)` trả một call site có target bất biến.

`linkCount` là biến quan sát **dành riêng cho bài demo chạy một luồng**. Đừng dùng cách tăng `linkCount++` như một metric an toàn cho BSM được phân giải đồng thời; JVMS cho phép concurrent bootstrap calls.

### 6.2. Ghi class file mang `CONSTANT_InvokeDynamic` và `BootstrapMethods`

Lưu **`IndyClassWriter.java`**:

~~~java
import java.io.*;
import java.nio.file.*;

public class IndyClassWriter {
    private static void utf(DataOutputStream out, String value)
            throws IOException {
        out.writeByte(1);
        out.writeUTF(value);
    }

    private static void clazz(DataOutputStream out, int name)
            throws IOException {
        out.writeByte(7);
        out.writeShort(name);
    }

    private static void nameType(
            DataOutputStream out, int name, int descriptor)
            throws IOException {
        out.writeByte(12);
        out.writeShort(name);
        out.writeShort(descriptor);
    }

    private static void methodRef(
            DataOutputStream out, int clazz, int nt)
            throws IOException {
        out.writeByte(10);
        out.writeShort(clazz);
        out.writeShort(nt);
    }

    private static void methodHandle(
            DataOutputStream out, int kind, int ref)
            throws IOException {
        out.writeByte(15);
        out.writeByte(kind);
        out.writeShort(ref);
    }

    private static void indy(
            DataOutputStream out, int bootstrap, int nt)
            throws IOException {
        out.writeByte(18);
        out.writeShort(bootstrap);
        out.writeShort(nt);
    }

    private static void str(DataOutputStream out, int utf8)
            throws IOException {
        out.writeByte(8);
        out.writeShort(utf8);
    }

    private static void integer(DataOutputStream out, int number)
            throws IOException {
        out.writeByte(3);
        out.writeInt(number);
    }

    public static void main(String[] args) throws Exception {
        Path target = Path.of(args.length == 0 ? "." : args[0],
                "IndyGenerated.class");

        try (DataOutputStream out = new DataOutputStream(
                Files.newOutputStream(target))) {
            out.writeInt(0xCAFEBABE);
            out.writeShort(0);
            out.writeShort(61); // class-file version 61 = Java 17
            out.writeShort(22); // CP count: 21 entries + slot zero

            utf(out, "IndyGenerated");                 // #1
            clazz(out, 1);                             // #2
            utf(out, "java/lang/Object");              // #3
            clazz(out, 3);                             // #4
            utf(out, "run");                           // #5
            utf(out, "(Ljava/lang/String;)Ljava/lang/String;"); // #6
            utf(out, "Code");                          // #7
            utf(out, "BootstrapMethods");              // #8
            utf(out, "DecorateBootstrap");             // #9
            clazz(out, 9);                             // #10
            utf(out, "bootstrap");                     // #11
            utf(out, "(Ljava/lang/invoke/MethodHandles$Lookup;"
                    + "Ljava/lang/String;Ljava/lang/invoke/MethodType;"
                    + "Ljava/lang/String;I)Ljava/lang/invoke/CallSite;"); // #12
            nameType(out, 11, 12);                     // #13
            methodRef(out, 10, 13);                    // #14
            methodHandle(out, 6, 14);                  // #15 REF_invokeStatic
            utf(out, "decorate");                      // #16
            nameType(out, 16, 6);                      // #17
            indy(out, 0, 17);                          // #18 BSM 0
            utf(out, "Hi-");                           // #19
            str(out, 19);                              // #20 static String
            integer(out, 2);                           // #21 static int

            out.writeShort(0x0021); // public + super
            out.writeShort(2);      // this_class
            out.writeShort(4);      // java/lang/Object
            out.writeShort(0);      // interfaces
            out.writeShort(0);      // fields
            out.writeShort(1);      // methods

            out.writeShort(0x0009); // public static run
            out.writeShort(5);      // "run"
            out.writeShort(6);      // (String)String
            out.writeShort(1);      // Code attribute count
            out.writeShort(7);      // "Code"
            out.writeInt(19);       // attribute length
            out.writeShort(1);      // max_stack
            out.writeShort(1);      // max_locals
            out.writeInt(7);        // bytecode length
            out.writeByte(0x2a);    // aload_0
            out.writeByte(0xba);    // invokedynamic
            out.writeShort(18);     // CP #18
            out.writeShort(0);      // reserved zero bytes
            out.writeByte(0xb0);    // areturn
            out.writeShort(0);      // exception table length
            out.writeShort(0);      // nested Code attributes

            out.writeShort(1);      // class attributes
            out.writeShort(8);      // "BootstrapMethods"
            out.writeInt(10);       // attribute length
            out.writeShort(1);      // one bootstrap entry
            out.writeShort(15);     // MethodHandle #15
            out.writeShort(2);      // two static args
            out.writeShort(20);     // "Hi-"
            out.writeShort(21);     // int 2
        }
        System.out.println("generated=IndyGenerated.class");
    }
}
~~~

Chú ý nội dung bytecode tối giản:

- Java 17 dùng class-file major version **61**.
- Lệnh `aload_0` đưa tham số `String` lên operand stack.
- Lệnh `invokedynamic #18` gọi dynamic site `decorate:(String)String`, bytecode kết thúc bằng hai byte 0.
- Lệnh `areturn` trả `String` cho method `run`.
- `#15` là method handle `REF_invokeStatic` trỏ tới `DecorateBootstrap.bootstrap`.
- `#20` là static argument `"Hi-"`, `#21` là static argument `2`. Chúng được lưu trong `BootstrapMethods`, **không** được load như tham số của method `run`.
- Class sinh ra **chỉ có static method `run(String)`**, không cần constructor vì runner không tạo instance. Đây là class file phục vụ minh họa, không phải bộ sinh bytecode tổng quát. Mọi constant pool string đều ASCII để có thể viết đơn giản bằng `writeUTF`.

### 6.3. Runner nạp class vừa sinh

Lưu **`IndyRunner.java`**:

~~~java
import java.lang.reflect.Method;

public class IndyRunner {
    public static void main(String[] args) throws Exception {
        Class<?> generated = Class.forName("IndyGenerated");
        Method run = generated.getMethod("run", String.class);

        System.out.println("first=" + run.invoke(null, "Ada"));
        System.out.println("second=" + run.invoke(null, "Bob"));
        System.out.println("linkCount=" + DecorateBootstrap.linkCount);
    }
}
~~~

Từ thư mục có cả ba source files, dùng JDK 17+:

~~~sh
javac --release 17 -d out DecorateBootstrap.java IndyClassWriter.java IndyRunner.java
java -cp out IndyClassWriter out
java -cp out IndyRunner
javap -classpath out -v -p IndyGenerated
~~~

Lệnh `javap` là **bước quan sát**, không làm thay đổi output của chương trình runner.

**Stdout của hai lệnh `java` (theo thứ tự):**

~~~text
generated=IndyGenerated.class
link=IndyGenerated|decorate|(String)String|Hi-|2
first=Hi-Hi-Ada
second=Hi-Hi-Bob
linkCount=1
~~~

**Vì sao đây là invokedynamic thật?** `IndyClassWriter` ghi opcode `0xba` và `CONSTANT_InvokeDynamic` vào class file. JVM liên kết lệnh khi thực hiện `IndyGenerated.run("Ada")`. BSM do JVM gọi với đúng ba argument ngầm định + hai static arguments. `IndyRunner` dùng Reflection để **gọi method `run`**, nhưng **lệnh `invokedynamic` thực sự nằm trong bytecode của `run`**, không phải do Reflection tự mô phỏng.

**Giải thích từng dòng:**

- `caller.lookupClass().getSimpleName()` là **`IndyGenerated`**, dù BSM được định nghĩa trong `DecorateBootstrap`.
- `name` là `decorate` do `#17 NameAndType` gắn cho site.
- `type` in `(String)String` vì call site nhận một `String` runtime và trả một `String`.
- Hai static arguments là `"Hi-"` và `2`; BSM dùng chúng để bind prefix và repeat count.
- `"Ada"` và `"Bob"` là **dynamic arguments** của hai invocation riêng, không xuất hiện trong static-argument list.
- BSM liên kết thành công bằng `ConstantCallSite` rồi các lần chạy site dùng target đã gắn. Trong chương trình tuần tự này, `linkCount=1`.

Hãy xem đoạn quan trọng của `javap -v -p IndyGenerated` (các số này **cố định trong generator ví dụ**, nhưng không nên coi là quy tắc chung):

~~~text
#15 = MethodHandle ... REF_invokeStatic DecorateBootstrap.bootstrap
#17 = NameAndType  #16:#6    // decorate:(Ljava/lang/String;)Ljava/lang/String;
#18 = InvokeDynamic #0:#17   // #0:decorate:(Ljava/lang/String;)Ljava/lang/String;
#20 = String       #19       // Hi-
#21 = Integer      2
...
  public static java.lang.String run(java.lang.String);
    ...
       1: invokedynamic #18,  0
...
BootstrapMethods:
  0: #15 REF_invokeStatic DecorateBootstrap.bootstrap...
    Method arguments:
      #20 Hi-
      #21 2
~~~

Đây là quan hệ cụ thể giữa *call-site name/type* và *bootstrap method + static args* trong class file. Không nhầm literal `"Hi-"` với `"Ada"`/`"Bob"`.

## 7. BSM trả về `CallSite` như thế nào cho đúng?

BSM có trách nhiệm làm sao để `CallSite.type()` **bằng** `invokedType` do JVM truyền. Trong ví dụ:

~~~text
BSM signature:    (Lookup,String,MethodType,String,int)CallSite
Site descriptor:  (String)String
Target trước bind:(String,int,String)String
Static arguments: "Hi-", 2
Target sau bind:  (String)String
CallSite.type():  (String)String  [khớp site]
~~~

JVM không tự đoán “truyền hai static args rồi bỏ chúng khỏi signature target”. Chính BSM gọi `insertArguments` để **biến** target ban đầu thành đúng method handle mà site cần.

### Các dạng `CallSite`

| Lớp | Target có đổi được không? | Dùng khi |
| --- | --- | --- |
| `ConstantCallSite` | Không. `setTarget` luôn ném `UnsupportedOperationException` | Liên kết cố định, ví dụ lambda factory hoặc custom site bất biến |
| `MutableCallSite` | Có; việc quan sát update giữa các thread cần phối hợp `MutableCallSite.syncAll(...)` theo API | Inline cache, runtime cần relink target với chi phí memory-ordering thấp hơn |
| `VolatileCallSite` | Có, target mang hiệu ứng volatile khi cập nhật/đọc | Cần thread khác thấy target update theo hợp đồng volatile |

Dù mutable, **type của call site không đổi**. `setTarget(newTarget)` yêu cầu `newTarget.type()` cùng kiểu với target cũ; nếu không, ném `WrongMethodTypeException`. Không thể đổi `(String)String` thành `(int)int` chỉ bằng relink.

**`CallSite.dynamicInvoker()`** cung cấp một method handle tương đương lời gọi dynamic tới target hiện tại. Với `ConstantCallSite`, nó tương đương target cố định; với mutable/volatile site, nó theo target được cập nhật theo quy tắc tương ứng. Trong phần 6, JVM gắn chính `CallSite` để thực thi `invokedynamic`.

### Khi nào cần `MethodHandle.asType`?

Target method tìm bằng `Lookup` có thể có method type khác site type nhưng **chuyển đổi hợp lệ** qua `asType(invokedType)`. Ví dụ handle trả `Integer` trong khi site mong `Object` có thể được thích nghi. Nhưng `asType` **không** tự cho phép mọi primitive narrowing hoặc biến `String` thành số. Nếu conversion không hợp lệ, BSM nên kiểm tra/thiết kế lại adapter thay vì trả target sai kiểu.

Đừng tin rằng JVM sẽ tự thích nghi một `CallSite` có target type khác descriptor: **đó là trách nhiệm BSM trước khi trả CallSite**. Không khớp vẫn thất bại linkage.

## 8. Lỗi bootstrap: `BootstrapMethodError` và những nguyên nhân chính

Các lỗi trong bước **resolution/linkage** khác với exception ném **sau khi target đã chạy**.

| Tình huống | Hệ quả điển hình |
| --- | --- |
| Bootstrap method handle không phân giải được hoặc static arguments không phân giải được | Linkage thất bại, có thể là `LinkageError`/`BootstrapMethodError` theo giai đoạn |
| BSM nhận sai/thiếu static arguments và không thể gọi bằng `invokeWithArguments` | Thường gây exception khi gọi BSM; runtime có thể báo `BootstrapMethodError` tùy ngoại lệ gốc |
| BSM ném một exception **không phải `Error`** | JVMS yêu cầu resolution thất bại bằng `BootstrapMethodError` với cause gốc |
| BSM trực tiếp ném một `Error` hoặc subclass | Resolution có thể thất bại bằng **chính `Error` đó**, không luôn bị bọc lại |
| BSM trả `null`, hoặc giá trị không phải `CallSite` | `BootstrapMethodError` |
| BSM trả CallSite type **khác** descriptor của site | `BootstrapMethodError` |
| Đã liên kết tốt, target ném `IllegalArgumentException` hay exception khác lúc invoke | Lỗi từ **target invocation**, không phải mặc định `BootstrapMethodError` |

**Ví dụ sai về target type (snippet, không phải chương trình độc lập):**

~~~java
// invokedType thực tế là (String)String
MethodHandle wrong = MethodHandles.constant(String.class, "bad");
// wrong.type() == ()String, không phải (String)String
return new ConstantCallSite(wrong);
~~~

Nếu đặt logic trên vào BSM của một site `(String)String` rồi thực sự thực hiện `invokedynamic`, JVM sẽ không chấp nhận CallSite type `()String` và báo lỗi linkage bằng `BootstrapMethodError`. Đây **không** phải lời gọi `MethodHandle.invoke(...)` thông thường tự thích nghi kiểu; validator của `invokedynamic` đòi **CallSite type bằng site descriptor**.

### Lỗi runtime thường bị gán nhầm cho BSM

- `ClassCastException` trong body target: không tự suy ra BSM sai; tìm đoạn conversion/cast của target.
- `WrongMethodTypeException` khi BSM xây adapter `asType` sai: BSM có thể ném exception này, sau đó JVM báo lỗi bootstrap trong lúc linkage.
- `IllegalAccessException` khi BSM dùng `Lookup.findStatic` sai quyền: xác định ai là `lookupClass()` và target có accessible không.
- `NoSuchMethodException` khi BSM tra method sai tên/type: đây là lỗi tra cứu trong BSM, không phải JVM tự chọn overload cho `name`.
- `InvocationTargetException` có thể xuất hiện nếu chính ứng dụng dùng `Method.invoke` để gọi runner/target (như `IndyRunner`); nó là lớp bọc của Reflection, **không phải** cách `invokedynamic` bọc mọi exception từ target.

**Cách điều tra:** nhìn outer error và `getCause()` (khi có), phân biệt stack frame bootstrap, target và caller. Không tự sửa BSM bằng cách nuốt exception rồi trả CallSite sai kiểu: điều đó chỉ biến nguyên nhân rõ ràng thành lỗi liên kết khó chẩn đoán.

## 9. Vấn đề một site có thể bootstrap nhiều lần đồng thời

JVMS 17 nêu khả năng nhiều thread cùng resolution một symbolic reference tới dynamically-computed call site:

1. Một số bootstrap method invocations **có thể chạy đồng thời**.
2. JVM chọn **một kết quả** và cài đặt kết quả ấy cho tất cả thread dùng cùng symbolic reference tại site phù hợp.
3. Những bootstrap executions khác có thể hoàn thành, nhưng kết quả bị bỏ qua.

Do đó khi BSM tạo object tốn kém, ghi cache toàn cục hoặc tăng counter không đồng bộ, có rủi ro duplicated side effects. Không lấy output `linkCount=1` của ví dụ chạy tuần tự làm bảo đảm về mọi concurrent scheduling.

Mặt khác, **một instruction đã liên kết thành công sẽ tái sử dụng liên kết**, không gọi BSM lại trên từng lần thực thi. `ConstantCallSite` cố định target; `MutableCallSite`/`VolatileCallSite` cho phép đổi target mà **không cần bootstrap lại** một lần cho mỗi switch. Việc thay target phải tuân theo type/visibility semantics.

Về granularity, hãy hiểu liên kết thuộc **điểm gọi/symbolic reference trong class-file context**, không phải một singleton tự động chia sẻ giữa mọi class, mọi instruction hoặc mọi class loader. Hai call sites cùng gọi một BSM và cùng có static args **không vì thế mặc định là một CallSite duy nhất**.

## 10. So sánh với `ConstantDynamic` (để khỏi nhầm contract)

Từ Java 11, constant pool còn có `CONSTANT_Dynamic` (*condy*): một **constant được tính khi resolve**. Condy cũng dùng bootstrap method và static arguments, nhưng khác mục tiêu:

| Đặc điểm | `invokedynamic` | `CONSTANT_Dynamic` |
| --- | --- | --- |
| Thứ được phân giải | Dynamic **call site** | Dynamic **constant** |
| Đầu vào thứ ba thường dùng | `MethodType` (method descriptor) | `Class<?>` (field descriptor / constant type) |
| Kết quả cần có | `CallSite` type khớp site descriptor | Constant value phù hợp constant descriptor |
| Runtime sau resolution | Gọi target khi instruction chạy | Dùng giá trị constant đã resolve |
| Bài này tập trung? | **Có** | Chỉ để phân biệt |

Không viết generic BSM cho condy rồi mặc định signature/return hợp lệ cho indy, và ngược lại. JVMS quy định rõ phần đầu vào và validation khác nhau của hai loại symbolic reference.

## 11. Checklist thiết kế và kiểm chứng bootstrap method

Khi tự xây compiler, bytecode emitter, runtime linker hoặc phân tích `javap`, kiểm tra theo thứ tự:

1. **`CONSTANT_InvokeDynamic` có name và descriptor nào?** Xác định đúng arity và return type, không chỉ tên method trong source.
2. **Bootstrap index nào?** Tra entry tương ứng trong `BootstrapMethods`, rồi tra `bootstrap_method_ref` đến method handle cụ thể.
3. **Có bao nhiêu static arguments?** Đọc loại constant pool, thứ tự, giá trị và cách resolution/boxing; không nhầm chúng với runtime operands.
4. **BSM có nhận được những giá trị đó không?** Kiểm tra method handle type hoặc varargs collector theo `invokeWithArguments` semantics; ví dụ `String` và `int` phải khớp hoặc convertible.
5. **`caller.lookupClass()` là ai?** Đây là class chứa call site. Dùng quyền lookup phù hợp với target/module, không đoán quyền theo class bootstrap.
6. **BSM xử lý `name` như thế nào?** Có dispatch theo tên, ignore name hay validate tập tên? Không mặc định name là tên target.
7. **BSM dùng `invokedType` làm gì?** Tạo target method handle có type chính xác, bind parameters hoặc `asType` nếu hợp lệ.
8. **`CallSite` có khác null và type khớp tuyệt đối không?** Không trả wrong-type target với hy vọng JVM tự cast.
9. **Chọn `ConstantCallSite` hay mutable/volatile?** Cần relink không, memory visibility giữa threads thế nào, type bất biến ra sao?
10. **BSM có side effect không?** Tính đến concurrent resolution và cache; đừng dựa vào “chỉ chạy một lần” làm rào chắn.
11. **Thất bại nằm ở linkage hay invocation?** Phân biệt `BootstrapMethodError` với exception target; xem cause và stack trace.
12. **Có thể kiểm chứng bytecode không?** Chạy `javap -v -p -c` và nhìn đồng thời `InvokeDynamic`, `BootstrapMethods`, method handle BSM, static args.

### Những sai lầm phổ biến

- “Ba argument của BSM là input do ứng dụng truyền mỗi lần gọi site.” — Sai: JVM cấp chúng lúc linkage.
- “`caller` là `Lookup` của class chứa method bootstrap.” — Sai: nó phản ánh class chứa instruction.
- “`name` bắt buộc là tên Java method target.” — Sai: nó là tên call site, BSM chọn nghĩa.
- “`invokedType` là chữ ký của BSM.” — Sai: nó là type của **call site**.
- “Static args là field `static`.” — Sai: chúng là constant-pool metadata gắn với bootstrap specifier.
- “Cứ trả `CallSite` bất kỳ JVM sẽ tự thích nghi.” — Sai: type phải khớp chính xác.
- “`asType` chuyển được mọi dữ liệu.” — Sai: conversion có giới hạn.
- “Lần nào chạy indy cũng gọi lại BSM.” — Sai sau successful linkage.
- “BSM không bao giờ bị gọi đồng thời cho một site.” — Sai theo JVMS.
- “`invokedynamic` chỉ được tạo bằng code Java Reflection.” — Sai: nó là opcode trong class file; Reflection có thể giúp gọi method chứa opcode, nhưng không tạo ra opcode đó.
- “Lambda site type luôn là `(String)String` nếu lambda body nhận/trả `String`.” — Sai: site type thường mô tả **factory tạo functional object**.
- “BSM exception nào cũng bị bọc thành `BootstrapMethodError`.” — Sai: JVMS phân biệt `Error` và những exceptions khác.
- “Hai sites dùng chung BSM đồng nghĩa dùng cùng một CallSite.” — Không được bảo đảm; mỗi site liên kết theo symbolic reference context.

## 12. Bài tập kèm đáp án

**Câu 1.** Một instruction có `name="make"`, descriptor `(I)Ljava/lang/String;` và static arg `"TAG"`. `MethodType` do JVM cấp là gì?

**Đáp án:** `MethodType.methodType(String.class, int.class)`, hiển thị `(int)String`. `"TAG"` không làm tăng số argument runtime của site.

**Câu 2.** BSM khai báo `(Lookup,String,MethodType,String,int)CallSite`, trong `BootstrapMethods` có hai static args `"Hi-"`, `2`. Đâu là ba implicit args và đâu là hai static args?

**Đáp án:** Lookup của caller, name và MethodType là implicit JVM inputs. `"Hi-"` và `2` là static arguments từ class file, theo đúng thứ tự. Argument runtime của site được truyền sau khi BSM liên kết, không nằm trong năm giá trị gọi BSM này.

**Câu 3.** Nếu `caller.lookupClass()` in `IndyGenerated` nhưng bootstrap được định nghĩa trong `DecorateBootstrap`, điều đó có sai không?

**Đáp án:** Không. Đó chính là ngữ cảnh caller của invokedynamic instruction.

**Câu 4.** Với site `(String)String`, BSM trả `new ConstantCallSite(MethodHandles.constant(String.class,"x"))`. Vì sao lỗi?

**Đáp án:** Handle từ `constant` có type `()String`, nên CallSite type sai so với descriptor `(String)String`; JVM báo `BootstrapMethodError` trong linkage.

**Câu 5.** Trong ví dụ `LambdaIndyDemo`, tên indy là `apply` và site type là `()UnaryOperator`. Tại sao không phải `(String)String`?

**Đáp án:** Site tạo functional object. `(String)String` mô tả implementation method/instantiated SAM type, một static argument cho `LambdaMetafactory`, không phải type của factory site.

**Câu 6.** `compareAndSet` và `invokedynamic` đều liên quan runtime. Có thể gọi chúng là cùng một loại “bootstrap method” không?

**Đáp án:** Không. CAS là atomic update trên biến; invokedynamic bootstrap là thao tác liên kết dynamic call site. Chúng khác mục tiêu và API.

**Câu 7.** Nếu cùng một `IndyGenerated.run` được gọi tuần tự 1.000 lần sau successful linkage, BSM có bắt buộc chạy 1.000 lần không?

**Đáp án:** Không. Linkage được giữ để thực thi target ở các lần tiếp theo. Tuy nhiên không suy rộng thành cam kết mọi lần concurrent resolution chỉ gọi BSM một lần.

**Câu 8.** Một BSM ném `IllegalArgumentException` lúc tạo adapter; lỗi bên ngoài thường là gì? Nếu tự ném `LinkageError` thì sao?

**Đáp án:** `IllegalArgumentException` không phải `Error` nên quá trình resolution thất bại với `BootstrapMethodError` mang cause gốc. `Error` có thể được truyền ra chính nó theo quy tắc JVMS.

**Câu 9.** Muốn target có hai tham số static được bind sẵn, cần chỉnh đâu?

**Đáp án:** Trong BSM, dùng `insertArguments`/combinators phù hợp để đưa target ban đầu về đúng type của site. Static arguments không tự bị JVM loại khỏi target descriptor.

**Câu 10.** Tại sao không thể dùng `javap -c` đơn lẻ để hiểu đầy đủ static bootstrap arguments?

**Đáp án:** `javap -c` cho thấy opcode và constant-pool index, còn `javap -v` hiển thị `BootstrapMethods` và metadata cần thiết để liên hệ BSM với static arguments.

## 13. Tài liệu chuẩn Java 17

- JVMS 17, `5.4.3.6` — *Dynamically-Computed Constant and Call Site Resolution*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6
- JVMS 17, `4.4.10` — `CONSTANT_InvokeDynamic_info`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10
- JVMS 17, `4.7.23` — `BootstrapMethods` attribute: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.23
- JVMS 17, `6.5` — `invokedynamic` instruction: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic
- Java SE 17, `CallSite`, `ConstantCallSite`, `MutableCallSite`, `VolatileCallSite`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html
- Java SE 17, `LambdaMetafactory` và ba bootstrap static arguments cho lambda: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html
- Java SE 17, `MethodHandles.Lookup` / `MethodHandle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java SE 17, `BootstrapMethodError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/BootstrapMethodError.html

**Kết luận:** Hợp đồng của `invokedynamic` BSM là **JVM cấp `Lookup` của class gọi, tên site, `MethodType` của site và các static arguments đã mã hóa**, sau đó yêu cầu một `CallSite` khác null với target type đúng descriptor. BSM quyết định cách tìm/bind/thích nghi target; JVM giữ liên kết và thực thi target cho các dynamic arguments về sau. Phân biệt thật rõ **linkage inputs**, **static metadata** và **runtime call arguments** là chìa khóa để đọc `javap`, debug `BootstrapMethodError` và thiết kế bootstrap an toàn.