# Resolution: chuyển tham chiếu ký hiệu thành liên kết dùng khi chạy

Trong **Java Virtual Machine (JVM)**, mã bytecode trong một `.class` thường không chỉ thẳng tới địa chỉ bộ nhớ của một class, field hay method. Thay vào đó, ClassFile có **constant pool** chứa các **symbolic references (tham chiếu ký hiệu)**: tên class/interface, tên thành viên và **descriptor** mô tả kiểu hoặc chữ ký JVM. Khi cần sử dụng chúng, JVM thực hiện **resolution**: xác định thực thể runtime mà tham chiếu chỉ tới, đồng thời áp dụng các quy tắc về định danh lớp, tra cứu thành viên, kiểm soát truy cập và tính tương thích.

Resolution là một phần của **linking**, nhưng không phải toàn bộ linking. Nó cũng **không đồng nghĩa** với chạy static initializer (`<clinit>`), không phải việc gọi method từ Java source và không phải cứ mỗi lần opcode chạy thì JVM lại dò lại tên từ đầu.

Mục tiêu học tập:

1. Đọc được tham chiếu ký hiệu từ constant pool bằng `javap -v`.
2. Hiểu điều kiện nào làm một tham chiếu có thể trở thành liên kết runtime hợp lệ.
3. Phân biệt **loading**, **verification**, **preparation**, **resolution**, **initialization** và **execution/dispatch**.
4. Lý giải các lỗi như `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` và `IncompatibleClassChangeError`.
5. Hiểu việc resolution có thể diễn ra sớm hoặc muộn, tùy cơ chế VM và loại tham chiếu; không áp đặt thứ tự chạy giả tạo cho tất cả JVM.
6. Biết ranh giới của resolution khi gặp **`invokevirtual`**, **`invokeinterface`**, **`invokedynamic`** và **constant dynamic**.

## 1. Constant pool chứa “tên cần giải nghĩa”, không phải địa chỉ native

Một class được `javac` biên dịch có thể mang những mục như:

```text
CONSTANT_Class_info
CONSTANT_Fieldref_info
CONSTANT_Methodref_info
CONSTANT_InterfaceMethodref_info
CONSTANT_NameAndType_info
CONSTANT_Utf8_info
```

Các mục tham chiếu **không lưu cố định địa chỉ RAM** nơi field/method sẽ ở trên một JVM cụ thể. Chúng biểu diễn các mối liên hệ tượng trưng, để class file có thể được mang sang JVM khác, kiến trúc CPU khác và môi trường nạp lớp khác mà vẫn sử dụng cùng định dạng.

Ví dụ Java:

```java
class Account {
    int balance;

    int add(int amount) {
        balance += amount;
        return balance;
    }
}
```

Đây là class minh họa, có thể lưu riêng thành `Account.java`. Một method gọi `Account.add(int)` có thể tham chiếu tới method dựa trên thông tin dạng:

```text
Class:       Account
Method name: add
Descriptor:  (I)I
```

`(I)I` nghĩa là method nhận một `int` và trả về `int`. Bộ ba này là **dữ liệu logic của symbolic method reference**, không phải “con trỏ hàm” đóng băng vào bytecode.

Sơ đồ khái niệm:

```text
ClassFile của Client
┌────────────────────────────────────────────────┐
│ constant_pool                                  │
│  #N  Methodref → Account.add:(I)I               │
└────────────────────────────────────────────────┘
                    │
                    │ resolution
                    ▼
    JVM tìm runtime class Account phù hợp
    + tìm method có tên/descriptor cần thiết
    + kiểm tra quy tắc truy cập/tương thích
                    │
                    ▼
       một tham chiếu đã được phân giải
                    │
                    │ invocation, dispatch
                    ▼
        mã method thích hợp được thực thi
```

Đây là **mô hình diễn giải**, không yêu cầu mọi JVM lưu một ô địa chỉ có cùng cấu trúc. JVM có thể dùng runtime constant pool, cache, metadata pointers, inline caches hoặc cấu trúc nội bộ khác để hiện thực hóa liên kết.

## 2. ClassFile constant pool và runtime constant pool

Theo *Java Virtual Machine Specification* (JVMS), ClassFile chứa `constant_pool` — cấu trúc nhị phân lưu các symbolic references và hằng số. Khi JVM tạo class/interface từ class file, nó có **runtime constant pool** tương ứng với các thông tin này.

| Nơi | Vai trò |
| --- | --- |
| `constant_pool` trong `.class` | Dữ liệu tuần tự hóa trong file, dùng các chỉ mục và thẻ `CONSTANT_*` |
| Runtime constant pool của class/interface | Cấu trúc runtime mà JVM dùng để thao tác với các hằng và symbolic references |
| Thông tin resolution | Kết quả nội bộ khi JVM đã phân giải một reference theo luật liên kết |
| Object/field/method lúc chạy | Thực thể runtime, có ngữ nghĩa thực thi tương ứng; không phải chuỗi UTF-8 trong file |

Ví dụ khi xem `javap -v`:

```text
#12 = Methodref          #18.#19  // Account.add:(I)I
#18 = Class              #20      // Account
#19 = NameAndType        #21:#22  // add:(I)I
#20 = Utf8                         Account
#21 = Utf8                         add
#22 = Utf8                         (I)I
```

Đây là **bản trích minh họa**, chỉ số `#12`, `#18`… là ví dụ, không phải output cam kết từ một lần biên dịch cụ thể. Kết quả thật phụ thuộc thứ tự constant pool của `javac` và code được biên dịch.

**NameAndType** kết hợp **tên** và **descriptor**. Class symbolic reference trỏ tới tên class/interface phù hợp; Fieldref/Methodref/InterfaceMethodref liên kết tới class/interface và NameAndType. Mục `Utf8` lưu chuỗi định dạng mà JVM dùng để xác định tên, chữ ký hoặc metadata.

### 2.1. Descriptor quan trọng như tên

```text
foo:()I                 → không tham số, trả int
foo:(I)I                → một int, trả int
foo:(Ljava/lang/String;)V → một String, trả void
```

Nếu class mới vẫn có method tên `foo` nhưng đổi descriptor, một binary client được biên dịch theo descriptor cũ có thể **không resolution thành công**. Vì vậy không thể chỉ tìm “một method có cùng tên” rồi coi là tương thích.

Đối với field, descriptor cũng xác định loại field, ví dụ `I` cho `int`, `Ljava/lang/String;` cho `String`. Generic `List<String>` và `List<Integer>` thường có descriptor sau **type erasure** là `Ljava/util/List;`; thông tin kiểu generic có thể nằm trong thuộc tính `Signature` nhưng không thay thế JVM field descriptor.

## 3. Phân biệt loading, linking và initialization

Vòng đời cần đọc đúng thứ tự khái niệm:

```text
              Loading
                │
                ▼
              Linking
          ┌─────┼───────┐
          │     │       │
       Verify  Prepare  Resolve
                │       │
                │       └── có thể thực hiện theo nhu cầu
                ▼
           Initialization
       (<clinit> nếu có, theo
       điều kiện active use)
                │
                ▼
             Execution
```

Sơ đồ gom các giai đoạn thành một hình để so sánh; **không khẳng định resolution bắt buộc được hoàn tất toàn bộ trước initialization hoặc mọi symbol đều được giải cùng lúc**.

- **Loading:** JVM sử dụng class loader thích hợp để tìm/lấy định nghĩa class/interface và tạo biểu diễn runtime. Việc tìm một lớp không đảm bảo lớp đã initialized.
- **Verification:** kiểm tra cấu trúc và các điều kiện hợp lệ của class file/bytecode theo quy tắc JVM.
- **Preparation:** tạo/chuẩn bị static fields và gán giá trị mặc định hoặc giá trị hằng theo luật định, **không phải chạy toàn bộ static initializer Java**.
- **Resolution:** chuyển symbolic references thành các thực thể runtime cụ thể theo luật JVMS.
- **Initialization:** thực hiện quy trình khởi tạo class/interface, bao gồm `<clinit>` nếu có và các yêu cầu về superclass/superinterfaces liên quan.
- **Execution/dispatch:** thực hiện bytecode và chọn implementation của invocation thích hợp tại thời điểm gọi.

**Điểm khác biệt:** resolution một reference tới class **không mặc nhiên gọi `<clinit>`** của class đó. Một class có thể đã được nạp/được dùng để phân giải reference nhưng vẫn chưa chạy static initializer. Ngược lại, một active use có thể yêu cầu initialization và JVM sẽ bảo đảm các tiền điều kiện liên kết cần thiết cho thao tác đó.

## 4. Resolution diễn ra khi nào? Eager và lazy resolution

JVM Specification cho phép sự linh hoạt về chiến lược **khi nào** giải các symbolic references. Một JVM có thể chọn giải sớm một số reference sau khi class được nạp, hoặc **giải muộn khi lệnh cần đến**, miễn là tuân thủ hành vi quan sát được và các ràng buộc báo lỗi của đặc tả.

### 4.1. Không phải toàn bộ constant pool được giải ngay khi load

Giả sử một class có method `unused()` tham chiếu tới một dependency không có trong runtime classpath, nhưng đường chạy hiện tại không dùng tới method đó. Trong một số tình huống và JVM, class có thể nạp hoặc bắt đầu chạy mà chưa cần resolution của symbol trong method không dùng tới. **Không được biến quan sát đó thành lời cam kết cho mọi JVM**, vì VM có thể làm thêm thao tác liên kết/kiểm tra khi thích hợp.

Việc resolution xảy ra sớm/muộn vẫn phải tuân thủ yêu cầu **báo lỗi linking tại một điểm mà việc sử dụng chương trình có thể phát sinh lỗi theo quy tắc JVMS**, thay vì tự ý thay đổi ngữ nghĩa chương trình.

### 4.2. Một symbolic reference được phân giải có cần dò từ đầu mỗi lần dùng?

Về mặt ngữ nghĩa, JVM thực hiện resolution của một symbolic reference theo một định nghĩa runtime cụ thể và ghi nhớ kết quả thành công hoặc lỗi theo các quy tắc tương ứng; **không có yêu cầu mỗi lần thực thi bytecode đều chạy lại thuật toán tìm tên**. Cách cache cụ thể do bản triển khai quyết định.

**Không nhầm cache resolution với cache kết quả method call:** một reference `Animal.speak:()V` có thể được phân giải thành một method đại diện phù hợp, nhưng `invokevirtual` ở những lần gọi khác nhau vẫn cần tìm/chọn implementation theo **runtime class của receiver**.

## 5. Resolution của class và interface symbolic references

Một `CONSTANT_Class` chứa symbolic name biểu thị class/interface hoặc array class. Khi resolution cần xác định runtime type, JVM sử dụng **class loader** thích hợp và thực hiện các ràng buộc liên quan.

### 5.1. Định danh class không chỉ là tên

Với class/interface thông thường, **runtime identity** gắn với cặp **(binary name, defining class loader)**. Hai class cùng tên do **hai defining loaders khác nhau** định nghĩa không tự động là cùng một runtime type.

```text
"org.example.Plugin" + Loader-A  → Runtime type A
"org.example.Plugin" + Loader-B  → Runtime type B

A.getName().equals(B.getName())    → true
A == B                             → false
```

Sơ đồ giả định loader A và B thực sự tự định nghĩa cùng tên. Nếu loader B chỉ *delegate* và lấy chính type của loader A, thì chúng không phải hai runtime definitions độc lập.

**Initiating loader** (loader khởi xướng việc nạp) và **defining loader** (loader thực sự định nghĩa class) có thể khác nhau. Trong resolution, JVM còn có các **loader constraints** để bảo đảm những types xuất hiện trong descriptors tương thích qua ranh giới loaders khi cần bảo toàn tính an toàn kiểu.

### 5.2. Kiểm tra accessibility của class

Một type được tìm thấy chưa chắc **được phép truy cập** từ class đang mang symbolic reference. JVM phải tôn trọng các quy tắc accessibility, module access và mối quan hệ runtime package thích hợp. Trong JVM, một runtime package không chỉ xác định bằng tên package mà còn phụ thuộc defining loader theo quy tắc JVMS.

Do đó resolution có thể phát hiện những vấn đề như:

- Class tồn tại nhưng không accessible đối với bên tham chiếu.
- Class được định nghĩa ở loader khác với kỳ vọng của dependency, làm vỡ định danh hoặc loader constraint.
- Cần một class/interface nhưng không tìm hoặc định nghĩa được theo cơ chế loader hiện tại.

**Không gọi mọi trường hợp trên là `ClassNotFoundException`**: đây là checked exception phổ biến của các API như `Class.forName` và `ClassLoader.loadClass`, trong khi các thao tác bytecode được JVM liên kết thường báo nhóm `LinkageError` hoặc các lỗi tương ứng.

## 6. Resolution của field symbolic references

Tham chiếu tới field thường dựa trên:

```text
CONSTANT_Fieldref
  ├── class/interface chứa symbolic owner
  └── NameAndType:
         fieldName
         fieldDescriptor
```

Khi giải Fieldref, JVM phải tìm field phù hợp qua thuật toán **field lookup** theo quy tắc class/interface và kiểm tra accessibility. Việc tìm field không đơn thuần là lấy public field trên đúng class mang tên ở source; **field có thể được tìm thông qua hierarchy** theo luật JVM.

### 6.1. Ví dụ

```java
class Config {
    static int port = 8080;
}

class Reader {
    static int read() {
        return Config.port;
    }
}
```

Đây là hai class minh họa; cần đặt vào các file thích hợp hoặc một compilation unit hợp lệ để chạy. Bytecode của `Reader.read()` có thể chứa:

```text
getstatic Config.port:I
ireturn
```

Resolution của `Config.port:I` liên quan tới một **field cụ thể**. Nhưng `getstatic` còn yêu cầu field thực sự là **static** và việc truy cập static field có thể kích hoạt **initialization của class/interface khai báo field** theo quy tắc phù hợp. Đây là những kiểm tra/hành vi **khác** với việc tìm field bằng tên/descriptor.

### 6.2. Field resolution khác method resolution

- Field lookup dựa trên tên, descriptor và quy tắc hierarchy của field.
- Method resolution có các thuật toán khác nhau tùy Methodref, InterfaceMethodref và các quan hệ override/default method.
- Trường instance dùng `getfield`/`putfield`, trường static dùng `getstatic`/`putstatic`. Nếu một binary client kỳ vọng field static nhưng bản class runtime đổi thành instance field, có thể xuất hiện **`IncompatibleClassChangeError`**.
- Nếu field đã bị đổi tên, xóa hoặc đổi descriptor, có thể xuất hiện **`NoSuchFieldError`**.

Các lỗi này thường do **mất binary compatibility** khi deploy thư viện khác bản dùng lúc compile, không phải lúc nào cũng có thể phát hiện khi chỉ biên dịch riêng module client.

### 6.3. Compile-time constants và inlining

```java
class Flags {
    static final int LIMIT = 100;
    static int dynamic = compute();

    static int compute() {
        return 25;
    }
}
```

Khi `Flags.LIMIT` là constant variable được compiler inline vào client, bytecode của client có thể **không chứa Fieldref** tới `LIMIT` tại điểm sử dụng: nó chỉ chứa literal 100. Do đó việc sửa giá trị `LIMIT` trong thư viện rồi không biên dịch lại client có thể làm client tiếp tục nhìn thấy **giá trị cũ đã inline**, không phải vấn đề “JVM resolution vẫn cache Fieldref cũ”.

Ngược lại, `Flags.dynamic` cần đọc giá trị static lúc runtime và thường có `getstatic`. Khi chẩn đoán, hãy dùng **`javap -c -v` trên binary client** để xem thực sự có symbolic reference đến field hay không.

## 7. Method resolution: giải symbol chưa phải chọn implementation cuối cùng

Một symbolic method reference chứa **tên class/interface chủ**, **method name** và **method descriptor**.

| Constant-pool entry | Tình huống điển hình |
| --- | --- |
| `CONSTANT_Methodref` | Method của class, dùng với `invokevirtual`, `invokespecial`, `invokestatic` tùy loại |
| `CONSTANT_InterfaceMethodref` | Method của interface, dùng với `invokeinterface` và một số tình huống invocation hợp lệ khác |
| `CONSTANT_NameAndType` | Chứa tên và descriptor phục vụ cả các method/field references |

Ví dụ:

```java
interface Printer {
    String print();
}

class ConsolePrinter implements Printer {
    public String print() {
        return "console";
    }
}
```

Trong một method:

```java
Printer printer = new ConsolePrinter();
System.out.println(printer.print());
```

Bytecode thường chứa:

```text
invokeinterface Printer.print:()Ljava/lang/String;
```

**Resolution** làm rõ symbolic reference tới method của interface theo thuật toán JVMS. Nhưng **lúc gọi**, `invokeinterface` còn phải chọn method triển khai phù hợp với **runtime class của object receiver**, ở đây là `ConsolePrinter`.

### 7.1. Resolution và dynamic dispatch là hai bước logic

```text
Constant pool:
  InterfaceMethodref Printer.print:()Ljava/lang/String;
                   │
                   ▼
      Resolution (interface method reference)
                   │
                   ▼
         invokeinterface thực thi
                   │
              receiver?
                   │
              ConsolePrinter
                   │
                   ▼
      ConsolePrinter.print() → "console"
```

Một method reference đã resolution **không làm cho mọi lệnh gọi virtual/interface về sau bắt buộc trỏ một implementation duy nhất**. Nếu receiver thuộc một subtype khác override method, dispatch có thể chọn implementation khác.

### 7.2. Các opcode invocation

| Instruction | Cơ chế sử dụng thường gặp | Quan hệ với resolution |
| --- | --- | --- |
| `invokestatic` | Gọi static method của class/interface | Cần method reference phù hợp, staticness check và initialization của declaring type khi áp dụng |
| `invokespecial` | Constructor `<init>`, private method, gọi superclass/interface theo ngữ nghĩa đặc biệt | Có các luật tra cứu/chọn method đặc biệt, không dispatch virtual bình thường |
| `invokevirtual` | Gọi instance method class có khả năng override | Resolution symbolic method rồi chọn implementation theo runtime class của receiver |
| `invokeinterface` | Gọi method thông qua interface | Resolution interface method rồi chọn implementation thích hợp ở runtime |
| `invokedynamic` | Liên kết call site bằng bootstrap method | Có cơ chế resolution/liên kết riêng; xem mục 11 |

Nếu source viết `Child c = new Child(); c.run();`, không thể chỉ nhìn chữ `run` để đoán opcode. Trình biên dịch xét kiểu khai báo, static/private/super, interface, overload và các luật ngôn ngữ; kết quả thực tế nên kiểm chứng bằng `javap`.

### 7.3. Return type cũng nằm trong JVM method descriptor

```text
method():Ljava/lang/Object;
method():Ljava/lang/String;
```

Ở **mức ClassFile**, hai descriptor trên khác nhau, dù source Java không cho phép chỉ overload theo kiểu trả về. Các **bridge methods** được compiler tạo để duy trì override/dispatch khi generics bị erase hoặc khi covariant return cần hỗ trợ có thể mang cùng tên, cùng tham số, nhưng **khác return descriptor**. Không được đồng nhất “method cùng tên” với “method reference nhất định resolution được”.

## 8. Resolution có liên quan tới access control và binary compatibility

Giả sử client `C` được compile khi library `L` có method công khai `run()`. Sau đó runtime nạp một bản library đã sửa:

- Method `run()` bị xóa/đổi descriptor → symbolic method reference cũ có thể gặp **`NoSuchMethodError`**.
- Method trở thành không accessible từ client → có thể gặp **`IllegalAccessError`**.
- Kiểu member static/instance không còn phù hợp với instruction trong client → có thể gặp **`IncompatibleClassChangeError`**.
- Library đổi hierarchy, biến một class thành interface hoặc có các ràng buộc cấu trúc khác không tương thích → có thể gặp lỗi linkage thích hợp.
- Lúc thực thi virtual invocation, nếu không thể tìm implementation concrete phù hợp, có thể gặp **`AbstractMethodError`** ở giai đoạn invocation dù các bước resolution liên quan trước đó đã xảy ra.

**Quan trọng:** lỗi ở **resolution**, **invocation**, **loading**, **initialization** có thể gần nhau trong stack trace nhưng không đồng nhất. Một chương trình in ra `NoSuchMethodError` không có nghĩa tự động “JVM tìm nhầm overload ở Java source”; thường là binary đang chạy không khớp ABI/chữ ký mà client đã biên dịch.

## 9. Ví dụ Java 17+ chạy được: symbol, dispatch và initialization

Tạo file **`ResolutionDemo.java`**:

```java
public class ResolutionDemo {
    interface Greeter {
        String greet();
    }

    static class Human implements Greeter {
        static {
            System.out.println("Human initialized");
        }

        @Override
        public String greet() {
            return "hello";
        }
    }

    static class Machine implements Greeter {
        @Override
        public String greet() {
            return "beep";
        }
    }

    static class Service {
        static {
            System.out.println("Service initialized");
        }

        static int count = 5;

        static String message() {
            return "ready";
        }
    }

    static String use(Greeter greeter) {
        return greeter.greet();
    }

    public static void main(String[] args) {
        System.out.println("start");
        System.out.println("class literal: "
                + Service.class.getSimpleName());

        Greeter first = new Human();
        System.out.println("first: " + use(first));

        Greeter second = new Machine();
        System.out.println("second: " + use(second));

        System.out.println("static field: " + Service.count);
        System.out.println("static method: " + Service.message());
        System.out.println("static method again: " + Service.message());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ResolutionDemo.java
java ResolutionDemo
```

**Standard output chính xác:**

```text
start
class literal: Service
Human initialized
first: hello
second: beep
Service initialized
static field: 5
static method: ready
static method again: ready
```

### Giải thích chi tiết

1. `Service.class.getSimpleName()` sử dụng Class mirror nhưng **không yêu cầu class initialization**, nên không in `Service initialized` trước dòng `class literal: Service`.
2. `new Human()` tạo instance và yêu cầu `Human` được initialized; static initializer của Human in đúng một lần.
3. Lần gọi `use(first)` và `use(second)` đều đi qua symbolic interface method `Greeter.greet:()Ljava/lang/String;` trong bytecode của `use`. Tuy vậy, **receiver runtime class** khác nhau, nên dispatch lần lượt đến `Human.greet()` và `Machine.greet()`.
4. Lần đọc `Service.count` là active use thích hợp và kích hoạt **class initialization** của Service, in `Service initialized` trước khi đọc giá trị 5.
5. Các lời gọi `Service.message()` sau đó không chạy lại `<clinit>`; resolution hoặc việc JVM cache liên kết không có nghĩa phải initialize class lần nữa.
6. Output không phụ thuộc thời gian thực, thread scheduling hay thông báo lỗi cụ thể của JVM.

**Điểm mấu chốt:** bài này dùng source dễ đọc để nhìn được hệ quả của các ranh giới **resolution / initialization / dispatch**. Không thể chỉ dựa vào thứ tự stdout để biết chính xác VM đã resolution từng constant pool entry lúc nào; dùng `javap` để thấy symbols và quy tắc JVMS để suy luận.

### 9.1. Đọc constant pool và bytecode

```bash
javap -c -p ResolutionDemo
javap -c -p 'ResolutionDemo$Human'
javap -c -p 'ResolutionDemo$Service'
javap -v -p ResolutionDemo
```

Nếu dùng Bash hoặc PowerShell, nháy đơn giúp bảo vệ ký tự `$` trong tên nested class; với `cmd.exe` của Windows, dùng nháy kép.

Tìm trong `javap -c -p ResolutionDemo` những mẫu điển hình:

```text
// Trong use(Greeter), mô tả rút gọn:
aload_0
invokeinterface ResolutionDemo$Greeter.greet:()Ljava/lang/String;
areturn

// Trong main, mô tả rút gọn:
ldc           ... ResolutionDemo$Service
invokevirtual ... Class.getSimpleName:()Ljava/lang/String;
...
getstatic     ... ResolutionDemo$Service.count:I
...
invokestatic  ... ResolutionDemo$Service.message:()Ljava/lang/String;
```

Đây là **minh họa**, không phải listing chứa offset/constant pool index chính xác. `javap -v` sẽ giúp quan sát các entry như `Class`, `Fieldref`, `Methodref`, `InterfaceMethodref` và `NameAndType` từ những code paths này.

Bạn có thể tự trả lời:

- `Service.class` có class literal nhưng đã làm `Service` initialized chưa?
- Symbolic owner/method descriptor của `invokeinterface` là gì?
- Có phải mỗi lần `use` đều chọn implementation giống nhau không?
- `Service.count` đọc bằng `getstatic` có hành vi active use gì?
- `Service.message()` có cần resolution và vì sao `<clinit>` không chạy lại?

## 10. Ví dụ binary incompatibility: cùng source client, đổi thư viện runtime

Resolution có giá trị thực tiễn lớn khi **compile một phiên bản, deploy một phiên bản khác**. Ví dụ sau sử dụng **hai bản độc lập** của một class `Api`, để thấy rằng client đã biên dịch vẫn giữ symbolic reference tới descriptor cũ.

**Dùng terminal Bash** (Linux, macOS hoặc Git Bash); trên Windows native, thay dấu `:` của classpath thành `;`.

Tạo cấu trúc thư mục:

```text
resolution-lab/
  api-v1/Api.java
  api-v2/Api.java
  client/Client.java
```

File **`api-v1/Api.java`**:

```java
public class Api {
    public static String message() {
        return "v1";
    }
}
```

File **`api-v2/Api.java`**:

```java
public class Api {
    public static String renamed() {
        return "v2";
    }
}
```

File **`client/Client.java`**:

```java
public class Client {
    public static void main(String[] args) {
        System.out.println(Api.message());
    }
}
```

Tại thư mục `resolution-lab/`:

```bash
mkdir -p out-api1 out-api2 out-client
javac --release 17 -d out-api1 api-v1/Api.java
javac --release 17 -cp out-api1 -d out-client client/Client.java
javac --release 17 -d out-api2 api-v2/Api.java
```

**Chạy với phiên bản thư viện client đã được biên dịch cùng:**

```bash
java -cp out-client:out-api1 Client
```

**Standard output:**

```text
v1
```

Bây giờ giữ nguyên **`Client.class`** nhưng đổi runtime classpath để chỉ nạp Api v2:

```bash
java -cp out-client:out-api2 Client
```

Lúc chạy, lời gọi tới `Api.message:()Ljava/lang/String;` không còn method phù hợp trong bản class `Api` đang được nạp. Kết quả là chương trình **thất bại với `java.lang.NoSuchMethodError`**. Không chép nguyên stack trace ở đây vì cách viết thông báo, dòng trace và chi tiết runtime khác nhau theo JDK.

### 10.1. Vì sao vẫn biên dịch được?

`Client.java` được compile **khi** `Api.message()` còn tồn tại trong `out-api1`. `Client.class` chứa symbolic reference kiểu:

```text
Methodref Api.message:()Ljava/lang/String;
```

Thay runtime library bằng một `Api.class` thiếu method này không sửa lại bytecode của client. Lúc JVM cần liên kết lời gọi, nó tìm method theo **tên và descriptor** trong bản Api đang hiện diện nhưng không thành công.

Quan sát:

```bash
javap -v -p -classpath out-client Client
```

Tìm `Methodref` hoặc lời gọi `invokestatic Api.message:()Ljava/lang/String;`. Dù library v2 chỉ còn `renamed()`, **symbolic reference bên trong client không tự biến thành `renamed()`**.

### 10.2. Nếu biên dịch lại client thì sao?

Giữ `Client.java` cũ và biên dịch với `-cp out-api2`, `javac` sẽ báo lỗi **không tìm thấy symbol `Api.message()`** tại thời điểm biên dịch. Đây là lỗi nguồn-API compile-time, khác với **`NoSuchMethodError`** tại runtime của binary client cũ.

Không cần xoá toàn bộ ứng dụng để chẩn đoán: hãy kiểm tra **bytecode của client**, **bản JAR/class thực sự có trong runtime classpath**, **binary name**, **loader** và **descriptor**.

### 10.3. Biến thể: thay đổi field

Nếu library v1 có `public static int count;` rồi library v2 xóa hoặc đổi field, client cũ có `getstatic Api.count:I` có thể gặp `NoSuchFieldError`. Nếu giữ tên/descriptor nhưng đổi `static` thành instance field, loại lỗi cần xét là **`IncompatibleClassChangeError`**. Đây là các tình huống khác nhau; không nên gộp thành `NoSuchMethodError`.

## 11. Error taxonomy: lỗi xảy ra ở bước nào?

| Triệu chứng/lỗi | Cần kiểm tra điều gì? | Nhóm vấn đề |
| --- | --- | --- |
| `ClassNotFoundException` khi gọi `Class.forName` | Loader/API không tìm thấy class theo tên/đường nạp | Explicit reflective loading/lookup API |
| `NoClassDefFoundError` | Class được JVM cần đến nhưng không lấy/khởi tạo được trong trạng thái hiện tại | Loading/linking/initialization; xem cause |
| `NoSuchFieldError` | Field name/descriptor trong binary client không khớp thư viện runtime | Field resolution |
| `NoSuchMethodError` | Method name/descriptor của symbolic reference không có đích phù hợp | Method resolution/binary compatibility |
| `IllegalAccessError` | Quyền truy cập runtime không phù hợp với reference hiện có | Access check lúc linking |
| `IncompatibleClassChangeError` | Thay đổi dạng class/interface hoặc static/instance hay tương thích nhị phân khác | Linking/invocation |
| `AbstractMethodError` | Không thể tìm concrete implementation thích hợp cho lời gọi | Invocation/dispatch |
| `ExceptionInInitializerError` | Static initializer thất bại theo trường hợp JVM bọc exception | Class initialization, **khác resolution** |
| `BootstrapMethodError` | Bootstrap method cho dynamic linkage/constant thất bại trong trường hợp tương ứng | Dynamic linkage / bootstrap |

Một `NoClassDefFoundError` **không nhất thiết** là không tìm thấy file; class có thể đã lỗi initialization trước đó. Đọc **cause chain, tên class, loader, đường nạp và stack trace**.

**`LinkageError`** là nhóm lỗi rộng; những subtype nêu trên có vị trí ngữ nghĩa khác nhau. `ClassNotFoundException` là checked exception, không phải subtype của `LinkageError`. Giữ phân biệt này khi viết catch clauses hoặc đọc logs.

## 12. `invokedynamic`, method handles và dynamic constants: resolution nâng cao

Từ Java 7 trở lên, định dạng ClassFile và JVM đã có thêm cơ chế liên kết động. Không nên giả định mọi entry constant pool đều là `Fieldref`/`Methodref` truyền thống.

### 12.1. `invokedynamic` và bootstrap method

Instruction **`invokedynamic`** liên quan tới `CONSTANT_InvokeDynamic` và một **bootstrap method**. Khi call site cần liên kết, JVM sử dụng bootstrap information, method types/handles và static arguments thích hợp để tạo ra **call site linkage** theo JVMS.

```text
invokedynamic instruction
    │
    ├── name + method type
    ├── bootstrap method reference
    └── static bootstrap arguments
                │
                ▼
         Bootstrap invocation
                │
                ▼
             CallSite
                │
                ▼
        Invocation target handle
```

Sơ đồ là mô hình logic, không bắt một implementation JVM hiện thực đúng số bước vật lý như hình. `CallSite` và `MethodHandle` thuộc API `java.lang.invoke`; chúng không đơn thuần là `java.lang.reflect.Method`.

Compiler hiện đại có thể dùng `invokedynamic` cho **lambda expressions** và **string concatenation**, tùy phiên bản/chiến lược biên dịch. Ví dụ:

```java
Runnable action = () -> System.out.println("run");
action.run();
```

Đây là **đoạn minh họa trong một method**, có thể tương ứng với `invokedynamic` dùng lambda metafactory, thay vì JVM có instruction đặc biệt tên `lambda`.

### 12.2. `CONSTANT_MethodHandle` và `CONSTANT_MethodType`

- **`CONSTANT_MethodHandle`** mô tả một tham chiếu symbolic tới một trường/phương thức/cơ chế gọi thích hợp; resolution có các quy tắc riêng, bao gồm reference kind và kiểm tra access.
- **`CONSTANT_MethodType`** mô tả kiểu của phương thức ở mức tham số và kết quả; khi giải thành công, JVM có đối tượng kiểu phương thức tương ứng.
- Khi resolution hoặc bootstrap liên quan tới loader/access sai, lỗi sẽ phụ thuộc loại symbolic reference và bước thực tế. Đừng gộp tất cả thành `NoSuchMethodError`.

### 12.3. `CONSTANT_Dynamic` (condy)

**Constant dynamic** cho phép một hằng trong constant pool được tính qua bootstrap mechanism khi liên kết giá trị. Nó khác với static final constant variable inlined đơn giản và khác với việc gọi Java method mỗi lần muốn đọc một hằng.

Không nhất thiết có `ConstantDynamic` trong class file thông thường: tùy JDK/compiler/library sinh bytecode. `javap -v` có thể hiển thị các constant pool entries và `BootstrapMethods` khi class file thực tế chứa cơ chế đó.

**Giới hạn trong bài:** các cách giải `CONSTANT_Dynamic`, `CONSTANT_InvokeDynamic` và method handles có quy tắc đặc biệt về bootstrap, accessibility, type consistency, vòng lặp resolution và lỗi. Để phân tích chính xác một trường hợp, cần đọc đúng mục tương ứng của JVMS §5.4.3 và §6.5 thay vì áp dụng máy móc thuật toán Fieldref/Methodref thông thường.

## 13. Resolution, method selection và JIT optimization: tránh nhầm tầng

Ba bước khái niệm có thể xảy ra quanh một lời gọi:

```text
Source Java            JVM semantics                  Implementation
-----------            -------------                  --------------
a.run()                symbolic method resolution     runtime pool/cache
                       + method selection             dispatch/vtable...
                       + invocation                   interpreter/JIT code
```

- **Resolution** xác định đối tượng mà một symbolic reference biểu thị theo các quy tắc của JVM.
- **Selection/dispatch** xác định method implementation cụ thể trong một lời gọi có tính đa hình. Cùng một resolved symbolic reference có thể dẫn đến implementation khác nhau với receiver khác nhau.
- **JIT** có thể inline, devirtualize hoặc dùng inline cache, nhưng chỉ khi giữ đúng ngữ nghĩa Java/JVM; một optimization không biến một symbolic reference sai thành hợp lệ hay được phép bỏ qua lỗi liên kết bắt buộc.

Địa chỉ máy thật và cấu trúc metadata nội bộ **không thuộc định dạng chuẩn của `CONSTANT_Methodref`**. Class file đem sang CPU khác vẫn chứa symbolic reference đã biên dịch, còn JVM bên đích làm nhiệm vụ nạp và liên kết theo runtime của nó.

### 13.1. Resolution không phải object construction

Giải `CONSTANT_Class` về runtime class không phải tạo instance của class đó. `new SomeClass()` có thể khiến JVM phải load/link/initialize class phù hợp, rồi mới cấp phát đối tượng và chạy constructor `<init>` trong trình tự đúng. Đừng nói “resolution gọi `new`” hoặc “resolution tự chạy constructor”.

### 13.2. Resolution không phải reflection

`Class.forName`, `Method.invoke`, `getDeclaredMethod` là **Java APIs** cho runtime type lookup và reflective access. Chúng có thể dẫn tới loading/linking/initialization/invocation bên dưới, nhưng **không đồng nhất** với instruction-level resolution của một constant pool symbolic reference. Ví dụ lỗi `ClassNotFoundException` của `Class.forName` khác với `NoSuchMethodError` của một binary Methodref.

### 13.3. Resolution không phụ thuộc chỉ duy nhất vào classpath

Classpath/module path ảnh hưởng lớp nào được tìm/định nghĩa, nhưng **class loader hierarchy, module boundaries, package access, descriptors và runtime class identity** cũng rất quan trọng. Hai ứng dụng có cùng file `.class` trên disk có thể hành xử khác khi loader/module arrangement khác.

## 14. Hướng chẩn đoán từng bước khi nghi lỗi resolution

1. **Ghi lại lỗi đầy đủ:** loại `Error`/exception, tên class, method/field, descriptor nếu được in, cause chain và thời điểm phát sinh.
2. **Xác nhận runtime:** `java --version`, classpath/module path, JARs thực tế, version của dependency. Không chỉ nhìn cấu hình IDE hoặc build file.
3. **Đọc ClassFile client:** `javap -v -p -classpath <client-path> Client`; tìm `Methodref`, `InterfaceMethodref`, `Fieldref`, `Class` liên quan.
4. **Đọc ClassFile dependency:** `javap -p -s -classpath <runtime-lib-path> Api`; so tên, descriptor và static/instance status với kỳ vọng client.
5. **Xác nhận class loader khi cần:** log `SomeType.class.getClassLoader()` và `getProtectionDomain().getCodeSource()` khi API/permissions phù hợp; xem quan hệ delegation và module.
6. **Tách resolution khỏi initialization:** lỗi do `<clinit>` không được “sửa” bằng cách đổi descriptor, và lỗi `NoSuchMethodError` không tự hết bằng cách gọi static initializer.
7. **Khôi phục binary compatibility:** dùng bản thư viện phù hợp hoặc biên dịch lại/deploy nhất quán các bên sau khi thay đổi public API/ABI.

Các dấu `<client-path>` và `<runtime-lib-path>` ở mục này là **ký hiệu vị trí đường dẫn**, không phải tên file thật để chép nguyên xi. Với ví dụ hoàn chỉnh mục 10, thay bằng `out-client` và `out-api1` hoặc `out-api2`.

### Các lỗi dễ đưa ra kết luận sai

| Kết luận vội | Sự thật cần kiểm tra |
| --- | --- |
| “Lỗi `NoSuchMethodError` nghĩa là source client không biên dịch.” | Client có thể đã biên dịch với API cũ; lỗi xảy ra khi **binary được liên kết với runtime API khác** |
| “Mỗi method call phải đi tìm lại tên đầy đủ từ disk.” | JVM có thể giữ kết quả resolution; gọi đa hình vẫn có method selection riêng |
| “Resolution xong thì `<clinit>` chắc chắn đã chạy.” | Resolution không mặc nhiên kích hoạt class initialization |
| “`Class.forName` và `CONSTANT_Class` resolution là một hàm API.” | Reflection và JVM symbolic resolution là hai tầng khác nhau |
| “Cùng class name tức cùng runtime type.” | **Defining loader** là một phần định danh class/interface |
| “`Methodref` chỉ cần name, không cần descriptor.” | Descriptor gồm tham số **và return type** của method |
| “JVM phải resolve toàn bộ constant pool ngay trước `main`.” | VM được phép dùng chiến lược eager/lazy theo luật JVMS |
| “JIT inline một lời gọi thì không còn lỗi binary compatibility.” | Optimization phải giữ nguyên các hiệu ứng và lỗi theo ngữ nghĩa |
| “Đổi static field thành instance field không ảnh hưởng binary client.” | Client có opcode `getstatic` sẽ không tương thích với field instance |
| “`invokedynamic` là gọi Methodref class bình thường.” | Nó có **bootstrap/call-site linkage** riêng |

## 15. Bài tập tự kiểm tra

### Bài tập 1 — Đọc một symbolic method reference

Một constant pool entry tương đương:

```text
Methodref: pkg/MathUtil.calc:(II)I
```

**Hỏi:** JVM cần những thành phần gì để resolution?  
**Đáp án:** Runtime class `pkg.MathUtil` phù hợp, method name `calc`, descriptor nhận **hai `int`** và trả **`int`**, cùng các yêu cầu về loader, lookup, accessibility và tính tương thích áp dụng. Không thể chỉ tìm một method tên `calc` bất kỳ.

### Bài tập 2 — Vì sao overload không gây lẫn?

Class có:

```java
static int parse(String text) { return 1; }
static int parse(int number)  { return 2; }
```

Đây là **hai method minh họa** trong cùng class. Cặp descriptors khác nhau: `(Ljava/lang/String;)I` và `(I)I`; JVM method references phân biệt được. Lựa chọn overload ở **compile time của Java source**, còn resolution giải symbol mang descriptor đã được ghi trong binary.

### Bài tập 3 — Resolution hay initialization?

Source Java đọc:

```java
int x = Settings.value;
```

nơi `Settings.value` là một static field **không phải compile-time constant variable**.  
**Đáp án:** JVM cần liên kết Fieldref `Settings.value` theo luật, và việc `getstatic` có thể yêu cầu **class initialization** trước khi đọc. Đây là hai trách nhiệm khác nhau.

### Bài tập 4 — Một method symbol, hai receiver

```java
Printer a = new ConsolePrinter();
Printer b = new NetworkPrinter();
a.print();
b.print();
```

Giả sử cả hai classes triển khai `Printer`.  
**Hỏi:** `invokeinterface` có nhất thiết gọi cùng implementation không?  
**Đáp án:** Không. Cùng symbolic interface method có thể dispatch khác theo runtime class của `a` và `b`.

### Bài tập 5 — Phiên bản library sai

Client compiled với `Api.message:()Ljava/lang/String;`, nhưng runtime `Api` chỉ có `Api.renamed:()Ljava/lang/String;`.  
**Đáp án:** Khi JVM cần liên kết lời gọi, có thể gặp **`NoSuchMethodError`**. Đổi classpath để dùng binary tương thích hoặc biên dịch lại client sau khi cập nhật source.

### Bài tập 6 — Hai loaders

Loader A và Loader B định nghĩa cùng binary name `example.Model` độc lập.  
**Hỏi:** JVM có coi hai runtime classes là một chỉ vì tên giống nhau?  
**Đáp án:** Không. Runtime identity của class/interface phụ thuộc **binary name + defining class loader**.

### Bài tập 7 — Compile-time constant

`static final int LIMIT = 9;` là compile-time constant variable. Source client in `Config.LIMIT`.  
**Hỏi:** Bytecode client luôn chứa `getstatic Config.LIMIT:I`?  
**Đáp án:** Không. Compiler có thể **inline số 9**; phải dùng `javap` để biết binary thực sự chứa instruction gì.

### Bài tập 8 — Dynamic call sites

**Hỏi:** `invokedynamic` có cần symbolic class method reference thông thường mang đủ method implementation cuối cùng?  
**Đáp án:** Không theo mô hình đó. Nó sử dụng **bootstrap method linkage** để liên kết call site và method type; cơ chế khác với giải một `Methodref` rồi gọi static method.

## 16. Tóm tắt và tài liệu tra cứu

- **Symbolic reference** cho biết một class, field, method hoặc kiểu động được nói đến theo **tên, descriptor và constant-pool structures**.
- **Resolution** xác định runtime target theo các quy tắc của JVM, gồm loading khi cần, lookup, access/loader constraints và báo lỗi thích hợp.
- **Timing** có thể eager hoặc lazy; đừng dựa vào một thứ tự resolve duy nhất cho mọi JVM.
- **Method resolution ≠ dynamic dispatch**; virtual/interface invocation còn chọn implementation dựa trên receiver.
- **Resolution ≠ initialization**; `<clinit>` và active use là một trách nhiệm khác của JVM.
- **Binary compatibility** phụ thuộc đúng tên, descriptor, staticness, accessibility và các ràng buộc runtime; đổi thư viện mà không cập nhật client có thể gây `LinkageError`.
- **`invokedynamic`/`CONSTANT_Dynamic`** có bootstrap linkage đặc thù, không thể quy hết thành Fieldref/Methodref cổ điển.

Tài liệu chuẩn:

- *The Java Virtual Machine Specification*, **§5.3 Loading, §5.4 Linking, §5.4.3 Resolution, §5.5 Initialization**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- *JVMS* **§4.4 Constant Pool** và các loại `CONSTANT_*`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- *JVMS* **§6.5 Instructions** — `getstatic`, `getfield`, `invokevirtual`, `invokeinterface`, `invokestatic`, `invokespecial`, `invokedynamic`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html

**Kết luận:** Khi bytecode của một class nói “gọi `Api.message:()Ljava/lang/String;`”, nó đang mang **một hợp đồng ký hiệu**, không phải địa chỉ method được đóng vào class file. **Resolution** là cầu nối từ hợp đồng ấy đến thế giới runtime với tên class, defining loader, quyền truy cập và descriptors cụ thể. Khi đã tách được resolution khỏi initialization và dispatch, việc đọc `javap` và xử lý các lỗi binary compatibility trở nên rõ ràng, có thể kiểm chứng.