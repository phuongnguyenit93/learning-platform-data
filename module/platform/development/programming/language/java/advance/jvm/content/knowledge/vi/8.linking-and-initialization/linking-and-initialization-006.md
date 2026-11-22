# Phân giải sớm, phân giải muộn và thời điểm lỗi liên kết xuất hiện

## 1. Mục tiêu: JVM được phép giải quyết tham chiếu lúc nào?

Khi Java source gọi `lib.Library.version()`, class file của chương trình gọi thường không chứa một địa chỉ native cố định trỏ thẳng tới code của phương thức đó. Thay vào đó, các bytecode như `invokestatic`, `getfield`, `new`, `checkcast`… có thể sử dụng **symbolic references** trong run-time constant pool. JVM phải **resolve** những tham chiếu này thành class, field, method hoặc giá trị runtime phù hợp trước khi thực hiện thao tác cần đến chúng.

**Câu hỏi chính của bài** không phải “JVM có phân giải tham chiếu không?” mà là:

- JVM có thể **phân giải sớm (eager resolution)** trong lúc liên kết, trước khi chương trình thực sự gọi một method?
- JVM có thể **phân giải muộn (lazy resolution)** ngay khi bytecode liên quan được sử dụng?
- Nếu một tham chiếu không hợp lệ, ví dụ method bị xóa khỏi thư viện sau khi client đã biên dịch, **lỗi được phép xuất hiện ở thời điểm nào**?
- Vì sao thấy ứng dụng đã in ra một số dòng hoặc `main` chạy được **không chứng minh** mọi symbolic reference của ứng dụng đã được resolve thành công?

Theo **JVMS `5.4** và **`5.4.3**, JVM được quyền chọn một số thời điểm thực hiện resolution, nhưng **không được tùy ý ném lỗi liên kết tại điểm hoàn toàn không liên quan với hành động của chương trình có thể cần liên kết**. Có những quy tắc chặt hơn cho **dynamically-computed constants** và **dynamically-computed call sites**, sẽ bàn riêng.

### Một bản đồ tổng quan

~~~text
Java source
   |
   | javac
   v
ClassFile
   |    constant pool: Methodref, Fieldref, Class, NameAndType, ...
   |    Code: invokestatic #N, getstatic #M, new #K ...
   v
JVM class loading
   v
Linking
   +-- Verification (kiểm tra hợp lệ)
   +-- Preparation (chuẩn bị static storage/default values)
   +-- Resolution (phân giải symbolic refs) <-- linh hoạt về thời điểm*
   v
Initialization (static field initializers / <clinit> khi cần)
   v
Execution of methods / instructions
      \-- có thể tiếp tục resolve những refs chưa sử dụng*

* Có giới hạn và trường hợp đặc biệt theo JVMS.
* Lỗi phát hiện trong linkage phải được ném ở điểm chương trình có hành động
  có thể trực tiếp hoặc gián tiếp yêu cầu linkage tương ứng.
~~~

Đừng đọc sơ đồ như một thứ tự cứng “phải resolve toàn bộ trước initialize”. **Load xong, verify và prepare xong trước initialization**, nhưng một số symbolic references có thể chỉ được resolve **sau khi class đã initialized và khi method liên quan chạy**.

## 2. Phân biệt loading, linking, resolution và initialization

| Khái niệm | Điều VM làm | Không đồng nghĩa |
| --- | --- | --- |
| **Loading** | Tìm/tạo runtime class hoặc interface từ định nghĩa nhị phân và loader | Chạy `static {}` |
| **Verification** | Kiểm tra binary structure, bytecode constraints và type-safety rules | Thực thi từng nhánh Java code |
| **Preparation** | Tạo storage và giá trị mặc định cho static fields; xử lý quy tắc constant phù hợp | Thực thi mọi biểu thức `static int x = f()` |
| **Resolution** | Chuyển **symbolic reference** thành đối tượng/giá trị runtime cụ thể, kiểm tra liên quan | Gọi thân method được resolve |
| **Initialization** | Thực thi initialization logic của class/interface khi được yêu cầu | Resolve tất cả constant-pool entries |
| **Execution** | Thực thi bytecode, tạo object, gọi method, đọc field… | Chỉ đơn thuần đọc `.class` |

Ở cấp class file, các tham chiếu có thể trông như:

~~~text
#11 = Class        #12                // lib/Library
#12 = Utf8         lib/Library
#13 = NameAndType  #14:#15            // version:()Ljava/lang/String;
#16 = Methodref    #11.#13            // lib/Library.version:()Ljava/lang/String;

Code:
   ... invokestatic #16              // Method lib/Library.version:()Ljava/lang/String;
~~~

Đây là **sơ đồ minh họa constant pool**: các chỉ số `#11`, `#16` có thể khác ở class thực do compiler tạo. **Methodref** chứa owner, method name và descriptor, **không phải địa chỉ máy đã cố định lúc biên dịch source**. Resolution cần xác định xem ở runtime có method thích hợp và các yêu cầu truy cập, loại lệnh gọi có hợp lệ không.

Một phương thức có symbolic reference tới `lib.Library.version()` **không cần thực sự invoke method đó** chỉ vì VM đã nhận diện class file chứa lời gọi. Ngược lại, khi thực thi bytecode invoke, các yêu cầu resolution và instruction-specific linking checks phải được thỏa.

## 3. Early/eager resolution là gì?

**Eager resolution** nghĩa là JVM chọn **phân giải trước** một hoặc nhiều symbolic references của class đang được liên kết, chẳng hạn trong quá trình verification, thay vì đợi lần đầu lệnh bytecode trực tiếp dùng tham chiếu đó.

Ví dụ: một class có method `run()` chứa symbolic reference tới `A.m:()V` nhưng nhánh gọi `A.m()` có thể chưa được chương trình đi qua. Một implementation có thể phân giải reference liên quan sớm theo giới hạn đặc tả.

Lợi ích tiềm năng:

- Phát hiện một số vấn đề liên kết trước khi đường lệnh thực sự chạy.
- Chuẩn bị/caching kết quả resolution, khiến lần dùng sau có ít việc phải làm hơn.
- Phù hợp chiến lược implementation/verifier hoặc tối ưu runtime cụ thể.

Giới hạn:

- **Không thể tùy tiện ném lỗi đã phát hiện sớm tại một chỗ vô can.** JVMS ràng buộc điểm **throw** cho lỗi linkage.
- Không phải mọi reference đều được phép eager theo cùng cách; **`CONSTANT_Dynamic` và `invokedynamic`** có hạn chế riêng.
- “Eager” ở đây nói về **thời điểm resolve symbolic references**, không đồng nghĩa **eager loading tất cả class của classpath**, chạy mọi `static initializer` hay gọi các method sớm.
- Không nên gắn nhãn “HotSpot luôn eager” hoặc “mọi JVM luôn eager” chỉ dựa trên một log ngắn; một JVM có thể dùng nhiều chiến lược theo loại reference và hoàn cảnh.

## 4. Late/lazy resolution là gì?

**Lazy resolution** nghĩa là VM để symbolic reference ở trạng thái chưa resolve cho đến khi một hành động cụ thể thực sự cần nó, ví dụ khi một bytecode `invokestatic`, `getstatic`, `new` hoặc `checkcast` có tham chiếu tương ứng được sử dụng.

~~~text
Constant pool của Caller:
  #A = Methodref lib/Library.version:()Ljava/lang/String;

Code của Caller:
  if (someCondition) {
      invokestatic #A
  }

Nếu không đi vào nhánh:
  Có JVM có thể chưa resolve #A (lazy).
  Có JVM có thể đã thử resolve sớm #A (eager),
  nhưng phải tuân thủ quy tắc ném lỗi ở điểm sử dụng có liên quan.

Nếu đi vào nhánh:
  Lệnh invoke phải có resolution thành công và checks hợp lệ,
  hoặc lời gọi sẽ thất bại theo quy tắc liên kết.
~~~

**Không đồng nhất “lười phân giải” với “không cần phân giải”.** Những bytecode dùng symbolic reference không thể bỏ qua các kiểm tra type, access và tính đúng đắn. Một số hành vi thực tế có thể được VM tối ưu và cache, nhưng kết quả quan sát phải giữ đúng contract.

### Tham chiếu nào thường liên quan resolution?

JVMS `5.4.3 liệt kê các instruction như:

- **Class/interface**: `new`, `anewarray`, `checkcast`, `instanceof`, `multianewarray`…
- **Field**: `getfield`, `putfield`, `getstatic`, `putstatic`.
- **Methods**: `invokevirtual`, `invokespecial`, `invokestatic`, `invokeinterface`.
- **Constants and dynamic linkage**: `ldc`, `ldc_w`, `ldc2_w` và `invokedynamic` trong những trường hợp thích hợp.

Ngoài ra, một symbolic reference trong constant pool được dùng bởi method handle, method type hoặc bootstrap machinery có quy tắc resolution riêng.

Cần phân biệt **resolution của symbolic method reference** và **dynamic method dispatch**: sau khi một method reference được resolve, `invokevirtual` vẫn cần tìm method body thích hợp theo runtime class của receiver và các quy tắc lookup/selection. Còn `invokedynamic` tạo và liên kết call site theo cơ chế bootstrap riêng. Ba hoạt động không phải một.

## 5. Quy tắc then chốt: lỗi liên kết được ném khi nào?

JVMS `5.4 nêu các điều kiện triển khai phải giữ khi chọn thời điểm các hoạt động linking:

1. Một class/interface phải được **load hoàn chỉnh** trước khi được link.
2. Class/interface phải được **verify và prepare hoàn chỉnh** trước khi được initialize.
3. **Lỗi phát hiện trong linkage** phải được ném tại một **điểm chương trình thực hiện hành động** có thể trực tiếp hoặc gián tiếp cần linkage với class/interface liên quan đến lỗi.
4. Với một số dynamic constant/call-site references, đặc tả hạn chế **thời điểm được phép bắt đầu resolution**.

Đối với resolution, JVMS `5.4.3 còn khẳng định: dù JVM resolve references sớm hay muộn theo chiến lược nào, lỗi resolution phải xuất hiện **tại điểm chương trình có thể trực tiếp hoặc gián tiếp sử dụng symbolic reference gây lỗi**.

### “Phát hiện sớm” không có nghĩa “ném bất kỳ lúc nào”

Giả sử bytecode có một Methodref không tồn tại trong bản thư viện runtime:

- VM có thể **biết reference sai** trước khi dòng code ứng dụng thực sự gọi phương thức đó.
- Nhưng VM phải bảo toàn điều kiện ném lỗi khi chương trình thực hiện hành động **có liên quan và có thể cần** resolution.
- Không được kết luận “nếu eager thì ngay khi JVM process vừa start phải ném `NoSuchMethodError` cho mọi method chưa dùng”.
- Cũng không được kết luận “nếu lazy thì lỗi luôn xuất hiện chính xác ở dòng Java viết lời gọi”. JVM có loading/verification/inlining, các yêu cầu liên kết gián tiếp và startup activities; vị trí quan sát có thể phức tạp hơn source line tưởng tượng.

Vì vậy từ ngữ cần dùng là **“điểm hành động của chương trình có thể trực tiếp hoặc gián tiếp cần liên kết”**, không phải “chắc chắn đến khi opcode cụ thể được thực thi mới có thể báo lỗi” cho mọi hình thức liên kết.

### Ví dụ đối lập

| Kết luận sai | Cách hiểu theo JVMS |
| --- | --- |
| “Eager resolution bắt buộc throw lỗi ở class load.” | VM có thể phát hiện sớm nhưng phải trì hoãn điểm **throw** đúng quy tắc. |
| “Lazy resolution nghĩa không có lỗi trong linking.” | Lỗi vẫn có thể xuất hiện khi reference được sử dụng. |
| “Đã chạy được `main` nên mọi constant-pool method/field references đều hợp lệ.” | Có refs có thể chưa được dùng; lỗi có thể xuất hiện ở đường chạy về sau. |
| “Lỗi Methodref chỉ xảy ra khi method body bên đích bắt đầu chạy.” | Resolution/instruction checks có thể thất bại **trước khi** method đích được invoke. |
| “Line number của stack trace là thời điểm duy nhất JVM thực sự resolve.” | Stack trace giúp định vị error exposure; không chắc phản ánh thời điểm VM phát hiện/resolve bên trong. |

## 6. Ví dụ runnable Java 17+: quan sát đường có dùng và không dùng tham chiếu

Tạo file **`ResolutionBasics.java`**:

~~~java
public class ResolutionBasics {
    static class Helper {
        static int twice(int n) {
            return n * 2;
        }
    }

    static int execute(boolean useHelper) {
        if (!useHelper) {
            return -1;
        }
        return Helper.twice(21);
    }

    public static void main(String[] args) {
        System.out.println("skip=" + execute(false));
        System.out.println("call=" + execute(true));
    }
}
~~~

Lệnh:

~~~bash
javac -g ResolutionBasics.java
java ResolutionBasics
javap -c -v -p ResolutionBasics
~~~

**Stdout do chương trình Java in trước khi lệnh `javap` chạy:**

~~~text
skip=-1
call=42
~~~

Tại sao? `execute(false)` trả `-1` mà không đi qua nhánh gọi `Helper.twice`; `execute(true)` gọi `Helper.twice(21)` và nhận 42. Trong `javap -c -v -p`, tìm Methodref hoặc liên kết tới `ResolutionBasics$Helper.twice:(I)I` và opcode `invokestatic` trong method `execute`.

**Giới hạn của ví dụ:** đây là **hành vi điều khiển của source và bytecode**, không phải thí nghiệm đủ để biết JVM đã resolve Methodref này **lúc nào**. Output không chứa “timestamp resolution” và không buộc JVM lazy thay vì eager. Kết luận đúng là chương trình **chỉ gọi thân `twice` trên nhánh true**; resolution nội bộ vẫn tuân thủ JVMS.

## 7. Ví dụ trọng tâm: thay đổi binary API sau khi client được biên dịch

Đây là cách trực quan chứng minh một class client có thể chứa symbolic reference hợp lệ **lúc compile** nhưng không còn giải được **trên runtime thư viện khác**. Bài dùng Java 17+ và JDK tools chuẩn; tạo ba file có đường dẫn đúng như cấu trúc:

~~~text
resolution-lab/
  src/
    v1/
      lib/
        Library.java
    v2/
      lib/
        Library.java
    client/
      LinkageDemo.java
  out/                 (thư mục output, ban đầu rỗng)
~~~

### 7.1. Thư viện phiên bản 1: có method `version()`

File **`src/v1/lib/Library.java`**:

~~~java
package lib;

public class Library {
    public static String version() {
        return "v1";
    }
}
~~~

File **`src/client/LinkageDemo.java`**:

~~~java
public class LinkageDemo {
    public static void main(String[] args) {
        System.out.println("start");

        if (args.length == 0) {
            System.out.println("skipped");
            return;
        }

        try {
            System.out.println("value=" + lib.Library.version());
        } catch (NoSuchMethodError error) {
            System.out.println("linkage=NoSuchMethodError");
        }
    }
}
~~~

Biên dịch **v1 và client cùng lúc** (đứng ở thư mục `resolution-lab`):

~~~bash
mkdir -p out
javac -g -d out src/v1/lib/Library.java src/client/LinkageDemo.java

java -cp out LinkageDemo
java -cp out LinkageDemo call
~~~

**Stdout của lần chạy thứ nhất, không có argument:**

~~~text
start
skipped
~~~

**Stdout của lần chạy thứ hai:**

~~~text
start
value=v1
~~~

Câu lệnh `LinkageDemo` đã được biên dịch dựa vào `lib.Library.version:()Ljava/lang/String;`. Khi v1 hiện diện trên classpath, method resolution thành công và invocation trả chuỗi `v1`.

**Windows PowerShell:** có thể thay `mkdir -p out` bằng `New-Item -ItemType Directory -Force out`; ba lệnh `javac`/`java` còn lại có cùng ý nghĩa. Không dùng hai phiên bản Library cùng lúc trong một output directory khi đang so sánh; bước sau **cố tình thay thế** `Library.class`.

### 7.2. Thư viện phiên bản 2: xóa `version()` khỏi API

File **`src/v2/lib/Library.java`**:

~~~java
package lib;

public class Library {
    public static String release() {
        return "v2";
    }
}
~~~

Bây giờ **chỉ biên dịch v2 vào cùng thư mục output**, không biên dịch lại client:

~~~bash
javac -g -d out src/v2/lib/Library.java

java -cp out LinkageDemo
java -cp out LinkageDemo call
~~~

`out/lib/Library.class` được ghi đè thành bản v2, nhưng `out/LinkageDemo.class` vẫn chứa Methodref **`lib/Library.version:()Ljava/lang/String;`** từ lúc compile với v1.

**Stdout trong môi trường JDK 17+ thông thường (với đúng file và classpath như mô tả), lần chạy không argument:**

~~~text
start
skipped
~~~

**Stdout khi đi vào nhánh gọi method:**

~~~text
start
linkage=NoSuchMethodError
~~~

Diễn giải:

1. **`start`** được in bởi code client không cần lời gọi Library.
2. Nhánh không argument **không sử dụng `Library.version()`**; không có lời gọi method này.
3. Nhánh có argument cố invoke Methodref của v1. Ở runtime, class `lib.Library` phiên bản 2 **không khai báo** method `version()` có descriptor phù hợp. Method resolution thất bại bằng **`NoSuchMethodError`**.
4. `catch (NoSuchMethodError error)` bắt lỗi và chủ động in dòng cố định, vì vậy ví dụ tránh phụ thuộc thông báo stack trace vốn thay đổi theo JDK.

**Quy tắc quan trọng:** ví dụ chỉ nhằm mô tả một **đường sử dụng tham chiếu gây lỗi** và kết quả thực hành điển hình; không chứng minh HotSpot thực hiện “mọi Methodref resolution đều lazy”. JVMS có quyền lựa chọn eager/lazy cho những references phù hợp nhưng phải ném lỗi tại điểm hành động có thể cần resolution. Đừng suy từ việc in dòng `start` rằng JVM “chưa hề nhìn thấy” constant-pool reference.

### 7.3. Vì sao biên dịch lại client có thể đổi loại lỗi?

Nếu chạy:

~~~bash
javac -g -cp out -d out src/client/LinkageDemo.java
~~~

khi trong `out` chỉ còn Library v2 (không có `version()`), compiler Java sẽ nhận biết không tìm được `version()` trong `lib.Library` và báo **compile-time error**. Đây **không phải** `NoSuchMethodError` ở runtime.

Hai trường hợp khác nhau:

- **Compile-time error:** compiler có thông tin API mới và phát hiện source client gọi method không tồn tại.
- **Runtime linkage error:** client **đã biên dịch** theo API cũ, còn runtime class file của thư viện không còn đáp ứng tham chiếu đã ghi trong client binary.

Trong production, kiểu lỗi này thường do dependency/JAR version mismatch hoặc deployment classpath có phiên bản thư viện không đồng nhất.

### 7.4. Đọc bằng `javap` để xác minh

~~~bash
javap -v -p -classpath out LinkageDemo
javap -c -p -classpath out LinkageDemo
javap -p -classpath out lib.Library
~~~

Điều cần tìm:

- `LinkageDemo.class` vẫn có Methodref dạng `lib/Library.version:()Ljava/lang/String;`.
- Ở nhánh dùng thư viện, bytecode client chứa `invokestatic` tham chiếu Methodref ấy.
- `lib.Library` của v2 chỉ khai báo `release()` mà **không có `version()`**.
- Những chỉ số constant-pool `#N`, offsets BCI và dòng mã trong `javap` phụ thuộc compiler; **đọc nội dung biểu tượng**, không học thuộc con số `#17`.

## 8. Vì sao không nên đo thời điểm resolution bằng stdout đơn lẻ?

Mọi dòng `System.out.println` chỉ chứng minh **hành động Java quan sát được** đã diễn ra. Nó không ghi được tất cả event nội bộ của VM. Để nghiên cứu early vs late resolution, cần phân biệt:

| Câu hỏi | Có thể rút ra từ stdout ví dụ? |
| --- | --- |
| Nhánh có `Library.version()` đã được thực thi chưa? | Có, nhờ output và code |
| Với v2, lời gọi method đó còn hợp lệ không? | Không; `NoSuchMethodError` khi nhánh dùng reference |
| JVM đã scan constant pool lúc load chưa? | Không thể kết luận |
| Symbolic reference đã được eager-resolve rồi giữ error để ném lúc dùng? | Không thể kết luận chỉ từ stdout |
| JVM có cache kết quả resolution? | Đây là cơ chế theo quy tắc JVMS; không đo bằng stdout đơn giản |
| Cấu hình/module/loader khác có làm fail ở hành động khác không? | Có thể, phải điều tra ngữ cảnh runtime |

Không cần dựng một microbenchmark “đếm dòng trước lỗi” rồi khẳng định đặc tả yêu cầu VM phải lazy. Điểm cần nắm là **quyền linh hoạt về thời điểm xử lý và ràng buộc về thời điểm biểu hiện lỗi**.

## 9. Những loại lỗi resolution/linkage đáng nhận biết

| Error / exception | Phân loại | Tình huống tiêu biểu |
| --- | --- | --- |
| **`NoSuchMethodError`** | `IncompatibleClassChangeError` → `LinkageError` | Client đã compile gọi method nhưng runtime class thiếu method tương ứng |
| **`NoSuchFieldError`** | `IncompatibleClassChangeError` → `LinkageError` | Field name/descriptor được tham chiếu không tìm thấy |
| **`IllegalAccessError`** | `IncompatibleClassChangeError` → `LinkageError` | Access check thất bại khi liên kết/thực thi |
| **`IncompatibleClassChangeError`** | `LinkageError` | Runtime class/interface/member shape không phù hợp kỳ vọng bytecode, gồm mismatch static/instance |
| **`AbstractMethodError`** | `IncompatibleClassChangeError` → `LinkageError` | Method được invoke nhưng không có implementation phù hợp tại điểm selection/invocation theo quy tắc |
| **`NoClassDefFoundError`** | `LinkageError` | VM không thể tìm/định nghĩa class cần thiết ở runtime hoặc class đã bị đánh dấu initialization erroneous |
| **`VerifyError`** | `LinkageError` | Bytecode vi phạm yêu cầu verifier |
| **`ClassFormatError`** | `LinkageError` | Binary class file có định dạng không hợp lệ |
| **`BootstrapMethodError`** | `LinkageError` | Lỗi liên quan quá trình bootstrap dynamic constants/`invokedynamic` |
| **`ExceptionInInitializerError`** | `LinkageError` | Static initializer thất bại trong quá trình **initialization**, không phải là lỗi method resolution thông thường |

Cũng cần biết:

- **`ClassNotFoundException`** là **checked exception** từ một số API tải class tường minh như `Class.forName`/`ClassLoader.loadClass`, **không phải** subclass của `LinkageError`.
- **`ClassCastException`** là runtime type-check failure, có thể liên quan hai class loaders định nghĩa cùng tên nhưng **không tự chứng minh** loader constraint violation.
- **`OutOfMemoryError`** trong quá trình liên kết/cấp phát là khả năng riêng, không mặc định là “thiếu method trong constant pool”.

### Lỗi method vs class initialization

Nếu method **có tồn tại** và resolution thành công, nhưng khi JVM cần initialize owner class thì một `static { ... }` ném exception, caller có thể thấy **`ExceptionInInitializerError`**. Đây là lỗi **giai đoạn initialization**, khác với `NoSuchMethodError` do resolution không tìm ra method.

Đừng gom “mọi lỗi xuất hiện khi gọi phương thức” thành “resolution failure”. Giao dịch invoke có thể gồm resolution, access checks, class initialization, dynamic method selection và thực thi body; lỗi có thể đến từ các tầng khác nhau.

## 10. Sticky resolution failures: cùng tham chiếu, kết quả có được thử lại không?

Theo **JVMS `5.4.3**, với các symbolic references thông thường được mô tả ở mục này:

- Nếu **resolution thành công**, những lần resolve sau của **cùng symbolic reference** thành công theo kết quả đã ghi nhận; không yêu cầu tìm lại mọi thứ từ đầu.
- Nếu **resolution thất bại**, những lần resolve sau **cùng symbolic reference** tiếp tục thất bại với **cùng error** theo quy tắc đặc tả.
- Đừng suy rằng ứng dụng có thể “sửa classpath” hoặc thay đổi access configuration rồi JVM sẽ tự động liên kết lại một symbolic reference đã thất bại trong class hiện hữu.

Đây là đặc điểm quan trọng của **binary linkage stability**. Trong nhiều hệ plugin/hot reload, muốn đổi thế hệ type có thể phải dùng **class loader mới** hoặc khởi động lại vùng runtime phù hợp thay vì hy vọng JVM tự làm mới toàn bộ liên kết của class đã được load.

**Ngoại lệ cần nêu rõ:** `invokedynamic` có quy tắc kết quả **gắn với instruction site** riêng, dù các instructions có thể chỉ cùng một constant-pool entry. Dynamic constants và dynamic call sites cũng có semantics bootstrap/caching riêng. Không lấy quy tắc caching của một loại symbolic reference rồi áp máy móc cho mọi loại reference.

## 11. Giới hạn riêng: dynamic constants và `invokedynamic`

Không phải mọi symbolic reference có thể được eager-resolve tùy ý. Theo JVMS `5.4:

1. **Dynamically-computed constant** (`CONSTANT_Dynamic`): không được resolve trước khi một lệnh `ldc`/`ldc_w`/`ldc2_w` sử dụng nó được thực thi, **hoặc** nó được dùng như static argument cho một bootstrap method đang được invoke.
2. **Dynamically-computed call site** (`CONSTANT_InvokeDynamic`): không được resolve trước khi một bootstrap method cần đến call site ấy dưới vai trò static argument được invoke (theo diễn đạt điều kiện đặc tả). Đối với chính opcode `invokedynamic`, resolution của call site diễn ra theo cơ chế bootstrap khi instruction yêu cầu.
3. Một bootstrap method có thể liên quan `MethodHandle`, `MethodType`, static bootstrap arguments và tạo một `CallSite` hay constant value.
4. Lỗi bootstrap có thể được bọc thành **`BootstrapMethodError`** trong những điều kiện quy định; không nên cho rằng cứ có `invokedynamic` thì mọi lỗi đều là `NoSuchMethodError`.

**Ví dụ Java source:** phép nối chuỗi trên JDK hiện đại thường được `javac` biên dịch qua `invokedynamic` và `StringConcatFactory`. Lambda cũng thường dùng cơ chế bootstrap của invokedynamic, nhưng cách compiler sinh bytecode là chi tiết phụ thuộc bản JDK.

~~~java
public class DynamicExample {
    public static void main(String[] args) {
        int count = 3;
        System.out.println("count=" + count);
    }
}
~~~

~~~bash
javac DynamicExample.java
java DynamicExample
javap -v -c -p DynamicExample
~~~

**Stdout của chương trình:**

~~~text
count=3
~~~

Trong disassembly của `javac` Java 17+ thông thường, bạn có thể thấy `invokedynamic` cho phép nối chuỗi và `BootstrapMethods` attribute. Không dùng output này để suy rằng tất cả constant-pool entries được eager resolved ở startup; cách bootstrap được gọi phải theo quy tắc specific call site.

## 12. Phân giải, quyền truy cập và class loader: lỗi có thể xuất hiện muộn

Symbolic references không chỉ lưu tên method. Resolution phải xét **đúng runtime class identity**, loader và quyền truy cập. Một class `api.Message` do loader A định nghĩa **không tự động giống** class cùng tên do loader B định nghĩa.

Khi hai class thuộc loaders khác nhau tương tác qua method/field signatures, **loading constraints** có thể ràng buộc các cách hiểu tên class/interface để bảo vệ type safety. Nếu ràng buộc thất bại, JVM có thể ném **`LinkageError`** trong quá trình linking. Không nhầm:

- **`NoSuchMethodError`**: tên và descriptor method client mong đợi không còn có trong runtime type cần được resolve.
- **`IllegalAccessError`**: symbolic reference có thể xác định được thành viên nhưng access check không hợp lệ.
- **Loader constraint violation**: type names xuyên loader phải đồng nhất nhưng lại dẫn đến những runtime class identities không tương thích.
- **`ClassCastException`**: runtime object type không tương thích với type cast, có thể xảy ra sau khi việc load hai lớp đã thành công hợp lệ.

**Thời điểm lỗi phụ thuộc hành động resolution/linkage và deployment.** Từ thông báo lỗi nên bắt đầu điều tra **owner class, loader, name, descriptor và phiên bản binary**, chứ không phỏng đoán “chắc chắn do lazy resolution” chỉ vì lỗi phát sinh sau vài phút chạy.

### Tình huống plugin thực tế

Host compile với `api.Service.send(Message)` v1. Plugin runtime dùng `api.Service` v2 thay đổi descriptor hoặc vô tình tự định nghĩa `api.Message` bằng loader riêng. Các lớp có thể load nhưng một đường invoke/interface-resolution hoặc override checks sẽ thất bại.

Cách phân tích:

1. Đọc `Class.getClassLoader()` và `Class.getModule()` của các runtime classes liên quan.
2. Kiểm tra `javap -s -p` để so method descriptors giữa client/library.
3. Kiểm tra JAR version trên runtime classpath/module path và chính sách delegation.
4. Chọn shared loader cho API types có mặt trong signatures, tránh bundle trùng API trong child-first plugin.
5. Thử lại ở môi trường kiểm thử có thể tái tạo, không “fix” bằng cách cast cưỡng ép.

## 13. Quy trình chẩn đoán lỗi liên kết: từ stack trace tới bytecode

Một workflow có thể áp dụng khi thấy `NoSuchMethodError` hoặc một lỗi linking muộn:

### Bước A — Thu thập môi trường

~~~bash
java -version
javac -version
java -cp out LinkageDemo call
~~~

Ghi lại Java **compile version**, Java **runtime version**, classpath/module path, class loader context và stack trace/cause đầu tiên. Compiler mới và runtime cũ có thể gây `UnsupportedClassVersionError`; đó là câu chuyện **class-file version compatibility**, không phải Methodref resolution thiếu method.

### Bước B — Xác định caller và tham chiếu bị lỗi

~~~bash
javap -s -p -classpath out LinkageDemo
javap -c -v -p -classpath out LinkageDemo
~~~

Tìm instruction `invokestatic #N` hoặc opcode khác tại method gây lỗi, rồi tra `#N` trong constant pool. Đọc **owner/name/descriptor**, ví dụ:

~~~text
Methodref lib/Library.version:()Ljava/lang/String;
~~~

`#N` là constant-pool index, **không** là địa chỉ heap hay line number. Bytecode index BCI khác với constant-pool index. Stack trace line numbers được ánh xạ qua `LineNumberTable` nếu class giữ debug metadata.

### Bước C — Kiểm tra binary thực được tải

~~~bash
javap -s -p -classpath out lib.Library
javap -v -p -classpath out lib.Library
~~~

So sánh method list và descriptor thực. Nếu client đòi `version:()Ljava/lang/String;` nhưng v2 chỉ có `release:()Ljava/lang/String;`, đây là **binary API mismatch** có thể giải thích `NoSuchMethodError`.

### Bước D — Phân biệt giai đoạn lỗi

| Câu hỏi | Cách xác định |
| --- | --- |
| Class file không đọc được hoặc không hỗ trợ? | Xem `ClassFormatError`, `UnsupportedClassVersionError` |
| Bytecode không hợp lệ? | Xem `VerifyError` |
| Owner class không tìm thấy? | Xem `NoClassDefFoundError` và cause; xác định loader |
| Field/method không tồn tại đúng descriptor? | Xem `NoSuchFieldError` / `NoSuchMethodError` |
| Field/method sai static/instance hoặc owner shape? | Xem `IncompatibleClassChangeError` và instruction |
| Không đủ quyền? | Xem `IllegalAccessError`, module exports/runtime package |
| Static initializer ném exception? | Xem `ExceptionInInitializerError` và `Caused by` |
| `invokedynamic`/constant bootstrap thất bại? | Xem `BootstrapMethodError` và cause chain |

### Bước E — Chứng minh đường sử dụng

Ghi lại input/đường code khiến method reference được **sử dụng**, ví dụ `LinkageDemo call` so với `LinkageDemo` không tham số. Khi báo cáo, diễn đạt:

> “Client binary chứa tham chiếu tới method cũ; đường gọi method ấy không còn resolve được trên library v2, nên lỗi xuất hiện khi chương trình đi tới hành động cần liên kết.”

**Không tự khẳng định** “JVM chắc chắn chỉ bắt đầu resolution tại instruction ấy” nếu chưa đo được internal resolution behavior của JVM cụ thể.

### Logging bổ sung (HotSpot)

Trên HotSpot hiện đại, có thể thử:

~~~bash
java -Xlog:class+load=info -cp out LinkageDemo call
java -Xlog:help
~~~

Logging giúp quan sát class loading, nhưng **class loaded ≠ symbolic reference resolved**. Không suy rằng dòng log load của `lib.Library` là thời điểm Methodref `version` đã được phân giải. Các tag của unified logging thay đổi theo bản JVM; tham khảo `-Xlog:help` và chỉ bật mức log đủ dùng.

## 14. Câu hỏi phỏng vấn và các hiểu nhầm cần tránh

| Nhận định | Đúng hay sai, vì sao? |
| --- | --- |
| “JVM luôn resolve toàn bộ constant pool trước `main`.” | **Sai.** JVMS cho phép eager/lazy với những references thích hợp; còn ngoại lệ động có giới hạn riêng. |
| “JVM bắt buộc chỉ resolve method đúng lúc opcode `invoke` được thực thi.” | **Không tổng quát.** Có thể eager, nhưng error phải được ném ở điểm action liên quan. |
| “Eager resolution có thể ném mọi lỗi thiếu method ngay khi JVM bật.” | **Sai.** Không được tùy ý throw tại điểm không thể cần linkage/reference tương ứng. |
| “Lazy resolution là bỏ qua kiểm tra quyền truy cập.” | **Sai.** Khi resolution/instruction checks cần thiết, access control vẫn phải được thỏa. |
| “Đã initialize class nghĩa mọi reference của nó thành công.” | **Sai.** Resolution có thể còn tiếp tục về sau. |
| “`NoSuchMethodError` giống lỗi compiler `cannot find symbol`.” | **Sai.** Một cái runtime binary linkage error, một cái compile-time source error. |
| “Thay JAR dưới đường dẫn mà không tải class mới sẽ cập nhật method references đã resolved.” | **Không thể giả định.** Class identities và kết quả resolution đã được VM giữ theo quy tắc. |
| “Một lỗi linkage xuất hiện muộn chứng minh JVM dùng lazy resolution.” | **Sai.** JVM có thể phát hiện sớm rồi trì hoãn điểm throw theo JVMS. |
| “Mỗi lần invoke một method cần resolve lại reference từ đầu.” | **Sai.** Resolution outcomes có quy tắc caching/stability. |
| “`invokedynamic` cho phép tùy ý bootstrap mọi call site tại class loading.” | **Sai.** Có các giới hạn về thời điểm resolution/bootstrap. |
| “Một class có thể load thành công nhưng vỡ khi dùng một method của library.” | **Đúng,** như ví dụ client compiled v1 và chạy với library v2. |
| “`ExceptionInInitializerError` là `NoSuchMethodError` loại khác.” | **Sai.** Nó thuộc lỗi initialization, không phải lỗi tìm method thông thường. |

## 15. Tự kiểm tra có đáp án

**Câu 1.** `ClassFile` chứa `Methodref lib/Library.version:()Ljava/lang/String;` có nghĩa `Library.version` đã được invoke chưa?  
**Đáp án:** Không. Đó là symbolic reference mô tả owner/name/descriptor; invocation còn phụ thuộc đường thực thi.

**Câu 2.** JVM được phép resolve reference thông thường sớm trước khi đường gọi chạy không?  
**Đáp án:** Có, trong giới hạn của JVMS; nhưng lỗi resolution phải được ném ở điểm hành động có thể dùng reference tương ứng.

**Câu 3.** JVM được phép resolve muộn sau khi class đã initialize không?  
**Đáp án:** Có. Linking và resolution không bắt buộc giải quyết hết trước initialization.

**Câu 4.** Trong ví dụ Library v1/v2, tại sao compile lại `LinkageDemo` dựa trên v2 có thể báo compiler error, còn chạy binary cũ với v2 gây `NoSuchMethodError`?  
**Đáp án:** Compiler mới nhận diện API không còn method; binary cũ vẫn chứa Methodref v1 và resolution runtime không thể tìm method trên Library v2.

**Câu 5.** Một lần `NoSuchMethodError` xảy ra khi dùng reference; JVM có bắt buộc tự thử tải lại JAR mới ở lần dùng thứ hai không?  
**Đáp án:** Không. `JVMS `5.4.3` quy định kết quả resolution failure được giữ cho cùng symbolic reference theo điều kiện áp dụng.

**Câu 6.** `NoClassDefFoundError` và `ExceptionInInitializerError` có luôn chỉ ra cùng một pha không?  
**Đáp án:** Không. Một lỗi có thể liên quan loading/linking hoặc class ở erroneous state, còn lỗi kia thường do static initialization thất bại.

**Câu 7.** Từ `java -Xlog:class+load=info` có thể khẳng định Methodref nào đã resolve tại timestamp nào không?  
**Đáp án:** Không. Class loading log không phải per-symbolic-reference resolution log.

**Câu 8.** Vì sao `CONSTANT_Dynamic` cần quy tắc timing riêng?  
**Đáp án:** Nó có bootstrap computation và đặc tả không cho resolve quá sớm trước các hành động `ldc` liên quan hoặc bootstrap sử dụng như static argument.

**Câu 9.** Loading constraint violation có thể xuất hiện khi hai loaders không nhất trí về một tên kiểu trong method descriptor không?  
**Đáp án:** Có, nếu các constraints bắt buộc yêu cầu cùng runtime class identity mà hai loaders không thể đáp ứng.

**Câu 10.** Khi một linking error xuất hiện “muộn”, nên mô tả kết luận chắc chắn nhất là gì?  
**Đáp án:** Chương trình đã đến **hành động có liên quan tới linkage** bị lỗi; chưa thể kết luận chính xác JVM bắt đầu resolution tại thời điểm ấy hay phát hiện trước đó.

## 16. Tài liệu chính thức

- [JVMS Java SE 17 — 5.4 Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4): loading trước linking, verification/preparation trước initialization; eager vs lazy và giới hạn thời điểm báo lỗi.
- [JVMS Java SE 17 — 5.4.3 Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3): symbolic references, thời điểm lỗi, caching kết quả resolution.
- [JVMS Java SE 17 — 5.4.3.1 Class and Interface Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.1): phân giải các class/interface symbolic refs.
- [JVMS Java SE 17 — 5.4.3.2 Field Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.2): `NoSuchFieldError`, field lookup và loading constraints.
- [JVMS Java SE 17 — 5.4.3.3 Method Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.3): method lookup, lỗi `NoSuchMethodError` và liên kết class methods.
- [JVMS Java SE 17 — 5.4.3.4 Interface Method Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.4): interface methods.
- [JVMS Java SE 17 — 5.4.4 Access Control](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4): runtime access checks và khả năng lỗi.
- [JVMS Java SE 17 — 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): thời điểm class initialization.
- [JVMS Java SE 17 — 4.4 The Constant Pool](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4): Methodref, Fieldref, InvokeDynamic, Dynamic, NameAndType.
- [JDK 17 — `javap` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): xem constant pool/bytecode bằng `-v`/`-c`.
- [JLS Java SE 17 — 13 Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): thay đổi binary APIs và tương thích nhị phân Java.

**Kết luận cần nhớ:** **Early/lazy resolution** là sự linh hoạt của VM về lúc chuyển symbolic references sang runtime entities; **error timing** lại bị JVMS giới hạn bởi những **hành động của chương trình có thể cần liên kết**. Để xác định một lỗi xuất hiện muộn, hãy tìm đúng **constant-pool reference, bytecode sử dụng, binary version và class loader**, không suy từ số dòng đã in ra rằng VM chắc chắn resolve sớm hay muộn.