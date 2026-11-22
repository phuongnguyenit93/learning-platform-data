# Constant pool và tham chiếu ký hiệu tới kiểu, field, method trong Java

Một file `.class` không lưu trực tiếp con trỏ tới mọi lớp, trường (field) và phương thức (method) mà chương trình sử dụng. Thay vào đó, nó chứa **constant pool** — bảng các hằng và bản ghi mô tả tham chiếu bằng **tên + kiểu/chữ ký**. Trong quá trình liên kết (linking) và thực thi, JVM dùng các mô tả này để tìm thực thể tương ứng. Đây là cầu nối giữa bytecode, cơ chế nạp lớp và hành vi gọi phương thức ở runtime.

Bài này thuộc chủ đề **Tên và bytecode** trong Java core – classloader. Mục tiêu là đọc được một tham chiếu trong constant pool, biết vì sao cùng tên lớp chưa chắc là cùng kiểu, phân biệt *resolution* với *dispatch* và chẩn đoán lỗi liên kết sau khi thay đổi thư viện.

## 1. Constant pool nằm ở đâu, chứa gì?

Trong cấu trúc `ClassFile`, phần đầu gồm `magic`, phiên bản class file, rồi đến `constant_pool_count` và mảng `constant_pool`. Mỗi phần tử có một `tag` cho biết loại thông tin. Chỉ số trong constant pool thường bắt đầu từ **#1**; `#0` không phải một phần tử thông thường và chỉ được dùng như giá trị đặc biệt tại một số vị trí do định dạng class file quy định.

- **Compile time:** `javac` ghi vào constant pool các chuỗi, giá trị số và mô tả biểu tượng của lớp/field/method mà bytecode cần. Không nhất thiết mỗi biểu thức nguồn sinh ra một mục riêng; compiler có thể tái sử dụng mục.
- **Load time:** JVM đọc định dạng class file và tạo biểu diễn runtime, gồm *run-time constant pool* của từng class hoặc interface.
- **Link time / runtime:** tham chiếu ký hiệu có thể được giải quyết thành thực thể tương ứng. JVM được phép resolve sớm hoặc trì hoãn đến lúc cần, miễn hành vi lỗi tuân thủ quy định JVM.
- **Không đồng nghĩa:** constant pool trong `.class`, *run-time constant pool* và *String intern pool* là những khái niệm khác nhau. Ví dụ `"hello"` có thể dẫn tới một `CONSTANT_String` trong class file, còn đối tượng `String` được JVM quản lý theo cơ chế riêng.

`constant_pool_count` là số lượng mục cộng một. `CONSTANT_Long` và `CONSTANT_Double` chiếm hai vị trí chỉ số trong bảng theo định dạng class file (vị trí thứ hai không được tham chiếu như mục độc lập), một chi tiết dễ gây nhầm khi tự phân tích byte.

### Các loại mục liên quan trực tiếp

| Tag | Mục đích | Ví dụ ý nghĩa |
| --- | --- | --- |
| `CONSTANT_Utf8` | Lưu văn bản mã hóa theo *modified UTF-8* của JVM | `java/lang/String`, `length`, `()I` |
| `CONSTANT_Class` | Biểu diễn tên nội bộ của class/interface hoặc descriptor kiểu mảng | `java/lang/String` |
| `CONSTANT_NameAndType` | Cặp tên thành viên và descriptor | `count:I`, `run:()V` |
| `CONSTANT_Fieldref` | Lớp chủ khai báo trong tham chiếu + `NameAndType` của field | `pkg/Box.value:I` |
| `CONSTANT_Methodref` | Lớp + `NameAndType` của method theo quy tắc class-method | `pkg/Box.get:()I` |
| `CONSTANT_InterfaceMethodref` | Interface + `NameAndType` cho tham chiếu method của interface | `java/util/List.size:()I` |
| `CONSTANT_String` | Tham chiếu tới nội dung chuỗi ký tự | `"hello"` |
| `CONSTANT_Integer/Float/Long/Double` | Hằng số nguyên/thực ở dạng phù hợp | `42`, `3.14f` |
| `CONSTANT_MethodHandle`, `CONSTANT_MethodType` | Mô tả method handle và kiểu phương thức | Dùng với `invokedynamic`/bootstrap |
| `CONSTANT_Dynamic`, `CONSTANT_InvokeDynamic` | Hằng và điểm gọi được bootstrap liên kết động | `condy`, lambda, chuỗi nối |
| `CONSTANT_Module`, `CONSTANT_Package` | Tên module/package phục vụ cấu trúc module | `module-info.class` |

Không phải mọi hằng ở ngôn ngữ Java đều bắt buộc có mục riêng trong constant pool. Chẳng hạn, compiler có thể phát lệnh `iconst_1` hoặc `bipush` thay vì tạo `CONSTANT_Integer` cho một số nguyên nhỏ.

## 2. Tham chiếu ký hiệu được ghép như thế nào?

Một `Fieldref` hoặc `Methodref` không chứa địa chỉ bộ nhớ. Nó tham chiếu gián tiếp qua nhiều mục trong bảng:

```text
CONSTANT_Fieldref / CONSTANT_Methodref / CONSTANT_InterfaceMethodref
    ├── class_index ──────> CONSTANT_Class
    │                          └── name_index ──> CONSTANT_Utf8: tên kiểu
    └── name_and_type_index -> CONSTANT_NameAndType
                                   ├── name_index ──────> CONSTANT_Utf8: tên thành viên
                                   └── descriptor_index -> CONSTANT_Utf8: descriptor
```

Ví dụ bytecode cần truy cập `pkg/Counter.total:I`:

- `pkg/Counter` là **internal name** của lớp, dùng dấu `/` thay dấu `.` trong tên nhị phân quen thuộc `pkg.Counter`.
- `total` là tên field.
- `I` là **field descriptor** chỉ kiểu `int`.

Một lời gọi `pkg/Counter.increment:(I)V` nói rằng phương thức tên `increment` nhận một `int` và trả `void`. Descriptor là một phần của tham chiếu ký hiệu, không chỉ là chú thích.

### Đọc descriptor đủ để lần theo tham chiếu

Descriptor là phần chữ ký kiểu đi cùng tên thành viên trong constant pool. Một số mẫu cần nhận ra ngay khi xem `javap`:

| Mẫu | Ý nghĩa |
| --- | --- |
| `I`, `J`, `Z` | `int`, `long`, `boolean` |
| `Ljava/lang/String;` | Tham chiếu `java.lang.String` |
| `[I`, `[[Ljava/lang/String;` | `int[]`, `String[][]` |
| `(I)V` | Method nhận `int`, trả `void` |
| `(Ljava/lang/String;)I` | Method nhận `String`, trả `int` |

**Field descriptor** mô tả một kiểu; **method descriptor** ghép các kiểu tham số giữa `(` và `)`, rồi thêm kiểu trả về. `V` chỉ hợp lệ làm kiểu trả về `void`. Descriptor không chứa tên biến, tên tham số hay generic type argument: `List<String>` sau erasure thường có field descriptor `Ljava/util/List;`. Bài chuyên về descriptor của chương này giải thích đầy đủ các mã primitive, mảng nhiều chiều và quy tắc parse.

Constructor có tên bytecode `<init>`, còn bộ khởi tạo tĩnh có tên `<clinit>`. Cả hai có ngữ nghĩa riêng, nên không áp dụng máy móc cách gọi method thông thường.

## 3. Từ tham chiếu trong bytecode đến lớp, field, method thật

Khi bytecode gặp một lệnh cần class/field/method, JVM dùng mục constant pool được lệnh tham chiếu. Quy trình tư duy hữu ích:

1. **Đọc mục constant pool:** xác định tên kiểu, tên thành viên và descriptor.
2. **Resolve kiểu chủ:** tìm hoặc nạp class/interface được tham chiếu trong ngữ cảnh class loader thích hợp; kiểm tra định dạng, tính hợp lệ và khả năng truy cập theo quy tắc JVM.
3. **Resolve field hoặc method:** tìm thành viên phù hợp theo quy tắc tra cứu trong kiểu, superclass/superinterface thích hợp; kiểm tra kiểu thành viên, tính truy cập và các ràng buộc tương thích.
4. **Thực hiện lệnh:** đọc/ghi field, tạo object, kiểm tra kiểu, hoặc chọn method body để gọi. Với lời gọi ảo, bước chọn implementation khi chạy là phần riêng.

Cần phân biệt các mốc vòng đời của lớp:

- **Loading:** tạo class/interface từ định dạng nhị phân với một defining loader.
- **Linking:** gồm **verification** (kiểm chứng), **preparation** (chuẩn bị vùng lưu trữ static và giá trị mặc định) và **resolution** (giải quyết các symbolic reference).
- **Initialization:** thực hiện khởi tạo class/interface theo điều kiện JVM, bao gồm các static initializer tương ứng. *Resolution không đồng nghĩa initialization.* Một `.class` literal thường không chủ động khởi tạo class được nhắc đến.

Thông thường JVM thực hiện các bước cần thiết theo yêu cầu của lệnh và ngữ cảnh. Không nên dạy rằng toàn bộ constant pool được resolve đúng một lần ngay khi load, cũng không nên khẳng định chỉ có lazy resolution: đặc tả cho phép chiến lược sớm hoặc muộn trong giới hạn hành vi quan sát được.

### Tại sao tên lớp còn phụ thuộc class loader?

Trong JVM, danh tính của một class/interface được xác định bởi **tên nhị phân + defining class loader**. Hai loader độc lập có thể định nghĩa hai class đều mang tên `com.example.Plugin` nhưng chúng là **hai kiểu khác nhau**. Một `CONSTANT_Class` chỉ lưu tên biểu tượng; việc resolve đặt tên ấy vào ngữ cảnh loading cụ thể.

Điều này quan trọng trong plugin, application server, hot deployment và framework dùng loader tùy biến. Trình tự thường là loader của lớp đang tham chiếu yêu cầu load tên phụ thuộc; quá trình ủy quyền (delegation) có thể đưa tới loader cha hoặc tự định nghĩa, tùy chính sách loader. JVM còn áp dụng **loading constraints** khi cần để bảo đảm các kiểu xuất hiện trong descriptor tương thích giữa các loader. Vì vậy không thể suy từ chuỗi tên bằng nhau rằng hai tham chiếu nhất định chỉ tới cùng một `Class`.

Một lỗi `ClassCastException` giữa hai tên class trông giống hệt nhau có thể do khác defining loader; đó là vấn đề danh tính kiểu ở runtime, không phải do `CONSTANT_Utf8` hỏng.

## 4. Đọc bằng `javap`: ví dụ Java 17+ chạy được

Tạo **một file duy nhất** tên `Main.java`:

```java
public class Main {
    static class Parent {
        public String label = "parent";

        public String describe() {
            return "Parent.describe";
        }
    }

    static class Child extends Parent {
        public String label = "child";

        @Override
        public String describe() {
            return "Child.describe";
        }
    }

    static String prefix = "cp";

    public static void main(String[] args) {
        Parent obj = new Child();
        System.out.println(obj.label);
        System.out.println(obj.describe());
        System.out.println(prefix);
        System.out.println(String.class.getName());
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac --release 17 Main.java
java Main
javap -v -p Main
javap -c -p Main
```

Stdout của lệnh `java Main` chính xác là:

```text
parent
Child.describe
cp
java.lang.String
```

Điểm cần đọc trong output `javap`:

- Mục dạng `Class ... Main$Parent` và `Class ... Main$Child` mô tả các kiểu được tạo/tham chiếu.
- Mục dạng `Fieldref ... Main$Parent.label:Ljava/lang/String;` gắn lệnh `getfield` với **field của `Parent`**. Dù object thực tế là `Child`, field Java không override như method. Do biến `obj` có kiểu compile time `Parent`, kết quả là `parent`.
- Mục dạng `Methodref ... Main$Parent.describe:()Ljava/lang/String;` gắn lệnh `invokevirtual` với method được tham chiếu từ `Parent`. Khi thực thi, dispatch động chọn override trong `Child` nên kết quả là `Child.describe`.
- Mục dạng `Fieldref ... Main.prefix:Ljava/lang/String;` phục vụ `getstatic`, trả giá trị đã khởi tạo `cp`.
- `String.class` tạo tham chiếu kiểu `java/lang/String`. `String.class.getName()` trả tên nhị phân có dấu chấm: `java.lang.String`.
- Những lời gọi `println` thường có các `Methodref` tới overload `java/io/PrintStream.println:(Ljava/lang/String;)V`.

Ví dụ các dòng **minh họa dạng** bytecode (bỏ chỉ số `#n` vì chỉ số có thể thay đổi theo compiler):

```text
getfield       #...  // Field Main$Parent.label:Ljava/lang/String;
invokevirtual  #...  // Method Main$Parent.describe:()Ljava/lang/String;
getstatic      #...  // Field Main.prefix:Ljava/lang/String;
```

Các dòng trên là **trích dạng lệnh để nhận diện**, không phải bản chép đầy đủ `javap -c` của chương trình. Quan sát output thật để đối chiếu số thứ tự, offset, những lệnh trung gian và vị trí xuất hiện. Nếu cần đọc constant pool của class lồng nhau, có thể chạy `javap -v -p 'Main$Parent'` trong shell hỗ trợ dấu nháy đơn; trên Windows Command Prompt dùng `javap -v -p "Main$Parent"`.

### Cách xem một mục `#n` cho đúng

Trong `javap -v`, phần `Constant pool:` ghi các mục dạng:

```text
#n = Methodref          #a.#b     // pkg/Service.work:(I)V
#a = Class              #c        // pkg/Service
#b = NameAndType        #d:#e     // work:(I)V
#c = Utf8                         pkg/Service
#d = Utf8                         work
#e = Utf8                         (I)V
```

`#n`, `#a`, ... ở đây là **ký hiệu giả định**, không phải chỉ số cụ thể mà `javap` bắt buộc in ra. Hãy lần theo chỉ số thực từ `Methodref` đến `Class` và `NameAndType`, rồi tới các `Utf8`. Sau đó tìm lệnh `invoke*` nào dùng `#n` để hiểu tác dụng runtime.

## 5. Lệnh JVM nào thường dùng các tham chiếu này?

| Lệnh bytecode | Tham chiếu hoặc ý nghĩa |
| --- | --- |
| `new`, `anewarray`, `checkcast`, `instanceof` | Dùng tham chiếu class/interface hoặc kiểu mảng thích hợp |
| `multianewarray` | Dùng tham chiếu đến kiểu mảng |
| `getstatic` / `putstatic` | Đọc/ghi static field qua `Fieldref` |
| `getfield` / `putfield` | Đọc/ghi instance field qua `Fieldref` |
| `invokestatic` | Gọi static method thích hợp |
| `invokespecial` | Constructor, private method và các lời gọi đặc biệt, gồm `super` |
| `invokevirtual` | Gọi instance method theo class-method reference và dispatch ảo |
| `invokeinterface` | Gọi method qua interface reference với cơ chế chọn implementation |
| `invokedynamic` | Dùng `InvokeDynamic` và bootstrap method để liên kết call site |
| `ldc` / `ldc_w` / `ldc2_w` | Nạp các hằng thích hợp; `ldc` cũng có thể dùng class literal, method handle/type và dynamic constant, tùy loại/kiểu |

Điều then chốt: **resolve symbolic reference không giống chọn method body**. Ví dụ `invokevirtual Parent.describe` cần một method reference hợp lệ tại bước resolution; sau đó receiver `new Child()` quyết định implementation `Child.describe` khi lời gọi chạy. Với `getfield`, không có dispatch override field tương tự; field hiding tạo các field riêng biệt.

`Methodref` hay `InterfaceMethodref` nào hợp lệ còn phụ thuộc opcode và quy tắc JVM. Không nên gán máy móc “`Methodref` = `invokevirtual`” bởi `Methodref` cũng được dùng trong một số lời gọi `invokestatic` và `invokespecial`. Đồng thời, `invokedynamic` có cơ chế bootstrap riêng, không thể giải thích đơn thuần bằng tìm method trực tiếp theo tên.

### Một câu hỏi thường gặp: `final static` có luôn tạo `Fieldref` không?

Không. Với **constant variable** của Java, ví dụ `static final int LIMIT = 10`, compiler của class sử dụng có thể *inline* giá trị vào bytecode, nên thao tác đọc tại call site không nhất thiết dùng `getstatic` hoặc `Fieldref` tới field ấy. Đây là lý do khi đổi hằng compile time trong một thư viện mà không biên dịch lại client, client có thể vẫn thấy giá trị cũ. Với static field không phải constant variable, bytecode thường thực hiện `getstatic`.

## 6. Resolution, lỗi liên kết và thay đổi binary compatibility

Tham chiếu ký hiệu được tạo khi compile dựa vào API lúc đó. Nếu ở runtime nạp phiên bản thư viện khác, bytecode của client có thể vẫn chứa tên/descriptor cũ. Những tình huống tiêu biểu:

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| `NoClassDefFoundError` | JVM không thể tìm/định nghĩa class cần dùng hoặc lỗi khi initialization trước đó; thông báo và nguyên nhân gốc rất quan trọng |
| `ClassNotFoundException` | API nạp lớp chủ động (ví dụ `Class.forName` / `ClassLoader.loadClass`) báo không tìm thấy; đây là **checked exception**, khác với linkage error mà bytecode có thể gây ra |
| `NoSuchFieldError` | Field mà bytecode tham chiếu theo **tên + descriptor** không còn được tìm thấy theo quy tắc resolution |
| `NoSuchMethodError` | Method với tên/descriptor mong đợi không còn phù hợp/tìm thấy khi liên kết |
| `IllegalAccessError` | Truy cập từng hợp lệ khi biên dịch nhưng không còn hợp lệ tại runtime (ví dụ thay đổi visibility/module access) |
| `IncompatibleClassChangeError` | Loại/thực thể bytecode kỳ vọng khác cấu trúc runtime, ví dụ thay đổi static ↔ instance hoặc class ↔ interface; một số lỗi trên là subclass của lỗi này |
| `VerifyError` | Bytecode không hợp lệ theo các quy tắc kiểm chứng, không nhất thiết là thiếu class/field/method |
| `ClassCastException` | Cast tại runtime thất bại; khi có nhiều loader, cần kiểm tra danh tính lớp |

Chẳng hạn client đã biên dịch lời gọi `Api.answer:()I`. Nếu thư viện mới đổi phương thức thành `long answer()`, descriptor thành `()J`. Ngay cả khi tên phương thức vẫn là `answer`, bytecode client có thể phát sinh `NoSuchMethodError` khi lời gọi cũ được liên kết. Rebuild client và kiểm tra tương thích API là hướng sửa đúng hơn việc giả định JVM tự chuyển chữ ký cũ sang mới.

Tương tự, xóa/chuyển tên field hoặc thay đổi kiểu field thường làm tham chiếu `Fieldref` cũ mất hiệu lực. Chuyển một method từ instance thành static (hoặc ngược lại) có thể gây lỗi dạng `IncompatibleClassChangeError` vì opcode gọi không còn phù hợp.

**Đừng quy mọi lỗi vào thời điểm “load class”.** Một class có thể đã load thành công nhưng việc dùng một tham chiếu cụ thể mới làm lộ lỗi resolution/linking. Thời điểm biểu hiện có thể khác nhau tùy cách JVM chuẩn bị các tham chiếu.

### Quy trình chẩn đoán thực tế

1. Xác định **class client** phát lệnh lỗi từ stack trace; tìm đúng artifact `.class` thực tế đã chạy.
2. Xem `javap -v -p <TenClass>` và `javap -c -p <TenClass>` để tìm **opcode**, `#index`, tên owner, tên thành viên và descriptor.
3. So sánh chính xác **runtime artifact** với phiên bản biên dịch: classpath/module path, dependency conflict, shaded JAR, deployment cũ, bản sao class trong nhiều JAR.
4. Nếu lỗi liên quan class loader, xem **defining loader** của các kiểu liên quan, đường nạp class và boundary giữa các plugin/module.
5. Kiểm tra thay đổi API: field/method có tồn tại đúng chữ ký không, là static/instance đúng lệnh không, access có hợp lệ không.
6. Sửa lại tập dependency hoặc phục hồi binary compatibility; rebuild các client phụ thuộc khi chữ ký nguồn đã thay đổi. Chạy lại và xác minh cả đường code trước đây gây lỗi.

Để kiểm tra class loader khi có đối tượng thực tế:

```java
Object value = new Main.Child();
System.out.println(value.getClass().getName());
System.out.println(value.getClass().getClassLoader());
```

Đây là **đoạn minh họa chèn vào môi trường đã có `Main`**, không phải một chương trình độc lập. Output dòng thứ hai tùy JVM và class loader. Đừng dựa vào cách `toString()` của loader để khẳng định danh tính; khi phân tích sâu có thể so sánh trực tiếp các instance `ClassLoader` và `Class`.

## 7. Hiểu đúng ranh giới giữa source, class file và runtime

| Ở mã nguồn Java | Ở class file / bytecode | Ở JVM runtime |
| --- | --- | --- |
| `Box b` hoặc `new Box()` | Internal name kiểu, `CONSTANT_Class`, có thể là `new` | Resolve tên kiểu trong ngữ cảnh loader, tạo object khi `new` thực thi |
| `b.value` | `Fieldref` với owner/name/descriptor; `getfield` hoặc `putfield` | Resolve đúng field đã mô tả; field hiding không dispatch ảo |
| `b.run()` | `Methodref` hoặc `InterfaceMethodref`; opcode `invoke*` | Resolve method và, nếu áp dụng, chọn implementation theo receiver |
| `List<String>` | Descriptor thường là `Ljava/util/List;`, metadata generic ở `Signature` | JVM kiểm tra phần lớn thao tác theo kiểu đã erasure; cast do compiler chèn vẫn có thể xảy ra |
| `String.class` | Class reference, thường nạp bằng `ldc` | Trả `Class<?>` mà bản thân thao tác này không bắt buộc initialize `String` |
| Lambda / một số cách nối chuỗi | Có thể có `InvokeDynamic` và `BootstrapMethods` | Bootstrap tạo/liên kết call site; chiến lược compiler/JDK quyết định cấu trúc cụ thể |

Không nhầm lẫn **descriptor** và **generic signature**, **symbolic reference** và **địa chỉ runtime**, **method resolution** và **virtual dispatch**, hay **class loading** và **class initialization**.

## 8. Tự kiểm tra

**Câu 1.** Vì sao `obj.label` trong ví dụ in `parent` nhưng `obj.describe()` in `Child.describe`?

**Đáp án:** `obj` có kiểu compile time `Parent`, nên field access tham chiếu `Parent.label`. Field hiding không có cơ chế override. `describe()` dùng lời gọi ảo, runtime receiver là `Child` và có override, vì vậy chọn `Child.describe`.

**Câu 2.** `CONSTANT_Methodref` tới `Service.run:()V` đã có trong class file thì có bảo đảm method tồn tại, gọi được ngay không?

**Đáp án:** Không. Constant pool lưu mô tả biểu tượng do compiler ghi. Khi resolution, JVM còn phải tìm được class/method đúng descriptor và kiểm tra điều kiện liên kết/truy cập. Sau đó opcode và đối tượng nhận lời gọi (nếu có) quyết định hành vi runtime.

**Câu 3.** Hai plugin cùng chứa `com.acme.Task` có thể cast object qua lại không?

**Đáp án:** Chỉ dựa vào tên là chưa đủ. Nếu hai class được **định nghĩa** bởi hai defining loader khác nhau thì chúng là hai kiểu khác nhau; cast có thể thất bại. Nếu cả hai bên thực sự dùng cùng một định nghĩa class qua delegation hoặc API chung, tình huống khác.

**Câu 4.** Sau khi đổi `int find()` thành `long find()` trong thư viện, vì sao client cũ có thể vỡ dù tên vẫn là `find`?

**Đáp án:** Descriptor đã đổi từ `()I` thành `()J`. Binary reference của client còn giữ chữ ký cũ, nên method resolution có thể không tìm thấy method tương ứng và ném `NoSuchMethodError`.

**Câu 5.** `new Counter()` và `Counter.class` có đồng nghĩa về thời điểm initialization không?

**Đáp án:** Không. Việc tạo instance bằng `new` là một tác nhân dẫn đến initialization thích hợp trước khi tạo object; chỉ lấy class literal `Counter.class` không tự nó buộc chạy static initializer của `Counter`.

## Ghi nhớ để đọc bytecode hiệu quả

Mỗi lần thấy `getfield`, `invokevirtual`, `invokestatic` hay `new`, hãy đi từ **opcode → chỉ số constant pool → loại entry → owner/name/descriptor → quy tắc resolution → hành vi runtime**. Trong môi trường có nhiều class loader, bổ sung câu hỏi **kiểu đó được định nghĩa bởi loader nào?**. Chuỗi truy vết này giải thích được phần lớn lỗi tên lớp, liên kết và gọi method mà chỉ đọc mã nguồn không thấy.

Tài liệu chuẩn để tra cứu sâu hơn: *Java Virtual Machine Specification*, mục **Class File Format / Constant Pool**, **Loading, Linking, and Initializing**, và **Method Invocation and Return Instructions**; đối chiếu phiên bản JVM đang dùng khi cần chi tiết opcode hoặc điều kiện lỗi.