# getfield, putfield, getstatic và putstatic khi truy cập trường trong JVM

## Mục tiêu bài học

Khi đọc mã nguồn Java, các biểu thức như `object.count`, `object.count = 5`, `Counter.total` hay `Counter.total = 10` trông gần giống nhau. Ở cấp bytecode JVM, chúng thuộc **hai nhóm truy cập khác nhau**: trường gắn với một đối tượng (*instance field*) và trường của lớp (*static field*). Ngoài ra, thao tác đọc và ghi cũng dùng opcode khác nhau.

Sau bài này, bạn sẽ:
- Phân biệt chính xác bốn instruction **`getfield`, `putfield`, `getstatic`, `putstatic`** theo đối tượng hay lớp, đọc hay ghi.
- Giải thích operand stack trước/sau mỗi lệnh; hiểu vì sao `getfield`/`putfield` cần `objectref`, còn các lệnh static không cần.
- Lần theo operand chỉ mục của bytecode đến **`CONSTANT_Fieldref`** và ý nghĩa của owner, field name, descriptor, resolution.
- Nhận biết tác động của `getstatic`/`putstatic` lên **class initialization**, quy định đối với `final`, `volatile` và các lỗi runtime.
- Biên dịch ví dụ Java 17+, dùng **`javap -c -v -p`** để nhận diện và giải thích bytecode trong constructor, class initializer và phương thức thường.
- Tránh nhầm field hiding với method overriding, truy cập field với local variable, và constant inlining với đọc field runtime.

## 1. Bảng phân biệt bốn opcode

| Opcode | Mã opcode JVM | Loại field | Hành động | Thao tác với operand stack |
| --- | --- | --- | --- | --- |
| `getfield` | 180 (`0xb4`) | Instance | Đọc giá trị field từ đối tượng | `..., objectref → ..., value` |
| `putfield` | 181 (`0xb5`) | Instance | Ghi giá trị vào field của đối tượng | `..., objectref, value → ...` |
| `getstatic` | 178 (`0xb2`) | Static | Đọc giá trị field của lớp/interface khai báo | `... → ..., value` |
| `putstatic` | 179 (`0xb3`) | Static | Ghi giá trị vào field của lớp/interface khai báo | `..., value → ...` |

Đây là **mô hình của operand stack**, trong đó dấu `...` biểu diễn những phần tử thấp hơn không bị lệnh thay đổi. Stack được viết từ đáy (trái) đến đỉnh (phải).

- **`getfield`** cần tham chiếu đối tượng để biết instance nào đang được đọc; nó pop `objectref` rồi push giá trị field.
- **`putfield`** cần cả tham chiếu đối tượng và giá trị mới, với **`value` ở đỉnh**, `objectref` ngay dưới nó; lệnh pop cả hai và không để lại một giá trị trên stack.
- **`getstatic`** không cần objectref; field static gắn với class/interface đã được resolve.
- **`putstatic`** chỉ cần giá trị mới trên stack.

Tất cả bốn lệnh có cùng định dạng bytecode gồm một opcode và **hai byte operand chỉ mục**:

~~~text
getfield    indexbyte1 indexbyte2
putfield    indexbyte1 indexbyte2
getstatic   indexbyte1 indexbyte2
putstatic   indexbyte1 indexbyte2

constant-pool index = (indexbyte1 << 8) | indexbyte2
~~~

Toán hạng đó là chỉ mục không dấu **16-bit** trong *run-time constant pool* của class đang thực thi. Nó **không phải offset trực tiếp của field trong bộ nhớ**, cũng không phải địa chỉ của một object. Khi xem bằng `javap`, nó được in dưới dạng `#N` kèm chú thích về trường được tham chiếu.

## 2. Hai kiểu trường: instance và static

Xét định nghĩa class:

~~~java
public class Counter {
    int count;           // Instance field
    static int total;    // Static field
}
~~~

Đây là một **class minh họa khai báo**; chưa có phương thức `main` để chạy. Ý nghĩa:

- Mỗi đối tượng `new Counter()` có trạng thái `count` của **riêng nó**. Đọc `a.count` và `b.count` có thể trả giá trị khác nhau.
- Trường `total` thuộc về **class `Counter`** theo ngữ nghĩa Java. Mọi instance cùng định nghĩa class đó truy cập cùng trường static.
- Instance field và static field là hai loại symbol truy cập riêng; một opcode `getfield` **không được dùng để đọc trường static**, và `getstatic` **không được dùng để đọc instance field**.
- Kiểu Java của field (`int`, `long`, `String`, ...) không quyết định việc dùng `getfield` hay `getstatic`; **tính static** mới là điểm phân biệt.

Ví dụ mã nguồn:

~~~java
Counter a = new Counter();
Counter b = new Counter();
a.count = 3;
b.count = 8;
Counter.total = 11;
~~~

Các phép gán cho `a.count` và `b.count` thường biên dịch thành **`putfield`** với objectref khác nhau; phép gán cho `Counter.total` thường dùng **`putstatic`**. Đoạn này minh họa biểu thức, muốn chạy phải đặt trong class/phương thức hợp lệ.

### Local variables, array elements và thuộc tính đối tượng khác gì?

| Mã nguồn / tác vụ | Nhóm bytecode phổ biến |
| --- | --- |
| Đọc một biến local `int n` | `iload`, `iload_0`... |
| Ghi một biến local `int n` | `istore`, `istore_0`... |
| Đọc/ghi instance field | `getfield` / `putfield` |
| Đọc/ghi static field | `getstatic` / `putstatic` |
| Lấy độ dài mảng `array.length` | `arraylength` |
| Đọc/ghi phần tử mảng `arr[i]` | `iaload/iastore`, `aaload/aastore` và biến thể khác tùy kiểu |

Mảng Java có thuộc tính `length` đặc biệt nhưng **không đọc bằng `getfield`**. Toán tử truy cập mảng được triển khai qua bộ lệnh mảng. JavaBean getter như `obj.getCount()` là **lời gọi phương thức** (chẳng hạn `invokevirtual`), không tự động là `getfield` đối với caller. Một field tên `count` và method tên `getCount` là hai thành viên khác nhau.

## 3. Operand stack trong lệnh truy cập instance field

### `getfield`: pop tham chiếu, push giá trị

Giả sử `counter` có `count = 7`. Mã nguồn:

~~~java
int result = counter.count;
~~~

Một hình thức bytecode khái niệm:

~~~text
aload_1              // stack: [..., objectref]
getfield #12         // stack: [..., 7]
istore_2             // stack: [...]
~~~

Giá trị `objectref` đến từ `aload_1` (giả định biến `counter` nằm tại local slot 1); chỉ số `#12` minh họa và **không phải chỉ số cố định**. Trước `getfield`, JVM phải có đúng tham chiếu của instance thuộc loại phù hợp trên đỉnh stack. Sau `getfield`, tham chiếu ấy bị tiêu thụ, chỉ còn giá trị field đã đọc.

Nếu instance field có kiểu `long` hay `double`, giá trị trả lên stack thuộc **category 2** (chiếm hai đơn vị độ sâu); kiểu `int`, `float` và reference là category 1. Với field mang descriptor `Z`, `B`, `C`, `S`, giá trị stack dùng dạng **`int`** theo quy tắc JVM; điều này không đồng nghĩa toàn bộ field trong object đều có 32 bit lưu trữ vật lý.

### `putfield`: thứ tự stack bắt buộc

Với câu lệnh:

~~~java
counter.count = 9;
~~~

Bytecode dạng thường gặp:

~~~text
aload_1              // stack: [..., objectref]
bipush 9             // stack: [..., objectref, 9]
putfield #12         // stack: [...]
~~~

**Objectref nằm dưới value**. Trật tự ngược lại sẽ không thỏa stack contract của `putfield`. Khi biên dịch biểu thức gán **có sử dụng giá trị kết quả**, compiler có thể dùng instruction như `dup`/`dup_x1`/`dup2_x1` để giữ lại một bản giá trị trước khi `putfield` tiêu thụ operands. `putfield` tự nó **không push kết quả assignment**.

Câu lệnh `counter.count++` thường gồm các bước đọc rồi ghi:

~~~text
aload_1
dup
getfield #12
iconst_1
iadd
putfield #12
~~~

Đây là mô hình minh họa thao tác tăng trên **instance field int**. Opcode `iinc` chỉ thao tác trực tiếp local variable kiểu int, **không** thay thế toàn bộ `getfield` + `iadd` + `putfield`. Với kiểu nhỏ hơn int, compiler có thể cần narrowing như `i2b`, `i2s` hay `i2c`.

**Tăng field bằng chuỗi lệnh không có nghĩa là atomic.** Nếu nhiều thread cùng thực hiện `counter.count++` không đồng bộ, chúng có thể đọc cùng giá trị, tính rồi ghi đè nhau; `volatile` đơn thuần cũng không biến phép read-modify-write thành atomic (xem mục đồng thời).

## 4. Truy cập static field và khởi tạo class

### `getstatic`

Đọc một static field:

~~~java
int x = Counter.total;
~~~

Bytecode minh họa:

~~~text
getstatic #18         // stack: [..., total]
istore_1              // stack: [...]
~~~

Không cần `aload` một đối tượng `Counter` trước `getstatic`. JVM resolve reference đến field và nếu **class hoặc interface thực sự khai báo field đó** chưa được khởi tạo, `getstatic` kích hoạt việc khởi tạo theo quy tắc JVMS (`5.5), ngoại trừ trường hợp code đã được biên dịch theo hình thức khác như inline compile-time constant.

### `putstatic`

Ghi static field:

~~~java
Counter.total = 20;
~~~

Bytecode thường gặp:

~~~text
bipush 20             // stack: [..., 20]
putstatic #18         // stack: [...]
~~~

Khi thực thi thật, `putstatic` cũng yêu cầu class/interface **khai báo field được resolve** hoàn thành initialization nếu chưa xong, trước khi ghi giá trị mới theo quy tắc JVM.

### Vì sao class initialization quan trọng?

Trong giai đoạn **preparation**, các static field (không kể một số gán hằng theo `ConstantValue`) được chuẩn bị với **giá trị mặc định** theo kiểu: 0 cho `int`, `false` cho `boolean`, `null` cho reference. Giai đoạn **initialization** chạy class initializer `<clinit>` nếu có, thực thi các static initializer/biểu thức khởi tạo theo thứ tự do Java quy định.

Khi class đã được khởi tạo thành công, đọc `getstatic` trả giá trị hiện tại của field. Nếu initialization thất bại, truy cập có thể dẫn tới `ExceptionInInitializerError` hoặc ở những lần dùng tiếp theo là `NoClassDefFoundError`, tùy trường hợp.

Tránh khái quát “lần đầu nhắc tên class sẽ khởi tạo class”: class literal `SomeClass.class`, hằng compile-time đã inline và nhiều thao tác reflection/class loading có quy tắc riêng. Nói chính xác **đọc/ghi static field được resolve qua opcode getstatic/putstatic** là một trong những hoạt động kích hoạt class initialization.

## 5. Ví dụ Java 17+ dùng đủ bốn opcode

Tạo đúng tệp **`FieldOpsDemo.java`**:

~~~java
public class FieldOpsDemo {
    static int total = 10;
    int value;

    FieldOpsDemo(int initial) {
        value = initial;
    }

    static int change(FieldOpsDemo target) {
        int current = target.value;
        target.value = current + 2;

        int previousTotal = total;
        total = previousTotal + 1;

        return target.value + total;
    }

    public static void main(String[] args) {
        FieldOpsDemo box = new FieldOpsDemo(5);
        System.out.println("sum=" + change(box));
        System.out.println("value=" + box.value);
        System.out.println("total=" + total);
    }
}
~~~

Biên dịch và chạy trên **JDK 17 hoặc mới hơn**:

~~~bash
javac --release 17 FieldOpsDemo.java
java FieldOpsDemo
~~~

**Stdout chính xác:**

~~~text
sum=18
value=7
total=11
~~~

Phân tích:

1. Trước khi thực thi `main`, class `FieldOpsDemo` được initialization. Lời khai báo `static int total = 10;` thông thường làm compiler sinh một đoạn trong `<clinit>` có **`putstatic FieldOpsDemo.total:I`**.
2. Constructor nhận `initial = 5` và ghi `this.value = 5` bằng **`putfield FieldOpsDemo.value:I`**.
3. Trong `change`, `target.value` được đọc qua **`getfield`**, cộng 2, rồi được ghi lại bằng **`putfield`**.
4. `total` là static field nên việc đọc ra `previousTotal` dùng **`getstatic`**, còn phép gán `total = previousTotal + 1` dùng **`putstatic`**.
5. Biểu thức trả về đọc cả `target.value` qua **`getfield`** và `total` qua **`getstatic`**, tính `7 + 11 = 18`.

Quan sát bytecode và constant pool:

~~~bash
javap -c -p FieldOpsDemo
javap -v -p FieldOpsDemo
~~~

Tìm trong phương thức `change` các dòng có chú thích dạng:

~~~text
getfield     #N  // Field value:I
putfield     #N  // Field value:I
getstatic    #M  // Field total:I
putstatic    #M  // Field total:I
~~~

Phần trên là **mẫu để nhận biết**, không phải toàn bộ output của một bản build cụ thể. Chỉ số `#N` và `#M`, offset và lựa chọn một số instruction phụ thuộc vào compiler/phiên bản. Trong `main` còn có `getstatic java/lang/System.out:Ljava/io/PrintStream;` để lấy stream in ra console; đây là một ví dụ static field **thuộc class khác** với `FieldOpsDemo`.

### Theo dõi operand stack ở phương thức `change`

Giả sử local slot 0 chứa `target`:

~~~text
Bước đọc instance:
  aload_0               Stack [target]
  getfield value:I      Stack [5]
  istore_1              Stack []

Bước ghi instance:
  aload_0               Stack [target]
  iload_1               Stack [target, 5]
  iconst_2              Stack [target, 5, 2]
  iadd                  Stack [target, 7]
  putfield value:I      Stack []

Bước đọc static:
  getstatic total:I     Stack [10]
  istore_2              Stack []

Bước ghi static:
  iload_2               Stack [10]
  iconst_1              Stack [10, 1]
  iadd                  Stack [11]
  putstatic total:I     Stack []
~~~

Đây là **sơ đồ phân tích logic**; thứ tự opcode trong disassembly thực tế có thể xuất hiện với những dạng tương đương. Bất biến cốt lõi là giá trị trên stack phù hợp với hợp đồng lệnh và descriptor trường.

## 6. Fieldref trong constant pool: owner + name + descriptor

Bốn opcode không chứa tên field dưới dạng text ngay trong operand instruction. Chúng dùng chỉ mục **`CONSTANT_Fieldref`** trong run-time constant pool của class đang thực thi.

Một symbolic reference điển hình có chuỗi:

~~~text
getfield #12
    |
    +--> #12 CONSTANT_Fieldref
           |
           +--> class_index --------> CONSTANT_Class
           |                              |
           |                              +--> CONSTANT_Utf8 "org/example/Account"
           |
           +--> name_and_type_index -> CONSTANT_NameAndType
                                         |
                                         +--> CONSTANT_Utf8 "balance"
                                         +--> CONSTANT_Utf8 "J"
~~~

Theo đó, một tham chiếu symbolic có thể mang ý nghĩa:
**`org/example/Account.balance:J`**, tức field tên `balance` có descriptor `J` (`long`) thuộc class/interface được xác định qua quy tắc resolution.

Định dạng `CONSTANT_Fieldref_info` có tag 9 và hai chỉ mục `class_index`, `name_and_type_index`. `CONSTANT_NameAndType` lại trỏ đến hai `CONSTANT_Utf8`: **tên field** và **field descriptor**. Chỉ mục không thể hiểu đúng nếu chỉ nhìn một số `#12` mà không tra cả chuỗi entry.

Một vài field descriptor thường gặp:

| Descriptor | Kiểu Java |
| --- | --- |
| `I` | `int` |
| `J` | `long` |
| `D` | `double` |
| `F` | `float` |
| `Z` | `boolean` |
| `B` | `byte` |
| `S` | `short` |
| `C` | `char` |
| `Ljava/lang/String;` | `java.lang.String` |
| `[I` | `int[]` |
| `Ljava/util/List;` | `java.util.List` (erasure của kiểu generic như `List<String>`) |

**Descriptor không phải tên kiểu hiển thị dạng Java.** Ví dụ field `long balance` có descriptor `J`, không phải chuỗi `long`. Trong `javap -v`, có thể thấy dòng như `Fieldref ... // Field org/example/Account.balance:J`.

## 7. Resolution, kiểm tra loại field và kiểm tra quyền truy cập

Một JVM phải xác định field thực tế từ symbolic reference qua **field resolution** (JVMS `5.4.3.2), theo quy tắc tìm field trong class/interface hierarchy, kiểm tra class loading và khả năng truy cập. Quá trình resolution có thể thực hiện sớm hoặc theo nhu cầu, trong những giới hạn mà JVMS cho phép.

Phân biệt ba bước:

1. **Tham chiếu ký hiệu:** tên owner, tên field và descriptor đã có trong constant pool.
2. **Resolution:** JVM tìm field thực tế và thực hiện các kiểm tra liên kết/quyền theo quy tắc.
3. **Thực thi instruction:** kiểm tra loại static/instance, điều kiện `final` và objectref khi cần, rồi đọc/ghi giá trị.

**Không được đồng nhất `Fieldref` với địa chỉ/offset vật lý.** JVM triển khai có thể cache kết quả resolution hoặc tối ưu hóa đường truy cập khi chạy, nhưng thông tin nhị phân chuẩn hóa vẫn là symbolic reference.

### Field cùng tên nhưng khác loại/descriptor

Một lớp có thể công khai các member khác nhau qua nhiều phiên bản binary. Caller đã biên dịch theo field `score:I` sẽ tìm field phù hợp **tên và descriptor**, không đơn thuần là member cùng tên. Khi runtime cung cấp một phiên bản class mà field bị xóa hoặc đổi descriptor từ `I` sang `J`, liên kết có thể thất bại với `NoSuchFieldError`. Đổi field từ instance sang static (hoặc ngược lại) còn có thể làm instruction hiện có không tương thích với loại field, gây `IncompatibleClassChangeError`.

### Field hiding không phải dynamic dispatch

Trong Java, **field access được liên kết theo kiểu tham chiếu tại compile time**, khác virtual method dispatch. Xét:

~~~java
class Parent {
    int number = 1;
}

class Child extends Parent {
    int number = 2;
}
~~~

Nếu có:

~~~java
Parent p = new Child();
System.out.println(p.number);          // 1
System.out.println(((Child) p).number); // 2
~~~

Đây là đoạn minh họa cần đặt trong phương thức để chạy. `p.number` đã được compile để truy cập field của `Parent`; ép kiểu sang `Child` cho phép mã nguồn trỏ tới field khác của `Child`. JVM **không tự tìm “field override” theo class runtime của object** khi thực thi `getfield`, bởi field có thể bị *hide* chứ không *override*. Các phương thức instance mới là nơi thường có virtual dispatch qua opcode invocation phù hợp.

### Quyền truy cập được kiểm tra ở runtime

Khả năng compile được trong một cấu hình không có nghĩa binary luôn liên kết được sau khi thay JAR, module hoặc class loader. Các trường hợp thường gặp:
- Field không còn tồn tại: `NoSuchFieldError`.
- Field tồn tại nhưng không được phép truy cập: `IllegalAccessError`.
- Static/instance mismatch: `IncompatibleClassChangeError`.
- Owner class không thể nạp/được định nghĩa theo yêu cầu: có thể gặp `NoClassDefFoundError` hoặc lỗi liên kết liên quan.

Những lỗi này thuộc họ **`LinkageError`**, không giống ngoại lệ kiểm tra null ở bước thực thi `getfield`/`putfield`.

## 8. Truy cập null: vì sao chỉ instance field cần đối tượng?

Nếu `objectref` là `null` khi thực thi **`getfield` hoặc `putfield`** sau các kiểm tra liên kết liên quan, JVM ném `NullPointerException`.

Ví dụ Java 17+ đầy đủ:

Tạo **`NullFieldDemo.java`**:

~~~java
public class NullFieldDemo {
    int value = 5;
    static int shared = 9;

    public static void main(String[] args) {
        NullFieldDemo item = null;

        try {
            System.out.println(item.value);
        } catch (NullPointerException expected) {
            System.out.println("instance=NPE");
        }

        System.out.println("static=" + NullFieldDemo.shared);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 NullFieldDemo.java
java NullFieldDemo
~~~

**Stdout chính xác:**

~~~text
instance=NPE
static=9
~~~

`item.value` đòi objectref và thất bại vì tham chiếu null. `NullFieldDemo.shared` sử dụng `getstatic`, không cần instance.

Java cho phép viết cú pháp static field qua biểu thức tham chiếu như `item.shared` (compiler có thể cảnh báo về phong cách), kể cả `item` đang null. Tuy nhiên, **biểu thức đứng trước dấu chấm vẫn có thể được đánh giá và gây side effect hoặc exception của chính nó**; vì vậy không nên viết static access qua biến object. Hãy dùng `TênLớp.field` để làm rõ ý nghĩa và tránh nhầm lẫn với `getfield`.

### Thứ tự lỗi và ngoại lệ

Trong trường hợp bytecode sai liên kết và objectref null đồng thời, đừng xây dựng logic dựa trên phỏng đoán “NPE nhất định được ném trước”. JVM phải tuân thủ thứ tự resolution/kiểm tra được đặc tả; lỗi liên kết có thể xảy ra trước bước kiểm tra objectref. Điều này đặc biệt quan trọng khi phân tích class file tự sinh hoặc binary lỗi tương thích.

## 9. `final`, hằng compile-time và các ngoại lệ ghi field

### Quy tắc `final` ở bytecode

Với định dạng class file Java hiện đại, verifier/linker hạn chế ghi field `final`:

- **`putfield` vào instance `final`**: field phải được khai báo trong **class hiện tại**, và instruction phải nằm trong **instance initialization method `<init>`** của chính class đó; nếu không, có thể xảy ra `IllegalAccessError` khi thực thi kiểm tra liên quan.
- **`putstatic` vào static `final`**: field phải được khai báo trong **class/interface hiện tại**, và instruction phải nằm trong **class/interface initialization method `<clinit>`**.
- `getfield`/`getstatic` có thể đọc field final từ vị trí được phép nếu resolution/access thành công.

Những quy tắc bytecode giải thích vì sao compiler Java chỉ cho phép gán `final` trong ngữ cảnh khởi tạo hợp lệ, nhưng **chúng không thay thế mọi quy tắc của JLS** về definite assignment, blank final và tính hợp lệ của constructor/source code.

### Không phải đọc `static final` luôn là `getstatic`

Một **constant variable** trong Java là field `final` kiểu primitive hoặc `String` được khởi tạo bằng *constant expression* phù hợp. Giá trị có thể được compiler **inline ngay tại nơi sử dụng**, nên code dùng field đó có thể **không chứa `getstatic`** cho field.

Ví dụ đầy đủ:

Tạo **`ConstantFieldDemo.java`**:

~~~java
class ConfigData {
    static final int LIMIT = 7; // Compile-time constant variable

    static int dynamic = start();

    private static int start() {
        System.out.println("ConfigData initialized");
        return 21;
    }
}

public class ConstantFieldDemo {
    public static void main(String[] args) {
        System.out.println("limit=" + ConfigData.LIMIT);
        System.out.println("before dynamic");
        System.out.println("dynamic=" + ConfigData.dynamic);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ConstantFieldDemo.java
java ConstantFieldDemo
~~~

**Stdout chính xác:**

~~~text
limit=7
before dynamic
ConfigData initialized
dynamic=21
~~~

Giải thích:

1. `ConfigData.LIMIT` là compile-time constant; compiler có thể đưa trực tiếp số 7 vào class caller. Bởi vậy phép đọc này không cần dùng `getstatic` và không kích hoạt khởi tạo `ConfigData` theo cách mà một `getstatic` thực sự làm.
2. `ConfigData.dynamic` không phải compile-time constant vì giá trị đến từ lời gọi `start()`. Khi bytecode thực hiện `getstatic` để đọc nó, JVM phải khởi tạo `ConfigData` trước.
3. Thân `<clinit>` chạy `start()` và in `ConfigData initialized`, rồi lưu giá trị 21 bằng `putstatic`.
4. Sau initialization, `getstatic` trả 21.

**Điểm quan trọng về binary compatibility:** Nếu một thư viện thay giá trị compile-time constant `static final int LIMIT` rồi người dùng **không biên dịch lại caller**, caller có thể tiếp tục sử dụng giá trị đã inline từ bản cũ. Đó là một lý do không nên dùng primitive/string compile-time constants để công bố những cấu hình cần thay đổi ở runtime giữa các bản phát hành.

### Final field không đồng nghĩa immutable object

`final Account account` ngăn gán lại tham chiếu field sau khi được khởi tạo hợp lệ, nhưng **không làm mọi field bên trong đối tượng Account trở thành bất biến**. Cũng không có bảo đảm thread-safety tự động cho mọi thao tác lên object được tham chiếu.

## 10. `volatile`, Java Memory Model và tính nguyên tử

Các field được đánh dấu `volatile` vẫn được truy cập qua **cùng các opcode**: `getfield`/`putfield` nếu instance, `getstatic`/`putstatic` nếu static. Không tồn tại bộ opcode “`getvolatile`” hoặc “`putvolatile`” riêng trong JVM chuẩn.

Ví dụ:

~~~java
class Flag {
    volatile boolean ready;
    static volatile int version;
}
~~~

Đây là class minh họa. Bytecode sử dụng `getfield`/`putfield` cho `ready` và `getstatic`/`putstatic` cho `version`; **field metadata** chứa flag `ACC_VOLATILE` để JVM thực thi theo quy tắc Java Memory Model (JMM).

- **Read volatile** có semantics về visibility và ordering; **write volatile** cũng có semantics tương ứng, bao gồm quan hệ *happens-before* của một write với những read sau đó của cùng field theo JMM.
- Các tác vụ đọc/ghi volatile đơn lẻ có bảo đảm atomic cho kiểu field theo JMM; ví dụ đọc/ghi `volatile long` và `volatile double` là atomic theo quy tắc Java.
- **`volatile int counter; counter++;` không atomic** như một phép read-modify-write. Nó gồm đọc, tính toán, ghi; hai thread vẫn có thể làm mất cập nhật.
- Nếu cần tăng atomic, dùng đồng bộ hóa, `AtomicInteger.incrementAndGet()`, hoặc công cụ concurrency phù hợp. Lời gọi API này không tạo opcode field access mới, dù JIT có thể sử dụng intrinsic/CPU instruction hiệu quả.

**Ngữ nghĩa JMM khác với lưu trữ vật lý.** Từ bytecode `getfield` một mình không thể kết luận field có volatile hay không; cần kiểm tra field declaration/flag trong class file. Với `javap -v -p`, phần khai báo field có thể hiển thị `ACC_VOLATILE`.

## 11. Compound assignment và expression result

Các phép gán như `obj.x += 3`, `obj.x++` hoặc `staticCount *= 2` **không có opcode “fieldAdd” riêng**. Compiler phối hợp:
1. Tính receiver/objectref nếu là instance field.
2. Đọc giá trị cũ bằng `getfield` hoặc `getstatic`.
3. Tính toán bằng opcode như `iadd`, `imul`; chuyển đổi nếu cần.
4. Ghi lại bằng `putfield` hoặc `putstatic`.
5. Nếu biểu thức gán có giá trị được sử dụng, có thể cần các opcode nhân bản stack như `dup`, `dup_x1`, `dup2_x1`, `dup2_x2` để giữ giá trị thích hợp.

Ví dụ:

~~~java
int result = (obj.count += 3);
~~~

Đây là snippet trong một phương thức với `obj` là instance phù hợp. `result` cần nhận **giá trị mới của biểu thức gán**; trong khi `putfield` tự nó không push gì. Compiler phải đảm bảo ngữ nghĩa biểu thức Java bằng cách tổ chức stack trước và sau lệnh ghi.

Tương tự, `obj.count++` (post-increment) biểu thức trả về **giá trị cũ**, còn `++obj.count` trả về **giá trị mới**. Chúng có thể dùng cùng `getfield`/`putfield` nhưng tổ chức stack khác nhau để giữ đúng kết quả.

## 12. Liên hệ class initialization với constructor

Hai loại initializer thường thấy khi đọc disassembly:

| Thành phần | Ký hiệu JVM | Chạy khi nào | Instruction field access thường gặp |
| --- | --- | --- | --- |
| Constructor | `<init>` | Khi tạo và khởi tạo một instance theo quy tắc Java | `putfield` cho instance field initializer/constructor assignment |
| Class/interface initializer | `<clinit>` | Khi class/interface cần initialization lần đầu theo quy tắc | `putstatic` cho static field initializer / static block |

Cần phân biệt:
- `new Counter()` đòi class được khởi tạo phù hợp, tạo object mới rồi chạy constructor; chính `<init>` là instance initializer trong thuật ngữ JVM.
- `<clinit>` là phương thức đặc biệt của class/interface được JVM gọi để initialization; người dùng không trực tiếp gọi nó bằng Java source như phương thức bình thường.
- `getstatic`/`putstatic` trên field đã resolve là một trigger initialization nếu class/interface khai báo field chưa được khởi tạo, nhưng `getfield`/`putfield` không có cơ chế trigger initialization tương tự **chỉ vì đọc/ghi instance field**. Thông thường object hợp lệ đã trải qua chuỗi khởi tạo thích hợp khi được tạo.

Đừng giải thích “`putfield` khởi tạo class khi ghi lần đầu”: đây là nhầm lẫn phổ biến giữa **constructor instance** và **class initialization**.

## 13. Các lỗi JVM liên quan đến bốn opcode

| Tình huống | Error/exception thường gặp | Cách hiểu đúng |
| --- | --- | --- |
| `getfield`/`putfield` với `objectref = null` | `NullPointerException` | Không có instance để đọc/ghi; thuộc bước chạy, sau kiểm tra liên kết liên quan. |
| Tham chiếu một field không còn tồn tại theo tên và descriptor | `NoSuchFieldError` | Class runtime không khớp binary mà caller kỳ vọng. |
| Cố dùng `getfield`/`putfield` cho field static hoặc `getstatic`/`putstatic` cho field instance | `IncompatibleClassChangeError` | Opcode không tương thích với loại field được resolve. |
| Bytecode truy cập field không còn được phép | `IllegalAccessError` | Quy tắc truy cập runtime hoặc quy định `final` bị vi phạm. |
| Owner class không thể được nạp | `NoClassDefFoundError` hoặc lỗi tải/liên kết thích hợp | Xem nguyên nhân và class loader, classpath/module path. |
| Static initialization ném exception | `ExceptionInInitializerError` hoặc lỗi liên quan | Xem stack trace và lỗi gốc của `<clinit>`. |
| Class file tự sinh có stack/type không hợp lệ | `VerifyError`/`ClassFormatError` | Bytecode không hợp lệ; cần xem verifier và class format. |

Khi sửa lỗi, hãy đọc **full exception chain**, class và descriptor mà runtime kỳ vọng. Ví dụ một bản thư viện đổi `static int total` thành `int total` trong khi caller không được biên dịch lại: bytecode cũ vẫn dùng `getstatic`, nên không thể “tự hiểu lại” thành `getfield` chỉ vì tên field trùng nhau.

### Không dùng reflection để đoán opcode trực tiếp

Khi viết `Field.get(target)` hoặc `Field.set(target, value)`, bytecode tại vị trí gọi là **lời gọi API reflection**. JVM/reflection implementation có thể dùng cơ chế nội bộ khác nhau, nhưng mã caller không tự nhiên xuất hiện một opcode `getfield` hướng trực tiếp vào field mục tiêu. Tương tự, các API như `VarHandle.get` và `VarHandle.set` diễn tả chế độ access linh hoạt; chúng không phải tên của instruction mới thay bốn opcode trên.

## 14. Checklist đọc `javap`

Khi tự disassemble một class bằng `javap -c -v -p`, kiểm tra theo thứ tự:

1. **Class và method hiện hành:** thuộc instance method, constructor `<init>`, static method hay `<clinit>`?
2. **Operand chỉ mục:** lệnh `getfield/putfield/getstatic/putstatic` chứa `#N` nào?
3. **Constant pool:** `#N` trỏ đến `CONSTANT_Fieldref` nào? Owner class, field name và descriptor là gì?
4. **Loại field:** field có flag `ACC_STATIC` hay không? Nếu `ACC_FINAL`, instruction ghi nằm ở vị trí hợp lệ?
5. **Stack:** instance read cần `objectref`; instance write cần `objectref` dưới `value`; static read/write không cần objectref.
6. **Instruction xung quanh:** load, constant, arithmetic, `dup`, `invoke*`, store cho thấy đây là một assignment, compound assignment hay access trong biểu thức.
7. **Class initialization:** với `getstatic/putstatic`, class/interface khai báo field có cần initialization vào thời điểm đó không?
8. **Đồng thời:** field có `ACC_VOLATILE`? Có read-modify-write cần atomicity lớn hơn từng access?
9. **Số index không ổn định:** không gán ý nghĩa cố định cho `#N` giữa các lần biên dịch; đọc chính file được kiểm tra.

### Một vài biểu thức nguồn thường gặp

| Biểu thức Java | Bytecode liên quan thường thấy | Ghi chú |
| --- | --- | --- |
| `obj.x` | `aload` + `getfield` | Receiver lấy từ biểu thức. |
| `obj.x = 42` | `aload` + nạp 42 + `putfield` | Thứ tự stack receiver, rồi value. |
| `Holder.x` nếu `x` static thường | `getstatic` | Có thể trigger class initialization. |
| `Holder.x = 42` nếu `x` static thường | nạp 42 + `putstatic` | Có thể trigger class initialization. |
| `obj.x++` | `getfield`, arithmetic, `putfield`, stack duplication nếu cần | Không bảo đảm atomic. |
| `staticCounter += 2` | `getstatic`, arithmetic, `putstatic` | Không bảo đảm atomic. |
| `Holder.CONSTANT` nếu compile-time constant | Lệnh nạp hằng (không nhất thiết `getstatic`) | Có thể inline. |
| `array.length` | `arraylength` | Không phải instance field opcode. |
| `obj.getX()` | `invokevirtual` / instruction invoke thích hợp | Method call, không phải trực tiếp getfield tại caller. |

## 15. Tự kiểm tra và đáp án

**Câu 1.** Điểm khác nhau cơ bản giữa `getfield` và `getstatic` là gì?

**Đáp án:** `getfield` đọc giá trị từ **một instance** và cần objectref trên stack; `getstatic` đọc field **của class/interface được resolve** và không cần objectref. `getstatic` có thể trigger initialization của class/interface khai báo field.

**Câu 2.** Trước `putfield`, operand stack cần chứa gì và theo thứ tự nào?

**Đáp án:** `..., objectref, value` từ đáy đến đỉnh. Giá trị mới ở trên, objectref ở dưới. Lệnh pop cả hai.

**Câu 3.** Có opcode `iincfield` để tăng `obj.count++` không?

**Đáp án:** Không. Compiler thường ghép `getfield`, instruction tính toán và `putfield`; `iinc` dành cho biến local int, không phải field.

**Câu 4.** `getstatic` có phải luôn xuất hiện khi đọc `static final int LIMIT = 7` không?

**Đáp án:** Không. Nếu là compile-time constant variable và caller được biên dịch với giá trị đó, compiler có thể inline 7 và không tạo `getstatic` cho field tại call site.

**Câu 5.** Instance field `int number` của Parent và Child cùng tên là override hay hiding?

**Đáp án:** **Hiding**. Field được chọn theo quy tắc liên kết tại compile time và symbolic reference, không virtual dispatch như instance method.

**Câu 6.** `getfield` với objectref null gây gì? `getstatic` có cần objectref không?

**Đáp án:** Sau khi kiểm tra liên kết phù hợp, `getfield` trên null ném `NullPointerException`. `getstatic` không có objectref operand.

**Câu 7.** Nếu caller đã biên dịch truy cập `static int total` nhưng runtime đổi thành `int total`, sẽ thế nào?

**Đáp án:** Bytecode cũ dùng `getstatic/putstatic` trên field nay là instance; khi resolution và thực thi theo kiểm tra JVM, có thể gặp `IncompatibleClassChangeError`. Cần giải quyết incompatibility nhị phân và biên dịch/triển khai nhất quán.

**Câu 8.** Một field `volatile int counter` được tăng bằng `counter++` có atomic không?

**Đáp án:** Không. Read volatile và write volatile có quy tắc visibility/ordering, nhưng chuỗi read-modify-write không tự thành atomic. Có thể dùng `AtomicInteger` hoặc synchronization.

**Câu 9.** `putstatic` ghi một `static final` vào lúc tùy ý sau initialization có hợp lệ không?

**Đáp án:** Không. Bytecode hợp lệ phải tuân thủ quy tắc của JVMS: field `final` thuộc class/interface hiện tại và instruction `putstatic` phải nằm trong initializer `<clinit>` của class/interface ấy.

**Câu 10.** Vì sao chỉ mục `#18` sau `getfield` không phải “offset 18 byte” trong object?

**Đáp án:** Vì operand đó là chỉ mục của `CONSTANT_Fieldref` trong run-time constant pool. JVM resolve symbol sang field phù hợp; layout vật lý là chi tiết runtime implementation.

## 16. Bản đồ ghi nhớ

~~~text
                         TRUY CẬP FIELD
                              |
                   +----------+----------+
                   |                     |
                INSTANCE                STATIC
             cần objectref          không cần objectref
                   |                     |
           +-------+-------+     +-------+-------+
           |               |     |               |
         READ            WRITE  READ            WRITE
       getfield         putfield getstatic       putstatic

Stack:
  getfield : ..., ref        -> ..., value
  putfield : ..., ref, value -> ...
  getstatic: ...             -> ..., value
  putstatic: ..., value      -> ...

Mỗi lệnh -> #N CONSTANT_Fieldref -> Class + NameAndType
            -> owner class, field name, field descriptor
            -> resolution + access/field-kind checks

Static access (getstatic/putstatic)
            -> có thể kích hoạt class/interface initialization
Instance access (getfield/putfield)
            -> cần objectref không null

final       -> hạn chế ghi ở <init>/<clinit> theo loại field
volatile    -> thêm memory-order/visibility; không biến ++ thành atomic
~~~

**Điểm cốt lõi:** Bốn opcode đều truy cập field qua **symbolic reference** từ constant pool, nhưng khác nhau ở **instance/static**, **đọc/ghi**, **hình dạng operand stack** và **điều kiện runtime**. Đọc disassembly đúng cần ghép opcode với descriptor, flags, class initialization và quy tắc Java Memory Model.

## Tài liệu tham khảo

- [JVMS Java SE 21 — 6.5 Instructions: getfield, putfield, getstatic, putstatic](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5).
- [JVMS Java SE 21 — 4.4.2 Fieldref, Methodref và InterfaceMethodref](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4.2).
- [JVMS Java SE 21 — 5.4.3.2 Field Resolution](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3.2).
- [JVMS Java SE 21 — 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5).
- [JLS Java SE 21 — 12.4 Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4).
- [JLS Java SE 21 — 17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4).
- [JDK 21 — javap tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html).
