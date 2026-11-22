# Retransformation: ràng buộc với `NestHost`, `NestMembers`, `Record` và `PermittedSubclasses`

> **Ngữ cảnh:** Java Advance → Instrumentation → **Retransformation**. Khi một JVM đã định nghĩa class, `Instrumentation.retransformClasses(...)` có thể cài đặt phiên bản mới của **thân phương thức**, nhưng không được tùy tiện thay đổi định danh/cấu trúc/những quan hệ class đã được JVM thừa nhận. Bốn class-file attributes `NestHost`, `NestMembers`, `Record` và `PermittedSubclasses` thuộc nhóm **không được thay đổi** trong retransformation và redefinition theo đặc tả JVM TI của Java 17/21. Ví dụ dưới đây chạy với mã nguồn Java 17+ và có kiểm chứng thực tế trên OpenJDK 24.

## 1. Tại sao một lần retransform có giới hạn?

Một class có thể được instrument khi **định nghĩa lần đầu** (load-time transformation) hoặc sau khi đã có `Class<?>` bằng `retransformClasses(...)`:

~~~text
Class file ban đầu
   │
   ├── Load-time: ClassFileTransformer.transform(..., classBeingRedefined=null)
   │   └── JVM định nghĩa class và xác lập quan hệ type/nest/record/sealed
   │
   └── Class đã tồn tại trong JVM
       └── Instrumentation.retransformClasses(existingClass)
           ├── transformer có canRetransform=true được gọi lại
           ├── JVM kiểm tra class file sau toàn bộ transformer chain
           ├── hợp lệ   -> cài định nghĩa mới
           └── vi phạm -> từ chối, không cài bản thay đổi
~~~

Retransformation không phải công cụ “compile lại bất kỳ source Java nào rồi hot-swap”. Theo đặc tả JVM TI:

- Có thể sửa **method bodies** và một số nội dung constant pool/attributes, **trừ** những thay đổi bị cấm hoặc khiến class file không hợp lệ.
- Không được thêm, bỏ hoặc đổi tên **field/method**; không được đổi **method signatures**, **modifiers** và **inheritance**.
- **Không được thay đổi bốn thuộc tính cấp class:** `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses`.
- Các giới hạn áp dụng cả với `RetransformClasses` và `RedefineClasses` ở những JDK được đặc tả; đừng nghĩ dùng `redefineClasses` thay `retransformClasses` là cách hợp lệ để vượt chúng.
- Nếu một lượt retransformation yêu cầu nhiều class và JVM trả lỗi, **không class nào trong tập đó nhận định nghĩa mới**. Việc đánh giá/kiểm tra xảy ra sau khi transformer chain đã xử lý bytes.

Một Java agent phải xin capability `Can-Retransform-Classes: true` trong manifest và xác nhận `Instrumentation.isRetransformClassesSupported()`. Đồng thời `isModifiableClass(type)` chỉ cho biết class **có thể được cân nhắc để biến đổi**, không phải mọi bản vá bytecode gửi vào đều hợp lệ.

### Phân biệt ba thao tác

| Thao tác | Đầu vào | Có thể can thiệp vào bốn attributes? |
|---|---|---|
| **Load-time transform** | Bytes khi class **chưa** được JVM định nghĩa | Có thể tạo một class file hợp lệ với thuộc tính phù hợp trước khi định nghĩa lần đầu; vẫn phải tuân thủ JVMS, access control, class-format và verification |
| **Retransform** | `Class<?>` đã load, JVM chạy lại transformation pipeline | **Không được thay đổi** `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses` |
| **Redefine** | `ClassDefinition(type, replacementBytes)` của class đã load | **Cũng không được thay đổi** bốn attributes theo JVM TI |

Có thể **giữ nguyên bốn attributes** và sửa phần code hợp lệ: không nên hiểu “record/sealed/nest class không retransform được”. Một class có chứa những thuộc tính đó **vẫn có thể retransform** nếu JVM hỗ trợ, class modifiable và kết quả không vi phạm giới hạn. Sự tồn tại của thuộc tính không phải lỗi; **sự thay đổi không hợp lệ của thuộc tính** mới là vấn đề.

## 2. `NestHost` và `NestMembers`: quan hệ truy cập private

Từ Java 11 (class-file version **55**), JVM hỗ trợ khái niệm **nest** (JEP 181). Các class thuộc cùng nest có thể truy cập thành viên `private` của nhau theo quy tắc kiểm soát truy cập của JVM, kể cả khi chúng là những class file riêng.

Hai thuộc tính giữ **hai phía của cùng quan hệ**:

| Attribute | Nằm ở class nào? | Dữ liệu và ý nghĩa |
|---|---|---|
| `NestHost` | Class/interface **thành viên** không phải host | Một `u2 host_class_index` tham chiếu constant-pool `CONSTANT_Class_info` của nest host |
| `NestMembers` | Class/interface **đóng vai host** | Danh sách `number_of_classes` và các `u2 classes[]`, nêu những class được host cho phép khai là member |

Một host thuộc nest do chính nó làm host, nên không cần tự ghi một `NestHost`. Theo JVMS, **không đặt đồng thời `NestHost` và `NestMembers` trong cùng một class file**. Một nested class Java thông thường có thể có `NestHost` trỏ về outer class; outer class có `NestMembers` chứa các nested classes.

Ví dụ Java 17:

~~~java
package lab.model;

public final class Outer {
    private static int secret() {
        return 41;
    }

    public static final class Inner {
        public static int answer() {
            return secret() + 1; // Quyền truy cập private nhờ nestmates.
        }
    }
}
~~~

Khi compile, `Outer.class` thường có `NestMembers: lab/model/Outer$Inner` và `Outer$Inner.class` có `NestHost: class lab/model/Outer`. Kiểm chứng với `javap -v -p`.

**Vì sao không được đổi khi class đã load?** JVM có thể đã dùng thông tin nest để thực hiện access checking, resolution và liên kết các class. Nếu hot-swap tùy tiện đổi host hoặc danh sách member, một class đã được JVM chấp nhận có thể bỗng được cấp hoặc bị tước quyền truy cập `private`. Đặc tả không cho phép “đổi tổ tiên nest” bằng retransform/redefine.

Ví dụ **bị cấm**:

- Đổi `Outer$Inner.NestHost` từ `Outer` sang một host khác.
- Thêm/bỏ `Outer$Inner` khỏi `Outer.NestMembers`.
- Xóa toàn bộ `NestHost`/`NestMembers` của class đã load, dù không thay đổi bytecode phương thức.
- Thay nội dung danh sách member, kể cả khi tên class hiển thị trong code Java không đổi.

**Phân biệt `InnerClasses`:** thuộc tính `InnerClasses` mang metadata về cấu trúc nested-class trong source/bytecode; nó **không thay thế** `NestHost`/`NestMembers` để xác định quyền truy cập private theo nestmates. Công cụ ASM hoặc bytecode visitor không được dùng danh sách `InnerClasses` để “tái tạo” nest metadata bằng suy đoán khi retransform.

### Thận trọng với nhiều class loader

Nest membership còn gắn với **run-time package** và class identity. Hai class tên giống nhau nhưng do hai defining class loader khác nhau định nghĩa không tự nhiên là nestmates. Sửa một chuỗi tên `NestHost` không thể biến hai class loader không tương thích thành một nest hợp lệ; và với class đã load, JVM cấm thay đổi attribute trong retransformation dù tên mới trông “hợp lệ”.

## 3. `Record`: hình dạng record và các record components

Thuộc tính class-file `Record` xuất hiện từ class-file version **60** (Java 16). Nó ghi metadata về các **record components**, bao gồm tên, descriptor và attributes liên quan của từng component. Chẳng hạn:

~~~java
package lab.model;
public record Point(int x, int y) { }
~~~

Trong `Point.class`, `javap -v` có thể hiển thị:

~~~text
Record:
  int x;
    descriptor: I

  int y;
    descriptor: I
~~~

Record class còn có những field/method/constructor được compiler tạo: `private final` fields, accessors `x()`/`y()`, canonical constructor, `equals`, `hashCode`, `toString`. Nhưng **`Record` attribute không chỉ là danh sách fields**: nó là metadata record components dùng bởi reflection `Class.isRecord()` và `Class.getRecordComponents()` cùng quy tắc language/runtime.

Không được dùng retransform/redefine để:

- Thay record components `(x, y)` thành `(x, y, z)`.
- Đổi tên component `x` thành `left`, hoặc đổi descriptor component.
- Xóa `Record` attribute để biến class đã load thành một class thường.
- Thêm `Record` vào một class vốn không có để “biến nó thành record”.
- Làm code visitor vô tình làm mất hoặc viết lại `Record` metadata dưới dạng khác không tương thích.

Nhiều trường hợp trên còn vi phạm quy tắc **không thêm/xóa fields, methods hoặc đổi signatures**. Tuy nhiên ngay cả một bản vá **chỉ thay `Record` attribute** mà không đụng danh sách methods cũng bị cấm. Kiểm tra schema field/method là cần thiết nhưng **chưa đủ**.

**Điều vẫn hữu ích:** bạn có thể instrument **thân accessor, constructor hoặc business method có sẵn** khi biến đổi hợp lệ, giữ nguyên số lượng/tên/descriptor/modifiers và `Record` metadata. Ví dụ thêm một probe thời gian vào method `Point.x()` mà không thay chữ ký, nếu bytecode mới hợp lệ và không làm sai semantics của ứng dụng.

## 4. `PermittedSubclasses`: ranh giới kế thừa của sealed types

Thuộc tính `PermittedSubclasses` xuất hiện từ class-file version **61** (Java 17). Nó nằm ở sealed class/interface và liệt kê các class/interface **được phép trực tiếp extends hoặc implements** type đó.

Ví dụ:

~~~java
package lab.model;
public sealed interface Shape permits Circle, Square { }

final class Circle implements Shape { }
final class Square implements Shape { }
~~~

Trong `Shape.class`, `javap -v` có thể hiển thị:

~~~text
PermittedSubclasses:
  lab/model/Circle
  lab/model/Square
~~~

Đây là một danh sách từ metadata class file, **không phải danh sách tất cả các subtype gián tiếp**. Trong thí nghiệm, `Shape.class.getPermittedSubclasses().length == 2`. Nếu có subtype mới kế thừa từ một permitted subtype `non-sealed`, nó không tự động trở thành entry trực tiếp trong `PermittedSubclasses` của `Shape`.

Không được retransform/redefine `Shape` để:

- Thêm `Triangle` vào `PermittedSubclasses` của `Shape` đã load.
- Bỏ `Square` khỏi danh sách.
- Thay tên entry, đảo sang class khác hoặc xóa thuộc tính.
- Thêm thuộc tính vào class thường để biến nó thành sealed type sau khi đã định nghĩa.

**Lý do:** JVM dùng ràng buộc permits khi class con được định nghĩa; mở rộng/thu hẹp quyền kế thừa giữa vòng đời JVM gây bất nhất với class hierarchy đã thiết lập. Ngoài attribute, đổi modifier `final` hoặc hierarchy còn chịu các giới hạn riêng của retransform.

**Không suy diễn quá mức:** bạn vẫn có thể retransform **method bodies** của sealed interface, permitted implementation hoặc các class con vốn có, nếu không thay đổi những quan hệ bị cấm. Một chương trình có sealed class không đòi JVM phải chặn *mọi* instrumentation.

## 5. Tóm tắt thuộc tính và mức ràng buộc

| Class-file attribute | Phiên bản class file đầu tiên | Phản ánh điều gì? | Ví dụ thay đổi bị cấm khi retransform |
|---|---:|---|---|
| `NestHost` | 55.0 / Java 11 | Một class tuyên bố nest host | Thay host từ `Outer` sang `Other` |
| `NestMembers` | 55.0 / Java 11 | Danh sách thành viên được host chấp thuận | Bổ sung/xóa `Outer$Inner` |
| `Record` | 60.0 / Java 16 | Metadata record components | Đổi `Point(x, y)` thành `Point(x, y, z)` hoặc xóa attribute |
| `PermittedSubclasses` | 61.0 / Java 17 | Những direct subclasses được sealed type cho phép | Thêm/bỏ/đổi `Circle`, `Square` |

Cả bốn đều là **class-level attributes** trong JVMS §4.7; quy tắc cấm thay đổi được nêu trực tiếp ở **JVM TI — Retransform Classes** và lặp lại ở **Redefine Classes**. Các giới hạn cụ thể của runtime/JDK có thể thay đổi trong tương lai, nhưng **không thiết kế agent Java 17+ dựa vào giả định rằng VM sẽ cho phép đổi chúng**.

### Những thay đổi khác cũng bị ràng buộc

Một class có thể bị từ chối ngay cả khi giữ nguyên cả bốn attributes:

- Thêm method `trace()` vào class đã load; thêm field để lưu trạng thái của probe.
- Đổi method descriptor, return type hoặc tham số.
- Thay `extends`/`implements` hay class/method modifiers.
- Trả bytes hỏng, sai tên class, sai class-file version, có lỗi verification hoặc invalid StackMapTable.

Vì vậy trong retransform hãy ưu tiên **inject code vào method có sẵn**, và giữ trạng thái agent trong class riêng có lifecycle rõ ràng (helper/registry), không cố thêm field vào target class. Helper classes nếu cần phải được nạp hợp lệ mà không gây recursive class loading/deadlock.

## 6. Ví dụ tự chạy Java 17+: no-op hợp lệ và thay đổi bị từ chối

Thí nghiệm dùng startup agent gồm hai transformer theo hai lượt **tách biệt**:

1. **Positive:** một transformer trả `null` và ghi mốc khi retransform bốn class có các attributes ở trên. Mọi lượt hợp lệ trên HotSpot, cho thấy class chứa các metadata này vẫn retransform được.
2. **Negative:** một transformer chỉ tác động `Shape.class`, thay **một entry trong `PermittedSubclasses`** ở bytecode sau khi class đã load, rồi yêu cầu JVM cài bản đó. JVM từ chối do vi phạm ràng buộc. Mã negative cố ý làm điều không được phép để học; **không dùng parser/patcher này trong agent production**.

Các file đặt tại:

~~~text
retransform-attributes-lab/
├── manifest.mf
├── src/
│   └── lab/
│       ├── agent/
│       │   └── ConstraintAgent.java
│       ├── app/
│       │   └── ConstraintDemo.java
│       └── model/
│           ├── Outer.java
│           ├── Point.java
│           └── Shape.java
└── out/
    ├── agent/                     # sinh khi biên dịch
    ├── app/
    └── constraint-agent.jar
~~~

Dùng **JDK 17+**, chạy mọi lệnh từ thư mục `retransform-attributes-lab`. Không cần ASM, Byte Buddy hay Maven.

### 6.1 Ba file mô hình

`src/lab/model/Outer.java`:

~~~java
package lab.model;

public final class Outer {
    private static int secret() { return 41; }

    public static final class Inner {
        public static int answer() { return secret() + 1; }
    }
}
~~~

`src/lab/model/Point.java`:

~~~java
package lab.model;

public record Point(int x, int y) { }
~~~

`src/lab/model/Shape.java`:

~~~java
package lab.model;

public sealed interface Shape permits Circle, Square { }

final class Circle implements Shape { }
final class Square implements Shape { }
~~~

Chính compiler Java tạo các attributes tương ứng. Không cố tự ghép `NestHost`/`Record`/`PermittedSubclasses` khi compile. `Circle` và `Square` có package access là đủ, vì chúng cùng package với `Shape`.

### 6.2 Agent: `src/lab/agent/ConstraintAgent.java`

~~~java
package lab.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class ConstraintAgent {
    private static Instrumentation inst;

    private ConstraintAgent() {}

    public static void premain(String options, Instrumentation instrumentation) {
        inst = instrumentation;
        System.out.println("[AGENT] retransformSupported="
                + inst.isRetransformClassesSupported());
    }

    public static void observe(Class<?>... types) throws Exception {
        if (!inst.isRetransformClassesSupported()) {
            System.out.println("[PROBE] unsupported");
            return;
        }

        ClassFileTransformer observer = new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader, String name,
                    Class<?> old, ProtectionDomain pd, byte[] bytes) {
                if (old != null && name != null && name.startsWith("lab/model/")) {
                    System.out.println("[PROBE] " + name);
                }
                return null;
            }
        };

        inst.addTransformer(observer, true);
        try {
            for (Class<?> type : types) {
                if (inst.isModifiableClass(type)) {
                    inst.retransformClasses(type);
                } else {
                    System.out.println("[PROBE] unmodifiable=" + type.getName());
                }
            }
        } finally {
            inst.removeTransformer(observer);
        }
    }

    public static void attemptPermittedChange(Class<?> sealed) throws Exception {
        if (!inst.isRetransformClassesSupported() || !inst.isModifiableClass(sealed)) {
            System.out.println("[NEGATIVE] unsupported");
            return;
        }

        ClassFileTransformer mutator = new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader, String name,
                    Class<?> old, ProtectionDomain pd, byte[] bytes) {
                if (old != null && "lab/model/Shape".equals(name)) {
                    return patchPermitted(bytes);
                }
                return null;
            }
        };

        inst.addTransformer(mutator, true);
        try {
            inst.retransformClasses(sealed);
            System.out.println("[NEGATIVE] unexpectedlyAccepted");
        } catch (UnsupportedOperationException expected) {
            System.out.println("[NEGATIVE] rejected="
                    + expected.getClass().getSimpleName());
        } finally {
            inst.removeTransformer(mutator);
        }
    }

    // Đọc đủ cấu trúc để tìm class attribute PermittedSubclasses.
    // CHỈ dành cho class file nhỏ của bài tập; không phải thư viện parser tổng quát.
    private static byte[] patchPermitted(byte[] input) {
        byte[] copy = input.clone();
        ByteBuffer b = ByteBuffer.wrap(copy).order(ByteOrder.BIG_ENDIAN);
        if (b.getInt() != 0xCAFEBABE) {
            throw new IllegalArgumentException("not class");
        }
        skip(b, 4); // minor_version, major_version
        int size = u2(b);
        String[] names = new String[size];

        for (int i = 1; i < size; i++) {
            int tag = Byte.toUnsignedInt(b.get());
            switch (tag) {
                case 1 -> {
                    byte[] data = new byte[u2(b)];
                    b.get(data);
                    names[i] = new String(data, StandardCharsets.UTF_8);
                }
                case 3, 4 -> skip(b, 4);
                case 5, 6 -> { skip(b, 8); i++; }
                case 7, 8, 16, 19, 20 -> skip(b, 2);
                case 9, 10, 11, 12, 17, 18 -> skip(b, 4);
                case 15 -> skip(b, 3);
                default -> throw new IllegalArgumentException("tag=" + tag);
            }
        }

        skip(b, 4);              // access_flags + this_class
        int superIndex = u2(b); // java/lang/Object cho Shape
        skip(b, 2 * u2(b));     // interfaces
        skipMembers(b);         // fields
        skipMembers(b);         // methods

        int attributes = u2(b);
        for (int i = 0; i < attributes; i++) {
            String name = names[u2(b)];
            int length = b.getInt();
            int start = b.position();

            if ("PermittedSubclasses".equals(name)) {
                if (u2(b) < 1) {
                    throw new IllegalArgumentException("empty permitted");
                }
                // u2 đầu tiên trong danh sách: thay bởi CP index của Object.
                // Không đổi độ dài hay số lượng method/field.
                b.putShort(b.position(), (short) superIndex);
                return copy;
            }
            b.position(start + length);
        }
        throw new IllegalArgumentException("missing PermittedSubclasses");
    }

    private static int u2(ByteBuffer b) {
        return Short.toUnsignedInt(b.getShort());
    }

    private static void skip(ByteBuffer b, int n) {
        b.position(b.position() + n);
    }

    private static void skipMembers(ByteBuffer b) {
        int count = u2(b);
        for (int i = 0; i < count; i++) {
            skip(b, 6); // access_flags, name_index, descriptor_index
            int attrs = u2(b);
            for (int j = 0; j < attrs; j++) {
                skip(b, 2);  // attribute_name_index
                int len = b.getInt();
                skip(b, len);
            }
        }
    }
}
~~~

**Điểm học tập của agent:**

- `premain` nhận `Instrumentation` nhưng chưa đăng ký transformer cho đến khi app gọi method `observe` hoặc `attemptPermittedChange`. Điều này giảm log và giúp test kiểm soát thời điểm.
- Trong `observe`, transformer được đăng ký `canRetransform=true`, thấy `classBeingRedefined != null` và trả `null` để không sửa bytecode. Các lời gọi `inst.retransformClasses(type)` theo từng class, tránh phụ thuộc thứ tự callback của một batch nhiều class.
- Trong `attemptPermittedChange`, mutator chỉ trả byte mới cho `lab/model/Shape` khi xử lý **class đã có**. Hàm `patchPermitted` đi qua constant pool và member tables, tìm đúng class-level `PermittedSubclasses` rồi thay u2 của entry đầu bằng `super_class` constant-pool index. Với sealed interface `Shape`, `super_class` trỏ `java/lang/Object`; không phải class mà `Shape` cho phép direct implement. Đây là **sửa đổi deliberate** để JVM phát hiện class attribute khác bản đã cài.
- Không sửa `classfileBuffer` ngay tại chỗ: hàm tạo mảng clone. Bản class không được cài nếu JVM từ chối. `removeTransformer(mutator)` nằm trong `finally` để dọn registration sau thử nghiệm.
- Parser này **chỉ đủ để xử lý đúng cấu trúc class-file thông thường của ví dụ**. Việc đọc các UTF8 constants bằng `StandardCharsets.UTF_8` là thuận tiện khi dò tên attribute ASCII; một class-file reader production phải xử lý đầy đủ **modified UTF-8**, bounds checking, constant-pool tags, length/verification và mọi biến thể phiên bản mới. Không copy patcher làm thư viện bytecode chung.

### 6.3 Ứng dụng: `src/lab/app/ConstraintDemo.java`

~~~java
package lab.app;

import lab.agent.ConstraintAgent;
import lab.model.Outer;
import lab.model.Point;
import lab.model.Shape;

public final class ConstraintDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("[APP] nestHost="
                + Outer.Inner.class.getNestHost().getSimpleName());
        System.out.println("[APP] nestMembers="
                + Outer.class.getNestMembers().length);
        System.out.println("[APP] record=" + Point.class.isRecord());
        System.out.println("[APP] permitted="
                + Shape.class.getPermittedSubclasses().length);

        ConstraintAgent.observe(
                Outer.Inner.class, Outer.class, Point.class, Shape.class);

        ConstraintAgent.attemptPermittedChange(Shape.class);
        System.out.println("[APP] permittedAfter="
                + Shape.class.getPermittedSubclasses().length);
    }
}
~~~

Hai mốc `permitted` và `permittedAfter` so sánh metadata trước/sau lượt **bị từ chối**. Trong bài có đúng hai permitted direct implementations và hai nest members tính cả chính host. App không gọi method `answer()` vì mục tiêu là thử cấu trúc class và retransformation, không phải hành vi business.

### 6.4 Manifest và capability

`manifest.mf`, có newline cuối file và dòng trống kết thúc header:

~~~text
Manifest-Version: 1.0
Premain-Class: lab.agent.ConstraintAgent
Can-Retransform-Classes: true

~~~

- `Premain-Class` bắt JVM gọi static `premain` khi dùng `-javaagent`.
- `Can-Retransform-Classes: true` yêu cầu capability; JVM vẫn có quyền không hỗ trợ. Phải đọc `isRetransformClassesSupported()` và `isModifiableClass()` thay vì giả định.
- Không cần `Agent-Class` vì không dùng dynamic Attach, cũng không cần `Can-Redefine-Classes` vì bài chỉ gọi `retransformClasses`.

### 6.5 Biên dịch/chạy

**macOS/Linux (Bash):**

~~~bash
mkdir -p out/agent out/app
javac --release 17 -d out/agent src/lab/agent/ConstraintAgent.java
javac --release 17 -cp out/agent -d out/app src/lab/model/Outer.java src/lab/model/Point.java src/lab/model/Shape.java src/lab/app/ConstraintDemo.java
jar --create --file out/constraint-agent.jar --manifest manifest.mf -C out/agent .
java -javaagent:out/constraint-agent.jar -cp out/agent:out/app lab.app.ConstraintDemo
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/app | Out-Null
javac --release 17 -d out/agent src/lab/agent/ConstraintAgent.java
javac --release 17 -cp out/agent -d out/app src/lab/model/Outer.java src/lab/model/Point.java src/lab/model/Shape.java src/lab/app/ConstraintDemo.java
jar --create --file out/constraint-agent.jar --manifest manifest.mf -C out/agent .
java "-javaagent:out/constraint-agent.jar" -cp "out/agent;out/app" lab.app.ConstraintDemo
~~~

**Lưu ý:** ứng dụng cần gọi các helper public của agent nên `out/agent` nằm trong classpath. Agent JAR được JVM nhận riêng qua `-javaagent`; trên system loader thông thường, class `ConstraintAgent` được dùng chung. Dấu `:` phân cách classpath trên Linux/macOS, còn Windows dùng `;`. Lệnh phải chạy từ thư mục gốc để đường dẫn `out/...` đúng.

### 6.6 Stdout thực nghiệm

Đã chạy với OpenJDK 24 (được biên dịch bằng `javac --release 17`):

~~~text
[AGENT] retransformSupported=true
[APP] nestHost=Outer
[APP] nestMembers=2
[APP] record=true
[APP] permitted=2
[PROBE] lab/model/Outer$Inner
[PROBE] lab/model/Outer
[PROBE] lab/model/Point
[PROBE] lab/model/Shape
[NEGATIVE] rejected=UnsupportedOperationException
[APP] permittedAfter=2
~~~

**Phân tích kết quả:**

1. `retransformSupported=true` xác nhận capability cho agent trong JVM thử nghiệm. Trên JVM không hỗ trợ, chương trình in nhánh `unsupported` và không chạy negative test.
2. `nestHost=Outer` và `nestMembers=2` phản ánh quan hệ nest của hai class do compiler tạo. `record=true` và `permitted=2` xác nhận metadata của record và sealed type.
3. Bốn dòng `[PROBE]` chứng minh mỗi class đều được retransform khi **không thay đổi** cấu trúc. `return null` nghĩa là transformer chỉ quan sát, không thay method bodies.
4. `[NEGATIVE] rejected=UnsupportedOperationException` chứng minh JVM đã từ chối định nghĩa `Shape` có `PermittedSubclasses` bị sửa trong đường retransform. Javadoc Java `Instrumentation.retransformClasses` mô tả `UnsupportedOperationException` khi có thay đổi không hỗ trợ; ở tầng JVM TI, một lỗi tương ứng là `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_CLASS_ATTRIBUTE_CHANGED`.
5. `permittedAfter=2` cho thấy bản định nghĩa bị từ chối **không được cài** và metadata phản chiếu vẫn giữ nguyên.

Đây là output của một phiên bản/JVM cụ thể; thông điệp chi tiết của `UnsupportedOperationException`, sự hỗ trợ retransformation và các logging bổ sung có thể khác theo vendor/JDK. Không dùng một error message cố định để nhận diện mọi trường hợp.

### 6.7 Xem các thuộc tính thật bằng `javap -v`

Sau compile, trên Bash:

~~~bash
javap -v -p out/app/lab/model/Outer.class
javap -v -p 'out/app/lab/model/Outer$Inner.class'
javap -v -p out/app/lab/model/Point.class
javap -v -p out/app/lab/model/Shape.class
~~~

Trên PowerShell:

~~~powershell
javap -v -p 'out/app/lab/model/Outer.class'
javap -v -p 'out/app/lab/model/Outer$Inner.class'
javap -v -p 'out/app/lab/model/Point.class'
javap -v -p 'out/app/lab/model/Shape.class'
~~~

Các vị trí cần tìm: `NestMembers` trong Outer; `NestHost` trong Outer$Inner; `Record` trong Point; `PermittedSubclasses` trong Shape. Các chuỗi attribute có thể xuất hiện cả trong constant pool, vì vậy hãy tìm **phần khai class-level attribute cuối output**, không chỉ một string match trong constant pool. Dấu nháy đơn quanh `Outer$Inner.class` rất quan trọng trong Bash/PowerShell để dấu `$` không bị diễn giải như biến.

## 7. Chẩn đoán lỗi khi retransform/redefine

Nếu agent sử dụng ASM/Byte Buddy/instrumentation framework và thấy `UnsupportedOperationException`, phải xác định **điều gì thực sự thay đổi** sau toàn bộ transformer chain.

| Hiện tượng | Điều cần kiểm tra | Hướng sửa |
|---|---|---|
| Thử đổi nested class/host | `NestHost`, `NestMembers` khác bản gốc | Bảo toàn nest metadata và private-access topology |
| Record class bị từ chối | `Record` attribute/record components bị mất hoặc thay đổi; có thêm field/method | Bảo toàn record component table; chỉ sửa method code hợp lệ |
| Sealed type bị từ chối | `PermittedSubclasses` bị thêm/bớt/sửa | Giữ nguyên danh sách direct permitted subclasses |
| Method instrumentation vẫn thất bại dù bốn attributes không đổi | Thay method descriptor, modifiers, fields, superclass/interfaces; StackMapTable/bytecode sai | Kiểm tra toàn bộ JVMTI schema restrictions, verifier và nguồn bytes |
| Codegen viết lại class file bỏ attribute lạ | Visitor/library không copy attributes khi round-trip | Dùng phiên bản thư viện bytecode hiểu đúng class-file version; test giữ class-level metadata |
| Không nhận callback khi `retransformClasses` | Transformer đăng ký `canRetransform=false` hoặc capability không hỗ trợ | Manifest `Can-Retransform-Classes: true`, kiểm tra `isRetransformClassesSupported`, `isModifiableClass` |
| Có callback nhưng class không đổi | Transformer trả `null` hoặc lỗi trên class file kết quả | Log quyết định transform/exception và phân biệt load vs retransform |
| Muốn thêm field để chứa tracing data | Retransformation không cho đổi field schema | Lưu trạng thái probe trong agent/helper, tránh thêm field vào target |

**Không so sánh byte array thô một cách ngây thơ.** Javadoc cho phép đầu vào retransform có thể khác bytes gốc về thứ tự/content constant pool và sự có mặt của vài attributes không quan trọng; method ordering cũng có thể khác. Khi cần xác định “NestHost có bị đổi không?”, phải **parse class file và so sánh nội dung semantic** (host class name, member names, component names/descriptors và permitted names) thay vì so sánh offset/CP index bằng số tuyệt đối.

**Chú ý lỗi bị che giấu:** `ClassFileTransformer.transform` có thể ném exception mà JVM vẫn tiếp tục gọi các transformer khác. Ngoài ra, một transformer trả `null` không chứng minh những transformer khác chưa làm thay đổi bytes. Trường hợp bị từ chối thường được phát hiện ở **bước cài class definitions cuối**, tức sau cả transformer chain. Log từ một callback riêng lẻ chưa đủ để khẳng định kết quả cuối hợp lệ.

### `isModifiableClass` không phải quyền sửa mọi thứ

Thứ tự kiểm tra an toàn trước khi gọi:

~~~java
if (!instrumentation.isRetransformClassesSupported()) {
    // Chọn fallback hoặc báo capability không hỗ trợ.
} else if (!instrumentation.isModifiableClass(target)) {
    // Không nên gọi retransform với class không modifiable.
} else {
    // Vẫn phải đảm bảo bytes tạo ra không thay đổi schema/attributes bị cấm.
    instrumentation.retransformClasses(target);
}
~~~

Đây là **mảnh minh họa trong agent**, không phải Java program độc lập. `isModifiableClass == true` không có nghĩa được đổi `PermittedSubclasses` hay `NestHost`; nó chỉ loại bỏ một nhóm nguyên nhân thất bại.

## 8. Tình huống thực tế khi dùng thư viện instrument

**Tình huống A — “Tôi chỉ thêm log vào record accessor”.** Nếu transformer chèn code vào thân accessor `Point.x()` nhưng đồng thời bytecode visitor bỏ mất `Record` attribute, JVM có thể từ chối bản retransform. Đây không phải bằng chứng rằng record không thể được instrument; lỗi đến từ **việc không bảo toàn metadata**.

**Tình huống B — “Thêm nested helper vào class đã load”.** Framework generate class phụ hoặc đổi danh sách nest members của class hiện tại sau lúc load: có thể đụng `NestMembers` và bị cấm. Nếu cần helper, tạo nó đúng classloader/packaging, không rewrite nest topology của class đã tồn tại. Việc mở quyền truy cập module bằng `redefineModule` (nếu cần và được cấp phép) cũng là khái niệm **khác** với thay đổi nest metadata.

**Tình huống C — “Cho plugin subtype mới của sealed interface”.** Không thể thêm entry vào `PermittedSubclasses` của sealed interface đã load bằng retransform. Nếu kiến trúc đòi mở rộng runtime, hãy thiết kế extension point khác (composition, service provider hoặc interface non-sealed được cho phép từ đầu), hoặc triển khai version class mới trong runtime/classloader phù hợp khi khởi động lại.

**Tình huống D — “Class load lần đầu thì chạy được, nhưng retransform sau đó fail”.** Ở lần load đầu, transformer có thể thiết lập class file hợp lệ theo một cấu trúc; khi retransform, pipeline vô ý sinh output khác về nest/record/permits. Lúc này hãy so sánh **định nghĩa đã được JVM chấp nhận** và output của lần retransform, không chỉ so source files trên đĩa.

## 9. Câu hỏi tự kiểm tra

1. **Nếu class có `NestMembers`, nó có bị cấm retransform hoàn toàn không?** Không. Có thể thay method bodies hợp lệ, nhưng không đổi `NestMembers`.
2. **`NestHost` và `NestMembers` có giống `InnerClasses` không?** Không; hai thuộc tính đầu thuộc quan hệ nestmate access, còn `InnerClasses` mô tả metadata nested classes.
3. **Record có thể chèn timing probe vào accessor không?** Có thể, nếu bytecode hợp lệ và giữ nguyên field/method schema, `Record` metadata cùng các ràng buộc khác.
4. **Muốn thêm một record component bằng retransform thì sao?** Không được; vi phạm `Record` attribute và thường cả field/method schema.
5. **Có thể thay danh sách permitted direct subclasses sau khi sealed class đã load không?** Không theo JVM TI retransformation/redefinition hiện hành.
6. **Nếu retransform chỉ gọi `transform` rồi trả `null` cho sealed class, có thể thành công không?** Có; ví dụ chạy được trên HotSpot/OpenJDK.
7. **`isModifiableClass(type) == true` có cho phép sửa bốn attributes không?** Không. Capability/class modifiability không xóa các class-attribute restrictions.
8. **Nếu một class trong batch retransform lỗi thì những class còn lại đã được cài bytes mới chưa?** Theo JVMTI, nếu batch trả lỗi thì không class nào trong batch được cài định nghĩa mới.
9. **Có thể sửa `PermittedSubclasses` bằng `redefineClasses` thay vì retransform không?** Không, quy tắc JVM TI cho redefinition cũng cấm thay đổi nó.
10. **Vì sao bản vá có vẻ chỉ thay method body mà vẫn bị từ chối?** Một công cụ rewrite có thể vô tình làm mất metadata, hoặc có transformer khác trong chain thay đổi class file.
11. **Tại sao không lấy raw CP index bằng số để so sánh hai bản class file?** Vì constant-pool layout có thể thay đổi giữa các lượt; phải so sánh nội dung attribute đã resolve.
12. **Bài thử thay entry PermittedSubclasses rồi lỗi có chứng minh Java không hỗ trợ sealed types trong agent không?** Không. Nó chỉ chứng minh **đổi metadata sealed đã được JVM cài đặt** là không hợp lệ.

## 10. Checklist thiết kế transformer an toàn

- [ ] Xác minh đúng JVM/capability: `Can-Retransform-Classes`, `isRetransformClassesSupported()` và `isModifiableClass()`.
- [ ] Chỉ biến đổi code trong các method đã tồn tại, giữ nguyên schema, modifiers và inheritance.
- [ ] Giữ nguyên semantic `NestHost`/`NestMembers`, `Record` và `PermittedSubclasses` của class đã định nghĩa.
- [ ] Không làm mất class-file attributes khi parse/rewrite bằng ASM, Byte Buddy hoặc codegen khác.
- [ ] Thử test với **nested class**, **record** và **sealed class**, không chỉ class POJO đơn giản.
- [ ] Với ClassFileTransformer, lọc đúng internal class name và `classBeingRedefined`; tránh đệ quy load/IO nặng trong callback.
- [ ] Không đánh đồng `isModifiableClass` với “được thêm field/method/nest member”.
- [ ] Khi lỗi, ghi nhận exception từ API, class identity/loader, capabilities, outcome của toàn bộ transformer chain.
- [ ] Xác nhận method đang chạy trên stack có thể tiếp tục dùng phiên bản bytecode cũ, còn những lời gọi mới dùng method version đã cài.
- [ ] Không kỳ vọng retransform chạy lại static initializer, tạo lại instance hoặc đổi giá trị field hiện tại.

## Tài liệu chuẩn

- [JVM TI 21 — Retransform Classes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RetransformClasses): đặc tả nêu trực tiếp không được thay đổi `NestHost`, `NestMembers`, `Record` hoặc `PermittedSubclasses` và các lỗi redefinition.
- [JVM TI 21 — Redefine Classes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RedefineClasses): những ràng buộc tương ứng với redefinition.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capability, `retransformClasses`, `UnmodifiableClassException`, `UnsupportedOperationException`.
- [JVMS 21 — §4.7.28 NestHost, §4.7.29 NestMembers](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.28): định dạng và quyền nghĩa vụ của hai nest attributes.
- [JVMS 21 — §4.7.30 Record](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.30): định dạng metadata record components.
- [JVMS 21 — §4.7.31 PermittedSubclasses](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.31): danh sách direct permitted subclasses của sealed class/interface.
- [JVMS 21 — §5.4.4 Access Control](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.4): nestmate access và kiểm tra nest host/host membership.
