# invokedynamic, BootstrapMethods và liên kết điểm gọi động trong JVM

## Mục tiêu

Các lệnh gọi phương thức thường gặp trong bytecode Java như `invokestatic`, `invokevirtual`, `invokeinterface` và `invokespecial` có quy tắc liên kết dựa vào tham chiếu lớp/phương thức và kiểu gọi. **`invokedynamic`** bổ sung một cơ chế quan trọng: trình biên dịch cung cấp **mô tả điểm gọi** cùng một **bootstrap method** để JVM xác định *cách thức liên kết lời gọi* khi điểm gọi được sử dụng. Đây là nền tảng của nhiều đặc tính JVM hiện đại, đặc biệt là lambda và cách nối chuỗi được `javac` hiện đại sử dụng.

Sau bài, bạn có thể:
- Giải thích `invokedynamic` ở cấp instruction, operand stack và method descriptor.
- Lần theo `CONSTANT_InvokeDynamic` → `BootstrapMethods` → `MethodHandle` → `CallSite`.
- Phân biệt **bootstrap arguments tĩnh** trong class file với **arguments động** được đưa lên operand stack khi lời gọi chạy.
- Mô tả vòng đời của điểm gọi: chưa liên kết → bootstrap/link → lời gọi vào target, gồm lỗi bootstrap và các trường hợp race.
- Phân biệt `ConstantCallSite`, `MutableCallSite`, `VolatileCallSite`; nhận biết giới hạn visibility khi đổi target.
- Dùng Java 17+ biên dịch lambda/nối chuỗi, quan sát `javap -v -p` và hiểu tại sao index của constant pool không cố định.
- Phân biệt `CONSTANT_InvokeDynamic` với `CONSTANT_Dynamic` (condy) và tránh những nhận định sai như “`invokedynamic` gọi bootstrap mọi lần”.

## 1. Vì sao JVM cần một cơ chế gọi động?

Một ví dụ quen thuộc:

~~~java
object.toString();
~~~

Với lời gọi method instance thông thường, bytecode có thể mang `invokevirtual` với tham chiếu đến method được xác định bởi owner class, tên và method descriptor trong constant pool. JVM có quy tắc riêng để resolve phương thức và chọn implementation khi thực thi (ví dụ virtual dispatch).

Cơ chế trên không thuận tiện cho mọi yêu cầu của compiler/runtime: một call site có thể cần được **cấu hình bằng quy tắc riêng** mà compiler chỉ mô tả qua metadata. Đó là nơi `invokedynamic` có ích. Thay vì bytecode cố định một owner method theo mô hình gọi thông thường, nó chỉ đến **call site specifier**; JVM dùng **bootstrap method** do class file quy định để lấy một `CallSite` và method handle tương ứng.

Sơ đồ:

~~~text
Bytecode của caller
    |
    | invokedynamic #N
    v
CONSTANT_InvokeDynamic #N
    |
    +-- name_and_type_index --> tên điểm gọi + METHOD descriptor
    |
    +-- bootstrap_method_attr_index (bắt đầu từ 0)
            |
            v
        BootstrapMethods attribute
            |
            +-- bootstrap_method_ref --> CONSTANT_MethodHandle
            +-- bootstrap_arguments[] --> các entry constant pool
            |
            v
        Bootstrap Method được JVM gọi để liên kết
            |
            v
        CallSite có target là MethodHandle
            |
            v
        target được gọi bằng dynamic args trên operand stack
~~~

Sơ đồ này mô tả mối quan hệ logic, **không phải layout cố định trong bộ nhớ**. Những mục `#N` là chỉ số class file cụ thể; thứ tự, số index và một số tên do compiler quyết định. `invokedynamic` không có nghĩa mỗi lần chạy sẽ tìm lại phương thức bằng cách phân giải tên một cách chậm chạp.

### “Dynamic” nằm ở giai đoạn nào?

Có hai giai đoạn riêng:
1. **Liên kết điểm gọi (*linkage*)**: bootstrap được kích hoạt theo quy tắc resolution cho một instruction `invokedynamic` chưa liên kết, chuẩn bị một `CallSite` hợp lệ.
2. **Thực thi lời gọi (*invocation*)**: mỗi lần đi qua instruction, các arguments runtime được lấy từ operand stack để gọi target hiện hành của call site.

Cơ chế liên kết có thể chọn target một lần hoặc cung cấp `CallSite` có target thay đổi được, tùy loại call site và chương trình. Điều này khác với việc bootstrap cứ chạy lại trước từng invocation.

## 2. Instruction `invokedynamic` và operand stack

`invokedynamic` có opcode thập phân **186**, hệ 16 là **`0xBA`**. Định dạng trong class file:

~~~text
invokedynamic indexbyte1 indexbyte2 0 0

index = (indexbyte1 << 8) | indexbyte2
~~~

Hai byte chỉ số tạo thành operand không dấu 16 bit trỏ tới một **`CONSTANT_InvokeDynamic`** trong run-time constant pool của class hiện hành; **hai byte sau phải bằng 0** theo định dạng JVM. Khi xem bằng `javap -c`, bạn thường thấy:

~~~text
invokedynamic #N,  0  // InvokeDynamic #k:applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
~~~

Đây chỉ là **minh họa dạng hiển thị**: tên, descriptor và chỉ số phụ thuộc class đã biên dịch. `#N` sau opcode và `#k` trong chú thích có ý nghĩa khác: `#N` là constant pool index, còn `#k` thường thể hiện bootstrap method table index do `javap` định dạng.

**Method descriptor** ở `NameAndType` xác định kiểu tham số và kiểu trả về của *lời gọi tại chính điểm đó*. Ví dụ:

~~~text
(II)I                         // hai int -> int
(Ljava/lang/String;)V         // String -> void
(I)Ljava/lang/String;        // int -> String
()Ljava/lang/Runnable;       // không tham số -> Runnable
(I)Ljava/util/function/IntUnaryOperator; // int -> IntUnaryOperator
~~~

Với descriptor `(II)I`, trước lệnh operand stack có hai `int`:

~~~text
Stack trước:   ..., int1, int2
invokedynamic: lấy cả hai đối số, gọi target phù hợp
Stack sau:     ..., intResult
~~~

Nếu descriptor trả về `V` (void), không push giá trị trả về. Với `long`/`double`, JVM sử dụng category-2 value trên stack. Những tham số đã được đưa lên stack chính là **dynamic arguments**; chúng **khác** với bootstrap static arguments trong attribute.

Khác các lời gọi instance như `invokevirtual`, instruction `invokedynamic` không có một operand `objectref` ngầm định. Nếu muốn truyền receiver vào call target, receiver đó có thể là **tham số hiện rõ trong descriptor**, tức một dynamic argument thông thường.

## 3. Class file: `CONSTANT_InvokeDynamic`

Theo JVMS, entry có tag **18**:

~~~text
CONSTANT_InvokeDynamic_info {
    u1 tag;                            // 18
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}
~~~

Trong đó:
- **`bootstrap_method_attr_index`** trỏ đến **một phần tử trong bảng `bootstrap_methods[]`** thuộc attribute `BootstrapMethods` của class file. Chỉ số này **bắt đầu từ 0**, không phải chỉ mục constant pool.
- **`name_and_type_index`** trỏ đến `CONSTANT_NameAndType`; từ đây có thể đọc **unqualified name** và **method descriptor** của call site. Đây là một *method descriptor*, không phải field descriptor.
- `CONSTANT_InvokeDynamic` **không có `class_index`** kiểu `CONSTANT_Methodref`. Việc chọn method handle target là kết quả của bootstrap, không phải một phép resolve cố định trực tiếp theo owner/method của caller.
- Class file sử dụng các loại entry này phải tuân thủ yêu cầu phiên bản, đặc tả constant pool và thuộc tính bootstrap. `invokedynamic`/`CONSTANT_InvokeDynamic` có từ Java 7, tương ứng major class file 51 trở lên.

Đừng lấy tên call site làm một phương thức Java chắc chắn tồn tại. Tên được truyền tới bootstrap làm metadata để bootstrap diễn giải; **không nhất thiết có một method cùng tên được khai báo ở class owner nào đó**.

### Cách nhận biết dạng `NameAndType`

Giả sử `javap -v` cho ra những mục minh họa:

~~~text
#20 = InvokeDynamic      #0:#21    // #0:applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
#21 = NameAndType        #22:#23   // applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
#22 = Utf8               applyAsInt
#23 = Utf8               (I)Ljava/util/function/IntUnaryOperator;
~~~

Đây là **một đoạn giả lập để giải thích**, không phải output có thể dự đoán đúng từ mọi phiên bản compiler. Đọc theo chuỗi:
1. Entry `#20` có tag InvokeDynamic.
2. Số `#0` ở bootstrap portion chỉ phần tử **0** của attribute `BootstrapMethods`.
3. `#21` là `NameAndType` trong constant pool; từ đó mới đọc tên và descriptor.
4. Để biết phương thức bootstrap thực tế, xem **attribute `BootstrapMethods`**, không coi `#0` là `constant_pool[0]`.

## 4. Attribute `BootstrapMethods` chứa gì?

Attribute `BootstrapMethods` nằm ở **cấp class** trong `ClassFile`. Nếu constant pool có một hoặc nhiều `CONSTANT_InvokeDynamic` hoặc `CONSTANT_Dynamic`, class file phải có đúng **một** attribute `BootstrapMethods` theo quy tắc định dạng.

Sơ đồ rút gọn:

~~~text
BootstrapMethods_attribute {
    u2 attribute_name_index; // Utf8 "BootstrapMethods"
    u4 attribute_length;
    u2 num_bootstrap_methods;
    {
        u2 bootstrap_method_ref;
        u2 num_bootstrap_arguments;
        u2 bootstrap_arguments[num_bootstrap_arguments];
    } bootstrap_methods[num_bootstrap_methods];
}
~~~

Mỗi phần tử bootstrap table gồm:
- **`bootstrap_method_ref`**: chỉ mục constant pool tới một **`CONSTANT_MethodHandle`**, mô tả bootstrap method.
- **`bootstrap_arguments[]`**: dãy chỉ mục constant pool cho các **static bootstrap arguments** được phép. Từng argument được resolve/diễn giải theo loại hằng của nó.
- Bảng được đánh chỉ số **từ 0**; trong khi constant pool trong class file đánh chỉ số **từ 1** (vị trí 0 không dùng). Đây là lỗi đọc class file rất phổ biến.

Một bản `javap -v` có thể trình bày:

~~~text
BootstrapMethods:
  0: #40 REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory:...
    Method arguments:
      #47 (I)I
      #48 REF_invokeStatic Example.lambda$main$0:(II)I
      #47 (I)I
~~~

Các index/names ở trên chỉ nhằm **minh họa quan hệ bootstrap**; tên method synthetic và kiểu có thể khác. Điểm quan trọng là **method handle cho bootstrap** ở cùng bảng với **các hằng bổ sung** như `MethodType` hoặc `MethodHandle`. Những arguments này hỗ trợ bootstrap tạo một target khớp descriptor của call site.

### Hai nhóm arguments không được nhầm lẫn

| Nhóm | Nguồn | Có ở thời điểm nào? | Ví dụ |
| --- | --- | --- | --- |
| **Bootstrap static arguments** | `bootstrap_arguments[]` trỏ vào constant pool | Khi bootstrap/link point được xử lý | MethodType của SAM, MethodHandle của lambda body, recipe nối chuỗi |
| **Bootstrap JVM-supplied arguments** | JVM cung cấp khi gọi bootstrap | Khi resolution call site | `MethodHandles.Lookup`, call site name, `MethodType` của lời gọi |
| **Dynamic invocation arguments** | Operand stack tại `invokedynamic` | **Mỗi lần** instruction được thực thi | Giá trị captured từ scope, số để nối chuỗi, receiver theo descriptor |

Các bootstrap arguments **không tự xuất hiện trên operand stack của chương trình caller**. Ngược lại, các dynamic arguments **không phải metadata trong BootstrapMethods**: chúng biến đổi giữa các lần chạy lệnh.

## 5. Vòng đời liên kết (*linkage*) của một call site

Quy trình khái quát khi JVM lần đầu thực thi một instruction `invokedynamic` chưa liên kết:

1. **Đọc symbolic reference** `CONSTANT_InvokeDynamic` của instruction, gồm tên/descriptor và bootstrap table index.
2. **Resolve các hằng cần thiết** như `MethodHandle` của bootstrap và static arguments, xác định `MethodType` của call site.
3. **Chuẩn bị đối số cho bootstrap**. Trong trường hợp bootstrap điển hình, ba đối số đầu gồm `MethodHandles.Lookup` với quyền của caller, tên call site kiểu `String`, `MethodType` của call site; tiếp theo là các static arguments đã được định nghĩa. Signature thực tế phải tương thích với quy tắc gọi bootstrap.
4. **Gọi bootstrap method** được chỉ định bằng method handle. Bootstrap quyết định cách tạo target và trả một đối tượng **`CallSite`** thích hợp.
5. **Kiểm tra kết quả**: không null, là `CallSite` và **type của CallSite tương thích đúng với method descriptor được chỉ định**. Nếu không thỏa, quá trình resolution thất bại.
6. **Gắn kết quả với instruction call site đó**. Những lần thực thi tiếp theo của **chính instruction ấy** sử dụng kết quả đã được liên kết để gọi target tương ứng (có thể thay đổi nếu là loại CallSite cho phép).

~~~text
Lần đầu instruction indy chạy
   |
   v
Kiểm tra call site đã liên kết?
   |
   +-- CHƯA --> resolve bootstrap metadata
   |                |
   |                v
   |          gọi bootstrap method
   |                |
   |                v
   |          validate CallSite + type
   |                |
   |                v
   |          gắn kết quả cho instruction
   |
   +-- RỒI ------+
                 |
                 v
       đọc target của CallSite theo semantics loại site
                 |
                 v
       truyền dynamic args -> gọi MethodHandle
                 |
                 v
       trả kết quả lên operand stack nếu không void
~~~

**Không khẳng định bootstrap luôn chạy chính xác một lần vật lý.** JVMS cho phép những thread khác nhau có thể cùng cố resolve một site chưa liên kết; bootstrap có thể được kích hoạt bởi hơn một thread trong cuộc đua, nhưng **chỉ một kết quả được chọn làm liên kết chính thức**. Do đó bootstrap nên tránh side effect không idempotent hoặc phải xử lý được việc gọi cạnh tranh. Khi site đã liên kết thành công, các lần thực thi tiếp theo của *instruction đó* không liên kết lại như một site mới.

### Điểm gọi nào được cache?

Cần phân biệt **một entry constant pool** và **một occurrence của instruction `invokedynamic`**. Quy tắc resolution của indy gắn liên kết với **chính occurrence instruction**; hai instruction `invokedynamic` khác nhau có thể tham chiếu cùng một symbolic entry nhưng vẫn có kết quả resolution riêng. Vì vậy không thể suy luận “cùng `#N` thì hai vị trí bytecode phải sử dụng cùng một `CallSite`”.

Tương tự, việc gọi một method Java chứa instruction `invokedynamic` nhiều lần **không tạo call site mới theo từng lần gọi method**. Call site thuộc vị trí instruction trong class hiện hành, không phải từng frame stack đang hoạt động.

### Frame và method invocation

Liên kết một call site là hoạt động của JVM ở cấp runtime, nhưng khi target được gọi, **method handle invocation** vẫn phải tuân thủ kiểu tham số/trả về và các quy tắc invocation. Không tồn tại một “frame BootstrapMethods” cố định cho mọi lần gọi: bootstrap được gọi ở giai đoạn link, còn target được gọi ở giai đoạn thực thi instruction. JVM/JIT có thể tối ưu implementation thực tế, nhưng semantics quan sát được phải phù hợp với liên kết và target hiện hành của `CallSite`.

## 6. `CallSite` và `MethodHandle`

**`MethodHandle`** là một giá trị runtime có kiểu `MethodType`, biểu diễn khả năng gọi một mục tiêu theo cơ chế được định nghĩa. **`CallSite`** là đối tượng nắm giữ một **target MethodHandle** của một điểm gọi động.

Ba nhóm CallSite thường gặp:

| Loại | Target sau khi tạo | Điều cần chú ý |
| --- | --- | --- |
| **`ConstantCallSite`** | Không đổi sau khởi tạo hợp lệ | Phù hợp khi target của điểm gọi đã cố định; dễ tối ưu. |
| **`MutableCallSite`** | Có thể thay đổi bằng `setTarget` | Việc quan sát target mới ở các thread khác có quy tắc visibility riêng; `MutableCallSite.syncAll` là công cụ đồng bộ hóa thay đổi. |
| **`VolatileCallSite`** | Có thể thay đổi, đọc/ghi target có semantics tương tự volatile | Hữu ích khi cần visibility mạnh hơn mà không muốn tự quản lý đồng bộ site mutable. |

**`MethodHandle` không tự đồng nghĩa `Methodref` trong constant pool.** `CONSTANT_MethodHandle` là *mô tả nhị phân* để tạo/resolve một method handle; `java.lang.invoke.MethodHandle` là *đối tượng runtime*. Bootstrap có thể kết hợp/adapt các handle để tạo target, và `CallSite` nắm target sẽ được gọi.

**Loại của target quan trọng:** bootstrap phải trả một `CallSite` có `type()` khớp với call site descriptor. Nếu không khớp, không thể lấy một target có tham số/trả về bất kỳ rồi mặc kệ để JVM “tự đoán”; bootstrap phải dùng các combinator như `asType`, `bindTo`, `insertArguments` hoặc dựng handle đúng kiểu khi cần.

### Thay target và tính hiển thị giữa các thread

Với `MutableCallSite`, `setTarget` thay target, nhưng việc nhiều thread cùng thực thi có thể tiếp tục thấy target cũ nếu không thiết lập visibility thích hợp. `syncAll` giúp đồng bộ thay đổi theo contract của `MutableCallSite`, nhưng không phải cơ chế transaction của toàn ứng dụng. Với `VolatileCallSite`, target có semantics tương tự thao tác volatile cho việc đọc/ghi target; chi phí và nhu cầu đồng bộ khác nhau tùy trường hợp.

**CallSite không có nghĩa một method body Java bị “ghi đè” hoặc “chỉnh sửa” khi chạy.** Nó chọn *method handle target* cho vị trí gọi, có thể chuyển từ behavior A sang B, trong khi class/method bytecode không nhất thiết bị sửa.

## 7. Ví dụ chạy được Java 17+: lambda và nối chuỗi

Lập trình viên không có cú pháp Java nguồn tương đương một cách trực tiếp với instruction `invokedynamic`. Thay vào đó, **compiler** phát instruction khi cần. Hai ví dụ phổ biến của `javac` hiện đại là **lambda expression** và **string concatenation**.

Tạo tệp **`InvokeDynamicDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class InvokeDynamicDemo {
    private static String message(int value) {
        return "value=" + value;
    }

    public static void main(String[] args) {
        int offset = 3;
        IntUnaryOperator addOffset = n -> n + offset;

        System.out.println("lambda=" + addOffset.applyAsInt(7));
        System.out.println("concat=" + message(42));
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac --release 17 InvokeDynamicDemo.java
java InvokeDynamicDemo
~~~

**Stdout chính xác:**

~~~text
lambda=10
concat=value=42
~~~

Phân tích:
- Biến `offset = 3` được lambda capture. Lambda `n -> n + offset` sau khi chuyển thành một implementation của `IntUnaryOperator` cộng `n` với 3; `applyAsInt(7)` trả 10.
- Biểu thức nối chuỗi `"value=" + value` trả `"value=42"`.
- `System.out.println` là lời gọi API Java bình thường; không phải bản thân từ `println` là một opcode indy.

Quan sát bytecode:

~~~bash
javap -c -p InvokeDynamicDemo
javap -v -p InvokeDynamicDemo
~~~

Trong **`javac --release 17` thông thường**:
- `main` có một `invokedynamic` liên quan đến tạo instance functional interface cho lambda; bootstrap thường tham chiếu `java/lang/invoke/LambdaMetafactory.metafactory`.
- `message` có thể có một `invokedynamic` phục vụ nối chuỗi; bootstrap thường tham chiếu `java/lang/invoke/StringConcatFactory.makeConcatWithConstants`.
- Có thể thấy một method synthetic dạng `lambda$main$0` được compiler tạo để chứa thân lambda. **Không được phụ thuộc chính xác vào tên/đánh số synthetic method**, thứ tự hoặc chỉ mục `#N`.
- Những biểu thức ghép chuỗi khác trong `main` cũng có thể tạo các indy call site. Các chỉ mục constant pool/recipe khác nhau theo cách compiler sinh code.

Ví dụ một dạng disassembly **rút gọn, chỉ để nhận diện**:

~~~text
invokedynamic #N, 0  // InvokeDynamic #k:applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
...
invokeinterface #M   // InterfaceMethod IntUnaryOperator.applyAsInt:(I)I
...
invokedynamic #P, 0  // InvokeDynamic #j:makeConcatWithConstants:(I)Ljava/lang/String;
~~~

**Phân biệt hai invocation!** `invokedynamic` trong trường hợp lambda thường **tạo đối tượng functional interface ở call site**; việc gọi `addOffset.applyAsInt(7)` sau đó có thể sử dụng `invokeinterface`, không phải mọi lần gọi lambda đều thực thi cùng opcode indy. Bootstrap có nhiệm vụ tạo linkage/factory hành vi; call site của việc *tạo lambda object* là một lớp nghĩa riêng với method invocation trên object đó.

## 8. Đi sâu vào LambdaMetafactory

Với lambda hoặc method reference, `javac` thường sử dụng `LambdaMetafactory` để tạo một factory cho implementation functional interface. Bộ thông tin điển hình gồm:

1. **Lookup:** bối cảnh truy cập của class caller.
2. **Invoked name:** thường liên quan tên abstract method của functional interface, ví dụ `applyAsInt`.
3. **Invoked type:** descriptor tại vị trí call site, trả về functional interface; tham số có thể là các captured values, ví dụ `(I)Ljava/util/function/IntUnaryOperator;`.
4. **SAM method type:** chữ ký abstract method mà functional interface yêu cầu, ví dụ `(I)I`.
5. **Implementation method handle:** tham chiếu đến lambda body synthetic/static/instance method hoặc một method reference phù hợp.
6. **Instantiated method type:** method type sau khi áp dụng generic adaptation/instantiation của lambda.

Từ đó bootstrap có thể sản xuất một `ConstantCallSite` mà target là **factory method handle**, có chức năng tạo một object tương thích functional interface. Khi Java chạy `n -> n + offset`, giá trị capture thường được truyền như **dynamic argument** vào factory của call site. Khi gọi `applyAsInt` trên instance kết quả, implementation được sinh sẽ chuyển tiếp tới logic lambda body.

### Tính capture và “stateless”

Nếu lambda **không capture** biến nào, invoked type có thể có descriptor không tham số và có thể được triển khai bằng cách tái sử dụng một instance. Tuy nhiên, **không được phụ thuộc identity** (¤==¤) của hai lambda object từ những lần đánh giá khác nhau: đặc tả ngôn ngữ không hứa object mới mỗi lần hay một singleton ổn định.

Nếu lambda capture một giá trị, invoked type có thể mang các captured values làm tham số, ví dụ `(I)Ljava/util/function/IntUnaryOperator;`. Điều này không có nghĩa body của lambda chạy tại thời điểm tạo factory; tạo lambda instance và gọi method của instance là **hai hành động khác nhau**.

### Method reference không phải một API gọi động riêng

Biểu thức nguồn `String::length` hoặc `MyClass::staticMethod` cũng có thể được compiler triển khai qua `LambdaMetafactory`. Nhưng đây là lựa chọn **của compiler theo phiên bản/chiến lược**, không phải lời hứa mọi expression dạng `::` đều phát chính xác một lệnh indy. Quan sát bytecode thực tế thay vì gán cứng số lượng opcode.

## 9. Nối chuỗi qua StringConcatFactory

Kể từ Java 9, `javac` thường triển khai toán tử nối chuỗi `+` qua `invokedynamic` với một bootstrap `StringConcatFactory`, thay vì luôn dựng một chuỗi `new StringBuilder().append(...).toString()` trực tiếp tại mỗi call site như những bytecode cũ.

Ví dụ:

~~~java
static String describe(String name, int age) {
    return "name=" + name + ", age=" + age;
}
~~~

Đây là **method minh họa** cần đặt trong một class; có thể biên dịch trong ví dụ chương trình đầy đủ nếu muốn. Với target Java 17, compiler thường dùng một call site có invoked type tương ứng với các biến động, kiểu như:

~~~text
(Ljava/lang/String;I)Ljava/lang/String;
~~~

Bootstrap `StringConcatFactory.makeConcatWithConstants` có thể được cung cấp một **recipe string** trong các static arguments, trong đó một số ký tự đánh dấu vị trí dynamic arguments hoặc static constants. **Recipe là metadata bootstrap**, không phải dynamic input truyền từ stack mỗi lần gọi.

Khi runtime chạy expression với `name="An"`, `age=20`, các giá trị `"An"` và `20` mới là dynamic arguments được đặt lên stack rồi đi qua call site để tạo chuỗi kết quả. Cùng call site có thể chạy tiếp với `name="Binh"`, `age=21` mà **không cần bootstrap lại để biết một method nào sẽ được dùng**.

### Có phải kết quả String cũng là CallSite?

Không. **CallSite** là đối tượng liên kết cho instruction. **String** là kết quả của việc target xử lý các arguments tại runtime. Trộn hai khái niệm này dễ dẫn đến lập luận sai như “mỗi lần nối chuỗi tạo một CallSite” hoặc “BootstrapMethods chứa từng chuỗi kết quả”.

## 10. Ví dụ Java API độc lập: đổi target của MutableCallSite

Để hiểu CallSite tốt hơn, ta có thể thao tác `java.lang.invoke` trực tiếp bằng Java chuẩn. **Ví dụ dưới đây không tự phát opcode `invokedynamic` tùy biến.** Nó sử dụng public API để cho thấy target của một `CallSite` có thể được thay đổi. Vì mã nguồn Java không có toán tử gọi `invokedynamic` trực tiếp, bạn cần compiler hoặc một bộ sinh class file/bytecode khi muốn định nghĩa call site tùy biến trong bytecode.

Tạo tệp **`MutableSiteDemo.java`**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;

public class MutableSiteDemo {
    private static String first(String name) {
        return "A:" + name;
    }

    private static String second(String name) {
        return "B:" + name;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(String.class, String.class);

        MethodHandle initial = lookup.findStatic(
                MutableSiteDemo.class, "first", type);

        MutableCallSite site = new MutableCallSite(initial);
        MethodHandle invoker = site.dynamicInvoker();

        String before = (String) invoker.invokeExact("x");
        System.out.println("before=" + before);

        MethodHandle replacement = lookup.findStatic(
                MutableSiteDemo.class, "second", type);

        site.setTarget(replacement);
        MutableCallSite.syncAll(new MutableCallSite[] { site });

        String after = (String) invoker.invokeExact("x");
        System.out.println("after=" + after);
    }
}
~~~

Biên dịch và chạy Java 17+:

~~~bash
javac --release 17 MutableSiteDemo.java
java MutableSiteDemo
~~~

**Stdout chính xác:**

~~~text
before=A:x
after=B:x
~~~

Giải thích:
- `MethodType.methodType(String.class, String.class)` mô tả target nhận một `String` và trả một `String`.
- `findStatic` lấy method handle của `first`. `MutableCallSite` giữ target đó.
- `dynamicInvoker()` trả handle mà hành vi theo target hiện tại của site.
- `setTarget(replacement)` đổi target; `syncAll` thể hiện cách phát tín hiệu đồng bộ khi có nhiều thread quan sát site. Trong ví dụ single-thread, kết quả đầu/ cuối có thể xác định như đã in.
- `invokeExact("x")` đòi kiểu tham số và kiểu trả về chính xác theo `MethodType`; cast `(String)` ở call site giúp compiler phát chữ ký return phù hợp cho invocation.

**Không nhầm `CallSite` với `invokedynamic`:** API Java này minh họa đối tượng site và method handles. Lệnh gọi `MethodHandle.invokeExact` trong class file có quy tắc đặc biệt của `invokevirtual` signature-polymorphic; đó không phải cách chứng minh đã phát ra một instruction `invokedynamic` tùy biến. Với ví dụ lambda ở trên, bạn mới quan sát một trường hợp compiler thực sự phát indy.

## 11. Phân biệt invokedynamic và dynamic constant (condy)

Cả `CONSTANT_InvokeDynamic` và `CONSTANT_Dynamic` cùng dùng bootstrap table nhưng mục đích khác nhau.

| Tiêu chí | `CONSTANT_InvokeDynamic` | `CONSTANT_Dynamic` |
| --- | --- | --- |
| Constant pool tag | **18** | **17** |
| Dùng để | Mô tả **điểm gọi** cần liên kết | Mô tả **giá trị hằng** cần tính khi resolve |
| `NameAndType` descriptor | **Method descriptor** như `(I)Ljava/lang/String;` | **Field descriptor** như `Ljava/lang/String;` hoặc `J` |
| Cách sử dụng | Opcode **`invokedynamic`** | Một trong các lệnh nạp hằng `ldc`/`ldc_w`/`ldc2_w` theo kiểu và quy tắc |
| Kết quả bootstrap | Một **`CallSite`** tương thích descriptor | Một **giá trị** tương thích kiểu hằng được mô tả |
| Có mặt từ | Class file major **51** (Java 7) | Class file major **55** (Java 11) |

**BootstrapMethods** có thể chứa các entry phục vụ cả hai loại. Điều đó **không** làm hai loại trở thành một: indy là cơ chế gọi; condy là cơ chế tính hằng. Nếu thấy `Dynamic` trong `javap -v`, đừng tự động kết luận class có instruction `invokedynamic`.

### Các loại reference liên quan cũng khác nhau

| Loại constant pool | Công dụng |
| --- | --- |
| `CONSTANT_Methodref` | Symbolic reference cho method class trong quy tắc resolve thông thường |
| `CONSTANT_InterfaceMethodref` | Symbolic reference cho method interface |
| `CONSTANT_MethodHandle` | Mô tả method handle, gồm reference kind và index đến reference phù hợp |
| `CONSTANT_MethodType` | Mô tả một method type qua descriptor |
| `CONSTANT_InvokeDynamic` | Mô tả điểm gọi động, trỏ đến bootstrap index và `NameAndType` |
| `CONSTANT_Dynamic` | Mô tả hằng động, trỏ đến bootstrap index và `NameAndType` |

Tuy tên nhiều entry bắt đầu `CONSTANT_`, **constant pool không chỉ chứa giá trị literal**. Nó cũng chứa metadata giúp JVM liên kết code vào runtime.

## 12. Lỗi trong liên kết điểm gọi động

Khi bootstrap không thể chạy/không thể cho ra kết quả hợp lệ, JVM thường báo **`BootstrapMethodError`**, một dạng lỗi liên kết. Các trường hợp cần xem xét:

- Bootstrap method handle không thể resolve do lớp/entry sai, access hoặc binary không tương thích.
- Bootstrap ném exception, khởi tạo dependency thất bại, hoặc thực hiện logic lỗi.
- Bootstrap trả **null** hoặc một đối tượng không phải `CallSite` trong trường hợp indy.
- Bootstrap trả `CallSite` có type không khớp method descriptor của điểm gọi.
- `BootstrapMethods`/constant pool chứa index hoặc tag không hợp lệ, class file không thỏa format/verification constraints — một số tình huống có thể biểu hiện thành **`ClassFormatError`, `VerifyError` hoặc lỗi liên kết khác**, không nhất thiết đều được bọc thành `BootstrapMethodError`.

**Không chẩn đoán tất cả lỗi `BootstrapMethodError` là “thiếu class lambda”.** Hãy xem nguyên nhân gốc, call site name/type, bootstrap method handle, static arguments, class loading và phiên bản dependency liên quan.

### Khi bootstrap thất bại thì sao?

Sau khi JVM xác định resolution của một instruction indy **thất bại**, lần thử tiếp theo của **cùng instruction** không tự động gọi lại bootstrap để “thử vận may” theo mỗi invocation. Lỗi resolution được duy trì theo semantics đặc tả. Điều này quan trọng: bootstrap không phải cơ chế retry cho network, IO hoặc registry tạm thời bị lỗi. Nếu muốn runtime logic có thể thay đổi, nên liên kết thành công đến một `CallSite` có target thích hợp để chính target xử lý retry/fallback theo thiết kế.

### Vấn đề concurrency trong bootstrap

Nếu hai thread cùng chạm đến một điểm gọi chưa liên kết, JVM có thể cho phép bootstrap được chạy nhiều lần trong một cuộc đua. Mặc dù một kết quả được công nhận để liên kết instruction, **side effects xảy ra trong những bootstrap executions không được chọn có thể vẫn quan sát được**. Vì vậy bootstrap nên có logic thuần/ít side effect, hoặc được thiết kế idempotent và thread-safe khi cập nhật cache/registry.

### Đổi target không đúng kiểu

Với một `CallSite` đã liên kết, `setTarget` trên loại cho phép thay đổi vẫn phải tôn trọng type tương ứng; target không tương thích sẽ gây lỗi tại API. Không thể đổi từ handle `(int)int` sang `(String)String` cho cùng call site chỉ bằng cách gán tùy ý.

## 13. Cách đọc javap từng bước

Với `InvokeDynamicDemo.class`, làm theo các bước:

1. Chạy `javap -c -p InvokeDynamicDemo` để xác định các instruction `invokedynamic` ở phương thức nào và operand index `#N` là bao nhiêu.
2. Chạy `javap -v -p InvokeDynamicDemo`. Trong phần **Constant pool**, tìm `#N = InvokeDynamic #k:#m`.
3. Theo `#m` đến `NameAndType`, rồi xem **tên call site** và **method descriptor**. Descriptor cho biết dynamic arguments cần nằm trên operand stack.
4. Theo **`#k` trong chú thích/bảng** đến phần **BootstrapMethods** cuối output. Lưu ý index bootstrap bắt đầu từ 0.
5. Trong entry bootstrap, đọc `REF_invokeStatic ...LambdaMetafactory.metafactory` hoặc `...StringConcatFactory.makeConcatWithConstants` nếu dùng `javac` theo cấu hình ví dụ.
6. Theo các **Method arguments** là static bootstrap arguments như method handle, method type, recipe; không xem chúng là dữ liệu runtime truyền mỗi lần.
7. Đối chiếu bytecode chuẩn bị stack ngay trước instruction `invokedynamic`: các ¤iload`, ¤aload` hoặc opcode khác đưa dynamic arguments đúng descriptor.
8. Xem instruction **sau** indy: call site trả kết quả gì? Nếu trả functional interface, sẽ có đoạn code tiếp theo lưu/thực thi instance ấy, thường bằng `invokeinterface`.
9. Ghi rõ compiler, target class file và kết quả trong ghi chép; **không hardcode các chỉ số `#N`** giữa các lần biên dịch.

### Dạng bản đồ ở javap

~~~text
Code:
  ...
  invokedynamic #N, 0      // InvokeDynamic #k:someName:(I)Ljava/lang/Runnable;
  ...

Constant pool:
  #N = InvokeDynamic #k:#m  // #k:someName:(I)Ljava/lang/Runnable;
  #m = NameAndType   #a:#b
  #a = Utf8          someName
  #b = Utf8          (I)Ljava/lang/Runnable;
  ...

BootstrapMethods:
  k: #handle REF_invokeStatic some/bootstrap/Owner.bootstrap:...
    Method arguments:
      #arg1 ...
      #arg2 ...
~~~

Đây là **mẫu biểu diễn tổng quát**, không phải output exact của một class hay câu khẳng định bootstrap luôn nằm ở class tên `some.bootstrap.Owner`. Trong một bản dump, `javap` có thể in nhiều mức comment đã diễn giải giúp đọc dễ hơn.

## 14. Tình huống thực tế và lỗi tư duy phổ biến

| Nhận định/tình huống | Phân tích đúng |
| --- | --- |
| “`invokedynamic` là gọi method có tên lưu trong constant pool, giống `invokevirtual`.” | Indy liên kết qua bootstrap được chỉ định; call site name/type là metadata, target lấy từ `CallSite`. |
| “Bootstrap chạy trước mỗi lần lambda được gọi.” | Bootstrap phục vụ liên kết site; lambda object có thể được tạo qua linked site, sau đó SAM method được gọi bằng cơ chế khác. |
| “Một entry `InvokeDynamic` phải có một target chung cho mọi instruction tham chiếu.” | Linkage của call site gắn theo **occurrence instruction**. |
| “Bootstrap luôn chỉ chạy một lần vật lý.” | Những thread race có thể thực hiện nhiều bootstrap executions; chỉ một kết quả được chọn. |
| “BootstrapMethod index `#0` là entry constant pool số 0.” | Bootstrap table có chỉ số bắt đầu 0; constant pool bắt đầu 1. |
| “Dynamic arguments là Method arguments liệt kê trong `BootstrapMethods`.” | Method arguments ở attribute là **static bootstrap arguments**; dynamic invocation arguments nằm trên operand stack. |
| “`CallSite` là kết quả String của phép nối chuỗi.” | CallSite mô tả target đã liên kết; String là kết quả mỗi lần invocation. |
| “`MutableCallSite.setTarget` khiến mọi thread lập tức thấy target mới.” | Có quy tắc visibility; dùng `syncAll` hoặc `VolatileCallSite` khi phù hợp. |
| “Thấy `invokedynamic` nghĩa là JVM phải dùng reflection.” | Cơ chế chính dựa trên MethodHandle/CallSite, không đồng nghĩa `java.lang.reflect.Method.invoke`. |
| “`invokedynamic` luôn chậm do bootstrap.” | Bootstrap là chi phí liên kết site; sau đó JIT có thể tối ưu, nhưng hiệu năng phụ thuộc target, site kind và workload. |
| “Lambda lúc nào cũng tạo class file riêng trước runtime.” | Compiler/runtime có thể tạo implementation linh hoạt; đừng suy luận cấu trúc file dựa vào một cách triển khai. |
| “Bất kỳ method handle nào cũng có thể là bootstrap.” | Phải thỏa quy tắc về kiểu đối số/return và yêu cầu CallSite/type. |
| “Có `Dynamic` trong constant pool tức là có call site indy.” | `CONSTANT_Dynamic` là hằng động (condy); nó khác `CONSTANT_InvokeDynamic`. |
| “Tất cả tên synthetic lambda sẽ mãi theo một format.” | Tên/số lượng method sinh ra là chi tiết compiler. |
| “Bootstrap lỗi có thể retry tự do trong lần gọi tiếp theo.” | Resolution thất bại có quy tắc cache lỗi; không tự lặp lại bootstrap theo invocation. |

## 15. Khi nào lập trình viên cần biết cơ chế này?

Bạn sẽ thường **không cần tự tạo indy call site** trong code nghiệp vụ Java thường ngày. Kiến thức này hữu ích khi:

- **Đọc bytecode**: hiểu tại sao `javap -c` cho thấy `invokedynamic` dù trong Java source chỉ có lambda hoặc phép nối chuỗi.
- **Chẩn đoán lỗi linking**: khi thấy `BootstrapMethodError`/`LambdaConversionException` hoặc lỗi khi chạy class được sinh bằng bytecode tooling.
- **Phát triển compiler/ngôn ngữ JVM hoặc bytecode tooling**: tạo bootstrap, call site descriptors, dynamic constants, method handles và thông tin đúng trong `BootstrapMethods`.
- **Hiểu hiệu năng/JIT**: phân biệt chi phí liên kết một lần với invocation liên tục; đánh giá target ổn định so với target có thể đổi.
- **Thiết kế hệ thống thay đổi hành vi runtime**: dùng MethodHandle/CallSite API khi thực sự có nhu cầu dynamic linking, đồng thời kiểm soát thread safety, type safety và quan sát behavior.

Nếu chỉ muốn gọi method Java thông thường, không nên chọn invokedynamic như một “mẹo tối ưu” mặc định. Tập opcode `invoke*` mỗi loại có semantics riêng, và cách compiler sử dụng chúng phải dựa vào yêu cầu chương trình.

## 16. Tự kiểm tra

**Câu 1.** `invokedynamic` có bắt buộc chứa class owner của method target trong `CONSTANT_InvokeDynamic` không?

**Đáp án:** Không. Entry chứa **bootstrap_method_attr_index** và **name_and_type_index**. Bootstrap xác định target bằng cách trả CallSite, không phải chỉ theo owner/method reference như `Methodref`.

**Câu 2.** Chỉ số 0 ở `BootstrapMethods` có phải là `constant_pool[0]`?

**Đáp án:** Không. Danh sách `bootstrap_methods[]` bắt đầu tại 0, constant pool bắt đầu tại 1. Trong bootstrap entry còn có `bootstrap_method_ref` trỏ ngược đến constant pool.

**Câu 3.** Call site `(I)Ljava/lang/String;` nhận và trả những gì?

**Đáp án:** Mỗi invocation nhận một dynamic argument kiểu int từ operand stack và trả reference đến String trên stack. Nó không nói gì về số static bootstrap arguments.

**Câu 4.** Tại sao `LambdaMetafactory` cần implementation method handle?

**Đáp án:** Bootstrap cần biết logic phương thức nào sẽ được implementation của functional interface gọi. Method handle mô tả implementation, trong khi SAM method type và instantiated method type mô tả hợp đồng kiểu.

**Câu 5.** Gọi lambda `op.applyAsInt(5)` có phải luôn thực thi `invokedynamic` lần nữa không?

**Đáp án:** Không. `invokedynamic` thường được dùng để tạo factory/object lambda; gọi method trên object sau đó có thể dùng `invokeinterface` hoặc cơ chế gọi phù hợp khác.

**Câu 6.** Hai instruction indy ở vị trí bytecode khác nhau tham chiếu cùng entry constant pool. Có chắc chỉ một CallSite không?

**Đáp án:** Không. Linkage thành công được xác lập theo **instruction occurrence**, dù symbolic constant pool entry giống nhau.

**Câu 7.** Bootstrap trả `null` hoặc CallSite sai type thì sao?

**Đáp án:** Resolution call site thất bại, thường gây `BootstrapMethodError` theo quy tắc JVMS.

**Câu 8.** Tại sao bootstrap cần tránh side effect không idempotent?

**Đáp án:** Vì các thread có thể cạnh tranh resolve cùng site chưa liên kết, gây nhiều bootstrap execution, nhưng chỉ một kết quả được chọn.

**Câu 9.** `MutableCallSite` khác `ConstantCallSite` ở đâu?

**Đáp án:** Target của MutableCallSite có thể thay đổi bằng `setTarget` và cần chú ý visibility, còn ConstantCallSite giữ target không đổi sau khi khởi tạo thích hợp.

**Câu 10.** `CONSTANT_Dynamic` có mang method descriptor cho việc gọi method không?

**Đáp án:** Không. `CONSTANT_Dynamic` mô tả **hằng động** với **field descriptor**; method descriptor dành cho `CONSTANT_InvokeDynamic`.

**Câu 11.** Gặp `BootstrapMethodError` tại lần gọi đầu, có nên thử lặp lại cùng instruction để bootstrap tự chạy lại không?

**Đáp án:** Không. JVM duy trì trạng thái lỗi resolution theo đặc tả. Xác định và sửa vấn đề bootstrap, type, class loading hoặc dependency.

**Câu 12.** Nếu thay target của `MutableCallSite` trong một thread, mọi thread khác có lập tức thấy không?

**Đáp án:** Không tự động bảo đảm như volatile trong mọi trường hợp. Cần dùng `syncAll` hoặc thiết kế phù hợp như `VolatileCallSite` theo yêu cầu visibility.

## 17. Bản đồ ghi nhớ

~~~text
ClassFile
  |
  +-- constant_pool
  |     +-- CONSTANT_InvokeDynamic (tag 18)
  |             +-- NameAndType  -> name + METHOD descriptor
  |             +-- bootstrap_method_attr_index -> BootstrapMethods[k]
  |
  +-- BootstrapMethods attribute
        +-- bootstrap_method_ref  -> CONSTANT_MethodHandle
        +-- bootstrap_arguments[] -> CONSTANT_* hỗ trợ

Runtime:
  opcode invokedynamic #N, 0
             |
             v
      [site chưa liên kết?]
             |
             +-- yes -> resolve metadata -> gọi bootstrap
             |                            -> validate CallSite / type
             |                            -> gắn kết quả cho instruction
             |
             v
         target MethodHandle
             |
             +-- ConstantCallSite: target ổn định
             +-- MutableCallSite : target đổi được, chú ý sync
             +-- VolatileCallSite: target đổi được, volatile semantics
             |
             v
       dynamic args từ operand stack
             |
             v
       thực thi target -> push return nếu khác void
~~~

**Điểm quan trọng:** `invokedynamic` cung cấp **điểm gọi có liên kết tùy biến qua bootstrap**; `BootstrapMethods` mang phương thức và hằng phục vụ liên kết; `CallSite` là kết quả liên kết giữ target MethodHandle; còn các **dynamic arguments** chỉ được truyền khi thực sự gọi. Tách rõ bốn khái niệm này là chìa khóa để hiểu lambda, nối chuỗi và call-site linking ở JVM.

## Tài liệu tham khảo chính thức

- [JVMS Java SE 21 — `4.4.10` CONSTANT_InvokeDynamic và CONSTANT_Dynamic](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4.10).
- [JVMS Java SE 21 — `4.7.23` BootstrapMethods attribute](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.23).
- [JVMS Java SE 21 — `5.4.3.6` Dynamic constant và call site resolution](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3.6).
- [JVMS Java SE 21 — `6.5` invokedynamic](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.invokedynamic).
- [Java SE 17 API — CallSite](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html).
- [Java SE 17 API — LambdaMetafactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html).
- [Java SE 17 API — StringConcatFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html).
- [JDK 17 javap tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
