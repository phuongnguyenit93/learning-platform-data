# Ảnh hưởng của bridge method đến dấu vết lỗi ép kiểu lúc chạy trong Java Generics

## Mục tiêu học tập

Khi sử dụng generics và ghi đè phương thức, đôi khi một `ClassCastException` xuất hiện ở nơi không thấy phép ép kiểu nào trong mã nguồn. Stack trace có thể chỉ đến phương thức của lớp con, dù phương thức đó khai báo tham số `String` và lỗi lại nói một `Integer` không thể chuyển thành `String`. Một nguyên nhân thường gặp là **bridge method** do trình biên dịch tự sinh để giữ đúng cơ chế ghi đè sau *type erasure*.

Sau bài này, bạn có thể:

1. Giải thích vì sao phương thức cầu nối được tạo ra khi lớp con chuyên biệt hóa tham số kiểu generic.
2. Phân biệt `ClassCastException` phát sinh **trong bridge** với lỗi ép kiểu xảy ra ở **vị trí người gọi**.
3. Đọc stack trace mà không nhầm bridge do compiler sinh với phương thức do lập trình viên viết.
4. Sử dụng `javap -c -p`, `javap -v` và reflection (`Method.isBridge()`, `isSynthetic()`) để xác minh vị trí ép kiểu.
5. Truy tìm nguồn dữ liệu sai kiểu từ raw type, unchecked invocation hoặc đoạn mã vượt qua kiểm tra generic.

## 1. Quan hệ giữa erasure, ghi đè và bridge

Generics của Java được triển khai chủ yếu bằng **type erasure**: tham số kiểu không được biểu diễn trong method descriptor của JVM giống như thông tin generic của mã nguồn. Ví dụ:

```java
interface Handler<T> {
    void handle(T value);
}

final class TextHandler implements Handler<String> {
    @Override
    public void handle(String value) {
        System.out.println(value);
    }
}
```

Đây là đoạn minh họa khai báo các kiểu; nếu muốn chạy một chương trình hoàn chỉnh, dùng ví dụ `BridgeTraceDemo.java` ở phần 3.

Ở mã nguồn, `Handler<String>` yêu cầu nhận `String` và `TextHandler.handle(String)` là một phương thức ghi đè hợp lệ. Nhưng khi dịch:

- Phương thức interface `Handler<T>.handle(T)` có erasure tương ứng với tham số `Object` vì `T` không có bound tường minh.
- Phương thức thực thi do người lập trình viết có tham số `String`.
- Để lời gọi tới `Handler.handle(Object)` vẫn dispatch tới implementation `TextHandler.handle(String)`, `javac` tạo thêm một **bridge method** mang chữ ký bytecode tương ứng.

Về mặt ý tưởng, compiler sinh logic như sau:

```java
// SƠ ĐỒ Ý TƯỞNG: không được tự khai báo thêm vào TextHandler.
public void handle(Object value) {
    handle((String) value);
}
```

Bridge có phép ép kiểu tại runtime: `(String) value`. Nếu đối số thực tế là `Integer`, phép ép kiểu này ném `ClassCastException` **trước khi phần thân `handle(String)` của người lập trình được gọi**.

Sơ đồ luồng:

```text
Handler<String> reference
          |
          | gọi handle("hello") — an toàn, đối số String
          v
  invokeinterface Handler.handle(Object)
          |
          v
  TextHandler.handle(Object) [bridge]
          |
          | checkcast String (PASS)
          v
  TextHandler.handle(String) [mã nguồn]
          |
          v
  Xử lý bình thường


Handler raw reference
          |
          | gọi handle(Integer) — unchecked invocation
          v
  invokeinterface Handler.handle(Object)
          |
          v
  TextHandler.handle(Object) [bridge]
          |
          | checkcast String (FAIL)
          v
  ClassCastException
  (chưa đi tới handle(String))
```

**Điểm quyết định:** bridge không phải một bước “Java tự kiểm tra generic ở mọi thời điểm chạy”. Nó là phương thức chuyển tiếp có các thao tác cụ thể do compiler tạo ra để giữ đúng quy tắc override. Một số bridge có `checkcast`, một số chỉ ủy quyền lời gọi và không cần ép kiểu đối số.

## 2. Vì sao stack trace có thể gây hiểu nhầm?

Stack trace cho biết phương thức đang thực thi khi ngoại lệ được tạo ra và chuỗi lời gọi dẫn đến đó. Nếu lệnh `checkcast` nằm trong bridge, top frame có thể hiển thị tên phương thức ở lớp con, ví dụ:

```text
BridgeTraceDemo$TextHandler.handle(BridgeTraceDemo.java:<line>)
```

`<line>` ở trên chỉ là ký hiệu minh họa: số dòng thực tế phụ thuộc nội dung tệp, thông tin debug khi biên dịch và compiler. Đây không phải nguyên văn stdout của chương trình ở phần sau.

Người đọc mã nguồn tìm `TextHandler.handle(String)` sẽ thấy không có cast nào:

```java
@Override
public void handle(String value) {
    System.out.println("accepted:" + value);
}
```

Tuy nhiên, JVM đang chạy **một phương thức khác cũng tên `handle`**: bridge `handle(Object)`. Trong stack trace thông thường, `StackTraceElement` cung cấp tên lớp, tên phương thức, tệp và dòng, **không cung cấp danh sách kiểu tham số hay cờ bridge**. Hai phương thức cùng tên có thể nhìn giống nhau khi chỉ quan sát stack trace.

Ngay cả vị trí dòng được gán cho bridge cũng không đủ để kết luận đó là phương thức nguồn. Trình biên dịch có thể ánh xạ bridge tới dòng khai báo phương thức hoặc thông tin dòng tương ứng. Do đó, **đừng suy ra rằng một lỗi ở dòng `handle(String)` nhất thiết do thân phương thức đó trực tiếp ném**.

Muốn kiểm chứng, cần kết hợp stack trace với bytecode hoặc reflection của lớp đã biên dịch.

## 3. Chương trình Java 17 hoàn chỉnh: lỗi ở bridge và lỗi ở caller

Chương trình dưới đây trình bày hai tình huống **cố ý** dùng raw type để vượt qua kiểm tra generic:

- Gọi handler chuyên biệt cho `String` qua một tham chiếu raw để đưa `Integer` vào bridge.
- Ghi một `Integer` vào `Box<String>` qua raw `Box`. `Box` không có override tạo bridge, nên lỗi xảy ra khi người gọi nhận kết quả thành `String`.

**Tệp `BridgeTraceDemo.java`:**

```java
import java.lang.reflect.Method;

public class BridgeTraceDemo {
    interface Handler<T> {
        void handle(T value);
    }

    static final class TextHandler implements Handler<String> {
        @Override
        public void handle(String value) {
            System.out.println("accepted:" + value);
        }
    }

    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Handler<String> typedHandler = new TextHandler();
        typedHandler.handle("safe");

        Handler rawHandler = typedHandler;
        try {
            rawHandler.handle(123);
        } catch (ClassCastException exception) {
            StackTraceElement frame = exception.getStackTrace()[0];
            System.out.println("bridge error:" + exception.getClass().getSimpleName());
            System.out.println("bridge top:" + frame.getClassName()
                    .replace("BridgeTraceDemo$", "") + "." + frame.getMethodName());
        }

        for (Method method : TextHandler.class.getDeclaredMethods()) {
            if (method.isBridge()) {
                System.out.println("bridge reflection:"
                        + method.getName()
                        + "(" + method.getParameterTypes()[0].getSimpleName()
                        + "), synthetic=" + method.isSynthetic());
            }
        }

        Box<String> typedBox = new Box<>("initial");
        Box rawBox = typedBox;
        rawBox.set(123);
        try {
            String value = typedBox.get();
            System.out.println(value);
        } catch (ClassCastException exception) {
            StackTraceElement frame = exception.getStackTrace()[0];
            System.out.println("caller error:" + exception.getClass().getSimpleName());
            System.out.println("caller top:" + frame.getClassName()
                    + "." + frame.getMethodName());
        }
    }
}
```

**Biên dịch và chạy bằng JDK 17+:**

```bash
javac --release 17 BridgeTraceDemo.java
java BridgeTraceDemo
```

`javac` có thể in ghi chú về thao tác unchecked/unsafe ở stderr trong bước biên dịch, vì hai lời gọi dùng raw type là cố ý. Phần dưới là **stdout của lệnh `java`**, đã kiểm chứng trên chương trình này:

```text
accepted:safe
bridge error:ClassCastException
bridge top:TextHandler.handle
bridge reflection:handle(Object), synthetic=true
caller error:ClassCastException
caller top:BridgeTraceDemo.main
```

Chương trình bắt ngoại lệ để trình bày phần tên phương thức ổn định hơn trong stack trace. Nó **không** in số dòng, class-loader hay toàn văn `ClassCastException.getMessage()`, vì các chi tiết đó có thể khác giữa các JDK hoặc cấu hình biên dịch.

### 3.1. Nhánh 1: `ClassCastException` từ bridge

Các câu lệnh:

```java
Handler<String> typedHandler = new TextHandler();
typedHandler.handle("safe");

Handler rawHandler = typedHandler;
rawHandler.handle(123);
```

Đoạn này đã có trong chương trình hoàn chỉnh; dòng cuối ở ví dụ thực tế được bọc trong `try/catch`.

Lời gọi `typedHandler.handle("safe")` hợp lệ vì đối số thuộc `String`. Ngược lại, nếu viết:

```java
// typedHandler.handle(123); // Không biên dịch: cần String, nhận int/Integer.
```

thì trình biên dịch sẽ chặn lỗi. Chỉ khi chủ động dùng raw `Handler`, lời gọi `rawHandler.handle(123)` mới có thể được biên dịch với cảnh báo unchecked và truyền `Integer` qua chữ ký đã xóa `handle(Object)`.

Thứ tự lúc runtime:

1. `rawHandler` vẫn trỏ đến một `TextHandler` thật; raw type chỉ thay đổi cách compiler kiểm tra ở nguồn, không tạo đối tượng handler khác.
2. Lời gọi theo interface được dispatch tới bridge `TextHandler.handle(Object)`.
3. Bridge thực thi `checkcast java/lang/String`.
4. `Integer` không phải `String`, nên JVM tạo `ClassCastException`.
5. Chương trình bắt lỗi và in `bridge top:TextHandler.handle`. Dòng `System.out.println("accepted:" + value)` trong `handle(String)` không được chạy ở lượt lỗi.

Ở đây, bridge chính là **vị trí ngoại lệ phát sinh**. Nhưng **nguyên nhân tạo dữ liệu sai kiểu** nằm ở lời gọi qua raw reference. Đọc top frame là bước xác định nơi lỗi bị phát hiện, chưa đủ để xác định vị trí gây ra vi phạm kiểu ban đầu.

### 3.2. Nhánh 2: lỗi ép kiểu ở caller mà không có bridge

`Box<T>` là một lớp generic thông thường:

```java
static final class Box<T> {
    private T value;

    Box(T value) { this.value = value; }

    T get() { return value; }

    void set(T value) { this.value = value; }
}
```

Trong class file của `Box`, `T` không bị ràng buộc nên các vị trí `T` được xóa thành `Object`. Không có subclass ghi đè phương thức generic ở trường hợp này nên **không cần sinh bridge để xử lý `Box.get()`/`set()`**.

Các câu lệnh:

```java
Box<String> typedBox = new Box<>("initial");
Box rawBox = typedBox;
rawBox.set(123);
String value = typedBox.get(); // ClassCastException tại caller.
```

được dùng bên trong chương trình chính; dòng đọc `value` được bọc `try/catch` để quan sát lỗi.

Sau lời gọi raw `set(123)`, trường trong cùng một đối tượng `Box<String>` thực tế chứa `Integer`. Đây là một dạng **heap pollution**: một vị trí được chương trình xem là mang giá trị của kiểu đã tham số hóa chứa đối tượng không thỏa kỳ vọng đó.

Khi `typedBox.get()` trả về giá trị qua descriptor có kiểu `Object`, compiler chèn phép cast sang `String` **ở chỗ dùng kết quả** để đáp ứng khai báo `String value`. Vì vậy lỗi hiển thị:

```text
caller error:ClassCastException
caller top:BridgeTraceDemo.main
```

Đây là chứng cứ rằng **không phải mọi ClassCastException liên quan đến generics đều có bridge**. Cùng một nguyên nhân gốc là vượt kiểm tra kiểu, nhưng điểm phát hiện sai kiểu có thể nằm ở caller thay vì trong bridge.

## 4. Kiểm tra bridge bằng `javap`

Biên dịch tệp ở phần 3, sau đó xem mã JVM của lớp lồng `TextHandler`:

```bash
javap -c -p 'BridgeTraceDemo$TextHandler'
```

Dùng dấu nháy đơn quanh tên có ký tự `$` trên Bash, zsh hoặc PowerShell để tránh shell coi đó là biến. Với Windows CMD, quy tắc trích dẫn tên lớp có thể khác. Các lệnh `javap` dưới đây đọc class file từ thư mục đầu ra của `javac`; nếu dịch sang thư mục khác, thêm `-classpath` phù hợp.

Phần kết quả đáng chú ý (lược bớt constructor và các phương thức không liên quan):

```text
public void handle(java.lang.String);
  Code:
     ...

public void handle(java.lang.Object);
  Code:
     0: aload_0
     1: aload_1
     2: checkcast     #23 // class java/lang/String
     5: invokevirtual #25 // Method handle:(Ljava/lang/String;)V
     8: return
```

Chỉ số constant pool `#23`, `#25` là giá trị của bản build minh họa; chúng có thể thay đổi. Điều cần quan sát là:

- Có thêm `handle(java.lang.Object)` dù mã nguồn chỉ khai báo `handle(String)`.
- Lệnh `checkcast java/lang/String` nằm trong `handle(Object)`.
- Sau cast, `invokevirtual` chuyển tiếp tới phương thức nhận `String`.
- Chính `checkcast` là nơi ném `ClassCastException` nếu đối số thực không phù hợp.

Xem cờ của phương thức:

```bash
javap -p -v 'BridgeTraceDemo$TextHandler'
```

Trong kết quả đã kiểm chứng có dạng:

```text
public void handle(java.lang.Object);
  descriptor: (Ljava/lang/Object;)V
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
```

`ACC_BRIDGE` biểu thị phương thức cầu nối do compiler tạo để hỗ trợ ngữ nghĩa của Java; `ACC_SYNTHETIC` cho biết nó không tương ứng với một khai báo phương thức thông thường do người lập trình viết trong nguồn. `Method.isBridge()` và `Method.isSynthetic()` qua reflection xác nhận tương ứng.

Muốn kiểm tra việc cast ở phía caller trong tình huống `Box<String>`, hãy xem bytecode của lớp chính:

```bash
javap -c -p BridgeTraceDemo
```

Tìm đoạn gọi `Box.get` theo descriptor trả về `Object` và lệnh `checkcast java/lang/String` xuất hiện **sau lời gọi này trong `main`**. Thay vì đoán vị trí từ stack trace, đối chiếu vị trí lệnh `checkcast` và đường gọi đã thực thi.

### So sánh hai loại vị trí lỗi

| Tình huống | Có bridge ở đường lỗi? | Nơi chứa `checkcast String` | Top frame quan sát |
| --- | --- | --- | --- |
| `TextHandler` nhận `Integer` qua raw `Handler` | Có | Bridge `TextHandler.handle(Object)` | `TextHandler.handle` |
| `Box<String>` bị raw `Box` ghi `Integer` rồi đọc ra `String` | Không cần bridge | Mã gọi `Box.get()` trong `main` | `BridgeTraceDemo.main` |

Hai hàng cùng ném `ClassCastException`, nhưng muốn kết luận “lỗi nằm ở bridge”, cần bằng chứng ở bytecode/reflection, **không chỉ dựa vào tên phương thức trong trace**.

## 5. Đọc stack trace của bridge như thế nào?

Một stack trace đầy đủ có thể bắt đầu đại loại như sau trong tình huống đầu tiên:

```text
java.lang.ClassCastException: ...
    at BridgeTraceDemo$TextHandler.handle(BridgeTraceDemo.java:<line>)
    at BridgeTraceDemo.main(BridgeTraceDemo.java:<line>)
```

Đây là **sơ đồ**, không phải bản chép nguyên văn: dấu `...` và `<line>` thay cho thông tin phụ thuộc runtime. Không dùng số dòng hay toàn văn thông báo để xác định kiểu dữ liệu một cách máy móc.

Đọc theo thứ tự:

1. **Loại ngoại lệ**: `ClassCastException` là dấu hiệu một phép cast tham chiếu thất bại ở runtime.
2. **Top frame**: xác định phương thức chứa lệnh đang ném lỗi. Nếu phương thức đó trông như không có cast, nghi ngờ bridge hoặc cast compiler chèn.
3. **Frame ngay dưới**: xác định đường gọi dẫn đến điểm thất bại; ở ví dụ, `main` gửi một giá trị sai qua raw `Handler`.
4. **Kiểu runtime thực**: tìm nguồn của đối số. Với Java hiện đại, message của CCE thường có tên kiểu nguồn/đích; cách biểu diễn module/class loader có thể thay đổi theo phiên bản Java.
5. **Bytecode**: nếu nghi bridge, dùng `javap -p -v` để tìm `ACC_BRIDGE`, và `javap -c -p` để tìm `checkcast` hoặc lời gọi ủy quyền.
6. **Luồng dữ liệu**: lần ngược nơi raw type, cast unchecked, reflection hoặc thư viện cũ đã phá vỡ hợp đồng generic.

**Cẩn trọng:** stack trace Java thông thường không in descriptor như `(Ljava/lang/Object;)V`. Ngay cả khi có hai `handle` trong bytecode, chúng đều được hiển thị dưới tên `handle`. Không thể khẳng định frame là bridge chỉ vì nó có tên giống phương thức mã nguồn hoặc số dòng trùng với khai báo.

Một kỹ thuật hữu ích khi cần chứng minh bridge mà không phụ thuộc cách debugger đặt breakpoint:

```java
for (java.lang.reflect.Method method
        : TextHandler.class.getDeclaredMethods()) {
    if (method.isBridge()) {
        System.out.println(method);
    }
}
```

Đây là đoạn minh họa đặt **bên trong `BridgeTraceDemo`**, nơi `TextHandler` đã được định nghĩa. Reflection có thể hiển thị phương thức bridge `handle(Object)`. Khi viết công cụ phân tích reflection, cân nhắc lọc `isBridge()` cho mục đích hiển thị API người viết; khi phân tích **runtime dispatch/ABI**, cần giữ thông tin bridge để hiểu đầy đủ class file.

## 6. Vì sao warning unchecked liên quan trực tiếp đến lỗi?

Trong chương trình, hai dòng:

```java
Handler rawHandler = typedHandler;
rawHandler.handle(123);

Box rawBox = typedBox;
rawBox.set(123);
```

là nguyên nhân tạo đường truyền dữ liệu không an toàn. `rawHandler` và `rawBox` là **raw type**, tức thiếu tham số generic. Chúng làm mất kiểm tra đối số ở mức mà chương trình thông thường được compiler bảo đảm.

Để xem cảnh báo rõ hơn:

```bash
javac --release 17 -Xlint:rawtypes -Xlint:unchecked BridgeTraceDemo.java
```

Bạn sẽ gặp cảnh báo liên quan tới khai báo raw `Handler`/`Box` và các lời gọi unchecked `handle`/`set`. Cảnh báo này không phải “nhiễu” có thể bỏ qua vô điều kiện: nó chỉ ra chỗ hợp đồng generic không còn được xác minh đủ tại thời điểm biên dịch.

**Không có `rawHandler.handle(123)` tương đương khi giữ kiểu chính xác:**

```java
Handler<String> typedHandler = new TextHandler();
// typedHandler.handle(123); // Compiler từ chối.
typedHandler.handle("safe");  // Hợp lệ.
```

Điều tương tự áp dụng cho `Box<String>`: lời gọi `typedBox.set(123)` không biên dịch. Sự khác biệt là raw type đã cho phép điều bất hợp lệ đi qua và khiến lỗi chỉ xuất hiện muộn khi bridge hoặc caller buộc phải cast.

Ngoài raw type, cần rà soát các nguồn dữ liệu sai kiểu khác:

- Cast unchecked, nhất là `(List<String>) someObject` hoặc ép kiểu generic không thể được kiểm tra đầy đủ vì erasure.
- API phản chiếu (`Method.invoke`, field access) hoặc thư viện sinh bytecode không giữ đúng hợp đồng kiểu.
- Thư viện legacy trả về collection không tham số hóa.
- Các đường đi qua varargs generic hoặc cấu trúc có heap pollution, nếu có cảnh báo unchecked thực sự phù hợp.

Không nên quy lỗi cho bridge nếu không thấy raw type ở **chính frame gần lỗi**. Dữ liệu sai kiểu có thể được đưa vào một đối tượng từ sớm và bị phát hiện tại một lời gọi khác nhiều tầng sau đó.

## 7. Khi nào bridge không phải nơi phát sinh `ClassCastException`?

Bridge xuất hiện trong nhiều trường hợp ngoài việc chuyển `Object` thành kiểu cụ thể của tham số.

### 7.1. Covariant return

Ví dụ:

```java
class Animal {
    Animal copy() {
        return this;
    }
}

final class Dog extends Animal {
    @Override
    Dog copy() {
        return this;
    }
}
```

Trong trường hợp này, Java cho phép phương thức ở lớp con trả về `Dog` thay vì `Animal` (kiểu trả về hiệp biến). JVM descriptor có bao gồm kiểu trả về, vì vậy compiler có thể tạo một bridge mang descriptor trả về `Animal` và chuyển tiếp tới `Dog.copy()`.

Bridge kiểu này có thể **không cần `checkcast` đối số**. Chỉ thấy `ACC_BRIDGE` không đủ để kết luận nó là nơi xảy ra ClassCastException. Cần xem bytecode cụ thể.

### 7.2. Getter trả về kiểu generic

`Box<T>.get()` trả về `T`, nhưng erasure của T là `Object`. Với `Box<String>`, khi giá trị trả về được đưa vào một biến `String`, cast thường nằm tại vị trí caller như phần 3.2.

Với phương thức trả về `T` được override bởi lớp con, có thể xuất hiện **bridge mang descriptor khác** để đảm bảo override; lúc đó cần kiểm tra riêng body của bridge và chỗ dùng kết quả. Đừng áp dụng quy tắc “tất cả getter generic đều cast trong bridge”.

### 7.3. Cast được viết trực tiếp trong mã nguồn

Nếu lập trình viên viết:

```java
Object value = Integer.valueOf(12);
String text = (String) value; // Lỗi ngay tại phép cast do người viết.
```

đây là ví dụ minh họa một phép cast trực tiếp trong phương thức, không cần generics hay bridge. Lỗi do phép cast ở dòng mã nguồn tương ứng; `javap` cũng có `checkcast java/lang/String`, nhưng method chứa lệnh đó không phải bridge.

Vì vậy, ba vị trí cần phân biệt là **bridge**, **caller do compiler chèn cast**, và **cast tường minh của người lập trình**.

## 8. Bridge và stack trace khi debug thư viện/framework

Trong ứng dụng lớn, ngăn xếp có thể chứa proxy, interceptor, reflection hoặc các adapter gọi vào một interface generic. Khi nhìn thấy một lỗi ép kiểu, hãy tách ba trách nhiệm:

- **Nơi gửi dữ liệu:** component đã truyền đối số sai kiểu hoặc làm ô nhiễm trạng thái generic.
- **Nơi chuyển giao:** interface, proxy hay bridge thực hiện dispatch và có thể chứa cast.
- **Nơi phát hiện lỗi:** instruction `checkcast` cụ thể ném `ClassCastException`.

Ví dụ, một framework lưu handler qua raw hoặc không giữ metadata generic chính xác có thể khiến nó gửi đối tượng không phù hợp. Stack trace hiện ra ở bridge của implementation, nhưng sửa bằng cách xóa bridge hoặc sửa phương thức `handle(String)` sẽ không giải quyết nguyên nhân. Cần thay đổi nơi framework chọn handler, kiểm tra kiểu đối số hoặc khôi phục hợp đồng generic ở ranh giới.

Khi một stack trace có phương thức do compiler sinh, một số công cụ instrumentation/profiling có thể hiển thị thêm thông tin synthetic/bridge. Tuy vậy, cách hiển thị phụ thuộc công cụ. Đối với chẩn đoán có thể kiểm chứng, `javap` trên **đúng class file đang chạy** đáng tin hơn suy đoán từ giao diện IDE.

Nếu có nhiều phiên bản JAR trong classpath hoặc class loader khác nhau, hãy xác minh lớp thực sự được tải từ đâu trước khi phân tích bản .class trong source tree. Trace cũng có thể có các frame reflection/proxy, nên không nên cho rằng hai frame liền kề trong mọi ứng dụng luôn là caller và bridge.

## 9. Quy trình điều tra một lỗi ép kiểu nghi do bridge

Sử dụng các bước sau theo thứ tự:

1. **Giữ stack trace đầy đủ.** Lưu loại ngoại lệ, message, top frame và các frame ngay dưới; đừng chỉ trích dòng báo lỗi ngắn.
2. **Xác định kiểu nhận ở nguồn.** Tìm interface hoặc superclass generic mà lớp đang thực thi đã chuyên biệt hóa, ví dụ `Handler<String>`.
3. **So sánh với erasure.** Với `Handler<T>` không có bound, tham số T sau erasure là `Object`; implementation nhận `String` có khả năng cần bridge.
4. **Kiểm tra class file.** Chạy `javap -p -v` tìm phương thức `ACC_BRIDGE`; chạy `javap -c -p` tìm `checkcast` và lời gọi ủy quyền.
5. **Phân biệt vị trí phát hiện.** Nếu cast trong bridge, top frame thường là method của bridge. Nếu cast được chèn ở caller sau khi lấy kết quả từ generic API, top frame thường là caller.
6. **Lần ngược nguồn sai kiểu.** Tìm raw type, unchecked warning, cast không được kiểm tra, serialization, reflection hay adapter chuyển đổi dữ liệu.
7. **Chỉnh sửa ranh giới dữ liệu.** Tham số hóa API đúng kiểu, tránh bỏ generic, xác thực dữ liệu runtime nếu nguồn không đáng tin và không dùng cast để “dập” lỗi compile.
8. **Kiểm chứng lại.** Bật `-Xlint:rawtypes,unchecked`, viết ca kiểm thử đưa đúng/sai kiểu qua ranh giới liên quan; chỉ gọi là đã sửa khi đường truyền sai kiểu không còn.

Một ghi chú hữu ích khi báo lỗi: “Bridge là nơi exception được ném” **khác** với “bridge là nguyên nhân bug”. Phương thức do compiler sinh đang thực thi một kiểm tra kiểu cần thiết; nguồn vi phạm có thể nằm ở code gọi từ trước.

## 10. Các sai lầm thường gặp

| Nhận định sai | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “Lỗi tại `handle(String)` thì chắc chắn do code trong body `handle(String)`.” | Stack frame không ghi kiểu tham số; bridge `handle(Object)` có cùng tên. | Kiểm tra `ACC_BRIDGE` và `checkcast` bằng `javap`. |
| “Bridge tự tạo dữ liệu sai kiểu.” | Bridge thường chỉ kiểm tra/ủy quyền đối số đã nhận. | Truy nguồn raw/unchecked invocation hoặc dữ liệu sai được truyền vào. |
| “Bất kỳ `ClassCastException` nào của generics đều ở bridge.” | Caller cũng có thể chứa cast do compiler chèn. | Xem bytecode của cả method được gọi và caller. |
| “`isSynthetic()` đồng nghĩa với `isBridge()`.” | Synthetic có nhiều loại thành phần do compiler/tool tạo. | Dùng `isBridge()` để nhận diện bridge; xem cả flags khi cần. |
| “Có bridge thì chắc chắn có `checkcast`.” | Bridge cho covariant return hoặc trường hợp khác có thể chỉ delegate. | Đọc phần Code của bridge cụ thể. |
| “Bỏ `@Override`, thêm cast, hay bỏ qua warning sẽ sửa lỗi.” | Thay đổi bề mặt, mất kiểm tra kiểu hoặc che dấu triệu chứng. | Sửa hợp đồng generic và nguồn dữ liệu sai kiểu. |
| “Số dòng ở trace xác định duy nhất một method overload.” | Stack trace không mang descriptor và dòng bridge do compiler gán. | So class, method, descriptor và bytecode. |
| “Vì compile không lỗi nên không thể có CCE.” | Raw/unchecked là vùng compiler không chứng minh được an toàn. | Bật lint, kiểm tra chỗ phá generic và test runtime có chủ đích. |

## 11. Bài tập tự kiểm tra

**Bài 1.** Một lớp triển khai `Consumer<String>` có `accept(String)`. Một raw `Consumer` gọi `accept(Integer.valueOf(1))`. Nếu bridge `accept(Object)` chứa `checkcast String`, ngoại lệ xuất hiện ở đâu?

**Đáp án:** Trong bridge `accept(Object)` của lớp implementation, trước khi phần thân `accept(String)` chạy.

**Bài 2.** Tại sao stack trace chỉ hiện `SomeConsumer.accept` không đủ xác định có phải bridge?

**Đáp án:** Stack trace mặc định chỉ hiện tên lớp và tên phương thức, không in kiểu tham số hay cờ bridge. Phải kiểm tra bytecode/flags hoặc reflection.

**Bài 3.** Một `List<String>` thực tế chứa `Integer` do raw list thêm vào. Khi vòng lặp đọc `String s` rồi ném CCE, có chắc bridge đã ném lỗi?

**Đáp án:** Không. Compiler có thể chèn `checkcast String` ở đoạn lấy phần tử của caller. Cần kiểm tra bytecode tại frame tương ứng.

**Bài 4.** Trong `BridgeTraceDemo`, vì sao output có `accepted:safe` nhưng không có `accepted:123`?

**Đáp án:** Lần gọi an toàn qua `Handler<String>` đưa String vào thành công. Lần gọi raw đưa Integer tới bridge, cast thất bại trước khi gọi `handle(String)`.

**Bài 5.** `javap` cho thấy `ACC_BRIDGE` nhưng không có `checkcast`. Có thể kết luận bridge này gây CCE không?

**Đáp án:** Không. Cờ bridge xác nhận vai trò chuyển tiếp, không khẳng định nó chứa phép cast thất bại. Cần xem code và stack thực tế.

**Bài 6.** Cần sửa bug ở raw handler bằng cách nào?

**Đáp án:** Giữ `Handler<String>` xuyên suốt các nơi lưu trữ và gọi; loại bỏ raw invocation, không truyền Integer tới handler chỉ chấp nhận String. Nếu đầu vào là `Object` từ nguồn ngoài, xác thực/chuyển đổi nó trước khi gọi handler.

## 12. Ghi nhớ

Bridge method giúp ngữ nghĩa ghi đè ở mã nguồn Java tiếp tục đúng khi các chữ ký generic bị xóa ở bytecode. Nếu bridge chứa lệnh `checkcast`, nó có thể là frame đầu của `ClassCastException` dù tác giả không viết phép cast nào trong method gốc. Tuy nhiên, lỗi ép kiểu cũng có thể xảy ra tại caller, chẳng hạn khi một generic getter trả về `Object` sau erasure và giá trị được gán sang `String`.

Để chẩn đoán đúng, hãy kết hợp **stack trace → method descriptor → bytecode `checkcast` → đường truyền dữ liệu sai kiểu**. Dấu vết cho biết nơi lỗi bị phát hiện; nguyên nhân thường là đoạn mã vượt qua kiểm tra kiểu ở ranh giới generic, raw type hoặc unchecked operation.
