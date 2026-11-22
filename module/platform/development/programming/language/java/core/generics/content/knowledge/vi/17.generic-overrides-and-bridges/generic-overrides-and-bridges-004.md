# Đối chiếu mã Java với bytecode bằng `javap`: ghi đè generic và phương thức cầu nối

## Mục tiêu học tập

Bài này thuộc chủ đề **Ghi đè và cầu nối (overriding and bridge methods)** trong Java generics. Sau khi hoàn thành, bạn có thể:

- Đọc một phương thức `@Override` ở Java source và tìm phương thức tương ứng trong tệp `.class`.
- Giải thích vì sao trình biên dịch có thể tạo **bridge method** ngoài những phương thức do lập trình viên khai báo.
- Phân biệt `Signature` mô tả thông tin generic với **JVM descriptor** dùng để gọi phương thức.
- Dùng `javap -s`, `javap -c`, `javap -v` để kiểm tra descriptor, bytecode, cờ `ACC_BRIDGE` và `ACC_SYNTHETIC`.
- Theo dõi đúng luồng gọi phương thức qua biến kiểu cha và dự đoán nơi phát sinh `ClassCastException` khi dùng raw type sai.
- Nhận ra cầu nối do erasure, cầu nối liên quan đến kiểu trả về hiệp biến và ảnh hưởng của upper bound không phải `Object`.

Mọi phần kết quả bên dưới được đối chiếu với ví dụ Java 17 chạy thực tế. Các đoạn trích `javap` chỉ giữ những dòng liên quan; các vị trí bytecode/constant-pool có thể khác tùy JDK.

## 1. Vấn đề: mã Java nói “ghi đè”, descriptor lại khác nhau

Xét hai kiểu:

```java
class Processor<T> {
    public T transform(T value) {
        return value;
    }
}

class UppercaseProcessor extends Processor<String> {
    @Override
    public String transform(String value) {
        return value.toUpperCase();
    }
}
```

Nhìn từ Java source, `UppercaseProcessor` kế thừa `Processor<String>`. Sau khi thay `T = String` để kiểm tra kiểu, phương thức `transform(String)` trong lớp con **ghi đè** phương thức `transform(T)` của lớp cha. Chú thích `@Override` được trình biên dịch chấp nhận.

Nhưng `Processor<T>` khai báo `T` **không có giới hạn tường minh** nên type erasure thay `T` bằng `Object`. Sau biên dịch:

| Nơi khai báo | Nhìn từ Java source | JVM descriptor |
| --- | --- | --- |
| `Processor<T>` | `T transform(T)` | `(Ljava/lang/Object;)Ljava/lang/Object;` |
| `UppercaseProcessor` | `String transform(String)` | `(Ljava/lang/String;)Ljava/lang/String;` |

Nếu runtime chỉ thấy phương thức `transform(String)` ở lớp con, lời gọi qua `Processor<String>` vẫn có thể tham chiếu đến chữ ký đã xóa `transform(Object)`, dẫn tới vấn đề giữ đúng ngữ nghĩa ghi đè. `javac` giải quyết bằng một **phương thức cầu nối** có descriptor tương thích với phương thức của lớp cha. Cầu nối nhận `Object`, ép sang `String`, rồi ủy quyền cho phương thức `transform(String)` thật.

Phương thức cầu nối này **không xuất hiện trong source**. Nó được trình biên dịch tạo tự động vào tệp `.class` để bảo đảm tính đa hình sau type erasure.

## 2. Chương trình Java 17 có thể chạy và kiểm tra

Tạo tệp **`BridgeInspection.java`** với nguyên văn chương trình:

```java
import java.lang.reflect.Method;

public class BridgeInspection {
    static class Processor<T> {
        public T transform(T value) {
            return value;
        }
    }

    static final class UppercaseProcessor extends Processor<String> {
        @Override
        public String transform(String value) {
            return value.toUpperCase();
        }
    }

    static class Provider<T> {
        public T produce() {
            return null;
        }
    }

    static final class StringProvider extends Provider<String> {
        @Override
        public String produce() {
            return "ready";
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Processor<String> processor = new UppercaseProcessor();
        System.out.println("generic call: " + processor.transform("java"));

        Method concrete = UppercaseProcessor.class
                .getDeclaredMethod("transform", String.class);
        Method bridge = UppercaseProcessor.class
                .getDeclaredMethod("transform", Object.class);

        System.out.println("concrete: "
                + concrete.getReturnType().getSimpleName()
                + ", bridge=" + concrete.isBridge()
                + ", synthetic=" + concrete.isSynthetic());
        System.out.println("bridge: "
                + bridge.getReturnType().getSimpleName()
                + ", bridge=" + bridge.isBridge()
                + ", synthetic=" + bridge.isSynthetic());

        Provider<String> provider = new StringProvider();
        System.out.println("provider: " + provider.produce());

        Processor raw = new UppercaseProcessor();
        try {
            raw.transform(100);
        } catch (ClassCastException ex) {
            System.out.println("raw call: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Từ thư mục chứa tệp, chạy:

```bash
javac -Xlint:unchecked BridgeInspection.java
java BridgeInspection
```

**Stdout đã kiểm chứng:**

```text
generic call: JAVA
concrete: String, bridge=false, synthetic=false
bridge: Object, bridge=true, synthetic=true
provider: ready
raw call: ClassCastException
```

`javac -Xlint:unchecked` còn phát cảnh báo cho lời gọi `raw.transform(100)` trên raw type `Processor` (cảnh báo là đầu ra của compiler, không nằm trong stdout của ứng dụng). Cách gọi raw được giữ **cố ý** để quan sát rủi ro khi bỏ qua kiểm tra kiểu. Trong mã ứng dụng thông thường, hãy dùng `Processor<String>` thay vì raw `Processor`.

Tại sao có ba dòng cần chú ý?

- `generic call: JAVA`: khi gọi qua tham chiếu kiểu cha `Processor<String>`, chương trình vẫn thực thi phần thân ghi đè của `UppercaseProcessor`.
- Reflection nhìn thấy **hai** phương thức trong lớp con: phương thức người lập trình khai báo có tham số `String`, và phương thức cầu nối do compiler sinh có tham số `Object`.
- `raw call: ClassCastException`: raw type cho phép qua bước kiểm tra source với cảnh báo, nhưng bridge phải ép đối số `Integer` sang `String`; phép ép đó thất bại.

## 3. Lệnh `javap` cần dùng và cách đọc

Sau khi `javac` thành công, chương trình trên tạo các tệp class cho lớp ngoài cùng và những lớp lồng, ví dụ `BridgeInspection$UppercaseProcessor.class`.

Dùng ba mức độ quan sát, mỗi lệnh phục vụ mục tiêu khác nhau:

```bash
# 1. Xem descriptor của các method, kể cả private.
javap -p -s 'BridgeInspection$UppercaseProcessor'

# 2. Xem mã lệnh trong phần thân từng method.
javap -p -s -c 'BridgeInspection$UppercaseProcessor'

# 3. Xem flags, thuộc tính Signature và chi tiết class file.
javap -p -v 'BridgeInspection$UppercaseProcessor'
```

Dấu nháy đơn quanh tên lớp lồng đặc biệt hữu ích trên Bash và PowerShell vì ký tự `$` có ý nghĩa với shell. Trên Windows PowerShell, những lệnh trên cũng có thể dùng dấu nháy đơn như ví dụ. Nếu đã lưu các tệp vào một thư mục khác, cung cấp `-classpath <thư-mục-chứa-class>`, hoặc chạy ngay từ thư mục ấy.

Ý nghĩa các tùy chọn:

| Tùy chọn | Dữ liệu chính | Dùng khi |
| --- | --- | --- |
| `-p` | Hiển thị mọi thành viên, kể cả private | Không bỏ sót phương thức được sinh thêm |
| `-s` | Hiển thị JVM descriptor | Xác định erasure của kiểu tham số và kết quả |
| `-c` | Disassemble mã lệnh JVM của phương thức | Kiểm tra `checkcast`, `invokevirtual`, `areturn` |
| `-v` | Chi tiết class file, access flags, constant pool, thuộc tính | Xác định chính xác `ACC_BRIDGE`, `ACC_SYNTHETIC`, `Signature` |

Chỉ chạy `javap BridgeInspection` trên lớp ngoài cùng có thể khiến bạn không thấy bridge bên trong lớp lồng. Hãy trỏ đúng **class chứa phương thức ghi đè**: `BridgeInspection$UppercaseProcessor`.

## 4. Đối chiếu trực tiếp `UppercaseProcessor`: hai descriptor

Đoạn liên quan từ kết quả thực tế của:

```bash
javap -p -s -c 'BridgeInspection$UppercaseProcessor'
```

```text
public java.lang.String transform(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
  Code:
     0: aload_1
     1: invokevirtual #7  // Method java/lang/String.toUpperCase:()Ljava/lang/String;
     4: areturn

public java.lang.Object transform(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  Code:
     0: aload_0
     1: aload_1
     2: checkcast     #8  // class java/lang/String
     5: invokevirtual #13 // Method transform:(Ljava/lang/String;)Ljava/lang/String;
     8: areturn
```

Các số `#7`, `#8`, `#13` là index trong constant pool của lần biên dịch kiểm tra, không phải giá trị chuẩn bắt buộc ở mọi JDK. Nếu compiler thay đổi thứ tự constant pool, nội dung cần quan sát vẫn là các cặp **descriptor và bytecode**.

Tách thành hai phương thức:

**Phương thức thực do lập trình viên viết:**

```java
public String transform(String value) {
    return value.toUpperCase();
}
```

Nó có JVM descriptor `(Ljava/lang/String;)Ljava/lang/String;`.

**Phương thức cầu nối được compiler tạo (mã giả gần tương đương):**

```java
// PSEUDOCODE: minh họa compiler tạo bridge trong bytecode.
// Không tự viết thêm phương thức này vào UppercaseProcessor.
public Object transform(Object value) {
    return transform((String) value);
}
```

Cầu nối có JVM descriptor `(Ljava/lang/Object;)Ljava/lang/Object;`, chính là dạng erasure của phương thức trong `Processor<T>`. Ví dụ mã giả minh họa semantics của method sinh, không phải đoạn cần sao chép vào lớp con: tự viết `transform(Object)` cạnh override generic sẽ gây xung đột/name clash trong Java source.

### Đọc bytecode của cầu nối theo từng bước

1. `aload_0`: đưa `this` lên operand stack.
2. `aload_1`: đưa tham số `Object value` lên stack.
3. `checkcast java/lang/String`: kiểm tra đối tượng nhận được có thể ép sang `String`; với `Integer` sẽ ném `ClassCastException`.
4. `invokevirtual ... transform(String):String`: gọi method chuyên biệt trong lớp con (được người lập trình viết).
5. `areturn`: trả về tham chiếu kết quả. `String` cũng là `Object`, nên ở bước trả về không cần tạo một đối tượng khác.

Với `Processor<String> p = new UppercaseProcessor(); p.transform("java")`, bytecode lời gọi có thể tham chiếu descriptor erased của lớp cha. Cơ chế dispatch chọn triển khai tương ứng trên đối tượng lớp con thông qua bridge, rồi bridge chuyển tới `transform(String)`. Nhờ vậy, ngữ nghĩa ghi đè mà Java source hứa vẫn được thực thi tại runtime.

Đây là điểm quan trọng: **bridge bảo toàn đa hình (polymorphism)** khi descriptor của phương thức được dùng để gọi qua lớp cha không trùng trực tiếp với descriptor của phương thức chuyên biệt trong lớp con.

## 5. Xác nhận cờ `ACC_BRIDGE` và `ACC_SYNTHETIC`

Chạy:

```bash
javap -p -v 'BridgeInspection$UppercaseProcessor'
```

Trong đầu ra dài, tìm phương thức có descriptor `(Ljava/lang/Object;)Ljava/lang/Object;`. Trích đoạn đã kiểm tra:

```text
public java.lang.String transform(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
  flags: (0x0001) ACC_PUBLIC

public java.lang.Object transform(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
```

Ý nghĩa:

- `ACC_PUBLIC`: bridge trong ví dụ vẫn công khai, tương thích với phương thức ghi đè công khai của lớp cha.
- `ACC_BRIDGE`: class file đánh dấu phương thức này là **bridge** do compiler tạo nhằm duy trì quan hệ ghi đè/kiểu.
- `ACC_SYNTHETIC`: thành viên được compiler sinh ra; không phải một phương thức thông thường do lập trình viên trực tiếp khai báo trong source.

Không suy ra rằng mọi phương thức `synthetic` đều là bridge: `synthetic` là khái niệm rộng hơn. Với method ở đây, cả hai cờ cùng xuất hiện.

Trình biên dịch có thể chọn những chi tiết bytecode khác khi sinh bridge; để kiểm tra một class file cụ thể, hãy tin descriptor và flags của chính class file đó, thay vì học thuộc bytecode của ví dụ.

## 6. Reflection kiểm chứng bytecode từ chương trình Java

Trong `main` của chương trình hoàn chỉnh, hai phương thức được truy xuất bằng:

```java
Method concrete = UppercaseProcessor.class
        .getDeclaredMethod("transform", String.class);
Method bridge = UppercaseProcessor.class
        .getDeclaredMethod("transform", Object.class);
```

Đây là đoạn trích từ `BridgeInspection.java`; các import `java.lang.reflect.Method`, class và method `main` đã có trong chương trình chạy ở mục 2.

Đầu ra xác nhận:

```text
concrete: String, bridge=false, synthetic=false
bridge: Object, bridge=true, synthetic=true
```

`Class.getDeclaredMethod(name, parameterTypes...)` tìm theo tên và kiểu tham số; cầu nối có tham số `Object` nên có thể được truy xuất riêng với phương thức thật có tham số `String`. `Method.isBridge()` và `Method.isSynthetic()` phản ánh vai trò của các method trong class file.

Khi xây công cụ reflection, serializer, mapper hoặc framework nhận diện API của người dùng, bạn cần biết cầu nối có thể hiện diện trong `getDeclaredMethods()`. Nếu mục tiêu là lấy phương thức do người dùng khai báo để xử lý metadata, phải xem xét `isBridge()`/`isSynthetic()` và quan hệ ghi đè cho phù hợp; không đếm máy móc tất cả method cùng tên thành API độc lập. Trong một số trường hợp framework vẫn **cần** resolve bridge về method thực để tìm annotation hoặc generic metadata đúng ngữ cảnh.

Tránh giả định thứ tự của mảng do `getDeclaredMethods()` trả về. Trong ví dụ, chúng ta dùng `getDeclaredMethod` với tham số cụ thể để kết quả không phụ thuộc thứ tự liệt kê.

## 7. Một biến thể quan trọng: tham số không đổi, kiểu trả về đổi

Bridge không chỉ liên quan đến tình huống `transform(T)`. Trong cùng tệp chạy được ở mục 2 còn có:

```java
static class Provider<T> {
    public T produce() {
        return null;
    }
}

static final class StringProvider extends Provider<String> {
    @Override
    public String produce() {
        return "ready";
    }
}
```

Từ Java source, `StringProvider.produce()` ghi đè phương thức ở `Provider<String>`. Phương thức cha sau erasure trả về `Object`; phương thức lớp con trả về `String`. Kiểu tham số đều rỗng.

Dùng:

```bash
javap -p -s -c 'BridgeInspection$StringProvider'
```

Hai phương thức quan trọng trong kết quả thực tế:

```text
public java.lang.String produce();
  descriptor: ()Ljava/lang/String;
  Code:
     0: ldc           #7  // String ready
     2: areturn

public java.lang.Object produce();
  descriptor: ()Ljava/lang/Object;
  Code:
     0: aload_0
     1: invokevirtual #9  // Method produce:()Ljava/lang/String;
     4: areturn
```

**Khác biệt so với cầu nối ở `transform(Object)`:** phương thức `produce()` không có đối số cần `checkcast`. Cầu nối đơn giản gọi bản trả về `String` rồi trả dưới dạng `Object`.

Cần nhớ rằng JVM method descriptor **có chứa kiểu trả về**. Việc compiler tạo cầu nối có cùng danh sách tham số nhưng descriptor kiểu trả về khác nhau là hợp lệ ở cấp class file. Trong Java source, bạn không được tự khai báo hai overload chỉ khác kiểu trả về:

```java
// Không thể tự khai báo trong cùng lớp Java source:
// String produce() { ... }
// Object produce() { ... }
```

Các bridge còn có thể phát sinh với ghi đè trả về kiểu hiệp biến (*covariant return*) ngay cả khi không có generic. Khi kiểm tra bằng `javap`, hãy kết luận từ quan hệ override thực tế và descriptor chứ đừng mặc định mọi bridge chỉ do `<T>`.

## 8. Upper bound ảnh hưởng descriptor cầu nối thế nào?

Với `Processor<T>`, giới hạn trên của `T` là `Object` vì không khai báo `extends`. Nếu thay bằng `<T extends Number>`, erasure của `T` sẽ là `Number`.

Một ví dụ độc lập khác, tệp **`BoundedBridge.java`**:

```java
public class BoundedBridge {
    static class Receiver<T extends Number> {
        public void accept(T value) {
            System.out.println("base: " + value);
        }
    }

    static final class IntegerReceiver extends Receiver<Integer> {
        @Override
        public void accept(Integer value) {
            System.out.println("integer: " + value);
        }
    }

    public static void main(String[] args) {
        Receiver<Integer> receiver = new IntegerReceiver();
        receiver.accept(7);
    }
}
```

Biên dịch/chạy/kiểm tra:

```bash
javac BoundedBridge.java
java BoundedBridge
javap -p -s 'BoundedBridge$IntegerReceiver'
```

Stdout đã kiểm chứng:

```text
integer: 7
```

Đoạn trích descriptor thực tế:

```text
public void accept(java.lang.Integer);
  descriptor: (Ljava/lang/Integer;)V

public void accept(java.lang.Number);
  descriptor: (Ljava/lang/Number;)V
```

Phương thức `accept(Number)` được tạo làm cầu nối của phương thức trong `Receiver<T extends Number>`; erasure dùng `Number`, **không phải** `Object`. Phương thức cầu nối chuyển đối số `Number` về `Integer` trước khi gọi phương thức thật. Vì thế câu khẳng định “mọi bridge generic đều có tham số `Object`” là sai.

Khi một type variable có nhiều giới hạn, erasure dựa trên giới hạn đầu tiên. Quy tắc xóa kiểu áp dụng vào **chữ ký JVM thực sự đang được bridge kết nối**; không nên tự suy ra descriptor chỉ từ kiểu giá trị truyền tại một điểm gọi.

## 9. Bridge và overload: đừng lẫn khái niệm

**Override** là quan hệ giữa phương thức lớp con với phương thức lớp cha/interface theo các quy tắc của ngôn ngữ, bao gồm trường hợp sau thay thế tham số kiểu generic. `@Override` giúp compiler xác nhận ý định đó.

**Overload** là nhiều phương thức có tên giống nhau nhưng khác danh sách tham số trong ngữ cảnh cho phép. Ví dụ `void print(String)` và `void print(Integer)` là overload thông thường. Compiler không tự biến mọi overload thành bridge.

**Bridge** là phương thức bổ sung trong bytecode do compiler tạo để giữ ngữ nghĩa override khi descriptor cụ thể khác descriptor được dùng qua kiểu cha. Bridge có thể nhìn giống một overload nếu chỉ xét `javap -p`, nhưng nó mang cờ `ACC_BRIDGE` và có vai trò ủy quyền.

Ví dụ lỗi sai phổ biến:

```java
class Parent<T> {
    public void handle(T value) {}
}

class Child extends Parent<String> {
    // Sai nếu mong đây là override của handle(String):
    // public void handle(Object value) {}
}
```

Trường hợp này không phải giải pháp tự viết bridge; giữa `handle(Object)` ở lớp con và phương thức cha sau thay kiểu có xung đột erasure/name clash, và không thể dùng nó thay cho `handle(String)` một cách hợp lệ.

Cách viết đúng:

```java
class Child extends Parent<String> {
    @Override
    public void handle(String value) {
        System.out.println(value);
    }
}
```

Hai đoạn này minh họa độc lập với các chương trình hoàn chỉnh phía trên; đặt mỗi cặp lớp trong một tệp/ngữ cảnh riêng khi thử nghiệm.

**Giữ `@Override`** để phát hiện sớm tên sai, kiểu tham số sai hoặc việc vô tình tạo overload khác với phương thức định ghi đè. Việc sinh bridge là trách nhiệm compiler; không thêm bridge thủ công vào Java source.

## 10. Phân biệt `descriptor`, `Signature` và mã lệnh

Khi dùng `javap -v`, ba loại bằng chứng trả lời ba câu hỏi khác nhau:

| Thứ kiểm tra | Câu hỏi | Quan sát trong ví dụ |
| --- | --- | --- |
| **Descriptor** | JVM nhận/trả kiểu gì ở mức binary? | `transform(Object):Object` hoặc `transform(String):String` |
| **Signature metadata** | Class/method có khai báo generic ra sao? | `Processor<T>`, `extends Processor<String>` có thể hiện trong metadata |
| **Code** | Khi chạy thì method làm gì? | Bridge ép `Object` thành `String` rồi gọi method thật |
| **Access flags** | Method có phải do compiler sinh làm cầu nối? | `ACC_BRIDGE, ACC_SYNTHETIC` |
| **Reflection** | Chương trình có thể nhận diện method cầu nối không? | `Method.isBridge() == true` |

Một dòng `Signature` nói lớp con mở rộng `Processor<String>` **không** làm biến mất descriptor `Processor.transform(Object):Object`. Metadata generic giúp mô tả khai báo cho công cụ, còn method bridge giúp thực thi đúng dispatch ở binary level.

Không đồng nhất `Signature` với “một phương thức được gọi tại runtime” và không đồng nhất `checkcast` với việc sinh một instance mới. `checkcast` chỉ kiểm tra khả năng ép một tham chiếu sang kiểu mong muốn.

## 11. Lỗi và bẫy thường gặp khi đọc `javap`

**Chỉ nhìn source, bỏ qua bridge.** Nếu lớp con ghi đè thành công nhưng descriptor của lớp cha và lớp con khác nhau sau erasure, hãy kiểm tra class file lớp con trước khi kết luận JVM không dispatch đúng.

**Nhầm `synthetic` và `bridge`.** Một method `synthetic` không nhất thiết là bridge. Dùng `ACC_BRIDGE` hoặc `Method.isBridge()` để nhận diện chính xác hơn.

**Dùng sai tên lớp lồng.** Với `static class UppercaseProcessor` trong `BridgeInspection`, class file có tên binary `BridgeInspection$UppercaseProcessor`. Đừng chỉ chạy `javap BridgeInspection` rồi tìm method lớp con không có trong lớp ngoài.

**Lấy số constant-pool làm kết luận.** Các mã như `#8` và offset `2` là đặc thù của bản biên dịch. Khi giải thích, ưu tiên tên method, descriptor, `checkcast` và opcode `invokevirtual`.

**Nghĩ bridge làm mọi raw call an toàn.** Ví dụ `raw.transform(100)` chứng minh điều ngược lại: bridge ném `ClassCastException` nếu giá trị không phù hợp với kiểu chuyên biệt.

**Cho rằng mỗi method tên trùng là overload do tác giả viết.** Một số method có thể là bridge ẩn trong source. Dùng `javap -v`, `isBridge()` và quan hệ giữa các lớp.

**Suy luận cứng rằng return type không liên quan descriptor.** JVM descriptor có kiểu trả về; ví dụ `StringProvider.produce()` có một bridge trả `Object` để phù hợp với dạng erased của phương thức cha.

**Xóa thủ công bridge khỏi bytecode.** Làm như vậy có thể phá vỡ dispatch/khả năng tương thích binary của lớp. Sửa mã nguồn đúng quan hệ ghi đè và để compiler sinh bridge cần thiết.

## 12. Quy trình đối chiếu nhanh trên dự án thực

Khi gặp một phương thức generic `@Override` khó hiểu:

1. **Nhìn source:** xác định lớp cha/interface, `T`, giới hạn của `T`, lớp con thay `T` bằng kiểu nào và chữ ký override cụ thể.
2. **Dự đoán erasure:** nếu `T` không giới hạn, dùng `Object`; nếu bị giới hạn như `T extends Number`, dùng `Number`. Phân biệt kiểu tham số và kiểu trả về.
3. **Biên dịch đúng Java version:** dùng `javac`; xem cảnh báo `-Xlint:unchecked` nếu dùng raw type.
4. **Xem `javap -p -s`:** tìm descriptor của phương thức được viết ở source và method bổ sung tương thích với dạng erased.
5. **Xem `javap -p -c`:** tìm `checkcast`, method đích và cách trả về.
6. **Xem `javap -p -v`:** xác minh bridge có `ACC_BRIDGE` và `ACC_SYNTHETIC`.
7. **Thử qua tham chiếu kiểu cha:** đảm bảo dispatch đi đến override và kiểm tra một tình huống raw type sai khi cần chứng minh rủi ro.
8. **Đối chiếu reflection:** nếu framework xử lý method descriptors, quan sát `isBridge()` và cân nhắc resolve method thật.

Thứ tự này đưa bạn từ **ý định trong Java source** đến **bằng chứng trong bytecode** rồi trở lại **hành vi runtime**, giúp phân biệt lỗi suy luận về generics với lỗi trong thuật toán.

## 13. Bài tập có đáp án

### Bài 1. Dự đoán bridge cho `transform`

Cho `Processor<T>` và `UppercaseProcessor extends Processor<String>`, hỏi trình biên dịch có tạo `transform(Object)` trong lớp con không? Descriptor và vai trò của nó là gì?

**Đáp án:** có. `(Ljava/lang/Object;)Ljava/lang/Object;` phù hợp với phương thức `Processor<T>` sau erasure. Nó nhận `Object`, ép sang `String`, gọi `transform(String)` và trả về kết quả như `Object`.

### Bài 2. Nhận diện lỗi lúc chạy

Biến `Processor raw = new UppercaseProcessor();` được dùng để gọi `raw.transform(100)`. Lỗi nào có thể xảy ra và ở đâu?

**Đáp án:** compiler cảnh báo unchecked raw call; khi chạy bridge thực hiện `checkcast String` trên `Integer` và ném `ClassCastException`. Lỗi xuất hiện trước khi thân `transform(String)` xử lý chuỗi.

### Bài 3. Bridge không có đối số

Với `Provider<T>.produce()` và `StringProvider.produce()`, có cần `checkcast` trong bridge không?

**Đáp án:** không cần vì bridge không nhận tham số; nó gọi `produce():String` rồi trả kết quả dưới dạng `Object`.

### Bài 4. Thay upper bound

Với `Receiver<T extends Number>` và `IntegerReceiver`, descriptor bridge nhận `Object` hay `Number`?

**Đáp án:** `(Ljava/lang/Number;)V`, vì erasure của `T` là `Number`. Method thật nhận `Integer`.

### Bài 5. Nhận diện compiler-generated method

Một lớp có hai `transform` trong `javap`: một có `ACC_PUBLIC`; phương thức kia có `ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC`. Có thể kết luận cả hai đều được viết thủ công trong source không?

**Đáp án:** không. Method có `ACC_BRIDGE` là phương thức cầu nối. Trong ví dụ, compiler tự tạo thêm phương thức đó để duy trì override sau erasure.

### Bài 6. Phân tích `@Override`

Vì sao nên giữ `@Override` cho `String transform(String)` trong `UppercaseProcessor`, mặc dù bytecode có thêm `transform(Object)`?

**Đáp án:** `@Override` yêu cầu compiler xác nhận mối quan hệ ghi đè ở cấp Java source; compiler mới là thành phần quyết định cách sinh bridge. Lập trình viên viết và bảo trì phương thức chuyên biệt, không phải cầu nối do compiler sinh.

## Kết luận cần nhớ

`javap` giúp thấy sự khác biệt giữa **mã Java source**, **kiểu bị xóa trong descriptor** và **method cầu nối được thêm vào class file**. Khi một phương thức generic ở lớp cha được lớp con ghi đè với kiểu cụ thể, `javac` có thể sinh method mang cờ `ACC_BRIDGE, ACC_SYNTHETIC` để giữ đúng đa hình. Hãy đối chiếu `-s` để đọc descriptor, `-c` để theo luồng ép kiểu/ủy quyền và `-v` để xác nhận flags. Bridge giải thích vì sao lời gọi qua kiểu cha vẫn đến đúng override sau type erasure, đồng thời cho thấy tại sao raw type sai có thể gây `ClassCastException`.
