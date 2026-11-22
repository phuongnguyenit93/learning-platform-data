# Constant pool và tham chiếu đến lớp, trường, phương thức được gọi

Trong Java, mã nguồn nhắc tới một lớp, đọc một trường hoặc gọi một phương thức bằng tên. Sau khi biên dịch, bytecode không lưu địa chỉ bộ nhớ cố định của các thành phần đó. Thay vào đó, tệp `.class` lưu các **tham chiếu ký hiệu (symbolic references)** trong **constant pool**, còn lệnh bytecode trỏ tới chúng bằng chỉ số. JVM dùng thông tin này để xác minh, liên kết và tìm thành phần tương ứng lúc chạy.

Sau bài này, bạn có thể đọc các mục `Class`, `NameAndType`, `Fieldref`, `Methodref`, `InterfaceMethodref` trong kết quả `javap -v`; phân biệt tên với descriptor; nối một lệnh bytecode với tham chiếu của nó; và giải thích vì sao thay đổi API nhị phân có thể gây `NoSuchMethodError` hoặc `NoSuchFieldError`.

## 1. Constant pool nằm ở đâu và dùng để làm gì?

Cấu trúc rút gọn của một class file là:

```text
ClassFile
├── magic = 0xCAFEBABE
├── minor_version, major_version
├── constant_pool_count
├── constant_pool[1 .. constant_pool_count - 1]
├── access_flags, this_class, super_class
├── interfaces[]
├── fields[]
├── methods[]                  (bao gồm thuộc tính Code chứa bytecode)
└── attributes[]
```

- Mỗi class/interface có **constant pool riêng** trong tệp `.class`; đây không phải một bảng tên chung của toàn ứng dụng. Một mục có dạng `cp_info { u1 tag; u1 info[]; }`: `tag` xác định loại và phần còn lại chứa dữ liệu/chỉ số tham chiếu.
- `constant_pool_count` là một giá trị `u2`; chỉ số hợp lệ bắt đầu từ **1**, không phải 0. Mục `Long`/`Double` chiếm **hai vị trí chỉ số**, trong đó vị trí thứ hai không phải mục độc lập có thể tham chiếu. Vì vậy số mục hữu dụng không nhất thiết bằng `constant_pool_count - 1`.
- Một số mục là hằng số có thể nạp lên operand stack (số, chuỗi, class literal...); một số chỉ chứa tên, kiểu và liên kết đến lớp/trường/phương thức. Tên “constant pool” **không** có nghĩa mọi mục đều là giá trị `static final`.
- Các cấu trúc `this_class`, `super_class`, khai báo trường/phương thức và nhiều attribute cũng trỏ vào constant pool; không phải mọi mục đều xuất hiện trong một lệnh `Code`.
- JVM tạo **run-time constant pool** tương ứng khi tạo lớp ở runtime. JVM có thể phân giải tham chiếu khi cần hoặc sớm hơn nếu vẫn giữ đúng hành vi được đặc tả; không nên hiểu rằng cứ mỗi lần gọi phương thức là JVM lại tìm tuyến tính trong bảng văn bản.

Tệp Java 17 biên dịch với `javac --release 17` có `major version: 61`. Đây là phiên bản định dạng class file, không phải số lượng mục constant pool.

## 2. Các loại mục cần nhận diện

| Dạng trong `javap -v` | Tag | Vai trò |
| --- | ---: | --- |
| `Utf8` | 1 | Lưu chuỗi dữ liệu của tên, descriptor, tên attribute... (class file sử dụng *modified UTF-8*). |
| `Integer`, `Float`, `Long`, `Double` | 3, 4, 5, 6 | Giá trị số hằng trong class file. |
| `Class` | 7 | Trỏ tới `Utf8` biểu diễn tên nội bộ của lớp/interface hoặc descriptor của kiểu mảng. |
| `String` | 8 | Trỏ tới `Utf8` chứa nội dung string literal; không phải cùng một loại với `Utf8`. |
| `Fieldref` | 9 | Tham chiếu đến trường qua lớp/interface sở hữu và `NameAndType`. |
| `Methodref` | 10 | Tham chiếu đến phương thức thuộc lớp, bao gồm lời gọi constructor `<init>`. |
| `InterfaceMethodref` | 11 | Tham chiếu đến phương thức khai báo trong interface. |
| `NameAndType` | 12 | Cặp **tên thành phần + descriptor**; bản thân nó chưa chỉ ra lớp sở hữu. |
| `MethodHandle`, `MethodType` | 15, 16 | Biểu diễn handle của trường/phương thức và kiểu phương thức; quan trọng cho lambda và liên kết động. |
| `Dynamic`, `InvokeDynamic` | 17, 18 | Hằng số động / vị trí gọi được liên kết qua bootstrap method, không phải `Methodref` thông thường. |
| `Module`, `Package` | 19, 20 | Thông tin module/package dùng trong các cấu trúc class file thích hợp, chẳng hạn `module-info.class`. |

Trọng tâm khi đọc lời gọi thông thường là bộ ba **`Class` → `NameAndType` → `Fieldref/Methodref/InterfaceMethodref`**, với các `Utf8` giữ văn bản thực tế.

## 3. Một tham chiếu được ghép từ những gì?

Ba cấu trúc tham chiếu chính có cùng hình dạng:

```text
CONSTANT_Fieldref_info / Methodref_info / InterfaceMethodref_info
    u1 tag
    u2 class_index             -> CONSTANT_Class_info
    u2 name_and_type_index     -> CONSTANT_NameAndType_info

CONSTANT_Class_info
    u1 tag = 7
    u2 name_index              -> CONSTANT_Utf8_info

CONSTANT_NameAndType_info
    u1 tag = 12
    u2 name_index              -> CONSTANT_Utf8_info
    u2 descriptor_index        -> CONSTANT_Utf8_info
```

Giả sử có lời gọi Java `account.deposit(5)`, trong đó lớp `Account` thuộc package `demo.constantpool` và phương thức có chữ ký `void deposit(int amount)`. Constant pool của **lớp chứa lời gọi** có thể biểu diễn theo sơ đồ minh họa sau (chỉ số `#...` là ví dụ, không phải output cố định của `javac`):

```text
#12 = Class       #40          // demo/constantpool/Account
#40 = Utf8        demo/constantpool/Account
#21 = NameAndType #41:#42      // deposit:(I)V
#41 = Utf8        deposit
#42 = Utf8        (I)V
#31 = Methodref   #12.#21      // demo/constantpool/Account.deposit:(I)V

Bytecode: invokevirtual #31     // Method demo/constantpool/Account.deposit:(I)V
```

Ở đây:

1. `Methodref` cho biết **lớp được nhắc tới** và **tên + descriptor** của phương thức; nó chưa phải địa chỉ hàm trong bộ nhớ.
2. `Class` giữ tên nội bộ `demo/constantpool/Account`. Trong tên nội bộ của class file, dấu `/` phân tách package, khác dấu `.` trong tên Java dùng bởi `javap`/`java`.
3. `NameAndType` phân biệt các thành phần trùng tên nhưng khác kiểu/chữ ký. Chẳng hạn `deposit(I)V` và `deposit(J)V` là hai phương thức có descriptor khác nhau.
4. Một `NameAndType` có thể được nhiều tham chiếu dùng lại; giá trị số của chỉ số tùy thứ tự biên dịch và trình biên dịch. Đọc chuỗi `#31 → #12/#21 → #40/#41/#42` mới cho ra ý nghĩa đầy đủ.

Với trường, mô hình tương tự, nhưng `NameAndType` mang **field descriptor** thay vì **method descriptor**. Ví dụ `Fieldref Account.balance:I` cho biết trường tên `balance` có kiểu `int`. `Fieldref` có thể chỉ tới trường của lớp **hoặc** interface; còn `Methodref` trỏ tới lớp và `InterfaceMethodref` trỏ tới interface.

**Phân biệt nơi khai báo và nơi tham chiếu:** `Account.class` có khai báo `deposit` ở bảng `methods[]`; `PoolDemo.class` có `Methodref` khi nó gọi `Account.deposit`. Không cần có một `Methodref` tương ứng cho mọi phương thức khai báo; bộ tham chiếu tùy bytecode thực tế của từng class file.

## 4. Descriptor: phần thường bị đọc nhầm

Descriptor là chuỗi mã hóa **kiểu JVM**, khác generic signature và tên kiểu theo cú pháp Java.

| Kiểu Java | Field descriptor |
| --- | --- |
| `boolean`, `byte`, `char`, `short` | `Z`, `B`, `C`, `S` |
| `int`, `long`, `float`, `double` | `I`, `J`, `F`, `D` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[][]` | `[[Ljava/lang/String;` |

**Method descriptor** có dạng `(kiểu_tham_số...)kiểu_trả_về`. `V` chỉ dùng cho kiểu trả về `void`:

| Khai báo Java | Descriptor |
| --- | --- |
| `void deposit(int amount)` | `(I)V` |
| `String name()` | `()Ljava/lang/String;` |
| `long sum(int x, long y)` | `(IJ)J` |
| `static void main(String[] args)` | `([Ljava/lang/String;)V` |

Nhớ ba điều: (1) tham số ghi liên tiếp, không có dấu phẩy; (2) `L...;` bao quanh tên nội bộ của kiểu đối tượng; (3) `[` thêm một chiều mảng. Ví dụ `(Ljava/lang/String;[I)Z` nhận `String` và `int[]`, trả về `boolean`.

**Overload** cần tên + descriptor để phân biệt lời gọi. Ở mức JVM, descriptor của phương thức còn chứa cả kiểu trả về, nhưng Java không cho overload hai phương thức chỉ khác kiểu trả về. **Generic** thường bị *type erasure*: `List<String>` và `List<Integer>` thường cùng descriptor `Ljava/util/List;`; thông tin kiểu tổng quát có thể được lưu thêm ở attribute `Signature`, không làm thay đổi field/method descriptor dùng trong liên kết thông thường.

Tên đặc biệt `<init>` là phương thức khởi tạo đối tượng, có kiểu trả về `V` trong descriptor; `<clinit>` là phương thức khởi tạo lớp được JVM gọi ngầm, không phải mục tiêu của lời gọi trực tiếp thông thường.

## 5. Thí nghiệm chạy được với Java 17+

Tạo đúng một tệp `PoolDemo.java` dưới thư mục làm việc tùy ý, với nội dung sau. Các kiểu không `public` được khai báo cùng tệp để việc thực hành gọn hơn:

```java
package demo.constantpool;

interface Named {
    String name();
}

final class Account implements Named {
    static int opened;
    final String owner;
    int balance;

    Account(String owner, int opening) {
        this.owner = owner;
        this.balance = opening;
        opened++;
    }

    @Override
    public String name() {
        return owner;
    }

    void deposit(int amount) {
        balance += amount;
    }

    static String label() {
        return "Account";
    }
}

public class PoolDemo {
    public static void main(String[] args) {
        Account account = new Account("Lan", 10);
        account.deposit(5);

        Named named = account;
        String line = Account.label() + " " + named.name()
                + ": " + account.balance + ", opened=" + Account.opened;
        System.out.println(line);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp; thư mục `out` sẽ được tạo nếu cần:

```bash
javac --release 17 -d out PoolDemo.java
java -cp out demo.constantpool.PoolDemo
```

Kết quả chính xác:

```text
Account Lan: 15, opened=1
```

Giải thích: constructor gán `balance = 10` và tăng `opened` từ 0 lên 1; `deposit(5)` tăng `balance` lên 15; lời gọi qua biến `Named` trả `"Lan"`. Các biến static được khởi tạo mặc định về 0 trước khi chạy constructor đầu tiên.

Xem các mục constant pool và bytecode bằng bộ công cụ đi kèm JDK:

```bash
javap -v -p -classpath out demo.constantpool.PoolDemo
javap -c -p -classpath out demo.constantpool.PoolDemo
javap -v -p -classpath out demo.constantpool.Account
javap -v -p -classpath out demo.constantpool.Named
```

Trong `PoolDemo.class`, hãy tìm các thành phần sau (chỉ số `#n` thực tế tùy phiên bản trình biên dịch):

| Dấu vết trong `javap` | Vì sao xuất hiện? |
| --- | --- |
| `Class demo/constantpool/Account` và `Methodref Account."<init>":(Ljava/lang/String;I)V` | `new Account("Lan", 10)` tạo đối tượng, sau đó gọi constructor bằng `invokespecial`. |
| `Methodref Account.deposit:(I)V` | `account.deposit(5)` dùng lời gọi phương thức instance. |
| `Methodref Account.label:()Ljava/lang/String;` | `Account.label()` là lời gọi static. |
| `InterfaceMethodref Named.name:()Ljava/lang/String;` | `named.name()` gọi qua kiểu interface. |
| `Fieldref Account.balance:I` và `Fieldref Account.opened:I` | Đọc trường instance và static cho chuỗi kết quả. |
| `Fieldref java/lang/System.out:Ljava/io/PrintStream;` và `Methodref java/io/PrintStream.println:(Ljava/lang/String;)V` | Ghi dòng ra màn hình. |
| `InvokeDynamic ... makeConcatWithConstants ...` và `BootstrapMethods` | Với trình biên dịch Java 17 thông thường, phép nối chuỗi động được triển khai qua cơ chế `invokedynamic` và bootstrap từ `StringConcatFactory`. |

Chú ý `Account.class` có code cho constructor, `name` và `deposit`; bạn cần mở **cả** `PoolDemo.class` để thấy các tham chiếu từ phía gọi. Trong `Account.class`, `opened++` thường tạo một cặp `getstatic`/`putstatic` và `balance += amount` tạo `getfield`/`putfield`. Các chi tiết như thứ tự chỉ số, vị trí bytecode, cách nối chuỗi có thể thay đổi theo compiler và tùy chọn; hãy bám vào loại mục, descriptor và opcode thay vì học thuộc số `#n`.

## 6. Bytecode sử dụng tham chiếu như thế nào?

| Opcode thường gặp | Dạng constant-pool entry / ý nghĩa |
| --- | --- |
| `new`, `anewarray`, `checkcast`, `instanceof` | Trỏ tới `Class`; ví dụ `new Account` hay `checkcast Account`. |
| `getfield`, `putfield` | Trỏ tới `Fieldref`; đọc/ghi trường của đối tượng. |
| `getstatic`, `putstatic` | Trỏ tới `Fieldref`; đọc/ghi trường của lớp/interface, theo ràng buộc truy cập và kiểu trường. |
| `invokevirtual` | Thường trỏ tới `Methodref` cho phương thức instance với dispatch động theo lớp runtime của receiver. |
| `invokespecial` | Gọi constructor, phương thức superclass hoặc một số trường hợp lời gọi đặc biệt; tham chiếu thích hợp là `Methodref` hoặc `InterfaceMethodref` theo đích. |
| `invokestatic` | Gọi phương thức static; có thể dùng `Methodref` hoặc `InterfaceMethodref` nếu đích là phương thức static của interface. |
| `invokeinterface` | Trỏ tới `InterfaceMethodref`, gọi phương thức qua hợp đồng interface và dispatch trên receiver runtime. |
| `invokedynamic` | Trỏ tới `InvokeDynamic`; liên kết call site bằng bootstrap method, không mang cặp owner/method giống `Methodref`. |
| `ldc`/`ldc_w`, `ldc2_w` | Nạp hằng số hỗ trợ bởi opcode, như string, class literal, số; `ldc2_w` dùng cho `long`/`double`. |

Ví dụ một chuỗi bytecode kiểu khái niệm, **không phải bản dump byte-for-byte**:

```text
new           #...    // Class Account
dup
ldc           #...    // String "Lan"
bipush        10
invokespecial #...    // Methodref Account.<init>:(Ljava/lang/String;I)V
astore_1
aload_1
iconst_5
invokevirtual #...    // Methodref Account.deposit:(I)V
...
invokeinterface #...  // InterfaceMethodref Named.name:()Ljava/lang/String;
...
getfield      #...    // Fieldref Account.balance:I
getstatic     #...    // Fieldref Account.opened:I
```

`new` cấp phát đối tượng nhưng chưa chạy thân constructor; `dup` giữ một tham chiếu trên operand stack để `invokespecial <init>` khởi tạo đối tượng rồi vẫn còn tham chiếu cho `astore_1`. Chỉ số sau opcode là chỉ số constant pool **của lớp đang chứa bytecode**.

Điểm dễ nhầm: `invokevirtual` và `invokeinterface` thường dùng thông tin ký hiệu để **phân giải thành viên** trước, sau đó JVM mới chọn phần cài đặt phù hợp với lớp thực tế của receiver. Còn `invokestatic` gọi đích static đã phân giải; `invokespecial` có quy tắc chọn đích riêng. Vì thế “có `Methodref` tới lớp X” không đảm bảo chính code của X được thực thi trong mọi lời gọi ảo.

## 7. Từ tên trong class file đến đích thực khi chạy

Một mô hình hữu ích là:

```text
Mã nguồn Java
  -> javac sinh bytecode + constant pool theo từng class
  -> JVM load class, kiểm tra định dạng và verify bytecode
  -> linking: prepare và resolve symbolic references khi thích hợp
  -> lệnh sử dụng trường/phương thức; dispatch nếu kiểu lời gọi cần
  -> kết quả hoặc lỗi liên kết
```

**Loading** tìm định nghĩa lớp và tạo đại diện runtime. **Verification** kiểm tra các ràng buộc của class file/bytecode. **Preparation** thiết lập trạng thái ban đầu cho các trường static. **Resolution** chuyển tham chiếu ký hiệu thành thực thể runtime cụ thể theo quy tắc tra cứu, kiểu thành viên, access control và class loader. **Initialization** thực thi `<clinit>` khi có điều kiện kích hoạt; nó là bước khác với việc chỉ phân giải một tên. Thời điểm resolution có thể linh hoạt theo JVM, nhưng lỗi phải xuất hiện theo quy tắc của đặc tả.

- **Class reference:** tên nội bộ như `java/lang/String` được phân giải trong ngữ cảnh class loader của lớp tham chiếu. Hai lớp có cùng tên nhị phân nhưng do hai defining class loader khác nhau tạo ra có thể là hai kiểu runtime khác nhau.
- **Field reference:** JVM tìm trường dựa trên owner, tên **và descriptor**, xét thứ bậc thành viên phù hợp, rồi kiểm tra quyền truy cập. Dù bytecode ghi `Account.balance:I`, vị trí lưu trữ và đối tượng thực là chuyện của runtime.
- **Method reference:** JVM phân giải theo owner, tên, descriptor và các quy tắc lookup; loại invocation quyết định có dispatch ảo/interface hay không. Không thể suy luận chỉ từ dòng `Methodref` rằng phương thức nào cuối cùng chạy nếu có override.
- **Initialization:** ví dụ `new`, `invokestatic`, `getstatic`/`putstatic` thường là các tình huống kích hoạt khởi tạo lớp theo các điều kiện của JVM. Tuy nhiên đọc một biến `static final` là **compile-time constant** có thể đã được compiler nhúng thẳng vào nơi dùng, khiến bytecode phía gọi không có `getstatic` cho biến đó.

**Liên kết động không đồng nghĩa JIT compilation.** Resolution xác định ý nghĩa của tham chiếu; JIT có thể tối ưu mã máy sau đó (inline, devirtualization...), nhưng đó là cơ chế khác. Cũng đừng đồng nhất class-file constant pool với **String pool** của đối tượng `String` được intern hoặc với cache `Integer`.

## 8. `invokedynamic` và constant pool hiện đại

Không phải mọi lời gọi đều có `Methodref` trực tiếp tới phương thức đích. Mục `CONSTANT_InvokeDynamic_info` gồm **bootstrap_method_attr_index** (chỉ số trong bảng `BootstrapMethods` của class file) và **name_and_type_index**. Lúc liên kết call site, JVM sử dụng bootstrap method để nhận một `CallSite` phù hợp. Trong ví dụ nối chuỗi với Java 17, phần constant pool có thể chứa `InvokeDynamic` cùng các `MethodHandle` và thông số bootstrap liên quan `java/lang/invoke/StringConcatFactory`.

Tương tự, `CONSTANT_Dynamic_info` mô tả **dynamic constant** được tính/liên kết qua bootstrap, khác `InvokeDynamic` dành cho call site. Lambda có thể dùng `LambdaMetafactory` nhưng không nên kết luận mọi lambda hay mọi nối chuỗi đều có cùng output ở mọi compiler. Kiểu `Module`/`Package` giúp mô tả module; chúng không thay cho các `Class`/`Fieldref`/`Methodref` của lệnh Java thông thường.

Khi thấy `InvokeDynamic`, kiểm tra đồng thời: mục `InvokeDynamic`, `NameAndType` (tên + method descriptor), attribute `BootstrapMethods`, `MethodHandle`/các đối số bootstrap và bytecode `invokedynamic`. Đừng tìm một “owner class” cùng cấu trúc với `Methodref` ngay trong mục đó.

## 9. Lỗi thường gặp khi đọc hoặc thay đổi bytecode

| Hiện tượng | Cách hiểu/kiểm tra |
| --- | --- |
| Chỉ số `#n` đổi khi biên dịch lại | Đây là chỉ số cục bộ của từng class file; so sánh **loại, tên, descriptor và opcode**, không dựa vào số. |
| Thấy `Utf8` chứa tên nhưng không thấy `Methodref` | Chuỗi tên còn có thể phục vụ khai báo hoặc attribute; chỉ sự tồn tại của tên không chứng tỏ có lời gọi. |
| Tìm `Fieldref` cho hằng `static final int` mà không thấy | Hằng compile-time có thể được nhúng bằng `iconst`, `bipush`, `sipush` hoặc `ldc`; xem bytecode thực. |
| Biên dịch thành công nhưng runtime báo `NoSuchMethodError`/`NoSuchFieldError` | Thường là binary không khớp: class được load lúc chạy thiếu **tên + descriptor** đã ghi trong bên gọi. Kiểm tra JAR/classpath, phiên bản và `javap` của cả hai phía. |
| `IllegalAccessError` hoặc `IncompatibleClassChangeError` | Có thể API thay đổi quyền truy cập hoặc hình thức static/instance, class/interface... khiến liên kết không hợp lệ. |
| Không tìm thấy lớp lúc runtime | Kiểm tra classpath/module path, tên nhị phân và class loader. `NoClassDefFoundError` trong đường load/link khác với `ClassNotFoundException` thường được ném bởi API tải lớp tường minh. |
| Nhầm `NameAndType` với method thực tế | `NameAndType` thiếu owner; phải lần ngược mục `Methodref`/`InterfaceMethodref` chứa nó. |
| Nhầm source signature với JVM descriptor | Generic bị erasure; package dùng `/`; các kiểu nguyên thủy và mảng dùng mã một ký tự/`[`. |
| Cho rằng tham chiếu tới interface buộc chạy default method của interface | `invokeinterface` chọn hành vi theo receiver và quy tắc JVM; implementation của lớp có thể được gọi. |

Khi điều tra lỗi binary, thực hành theo thứ tự: xác định đúng tệp class/JAR mà runtime nạp; dùng `javap -v -p` trên **lớp gọi** để lấy owner/name/descriptor; kiểm tra **lớp đích thực sự được nạp**; đối chiếu chữ ký và tính static/access/interface; sau đó mới tìm tới class loader hoặc quá trình build. Đừng sửa số index constant pool bằng tay để chữa lỗi.

## 10. Bài tự kiểm tra

1. Nếu thấy `#18 = Fieldref #7.#11 // demo/constantpool/Account.balance:I`, chỉ ra owner, tên trường và kiểu. Trả lời: owner là `demo/constantpool/Account`, tên `balance`, kiểu `int`. Để xác minh đường tham chiếu đầy đủ, mở tiếp `#7` (`Class`) và `#11` (`NameAndType`).
2. Nếu đổi `void deposit(int)` thành `void deposit(long)` rồi chỉ biên dịch lại `Account.java`, lớp gọi cũ có tự động thích nghi không? Không. Lớp gọi cũ còn tham chiếu `deposit:(I)V` và có thể gặp `NoSuchMethodError` khi gọi. Biên dịch lại lớp gọi hoặc giữ phương thức tương thích.
3. Vì sao `Named named = account; named.name();` có thể xuất hiện `InterfaceMethodref Named.name:()Ljava/lang/String;`, còn code chạy `Account.name()`? Constant pool ghi hợp đồng interface tại **điểm gọi**; cơ chế dispatch chọn phương thức cụ thể của đối tượng runtime.

## 11. Ghi nhớ và tài liệu đối chiếu

**Bốn câu cần nhớ:** (1) mỗi `.class` có constant pool riêng; (2) một tham chiếu thành viên là **owner + name + descriptor** được nối qua chỉ số; (3) bytecode sử dụng chỉ số này, còn JVM giải quyết tham chiếu ở runtime và dispatch theo loại lệnh; (4) `javap -v -c -p` là công cụ trực tiếp nhất để đối chiếu mã Java, constant pool và bytecode.

Đọc thêm trong **Java Virtual Machine Specification, Java SE 17**:
- §4.1 — `ClassFile` và `constant_pool_count`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1
- §4.3 — Field và method descriptors: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3
- §4.4 — Các mục constant pool: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4
- §5.4.3 — Resolution: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3