# Constructor `<init>`, class initializer `<clinit>` và trạng thái `uninitializedThis`

> **Phạm vi:** nền tảng class file và JVM verifier dành cho người đọc/disassemble hoặc biến đổi bytecode Java. Bài dùng Java 17/21 làm mốc cho ví dụ nguồn; các tên `<init>`, `<clinit>` và `uninitializedThis` là khái niệm ở tầng JVM, không phải tên phương thức Java có thể gọi trong mã nguồn.

## 1. Ba khái niệm không được đánh đồng

| Khái niệm | Nằm ở đâu? | Khi nào thực thi? | Vai trò |
|---|---|---|---|
| `<init>` | Phương thức đặc biệt **của từng lớp** trong class file, có descriptor dạng `(tham_so)V` | Khi JVM thực hiện một lời gọi constructor hợp lệ; thông thường một chuỗi constructor diễn ra cho mỗi đối tượng `new` | Khởi tạo phần instance theo quy tắc kế thừa và constructor chaining |
| `<clinit>` | Phương thức đặc biệt **tối đa một** cho mỗi class/interface, descriptor `()V` trên class file hiện đại | Khi JVM khởi tạo lớp/interface theo quy tắc *active use* | Chạy khởi tạo trường `static` và các `static { ... }` theo thứ tự |
| `uninitializedThis` | Kiểu xác minh (*verification type*) của tham chiếu `this` lúc bắt đầu bytecode của `<init>` | Tồn tại trong phân tích kiểu của verifier trước khi lời gọi `this(...)` hoặc `super(...)` phù hợp hoàn tất | Ngăn dùng/thoát tham chiếu đối tượng trước khi chuỗi constructor được thiết lập hợp lệ |

Lưu ý hai chữ “khởi tạo” ở đây chỉ **hai việc khác nhau**. Khởi tạo *lớp* (`<clinit>`) không đồng nghĩa khởi tạo *đối tượng* (`<init>`). `uninitializedThis` không phải `null`, không phải một đối tượng khác, và không phải cờ boolean do chương trình Java tự kiểm tra được; nó là kiểu trạng thái được JVM verifier theo dõi.

## 2. `<init>` trong cấu trúc class file

Trong Java source, constructor mang tên lớp, không có kiểu trả về:

```java
class Account {
    private final int id;

    Account(int id) {
        this.id = id;
    }
}
```

Compiler tạo phương thức bytecode có tên **`<init>`** và descriptor **`(I)V`**: tham số `int`, trả về `void` ở mức JVM. Hai constructor nạp chồng `Account()` và `Account(int)` tương ứng với hai `<init>` có descriptor khác nhau (`()V` và `(I)V`); chúng không override lẫn nhau. `<init>` là *instance initialization method*, không `static`, không được gọi bằng `invokevirtual`/`invokeinterface`. Các lời gọi constructor hợp lệ dùng `invokespecial` trên tham chiếu đang ở trạng thái chưa khởi tạo.

Với constructor instance, local variable slot 0 thường chứa `this`; các slot tiếp theo chứa tham số (`long`/`double` chiếm hai slot). Riêng phương thức `<clinit>` không có `this`. Các đoạn khởi tạo trường instance và `{ ... }` trong Java source được compiler đưa vào đường thực thi của constructor thích hợp, chứ không tự trở thành `<clinit>`.

### Từ `new` đến `invokespecial`

Với biểu thức `new Account(7)`, có thể nhìn thấy mô hình opcode sau (minh họa; offset/chỉ số constant pool tùy bản biên dịch):

```text
new           Account             ; cấp phát, tạo tham chiếu chưa khởi tạo
dup                               ; giữ một bản tham chiếu làm kết quả biểu thức
bipush        7                   ; đưa tham số int lên operand stack
invokespecial Account.<init>:(I)V  ; tiêu thụ tham chiếu + đối số, chạy constructor
                                   ; bản tham chiếu còn trên stack nay được verifier
                                   ; coi là kiểu Account đã khởi tạo
```

`new` cấp phát đối tượng và các trường instance ban đầu mang **giá trị mặc định** (`0`, `false`, `null`, ...). Nó **chưa** tự thực thi thân constructor. Lời gọi `invokespecial ...<init>` mới làm việc đó. Trên đường đi thông thường, việc tạo instance còn có thể kích hoạt khởi tạo class trước khi cấp phát.

Verifier biểu diễn tham chiếu vừa tạo bởi opcode `new` ở offset `p` là `uninitialized(p)`. Còn local 0 bên trong chính một `<init>` bắt đầu với kiểu đặc biệt `uninitializedThis`. Hai kiểu này cùng nói về tham chiếu chưa được phép dùng như một đối tượng đã khởi tạo, nhưng **không cùng nguồn gốc**:

- `uninitialized(p)` gắn với một lệnh `new` cụ thể và địa chỉ bytecode của nó.
- `uninitializedThis` gắn với receiver của constructor đang được xác minh; không cần lệnh `new` trong chính constructor đó.

Khi `invokespecial` gọi constructor đúng đối tượng và **trở về bình thường**, verifier chuyển **tất cả bản sao được theo dõi** của tham chiếu chưa khởi tạo tương ứng sang kiểu đối tượng đã khởi tạo. Nếu lời gọi constructor ném exception, không được coi rằng đối tượng đã khởi tạo thành công.

## 3. Quy tắc của `uninitializedThis` và chuỗi `this(...)`/`super(...)`

Xét đoạn Java 17/21:

```java
class Parent {
    Parent(int code) {
        System.out.println("Parent: " + code);
    }
}

class Child extends Parent {
    private final String label;

    Child() {
        this("default");
    }

    Child(String label) {
        super(10);
        this.label = label;
        System.out.println("Child: " + label);
    }
}
```

Chạy `new Child()` sẽ gọi `Child.<init>:()V`, chuyển tiếp sang `Child.<init>:(Ljava/lang/String;)V` nhờ `this("default")`; constructor đích gọi `Parent.<init>:(I)V` nhờ `super(10)`. Sau khi lời gọi kế thừa thành công, code mới thiết lập `label` và chạy phần thân còn lại. Kết quả in:

```text
Parent: 10
Child: default
```

Trong bytecode của `Child.<init>`, local 0 ban đầu được verifier xem là `uninitializedThis`. Tại lệnh `invokespecial` có receiver này, constructor đích phải thuộc **chính lớp hiện tại** (`this(...)`) hoặc **lớp cha trực tiếp** (`super(...)`). Khi lời gọi đó trở về bình thường, trạng thái verifier được cập nhật thành kiểu lớp hiện tại. Trên mọi đường thoát **bình thường** của constructor (trừ trường hợp đặc biệt của `Object`), chuỗi khởi tạo hợp lệ phải được thiết lập trước khi `return`.

Trước mốc này, không được tùy tiện xem `this` như tham chiếu object bình thường. Chẳng hạn bytecode dùng `aload_0` rồi `invokevirtual` một phương thức instance hay truyền `this` vào phương thức `static` nhận `Object` khi nó vẫn là `uninitializedThis` sẽ bị từ chối xác minh. **Ngoại lệ ở tầng bytecode:** JVM cho phép một số thao tác hạn chế như `putfield` lên trường instance *được khai báo ngay trong lớp hiện tại* trước khi gọi constructor cha; điều này không có nghĩa có thể đọc trường hoặc gọi phương thức trên `this` tùy ý. Java 17/21 source còn chặt hơn: lời gọi `this(...)`/`super(...)` là câu lệnh đầu tiên của constructor.

Cẩn thận với câu “`this` đã khởi tạo sau `super()`”. Đó là **trạng thái hợp lệ đối với verifier**, không đảm bảo mọi field của subclass đã được gán giá trị mong muốn. Các instance initializer và phần còn lại của constructor subclass có thể vẫn đang chạy. Không truyền `this` ra ngoài chỉ vì verifier cho phép dùng nó.

### `StackMapTable` và lỗi xác minh

Trong class file có stack map frames, `verification_type_info` phân biệt `ITEM_UninitializedThis` với `ITEM_Uninitialized` (loại thứ hai mang offset của lệnh `new`). Verifier hợp nhất trạng thái locals và operand stack qua các nhánh/exception handlers. Nếu công cụ instrumentation sửa `<init>`, thay thế máy móc `uninitializedThis` bằng `Object`, làm sai đường đi của `invokespecial` hoặc tạo đường `return` trước khi khởi tạo phù hợp, JVM có thể ném `VerifyError` khi kiểm tra class.

Đặc biệt, exception handler bao phủ một lời gọi `<init>` cần phản ánh đúng đường bất thường: lời gọi constructor thất bại **không** tạo ra tham chiếu đã khởi tạo. Không được gộp tùy tiện frame trước và sau `invokespecial`.

## 4. `<clinit>`: khởi tạo class, không phải constructor instance

Compiler có thể tổng hợp code gán `static` và khối `static { ... }` của một lớp vào phương thức đặc biệt `<clinit>:()V`, theo **thứ tự xuất hiện trong source**. Trên class file Java hiện đại, phương thức này là `static`; class/interface có **tối đa một** `<clinit>`. Không phải lớp nào cũng cần phương thức này: nếu không có công việc khởi tạo runtime thích hợp, compiler có thể không sinh nó; biến hằng `static final int` hoặc `String` là constant variable thường được biểu diễn qua `ConstantValue`.

Về *active use*, JVM khởi tạo class trước những hoạt động như tạo instance, gọi phương thức `static` **khai báo tại class đó**, ghi field `static`, hoặc đọc field `static` không phải constant variable. Một số cách reflection cũng kích hoạt khởi tạo. Ngược lại, chỉ viết `SomeType.class`, khai báo biến có kiểu đó, hoặc đọc một constant variable được inline **không tự nó** buộc chạy `<clinit>`.

Với một class, JVM khởi tạo superclass (và các superinterface liên quan có default methods theo quy tắc đặc tả) trước phần khởi tạo của class con. Việc khởi tạo được đồng bộ giữa các thread: nếu thread khác đang khởi tạo cùng `Class` object, thread hiện tại chờ kết quả. Khi đã thành công thì không chạy lại cho những lần `new` tiếp theo. Danh tính class trong JVM phụ thuộc cả **tên binary** và **defining class loader**: cùng tên ở hai loader khác nhau có thể là hai class riêng, mỗi class được khởi tạo riêng.

Khi `<clinit>` thất bại, class có thể bị đánh dấu *erroneous*. Với exception không phải `Error`, lần lỗi đầu thường được bọc bởi `ExceptionInInitializerError`; lần active use sau thường nhận `NoClassDefFoundError`. Không coi đây là lỗi constructor của một instance và cũng không kỳ vọng một lần `new` tiếp theo sẽ chạy lại `<clinit>` để sửa lỗi.

## 5. Ví dụ chạy được: thứ tự `<clinit>` và `<init>`

Lưu toàn bộ mã dưới đây thành **`InitLifecycleDemo.java`**:

```java
public class InitLifecycleDemo {

    static int mark(String message) {
        System.out.println(message);
        return 10;
    }

    static class Parent {
        static {
            System.out.println("Parent: static block");
        }

        Parent() {
            System.out.println("Parent: constructor");
        }
    }

    static class Child extends Parent {
        static int count = mark("Child: static field");
        static {
            System.out.println("Child: static block");
        }

        int value = mark("Child: instance field");
        {
            System.out.println("Child: instance block");
        }

        Child() {
            super();
            System.out.println("Child: constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("Before first new");
        new Child();
        System.out.println("Before second new");
        new Child();
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên (cú pháp cũng chạy trên JDK 21):

```bash
javac --release 17 InitLifecycleDemo.java
java InitLifecycleDemo
```

**Stdout đúng**:

```text
Before first new
Parent: static block
Child: static field
Child: static block
Parent: constructor
Child: instance field
Child: instance block
Child: constructor
Before second new
Parent: constructor
Child: instance field
Child: instance block
Child: constructor
```

Giải thích theo từng lớp:

1. Khi chạy `main`, `InitLifecycleDemo` đã được khởi tạo. Lệnh `new Child()` đầu tiên kích hoạt khởi tạo `Child` nếu chưa làm, kéo theo `Parent` khởi tạo trước. Do đó `Parent: static block` đứng trước hai dòng static của `Child`.
2. Sau khởi tạo class, constructor `Child` gọi `Parent()`; sau khi constructor cha trả về, instance field initializer và instance block của `Child` chạy theo thứ tự source; cuối cùng là phần thân constructor `Child`.
3. Ở lần `new Child()` thứ hai, **không lặp lại static block/field initializer**, nhưng toàn bộ luồng constructor và khởi tạo instance chạy lại cho đối tượng mới.

Trên Windows PowerShell, macOS hoặc Linux shell, dùng lệnh có dấu nháy đơn sau để tránh shell diễn giải ký tự `$` trong tên nested class:

```bash
javap -c -p 'InitLifecycleDemo$Child'
javap -v -p 'InitLifecycleDemo$Child'
```

Trong output `javap -c -p`, quan sát constructor của `Child`: thường bắt đầu bằng `aload_0` rồi `invokespecial ...Parent."<init>":()V`; tiếp theo là lời gọi `mark`, `putfield value` và những lệnh in dòng instance block/constructor. Phần `static {};` riêng chứa lệnh gọi `mark`, `putstatic count` và thông điệp static block. Trong output `javap -v`, xem descriptor `()V`, cờ `ACC_STATIC` của initializer và mục `<init>`/`<clinit>` ở constant pool. Offset, số hiệu constant pool và cú pháp hiển thị chi tiết có thể thay đổi theo bản `javac`/`javap`.

## 6. Góc nhìn instrumentation: chèn probe ở đâu an toàn?

Công cụ biến đổi class file (agent, ASM, Byte Buddy hoặc transformer khác) phải tôn trọng **ngữ nghĩa constructor** lẫn **trạng thái verifier**.

### Probe trước `super()`: khác biệt giữa gọi static và truyền `this`

Đoạn **pseudo-bytecode sai** bên dưới minh họa ý tưởng dễ gây `VerifyError`; đây không phải chương trình Java để biên dịch:

```text
; Trong <init>, local 0 vẫn là uninitializedThis
aload_0
invokestatic Probe.capture:(Ljava/lang/Object;)V   ; SAI: chưa được dùng như Object
aload_0
invokespecial Parent.<init>:()V
```

Chèn `invokestatic Probe.enter:()V` không nhận `this` có thể hợp lệ về mặt verifier *nếu* đường điều khiển và stack map được xử lý đúng. Tuy nhiên, probe có side effect hoặc ném exception sẽ đổi hành vi constructor. Một cách thực dụng để ghi nhận object là chèn sau lời gọi constructor cha/constructor cùng lớp phù hợp, rồi chỉ dùng `this` khi chắc chắn đã chuyển sang kiểu initialized trên **mọi đường điều khiển**. Ngay cả lúc đó, tránh gọi code đưa `this` sang thread/cache/listener trước khi toàn bộ trạng thái subclass ổn định.

### Kiểm tra trước khi phát hành class đã biến đổi

- Xác định chính xác phương thức bằng **tên `<init>` cộng descriptor**, vì một lớp có thể có nhiều overload. Không nhầm với phương thức tên `<clinit>`; JVM tự gọi class initializer, còn `<init>` được gọi qua `invokespecial`.
- Phân biệt vùng bytecode **trước** và **sau** lời gọi `this(...)`/`super(...)`, cùng mọi branch và exception edge. Không giả định tất cả đường đi qua cùng offset nếu transformer đã thay đổi code.
- Giữ đúng operand stack, `max_stack`/`max_locals`, jump offsets, exception table và `StackMapTable`. Khi dùng ASM `COMPUTE_FRAMES`, vẫn phải cung cấp hierarchy/classpath hợp lệ; tự động tính frame không sửa được một control flow sai.
- Với `new`/`dup`/`invokespecial`, không tách hoặc biến tham chiếu `uninitialized(p)` thành reference initialized trước khi constructor đích hoàn tất. Không dùng một uninitialized reference vào `invokevirtual`, `invokeinterface` hay lệnh yêu cầu object đã khởi tạo.
- Với `<clinit>`, chú ý probe có thể tải thêm class hoặc gây vòng khởi tạo; static initialization chạy một lần theo từng class identity và thất bại có thể để lại class ở trạng thái erroneous. Transformer không được giả định có thể “chạy lại” `<clinit>` sau khi redefine/retransform class.
- Kiểm tra cả đường **thành công** lẫn **ném exception**. Khi kiểm thử mã đã biến đổi, hãy chạy nó dưới JVM thực với verification bật (mặc định) và so sánh thứ tự side effect trước/sau instrumentation.

### Ba lỗi tư duy thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`new` gọi xong constructor ngay” | `new` tạo/cấp phát reference chưa khởi tạo; `invokespecial <init>` thực thi constructor. |
| “`<clinit>` chạy cho mọi `new`” | Nó là pha khởi tạo **class**, thường tối đa một lần cho mỗi `Class` object; `<init>` mới nằm trên đường khởi tạo từng instance. |
| “Sau `super()`, mọi field subclass đã hoàn tất” | Verifier có thể coi `this` là initialized, nhưng instance initializers/thân constructor subclass vẫn có thể chưa chạy xong. |

## 7. Tự kiểm tra hiểu biết

1. Vì sao verifier cần hai kiểu `uninitializedThis` và `uninitialized(offset)`? Vì một kiểu mô tả receiver của `<init>` hiện tại, kiểu kia mô tả object sinh từ một lệnh `new` cụ thể; quy tắc gọi constructor và chuyển đổi kiểu đều cần phân biệt.
2. Khi có `Child() { this("x"); }`, constructor `Child()` có tự gọi `super()` nữa không? Không. Constructor được ủy quyền sẽ tiếp tục chuỗi và cuối cùng gọi constructor cha thích hợp; không gọi constructor cha hai lần cho một đường xây dựng đối tượng.
3. Vì sao đọc `static final int PORT = 8080` thường không làm chạy static block? Vì đây là constant variable với giá trị compile time, client có thể inline giá trị và việc đọc đó không kích hoạt class initialization.
4. Tại sao không đơn giản chèn `aload_0; invokestatic log(Object)` ở bytecode đầu constructor? Vì local 0 có verification type `uninitializedThis`; không được truyền nó như `Object` trước lúc hợp lệ.
5. Nếu khởi tạo `Child` thất bại trong `<clinit>`, lần `new Child()` sau có “thử lại” không? Không; JVM đánh dấu class lỗi và active use sau có thể ném `NoClassDefFoundError`.

## Tài liệu chuẩn để đối chiếu

- [JVMS 21, §2.9 — Instance/Class Initialization Methods](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.9)
- [JVMS 21, §4.10.1.9 — Type Checking / invokespecial và uninitializedThis](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.10.1.9)
- [JLS 21, §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4)
- [JLS 21, §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.5)
