# `invokestatic`, `invokespecial`, `invokevirtual` và `invokeinterface` trong JVM

## 1. Bốn lệnh gọi phương thức giải quyết những vấn đề khác nhau

Mã nguồn Java có thể dùng cùng một cú pháp `object.method(...)` hoặc `Type.method(...)`, nhưng ở mức JVM, trình biên dịch phải chọn một **instruction gọi phương thức** phù hợp với tính chất method và cách liên kết. Bốn lệnh cần phân biệt là:

| Instruction | Vai trò chính | Có receiver object trên operand stack? | Cách chọn method cần thực thi |
| --- | --- | --- | --- |
| `invokestatic` | Gọi **static method** của class hoặc interface | **Không** | Dựa trên symbolic reference tới static method đã được resolve; không dispatch theo kiểu runtime của object |
| `invokespecial` | Gọi instance initialization method `<init>`, lời gọi `super` và những lời gọi instance có quy tắc đặc biệt | **Có** | Áp dụng special lookup/selection của JVMS; không phải dispatch override thông thường của `invokevirtual` |
| `invokevirtual` | Gọi instance method thông thường qua **class type** | **Có** | Chọn implementation theo class runtime của receiver và quy tắc override |
| `invokeinterface` | Gọi instance method qua **interface type** | **Có** | Chọn method phù hợp mà runtime class của receiver triển khai hoặc kế thừa, gồm quy tắc default methods |

Đặc tả còn có **`invokedynamic`** cho call site được liên kết thông qua bootstrap method. Nó là instruction gọi thứ năm, nhưng có mô hình liên kết khác và không phải đối tượng chính của bài. Trong Java 17, nối chuỗi có thể sinh `invokedynamic`, nên đừng nghĩ mọi dòng output của `javap -c` chỉ chứa bốn instruction nêu trên.

**Tư duy đúng:** kiểu khai báo của biểu thức và cách method được gọi giúp compiler tạo instruction cùng constant-pool reference; sau đó JVM resolve và (với những lệnh cần dynamic dispatch) chọn implementation dựa trên đối tượng thực. “Tên method giống nhau” chưa đủ để kết luận opcode sẽ giống nhau.

## 2. Bối cảnh bắt buộc: frame, operand stack và method descriptor

Mỗi lời gọi method Java có thể tạo một **frame** trong JVM stack của thread. Frame chứa local variables, operand stack và thông tin hỗ trợ liên kết/trả về. Trước instruction `invoke*`, JVM sử dụng các operand đã được chuẩn bị trên **operand stack** của caller.

Ví dụ chữ ký JVM:

| Java declaration | Method descriptor trong class file |
| --- | --- |
| `static int twice(int n)` | `(I)I` |
| `String say()` | `()Ljava/lang/String;` |
| `void save(String value, long time)` | `(Ljava/lang/String;J)V` |
| `Child()` | `<init>:()V` |
| `void process(int[] values)` | `([I)V` |

Descriptor ghi **kiểu của các tham số và kiểu trả về**, không mang tên tham số Java như `n` hay `time`. JVM dùng symbolic method reference gồm **loại sở hữu method, tên method và descriptor** (cùng thông tin constant pool khác) để tìm method phù hợp. Method overload dựa trên các chữ ký khác nhau sẽ có descriptor khác nhau tại mức JVM.

### Sơ đồ một lời gọi instance

~~~text
Caller frame:
  local variables:  ...
  operand stack:    [..., objectref, arg1, arg2]
                                      |
                        invokevirtual / invokeinterface /
                        invokespecial
                                      v
Callee frame (với instance method):
  local slot 0: this = objectref
  các slot kế tiếp: arg1, arg2, ...
  operand stack riêng của callee
                                      |
                           thực thi bytecode của callee
                                      |
                          xreturn / return / athrow
                                      v
Caller tiếp tục sau instruction invoke;
nếu có return value, nó được đưa vào operand stack của caller
~~~

Với `invokestatic`, **không có `this`**: tham số đầu tiên (nếu có) bắt đầu ở local slot 0 của callee. Với instance method, slot 0 thường chứa `this`. Giá trị `long` và `double` sử dụng **hai slot** local-variable theo mô hình frame JVM; số lượng tham số ở source không luôn bằng số local slots.

Ví dụ gọi `Child.say()` trả String: receiver là một reference, descriptor `()Ljava/lang/String;`, kết quả trở lại caller bằng `areturn`. Nếu callee ném exception, call không trả về bình thường; các frame có thể được tháo trong quá trình tìm exception handler. Gọi method không phải cứ “copy toàn bộ object vào frame mới”; frame nhận **giá trị reference** cho `this`.

## 3. Lớp, interface và thông tin symbolic reference trong constant pool

Instruction `invoke*` chỉ ra **constant-pool index** cần dùng cho method reference. Tệp class không ghi trực tiếp địa chỉ byte máy của một method vào từng chỗ gọi. Thông tin dạng:

~~~text
#18 = Methodref             #... // InvokeModesDemo.twice:(I)I
#45 = Methodref             #... // InvokeModesDemo$Parent.label:()Ljava/lang/String;
#49 = InterfaceMethodref    #... // InvokeModesDemo$Speaker.say:()Ljava/lang/String;
~~~

Đây là ví dụ cách `javap -v` trình bày, các số constant-pool index **có thể khác** theo compiler và binary.

Các điểm cần phân biệt:

- `CONSTANT_Methodref` và `CONSTANT_InterfaceMethodref` là các loại entry khác nhau; chúng chứa quan hệ tới class/interface và `NameAndType` tương ứng.
- Theo ràng buộc class-file version Java 17, `invokevirtual` dùng `CONSTANT_Methodref`; `invokeinterface` dùng `CONSTANT_InterfaceMethodref`. `invokestatic` và `invokespecial` có thể dùng `Methodref` hoặc `InterfaceMethodref` khi hợp lệ theo phiên bản class file và loại method.
- **Resolution** tìm symbolic method reference phù hợp, kiểm tra điều kiện liên kết/truy cập; **selection/dispatch** có thể còn phụ thuộc class thực của receiver ở `invokevirtual`/`invokeinterface`. Không gộp resolution và dispatch thành một ý “JVM đã biết method tại compile time”.
- Trình biên dịch Java kiểm tra kiểu, overload và khả năng truy cập tại compile time, nhưng runtime class và thư viện thực có thể khác phiên bản được dùng khi biên dịch, nên JVM vẫn có các **linkage errors** khi chạy.
- JIT/HotSpot có thể dùng vtable, itable, inline cache hoặc devirtualization để tối ưu. **Cơ chế dữ liệu cụ thể đó không phải định nghĩa bắt buộc của opcode trong JVM Specification**.

Một lệnh gọi có thể được tối ưu rất mạnh trong native code, nhưng ngữ nghĩa quan sát được vẫn phải phù hợp với cơ chế chọn method mà Java/JVM định nghĩa (trừ các trường hợp lỗi, hành vi không xác định bởi chương trình, hoặc khác biệt được đặc tả).

## 4. `invokestatic`: gọi static method không cần receiver

Khi Java gọi:

~~~java
int result = Math.max(4, 7);
~~~

Compiler Java thông thường phát sinh `invokestatic` tham chiếu static method `Math.max:(II)I`. Trước khi gọi, các đối số `4`, `7` được đưa lên operand stack. **Không có object receiver** cho method static, và bên callee không có `this`.

Về mặt khái niệm:

~~~text
iconst_4
bipush 7
invokestatic java/lang/Math.max:(II)I
istore_1
~~~

Đây là trình bày giản lược, không phải toàn bộ output `javap` được bảo đảm; biến và offset thực do compiler quyết định.

### Static hiding không phải override động

~~~java
class Parent {
    static String kind() { return "PARENT"; }
}
class Child extends Parent {
    static String kind() { return "CHILD"; }
}
~~~

`Parent.kind()` và `Child.kind()` là **hai lời gọi static riêng**. Method static trong class con có thể **hide** static method cùng chữ ký của class cha, nhưng không override nó như instance method.

Nếu code Java cho phép gọi static method qua một biểu thức receiver như `ref.kind()`, cách giải quyết method vẫn theo **kiểu tại compile time**, không phải dispatch theo object thực. Cách viết `Type.kind()` rõ ràng hơn và tránh khiến người đọc tưởng đây là virtual call.

**Class/interface initialization:** việc thực thi `invokestatic` có thể kích hoạt khởi tạo class hoặc interface **khai báo method static đã được resolve**, theo quy tắc initialization của JVM. Điều này tách biệt với việc tạo một object: static method có thể được gọi ngay cả khi chương trình không có instance nào của class. Không phát biểu quá đơn giản rằng “chỉ cần nhìn thấy tên class trong source là static initializer chắc chắn chạy”; điều kiện initialization do đặc tả quy định.

`invokestatic` cũng gọi được **static method của interface**, như `Speaker.version()` ở ví dụ bên dưới; vì vậy mô tả “chỉ gọi static method trong class” là không đủ cho Java hiện đại.

## 5. `invokespecial`: constructor, `super` và xử lý instance đặc biệt

`invokespecial` có semantics riêng so với virtual dispatch thông thường. Những trường hợp tiêu biểu:

1. **Constructor `<init>`**: khi bytecode tạo object bằng `new`, quá trình initialization instance sử dụng `invokespecial` để gọi constructor. Constructor của class con cũng gọi constructor của class cha theo quy tắc Java/JVM.
2. **Gọi method của superclass bằng `super.method(...)`**: mong muốn của source là **bắt đầu truy cập implementation ở phía cha** theo ngữ nghĩa `super`, chứ không chọn override của class con như `this.method()` thông thường.
3. **Gọi default method được chỉ định bằng `InterfaceName.super.method(...)`** khi Java và quan hệ superinterface cho phép.
4. **Một số lời gọi instance có quyền truy cập/quy tắc đặc biệt**, gồm những trường hợp liên quan private method. Không nên khẳng định rằng **mọi** private call ở **mọi** phiên bản compiler đều phải mang opcode `invokespecial` chỉ dựa vào từ khóa `private`; cần kiểm tra class file thực và quy tắc JVM tương ứng.

### 5.1. Constructor: `new` khác `invokespecial`

Khi viết:

~~~java
Child child = new Child();
~~~

Bytecode thường có dạng:

~~~text
new           #... // class Child
dup
invokespecial #... // Method Child."<init>":()V
astore_1
~~~

- `new` cấp phát instance mới (sau khi các điều kiện initialization liên quan được thỏa mãn) và tạo **uninitialized object reference** ở mức verifier.
- `dup` giữ một bản giá trị tham chiếu trên operand stack để dùng sau khi gọi constructor.
- `invokespecial Child.<init>` thực thi instance initialization method; trình kiểm chứng JVM đặt những ràng buộc riêng lên cách sử dụng tham chiếu chưa khởi tạo.
- `astore_1` chỉ là ví dụ về việc lưu reference đã khởi tạo vào local slot; compiler có thể bố trí khác.

**Chỉ `invokespecial` được phép gọi instance initialization method `<init>`** theo class-file constraints. Constructor không phải là method được override; một constructor không thể virtual-dispatch tới “constructor override” ở subclass.

### 5.2. Super call bỏ qua override theo ngữ nghĩa nguồn

Ví dụ:

~~~java
class Parent {
    String label() { return "PARENT"; }
}
class Child extends Parent {
    @Override String label() { return "CHILD"; }
    String parentLabel() { return super.label(); }
}
~~~

Với một `Child`, gọi `child.label()` từ bên ngoài là virtual call thông thường và chọn `Child.label()`. Nhưng bên trong `Child.parentLabel()`, biểu thức `super.label()` có ngữ nghĩa gọi implementation phía superclass, nên compiler sinh `invokespecial` phù hợp.

Không diễn dịch `invokespecial` là “lúc nào cũng gọi chính xác class được viết trong constant pool mà không có quy tắc lựa chọn”. Đặc tả có **special lookup/selection**, gồm ảnh hưởng của `ACC_SUPER` và quan hệ thừa kế. Điều cần nhớ ở cấp học tập là **nó không thực hiện dispatch override thông thường giống invokevirtual**.

### 5.3. Interface default method qua `Interface.super`

Với một direct superinterface thích hợp, biểu thức `Speaker.super.banner()` gọi default implementation từ interface ấy, thường được biên dịch bằng `invokespecial` với **InterfaceMethodref**. Điều này **khác** lời gọi qua biến `Speaker`, vốn có thể dùng `invokeinterface`.

Nhờ đó, dù cùng là method của interface, **cách gọi** (`Speaker.super.banner()` hay `speaker.banner()`) có thể quyết định instruction khác nhau.

## 6. `invokevirtual`: dispatch dựa vào object runtime

Đây là lệnh gọi instance method rất phổ biến đối với **class-typed receiver**.

~~~java
Parent value = new Child();
System.out.println(value.label());
~~~

Compiler thấy biến `value` có kiểu khai báo `Parent` và thông thường sinh symbolic reference `Parent.label:()Ljava/lang/String;`, nhưng object thực là `Child`. Khi chạy, `invokevirtual` thực hiện lựa chọn implementation theo **runtime class của receiver**, do đó có thể chọn `Child.label()`.

~~~text
Biên dịch (theo kiểu khai báo)              Thực thi (theo object thực)
Parent value;                                receiver = instance Child
value.label()  ── invokevirtual Parent.label ──> Child.label()
~~~

**Chú ý:**

- `invokevirtual` vẫn có thể xuất hiện khi method là `final` hoặc không thực sự có subclass override nào. Opcode biểu diễn chế độ gọi, **không chứng minh** runtime luôn cần tìm kiếm phức tạp.
- `private` method không được override như virtual instance method thông thường. Java compiler và JVM có quy tắc riêng, cần nhìn bytecode cụ thể khi phân tích trường hợp private/nestmate.
- `static` method không nằm trong virtual dispatch. Static method bị hide chứ không được override.
- Nếu receiver value là `null`, lời gọi instance cần dereference receiver sẽ gây `NullPointerException`, không có implementation nào được chọn để chạy.
- `Object.equals`, `toString`, `hashCode` là ví dụ dễ thấy về virtual method; với class override hợp lệ, method thực thi có thể là của subclass. Riêng quy tắc chọn implementation vẫn dựa vào class runtime và luật method selection.

### Overload được chọn trước, override được chọn sau

~~~java
class Parent {
    String pick(Object value) { return "OBJECT"; }
}
class Child extends Parent {
    @Override String pick(Object value) { return "CHILD_OBJECT"; }
    String pick(String value) { return "CHILD_STRING"; }
}
~~~

Với `Parent p = new Child();`, biểu thức `p.pick("JVM")` được compiler chọn **overload `pick(Object)`** vì kiểu khai báo `Parent` không cung cấp `pick(String)`. Khi chạy, `invokevirtual` chọn override **`Child.pick(Object)`**, không “đổi overload” sang `Child.pick(String)` vì object thực là Child. Descriptor đã được xác định tại compile time; dispatch lựa chọn method **cùng tên/descriptor phù hợp** theo luật override.

Điểm này giải thích vì sao “động” của virtual dispatch không có nghĩa Java hoãn **mọi quyết định về method** cho tới runtime.

## 7. `invokeinterface`: gọi qua hợp đồng interface

Khi một biến có **kiểu interface**, bytecode thường sử dụng `invokeinterface`:

~~~java
Speaker speaker = new Child();
String message = speaker.say();
~~~

Compiler tham chiếu symbolic method của `Speaker`, còn JVM tìm method phù hợp mà **class runtime** của receiver cung cấp hoặc kế thừa. Ở đây `Child.say()` thực thi.

Sự khác nhau với `invokevirtual` không phải “interface không có code”: từ Java 8 interface có thể có **default method**, và từ Java 9 còn có private method trong interface. `invokeinterface` vẫn cần tuân theo quy tắc resolution/selection để tìm implementation, bao gồm các trường hợp method được class kế thừa, method của `Object` theo quy tắc cho phép, và default method.

### 7.1. Default method

Nếu interface khai báo:

~~~java
interface Speaker {
    String say();
    default String banner() {
        return "INTERFACE_DEFAULT";
    }
}
~~~

Thì lời gọi `speaker.banner()` thông qua reference `Speaker` có thể dùng `invokeinterface`, và runtime có thể chọn default implementation nếu class không cung cấp override ưu tiên hơn. Ngược lại, `Speaker.super.banner()` bên trong class triển khai được phép gọi qua `invokespecial`.

Cần biết: Java có những quy tắc giải quyết xung đột default methods khi nhiều superinterface đưa ra cùng chữ ký. Compiler thường phát hiện trường hợp không hợp lệ; class file được thay đổi hay binary mismatch có thể dẫn tới linkage/invocation errors theo đặc tả. Không nên tự viết mô hình “luôn chọn interface đứng trước trong danh sách implements”.

### 7.2. Layout instruction `invokeinterface`

Ở bytecode, `invokevirtual`, `invokespecial`, `invokestatic` có dạng opcode cộng **2 byte constant-pool index**. `invokeinterface` có **5 byte**:

~~~text
invokeinterface indexbyte1 indexbyte2 count 0
~~~

- Hai byte `indexbyte1/indexbyte2` tạo constant-pool index tới InterfaceMethodref.
- Byte `count` ghi số đơn vị local-variable slot cần cho **receiver và các đối số**; `long`/`double` chiếm hai slot.
- Byte cuối phải bằng 0 theo class-file format.

Ví dụ `javap` có thể in:

~~~text
invokeinterface #49,  1  // InterfaceMethod Speaker.say:()Ljava/lang/String;
~~~

Với method không nhận tham số nguồn, `count = 1` vẫn hợp lý vì có **receiver**. Không suy ra byte `count` là số phương thức trong interface, số interface của object hay số lượng tham số Java bỏ qua receiver.

## 8. Bài thực hành đầy đủ trên Java 17+

Tạo file **`InvokeModesDemo.java`** trong thư mục làm việc:

~~~java
public final class InvokeModesDemo {
    interface Speaker {
        String say();

        default String banner() {
            return "INTERFACE_DEFAULT";
        }

        static String version() {
            return "SPEAKER_STATIC";
        }
    }

    static class Parent {
        String label() {
            return "PARENT";
        }

        static String kind() {
            return "PARENT_STATIC";
        }
    }

    static class Child extends Parent implements Speaker {
        @Override
        String label() {
            return "CHILD";
        }

        @Override
        public String say() {
            return "CHILD_SAYS";
        }

        String parentLabel() {
            return super.label();
        }

        String interfaceBanner() {
            return Speaker.super.banner();
        }

        static String kind() {
            return "CHILD_STATIC";
        }
    }

    static int twice(int n) {
        return n * 2;
    }

    public static void main(String[] args) {
        Parent asParent = new Child();
        Speaker asSpeaker = (Speaker) asParent;
        Child exact = (Child) asParent;

        System.out.println("static=" + twice(3));
        System.out.println("classStatic=" + Parent.kind());
        System.out.println("hiddenStatic=" + Child.kind());
        System.out.println("virtual=" + asParent.label());
        System.out.println("interface=" + asSpeaker.say());
        System.out.println("super=" + exact.parentLabel());
        System.out.println("default=" + exact.interfaceBanner());
        System.out.println("interfaceStatic=" + Speaker.version());
    }
}
~~~

Biên dịch/chạy với **JDK 17 trở lên**:

~~~bash
javac --release 17 InvokeModesDemo.java
java InvokeModesDemo
~~~

**Stdout chính xác:**

~~~text
static=6
classStatic=PARENT_STATIC
hiddenStatic=CHILD_STATIC
virtual=CHILD
interface=CHILD_SAYS
super=PARENT
default=INTERFACE_DEFAULT
interfaceStatic=SPEAKER_STATIC
~~~

Mã đã được biên dịch thực tế bằng `javac --release 17` trên JDK 21 và chạy với kết quả đúng như trên. Các nested class được compiler xuất thành những file `InvokeModesDemo$Parent.class`, `InvokeModesDemo$Child.class`, `InvokeModesDemo$Speaker.class` (trong tên file có ký tự `$`), bên cạnh `InvokeModesDemo.class`.

### 8.1. Xem bytecode của class chính

~~~bash
javap -c -p InvokeModesDemo
~~~

Hãy tìm các lệnh trong `main`:

| Biểu thức nguồn | Instruction cần tìm trong ví dụ |
| --- | --- |
| `new Child()` | `new`, `dup`, `invokespecial Child."<init>":()V` |
| `twice(3)` | `invokestatic InvokeModesDemo.twice:(I)I` |
| `Parent.kind()` | `invokestatic Parent.kind:()Ljava/lang/String;` |
| `Child.kind()` | `invokestatic Child.kind:()Ljava/lang/String;` |
| `asParent.label()` | `invokevirtual Parent.label:()Ljava/lang/String;` |
| `asSpeaker.say()` | `invokeinterface Speaker.say:()Ljava/lang/String;` |
| `exact.parentLabel()` | `invokevirtual Child.parentLabel:()Ljava/lang/String;` |
| `exact.interfaceBanner()` | `invokevirtual Child.interfaceBanner:()Ljava/lang/String;` |
| `Speaker.version()` | `invokestatic Speaker.version:()Ljava/lang/String;` |

**Phân biệt cẩn thận:** `main` gọi `exact.parentLabel()` bằng `invokevirtual`, nhưng **bên trong** `parentLabel()` có lời gọi `super.label()` dùng `invokespecial`. Tương tự, `main` gọi `exact.interfaceBanner()` bằng `invokevirtual`, còn **bên trong method ấy** dùng `invokespecial` cho `Speaker.super.banner()`. Không kết luận opcode của toàn bộ một chuỗi lời gọi chỉ từ kết quả stdout.

### 8.2. Xem bytecode trong nested class bằng javap

Ở **Bash**, dùng dấu nháy đơn để shell không mở rộng ký tự `$` trong tên class:

~~~bash
javap -c -p 'InvokeModesDemo$Child'
javap -c -p 'InvokeModesDemo$Parent'
javap -c -p 'InvokeModesDemo$Speaker'
~~~

Trong **PowerShell**, các tên class có `$` cũng nên đặt trong nháy đơn, ví dụ:

~~~powershell
javap -c -p 'InvokeModesDemo$Child'
~~~

Trong output `Child`, tìm:

~~~text
InvokeModesDemo$Child();
  ...
  invokespecial ... // Method InvokeModesDemo$Parent."<init>":()V

java.lang.String parentLabel();
  ...
  invokespecial ... // Method InvokeModesDemo$Parent.label:()Ljava/lang/String;

java.lang.String interfaceBanner();
  ...
  invokespecial ... // InterfaceMethod InvokeModesDemo$Speaker.banner:()Ljava/lang/String;
~~~

Đây là **trích ý nghĩa cần tìm**, không phải toàn bộ output `javap` gồm constant-pool indices/bytecode offsets cố định. `javap -c` trên JDK 21 khi chạy bản đã biên dịch ở trên đã xác nhận cả ba trường hợp.

### 8.3. Điều gì còn xuất hiện ngoài bốn opcode?

Trong `main`, Java 17 compiler có thể dùng:

- `getstatic java/lang/System.out` để lấy `PrintStream`.
- `checkcast` khi ép `Parent` thành `Speaker` hoặc `Child`.
- `invokevirtual PrintStream.println` để in chuỗi.
- `invokedynamic makeConcatWithConstants` để nối `"static=" + twice(3)` và các chuỗi output.
- `aload` và `astore` để di chuyển reference giữa local variables với operand stack.

Các instruction này giúp tạo bối cảnh đầy đủ của lời gọi. Khi bạn thấy `invokedynamic` cho nối chuỗi, **đừng nhầm nó là opcode gọi `twice` hay `label`**; những method đó vẫn được gọi bằng `invokestatic` hoặc `invokevirtual` trong bản biên dịch đã kiểm tra.

## 9. Nhìn từ một lời gọi: compile time, link time và run time

Xét lời gọi `asParent.label()` trong ví dụ. Có ba mốc:

### Bước 1 — Chọn overload và tên/descriptor lúc biên dịch

Compiler nhìn kiểu khai báo `Parent`, kiểm tra method accessible và quyết định tham chiếu `label:()Ljava/lang/String;`. Nếu có nhiều overload, compiler chọn overload phù hợp với kiểu biểu thức và luật overload resolution của Java **trước khi chạy**.

### Bước 2 — JVM resolve symbolic method reference

Khi thực thi, JVM cần class/method descriptor thích hợp và bảo đảm các điều kiện liên kết/truy cập. Resolution có thể diễn ra lúc linking hoặc khi instruction cần dùng tùy những điều JVM cho phép. Đây là việc nhận diện một symbolic reference thực sự tương ứng với phần tử runtime hợp lệ.

### Bước 3 — Chọn implementation theo receiver thực

Receiver của `asParent` là instance `Child`; `invokevirtual` theo rules method selection sẽ chạy `Child.label()`, vì đây là override hợp lệ. **Resolution tới method được biểu thị từ Parent không có nghĩa bỏ qua override của Child.**

Đối với `invokestatic Parent.kind()`, không có bước dispatch theo receiver. Với `invokespecial super.label()`, áp dụng special selection. Với `invokeinterface Speaker.say()`, JVM xét implementation khả dụng từ runtime class `Child` cùng quy tắc interface method.

### Method lookup không đồng nghĩa call stack không thay đổi

Dù là `invokestatic` hay `invokevirtual`, khi vào body callee, về mặt ngữ nghĩa JVM có **lời gọi method và frame tương ứng**, tham số/receiver được chuyển vào locals, rồi method trả về hoặc ném exception. Khi JIT inline, các frame vật lý/nội bộ có thể được tối ưu; điều đó không thay đổi kết quả điều khiển luồng và những gì chương trình Java được phép quan sát.

## 10. Trường hợp method là `null`, `final`, `abstract` hoặc không tồn tại

### 10.1. Null receiver

~~~java
Parent value = null;
// value.label(); // nếu chạy: NullPointerException
~~~

Với instance call cần receiver, `invokevirtual` và `invokeinterface` yêu cầu reference không null. `invokespecial` gọi instance method cũng cần receiver hợp lệ theo quy tắc invocation, ngoại trừ các chi tiết verifier đặc thù của uninitialized reference khi xây dựng object.

`invokestatic` **không cần receiver** và không thể ném NullPointerException chỉ vì “receiver của lời gọi static là null”; source có thể đánh giá expression dùng cú pháp gọi static qua instance, nhưng method static vẫn không có `this` và không có dynamic receiver dispatch. Đừng dùng cú pháp ấy trong code mới.

### 10.2. Final method

Một instance method `final` không thể được override hợp lệ ở subclass. Compiler vẫn có thể sinh `invokevirtual` để gọi nó theo bytecode. JIT thường có cơ hội tối ưu khi biết target, nhưng không được dùng sự hiện diện của `invokevirtual` để kết luận có nhiều override khả thi.

### 10.3. Abstract method và interface implementation

Một class có thể khai báo abstract method; object hợp lệ của một concrete subclass phải cung cấp implementation theo các quy tắc Java. Nếu binary không tương thích khiến method được chọn tại runtime không có implementation phù hợp, JVM có thể ném **`AbstractMethodError`**. Đây là **linkage error** và không nên giải thích đơn giản là `NullPointerException`.

### 10.4. Class/interface API thay đổi giữa compile và runtime

Ví dụ, caller từng biên dịch dựa trên `Parent.label:()Ljava/lang/String;`, nhưng thư viện runtime xóa/đổi method hay descriptor. Caller có thể chạy tới lúc gặp `NoSuchMethodError` hoặc lỗi liên kết khác. Đổi một method từ instance sang static (hoặc ngược lại) phá tính tương thích của opcode và thường dẫn tới **`IncompatibleClassChangeError`** trong hoàn cảnh phù hợp.

| Lỗi hay gặp | Điều cần kiểm tra |
| --- | --- |
| `NullPointerException` khi gọi instance | Receiver thực có `null` không? |
| `NoSuchMethodError` | Binary runtime có đúng tên và descriptor caller đã biên dịch không? |
| `IllegalAccessError` | Quyền truy cập hoặc module/package/nest relationship có thay đổi khiến runtime không còn truy cập hợp lệ? |
| `IncompatibleClassChangeError` | Caller mong static/instance, class/interface hoặc cấu trúc kế thừa khác với binary đang chạy? |
| `AbstractMethodError` | Method được chọn có implementation hợp lệ không? |
| `StackOverflowError` | Đệ quy/call chain quá sâu so với khả năng stack của thread? |

Đây là hướng điều tra, **không phải ánh xạ một-một bảo đảm cho mọi lỗi**. Xem stack trace, classpath/module path, file class thực được load, các loader và version dependency trước khi kết luận.

## 11. Method override, default method và quyền truy cập

### Override phải hợp lệ theo Java/JVM

Với `@Override`, compiler giúp xác minh chữ ký của instance method mới tương thích với method muốn override. Không phải method cùng tên đều override: private method, static method, constructor và method overload có luật khác nhau.

Về mặt JVM, override phụ thuộc tên, descriptor cùng những điều kiện như accessibility, quan hệ lớp và các luật method overriding/selection. Khi có generic erasure hoặc covariant return, compiler có thể tạo **bridge method** để giữ ABI nhất quán; bạn có thể thấy thêm method có cờ `ACC_BRIDGE`/`ACC_SYNTHETIC` trong `javap -v`. Vì vậy không thể luôn ánh xạ “một khai báo method trong Java” thành “đúng một method_info JVM”.

### Default method của interface có thể được class override

Nếu `Child` tự khai báo:

~~~java
@Override
public String banner() {
    return "CHILD_BANNER";
}
~~~

thì lời gọi qua `Speaker speaker = new Child(); speaker.banner()` có thể chọn `Child.banner()` thay vì default implementation. Tuy nhiên, một lời gọi có chủ đích `Speaker.super.banner()` bên trong class được phép dùng nó vẫn gọi nhánh default phù hợp qua special invocation.

**Đoạn trên chỉ minh họa sự thay đổi so với chương trình thực hành**; không thêm nó vào file mẫu nếu muốn giữ stdout của phần 8. Nếu thêm override và biên dịch lại, kết quả gọi thường sẽ đổi theo method implementation mới.

### Access và module boundary

Một phương thức tồn tại ở class file nhưng caller vẫn không được phép gọi nếu quy tắc truy cập Java/JVM không cho. Method có thể `public`, `protected`, package-private hoặc `private`, và trong dự án module Java còn có điều kiện module accessibility. Đừng suy luận rằng cứ `javap -p` nhìn thấy method thì có thể gọi hợp lệ từ mọi class.

## 12. Những cách tối ưu của JIT không làm thay đổi ý nghĩa lệnh

HotSpot hoặc JVM khác có thể dùng **inline**, **devirtualization**, **inline caches**, profile-guided optimization hoặc kỹ thuật lookup khác để tăng tốc. Khi runtime thấy một call site `invokevirtual` trong một khoảng thời gian chỉ gặp một kiểu object, JIT có thể tối ưu đường gọi và có cơ chế fallback/deoptimization khi giả định không còn phù hợp.

Các thuật ngữ này giúp đọc tài liệu performance, nhưng không sửa ý nghĩa của `invokevirtual`: override hợp lệ của receiver runtime vẫn phải được tôn trọng. Tương tự, `invokeinterface` không mặc nhiên chậm hơn `invokevirtual` trong mọi workload và mọi JVM; mức tối ưu phụ thuộc môi trường, kiểu dữ liệu và số lượng implementation thực tế. Khi muốn so sánh hiệu năng, hãy đo bằng benchmark đáng tin (ví dụ JMH), tránh dựa vào cách đếm opcode đơn thuần.

### Exception và synchronized method

Nếu method được gọi là `synchronized`, JVM có quy tắc monitor entry/exit khi invoke/return hoặc hoàn tất bất thường. Nó không thay đổi “static hay virtual” của method, nhưng ảnh hưởng cơ chế đồng bộ của callee. Nếu callee ném exception, caller có thể bắt theo exception table; việc exception lan truyền không biến `invokevirtual` thành `invokespecial`.

## 13. Cách đọc `javap` để kiểm chứng phương thức được gọi

Trong project có một class bất kỳ, làm theo thứ tự:

1. **Biên dịch đúng Java target** (ví dụ `javac --release 17 ...`) và bảo đảm class file được đọc chính là binary đang chạy.
2. Dùng `javap -c -p TenClass` để tìm method chứa call site. Lưu ý `javap` có thể in cả `<init>`, synthetic/bridge method và code do compiler sinh.
3. Quan sát **opcode + constant-pool reference + descriptor**: `invokestatic`, `invokespecial`, `invokevirtual` hay `invokeinterface`.
4. Xác định **object receiver** (nếu có) qua `aload`, `getfield`, `new`, `checkcast` và các instruction trước call site.
5. Với `invokevirtual`/`invokeinterface`, xác định **runtime class** của object để hiểu implementation được chọn; chỉ đọc tên method ở comment của `javap` chưa đủ suy ra target cuối cùng.
6. Dùng `javap -v` khi cần xem Methodref/InterfaceMethodref, flags như `ACC_STATIC`, `ACC_BRIDGE`, signature, class-file version và metadata.
7. Nếu runtime báo linkage error, đối chiếu class file đã **load tại runtime** và dependency tree với class mà caller **được biên dịch dựa trên**.

Điểm kỹ thuật quan trọng: các số như `#45` sau `invokevirtual` là **constant-pool index**, không phải địa chỉ native method. Các số đầu dòng như `65:` là **bytecode PC** trong method, không phải dòng Java hoặc địa chỉ vật lý.

## 14. Các hiểu lầm thường gặp

1. **“`invokestatic` luôn cần một object để tìm method.”** Sai, static call không có receiver và không có `this`.
2. **“`invokevirtual` gọi đúng method của kiểu khai báo, không quan tâm object thật.”** Sai, nó sử dụng method selection theo runtime class khi override hợp lệ.
3. **“`invokeinterface` chỉ chạy code trong interface, không thể chạy class method.”** Sai, runtime tìm implementation thích hợp của object; interface default method là một trong những trường hợp.
4. **“Constructor được gọi qua `invokevirtual` như method bình thường.”** Sai, instance initializer `<init>` chỉ được gọi qua `invokespecial`.
5. **“`super.method()` vẫn dispatch tới override ở class con.”** Sai theo ngữ nghĩa `super`; nó dùng đường special invocation.
6. **“`invokeinterface` có `count=1` nghĩa là một tham số Java.”** Sai, count bao gồm receiver và tính slot của đối số.
7. **“Method static ở class con override static method cha.”** Sai, Java dùng **hiding** cho static.
8. **“Overload resolution được JVM tự đổi theo class runtime.”** Sai, overload đã được chọn theo kiểu biểu thức lúc compile; virtual dispatch chỉ tìm override phù hợp.
9. **“`final` method không thể xuất hiện sau opcode `invokevirtual`.”** Sai, opcode không đồng nghĩa chắc chắn có subclass override.
10. **“Mọi private instance call nhất thiết được biên dịch thành `invokespecial` ở mọi JDK.”** Sai, chi tiết encoding còn phụ thuộc phiên bản JVM/compiler và ngữ cảnh truy cập.
11. **“Vtable/itable của HotSpot là phần bắt buộc của JVMS.”** Sai, spec định nghĩa **ngữ nghĩa**, implementation tự chọn cấu trúc tối ưu.
12. **“Có method trùng tên và compile thành công là chắc chạy trên mọi phiên bản thư viện.”** Sai, runtime descriptor, access và loại method có thể đã thay đổi.

## 15. Câu hỏi tự kiểm tra

1. Khi gọi `Math.max(4,7)`, opcode thường thấy là gì và có receiver không? **`invokestatic`; không có receiver**.
2. Khi `Parent p = new Child(); p.label()` và `Child` override `label()`, method nào chạy? **`Child.label()`**, do `invokevirtual` chọn theo runtime class.
3. Lời gọi `super.label()` từ một method của `Child` thường dùng lệnh nào? **`invokespecial`**, theo super invocation semantics.
4. Constructor `<init>` được gọi bằng lệnh nào? **`invokespecial`**, không phải `invokevirtual`.
5. Khi biến khai báo kiểu `Speaker` gọi `say()`, compiler thường dùng opcode gì? **`invokeinterface`**.
6. Tại sao `Speaker.version()` không dùng `invokeinterface`? Vì đây là **static interface method**, được gọi bằng `invokestatic`.
7. `Parent.kind()` và `Child.kind()` cùng tên có dynamic override không? **Không**, đó là static method hiding.
8. Với `Parent p = new Child()`, nếu Parent chỉ khai báo `pick(Object)` còn Child thêm overload `pick(String)`, `p.pick("x")` dùng overload nào? **`pick(Object)` đã được compiler chọn**, sau đó dispatch tới override phù hợp của nó.
9. `invokeinterface` gọi method không có tham số nguồn thì byte `count` có thể bằng 1 không? **Có**, vì gồm receiver.
10. Tại sao `javap` có thể in `invokedynamic` dù đang học bốn lệnh trên? **Compiler Java hiện đại dùng invokedynamic cho một số call site, chẳng hạn nối chuỗi**.
11. Có thể kết luận method nào thực sự chạy chỉ từ comment `// Method Parent.label...` của `invokevirtual` không? **Chưa đủ**; cần runtime receiver type và rules selection.
12. Một call site ban đầu được JIT inline có thay đổi ý nghĩa override của Java không? **Không**, tối ưu phải bảo toàn ngữ nghĩa dispatch.

## 16. Tài liệu chuẩn

- JVM Specification Java SE 17, mục **Method Invocation and Return Instructions**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.8
- JVMS, **Instruction Set** (`invokestatic`, `invokespecial`, `invokevirtual`, `invokeinterface`): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- JVMS, **Method Resolution, Interface Method Resolution, Method Selection**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- JVMS, **Class-file Constraints** và constant pool: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- Java Language Specification, **Method Invocation Expressions**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12
- `javap` của JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html

**Kết luận kỹ thuật:** `invokestatic` gọi static method **không có receiver**; `invokespecial` dùng cho constructor và những lời gọi instance có **special selection**, nổi bật là `super`; `invokevirtual` chọn override theo **runtime class** của object; còn `invokeinterface` thực hiện lời gọi qua **interface contract**. Để hiểu chính xác một lời gọi JVM, cần đọc **opcode**, **method reference + descriptor**, **receiver/runtime type**, và phân biệt **resolution** với **method selection**.
